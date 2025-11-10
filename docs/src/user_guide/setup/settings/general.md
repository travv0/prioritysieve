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

* **Auto-suspend kanji subset variants:**  
  When enabled, PrioritySieve keeps only the kanji-richest spelling of a word active. New cards that drop kanji you have
  already reviewed (or that will appear sooner with a lower due value) are suspended automatically so you encounter the
  most informative variant first.
  * Enable **Also suspend okurigana-only variants** to extend the rule to spellings that share the exact same kanji (e.g.,
    `入口` vs `入り口`). Purely kana spellings stay active so homophones without kanji aren’t suppressed.
