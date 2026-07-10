# Intraday Flow Tracker — design ruling (spec of record)

Status: DESIGN RULING (Fable, 2026-07-10). Display-tier build — ships freely per house
epistemics (gauntlet = promotion gate, not build gate). Trigger: operator ask — "intraday
flow tracker that assesses the durability and velocity of funds and volume flowing into
tickers, integrated with options flow, to find washed-out-bottom → momentum-continuation
leaders (Mag 7 / AI leaders / cyclical large caps) for tight-stop continuation entries."

Grounded in a 7-lane infrastructure census (2026-07-10) + the prior flow adjudications:
`research/momoedge/FLOW_INTELLIGENCE_V2_SPEC.md`, `research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md`
(P3.2/P3.3 lineage), `research/momoedge/flow_spec.md`.

## 1. What exists (census findings this build stands on)

- **Intraday options tape is LIVE**: `live_flow_poller` (120 s cadence, 09:25–16:05 ET,
  launchd) → R2 `live_flow/{tide_current,dte_tide_current,feed_current,enrich_current}.json`
  + per-root `live_flow/tickers/{ROOT}.json` (per-minute cumulative NCP/NPP, strikes,
  sweeps). `engine/flow_enrich.py` (5-min cadence) adds deterministic badges
  (WHALE/FRESH/Z_OUTLIER/SIZE_VS_OI/REPEAT_HITTER/LADDER/MULTI_LEG) + percentile session
  tiers. The full 116-name leaders universe (mag7 + AI + cyclical baskets) is inside the
  poller universe.
- **Intraday price bars**: `data/intraday/<T>.parquet` hourly OHLCV (Polygon STANDARD,
  15-min delayed), refreshed hourly by `intraday.yml` via the shared `intraday-` actions
  cache.
- **Live quotes**: `live-quotes.yml` every 5 min → `quotes.json` on the `live-data` branch
  (~1,900+ symbols, price only today).
- **30-min fastpath**: `intraday-fastpath.yml` commits `site/live/*.json` (overlay,
  basket_pulse, risk_state) to main.
- **Browser → R2**: `site/data_base.js` fetch shim already routes to the public R2 bucket
  (`storage.public_base` in config.yml) — CORS proven in production.
- **EOD context (nightly, per ticker)**: `stockdata/<T>.json` (`mtf_upturn`, `entry_signal`
  with buy_zone/stop/atr_pct, `vol_squeeze`, personality incl. `stair_step_leader` /
  `failed_breakout_trap`, `current_mode`), `data/options_entry/state.parquet`
  (gamma_regime, dist_to_flip_pct, walls), `engine/bollinger_event_signals.bb_lower_reclaim`
  (washout event), `data/live_flow_baselines/baselines.json` (252d premium mean/std).
- **Named gaps this build fills** (census-confirmed absent): intraday RVOL vs
  time-of-day baseline; VWAP-relative position; per-ticker flow VELOCITY (slope of
  cumulative NCP) and DURABILITY (persistence of positive windows); a washout→continuation
  leaders board joining price flow with options flow.

## 2. Product

New page **`site/intraday_flow.html`** ("Intraday Flow Tracker" / 盘中资金流追踪) — a
leaders board over the configured universe with, per name:

1. **Live tape block** (5-min freshness, client-computed from quotes.json):
   last, %chg, day-range position, **RVOL_tod** = cumulative day volume ÷
   (ADV20_shares × expected-volume-share-at-time-of-day), volume pace arrow.
2. **Durability block** (30-min fastpath, `site/live/flow_pulse.json`): session VWAP
   (hourly-bar approximation, labeled), spot-vs-VWAP %, **volume durability** = share of
   today's hourly bars closing in their upper half with volume ≥ time-of-day baseline,
   higher-lows count, cum-vol asof stamp.
3. **Options-flow block** (2–5-min freshness, client-fetched from R2 `live_flow/*`):
   cumulative ~net call prem (NCP) / ~net put prem, **flow velocity** = slope of
   cumulative NCP over trailing 15/30-min windows vs session mean pace (kinetics
   primitive ported from `engine/flow_velocity.py`), **flow durability** = share of last
   N 5-min windows with NCP > 0 + longest positive streak, today's badge counts + best
   session tier from `enrich_current.json`. All direction reads ~-soft (RUL-F3.12).
