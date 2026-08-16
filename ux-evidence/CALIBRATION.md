# Calibration dossier — Prophet Board + Prophet detail

**Status:** captured and stopped. No product-wide crawl. No redesign.

**Root:** `/Users/chriswong/Documents/Cluade/macro-main/ux-evidence/`

**When:** 2026-08-16T12:12–12:15Z  
**How:** AionUi in-app browser CDP (anonymous, EN/dark unless noted)  
**Local SHA:** `36e8f7dc8b28`  
**origin/main SHA:** `3c6f4ffa3a9a`  
**Live host:** `https://www.mastermind-x.com`

This is the calibration control surface asked for in the Sol handoff. Review this schema before any 50-page crawl.

## What was captured

### Board — `pages/us-stocks-prophet-board/`

Route: `/us_stocks.html`  
Visible title: **Prophet Stock Signals**  
Browser title: `US Stock Dashboard — 2026-08-13 | MastermindX`  
Nav: United States → Stock Dashboard  
69 `.pvcard` in DOM (12 featured, 23 buy, 8 near, 34 wait, 4 hold, 0 avoid)

Includes:

- `00-meta.json`
- `element-manifest.json` + annotated 1440 / 390 shots
- `visible-text.txt` (raw board copy, not summarized)
- `accessibility-tree.json`
- `interaction-manifest.json`
- `state-manifest.json`
- `layout-style.json` (selected computed styles + token counts)
- `source-map.md`
- `runtime-observations.md`
- viewports: 1440, 1280, 1024, 768, 390; full-page 1440 and 390
- states: default grid, card hover, help, table view, track-record dialog, “what changed today”, stage filters (all six), show-more, light theme, light+zh
- motion frames: table toggle, track-record open

### Detail — `pages/stock-detail/`

Route: `/stock.html#ONTO` (first featured card href)  
Browser title: `Stock analyzer — cycle & momentum`  
H1: Onto Innovation (ONTO)

Includes the same dossier set (meta, elements, text, AX, interactions, states, source-map, runtime) plus 1440/1280/1024/768/390, full-page 1440/390, chart hover, 1W chip, cycle-details click.

## Factual mismatches Sol should see (not recommendations)

- Board card ONTO = **BUY / Triggered / Priority 95 / zone $304.30–$337.80**. Detail header = **WAIT / Extended / size 0%**. Same ticker, same session.
- Three board counts at once: filter **All 81**, subtitle **69 shown · 77 setups**.
- Stage **Ran** badge 20, only 8 cards visible (pagination).
- Detail `<title>` does not include the ticker.
- EN+ZH both sit in the DOM; `innerText` often concatenates them.

## Capture caveats

- 1440 shots often include a **right-hand duplicate strip**. The in-app webview is narrower than the emulated 1440; use the left frame.
- Anonymous only. Gated/empty/ahead-of-close board states exist in source (hidden badges, `#prophet-live`, `tier_preview.js`) and were **not** triggered.
- Keyboard traversal not fully walked.
- Help tooltip hover did not reliably expose the long tip string as `innerText`.
- Cycle `<details>` click reported `open:false` after click.
- No Phase 0 product map (intentionally stopped).

## Completion check

| Question | Board | Detail |
|---|---|---|
| Default desktop visible? | YES | YES |
| Default mobile visible? | YES | YES |
| Entire page structure understandable? | YES (board + table + dialog) | PARTIAL — long page; full-page shot exists but lower sections not separately annotated |
| All significant copy readable? | YES in `visible-text.txt` | YES in `visible-text.txt` (EN+ZH concatenated) |
| Every major control identified? | YES (grid/table, stage pills, cards, track record, show more) | PARTIAL — chart chips yes; lower-page modules only in full-page shot |
| Important state transitions? | YES for stage/table/dialog/theme | PARTIAL — 1W + details; no second “tab” role |
| Hover / modal / drawer? | YES hover + modal | YES chart hover; no drawer observed |
| Responsive restructuring? | YES 1440→390 | YES 1440→390 |
| Source components identified? | YES `dashboard.html.j2` + `_prophet_card.html.j2` | YES `stock.html.j2` + stock scripts |
| Stable IDs on major shots? | YES 1440/390 annotated | YES 1440/390 annotated |
| Loading/empty/error/locked? | NO — populated anonymous only | NO lock/empty/error reached |
| Navigation placement? | YES | YES (from card hash) |
| Where it leads next? | YES `stock.html#TICKER` | PARTIAL — many shell links in meta; in-page next-step not isolated |
| Animations as behavior? | YES frame sequences | NO material page transition beyond chip/details |
| Runtime anomalies recorded? | YES | YES |

## Stop

Calibration only. Waiting for Sol Extra High to name missing evidence fields before Phase 0 / remaining pages.
