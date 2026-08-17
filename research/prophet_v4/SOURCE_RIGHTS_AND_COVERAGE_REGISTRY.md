# PROPHET US V4 — SOURCE RIGHTS AND COVERAGE REGISTRY (V4-0A)

**Pinned main:** `fc0557bb0873` (2026-08-17). Registry of every evidence family V4 may draw on: source, rights posture, coverage/freshness truth, and the null state it must publish until fixed. Law 21 binds: **rights before use**; unknown/unlicensed fails closed. This registry seeds V4-D1 (theme census) and V4-D7 (per-family adapters); each adapter wave re-verifies its row at its own SHA.

## 1. The Theia/S&P ruling (explicit, as the 0A handoff requires)

**Decision record: `DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS`** (agentos/decisions/, this PR).

- The remembered "S&P theme dashboard" source **is Theia Insights**: S&P's Thematics Dashboard runs on Theia's TIIC multi-level hierarchy; Theia publicly describes 245 major themes, 3,200+ micro-themes, 50,000+ companies, and daily Theme Watch Indices across 200+ themes.
- Estate truth at pin: **no adapter or ingestion code exists**; `config/theme_sources.yml:49-52` carries a commented-out `theia:` stub (`rights_class: unresolved`, `auth_class: licensed`); GMI W3A prepared the procurement question list (`research/theme_graph/W3A_SOURCE_RIGHTS_AND_PROCUREMENT.md` §5: Level-4/5 taxonomy access, company↔theme exposure **weights**, PIT vintages, issuer-grain identifiers, provenance labeling) and the CEO W3 directive §13 says "evaluate, do not block W3."
- **Ruling:** default = build the Mastermind classification originally from lawful sources; Theia/S&P = competitor-methodology research only — no scraping, no taxonomy/constituent copying, no ingestion absent a signed license. Licensed TIIC/TWI remains a recorded **Chairman procurement option** (W3A §5 is the requirements list); if purchased it enters as one provider-classification plane under the graph's rights gates, never as the canonical spine.

## 2. Theme/graph sources

