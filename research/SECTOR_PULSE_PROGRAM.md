# Sector Pulse Program — rotation velocity as a first-class, shared signal

*Program doc. Started 2026-07-03. Orchestrated by Fable; waves executed by Opus/Sonnet subagents.*

## Why this program exists (the brain dump, organized)

The user observed three distinct problems that share one root:

1. **Healthcare mislabel** — `us_sector_health` / `big_pharma` ranked #3/#5 of 46 themes
   (emerging, all four timeframes' MACD up, fresh monthly cross-up, above a rising 200d,
   clean-entry texture true) yet rendered "Downtrend confirmed across timeframes" / AVOID,
   got demoted to HOLD, and vanished from the "What to act on now" board. **Verdict: the
   dashboard was objectively wrong — a three-leg bug cluster, fixed in W0 (PR #1166).**
2. **Rotation intel is trapped in one page** — "5-Day Theme Rotation" and "Owns the
   advance / In the decline" are among the best reads on the site, but they lived only in
   the baskets-page payload. No other engine (stock scorers, Mastermind bot, Terminal)
   could ask "which sectors are heating up, and how fast?"
3. **Mastermind buys without entry discipline** — no confluence gating, no extension
   check, chases highs. It should be a *consumer* of sector rotation state.

Shared root: **sector rise/deterioration velocity was computed but not productized.**
Engines each re-derive fragments (spotlight tilt, basket-risk de-risk, group_context)
from static label/reco snapshots; none see velocity (rank momentum, heat tiers), and
external repos see nothing at all.

## Wave plan

### W0 — Truth first: fix the mislabel bug cluster ✅ (PR #1166, merged)
- `btc_mtf.confluence_verdict` was **monthly-blind for every basket** (read the BTC-only
  `ME` key; baskets carry `M`) → long governor set by cycle-shape penalties alone.
- TOP WATCH / BOTTOM WATCH (daily-driven warnings) forced `short_sign=-1` against an
  up tape → now defer to a decisive D+3D tape; DECLINE/ROLLING OVER stay authoritative.
- `theme_scoring._long_sign` now prefers the price-vs-200d proxy — the definition the
  phase-0 drawdown gate was actually validated on — over the confluence governor, in
  every region.
- Honesty guard: "confirmed across timeframes" prose can never contradict the per-TF
  reads on the same payload.
- Result (verified live): healthcare → dominant/ACCUMULATE, act-now Buy; risk-side
  labels (uranium/nuclear/energy) unchanged.

### W1 — Sector Pulse data product (`engine/sector_pulse.py` + `site/basketdata/sector_pulse.json`)
Canonical read API + persisted artifact: per-theme label/reco/score/rank plus
**rank_delta_1d/5d/20d, score deltas, heat tier (heating/hot/cooling/broken/idle)**,
clean-entry, momentum, long_sign; ticker→theme mapping (`for_ticker`). Velocity computed
from the existing daily signal archive (point-in-time, no new store). Schema-versioned
JSON so Mastermind and the Terminal ingest it.

### W2 — Consumers
- **a) Per-name intel export + us_stocks cards**: sector-pulse heat rides into the
  per-ticker intel JSONs (which the Terminal already pulls via `ingest/pull_macro_intel.py`)
  and a display chip on stock cards. Display-only first — spotlight *tilt math* is
  validated; heat may not bind scoring until it passes its own kill-test.
- **b) macro.html front page**: compact sector-heat strip (top heating / top cooling),
  fed from sector_pulse.json via the MACRO_DUMP_VM view-model so fast re-render works.
- **c) Terminal**: display wiring on the pulled intel fields.
- **d) Mastermind**: consumes sector_pulse.json in its entry path (see W3).

### W3 — Mastermind entry discipline (independent plan, Mastermind repo)
Audit of the buy path with file:line evidence; `research/ENTRY_DISCIPLINE_PLAN.md` with
an Entry Quality Officer stage (sector-tailwind gate, chase-guard extension veto,
staged-entry ladders, patience queue), advisory-first with ledger-graded validation
before anything binds. Aligned with the existing mastermind-fix masterplan.

### W4 — Scorecard upgrades on the baskets pages
5-Day Theme Rotation and Owns-the-advance/In-the-decline get velocity + persistence
context (multi-horizon rank deltas, streaks, heat chips), promoted visually. Honest
framing preserved (descriptive vs backtested grades).

### W5 — Re-render, cross-page audit, ship
Scoped re-render, verify healthcare end-state on baskets/basket-detail/sector pages,
tests + audits green, PRs squash-merged same-day.

## House rules this program honors
- **Validate-before-weight**: no new signal binds a scored decision without its own
  kill-test; everything ships display-only/advisory first.
- **Additive, never fatal**: every new leg degrades to None/empty.
- **Honest labels**: descriptive reads must never render as forecasts; prose must never
  contradict the data on the same card (the W0 honesty guard enforces one instance).
- **Point-in-time**: velocity comes from the append-only signal archive, not from
  recomputed hindsight.

