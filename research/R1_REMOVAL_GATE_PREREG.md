# R1 — Connect-Removal Risk Gate · PRE-REGISTRATION

**Program:** HK & Canada Stocks (masterplan `research/HK_CANADA_STOCKS_MASTERPLAN_BY_FABLE.md`, §6 constitution binding).
**Battery:** R1 — connect-removal (调出) risk gate. Registered by the H-INCL2 exploratory (#1078).
**Author:** Opus 4.8 research wave · 2026-07-03. **Branch:** `hkca-w7pre-r1`.
**This document is committed BEFORE any R1 analysis run.** Hypotheses, constructions, the full trial
list, and gates are frozen here first (§6 discipline: pre-reg-committed-before-runs).

---

## 0. What we already know (the thing this battery must correct for)

The H-INCL2 exploratory (labelled, non-gated, `data/experiments/hincl2_event_study_results.json`)
found that names **removed** (调出) from the SH-HK southbound Connect eligible list underperform HSI
after the event:

- announce-anchored, +20d: mean CAR **−4.67%**, HAC t **−2.83** (n=76 events, K=28 episodes);
- effective-anchored, +20d: mean CAR **−9.07%**, HAC t **−1.42** (same n/K).

(The masterplan brief cites −6.5% / t≈−3.93 for this cell — a horizon/HSI-vintage variant of the same
signal; the sign and rough magnitude are stable across the variants.)

**The confound the exploratory itself flagged: reverse causality.** The semi-annual SSE review removes
names *because* they have already deteriorated — the removal criteria are mechanical rank / market-cap /
liquidity thresholds, so a name that has fallen out of the top ranks over the prior months is exactly the
name that gets removed. A raw removal→underperformance event study therefore mixes (i) any *incremental*
information/flow shock caused by the removal itself with (ii) the *pre-existing* deterioration that
triggered the removal and would have continued anyway. Only (i) is a wireable gate; (ii) is already in the
price and is not caused by removal.

**R1's job:** isolate (i) — the removal effect **incremental to** the deterioration proxy — via a
matched cause-controlled design. NO WIRING regardless of outcome.

---

## 1. Hypotheses

Mechanism (candidate): being removed from the southbound eligible list is a one-off *negative* demand /
information event — mainland southbound holders can no longer add (and, over a wind-down window, must
exit), removing a marginal buyer and stamping a public "no longer top-tier" label. If real and
**incremental**, this predicts negative forward index-relative CAR *beyond* what the name's own trailing
deterioration already predicts.

- **H_REM (gated, one-sided negative):** conditional on the name's own trailing-3M return (the
  deterioration proxy), the removal indicator carries a **negative** incremental forward CAR vs matched
  non-removed names at +5d and +20d.
- **H0 (each horizon):** the removal-indicator coefficient = 0 once trailing-3M return is controlled.

**Pre-registered gated family = the 2 trials {H_REM@+5d, H_REM@+20d}**, one BH-FDR family (α = 0.10),
one-sided (negative) p-values.

**Descriptive / NON-GATED / labelled (Trial b):** the pre-announcement window −20..0 sessions for the
removed names — how much of the total removal underperformance is *already impounded before the
announcement* (i.e. how much of the raw −4.67% is the deterioration that caused the removal, not the
removal itself). Reported as a magnitude, no test, no FDR slot.

---

## 2. Data (frozen)

- **Roster:** `data/hk_connect_roster/roster.parquet`, `action=="remove"` — 330 events, announce dates
  2018-01-12 → 2026-06-29 (verified this session). Anchor = `announce_date` (the notice date). Matches
  the exploratory's roster exactly.
- **Price panel = union** of `data/hk_search/closes_deep.parquet` (157) ∪ `data/hk_stocks/*.HK.parquet`
  `close` (157) ∪ `hk_stocks_ext/*.HK.parquet` `close` (388, read from the ABSOLUTE gitignored/R2 path
  `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/amazing-blackburn-5d2027/data/hk_stocks_ext/`).
  De-dup by ticker preferring the longest non-null close history → ~545-name close matrix, outer-joined
  on the trading calendar. Exact per-store row/date state stamped in the report.
