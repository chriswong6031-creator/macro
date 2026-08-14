# Track B — Macro-side indicator + entry-lane census (Live Entry Radar PR-0)

Archaeology for the Live Entry Radar frozen contract. Every load-bearing claim carries a
`file:line` receipt. Claims I could not verify from source are marked **UNVERIFIED**.
Read-only census; nothing in the repo was modified.

---

## 1 · Indicator implementations

### 1.1 The two RSI families (the headline parity hazard)

There are **two mutually-incompatible RSI implementations**, and the repo knows it:

| # | Impl | Math | Receipt |
|---|---|---|---|
| R-A | `canon.rsi` | Wilder RSI on an **SMA-seeded RMA** (== Pine `ta.rsi`); `rma` seeds with the mean of the first `n` finite values, then recurses `alpha=1/n`, and **carries `prev` through NaN gaps** | `engine/canon.py:353-362`, `rma` at `:320-340` |
| R-B | `technicals.rsi` | Bare `ewm(alpha=1/n, min_periods=n).mean()` — **pandas default `adjust=True`**, no SMA seed | `engine/technicals.py:26-31` |

They are NOT the same function. Canon states it outright:

> `engine/canon.py:354-356` — "This is the corrected RSI the whole confluence cascade rides
> on; it differs from `engine.technicals.rsi` (bare `ewm(alpha=1/n)`) only in the early
> warm-up — but that is where crosses flip."

`engine/washout_turn.py:31-33` is blunter:

> "WARNING: `engine.technicals.rsi` is a DIFFERENT rsi (bare `ewm` warm-up) and must NEVER be
> used here — it flips near-threshold crosses in the early history, which is exactly the depth
> region this organ reads. Canon only."

**The trap:** at least five modules import R-B under a comment asserting it is R-A —
`engine/confluence_tiers.py:45` ("faithful Wilder RSI (== Pine ta.rsi)"),
`engine/signal_quality.py:44` ("Wilder RSI, matches Pine ta.rsi"),
`engine/coiled.py:53`, `engine/postcross.py:54`, `engine/pick_lab/signals_1d.py:39`.
The comments are wrong. **The shipped Prophet entry gate runs on R-B**, while the cross-repo
golden-vector oracle (`canon`) and `washout_turn` run on R-A. Live Entry Radar must pick one
family *explicitly* and never inherit a comment's claim.

A third variant exists: `engine/strategy_signals.py:38-48 wilder_rsi` — recursive
`adjust=False`, no SMA seed, plus a `.where(roll_dn != 0, 100.0)` flat-market clamp R-A/R-B
lack. Used by the Connors/RSI-2 strategy lane only.

### 1.2 StochRSI implementations (9 distinct sites)

All are RSI(14) → rolling stoch(14) → SMA %K(3) → SMA %D(3) in shape. They differ in RSI
family, flat-window (`hi == lo`) policy, and `%D` derivation.

| # | Site | RSI | Flat-window policy | %D from | Notes |
|---|---|---|---|---|---|
| S-1 | `engine/canon.py:437-443` | R-A | `.replace(0, np.nan)` → NaN | SMA(%K,3) | Cross-repo golden oracle |
| S-2 | `engine/confluence_tiers.py:256-261` | R-B | `.replace(0, np.nan)` | SMA(%K,3) | **The shipped gate's 2D/3D stoch leg** |
| S-3 | `engine/signal_quality.py:78-83` | R-B | `.replace(0, np.nan)` | SMA(%K,3) | T1 master / §7 markers |
| S-4 | `engine/coiled.py:103-111` | R-B | `.replace(0, np.nan)` | SMA(%K,3) | Self-described "exact copy of confluence_tiers" |
| S-5 | `engine/postcross.py:94-104` | R-B | **`+ 1e-10` epsilon → ~0, never NaN** | SMA(%K,3) | **Divergent NaN policy** |
| S-6 | `engine/pick_lab/signals_1d.py:85-96` | R-B | `.replace(0, np.nan)` | SMA(%K,3) | Mirror of S-3 |
| S-7 | `engine/cycles.py:205-210 stoch_rsi` | R-B | `.replace(0, np.nan)` | **%K only** (caller smooths) | `%D` added by consumers |
| S-8 | `engine/momentum_events.py:119-123 _stoch_kd` | R-B (via S-7) | inherits S-7 | SMA(%K, `_STOCH_D_SMOOTH`) | Event-miner leg |
| S-9 | `engine/btc_signals.py:420-423 _srsi_k` | local `_rsi` | `hi-lo` raw | **%K only** | BTC lane, out of scope |

**Two genuine math divergences, not stylistic:**
1. **S-5 (`postcross`) uses `(hi - lo + 1e-10)`** instead of `.replace(0, np.nan)`. On a flat
   RSI window every other implementation emits NaN; S-5 emits ~0 (i.e. "maximally oversold").
   That is a silent false-oversold on low-volatility names.
