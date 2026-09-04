# Global Liquidity Transmission v1 — State Methodology and Contract

**Schema:** `global_liquidity_transmission.v1`

**Producer:** `w-liq.1.0`

**Authority:** measurement only

**Scope:** W-LIQ.1 state, quality, and freshness. Later shock, transmission,
repricing-gap, product, and learning blocks are intentionally absent.

## 1. Contract boundary

The public sample at
`site/liquiditydata/global_liquidity_transmission.json` has exactly four
top-level blocks:

- `meta`: schema, producer, causal policy, scope, lineage, and forbidden authority;
- `state`: candidate factor values and exact units;
- `quality`: source semantics, current US quality, separate credit context, and limitations;
- `freshness`: coverage plus per-component source/reference/availability receipts.

Consumers must tolerate additive fields inside these blocks, but must not infer
the future architecture blocks from their absence. In v1 there is no `shocks`,
`transmission`, `repricing_gap`, `opportunities`, or trading/action block.

The artifact can describe state. It cannot execute, recommend, allocate, alert,
rank an opportunity, set a gap score, or authorize a later workstream.

`state.event_reference` is the frozen W-LIQ.3 seam requested by PR #124. It is
not an episode and does not import the lab. A downstream adapter copies this
object into its closed envelope without z-scoring, classifying, filling, or
deriving a fallback.

## 2. Causal clock

For source value \(x_i\), define an economic reference date \(r_i\) and an
availability date \(a_i = r_i + L_i\), where \(L_i\) is the configured
conservative business-day lag. A weekly W-FRI state at \(t\) can use only values
whose \(a_i \leq t\). A carried value becomes unavailable when
\(t-r_i\) exceeds its component staleness threshold.

Fed and ECB reference their observation dates. BoJ monthly total assets are
first anchored to calendar month-end because the provider observation is an
end-of-period value despite its first-of-month label. FX is sampled on or before
the economic reference date—not the later build or availability date.

Every standardisation is prior-only:

\[
z_t = \frac{x_t - \mu(x_{<t})}{\sigma(x_{<t})}
\]

The configured minimum history is 52 weekly observations. There is no centered
window, full-sample normalisation, backfill from future releases, or zero fill.

The event-reference clock object distinguishes:

- `state_asof`: the W-FRI decision grid stamp;
- `latest_component_observed_at`: newest economic reference date among the
  monetary inputs;
- `monetary_release_at`: latest conservative availability date among the usable
  **monetary** inputs only — a narrow diagnostic, never the envelope clock;
- `evidence_available_at`: the conservative **all-evidence** availability clock
  (see the law below);
- `release_at`: an alias of `evidence_available_at`, kept for field-name
  continuity;
- `first_known_at`: the timestamp when this exact producer payload was first
  generated; and
- `release_clock_precision=conservative_date_only`: the repository does not
  claim intraday release timestamps.

### The evidence-availability law

An event envelope may never claim an observed/release time earlier than the
latest availability of **any** field it carries downstream. `state.event_reference`
carries three families of evidence, so `evidence_available_at` is the maximum
over all three, and `clocks.evidence_available_at_contributions` publishes each
family's contribution so the binding leg is always visible:

1. every **monetary** component receipt — drives `monetary_*` and the direction
   label;
2. every **USD-funding** component receipt — drives `conditions.usd_funding_impulse`
   and the funding half of `component_snapshot`;
3. the embedded **`us_liquidity_quality`** leg — drives `event_reference.quality`
   and `conditions.us_liquidity_quality`.

Component receipts are counted whether or not they are `usable`, because their
dates are copied into `component_snapshot` verbatim either way.

`quality.global_credit` is deliberately **outside** this clock: it is not part of
`state.event_reference`, and it already carries its own per-component
`reference_date` / `available_date` stamps. It is kept separately timestamped
rather than folded into the envelope clock, which is the other option the repair
law permits for evidence that is not copied into the event reference.
`clocks.evidence_available_at_excludes` says so in the payload.

