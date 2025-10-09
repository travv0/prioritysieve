# Changes To Anki

After installing PrioritySieve you will notice a few additions to Anki:

## Toolbar Counters

The main toolbar shows three counters labelled **T**, **R**, and **P**:

- **Tracked (T)** – total number of unique entries PrioritySieve has discovered in your cards.
- **Reviewed (R)** – entries that have been studied at least once.
- **Pending (P)** – tracked entries you have not reviewed yet.

Each counter can be hidden individually via **Tools → PrioritySieve Settings → General → Hide toolbar items**, where you
can also hide the Recalc button if desired.

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
