# Leader ⅓-starter sizing — Phase-0 (VERDICT: NO-GO)

**Question.** The board zeroes a name that trips the absolute extension brake
(`pct_vs_200dma >= 30%`, `engine/stock_score._STRETCH_BLOCK`) — verdict *"Extended — don't
chase; wait for a pullback"*, suggested size **avoid / 0%**. The deferred half of the
pullback buy-zone (`engine/pullback_zone.py`, move 3) proposed flipping that to a **⅓ starter now
+ add the rest on a pullback** for a non-parabolic leader in the 30–47% gray zone. That changes
what the board *recommends*, so it needs a gate before shipping.

**Why caution up front.** The brake's own deep-PIT calibration (`engine/stock_score:388`) already
found this cohort — names >35% above their 200d MA — has the **worst** forward return **and** the
**deepest** drawdown at every horizon. The flip would put (partial) size into exactly that cohort.

## Test

`scripts/leader_starter_size_phase0.py`. Monthly rebalances; cohort = gray-zone (30–47% over
200d), **not** parabolic (`ext_z < 2`), top-40% 12-1 momentum (a "leader"). Four entry rules,
each simulated over a 63-day forward hold per name, pullback = the 25%-over-200d line within 21d:

- **FULL_NOW** — full size at the rebalance (the chase the brake forbids; deterrent baseline).
- **STARTER_ADD** — ⅓ now; add the rest at the first pullback to the line, else stay ⅓.
- **WAIT_FULL** — 0 now; full only if it pulls back within 21d, else miss it (= what the buy-zone display already advises).
- **AVOID** — 0 (current behaviour).

Deep survivorship-clean PIT cache in CI; falls back to the available ~3y S&P-1500 cache locally
(**survivorship-biased → biases the starter UP**, so a NO-GO here is strong).

## Result (available ~3y cache, 20 rebalances, 573 gray-zone-leader entries, 48% pull back)

| rule | mean ret | median | p5 ret | mean DD | p5 DD | hit% | ret/DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| FULL_NOW | +8.0% | +2.4% | −33.7% | **−23.3%** | −47.3% | 54% | 0.34 |
| STARTER_ADD | +6.0% | +2.5% | −27.1% | −14.6% | −38.8% | 59% | 0.41 |
| **WAIT_FULL** | +5.0% | 0.0% | −24.6% | **−10.3%** | −37.5% | 27% | **0.49** |
| AVOID | 0 | 0 | 0 | 0 | 0 | — | — |

## Verdict — **NO-GO**

- **WAIT_FULL is risk-adjusted best** (ret/DD 0.49) — i.e., *waiting fully for the pullback*, which
  is exactly what the shipped buy-zone already tells the user to do.
- **STARTER_ADD** carries ~40% deeper drawdown (−14.6% vs −10.3%) for ~1pp more return → worse
  risk-adjusted (0.41 < 0.49) and fails the drawdown guard.
- This holds **even on the survivorship-biased cache that flatters the starter**; the deep cache
  would only widen the gap.

**Decision:** do **not** flip `_suggested_size`. The board keeps **avoid / 0** for extended
leaders. The move-3 buy-zone stays **display-only** — it already surfaces the best behaviour
(*wait for the pullback*) as actionable levels, without the board sizing into the worst-drawdown
cohort. Re-run with the deep cache in CI before revisiting; a GO would need it to overturn this.
