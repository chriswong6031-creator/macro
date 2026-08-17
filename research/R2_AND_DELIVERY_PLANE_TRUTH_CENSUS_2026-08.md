# R2 and Delivery-Plane Truth Census — 2026-08

**Program:** Operation Institutionalize W0 — Open Product, Protected Intelligence

**PR boundary:** W0-A evidence and enforcement only

**As of:** 2026-08-12

**Machine contract:** [`config/r2_delivery_plane_classification.v1.json`](../config/r2_delivery_plane_classification.v1.json)

**Remote mutation:** none

## Verdict

The current Cloudflare R2 development origin is a **mixed-authority public bucket**, not a public-facts plane. Anonymous clients can retrieve commodity chart facts, complete paid products, raw vendor stores, and private operational state through the same hostname. The primary website's entitlement denials are real, but they are not containment while R2, public-repository raw URLs, Terminal `/data`, or legacy fallbacks deliver the protected bytes directly.

The required architecture is a physical and semantic split:

```text
approved public facts / previews
  -> allowlist builder
  -> deliberately public origin

premium product / private operations / vendor raw
  -> private object origin
  -> service-authenticated reader
  -> authoritative entitlement projection
  -> browser receives only its tier's bytes
```

This census contains **106 non-overlapping delivery families** at the level needed to make that split. Their single required classifications are:

| Classification | Count | Meaning in this census |
|---|---:|---|
| `PUBLIC_FACT` | 5 | Candidate for an anonymous allowlist projection; source rights, delay and provenance still bind. |
| `PREMIUM_PRODUCT` | 41 | Sellable differentiated output. Full objects require Essential or Pro delivery. |
| `PRIVATE_OPERATIONAL` | 27 | Internal state, controls, models, telemetry or authority material. No customer tier receives the raw object. |
| `VENDOR_RAW` | 12 | Raw/transformed upstream material. Private service/operator access only unless a separate licensed projection is proved. |
| `UNRESOLVED` | 21 | Field, source-rights, mixed-schema, or unregistered-key audit is incomplete. It fails closed to private. |

The counts are descriptive, not a blanket ACL rule. The JSON registry is normative for producer, source, publisher, consumer, browser exposure, Terminal/server consumer, URL, cache behavior, sensitivity, tier, safe schema, migration dependency and evidence for every row. `required_tier` means the minimum tier allowed to receive the **complete stored family**; any lower-tier view is a separate allowlisted object. Thus Anonymous receives about one approved preview, Free about three plus persistence, Essential the standard current product, and Pro the approved deeper history/research/export. No lower-tier response may carry a hidden paid remainder.

## Evidence boundary

The shared working checkouts were not used as truth and were not modified. Source was archived or inspected from freshly fetched immutable commits:

| Repository | Branch | Audited commit |
|---|---|---|
| Macro Dashboard | `origin/main` | `772c8b36d2a70e9e72f870e76db73cf30c7dfed0` |
| Terminal / charting-app | `origin/master` | `b383d8c3579faeca1cdbcd29063535081aabf35b` |
| Mastermind | `origin/master` | `42ba5c76eb7ce1fdf44f3b44f332928668939df4` |

Before final review, the task branch was rebased onto `origin/main` at `e0ed5f89b9a`. The intervening commits changed generated research/earnings/marketing artifacts, fixtures, public rendering and CI orchestration; none of the pinned delivery-source evidence files changed. The census remains explicitly anchored to the three immutable audited commits above.

Every `repo:path:line` citation in the machine registry is independently pinned. Macro anchors resolve against the audited Git tree and a checked-in whole-file SHA-256/line-count receipt. Terminal and Mastermind anchors resolve against equivalent receipts built from immutable archives at the commits above. Terminal receipts additionally pin the full tracked `public/data` path list, all 38 fixture hashes/content dispositions, the exact ordered `flowSource.r2Key` selector map, eight `TERMINAL_E2E_FIXTURE` production-source occurrences, five additional fixture/test controls, six deployed Alerts Engine R2 mappings and all eight washout aliases across R2, primary static, Macro raw Git and Terminal static. The Mastermind receipt records a bounded zero-result exact-path search across 688 tracked candidates outside research and the declarative contract row; this supports “no active feed reader identified,” not a claim that an impossible dynamic reader cannot exist. CI therefore fails on a missing path, zero/non-numeric/out-of-range line, unreceipted file, changed inventory, or consumer mapping that no longer resolves to exactly one family.

The census combined:

1. static producer/publisher/consumer tracing;
2. every `DEFAULT_DIRS ∪ _DATA_DIRS` family from `scripts/publish_r2.py`;
3. direct R2 writers outside the generic publisher;
4. Macro browser routing from `templates/data_base.js`;
5. Terminal R2, BFF, `/data`, legacy fallback and client-bundle delivery;
6. Mastermind server dependencies;
7. anonymous live `HEAD`/bounded `GET` probes on the primary site, R2 and public repository raw origin.

