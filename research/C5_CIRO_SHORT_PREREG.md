# C5 — CIRO Short-Position Δ — PRE-REGISTRATION

**Battery:** C5 (HK/Canada masterplan §4.1). **Wave:** W3. **Branch:** `hkca-w3-c5`.
**Author:** quant research agent. **Status:** PRE-REGISTERED — committed BEFORE any phase-0 run.
**Constitution:** masterplan §6 (pre-reg first; HAC; BH-FDR within family; program-level DSR
`n_trials=30`; split-half sign-stability; effective-N = independent episodes; DSR ≥ 0.90 the only
door to a GO; survivorship bounds not stamps; suspension-honest / lag-honest fills;
verdicts GO/NO-GO/KILL/ACCRUE).

This is the pre-registration the protocol requires **committed before the verdict is written**.
It is authored in full even though the data-depth spike (Part 1 of this wave) has already told us,
with high confidence, that the gated phase-0 test will **not clear the power bar** and the verdict
will be **ACCRUE-DATA**. Pre-registering the complete trial plan anyway is the discipline: if the
depth had surprised us upward (≥60 cross-sections joinable to a forward-return panel), these are the
exact gates the test would have had to pass — no post-hoc trial invention.

---

## 0. The power reality (established by the Part-1 depth spike, 2026-07-03)

Two **independent** constraints, either of which alone forces ACCRUE-DATA. Both are documented in
`collectors/ciro_short.py` (module docstring) and `reports/c5-phase0.md`, and both were established
by **direct Wayback probe on 2026-07-03**, not assumed:

1. **Archive depth ≈ 42–50 semi-monthly cross-sections, frozen 2018-11 → 2021-02.** The CIRO/IIROC
   Consolidated Short Position Report (CSPR) `.xls` files are reachable only by walking Wayback
   snapshots of the CSPR *page* (`iiroc.ca/.../consolidated-short-position-report.aspx`, archived
   2019-01 → 2021-05) and replay-fetching the GUID-named files each snapshot lists. The page 404s
   after the 2021-05 ciro.ca migration; the ciro.ca successor page is not in Wayback under any CSPR
   slug and its `/media/<id>/download` files are uncaptured; the live ciro.ca site returns 403
   Cloudflare. So the reachable report dates run **2018-11-30 → ~2021-02-15**. That is **< 60**, the
   masterplan's decision-grade threshold (§6.1 trial ledger: "YES if depth verified", ~330 assumed;
   the earlier Slice-G ~114/2021-10 figure is falsified — see collector docstring).

2. **Zero overlap with the name-level forward-return panel.** The CA **name-level** price panel
   (`data/canada_search/closes.parquet`, 219 `.TO` names) begins **2021-06-14**. The reachable CIRO
   archive **ends 2021-02-15**. There is therefore **no date on which a CIRO short-position reading
   can be joined to a forward name-level return** — the forward window for every archived short
   reading falls entirely before the panel's first bar. The name-tier C5 test (short-Δ → forward
   within-sector name excess) is **unrunnable on the historical archive at any depth**.

The honest consequence, pre-registered here so it cannot be reframed later: **C5's historical-archive
value is nil for a name-level forward test.** C5's real value is **forward-accruing** — live CIRO
collection from now, graded against the live name panel, maturing to a decision-grade read only once
≥60 forward semi-monthly cross-sections accrue **on dates the name panel covers** (≈ 2.5 years of
twice-monthly collection). The registry come-back date reflects that (§7).

The trials in §1–§4 are pre-registered for the counterfactual (had the archive been deep AND
overlapping) and for the **forward** accrual run when it matures. They are **not run now.**

---

## 1. Hypotheses (frozen; NOT evaluated this wave — accrual only)

The C5 family is **two trials** (masterplan §6.1: `C5 {Δ, level}`), pre-registered one-sided where
the mechanism is directional.

