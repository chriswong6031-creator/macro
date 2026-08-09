# Options Prophet shadow architecture

Status: canonical display-only foundation
Schema: `options.prophet_shadow/v1`
As of: 2026-08-08

## Audit verdict

The current Options surface does **not** operate as an independent, promoted
options-native stock-picking engine. Flow Leaders supplies options-derived
context and two Pick Lab books (`plab_flow_leader`, `plab_flow_washout`) create
forward-ledger fires, but the production direction gate is false, both flow-book
ledgers are accruing, options-entry/dislocation evidence has zero authority, and
there is no executable option-contract lifecycle or calibrated trajectory model.

Therefore the first lawful product slice is a transparent shadow projection,
not a new composite. `scripts/build_options_prophet.py` publishes the current
state to `site/options_prophet/index.json` and R2 key
`options_prophet/index.json` without changing Macro Prophet ranking.

## Three engines, kept separate

| Engine | Current evidence | Current readiness | What is still missing |
|---|---|---|---|
| Information | Flow Leaders magnitude/recurrence plus Pick Lab fires | Not ready for directional claims while the applicable signing gate fails | Production-calibrated signed opening/closing participant flow, PIT surface features, and a forward directional gate |
| Positioning | OI confirmation, gamma regime, options-entry state, dislocation research | Context can be available; promotion remains false while the source gates confer zero weight/authority | Stable era-split validation of positioning primitives and explicit dealer-assumption sensitivity |
| Execution | None in this projection | Not ready | OCC contract selection, NBBO/spread/liquidity checks, executable entry rule, fill model, mark ledger, lifecycle, and exit attribution |

An engine is never labelled ready merely because a display artifact exists.

## Projection contract

The artifact contains:

- `opportunities`: only same-session fires already admitted by the two Pick Lab
  flow books after their liquidity and refire-lockout rules;
- `watchlist`: the stable union of Flow Leaders Board A then Board B, preserving
  both memberships and source positions without a new score or re-ranking;
- `readiness`: component and gate truth for information, positioning, execution,
  sources, signing, forward sample, and trajectory calibration;
- positioning evidence includes the options-entry coverage census (`n_rows`,
  `n_features`, selected IV/vanna/charm coverage, and structural-null highlights)
  without reading the parquet or converting coverage into a score;
- `direction`: no originated direction and therefore `reliable=false`; the
  source-specific signing measurement is reported separately and fails closed;
- `forward_ledgers`: the existing flow-book horizons/path outcomes, plus an
  explicit statement that paired incremental options attribution is absent;
- `trajectory`: withheld until a PIT path/exit calibration passes;
- `macro_feedback`: always `enabled=false`, `weight=0` in this version;
- `provenance`: paths, schemas, vintages, availability, and read errors for every
  source gate/artifact.
- exact nullable `decision_at` and exact `available_at` fields at the projection
  and fire boundaries. Wave 0 publishes `decision_at=null` because Pick Lab does
  not yet expose an exact decision clock; it does not infer one from the session
  date;
- `accrual.events` as immutable fire counts, separate from
  `accrual.outcomes.horizons` at 1h, EOD, 1d, 3d, 5d, 10d and expiry. Only the
  legacy 5d/10d books are instrumented today, and they are explicitly
  `pit_exact=false`;
- a `context_inputs.konseki_market_memory` consumer seam pinned to
  `konseki.market_memory/v1`, `authority=context_only`, weight zero and no
  rank/gate/size permissions. It is connected only with a nonempty immutable
  memory ID plus exact, time-ordered `decision_at` and `available_at`; incomplete
  receipts fail closed. No Market Memory producer is added by this wave;
- an execution envelope on every fire with OCC symbol, right, strike, expiry,
  entry quote, stop, targets and take-profit management all null/withheld until
  a point-in-time quote/fill/lifecycle engine exists.

Rows fail closed at the publication boundary. A foreign, stale or cold Flow
Leaders artifact cannot project watch rows; a non-display Pick Lab contract or a
session mismatch cannot project fires. The published `source_alignment` receipt
is deliberately scoped to Flow Leaders and Pick Lab only; the separately dated
research gates disclose their own vintages and are never implied to be
point-in-time aligned with that session.

The JSON boundary is strict: non-finite upstream research values become `null`
and serialization rejects `NaN`/infinity. The credentialed R2 mirror validates
the exact schema/authority/mode before upload, reports missing credentials or an
upload failure with a non-zero strict exit, and verifies the resulting object via
R2 HEAD. The nightly may continue after that failure, but it emits an explicit
publication warning instead of silently claiming success.

