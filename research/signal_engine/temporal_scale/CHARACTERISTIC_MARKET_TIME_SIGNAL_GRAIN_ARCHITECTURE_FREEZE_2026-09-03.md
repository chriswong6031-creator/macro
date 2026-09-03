# Characteristic Market Time × Signal Grain — W0 Architecture Freeze

**Date:** 2026-09-03
**Workstream:** `WS:TEMPORAL-GRAIN-INTELLIGENCE`
**Parent program:** `market-timing-intelligence`
**Chairman intent:** continue the approved Pro-mode investigation at full throttle
**W0 operation:** `temporal-grain-w0-freeze-20260903-sol-001`
**First empirical child:** `temporal-grain-gakd-artifact-attack-r1-20260903-sol-001`
**Protected procedure pin:** `mastermindx-market-intelligence/Mastermind@793e75639911f21dae9c90a77c3a5dbf4b37cbb0`
**Macro base:** `mastermindx-market-intelligence/macro@931870b1feccb91b5122d92b07995e9749566aae`
**Capability at W0:** `SPEC_ONLY`
**Authority at birth:** research only; rank/gate/size/trade/Prophet/Golden-Oracle authority all false

---

## 1. Outcome and scientific question

The user job is not to memorize that one ticker “likes” one candle interval. The user needs
Mastermind to distinguish a genuinely useful temporal listening scale from a chart artifact before
trusting an entry or transition read.

The machine job is to determine whether an instrument’s path, session, liquidity and information
structure can select or constrain a useful signal grain or filter-memory band **before signal
outcomes are read**, and to abstain when no stable scale exists.

The frozen scientific question is:

> Do traded instruments possess measurable characteristic time scales that determine which signal
> grain/filter horizon is useful, and can those scales be derived ex ante from market/path/session
> structure rather than selected from historical signal outcomes?

The motivating observations are WMT around 12H with extended-hours data and an unresolved “silver”
instrument around 8H. They are discovery examples only. Neither may serve as untouched confirmation.

The 10/10 end-state is a correction-safe, identity-safe and evidence-disciplined capability that can
say one of the following before outcome exposure:

- a stable market-scale band exists and this signal kernel is structurally compatible;
- session semantics, not nominal duration, explain the useful construction;
- information/activity time is the relevant clock;
- the apparent edge follows kernel memory rather than bar grain;
- the instrument is multiscale or unstable and Mastermind must abstain;
- the original observation is a data, phase, warm-up or implementation artifact.

## 2. Current one-sentence ruling

`MIXED — SESSION_GRAMMAR + FILTER_MEMORY, with UNRESOLVED_DATA on exact motivating-chart
reproduction.`

That is a research prior and architecture decision, not a validated signal result. It authorizes the
bounded reproduction-and-artifact-attack child only.

## 3. Binding prior evidence and permanent exclusions

`DNR:KILL-OUTCOME-AUDITION` is binding. Per-name in-sample selection of a historically winning
indicator/rung had effectively zero out-of-sample persistence in PTT W1a. The lawful surviving
method was structure measurement: measure the path first, mechanically derive the configuration,
then use outcomes only to validate the frozen relationship.

The governing law is:

> **MEASURE THE STOCK, DON'T AUDITION THE WARDROBE.**

This workstream therefore forbids:

1. `ticker -> historically best timeframe` lookup tables;
2. per-name argmax over grain, anchor, kernel or data-plane outcomes;
3. a “temporal fingerprint” that is really an outcome-selected label;
4. changing the frozen Stock Identity v0 representation;
5. treating WMT or the motivating silver chart as independent confirmation;
6. changing Golden Oracle’s 3D definition or `engine/signal_quality.py`;
7. granting Prophet, rank, gate, size, trade or `can_open_entry` authority;
8. creating a second event store, evaluator, trial ledger, data plane, identity plane, lifecycle,
   signal registry or chart renderer;
9. collapsing localization, risk utility and trade economics into one post-hoc score;
10. silently substituting another symbol/vendor/session when exact reproduction fails.

## 4. Current-state and disagreement ledger

### 4.1 Canonical current state

- Protected procedure is Skillpack v1.0.1 at the exact Mastermind pin above.
- Macro base is the exact main SHA above.
- No GitHub issue, pull request, branch, Agent OS record or Slack message was found for this exact
  temporal-grain operation before W0 branch creation.
