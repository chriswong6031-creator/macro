# Calibration v2 — CONDITIONAL PASS follow-up

**Status:** second Prophet-only run complete. Stopped. No Phase 0.

**Collector:** Playwright + installed Google Chrome (`channel=chrome`), real window 1440/1280/1024/768/390, `deviceScaleFactor=1`.  
**Not used:** AionUi in-app webview emulation.

**When:** 2026-08-16T12:57–13:15Z  
**Session:** 3 `mastermind-x.com` cookies copied in memory from AionUi CDP (not written to disk).

## What changed vs v1

| Review item | v2 behavior |
|---|---|
| P0 capture fidelity | Real Chrome viewport; `innerWidth/Height` must match requested ±1px or the shot is deleted. Full-page tiling fails. |
| P0 re-extract | `extract-<viewport>.json` after every size. Boxes are `viewport_box` + `page_box`. |
| P0 verified states | `interaction-manifest.json` has expected vs observed postcondition, pass/fail. Failed states are not named as success. |
| P0 target focus | Chart hover used `#tvbox` (1058×559, canvases 1004×297). Caution used `.pv-cau-btn` hover/focus, not a 29px SVG. |
| P0 independent branches | Each board interaction family used a fresh context + `goto`. |
| P1 coverage | `control-coverage.json` + full interaction records. |
| P1 page structure | `page-sections.json` + full-page and/or viewport-height segments. |
| P1 active language | `visible-text-active-language.txt` + `text-i18n-raw.json`. |
| P1 source parity | `pages/source-parity.json`. |
| P1 decision map | `decision-data-map.json` (ONTO Buy vs WAIT). |
| P2 AX | `accessibility-summary.json` + snapshot (not multi-MB raw CDP tree). |

## Source parity

| Artifact | Status |
|---|---|
| live `us_stocks.html` vs `site/us_stocks.html` | **VERIFIED** (sha256 `7a014653c9d8abe1…`, 1,123,351 bytes) |
| live `stock.html` vs `site/stock.html` | **VERIFIED** (sha256 `b981b9bd3fa9a0ae…`) |
| live `stockdata/ONTO.json` | **UNVERIFIED** — HTTP 401 `x-regwall`; local `site/stockdata/` gitignored |

## Verified interactions (board)

Passed: table view, track-record dialog, all six stage filters, show-more (second attempt), ONTO hover, ONTO caution popover, light theme, ZH.

Failed (recorded, not mislabeled): first show-more helper (no target); then recovered.

## Verified / failed (detail)

Passed: cookied load populated (not lock-cta); 1W chip `class=on`.

Failed (honest):

- `I.detail.cycle` — first `details>summary` in the DOM is not visible (not the Cycle & timing control). `CYCLE_EXPANDED` was **not** claimed.
- `I.detail.chart_hover` — real plot found (1004×297 canvas) but tooltip/crosshair text was **not** verified. Shot kept only as a failed-attempt frame (`detail_chart_hover_1440x1000.png`); do not treat as CHART_HOVER.

## ONTO Buy vs WAIT (evidence only)

See `pages/stock-detail/decision-data-map.json`.

- Board card (baked HTML, VERIFIED = live): verb **Buy**, **Triggered**, **Priority 95**, zone $304.30–$337.80, date Aug 13. Table island on the same page: `conviction_score` 55, `stage` ENTRY, `entry_status` partial.
- Detail (cookied `stockdata/ONTO.json`): **WAIT**, Extended, size 0%. `stock.html.j2` comments: cycle ladder caps the verdict; board rank is context.
- No product judgment.

## Capture self-check (sample)

1440 board default: requested 1440×1000, inner 1440×1000, screenshot 1440×1000, dpr 1. No right-hand duplicate strip (visual check).

390 board default: requested 390×844, inner 390×844, screenshot 390×844. Title of `#us-standouts` scrolled into view (page y≈1774).

## Still missing / do not treat as captured

- Keyboard traversal
- Chart tooltip/crosshair as a verified state
- Cycle `<details open===true>` verified state
- Ahead/behind/closed/empty/gated board badges
- `#prophet-live` visible panel

## Stop

No Phase 0. Waiting for Sol to review this second calibration.
