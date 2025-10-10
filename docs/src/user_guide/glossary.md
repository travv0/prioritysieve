# Glossary

## 1T Sentence

Abbreviation for “one-target sentence”. A sentence that contains one unknown word or grammar structure. The unknown word
or structure is referred to as the “target word” or “target structure”.

Learning through 1T sentences can be thought of as “picking low-hanging fruit”. It makes the target word/structure easy
to understand and retain. As you continue to learn, sentences that were previously one-target will become zero-target,
and sentences that were previously [multi-target](glossary.md#mt-sentence) will become one-target. In this way, one-target sentences can take you
all the way to fluency.

[Learn about the "Input Hypothesis"](https://en.wikipedia.org/wiki/Input_hypothesis)

## MT Sentence
Abbreviation for “multi-target sentence”. A sentence that contains **more than** one unknown word or grammar structure.

## Entry

PrioritySieve tracks **entries**: a single expression (usually a sentence fragment or vocabulary item) and an optional
reading. An entry is identified by the pair `(text, reading)` and shared by every card in your collection that contains
the same expression. Recalc updates its lightweight database so each entry keeps one reviewed/pending state and priority.


## New cards

A card is considered "new" by Anki if it hasn't been studied yet, meaning you have never answered the card with
"Again", "Hard", "Good", or "Easy".

You can tell if a card is in the 'new' state when its `due` value looks like this: `New #....`

After reviewing a card, you can change its state back to "new" by using the reset option.

## Reviewed cards

Once a card has been studied, i.e. answered with either "Again", "Hard", "Good", or "Easy", it will move
from the "new" state into the "review" state.


## Unknown Entries
An entry is classified as **unknown** if it does not appear on any review cards and is not stored in the
[known entries folder](setup/setting-known-entries.md).

## Known Entries
An entry is classified as **known** if it is marked reviewed with a sufficient interval by Recalc, or if it is stored in
the [known entries folder](setup/setting-known-entries.md).


## Profile folder

For PrioritySieve to work, it needs to use some dedicated files and folders, namely:
- `prioritysieve.db`
- `names.txt`
- `priority-files/`
- `known-entries/`

Those can be found in the Anki profile folder. The path to the Anki profile folder depends on your operating system:

* Windows: `C:\Users\[user]\AppData\Roaming\Anki2\[profile_name]`
* Mac: `/Users/[user]/Library/Application Support/Anki2/[profile_name]`
* Linux: `/home/[user]/.local/share/Anki2/[profile_name]`


## sub2srs

You can get automatically generated Anki cards from tv-shows or movies by using a tool called sub2srs. Generating decks
with sub2srs is pretty technical, so I recommend finding sub2srs decks other people have already made.

[You can download many different anime sub2srs decks from this site.](https://www.mediafire.com/folder/p17g5uk4phb41/User_Uploaded_Anki_Decks)

[Read more about sub2srs here](https://learnanylanguage.fandom.com/wiki/Subs2srs)
