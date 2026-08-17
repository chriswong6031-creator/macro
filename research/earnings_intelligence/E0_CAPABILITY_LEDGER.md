# E0 Capability Ledger — Earnings Intelligence OS

**Wave:** E0 · **Verified:** 2026-08-16 · **Production mutation:** none  
**Authority:** `research/EARNINGS_INTELLIGENCE_E0_FREEZE_ARCHAEOLOGY_AND_EXPERIENCE_HANDOFF_2026-08-16.md`  
**Code base:** `origin/main` @ `3b16672fcfee` plus live fetches the same day  
**Terminal base:** `origin/master` @ `82cb8cbf` (CI v1 + transcript search)

State vocabulary is closed. No `UNKNOWN` remains.

| State | Meaning used here |
|---|---|
| `PROVEN_LIVE` | Producer writes it and a production surface or artifact was observed this session |
| `BUILT_NOT_PROVEN` | Implementation exists; this session did not observe a live consumer path |
| `PARTIAL` | Some of the user job works; a named gap remains |
| `DARK_OR_DISCONNECTED` | Code exists and is not on the normal product path |
| `BROKEN` | Intended path fails on current production |
| `SPEC_ONLY` | Docket/spec/screenshot only |
| `NOT_BUILT` | No implementation in the inspected trees |
| `REJECTED_BY_DESIGN` | Explicitly not a rebuild target |

**Estate split (the load-bearing finding):** transcript evidence + public Wire + CI dossier teaser + Stage scores + Group Reads pulse are live. Issuer-keyed `company_event.v1`, per-claim v2 citations, release/filing/slides joins, and the research workspace are library, spec, or split across planes. See `DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER`.

E-wave owner is the *first* wave allowed to change the row. Later waves may consume it.

---

## 1. Source and event truth

