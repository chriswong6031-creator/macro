# Government Revenue candidate grader — pre-registration (GRV-FA1)

**Version 4.0.0. Registered 2026-08-06, amended 2026-08-07 and 2026-08-08, before any
observation exists.**

*Version 2.0.0 amends 1.0.0 on the same day, still before the first issuance row exists (the
live log is 0 bytes — see §0). The amendments are §7's decision rule and power calculation,
§6's clocks, and §8's correction allowlist; each is recorded in the amendment table in §10 with
its reason. §9's amendment law is untouched: after the first issuance row exists, none of this
may move without a new `family_id`.*

*Version 3.0.0 (2026-08-07) adds §11, the disclosure-label layer the Wave 9G handoff asks for
("earnings-window and subsequent-filings outcome labels where available"). It is still
pre-observation: the live issuance log does not exist and the candidate ledger is 0 bytes. The
amendment touches **no** threshold, horizon, benchmark, admission rule, or decision rule — §11
is descriptive and is computed after the verdict — so §7's power calculation and the registered
kill condition are unchanged, and N = 545 still describes the statistic it was derived for.
(The kill condition is named and stated in §7.3; it is deliberately not repeated above the
machine-readable declaration, because §9's drift guard reads the prose on both sides of that
block and a mention here would satisfy it without anyone stating the rule.)*

*Version 4.0.0 (2026-08-08) amends §7 — the **evaluation rule** — in response to an
adversarial audit of the instrument. It adds two necessary preconditions to every verdict (a
coverage floor on the paired placebo delta, and a floor on independent draws) and refuses a
degenerate one-observation interval; the kill condition is renamed accordingly and its new id is
stated with the rule itself in §7.3 — deliberately not here, for the reason given just above.
It also amends §1, fencing the family to the ACTION source rail (§7.6.4), because sibling
PR #5085 admits snapshot-rail balance-change events into the same candidate family and this
grader would otherwise have pooled two different measurement units into one graded cohort.
§7.6 states each change, its evidence, and — because this is an amendment to a
registered evaluation rule — the proof that the amendment window is still open. **No
threshold value moved.** The pre-registration's §9 amendment law is unchanged and is now
narrower in practice: the next issuance row closes this window permanently.*

> **Post-registration incident notice (2026-08-10; non-normative).** Commit
> `5fc18d5aac892ac61bcfdcc7ae1638c028c66781` erroneously issued eight historical
> snapshot-rail candidate rows contrary to the already reviewed do-not-backfill
> decision. The rows remain in the append-only candidate audit ledger and an
> exact issuance-correction receipt quarantines them from active candidate and
> Prophet surfaces. This permanently closes the amendment window described
> below. It does **not** create a grader observation: the grader still has no
> caller and no grader issuance log. This notice changes no registered family,
> threshold, horizon, rule, or authority.

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
- **`source_event.source_rail` is exactly `usaspending_award_action`** — the family is fenced to the
  ACTION rail, and the fence is fail-closed: an absent, null, non-string, or differently-cased
  rail abstains as `family_rail_mismatch`. The candidate contract admits **both** the action
  rail and `usaspending_award_snapshot` into `award_obligation_change`, and they are not the
  same number. The action rail emits a `transaction_delta` — money that moved in one recorded
  action. The snapshot rail emits a delta obtained by **differencing `award_cumulative`
  balances** between two observations of the same award, in which a restatement, a late-posted
  correction, and a genuine new obligation are indistinguishable, and whose magnitude is not
  the size of any event. Pooling the two into one graded cohort is the amount-class conflation,
  reaching the family through the RAIL rather than through the family name. See §7.6.4. The
  snapshot rail is not rejected as evidence — it is a **different measurement** and needs its
  own preregistration, with its own horizons and its own N, before anything grades it;
- `source_event.event_type != "deobligation"` and `transmission_direction == "possible_positive"`;
- `coverage.exact_link_status == "exact_linked"` — an exact reviewed issuer path, never a
  discovery-name or fuzzy match;
- `authority` is the display/context block, byte-identical to the candidate contract's;
- `known_at` parses;
- the candidate carries a **`ticker`**. An issuer the recipient graph could not map to a market
  identity has no price panel and no honest number, so it abstains as `mapping_missing` and is
  counted like every other refusal. *Version 3.0.0 had no such check: an unmapped issuer was
  ADMITTED and then raised inside the row builder's own validation, so the first unmapped issuer
  in a batch killed the whole batch — no rows, no abstention, no printed null, no report. The
  reviewed recipient graph carries unmapped issuers today (GE and BWXT among them), so this was
  the live shape and not a hypothetical, and `mapping_missing` was declared in the vocabulary
  and emitted by nothing.* The abstention row carries an explicit **null** ticker, never an
  empty string, which every downstream census would read as a symbol; and
- `source_event.is_late_discovery` is **exactly `false`** — fail-closed. A late-discovered
  action was already public before this pipeline could see it, so grading it from our
  `known_at` would measure stale news. Late discoveries abstain and are counted separately.
  A **missing**, null, or non-boolean flag also abstains: an absence of evidence is not
  evidence of a fresh discovery. Version 1.0.0 tested `bool(...)`, which admitted any payload
  that simply omitted the key — the one admission test in the family that failed **open**,
  guarding the one thing this clause exists to guard.

Every refusal above is recorded in the same append-only log as an `abstention` row with its
named reason, so the abstention rate is computable from the log alone and a filter cannot
be applied silently.

**Identity basis — what `exact_linked` is allowed to rest on (registered 2026-08-08).** The
`exact_link_status` clause above constrains the link *class* (exact identifier, reviewed
ownership path — never a discovery name or a fuzzy match). It did not, through 3.0.0,
constrain the *basis*: whose assertion supplied that exact identifier, and on which clock. It
now does, because the answer changed. The USAspending action rail — `POST
/api/v2/transactions/`, the only rail this registered family admits after 4.0.0 — carries no
recipient identity of its own (35,140 of 35,140 accrued action rows hold a null
`recipient_uei`), so until now no candidate on the admitted rail could clear the exact-link
gate. Snapshot-rail candidates remain display-only and refuse here as `family_rail_mismatch`.
An action is now linkable through the award's recipient of record, attached to the row under a
named basis with the award's own retrieval clock. Two bases are registered, and a candidate
carries exactly one:

- `source_record_recipient` — the observation's own recipient fields, asserted by the response
  that produced the row. This is what every candidate before this amendment rested on.
- `award_level_recipient_at_collection` — the award's recipient of record, attached to an
  observation that asserted none of its own. The identifier is exact and the ownership path is
  reviewed, so the link satisfies `exact_linked` as written; what is *not* claimed is that the
  transaction named this recipient. The identity's clock is the award record's retrieval
  clock, never the transaction's `effective_at`, so a recipient recorded after collection is
  outside the claim. Every such candidate prints the basis in `issuer_resolution_ref` and the
  limitation in `limitations`.

