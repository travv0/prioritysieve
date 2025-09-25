from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - imported lazily in tests
    from aqt.package import venv_binary
except ImportError:  # pragma: no cover - falls back during tests
    venv_binary = None  # type: ignore[assignment]

from ..morpheme import Morpheme

SUDACHI_DICTIONARY_VARIANTS = ["small", "core", "full"]

_DICTIONARY_PACKAGE_MAP: dict[str, tuple[str, str]] = {
    "small": ("sudachidict-small", "sudachidict_small"),
    "core": ("sudachidict-core", "sudachidict_core"),
    "full": ("sudachidict-full", "sudachidict_full"),
}

SUPPORTED_SPLIT_MODES = ["A", "B", "C"]

testing_environment: bool = False

_sudachi_dictionary_module: Any | None = None
_sudachi_tokenizer_module: Any | None = None
_modules_imported: bool = False
_path_appended: bool = False
successful_import: bool = False

_tokenizer_cache: dict[tuple[str, str], tuple[Any, Any]] = {}
_last_error: str | None = None

_packages_path_override: Path | None = None

_POS_BLACKLIST = {
    "補助記号",  # punctuation and auxiliary symbols
    "記号",  # symbols
}
_SUB_POS_BLACKLIST = {
    "数詞",  # numeric terms
}


def set_packages_path_override(path: Path | None) -> None:
    global _packages_path_override
    _packages_path_override = path
    invalidate_cache()


def invalidate_cache() -> None:
    global _tokenizer_cache
    global _last_error
    global _sudachi_dictionary_module
    global _sudachi_tokenizer_module
    global _modules_imported
    global successful_import

    _tokenizer_cache = {}
    _last_error = None
    _sudachi_dictionary_module = None
    _sudachi_tokenizer_module = None
    _modules_imported = False
    successful_import = False


def ensure_tokenizer(dict_variant: str | None, split_mode: str) -> bool:
    normalized_variant = _normalize_dict_variant(dict_variant)
    normalized_mode = split_mode.upper()
    signature = (normalized_variant, normalized_mode)

    if signature in _tokenizer_cache:
        return True

    _import_sudachi_modules()

    if _sudachi_dictionary_module is None or _sudachi_tokenizer_module is None:
        if _last_error is None:
            _set_last_error("SudachiPy is not installed")
        return False

    kwargs = _build_dictionary_kwargs(normalized_variant)

    try:
        dictionary_obj = _sudachi_dictionary_module.Dictionary(**kwargs)
        tokenizer_obj = dictionary_obj.create()
    except Exception as error:  # pragma: no cover - defensive guard
        _set_last_error(str(error))
        return False

    split_mode_obj = _resolve_split_mode(normalized_mode)
    _tokenizer_cache[signature] = (tokenizer_obj, split_mode_obj)
    _set_last_error(None)
    return True


def get_morphemes_sudachi(
    expression: str,
    dict_variant: str | None,
    split_mode: str,
) -> list[Morpheme]:
    if not ensure_tokenizer(dict_variant, split_mode):
        return []

    tokenizer, resolved_mode = _tokenizer_cache[
        (_normalize_dict_variant(dict_variant), split_mode.upper())
    ]

    morphs: list[Morpheme] = []

    for sudachi_morph in tokenizer.tokenize(expression, resolved_mode):
        if _should_skip_token(sudachi_morph):
            continue

        pos_info = sudachi_morph.part_of_speech()
        pos = pos_info[0] if pos_info else "*"
        sub_pos = pos_info[1] if len(pos_info) > 1 else "*"

        lemma = sudachi_morph.dictionary_form() or sudachi_morph.surface()
        inflection = sudachi_morph.surface()

        if not lemma or not inflection:
            continue

        morphs.append(
            Morpheme(
                lemma=lemma,
                inflection=inflection,
                part_of_speech=pos,
                sub_part_of_speech=sub_pos,
            )
        )

    return morphs


def get_available_variants() -> list[str]:
    variants = sorted(set(list_installed_dictionary_variants()))
    return variants


def get_supported_split_modes() -> list[str]:
    return SUPPORTED_SPLIT_MODES.copy()


def is_sudachipy_available() -> bool:
    _import_sudachi_modules()
    return _sudachi_dictionary_module is not None and _sudachi_tokenizer_module is not None


def get_last_error() -> str | None:
    return _last_error


def install_sudachipy() -> None:
    _install_packages(["sudachipy"])
    invalidate_cache()


def uninstall_sudachipy() -> None:
    packages_path = _get_packages_path()
    if not packages_path.exists():
        return

    for entry in list(packages_path.iterdir()):
        if entry.name.startswith("sudachipy"):
            _delete_path(entry)

    for variant in SUDACHI_DICTIONARY_VARIANTS:
        remove_dictionary(variant)

    invalidate_cache()


