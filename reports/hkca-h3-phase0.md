# H3 — A/H Discount Tilt — Phase-0 Report

**VERDICT: ACCRUE.** The own-history A/H-discount tilt has a real, sign-stable
cross-sectional edge on the deepest HK panel we have (rank-IC 0.055 at 3m, HAC-t 2.23;
top-5 H-leg excess +2.8%/3m, HAC-t 3.08; positive in both split-halves and both
pre/post-2021 eras; robust across portfolio width and lookback window) — **but it falls
just short of the decision-grade door: DSR = 0.879 < 0.90** at program n_trials=30. The
shape is right and the power is structurally close but not yet sufficient. Do not torture
0.879 into a GO. Re-run when the panel deepens / the 2024–26 dividend-tax-cycle confound
resolves. Nothing is wired.

Pre-registered: `research/HK_CANADA_H3_PREREG.md` (committed BEFORE any run — see git).
Code: `research/hk_h3_ah_discount.py`. Raw: `research/hk_h3_results.json`.

---

## 1. Gates vs results (PRIMARY = own-history percentile, binding horizon 3m)

| Gate (from prereg §8) | Requirement | Result | Pass? |
|---|---|---|---|
| (1) rank-IC > 0 both horizons, same sign | IC>0 @1m & @3m | 1m 0.034, 3m 0.055 (both +) | ✅ |
| (2) HAC-t ≥ 2.0 on 3m IC AND 3m excess | both ≥ 2.0 | IC-t 2.23, excess-t 3.08 | ✅ |
| (3) dividend-neutral L/S shares sign @3m | L/S sign = long sign | L/S +1.38%, t 1.59 (same +) | ✅ |
| **(4) DSR ≥ 0.90** on 3m excess, n_trials=30 | **≥ 0.90** | **0.879** | ❌ **(binding fail)** |
| (5) split-half + era sign stability @3m | both halves & pre/post-2021 same sign | halves +0.025/+0.030; eras +0.022/+0.041 | ✅ |
| (6) survivorship: GO on ≥8-pair inception-honest panel | edge survives | see §4 | ✅ |

**Only gate (4) fails.** Per prereg §8, "rank-IC > 0 at both horizons AND HAC-t ≥ 1.5 at
3m BUT DSR < 0.90" → **ACCRUE** — and this was the pre-registered honest-default
expectation (§1, §6, §10 of the prereg all called GO/ACCRUE-lean).

### Full numbers

| Trial | Horizon | mean IC | IC HAC-t | IC hit | top-5 excess | excess HAC-t | L/S t | DSR | n | t_eff |
|---|---|---|---|---|---|---|---|---|---|---|
| **primary pctile** | 1m | 0.034 | 1.82 | — | +1.03% | 2.52 | 1.04 | 0.680 | 219 | 219 |
| **primary pctile** | **3m** | **0.055** | **2.23** | 0.62 | **+2.77%** | **3.08** | 1.59 | **0.879** | 217 | 125 |
| secondary d1y (ACCRUE-capped) | 1m | 0.023 | 1.31 | — | +1.19% | 2.55 | 1.17 | 0.750 | 219 | 219 |
| secondary d1y (ACCRUE-capped) | 3m | 0.037 | 1.39 | — | +2.95% | 3.27 | 1.42 | 0.914 | 217 | 122 |

BH-FDR (α=0.10, family = 4 p-values on the top-5 excess): **all four reject** (q < 0.10);
the primary-3m p = 0.0021 survives comfortably. Monthly Sharpe of the primary 3m top-5
excess = 0.27 (√12-annualized ≈ 0.93). Skew +0.82, kurtosis 4.8 (fat right tail — the
edge is partly a few large convergence episodes, which is why DSR's non-normal haircut
bites).

### Size control (prereg §3 — PIT log-price proxy, reported not a decision trial)
Residualizing the primary signal against a PIT log-price size proxy each rebalance:
**resid IC = 0.035 (t 1.45)** vs raw 0.055. The tilt keeps ~65% of its magnitude after
removing the log-price factor → it is **not merely a size/level bet**, consistent with the
own-history-percentile transform doing its intended job (differencing out the constant
per-pair size level). Caveat (prereg §9): this is a *log-price* proxy, NOT a true PIT
market cap (none exists in-tree; fundamentals are a static 2026-06-18 snapshot → excluded
as look-ahead). A tilt that survives own-history ranking but not a *real* PIT-cap control
cannot be ruled out.

---

## 2. Why DSR misses (the honest diagnosis)