The `us_liquidity_quality` object in `data/regime/latest.json` exposes only an
`asof` and carries no separate publication stamp. That `asof` is therefore taken
as a **conservative availability lower bound**: the object cannot have existed
before its own as-of date, and the true publication happened at or after it.
This is deliberately a bound, not a measurement — it keeps the combined clock
safe against look-ahead rather than precise.

Before this repair, the envelope derived its release clock from the monetary
inputs alone. On 2026-08-21 that published `release_at=2026-08-20` while the same
envelope already carried HY-OAS and real-yield receipts available 2026-08-21 and
a `us_liquidity_quality` object with `asof=2026-08-21`. The repaired clock reads
2026-08-21 for that row.

The W-LIQ.3 adapter maps its `observed_at` to producer `evidence_available_at`
(`clocks.adapter_observed_at_field` names it) and its `known_at` to
`first_known_at`. `known_at` therefore cannot precede the availability of any
evidence in the envelope. The historical backfill reconstructs observation and
conservative release dates but **cannot** reconstruct exact first-known payload
timestamps before this producer existed.

## 3. Candidate factor semantics

### `monetary_stance`

For each usable Fed/ECB/BoJ USD balance-sheet series, take log level and its
prior-only expanding z-score. Combine available scores with equal configured
weights, renormalising across usable components. Publish only when the weighted
coverage ratio is at least 2/3.

This is a candidate **relative level** factor. Positive means the available CB
balance-sheet levels stand above their own earlier expanding distributions. It
does not mean every bank expanded this week and it is not the existing
WALCL−RRP−TGA quality verdict.

### `monetary_impulse`

First weekly difference of `monetary_stance`:

\[
I_t = S_t - S_{t-1}
\]

Positive means the composite relative stance improved during the week.

`monetary_impulse` is **not standardized**. It is a first difference of an
already-z-scored stance, so its unit is
`weekly_change_in_expanding_z_score` — a change in z, not a z. Nothing may
threshold it as if it were a shock z-score.

The contract label reads `flat` inside a small frozen ±0.05 band expressed in
those raw units, and otherwise `expanding` or `contracting` (or `unknown` when
the impulse is unavailable). The band lives at
`quality_thresholds.monetary_impulse_flat_band` and is republished, with its
unit and config key, at `state.label_rule`. It was previously named
`monetary_impulse_z`, which claimed a standardization the quantity does not have.

### `monetary_impulse_z`

The prior-only causal expanding z-score of `monetary_impulse`, built with the
same `causal_expanding_z` transform used for every component score:

\[
Z_t = \frac{I_t - \mu(I_{<t})}{\sigma(I_{<t})}
\]

Mean and standard deviation at `t` contain only impulses strictly before `t`
(minimum 52 prior weekly observations), so a future impulse can never restate a
past `monetary_impulse_z`. Unit:
`prior_only_expanding_z_score_of_weekly_change_in_expanding_z_score`.

This is the **only** field a downstream materiality threshold expressed in
z units may gate. It is published as `state.monetary_impulse_z` and copied to
`state.event_reference.magnitude_z`; the raw delta remains available and
separately united as `state.event_reference.magnitude`.

The adapter-ready `direction` is the raw sign of `magnitude` (`-1` or `1` when
finite), while `direction_label` is the thresholded contract label. Thus a tiny
negative observation can truthfully be `direction=-1` and `direction_label=flat`;
W-LIQ.3's separately ratified materiality policy decides whether it can mint an
episode. W-LIQ.1 does not make that decision.

### `orthogonalised_impulse`

Residual of the current impulse on the current stance, using an OLS intercept
and slope fit only to paired observations strictly before the current week:

\[
O_t = I_t - (\hat\alpha_{<t} + \hat\beta_{<t}S_t)
\]

The minimum prior paired history is 104 weeks. This reproduces the architecture’s
named candidate factor; it does not residualise liquidity against BTC or other
market outcomes.

