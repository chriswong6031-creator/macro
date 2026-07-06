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
| Fire tape | `data/research/gate_fires_baskets.parquet` | 113,542 fires, 2014-08-11 to present |
| PIT fundamentals | `data/edgar/fundamentals_panel.parquet` | Accessed via `period_end + 120d` lag |
| Sector benchmarks | `data/baskets/ohlcv/*.parquet` (11 GICS EW sector baskets) | Sector-relative returns computed vs sector basket |

### 2.2 Tactical win precondition

"Tactical win" reuses the entry-stack grader (`engine/grading.py`) exactly. A fire
is a **tactical win** if it achieves `TerminalState.CLEAN_LIFTOFF` under the
**positional** grader: close ≥ entry_price × 1.15 strictly before close ≤
entry_price × 0.95, within 126 trading days of fire date (the `clean15_126`
convention). This is the existing production grader; it is not redefined here.

A fire that is a tactical win is always assigned exactly one long-hold label based
on its subsequent 252d total return from fire date (not from tactical exit).

A fire that is **not** a tactical win is assigned `tactical_only = False` and
receives label `tactical_only` (meaning: the entry never lifted off; the hold-thesis
question is moot for this fire).

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

These rows receive `label='tactical_only_fail'` (the fire did not lift off) and are
excluded from all label-comparison analyses. They are retained in output for
coverage accounting.

### 2.4 Label assignment algorithm (computable, unambiguous)

```
for each fire row (ticker, fire_date):
    resolve price path (yahoo then Massive; mark no_price if absent)
    compute tactical_win via grading.terminal_state(clean15_126)
    if not tactical_win:
        label = 'tactical_only_fail'
        continue

    compute total_return_252d = close[fire_date + 252d] / close[fire_date] - 1
    compute sector_rel_252d = total_return_252d - sector_basket_252d_return
    compute cohort_year = fire_date.year
    compute tercile_rank = rank(total_return_252d) within cohort_year fires
    (tercile cutoffs computed on tactical-win fires only, within cohort_year)

    if tercile_rank >= 0.67 and sector_rel_252d >= 0:
        if piotroski_f >= 6 OR coverage_waived:
            label = 'compounder'
        else:
            label = 'multiple_expansion_only'
    elif tercile_rank < 0.33:
        label = 'cheap_trap'
    else:
        label = 'tactical_only'
```

Label output is written to `data/research/long_hold_labels.parquet` with fields:
`ticker, fire_date, label, total_return_252d, sector_rel_252d, tercile_rank,
cohort_year, tactical_win, piotroski_f, fund_unchecked, survivorship_biased,
coverage_frac, label_reason`.

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
(`as_of_cross_section(fire_date)`) so that no future-fundamental data leaks in.

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

### 6.3 Minimum episode-cluster floor

**n ≥ 25 independent episode-clusters per horizon** is required before any
statistic is reported as inferential. "Independent episode-cluster" means a
(name × macro-regime) block that does not overlap within ±10 trading days of
another block for the same name. Raw fire counts are banned as inferential n and
may not appear in any results table as if they were the sample size for a test.

If a horizon does not meet the n ≥ 25 floor, results for that horizon are refused
(not reported, not stamped as "directional", not shown with a larger caveat — simply
refused and absent from output).

### 6.4 Within-regime reshuffle null

Any classifier or feature separation result must beat the within-regime
label-reshuffle null. The null is constructed by randomly permuting the
`missed_hold` label within each `(cohort_year × macro_regime)` cell 1,000 times
and computing the feature test statistic distribution. The claim is that the
observed statistic exceeds the 90th percentile of the null distribution
(one-sided; consistent with q=0.10). A result that passes BH-FDR but fails the
reshuffle null is marked as "reshuffle-null-fail" and does not count as evidence.

---

## 7. Temporal split

| Split | Fire date range | Role |
|---|---|---|
| Fit / exploration | 2014-01-01 – 2019-12-31 | Feature selection, direction-finding, hyperparameter tuning |
| OOS | 2020-01-01 – 2023-12-31 | Held-out evaluation; touched ONCE after design is locked |
| Recent (do not use in W1) | 2024-01-01 – present | Reserved for post-publication monitoring; not used in W1 |

The OOS split is opened once, after the fit-period analysis is complete and the W1
study script is committed. Any analysis run on the OOS split counts as the single
OOS test; no iterative refinement is permitted.

The fire tape (`gate_fires_baskets.parquet`) spans 2014-08-11 to present; the fit
period therefore starts at the first available fire.

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
| PIT fundamentals accessor | `collectors/edgar.py as_of_cross_section()` |
| FDR machinery | `engine/neuralweb/metabolism.py` (extend to `fdr_family='long_hold'`) |
| Survivorship field precedent | `ic_scorecard.json` (`survivorship_biased`, `coverage_frac`) |
| IC scorecard (context) | `data/ic_scorecard.json` — quality mean_ic = 0.0042; composite anti-predictive (-0.0072); context only |
| Dead-name architecture (exists; data missing) | `engine/grading.py resolve_series()`, `terminal_state()` |
| Dead-name price target | `data/edgar/dead_name_prices.parquet` (absent; 15/1,083 names covered) |
| Sector baskets | `data/baskets/ohlcv/*.parquet` (11 GICS EW) |
| Fire tape | `data/research/gate_fires_baskets.parquet` |

---

*Document locked on merge. Any change requires a new pre-registration file.*