| Capability | User job | State | Sources | Production surface | Data source | Missing deps | Governing doc | E-wave | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| Company / security / alias identity | Know which legal issuer and share class an event belongs to | PARTIAL | `engine/company_intelligence/identity.py`; live mint still `contracts.py` | Library + golden issuers fixture; live CI keyed by ticker | SEC CIK intended; live history keyed by ticker | Production builders do not mint from `IssuerRegistry` | Freeze Q1; Docket §4.2 | E1 | `identity.py:1-11`; `contracts.py:214-223` hashes ticker. Live `GET /api/company-intelligence/GOOGL` 200, `…/GOOG` 404 (2026-08-16) |
| Event identity and lifecycle | One issuer-quarter event, correction-stable | PARTIAL | `events.py` `company_event.v1`; `event_id_adapter.py`; live `stable_event_id` / narrative `event_key` | Adapter + corpus tests; live Wire/CI still `cie_…` and `TICKER/YYYYQn` | Transcript period + earnings history rows | Live producers listing-keyed; lifecycle not driving publication | Freeze Q1/Q4; Wave 1.1–1.3 | E1 | `events.py:182-200` `evt_cik0000320193_2026q3_results`; AAPL live `cie_98e318c37ec1a2a1f83c45e1` |
| Earnings calendar | What reports when | PARTIAL | `collectors/equity_earnings.py`; `scripts/audit_earnings_freshness.py` | `data/earnings/earnings.parquet`; nightly `daily.yml` | Finnhub/Yahoo-style calendar | Coverage SLA failing | Handoff §3.1 | E5 | `earnings_freshness_audit.json` `ok: false`, 17.9% within 2-td SLA (as_of 2026-08-13) |
| Release / Exhibit 99.1 | Read the press release bound to the event | PARTIAL | `engine/marketing/edgar_earnings_wire.py` | Marketing SEC cards; **not** CEI ingest | EDGAR 8-K Item 2.02 → Exhibit 99.1 | CEI digest hard-codes `release: not_ingested` | Wave 1.4 | E1 | `digest.py:252-260`; `public_wire.py:396-400` |
| 8-K / 10-Q / 10-K binding | Open the filing that is this event | PARTIAL | `collectors/edgar_earnings_8k.py`; `resolution.py` | `data/edgar/earnings_8k_dates.parquet`; marketing lane | SEC submissions JSON Item 2.02 | 10-Q/10-K unbound; CEI filing `not_ingested` | Freeze Q2 | E1 | `edgar_earnings_8k.py` stores `(cik, accession)`; digest still `filing: not_ingested` |
| Raw / edited transcript revisions | Open the exact body revision | PROVEN_LIVE | `earnings_narrative/contracts.py` `mastermind.tx/v1`; Terminal bodies | Evidence/story R2; Wire sourced from admitted packets | Terminal transcript index + body SHA-256 | Multi-doc revision graph beyond transcript | Handoff §3.1–3.2 | E1 | Live LMND/IEX Wire pages bind `source_sha256` + byte spans (2026-08-16) |
| Slides | Search and cite a deck page | SPEC_ONLY | Completeness enums; corpus `slide_region` | None ingested | None | Slide ingest, page-region receipts | Docket §4.1; Wave 5 | E10 | `context_packets.py` `"slides": "not_ingested"` |
| Audio metadata | Jump to a timestamp | SPEC_ONLY | Docket only | None | None | Licensed audio + time-aligned spans | Docket §2 / §6 | E15 (defer) | No engine module |
| Consensus snapshots | Compare actual vs decision-time estimate on a matched basis | PARTIAL | `data/earnings/earnings.parquet` `eps_forecast`; marketing plausibility | Calendar EPS field; marketing cards | Free calendar EPS, not a licensed consensus product | Licensed estimates; CEI `consensus: unlicensed_absent` | Freeze completeness | E1 (typed absence) / E3 (licensed) | `digest.py:256-257` |
| Market reaction | What the stock did after the print | SPEC_ONLY | Stub in `digest.py`; forbidden in `promotion.py` | Empty `not_joined` disclosure | None for CEI | PIT prices + `security_id` windows | Docket Event Digest | E2 (join) | `digest.py:397-400`; `promotion.py:52` forbids `market_reaction` |
| Source rights | Know when a body cannot be shown | SPEC_ONLY | `events.py` reserved `blocked_rights` | Enum reserved, not mintable | None | Rights registry | Freeze Q5 | E15 | `events.py:76-84` excluded from mintable status |
| Correction replay | One amendment updates every consumer | PARTIAL | `story.py`; `story_store.py`; corpus amendments | Story/evidence supersession on source SHA change | Transcript body revision SHA | Invalidate dossier/Terminal/Wire/X as one graph | Wave 1.7 | E1 | `story.py:517-520`; corpus `amendment: 16` |

---

## 2. Extraction and intelligence