## Open follow-ups (candidates for future waves)
- ~~Backfill heat-tier history from basket OHLCV RS series and kill-test heat as an
  entry-timing overlay (does "heating" lead 21d relative return / shallower drawdown?)~~
  **DONE — W6 below. Verdict: heating/hot/cooling REFUTED as entry timing; broken
  confirmed as a risk timer. Tiers stay display-only; grades now shipped in the payload.**
- Region variants (cn/hk/ca) of sector_pulse once the US shape settles.
- Subsector confluence + subsector rotation (RRG velocity) folded into the same pulse
  schema so Mastermind reads ONE artifact for "what's rising, how fast".
- Cross-page consistency audit: any surface that still renders a trend/label contradicting
  per-TF data (basket detail pages, sector pages, china/hk variants of the confluence).

## W5 audit outcome (2026-07-03)

11-agent adversarial workflow (4 dimension auditors → per-finding refuters):
- **Honesty**: all 46 themes clean — no grade contradicts unanimous per-TF signs; no
  constructive clean-entry theme excluded from act-now. Healthcare/big_pharma verified
  dominant/ACCUMULATE, act-now Buy, heat hot/heating on the rebuilt page.
- **i18n/UX**: title-attribute guard + nav-gap guard pass; dual-span coverage complete.
  Fixed post-audit: `.heat-pill.hot` hardcoded `#f59e0b` → `var(--orange)` (both desk
  copies); `actNowPulseBar` BASE-variable drift in the US inline copy.
- **Code review**: fixed `ME or M` loose-truthiness fallback → explicit None check
  (preserves empty-dict ME semantics for short-history BTC).
- **Contracts**: producer stockdata block ⇄ Terminal intel/v1 trim ⇄ heat vocabulary all
  consistent; Terminal staleness gate verified. CRITICAL find: Mastermind's
  `entry_quality.annotate()` was never handed theme_id/pulse (cooling_sector verdict
  unreachable) — fixed on the Mastermind branch by injecting both at the phase2 call site.

Shipped: #1166 (W0 fix), #1168 (W1 pulse), #1170 (W2 consumers), #1172 (W4 scorecards),
plus this audit-fix PR. Sibling repos: charting-app `feat/sector-pulse-intel`,
Mastermind `fable/entry-discipline` (both local-only branches — no remotes).

## W6 — heat-tier phase-0 kill-test (2026-07-04)

**Question**: do the heat tiers carry a measurable forward edge, or are they texture?
Pre-registered claims, all vs the same-day **idle** baseline at 21d: heating/hot →
higher relative return OR shallower drawdown; cooling/broken → deeper drawdown.

**Method** (`scripts/calibrate_sector_pulse_heat.py`): rank series reconstructed
point-in-time from RS-derived proxy scores on the 27y SPDR sector panel (the
calibrate_baskets GO/NO-GO substrate); heat classified by the SHIPPED
`sector_pulse._heat_tier` (imported, never re-implemented) at exact 5-session deltas.
Paired same-day tier-vs-idle differences, HAC t (floor 2.0) + BH-FDR q≤0.10 across the
6-cell panel, split-half 2013, ±1-rank board-width sensitivity (±3 of 11 ≈ 27% of the
proxy board vs 6.5% live — the literal thresholds under-fire on the proxy). Live ~3y
basket lane (descriptive) + accruing signal-archive lane (rerun bar ≥90 sessions)
as confirmation channels. Trial ledger family `sector_pulse_heat` (budget 16).

**Verdict** (`data/strategies/sector_pulse_heat.json`):
- **heating — REFUTED**: rel21 vs idle +0.01pp (t 0.07, n 420 days); the drawdown leg
  is *inverted* — heating themes drew DEEPER 21d drawdowns than idle (−0.35pp, t −2.38).
  Velocity-chasing, measured. Same story at the ±1 sensitivity.
- **hot — REFUTED**: no rel edge (t −0.88); drawdown leg mildly inverted (t −2.15).
- **cooling — NOT CONFIRMED** (t −0.75): the rank-drop leg dilutes the *validated*
  fading label into noise — the label-level fading/deteriorating grades remain the
  backtested risk reads.
- **broken — CONFIRMED risk timer**: −0.41pp deeper dd21 vs same-day idle (t −4.34,
  BH q≈0), consistent with the deteriorating label's baskets_calibration verdict.
- Live 3y lane: nothing significant (hot rel +8.1pp at t 1.9 on 62 hindsight-curated
  days — context only). Archive lane: 10 snapshots, 0 gradeable 21d windows yet.

**Shipped**: tiers stay display-only (validate-before-weight honored); the payload now
carries the grade the way `theme_scoring._signal_strength` does — per-row
`heat_strength` (grade/kind/measured/t/en/zh, with the chase-caution text on the
inverted heating read), top-level `heat_grades`, and `pulse_heat_grade` in the
theme_intel merge. `_heat_strength` reads only the verdict block; artifact absent →
None everywhere (honest-descriptive fallback). Re-run the script once the archive
lane matures (≥90 sessions, ~2026-11) to confirm/deny on the real shipped snapshots.
