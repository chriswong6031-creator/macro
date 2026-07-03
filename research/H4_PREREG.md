# H4 Phase-0 Pre-Registration — Within-Universe Reversal on the Expanded HK Universe

**Battery:** H4 (masterplan §3 H4, red-team-re-scoped). **Branch:** `hkca-w3-h4`.
**Author:** Opus 4.8 quant agent · **Date:** 2026-07-03 · **Committed BEFORE any run** (separate commit from code+report).
**Constitution:** masterplan §6 / §6.1. Pre-reg → HAC-t → BH-FDR within family → DSR≥0.90 via
`engine/validation.py:deflated_sharpe` at PROGRAM `n_trials=30` → split-half sign-stability →
effective-N = independent episodes → survivorship BOUND → suspension rule. Verdicts: GO / NO-GO / KILL / ACCRUE.
NO wiring into engines/boards.

---

## 0. Data state STAMP (exact local state read for this battery)

- `data/hk_stocks_ext/*.parquet` — **388** names, deep OHLCV, Date-indexed, cols `[open,close,high,low,volume]`.
  Store max date **2026-07-03**. First-valid-close tiers: **77 pre-2005, 124 pre-2010, 166 pre-2015, 228 pre-2020**.
  **GITIGNORED (R2-destined).** Read locally from the sibling worktree
  `.../worktrees/amazing-blackburn-5d2027/data/hk_stocks_ext/` (the isolated worktree's copy is a stub:
  `_checkpoint.json n_fetched=0`). The 388 parquets are the real fetched store.
- `data/hk_stocks/*.parquet` — **157** mega-caps, same schema, 2000→ (`0001.HK` shape (6603,5)).
- **Union = 545 names, overlap = 0** (the two stores are disjoint by construction).
- Benchmark `_HSI` = `data/hk_search/_HSI_deep.parquet` (single `close` col, 1986→**2026-06-12**).
  HSI is **18 days staler** than the price store; all forward returns are HSI-relative, so the panel is
  **clipped to the last HSI date** (2026-06-12) for return computation — stamped in the report.
- `data/hk_search/closes_deep.parquet` — 157-name mega-cap panel, **67 names first-valid pre-2005**,
  stale 2026-06-18 (survivorship-selected). This is Control 2's source.
- Sector map (SECONDARY only): `data/hk_breadth/constituents.parquet` — 160 current constituents, **13 sectors**,
  CURRENT map, **no PIT status** (red-team: HK has no PIT sector taxonomy) → labelled hindsight.

---

## 1. Hypotheses

**PRIMARY (H4-P) — small/low-ADV within-universe short-horizon reversal.**
On the UNION universe (≈545 names), the deepest quintile of a within-universe 3-month return z-score,
restricted to the **bottom-half by 63d HKD ADV** cohort, earns positive HSI-relative forward 1-month
returns (a long-only deepest-quintile tilt, and the long-short deepest-minus-shallowest spread).
Mechanism: microstructure/illiquidity reversal, which the literature places in small/illiquid names —
the CN lesson said NO confirmation gates, so this runs with **hygiene screens only**.
Honest prior: **genuinely open** — literature lives here.

**CONTROL 1 (H4-C1, expected-fail confirm-a-kill).** Identical construction on the **157 mega-cap panel**
(`hk_stocks`). `rev_st` already failed FDR there (masterplan §0: t_HAC 1.52 full / 0.49 modern, DSR 0.07–0.18).
Expectation: reproduce ≈ that NO-GO. A GO here would be a red flag on the whole construction.

**CONTROL 2 (H4-C2, survivorship-heavy, labelled).** Identical construction on the **67-name pre-2005 deep
subset** of `closes_deep`. Survivorship-selected (current-constituent, back-filled) → results are an
OPTIMISTIC ceiling, labelled as such, never decision-grade.

**SECONDARY (H4-S, robustness, labelled non-PIT).** PRIMARY construction but z-scored WITHIN the 13-sector
CURRENT map (`constituents.parquet`) instead of whole-universe. Sector map is hindsight (no PIT taxonomy) →
this is a labelled robustness trial, not decision-grade on its own.

**Family = 2 gated trials (PRIMARY + SECONDARY) + 2 controls.** BH-FDR applied across the 2 gated trials.

---

## 2. Exact constructions

