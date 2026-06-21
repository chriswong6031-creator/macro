# Special Situations Desk — Phase-1 Build Spec

*Companion to [`SPECIAL_SITUATIONS_RECON_FINDINGS.md`](SPECIAL_SITUATIONS_RECON_FINDINGS.md). Grounded in a live codebase map (collectors / desk-site / LLM / emit / news subsystems). Implementation-ready; file paths and line refs are real as of branch `claude/friendly-colden-7d0392`.*

## Locked decisions
- **Market-cap floor: $100M** (applied to the covered company; drops nano/micro noise, keeps small-cap activist/take-private sweet spot).
- **Cross-border: YES — "US-anchored" scope.** Any situation where a **US-registered security** is a party (US acquiring/divesting a foreign business; foreign bidder for a US/ADR target; cross-listed FPI 6-K events; 13D/TO on US-registered ADRs). All of these hit EDGAR, so coverage is near-free. We do **not** pre-filter to a domestic watchlist — we ingest the whole EDGAR event stream and let the floor + enrichment decide. Pure foreign-domestic situations (e.g. a Japan-only activist filing on EDINET) stay **Phase 3**.
- **Cadence: once per (week)day**, as a step in the existing `daily.yml` build.

## Design doctrine (matches house style)
- **LEAF / display-only.** `engine/special_situations.py` declares `SCORED = False`, imports nothing from `conditions`/`regime`/`run`/scoring, and nothing in the scoring path imports it. Every emitted record carries `is_context_only: true` + a `disclaimer`. (Same contract as `catalyst_stock.v1` / `commodity_news`.)
- **Deterministic core, one thin LLM touchpoint.** Discovery, classification, floor, enrichment, stage = pure code. The only LLM call is the ~88-word summary, gated + cached so we pay once per *new* situation.
- **Two ingest lanes merged by company-date key:** (A) EDGAR event-forms (high precision), (B) GDELT newswire keyword lane for the form-absent categories (Strategic Reviews, Capital Returns, out-of-court Restructuring, Deal Terminations).

---

## 1. Architecture / data flow

```
                    ┌─────────────────────────────────────────────┐
 LANE A (EDGAR) ──► │ collectors/special_situations.py            │
   daily-index      │  · discover filings since last run          │
   form filter      │  · fetch header (8-K items) / primary doc   │──┐
                    └─────────────────────────────────────────────┘  │
                                                                      ▼
 LANE B (GDELT) ──► engine/ss_newswire.py (clone news_vector)   ─► data/special_situations/
   keyword themes     · PIT event store (event_id, keep-first)        events.parquet  (append-only)
                                                                      │
                                                                      ▼
                    ┌─────────────────────────────────────────────┐
                    │ engine/special_situations.py  (SCORED=False) │
                    │  classify(form,items,kw)->category           │
                    │  derive stage · apply $100M floor            │
                    │  enrich (mc/ev/metrics/biz from our feeds)   │
                    │  cross-border tag · dedup merge lanes        │
                    │  snapshot() -> dict                          │
                    └─────────────────────────────────────────────┘
                          │              │                 │
        (only NEW ids) ◄──┤              │                 │
   engine/ss_summary.py   │              │                 │
   gated DeepSeek/Haiku   │              │                 │
   88-word + zh, cached    ▼             ▼                 ▼
                    scripts/build_special_situations.py
                          │              │                 │
            site/special_situations.html │   data/regime/special_situations_latest.json (hub card)
                                         │
        site/stockdata/<T>.json["special_situation"]  ·  site/allocationdata/special_situations.json
                                         │
                          engine/master_brain.gather_state() -> state["special_situations"]
```

---

## 2. Lane A — EDGAR event collector  `collectors/special_situations.py`

New collector following the established EDGAR pattern (`collectors/edgar.py`, `collectors/sec_insider.py`): local `_get_json()`/`_get_text()` with 3-retry backoff, `time.sleep(0.12)` pacing (SEC <10 req/s), and the **email-bearing UA** (`smart_money.user_agent`) for `www.sec.gov/Archives`, plain UA (`edgar.user_agent`) for `data.sec.gov`.