- The earlier chat-only proposed key `temporal-grain-gakd-artifact-attack-r1-20260902-sol-001`
  never acquired a branch, issue, PR, Slack carrier, pickup, START or effect. It is superseded
  before materialization by the current-date key ending `20260903-sol-001`; this is not a retry.
- `engine/entry_radar/four_hour.py` already proves the house principle that an intraday bar is a
  session object with an actual open, effective end, clipped duration and confirmation state.
- `engine/entry_radar/indicator_core.py` already owns the canonical Radar RSI-MACD/StochRSI
  implementation through `engine.canon`.
- `engine/stock_identity/fingerprint.py` already owns daily structural measurements such as
  mean-reversion half-life, autocorrelation, variance ratio, trend persistence, volatility
  persistence and swing-period statistics.
- `engine/trial_ledger.py` already owns look-budget registration and multiple-testing memory.
- The current Macro intraday stock aggregate path is a component, not proof of TradingView parity or
  of a cross-asset silver substrate.

### 4.2 Reconciled disagreement

`WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE` currently says W0 / PR #6570 is `awaiting_ci`, but GitHub
records PR #6570 merged on 2026-08-30 as
`6e3126c5106d5d240961088a866bf0e45f940538`.

Canonical owner for merge truth: GitHub.
Stale layer: Agent OS workstream projection.
Repair in this W0 carrier: mark TOI W0 done and leave W1/W2-0 honestly todo and undispatched.

This temporal study is a **sibling**, not a replacement for TOI W2-0:

- TOI W2-0 owns broad U.S.-equity Weekly/Daily/4H data, clock, coverage, rights and Terminal-parity
  archaeology for Compression Release.
- Temporal Grain owns exact motivating-chart reproduction, G/A/K/D causal separation,
  filter-memory matching and the later structure-to-kernel relationship.
- A result from one may be consumed by the other only through explicit contracts; neither absorbs
  the other’s workstream or creates a duplicate store.

## 5. Primary-source facts frozen for Gate 1

The empirical child must recheck these sources when it starts; these are W0 design inputs, not
cached authority.

1. TradingView’s current Time documentation states that time-based intraday chart bars align to
   session open/close and the final bar is shortened when the timeframe does not divide the
   session.
   - <https://www.tradingview.com/pine-script-docs/concepts/time/>
2. TradingView’s current Sessions documentation states that `syminfo.session` reflects the active
   named session, that U.S. equities commonly distinguish `regular` and `extended`, and that many
   futures use the long electronic session as named `regular` while a shorter session may be
   `us_regular`.
   - <https://www.tradingview.com/pine-script-docs/concepts/sessions/>
3. TradingView’s current export documentation states that chart CSV exports include OHLC and
   numeric plots from active scripts; hidden/Data-Window plots can be included.
   - <https://www.tradingview.com/support/solutions/43000537255-how-to-export-chart-data/>
   - <https://www.tradingview.com/pine-script-docs/faq/indicators/>
4. Massive’s current stock aggregate documentation states that stock custom bars are constructed
   from qualifying trades, can cover premarket/RTH/after-hours, omit intervals with no qualifying
   trades and default to split-adjusted output unless `adjusted=false`.
   - <https://www.massive.com/docs/rest/stocks/aggregates/custom-bars>
5. CME’s current benchmark Silver futures product information identifies `SI` as the 5,000-troy-
   ounce COMEX contract and gives its electronic trading hours and daily maintenance break.
   Product identity and hours must be re-pinned because CME also introduced a distinct 100-ounce
   Silver product in 2026.
   - <https://www.cmegroup.com/markets/metals/precious/silver.html>
   - <https://www.cmegroup.com/trading-hours.html>

These facts make exact instrument identity non-optional. “Silver” can mean XAGUSD, a CFD, `SI`, a
continuous contract with a vendor-specific roll, `SLV`, or another product. They may not be pooled.

## 6. G/A/K/D identification model

Every candidate observation is represented by four independently versioned variables:

### G — bar grain

Nominal interval and actual bar duration. Examples: 4H, 8H, 12H, 1D. A shortened session-final bar
must disclose its actual duration rather than inheriting the nominal label as if equal.

