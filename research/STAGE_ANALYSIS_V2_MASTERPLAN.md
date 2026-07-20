# Stage Analysis v2 — full EquityDesk transfer + upgrade (SGA-2)

Status: **ACTIVE** (2026-07-20). Supersedes the v1 single-page build (which was an interpretation, not a
transfer). Grounded in `research/EQUITYDESK_TEARDOWN.md` (complete live teardown + 51-table schema).
Reuses v1 infrastructure where sound (`engine/weinstein_stage.py`, `engine/stage_analysis.py`, the lobe,
the earnings-qual harness, R2 seam) — but **rebuilds the surface as a faithful, multi-view, dark-first hub**
and adds the engines their features require.

## 0. Doctrine for this program (why v1 failed, what changes)

1. **Transfer first, improve second.** Build every EquityDesk surface faithfully (same columns, same score
   semantics, same views) BEFORE layering our upgrades. You cannot improve what you haven't reproduced.
2. **Design is a deliverable, at opus+.** Their UI is light-only, flat, primitive. Ours is dark-first
   billion-dollar SaaS matching macro.html / Terminal. The v1 defect (black text on dark bg) is the exact
   failure mode to never repeat — every surface browser-verified in DARK mode with real data.
3. **Our data, their yardstick.** We compute stages/scores from OUR OHLCV, calibrated to their tables
   (73.3%/85% already). Their pulled data = seed backfill + calibration reference, not a runtime dependency.
4. **Epistemics unchanged.** Stage/SATA/EC scores ship DISPLAY-tier; LLM earnings scores context-only;
   Prophet integration is a gauntleted phase-2 hypothesis, not a launch gate.

## 1. Information architecture — the Stage Analysis hub

One hub, tabbed client-side over committed JSON artifacts (mirrors their nav; matches our hub-page pattern).
Route stays `stage_analysis.html`. Six primary surfaces:

| # | Surface | Mirrors EquityDesk | Data artifact |
|---|---|---|---|
| **A** | **Screener** (flagship combined table) | Overview | `screener.json` (from overview_combined_table + our engine) |
| **B** | **Stage Board** — Daily / Weekly toggle | Trending Stocks | `stage_board_{daily,weekly}.json` |
| **C** | **Industries** — Ranking · Heatmap · EC Heatmap · Flows | Industries (4 views) | `industry_ranks.json`, `industry_flows.json`, `ec_industry.json` |
| **D** | **Earnings Calls** — Table · Season · Comparison | Earnings Calls (3 views) | `earnings_table.json`, `earnings_season.json`, `earnings_compare.json` |
| **E** | **Alt-Data** — Google · Reddit · Wikipedia · TikTok | Alt-Data | `altdata_trending.json` |
| **F** | **Research** — per-company deep dives + transcript reader | Research + transcript view | `research_index.json` + per-ticker |

Column parity for A/B (the core tables): Ticker · Name · Industry · **Ind %ile** · **SATA** (0–10) ·
**Δ SATA** · **Stage** (2X Bullish / 2X Catch, i.e. established vs fresh-recapture) · **Weeks** ·
**ATR Ext** · **ATR % Price** · **Tags** · **EC Sent** · **EC Perf** · **Rating** (0–100) · Mansfield RS + Δ.
Every score column is filterable (their exact filter bands). Every row: mini weekly stage chart on hover/expand.

## 2. Engines to build (compute from our data; calibrate to their tables)

