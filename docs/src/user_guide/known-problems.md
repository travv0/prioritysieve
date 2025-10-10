# Known Problems

<details>
  <summary style="display:list-item">Undoing “Tag as known”</summary>

> There is an edge case when you mark several cards as known without answering anything in-between. The first undo may not
> revert the tag immediately. Simply answer the next card normally—after that you can undo twice and both cards will be
> restored.

</details>


<details>
  <summary style="display:list-item">Redo is not supported</summary>

> Redoing, i.e. undoing an undo (Ctrl+Shift+Z), is a nightmare to handle with the current Anki API. Since it is a rarely
> used feature, it is not worth the required time and effort to make sure it always works. Redo _might_ work just fine,
> but
> it also might not. Use it at your own risk.
</details>

