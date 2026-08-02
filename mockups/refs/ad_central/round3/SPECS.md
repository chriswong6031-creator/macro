# Round 3 — locked specs (2 concepts × 2 sizes)

Governed by `research/AD_MASTER_PAPER.md` (§0 gates) + `research/AD_ROUND3_FLAGSHIP_BRIEF.md`
(strategy, §3 operator rulings 2026-08-02). Copy below is LOCKED — pixel changes may not
reword anything without re-opening the brief.

## call — the flagship (dark plate + candle field)

| | |
|---|---|
| class | category × cadence |
| canvases | 1200×628 (X website card, primary) · 1080×1080 |
| kicker | MARKET INTELLIGENCE DESK (pill on 628 · catline on 1080) |
| launch flag | `LAUNCH — 50% OFF` (violet, brandbar right — ruling 2) |
| headline | `Daily stock signals.` / `Institutional grade.` (gradient on line 2) |
| subline | `Buy, wait or avoid — every stock graded 0–100, with an exact entry zone. Updated every trading day.` |
| chips | Sector rotation · Macro dashboards · Advanced charting · AI analyst (2×2) |
| hero | SBUX Prophet card — BUY · $104.27 · EDGE 89 · stage Ready · ZONE $102.60–$104.30 · Jul 2 · `demo` (landing showcase prophet.showcase/v2, 2026-07-02 board — a real graded call) |
| support | gauge card 57 · Mixed tape · "Watch, don't chase." (1080 only; dropped on 628 — it collided with the flag) |
| offer | 7-DAY FREE TRIAL / ~~$149~~ $75/mo · 50% OFF · ANNUAL / Try Pro free |
| micro | `Research tools — not investment advice · 2,000 founding memberships · mastermind-x.com` (AG-8 ON: hero quotes an entry zone) |

## desk-rotation — the support (paper mode)

| | |
|---|---|
| class | pain flip / breadth |
| canvases | 1200×628 · 1080×1080 |
| kicker | SECTOR ROTATION DESK |
| launch flag | `LAUNCH — 50% OFF` |
| headline | `See the rotation` / `before your` / `watchlist does.` (gradient on "rotation") |
| subline 628 | `Every theme sorted into four plain-word lanes — updated daily.` |
| subline 1080 | `Buy now, Almost ready, Take profits, Stand aside — every theme, sorted daily.` |
| chips 628 | 34 themes · Macro dashboards · Institutional flow · Daily signals (2×2) |
| chips 1080 | Macro dashboards · Institutional flow · Daily signals (one row; "13F" banned — ruling 5) |
| hero | four-lane board (round-2 vetted demo rows: Big Pharma 69 · US Energy 71 · Industrials 58 · Payments 64 · Defensives 57 · Cybersecurity 72) |
| signature (1080) | the Payments row changing lanes — ghost trail, flight arrow, lifted chip (salvaged from R2 rotation, reviewer-vetted) |
| support (1080) | VCTR Prophet sliver (zone in a background sliver ⇒ AG-8 not triggered) |
| offer | same standard block |
| micro | `2,000 founding memberships · allotment shrinks daily · mastermind-x.com` |

## Build notes / defect log (all four PNGs eyeballed at full + thumbnail size)

- Round-2's four recurring defect classes all appeared in draft renders and were fixed
  by looking, not by the renderer: bottom clip (all three new layouts), auto-wrap
  breaks ("0–/100", "plain-/word" — now `white-space:nowrap`), chip widow rows
  (max-width must include the 2×`--pad` side padding — content = max-width − 96/128),
  non-atomic occlusion (offer bar top edge cutting the SBUX ZONE row on 1080 — hero
  scale reduced .74→.70).
- 628 headlines sit at 48–52px vs round-2's 58px precedent — a deliberate trade for a
  complete offer block + launch flag + 4 chips; verified readable at thumbnail scale.
- The launch flag owns the brandbar's right edge; on 628 the category line rides as a
  brandbar pill, on 1080 as a catline under the brand (widths don't fit three-up).
