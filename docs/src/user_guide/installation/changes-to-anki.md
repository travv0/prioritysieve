# Changes To Anki

After installing PrioritySieve you will notice a few additions to Anki:

## Toolbar Counter

The main toolbar shows two counters:

- **Reviewed** – number of entries you have already reviewed.
- **Tracked** – total number of entries PrioritySieve has seen (or, if you enable the option in settings, only the
  reviewed count).

You can hide either counter or the Recalc button from **Tools → PrioritySieve Settings → General**.

## PrioritySieve Menu

The main window, browser, and reviewer receive new PrioritySieve menu entries. They expose actions such as Recalc, Learn
Card Now, Browse Same Entry, and the Known Entries exporter.

## Profile Files

PrioritySieve stores its data inside your Anki profile folder:

- `prioritysieve.db` – lightweight entry database.
- `prioritysieve-priority-files/` – custom priority CSVs.
- `prioritysieve-known-entries/` – exported reviewed entries.
- `prioritysieve_names.txt` – optional list of names to ignore during preprocessing.

You can safely back up, copy, or version control these files along with the rest of your profile.
