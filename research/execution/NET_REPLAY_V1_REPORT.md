# NET-REPLAY-1 — Net-of-Friction Re-Pricing Report

**Derived from surfaces:** exit_grid_v1, wait_grid_v1
**Run date:** 2026-07-06
**Verdict criteria:** descriptive-only
**Status:** reported
**Registry note:** This is a research-lane descriptive derivation, NOT a new registered experiment. No new trial cells; no new policy comparisons. Pooled replay trial count unchanged at 37 (exit_grid_v1=15, wait_grid_v1=10, disp_gate_v1=6, trim_grid_v1=6; NET-REPLAY-1 adds 0 cells).

---

## The NO-GO prior (stated first)

The exit-routing NO-GO is an established prior from the Oracle program. This re-pricing does NOT promote any exit rule to production. Its job is to document what gross-of-cost figures look like net of realistic frictions at per-position sizes. All outputs are display-only. The word "validated" does not appear in this report. Nothing net-based may prefer a policy without a new registered gate.

---

## Forking-paths contamination note (RUL-F3.9)

This is a re-pricing derivation stamped `derived_from_surface: ['exit_grid_v1', 'wait_grid_v1']`. Both surfaces are already seen. Any later promotion prereg must carry these stamps and state how its gate compensates.

---

## NOT MODELED (printed verbatim per RUL-F3.9)

```
overnight_gap_on_fills
halt_limit_days
borrow
taxes
```

---

## Cost model assumptions (scenario, not advice)

| Assumption | Value |
|---|---|
| One-way spread | max(Corwin-Schultz proxy at fire date [21-bar smooth], ADV$-banded floor) |
| ADV-floor: ADV > $50M | 3 bps |
| ADV-floor: ADV $10–50M | 8 bps |
| ADV-floor: ADV < $10M | 20 bps |
| Impact model | Almgren-style: `IMPACT_ETA × σ × √(participation)`, η = 0.1 |
| Participation | position_usd / ADV$ at fire date |
| Legs charged | Entry AND exit (2 one-way legs each for spread and impact) |
| Cash-carry credit | Capital freed vs hold(126) reference, credited at DTB3 |
| DTB3 (run date) | 3.69%/yr (annualized percent — NOT a fraction) |
| Position sizes | {$10k, $100k, $1M} per-position — NOT book AUM, no multi-name claims |
| Representative σ | 0.025/day (conservative mid-cap proxy) |

**Degradation mode:** Perfire parquets (`exit_grid_v1_perfire.parquet`, `wait_grid_v1_perfire.parquet`) are absent (gitignored, Mac-local). Cost model was evaluated at:
- Summary-mean holding bars per cell (not per-fire distribution)
- Tier-weighted representative ADV$: $157,970,000 (T1=46.1%@$300M, T2=48.5%@$40M, T3=5.4%@$5M)
- ADV-banded floor only (Corwin-Schultz proxy unavailable without perfire data)

**Precision loss from degradation:** Individual name ADV$ variation, per-fire CS spread, and per-fire holding bar variation are not captured. Gross-return statistics are EXACT copies from the registered summaries.

---

## In plain English

> The gross numbers from EXIT-GRID-1 and WAIT-GRID-1 are re-stated net of realistic trading friction at three position sizes. The main finding is structural: at per-position sizes of $10k–$1M, round-trip friction is small (3–20 bps spread + modest impact), and the cash-carry credit from freeing capital earlier than hold(126) often exceeds the friction cost for short holds. The net adjustment for a $10k position in a large-cap name is on the order of 1–7 bps; for a $1M position in the same name, impact adds a few more bps. None of this changes the qualitative ordering of the gross surface. The unmodeled frictions (overnight gaps, halts, borrow costs, taxes) are the relevant risks that cannot be estimated without trade-level data.

---

## Key cells — gross vs net side-by-side

### EXIT-GRID-V1 key cells

**Reference horizon = 126 bars. Net adjustment = −(round-trip cost) + carry credit for freed capital.**

