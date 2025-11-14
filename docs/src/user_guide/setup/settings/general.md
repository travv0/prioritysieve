# General

![general-tab.png](../../../img/general-tab.png)

The General tab contains a handful of global behaviour toggles.

* **Read files in 'known-entries' folder and register entries as known**:  
  Import known entries from the `known-entries` folder. Read more in [Setting Known Entries](../setting-known-entries.md).

* **Automatically Recalc after Anki sync**:  
  Run a full recalc as soon as sync downloads changes that touch your configured note filters. PrioritySieve compares
  collection snapshots before and after syncing so the recalc only runs when something relevant changed.

* **Hide toolbar items:**  
  Toggle the visibility of each [toolbar item](../../installation/changes-to-anki.md#toolbar) individually. The three counters
  now appear as single-letter labels (**T**, **R**, **P**) for tracked, reviewed, and pending entries respectively.

* **Deduplicate toolbar counts:**  
  Merge toolbar counters when multiple notes represent the same word with different kanji/kana mixes (e.g., removing
  okurigana or showing the reading only). Homophones that use different kanji remain separate so distinct words are still
  counted individually.

* **Auto-suspend variant spellings (kanji subsets & okurigana):**  
  Keeps only the most informative spelling of each entry active. Cards whose kanji are a strict subset of a reviewed
  spelling, or that differ only by okurigana, get suspended (and treated as a single entry in the toolbar counts). Purely
  kana spellings stay active so distinct homophones without kanji aren’t hidden.

* **Treat hiragana & katakana spellings as variants:**  
  When enabled, words written entirely in kana are also treated as duplicates if the same text appears in both hiragana
  and katakana. The higher-frequency spelling stays active while the alternate spelling is suspended, and toolbar counts
  collapse those duplicates alongside the Browser tool.
