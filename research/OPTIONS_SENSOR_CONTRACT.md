# Options Sensor Contract — Package A

**Author:** Build agent (Sonnet), 2026-07-07
**Program:** MomoEdge-parity Options Terminal + Oracle (MASTER_BUILD_DOCKET.md)
**Status:** DISPLAY-ONLY — no schema has passed a forward ledger gate.

---

## 0. Purpose and scope

This document is the canonical specification for the six options-sensor schemas
introduced in Package A.  Every later build stage (Flow, Heatmap, GEX, PRISM,
Oracle) MUST read from these schemas, not invent its own.  Each schema carries
`authority_tier` and `reliability` metadata; the word "validated" is forbidden in
user-facing text (CI-enforced by `scripts/check_validated_claims.py`).

### Authority tier ladder

| Tier | Meaning |
|---|---|
| `display` | Rendered, salience-eligible; no arithmetic on scored surfaces. |
| `shadow` | Computed + claim-registered + graded nightly; never rendered as conviction. |
| `confirmer` | Passed §3 gate (n_dates ≥ 25, Wilson CI > 0 vs matched control). |
| `scored` | Composite re-validation + 63d OOS accrual passed. |

All six schemas in Package A ship at `display` or `shadow` (structural only).
Escalation requires a pre-registered forward ledger and explicit adjudication.

### Reliability-flag conventions

| Flag value | Meaning |
|---|---|
| `"reliable"` | Signing-free (premium magnitude, OI counts, volume). |
| `"soft"` | Tick-rule signed (net recovery ~0.41); magnitude reliable, direction not. |
| `"assumption-signed"` | GEX/gamma fields: assumes dealers are long calls / short puts (unobservable). |
| `"display-only-until-gate"` | Not yet gated by a forward ledger. |

**Direction without NBBO is always soft.**  `ask_share`-derived lean ≠ confirmed trade side.
The NBBO-signed trade tape is entitled via ThetaData but not yet wired into these engines
(poller wiring is a follow-up PR in the concurrent deploy lane).

### Versioning rules

- Schema strings follow `<namespace>.<name>/vN` (e.g. `options_flow.chain_heat/v1`).
- A version bump is required when a field is removed, its type changes, or its semantics
  change in a way that is not backward-compatible.
- Adding optional fields is non-breaking (no version bump needed).
- Producers MUST stamp `schema` on every output artifact.
- Consumers MUST reject (log + skip) artifacts with unknown or mismatched schema strings.

---

## 1. Schema: `options_structure.gex_state/v1`

**Artifact path (R2):** `options_structure/gex_state/<ROOT>.json`
**Artifact path (site):** `site/options_structure/gex_state/<ROOT>.json` (future)
**Producer:** `engine/options_structure.py` (Package C builder, not yet wired)
**Cadence:** daily-engine (nightly)
**Authority tier:** `display`
**Consumers:** Terminal GEX tab, Neural Web context sensors (future)

Carries the per-symbol dealer gamma structure state for the GEX tab
(Package 3 of the build sequence).  All level and regime fields are DISPLAY-ONLY
until the GEX→forward-vol validation gate passes (~Sept 2026).  Single-name regime
(`structurally_constant: true`) is a near-constant product attribute, NOT a
time-varying signal.  `regime_passport` must be preserved in all consumers.

### Field table

