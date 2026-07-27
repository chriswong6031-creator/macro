# China/HK Native Data & Context Masterplan — by Fable (2026-07-25)

*Answers the operator's 2026-07-25 charter: "Is the current China/HK data context supportive
enough for Mastermind AI? Increase robustness of China analysis (market quirks, semi-closed
economy, China-specific rules/strategies/themes). We lack direct Chinese data sources that
can't be searched in English — find native sources (free API/websocket/other) and advance
integrations for Neural Web, Mastermind chat, and the Mastermind trading bot."*

*Grounded in a 4-lane census/research run (2026-07-25): estate census (70 CN/HK-facing
collectors = 61 asia-prefix + 9 US-lane `tushare_*`/`cn_*`; 98 engines matching
china|hk|cn_; 57 `data/china*` + 27 `data/hk*` stores), Mastermind/NW plumbing map, and two
live-verified source catalogs —
[SOURCE_CATALOG_MARKET.md](SOURCE_CATALOG_MARKET.md) and
[SOURCE_CATALOG_MACRO_POLICY_HK.md](SOURCE_CATALOG_MACRO_POLICY_HK.md) — plus a 39-endpoint
main-loop spot-verification committed as [PROBE_RESULTS_2026-07-25.json](PROBE_RESULTS_2026-07-25.json)
(re-runnable: `scripts/probe_china_sources.py`).*

---

## §0 ACCEPTANCE GATES (bind every wave; copy INLINE into every spawn prompt)

1. **Epistemics**: every artifact ships display/context tier (`may_rank/gate/size/escalate=false`,
   `is_context_only`). No scoring, no promotion, no "validated" wording. The gauntlet applies
   only at a future pre-registered promotion. Standalone-null factors are legal confluence
   inputs (context-accrual doctrine, CN-SYS-R1/R2 inherited).
2. **Probe-before-build**: a wave may only build on endpoints that are LIVE in the committed
   probe baseline. Any endpoint a wave builds on that is NOT yet in the baseline MUST be
   added to `build_probes()` (with a content check, not status-only) in that wave's own PR
   and the baseline re-committed. UNSTABLE endpoints (`em_fflow_daykline`,
   `jin10 datacenter-api`, DCE) may be opportunistic fallbacks, never anchors.
3. **Render budget**: new collectors are `china_*`/`hk_*`-named (asia-lane prefix match,
   `scripts/collect.py:350`), each nightly step ≤ ~2 min, throttled ≤1 req/s/host, graceful
   degrade on failure (0-row day ≠ crash), one-shot backfills run OFF the render path.
   `config/dag.yml` row per new builder step (CN-SYS-R11 inherited). NOTE the lane split:
   61 collectors are asia-prefix-matched; 9 CN-facing collectors (`tushare_*`,
   `cn_holder_sale_calendar`) run in the US-evening lane — any `china_*` collector reading a
   `tushare_*` store has a cross-lane ordering dependency (data is ~one lane stale).
4. **PIT honesty**: stores are append-only PIT from creation; backfills stamped
   `backfill=true`; data gaps printed (`data_gaps`), never silently zero-filled. Northbound
   daily net-flow is structurally dead (field-level zeroed since 2024-08) — it must never be
   read as a live zero.
5. **Redistribution posture**: derived signals only. Sell-side report text/target tables and
   wire full-text are never republished; consensus-revision aggregates, counts, tones only.
   No login-cookie scraping (Baidu Index, jisilu full list, Xueqiu) without a fresh ruling.
6. **Bilingual + design law**: any user-facing surface passes DESIGN_DOCTRINE + the
   frontend-design skill; glance tier = state + plain-word stance; no raw feeds dumped on a
   page; zh strings native (mojibake = red-flag test); no translated text in `title=`.
7. **Verification**: each wave's PR carries tests (fixture-pinned parsers; schema pins for new
   JSON contracts), a probe-harness run for its endpoints, and — for briefing/context changes —
   before/after token-budget measurements. A wave is not done until merged same-day and
   verified on the next asia-close render (or live API check for VPS surfaces).

---

## §1 The honest verdict: is today's estate Mastermind-ready?

**Category scorecard** (evidence: lane censuses 2026-07-25):

