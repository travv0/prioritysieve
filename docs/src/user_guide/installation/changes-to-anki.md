# Changes To Anki

After installing PrioritySieve you will notice a few additions to Anki:

## Toolbar Counter

The main toolbar shows two counters:

- **Tracked** – total number of unique entries PrioritySieve has discovered in your cards.
- **Pending** – tracked entries you have not reviewed yet.

If you switch **Tools → PrioritySieve Settings → General → Toolbar counters show** to *Reviewed entries*, the primary
counter becomes **Reviewed** (entries already studied) while the secondary counter continues to display **Pending**.
You can hide either counter or the Recalc button from the same settings page.

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
