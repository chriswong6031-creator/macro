# GD-1 U.S. Prophet defensive composition

**Question (packet §16):** was the absence of technology from U.S. actionable recommendations a repeatable consequence of canonical candidate evidence, an entry/availability gate, ranking, data absence, or chance?

**Answer:** On the **pit_live** board, technology was **not** absent on 2026-08-17: 29 of 127 buyable names (22.8%). On 2026-08-18 it was 6 of 52 (11.5%). Live `n_raw` is 2936 both days. The 4439→2936 and 241→52 figures in an unfiltered read mix in 1503 `recomputed_history` rows on 08-17 (114 of them buyable, `sector` NA). Prereg §11: that slice is not emission at `t`.

Tech share of live buyable **did fall** 22.8% → 11.5%. That is a same-session gate effect on 08-18, not proof the board pre-empted the crash. Do not infer "Prophet knew."

## Board identity (do not rebuild)

| stamp_date | board_definition | basis | n_raw | eligible | buyable |
|---|---|---|---|---|---|
| 2026-08-12 | us_prophet_v2 | recomputed_history only | 1508 | 125 | 113 |
| 2026-08-17 | us_prophet_v3 | **pit_live** | **2936** | **148** | **127** |
| 2026-08-17 | us_prophet_v3 | recomputed_history (do not use) | 1503 | 121 | 114 |
| 2026-08-18 | us_prophet_v3 | **pit_live** | **2936** | 115 | 52 |

Raw population is preserved in `data/us_prophet_rank/candidates/2026-08.parquet`. Compare live-to-live only.

Missing **pit_live** dates in August: everything before 08-17 except none — only 08-17 and 08-18 are `pit_live`. Earlier August stamps are recomputed history.

## Buyable sector mix

**2026-08-17 pit_live buyable (n=127)**

| bucket | n | share |
|---|---|---|
| tech (IT + Technology + Communication Services) | 29 | 22.8% |
| defensive (Healthcare/Health Care/Staples/Utilities/Real Estate + Consumer Defensive) | 36 | 28.3% |
| other | 62 | 48.8% |

**2026-08-18 pit_live buyable (n=52)**

| bucket | n | share |
|---|---|---|
| tech | 6 | 11.5% |
| defensive | 26 | 50.0% |
| other | 20 | 38.5% |

Tech share of live buyable fell 22.8% → 11.5%. Absolute tech buyable 29 → 6. Healthcare is the modal 08-18 buyable sector. That is **same-session** gate firing, not a pre-08-18 defensive allocation.

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

A chance-composition story is not needed to explain a 22.8% → 11.5% share move when buyable N also fell 127 → 52 on the same session the tape sold off. The 08-17 live board still carried 29 buyable tech names. That coexistence — LC BROKEN + 29 live buyable tech — is the fact. A restriction would have been a new policy, not something the board already did.

## Intraday

Historical intraday board quotes: **not retained**. `UNAVAILABLE`.
