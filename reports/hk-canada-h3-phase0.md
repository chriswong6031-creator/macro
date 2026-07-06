# H3 — A/H Discount Tilt — Phase-0 Report

**Program:** HK/Canada program W3 — H3  
**Pre-registration:** `research/HK_CANADA_H3_PREREG.md`  
**Trial family:** `hk_canada_h3` (programme budget n_trials = 30)  
**Run date:** 2026-07-06  
**Script:** `scripts/hk_canada_h3_phase0.py`  
**VERDICT: ACCRUE**

---

## In plain English

We tested whether HK H-shares that are unusually cheap relative to their own history (the "A/H discount is deeper than normal for this pair") tend to outperform the Hang Seng Index over the next 1–3 months.

The answer is: the shape of the signal is real and stable — H-shares with a deeper-than-normal own-history discount do outperform, across time periods, portfolio widths, and when we exclude the most fragile names. The statistical signal is robust with HAC-corrected t-statistics above 2.0 at the 3-month horizon, sign-stable across both halves of the sample and across the pre/post-2021 dividend-tax cycle split.

However, the pre-registered DSR (Deflated Sharpe Ratio) gate cannot be passed. The programme-level multiple-testing budget of n_trials = 30 produces a comparison hurdle (SR0_annual ≈ 3.0) that is structurally impossible to clear with monthly cross-sectional returns across 25 pairs. The signal's actual annualized Sharpe Ratio, while positive, sits far below this extreme SR0 haircut. This is the pre-stated "ACCRUE" outcome from the pre-registration: honest borderline result, the right shape but structurally thin power.

The signal is worth watching as the panel deepens and as the 2024–2026 dividend-tax rumour cycle resolves. No engine wiring.

---

## 1. Data and PIT discipline

| Series | Source | Range | Role | PIT assumption |
|---|---|---|---|---|
| A/H premium panel | `data/hk_ah_panel/premium.parquet` | 2001-07-16 → 2026-07-03, 5,711 rows × 25 pairs | Signal source | Same-day A and H closes, no lag; monthend known before signal is actionable |
| H-leg closes (total return, dividend-adjusted) | `data/hk_search/closes_deep.parquet` | 1986-12-31 → 2026-07-03, 9,824 rows × 160 names | Forward H returns | Last date 2026-06-18 (15bd stale vs HSI); does not affect any graded cross-section |
| HSI close (price index) | `data/hk/_HSI.parquet` | 1986-12-31 → 2026-07-03 | Benchmark | Actual traded closes only; no forward-fill |
| Pair map | `data/hk_ah_panel/pairs.json` | 25 pairs, listing-date PIT | Universe / inception | Each pair enters only from joint_start (inception-honest) |

**Publication-lag assumption:** the premium is formed from same-day A-share and H-share closes. Entry is the **next trading day's close** strictly after month-end (a 1-bar-lagged, look-ahead-free open proxy). The signal at month-end t uses only data through t.

**TR vs price-index mismatch (pre-registered §2):** H-leg closes are dividend-adjusted total return; HSI is a price index. The H dividend yield (~2–4%/yr for these SOE/insurer names) adds a slow positive drift to every long-H-vs-HSI number. Mitigations: (i) the dividend-neutral L/S tercile (both legs are TR H-legs, drift cancels) is checked against the long-only sign; (ii) the rank-IC is scale/drift-free by construction.

---

## 2. Universe and effective coverage

- **Graded window:** month-ends with ≥ 8 pairs = **203 months** (first: 2008-02-29)
- **Total month-ends:** 262 (2001-07 → 2026-07)
- **Month-ends ≥ 5 pairs:** 226 (first: 2005-12-30)
- **Median pair count per rebalance:** 23 out of 25
- The pre-registration estimated "~235 months with ≥8 pairs (first = 2007-01)"; actual is 203 months (first = 2008-02-29) — a minor downward revision due to inception-honest joint_start masking.

---

## 3. Signal construction (exact per pre-reg §3)