### A — anchor/session construction

Exchange session, active named subsession, timezone, trading-day boundary, phase, maintenance
break, holiday/early close, DST, no-trade interval, clipping, provisional/final status and
`known_at`.

### K — indicator kernel/effective memory

Exact implementation, input series, RMA/EMA seeding, lengths, nonlinear transforms, warm-up,
frequency response, elapsed/traded/activity-time decay and confirmation logic.

### D — data/instrument plane

Exact instrument/contract, exchange, vendor/feed, adjusted/raw basis, futures roll/settlement,
correction vintage, entitlement/delay, qualifying-trade policy and rights.

No report may use “timeframe effect” without showing which of G/A/K/D changed.

## 7. Mechanism hypotheses and decisive interventions

| Hypothesis | Required intervention | Evidence that would favor it | Falsifier |
|---|---|---|---|
| `ARTIFACT` | Exact parity, history truncation, implementation and data-vintage replay | Effect disappears or signal vector changes under irrelevant history/seed/vendor changes | Stable post-warm-up parity and survival across lawful replications |
| `FILTER_MEMORY` | Compare fixed-bar human chart with elapsed/traded/activity-memory-matched kernels | Usefulness follows matched kernel memory across grains | One grain remains superior after memory matching |
| `SESSION_GRAMMAR` | Shift anchors; compare semantic session boundaries with arbitrary phases | Effect concentrates at economically meaningful session partitions | Broad survival across most phases |
| `STRUCTURE_SCALE` | Freeze outcome-blind scale band, then evaluate held-out instruments | Frozen structure-to-kernel relationship transfers instrument-disjoint | Relationship fails untouched confirmation/permutation |
| `INFORMATION_TIME` | Compare wall clock with equal-volume/trade-count/variance clocks | Activity-time construction is more stable and transferable | Wall-clock result survives while activity clocks do not |
| `REGIME_MULTISCALE` | Test scale stability across subwindows/regimes | Predictable hierarchy changes while one fixed scale fails | One stable scale band survives regimes |
| `UNRESOLVED_DATA` | Freeze exact recipe and lawful history | Required identity/session/vector cannot be obtained | Complete hashed chart packet and parity |

Mixtures are allowed only when separate interventions identify each component.

## 8. Exact contracts

All JSON is strict: UTF-8, sorted deterministic serialization for hashes, no NaN, no implicit
defaults and no untyped free-form success state.

### 8.1 `mastermind.temporal_chart_recipe.v1`

```json
{
  "schema_version": "mastermind.temporal_chart_recipe.v1",
  "recipe_id": "wmt-720-extended-0123456789abcdef",
  "captured_at": "ISO-8601 UTC",
  "capture_status": "complete|incomplete",
  "observer": "human-or-system-id",
  "instrument": {
    "display_symbol": "WMT",
    "tickerid": "EXCHANGE:TICKER",
    "main_tickerid": "EXCHANGE:TICKER",
    "asset_class": "equity|futures|spot_fx|cfd|etf|other",
    "exchange": "string",
    "vendor_feed": "string",
    "currency": "string",
    "contract_month": null,
    "continuous_symbol": null,
    "roll_recipe": null,
    "settlement_basis": null
  },
  "chart": {
    "timeframe_period": "720",
    "named_session": "regular|extended|24h|us_regular|vendor_named",
    "exchange_timezone": "IANA zone",
    "chart_timezone": "IANA zone or explicit manual value",
    "extended_hours_enabled": true,
    "price_adjustment": "split_adjusted|raw|other",
    "dividend_adjustment": "on|off|unknown",
    "back_adjustment": "on|off|not_applicable|unknown",
    "settlement_as_close": "on|off|not_applicable|unknown"
  },
  "indicator": {
    "family": "owner_rsi_macd_stochrsi|other",
    "probe_version": "temporal-recipe-probe-v1",
    "source_git_blob_sha": "40-hex",
    "inputs": {
      "rsi_len": 14,
      "macd_fast": 14,
      "macd_slow": 60,
      "macd_signal": 5,
      "stoch_len": 14,
      "smooth_k": 3,
      "smooth_d": 3
    },
    "ema_adjust": false,
    "rma_seed": "sma_seeded"
  },
  "export": {
    "csv_filename": "string",
    "csv_sha256": "64-hex",
    "row_count": 1,
    "first_bar_open_ms": 0,
    "last_bar_close_ms": 0,
    "loaded_history_start_ms": 0
  },
  "rights": {
    "use": "local_research_only",
    "redistribution": "blocked|allowed|unknown",
    "source_reference": "string"
  },
  "missing_fields": []
}
```

