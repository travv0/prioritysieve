################################################################
#                          IMPORTS
################################################################
# Use package-relative imports because Anki renames addon folders to numeric IDs.
#
# Correct:
# from . import browser_utils
#
# Incorrect (causes "not found" crashes):
# from prioritysieve import browser_utils
################################################################

import json
import sqlite3
from dataclasses import dataclass
from collections.abc import Iterable
from functools import partial
from pathlib import Path
import sys
from typing import Optional
import aqt
from anki import hooks
from anki.consts import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED
from anki.utils import ids2str
from anki.tags import TagManager
from aqt import gui_hooks, mw
from aqt.browser.browser import Browser
from aqt.qt import (  # pylint:disable=no-name-in-module
    QAction,
    QDesktopServices,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QKeySequence,
    QMenu,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
    QUrl,
    QVBoxLayout,
)
from aqt.toolbar import Toolbar
from aqt.utils import tooltip
from aqt.webview import AnkiWebView

from . import prioritysieve_config
from . import prioritysieve_globals as ps_globals
from . import (
    browser_utils,
    card_filters,
    debug_utils,
    message_box_utils,
    priority_gap_utils,
    name_file_utils,
    tags_and_queue_utils,
    text_preprocessing,
    toolbar_stats,
)
from .entry_db import EntryDB
from .kanji_utils import (
    contains_hiragana,
    contains_kana,
    contains_katakana,
    extract_kanji_sequence,
    is_kanji_subsequence,
)
from .prioritysieve_config import PrioritySieveConfig, PrioritySieveConfigFilter
from .extra_settings import prioritysieve_extra_settings, extra_settings_keys
from .extra_settings.prioritysieve_extra_settings import PrioritySieveExtraSettings
from .reading_utils import normalize_reading
from .recalc import recalc_main
from .recalc.anki_data_utils import AnkiCardData, AnkiDBRowData
from .recalc.caching import _build_entry
from .settings import settings_dialog
from .settings.settings_dialog import SettingsDialog
from .settings.settings_language_selector import LanguageSelectorDialog
from .tag_selection_dialog import TagSelectionDialog
from .toolbar_stats import EntryToolbarStats
from .priority_files import load_priority_map, KNOWN_ENTRIES_DIR
from . import stats_graph

_TOOL_MENU: str = "ps_tool_menu"
_BROWSE_MENU: str = "ps_browse_menu"
_CONTEXT_MENU: str = "ps_context_menu"

_startup_sync: bool = True
_showed_update_warning: bool = False
_state_before_sync_recalc: dict[str, str] | None = None
_pending_changes_before_sync: set[str] = set()
_followup_sync_pending: bool = False
_last_sync_was_followup: bool = False


def _get_kanjicards_manager() -> Optional[object]:
    try:
        module = sys.modules.get("KanjiCards")
        if module is None:
            module = __import__("KanjiCards")  # type: ignore[import]
        manager = getattr(module, "_manager", None)
        if manager is None:
            initializer = getattr(module, "_initialize_manager", None)
            if callable(initializer):
                try:
                    initializer()
                except Exception:  # pylint:disable=broad-except
                    return None
                manager = getattr(module, "_manager", None)
        return manager
    except Exception:  # pylint:disable=broad-except
        return None


def _kanjicards_installed() -> bool:
    if _get_kanjicards_manager() is not None:
        return True
    try:
        __import__("KanjiCards")
        return True
    except Exception:
        try:
            __import__("kanjicards")
            return True
        except Exception:
            return False


def _run_recalc_with_kanjicards_followup() -> None:
    manager = _get_kanjicards_manager()
    run_kc_recalc = getattr(manager, "run_recalc", None) if manager is not None else None

    if not callable(run_kc_recalc):
        recalc_main.recalc()
        return

    previous_callback = getattr(recalc_main, "_followup_sync_callback", None)

    def _run_followups() -> None:
        try:
            run_kc_recalc()
        except Exception as error:  # pylint:disable=broad-except
            print(f"PrioritySieve: KanjiCards recalc failed ({error})")
        finally:
            if callable(previous_callback):
                try:
                    previous_callback()
                except Exception as callback_error:  # pylint:disable=broad-except
                    print(
                        "PrioritySieve: follow-up callback failed after KanjiCards recalc "
                        f"({callback_error})"
                    )

    try:
        recalc_main.set_followup_sync_callback(_run_followups)
    except Exception as error:  # pylint:disable=broad-except
        print(
            "PrioritySieve: unable to attach KanjiCards recalc follow-up "
            f"({error}); falling back to PrioritySieve-only recalc"
        )
        recalc_main.recalc()
        return

    try:
        recalc_main.recalc()
    except Exception:
        try:
            recalc_main.set_followup_sync_callback(previous_callback)
        except Exception:  # pylint:disable=broad-except
            pass
        raise


def _schedule_followup_sync() -> None:
    assert mw is not None
    global _followup_sync_pending
    _followup_sync_pending = True
    print("PrioritySieve: running follow-up sync after auto recalc")

    ps_changed = bool(
        getattr(recalc_main, "_last_modified_cards_count", 0)
        or getattr(recalc_main, "_last_modified_notes_count", 0)
    )

    manager = _get_kanjicards_manager()
    if manager is None or not hasattr(manager, "run_after_sync"):
        if ps_changed:
            mw.onSync()
        else:
            _followup_sync_pending = False
        return

    def _finish(kc_changed: bool) -> None:
        global _followup_sync_pending
        any_changes = ps_changed or kc_changed
        if not any_changes:
            _followup_sync_pending = False
            return

        mark_followup = getattr(manager, "mark_followup_sync_scheduled", None)
        if callable(mark_followup):
            try:
                mark_followup()
            except Exception:  # pylint:disable=broad-except
                pass
        mw.onSync()

    try:
        manager.run_after_sync(
            allow_followup=False,
            on_finished=_finish,
        )
    except Exception:  # pylint:disable=broad-except
        if ps_changed:
            mw.onSync()
        else:
            _followup_sync_pending = False


def main() -> None:
    # Support anki version 25.07.3 and above
    # Place hooks in the order they are executed

    gui_hooks.top_toolbar_did_init_links.append(init_toolbar_items)

    gui_hooks.profile_did_open.append(load_am_profile_configs)
    gui_hooks.profile_did_open.append(reset_startup_sync_variable)
    gui_hooks.profile_did_open.append(init_db)
    gui_hooks.profile_did_open.append(create_am_directories_and_files)
    gui_hooks.profile_did_open.append(register_addon_dialogs)
    gui_hooks.profile_did_open.append(redraw_toolbar)
    gui_hooks.profile_did_open.append(init_tool_menu_and_actions)
    gui_hooks.profile_did_open.append(init_browser_menus_and_actions)
    gui_hooks.profile_did_open.append(text_preprocessing.update_translation_table)
    gui_hooks.profile_did_open.append(maybe_show_version_warning_wrapper)

    gui_hooks.sync_will_start.append(cache_state_before_sync)
    gui_hooks.sync_did_finish.append(recalc_after_sync)

    gui_hooks.webview_will_show_context_menu.append(add_text_as_name_action)

    gui_hooks.profile_will_close.append(cleanup_profile_session)


