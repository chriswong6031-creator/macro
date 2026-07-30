# Live Intraday Dashboard — production master plan

**Date:** 2026-07-29
**Status:** ratified architecture + Phase 0 implementation
**Extends:** `research/LIVE_DATA_ARCHITECTURE.md`,
`research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md`, and
`docs/VPS_LIVE_ORCHESTRATION.md`
**Does not create:** a second forecast engine, a second forward ledger, or a
Git-backed tick stream

## 0. Executive ruling

The dashboard should remain a hybrid product:

- committed HTML is the fast, resilient shell and nightly research baseline;
- an always-on live data plane owns facts whose useful life is measured in
  seconds or minutes;
- small browser hydrators update only those high-change islands;
- a same-origin API/SSE layer becomes the stable contract as the number of live
  islands grows;
- canonical vintages, research scores, allocations and forward ledgers remain
  single-writer nightly products.

A full SPA rewrite is not the remedy. React, Next or another application shell
would still show stale FOMC data if no source adapter advances the event state.
The immediate defect was missing event semantics and data plumbing, not HTML.

The rule for every surface is:

> If its acceptable staleness is shorter than one day, it must read a runtime
> contract with an explicit source timestamp, freshness state and fallback. It
> must not wait for a site regeneration.

GitHub Actions is not part of the release-time critical path. It remains useful
for CI, nightly canonical work, reconciliation and an external dead-man check.

## 1. Incident: the 2026-07-29 FOMC failure

At 14:00 ET the Federal Reserve published its decision. At roughly 20:00 ET the
public macro page still called the decision upcoming and continued to tell users
to expect announcement noise.

The evidence isolated five independent defects:

1. `engine/event_calendar.py` filtered by calendar date, not the scheduled ET
   timestamp. A 14:00 event remained upcoming until midnight.
2. A render more than four hours after the release reproduced the stale copy.
   More frequent HTML generation alone therefore could not fix the semantics.
3. The one-minute VPS publication watcher was healthy but had no FOMC adapter
   and no deterministic actual-value parser.
4. The browser used the UTC date. At 20:00 EDT, UTC had already rolled to the
   following day, so a July 29 result would have been filtered out.
5. The public page loaded a public JavaScript client, but its live JSON endpoint
   was registration-gated. Anonymous users received a 401 that the client
   silently ignored.

The official statement was available on the Fed site at the scheduled time. It
held the target range at 3.50%–3.75% on a 9–3 vote; three dissenters preferred a
25 bp increase. The Fed monetary RSS metadata was observed about 15 seconds
after schedule. That observation is not a formal Fed SLA, but it proves the
source was not the multi-hour bottleneck.

## 2. Product freshness contract

“Live” must describe the age of the underlying fact, not how recently a JSON
file was rewritten.

| Product object | Target cadence | User-visible freshness | Authority |
|---|---:|---|---|
| High-impact official release state | 10–60 sec around release | official source time + observed time | official agency |
| Release actual | 10–120 sec | actual/previous/revision/units + source | official agency |
| Consensus | streaming or 1 min | provider time + license label | licensed calendar vendor |
| Display quotes today | 1 min transport | vendor trade time and delay label | current vendor |
| Professional real-time quotes | streaming | exchange time + entitlement | licensed redistributor |
| Market State fast leaves | 1–2 min | provisional/intraday badge | live price plane |
| Breadth/flow/technical leaves | 1–5 min | source time + coverage | live price/flow plane |
| Official news and filings | 1–3 min | published/observed time | source document |
| Intraday bars | 1–5 min | final/provisional bar state | licensed market feed |
| Regime, allocation, conviction | nightly by design | close date + built time | slow brain |
| Vintage history and scoreboards | nightly | vintage and reconciliation time | canonical writer |
| 13F, economic history, long research | source cadence/nightly | source-specific | canonical writer |

The current quote plane is fresh transport over data that can be approximately
15 minutes delayed. It must remain labeled delayed. A professional “real-time”
claim requires a redistribution-capable market-data contract; polling faster
cannot manufacture an entitlement.

## 3. Target architecture

```text
 Official schedules      Official feeds/pages      Licensed streams
 Fed/BLS/BEA/Census  →   source adapters       ←   calendar/market vendor
          │                       │                         │
          └────────── release-window orchestrator ─────────┘
                                  │
                        immutable source receipt
                                  │
                    deterministic parser + validator
                                  │
                   current event/fact state + revisions
                                  │
              atomic JSON now → API/SSE as scale requires it
                                  │
             static dashboard shell + hydrated live islands
                                  │
                  nightly canonical reconciliation/ledger
```

### 3.1 Four planes, one product

