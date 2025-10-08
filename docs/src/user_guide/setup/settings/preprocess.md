# Preprocess

![preprocess-tab.png](../../../img/preprocess-tab.png)

These options preprocess the expression field before PrioritySieve stores it as an entry. They let you ignore
supporting text (furigana, speaker names, etc.) so the tracked entry stays clean.

* **Ignore content in square brackets []**:  
  Ignore content such as furigana readings and pitch

* **Ignore content in round brackets ()**:  
  Ignore content such as character names and readings in scripts
* **Ignore content in slim round brackets（ ）**:  
  Ignore content such as character names and readings in Japanese scripts
* **Ignore content in suspended cards**:  
  Ignore text found on suspended cards **except** for cards tagged as known. This lets you safely suspend duplicates
  without losing the entry history.
* **Ignore names found in names.txt**:  
  Ignore any words listed in [names.txt](../names.md).
* **Ignore numbers**:  
  Strip digits from the analysed text.
* **Ignore custom characters**:  
  Any characters you specify (e.g. `,.?@`) will be removed before entries are matched.