**H1 — short-ratio Δ (primary).** A **rising** short position on a name predicts NEGATIVE forward
within-sector excess return (short sellers as informed traders → drawdown-side signal, consistent
with the program's drawdown-side reframe). Pre-registered direction: **negative** (higher Δshort →
lower forward excess). One-sided.

**H2 — short-ratio level (secondary).** A name in the **top** cross-sectional quantile of
normalized short level earns NEGATIVE forward within-sector excess vs the bottom quantile
(crowded-short → drawdown / squeeze ambiguity). Pre-registered direction: **negative**; reported
two-sided because the US short-interest analog is mixed (the "short squeeze" sign is the live
alternative — HONEST PRIOR: genuinely open).

**H0 (both):** mean forward within-sector excess = 0 (no short-position edge).

**Normalization choice, pre-registered (the red-team's lag/normalization demand):**
- The CSPR reports **short_shares** (aggregate short position in shares) and **net_change** (Δ shares
  vs the prior report). Raw share counts are not cross-sectionally comparable (mega-caps carry more
  shares). We normalize by **shares outstanding** (→ short interest as % of float) when a PIT
  shares-outstanding series is available; **fallback = normalize by 63-day median ADV** (→ days-to-cover
  proxy) when shares-outstanding PIT is not available. **Pre-registered primary = shares-outstanding
  normalization; ADV normalization is the labelled robustness variant, not a separate FDR slot.**
  H1's Δ is the **semi-monthly change in the normalized level** (period-over-period, matching the
  report cadence), NOT a share-count delta.

---

## 2. Constructions (exact, frozen)