### `liquidity_breadth`

Share of currently usable monetary component z-scores that improved from the
prior week, from 0 to 1. Missing/stale components reduce reported coverage and
are absent from numerator and denominator; if aggregate coverage fails, breadth
is null. Missing is never interpreted as “not worsening.”

### `credit_impulse_global`

Always null in W-LIQ.1, with status
`insufficient_comparable_pit_coverage`. US commercial and industrial loans and
China TSF differ in construction; the BIS structural series lack repository
release-vintage timestamps. The contract exposes separate current US/China
directions so a null does not hide what is known.

### `usd_funding_impulse`

Equal-weight prior-only expanding z composite of 13-week changes in:

- negative broad dollar log change;
- negative 10-year real-yield level change;
- negative HY OAS level change.

Positive consistently means easier USD funding. This stays separate from the
monetary state and is not used to manufacture the raw CB factor.

### `policy_liquidity_impulse`

In v1 this is an explicit alias of `monetary_impulse`, included to reserve the
architecture’s policy-liquidity family without adding a second calculation.
Consumers must not sum both fields.

## 4. Quality and source semantics

`quality.source_semantics` preserves four separate mechanisms:

1. **monetary** — Fed/ECB/BoJ balance-sheet stance;
2. **treasury plumbing** — existing canonical US WALCL−RRP−TGA quality;
3. **credit** — separate US bank-credit and China TSF context;
4. **USD funding** — dollar, real yield, and credit-spread pressure.

This separation prevents an easy dollar or a TGA drawdown from being relabelled
as central-bank easing. The embedded US quality object wins for its own scope.
On 2026-08-21, for example, the candidate global impulse is `flat` while the
canonical US liquidity-quality read is `contracting`; the correct result is the
dual read, not a forced consensus.

`quality.status=measured` means all configured state/funding components are
usable and the canonical US quality object is present. It is not statistical
validation, product acceptance, or live/deployed status.

### The two closed label vocabularies

The contract publishes two closed vocabularies that answer different questions.
Their only shared member is `unknown`, and **no sentence in this repository may
describe one using the words of the other**:

| Vocabulary | Question it answers | Members | Published enum |
|---|---|---|---|
| state direction | which way is the global monetary state moving? | `expanding`, `flat`, `contracting`, `unknown` | `state.label_enum`, `state.event_reference.direction_label_enum` |
| state-vs-US-quality agreement | do the global state and the canonical US liquidity-quality read agree, and in which sense? | `easing`, `tightening`, `mixed`, `unknown` | `state.event_reference.quality_enum`, `quality.event_quality_enum` |

`easing` is **not** a synonym for `expanding` and `tightening` is **not** a
synonym for `contracting`. `state.label` and `direction_label` never take a
value from the agreement vocabulary, and `event_reference.quality` never takes a
value from the direction vocabulary. `engine/global_liquidity_transmission.py`
freezes both as `STATE_LABEL_ENUM` and `QUALITY_LABEL_ENUM`, and
`test_every_emitted_label_belongs_to_its_own_closed_vocabulary` proves every
emitted label is a member of its own enum and that every declared member is
reachable.

`state.event_reference.quality` is assigned as:

- `easing` only when the global state label is `expanding` and canonical US
  quality is `benign-expansion`;
- `tightening` only when the global state label is `contracting` and canonical
  US quality is `contracting`;
- `unknown` only when both are unknown;
- `mixed` for every conflicting or non-confirming combination.

`confidence` is **data** confidence: monetary coverage multiplied by the mean
disclosed PIT-reliability coefficient of usable components (low revision risk
1.0, medium 0.75, high/unknown 0.5). It is not a probability, alpha confidence,
or promotion grade. Current confidence is 0.833333: full 3/3 coverage with one
low-risk and two medium-risk histories.

## 5. Coverage and staleness

