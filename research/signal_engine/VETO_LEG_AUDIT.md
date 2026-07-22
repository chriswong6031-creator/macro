# Veto-leg audit — what the NOT-TOPPED veto actually costs (2026-07-22)

**Trigger.** CRCL (2026-07-21): 2D MACD-RSI crossed, 2D StochRSI crossed, 3D StochRSI crossed
from oversold, weekly StochRSI floored (~0 for a month) and turning — yet the cascade surfaces
nothing. The binding blocker is one leg of the not-topped veto: `macd_bear` (3D RSI-MACD below
its signal), which at a genuine washout bottom is almost definitionally still true — the 3D
MACD is the *slowest* leg and the last to cross. `cascade()` hard-blanks **all** tiers when any
veto leg trips (`if not not_topped: return blank`, engine/confluence_tiers.py).

**Provenance finding (important on its own).** The validated T1–T4 table in TIERED_CASCADE.md
was measured **without** the not-topped veto — `tuning_harness.build_signals` has no topped leg
(`buy = mb_d & recent_sb_d & confirm_bull & rsi_ok`). The veto is a post-validation bolt-on
(the AMAT extended-top incident guard). Its cost/benefit was never measured. This audit
measures it, fire-conditionally, on the house ruler.

## Design (pre-registered before results; see veto_leg_audit.py docstring for full spec)

- **Base fire** = live-T2-shaped pre-veto event replicated with the *live* legs
  (2D RSI-MACD cross knowable that day ∧ recent3 ∧ confirm3 ∧ rsi_ok), deduped 5d.
- **Cells** by veto-leg state at fire: `P` passes; `Vm` macd_bear only (the CRCL class);
  `Vob` overbought only; `Vs` stoch-bear; `Vsm` stoch-bear+macd-bear.
