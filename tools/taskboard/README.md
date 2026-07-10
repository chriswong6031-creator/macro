# Slate — personal task boards + Brain

A single-user, local-first, responsive web app: Trello-style task boards plus a
"Brain" for writing down learned truths. No accounts, no network, no teams:
everything lives in your browser (state in localStorage, attachments in IndexedDB).

## Use it

Two ways, same app:

- **Web app (recommended)** — double-click `Start Slate.command` (or run
  `python3 -m http.server 8123` in this folder) and open http://localhost:8123.
  Served, Slate is a full PWA: install it from the browser's install button for a
  standalone window, dock/home-screen icon, and offline support via a precached
  service worker (cache rolls automatically whenever the sources change).
- **Single file** — double-click `Slate.html`. Same app, no install/offline layer.

Data is browser+origin-scoped, so the two forms keep separate data — pick one, or
move between them with Export/Import. Two platform caveats: on iOS, a
home-screen-installed PWA has its own storage container separate from Safari
(export/import to move data in), and the PWA install splash/title bar always uses
the light color — web manifests can't follow the in-app theme.

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
- **Command palette** — ⌘K / Ctrl+K (or the magnifier) searches everything at once:
  cards (titles, descriptions, tags — done ones too), boards, workspaces, Brain notes
  and topics. Enter jumps straight there — switching workspace/view, scrolling to the
  board or pane, pulsing it, and opening the right editor. Typed commands too:
  new board, write a note, go to views, toggle dark mode, tidy, export.
- **Backups** — gear menu → Export/Import backup (single JSON including attachments
  and the Brain).
- **Responsive** — phone/tablet friendly: bottom-sheet modals, compact topbar,
  double-tap to create, long-press to drag cards, drag boards by their header.
- Light/dark theme, undo toasts for every destructive action.

## Files

- `index.html` + `css/` + `js/` — modular source
- `manifest.webmanifest`, `sw.js`, `icons/` — PWA layer (served form only)
- `Start Slate.command` — double-clickable local server launcher (macOS)
- `build_standalone.py` — stamps the service-worker cache version from a source
  hash, then inlines everything into `Slate.html` (stripping the PWA layer)
- `Slate.html` — the shippable single-file app (regenerate after editing source)
- `verify_playwright.py` — end-to-end test suite (run against any of the 3 modes)

Data is browser+origin-scoped: the `file://` copy and a served copy keep separate data.
Use Export/Import to move between them.
