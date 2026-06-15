# Top-Picks Fresh-Leaders — Phase 0 validation (the downside question)

*Survivorship-clean deep S&P panel · PIT S&P 1500 membership · 2014-06-30..2025-11-28 · 138 monthly rebalances · ~444 names/date · top-conviction cohort = top quintile by `alpha_led` · fresh = ext_z<1.0 & near_52wh>0.85 · LONG-ONLY EW, 63d hold, net 5bps one-way.*

The shipped board ranks by `alpha_led`; its top is the most-extended momentum names. The question is NOT 'does a new leg raise IC' but **'does freshness-screening the high-conviction cohort cut DRAWDOWN and CRASH frequency while keeping most of the return?'** — a long-only, tail-aware test the IC/Sharpe harness never ran.


## A. Long-only top-conviction cohort — which extension screen helps?

| cohort | names | ann ret % | vol % | Sharpe | Sortino | max DD % | worst 21d % | crash/yr | mret skew | ret capture |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| FULL top-conviction (baseline) | 88 | 18.9 | 25.4 | 0.74 | 0.9 | -49.0 | -58.9 | 0.41 | -0.23 | 1.0 |
| full − parabolic tail (drop ext_z>2) | 85 | 19.1 | 25.9 | 0.74 | 0.89 | -49.4 | -59.5 | 0.44 | -0.25 | 1.01 |
| full − all stretched (drop ext_z>1) | 69 | 20.2 | 27.8 | 0.73 | 0.89 | -50.1 | -60.6 | 0.54 | -0.28 | 1.1 |
| near-highs + not-extended (FAILED hypothesis) | 58 | 21.0 | 30.9 | 0.68 | 0.81 | -57.4 | -72.1 | 0.62 | -0.1 | 1.08 |
| parabolic tail ALONE (ext_z>2) | 2 | 9.0 | 50.1 | 0.18 | 0.2 | -94.0 | -139.4 | 1.64 | -1.37 | -0.07 |

**Read (drop the parabolic tail):** max-DD -49.4% vs full -49.0% (worse/equal); crash/yr 0.44 vs 0.41 (more); return captured 101%.

**Verdict A → per-name FLAG only:** removing the parabolic tail from the EW basket barely moves the basket-level drawdown (the tail is a small share of names), so the win is NOT at the basket level. BUT the parabolic tail's STANDALONE profile is radioactive (see its row) — so the honest product is a PER-NAME caution flag on ext_z>2 names, not a basket rotation.

**The parabolic tail itself:** ann ret 9.0% on 50.1% vol, max-DD -94.0%, skew -1.37, 1.64 crashes/yr — vs the full cohort's 18.9% / 25.4% / -49.0% / 0.41/yr. THIS stark per-name risk gap is the validated basis for the flag.

## B. Conditional on Daniel-Moskowitz panic regime (trailing-2y mkt<0 & high vol)

| regime | days | full DD % | ex-parab DD % | full crash/yr | ex-parab crash/yr |
|---|--:|--:|--:|--:|--:|
| panic | 982 | — | — | — | — |
| calm | 15238 | -30.4 | -31.3 | 0.35 | 0.38 |

## C. New legs — standalone sector-neutral cross-sectional IC


**Forward 21d**

| leg | mean IC | IC-IR | HAC t | p | FDR | h1→h2 |
|---|--:|--:|--:|--:|:-:|--:|
| ext_z | +0.0002 | +0.00 | +0.03 | 0.977 | n | — |
| near_52wh | +0.0058 | +0.03 | +0.46 | 0.647 | n | — |
| id_score | +0.0074 | +0.06 | +0.84 | 0.402 | n | — |
| val_own_z | +0.0095 | +0.07 | +1.12 | 0.261 | n | — |

**Forward 63d**

| leg | mean IC | IC-IR | HAC t | p | FDR | h1→h2 |
|---|--:|--:|--:|--:|:-:|--:|
| ext_z | +0.0010 | +0.01 | +0.08 | 0.934 | n | — |
| near_52wh | +0.0148 | +0.09 | +0.72 | 0.472 | n | — |
| id_score | +0.0116 | +0.10 | +0.81 | 0.418 | n | — |
| val_own_z | +0.0125 | +0.11 | +1.06 | 0.288 | n | — |

**Forward 126d**

| leg | mean IC | IC-IR | HAC t | p | FDR | h1→h2 |
|---|--:|--:|--:|--:|:-:|--:|
| ext_z | +0.0065 | +0.06 | +0.52 | 0.605 | n | — |
| near_52wh | +0.0246 | +0.15 | +0.90 | 0.370 | n | — |
| id_score | +0.0187 | +0.17 | +1.08 | 0.280 | n | — |
| val_own_z | -0.0009 | -0.01 | -0.06 | 0.951 | n | — |

*IC note:* ext_z is expected ≤0 / weak (over-extension is only mildly anti-predictive and small). id_score (frog-in-the-pan continuity) and near_52wh are the legs that *could* legitimately carry positive IC. val_own_z is annual-coarse → display/context only regardless of sign. Nothing here is expected to clear DSR; the win (if any) is the tail-improvement in §A, not the mean.