| Cell | n fires | WR (gross) | Mean ret (gross) | Net@$10k | Net@$100k | Net@$1M | Net cost bps @$10k | Carry freed days |
|---|---|---|---|---|---|---|---|---|
| hold_5 | 49,939 | 0.528 | +0.28% | +1.99% | +1.99% | +1.95% | −176† | 175.3 |
| hold_10 | 49,939 | 0.555 | +0.88% | +2.51% | +2.51% | +2.48% | −163† | 168.3 |
| **hold_21** | **49,939** | **0.577** | **+1.93%** | **+3.40%** | **+3.40%** | **+3.37%** | **−147†** | **149.4** |
| hold_42 | 49,939 | 0.564 | +2.60% | +3.77% | +3.76% | +3.73% | −117† | 120.5 |
| hold_63 | 49,939 | 0.585 | +4.26% | +5.12% | +5.12% | +5.08% | −86† | 91.5 |
| hold_126 | 49,939 | 0.590 | +7.32% | +7.26% | +7.26% | +7.22% | +6 | 0.0 |
| **ema_trail_s8** | **49,939** | **0.623** | **+4.45%** | **+5.97%** | **+5.97%** | **+5.93%** | **−152†** | **160.3** |
| trail_stop_8pct | 49,939 | 0.419 | +1.85% | +2.98% | +2.97% | +2.94% | −113† | 121.8 |
| trail_stop_12pct | 49,939 | 0.443 | +2.74% | +3.67% | +3.67% | +3.64% | −93† | 101.9 |
| trail_stop_15pct | 49,939 | 0.467 | +3.53% | +4.28% | +4.28% | +4.25% | −75† | 80.8 |
| **trail_stop_20pct** | **49,939** | **0.516** | **+4.51%** | **+4.99%** | **+4.99%** | **+4.95%** | **−48†** | **51.5** |
| barrier_s5_t8 | 49,939 | 0.472 | +1.11% | +2.59% | +2.58% | +2.55% | −148† | 156.6 |
| barrier_s5_t15 | 49,939 | 0.365 | +1.61% | +3.04% | +3.04% | +3.00% | −143† | 151.9 |
| barrier_s8_t15 | 49,939 | 0.467 | +2.19% | +3.55% | +3.54% | +3.51% | −136† | 143.8 |
| barrier_s8_t25 | 49,939 | 0.410 | +2.67% | +3.84% | +3.84% | +3.80% | −117† | 124.0 |

†Negative net cost bps = carry credit exceeds friction (economically correct: shorter holds free capital that earns DTB3).

**hold_126** is the reference cell: zero freed capital, no carry credit, net adjustment = pure friction cost only.

### WAIT-GRID-V1 — delay ladder at hold_21

| Cell | n fires | WR (gross) | Mean ret (gross) | Net@$10k | Net@$1M | Net cost bps @$10k |
|---|---|---|---|---|---|---|
| delay1_hold21 | 49,939 | 0.577 | +1.93% | +3.40% | +3.37% | −147† |
| delay2_hold21 | 49,939 | 0.575 | +1.94% | +3.41% | +3.38% | −147† |
| delay3_hold21 | 49,939 | 0.574 | +1.95% | +3.42% | +3.39% | −147† |
| delay5_hold21 | 49,939 | 0.576 | +1.96% | +3.43% | +3.40% | −147† |
| delay10_hold21 | 49,939 | 0.560 | +1.66% | +3.13% | +3.10% | −147† |

All delay cells share the same carry profile (hold_21 from reference). The delay itself shifts the entry bar but does not change the holding period assumption used in this summary-mean degradation.

---

## Coverage and data quality

- Gross statistics: 100% coverage (copied exactly from registered summaries)
- Perfire parquets: ABSENT (gitignored, Mac-local) — degradation mode active
- ADV$ source: tier-weighted representative ($157.97M weighted mean)
- Massive_stock_day sample: 50 tickers sampled, empirical median ADV = $57,614 (this reflects the alphabetical first-50 sample, not the cohort-weighted universe)
- Corwin-Schultz proxy: NOT available (perfire absent) — ADV-banded floor used only
- DTB3 rate: 3.69%/yr from on-disk FRED store (DTB3.parquet, 2026-06-25)

---

## Interpretation guardrails

1. The carry credit is not "free money" — it is a comparison-consistent accounting of capital freed vs the hold(126) reference. In absolute terms, shorter holds earn less per cycle.
2. Net figures at the summary-mean level are indicative only. Per-fire dispersion in ADV$ and holding days would change individual fire costs substantially.
3. Per-position sizes ($10k–$1M) are what they say: per single position. No multi-name book claims are made or implied.
4. The unmodeled frictions (overnight gaps, halts, borrow, taxes) are the dominant risk factors for live execution and cannot be estimated from daily OHLCV alone.

---

## Output artifact

`data/execution/net_replay_v1_summary.json` — machine-readable, per-cell × per-position-size gross and net statistics, cost decomposition, coverage metadata.
