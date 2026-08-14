# Track A — Grey Dot forensics & cross-repo parity (Live Entry Radar PR-0)

Read-only archaeology of the Terminal repo `/Users/chriswong/Documents/Cluade/charting-app`.
Every load-bearing claim carries a `file:line` receipt. `UNVERIFIED` marks anything inferred.

## §0. READ THIS FIRST — the checkout is a month stale

`charting-app`'s working tree is branch `claude/terminal-audit-fixes-20260713` @ `687da219`
(2026-07-13); the canonical tip is `origin/master` @ `82cb8cbf` (2026-08-13). The entire
amber-EARLY / bottom-watch / point-in-time layer landed in `935389d4` "Surface early bottom
entries and durable Prophet receipts (#392)" (2026-08-11) — **not in the working tree**
(`signal_layer/confluence_v2.py` 562 ln @HEAD vs 1211 ln @origin/master). Citations: `@om:N` =
line N of `git show origin/master:<path>`; `@HEAD:N` = the stale tree. **Anyone reading the
checked-out files is reading a superseded, leak-carrying G0.**

## §1. G0 — exact math, constant by constant

Entry `signal_layer/confluence_v2.py@om:643 early_dots()` → `@om:600 _early_dot_mask()`; input
frame from `signal_layer/confluence.py@om:240 compute_signals()`.

### 1.1 Bar construction

**3D bars — session-grouped, NOT calendar** (`confluence.py@om:146-163 _3d_groups`): sessions
numbered from the symbol's first listed session (`gi = arange(n) + bar_anchor`, `@om:156`); a bar
OPENS the session after any session whose global index `% 3 == 0` (`@om:159`) and CLOSES the
session before the next opens (`@om:161`). Bar value = **close of its last session**
(`@om:162-163`); the frame is **indexed by the bar's OPEN date** (TradingView's timestamp,
`@om:250-253`). Rationale `@om:166-179`: `resample("3B")` buckets by the Mon–Fri calendar and
"relocated ~80% of NVDA's signal dates" (`@om:44-45`). Needs ≥90 3D bars else empty (`@om:251`).

**2D bars — calendar, deliberately different from 3D** (`confluence_v2.py@om:620`):
`dc.resample("2B").last().dropna()` on the DAILY close — left-edge label, anchored to the first
daily row, empty buckets dropped. Availability is computed separately as the bucket's **last
actual session**, `dc.index.to_series().resample("2B").max()` (`@om:623`), `NaT` dropped
(`@om:624-626`). Partial in-progress buckets are not suppressed: a live half-bucket is usable the
day it prints.

**Price source is CLOSE ONLY** — `s3` is built from `daily_close` (`confluence.py@om:250-253`);
"Every stream is **close-only-safe** (no intrabar OHLC required)" (`confluence_v2.py@om:26-27`).

### 1.2 Oscillators

Constants, one block (`confluence.py@om:57-64`): `RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14,
60, 5`; `STOCH_RSI_LEN, STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 14, 3, 3`; `OB, OS = 80, 20`;
`CONF_W = 8`.

* **RSI** (`@om:89-101`) — Wilder, `n=14`, on the **3D close series** `s3`; `_rma` (`@om:68-86`) is
  **SMA-seeded** (mean of first 14 valid) then recursive `α=1/n` (the header notes
  `ewm(alpha=1/n, adjust=True)` does NOT match Pine and flips near-threshold crosses, `@om:70-74`);
  mask `dn == 0 → 100.0` (`@om:101`).
* **StochRSI** (`@om:119-127`) — stochastic OF that RSI: `lo/hi = r.rolling(14).min()/.max()`
  (`@om:122-123`); `rawk = (r-lo)/(hi-lo)*100`, `(hi-lo)==0 → NaN` (`@om:124`);
  `k = rawk.rolling(3).mean()` (`@om:125`); `d = k.rolling(3).mean()` (`@om:126`).
  **NaN policy:** no `min_periods` override anywhere in the chain ⇒ pandas' default
  `min_periods = window` ⇒ `k` NaN until 14 valid RSI + 3, `d` until +3 more. `_early_dot_mask`
  hard-drops NaN rows (`dropna(subset=["macd","sig","k","d","rsi14"])`, `confluence_v2.py@om:611`)
  and bails if `len(rows) < CONF_W + 2` i.e. < 10 (`@om:612-613`).
