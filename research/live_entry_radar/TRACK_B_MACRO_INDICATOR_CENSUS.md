# Track B — Macro-side indicator + entry-lane census (Live Entry Radar PR-0)

Archaeology for the Live Entry Radar frozen contract. Every load-bearing claim carries a
`file:line` receipt; unverified claims are marked **UNVERIFIED**. Read-only census.
*This worktree is a SPARSE checkout (`data/`, `site/` absent locally) — `data/` claims come from
`git ls-files` here plus a read-only `ls` of the primary checkout, never a failed local read.*

## 1 · Indicator implementations

### 1.1 Two incompatible RSI families — the headline parity hazard

| # | Impl | Math | Receipt |
|---|---|---|---|
| **R-A** | `canon.rsi` | Wilder RSI on an **SMA-seeded RMA** (== Pine `ta.rsi`): seeds with the mean of the first `n` finite values, recurses `alpha=1/n`, **carries `prev` through NaN gaps** | `engine/canon.py:353-362`; `rma` `:320-340` |
| **R-B** | `technicals.rsi` | Bare `ewm(alpha=1/n, min_periods=n).mean()` — **pandas default `adjust=True`**, no SMA seed | `engine/technicals.py:26-31` |

`engine/canon.py:354-356`: canon is "the corrected RSI the whole confluence cascade rides on; it
differs from `engine.technicals.rsi` (bare `ewm(alpha=1/n)`) only in the early warm-up — **but that
is where crosses flip**." `engine/washout_turn.py:31-33`: technicals' RSI "must NEVER be used here
— it flips near-threshold crosses in the early history … Canon only."

**The trap:** five modules import R-B under a comment asserting it *is* R-A —
`engine/confluence_tiers.py:45` ("faithful Wilder RSI (== Pine ta.rsi)"),
`engine/signal_quality.py:44`, `engine/coiled.py:53`, `engine/postcross.py:54`,
`engine/pick_lab/signals_1d.py:39`. The comments are wrong. **The shipped Prophet gate runs R-B**;
canon and `washout_turn` run R-A. Third variant: `engine/strategy_signals.py:38-48 wilder_rsi`
(recursive `adjust=False`, no SMA seed, `.where(roll_dn != 0, 100.0)` flat clamp), Connors lane only.

### 1.2 StochRSI — 9 sites

All are RSI(14) → stoch(14) → SMA %K(3) → SMA %D(3) in shape; they differ in RSI family,
flat-window (`hi == lo`) policy, and %D derivation.

| # | Site | RSI | Flat-window | %D | Note |
|---|---|---|---|---|---|
| S-1 | `engine/canon.py:437-443` | R-A | `.replace(0,nan)` | SMA(%K,3) | Cross-repo golden oracle |
| S-2 | `engine/confluence_tiers.py:256-261` | R-B | `.replace(0,nan)` | SMA(%K,3) | **Shipped gate's 2D/3D leg** |
| S-3 | `engine/signal_quality.py:78-83` | R-B | `.replace(0,nan)` | SMA(%K,3) | T1 master / §7 markers |
| S-4 | `engine/coiled.py:103-111` | R-B | `.replace(0,nan)` | SMA(%K,3) | "exact copy of confluence_tiers" |
| S-5 | `engine/postcross.py:94-104` | R-B | **`+1e-10` → ~0, never NaN** | SMA(%K,3) | **Divergent NaN policy** |
| S-6 | `engine/pick_lab/signals_1d.py:85-96` | R-B | `.replace(0,nan)` | SMA(%K,3) | Mirror of S-3 |
| S-7 | `engine/cycles.py:205-210` | R-B | `.replace(0,nan)` | **%K only** | Consumers smooth |
| S-8 | `engine/momentum_events.py:119-123` | R-B via S-7 | inherits | SMA(%K,`_STOCH_D_SMOOTH`) | Event-miner leg |
| S-9 | `engine/btc_signals.py:420-423` | local `_rsi` | raw `hi-lo` | **%K only** | BTC lane, out of scope |

