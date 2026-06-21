# Tushare Pro integration — gated premium A-share data

**Status:** shipped (data layer + fund-flow leg + crowding upgrade), display/context-only.
`TUSHARE_TOKEN` is configured as a GitHub Actions secret — the nightly build refreshes
`data/tushare/`.
**Tier:** ¥500/yr · 5000积分 (regular data, no daily cap). Every collector's endpoint sits within
this tier (smoke-tested live: daily_basic, margin_detail, moneyflow_dc, cyq_perf,
broker_recommend, forecast_vip all return rows). `report_rc` (8000积分) is ABOVE this tier, but
Tushare still serves a throttled ~1/hour PREVIEW of it (a `频率超限` rate-limit, not a
permission-denied), so the forecast-revision raw still accrues slowly — best-effort, never
required.

## How it's gated

The whole integration hangs off `collectors/tushare_client.py`, which is **inert unless the
`TUSHARE_TOKEN` env var is set**:

- No token → `enabled()` is `False`, every `query()` returns `None`, and every `tushare_*`
  collector's `refresh()` returns `0`. The free akshare/Eastmoney stack and the keyless CI build
  are completely unaffected.
- The token is read from the environment **only** — never written to disk or committed. Add it as
  a GitHub Actions secret named `TUSHARE_TOKEN` for the nightly build.
- Suffix normalisation: Tushare uses `.SH` for Shanghai; this repo uses `.SS`. The client remaps
  `.SH → .SS` on every returned `ts_code` so per-name joins line up. `.SZ`/`.BJ`/`BK####.DC` pass
  through.

The collectors are gated; the **parsers are not** — `engine/china_extras` reads whatever parquet
is on disk (the "repo is the database" convention). So a committed Tushare cache surfaces even in a
keyless build, and CI with the secret refreshes it nightly.

## Endpoints used (endpoint → 积分 → what it fills)

| Collector | Endpoint | 积分 | Fills |
|---|---|---|---|
| `tushare_moneyflow` | `moneyflow_dc` (per-name) + `moneyflow_ind_dc` (sector) | 5000 | **THE gap** — push2 fund-flow 502s from a non-CN IP; DC = same 东财 data, IP-reliable |
| `tushare_valuation` | `daily_basic` | 2000 | per-name PE/PB/turnover/mv → per-name crowding `rich_valuation` |
| `tushare_margin` | `margin_detail` | 2000 | per-name 融资余额 → cleaner crowding `margin_froth` |
| `tushare_chips` | `cyq_perf` | 5000 | holder cost-basis + win-rate (筹码胜率) positioning |
| `tushare_broker` | `broker_recommend` | 2000 | 券商每月金股 monthly pick tally (discrete sell-side conviction) |
| `tushare_forecast` | `forecast_vip` + `report_rc` | 5000 / 8000 | earnings guidance (in-tier) + sell-side EPS-revision (above-tier, 1/hr preview, best-effort) |

All snapshot collectors pull the whole market in ONE `trade_date=` call (`snapshot_by_date` walks
back to the latest day with rows). `report_rc` is throttled to 1 call/hour → pulled once per build
over a date window (best-effort; degrades silently when the hourly budget is spent).

## What's wired now

- **Fund flow is a NEW signed leg** in the alt-data convergence (`engine/china_altdata` `flow`,
  prior weight 0.18). It expanded the convergence universe from ~hundreds to ~5,200 names. This is
  a DISPLAY join — no validated edge claimed — and the predictive-weighting bridge
  (`china_signal_lab.leg_weights_for`) will zero/boost it once `china_validation` proves it.
- **Crowding upgraded** (`engine/china_crowding`): `rich_valuation` and `margin_froth` now prefer
  the per-name Tushare snapshots (free whole-market anchor / akshare cache remain the fallback), so
  `rich_valuation` fires stock-by-stock instead of only the market-regime sentinel.
- **券商金股 panel** on the alt-data desk (display-only pick tally).
- `chips` (winner_rate) + `forecast` guidance + `report_rc` revisions are **collected + registered
  `pending`/`display`** in `china_signal_lab` — surfaced/scored only after a Phase-0 validation.

## Validate-before-score discipline

Every new premium feed lands **display/context-only**. Promotion to an earned, scored weight goes
through `engine/china_validation` (forward-return rank-IC, HAC t, sign check) → only a `proven`,
right-sign family earns weight via `china_signal_lab.leg_weights_for`; a proven wrong-sign family is
zeroed. Fund-flow has no validation family yet, so it rides at its prior (context floor) until one
is added — honest, not alpha.

## Next (follow-ups, not in this PR)

- Add a `fundflow` / `chips` / `report_rc` family to `china_validation` so the new legs can EARN
  weight (or be zeroed).
- Wire `moneyflow_ind_dc` (sector flow) into the divergence radar (sector-flow vs price pair).
- Compute forecast-REVISION momentum from the `report_rc` raw history once it accrues.
