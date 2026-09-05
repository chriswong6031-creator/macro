# Macro Context Index — Benchmark Results

## Eval run v1 — 2026-07-19 04:38 UTC

### Index SHAs

- `macro-dashboard`: `014433eae719`

### Scope: shared-visibility rows only

Rows evaluated: **68**  Pass: **35**  Global Recall@10: **51.5%**

### Gate results

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Global Recall@10 | ≥90% | **FAIL** | 51.5% |
| adjudication_replay Recall@10 | ≥90% | **FAIL** | 50.0% (7/14) |
| Governance A0/A1 precision | ≥95% | **FAIL** | 60.0% (6/10) |

### Latency

| p50 | p95 |
|-----|-----|
| 527ms | 925ms |

### Per-family Recall@10

| Family | Pass | Fail | Recall@10 |
|--------|------|------|-----------|
| adjudication_replay | 7 | 7 | 50.0% |
| architecture | 6 | 1 | 85.7% |
| code | 5 | 3 | 62.5% |
| contract | 3 | 1 | 75.0% |
| current_state | 2 | 0 | 100.0% |
| freshness | 1 | 0 | 100.0% |
| governance | 6 | 4 | 60.0% |
| location | 3 | 3 | 50.0% |
| negative_control | 0 | 10 | 0.0% |
| operations | 0 | 1 | 0.0% |
| research | 2 | 3 | 40.0% |

### Cross-repo block (private-visibility rows)

_NOT-EVALUATED: --include-private not set. Re-run with --include-private to evaluate cross-repo rows._

### Failed rows

33 failed:

- **CTX-002** (location): scripts/build_active_build_map.py
- **CTX-003** (code): engine/market_drivers.py
- **CTX-004** (code): engine/neuralweb/query.py
- **CTX-006** (location): scripts/build_market_structure_page.py
- **CTX-007** (governance): scripts/check_blocklist_drift.py
- **CTX-010** (governance): research/DO_NOT_REBUILD.md, research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-013** (governance): research/DO_NOT_REBUILD.md
- **CTX-015** (governance): research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md
- **CTX-039** (contract): scripts/build_active_build_map.py
- **CTX-041** (research): research/DO_NOT_REBUILD.md
- **CTX-042** (research): research/DO_NOT_REBUILD.md
- **CTX-046** (location): config/synapse.yml, docs/SIGNAL_BUS.md
- **CTX-047** (code): scripts/check_template_site_sync.py
- **CTX-049** (operations): scripts/check_blocklist_drift.py
- **CTX-050** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-051** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-052** (adjudication_replay): engine/risk_radar.py
- **CTX-053** (adjudication_replay): engine/market_drivers.py
- **CTX-056** (adjudication_replay): research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md
- **CTX-059** (adjudication_replay): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-060** (adjudication_replay): research/CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md
- **CTX-066** (research): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-067** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-068** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-069** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-070** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-071** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-072** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-073** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-074** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-075** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-076** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-082** (adjudication_replay): research/DO_NOT_REBUILD.md

---

_Nulls printed per house epistemics. No content excerpts from private projects._

## Eval run v2 — 2026-07-19 05:36 UTC

### Index SHAs

- `macro-dashboard`: `fb23f9c61ca0`

### Scope: shared-visibility rows only

Rows evaluated: **68**  Pass: **35**  Global Recall@10: **51.5%**

### Gate results

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Global Recall@10 | ≥90% | **FAIL** | 51.5% |
| adjudication_replay Recall@10 | ≥90% | **FAIL** | 57.1% (8/14) |
| Governance A0/A1 precision | ≥95% | **FAIL** | 70.0% (7/10) |

### Latency

| p50 | p95 |
|-----|-----|
| 534ms | 836ms |

### Per-family Recall@10

| Family | Pass | Fail | Recall@10 |
|--------|------|------|-----------|
| adjudication_replay | 8 | 6 | 57.1% |
| architecture | 4 | 3 | 57.1% |
| code | 5 | 3 | 62.5% |
| contract | 3 | 1 | 75.0% |
| current_state | 2 | 0 | 100.0% |
| freshness | 1 | 0 | 100.0% |
| governance | 7 | 3 | 70.0% |
| location | 3 | 3 | 50.0% |
| negative_control | 0 | 10 | 0.0% |
| operations | 0 | 1 | 0.0% |
| research | 2 | 3 | 40.0% |

