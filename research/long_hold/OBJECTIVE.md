# Long-Hold Thesis Layer — Pre-Registration (W0 PR-B)

**Status:** PRE-REGISTERED — locked before any label is computed  
**Registered:** 2026-07-05  
**Program:** Long-Hold Thesis Layer (masterplan: `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`)  
**Wave:** W0 PR-B (discipline tier; ships unconditionally)  
**FDR family:** `long_hold` (isolated; no mixing with entry-desk batches — see §6)

> This document locks the study design. Nothing below may be changed after this file
> is merged. Post-hoc label-definition changes, horizon additions, feature additions,
> or cohort-boundary changes are FORBIDDEN. A change requires a new pre-registration
> (new file, new PR), with the original retained and linked.

---

## 1. Objective tiers

Three tiers, in priority order. The tiers are independent; lower tiers are not
reached if higher ones fail, but tier 1 ships regardless of all empirical results.

### Tier 1 — Discipline (ships unconditionally, W0)

A mechanical, CI-enforced horizon firewall. Every registered artifact in
`config/synapse.yml` carries a `horizon_role` stamp:
`tactical_entry | hold_thesis | dual | context`. The CI gate
(`check_synapse_reads.py`) hard-fails if a `hold_thesis` artifact is consumed by
any entry-stack surface (board ordering, top setups, alert triage, push floor), or
if a `tactical_entry` artifact is consumed by a hold surface. The wall is
bidirectional and enforced by tests, not documentation.

This tier directly resolves the reported entry/hold confusion and has value even if
every alpha hypothesis in tiers 2 and 3 dies.

### Tier 2 — Duration-extension (W2; proceeds regardless of tier-3 outcome)

For names the entry stack has already caught, separate the entry clock (~2-4wk
horizon) from the thesis clock (12-36 months) and surface falsifier evidence on
the hold reason. Shaped as de-escalation and annotation only — never an escalating
signal. The deliverable is machinery that surfaces: "your entry reason has expired;
here is the current state of evidence for continuing to own this name."

### Tier 3 — Selection alpha (option; gated by W1 kill-test)

Whether hold quality (compounder vs cheap trap) was visible at entry is an
empirical question. W1 answers it. Until W1 prints non-null, no selection
machinery is built. If G1 kills this tier, tiers 1 and 2 are unaffected and the
program continues on those deliverables only.

---

## 2. Outcome label definitions

Labels are assigned per `(ticker, fire_date)` row from `data/research/gate_fires_baskets.parquet`.
A row must have a resolvable price path to receive any label; rows without a
usable price path are recorded as `unlabeled` with `label_reason='no_price'`.

### 2.1 Data sources

| Source | Path | Notes |
|---|---|---|
| Price paths | `data/yahoo/*.parquet` (primary); Massive whole-market store (survivorship-correct post-2021-07) | `close` is dividend-adjusted total return |
| Fire tape | `data/research/gate_fires_baskets.parquet` | 113,542 fires, 2014-08-11 to 2026-07-02 (frozen snapshot at registration; the population is reproducible from this snapshot date) |
| PIT fundamentals | `data/edgar/fundamentals_panel.parquet` | Accessed via `period_end + 120d` lag |
| Sector benchmarks | `data/baskets/ohlcv/*.parquet` (11 GICS EW sector baskets) | Sector-relative returns computed vs sector basket |

### 2.2 Tactical win precondition

"Tactical win" reuses the entry-stack grader (`engine/grading.py`) exactly. A fire
is a **tactical win** if it achieves `TerminalState.CLEAN_LIFTOFF` under the
**positional** grader: close ≥ entry_price × 1.15 strictly before close ≤
entry_price × 0.95, within 126 trading days of fire date (the `clean15_126`
convention). This is the existing production grader; it is not redefined here.

**Maturity handling:** `grading.terminal_state(clean15_126)` returns `state=None`
(not a boolean) for fires with fewer than 126 matured forward bars. A `None` return
is NOT treated as "not a tactical win"; it is treated as `unlabeled` with
`label_reason='unmatured_126'`. Separately, computing `total_return_252d` requires
252 matured forward bars. A fire with ≥ 126 bars but < 252 bars is a potential
tactical win but cannot receive a 252d-horizon label; such fires are assigned
`label_reason='unmatured_252'` and are excluded from all label-comparison analyses.
Both unmatured categories are retained in output for coverage accounting. They do
NOT fall into `tactical_only_fail` or any tercile bucket.

A fire that is a tactical win AND has ≥ 252 matured bars is always assigned exactly
one long-hold label based on its subsequent 252d total return from fire date (not
from tactical exit).

A fire where `terminal_state` returns a non-None, non-CLEAN_LIFTOFF state (i.e.,
STOPPED, DEAD_MONEY, or CUSHIONED) with ≥ 126 matured bars is assigned label
`tactical_only_fail` (meaning: the entry never lifted off; the hold-thesis question
is moot for this fire).

