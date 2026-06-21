# China Macro Intelligence Powerhouse — design + free-data source catalog

Status: **building** (2026-06-20). Companion to the approved plan
(`.claude/plans/crispy-riding-dijkstra.md`). This is the durable reference for the
four new China intelligence surfaces and the Mastermind transmission bus:

1. **China News** powerhouse (multi-source wire + PIT event bus + media-sentiment)
2. **China Alternative Data** desk (flows / LHB / pledges / unlocks / convergence)
3. **China Central Bank & Government Policy Watch** (PBoC corridor + policy feed)
4. **China Divergence Radar** (policy/flow/credit signal vs sector price)
5. **China Intelligence transmission bus** → future China Mastermind bot

It mirrors the discipline of `research/CHINA_DATA_AUDIT.md` / `VECTOR_DATA_AUDIT.md`:
free, keyless, **globally reachable** (proxy for GitHub-Actions CI from a non-CN IP),
`akshare` + Eastmoney datacenter JSON (browser UA + `Referer`) + RSS. Every signal is
**display/context-only** until a Phase-0 harness validates it (the repo house rule).

---

## Reachability tiers (verified pattern, live-probed by research agents)

| Tier | Hosts | Notes |
|---|---|---|
| **Reliable from global IP** | Eastmoney `datacenter-web` / `push2his` / `push2ex` / `search-api-web`, `cdn.jin10.com`, `english.news.cn` RSS, `chinadaily.com.cn` RSS, GDELT, cninfo POST, PBoC `pbc.gov.cn/en/*` HTML | the spine — build on these |
| **Usually OK, throttle** | Sina RSS/finance, THS, Futu, Baidu media | UA + `sleep ≥1s + jitter`; degrade gracefully |
| **Best-effort / fragile** | MOFCOM `data.mofcom.gov.cn` (TSF `macro_china_shrzgm`, legacy SSL), public RSSHub instances (CLS/Yicai/Jin10/Caixin), MOF/NDRC/CSRC scrapes | mark `expected_failure`; never load-bearing |
| **GeoIP-BLOCKED — do not use** | NBS EasyQuery `data.stats.gov.cn` | use Eastmoney mirror of the same series instead |
| **Dead / discontinued** | Northbound Connect *direction* (curtailed Aug-2024), `stock_info_global_cls` direct (broke Feb-2025 → RSSHub) | do not lean on |

---

## 1. China News — sources

Existing: `collectors/china_news.py` (CCTV 新闻联播 tone) + `engine/china_news.py`
(Eastmoney flash via `stock_info_global_em`). **Add** a multi-source wire + per-ticker
news + a PIT event bus.

| Source | Access | Lang | Freq | Reach | Gives |
|---|---|---|---|---|---|
| CCTV 新闻联播 | `ak.news_cctv(date)` | zh | daily | reliable | official policy-tone transcript (have) |
| Eastmoney 全球财经快讯 | `ak.stock_info_global_em()` | zh | realtime | reliable | broad domestic flash wire (have) |
| Sina flash | `ak.stock_info_global_sina()` | zh | realtime | throttle | flash wire |
| THS flash | `ak.stock_info_global_ths()` | zh | realtime | throttle | flash wire |
| Futu flash | `ak.stock_info_global_futu()` | zh | realtime | reliable | HK/US-tilted flash |
| Per-stock news | `ak.stock_news_em(symbol)` | zh | on-demand | reliable | multi-year per-ticker news timeline |
| Xinhua business (EN) | RSS `english.news.cn/rss/businessrss.xml` | en | continuous | reliable | official state wire (PBoC/NDRC/SOE) |
| China Daily biz (EN) | RSS `chinadaily.com.cn/rss/bizchina_rss.xml` | en | hourly | reliable | EN business/policy |
| GDELT (China) | `api.gdeltproject.org/api/v2/doc/doc` `sourcecountry:CH sourcelang:zho/eng` | en/zh | 15-min | reliable | sentiment timeline + intl coverage |
| CLS 财联社 / Jin10 / Yicai | RSSHub routes `/cls/telegraph`, `/jin10`, `/yicai/headline` | zh | realtime | fragile (self-host) | pro telegraph wires |

**Design:** `collectors/china_news_wire.py` (append-only `data/china_news/wire.parquet`)
+ `collectors/china_news_stock.py` (`data/china_news/by_ticker.parquet`). Engine
`engine/china_news_intel.py`: PIT bus (`data/china_news_vector/events.parquet`,
keep-FIRST like `engine/news_vector.py`), Chinese theme buckets (reuse
`china_news.MACRO_THEMES` + add geopolitics/trade/industrial_policy), `scheduled_ref`
stamp vs `china_event_calendar`, a **media-sentiment index** (z-scored CCTV+wire tone),
entity→`cn_*`-basket map, gated bilingual DeepSeek brief.

