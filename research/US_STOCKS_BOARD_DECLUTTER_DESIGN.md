# US Stocks Standout Board — Declutter Design v2 (Fable-adjudicated)

**Date:** 2026-07-05 · **Scope:** `templates/dashboard.html.j2` (mode="stocks", standout section
~L2773–3240) + its CSS, `templates/theme.js`, `templates/theme.css`. **NO builder-logic changes**
(`build_stock_library.py` untouched; artifact JSON byte-identical).
**Status:** ADJUDICATED — red-teamed by a 3-lens Opus panel (contracts / UX / implementation-risk);
all BLOCKER + MUST-FIX findings resolved below. Build may proceed against this spec.

## 1. The measured problem (2026-07-05 live render, 19 cards)

- Per card: median **27 named info elements** (max 36), 7–13 tooltips averaging 33 words; the
  section's tooltips total **6,450 words**. Vocabulary: 43 distinct semantic terms.
- **Verdict conflict:** one card (AEE) simultaneously shows "Entry armed" (green), "Hold — don't
  add here" (orange), "💥 Already moving" (red), and "Neutral — no clear edge". Entry-timing
  information appears in six places per card; "don't chase" in up to four layers.
- Board level: **six** stacked banners render above the first card.
- Root cause: every program wave added its own element; each is individually honest and
  contract-compliant; the aggregate has no information hierarchy.

## 2. Design principle

**One question per zone, one verdict per question; ink proportional to power.** At rest a card
answers: (1) what is it, (2) is it worth owning — ONE edge line, (3) can I enter today and at what
price — ONE entry line + one-clause plain-language reason, (4) anything urgent — a strict
exception-chip row. Everything else stays computed, emitted, server-rendered, and **available**
in a per-card details expander. Convergent with the ratified W6-US "two glyphs, never one fused
score" doctrine.

**Entry authority (adjudicated wording):** `entry_signal.status` becomes the *sole at-rest entry
surface* **by display choice** — the builder does NOT arbitrate between it and the alignment
`entry_tier` (W6-US fix 7 reconciles row `urgency` only). The alignment tier tag and reason detail
move to the expander; a one-clause reason stays inline (plain-language house law).

## 3. Board level: 6 banners → 1 context strip + contract rows

