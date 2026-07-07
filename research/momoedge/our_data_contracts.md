# Options Data Layer — Integration Map for MomoEdge Build

_Generated 2026-07-06. Repo root: `/Users/chriswong/Documents/Cluade/Macro Dashboard`._

---

## 1. Artifact Inventory

### 1A. `site/flow/<SYM>.json` — EOD Per-Name Flow Desk
**Producer:** `scripts/build_options_flow.py` → `engine/options_flow.py`
**Cadence:** daily (MASSIVE_S3 minute aggregates path; gated on S3 creds)
**Location:** `site/flow/AAPL.json`, `site/flow/SPY.json`, etc. — ~200+ names
**Schema (top-level keys):**
```
underlying, available, asof, spot, volume, premium_mn, net_premium_mn,
call_vol, put_vol, pc_ratio, net_call_vol, net_put_vol, signed_pc,
zerodte_share, intraday{open_share,mid_share,close_share},
large_prints[{k,cp,exp,vol,prem_mn,dir}],
dealer{gamma_flow_bn, gamma_flow_dir, delta_flow_mn, assumed_gex_bn,
       divergence[{k,cp,flow,prem_mn}], coverage{contracts,oi}},
new_positions{fresh_contracts, fresh_premium_mn, top[...]},
positioning{available, reliable, asof, prior_asof, days_back, n_matched,
            net_doi, call_doi, put_doi, call_oi_chg_pct, put_oi_chg_pct,
            doi_pc, net_delta_doi_mn, opening, tone, lean_en, lean_zh,
            top_build[...], top_unwind[...]},
signing{method, direction_reliable, magnitude_reliable,
        per_trade_agreement, net_sign_recovery, note},
reliability{net_premium_mn{gated_out,...}, signed_pc{gated_out,...}, ...},
verdict{tone, en, zh, direction_reliable, positioning_reliable}
```
**Reliability contract (CRITICAL):**
- `positioning` (ΔOI) — **RELIABLE** (no trade-signing needed); `reliable: true` in payload.
- `dealer.gamma_flow_bn`, `net_premium_mn`, `signed_pc` — **SOFT direction** (tick-rule net-sign recovery = 0.41); magnitude only. `direction_reliable: false` in `signing` block.
- `premium_mn`, `volume`, `pc_ratio`, `zerodte_share`, `fresh_contracts` — **RELIABLE magnitude** (signing-free).

**Companion files:**
- `site/flow/index.json` — manifest row per name (asof, spot, net_premium_mn, signed_pc, zerodte_share, gamma_flow_bn, delta_flow_mn, fresh_contracts, net_doi, doi_pc, positioning_lean, tone, verdict)
- `site/flow/mastermind.json` — compact context block (`schema: options_flow.context.v1`)

---

### 1B. `site/gex/<SYM>.json` — GEX Board (Cboe Delayed, EOD)
**Producer:** `scripts/build_gex_board.py` → `engine/gex_engine.py` + `engine/gex_model.py`
**Cadence:** daily (Cboe CDN free-delayed chain, ~313 names: 35 core + all basket members)
**Location:** `site/gex/AAPL.json`, `site/gex/SPX.json`, etc.
**Schema (top-level keys):**
```
meta{key,en,zh,grp,src,asof},
summary{
  spot, regime(long|short), tier(full|thin_chain|no_options),
  net_gex_bn, net_vex, net_cex, net_delta_bn,
  gamma_flip, dist_to_flip_pct,
  magnet_up, magnet_down, charm_anchor, charm_net_sign,
  iv30, put_call_oi_ratio, max_pain, n_strikes, top_oi_share,
  call_wall, put_wall, call_wall_band, put_wall_band,
  call_wall_strength, put_wall_strength,
  skew{tone,...}, iv_rank{band,...},
  regime_passport{basis,structurally_constant,is_index_product,verdict,note}
},
expected_move{daily_pct,...},
vol_hole{state,bias,...},
tilt{read,...},
profile[...],  walls[...],  surface[...],  smile[...],  term[...],  history[...]
```
**Reliability contract:**
- `regime` (long/short gamma) — **ASSUMPTION-SIGNED** (long-call/short-put sign unobservable). For indices (SPX/SPY/QQQ/NDX/IWM/RUT): "robust assumption". For single names: `structurally_constant:true` = near-constant product attribute, NOT a time-varying signal.
- `net_gex_bn`, `gamma_flip`, `call_wall`, `put_wall` — **LEVELS MAP only** (display-only by doctrine; GEX→forward-vol validation gate pending, ~Sept 2026).
- `iv30`, `put_call_oi_ratio`, `max_pain` — signing-free, reliable as measured values.