**Both bases are admitted, and neither is a separate cohort.** A basis split is not registered
as a stratum here because the family's N (§7) was derived for one pooled statistic and
splitting it post hoc is exactly the optional-stopping move §7.5 latches against. The basis is
recorded on every issuance row so a *descriptive* partition is computable later; it is not a
verdict input. This widens which action-rail records can satisfy an unchanged exact-link rule,
made before any measurement exists to be flattered by it: `data/government_revenue/candidate_ledger.jsonl`
is **0 bytes** at the amending commit's parent, and no issuance log exists.

### Machine-readable declaration (binding)

`engine/government_revenue/candidate_grader.py:load_family_declaration` reads this block
and **refuses to run if it disagrees with the registered family in code**. The document and
the instrument cannot drift apart in either direction.

Every threshold that can change a verdict lives inside this block. Two of them used to sit in
the module as bare constants (`_PLACEBO_FLOOR = 0.01` and a literal `lower > 0.5`), where §9's
"no threshold may be changed after first issuance" was unenforceable because the drift guard
compares only this declaration against the family object. A threshold the guard cannot see is
not registered.

```json
{
  "family_id": "grv-fa1",
  "title": "exact-issuer receipt-bound positive funded-action acceleration",
  "document": "research/GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md",
  "version": "4.1.0",
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
    "min_distinct_source_events": 545,
    "min_distinct_issuers": 12,
    "min_distinct_event_months": 12,
    "min_distinct_known_at_months": 12,
    "min_distinct_entry_sessions": 120,
    "min_outcome_coverage": 0.7
  },
  "decision_rule": {
    "minimum_interesting_effect": 0.03,
    "hit_rate_floor": 0.5,
    "confidence_level": 0.95,
    "bootstrap_resamples": 2000,
    "bootstrap_seed": 20260806,
    "min_verdict_outcome_coverage": 0.7
  },
  "power": {
    "planning_sd_paired": 0.25,
    "planning_alpha": 0.05,
    "planning_power": 0.8,
    "planning_n_required": 545
  },
  "accrual_expiry_date": "2029-08-06",
  "kill_condition_id": "GRV-FA1-KILL-V3"
}
```

## 2. Hypotheses (committed before any observation)

- **GRV-FA1-H1 (PRIMARY).** Among GRV-FA1 candidates, the pooled **h63 market-relative
  return** is positive and exceeds the registered placebo cohort's by at least the
  **minimum interesting effect of +3.0pp**, measured as a **paired** difference (same
  candidate, event window minus its own registered placebo window) with a bootstrap
  interval. This is the only hypothesis with kill power.
- **GRV-FA1-H2 (supporting).** The **conditional** h63 hit rate (`market_relative_return > 0`)
  clears 0.50 with its own bootstrap interval, at or above the registered outcome-coverage
  floor. *This replaces 1.0.0's requirement that the Manski lower bound over the fixed cohort
  clear 0.50: at the registered 0.70 coverage floor that demanded a conditional hit rate above
  71.4%, which no plausible equity signal at a one-quarter horizon delivers. A supporting
  hypothesis no data can satisfy is a `SUPPORTED` branch no code path can reach, which is the
  same defect as an unreachable kill, pointed the other way. The bounds are still computed and
  still printed — they are disclosure of the coverage cost, not a decision threshold.*
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
  `engine/grading.py`'s next-bar-fill convention. **The calendar must reach back past
  `known_at`**: one whose first session is later cannot name "the session after `known_at`" —
  index 0 is merely the earliest bar it carries — so such a row is `entry_session_unavailable`,
  never filled on that bar.
- **Exit.** `entry_index + horizon_sessions` on the same calendar, and the exit session must be
  **strictly before** the report's `as_of` UTC date. `as_of` is an instant and the nightly
  pipeline runs 00:05–07:00 UTC, so a date-granular comparison consumed the exit session's close
  roughly twenty hours before the US market produced it. A one-session lag is the conservative
  reading of an instant against a calendar that carries no close times; this module deliberately
  holds no session-hours or timezone table (§3) and may not infer one.
- **The session LIST is frozen, not only the calendar id.** Every issuance row records
  `entry_rule.calendar_session_count` and `entry_rule.calendar_sessions_sha256` — the content
  address of the sessions that existed at issuance. A vendor revision of the same calendar (a
  make-up session added, a holiday reclassified) keeps the same `calendar_id`, and it re-cuts an
  already-frozen window bit-for-bit differently under a byte-identical price vintage; freezing an
  id a revision preserves froze nothing. At grade time the calendar's prefix of that length must
  reproduce the digest, or the row is `ungraded(calendar_revised)` — a refusal rather than an
  exception, because exchanges do restate session lists and a batch that dies on the first one
  grades nothing. A PREFIX and not the whole list, because the calendar legitimately GROWS every
  night; hashing the whole list would refuse every row within a day and prove nothing.
  `regrade_diff` carries the calendar identity and the window's session digest on both sides, so
  a moved value is attributable to the calendar rather than to the vintage — and it now reports a
  grade that **disappeared** between runs, which it previously could not see at all.
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
  anyway? The placebo is reported with its own coverage and is an input to H1. It carries
  **every refusal** the event grade carries — foreign calendar, mismatched price basis, a revised
  session list, a calendar that does not reach back to `known_at`, **and `as_of`** — because a
  baseline computed on a different calendar, a different adjustment, or a different **clock** than
  the cohort it is subtracted from is not a baseline. *Version 3.0.0's placebo took no `as_of` at
  all: "the window lies before issuance" bounds it against the ROW's clock, not the REPORT's, so a
  report replayed at a historical `as_of` published a placebo block computed from bars after it.
  Only the paired delta was protected, and only incidentally, by its intersection with a real side
  that had already refused.*
- **The placebo delta is PAIRED, on `candidate_id`, over the intersection.** A candidate
  graded on the event window but not on its placebo window (or the reverse) contributes to
  neither side. A difference between a mean over one row set and a mean over a different row
  set is not a difference, and this figure feeds the kill condition. The unpaired difference
  is still printed, labelled, and carries no verdict power.
