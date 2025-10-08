# Databases

## prioritysieve.db

This is an sqlite database with three tables that store cached entry metadata:

```
'Cards'
'Entries'
'CardEntries'
```

Each card can reference a single focus entry, while the same entry can appear on many cards. The `CardEntries`
table therefore links cards to entry rows and allows PrioritySieve to answer questions like “which other cards use the
same expression + reading combination?” quickly.

### Cards table

```roomsql
card_id INTEGER PRIMARY KEY,
note_id INTEGER NOT NULL,
note_type_id INTEGER NOT NULL,
card_type INTEGER NOT NULL,
tags TEXT NOT NULL
```

The card metadata mirrors the information we need for duplicate detection and tagging.

### Entries table

```roomsql
text TEXT NOT NULL,
reading TEXT NOT NULL,
reviewed INTEGER NOT NULL,
PRIMARY KEY (text, reading)
```

Entries are unique per `(text, reading)` pair. The `reviewed` flag indicates whether any card containing that entry
has been seen.

### CardEntries table

```roomsql
card_id INTEGER PRIMARY KEY,
entry_text TEXT NOT NULL,
entry_reading TEXT NOT NULL,
FOREIGN KEY(card_id) REFERENCES Cards(card_id) ON DELETE CASCADE,
FOREIGN KEY(entry_text, entry_reading) REFERENCES Entries(text, reading)
```

This table joins the two sets together so we can query by either direction efficiently.

## Anki dbs

        table_info = mw.col.db.execute("PRAGMA table_info('decks');")
        print(f"table_info: {result}")

Anki collection db tables:

```
[['col'],
['notes'],
['cards'],
['revlog'],
['deck_config'],
['config'],
['fields'],
['templates'],
['notetypes'],
['decks'],
['sqlite_stat1'],
['sqlite_stat4'],
['tags'],
['graves']]
```

notes table:

```
[[0, 'id', 'INTEGER', 0, None, 1],
[1, 'guid', 'TEXT', 1, None, 0],
[2, 'mid', 'INTEGER', 1, None, 0],
[3, 'mod', 'INTEGER', 1, None, 0],
[4, 'usn', 'INTEGER', 1, None, 0],
[5, 'tags', 'TEXT', 1, None, 0],
[6, 'flds', 'TEXT', 1, None, 0],
[7, 'sfld', 'INTEGER', 1, None, 0],
[8, 'csum', 'INTEGER', 1, None, 0],
[9, 'flags', 'INTEGER', 1, None, 0],
[10, 'data', 'TEXT', 1, None, 0]]
```

notetypes table:

```
[[0, 'id', 'INTEGER', 1, None, 1],
[1, 'name', 'TEXT', 1, None, 0],
[2, 'mtime_secs', 'INTEGER', 1, None, 0],
[3, 'usn', 'INTEGER', 1, None, 0],
[4, 'config', 'BLOB', 1, None, 0]]
```

cards table:

```
'id'     ID_FIELD_NUMBER: builtins.int
'nid'    NOTE_ID_FIELD_NUMBER: builtins.int
'did'    DECK_ID_FIELD_NUMBER: builtins.int
'ord'    TEMPLATE_IDX_FIELD_NUMBER: builtins.int
'mod'    MTIME_SECS_FIELD_NUMBER: builtins.int  # when card was modified
'usn'    USN_FIELD_NUMBER: builtins.int
'type'   CTYPE_FIELD_NUMBER: builtins.int
'queue'  QUEUE_FIELD_NUMBER: builtins.int
'due'    DUE_FIELD_NUMBER: builtins.int
'ivl'    INTERVAL_FIELD_NUMBER: builtins.int
'factor' EASE_FACTOR_FIELD_NUMBER: builtins.int
'reps'   REPS_FIELD_NUMBER: builtins.int
'lapses' LAPSES_FIELD_NUMBER: builtins.int
'left'   REMAINING_STEPS_FIELD_NUMBER: builtins.int
'odue'   ORIGINAL_DUE_FIELD_NUMBER: builtins.int
'odid'   ORIGINAL_DECK_ID_FIELD_NUMBER: builtins.int
'flags'  FLAGS_FIELD_NUMBER: builtins.int
'data'   custum_data builtins.str
```

'type' is the learning stage type:
```
CardType = NewType("CardType", int)
CARD_TYPE_NEW = CardType(0)
CARD_TYPE_LRN = CardType(1)
CARD_TYPE_REV = CardType(2)
CARD_TYPE_RELEARNING = CardType(3)
```


'queue' types:
```
CardQueue = NewType("CardQueue", int)
QUEUE_TYPE_MANUALLY_BURIED = CardQueue(-3)
QUEUE_TYPE_SIBLING_BURIED = CardQueue(-2)
QUEUE_TYPE_SUSPENDED = CardQueue(-1)
QUEUE_TYPE_NEW = CardQueue(0)
QUEUE_TYPE_LRN = CardQueue(1)
QUEUE_TYPE_REV = CardQueue(2)
QUEUE_TYPE_DAY_LEARN_RELEARN = CardQueue(3)
QUEUE_TYPE_PREVIEW = CardQueue(4)
```
