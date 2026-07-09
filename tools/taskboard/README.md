# Slate — personal task boards + Brain

A single-user, local-first, responsive web app: Trello-style task boards plus a
"Brain" for writing down learned truths. No accounts, no network, no teams:
everything lives in your browser (state in localStorage, attachments in IndexedDB).

## Use it

Open `Slate.html` (the bundled single file) directly in a browser — double-click it —
or serve this folder and open `index.html`:

```bash
python3 -m http.server 8123   # then open http://localhost:8123
```

## What it does

- **Workspaces** — separate spaces for work / life / anything, switched from the top-left name.
- **Spatial canvas** — boards float on a dot-grid desk. Drag a board by its header to move it
  anywhere; drag empty canvas to pan; **double-click empty canvas to create a board**;
  press **Tidy** to snap all boards into a clean grid ordered by where they sit.
- **Cards** — click *Add a card* for a title (description optional), Enter for rapid entry.
  Drag cards to reorder or move across boards. Click a card to expand it: color, tags,
  optional due date, description, attachments. Click outside to close — edits autosave.
- **Complete ritual** — click a card's open circle: the check draws, the card folds away into
  the board's `n done` ledger. Expand the ledger to restore or clear.
- **Attachments** — drop images/files onto any card (collapsed or expanded). Images show as
  thumbnails (click for a lightbox), files as chips (hover shows the name, click opens/downloads).
- **Brain** (topbar switcher) — a two-part notebook for personal learned truths:
  - **Board**: an ephemeral capture canvas. Double-click (or the pen button) to write a
    note and file it under a topic — the note is saved into that topic *instantly*
    ("shadow push", with a little fly-to-Library animation), while the card stays on the
    board for the rest of the session. Refreshing or closing wipes the board only.
  - **Library**: permanent panes, one per topic, holding every saved note. Click a note
    to edit, re-file, or delete it (with undo); rename/delete topics from the pane menu.
- **Backups** — gear menu → Export/Import backup (single JSON including attachments
  and the Brain).
- **Responsive** — phone/tablet friendly: bottom-sheet modals, compact topbar,
  double-tap to create, long-press to drag cards, drag boards by their header.
- Light/dark theme, undo toasts for every destructive action.

## Files

- `index.html` + `css/` + `js/` — modular source
- `build_standalone.py` — inlines everything into `Slate.html`
- `Slate.html` — the shippable single-file app (regenerate after editing source)

Data is browser+origin-scoped: the `file://` copy and a served copy keep separate data.
Use Export/Import to move between them.