- **Read-window hash is order-sensitive.** `read_window_sha256` covers the consumed
  `(symbol, session, close)` triples **in read order**. A hash over the sorted set is
  permutation-invariant, so inverting entry and exit — which flips the sign of every return —
  would leave it byte-identical and the audit question unanswerable.

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
  `benchmark_missing`, `mapping_missing`, `source_outage`, `retracted`, `calendar_gap`,
  `calendar_revised` — and is excluded from **both** the numerator and the denominator of the
  conditional rate. **A non-finite close (`NaN`, `±inf`) is a MISSING bar, not a number**: it
  resolves to `price_missing`. `NaN <= 0` is `False`, so a bare positivity guard passed it, and
  `nan > 0` is `False`, so the row then graded a **miss** — this rule broken in the one direction
  that reads as a measured loss rather than as an absence.
- **Bounds accompany every hit rate — and the kill-bearing mean.** Over the fixed issuance
  cohort, the hit-rate lower bound counts every ungraded row as a miss and the upper bound
  counts every one as a hit. The pooled market-relative **mean** now carries the same kind of
  band (`market_relative_return_bounds`), imputing every unresolved row at the registered
  support `[-1.0, +1.0]`. The gap between them *is* the cost of incomplete resolution, made
  visible rather than assumed away. The band is **sensitivity, not the verdict input** — see
  §7, which states why and what protects the verdict instead.
- **Coverage travels with every rate — and with every cohort statistic.** A rate cannot be
  constructed without a coverage object, and the finished report is walked to fail closed on
  any bare `*_rate`, `*_ratio`, `*_mean`, `*_summary`, or `*_bound` value. A walker that knew
  only about `*_rate` was structurally blind to the mean the verdict actually reads; aggregate
  blocks therefore carry a `_summary` suffix so the walker can see them. A rate over 30% of a
  cohort is not the cohort's rate, and neither is a mean.
- **The supersession ratchet.** A superseding row may lower coverage; it may never delete a
  grade its predecessor already earned. See §8.
- **Median and pooled are reported together.** The median of a set of monthly binary rates can
  flip sign against the pooled rate, because a one-observation month weighs the same as a
  fifty-observation month. There is no code path that returns one without the other.
- **Three coverages, never one.** `identity_coverage` (issuers with a reviewed exact mapping),
  `event_coverage` (eligible events the spine actually observed), and `outcome_coverage`
  (issuance rows the grader could resolve) are three separate objects under three separate
  keys, and an outcome rate may only cite an outcome coverage. A lobe can have excellent
  identity coverage and no predictive value; that combination must remain legible.

## 6. Maturity gate — and why it counts what it counts

No verdict is available until **all six** hold:

| Requirement | Threshold | What it stops |
|---|---|---|
| Distinct source events | ≥ 545 | an N chosen for convenience (§7 power calculation) |
| Distinct issuers | ≥ 12 | one issuer carrying the result |
| Distinct **event** months (`effective_at`) | ≥ 12 | one budget cycle carrying the result |
| Distinct **known_at** months | ≥ 12 | one backfill night carrying the result |
| Distinct **entry sessions** | ≥ 120 | 545 rows that are one independent draw |
| Outcome coverage at the primary horizon | ≥ 0.70 | a rate over a third of a cohort |

The first counter is **distinct source events, not issuance rows**. An "≥ N observations"
gate that counts rows can be satisfied by a change in issuance frequency rather than by the
world supplying anything new — such a gate does not gate. Distinct issuers and distinct
months prevent one issuer or one budget cycle from carrying the whole result.

**The event clock is not the entry clock, and version 1.0.0 conflated them.** It counted
months off `effective_at`, falling back to `known_at`. That is satisfiable by a single
backfill night: 40 rows, 40 distinct `event_id`, 12 issuers, `effective_at` spanning twelve
historical months — and one shared `known_at`. Every row then has the **same entry session and
the same market window**: 40 rows, one independent draw, gate `satisfied: true`, coverage 1.0.
That is precisely the trap §6 claims to close, reintroduced through the wrong clock. Both
clocks are now counted separately, and **distinct entry sessions** — the count of genuinely
independent market windows the cohort contains — is counted alongside them.

Overlap between windows is *not* de-duplicated (the denominator is the issuance cohort by §5
and that does not move) but it **is** disclosed: `window_independence` prints distinct tickers,
distinct entry sessions, overlapping window pairs, the maximum overlap in sessions, and a
greedy non-overlapping-window estimate beside `issued_n`. Two candidates on one ticker five
sessions apart give two h63 windows sharing 58 of 63 sessions; they are two rows and roughly
one draw, and the report must not let those look like the same thing.

## 7. Decision thresholds, the power calculation, and the kill condition

### 7.1 The statistics every verdict input carries

Every verdict input is emitted with `n`, `mean`, `median`, `min`, `max`, **`sd`**,
**`standard_error`**, and a **percentile bootstrap interval** at `confidence_level = 0.95`
(`bootstrap_resamples = 2000`, seeded from `bootstrap_seed` mixed with the statistic's label,
so a report reproduces bit-for-bit). The bootstrap is nonparametric on purpose: single-name
horizon returns are fat-tailed and skewed, and a normal-theory interval understates the tail
exactly where a verdict is decided.

**Each verdict region tests an INTERVAL against a registered threshold.** Version 1.0.0
compared bare point estimates to 0, +1.0pp, and 0.50. At its gate floor (~40 graded h63 rows)
with single-name 63-session market-relative SD of 15–25pp, the standard error of the delta is
roughly 3.4–5.6pp: a preregistered KILL fired on noise roughly 25–40% of the time under a true
null and roughly 15–25% of the time against a genuine +3pp edge. That is a coin flip wearing a
preregistration, and it is the reason the registered N moved.

### 7.2 The power calculation (why N = 545)

- **Minimum interesting effect** δ\* = **+3.0pp** paired h63 market-relative. Below this the
  family is not economically interesting for a one-quarter catalyst, so it is not worth
  distinguishing from zero and the instrument does not pretend to.
- **Planning SD** σ = **25pp** for the *paired* difference. Single-name h63 market-relative SD
  is 15–25pp; the placebo window sits 252 sessions away and is effectively uncorrelated, so
  the paired difference has SD ≈ σ·√2 and 25pp is the conservative planning value. The
  *decision* uses the realized bootstrap spread, not this number; σ only sizes the gate.
- **Requirement.** For KILL to fire with ≥ 80% probability under a true null — i.e. for
  `P(observed δ + 1.96·SE < δ*) ≥ 0.80` — we need `δ* ≥ 2.80·SE`, so `SE ≤ 0.0107`, so
  `N ≥ (σ/SE)² = (0.25/0.0107)² ≈ **545**`.
- **What that buys.** At N = 545, SE ≈ 1.07pp. Under a true null KILL fires ~80% of the time;
  against a genuine +3pp edge it fires ~2.5% of the time (down from 15–25%). SUPPORTED needs an
  observed paired delta above ≈ +5.1pp, which a real effect of 6pp+ reaches.