No bucket listing, credential use, customer-record enumeration, object deletion, ACL change, DNS change or cache purge was performed.

## Decisive live receipts

Anonymous probes ran at approximately `2026-08-12T09:36Z` with no cookie or credential.

| Surface | Anonymous result | What it proves |
|---|---:|---|
| `www.mastermind-x.com/prophet/index.json` | `401`, `Cache-Control: no-store` | Primary-origin full Prophet gate works. |
| `www.mastermind-x.com/live/prophet_live.json` | `401`, `no-store` | Primary-origin live-state gate works. |
| `www.mastermind-x.com/stockdata/SPY.json` | `401`, `no-store` | Primary-origin stockdata gate works. |
| `www.mastermind-x.com/prophet/showcase.json` | `200`, `max-age=300` | Approved delayed showcase remains public. |
| Public R2 `prophet/index.json` | `200`, 813,772 bytes, 140 plans | Full current Prophet is anonymously retrievable from an alternate origin. |
| Public R2 `stockdata/SPY.json` | `200`, 85,479 bytes | Graded stock intelligence bypasses the primary gate. |
| Public R2 `live_flow/feed_current.json` | `200`, 272,932 bytes, 307 events | Exact live options rows are anonymous. |
| Public R2 `options_prophet/index.json` | `200`, 138,803 bytes | Internal shadow/authority material is anonymous. |
| Public R2 `thetadata_eod/_manifest.json` | `200`, 13,126 listed objects | Raw vendor store inventory is anonymous. |
| Public R2 `massive_stock_day/_manifest.json` | `200`, 20,765 listed objects | Raw whole-market store inventory is anonymous. |
| Public repository raw full Prophet index and plan | `200`, `Access-Control-Allow-Origin: *`, `max-age=300` | Site/R2 repair alone cannot contain tracked payloads. |
| Public repository raw options signing gate and tape state | `200`, `max-age=300` | Internal operational state has a second alternate origin. |

Most sampled R2 objects returned `ETag` and `Last-Modified` but **no explicit `Cache-Control`**. `live_flow/prophet_marks.json` was an exception with `public,max-age=15,must-revalidate`. A missing cache header is not containment, and a future private cutover must explicitly invalidate previously public immutable URLs and Terminal's IndexedDB cache.

## Generic `publish_r2` families

`scripts/publish_r2.py:69-132` defines 25 distinct directory roots across `DEFAULT_DIRS` and `_DATA_DIRS`. Data directories resolve from `data/<dir>` and other roots from `site/<dir>`; object keys mirror the relative path. Uploads set Content-Type but not Cache-Control. A full run writes `<dir>/_manifest.json` last. It does **not** prune remote objects missing locally, so moving a writer does not remove already-public bytes.

| Key family | Current class | Tier/default | Browser/consumer truth | Required split |
|---|---|---|---|---|
| `ohlc`, `chinaohlc`, `hkohlc`, `intlohlc`, `canadaohlc` | `PUBLIC_FACT` | Anonymous | Rewritten directly to R2 by `data_base.js`. | Chart-only OHLCV/source/as-of allowlist; keep dossier fields out. |
| `subsectorohlc{,_china,_russell,_nasdaq}` | `PUBLIC_FACT` | Anonymous | Browser-direct synthetic display indices. | Bars plus construction/provenance only; no members/ranks/signals. |
| Per-ticker `*stockdata/<ticker>.json` | `PREMIUM_PRODUCT` | Essential | Browser-direct R2 bypass plus a primary protected alias; Mastermind mirrors full US stockdata. | New public fact object plus 1/3 previews; private full dossier; withdraw both full-object origins. |
| `*stockdata/index.json` | `PREMIUM_PRODUCT` | Essential | Global search receives ladder/state/action fields through R2; the same built file has a primary protected alias. | New identity-only directory schema and cross-origin cutover. |
| `*stockdata/calibration*.json` | `PRIVATE_OPERATIONAL` | Private service | Browser routing includes the R2 directory; the same built control files have primary protected aliases. | Server-only calibration and withdrawal of both full-object origins. |
| Other reserved/future `*stockdata` artifacts | `UNRESOLVED` | Hold private | Generic directory publication grants accidental exposure. | Exact filename registry; CI rejects unknown files. |
| `intraday/**` | `UNRESOLVED` | Hold private | Browser-direct true intraday bars. | Source-rights/delay audit before a chart allowlist. |
| `feeds/event_calendar.json`, `sector_breadth.json` | `PUBLIC_FACT` | Anonymous | Public machine-contract siblings today. | Exact public allowlist with provenance/disclosure. |
| `feeds/risk_radar.json`, `intl_spillover.json`, `subsector_rotation.json` | `PREMIUM_PRODUCT` | Essential | Macro product contract, anonymously reachable. Mastermind declares/venders `site/feeds`; the bounded pinned source search identified no active reader at its audited SHA. | Private contract; optional delayed top-level preview. |
| `feeds/froth_fragility_log.jsonl`, `dislocation_state_log.parquet` | `PREMIUM_PRODUCT` | Pro | Deep history anonymously reachable. | Private history endpoint. |
| `feeds/group_flow_validation_meta.json`, `world_state.json`, `nw_mastermind_context.json`, metadata/manifests | `PRIVATE_OPERATIONAL` | Private service | Full blackboard/authority and inventory plane. | Private server contract; separate sanitized freshness file. |
| New unregistered `feeds/*` | `UNRESOLVED` | Hold private | Would inherit publication from an open-ended directory. | Publisher allowlist and registration test. |
| `hk_stocks_ext/**`, `massive_stock_day/**`, `thetadata_eod/**`, `odds_ohlcv/**` | `VENDOR_RAW` | Operator | Directly addressable raw/deep stores; live Massive/Theta manifests enumerate contents. | Private raw bucket, credentialed restore and exact migration receipt. |
| `stock_personality/**` | `PRIVATE_OPERATIONAL` | Private service | Cross-universe PIT/model panel; configured public prefix, live presence not proved by manifest. | Private research/model store; project only approved label. |
| `oddsmatrix/**` | `PREMIUM_PRODUCT` | Pro | Browser-direct full factor matrix and realized-forward history. | Private matrix; public methodology and one preview. |
| `seasonalitydata/entities/**` | `PUBLIC_FACT` | Anonymous | Explicit existing no-rank/no-forecast public contract. | Retain only descriptive historical-path allowlist and disclosures. |
| `attention/**` | `UNRESOLVED` | Hold private | Public Wikimedia facts are packaged as a full deep research hydration store whose exact browser-safe boundary is not approved. | Register a separate bounded delayed aggregate; preserve hydration/restore role privately. |
| `index_gex_history/**` | `PREMIUM_PRODUCT` | Pro | Direct parquet keys are live; publisher manifest is intentionally absent. | Private history/offsite store; optional delayed current preview. |
| `price_pressure/**` | `PRIVATE_OPERATIONAL` | Private service | Deep event ledger, base rates, completion receipts and restore truth are operational/model state. | Private operational store; any public summary must be a separate allowlisted projection. |