| Category | State | Evidence |
|---|---|---|
| A-share market brain (phase/participation/microstructure/policy) | **STRONG** | `china_market_state.v1` live, fresh (as_of 2026-07-25); 10-phase cycle lobe; limit tape 2011→; falsifier ledger |
| Stock-level intel (boards, setups, LHB, special-sits) | **STRONG** | china_alpha estate + setup_tier + 12-block briefing v6 |
| Native news (mainland) | **GOOD** | 3 native wires (见闻/金十/格隆汇) + CCTV tone + official corpora; native-first ranking law |
| Policy data | **GOOD data, MEDIUM structure** | corpora + phrase-diff + events.jsonl exist; no OBSERVED-OMO feed (a synthetic FR007-z proxy already occupies `kind=omo_mlf` — see W3), NO calendar organ |
| Macro | **MEDIUM** | EastMoney datacenter mirror works; property climate leg dead since 2025-12; everything proxied through one vendor. (RRR quiet since 2025-05-07 is an EVENT series at rest, not rot — see CNH-R10) |
| Funding/rates | **MEDIUM-THIN** | FR007 via akshare; SHIBOR store is a 44-session window (since 2026-05-26, `data/china_macro/rates.parquet`); chinamoney/chinabond never called directly |
| Flows/positioning | **MEDIUM** | margin + southbound + Tushare moneyflow live; missing: ETF shares daily, CB breadth, holder counts, fund issuance; no CFFEX positioning |
| Disclosure/interaction plane | **THIN** | CNINFO headline metadata only; no 互动易/e互动, no sell-side revision stream |
| Alt-data | **THIN** | 70-city property + rebar; missing CPCA autos, SCFI, AQI; climate leg dead |
| Hong Kong | **THIN across the board** | no HK intel bus, no HK lens, 0 HK lobes chartered, no HK native wire, HKMA underused, bot's HK book reads China's regime file |
| LLM last-mile | **WEAKEST LAYER** | production chat (`brain_gateway`) registers `read_china_decision_packet` (`brain_gateway.py:238`) but nothing pre-routes/seeds it — the deterministic CN router exists only on `/api/ask` (`ask_brain.py`); china NW packet = 5 blocks/6KB vs US 20/10KB; bot has 7 CN tools vs 26 US; `chinaaltdata/mastermind.json` built but `external_consumers: []`; no knowledge pack |

**Verdict**: Mastermind is genuinely well-fed for *display-grade China regime and tape
questions* — the CN-SYS spine (2026-07-08) already encodes the semi-closed-market quirks the
operator names (T+1, price limits, who-controls, policy-put phases). It is **not yet
supportive for deep native-context analysis**: the LLM-facing last mile is under-plumbed
(routing, budgets, tools), HK is materially behind China everywhere, and a handful of
native-only planes Chinese institutions watch (investor Q&A, sell-side revisions, funding
curve, CPCA, holder counts) are absent. **The binding constraint is the last mile + specific
native planes, not raw breadth** — the estate already has 70 CN/HK collectors.

## §2 What the source research actually found (2026-07-25, all live-verified)

**Newly available, high value (anchor-grade, in the committed probe baseline):**

- **Interaction plane**: 互动易 (`irm.cninfo.com.cn`, SZSE investor Q&A) and 上证e互动
  (`sns.sseinfo.com`) — genuinely native-only company color, machine-readable, keyless.
- **Sell-side stream**: `reportapi.eastmoney.com/report/list` — ratings, target prices,
  EPS forecasts with revision history. The consensus-revision plane US-side has via analysts.
- **Positioning**: `RPT_HOLDERNUMLATEST` (股东户数, quarterly retail concentration);
  SSE/SZSE official **ETF share/scale daily** (deepens the existing 21-fund/~6-week
  `etf_share_chg` window flagged in CN-SYS-R4 — see W2); `RPT_BOND_CB_LIST` full convertible
  universe (1,038 rows; jisilu is login-capped at 30 — use EastMoney); 新发基金 fund issuance.
- **Funding curve**: chinamoney CFETS `FrrHis` + `frr-chrt.csv` (FR001/FR007/FR014 +
  FDR fixings — the "liquidity temperature" PBOC-watchers actually trade) and CGB
  market-maker quotes (`CbMktMakQuot`) — all keyless, no session dance needed.
  Jin10 CDN `il_1.json` = full-tenor SHIBOR history, zero-auth (our current SHIBOR window
  is 14 days).
- **Wires**: Futu (`news.futunn.com` flash JSON, CN+HK, sub-minute) and THS push
  (`news.10jqka.com.cn/tapp/news/push/stock`) — wire redundancy plus **HK's first native
  wire candidate**. cls.cn/thepaper remain dead (re-confirmed).
- **Alt-data**: CPCA `data.cpcadata.com/api/chartlist` (auto/NEV monthly by manufacturer
  and fuel type, keyless, akshare wrappers exist, unused in repo); GACC **English** portal
  (Chinese site 412-blocked) for by-country trade; AQI via waqi.info free token;
  SCFI/CCFI pages reachable (scrape).
- **HK**: HKMA open API — HIBOR all tenors, **daily monetary base incl. aggregate balance**
  (peg-pressure organ material), monthly bulletins; keyless, textbook JSON. C&SD
  `tradeidds` API live (general `get.php` is gateway-blocked — sibling-subdomain pattern).
  CCASS + southbound shareholding search reachable (form-scrape).
