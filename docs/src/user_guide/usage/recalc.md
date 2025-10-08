# Recalc

Recalc (“recalculate”) is the command that keeps PrioritySieve in sync with your collection. When you run it, the add-on:

1. Rebuilds the entry database (`prioritysieve.db`) from the cards that match your note filters.
2. Merges in the priorities from your CSV files (or the collection-frequency option).
3. Applies tags, updates the optional `ps-reading` field, and automatically suspends duplicate or out-of-scope entries.

Run Recalc at least once per study session—either before you start or after you finish—so new cards appear in the right
order. You can also enable “Automatically Recalc before Anki sync” in **Tools → PrioritySieve Settings → General** to
let the add-on update itself during every sync.