def init_toolbar_items(links: list[str], toolbar: Toolbar) -> None:
    # Adds the per-language stats and 'Recalc' to the toolbar

    entry_toolbar_stats = EntryToolbarStats()
    am_config = PrioritySieveConfig()

    # Show Recalc button (global setting)
    if not am_config.hide_recalc_toolbar:
        label = "Recalc"
        links.append(
            toolbar.create_link(
                cmd="recalc_toolbar",
                label=label,
                func=_run_recalc_with_kanjicards_followup,
                tip=f"Shortcut: {am_config.shortcut_recalc.toString()}",
                id="recalc_toolbar",
            )
        )

    # Show per-language stats (format: "PREFIX: reviewed/tracked")
    for lang_stats in entry_toolbar_stats.language_stats:
        if not lang_stats.is_visible:
            continue

        command = f"lang_stats_{lang_stats.language_name}"
        message = lang_stats.tooltip
        links.append(
            toolbar.create_link(
                cmd=command,
                label=lang_stats.label,
                func=lambda msg=message: tooltip(msg),
                tip=message,
                id=command,
            )
        )


def load_am_profile_configs() -> None:
    assert mw is not None

    profile_settings_path = Path(
        mw.pm.profileFolder(), ps_globals.PROFILE_SETTINGS_FILE_NAME
    )
    try:
        with open(profile_settings_path, encoding="utf-8") as file:
            profile_settings = json.load(file)
            prioritysieve_config.load_stored_am_configs(profile_settings)
    except FileNotFoundError:
        # This is reached when we load a new anki profile that hasn't saved
        # any prioritysieve settings yet. It's important that we don't carry over
        # any settings from the previous profile because they can be somewhat
        # hidden (like note filter tags), which could lead to completely unexpected
        # results for no apparent reason. We therefore reset meta.json to
        # config.json (default settings)
        prioritysieve_config.reset_all_configs()


def reset_startup_sync_variable() -> None:
    # we have to reset this variable on profile_did_open rather than
    # profile_will_close, because sync can trigger after the latter.
    global _startup_sync
    _startup_sync = True


def init_db() -> None:
    with EntryDB() as entry_db:
        entry_db.create_schema()


def create_am_directories_and_files() -> None:
    assert mw is not None

    names_file_path: Path = Path(mw.pm.profileFolder(), ps_globals.NAMES_TXT_FILE_NAME)
    known_entries_dir_path: Path = Path(
        mw.pm.profileFolder(), KNOWN_ENTRIES_DIR
    )
    priority_files_dir_path: Path = Path(
        mw.pm.profileFolder(), ps_globals.PRIORITY_FILES_DIR_NAME
    )

    # Create the file if it doesn't exist
    names_file_path.touch(exist_ok=True)

    if not known_entries_dir_path.exists():
        Path(known_entries_dir_path).mkdir()

    if not priority_files_dir_path.exists():
        Path(priority_files_dir_path).mkdir()


def register_addon_dialogs() -> None:
    # We use the Anki dialog manager to handle our dialogs

    from .generators.generators_window import GeneratorWindow
    from .progression.progression_window import ProgressionWindow
    from .known_entries_exporter import KnownEntriesExporterDialog

    aqt.dialogs.register_dialog(
        name=ps_globals.SETTINGS_DIALOG_NAME,
        creator=SettingsDialog,
    )
    aqt.dialogs.register_dialog(
        name=ps_globals.GENERATOR_DIALOG_NAME,
        creator=GeneratorWindow,
    )
    aqt.dialogs.register_dialog(
        name=ps_globals.PROGRESSION_DIALOG_NAME,
        creator=ProgressionWindow,
    )
    aqt.dialogs.register_dialog(
        name=ps_globals.KNOWN_ENTRIES_EXPORTER_DIALOG_NAME,
        creator=KnownEntriesExporterDialog,
    )


def redraw_toolbar() -> None:
    # Updates the toolbar stats
    # Wrapping this makes testing easier because we don't have to mock mw
    assert mw is not None
    mw.toolbar.draw()


def init_tool_menu_and_actions() -> None:
    assert mw is not None

    for action in mw.form.menuTools.actions():
        if action.objectName() == _TOOL_MENU:
            return  # prevents duplicate menus on profile-switch

    am_config = PrioritySieveConfig()

    settings_action = create_settings_action(am_config)
    recalc_action = create_recalc_action(am_config)
    generators_action = create_generators_dialog_action(am_config)
    progression_action = create_progression_dialog_action(am_config)
    reset_tags_action = create_tag_reset_action()
    duplicate_entries_action = create_duplicate_entries_action()
    variant_entries_action = create_variant_entries_action()
    suspended_only_entries_action = create_suspended_only_entries_action()
    missing_priority_cards_action = create_missing_priority_cards_action()
    missing_priority_entries_action = create_missing_priority_entries_action()
    guide_action = create_guide_action()
    changelog_action = create_changelog_action()

    am_tool_menu = create_am_tool_menu()
    am_tool_menu.addAction(settings_action)
    am_tool_menu.addAction(recalc_action)
    am_tool_menu.addAction(generators_action)
    am_tool_menu.addAction(progression_action)
    known_entries_exporter_action = create_known_entries_exporter_action(am_config)
    am_tool_menu.addAction(known_entries_exporter_action)
    am_tool_menu.addAction(reset_tags_action)
    am_tool_menu.addAction(duplicate_entries_action)
    am_tool_menu.addAction(variant_entries_action)
    am_tool_menu.addAction(suspended_only_entries_action)
    am_tool_menu.addAction(missing_priority_cards_action)
    am_tool_menu.addAction(missing_priority_entries_action)
    am_tool_menu.addAction(guide_action)
    am_tool_menu.addAction(changelog_action)

    if ps_globals.DEV_MODE:
        test_action = create_test_action()
        am_tool_menu.addAction(test_action)


def init_browser_menus_and_actions() -> None:
    am_config = PrioritySieveConfig()

    learn_now_action = create_learn_now_action(am_config)
    browse_entry_action = create_browse_same_entry_action()
    browse_entry_unknowns_action = create_browse_same_entry_unknowns_action(am_config)
    browse_entry_unknowns_broad_action = create_browse_same_entry_unknowns_broad_action(
        am_config
    )
    already_known_tagger_action = create_already_known_tagger_action(am_config)

    def setup_browser_menu(_browser: Browser) -> None:
        browser_utils.browser = _browser

        for action in browser_utils.browser.form.menubar.actions():
            if action.objectName() == _BROWSE_MENU:
                return  # prevents duplicate menus on profile-switch

        am_browse_menu = QMenu("PrioritySieve", mw)
        am_browse_menu_creation_action = browser_utils.browser.form.menubar.addMenu(
            am_browse_menu
        )
        assert am_browse_menu_creation_action is not None
        am_browse_menu_creation_action.setObjectName(_BROWSE_MENU)

        am_browse_menu.addAction(learn_now_action)
        am_browse_menu.addAction(browse_entry_action)
        am_browse_menu.addAction(browse_entry_unknowns_action)
        am_browse_menu.addAction(browse_entry_unknowns_broad_action)
        am_browse_menu.addAction(already_known_tagger_action)

    def setup_context_menu(_browser: Browser, context_menu: QMenu) -> None:
        for action in context_menu.actions():
            if action.objectName() == _CONTEXT_MENU:
                return  # prevents duplicate menus on profile-switch

        context_menu_creation_action = context_menu.insertSeparator(learn_now_action)
        assert context_menu_creation_action is not None

        context_menu.addAction(learn_now_action)
        context_menu.addAction(browse_entry_action)
        context_menu.addAction(browse_entry_unknowns_action)
        context_menu.addAction(browse_entry_unknowns_broad_action)
        context_menu.addAction(already_known_tagger_action)
        context_menu_creation_action.setObjectName(_CONTEXT_MENU)

    gui_hooks.browser_menus_did_init.append(setup_browser_menu)
    gui_hooks.browser_will_show_context_menu.append(setup_context_menu)