---

## 2. China Alternative Data — sources

Existing (reuse): `china_connect` (southbound), `china_flows` (AH premium / limit
breadth / ETF shares), `china_margin` + `china_margin_detail`, `china_analyst`,
`china_valuation`, `hk_southbound_holdings`. **Add** (all keyless akshare, reliable):

| Signal | akshare fn | Gives |
|---|---|---|
| Per-name fund flow 资金流 | `stock_individual_fund_flow(stock, market)` | super-large/large/med/small net inflow (main-force vs retail) |
| Sector/concept flows | `stock_sector_fund_flow_rank(indicator, sector_type)` | daily sector & theme rotation heat |
| Dragon-Tiger 龙虎榜 | `stock_lhb_detail_em(start,end)` | institutional hot-money fingerprint (brokerage seats) |
| Pledges 股权质押 | `stock_gpzy_pledge_ratio_em()` | forced-sell risk league table |
| Unlocks 限售解禁 | `stock_restricted_release_queue_em()` | forward supply-overhang calendar |
| Block trades 大宗交易 | `stock_dzjy_mrmx(symbol,start,end)` | block premium/discount + buyer/seller desks |
| Insider 高管增减持 | `stock_hold_management_detail_em(symbol)` | exec buy/sell |
| Buybacks 回购 | `stock_repurchase_em(symbol)` | management conviction / price support |

NOT free/keyless (skip): Baidu 百度指数 (cookie auth), Weibo/Xueqiu/Guba (no keyless
CI path; `stock_hot_keyword_em()` is the only free sentiment proxy).

**Design:** collectors above → `engine/china_signal_lab.py` (`CHINA_REGISTRY` honest
tiers; scored legs already in `china_masterminds` = credit-impulse/vol/margin) +
`engine/china_altdata.py` (per-ticker rank-aggregate **convergence kernel**,
display-only with Phase-0 hooks). Emits `site/chinaaltdata/{feed,by_ticker,mastermind}.json`.

---

## 3. China Central Bank & Government Policy Watch — sources

Existing (reuse): `china_macro` (LPR 1Y/5Y, RRR, PMI/CPI/PPI/M2/IndPro/GDP/loans/FAI/
retail/customs/SHIBOR), `china_credit` (TSF), `china_property` (CGB curve, 70-city).

**PBoC corridor / liquidity (add `collectors/china_pboc.py`):**

| Series | akshare fn / source | Reach | Note |
|---|---|---|---|
| LPR 1Y/5Y | `macro_china_lpr()` / EM `RPTA_WEB_RATE` | reliable | have (`china_macro/lpr_rate`) |
| RRR 存准率 | `macro_china_reserve_requirement_ratio()` / EM `RPT_ECONOMY_DEPOSIT_RESERVE` | reliable | big/small-bank before/after |
| FX reserves + gold 外储 | `macro_china_fx_gold()` / EM `RPT_ECONOMY_GOLD_CURRENCY` | reliable | FOREX 亿USD + gold tons |
| MLF / OMO rate events | `macro_bank_china_interest_rate()` (Jin10) | reliable | 7-day reverse repo is the primary rate since Jul-2024 |
| Money-market rates | `repo_rate_query()` (FR007/FDR007≈DR007), `macro_china_shibor_all()` | reliable | liquidity conditions |
| USD/CNY parity vs CNH | `currency_pair_hist`/`forex_pair_quote("USDCNY"/"USDCNH")` | reliable | CNY/CNH spread = outflow pressure |
| PBoC balance sheet | `macro_china_central_bank_balance()` (Sina) | reliable | PSL/MLF/SLF line items |
| Daily OMO net inject/drain | PBoC `pbc.gov.cn/en/3688110/3688181/{id}/` HTML | fragile | sequential numeric IDs; degrade to FR007−LPR spread proxy |

**Gov / fiscal / policy feed (add `collectors/china_policy_feed.py`):** no official
RSS/JSON for policy text — HTML scrape, dated + tiered:
State Council `gov.cn/zhengce/zuixin.htm` (+ EN `english.www.gov.cn/policies/`),
NDRC `en.ndrc.gov.cn/news/pressreleases/`, MOFCOM, CSRC, MOF, PBoC press, Xinhua RSS,
`news_cctv`. Fiscal: `macro_china_czsr` (revenue), `macro_china_national_tax_receipts`,
Caixin PMI `macro_china_cx_pmi_yearly`/`_cx_services_pmi_yearly` (Jin10).
NPC/CPPCC annual targets (GDP target, deficit ratio, special-bond quota, FYP sector
priorities) = hardcode annually from the Work Report.

