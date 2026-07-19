# Stage Analysis (SGA) — program masterplan

Status: **ACTIVE** (chartered 2026-07-19, this PR = W0–W4). Owner lane: `stage-analysis`.
Program codename: **SGA**. Page: `site/stage_analysis.html`. Lobe: `stage-analysis-context-latest`
(synapse data-organ, `external_consumers: [mastermind:context]` — NO metabolism charter at launch;
the 66/66 `lobe_charters.yml` roster is operator-capped and a charter is NOT required for a
display-tier context lobe).

## 0. Why (competitor assessment, 2026-07-19)

EquityDesk.ai ($25/mo, ~2,552-name universe) runs Stan Weinstein 4-stage analysis hunting
**early Stage 2** entries, filtered by **LLM-scored earnings calls**. Their published screen
(all five required): early Stage 2 (trendline recapture or pullback-resume) · ≤10 weeks into
Stage 2 · quality composite ≥85 · earnings-call sentiment ≥24 · earnings-call performance ≥6.
Exit at weekly close when no longer Stage 2. Backtest 2022–2026: 942 trades, ~61% hit,
~7.0% mean / ~2.1% median excess per trade, ~8–9wk hold.

**Their own nulls (published):** a relative-strength gate was tested and REMOVED (negative
typical return 3 of 5 years); industry-strength inside the screen "flattened completely."
Both still *display*. This matches our epistemics exactly: RS and industry are **context,
never gates**. The promotable core is narrow: stage-2 freshness + earnings-call quality +
extension control.

**Our edge over theirs:** (1) bigger universe already on disk (2,758 OHLCV names ≥ their
2,552); (2) our validated T1–T4 confluence cascade as an *additional* independent
confirmation layer they don't have; (3) honest promotion discipline (their LLM scores gate
entries un-gauntleted — ours accrue a shadow ledger first); (4) bilingual, design-doctrine UI.

## 1. Rulings (SGA-R1..R8, pre-registered)

- **SGA-R1 (stage machine).** Weinstein stage is computed on **completed W-FRI weekly bars**
  (reuse `engine/cycles._w_fri_completed`), `ma30` = 30-week SMA of weekly close. Slope
  = `(ma30[t] − ma30[t−5]) / ma30[t−5]` per 5 weeks; FLAT iff |slope| < 0.75% per 5wk
  (≈0.15%/wk). Deterministic state machine **with hysteresis** (prev stage disambiguates
  1 vs 3): Stage 2 = close > ma30 AND slope rising; Stage 4 = close < ma30 AND slope
  falling; Stage 3 = flat slope arriving from Stage 2; Stage 1 = flat slope arriving from
  Stage 4 (or unknown). `weeks_in_stage` tracked; `fresh` = Stage 2 AND weeks_in_stage ≤ 10.
  Event chips: `breakout` (S1→S2 with weekly close > 10-week high on vol_ratio ≥ 1.5),
  `trendline_recapture` (within S2, weekly close recrosses above rising ma30),
  `pullback_resume` (S2, close made ≥3wk low above ma30 then closes up). Constants are
  pinned in `engine/weinstein_stage.py` and may only change with a ruling amendment here.
- **SGA-R2 (RS is context, not a gate).** Mansfield RS `= (rs/rs.rolling(52w).mean() − 1)·100`
  vs SPY, shown as a chip. Never a screen condition (mirrors competitor null + our own
  DO_NOT_REBUILD discipline). Benchmark = **SPY** for all names (single benchmark).
- **SGA-R3 (universe).** All tickers in `data/baskets/ohlcv/` ∪ SP1500 actives
  (`data/universe/membership.parquet`) ∪ `data/stocks/`, deduped, with ≥ 45 completed weeks
  of history. Names with less print as "too young to stage" (counted, not hidden).
- **SGA-R4 (quality score, display-tier).** `sga_score` (0–100) is a **deterministic**
  blend: stage-2 freshness, ma30 slope strength (cross-sectional pctile), Mansfield RS > 0,
  volume confirmation, extension penalty (|close/ma30 − 1| beyond 15% decays score),
  confluence-tier presence (T1/T2/T3 from `site/factordata/signal_gate.json`, read-only
  join per CSP read-gate precedent). **No LLM input at launch.** It ranks ONLY the Stage
  Analysis page (display board precedent: altdata convergence, setup_tier). It feeds no
  scored surface, gate, or sizing.