- **Consequence, stated plainly.** 545 distinct source events is a demanding gate for a lobe
  whose ledger is currently 0 bytes with one reviewed issuer. The registered expiry moved to
  **2029-08-06** so that the registered N is reachable *in principle* — a gate that cannot be
  met inside its own window guarantees `expired_unmeasurable`, which is the same broken
  instrument as one that only ever kills. If the events do not arrive, the honest answer is
  "we could not measure this", and §7's EXPIRY clause files exactly that.

### 7.3 GRV-FA1-KILL-V3 — three exhaustive regions

At the first report where the §6 gate is satisfied *and* **all three** verdict preconditions
below hold, evaluate H1 **once**:

1. **Verdict-basis coverage** clears `min_verdict_outcome_coverage` (0.70);
2. **Paired-placebo coverage** clears the same registered floor — the paired intersection is a
   different and strictly smaller set than the verdict basis, and it carries half the decision
   rule (§7.6.1); and
3. **Independent draws** — `verdict_basis.window_independence.non_overlapping_window_estimate`
   — reach `planning_n_required` (545), because §7.2's N is a power calculation and a power
   calculation counts draws, not rows (§7.6.2).

A precondition that fails yields `accruing` with the reason named
(`paired_placebo_coverage_below_registered_floor`, `independent_draws_below_registered_n`),
never a softer decided state. Let `m` be the pooled h63 market-relative
mean over the verdict basis with interval `[m_lo, m_hi]`, `d` the **paired** placebo delta with
interval `[d_lo, d_hi]`, and `h` the conditional h63 hit rate with lower interval bound `h_lo`.

- **KILL** iff `m_hi < δ*` **and** `d_hi < δ*`. The data rule the minimum interesting effect
  out, both absolutely and against the family's own prior drift. Consequence: append a
  construction-scoped row to `research/DO_NOT_REBUILD.md` §1 with a minted key, closing
  "exact-issuer receipt-bound positive funded-action acceleration as a market-outcome
  signal". The evidence rails, candidate contract, dossiers, and display surfaces are **not**
  deleted — a null never deletes the layer, and a kill closes the construction tested, not
  the search space.
- **SUPPORTED** iff `m_lo > 0` **and** `d_lo > δ*` **and** `h_lo > 0.50`. This buys **nothing**
  by itself except eligibility to request the Wave 12 gauntlet. It is not a promotion and must
  not be surfaced as one.
- **TESTED-NULL** otherwise. Measured, and neither ruled out nor supported at the registered
  power: the interval spans δ\*. Filed as a null, authority unchanged. *This label makes no
  claim about the sign of the cohort mean — 1.0.0's `tested_null` prose said "positive but not
  separable" and a mean ≤ 0 with a delta > 0 fell through to it, shipping a label that
  contradicted its own printed numbers. The three regions above are exhaustive and none of them
  narrates a sign.*
- **EXPIRY — the gate cannot be an alibi.** If the §6 gate is not satisfied by
  **2029-08-06**, GRV-FA1 is closed as **unmeasurable at this issuance rate** and filed as
  such. "Still accruing" stops being an available answer on that date. Re-opening requires a
  new registration with a new `family_id`, not an extension of this one.

**Both directional branches are reachable at the registered constants**, and
`tests/test_government_revenue_candidate_grader.py::test_the_registered_family_still_carries_its_real_thresholds`
asserts their **joint satisfiability** rather than merely asserting the constants exist. A
`SUPPORTED` branch no plausible data can reach is the same defect as an unreachable kill,
pointed the other way, and 1.0.0 shipped one.

### 7.4 What protects the kill-bearing statistic (the B1 choice, stated)

The kill-bearing statistic is a **mean**, and a mean over "the rows that resolved" is a
resolution-conditioned statistic — the same defect §5 names for rates, applied to the number
the verdict actually reads. Two protections were available: bound the statistic the way the hit
rate is bounded, or refuse to fire below a registered coverage floor. **Both are registered,
and the bound is deliberately not the verdict input.**

1. **A registered verdict coverage floor.** `min_verdict_outcome_coverage = 0.70`. Below it no
   verdict fires — not a softer one, *none*: the state is `accruing` with
   `verdict_blocked_reason: verdict_basis_coverage_below_registered_floor`. A blocked verdict
   is never a decided verdict, because "escaping into a softer state" is the same escape.
2. **The supersession ratchet** (§8), which is what makes the verdict *not flip* rather than
   merely refuse: a grade a superseded row already earned is retained for the verdict basis.
3. **The Manski-style band is printed as sensitivity, not used as the threshold.** An
   assumption-free support for a return is `[-1.0, +1.0]`; at the registered 0.70 coverage
   floor, imputing 30% of the cohort at −100% would make every cohort kill and imputing at
   +100% would make every kill impossible. A bound wide enough to be assumption-free is wide
   enough to make every verdict indeterminate, so it is disclosed
   (`market_relative_return_bounds`) and the verdict's protection is structural (1 and 2)
   rather than statistical. **Residual risk, disclosed:** within the 30% the floor allows, a
   non-discretionary resolution failure (a genuine price outage, a name that stops trading)
   can still move the mean, and nothing here eliminates that. It is bounded by the floor,
   printed in the band, and named in every report's limitations.

### 7.5 One look, and it is latched

§7 says H1 is evaluated **once**. That is now implemented rather than asserted:
`evaluate_verdict` accepts the previously latched verdict, and once a decided state exists the
report carries **that** state, with `latched: true` and tonight's `recomputed_state` printed
beside it for drift — never in place of it. Recomputing every night and reporting the newest
answer is optional stopping against a rule that promised one look, and it is a second way a
losing cohort walks back a kill.

These states are **computed**, not narrated:
`engine/government_revenue/candidate_grader.py:evaluate_verdict` emits exactly one of
`accruing`, `expired_unmeasurable`, `kill`, `tested_null`, `supported` on every report, and
`tests/test_government_revenue_candidate_grader.py::test_the_kill_condition_is_reachable`
proves a losing cohort actually produces `kill`. A kill condition that no code path can emit
is a detector with an unsatisfiable precondition: it returns a clean null forever and reads
as working. Emitting the state is not the same as acting on it — filing a kill, or asking
for the gauntlet, remains an operator act, and the authority block is unchanged in every
branch including `supported`.

Multiplicity is controlled: exactly ONE kill-bearing hypothesis (H1), at ONE horizon (h63),
on ONE statistic (pooled market-relative mean over the verdict basis, against the registered
paired placebo). Everything else in the report is labeled supporting or disclosure and carries
no verdict power. No threshold in this document may be tuned on the held-forward window; see
§9.

### 7.6 Amendment 4.0.0 (2026-08-08) — what changed in the evaluation rule, and why