### Cross-repo block (private-visibility rows)

_NOT-EVALUATED: --include-private not set. Re-run with --include-private to evaluate cross-repo rows._

### Failed rows

33 failed:

- **CTX-002** (location): scripts/build_active_build_map.py
- **CTX-003** (code): engine/market_drivers.py
- **CTX-004** (code): engine/neuralweb/query.py
- **CTX-006** (location): scripts/build_market_structure_page.py
- **CTX-007** (governance): scripts/check_blocklist_drift.py
- **CTX-010** (governance): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-015** (governance): research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md
- **CTX-025** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-039** (contract): scripts/build_active_build_map.py
- **CTX-041** (research): research/DO_NOT_REBUILD.md
- **CTX-042** (research): research/DO_NOT_REBUILD.md
- **CTX-044** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-046** (location): config/synapse.yml, docs/SIGNAL_BUS.md
- **CTX-047** (code): scripts/check_template_site_sync.py
- **CTX-049** (operations): scripts/check_blocklist_drift.py
- **CTX-050** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-051** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-052** (adjudication_replay): engine/risk_radar.py
- **CTX-053** (adjudication_replay): engine/market_drivers.py
- **CTX-056** (adjudication_replay): research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md
- **CTX-059** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-060** (adjudication_replay): research/CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md
- **CTX-066** (research): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-067** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-068** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-069** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-070** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-071** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-072** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-073** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-074** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-075** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-076** (negative_control): no_answer: returned 30 results; expected honest null

---

_Nulls printed per house epistemics. No content excerpts from private projects._

## Eval run v3 — 2026-07-20 09:07 UTC

> NOTE: this run used a stale DB/benchmark snapshot (pre-rebuild, 68 rows); superseded by run v4. Kept per append-only policy.

### Index SHAs

- `macro-dashboard`: `014433eae719`

### Scope: shared-visibility rows only

Rows evaluated: **68**  Pass: **36**  Global Recall@10: **52.9%**

### Gate results

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Global Recall@10 | ≥90% | **FAIL** | 52.9% |
| adjudication_replay Recall@10 | ≥90% | **FAIL** | 57.1% (8/14) |
| Governance A0/A1 precision | ≥95% | **FAIL** | 60.0% (6/10) |

### Latency

| p50 | p95 |
|-----|-----|
| 528ms | 1050ms |

### Per-family Recall@10

| Family | Pass | Fail | Recall@10 |
|--------|------|------|-----------|
| adjudication_replay | 8 | 6 | 57.1% |
| architecture | 6 | 1 | 85.7% |
| code | 5 | 3 | 62.5% |
| contract | 3 | 1 | 75.0% |
| current_state | 2 | 0 | 100.0% |
| freshness | 1 | 0 | 100.0% |
| governance | 6 | 4 | 60.0% |
| location | 3 | 3 | 50.0% |
| negative_control | 0 | 10 | 0.0% |
| operations | 0 | 1 | 0.0% |
| research | 2 | 3 | 40.0% |

### Cross-repo block (private-visibility rows)

_NOT-EVALUATED: --include-private not set. Re-run with --include-private to evaluate cross-repo rows._

### Failed rows

32 failed:

- **CTX-002** (location): scripts/build_active_build_map.py
- **CTX-003** (code): engine/market_drivers.py
- **CTX-004** (code): engine/neuralweb/query.py
- **CTX-006** (location): scripts/build_market_structure_page.py
- **CTX-007** (governance): scripts/check_blocklist_drift.py
- **CTX-010** (governance): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-013** (governance): research/DO_NOT_REBUILD.md
- **CTX-015** (governance): research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md
- **CTX-039** (contract): scripts/build_active_build_map.py
- **CTX-041** (research): research/DO_NOT_REBUILD.md
- **CTX-042** (research): research/DO_NOT_REBUILD.md
- **CTX-046** (location): config/synapse.yml, docs/SIGNAL_BUS.md
- **CTX-047** (code): scripts/check_template_site_sync.py
- **CTX-049** (operations): scripts/check_blocklist_drift.py
- **CTX-050** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-051** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-052** (adjudication_replay): engine/risk_radar.py
- **CTX-053** (adjudication_replay): engine/market_drivers.py
- **CTX-056** (adjudication_replay): research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md
- **CTX-059** (adjudication_replay): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-060** (adjudication_replay): research/CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md
- **CTX-066** (research): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-067** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-068** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-069** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-070** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-071** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-072** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-073** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-074** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-075** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-076** (negative_control): no_answer: returned 30 results; expected honest null

---

_Nulls printed per house epistemics. No content excerpts from private projects._

## Eval run v4 — 2026-07-20 09:47 UTC

### Index SHAs

- `macro-dashboard`: `972521325da3`

### Scope: shared-visibility rows only

Rows evaluated: **76**  Pass: **37**  Global Recall@10: **48.7%**

### Gate results

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Global Recall@10 | ≥90% | **FAIL** | 48.7% |
| adjudication_replay Recall@10 | ≥90% | **FAIL** | 57.1% (8/14) |
| Governance A0/A1 precision | ≥95% | **FAIL** | 70.0% (7/10) |

### Latency

| p50 | p95 |
|-----|-----|
| 553ms | 924ms |

### Per-family Recall@10

| Family | Pass | Fail | Recall@10 |
|--------|------|------|-----------|
| adjudication_replay | 8 | 6 | 57.1% |
| architecture | 4 | 3 | 57.1% |
| code | 5 | 3 | 62.5% |
| comprehension | 2 | 6 | 25.0% |
| contract | 3 | 1 | 75.0% |
| current_state | 2 | 0 | 100.0% |
| freshness | 1 | 0 | 100.0% |
| governance | 7 | 3 | 70.0% |
| location | 3 | 3 | 50.0% |
| negative_control | 0 | 10 | 0.0% |
| operations | 0 | 1 | 0.0% |
| research | 2 | 3 | 40.0% |

### Cross-repo block (private-visibility rows)

_NOT-EVALUATED: --include-private not set. Re-run with --include-private to evaluate cross-repo rows._

### Failed rows

39 failed:

- **CTX-002** (location): scripts/build_active_build_map.py
- **CTX-003** (code): engine/market_drivers.py
- **CTX-004** (code): engine/neuralweb/query.py
- **CTX-006** (location): scripts/build_market_structure_page.py
- **CTX-007** (governance): scripts/check_blocklist_drift.py
- **CTX-010** (governance): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-015** (governance): research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md
- **CTX-025** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-039** (contract): scripts/build_active_build_map.py
- **CTX-041** (research): research/DO_NOT_REBUILD.md
- **CTX-042** (research): research/DO_NOT_REBUILD.md
- **CTX-044** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-046** (location): config/synapse.yml, docs/SIGNAL_BUS.md
- **CTX-047** (code): scripts/check_template_site_sync.py
- **CTX-049** (operations): scripts/check_blocklist_drift.py
- **CTX-050** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-051** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-052** (adjudication_replay): engine/risk_radar.py
- **CTX-053** (adjudication_replay): engine/market_drivers.py
- **CTX-056** (adjudication_replay): research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md
- **CTX-059** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-060** (adjudication_replay): research/CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md
- **CTX-066** (research): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-067** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-068** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-069** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-070** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-071** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-072** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-073** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-074** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-075** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-076** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-098** (comprehension): engine/market_state.py
- **CTX-099** (comprehension): engine/stock_score.py
- **CTX-100** (comprehension): engine/playbook.py
- **CTX-101** (comprehension): engine/signal_gate.py
- **CTX-102** (comprehension): engine/risk_radar.py
- **CTX-103** (comprehension): engine/china_internals.py

---

_Nulls printed per house epistemics. No content excerpts from private projects._

## Eval run v5 — 2026-07-20 09:52 UTC (post CXI-R21 comprehension regold)

### Index SHAs

