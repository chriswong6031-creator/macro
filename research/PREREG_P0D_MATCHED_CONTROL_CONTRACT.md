# PREREG — P0d: the matched-control evidence contract

**Registered** 2026-08-14, before any producer wiring or gate change ships. ·
**Workstream** WS:EVAL-OS-MEASUREMENT-LAW wave 5 · **Grounding census**
`EVAL_OS_P0D_CONTROL_CENSUS.md` · **Ruling executed** CEO P0d: benchmark = universal
baseline; matched control = stricter second evidence basis where a defensible matched
counterfactual exists; no manufactured controls, no rewritten history, no evaluation
silently conditioned on which rows happen to carry control data.

This document is the contract. The implementation may not weaken any numbered clause; a
later change to a clause is a governed act (PR + updated pinning test + this file), never
a drive-by.

---

## C1. The classification and its home

**C1.1** Every claim family carries exactly one `control_policy` ∈
{`matched_control_required`, `benchmark_only`, `not_applicable`}. The initial assignment
is census §4, verbatim.

**C1.2** The classification lives in **one module-level table in `engine/qledger.py`**
(`FAMILY_CONTROL_POLICY`), the same governed-table pattern as `DESK_MARKET`. It is
policy, not derivable fact, so it cannot be "derived" from data; the existing canonical
registries were audited and refused: `config/qual_ladder.yml` is field-keyed (a family
appears under many fields — a per-family policy there would be duplicated state), and
deriving policy from row contents is precisely the forbidden data-conditioned evaluation.