This subsection exists because §9 permits an amendment to a registered rule **only before the
first observation**, and an amendment to an evaluation rule is exactly the change most likely
to be a threshold tuned on data. So it is recorded here in full, with its evidence, and with
the proof that no observation existed when it was made.

**The amendment window, stated as checkable facts (2026-08-08).** All three are asserted
programmatically by
`tests/test_government_revenue_candidate_grader.py::test_amendment_window_the_issuance_record_is_still_empty_and_uncalled`,
which was registered here as a **temporary witness to the then-current tree**:

1. `data/government_revenue/candidate_ledger.jsonl` is **0 bytes** in the committed tree;
2. no `candidate_issuance_log.jsonl` exists anywhere under `data/`; and
3. **the grader has no caller.** No module under `engine/`, `scripts/`, `app/`, or `admin/`
   imports `candidate_grader`; the only references in the repository are this document, the
   test suite, and the CI job lists.

**Therefore no number has ever been produced by this instrument, no cohort has ever been
graded, and no threshold below was chosen with knowledge of an outcome.** That is the whole
warrant for amending rather than minting a new `family_id`, and it expires at the first
issuance row. The changes below make every verdict region *strictly harder* to reach, which is
also the safe direction if this reasoning is ever found to be wrong.

After the 2026-08-10 incident, that temporary witness was replaced by
`test_amendment_window_is_closed_and_the_grader_remains_uncalled`, which pins the exact
eight-row immutable incident prefix while continuing to prove that this grader has neither an
issuance log nor a caller. The historical facts above remain the registration-time evidence;
they are not a claim that the present candidate ledger is empty.

**No threshold VALUE moved.** `minimum_interesting_effect`, `hit_rate_floor`,
`confidence_level`, `min_verdict_outcome_coverage`, `planning_n_required` and every §6 gate
constant are unchanged. What changed is *which statistics those existing constants are applied
to*.

#### 7.6.1 The paired placebo delta carries the registered coverage floor

The paired delta `d` is half of both decision regions (`d_hi < δ*` for KILL, `d_lo > δ*` for
SUPPORTED). §7.4's coverage floor guards `verdict_basis` coverage — the **real** side — and the
paired intersection is a different, strictly smaller set. `paired_coverage` was computed and
printed by the instrument and **consulted by nothing**.

*Evidence (audit probe p4/p4b, reproduced as
`test_one_paired_observation_cannot_decide_a_verdict`).* A cohort of 545 candidates satisfying
every registered §6 gate on the real side — 545 distinct source events, 545 issuers, 251 entry
sessions, outcome coverage 1.0 — with the placebo window priced for exactly **one** of them
produced `paired_n = 1`, a paired coverage of 1/545, and a decided verdict. Flipping that one
row's placebo window flipped the verdict of all 545; deleting it changed the verdict again. The
KILL branch behaved identically, and a KILL files a construction-scoped kill row.

**The rule.** The paired delta's own coverage must clear `min_verdict_outcome_coverage` before
any verdict that reads it fires. Below the floor: `accruing`, reason
`paired_placebo_coverage_below_registered_floor`.

#### 7.6.2 The verdict is gated on independent draws, not on row count

§7.2 derives N = 545 from `SE ≤ 0.0107` at `σ_paired = 25pp`. That arithmetic is over
**independent draws**. §6 already said so in prose — "545 rows that are one independent draw"
is what `min_distinct_entry_sessions` exists to stop — and §6 already required
`window_independence` to be *printed*. It was printed and never read.

*Evidence (audit probe p8, reproduced as
`test_a_verdict_is_gated_on_independent_draws_not_on_row_count`).* 552 rows from 12 issuers on
consecutive entry sessions: `non_overlapping_window_estimate = 12`, every §6 gate satisfied,
and a bootstrap interval computed at n = 552 that cleared δ\* — an interval the same evidence
fails at n = 12, because the overlap narrows it by ≈ √(552/12) ≈ 6.8×. Two h63 windows one
session apart share 62 of 63 sessions of tape; they are two rows and about one draw.

**The rule.** `verdict_basis.window_independence.non_overlapping_window_estimate` must reach
`planning_n_required` before any verdict fires. Below it: `accruing`, reason
`independent_draws_below_registered_n`. The estimate is computed over the **verdict basis**
rather than over tonight's grades, because the supersession ratchet (§8) can place a row in the
basis that is ungraded tonight, and the basis is the set the interval is computed over.

#### 7.6.3 A one-observation interval is not an interval

`_bootstrap_mean_ci` returned a **degenerate** interval `(v, v)` at `n == 1`, documented as
"honest, because one observation has no sampling spread". It is honest and it is exactly why the
value must not be emitted as an interval: §7.1 tests intervals against thresholds *precisely so
a point comparison cannot decide a verdict*, and a zero-width interval passes every test the
point passes. 2.0.0's own remedy was reintroduced as its own defect.

**The rule.** `n < 2` has no interval: `(None, None)`, which routes to `accruing` /
`verdict_inputs_unavailable`. This is a rule about what may be *emitted*, and it applies to
every statistic in the report, not only to the verdict inputs.

#### 7.6.4 The family is fenced to the action rail (§1)

This is an **admission-rule** amendment, made in the same window and for the same reason: it
must land before the first issuance row, because after that the cohort would already contain
the two units it exists to keep apart.

*The admitting event.* Sibling PR #5085 admits snapshot-rail
`reported_obligation_balance_changed` events into the `award_obligation_change` **candidate**
family. That is correct at display tier and is not in question here. Its side effect is: §1
gated GRV-FA1 on the family name with **no rail restriction**, so this grader — registered as
positive funded-**ACTION** acceleration — would have begun issuing on snapshot-derived
cumulative-balance deltas. Verified in this repository at this PR's base:
`engine/government_revenue/candidates.py` admits `source_rail in {"usaspending_award_snapshot",
"usaspending_award_action"}` into the family, `engine/government_revenue/award_events.py`
stamps `usaspending_award_snapshot` on snapshot-mode events, and `admit` accepted such a
candidate.

*Why a fence and not a filter.* `source_rail` says what KIND OF NUMBER produced the candidate.
`transaction_delta` (action rail) is money that moved in one recorded action.
`award_cumulative`-differenced delta (snapshot rail) is the change between two observations of
a running balance: a restatement, a late-posted correction, and a genuine new obligation are
indistinguishable in it, and its magnitude is not the size of any event. §5 forbids pooling
amount classes inside one graded cohort; a cohort mixing these two has no single unit, so its
pooled mean measures nothing and the registered δ\* = +3.0pp does not describe it.