2. **S-5 also binds the RSI period to `stoch_len`**, not to a separate `rsi_len`
   (`engine/postcross.py:99` — `r = rsi(series, stoch_len)`). Identical at the 14/14 default;
   divergent the moment either is retuned.

Frozen params, duplicated in two places that must agree:
`engine/canon.py:417-419` and `engine/confluence_tiers.py:56-59` —
`RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5`; `STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 3, 3`;
`OB, OS = 80, 20`; `CONF_W = 8`; `BUY_RSI_MAX = 65`.

### 1.3 MACD-on-RSI ("RSI-MACD") — 5 sites

Shape everywhere: `EMA(RSI,14) − EMA(RSI,60)`, signal `EMA(·,5)`. **The EMA `adjust` flag is
where they split.**

| # | Site | EMA form | Receipt |
|---|---|---|---|
| M-1 | `canon.rsi_macd` | `ewm(span, adjust=False, min_periods=span)` (`canon.ema`) | `engine/canon.py:430-434`, `:343-350` |
| M-2 | `confluence_tiers._rsi_macd` | `_ema` — see note | `engine/confluence_tiers.py:250-253` |
| M-3 | `coiled._rsi_macd` | **`ewm(span, min_periods=span)` — `adjust=True` (pandas default)** | `engine/coiled.py:91-92, 95-101` |
| M-4 | `postcross._rsi_macd` | `ewm(span, adjust=False)`, **no `min_periods`** → emits half-warmed values | `engine/postcross.py:84-92` |
| M-5 | `donor._rsi_macd` / `_rsi_macd_fallback` | UNVERIFIED (not read) | `engine/donor.py:91,110` |

`canon.ema` documents exactly why this matters:
> `engine/canon.py:344-348` — "`adjust=False` is the recursive definition TradingView uses; the
> pandas default (`adjust=True`) is an expanding-weight average that **disagrees near threshold
> crosses**."

So **M-3 (`coiled`) is on the disagreeing branch**, and **M-4 (`postcross`) drops the warm-up
floor** — both against a house rule stated in canon.

### 1.4 Plain price MACD (a *different indicator family*)

`engine/technicals.py:34-38 macd_hist` and `engine/cycles.py:213-218 macd_parts` — classic
12/26/9 on **price**, `adjust=True`, `min_periods=span`. Do not confuse with §1.3: the
confluence gate uses RSI-MACD, never price MACD (`engine/confluence_tiers.py:32` — "faithful
RSI-MACD (NOT price MACD)"). `engine/mtf_upturn.py:268 _price_macd_hist` is the price-MACD leg.

### 1.5 ATR — 6+ sites, three different definitions

| # | Site | Definition | Receipt |
|---|---|---|---|
| A-1 | `stock_technicals.atr` | Wilder TR, `ewm(alpha=1/n, adjust=False, min_periods=n)` | `engine/stock_technicals.py:58-73` |
| A-2 | `strategy_signals.atr` | Same, **plus a close-only fallback** (`c.diff().abs()`) when high/low absent | `engine/strategy_signals.py:65-74` |
| A-3 | `ignition_features` | TR then **simple `rolling(ATR_WIN).mean()`** — SMA, not Wilder | `engine/ignition_features.py:90,111` |
| A-4 | `personality_relief_hazard.atr14_prior` | TR then `rolling(14).mean()`, **`.shift(1)`** (PIT-safe prior) | `engine/personality_relief_hazard.py:210-220` |
| A-5 | `ohlc_reconstruct.atr_proxy` | Close-only proxy | `engine/ohlc_reconstruct.py:82` |
| A-6 | **`entry_signal._atr_pct`** | **NOT ATR** — `mean(abs(pct_change))` over 14 bars, ×100 | `engine/entry_signal.py:60-73` |

**A-6 is the trap.** It is named `_atr_pct` and sizes Prophet's buy zone / chase line / stop,
but it never touches high/low — the `high` argument is accepted and then deliberately unused
(`engine/entry_signal.py:67-71` explains the low series is not threaded through). It is a
close-to-close mean absolute return. Note also **none** of A-1..A-5 use canon's SMA-seeded RMA,
so no ATR here equals Pine `ta.atr`.

---

## 2 · `engine/entry_signal.py` — the boundary Prophet's gate must not cross

### 2.1 What it actually is

**`entry_signal.py` does NOT compute the confluence.** It is a *presentation + price-plan*
layer. It receives the gate verdict as a plain boolean keyword:

> `engine/entry_signal.py:148-159` — `assess(close, high, rec, *, buyable: bool | None = None)`;
> "``buyable`` is the MACD-2D x StochRSI-3D CONFLUENCE verdict
> (engine/signal_gate.is_buyable) for this name."

Its only use of `buyable` is a one-way demotion (`engine/entry_signal.py:193-195`): when
`buyable is False` and the cycle ladder says `buy_now`/`partial`, the status is downgraded to
`await_confluence`. It never upgrades, never re-derives, never inspects a timeframe.
`buyable=None` leaves it ungated (back-compat for markets without the gate wired).

Everything else it produces is derived from the daily close plus `rec["ladder"]`/`rec["cycle"]`:
buy zone, `chase_above`, `stop`, `atr_pct` (A-6), horizon reads `d3/d21/d63`, timing window.
Self-gates: no ladder state, or `< 60` closes → `None`, with a named reason from
`null_reason` (`engine/entry_signal.py:131-145`), which mirrors `assess`'s gates one-for-one.

### 2.2 Where the validated gate really lives

The MACD-2D × StochRSI-3D confluence is computed in **`engine/confluence_tiers.py`** and
adjudicated in **`engine/signal_gate.py`**:

- Tier table — `engine/confluence_tiers.py:12-16`:
  `T1` 0.90 = 3D MACD-RSI × 3D StochRSI, buy-filter endorsed (master; held-out stop-out 38.3%);
  `T2` 1.00 = 2D MACD-RSI cross & 3D StochRSI crossed recently (40.6%);
  `T3` 0.60 = 2D MACD-RSI projected ≤1-2d & 3D StochRSI already crossed (42.3%);
  `T4` 0.40 = 2D MACD-RSI projected & **2D** StochRSI crossed & above-200MA (43.1%).
- `BUYABLE_TIERS = ("T1", "T2", "T3")` — `engine/signal_gate.py:104`.
  **T4 is deliberately excluded** because it fires off the 2D StochRSI, not the 3D
  (`engine/signal_gate.py:102-103`).
- `is_buyable(v)` = `v["eligible"] and v["tier_cascade"] in BUYABLE_TIERS` —
  `engine/signal_gate.py:107-114`.
- Freshness: `FRESH_TICKS = 2` **on the signal's own timeframe** (a "tick" = one native bar:
  3 days on the 3D, 2 on the 2D) — `engine/confluence_tiers.py:60-65`.
  `EARLY_CROSS_BARS = 1.5` is the T3/T4 projection window (`:66`).