| Field | Type | Units | Semantics |
|---|---|---|---|
| `schema` | string | — | Must be `"options_structure.gex_state/v1"` |
| `asof` | string | ISO-8601 with tz | Timestamp of computation |
| `root` | string | — | Underlying root symbol (e.g. `"SPY"`) |
| `spot` | float\|null | USD | Spot price at computation time |
| `net_gex_bn` | float\|null | $B | Net dealer GEX (assumption-signed) |
| `gamma_regime` | string | — | 6-state: `PIN\|DRIFT\|RANGE\|TRANSITION\|TREND\|CASCADE` |
| `stability_pct` | float\|null | % | posGex / (posGex + \|negGex\|) × 100 within ±20% of spot |
| `gamma_flip` | float\|null | USD | Price at which net GEX crosses zero |
| `dist_to_flip_pct` | float\|null | % | (spot − gamma_flip) / spot × 100 |
| `call_wall` | float\|null | USD | Strike with highest call OI·γ |
| `put_wall` | float\|null | USD | Strike with highest put OI·γ |
| `magnet` | float\|null | USD | Strike with strongest gravitational pull |
| `max_pain` | float\|null | USD | Price that maximises net option-writer profit |
| `pin_probability` | float\|null | 0–1 | Probability of pinning at expiry (descriptive heuristic) |
| `gravity_direction` | string\|null | — | `"up"` or `"down"` |
| `gravity_up_pct` | float\|null | % | Upward gravity strength |
| `cascade_trigger` | float\|null | USD | Price below which cascade acceleration may occur |
| `upside_trigger` | float\|null | USD | Price above which upside acceleration may occur |
| `oi_delta_clusters` | dict | — | `{new_oi: [...], exit_oi: [...]}` — new/exit OI strike clusters |
| `regime_passport` | dict | — | `{basis, structurally_constant, is_index_product, verdict, note}` |
| `authority_tier` | string | — | Always `"display"` in Package A |
| `reliability` | dict | — | `{levels, regime, note}` |

---

## 2. Schema: `options_flow.chain_heat/v1`

**Artifact path (R2):** `live_flow/chain_heat_current.json`
**Producer:** `aggregate_chain_heat()` in `engine/options_structure.py`
**Cadence:** intraday (120s cadence, market hours — matching live poller)
**Authority tier:** `display`
**Consumers:** Terminal Flow tab Chain Heat rail, Neural Web context sensors (future)

Surfaces contract-day accumulation campaigns — cases where institutional flow
splits a large position across many small alerts that individually fall below
scoring thresholds.  Per the worked example in `chain_heat_spec.md §1`:
_"SMH 6/18 530P, $11.97M over 29 alerts in 91 min at 91% ask."_

`lean` is derived from `ask_share` (tick-rule signed), NOT from asserted BOUGHT/SOLD:
- `ask_share ≥ 0.65` → `"accumulation"`
- `ask_share ≤ 0.35` → `"distribution"`
- otherwise → `"contested"`

`direction_reliability` is hardcoded `"soft"` and may not be elevated in this
artifact until an NBBO-signed source passes a forward ledger gate.

### Feed envelope fields

| Field | Type | Units | Semantics |
|---|---|---|---|
| `schema` | string | — | `"options_flow.chain_heat/v1"` |
| `asof` | string | ISO-8601 UTC | Timestamp of last aggregation |
| `session_date` | string | YYYY-MM-DD | Trading session date |
| `campaigns` | list[dict] | — | Array of campaign objects (see below) |
| `authority_tier` | string | — | `"display"` |
| `reliability` | dict | — | `{lean, premium_magnitude, direction, note}` |

### Campaign object fields

| Field | Type | Units | Semantics |
|---|---|---|---|
| `option_symbol` | string | — | OCC-style padded symbol |
| `ticker` | string | — | Underlying root symbol |
| `right` | string | — | `"CALL"` or `"PUT"` |
| `strike` | float | USD | Strike price |
| `expiry` | string | YYYY-MM-DD | Option expiration |
| `dte` | int\|null | days | Days to expiry at computation time |
| `total_premium_mn` | float | $M | Total campaign premium in millions |
| `alert_count` | int | count | Number of component flow alerts |
| `span_minutes` | float | min | Campaign duration (last_seen − first_seen) |
| `first_seen` | string | ISO-8601 UTC | Timestamp of first component alert |
| `last_seen` | string | ISO-8601 UTC | Timestamp of most recent alert |
| `ask_share` | float\|null | 0–1 | Premium-weighted fraction filled at ask; None if unavailable |
| `lean` | string | — | `"accumulation"\|"distribution"\|"contested"` |
| `direction_reliability` | string | — | Always `"soft"` (tick-rule; no NBBO) |
| `authority_tier` | string | — | `"display"` |