### Manifest caveat

On the 2026-08-12 crawl, manifests returned `200` for 22 configured roots. `hk_stocks_ext` and `stock_personality` manifests returned `404`, which proves only that those manifest keys were absent. `index_gex_history/_manifest.json` also returned `404`, but that publisher deliberately uses `--no-manifest`; direct `SPY.parquet` and `QQQ.parquet` probes returned `200`. Absence of a manifest is never evidence of a private prefix.

## Shared-R2 publishers outside `publish_r2`

| Family | Classification / tier | Current consumers | Safe public boundary | Migration dependency |
|---|---|---|---|---|
| `prophet/index.json` across R2 and primary static | `PREMIUM_PRODUCT` / Essential | Macro's primary alias is protected; Terminal consumes the anonymous R2 key. Mastermind instead reads the Git-vendored `site/prophet/index.json`. | Separate 1-card anonymous and 3-card Free previews; full exact plans never included. | Private product origin, authenticated Terminal BFF, preserve the primary entitlement contract while replacing static bytes, private Mastermind sync and alternate-origin closure. |
| Public-repository `site/prophet/{index,plans,states}` plus primary `/prophet/{plans,states}` | `PREMIUM_PRODUCT` / Essential | Raw Git is anonymous; primary plans/states inherit the site's protected asset boundary. | Existing delayed showcase only. | Stop public tracking, withdraw protected static full plans/states after replacement, and obtain an operator decision for immutable history remediation. |
| Public-repository Prophet ledger/corrections/quarantine/arena state | `PRIVATE_OPERATIONAL` | Prophet services/operators | Aggregated delayed proof only. | Private repo/store and history decision. |
| R2 `live_flow/{prophet_live,prophet_marks}.json` plus primary `/live/prophet_live.json` | `PREMIUM_PRODUCT` / Essential | Terminal uses R2; Macro's same-origin live state is protected and returned `401/no-store`. | Freshness and approved delayed preview only. | Private live gateway; preserve the primary entitlement and short freshness semantics while invalidating public R2 URLs. |
| `prophet_live_armed.json`, `prophet_live_events/**`, observations | `PRIVATE_OPERATIONAL` | Live evaluator/reconciliation | Health-only projection at most. | Private runtime/evidence store. |
| Current `live_flow` tape/heat/tides/tickers/chain heat/enrichment/baselines | `PREMIUM_PRODUCT` / Essential | Terminal BFF/browser fallback, deployed five-minute Alerts Engine and Macro models | Delayed totals/freshness and one approved preview, no exact contract rows. | W0-E private upstream plus service-authenticated BFF, model and Alerts Engine consumers. |
| `live_flow/archive`, events, dated tides, surfaces and daily history | `PREMIUM_PRODUCT` / Pro; raw receipts private | Terminal history/research and deployed Alerts Engine surface conditions | Separate bounded proof only. | Private history/replay endpoint plus service-authenticated Alerts Engine reads. |
| `options_hub` current keys, including root `oi_change.json`, `oi_movers.json`, `hot_contracts.json`, `context.json`, `oi_confirmed.json`, `quad.json`, plus `options_structure/{gex_state,matrix}/**` | `PREMIUM_PRODUCT` / Essential current | Terminal options panels and deployed Alerts Engine | Delayed broad regime/freshness only. | Private options origin plus authenticated Terminal gateway and service-authenticated Alerts Engine. |
| `options_hub/{aggtrend,oi_time}/**` and `gex_history/**` | `PREMIUM_PRODUCT` / Pro | Nine-year/520-session aggregate trend, 18-month/389-row OI history and dated GEX replay | No history rows; separately approved delayed current label only. | Private history origin and Pro-authorized Terminal history endpoint. |
| `options_structure/msc_intraday/**` | `PREMIUM_PRODUCT` / Essential current | Focused quote/selection | Methodology only. | Private options origin; invalidate year-cached URLs. |
| `options_prophet/index.json` across R2, primary static and raw Git | `PRIVATE_OPERATIONAL` | Terminal Options Alpha shadow plus anonymous alternate-origin clients | None before explicit product promotion. | Immediate private move, stop public tracking/static publication, and governance decision before tiering. |
| `flowleaders`, `leaderradar`, `live_flow/flow_idx` | `PREMIUM_PRODUCT` / Essential | Terminal ranking/heatmap | 1/3 preview projections. | Remove R2 and GitHub Pages fallback. |
| `darkpool/eod.json`, `vol/regime.json` | `PREMIUM_PRODUCT` / Essential | Terminal EOD context | Delayed aggregate label only. | Private product origin. |
| Levels, ledger, track record and trust objects | `UNRESOLVED` | Terminal levels/proof | Must split exact levels/history from approved aggregate proof. | Field-by-field audit and raw-repository alias closure. |
| Company intelligence complete stored family | `PREMIUM_PRODUCT` / Pro | Macro/Terminal company views | One Anonymous and three Free previews; a separate Essential current projection. | Private R2 and tier-aware BFF; current Terminal BFF is anonymous. |
| Company theme | `PREMIUM_PRODUCT` / Essential | Macro/Terminal theme view; Terminal BFF reads public R2 after a sign-in-only check | 1/3 theme previews. | Private R2 and plan-aware BFF; sign-in alone is insufficient and `TERMINAL_E2E_FIXTURE=1` bypasses it. |
| Institutional context | `PREMIUM_PRODUCT` / Pro | Terminal signed-in BFF, browser client/live card and company institutional research | Methodology/freshness/coverage only. | Private R2, service-authenticated Terminal read and Pro feature check; `TERMINAL_E2E_FIXTURE=1` currently bypasses sign-in and lineage verification. |
| `factordata/basket_washout_{state,history}.json` across R2, primary static, raw Git and Terminal static | `PRIVATE_OPERATIONAL` / private service | Terminal bridge pullers and signal-layer entry admission | None. | Preserve bridge/admission semantics while replacing every public alias with one authenticated private source; handle immutable Git history under an operator decision. |
| Earnings-call scores | `PREMIUM_PRODUCT` / Pro | Earnings/company intelligence | Approved bounded summary only. | Private research/product plane. |
| Earnings evidence | `UNRESOLVED` / hold private | Narrative/research builders | None until source-rights and object schema are audited. | Private first, then exact projection registry. |
| Earnings story packets | `PREMIUM_PRODUCT` / Pro | Research/Press/member wire | Separately staged public wire only. | Private product store. |
| Earnings story journal | `PRIVATE_OPERATIONAL` | Publication audit/reconciliation | None. | Private operational store. |
| Oracle panels | `PREMIUM_PRODUCT` / Pro | Oracle/Neural Web build services | Separately approved regime preview only. | Private model/product hydration. |
| AI response logs and eval summaries | `PRIVATE_OPERATIONAL` / operator | Admin/evaluation only | None. | Priority private-bucket migration and historical-object handling gate. |
| Host-local commercial-path alert ledger | `PRIVATE_OPERATIONAL` / operator | Sentinel Telegram/Discord/email | None. | Remain host-local; never publish to shared R2 or public Git. |
| Flow model/calibrator artifacts | `PRIVATE_OPERATIONAL` / private service | Flow scoring service | Public model-card methodology only. | Private model registry. |
| Marketing chart PNGs | `PUBLIC_FACT` / Anonymous | Public web/social | Approved PNG only. | Deliberate public-media allowlist. |
| User share snapshots | `UNRESOLVED` / hold private | Public-by-possession share page | Only after explicit share, metadata stripping, retention/delete and paid-overlay policy. | Separate deliberate share-media bucket before blanket ACL closure. |
| Public-repository options controls and accruals | `PRIVATE_OPERATIONAL` / private service | Options/Neural Web/research jobs; anonymous raw Git clients in practice | None; product views must be separately generated. | Stop tracking signing/tape/control state and per-name parquet accruals; preserve point-in-time readers and decide history remediation. |
| Unregistered shared-R2, Macro-repository, Terminal-data and primary-static keys | `UNRESOLVED` / hold private | Unknown until an exact family is added | None. | Ordered default-deny rules; a new key cannot inherit safety from a directory name. |