* **RSI-MACD** (`@om:111-116`) — **MACD of the RSI, not of price**:
  `macd = ema(rsi(x,14),14) − ema(rsi(x,14),60)`, `sig = ema(macd,5)`; `ema` =
  `ewm(span, adjust=False)` (`@om:104-108`). The 12/26/9 `_f_macd` at `confluence_v2.py@om:392`
  is a *different* function used only by the recipe score — **G0 never touches it.**

### 1.3 The three legs (on the dropna'd 3D rows)

```
stoch_bull = crossover(k, d)                         # confluence_v2@om:616
from_os    = d.rolling(CONF_W).min() < OS            # confluence_v2@om:617
rising2    = (m2 - s2) > (m2 - s2).shift(1)          # confluence_v2@om:627-628
dot        = stoch_bull & from_os & mapped(rising2)  # confluence_v2@om:640
```

* **"Bullish cross"** = `crossover` (`confluence.py@om:130-131`):
  `(a > b) & (a.shift(1) <= b.shift(1))` — **strict `>` now, NON-strict `<=` prior.** K over D,
  one bar, no confirmation.
* **"From oversold"** = `d.rolling(8).min() < 20` — the **D line only** (never K, never both),
  strict `<`, threshold `OS = 20`, window `CONF_W = 8` **3D bars inclusive of the current bar**
  (≈24 sessions); default `min_periods=8` ⇒ first 7 rows False. Named as the oracle's
  `b1_from_os` primitive (`confluence_v2.py@om:649-650`), the same primitive gating the oracle's
  confirmed BUY (`confluence.py@om:283`).
* **"2D RSI-MACD histogram rising"** = `hist = macd − signal` on the 2B series, then
  `hist > hist.shift(1)` — **strictly greater, exactly ONE bar of lookback**, `.fillna(False)`
  (`confluence_v2.py@om:627-628`). No magnitude floor, no run-length, no sign requirement: the
  histogram may be deeply negative and still qualify.

### 1.4 Point-in-time availability (the `known_at` rule)

`compute_signals` now emits `known_ts` — "the session on which each bar's current value became
knowable" = the bar's CLOSE session (`confluence.py@om:242-243, 322-328`), whose comment states
the hazard: "For the live incomplete 3D bar this advances each session; a signal printed on Jul 28
inside a Jul 24-opened bar must not be presented as knowable on Jul 24." `_known_dates`
(`confluence_v2.py@om:590-597`) reads it with a fallback to the chart label. The 2D→3D join
(`confluence_v2.py@om:630-638`):

```
rising_known = Series(rising2, index=known2)                 # relabel by LAST ACTUAL SESSION
rising_known = rising_known[~dup].sort_index()               # dedupe, keep last
pos = rising_known.index.searchsorted(row_known, "right")-1  # newest 2D state known at 3D close
mapped[pos < 0] = False
```

**Rule in one sentence: a higher-timeframe bar becomes usable on the last real trading session
inside it, and each 3D row consumes only the newest 2D state whose availability date is ≤ that 3D
row's own `known_ts`.**

**The replaced bug is documented in-code** (`confluence_v2.py@om:603-606`): "The 2B resample label
is the LEFT edge of a pandas bucket, not the date on which the bucket's last price was observable.
Mapping that label directly onto a 3D bar lets a later 2B close leak backwards." The stale
checkout still carries the leaking form (`confluence_v2.py@HEAD:374`). Regression test:
`tests/test_bottom_watch_lane.py@om:53-55` — "A 2B bucket labelled Jan-13 closes Jan-14; Jan-13
must not see its rising hist."

**Residual PIT trap for Radar:** the emitted event `ts` is still the 3D bar's **OPEN** date
(`confluence_v2.py@om:653`), up to 2 sessions before its `known_ts` (measured: NVDA `2026-01-21`
→ `2026-01-23`; NFLX `2026-06-26` → `2026-06-30`). A consumer treating `ts` as the decision date
backdates the signal by 1–4 calendar days.

### 1.5 The ~4.6-day docstring, verbatim

`signal_layer/confluence_v2.py@om:644-651` (identical at `@HEAD:352-359`):

