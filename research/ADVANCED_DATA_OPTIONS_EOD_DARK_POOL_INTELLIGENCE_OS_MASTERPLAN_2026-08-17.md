# Advanced Data: Options EOD + Off-Exchange Intelligence OS
## Recovery Masterplan — 2026-08-17

**Program:** Advanced Data / Options EOD / Off-Exchange Intelligence  
**Repository:** `mastermindx-market-intelligence/macro`  
**Status:** Recovery architecture; prior options sessions are not the execution authority  
**Chairman outcome:** Convert expensive, broad options and off-exchange data from a largely interpret-it-yourself dashboard into a standalone institutional-grade anticipation and risk intelligence lobe that materially improves Prophet when confluenced with it.  
**Execution law:** Outcome before code. One vertical slice at a time. Green CI is never production acceptance.  
**First authorized wave:** `AD-0` only — recovery archaeology, production truth, salvage adjudication, and exact AD-1 handoff.  
**Do not begin AD-1 until AD-0 is reviewed.**

---

# 0. Executive ruling

The existing Options EOD / Dark Pool product must **not** be treated as a nearly complete build that needs polish.

The recovered problem is deeper:

- the data layer appears materially more mature than the intelligence layer;
- the user is still required to interpret raw or lightly transformed options and off-exchange data;
- the page does not consistently answer what matters, why it matters, whether it is early, what is priced, what the horizon is, what invalidates the thesis, or whether the evidence should change a real decision;
- downstream use by Prophet, Neural Web, Sector Intelligence, and the Watchlist/Portfolio experience is not production-proven at the required level;
- previous work created substantial options infrastructure, canaries, research, tests, and handoffs, but much of it is not equivalent to a useful production lobe;
- prior effort and token spend are sunk cost. Artifacts survive only if they fit the recovered architecture and can pass real production proof.

The target is therefore **not an options dashboard**.

The target is:

> **Mastermind’s institutional derivatives, volatility, positioning, and off-exchange anticipation engine: a system that converts EOD options and off-exchange observations into ranked, time-sensitive, falsifiable intelligence signals, stands alone as an elite Advanced Data surface, and contributes bounded incremental information to Prophet without bypassing Prophet timing or entry authority.**

---

# 1. Frozen Chairman intent

## 1.1 Human job

In under one minute, the user must be able to answer:

1. What are the most important derivatives or institutional-positioning developments now?
2. Which names and sectors deserve attention?
3. Is the evidence directional, volatility-oriented, positioning-only, or risk-only?
4. What horizon does it matter over?
5. What is unusual relative to a defensible baseline?
6. What appears already priced?
7. What appears underpriced or asymmetric?
8. What independent evidence confirms or contradicts the thesis?
9. What is the trigger?
10. What invalidates the thesis?
11. Is the evidence fresh?
12. Is the name still tradeable and still buyable?
13. What does Prophet think?
14. What would make the signal wrong?

The product fails if the user must open raw chains and manually infer these answers.

## 1.2 Machine job

For every emitted signal, the lobe must be able to provide a deterministic, point-in-time, versioned record that can be:

- reproduced from immutable evidence;
- consumed by Prophet, Sector Intelligence, Neural Web, Watchlist, and Portfolio through existing Mastermind planes;
- corrected, superseded, retracted, and replayed;
- evaluated against forward outcomes without leakage;
- calibrated by family, horizon, event state, liquidity, and regime;
- disarmed independently when data quality or calibration degrades.

## 1.3 What this lobe must become

The lobe must answer four distinct questions instead of collapsing everything into a generic “options score”:

### A. Direction
Does qualified evidence lean toward upside, downside, or neither?

### B. Magnitude / volatility
Is the market-implied distribution rich, cheap, compressed, expanded, or event-mispriced?

### C. Positioning mechanics
Where might hedging mechanics accelerate, suppress, pin, or destabilize price?

### D. Crowding / risk
Is an apparently attractive setup already crowded, expensive, fragile, or dangerous?

These axes remain separate until the decision-composition layer.

---

# 2. Binding product thesis