---

## 3. Schema: `options_structure.matrix/v1`

**Artifact path (R2):** `options_structure/matrix/<ROOT>.json`
**Producer:** matrix builder (Package E, PRISM — future)
**Cadence:** daily-engine
**Authority tier:** `display`
**Consumers:** Terminal PRISM tab

Strike × expiration matrix for one underlying, used by the PRISM tab.  Per the
docket and MomoEdge's own copy: _"Sign is an assumption, not a fact. Magnitude
is the reliable read."_  The `heat_seeker.note` field is CI-enforced as
`"descriptive — not a recommendation"`.

### Envelope fields

| Field | Type | Units | Semantics |
|---|---|---|---|
| `schema` | string | — | `"options_structure.matrix/v1"` |
| `asof` | string | ISO-8601 | Computation timestamp |
| `root` | string | — | Underlying root |
| `spot` | float\|null | USD | Spot price |
| `expiries` | list[string] | YYYY-MM-DD | Expiry dates in the matrix |
| `strikes` | list[float] | USD | Strike prices in the matrix |
| `cells` | list[dict] | — | One dict per (strike, expiry) cell |
| `levels` | dict | — | `{call_wall, put_support, hvl, gamma_flip, max_pain}` |
| `heat_seeker` | dict\|null | — | Descriptive standout cell (see below) |
| `authority_tier` | string | — | `"display"` |
| `reliability` | dict | — | `{gex, delta_oi, vol, note}` |

### Cell fields

| Field | Type | Units | Semantics |
|---|---|---|---|
| `strike` | float | USD | Strike price |
| `expiry` | string | YYYY-MM-DD | Expiry date |
| `gex` | float\|null | $ | Net $γ/1% in this cell (assumption-signed) |
| `call_oi` | int\|null | contracts | Call open interest |
| `put_oi` | int\|null | contracts | Put open interest |
| `call_vol` | int\|null | contracts | Call volume today |
| `put_vol` | int\|null | contracts | Put volume today |
| `delta_oi` | dict | — | `{call: int\|null, put: int\|null}` day-over-day OI change (RELIABLE) |
| `unusual` | dict\|null | — | `{ratio, samples, side}` or null if no 30d history |

### Heat Seeker fields

| Field | Type | Units | Semantics |
|---|---|---|---|
| `strike` | float\|null | USD | Standout strike |
| `expiry` | string\|null | YYYY-MM-DD | Standout expiry |
| `lens` | string | — | `"GEX"\|"OI"\|"VOL"\|"DELTA_OI"\|"UNUSUAL"` |
| `standout_ratio` | float\|null | — | Relative standout vs median cell in matrix |
| `confidence` | float\|null | 0–1 | `(ratio − 1) / 3`; uncalibrated heuristic |
| `note` | string | — | **Must be** `"descriptive — not a recommendation"` |

---

## 4. Schema: `options_structure.structural/v1`

**Artifact path (R2):** `options_structure/structural/<ROOT>.json`
**Producer:** structural detector (Package D — future)
**Cadence:** daily-engine
**Authority tier:** `shadow` (context-only until gauntlet)
**Consumers:** Neural Web context sensors (gated)

Structural detector state: squeeze and cascade states, flow proximity to key
levels, and a plain-language explanation.  Ships at `shadow` tier because it
feeds the Neural Web as a GATED CONTEXT SENSOR only.  LLMs may narrate; may not
originate signals or escalations.  Escalation requires a pre-registered forward
ledger gate and explicit adjudication.