`capture_status=complete` requires every load-bearing field, an exact CSV hash and
`missing_fields=[]`. Chart timezone is manual because Pine’s exchange-timezone variables do not
prove the user-selected chart display timezone.

### 8.2 `mastermind.temporal_bar_receipt.v1`

One row per actual bar:

```json
{
  "schema_version": "mastermind.temporal_bar_receipt.v1",
  "recipe_id": "string",
  "bar_index": 0,
  "open_ms": 0,
  "close_ms": 0,
  "nominal_minutes": 720,
  "effective_minutes": 720,
  "traded_minutes": null,
  "volume": null,
  "trade_count": null,
  "realized_variance": null,
  "session_flags": {
    "premarket": false,
    "market": true,
    "postmarket": false,
    "first_session_bar": false,
    "last_session_bar": false,
    "first_regular_bar": false,
    "last_regular_bar": false
  },
  "clipped": false,
  "confirmed": true,
  "empty_interval": false,
  "known_at_ms": 0,
  "source_row_sha256": "64-hex"
}
```

Null activity fields mean unavailable, never zero. A missing/no-trade interval is not forward-filled.

### 8.3 `mastermind.temporal_kernel_signature.v1`

```json
{
  "schema_version": "mastermind.temporal_kernel_signature.v1",
  "indicator_spec_hash": "64-hex",
  "input_series": "close",
  "components": [],
  "bar_memory": {
    "rma14_half_life_bars": 9.353206684999464,
    "ema14_half_life_bars": 4.843767254792992,
    "ema60_half_life_bars": 20.79172760465854,
    "ema5_half_life_bars": 1.7095112913514545
  },
  "clock_basis": "bar_count|elapsed_time|traded_time|volume_time|trade_time|variance_time",
  "clock_parameter": {},
  "warmup_first_finite_index": {},
  "linear_diagnostics": {},
  "nonlinear_caveat": "RSI and StochRSI prevent exact linear equivalence across grain changes"
}
```

Frequency-response values are diagnostics, not outcome-selected tuning targets.

### 8.4 `mastermind.temporal_artifact_attack.v1`

```json
{
  "schema_version": "mastermind.temporal_artifact_attack.v1",
  "operation_key": "temporal-grain-gakd-artifact-attack-r1-20260903-sol-001",
  "recipes": [],
  "frozen_grid_hash": "64-hex",
  "trial_family": "temporal_grain_gakd_r1",
  "tests": [],
  "parity": {
    "status": "PASS|FAIL|UNRESOLVED_DATA",
    "tolerance": 1e-10,
    "first_comparable_bar_ms": null,
    "max_abs_error": {}
  },
  "classification": "ARTIFACT|FILTER_MEMORY|SESSION_GRAMMAR|MIXED|UNRESOLVED_DATA",
  "classification_receipts": [],
  "authority": {
    "may_rank": false,
    "may_gate": false,
    "may_size": false,
    "may_trade": false,
    "may_modify_prophet": false
  }
}
```

Gate 2 cannot return `STRUCTURE_SCALE`, `INFORMATION_TIME` or `REGIME_MULTISCALE` as validated.
Those require later, separately preregistered children. Gate 2 may only establish that the motivating
effect survives or fails G/A/K/D artifact attacks and identify the mechanism class justified by
those interventions.

## 9. Gate 1 — exact reproduction

Gate 1 begins with two separate packets:

1. exact WMT chart;
2. exact silver chart.

The TradingView probe must expose in a table:

- `syminfo.tickerid`;
- `syminfo.main_tickerid`;
- `syminfo.session`;
- `syminfo.timezone`;
- `timeframe.period`;
- probe version and exact indicator parameters.

It must export numeric plots for:

