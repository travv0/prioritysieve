<br>
<div style="text-align: center;">
<i>
A huge thank you to Matt Vs Japan (<a href="https://www.youtube.com/@mattvsjapan">Youtube</a>, <a href="https://twitter.com/mattvsjapan">Twitter</a>) for his absolutely <br> amazing work on the original version of the user guide!
</i>
</div>
<br>

# Introduction

PrioritySieve is an Anki add-on that rearranges your cards based on two pieces of information: whether you have already
reviewed an entry and how important that entry is according to your priority lists. It keeps a lightweight database of
every expression you study so your decks surface the right cards at the right time.

During Recalc, PrioritySieve reads the expression field you configured for each note type, links every card to a single
entry `(text, reading)`, and merges in the priorities from your CSV files. Entries you have already reviewed are marked
as known; unseen entries remain pending.

It then reorders your new cards based on their [score](./user_guide/usage/recalc.md#scoring-algorithm) so that you see the
easiest cards (the ones with the highest priority among the remaining pending entries) first. PrioritySieve only
reorders new cards; it doesn’t touch the scheduling of cards you have already learned. You can run Recalc as often as
you like to keep learning in a [1T](./user_guide/glossary.md#1t-sentence) fashion.

This guide is an attempt to explain how PrioritySieve functions as simply as
possible. Feel free to skip straight to [Installation](./user_guide/installation.md), [Setup](./user_guide/setup.md),
or [Usage](./user_guide/usage.md), and
refer back to
the [Glossary](./user_guide/glossary.md) whenever clarification is needed. 