- **Futures**: SHFE daily (via `www.` host), CZCE daily txt, CFFEX **monthly ZIP** (the CSV
  path is connection-blocked) — a CFFEX positioning tape (China's COT analog) is feasible at
  monthly grain; GFEX transport OK. DCE is fingerprint-blocked (412).
- **Policy**: gov.cn policy-library **search JSON** responds (params need one devtools pass);
  PBOC OMO bulletin pages reachable — **no machine mirror of OMO exists anywhere** (not
  EastMoney, not Jin10), so an OMO scraper is a genuine edge.

**2024→2026 regime facts to encode (so signals don't assume dead feeds):**
1. Northbound daily net-flow: field-level zeroed (verified `dayNetAmtIn=0.0` on a real
   trading day); quarterly holdings only. **Southbound daily net-flow is alive with real
   numbers** — same report.
2. 转融券 (securities re-lending) suspended since 2024-07, balance zeroed, no restart as of
   2026-07 — any factor keyed to it measures literal zero.
3. Program-trading reporting regime (CSRC 2024-10) = compliance regime, NOT a public feed.
4. ChinaClear investor counts are **annual** now (2025: 13.87M new, 250.7M total) — "new
   accounts monthly" is not a buildable participation input.
5. Xueqiu's long-shared akshare token is dead (400016) — real login required; out of posture.
6. Caixin PMI is rebranding (S&P licensing partner "RatingDog" appears in 2026 calendars) —
   verify naming before user-facing copy.

**Failure-mode taxonomy** (from the catalogs; the load-bearing operational insight):
WAF-ACL (NBS easyquery) ≠ WAF-challenge (GACC-CN) ≠ generic anti-bot (thepaper) ≠ DNS-dead
(shibor.org) ≠ TLS-fingerprint reject (MOFCOM data) ≠ path-specific gateway block (EastMoney
`clist/get` dead while `stock/get`/`kline/get` live on the same host). **Organizations are
rarely uniformly blocked — probe sibling subdomains/paths before declaring a source dead**
(CPCA, censtatd, GACC all have one blocked and one open door).

**Egress caveat**: all verdicts are relative to this runner's egress (2026-07-25 baseline:
datacenter IP, Zenlayer/US). If the network posture changes, re-run
`python3 scripts/probe_china_sources.py` and re-baseline before trusting any claim here.

## §3 Rulings

- **CNH-R1 (epistemics)** — §0.1 verbatim. This program is context accrual; zero new
  backtest studies; preregistered constructs (e.g. `china_policy_events` prereg) untouched.
- **CNH-R2 (native-first transport)** — where an official/native source and an EastMoney
  proxy both exist, new collectors prefer the native transport and keep the proxy as
  documented fallback (breaks the single-vendor SPOF the census found). Existing collectors
  are NOT migrated for migration's sake.
- **CNH-R3 (probe law)** — `scripts/probe_china_sources.py` is the accessibility arbiter:
  probe before build, probe before declaring dead, re-baseline on egress change. The harness
  is manual-only (never wired into nightly).
- **CNH-R4 (no anchoring on unstable endpoints)** — `em_fflow_daykline` (verified once, then
  connection-refused), `jin10 datacenter-api` (502-flaky; its CDN mirrors are stable), DCE
  (fingerprint-blocked) are fallback-only. Tushare stays primary for moneyflow.
- **CNH-R5 (do-not-re-add)** — cls.cn nodeapi, api.thepaper.cn, people.com.cn RSS, Xueqiu
  shared-token, northbound daily net: re-add only after a probe run shows genuine revival
  (thepaper's 200-wrapped error envelope is not revival).
- **CNH-R6 (redistribution)** — §0.5 verbatim; sell-side stream is consumed as revision
  aggregates/counts; wires as timing/tone inputs; CCASS as aggregates.
- **CNH-R7 (HK parity principle)** — HK stops riding China's plumbing: own intel bus, own
  brief lens (or first-class hk state block), own chartered lobes, and the trading bot's HK
  book must read `hk_regime/latest.json` (today it reads China's file —
  Mastermind repo `brain/regime_frame.py` aliases hk→china and the vendored checkout has no
  hk_regime dir at all).
- **CNH-R8 (LLM laws inherited)** — MNZ-R5/CN-SYS-R14: LLMs read and explain calibrated
  artifacts; never originate signals/scores/escalations; knowledge pack is versioned,
  sourced, dated facts — never model-generated state.
- **CNH-R9 (registry law)** — every new artifact gets a full `config/synapse.yml` entry
  (tier/horizon_role/freshness_sla/asof_field...) with the `may_rank=false` stamp; lobes via
  `config/lobe_charters.yml` under owner_program `china-system` (CN) / new `hk-system` (HK);
  the metabolism genesis pathway is respected — nothing self-anoints above display tier.
- **CNH-R10 (rot repair is in-scope — with corrected diagnoses, red-team 2026-07-25)** —
  dead series are fixed or honestly retired, never left "ok"-but-stale; but a quiet EVENT
  series is not rot:
  - `china_macro/rrr` is **NOT rotted and MUST NOT be re-pointed**: it is an event series
    (one row per PBOC change; 55 rows 2007-01→2025-05-07; no RRR change since = correctly
    empty), and it is **frozen by pre-registration** (`CHINA_POLICY_EVENTS_PREREG.md` F-A,
    n=26, date semantics pinned to `RPT_ECONOMY_DEPOSIT_RESERVE` REPORT_DATE; void rule
    applies). `engine/china_policy_transmission.py:_seed_rrr_events` reads the same file.
    If freshness monitoring is wanted, add a SEPARATE `rrr_level` daily-observation store —
    never mutate `rrr.parquet` or its upstream.
  - `china_property/climate` — genuinely dead (max 2025-12-01 on a monthly cadence): find
    the moved upstream or retire the leg honestly (W4).
  - `narrative_divergence` briefing block — **dead-wire class, not missing-producer**: the
    producer `engine/missing_tape_gdelt.py` exists and writes exactly
    `data/missing_tape/tone_divergence.parquet`, and `config/qual_ladder.yml` registers
    `missing_tape.divergence_z` — but no `scripts/` builder or `config/dag.yml` step ever
    invokes it (new-organ nightly-wiring-check law). Wire the EXISTING producer or retire
    both the block and the qual_ladder key — do not build a new producer.
  - `hk_gdelt` bellwethers — tickers are already correct (`collectors/hk_gdelt.py:90,92`);
    the defect is the GDELT **query terms** (`["JD.com"]` returns nothing; smic accrues
    volume but all-NaN tone). Fix the query terms or drop both entities and print the
    coverage null.
  - "Adapter didn't error" ≠ fresh (vacuous-green law) — but freshness expectations must
    match series semantics (event vs observation) before declaring rot.
- **CNH-R13 (bus schema authority)** — `site/china_intel/briefing.json` is owned by
  `owner_program: china-alpha` (`config/synapse.yml:3440`) and `engine/china_intel_bus.py`
  is READ-ONLY to non-owning programs (CN-SYS-R6). This program does NOT edit the bus:
  new briefing blocks (W1 `interaction`, W3 calendar) are **commissioned to the owning
  program** as additive v7 bumps, and that same PR heals the already-stale registry field
  (`config/synapse.yml:3445` says v5 while the live artifact is v6).
- **CNH-R11 (display wave is optional + adjudicated)** — operator note 2026-07-25: front-end
  integration only where a feed earns a glance-tier stance on an EXISTING page; explicitly NO
  standalone raw-feed page (the unused `macro_signals.html` is the named anti-pattern).
- **CNH-R12 (calendar is data + rules, not vibes)** — algorithmic entries (LPR 20th, NBS
  release days, HKMA cadences) are encoded as rules; announced-ad-hoc entries (MLF, Politburo
  exact dates) come from monitored feeds/scrapes; political rhythm (Two Sessions, CEWC,
  plenums) is static knowledge refreshed manually. Every calendar row carries its source class.

## §4 Architecture: three pillars

```
 PILLAR A — native data plane            PILLAR B — knowledge layer         PILLAR C — LLM last-mile
 (collectors → data/ → engines)          (versioned facts + doctrine)       (routing, budgets, tools)
 W1 interaction/sell-side/holders   ┐    W6 china knowledge pack v1     ┌ W7 brain_gateway CN router
 W2 funding curve/CB/ETF shares     ├──▶ (quirks, regime history,   ───┤   china_slice budget parity
 W3 OMO/policy corpus/calendar      │    calendar rules, data-regime   │   bot CN/HK tool parity
 W4 alt-data (CPCA/AQI/SCFI/GACC)   │    facts, failure taxonomy)      │   chinaaltdata→bot wiring
 W5 HK depth + hk_intel_bus         ┘    bilingual, sourced, dated     └ hk lens + hk_regime vendoring
                                                                          W8 (optional) display chips
```

Pillar A fills the native planes; Pillar B turns the existing 1,234-line A-share mechanics
research (already written, `research/A_SHARE_MARKET_MECHANICS_AND_CHINA_SYSTEM_UPGRADE_FOR_CLAUDE.md`)
plus this program's regime facts into an **LLM-consumable, versioned knowledge pack** — the
piece the operator's "deeper understanding and context-driven awareness" ask actually needs;
Pillar C closes the asymmetry lane 2 mapped (the same data, actually reachable by the three
AI consumers).

## §5 Build waves

Model routing per CLAUDE.md: waves build via `builder` (Opus) with these gates inline;
design-touching steps via `designer`; this masterplan and wave adjudications stay in the
main loop. Each wave = one PR off fresh origin/main, same-day squash-merge, verified on the
next asia-close render.

### W0 — This PR (registry + harness + plan)
Masterplan + two source catalogs + probe harness + committed baseline
(`PROBE_RESULTS_2026-07-25.json`). No engine changes. Gate: harness runs clean — final
baseline 39 probes: **37 ok / 1 empty-dated** (`em_zt_pool`: keyless probes get an empty
envelope; the production collector runs the gated `EASTMONEY_UT_TOKEN` path) / **1
flaky-degraded** (`em_fflow_daykline`, CNH-R4) / **0 deviating**.

### W1 — Interaction & sell-side plane (builder)
New collectors (all keyless, all in the probe baseline):
- `collectors/china_irm.py` — 互动易: per-name Q&A pull for the board universe (drip-paged)
  + a market-wide Q&A-velocity aggregate. Store `data/china_irm/`.
- `collectors/china_einteraction.py` — 上证e互动 (uid map built once, cached; M-effort
  2-step documented in the market catalog). Store `data/china_einteraction/`.
- `collectors/china_reports.py` — sell-side stream: per-name rating/TP/EPS revisions +
  daily aggregate (upgrades/downgrades/initiations counts). Store `data/china_reports/`.
- `collectors/china_holder_counts.py` — 股东户数 quarterly full-market snapshot + change
  tape. Store `data/china_holder_counts/`. (Named to avoid collision with the existing,
  unrelated `collectors/cn_holder_sale_calendar.py` = 减持 sale windows.)
Feeds: new additive `interaction` briefing block — commissioned to the bus's owning program
per CNH-R13, never edited from this program; revision/holder legs registered as `pending` in
the china signal-lab registry (collected + accruing, NOT scored — validate-before-score,
exactly the Tushare-chips precedent). Gates: §0 + fixtures for every parser + throttles
≤1 rps/host + per-step ≤2 min. **IRM budget arithmetic**: 互动易 is a 2-step flow and the
board universe is ~110 names — a full sweep does not fit one step. Org-ids are resolved once
and cached (like the SSE uid map); the Q&A pull is **sharded across nights** (≤40 names/night
with a persisted cursor) plus one cheap market-wide velocity call nightly; never a full
per-name sweep in a single step.

### W2 — Funding & risk-appetite plane (builder)
- `collectors/china_funding.py` — chinamoney `FrrHis` (FR/FDR full set) + `frr-chrt.csv`
  + CGB market-maker quotes; Jin10 CDN `il_1.json` full-tenor SHIBOR (replaces the 14-day
  window as the deep store; EastMoney reportName stays fallback per CNH-R2).
  Store `data/china_funding/`.
- `collectors/china_cb.py` — EastMoney CB universe + jisilu CB **index** (the index endpoint
  is keyless; the login-capped list is not used, CNH-R5/R6). Store `data/china_cb/`.
- ETF shares: **widen and deepen the EXISTING store — do NOT create a new one.**
  `collectors/china_flows.py:_etf_shares()` already pulls `RPT_FUND_ETFLIST` for 21 tracked
  ETFs → `data/china_flows/etf_shares.parquet`, and `engine/china_participation.py` already
  computes a non-null `etf_share_chg` from it. The W2 change: swap the 21-code EastMoney
  basket for the full-universe SSE `commonQuery` ETF scale + SZSE xlsx (native transport per
  CNH-R2), **keeping the same store path and the participation-engine contract**. This
  deepens the ~6-week/21-fund window CN-SYS-R4 flags — the field is present today, just
  shallow and narrow.
- `collectors/china_fund_issuance.py` — 新发基金 weekly snapshot. Store `data/china_fund_issuance/`.
Feeds: pboc_stance/policy lobe gains funding-curve depth (FR007-vs-DR007-vs-SHIBOR spread
context); participation lobe reads the deepened etf_share panel + fund issuance; crowding
gets CB-premium context leg (pending-tier).

### W3 — Policy corpus, OMO, calendar, wires (builder)
- `collectors/china_omo.py` — PBOC OMO daily bulletin scrape (reverse-repo/MLF amount+rate
  from title strings; the no-machine-mirror edge). **Namespace caution (red-team 2026-07-25):
  `kind=omo_mlf` in `data/china_policy_transmission/events.jsonl` is already occupied by
  SYNTHETIC events** — `engine/china_policy_transmission.py:_seed_omo_mlf_events()` emits
  FR007 z-score exceedances under that exact kind/source (25 rows live), and `_event_hash`
  keys on title so observed/inferred same-date pairs would NOT dedup. Observed operations
  therefore ship as **`kind=omo_observed` with a `provenance: "pboc_bulletin"` field on
  every row**; reconciling or retiring the synthetic seeder is commissioned WITH the
  owning program (CNH-R13), never done unilaterally here.
- Corpora enrichment: gov.cn policy-library search JSON (one devtools pass for params;
  fallback = existing layout scrape), NDRC/CSRC/MIIT list scrapes into the existing corpora
  collector. GACC English monthly tables → `data/china_trade_detail/` (by-country exports).
- **`engine/china_calendar.py` + `scripts/build_china_calendar.py`** → structured forward
  calendar `site/chinastatedata/calendar.json`: NBS release days (stats.gov.cn schedule page
  + rule), LPR 20th rule, MLF window (monitored via OMO feed), Politburo/CEWC/Two-Sessions
  windows (static rules per CNH-R12), HK data days (C&SD cadence), CN earnings-season
  windows (existing `china_earnings` calendar join).
- Wire redundancy: add Futu flash + THS push as wires 4/5 in `engine/cn_newswires.py`
  (same shared-cache contract; native-first ranking law observed; HK-tagged items flow to W5).
Gate additions: calendar JSON schema-pinned; OMO parser fixture-tested against 3 real
bulletin formats; no translated `title=`.

### W4 — Alt-data plane (builder)
- `collectors/china_cpca.py` — all 6 chartlist types (total/manufacturer/category/
  country/segment/fuel), monthly. Store `data/china_cpca/`.
- `collectors/china_aqi.py` — waqi city feed (free token secret `WAQI_TOKEN`), daily, a few
  industrial cities. Store `data/china_aqi/`.
- `collectors/china_freight.py` — SCFI/CCFI weekly scrape (sse.net.cn). Store `data/china_freight/`.
- MOA pork: probe `scs.moa.gov.cn/scxxfb/` first (UNVERIFIED in catalog); build only on a
  live probe, else defer with the finding recorded.
- Rot repair: `china_property/climate` — find the moved upstream or retire the leg honestly;
  `hk_gdelt` dead bellwethers replaced (jdcom→9618.HK-appropriate name, smic→0981 alt) or dropped.
Deferred with reasons documented (NOT built): Baidu Index (login-cookie posture, CNH-R5),
box office (signed SPA API), Amap (mainland-phone registration), 涨停原因 vendor tags
(commercial license; a self-built NLP tagger over announcements is a future program),
THS hexin-v signer (akshare's battle-tested wrappers only).

### W5 — HK depth + HK bus (builder; the parity wave)
- Expand `collectors/hkma.py`: daily monetary base incl. aggregate balance (VERIFIED T-1
  fresh via the `daily-monetary-statistics` family), discount-window + EF-bills
  (probe-gated per §0.2 — not yet in the baseline). **HIBOR cadence correction (red-team
  2026-07-25): the `monthly-statistical-bulletin` HIBOR path publishes daily observations
  MONTHLY — its latest record is prior month-end (~25d stale), so it cannot feed a daily
  organ.** New organ `engine/hk_peg_pressure.py` v1 therefore = aggregate-balance trend +
  HKD position in the 7.75–7.85 band (both verified daily); an intraday/daily HIBOR leg is
  added only after probing a daily source (HKAB fixing page or a Jin10 CDN HIBOR report —
  candidates, unverified). Display-tier.
- `collectors/hk_stats.py` — **trade only** via the verified C&SD `tradeidds` API (dataset-
  hash enumeration from data.gov.hk is an explicit in-wave step + probe entries). Retail
  sales and visitor arrivals are **deferred pending a probe**: the general
  `censtatd.gov.hk/api/get.php` is gateway-blocked, and there is no evidence the trade
  subdomain serves non-trade tables — same gating discipline as MOA pork (W4).
- `collectors/hk_ccass_southbound.py` — southbound per-name holding concentration
  (mutualmarket.aspx scrape, 12-month window honesty).
- centadata CCL hardening for the existing fragile collector.
- **`engine/hk_intel_bus.py` → `site/hk_intel/briefing.json` (hk_intel.briefing.v1)**:
  news (Futu HK-tagged wire — HK's first native wire), regime, conditions, command panel,
  shorts, southbound, peg pressure, property, filings bus. Mirrors the China bus contract
  (asof/staleness/is_context_only).
- `master_brain`: add `LENSES["hk"]` with `gather_hk_state()` (HK briefing + slim
  CN + US backdrops) → `site/hk_brief.json`. (Adjudicated: a lens, not a fatter china-lens
  block — the bot has a separate HK book and the operator asked for HK-specific robustness.)
- Charter `site-hk-regime` + `site-hk-command` lobes in `config/lobe_charters.yml`
  (new owner_program `hk-system`), full synapse entries per CNH-R9.
- Mastermind bot repo (separate PR there; red-team-corrected scope): `brain/hk_mcp.py` is a
  **China clone, not a thin alias** — its tools are China-named (`get_china_regime` etc.),
  read `china_regime/latest.json` directly via `china_intake._read`, and never import
  `regime_frame`. The fix is therefore two independent paths: (a) rewrite `hk_mcp.py` to HK
  artifacts with HK-named tools (`get_hk_regime`/`get_hk_brief`/`get_hk_peg`); (b) vendor
  `data/hk_regime/` and fix `brain/regime_frame.py`'s hk→china alias for every OTHER
  consumer of the region frame.

### W6 — China knowledge pack v1 (main-loop design, builder implementation)
`data/china_knowledge/pack_v1/` — one JSON file per section, each entry
`{id, en, zh, source, as_of, tags}`:
1. **market-structure quirks**: T+1; board limit widths incl. eras (main 10%, STAR 20%
   2019-07→, ChiNext 20% 2020-08→, BSE 30%, ST 5%, IPO no-limit windows — reuse CN-SYS-R12
   wording); auction mechanics; sealed/failed-seal behavior; short-selling constraints;
   QFII/Connect access shape.
2. **participant taxonomy**: retail/institutional/margin/state-proxy/offshore vocabulary
   aligned to the participation lobe's `who_controls` enum; National Team intervention
   patterns; insurer/dividend flows.
3. **policy transmission map**: instrument ladder (OMO→MLF→LPR→RRR→fiscal), phrase-diff
   significance, meeting calendar rhythm, "policy put" mechanics.
4. **regime history 2005→2026**: the analog map distilled from the mechanics doc §4 + late-
   2024→2026 policy-put rally read — aligned to the cycle-phase lobe's 10-phase vocabulary.
5. **strategy doctrine**: what ports from US and what doesn't (momentum weak, reversal+
   turnover robust, limit-up chase dead, confirmation-gating kills the reversal edge);
   fillability/T+1 realism; defensive = relative not absolute.
6. **data-regime facts**: northbound dead (quarterly holdings only), southbound alive,
   转融券 suspended, program-trading reporting regime, ChinaClear annual cadence,
   youth-unemployment methodology break (2023-08 suspension → 2024-01 revised basis),
   RRR/LPR mirror provenance.
7. **source-failure taxonomy** (from §2) — so the LLM can reason about "why is this feed
   empty" instead of hallucinating.
Build step → `site/china_intel/knowledge.json` (chunked by section, per-section byte caps).
Consumers wired in W7. Gates: every entry sourced+dated; zh native-authored (not
back-translated); schema-pinned test; NO model-generated claims (CNH-R8).

### W7 — Mastermind last-mile parity (builder; the payoff wave)
- **Production chat router**: `brain_gateway` gains the deterministic CN pre-router.
  Precision (red-team): the TOOL is already registered in its allowlist
  (`brain_gateway.py:238`) — what's missing is the deterministic pre-routing/seeding that
  `ask_brain.py` has via `_CHINA_TRIGGER_TERMS`. W7 adds the seeding (reusing those terms),
  injecting `read_china_decision_packet` + knowledge chunks for CN-routed queries; HK terms
  route to the W5 packet.
- **NW packet parity**: `brief_context` china_slice budget 5 blocks/6,144B → 10 blocks/
  10,240B; `themes_china` actually China-filtered; new blocks: calendar (W3), knowledge
  digest (W6), interaction/sell-side aggregates (W1). Measured before/after; macro_slice
  budget untouched. While in there, repair the pre-existing `_CHINA_DROP_ORDER` drift (the
  docstring lists 5 entries incl. cortex; the actual list has 4 and omits cortex even though
  `_build_china_slice` emits it) so new blocks drop in documented order.
- **China lens enrichment** (`gather_china_state`): add `forward_calendar` (W3),
  `special_situations` (already in briefing v6 — add to the whitelist), CN desk
  track-record block (the CN grader exists since #3196/#3207), `funding` (W2 curve).
- **Bot wiring** (Mastermind repo PR): `chinaaltdata/mastermind.json` gains
  `external_consumers: [mastermind:vendored]` + bot `china_mcp.py` tools to parity-relevant
  depth: `get_china_altdata`, `get_china_news`, `get_china_calendar`, `get_china_knowledge`,
  `get_china_microstructure`; HK book equivalents per W5. (26-vs-7 tool gap — verified
  counts, `bot_mcp.py` 20 read + 6 action vs `china_mcp.py` 7 — closed to the extent CN data
  exists; no tool fabricates a plane we don't have.)
- **Decision packet v2**: `assemble_china_decision_packet` reads briefing v6 blocks
  (analysis/conviction/what_changed) alongside market_state — still `is_context_only`,
  still no fused score (CN-SYS-R13).
Gates: §0.7 token budgets; response-log QA — 10 China + 5 HK canonical questions before/after
(stored under `data/mastermind_responses/qa/` per the response-log program); zero regression
on US-lens budgets; guard tests for router determinism.

### W8 — OPTIONAL display adjudication (designer; per operator note 2026-07-25)
Only chips on EXISTING pages; each goes through the design lane; skip-by-default posture:
| Feed | Surface | Default verdict |
|---|---|---|
| Sell-side revision + 互动易 digest | china_intel hub panel | **build** (the hub is the intel surface; counts + plain stance, no report text) |
| CB breadth + ETF share flow chips | china_altdata crowding/participation panels | build **iff** W2 stores prove 2 weeks stable |
| CPCA NEV mix | china_altdata alt-planes panel | **build** (monthly, cheap, genuinely glanceable) |
| Aggregate balance + peg distance | hk.html liquidity organ | **build** (HK's "one number that matters") |
| Calendar "next 2 weeks" strip | china.html + hk.html | **build** (answers "what do I watch") |
| Holders/pork/SCFI/AQI raw series | none (hover/detail tier only if ever) | **skip** |
**No standalone feed page** (macro_signals.html anti-pattern, CNH-R11).

**Sequencing**: W1 ∥ W2 (disjoint stores) → W3 (bus schema after W1) ∥ W4 ∥ W5 → W6 → W7 →
W8 after a 2-week accrual read. Bot-repo PRs (W5/W7 parts) commissioned per the spawn-handoff
law with gates inline; no child self-merge on the bot repo.

## §6 Accrual clocks (register in experiments registry at each wave's merge)

| Clock | Date | What matures |
|---|---|---|
| Interaction/sell-side planes first descriptive review | 2026-10-25 | 90d of Q&A velocity + revision aggregates — descriptive only |
| ETF-share participation upgrade folds into CN-SYS participation review | 2026-10-08 | existing CN-SYS clock, now with full-universe etf_share depth (field already live, previously 21 funds/~6 wks) |
| Knowledge-pack QA read (response-log sampling) | 2026-08-25 | do CN answers cite pack facts correctly; zh quality |
| W8 display adjudication | ~2026-08-08 | 2 weeks of W2 store stability |
| CFFEX monthly-ZIP positioning tape feasibility ruling | 2026-09-01 | one month of ZIP pulls parsed clean |

## §7 Non-goals and honored kills

- **No scoring/promotion** anywhere in this program; preregistered `china_policy_events`
  constructs untouched (incl. the RRR event store per CNH-R10); A-share reversal-gating kill
  and LHB-copy kill honored (data layers legal, buy-trigger constructions remain dead);
  **RIC-R3 honored** (DO_NOT_REBUILD: calendar/event-window-gated risk legs are forbidden at
  any tier) — the W3 calendar organ, W7 `forward_calendar` block, and W8 calendar strip are
  display context ONLY and must never gate, size, or feed a state/risk channel.
- **No options-chain plane** this program (QVIX remains the CN vol read; an SSE 50ETF/300ETF
  option-chain collector is a future candidate, listed here so it isn't re-invented blind).
- **No login-cookie scrapers** (Baidu Index, Xueqiu, jisilu full list) — posture change
  requires an operator ruling.
- **No northbound-revival assumptions**; no 转融券 factors; no "new accounts monthly" inputs.
- **No new standalone feed pages.**
- The two "Mastermind" namesakes stay distinct: `engine/china_masterminds.py` (GTAA
  backtest flagship) is NOT the AI-consumer contract (`briefing.json` / bot books).

## §8 Program record

- 2026-07-25: W0 shipped (this PR) — masterplan, catalogs, probe harness, committed
  baseline. Census: 70 CN/HK-facing collectors (61 asia-prefix + 9 US-lane), 98 engines,
  57+27 CN/HK data stores; briefing at v6; spine fresh same-day. Lanes: estate census,
  plumbing map, market sources (60+ endpoints), macro/policy/HK sources (~45 sources).
  Spot-verification: 13 anchor endpoints re-verified in the main loop; `em_fflow_daykline`
  and `jin10 datacenter-api` downgraded to unstable on retry evidence; thepaper
  200-error-envelope noted. Opus red-team (28 findings) folded pre-merge — 3 blockers
  corrected: RRR is a prereg-frozen event series (not rot); ETF shares deepen the existing
  `china_flows` store (not a new collector); observed OMO ships as `kind=omo_observed` with
  provenance (the `omo_mlf` namespace is occupied by synthetic FR007-z events).
- 2026-07-26: W1 shipped — `china_irm` / `china_einteraction` / `china_reports` /
  `china_holder_counts` collectors (display/context tier; four legs registered as
  `pending` in `engine/china_signal_lab.py`, nothing scored or surfaced), fixture-pinned
  parser tests against the live 2026-07-25 captures, 5 new probes (`irm_company_question`,
  `irm_index_search`, `sse_userfeeds`, `em_report_window`, `em_holdernum_full`) plus a
  strengthened `sse_einteraction` content check (min_bytes-only → `json_path=["content"]`
  + min_bytes), a `china-native-collectors` CI job, and the §6 clock registered as
  `cnh-w1-interaction-sellside-planes` (descriptive review 2026-10-25). Budget shape:
  互动易 and e互动 are per-name planes sharded ≤40 names/night behind a persisted cursor
  that is written at the TRUE stop position when the in-collector ~100 s guard fires;
  the e互动 uid map is built once and its build is RESUMABLE, so a truncated directory
  crawl continues the next night instead of masquerading as complete. Probe baseline
  re-run 2026-07-26 from the runner: 44 probes — 42 ok / 1 empty-dated (`em_zt_pool`,
  expected keyless state) / 1 flaky-degraded (`em_fflow_daykline`, CNH-R4) / 0 deviating
  (the W0 `sse_einteraction` probe's loose `{pageSize,page}` params were corrected to the
  production `{code,order,areaId,page}` contract — the loose set intermittently answers a
  near-empty envelope). Live dry-run before merge: all four adapters end-to-end against a
  scratch store — 1,207 Q&A rows / 27 SZ names + velocity total 94,789 (互动易), map-build
  night resumed-and-verified (e互动), 29 Sunday reports with honest per-class aggregates,
  full 5,535-name holder seed in 34 s. One-shot cache seeding committed (off render path):
  `china_irm/org_ids.json` 50/50 SZ resolved, `china_einteraction/uid_map.json` 2,312 SSE
  codes `complete=true` (directory exhausted at page 73) — night 1 runs productive.
  **First production night VERIFIED (2026-07-27 asia-close, data commit `7ef3e68604b`)**:
  all four sentinels clean (`n_failed=0`, `n_nulls=0`) with full 40-name shards inside the
  budget guard (both cursors advanced exactly 0→40, no truncation). 互动易 1,590 Q&A rows /
  40 SZ names (72% answered) + velocity `total_record=94,537` (vs 94,789 at seed — ES
  wobble, raw totals stored as designed); e互动 skipped the map-build night as intended
  (pre-seeded map, `map_built=0`) and pulled 284 rows — 26 of 40 shard names carried feed
  items, the rest are genuinely quiet names (empty feeds, not nulls); reports 34 rows with
  aggregates on all four window dates and `first_seen` populated (Monday-morning pull at
  ~18:00 CST — the rolling window re-pull collects the evening's reports tomorrow);
  holder counts full-market seed 5,537 rows (12 pages) with same-day notices included.