1. **Slow research plane**
   - Nightly models, regimes, scoreboards, forecasts, vintage history and HTML.
   - Stable and hysteresis-gated. It must not react to every tick.

2. **Official event plane**
   - Schedules, lifecycle, source receipts and deterministic release facts.
   - Independent of quotes and Git.
   - At scheduled time the state advances even if the publisher is late.

3. **Market live plane**
   - Quotes, bars, breadth, flow and fast derived leaves.
   - Every value carries exchange/provider time, observed time, delay and
     entitlement.

4. **Delivery/control plane**
   - Same-origin no-store JSON initially; BFF plus SSE/WebSocket for fan-out and
     deltas later.
   - Freshness registry, health, metrics, circuit breakers and access policy.

### 3.2 Why the shell remains static

The shell provides excellent availability, cacheability, SEO and a last-known
good view. Live modules progressively enhance it. If a runtime source fails,
the page still loads and clearly labels the stale island. This is more resilient
than making the whole page dependent on one application server.

A route should move to a fully client-rendered application only when its
interaction/state complexity—not its data cadence—requires that migration.

## 4. Canonical event and fact contract

All event time calculations use `America/New_York`. UTC is used for transport
timestamps. Host-local `date.today()` and browser UTC date slicing are banned
from US release lifecycle logic.

Lifecycle:

```text
scheduled → watching → awaiting_publication → published → reconciled
                                      ├────→ published_unparsed
                                      └────→ verification_delayed
published → revised
```

Once the scheduled ET timestamp passes, the UI may say “awaiting official
release,” but can never continue to say “upcoming.”

Minimum v2 event packet:

```json
{
  "event_id": "fomc:2026-07-29",
  "type": "FOMC",
  "scheduled_at": "2026-07-29T14:00:00-04:00",
  "status": "published",
  "source_released_at": "2026-07-29T14:00:00-04:00",
  "observed_at": "2026-07-29T18:00:15Z",
  "publisher": "Board of Governors of the Federal Reserve System",
  "source_url": "https://www.federalreserve.gov/...",
  "source_sha256": "...",
  "parser": {"name": "fomc_statement", "version": 1},
  "actual": {
    "kind": "policy_rate",
    "action": "hold",
    "target_low": 3.5,
    "target_high": 3.75,
    "unit": "percent",
    "vote_for": 9,
    "vote_against": 3
  },
  "canonical_reconciliation": "nightly"
}
```

Consensus, forecast and official actual are separate namespaces. No UI may
label an internal benchmark “consensus.” AI may summarize a verified packet,
but may never originate or alter the actual.

## 5. Source hierarchy

### 5.1 Official authority lane

- **Federal Reserve:** monetary RSS plus the official statement and
  implementation note. No authentication is documented.
- **BEA:** release schedule JSON/ICS, RSS and keyed API. Respect documented
  quotas and `Retry-After`.
- **BLS:** schedule ICS, release feeds/pages and keyed v2 API. Batch requests,
  use an identifiable user agent and avoid aggressive bot cadence.
- **Census:** economic-indicator calendar/RSS and keyed EITS API. Preserve
  official precision and the required non-endorsement language.
- **Treasury/NY Fed:** authoritative daily/reference rates, but not substitutes
  for live Treasury or Fed-funds futures.

FRED remains a history/QA and vintage source, not the release trigger. Source
release dates do not guarantee simultaneous FRED availability, and public
redistribution requires terms review.

### 5.2 Commercial enrichment lane

Run an RFP for a licensed economic-calendar provider. The contract must
explicitly cover public display, storage, derived surprises, history and
redistribution. A Trading Economics Enterprise-class stream is a candidate
because it exposes event IDs, actual, previous, revision, consensus and units.
Official values remain authoritative if the vendor disagrees.

Run a separate market-data RFP for customer-facing real-time US equities,
Treasury futures, SOFR/Fed-funds futures and options. Exchange display fees and
redistribution rights are a launch dependency, not an engineering footnote.

## 6. Runtime behavior

### 6.1 Polling policy

- schedules: synchronize 1–4 times per day;
- normal source heartbeat: every 5–15 minutes with conditional requests;
- T−30 seconds through T+3 minutes: every 10–15 seconds where source terms
  permit;
- T+3 through T+15 minutes: every 30 seconds;
- then exponential backoff through the reconciliation window;
- add jitter, honor `ETag`, `Last-Modified`, 429 and `Retry-After`.

Phase 0 uses the already-running one-minute fast lane, yielding roughly
one-timer-tick detection. A dedicated event service is the next latency step;
quote work must never delay an official release fetch.

### 6.2 Persistence

