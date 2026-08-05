# Board continuity forensic — VALE, HL, NEM, and the why-not battery

**Date:** 2026-08-05 · **Trigger:** operator report — *"VALE sat in the US board BUY lane
07-24..07-31, then vanished from the live board AND has zero rows in retro_grades /
retro_grades_v2 AND never appears in the track-record dialog — while NEM, same admission
era, shows fine."*

Everything below is measured against committed artifacts in this repo. Where a claim
could not be established from a receipt it says so.

---

## §0 — Verdicts

| Question | Verdict |
|---|---|
| Why is VALE absent from the track-record dialog? | **Bug, now fixed.** The graders priced from a *narrower universe than the board admits from*. VALE was never delisted or stale — `data/yahoo/VALE.parquet` carries 6,131 closes through 2026-08-03. |
| Why did VALE leave the *rendered* board? | **A real, dated exit on the 2026-08-03 bar** — not the collect outage, and not a signal invalidation. Its entry gate is still `T1 / eligible` today. 22/22 builds correlate exactly with the build's data reach. |
| Was the 08-01..08-03 gap backfilled? | **No.** It is disclosed in the artifact and now warns in Actions. |
| Is NEM "fine" while VALE is not? | **The premise is wrong.** NEM left the snapshot board after 07-27 and is absent from the live board too. It differs from VALE only in being *priced* — it is an S&P 500 name in the breadth cache. |
| Why-not battery (FNV, CDE, FSM, EXK, AG, GOLD, SBSW, RKLB, ASTS, SPCX) | 5 of 10 are **not in the universe at all** (scan-tier gap, roadmap §4.5 — chartered, not built). 3 more are in-universe but have **too little price history** to compute a tier. Only 2 are genuinely gated by a signal leg. |

---

## §1 — The VALE class: the ledger priced a narrower universe than the board admits

### The population rule that dropped it

The board's universe (`scripts/build_stock_library.py::universe`) is a **union of three
sources**:

1. `data/stocks/*.parquet` — deep history (235 names)
2. the breadth close caches — `data/{breadth,smallcap_breadth,midcap_breadth}/_closes_cache.parquet`
3. the curated extras — `stock_search.extra_tickers` (449 entries: foreign ADRs, recent
   IPOs outside the S&P 1500), read from the yahoo store via `lib.store.read('yahoo', t)`

Every grader in `scripts/grade_us_board.py` priced from **exactly one** of them —
`engine.equity_factors._closes("broad")`, which is sources (2) only. So a name admitted
through the extras lane satisfied `tk not in names.columns` and hit `continue`:

```python
for ep in _ts.build_episodes(board_days):
    tk, d0 = ep["ticker"], ep["entry_date"]
    if tk not in names.columns:
        skipped_no_price.append(tk)
        continue                     # <- the row simply never existed
```

Three call sites had this shape (`emit_ledger` ×3), plus the retro grader
(`grade_boards`, via `resolve_series` returning `None`) and the outcomes strip.

### It was the whole skip list, not one name

Reconstructing the boards and testing every skipped ticker against each admission source:

| Ticker | in broad closes | in `data/stocks` | in yahoo store (the admission source) |
|---|---|---|---|
| ASTS, BIDU, CRDO, LCID, NET, NVO, NXE, PL, RKLB, TEAM, U, UROY, **VALE** | no | no | **yes — all 13, through 2026-08-03** |

`n_skipped_no_price` in the shipped `site/factordata/us_track_ledger.json` was **12
episodes / 10 unique tickers**; `tickers_skipped` read
`["ASTS","BIDU","CRDO","NET","NVO","NXE","TEAM","U","UROY","VALE"]`. Across the full
board history this checkout can reconstruct, the class is **13 tickers** (the 12 above
plus LCID, and PL from a non-buy lane). Every one is recoverable from the very store the
board admitted it from. **Residual unresolvable: 0.**

VALE specifically ran **two** episodes (contiguous board runs), which is why the episode
count was 12 against 10 tickers:

- `2026-07-24 → 2026-07-28` (absent 07-29)
- `2026-07-30 → 2026-07-31`

### The fix

1. **`extend_prices_to_admitted(names, boards)`** (new, `scripts/grade_us_board.py`) —
   widens the close panel to every ticker the boards admitted, resolving misses from the
   same yahoo store the board read. Dead names are excluded from the re-read so
   `engine.grading.resolve_series` keeps owning the delisted-terminal path. Wired in
   `main()` between `collect_boards()` and every grader, so the retro grader, the track
   JSON, the outcomes strip and the ledger all widen together.