## The response-log finding

`lib/mastermind_response_log.py` writes one shared-R2 object per Macro or Terminal assistant response. The schema includes the raw user question, full assistant answer, conversation/thread ID, hashed user reference, citations, invoked tool names, flags and optional bounded reasoning segments. Object IDs are difficult to guess, but that is not authorization. This family is `PRIVATE_OPERATIONAL`, has no public schema, and should be the first shared-bucket family moved after private storage exists.

This census did not list, guess, fetch or inspect any user response-log object.

## Terminal delivery plane

Terminal has two distinct issues: an alternate-origin bypass around otherwise useful BFF gates, and a separate public/static delivery plane.

### BFF versus origin

At the audited Terminal commit:

- `lib/upstreams.ts` hardcodes the public R2 base;
- `lib/flowSource.ts` maps 44 live-flow, options, levels, Prophet and leaders/radar selectors to exact R2 keys; its `manifest` selector actually short-circuits to local `/data/manifest.json`, Options Prophet is R2-first, and `flow_idx` retains a final public GitHub Pages fallback;
- `/api/flow` and its SSE route check `terminal_live_options` for Essential/Pro, but `FLOW_FIXTURE=1` bypasses that entitlement; successful JSON/SSE paths are `no-store`, while the stream's early `403/400` branches omit an explicit cache header;
- `FLOW_FIXTURE=1` also exempts the `/options` page entitlement, precedes `/api/intraday` auth, and redirects server Copilot GEX reads to public fixtures; `NW_FIXTURE=1` likewise redirects both the NW route and Copilot market-plane read;
- anonymous probes of those BFFs returned `403`, while their raw R2 objects returned `200`;
- `/api/intraday` evaluates `FLOW_FIXTURE=1` before optional auth and returns the fixture without an explicit cache header; bad parameters, disabled-seconds, `401`, warm-hit and several error/stale branches also omit explicit `Cache-Control`, while successful fill paths use `no-store`;
- `/api/nw` has no entitlement check and would anonymously relay the protected Neural Web plane if its primary upstream recovers; `NW_FIXTURE=1` is also anonymous; successful upstream, warm and fixture responses are `no-store`, but invalid-selector `400` and fixture-unavailable `503` branches omit an explicit cache header;
- `/api/quote` gates only cache misses when generic Terminal auth is enabled, so warm hits remain anonymous; its single warm-hit, error, empty-batch, bad-parameter and unauthenticated-`401` branches omit explicit `Cache-Control` even though fill paths use `no-store`;
- `/api/ext-quote` is anonymous and has no explicit response cache header; its Quote Hub has mixed Alpaca/Webull/Yahoo/public-R2 source legs;
- the institutional-context BFF is signed-in-only rather than Pro-aware, verifies a 30-second manifest/generation cache against public R2, and feeds the live browser card; `TERMINAL_E2E_FIXTURE=1` bypasses both sign-in and current Company Intelligence lineage before that live R2 read;
- the company-theme BFF has the same unguarded E2E auth/lineage bypass, while company-source search swaps to a deterministic test source; the same flag also bypasses the Discover, Alerts and Portfolio page gates, stubs `/api/me` only outside production, and supplies deterministic data to the already guest-open Terminal page;
- `COMPANY_INTELLIGENCE_FIXTURE=1` and non-production `ANALYSIS_LOCAL_PREVIEW=1` are separate test-source/page controls; the production launch gate must enumerate them rather than assume all fixture authority is carried by `FLOW_FIXTURE`;
- the deployed five-minute `ingest/alerts_engine.py` uses backend-first then anonymous-public-R2 reads for GEX state, GEX, tide, DTE tide and current surface frames, sends `Cache-Control: no-cache` with an eight-second timeout, and has an independent `--flow-fixtures` evidence-source switch;
- `next.config.ts` omits R2 from `connect-src`, but CSP prevents one browser fetch path and does not authorize the object;
- `/data/*` is deliberately outside page middleware and served directly by Caddy.