**Two genuine divergences.** (1) **S-5 uses `(hi - lo + 1e-10)`** — on a flat RSI window every
other impl emits NaN, S-5 emits ~0, a silent **false-oversold** on low-vol names. (2) **S-5 binds
the RSI period to `stoch_len`**, not a separate `rsi_len` (`engine/postcross.py:99`) — identical at
the 14/14 default, divergent on any retune.

Frozen params are duplicated in two places that must agree — `engine/canon.py:417-419` and
`engine/confluence_tiers.py:56-59`: `RSI_LEN,FAST_LEN,BASE_LEN,SIG_LEN = 14,14,60,5`;
`STOCH_LEN,SMOOTH_K,SMOOTH_D = 14,3,3`; `OB,OS = 80,20`; `CONF_W = 8`; `BUY_RSI_MAX = 65`.

### 1.3 MACD-on-RSI ("RSI-MACD") — 5 sites

Shape everywhere: `EMA(RSI,14) − EMA(RSI,60)`, signal `EMA(·,5)`. **The `adjust` flag splits them.**

| # | Site | EMA form | Receipt |
|---|---|---|---|
| M-1 | `canon.rsi_macd` | `ewm(span, adjust=False, min_periods=span)` | `engine/canon.py:430-434`, `:343-350` |
| M-2 | `confluence_tiers._rsi_macd` | `_ema` | `engine/confluence_tiers.py:250-253` |
| M-3 | `coiled._rsi_macd` | **`ewm(span, min_periods=span)` — `adjust=True`** | `engine/coiled.py:91-92, 95-101` |
| M-4 | `postcross._rsi_macd` | `ewm(span, adjust=False)`, **no `min_periods`** → half-warmed values | `engine/postcross.py:84-92` |
| M-5 | `donor._rsi_macd` / `_rsi_macd_fallback` | **UNVERIFIED** (not read) | `engine/donor.py:91,110` |

`engine/canon.py:344-348`: "`adjust=False` is the recursive definition TradingView uses; the pandas
default (`adjust=True`) is an expanding-weight average that **disagrees near threshold crosses**."
So M-3 sits on the disagreeing branch; M-4 drops the warm-up floor.

### 1.4 Plain price MACD — a different family

`engine/technicals.py:34-38 macd_hist`, `engine/cycles.py:213-218 macd_parts`,
`engine/mtf_upturn.py:268 _price_macd_hist`: classic 12/26/9 on **price**, `adjust=True`. The gate
uses RSI-MACD, never price MACD (`engine/confluence_tiers.py:32`).

### 1.5 ATR — three different definitions

| # | Site | Definition |
|---|---|---|
| A-1 | `engine/stock_technicals.py:58-73` | Wilder TR, `ewm(alpha=1/n, adjust=False, min_periods=n)` |
| A-2 | `engine/strategy_signals.py:65-74` | Same **+ close-only fallback** (`c.diff().abs()`) when high/low absent |
| A-3 | `engine/ignition_features.py:90,111` | TR then **simple `rolling(ATR_WIN).mean()`** — SMA, not Wilder |
| A-4 | `engine/personality_relief_hazard.py:210-220` | TR then `rolling(14).mean()`, **`.shift(1)`** (PIT-safe prior) |
| A-5 | `engine/ohlc_reconstruct.py:82` | Close-only proxy |
| A-6 | **`engine/entry_signal.py:60-73`** | **NOT ATR** — `mean(abs(pct_change))` over 14 bars ×100 |

**A-6 is the trap:** named `_atr_pct`, it sizes Prophet's buy zone / chase line / stop but never
touches high/low — the `high` arg is accepted then deliberately unused (`:67-71`). Also **no ATR
here uses canon's SMA-seeded RMA**, so none equals Pine `ta.atr`.

## 2 · `engine/entry_signal.py` — the boundary to prove clear of

**It does not compute the confluence.** It is a presentation + price-plan layer receiving the gate
verdict as a boolean keyword — `engine/entry_signal.py:148-159`:
`assess(close, high, rec, *, buyable: bool | None = None)`, "the MACD-2D x StochRSI-3D CONFLUENCE
verdict (engine/signal_gate.is_buyable)". Its only use of `buyable` is a **one-way demotion**
(`:193-195`): `buyable is False` + a ladder reading `buy_now`/`partial` → `await_confluence`. It
never upgrades, never re-derives, never inspects a timeframe; `buyable=None` leaves it ungated.
Everything else (buy zone, `chase_above`, `stop`, `atr_pct` = A-6, horizon reads `d3/d21/d63`,
timing window) derives from the daily close plus `rec["ladder"]`/`rec["cycle"]`. Self-gates: no
ladder state, or `< 60` closes → `None` with a named reason (`:131-145`).