2. **Row-persistence law** — the three `continue` sites now publish a row instead of
   deleting the episode: `st="unscored"`, `xr="no price data"`, all numbers null, in no
   summary. A pick the desk can no longer price is still a pick the desk made; a missing
   row is indistinguishable from a name that was never chosen.
3. `unscored` registered in `engine/track_ledger.STATUS_VOCAB` and given plain words in
   both languages in the dialog (`No price data` / `无价格数据`) — the vocabulary gate
   caught the new status immediately, which is the gate working.

### Measured effect — the headline record does **not** move

Rebuilt against the real boards, with a control run that keeps the old price panel so
the change is isolated from this checkout's git-archaeology variance (see §7):

| | control (old panel) | fixed |
|---|---|---|
| episodes added / removed | — | **0 / 0** |
| `win_pct` | 62.2 | **62.2** |
| `expectancy_pct` | 1.12 | **1.12** |
| `profit_factor` | 1.62 | **1.62** |
| `n_matured` | 275 | **275** |
| `n_inflight` | 289 | 302 |
| `n_skipped_no_price` | 13 | **0** |

All 13 recovered episodes entered 07-22..07-31 and are still in flight at H=10, so they
join the record as they mature — earned forward, not injected retroactively.

VALE's rows after the fix:

```
{"t":"VALE","d":"2026-07-30","e":15.06,"l":14.58,"p":-3.2,"dy":1, "st":"onboard","m":false,"rk":6,"sec":"Materials"}
{"t":"VALE","d":"2026-07-24","e":14.78,"l":14.58,"p":-1.4,"dy":5, "st":"onboard","m":false,"rk":6,"sec":"Materials"}
```

The **retro** half recovers too. Running `grade_boards` over the five boards that carried
VALE, control panel vs widened panel:

| | graded rows | `skipped_no_price` | VALE rows |
|---|---|---|---|
| control (old panel) | 0 | 25 | **0** |
| widened | 1 | **0** | **1** |

```
as_of 2026-07-24 · entry_date 2026-07-27 · horizon 5 · lane buy · VALE
ret −1.35% · excess_spy −3.87% · Materials
```

Exactly one row, because 07-27 + 5 sessions lands on 2026-08-03 — the newest close that
exists. The other boards and horizons are still unmatured, which is the maturity gate
working, not a hole.

---

## §2 — VALE: why it left the rendered board

**Verdict: a genuine, dated exit on the 2026-08-03 bar. Not the collect data gap, and
not a signal invalidation.**

### Its entry gate never turned off

`engine.confluence_tiers.tier_stream` over VALE's full close history:

| date | tier | eligible | not_topped | weight |
|---|---|---|---|---|
| 2026-07-24 | — | False | **False** | 0.0 |
| 2026-07-30 | T1 | True | True | 0.9 |
| 2026-07-31 | T1 | True | True | 0.9 |
| **2026-08-03** | **T1** | **True** | **True** | **0.9** |

Leg snapshot today: `stoch_ob=False, stoch_bear=False, macd_bear=False, rsi_block=False,
k3=59.2, d3=51.6, rsi3d=43.9` (cap is 65), `t1_ticks=2` (freshness cap is 2).
`eligibility_window` reports `eligible_today=True, tier_today=T1, days_eligible=5,
first_eligible=2026-07-28`. **No veto leg fires. VALE is still admissible today.**

### What actually decided its presence: the build's data reach

Across the 22 most recent revisions of `site/factordata/us_standouts.json`
(2026-08-03T15:41Z → 2026-08-05T09:19Z), **every single one** stamps
`as_of: 2026-07-31` and `staleness.price_through: 2026-07-31`, and `universe: 1579`. Yet
VALE flips in and out eight times and the buy lane ranges 55–76 names.

The discriminator is exact, 22 for 22 — `donor.asof`, the only field in the artifact that
reveals how far the build's data actually reached:

| `donor.asof` | builds | VALE in buy lane |
|---|---|---|
| 2026-07-31 | 7 | **yes — 7/7** |
| 2026-08-03 / 2026-08-04 | 15 | **no — 0/15** |

