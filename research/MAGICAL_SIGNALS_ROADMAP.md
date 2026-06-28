# "Making the signals magical" — what's real, what isn't (tested)

**Question (user):** is the two-gauge + cycle-top + anticipation work *enough*? How do we take it
one step further and make it magical? Researched (4-agent literature workflow) + TESTED on our own
data (deep survivor names 1962-2026; non-survivor small-caps 2022-2026; net of cost).

## The honest verdict: hygiene done, edge barely started
Everything shipped so far (two-gauge, cycle-top fix, anticipation→ordering-only) is **hygiene** — it
STOPS bad signals from sizing capital. It generates almost no return-alpha. Single-name direction is a
coin-flip; a small shop cannot win there. The real, defensible edge — confirmed by both the literature
and our tests — is **portfolio construction × risk × breadth × cost-discipline, NOT prediction.**

## What we TESTED (measured on our data)
| idea | gross / survivor | NET of cost, NON-survivor | verdict |
|---|---|---|---|
| short-term reversal (cross-sectional) | rank-IC +0.028 t=7.0; +12.9%/yr; 4× in high-VIX | **−2 to −8%/yr** (10–20bps); banding/liq didn't flip it | **MIRAGE net of cost** — survivor + turnover ate it |
| momentum 12-1 long-only tilt | Sharpe 0.37 (60y deep) | **Sharpe +0.71 (4y smallcap), low turnover** | **ROBUST** — our existing edge, more robust than the DSR-fail story |
| signal stacking (mom⊥rev, corr −0.06) | blend IC 1.42× best single (deep) | blend 0.68 < momentum-alone 0.71 (smallcap) | only helps if the ADDED leg has net edge; reversal doesn't → dilutes |
| vol-managed sizing (Moreira-Muir) | SPY 0.64→0.76, EqW 1.07→1.22 | (absolute Sharpe lever, selection-agnostic) | **likely real free Sharpe** (+0.11–0.15), needs cap/cost discipline |

**Key literature refinements (why naive reversal fails, and the salvage path):** reversal = a
LIQUIDITY-PROVISION premium (Nagel 2012) → strongest in stress (our 4× high-VIX is the textbook twin),
but ~100%+ turnover means net≈0 broad (Novy-Marx-Velikov). It survives ONLY as RESIDUAL reversal
(strip industry+beta+cash-flow-news; Blitz/Da-Liu-Schaumburg) + turnover-conditioning (reversal in
LOW-turnover names, momentum in HIGH-turnover — Medhat-Schmeling sign-flip) + banding + large-cap. Our
test had liquidity+banding but NOT residualization/turnover-conditioning, so the large-cap question is
UNRESOLVED (deep survivor +0.71 vs smallcap −0.26); settling it needs a non-survivor LARGE-cap PIT
panel + the full residual form. Until then, presume the survivor gross is inflated 20–30% and reversal
is NOT sized capital.

## The magical synthesis (4 composable, mostly selection-agnostic modules)
1. **SELECTION** — a daily cross-sectional COMPOSITE z (`engine/signal_stack.py`): residual momentum
   (kept as a decorrelated combo input despite DSR-failing solo — the Fundamental-Law multiplier) +
   value + quality + one orthogonal slow leg (analyst-revisions/insider/seasonality), sector-neutral,
   equal/lightly-shrunk-IC weighted. (Reversal only if the residual+large-cap net-of-cost proof passes.)
2. **REGIME** — two distinct dials: a DISPERSION/correlation gate sizing SELECTION conviction (lean in
   when dispersion/VIX high), and the BREADTH/trend/LIQUIDITY overlay (our one robust edge) gating NET
   market exposure. Discrete 2–3 states, frozen thresholds (avoid the continuous-curve overfit).
3. **SIZING** — Layer A inverse-vol / Ledoit-Wolf-shrunk risk-parity (no name dominates book risk);
   Layer B a CAPPED (≤1.5) vol-target scalar (EWMA→HAR) cutting gross in stress. The +0.1–0.15 Sharpe
   drawdown lever. **Load-bearing reconciliation:** book vol-sizing de-grosses in high-VIX while
   reversal pays MORE there — size the BOOK by vol, rotate the MIX by dispersion/VIX; wire explicitly.
4. **LONG-ONLY TILT** — multiplicative `active_w = bench_w·clip(1+k·z, 0.5, 1.5)`, continuous rank
   (protect the transfer coefficient), ADV/price/cap screens, banded rebalance.

## Honest ceiling (no overclaiming)
A drawdown-controlled, breadth-driven long-only tilt realizing **~0.4–0.6 IR before costs** (the
long-only transfer-coefficient haircut ~halves the ~0.9–1.1 gross IR), with a meaningfully better
drawdown / left-tail (vol-management, crash-kurtosis compression). After realistic cost on a liquid
panel the selection edge shrinks toward the thin residual-reversal/momentum figure. **NOT** a high-Sharpe
alpha machine; NOT any per-name directional edge; NOT capacity beyond a few hundred $M on fast legs.

## Highest-EV next steps (ranked)
1. **BUILD the vol-managed / risk-parity SIZING overlay** — the one clearly-real, implementable,
   selection-agnostic Sharpe/drawdown lever (+0.1–0.15). Lowest risk, immediate value. `engine/vol_forecast.py` exists.
2. **Lean into the momentum tilt** (robust both universes) + a DISPERSION/breadth regime gate on gross.
3. **Reversal = research item, not capital:** needs a non-survivor LARGE-cap PIT panel + residual +
   turnover-conditioned form + a strict net-of-cost DSR bar before it earns size; at most an
   entry-ordering nudge meanwhile.
4. Keep direction/anticipation firewalled to entry-ordering (done).

The "magic" is real but modest, and it is engineering — risk, breadth, cost-discipline, regime — not
prophecy. The biggest single unproven gate remains reversal's net-of-cost survival on a clean panel.
