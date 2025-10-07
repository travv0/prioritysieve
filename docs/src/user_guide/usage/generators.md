# Generators

PrioritySieve ships with three tools under **Tools → PrioritySieve → Generators**:

- **Readability report** – summarises how many entries inside a batch of CSV files are already reviewed versus still unseen.
- **Priority file generator** – merges one or more CSV files into a PrioritySieve-ready priority list.
- **Study plan generator** – stitches several CSV files together in a fixed order so you can study entries in the same sequence they appear in your source material.

Unlike the legacy workflow, generators no longer run morphemizers. They work directly with CSV files that already contain entries. This makes it easy to reuse exports from other tools or tweak priority lists in a spreadsheet.

---

## Preparing input files

1. Place the CSV files you want to analyse in a directory. The generator scans the directory recursively and picks up every `.csv` file it finds.
2. Each file must be encoded in UTF-8 and contain at least an `Entry` column. Optional columns include `Reading`, `Morph-Reading`, `Lemma`, or `Morph-Lemma` (PrioritySieve treats these as entry/reading synonyms) and `Occurrences`, `Occurrence`, `Count`, or `Frequency`.
3. Click **Choose Folder** in the generator window, point it at the directory, and press **Load Files**. The table at the bottom lists every CSV that will be processed.

*Tip:* because the generator works with plain CSVs, you can feed it frequency lists, immersion logs, or any other export as long as you provide an `Entry` column.

---

## Output options

Clicking **Generate Priority File** or **Generate Study Plan** opens a dialog with the following settings:

- **Output file** – defaults to your profile’s `prioritysieve-priority-files/` directory. You can change the destination, but PrioritySieve only auto-loads files stored in that folder.
- **Include reading column** – adds a `Reading` column when the input files contain reading information.
- **Include occurrences column** – writes out the summed occurrence count for each entry. This is optional; PrioritySieve only needs the `Entry` (and optional `Reading`) columns when consuming a priority file.
- **Minimum occurrence** – keep entries that appear at least *n* times across the selected files.
- **Comprehension target** – keep enough entries to cover the specified percentage of total occurrences. For example, 90% includes the most common entries until their cumulative count reaches 90% of all occurrences.

Only one cutoff mode (minimum occurrence or comprehension) is active at a time.

---

## Readability report

The readability report combines every loaded CSV with your existing PrioritySieve entry database:

- **Unique entries** – total distinct entries in the file.
- **Reviewed / Unreviewed entries** – how many of those entries PrioritySieve already marks as reviewed.
- **Reviewed / Unreviewed occurrences** – occurrence counts split the same way.

Both the raw counts and the percentages are displayed in separate tabs. Sorting a column in either tab preserves the order when you generate a study plan, which is handy when you want to follow the file with the fewest unknown entries first.

---

## Priority file generator

This generator produces a PrioritySieve-ready CSV with the following columns:

1. `Entry`
2. Optional `Reading`
3. `Priority` (0-based, lower numbers indicate higher priority)
4. Optional `Occurrences`

Entries are sorted by total occurrence count. If you apply a comprehension cutoff or minimum occurrence threshold, rows outside the range are dropped. The resulting file can be copied straight into `prioritysieve-priority-files/` and selected from the settings dialog.

---

## Study plan generator

Study plans keep the input files in their current order before sorting by occurrence inside each file. The output columns are:

1. `Entry`
2. Optional `Reading`
3. `Status` (`reviewed` or `unreviewed` based on the current PrioritySieve entry database)
4. Optional `Occurrences`
5. `File` (relative path from the chosen input directory)

Duplicate entries are removed after the first appearance so that you only study each expression once. This format is useful when you want to progress through a TV series, book series, or any other structured source in the order it was published.

---

## After generating files

- Priority files placed in `prioritysieve-priority-files/` are available immediately in the **Note Filters** tab of the settings dialog.
- Study plans live alongside other priority files. You can reference them directly or merge them into larger lists.
- The readability report updates in-place; no files are written.

Whenever you add or modify CSVs, rerun **Load Files** before generating new outputs, and run **Recalc** afterwards so the new priorities flow into your cards.