- immutable raw receipt keyed by source URL, event ID, observed time and hash;
- append-only revision history in R2/Postgres;
- atomic current-state JSON for browser reads;
- nightly import to the existing canonical release/vintage stores;
- never write forward ledgers from the intraday process.

### 6.3 Browser delivery

Phase 0 polls same-origin JSON. When event breadth grows, move fan-out to:

- `GET /api/live/events?since=<cursor>` for snapshots/recovery;
- `GET /api/live/stream` using SSE for low-frequency official/news deltas;
- WebSocket only where high-frequency bidirectional or market-tick behavior
  justifies its connection cost.

The event hydrator updates every dependent surface from one packet so the page
cannot say “released” in one place and “upcoming” in another.

## 7. Site-wide live-island map

### Macro dashboard

- Events rail/dialog: lifecycle, actual, source and observed time.
- Release Radar: nightly projection plus live actual/previous/revision and
  honest surprise versus a licensed consensus or labeled benchmark.
- Fed Path: live official target immediately; separate source timestamps for
  policy target, ZQ/SOFR futures, dots and statement.
- Market State: keep the existing provisional live score/path; add an explicit
  “intraday provisional” endpoint date and per-leg freshness.
- Alerts/What to do next: retire prospective event-risk copy at publication.
- Macro News: official source receipts first, synthesis second.

### US, Canada, HK, China and international dashboards

- prices, breadth and technical leaves hydrate at their warranted cadence;
- slow scores/verdicts remain nightly and visibly dated;
- exchange/session/holiday calendars determine staleness;
- no region silently inherits a US timezone or vendor entitlement.

### Rates, commodities, FX, crypto and options

- live spot/futures fields require source timestamps and license labels;
- official reference rates are not presented as live market yields;
- derivative/open-interest/GEX surfaces use the cadence of the licensed
  underlying source, not a guessed “real-time” badge.

### Research and AI surfaces

- Neural Web/Mastermind can cite current verified fact packets;
- LLM synthesis is invalidated/rebuilt when its cited inputs change;
- every generated sentence retains the source packet IDs and as-of times;
- a stale synthesis never overwrites a newer deterministic fact.

## 8. Freshness registry and UI law

Phase 2 publishes `live/freshness.json`:

```json
{
  "schema": "freshness.v1",
  "built": "2026-07-29T18:01:00Z",
  "objects": {
    "events": {
      "source_asof": "2026-07-29T18:00:15Z",
      "observed_at": "2026-07-29T18:00:16Z",
      "published_at": "2026-07-29T18:00:17Z",
      "target_age_sec": 60,
      "state": "fresh",
      "coverage": 1.0
    }
  }
}
```

Every live island has exactly three user states:

- **Fresh:** normal presentation with source/as-of details available.
- **Delayed:** last-known value remains visible with a prominent age/reason.
- **Unavailable:** no value is shown; the fallback never masquerades as live.

“Updated now” based only on file mtime is prohibited.

## 9. Reliability and observability

Initial SLOs:

- high-impact official detection: p95 under 60 seconds, p99 under 120 seconds;
- deterministic core actual: p95 under 120 seconds;
- browser visibility after atomic publish: p95 under 60 seconds;
- event plane monthly availability: 99.9%;
- no past high-impact event shown as upcoming: 100%;
- no unlicensed value labeled real-time: 100%.

Metrics:

- expected events versus adapter coverage;
- polls, conditional hits, source latency and rate-limit responses;
- scheduled-to-source, source-to-observed, observed-to-published and
  published-to-browser lag;
- parser failures and unknown-format hashes;
- stale/late lifecycle count;
- browser fetch success by endpoint/version;
- canonical reconciliation lag and discrepancies.

Alerts:

- a high-impact event lacks an adapter seven days before schedule;
- state remains `scheduled` after its timestamp;
- official result remains unavailable at T+2 minutes;
- parser fails on a changed official document;
- v2 payload is fresh by mtime but semantically empty;
- client endpoint returns auth or cache-policy errors;
- current and canonical values disagree after reconciliation.

Store replayable fixtures for every parser. A format change pages an operator
and presents “official publication detected; values verifying” to users.

## 10. Security, access and compliance

- Public event state contains only public official facts and provenance.
- Proprietary forecasts, ranked signals and user data retain their existing
  registration/tier boundaries.
- Source URLs are allowlisted in the browser before becoming links.
- JSON is rendered through DOM `textContent`; source strings are never injected
  as HTML.
- Raw receipts are checksummed and immutable.
- API responses are schema-validated, no-store where current, and bounded in
  size.
- Agency attribution, non-endorsement and logo/seal rules are documented per
  adapter.
- Vendor values do not launch publicly until counsel/procurement confirms the
  exact redistribution rights.