- `time`, `time_close`, bar duration and `bar_index`;
- OHLCV already present in the chart export;
- regular/premarket/postmarket and first/last session flags;
- confirmed state;
- canonical RSI;
- RSI-MACD line, signal and histogram;
- StochRSI K and D.

The Git blob SHA of the probe and SHA-256 of the exported CSV enter the recipe. The chart export
must be loaded far enough left to establish a declared warm-up start.

Gate 1 passes for a recipe only when:

- instrument/feed/session/timeframe/adjustment identity is complete;
- actual bar open/close timestamps are present;
- Python reproduction matches TradingView after the frozen warm-up within the declared tolerance;
- adding or removing irrelevant leading history does not change comparable post-warm-up values;
- no alternate instrument or feed was silently substituted.

If either motivator cannot be frozen, its result is `UNRESOLVED_DATA`; the other recipe may still
proceed independently.

## 10. Gate 2 — artifact attack

The entire diagnostic grid is generated and hashed before any localization/risk/economic outcome
is read. It is registered under the existing `TrialLedger` family `temporal_grain_gakd_r1`.

### 10.1 Human-chart family

Keep indicator bar-count parameters fixed while changing grain. This reproduces the interaction
Chris sees and deliberately lets real-world memory change.

### 10.2 Memory-matched family

Freeze the target decay constants from the motivating kernel and derive approximate lengths for
each alternative grain. At minimum report bar-count, elapsed-time and traded-time matches.

For a fixed-duration approximation:

```text
EMA half-life bars = ln(0.5) / ln(1 - 2/(N+1))
RMA half-life bars = ln(0.5) / ln(1 - 1/N)
target half-life time = half-life bars × actual clock amount per bar
```

For unequal or clipped bars, apply continuous-time decay per observation:

```text
alpha_i = 1 - exp(-delta_clock_i / tau)
state_i = alpha_i * x_i + (1 - alpha_i) * state_(i-1)
```

This is an identification challenger, not a claim of exact RSI equivalence.

### 10.3 Anchor/session family

For each complete recipe:

- exact chart anchor/session;
- semantic session alternatives allowed by the same instrument/feed;
- prespecified phase shifts;
- RTH/extended/24h only where genuinely available;
- holiday, early-close, DST, maintenance-break and missing-print cases;
- shortened final-bar disclosures.

No construction with a different instrument or vendor enters the same contrast.

### 10.4 Implementation/data-plane controls

- canonical owner indicator versus explicitly named standard price-MACD negative control;
- exact feed versus another feed only as a labeled D-plane contrast;
- adjusted versus raw only as separate basis classes;
- futures individual contract versus continuous contract only with explicit roll identity.

### 10.5 Signal-density and dependence controls

Before any later outcome study, Gate 2 reports:

- evaluable bar count;
- finite-indicator count;
- cross/turn count;
- events per traded day/session;
- overlapping-event clusters;
- warm-up loss;
- missing/clipped bar prevalence.

No configuration wins by merely firing less often.

## 11. Structure-derived scale — held after Gate 2

A later child may proceed only if the motivating phenomenon survives exact parity and artifact
attack.

`T_market` is represented as a **scale profile/band**, not a scalar:

- path swing distribution;
- mean-reversion decay;
- return autocorrelation/variance-ratio scales;
- volatility persistence;
- trend efficiency/persistence;
- session periodicities;
- liquidity/information-time periodicities;
- subwindow stability;
- multimodality and uncertainty.

`T_signal` is the frozen kernel signature and response band.

The later test asks whether a global, outcome-blind mapping from measured structure to a compatible
kernel band transfers on instrument-disjoint confirmation. It may consume existing Stock Identity
features read-only. Any intraday feature extension is a future preregistered version after the
current Stock Identity confirmatory arc; it is not patched into v0.

Mandatory abstentions include:

- incomplete instrument/session identity;
- insufficient history or activity coverage;
- unstable/multimodal scale with no frozen selection rule;
- phase-specific result that does not align with semantic sessions;
- material vendor/roll/correction ambiguity;
- dependence/effective-N below the registered floor.

## 12. Ownership freeze

