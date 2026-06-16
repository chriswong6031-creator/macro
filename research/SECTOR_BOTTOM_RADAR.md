# Sector Bottom Radar — can we call sector bottoms? (measured)

> **STATUS: engine BUILT + Phase-0 VALIDATED (2026-06-16).** `engine/sector_bottom.py`
> + `scripts/sector_bottom_phase0.py`. The verdict is a *qualified yes*: we cannot
> call the exact low, but the validated per-stock Bottom Confidence machinery
> **transfers cleanly to the sector level**, and the index Fed-put gate splits sectors
> the same way it splits the index. The product is a **risk / durability** read, not a
> bottom-timing oracle and not alpha.

## The question (user)

> The Sector Heat Board shows RRG stages (improving / lagging / leading / weakening).
> "These help but not a lot." Can we determine, *with accuracy*, that a sector has
> bottomed — using our data, technicals, momentum and other factors?

## Why the RRG stages are weak for this

`engine.playbook.stage_table` classifies a sector on a 2×2 of {price vs its 200-day-
smoothed RS ratio} × {20-day RS momentum sign}. It is a **rotation** lens: built on a
200-day-smoothed relative-strength ratio, it confirms a turn weeks late, it is
*relative* (a sector can rotate to "improving" while still falling, just less than
SPY), and "improving" fires identically on a real bottom and on a bear bounce that
rolls over. Nothing in it separates a **durable** low from a **falling knife**.

## What we already had (and the gap)

* **Per-STOCK Bottom Confidence** — `engine.cycles.bottom_confidence`, walk-forward
  calibrated MONOTONE on 69k evals (`research/BOTTOM_CONFIDENCE.md`). A durability /
  drawdown-tail score. Lived only on `stock.html`.
* **Index buyable-washout gate** — `engine.dislocation`, the Fed-put master switch,
  Phase-0 hardened (`research/DISLOCATION_VALIDATION.md`). Lived only at the SPY level.
* **Gap:** nothing at the **sector** level except the RRG stages.

The Sector Bottom Radar points the *same validated machinery* at each sector ETF and
conditions it on the *same validated macro gate*. The only genuinely new question is
whether the separation **survives the move from single names to a sector index** —
which is what the Phase-0 tests.

## Method (no look-ahead)

Walk-forward over the **12 SPDR sector ETFs** (`XL*` + `SMH`), weekly step (5 bars) on
a trailing 600-bar window — the exact harness `research_bottom_confidence.py` uses.
State at bar *i* from `close[i-600:i+1]`; outcomes from `close[i+1:i+1+fwd]`.
Restricted to the bottoming population (DECLINE / BOTTOM WATCH / TURN SIGNALED /
FRESH BUY / COUNTERTREND BOUNCE). Macro gate (put-absent) read PIT from
`dislocation.master_switch_frame` over a daily Sahm (`SAHMREALTIME`, real-time
vintage) + 10y breakeven (`T10YIE`) series. **8,181 sector-bottoming evals; ~138
independent calendar clusters** (>63d apart, pooled — the honest effective-N).

Honest lens: forward **drawdown p10** (the tail you sit through) + **held21** (did the
cycle low survive 21 sessions), NOT endpoint return (sector ETFs in a ~27y bull all
drift up — every band has ~67% 63d hit-rate, so hit-rate is uninformative here).

## Result A — the per-stock score TRANSFERS to sectors (monotone)

Sector-bottoming evals, bucketed by the sector ETF's own `bottom_confidence`:

| bc band | n | fwd drawdown p10 (21d) | **held21** (low survived) | ret63 |
|---|---:|---:|---:|---:|
| 0–20  | 3,610 | −10.67% | **34.3%** | +3.66% |
| 20–40 | 2,805 | −7.61% | **64.0%** | +2.68% |
| 40–60 | 1,168 | −7.90% | **75.2%** | +2.06% |
| 60+   | 598 | **−6.39%** | **79.4%** | +2.39% |