**C1.3** A family absent from the table is `unclassified`: benchmark mechanics, labelled
`unclassified`, and **structurally ineligible for matched-control authority**. Promotion
of a family into `matched_control_required` happens only by editing the table and its
pinning test (adversarial control #7). Row-level fields never influence policy.

**C1.4** The evaluation basis is decided by the policy alone — never by data
availability. A `benchmark_only` family whose rows all happen to carry controls still
evaluates benchmark-relative; a `matched_control_required` family with zero controls
still evaluates matched-control (and fails closed). There is no "optional control" state.

## C2. Control validity at registration (matched_control_required families)

**C2.1** The control is chosen **at registration**, from registration-time metadata only,
and freezes on the immutable claim row. Freezing is structural, not procedural: the store
is append-only (P2 law), `register`/`register_batch` dedupe is keep-FIRST by `claim_id`,
and `claim_id` excludes the control — a re-registration with a different control returns
the original row unchanged.

**C2.2** A valid control is a non-null ticker with `control ≠ scope.key` and
`control ≠ bench`. A control equal to the subject nets the claim against itself; a
control equal to the bench relabels the baseline as a stricter basis. Both register as
**missing-control** (the row registers; the absence is counted — C4).

**C2.3** Construction per required family (existing primitives only; no new
control-selection engine):

- `stock_desk` — `control_for_sector(identity.sector)`; the sector is the validated-GICS
  stamp from `site/stockdata/*.json`, threaded by #5577's `sector_of`. Why it isolates
  the claim: the desk's proposition is name-level (constructive/cautious on the stock),
  so the sector ETF removes the sector's own drift from the excess.
- `demand_chain` — GICS sector ETF via `data/universe/membership.parquet` with the
  **explicit alias normalisation** of census D0-2 (Technology→Information Technology,
  Healthcare→Health Care, Financial→Financials, Consumer Cyclical→Consumer
  Discretionary, Basic Materials→Materials, Consumer Defensive→Consumer Staples). An
  unknown or unmapped vocabulary value is a **counted refusal**, never a silent None.
  Why it isolates the claim: the desk's proposition is that a chain read predicts the
  *name's* relative strength; sector matching removes the sector bet it never made.

**C2.4** `control_for_sector()` keeps returning None for unknown input (display-tier
callers depend on null-tolerance), but every **required-family registrar path** must
count its refusals (vocabulary_unmapped vs sector_absent) into its run stats. Silence
was how D0-1 stayed dead for four months.

## C3. The matched-control cohort and its clock (prospective-only, D3)

**C3.1** Per required family, the **matched-control evidence clock** starts at the first
claim that is *cohort-eligible AND control-carrying* (C3.2/C2.2). It is recorded
write-once in `data/qledger/control_evidence_clock_start/<family>.json` (per-family file,
same race-free pattern and same write-once law as #5577's evidence clock), written by the
**registrar** (`engine/qledger.register_batch`/`register`) — not by any producer — so no
producer wiring can be bypassed around it. Nothing pre-creates these files; a timestamp
written by hand is the retrospective stamping this design forbids.

> **AMENDED 2026-08-14 (review round 1, strengthening).** C3.1 additionally requires that
> the clock be recorded with **the triggering claim's own `timestamp`**, not with the
> moment the registrar hook runs. The field is named
> `first_controlled_prospective_registration_utc`, so it must BE that registration's
> stamp. Writing `now()` placed the clock microseconds after every row of its own batch
> and, under the original instant-granularity C3.2(d), excluded the entire triggering
> batch from the cohort it had just opened (measured: 5 rows registered, clock started,
> gate answered `n_cohort_rows=0`). See the C3.2(d) amendment below — the two changes are
> one repair.

**C3.2** A claim is a **cohort member** iff ALL of:
  (a) its family is `matched_control_required`;
  (b) it is live (not placebo) and directional (`direction` ∈ {+1, −1});
  (c) it declares an explicit `horizon_unit` (legacy-clock rows are pre-contract history
      by construction);
  (d) its registration stamp `timestamp` ≥ the family's control-clock start,
      **compared as UTC DATES** (amended — see below);
  (e) it is **prospective at registration**: its resolved window's `fill_date` is
      strictly after `date(timestamp)` — the same one-clock predicate as #5577's forward
      gate, resolved through `claim_window`. Unresolvable ⇒ NOT a member, counted
      (`excluded_unresolvable`), fail-closed.
Membership never consults whether the row carries a control — that is what coverage
measures (C4). Clause (e) with the *registration stamp* (not "today") is what makes a
later import of old-asof rows structurally unable to join the cohort (adversarial
control #5): a claim registered after its window began fails (e) forever.

> **AMENDED 2026-08-14 (review round 1, strengthening).** Clause (d) compares **UTC
> DATES**, not instants. An instant comparison made cohort membership depend on
> sub-millisecond registration ORDER: the clock is stamped by one row of a batch, and
> every sibling registered microseconds earlier fell below it and left the coverage
> denominator forever. Measured: the same five-claim batch reported
> `cohort_rows=1, coverage=1.0` registered uncontrolled-first and
> `cohort_rows=4, coverage=1.0` registered controlled-first — adversarial control #6
> defeated by a sort order, with the uncovered rows silently deleted from the
> denominator rather than counted. A registration DATE is the honest granularity for
> "was this claim part of the prospective cohort", and it is stable under any intra-day
> ordering. This is strictly *widening* the cohort — it can only ADD rows to the
> denominator, never remove them — so no clause is softened. A registration stamp that
> is unparseable **or timezone-naive** cannot be placed against the clock: it is
> excluded and COUNTED (fail-closed), never an exception escaping the gate.

**C3.3** Historical claims are untouched: no backfilled controls, no re-labelling, no
combination of any pre-clock evidence with cohort evidence, no authority minted from
pre-clock rows. Research diagnostics over history stay clearly labelled research and
never enter the gate.

**C3.4** The clock records `{claim_family, first_controlled_prospective_registration_utc,
declared_horizon_d, horizon_unit, control, git_sha}` of the triggering claim. The
timestamps do not exist until the first real registration writes them; **this PR ships
with zero clock files and reports that fact, not a placeholder.**

## C4. Coverage is part of the evidence

**C4.1** At gate time, per (family, horizon, clock-basis):
`n_cohort_dates` = independent date clusters over **all** cohort members graded at that
horizon/basis; `n_controlled_dates` = the same count over cohort members carrying valid
controls; `control_coverage = n_controlled_dates / n_cohort_dates` (None when the cohort
is empty) — **amended below to the minimum of that ratio and the row ratio**. Row counts
(`n_cohort_rows`, `n_controlled_rows`) are disclosed beside the date-cluster counts. The
**issued cohort is always visible**: missing-control rows can never leave the
denominator (adversarial control #6).

**C4.2** `CONTROL_COVERAGE_MIN = 0.95`, one global constant, pre-registered here.
Rationale: tolerates a rare metadata failure (the census's ADR tail) without permitting
subset selection; at the gate's own n=25 floor a family may carry at most one uncovered
date. Not per-family-tunable — a per-family knob is subset selection with a config file.

> **AMENDED 2026-08-14 (review round 1, strengthening).** `control_coverage` is
> **`min(date-cluster coverage, ROW coverage)`**, where
> `date_coverage = n_controlled_dates / n_cohort_dates` and
> `row_coverage = n_controlled_rows / n_cohort_rows`. **Both are disclosed** (in the
> verdict's reason string; the four counts they are computed from are already published
> fields), and the MINIMUM is the number stored in `control_coverage` and compared to
> `CONTROL_COVERAGE_MIN`.
>
> A date-cluster ratio alone asks only "did this date have *a* control?", so ONE
> controlled row per date bought coverage 1.0 no matter how large the uncovered book
> sharing that date. Measured: 300 cohort rows with 30 controlled — **10% of the issued
> cohort** — reported `control_coverage=1.0` and the gate returned **eligible=True**.
> That is precisely the subset selection this clause exists to forbid, and it is the
> shape a single-name desk naturally produces (one pick a day carries a control, the
> rest of the day's book does not). The date ratio measures whether the CALENDAR is
> covered; the row ratio measures whether the CLAIMS are. The gate needs both, so it
> takes the worse one. This can only *lower* a reported coverage, never raise one — the
> bar moves up, never down.

**C4.3** The Wilson interval for the matched-control verdict is computed **only over
controlled cohort rows**, projected onto `n_controlled_dates` — never onto the full
family's date count. This retires census defect D0-3 *for this gate*; the legacy
projection inside `promotion_check(control_only=True)` becomes unreachable from
production paths (C5.4) and its remaining direct-call use is documented as
subset-projecting.

## C5. Gate semantics (fail-closed matrix)

**C5.1** `matched_control_required` — the family's **authority basis is matched
control**. The gate returns eligible=True only when ALL hold on one explicit clock
basis: clock started; `n_controlled_dates ≥ 25` (PROMOTION_MIN_DATES); `control_coverage
≥ 0.95`; Wilson `ci_low > 0.5` on controlled rows (direction-correct per P0c-1's rule,
strict inequality, `direction=0` and missing legs excluded from numerator and
denominator). Refusals name their failing clause:
  - clock not started → `matched-control evidence has not begun accruing` (never a miss,
    never a bench substitute);
  - cohort accruing with missing controls / coverage < min → `accruing_with_missing_control`,
    with both date counts and the coverage printed;
  - controlled dates < 25 → accruing, with the honest controlled count.
Benchmark-relative statistics for such a family remain computed and published **as the
labelled baseline** (`benchmark_baseline`), and can never produce `ready=True` for it
(adversarial control #1: no fallback under any data condition).

> **IMPLEMENTATION NOTE, 2026-08-14 (review round 1).** The `benchmark_baseline` label is
> realized as `benchmark_baseline_*` keys in the nightly readiness rows
> (`benchmark_baseline_hit_rate`, `_excess_mean`, `_mean_abs_excess`, `_excess_basis`,
> `_excess_mean_by_direction`), populated **only** on a matched-control verdict; the
> unprefixed keys are `None` there. Before this, the whole-family bench statistics rode
> in the unprefixed `hit_rate`/`excess_mean` slots of a row whose `n_dates`,
> `wilson_ci_low` and `control_coverage` described the CONTROLLED COHORT ONLY — two
> populations in one unlabelled record (measured: `wilson_ci_low=0.886` over 30 cohort
> rows published beside `hit_rate=0.4286` over 70 whole-family rows). C6.1 requires the
> four concepts to stay separate wherever they are rendered, and a shared key name is
> not separation. Keeping pre-clock rows inside the BASELINE numbers is consistent with
> C3.3 precisely because they are now named: history is disclosed, never combined with
> cohort evidence.

**C5.2** `benchmark_only` / `unclassified` — evaluated exactly as today's
`promotion_check(control_only=False)`, with the verdict labelled
`evidence_basis="benchmark"` (plus `unclassified` marking). P0c-2's
legacy-cannot-originate-authority rule applies unchanged inside this path.

**C5.3** `not_applicable` — no directional gate runs; the ladder entry states the basis
(`not_applicable`) and points at the salience/placebo path. Nothing new is computed.

**C5.4** The production call paths (`emit_ladder_states`,
`compute_promotion_readiness`) dispatch **by policy**; the blanket
`control_only=True` call disappears from production. Every emitted verdict carries
`evidence_basis` ∈ {`matched_control`, `benchmark`, `not_applicable`} (+`unclassified`
flag), and required-family verdicts carry `control_coverage`, `n_cohort_dates`,
`n_controlled_dates`, `control_clock_start`.

**C5.5** Readiness alerting (`ready=True` first-cross) fires only on a verdict that is
eligible **on its family's own authority basis**.

## C6. Language and surfaces (D5)

**C6.1** Four concepts stay separate everywhere rendered: benchmark-relative evidence;
matched-control evidence; control coverage; authority eligibility.

**C6.2** Corrections shipped with this contract: the architecture document's
"matched-control grading substrate" recon line and standards §5.1 are restated to the
ruling's form — benchmark as universal baseline, matched control as the stricter second
basis under this classification — with the honest history: **qledger supported matched
controls in code; no live claim carried one before this contract; prospective
matched-control evidence begins when controlled claims register, and had not begun at
authoring time.** The `config/qual_ladder.yml` header's "vs matched control" gate
description is corrected to name the policy dispatch. The correction is not exaggerated:
the code path existed and was tested; what never existed is live evidence.

**C6.3** No user-facing surface may say "matched-control evaluated" about any family
until that family's clock has started and its gate reports coverage — and then only in
Calibration-Lab-tier surfaces (falsifier language stays off user cycle surfaces per the
standing 2026-07-27 ruling).

## C7. Adversarial controls (mechanical, mutation-backed)

Each numbered control from the P0d directive maps to at least one test that FAILS under
a targeted mutation of the guarded logic (a green assert-field-exists test is not
sufficient and not counted):

1. **No bench fallback**: a required family whose bench-relative record would pass but
   whose coverage fails must refuse; mutation = re-introduce the bench fallback in the
   required path → test fails.
2. **direction=−1 scored correctly vs control**: mirrored bullish/bearish pair produce
   identical control-basis hit rates; mutation = drop `direction *` from the comparison.
3. **direction=0 cannot manufacture a control hit**: salience rows excluded from
   numerator AND denominator of the matched gate; mutation = count them in either.
4. **Post-registration control selection impossible**: re-registration with a different
   control leaves the stored row byte-identical; grade rows never write back into
   claims. Mutation = dedupe keep-LAST → test fails.
5. **Historical backfill cannot mint authority**: controlled rows whose window began
   before their registration stamp never enter the cohort, the clock, or the N;
   mutation = drop C3.2(e).
6. **Missing-control rows cannot vanish from accounting**: 37 controlled / 100 cohort
   reports coverage 0.37 and refuses; mutation = compute coverage over controlled rows
   only (37/37) → test fails.
7. **Re-classification is governed**: policy comes from the table alone; a
   benchmark_only family with 100% control-carrying rows still evaluates benchmark;
   mutation = infer policy from row data. The table itself is pinned by an exact-content
   test.
8. **The gate cannot pass under a coverage violation**: all-else-green at coverage 0.94
   refuses; mutation = drop the coverage clause.
Plus: control-clock write-once (second write is a no-op); clock never pre-created;
`control==subject`/`control==bench` count as missing (C2.2); the alias normalisation
refuses unknown vocabulary loudly (D0-2).

## C8. Scope fences (inherited from the P0d directive, restated as obligations)

No engine retuning; no Prophet changes; no restored bench fallback; no retrospective
claims or authority-bearing controls; `GRADE_HORIZONS` ceiling 63 untouched; no T7/T8;
no P0a/P0b/P0c rebuilds; no universal composite control score; unrelated append-only /
Government-Revenue failures stay in their owning lanes.

## C9. What "live" will mean, honestly

At registration of this contract: **zero matched-control evidence exists anywhere.** The
first possible accrual is stock_desk's first post-merge nightly that registers a
prospective, control-carrying claim (#5577's wiring + this contract), and demand_chain's
after its `sector_of` wiring lands. The evidence clock files will say when that happened;
until they exist, every surface says the evidence has not begun. A reader in six months
should be able to reconstruct: classification date (this file's git history), clock start
(the write-once artifacts), and every coverage number in between (nightly readiness
payloads).
