# EquityDesk — full product teardown (2026-07-20, logged-in reconnaissance)

Source: live walk of every page + sub-tab on equitydesk.ai (authenticated trial), full PostgREST
schema enumeration (51 tables + 10 RPCs), per-table column probes, and network capture. This is the
**complete infrastructure blueprint** for a faithful transfer, ahead of building on top of it.

Supabase project `zmymxrruoppgvxntafvp`. Frontend = Next.js. Two storage buckets:
`research-slides` (per-call ChatGPT/Gemini/Claude research PDFs — the "powerpoints", signed URLs) and
`earnings-transcripts` (raw call transcripts as files; NOT a DB table — 404 as table = it's a bucket).

## 1. Navigation & feature inventory (7 top nav items, ~15 distinct surfaces)

| Nav item | Route | Sub-tabs / views | What it is |
|---|---|---|---|
| **Overview** | `/market-view` | region N.Amer/Europe/Asia; tag L1/L2 | THE flagship screener. 2,552 names. Columns: Ticker, Name, Industry, **Ind %ile**, **SATA**, **Δ SATA**, **Stage** (2X Bullish / 2X Catch), **Weeks**, **ATR Ext**, **ATR % Price**, **Tags**, **EC Sent**, **EC Perf**, **Rating**, Add. Filters on every score column (Ind %ile band, SATA ≥N, ΔSATA, Stage type, Weeks ≤N, ATR Ext, EC Sent >N, EC Perf >N). Per-row icons: 📄 research-slide PDF, 🖥 weekly stage chart. Export CSV. |
| **Trending Stocks** | `/trending-stocks` | **Stage Analysis (Daily)** / **Stage Analysis (Weekly)** | The actual Stage-Analysis screener. Same universe, columns: Ind %ile, **SATA**, **Stage**, **ATR Ext**, ATR % Price, **Weeks**, **Stage Δ** (Yes/No), **SATA Δ**, **M.RS** (Mansfield RS), **RS Δ**. Daily vs Weekly = the two stage tables below. |
| **Industries** | `/price-leaders` | **Ranking**, **Industry Heatmap**, **Industry EC Heatmap**, **Industry Flows** | Ranking: region × Industries/Sub-industries × Leaders/Laggards × timeframe (1D/1W/1M/3M/6M/12M) → Industry Group, Performance%, top-5 stocks. Heatmap: industry rank grid. EC Heatmap: avg earnings-call sent/perf/combined per GICS industry per week. Flows: breadth-rotation engine (stage2/4 ratios, fresh counts, RS change, turn flags). |
| **Earnings Calls** | `/earnings-calls` | **Table**, **Season Analysis**, **Comparison** | Table: per-call Company, Industry, Date, **Score** (sentiment stacked over performance), Tags, Positive Highlights, Negative Highlights, 📄 slide. Season Analysis: per-quarter (Q2'26/Q1'26/Q4'25/Q3'25) Raisers(Δ>5) vs Decliners(Δ<−5) with industry allocation + tag-frequency cloud + Combined-Rating & Performance sliders. Comparison: current-quarter vs prior-quarter combined score + tags → **Δ Combined**. |
| **Research** | (gated) | — | Per-company deep research (OpenAI/Claude/Gemini reasoning + research URL + summary thesis). Table `research_items` RLS-gated on tier; content in `company_generated_info`. |
| **Alt-Data** | `/alt-data` | **Trending Last Week** / **My Watchlist**; source tabs **Google Trends / Reddit / Wikipedia / TikTok** | Per source: trending topics table (Topic, YoY%, 2W Δ%, Type, Description, matched Company ticker, Add). Topics are LLM-matched to tickers with an explanation. |
| **Portfolio** | `/portfolio` | — | User watchlist/portfolio (portfolios, portfolio_companies, images). |

## 2. Data model — the tables that matter (grouped by feature)

### Stage engine (their core)
- **`stageanalysis_stock_sata_stage_rs_ui_all_data`** (DAILY) — the master per-stock stage record:
  `sata_score, sata_score_prev, sata_change_1w, stage_flag, stage_detailed, weeks_in_stage,
  is_stage2_start, breakout_confirmed, stage_changed, rs_ratio, rs_trend_52w, mansfield_rs,
  mansfield_rs_change, mansfield_rs_change_rel, atr_14w, atr_ext, close, sma_30w, week_end,
  industry_id/name/percentile/label/bucket, sub_industry_* (same), gics_industry, gics_sub_industry,
  data_as_of_date, region, ticker/tickerb/ticker_tradingview, name_ui`.
- **`..._weekly_view`** — same columns, weekly-resampled (the "Weekly" tab).
- **`stageanalysis_stock_price_ma_weekly_3y`** — 3yr weekly candles for the chart:
  `date, open, high, low, close, volume, sma_10w, sma_30w, is_up_week, is_latest_week`.
- **`overview_combined_table`** — the flagship join (stage + EC + industry pctile + rating):
  adds `industry_percentile, sub_industry_percentile, industry_bucket, combined_rating,
  earnings_call_sent/perf/combined/pop, call_date, analysts_count, questions_count,
  positive/negative_highlights, level1_tags, level2_tags, stage_detailed`.

### Scoring model (decoded)
- **SATA** = 0–10 proprietary quality/trend score (their strongest rating driver; corr .85 with combined_rating). Formula not exposed in columns; treat as their black box — we reproduce with our own quality composite and calibrate.
- **stage_flag / stage_detailed** — stage_flag e.g. `2X`; stage_detailed e.g. `2X Bullish` (established uptrend) vs `2X Catch` (fresh recapture — their early-entry pattern). is_stage2_start + breakout_confirmed are the event flags (= our breakout/recapture/pullback-resume).
- **Mansfield RS** = `rs_ratio` normalized vs its 52w mean; `mansfield_rs_change` / `_rel` = momentum. (Confirms our SGA-R2.)
- **ATR Ext** = ATR-based extension from the 30w line (extension penalty proxy). ATR % Price = atr_14w/close.
- **Industry percentile / bucket** = the name's price-momentum percentile within its GICS industry (from `stageanalysis_industry_ranks_weekly`: score, rank, bucket, z_rsroc, z_mom, industry_percentile).
- **combined_rating** = SATA-dominated blend (SATA .85 / ATR-ext .72 / RS .65 / EC .57 from W5 regression).

### Earnings (`earnings_call_data`) — the qualitative engine
`call_positivity_score, management_confidence_score, analyst_criticism_score, future_outlook_score`
→ **EC_sent = call_positivity + management_confidence + future_outlook − analyst_criticism** (0–30, gate ≥24; CONFIRMED 3431/3431 in W5). `earnings_call_perf` = signed performance (−12..12), `earnings_call_combined = sent + perf`, `earnings_call_pop`. Plus `raised/lowered_revenue_estimates(+reason)`, `raised/lowered_eps(+reason)`, `improved/deteriorated_business_conditions`, `improved/deteriorated_gross_margin`, `revenue_growth, eps_growth, gross_margin, key_quote, summary, positive_highlights, negative_highlights, unified_analysis` (Gemini JSON), `file_path` (slide PDF), `level1_tags, level2_tags, gics_*, analysts_count, questions_count`.
- **`earnings_call_gics_industry_weekly`** — EC heatmap: `as_of_date, gics_industry, companies_with_fresh_ec, avg_earnings_call_sent/perf/combined`.

### Industry rotation / flows
- **`industry_flows`** + **`subindustry_flows`** — a real breadth-rotation engine per industry:
  `rs_chg_4w_median, rs_chg_1w_median, sata_mean, breadth_4w_pct, stage2_stage4_ratio,
  stage2_count, stage4_count, fresh_stage2_count/pct, fresh_stage4_count/pct, stage2_median_age_wks,
  state, turn_flag, lookback_days, formula_version`. (This is essentially sector rotation via stage breadth — directly relevant to Prophet-integration.)
- **`stageanalysis_industry_ranks_weekly`** — industry momentum ranks (z_rsroc, z_mom, percentile).
- **`top_performers_by_industries`** (+ `_leaders_laggards_horizontal_view`) — per-industry top-5 across timeframes with volume ratios (the Ranking view).

### Alt-data (4 sources, LLM-matched to tickers)
- **`alt_data_{gt,reddit,tiktok,wiki}_companies_matched`** — each maps a trending
  {google_query / subreddit / hashtag / wikipage} → matched ticker + `explanation` + classifier + matching_date.
- Raw trending: **`google_trends_trending_topics, trending_subreddits, top_growing_subreddits,
  top_growing_tiktok_pages, wiki_top_pages`** (Topic, YoY%, 2W Δ%, type, description).

### Trending / volume / news / research / themes
- **`volume_analytics`** — volume_ratio, is_high_volume, avg_volume_20d, price_change_1d.
- **`news_history`** — headline, summary, url, source, timestamp, region.
- **`company_generated_info`** — the Research deep-dive: `full_openai_response, claude_reasoning_analysis,
  openai_reasoning_analysis, gemini_reasoning_research_url, summary_thesis_answer, model_used, tier`.
- **`themes` / `theme_companies` / `theme_performance_view`** — user thematic baskets + returns.
- **`companies` / `ticker_mappings`** — identity + full GICS taxonomy (sector→industry_group→industry→sub_industry, with codes).

### RPCs
`get_latest_earnings_per_company` (used for W5 backfill), `get_admin_status`, `can_access_company`,
`get_research_availability(_for_tickers)`, `start_guest_access`, `has_promo_override`, + admin fns.

## 3. What we already have vs what this pull adds

- **Had (W5):** `overview_combined_table` (6,536) + latest earnings (3,431). EC formula decoded. Stage engine calibrated 73.3%/85% vs their stage_flag; SMA r=1.0.
- **New this pull:** full `earnings_call_data` (all quarters → Comparison/Season), 4× alt_data matched + 5× trending-topic tables (**incl. TikTok, which we could not source natively**), industry_flows + subindustry_flows (rotation engine), industry_ranks_weekly, ec_gics_industry_weekly (heatmap), top_performers (ranking), company_generated_info (research), themes, volume_analytics, news, ticker_mappings (GICS taxonomy).

## 4. Design verdict (why ours must be better)

Their UI is **light-mode-only, flat, utilitarian** — dense tables, tiny colored score chips, no dark mode,
no chart-forward hero, no motion, primitive typography. It is a data terminal, not a product. Our transfer
must be a **dark-first, billion-dollar-SaaS** surface matching our native design language (the macro.html /
Terminal quality bar), with: a chart-forward stage view (weekly candles + 10w/30w MA + stage bands),
readable dark-mode contrast (the prior build's black-on-dark text was the exact defect to never repeat),
progressive-disclosure per DESIGN_DOCTRINE, and every score explained in plain words on Tier 1.

## 5. The end goal — Prophet × Stage Analysis (the actual thesis)

Prophet times entries (2–3wk holds) but can buy bounces inside downtrends. Stage Analysis adds:
(a) a **trend-quality gate** — only take Prophet signals in Stage 2 (rising 30w MA), veto Stage 4;
(b) an **earnings/fundamental qualitative layer** (EC_sent/perf, tags, highlights) for conviction;
(c) the possibility of **longer holds** (their ~8wk vs our 2–3wk) when stage + quality both hold.
Hypothesis: the Prophet∩Stage-2∩positive-EC intersection lifts win rate and cuts bad-trend bounces.
This is the integration target AFTER the faithful transfer + our upgrades land.