| Source | Rights posture (registry: `config/theme_sources.yml` + `engine/theme_graph/rights.py` gate) | Coverage at pin | V4 use |
|---|---|---|---|
| Finviz local themes (`ltheme:finviz:*`, 268) | `unresolved` ⇒ **internal-only**, no public emission | PIT memberships since W3A (#5718); refresh receipts `data/themes_heatmap/tree_refresh_receipts/` | internal context; probation mapping to canonical IDs only |
| THS local themes (`ltheme:ths:*`, 373) | `unresolved` ⇒ internal-only | same store | same |
| Curated baskets (`data/baskets/latest.json`) | first-party | live; today the ONLY theme signal Prophet's context vector reads (`engine/us_context_vector.py:435-465`) | bridge to graph plane in D-lane (two theme planes are currently UNJOINED — see CURRENT_STATE) |
| Theme graph store (`data/theme_graph/{nodes,edges,capability,evidence}.parquet`) | first-party derived, rights-gated per edge | nodes/edges/capability shipped; **no `state/` subdir — ThemeState not built** | canonical substrate to extend (D2–D4) |
| S&P/Theia public pages | terms-bound reading only | n/a | benchmark orientation only; nothing enters stores |

## 3. Alt-data families (V4-D7 adapter candidates)

Census by the V4-0A intelligence archaeology (receipts in module docstrings/paths). "Display-only" = no scored-axis authority today; every family enters V4 only through the §14.2 envelope with the states below.

| Family | Source | Module | Artifact | Freshness model | Rights/coverage truth at pin |
|---|---|---|---|---|---|
| Political/insider/institutional suite (congress, govcontracts, lobbying, off-exchange, WSB…) | Quiver Quant API | `engine/altdata.py` | `data/quiver/`, `data/altdata/feed.json` | nightly append | display/context only by module law |
| Institutional 13F | SEC | `scripts/run_institutional_13f_rolling.py`, `engine/fund_intelligence.py` | `data/institutional_13f/` | quarterly | lawful public |
| Insider Form 4 | SEC EDGAR | `engine/insider_factor.py`, `insider_power.py` | `data/sec_insider/` | per-filing | **collector DEAD since 2026-Q1** → family = `PRODUCER_DEGRADED` until repaired |
| Short interest | FINRA | `lib/finra_knowable.py`, `engine/short_pressure.py` | `data/finra/short_interest_history.parquet` | knowable = 8th NYSE session post-settlement (#5705) | PIT-lawful; **only 3 settlements committed → `ACCRUING`, not estimable** |
| Short volume | FINRA | `scripts/backfill_finra_short_volume.py` | `data/finra_short_volume/` | daily | lawful public |
| Dark pool / ATS | FINRA ATS + Quiver | `engine/darkpool_context.py` | `data/darkpool/`, `data/finra_ats/` | weekly/daily | lawful |
| Borrow/HTB | IBKR | `scripts/collect.py` | `data/ibkr_borrow/` | daily | licensed feed, internal |
| Options flow | vendor tape | `engine/options_flow.py` | `data/options_flow/` | intraday | licensed, verify redistribution before UI |
| Gamma exposure | CBOE/Polygon-derived | `engine/gex_engine.py` etc. | `data/gex/`, `data/polygon_gex/` | daily | licensed-derived |
| News vector/flow | wire aggregation | `engine/news_vector.py`, `news_flow.py` | `data/news_vector/`, `data/news/` | continuous | verify per-source redistribution at adapter time |
| Social/retail attention | StockTwits + Quiver | `engine/altdata.py`, `missing_tape_attention.py` | `data/stocktwits/` | daily | display-only |
| Wikipedia attention | Wikipedia API | producer unverified | `data/wikipedia/` | daily | lawful public; producer liveness unverified |
| Analyst revisions | vendor estimates | `engine/analyst_revisions.py` | `data/revisions/` | per-release | **coverage-blocked: 0.67% of events** → `PARTIAL`/`UNAVAILABLE` for most names |
| 8-K magnitude | SEC EDGAR | `engine/eightk_magnitude.py` | `data/eightk_magnitude/` | per-filing | lawful |
| Gov spending/contracts | USASpending, SAM.gov | `engine/intel_discovery.py`, `radar.py` | `data/usaspending/`, `data/sam_gov/` | periodic | lawful public |
| Bio catalysts | ClinicalTrials.gov, openFDA | `engine/altdata.py`, `theme_clinical.py` | `data/clinicaltrials/`, `data/openfda/` | periodic | lawful public |

**Registry law for adapters:** each V4-D7 adapter PR carries its family's source law, PIT/knowability law, coverage, freshness, null taxonomy, rights state, and Evaluation OS registration — one family per PR, authority never above its registered tier.

## 4. Earnings

Owner: **Earnings Intelligence OS** (E0 in progress; E1/E2 todo). V4's earnings family publishes **`ACCRUING`** (null_reason `canonical_event_workspace_not_live`) until EIOS ships a stable consumer contract. Known estate hazard V4 must not inherit: the Wire and Company-Intelligence planes currently disagree per-issuer (`DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER`); the V4-D6 adapter binds to EIOS's canonical event workspace, never to both planes at once.

## 5. Market data / quotes

Canonical market-data owner serves the 5-minute Radar lane (`DEC:LER-LIVE-LANE-VPS-5MIN-REST`: VPS timer, REST/snapshot, **no second WebSocket owner** — masterplan §6.4). Entry-availability freshness inputs (quote age, session basis, extended-hours flags) come from this owner; a stale/missing quote is a non-waivable `ENTRY_OPEN` blocker, never a default.

## 6. Identity

Security/company identity, identity epochs, delistings, corporate-action basis: **Stock Identity** program (`engine/stock_identity/`, W1 Identity Atlas v0 merged #5612, W1-A1 correction #5660). V4 consumes `stock_identity.*` interfaces; minting identity inside Prophet is prohibited (Fusion's do_not_redo already binds the same).

## 7. Coverage disclosure law (restated for adapters)

Every family row publishes exactly one of `MEASURED / PARTIAL / STALE / NOT_APPLICABLE / UNAVAILABLE / ACCRUING / RIGHTS_BLOCKED / PRODUCER_DEGRADED` + as-of/knowable/captured clocks + receipts + null_reason. The board publishes evidence-coverage ratio and band per row. A high-coverage row must not outrank a low-coverage row merely because more data exists — coverage feeds the conservative priority and the band chip, not the raw family values.