```
"""GRID_GATE anticipation form (a) — the EARLY pre-cross dot (~4.6d lead, hollow):

    3D StochRSI **bull cross from oversold**  AND  the 2D RSI-MACD histogram is
    **RISING** (pre-cross momentum).

"From oversold" = the 3D StochRSI D dipped below OS(20) within the last CONF_W bars
(the oracle's ``b1_from_os`` primitive). All math is the ORACLE's. Close-only-safe.
Returns the list of 3D-open-date strings on which the dot fires (chronological)."""
```

**The "4.6d" number is not sourced in the Terminal repo.** The nearest published figure is in the
Macro repo, where the detector is named `m2d_s3d_early`:
`research/signal_engine/CONFLUENCE_TUNING.md:105` gives **"+4.89 d"** under *"days earlier
(mean)"* vs the `base3d` confirmed buy at **coverage of base moves = 49.9%** — a matched-pair mean
over the ~half of base moves it anticipates, **not** "every dot precedes a buy by 4.6 days".
`CHARTER.md:199` quotes the mechanism as "~5 trading days" and adds that acting on it early was
empirically WORSE entry quality (deeper drawdown). Treat "~4.6d" as a paraphrase of a superseded
study — `UNVERIFIED` as stated.

## §2. Emitter / glyph trace

### 2.1 Event type and side channel

`build_v2` (`confluence_v2.py@om:1072`) is the sole emitter. At `@om:1170-1179`:

```python
bottom_watches = bottom_watch_events(sig, close, high=high, low=low)
promoted_dot_dates = {str(w.get("ts")) for w in bottom_watches if w.get("kind") == "early_dot"}
# A deep-washout anticipation dot now has a proper amber EARLY marker. Keeping the old
# gray side-channel dot underneath it would show one event twice and preserve the exact
# ambiguity this lane removes. Ordinary anticipation dots remain unchanged.
unpromoted_early_dots = [ts for ts in early_dots(sig, close) if ts not in promoted_dot_dates]
```

**That is the operator's comment, verbatim, at `signal_layer/confluence_v2.py@om:1174-1176`.**

Two emissions result. (i) `early_dots: [<YYYY-MM-DD>...]` — a bare **date-string side channel**,
last 40 (`@om:1201`, cap `SIDE_CHANNEL_CAP = 40` `@om:64`), re-capped to 40 in the doc
(`contracts.py@om:185,214`) and to 12 in the model slice (`@om:642`); **no signal type, no price,
no quality** — not a member of the unified signal stream. (ii) `bottom_watches: [...]`
(`@om:1204`) → `contracts.py@om:348-378` stamps `type="BOTTOM_WATCH"`, `scored=False`,
`subtype ∈ {early_dot, blocked_trigger}`. Schema: `contracts/indicator.v1.schema.json@om:133`
enumerates `BOTTOM_WATCH`; `@om:231` "False on display/watch-only events"; `@om:238`
"anticipation-dot origin or raw blocked CB/revBuy origin"; `@om:260` the washout facts block.

### 2.2 Rendering (frontend = `terminal/`)

**Grey dot (ordinary, unpromoted)** — `terminal/components/ChartPanel.tsx@om:3845-3855`:

```
if (showDetailRef.current) {                                // "Signals detail" chip, @om:3845
  const g = mk("g", { opacity: 0.55 });                     // @om:3852
  g.appendChild(mk("circle", { cx: x, cy: y + 9, r: 2.2, fill: t2.mut }));   // @om:3853
```
Circle, r = **2.2 px**, group opacity **0.55**, **9 px below the bar LOW** (`y = yOf(b.l)`,
`@om:3851`), fill `t2.mut` = CSS `--muted` = **`#717a8e`** (`terminal/app/globals.css:9`).
Bar-snapping in `resolveSideChannels` (`@om:2373-2379`); cleared on non-daily TFs (`@om:7048`).

**Amber EARLY marker (washout-promoted)** — `ChartPanel.tsx@om:3538`:
`BOTTOM_WATCH: { dir: "up", fill: t2.signal, tc: "#231800", txt: "EARLY" }` — an **up-pointing
marker with the literal text label `EARLY`**, fill `t2.signal` = `--signal` = **`#e8b339`**
(`globals.css:14`). Verdict chip `@om:2462`: `v === "BOTTOM_WATCH" ? "EARLY"`.

### 2.3 Git history of the grey→amber change