### 2.3 Label definitions

All thresholds are computed within the **cohort-year** (calendar year of fire date)
to avoid cross-year distribution shift. "Sector-relative 252d return" means the
name's total return over 252 trading days from fire date minus the corresponding
sector basket's total return over the same window.

**Required precondition for labels A–D:** tactical win = True.

---

**Label A — `compounder`**

> The name continued to compound well beyond the tactical window.

Conditions (all must hold):
1. Total return from fire date to 252 trading days: top tercile within cohort-year
   (rank ≥ 67th percentile of all tactical-win fires in that cohort-year).
2. Sector-relative 252d return ≥ 0 (beat own sector).
3. (For fires with available 126d fundamentals via PIT panel) Piotroski F-score at
   `period_end + 120d` ≥ 6 **OR** fundamentals unavailable (this condition is
   waived if coverage < 30% of cohort-year; the waiver is stamped in output).

A `compounder` that does not meet condition 3 solely due to waived coverage is
stamped `fund_unchecked=True`.

---

**Label B — `multiple_expansion_only`**

> The name ran hard but the run was driven by multiple expansion rather than
> compounding; the ride is over once the multiple reverts.

Conditions (all must hold):
1. Total return from fire date to 252d: top tercile within cohort-year (same as A,
   condition 1).
2. Sector-relative 252d return ≥ 0 (beat own sector).
3. (Where PIT fundamentals are available) Piotroski F-score at `period_end + 120d`
   < 6 AND coverage ≥ 30% of cohort-year.

If fundamentals coverage < 30%, the fire is classified `compounder` (label A) with
`fund_unchecked=True` rather than `multiple_expansion_only`, because we cannot
confirm the multiple-expansion diagnosis.

---

**Label C — `cheap_trap`**

> The name achieved a tactical win but failed to hold gains or deteriorated over the
> hold horizon; it looked cheap but was a trap.

Conditions (all must hold):
1. Tactical win = True.
2. Total return from fire date to 252d: bottom tercile within cohort-year
   (rank < 33rd percentile of all tactical-win fires in that cohort-year).

No fundamental condition is applied to `cheap_trap` — we are documenting the
outcome, not diagnosing the cause; cause analysis is W2.

---

**Label D — `tactical_only`**

> The fire produced a usable ~2-4wk bounce but the name did not sustain; holding
> beyond the tactical window added no return. This is the null hypothesis against
> which the selection-alpha thesis competes.

Conditions (all must hold):
1. Tactical win = True.
2. Total return from fire date to 252d: middle tercile within cohort-year
   (33rd ≤ rank < 67th percentile of all tactical-win fires in that cohort-year).

Note: Label D is **strictly** the middle tercile. It does NOT absorb top-tercile
fires that merely lagged their sector — those are Label G (see below).

---

**Label G — `sector_laggard_winner`**

> The fire produced a strong absolute return (top tercile) but lagged its own
> sector benchmark. The name was carried by its sector rather than compounding on
> its own merits.

Conditions (all must hold):
1. Tactical win = True.
2. Total return from fire date to 252d: top tercile within cohort-year
   (rank ≥ 67th percentile of all tactical-win fires in that cohort-year).
3. Sector-relative 252d return < 0 (lagged own sector).

This label closes the mutual-exclusivity gap: a top-tercile fire with
`sector_rel_252d < 0` is neither `compounder` nor `multiple_expansion_only`
(both require `sector_rel_252d ≥ 0`) nor `tactical_only` (middle tercile only).
Without this label that cell would be an unregistered residual in the algorithm.
`sector_laggard_winner` fires are excluded from the W1 kill-test contrast
(`missed_hold` vs `tactical_only`) because their path into the top tercile was
sector-driven, not quality-driven; they are retained in output for coverage
accounting.

---

**Label E — `missed_hold`**

> The fire produced a tactical win AND the name compounded strongly — but only in
> retrospect. This is the key label for the W1 kill-test: can we predict, at entry,
> which tactical wins will become compounders rather than tactical-onlys?

`missed_hold` is not a separate label assignment. It is a derived flag:
```
missed_hold = (label == 'compounder')
```
applied at analysis time on the labeled dataset. The question W1 asks:
"Did at-entry features separate `missed_hold=True` from `label == 'tactical_only'`
among fires where both were reachable (i.e., both labels are represented in the
cohort)?"

---

**Label F — fires that never achieved tactical win**

These rows receive `label='tactical_only_fail'` (the fire reached a non-None
non-CLEAN_LIFTOFF terminal state within the 126d window, e.g. STOPPED, DEAD_MONEY,
or CUSHIONED) and are excluded from all label-comparison analyses. They are retained
in output for coverage accounting. Fires where `terminal_state` returns `None` due
to insufficient maturity are `unlabeled` with `label_reason='unmatured_126'` and are
distinct from `tactical_only_fail`.