## 11. GitHub Actions reduction

The repo currently creates many scheduled workflow runs even when VPS-primary
guards skip the jobs. The skip guard saves compute, not scheduler queue slots.

After each VPS consumer is verified:

1. make legacy intraday fastpath/breadth/bars/BTC schedules manual-only;
2. retire scheduled quote commits after every live consumer reads the VPS plane;
3. move press-feed cadence to its existing VPS service after ownership tests;
4. keep one low-frequency external dead-man monitor;
5. constrain unrelated Worker builds to relevant paths;
6. never commit ephemeral ticks or event states to `main`.

CI and nightly research remain on Actions. User freshness does not.

## 12. Delivery phases

### Phase 0 — FOMC-grade event foundation (this change)

- add FOMC to the one-minute official watcher;
- resolve the deterministic Fed statement URL;
- parse target range, action, vote and dissent preference without AI;
- publish the v2 ET-aware event lifecycle;
- patch the calendar, event rail, Release Radar, “Where next” and stale
  prospective copy from one sidecar;
- expose the official-fact sidecar publicly with no-store;
- retain outcomes for 24 hours in the client;
- make health semantic: alert on T+2 publication lag, not just file age;
- preserve nightly canonical ownership and fail-open page behavior.

Acceptance: a fixture and a live official statement both produce
“Fed holds at 3.50%–3.75%, 9–3” and the event cannot remain upcoming after
14:00 ET.

### Phase 1 — complete official release adapters

- CPI/core CPI, PPI, payrolls/unemployment/earnings, claims, GDP, PCE,
  retail sales, ISM, JOLTS and Treasury auctions;
- official actual, previous/revised previous, units and period;
- immutable receipts/replay and parser-version registry;
- official schedule sync removes annual hard-coded date risk;
- reconcile into the existing Macro Release Intelligence store nightly.

Acceptance: every high-impact calendar event has an adapter or an explicit
unsupported badge seven days before release; p95 actual latency is under two
minutes over a full release cycle.

### Phase 2 — freshness control plane

- publish the site-wide freshness registry;
- shared freshness/status UI component;
- source-level SLO dashboards and alerts;
- synthetic anonymous checks for every public runtime endpoint;
- canonical ET clock utility used by build, event and browser contracts;
- component-level timestamps for Fed Path and Market State.

Acceptance: automated checks fail on fresh-but-empty payloads, auth mismatches,
timezone rollover and stale synthesis.

### Phase 3 — broaden live islands

- hydrate the highest-value macro, equities, rates, commodities, FX, crypto and
  regional surfaces;
- separate fast leaves from slow score ownership in every contract;
- propagate current fact packets into Neural Web with source receipts;
- add current-event notifications and optional user watchlists;
- explicitly label every delayed feed.

Acceptance: each Tier-1 page has a signed-off cadence map and no field exceeds
its product freshness budget silently.

### Phase 4 — event service and streaming delivery

- split event polling from the one-minute quote lane;
- release-window scheduler at source-safe 10–15 second cadence;
- durable event/revision store;
- same-origin BFF, SSE cursor recovery and backpressure;
- replay, idempotency and blue/green deployment;
- mobile/push hooks after notification preference and compliance work.

Acceptance: p95 official detection under 30 seconds where source availability
permits, no duplicate notifications, and snapshot recovery after disconnect.

### Phase 5 — professional entitlements

- contract economic-calendar consensus;
- contract real-time redistribution for required exchanges/assets;
- switch providers behind stable event/quote contracts;
- entitlement-aware API and subscriber delivery;
- document display fees, delayed fallbacks and jurisdiction coverage.

Acceptance: legal approval, provider failover exercise, exchange auditability
and external latency/coverage benchmark.

## 13. Rollout and rollback

For each adapter:

1. replay fixtures and historical official pages;
2. shadow-publish internally without browser consumption;
3. compare source facts and nightly reconciliation;
4. enable one public island behind a contract flag;
5. observe at least one live release;
6. expand dependent surfaces;
7. retain the old client contract for one release cycle.

Rollback disables the hydrator or source adapter. The committed nightly page
remains the last-known-good shell. Runtime rollback never deletes canonical
history, and the intraday process has no authority to modify the forward
ledger.

## 14. Definition of done

The program is complete when:

- no high-impact past event is labeled upcoming;
- all Tier-1 fields expose their true source age and delay;
- official releases reach users inside the documented SLO;
- real-time claims are licensed and measured from source timestamps;
- GitHub/deploy queues cannot delay intraday facts;
- live failures degrade visibly and never silently substitute stale data;
- nightly reconciliation is deterministic, audited and single-writer;
- the same fact packet updates all dependent site surfaces consistently.
