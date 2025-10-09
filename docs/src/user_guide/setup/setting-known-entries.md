# Setting Known Entries

PrioritySieve tracks which entries you have reviewed by analyzing the cards you target. If you later remove those cards,
the history would normally disappear. To keep a permanent record, store known entries in `.csv` files inside
[[anki profile](../glossary.md#profile-folder)]`/known-entries`.

![known-entries-folder.png](../../img/known-morphs-folder.png)

Any `.csv` that follows the [priority file format](prioritizing.md#custom-priority-files)—such as the exports produced by
the [Known Entries Exporter](../usage/known-entries-exporter.md)—and lives in this folder will be read during
[Recalc](../usage/recalc.md) and merged into the database.

Enable this behaviour via `Read files in 'known-entries' folder and register entries as known` in the
[general settings tab](../setup/settings/general.md).
