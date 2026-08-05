# CN Prophet — 12-month CHASE x THEME-IGNITION study (phase-0)

Instrument `research/cn_prophet_audit/ignition_chase_study.py`; frozen cells in `ignition_chase_results.json`. Window **2025-08-01 → 2026-07-31** (241 CSI300 sessions), universe 1668 A-share names, 257 theme baskets. Generated 2026-08-04T07:46Z.

Motivated by the V1 loser audit (`RESULTS_2026-08-04.md`, PR #4500), whose chase x theme cell held **n=5**. This re-runs the same constructions at 12-month scale. **Everything below is in-sample and motivating-only.**

## DECISION-RELEVANT SUMMARY

1. **Chase x theme interaction: DOES NOT REPLICATE.** Chase events inside a HOT theme: n=3317, median excess -2.04pp, win 43.4%. Chase events with no qualifying theme: n=3694, median -1.51pp, win 45.3%. Gap **-0.53pp** at H=10; half-by-half gaps [0.01, -0.91] (SIGN FLIPS across halves).
2. **Theme ignition lead: PARTIAL (one leg only).** After a WARMING/HOT upgrade the basket itself ran median 1.25pp excess over 10 sessions (n=3391) against an all-cells basket control of 0.33pp (n=59624). Members printing a fresh admission-like event inside the next 10 sessions: median -1.46pp (n=3564) vs an all-admission baseline of -1.06pp (n=9547).
3. **Naive blanket chase veto: MIXED — the chase cohort is worse on median but better on mean/win_pct; no blanket verdict is honest.** All 7816 matured chase events pooled ran median -1.72pp excess, mean 0.98pp, win 44.7% (Wilson 43.6–45.8%), against a date-matched universe cell baseline of median -1.04pp, mean 0.25pp, win 43.9%. The chase cohort has a WIDER distribution than the tape in both directions, so a blanket veto deletes the right tail along with the left.
4. **What actually separated: relay position, not theme heat (MONOTONE early > mid > late).** Pooled across every theme state that has a relay count — early (<=1 other member limit-closed in [d-2, d]) median -1.17pp / win 46.0% (n=3459); mid -2.61pp / 42.3% (n=1225); late (>=4) -5.32pp / 36.0% (n=406). The V1 audit's intuition — that WHERE in a theme's relay you buy decides the outcome — survives; its proxy (is the theme HOT) does not. The ladder is a RANKING, not a green light: even the early rung sits below the universe median, and the ONLY name-level cell with n>=100 and a positive median excess is `WARMING|early` (n=591, 0.25pp). A relay-aware rule is therefore a candidate ORDERING or de-escalation input, not a buy trigger.

**Read this before acting on any row.** Forward windows overlap massively; theme cells are the same few dozen baskets on the same few dozen dates, so the effective n is far below the printed n. Basket membership is a single 2026-07-08 snapshot applied backward for twelve months — the one irreducible lookahead here, quantified in Caveats. No cell below has been through the gauntlet; nothing here promotes anything.

## A. Chase events by theme state at d

**A — theme state at admission — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT` | 3317 | 43.4% | 41.7–45.1 | -2.04 | 0.41 | -15.88 | 20.8 |
| `WARMING` | 805 | 47.0% | 43.5–50.4 | -1.35 | 1.11 | -15.71 | 20.56 |
| `none_unqualified` | 968 | 45.1% | 42.0–48.3 | -1.56 | 0.74 | -17.15 | 22.21 |
| `no_basket` | 2726 | 45.3% | 43.5–47.2 | -1.5 | 1.71 | -16.4 | 25.0 |
| `none_pooled(unqualified+no_basket)` | 3694 | 45.3% | 43.7–46.9 | -1.51 | 1.45 | -16.59 | 24.28 |
| `ALL` | 7816 | 44.7% | 43.6–45.8 | -1.72 | 0.98 | -16.24 | 22.37 |

**A — theme state at admission — H=21 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT` | 3199 | 45.3% | 43.6–47.0 | -2.15 | 1.52 | -21.73 | 30.1 |
| `WARMING` | 770 | 41.4% | 38.0–44.9 | -3.79 | 0.59 | -23.53 | 27.2 |
| `none_unqualified` | 901 | 42.0% | 38.8–45.2 | -3.43 | 1.25 | -22.79 | 29.43 |
| `no_basket` | 2596 | 44.5% | 42.6–46.4 | -2.71 | 3.64 | -22.21 | 38.23 |
| `none_pooled(unqualified+no_basket)` | 3497 | 43.9% | 42.2–45.5 | -2.95 | 3.02 | -22.41 | 36.33 |
| `ALL` | 7466 | 44.2% | 43.1–45.4 | -2.64 | 2.13 | -22.19 | 32.42 |

## B. Theme state x relay position

`early` = at most 1 OTHER member of the same theme printed a limit-close in [d-2, d]; `late` = 4 or more; `mid` = 2-3; `na` = the name sits in no covered basket, so the relay count is undefined rather than zero.

**B — theme x relay — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT\|early` | 2023 | 44.9% | 42.8–47.1 | -1.38 | 1.15 | -14.51 | 20.93 |
| `HOT\|mid` | 957 | 42.8% | 39.7–46.0 | -2.44 | -0.04 | -16.64 | 21.1 |
| `HOT\|late` | 337 | 35.9% | 31.0–41.2 | -5.54 | -2.72 | -21.17 | 19.45 |
| `WARMING\|early` | 591 | 50.6% | 46.6–54.6 | 0.25 | 2.0 | -14.89 | 20.64 |
| `WARMING\|mid` | 168 | 40.5% | 33.3–48.0 | -3.64 | -0.69 | -16.46 | 20.22 |
| `WARMING\|late` | 46 | 23.9% | 13.9–37.9 | -6.0 | -3.66 | -18.19 | 14.82 |
| `none_unqualified\|early` | 845 | 45.3% | 42.0–48.7 | -1.33 | 0.77 | -17.1 | 21.4 |
| `none_unqualified\|mid` | 100 | 40.0% | 30.9–49.8 | -3.76 | -0.61 | -16.9 | 22.02 |
| `none_unqualified\|late` | 23 | 60.9% | 40.8–77.8 | 6.62 | 5.37 | -26.11 | 32.12 |
| `no_basket\|na` | 2726 | 45.3% | 43.5–47.2 | -1.5 | 1.71 | -16.4 | 25.0 |
| `ANY_THEME\|early` | 3459 | 46.0% | 44.3–47.7 | -1.17 | 1.2 | -14.99 | 21.01 |
| `ANY_THEME\|mid` | 1225 | 42.3% | 39.5–45.1 | -2.61 | -0.18 | -16.68 | 21.45 |
| `ANY_THEME\|late` | 406 | 36.0% | 31.4–40.7 | -5.32 | -2.37 | -20.98 | 20.05 |

**B — theme x relay — H=21 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT\|early` | 1945 | 48.0% | 45.8–50.2 | -0.96 | 2.95 | -19.39 | 30.3 |
| `HOT\|mid` | 923 | 44.3% | 41.1–47.5 | -2.85 | 0.59 | -23.32 | 30.31 |
| `HOT\|late` | 331 | 32.3% | 27.5–37.5 | -7.43 | -4.26 | -30.87 | 27.27 |
| `WARMING\|early` | 569 | 44.3% | 40.3–48.4 | -2.3 | 2.5 | -20.55 | 28.41 |
| `WARMING\|mid` | 156 | 38.5% | 31.2–46.3 | -5.18 | -2.67 | -27.18 | 25.07 |
| `WARMING\|late` | 45 | 15.6% | 7.7–28.8 | -13.84 | -12.22 | -36.68 | 6.03 |
| `none_unqualified\|early` | 791 | 41.6% | 38.2–45.1 | -3.43 | 1.26 | -22.79 | 29.93 |
| `none_unqualified\|mid` | 90 | 43.3% | 33.6–53.6 | -3.93 | 0.1 | -26.65 | 27.61 |
| `none_unqualified\|late` | 20 | 50.0% | 29.9–70.1 | 0.08 | 6.02 | -19.77 | 27.35 |
| `no_basket\|na` | 2596 | 44.5% | 42.6–46.4 | -2.71 | 3.64 | -22.21 | 38.23 |
| `ANY_THEME\|early` | 3305 | 45.8% | 44.1–47.5 | -1.81 | 2.47 | -20.23 | 29.98 |
| `ANY_THEME\|mid` | 1169 | 43.5% | 40.6–46.3 | -3.4 | 0.12 | -24.05 | 29.76 |
| `ANY_THEME\|late` | 396 | 31.3% | 26.9–36.0 | -8.36 | -4.65 | -31.07 | 25.43 |

## C. Theme state x washout context (drawdown from the 252d high at d)

**C — theme x washout — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT\|deep_dd` | 104 | 36.5% | 27.9–46.1 | -4.48 | -3.02 | -17.64 | 15.32 |
| `HOT\|shallow_dd` | 3213 | 43.6% | 41.9–45.4 | -1.98 | 0.53 | -15.81 | 20.96 |
| `WARMING\|deep_dd` | 60 | 41.7% | 30.1–54.3 | -2.88 | -2.69 | -16.48 | 11.23 |
| `WARMING\|shallow_dd` | 745 | 47.4% | 43.8–51.0 | -1.11 | 1.42 | -15.5 | 21.29 |
| `none_unqualified\|deep_dd` | 142 | 32.4% | 25.2–40.5 | -5.44 | -3.96 | -16.99 | 10.45 |
| `none_unqualified\|shallow_dd` | 826 | 47.3% | 44.0–50.7 | -0.88 | 1.54 | -17.25 | 23.36 |
| `no_basket\|deep_dd` | 215 | 37.7% | 31.5–44.3 | -4.0 | -2.57 | -17.47 | 12.25 |
| `no_basket\|shallow_dd` | 2511 | 46.0% | 44.1–48.0 | -1.22 | 2.07 | -16.34 | 25.48 |

**C — theme x washout — H=21 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT\|deep_dd` | 88 | 27.3% | 19.1–37.4 | -9.24 | -6.49 | -24.66 | 12.52 |
| `HOT\|shallow_dd` | 3111 | 45.8% | 44.1–47.6 | -1.91 | 1.75 | -21.53 | 30.28 |
| `WARMING\|deep_dd` | 46 | 28.3% | 17.3–42.5 | -9.24 | -5.86 | -22.58 | 9.09 |
| `WARMING\|shallow_dd` | 724 | 42.3% | 38.7–45.9 | -3.57 | 1.0 | -23.64 | 28.05 |
| `none_unqualified\|deep_dd` | 115 | 31.3% | 23.5–40.3 | -8.3 | -4.38 | -22.79 | 19.17 |
| `none_unqualified\|shallow_dd` | 786 | 43.5% | 40.1–47.0 | -2.82 | 2.07 | -22.77 | 30.16 |
| `no_basket\|deep_dd` | 168 | 29.2% | 22.8–36.4 | -9.19 | -5.34 | -23.79 | 10.41 |
| `no_basket\|shallow_dd` | 2428 | 45.6% | 43.6–47.6 | -2.03 | 4.26 | -22.14 | 39.41 |

## D. What a naive blanket chase veto actually vetoes

**D — pooled chase vs universe — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `all_chase_events_pooled` | 7816 | 44.7% | 43.6–45.8 | -1.72 | 0.98 | -16.24 | 22.37 |
| `limit_close_leg_only` | 3262 | 42.2% | 40.6–43.9 | -2.44 | 0.15 | -16.07 | 19.85 |
| `trail21_leg_only` | 4554 | 46.4% | 45.0–47.8 | -1.21 | 1.57 | -16.38 | 23.98 |
| `universe_cell_baseline` | 382333 | 43.9% | 43.8–44.1 | -1.04 | 0.25 | -10.1 | 11.64 |

**D — pooled chase vs universe — H=21 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `all_chase_events_pooled` | 7466 | 44.2% | 43.1–45.4 | -2.64 | 2.13 | -22.19 | 32.42 |
| `limit_close_leg_only` | 3096 | 39.5% | 37.8–41.3 | -4.7 | -0.25 | -22.88 | 26.69 |
| `trail21_leg_only` | 4370 | 47.6% | 46.1–49.0 | -1.17 | 3.81 | -21.76 | 35.76 |
| `universe_cell_baseline` | 364021 | 42.3% | 42.2–42.5 | -2.05 | 0.7 | -14.55 | 18.34 |

68 events were dropped because their T+1 bar printed high==low==close (locked limit, unfillable at any price) — the same exclusion production grading makes.

## E. Ignition lead test

3459 theme upgrades (heat level today strictly above its level 5 sessions ago, deduped to one per basket per 5 sessions). Basket forward excess is close-to-close on the EW basket level — a basket is not tradeable, so no fill mechanics are applied to it. Member rows use the same T+1-fill grading as everything else.

**E — ignition lead — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `basket after ignition` | 3391 | 58.0% | 56.3–59.7 | 1.25 | 1.38 | -6.46 | 9.1 |
| `basket control (all cells)` | 59624 | 52.4% | 52.0–52.8 | 0.33 | 0.6 | -6.47 | 8.24 |
| `member fresh admission <=10d after ignition` | 3564 | 44.3% | 42.7–45.9 | -1.46 | 0.04 | -13.56 | 14.53 |
| `all admission-like events (baseline)` | 9547 | 45.3% | 44.3–46.3 | -1.06 | 0.35 | -12.56 | 14.44 |
| `chase inside HOT, rel20 slope5 >= 0` | 2636 | 43.7% | 41.8–45.6 | -1.97 | 0.48 | -15.88 | 20.69 |
| `chase inside HOT, rel20 slope5 < 0 (fading)` | 681 | 42.3% | 38.6–46.0 | -2.42 | 0.14 | -15.84 | 21.2 |

**E — ignition lead — H=21 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `basket after ignition` | 3315 | 54.1% | 52.4–55.8 | 0.89 | 1.62 | -10.15 | 14.99 |
| `basket control (all cells)` | 56797 | 53.4% | 53.0–53.8 | 0.65 | 1.44 | -8.58 | 12.83 |
| `member fresh admission <=10d after ignition` | 3352 | 42.9% | 41.2–44.6 | -2.72 | -0.1 | -19.28 | 21.84 |
| `all admission-like events (baseline)` | 8834 | 42.7% | 41.7–43.8 | -2.61 | 0.24 | -18.34 | 20.69 |
| `chase inside HOT, rel20 slope5 >= 0` | 2567 | 44.5% | 42.6–46.5 | -2.3 | 1.37 | -21.88 | 30.33 |
| `chase inside HOT, rel20 slope5 < 0 (fading)` | 632 | 48.4% | 44.5–52.3 | -0.9 | 2.14 | -20.52 | 27.89 |

## F. Robustness — halves and a curated-only theme assignment

**F — H1_2025_08_2026_01 — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT` | 1878 | 42.3% | 40.1–44.6 | -2.25 | 1.03 | -13.78 | 20.26 |
| `WARMING` | 386 | 49.2% | 44.3–54.2 | -0.34 | 2.51 | -11.46 | 20.86 |
| `none_unqualified` | 318 | 43.7% | 38.4–49.2 | -1.78 | 0.52 | -13.35 | 17.07 |
| `no_basket` | 1229 | 41.7% | 38.9–44.4 | -2.38 | 0.86 | -14.0 | 20.25 |

**F — H2_2026_02_2026_07 — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT` | 1439 | 44.8% | 42.3–47.4 | -1.79 | -0.39 | -19.79 | 20.98 |
| `WARMING` | 419 | 44.9% | 40.2–49.7 | -1.82 | -0.18 | -17.66 | 20.48 |
| `none_unqualified` | 650 | 45.8% | 42.1–49.7 | -1.3 | 0.84 | -19.41 | 23.61 |
| `no_basket` | 1497 | 48.4% | 45.8–50.9 | -0.66 | 2.4 | -19.57 | 27.33 |

No A-cell median changed sign between halves.

The curated-only pass re-assigns every name's theme using ONLY the 22 hand-curated baskets (seeded 2021, not a 2026 vendor snapshot), so it is the closest thing here to a membership-drift control:

**F — curated-only assignment — H=10 sessions**

| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |
|---|---|---|---|---|---|---|---|
| `HOT` | 755 | 47.9% | 44.4–51.5 | -0.71 | 2.11 | -13.42 | 21.92 |
| `WARMING` | 134 | 36.6% | 28.9–45.0 | -3.35 | -1.61 | -16.53 | 15.3 |
| `none_unqualified` | 215 | 45.1% | 38.6–51.8 | -1.69 | 0.2 | -13.91 | 17.85 |
| `no_basket` | 6712 | 44.4% | 43.3–45.6 | -1.8 | 0.93 | -16.51 | 22.98 |
| `none_pooled(unqualified+no_basket)` | 6927 | 44.5% | 43.3–45.6 | -1.79 | 0.9 | -16.47 | 22.66 |
| `ALL` | 7816 | 44.7% | 43.6–45.8 | -1.72 | 0.98 | -16.24 | 22.37 |

## Caveats — read these as part of the result

- **Membership lookahead (the big one).** `data/baskets_china_ths/membership.json` is byte-identical to the 2026-07-08 THS snapshot and carries no `removed` rows and no in-window `added` dates: it is TODAY's composition applied backward for twelve months. The only two point-in-time snapshots in the repo are 8 calendar days apart and already differ by 7.7% of member-slots once both are filtered to the price cache, so a 12-month backward application is a material and unquantified composition bias. Its direction is knowable even if its size is not: a name sits in the 2026 concept board partly BECAUSE it moved with that theme, so every HOT/WARMING cell is flattered and every no-theme cell is the residue. The curated-only pass in table F is the closest available control, not a fix.
- **A chase event helps cause its own theme's HOT tag.** rel20 and breadth are computed over ALL covered members INCLUDING the event name (production's definition, kept deliberately). The median basket here holds 13 covered members, so one member closing limit-up moves its own basket's 20d EW return by roughly 1.5pp single-handedly, and the same close puts that member above its own 20d MA in the breadth count. Part of 'this chase event sat in a HOT theme' is therefore mechanical rather than contextual, which is one plausible reason the theme axis in table A separates nothing. The relay count in table B does NOT have this problem — it excludes the event name by construction.
- **Young names.** 26 of 1020 basket members have under 200 sessions of price history before the window opens, so their early-window breadth and rel20 contributions rest on short series.
- **Overlapping windows.** Events cluster on the same dates and inside the same themes; a 10-session forward window overlaps the next event's. The printed n counts events, not independent observations. Treat every median as descriptive.
- **No CI theater.** The only interval reported is a Wilson interval on win%, which is a binomial statement and still ignores the overlap above. No p-values, no bootstrap on medians, no significance claim anywhere.
- **In-sample.** Thresholds (18.5%/9.5% band, +25%/+3% chase leg, rel20 5/0, breadth 0.60/0.50, relay 1/4, dd -25%) were fixed BEFORE this run from production and from the V1 audit, not fitted here — but the window, the cohorts, and the cuts were all chosen after seeing the V1 result. Nothing here is out-of-sample in the sense that matters.
- **Horizon maturation.** Events late in the window cannot mature: an H=21 outcome needs 21 further sessions and the price store ends 2026-08-03. H=21 cells are therefore built on an earlier, smaller slice of the window than H=10 cells — they are not the same cohort re-measured.
- **Survivorship.** `data/china_stocks` is the live price cache; names delisted before it was built are absent from both the universe and every basket.
- **Theme assignment is coarse.** A name in several baskets is assigned the single strongest qualifying one by rel20 (production's rule). Multi-theme names therefore contribute to exactly one cell, and the choice is made with same-day data only.
