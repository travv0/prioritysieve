from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

import pytest


def _bootstrap_minimal_environment() -> None:
    if "ankimorphs" not in sys.modules:
        package_root = Path(__file__).resolve().parents[2] / "ankimorphs"
        package_module = ModuleType("ankimorphs")
        package_module.__path__ = [str(package_root)]  # type: ignore[attr-defined]
        sys.modules["ankimorphs"] = package_module

    if "ankimorphs.ankimorphs_config" not in sys.modules:
        config_module = ModuleType("ankimorphs.ankimorphs_config")

        class _StubConfig:  # pylint:disable=too-few-public-methods
            def __init__(self, *_, **__) -> None:  # noqa: D401
                pass

        config_module.AnkiMorphsConfig = _StubConfig  # type: ignore[attr-defined]
        config_module.RawConfigKeys = SimpleNamespace()  # type: ignore[attr-defined]
        config_module.update_configs = lambda _cfg: None  # type: ignore[attr-defined]
        sys.modules["ankimorphs.ankimorphs_config"] = config_module

    if "aqt" not in sys.modules:
        aqt_module = ModuleType("aqt")
        aqt_module.mw = None  # type: ignore[attr-defined]
        package_module = ModuleType("aqt.package")

        def _venv_binary(_: str) -> str | None:  # pylint:disable=unused-argument
            return None

        package_module.venv_binary = _venv_binary  # type: ignore[attr-defined]

        sys.modules["aqt"] = aqt_module
        sys.modules["aqt.package"] = package_module

    if "anki" not in sys.modules:
        try:
            importlib.import_module("anki")
        except ModuleNotFoundError:
            anki_module = ModuleType("anki")
            utils_module = ModuleType("anki.utils")

            def _is_win() -> bool:
                return sys.platform.startswith("win")

            utils_module.is_win = _is_win  # type: ignore[attr-defined]
            anki_module.utils = utils_module  # type: ignore[attr-defined]
            sys.modules["anki"] = anki_module
            sys.modules["anki.utils"] = utils_module


_bootstrap_minimal_environment()


class _FakeSudachiMorpheme:
    def __init__(self, surface: str, lemma: str, pos: str, sub_pos: str) -> None:
        self._surface = surface
        self._lemma = lemma
        self._pos = pos
        self._sub_pos = sub_pos

    def surface(self) -> str:
        return self._surface

    def dictionary_form(self) -> str:
        return self._lemma

    def part_of_speech(self) -> tuple[str, str, str, str, str, str]:
        return (self._pos, self._sub_pos, "*", "*", "*", "*")


class _FakeSudachiTokenizer:
    SplitMode = SimpleNamespace(A="mode_a", B="mode_b", C="mode_c")

    last_mode: Any | None = None
    last_sentence: str | None = None
    last_variant: str | None = None

    def __init__(self, variant: str) -> None:
        self.variant = variant

    def tokenize(self, sentence: str, mode: Any) -> list[_FakeSudachiMorpheme]:
        _FakeSudachiTokenizer.last_mode = mode
        _FakeSudachiTokenizer.last_sentence = sentence
        _FakeSudachiTokenizer.last_variant = self.variant

        if mode == self.SplitMode.A:
            return [
                _FakeSudachiMorpheme("す", "す", "名詞", "普通名詞"),
                _FakeSudachiMorpheme("だち", "だち", "名詞", "普通名詞"),
                _FakeSudachiMorpheme("が", "が", "助詞", "格助詞"),
                _FakeSudachiMorpheme("好き", "好き", "形容詞", "一般"),
                _FakeSudachiMorpheme("です", "です", "助動詞", "*"),
            ]

        return [
            _FakeSudachiMorpheme("すだち", "すだち", "名詞", "普通名詞"),
            _FakeSudachiMorpheme("が", "が", "助詞", "格助詞"),
            _FakeSudachiMorpheme("好き", "好き", "形容詞", "一般"),
            _FakeSudachiMorpheme("です", "です", "助動詞", "*"),
        ]


class _FakeSudachiDictionary:
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        _FakeSudachiDictionary.last_kwargs = kwargs
        self._variant = kwargs.get("dict", "")

    def create(self) -> _FakeSudachiTokenizer:
        return _FakeSudachiTokenizer(self._variant)