VALE closed **−3.2% on 2026-08-03** (15.06 → 14.58). Every build that could see that bar
dropped it; every build that stopped at 07-31 kept it. It was a marginal admission to
begin with — from the 07-31 snapshot payload: `lane: "bottoming"`, `label: "UNCONFIRMED
TURN"`, `state: "COUNTERTREND BOUNCE"`, `urgency: "caution"`, `conviction.score: 9`, band
`neutral`, `size.bucket: "quarter"`, `capped_by_entry: true`, `sector_rank: 11/88`.

So the exit is real and it is dated 2026-08-03. What the collect outage did was make it
**undateable from the outside**: the board's own `as_of`/`price_through` never advanced
past 2026-07-31, and the forward ledger recorded no board after 2026-07-31, so the
departure has no ledger event at all. To a reader the name simply stopped existing.

> **Flagged, out of scope here (fences: display/ledger honesty only).** Render lanes are
> disagreeing about data reach while all stamping the same `price_through`. `donor.asof`
> alternates 07-31 ↔ 08-03 between consecutive builds an hour apart, moving the buy lane
> by up to 21 names. The donor block itself is display-only (`build_stock_library.py`:
> *"DISPLAY-ONLY — never a gate, never changes ranking"*), so it is the **symptom**, not
> the cause; it is simply the only field that leaks the build's true data date. This
> wants its own lane.

---

## §3 — HL: the admission receipt

HL (Hecla Mining) was admitted to the **buy lane on 2026-07-01**. Its own row from that
night's snapshot:

```
ticker HL · Hecla Mining · Materials · alpha 1.71 · alpha_entry "pullback"
state  "RALLY ON"     label "UPTREND (blocked)"     urgency "hold"     off_high −51.0
align_tier "aligned"
signal { eligible: FALSE, tier: null, weight: 0.0, above200: false, weekly_bull: false,
         reason: "buy blocked by filter: counter-trend, no 200-reclaim/hold",
         last: { date: 2026-06-16, type: "buy", quality: "BLOCK",
                 reason: "counter-trend, no 200-reclaim/hold" } }
conviction { score: 50, band: "neutral", verdict: "Neutral — no clear edge",
             cautions: ["accounting warn"] }
size { bucket: "FULL", pct: 100, vol_mult: 0.52 }
```

**This is the era's chop-intake failure mode in one row.** The board put HL in the *buy*
lane on its **alpha** rank (1.71, a strong reading) while HL's own entry gate said
`eligible: false`, `weight: 0.0`, `quality: "block"` — a name 51% off its high, below its
200DMA, with no reclaim, carrying an accounting caution — and then sized it **full,
100%**. The washout detector took it because the alpha leg ranked it and the gate's
refusal was carried as a *label* (`UPTREND (blocked)`) rather than as an exclusion.

Outcome, from the rebuilt ledger: entry 16.33 → exit 14.33, **−12.2%**, `x` (excess vs
SPY) −12.05, held 10 sessions, `exit_reason: "horizon"` — it never hit the target or the
stop, it simply ran out the forced verdict clock. This is the loss the W1 repair
addressed, and it is now visible in the dialog rather than inferred.

---

## §4 — NEM: current state and grading timeline

**The brief's premise does not hold.** NEM is not "still on board":

- snapshot ledger: NEM in the buy lane on **2026-07-24 and 2026-07-27 only** — gone from
  07-28 onward, one board date *before* VALE's last appearance;
- live board (HEAD, `as_of 2026-07-31`): NEM is **absent from every lane** — buy, watch,
  leaders, laggards, ran.

The only real difference between NEM and VALE is that NEM is **priced**: it is an S&P 500
constituent, so it sits in `data/breadth/_closes_cache.parquet` and the grader could
always see it. VALE, an ADR admitted through the curated-extras lane, could not be seen at
all. That is the whole of "NEM shows fine" — a coverage artifact, not a difference in how
the two names were treated.

Current NEM episode (rebuilt ledger, entry from the 2026-07-22 board revision that git
archaeology carries but `snapshots.jsonl` does not — see §7):

```
{"t":"NEM","d":"2026-07-22","e":94.72,"l":93.71,"p":-1.1,"dy":6,"st":"onboard","m":false,"rk":15,"sec":"Materials"}
```

Price path: 07-24 93.19 · 07-31 93.71 · 08-03 95.37. At `LEDGER_HORIZON = 10` sessions
from a 07-23 fill, **NEM matures ~2026-08-06**, one session earlier than the ~08-07 in the
brief (which assumed a 07-24 admission). Note NEM's *yahoo* file holds only 23 bars — it
is priced from the breadth cache, not the extras store, so `tier_stream` returns an empty
frame if run off the yahoo series alone (`MIN_HISTORY = 200`).

