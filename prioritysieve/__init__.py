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
from functools import partial
from pathlib import Path
from typing import Literal

import aqt
from anki import hooks
from anki.cards import Card
from anki.collection import OpChangesAfterUndo
from anki.utils import ids2str
from aqt import gui_hooks, mw
from aqt.browser.browser import Browser
from aqt.overview import Overview
from aqt.qt import (  # pylint:disable=no-name-in-module
    QAction,
    QDesktopServices,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QKeySequence,
    QMenu,
    QPlainTextEdit,
    QWidget,
    QUrl,
    QVBoxLayout,
)
from aqt.reviewer import Reviewer
from aqt.toolbar import Toolbar
from aqt.utils import tooltip
from aqt.webview import AnkiWebView

from . import (
    prioritysieve_config,
)
from . import prioritysieve_globals as ps_globals
from . import (
    browser_utils,
    debug_utils,
    message_box_utils,
    priority_gap_utils,
    morph_priority_utils,
    name_file_utils,
    reviewing_utils,
    tags_and_queue_utils,
    text_preprocessing,
    toolbar_stats,
)
from .prioritysieve_config import PrioritySieveConfig, PrioritySieveConfigFilter
from .prioritysieve_db import PrioritySieveDB
from .extra_settings import prioritysieve_extra_settings, extra_settings_keys
from .extra_settings.prioritysieve_extra_settings import PrioritySieveExtraSettings
from .generators.generators_window import GeneratorWindow
from .highlighting.highlight_just_in_time import highlight_morphs_jit
from .known_morphs_exporter import KnownMorphsExporterDialog
from .morphemizers import spacy_wrapper
from .progression.progression_window import ProgressionWindow
from .reading_utils import normalize_reading
from .recalc import recalc_main
from .settings import settings_dialog
from .settings.settings_dialog import SettingsDialog
from .tag_selection_dialog import TagSelectionDialog
from .toolbar_stats import MorphToolbarStats

_TOOL_MENU: str = "ps_tool_menu"
_BROWSE_MENU: str = "ps_browse_menu"
_CONTEXT_MENU: str = "ps_context_menu"

_startup_sync: bool = True
_showed_update_warning: bool = False
_updated_seen_morphs_for_profile: bool = False
_state_before_sync_recalc: str | None = None


def _schedule_followup_sync() -> None:
    assert mw is not None
    print("PrioritySieve: running follow-up sync after auto recalc")
    mw.onSync()


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
    gui_hooks.profile_did_open.append(replace_card_reviewer)
    gui_hooks.profile_did_open.append(text_preprocessing.update_translation_table)
    gui_hooks.profile_did_open.append(spacy_wrapper.maybe_delete_spacy_venv)
    gui_hooks.profile_did_open.append(maybe_show_version_warning_wrapper)

    gui_hooks.sync_will_start.append(recalc_on_sync)
    gui_hooks.sync_did_finish.append(recalc_after_sync)

    hooks.field_filter.append(highlight_morphs_jit)

    gui_hooks.webview_will_show_context_menu.append(add_text_as_name_action)

    gui_hooks.overview_did_refresh.append(update_seen_morphs)

    gui_hooks.reviewer_did_answer_card.append(insert_seen_morphs)

    gui_hooks.state_did_undo.append(rebuild_seen_morphs)

    gui_hooks.profile_will_close.append(cleanup_profile_session)