- **Benchmark:** `data/hk/_HSI.parquet` `close` (fresh to 2026-07-03, verified — the refreshed series
  H-INCL2 §3.3 adopted; supersedes the stale `_HSI_deep.parquet` @2026-06-12).
- **hk_stocks_ext coverage caveat (verified this session):** the ext store starts **2023-11-17** (~2.6y
  deep). Most 2018–2023 remove events are studiable only via `hk_stocks` / `closes_deep`. Removed names
  that are delisted micro-caps are largely ABSENT from the survivorship-selected union panel — this is the
  binding power constraint (see §5).

### 2.1 Studiable-coverage reality (verified this session — the honest power ceiling)

Of 330 remove events: **79** have a ticker in the union panel; **76** additionally have ≥63 trading days
of price history before the announce date (trail3m computable). **Unique announce dates among the 79 in-panel
events = 30 episodes.** Control pool (union names never removed) = ~475. **K = 30 episodes is the effective-N
ceiling** — the design is episode-clustered (§4), not event-clustered, because same-date removals share the
same market state and control draw. This is thin; the report states K first and treats sub-power as a
first-class NO-GO branch (§6). The 251 non-panel removed events enter the survivorship discussion (§5) as
the known selection: our panel over-represents survivors, which if anything *understates* removal pain.

---

## 3. Constructions (frozen)

### 3.1 Fill convention — next-valid-CLOSE (inherited precedent)
Entry at the panel close on the first valid trading day strictly after `announce_date` (the hk `open`
column is unpopulated in the deep stores — H1/H-INCL2 documented; brief confirms). Forward CAR measured
close-to-close from that fill. Identical convention to the H-INCL2 gated cells — keeps R1 comparable.