> **Advanced Data should identify changes in derivatives pricing, institutional activity, and crowding that alter the probability distribution or risk/reward of a security before those changes are fully expressed in price.**

The lobe does not need to rediscover momentum. Mastermind already has mature price, technical, timing, event, and contextual systems.

Its edge is **orthogonal anticipation**.

Examples:

- Prophet timing is attractive and the lobe finds underpriced event movement plus qualified upside demand.
- Price is strong but options imply expensive crowding and poor new-entry asymmetry.
- A sector is rotating before the move is obvious in its index because multiple constituents show independent derivatives confirmation.
- A very large off-exchange print is unusual but directionally ambiguous; the system withholds the accumulation label.
- A squeeze setup is real but already extended; the lobe emits risk/continuation context without granting a late positive Prophet boost.
- A high-profile name has complete data but no unusual conditioned evidence; the correct output is `NO_SIGNAL`.

---

# 3. Non-negotiable acceptance laws

1. **Raw-data completeness is substrate, not product acceptance.**
2. **A reachable page is not proof of fresh data.**
3. **Fresh data is not proof of intelligence.**
4. **A score is not a signal unless its horizon, confidence, decay, evidence, and falsification conditions are explicit.**
5. **Observed facts and inferred claims must remain visibly distinct.**
6. **The system must be allowed to publish no signal.**
7. **No downstream score effect is allowed without a consumer receipt.**
8. **No live Prophet influence begins before shadow outcome evidence.**
9. **Prophet retains timing, extension, tradeability, and final rank authority.**
10. **Terminal retains intraday options-flow producer/classifier authority.**
11. **The Advanced Data lobe may consume Terminal summaries; it may not rebuild Terminal.**
12. **No second identity, event, transcript, queue, state, graph, sector-taxonomy, or publication plane.**
13. **Correction is part of the product, not an operator afterthought.**
14. **Green CI is never acceptance.**
15. **Every slice requires real input → real producer → real consumer → visible production output.**
16. **Every slice demonstrates a null case and a failure/degradation case.**
17. **No source is added merely to increase field count.**
18. **No model or page may imply direction the underlying observations cannot support.**

---

# 4. Current-state ruling

The starting assumption is:

> **The existing product is a substantial data-access and presentation asset, but not yet a production-proven institutional intelligence lobe.**

Prior sessions produced useful work, but it is fragmented across:

- EOD options ingestion and presentation;
- options-flow and options-screener builders;
- options signal episodes and H+60 outcome research;
- Market Memory options-context integration;
- a sparse-selector research/canary path;
- private receipt verification and replication work;
- options/GEX Prophet-fusion research;
- source freshness and gap diagnostics;
- raw and lightly interpreted user-facing options surfaces;
- historic handoffs such as PR `#5747`.

None of these may be called “the completed lobe” merely because the code exists.

## 4.1 Historical work that must be reconciled in AD-0

At minimum, AD-0 must inspect and adjudicate the current-main descendants or replacements of:

- PR `#5747` — options sparse selector handoff;
- PR `#5694` — bounded sparse selector canary;
- PR `#5696` — sealed runtime v2;
- PR `#5708` / `#5711` / related selector runtime governance;
- PR `#5790` / `#5801` — local receipt verifier / replica producer work;
- options signal episode and H+60 outcome machinery;
- options market-memory context and receipt machinery;
- options/GEX Prophet fusion family and its current status;
- `scripts/build_flow_leaders.py`;
- `scripts/build_options_screener.py`;
- options gap-discipline and estate tests;
- current EOD options and off-exchange page builders/templates/endpoints;
- current source collectors and current source clocks;
- current `config/synapse.yml` producer/consumer declarations;
- current Prophet consumer declarations;
- current Neural Web and Sector consumers;
- any Terminal-to-Macro options bridge.

This is a minimum archaeology list, not a claim that each item remains canonical.

## 4.2 Required maturity ledger

Every relevant component must be classified as exactly one:

- `PROVEN_LIVE`
- `BUILT_NOT_PROVEN`
- `PARTIAL`
- `DARK_OR_DISCONNECTED`
- `BROKEN`
- `SPEC_ONLY`
- `NOT_BUILT`
- `REJECTED_BY_DESIGN`