**Companion file:**
- `site/gex/index.json` — lightweight manifest per symbol (regime, net_gex_bn, gamma_flip, iv30, call_wall, put_wall, max_pain, daily_move_pct, skew_tone, iv_rank_band, etc.)

**Archive:**
- `data/gex/latest.json` — index/ETF-only snapshot (SPX/NDX/RUT/SPY/QQQ/IWM/DIA) + CBOE SKEW + index/equity put-call ratio, written by `_write_archive_snapshot()` after each board build.

---

### 1C. R2 `live_flow/` — Intraday Live Poller (ThetaData, RTH 09:25–16:05 ET)
**Producer:** `scripts/live_flow_poller.py` → `engine/live_flow.py`
**Cadence:** every ~120s during RTH (launchd on Mac Studio)
**R2 keys (prefix `live_flow/`):**
```
feed_current.json    schema: live_flow.feed/v1
                     {asof, session_date, session_pct, baseline_note,
                      events[{...}], unusual_names[{root, prem_z, gross_premium_today,
                              group, group_zh, call_prem_share,...}]}

heat_current.json    schema: live_flow.heat/v1
                     {asof, session_date, groups[...aggregated heat rows...]}

meta.json            schema: live_flow.meta/v1
                     {asof, cadence_sec_target, cadence_sec_measured, universe_n,
                      roots_polled, requests_last_cycle, cycle_sec, delta_mode, notes}

tide_current.json    — market tide (NCP/NPP/gross/vol cumulative minutes + sectors)
dte_tide_current.json — DTE-bucket tide (5 buckets: 0DTE, 1-3d, 4-7d, 8-21d, >21d)
tickers/{ROOT}.json  — per-root drill (top ~40 by day gross premium;
                       {minutes[...], strikes[...], expiries[...], top_contracts[...]})
archive/{YYYYMMDDTHH}.json — hourly snapshot of feed (48h retention)
```
**Universe:** ~22 ETF anchors (SPY/QQQ/IWM/GLD/SLV/TLT/HYG/XLF/XLE/XLU/XLK/XLV/XLI/XLB/XLY/XLP/XLRE/KRE/SMH/XBI/ARKK/DIA) + up to 100 single-name GEX symbols from `engine/options_universe.gex_symbols()`.
**Data source:** ThetaData Terminal → `collectors/thetadata.bulk_trade_quote()`.
**Reliability:** intraday event detection (sweep clusters, unusual activity by z-score vs 252d EOD baselines). Flow direction same caveats as flow desk above.

---

### 1D. R2 `options_hub/` — Nightly Options Hub Analytics (ThetaData EOD)
**Producer:** `scripts/build_options_hub_nightly.py` → `engine/options_hub.py`
**Cadence:** nightly (after ThetaData EOD store updates)
**R2 keys (prefix `options_hub/`):**
```
vol/{ROOT}.json       schema: options_hub.vol/v1
                      {iv30, iv_rank, skew, term_slope, rv20, vol_regime,...}

gex/{ROOT}.json       schema: options_hub.gex/v1
                      {by_strike[...], net_gex, gamma_flip, walls,..., history (polygon)}
                      GUARD: R2 upload suppressed if by_strike empty but store has OI

oi_movers.json        schema: options_hub.oi_movers/v1
                      {asof, movers[{root, strike, expiry, right, d_oi, oi, ...} × top-100]}

hot_contracts.json    schema: options_hub.hot/v1
                      {asof, hot[...]} — notable EOD contracts by ΔOI × premium

context.json          schema: options_hub.context/v1
                      {asof, index_gex{SPX/NDX/RUT/SPY/QQQ/IWM/DIA...},
                       fear_greed{...}, sector_etf_flows{...}}

oi_confirmed.json     schema: options_hub.oi_confirmed/v1
                      {asof, confirmed[...]} — prior session notable ∩ today's live feed

tickers_ctx/{ROOT}.json  schema: options_hub.tickers_ctx/v1
                         {asof, tape_flow context for individual ticker drill}
```
**OI timing law:** all GEX and ΔOI uses OI[t-1] (OPRA reports EOD of t-1 as the "today" parquet). Same-day OI is NEVER used in any computation.
**Store path:** `data/thetadata_eod/` (symlinked from `/Users/chriswong/theta-ops-wt/data/thetadata_eod` on Mac Studio ops worktree). Subdirs: `eod/`, `greeks/`, `oi/` — per-root parquets.
**Polygon GEX history:** `data/polygon_gex/summary_{ROOT}.parquet` — accrued daily by `build_polygon_gex.py`; attached to `options_hub/gex/{ROOT}.json` as `history` list.

