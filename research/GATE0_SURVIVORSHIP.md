# GATE-0 — PIT-membership survivorship audit of the sector-rotation ladder

> **STATUS: COMPLETE (2026-06-27). VERDICT — the VALIDATED label HOLDS; survivorship is
> not in play for the shipped numbers, and is immaterial at the name level.** This is the
> first gate in `research/SECTOR_ROTATION_CONTINUATION.md`. Engine + harness:
> `scripts/research/gate0_survivorship.py` → `data/research/gate0_survivorship.json`.

## TL;DR

1. **The literal worry is a non-sequitur — proven from source.** Every "validated"
   sector-rotation number the handoff lists (BUY +0.87%, AVOID −1.34%, liquidity +6.4pp)
   was computed on a **survivorship-clean universe with no S&P-1500 membership**: the
   sector-confluence ladder on the **11 SPDR sector ETFs vs SPY**, the liquidity edge on a
   **fixed ~141-instrument cross-asset panel**. ETF/panel prices have no constituent
   membership, so they *cannot* carry dead-name survivorship bias. There is no
   "current-membership" version of these numbers to re-run. **No downstream weight re-tune
   is warranted on survivorship grounds.**

2. **The genuine test the PIT data enables — does the edge generalise to the constituent
   NAMES, survivorship-clean? — was run, and survivorship does not change its direction.**
   Applying the engine's own `_verdict` state machine to ~1,656 S&P-1500 names (deep +
   delisted prices, 1998–2026), the **sign/rank** of the within-engine sorting (full BUY >
   confirmed SELL) is preserved in all four eras going from a survivorship-biased universe
   to a point-in-time, delisting-inclusive one. De-biasing shifts absolute levels down
   ~uniformly; it does **not** flip the BUY-vs-SELL structure. (It *does* move the per-era
   spread *magnitude* — e.g. 1998-2007 BUY−SELL +0.06 BIASED → +1.08 PIT — so the honest
   statement is "the direction is survivorship-robust," not "the numbers are identical.")

3. **What the name-level test additionally found (honest, and it re-scopes downstream):**
   the ladder is a **sector/ETF tool, not a single-name picker** — the broad BUY/AVOID
   families do *not* sort individual names — but the **flagship extremes do**: full-confluence
   BUY beats confirmed SELL by **+1.08 / +1.75 / +0.46 / +2.12 %/63d (median, all four eras,
   on PIT)** — positive in every era, though weak (+0.46) in 2016-2020. This corroborates the
   engine's existing claim that the EXTENDED/TOPPING/SELL flag is its most valuable output.

4. **One real code finding (gate #7):** the shipped `calibrate()` 3-day resample carries a
   **~2-business-day look-ahead** (a left-labelled `3B` bar ffilled onto its own start
   date). It cancels in this audit's BIASED↔PIT delta, but it mildly inflates the
   *absolute* displayed `STATE_BASE_RATES`. Recommended fix logged below.

## Why the literal GATE-0 framing is a conflation (provenance, adversarially confirmed)

The handoff worries "every cited number was computed on **current** membership unless
proven otherwise … if the edge halves on historical constituents, all downstream weights
re-tune." Reading the actual validation code refutes the premise for the cited numbers:

| Cited number | Where it's computed | Universe | Survivorship-exposed? |
|---|---|---|---|
| BUY +0.87% / TOP −1.34% / spread +0.83% | `scripts/_bt_sector_confluence*.py`, `engine/sector_signals.calibrate()` | **11 SPDR sector ETFs vs SPY** (`_bt_sector_confluence.py:27` `SECTORS=[XLB…XLY]`; ETF closes from `data/yahoo/{t}.parquet`) | **No** — ETFs have no membership |
| Liquidity +6.4pp/21d | `scripts/research_liquidity_ladder.py` over `research_trend_gate.load_panel()` | **Fixed ~141-instrument cross-asset panel** (`data/yahoo/*` + `data/stocks/*`, static glob) | **No dead-name reconstitution bias** — but see caveat |

`engine/sector_signals.calibrate()` loops over whatever `sectors` list is passed; in
production that is the same 11 ETFs, and no membership/constituent table is ever loaded.
`research/SECTOR_CONFLUENCE.md` says it plainly: *"the 11 SPDR sector ETFs, full Yahoo
history … benchmark SPY."* The handoff itself concedes *"the 11 sector ETFs themselves are
survivorship-clean."*

**Caveat (honest):** the liquidity panel pulls ~121 hand-curated single names from
`data/stocks/`. That is a mild **selection/hand-curation** skew toward large, liquid
survivors — *not* index-reconstitution survivorship (dead names aren't systematically
dropped by a rebalance rule), and the LIQUIDITY_LADDER verdict already collapses to a
defensible episode-unit N. It does not change this gate's conclusion.

## The name-level generalisation test (the honest extension)

**Method.** `scripts/research/gate0_survivorship.py` applies the engine's *own* `_verdict`
state machine (reused verbatim — never reimplemented), weekly-sampled, 200-day-gated,
forward-63d **excess vs SPY** (plus absolute), point-in-time (the daily + 3-day flags are
forward-filled so date *t* uses only data ≤ *t*, exactly as `calibrate()`). Prices:
`data/breadth/_closes_deep.parquet` (survivors, 1962→) ∪ `_closes_delisted.parquet` (dead
names) ; PIT spans from `data/breadth/sp1500_pit_membership.parquet`. Two universes,
identical rule:

* **BIASED** = today's surviving members, evaluated over ALL their history (classic
  survivorship backfill).