A component is not `PROVEN_LIVE` because:

- a test passes;
- a route exists;
- a page loads;
- a file is recent;
- an artifact was generated;
- a PR merged;
- a handoff says it is complete.

`PROVEN_LIVE` requires a current or bounded production proof connecting real source input to real consumer output.

---

# 5. Architecture doctrine

## 5.1 Reuse existing Mastermind planes

| Existing authority | Advanced Data must reuse | Forbidden rebuild |
|---|---|---|
| Identity | issuer, security, option contract, ETF, sector, event identities | local ticker/contract authority |
| Event | canonical envelope, versioning, event time, observation time | second event bus |
| Transcript / receipt | source hashes, calculation lineage, evidence chain, corrections | untraceable narrative store |
| Queue | delivery, idempotency, retries, dead-letter semantics | lobe-specific parallel queue |
| State | watermarks, last-good, stale, degraded, disarmed | local freshness authority |
| Publication | authenticated/private/public projection | direct page file as truth |
| Prophet | timing, entry readiness, extension, final candidate rank | unconditional lobe buy authority |
| Neural Web | cross-lobe context and graph | options-specific second graph |
| Sector Intelligence | taxonomy, membership, final sector rank | competing sector ontology |
| Terminal | intraday options-flow collection/classification | duplicate intraday pipeline |

## 5.2 Logical end-to-end topology

```text
EOD options
Off-exchange prints / aggregates
Underlying price / NBBO / liquidity
Corporate actions / event calendar
Terminal intraday flow summaries
Short / borrow / insider / ownership / estimates (later waves)
        │
        ▼
EXISTING IDENTITY + EVENT + QUEUE PLANES
        │
        ▼
PIT-normalized observations
        │
        ▼
Feature computation
        │
        ├─ options demand
        ├─ volatility / event pricing
        ├─ positioning scenarios
        ├─ off-exchange activity + price acceptance
        ├─ crowding / ownership / insider
        └─ market / sector context
        │
        ▼
Named intelligence primitives
        │
        ▼
Horizon-specific calibrated composer
        │
        ├─ direction
        ├─ asymmetry
        ├─ confidence
        ├─ freshness / decay
        ├─ actionability
        ├─ contradiction
        └─ null reason
        │
        ▼
Advanced Data signal in EXISTING event plane
        │
        ├─ Advanced Data board
        ├─ Prophet shadow/live bounded consumer
        ├─ Sector Intelligence projection
        ├─ Neural Web evidence edges
        └─ Watchlist / Portfolio alerts
        │
        ▼
EXISTING transcript + state + publication planes
        │
        ▼
Forward outcome labels + calibration + correction + disarm
```

---

# 6. Observation and signal laws

## 6.1 Point-in-time observation contract

Every observation family must preserve:

```text
observation_id
canonical_instrument_id
canonical_contract_id          optional
source_id
source_record_id
observation_type
market_effective_at
source_published_at
ingested_at
available_to_model_at
corrected_at                   optional
supersedes_observation_id      optional
source_session
source_watermark
raw_payload_hash
schema_version
calculation_version
entitlement_class
quality_state
quality_reasons[]
payload
```

`available_to_model_at` is load-bearing. It cannot be replaced by market-effective time.

## 6.2 Signal contract

Every signal must expose:

```text
signal_id
canonical_instrument_id
as_of_session
direction
horizon
state
probability_up
probability_down
probability_move_exceeds_implied
expected_edge_bps
expected_adverse_move_bps
asymmetry_score
confidence
freshness
actionability
extension_state
trigger
invalidation
fresh_until
evidence_family_contributions[]
contradictions[]
null_reason
suggested_consumer_action
receipt_id
model_version
supersedes_signal_id
```

### Direction enum

- `LONG`
- `SHORT`
- `VOLATILITY`
- `RISK_ONLY`
- `NEUTRAL`

### Lifecycle states

- `candidate`
- `confirmed`
- `decaying`
- `invalidated`
- `corrected`
- `retracted`
- `expired`

### Null states

