# TrendSpider-Grade Hardening — ticker-chart post engine masterplan

*Program owner: marketing chart family (`watchlist` / "On Our Radar", `chart`, `signal`, `mover`).
Authored 2026-08-02 from a 396-post @TrendSpider corpus study (19.9 days, Jul 14 – Aug 3 2026,
median 82k views/post) + 32-image chart-design autopsy + full recon of our own pipeline.
Corpus + per-image catalogs archived under `mockups/refs/trendspider-hardening/`.*

---

## §0 ACCEPTANCE GATES (read first; every builder PR is judged on these)

A build in this program is **not done unless**:

1. **Renderer backward compatibility** — every existing `render_chart_v2` call site renders
   byte-plausibly unchanged when no new kwarg is passed (snapshot test on a pinned OHLCV
   fixture). New primitives ship with golden-sample SVG fixtures under `tests/fixtures/` and
   **rendered PNG crops posted in the PR body** (light inspection is not optional — charts are
   user-facing surfaces; the operator sees crops before merge).
2. **Claim-window law** — a superlative or analog-count fact ("worst week since 2022",
   "third touch of the 200-day") may only ship when its FULL evidence window lies inside the
   plotted axis range of the attached chart. The spec builder rescopes the claim or widens the
   chart; if neither is possible the fact is dropped. This is the inverse of TrendSpider's
   documented failure mode (3 of 13 sampled charts assert "ever"/"since 2015" on an axis that
   starts in 2025) and it is enforced in code, not in prompt text.
3. **PIT discipline** — superlative/streak/analog facts are computed from the same
   split-adjusted series the chart plots, with the PIT max-date guard
   (see memory: `pit-anchor-max-date-null-trap`): a null/short history **suppresses the fact**,
   never falls back to a snapshot. No fact may be computed from `massive_stock_day` without
   split-adjustment care.
4. **Display-tier only, A7 intact** — stage reads, attention ranks, options-volume ranks and
   every new selection feed are display-tier context. No "validated" in any user-facing string
   (CI-enforced already); the LLM writer never originates a ranking, score or signal — it
   captions facts the deterministic layer computed.
5. **Copy law extensions honored** — chart-family captions: 7–12 word target, 100-char hard
   cap, horizon disclosed by the chart header (`TICKER WEEKLY`), not the caption; a number may
   appear in the caption only if the chart restates it in-frame (axis tag, measurement box, or
   callout); the existing banned-vocab law stands for COPY (never name MACD/RSI/AVWAP/POC in
   text) while CHART LABELS may name indicators (`50 SMA` inline label) — that asymmetry is the
   law's existing design (`config/marketing.yml` copy_laws) and it is exactly TrendSpider's
   split: show the 200 EMA, don't say it in the hook.
6. **Selection diversity is measurable** — after the selection PR, the nightly plan must draw
   its chart-family candidates from a pool ≥1,000 US names, must introduce ≥3 tickers/day that
   haven't been posted in 30 days (long-tail quota), and caps any one ticker at 3 chart posts
   per day. A pool/quota shortfall prints a `::warning` (bare print, line-start,
   flush=True — see CLAUDE.md GitHub-annotation law), never silently narrows.
7. **Ship chain** — each PR: commit → push → PR with rendered sample charts in the body →
   `merge-on-green` label → live verification of the next nightly plan artifacts. Builders
   return the PR to the commissioning session for review; no self-merge on first pass.

---

## 1. What the corpus taught us (condensed; full analyst reports in refs dir)

### 1.1 The chart grammar (32-image autopsy, both analysts independently converged)

* Fixed canvas 1200×898 (4:3-ish); price pane ≥55% height; **≤2 sub-panes ever**.
* **Zero gridlines in the price pane.** The only straight lines are the ones a human drew.
* **Pure white is reserved for annotation ink** — candles lime/coral, indicators gold/cyan/
  salmon/olive, volume muted slate so it never competes. This is why the charts read at 500px.
* **Future runway**: last bar sits at 60–85% of frame width; the 15–40% dead space to the
  right holds the volume profile (drawn leftward from the right edge, never occluding candles),
  the last-price tag, and level tags.
