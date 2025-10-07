class General:
    PRIORITYSIEVE_VERSION = "prioritysieve_version"
    RECALC_COLLECTION_STATE = "recalc_collection_state"
    RECALC_SETTINGS_STATE = "recalc_settings_state"


class Dialogs:
    GENERATORS_WINDOW = "generators_window"
    KNOWN_ENTRIES_EXPORTER = "known_entries_exporter"
    PROGRESSION_WINDOW = "progression_window"
    GENERATOR_OUTPUT_PRIORITY_FILE = "generator_output_priority_file"
    GENERATOR_OUTPUT_STUDY_PLAN = "generator_output_study_plan"
    SETTINGS_DIALOG = "settings_dialog"


class GeneratorsWindowKeys:
    WINDOW_GEOMETRY = "window_geometry"
    INPUT_DIR = "input_dir"


class KnownEntriesExporterKeys:
    WINDOW_GEOMETRY = "window_geometry"
    OUTPUT_DIR = "output_dir"
    INCLUDE_READING = "include_reading"
    REVIEWED_ONLY = "reviewed_only"
    OCCURRENCES = "occurrences"


class ProgressionWindowKeys:
    WINDOW_GEOMETRY = "window_geometry"
    PRIORITY_FILE = "priority_file"
    LEMMA_EVALUATION = "lemma_evaluation"
    INFLECTION_EVALUATION = "inflection_evaluation"
    PRIORITY_RANGE_START = "priority_range_start"
    PRIORITY_RANGE_END = "priority_range_end"
    BIN_SIZE = "bin_size"
    BIN_TYPE_NORMAL = "bin_type_normal"
    BIN_TYPE_CUMULATIVE = "bin_type_cumulative"


class GeneratorsOutputKeys:
    WINDOW_GEOMETRY = "window_geometry"
    OUTPUT_FILE_PATH = "output_file_path"
    INCLUDE_READING = "include_reading"
    MIN_OCCURRENCE_SELECTED = "min_occurrence_selected"
    MIN_OCCURRENCE_CUTOFF = "min_occurrence_cutoff"
    COMPREHENSION_SELECTED = "comprehension_selected"
    COMPREHENSION_CUTOFF = "comprehension_cutoff"
    OCCURRENCES_COLUMN_SELECTED = "occurrences_column_selected"


class SettingsDialogKeys:
    WINDOW_GEOMETRY = "window_geometry"