### 2.4 Label assignment algorithm (computable, unambiguous)

**`coverage_waived` definition (locked, not tunable):**
`coverage_waived` for cohort-year Y = True when the fraction of fires in cohort-year
Y that have a non-null `piotroski_f` value in `fundamentals_panel.parquet` (accessed
at `period_end + 120d` PIT) is < 0.30.
Formally:
```
fundamentals_coverage(Y) = count(fires in Y with non-null piotroski_f) /
                            count(fires in Y with tactical_win == True AND
                                  total_return_252d is not None)
coverage_waived(Y) = fundamentals_coverage(Y) < 0.30
```
This is computed once per cohort-year before any label assignment; the per-cohort-year
value is frozen and stored in the output parquet as `cohort_fundamentals_coverage_frac`.
Fires in a coverage-waived year that land in the top-tercile + sector-positive cell
receive `label='compounder'` and `fund_unchecked=True`.

**Implication for `missed_hold` (the kill-test outcome variable):** `fund_unchecked`
fires DO count as `missed_hold=True` (i.e. label == 'compounder') in the W1 contrast.
A sensitivity run EXCLUDING `fund_unchecked=True` fires from the missed_hold contrast
is pre-registered as a mandatory secondary analysis. If the primary result and the
fund_unchecked-excluded result disagree in direction, the primary result is marked
"coverage-sensitive" and not treated as evidence. This sensitivity run is reported
unconditionally alongside the primary result.

```
# PRE-PASS: compute cohort_fundamentals_coverage_frac per cohort-year
for each cohort_year Y:
    cohort_fundamentals_coverage_frac[Y] = (
        count fires in Y where tactical_win=True AND 252d bars matured AND piotroski_f is not null
    ) / (
        count fires in Y where tactical_win=True AND 252d bars matured
    )
    coverage_waived[Y] = cohort_fundamentals_coverage_frac[Y] < 0.30

# MAIN PASS: label each fire
for each fire row (ticker, fire_date):
    # Step 1: resolve price path
    resolve price path (yahoo then Massive; mark no_price if absent)
    if no_price:
        label = 'unlabeled'; label_reason = 'no_price'; continue

    # Step 2: tactical win check
    result_126 = grading.terminal_state(clean15_126)
    if result_126['state'] is None:
        label = 'unlabeled'; label_reason = 'unmatured_126'; continue
    if result_126['state'] != TerminalState.CLEAN_LIFTOFF:
        label = 'tactical_only_fail'; continue

    # Step 3: 252d return check
    if fewer than 252 matured forward bars available:
        label = 'unlabeled'; label_reason = 'unmatured_252'; continue

    compute total_return_252d = close[fire_date + 252d] / close[fire_date] - 1
    compute sector_rel_252d = total_return_252d - sector_basket_252d_return
    compute cohort_year = fire_date.year
    compute tercile_rank = rank(total_return_252d) within cohort_year fires
    (tercile cutoffs computed on tactical-win, 252d-matured fires only, within cohort_year)

    # Step 4: label assignment — all cells are explicit; no residual
    if tercile_rank >= 0.67 and sector_rel_252d >= 0:
        # Top absolute AND beats sector
        if piotroski_f >= 6 OR coverage_waived[cohort_year]:
            label = 'compounder'
            fund_unchecked = coverage_waived[cohort_year] AND piotroski_f is null
        else:
            label = 'multiple_expansion_only'
            fund_unchecked = False
    elif tercile_rank >= 0.67 and sector_rel_252d < 0:
        # Top absolute BUT lagged sector — Label G
        label = 'sector_laggard_winner'
    elif tercile_rank < 0.33:
        label = 'cheap_trap'
    else:
        # 33rd <= rank < 67th — middle tercile
        label = 'tactical_only'
```

Every branch above maps to exactly one named label. The label set
{compounder, multiple_expansion_only, sector_laggard_winner, cheap_trap,
tactical_only, tactical_only_fail, unlabeled} is exhaustive and mutually exclusive
over all fires with a resolvable price path.

Label output is written to `data/research/long_hold_labels.parquet` with fields:
`ticker, fire_date, label, total_return_252d, sector_rel_252d, tercile_rank,
cohort_year, tactical_win, piotroski_f, fund_unchecked, survivorship_biased,
coverage_frac, cohort_fundamentals_coverage_frac, label_reason`.

---

## 3. Horizons

| Horizon | Status | Notes |
|---|---|---|
| **126d** | Primary | ~6 months; aligns with existing SPINE_HORIZONS max |
| **252d** | Primary | ~1 year; primary label horizon for W1 kill-test |
| **504d** | Caveat-stamped | ~2 years; available for description only; must carry `survivorship_biased=True` and `horizon_status='caveat_504d'` in every artifact |
| **756d** | **REFUSED** | ~3 years; refused until `data/edgar/dead_name_prices.parquet` achieves ≥ 50% coverage of the 1,083-name dead universe (LH-R3). No 756d results may be published under any wave of this program until that coverage gate is met |