def cache_state_before_sync() -> None:
    # Anki can sync automatically on startup, but we don't
    # want to recalc at that point.
    global _startup_sync
    global _state_before_sync_recalc
    global _last_sync_was_followup

    if mw.pm.auto_syncing_enabled():
        if _startup_sync:
            # trivial bug: this will cause recalc to not run on the first profile close
            # sync after the user first activates the Anki 'auto_syncing_enabled'
            # setting, but that's not a big deal.
            _startup_sync = False
            _last_sync_was_followup = False
            return

    extra_settings = PrioritySieveExtraSettings()
    global _followup_sync_pending
    is_followup_sync = _followup_sync_pending
    _followup_sync_pending = False
    _last_sync_was_followup = is_followup_sync

    previous_state_json = extra_settings.get_recalc_collection_state()
    previous_settings_state_json = extra_settings.get_recalc_settings_state()
    print("PrioritySieve pre-sync previous stored state:", previous_state_json)

    # Compute per-language state
    current_per_lang_state: dict[str, str] = {}
    try:
        per_lang_state = recalc_main.compute_per_language_filters_state()
        for lang_name, state in per_lang_state.items():
            current_per_lang_state[lang_name] = json.dumps(state, sort_keys=True)
    except Exception as error:  # pylint:disable=broad-except
        print(
            f"PrioritySieve: failed to snapshot collection state before sync ({error})"
        )
        # Fall back to cached state
        if previous_state_json:
            try:
                cached = json.loads(previous_state_json)
                if isinstance(cached, dict):
                    current_per_lang_state = cached
            except json.JSONDecodeError:
                pass

    recalc_main.set_followup_sync_callback(None)

    # Store combined state as JSON dict
    current_state_json = json.dumps(current_per_lang_state, sort_keys=True)
    print("PrioritySieve pre-sync per-language state:", current_state_json)

    current_settings_state_json: str | None = None
    try:
        current_settings_state_json = json.dumps(
            prioritysieve_config.get_config_dict(), sort_keys=True
        )
    except Exception as error:  # pylint:disable=broad-except
        print(
            "PrioritySieve: falling back to cached settings state"
            f" (snapshot failed: {error})"
        )
        current_settings_state_json = extra_settings.get_recalc_settings_state()

    extra_settings.set_recalc_collection_state(current_state_json)
    if current_settings_state_json is not None:
        extra_settings.set_recalc_settings_state(current_settings_state_json)

    # Determine which languages have pending changes
    languages_with_changes: set[str] = set()

    if is_followup_sync:
        print("PrioritySieve: skipping pending-change probe (follow-up sync)")
    else:
        # Check for settings changes (affects all languages)
        settings_changed = False
        if current_settings_state_json is None:
            settings_changed = True
        elif previous_settings_state_json is None:
            settings_changed = True
        else:
            settings_changed = (
                previous_settings_state_json != current_settings_state_json
            )

        if settings_changed:
            # Settings changed, mark all current languages as changed
            languages_with_changes.update(current_per_lang_state.keys())
        else:
            # Check per-language collection state changes
            previous_per_lang: dict[str, str] = {}
            if previous_state_json:
                try:
                    cached = json.loads(previous_state_json)
                    if isinstance(cached, dict):
                        previous_per_lang = cached
                    else:
                        # Old format was a list, treat as all languages changed
                        languages_with_changes.update(current_per_lang_state.keys())
                except json.JSONDecodeError:
                    # Malformed JSON, treat as all languages changed
                    languages_with_changes.update(current_per_lang_state.keys())

            if not languages_with_changes:
                # Compare per-language states
                all_lang_names = set(current_per_lang_state.keys()) | set(previous_per_lang.keys())
                for lang_name in all_lang_names:
                    current = current_per_lang_state.get(lang_name)
                    previous = previous_per_lang.get(lang_name)
                    if current != previous:
                        languages_with_changes.add(lang_name)

    global _pending_changes_before_sync
    _pending_changes_before_sync = languages_with_changes
    print(
        "PrioritySieve pre-sync change flags:",
        {
            "languages_with_pending_changes": sorted(languages_with_changes),
            "followup_sync": is_followup_sync,
        },
    )

    _state_before_sync_recalc = current_per_lang_state


def recalc_after_sync(success: bool | None = None) -> None:
    global _state_before_sync_recalc
    global _pending_changes_before_sync
    global _last_sync_was_followup

    was_followup_sync = _last_sync_was_followup
    _last_sync_was_followup = False

    extra_settings = PrioritySieveExtraSettings()

    recalc_main.set_followup_sync_callback(None)

    if success is False:
        _state_before_sync_recalc = None
        recalc_main.set_followup_sync_callback(None)
        _pending_changes_before_sync = set()
        return

    am_config = PrioritySieveConfig()
    pending_language_changes = _pending_changes_before_sync

    # Compute post-sync per-language state
    post_per_lang_state: dict[str, str] = {}
    try:
        per_lang_state = recalc_main.compute_per_language_filters_state()
        for lang_name, state in per_lang_state.items():
            post_per_lang_state[lang_name] = json.dumps(state, sort_keys=True)
    except Exception as error:  # pylint:disable=broad-except
        if was_followup_sync:
            print(
                "PrioritySieve: follow-up sync state snapshot failed; skipping post-sync recalc "
                f"({error})"
            )
            try:
                cached = extra_settings.get_recalc_collection_state()
                if cached:
                    parsed = json.loads(cached)
                    if isinstance(parsed, dict):
                        _state_before_sync_recalc = parsed
                    else:
                        _state_before_sync_recalc = None
                else:
                    _state_before_sync_recalc = None
            except Exception:  # pylint:disable=broad-except
                _state_before_sync_recalc = None
            _pending_changes_before_sync = set()
            return
        if am_config.recalc_after_sync:
            print(
                f"PrioritySieve: running full post-sync recalc (state snapshot failed: {error})"
            )
            recalc_main.set_followup_sync_callback(_schedule_followup_sync)
            recalc_main.recalc()
            try:
                cached = extra_settings.get_recalc_collection_state()
                if cached:
                    parsed = json.loads(cached)
                    if isinstance(parsed, dict):
                        _state_before_sync_recalc = parsed
                    else:
                        _state_before_sync_recalc = None
                else:
                    _state_before_sync_recalc = None
            except Exception:  # pylint:disable=broad-except
                _state_before_sync_recalc = None
            _pending_changes_before_sync = set()
            return
        else:
            _state_before_sync_recalc = None
            recalc_main.set_followup_sync_callback(None)
            _pending_changes_before_sync = set()
        return

    post_state_json = json.dumps(post_per_lang_state, sort_keys=True)

    # Get baseline state (per-language dict)
    baseline_per_lang: dict[str, str] = {}
    if _state_before_sync_recalc is not None:
        baseline_per_lang = _state_before_sync_recalc
    else:
        cached = extra_settings.get_recalc_collection_state()
        if cached:
            try:
                parsed = json.loads(cached)
                if isinstance(parsed, dict):
                    baseline_per_lang = parsed
            except json.JSONDecodeError:
                pass

    baseline_state_json = json.dumps(baseline_per_lang, sort_keys=True) if baseline_per_lang else None

    print("PrioritySieve post-sync baseline per-lang state:", baseline_state_json)
    print("PrioritySieve post-sync observed per-lang state:", post_state_json)

    if was_followup_sync:
        print("PrioritySieve: skipping post-sync recalc (follow-up sync)")
        extra_settings.set_recalc_collection_state(post_state_json)
        _state_before_sync_recalc = post_per_lang_state
        recalc_main.set_followup_sync_callback(None)
        _pending_changes_before_sync = set()
        return

    if not am_config.recalc_after_sync:
        extra_settings.set_recalc_collection_state(post_state_json)
        _state_before_sync_recalc = post_per_lang_state
        recalc_main.set_followup_sync_callback(None)
        _pending_changes_before_sync = set()
        return

    # Determine which languages have changes (from sync downloads)
    languages_with_sync_changes: set[str] = set()
    all_lang_names = set(post_per_lang_state.keys()) | set(baseline_per_lang.keys())
    for lang_name in all_lang_names:
        post = post_per_lang_state.get(lang_name)
        baseline = baseline_per_lang.get(lang_name)
        if post != baseline:
            languages_with_sync_changes.add(lang_name)

    # Combine with pending changes from before sync
    languages_needing_recalc = languages_with_sync_changes | pending_language_changes

    print(
        "PrioritySieve post-sync state change:",
        {
            "languages_with_sync_changes": sorted(languages_with_sync_changes),
            "languages_with_pending_changes": sorted(pending_language_changes),
            "languages_needing_recalc": sorted(languages_needing_recalc),
            "recalc_after_sync": am_config.recalc_after_sync,
        },
    )

    if not baseline_per_lang and not pending_language_changes:
        print(
            "PrioritySieve: skipping post-sync recalc (no baseline state available)"
        )
        extra_settings.set_recalc_collection_state(post_state_json)
        _state_before_sync_recalc = post_per_lang_state
        recalc_main.set_followup_sync_callback(None)
        _pending_changes_before_sync = set()
        return

    if not languages_needing_recalc:
        print(
            "PrioritySieve: skipping post-sync recalc (no languages have changes)"
        )
        _state_before_sync_recalc = post_per_lang_state
        recalc_main.set_followup_sync_callback(None)
        _pending_changes_before_sync = set()
        return

    print(
        "PrioritySieve post-sync recalc triggered for languages:",
        sorted(languages_needing_recalc),
    )
    recalc_main.set_followup_sync_callback(_schedule_followup_sync)
    recalc_main.recalc_languages(languages_needing_recalc)

    try:
        updated_state = extra_settings.get_recalc_collection_state()
        if updated_state is None:
            per_lang = recalc_main.compute_per_language_filters_state()
            updated_per_lang = {
                lang_name: json.dumps(state, sort_keys=True)
                for lang_name, state in per_lang.items()
            }
            updated_state = json.dumps(updated_per_lang, sort_keys=True)
    except Exception as error:  # pylint:disable=broad-except
        print(
            f"PrioritySieve: failed to cache post-sync state ({error})"
        )
        updated_state = post_state_json

    try:
        parsed = json.loads(updated_state) if updated_state else {}
        _state_before_sync_recalc = parsed if isinstance(parsed, dict) else post_per_lang_state
    except json.JSONDecodeError:
        _state_before_sync_recalc = post_per_lang_state
    _pending_changes_before_sync = set()
    print(
        "PrioritySieve post-sync baseline stored state:",
        json.dumps(_state_before_sync_recalc, sort_keys=True) if _state_before_sync_recalc else None,
    )