The current contract publishes `monetary_coverage_ratio` and
`funding_coverage_ratio` plus every component’s source ID, economic reference
date, availability date, age, staleness limit, PIT class, and revision risk.

Coverage behavior is fail-closed:

- at least 2/3 of each basket is required;
- weights are renormalised only among usable components;
- values are never filled with supportive zero;
- state/breadth/funding become null when the relevant gate fails;
- quality/freshness mark the exact missing or stale source.

The event seam maps the fields exactly as follows:

| W-LIQ.3 envelope meaning | Producer field | Frozen meaning |
|---|---|---|
| producer schema | `meta.schema` / `state.event_reference.producer_schema` | exact `global_liquidity_transmission.v1` |
| source snapshot hash | `meta.source_snapshot_hash` | SHA-256 of config hash, all component snapshots, quality/credit hashes, and state as-of |
| model version | `meta.model_version` | `glt_state.v1`; changes only with factor semantics/model law |
| data version | `meta.data_version` | `glt_data:<16 hash chars>` derived from the full source snapshot hash |
| state family | `state.event_reference.state_family` | `monetary_impulse` |
| shock/source type | `state.event_reference.shock_type` | `policy_liquidity_impulse`; a source type, not a minted shock |
| direction | `state.event_reference.direction` | raw sign of `magnitude`, null only if `magnitude` is unavailable/exactly zero |
| direction label | `state.event_reference.direction_label` | state-direction vocabulary: `expanding` / `flat` / `contracting` / `unknown`, per `direction_label_enum` |
| raw magnitude | `state.event_reference.magnitude` | copied `state.monetary_impulse`; unit in `magnitude_unit` = `weekly_change_in_expanding_z_score`; **not standardized** |
| standardized magnitude | `state.event_reference.magnitude_z` | copied `state.monetary_impulse_z`; unit in `magnitude_z_unit`; prior-only causal expanding z of the raw delta; the only field a z-unit materiality threshold may gate |
| breadth | `state.event_reference.breadth` | copied 0–1 monetary breadth |
| quality | `state.event_reference.quality` | agreement vocabulary: `easing` / `tightening` / `mixed` / `unknown`, per `quality_enum` and the rule above |
| observed clock | `state.event_reference.clocks.evidence_available_at` | conservative maximum availability over monetary, USD-funding, and US-quality evidence; `release_at` is its alias; named by `clocks.adapter_observed_at_field` |
| known clock | `state.event_reference.clocks.first_known_at` | first generation of this exact payload; named by `clocks.adapter_known_at_field` |
| confidence | `state.event_reference.confidence` | 0–1 lineage/coverage confidence, never predictive confidence |
| coverage | `state.event_reference.coverage` | monetary weighted usable coverage ratio |
| freshness | `state.event_reference.freshness` | `fresh`, `degraded`, or `unknown` from current monetary inputs |
| conditions | `state.event_reference.conditions` | copied US-quality label and separate funding impulse |
| regional gates | `state.event_reference.regional_gates` | empty; W-LIQ.4 owns future gates |
| component snapshot | `state.event_reference.component_snapshot` | exact per-component receipt/spec/current contribution/history/component hashes |

## 6. Snapshot, version, and amendment law

Each component snapshot contains its source receipt, full model spec, current
contribution, a stable hash of the complete dated derived history used by the
expanding transform, and a component SHA-256. The overall
`source_snapshot_hash` is canonical JSON SHA-256 over:

- the full producer config hash;
- all monetary and funding component snapshots;
- the canonical US-liquidity-quality object hash;
- the separate global-credit-context hash; and
- the state as-of date.

`generated_at` and `first_known_at` are deliberately excluded from the source
hash: regenerating identical inputs is the same immutable source snapshot. A
builder retry with the same hash preserves the earliest already-published
`first_known_at` while updating `generated_at`. A
source revision or model/config change produces a different source hash and
data/model version. It must be published as a new observation; it never rewrites
a previously persisted first-known shock. W-LIQ.3 owns append-only episode and
amendment ledgers. W-LIQ.1 owns source snapshots and does not duplicate those
ledgers.

