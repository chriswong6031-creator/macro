# Technical Opportunity Intelligence W2-0 — Data and Clock Archaeology Commission

**Date:** 2026-08-27  
**Parent:** `WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE`  
**Authority:** `research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-27.md`  
**Base archaeology:** `macro@463bb3b4b708a4748fc65a04250366ca94205186`, `mastermind-terminal@b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`  
**Mission class:** data/contract archaeology and proof design only  
**Recommended operator:** Fable principal with bounded data, Terminal-parity, and rights-review workers

---

## 1. Observable mission

Determine whether Mastermind currently has a causal, correction-safe, rights-safe, point-in-time Weekly/Daily/4H U.S. equity panel suitable for the first Technical Opportunity Compression Release experiment.

Audit Monthly derivation and context capability now so the full long-horizon end-state does not require a second broad data archaeology later. True tactical intraday remains owned by Live Entry Radar; W2-0 may crosswalk its source and clocks but may not create another feed, store, or event owner.

Return, for every source plane and for the combined research panel:

1. one canonical company capability state:
   - `PROVEN_LIVE`
   - `BUILT_NOT_PROVEN`
   - `PARTIAL`
   - `DARK_OR_DISCONNECTED`
   - `BROKEN`
   - `SPEC_ONLY`
   - `NOT_BUILT`
   - `REJECTED_BY_DESIGN`
2. one W3 gate result:
   - `ADMIT`
   - `HOLD`
   - `REJECT`

`ADMIT` means the exact frozen panel contract may be used for W3 research. It does not mean the eventual Technical Opportunity product is live or validated.

If the panel is not admitted, freeze the smallest lawful W2 implementation architecture using existing market-data owners. Do not build the panel in W2-0.

---

## 2. Why it matters

A technical system can look excellent while leaking:

- incomplete higher-timeframe bars;
- after-hours prints into regular-session bars;
- future split adjustments;
- current constituents into historical universes;
- corrected vendor bars before their actual availability;
- different 4H anchors between research and Terminal;
- reused ticker histories;
- survivor-only prices.

No W3 performance statistic is readable until the exact observation and availability clocks are proven.

---

## 3. Authority and precedence

1. Technical Opportunity architecture freeze
2. Current market-data and tick-plane architecture/rulings
3. Current Massive capability and license receipts
4. Existing collector/store contracts
5. Terminal chart/intraday contracts
6. Live Entry Radar price-receipt and event-time law
7. Existing identity and point-in-time universe owners
8. Current DNR
9. This commission

Entitlement text, API documentation, old handoffs, and artifact mtimes are evidence. They do not prove current production availability or lawful use.

---

## 4. Verified starting state

At the pinned archaeology:

- the repo contains daily equity stores with different depth and adjustment semantics;
- a Polygon/Massive intraday collector exists;
- `mtf_monitor.py` can derive an optional 4H state from an intraday store;
- Massive entitlement evidence reports minute/second aggregates and deep trade history;
- Terminal has its own intraday ingest, chart time-axis, session, and bar behavior;
- Live Entry Radar has price-receipt and tactical event-time contracts;
- no current artifact has yet been accepted as the whole-universe, deep-history, correction-safe Technical Opportunity 4H research panel.

The integrated deep 4H research-panel capability is therefore `NOT_BUILT` at the W0 decision level even though individual collector, entitlement, and store components are `PARTIAL` or `BUILT_NOT_PROVEN`.

Reverify on current heads.

---

## 5. Exact scope

### Repository and modification scope

- All W2-0 authored reports, receipts, validators, and tests live in `macro` on one W2-0 carrier.
- `mastermind-terminal` is read-only archaeology and parity evidence in W2-0.
- No production store, collector, chart, Radar, or data path is mutated.

### Stores and producers

Audit at minimum:

- `data/stocks/`
- `data/baskets/ohlcv/`
- `data/massive_stock_day/`
- `data/intraday/`
- Massive/tick-plane stores and receipts
- breadth/PIT membership and delisted stores
- split/dividend/corporate-action sources
- Terminal intraday stores/slices/manifests
- Live Entry Radar quote and slice sources
- R2/private/public publication routes where relevant

### Clocks

For every candidate input:

- event/trade timestamp;
- bar start/end;
- exchange timezone;
- session;
- source availability time;
- collection/write time;
- correction time;
- adjusted-price vintage;
- research `as_of` and `known_at`;
- provisional/final status.

### Horizons

- Daily and Weekly for the first vertical;
- candidate 4H constructions for the first vertical;
- Monthly derivation and completed-month availability as later structural context;
- Radar-owned 5m/tactical source and clock crosswalk only, with no second owner.

### Universe

- current versus historical listed universe;
- index membership versus all-liquid-stock universe;
- delistings;
- ticker reuse;
- IPO history;
- ADR/class-share treatment;
- liquidity and price eligibility;
- per-date coverage.

### Rights

- historical research use;
- server-side computation;
- derived artifact storage;
- subscriber display;
- public display;
- redistribution;
- retention and deletion obligations.

---

## 6. Explicit non-goals

Do not:

- run technical outcome tests;
- implement Compression Release;
- create a new WebSocket connection, collector, tick plane, or database;
- change current bars or production chart behavior;
- modify Live Entry Radar;
- backfill data;
- repair corporate actions;
- select a vendor by intuition;
- infer rights from successful API calls;
- call a short smoke file a deep panel;
- create a synthetic 4H series from daily bars;
- transfer tactical-intraday ownership out of Live Entry Radar;
- treat a W3 `ADMIT` gate as product, signal, or production completion.

---

## 7. Required output artifacts

W2-0-owned paths, after an exact pickup collision recheck:

- `research/technical_opportunity/W2_DATA_PLANE_CENSUS.md`
- `research/technical_opportunity/w2_store_contracts.json`
- `research/technical_opportunity/w2_clock_matrix.json`
- `research/technical_opportunity/w2_coverage_receipts.json`
- `research/technical_opportunity/w2_terminal_parity_receipts.json`
- `research/technical_opportunity/w2_rights_matrix.json`
- `research/technical_opportunity/W2_DATA_CLOCK_ARCHITECTURE_FREEZE.md`
- `research/technical_opportunity/W2_REPORT.md`
- `scripts/research/validate_toi_w2_store_contracts.py`
- `scripts/research/run_toi_w2_clock_fixtures.py`
- `scripts/research/run_toi_w2_terminal_parity.py`
- `scripts/research/run_toi_w2_coverage.py`
- `tests/test_toi_w2_data_clock.py`
- `agentos/handoffs/TECHNICAL-OPPORTUNITY-INTELLIGENCE-W2-0-<YYYY-MM-DD>.md`

The date token in the handoff filename is the actual close date; every other path above is exact.

No permanent data or engine path changes in W2-0.

---

## 8. Store-contract schema

Each candidate store receives:

```json
{
  "schema_version": "toi.store_contract.v1",
  "store_id": "",
  "owner_program": "",
  "producer_paths": [],
  "consumer_paths": [],
  "physical_location": [],
  "source_vendor": "",
  "source_rights_ref": null,
  "universe_definition": "",
  "first_date": null,
  "last_date": null,
  "row_count": null,
  "symbol_count": null,
  "price_basis": "raw|split_adjusted|total_return|unknown",
  "timestamp_basis": "",
  "session_basis": "RTH|extended|mixed|unknown",
  "bar_definition": "",
  "source_available_at": "present|absent|unverified",
  "correction_policy": "",
  "corporate_action_policy": "",
  "point_in_time_status": "proven|partial|not_pit|unknown",
  "delisted_coverage": "proven|partial|absent|unknown",
  "ticker_reuse_guard": "proven|partial|absent|unknown",
  "rights": {
    "research": "allowed|blocked|unknown",
    "derived_storage": "allowed|blocked|unknown",
    "subscriber_display": "allowed|blocked|unknown",
    "public_display": "allowed|blocked|unknown"
  },
  "coverage_receipt": "",
  "integrity_findings": [],
  "capability_state": "PROVEN_LIVE|BUILT_NOT_PROVEN|PARTIAL|DARK_OR_DISCONNECTED|BROKEN|SPEC_ONLY|NOT_BUILT|REJECTED_BY_DESIGN",
  "w3_admission": "ADMIT|HOLD|REJECT"
}
```