def maybe_show_version_warning_wrapper() -> None:
    assert mw is not None
    assert mw.pm is not None

    if mw.pm.auto_syncing_enabled():
        # we wait for sync to finish before we display
        # our warning dialog to prevent gui race conditions
        gui_hooks.sync_did_finish.append(maybe_show_version_warning)
    else:
        maybe_show_version_warning()


def maybe_show_version_warning() -> None:
    global _showed_update_warning

    if _showed_update_warning:
        return
    _showed_update_warning = True

    am_extra_settings = PrioritySieveExtraSettings()

    previous_local_am_version: list[str] = am_extra_settings.value(
        extra_settings_keys.General.PRIORITYSIEVE_VERSION,
        defaultValue=ps_globals.__version__,
        type=str,
    ).split(".")

    try:
        if int(previous_local_am_version[0]) < 6:
            _title = "AnkiMoprhs"
            _body = (
                "Some 'Card Handling' settings have been changed, please make"
                " sure they are correct before using recalc."
                "<br><br>"
                "See <a href='https://github.com/mortii/prioritysieve/releases/tag/v6.0.0'>"
                "the v6.0.0 release notes</a> for more info."
            )
            message_box_utils.show_info_box(title=_title, body=_body, parent=mw)
    except ValueError:
        # the extra settings file is broken somehow
        pass


def cleanup_profile_session() -> None:
    PrioritySieveExtraSettings().save_current_prioritysieve_version()


def reset_am_tags() -> None:
    assert mw is not None

    am_config = PrioritySieveConfig()

    title = "Reset Tags?"
    core_tags = [
        am_config.tag_ready,
        am_config.tag_not_ready,
        am_config.tag_suspended_automatically,
    ]
    legacy_tags = sorted(
        {
            *ps_globals.legacy_fresh_tags,
            *ps_globals.legacy_known_automatically_tags,
        }
    )
    combined_items = "".join(f"<li> {tag}" for tag in [*core_tags, *legacy_tags])
    body = (
        'Clicking "Yes" will remove the following tags from all cards:'
        "<ul>"
        + combined_items
    )
    body += "</ul>"
    want_reset = message_box_utils.show_warning_box(title, body, parent=mw)
    if want_reset:
        tags_and_queue_utils.reset_am_tags(parent=mw)


def find_duplicate_non_new_entry_cards() -> None:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    am_config = PrioritySieveConfig()
    suspended_exception_tags = set(
        am_config.get_preprocess_ignore_suspended_unless_tag_list()
    )

    try:
        with EntryDB() as entry_db:
            entry_map = entry_db.get_non_new_card_ids_grouped_by_entry()
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for duplicate entries.")
        return

    duplicates: dict[tuple[str, str], list[int]] = {}

    for entry_key, card_ids in entry_map.items():
        active_ids: list[int] = []
        for card_id in card_ids:
            row = mw.col.db.first(
                """
                SELECT cards.queue, cards.type, notes.tags
                FROM cards
                JOIN notes ON notes.id = cards.nid
                WHERE cards.id = ?
                """,
                card_id,
            )
            if row is None:
                continue
            queue, card_type, note_tags = row
            queue = int(queue)
            card_type = int(card_type)
            if card_type == CARD_TYPE_NEW:
                continue
            if not card_filters.counts_as_unsuspended(
                queue=queue,
                tags_text=note_tags,
                exception_tags=suspended_exception_tags,
            ):
                continue
            active_ids.append(card_id)
        if len(active_ids) >= 2:
            duplicates[entry_key] = active_ids

    if not duplicates:
        tooltip("No duplicate non-new entries found")
        return

    card_ids_to_browse: set[int] = set()
    for ids in duplicates.values():
        card_ids_to_browse.update(ids)

    query = "cid:" + ",".join(str(cid) for cid in sorted(card_ids_to_browse))

    browser_instance = aqt.dialogs.open("Browser", mw)
    assert browser_instance is not None

    browser_utils.browser = browser_instance
    search_edit = browser_instance.form.searchEdit.lineEdit()
    assert search_edit is not None

    search_edit.setText(query)
    browser_instance.onSearchActivated()

    tooltip(
        f"Found {len(duplicates)} duplicate entry group(s); opened Browser with {len(card_ids_to_browse)} card(s)."
    )


@dataclass
class _VariantCard:
    card_id: int
    text: str
    reading: str
    kanji_sequence: str
    due: int