| Capability | User job | State | Sources | Production surface | Data source | Missing deps | Governing doc | E-wave | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| Deterministic result facts | What numbers were reported | PARTIAL | `engine/earnings_narrative/extract.py`; marketing table extract | Fact packs on Wire | Transcript numeric spans; marketing Exhibit 99.1 tables | Typed GAAP/non-GAAP from release bound to the CEI event | Wave 1.5 | E1 | `extract.py:1,70-81` quote/numeric only; Wire IEX `46.4%` / `110` bps spans live |
| Actual / prior / consensus / guide deltas | Beat, miss, raise, cut on a matched basis | PARTIAL | `views.py` `previous_event_deltas`; marketing comparable EPS | CI metric deltas; marketing cards | Score metrics / calendar estimate | Basis-matched beat/miss + guidance raise/cut | Wave 2A; Freeze GAAP | E1 | AAPL live deltas `revenue_growth_pct: -1`, `eps_growth_pct: +7` (score overlay, not 8-K) |
| Guidance extraction and history | What management now expects vs last time | PARTIAL | `digest.py` lexical `guidance` | Digest/Wire category buckets | Transcript phrase hits | `guidance_item.v1` ranges, prior comparable | Docket `guidance_item.v1` | E1 / E3 | Live IEX: “5%-7% organic growth… adjusted EPS $2.20-$2.25” as a quote, not a structured item |
| Segment / KPI extraction | Operating KPIs, not just EPS | PARTIAL | `digest.py` `segment_changes` phrases | Lexical category refs | Transcript phrases | Real segment/KPI series with units | Wave 1.5 | E3 | `digest.py:89-92` |
| Narrative summary | What happened, in one glance | PARTIAL | `views.py`; `generation.py` / story copy | Dossier summaries; Wire is **not** a summary | History + score overlay | Span-cited briefs | Handoff §3.2 | E2 | AAPL live summary from `score_overlay`; `claim_citations_pending: true` |
| Narrative change | What is new vs last quarter | PARTIAL | `views.py` `_topic_summary`; digest `narrative_deltas: []` | Tag added/dropped/persistent | Event tags | Phrase/commitment deltas vs prior quarter | Docket Narrative Timeline | E4 | `views.py:467-496`; `digest.py:615` empty |
| Management commitments | Promises and whether they were kept | PARTIAL | `digest.py` commitment phrases | Lexical digest category | “we will / plan to …” | Commitment lifecycle | Docket §7 | E4 | `digest.py:85-88` |
| Q&A exchange structure | Who asked, who answered, on what | PARTIAL | `digest.py` prepared vs `q_and_a` markers; Terminal in-call filters | Chapter labels; Terminal speaker/Q&A display filters | Transcript markers | Structured Q↔A pairs | Docket §7.6 | E2 / E6 | Terminal `TranscriptDrawer.tsx` filters; no exchange object |
| Question topics | What analysts pressed | PARTIAL | CI `topics` from tags | Dossier topic chips | Upstream tags | Q&A-derived clusters with receipts | Docket Peer Topics | E6 | Topics = tag timeline `views.py:467+` |
| Non-answer / deflection | What management avoided | NOT_BUILT | — | None | None | Evasion labels + spans | Docket §7 | E6 | No matches under `engine/earnings_narrative/` or `company_intelligence/` |
| Tone / uncertainty | How confident / hedged | PARTIAL | `engine/stage_analysis.py` `_tone_word`; CI metrics | Stage “earnings tone”; dossier metrics | Legacy qualitative scores | Claim-grade uncertainty with receipts | Handoff R0-C fence | E3 (display) | Stage tone from sentiment; CI `PUBLIC_METRICS` `contracts.py:32-46` |
| Entity extraction | Named products, customers, places | SPEC_ONLY | Digest stub | Forced empty | None | Named-entity extract with spans | Docket | E7 | `digest.py:394-396` `issuer_mentions: []` |
| Relationship extraction | Customer / supplier / competitor edges | SPEC_ONLY | Digest stub; Docket `relationship_edge.v1` | Forced empty | None | Filing/transcript relationship graph | Docket §7.7 | E7 | `digest.py:617` empty |
| Theme / topic evidence | What theme this event feeds | PARTIAL | CI topics; digest `theme_context: []` | Tag topics on dossier | History tags | Source-grounded theme evidence rail | Docket Themes | E9 | `theme_context` forced empty; TIL does not own earnings read-through |
| Contradictions | Claim vs later claim / filing | NOT_BUILT | — | None in CEI | None | Claim contradiction ledger | Docket | E4 | NW `factor_contradictions` is a different plane |
| Exact per-claim citations | Click a claim, land on the span | PARTIAL | Narrative span receipts; CI pending flag | Exact on Wire/evidence; CI metadata/document | Transcript UTF-8 spans | v2 derived pending / typed absence on CI and Terminal Brief | Freeze Q3; Wave 1.8 | E1 | Wire IEX/LMND byte tables live; CI `views.py:461` stored `True`; AAPL sources `citation_precision: "document"\|"metadata"` |

---

## 3. Search and research workflow

Macro vs Terminal are separate rows where they diverge.