---

## §5 — Why-not receipts battery

Universe membership was tested against all four admission sources per name.
**`data/russell_breadth/_closes_cache.parquet` does not exist** in this checkout (the
directory holds `breadth/constituents/high/low/volume` parquets but no closes cache), so
only three of the four breadth caches are live and no name can be admitted through the
Russell lane at all.

| Ticker | `data/stocks` | breadth caches | curated extras | yahoo store | Status |
|---|---|---|---|---|---|
| **FNV** (Franco-Nevada) | no | no | no | no | **not in universe** |
| **FSM** (Fortuna) | no | no | no | no | **not in universe** |
| **EXK** (Endeavour Silver) | no | no | no | no | **not in universe** |
| **AG** (First Majestic) | no | no | no | no | **not in universe** |
| **SBSW** (Sibanye-Stillwater) | no | no | no | no | **not in universe** |
| **CDE** (Coeur Mining) | no | `midcap_breadth` | no | no | in universe, **no tier** |
| **GOLD** (Barrick Mining) | no | no | **yes** (`config.yml:2537`) | 23 bars → 2026-08-03 | in universe, **no tier** |
| **SPCX** (SpaceX) | no | no | **yes** (`config.yml:2135`) | 35 bars → 2026-08-03 | in universe, **no tier** |
| **RKLB** (Rocket Lab) | no | no | **yes** (`config.yml:2136`) | 1,427 bars | in universe, **gated** |
| **ASTS** (AST SpaceMobile) | no | no | **yes** (`config.yml:2138`) | 1,695 bars | in universe, **gated** |

### (a) Not in the universe — the scan-tier gap

**FNV, FSM, EXK, AG, SBSW** are absent from every admission source. There is no close
series for them anywhere in the repo, so the board cannot rank them, refuse them, or
explain them — they are simply outside the search set. The only `FNV` string anywhere in
`config.yml` is `FNV.TO` (the Toronto listing) inside the curated TSX breadth block at
`config.yml:6251`, a different config path that grants no US-board reachability.