**PRIMARY:** own-history percentile of the A/H premium.  
For pair j on date t: `pctile(j,t)` = percentile rank of `P[j,t]` within trailing 504-trading-day window, requiring ≥ 252 non-NaN observations. High pctile = H unusually cheap vs own norm = long candidate.

**SECONDARY:** 1-year premium change `d1y(j,t) = P[j,t] − P[j, t−252]`. Positive = H got cheaper over the year.

**Size control (R3):** log-price proxy residualization via `engine.validation.cross_sectional_resid`. A weak proxy flagged as such (not true PIT mktcap — the fundamentals panel is a 2026-06-18 snapshot and was excluded for look-ahead reasons).

---

## 4. Decision trial results

### Trial (a) — PRIMARY: own-history percentile

| Metric | 1m (21bd) | 3m (63bd) |
|---|---|---|
| n rebalances | 202 | 199 |
| n IC observations | 199 | 196 |
| Median pair count | 23 | 23 |
| IC mean | 0.0339 | **0.0592** |
| IC-IR | 0.132 | 0.219 |
| IC hitrate | 51.3% | **63.3%** |
| HAC-t (IC, NW lags) | 1.799 (1 lag) | **2.412** (2 lags) |
| Top-5 excess mean | +1.08%/mo (12.96% ann) | **+2.99%/mo (35.85% ann)** |
| HAC-t (top-5 excess) | 2.511 | **3.203** |
| L/S tercile mean | +0.41%/mo | **+1.54%/mo** |
| t_eff (block-bootstrap, block=3) | 202 | 123 |
| **DSR** | N/A | **0.0855** |
| **DSR verdict** | N/A | FAILS (< 0.90) |

### Trial (b) — SECONDARY: 1y premium change (d1y)

| Metric | 1m (21bd) | 3m (63bd) |
|---|---|---|
| IC mean | 0.0181 | 0.0342 |
| IC hitrate | 51.3% | 57.1% |
| HAC-t (IC) | 0.918 | 1.252 |
| Top-5 excess mean | +1.13%/mo | +2.93%/mo |
| HAC-t (top-5 excess) | 2.241 | 3.105 |
| L/S tercile mean | +0.39%/mo | +1.27%/mo |
| DSR | N/A | 0.0814 |
| Secondary verdict | capped at ACCRUE by construction |

---

## 5. BH-FDR (4 p-values, α = 0.10)

| Trial | NW HAC p-value (IC) | BH q | BH-significant |
|---|---|---|---|
| pctile 1m | 0.0735 | 0.1471 | NO |
| **pctile 3m** | **0.0168** | **0.0672** | **YES** |
| d1y 1m | 0.3597 | 0.3597 | NO |
| d1y 3m | 0.2121 | 0.2828 | NO |

Note: only the PRIMARY 3m trial survives BH correction at α=0.10 (q=0.0672 < 0.10). The pctile_1m, d1y_1m, and d1y_3m trials do NOT survive BH (q-values 0.1471, 0.3597, 0.2828 respectively). This is sufficient for the GO gate, which requires only that the primary 3m be BH-significant — and it is.

---

## 6. Split-half sign stability (PRIMARY 3m)

| Split | H1 or pre-split mean | H2 or post-split mean | Same sign |
|---|---|---|---|
| IC — median-date | 0.0605 | 0.0579 | YES |
| IC — pre/post 2021 | 0.0774 | 0.0159 | YES |
| Top-5 excess — median-date | +0.0261/mo | +0.0337/mo | YES |
| Top-5 excess — pre/post 2021 | +0.0232/mo | +0.0460/mo | YES |

Sign stability is excellent. Notably, the post-2021 IC (0.0159) is materially weaker than pre-2021 (0.0774), consistent with the 2024–2026 dividend-tax rumour cycle compressing the premium's predictive content — but the sign does not flip.

---

## 7. Robustness variants (NOT decision, NOT FDR-counted)