def find_variant_entry_cards() -> None:
    """Show all non-new cards that represent variant spellings of the same word."""

    assert mw is not None
    assert mw.col is not None

    am_config = PrioritySieveConfig()
    if not am_config.auto_suspend_variant_spellings:
        tooltip("Enable 'Auto-suspend variant spellings' in Settings first.")
        return

    exception_tags = set(
        am_config.get_preprocess_ignore_suspended_unless_tag_list()
    )

    selections: set[str] = set()
    for config_filter in am_config.filters:
        selections.update(config_filter.priority_files)

    normalized_priority_files = [
        selection
        for selection in selections
        if selection and selection != ps_globals.NONE_OPTION
    ]

    priority_map = (
        load_priority_map(normalized_priority_files)
        if normalized_priority_files
        else {}
    )

    try:
        with EntryDB() as entry_db:
            cards = entry_db.get_cards()
            entry_cache = entry_db.get_card_entry_cache()
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for variant spellings.")
        return

    reading_groups: dict[str, list[_VariantCard]] = {}

    for stored_card in cards:
        if stored_card.card_type == CARD_TYPE_NEW:
            continue

        entry = entry_cache.get(stored_card.card_id)
        if entry is None:
            continue

        if not card_filters.counts_as_unsuspended(
            queue=stored_card.card_queue,
            tags_text=stored_card.tags,
            exception_tags=exception_tags,
        ):
            continue

        reading = (entry.reading or "").strip()
        if not reading:
            continue

        text = entry.text or ""
        due_value = _entry_priority_due(text, reading, priority_map)
        variant = _VariantCard(
            card_id=stored_card.card_id,
            text=text,
            reading=reading,
            kanji_sequence=extract_kanji_sequence(text),
            due=due_value,
        )
        reading_groups.setdefault(reading, []).append(variant)

    merge_kana_variants = am_config.merge_kana_variant_spellings
    variant_card_ids = _collect_variant_card_ids(
        reading_groups,
        merge_kana_variants=merge_kana_variants,
    )
    if not variant_card_ids:
        tooltip("No variant spellings found among non-new cards.")
        return

    query = "cid:" + ",".join(str(card_id) for card_id in sorted(variant_card_ids))

    browser_instance = aqt.dialogs.open("Browser", mw)
    assert browser_instance is not None

    browser_utils.browser = browser_instance
    search_edit = browser_instance.form.searchEdit.lineEdit()
    assert search_edit is not None

    search_edit.setText(query)
    browser_instance.onSearchActivated()

    tooltip(
        f"Found {len(variant_card_ids)} card(s) with variant spellings; opened Browser."
    )


def _collect_variant_card_ids(
    reading_groups: dict[str, list[_VariantCard]],
    *,
    merge_kana_variants: bool = False,
) -> set[int]:
    variant_card_ids: set[int] = set()

    for variants in reading_groups.values():
        count = len(variants)
        if count < 2:
            continue

        parent = list(range(count))

        def _find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def _union(left: int, right: int) -> None:
            root_left = _find(left)
            root_right = _find(right)
            if root_left == root_right:
                return
            parent[root_right] = root_left

        non_empty_indices = [
            idx for idx, variant in enumerate(variants) if variant.kanji_sequence
        ]
        empty_indices = [
            idx for idx, variant in enumerate(variants) if not variant.kanji_sequence
        ]

        for i in non_empty_indices:
            for j in non_empty_indices:
                if i >= j:
                    continue

                if _should_link_non_empty_variants(variants[i], variants[j]):
                    _union(i, j)

        components: dict[int, list[int]] = {}
        assigned_indices: set[int] = set()

        for idx in non_empty_indices:
            root = _find(idx)
            components.setdefault(root, []).append(idx)
            if merge_kana_variants:
                assigned_indices.add(idx)

        for idx in empty_indices:
            candidate_idx = _select_best_matching_variant(idx, variants, non_empty_indices)
            if candidate_idx is None:
                continue
            root = _find(candidate_idx)
            components.setdefault(root, []).append(idx)
            if merge_kana_variants:
                assigned_indices.add(idx)

        pure_kana_components: list[list[int]] = []
        if merge_kana_variants:
            remaining_empty_indices = [
                idx for idx in empty_indices if idx not in assigned_indices
            ]
            if remaining_empty_indices:
                normalized_groups: dict[str, list[int]] = {}
                script_presence: dict[str, set[str]] = {}

                for idx in remaining_empty_indices:
                    variant = variants[idx]
                    text = (variant.text or "").strip()
                    if not text:
                        continue

                    normalized_text = normalize_reading(text)
                    if not normalized_text:
                        continue

                    has_hiragana = contains_hiragana(text)
                    has_katakana = contains_katakana(text)
                    if not (has_hiragana or has_katakana):
                        continue

                    normalized_groups.setdefault(normalized_text, []).append(idx)
                    scripts = script_presence.setdefault(normalized_text, set())
                    if has_hiragana:
                        scripts.add("hiragana")
                    if has_katakana:
                        scripts.add("katakana")

                for normalized_text, indices in normalized_groups.items():
                    if len(indices) < 2:
                        continue
                    scripts = script_presence.get(normalized_text)
                    if not scripts or "hiragana" not in scripts or "katakana" not in scripts:
                        continue
                    pure_kana_components.append(indices)

        all_components = list(components.values()) + pure_kana_components

        for indices in all_components:
            if len(indices) < 2:
                continue
            component_variants = [variants[idx] for idx in indices]
            canonical = _select_primary_variant(component_variants)
            skipped_primary = False
            for variant in component_variants:
                if not skipped_primary and variant.card_id == canonical.card_id:
                    skipped_primary = True
                    continue
                variant_card_ids.add(variant.card_id)

    return variant_card_ids


def _select_primary_variant(variants: list[_VariantCard]) -> _VariantCard:
    best_variant = variants[0]
    best_score = _variant_score(best_variant)

    for variant in variants[1:]:
        score = _variant_score(variant)
        if score > best_score:
            best_variant = variant
            best_score = score

    return best_variant


def _variant_score(variant: _VariantCard) -> tuple[int, int, int, int]:
    kanji_len = len(variant.kanji_sequence)
    due_score = -variant.due
    text_len = -len(variant.text)
    card_id_score = -variant.card_id
    return (kanji_len, due_score, text_len, card_id_score)


def _should_link_non_empty_variants(left: _VariantCard, right: _VariantCard) -> bool:
    seq_left = left.kanji_sequence
    seq_right = right.kanji_sequence
    has_kana = contains_kana(left.text) or contains_kana(right.text)

    if not has_kana:
        return False

    if seq_left == seq_right:
        return True

    return _has_strict_subsequence_relation(seq_left, seq_right)


def _select_best_matching_variant(
    empty_idx: int,
    variants: list[_VariantCard],
    non_empty_indices: list[int],
) -> int | None:
    best_idx: int | None = None
    best_score: tuple[int, int, int, int] | None = None
    empty_variant = variants[empty_idx]

    for idx in non_empty_indices:
        candidate = variants[idx]
        if not _are_variant_spellings(empty_variant, candidate):
            continue
        score = _variant_score(candidate)
        if best_score is None or score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def _has_strict_subsequence_relation(seq_a: str, seq_b: str) -> bool:
    if seq_a == seq_b:
        return False
    return is_kanji_subsequence(seq_a, seq_b) or is_kanji_subsequence(seq_b, seq_a)


def _entry_priority_due(
    text: str,
    reading: str,
    priority_map: dict[tuple[str, str], int],
) -> int:
    normalized_reading = normalize_reading(reading.strip()) if reading else ""
    key_exact = (text, normalized_reading)
    priority = priority_map.get(key_exact)
    if priority is not None:
        return priority
    if normalized_reading:
        fallback_priority = priority_map.get((text, ""))
        if fallback_priority is not None:
            return fallback_priority
    return ps_globals.DEFAULT_REVIEW_DUE


