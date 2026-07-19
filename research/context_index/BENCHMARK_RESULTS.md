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