### 3.2 Suspension / halt / missing-bar rule (mandatory, HK-specific)
Need a valid print within **5 sessions** after the intended fill bar, else **EXCLUDE** the event (never
forward-fill through a halt). Within a forward window cumulate over present bars only on the stock∩index
date intersection; require ≥ max(3, h//2) common bars. If the forward window runs past the panel's last
bar, DROP the event. The identical rule is applied to matched control names.

### 3.3 Abnormal return — index-relative CAR (β≡1)
Stock cumulative log-return − HSI cumulative log-return over the identical calendar window. Horizons: +5d
and +20d (gated); the pre-window −20..0 (descriptive, Trial b).

### 3.4 Deterioration proxy — trailing-3M return
`trail3m` = the name's own raw (not index-relative) simple return over the **63 trading days ending at the
last valid close on or before `announce_date`** (a strictly-backward, no-look-ahead window). This is the
deterioration the mechanical review is presumed to respond to. Names without ≥63 valid trailing bars are
dropped (part of the 76-studiable filter).

### 3.5 Matched sample — 2 non-removed controls per removed name, same trailing-3M decile, same date
For each studiable removed name at its announce date `d`:
1. Compute `trail3m` for **every** union name that (a) is not itself a removed name at `d`, (b) has ≥63
   valid trailing bars ending ≤ `d`, (c) passes the same suspension rule at the `d`-anchored fill, and
   (d) has a computable forward CAR at the horizon.
2. Rank the eligible-control pool into deciles by `trail3m` **as of `d`** (deciles formed on the control
   pool at that date). Identify the removed name's decile.
3. Draw **2** controls from the removed name's own decile, chosen as the nearest neighbours in `trail3m`
   (the two eligible names with `trail3m` closest to the removed name's). If a decile has <2 eligible
   controls, widen to nearest-neighbour in raw `trail3m` distance across the whole eligible pool (fallback
   labelled; expected rare given ~475 pool). Sampling is deterministic (nearest-neighbour, no RNG) → the
   run is reproducible without a seed.
This yields, per horizon, a stacked panel of (removed rows, matched control rows) each tagged
`removal_dummy∈{1,0}` and carrying `trail3m` and the forward CAR.

### 3.6 Regression — the incremental test
Per horizon h∈{+5, +20}:

    CAR_h  ~  β0 + β1·removal_dummy + β2·trail3m         (OLS, over the stacked matched panel)

β1 is the **incremental removal effect** — the removal underperformance *beyond* what trailing-3M return
(deterioration) already explains. GO-for-demote requires β1 < 0 with the gates in §4. Matching on decile
+ including trail3m linearly is belt-and-suspenders against the confound (residual within-decile
deterioration is absorbed by β2).

### 3.7 Episode aggregation for honest inference (the effective-N discipline)
Same-date removals share market state and control draw, so event-level t-stats would over-count. The
gated inference runs on an **episode-level β1 series**: for each of the K=30 episode dates, fit the §3.6
regression on that date's removed-vs-matched-control rows (or, where a single episode has too few rows for
a per-date fit — <4 rows — pool that episode's rows into a leave-that-episode-in stack and recover its
contribution via the panel fit's per-episode partial residual). Concretely, the primary statistic is the
**episode-clustered β1**: fit the pooled OLS (§3.6) with **episode-cluster-robust / block treatment** —
implemented as the mean of per-episode β1 estimates where estimable, HAC-t'd across the K-episode series
(`newey_west_tstat`, lags=4). This is the same episode=review-batch effective-N rule H-INCL2 §3.8 used.
Report K, the per-episode β1 series, and its HAC t.

---

## 4. Statistics & GATES (frozen)

Primary decision horizon **+20d** (the +5d cell is the second FDR slot). On the episode-level β1 series:

1. **HAC t** (`engine.validation.newey_west_tstat`, lags=4) on the K-episode β1 series. Report mean β1,
   HAC se, t, one-sided (negative) p.
2. **BH-FDR** (`benjamini_hochberg`, α=0.10) across the 2 gated one-sided p-values {+5d, +20d}.
3. **Split-half sign-stability:** split the K episodes chronologically in half; β1 mean same sign in both
   halves (and non-zero). Required for GO.
4. **DSR** via `deflated_sharpe(..., ledger=TrialLedger.with_declared_budget(N, family), family=...)` —
   program-level multiplicity. **N = 36** (masterplan §6 program budget ≈36; declared, not literal).
   Family = `r1_removal_gate_phase0`. Reported for context; the demote gate is the incremental-effect
   gate below, not a Sharpe seam, so DSR is a supporting statistic (this is a protective demote, not a
   return-alpha strategy — the DSR is on the β1 signal treated as a monthly-scale series for the haircut).
5. **Effective-N** (`bootstrap_effective_t`, block-bootstrap on the episode series) reported alongside K.
6. **Block-bootstrap 90% CI** of episode-mean β1 (block=4, B=5000, seed=7).
7. **Survivorship bound** (§5).

### 4.1 GO-for-DEMOTE gate (the demote-gate precedent, H4-strength)

This is a PROTECTIVE gate candidate; the wire would be a **DEMOTE** (avoid names facing / just-hit
removal). Per the demote-gate precedent the bar is a **strong, sign-stable, well-powered INCREMENTAL
effect**, NOT a return-alpha seam. GO-for-demote requires ALL of:

- (a) incremental **β1 HAC t ≤ −2.0** at +20d,
- (b) **split-half sign-stable** (both halves negative, non-zero),
- (c) **BH-FDR reject** at α=0.10 within the {+5d,+20d} family,
- (d) survivorship bound does not flip the sign of β1 (§5).

Miss any → **NO-GO / ACCRUE** (respectable; the raw exploratory effect being mostly pre-impounded
deterioration is itself the finding). Sub-power (K<12 studiable episodes, or the matched panel too thin
to estimate β1 at a horizon) → **NO-GO (underpowered)**, reported as such. There is NO WIRING in this
battery under any outcome — GO means "graduates to a wiring proposal in a later wave," not "wired now."

---

## 5. Survivorship bound

Our union panel is survivor-selected: 251/330 removed tickers are absent (delisted micro-caps). This
selection **understates** removal pain (the worst removed names left the panel). The bound therefore runs
in the conservative-for-the-null direction for a demote gate: we do **not** need to inflate the effect —
we need to show the *incremental* β1 is not an artifact of the survivors. Reported bound: re-estimate β1
after appending, per episode, a small mass of imputed phantom removed names at CAR = −30% (the missing
micro-caps' worst-case terminal), at 2× the observed monthly delist base rate, matched against the same
control draw. If β1 stays negative and its sign is unchanged, the bound holds. (Because phantoms make the
removed leg *worse*, this can only strengthen a negative β1 — the honest check is that the CONTROLLED β1,
not the raw CAR, survives; the phantom mass tests whether the incremental gap is robust to the selection,
not whether removal hurts in absolute terms, which is not in dispute.)

---

## 6. Verdict branches (pre-committed)

- **GO-for-demote** — all §4.1 conditions met. Graduates to a wiring proposal in a later wave. Not wired here.
- **NO-GO (effect not incremental)** — raw removal underperformance survives but β1 (removal beyond
  trailing-3M) fails the t / FDR / sign gate → the exploratory −4.67% is (mostly) the deterioration that
  *caused* the removal, already in the price; removal adds little incremental information. Respectable;
  this is the reverse-causality verdict the battery was built to test.
- **NO-GO (underpowered)** — K<12 studiable episodes or un-estimable β1. The signal may be real but our
  survivor-selected 2y-deep-ext panel cannot power it; ACCRUE (the H-PLC/roster pipeline keeps stamping
  forward removals; revisit when forward episodes accrue).

## 7. "What this does NOT show" (pre-committed)

- Nothing about **northbound** (SSE/SZSE) removals — this is SH-HK southbound only.
- Nothing about the **SZ-HK** leg beyond the ~90% overlap (roster is the SSE 沪港通 record).
- Nothing about names **outside the survivor-selected union panel** — the 251 absent removed tickers are
  characterised only by the survivorship bound, not measured.
- Not a claim about **absolute** removal underperformance (that is the exploratory's, and is not in
  dispute) — R1 tests only the **incremental** effect net of trailing deterioration.
- No **causal identification** beyond matched-decile + linear control: unobserved contemporaneous shocks
  correlated with both removal and forward returns are not ruled out (no instrument).
- No **capacity / tradability / borrow** analysis for the demote (a demote avoids longs; it does not
  require shorting the removed name).

## 8. Anticipation feasibility (exploratory, one paragraph, NO test — required deliverable)

The SSE semi-annual southbound review is **mechanical**: eligibility keys on index membership
(constituents of specified HSI-family indices) plus market-cap and liquidity/turnover thresholds measured
over a defined look-back, with removals published on a fixed cadence (roster shows clustered announce
dates ~twice yearly). Because the inputs are public and rule-based, a **watch-list is feasible in
principle**: track each held/candidate HK name's trailing market-cap rank and average turnover against the
published thresholds and flag names drifting toward the removal band ahead of the review window. Two real
frictions bound the feasibility: (i) the exact index-membership + threshold definitions must be pinned
from the current SSE/HKEX rulebook (they have been revised over the sample — e.g. index-family changes),
so a naive fixed-threshold rule would drift out of calibration; (ii) our panel lacks a clean point-in-time
free-float market-cap + eligible-index-membership history, so building the watch-list requires a new PIT
data leg, not just the price panel here. Verdict on feasibility (no test run): **buildable as a
rules-mirror watch-list, gated on a PIT market-cap/membership collector** — out of scope for R1, noted for
a later data-collection wave. This is qualitative only; R1 registers no anticipation trial.

---

### Registry
A `data/experiments/registry_seed.json` entry is appended at the END of the experiments array on this
branch (id `r1-removal-risk-gate`), status per the realized verdict. NO WIRING.