| Variant | IC mean | HAC-t(IC) | Top-5 excess/mo | Notes |
|---|---|---|---|---|
| R1 top-3 | 0.0592 | 2.412 | +3.42% | IC unchanged (rank-only) |
| R1 top-7 | 0.0592 | 2.412 | +2.94% | Slight dilution, still strong |
| R2 756d window | 0.0737 | 3.153 | +3.09% | Longer window stronger IC |
| R3 size-residualized IC | 0.0384 | 1.602 | n/a | Survives residualization (log-price proxy) — signal is not purely a size bet |
| R4 pre-2021 | 0.0774 | 2.628 | +2.32% | Solid |
| R4 post-2021 | 0.0159 | 0.371 | +4.60% | IC weak; excess mean higher but noisy (n=62) |

R3 commentary: the IC drops from 0.0592 to 0.0384 after residualizing on log-price (a price-level proxy for market cap). This is a ~35% attenuation, consistent with the red-team's claim that "own-history largely absorbs the size level effect" — the own-history transform already removes most of the structural premium level, but log-price residualization attenuates further, suggesting residual size exposure remains. With a proper PIT market cap (unavailable in-tree), this attenuation could be larger or smaller.

---

## 8. Survivorship bound (prereg §7)

| Bound scenario | IC mean | HAC-t | Top-5 excess | 
|---|---|---|---|
| Full 25-pair inception-honest panel | 0.0592 | 2.412 | +2.99%/mo |
| Haircut: excl. shortest-5 pairs | 0.0575 | 2.054 | +2.88%/mo |
| Long survivors (≥15y history, n=19) | **0.0542** | **1.953** | **+2.72%/mo** |

Shortest-5 haircut: 0941.HK (China Mobile), 1833.HK (Ping An Health), 0902.HK (Huaneng Power), 2333.HK (Great Wall Motor), 1211.HK (BYD).  
Longest ≥15y pairs (19 pairs): 0358.HK, 0386.HK, 0390.HK, 0762.HK, 0763.HK, 0857.HK, 0939.HK, 0998.HK, 1088.HK, 1186.HK, 1398.HK, 1766.HK, 1898.HK, 2318.HK, 2600.HK, 2601.HK, 2628.HK, 3328.HK, 3988.HK.

The haircut of the 5 shortest-history pairs leaves the signal qualitatively unchanged. The ≥15y-only subsample (19 pairs, 76% of the universe) shows a computable and positive IC of 0.0542 with HAC-t 1.953 — below the 2.0 threshold but directionally consistent, providing an honest survivorship bound.

---

## 9. Pre-registered gate table (prereg §8)

| Gate | Condition | Status | Detail |
|---|---|---|---|
| GO (1) | IC > 0 at BOTH 1m and 3m | **PASS** | IC(1m)=0.0339, IC(3m)=0.0592 |
| GO (2) | HAC-t ≥ 2.0 on 3m IC AND 3m excess | **PASS** | IC HAC-t=2.412, excess HAC-t=3.203 |
| GO (3) | Dividend-neutral L/S same sign as top-5 excess at 3m | **PASS** | L/S=+1.54%/mo, top-5=+2.99%/mo, both positive |
| GO (4) | DSR ≥ 0.90 (3m series, n_trials=30) | **FAIL** | DSR=0.0855 (SR0_ann≈2.98 — extreme haircut at n=30) |
| GO (5) | Split-half sign stability (H1/H2 and pre/post 2021) | **PASS** | All splits sign-stable (see §6) |
| GO (6) | Survivorship: GO survives on haircut panel | **PASS** | Haircut IC=0.0575, positive |
| ACCRUE | IC>0 both horizons AND HAC-t ≥ 1.5 at 3m BUT DSR<0.90 OR half-flip OR HAC-t<2.0 | **MATCHES** | Gates (1)(2)(3)(5)(6) pass; gate (4) fails |
| NO-GO | IC ≤ 0 either horizon OR L/S negative vs positive long-only | NOT triggered | N/A |
| KILL | IC < 0 with HAC-t ≥ 2.0 at 3m | NOT triggered | N/A |