def install_dictionary(variant: str) -> None:
    if variant not in _DICTIONARY_PACKAGE_MAP:
        raise ValueError(f"Unsupported Sudachi dictionary variant: {variant}")

    pip_name, _module_name = _DICTIONARY_PACKAGE_MAP[variant]
    _install_packages([pip_name])
    invalidate_cache()


def remove_dictionary(variant: str) -> None:
    if variant not in _DICTIONARY_PACKAGE_MAP:
        return

    pip_name, module_name = _DICTIONARY_PACKAGE_MAP[variant]
    packages_path = _get_packages_path()
    if not packages_path.exists():
        return

    prefixes = {
        pip_name.replace("-", "_"),
        pip_name,
        module_name,
    }

    for entry in list(packages_path.iterdir()):
        if any(entry.name.startswith(prefix) for prefix in prefixes):
            _delete_path(entry)

    invalidate_cache()


def list_installed_dictionary_variants() -> list[str]:
    packages_path = _get_packages_path()
    if not packages_path.exists():
        return []

    installed: set[str] = set()
    existing_entries = {entry.name for entry in packages_path.iterdir()}

    for variant, (_pip_name, module_name) in _DICTIONARY_PACKAGE_MAP.items():
        module_prefix = module_name
        dist_prefix = _pip_name_prefix(_pip_name)

        if any(
            name.startswith(module_prefix) or name.startswith(dist_prefix)
            for name in existing_entries
        ):
            installed.add(variant)

    return sorted(installed)


def is_sudachipy_installed() -> bool:
    if list_installed_dictionary_variants():
        return True
    _import_sudachi_modules()
    return _sudachi_dictionary_module is not None


def _normalize_dict_variant(dict_variant: str | None) -> str:
    if dict_variant is None:
        return ""
    variant = dict_variant.strip().lower()
    if variant == "auto":
        return ""
    return variant


def _build_dictionary_kwargs(dict_variant: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    if dict_variant:
        kwargs["dict"] = dict_variant

    return kwargs


def _resolve_split_mode(split_mode_name: str) -> Any:
    assert _sudachi_tokenizer_module is not None

    token_split_modes = _sudachi_tokenizer_module.Tokenizer.SplitMode
    default_mode = token_split_modes.C

    mode_lookup = split_mode_name.upper()
    return getattr(token_split_modes, mode_lookup, default_mode)


def _should_skip_token(sudachi_morph: Any) -> bool:
    surface = sudachi_morph.surface()
    if not surface or surface.isspace():
        return True

    pos_info = sudachi_morph.part_of_speech()

    if not pos_info:
        return False

    pos = pos_info[0] if pos_info[0] else "*"
    sub_pos = pos_info[1] if len(pos_info) > 1 and pos_info[1] else "*"

    if pos in _POS_BLACKLIST:
        return True

    if sub_pos in _SUB_POS_BLACKLIST:
        return True

    return False


def _set_last_error(message: str | None) -> None:
    global _last_error
    _last_error = message


def _import_sudachi_modules(force: bool = False) -> None:
    global _sudachi_dictionary_module
    global _sudachi_tokenizer_module
    global _modules_imported
    global successful_import

    if _modules_imported and not force:
        return

    _ensure_packages_on_sys_path()

    try:
        sudachi_dictionary = importlib.import_module("sudachipy.dictionary")
        sudachi_tokenizer = importlib.import_module("sudachipy.tokenizer")
    except ModuleNotFoundError:
        _sudachi_dictionary_module = None
        _sudachi_tokenizer_module = None
        _modules_imported = False
        successful_import = False
        return

    _sudachi_dictionary_module = sudachi_dictionary
    _sudachi_tokenizer_module = sudachi_tokenizer
    _modules_imported = True
    successful_import = True


def _install_packages(packages: list[str]) -> None:
    python_binary = _get_python_binary()
    packages_path = _get_packages_path()
    packages_path.mkdir(parents=True, exist_ok=True)

    command = [
        python_binary,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(packages_path),
    ] + packages

    if testing_environment:
        return

    subprocess.run(command, check=True)


def _get_python_binary() -> str:
    if venv_binary is not None:
        python_path: str | None = venv_binary("python")
        if python_path is not None:
            return python_path
    return sys.executable


def _pip_name_prefix(pip_name: str) -> str:
    return pip_name.replace("-", "_")


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:  # pragma: no cover - defensive guard
            pass


def _get_packages_path() -> Path:
    if _packages_path_override is not None:
        return _packages_path_override
    return Path(__file__).resolve().parent.parent / "sudachi_packages"


def _ensure_packages_on_sys_path() -> None:
    global _path_appended

    if _path_appended:
        return

    packages_path = _get_packages_path()
    sys.path.append(str(packages_path))
    _path_appended = True