| Field | Type | Units | Semantics |
|---|---|---|---|
| `schema` | string | — | `"options_structure.structural/v1"` |
| `asof` | string | ISO-8601 | Computation timestamp |
| `root` | string | — | Underlying root |
| `squeeze_state` | string | — | `"NONE"\|"BUILDING"\|"ACTIVE"` |
| `cascade_state` | string | — | `"NONE"\|"BUILDING"\|"ACTIVE"` |
| `top_relevance_score` | float\|null | 0–100 | Descriptive relevance index (not a signal score) |
| `contributing_flows` | int | count | Number of distinct flow events contributing |
| `flow_near_flip` | bool | — | True if notable flow detected within ±2% of gamma flip |
| `flow_near_wall` | bool | — | True if notable flow detected within ±1% of a wall |
| `dealer_regime` | string | — | Copied from `gex_state.gamma_regime` |
| `explanation` | string | — | Plain-language description ("validated" forbidden) |
| `vol_ladder_suppressed` | bool | — | True if IV term structure is inverted / suppressed |
| `authority_tier` | string | — | Always `"shadow"` |
| `allowed_authority` | string | — | `"context-only-until-gauntlet"` |
| `reliability` | dict | — | `{structural_state, note}` |

---

## 5. Schema: `oracle.trade_plan/v1`

**Artifact path:** `oracle/trade_plan/<ID>.json` (site or R2)
**Producer:** Neural Web (NW originates; Oracle does not re-originate)
**Cadence:** on-demand (when NW emits a candidate)
**Authority tier:** `display`
**Consumers:** Oracle management engine, Oracle desk UI

The STATIC plan envelope.  The Neural Web is the **sole originator** of trade
candidates; the Oracle **manages** active trades; LLMs **narrate**.  This
separation is non-negotiable (house law).  Live management state lives in a
separate artifact at `oracle/state/<ID>.json` (schema `oracle.management_state/v1`).

| Field | Type | Units | Semantics |
|---|---|---|---|
| `schema` | string | — | `"oracle.trade_plan/v1"` |
| `id` | string | — | Stable UUID or composite key (asset-direction-date-seq) |
| `asof` | string | ISO-8601 | Plan creation timestamp |
| `asset` | string | — | Underlying (ticker or index symbol) |
| `direction` | string | — | `"BULL"\|"BEAR"` |
| `thesis` | string | — | Plain-language thesis ("validated" forbidden) |
| `source_engines` | list[string] | — | Must be non-empty; must include `"neural_web"` or equivalent |
| `trigger` | float\|null | USD | Price level that activates the trade |
| `entry` | float\|null | USD | Target entry price |
| `invalidation` | float\|null | USD | Price that invalidates the thesis |
| `targets` | list[float] | USD | Ordered profit targets [T1, T2, …] |
| `horizon_days` | int\|null | days | Maximum hold duration |
| `min_hold_days` | int\|null | days | Minimum hold before exiting |
| `tranche` | int | — | 1 (initial) or 2 (scale-in on trigger) |
| `option_contract` | dict\|null | — | `{type, strike, expiry, entry_premium}` |
| `management_ref` | string | — | Path to `oracle.management_state/v1` artifact |
| `authority_tier` | string | — | `"display"` |
| `reliability` | dict | — | `{plan, option_premium}` |

---

## 6. Schema: `oracle.management_state/v1`

**Artifact path:** `oracle/state/<ID>.json` (site or R2)
**Producer:** `engine/oracle_management.py` (Package 6 — future)
**Cadence:** intraday or daily-engine
**Authority tier:** `display`
**Consumers:** Oracle desk UI, forward outcome ledger

The LIVE management confidence state.  This is a **TRADE-MANAGEMENT score**, NOT
a pick-rank score.  The Neural Web produces pick candidates; the Oracle manages
active trades.  These two surfaces must stay separated (docket §4).

**Confidence ceiling: 92.**  `management_confidence` must never exceed 92.
Uncertainty is honest; certainty is forbidden.

**7-phase lifecycle:**
`pre_trigger → triggered_pre_t1 → at_t1 → between_t1_t2 → at_t2 → overtime → invalidated`

