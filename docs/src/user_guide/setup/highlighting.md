# Highlighting

The entry-first rewrite removed the legacy morph highlighter. PrioritySieve no longer injects `<span>` wrappers, custom filters, or the `am-highlighted` field, so there is nothing to configure in this section.

If you relied on the previous highlighting workflow you now have three options:

1. Keep a copy of an older PrioritySieve release alongside the new entry-based add-on and continue using the legacy highlighter there.
2. Switch to a dedicated highlighting add-on that colours fields based on tags or templates.
3. Leave highlighting disabled—PrioritySieve’s tags still mark entries as `ready`, `not ready`, and `am-known-*`, and the toolbar counters show how many entries you have already reviewed.

All other functionality (recalc, tagging, duplicate handling, priority files, exporters, etc.) remains intact. You can safely remove any custom card template filters or styling that referenced `am-highlight` or `morph-status`.