def _are_variant_spellings(left: _VariantCard, right: _VariantCard) -> bool:
    if not (contains_kana(left.text) or contains_kana(right.text)):
        return False

    seq_left = left.kanji_sequence
    seq_right = right.kanji_sequence

    if seq_left == seq_right:
        return left.text != right.text

    return is_kanji_subsequence(seq_left, seq_right) or is_kanji_subsequence(
        seq_right,
        seq_left,
    )


def _merge_suspended_entry_cards(
    entry_card_map: dict[tuple[str, str], list[int]],
    am_config: PrioritySieveConfig,
) -> None:
    suspended_cards_by_entry = _load_suspended_entry_cards(am_config)
    if not suspended_cards_by_entry:
        return

    for entry_key, card_ids in suspended_cards_by_entry.items():
        existing = entry_card_map.setdefault(entry_key, [])
        existing_set = set(existing)
        for card_id in card_ids:
            normalized = int(card_id)
            if normalized not in existing_set:
                existing.append(normalized)
                existing_set.add(normalized)


def _load_suspended_entry_cards(
    am_config: PrioritySieveConfig,
) -> dict[tuple[str, str], list[int]]:
    assert mw is not None
    assert mw.col is not None

    cards_by_entry: dict[tuple[str, str], list[int]] = {}
    tag_manager = TagManager(mw.col)
    model_manager = mw.col.models

    for config_filter in am_config.filters:
        note_type_id = model_manager.id_for_name(config_filter.note_type)
        if note_type_id is None:
            continue

        note_type_dict = model_manager.get(note_type_id)
        if note_type_dict is None:
            continue

        existing_field_names = model_manager.field_names(note_type_dict)
        if config_filter.field not in existing_field_names:
            continue

        expression_field_index = existing_field_names.index(config_filter.field)

        if (
            config_filter.furigana_field != ps_globals.NONE_OPTION
            and config_filter.furigana_field in existing_field_names
        ):
            furigana_field_index: int | None = existing_field_names.index(
                config_filter.furigana_field
            )
        else:
            furigana_field_index = None

        if (
            config_filter.reading_field != ps_globals.NONE_OPTION
            and config_filter.reading_field in existing_field_names
        ):
            reading_field_index: int | None = existing_field_names.index(
                config_filter.reading_field
            )
        else:
            reading_field_index = None

        if (
            config_filter.extra_reading_field
            and ps_globals.EXTRA_FIELD_READING in existing_field_names
        ):
            extra_reading_field_index: int | None = existing_field_names.index(
                ps_globals.EXTRA_FIELD_READING
            )
        else:
            extra_reading_field_index = None

        tags_object = config_filter.tags
        excluded_tags = tags_object["exclude"]
        included_tags = tags_object["include"]
        tags_search_string = ""

        if excluded_tags:
            tags_search_string += "".join(
                f" AND notes.tags NOT LIKE '% {tag} %'" for tag in excluded_tags
            )
        if included_tags:
            tags_search_string += "".join(
                f" AND notes.tags LIKE '% {tag} %'" for tag in included_tags
            )

        suspended_rows = mw.col.db.all(
            """
            SELECT
                cards.id,
                cards.ivl,
                cards.type,
                cards.queue,
                cards.due,
                cards.did,
                COALESCE(cards.odid, 0),
                notes.id,
                notes.flds,
                notes.tags
            FROM cards
            INNER JOIN notes ON cards.nid = notes.id
            WHERE notes.mid = ?
              AND cards.queue = ?
            """
            + tags_search_string,
            note_type_id,
            QUEUE_TYPE_SUSPENDED,
        )

        if not suspended_rows:
            continue

        for row in suspended_rows:
            row_data = AnkiDBRowData(row)

            card_data = AnkiCardData(
                am_config=am_config,
                tag_manager=tag_manager,
                note_type_id=note_type_id,
                expression_field_index=expression_field_index,
                furigana_field_index=furigana_field_index,
                reading_field_index=reading_field_index,
                extra_reading_field_index=extra_reading_field_index,
                anki_row_data=row_data,
            )

            entry = _build_entry(am_config, config_filter, card_data)
            cards_by_entry.setdefault(entry.key(), []).append(row_data.card_id)

    return cards_by_entry


def show_suspended_only_entry_cards() -> None:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    am_config = PrioritySieveConfig()
    suspended_exception_tags = set(
        am_config.get_preprocess_ignore_suspended_unless_tag_list()
    )
    auto_suspend_tag = am_config.tag_suspended_automatically

    selections: set[str] = set()
    for config_filter in am_config.filters:
        selections.update(config_filter.priority_files)

    normalized_selections = [
        selection
        for selection in selections
        if selection and selection != ps_globals.NONE_OPTION
    ]

    if not normalized_selections:
        tooltip("No priority lists configured in PrioritySieve settings.")
        return

    try:
        with EntryDB() as entry_db:
            entry_card_map = entry_db.get_card_ids_grouped_by_entry()
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for manually suspended entries.")
        return

    _merge_suspended_entry_cards(entry_card_map, am_config)

    if not entry_card_map:
        tooltip("No cached entries found. Run Recalc first.")
        return

    all_card_ids: set[int] = set()
    for card_ids in entry_card_map.values():
        all_card_ids.update(int(card_id) for card_id in card_ids)

    if not all_card_ids:
        tooltip("No cached entries found. Run Recalc first.")
        return

    card_status_lookup = _load_card_status_lookup(all_card_ids)
    card_status_with_type = _load_card_status_lookup_with_type(all_card_ids)

    priority_map = load_priority_map(normalized_selections)

    suspended_cards_by_entry = card_filters.find_suspended_only_entry_card_ids(
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags=suspended_exception_tags,
        auto_suspend_tag=auto_suspend_tag,
    )

    def _is_priority_entry(entry_key: tuple[str, str]) -> bool:
        text, reading = entry_key
        normalized_reading = normalize_reading(reading)
        key_exact = (text, normalized_reading)
        if key_exact in priority_map:
            return True
        if normalized_reading:
            key_fallback = (text, "")
            if key_fallback in priority_map:
                return True
        return False

    suspended_cards_by_entry = {
        key: ids
        for key, ids in suspended_cards_by_entry.items()
        if _is_priority_entry(key)
    }

    suspended_cards_by_entry = card_filters.filter_variant_shadowed_entries(
        suspended_cards_by_entry=suspended_cards_by_entry,
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_with_type,
        exception_tags=suspended_exception_tags,
        merge_kana_variants=am_config.merge_kana_variant_spellings,
        auto_suspend_variants=am_config.auto_suspend_variant_spellings,
        am_config=am_config,
    )

    if not suspended_cards_by_entry:
        tooltip("No manually suspended entries found in the configured priority lists.")
        return

    card_ids_to_browse: set[int] = set()
    for ids in suspended_cards_by_entry.values():
        card_ids_to_browse.update(ids)

    query = "cid:" + ",".join(str(cid) for cid in sorted(card_ids_to_browse))

    browser_instance = aqt.dialogs.open("Browser", mw)
    assert browser_instance is not None

    browser_utils.browser = browser_instance
    search_edit = browser_instance.form.searchEdit.lineEdit()
    assert search_edit is not None

    search_edit.setText(query)
    browser_instance.onSearchActivated()

    tooltip(
        f"Found {len(suspended_cards_by_entry)} manually suspended entr{'y' if len(suspended_cards_by_entry) == 1 else 'ies'}; opened Browser with {len(card_ids_to_browse)} card(s)."
    )