The flow BFF should be preserved and become the actual delivery boundary after its source is private. The other anonymous BFFs require the field-rights and tier decisions recorded below; merely routing an object through same-origin server code is not an entitlement boundary.

The Terminal Git snapshot contains **134 tracked `terminal/public/data` files**, despite deployment documentation describing the production overlay as untracked: 34 base bars, 34 signal slices, 24 insider files, 2 intelligence files, 38 `*_fixture.json` files, one manifest and one `seed.js`. Every tracked file has both a public raw-Git alias and, when deployed, a public `/data` alias. The checked-in path receipt pins the sorted list (`SHA-256 ee7b3189…`) and mutually exclusive counts. A second receipt pins every fixture's byte count, whole-file SHA-256, semantic family, class, tier and content basis; suffix alone never assigns authority.

Macro's audited public tree adds a separate legacy leak: **244 tracked `site/factordata` product/state artifacts** in the exact families Terminal consumes—two basket-washout state/history objects, `tech_lab.json`, and 241 `tech_events/*.json` files. Their raw-Git URLs are independent alternate origins. Washout remains private operational; technical-lab/event signals remain Essential product. Raw Git's `max-age=300` cache and immutable repository history therefore belong in both cutovers.

### Public `/data` families

| Family | Class / tier | Why current bytes are not a safe anonymous contract |
|---|---|---|
| OHLC files | `UNRESOLVED` | Polygon/Yahoo/Tencent redistribution and delay terms vary. Candidate public chart schema is narrow. |
| `manifest.json` | `PREMIUM_PRODUCT` / Essential | Rows mix identity with verdict, win rate, profit factor, CAGR and bull regime. |
| `coverage.json` | `UNRESOLVED` | Exact per-symbol intelligence inventory can reveal protected families. |
| `*.slice.json` | `PREMIUM_PRODUCT` / Pro complete family | Full signals, gates, quality, opportunities and embedded backtests; Essential requires a separate standard-current projection. |
| `*.intel.json` | `PREMIUM_PRODUCT` / Essential | AI conviction/decisions, GEX, revisions, smart money and exact levels. |
| `*.backtest.json` | `PREMIUM_PRODUCT` / Pro | Parameters, trades, metrics and equity curve. |
| `*.seasonal.json` | `PREMIUM_PRODUCT` / Pro complete family | Analog weights, forward distributions and deep history; Essential requires a separate current projection. |
| `market_risk.json` | `PREMIUM_PRODUCT` / Essential | Proprietary score/components/radar. |
| Washout state/history | `PRIVATE_OPERATIONAL` | Internal entry-admission input with no browser UI consumer found. The exact source bytes have public-R2, primary `factordata`, Macro raw-Git and Terminal-static aliases; all inherit one private-service disposition. |
| `*.fund.json` | `UNRESOLVED` | Filed facts are mixed with estimates/ownership/vendor fields and cadence semantics. |
| `*.opts.json` | `VENDOR_RAW` | Transformed delayed chain/smile/term structure with unproved redistribution rights. |
| `*.insider.json` | `PREMIUM_PRODUCT` / Essential | Form 4 facts are mixed with proprietary score/signal/analysis. |
| `tx/**` transcript corpus | `VENDOR_RAW` | Large third-party full-text corpus with unresolved copyright/redistribution rights. |
| Intraday static/API bars | `UNRESOLVED` | Minute/second vendor rights and commercial tier are unresolved. |
| 38 tracked `*_fixture.json` files | 30 Essential product; 6 Pro history; 1 Options Prophet `PRIVATE_OPERATIONAL` / operator-only; 1 levels `UNRESOLVED` | Each file is joined to its semantic family by exact static and raw-Git aliases. The immutable taxonomy receipt pins per-file bytes/hash and disposition; a “fixture” suffix confers no safety. |
| Tracked `seed.js` | `PREMIUM_PRODUCT` / Pro | A 17,692-byte real seed with 200 NVDA bars, 12 proprietary signals/state and a complete 39-trade backtest. |
| `/api/quote`, `/api/ext-quote` | `UNRESOLVED` / hold private pending rights | Basic quote fields may qualify as facts, but source rights, delay/basis and inconsistent cache branches are not yet an approved contract. |
| `/api/nw` plus primary Neural Web JSON | `PREMIUM_PRODUCT` / Essential | The primary origin returned `401`, but the anonymous proxy has no product entitlement and will relay full scores/context when upstream is available. |
| Exact legacy `factordata` fallbacks | `PREMIUM_PRODUCT` / Essential | Terminal fetches only `tech_lab.json` and `tech_events/<SYM>.json`; 242 tracked files in those patterns remain anonymously reachable through raw Git as well as the primary fallback. Other primary/raw-Git `factordata` leaves fail to their ordered unresolved defaults unless separately classified, while the two washout leaves are private operational on every origin. |