* **PIT** = the full historical roster *including delisted names*, each evaluated ONLY
  within its actual membership window(s).
* (**SURV_WIN / DEAD_WIN** decompose the PIT universe.)

**Robust statistics (load-bearing).** Delisted tapes are riddled with penny-stock / split
artifacts that make `c.shift(-63)/c` explode (the raw-mean DEAD slice showed **+800%**
means). The headline statistic is therefore the **MEDIAN** forward-63d excess (outlier-
immune), with a winsorized mean (returns clipped to [−90%, +200%]) beside it; hit-rate is a
sign-count and was never affected. A level-based price floor is deliberately avoided — these
are dividend-adjusted closes, so a $5 floor would delete the early history of every
multi-decade compounder.

**Coverage / honest ceiling.** roster 2,589 · with prices 1,696 · evaluated 1,656. Dead
names: only **199 / 1,083 (≈18%)** have post-exit prices — the irreducible free-data gap
(`scripts/residual_alpha_pit.py` says it needs paid CRSP). Forward-63d returns that run past
a delisting are dropped (no −100% bankruptcy imputation here). Both push PIT **optimistic**
(the worst of the dead is under-sampled), so any surviving de-biasing is a *lower bound* —
**conservative for the verdict, not against it.** By row-count the PIT universe is ~95%
survivors, so this test bounds, rather than fully eliminates, the bias.

### Results (median forward-63d excess vs SPY, %/63d)

**(A) Survivorship does not change the engine's sorting direction.** BIASED → PIT shifts
absolute levels (and per-era magnitudes) but preserves the sign/rank — full BUY > confirmed
SELL in all four eras, both universes:

| BUY − SELL (the flagship extreme spread) | 1998-07 | 2008-15 | 2016-20 | 2021-26 | all 4 > 0 |
|---|--:|--:|--:|--:|:--:|
| **BIASED** | +0.06 | +0.91 | +1.19 | +2.13 | ✅ |
| **PIT** | +1.08 | +1.74 | +0.46 | +2.12 | ✅ |

The de-biasing *strengthens* the early-era extreme spread if anything; it never inverts it.

**(B) The BROAD families do NOT sort single names** — `BUY_SIDE − AVOID_SIDE` oscillates
around zero with inconsistent sign in both universes (it lumps the weak BUY_PARTIAL /
EXTENDED / TOPPING middle, which carries no name-level edge):

| BUY_SIDE − AVOID_SIDE | 1998-07 | 2008-15 | 2016-20 | 2021-26 |
|---|--:|--:|--:|--:|
| **BIASED** | −0.53 | +0.03 | −0.22 | +0.19 |
| **PIT** | −0.07 | +0.08 | −0.50 | +0.09 |

A mechanical reason this rollup never separates: **BELOW_TREND is the single largest state
by count and sits between SELL and BUY** (closer to SELL) — it is counted inside
AVOID_SIDE and dilutes it. The family label "AVOID_SIDE" is, at the name level, a misnomer.

**(C) The EXTREMES do sort names, survivorship-robust.** Pooled (ALL), PIT: BUY median
**+0.22** vs SELL median **−1.19** → **+1.41 BUY−SELL**, and positive in every individual
era (table A). The middle states wash out; the extremes do not. *Caveat:* in 1998-2007 the
winsorized **mean** inverts (SELL +2.02 > BUY +1.25) — a fat right tail in a small
early-era SELL sample (n=1,631). The **median** (BUY > SELL) is the correct robust read,
but the inversion flags that early-era extreme-state point estimates carry wide CIs.

**(D) The dominant name-level pattern is a per-era breadth drift, not state sorting.** The
cross-state median excess declines monotonically by era — PIT all-state mean of the per-
state medians: **+0.71 → +0.34 → −0.34 → −2.03** (1998-07 / 2008-15 / 2016-20 / 2021-26).
*Within* each era every state moves together with the tide: in 2021-26 even full BUY is
**−1.10** (still 1.1pp below SPY). The average S&P-1500 *name* badly lagged **cap-weighted**
SPY in the mega-cap-concentration era — a breadth/benchmark effect that swamps the engine's
weak/middle states and is the province of the breadth + MRS engines (P1 `regime_vector`),
not the confluence ladder. The DEAD_WIN slice confirms the de-biasing direction (dead names
in BELOW_TREND cratered, 2021-26 median −9.1%), though its extreme-state counts are too thin
(n≈14–16) for per-state era inference.