### 2a. Discovery — EDGAR daily index (net-new; repo doesn't do this yet)
- Pull the **daily index** for every date since the last successful run (so Monday's build catches Fri-evening + weekend filings):
  `https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/form.{YYYYMMDD}.idx`
  (pipe/fixed-width: `Form Type | Company Name | CIK | Date Filed | File Name`).
- Keep rows whose **Form Type** ∈ the target set below. Persist a `last_index_date` watermark in `data/special_situations/_meta.json`.

**Target forms (high-precision, low-volume — classify directly):**
`SC 13D`, `SC 13D/A`, `SC TO-T`, `SC TO-T/A`, `SC TO-I`, `SC TO-I/A`, `SC 14D9`, `SC 13E3`, `SC 13E3/A`, `DEFM14A`, `PREM14A`, `DEFC14A`, `PREC14A`, `25`, `25-NSE`, `15-12B`, `15-12G`, `10-12B` (Form 10), `S-4`, `424B5` (rights context), `6-K` (FPI — heterogeneous, see 2c).

**8-K (high-volume — needs item filter):** ✅ **IMPLEMENTED via EFTS join, not SGML headers.** One paginated **EFTS** call per day — `https://efts.sec.gov/LATEST/search-index?q=&forms=8-K&startdt=D&enddt=D` — returns every 8-K's `items`, `biz_locations`, `inc_states`, `sics` keyed by accession (`adsh`). We join it to the daily-index 8-K rows by accession and keep only Items **1.01, 1.02, 1.03, 2.01, 3.01, 5.02, 8.01**. This avoids downloading any 8-K document AND yields geography (cross-border) + SIC for free. (Range requests on the full submission `.txt` are **not** honored by SEC's CDN, so the SGML-header idea was dropped.)