- `macro-dashboard`: `972521325da3`

### Scope: shared-visibility rows only

Rows evaluated: **76**  Pass: **43**  Global Recall@10: **56.6%**

### Gate results

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Global Recall@10 | ≥90% | **FAIL** | 56.6% |
| adjudication_replay Recall@10 | ≥90% | **FAIL** | 57.1% (8/14) |
| Governance A0/A1 precision | ≥95% | **FAIL** | 70.0% (7/10) |

### Latency

| p50 | p95 |
|-----|-----|
| 531ms | 1022ms |

### Per-family Recall@10

| Family | Pass | Fail | Recall@10 |
|--------|------|------|-----------|
| adjudication_replay | 8 | 6 | 57.1% |
| architecture | 4 | 3 | 57.1% |
| code | 5 | 3 | 62.5% |
| comprehension | 8 | 0 | 100.0% |
| contract | 3 | 1 | 75.0% |
| current_state | 2 | 0 | 100.0% |
| freshness | 1 | 0 | 100.0% |
| governance | 7 | 3 | 70.0% |
| location | 3 | 3 | 50.0% |
| negative_control | 0 | 10 | 0.0% |
| operations | 0 | 1 | 0.0% |
| research | 2 | 3 | 40.0% |

### Cross-repo block (private-visibility rows)

_NOT-EVALUATED: --include-private not set. Re-run with --include-private to evaluate cross-repo rows._

### Failed rows

33 failed:

- **CTX-002** (location): scripts/build_active_build_map.py
- **CTX-003** (code): engine/market_drivers.py
- **CTX-004** (code): engine/neuralweb/query.py
- **CTX-006** (location): scripts/build_market_structure_page.py
- **CTX-007** (governance): scripts/check_blocklist_drift.py
- **CTX-010** (governance): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-015** (governance): research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md
- **CTX-025** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-039** (contract): scripts/build_active_build_map.py
- **CTX-041** (research): research/DO_NOT_REBUILD.md
- **CTX-042** (research): research/DO_NOT_REBUILD.md
- **CTX-044** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-046** (location): config/synapse.yml, docs/SIGNAL_BUS.md
- **CTX-047** (code): scripts/check_template_site_sync.py
- **CTX-049** (operations): scripts/check_blocklist_drift.py
- **CTX-050** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-051** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-052** (adjudication_replay): engine/risk_radar.py
- **CTX-053** (adjudication_replay): engine/market_drivers.py
- **CTX-056** (adjudication_replay): research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md
- **CTX-059** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-060** (adjudication_replay): research/CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md
- **CTX-066** (research): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-067** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-068** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-069** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-070** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-071** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-072** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-073** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-074** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-075** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-076** (negative_control): no_answer: returned 30 results; expected honest null

---

_Nulls printed per house epistemics. No content excerpts from private projects._

## Eval run v6 — 2026-08-28 06:39 UTC

### Index SHAs

- `macro-dashboard`: index `2e042a6ab409`, repo `2e042a6ab409` (clean)

### Scope: shared-visibility rows only

Rows evaluated: **76**  Pass: **42**  Global Recall@10: **55.3%**  Not-evaluated: **0**

### Gate results

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Global Recall@10 | ≥90% | **FAIL** | 55.3% |
| adjudication_replay Recall@10 | ≥90% | **FAIL** | 42.9% (6/14) |
| Governance A0/A1 precision (true) | ≥95% | **FAIL** | 38.2% (21/55) |
| Negative-control (no-answer) accuracy | ≥90% | **FAIL** | 0.0% (0/8) |

_Informational (no gate) — Governance recall (row pass-rate): 70.0% (7/10)._

### Not evaluated

_None._

### Latency

| p50 | p95 |
|-----|-----|
| 1204ms | 2296ms |

### Per-family Recall@10