| Field | Type | Units | Semantics |
|---|---|---|---|
| `schema` | string | — | `"oracle.management_state/v1"` |
| `id` | string | — | Matches `oracle.trade_plan/v1.id` |
| `asof` | string | ISO-8601 | State computation timestamp |
| `phase` | string | — | Current lifecycle phase (7 valid values) |
| `management_confidence` | float\|null | 0–92 | EMA-smoothed confidence; ceiling = 92 |
| `raw_confidence` | float\|null | 0–92 | Pre-EMA confidence score |
| `delta_vs_base` | float\|null | — | Change vs plan-initiation baseline |
| `recommended_action` | string | — | `"wait"\|"enter"\|"hold"\|"trim"\|"trail"\|"exit"\|"invalidated"` |
| `components` | dict | — | `{validity, progress, pace, retention, overlay}` each 0–100 |
| `geometry` | dict | — | `{dist_to_stop_r, dist_to_t1_r, horizon_pct_used}` |
| `change_reason` | string | — | Plain-language reason for the latest change |
| `confidence_ceiling` | int | — | Always 92 |
| `authority` | string | — | `"trade-management-only-NOT-pick-rank"` |
| `authority_tier` | string | — | `"display"` until forward ledger gate passes |
| `reliability` | dict | — | `{management_confidence, recommended_action, ceiling}` |

---

## 7. Implementation notes for downstream readers

### 7.1 `right` field name vs docket §2.3 `type` field

Docket §2.3 draft used `type` (`'PUT'`/`'CALL'`) as the campaign object field name.
The implementation (`engine/options_structure.py`, `ChainHeatCampaign`, and all
`synapse.yml` consumer rows) uses `right` instead.  This is intentional — `right` is
the canonical options-market term and avoids collision with Python's reserved keyword
pattern.  All four downstream readers (Terminal flow-tab, Neural Web context sensors,
oracle management engine, and oracle desk UI) MUST consume `right`, not `type`.

### 7.2 `aggregate_chain_heat()` session_date parameter

`aggregate_chain_heat()` accepts an explicit `session_date: str | None` argument
(format `YYYY-MM-DD`) to compute `dte` (days to expiry) deterministically.  When
`session_date` is `None`, `dte` is `None` in all output campaigns.  The writer
(poller) is responsible for passing the correct trading session date before
persisting.  The function MUST NOT read the wall clock (`datetime.now()`); doing
so would make the same event list yield different `dte` values on different
calendar days (PIT-unsafe, non-deterministic).

### 7.3 Synapse.yml self-consumer entries

Several `options-structure-*` synapse rows list `engine/options_structure.py` as
both producer AND consumer.  These entries reflect a contract-before-builder pattern:
the module defines the dataclasses and validators (schema layer) that future builder
scripts in the same file (or calling it) will consume.  They are not circular data
dependencies.  Similarly, `oracle-trade-plan` lists `producer: engine/neuralweb/world_state.py`
which does not yet write to `oracle/trade_plan/` (the builder is Package 6, future
scope).  DAG-conformance CI is green because it does not check that the producer path
performs actual writes.  Both patterns are accepted contract-before-builder entries
and do not require action before Package 6 is wired.

---

## 8. Synapse.yml registration

All six schemas are registered in `config/synapse.yml` under `owner_program: momoedge`.
See that file for producer, cadence, storage, freshness SLA, and consumer lists.

---

## 9. Build status (Package A)

| Deliverable | Status |
|---|---|
| `research/OPTIONS_SENSOR_CONTRACT.md` | DONE — this file |
| `engine/options_structure.py` (dataclasses + validators + `aggregate_chain_heat`) | DONE |
| `tests/test_options_structure.py` (55 tests, all passing) | DONE |
| `config/synapse.yml` entries (6 artifacts) | DONE |
| `site/options_structure/examples/*.json` (6 examples) | DONE |
| Poller wiring (`live_flow_poller.py` → `aggregate_chain_heat`) | DEFERRED — concurrent deploy lane owns live_flow tonight |

---

*End of Package A contract doc.  Next: Package 1 — FLOW tab (Sonnet build, Opus review of score design).*