**The validated gate lives in `confluence_tiers.py` (compute) + `signal_gate.py` (adjudicate).**
Tier table `engine/confluence_tiers.py:12-16` (weight, definition, held-out stop-out / 110 US
names): **T1** 0.90 3D MACD-RSI × 3D StochRSI, buy-filter endorsed (master) 38.3% · **T2** 1.00 2D
MACD-RSI cross & 3D StochRSI crossed recently 40.6% · **T3** 0.60 2D MACD-RSI projected ≤1-2d & 3D
StochRSI already crossed 42.3% · **T4** 0.40 2D MACD-RSI projected & **2D** StochRSI crossed &
above-200MA 43.1%. `BUYABLE_TIERS = ("T1","T2","T3")` (`engine/signal_gate.py:104`); **T4
deliberately excluded** — it fires off the 2D StochRSI, not the 3D (`:102-103`). `is_buyable(v)` =
`v["eligible"] and v["tier_cascade"] in BUYABLE_TIERS` (`:107-114`). `FRESH_TICKS = 2` **on the
signal's own timeframe** (a tick = one native bar: 3d on the 3D, 2d on the 2D);
`EARLY_CROSS_BARS = 1.5` is the T3/T4 projection window (`:60-66`). The asymmetry is intentional:
"the StochRSI sets up the zone (it need not be same-bar), the 2D MACD cross is the freshness-gated
trigger" (`engine/signal_gate.py:96-99`).

**2D/3D bar construction (the PIT core)** — `_tf_bars(daily, n, market)`,
`engine/confluence_tiers.py:274-304`: `bucket(d) = session_anchor.session_positions(d, market) // n`
— an **absolute** session-calendar anchor, not the caller's first timestamp; era
`ANCHOR_ERA = "abs-session-2026-08-06"` on every verdict (`:54`); ruling
`research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`. Aggregation = per-bucket
**last close**, indexed by that bucket's **last session date** (`:286-290`) — leak-free. The old
`resample("2B"/"3B")` anchored bins to the series' first timestamp: one dropped leading bar flipped
the tier on 13/232 names and the not-topped veto on 27/232, and the two production loaders
disagreed on live buyability the same night (`engine/session_anchor.py:5-12`). The US reference is
**rules, not data** — `lib.nyse_calendar` (`:20-26`); a missing CN/HK/CA reference **raises**
(`:28-33`). A second, deliberate anchor exists: `canon.resample_sessions`
(`engine/canon.py:365-398`) buckets by *ordinal from the caller's first bar* — a 1-to-5-session
leading drop moves a cascade field on **12.83%** of data/stocks cases through the ordinal path and
**0.00%** through the anchored one (`engine/canon.py:380-384`; pinned `tests/test_canon.py:237-338`
§5b). Canon must not be re-phased; the cascade stays absolute.

**What Prophet consumes:** `engine/prophet_doors.py:565-570` — `door_t_fires(v)`, "the incumbent
VALIDATED construction, **byte-unmodified**", returning
`bool(v) and bool(v.get("eligible")) and signal_gate.is_buyable(v)`.

```
daily close ─► confluence_tiers._tf_bars (2D/3D, absolute anchor)
            ─► _stoch_rsi_kd + _rsi_macd   (RSI family R-B)
            ─► signal_gate.gate() → verdict {eligible, tier_cascade, …}
            ─► signal_gate.is_buyable() → bool
            ─► prophet_doors.door_t_fires()       ← Prophet
               entry_signal.assess(buyable=…)     ← display / price plan
```

