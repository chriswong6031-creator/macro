# Lane 4 — Native China Macro/Policy/Alt-Data + Hong Kong Source Catalog

> **ERRATA (main-loop red-team, 2026-07-25):**
> 1. §5.1 HKMA "HIBOR fixed and published same-day" is contradicted by this catalog's own
>    verified sample (`end_of_day: 2026-06-30`, ~25d stale): the `monthly-statistical-bulletin`
>    family publishes **daily observations at monthly cadence**. The `daily-monetary-statistics`
>    family (monetary base incl. aggregate balance) IS T-1 fresh — use that for daily organs.
> 2. §6.1 Jin10 `datacenter-api` list_v2: verified 200-with-payload once, then 502 on every
>    same-day main-loop retry — treat as UNSTABLE from datacenter egress; the `cdn.jin10.com`
>    report mirrors are the stable path.

Verified live from this machine on **2026-07-25/26** (Beijing-time timestamps returned by several endpoints read 2026-07-26 13:xx, i.e. UTC+8).

**Machine identity (measured via `ipinfo.io` and WAF challenge pages that echo client IP):** egress IP `185.213.193.199`, ASN `AS21859 Zenlayer Inc` (a commercial CDN/proxy network), geolocated Washington DC, US. This is a **datacenter/hosting IP**, not a residential one — several blocks below are keyed off ASN/datacenter reputation (WAF `UrlACL`), not a simple "China vs. not-China" rule. Anyone running this pipeline from a different host (incl. the actual Mac Studio on a residential/business ISP) may see different results on the WAF-gated rows — re-verify there before hard-coding "dead."

**Method:** `curl -s -m 15` / Python `requests` with a browser UA (15s timeout), reading HTTP status + a short body snippet (never full CJK dumps). For endpoints discovered via the **locally-installed `akshare==1.18.64`** package (confirmed installed at `/opt/homebrew/Caskroom/miniconda/base/lib/python3.12/site-packages/akshare`), calls were replicated with the exact params/headers/tokens the library uses, so the verdict reflects the real integration path, not a guess. **VERIFIED** = live 2xx/expected-shape response observed this session. **UNVERIFIED** = reachable but exact data contract not confirmed, or not tested. **DEAD** = confirmed blocked/unreachable from this machine.

---

## Family 1 — Official macro

### 1.1 NBS 国家统计局 — `easyquery.htm`
- **Provides / why it matters**: The primary indicator tree behind every headline China macro print (GDP, CPI, PPI, industrial output, retail sales, FAI, regional breakdowns). Ground truth for everything else in this family, which are mostly *mirrors* of NBS releases.
- **Endpoint**: `https://data.stats.gov.cn/easyquery.htm` (POST, params `id`/`dbcode`/`wdcode`/`m=getTree` etc.)
- **Auth**: none (undocumented public JSON, scraped by convention)
- **Cost**: free
- **Rate limits**: unknown/undocumented; irrelevant here — see below
- **Cadence + lag**: NBS press-conference cadence (monthly ~15th–18th; quarterly GDP ~17th–18th of the month after quarter-end)
- **History depth**: full historical series back to earliest NBS collection (varies by indicator, some to 1990s)
- **Geo-block status (THIS MACHINE): DEAD — VERIFIED.** `403 Forbidden`, body: `Client IP: 185.213.193.199 ... reason:UrlACL`. Reproduced with a byte-for-byte replica of akshare's actual POST call (same params, `verify=False`, default `python-requests` UA) — same 403/UrlACL. This is a WAF ACL keyed to the requesting IP/ASN, independent of HTTP method or headers.
- **akshare wrapper**: `akshare.economic.macro_china_nbs` (multiple functions) — **broken from this machine**, matches the task's "notorious foreign-IP flakiness."
- **Surprising sub-finding**: NBS's *other* public data endpoint, `https://data.stats.gov.cn/dg/website/publicrelease/web/external/getEsDataByCidAndDt` (used by `akshare.macro_china_urban_unemployment`), does **NOT** show the same WAF signature — it returns a plain `404 Not Found` (nginx-style, no `UrlACL`/`waf01fst` marker). That looks like a stale/changed path rather than a geo-block, i.e. the WAF rule is applied per-URL, not domain-wide. Worth periodic re-probing; not reliable enough to build on yet.
- **Practical workaround (see 1.1a)**: nearly every headline series NBS publishes is mirrored, same-day, on Eastmoney's `datacenter-web.eastmoney.com` JSON API, which is **not** blocked from this machine.
- **ToS/redistribution risk**: low for derived signals (we never republish raw NBS series); NBS ToS doesn't address API scraping directly since the endpoint isn't official.
- **Integration effort**: **L** if pursuing direct NBS access (proxy/VPN needed); effectively moot given 1.1a.

### 1.1a Eastmoney 东方财富 datacenter-web — NBS/PBOC macro mirror (the real workhorse)
- **Provides / why it matters**: A single, **unblocked**, zero-real-auth JSON API that mirrors the vast majority of NBS/PBOC headline releases: CPI, PPI, GDP (yearly/quarterly), PMI (official + non-manufacturing), trade balance, exports/imports YoY, M2, industrial production YoY, urban unemployment, national tax receipts, **new RMB loans**, **reserve requirement ratio (RRR)**, **LPR**, FX reserves, insurance income, bank financing, vegetable-basket/agricultural wholesale price indices, construction indices, and more — `akshare/economic/macro_china.py` wraps ~50 of these functions against this one host.
- **Endpoint**: `https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=<REPORT_CODE>&columns=...&token=...`. Report codes are undocumented but fully enumerable from the installed akshare source (e.g. `RPTA_WEB_RATE` = LPR + historical benchmark rates, `RPT_ECONOMY_RMB_LOAN` = new RMB loans).
- **Auth**: a **shared, non-personal token** baked into akshare (`894050c76af8597a853f5b408b759f5d` for the LPR report); several reports (e.g. new RMB loans) need no token param at all.
- **Cost**: free
- **Rate limits**: none published; this is Eastmoney's own retail-facing data-center API, built for browser traffic — self-throttle to nightly-batch cadence out of courtesy.
- **Cadence + lag**: same-day as NBS/PBOC release (Eastmoney re-publishes within minutes to hours)
- **History depth**: deep — the LPR/benchmark-rate report alone paginated to `pages:315` at `pageSize:5` (~1,575 rows), spanning pre-2019 benchmark lending/deposit rate changes plus the post-Aug-2019 LPR-reform fixings.
- **Geo-block status (THIS MACHINE): VERIFIED LIVE.** Tested `RPTA_WEB_RATE` (LPR) → real July-2026 fix (`LPR1Y:3, LPR5Y:3.5`, matching the actual 20 Jul 2026 fixing). Tested `RPT_ECONOMY_RMB_LOAN` (new RMB loans) → real June-2026 data. Both `200`, clean JSON, zero blocking.
- **akshare wrapper**: yes, extensively — `macro_china_lpr`, `macro_china_new_financial_credit`, `macro_china_reserve_requirement_ratio`, `macro_china_cpi`, `macro_china_ppi`, `macro_china_gdp`, `macro_china_pmi`, `macro_china_m2_yearly`, `macro_china_urban_unemployment`(NBS-direct, separately dead — see 1.1), `macro_china_vegetable_basket`, `macro_china_agricultural_product`, and ~40 more in `economic/macro_china.py`.
- **ToS/redistribution risk**: low — same posture as any Eastmoney-sourced akshare data already in the pipeline; we publish derived signals only.
- **Integration effort**: **S** — this is the single highest-leverage unblock in this catalog; almost pure upside since akshare already ships the report codes.

