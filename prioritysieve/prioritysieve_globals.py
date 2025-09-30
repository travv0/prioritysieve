"""
This file contains constants and variables that are used across multiple files.
If a constants or a variable is only used in one file, then it should be declared in
that file and not here.
"""

# Semantic Versioning https://semver.org/
__version__ = "6.0.3"

DEV_MODE: bool = False

PROFILE_SETTINGS_FILE_NAME = "prioritysieve_profile_settings.json"
NAMES_TXT_FILE_NAME = "prioritysieve_names.txt"
KNOWN_MORPHS_DIR_NAME = "prioritysieve-known-morphs"
PRIORITY_FILES_DIR_NAME = "prioritysieve-priority-files"

SETTINGS_DIALOG_NAME: str = "ps_settings_dialog"
TAG_SELECTOR_DIALOG_NAME: str = "ps_tag_selector_dialog"
GENERATOR_DIALOG_NAME: str = "ps_generator_dialog"
PROGRESSION_DIALOG_NAME: str = "ps_progression_dialog"
KNOWN_MORPHS_EXPORTER_DIALOG_NAME: str = "ps_known_morphs_exporter_dialog"

# The static names of the extra fields
EXTRA_FIELD_ALL_MORPHS: str = "ps-all-morphs"
EXTRA_FIELD_ALL_MORPHS_COUNT: str = "ps-all-morphs-count"
EXTRA_FIELD_UNKNOWN_MORPHS: str = "ps-unknown-morphs"
EXTRA_FIELD_UNKNOWN_MORPHS_COUNT: str = "ps-unknown-morphs-count"
EXTRA_FIELD_HIGHLIGHTED: str = "ps-highlighted"
EXTRA_FIELD_SCORE: str = "ps-score"
EXTRA_FIELD_SCORE_TERMS: str = "ps-score-terms"
EXTRA_FIELD_STUDY_MORPHS: str = "ps-study-morphs"
EXTRA_FIELD_MORPH_READINGS: str = "ps-morph-readings"

# Morph priority options in the note filter settings
NONE_OPTION = "(none)"
COLLECTION_FREQUENCY_OPTION = "Collection frequency"

# Combobox options for 'on recalc' in card-handling settings
NEVER_OPTION = "Never"
ONLY_KNOWN_OPTION = "If all morphs are known"
ONLY_KNOWN_OR_FRESH_OPTION = "If all morphs are known or fresh"

# Priority file/study plan headers
LEMMA_HEADER = "Morph-Lemma"
INFLECTION_HEADER = "Morph-Inflection"
READING_HEADER = "Morph-Reading"
LEMMA_PRIORITY_HEADER = "Lemma-Priority"
INFLECTION_PRIORITY_HEADER = "Inflection-Priority"
OCCURRENCES_HEADER = "Occurrences"

STATUS_KNOWN = "known"
STATUS_LEARNING = "learning"
STATUS_UNKNOWN = "unknown"
STATUS_UNDEFINED = "undefined"

config_broken: bool = False
new_config_found: bool = False
shown_config_warning: bool = False
