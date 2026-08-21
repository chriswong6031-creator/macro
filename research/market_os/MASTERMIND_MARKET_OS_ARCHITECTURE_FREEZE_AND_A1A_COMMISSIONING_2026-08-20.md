# Mastermind Market OS
## Architecture Freeze and A1A Commissioning Record

**Date:** 2026-08-20  
**Chairman:** Chris Wong  
**Product owner:** Sol, AI CEO  
**Program operator:** Fable  
**Repositories:** Macro + Terminal  
**Status:** architecture frozen through Turn 6; M0 records landing; A1A is the only next runtime wave

---

# 1. Outcome contract

Mastermind Market OS is the free flagship system that makes Mastermind the canonical
center of a user's investing life.

The user moves through one uninterrupted loop:

```text
Discover -> investigate -> track -> understand personal impact -> return when something changes
```

The system is complete only when a self-directed investor can answer:

| Time | Required answer |
|---|---|
| 10 seconds | What changed, and where should I look? |
| 1 minute on a security | What is it doing, what changed, what is the opportunity context, what is the risk, and what comes next? |
| 2 minutes on a Portfolio | What are my hidden bets, largest risks, strongest current setups, upcoming catalysts, and material changes? |
| 5–15 minutes | What evidence supports the read, what disagrees, how fresh is it, and where can I investigate? |
| Ongoing | Tell me when the answer materially changes. |

Free provides a complete current-state experience. Paid Mastermind sells continuous
monitoring, deeper history, premium data, calibrated forecasts, research agents, thesis
memory, and user-specific decision policies. Free is not a collection of locked previews.

---

# 2. One product, three lenses

## Market — Discover

Primary question:

> Where should I look?

Required composition:

- universal search and command field;
- What Changed across the market;
- deterministic research-priority board;
- explicit Changed, Opportunity, Risk, Catalyst, event, and owned/watched lenses;
- sectors, themes, breadth, and heatmaps;
- personal overlays;
- change history and resolved events.

## Security — Understand

Primary question:

> What is happening here, why, what may happen next, and what would change the read?

Required composition:

- identity, price, freshness, and owned/watched state;
- shared Decision Spine;
- large Terminal-grade chart;
- key levels and next catalyst;
- source-linked Change Feed;
- setup and risk;
- earnings and management evidence;
- financials, valuation, ownership, options, and positioning;
- personal Portfolio and Watchlist context.

The current earnings-first hierarchy is superseded. Company Intelligence follows the
chart unless the company event is genuinely the dominant current story.

## My Market — Track

Primary question:

> What changed in what I own or follow, and what deserves attention?

My Market contains:

- Overview;
- one canonical Portfolio;
- multiple named Watchlists;
- alerts and change history;
- future brokerage synchronization;
- explicit hypothetical Watchlist basket analysis.

---

# 3. Shared Decision Spine

Every security projection answers the same six questions:

| Axis | Question |
|---|---|
| State | What is it doing? |
| Change | What is newly different? |
| Opportunity | What favorable setup context may remain? |
| Risk | What could reverse, disappoint, or transmit? |
| Catalyst | What comes next? |
| Personal impact | What does it mean to this user? |

These axes remain separate. There is no fused Buy score.

Authority is explicit:

```text
recorded fact
deterministic current state
calibrated forecast
user assumption
unavailable
```

An LLM may retrieve, extract, compare, summarize, explain, and de-escalate. It may not
originate ranks, gates, sizes, signals, forecast probabilities, or naked trade authority.

---

# 4. Canonical intelligence contracts

The logical architecture is frozen around:

```text
security_state.v1
change_event.v1
user_exposure_overlay.v1
portfolio_risk_packet.v1
portfolio_brief.v3
forecast_packet.v1
```

## Security State

The governed public current state of one security. It carries identity, state, change,
opportunity context, risk legs, catalysts, levels, health, authority, freshness, and
evidence. It never contains private user holdings.

Preferred physical publication is an additive `security_state` block inside the existing
per-security stockdata payload, plus a compact universe projection in the existing index.
A second per-ticker truth estate is rejected without measured necessity.

## Change Event

A product projection that says an authoritative domain object changed. It references
qbus/news, Company Event Intelligence, signal histories, identity corrections, and other
domain owners rather than replacing them with a universal event database.

## User Exposure Overlay