*The rule.* A candidate whose `source_event.source_rail` is not exactly
`usaspending_award_action` abstains as **`family_rail_mismatch`** — a named abstention row in
the same append-only log, counted in the abstention rate, with the batch continuing, exactly as
`mapping_missing` behaves. It is never an exception and never a silent filter. The test is
`!=` against the ONE registered rail rather than a blocklist of known snapshot rails, because a
blocklist admits every rail a later ingest adds — which is precisely how the snapshot rail
reached this family.

*What is explicitly NOT done.* No second registered family is created here for the snapshot
rail. Registering a family as a side effect of fixing another one is how an unowned measurement
acquires a horizon nobody chose; the snapshot rail gets its own deliberate preregistration, or
it gets nothing.

*Amendment window, re-verified for this clause.* Because this clause landed after the rest of
4.0.0, the §7.6 window test was re-run against the amended tree before it was written:
`data/government_revenue/candidate_ledger.jsonl` is still **0 bytes**, no
`candidate_issuance_log.jsonl` exists under `data/`, and the grader still has no caller. No
candidate has ever been admitted by this instrument, so no admission rule here was narrowed
against an observed outcome — and #5085's four snapshot obligation candidates, which `admit`
accepted before this clause, had never been graded.

#### 7.6.5 Non-evaluation repairs shipped in the same change (recorded, not registered)

These fix the instrument's *measurement* rather than its decision rule. They are listed so the
amendment is a complete account of what moved:

- **A non-finite close is a missing bar.** `NaN <= 0` is `False`, so the panel accessor passed
  every NaN and infinity through. A NaN on the entry bar produced `nan > 0 == False` and graded
  the row a **MISS** — a null endpoint scored as a loss, §5's rule broken in its worst
  direction, and invisible, because the row read as resolved with full coverage. The report also
  carried a bare `NaN` literal, which RFC 8259 forbids: the record round-tripped inside Python
  and was unparseable to every conforming reader. Both the accessor and the canonical serializer
  now refuse non-finite values.
- **A calendar the row's `known_at` predates cannot place its entry.** `first_index_after`
  returns index 0 either way, so a trimmed panel plus a backfilled candidate silently filled the
  row on a POST-issuance session. Now `entry_session_unavailable`.
- **`as_of` is an instant, and maturity is now strict.** The exit session must be **strictly
  before** `as_of`'s UTC date. The comparison was date-granular, so a nightly run at 00:05 UTC
  consumed the exit session's close ~20 hours before the US close produced it. A one-session lag
  is the conservative reading: §3's anti-`resample` doctrine means this module holds no session
  hours or timezone table and may not infer one.
- **The placebo obeys `as_of`.** `grade_placebo_row` took no `as_of` at all. "The window lies
  before issuance" bounds it against the row's clock, not the report's, so a replayed report
  computed its published placebo block from bars after `as_of`. Only the paired delta was safe,
  and only incidentally.
- **The correction allowlist is enforced on the log** (§8), not only in the constructor.
- **The session list is frozen, not just the calendar id** (§4).
- **An unmapped issuer abstains** as `mapping_missing` (§1) instead of raising.
- Report hygiene: an empty cohort reports coverage `empty` rather than `complete`; monthly
  buckets cite their own per-month coverage; `verdict.inputs.coverage` cites the verdict basis's
  coverage — the denominator its numbers actually came from — with the cohort's printed beside
  it as `cohort_outcome_coverage`; `regrade_diff` reports deletions and names the calendar axis.

## 8. Corrections and retractions policy (fixed before observation)

- The issuance log is **append-only**. A row, once written, is never edited. A correction is
  a **new row** carrying `supersedes_row_id`, its own reason, and its own content address;
  the superseded row remains byte-identical in the file forever, and the append receipt binds
  the prior prefix by hash so a rewrite is detectable from the receipt alone.
- A **retraction** does not remove its target from the issuance cohort. It moves the row to
  `ungraded(retracted)`, which **lowers coverage and widens the hit-rate bounds**. You cannot
  retract your way out of a loss; you can only pay for it in coverage.
- **A correction may change only `candidate_payload_sha256`, `evidence_generation`, and
  `observation_id`.** This is an allowlist, and everything that defines the measurement is
  refused by name: `known_at`, `ticker`, `horizons`, `entry_rule`, `effective_at`,
  `source_event`, `issuer_company_id`, `prereg_document_sha256`, plus the identity fields
  1.0.0 already blocked. Version 1.0.0 blocked six fields and accepted the rest, which meant a
  plain `correction` could rewrite `known_at` **after the outcome was observable** — re-cutting
  the entry session, which is post-issuance information reaching the grade and the exact leak
  this module exists to prevent — or rewrite `ticker` onto a symbol the panel does not carry
  and quietly ungrade a loser. An allowlist is used rather than a blocklist because a blocklist
  admits every field a later schema adds. A correction that genuinely needs a different ticker,
  event, or `known_at` is a **different candidate**, not a correction.
- **The allowlist is enforced ON THE LOG, not only in the constructor.** Version 2.0.0 and 3.0.0
  checked it in `build_correction_row` alone. A superseding row built **by hand** — the same dict,
  a recomputed `row_id`, no constructor involved — carrying the identical `known_at` rewrite
  passed `validate_issuance_row`, `parse_issuance_log`, `append_issuance_rows` **and**
  `cohort_rows`, re-cut the entry session onto a post-outcome bar, and changed the published
  number and the verdict. A guard living only in the convenience constructor guards only the
  callers who use the convenience constructor, and the log is the record of authority. Every
  field outside the allowlist and outside the supersession machinery itself (`row_kind`,
  `row_id`, `supersedes_row_id`, `correction_reason`, `appended_at`) must now reproduce
  **byte-for-byte** from the row it supersedes, checked as canonical bytes so a re-ordered nested
  object cannot pass as unchanged, at all three of those gates — and before the append is
  written, not after.
- **`correction_reason` comes from a closed vocabulary**, validated on the row:
  `source_record_corrected`, `source_receipt_binding_failed`, `evidence_artifact_regenerated`.
  A **retraction** takes the narrower pair — `source_record_corrected`,
  `source_receipt_binding_failed`. Free text let "we disagree with the outcome" wear the same
  clothes as "the upstream official record changed"; §8 restricted retractions and left plain
  corrections, which do identical damage, under no restriction at all.
- **The supersession ratchet.** A superseding row that cannot be graded **does not delete the
  grade its predecessor already earned.** The append-only log keeps every superseded row
  byte-identical forever, so that grade is still computable, and the verdict basis retains it
  (listed row by row in `verdict_basis.retained_from_superseded`). Coverage is deliberately
  *not* repaired by the ratchet: a retraction still lowers coverage and still widens the
  bounds, exactly as above. What supersession cannot do is make a losing **number** disappear
  from the verdict. Without this, §8's promise held for the hit rate and was false for the
  kill-bearing mean: on a two-row cohort (+1% winner, −40% loser) a supersession that ungraded
  the loser moved the pooled mean from −19.5pp to +1.0pp and the verdict from `kill` to
  `tested_null`, with `issued_n` unchanged at 2.