- The asymmetry is intentional: "the StochRSI sets up the zone (it need not be same-bar), the
  2D MACD cross is the freshness-gated trigger" — `engine/signal_gate.py:96-99`.

### 2.3 How 2D/3D bars are constructed (the PIT core)

`_tf_bars(daily, n, market)` — `engine/confluence_tiers.py:274-304`:

```
bucket(d) = session_anchor.session_positions(d, market) // n
```

- **Absolute session-calendar anchor**, not the caller's first timestamp. Era string
  `ANCHOR_ERA = "abs-session-2026-08-06"` rides on every verdict
  (`engine/confluence_tiers.py:54`). Ruling:
  `research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`.
- Aggregation rule: per-bucket **last close**, indexed by that bucket's **last session date**
  (`engine/confluence_tiers.py:286-290`) — so a downstream ffill can only reference a bucket
  at/after its close (leak-free).
- Why it exists: the old `resample("2B"/"3B")` anchored bins to the series' first timestamp, so
  one dropped leading bar flipped the tier on 13/232 names and the not-topped veto on 27/232,
  and the two production loaders disagreed on live buyability the same night
  (`engine/session_anchor.py:5-12`).
- The US reference calendar is **rules, not data** — `lib.nyse_calendar`, pure stdlib
  arithmetic, "immune to vendor-revision re-phasing" (`engine/session_anchor.py:20-26`).
  CN/HK/CA read a never-halting index instead; a missing reference **raises**, never falls back
  (`engine/session_anchor.py:28-33`).

**Two anchors coexist deliberately.** `canon.resample_sessions` (`engine/canon.py:365-398`)
buckets by *ordinal from the caller's first bar*; `_tf_bars` buckets absolutely. Measured
divergence: a 1-to-5-session leading drop moves a cascade field on **12.83%** of data/stocks
cases through the ordinal path and **0.00%** through the anchored one
(`engine/canon.py:380-384`; pinned by `tests/test_canon.py:237-338` §5b). Canon must not be
re-phased (its phase is part of the cross-repo golden-vector contract); the cascade must stay
absolute.

### 2.4 The exact interface Prophet consumes — what "do not modify" protects

Prophet's Door T is a *byte-unmodified* re-export of the gate:

> `engine/prophet_doors.py:565-570` — `door_t_fires(v)`: "Door T trigger leg: the incumbent
> VALIDATED construction, byte-unmodified." Returns
> `bool(v) and bool(v.get("eligible")) and signal_gate.is_buyable(v)`.

So the protected surface is exactly:

```
daily close ─► confluence_tiers._tf_bars (2D/3D, absolute anchor)
            ─► _stoch_rsi_kd + _rsi_macd  (RSI family R-B)
            ─► signal_gate.gate() → verdict dict {eligible, tier_cascade, ...}
            ─► signal_gate.is_buyable() → bool
            ─► prophet_doors.door_t_fires()          ← Prophet
               entry_signal.assess(buyable=...)      ← display/price plan
```

