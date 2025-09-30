# Card Handling

![card-handling-tab.png](../../../img/card-handling-tab.png)

This is where you can make PrioritySieve really efficient. PrioritySieve sorts
your cards based on how well you know its content; the more you know, the sooner the card will be shown. The downside is
this is that it might take a long time before you see a cards with any unknown entries, i.e., you don't learn anything
new.

To overcome this problem and speed up the learning process, we can use the options found here.

**When Encountering Cards (skip = bury)**:

* **Skip cards that have no unknown entries**:  
  If AnkiMorph has determined that there are no unknown entries on the card, then it will be buried and skipped.
  

* **Skip cards that have unknown entries already seen today**:  
  If you have already studied a card earlier today with the same unknown entry, then any subsequent cards with that
  unknown entry will be buried and skipped, which reduces the need to [Recalc](../../usage/recalc.md).
* **Show notification "Skipped x cards"**:  
  After cards are skipped, a notification in the lower left corner displays how many cards were skipped and for what
  reason. If you don't want to see this notification, you can uncheck this option.

  ![skipped_cards.png](../../../img/skipped_cards.png)


**On Recalc**:
* **When a new card has no unknown entries:**  
  You can choose how PrioritySieve handles these cards: either move them to the end of the new queue (default) or suspend them outright. This ensures you always focus on unseen material first.

* **Shift new cards that are not the first to have the unknown entry**:  
  This option is an alternative to the [skip options](skip.md) that are only available on desktop, potentially making it
  easier to study new cards on mobile.  
  <br>There are two parameters you can adjust:
    * How much to shift/offset the due of the affected cards
    * How many unknown entries to perform this shift/offset on
  <br>You can also optionally provide a deck name. When set, cards belonging to that deck
  will be kept as the "first" card for their morph (i.e. not shifted) if one exists, even if
  another deck has an earlier due card.

  <br>Here is an example card order **without** this option activated:
  <div class='morph-variation'>
  <table>
  <tr>
      <th style="text-align: center">Card ID</th>
      <th style="text-align: center">Unknown Entry</th>
      <th style="text-align: center">Due</th>
  </tr>
  <tr>
      <td>Card_1</td>
      <td style="text-align: center">break</td>
      <td>50 001</td>
  </tr>
  <tr>
      <td class="morph-variation-selected_cell">Card_2</td>
      <td class="morph-variation-selected_cell" style="text-align: center">break</td>
      <td class="morph-variation-selected_cell">50 002</td>
  </tr>
  <tr>
      <td>Card_3</td>
      <td style="text-align: center">walk</td>
      <td>50 003</td>
  </tr>
    <tr>
      <td class="morph-variation-selected_cell">Card_4</td>
      <td class="morph-variation-selected_cell" style="text-align: center">walk</td>
      <td class="morph-variation-selected_cell">50 004</td>
  </tr>
  </table>
  </div>

  <br>Here are the same cards but with this option activated (due_shift = 50 000, first_morphs = 2):
  <div class='morph-variation'>
  <table>
  <tr>
      <th style="text-align: center">Card ID</th>
      <th style="text-align: center">Unknown Entry</th>
      <th style="text-align: center">Due</th>
  </tr>
  <tr>
      <td>Card_1</td>
      <td style="text-align: center">break</td>
      <td>50 001</td>
  </tr>
  <tr>
      <td>Card_3</td>
      <td style="text-align: center">walk</td>
      <td>50 003</td>
  </tr>
    <tr>
      <td class="morph-variation-selected_cell">Card_2</td>
      <td class="morph-variation-selected_cell" style="text-align: center">break</td>
      <td class="morph-variation-selected_cell">100 002</td>
  </tr>
    <tr>
      <td class="morph-variation-selected_cell">Card_4</td>
      <td class="morph-variation-selected_cell" style="text-align: center">walk</td>
      <td class="morph-variation-selected_cell">100 004</td>
  </tr>
  </table>
  </div>
  <br>