The private join between public intelligence and the user's Portfolio/Watchlists. It is
computed request/browser-time and never written to public artifacts, logs, model ledgers,
or analytics.

## Portfolio Risk Packet

A stable contract over the existing risk core. It does not introduce new mathematics.

## Portfolio Brief v3

An additive extension of the one deterministic `engine/portfolio_brief.py` composer.
No second Portfolio-composition engine is authorized.

## Forecast Packet

The only legal carrier of continuation, pullback, upside, downside, volatility, or event
forecasts. No current-context label may be relabeled as probability. Promotion requires
point-in-time replay, baselines, calibration, subgroup stability, forward shadow evidence,
and explicit authority adjudication.

---

# 5. No-rebuild boundaries

Preserve:

- issuer/security/listing identity authority;
- stockdata and existing dossier integrity guards;
- qbus/news ingestion and event identity;
- Company Event Intelligence and `event_workspace.v1`;
- signal and entry-event ledgers;
- `watchlists`, `watchlist_symbols`, and `portfolio_positions`;
- Macro and Terminal adapters over the shared state;
- existing Portfolio risk math;
- `build_portfolio_ctx.py`;
- `portfolio_brief.py`;
- `portfolio_changes.py` privacy law;
- Terminal chart engine.

Reject:

- another Portfolio or Watchlist store;
- Watchlist names inside Portfolio counts or risk;
- a generic universal event database;
- another Portfolio composer;
- a fused Buy/Opportunity score;
- silent equal weighting of a mixed book;
- a naked LLM recommendation layer;
- six hidden risk tabs as the final Portfolio experience;
- giant inline drawers as the final security-inspection pattern;
- infrastructure-only waves called product completion.

---

# 6. Current Portfolio truth defects

Turn 6 verified the following mechanisms on current Macro code.

## Temporary paste is a Watchlist mutation

`watchlist.js::runEntry()` parses the input, calls the Watchlist `add()` path, persists
`ENTERED` separately, and calls `pushCloud()`. It does not create canonical Portfolio
positions.

## Count fallback

`watchlist.js::pfCount()` may return the Watchlist blob length when the Portfolio
controller is unavailable.

## Population union

`market_books.js::buildModel()` constructs market membership from Watchlist symbols union
open Portfolio positions. Existing tests pin this rejected construction.

## Global hidden filter

The same active market predicate can filter Watchlist rows even though the Watchlist
surface does not show that Portfolio market filter.

## Zero/one collapse

`portfolio.js` uses `open.length < 2`, so zero and one positions receive the same copy.

## Authenticated cloud-to-local fork

After an authenticated cloud Portfolio read fails, `watchstore.js` returns the anonymous
local Portfolio and later routes writes locally. This is not an offline outbox.

## Save-state crossover

The page's primary save chip is driven by Watchlist synchronization and is not reliable
Portfolio-write authority.

## Hidden weighting completion

The temporary basket average-fills unspecified sizes. The canonical Portfolio can mix
actual values with equal fallback rows in one distribution.

## Fabricated cluster

When the risk publisher supplies no cluster, the current Portfolio marks the top half by
money as the cluster.

---

# 7. Program sequence

```text
M0   Durable records and collision refresh
A1A  Portfolio Population Truth + State Authority
A1B  Portfolio Fast Start Import
A2   Persistent user weighting and cash assumptions
A3   CSV import and field mapping
A4   My Market collection rail
A5   Universal Add to My Market
A6   Watchlist workspace
B1   Security State vertical slice
B2   Chart-first dossier cockpit
B3   Ticker Change Feed
C1–C6 Market discovery
D1–D9 Portfolio intelligence
E1–E3 Continuous change and alerts
F0–F5 Earned forecast program
```

A1B is blocked until A1A is merged, deployed, and proven on a real account.

---

# 8. A1A observable mission

> The Portfolio surface always describes the canonical Portfolio—in loading, empty,
> one-position, many-position, degraded, and error states—and no Watchlist or temporary
> basket can enter its count, market views, table, save state, or risk.

A1A does not implement canonical paste/import.

---

# 9. A1A private state contract

Recommended pure paired module:

```text
templates/portfolio_state.js
site/portfolio_state.js
```

Private `portfolio_snapshot.v1`:

```json
{
  "schema": "portfolio_snapshot.v1",
  "authority": "local|cloud",
  "read_state": "loading|ready|degraded|error",
  "write_state": "clean|saving|saved|failed|offline_readonly",
  "rows": [],
  "open_rows": [],
  "closed_rows": [],
  "population": "empty|one|many",
  "last_good_at": null,
  "warning": null,
  "weighting": {
    "state": "all_unsized_equal|all_sized_current|all_sized_cost|mixed_unsized_abstain|mixed_price_basis_abstain|cross_currency_partitioned|insufficient",
    "eligible": [],
    "excluded": [],
    "weights": {},
    "basis": "equal_assumption|current_value|entry_cost|none",
    "complete": false,
    "reason": null
  }
}
```

This object is private and must not be logged or published.

---

# 10. A1A authority law

```text
anonymous     -> local Portfolio is canonical
authenticated -> cloud Portfolio is canonical
```

Authenticated cloud failure:

- preserve last-good cloud rows, marked degraded and read-only; or
- show explicit unavailability when no last-good state exists;
- never assert zero;
- never substitute the anonymous local Portfolio;
- never silently write locally;
- never claim Saved.

A durable authenticated offline outbox is a separate future capability.

---

# 11. A1A population and filter law

Required explicit constructors:

```javascript
buildPortfolioModel(rows, priceOf)
buildWatchlistModel(watchSyms)
```

Portfolio market membership uses open Portfolio rows only. Watchlist membership uses the
selected Watchlist only.

A Portfolio market filter must not invisibly filter Watchlists. A1A shows every selected
Watchlist name and adds no new Watchlist filter.

Temporary `ENTERED` data becomes a labeled hypothetical basket:

> Temporary basket — not saved to your Portfolio.

It cannot alter Portfolio count, market views, risk, or save state and cannot mutate a
Watchlist as a side effect.

---

# 12. A1A weighting law

```text
all unsized                -> equal relative weights, explicitly labeled
all current-valued         -> current-value weights
all cost-valued            -> entry-cost weights, explicitly labeled
some sized / some unsized  -> abstain
some current / some cost   -> abstain
different currencies       -> partition before weighting
one modeled position       -> no relationship-risk read
```

For an all-unsized modeled book:

```javascript
FX.setAutoWeights({AAPL: 1, MSFT: 1, NVDA: 1})
```

No fake shares or values are persisted.

No source cluster means no cluster role, bracket, coloring, or explanatory caption.

---

# 13. A1A acceptance

Required live scene:

```text
Watchlist: at least 12 names across several markets
Portfolio: 0 canonical positions
```

The live page must show:

- Portfolio count 0 everywhere;
- no Portfolio market populated by Watchlists;
- no Watchlist name in Portfolio risk;
- all Watchlist rows still visible;
- no hidden Watchlist market filter;
- no false Saved state.

Then:

1. add one canonical position and verify the one-position state;
2. add two unsized positions and verify equal assumption;
3. size only one and verify mixed-sizing abstention;
4. block cloud Portfolio access after a last-good read and verify degraded/read-only;
5. verify the same cloud rows in Terminal;
6. inspect logs and analytics for private holdings leakage.

Required mutation reds:

- restore population union;
- restore Watchlist count fallback;
- restore the `<2` state branch;
- restore average-filling missing sizes;
- restore mixed actual/equal fallback;
- restore cloud-to-local fallback;
- let Watchlist save drive Portfolio save;
- restore top-half cluster fallback;
- apply the Portfolio market filter to Watchlists;
- combine facts across modes.

Green CI without production state round-trip is not acceptance.

---

# 14. A1B gate

A1B later owns:

- a pure Portfolio paste parser;
- reviewable draft rows;
- exact duplicate behavior;
- stable row identity;
- atomic and idempotent persistence;
- lost-response recovery;
- local-to-cloud fold safety;
- Macro/Terminal conformance.

If explicit stable IDs and atomic batch behavior cannot be proven against the live shared
schema, the operator stops. A loop of ambiguous one-row inserts is not an acceptable
substitute.

---

# 15. Exact next action

After this records PR merges:

1. Fable refreshes current heads, worktrees, Active Build Map, and open PR path collisions.
2. Fable dispatches one A1A builder against the current Macro `main`.
3. The builder ships one PR and stops after production proof.
4. Sol reviews the actual A1A diff and receipts.
5. A1B remains unauthorized until that review passes.