Production `/data/manifest.json` was anonymously readable at roughly 2.1 MB; a representative symbol's slice, intelligence, fundamentals, options, backtest and seasonal files also returned `200`. At least `prophet_fixture.json`, `flow_fixture.json` and `seed.js` were anonymously readable with `s-maxage=300`. Browser code adds SWR and IndexedDB persistence for up to 300 objects. Cutover therefore requires removal of tracked/raw aliases, fixture-mode launch assertions and a cache namespace/version change—not merely origin ACLs.

### Proprietary client source

Terminal also embeds the full flagship Pine literal, Oracle-derived source and premium-suite formulas in client code. Source maps being disabled is only friction. Raw algorithms are `PRIVATE_OPERATIONAL`; computed entitlement-projected series are `PREMIUM_PRODUCT`. A paid dynamic chunk would still reveal the formulas to its recipient, so the containment dependency is server-side computation, not a stronger client feature flag.

## Mastermind server dependency

Mastermind cannot tolerate an uncoordinated public-R2 shutdown:

- `data_layer/macro_refresh.py` hardcodes and anonymously mirrors the public `stockdata` manifest and objects;
- missing stockdata is a safety-relevant degraded input for conviction, entry, risk/gate, portfolio and brain consumers;
- `portfolio/prophet_feed.py` consumes the complete vendored Prophet schema and exact plan geometry;
- those plans feed discovery and portfolio intelligence.

