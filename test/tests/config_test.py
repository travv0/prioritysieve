import json
from test.fake_configs import DEFAULT_CONFIG_PATH
from typing import Any

from prioritysieve.prioritysieve_config import (
    RawConfigFilterKeys,
    RawConfigKeys,
    RawConfigLanguageKeys,
)


def test_am_config_contains_keys() -> None:
    # This function loads the dict from 'config.json' and
    # removes all the attributes found in the key classes and checks
    # if anything was missed

    default_config_dict: dict[str, Any]

    with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as _file:
        default_config_dict = json.load(_file)

    assert len(default_config_dict) > 0

    custom_config_filter_attributes: list[str] = [
        _attr for _attr in dir(RawConfigFilterKeys) if _attr.startswith("__") is False
    ]
    custom_config_attributes: list[str] = [
        _attr for _attr in dir(RawConfigKeys) if _attr.startswith("__") is False
    ]
    custom_language_attributes: list[str] = [
        _attr for _attr in dir(RawConfigLanguageKeys) if _attr.startswith("__") is False
    ]

    assert len(custom_config_filter_attributes) > 0
    assert len(custom_config_attributes) > 0
    assert len(custom_language_attributes) > 0

    # Check filter keys within language
    language_dict = default_config_dict[RawConfigKeys.LANGUAGES][0]
    filter_keys = language_dict[RawConfigLanguageKeys.FILTERS][0].keys()

    for filter_key in list(filter_keys):
        if filter_key.upper() in custom_config_filter_attributes:
            del language_dict[RawConfigLanguageKeys.FILTERS][0][filter_key]
        else:
            assert False, f"Filter key {filter_key} not found in RawConfigFilterKeys"

    assert len(language_dict[RawConfigLanguageKeys.FILTERS][0]) == 0

    # Check language-level keys
    language_keys = list(language_dict.keys())
    for lang_key in language_keys:
        if lang_key.upper() in custom_language_attributes:
            del language_dict[lang_key]
        else:
            assert False, f"Language key {lang_key} not found in RawConfigLanguageKeys"

    assert len(language_dict) == 0

    # Check root-level config keys
    config_keys = list(default_config_dict.keys())
    for config_key in config_keys:
        if config_key.upper() in custom_config_attributes:
            del default_config_dict[config_key]
        else:
            assert False, f"Config key {config_key} not found in RawConfigKeys"

    assert len(default_config_dict) == 0


def test_am_config_correct_values() -> None:
    # All key class attributes should have the lowercase version
    # of the attribute name as their value.

    for attr in dir(RawConfigKeys):
        if not attr.startswith("__") and attr.isupper():
            if attr.startswith("LEGACY_"):
                continue
            value = getattr(RawConfigKeys, attr)
            if value.upper() != attr:
                print(f"attr: {attr} is not upper of value: {value}")
                assert False

    for attr in dir(RawConfigLanguageKeys):
        if not attr.startswith("__") and attr.isupper():
            value = getattr(RawConfigLanguageKeys, attr)
            if value.upper() != attr:
                print(f"attr: {attr} is not upper of value: {value}")
                assert False

    for attr in dir(RawConfigFilterKeys):
        if not attr.startswith("__") and attr.isupper():
            if attr.startswith("LEGACY"):
                continue
            value = getattr(RawConfigFilterKeys, attr)
            if value.upper() != attr:
                print(f"attr: {attr} is not upper of value: {value}")
                assert False
