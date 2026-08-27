# Technical Opportunity Intelligence W2-0 — Data and Clock Archaeology Commission

**Date:** 2026-08-27  
**Parent:** `WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE`  
**Authority:** `research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-27.md`  
**Base archaeology:** `macro@463bb3b4b708a4748fc65a04250366ca94205186`, `mastermind-terminal@b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`  
**Mission class:** data/contract archaeology and proof design only  
**Recommended operator:** Fable principal with bounded data, Terminal-parity, and rights-review workers

---

## 1. Observable mission

Determine whether Mastermind currently has a causal, correction-safe, rights-safe, point-in-time Weekly/Daily/4H U.S. equity panel suitable for Technical Opportunity research.

Return one unambiguous verdict per plane:

- **PROVEN_READY**
- **PARTIAL**
- **BROKEN**
- **NOT_BUILT**
- **REJECTED_BY_DESIGN**

If the panel is not ready, freeze the smallest lawful W2 implementation architecture using existing market-data owners. Do not build the panel in W2-0.

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

Reverify on current heads.

---

## 5. Exact scope

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
- create a synthetic 4H series from daily bars.

---

## 7. Required output artifacts

Proposed W2-0-owned paths:

- `research/technical_opportunity/W2_DATA_PLANE_CENSUS.md`
- `research/technical_opportunity/w2_store_contracts.json`
- `research/technical_opportunity/w2_clock_matrix.json`
- `research/technical_opportunity/w2_coverage_receipts.json`
- `research/technical_opportunity/w2_terminal_parity_receipts.json`
- `research/technical_opportunity/w2_rights_matrix.json`
- `research/technical_opportunity/W2_DATA_CLOCK_ARCHITECTURE_FREEZE.md`
- `research/technical_opportunity/W2_REPORT.md`
- one continuation handoff

No permanent data or engine path changes in W2-0.

---

## 8. Store-contract schema

Each candidate store receives:

```json
{
  "store_id": "",
  "owner_program": "",
  "producer_paths": [],
  "consumer_paths": [],
  "physical_location": [],
  "source_vendor": "",
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
  "verdict": "PROVEN_READY|PARTIAL|BROKEN|NOT_BUILT|REJECTED_BY_DESIGN"
}
```

Strict JSON, no NaN or implicit defaults.

---

## 9. Required 4H constructions

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

The operator must also inspect Terminal’s current displayed “4H” construction. Research and product parity is a measured question, not an assumption.

No pooling across constructions.

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

Models may summarize contracts and flag discrepancies. They may not decide legal rights, silently repair bars, infer missing timestamps, or choose a canonical clock without deterministic receipts and principal review.

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
10. Compare with Terminal chart bars and any current Macro 4H consumer.
11. Audit rights by use case.
12. Classify each plane and the combined panel.
13. If not ready, freeze one extension architecture over existing owners.
14. Run adversarial review.
15. Validate artifacts and return the continuation handoff.

---

## 13. Required adversarial fixtures

At minimum:

- normal full session;
- early-close session;
- DST transition week;
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
- the operator is tempted to begin outcome tests before the clock verdict.

Do not weaken the claim to make the panel look ready. Classify it honestly.

---

## 15. Acceptance tests and production proof

W2-0 is a research/architecture wave. Proof is deterministic and real-data, not production deployment.

Minimum gates:

- every store record validates;
- every claimed clock is demonstrated on real timestamps;
- at least 20 symbol-session parity cases per 4H construction;
- zero unexplained lookahead in the fixture set;
- split and correction receipts;
- current and historical universe coverage tables;
- rights matrix with primary documents or explicit unknown;
- exact current verdict;
- no data/runtime path changed.

Required commands include:

```bash
python3 scripts/agentos.py validate
python3 <w2_store_contract_validator>
python3 <w2_bar_clock_fixture_runner>
python3 <w2_terminal_parity_runner>
python3 <w2_coverage_runner>
git diff --check
```

---

## 16. Completion and continuation

W2-0 is complete when Sol can either:

1. declare the existing panel `PROVEN_READY` for W3 under exact contracts; or
2. commission one bounded W2 implementation that extends existing owners and names the production proof required.

The continuation handoff must include:

- exact store verdicts;
- exact canonical clock recommendation and rejected alternatives;
- Terminal parity result;
- coverage and rights gaps;
- proposed owner and paths for any W2 build;
- compute/storage/backfill estimate;
- exact W3 blocker status;
- do-not-redo list.