`935389d4` (2026-08-11, PR #392) is the **only** commit introducing the promotion: touched
`confluence_v2.py` (+351), `contracts.py` (+105), `ChartPanel.tsx` (+100), `OracleDash.tsx`
(+115), `indicator.v1.schema.json` (+62), added `tests/test_bottom_watch_lane.py` (236 ln).
Pickaxe `git log --all -S"gray side"` returns exactly it and its pre-squash twin `02d302a3`. The
grey-dot render itself is unchanged since the `9ef273b4` VPS snapshot
(`git log -L 2182,2192:terminal/components/ChartPanel.tsx@HEAD`). Earlier "amber" commits
(`397700aa` #375, `07244dff` #376, `e152fd85` #378) are the **washout-override** ⊘/star classes —
a different lane, not the anticipation dot.

### 2.4 Does a grey dot still render today? YES

Only washout-context dots are promoted; every ordinary dot still emits into `early_dots` and still
paints the `#717a8e` circle. Measured (§2.6): NVDA 8 dots ≥2025 with **0** promotions; TSLA 10
dots, **0**; NFLX 11 dots with only **3** promoted. Grey remains the dominant form.

### 2.5 Verdict — "operator's grey dot == this event": **HIGH confidence**

It is the *only* grey/muted dot rendered by the chart's signal layer; positioned below the bar as
an anticipation mark distinct from the BUY ▲ (`@om:3846`); the in-code name for the class is
literally "the old **gray** side-channel dot" (`@om:1175`); and the description matches the
operator's. No competing grey marker exists in `ChartPanel.tsx`. Residual risk: he may be
recalling the pre-#392 rendering, in which case some remembered dots are now amber. Definitive
confirmation needs (a) the operator naming one dated dot on one symbol and (b) that date appearing
in that symbol's `early_dots` / `bottom_watches` — one lookup, no new code.

### 2.6 Fired dates — ACTUALLY RUN (2026-08-13)

No CLI or artifact emits these: `signal_layer`'s only `__main__` is `confluence.run()`
(`confluence.py@om:425-449`), which prints backtest tables, not dots; `web/mockup/data/NVDA.slice.json`
is a slim 2026-06-18 mockup with no `early_dots` key. Cheapest real path (≈40 s, no new tooling):
stage `git show origin/master:signal_layer/*` into a temp dir and call the shipped functions —
`compute_signals(pd.read_parquet(DATA/f"{t}.parquet")["close"].dropna())` → `early_dots(sig, c)`.
Deep store spans NVDA 1999-01-22→**2026-07-08** (stale ~5 weeks). `SIGNAL_ERA = gc_v2_wo2`. Dates
are 3D bar **OPEN** dates (§1.4).

| ticker | `early_dots` ≥2025-01-01 (all-history n) | `bottom_watches` ≥2025 (ts / known_ts / kind) |
|---|---|---|
| NVDA | 2025-01-17, 2025-03-12, 2025-09-11, 2025-09-29, 2025-12-02, 2025-12-18, 2026-01-21, 2026-07-07 (n=135) | none (n=27 all-history) |
| NFLX | 2025-01-17, 2025-03-17, 2025-04-10, 2025-08-04, 2025-11-05, 2025-12-23, 2026-02-06, 2026-02-25, 2026-05-18, 2026-06-09, 2026-06-26 (n=132) | 2026-02-06/02-10/early_dot · 2026-02-20/02-24/**blocked_trigger** · 2026-02-25/02-27/early_dot · 2026-06-26/06-30/early_dot (n=22) |
| TSLA | 2025-01-16, 2025-02-12, 2025-03-11, 2025-04-09, 2025-07-11, 2025-08-11, 2025-11-20, 2026-02-05, 2026-02-24, 2026-03-30 (n=80) | none (n=9) |

Empirical lead, dot → next `CB|revBuy` within 30 sessions: **mean 12.7 / median 12.0 sessions**
(n=190 across the three names). This does not refute "+4.89d" — that is a *matched-pair* mean at
49.9% coverage, while this charges every dot to the next buy at any distance — but **"~4.6d lead"
must not be quoted as the Radar's expected lead** without re-deriving under a declared matching
rule.

## §3. Bottom Watch lane (challenger C5)

`confluence_v2.py@om:686-716 washout_context()` + `@om:756-805 bottom_watch_events()`; frozen
constants `@om:72-77`. **Washout context = W1 ∧ (W2a ∨ W2b) ∧ W3**, on the dropna'd 3D rows
(`@om:696-705`):

| leg | definition | receipt |
|---|---|---|
| W1 | `sig["bear_block"]` — monthly RSI-MACD bear **and** below the 200-day MA **and** 2W RSI-MACD not bull | `confluence.py@om:315`; used `confluence_v2.py@om:704` |
| W2a | `close3 / close3.rolling(84, min_periods=20).max() − 1 ≤ −0.35` (84 3D bars ≈ 252 sessions) | `@om:73-74`, `@om:701` |
| W2b | prior-closed **monthly** StochRSI-D `< 20` for `≥ 3` consecutive months | `@om:75`, `@om:702`, dwell `@om:430-436` |
| W3 | `d.rolling(8, min_periods=1).min() < 20` — a 3D StochRSI-D oversold visit in the last 8 bars | `@om:76`, `@om:703` |

W3 uses `min_periods=1`, unlike G0's `from_os` (defaults to 8) — early history qualifies here but
not there. **Monthly PIT** (`@om:657-683`): `resample("ME").last()`, dwell `.shift(1)`
(prior-closed month), **relabelled by the bucket's last actual session** (`@om:669-672`), joined by
`searchsorted(row_known, "right")-1` — same discipline as §1.4, because "`resample('ME')` uses a
calendar month-end label that may not be a session" (`@om:661-663`).

**Emission** (`@om:774-804`): candidates = `(early_dot_mask | trig) & washed`, where
`trig = (CB | revBuy) & washed` (`@om:715`). `trig` true → `kind="blocked_trigger"`,
`quality="washout_trigger_watch"` (the stronger subtype; it **de-duplicates** an anticipation dot
on the same bar, `@om:765-766`); else `kind="early_dot"`, `quality="washout_early_watch"`. Each
event carries `ts`, `known_ts`, `trigger_ts`, `trigger_known_ts`, `price`, **`scored: False`**
(`@om:799`), and `washout_ctx` with the frozen rule string
`"bear_block & (dd252<=-35% | monthly_os_dwell>=3) & recent_3d_os"` plus `drawdown_252`,
`monthly_oversold_dwell`, `recent_3d_oversold` (`@om:785-790`). `_event_risk_metadata`
(`@om:719-753`) appends a PIT `sweep_low` (min low from 2 bars before the fire), `atr14`, an
ATR×0.5 `stop_level`, and `risk_basis ∈ {daily_ohlc_atr14, close_proxy_atr14}` — explicitly
flagging when close was substituted for absent OHLC.

**Semantics: display/watch only.** "Every event is explicitly `scored:false`; no position, alert or
backtest behavior changes" (`@om:766-767`); "This is context only: it never weakens the classic
`bear_block` entry rule" (`@om:691`). `contracts.py@om:541` keeps `BOTTOM_WATCH` out of the scored
state.

## §4. Data plane and artifacts

* **Store:** `DATA = $MACRO_REPO/data/stocks/<SYM>.parquet`, default
  `/Users/chriswong/Documents/Cluade/Macro Dashboard` (`confluence.py@om:53-55`). **The Terminal
  signal layer reads the MACRO repo's OHLC store** — the two repos already share a data plane. 229
  parquet files; columns `close, high, low, volume` **with no `open`** (verified by read), hence
  `bar_quality: "synthetic_open_deepstore"` (`contracts.py@HEAD:65`).
* **Vendor / adjustment:** Polygon daily aggs, Yahoo `period=max` preferred when deeper —
  "(split/div adjusted, back to IPO)" (`ingest/build_polygon_universe.py:34`; manifest
  `"source": "polygon"` `:117`). Spot-check: NVDA 2024-06-05 close = 122.23 ⇒ **post-10:1-split
  adjusted**. Daily RTH bars; no extended-hours series reaches the signal layer. Local copy's last
  bar: **2026-07-08**.
* **Versioned artifact — YES.** `mastermind.indicator/v1` (`contracts.py@om:29`, schema
  `contracts/indicator.v1.schema.json`, 363 ln): top-level `early_dots` (`@om:214`), `warnings`,
  the unified `signals` stream including `BOTTOM_WATCH`, `state`, `meta.leakfree/score_basis`.
  Emitted per symbol as `<SYM>.slice.json` by `ingest/gen_slices_all.py` (broad universe) and
  `ingest/build_polygon_universe.py` (flagship ~37, with backtest).
* **spec_hash conventions already present:**
  `source_hash(src, params) = "sha256:" + sha256(src + "\x00" + json(params, sort_keys))`
  (`contracts.py@om:128-133`); `strategy_spec_hash(id, params) = sha256({id,params})[:8]`
  (`@om:135-141`, "so ingest can detect a LANE-STALE artifact"). Hashed params `FLAGSHIP_PARAMS`
  (`@HEAD:36-44`) = `{confW:8, rsiLen:14, useMTF:true, confirmTF:"1W", macd_on:"rsi",
  macd_fast:14, macd_slow:60, macd_signal:5, buy_rsi_max:65, ext_rsi:70, rev_bars:3,
  no_cut_exits:true}`. Second identity axis: `SIGNAL_ERA` (**`gc_v2_wo2`**,
  `signal_layer/__init__.py`), asserted in tests and stamped on every emission.
* **Fixture convention:** `tests/test_bottom_watch_lane.py@om:27-51` builds **synthetic** `sig`
  frames (`_frame(n)`), not recorded real-data goldens. A parity module exists —
  `signal_layer/golden_gate.py` (235 ln, "Golden-reference parity gate — INVERTED (audit #7)") —
  but its header warns the exported-vector gate reflects the **dashboard's** canon sequence, not
  this engine's. **No known-answer fixture for `early_dots` exists anywhere.**

**Cross-repo fork hazard (verified):** `Macro Dashboard/research/signal_engine/confluence.py` still
exists. Diffed against `origin/master:signal_layer/confluence.py`: **38 changed lines, all the
module header/`DATA` path plus the `known_ts` addition** — oscillator and 3D-bar math is
byte-identical, so the Terminal header's claim that it "has CORRECTED the math vs that copy"
(`confluence.py@om:31-35`) is **stale**. But the Macro copy has **zero** occurrences of
`known_ts`, so it cannot express §1.4's PIT rule, and there is no `confluence_v2.py` on the Macro
side at all. The `m2d_s3d_early` corpus in `research/signal_engine/` (`CONFLUENCE_TUNING.md`,
`tuning_lead.py`, `tuning_stops.py`, `TIERED_CASCADE.md`) all predates the PIT fix.

## §5. Known-answer fixture plan

Extractable today from the shared deep store with the shipped functions. Freeze each as
`{symbol, feed_end, expected_early_dots[], expected_bottom_watches[]}` plus the `source_hash` and
`SIGNAL_ERA` it was cut under.

| # | ticker | window | asserts | why |
|---|---|---|---|---|
| F1 | NVDA | full → 2026-07-08 | `early_dots` ≥2025 == the 8 dates in §2.6; `bottom_watches` == ∅ | baseline positive; pins the 3D session-grid phase (IPO 1999) + the empty-promotion path |
| F2 | NFLX | same | 11 dots ≥2025; the 4 watch events; emitter's `unpromoted_early_dots` **excludes** 2026-02-06 / 02-25 / 06-26 | only name with promotions — pins the de-dup rule of §2.1 in both directions |
| F3 | NFLX | same | `2026-02-20` has `kind == "blocked_trigger"` and is NOT in `early_dots` | pins stronger-subtype precedence (`@om:779-781`) |
| F4 | TSLA | same | 10 dots ≥2025; ∅ watches | shorter history (IPO 2010, 1344 3D rows) — catches `bar_anchor`/warm-up drift |
| F5 | all three | per-event | `known_ts` == §2.6 values (NVDA 2026-01-21→01-23; NFLX 2026-06-26→06-30) | the PIT contract; a reimplementation without `known_ts` fails loudly |
| F6 | any | truncate the daily feed to end at each dot's `ts`, before its `known_ts` | the dot must NOT be present | negative/leak test — the exact failure PR #392 fixed; the only case that would have caught it |

## §6. Parity strategy — recommendation

**Recommended: (a) consume the versioned Terminal artifact, with (c) as fallback under a locked
spec. Not (b).**

1. **The data plane is already shared.** The Terminal signal layer reads
   `$MACRO_REPO/data/stocks/*.parquet` (`confluence.py@om:53-55`). Macro *produces* the bars G0
   consumes, so there is no data-coupling barrier to (a) and no vendor/adjustment reconciliation —
   the usual reason to prefer a reimplementation is absent.
2. **A versioned, hashed artifact already exists.** `mastermind.indicator/v1` carries `early_dots`
   + `BOTTOM_WATCH` with `known_ts`, `source_hash`, `SIGNAL_ERA` (§4). Macro consumes
   `<SYM>.slice.json` and pins on `(source_hash, SIGNAL_ERA)` — exactly what `strategy_spec_hash`
   was written for (`@om:137-139`).
3. **(b) is the worst option here.** `confluence_v2.py` is 1211 ln with a hard
   `from .washout_override import …` (`@om:41`, 1107 ln) pulling the whole override/ledger/era
   machinery; a "pure" extraction forks four files across two repos with no shared package boundary
   (no installable package, no version pin, `sys.path.insert` bootstrapping throughout `ingest/`
   and `tests/`). The last attempt is the evidence: `research/signal_engine/confluence.py` drifted
   into a *silent* fork the Terminal header still mis-describes, missing `known_ts` entirely (§4).
4. **(c) is a fallback, not a co-equal.** If Radar needs a cadence the nightly slice lane does not
   serve, reproduce G0 in Macro under a **locked spec** = §1 of this document + §5 fixtures + a
   `spec_hash` computed the way `source_hash` is, gated by a parity test re-running F1–F6 against a
   freshly generated Terminal slice. Do **not** seed it from
   `research/signal_engine/confluence.py` (no PIT, no v2 layer) or from the checked-out
   `charting-app` tree (§0: leaking 2D map).

Constraints observed: no installable package or version pin on either side; both repos bootstrap
via `sys.path.insert(0, ROOT)`; the store the slices are built from is currently **5 weeks stale
(last bar 2026-07-08)**, so an artifact-consumption design needs its own freshness gate; and
`early_dots` is capped at 40 in the doc and 12 in the model slice (`@om:185, 642`), so a Radar
needing deep history must read the raw emission, not the model slice.

## §7. Other `signal_layer/` primitives — inventory only (OUT OF SCOPE for V1)

| module | ln | one-line (from its module docstring @origin/master) |
|---|---|---|
| `__init__.py` | 68 | "Signal layer — the TRUSTED math of the charting container"; holds `SIGNAL_ERA`. |
| `confluence.py` | 456 | The immutable oracle: Pine "RSI-MACD × StochRSI MTF" port on 3D + trade-level backtest. |
| `confluence_v2.py` | 1211 | GC v2 emitter — no-cut exits, graded recipe tier, keeper verdict, early dot, ARM/CONFIRM warns, bottom watch, reclaim lane. |
| `contracts.py` | 679 | The data contracts — builds `mastermind.indicator/v1` + `backtest_result/v1`; owns `source_hash`/`spec_hash`. |
| `backtest.py` | 271 | Tier-1 backtester; promotes `confluence.simulate` and adds the `backtest_result/v1` metrics. |
| `golden_gate.py` | 235 | Golden-reference parity gate (INVERTED, audit #7) — exported-vector comparison vs the dashboard canon. |
| `washout_override.py` | 1107 | Blocked-entry washout override: live entry gate, display stamp, forward ledger (era `gc_v2_wo1/wo2`). |
| `washout_lab.py` | 250 | Panel evaluation for the washout-reversal lane (`docs/PREREG_WASHOUT_REVERSAL.md`). |
| `reclaim_lab.py` | 159 | Panel evaluation for the RE-ENTRY repair lane (2026-07-15 rotation-miss directive). |
| `seasonal_regime.py` | 592 | Regime-aware forward seasonal-outlook engine from daily adjusted closes. |
| `regime_calendar.py` | 156 | Static macro-regime reference calendar 1970–2027 — the one curated-knowledge layer. |

Outside `signal_layer/` but referenced above: `terminal/lib/signalVerdict.ts` (993 ln,
verdict/soft-quality classification consumed by `ChartPanel.tsx`) and `terminal/lib/pine.ts` (the
flagship Pine source string, `B1/S1` early vs `B2/S2` confirm grammar).