| Capability | User job | State | Sources | Production surface | Data source | Missing deps | Governing doc | E-wave | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| Transcript search | Find a phrase across calls | PARTIAL | Terminal `TranscriptSearchWorkspace.tsx`; Macro none | Terminal analysis intelligence tab | Terminal bodies + BFF `/api/company-source-search` | Macro corpus search; cross-call speaker/Q&A filters | Handoff Wave 3 | E5 | Terminal live exact segment + byte span; Macro `NOT_BUILT` |
| Filing / release search | Find a number in an 8-K | NOT_BUILT | Source kinds only `earnings_history \| score_overlay \| transcript` | None | None | Filing index | Spec §12.1 | E5 | `companyIntelligence.ts:16-19` |
| Slide search | Find a chart in a deck | SPEC_ONLY | V2 delta spec §5.8 | Spec + mock HTML | None | Wave 5A producer | Spec §5.8 | E10 | Terminal `Lens` type has no slides |
| Global cross-source search | One box across transcript/filing/slides | SPEC_ONLY | Spec §5.6 | None | None | Corpus route + provider health | Spec §5.6 | E5 | Live search is ticker-scoped |
| Exact context open | Citation → source span | PARTIAL | Wire receipt table; Terminal search→reader; Brief rail | Wire + Terminal search | Transcript spans | Brief→span; intra-segment highlight | Freeze Q3 | E2 | Wire tables live; Brief `EvidenceRail.tsx` “span pinning pending”; `claim_citations_pending: true` |
| Company history comparison | This quarter vs last | PARTIAL | Stage QoQ; CI history; Terminal two-event compare | Stage `ernCompareView`; CI History lens | History + scores | Narrative/commitment history | Wave 4A | E2 / E4 | Stage `earnings_qual.py:2756-2769`; CI History is a metrics table |
| Peer comparison | This print vs peers | SPEC_ONLY | Spec §5.5 Peers | None | None | Wave 4A entity graph | Spec §5.5 | E8 | Live `Lens` has no peers |
| Topics | What this company is being asked | PROVEN_LIVE | CI topics; Terminal Topics lens | Dossier + Terminal | Tag timeline | Topic→span navigation | Handoff §3.2 | E6 (deepen) | Terminal e2e Topics tab; AAPL live tags include `supply_constraints`, `memory_costs` |
| Mentioned By | Who named this company | SPEC_ONLY | Digest stub; spec §5.5 | None | None | Mentions producer | Wave 4 | E7 | `digest.py:616` `[]` |
| Cited chat | Ask, get a sourced answer | PARTIAL | Brain compact context; Terminal Ask Mastermind | Brain widget + Terminal | Compact call context | Locator chips on answers | Wave 2B+ | E2 / E13 | `brain_gateway.py:1475-1534`; no claim locators |
| Exports | Take the evidence with you | PARTIAL | Private Research Vault; no CI export | Private `/api/earnings/v1/records/{slug}` | Story packets | CI PDF/CSV; rights-aware source export | Wave 5 | E12 | `private_publication.py:6-11` |
| Highlights / notes / workspaces | Save my reading | PARTIAL | Producer `highlights` fields | CI highlights UI | History highlights | User notes, bookmarks, saved searches | Wave 3B/5 | E5 | `CompanyIntelligencePage.tsx:502-512` |
| Keyword alerts | Tell me when a phrase returns | NOT_BUILT | Alerts = price/RSI/options | None for transcripts | None | Keyword/transcript alert type | Wave 3/5 | E5 | `AlertsView.tsx:37-42` |
| Watchlist / calendar integration | My names, this week’s prints | PARTIAL | Watchlist “next earnings”; daily calendar sweep | Watchlist + stock page | `earnings.parquet` next dates | Watchlist-scoped CI calendar | Wave 3 | E5 | `watchlist.html.j2:858-860`; CI calendar spec-only |

---

## 4. Group and market intelligence