- A retraction is valid only for a **source-evidence correction** — the upstream official
  record changed or the receipt binding failed. Disagreement with an outcome is never a valid
  reason. Every retraction states its reason in the row.
- **Residual risk, disclosed:** a retraction issued after an outcome is observable is still a
  discretionary act. The mitigation is structural, not procedural — the row keeps its slot in
  the denominator, `retracted_n` is printed in every report, and the ratchet keeps its number
  in the verdict basis — but it is not eliminated. The ratchet has its own cost, also
  disclosed: when a supersession is *genuine* (the official record really did name a different
  issuer), the verdict basis reads the superseded row's grade. Every such row is printed with
  both identities, so the cost is legible rather than silent, and it is preferred to the
  alternative, in which any unresolvable row is a discretionary exit from a loss.

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
| 1.0.0 | 2026-08-06 | initial registration | Registered with zero candidates in existence. |
| 2.0.0 §7 | 2026-08-06 | verdict regions test bootstrap **intervals** against registered thresholds; δ\* = +3.0pp registered; `_PLACEBO_FLOOR` and the literal `0.5` moved into the binding declaration | Point comparisons at the 1.0.0 gate floor fired KILL on noise ~25–40% under a true null and ~15–25% against a genuine +3pp edge. Two of three thresholds sat outside the declaration where §9's drift guard could not see them. |
| 2.0.0 §7 | 2026-08-06 | `min_distinct_source_events` 40 → **545**; `accrual_expiry_date` 2027-08-06 → **2029-08-06** | 545 is what δ\* = 3.0pp needs at σ_paired = 25pp, α = 0.05, power = 0.80. The expiry moved so the registered N is reachable in principle; a gate unmeetable inside its own window guarantees `expired_unmeasurable`. |
| 2.0.0 §2 | 2026-08-06 | H2 tests the **conditional** hit rate's interval, not the Manski lower bound over the fixed cohort | `lower = hits/issued = p·coverage`; at the 0.70 coverage floor `lower > 0.50` demanded a conditional hit rate above 71.4%, so `SUPPORTED` was unreachable by any plausible signal. Bounds remain printed as coverage disclosure. |
| 2.0.0 §6 | 2026-08-06 | added `min_distinct_known_at_months` (12) and `min_distinct_entry_sessions` (120) | 1.0.0 counted months off `effective_at`, so one backfill night with 40 events across 12 historical months and **one** `known_at` satisfied the gate at coverage 1.0 — 40 rows, one independent draw. |
| 2.0.0 §4 | 2026-08-06 | placebo delta is **paired** on `candidate_id`; placebo grading gains the calendar and price-basis refusals; `read_window_sha256` hashes in **read order** | The delta fed the kill condition as a difference of means over two different row sets. The placebo lacked `grade_row`'s two refusals. A sorted hash is permutation-invariant, so an entry/exit inversion left it unchanged. |
| 2.0.0 §7 | 2026-08-06 | `min_verdict_outcome_coverage` (0.70) registered; `market_relative_return_bounds` emitted as sensitivity; the one-look verdict is **latched** | The kill-bearing mean was unbounded and resolution-conditioned; `evaluate_verdict` recomputed every run with no latch, which is optional stopping against a rule promising one look. |
| 2.0.0 §8 | 2026-08-06 | correction field **allowlist**; closed `correction_reason` vocabulary; the **supersession ratchet** | A plain correction could rewrite `known_at` (re-cutting the entry session after the outcome was observable), `ticker`, `horizons`, or `entry_rule`; the reason was unvalidated free text; and ungrading a loser moved a two-row cohort from `kill` to `tested_null`. |
| 2.0.0 §1 | 2026-08-06 | `is_late_discovery` admission is fail-**closed** | `bool(...)` admitted a payload that omitted the key — the only fail-open admission test in the family. |
| 2.0.0 §5/§6 | 2026-08-06 | coverage walker covers `*_mean`/`*_summary`/`*_bound`; `window_independence` emitted | The walker was structurally blind to the mean the verdict reads; `issued_n` counted overlapping windows as independent draws with no disclosure. |
| 4.1.0 §1 | 2026-08-08 | **identity basis registered**: `exact_linked` may rest on `source_record_recipient` or on `award_level_recipient_at_collection`; the basis is printed on every candidate and is descriptive, never a verdict input or a stratum | §1 constrained the link *class* and was silent on *basis*, which was harmless only while the answer could not change: the action rail carries no recipient identity (35,140/35,140 null UEIs), so nothing on the only admitted rail could ever be exact-linked. Attaching the award's recipient of record makes that rail linkable, widening which action records can satisfy the unchanged exact-link rule; the snapshot rail remains display-only under 4.0.0's `family_rail_mismatch` fence. Registered pre-observation (`candidate_ledger.jsonl` still 0 bytes, no issuance log), so §9's post-issuance freeze is not engaged. |
| 4.0.0 §7.6.1 | 2026-08-08 | the **paired placebo delta** carries `min_verdict_outcome_coverage`; new blocked reason `paired_placebo_coverage_below_registered_floor`; kill condition renamed **GRV-FA1-KILL-V3** | The coverage floor guarded the real side only. A cohort meeting every registered gate at 545 events with the placebo priced for ONE candidate reached a decided verdict on `paired_n = 1`; flipping that single row's placebo window flipped the verdict of all 545, on both the KILL and the SUPPORTED branch. `paired_coverage` was computed, printed, and read by nothing. |
| 4.0.0 §7.6.2 | 2026-08-08 | the verdict is gated on `non_overlapping_window_estimate ≥ planning_n_required`, computed over the **verdict basis**; new blocked reason `independent_draws_below_registered_n` | §7.2's N is a power calculation and counts independent draws. 552 rows from 12 issuers on consecutive entry sessions gave `non_overlapping_window_estimate = 12`, a satisfied gate, and an interval narrowed ~6.8× by overlap that cleared δ\* — a threshold the same evidence fails at its honest N. §6 already required the number to be printed; nothing read it. |
| 4.0.0 §7.6.3 | 2026-08-08 | `n < 2` emits **no interval** (`None`), never a degenerate `(v, v)` | §7.1 tests intervals so a point comparison cannot decide a verdict; a zero-width interval passes every test the point passes, so 2.0.0's remedy was reintroduced as its own defect and one observation cleared a threshold derived for N = 545. |
| 4.0.0 §5 | 2026-08-08 | a **non-finite close is a missing bar**; the canonical serializer refuses `NaN`/`Infinity` | `NaN <= 0` is `False`, so the accessor passed every NaN and inf. A NaN entry bar made `nan > 0 == False` and graded the row a **MISS** — a null endpoint scored as a loss, reading as resolved with full coverage — and the emitted report carried a bare `NaN` literal, which RFC 8259 forbids: it round-tripped in Python and was unparseable to conforming readers. |
| 4.0.0 §4 | 2026-08-08 | entry requires a calendar covering `known_at`; exit maturity is **strict** against `as_of`; the **session-list prefix digest** is frozen on the row (`calendar_revised` refusal); the placebo takes `as_of`; `regrade_diff` gains calendar and deletion axes | `first_index_after` returns 0 for a day the calendar never covered, so a trimmed panel filled rows on POST-issuance bars. A date-granular `as_of` consumed the exit close ~20h before the US close. A vendor revision keeps the same `calendar_id` and re-cut frozen windows, which the diff attributed to the price vintage. The placebo had no `as_of` at all. A vanished grade produced no drift row. |
| 4.0.0 §8 | 2026-08-08 | the correction allowlist is enforced in `parse_issuance_log`, `append_issuance_rows`, and `cohort_rows` | A hand-built superseding row rewriting `known_at`/`ticker`/`horizons` passed all four log-side gates; the allowlist lived only in `build_correction_row`. |
| 4.0.0 §1 | 2026-08-08 | the family is **fenced to the action rail**: `source_event.source_rail` must be exactly `usaspending_award_action`, fail-closed, else `family_rail_mismatch` | Sibling PR #5085 admits snapshot-rail `reported_obligation_balance_changed` events into the `award_obligation_change` **candidate** family — correct at display tier. §1 gated only on the family name, so this grader, registered for funded-**ACTION** acceleration, would have begun issuing on `award_cumulative`-differenced balance deltas: a restatement, a late correction and a genuine obligation are indistinguishable in that number and its magnitude is not the size of any event. Two measurement units in one graded cohort is the amount-class conflation, arriving through the rail rather than the family name. Verified at this PR's base: `candidates.py` admits both rails and `admit` accepted such a candidate. No second family is registered for the snapshot rail — that is a deliberate future preregistration, not a ride-along. |
| 4.0.0 §1 | 2026-08-08 | an unmapped issuer **abstains** as `mapping_missing` with a null ticker | `admit` had no ticker check, so an unmapped issuer was admitted and then raised inside the row builder: batch-fatal on the first one, with no abstention row and no printed null. The reviewed graph carries unmapped issuers today. |
| 4.0.0 §5 | 2026-08-08 | empty cohorts report coverage `empty`, monthly buckets carry per-month coverage, `verdict.inputs.coverage` cites the verdict basis | `0 == 0` reported COMPLETE coverage on the lobe's actual zero-candidate state; every monthly bucket repeated the cohort-wide coverage; and the verdict printed the cohort's coverage beside numbers computed over a different denominator. |
| 3.0.0 §11 | 2026-08-07 | **disclosure-label layer registered**: earnings-window and subsequent-filings labels, their two PIT clamps, and the `unavailable` / `none_in_window` split | Wave 9G's build list asks for "earnings-window and subsequent-filings outcome labels where available" and 1.0.0/2.0.0 shipped neither — the word `earnings` did not appear in the instrument, the registration, or the suite. Registered pre-observation (log still absent, ledger still 0 bytes) and deliberately **outside** the decision rule, so §7's N = 545 continues to describe the statistic it was derived for. |