1. **Stage engine v2** (`engine/weinstein_stage.py` + `engine/stage_analysis.py` extend):
   - `stage_detailed`: `2X Bullish` (Stage 2, established, ma30 rising ≥N weeks) vs `2X Catch`
     (fresh recapture/pullback-resume, weeks ≤ threshold) — mirror their taxonomy.
   - `sata_score` (0–10): reproduce their quality score from our quality composite + stage strength,
     **calibrated** to `overview_combined_table.sata_score` (target the .85 combined-rating driver).
   - `atr_ext` (extension in ATR-14w units from ma30), `atr_pct_price` (atr_14w/close).
   - Mansfield RS + `rs_change` (already have), `industry_percentile` (from engine #2).
   - Weekly variant view.
2. **Industry ranks** (`engine/stage_industry.py`): per-GICS-industry `z_rsroc` (RS rate-of-change z),
   `z_mom` (momentum z), composite `score`, `rank`, `bucket`, `industry_percentile`. Powers Heatmap + Ranking + the
   name-level Ind %ile join.
3. **Industry flows** (`engine/stage_flows.py`): per-industry breadth-rotation — `stage2_count/stage4_count`,
   `stage2_stage4_ratio`, `fresh_stage2_count/pct`, `breadth_4w_pct`, `rs_chg_4w/1w_median`, `sata_mean`,
   `stage2_median_age_wks`, `state`, `turn_flag`. (This is the sector-rotation-via-stage engine — a genuine
   new signal for us; ties into Prophet integration.)
4. **EC industry heatmap** (`engine/stage_ec_industry.py`): weekly avg EC sent/perf/combined + fresh-EC count
   per GICS industry (from our earnings scores + backfill).
5. **Earnings season + comparison** (`engine/earnings_qual.py` extend): season aggregation (raisers Δ>5 /
   decliners Δ<−5, industry allocation, tag-frequency), and QoQ comparison (current vs prior quarter Δ combined).
6. **Alt-data trending** (`engine/altdata_stage.py` extend / importer): the 4 sources as topic→ticker matches.
   Seed from their pulled tables; our own collectors continue forward (google_trends already built; reddit=Quiver;
   wiki=active; tiktok=SEED-ONLY from them, no lawful live source yet — disclosed).
7. **Research** (`engine/stage_research.py`): per-company deep-dive index (seed from `company_generated_info`);
   our own generation via the Qwen/cloud harness forward. Transcript reader surfaces `summary` + `unified_analysis`.

## 3. Importers (seed backfill from the pulled tables)

`scripts/import_equitydesk_full.py` — reads `~/Documents/Cluade/equitydesk_backfill/full/*.json`, writes
committed parquet seeds under `data/stage_analysis/backfill/`:
`overview.parquet, earnings_calls.parquet, industry_flows.parquet, subindustry_flows.parquet,
industry_ranks.parquet, ec_industry.parquet, top_performers.parquet, altdata_{gt,reddit,tiktok,wiki}.parquet,
trending_topics.parquet, research.parquet, themes.parquet, volume.parquet`. Each surface's engine reads its
own computed data with the backfill as fallback/seed + calibration yardstick. Large tables (stage history,
price_ma_weekly_3y) stay in the backfill dir (gitignored) — we reproduce from our OHLCV. Transcripts:
list the `earnings-transcripts` storage bucket; import viewable text where present (skip the slide PDFs).

## 4. Design direction (opus `designer` executes; DARK-FIRST, browser-verified)

- **Dark-first**, our token system (theme.css) — NEVER hardcode text colors; every surface verified readable
  in dark mode with real data (the v1 killer bug).
- **Chart-forward**: the signature is the weekly stage chart (candles + 10w/30w MA + stage bands + up/down
  volume) — theirs is a plain table; ours leads with the visual.
- **Score chips** with plain-word meaning on hover (Tier-1 doctrine): SATA, Stage, Ind %ile, EC Sent/Perf,
  Rating — each a compact chip + a `data-tip` explaining what big/small means.
- **Dense but elegant** tables (their density, our polish): sticky headers, virtualized rows, filter bar,
  CSV export, region + tag (L1/L2) toggles.
- Bilingual EN/ZH throughout; stances/nulls in plain words; no "validated"; no black-on-dark.

## 5. Prophet × Stage Analysis (phase 2 — the thesis, after transfer lands)

Once the transfer + upgrades are live and stable: build `engine/prophet_stage_fusion.py` — for every Prophet
signal, join the name's stage (must be Stage 2, ma30 rising), EC quality (sent/perf), and industry flow state;
emit a **fusion conviction** and a **hold-extension** flag (Stage 2 + positive EC → allow ~8wk hold vs our 2–3wk).
Pre-register SGA2-H1 (Prophet∩Stage2∩EC+ lifts win rate / cuts bad-trend bounces vs Prophet alone) on the
one-grader spine; gauntlet before any ranking authority. This is the integration payoff and the reason for
the whole program.

## 6. Waves

- **W1** — importer + all backfill seeds committed; `research/EQUITYDESK_TEARDOWN.md` (done).
- **W2** — engines: stage v2 (sata/stage_detailed/atr_ext), industry ranks, industry flows, EC industry,
  earnings season/comparison; artifacts + tests.
- **W3** — the dark hub: 6 surfaces, real data, browser-verified dark mode (opus designer).
- **W4** — alt-data + research + transcript reader surfaces; calibration report vs their tables.
- **W5** — Prophet fusion engine + prereg (phase-2 thesis).