def init_toolbar_items(links: list[str], toolbar: Toolbar) -> None:
    # Adds the 'L: V:' and 'Recalc' to the toolbar

    morph_toolbar_stats = MorphToolbarStats()
    am_config = PrioritySieveConfig()

    known_entries_tooltip_message = (
        "L = Known entry base forms<br>V = Known entry variants"
    )

    if am_config.hide_recalc_toolbar is False:
        links.append(
            toolbar.create_link(
                cmd="recalc_toolbar",
                label="Recalc",
                func=recalc_main.recalc,
                tip=f"Shortcut: {am_config.shortcut_recalc.toString()}",
                id="recalc_toolbar",
            )
        )

    if am_config.hide_lemma_toolbar is False:
        links.append(
            toolbar.create_link(
                cmd="known_lemmas",
                label=morph_toolbar_stats.lemmas,
                func=lambda: tooltip(known_entries_tooltip_message),
                tip="L = Known entry base forms",
                id="known_lemmas",
            )
        )

    if am_config.hide_inflection_toolbar is False:
        links.append(
            toolbar.create_link(
                cmd="known_variants",
                label=morph_toolbar_stats.variants,
                func=lambda: tooltip(known_entries_tooltip_message),
                tip="V = Known entry variants",
                id="known_variants",
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
    with PrioritySieveDB() as am_db:
        am_db.create_all_tables()


def create_am_directories_and_files() -> None:
    assert mw is not None

    names_file_path: Path = Path(mw.pm.profileFolder(), ps_globals.NAMES_TXT_FILE_NAME)
    known_morphs_dir_path: Path = Path(
        mw.pm.profileFolder(), ps_globals.KNOWN_MORPHS_DIR_NAME
    )
    priority_files_dir_path: Path = Path(
        mw.pm.profileFolder(), ps_globals.PRIORITY_FILES_DIR_NAME
    )

    # Create the file if it doesn't exist
    names_file_path.touch(exist_ok=True)

    if not known_morphs_dir_path.exists():
        Path(known_morphs_dir_path).mkdir()

    if not priority_files_dir_path.exists():
        Path(priority_files_dir_path).mkdir()


def register_addon_dialogs() -> None:
    # We use the Anki dialog manager to handle our dialogs

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
        name=ps_globals.KNOWN_MORPHS_EXPORTER_DIALOG_NAME,
        creator=KnownMorphsExporterDialog,
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
    known_morphs_exporter_action = create_known_morphs_exporter_action(am_config)
    reset_tags_action = create_tag_reset_action()
    duplicate_entries_action = create_duplicate_entries_action()
    missing_priority_cards_action = create_missing_priority_cards_action()
    missing_priority_entries_action = create_missing_priority_entries_action()
    guide_action = create_guide_action()
    changelog_action = create_changelog_action()

    am_tool_menu = create_am_tool_menu()
    am_tool_menu.addAction(settings_action)
    am_tool_menu.addAction(recalc_action)
    am_tool_menu.addAction(generators_action)
    am_tool_menu.addAction(progression_action)
    am_tool_menu.addAction(known_morphs_exporter_action)
    am_tool_menu.addAction(reset_tags_action)
    am_tool_menu.addAction(duplicate_entries_action)
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
    browse_morph_action = create_browse_same_morph_action()
    browse_morph_unknowns_action = create_browse_same_morph_unknowns_action(am_config)
    browse_morph_unknowns_lemma_action = create_browse_same_morph_unknowns_lemma_action(
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
        am_browse_menu.addAction(browse_morph_action)
        am_browse_menu.addAction(browse_morph_unknowns_action)
        am_browse_menu.addAction(browse_morph_unknowns_lemma_action)
        am_browse_menu.addAction(already_known_tagger_action)

    def setup_context_menu(_browser: Browser, context_menu: QMenu) -> None:
        for action in context_menu.actions():
            if action.objectName() == _CONTEXT_MENU:
                return  # prevents duplicate menus on profile-switch

        context_menu_creation_action = context_menu.insertSeparator(learn_now_action)
        assert context_menu_creation_action is not None

        context_menu.addAction(learn_now_action)
        context_menu.addAction(browse_morph_action)
        context_menu.addAction(browse_morph_unknowns_action)
        context_menu.addAction(browse_morph_unknowns_lemma_action)
        context_menu.addAction(already_known_tagger_action)
        context_menu_creation_action.setObjectName(_CONTEXT_MENU)

    gui_hooks.browser_menus_did_init.append(setup_browser_menu)
    gui_hooks.browser_will_show_context_menu.append(setup_context_menu)


def recalc_on_sync() -> None:
    # Anki can sync automatically on startup, but we don't
    # want to recalc at that point.
    global _startup_sync
    global _state_before_sync_recalc

    if mw.pm.auto_syncing_enabled():
        if _startup_sync:
            # trivial bug: this will cause recalc to not run on the first profile close
            # sync after the user first activates the Anki 'auto_syncing_enabled'
            # setting, but that's not a big deal.
            _startup_sync = False
            return

    am_config = PrioritySieveConfig()

    extra_settings = PrioritySieveExtraSettings()

    current_state_json: str | None = None
    try:
        current_state = recalc_main.compute_modify_filters_state()
        current_state_json = json.dumps(current_state, sort_keys=True)
    except Exception as error:  # pylint:disable=broad-except
        print(
            f"PrioritySieve: running pre-sync recalc (state snapshot failed: {error})"
        )
        current_state_json = extra_settings.get_recalc_collection_state()

    recalc_main.set_followup_sync_callback(None)

    print("PrioritySieve pre-sync snapshot state:", current_state_json)
    if not am_config.recalc_on_sync:
        _state_before_sync_recalc = current_state_json
        return

    if current_state_json is not None:
        previous_state = extra_settings.get_recalc_collection_state()
        print("PrioritySieve cached snapshot state:", previous_state)
        if previous_state == current_state_json:
            print(
                "PrioritySieve: skipping pre-sync recalc (collection unchanged)"
            )
            _state_before_sync_recalc = current_state_json
            return

        if previous_state is None:
            reason = "no cached state"
        else:
            reason = "collection metrics changed"
        print(f"PrioritySieve: running pre-sync recalc ({reason})")

    def _cache_post_recalc_state() -> None:
        global _state_before_sync_recalc

        updated_state: str | None = None
        try:
            updated_state = extra_settings.get_recalc_collection_state()
            if updated_state is None:
                updated_state = json.dumps(
                    recalc_main.compute_modify_filters_state(), sort_keys=True
                )
        except Exception as error:  # pylint:disable=broad-except
            print(
                f"PrioritySieve: unable to cache pre-sync state after recalc ({error})"
            )
            updated_state = current_state_json

        _state_before_sync_recalc = updated_state
        print(
            "PrioritySieve pre-sync baseline stored state:",
            _state_before_sync_recalc,
        )

    _state_before_sync_recalc = None
    recalc_main.set_followup_sync_callback(_cache_post_recalc_state)
    recalc_main.recalc()
    return


def recalc_after_sync(success: bool | None = None) -> None:
    global _state_before_sync_recalc

    extra_settings = PrioritySieveExtraSettings()

    recalc_main.set_followup_sync_callback(None)

    if success is False:
        _state_before_sync_recalc = None
        recalc_main.set_followup_sync_callback(None)
        return

    am_config = PrioritySieveConfig()

    try:
        post_state = recalc_main.compute_modify_filters_state()
        post_state_json = json.dumps(post_state, sort_keys=True)
    except Exception as error:  # pylint:disable=broad-except
        if am_config.recalc_after_sync:
            print(
                f"PrioritySieve: running post-sync recalc (state snapshot failed: {error})"
            )
            recalc_main.set_followup_sync_callback(_schedule_followup_sync)
            recalc_main.recalc()
            try:
                _state_before_sync_recalc = (
                    extra_settings.get_recalc_collection_state()
                )
            except Exception:  # pylint:disable=broad-except
                _state_before_sync_recalc = None
            return
        else:
            _state_before_sync_recalc = None
            recalc_main.set_followup_sync_callback(None)
        return

    baseline_state = _state_before_sync_recalc
    if baseline_state is None:
        baseline_state = extra_settings.get_recalc_collection_state()

    print("PrioritySieve post-sync baseline state:", baseline_state)
    print("PrioritySieve post-sync observed state:", post_state_json)

    if not am_config.recalc_after_sync:
        if post_state_json is not None:
            extra_settings.set_recalc_collection_state(post_state_json)
        _state_before_sync_recalc = post_state_json
        recalc_main.set_followup_sync_callback(None)
        return

    if baseline_state is None:
        print(
            "PrioritySieve: skipping post-sync recalc (no baseline state available)"
        )
        if post_state_json is not None:
            extra_settings.set_recalc_collection_state(post_state_json)
        _state_before_sync_recalc = post_state_json
        recalc_main.set_followup_sync_callback(None)
        return

    if baseline_state == post_state_json:
        print(
            "PrioritySieve post-sync skip (baseline == post) state:",
            post_state_json,
        )
        print(
            "PrioritySieve: skipping post-sync recalc (no changes downloaded)"
        )
        _state_before_sync_recalc = post_state_json
        recalc_main.set_followup_sync_callback(None)
        return

    print(
        "PrioritySieve post-sync recalc triggered (baseline != post) state:",
        {
            "baseline": baseline_state,
            "post": post_state_json,
        },
    )
    recalc_main.set_followup_sync_callback(_schedule_followup_sync)
    recalc_main.recalc()

    try:
        updated_state = extra_settings.get_recalc_collection_state()
        if updated_state is None:
            updated_state = json.dumps(
                recalc_main.compute_modify_filters_state(), sort_keys=True
            )
    except Exception as error:  # pylint:disable=broad-except
        print(
            f"PrioritySieve: failed to cache post-sync state ({error})"
        )
        updated_state = post_state_json

    _state_before_sync_recalc = updated_state
    print(
        "PrioritySieve post-sync baseline stored state:",
        _state_before_sync_recalc,
    )


def replace_card_reviewer() -> None:
    assert mw is not None

    reviewing_utils.init_undo_targets()

    mw.reviewer.nextCard = reviewing_utils.am_next_card
    mw.reviewer._shortcutKeys = partial(
        reviewing_utils.am_reviewer_shortcut_keys,
        self=mw.reviewer,
        _old=Reviewer._shortcutKeys,  # type: ignore[arg-type]
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


def insert_seen_morphs(
    _reviewer: Reviewer, card: Card, _ease: Literal[1, 2, 3, 4]
) -> None:
    """
    The '_reviewer' and '_ease' arguments are unused
    """
    with PrioritySieveDB() as am_db:
        am_db.update_seen_morphs_today_single_card(card.id)


def update_seen_morphs(_overview: Overview) -> None:
    """
    The '_overview' argument is unused
    """
    # Overview is NOT the starting screen; it's the screen you see
    # when you click on a deck. This is a good time to run this function,
    # as 'seen morphs' only needs to be known before starting a review.
    # Previously, this function ran on the profile_did_open hook,
    # but that sometimes caused interference with the add-on updater
    # since both occurred simultaneously.

    global _updated_seen_morphs_for_profile

    if _updated_seen_morphs_for_profile:
        return

    has_active_note_filter = False
    read_config_filters: list[PrioritySieveConfigFilter] = (
        prioritysieve_config.get_read_enabled_filters()
    )

    for config_filter in read_config_filters:
        if config_filter.note_type != "":
            has_active_note_filter = True

    if has_active_note_filter:
        PrioritySieveDB.rebuild_seen_morphs_today()

    _updated_seen_morphs_for_profile = True


def rebuild_seen_morphs(_changes: OpChangesAfterUndo) -> None:
    """
    The '_changes' argument is unused
    """

    ################################################################
    #                      TRACKING SEEN MORPHS
    ################################################################
    # We need to keep track of which morphs have been seen today,
    # which gets complicated when a user undos or redos cards.
    #
    # When a card is answered/set known, we insert all the card's
    # morphs into the 'Seen_Morphs'-table. If a morph is already
    # in the table, we just ignore the insert error. This makes
    # it tricky to remove morphs from the table when undo is used
    # because we don't track if the morphs were already in the table
    # or not. To not deal with this removal problem, we just drop
    # the entire table and rebuild it with the morphs of all the
    # studied cards. This is costly, but it only happens on 'undo',
    # which should be a rare occurrence.
    #
    # REDO:
    # Redoing, i.e., undoing an undo (Ctrl+Shift+Z), is almost
    # impossible to distinguish from a regular forward operation.
    # Since this is such a nightmare to deal with (and is hopefully
    # a rare occurrence), this will just be left as unexpected behavior.
    ################################################################
    PrioritySieveDB.rebuild_seen_morphs_today()

    if ps_globals.DEV_MODE:
        with PrioritySieveDB() as am_db:
            print("Seen_Morphs:")
            am_db.print_table("Seen_Morphs")


def cleanup_profile_session() -> None:
    global _updated_seen_morphs_for_profile
    _updated_seen_morphs_for_profile = False
    PrioritySieveDB.drop_seen_morphs_table()
    PrioritySieveExtraSettings().save_current_prioritysieve_version()


def reset_am_tags() -> None:
    assert mw is not None

    am_config = PrioritySieveConfig()

    title = "Reset Tags?"
    body = (
        'Clicking "Yes" will remove the following tags from all cards:'
        "<ul>"
        f"<li> {am_config.tag_known_automatically}"
        f"<li> {am_config.tag_ready}"
        f"<li> {am_config.tag_not_ready}"
        f"<li> {am_config.tag_fresh}"
        "</ul>"
    )
    want_reset = message_box_utils.show_warning_box(title, body, parent=mw)
    if want_reset:
        tags_and_queue_utils.reset_am_tags(parent=mw)


def find_duplicate_non_new_entry_cards() -> None:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    try:
        with PrioritySieveDB() as am_db:
            entry_map = am_db.get_non_new_card_ids_grouped_by_entry()
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for duplicate entries.")
        return

    duplicates: dict[tuple[str, str], list[int]] = {}

    for entry_key, card_ids in entry_map.items():
        active_ids: list[int] = []
        for card_id in card_ids:
            row = mw.col.db.first(
                "SELECT queue, type FROM cards WHERE id = ?", card_id
            )
            if row is None:
                continue
            queue, card_type = row
            if queue == -1:
                continue
            if card_type == 0:
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



def show_missing_priority_cards() -> None:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    am_config = PrioritySieveConfig()

    selections: set[str] = set()
    for config_filter in am_config.filters:
        selections.update(config_filter.morph_priority_selections)

    normalized_selections = [
        selection
        for selection in selections
        if selection and selection != ps_globals.NONE_OPTION
    ]

    if not normalized_selections:
        tooltip("No priority lists configured in PrioritySieve settings.")
        return

    try:
        with PrioritySieveDB() as am_db:
            missing_entries = priority_gap_utils.find_missing_priority_entries(
                am_db=am_db,
                morph_priority_selection=normalized_selections,
            )
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for missing priority cards.")
        return

    if not missing_entries:
        tooltip("Every configured priority entry already has a corresponding card.")
        return

    total_missing = len(missing_entries)
    default_limit = min(100, total_missing)
    max_limit = max(total_missing, 1)

    limit, ok = QInputDialog.getInt(
        mw,
        "Missing Priority Cards",
        f"How many entries should be shown? (1-{max_limit})",
        default_limit,
        1,
        max_limit,
    )
    if not ok:
        return

    entries_to_show = missing_entries[:limit]

    dialog = MissingPriorityEntriesDialog(
        parent=mw,
        entries=entries_to_show,
        total_missing=total_missing,
    )
    dialog.exec()


class MissingPriorityEntriesDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        entries: list[tuple[str, str, int]],
        total_missing: int,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Missing Priority Cards")
        self.resize(520, 460)

        layout = QVBoxLayout(self)

        summary = QLabel(
            f"Showing {len(entries)} of {total_missing} priority entries without matching cards."
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
        for index, (lemma, reading, priority) in enumerate(entries, start=1):
            reading_suffix = f" [{reading}]" if reading else ""
            lines.append(f"{index}. {lemma}{reading_suffix} — priority {priority}")
        return "\n".join(lines)


def find_entries_missing_priority_lists() -> None:
    assert mw is not None
    assert mw.col is not None
    assert mw.col.db is not None

    am_config = PrioritySieveConfig()
    selections: set[str] = set()
    for config_filter in am_config.filters:
        selections.update(config_filter.morph_priority_selections)

    normalized_selections = [
        selection
        for selection in selections
        if selection and selection != ps_globals.NONE_OPTION
    ]

    try:
        with PrioritySieveDB() as am_db:
            entry_map = am_db.get_non_new_card_ids_grouped_by_entry()
            priority_map = (
                morph_priority_utils.get_morph_priority(am_db, normalized_selections)
                if normalized_selections
                else {}
            )
    except sqlite3.OperationalError:
        tooltip("Run Recalc before searching for missing priorities.")
        return

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

    priority_keys = set(priority_map.keys())

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

        lemma, reading = entry_key
        normalized_reading = normalize_reading(reading)
        key_exact = (lemma, lemma, normalized_reading)
        has_priority = key_exact in priority_keys

        if not normalized_reading:
            key_fallback = (lemma, lemma, "")
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


def create_settings_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Settings", mw)
    action.setShortcut(am_config.shortcut_settings)
    action.triggered.connect(
        partial(aqt.dialogs.open, name=ps_globals.SETTINGS_DIALOG_NAME)
    )
    return action


def create_duplicate_entries_action() -> QAction:
    action = QAction("&Find Duplicate Entry Cards", mw)
    action.triggered.connect(find_duplicate_non_new_entry_cards)
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


def create_browse_same_morph_action() -> QAction:
    action = QAction("&Browse Same Entries", mw)
    action.triggered.connect(browser_utils.run_browse_morph)
    return action


def create_browse_same_morph_unknowns_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Browse Same Unknown Entries", mw)
    action.setShortcut(am_config.shortcut_browse_ready_same_unknown)
    action.triggered.connect(
        partial(browser_utils.run_browse_morph, search_unknowns=True)
    )
    return action


def create_browse_same_morph_unknowns_lemma_action(
    am_config: PrioritySieveConfig,
) -> QAction:
    action = QAction("&Browse Same Unknown Entries (broad match)", mw)
    action.setShortcut(am_config.shortcut_browse_ready_same_unknown_lemma)
    action.triggered.connect(
        partial(
            browser_utils.run_browse_morph, search_unknowns=True, search_lemma_only=True
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
    action = QAction("Mark as name", menu)
    action.triggered.connect(lambda: name_file_utils.add_name_to_file(selected_text))
    action.triggered.connect(PrioritySieveDB.insert_names_to_seen_morphs)
    action.triggered.connect(mw.reviewer.bury_current_card)
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


def create_known_morphs_exporter_action(am_config: PrioritySieveConfig) -> QAction:
    action = QAction("&Known Entries Exporter", mw)
    action.setShortcut(am_config.shortcut_known_morphs_exporter)
    action.triggered.connect(
        partial(
            aqt.dialogs.open,
            name=ps_globals.KNOWN_MORPHS_EXPORTER_DIALOG_NAME,
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

    # with PrioritySieveDB() as am_db:
    #     print("Seen_Morphs:")
    #     am_db.print_table("Seen_Morphs")
    #
    #     print("Morphs:")
    #     am_db.print_table("Morphs")

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