DSR = 0.879 at n_trials=30, T=217 monthly rebalances, **t_eff = 125** (block-bootstrap,
block=3 months). The 3m forward windows overlap → the autocorrelation-honest effective
count is ~125, not 217. Against a program-level 30-trial haircut (SR0 ≈ the best-of-30
null bar), a monthly Sharpe of 0.27 clears p=0.002 on a plain t but lands at 0.879 on the
deflated, non-normal, t_eff-corrected DSR. The +0.82 skew / 4.8 kurtosis inflate the
`var_scaler` haircut. **This is not a marginal-torture situation — it is a genuine
"almost."** The signal is real; the power is ~0.02 of DSR short.

---

## 3. Split-half, era, effective-N

- **Median-date split-half (3m):** first half +2.52%/3m, second half +3.01%/3m — same
  sign, similar magnitude. No flip.
- **Era split (dividend-tax-cycle probe, prereg §4 R4):** pre-2021 (n=155) +2.24%/3m;
  2021→ (n=62, the southbound dividend-tax-rumor era) +4.09%/3m — same sign, LARGER
  post-2021. So the edge is **not** a pre-2021 artifact; if anything the recent era is
  stronger — but the recent era is precisely where the dividend-tax-rumor confound lives,
  so the larger post-2021 number should be read with that named confound in mind, not as
  clean out-of-sample confirmation.
- **Robustness (prereg R1/R2, reported):** top-3 / top-5 / top-7 excess = +3.10 / +2.77 /
  +2.79%/3m (HAC-t 2.93 / 3.08 / 3.34); 756-day (3y) own-window IC 0.068, excess t 3.34.
  Sign stable everywhere, no flips → the ACCRUE is robust, not fragile.
- **Effective-N:** binding = **t_eff 125** independent-ish 3m units (block-bootstrap),
  cross-checked against ~217/3 ≈ 72 non-overlapping 3m blocks. The 25-pair cross-section
  is one correlated HK basket, so cross-sectional breadth adds signal, not independent
  time. Pre-stated expectation was 60–90 episodes → landed as expected.

---

## 4. Survivorship bound (prereg §7)

The 25 pairs are **today's** dual-listings → survivorship-biased UP. Bounds:
- **Exclude 5 shortest-history pairs** (0941/1833/0902/2333/1211.HK, likeliest recent /
  fragile survivors): primary 3m IC = 0.057, top-5 excess +3.12% — edge *stronger*, not
  weaker.
- **Deep-core ≥15y pairs** (23 names): IC = 0.059, top-5 excess +3.37%.

Both haircuts *increase* the edge — consistent with survivorship inflating the reported
number: the deepest survivors are exactly the pairs whose discount did converge. **These
bounds cover inclusion + fragility, NOT true delisting survivorship** (no PIT dual-listing
registry in-tree). The reported IC is therefore an **upper bound** on the tradable edge —
stated in the prereg and reaffirmed here.

---

## 5. What this does NOT show (pre-committed, prereg §9)

- **No causal** A/H-convergence mechanism — a cross-sectional mean-reversion association,
  confounded with size (log-price proxy only, no true PIT cap), liquidity, and the named
  **2024–2026 southbound dividend-tax rumor cycle** (which the post-2021 strength sits
  inside).
- **No true PIT market cap** — the size control is a log-price proxy; a real-cap control
  could weaken it.
- **No delisting-survivorship correction** — reported IC is an upper bound (§4).
- **TR-vs-price benchmark mismatch** — H legs are dividend-adjusted total return, HSI is a
  price index, so long-only excess carries a positive dividend drift. Mitigation held: the
  dividend-neutral L/S (both legs TR) shares the sign (+1.38%, t 1.59) and the rank-IC is
  drift-free — so the edge is not *only* the dividend gap. But the L/S t (1.59) is the
  weakest of the corroborating legs and is another reason this is ACCRUE not GO.
- **No tradability net of costs / borrow / halt-prone illiquidity** of the cheapest-H
  names.
- **NOT wired** into any engine or board.

---

## 6. Come-back / accrual

Re-run when (a) the panel deepens materially (more pairs / more post-confound history
lifts t_eff), or (b) the 2024–26 dividend-tax-cycle resolves so the post-2021 leg is
clean out-of-sample. Registry entry appended to `data/experiments/registry_seed.json`
(id `hkca-h3-ah-discount-tilt`, come-back 2027-01-15). A GO on re-run requires the 3m DSR
to cross 0.90 with sign stability intact.

**Secondary trial (1y-Δ):** DSR 0.914 at 3m *does* clear 0.90, but its verdict is capped
at ACCRUE by construction (prereg §4) — it is the more confound-exposed momentum-of-discount
signal and its IC-t (1.39) is below the primary's, so it is corroboration, not a promotion.