**Context strip** (one row of inline tokens, tooltips carried over verbatim):
`🌀 Short-gamma` · `🎯 Selection pays` · `19 names · 7 sectors` (tooltip carries "effective
bets") · `✓ Rotation leader intact` + visible `display-only · G6a context` label · earnings-cal
token.

Adjudicated amendments:
- **lane_counts pill row is KEPT** (distinct P2.4 §4.2 element, L274–284 — NOT absorbed by
  sub-headings). It renders as today's `.lane-counts-row`; CSS may tighten margins so it sits
  compactly under the strip, DOM element intact.
- **Earnings-blackout:** suppressed-names state (`count>0`) stays a full-width disclosure line
  naming tickers (W1.5). Stale-store state stays **warn-styled** (dashed-warn token, never a
  neutral one) — it discloses a fail-open safety gate.
- Worst-case board header = strip + lane-counts row + one warn disclosure line. Still ≤3 compact
  rows vs today's 6 banners.

## 4. Per card

### At rest
| Zone | Content |
|---|---|
| Head | ticker · sector/theme spotlight chip · price (`.nb-px[data-sym]` stays here — live.js) |
| Sub | name · GICS-when-theme-differs · off-52w-high |
| Spark | sparkline |
| EDGE line | score pill (band-colored) + `Edge NN%ile` + `c.verdict` text — one line. (Build-time W6-US RAISE invariants guard exactly this verdict/band pair; at-rest EDGE must render those same fields — assertion added to test plan.) |
| ENTRY line | state dot + `entry_signal` status + buy zone `$lo–$hi (−N.N%)`; **one-clause reason** beneath (single line, ellipsized; full reason in expander) |
| Exception chips | strict admission — see below |

**No at-rest stat footer.** α, #sector-rank, ⚖ size-mult, neutral ext, 200DMA±, SUE/revisions
etc. all live in the expander (UX ruling: quant shorthand fails the flagship persona).

### Exception-chip row — admission rule
A chip renders at rest iff it is (i) minority-frequency board-wide AND (ii) an actionable
veto/caution or a validated gate/contract-mandated chip:
- `⚠ Caution N` (+ popover, intact),
- `⏳ Anti-chase watch` (validated safety warning),
- `Sector capitulating`,
- `📅 Earnings Nd` (W1.5, ≤7d),
- `ext N.N ⚠` — **warn form only** (>2.0),
- `↗ Shaken-recovery`,
- **`💥 Moving — don't chase`** (NEW promotion, adjudicated from UX finding 2): renders when
  (vol-squeeze state ∈ {FIRED_UP, EXPANSION} OR `alpha_entry == 'momentum'`) AND
  `entry_signal.status` is NOT already ∈ {extended, topping, exit, avoid, blocked} — i.e. exactly
  when the at-rest entry line would otherwise read constructive while the move already fired.
  Template-level conditional on existing fields; no builder change.
- sig-gate tier badge **kept as a chip** (5/19 today = minority; the validated buy gate is the
  highest-value chip) **with its nested `prov-flag` repaint disclosure intact at rest**,
- `⚡ Coiled(-FIRE)` **kept** (contract: the chip is the canonical delivery mechanism; 1/19 today).

### Demoted to the details expander (server-rendered, CSS-collapsed, whole elements intact)
Alignment row + tier tag + full reason · cycle-day bar + window · conviction axes + basis chips ·
SUE · revisions · insider · demand-desk · pulse-heat · liquidity tier · valuation band · verifier
row (GEX/IV/squeeze — squeeze also surfaces at rest via the 💥 exception rule) · hold detail
(days basing · invalidation; hold *state* reads through the ENTRY line at rest) · `200DMA±` chip ·
neutral-form `ext_z` chip · α z-chip · sector rank · ⚖ size · momentum/α-laggard chips ·
stop guidance · name-specific notes.

**Contract ruling (P2.4 §4.2, adjudicated):** chips "on every row" are satisfied by
DOM-present-but-collapsed **whole chip elements** (contracts-lens primary-source ruling); the
`.nb-extz` chip keeps its exact single-line `data-tip` (BC-2 line-scoped allowlist: `"P1.3
validated"` must stay on one physical line). Never split or re-wrap a `data-tip` across lines;
move whole elements only. PR body documents this ruling for registration review.

### Board-level triage cue (flagship gap, UX finding 9)
Cards with `score_edge ≥ 0.8` AND `entry_signal.status ∈ {buy_now, partial}` get a subtle accent
ring (existing tone vars) — a pure visual conjunction of two already-displayed calibrated values;
no new signal, no re-ordering, order stays frozen.

### Lane: chip → structure
Per-card lane chips are removed; cards render grouped under **featherweight lane sub-headings**
(`Bottoming · 7` …, tiny muted label, not a heavy break), always rendered when a lane is
non-empty (no ≥3 threshold — contract fidelity over choppiness aesthetics), with the per-lane
left-border accent kept. This *builds* P2.4 §4.2's lane-sub-heading element (never shipped —
net-additive DOM, honestly stated) while deleting the 19/19 chip class. Stable partition of
producer order; within-lane order unchanged (guarded by `test_us_board_lanes.py` alpha-desc test +
an explicit pre/post per-lane ticker-sequence assertion — AC-1 tests set membership only, and is
still run for that).

## 5. Mechanics (risk-lens resolutions — all BLOCKERs)

- **Card restructure:** `<a class="nbcard">` → `<div class="nbcard">`; head zone keeps
  `<a href="stock.html#{{ticker}}">` **verbatim** (Terminal interceptor, theme.js L143–151, keys
  on `a[href]`). A delegated click handler on the grid makes the card *body* trigger the head
  anchor's `.click()` (re-entering the interceptor naturally), except on interactive elements
  (`.nb-cau-btn`, `.nb-more-btn`, `.nb-more`, `.nb-spot[data-href]`). "Click a card" header copy
  stays true. This also fixes today's invalid HTML (button nested in anchor).
