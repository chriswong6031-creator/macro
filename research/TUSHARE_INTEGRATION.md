# Tushare Pro integration — gated premium A-share data

**Status:** shipped (data layer + fund-flow leg + crowding upgrade), display/context-only.
`TUSHARE_TOKEN` is configured as a GitHub Actions secret — the nightly build refreshes
`data/tushare/`. **⚠️ DARK since 2026-07-27:** the vendor rejects the configured token's value
(`code=40101`) and the plane is frozen at the 2026-07-24 close pending an operator token
regeneration — see the incident section immediately below.
**Tier:** ¥500/yr · 5000积分 (regular data, no daily cap). Every collector's endpoint sits within
this tier (smoke-tested live: daily_basic, margin_detail, moneyflow_dc, cyq_perf,
broker_recommend, forecast_vip all return rows). `report_rc` (8000积分) is ABOVE this tier, but
Tushare still serves a throttled ~1/hour PREVIEW of it (a `频率超限` rate-limit, not a
permission-denied), so the forecast-revision raw still accrues slowly — best-effort, never
required.

## 2026-07-27 — the vendor started REJECTING the configured token (code 40101)

**Operator action required.** Since 2026-07-27 every Tushare call in the nightly asia lane comes
back `code=40101 msg=您的token不对，请确认。` ("your token is incorrect") — `trade_cal`, `daily`,
`daily_basic` and `moneyflow_dc` alike (last observed: run 31095457182, asia job 2026-08-06
11:39Z–11:49Z). The `TUSHARE_TOKEN` secret **is set** — the gate in `collectors/china_tushare.py`
would have raised before the module loop otherwise, and a heartbeat row was written every night —
so this is not a missing credential: the vendor is rejecting its **value**.
`data/tushare/*.parquet` has been frozen at the 2026-07-24 close ever since.

**Nothing on this side changed — the invalidation is server-side.** The `TUSHARE_TOKEN` secret
was last written **2026-07-02** (GitHub's secret `updated_at`; the API exposes the timestamp, never
the value), 25 days before the break, and that same value collected cleanly every night up to the
cliff — `data/china_tushare/run_log.parquet` reads valuation 5526 / moneyflow 5910 on 07-26, then
`0.0` across all seven modules from 07-27 onward. `collectors/tushare_client.py` has not been
touched since before 07-15 either. So the same string, unchanged, worked for 24 nights and was
then refused: it was invalidated on tushare.pro's side, NOT rotated or mangled here. (An earlier
revision of this note guessed "a rotated, regenerated or mangled token" — the secret timeline
refutes that; the operator confirmed they never changed it.)

**Remedy (operator only) — compare first, then decide.** Open the tushare.pro account page and
compare the token shown there with the one in the GitHub Actions secret `TUSHARE_TOKEN`:

* **It DIFFERS** → the token was regenerated on their side (their account page has a refresh
  action, and a password change rotates it too, killing the old string instantly). Copy the
  current token into the secret and the plane resumes on the next asia run.
* **It MATCHES** → the value is correct and re-copying it changes nothing. The account itself is
  what stopped resolving — check membership / 积分 state.

`40101` reads as "token is wrong" in both cases, so the error text alone cannot separate them —
which is why the remedy is a comparison and not a blind regeneration. Nothing in the repo can fix
either case; never paste a token value into a file, a PR, or a log line.

**Why it was invisible for ten nights, and what now surfaces it.** `query()` degrades *every*
failure to `None`, so a rejected credential was indistinguishable from an empty snapshot: each
`tushare_*` `refresh()` returned 0 rows, `china_tushare`'s heartbeat wrote **0.0** (not the `-1.0`
an exception leaves), the adapter reported `status=ok`, and run_status, the circuit breaker and
every freshness guard saw a healthy plane. `#4676`'s `desk.json` staleness `::warning` fired, but
it names the symptom, not the cause. Now:

- `tushare_client.last_auth_error()` latches the last auth-class rejection
  (`{api_name, code, msg, ts}`); the latch is deliberately narrow (**40101 only** — 40203 is the
  rate-limit / above-tier code, and `report_rc` is throttled by design every night) and clears on
  the next `code==0` response, so a re-issued token self-clears with no restart.
- `ChinaTushareAdapter.fetch()` raises when a rejection is latched **and no module landed rows**,
  after printing a line-start `::error title=tushare-auth-rejected::…` annotation. The night's
  heartbeat row is then *not* written — intended: the missing row is the honest signal the
  freshness guards can already see, and `expected_failure` stays unset (it only covers an *absent*
  token) so the breaker counts the failure. Partial success (some module still returns rows) logs a
  warning and does not fail the night.

**Recovery is visible** when `data/china_tushare/run_log.parquet` shows any non-zero module count
(and `data/tushare/*.parquet` starts advancing again).

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
zeroed; an unproven family rides its prior (context floor).

**`fundflow` + `chips` families are now live.** `collectors/tushare_history` backfills + accrues a
compact DAILY-grid per-name history (`data/tushare/{flow_hist,chips_hist}.parquet`, panel names
only) so the cross-sectional rank-IC computes against ~1 year of real history immediately rather
than waiting months. `china_validation` validates them like the valuation family (forward
CSI-300-relative rank-IC + an incremental-IC neutralization vs momentum/reversal/size), and
`_VAL_FAMILY` maps the `flow` convergence leg → `fundflow`.

**First verdict (51 weekly cross-sections):** fund-flow has **no significant 21d cross-sectional
edge** (IC ≈ −0.008, HAC t ≈ −0.8) — a slight short-horizon reversal (5d t≈−1.5) flipping to slight
continuation by 63d (t≈+1.7), net-zero at 21d. So `flow` correctly **holds its 0.18 prior** (not
proven → not boosted; |t| < 2 → not zeroed): measured context, not validated alpha. `chips`
(win-rate) is likewise insignificant (IC +0.014, t 0.6). This is the honest machinery working — the
moment fund-flow either proves out or proves wrong-sign on accruing data, its weight moves on its own.

**Sector flow → radar (done).** `engine/china_radar` adds per-sector pairs: each sector's own 东财
net-flow (`moneyflow_ind_dc`) vs its price RS → POSITIVE/NEGATIVE divergence, gated, deadbanded,
8 sector ETFs mapped to exact 东财 industry boards. Accrues in the radar ledger like every pair.

**Earnings-guidance signal + family (done).** `collectors/tushare_forecast` scores each 业绩预告
(type direction × guided net-profit Δ%) and accrues `forecast_hist.parquet`; a 📣 desk panel surfaces
the top surprises; `china_validation` adds a `guidance` family (cross-sections keyed by ann_date).
**Verdict:** a real ~3-month post-earnings drift — 63d IC +0.097, HAC t +2.83 (right sign,
significant); 21d still weak (t 0.5, n 19), so honestly `tested`/accruing toward proven.

## Next (follow-ups)

- Compute sell-side forecast-REVISION momentum from `report_rc` once its raw history accrues (now
  throttled to ~2 calls/day on this tier → ~1 windowed call per nightly build), then add a
  `report_rc` validation family.
- Accrue a sector-flow history so the radar pair can use a smoothed multi-day flow (vs today's
  single-day snapshot) and gain its own validation.