@pytest.fixture()
def sudachi_stub_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[None]:
    packages_path = tmp_path / "sudachi_pkgs"
    packages_path.mkdir()
    (packages_path / "sudachidict_core").mkdir()
    (packages_path / "sudachidict_full").mkdir()

    sudachi_module = ModuleType("sudachipy")
    dictionary_module = ModuleType("dictionary")
    dictionary_module.Dictionary = _FakeSudachiDictionary
    tokenizer_module = ModuleType("tokenizer")
    tokenizer_module.Tokenizer = _FakeSudachiTokenizer
    sudachi_module.dictionary = dictionary_module
    sudachi_module.tokenizer = tokenizer_module

    original_modules = {
        "sudachipy": sys.modules.get("sudachipy"),
        "sudachipy.dictionary": sys.modules.get("sudachipy.dictionary"),
        "sudachipy.tokenizer": sys.modules.get("sudachipy.tokenizer"),
    }

    sys.modules["sudachipy"] = sudachi_module
    sys.modules["sudachipy.dictionary"] = dictionary_module
    sys.modules["sudachipy.tokenizer"] = tokenizer_module

    from ankimorphs.morphemizers import morphemizer_utils, spacy_wrapper, sudachi_wrapper

    importlib.reload(sudachi_wrapper)
    monkeypatch.setattr(morphemizer_utils, "sudachi_wrapper", sudachi_wrapper, raising=False)

    sudachi_wrapper.testing_environment = True
    spacy_wrapper.testing_environment = True
    sudachi_wrapper.set_packages_path_override(packages_path)
    sudachi_wrapper.invalidate_cache()

    yield

    sudachi_wrapper.set_packages_path_override(None)
    sudachi_wrapper.invalidate_cache()
    spacy_wrapper.testing_environment = False

    for module_name, module in original_modules.items():
        if module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = module

    sys.modules.pop("sudachipy", None)
    sys.modules.pop("sudachipy.dictionary", None)
    sys.modules.pop("sudachipy.tokenizer", None)


from ankimorphs.morpheme import Morpheme
from ankimorphs.morphemizers import morphemizer_utils, sudachi_wrapper
from ankimorphs.morphemizers.sudachi_morphemizer import SudachiMorphemizer


def _get_surfaces(morphs: list[Morpheme]) -> list[str]:
    return [morph.inflection for morph in morphs]


@pytest.mark.usefixtures("sudachi_stub_environment")
def test_sudachi_morpheme_generation_default_variant() -> None:
    morphemizer = SudachiMorphemizer("core", "C")
    assert morphemizer.init_successful()

    sentence = "すだちが好きです"
    morphs = next(morphemizer.get_morphemes([sentence]))
    assert _get_surfaces(morphs) == ["すだち", "が", "好き", "です"]


@pytest.mark.usefixtures("sudachi_stub_environment")
def test_sudachi_split_mode_controls_tokenization() -> None:
    morphemizer = SudachiMorphemizer("core", "A")
    assert morphemizer.init_successful()

    sentence = "すだちが好きです"
    morphs = next(morphemizer.get_morphemes([sentence]))
    assert _get_surfaces(morphs) == ["す", "だち", "が", "好き", "です"]


@pytest.mark.usefixtures("sudachi_stub_environment")
def test_list_installed_dictionary_variants_detects_modules() -> None:
    assert set(sudachi_wrapper.list_installed_dictionary_variants()) == {"core", "full"}


@pytest.mark.usefixtures("sudachi_stub_environment")
def test_available_morphemizers_include_variants() -> None:
    morphemizer_utils.available_morphemizers = None
    morphemizer_utils.morphemizers_by_description.clear()

    descriptions = {
        morphemizer.get_description(): morphemizer
        for morphemizer in morphemizer_utils.get_all_morphemizers()
    }

    expected_description = "SudachiPy: Japanese (core, mode C)"
    assert expected_description in descriptions


def test_install_dictionary_invokes_pip_with_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sudachi_wrapper.testing_environment = False
    sudachi_wrapper.set_packages_path_override(tmp_path / "sudachi_pkgs")

    commands: list[list[str]] = []

    monkeypatch.setattr(sudachi_wrapper, "_get_python_binary", lambda: "python-bin")

    def _fake_run(cmd: list[str], check: bool) -> None:  # pylint:disable=unused-argument
        commands.append(cmd)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    sudachi_wrapper.install_dictionary("core")

    assert commands, "Expected pip install command to be executed"
    cmd = commands[0]
    assert cmd[:7] == [
        "python-bin",
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(tmp_path / "sudachi_pkgs"),
    ]
    assert cmd[-1] == "sudachidict-core"

    sudachi_wrapper.testing_environment = True
    sudachi_wrapper.set_packages_path_override(None)
    sudachi_wrapper.invalidate_cache()


def test_remove_dictionary_deletes_installed_files(tmp_path: Path) -> None:
    packages_path = tmp_path / "sudachi_pkgs"
    packages_path.mkdir()
    module_dir = packages_path / "sudachidict_full"
    module_dir.mkdir()
    dist_dir = packages_path / "sudachidict-full-202401.dist-info"
    dist_dir.mkdir()

    sudachi_wrapper.set_packages_path_override(packages_path)
    sudachi_wrapper.remove_dictionary("full")
    assert not module_dir.exists()
    assert not dist_dir.exists()
    sudachi_wrapper.set_packages_path_override(None)
    sudachi_wrapper.invalidate_cache()


def test_install_sudachipy_invokes_pip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sudachi_wrapper.testing_environment = False
    sudachi_wrapper.set_packages_path_override(tmp_path / "sudachi_pkgs")

    commands: list[list[str]] = []

    monkeypatch.setattr(sudachi_wrapper, "_get_python_binary", lambda: "python-bin")

    def _fake_run(cmd: list[str], check: bool) -> None:  # pylint:disable=unused-argument
        commands.append(cmd)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    sudachi_wrapper.install_sudachipy()

    assert commands, "Expected pip install command to be executed"
    assert commands[0][-1] == "sudachipy"

    sudachi_wrapper.testing_environment = True
    sudachi_wrapper.set_packages_path_override(None)
    sudachi_wrapper.invalidate_cache()