| Capability | User job | State | Sources | Production surface | Data source | Missing deps | Governing doc | E-wave | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| Season analytics | Who raised/cut this season | PROVEN_LIVE | `engine/earnings_qual.py` `earnings_season` | Stage Analysis | Earnings-call scores + history | Claim-grade season (not Stage scores) | Handoff §3.1 | E11 (consume) | `stage_analysis.html.j2:1791-1813`; health `ready`, 50,982 rows, latest call 2026-08-07 |
| Industry earnings heatmaps | Where the season is concentrating | PROVEN_LIVE | `ec_industry_heatmap` | Stage | Same | Join to CEI events | Stage | E11 | `earnings_qual.py:2349+` |
| Reporting waves | Who in this group has printed | PROVEN_LIVE | `engine/group_earnings.py` | Basket detail | Group Reads + calendar | Issuer-keyed wave object | Group Reads | E8 (consume, do not rebuild) | `group_earnings.py:64-70,785` |
| Peer read-through | What this print implies for silent peers | PROVEN_LIVE (group) / SPEC_ONLY (event-mechanism) | `group_earnings.py` sympathy | Basket detail | Group participation | Event-level mechanism / incorporation (neural-graph docket) | `group-reads` owns this | E8 | `mastermind_programs.yml:1289-1291`; neural-graph architecture is spec |
| Relationship paths | Customer/supplier path | DARK_OR_DISCONNECTED | `engine/group_linked_outsiders.py` | Pipeline; `outsiders: []` | 0 counterparty edges | Filing relationship extract | Wave 4 | E7 | `group_linked_outsiders.py:29-41` |
| Residual co-movement groups | Who moves together after beta | PARTIAL base / SPEC_ONLY earnings-joined | `engine/theme_crowding.py`; Wave 4 | Crowding ≠ earnings join | Residuals | Event join | Wave 4 | E9 | Group Reads uses curated baskets, not residual communities |
| Group Reads × earnings | Basket pulse + sympathy | PROVEN_LIVE | `engine/group_earnings.py` | `basket_detail.html.j2` | Group Reads | Do not duplicate inside Earnings | `DEC:EARNINGS-INTELLIGENCE-IS-A-CENTRAL-LOBE` | E9 | Implementation root `group_earnings.py:1-29` |
| Theme / TIL × earnings | Theme catalyst from prints | PARTIAL | `theme_catalyst_binder.py` | Theme addons `days_to_earnings` | `earnings.parquet` | Source-grounded theme evidence | TIL does **not** own read-through | E9 | Binder `theme_catalyst_binder.py:17-30`; digest `theme_context: []` |
| Price incorporation / catch-up | Has the tape already moved | PARTIAL | Stock PEAD copy; group `drift` | Stock page; group drift leg | Prices + calendar | Event-window incorporation object | Neural-graph docket | E8 / E14 | `stock.html.j2:1580-1645`; not a CEI field |

---

## 5. Distribution and consumers

