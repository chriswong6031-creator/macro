# R1 — Connect-Removal Risk Gate · phase-0

**VERDICT: NO-GO (effect not incremental) — do not wire a removal demote.** Being removed
(调出) from the SH-HK southbound Connect eligible list *does* precede HSI underperformance, but once
you control for the name's own trailing-3M return (the deterioration the mechanical semi-annual review
responds to), the **incremental** removal effect at the primary +20d horizon is β1 = **−1.32%** with an
episode-clustered HAC t of **−1.69** — directionally negative, but it **fails** the pre-registered
GO-for-demote bar of HAC t ≤ −2.0. The demote-gate precedent requires a *strong, well-powered
incremental* effect (H4-strength); this effect is real-signed but sub-threshold on a survivor-selected,
K=15-episode sample. Respectable NO-GO: most of the raw −4.7% removal underperformance the H-INCL2
exploratory found is the pre-existing deterioration that *caused* the removal, already impounded — not an
incremental shock from the removal itself.

Pre-registered in `research/R1_REMOVAL_GATE_PREREG.md` (committed before the run, branch `hkca-w7pre-r1`).
Results JSON: `data/experiments/r1_removal_gate_results.json`. NO WIRING.

---

## Data state used (stamped)

- **Roster:** `data/hk_connect_roster/roster.parquet`, 330 remove events, announce 2018-01-12 → 2026-06-29.
- **Price panel:** union of `closes_deep.parquet` (157 cols, 1986→2026-06-18) ∪ `hk_stocks/*.HK` (157) ∪
  `hk_stocks_ext/*` (388, read from the absolute sibling path
  `/Users/chriswong/…/amazing-blackburn-5d2027/data/hk_stocks_ext/`) → **545 union names, 2000-01-03 →
  2026-07-03**.
- **Benchmark:** `data/hk/_HSI.parquet` close, 1986-12-31 → **2026-07-03** (fresh).
- Fill = next-valid-close; suspension rule = valid print within 5 sessions after fill else exclude.

## Coverage / power reality (the binding constraint)

| item | value |
|---|---|
| remove events total | 330 |
| ticker in union panel | 79 |
| **NOT in union panel** (delisted micro-caps) | **251** |
| studiable events (trail3m + fwd CAR computable) | 76 |
| studiable removed tickers | 67 |
| unique announce dates (episodes) in-union | 30 |
| **episodes usable for per-date β1** (≥2 removed names) | **15** |

The 15-episode ceiling is because 13 of the 30 episodes had a *single* removed name (1 removed + 2
controls = 3 rows), too few for a per-date regression. The 251 non-panel removed names are the delisted
micro-caps our survivor-selected panel structurally lacks — a selection that, if anything, *understates*
removal pain (see survivorship bound).

## Gates vs results (primary horizon +20d)

| gate | threshold | result | pass? |
|---|---|---|---|
| incremental HAC t | ≤ −2.0 | **−1.69** | **NO** |
| split-half sign-stable | both halves neg, non-zero | h1 −0.09%, h2 −2.39% (both neg) | yes |
| BH-FDR reject (+20d, α=0.10) | q ≤ 0.10 | q = 0.091 | yes |
| survivorship no sign-flip | β1 sign holds | −1.32% → −7.60% (still neg) | yes |
| powered | K ≥ 12 episodes | K = 15 | yes |
| **GO-for-demote (ALL of above)** | | | **NO** (t-gate fails) |

**+5d cell:** β1 = −0.005%, HAC t = −0.005, no effect (split-half sign-unstable). BH q = 0.498.

Because the single binding gate (HAC t ≤ −2.0) fails, the verdict is **NO-GO (effect not incremental)**.

## Descriptive Trial (b): pre-announcement window −20..0