- `NO_SIGNAL`
- `INSUFFICIENT_COVERAGE`
- `STALE_SOURCE`
- `AMBIGUOUS_DIRECTION`
- `EVENT_CONTAMINATED`
- `UNRESOLVED_CONTRACT`
- `UNSUPPORTED_INFERENCE`
- `NOT_TRADEABLE`
- `ALREADY_EXTENDED`
- `CORRECTED`
- `RETRACTED`
- `EXPIRED`

---

# 7. Required intelligence families

The engine should derive named primitives rather than a monolithic score.

## 7.1 Options demand

- persistent upside/downside demand;
- DTE- and moneyness-conditioned demand;
- cross-expiry confirmation;
- speculative-wing activity;
- probable roll/spread structure;
- event convexity demand;
- index/ETF hedge contamination;
- single-name demand independent of market hedging.

## 7.2 Volatility

- implied move underpriced;
- implied move overpriced;
- front/back term-structure dislocation;
- skew steepening/flattening;
- downside-tail demand;
- upside-convexity demand;
- volatility compression/expansion;
- disagreement between option-implied and realized/event-conditioned distributions.

## 7.3 Positioning mechanics

- strike concentration;
- expiry concentration;
- concentration migration;
- modeled gamma acceleration/suppression zone;
- possible pin/magnet level;
- modeled gamma flip range;
- vanna/charm sensitivity scenario;
- expiry instability.

These are **modeled scenarios**, not observed dealer inventory.

## 7.4 Off-exchange

- unusual off-exchange share;
- unusual block notional;
- repeated price-region cluster;
- bid/ask-side confidence where lawful;
- midpoint/ambiguous cluster;
- subsequent price acceptance;
- subsequent rejection;
- multi-session persistence;
- lit-market confirmation/contradiction.

## 7.5 Later Advanced Data families

- short crowding;
- borrow pressure;
- squeeze susceptibility;
- insider-buy conviction;
- clustered insider buying;
- institutional sponsorship;
- institutional crowding;
- estimate-revision breadth;
- expectations dispersion;
- ownership/derivatives disagreement.

---

# 8. Scoring and asymmetry doctrine

The final implementation may refine formulas, but it must preserve the conceptual separation below.

## 8.1 Conditioned feature surprise

A feature is evaluated against the right peer distribution:

```text
symbol liquidity tier
DTE
moneyness
event state
market regime
sector / market context
```

Raw volume, premium, or volume/OI never qualifies merely because the number is large.

## 8.2 Empirical evidence

Per feature and horizon, use empirically measured contribution when enough outcomes exist.

Heuristic mappings are permitted only in shadow and must be labeled heuristic.

