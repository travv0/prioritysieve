# Exporting Known Entries

![known-entries-exporter.png](../../img/known-entries-exporter.png)

Exports all reviewed entries from `prioritysieve.db`. This is handy for [setting known entries](../setup/setting-known-entries.md)
or seeding external tools with the vocabulary you have already covered.

### Select Output

Choose the folder where PrioritySieve should write the CSV.

The default is [[anki profile](../glossary.md#profile-folder)]`/known-entries`.

### Resulting File

The file name will be `known_entries-{datetime}.csv`, where datetime is the time of creation, e.g.:

```
known_entries-2024-01-11@18-47-19.csv
```
The file format matches the [priority file generator](generators/frequency-file-generator.md) output.