Strict JSON, no NaN or implicit defaults.

`source_rights_ref` must be non-null before any rights field is `allowed`. `w3_admission=ADMIT` requires all load-bearing source planes to have a proven contract; it may not be inferred by majority vote across mixed states.

---

## 9. Required bar constructions

W2-0 must define and compare at least:

### `4H-CLOCK`

- exact ET anchor;
- exact inclusion/exclusion of pre-market and after-hours;
- treatment of 9:30–13:30 and 13:30–16:00 partial bar or another product-parity split;
- early-close days;
- DST;
- holidays;
- missing-minute behavior;
- correction behavior;
- completed-bar `known_at`.

### `195M-RTH`

- 9:30–12:45 ET;
- 12:45–16:00 ET;
- regular session only;
- early-close rule;
- independent method/trial identity.

### Completed Monthly context

- calendar/exchange month-end rule;
- completed-month `known_at`;
- holiday and partial-month handling;
- adjustment and correction basis;
- explicit statement that Monthly is later context and not a W3 trigger horizon.

The operator must also inspect Terminal’s current displayed “4H” construction. Research and product parity is a measured question, not an assumption.

No pooling across 4H constructions.

---

## 10. Time, null, and correction behavior

- A missing interval remains missing unless the source contract explicitly defines a zero-volume carry; never forward-fill OHLC bars by convenience.
- Late vendor corrections retain correction receipts.
- Adjusted and raw series are separate basis classes.
- A future-known split factor may not be applied to a historical research vintage unless the system’s target explicitly uses a final-price basis and labels it non-PIT.
- If source availability time cannot be reconstructed, historical evidence carries the weaker research mode and cannot claim operational PIT.
- A bar is final only when its registered close time and source delay/correction budget have elapsed.
- Empty vendor results are distinguished from request failure and no entitlement.
- Coverage denominators are point-in-time eligible subjects, not current survivors.
- Monthly and tactical-intraday residue remains explicitly classified even when not admitted to the first W3 vertical.

---

## 11. Deterministic, statistical, and model-generated responsibilities

### Deterministic

- file and store inventory;
- schema and metadata inspection;
- sample timestamp reconstruction;
- bar reaggregation;
- digest and correction comparison;
- split checks;
- point-in-time membership joins;
- Terminal parity comparisons;
- Live Entry Radar ownership/clock crosswalk;
- rights-document reference extraction.

### Statistical

- coverage percentages;
- correction frequency;
- bar mismatch rates;
- missing-interval rates;
- split-jump incidence;
- universe depth distributions;
- clock skew distributions.

No return prediction or alpha tests.

### Model-generated

Models may summarize contracts and flag discrepancies. They may not decide legal rights, silently repair bars, infer missing timestamps, choose a canonical clock, or grant W3 admission without deterministic receipts and principal review.

---

## 12. Ordered implementation sequence

