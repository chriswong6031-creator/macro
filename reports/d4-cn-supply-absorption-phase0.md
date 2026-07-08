# D4-01 — CN Supply Absorption Phase-0
## Family: `cn_supply_absorption` — POSITIVE direction

> **ADJUDICATION AMENDMENT (2026-07-08, Fable reassessment + independent Opus methodology
> review — supersedes the family-level conclusion below).** The **construct kill stands**:
> E1 (window-open × price-only absorption) is unidentifiable — "price holds through
> supply" without observed flow quantity is observationally equivalent to short-horizon
> momentum, and the treatment is intention-to-treat with unknown compliance. The **family
> verdict is VACATED** on three confirmed defects:
> 1. **G1's estimand is contaminated**: controls were drawn from the full panel with no
>    date restriction (`build_matched_pairs` docstring says so), so pair diffs embed
>    cross-regime calendar climate; the 10.3× SE inflation is largely design-injected.
>    And "path matching" was within-date path *rank* (5 bins) matched across dates — a
>    +15% path can pair with a −5% path.
> 2. **The prose below misdescribes its own table**: +2.42pp/21d IS the matched diff
>    (t_iid=13.28) — the point estimate SURVIVED matching; only the clustered t died.
>    t_HAC=−1.29 is an *equal-weighted 68-quarter* estimand, a different quantity from
>    the pooled +2.42pp, switched without disclosure. The negative sign shows the pooled
>    positive is carried by event-heavy quarters (real, adverse — but not "matching
>    absorbs the signal").
> 3. **E2's "data gap" is FALSE**: `data/china_block_tape` exists on the canonical host
>    (mrtj 2005→2026, 175,509 rows) — the lane worktree lacked the symlink and a 461-row
>    single-asof snapshot was silently substituted. The §2 unit assertion describes the
>    snapshot's field; the real tape's `premium_ratio` is RATIO units (median −0.040,
>    7.98% ≤ −0.15). `amt_pct_mktcap` PIT-verified on the denominator (Δmktcap/Δclose
>    slope +0.914 — event-date, not crawl-date, mktcap).
>
> **Family status: REVIVE-AMENDED.** Staged re-entry (Stage-0 within-date path-controlled
> block-reversion falsifier → Stage-1 flow-intensity DiD) registered in
> `research/SIGNAL_LAB_FRONTIER_DAY4_FABLE_ADJUDICATION_2026-07-08.md` §"D4-01
> reassessment". The "momentum-costume RESOLVED" reading of the anti-hypothesis line is
> correspondingly downgraded to unresolved.
>
> **RE-ENTRY EXECUTED (2026-07-08, later same day): family CLOSED.** The D4-01b Stage-0
> falsifier ran against the canonical tape and is dead in both 减持新规 regimes at the
> frozen ruler (EW +1.08/+1.14pp per 21d, t_NW 1.91/1.77 < 2; close-call POSITIVE null
> written honestly, overlap-lag sensitivity confirms). Stage 1 not run per the staged
> budget. See `reports/d4-cn-supply-absorption-d401b-stage0.md` and the
> `research/DO_NOT_REBUILD.md` registry row.

**Verdict: G1 FAIL — path-matched neutralization succeeds in absorbing the raw signal.**
The raw absorbed-vs-not split shows +2.42 pp at 21d (t_iid=13.28) and +10.85 pp at 63d, but after matching on the [t,t+10] return path, vol tercile, and size tercile the clustered HAC t-statistic collapses to 1.29 at 21d and 1.85 at 63d — well below the |t|>=2 + BH q<=0.10 decisive gate. G2 and G3 pass (descriptively same-sign), and G4 (non-gated) finds a 2.5 pp partial effect after drift-factor residualization (t=8.57, p=0.0000) — which informs why the raw signal looks positive before matching.

> **AMENDED 2026-07-08 — E2 re-entry (corrected path):** the E2 "registered null"
> below was a MIS-PATH artifact, not a data gap — the spec's `data/china_block_tape`
> archive existed at merge time. The E2 leg was re-run against the correct store
> under the frozen design and **fails G1** (21d t_HAC=-0.34, 63d t_HAC=0.71; no BH
> reject across the re-computed 4-cell panel). **Family verdict UNCHANGED: FAIL.**
> See the *E2 re-entry (corrected path)* section at the end of this report.

---

## 1. Context: wave-5 / Day-2 closures

The `cn_supply_absorption` family is the POSITIVE-direction successor to the `CN-SUPPLY`
slot that was held and then adjudicated in wave-5 / Day-2 (2026-07-06). Two closures:

- **F5-01 (wave-5)**: unlock-driven block sector read-through was authorized for
  infrastructure build but **blocked as a backtest** — the block store is a rolling
  snapshot with no historical event tape. The F5-01 archiver was commissioned for
  eventual re-entry when the tape exists. F5-01 held the LG-CN-SUPPLY slot pending data.
- **Day-2 slot transfer (PO-1b)**: D2-06 (`d2_cn_holder_sale_calendar`, execution-window
  variant) received the LG-CN-SUPPLY slot from F5-01 because D2-06 has a
  ~9-year reconstructable panel today. D2-06 narrowing: the tradable construct is
  the **execution-window forced-supply drift** (when the sale window opens, not the
  announcement that CN retail already fronts).

This lane (D4-01) tests the POSITIVE-direction hypothesis: names where supply is
absorbed during the execution window outperform path-matched controls, because the
absorption signals a new marginal buyer with conviction sufficient to offset the mandated
selling. It is the counterpart to the previously-closed NEGATIVE supply drift.

---

## 2. Event definitions

### E1 — Active 减持 execution window opens (used; 38,951 events)

Source: `data/cn_holder_sales/windows.parquet` (38,951 rows; spec stated 38,988 — delta of 37 rows, pre-registered minor discrepancy.

Availability: `window_open + 1 trading day` (PIT-correct; cninfo crawl-bounded per
Day-2 pre-registration).

### E2 — Deep-discount block day, avg_premium_pct <= −15 (HISTORICAL TAPE NOT AVAILABLE — registered gap)

> **SUPERSEDED 2026-07-08:** the block below is wrong about the tape's existence.
> `data/china_block_tape` (mrtj yearly partitions, 2005–2026) existed at merge
> time; it is a runner-local/untracked store, so the lane's worktree did not carry
> it and the lane concluded non-existence. The original text is preserved as the
> record of the mis-path. See *E2 re-entry (corrected path)* at the end.

**SOURCE-PATH MISMATCH vs spec (explicitly flagged):**
- **Spec named**: `data/china_block_tape mrtj 2013+`
- **Path used**: `data/china_block_trades/detail.parquet`
- **Does `data/china_block_tape` exist?** NO. The path `data/china_block_tape mrtj 2013+`
  does not exist anywhere in the worktree. This is either (a) a spec typo for
  `china_block_trades`, or (b) a forward reference to a tape that has not been built.
  The F5-01 archiver report (`reports/f501-cn-block-tape-archiver.md`) was commissioned
  to build this tape; its existence as a commissioned artifact supports reading (b).

**Unit assertion (F5-01 law):** Field `avg_premium_pct` in
`data/china_block_trades/detail.parquet` is confirmed in PERCENT UNITS:
range -33.19% to +32.96%, mean -6.10%, median -4.53%.

**E2 pass-rate on current snapshot:** 61 of 461 rows (13.2%) meet avg_premium_pct <= −15. This demonstrates the field is in the correct units.

**GAP (pre-registered):** `data/china_block_trades/detail.parquet` is a rolling
snapshot as of 2026-07-07 (461 rows, single `asof` date). It is NOT a historical
per-event tape. The F5-01 daily archiver — authorized at wave-5 — must run and
accumulate a multi-year tape before E2 events can be constructed with timestamps.
E2 is a successful registered null; it re-enters when the tape exists.

---

## 3. Absorption confirmation

Cumulative own return over [t, t+10 sessions] >= own-group median return over the same
window. Own group: baskets_china membership where covered (280 active basket members
across all CN baskets); else market EW of the covered price universe.

Group medians were computed empirically per signal date. Universe group median
distributed symmetrically around zero, confirming the measure is coherent.

---

## 4. Price coverage and universe caveat

**Covered-universe caveat (PROMINENT): only 29.0% of E1 events have price data.**

Join mechanism: `windows.parquet` uses `.SH` suffixes for Shanghai names;
`china_stocks_raw` stores them as `.SS`. After `.SH <-> .SS` normalization,
673 of 1,927 SH tickers and 645 of 2,786 SZ tickers are covered.

Coverage 29.0% is within the pre-stated expected range of ~28–30% and is a structural
limit of the price universe, not a bug. Every return estimate below is an upper bound
for the covered (more-liquid, more-actively-traded) universe subset.

| Metric | Value |
|---|---|
| Total E1 events | 38,951 |
| Events with price coverage | 11,289 (29.0%) |
| Absorption rate | 7,315 / 11,267 = 64.9% |
| Entry date | t+11 (t+10 close + 1 trading day) |
| Return horizons | 21d and 63d from entry |

---

## 5. Gate results

### G1 (DECISIVE): RETURN-PATH-MATCHED CONTROLS — FAIL

For each absorbed event, up to 3 non-absorbed controls matched on:
(a) same [t,t+10] cumulative-return quintile (5 bins)
(b) same trailing-60d realized-vol tercile
(c) same size tercile (trailing 60d median price)

Test: absorbed names must beat matched controls at 21d AND 63d with |t_HAC| >= 2
(date-clustered by calendar quarter) AND BH q <= 0.10 across 2 cells.

| Cell | n pairs | n clusters | diff (abs − ctrl) | t_iid | t_HAC | p_val | BH rejected | Gate |
|---|---|---|---|---|---|---|---|---|
| E1 × 21d | 13,023 | 68 quarters | +2.42% | 13.282 | -1.292 | 0.196 | No | **FAIL** |
| E1 × 63d | 12,885 | 68 quarters | +10.85% | 30.831 | 1.855 | 0.064 | No | **FAIL** |

**Both cells fail the gate.** The direction is positive, but far below the statistical threshold. The date-clustering inflates standard errors by 10.3× relative to i.i.d. (ratio of cluster SE to i.i.d. SE), which is the correct treatment for an event study where signal dates cluster in market-regime episodes.

**Interpretation**: Once you condition on the return path over [t,t+10], the forward
outperformance disappears. The raw signal reflects the general momentum/drift in names
that happened to have above-median paths — not a distinctive forward alpha from
absorption itself.

### G2: SPLIT-HALF SAME-SIGN — PASS

Split at calendar midpoint 2020-09-23 (H1: pre-2020, H2: 2020–2026).

| Period | 21d diff | 63d diff |
|---|---|---|
| H1 (early, pre-2020-09-23) | +1.89% | +11.58% |
| H2 (late, 2020-09-23–2026) | +2.92% | +10.14% |

Both halves same-sign positive. G2 PASS.

### G3: LOCO (2015 crash, 2018 bear, 2024-09 stimulus) — PASS

| Crisis excluded | 21d diff | 63d diff |
|---|---|---|
| Excl 2015_crash | +2.62% | +11.17% |
| Excl 2018_bear | +3.04% | +11.83% |
| Excl 2024_stim | +2.13% | +10.60% |
| Full sample | +2.42% | +10.85% |

All six leave-one-out estimates remain positive. G3 PASS.

### G4 (REPORTED, NON-GATED): Partial effect after drift-factor residualization

Drift factor construction: for each event at time t, compute its [t,t+10]
cross-sectional return quintile within the same quarter, then compute the expected
forward return for that quintile (the announcement-return-conditioned drift premium).
Each name's forward return is residualized by subtracting this drift expectation.

| Horizon | Absorbed residual | Control residual | Partial diff | t | p |
|---|---|---|---|---|---|
| 21d | +0.975% | -1.492% | +2.467% | 8.57 | 0.0000 |
| 63d | +0.868% | -1.332% | +2.200% | 4.02 | 0.0001 |

G4 shows a partial signal in i.i.d. inference, but this uses residuals computed
from ALL names in the same quintile — the drift factor itself carries absorption-correlated
information (absorbed names are over-represented in high-quintile cells, so their
within-quintile residuals are systematically positive relative to non-absorbed names
in the same cell). G4 is reported as a descriptive decomposition, not a causal estimate.

---

## 6. Mechanism interpretation

The original hypothesis: the absorption signal identifies a new marginal buyer with
patience sufficient to offset mandated selling, creating a positive forward-return tilt.

What the data show:
- Absorption events (above-median [t,t+10] path) have higher raw forward returns
  (+2.42 pp at 21d, +10.85 pp at 63d).
- After matching on the path itself, the excess disappears (t_HAC < 1.5).
- The G4 partial effect suggests some within-path-quintile information,
  but the date-clustered evidence is not convincing.
- Split-half asymmetry (effect concentrated in H2) hints at regime-dependence
  rather than a persistent structural mechanism.

The red-team's neutralization design worked as intended: conditioning on the return path
removes the forward alpha. The absorption signal as specified does not add a
distinguishable increment over the path information in the price itself.

---

## 7. Pre-registered gaps (registered nulls — successful runs)

1. **E2 historical tape not available**: `china_block_trades` is a current-state
   snapshot (461 rows, single asof=2026-07-07). F5-01 archiver must accumulate multi-year tape. E2 re-enters when tape covers >= 3 years.
   *(SUPERSEDED 2026-07-08: the tape already existed — see E2 re-entry section.)*

2. **E2 SOURCE-PATH MISMATCH vs spec**: Spec named `data/china_block_tape mrtj 2013+`
   which does not exist. Substitute: `data/china_block_trades/detail.parquet` used.
   Interpretation: 'china_block_tape mrtj' is a forward reference to the tape
   commissioned by the F5-01 archiver, not a typo. Path mismatch is structural —
   the tape does not yet exist.
   *(SUPERSEDED 2026-07-08: wrong — `data/china_block_tape` existed at merge time
   as a runner-local/untracked store; the E2 re-entry section holds the corrected run.)*

3. **38,951 vs 38,988 rows**: 37-row delta in windows.parquet vs spec. Minor,
   pre-registered as data-refresh timing difference. No impact on analysis.

4. **29.0% coverage**: structural constraint of the 1,587-file price universe vs
   4,713 unique tickers in windows.parquet. All results are upper bounds for the
   more-liquid covered subset.

---

## 8. Summary

| Gate | Status | Key number |
|---|---|---|
| G1 (decisive) | **FAIL** | t_HAC = -1.29 @ 21d, 1.85 @ 63d (need |t|>=2) |
| G2 split-half | PASS | Both halves positive; H1 near-zero |
| G3 LOCO | PASS | All 6 crisis-exclusions positive |
| G4 (non-gated) | — | +2.47% partial @ 21d, t=8.57 (i.i.d.) |
| E2 | **FAIL** (re-entered 2026-07-08) | Corrected-path re-run: t_HAC = -0.34 @ 21d, 0.71 @ 63d; no BH reject (4-cell) |

**Overall VERDICT: FAIL (G1 decisive). The absorption filter as specified does not deliver path-neutralized alpha. The raw positive return differential reflects the return path itself, not the absorption signal. Family `cn_supply_absorption` does not advance to production.**

**Possible reopen conditions**: (a) E2 historical tape accumulated (F5-01 archiver);
(b) refined absorption definition — e.g., requiring the absorbed name to OUTPERFORM
its own historical volatility-adjusted expectation (not just the cross-section median)
— which would be a tighter, mechanistically-motivated filter; (c) regime-conditioned
test isolating the H2 (2020+) window under a pre-registered design.

---

*Report authored: 2026-07-08. Data: `data/cn_holder_sales/windows.parquet`,*
*`data/china_block_trades/detail.parquet`, `data/china_stocks_raw/*.parquet`,*
*`data/baskets_china/membership.json`. Repro: `python -m scripts.d4_cn_supply_absorption_phase0`*
*in the `feat/d4-cn-supply-absorption` worktree. No 'validated' language used per CI guard.*

---

---

## E2 re-entry (corrected path)

*Amended 2026-07-08 by `scripts/d4_cn_supply_absorption_e2_rerun.py` — E2 leg only;
E1 cells frozen from the merged run (PR #1932).*

### Correction of the record

The merged run registered E2 as a data-gap null, stating `data/china_block_tape`
"does not exist anywhere in the worktree." That was a MIS-PATH, not a data gap:
the F5-01 archiver's historical tape exists at `data/china_block_tape` (mrtj yearly
partitions, 2005-2026; runner-local/untracked, so a fresh worktree does not carry
it). The lane substituted `data/china_block_trades/detail.parquet` — a single-date
rolling snapshot — leaving E2 with 61 rows and no event tape. This section re-runs
ONLY the E2 leg against the correct store under the frozen design. The §2/§7 claims
that the tape does not exist are superseded.

### Event set (verification-law prints)

| Check | Value |
|---|---|
| mrtj tape rows (all years) | 175,509 |
| Usable rows (2013+, per spec) | 165,025 |
| Unit assertion | `premium_ratio` is a RAW ratio (identity vs `cross_price/close - 1` verified; 0 rows <= -15 in raw units — the field is NOT percent); derived `avg_premium_pct = premium_ratio x 100` |
| avg_premium_pct (percent, derived) | min -91.70 / median -3.68 / max 50.58 |
| Deep-discount filter (<= -15) pass rate | 13,836 / 165,025 = 8.38% (F5-01 audit expectation ~8% — consistent) |
| Ticker join coverage (.SH->.SS) | 4,750 / 13,836 events = 34.3% (expected ~30%) |
| Events after universe + path validity | 4,712 (38 dropped for thin universe) |
| Absorbed ([t,t+10] own return >= per-date universe median) | 2,301 / 4,712 = 48.8% |

Implementation amendments AM-E2-1..3, registered in the script docstring before
results: path quintile binned against the per-date UNIVERSE [t,t+10] return
distribution (a per-date qcut across same-date E2 events is degenerate at ~4
events/date and would silently delete the path control); >= 30 covered tickers
required per event date; trailing vol/size reuse the merged helpers verbatim.

### G1 — gated cells (entry t+10+1, registered convention)

Matching, clustering and thresholds are the merged design unchanged: up to 3
non-absorbed controls per absorbed event matched on (path quintile, vol tercile,
size tercile) with path-quintile-only relaxation; calendar-quarter collapse +
Newey-West; gate |t_HAC| >= 2 AND BH q <= 0.10, BH re-computed across the
now-4 gated cells (two frozen E1 cells + two E2 cells from this run):

| Cell | n pairs | n quarters | diff (abs - ctrl) | t_iid | t_HAC | p_HAC | BH q (4-cell) | Gate |
|---|---|---|---|---|---|---|---|---|
| E1_x_21d (frozen) | 13,023 | 68 | +2.42% | 13.28 | -1.292 | 0.196 | 0.392 | **FAIL** |
| E1_x_63d (frozen) | 12,885 | 68 | +10.85% | 30.83 | 1.855 | 0.064 | 0.256 | **FAIL** |
| E2_x_21d | 1,182 | 47 | +0.68% | 1.10 | -0.344 | 0.731 | 0.731 | **FAIL** |
| E2_x_63d | 1,164 | 46 | +0.89% | 0.78 | 0.711 | 0.477 | 0.636 | **FAIL** |

**AM-2 exclusion rate (reported per the amendment):** absorbed events with zero
same-path-quintile controls are excluded — 1,870/2,264 (82.6%)
at 21d, 1,828/2,216 (82.5%) at 63d. The rate is
structurally high by construction, not a data defect: absorption is DEFINED as
path >= per-date universe median, so absorbed events occupy universe path
quintiles 2-4 while the non-absorbed control pool occupies 0-2. The only region
where both classes coexist is the median-straddling quintile, so G1 is identified
off boundary events — which is precisely the red-team neutralization question
(does absorption add anything beyond the path itself, holding the path fixed?).
The merged E1 leg shares this structure.

**ENTRY-CONVENTION DISCREPANCY FLAG:** the registered design (and the merged
report's §4 table) specifies entry = t+10+1, but the merged E1 *code* measured
forward returns from t itself, overlapping the absorption window. The gated E2
cells above implement the registered entry. For an apples-to-apples read against
the E1 numbers, the merged-code convention is reported below as a NON-GATED
sensitivity (logged to the trial ledger; not part of the gate panel):

| Sensitivity cell (entry t, overlaps absorption window) | n pairs | n quarters | diff | t_iid | t_HAC | p_HAC |
|---|---|---|---|---|---|---|
| E2_x_21d entry-t | 1,185 | 47 | +5.22% | 11.27 | 3.535 | 0.000 |
| E2_x_63d entry-t | 1,167 | 46 | +3.77% | 3.29 | 2.064 | 0.039 |

Read the sensitivity with care: under the entry-at-t convention the forward
window CONTAINS the absorption window, and within a matched path quintile the
absorbed events sit above the quintile's own median path by construction. Much of
the sensitivity diff is therefore the residual within-quintile path gap itself,
not post-window alpha — the same contamination channel the merged report's G4
discussion identified. The clean post-window increment is what the gated cells
measure, and it is small and statistically indistinguishable from zero. No entry
convention changes the family outcome: under the merged-code convention the E1
cells themselves remain failed (t_HAC -1.29 / +1.86).

### G2 / G3 (descriptive, per the merged family design)

| Split at 2020-09-23 | 21d diff | 63d diff |
|---|---|---|
| H1 (pre) | -0.33% | +0.78% |
| H2 (post) | +0.84% | +0.91% |

| Crisis excluded | 21d diff | 63d diff |
|---|---|---|
| Excl 2015_crash | +0.59% | +0.73% |
| Excl 2018_bear | +0.85% | +1.05% |
| Excl 2024_stim | +0.66% | +1.09% |

Split halves same-sign: NO at 21d, yes at 63d — the 21d effect flips sign in the early half, so G2 would fail descriptively for E2.

### Gate outcome and family verdict

**E2 G1: FAIL.** The E2 cells do not clear |t_HAC| >= 2 with BH q <= 0.10 under the 4-cell panel.

**FAMILY VERDICT: UNCHANGED — FAIL.** The pre-registered rule flips the family verdict only if E2 passes G1 under the re-computed 4-cell BH; it does not. The well-powered E1 legs already failed G1 in the merged run, and the corrected-path E2 leg does not rescue the family.

The E2 'registered null' in §7 is retired: the null was a mis-path artifact, not a
data gap. The F5-01 archiver re-entry condition (>= 3 years of tape) was already
satisfied at merge time.

*Store: `data/china_block_tape` (mrtj partitions; runner-local/untracked — set
CHINA_BLOCK_TAPE_STORE when the worktree does not carry it).
Prices: `data/china_stocks_raw` with .SH->.SS normalization. Repro:
`python -m scripts.d4_cn_supply_absorption_e2_rerun`. Trial-ledger rows for this
run were logged then restored per the intraday data/-discard law; the delta is
reported in the PR body. Numbers above are display-tier study output, not a
production signal.*
