# K3E-0 Owner and Reuse Matrix

| Concern | Canonical owner | K3E may | K3E must not |
|---|---|---|---|
| Raw free EPS/revenue estimate snapshot and its accrual | existing `collectors/equity_revisions.py` → `data/revisions/` owner lane | Add raw multi-horizon EPS/revenue observations compatibly in `SRC-A1` | Widen the separate `collectors/yf_analyst.py` price-target/rating lane, mint a second Yahoo collector/store, overwrite history or infer historical vintages |
| Price-target/rating snapshot history | `collectors/yf_analyst.py` → `data/analyst/targets.parquet`, `data/narrative/analyst_snapshots.parquet` | Reference as a separate context family if later needed | Conflate target/rating observations with EPS/revenue expectations or create a third generic analyst-history plane |
| Common catalyst expectations | `MAS-119` Catalyst Federation | Emit owner-preserving interim observations; later adapt to accepted `ExpectationBaseline` | Declare a universal baseline before MAS-119; own common event semantics |
| Family-specific incorporation | `MAS-118` / Alpha-E | Consume accepted family methods and preserve family identity | Collapse methods into one universal gap/grade |
| Earnings events and documents | Earnings Intelligence owner | Reference stable event/workspace IDs and source clocks | Create a K3E event table, lifecycle or document truth |
| Issuer financial truth | FIF / Fundamental Forensics | Reference accepted packets and correction lineage | Create statement truth, bypass unavailable providers or relabel fixtures as issuer proof |
| Stock/share-class identity | `WS:STOCK-IDENTITY` | Store identity references and resolution receipts | Normalize a rival issuer/security master |
| Price/session calendar | existing market/calendar owners | Read exact owner bars/session ordinals through adapters | Persist a rival price store or fabricate timestamps |
| Relative/factor residuals | DRL/residual-alpha owners | Reference exact residual method/version and its honest nulls | Build a K3E residual-alpha engine or silently substitute raw return |
| Options distributions | options owners | Include an optional owner-backed distribution leg | Treat missing chain/IV prerequisites as flat expectations |
| Opportunity evidence | canonical Alpha `K3-E` | Supply typed, decomposed K3E components after acceptance | Rename/replace K3-E or emit a fused scalar |
| Evaluation and outcomes | Eval OS / current forward ledgers | Register preregistration and outcome references | Create a K3E scoreboard, grader or promotion lifecycle |
| Cross-family ranking and Prophet | conditional fusion / Prophet | Submit a later research proposal through existing gates | Rank, gate, train, originate, size or trade |
| Product composition | Market OS | Offer a reference-only projection after owner acceptance | Create a publication plane or claim product/live proof from research artifacts |
| Agent coordination | Agent OS knowledge plane | Record decisions, waves, evidence and handoffs | Gate/dispatch execution or claim a record proves worker liveness |

## Name boundary

`K3E-0` means this program's architecture freeze. `K3-E` remains the existing
Opportunity Evidence Vector. Code, schema and UI names must use the explicit
`expectation_market_dynamics` family (or a later owner-approved name), never a
bare `k3e` that could overwrite the established lane.

## Composition law

Every K3E object is one of:

1. an owner-native source observation;
2. a deterministic reference/view over owner-native observations;
3. a versioned research inference whose full inputs, method and estimability are
   receipted; or
4. a downstream projection of those references.

There is no fifth category called K3E truth. This is the practical application
of `DEC:MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE` and
`DNR:KILL-FUSED-COMPOSITE`.