**Panels.** Load each store into a wide close matrix (and volume matrix for ADV). Business-day union index.
NO forward-fill of prices through gaps (suspension rule, §5). Clip to `min(store_max, HSI_max=2026-06-12)`.

**Reversal signal (per rebalance date t, per name i).**
- `raw_i = close_i[t] / close_i[t-63bd] - 1` (3-month / 63-trading-day total return; `close` is div-adjusted
  per the yahoo-close gotcha, so this is total return — noted).
- Require ≥ 63 valid trading days in the lookback window AND a valid close at t and t-63.
- Within the eligible cross-section on date t, convert to z: `z_i = (raw_i - mean)/std`.
  For H4-S the mean/std are computed WITHIN each sector (sectors with <5 eligible names that date dropped).
- **Deepest quintile = lowest z (biggest losers)** — the reversal long leg. Shallowest = highest z.

**ADV cohort (PRIMARY + SECONDARY only).**
- `adv_i[t] = median( close_i * volume_i )` over the trailing **63 trading days** (HKD dollar ADV; `close` is
  price in HKD, `volume` in shares). Median (not mean) to blunt single-day spikes.
- Cohort = names with `adv_i[t] < cross-sectional median(adv[t])` (bottom-half by ADV). Recomputed each date.
- Controls use the WHOLE panel (no ADV cohort split) — they are the large-cap confirm-a-kill and the deep ceiling.

**Hygiene screens (all trials, applied at date t — NO confirmation/alpha gates).**
- **ADV floor**, scaled down for small caps: name must have `adv_i[t] ≥ 1,000,000 HKD` (1 M HKD/day).
  This is deliberately low (mega-cap harnesses use higher floors) so the small-cap cohort is not emptied;
  it only removes near-untradeable/dormant listings. Stamped.
- **Staleness:** the name's last valid close must be within 5 trading days of t (else excluded that date).
- **Suspension rule (§5):** see below — no valid print within 5 sessions after a fill ⇒ excluded, never ffilled.

