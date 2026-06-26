# Entry-gate Phase-0 — fresh-from-oversold swing entry (honesty check)

*Walk-forward, no look-ahead (state from close[i-600:i+1], outcomes from close[i+1:i+1+k]).
Panel = 116 deep-history names in `data/stocks` (a SURVIVOR set — today's liquid names — so every
number is an OPTIMISTIC bound, directional read only). Repro: `python -m scripts.entry_gate_phase0`.*

## What was tested
The revamp of `engine.cycles.mtf_alignment`: require a FRESH turn FROM A LOW (weekly
bear-recovering/basing + 3-day cross from oversold <25 + daily just-crossed) and EXCLUDE the
overextended chase. The user's stated thesis: such entries are "low-risk / won't get shaken out
right after entry." The honest arbiter is a PIVOT-relative stop (tight stop under the entry's swing
low), not a fixed % stop — that is how the strategy is actually traded.

## Result (step=12, pivot lookback=12, fixed stop −6%)

| bucket | n | stop dist (risk) | pivot stop-out 10d | pivot stop-out 21d | fwd mean21 | hit63 | mean63 |
|---|---|---|---|---|---|---|---|
| OLD gate (prior) | 26192 | 5.35% | 21.0% | 32.6% | 1.58% | 62.9% | 4.57% |
| NEW (PRIME+ARMED) | 6180 | 3.45% | 35.6% | 47.8% | 1.76% | 63.2% | 4.68% |
| PRIME (best combo) | 4821 | 3.16% | 38.1% | 49.7% | 1.84% | 63.8% | 4.66% |
| REMOVED (chase dropped) | 20715 | 5.89% | 17.2% | 28.7% | 1.51% | 62.7% | 4.52% |

## Honest read (two things the user's framing got right, one it got wrong)

1. **The SELECTION is right.** PRIME (the fresh-from-oversold "best combination") is the
   highest forward-return, highest-hit bucket (mean21 **1.84%** vs ALL 1.51%; hit63 **63.8%**),
   and the overextended chase the gate now DROPS (REMOVED) is the *weakest* forward bucket
   (mean21 **1.51%**, mean63 4.52%). Prioritising fresh oversold over the chase is return-accretive.

2. **The entries ARE lower-RISK per trade** — a tighter stop. PRIME sits **3.16%** above its
   pivot vs the chase's **5.89%**. You risk roughly *half* the distance per trade.

3. **But they are NOT "shakeout-free" — the opposite.** That tight stop is breached MORE often
   (PRIME 38% within 10d vs the chase's 17%). Oversold turns are volatile and frequently undercut
   their first pivot before working; the chased names get stopped LESS (wide stops) — they just
   earn less. So "we'll get shaken out on the chase, not on the fresh entry" is contradicted:
   it's the reverse on frequency.

**Net:** the new gate is a **tighter-risk + higher-reward + more-frequent-small-stops** profile —
risk-EFFICIENT (more reward per unit of stop), not risk-FREE. The right way to trade it is small
size + readiness to re-enter, not a wide "set and forget" stop. The `fix_sh10` column (a fixed −6%
stop, entry-blind) shows ~no difference (16.8%→18.5%) — confirming the edge is in the SELECTION and
the stop DISCIPLINE, not in dodging near-term volatility.

## Decision
Ship the gate (it does what was asked: drops the overextended chase, ranks fresh-oversold turns
first, never goes empty). KEEP the Bottom-Confidence durability read on the card as the secondary
signal. Correct the EXPECTATION on the card / in the doctrine: these are tighter-risk, higher-reward
entries that take more frequent small stops — not shakeout-free. Re-run on the offline deep-PIT
panel before treating any magnitude as more than directional.