### 2.1 Data
- Short positions: `data/ciro_short/positions.parquet` (this wave's deliverable), index `report_date`
  (twice-monthly: 15th + month-end), columns `symbol` (CSPR format, no `.TO`), `short_shares`,
  `net_change`. Mapped to `.TO` tickers via `collectors.ciro_short.from_cspr` / `to_cspr`
  (dual-class dash↔dot; report unmapped % in coverage).
- Name prices: `data/canada_search/closes.parquet` (219 `.TO`, 2021-06-14→, dividend-adjusted TR).
- Sector map (within-sector neutralization): `data/canada_search/members.parquet` `sector` column
  (GICS-ish curated map — **PIT caveat**: today's membership/sector, not point-in-time; documented,
  a survivorship + look-ahead caveat on the within-sector leg, per constitution §7).
- Benchmark for the broad-market fallback: `data/canada/_GSPTSE.parquet`.

### 2.2 Publication-lag-honest forward windows (the red-team's core demand)
CSPR publication lag ≈ **T+2** trading days after the report date (the report_date is the position
snapshot; the file publishes ~2 days later). **Every forward window starts at the next open AFTER a
conservative ~2-week (10-trading-day) information-availability buffer** past report_date — the red-team
explicitly demanded lag honesty, and the collector's own `_STALE_DAYS = 18` encodes the same
cadence+lag reality. Concretely: signal known at report_date `t`; entry fill at the **next open on or
after `t + 10 trading days`**; forward horizons measured from that fill.
- **Forward horizon family:** 1 and 2 months (21, 42 trading days). Both reported; **primary = 1 month
  (21d)**. The horizon is a nuisance dimension reported as a short curve, NOT two separate FDR slots.
- **Excess return:** name TR − sector-cohort mean TR (equal-weighted mean of same-sector names in the
  panel that period) → within-sector excess. Broad-market excess (name TR − `_GSPTSE` TR) is the
  labelled secondary robustness cut.
- **Suspension/halt honesty:** no ffill through a gap > 5 trading days; a name with a return gap
  spanning the fill or the horizon end is dropped for that cross-section (not silently forward-filled).

### 2.3 Effective-N (the binding power control)
Semi-monthly cross-sections are **serially autocorrelated** (a name's short level barely moves in 2
weeks). Effective-N is reported three ways, and the **smallest governs**:
(a) raw report-date count; (b) **independent-episode count** = non-overlapping forward windows
(a 21d forward window consumes ~1 report-date of independence, so ≈ report_count/1 for 21d but the
autocorrelation of the *signal* means the independent cross-section count is far lower);
(c) `engine.validation.bootstrap_effective_t` block-bootstrap `t_eff` on the pooled cross-sectional
rank-IC time series (21-day blocks) — the honest floor. **The GO decision uses (c).**

---

## 3. Statistic & gates (frozen; the DSR ≥ 0.90 door)

For each trial (H1 Δ, H2 level):
1. Per report-date, cross-sectional **Spearman rank-IC** between the (lag-honored) signal and the
   forward within-sector excess. Primary horizon 21d.
2. Pooled mean IC; **HAC (Newey-West) t-stat** via `engine.validation.newey_west_tstat` (lags = 4,
   ≈ 2 months of semi-monthly obs) AND `bootstrap_effective_t` `t_eff`.
3. **BH-FDR** across the C5 family (2 trials) at q = 0.10; and the trial is counted in the
   **program-level DSR `n_trials = 30`** (masterplan §6.1 — every config across both markets).
4. **Split-half sign-stability:** split report-dates into early/late halves; the pooled IC sign must
   agree across halves. Sign flip → NO-GO regardless of full-sample t.
5. **Deflated Sharpe** (`engine.validation.deflated_sharpe`) on the long-short (top-minus-bottom
   normalized-short quantile) daily-equivalent return stream, `n_trials = 30`. **DSR ≥ 0.90 is the
   ONLY door to a GO.**
6. **Survivorship bound (not a stamp):** the name panel is current-constituent. Report the IC on
   (i) the panel as-is and (ii) a worst-case bound that imputes the drawdown-side signal as wrong on
   any name that would have delisted — since no ex-post delisted-name store exists for CA, the bound
   is stated as "sign holds only within the survivorship-clean sub-window / cannot be ruled out".

**Verdict rule (pre-committed):**
- **GO** only if, for the primary trial at the primary horizon: BH-FDR-significant AND
  `t_eff`-significant (|t_eff| ≥ 2) AND split-half sign-stable AND **DSR ≥ 0.90** AND survivorship
  bound does not flip the sign.
- **NO-GO** if the data is sufficient (effective-N clears the floor) but the gates fail.
- **ACCRUE-DATA** if effective-N does not clear the floor (the current, pre-registered expectation).
- **KILL** reserved for a sign-inconsistent, DSR-failing result on adequate N.

**Pre-registered effective-N floor for a decision-grade read:** ≥ **60** semi-monthly cross-sections
**that overlap the forward-return panel**, with `bootstrap_effective_t` `t_eff` degrees-of-freedom ≥ 20.
Below either floor → ACCRUE-DATA, no gated test run (running an underpowered gated test is itself a
protocol violation).

---

## 4. What this pre-registration does NOT do

- It does **not** run the gated test this wave. The Part-1 depth spike established that neither floor
  in §3 is met (≈ 42–50 archived cross-sections, **zero** of which overlap the name panel). Running
  the test would be theater.
- It does **not** wire any C5 signal into any board, score, or card. NO WIRING (masterplan W3 bar).
- It does **not** claim the archive is deeper than it is, or that a ciro.ca / live path exists.
  All three alternative routes (iiroc `.xls` CDX glob, ciro.ca CSPR slug, live ciro.ca) were probed
  and returned empty / 403 on 2026-07-03.

## 5. Registry

Appended to `data/experiments/registry_seed.json` at the END of the experiments array:
`c5_ciro_short_delta`, status **ACCRUE-DATA**, with the honest come-back date = when ≥60 FORWARD
semi-monthly cross-sections have accrued on name-panel dates (≈ **2028-01** at twice-monthly cadence
from the first forward collection), and a min-N alert gate so it does not ping early.

## 6. Verdict pointer

Full verdict + honest limitations: `reports/c5-phase0.md` (bold verdict first line).
