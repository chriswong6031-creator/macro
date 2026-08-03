Based on this exploration, here is the structured map of the "On Our Radar" franchise and sibling ticker-chart lanes.

## 1. FRANCHISES

**Content-type catalogue** (the actual kinds the pipeline ships) is defined in `engine/marketing/content_studio.py:48-103` (`CONTENT_TYPES`), with default weight tilt at `content_studio.py:131-141` (`_DEFAULT_TILT`). Relevant to ticker-chart posts:
- `watchlist` = "On Our Radar" — `content_studio.py:80-84`, tilt weight 0.06 (`content_studio.py:137`)
- `chart` = "Chart of the Day" — `content_studio.py:56-60`, tilt weight 0.23 (raised from 0.13 after `education` was zeroed, `content_studio.py:107-130`)
- `signal` = "Signal Alert" — `content_studio.py:49-54`, tilt weight 0.30 (largest)
- `mover` = "Mover of the Day" — `content_studio.py:91-96`, tilt 0.10
- `theme_list` = "Theme Tape" — `content_studio.py:97-102`, tilt 0.06
- `receipt`, `macro`, `event`, `education` (education forced to 0.00 — operator ruling documented at `content_studio.py:111-130`)

Separately, `engine/marketing/franchises.py` defines a **named-format register** (`_RAW_REGISTER`, `franchises.py:253-701`) — per-account formats like "Risk Radar Note" (kelly, kind=`watchlist`, weekly, max 2/wk, `franchises.py:560-575`), "Risk Radar" (flagship, kind=`watchlist`, weekly, max 1/wk, `franchises.py:661-676`), "Chart Detective" (kelly, kind=`chart`, `franchises.py:507-522`), "One Chart, Two Stories" (sophia, `franchises.py:458-473`), "Institutional Research in One Chart" (flagship, `franchises.py:645-660`), plus daily signal-kind formats ("Confirmation Check", "What Changed Since Yesterday", "Signal of the Day"). Each franchise declares `kind`, `cadence` (`daily`/`weekly`/`sessional`), `windows` (local time), `max_per_day`/`max_per_week`, and a `contract` (required content beats) — schema at `franchises.py:146-190`.

**Critical finding — the franchise register is not wired into production.** `content_studio.py` never imports `engine.marketing.franchises`. The only production consumer of `franchises.py` is `engine/marketing/desk_feed.py` (`desk_feed.py:296,375,537,699`), which is itself an *assembly/ranking* layer, self-documented as "THIS IS ASSEMBLY, NOT A NEW POSTING RAIL... nothing here posts, nothing here generates copy" (`desk_feed.py:1-19`). Nothing in the nightly governor (`engine/neuralweb/marketing_governor.py`) or the publisher imports `desk_feed.assemble` or `franchises.open_slots` — confirmed by repo-wide grep with zero non-test hits. So the entire named-franchise/contract/window/cadence-cap system (including both `watchlist`-kind franchises) is dead relative to what actually posts. The real "On Our Radar" volume is produced by the generic `watchlist` content-type mixer in `content_studio.py` plus two splice-in lanes (see §2).

## 2. TICKER SELECTION

The **real** ticker-chart pipeline, contradicting the franchise register above:

**a) Base tilt allocation (`plan_account`, `content_studio.py:2070-2205`).** Only `type_id in ("signal", "chart", "receipt")` pull a ticker from `plan_pool` (Prophet plans, filtered to `postable_signals`, bull-preferred) at `content_studio.py:2171-2183`. **`watchlist` is NOT in that list** — a directly-tilted watchlist slot starts with `ticker=""`. Later (`content_studio.py:4607-4618`), a ticker-less `watchlist` item is attached generic breadth/sector `market_facts` rather than a per-name fact — i.e., the organic 6% tilt allocation produces market-commentary posts, not name-specific ones.

**b) Signal→watchlist demotion (the dominant source of ticker-bearing watchlist posts).** The live-price gate (`copywriter.verify_signal_live`) demotes `signal` items whose entry fails the gate; `config/marketing.yml:1719-1733` restricts demotion to `demotable_gate_reasons: [runaway, underwater]` (stale/unverified signals are dropped, not repurposed) — measured 168/335 watchlist posts on one plan were demoted signals (`content_studio.py:4461,4471,4493-4515`). So watchlist ticker supply mostly inherits signal's own pool: Prophet plans (`site/prophet/index.json`).