**Non-interference proof for the new program is therefore mechanical:** Live Entry Radar is
clear of Prophet's gate iff it (a) adds no import into `engine/entry_signal.py`,
`engine/signal_gate.py`, `engine/confluence_tiers.py`, `engine/signal_quality.py`,
`engine/prophet_doors.py`; (b) does not change `ANCHOR_ERA`, `BUYABLE_TIERS`, `FRESH_TICKS`,
`EARLY_CROSS_BARS`, or the frozen params at `engine/confluence_tiers.py:56-59`; and (c) writes
no key those modules read. A new module computing its own StochRSI in its own file cannot
affect Door T — the coupling surface is imports and the params block, nothing else.
`engine/washout_turn.py:1-5` is the house precedent for stating this ("Nothing in the pick
chain imports this module; this module imports nothing from prophet/board code").

---

## 3 · Prior entry-timing research + the registered kill

### 3.1 The Entry Stack expansion corpus

`research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md` (283 ln), `…AMENDMENT1…` (121),
`…AMENDMENT2…` (135), **`…AMENDMENT3_BY_FABLE.md` (308)** — plus 16 backing reports under
`research/entry_stack/` (notably `A3_HTF_REPORT.md` 634 ln, `A3_CANDIDATE_BOOK_DRAFT.md` 250 ln).

### 3.2 Washout DEPTH failed; turn/MOTION looked better

Verbatim, `research/entry_stack/A3_CANDIDATE_BOOK_DRAFT.md:20`:

> | Multi-TF stoch **washout DEPTH** behind a fire (incl. 2W deep) | **H1 FAIL** — +2.9pp clean15
> but **+3.5pp stop5**; `w2_deep ≈ 0 alone`; depth works only through the cohort lens (H6→COILED) |
> DURABLE_BOTTOM §8 ledger, WAVE1_REPORT §2 |

i.e. depth bought a marginally cleaner 15-day path at the cost of a **+3.5pp higher stop-out
rate** — the "increased stop burden" the program handoff refers to.

The motion side, `research/entry_stack/A3_CANDIDATE_BOOK_DRAFT.md:39`:

> Weekly TURN adds **+19pp held21** (68.4 vs 49.0) at state level; deep×reversing **+26pp**;
> **4-TF turn-confluence count monotone 43.7→61.4%** (BOTTOM_CONFIDENCE Ph1-2, 68,916 evals —
> state-level, held21, NOT fire-conditional, NOT ESX grader).

And the lesson, `research/entry_stack/A3_CANDIDATE_BOOK_DRAFT.md:62-65`:

> **at fire time, cycle-scale POSITION (depth/age/location) is dead or NC-2-confounded;
> cycle-scale MOTION (turn evidence) is a near-miss/validated-ingredient at state level, on
> blocked populations, and inside shipped chips (SHAKEN) — but never adjudicated on the
> gate-fire tape itself.**

Note the scope caveat carefully: the +19pp/+26pp/monotone numbers are **state-level, not
fire-conditional, and not on the ESX grader**. They motivate; they do not validate.

### 3.3 The registered kill — `DNR:KILL-WASHOUT-TURN`

`research/DO_NOT_REBUILD.md:83`, verbatim:

> `| KILL-WASHOUT-TURN | Washout × turn (2W operator seed) | KILLED — operator seed dies in test | Entry-stack Amendment-3 adjudication (#1747) |`

**What the "2W operator seed" was.** The operator's literal proposal: a **2-week (2W) / 1-month
StochRSI washout** — i.e. deep HTF oversold *position* — used **in interaction with a turn**, as
an entry condition layered on gate fires. `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md:271-272`
calls it "The operator's literal **'2W/1M StochRSI washout' seed**".

**What killed it.** Family `esx_washout_x_turn` (arm C),
`research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md:259`:

> | **C `esx_washout_x_turn`** | **KILLED** | The operator's literal 2W-washout × turn seed adds
> NEGATIVE marginal value once proximity is removed: nc2 kills contrast-i (−0.29pp CI incl 0)
> and the marginality interaction is adverse (+0.014 baskets / +0.024 deep). Re-confirms the H1
> depth kill fire-conditionally. |

The killing instrument is the **NC-2 proximity de-confound** mandated as a KILL-ARM by RUL-28
(`…AMENDMENT3…:65-68`): "The 63-bar close-min NC-2-PROXY band-FE arm is **mandatory in every A3
primary read as a KILL-ARM**: an effect that dies under proxy-FE is a proximity shadow —
buried." The seed's apparent edge was mostly *proximity to a recent low*, not washout×turn.

**Scope of the kill** (`…AMENDMENT3…:271-276`): dead in its **position form** and dead in its
**interaction form** (C KILLED, A3m monthly NULL-by-non-replication, A2 2W NULL) — but the
**motion form survives** on the broad tradeable universe (A1 weekly turn, baskets-only,
DISPLAY-CANDIDATE-CAVEATED, ~⅔ proximity, thin −0.83pp residual after nc2 FE; `…:255`).
Related registry rows to cite alongside: sector-level standalone washout→turn triggers are NULL
per Oracle P8 P-W1/S-W3 (`…AMENDMENT3…:20-23`).

### 3.4 The house template for distinguishing a new construction

There is an approved precedent for shipping a turn-family organ *without* reviving the kill —
`research/TURN_SENSITIVITY_UPGRADE_MASTERPLAN_BY_FABLE.md:46` (TS-R3):

> This is NOT a revival of the killed "Washout × turn (2W operator seed)" (**different
> construction: no washout precondition, no operator seed, per-stock granularity, K-of-N legs**)
> and is registered as an **expected-NULL forward meter** citing Oracle P8 P-W1/S-W3 +
> DO_NOT_REBUILD §2.

Live Entry Radar's contract should carry the same four-part distinction plus an explicit
nc2-proximity arm, and — per the epistemics law — ship display-tier while it accrues.
Other rows that cite this kill and model the citation idiom:
`research/MAG7_WASHOUT_REENTRY_PREREG.md:292`,
`research/CHINA_STANDOUT_DOUBLE_CONFLUENCE_MASTERPLAN_BY_FABLE.md:155`,
`research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md:59-61`.

---

## 4 · Daily OHLCV data plane

*(This worktree is a SPARSE checkout — `data/` and `site/` are absent locally. Counts below
come from `git ls-files` in this worktree and a read-only `ls` of the primary checkout at
`/Users/chriswong/Documents/Cluade/Macro Dashboard/data/`, never from a failed local read.)*

**Vendor + adjustment basis.** yfinance, `auto_adjust=True` —
`collectors/_stock_ohlc.py:52-56`, documented at `:92` as "the dividend/split-ADJUSTED
total-return plane". So the daily plane is **split AND dividend adjusted**, which
`engine/prophet_live/live_states.py:136-138` independently confirms ("the nightly store's
SPLIT+DIVIDEND ADJUSTED close series").

**Canonical accessor.** `lib/store.py:36 read(group, name)`; writes go through
`lib/store.py:60 upsert(...)`.

**The adjustment hazard is already documented and already bites indicators** —
`lib/store.py:64-77`:

> "`overwrite_overlap=True` — for DIVIDEND/SPLIT-ADJUSTED series (yfinance `auto_adjust=True`).
> An adjusted history is a coherent whole: after an ex-dividend every prior bar is re-scaled…
> Plain `combine_first` keeps old values wherever the fresh pull did not re-cover them, leaving
> a PERMANENT basis STEP at the refresh edge (measured 17/300 A-share names >0.4%, worst 40%,
> May-dividend clustered) that seasonally biases rev_z and **can fabricate MACD/StochRSI
> crosses**."

Related guards: `lib/store.py:106 basis_shifted(...)` detects a re-adjusted basis;
`collectors/yahoo.py:226-235` re-pulls `period='max'` for any name that shifted, so the whole
store rebases in one shot; `collectors/breadth.py:36` records that "yfinance `auto_adjust` back-adjusts
ONLY the window it downloads". **This is the single most under-appreciated parity risk for a
live entry system**: a corporate action silently re-scales the entire history under the
indicator.

**Coverage breadth — two equity stores with different depth.**

| Store | Tracked (`git ls-files`) | On disk (primary) | Depth |
|---|---|---|---|
| `data/stocks/` | 240 | 229 | deep history, **1960s-start** |
| `data/baskets/ohlcv/` | 2779 | 2519 | **2014-start** |

Depths per `engine/session_anchor.py:8-9`. The tracked-vs-disk gap is unexamined here
(**UNVERIFIED** — likely delistings/gitignored rows, not a defect claim).
These two loaders are **known to have disagreed on live buyability the same night**
(NUE/PEP/WMT buyable from one store only; ECL/SW inverted) — that disagreement is precisely
what the absolute session anchor was built to fix (`engine/session_anchor.py:5-12`, §2.3).
Live Entry Radar must pin which store it reads and disclose it.

**Intraday bar data: NO — not for US equities.** Verified three ways:

1. Interval-argument sweep across `engine/`, `scripts/`, `collectors/`, `lib/` returns exactly
   **one** hit: `scripts/commodity_sentinel.py:40` (`interval="60m"`, commodities).
2. The store's own intraday affordance (`normalize_index=False`, "preserves intraday timestamps
   (hourly candles)", `lib/store.py:63`) has exactly **two** callers:
   `scripts/vector_sentinel.py:63` → `coinbase/btc_hourly`, and
   `scripts/commodity_sentinel.py:75` → `commodity/{asset}_hourly`.
3. `engine/thetadata_store.py` is **EOD options** data, not intraday equity bars — layout
   `{THETADATA_STORE}/eod/{ROOT}/{YYYY}.parquet`, tiers `("eod", "oi", "greeks")`
   (`:4`, `:96`).

So: hourly bars exist for **BTC and commodities only**. There is **no minute, hourly, or 4H
equity bar store**, and therefore no existing basis for a 4H equity timeframe. The live equity
plane is **delayed quote SNAPSHOTS**, not bars (§6) — a last price, not an OHLCV series.

**Consequence for Live Entry Radar:** the requested 4H timeframe has **no data source in this
repo today**. It must either be sourced new (a vendor decision, with its own adjustment basis
to reconcile against the adjusted daily plane) or the 4H tier must be dropped/deferred from the
frozen contract. This is a PR-0 blocking finding, not a build detail.

---

## 5 · Session calendar

**All calendar logic is hand-rolled stdlib.** `pandas_market_calendars` and
`exchange_calendars` are used nowhere and are absent from every `requirements.txt`.
Timezones are stdlib `zoneinfo` — "Stdlib zoneinfo (repo convention) — no pytz"
(`scripts/live_breadth_poller.py:69`).

| Module | Covers | Grade |
|---|---|---|
| **`lib/nyse_calendar.py`** (625 ln) | Rule-computed NYSE holidays (MLK, Presidents, Good Friday, Memorial, Juneteenth, Jul 4, Labor, Thanksgiving, Christmas + observance shifts); `ONE_OFF_CLOSURES` (3: 2012 Sandy, 2018 Bush, 2025 Carter); session-gap API `session_n_back/forward`, `sessions_between`, `sessions_apart` (`:469-624`) | **Real.** Explicitly does **not** model early closes (`:10-13`) |
| **`engine/session_digest.py`** | `SESSION_OPEN_ET` 9:30 / `SESSION_CLOSE_ET` 16:00 / `EARLY_CLOSE_ET` 13:00 (`:170-176`); `is_early_close()` (`:199-226`); `session_window_et()` (`:229-239`) | **Real, DST-safe** (localizes wall-clock onto the date). The only early-close model |
| `lib/hk_calendar.py` (283) / `lib/cn_calendar.py` (202) | Mirror nyse_calendar's `is_session`/`holidays`/`expected_last_session` shape; **separate modules, no shared rule engine**. CN is deliberately minimal + a `MAX_LEGIT_CLOSURE_DAYS = 11` backstop (`cn_calendar.py:16-28,53`) because the State Council sets spans annually | Real |
| `engine/marketing/market_clock.py:108-217`, `engine/rebalance_calendar.py`, `engine/source_registry.py:236-249`, `engine/earnings_catalyst.py:96-114` | Session-day arithmetic built on `lib.nyse_calendar` | Real |
| `pd.offsets.BDay()` — dozens of sites | Holiday-**blind** weekday arithmetic for non-critical lookbacks; self-labelled (`engine/earnings_blackout.py:102` "KNOWN IMPRECISION"; `engine/neuralweb/context_api.py:152` "holiday-agnostic") | Naive |

**Reach:** ~110 distinct files import `lib.nyse_calendar` (404 text occurrences across
`engine/`+`scripts/`+`app/`). The nightly `daily.yml` depends on it transitively through dozens
of `scripts.build_*` jobs and directly via `scripts.build_session_digest` (`daily.yml:3622`);
the render lane imports it at `scripts/build_site.py:74`; Prophet consults it in
`engine/prophet_bridge.py`, `engine/prophet_live/{armed_pack,live_states}.py` and raises
`ContractError` on "not an NYSE session" (e.g. `engine/options_signal_episode.py:620`).
Critically, it is the reference calendar behind the 2D/3D anchor (§2.3,
`engine/session_anchor.py:20-26`).

**Intraday session clock: YES, but fragmented and partly holiday-blind.**
Holiday-aware `pre|rth|post|closed` state machines exist at
`scripts/build_basket_pulse.py:158-214` (US+HK, calls `is_session()` first),
`scripts/chain_snapshot_poller.py:1462-1541` (with bar-close bucket boundaries and sub-minute
grace), and `scripts/build_prophet_marks.py:206-213`.
**Holiday-BLIND** RTH checks — verified directly — at
`scripts/live_breadth_poller.py:138-169` (`session_tag`: bare `et.weekday() >= 5` + minute
arithmetic; the file does not import `nyse_calendar` at all),
`scripts/live_flow_poller.py:2712-2725`, `engine/live_quotes.py:51-66`, and
`engine/live_overlay.py:129-160` (self-labelled "ADVISORY hint only — no exchange holiday
calendar and no half-days"). These would treat a weekday market holiday as open.

**There is no canonical "now in ET" helper.** 27+ modules independently define
`ET = ZoneInfo("America/New_York")` and several re-implement a private `_et()`/`_now_et()`
normalizer. `engine/marketing/market_clock.py:20-22` records the precedent: "Nine separate sites
had independently re-implemented `weekday() >= 5`... not one of them was holiday-aware."

---

## 6 · Existing live / provisional-intraday computation

**Yes — a live lane exists, and it deliberately does NOT recompute indicators intraday.**

`engine/prophet_live/` — `armed_pack.py` (1011 ln), `interval.py` (317), `live_states.py` (988),
`r2io.py` (163). Schedule: `.github/workflows/prophet-live.yml:65-67` — every 5 minutes,
13:25Z through 21:15Z, Mon-Fri (US RTH plus edges).

**The architecture (this is the key precedent for Live Entry Radar):**

> `engine/prophet_live/armed_pack.py:3-8` — "For every name in the scored universe it re-runs the
> SAME close-only admission gate (`engine.signal_gate.gate`) with candidate provisional closes
> appended as tonight's new session bar, and records the price interval over which
> `engine.signal_gate.is_buyable` is true. **The */5 intraday lane then only has to compare a
> delayed live price to those two numbers — it never re-derives a signal.** The pack is an
> OPTIMIZATION; the gate is the truth."

So the house pattern for "live" is **nightly price-threshold inversion**, not intraday indicator
recomputation. The intraday lane does no math on bars at all.

`probe_series(close, candidate)` — `engine/prophet_live/armed_pack.py:225-243` — appends the
candidate as the **NEXT session's bar** (label from `next_session_stamp`, the repo NYSE
calendar), never overwriting the as-of close. This is measured, not assumed: switching from
replace-semantics to append-semantics changed the answer for **45 of 180 probed names** and moved
the armed count 98 → 68 (`armed_pack.py:20-25`) — because replacing froze series length,
session-anchor bucket positions and freshness tick counts at yesterday's values.

**Price-basis hazard, already solved once here** —
`engine/prophet_live/live_states.py:136-147`:

> "ONE PRICE BASIS (W-L0 gate 3). The armed levels are prices on the nightly store's
> **SPLIT+DIVIDEND ADJUSTED** close series; ``price`` on every row is a **RAW vendor print** off
> the live plane… the live quote is deliberately NOT converted — an adjusted 'quote' is a number
> no exchange ever printed."

Reconciliation is a per-name assertion every pass (`interval.basis_audit`): the pack's
`as_of_close` vs the feed's `prev_close`; past `basis_tolerance_pct` the name goes `dark` with
reason `basis_mismatch`. Live states are graded `live / delayed(~Nmin) / last_rth / eod / dark`
(`live_states.py:20`, and the honest-delay law TS-R1 at
`research/TURN_SENSITIVITY_UPGRADE_MASTERPLAN_BY_FABLE.md:44`).

**Partial-bucket provisional values do exist** on the daily grid:
`engine/confluence_tiers.py:664` refers to "the partial bucket `_tf_bars` still emits — the
live board's provisional basis. The last row…". So a 2D/3D bucket in progress *is* published as
provisional from daily closes; there is still no intraday bar feeding it.

Other HTF oscillator lanes that compute a *daily-grid* provisional of a higher timeframe:
`engine/htf_oscillators.py:51-92 stochrsi_2w` (2W StochRSI on the epoch-anchored biweekly close,
reusing `signal_quality._stoch_rsi_kd`), and `engine/oracle/oscillators.py:110+
weekly_stochrsi_kd` (W-FRI, ffilled onto the daily index, **in-progress week excluded**).

**A 2W-grid contradiction to avoid inheriting:** `engine/htf_durability.py:102-115
_biweekly_close` states "MUST NOT use `resample('2W-FRI')` — that bins are calendar-anchored and
drift with as-of date, making backtest != live", and uses a fixed-epoch week-pair anchor with
only COMPLETED pairs. But `engine/momentum_events.py:149,166` does exactly that
(`close.resample("2W-FRI").last()`) for its `stoch_events_2w` family. Two live 2W grids, one of
which the other calls unsafe.

---

## 7 · Boundary addendum — the market-timing-intelligence parent program

Implementation roots named for the parent program: `engine/stock_personality.py` (1129 ln),
`engine/ignition_radar.py` (1137 ln), `engine/setups.py` (293 ln).

### 7.1 `engine/ignition_radar.py` — what it detects today

Risk-**ON** mirror of the Risk Radar (点火雷达). **DISPLAY-ONLY, FORWARD-GRADED, NOT VALIDATED**;
"nothing here is a buy signal" (`engine/ignition_radar.py:1-4`). Two channels, never fused:

- **BROAD** — a K-of-8 confluence *count*: 4 catalyst chips reused from
  `engine.risk_radar_market_catalysts.compute()` (`c1_thrust_confluence`, `c2_msi_swing`,
  `c3_washout_thrust20`, `c4_ftd`) + 4 participation confirms computed locally
  (`pct50_recover`, `nh_flip`, `rsp_confirm`, `sector_participation`) — `:5-17`.
  Thresholds `_K_IGNITED = 3`, `_K_WARMING = 1` (`:44-45`).
- **NARROW** — `compute_basket_ignition` per US thematic basket + 11 sector ETFs + SMH (`:18-20`).
- Output: `data/ignition_radar/latest.json`; regime label `ignited / narrow / warming / off`,
  bilingual (`:21-25`).

**Grain is MARKET and BASKET, never per-name.** It has no StochRSI, no per-ticker entry timing.

### 7.2 `engine/setups.py` — what it does today

Cross-sectional **setup scoring**: selection (sector-neutral residual alpha from
`engine/residual_alpha`) × timing (`engine/cycles` + the alpha engine's reversal overlay) —
`engine/setups.py:1-10`. Explicitly "**NOT a new statistical edge**"; the honest claim is
confluence, not a fresh signal (`:6-10`). Per-market alpha weights `US 0.7 / CN 0.35 / CA 0.55`
(`:29-31`). It is a **consumer of the Prophet gate**, not a competitor: the US "Top setups"
buy shortlist is gated on `signal_gate.is_buyable` (`:240-245`), and it reads
`entry_signal.assess()["status"]` (`:270`).

### 7.3 `engine/stock_personality.py`

Per-ticker `stock_personality.v1` label assembly. **DISPLAY-ONLY, PURE** (no I/O, all inputs
precomputed by the caller); "Never scores, sizes, or gates positions"; authority
`may_rank/size/gate=False` (`engine/stock_personality.py:1-18`). Exposes
`setup_compatibility(personality, species_entries)` — a natural place for a new entry species to
be *described*, not gated.

### 7.4 Where the real collision is

**Not `ignition_radar`.** Despite the name, it is market/basket-grain regime breadth; the only
washout-shaped element is `_c3_washout_thrust20`, a **breadth** chip (`%>20dma washout→thrust`,
computed off `data/breadth/_closes_cache.parquet`) —
`engine/risk_radar_market_catalysts.py:312-320`. Different grain, different input, no overlap
with a per-name entry detector beyond vocabulary.

**The real collision is `engine/washout_turn.py`** — an existing **per-name weekly washout-turn
watch organ (US)**, display-tier, zero authority (`engine/washout_turn.py:1-4`). It exists
because MCD printed a weekly RSI-MACD bullish cross at the 6.3rd percentile of its own weekly
line history since 1968 and no organ consumed weekly-grain confluence per name
(`:6-16`). It writes `site/stockdata/washout_turn.json`, `data/washout_turn/ledger.jsonl`, and
`rec["washout_turn"]` (`:18-22`), and it uses **canon math only** (R-A) (`:24-33`).
Its own charter already records the kill boundary:
`research/washout_turn_name_lane/MCD_MISS_EVIDENCE_2026-08-05.md:76-77` — "Scored washout→turn
constructions remain NULL/killed per Oracle P8 P-W1/S-W3 and Entry-stack Amendment-3 #1747 —
this lane ships display-tier watch vocabulary only."

`engine/mtf_upturn.py` (TS-R3, §3.4) is the second adjacency: a per-stock multi-TF upturn
organ with K-of-N legs, display tier, registered expected-NULL.

**Contract implication.** The frozen contract must draw its boundary against
`engine/washout_turn.py` and `engine/mtf_upturn.py` (same grain, same family, overlapping
vocabulary), and merely *note* `ignition_radar` as a name collision at a different grain.
`setups.py` and `stock_personality.py` are downstream consumers — the boundary there is
"Live Entry Radar may be read by them; it must not write into their scoring".

---

## 8 · Top risks for indicator parity

1. **RSI-family split (R-A vs R-B).** Five modules import the bare-`ewm` RSI under a comment
   claiming it is Pine `ta.rsi`. The shipped gate runs R-B; canon and `washout_turn` run R-A.
   Any new "StochRSI" that does not name its family will silently match one and diverge from the
   other near threshold crosses — which is exactly where entries fire.
2. **Two legitimate session-bucket anchors.** Ordinal (`canon.resample_sessions`) vs absolute
   (`confluence_tiers._tf_bars`), measured 12.83% vs 0.00% verdict movement under a leading-bar
   drop. Live Entry Radar must adopt the **absolute** anchor and mint its own era string; it must
   not delegate either direction (`tests/test_canon.py:237-274`).
3. **Adjusted-vs-raw price basis at the live edge.** Nightly closes are split+dividend adjusted;
   live quotes are raw vendor prints. Any intraday indicator (as opposed to a precomputed
   threshold) must reconcile per name or it silently drifts across every corporate action —
   the existing lane solves this only because it never recomputes (`live_states.py:136-147`).
4. Secondary: `postcross`'s `+1e-10` flat-window policy (false-oversold, §1.2), the
   `adjust=True` EMA in `coiled` and the missing `min_periods` in `postcross` (§1.3), the
   `_atr_pct` misnomer (§1.5 A-6), and the live 2W-grid contradiction (§6).
