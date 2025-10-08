# Progression

![progression-window.png](../../img/progression-window.png)

In the beginning stages of language acquisition, your working vocabulary will consist mostly of commonly used words.
As your ability increases, you will recognize a richer variety of expressions. As you approach native-level proficiency,
you will recognize almost everything—from the very common to the highly specialized.

The Progression tool helps you understand both your **learning progress** and the **quality of your card collection**
with respect to entry priorities.

## Setup

### Choosing Priority Files

![progression-priority.png](../../img/progression-priority.png)

Since progression is measured with respect to [entry priorities](../setup/prioritizing.md), first select which `.csv`
file(s) should define those priorities. Any `.csv` file located in the
[[anki profile folder](../glossary#profile-folder)]`/prioritysieve-priority-files/` directory is available for selection.

### Options

To gauge progression, PrioritySieve essentially calculates a histogram. Entries with assigned priorities are binned
into priority ranges (for example priorities `1–500`, `501–1000`, and so on).

The user can designate the bin size:

![bin_size.png](../../img/bin_size.png)

as well as the minimum and maximum priority considered:

![progression_priority_range.png](../../img/progression_priority_range.png)


> **Note**: the calculated bins depend on the number of entries present in the selected priority files.

Bins can also be cumulative:

![bins-cumulative.png](../../img/bins-cumulative.png)

In this mode, bin statistics will increase or decrease monotonically.

Entry-first PrioritySieve always evaluates entire expressions, so no additional evaluation mode is required.

## Results

Clicking `View Progress Report` will determine the current progression and populate the results. 

### Numerical and Percentage Tabs

![progression-numerical.png](../../img/progression-numerical.png)

The `Numerical` tab reports the number of unique entries, reviewed entries, pending entries, and missing entries in each
priority range (bin). Pending entries are present in the card collection but not yet reviewed. Missing entries do not
appear in your cards at all.

![progression-percentage.png](../../img/progression-percentage.png)

The `Percentage` tab reports the same statistics as percentages of unique entries. By examining the percentage of
reviewed entries you can gauge progress; the percentage of missing entries reflects how well your decks cover the chosen
priority files.

### Morph List Tab

![progression-morph-list.png](../../img/progression-morph-list.png)

The `Entry list` tab provides the status of each entry with a specified priority. Use it to quickly zero in on
high-priority expressions that are still pending or missing from your collection.

