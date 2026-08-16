# Runtime observations — stock detail (`#ONTO`)

## Load

- Navigated to `https://www.mastermind-x.com/stock.html#ONTO`
- Title stayed `Stock analyzer — cycle & momentum` (ticker not in `<title>`)
- H1: Onto Innovation (ONTO), live-ish price $331.71
- As-of line: data through 2026-08-14
- Board card on the same day showed ONTO as **BUY / Triggered / PRIORITY 95 / ZONE $304.30–$337.80**
- Detail header showed **WAIT / Extended — wait for a pullback / Suggested size 0% / BOTTOMING**
- This is a **source-vs-surface mismatch** between board verb and detail “Act now?” verb for the same ticker on the same capture day

## Interactions

- Chart `1W` chip clicked; screenshot saved. URL hash remained `#ONTO`
- `<details>` “Cycle & timing detail” clicked; CDP reported `open: false` after the click (toggle may have closed an already-open node, or the click did not stick). Screenshot saved regardless
- No `[role=tab]` list found. Timeframe chips are buttons, not tabs
- `.lock-cta` / paywall **not present** on this anonymous load
- Search bar on detail had a single character leftover (`I`) from prior session chrome — not set by this collector

## Accessibility / copy

- `document.body.innerText` concatenates EN and ZH for many headings (“United States美国”, “Anticipation — …预判 — …”) because both `l-en` and `l-zh` nodes exist in the DOM
- Mega-menu column H2s appear before the page H1 in heading order

## Network

- Same aborted-load noise as the board capture during navigation