The 252d label is the **kill-test horizon**. The 126d label is computed alongside it
for comparison and for the subset of post-2021 cohort where 252d bars may not yet be
fully matured.

---

## 4. Honest cohorts and survivorship stamps

### 4.1 Eligible cohorts for outcome CLAIMS

| Cohort | Price source | Horizon eligible | Notes |
|---|---|---|---|
| Post-2021-07 Massive | Massive whole-market store | ≤ 252d | Survivorship-correct per day; rolling entitlement anchored 2021-07-06. The 1,165-day gap (2021-10-25 → 2025-01-02) means fires in this window have impaired price resolution; these fires are labelled but flagged `gap_period=True` |
| 2025-2026 cohort | Yahoo + Massive | ≤ 126d fully matured | Delisters captured at terminal price in this window |

### 4.2 Survivor-only UPPER BOUND cohorts

All fires with `fire_date < 2021-07-06` may be used for exploration and
direction-finding only. Every output using pre-2021 data carries:
- `survivorship_biased = True`
- `coverage_frac` = fraction of fires with a resolvable price path
- A visible label: `"UPPER BOUND — survivor-only cohort"`

Estimated bias: 200-500 bps/yr overstatement in absolute returns (masterplan §2).
Sector-relative returns are less biased but not bias-free.

### 4.3 Mandatory fields on every artifact

Every parquet, JSON, or markdown table in `data/research/long_hold_*` carries:

```
survivorship_biased: bool
coverage_frac: float  # fires with resolvable price / total fires in cohort
cohort_description: str
horizon_status: str   # 'primary_126d' | 'primary_252d' | 'caveat_504d' | 'refused_756d'
```

---

## 5. At-entry feature family for W1 (FROZEN)

The following feature list is frozen at registration. No features may be added
after this document merges. Features may be dropped from analysis if they have
< 20% non-null coverage in the honest cohort, but dropping must be documented
in the W1 verdict; it does not constitute post-hoc modification of this list.

| Feature | Source | Field name in fundamentals_panel | Notes |
|---|---|---|---|
| Piotroski F-score | `data/edgar/fundamentals_panel.parquet` | `piotroski_f` | PIT via `period_end + 120d` |
| Quality z-score | `data/edgar/fundamentals_panel.parquet` | `quality_z` | As-of cross-section |
| Profitability z-score | `data/edgar/fundamentals_panel.parquet` | `profitability_z` | As-of cross-section |
| SUE (standardized unexpected earnings) | `data/edgar/fundamentals_panel.parquet` | `sue` | Most-recent quarter at fire date |
| Insider CMP flag | `data/edgar/fundamentals_panel.parquet` | `insider_cmp` | Cluster-matched purchase signal |
| Leverage (interest coverage proxy) | `data/edgar/fundamentals_panel.parquet` | `interest_coverage` | op_income / interest_exp; available where interest_exp > 0 |
| Dilution flag | `data/edgar/fundamentals_panel.parquet` | `dilution_flag` | shares YoY > +3% threshold |
| Gross-margin trend | `data/edgar/fundamentals_panel.parquet` | `gross_margin_trend` | 3-year slope of gross_profit/revenue |
| Archetype class | `data/edgar/fundamentals_panel.parquet` | `archetype` | Existing classification field |

All features are read at fire date using the PIT cross-section
(`as_of_cross_section(fire_date, panel=fundamentals_panel)`) so that no
future-fundamental data leaks in.

**No post-registration additions are permitted.** If a desired feature is absent from
this list, it requires a new pre-registration.

---

## 6. Inference rules

### 6.1 FDR family

All hypothesis tests in this program register under `fdr_family='long_hold'` in the
qledger. A CI test asserts that no `long_hold` key appears in any entry-desk FDR
batch (`fdr_family` in `{'entry_stack', 'oracle', 'cortex', 'china_cycles', ...}`).
The isolation is one-way and two-way: entry-desk tests never inherit long_hold
family batch corrections, and long_hold tests never inherit entry-desk corrections.

BH-FDR q = 0.10 across the full W1 feature family (9 features listed in §5).
Each feature's test against the `missed_hold` binary outcome is one hypothesis
in the family. The family-wise q threshold is 0.10 applied to the BH step-up
procedure over all 9 p-values simultaneously.

### 6.2 Cluster-robust confidence intervals

Standard errors are clustered by `(ticker_sector × macro_regime)` blocks.
Macro-regime labels are read from the existing regime vector at fire date.
Where a named-cluster solution is unavailable (e.g., regime label missing),
block-bootstrap CIs with block width 63 trading days are used instead.
Both methods must be tried; the wider CI governs.

