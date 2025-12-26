import json
from pathlib import Path
from typing import Any

from prioritysieve.prioritysieve_config import RawConfigKeys, RawConfigLanguageKeys

DEFAULT_CONFIG_PATH = Path("prioritysieve", "config.json")

with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as handle:
    default_config_dict: dict[str, Any] = json.load(handle)

config_ignoring_custom_characters = json.loads(json.dumps(default_config_dict))
config_ignoring_custom_characters[RawConfigKeys.LANGUAGES][0][
    RawConfigLanguageKeys.PREPROCESS_IGNORE_CUSTOM_CHARACTERS
] = True
config_ignoring_custom_characters[RawConfigKeys.LANGUAGES][0][
    RawConfigLanguageKeys.PREPROCESS_CUSTOM_CHARACTERS_TO_IGNORE
] = ",.?"