> ⚠️ **Validated gotcha — EFTS does NOT index Schedule 13D/13G** (0 SC 13D hits over a full month while the daily index listed them). This is why discovery MUST be the daily index, with EFTS used *only* to attach 8-K items. An EFTS-only build silently loses Activist Campaigns (the #1 US category).
>
> Volume budget (measured, Jun 2026): ~4,800 filings/day total → ~164 structured target forms + ~330 raw 8-Ks/day; after the EFTS item filter ~150–250 8-Ks/day survive. A 5-day backfill (idx + EFTS pagination) ran in **~41 s**. Comfortably inside the engine job.

### 2b. Per-filing fetch
For each kept filing: fetch `…/Archives/edgar/data/{cik}/{accession}/index.json` → locate the primary doc + `EX-99.1` if present. Pull the primary doc text (header / first ~8 KB is enough for terms parsing) and, for the form-absent 8-K items, the Exhibit 99.1 text (this is the input to classification + later the LLM summary).

### 2c. Cross-border handling (the decision in practice)
Because we ingest the **whole** EDGAR filer stream (not a domestic ticker list), ADRs/FPIs and cross-border deals come for free:
- US filer's 8-K 1.01/2.01 for a foreign target/divestiture → captured from the US filer.
- Foreign bidder for a US-listed target → captured via the target's `SC 14D9` / bidder's `SC TO-T`/`SC 13D`.
- Cross-listed FPI material events → `6-K` (route by parsing the 6-K exhibit for M&A/tender/restructuring language, per findings §D2 6-K row).
- Tag each record `counterparty_is_foreign` and `cross_border: true` when the deal counterparty resolves to a non-US entity. (No separate record is created for a purely-foreign counterparty.)

### 2d. Storage
Append-only event table `data/special_situations/events.parquet` via `lib/store.upsert(...)` with `normalize_index=False` (preserve filing timestamps), or a direct concat+`drop_duplicates(subset=["id"], keep="first")` to guarantee **first_seen** is never overwritten (mirror `news_vector.accrue()`). Companion `_meta.json` (`built`, `last_index_date`, `n_events`).

---

## 3. Lane B — newswire keyword lane  `engine/ss_newswire.py`
The form-absent categories (Strategic Reviews — their **#2** category, Capital Returns, out-of-court Restructuring, Deal Terminations) have no clean EDGAR trigger. Clone the **`engine/news_vector.py`** fetch-gate-store pipeline (it's the cleanest PIT primitive here):
- `_fetch_gdelt()` with `QUERY_CORE = ["strategic review","explore strategic alternatives","special committee","buyback","share repurchase","special dividend","tender offer","spin-off","restructuring","liability management","deal terminated","merger terminated","acquisition withdrawn","mutual termination"]`.
- Reuse `engine/macro_news._NEWS_SOURCES` + `_DEFAULT_SOURCES` allowlist (already imported by `news_vector._allowlist()`), tier-1 weighting.
- `event_id()` SHA-1 + `accrue()` keep-first for the PIT store.
- Resolve headline → ticker via the existing company/ticker map; drop unresolved.
- For per-ticker confirmation, `engine/catalyst_stock._fetch_stock_headlines(ticker)` is reusable as-is.

Lane B rows are **lower-confidence** → flagged `source_lane: "news"`, and only surface when they resolve to a ticker that passes the floor. Where a Lane-B item later gets an EDGAR filing (e.g. the 8-K Ex-99.1 for the strategic review), the EDGAR record supersedes (merge on company-date key, prefer Lane A `source_url`).

---

## 4. Classifier  `engine/special_situations.py :: classify()`
Pure function `classify(form_type, items, text_keywords, filer_role) -> (category, stage) | (None, None)`. The mapping is **findings §D2/§D3** distilled. Mature taxonomy = the ~16 live categories (adopt these; no legacy coarse labels).

| Trigger | → Category | Stage hint |
|---|---|---|
| `SC 13D` (Item 4 = control/board/strategic intent) | Activist Campaigns | initiated |
| `SC 13D/A` | Activist Campaigns | escalation |
| `SC TO-T` (unaffiliated bidder) | Tender Offers | live |
| `SC TO-T` + `SC 13E3` / affiliate bidder | Going-Private | live |
| `SC TO-I` | Issuer Tenders (fixed-price/Dutch) / Capital Returns | live |
| `SC 14D9` | Tender Offers (target response) | live |
| `SC 13E3` | Going-Private | live |
| `DEFM14A`/`PREM14A` (3rd-party acquirer) | Acquisitions | vote-scheduled |
| `DEFM14A`/`PREM14A` (sponsor/insider) | Going-Private | vote-scheduled |
| `DEFC14A`/`PREC14A` | Activist Campaigns (proxy fight) | live |
| `8-K 1.01` "Merger Agreement" | Acquisitions | announced |
| `8-K 1.01` "Purchase Agreement", filer=seller | Divestitures | announced |
| `8-K 1.01` "Separation/Distribution Agreement" | Spin-Offs | announced |
| `8-K 2.01` | (Acquisitions/Divestitures) | completed (update existing) |
| `8-K 1.02` | Deal Terminations | terminated |
| `8-K 1.03` "reorganization" / "liquidation" | Restructuring / Liquidations | filed |
| `8-K 3.01` + `Form 25` | Delistings | live |
| `Form 15-12B/G` | Delistings / Going-Private (post-close) | completed |
| `Form 10-12B` / `S-4` (separation) | Spin-Offs / New SpinCos | registered |
| `S-4` (de-SPAC, named target) | SPACs | announced |
| `424B5` + "subscription/rights/oversubscription" | Rights Offerings | live |
| `6-K` | route by exhibit keywords to the rows above | varies |
| **Lane B** "strategic alternatives" | Strategic Reviews | initiated |
| **Lane B** "buyback/special dividend" (no SC TO-I) | Capital Returns | announced |
| **Lane B** "restructuring/liability mgmt" (no 1.03) | Restructuring | announced |
| **Lane B** "deal terminated/withdrawn" | Deal Terminations | terminated |

- **`stage`** is a field they *don't* have — our improvement (announced → vote-scheduled → completed / terminated). `8-K 2.01` / scheme sanction / Form 15 advance an existing record's stage rather than creating a new one (merge on `cik+counterparty`).
- Boundary rules (Acquisition vs Tender vs Going-Private; Divestiture buyer/seller no-double-count; Restructuring/Liquidation/Insolvency/Delisting ladder; Issuer-Tender vs Capital-Return vs Rights) are codified verbatim from findings **§B1**.

---

## 5. Universe, $100M floor & enrichment
- **Floor:** keep a situation only if covered-company `mc ≥ $100M`. Resolution order: (a) our `data/edgar/fundamentals*.parquet` / price feeds for CIKs in our equity universe; (b) for others (ADRs, off-universe small caps), a cheap on-demand estimate = `companyfacts CommonStockSharesOutstanding × latest close` (cached per CIK); (c) if mc is still undeterminable, **hold** in a `data/special_situations/pending_mc.parquet` queue (don't silently drop — log the count) and retry next build.
- **Enrichment (we already hold all of it):** `mc`, `ev`, and the valuation quad **EV/Sales · EV/GP · Fwd P/E · EV/EBITDA** from `engine/stock_fundamentals` / `collectors/edgar_facts`; `px` from price feeds; `biz` 1-sentence descriptor from `engine/equity_profile` (fallback: first sentence generated in the LLM step). `ind`/`sec` from our GICS map (we can beat their 24% coverage).
- Deal terms (`price_per_share`, `premium_pct`, `consideration`) parsed best-effort from the filing text; absent-safe.

---

## 6. LLM summary touchpoint  `engine/ss_summary.py`
Copy `macro_news.macro_brief` (lines 313–347) + the `catalyst_tone` digest-cache pattern verbatim:
- **Gate:** `_cfg().get("enabled", False)` AND `config.secret(cfg.get("api_key_env","DEEPSEEK_API_KEY"))` present AND `cfg.get("llm_brief")`. Plus CI escape hatch `os.environ.get("DISABLE_SPECIAL_SITUATIONS_LLM")`.
- **Cache (critical for cost):** `data/special_situations/digest_cache/{id}.json`, written only on success. **The LLM is called only for situation `id`s not already cached** → daily builds re-pay nothing for existing situations.
- **Call:** `client.messages.create(model="deepseek-chat" | "claude-haiku-4-5", max_tokens=220, system=SS_SYSTEM, messages=[…])`. Input = the **pre-filtered structured situation** (category, parties, terms, dates, metrics) + the filing/Ex-99.1 snippet — never raw corpus.
- **System prompt** encodes findings **§E** house style: 1 business-descriptor sentence + an ~88-word 5-part summary (who/what filed → exact terms → board reco/advisor → mechanics/overhang → what-to-watch); neutral-analytical; map foreign filings to US equivalents in-prose; "context only, never a signal."
- **zh:** `engine.translate.translate_to_zh([summary], tcfg)` post-pass (batch, `deepseek-v4-flash`), mirror `master_brain._translate_brief`.
- Returns `{"text":…, "zh":…, "model":…, "is_context_only": True}`; degrade-never-raise.

---

## 7. Data model (`events.parquet` row + emitted record)
```
id (sha1 of cik+accession | cik+date+category for Lane B)   first_seen   built
ticker  cik  company  country  exchange  cross_border  counterparty  counterparty_is_foreign
category  stage  source_lane(edgar|news)  source_form  source_url
mc  ev  px  metrics{ev_sales,ev_gp,fwd_pe,ev_ebitda}  ind  sec  biz
price_per_share  premium_pct  consideration  announced_date  effective_date
summary  summary_zh  is_context_only=true  disclaimer
```

---

## 8. Surfaces & integration (all additive / absent-safe)

1. **Desk page** — `engine/special_situations.py::snapshot()` → `scripts/build_special_situations.py::build()` renders `templates/special_situations.html.j2` → `site/special_situations.html`, grouped by category as scannable cards (mirror their card layout: company · ticker/exch/sector · category badge · valuation quad · summary). Also writes the hub-card snapshot `data/regime/special_situations_latest.json`.
2. **Nav** — one `<a>` line in `templates/_navlinks.html.j2` US dropdown (after the IPO Radar line, ~line 36). `NP` prefix handles relative paths.
3. **Hub card** — `_special_situations_state()` in `scripts/build_vector.py` (mirror `_ipo_state()` line 1007) reading `special_situations_latest.json`; pass into `_hub_html()`.
4. **Per-ticker chip** — add key `special_situation` to `site/stockdata/<TICKER>.json` in `scripts/build_stock_library.py` (per-ticker loop ~line 815). `stock.html` SPA renders a `panel_special_sit` (clone the `panel_gex`/`panel_fragility` show-logic, ~lines 1416–1462). Absent key = no panel.
5. **Board chip** — `site/allocationdata/special_situations.json` (`{schema:"special_situations.v1", is_context_only:true, by_ticker:{…}}`), parallel to `ai_desk_us.json`; baskets / us_stocks boards surface it via the existing additive-chip path (`aidesk_lean.js` pattern) — no page rewrite.
6. **Mastermind** — add `state["special_situations"]` (compact `by_ticker` dict: `{TICKER:{category,stage,is_context_only:true}}`) in `engine/master_brain.py::gather_state()` (~lines 439–489). `MASTER_SYSTEM_TMPL` already treats display blocks as CONTEXT, never sizing. **Do not** touch `engine/masterminds.py` (GTAA backtest — category error).
7. **Daily build slot** — add `run_py "special situations (build_special_situations)" scripts.build_special_situations` to `.github/workflows/daily.yml` engine job, **between `build_transmission` and `build_vector`** (so the hub snapshot exists before `build_vector` reads it). Add the collector to `scripts/collect.py` specs (or invoke from the build script like `edgar.fetch_panel`). Runs Mon–Fri; the discovery watermark backfills weekend dates.

## 9. i18n / bilingual
- Build script holds EN↔zh view-model maps (category names, stage words) like `build_ipo.py`; template uses its own `{% macro t() %}`; add event/stage vocab to `LEX` in `engine/i18n.py` for `td()`/`tr()`. **Never** put `t()`/`T()` output in HTML attributes (use pre-joined literal strings in `title=`).

## 10. Tests  `tests/test_special_situations.py`
- `SCORED is False` invariant; leaf-import guard (no scoring imports).
- `classify()` unit table (each form/item → expected category+stage), incl. boundary pairs from §B1.
- `$100M` floor (keep/drop/pending), id determinism, keep-first accrue.
- LLM gate returns `None` when `enabled:false` / key missing; cache hit skips the call.
- Cross-border tagging on a foreign-counterparty fixture.

---

## 11. Build order (milestones) & effort
| # | Milestone | Output | Rough effort |
|---|---|---|---|
| P1.0 | EDGAR daily-index discovery + filing fetch + `events.parquet` | collector, no classification | ~1 session |
| P1.1 | Classifier (§D2 + §B1) + floor + enrichment + cross-border tag | deterministic engine snapshot | ~1 session |
| P1.2 | Desk page + nav + hub card + daily.yml slot | `site/special_situations.html` live (no summaries) | ~1 session |
| P1.3 | Gated+cached LLM 88-word summary (+zh) | populated cards | ~0.5 session |
| P1.4 | Cross-surface emit (stock chip · allocation json · Mastermind state) | chips + Mastermind context | ~0.5 session |
| P1.5 | Tests + a real dated-window dry run vs the digest as ground truth | green suite + accuracy spot-check | ~0.5 session |

## 12. Cost
LLM fires only on **new** situations/day (cache skips the rest). US-anchored new situations ≈ 40–120/weekday; ~250 output tokens each on DeepSeek/Haiku → **pennies/day**. Everything else is keyless (EDGAR, GDELT).

## 13. Open implementation questions / risks
1. **8-K item extraction at scale** — header `<ITEMS>` parse vs. EFTS JSON pre-filter. Start with header parse; switch to EFTS if the daily 8-K fetch volume is too slow.
2. **Ticker resolution for Lane B / foreign filers** — GDELT headlines and 6-K filers need a robust name→ticker map; unresolved rows are dropped (logged).
3. **Deal-terms parsing** is best-effort (price/premium/consideration vary wildly by filing); treat as absent-safe, never block a record on it.
4. **Accuracy check** — P1.5 should run the collector over a past dated window and diff against the corresponding digest issue (we have all 4,471 as ground truth in `_recon_raw/`) to measure recall/precision of the classifier before going live.

## 14. Explicitly out of scope (later phases)
- **Phase 2:** UK RNS + Canada SEDAR+ (English, structured) — adds ~556 situations; classifier/writer already exist (findings §D3).
- **Phase 3:** Japan EDINET/TDnet (562 situations, the moat) — needs Japanese-language ingest + the 大量保有 13G→13D purpose-flip detector.
- Full foreign-domestic coverage beyond US-anchored cross-border.
- A weekly "digest" rollup (we ship a live daily desk instead).
