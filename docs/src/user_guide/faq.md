# Frequently Asked Questions

### Transitioning from MorphMan

> Should I add a note-filter row for both my sentence field and my focus morph field?

No, only use the sentence field.

> Should I use the same tags in PrioritySieve that I was using with Morphman?

I recommend using the default PrioritySieve tags. Mixing tags can get confusing.

> Should I export all of studied and in progress words into a CSV spreadsheet?

PrioritySieve tracks entries independently of MorphMan. The [Known Entries Exporter](usage/known-entries-exporter.md) is
useful for trimming your collection, but it isn’t required for migrating.

If you want to seed PrioritySieve with entries you already tagged as known in MorphMan, bulk-tag those cards with
`am-known-manually`:

1. Open `Browse`
2. Select the MorphMan known tag in the sidebar
3. Select all those cards
4. Go to `Notes` in the topbar and click on `Add Tags` (or use Ctrl+Shift+A)
5. Enter the tag `am-known-manually`

That approach could be overkill though. You can always press `K` the next time the card appears.


> Should I manually delete the words in the focus morph field of my cards so that PrioritySieve can cleanly reparse
> everything?

PrioritySieve ignores MorphMan’s focus morph field, so it makes no difference.