- **SGA-R5 (earnings-call scores are context-only until gauntleted).** LLM sentiment /
  performance / highlights / tags carry `is_context_only: true`, display as chips + the
  earnings desk section, and are EXCLUDED from `sga_score` until the promotion gate
  (research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md §3: n_graded ≥ 25 dates, Wilson-CI
  lower bound > 0, etc.) passes. LLMs never originate ranking authority (NW Article 1/2).
- **SGA-R6 (single-writer / transport).** The Windows-PC Qwen worker is **producer-only**:
  it writes artifacts to R2 (`earnings_calls/` prefix) and NEVER touches git. Nightly
  fetches via `scripts/fetch_earnings_scores.py` and is the sole ledger advancer.
- **SGA-R7 (shadow ledger from day 1).** Every nightly appends fresh-Stage-2 entries (and
  their earnings context, when present) to `data/stage_analysis/forward_ledger.jsonl`
  (git-committed), graded later by the one-grader spine (`engine/grading.forward_metrics`),
  so the gauntlet clock starts immediately. Prereg for the two promotion hypotheses lives
  in §6 below and is committed BEFORE the first graded observation.
- **SGA-R8 (blackout respect).** The Fresh Stage 2 board flags names within the 3-trading-day
  earnings blackout (`engine/earnings_blackout.assess`) — shown as "earnings soon — wait",
  stance downgraded to *Get ready*, never *Act*.

## 2. Artifact contract — `stage_context.v1`

Written by `scripts/build_stage_analysis.py` (engine: `engine/stage_analysis.py`, classifier:
`engine/weinstein_stage.py`) to `data/stage_analysis/context/latest.json` (git). Same-day
idempotent change feed per `engine/special_sits_intel.py:1018–1134`.

```json
{
  "schema": "stage_context.v1",
  "asof": "YYYY-MM-DD", "built": "...Z",
  "is_context_only": true, "display_only": true,
  "disclaimer": "Context only — stage classification display, never a signal or sizing input.",
  "counts": {"total": 0, "stage1": 0, "stage2": 0, "stage2_fresh": 0, "stage3": 0, "stage4": 0,
              "too_young": 0, "new_today": 0},
  "market": {"pct_stage2": 0.0, "pct_stage4": 0.0, "weather": "advancing|mixed|deteriorating",
              "spy_stage": 2, "spy_weeks": 0},
  "top_stage2": [{"ticker": "", "company": "", "sector": "", "stage": 2, "weeks_in_stage": 0,
      "fresh": true, "sga_score": 0, "ma30_slope_pct5w": 0.0, "pct_vs_ma30": 0.0,
      "mansfield_rs": 0.0, "vol_ratio": 0.0, "event": "breakout|trendline_recapture|pullback_resume|null",
      "gate_tier": "T1|T2|T3|null", "blackout": false, "arc_pos": 0.0,
      "earnings": {"present": false, "sentiment": null, "performance": null, "tone_word": null,
                    "tags": [], "quarter": null},
      "why": [], "why_zh": []}],
  "warnings_stage3": [{"ticker": "", "company": "", "weeks_in_stage": 0, "sga_score": 0}],
  "sectors": [{"sector": "", "n": 0, "pct_stage2": 0.0, "trend": "up|flat|down"}],
  "roster": {"TICKER": [2, 7]},
  "changes": {"items": [{"kind": "entered_stage2|left_stage2|breakout|topping|entered_stage4",
                          "ticker": "", "detail": ""}], "n": 0},
  "prev_state": {"asof": null, "by_key": {}},
  "_current_by_key": {}
}
```

`arc_pos` ∈ [0,1): position along the idealized 4-stage cycle arc (for the page's signature
glyph): stage1 → [0,.25), stage2 → [.25,.5), stage3 → [.5,.75), stage4 → [.75,1), offset
within band by `weeks_in_stage` saturation. `roster` is the compact full-universe map
(ticker → [stage, weeks]); everything else is capped lists (top_stage2 ≤ 60,
warnings ≤ 20, changes ≤ 80) to keep the artifact well under 1 MB.