| Capability | User job | State | Sources | Production surface | Data source | Missing deps | Governing doc | E-wave | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| Public event archive | Browse admitted call records | PROVEN_LIVE | `templates/earnings_wire/`; `scripts/build_earnings_public_wire.py` | `https://www.mastermind-x.com/stocks/earnings/` | Admitted story packets | Release/filing/slides disclosed absent | Handoff §3.2 | E12 (do not replace) | Live 2026-08-16: **3361** admitted records, 4000 ingested, 639 held, 2636 tickers, **0 model calls** |
| Public event analysis | Synthesized event page | REJECTED_BY_DESIGN (current Wire) / NOT_BUILT (cited analysis) | Wire copy says source-first, not analysis | Wire articles are excerpt archives | Transcript facts | Cited analysis is E12, not a Wire rewrite | Wire templates; masterplan §2 | E12 | Live kicker: “This is a source record, not a synthesized analysis” |
| Weekly intelligence | Week’s pattern across calls | PROVEN_LIVE | `context_packets.py` `build_weekly_intelligence` | `/stocks/earnings/weekly/` | Public wire catalog | Non-transcript sources | Handoff §3.2 | E12 | Live week 2026-07-27→2026-08-02: 205 records, 2460 exact facts |
| Ticker dossier CI block | Glance earnings on the stock page | PROVEN_LIVE | `site/assets/js/company-intelligence-dossier.js`; `app/company_intelligence.py` | Dossier + `/api/company-intelligence/{ticker}` | History + score overlay + tx index | Claim-grade citations | Handoff §3.2 | E2 | AAPL API 2026-08-16 `status: partial`, `claim_citations_pending: true`, “Wording not yet checked” path |
| Stage | Season / QoQ scores | PROVEN_LIVE | `engine/stage_analysis.py`; builders | `stage_analysis.html` | R2 scores + history | Exact-evidence spine is not Stage authority | Handoff §3.1 | consume only | Health `ready`; `is_context_only: true` |
| Terminal workspace | Deep research on one event | PARTIAL | CI v1 Brief/Transcript/History/Topics/Sources | `/analysis?symbol=&page=intelligence` | Same CI contract | v2 claim-cited Brief, Peers, Slides, calendar | `COMPANY_INTELLIGENCE_V2_DELTA_SPEC.md` is **spec, not live proof** | E2 | Spec lines 1–4: “Not an implementation.” |
| Brain / Neural Web | Compact cited context | PROVEN_LIVE (bounded) | `context_packets.py`; `earnings_context_reader.py` | Private R2; synapse `earnings-evidence-context-latest` | Evidence catalog | Event knowledge packet (facts/deltas/Q&A/graph) | Synapse; masterplan §1.2 | E13 | Reader is private-store-only; compact excerpts, not event graph |
| Press / research | Editorial derivative | DARK_OR_DISCONNECTED | `scripts/stage_earnings_story_press.py` | Manual workflow, kill-switches off | Story packets | Auto publish | Handoff §3.2 | E12 | `earnings-story-press-stage.yml` requires `PRESS_PUBLISH_ENABLED` |
| X / alerts | Fast public print | DARK_OR_DISCONNECTED (CEI→X) / PARTIAL (SEC marketing cards) | `engine/marketing/earnings_call_lane.py`; `marketing-earnings-wire.yml` | SEC cards scheduled; CEI lane unwired | EDGAR vs Chronicle | Wire `enqueue_event` for CEI stories | `EARNINGS_WIRE_PROGRAM.md` | E12 | `earnings_call_lane.py:3-8` “NOT WIRED TO ANYTHING TODAY” |
| Prophet context | Post-selection annotation only | PARTIAL | `prophet_bridge.py` | After candidate selection | Exact context packets; legacy scores | R0-C retire `earnings_call_sent` live influence | Handoff R0-C; `DNR:HOLD-PSQ-TILT-CLOCK` | E14 (shadow only) | `prophet_bridge.py:2757` refuses unless `may_rank/size/gate=false` |
| Catalyst forward ledger | Gradeable forward targets | PARTIAL | `theme_catalyst_binder.py`; Stage `forward_ledger.jsonl` is Stage not CEI | Theme `days_to_earnings` | Calendar dates | Four-target CEI ledger | Neural-graph docket | E14 | Binder loads `earnings.parquet` |

---

## 6. Counts

| State | Rows |
|---|---|
| PROVEN_LIVE | 14 |
| PARTIAL | 32 |
| SPEC_ONLY | 10 |
| NOT_BUILT | 6 |
| DARK_OR_DISCONNECTED | 3 |
| REJECTED_BY_DESIGN | 1 (Wire-as-analysis; competitor clones also rejected, not counted as product jobs) |
| BROKEN | 0 as a whole capability; **plane splits** are recorded as PARTIAL + discovery |

Competitor clones of Quartr / EarningsCall.ai / Jodie / Struct / EquityDesk remain `REJECTED_BY_DESIGN` (`EARNINGS_COMPANY_EVENT_SUITE_REMAINING_BUILD_HANDOFF_FOR_CLAUDE_2026-08-06.md:9`).

---

## 7. What E1 is allowed to change

Only rows owned by **E1**: identity, event id, release/8-K bind, transcript revision already live, deterministic facts from the bound release, typed consensus absence, correction replay through one consumer, exact per-claim citations on that event, compact payload.

E1 must not build search, slides, topics ML, relationships, Command Center, or Prophet authority.
