# PrioritySieve

PrioritySieve is an entry-first scheduler for Anki. The add-on keeps track of every expression you study, lines them up against the priority lists you provide, and then updates card due dates, tags, and helper fields so that your decks always surface the next unseen entry. The project started life as a fork of [AnkiMorphs](https://github.com/mortii/anki-morphs), but it has since been rewritten around entries rather than morphs: a single expression with a single reading and a simple “reviewed or not” state.

Used together with [KanjiCards](https://github.com/travv0/KanjiCards) you can recreate the flow that jpdb.io popularised—learn the kanji that will appear in your vocabulary first, then move through vocabulary in frequency order with automatic tag and suspension management.

---

## What PrioritySieve does
- **Entry-based recalc.** Recalc inspects the note filters you configure and rebuilds a lightweight entry database (`EntryDB`). Every card linked to the same entry shares a single due date, and duplicates are automatically suspended so that only the highest-priority card remains in your queue.
- **Priority-aware scheduling.** Drop CSV files into `prioritysieve-priority-files/` with columns such as `Entry`, optional `Reading`, and `Priority`. PrioritySieve merges them, assigns integer priorities to matching entries, and sets card due values accordingly. Cards that are not listed can be automatically suspended.
- **Automatic tagging and helper fields.** During recalc, PrioritySieve applies the ready/not-ready/known tags you configure, ensures the optional `ps-reading` field mirrors the chosen reading source, and tidies up tags created by earlier runs.
- **Live toolbar stats and progression analysis.** The toolbar counters show how many entries you have seen versus reviewed, and the progression window lets you inspect how many cards ahead of you fall within any priority band.
- **Duplicate and maintenance utilities.** Tools such as the duplicate entry finder, profile-specific settings, priority-file generators, and the known entries exporter live under **Tools → PrioritySieve**.

Because everything pivots around entries, there is no morphemizer to configure and no highlighting layer to keep in sync—the add-on only needs the text field you target, an optional reading source, and your priority lists.

---

## Pairing with KanjiCards
KanjiCards keeps a dedicated kanji deck aligned with the characters that appear in your vocabulary notes. When you run KanjiCards before a PrioritySieve recalc you get a jpdb-like pipeline:

1. KanjiCards makes sure you have kanji cards ready (or suspended) for every character in your vocab decks.
2. PrioritySieve recalc only unsuspends vocab entries once their kanji have been reviewed and prioritises the remaining unseen entries by frequency.

The result is a smooth “kanji first, vocab second” workflow with Anki’s stock reviewer.

---

## Getting started
1. **Install.** Copy the folder into `Anki2/addons21/prioritysieve` (or install the packaged add-on) and restart Anki.
2. **Configure filters.** Open **Tools → PrioritySieve Settings** and, for each note type you care about, pick the expression field, optional reading field, and the tags you want PrioritySieve to manage.
3. **Provide priority data.** Place your CSV files in the profile folder under `prioritysieve-priority-files/`. Each file should contain at least an `Entry` column, optionally a `Reading` column (the legacy headers `Morph-Lemma`/`Morph-Reading` are still accepted), and a numeric `Priority` column. Lower numbers = higher priority; unlisted entries default to the lowest priority.
4. **Run recalc.** Use the toolbar button or the shortcut defined in the settings dialog. Recalc can also trigger automatically after sync when you enable the option in settings.

The add-on stores per-profile settings in `prioritysieve_profile_settings.json`, so each Anki profile can keep an independent set of note filters and behaviour.

---

## Working with priority files
- **Format.** PrioritySieve accepts `Entry`, optional `Reading`, and `Priority` columns. Legacy exports that label these columns `Lemma`, `Morph-Lemma`, or `Morph-Reading` are also recognised for backwards compatibility.
- **Generators.** The generator window (Tools → PrioritySieve → Generators) now reads existing CSV exports—such as frequency lists or parsed immersion logs—and converts them into PrioritySieve-friendly files. You can also build study plans that merge multiple CSVs and annotate the originating file for each entry.
- **Known entry exporter.** The exporter writes `Entry`, optional `Reading`, and optional `Occurrences` columns for every entry that PrioritySieve currently marks as reviewed, making it easy to seed external tooling or share progress.

---

## Documentation & support
The full user guide, including explanations of every settings tab, automation hook, toolbar button, and maintenance tool, lives in the [`docs/`](docs/) folder and is published alongside the project releases.

If you run into issues, start by checking the **Known Problems** section in the docs and the issue tracker. The codebase is fully open source (MPL 2.0), so contributions and pull requests are welcome.