**held21 is cleanly monotone — 34% → 79%, a 2.3× lift** — and the drawdown tail
shallows from −10.7% to −6.4% (monotone at the extremes; a minor mid-band wiggle at
40–60). Forward *return falls* with rising confidence (3.66 → 2.39) — the same
durability-for-upside trade the stock-level study found. The score is not degraded by
being applied to an index; if anything the held-rate separation is as clean as the
single-name version.

## Result B — the index Fed-put gate splits sectors too

| macro gate | n | fwd drawdown p10 (21d) | held21 | ret63 | hit63 |
|---|---:|---:|---:|---:|---:|
| **put-present** | 5,796 | **−7.41%** | **55.8%** | +3.69% | 70.5% |
| put-absent | 2,385 | −12.71% | 48.3% | +1.34% | 58.5% |

Put-present sector washouts had a **~5.3pp shallower drawdown tail**, +7.5pp higher
held-rate and **2.8× the forward return**. The index-level dislocation edge
(`research/DISLOCATION_VALIDATION.md`) carries to the sector level — in a put-absent
regime (recession or inflation-locked Fed) the same sector washouts kept falling.

## Result C — the combined selector (the actual product)

| selector | n | fwd drawdown p10 (21d) | **held21** | ret63 |
|---|---:|---:|---:|---:|
| **bc ≥ 40 AND macro put-present** | 1,349 | **−6.95%** | **78.3%** | +2.63% |
| everything else | 6,832 | −9.15% | 48.7% | +3.08% |

A sector that scores ≥40 on Bottom Confidence **while the index Fed-put is intact** held
its cycle low **78% of the time vs 49%** (a +29.6pp lift) with a meaningfully shallower
drawdown tail. That is the radar's "buyable washout" verdict, and it is a large, clean
separation on ~138 independent episodes.

## Result D — the knife temper is validated (counter-intuitive)

| washout state | n | fwd drawdown p10 (21d) | held21 | ret63 |
|---|---:|---:|---:|---:|
| **knife** (deep below 200d / still falling) | 409 | **−17.67%** | **30.3%** | **+6.98%** |
| not knife | 7,772 | −8.23% | 54.8% | +2.79% |

Deep sector washouts bounce the *hardest* (+6.98%/63d — the violent dead-cat) but hold
the low only 30% of the time and draw a −17.7% tail. This reproduces the stock-level
Phase-2 finding exactly: a deep stretch below the 200-day is a **falling knife, not a
higher-confidence bottom**. The radar surfaces it as `falling_knife` and the score's
washout temper already de-rates it.

## Honest ceiling & limits

* **Not a bottom oracle.** You cannot call the exact sector low. The radar trades some
  of the explosive bounce for a much higher chance the low holds — a risk/durability
  read, surfaced and labelled as such. Never alpha, never a sizer.
* **Effective-N.** 12 correlated ETFs → ~138 independent episodes. The claim is the
  monotone ORDERING + sign-consistency across A–D, not the exact magnitudes.
* **Member breadth is a LIVE confirmer only.** The per-sector constituent breadth
  (`member_breadth`: share washed-out and turning) is displayed context — the breadth
  close caches are ~1y deep, so this leg is *not* deep-backtested. The validated legs
  are the sector-ETF Bottom Confidence + the macro gate.
* **Survivorship is minimal** (sector ETFs, not single names) but the ~27y bull drift
  still inflates absolute returns — judged on drawdown + held-rate, never return.

## What shipped (engine + validation)

1. `engine/sector_bottom.py` — `sector_read` (validated per-sector core), `member_breadth`
   (live confirmer), `radar` (assembly + categorical verdict: buyable_washout /
   washout_forming / falling_knife / knife_regime / trend). Pure / leaf; the headline is
   the validated `bottom_confidence` verbatim — no new scored number is invented.
2. `scripts/sector_bottom_phase0.py` — the harness above (Results A–D reproducible).
3. `tests/test_sector_bottom.py` — verdict logic, macro-gate flip, breadth shares,
   radar sort, and the "no new score" invariant (10 tests).

UI wiring (onto the Sector Heat Board) is the next step, gated on this validation.