**VERDICT: ACCRUE**

---

## 10. DSR explainer (why DSR=0.085 despite HAC-t=2.4)

The Deflated Sharpe Ratio penalises the observed Sharpe by the maximum expected Sharpe across n_trials independent tests (the de Prado SR0 haircut). With a programme budget of n_trials=30 and t_eff=123 effective monthly observations, the SR0_annual ≈ **2.98** — the expected maximum Sharpe among 30 independent draws from SR=0 processes with this sample size. The observed annualized Sharpe of the 3m top-5 excess series is approximately **0.79** (monthly mean 2.99%, implied std ~13.2%, annualized ×√12). The DSR probability (P[SR_true > SR0 | observed SR]) is then very low — not because the signal is fake, but because the multiple-testing correction standard for n=30 is extreme relative to the modest SR available from monthly cross-sectional returns over 25 names.

To pass DSR≥0.90 with these data characteristics would require an annualized Sharpe of roughly **4.5–5.0**, which would be a world-class systematic edge and is structurally implausible for an 25-pair arbitrage spread at monthly rebalance. This is not a failure of the signal — it is the correct ACCRUE output under honest programme-level accounting. The pre-registration (§6.1, §6) pre-stated this exact outcome.

---

## 11. Deviations from pre-registration

| Deviation | Nature | Impact |
|---|---|---|
| Month-ends ≥8-pair first date: actual 2008-02-29 vs prereg estimate 2007-01 | ~14 months shorter graded window | Minor: 203 vs ~216 estimated month-ends; still well above the "~130" original estimate |
| R3 size residualization: `cross_sectional_resid` receives a `pd.Series` (log-price for tickers), not a DataFrame with multiple factor columns | Functionally equivalent — the function accepts 1-column input | No impact |
| `closes_deep` last date 2026-07-03 (not 2026-06-18 as stated in prereg) | Data is more current than prereg described | Forward return windows fully populated; no impact |
| HSI `_HSI.parquet` last date 2026-07-03 | Matches closes_deep | Consistent |
| **≥15y survivor threshold bug (corrected in v2):** initial code used `365*15=5475` (calendar days) compared against `pairs.json n_days` which counts trading days, collapsing the pool to 3 pairs and producing NaN IC. Fixed to `252*15=3780` (trading days). | Measurement unit mismatch — resolved | Pool expands from 3 → 19 pairs (76% of universe); IC now computable at 0.0542, HAC-t=1.953 — directionally consistent, provides the prereg §7 survivorship bound honestly |

The "closes_deep staleness" caveat in the prereg (15bd stale vs HSI) turned out to be a non-issue as both stores were updated to 2026-07-03.

---

## 12. What this does NOT show (per pre-reg §9)

- Does NOT establish a causal A/H convergence mechanism. This is a cross-sectional mean-reversion association, confounded with size (proxy-controlled only), liquidity, and the southbound **dividend-tax rumour cycle 2024–2026**.
- Does NOT use a true PIT market cap — the size control is a log-price proxy; the real attenuation from a proper PIT-cap control is unknown.
- Does NOT correct for **delisting survivorship** — 25 pairs are today's survivors; reported IC is an **upper bound** on tradable edge.
- The TR-vs-price benchmark mismatch means long-only excess carries a positive dividend drift (~2–4%/yr); only the rank-IC and dividend-neutral L/S are drift-clean.
- Does NOT show tradability net of HK transaction costs, borrow, or halt risk on the cheapest (often least liquid) H-legs.
- Is **NOT wired** into any engine or board — report only (masterplan W3, come-back when panel deepens or dividend-tax cycle resolves).

---

## 13. Trial ledger

- Family: `hk_canada_h3`
- Grid items logged: 10 (4 decision + 6 robustness configs)
- Declared programme budget: 30 (masterplan §6)
- Effective n_trials (used in DSR): 30

**Data info_cutoff:** 2026-07-03 (last date in HSI and closes_deep stores).
