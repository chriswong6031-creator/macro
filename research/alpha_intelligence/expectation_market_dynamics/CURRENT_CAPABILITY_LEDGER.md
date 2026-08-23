# K3E-0 Current Capability Ledger

**Snapshot base:** Macro `origin/main` `dc7135422f112d6c0c9ab3e08ed0cb2053bedb35`
**Rule:** states below distinguish present bytes, accepted capability, natural
evidence and production operation. Re-census before implementation.

| Capability | Current owner/artifact | State at freeze | K3E treatment |
|---|---|---|---|
| Broad current EPS revision snapshot and PIT accrual | `collectors/equity_revisions.py` → `data/revisions/latest.parquet`, `history.parquet` | `PARTIAL / ACCRUING`; current code selects `+1y` then `0y`, retains derived EPS revision/dispersion and forward-revenue context; history starts recently and natural current row counts must be re-derived by SRC-A1 | Extend this owner lane; preserve every legacy field and consumer meaning |
| Current analyst target/rating snapshot | `collectors/yf_analyst.py` → `data/analyst/targets.parquet` | Built; context-only current snapshot | Reuse owner; do not treat target as EPS/revenue expectation |
| Dated target/rating accrual | `_append_analyst_snapshots()` → `data/narrative/analyst_snapshots.parquet` | Built, append by ticker/date; current fields only | Extend in the same revisions lane or a companion owner artifact; never fork the collector |
| Prospective multi-horizon EPS/revenue raw accrual | yfinance exposes relevant current tables; repo has no accepted raw tape proven by K3E-0 | `NOT_BUILT` | `SRC-A1` first vertical |
| Natural historical Street vintages before collection start | No authoritative owner tape identified | `UNAVAILABLE` | Never reconstruct from today's snapshot; vendor evaluation may close it prospectively/licensed |
| Recommendation-revision display logic | `engine/analyst_revisions.py` and consumers | Built for rating-count change; not EPS/revenue expectation science | Reference only; no hidden conversion into K3E model state |
| Theme revision breadth consumer | `engine/theme_revisions.py` | Built; explicitly emits `INSUFFICIENT_HISTORY` for an immature real PIT derivative and keeps its single-snapshot proxy display-only | SRC-A1 must preserve `latest/history` semantics and parity-test this consumer |
| Earnings event identity/workspace | Earnings owner, `company_event.v1` / `event_workspace.v1` | Existing canonical owner | Join by reference; do not create event identity or lifecycle |
| Financial statement/fundamental revision | FIF and Fundamental Forensics owners | Accepted only to their recorded scope; default issuer providers may remain unavailable | Consume accepted packets only; never route around FIF gates |
| Stock/share-class identity | `WS:STOCK-IDENTITY` | Canonical owner | Resolve identity by reference; GOOG/GOOGL remains a golden negative/control case |
| Price/session response | existing market data and calendar owners | Existing inputs; no K3E response object | Adapter/read-time view only |
| Relative/factor residuals | DRL/residual-alpha owner planes | Existing owner-native outputs with their own estimability | Reference residuals; do not recalculate a rival alpha/residual engine |
| Options-implied context | existing options planes | Existing but output-specific prerequisites vary | Optional typed leg; absent leg yields `UNESTIMABLE`, never proxy imputation |
| Market incorporation science | `MAS-118` / Alpha-E | In progress | Family-specific methods remain there; K3E does not universalize them |
| Common catalyst expectation semantics | `MAS-119` | Backlog | Federation owns common `ExpectationBaseline`; K3E uses owner-native interim types and reconciles later |
| Opportunity Evidence Vector | canonical Alpha `K3-E` | Contract lane, distinct from this freeze | K3E can contribute typed references later; never replace it |
| Evaluation/forward truth | Eval OS and existing ledgers | Canonical owners | Register protocol and outcomes there; no K3E scoreboard |
| Prophet consumption | conditional-fusion / Prophet owners | Governed production plane | Forbidden until separate evaluation/promotion acceptance |
| Market OS display | `WS:MARKET-OS` | Product owner; B1 sequence separately gated | Downstream reference projection only after semantic acceptance |
| K3E expectation surface | none | `NOT_BUILT` | Derived, versioned view; no universal belief store |
| K3E market-dynamics state | none | `NOT_BUILT` | Multi-axis descriptive inference with typed `UNESTIMABLE` |
| K3E production operation | none | `NOT_STARTED` | Architecture acceptance is not production proof |

## State vocabulary

- `NOT_BUILT`: no accepted implementation was found.
- `BUILT_NOT_PROVEN`: bytes/tests exist but natural source or host proof does not.
- `FIXTURE_PROVEN`: deterministic fixtures pass within the stated boundary.
- `NATURALLY_ACCRUING`: scheduled source attempts and observations are receipted.
- `RESEARCH_ACCEPTED`: protocol/result accepted for research use only.
- `PRODUCT_ACCEPTED`: owner accepted a user-facing reference projection.
- `OPERATIONAL`: exact deployed job/host/schedule and fresh natural receipt proven.
- `UNAVAILABLE` / `UNESTIMABLE`: required evidence is absent or insufficient;
  these are not failures to hide.

Nothing in this ledger upgrades a current capability merely because code, CI or
a merged record exists.