---

### 1E. Signal Bus Artifacts (options-alpha tier)
From `docs/SIGNAL_BUS.md` (config/synapse.yml):
- `vol-regime-gate` → `data/vol_regime/gate.json` — scored, 3 consumers
- `vol-regime-basket-overlay-gate` → `data/vol_regime/basket_overlay_gate.json` — scored, 2 consumers

These are currently `scored=false` (gated on validation completing ~Sept–Dec 2026).

---

### 1F. GEX Archive (for signal_archive / entry intelligence)
- `data/gex/latest.json` — index/ETF GEX snapshot + CBOE SKEW/put-call; written by `build_gex_board.py`; consumed by `scripts/archive_signals.py` → folded into `data/signal_archive/mtf_signals_latest.json` (setup-species program artifact).
- `data/cboe/gex_{KEY}.parquet` — per-name daily GEX summary timeseries (accrued by Cboe collector); used by `build_gex_board._history()` for iv_rank and sparklines.

---

## 2. R2 Public Base URL

Config key: `r2_data_plane.public_base` (in `config.yml`). The live_flow_poller reads this to construct public URLs for the `live_flow/` prefix. All `live_flow/*` and `options_hub/*` R2 objects are served from this base.

**Pattern:** `{R2_PUBLIC_BASE}/live_flow/feed_current.json`, `{R2_PUBLIC_BASE}/options_hub/context.json`, etc.

---

## 3. Deploy Path

- **GEX board (`site/gex/`):** committed to git → deployed via `pages.yml` → VPS static serve.
- **Flow desk (`site/flow/`):** committed to git (but daily CI requires `MASSIVE_S3_*` secrets); render lanes skip (no S3 creds in render.yml).
- **Live flow R2 objects:** written by launchd-managed `live_flow_poller` on Mac Studio → directly to R2; NOT git-tracked.
- **Options hub R2 objects:** written by `build_options_hub_nightly` in nightly CI on Mac Studio runner → directly to R2; NOT git-tracked.
- **`data/thetadata_eod/`:** gitignored (large); lives on Mac Studio ops worktree only; symlinked into data dir.

---

## 4. Reliability / Authority Tier Summary

