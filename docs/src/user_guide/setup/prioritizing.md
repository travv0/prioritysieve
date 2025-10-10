# Prioritizing

Priority files tell PrioritySieve which entries matter most. Lower numbers mean higher priority.

You can provide priorities in two ways:

1. **Collection frequency** – select “Collection frequency” in the note filter. PrioritySieve counts how often each entry
   appears and uses that as its priority.
2. **Custom CSV files** – drop `.csv` files into `prioritysieve-priority-files/` inside your Anki profile folder. Each CSV
   should contain the following columns:

   | Column    | Description                                                   |
   |-----------|---------------------------------------------------------------|
   | `Entry`   | The expression to prioritise.                                  |
   | `Reading` | Optional reading for the entry.                                |
   | `Priority`| Integer priority; smaller numbers are served sooner.          |
   | `Occurrences` | Optional count used by the readability report/generator. |

   Legacy headers such as `Morph-Lemma`/`Morph-Reading` are still accepted for compatibility, but newly generated files
   always use the simpler names above.

When several files contain the same entry, PrioritySieve keeps the lowest priority number. Run [Recalc](../usage/recalc.md)
whenever you add or update priority files so the changes take effect.