**Note on `model_version` across the Sol semantic repair.** The repair that added
`monetary_impulse_z`, split the magnitude seam, renamed the flat-band config key,
and widened the availability clock changed factor semantics, which normally
requires a `model_version` bump. `model_version` is deliberately held at
`glt_state.v1`: this producer has never been accepted, merged, or published, so
no consumer has ever observed a different `glt_state.v1`. There is no prior
published episode to protect and bumping would falsely imply one existed. The
`data_version` and `source_snapshot_hash` did change, because the producer config
changed. Sol may overrule this and require a bump as a condition of acceptance.

## 7. Historical artifact and validation receipt

The causal backfill is
`data/global_liquidity_transmission/state_history.parquet`, with its receipt in
`state_history_meta.json`. It contains 1,482 W-FRI rows from 1998-04-03 through
2026-08-21. The first complete monetary stance is 2004-12-10 after source overlap
and the 52-week prior-only warm-up.

The frozen comparison at
`data/global_liquidity_transmission/factor_comparison_btc_4w.json` compares the
three architecture candidates against BTC’s forward four-week log return. It
uses a 208-week initial train window, 52-week expanding walk-forward test folds,
and a four-week purge. It is one preregistered asset/horizon diagnostic, not a
broad search or a promotion gate.

The result is honestly weak:

| Candidate | OOS n | OOS correlation | Directional accuracy | OOS MSE |
|---|---:|---:|---:|---:|
| monetary stance | 408 | 0.0646 | 0.4951 | 0.03501354 |
| monetary impulse | 408 | -0.0325 | 0.5368 | 0.03381118 |
| orthogonalised impulse | 408 | -0.1757 | 0.5368 | 0.03403506 |

No factor is promoted. The receipt neither tests the BTC→China/BABA hypothesis
nor supplies transmission curves; those belong to the later statistical
workstream specified in the masterplan.

For 2023–2026 the state parquet supplies conservatively release-aligned weekly
measurements, but the producer has no historical record of when an exact GLT
payload was first generated because GLT did not yet exist. Therefore
`state_history_meta.json` freezes
`2023_2026_exact_episode_chronology: []` with status
`unavailable_do_not_infer_from_backfill`. W-LIQ.3 must not convert backfill dates
into first-known episodes. If exact source chronology is later recovered, it
must arrive as a cited amendment before the event/holdout freeze.

## 8. Known limitations

- Full vintage reconstruction is unavailable for ECB and BoJ, so their earlier
  values retain medium revision risk even after conservative lagging.
- The historical parquet backfills the state-factor columns, coverage, and
  contributions. It does not project today's US quality or current-vintage
  credit context backward; a historical contract cutoff reports those contexts
  unavailable unless an exact as-of quality object exists.
- China M2 is excluded because the repository stores period dates without a
  usable release/vintage clock.
- NFCI/ANFCI are excluded because full histories revise and repository vintage
  coverage is absent.
- BoE, SNB, and PBoC total assets are omitted for lack of an adequate canonical
  balance-sheet feed; policy rates and FX are not substitutes.
- Central-bank balance-sheet levels are not interchangeable with broad money,
  bank credit, Treasury plumbing, or market funding. The contract keeps those
  mechanisms separate.
- A current measured artifact is not production deployment. W-LIQ.1 remains
  held for Sol’s schema and PIT-semantics acceptance under issue #123.

## 9. Reproduction

```bash
python3 scripts/build_global_liquidity_transmission.py
python3 -m pytest tests/test_global_liquidity_transmission.py -q
```

The tests cover month-end/release alignment, future-mutation invariance,
frequency alignment, staleness/coverage degradation, no supportive zero,
prior-only orthogonalisation, state-only schema scope, and purged walk-forward
folds.