| Artifact / Field | Authority | Reliable Today |
|---|---|---|
| `positioning.net_doi`, `call_doi`, `put_doi` (site/flow) | ΔOI — no signing | ✅ RELIABLE |
| `positioning.tone`, `lean_en` (site/flow) | ΔOI-derived | ✅ RELIABLE |
| `premium_mn`, `volume`, `pc_ratio`, `zerodte_share` (site/flow) | Magnitude — no signing | ✅ RELIABLE |
| `new_positions.fresh_contracts` (vol>OI) | OI arithmetic | ✅ RELIABLE |
| `net_premium_mn`, `signed_pc`, `gamma_flow_bn` (site/flow) | Tick-rule signed (net recovery 0.41) | ⚠️ SOFT direction, reliable magnitude |
| `verdict.tone` (site/flow) | ΔOI wins over signed-flow direction | ✅ RELIABLE when `positioning_reliable:true` |
| `net_gex_bn`, `gamma_flip`, `call_wall`, `put_wall` (site/gex) | Assumption-signed | ⚠️ LEVELS MAP only (display-only, validation ~Sept 2026) |
| `iv30`, `put_call_oi_ratio`, `max_pain` (site/gex) | Signing-free | ✅ RELIABLE |
| `regime` (site/gex single names) | Assumption + structurally constant | ❌ NOT a time-varying signal |
| `regime` (site/gex indices: SPX/SPY/QQQ) | Assumption-basis | ⚠️ Use with caveat |
| `options_hub/oi_movers.json` ΔOI | Measured OI change | ✅ RELIABLE |
| `options_hub/vol/{ROOT}.json` iv30/iv_rank/skew | Signing-free | ✅ RELIABLE |
| `vol-regime-gate`, `vol-regime-basket-overlay-gate` | scored=false until validation gate | ❌ NOT live-scored yet |
| `live_flow/feed_current.json` events | Tick-rule + z-score vs 252d baseline | ⚠️ Direction soft; magnitude/z-score reliable |

---

## 5. Gaps vs MomoEdge Feature Set

| MomoEdge Feature | Our Coverage | Gap |
|---|---|---|
| Per-trade tape (true buy/sell) | ❌ Not entitled (403 on OPRA trades) | Databento `tbbo` ~$0 under signup credit for focused universe; not funded yet |
| NBBO quote-rule signing | ❌ Not entitled | Same path as above |
| Real-time / sub-minute flow | ❌ (ThetaData RTH at 120s cadence, not tick) | ThetaData streaming (~$80-160/mo) or Databento; deferred |
| OI backfill (pre-2026-06-15) | ❌ blocked on massive.com (no OI in flat files) | Would need Cboe DataShop or similar; not funded |
| Institutional block detection | Partial (vol>OI fresh_contracts + sweep_clusters in live poller) | No true Lee-Ready; sweep heuristics only |
| IV backfill (2024-07-02→present) | ✅ FEASIBLE via massive `day_aggs_v1` BS-invert (~502 days, $0) | Not yet built (OPTIONS_ALPHA_MASTERPLAN F5) |
| Cross-sectional IV rank (120d) | Partial (40d sparkline from cboe parquets) | Full 502d backfill would unlock skew + IV-spread gates (~Dec 2026) |
| Entry-quality harness | Infrastructure wired (`gex_confirm`, `stock_score` GEX/IV tilts) | Scoring gated (`gate.json scored=false`) pending validation ~Q4 2026 |
| GEX→forward-vol validation | Accruing (data/cboe/gex_*.parquet since ~2026-06) | ~Sept 2026 minimum (30 obs/bucket/regime needed) |

---

## 6. Key Source Files (Canonical Paths)

- Engine: `/Users/chriswong/Documents/Cluade/Macro Dashboard/engine/options_flow.py`
- Engine: `/Users/chriswong/Documents/Cluade/Macro Dashboard/engine/gex_engine.py`
- Engine: `/Users/chriswong/Documents/Cluade/Macro Dashboard/engine/gex_model.py`
- Builder: `/Users/chriswong/Documents/Cluade/Macro Dashboard/scripts/build_options_flow.py`
- Builder: `/Users/chriswong/Documents/Cluade/Macro Dashboard/scripts/build_gex_board.py`
- Builder: `.../.claude/worktrees/inspiring-colden-8aedd8/scripts/build_options_hub_nightly.py` (on feat branch; will land on main)
- Engine: `.../.claude/worktrees/inspiring-colden-8aedd8/engine/options_hub.py`
- Poller: `.../.claude/worktrees/inspiring-colden-8aedd8/scripts/live_flow_poller.py`
- Research: `/Users/chriswong/Documents/Cluade/Macro Dashboard/research/OPTIONS_FLOW_DATA.md`
- Research: `/Users/chriswong/Documents/Cluade/Macro Dashboard/research/OPTIONS_ALPHA_MASTERPLAN.md`
- Signal bus: `/Users/chriswong/Documents/Cluade/Macro Dashboard/docs/SIGNAL_BUS.md`