**Note on clustering granularity across inference gates (intentional design):**
Three distinct block definitions are used across the three inference gates — this is
intentional and each is chosen for its purpose:
- §6.2 (CI clustering): `(ticker_sector × macro_regime)` — sector-level, because
  sector-correlated errors are the dominant source of within-cluster dependence in
  cross-sectional feature tests.
- §6.3 (episode-cluster n-floor): `(name × macro_regime)` — name-level, because the
  n-floor protects against pseudo-replication from the same stock firing repeatedly.
- §6.4 (reshuffle null): `(cohort_year × macro_regime)` — year-level, because the
  permutation must preserve annual cross-sectional structure to avoid destroying the
  seasonal dependence in the feature distribution.
**Effective-n for reporting** (the headline sample size quoted in any results table)
is the §6.3 episode-cluster count — i.e., the count of retained fires after the
(name × macro_regime) ±10d de-duplication. This is the most conservative of the
three granularities and is the correct denominator for the n ≥ 25 floor.

### 6.3 Minimum episode-cluster floor

**n ≥ 25 independent episode-clusters per horizon** is required before any
statistic is reported as inferential. "Independent episode-cluster" means a
(name × macro-regime) block whose `fire_date` does not fall within ±10 trading days
(measured on `fire_date`, not on episode-block span) of another fire for the same
(name × macro-regime) combination. Raw fire counts are banned as inferential n and
may not appear in any results table as if they were the sample size for a test.

**Tie-break rule for de-duplication within ±10d:** when multiple fires for the same
(name × macro-regime) fall within a ±10 trading-day window, retain the
**earliest** fire_date in the window. Remove the later fires. Apply greedily
left-to-right: after removing a later fire, do not re-evaluate earlier retained
fires. This rule is deterministic and produces a unique de-duplicated set for any
input ordering.

If a horizon does not meet the n ≥ 25 floor, results for that horizon are refused
(not reported, not stamped as "directional", not shown with a larger caveat — simply
refused and absent from output).

### 6.4 Within-regime reshuffle null

Any classifier or feature separation result must beat the within-regime
label-reshuffle null. The null is constructed by randomly permuting the
`missed_hold` label within each `(cohort_year × macro_regime)` cell 1,000 times
and computing the feature test statistic distribution.

**Per-feature application (9 separate nulls, not one aggregate):** The reshuffle
null is run independently for each of the 9 features in the frozen W1 family (§5).
For each feature, the test statistic is the Mann-Whitney U (rank-biserial correlation)
between feature values for `missed_hold=True` fires vs `label='tactical_only'` fires.
The claim is that the observed per-feature statistic exceeds the 90th percentile of
that feature's null distribution (one-sided; consistent with q=0.10). The 90th-pctile
threshold is applied independently per feature — there is no additional BH correction
on top of the reshuffle gate (BH-FDR §6.1 and the reshuffle gate are independent
hurdles, both of which must be cleared). A feature that passes BH-FDR but fails its
own reshuffle null is marked "reshuffle-null-fail" and does not count as evidence.

The reshuffle seed is fixed at 42 for reproducibility.

---

## 7. Temporal split

| Split | Fire date range | Role |
|---|---|---|
| Fit / exploration | 2014-01-01 – 2019-12-31 | Feature selection, direction-finding, hyperparameter tuning |
| OOS | 2020-01-01 – 2023-12-31 | Held-out evaluation; touched ONCE after design is locked |
| Recent (do not use in W1) | 2024-01-01 – 2026-07-02 (snapshot) | Reserved for post-publication monitoring; not used in W1 |

The OOS split is opened once, after the fit-period analysis is complete and the W1
study script is committed. Any analysis run on the OOS split counts as the single
OOS test; no iterative refinement is permitted.

The fire tape (`gate_fires_baskets.parquet`) spans 2014-08-11 to 2026-07-02 (frozen
snapshot at registration — see §2.1); the fit period therefore starts at the first
available fire.

---

## 8. G1 kill criterion (pre-registered)

> **If no at-entry feature from the frozen W1 family (§5) separates `missed_hold`
> from `tactical_only` in the honest cohorts (§4.1) under all three gates — BH-FDR
> q ≤ 0.10 across the family, the within-regime reshuffle null (§6.4), and the
> n ≥ 25 episode-cluster floor (§6.3) — on the OOS split (2020-2023), then the
> selection-alpha thesis is KILLED. W3 and W4 of the program are cancelled. The
> program collapses to W0 (discipline) and W2 (clocks and falsifiers) only.**

A null result is first examined for survivorship mechanics before ratification:
missing dead-name prices systematically understate the `cheap_trap` label count
(dead names are more likely to have been traps), which biases the `missed_hold`
contrast toward zero. If the null is attributed to survivorship mechanics rather
than true absence of signal, the finding is printed as: "selection-alpha may exist
but cannot be measured honestly without dead-name prices; verdict deferred to PR-G
dead-name spike." This deferral is not a reprieve — W3/W4 remain suspended until
PR-G resolves the price gap.