### 1.2 PBOC 中国人民银行 — statistics + OMO releases
- **Provides / why it matters**: Money supply (M2), TSF/社融, and the daily open-market-operation (OMO, 逆回购/MLF) bulletin — the primary liquidity-stance signal our PBOC stance engine already consumes for LPR+RRR+FR007.
- **Endpoints**: main site `http://www.pbc.gov.cn/` (200, reachable); statistics landing `.../diaochatongjisi/116219/index.html` (200); OMO bulletin `.../zhengcehuobisi/125207/125213/125431/index.html` (200).
- **Auth**: none. **Cost**: free.
- **Rate limits**: none published (HTML site).
- **Cadence + lag**: OMO announced daily ~9:20–9:30am Beijing time on days repo/reverse-repo is conducted; money-supply/TSF monthly, ~10th–15th.
- **History depth**: bulletin archive goes back years as dated HTML pages; no bulk download found.
- **Geo-block status (THIS MACHINE): VERIFIED reachable (200) at HTML level** — no WAF block observed on any pbc.gov.cn path tested. **No JSON/machine-readable API found** — confirmed via exhaustive grep of the local akshare install (`grep -rl "pbc.gov.cn"` → zero hits across the entire package). This means our own PBOC engine is almost certainly scraping HTML directly already (matches CLAUDE.md's "PBOC stance engine").
- **akshare wrapper**: **none** — LPR/RRR/OMO are sourced elsewhere (Eastmoney mirror for LPR/RRR; no OMO mirror found anywhere, including Eastmoney/Jin10/chinamoney).
- **ToS/redistribution risk**: low (derived signals only).
- **Integration effort**: **S–M** for OMO specifically — the bulletin list page is a clean dated-title list (date + operation type + amount + rate embedded in the title string), regex-parseable; no JSON shortcut exists anywhere we could find, so this stays HTML-scrape.

### 1.3 SAFE 国家外汇管理局 — FX reserves / RMB rate query
- **Provides / why it matters**: Official FX reserves (monthly) and the RMB central/settlement rate query tool — cross-check source for `currency_boc_safe` already integrated.
- **Endpoint**: main `http://www.safe.gov.cn/` (200); RMB rate query tool `https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do` (200, GET and POST both return the page shell); FX-reserve press-release index redirects through a numeric content ID (`.../safe/2020/1218/17833.html`-style), i.e. **not a stable URL** — akshare re-resolves it dynamically each call.
- **Auth**: none. **Cost**: free. **Rate limits**: none published.
- **Cadence + lag**: FX reserves monthly, ~7th of the following month. RMB rate query is daily.
- **History depth**: FX reserves series back to the 1990s on the press-release archive; RMBQuery tool supports a date-range query (exact JSON payload not reverse-engineered this session — the page loads but is a JS-rendered form, not a bare JSON endpoint at the URL level).
- **Geo-block status (THIS MACHINE): VERIFIED reachable (200)**, no WAF block. Exact underlying AJAX data call for RMBQuery **UNVERIFIED** (returns the HTML shell, not JSON, to a plain GET/POST — needs a devtools capture of the real XHR).
- **akshare wrapper**: `akshare.currency.currency_safe` (`currency_boc_safe`, `currency_boc_sino_forex`) — already integrated per project context.
- **ToS/redistribution risk**: low.
- **Integration effort**: **S** (already integrated); **M** if pursuing the RMBQuery AJAX call directly for a new series.

### 1.4 GACC 海关总署 — trade data
- **Provides / why it matters**: Official export/import values (trade balance, by country, by trade mode) — the authoritative source behind `macro_china_exports_yoy`/`trade_balance` (which are themselves Eastmoney mirrors, not GACC-direct).
- **Endpoint (Chinese)**: `http://www.customs.gov.cn/...` deep report links. **Endpoint (English)**: `http://english.customs.gov.cn/` and its per-report static pages (e.g. `.../Statics/<hash>.html`) with USD-denominated tables by trade mode/country/month.
- **Auth**: none. **Cost**: free. **Rate limits**: none published (static HTML).
- **Cadence + lag**: monthly, ~mid-month for prior month (customs data typically lags ~2–3 weeks after month-end; the flash trade balance most desks watch is actually the Eastmoney/NBS-mirrored `exports_yoy`/`trade_balance` series, sourced ahead of GACC's own detailed monthly bulletin).
- **History depth**: monthly report archive goes back years; not a single bulk CSV/API — one static page per report per month.
- **Geo-block status (THIS MACHINE)**: **Chinese main site: DEAD — VERIFIED.** `412 Precondition Failed` on a deep customs.gov.cn link (same WAF-challenge signature family as other blocked mainland gov sites). **English portal: VERIFIED LIVE (200)**, fully reachable, same underlying USD trade-value tables. This is a clean, no-effort bypass: use the English mirror.
- **akshare wrapper**: **none found** (no `customs` reference anywhere in the local akshare install).
- **ToS/redistribution risk**: low; these are official published statistical tables in English, explicitly for public/press consumption.
- **Integration effort**: **M** — no JSON, so this is per-page HTML table scraping (one page per metric per month), but the pages are static and structurally consistent.

### 1.5 MoF 财政部 — fiscal/local government bond (LGB) issuance
- **Provides / why it matters**: Fiscal revenue/expenditure and LGB issuance calendar — a real-economy-facing complement to the PBOC/credit side.
- **Endpoint**: main `http://www.mof.gov.cn/` (200); fiscal-data channel `http://www.mof.gov.cn/gkml/caizhengshuju/` (200).
- **Auth**: none. **Cost**: free. **Rate limits**: none published.
- **Cadence + lag**: fiscal revenue/expenditure monthly (~20th); LGB issuance calendar published ad hoc/quarterly guidance.
- **History depth**: archive of dated bulletins, years deep; no bulk API.
- **Geo-block status (THIS MACHINE): VERIFIED reachable (200)**, no WAF signature observed on either path tested.
- **akshare wrapper**: **none confirmed** in local grep (national tax receipts (`macro_china_national_tax_receipts`) is Eastmoney-sourced, not MoF-direct).
- **ToS/redistribution risk**: low.
- **Integration effort**: **M** — HTML bulletin scrape, no JSON shortcut found.

### 1.6 Caixin PMI 财新PMI (S&P Global / RatingDog)
- **Provides / why it matters**: The private-sector PMI read that diverges from the official NBS PMI at policy-relevant moments (smaller firms, export-exposed sample) — a standard confluence input against the official PMI.
- **Endpoint**: press release published on `pmi.spglobal.com/Public/Home/PressRelease/<hash>` (opaque per-month hash, not predictable) and mirrored as PDF at `pmi.caixin.com/upload/CN_Manufacturing_ENG_<YYMM>_PR.pdf`; **note**: as of the 2026 rebrand, some wires now label the same series "RatingDog Manufacturing/Services PMI" (S&P Global's China PMI licensing partner changed name from Caixin to RatingDog per FXStreet/Investing.com calendar listings found this session — verify branding before publishing to users).
- **Auth**: none. **Cost**: free (press release); full history/data feed is paid via S&P Global subscription.
- **Rate limits**: none published (static page/PDF).
- **Cadence + lag**: flash ~6 business days before month-end; final on the 1st business day of the following month (manufacturing) / 3rd business day (services) — a fixed, calendar-predictable release slot, unlike NBS's press-conference-driven date.
- **History depth**: press-release archive back to survey inception (2005 manufacturing, 2012 services); machine-friendly numeric history is paid-tier only.
- **Geo-block status (THIS MACHINE)**: caixinglobal.com direct guess path was `404` (wrong URL structure — no live block observed, just a bad guess this session). `pmi.spglobal.com` base domain not directly probed this session; **UNVERIFIED** at the exact URL level, but nothing suggests a China-specific block (this is a US/UK-hosted vendor site).
- **akshare wrapper**: `macro_china_cx_pmi_yearly` / `macro_china_cx_services_pmi_yearly` — sourced via the **Jin10 mirror** (`__macro_china_base_func`/`datacenter-api.jin10.com`, see 6.1), not S&P Global directly. This is almost certainly the more reliable path (see Family 6).
- **ToS/redistribution risk**: **medium** — Caixin/S&P Global PMI numbers are a licensed commercial product; free access is limited to the *headline number* in the press release, not the full history/subindices. Fine to reference the headline as a derived-signal input; do not scrape/republish the underlying subindex history without a license.
- **Integration effort**: **S** via the Jin10 mirror (already effectively free-riding on akshare's existing plumbing); **L** for a licensed direct feed.

---

## Family 2 — Rates/FX official feeds

### 2.1 CFETS / ChinaMoney 中国外汇交易中心 — central parity, FR007/FDR007, SHIBOR pages
- **Provides / why it matters**: The primary-market repo-rate curve (FR007/FDR007) is the "liquidity temperature" series PBOC-watchers inside China actually trade off, finer-grained than the SHIBOR headline most Western dashboards stop at. Also home of the CNY central parity fixing and the CFETS RMB index.
- **Endpoint**: `https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/FrrHis?start=...&end=...` (JSON, fixing-repo-rate history), `https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/frr-chrt.csv` (plain CSV), central-parity page family under `/chinese/mkdatapfx/`, bond-curve family under `/ags/ms/cm-u-bk-currency/ClsYldCurvHis`.
- **Auth**: none. **Cost**: free. **Rate limits**: none published; the `/ags/` path is CFETS's own AJAX backend (Origin/Referer headers recommended, not strictly required for the FR007 history call — see below).
- **Cadence + lag**: FR007/FDR007 fixed and published same-day; central parity fixed ~9:15am Beijing time daily.
- **History depth**: matches akshare docstrings — multi-year daily series for FR007/FDR007; central parity back to the 2015/2005 regime changes depending on series.
- **Geo-block status (THIS MACHINE): VERIFIED LIVE.** `FrrHis` → `200`, clean CWAP-branded JSON with real 26-Jul-2026 data (`baseCurveCfgList: [FR001,FR007,FR014,FDR001,FDR007,FDR014]`). `frr-chrt.csv` → `200`, plain CSV, real daily rows through 24-Jul-2026. Main site `www.chinamoney.com.cn` → `200`.
- **SHIBOR-specific caveat**: guessed endpoint `cm-u-bk-shibor/IfccHis` returned `200` but an application-level error (`rep_code:500, "InterestRateSwapCurveHistoryAction Exception"`) — that specific path/params combination is wrong (likely an interest-rate-*swap*-curve endpoint, not the SHIBOR fixing itself); **do not build on it as-is**. Use 2.1a (Jin10 CDN) or Eastmoney's SHIBOR mirror for the SHIBOR fixing instead — both confirmed live below.
- **akshare wrapper**: `akshare.rate.repo_rate` (`repo_rate_query`/`bond_china_close_return`-family), `akshare.fx.fx_quote`, `akshare.bond.bond_china_money` — already integrated per project context (FR007).
- **ToS/redistribution risk**: low — CFETS publishes these as public benchmark fixings, standard practice for redistribution of the *fixing value* (not raw order-book data).
- **Integration effort**: **S** (already integrated; hardening/expansion only).

### 2.1a SHIBOR fixings — two working zero-auth mirrors (shibor.org is dead)
- **Provides / why it matters**: SHIBOR is the deposit-side benchmark complementing FR007's repo-side view.
- **shibor.org — DEAD, VERIFIED**: `www.shibor.org` and bare `shibor.org` both fail **DNS resolution** entirely from this machine (`Could not resolve host`) — not a WAF block, the domain itself doesn't resolve here. This is a harder failure mode than the WAF 403s elsewhere; a DNS-over-HTTPS resolver or different DNS path might recover it, not tested. Websearch turned up `shibor.net.cn` as a possible alternate CFETS-run domain — **not verified this session**, worth a quick check before writing this off completely, but do not depend on shibor.org going forward regardless.
- **Jin10 CDN mirror — VERIFIED LIVE, zero auth**: `https://cdn.jin10.com/data_center/reports/il_1.json` → `200`, plain JSON, **no headers/token needed at all**, real 24-Jul-2026 SHIBOR fixings across all 8 tenors (O/N 1.3812, 1W 1.4000 … 1Y 1.4791). This is the easiest, lowest-friction SHIBOR path found in this entire survey.
- **Eastmoney mirror**: reachable but the exact `reportName` guessed this session (`RPT_IMP_INTRATEN`) was wrong (`"报表未配置" code:9501` — "report not configured", i.e. endpoint alive, report code wrong). akshare's own `interbank_rate_em.py` hits `datacenter-web.eastmoney.com/api/data/v1/get` for this; the correct report code is in that file if the Jin10 CDN path (above) ever breaks.
- **akshare wrapper**: `macro_china_shibor_all` (Jin10 CDN, confirmed working), `akshare.interest_rate.interbank_rate_em` (Eastmoney, report code needs lookup).
- **Integration effort**: **S** — `il_1.json` is genuinely trivial to consume.

### 2.2 PBOC OMO 逆回购/MLF announcements
- See **1.2** above — same source, no separate machine path found. HTML bulletin only.

### 2.3 中债 ChinaBond 中央国债登记结算 — yield curve
- **Provides / why it matters**: The official sovereign yield curve (中债收益率曲线), the benchmark curve for onshore bond pricing/duration signals.
- **Endpoint**: `https://www.chinabond.com.cn/` (main site).
- **Auth**: none. **Cost**: free for headline curve points; bulk/historical downloads may sit behind a registration wall on the sub-portal (not tested this session).
- **Rate limits**: none published.
- **Cadence + lag**: daily close.
- **History depth**: deep (multi-decade curve history advertised on the portal).
- **Geo-block status (THIS MACHINE): VERIFIED reachable (200)**, no block observed.
- **akshare wrapper**: `akshare.bond.bond_china` / `bond_cbond` modules exist locally (names suggest ChinaBond-adjacent coverage) — exact endpoint not deep-verified this session.
- **ToS/redistribution risk**: low for curve levels (standard benchmark redistribution norm).
- **Integration effort**: **M** — main site loads fine; exact yield-curve JSON/download endpoint needs one more devtools pass.

---

## Family 3 — Policy/news wires

### 3.0 Summary table — reachability this machine

| Source | 中文 | HTTP | Machine-readable? | Verdict |
|---|---|---|---|---|
| gov.cn main + policy library | 国务院 | 200 | JSON search API found | **VERIFIED reachable; query mechanics unconfirmed** |
| NDRC | 发改委 | 200 | no | reachable, HTML scrape only |
| CSRC | 证监会 | 200 | no | reachable, HTML scrape only |
| MIIT | 工信部 | 200 | no | reachable, HTML scrape only |
| MOFCOM | 商务部 | 200 (main); **SSL failure** (data.mofcom.gov.cn) | partial | mixed — see 3.5 |
| cls.cn telegraph page | 财联社 | 200 | **nodeapi DEAD (404)** | matches known-dead; page itself loads |
| Sina 7x24 zhibo | 新浪财经 | 200 | **JSON, VERIFIED LIVE** | already integrated, keep |
| 10jqka push | 同花顺 | 200 | **JSON, VERIFIED LIVE** | new find, good backup |
| Futu Niuniu flash | 富途牛牛 | 200 | **JSON, VERIFIED LIVE** | new find, best cls.cn replacement |
| nbd.com.cn | 每经 | 200 | no | reachable, HTML scrape only |
| jiemian.com | 界面 | 200 | no | reachable, HTML scrape only |
| yicai.com / yicaiglobal.com | 第一财经 | 200/200 | no | reachable, HTML scrape only |
| thepaper.cn | 澎湃 | **403 DEAD** | n/a | confirmed dead, matches known list |
| wallstreetcn.com | 华尔街见闻 | 200 | (already integrated) | unchanged |
| gelonghui.com | 格隆汇 | 200 | (already integrated) | unchanged |
| jin10.com | 金十 | 200 | **datacenter-api JSON, VERIFIED LIVE** | see Family 6 |

### 3.1 gov.cn 国务院 — policy releases
- **Provides / why it matters**: The apex policy-release channel; State Council decisions/briefings are the top of the policy-transmission chain everything else reacts to.
- **Endpoint**: main `https://www.gov.cn/` (200); policy library search API `https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary&...` — **VERIFIED LIVE, real JSON shape** (`{"code":200,"msg":..., "searchVO":{"totalCount":...,"pageSize":...}}`), but a test query (`q=利率`) returned `totalCount:0` — either a missing required param or the query needs a session/referer context not replicated this session. Guessed RSS paths (`/zhengce/zhengceku/rss.xml`, `/xinwen/rss.xml`) were `404` — **no RSS confirmed**.
- **Auth**: none apparent. **Cost**: free. **Rate limits**: unknown.
- **Cadence + lag**: real-time to same-day for major releases; State Council briefings on a published (if irregular) schedule.
- **History depth**: policy library search covers years of documents.
- **Geo-block status: VERIFIED reachable**, both HTML and the JSON search endpoint respond 200.
- **akshare wrapper**: none found.
- **ToS/redistribution risk**: low (public policy documents; standard to reference/summarize, not to bulk-republish full text).
- **Integration effort**: **M** — the JSON search API shape is promising (real pagination fields) but needs a devtools capture of a working query before it's usable; HTML title/date scraping of `/zhengce/zuixin/` is a fallback that works today.

### 3.2–3.4 NDRC 发改委 / CSRC 证监会 / MIIT 工信部
- All three: **VERIFIED reachable (200)**, no WAF block observed on main/news-list pages. No JSON/RSS discovered for any of them this session (all HTML-only, title+date scrape). Cadence: ad hoc, multiple releases per week; CSRC in particular publishes market-moving announcements at unpredictable times (after-hours Friday releases are a known pattern). Integration effort: **M** each (HTML list scraping, broadly similar structure to gov.cn's own news lists).

### 3.5 MOFCOM 商务部
- Main site `http://www.mofcom.gov.cn/` — **VERIFIED reachable (200)**.
- Data portal `https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery` (hosts a 社融规模/aggregate-financing-adjacent series per akshare's `macro_china_shrzgm`) — **DEAD, distinct failure mode**: `SSLError: SSLV3_ALERT_HANDSHAKE_FAILURE`. This is a **TLS-layer** failure, not a WAF 403 — the server is actively rejecting our TLS handshake (likely a cipher-suite/SNI fingerprint block), different from every other block in this catalog. Worth knowing because it means the standard "spoof a browser UA" trick won't fix it; would need a different TLS client fingerprint (e.g. `curl_cffi`/browser-impersonation library) to even test further.
- **Integration effort**: **M** for the main site (HTML scrape); **L** for the data subdomain given the TLS-fingerprint block.

### 3.6 财联社 cls.cn — re-verification
- Telegraph page `https://www.cls.cn/telegraph` — **VERIFIED reachable (200)**, page itself loads fine.
- `nodeapi/telegraphList` — **DEAD, VERIFIED**: `404`, confirmed against the exact path the currently-installed akshare (`stock_feature/stock_info.py`) still references. Matches the task's known-dead list; this is not a transient issue, the path is gone in the current site build (Next.js `data-next-head` markers indicate a full frontend rewrite since the old API was mapped).
- **No replacement cls.cn JSON path found.** Recommend **not** chasing this further — 3.7/3.8 below cover the same content category with working APIs.

### 3.7 Futu Niuniu 富途牛牛 flash news — new find, best cls.cn substitute
- **Provides / why it matters**: Real-time CN/HK market-moving flash headlines, essentially the same content category cls.cn/財联社电报 occupies, from a Hong Kong-listed brokerage's consumer app backend.
- **Endpoint**: `https://news.futunn.com/news-site-api/main/get-flash-list?type=1&page=1&pageSize=10`
- **Auth**: none. **Cost**: free. **Rate limits**: unknown/unpublished.
- **Cadence + lag**: real-time (seconds-level), each item timestamped.
- **History depth**: paginated backward via a `seqMark` cursor; depth not tested but appears to support arbitrary backward paging.
- **Geo-block status (THIS MACHINE): VERIFIED LIVE.** `200`, clean JSON: `{"code":0,"data":{"data":{"seqMark":"...","hasMore":true,"news":[{"audioInfos":[...],...}]}}}` — items include TTS audio URLs (`newsspeech.futunn.com`) and real 26-Jul-2026 timestamps.
- **akshare wrapper**: yes — this exact URL is referenced in `akshare/stock_feature/stock_info.py` (so it's an already-known path in the ecosystem, just apparently not wired into this project yet).
- **ToS/redistribution risk**: **medium** — Futu is a commercial brokerage; flash-news redistribution terms are unclear (likely intended for in-app use). Treat as we already treat wallstreetcn/jin10/gelonghui: consume for derived-signal timing/sentiment, don't republish full text.
- **Integration effort**: **S**.

### 3.8 同花顺 10jqka push news — redundant real-time backup
- **Endpoint**: `https://news.10jqka.com.cn/tapp/news/push/stock`
- **Auth**: none. **Cost**: free.
- **Geo-block status (THIS MACHINE): VERIFIED LIVE.** `200`, clean JSON (`{"code":"200","msg":"...","data":{"list":[{"id":...,"title":...,"digest":...}]}}`), real content.
- **akshare wrapper**: referenced in `stock_feature/stock_info.py` alongside the cls.cn and futunn paths.
- Separately, `news.10jqka.com.cn/realtimenews.html` (the human-facing page) is explicitly **GBK-encoded** (`<meta charset="GBK">`) — the one confirmed non-UTF-8 site in this whole survey; decode accordingly if ever scraping that page directly instead of the JSON push endpoint.
- **Integration effort**: **S**.

### 3.9 每经 nbd.com.cn / 界面 jiemian.com / 第一财经 yicai.com+yicaiglobal.com
- All four: **VERIFIED reachable (200)**, no blocks. No JSON/RSS discovered this session for any — HTML scrape only. yicai.com's homepage loads an `yc_autologin.js` script, suggesting some content may be soft-gated behind login for depth, but headlines/list pages are open. Integration effort: **M** each.

### 3.10 澎湃 thepaper.cn — re-confirmed dead
- **DEAD, VERIFIED.** `403 Forbidden`, server header `Zen/4.3`, generic anti-bot challenge page. No alternate path found or attempted (matches task's already-known-dead status; no new information beyond a fresh confirmation timestamp).

---

## Family 4 — Alt-data

### 4.1 Baidu Index 百度指数
- **Provides / why it matters**: Search-interest proxy for consumer/policy-topic attention (property, unemployment, specific stimulus keywords) — the closest China analogue to Google Trends.
- **Endpoint**: `https://index.baidu.com/` (portal); underlying data API `index.baidu.com/api/SearchApi/index`.
- **Auth**: **requires a logged-in Baidu account cookie** (`BAIDUID`/`BIDUPSID` from a real login — guest/anonymous cookies are explicitly rejected). Baidu also applies field-level cipher-text encryption to parts of the response that community scrapers have to reverse-engineer and that has broken/changed historically.
- **Cost**: free (with account) for interactive use; no official bulk API.
- **Rate limits**: unpublished, but session/cookie-based scraping is fragile against rate-based bans.
- **Cadence + lag**: near-real-time to daily.
- **History depth**: multi-year via the interactive portal.
- **Geo-block status (THIS MACHINE)**: portal itself **VERIFIED reachable (200)**; the actual data API is gated by login, not geography — reachability isn't the blocker, authentication is.
- **akshare wrapper**: none.
- **Honest feasibility assessment**: technically possible (multiple open-source scrapers exist, e.g. `spider-BaiduIndex`) but requires (a) a real Baidu account, (b) periodic cookie refresh, (c) tolerance for cipher-text format changes breaking the scraper without notice, (d) an internal decision on whether cookie-based scraping of a Baidu-account-gated product fits the project's ToS posture (it is a more direct ToS gray zone than a keyless public JSON endpoint — this is us impersonating a logged-in browser session against a product with an account wall, unlike everything else in this catalog).
- **ToS/redistribution risk**: **medium-high** — explicitly login-gated, unlike every keyless endpoint elsewhere in this survey.
- **Integration effort**: **L**, with ongoing maintenance burden.

### 4.2 AQI 空气质量 — aqicn.org / waqi.info
- **Provides / why it matters**: Air quality as an industrial-activity/lockdown-adjacent nowcast proxy (city-level PM2.5 correlates with factory throughput and, at times, administrative shutdown orders).
- **Endpoint**: `https://api.waqi.info/feed/<city>/?token=<TOKEN>`
- **Auth**: **free token**, self-service signup at aqicn.org/data-platform/token/ (no payment, near-instant).
- **Cost**: free (personal/non-commercial tier; commercial redistribution has a separate paid tier — check before publishing derived AQI numbers at any real granularity).
- **Rate limits**: shared `token=demo` is explicitly rate-limited/shared; a personal token gets a real (if modest) per-second quota.
- **Cadence + lag**: near-real-time, hourly-ish station updates.
- **History depth**: the free feed API is current-conditions only; historical bulk download is a separate (paid-ish) product.
- **Geo-block status (THIS MACHINE): VERIFIED LIVE** even with the shared demo token — `200`, real Beijing AQI reading (55) with proper attribution metadata pointing at the China National Urban air-quality platform as primary source.
- **akshare wrapper**: none confirmed (akshare's own air-quality modules — `air_hebei`, `air_zhenqi` — hit different, China-domestic aggregators, not aqicn/waqi).
- **ToS/redistribution risk**: low at personal-token tier for our use (derived industrial-proxy signal, not a public AQI display product).
- **Integration effort**: **S**.

### 4.3 高德 Amap traffic
- **Provides / why it matters**: City-level congestion index as a granular, weekly/daily mobility-recovery proxy — finer than official retail-sales/PMI cadence.
- **Endpoint**: `https://restapi.amap.com/v3/traffic/status/road?key=<KEY>`
- **Auth**: **API key required**, and registration (`console.amap.com/dev/id/phone`) is **phone-number-verified** — practically, this points at a **mainland Chinese phone number** for SMS verification, a real friction point for a foreign-registered project (workaroundable via a CN virtual-number service, but that's a workaround, not a clean path).
- **Cost**: free tier exists for modest call volumes; commercial/high-volume tiers are paid.
- **Rate limits**: tiered by key type; free tier is modest (thousands/day class, exact figure not confirmed this session).
- **Geo-block status (THIS MACHINE): VERIFIED reachable (200)** — the API itself isn't geo-blocked; `key=demo` correctly returns a structured `INVALID_USER_KEY` JSON error (not a network block), confirming the endpoint is live and normally-shaped.
- **akshare wrapper**: none.
- **ToS/redistribution risk**: medium — Amap's ToS for the Web Service API typically restricts redistribution of raw traffic data; a derived congestion-index *signal* is more defensible than republishing raw road-segment data.
- **Integration effort**: **M**, gated primarily by the phone-verification signup friction rather than technical difficulty.

### 4.4 Shanghai Shipping Exchange 上海航运交易所 — SCFI/CCFI
- **Provides / why it matters**: Export-goods freight rates (SCFI/CCFI) are a leading indicator for China export volumes/pricing power, watched closely by trade-desk macro shops.
- **Endpoint**: `https://www.sse.net.cn/` (Chinese) and `https://en.sse.net.cn/indices/scfinew.jsp` (English SCFI page).
- **Auth**: none. **Cost**: free (headline index values); the full sub-lane breakdown / historical bulk series may sit behind SSE's subscription data product.
- **Rate limits**: none published (HTML).
- **Cadence + lag**: SCFI weekly (Fridays); CCFI weekly.
- **History depth**: headline chart history on-site; multi-year bulk export not confirmed free.
- **Geo-block status (THIS MACHINE): VERIFIED reachable (200)** on both Chinese and English domains — no block observed.
- **akshare wrapper**: none confirmed (checked; no SCFI/CCFI/`sse.net.cn` reference found in the local akshare install — the BDTI/BSI/LPI shipping-adjacent functions in `macro_china.py` are Baltic-index/domestic-logistics, not SCFI/CCFI specifically).
- **ToS/redistribution risk**: low for headline index levels (standard benchmark citation norm).
- **Integration effort**: **M** — HTML table scrape, page structure looks stable.

### 4.5 Coal (秦皇岛/CCTD 中国煤炭运销协会)
- **Geo-block status (THIS MACHINE): both guessed domains DEAD at the connection level** — `cctd.org.cn` and `cqcoal.com` both returned `000`/connection failure (no response at all, not even a WAF page). This reads as wrong/stale domains rather than a live block; the correct current domain for CCTD/秦皇岛动力煤 price index needs a fresh websearch pass before further investment (not completed this session — flagging as a gap rather than a confirmed dead end).
- **Integration effort**: **unknown** pending correct domain identification; treat as **UNVERIFIED**, not dead.

### 4.6 CPCA 乘联会 — auto/NEV sales — genuinely excellent
- **Provides / why it matters**: The fastest, most granular read on Chinese auto demand — production/wholesale/retail/export, broken out by manufacturer and by fuel type (ICE vs. NEV/PHEV/BEV) — the number the entire EV/battery supply chain trades off monthly, well ahead of official NBS auto-output statistics.
- **Endpoint**: `http://data.cpcadata.com/api/chartlist?charttype=<1-6>` (1=total market, 2=manufacturer rank, 3=vehicle category, 4=country/origin segment, 5=size segment, 6=**NEV/fuel-type split**).
- **Auth**: none. **Cost**: free. **Rate limits**: none published.
- **Cadence + lag**: monthly, released within the first ~3–5 days of the following month (CPCA is famous for being *faster* than NBS on auto volumes).
- **History depth**: current-year + prior-year comparison arrays returned per call (multi-year backfill would need historical calls / isn't obviously exposed as one deep series — not fully explored this session).
- **Geo-block status (THIS MACHINE): VERIFIED LIVE.** `200`, real JSON with monthly production/wholesale/retail/export figures through at least March 2026 (units in 万辆/10k vehicles, with YoY% pre-computed).
- **Sharp contrast**: CPCA's **consumer-facing** domain `cpcaauto.com` is explicitly anti-bot-blocked (`403`, Chinese "please use [a real browser] to access" challenge) — but CPCA's own **data** subdomain (`cpcadata.com`) is wide open. Same organization, opposite bot posture depending on subdomain.
- **akshare wrapper**: yes, a full dedicated module — `akshare.other.other_car_cpca` (`car_market_total_cpca`, `car_market_man_rank_cpca`, `car_market_cate_cpca`, `car_market_country_cpca`, `car_market_segment_cpca`, `car_market_fuel_cpca`) — six ready-made functions, none currently referenced in this repo's `engine`/`scripts` per the earlier grep.
- **ToS/redistribution risk**: low — CPCA publishes this as public market data for industry consumption.
- **Integration effort**: **S** — one of the best value/effort ratios in the entire catalog.

### 4.7 Pork prices 猪肉价格 — MOA 农业农村部
- **Provides / why it matters**: Pork/CPI-food-basket leading indicator; the "猪周期" (pig cycle) is a standard China-macro talking point tightly linked to headline CPI swings.
- **Endpoint**: primary market-price channel is `https://scs.moa.gov.cn/scxxfb/` (市场信息发布/Market Information Release — identified via websearch this session as the actual weekly-report source cited by financial wires, e.g. Sina's "农业农村部：本周生猪价格..." pieces); monitoring/early-warning mirror at `https://www.agri.cn/sj/jcyj/`. **Not yet live-verified this session** — main `moa.gov.cn` domain resolved (200) but the specific guessed sub-path 404'd; the correct `scs.moa.gov.cn` path was found via websearch only, not curl-confirmed.
- **Auth**: none expected. **Cost**: free.
- **Cadence + lag**: weekly (published Monday/Tuesday for the prior week, based on wire citation patterns observed: "本周" reports appearing early the following week).
- **History depth**: monitoring covers 500 counties / 200 wholesale markets nationwide per MOA's own methodology description; historical depth of the machine-facing page not confirmed.
- **Geo-block status: UNVERIFIED** — flagging honestly rather than claiming a result I didn't observe; next step is a direct curl of `scs.moa.gov.cn/scxxfb/`.
- **akshare wrapper**: none confirmed (akshare's `macro_china_agricultural_product`/`agricultural_index`/`vegetable_basket` are Eastmoney-mirrored *basket* indices that include but don't isolate pork).
- **ToS/redistribution risk**: low.
- **Integration effort**: **M**, pending the direct verification above.

### 4.8 Box office 猫眼/灯塔
- **Provides / why it matters**: Consumer-discretionary-spending nowcast; box office is a widely-cited "are people going out and spending" proxy in China consumption commentary.
- **Endpoint**: `https://piaofang.maoyan.com/dashboard` (Maoyan) — page **VERIFIED reachable (200)**, but the guessed API sub-path (`/dashboard/webinfo`) was `404`; the real backing data call is embedded/signed in the page's own JS (`csrf`/`deviceId` meta tags observed, suggesting the real API needs a session-scoped signature, not a bare public JSON endpoint). Alternate: `endata.com.cn` (灯塔/Beacon-adjacent) — **VERIFIED reachable (200)**, redirects to an SPA shell.
- **Auth**: effectively **scrape/signature-required**, not a clean keyless API for either source, based on what's observable from the page shell alone.
- **Cost**: free (headline numbers, publicly displayed). **Rate limits**: unknown.
- **Cadence + lag**: daily (next-day box-office totals are a well-known "overnight" data point in Chinese entertainment/consumption commentary).
- **History depth**: multi-year via the dashboard UI.
- **Geo-block status**: reachable, but **machine path is scrape-only, not a public API** — matches the task's framing of "endpoint hard to find."
- **akshare wrapper**: none confirmed.
- **ToS/redistribution risk**: medium (commercial box-office data product; headline totals are widely re-quoted in press, which is a reasonable redistribution norm to follow).
- **Integration effort**: **M–L** — needs a signed-request reverse-engineering pass (devtools), not a same-session finding.

### 4.9 Excavator sales 挖掘机销量 — CME/CCMA 中国工程机械工业协会
- **Provides / why it matters**: A classic "hard infrastructure activity" alternative-data series, watched as a real-economy cross-check against official FAI/construction statistics (Li Keqiang-index-adjacent logic).
- **Endpoint**: `cncma.org` — **connection aborted** this session (`RemoteDisconnected`, no HTTP response at all) — inconclusive (could be transient, could be an anti-bot TCP-level drop; not enough signal to call it dead vs. flaky).
- **Machine path**: **none found** — CME/CCMA's own site is not obviously a JSON source even when reachable; every current data point found via websearch (Mysteel, SteelOrbis) is a **news re-publication**, not an API call, appearing within days of the monthly release.
- **Cadence + lag**: monthly, news wires re-publish within ~3–7 days of month-end.
- **History depth**: monthly series stretching back years via cumulative press citations; no single bulk source identified.
- **ToS/redistribution risk**: low (these are widely-quoted press statistics).
- **Integration effort**: **M**, and it's a **news-parse-only** series, not a machine API — mysteel.net/steelorbis.com monthly headline scrape is the realistic path, matching the task's own framing ("monthly via CME/news").

### 4.10 100-city land price index / land sales — 中指研究院 (China Index Academy)
- **Provides / why it matters**: Property-market-activity leading indicator (land sales precede construction starts by quarters), and a Chinese-institution-native series most Western property trackers only get third-hand.
- **Endpoint**: `https://www.cih-index.com/` (中指云/CIH Cloud, the Academy's own portal) — **VERIFIED reachable (200)**, server-rendered Vue app; specific report pages like `data/index/newHouse.html` exist per websearch. Alternate mirror: `fdc.fang.com` — **reachable but returned binary/gzip-garbled content to a plain curl** (needs `--compressed`/proper `Accept-Encoding` handling, not attempted with the fix this session — flagging as a retry item, not a dead end).
- **Auth**: none for headline monthly index; deeper weekly land-transaction series is available via **CEIC** (paid third-party aggregator), per websearch — i.e. free access = monthly cadence, weekly = paid.
- **Cadence + lag**: index itself monthly; underlying land-transaction data is transacted continuously and could in principle support weekly aggregation, but the *free* published product is monthly.
- **History depth**: since 2010 (100-cities index launched 2010 per Academy's own history).
- **Geo-block status: VERIFIED reachable**, exact JSON API not yet extracted (portal is a JS SPA — view-source doesn't expose a bare data endpoint the way CFETS/CPCA do).
- **akshare wrapper**: none confirmed.
- **ToS/redistribution risk**: low-medium (Academy is a commercial data/research house; headline index citation is standard practice, bulk scraping their platform less clearly licensed).
- **Integration effort**: **M** — one more devtools pass needed to find the SPA's backing JSON call.

### 4.11 Youth employment status
- Not an API — this is a **methodology/publication-status fact** worth encoding as institutional knowledge rather than chasing a feed:
  - NBS suspended the 16–24 youth-unemployment breakdown in **August 2023** (last clean print: 21.3% in June 2023).
  - Resumed **17 January 2024** under a **revised methodology excluding currently-enrolled students** from the 16–24 cohort — this methodology change is itself a signal Chinese policy-watchers price in (what's excluded changes what the number can embarrass).
  - Continues under the revised methodology through 2026 (recent prints per this session's websearch: 18.9% Aug-2025 graduate-season peak, easing to 16.5% Dec-2025, back up to 16.9% Mar-2026, easing to 15.6% May-2026 — graduate-season seasonality is structural, not noise).
  - **Machine path**: same Eastmoney mirror as 1.1a (`macro_china_urban_unemployment` covers the *headline* surveyed rate; the youth-specific breakdown's live machine path was not separately confirmed this session — likely the same NBS `dg/website` endpoint that 404'd in 1.1, meaning **this may currently be scrape-from-press-release only** from this machine).
  - **Integration effort**: **S** for the institutional-knowledge/methodology note (pure documentation); **M** for a live machine feed of the youth-specific breakdown pending further endpoint discovery.

---

## Family 5 — Hong Kong

### 5.1 HKMA 香港金融管理局 Open API — the standout of this entire survey
- **Provides / why it matters**: HK's entire monetary-plumbing dashboard — HIBOR fixings, aggregate balance, monetary base, Exchange Fund data — in one clean, well-documented, zero-friction API. This is the HK-side equivalent of a PBOC stance engine, and it's dramatically easier to build than the mainland side.
- **Endpoint base**: `https://api.hkma.gov.hk/public/<category>/<...>` — confirmed working paths include:
  - `market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily` — **daily HIBOR across all tenors (O/N through 12M)**
  - `market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-periodaverage` — period-average HIBOR
  - `market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod` and `monetary-base-daily` — **monetary base**
  - `market-data-and-statistics/daily-monetary-statistics/daily-figures-monetary-base` — daily monetary base (incl. **aggregate balance**, a component of this series)
  - `market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics` — broader monetary statistics
  - Full documentation portal: `apidocs.hkma.gov.hk/documentation/`
- **Auth**: **none** — fully public, keyless REST API.
- **Cost**: free.
- **Rate limits**: no hard published limit found; documentation-first design suggests normal courteous-use expectations, not a hard-metered quota.
- **Cadence + lag**: HIBOR fixed and published same-day (~11:30am HKT); monetary base/aggregate balance updated daily, typically same or next business day.
- **History depth**: deep — the docs describe both "monthly bulletin" (longer-run) and "daily statistics" (recent, high-frequency) variants of most series; our test call returned 100 records per page with clean pagination, going back at least to 2026-03 in one page — full depth not exhaustively paged this session but the API design supports it.
- **Geo-block status (THIS MACHINE): VERIFIED LIVE, zero friction.** `200`, textbook-clean JSON: `{"header":{"success":true,"err_code":"0000"},"result":{"datasize":100,"records":[{"end_of_day":"2026-06-30","ir_overnight":3.84024,"ir_1w":3.02643,...}]}}`. No auth, no headers, no WAF, nothing — this just works.
- **akshare wrapper**: **none** — confirmed via grep (`hkma` appears nowhere in the local akshare install). This is a genuinely novel direct-source addition this catalog brings, not previously mirrored anywhere in the existing toolchain.
- **ToS/redistribution risk**: low — this is HKMA's own public-data initiative, explicitly built for programmatic third-party use (comparable posture to data.gov.hk).
- **Integration effort**: **S** — build this first among all Family 5 items; best value/effort ratio in the whole catalog alongside CPCA (4.6) and the Eastmoney NBS mirror (1.1a).

### 5.2 HKEX 香港交易所 — short-selling, CCASS, Stock Connect Southbound
- **Provides / why it matters**: Southbound Stock Connect flow/quota and short-selling turnover are core "mainland money into HK" and "positioning stress" signals; CCASS shareholding is the standard HK ownership-concentration lookup.
- **Endpoints**:
  - CCASS shareholding search: `https://www3.hkexnews.hk/sdw/search/searchsdw.aspx` — **VERIFIED reachable (200)**; a date+stock-code search FORM, real data requires a scripted POST per lookup (not a bulk-download API) — search covers the trailing 12 months per HKEX's own documentation; older history (7 years) requires a written request to HKEX (`psh@hkex.com.hk`), i.e. **not machine-accessible at all beyond 12 months**.
  - Southbound/Stock-Connect shareholding search: `https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=hk` — same domain/pattern, **not separately curl-tested this session** (found via websearch), reasonable to expect same reachability given the sibling path is confirmed live.
  - Short-selling statistics: `https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Short-Selling?sc_lang=en` — **VERIFIED reachable (200)**, but this is a Webflow-rendered page (`data-wf-page` attribute observed) — the real data is behind an AJAX call not identified this session; guessed direct file paths (`scshksh.htm`, `DailyStat_c.htm`) all `404`'d.
  - Northbound daily-quota-balance real-time widget: HKEX states this updates "every minute" on their site; no backing JSON endpoint identified this session (two guessed paths both `404`'d).
  - `disclosure.hkex.com.hk` (company announcements): **DEAD at DNS level, VERIFIED** — `NameResolutionError`, domain doesn't resolve at all from this machine. The correct current home for company disclosures is almost certainly `www.hkexnews.hk` (the same host CCASS search lives on) rather than a separate `disclosure.` subdomain — worth correcting this assumption before further work.
- **Auth**: none for any of the above. **Cost**: free. **Rate limits**: unpublished.
- **Cadence + lag**: short-selling and Connect turnover published daily (T+1 typically); CCASS shareholding as-of-date snapshots, searchable same-day for recent dates.
- **Geo-block status**: everything tested is **reachable**; the gap is data-contract discovery (AJAX backing calls), not access.
- **akshare wrapper**: partial and mixed — `akshare.stock_feature.stock_hsgt_exchange_rate` covers HK-Connect exchange-rate/disclosure ratios but sources them from **SZSE/SSE** (`szse.cn`, `sse.com.cn`), not HKEX directly (see 5.2a). Separately, this repo's own `scripts/collect_hk_connect_roster.py` already documents that akshare's `stock_hk_ggt_components_em` (HK Connect component roster) is **host-WAF-blocked** — a pre-existing, already-known finding, not new this session.
- **ToS/redistribution risk**: low (official exchange statistics, standard citation norm); CCASS/company-disclosure data has clearer redistribution limits (personal-data-adjacent shareholding info) — stick to aggregate/derived signals.
- **Integration effort**: **S** for CCASS/Southbound search (form-POST scraping, well-documented site); **M** for short-selling/quota (needs an AJAX-call discovery pass).

### 5.2a Cross-border Connect data actually lives on the mainland exchanges too
- **Finding**: `akshare`'s HK-Connect-adjacent functions mostly call **`szse.cn`** (`https://www.szse.cn/api/report/ShowReport`) and **`sse.com.cn`** (`https://query.sse.com.cn/commonSoaQuery.do`), not HKEX. Both tested:
  - SSE `commonSoaQuery.do` — reachable (`200`) but returns `ExceptionInterceptor`/`SOA service is null` without the exact akshare-matching `sqlId` + `Referer: https://www.sse.com.cn/` header combination; **with** the Referer header the failure mode changed from a hard interceptor block to a soft "service is null" (wrong `sqlId`, not blocked) — i.e. **reachable and responsive to the right headers, just needs the correct `sqlId`** (not identified this session).
  - SZSE `ShowReport` — **inconsistent**: returned a `50x`-titled error body while curl separately reported `HTTP 000`, suggesting an unstable/gateway-flapping backend rather than a clean block. **UNVERIFIED**, worth a retry rather than a hard "dead" verdict.
- **Integration effort**: **M**, since the reachability question is basically settled (open, needs the right query params/headers) — this is parameter discovery, not access-blocking.

### 5.3 data.gov.hk + C&SD 政府统计处 (Census & Statistics Department)
- **Provides / why it matters**: Official HK GDP, retail sales, visitor arrivals, trade — the HK-side counterpart to NBS, and (unlike NBS) largely open.
- **Endpoints**:
  - Portal: `https://data.gov.hk/` — **VERIFIED reachable (200)**; API spec page `https://data.gov.hk/en/help/api-spec` — **VERIFIED reachable (200)**.
  - C&SD main: `https://www.censtatd.gov.hk/` — **VERIFIED reachable (200)**.
  - C&SD general API `https://www.censtatd.gov.hk/api/get.php` — **DEAD, VERIFIED**: `403 Forbidden`, server header `Microsoft-Azure-Application-Gateway/v2` — blocked at the Azure App Gateway layer regardless of query params tested.
  - **Working alternative — trade statistics subdomain**: `https://tradeidds.censtatd.gov.hk/api/<dataset-hash>/get?lang=en&sv=...&freq=M&period=...&ttype=ALL` — **VERIFIED LIVE**: `200`, real structured JSON (`{"header":{"status":{"name":"Success","code":0},"count":{"noOfRecords":60,...}}}`) with a real 60-record trade-statistics result. The dataset-hash-in-path pattern means each specific table needs its own hash (obtained from data.gov.hk's dataset listing for that table), but the mechanism itself is confirmed live and open.
- **Auth**: none. **Cost**: free. **Rate limits**: unpublished.
- **Cadence + lag**: GDP quarterly (~10 weeks after quarter-end, standard advanced-economy lag); retail sales/visitor arrivals monthly (~5–6 week lag); trade statistics monthly.
- **History depth**: C&SD web tables typically run back to the 1980s/90s depending on series.
- **Geo-block status**: **mixed within the same organization** — general `get.php` API is blocked at the gateway; the `tradeidds.` subdomain (and presumably other per-dataset API subdomains following the same pattern) is wide open. This mirrors the CPCA (4.6) and GACC (1.4) pattern of "one subdomain/path blocked, a sibling one isn't" seen repeatedly in this survey.
- **akshare wrapper**: none.
- **ToS/redistribution risk**: low (official statistics agency, explicit open-data mandate).
- **Integration effort**: **S–M** — need to enumerate the correct per-table dataset-hash for each series wanted (via data.gov.hk's catalog), but the access mechanism itself is proven.

### 5.4 Centaline CCL 中原城市指数 + property valuation
- **Provides / why it matters**: The standard weekly HK secondary-market property-price temperature check, closely watched given property's outsized role in HK household wealth/sentiment.
- **Endpoint**: `http://www.centadata.com/` (Centaline's dedicated data portal, distinct from the main `centaline.com.hk` brokerage site) — **VERIFIED reachable (200)**, a Nuxt/Vue SPA.
- `centaline.com.hk` (main brokerage site) — **DEAD at DNS/connection level this session** (`000`) — not needed anyway since `centadata.com` is the right property for CCL specifically.
- **Auth**: none apparent for headline index. **Cost**: free for the headline weekly index; deeper valuation/transaction-level data is Centaline's commercial product.
- **Cadence + lag**: CCL published weekly (Friday).
- **History depth**: since 1994 (CCL's well-known inception year).
- **Geo-block status: VERIFIED reachable**; exact backing JSON API not extracted this session (SPA shell, same pattern as 4.10's China Index Academy portal).
- **akshare wrapper**: none (confirmed via grep — no false-positive matches survived closer inspection).
- **ToS/redistribution risk**: low-medium (headline index citation is standard practice in HK property commentary).
- **Integration effort**: **M** — one more devtools pass to find the SPA's backing call.

---

## Family 6 — Calendar/event layer

### 6.1 Jin10 金十数据 — the widest machine-readable calendar/report mirror found
- **Provides / why it matters**: Functions as a single clearinghouse for a huge slice of both the *calendar* (what's releasing, actual/forecast/prior) and the underlying *series* for China (and global) macro prints — this is why akshare leans on it so heavily as a backbone.
- **Endpoints** (all distinct, all confirmed this session):
  - `https://datacenter-api.jin10.com/reports/list_v2?category=ec&attr_id=<N>&max_date=...` — the general report-series API (GDP, PMI, CPI, etc. — `attr_id` selects the series). **VERIFIED LIVE**: `200`, real GDP-YoY history (5.2%, 5.4%, 5.4%… back through 2023-10). Requires headers `x-app-id: rU6QIu7JHe2gOUeR` + `x-csrf-token: x-csrf-token` (both literal, **shared/non-personal** values baked into akshare — not real per-user auth).
  - `https://cdn.jin10.com/data_center/reports/<name>.json` (e.g. `il_1.json` = SHIBOR, `sge.json` = Shanghai Gold Exchange daily quotes, `fs_1.json`/`fs_2.json` = spot-price reports) — **VERIFIED LIVE** for `il_1.json`, **zero headers/auth needed at all**, the single easiest endpoint in this entire catalog.
  - Calendar-specific page `https://rili.jin10.com/` — **VERIFIED reachable (200)**; the exact JSON calendar-feed URL pattern guessed this session (`rili.jin10.com/datas/<year>/<date>/economics.json`) was **`404` — wrong pattern, not confirmed**. Jin10 also advertises an official `open-data-api.jin10.com` and an `mcp.jin10.com` (MCP server!) product per websearch — neither tested this session; the MCP angle in particular is worth a follow-up given this project's own MCP-aware tooling.
- **Auth**: none-to-trivial (shared header values, not real per-user credentials) for the two confirmed paths; the calendar-specific JSON path needs more discovery.
- **Cost**: free for what's been verified; Jin10 also sells a commercial terminal product, so there's likely a paid tier for deeper access — not needed for what we verified.
- **Rate limits**: unpublished.
- **Cadence + lag**: same-day mirror of underlying releases.
- **History depth**: GDP report alone returned data back through at least 2023 in one page (paginates via `max_date`).
- **akshare wrapper**: yes, extensively — this is the backbone of ~15+ `macro_china_*` functions (GDP, SHIBOR, HK interbank, SGE gold, spot-price reports) plus the Caixin/RatingDog PMI mirror noted in 1.6.
- **ToS/redistribution risk**: low-medium — Jin10 is a commercial data/media company; the specific JSON endpoints tested are the same ones their own free web frontend calls (not a paid-tier bypass), so this sits closer to "using their public frontend's own API" than to bypassing a paywall.
- **Integration effort**: **S**.

### 6.2 Structured calendar feeds elsewhere
- **stats.gov.cn release schedule**: `https://www.stats.gov.cn/sj/zxfb/` — **VERIFIED reachable (200)** (unlike `easyquery.htm`, this page-level path is not WAF-blocked) — HTML list of release dates/titles, scrape-only, no JSON found.
- **chinamoney calendar**: not separately identified this session beyond the rate/curve endpoints in Family 2; likely exists as an HTML calendar page on the main site (reachable) but no dedicated JSON calendar endpoint found.
- **HKMA calendar**: no separate "calendar" endpoint found in the API docs surveyed; instead, each series (5.1) has a well-known, near-fixed release cadence (HIBOR ~11:30am HKT daily, monetary base same/next business day) that can be hard-coded as a schedule rather than polled from a calendar feed.
- **jin10 calendar**: see 6.1 — page reachable, exact JSON feed URL unconfirmed this session.

### 6.3 Political/policy calendar — encode as static knowledge, not a feed
None of the following have (or should be expected to have) a machine-readable calendar API; they are fixed or announced-ad-hoc institutional rhythms best hard-coded and refreshed manually once or twice a year:
- **Two Sessions 两会**: annual, opens ~March 5 (NPC) with CPPCC just before.
- **Politburo economic meetings**: clustered around late-April, late-July, and the Oct–Dec window (the "①④季" pattern our own context already tracks per the masterplan references).
- **Central Economic Work Conference (CEWC) 中央经济工作会议**: mid-December, sets next year's policy tone.
- **LPR fix**: 20th of each month (or next business day if the 20th falls on a weekend/holiday) — this one **is** algorithmic/structured enough to encode as a rule rather than a lookup.
- **MLF operation**: mid-month, exact day announced same-day via the PBOC OMO bulletin (1.2/2.2) — not predictable in advance beyond "mid-month," so this stays a monitored feed, not a static rule.
- **Quarterly/monthly NBS data days**: ~17th–18th (quarterly GDP), ~15th (monthly activity data) — algorithmic enough to encode as a rule, cross-checked against the stats.gov.cn release-schedule page (6.2) when precision matters.

---

## Appendix A — Failure-mode taxonomy observed this session

Not all "blocked" sources fail the same way; the distinction matters for whether a workaround exists:

1. **WAF ACL block (`403`, `UrlACL` reason, echoes client IP)** — NBS `easyquery.htm`. Reproduced identically via exact akshare-replica calls; genuinely IP/ASN-based, not a header/method issue.
2. **WAF challenge (`412 Precondition Failed`)** — GACC Chinese site. Different signature from #1 but same practical effect; English mirror bypasses it entirely.
3. **Generic anti-bot (`403`, `Zen/4.3` or similar minimal server banner)** — thepaper.cn, cpcaauto.com. No mirror/bypass found for thepaper.cn; cpcaauto.com's own data subdomain (cpcadata.com) bypasses it trivially.
4. **DNS non-resolution** — shibor.org, centaline.com.hk, disclosure.hkex.com.hk. Not a block at all in the WAF sense — the domain doesn't resolve from here, meaning either the domain is genuinely gone/moved, or something in the DNS path (not investigated — could be resolver-specific) fails. Distinct from #1–3 because no amount of header/UA changes helps; only a different domain or a different DNS resolver would.
5. **TLS handshake failure** — `data.mofcom.gov.cn`. The server rejects our TLS ClientHello outright; a browser-TLS-fingerprint-impersonating client (not attempted this session) might succeed where a standard `requests`/curl call cannot.
6. **Gateway-level block on a specific API path, sibling paths open** — `censtatd` `get.php` (blocked, Azure App Gateway) vs. `tradeidds.censtatd.gov.hk` (open); `data.stats.gov.cn/easyquery.htm` (blocked) vs. `.../dg/website/...` (merely 404, not blocked); `cpcaauto.com` (blocked) vs. `cpcadata.com` (open). **This is the single most useful pattern in the whole survey**: a "dead" organization is rarely uniformly dead — check sibling subdomains/paths before writing off the whole source.
7. **Anti-hotlink / Referer-gated, not geo-blocked** — `query.sse.com.cn`. Adding the origin site's own `Referer`/`Origin` header changed the failure from a hard interceptor error to a soft "wrong query ID" error — i.e., fully open once you look like you came from the right page.

## Appendix B — akshare local install as ground truth

This session found `akshare==1.18.64` already installed locally (`/opt/homebrew/Caskroom/miniconda/base/lib/python3.12/site-packages/akshare`). Reading its source directly (rather than guessing endpoints) was the single highest-leverage research technique used this session — it turned several "unknown API" questions into "known exact URL + params + headers, just verify reachability" questions, and surfaced the Eastmoney/Jin10 mirror pattern (1.1a, 6.1) that likely matters more than any single direct-government endpoint in this catalog. Recommend treating the local akshare source tree as a standing reference (`grep -rl <keyword> $(python3 -c "import akshare,os;print(os.path.dirname(akshare.__file__))")`) whenever extending this catalog rather than re-guessing endpoints from scratch.