**c) House-picks splice (`house_picks.py`, wired at `content_studio.py:4154-4193`).** Reads three site artifacts read-only: `site/factordata/impulse.json` (momentum states EARLY_IGNITION/IGNITING/COILING, `min_impulse_score=80`, cap 3 — `house_picks.py:107-118,222-264`), `site/factordata/tech_screener.json` (`active_buy/active_total ≥ 0.6`, cap 2 — `house_picks.py:267-307`), `site/allocationdata/special_situations.json` (Acquisitions/Divestitures/Capital Returns/Spinoffs/Restructuring/Delistings, ≤3 days old, US-only, cap 2 — `house_picks.py:120-136,310-361`). Round-robin interleaved, deduped, capped at these per-desk limits (config echoes at `config/marketing.yml:1832-1839`), then filtered against `exclude` (tickers already claimed tonight) and `cooled` tickers. A house pick with no renderable chart is dropped outright (`content_studio.py:4162-4172`).

**d) Mover/theme lanes** (siblings, not `watchlist` kind): `movers_source.top_movers` (`movers_source.py:312-365`) reads `site/marketdata/sp500_heatmap.json` — S&P 500 tiles only, `min_abs=3.0%`, capped `n=8`/side, and content_studio only takes the top 2 by `|pct|` per night (`content_studio.py:3478-3486`). `theme_lists` (`movers_source.py:392-`) aggregates by sector/theme, `min_members=4`, `min_abs_theme=1.0`.

**Diversity limits identified:**
- **Fixed universe**: the cashtag-tier universe is built solely from `data/universe/membership.parquet` (`group=="sp500"`) plus `data/finviz_screener/idx_ndx.json` plus a config `t1_always` allow-list (`radar_internal.py:707-754`, defaults at `config/marketing.yml:66`: 17 mega-caps). Anything outside S&P 500 + Nasdaq-100 + the always-list is never even tiered, and `movers_source.top_movers`'s `tier_map` exclusion drops `T3` names from the mover pool (`content_studio.py:3456-3464`, `movers_source.py:359-360`).
- **Min-signal gates**: `min_impulse_score=80`, `active_buy/active_total≥0.6` for tech-lab, `min_abs=3.0%` for movers.
- **Dedup/cooldown windows**: `ticker_cooldown_days=3` (watchlist/chart/receipt) and `signal_cooldown_days=5` (`content_studio.py:534-546`, config echo `config/marketing.yml:1735,1738`), enforced in **trading days** via `trading_days_since` (`content_studio.py:607-634`) and applied via `cooled_tickers`/`cooldown_days_for` (`content_studio.py:701-737`). Cross-account caps: `max_accounts_per_ticker_day=2`, `max_signal_accounts_per_day=1` (`content_studio.py:536-537`, config `config/marketing.yml:1742,1744`).
- House picks/congress/insider are explicitly *extra supply*, never displacing a name a producer already claimed (`_claimed` set, `content_studio.py:4087-4093,4150,4191`).

## 3. POST TYPES / ANGLES

Angle vocabulary is a closed set: `ANGLES = ("level_watch", "risk_frame", "group_read", "precedent", "process", "receipt_frame", "macro_read", "event_read")` — `content_studio.py:503-506`. Per-kind preference order at `content_studio.py:510-527`: `watchlist` → `("level_watch", "risk_frame")`; `chart` → `("level_watch", "precedent")`; `mover` → `("group_read", "level_watch")`; `theme_list` → `("group_read", "macro_read")`. The Nth account keeping a ticker on a given day takes the Nth angle so two desks on one fact never collide (`content_studio.py:508-509`).

**No long-term / weekly-timeframe / stage-analysis angle exists in this vocabulary.** Everything is short-horizon (level/risk/group/precedent framed off daily bars). See §6 for the disconnected stage-analysis engine.

## 4. COPY GENERATION

Primary path is **LLM-first**, with a hard **no-fallback law** for planned kinds: `copywriter.write_posts_llm_v2` (`copywriter.py:6346-6452`) — provider waterfall `codex → oauth(Claude) → anthropic → deepseek` (`copywriter.py:6405-6428`), and "there is no template fallback: masterplan §0 gate 1 says a planned post whose model copy fails is DROPPED and counted, never replaced" (`copywriter.py:6362-6367`). If armed but no credential, every planned post is dropped, not templated (`copywriter.py:6434-6452`). A separate deterministic-template writer (`write_posts_deterministic`, `copywriter.py:4918`) exists as a v1/legacy fallback and is also embedded directly in `content_studio.py`'s `_COPY_TEMPLATES` (per `(type_id, voice)` pair, `content_studio.py:145-330`), but is explicitly the inferior path the LLM lane supersedes.

