# Government Revenue candidate grader — pre-registration (GRV-FA1)

**Version 1.0.0. Registered 2026-08-06, before any observation exists.**

Program: Government Revenue Foresight, Wave 9G
(`research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md` §"Wave 9G — prospective grader
and first preregistered family"). Candidate doctrine:
`research/GOVERNMENT_REVENUE_WAVE9_DEFENSE_CATALYST_CANDIDATE_LEDGER_2026-08-03.md`.
Instrument: `engine/government_revenue/candidate_grader.py`. Guard:
`tests/test_government_revenue_candidate_grader.py`. House form follows
`research/PROPHET_STAGE_QUALITY_PREREG.md`.

## 0. What this registration is for — read first

The Government Revenue lobe can produce evidence-bound, receipt-backed, well-argued
candidates and still have **no predictive value**. This document exists so that outcome
can be reached, stated, and filed. It is registered **before the first candidate exists**:
as of 2026-08-06 the candidate ledger is 0 bytes, the queue reports `counts.total: 0` with
`mapping_needed: 21` and one reviewed issuer ticker, and the forward event spine is
unavailable (`freshness.award_events.status == "unavailable"`, all three triad artifacts
absent). A zero-candidate lobe is the honest current state, and a null at the end of this
registration is an acceptable success.

Two consequences follow, and both are deliberate:

1. **The instrument is built and guarded against fixtures, not live candidates.** The
   harness must exist before the first candidate is issued or the first cohort is
   ungradeable after the fact — you cannot preregister a horizon for a candidate that has
   already matured.
2. **Nothing here confers authority.** The grader's output is `display`/`context`. It may
   not create, rank, size, or gate anything, and an attractive interim number is not a
   promotion. Promotion requires the existing gauntlet (Wave 12) and an operator ruling.

This registration covers exactly ONE narrow family. Other catalyst families
(ceiling changes, option exercises, new awards, deobligations) are **not** graded here and
must earn their own registration; they abstain, are counted, and are reported.

## 1. The family

**GRV-FA1 — exact-issuer, receipt-bound, positive funded-action acceleration.**

A candidate enters the family iff, from issuance-time fields only:

- `candidate_family == "award_obligation_change"` — funded money actually moved.
  `award_ceiling_change` is a different economic claim (a ceiling moves no money) and
  abstains as `ceiling_change_out_of_family`; `option_exercise` and `new_award` abstain as
  `family_mismatch`;
- `source_event.event_type != "deobligation"` and `transmission_direction == "possible_positive"`;
- `coverage.exact_link_status == "exact_linked"` — an exact reviewed issuer path, never a
  discovery-name or fuzzy match;
- `authority` is the display/context block, byte-identical to the candidate contract's;
- `known_at` parses; and
- `source_event.is_late_discovery` is **false**. A late-discovered action was already
  public before this pipeline could see it, so grading it from our `known_at` would measure
  stale news. Late discoveries abstain and are counted separately.

Every refusal above is recorded in the same append-only log as an `abstention` row with its
named reason, so the abstention rate is computable from the log alone and a filter cannot
be applied silently.

### Machine-readable declaration (binding)

`engine/government_revenue/candidate_grader.py:load_family_declaration` reads this block
and **refuses to run if it disagrees with the registered family in code**. The document and
the instrument cannot drift apart in either direction.

```json
{
  "family_id": "grv-fa1",
  "title": "exact-issuer receipt-bound positive funded-action acceleration",
  "document": "research/GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md",
  "version": "1.0.0",
  "horizons": [
    {"name": "h5", "sessions": 5, "role": "disclosure"},
    {"name": "h21", "sessions": 21, "role": "supporting"},
    {"name": "h63", "sessions": 63, "role": "primary"},
    {"name": "h126", "sessions": 126, "role": "supporting"}
  ],
  "primary_horizon": "h63",
  "market_benchmark": "SPY",
  "sector_benchmark": "ITA",
  "price_field": "close",
  "price_adjustment": "split_and_dividend_adjusted",
  "entry_session_rule": "first_session_strictly_after_known_at_utc_date",
  "hit_definition": "market_relative_return > 0",
  "drawdown_definition": "min over [entry_session, exit_session] of close/entry_close - 1",
  "placebo_offset_sessions": -252,
  "calendar_id": "us_equity_sessions",
  "maturity_gate": {
    "min_distinct_source_events": 40,
    "min_distinct_issuers": 12,
    "min_distinct_event_months": 12,
    "min_outcome_coverage": 0.7
  },
  "accrual_expiry_date": "2027-08-06",
  "kill_condition_id": "GRV-FA1-KILL-V1"
}
```

## 2. Hypotheses (committed before any observation)

- **GRV-FA1-H1 (PRIMARY).** Among GRV-FA1 candidates, the pooled **h63 market-relative
  return** is positive and exceeds the registered placebo cohort's by at least **+1.0pp**.
  This is the only hypothesis with kill power.
- **GRV-FA1-H2 (supporting).** The pooled h63 hit rate (`market_relative_return > 0`)
  exceeds 0.50, *and its lower bound over the fixed issuance cohort also exceeds 0.50*.
- **GRV-FA1-H3 (supporting).** Sector-relative (vs `ITA`) h63 return is positive — i.e. the
  effect is not the defense sector moving as a bloc.
- **GRV-FA1-H4 (disclosure only, no verdict power).** The h5 return distribution is
  reported to expose the stale-news case: an obligation observed on a publication lag may
  already be priced.

h21 and h126 are reported with the same machinery as robustness legs. They carry no verdict
power, and a sign disagreement between them and h63 is printed in the verdict rather than
used to re-choose the primary horizon.

## 3. Horizons — fixed, and frozen onto the row

Horizons are **5, 21, 63, 126 trading sessions**, aligned to the economic thesis rather than
to convenience: an obligation on an existing prime award transmits (if at all) through
backlog and funded backlog first, appears in a quarterly report next, and reaches recognized
revenue later. h63 (≈ one reporting quarter) is the primary. h5 exists to detect the
opposite of an edge — that the information was already public.

Two mechanical protections:

- **Session-indexed, never date-arithmetic.** A horizon is N steps along an explicit
  session calendar supplied to the grader. Nothing in the instrument calls
  `pandas.resample("nB")` or any business-day offset; that function start-anchors every bin
  and has silently misaligned four separate lanes in this repository. A horizon whose exit
  index runs past the end of the calendar is **ungraded**, never clamped to the last
  available session.
- **Frozen at issuance.** The horizon list is copied onto every issuance row when the row is
  written. Grading reads the horizons *off the row*, never off the live family object, so an
  edit to this document cannot re-cut a window on a cohort that is already accruing.

## 4. The ruler

- **Entry.** The first session **strictly after** the UTC date of the candidate's `known_at`.
  A row is never filled on the session during which it became knowable. This matches
  `engine/grading.py`'s next-bar-fill convention.
- **Exit.** `entry_index + horizon_sessions` on the same calendar.
- **Read window.** The closed interval `[entry_session, exit_session]` and nothing else.
  Every price the grader consumes passes through a single accessor, and each grade row
  carries a `read_window_sha256` over the exact `(symbol, session, close)` triples consumed,
  so "did this grade see the future" is an auditable question, not a claim.
- **Returns.** `absolute = exit_close / entry_close - 1`;
  `market_relative = absolute - SPY_return_over_the_identical_window`;
  `sector_relative = absolute - ITA_return_over_the_identical_window`.
- **Hit.** `market_relative_return > 0`, strictly. Zero is not a hit.
- **Drawdown.** `min over [entry, exit] of close / entry_close - 1` (≤ 0 by construction).
- **Price basis, pinned.** `close`, split- and dividend-adjusted. The collection lane
  re-adjusts historical closes **in place**, so a grade computed today may not reproduce
  tomorrow. Every grade row records the basis *and the vintage id and clock* it was computed
  against; a panel whose adjustment or field differs from this registration is refused
  outright; and `regrade_diff` surfaces rows whose window hash moved under a new vintage
  instead of silently overwriting them. A number in a results doc must cite its vintage.
- **Placebo / naive baseline.** For every graded row, the same name and the same horizon
  shifted **−252 sessions** — a window lying entirely before issuance, so it cannot borrow
  the future. It answers the question a bare hit rate cannot: does this name drift up
  anyway? The placebo is reported with its own coverage and is an input to H1.

## 5. Denominators, ungraded states, and coverage

These rules exist because each corresponding failure has actually shipped in this
repository. They are not stylistic.

- **The denominator is the issuance-time cohort.** It is enumerated from the issuance log at
  issuance and never from the resolved subset. A rate computed only over rows that resolved
  is inflated whenever resolution correlates with outcome.
- **One cohort member per candidate.** Re-observing the same candidate (a later
  `observation_id` for the same `candidate_id`) does not add a member; the first issuance
  wins. Raising issuance cadence cannot manufacture N.
- **An unresolved endpoint is not 0.5.** There is no imputation path anywhere in the
  instrument. A row that cannot be resolved is `ungraded` with a named reason from a closed
  list — `horizon_not_matured`, `entry_session_unavailable`, `price_missing`,
  `benchmark_missing`, `mapping_missing`, `source_outage`, `retracted`, `calendar_gap` — and
  is excluded from **both** the numerator and the denominator of the conditional rate.
- **Bounds accompany every hit rate.** Over the fixed issuance cohort, the lower bound counts
  every ungraded row as a miss and the upper bound counts every one as a hit. The gap between
  them *is* the cost of incomplete resolution, made visible rather than assumed away.
- **Coverage travels with every rate.** A rate cannot be constructed without a coverage
  object, and the finished report is walked to fail closed on any bare `*_rate` value. A rate
  over 30% of a cohort is not the cohort's rate.
- **Median and pooled are reported together.** The median of a set of monthly binary rates can
  flip sign against the pooled rate, because a one-observation month weighs the same as a
  fifty-observation month. There is no code path that returns one without the other.
- **Three coverages, never one.** `identity_coverage` (issuers with a reviewed exact mapping),
  `event_coverage` (eligible events the spine actually observed), and `outcome_coverage`
  (issuance rows the grader could resolve) are three separate objects under three separate
  keys, and an outcome rate may only cite an outcome coverage. A lobe can have excellent
  identity coverage and no predictive value; that combination must remain legible.

## 6. Maturity gate — and why it counts what it counts

No verdict is available until **all four** hold:

| Requirement | Threshold |
|---|---|
| Distinct source events | ≥ 40 |
| Distinct issuers | ≥ 12 |
| Distinct event months | ≥ 12 |
| Outcome coverage at the primary horizon | ≥ 0.70 |

The first counter is **distinct source events, not issuance rows**. An "≥ N observations"
gate that counts rows can be satisfied by a change in issuance frequency rather than by the
world supplying anything new — such a gate does not gate. Distinct issuers and distinct
months prevent one issuer or one budget cycle from carrying the whole result.

## 7. Decision thresholds and the kill condition

**GRV-FA1-KILL-V1.** At the first report where the §6 gate is satisfied, evaluate H1 once:

- **KILL** iff the pooled h63 market-relative mean is **≤ 0** *and* the placebo delta
  (cohort mean − placebo mean) is **≤ 0**. The family predicts neither absolute
  outperformance nor anything beyond the names' own prior drift. Consequence: append a
  construction-scoped row to `research/DO_NOT_REBUILD.md` §1 with a minted key, closing
  "exact-issuer receipt-bound positive funded-action acceleration as a market-outcome
  signal". The evidence rails, candidate contract, dossiers, and display surfaces are **not**
  deleted — a null never deletes the layer, and a kill closes the construction tested, not
  the search space.
- **TESTED-NULL** iff the mean is > 0 but either the placebo delta is < +1.0pp or the h63
  hit-rate **lower bound** is ≤ 0.50. No kill, no promotion, no authority change; the result
  is filed and the family stays display-tier context.
- **SUPPORTED** iff the mean is > 0, the placebo delta is ≥ +1.0pp, and the h63 hit-rate
  lower bound is > 0.50. This buys **nothing** by itself except eligibility to request the
  Wave 12 gauntlet. It is not a promotion and must not be surfaced as one.
- **EXPIRY — the gate cannot be an alibi.** If the §6 gate is not satisfied by
  **2027-08-06**, GRV-FA1 is closed as **unmeasurable at this issuance rate** and filed as
  such. "Still accruing" stops being an available answer on that date. Re-opening requires a
  new registration with a new `family_id`, not an extension of this one.

Multiplicity is controlled: exactly ONE kill-bearing hypothesis (H1), at ONE horizon (h63),
on ONE statistic (pooled market-relative mean, against the registered placebo). Everything
else in the report is labeled supporting or disclosure and carries no verdict power. No
threshold in this document may be tuned on the held-forward window; see §9.

## 8. Corrections and retractions policy (fixed before observation)

- The issuance log is **append-only**. A row, once written, is never edited. A correction is
  a **new row** carrying `supersedes_row_id`, its own reason, and its own content address;
  the superseded row remains byte-identical in the file forever, and the append receipt binds
  the prior prefix by hash so a rewrite is detectable from the receipt alone.
- A **retraction** does not remove its target from the issuance cohort. It moves the row to
  `ungraded(retracted)`, which **lowers coverage and widens the hit-rate bounds**. You cannot
  retract your way out of a loss; you can only pay for it in coverage.
- A retraction is valid only for a **source-evidence correction** — the upstream official
  record changed or the receipt binding failed. Disagreement with an outcome is never a valid
  reason. Every retraction states its reason in the row.
- **Residual risk, disclosed:** a retraction issued after an outcome is observable is still a
  discretionary act. The mitigation is structural, not procedural — the row keeps its slot in
  the denominator and `retracted_n` is printed in every report — but it is not eliminated.

## 9. Look-ahead controls, amendment law, and known contract gaps

- The grader reads only information available at issuance: admission uses candidate fields
  only, entry is strictly after `known_at`, the outcome window is exactly the frozen horizon,
  and `read_window_sha256` proves what was consumed. `tests/test_government_revenue_candidate_grader.py`
  fails if the read window is widened by a single session.
- No threshold, horizon, benchmark, or admission rule may be changed after the first issuance
  row for this family exists. Any such change voids the cohort and requires a new
  `family_id`. Changes before first issuance are dated amendment rows below.
- **Contract gaps the candidate payload does not close (carried into every report's
  limitations):**
  1. **No public-first-disclosure clock.** `known_at` is when this pipeline could first know
     the action. USAspending publishes on a lag and the DoD daily contract announcement may
     have made the same fact public days earlier. A positive result is therefore not
     separable from a stale-news artifact without an independent disclosure clock. h5 is the
     disclosure horizon that makes this visible; it is not a fix.
  2. **No sector identity on the candidate.** `ITA` is registered here as the family's sector
     benchmark for a defense-procurement family; the candidate contract carries no sector or
     industry field, so a wider issuer universe will need a sector map the contract does not
     supply.
  3. **No comparable materiality.** `materiality_ratio` and `issuer_attributed_denominator`
     are `null` by contract, so an award's size cannot be scaled to the issuer. Dose-response
     (does a bigger obligation move the stock more?) is not testable under the current
     contract; only absolute attributable dollars are available.
  4. **No supersession pointer on the candidate.** `candidate_state` has `superseded` and
     `withdrawn` but the payload carries no pointer to the superseding candidate, so the
     issuance log has to hold that lineage itself.
  5. **Ticker is the only market identity.** A reused or re-pointed ticker would silently
     re-point a grade; the contract carries no exchange, listing currency, or permanent
     security identifier.

## 10. Authority (restated because it is the thing most likely to erode)

`display` / `context`. `can_rank`, `can_size`, `can_gate`, `can_originate_signal`,
`can_add_candidates`, `can_escalate` are all false, in the candidate payload, on every
issuance row, and on every report. This does not change with the result. An LLM may never
originate or escalate a grade here.

| Amendment | Date | Change | Reason |
|---|---|---|---|
| — | — | none | Registered 2026-08-06 with zero candidates in existence. |