1. Re-pin Skillpack and current repository heads.
2. Re-run carrier/path collision census.
3. Read current market-data, tick-plane, Live Entry Radar, Terminal intraday, identity, and rights architecture.
4. Enumerate physical and published stores.
5. Generate per-store contract records.
6. Measure history depth and point-in-time universe coverage.
7. Audit price adjustment, splits, reused tickers, delistings, and corrections.
8. Reconstruct source availability and finality clocks.
9. Derive `4H-CLOCK` and `195M-RTH` on a fixed small symbol/date corpus.
10. Derive and receipt completed Monthly context from the candidate daily owner.
11. Compare with Terminal chart bars and any current Macro 4H consumer.
12. Crosswalk Radar-owned tactical clocks without changing them.
13. Audit rights by use case.
14. Classify each plane using the canonical capability vocabulary and assign the W3 gate.
15. If not admitted, freeze one extension architecture over existing owners.
16. Run adversarial review.
17. Validate artifacts and return the continuation handoff.

---

## 13. Required adversarial fixtures

At minimum:

- normal full session;
- early-close session;
- DST transition week;
- month-end ending on a holiday/weekend;
- partial first/last listing month;
- symbol with missing minutes;
- symbol with a split;
- symbol with ticker reuse or identity hazard;
- recent IPO;
- delisted symbol where available;
- extended-hours price gap;
- vendor correction;
- halted or extremely illiquid session;
- class-share symbol;
- ETF;
- exact same bar viewed in Terminal and re-derived in Macro.

---

## 14. Failure states and stop condition

Return to Sol immediately if:

- rights are unknown for the intended use;
- current and historical bars use irreconcilable price bases;
- Terminal and research 4H bars differ materially without an explicit product ruling;
- a second feed/store appears necessary;
- the point-in-time universe denominator cannot be defined;
- delisted or ticker-reuse hazards make the planned claim unreadable;
- a current carrier owns the same data/clock paths;
- the operator is tempted to begin outcome tests before the clock verdict;
- `ADMIT` would require treating a `PARTIAL`, `BUILT_NOT_PROVEN`, or unknown load-bearing source as proven;
- tactical intraday parity would require changing Live Entry Radar ownership in this wave.

Do not weaken the claim to make the panel look ready. Classify it honestly.

---

## 15. Acceptance tests and evidence

W2-0 is a research/architecture wave. Proof is deterministic and real-data, not production deployment.

Minimum gates:

- every store record validates;
- every claimed clock is demonstrated on real timestamps;
- at least 20 symbol-session parity cases per 4H construction;
- completed Monthly context passes month-end and partial-month fixtures;
- zero unexplained lookahead in the fixture set;
- split and correction receipts;
- current and historical universe coverage tables;
- rights matrix with primary documents or explicit unknown;
- one canonical capability state and W3 gate per plane;
- no data/runtime path changed.

Required proof:

```bash
python3 scripts/agentos.py validate
python3 scripts/research/validate_toi_w2_store_contracts.py
python3 scripts/research/run_toi_w2_clock_fixtures.py
python3 scripts/research/run_toi_w2_terminal_parity.py
python3 scripts/research/run_toi_w2_coverage.py
python3 -m pytest tests/test_toi_w2_data_clock.py -q
git diff --check
```

Hostile tests must prove that unknown rights cannot become allowed, missing intervals cannot be silently forward-filled, a mixed or unrecognized capability state fails validation, a load-bearing `HOLD` plane cannot yield combined `ADMIT`, and unequal clock constructions cannot be pooled.

---

## 16. Completion and continuation

W2-0 is complete when Sol can either:

1. assign the combined panel a canonical capability state and `w3_admission=ADMIT` under exact contracts; or
2. keep W3 held and commission one bounded W2 implementation that extends existing owners and names the production proof required; or
3. reject the planned panel construction by design and recut the first vertical without pretending the missing horizon exists.

The continuation handoff must include:

- exact store capability states and W3 gates;
- exact canonical clock recommendation and rejected alternatives;
- Terminal parity result;
- Monthly-context and Radar-owned tactical residue;
- coverage and rights gaps;
- proposed owner and paths for any W2 build;
- compute/storage/backfill estimate;
- exact W3 blocker status;
- do-not-redo list.
