# Round 3 — locked specs (2 concepts × 2 sizes) · state R3.3

Governed by `research/AD_MASTER_PAPER.md` (§0 gates + §9 R3/R3.1/R3.2 rulings) and
`research/AD_ROUND3_FLAGSHIP_BRIEF.md`. Copy is LOCKED — pixel changes may not reword
anything without re-opening the brief.

## Shared (all four ads)

- **Headline sub (campaign line, the only approved description):**
  `Institutional-grade signals on every stock — buy, wait or avoid, updated every
  trading day.`
- **Launch flag:** violet `LAUNCH — 50% OFF`, brandbar right.
- **Offer bar:** struck `$149` → `$75/mo` · d-line exactly `LAUNCH SALE` · single CTA
  `Start 7-day free trial`. Nothing else — no 7-DAY cell, no ANNUAL, no THEN FOUNDING
  RATE, no micro-footer, no chips, no on-canvas domain (operator orders, §9 R3.1/R3.2).
- **Rising-tape background** (R3.2c + R3.3): per-ad SVG in `assets/field_*.svg` —
  distinct patterns, all net-up, ~1/3 red candles (all-green ruled unrealistic).
  **Never under text**: fields are confined to illustration zones + empty margins
  (628s read subtler by necessity; the 1080s carry the prominence).
- 628s: brand + flag only. 1080s: small catline (`MARKET INTELLIGENCE DESK` /
  `SECTOR ROTATION DESK`).

## call — flagship (dark plate)

- **Headline (the operator's motto):** `KNOW WHEN TO BUY` / `KNOW WHAT TO BUY` —
  Inter 900 caps, equal measures, gradient on line 2.
- **Illustration — the deck (R3.2a):** four SAME-SIZE Prophet cards in a pyramid 3D
  stack, constant offset, front card highest z. Behind cards expose complete identity
  bars only: `ARLO · NEAR · EDGE 99`, `CPAY · NEAR · EDGE 90`, `REZI · NEAR · EDGE 83`.
  Front card = SBUX: BUY · demo · $104.27 · spark · EDGE 89 · Consumer Discretionary ·
  stages (Ready on) · ZONE $102.60 – $104.30 · Jul 2. Story: "a fresh book of graded
  calls every day — this is today's."
- 628: text column left, deck right, stacked offer (price over full-width CTA).
  1080: motto plate top, deck center band, horizontal offer.

## desk-rotation — support (paper)

- **Headline:** `See the rotation` / `before your` / `watchlist does.` (gradient on
  "rotation").
- **Illustration — two beats (R3.1 §6 + R3.2d):** lane board (BUY NOW: Big Pharma 69,
  US Energy 71 · ALMOST READY: Industrials 58, **Semiconductors 64** · TAKE PROFITS:
  Defensives 57 · STAND ASIDE: Cybersecurity 72) with ONE lifted `Semiconductors 64`
  chip riding the blue arrows into BUY NOW (ghost trail deleted), flowing on into the
  **NVDA card**: NEAR · demo · spark · NVDA / NVIDIA · Information Technology · stages
  (Ready on) · ZONE $199 – $203 · Jul 14. **No EDGE column on NVDA** — only passported
  atoms ship (paper §6 Mastermind-exchange row); we never invent signal data.
  Story: "the sector turns → the stocks inside get graded."
- **Lane de-emphasis (R3.3):** TAKE PROFITS and STAND ASIDE at 65% opacity so the eye
  lands on BUY NOW first.

## R3.4 additions (operator, 2026-08-02 late)

- **call 1080 deck**: true vertical pile — same-size cards, horizontal jitter ≤16px
  (the ±38px diagonal read as different-size sheets and was rejected).
- **Tapes are authored paths now**: the 628's tape is an ARC (bottom-left sweep,
  passing behind the offer, climbing to the deck); the 1080's is a steep column in
  the free right band (x≥800). Both bespoke SVGs in `assets/`.
- **Frosted offer plate** on both call ads: `rgba(17,26,46,.62)` + backdrop blur —
  the tape reads through it.
- **`call-trial` variant pair** (A/B arm): identical creative, NO price — single
  full-width CTA button `7-DAY FREE TRIAL + 50% OFF`. Launch flag retained (operator
  may rule the double 50% redundant).

## Verification state

- 4/4 renders exit-0 via `render.py` (exact sizes, Inter loaded), every PNG eyeballed
  at full + thumbnail; four recurring defect classes clear; banned-string greps clean
  (incl. LAUNCH RATE / LOCKED IN / VCTR / Payments / catchphrase labels).
- Nothing enrolled or published — operator verdicts via `ad_review.record(...)` (H-1).