**Forward return (implementation-lag honest).**
- Data availability lag for H4 = **0 trading days** for the price signal itself (close-based reversal on
  end-of-day prices is known at t's close), BUT the masterplan mandates **next-open fills**: the position is
  entered at the **NEXT OPEN after t** (t+1 open) and the forward 1-month return runs from that next open.
- `fwd_i = open_i[t+1 .. t+1+21bd] path` → measured as `close_i[t+1+21bd] / open_i[t+1] - 1` (enter next open,
  hold ~21 trading days ≈ 1 month, exit on close). HSI-relative: subtract
  `HSI[t+1+21bd]/HSI_open_proxy[t+1] - 1`. HSI has close only → use HSI close-to-close over the SAME dates
  `HSI[t+1+21bd]/HSI[t+1] - 1` as the benchmark (documented approximation; both legs share it so the L/S
  spread is benchmark-invariant).
- If `open_i[t+1]` is missing (halt at the open), the name is dropped for that rebalance (no synthetic fill).

**Rebalance.** MONTHLY — last business day of each calendar month is a rebalance date t. Non-overlapping
21-bd holds ⇒ **independent monthly episodes** (this is the effective-N unit).

**Portfolio construction.**
- Long-only deepest-quintile: equal-weight the deepest-z quintile of the cohort each month; forward return =
  mean HSI-relative fwd across held names.
- Long-short: deepest-quintile long minus shallowest-quintile short, equal-weight each leg
  (`quintile_ls`-style). This is the headline reversal spread.
- Monthly return series → daily-equivalent Sharpe for DSR by treating each monthly return as one period and
  annualizing with `trading_year=12` in `deflated_sharpe` (monthly periodicity; the DSR probability is
  annualization-invariant per the docstring).

---

## 3. Statistics & gates (pre-stated, per trial)

| Stat | Method | Gate |
|---|---|---|
| HAC t on mean monthly L/S | `newey_west_tstat(lags=3)` on the monthly spread series | report |
| Rank-IC | `rank_ic` per month (deepest-lowest-z → highest fwd), `ic_summary` | report; sign must agree with L/S |
| BH-FDR within family (2 gated) | `benjamini_hochberg` on {H4-P, H4-S} HAC p-values, α=0.10 | reject ⇒ eligible |
| DSR | `deflated_sharpe(sr, skew, kurt, T=n_months, n_trials=30, t_eff=…)` | **≥0.90** to pass |
| effective-N | `bootstrap_effective_t` on the (expanded to daily-equivalent) return stream; else raw n_months | report |
| split-half | first-half vs second-half by calendar time; L/S sign must MATCH | same sign ⇒ stable |

**PROGRAM n_trials = 30** (masterplan §6.1 program-level multiplicity, counting every config across both
markets). Passed as a literal to `deflated_sharpe` for this standalone battery.

**GO** = BH-reject AND DSR≥0.90 AND split-half sign-stable AND effective-N ≥ 12 independent episodes AND
HAC-t supports (|t|≥2 same sign). **ACCRUE** = right direction / promising but fails DSR or effective-N < 12.
**NO-GO** = null or fails FDR. **KILL** = clearly negative / opposite sign with power.

**Honest power note (pre-stated):** PRIMARY has ~310 monthly rebalances max but quintiles within the bottom-ADV
cohort are THIN (cohort ≈ half the eligible names; deepest quintile ≈ 10% of that). Effective independent
episodes across a ~20y span are far fewer than n_months (autocorrelated regimes) — `bootstrap_effective_t`
is the honest count. NO-GO/ACCRUE is a respectable and likely outcome; marginal results will NOT be tortured to GO.

---

## 4. Survivorship BOUND (mandatory, pre-registered — red-team demand)

The union panel is CURRENT constituents; delisted losers are absent. For a REVERSAL long leg (buying the
biggest losers), absent delisted losers bias the observed long-leg return UPWARD (the worst losers that would
have kept falling / delisted are missing).

**Pre-registered bound (simple, worst-case):** for each rebalance month, let `k` = number of deepest-quintile
long names actually held. Inject `k_phantom = round(k * OBSERVED_DELIST_RATE * 2)` phantom names into the
deepest-quintile long leg, each with a terminal **−30% one-month forward return**, and recompute the long-leg
(and L/S) monthly return. `OBSERVED_DELIST_RATE` is unknown for HK in-tree (no dead-name store), so we use a
literature-anchored **base rate of 3%/yr ⇒ 0.25%/month** delisting; the bound doubles it to **0.5%/month**
of the held count as phantom losers at −30%. Report the effect-size **RANGE** [bounded, observed], not a point
estimate. (This is a coarse, deliberately-pessimistic bound, not an estimate of the true delist process.)

**Interpretation rule:** if the L/S spread flips sign or loses HAC significance under the bound, the trial is
downgraded to at best ACCRUE regardless of the observed-panel gate outcome.

---

## 5. Suspension / halt rule (pre-registered — HK names halt for weeks)

A HK name that halts has no valid print for the halt duration. Rule applied in EVERY forward-return computation:
- Prices are NEVER forward-filled through gaps.
- A "valid print" = a non-NaN close on a business day the exchange traded.
- **Exclusion:** if, after a fill at t+1 open, the name has **no valid print within 5 trading sessions**, it is
  **EXCLUDED from that rebalance's return** (dropped, not ffilled) — the position is treated as un-enterable.
- Staleness screen (§2) already drops names whose last print is >5 sessions before t.
- This is applied identically to all four trials.

---

## 6. Trial ledger row (from masterplan §6.1)

| ID | Test | Effective-N basis | Decision-grade? |
|---|---|---|---|
| H4 {small-cap primary + 2 controls} | reversal | ~310 monthly rebalances; quintiles thin | **YES on expanded universe only** |

Controls (C1 large-cap, C2 deep-67) are NOT decision-grade (confirm-a-kill / survivorship ceiling).
SECONDARY (within-sector) is a labelled non-PIT robustness trial.

## 7. What this pre-reg BINDS

- Signal = 63bd total-return z; deepest quintile = biggest losers; monthly rebalance; NEXT-OPEN fills;
  21bd hold; HSI-relative.
- Cohort = bottom-half 63d HKD median ADV (PRIMARY/SECONDARY); whole panel (controls).
- Hygiene = ADV floor 1M HKD + 5-session staleness + suspension exclusion. NO confirmation/alpha gates.
- Gates = BH-FDR(α0.10) across {P,S} → DSR≥0.90 at n_trials=30 → split-half sign → effective-N≥12.
- Survivorship bound = phantom −30% losers at 0.5%/month-of-held-count injected into the long leg.
- Registry append at END of run (pure append).

No result-dependent choices remain after this document is committed.