Earnings-call scores artifact (separate lane, R2-transported):
`data/earnings_calls/scores.parquet` — columns: `ticker, quarter, year, call_date, source
("transcript"|"8k"), model, sentiment (−1..1 float), performance (0..10 float),
confidence (0..1), tone_word, positive_highlights (json), negative_highlights (json),
tags (json), source_sha256, scored_at`. Tag taxonomy (pinned): guidance_raised,
guidance_lowered, beat_and_raise, miss_and_cut, margin_expansion, margin_contraction,
demand_acceleration, demand_slowdown, supply_constraint, new_product, buyback_or_dividend,
regulatory_headwind, competitor_threat, macro_sensitivity.

## 3. Waves

- **W0 (this PR)** — masterplan + preregs (§6).
- **W1 (this PR)** — `engine/weinstein_stage.py` (pure classifier + vectorized weekly state
  machine), `engine/stage_analysis.py` (universe fan-out, sga_score, context feed, ledger
  append), `scripts/build_stage_analysis.py` (CLI), fixtures + tests. Runs in the daily.yml
  parallel band (~5–10 min at 4 cores for ~2.8k names; off the render-critical path).
- **W2 (this PR)** — NW wiring: synapse.yml entry (+SIGNAL_BUS regen + count bump),
  `world_state._compose_stage_analysis`, mastermind summarizer, `ask_brain` read tool
  (`read_stage_analysis`), qual_ladder.yml rows (DISPLAY, max_weight 0.0),
  nw_lobe_descriptions audit, 17+ tests per `tests/test_world_state_special_sits.py` model.
- **W3 (this PR)** — page: `templates/stage_analysis.html.j2` +
  `scripts/build_stage_analysis_page.py` + nav + i18n LEX (design direction §5).
- **W4 (this PR)** — earnings + alt-data substrate: `engine/earnings_qual.py`
  (provider-agnostic scorer harness: OpenAI-compatible endpoint → local Qwen, or
  Anthropic/DeepSeek via `engine/llm_auth`; contract per §2), `tools/earnings_worker/`
  (standalone Windows-PC worker: README + runner + prompts), `scripts/publish_earnings_r2.py`
  + `scripts/fetch_earnings_scores.py` (oracle-panels seam clone), EDGAR 8-K cold-start
  input lane (reuse `collectors/edgar_earnings_8k.py` text), `collectors/google_trends.py`
  (fail-open, pytrends, expected_failure), wiki pageviews activation for top stage-2 names.
  TikTok: **deferred** — no lawful API; revisit if a vendor appears. Reddit: **reuse Quiver
  WSB** (already collected) — a separate Reddit collector adds little and double-counts.
- **W5 (post-login, separate PR)** — competitor backfill: their CSV exports + earnings
  summaries imported to `data/stage_analysis/backfill/` as a calibration yardstick
  (side-by-side stage agreement %, score correlation), NOT as a data dependency.
  ToS/IP consideration flagged to operator 2026-07-19 — proceed only per operator call.
- **W6 (later PRs)** — Qwen worker live on the PC (ops), transcript vendor decision
  (Finnhub paid vs FMP vs EDGAR-only), shadow-ledger maturation → promotion gauntlet →
  `blend_sorted(bonus_of=…)` ≤0.10 stage-confirmation bonus IF the prereg passes; EU/Asia
  market expansion (their "US/EU/Asia" parity); per-ticker stage strips on dossier pages.

## 4. Compute plan (the 2,552/yr earnings problem)

~7 calls/day rolling. Local Qwen on the operator's PC (RTX 5070 = 12 GB VRAM →
**Qwen3-14B Q4_K_M ≈ 9 GB, fits fully on GPU**; Qwen3-30B-A3B MoE with partial offload is
the quality upgrade path given 64 GB RAM). Worker: fetch transcript (vendor TBD; 8-K text
free fallback) → score via local OpenAI-compatible endpoint (llama.cpp / LM Studio / vLLM)
→ write parquet rows → `publish_earnings_r2.py` (needs the same R2 env quad the Mac Studio
uses). Nightly `fetch_earnings_scores.py` (fail-open) → `engine/stage_analysis.py` joins
scores into `top_stage2[].earnings` + earnings desk section. Cloud fallback: the same
`engine/earnings_qual.py` harness runs on Haiku/DeepSeek off-render (stock_briefs job
precedent) for names the PC hasn't covered — capped, cheapest lane.