This is the **scan-tier gap** — roadmap §4.5, chartered but not built. Closing it is an
operator decision (it widens the nightly's compute), not something this lane should do.

### (b) In the universe, but no tier can be computed

`engine.confluence_tiers` requires `MIN_HISTORY = 200` non-null closes; below that
`tier_stream` returns an **empty frame** and `prophet_miss_audit` reports the excluder
`insufficient_history`.

- **GOLD** — 23 bars (first 2026-07-01). Recently added to the extras list; the store has
  not accrued enough history yet.
- **SPCX** — 35 bars (first 2026-06-12). **It is a single stock, not an ETF**:
  `config.yml:2135` reads `- SPCX   # SpaceX (IPO 2026-06-12, Nasdaq — days-old; LIMITED
  card until it ages)` and `config.yml:2642` `SPCX: {name: "SpaceX", sector:
  "Industrials"}`. The *fund* proxy is a separate ticker — `config.yml:2149`: DXYZ
  (Destiny Tech100), a closed-end fund whose top holding is SpaceX, kept alongside the
  now-public SPCX. `tests/test_ipo.py` and `tests/test_etf_board.py` both class SPCX as
  ordinary equity (`is_spac=False`, not cash-like).
- **CDE** — in `midcap_breadth`, but only **51 non-null closes** spanning 2026-05-19 →
  2026-07-31. In-universe in name only.

These three are **not** refusals. Nothing has judged them; there is not yet enough data to
form a judgement, and the honest report is "too new to read", not "rejected".

### (c) In the universe, with enough history — genuinely gated

Both are blocked by the **same single leg**, and it is the `not_topped` veto, which trips
*before* any cross / freshness / RSI check runs — so the tier is null regardless of cross
age.

`not_topped = not (stoch_ob or stoch_bear or macd_bear)` — code comment:
*"topped/rolled-over: never a fresh buy"* (`engine/confluence_tiers.py:266`).

| | tier today | blocking leg | k3 / d3 | rsi3d (cap 65) | cross age |
|---|---|---|---|---|---|
| **RKLB** | null | **`macd_bear`** (3D RSI-MACD below signal) | 11.4 / 4.3 | 43.4 | t1_ticks 26 (stale) |
| **ASTS** | null | **`macd_bear`** | 13.1 / 6.4 | 42.6 | t1_ticks 19 (stale) |

Neither is overbought, neither is RSI-capped. Both are below their 3D MACD signal line —
still rolling over. ASTS logged 5 eligible T1 days in the trailing 63 sessions (first
2026-05-18; **−26.9%** since), which is the receipt for why the veto is there. RKLB logged
zero.

---

## §6 — Desk themes and board composition

### Space and miners-adjacent themes

`engine/theme_tape.py` `THEME_MAP` (lines 223-238) and
`site/basketdata/foresight_cascade.json` (`asof: 2026-08-04`):

| desk theme | maps to shelf | current stage | earns a chip? |
|---|---|---|---|
| `space_satellite` | Space Tech | `WATCH` | **no** |
| `rare_earth_critical_min` | Commodities Metals | `PRECIPICE (text)` | yes — *"loading"*, **unconfirmed** (`bottleneck_text_only: true`) |
| `copper_steel_electrify` | Commodities Metals | `WATCH` | **no** |

**The Theme Tape's shelf will not show `space_satellite` after tonight's engine run
either** — not because the fields are missing, but because `WATCH` has no word in
`STAGE_LABEL` and `_foresight_themes` drops any theme whose stage maps to `None`:

```python
label = STAGE_LABEL.get(theme.get("stage"))
if not isinstance(key, str) or not key or label is None:
    continue
```

The module states the intent verbatim: *"a new stage is silent until someone decides its
word"* (`theme_tape.py:156`). So the shelf shows Space Tech only once `space_satellite`
advances past WATCH. Of the two miners-adjacent themes, only `rare_earth_critical_min`
currently votes, and its chip is explicitly **unconfirmed** (text-only bottleneck read).

### Board sector mix — beside the "NASDAQ +3%, ~9 tech on board" complaint

Current board (`as_of 2026-07-31`), buy lane n=60:

| sector | n | | sector | n |
|---|---|---|---|---|
| Materials | 10 | | Consumer Staples | 5 |
| Consumer Discretionary | 10 | | Communication Services | 4 |
| Financials | 10 | | Energy | 2 |
| Industrials | 9 | | Real Estate | 2 |
| Information Technology | 8 | | | |

**Tech-ish (Information Technology + Communication Services) = 12 of 60 = 20%.** Across
buy + watch (n=108) it is 20 of 108 = 19%, with Industrials the largest bloc at 26.

For scale: Information Technology is ~32% of the S&P 500 by weight. The board is running
roughly *under*weight technology on a day the NASDAQ moved +3%, which is the composition
a bottoming/washout screen produces by construction — it looks for names that have already
been sold, and technology had not been.

---

## §7 — Caveats and things deliberately not done

- **No forward-ledger backfill.** `snapshots.jsonl` ends 2026-07-31 and stays there. The
  01–03 August gap is disclosed (`meta.continuity` in the ledger artifact, a quiet line in
  the dialog, a line-start `::warning` in Actions) and never reconstructed. Nightly
  remains the sole advancer.
- **No gate, score or population change to admission.** The fix widens what the *grader*
  can price; it does not change who gets on the board.
- **Retro grading is maturity-gated, not broken.** `retro_grades.parquet` stops at
  `as_of 2026-07-21` because `forward_metrics` returns `None` for an unmatured horizon and
  closes end 2026-07-31 — a 07-24 board needs 08-03 to mature at H=5. That is the gate
  working. VALE's zero rows there had the *second*, durable cause fixed in §1: with no
  price series it would never have graded even after maturity.
- **This checkout sees a different board history than the machine that wrote the shipped
  artifact.** `collect_boards()` reads the local git history of
  `site/factordata/us_standouts.json`; here that yields 25 board revisions / 14 scored
  board days against the shipped artifact's 17 / 8, which is why a naive rebuild appears to
  add 174 episodes. That variance is pre-existing and is exactly what `meta.history` exists
  to make auditable (`_git_revisions` was hardened for it on 2026-07-26). The §1 numbers are
  from a **control run at identical board input**, so none of that variance is attributed to
  this change.
- **Flagged for a separate lane:** the render-lane data-reach oscillation in §2 — builds
  an hour apart alternating `donor.asof` 07-31 ↔ 08-03 while all stamping
  `price_through: 2026-07-31`, moving the buy lane by up to 21 names.