**OOS honest-cohort n-floor warning (pre-registered):** The G1 criterion requires
the kill-test to run on the OOS split (2020-2023) within honest cohorts (§4.1). The
only honest cohort for 252d labels is post-2021-07 Massive, which is gutted by the
1,165-day gap (2021-10-25 → 2025-01-02, all fires flagged `gap_period=True`). The
practical honest-OOS window for 252d resolution is approximately 2021-07-06 →
2021-10-25 (~3.5 months of fires, then nothing until post-gap fires reach 252d
maturity). This may produce fewer than 25 honest-OOS episode-clusters at 252d. If
the OOS honest-cohort n-floor is not met, the G1 criterion cannot fire from honest
data alone; per §8 the finding is automatically routed to the survivorship-deferral
path: "verdict deferred to PR-G dead-name spike." This routing is pre-registered and
not a post-hoc rescue — the program was designed knowing this gap exists. The PR-W1
analysis script must report the achieved honest-OOS episode-cluster count before
running any OOS statistic.

A null is not a failure of the program. It is a valid and publishable finding.
It is printed loudly in the verdict document, not hidden.

---

> **In plain English (kill criterion):**
>
> We are asking one question: when a stock fires our entry signal and then goes on to
> be a multi-year winner, could we have known that at the moment of entry — before it
> moved — using quality metrics we already track?
>
> If the answer is no (none of our nine quality metrics reliably distinguishes the
> multi-year winners from the ones that just bounced and faded), we stop building the
> selection machinery entirely. We keep the firewall (it still prevents entry/hold
> confusion) and we keep the "when does the thesis break?" tooling (it still helps us
> know when to sell). But we don't build an admission committee or a compounder
> score, because the data says there is nothing to select on.
>
> The only exception: if the answer looks like "no signal" but might actually be "we
> can't see the failures because the database doesn't include companies that went
> bankrupt," we note that caveat clearly and defer the verdict until we can get the
> dead-company prices.

---

## 9. Wrong-ruler firewall statement

Labels in `data/research/long_hold_*` operate on a 12-36 month clock. They measure
multi-year outcome quality. They may never:

- Feed entry-stack z-scores, entry quality bands, or the SPINE column family.
- Appear in board ordering, the buy-strip ranking, or top-setups confluence gates.
- Contribute to alert triage or push-floor decisions.
- Appear in any ~2-4wk backtest or rotational/positional study.

This firewall is stated here as a pre-registered constraint (LH-R1) and is enforced
by the CI gate implemented in W0 PR-D (`check_synapse_reads.py` extension). A test
asserts that `entry_strata_phase0.py` and the keystone harness never read any path
matching `data/research/long_hold_*`.

The ruler mismatch is causal: a fire that produces a multi-year compounder looks
identical at ~21d and ~126d to one that fades. Using long-horizon labels to grade
short-horizon features is a form of lookahead contamination. The wall is absolute.

---

## 10. Provenance and dependencies

| Item | Reference |
|---|---|
| Masterplan | `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md` |
| Entry grader (reused as-is for tactical win) | `engine/grading.py`, `TerminalState.CLEAN_LIFTOFF`, `clean15_126` |
| Entry harness template | `scripts/research/entry_strata_phase0.py` |
| PIT fundamentals accessor | `collectors/edgar.py as_of_cross_section(asof, panel=None)` — pass `panel=fundamentals_panel` explicitly to avoid default-load-path dependency; positional `asof` = fire_date |
| FDR machinery | `engine/neuralweb/metabolism.py` (extend to `fdr_family='long_hold'`) |
| Survivorship field precedent | `ic_scorecard.json` (`survivorship_biased`, `coverage_frac`) |
| IC scorecard (context) | `data/ic_scorecard.json` — quality mean_ic = 0.0042; composite anti-predictive (-0.0072); context only |
| Dead-name architecture (exists; data missing) | `engine/grading.py resolve_series()`, `terminal_state()` |
| Dead-name price target | `data/edgar/dead_name_prices.parquet` (absent; 15/1,083 names covered) |
| Sector baskets | `data/baskets/ohlcv/*.parquet` (11 GICS EW) |
| Fire tape | `data/research/gate_fires_baskets.parquet` |

---

*Document locked on merge. Any change requires a new pre-registration file.*

---

## Amendments

Amendments are additive pre-registrations appended after the base document is locked.
They must be registered before any feature-vs-outcome statistics are computed.
Each amendment carries its discovery PR, registration date, and the mandate scope.

---

### Amendment A1 — Sector-benchmark coverage sensitivity (mandatory)

**Registered:** 2026-07-05  
**Registered before any feature-vs-outcome statistics computed:** YES  
**Discovering PR:** #1517 (W1 label harness + outputs)  
**Ruling:** LH-W1-2

#### Background