The migration must give Mastermind two explicit private transports. Stockdata must preserve its flat-key/manifest/ETag/last-good semantics. Prophet must preserve the vendored path, schema, staleness and mtime-cache behavior while replacing public Git delivery with authenticated private sync. The correct split is a public identity/fact directory plus privately synchronized graded contracts—not deleting either family or weakening downstream safety checks.

## Existing correct private patterns

The repository already contains boundaries worth reusing:

| Family | Current boundary | Classification |
|---|---|---|
| Focused quote attempts | Dedicated private options credentials/prefix | `PRIVATE_OPERATIONAL` |
| Research Vault inbox/receipts/corpus, archive and private Earnings Wire | Separate `R2_RESEARCH_*` bucket/store | `VENDOR_RAW`, `PRIVATE_OPERATIONAL`, and `PREMIUM_PRODUCT` / Pro are split by exact key family |
| Institutional 13F raw evidence/catalog/control/research | Dedicated `INSTITUTIONAL_13F_R2_*`, no shared fallback | `VENDOR_RAW`, `PRIVATE_OPERATIONAL`, and `PREMIUM_PRODUCT` / Pro are split by exact key family |
| BioCatalyst raw/source evidence | Dedicated `BIOCATALYST_R2_*` | `VENDOR_RAW` / private service |
| BioCatalyst receipts/runs/attempts/manifests/commits/activation proof | Dedicated `BIOCATALYST_R2_*` | `PRIVATE_OPERATIONAL` / private service |
| BioCatalyst derived prospective/history lineage | Dedicated `BIOCATALYST_R2_*`; separate pointer-bound app projection | `PREMIUM_PRODUCT` / Essential through server only |
| Filing Forensics private store | Research/private object store with prefix-scoped credentials | Operational state plus Pro product |

Two boundaries still need hardening:

- Capital Structure prefers a dedicated/research store but can fall back to the generic shared bucket. Its raw SEC objects are `VENDOR_RAW`; heads, CAS witnesses and generation state are `PRIVATE_OPERATIONAL`.
- Research Vault supports dedicated variables but may fall back to shared account credentials. Bucket identity, not variable naming, is the proof required before migration.

BioCatalyst itself is correctly physically private, but its `biocatalyst/**` namespace is not one semantic family. The registry now uses exact raw, operational and derived-product key shapes plus an ordered `UNRESOLVED` remainder. Failed-fetch/incident key shapes are reserved as private operational even though the audited worker currently keeps those artifacts local; the report does not claim a remote emission that code does not prove.

Default-deny resolution is ordered and deterministic. Any positive family wins first; if none matches, the first matching `DEFAULT_DENY` row in registry order wins. Narrow prefix remainders therefore precede the shared-R2 and public-repository remainders, so `feeds/new_unknown.json`, a reserved `stockdata` filename, or an unregistered internal-options artifact resolves to one—not two—fail-closed families.

## Safe public schema rules

A family is not safe merely because its source facts are public. Every anonymous object must be generated from an explicit allowlist. The common public envelope should carry only what the surface needs:

```json
{
  "schema": "<approved-public-schema>/v1",
  "asof": "<source observation time>",
  "built_at": "<projection build time>",
  "source": "<non-secret provenance>",
  "delay": "<honest delay/basis>",
  "coverage": {"total": 0, "shown": 0},
  "items": []
}
```

Anonymous ranked surfaces receive approximately one approved item; Free receives approximately three; Essential receives the complete current standard product; Pro adds approved advanced history/research/export. The public and Free payloads must not contain the hidden remainder.

The public builder must deny, at minimum, unapproved ranks/scores, actions, sizing, entries, invalidations, targets, exact options contracts/levels, watchlists/preferences, customer/account data, prompts/responses/reasoning, raw vendor rows, model artifacts, private paths and internal manifests.

## Migration dependencies and order

No storage mutation is safe until consumers are closed transitively. The census yields this order:

1. Establish physically separate public-fact and private product/raw origins. Do not rely on a giant blacklist over the mixed bucket.
2. Give Macro, Terminal and Mastermind services authenticated private reads with least-privilege prefixes.
3. Move `PRIVATE_OPERATIONAL` first: response logs/evals, Options Prophet shadow, Prophet armed/events, washout state, internal options/repository state and model artifacts.
4. Move `VENDOR_RAW`: ThetaData, Massive, HK/odds raw stores, Terminal option snapshots/transcripts and raw evidence planes.
5. Move complete `PREMIUM_PRODUCT` objects: Prophet, stock intelligence, live/options, leaders/radar, company/earnings/Oracle and history.
6. Build public and Free projections from exact allowlists; keep public shells and critical assets anonymous.
7. Update Terminal BFF/fallbacks, the deployed Alerts Engine, Macro `data_base.js`, Mastermind refresh and every other server consumer; production launch assertions must reject all enumerated fixture/test controls, not only `FLOW_FIXTURE` and `NW_FIXTURE`.
8. Stop future public-repository publication of protected generated artifacts, including Prophet/options state and all 244 classified `site/factordata` aliases; separately decide immutable-history remediation.
9. Under an operator-approved runbook, remove old public objects, disable inappropriate public development origins, and purge CDN/browser cache namespaces.
10. Prove every former protected key returns `401/403/404` across primary origin, R2 direct origin, custom CDN, repository raw paths, Terminal fallbacks and legacy aliases; independently prove all four tier projections.

`scripts/audit_r2.py` currently treats `401/403` as public-access failure. It must split into a public-allowlist liveness audit and a protected-key denial audit. Weakening the existing check globally would turn the migration into a false green.

## Operator gates

The following remain operator-gated and were intentionally not attempted in W0-A:

- creating or changing an R2 bucket;
- changing public access or the `r2.dev` endpoint;
- adding/rotating credentials;
- changing DNS/custom domains;
- deleting or purging existing remote objects;
- repository-history remediation.

The future operator runbook must name the exact bucket/prefix, action, expected result, rollback and verification command. A vague “make R2 private” instruction is insufficient because share media and approved public facts require a deliberate public plane.

## W0-A enforcement contract

`tests/test_r2_delivery_plane_classification.py` makes this census executable. It must fail when:

- a class or tier leaves the closed enum;
- the Anonymous/Free/Essential/Pro complete-family versus projection semantics drift;
- a required record field is absent/empty;
- a family ID or key-family expression is duplicated;
- a key expression uses prose instead of the formal scoped grammar, or a positive expression's concrete witness resolves to zero or multiple families;
- a default expression cannot win its ordered remainder, a nested unknown resolves anywhere except its narrow first fallback, or a malformed BioCatalyst near-miss inherits a known class;
- a `publish_r2` directory is missing from the registry;
- the browser rewrite names an unregistered directory;
- a protected browser-direct family lacks a migration dependency or safe-schema decision;
- a critical family is weakened from its pinned classification;
- any Macro, Terminal or Mastermind evidence anchor lacks `repo:path:positive-line`, exceeds its pinned file, or lacks a whole-file SHA receipt;
- any of Terminal's 134 tracked public-data paths does not resolve exactly once on both static and raw-Git origins;
- the ordered 44-entry Terminal selector-to-key-to-family map, root-level options keys, normal/Options-Prophet source order, local manifest exception or exact GitHub Pages fallback drifts;
- any of the 38 fixture hashes/content dispositions drifts, a fixture resolves by suffix instead of exact semantic alias, or the seed loses its real browser-consumer anchor;
- any of the eight `TERMINAL_E2E_FIXTURE` production-source occurrences, five additional fixture/test controls, flow/options/intraday/Copilot bypasses, anonymous Neural Web route, quote warm-hit gate or enumerated route-cache branch truth is erased;
- any deployed Alerts Engine backend/R2/fixture mapping or its cache/source-order law drifts;
- washout state/history stops resolving to one private-operational family across public R2, primary static, Macro raw Git and Terminal static, the two exact paid technical-lab fallbacks widen or change disposition across primary/raw Git, or an unknown `factordata` key avoids the origin's default-deny;
- known Prophet, stockdata, live-state or Options Prophet aliases change disposition across R2, primary static and raw Git, or an unknown object in any registered shared-R2, Macro-repository, Terminal-data, in-scope primary-static or BioCatalyst namespace avoids its ordered `UNRESOLVED` default;
- the human report and machine registry drift.

The enforcement includes immutable inventory/evidence receipts under `tests/fixtures/`; it does not depend on sibling repositories existing in CI. W0-A changes no runtime or data-plane behavior. Its rollback is a normal revert of the report, registry, receipts and tests. It cannot make the current public exposure better or worse; it prevents the next PR from guessing.

## Open decisions retained as unknowns

- Per-source redistribution and delay terms for Macro/Terminal OHLC and intraday families.
- Exact public field allowlist for quote/fundamental schemas, including HK semiannual period semantics.
- Source-body and copyright rights inside Earnings Evidence and Terminal transcripts.
- Product/proof split inside levels, ledger, track-record and trust artifacts.
- Explicit user-share/retention policy for Terminal snapshots.
- Actual production bucket identity for every “private” credential namespace and whether any resolves to the shared public bucket.
- Historical public-object and public-repository remediation scope after future cutover.

Unknowns are not approvals. Every unresolved family remains private by default.
