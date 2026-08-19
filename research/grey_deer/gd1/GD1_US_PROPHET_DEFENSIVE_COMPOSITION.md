# GD-1 U.S. Prophet defensive composition

**Question (packet §16):** was the absence of technology from U.S. actionable recommendations a repeatable consequence of canonical candidate evidence, an entry/availability gate, ranking, data absence, or chance?

**Answer:** On 2026-08-17, technology was **not** absent. It was 29 of 241 buyable names (~12%). On 2026-08-18, buyable collapsed 241 → 52 and technology buyable 29 → 6 (~12% again). The shelf *looked* more defensive because **N collapsed** and Healthcare became the modal buyable sector, not because Prophet allocated away from tech before the 08-18 session.

Do not infer "Prophet knew the crash."

## Board identity (do not rebuild)

| stamp_date | board_definition | n_raw | on_board | eligible | buyable |
|---|---|---|---|---|---|
| 2026-08-12 | us_prophet_v2 | 1508 | 0 | 125 | 113 |
| 2026-08-17 | us_prophet_v3 | 4439 | 140 | 269 | 241 |
| 2026-08-18 | us_prophet_v3 | 2936 | 134 | 115 | 52 |

Raw population is preserved in `data/us_prophet_rank/candidates/2026-08.parquet`. Era stamp on rows includes `anchor_era = abs-session-2026-08-06`.

Missing emission dates in August: 03, 04, 10, 11, 13, 15.

## Buyable sector mix

**2026-08-17 buyable (n=241)** — bucketed as in the prereg:

| bucket | n | share |
|---|---|---|
| tech (IT + Technology + Communication Services) | 29 | 12% |
| defensive (Healthcare/Health Care/Staples/Utilities/Real Estate + Consumer Defensive) | 36 | 15% |
| other | 176 | 73% |

**2026-08-18 buyable (n=52):**

| bucket | n | share |
|---|---|---|
| tech | 6 | 12% |
| defensive | 26 | 50% |
| other | 20 | 38% |

Tech **share of buyable is unchanged**. Defensive share rose because other/tech names left the buyable set faster than Healthcare/Energy.

## Why tech names were not buyable (08-18, tech-like n=487)

Copied vocabulary, not paraphrased:

| gate_reason | n |
|---|---|
| `flat: sell` | 219 |
| `held but topped/rolled-over — no longer a fresh entry` | 66 |
| `buy blocked by filter: counter-trend, held but no 200-reclaim` | 48 |
| `buy blocked by filter: failed next-bar hold` | 42 |
| `buy blocked by filter: counter-trend, no 200-reclaim/hold` | 41 |
| `flat: cut` | 22 |
| `buy blocked by filter: veto: bearish divergence` | 16 |
| `held but risen for many days (cross 2+ ticks ago) — no longer a fresh entry` | 11 |
| `insufficient history` | 8 |
| `early advance-warning (no open buy)` | 6 |

Lane: `not_on_board` 466 / `watch` 10 / `buy` 6 / `leaders` 3 / `laggards` 2.

This is **canonical gate vocabulary** (trend/reclaim/hold/rollover/divergence), not a Grey Deer duration score and not a missing-data hole for the names that have `gate_reason`.

08-12 has **empty `sector`** on the v2 file — sector composition that day is **data absence**, not a defensive call.

## Disposition vs chance

A chance-composition story would predict tech share jittering randomly. Observed tech share of buyable is 12% on both 08-17 and 08-18. The change that needs explaining is **buyable N**, which is the gate stack firing on the 08-18 tape — **same-session**, therefore not an anticipatory defensive allocation.

## Intraday

Historical intraday board quotes: **not retained**. `UNAVAILABLE`.