| Family | Pass | Fail | Recall@10 |
|--------|------|------|-----------|
| adjudication_replay | 6 | 8 | 42.9% |
| architecture | 3 | 4 | 42.9% |
| code | 5 | 3 | 62.5% |
| comprehension | 8 | 0 | 100.0% |
| contract | 4 | 0 | 100.0% |
| current_state | 2 | 1 | 66.7% |
| freshness | 1 | 0 | 100.0% |
| governance | 7 | 3 | 70.0% |
| location | 4 | 3 | 57.1% |
| negative_control | 0 | 8 | 0.0% |
| operations | 0 | 1 | 0.0% |
| research | 2 | 3 | 40.0% |

### Cross-repo block (private-visibility rows)

_NOT-EVALUATED: --include-private not set. Re-run with --include-private to evaluate cross-repo rows._

### Failed rows

34 failed:

- **CTX-002** (location): scripts/build_active_build_map.py
- **CTX-003** (code): engine/market_drivers.py
- **CTX-004** (code): engine/neuralweb/query.py
- **CTX-006** (location): scripts/build_market_structure_page.py
- **CTX-007** (governance): scripts/check_blocklist_drift.py
- **CTX-010** (governance): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-012** (governance): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-025** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-041** (research): research/DO_NOT_REBUILD.md
- **CTX-042** (research): research/DO_NOT_REBUILD.md
- **CTX-044** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-046** (location): config/synapse.yml, docs/SIGNAL_BUS.md
- **CTX-047** (code): scripts/check_template_site_sync.py
- **CTX-049** (operations): scripts/check_blocklist_drift.py
- **CTX-050** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-051** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-052** (adjudication_replay): engine/risk_radar.py
- **CTX-053** (adjudication_replay): engine/market_drivers.py
- **CTX-056** (adjudication_replay): research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md
- **CTX-057** (adjudication_replay): research/NARRATIVE_IGNITION_MASTERPLAN_BY_FABLE.md
- **CTX-059** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-060** (adjudication_replay): research/CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md
- **CTX-063** (architecture): engine/metabolism/recall.py
- **CTX-066** (research): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-067** (current_state): scripts/context_index_query.py
- **CTX-068** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-070** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-071** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-072** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-073** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-074** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-075** (negative_control): no_answer: returned 10 results; expected honest null
- **CTX-076** (negative_control): no_answer: returned 24 results; expected honest null
- **CTX-082** (adjudication_replay): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md

---

_Nulls printed per house epistemics. No content excerpts from private projects._

## Eval run v7 — 2026-08-28 06:41 UTC

### Index SHAs

- `macro-dashboard`: index `2e042a6ab409`, repo `2e042a6ab409` (dirty)
- `terminal`: index `b1b21a17f843`, repo `b1b21a17f843` (clean)
- `mastermind`: index `e2092cb62355`, repo `e2092cb62355` (clean)

### Scope: all rows including private

Rows evaluated: **104**  Pass: **46**  Global Recall@10: **44.2%**  Not-evaluated: **0**

### Gate results

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Global Recall@10 | ≥90% | **FAIL** | 44.2% |
| adjudication_replay Recall@10 | ≥90% | **FAIL** | 37.5% (6/16) |
| Governance A0/A1 precision (true) | ≥95% | **FAIL** | 37.7% (23/61) |
| Negative-control (no-answer) accuracy | ≥90% | **FAIL** | 0.0% (0/9) |

_Informational (no gate) — Governance recall (row pass-rate): 72.7% (8/11)._

### Not evaluated

_None._

### Latency

| p50 | p95 |
|-----|-----|
| 1249ms | 2315ms |

### Per-family Recall@10

| Family | Pass | Fail | Recall@10 |
|--------|------|------|-----------|
| adjudication_replay | 6 | 10 | 37.5% |
| architecture | 3 | 5 | 37.5% |
| code | 5 | 3 | 62.5% |
| comprehension | 8 | 0 | 100.0% |
| contract | 4 | 4 | 50.0% |
| current_state | 2 | 4 | 33.3% |
| freshness | 1 | 0 | 100.0% |
| gotcha | 1 | 9 | 10.0% |
| governance | 8 | 3 | 72.7% |
| location | 6 | 6 | 50.0% |
| negative_control | 0 | 9 | 0.0% |
| operations | 0 | 1 | 0.0% |
| research | 2 | 4 | 33.3% |

### Cross-repo block (private-visibility rows)