* Volume-by-price profile on **~58% of charts** (15/26); volume pane on 100%.
* Max ONE moving average, labeled **inline in its own color** (`200 SMA`), never a legend box.
* Company logo dropped into whatever region is empty — it is the ticker at thumbnail size.
* Five annotation shapes, reused forever:
  1. **Translucent circle spotlight**, color-coded by tense: blue-grey = historical instance,
     **gold = current/"YOU ARE HERE"**, red = damage;
  2. **Zone band** (10–20px translucent rect) for S/R — never a 1px hairline;
  3. **Free-drawn arc** outlining formations (H&S, rounding bottoms) — curves read as
     interpretation, polylines read as clutter;
  4. **Trendline** — solid white structural, dotted white diagnostic/divergence;
  5. **2–6 word text callout** in the annotation's own color (`Squeezing`,
     `Highest weekly volume ever`, `4 consecutive red weeks`, `Stage 4`).
* **Measurement box** (`-1.68 (-30.317%) / 6 bars (30 minutes)`) — anchor-to-anchor arrow +
  arithmetic receipt. Top-viewed post in the corpus carries one.
* **In-frame restatement**: every number the caption claims is re-rendered inside the image
  (axis tag in the indicator's color, info table, callout) so a screenshot survives
  decontextualization.
* Timeframe ↔ claim horizon matched rigorously (monthly squeeze → MONTHLY chart; AH dump →
  5-MIN) — zero mismatches in 26 charts. **~48% of their chart posts are WEEKLY or MONTHLY.**
  Log scale + serif labels for multi-year editorial charts.
* Indicator doctrine — **"the indicator whose y-axis unit IS the claim's unit"**: a streak
  claim gets a consecutive-candles pane; a valuation claim gets a P/E pane with a dashed line
  at the claimed multiple; a compression claim gets a squeeze pane; a regime claim gets
  Weinstein stage painting; an insider-buy story turns everything else OFF. Never decoration.
* What they NEVER draw: Fibonacci, Ichimoku, Bollinger bands, ATR bands, pivots, two MAs,
  pattern names on the canvas (the wedge is drawn; the word "wedge" lives in the tweet).

### 1.2 The copy machine (396-post taxonomy)

* Chart family (technical/quip/stat-extreme/valuation) = **40.7% of output**; median caption
  **11 words / 61 chars**; 96% pure observation, 4% directional verbs (and those delegated to
  a third party or a question); **0/396 disclaimers** — compliance by construction.
* Top-decile separators: shorter (median 13 words), follow-up not origination (72.5%
  self-quotes), stance-or-superlative never scoreboard (0/34 breadth-scoreboard posts made
  top decile), interjection openers (`Wow…`, `My oh my`, `Phew`) are the strongest hook
  (41.7% top-decile within chart family).
* `valuation_obs` is the highest-reach class (medV 161k, 3.3× lift); `chart_stat_extreme`
  (superlatives/streaks) 2.1× lift; `earnings_print` and scoreboards are volume filler.
* Numbers live in the image: only 25% of chart captions carry a hard number; `%`-bearing
  captions underperform (5.3% top-decile).
* Emoji = terminal punctuation (53% within last 14 chars); tension glyphs (😬🌶️🩸) out-reach
  celebration glyphs (🔥). Three registers that never mix: stance-trailing, ledger-leading
  (🟢🔴✅), alarm-leading (🚨).
* **Self-quote machine**: 48.7% of all posts quote their own prior post. Bimodal: sub-1h
  event laddering, and **+2–4 day reawakening** (the reach sweet spot, medV 131k) when price
  reaches the level. The longer the gap, the shorter the copy (multi-week follow-up = 3 words
  + a face). "Ouch" follow-ups out-reach victory laps 107k vs 76k — honesty is also the
  reach-optimal play. Chains run to depth 7; one GOOG earnings chain = 1.81M cumulative views.
* Ticker strategy: 140 unique cashtags / 20 days; stable ~20-name hot rotation carries half
  the mentions; **~5 brand-new long-tail names injected per day**; a story name gets 2–3
  posts/day while the story is live; ~8 pure chart observations per day, weekends INCLUDED
  (weekly/monthly charts don't need a live tape — weekend chart share is their highest).

### 1.3 What we must NOT copy

* Superlatives whose evidence window is wider than the plotted axis (3/13 sampled) — §0.2.
* Follow-up ledger survivorship: they only follow up the calls that moved. Our forward ledger
  writes the row at ORIGINATION and grades on schedule (nightly is the sole advancer), or the
  mechanic manufactures a deleted-denominator track record.
* LLM-originated rankings as content (their "Sidekick picks" posts violate our A7). We adopt
  the provenance-panel FORMAT, never the practice.
* Their two hygiene artifacts: settings card overlaying candles; useless "Your local time
  zone" chrome.

---

## 2. Our gap map (recon findings, file:line in the analyst reports)

The dominant discovery: **almost everything needed already exists in-repo and is simply not
wired to the posting path.**

| Capability | Exists at | Wired to posts? |
|---|---|---|
| Weinstein stage classifier (30-wk SMA, SATA score, weekly bars) | `engine/weinstein_stage.py`, backfill parquet | NO — `radar_internal._feed_stage` emits top-15 Stage-2 nightly into `opportunities.jsonl`; content_studio never reads it |
| S/R clusters, trendline candidates, swing pivots, unfilled gaps, weekly resample | `engine/neuralweb/chart_perception.py` (same OHLCV loader as the renderer) | NO — chat tool only |
| RSI sub-pane | `chart_render.py` (fully implemented) | DEAD — every call site hardcodes `indicators=("volume","macd")` |
| AVWAP + volume profile (POC/VA) | `chart_render.build_m2_overlays` | Partially (signal lane unconditional, confluence conditional) |
| 1,315-name ADV-ranked ticker pack w/ RSI, 52w stats, streaks, next-earnings | `data/marketing/hot_tape_pack.json` (nightly) | NO — movers reads the 503-name S&P heatmap only |
| Options volume/premium/P-C per ticker (383 names) | `data/options_flow/summary_*.parquet` | NO |
| Retail attention: WSB mentions (~307 names/day), Wikipedia attention (1,221 names) | `data/quiver/wallstreetbets.parquet`, `site/factordata/attention.json` | NO (site display only) |
| Earnings calendar (1,364 names) | `data/earnings/earnings.parquet` (+ in hot-tape pack) | Partially (earnings lanes; not chart-post selection) |
| 12y split-adjusted daily OHLCV, 2,768 names | `data/baskets/ohlcv/` | Renderer clips to 90 visible daily bars; no weekly resample on render path |
| Whole-market 5y OHLCV, 20,677 names | `data/massive_stock_day/` (NOT split-adjusted) | Hot-tape opt-in only — keep it out of superlative facts |

Renderer gaps (nothing else in repo draws these): circle spotlights, zone bands, arcs,
trendlines, measurement box, second axis tag in indicator color, streak pane, squeeze pane,
EMA (any length; only SMA-50/200 exist), weekly/monthly resample, log scale, runway layout
control, per-post indicator selection. Also: the % callout box clips at the right edge
(visible on the 2026-07-26 TSLA watchlist card).

Selection gaps: `watchlist` never pulls its own ticker (demoted signals are its main supply);
cashtag tiers fence the universe to S&P500+NDX+17; closed 8-item ANGLES set has no
long-term/weekly/stage angle; the named-franchise register (`franchises.py`) is dead code.

---

## 3. Build plan — three PRs, Opus builders, sequenced

### PR-A · Renderer: the annotation grammar (`chart_render.py` + tests only)

New `render_chart_v2` kwargs (all optional, default None/off — §0.1 backward compat):

1. `bars`/`timeframe` become real: `timeframe="WEEKLY"|"MONTHLY"` resamples daily parquet
   (W-FRI / month-end, matching `weinstein_stage.py` and `chart_perception.py` conventions),
   `lookback_bars` overrides the 90-bar window (weekly default 156 = 3y, monthly 120 = 10y).
   `log_scale=True` for multi-year charts. Header prints `TICKER WEEKLY (LOG)`.
2. `spotlights=[{index, price?, tense: "past"|"now"|"damage", label?}]` — translucent circle
   discs, blue-grey/gold/red by tense, optional 2–6-word label in the disc's color.
3. `zones=[{lo, hi, start_index?, end_index?, label?}]` — translucent band rects.
4. `trendlines=[{from:(idx,price), to:(idx,price), style:"solid"|"dotted", extend?}]`.
5. `arcs=[{indices:[...], side:"under"|"over", label?}]` — smooth curve through swing points.
6. `measure_box={from_index, to_index}` — arrow + `Δ (Δ%) / N bars (elapsed)` receipt box;
   also FIX the existing top-right callout clipping (clamp inside canvas).
7. `level_tags=[{price, color}]` — second right-axis tag in the indicator's color.
8. `mas=[{kind:"sma"|"ema", length:int}]` (max 1 enforced upstream, renderer draws what it
   gets) with inline same-color label; keeps the existing 50/200 defaults working.
9. New sub-panes selectable via `indicators` tuple: `"rsi"` (already built — just reachable),
   `"streak"` (consecutive same-color candles histogram, y-unit = streak length),
   `"squeeze"` (BB(20,2) inside Keltner(20,1.5) dots + momentum histogram — computable from
   OHLCV alone). Sub-pane count hard-capped at 2.
10. Layout: `runway_frac` (default lifts from current cramped right edge to ~0.18), volume
    profile drawn INTO the runway; gridlines off in price pane (verify current state); white
    ink budget: annotation primitives render white/gold only, data layers never white.

Golden-sample fixtures: one chart per primitive + one "full TrendSpider-style" composite
(weekly, VbP, one MA, spotlights + zone + measure box). Crops in PR body.

### PR-B · Supply: universe, attention, options, stage feeds (no content_studio surgery)

1. `radar_internal.load_cashtag_tiers`: build tiers from `hot_tape_pack.json` ADV ranking
   (≥$25M ADV ⇒ tierable) union the existing S&P/NDX source — universe expands 503 → ~1,315
   without touching the tier contract. T3 stays excluded from movers, but tiering now COVERS
   the liquid market.
2. New `engine/marketing/attention_source.py` (read-only aggregator, display-tier):
   ranked candidate pools with provenance —
   `top_by_dollar_volume` (hot-tape pack `adv_rank`),
   `top_by_options_volume` (`data/options_flow/summary_*.parquet`, 383 names),
   `retail_attention` (WSB mentions × wiki-attention z, union),
   `earnings_this_week` (earnings parquet),
   `stage2_leaders` / `stage_transitions` (stage backfill parquet via the same read
   `radar_internal._feed_stage` uses).
   Every pool row carries `{ticker, rank, why, asof, source}`; stale asof (>3 sessions) drops
   the pool with a `::warning` (bare print, line-start, flush=True).
3. `movers_source.top_movers`: widen from the 503-name heatmap to the hot-tape pack universe
   (keep `min_abs`, keep tier filter semantics).
4. Config: pool caps, long-tail quota (≥3/day fresh names), per-ticker/day cap (3) — wired in
   PR-C's selector but DEFINED here in `config/marketing.yml` with one owner.

### PR-C · Integration: chart director + facts + angles + copy shapes (after A & B merge)

1. New `engine/marketing/chart_director.py` — the single spec builder every lane calls
   (kills the per-lane kwarg drift found at 9 call sites). Input: `{ticker, angle, fact}`;
   output: full `render_chart_v2` kwargs. Encodes the doctrine table:

   | Claim kind | Chart spec |
   |---|---|
   | level touch/reclaim (MA or horizontal) | that ONE MA (or level line) + spotlight per prior touch (blue-grey) + gold spotlight now + level tag in the MA's color; daily |
   | streak / superlative | streak pane (y-unit = claim unit) OR weekly chart with the record bars boxed; window ⊇ claim (§0.2) |
   | analog / "seen this before" | weekly or monthly, log if >4y; blue-grey spotlights on each prior instance + gold "now"; caption may enumerate (`✅/❔`) |
   | volume event | volume pane + boxed record bars + VbP; callout `Highest weekly volume in N years` scoped to window |
   | breakout/breakdown of structure | trendline(s) or zone band + measure box from the break bar |
   | stage read | WEEKLY, 30-wk SMA, stage-painted spotlights, `Stage 2` style callout (public Weinstein idiom is chart-label vocabulary; the COPY uses plain words: "base building", "marking up", "under distribution") |
   | post-event drift | AVWAP from event anchor (we HAVE this; TrendSpider doesn't — a legitimate edge) + measure box |
   | valuation observation | daily/weekly + zone band at the reference lows + callout; P/E pane deferred until a fundamentals series exists (§5 backlog) |

   The director enforces: ≤1 MA, ≤2 sub-panes, ≤3 annotation objects, claim-window law,
   PIT guard, VbP default-ON for chart-family posts.
2. `chart_facts.compute_facts` extensions: weekly/monthly resampled facts (weekly streaks,
   52-week+ level proximity on weekly closes, MA touch-count with lookback scoping, stage
   transition facts read from the stage parquet, options-volume/attention context facts from
   PR-B pools). Every fact carries its `window_start` so the director can enforce §0.2.
3. `content_studio` selection: `watchlist`/`chart` slots pull from `attention_source` pools
   (priority: hot story > retail attention > options volume > dollar volume > stage leaders >
   long-tail quota) instead of leaving `ticker=""`; ANGLES gains `long_term_structure` and
   `stage_read`; angle-to-kind preferences updated (`watchlist` → level_watch, stage_read,
   long_term_structure; `chart` → level_watch, precedent, long_term_structure).
   Weekend slots prefer weekly/monthly long-term angles (their weekend is chart-observation
   heavy and needs no live tape).
4. Copy: the LLM writer's chart-family shape guidance gains the corpus-derived budgets
   (7–12 words, terminal stance glyph from an allowed set, interjection-opener shape,
   enumerate-and-circle shape, superlative shape, question-delegation shape; numbers stay in
   the image). Existing voice law ("fact + a reaction that costs you") is unchanged — these
   are SHAPES under it, not a new voice. Banned-vocab law untouched.
5. Follow-up candidates (SPEC ONLY in this PR — coordinate with the cadence session before
   wiring a posting lane): nightly emit `followup_candidates.jsonl`
   `{parent_asset_id, ticker, trigger: level_reached|streak_extended|thesis_hurt, age_days}`
   for parents 2–4 days old whose drawn level got touched. The forward ledger row is written
   at ORIGINATION (every chart post with a drawn level gets a row), so the follow-up pool has
   an honest denominator. "Ouch" follow-ups are first-class (they out-reach victory laps).

### Test/CI notes for all three
`pytest` packs as usual; annotation-law asserts use `capsys` + `line.startswith("::")`;
no logger-prefixed `::warning` (five-strike law). Template/site pairing not touched (no
`templates/` files in scope). Suite additions must run in the packs, not only locally
(dead-suite trap).

---

## 4. What we already beat them at (don't regress)

* AVWAP + POC overlays with reserved-lane labels — they never draw AVWAP; it is our edge for
  post-event stories. Keep.
* Facts→numbers whitelist coupling (copy can only say what the fact layer computed) — their
  three major-slip charts show why this matters. Keep absolute.
* Bilingual surfaces, logo whitening pipeline, Sentinel/garbage gates, no-fallback LLM copy.
* Our compliance posture already matches their best structural trick (observation, not
  advice) — and ours is enforced, theirs is habit.

## 5. Backlog (explicitly OUT of this pass)

* P/E ratio sub-pane + revenue step-overlay (needs a fundamentals time series we don't
  collect; `valuation_obs` was their highest-reach class → separate adjudication for a
  fundamentals collector).
* Put/Call donut widget (data exists for 383 names in `options_flow`; widget is cheap but
  low-priority vs the grammar).
* Insider-trades on-chart markers (congress/insider feeds exist; marker semantics need the
  filing-lane attribution law review).
* Posting cadence/volume — ANOTHER SESSION owns it. This program widens supply, angles and
  chart quality; it does not change publisher scheduling.
* Live quote-tweet follow-up lane — spec'd in PR-C §5, wiring blocked on cadence-session
  coordination.

## 6. Reference material

* `mockups/refs/trendspider-hardening/` — 8 committed exemplar images + NOTES.md mapping each
  to the techniques above (spawn-handoff law: references are committed files, not prose).
* Full analyst reports (copy taxonomy, 2× chart autopsy, pipeline/render/universe recon)
  archived in the same directory as `ANALYSIS_*.md`.
* Corpus JSONL retained in session scratchpad only (competitor content; do not commit
  wholesale — committed refs are the curated minimum for build guidance).