def _load_card_status_lookup(card_ids: Iterable[int]) -> dict[int, tuple[int, str]]:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    unique_ids: list[int] = []
    seen: set[int] = set()
    for card_id in card_ids:
        normalized = int(card_id)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_ids.append(normalized)

    if not unique_ids:
        return {}

    lookup: dict[int, tuple[int, str]] = {}
    chunk_size = 900
    for start in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[start : start + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        if not placeholders:
            continue
        chunk_args = [int(card_id) for card_id in chunk]
        rows = mw.col.db.all(
            f"""
            SELECT cards.id, cards.queue, notes.tags
            FROM cards
            JOIN notes ON notes.id = cards.nid
            WHERE cards.id IN ({placeholders})
            """,
            *chunk_args,
        )
        for card_id, queue, note_tags in rows:
            text = note_tags if isinstance(note_tags, str) else ""
            lookup[int(card_id)] = (int(queue), text)
    return lookup


def _load_card_status_lookup_with_type(
    card_ids: Iterable[int],
) -> dict[int, tuple[int, str, int]]:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    unique_ids: list[int] = []
    seen: set[int] = set()
    for card_id in card_ids:
        normalized = int(card_id)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_ids.append(normalized)

    if not unique_ids:
        return {}

    lookup: dict[int, tuple[int, str, int]] = {}
    chunk_size = 900
    for start in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[start : start + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        if not placeholders:
            continue
        chunk_args = [int(card_id) for card_id in chunk]
        rows = mw.col.db.all(
            f"""
            SELECT cards.id, cards.queue, cards.type, notes.tags
            FROM cards
            JOIN notes ON notes.id = cards.nid
            WHERE cards.id IN ({placeholders})
            """,
            *chunk_args,
        )
        for card_id, queue, card_type, note_tags in rows:
            text = note_tags if isinstance(note_tags, str) else ""
            lookup[int(card_id)] = (int(queue), text, int(card_type))
    return lookup


def show_missing_priority_cards() -> None:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    range_dialog = PriorityRangeDialog(parent=mw)
    if range_dialog.exec() != 1:
        return

    min_priority, max_priority = range_dialog.get_range()

    am_config = PrioritySieveConfig()
    suspended_exception_tags = set(
        am_config.get_preprocess_ignore_suspended_unless_tag_list()
    )

    selections: set[str] = set()
    for config_filter in am_config.filters:
        selections.update(config_filter.priority_files)

    normalized_selections = [
        selection
        for selection in selections
        if selection and selection != ps_globals.NONE_OPTION
    ]

    if not normalized_selections:
        tooltip("No priority lists configured in PrioritySieve settings.")
        return

    try:
        with EntryDB() as entry_db:
            stored_entries = entry_db.get_entries()
            entry_card_map = entry_db.get_card_ids_grouped_by_entry()
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for missing priority cards.")
        return

    entry_lookup = {
        (stored.text, stored.reading): stored.to_entry()
        for stored in stored_entries
    }
    all_card_ids: set[int] = set()
    for card_ids in entry_card_map.values():
        all_card_ids.update(int(card_id) for card_id in card_ids)

    card_status_lookup = _load_card_status_lookup(all_card_ids)
    active_entry_keys = card_filters.entry_keys_with_active_cards(
        entry_card_map=entry_card_map,
        card_status_lookup=card_status_lookup,
        exception_tags=suspended_exception_tags,
    )
    entries = [
        entry_lookup[key]
        for key in sorted(active_entry_keys)
        if key in entry_lookup
    ]
    missing_entries = priority_gap_utils.find_missing_priority_entries(
        entries=entries,
        priority_files=normalized_selections,
    )

    if not missing_entries:
        tooltip("Every configured priority entry already has a corresponding card.")
        return

    filtered_entries = [
        entry
        for entry in missing_entries
        if min_priority <= entry[2] <= max_priority
    ]

    if not filtered_entries:
        tooltip(
            f"No missing priority entries between {min_priority} and {max_priority}."
        )
        return

    dialog = MissingPriorityEntriesDialog(
        parent=mw,
        entries=filtered_entries,
        total_missing=len(missing_entries),
        priority_range=(min_priority, max_priority),
    )
    dialog.exec()


class MissingPriorityEntriesDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        entries: list[tuple[str, str, int]],
        total_missing: int,
        priority_range: tuple[int, int],
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Missing Priority Cards")
        self.resize(520, 460)

        layout = QVBoxLayout(self)

        min_priority, max_priority = priority_range
        summary = QLabel(
            (
                f"Showing {len(entries)} missing priority entries with priority between {min_priority} and {max_priority}."
                f"<br/>Total missing entries: {total_missing}."
            )
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        entries_view = QPlainTextEdit(self)
        entries_view.setReadOnly(True)
        entries_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        entries_view.setPlainText(self._format_entries(entries))
        layout.addWidget(entries_view)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        close_button = button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setDefault(True)
        layout.addWidget(button_box)

    @staticmethod
    def _format_entries(entries: list[tuple[str, str, int]]) -> str:
        lines: list[str] = []
        for index, (entry_text, reading, priority) in enumerate(entries, start=1):
            reading_suffix = f" [{reading}]" if reading else ""
            lines.append(f"{index}. {entry_text}{reading_suffix} — priority {priority}")
        return "\n".join(lines)


class PriorityRangeDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        default_min: int = 0,
        default_max: int = 1000,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Missing Priority Cards – Range")
        self.resize(320, 160)

        layout = QVBoxLayout(self)

        instructions = QLabel("Show entries whose computed priority falls within this inclusive range:")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        form_layout = QFormLayout()
        self.min_spin = QSpinBox(self)
        self.min_spin.setMinimum(0)
        self.min_spin.setMaximum(2_147_483_647)
        self.min_spin.setValue(default_min)

        self.max_spin = QSpinBox(self)
        self.max_spin.setMinimum(0)
        self.max_spin.setMaximum(2_147_483_647)
        self.max_spin.setValue(default_max)

        form_layout.addRow("Minimum priority", self.min_spin)
        form_layout.addRow("Maximum priority", self.max_spin)
        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self) -> None:  # type: ignore[override]
        if self.min_spin.value() > self.max_spin.value():
            self.max_spin.setValue(self.min_spin.value())
        super().accept()

    def get_range(self) -> tuple[int, int]:
        return self.min_spin.value(), self.max_spin.value()


def find_entries_missing_priority_lists() -> None:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    am_config = PrioritySieveConfig()
    selections: set[str] = set()
    for config_filter in am_config.filters:
        selections.update(config_filter.priority_files)

    normalized_selections = [
        selection
        for selection in selections
        if selection and selection != ps_globals.NONE_OPTION
    ]

    try:
        with EntryDB() as entry_db:
            entry_map = entry_db.get_non_new_card_ids_grouped_by_entry()
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for missing priorities.")
        return

    priority_map = (
        load_priority_map(normalized_selections) if normalized_selections else {}
    )

    if not entry_map:
        tooltip("No cached entries found. Run Recalc first.")
        return

    all_card_ids: set[int] = set()
    for card_ids in entry_map.values():
        all_card_ids.update(card_ids)

    if not all_card_ids:
        tooltip("No cached entries found. Run Recalc first.")
        return

    cards_query = ids2str(sorted(all_card_ids))
    card_rows = mw.col.db.all(
        f"SELECT id, queue, type FROM cards WHERE id IN {cards_query}"
    )
    card_status_map = {card_id: (queue, card_type) for card_id, queue, card_type in card_rows}

    missing_entries: dict[tuple[str, str], list[int]] = {}

    priority_keys = {
        (text, normalize_reading(reading))
        for text, reading in priority_map.keys()
    }

    for entry_key, card_ids in entry_map.items():
        active_cards: list[int] = []
        for card_id in card_ids:
            status = card_status_map.get(card_id)
            if status is None:
                continue
            queue, card_type = status
            if queue == -1 or card_type == 0:
                continue
            active_cards.append(card_id)

        if not active_cards:
            continue

        text, reading = entry_key
        normalized_reading = normalize_reading(reading)
        key_exact = (text, normalized_reading)
        has_priority = key_exact in priority_keys

        if not normalized_reading:
            key_fallback = (text, "")
            has_priority = has_priority or key_fallback in priority_keys

        if has_priority:
            continue

        missing_entries[entry_key] = active_cards

    if not missing_entries:
        tooltip("All active entries are present in your configured priority lists.")
        return

    card_ids_to_browse: set[int] = set()
    for ids in missing_entries.values():
        card_ids_to_browse.update(ids)

    query = "cid:" + ",".join(str(cid) for cid in sorted(card_ids_to_browse))

    browser_instance = aqt.dialogs.open("Browser", mw)
    assert browser_instance is not None

    browser_utils.browser = browser_instance
    search_edit = browser_instance.form.searchEdit.lineEdit()
    assert search_edit is not None

    search_edit.setText(query)
    browser_instance.onSearchActivated()

    tooltip(
        f"Found {len(missing_entries)} entry group(s) missing priorities; opened Browser with {len(card_ids_to_browse)} card(s)."
    )



def create_am_tool_menu() -> QMenu:
    assert mw is not None
    am_tool_menu = QMenu("PrioritySieve", mw)
    am_tool_menu_creation_action = mw.form.menuTools.addMenu(am_tool_menu)
    assert am_tool_menu_creation_action is not None
    am_tool_menu_creation_action.setObjectName(_TOOL_MENU)
    return am_tool_menu


def create_recalc_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Recalc", mw)
    action.setShortcut(am_config.shortcut_recalc)
    action.triggered.connect(recalc_main.recalc)
    return action


def open_language_selector() -> None:
    """Open the language selector dialog."""

    def on_language_selected(lang_name: str) -> None:
        # Open settings dialog for the selected language
        # We use a custom dialog instead of Anki's dialog manager
        # to pass the language name
        dialog = SettingsDialog(language_name=lang_name)
        dialog.show()

    selector = LanguageSelectorDialog(on_language_selected=on_language_selected)
    selector.exec()


def create_settings_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Settings", mw)
    action.setShortcut(am_config.shortcut_settings)
    action.triggered.connect(open_language_selector)
    return action


def create_duplicate_entries_action() -> QAction:
    action = QAction("&Find Duplicate Entry Cards", mw)
    action.triggered.connect(find_duplicate_non_new_entry_cards)
    return action


def create_variant_entries_action() -> QAction:
    action = QAction("&Show Variant Entry Cards", mw)
    action.triggered.connect(find_variant_entry_cards)
    return action


def create_suspended_only_entries_action() -> QAction:
    action = QAction("&Show Suspended-Only Entries", mw)
    action.triggered.connect(show_suspended_only_entry_cards)
    return action


def create_missing_priority_cards_action() -> QAction:
    action = QAction("&Show Missing Priority Cards", mw)
    action.triggered.connect(show_missing_priority_cards)
    return action



def create_missing_priority_entries_action() -> QAction:
    action = QAction("&Find Entries Missing Priorities", mw)
    action.triggered.connect(find_entries_missing_priority_lists)
    return action


def create_tag_reset_action() -> QAction:
    action = QAction("&Reset Tags", mw)
    action.triggered.connect(reset_am_tags)
    return action


def create_guide_action() -> QAction:
    desktop_service = QDesktopServices()
    action = QAction("&Guide (web)", mw)
    action.triggered.connect(
        lambda: desktop_service.openUrl(
            QUrl("https://mortii.github.io/prioritysieve/user_guide/intro.html")
        )
    )
    return action


def create_changelog_action() -> QAction:
    desktop_service = QDesktopServices()
    action = QAction("&Changelog (web)", mw)
    action.triggered.connect(
        lambda: desktop_service.openUrl(
            QUrl("https://github.com/mortii/prioritysieve/releases")
        )
    )
    return action


def create_learn_now_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Learn Card Now", mw)
    action.setShortcut(am_config.shortcut_learn_now)
    action.triggered.connect(browser_utils.run_learn_card_now)
    return action


def create_browse_same_entry_action() -> QAction:
    action = QAction("&Browse Same Entries", mw)
    action.triggered.connect(browser_utils.run_browse_entry)
    return action


def create_browse_same_entry_unknowns_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Browse Same Unknown Entries", mw)
    action.setShortcut(am_config.shortcut_browse_same_unknown)
    action.triggered.connect(
        partial(browser_utils.run_browse_entry, search_unknowns=True)
    )
    return action


def create_browse_same_entry_unknowns_broad_action(
    am_config: PrioritySieveConfig,
) -> QAction:
    action = QAction("&Browse Same Unknown Entries (broad match)", mw)
    action.setShortcut(am_config.shortcut_browse_same_unknown_broad)
    action.triggered.connect(
        partial(
            browser_utils.run_browse_entry, search_unknowns=True, match_text_only=True
        )
    )
    return action



def create_already_known_tagger_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Tag As Known", mw)
    action.setShortcut(am_config.shortcut_set_known_and_skip)
    action.triggered.connect(browser_utils.run_already_known_tagger)
    return action


def add_text_as_name_action(web_view: AnkiWebView, menu: QMenu) -> None:
    assert mw is not None
    selected_text = web_view.selectedText()
    if selected_text == "":
        return
    action = QAction("Add selection to names.txt", menu)
    action.triggered.connect(lambda: name_file_utils.add_name_to_file(selected_text))
    menu.addAction(action)





def create_generators_dialog_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Generators", mw)
    action.setShortcut(am_config.shortcut_generators)
    action.triggered.connect(
        partial(
            aqt.dialogs.open,
            name=ps_globals.GENERATOR_DIALOG_NAME,
        )
    )
    return action


def create_progression_dialog_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Progression", mw)
    action.setShortcut(am_config.shortcut_progression)
    action.triggered.connect(
        partial(
            aqt.dialogs.open,
            name=ps_globals.PROGRESSION_DIALOG_NAME,
        )
    )
    return action


def create_known_entries_exporter_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Known Entries Exporter", mw)
    action.setShortcut(am_config.shortcut_known_entries_exporter)
    action.triggered.connect(
        partial(
            aqt.dialogs.open,
            name=ps_globals.KNOWN_ENTRIES_EXPORTER_DIALOG_NAME,
        )
    )
    return action


def create_test_action() -> QAction:
    keys = QKeySequence("Ctrl+T")
    action = QAction("&Test", mw)
    action.setShortcut(keys)
    action.triggered.connect(test_function)
    return action


def test_function() -> None:
    # To activate this dev function in Anki:
    # 1. In prioritysieve_globals.py set 'DEV_MODE = True'
    # 2. Use Ctrl+T, or go to: Tools -> PrioritySieve -> Test

    assert mw is not None
    assert mw.col.db is not None

    # print(f"card: {Card}")
    # mid: NotetypeId = card.note().mid
    #
    # model_manager = mw.col.models
    # note_type_dict: Optional[NotetypeDict] = model_manager.get(mid)
    # assert note_type_dict is not None
    # new_field: FieldDict = model_manager.new_field("am-unknowns")
    #
    # model_manager.add_field(note_type_dict, new_field)
    # model_manager.update_dict(note_type_dict)

    # mw.col.update_note(note)

    # card_id = 1720345836169
    # card = mw.col.get_card(card_id)
    # card.ivl += 30
    # mw.col.update_card(card)


main()
stats_graph.init_stats_graph()