- **Washout-motion stratifier** `W+` = weekly StochRSI D-min(8 closed wks) ≤ 10 ∧ weekly K×up
  within 2 closed weeks. Motion-conditioning only — depth-as-ranker stays dead (#1747).
- **Ruler** (house): next-close fill, −5% intrabar-low hard stop, 20d barrier; verdict metric =
  stop-out rate; clean = unstopped ∧ MFE ≥ 5%; fwd20 carried as context only.
- **Keep rule** (pre-registered): a leg earns its keep on a cell iff that cell stops out
  ≥ +3pp worse than `P`.
- **Panel**: data/stocks/*.parquet (232 files, 231 names with fires, 37,490 fires 1963→2026).

## Results

### Headline (stop% / clean%, −5% stop)

| Cell | Full history | Since 2023-06 |
|---|---|---|
| `P` (veto passes — what the board admits) | **41.8 / 40.6** (n=5,339) | **46.8 / 37.1** (n=404) |
| `Vm` (macd_bear only — CRCL class) | 42.6 / 39.1 (n=23,716) | **42.9 / 39.3** (n=2,026) |
| `Vm ∩ W+` (washed-out + weekly turn) | 44.0 / 39.7 (n=3,131) | **40.3 / 44.5** (n=283, 170 names) |
| `Vob` (overbought only) | **47.1** / 34.4 (n=543) | 36.1 / 47.2 (n=36, small) |
| `Vs` (3D stoch rolled over) | 41.7 / 38.4 (n=3,085) | 35.9 / 47.7 (n=306) |
| `Vsm` (fully rolled over) | 41.3 / 40.8 (n=4,802) | 43.5 / 41.0 (n=444) |

Sanity: `P` reproduces the validated T2 rate (published 40.6/42.5% — ruler agrees).

### Verdicts per leg (by the pre-registered rule)

- **`macd_bear` — FAILS its keep.** +0.8pp full-history; **−3.9pp (helps the wrong way) since
  2023**. Decade splits oscillate (1990s +5.0, 2000s −2.5, 2010s +1.2, 2020s −1.9) — noise-level
  protection, never a stable ≥3pp margin. Cost: it vetoes **4.4×** more fires than the gate
  admits (23,716 vs 5,339) — in the current window it blocks 83% of all T2-shaped fires.
  The board's *de facto* primary gate is an unvalidated leg pointing the wrong way this regime.
- **`stoch_ob` — EARNS its keep** (+5.3pp full-history; the AMAT case). Recent inversion is
  n=36, noted, not actionable.
- **`stoch_bear` — fails the +3pp rule on the pooled population** (±0pp) **but must stay** for
  T2 anyway: `long_bias` independently requires k3 ≥ d3, and the washout interaction is adverse
  (below).

### The washout-motion marginal is cell-specific (mechanism)

W+ minus W− stop%, since 2023: `Vm` **−3.1pp** (helps) · `Vs` **+14.7pp** (hurts) ·
`Vsm` **+7.8pp** (hurts) · `P` +3.3pp (n=14).

Read: a weekly washout-turn only adds value when the 3D **stoch** legs are constructive and
only the 3D **MACD** lags — i.e. the exact CRCL configuration. When the 3D stoch itself has
rolled over, the weekly turn "rescue" is a falling knife (+8 to +15pp stop tax). This is
coherent with Amendment-3 (deep×REVERSING was the strong cell; depth alone killed) and with
TIERED_CASCADE §4 (violent-selloff crosses get wicked through tight stops).

### Proximity honesty (where the lane lives — and where it doesn't)

`Vm ∩ W+` since 2023 by drawdown from 252d high:

| dd252 bucket | n | stop% | clean% | MFE med |
|---|---|---|---|---|
| −15..0% | 167 | 42.5 | 37.7 | 4.24 |
| **−30..−15%** | **96** | **34.4** | **55.2** | **6.47** |
| −50..−30% | 15 | 60.0 | 40.0 | 2.54 |
| ≤−50% | 5 | 20.0 | 80.0 | 15.06 (n=5 — anecdote tier) |

The tradable washout lane is the **−30..−15% pullback washout** (best cell in the whole study).
Deep-crash names (≤−30%) are stop-hostile under a −5% ruler **regardless of the veto** — the
admitted `P` cell in the same buckets stops out 50–77%. Nothing about the veto protects there;
the bar-width does the damage (a −5% stop on a 9%-daily-range name is a coin-flip wick).
CRCL itself (dd252 ≈ −67%) sits in the anecdote tier: the fires that work from there are
monsters (fwd20 med +29% on n=5), but n=5 is not evidence — it is a watch case, not a chase
case. Name concentration in `Vm∩W+`: top-5 names = 7.1% of fires — well spread.

## Recommendation (display-first; gauntlet at promotion — nothing here changes ranked tiers)

1. **Build a "Washout Watch" display shelf** on the US standouts surface: fires passing all
   live T2 legs (incl. `long_bias`, `stoch_ob`/`stoch_bear` clean) that fail not-topped **only
   via `macd_bear`**, tagged with washout context (weekly D-min, weekly-turn state, dd252
   bucket). Dimmed, plainly worded ("washed out, turning — earliest read; wide bars get
   stopped"), **never** ranked into the buy lane, **no Prophet origination**. This also finally
   implements the never-built TIERED_CASCADE §3 recommendation (surface below-200 T4 fires as
   dimmed context — same shelf, second admission reason).
2. **Pre-registered promotion gate** (before any ranking authority): shelf accrues on the
   forward board ledger from day one; promote to a scored tier only if, at ≥100 matured fires
   over ≥60 trading days, shelf stop% ≤ contemporaneous `P` stop% and clean% ≥ `P` clean%.
   Nulls printed on the surface either way.
3. **Do not delete `macd_bear` from the scored cascade now.** It failed its keep-test, but the
   decade oscillation says regime-dependence; the honest path is the forward shelf, not a
   retroactive gate rewrite. Revisit with the shelf's matured ledger.
4. **Keep `stoch_ob` and `stoch_bear`** exactly as-is (first earns it; second is structural to
   T2 and its washout interaction is adverse).

## Limitations

Deep-history panel is survivorship-lite (~230 names); 2D/3D resample conventions inherited
from the live engine; 5d dedup; no sector-clustered errors (name spread checked instead);
`W+` cells inside `P`/`Vs` are n≈14 (flagged, not read); fwd20 is context, never a verdict
(charter law). The study script is committed next to this memo (`veto_leg_audit.py`) — rerun:
`python3 research/signal_engine/veto_leg_audit.py`.

## Appendix — CRCL live case (2026-07-21)

Fires the full T2 leg set today (2D cross knowable 07-21, recent3 ✓, confirm3 ✓, rsi_ok ✓,
long_bias ✓), blocked solely by `macd_bear` ✓ — the audited `Vm` cell. Weekly D-min(8w) = 1.64
(floored, matches the operator's read); weekly turn is live-week true and completes under
closed-week discipline at Friday's close → strict `W+` then. dd252 = −67% (anecdote-tier
bucket: watch, don't chase; a −5% stop on current CRCL bar-width is near-certain to wick).
Separately, CRCL is outside the S&P 1500 and thus outside the alpha panel entirely — universe
admission is Lane A of this program and is required before *any* shelf could show it.

---

# Addendum — washout trigger-ladder study (operator directive 2026-07-22)

Operator ruling on the shelf proposal: **YES to washout surfacing, NO to a separate
display-only board — integrate into the existing standouts board's WAIT (watch) lane**, with
1W-crossover indication and a 2W crossover as a higher tier. Open design question raised: even
the 2D MACD cross felt ~20% late on CRCL — can the bottom be called earlier (fixed % bounce?
beta/Sharpe normalization?).

**First-principles frame.** A bottom cannot be known before demand shows; the earliest honest
EOD evidence is the first demand print. So the right shape is STATE + TRIGGER LADDER: the
washout state (weekly StochRSI floored ≥3 of last 6 closed weeks ≤10) is the standing context,
and each trigger rung is measured for LATENESS (median % off the trailing-20d low at first
knowable close) and stop economics — instead of pretending any one crossover "calls" the low.
Beta/Sharpe were considered and rejected as trigger inputs: bar-width (ATR), not beta, is the
correct per-name normalizer for a bounce test, and both are already implicit in the two rulers
below. Study: `washout_ladder_study.py` (pre-registered defs in docstring).

## Results (232-file house panel)

SINCE 2023-06 (n=1,867): `late%` = median % off 20d low at fire; `stop5%` = −5% intrabar stop;
`sstop%` = floor-stop touch rate; `risk%` = median entry-to-floor distance.

| Rung | n | late% | stop5% | clean% | MFE med | sstop% | risk% |
|---|---|---|---|---|---|---|---|
| W0 thrust (≥max(5%,1.5·ATR) up-bar, top-40% close, 1.5× vol) | 116 | 16.0 | 36.2 | **56.0** | **8.30** | **10.3** | 14.6 |
| **W1 2D StochRSI ×up from OS** | 357 | **4.7** | **36.4** | 52.1 | 7.21 | 46.2 | 4.9 |
| W2 2D RSI-MACD ×up (current cascade rung) | 447 | 6.1 | 39.8 | 46.5 | 6.53 | 37.4 | 6.4 |
| W3 1W StochRSI ×up | 404 | 5.9 | 38.4 | 46.8 | 6.67 | 37.6 | 6.2 |
| W4 2W StochRSI ×up | 543 | 9.7 | 40.9 | 46.6 | 6.15 | **26.3** | 9.9 |

Deep washouts only (dd252 ≤ −30%, full hist): every rung stops out 63–68% under −5%; MFE
medians are 10–12%; the thrust rung under a FLOOR stop survives 79.5% with median risk 19.6%.

## Read (what the ladder says)

1. **The earliest honest rung is the 2D StochRSI cross, not a bounce rule** — median +4.7% off
   the low, better stop-survival AND clean% than the 2D MACD rung it precedes. CRCL's "+20%
   late" was CRCL's bar-width (crypto-beta bars), not the rung's typical lateness (panel median
   +6%). No construction tested calls the low earlier without paying for it in stop-outs.
2. **The thrust bar is the ALERT, not the entry**: fired same-day it is +16% off the low with
   the worst tight-stop economics — but the best clean% (56) and MFE (8.3) and near-immunity to
   the floor stop (10.3%). Demand day = "the washout is live"; chase-entry on it is the mistake.
3. **Stop design dominates trigger design in this class.** −5% fixed stops are wicked at every
   rung in deep washouts (63–68%). The floor stop (washout low) survives — at the price of a
   disclosed 5–20% unit risk. The surface must therefore show risk-to-floor and say plainly:
   size for the floor stop, don't run a −5% stop on wide bars.
4. **Operator's 1W/2W hierarchy confirmed with one refinement**: 1W ≈ 2D-MACD grade
   (mid-ladder); the 2W cross is the durability tier — latest (+9.7%) but the most
   floor-secure oscillator rung (26.3% floor-touch). Higher score for 2W is honest as a
   CONFIRMATION tier, not an earliness tier.

## Revised deliverable (supersedes the standalone-shelf shape; same promotion prereg)

WAIT-lane integration on the existing standouts board: washout STATE chip (weeks at floor) +
rung chips (Demand day / Turning 2D / Confirming 2D-MACD·1W / Confirmed 2W) + lateness ("+X%
off the floor") + risk-to-floor line + plain-word stance ("watch — early turn; wide bars, size
for the floor stop"). Display-tier; never buy-lane; no Prophet origination; accrues through the
nightly board snapshots from day one; promotion gate unchanged (≥100 matured, ≥60td,
stop% ≤ P and clean% ≥ P on the forward ledger).