Removed names' pre-announcement index-relative CAR (−20..0d): mean **+0.42%**, **median +1.79%** (n=76).
This is the informative nuance: in the median, removed names were **not** in freefall in the 20 sessions
*before* the announcement — the deterioration that triggers the mechanical review is a *slower*,
longer-horizon rank/liquidity drift (the trail3m control is what absorbs it), not an acute pre-print
collapse. So the reverse-causality confound operates over months, not the 20d pre-window; the −20..0
descriptive does not by itself explain the raw post-event drop.

## Robustness cross-check (labelled, not the pre-registered primary)

A **pooled full-sample** OLS (all 76 events, including the 13 singleton episodes the episode-clustered
primary drops) gives a *larger* incremental β1 at +20d = **−3.66%** — but its *unclustered* t is only
**−1.94**, and unclustered t **overstates** significance by ignoring the episode clustering the pre-reg
mandated. So the fuller sample points the same direction and still does not clear −2.0 under any honest
(clustered) inference. The two estimators agree on the verdict.

## Survivorship bound

Injecting phantom missing-micro-cap removed rows at CAR = −30% (2× monthly delist rate) per episode
*deepens* the incremental β1 (−1.32% → −7.60%, mechanically, since phantoms worsen the removed leg) with
**no sign flip**. This confirms the controlled effect is not an artifact of the survivor selection — but
it does NOT rescue the GO: the phantom injection is a worst-case bound on the *absolute* removed-leg
return, not evidence the *incremental* (trailing-3M-controlled) t clears the bar on real data.

## DSR (supporting)

DSR at +20d = 0.002 (FAILS the multiple-testing haircut), with the program-declared budget N=36 via
`TrialLedger.with_declared_budget(36, "r1_removal_gate_phase0")`. Noted for completeness; the demote gate
is the incremental-effect gate (an incremental t / FDR / sign test), not a Sharpe seam — DSR on a 15-point
β1 series treated as monthly-scale is under-powered by construction and is not the decision statistic.

## Anticipation feasibility (exploratory, qualitative — no test run)

The SSE semi-annual southbound review is mechanical: eligibility keys on membership of specified
HSI-family indices plus market-cap and turnover/liquidity thresholds over a defined look-back, published on
a fixed ~twice-yearly cadence (the roster's announce dates cluster accordingly). Because the inputs are
public and rule-based, a **watch-list is feasible in principle** — track each held/candidate HK name's
trailing free-float market-cap rank and average turnover against the published bands and flag names
drifting toward the removal threshold ahead of a review window. Two frictions bound it: (i) the exact
index-membership and threshold definitions must be pinned from the *current* SSE/HKEX rulebook (they have
been revised across the 2018–2026 sample, so a fixed-threshold rule would drift out of calibration); (ii)
our stores lack a clean point-in-time free-float market-cap + eligible-index-membership history, so the
watch-list needs a **new PIT collector**, not the price panel here. Feasibility verdict (no test):
**buildable as a rules-mirror watch-list gated on a PIT market-cap/membership collector** — out of scope
for R1, parked for a later data-collection wave. R1 registers no anticipation trial.

## What this does NOT show

- Nothing about **northbound** (SSE/SZSE) or the **SZ-HK** leg beyond the ~90% roster overlap — this is
  the SSE 沪港通 southbound record only.
- Nothing about the **251 removed names absent from the panel** — characterised only by the survivorship
  bound, never measured. Our result is conditional on the survivor-selected union.
- Not a claim about **absolute** removal underperformance (that is the exploratory's −4.7%, not in
  dispute). R1 tests only the **incremental** effect net of trailing-3M deterioration, and finds it
  directionally negative but below the demote-strength bar.
- **No causal identification** beyond matched-decile + linear trail3m control — no instrument; unobserved
  contemporaneous shocks correlated with both removal and forward returns are not ruled out.
- The **K=15 usable-episode** ceiling means a genuine incremental effect of this size (~−1.3 to −3.7%)
  could exist and simply be un-powered here. This is why the alternative to NO-GO was ACCRUE, not "no
  effect" — the H-PLC/roster pipeline keeps stamping forward removals; revisit when more episodes accrue.