| Concern | Canonical owner |
|---|---|
| Instrument, venue, vendor, contract, roll, session and adjustment identity | current Market Ontology / market-data / instrument-identity owners |
| Existing daily structural measurements | Stock Identity v0, read-only in this program |
| Future intraday structural extensions | separate post-current-arc Stock Identity vNext or broader Instrument Identity ruling |
| Kernel signature and G/A/K/D research harness | Signal Engine research under this workstream |
| Session-aware bar precedent | Entry Radar and existing session/calendar owners, consumed without changing tactical ownership |
| Look budget, multiple testing and evaluation | existing TrialLedger / Evaluation OS |
| Implementation/evidence | GitHub |
| Organizational workstream/decisions/handoffs | Agent OS |
| Runtime Job/Attempt/Worker lifecycle | Executive OS, only when a runtime operation exists |
| Transport and hot dialogue | Slack, never lifecycle truth |

This workstream creates no new canonical identity or data owner.

## 13. First vertical release boundary

The first empirical PR must deliver one independently useful research capability:

> Given a complete TradingView chart recipe plus CSV export, deterministically validate identity and
> hashes, reproduce the canonical indicator, reconstruct actual bar/session receipts, execute the
> frozen G/A/K/D diagnostic grid, and return a typed parity/artifact classification without reading
> trade outcomes or modifying any production system.

Expected implementation paths:

```text
research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine
research/signal_engine/temporal_scale/fixtures/README.md
scripts/research/temporal_scale/__init__.py
scripts/research/temporal_scale/contracts.py
scripts/research/temporal_scale/chart_export.py
scripts/research/temporal_scale/kernel_memory.py
scripts/research/temporal_scale/session_bars.py
scripts/research/temporal_scale/parity.py
scripts/research/temporal_scale/artifact_attack.py
scripts/research/run_temporal_scale_artifact_attack.py
tests/test_temporal_scale_contracts.py
tests/test_temporal_scale_kernel_memory.py
tests/test_temporal_scale_session_bars.py
tests/test_temporal_scale_parity.py
tests/test_temporal_scale_artifact_attack.py
```

Real WMT and silver exports are local/licensed research inputs and must not be committed unless their
rights explicitly permit it. Tests use synthetic and rights-safe fixtures; proof receipts store
hashes and summaries, not restricted raw data.

## 14. Routing

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
WHY NOT FABLE: the product/scientific architecture and no-rebuild boundaries are frozen; the next
mission is bounded, deterministic, reasoning-heavy research engineering. Sustained principal
continuity is not required.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

A concrete eligible session may be assigned later under the same W1 operation before START, with a
fresh top-level child carrier, `PICKUP_ACK`, separate `START`, and reciprocal continuation path.
This W0 does not create a Slack delivery, runtime Job or watcher.

## 15. Acceptance and stop conditions

W0 is accepted when:

- all records validate;
- exact protected and Macro pins are preserved;
- the TOI W0 projection is reconciled to the immutable merge;
- ownership and no-rebuild boundaries are unambiguous;
- W1 contracts, files, tests and proof are implementation-ready;
- current-main collision checks and CI are green;
- Sol accepts the exact head.

W1 stops and returns to Sol if:

- exact TradingView parity cannot be established;
- exact silver identity remains unresolved;
- the phenomenon fails history-truncation or anchor invariance;
- the effect disappears under memory matching;
- the data plane cannot lawfully express the chart;
- a second data plane, evaluator, event store, lifecycle or identity owner appears necessary;
- the worker is tempted to read outcomes before the diagnostic grid is frozen;
- current code or another carrier now owns the same paths.

Green CI proves only source integrity. W1 is not scientifically complete until the real WMT/silver
packets run through the real harness and produce hashed receipts. A surviving artifact attack is
not production validation.

## 16. Exact continuation

1. Validate and accept this records-only W0 carrier.
2. Create one top-level W1 carrier for
   `temporal-grain-gakd-artifact-attack-r1-20260903-sol-001`.
3. Bind one capable CTO Sol/Terra-class implementation session, require `PICKUP_ACK`, then separate
   `START`.
4. Implement the plan in
   `docs/superpowers/plans/2026-09-03-temporal-grain-gakd-artifact-attack-r1.md`.
5. Capture the exact WMT and silver TradingView recipes/exports.
6. Return `PASS`, `FAIL` or `UNRESOLVED_DATA` with immutable hashes and no outcome claim.
7. Sol alone decides whether a structure-scale preregistration child may begin.