**Non-interference is mechanical.** Live Entry Radar is provably clear iff it (a) adds no import
into `entry_signal.py`, `signal_gate.py`, `confluence_tiers.py`, `signal_quality.py`,
`prophet_doors.py`; (b) does not change `ANCHOR_ERA`, `BUYABLE_TIERS`, `FRESH_TICKS`,
`EARLY_CROSS_BARS`, or the frozen params at `engine/confluence_tiers.py:56-59`; and (c) writes no
key those modules read. A new module computing its own StochRSI in its own file cannot affect
Door T — the coupling surface is imports and the params block, nothing else.
`engine/washout_turn.py:1-5` is the house precedent for declaring this.

## 3 · Prior entry-timing research + the registered kill

**Corpus:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md` (283 ln), `…AMENDMENT1…` (121),
`…AMENDMENT2…` (135), **`…AMENDMENT3_BY_FABLE.md` (308)**, plus 16 backing reports under
`research/entry_stack/` (notably `A3_HTF_REPORT.md` 634 ln, `A3_CANDIDATE_BOOK_DRAFT.md` 250 ln).

**Depth failed.** `research/entry_stack/A3_CANDIDATE_BOOK_DRAFT.md:20`, verbatim: "Multi-TF stoch
**washout DEPTH** behind a fire (incl. 2W deep) | **H1 FAIL** — +2.9pp clean15 but **+3.5pp
stop5**; `w2_deep ≈ 0 alone`; depth works only through the cohort lens (H6→COILED)" — a marginally
cleaner 15-day path at the cost of a **+3.5pp higher stop-out rate** (the "increased stop burden").
**Motion looked better** — `…:39`: "Weekly TURN adds **+19pp held21** (68.4 vs 49.0) at state
level; deep×reversing **+26pp**; **4-TF turn-confluence count monotone 43.7→61.4%**
(BOTTOM_CONFIDENCE Ph1-2, 68,916 evals — state-level, held21, **NOT fire-conditional, NOT ESX
grader**)." The lesson, `…:62-65`: "at fire time, cycle-scale POSITION (depth/age/location) is dead
or NC-2-confounded; cycle-scale MOTION (turn evidence) is a near-miss/validated-ingredient at state
level … **but never adjudicated on the gate-fire tape itself**." Those figures motivate, not validate.

**The kill.** `research/DO_NOT_REBUILD.md:83`, verbatim:
`| KILL-WASHOUT-TURN | Washout × turn (2W operator seed) | KILLED — operator seed dies in test | Entry-stack Amendment-3 adjudication (#1747) |`

*The "2W operator seed"* was the operator's literal proposal — a **2-week / 1-month StochRSI
washout**, i.e. deep HTF oversold *position*, used **in interaction with a turn**, layered on gate
fires; `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md:271-272` names it "The operator's
literal **'2W/1M StochRSI washout' seed**".

*What killed it:* family `esx_washout_x_turn` (arm C), `…:259` — "**KILLED** | The operator's
literal 2W-washout × turn seed adds NEGATIVE marginal value once proximity is removed: nc2 kills
contrast-i (−0.29pp CI incl 0) and the marginality interaction is adverse (+0.014 baskets / +0.024
deep). Re-confirms the H1 depth kill fire-conditionally." The killing instrument is the **NC-2
proximity de-confound**, mandatory per RUL-28 (`…:65-68`): "The 63-bar close-min NC-2-PROXY band-FE
arm is **mandatory in every A3 primary read as a KILL-ARM**: an effect that dies under proxy-FE is
a proximity shadow — buried." The seed's apparent edge was mostly *proximity to a recent low*.

*Scope* (`…:271-276`): dead in its **position form** and its **interaction form** (C KILLED; A3m
monthly NULL-by-non-replication; A2 2W NULL) — but the **motion form survives** on the broad
universe (A1 weekly turn, baskets-only, DISPLAY-CANDIDATE-CAVEATED, ~⅔ proximity, thin −0.83pp
residual after nc2 FE; `…:255`). Sector-level standalone washout→turn triggers are NULL per Oracle
P8 P-W1/S-W3 (`…:20-23`).

**The house template for distinguishing a new construction** —
`research/TURN_SENSITIVITY_UPGRADE_MASTERPLAN_BY_FABLE.md:46` (TS-R3): "This is NOT a revival of
the killed 'Washout × turn (2W operator seed)' (**different construction: no washout precondition,
no operator seed, per-stock granularity, K-of-N legs**) and is registered as an **expected-NULL
forward meter** citing Oracle P8 P-W1/S-W3 + DO_NOT_REBUILD §2." Live Entry Radar should carry the
same four-part distinction plus an explicit nc2-proximity arm, shipping display-tier while it
accrues. Citation idiom also at `research/MAG7_WASHOUT_REENTRY_PREREG.md:292`,
`research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md:59-61`.

## 4 · Daily OHLCV data plane

**Vendor + adjustment:** yfinance `auto_adjust=True` — `collectors/_stock_ohlc.py:52-56`, documented
`:92` as "the dividend/split-ADJUSTED total-return plane"; `engine/prophet_live/live_states.py:136-138`
independently confirms. **Canonical accessor:** `lib/store.py:36 read(group, name)`; writes via
`:60 upsert`.

**The adjustment hazard already bites indicators** — `lib/store.py:64-77`: "after an ex-dividend
every prior bar is re-scaled… Plain `combine_first` … leav[es] a PERMANENT basis STEP at the
refresh edge (measured 17/300 A-share names >0.4%, worst 40%, May-dividend clustered) … and **can
fabricate MACD/StochRSI crosses**." Guards: `lib/store.py:106 basis_shifted(...)`;
`collectors/yahoo.py:226-235` re-pulls `period='max'` for any shifted name;
`collectors/breadth.py:36` notes `auto_adjust` back-adjusts only the downloaded window.

**Coverage — two equity stores of different depth:** `data/stocks/` 240 tracked / 229 on disk, deep
**1960s-start**; `data/baskets/ohlcv/` 2779 / 2519, **2014-start** (depths per
`engine/session_anchor.py:8-9`; tracked-vs-disk gap **UNVERIFIED**, likely delistings/gitignored).
These two loaders **disagreed on live buyability the same night** (NUE/PEP/WMT buyable from one
only; ECL/SW inverted) — the disagreement the absolute anchor fixed (`engine/session_anchor.py:5-12`).
Pin and disclose which store is read.

**Intraday bar data: YES — a US-equity HOURLY store exists and already names the 4H timeframe.**
(An earlier pass of this census wrongly concluded "no": a sweep for `interval="60m"` misses it,
because Polygon is a REST aggregates path, not a kwarg. Corrected.)

**Producer** `scripts/build_polygon_intraday.py` → `data/intraday/<T>.parquet`; docstring `:1-7`:
"Intraday (hourly) US price accrual via Polygon / massive.com … **Powers the 4H timeframe** on US
single-stock charts and the 2D/3D intraday bar-derivation hooks (`engine/bar_derive.py`)".
**Vendor/freshness** Polygon **STANDARD** — **15-MIN DELAYED**, `DELAYED_MIN = 15` (`:38`), stamped
to a `data/intraday/_meta.json` sidecar (`:9-13`); **not real-time**. **Granularity**
`multiplier: 1`, `timespan: hour` (`config.yml:597-598`) — **4H is aggregated client-side by
chart.js** (`:590-591`), no stored 4H bar exists. **Coverage** US-only by entitlement, curated to
`data/stocks/*` + sector/factor ETFs (`:592`) — ~240 names, **not** the 2,779-name `baskets/ohlcv`
universe. **Retention** `lookback_days: 180` cold-start, hourly cron `--lookback-days 5`,
append-only with 2-day overlap and dedup on bar ts (`:598`); **schedule**
`.github/workflows/intraday.yml` (`intraday-bars`), cron `35 13-21 * * 1-5`, self-hosted,
`POLYGON_API_KEY` a CI secret (`:15,55-60`). **Persistence — this matters:** **gitignored**
(`.gitignore:66`), persisted only via `actions/cache` under the `intraday-` namespace (`:63-65`),
with `site/intraday/<T>.json` the shipped artifact — so it is **CI-cache-resident, not committed**
(0 tracked files, absent from the primary checkout). **UNVERIFIED:** live population (needs the
CI-only key, `:24-25`). Also present, out of scope: `commodity/{asset}_hourly`
(`scripts/commodity_sentinel.py:40,75`), `coinbase/btc_hourly` (`scripts/vector_sentinel.py:63`);
`engine/thetadata_store.py` is **EOD options** (`:4`, `:96`).

**Two hard caveats** — `engine/bar_derive.py:1-4, 20-23`: (1) "Nothing here is wired into a
production build by default — **it is additive plumbing**" — `derive_daily_close`,
`derive_2d_ohlcv`, `derive_3d_ohlcv` feed no scored signal today; (2) **basis mismatch**: "The
intraday store carries **raw** prices; the nightly `data/stocks` close is dividend/total-return
ADJUSTED. Confluence run on a raw intraday-derived close is **NOT directly comparable** to
confluence on the adjusted daily store." `bar_derive` further warns `derive_2d/3d_ohlcv` are **not**
inputs to `signal_frame` — that "would double-resample and break faithfulness".

## 5 · Session calendar

All calendar logic is **hand-rolled stdlib**; `pandas_market_calendars` / `exchange_calendars` are
used nowhere and are in no `requirements.txt`. Timezones are stdlib `zoneinfo`.

**`lib/nyse_calendar.py`** (625 ln) is the **real** one: rule-computed NYSE holidays + observance
shifts, `ONE_OFF_CLOSURES` (2012 Sandy, 2018 Bush, 2025 Carter), session-gap API
`session_n_back/forward`, `sessions_between` (`:469-624`) — but it explicitly does **not** model
early closes (`:10-13`). That gap is filled by **`engine/session_digest.py`**, **real and
DST-safe** and the *only* early-close model: open 9:30 / close 16:00 / `EARLY_CLOSE_ET` 13:00
(`:170-176`), `is_early_close()` (`:199-226`), `session_window_et()` (`:229-239`).
`lib/hk_calendar.py` (283) and `lib/cn_calendar.py` (202) mirror the `is_session`/`holidays` shape
but are **separate modules with no shared rule engine** (CN deliberately minimal plus a
`MAX_LEGIT_CLOSURE_DAYS = 11` backstop, `cn_calendar.py:16-28,53`); `pd.offsets.BDay()` (dozens of
sites) is holiday-**blind**, self-labelled (`engine/earnings_blackout.py:102`).

**Reach:** ~110 files import `lib.nyse_calendar` (404 occurrences) — the nightly
(`scripts.build_session_digest`, `daily.yml:3622`), the render lane (`scripts/build_site.py:74`),
Prophet (`engine/prophet_bridge.py`, `engine/prophet_live/{armed_pack,live_states}.py`, raising
`ContractError` on "not an NYSE session", e.g. `engine/options_signal_episode.py:620`), and
`engine/{marketing/market_clock,rebalance_calendar,source_registry}.py`. It is also the reference
behind the 2D/3D anchor (§2).

**Intraday session clock: YES, but fragmented and partly holiday-blind.** Holiday-aware
`pre|rth|post|closed` machines at `scripts/build_basket_pulse.py:158-214` (US+HK),
`scripts/chain_snapshot_poller.py:1462-1541` (bar-close bucket boundaries + sub-minute grace),
`scripts/build_prophet_marks.py:206-213`. **Holiday-BLIND** RTH checks — verified directly — at
`scripts/live_breadth_poller.py:138-169` (`session_tag` is bare `et.weekday() >= 5` plus minute
arithmetic; the file **does not import `nyse_calendar` at all**),
`scripts/live_flow_poller.py:2712-2725`, `engine/live_quotes.py:51-66`,
`engine/live_overlay.py:129-160` ("ADVISORY hint only — no exchange holiday calendar and no
half-days"). These treat a weekday market holiday as open. **No canonical "now in ET" helper:** 27+
modules independently define `ET = ZoneInfo("America/New_York")`;
`engine/marketing/market_clock.py:20-22`: "Nine separate sites had independently re-implemented
`weekday() >= 5`... not one of them was holiday-aware."

## 6 · Existing live / provisional-intraday computation

**A live lane exists and deliberately does NOT recompute indicators intraday.**
`engine/prophet_live/`: `armed_pack.py` (1011 ln), `interval.py` (317), `live_states.py` (988),
`r2io.py` (163); cadence `.github/workflows/prophet-live.yml:65-67` — every 5 min, 13:25Z–21:15Z
Mon–Fri. `armed_pack.py:3-8`: "it re-runs the SAME close-only admission gate
(`engine.signal_gate.gate`) with candidate provisional closes appended as tonight's new session
bar, and records the price interval over which `is_buyable` is true. **The */5 intraday lane then
only has to compare a delayed live price to those two numbers — it never re-derives a signal.** The
pack is an OPTIMIZATION; the gate is the truth." So the house pattern for "live" is **nightly
price-threshold inversion**; the intraday lane does no bar math at all.

`probe_series(close, candidate)` (`armed_pack.py:225-243`) appends the candidate as the **NEXT
session's bar**, never overwriting the as-of close. Measured: switching from replace- to
append-semantics changed the answer for **45 of 180** probed names and moved the armed count
98 → 68 (`:20-25`), because replacing froze series length, session-anchor bucket positions and
freshness tick counts at yesterday's. **Price-basis hazard, already solved once** —
`live_states.py:136-147`: armed levels are prices on the **split+dividend adjusted** close series;
`price` on every row is a **raw vendor print**; "the live quote is deliberately NOT converted — an
adjusted 'quote' is a number no exchange ever printed." Every pass runs `interval.basis_audit`
(pack `as_of_close` vs feed `prev_close`, per name); past `basis_tolerance_pct` the name goes
`dark` with `basis_mismatch`. States are graded `live / delayed(~Nmin) / last_rth / eod / dark`
(`:20`; honest-delay law TS-R1 at
`research/TURN_SENSITIVITY_UPGRADE_MASTERPLAN_BY_FABLE.md:44`).

**Partial-bucket provisionals exist on the daily grid:** `engine/confluence_tiers.py:664` — "the
partial bucket `_tf_bars` still emits — the live board's provisional basis"; a 2D/3D bucket in
progress is published as provisional **from daily closes**, no intraday bar feeds it. Siblings:
`engine/htf_oscillators.py:51-92 stochrsi_2w` (epoch-anchored biweekly close, reusing
`signal_quality._stoch_rsi_kd`) and `engine/oracle/oscillators.py:110+ weekly_stochrsi_kd` (W-FRI
ffilled onto the daily index, **in-progress week excluded**). **A 2W-grid contradiction not to
inherit:** `engine/htf_durability.py:102-115 _biweekly_close` states "MUST NOT use
`resample('2W-FRI')` — that bins are calendar-anchored and drift with as-of date, making backtest
!= live", using a fixed-epoch week-pair anchor over completed pairs only;
`engine/momentum_events.py:149,166` does exactly that for its `stoch_events_2w` family.

## 7 · Boundary addendum — the market-timing-intelligence parent program

**`engine/ignition_radar.py` (1137 ln)** — risk-**ON** mirror of the Risk Radar (点火雷达).
**DISPLAY-ONLY, FORWARD-GRADED, NOT VALIDATED**; "nothing here is a buy signal" (`:1-4`). Two
channels, never fused: **BROAD** = a K-of-8 confluence *count* — 4 catalyst chips reused from
`risk_radar_market_catalysts.compute()` (`c1_thrust_confluence`, `c2_msi_swing`,
`c3_washout_thrust20`, `c4_ftd`) + 4 local participation confirms (`pct50_recover`, `nh_flip`,
`rsp_confirm`, `sector_participation`) (`:5-17`), thresholds `_K_IGNITED = 3` / `_K_WARMING = 1`
(`:44-45`); **NARROW** = `compute_basket_ignition` per US thematic basket + 11 sector ETFs + SMH
(`:18-20`). Output `data/ignition_radar/latest.json`, regime `ignited/narrow/warming/off` (`:21-25`).
**Grain is MARKET and BASKET, never per-name.** No StochRSI, no per-ticker entry timing.

**`engine/setups.py` (293 ln)** — cross-sectional **setup scoring**: selection (sector-neutral
residual alpha) × timing (`engine/cycles` + reversal overlay) (`:1-10`), explicitly "**NOT a new
statistical edge**" (`:6-10`); alpha weights US 0.7 / CN 0.35 / CA 0.55 (`:29-31`). A **consumer**
of Prophet's gate — the US "Top setups" shortlist is gated on `signal_gate.is_buyable` (`:240-245`)
and it reads `entry_signal.assess()["status"]` (`:270`).
**`engine/stock_personality.py` (1129 ln)** — per-ticker label assembly, **DISPLAY-ONLY and PURE**;
"Never scores, sizes, or gates positions"; `may_rank/size/gate=False` (`:1-18`).
`setup_compatibility(personality, species_entries)` is where a new entry species would be
*described*, not gated.

**The real collision is NOT `ignition_radar`** — despite the name it is market/basket-grain breadth,
and its only washout-shaped element is `_c3_washout_thrust20`, a **breadth** chip (`%>20dma
washout→thrust`, off `data/breadth/_closes_cache.parquet`,
`engine/risk_radar_market_catalysts.py:312-320`). Different grain, different input; the overlap is
vocabulary only.

**It is `engine/washout_turn.py`** — an existing **per-name weekly washout-turn watch organ (US)**,
display-tier, zero authority (`:1-4`), built because MCD printed a weekly RSI-MACD bullish cross at
the 6.3rd percentile of its own weekly line history since 1968 and no organ consumed weekly-grain
confluence per name (`:6-16`). It writes `site/stockdata/washout_turn.json`,
`data/washout_turn/ledger.jsonl`, `rec["washout_turn"]` (`:18-22`), on **canon math only** (R-A)
(`:24-33`), and its charter already records the kill boundary —
`research/washout_turn_name_lane/MCD_MISS_EVIDENCE_2026-08-05.md:76-77`: "Scored washout→turn
constructions remain NULL/killed per Oracle P8 P-W1/S-W3 and Entry-stack Amendment-3 #1747 — this
lane ships display-tier watch vocabulary only." `engine/mtf_upturn.py` (TS-R3, §3) is the second
adjacency: per-stock multi-TF upturn organ, K-of-N legs, display tier, registered expected-NULL.

**Contract implication.** Draw the boundary against `engine/washout_turn.py` and
`engine/mtf_upturn.py` (same grain, same family, overlapping vocabulary); merely *note*
`ignition_radar` as a name collision at a different grain. `setups.py`/`stock_personality.py` are
downstream consumers — "may be read by them; must not write into their scoring".

## 8 · Top risks for indicator parity

1. **RSI-family split (R-A vs R-B).** Five modules import the bare-`ewm` RSI under a comment
   claiming it is Pine `ta.rsi`. The shipped gate runs R-B; canon and `washout_turn` run R-A. Any
   new "StochRSI" that does not name its family will silently match one and diverge from the other
   near threshold crosses — exactly where entries fire.
2. **Adjusted-vs-raw basis — the deepest hazard, and the 4H tier sits on the wrong side of it.**
   The daily plane is split+dividend adjusted; the hourly `data/intraday` store is **raw**, and
   `engine/bar_derive.py:20-23` says confluence on a raw intraday-derived close is "NOT directly
   comparable" to confluence on the adjusted daily store. Separately, a re-adjustment on the daily
   plane can "fabricate MACD/StochRSI crosses" (`lib/store.py:73-76`). Any 1D-live or 4H indicator
   must pick one basis and reconcile per name; Prophet's live lane escapes this only because it
   never recomputes (`live_states.py:136-147`).
3. **The 4H tier's supply is thinner than it looks (§4).** Hourly bars exist, but: 15-min delayed
   by plan, ~240 names (not the 2,779 basket universe), no stored 4H bar (chart.js aggregates
   client-side), CI-cache-resident and gitignored rather than committed, live population
   **UNVERIFIED**, and `bar_derive` is explicitly "additive plumbing" wired to nothing. Treat 4H as
   a build item with a data-availability spike, not a solved input.
4. Secondary: two legitimate session anchors (12.83% vs 0.00% verdict movement — adopt the absolute
   one, mint a new era string); `postcross`'s `+1e-10` false-oversold (§1.2); `adjust=True` in
   `coiled` and missing `min_periods` in `postcross` (§1.3); the `_atr_pct` misnomer (§1.5 A-6);
   holiday-blind live RTH checks (§5); the live 2W-grid contradiction (§6).
