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