## Abstention and model-portfolio boundary

The product target is a sparse, abstention-first stream: roughly three to four
issued calls every few sessions when the environment supports them, not a
ranked scanner. Wave 0 does not pretend that a source-ordered research queue is
that portfolio. The artifact therefore marks three distinct stages:

1. **Research watchlist** — broad options evidence, source-ordered and never a
   recommendation;
2. **Research fire** — a governed Pick Lab event, still not an issued position;
3. **Issued model portfolio / managed position** — not implemented in Wave 0.

The Terminal keeps true fires primary and the research queue collapsed. A later
R6 slice must construct the issued portfolio jointly, not select the top four
independent scores. Its frozen policy must include regime fit, correlation and
sleeve caps, cash/abstention, maximum new picks, symbol/refire cooldown,
minimum-hold clocks, and position-level entry/stop/T1/horizon/management. Every
issue, suppression and management action needs exact `decision_at` and
`available_at` receipts.

### Non-overlapping next-slice ownership

Wave 0 owns `scripts/build_options_prophet.py`, schema
`options.prophet_shadow/v1`, its strict R2 publisher, and the Terminal
research-fire/readiness/accrual surface. The next slice should own a separate
operator-reviewed `options.issue_desk/v1` artifact plus review ledger as the
near-term speed path: frozen Macro candidates + options/regime/execution receipts,
explicit approve/reject, and 0–4 Research Portfolio additions per rolling three
sessions. It cannot change Macro rank or call itself automatic Options Alpha.
The later automatic lane owns `options.model_portfolio/v1` plus append-only
portfolio event, position and outcome ledgers. Both may consume this shadow
artifact and the Konseki receipt as context, but neither may retrofit allocation
or management authority into the Wave-0 watchlist projection. Konseki remains
context-only and weight zero unless its own independent promotion process says
otherwise.

## Hard fences

This version must never:

1. turn a Flow Leaders watch row or raw `fire_a`/`fire_b` flag into an
   opportunity when Pick Lab did not ledger a fire;
2. compute a composite, confidence, probability, direction, target, or contract;
3. treat gross OPRA volume, volume over prior OI, or conventional GEX as signed
   customer intent or known dealer inventory;
4. send a weight, rank, gate, size, or escalation into Macro Prophet;
5. call a path or take-profit time calibrated before a registered PIT test and
   forward shadow cohort support it.

## Measurement sequence before promotion

1. Freeze point-in-time data availability: trade/quote timestamps, previous-night
   OI, surface vintages, corporate actions, and vendor/venue coverage.
2. Validate information features separately: trade signing/open-close inference,
   delta-weighted imbalance, IV spread/skew/term-structure changes, and event and
   liquidity controls.
3. Validate positioning separately: GEX as a path/volatility regime first; vanna
   and charm as experimental sensitivities; publish the dealer-inventory
   assumption and sign-flip sensitivity.
4. Build execution only after the signal survives: point-in-time contract
   selection, spread/OI/volume filters, next-observable quote entry, adverse fills,
   mark-to-market lifecycle, and executable exits.
5. Run immutable paired books: `macro_base`, `macro_plus_options`, and
   `options_originated`, with identical timestamps/universe/costs. Only the paired
   incremental result can propose a Macro feedback weight.

## Primary-source evidence boundary

- [Cboe Open-Close Volume Summary](https://datashop.cboe.com/cboe-options-open-close-volume-summary)
  is appropriate for participant/action/open-close aggregates on Cboe venues; it
  is not whole-market trade-level intent.
- [OCC/OIC general options guidance](https://www.optionseducation.org/referencelibrary/faq/general-information)
  explains why reported OI is an end-of-day stock and why volume alone cannot say
  whether positions opened or closed.
- [Pan and Poteshman, *The Information in Option Volume for Future Stock Prices*](https://www.nber.org/papers/w10925)
  supports opening buyer-initiated flow as informative; it does not support gross
  call/put volume as a drop-in substitute.
- [Hu, *Does Option Trading Convey Stock Price Information?*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1970702)
  motivates delta-weighted option-induced order imbalance.
- [Federal Reserve note on option-implied densities](https://www.federalreserve.gov/econres/ifdp/files/ifdp1294.pdf)
  frames option-implied distributions as risk-neutral, not literal physical path
  probabilities or exact take-profit clocks.

These references motivate candidate measurements. They do not promote this
artifact or any current Options Prophet claim.