**Voice/law constraints:**
- `validate_copy` / `validate_copy_v2` enforce `copy_laws` from `config/marketing.yml` (`copywriter.py:1212,3008`), `_MAX_CHARS = 275` (`copywriter.py:65`).
- Banned vocabulary: `_BANNED_VOCAB` (indicator acronyms `macd, rsi, stochastic, ichimoku, bollinger, vwap, avwap, poc`, plus `validated, guaranteed, can't lose, buy now` — `copywriter.py:66-72`) and `_BANNED_SUBSTRINGS` (`point of control`, `value area`, `volume profile`, `signal stack`, etc. — `copywriter.py:74-88`).
- Public copy carries no technical-indicator vocabulary (module contract, `content_studio.py:27`); internal marker sources like `macd_cross` are computed but "name never surfaced" (`content_studio.py:2916`).
- `_NUMBER_RE`-style whitelist gating: numbers must trace to the facts packet (referenced at `movers_source.py:78-80`).
- Expression-dial quirk/emoji/vocab caps layered on top (`_DIAL_VIOLATION_MARKERS`, `copywriter.py:41-49`).
- House-picks copy carries mandatory desk attribution + the source artifact's own disclosure verbatim (`house_picks.py:21-39,368-415`) — never an unattributed screen output.

## 5. CHART ATTACHMENT

`content_studio.py`'s featured-chart loop (`content_studio.py:2774-2930+`) decides chart spec for every `signal`/`chart`/`watchlist`/`receipt` item with a ticker in a D1 slot (`_CHARTABLE_TYPES`, `content_studio.py:2798`), matching `_CHART_BEARING_KINDS` used by the publisher/approval desk (`approval_desk.py:670-672`, pinned by `tests/test_marketing_forward_booking.py:351` as `{signal, chart, watchlist, receipt}`).

- **Variant split**: `variant = "signal"` (carries entry marker/highlight/% callout) only for un-demoted, live-verified `signal` posts; everything else renders `variant = "tape"` (no marker, no claim) — `content_studio.py:2865-2895`. The live-gate here downgrades the *variant*, it never vetoes the chart itself.
- **Marker placement**: prefers the real Prophet `_signal_date`; falls back to an internal `macd_cross` "momentum turn" (name never surfaced in copy) or `latest` — `content_studio.py:2904-2926`.
- **Render call**: `chart_render.render_chart_v2` (candlestick, via `load_ohlcv_windowed`), with M2 overlays (`avwap_overlay`/`poc_overlay`) on by default since 2026-07-30 (`content_studio.py:2932-2966`).
- **House-pick/filing charts** use a distinct `_filing_chart` helper (`content_studio.py:4031-4085`) — deliberately a **TAPE-only** card: no marker, no SETUP pill, no v1-BUY fallback (to avoid fabricating a recommendation attached to a named politician/executive).
- **Theme-list cards** use a different renderer entirely — `chart_render.render_watchlist_card` (a multi-row ticker/pct table, portrait 1080×1350), built from theme members, not a price chart (`content_studio.py:3676-3730`). Note: an inline comment elsewhere (`content_studio.py:3416`) claims "theme_list items get no chart" — that comment is stale relative to this later code path.
- **Mover items** reuse the same v2 candlestick path as signal charts (comment at `content_studio.py:3415`, render block follows at `content_studio.py:3740+`).

## 6. STAGE-ANALYSIS (WEINSTEIN) — EXISTS BUT DISCONNECTED FROM POSTING

A full Weinstein 4-stage classifier exists at `engine/weinstein_stage.py:1-20` — "Stan Weinstein's stage analysis on completed W-FRI weekly bars," Stage 2 defined as `close > 30-week SMA, SMA rising` (`weinstein_stage.py:5`), plus a v2 SATA composite score and ATR extension (`weinstein_stage.py:33-49`). Supporting modules: `engine/stage_analysis.py`, `engine/stage_industry.py`, `engine/stage_flows.py`, `engine/prophet_stage_shadow.py`, backed by `data/stage_analysis/backfill/equitydesk_overview.parquet`.

Inside `engine/marketing/`, `radar_internal._feed_stage` (`radar_internal.py:248-272`) reads that same parquet, filters `region=="USA" & stage_flag==2`, sorts by `sata_score` descending, returns top 15 with `why = "stage {stage_detailed}, SATA {sata_score}, {weeks}w in stage"`. It's one of five feeds in `scan_signal_surplus` (`radar_internal.py:384-470`, `_SURPLUS_FEED_ORDER = [prophet, confluence, earnings, movers, stage]`) and feeds `emit_opportunities`/`sync_opportunities` into `data/marketing/opportunities.jsonl` (`radar_internal.py:502-604`), which is only ever surfaced via `marketing_governor.py:382-389` into a diagnostic `data/marketing/radar_report.json` and read back by `state.py:236` for ops state.

**This never reaches an actual post.** `content_studio.py` never imports `scan_signal_surplus`, `emit_opportunities`, or reads `opportunities.jsonl`/`radar_report.json` — its only `radar_internal` touchpoint is `load_cashtag_tiers` for T1/T2/T3 filtering of movers (`content_studio.py:3459-3464`). So today, a name sitting in a clean Weinstein Stage 2 (the textbook long-term/weekly "On Our Radar" case) is discovered nightly by the radar but has no path into `watchlist`/`chart` copy, no angle in `ANGLES`, and no franchise contract that names it (the two `watchlist`-kind franchises in the register are themselves unwired per §1).