- **CSS de-qualification:** every `a.nbcard`-qualified selector in BOTH
  `templates/dashboard.html.j2` (L527, 532, 533, 746–747 incl. the `:has(.nb-cau…)`
  overflow-visible rule that lets the Caution popover escape) AND `templates/theme.css` (L184,
  186, 195, 679) becomes bare `.nbcard` (still matches CN/HK anchor boards). Add explicit
  `.nbcard{color:var(--text)}`. Screenshot-diff china/hk/us boards.
- **Expander:** NEW delegated handler mirroring the `nb-cau-btn` pattern (stopPropagation,
  tap-toggle) — NOT `data-showmore-rows` (grid-level whole-card reveal; wrong mechanism).
  Trigger = a full-width slim bottom bar (`▾ details` / `▴ less`, l-en/l-zh spans,
  `role="button"`, `aria-expanded`, ≥32px tall on mobile) AND the ENTRY line is a secondary
  trigger (click the gauge → why). Event delegation on the grid (robust to showmore-hidden
  cards). On ≤680px, expanded card gets `grid-column: 1 / -1` (full-width breakout).
- **nb-spot dead link fix:** wire a small delegated `data-href` handler in theme.js
  (stopPropagation + navigate) — today the chip's `data-href` is dead UI saved only by the outer
  anchor; post-restructure `role="link"` would be an a11y lie otherwise.
- **theme.js/theme.css source of truth** = `templates/`; render overwrites `site/` copies.
- No new `render()` kwargs (kwarg-collision gotcha not triggered); `render_macro_fast` uses
  `write_page` so the data-base shim is injected.

## 6. What does NOT change

Builder logic, admission gates, ordering, `us_standouts.json` schema/fields — byte-identical.
Top-setups table, outcomes strip (+ survivorship disclosure), watch strip — untouched in v1.
All allowlisted "validated" tooltip strings — verbatim, single-line. Bilingual l-en/l-zh +
data-tip-en/zh everywhere; no CJK/`t()` in `title=`. `us_stocks_v2.html` shadow — untouched.
macro.html body — untouched (standout section is `mode != 'macro'`-gated; only shared CSS moves,
covered by screenshot diffs).

## 7. Verification checklist (build phase MUST run all)

1. `python -m scripts.render_macro_fast` → non-empty us_stocks.html; **rendered ticker set AND
   per-lane ticker sequence identical pre/post** (AC-1 set check + order assertion).
2. `pytest tests/test_us_board_lanes.py tests/test_us_board_outcomes.py
   tests/test_us_board_outcomes_strip.py tests/test_us_board_w3_evidence.py
   tests/test_horizon_firewall.py` (parse test alone is insufficient — lenient Undefined).
3. `python scripts/check_title_i18n.py` and `python scripts/check_validated_claims.py` — the
   latter against BOTH templates and rendered `site/us_stocks.html`.
4. Headless-Chrome at 1400px and 390px: expander opens/closes (keyboard too), Caution popover
   opens un-clipped, card-body click navigates, head-anchor click hits Terminal reroute path,
   `.nb-px[data-sym]` present, 19 cards, lane sub-headings present, exception chips ≤3 on the
   median card.
5. Screenshot-diff china.html + hk.html boards (shared theme.css).
6. Grep rendered HTML: every demoted chip class still DOM-present (`.nb-extz`, `.nb-200dma`,
   axes, verifier chips…) inside `.nb-more`.

## 8. Predicted outcome

At-rest per-card elements: ~27 → **~11** (head 3, sub 3, spark, EDGE line, ENTRY line + reason,
0–3 exception chips). Board header: 6 banners → strip + lane pills (+1 conditional warn line).
Vocabulary at rest: 43 → ~15 terms. Zero engines deleted; zero fields dropped; every demoted
element one tap away; all disclosures (prov-flag, caution, anti-chase, earnings, stale-gate)
still at rest.