**Design:** `engine/china_pboc_stance.py` (corridor classifier → easing/neutral/
tightening, `fed_stance` analog) + `engine/china_policy_watch.py` (assembler) +
`data/china_policy/intel.json` (curated PBoC/State-Council/NDRC substrate + sector-
policy matrix). Page models on US `policy_watch.html.j2`.

---

## 4. China Divergence Radar — taxonomy + pairs

No radar exists in the repo. Build fresh. Kernel = pair a management-independent
forward-demand/policy/flow **signal-A** vs sector/basket **relative-strength signal-B**
→ POSITIVE / NEGATIVE divergence (SILENT on the diagonal); winsorised z; falsifiable
hypothesis seed; ledger accrues on signal day. All display-only until Phase-0.

**Sector taxonomy:** Shenwan 申万一级 31 industries; map to the 16 repo sector ETFs
(banks 512800, brokers 512880, baijiu 512690, semis 512760, NEV 515030, solar 515790,
defense 512660, nonferrous 512400, coal 515220, real-estate 512200, …) and the 18
existing `cn_*` baskets. Sector flows via `stock_sector_fund_flow_rank`.

**Policy-driven themes (2025-26)** for theme-level divergence: 信创/国产替代 semis
(512760), humanoid robots 562500, AI compute, EV/battery 515030, solar/storage 515790,
defense 512660, SOE-reform 中特估 (561580/512580), consumption 以旧换新 (159928),
property stabilization 512200, innovative pharma 创新药 (159992), low-altitude economy
低空经济 (159230), data elements 数据要素, gold/nonferrous (518880/512400).

**Candidate divergence pairs (data already on disk — see exploration):**

| Pair | Signal-A (source) | Signal-B | Freq | Mgmt-indep? |
|---|---|---|---|---|
| Credit impulse vs sector | TSF 12m-sum YoY (`china_credit/tsf`) | sector/basket RS | monthly | high |
| PBoC easing vs rate-sensitive | RRR+LPR cumulative (`china_macro`) | banks/property/brokers RS | lumpy | high |
| Sector fund-flow vs price | `stock_sector_fund_flow_rank` | sector price | daily | low |
| Analyst EPS revision vs price | `china_analyst/forecast` | per-basket price | daily | low |
| PMI/PPI vs cyclicals | `china_macro/pmi`,`ppi` | metals/steel/machinery RS | monthly | high |
| Southbound vs price | `china_connect/southbound` | HSI/basket RS | daily | partial (reuse existing display-only chip) |

Most US-analogous (management-independent forward-demand, data on disk): **credit-
impulse** and **PBoC-easing** pairs.

---

## 5. Transmission bus → Mastermind

`engine/china_intel_bus.py` bundles the four surfaces into a schema-versioned,
context-only `china_intel.briefing.v1` (`site/china_intel/briefing.json`) + a compact
`digest.json`, consumed by the future China Mastermind bot. Extends
`engine/master_brain.gather_china_state()` so the new compact scalars reach the
china-lens LLM brief. Hub page `site/china_intel.html`.

`briefing.v1` shape (context-only, never a score/size):
```
{ schema:"china_intel.briefing.v1", is_context_only:true, generated_utc, asof,
  news:    {sentiment_z, band, top_themes[], scheduled_ahead[], n_events_7d},
  policy:  {pboc_stance, lpr_1y, lpr_5y, rrr, fx_reserves, last_moves[], predictions[]},
  altdata: {convergence_top[], convergence_bottom[], crowding_flags[]},
  radar:   {divergences:[{pair, sector/theme, sign, z, hypothesis}]},
  digest:  "<= ~1500-char plain-text Opus-optimized rollup" }
```

---

## Operational gotchas (carried from research + repo)

1. Eastmoney needs a browser UA; `sleep ≥1s + jitter`; >5-6 parallel workers → 429.
2. Lazy-import `akshare` inside `fetch()` so a missing dep never drops an adapter.
3. Datacenter rows carry a RangeIndex → assign by `.to_numpy()` or they NaN-align.
4. `repo_rate_hist` max 1-calendar-month window → paginate.
5. TSF (`macro_china_shrzgm`) MOFCOM POST may be CN-IP-gated → `expected_failure`.
6. NBS EasyQuery is GeoIP-blocked → always use the Eastmoney mirror.
7. Bilingual: every `label` needs `label_zh`; **never** `t()/td()` inside `title=`
   (emits `<span>`); add finite vocab to `engine/i18n.LEX`.
8. New pages: `{% extends "report_base.html.j2" %}` (gives nav/theme/lang/footer),
   fill `title`/`base_css`/`content`; render in a `scripts/build_china_*.py` with
   `env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)`.
9. Honest discipline: display/context-only until a Phase-0 harness validates;
   Northbound *direction* is dead post-2024-08.