## Verdict against the handoff bar

> *"if AVOID's all-4-era negativity survives on PIT → label stays VALIDATED; if it weakens,
> downgrade."*

**VALIDATED — holds.** Two independent reasons:

1. The ETF-level AVOID edge (the actual subject of that bar) is **survivorship-clean by
   construction** — it has no constituent membership to bias. The label was never exposed.
2. The supplementary name-level test shows the engine's discriminating power (the BUY↔SELL
   extreme spread) is **survivorship-robust in sign/rank** (the BIASED↔PIT delta moves
   magnitudes, never the direction) and **positive in all four eras on PIT**. The de-biasing
   does not weaken it.

The literal failure mode the handoff feared ("edge halves on historical constituents") does
**not** occur — and could not, because the edge was never measured on constituents.

## Downstream guidance (re-scopes P0 / P1)

* **P0 flow-router must gate at the SECTOR/ETF lane**, where the edge is validated and clean.
  Do **not** route individual names off sector states — the broad families don't sort names.
* If name-level use is ever added, restrict it to the **extremes** (full-confluence BUY /
  confirmed SELL), never the BUY_PARTIAL / EXTENDED / TOPPING middle.
* The per-era constituent-vs-SPY **breadth drift** the names exhibit belongs to P1's
  `regime_vector` (breadth + MRS), not the confluence ladder.
* **No re-tune of the published ETF base rates on survivorship grounds** is justified.

## Code finding (gate #7 — leak check) — recommended follow-up

`engine/sector_signals.calibrate()` builds the 3-day flags via
`c.resample("3B").last().reindex(c.index, method="ffill")`. `3B` bins are **left-labelled**,
so the bar labelled day *L* contains the close from *L+2*, and ffilling it back onto *L*/*L+1*
gives the historical read up to **2 business days of look-ahead**. This:

* **Does NOT affect the live signal** — the latest 3-day bar uses only closes ≤ today.
* **Does NOT affect this audit's survivorship conclusion** — the artifact is identical on
  both BIASED and PIT and cancels in the delta.
* **Does mildly inflate** the *absolute* displayed `STATE_BASE_RATES` (and the
  `_bt_sector_confluence*` levels). Small vs a 63-day horizon, but real.

**Fix:** lag the resampled frame so a daily date sees only the last *fully-closed* 3-day bar
(`.shift(1)` on the resampled flags before reindex, or right-label + 1-bar lag), then
re-run `calibrate()` and refresh the base rates. Tracked as a separate change (it alters
displayed numbers and needs its own before/after, so it is **not** bundled into this audit).

## Validation (two independent adversarial passes)

* **Provenance audit** (skeptical re-read of the validation source) — CONFIRMED the
  sector-confluence numbers are 11-ETF-vs-SPY (`_bt_sector_confluence.py:27`) and the
  liquidity number is a fixed cross-asset panel; **no constituent current-membership
  backtest exists anywhere** in the validation code.
* **Code-leakage audit** — PIT windowing, BIASED/PIT/SURV/DEAD universe definitions,
  multi-span membership, forward-return loop bounds, family rollups, and median-over-
  winsorized-stream all **pass**. Two nits surfaced: the 3B look-ahead (above; a known
  shared artifact, delta-neutral) and a now-removed inert double-clip of the SPY benchmark.
  An `end_date` ±1-trading-day inclusivity ambiguity is immaterial under weekly sampling.
* **Statistics audit** (independent re-read of the JSON) — claims A–D each **confirmed**:
  survivorship not material to the sign/rank of sorting; broad families don't sort names;
  extremes do (BUY−SELL PIT median `[+1.08, +1.75, +0.46, +2.12]`, verified); per-era
  breadth drift dominates. Sharpenings (magnitude distortion, early-era mean inversion, DEAD
  thinness) are folded in above.

## Reproduce

```
# (worktree: symlink the two gitignored caches from the main checkout first)
python -m scripts.research.gate0_survivorship
# -> data/research/gate0_survivorship.json + the printed BIASED/PIT/SURV_WIN/DEAD_WIN tables
```

*Refs:* `engine/sector_signals.py` · `research/SECTOR_CONFLUENCE.md` ·
`research/LIQUIDITY_LADDER.md` · `research/SECTOR_ROTATION_CONTINUATION.md` ·
`scripts/residual_alpha_pit.py` (PIT-membership + delisted-price plumbing).