Evaluated: 28  Pass: 4  Recall@10: 14.3%

_Note: paths only; no content excerpts from external projects per CXI-R14._

### Failed rows

58 failed:

- **CTX-002** (location): scripts/build_active_build_map.py
- **CTX-003** (code): engine/market_drivers.py
- **CTX-004** (code): engine/neuralweb/query.py
- **CTX-005** (gotcha): memory://nav-aurora-glass-system.md
- **CTX-006** (location): scripts/build_market_structure_page.py
- **CTX-007** (governance): scripts/check_blocklist_drift.py
- **CTX-010** (governance): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-012** (governance): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-018** (current_state): memory://prophet-program.md
- **CTX-025** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-026** (architecture): memory://nw-lobe-terminology-map-vs-observatory.md
- **CTX-027** (gotcha): memory://kernel-panel-frozen-spine-dtype.md
- **CTX-028** (gotcha): memory://render-guards-pytest9-misdiagnosis.md
- **CTX-029** (gotcha): memory://basket-ohlcv-membership-lane-freeze.md
- **CTX-030** (gotcha): memory://mx5-hash-open-heatmap-race.md
- **CTX-031** (gotcha): memory://macro-page-load-perf.md
- **CTX-032** (gotcha): memory://mm-data-guard-lessons.md
- **CTX-033** (gotcha): memory://nav-aurora-glass-system.md
- **CTX-034** (location): memory://prophet-program.md
- **CTX-035** (location): memory://nw-lobe-terminology-map-vs-observatory.md
- **CTX-040** (research): memory://gbp-sonia-splice-fred-tripwire.md
- **CTX-041** (research): research/DO_NOT_REBUILD.md
- **CTX-042** (research): research/DO_NOT_REBUILD.md
- **CTX-044** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-046** (location): config/synapse.yml, docs/SIGNAL_BUS.md
- **CTX-047** (code): scripts/check_template_site_sync.py
- **CTX-049** (operations): scripts/check_blocklist_drift.py
- **CTX-050** (architecture): research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md
- **CTX-051** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-052** (adjudication_replay): engine/risk_radar.py
- **CTX-053** (adjudication_replay): engine/market_drivers.py
- **CTX-056** (adjudication_replay): research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md
- **CTX-057** (adjudication_replay): research/NARRATIVE_IGNITION_MASTERPLAN_BY_FABLE.md
- **CTX-059** (adjudication_replay): research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-060** (adjudication_replay): research/CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md
- **CTX-062** (current_state): memory://prophet-program.md
- **CTX-063** (architecture): engine/metabolism/recall.py
- **CTX-065** (location): memory://marketing-lobe-genesis.md
- **CTX-066** (research): research/DO_NOT_REBUILD.md, research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md
- **CTX-067** (current_state): scripts/context_index_query.py
- **CTX-068** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-070** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-071** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-072** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-073** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-074** (negative_control): no_answer: returned 30 results; expected honest null
- **CTX-075** (negative_control): no_answer: returned 10 results; expected honest null
- **CTX-076** (negative_control): no_answer: returned 24 results; expected honest null
- **CTX-082** (adjudication_replay): research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md
- **CTX-083** (adjudication_replay): repo://terminal/indicator_engine/README.md
- **CTX-084** (adjudication_replay): repo://terminal/hub/hub.js
- **CTX-086** (contract): repo://terminal/contracts/indicator.v1.schema.json, repo://terminal/contracts/backtest_result.v1.schema.json
- **CTX-087** (contract): repo://terminal/signal_layer/contracts.py
- **CTX-088** (contract): repo://mastermind/brain/rotation_intake.py
- **CTX-092** (gotcha): repo://mastermind/docs/case_studies/2026-06-22-avgo-nvda-override-postmortem.md
- **CTX-094** (contract): repo://terminal/contracts/samples/NVDA.backtest.json
- **CTX-095** (current_state): repo://terminal/terminal/lib/portfolio.ts
- **CTX-096** (negative_control): no_answer: returned 30 results; expected honest null

---

_Nulls printed per house epistemics. No content excerpts from private projects._
