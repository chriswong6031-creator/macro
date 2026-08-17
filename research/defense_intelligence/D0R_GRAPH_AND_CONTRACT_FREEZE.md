# D0R Workstream F — Graph, temporal semantics, contracts, and ownership freeze

**Objective:** freeze the *minimum* D1–D4 contracts. Do not freeze every V3 field in code. No live migration in D0R.

## F2. Identity graph (minimum)

| Node | Canonical id | Source-native | Notes |
|---|---|---|---|
| Listed issuer | Stock Identity `central:TICKER` | ticker, exchange, share class | **Identity owner** — do not mint a defense ticker |
| Legal entity | `legal:{issuer}:{slug}` | CIK, LEI if present | Ex.21 / 10-K |
| Recipient | UEI primary; CAGE optional | USAspending `recipient_hash`/UEI | CAGE still absent on IRDM path |
| Award | USAspending generated award id | PIID + agency | `CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-` |
| Action/mod | transaction unique id | `CONT_TX_…P00032…` | versioned |
| Program/platform | D5+; **null allowed** | PE, MDS, program name | `major_program` null on IRDM award is honest |
| Budget PE | D1/D5 | PE code + FY | artifact missing live |
| Facility / supplier | D8+ | CAGE, plant | not in D1 |
| Event | `govws-*` / `grc1-*` | content_id | workspace vs candidate contracts stay distinct |

**Ownership:** percent edges + `valid_from`/`valid_to`. JV/consortium: separate node type; do not squash into the prime. IRDM example (proven): UEI `S77SW52LCR57` → `legal:irdm:iridium-government-services-llc` → wholly_owned `legal:irdm:iridium-communications-inc` → `central:IRDM`. Graph remains **defense19-v1**. `#5424` defense20-v1 is not live (`DNR:LAW-REVIEWED-MANIFEST-CENSUS`).

**Corrections:** invalidate with predecessor id; never overwrite receipts. **Rights/authority:** every payload keeps display/context_only flags; `can_rank/gate/size/entry/execute=false`.

## F3. Temporal freeze

| Clock | Meaning | IRDM P00032 |
|---|---|---|
| `action_date` | Official USAspending action date | 2026-05-12 |
| `source_published_at` | When the government first published the row | **absent** — named gap |
| `first_seen_at` / `known_at` | Collector observation | 2026-08-12T23:50:04Z |
| `generated_at` | Artifact bake | 2026-08-13T09:24:42Z |
| `as_of` | Cut date | 2026-08-13 |
| `published_at` | Product publish | **absent** |
| Fiscal / quarter | Company vs US FY | company 10-K FY ≠ DoD FY |
| First tradable | Session after known_at in listing TZ | not computed |
| Recurring option window | Derived POP end | not in this 500-cut as recompete events |

**Law:** `known_at.semantic` must not be `"official"`. Late discovery is a first-class flag and must appear in user title when `action_date` ≪ `known_at`.

## F4. D1–D4 contract minimum (versions stay as currently shipped unless D1 versions)

| Contract | Role | Entitled proof this session |
|---|---|---|
| `company_government_revenue.v1` | Compact + `/latest` | 200 cookie + bearer |
| `government_procurement_workspace.v2` | Change tape | 200; 500 events; bundle `grw2-dd9d7af893a7f3c773909351` |
| `government_revenue_candidate_queue.v1` | Radar API | 200 `total=22` `grcq1-d93ebaf6878402e3be09e490` — **UI still locked** |
| `government_recipient_resolution.v1` | Issuer path | proven on compact/entitled IRDM row |
| Source/evidence pointer | receipt id + sha + URL | P00032 receipt lineage closed |
| Company financial packet | **Earnings/SEC owner** | not a GovRev document |
| Evidence token | Macro+Terminal | existing product URL + event id |
| Health/failure enum | typed states from A | use; do not invent parallel enums |

Bearer vs cookie: D1 must treat them as one user session. Radar must rehydrate on `MDXAuth` change.

## F5. Owner map (one owner)

| Field/artifact | Owner | Consumers | Forbidden duplicate |
|---|---|---|---|
| Ticker / listing / splits | Stock Identity | all | defense ticker table |
| UEI→legal→issuer | Reviewed recipient graph | GovRev, dossiers | a second reviewed graph |
| Award/action facts | GovRev collectors | tape, radar | “defense USAspending” fork |
| SAM notices | GovRev opportunities | Opportunities tab | GovTribe clone |
| Budget PE | GovRev budget_program (missing) | Budget tab | spreadsheet PE in JS |
| Filings/transcripts/guidance | Earnings/SEC | dossier, divergence | defense 10-K store |
| Estimates | licensed owner or null | cockpit | scraped estimates |
| Prices/options/GEX | market owners | dislocation | defense price cache |
| Themes/residuals | Thematic / Prophet residual | theme room | defense ETF score |
| Prophet picks | Prophet | board | GovRev ranker |
| Neural Web context | NW mastermind_context | chat | LLM-originated signals |
| Auth | paywall `site_full` | APIs, Caddy JSON | a second entitlement |

## F6. Migration / no-rebuild

| Artifact | Ruling |
|---|---|
| `government_revenue.html` underscore route | **canonical** |
| Compact `#gov-data` teaser | **remain** for anonymous; do not pretend it is the desk |
| Workspace v2 500-cap | **canonical until D3** versions a longer tape; do not silently raise cap in D0R |
| defense19-v1 graph | **canonical live** until `#5424` merges |
| Candidate queue v1 | **canonical API**; UI hydrate is D1 |
| Budget graph files | **missing — build or stop advertising** |
| `shadow_context.py` / `sbir_progression.py` | **historical/dark** — do not rebuild as secret scores |
| `#5424` defense20-v1 | **open; not live** |
| Frontend scores | **rejected** |

Golden example for any schema discussion: **HC101319C0006 P00032 / IRDM** — official action, late known_at, reviewed path, entitled tape row *and* balance-changed sibling, non-material vs IRDM market cap. If a proposed field cannot be filled on this case, it is not D1-minimum.