## 5. Page design direction (Tier-1 law + frontend-design skill; opus designer executes)

**Subject:** a stock's life as a four-season cycle. **Signature element:** the **stage arc**
— the idealized Weinstein cycle curve (base → advance → top → decline) as an SVG motif.
Hero: one large arc with the universe rendered as density dots along it + per-stage counts
+ ONE stance line (e.g. "Most stocks are advancing — good weather for breakouts · 大多数股票处于上升期").
Every board row carries a micro-arc glyph with a dot at the stock's `arc_pos` — position on
the cycle readable with zero vocabulary. Stage palette (page-local accents; theme.css tokens
untouched): S1 steel-blue `#7f97b3`-family, S2 = `--up` family, S3 amber `#d9a441`-family,
S4 = `--down` family. Numbered markers ARE justified here (stages are literally a numbered
cycle) — oversized stage numerals as structural dividers. Sections: (A) hero arc;
(B) **Fresh Stage 2 board** (THE product: ticker, arc glyph, weeks-in-stage, price vs
30-wk line in plain words, volume check, RS chip, earnings tone chip, T-cascade badge,
blackout flag, stance lane per doctrine vocabulary); (C) **This week's transitions** (change
feed); (D) **Earnings call desk** (plain tone line + top positive/negative highlight + tag
chips; honest null: "No call analyzed yet — analysis begins with the next report");
(E) **Sector stage weather** (explicitly context: "context, not a gate — industry strength
didn't add edge in testing"). Tier-1 copy: stages as "Stage 2 · Advancing / 上升期" pairs;
all mechanics/receipts on `data-tip-en/zh` hovers; one as-of; one footnote; stance words
from the doctrine six; NO "validated". Mockup-first; browser-verify against fixture data.

## 6. Preregs (committed before first graded observation; ruler = one-grader spine)

- **SGA-H1 (stage confirmation).** Hypothesis: fresh-Stage-2 (≤10wk) names that ALSO carry
  T1/T2 gate eligibility show higher CLEAN_LIFTOFF and lower STOPPED rates at the 126d
  positional horizon than T1/T2 names not in fresh Stage 2. Falsifier: Wilson-CI lower bound
  of the hit-rate difference ≤ 0 at n_dates ≥ 25 → stage stays display-only context
  (retained as confluence input — a null never deletes the layer). Kill rule: negative
  point estimate at n_dates ≥ 50 across 2 regimes → SGA-H1 closed, row appended to
  DO_NOT_REBUILD §2.
- **SGA-H2 (earnings-call quality).** Hypothesis: among fresh-Stage-2 names, positive
  call scores (sentiment ≥ +0.3 AND performance ≥ 6) improve 21d and 126d outcomes vs
  sector-matched fresh-Stage-2 controls. Same falsifier/kill structure. LLM scores remain
  context-only regardless of outcome until an operator-ratified promotion (≤0.10 capped
  confirmer weight ceiling).

## 7. Standing traps for future lanes

- `data/earnings/` is the CALENDAR store (committed parquet) — the new call-scores lane
  lives in **`data/earnings_calls/`** (gitignored, R2-transported). Never mix.
- SP400 closes cache is missing (`data/midcap_breadth/_closes_cache.parquet` absent) —
  SGA routes midcaps through `baskets/ohlcv` and the deep store; do not "fix" the breadth
  collector inside SGA lanes.
- 30-week SMA on W-FRI weekly closes ≠ 150-day daily SMA. SGA-R1 pins the weekly form.
- Breadth `_closes_cache` split-seam class (#2896-adjacent): prefer `baskets/ohlcv`
  per-ticker parquets (full adjusted series) over breadth wide caches.
- The word "validated", trading verbs in LLM output, `title=` i18n, nav-gap ≥14px,
  paired-asset sync, SIGNAL_BUS count pin, nw_lobe_desc `src_fp` drift — all CI-guarded;
  run the guard suite before every push.