> **AD-0 data-feasibility amendment (2026-08-17, Sol delta review on #5838/#5830):**
> deterministic heuristic ranking is explicitly authorized for AD-1 as **display-tier
> research-priority authority only** — it orders human research attention on the Advanced
> Data board. It is not probability, alpha, forecast, Prophet authority, gating, sizing,
> or trade authority, and its outputs may never be described as "validated". Predictive
> or probabilistic promotion of any Advanced Data scoring remains exclusively AD-6
> (forward-outcome calibration) and AD-7 (bounded Prophet activation) territory. Every
> frozen heuristic must additionally satisfy the **data-feasibility law** (AD-1 handoff
> §5.4): no specification may require more historical depth, coverage, or fields than the
> canonical producer store supplies at spec-freeze time, proven by a real-store census.
> `LONG`/`SHORT` at this tier are directional research hypotheses (§6.2 vocabulary is
> unchanged); no field lacking aggressor/open-close evidence may be described as observed
> buying or selling, and front-facing copy uses upside/downside-evidence phrasing rather
> than trade imperatives.

> **AD-1P0 semantic-authority amendment (2026-08-18, Sol ruling;
> `DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION`):** the
> display-tier layer must keep six evidence classes SEPARATE — salience/intensity,
> directional hypotheses, dealer mechanics, volatility, event premium, and crowding —
> under the authority ladder (observed fact → qualified inference → display-tier
> research-priority hypothesis → prospective outcome measurement → calibrated
> forecast/asymmetry → bounded Prophet authority). Binding consequences: salience
> (volume anomaly, persistence) has zero direction sign; GEX/dealer-mechanics context
> (including `gex_confirm_verdict`, a long-thesis verifier) never originates equity
> direction; open-interest change is an unsigned positioning hypothesis, never observed
> buying/selling; machine direction requires two distinct qualifying hypothesis legs
> (ΔOI lean + skew CHANGE) plus material salience; tick-rule flow is structurally barred
> from direction while its production gate reports direction unreliable; event-premium
> surfaces claim no historical mispricing before historical event conditioning exists;
> heuristic strength is never presented as calibrated economic asymmetry (asymmetry/
> probability/expected-edge fields stay null/UNCALIBRATED until AD-6); and Prophet
> remains a display-only echo with zero rank authority inside AD-1 (first score-level
> confluence is AD-5). Exact frozen formulas live in the AD-1 handoff §5.3 (v1.2).

## 8.3 Family caps

Correlated features do not become independent votes merely because they are stored in different fields.

Families include:

- options demand;
- volatility;
- positioning;
- off-exchange;
- event pricing;
- crowding;
- ownership/insider;
- sector/market context.

Each family receives a contribution cap.

## 8.4 Separate asymmetry and confidence

**Asymmetry** asks whether favorable expected movement meaningfully exceeds adverse movement and friction.

**Confidence** asks whether the system has enough trustworthy, fresh, independent, directionally valid evidence to believe the asymmetry estimate.

A large theoretical edge with weak evidence is not high confidence.

## 8.5 Actionability

A signal’s rank must be multiplicatively reduced by:

- illiquidity;
- stale evidence;
- Prophet extension;
- event-risk contamination;
- crowding;
- poor source coverage;
- unresolved identity or contract semantics.

## 8.6 Prophet delta

Advanced Data may propose:

- `confirm`
- `boost`
- `downgrade`
- `veto`
- `risk_only`
- `none`

But:

- Prophet timing runs first;
- Prophet extension runs first;
- tradeability runs first;
- already-launched names receive zero positive Advanced Data boost;
- initial live score authority is tightly capped;
- every delta has a consumer receipt;
- corrections retract the delta;
- source or calibration degradation disarms the delta without taking Prophet offline.

---

# 9. Dark-pool / off-exchange doctrine

The product must not market uncertainty as certainty.

## 9.1 Taxonomy

Internally distinguish:

1. known ATS;
2. other off-exchange / TRF;
3. provider-abstracted or unknown venue;
4. aggregate ATS/non-ATS statistics;
5. directionally classified prints;
6. directionally ambiguous prints.

## 9.2 Direction law

Large notional alone does not imply accumulation or distribution.

A directional claim requires enough qualifying evidence, potentially including:

- eligible trade condition;
- de-duplication;
- contemporaneous NBBO or price context;
- price position versus bid/ask/mid;
- size versus normal distribution and ADV;
- repeated clustering;
- subsequent price acceptance or rejection;
- lit-market confirmation.

If direction cannot be established:

> `UNUSUAL_OFF_EXCHANGE_ACTIVITY — DIRECTION_UNKNOWN`

is the correct signal.

---

# 10. 10/10 user experience

## 10.1 First viewport: “What Matters Now”

The first viewport should contain only decision-grade surfaces.

### A. Market derivatives regime

- implied versus realized;
- skew;
- term structure;
- tail demand;
- positioning scenario;
- off-exchange regime;
- freshness and coverage.

### B. Top anticipation opportunities

Each card must show:

- symbol;
- direction/type;
- horizon;
- asymmetry;
- confidence;
- actionability;
- why now;
- independent evidence families;
- trigger;
- invalidation;
- expected move/scenario range;
- freshness;
- Prophet state;
- what would make it wrong.

### C. Event-pricing board

Surface event candidates where implied movement and event-conditioned distributions diverge meaningfully.

### D. Sector leadership and crowding

Show:

- derivatives-confirmed breadth;
- ETF versus constituent confirmation;
- options demand breadth;
- volatility regime;
- off-exchange confirmation;
- concentration;
- crowding.

### E. Watchlist / Portfolio changes

Only material changes:

- new signal;
- confirmation;
- contradiction;
- invalidation;
- crowding deterioration;
- implied-move repricing;
- positioning-level proximity;
- correction;
- staleness.

## 10.2 Drill-down order

1. thesis;
2. evidence family contributions;
3. price and event context;
4. options surface;
5. positioning scenarios;
6. off-exchange clusters;
7. Prophet and Neural Web context;
8. outcome history and calibration;
9. source/calc receipt;
10. raw records.

Raw data becomes the audit layer, not the primary product.

---

# 11. Real-data reference compositions

Every mature version of the product must handle these correctly.

| Composition | Required output |
|---|---|
| Pre-event upside asymmetry | directional anticipation signal with underpricing, trigger, invalidation, bounded Prophet effect |
| Sector rotation emerging early | sector leadership signal with breadth and constituent evidence |
| Large call print that is probably a roll | `NO_SIGNAL` or `PROBABLE_ROLL`, never default bullish |
| Crowded squeeze but bad new entry | squeeze-risk context; positive Prophet delta zero |
| Index tail hedge | market risk; no blanket bearish constituent projection |
| Ambiguous off-exchange block | unusual activity, direction unknown |
| Positioning acceleration zone | scenario band, not claimed dealer inventory |
| Source degradation | visible degraded state and withheld signal |
| Correction after publication | superseded signal and retracted consumer effect |
| Complete data, no edge | explicit `NO_SIGNAL` |

These compositions must become behavioral reference cases, but production acceptance must always use real current or recent market data.

---

# 12. Failure, freshness, and correction doctrine

## 12.1 Required failures to handle explicitly

- adjusted/special-deliverable contracts;
- wide/crossed/invalid quotes;
- provider IV or Greek methodology breaks;
- OI not yet knowable;
- late/corrected records;
- duplicate reports;
- event contamination;
- index hedge contamination;
- opening/closing ambiguity;
- off-exchange midpoint ambiguity;
- corporate actions;
- stale chain;
- partial chain;
- venue unknown;
- unavailable direction;
- 0DTE evidence carried beyond its life;
- short-volume/short-interest confusion;
- multiple correlated features double counted;
- source outage;
- consumer delivery failure;
- correction delivery failure.

## 12.2 Freshness

Different evidence families have different useful lives.

Freshness must eventually be empirically learned by:

- family;
- horizon;
- event state;
- regime.

Until then, conservative half-life rules are allowed only if visible and versioned.

## 12.3 Corrections

Source corrections do not rewrite history.

They must:

1. create a superseding observation;
2. recompute affected features;
3. create a superseding signal;
4. retract prior consumer effects;
5. update user projection;
6. preserve both old and corrected evidence for audit;
7. update outcome attribution.

No live Prophet effect is authorized before this correction path is production-proven.

---

# 13. Program sequence

## AD-0 — Recovery Archaeology and Production Truth

**Outcome:** establish what actually exists, what is live, what is stale, what is salvageable, what is duplicate, and the exact bounded AD-1 build contract.

**Type:** research/design/docs-only.

**No runtime changes.**

**Stop:** return for Chairman review. Do not start AD-1.

---

## AD-1 — Daily EOD Options Intelligence Brief

**Outcome:** every completed market session produces a small, decision-grade options intelligence brief with market regime, ranked opportunities, event-pricing opportunities, risk/crowding warnings, and explicit no-signal/degraded states.

**Producer:** existing EOD source plus existing price, event, corporate-action, liquidity, and identity planes.

**Consumer:** Advanced Data board + machine-readable signal projection + Prophet shadow intake record only.

**Production proof requires:**

- deployed SHA;
- current source session/watermark;
- real ranked signal;
- real liquid `NO_SIGNAL`;
- source/feature/signal receipt;
- UI/API parity;
- visible freshness;
- source degradation case.

**Stop:** do not proceed if the board still requires raw-chain interpretation.

---

## AD-2 — Evidence Receipts, Nulls, Lifecycle, Corrections

**Outcome:** every signal is auditable and correctable.

**Consumer:** evidence drawer + machine consumers + ops/audit projection.

**Production proof:** production-safe correction/supersession demonstration from observation through visible projection and consumer retraction.

**Stop:** no later score authority without this.

---

## AD-3 — Off-Exchange Reality Board

**Outcome:** unusual off-exchange activity becomes ranked institutional-activity intelligence without invented direction.

**Production proof:**

- one real directional high-confidence cluster;
- one real ambiguous cluster that remains neutral;
- one excluded late/ineligible print;
- UI/API/receipt parity.

---

## AD-4 — Options × Off-Exchange Confluence

**Outcome:** distinguish corroboration, contradiction, options-only, off-exchange-only, and no-actionable-edge states.

**Production proof:** real corroboration, contradiction, and no-signal compositions with contribution receipts.

---

## AD-5 — Prophet Shadow Consumer

**Outcome:** every eligible Prophet candidate receives an Advanced Data evaluation and proposed bounded delta, while actual Prophet rankings remain unchanged.

**Production proof:**

- real Prophet candidate;
- signal ID;
- consumer receipt;
- before score;
- proposed delta;
- timing/extension gate result;
- proposed after score;
- actual applied delta = 0.

---

## AD-6 — Forward Outcome and Calibration Ledger

**Outcome:** determine whether the lobe produces real information.

Track:

- directional outcome;
- MFE;
- MAE;
- realized versus implied movement;
- trigger occurrence;
- invalidation;
- Prophet baseline;
- market/sector regime.

Report:

- coverage;
- precision@K;
- Brier;
- calibration;
- IC;
- expected utility;
- MFE/MAE;
- incremental lift over Prophet;
- ablation;
- confidence intervals;
- correction rate;
- no-signal rate.

**Stop:** insufficient sample is not a pass.

---

## AD-7 — Bounded Prophet Activation

**Outcome:** calibrated Advanced Data signals begin changing live Prophet scoring in a tightly governed, reversible manner.

**Initial authority:** small cap, approximately ±5.

**Positive delta = 0 when:**

- already extended;
- not tradeable;
- stale;
- ambiguous;
- event contaminated;
- redundant;
- unsupported.

**Production proof:**

- live applied delta;
- before/after receipt;
- visible explanation;
- rollback drill;
- source-degradation disarm drill.

---

## AD-8 — Sector Intelligence + Neural Web Consumers

**Outcome:** derivatives-confirmed sector leadership, breadth, crowding, ETF-versus-constituent disagreement, and graph evidence.

**Stop:** no schema-only “integration.”

---

## AD-9 — Terminal Intraday Bridge

**Outcome:** EOD intelligence can state whether canonical Terminal intraday flow confirmed, contradicted, preceded, or added no information.

**Forbidden:** rebuilding Terminal producer/classifier/queue/state.

---

## AD-10 — Watchlist + Portfolio Intelligence

**Outcome:** users receive only material changes affecting followed/owned names.

No full-board spam.

---

## AD-11 — Short + Borrow Intelligence

**Outcome:** distinguish outstanding short positioning, borrow pressure, and squeeze susceptibility.

**Law:** daily short-sale volume is never substituted for short interest.

---

## AD-12 — Insider-Buy Intelligence

**Outcome:** high-conviction insider buying, not a Form 4 dump.

Must distinguish open-market buys from grants, exercises, gifts, conversions, amendments, and indirect changes.

---

## AD-13 — Institutional Ownership and Sponsorship

**Outcome:** slow-moving sponsorship/crowding context with correct filing-age semantics.

**Law:** no entry-timing boost solely from delayed ownership.

---

## AD-14 — Expectations Gap Intelligence

**Outcome:** combine point-in-time estimate revisions/dispersion with options event-pricing to identify mispriced expectations.

**Precondition:** licensed PIT-correct estimate history.

---

## AD-15 — Conditional Data-Quality / Vendor Upgrade

Only authorized if earlier production evidence identifies a named information gap the current source cannot close.

No purchase for completeness theater.

---

# 14. Production acceptance packet

Every implementation slice must return:

```text
audit_head
main_at_start
merged_sha
deployed_sha
production_url_or_projection
source_session
source_watermarks
source_entitlements
real_input_ids
raw_input_hashes
feature_set_ids
signal_ids
consumer_receipt_ids
visible_output_capture
freshness_state
null_case
correction_or_failure_case
test_commands_and_results
rollback_or_disarm_procedure
known_limits
next_slice_scope
```

A slice is **not accepted** when:

- only CI is green;
- only fixtures pass;
- only a schema exists;
- only a producer exists;
- the consumer is mocked;
- the page is not deployed;
- the data is stale;
- proof uses only a cherry-picked symbol;
- no null case is shown;
- no failure/degradation case is shown;
- repo and production SHAs cannot be reconciled.

---

# 15. Operator continuation handoff contract

Every operator must stop after its assigned slice and return:

1. outcome proven;
2. `main_at_start`;
3. merge SHA;
4. deployed SHA;
5. paths changed;
6. canonical contracts reused;
7. real production inputs;
8. real production outputs;
9. source watermarks;
10. signal IDs;
11. consumer receipt IDs;
12. null case;
13. failure/degradation case;
14. correction behavior;
15. rollback/disarm;
16. unresolved risks;
17. no-rebuild zones;
18. exact next slice only.

The next slice does not begin until the prior slice is reviewed.

---

# 16. Adversarial anti-theater rules

## 16.1 Pretty-page theater

A card that merely restates volume, premium, OI, or IV is not intelligence.

Every ranked card must have:

- conditioned anomaly;
- horizon;
- evidence;
- trigger;
- invalidation;
- freshness;
- independent family contribution;
- what would make it wrong.

## 16.2 False precision

Observed and inferred values remain separate.

Dealer positioning uses scenario assumptions and ranges.

Low-sample probabilities shrink to base rates or remain shadow.

## 16.3 PIT leakage

All observations require a lawful availability clock.

Historical observations are append-only.

Any discovered timing leak invalidates affected research until replayed.

## 16.4 Dark-pool marketing

Off-exchange activity is not automatically accumulation/distribution.

Ambiguity is a first-class output.

## 16.5 Double counting

Multiple options fields do not become independent votes.

Family caps, ablation, and incremental-information checks are mandatory.

## 16.6 Late-entry failure

Positive Advanced Data delta can never bypass Prophet extension or tradeability.

## 16.7 Permanent-shadow failure

Shadow mode must have:

- visible comparison;
- consumer receipts;
- forward outcome ledger;
- pre-registered promotion/rejection decision.

Shadow artifacts without evaluation are discarded.

## 16.8 Advanced-data sprawl

Do not begin short, borrow, insider, ownership, or estimates while core EOD + off-exchange + Prophet shadow remains unproven.

## 16.9 Duplicate systems

No “temporary” second plane is allowed merely to move faster.

## 16.10 Activity quota

The board is allowed to be empty.

There is no minimum number of daily signals.

---

# 17. Immediate execution ruling

The only authorized next wave is `AD-0`.

`AD-0` must:

1. audit current `main`;
2. audit current production;
3. reconcile all meaningful prior options/off-exchange work;
4. prove current source freshness and source coverage;
5. map producer → normalization → artifact → consumer → publication → health;
6. classify every piece using the required maturity ledger;
7. identify salvage, replacement, retirement, and no-rebuild zones;
8. identify the canonical existing Mastermind planes AD-1 must extend;
9. freeze the exact AD-1 data contract, user composition, and production proof;
10. write the AD-1 implementation handoff;
11. stop.

No runtime, page, model, source, workflow, queue, scheduler, state, Prophet, Neural Web, Sector, Terminal, or publication implementation changes are authorized in AD-0.

---

# 18. Final north star

This program is complete only when:

> **Mastermind sees derivatives repricing, institutional activity, volatility dislocations, positioning mechanics, and crowding early; converts them into calibrated and explainable anticipation signals; withholds unsupported claims; improves Prophet without causing late entries; survives corrections and source degradation; and lets a user understand the opportunity and its failure conditions in under one minute.**