§2.1 assumed pre-built sector basket candles (`data/baskets/ohlcv/*.parquet`, 11 EW GICS
sector baskets) would be available for all fire-tape tickers. The W1 label harness (#1517)
found that only 503 of 2,495 fire-tape tickers map to the 11 EW baskets. As a result,
3,391 of the 3,409 `sector_laggard_winner` (Label G) fires have no sector benchmark and
received Label G solely because `sector_rel_252d` was undefined (treated as < 0 under the
primary algorithm). This is a coverage collapse in the benchmark source, not a signal.

#### Sensitivity run A1 (mandatory, runs in the same wave as the primary W1 kill-test)

Reassign every no-benchmark Label G fire using an **equal-weight all-resolvable-tickers
market benchmark** in place of the missing sector benchmark:

- Replace `sector_rel_252d` with `market_rel_252d` for every fire where `sector_rel_252d`
  is null at labeling time.
- `market_rel_252d` = name's 252-trading-day total return **minus** the equal-weight
  average 252-trading-day total return across the benchmark constituent set S(f) for fire
  f, defined as follows:
  - **Fill anchor (identical to primary):** both the name leg and every constituent leg
    use the next-bar-after-fire_date anchor (`fill_index` = `searchsorted(fire_date,
    side='right')`, i.e. `fi + 1`). The forward window is `close.iloc[fi+1 : fi+1+252]`,
    exactly matching `_total_return` in the primary label harness. Reading "from fire date"
    means "fill-anchored at the next bar strictly after fire_date" — the same convention
    used by the primary code to eliminate the 1-bar look-ahead.
  - **Benchmark constituent set S(f):** for fire f, S(f) is the set of every ticker in
    the fire tape whose 252-trading-day fill-anchored forward price path
    (`close.iloc[fi+1 : fi+1+252]`) is **fully resolvable** (no NaN, length == 252) as of
    that fire's own fire_date. Membership is evaluated per-fire using that fire's fi+1
    anchor — it is not a pooled or shared set. Each constituent's 252d return is computed
    on its own fire_date-specific fi+1..fi+252 window.
  - **Survivorship caveat (inherited from §4.3):** in pre-2021 cohorts where dead names
    are absent from the price tape, S(f) is survivor-upward-biased. This mechanically
    depresses `market_rel_252d` for surviving names and can re-inflate Label G assignment.
    All A1 results from pre-2021 cohorts carry the `survivorship_biased` stamp from §4.3
    and the direction of induced bias (upward benchmark → downward `market_rel_252d` →
    excess Label G) must be noted in every table that reports A1 outcomes.
- The `>= 0` threshold is unchanged: `market_rel_252d >= 0` assigns Label A or B
  (depending on fundamentals); `market_rel_252d < 0` assigns Label G.
- All other label logic, tercile cutoffs, fundamentals gates, cohort-year groupings,
  n-floor rules, and inference gates are **identical** to the primary analysis.

Repeat the **entire primary W1 analysis** (all §6 inference gates, BH-FDR, reshuffle null,
episode-cluster n-floor) on the A1-reassigned label set. Report results alongside the
primary results in every table.

#### Interpretation rule (pre-registered, binding)

Each of primary and A1 produces one of three outcomes: **KILL**, **SURVIVE**, or
**DEFERRED** (survivorship-deferral: honest-OOS n-floor not met, verdict deferred to the
dead-name-spike wave per §8). The routing table is:

| Primary outcome | A1 outcome | Combined routing |
|---|---|---|
| KILL | KILL | Agreed KILL — ratifiable |
| SURVIVE | SURVIVE | Agreed SURVIVE — ratifiable |
| KILL | SURVIVE | Disagree — benchmark-coverage remediation (see below) |
| SURVIVE | KILL | Disagree — benchmark-coverage remediation (see below) |
| DEFERRED | any | DEFERRED — routes to dead-name-spike wave; A1 is reported but does not override deferral |
| any | DEFERRED | DEFERRED — routes to dead-name-spike wave; primary result is reported but does not override deferral |

The pre-registered expectation (§8 OOS n-floor warning) is that the honest-OOS 252d
cohort will very likely NOT meet the n-floor, routing primary to DEFERRED. Any pairing
that includes a DEFERRED outcome from either leg routes to DEFERRED (not remediation).
Remediation fires only on a clean KILL-vs-SURVIVE split with no deferral on either leg.

**Benchmark-coverage remediation path:** build a fuller sector-to-ticker mapping covering
at minimum >= 80% of episode-cluster-weighted fires (measured as the fraction of
episode-cluster-weighted `sector_laggard_winner` fires that receive a non-null
`sector_rel_252d`); re-run the label harness with the improved mapping; and re-open the
W1 study. W3/W4 remain suspended during this remediation path.

#### Scope

Amendment A1 is **additive only**. The primary analysis and all locked definitions in
§§2–9 are unchanged. The primary analysis runs first and its outputs are reported
unconditionally. A1 is an additional mandatory sensitivity run, not a replacement.

---

## Amendment A3 — W2 PR-K Pre-Registration: Moat Falsifier Sensors

**Registered:** 2026-07-06  
**Wave:** W2 PR-K  
**Module:** `engine/moat_falsifiers.py`  
**Status:** DISPLAY-ONLY — G1-DEFERRED ruling applies; no selection, ranking, or alert logic.

### §W2-PR-K.1 Sensor definitions (locked)

Four falsifier sensors, each a single measurable series derived from
`data/edgar/statements.parquet`. All are display-only annotations; no composite
"moat score" is produced (LH-R2, Signal Commons R3).

| Sensor | Condition | Rationale |
|---|---|---|
| `margin_compression_despite_revenue_growth` | `revenue_growth >= +3pp YoY AND gross_margin_pct latest < gross_margin_pct prior` | Top-line intact, pricing power / cost structure weakening |
| `receivables_stretch` | `receivables_growth > revenue_growth + 10pp AND revenue > 0` | AR outpacing revenue → channel-stuffing / collection risk |
| `inventory_build` | `inventory_growth > revenue_growth + 15pp AND revenue > 0` | Inventory accumulation vs demand signals over-production |
| `capital_intensity_rising` | `capex_growth > revenue_growth + 10pp AND (capex_growth > op_income_growth + 10pp OR op_income <= 0)` | Escalating capital requirement for same-or-less unit output |

### §W2-PR-K.2 Thresholds (locked)

| Constant | Value | Rationale |
|---|---|---|
| `_MARGIN_MIN_REVENUE_GROWTH_PP` | 3.0 pp | Minimum revenue growth to qualify as "revenue-intact"; below this, margin compression may be revenue-driven, not moat-erosion |
| `_RECV_STRETCH_PP` | 10.0 pp | Materiality buffer: AR growing 10pp faster than revenue is operationally significant |
| `_INV_BUILD_PP` | 15.0 pp | Higher bar than receivables: inventory build is more supply-chain-driven and requires a larger departure to be informative |
| `_CAPEX_INTENSITY_PP` | 10.0 pp | Consistent with receivables threshold; applied to both revenue and op_income legs |

These thresholds are locked as of Amendment A3.  They may not be tuned to improve
sensor fire rates or base rates.  Any threshold change requires a new amendment.

### §W2-PR-K.3 Base rate definition (display context, NOT a locked control)

The universe-level base rate is the fraction of `(ticker, fy)` pairs in
`statements.parquet` that satisfy the sensor condition in a given fiscal year.
It is **recomputed live on each build run** as the universe composition changes —
it is NOT a pre-registered locked control value.  It is printed as display context
alongside the per-ticker firing flag so the reader can assess how selective a
sensor is (base_rate ≈ 0.05 = 1-in-20 names fire; base_rate ≈ 0.50 = half fire,
which is uninformative).  The base rate is not an inferential anchor.

### §W2-PR-K.4 FY gap rule (locked)

Only adjacent fiscal year pairs (gap == 1 FY) are evaluated.  Rows spanning
> 1 FY (e.g. 2021→2023) are skipped to prevent inflating growth magnitudes.
This applies to both per-ticker evaluation and base-rate computation.

### §W2-PR-K.5 Great-company-trap overlay (LH-R10)

A deterministic de-escalation overlay assembled from existing signals only:

| Input | Source | Fire condition |
|---|---|---|
| `crowding_z` | `engine.theme_crowding.CROWDED_Z` | `crowding_z >= 1.0` (matches repo convention) |
| `insider_net_usd` | `sec_insider` panel / `engine.equity_factors` | `insider_net_usd <= -500,000` USD |
| `revision_direction` | `engine.analyst_revisions` | `direction == "downgrading"` |

May ONLY lower conviction display context, never raise it (LH-R10).  No LLM.
Inputs printed verbatim for Article-1/A3 transparency.  Returns `None` when both
insider and revision inputs are unavailable (panel omitted from JSON).

### §W2-PR-K.6 Coverage vocabulary (locked)

Sensor-level `coverage` field uses the same vocabulary as `sensor_coverage` (top-level):

- `"full"` — 2+ consecutive-FY rows with all required columns non-null **AND** the sensor evaluated successfully (`fy_fired_on` is not None)  
- `"partial"` — ticker has rows but sensor could not evaluate (sparse columns, or only non-adjacent FY pairs)  
- `"missing"` — no rows for this ticker in `statements.parquet`

### §W2-PR-K.7 Firewall (binding)

All outputs carry `_horizon_role="hold_thesis"`, `_display_only=True`.
These fields MUST NOT feed: board ordering, alert triage, top-setups gates,
push floor, or any entry-stack z-scored surface (LH-R1).
FDR family: `long_hold` (LH-R5).