## 11. Disclosure labels — earnings windows and subsequent filings (descriptive)

The Wave 9G build list asks for "earnings-window and subsequent-filings outcome labels **where
available**". This section registers what those labels mean, before any of them exists.

**What they are for.** A graded horizon may span an earnings print or a subsequent periodic
filing. If it does, the return it produced is not cleanly attributable to the award action the
family issued on. The label records that so a reader can partition the cohort afterwards. It
is a *contamination marker*, not an outcome, not a hit, and not a signal.

**What they may never do.** They are **not** an input to GRV-FA1-KILL-V2 or to any verdict
region. §7.2 derives N = 545 from a power calculation over the paired market-relative mean; a
decision rule that grew a term would leave that registered N describing a statistic the
instrument no longer computes. Enforcement is structural rather than by convention:
`build_cohort_report` computes the labels, holds them aside, calls `evaluate_verdict`, and only
then attaches them to the report. The suite pins the ordering by asserting that the verdict
block of a report built *with* a disclosure calendar is byte-identical to one built *without*.

**The three states, and why the third exists.** This is the point of the whole section:

| State | Meaning |
|---|---|
| `observed` | the calendar covers this issuer and ≥1 disclosure fell inside the graded window |
| `none_in_window` | the calendar covers this issuer and **nothing** fell inside the window |
| `unavailable` | the label could not be computed; a named reason says why |

`none_in_window` is evidence. `unavailable` is the absence of evidence. The natural
implementation — a mapping that returns an empty list for an unknown ticker — merges them, and
merges them in the flattering direction: every issuer with the *worst* disclosure data scores
as the *cleanest* window. A `DisclosureCalendar` therefore declares `covered_tickers`, a ticker
outside that set is `unavailable`/`issuer_not_in_calendar`, and no code path collapses the two.
The `unavailable` vocabulary is closed: `no_disclosure_calendar`, `issuer_not_in_calendar`,
`row_ungraded`, `source_outage`.

**The two point-in-time clamps**, both mutation-proved in the suite:

1. **Window clamp.** Only disclosures dated inside `[entry_session, exit_session]` — the
   graded window, computed in one place (`_disclosure_window`) so a widening is a one-line
   mutation the suite can catch. A disclosure after the exit did not touch the measured return.
2. **Availability clamp.** Only disclosures whose own `known_at` is at or before the report's
   `as_of`. Filing indexes publish on a lag, so an event carries an availability clock separate
   from its event date; without this clamp a label would use tomorrow's index to describe a
   window already graded.

**Denominators.** Both `earnings_window_rate` and `filing_window_rate` are conditioned on rows
whose label was *computable*, and both carry an `outcome` coverage whose universe is the fixed
issuance cohort. Poor filing coverage therefore reads as poor coverage, never as a clean
cohort — the §5 rule applied to the label layer.

**Contract gap (carried, not closed).** The candidate payload has no earnings date and no
filing pointer: `earnings_transmission` is mechanism prose, not a clock. The calendar is
therefore supplied by the caller, and with no calendar supplied every label is
`unavailable`/`no_disclosure_calendar` — which is the honest reading of "where available" on
2026-08-07, when no such calendar is wired.