4. **Setup context block** (nightly `site/flowtracker/base.json`): washout recency
   (bb_lower_reclaim days-ago; 21d max drawdown + % recovered), `mtf_upturn` state/K,
   `vol_squeeze` state, personality chips — `stair_step_leader` (clean leader) vs
   `failed_breakout_trap` (**trap-prone flag** — the operator's "scam stock that does a
   lot of bottom testing" screen), `current_mode`; gamma_regime + dist-to-flip + walls
   as dealer context.
5. **Confluence chips — K-of-N booleans, NO weighted composite** (mtf_upturn precedent;
   composite-law compliant). Legs, each independently inspectable:
   L1 washout_recent (bb_lower_reclaim ≤ 10 sessions OR 21d drawdown ≤ −12% with recovery
   begun) · L2 reclaim (px > VWAP AND px > prevClose) · L3 rvol_elevated (RVOL_tod ≥ 1.30,
   the `engine/impulse.py` rvol_confirm threshold) · L4 vol_durable (volume durability ≥
   0.60) · L5 flow_bid (cum NCP > 0 AND flow durability ≥ 0.60) [~-soft] ·
   L6 upturn_organ (mtf_upturn ≥ UPTURN_WATCH) · L7 leader_quality (NOT
   failed_breakout_trap). Display K/7 + chips. `dt_contra` is EXCLUDED from legs (DT-R11b).
6. **Risk ladder** (reference levels, never advice): nightly `entry_signal.stop`,
   session VWAP, session low; ATR% shown. Copy: "reference levels".
7. **Playbook accordion** (EN/ZH, on-page field guide — understanding-before-backtest
   law): the continuation play — leaders-only universe; wait for washout context + reclaim
   + elevated durable volume + flow confirmation; stop below structure (risk ladder);
   trap-prone names de-prioritized; let runners run. Deterministic language; no outcome
   claims; the word "validated" never appears; no vendor/competitor names.

Default sort: **RVOL_tod desc** (a single measured quantity — flow_desk top-movers
precedent). K and any column are user-sortable client-side. The board annotates; it feeds
no buy-strip, no alert queue, no authority surface (CONST-ART2).

## 3. Architecture (three cadences, all reusing existing lanes)

- **Nightly** (`scripts/build_intraday_flow.py --mode nightly`, daily.yml render band,
  cheap — reads existing parquets/JSONs only):
  emits `site/flowtracker/base.json` (per-leader: ADV20, hourly volume-share curve from
  trailing 20 sessions of `data/intraday/`, ATR14, prevClose, washout context, mtf_upturn,
  vol_squeeze, personality, entry_signal, options_entry context, premium baselines) and
  renders `site/intraday_flow.html` from `templates/intraday_flow.html.j2`.
  Also the sole advancer of the forward ledger (§5).
- **30-min fastpath** (`--mode fastpath`, new step in `intraday-fastpath.yml` with a
  read-only `intraday-` cache restore): emits `site/live/flow_pulse.json` (+
  `flow_pulse_lastgood.json` sidecar, basket_pulse mode/staleness pattern). site/live +
  R2 only — **zero `data/` writes intraday** (HOUSE-U5).
- **5-min**: `build_live_quotes.py` extended with per-symbol `vol`, `dayHigh`, `dayLow`
  (same Yahoo batch call, zero extra requests). Budget law: quotes.json must stay under
  the 500 KB browser budget — measure in a test; if over, carry the new fields for the
  leaders + CORE set only.
- **2-min**: browser fetches R2 `live_flow/*` directly (existing public bucket + shim
  precedent). Graceful absent-file fallback: options block renders "off-hours / feed
  stale" from `meta.json` asof.

Universe: config block `intraday_flow:` in config.yml — `universe_baskets` default
[mag7, ai_infra, ai_software, ai_semiconductors, semicap_equipment, reshoring, defense,
power_grid] resolved via `data/baskets/membership.json` ∩ `engine.options_universe.gex_symbols()`;
thresholds (rvol_confirm 1.30, durability_min 0.60, washout_lookback 10); `enabled` flag
(kill-switch: removes nav entry + page banner — roadmap P3.6 pattern).

## 4. Engine

`engine/intraday_flow.py` — pure functions + tests, no I/O:
`vol_share_curve()`, `rvol_tod()`, `session_vwap()`, `volume_durability()`,
`higher_lows()`, `ncp_velocity()` (slope_z kinetics ported from flow_velocity),
`flow_durability()`, `confluence_legs()` → dataclass with the 7 booleans + K.
The builder script is thin I/O only (flow_velocity.py precedent).

## 5. Forward ledger (nightly-only)

`data/intraday_flow/ledger.parquet`: one row per session × leader — EOD leg booleans, K,
RVOL_tod at close, cum NCP, flow durability, price. Forward returns (t+1/t+5/t+10/t+21)
stamped by subsequent nightlies. A9 single-writer; registered in `config/synapse.yml` +
run_status data-health breaker (P0.7 law). Display-tier until a future pre-registered
promotion gauntlet; a null retains the legs as confluence inputs (house law).

## 6. Compliance checklist (binding)

- HOUSE-U5: intraday writes → site/live/ + R2 only; nightly is sole data/ advancer.
- CONST-ART1: every metric/leg is a deterministic rule; zero LLM involvement.
- CONST-ART2: annotates only; never reorders any authority surface.
- RUL-F3.12: ~-soft direction labels + signing-honesty footnote until the tape
  calibration gate flips (production_ready currently false).
- Composite-law / Signal Commons R3: K-of-N boolean count only; no hand-weighted score;
  no positioning fusion. The MomoEdge radar rank formula is NOT reused (weighted).
- DT-R11b: DannyTrades composite excluded from legs and from any sort.
- Kills respected: DOI family dead as signal (net_doi = display context only, not a leg);
  no skew-decel; no charm narratives; sector-level "washout × turn" stays dead — this is
  per-stock display context, a different construction, no sector washout signal emitted.
- 0DTE: bucket-labeled only, never highlighted. Debrand law. TOP3-O2: no "money routing"
  framing — copy says "tape activity & options-flow persistence".
- CI guards: check_validated_claims, check_title_i18n (no translated title=), nav checks
  (check_nav_gap/check_nav_mega), EN/ZH bilingual pairs throughout.
- UI quality law: prod-shaped fixtures + real browser screenshot verification before PR
  (Playwright direct); curl-status theater is not verification.

## 7. Sequencing

- **PR-A** (this build): engine + tests, nightly/fastpath builder, quotes vol fields,
  template + nav + page JS, ledger + registrations, this doc. Same-day squash-merge.
- **PR-B** (follow-up, after A merges): Terminal (stock.html) "Intraday flow" panel
  reading flow_pulse.json + R2 per-root drill for the open ticker + deep link to the
  tracker (plain-copy byte-sync law applies to stock.html edits).
- Come-back clocks: first live-session read 2026-07-13 (next RTH after merge);
  ledger depth review 2026-08-10; promotion prereg decision no earlier than 2026-10
  (post options accrual gate GAP-U4).
