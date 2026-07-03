# H5 — HK Peg-Liquidity Regime Conditioner — Phase-0 Report

**VERDICT: ACCRUE** (conditioner-grade). The peg-liquidity regime split has the
**right shape** — easy HK liquidity precedes higher, shallower-drawdown forward HSI
returns; tight liquidity precedes lower returns with materially deeper left tails —
and the sign is **stable across both horizons, both split-halves, and 5 of 6
robustness variants**. But the SOFR-era window (8.2 years) yields too few independent
liquidity episodes (**3–5 EASY / 8–14 TIGHT**) for the HAC-t to clear even the relaxed
conditioner bar (t_diff = **1.10 at 3m**, pre-registered bar 1.5). This is the
**pre-registered honest default** for H5, not a demotion: the masterplan's own trial
ledger (§6.1) tagged H5 "few regimes 2018→ · conditioner-grade only," and the
red-team confirmed SOFR does not exist before 2018-04. Re-run when the SOFR window
lengthens (come-back **2028-01**). **Nothing is wired.**

The regime label is a **usable exposure conditioner today** on the strength of its
drawdown separation (EASY-only strategy max-drawdown −21% vs TIGHT-only −49%, a 2.3×
gap; 3m 5th-percentile forward return −10.5% EASY vs −16.4% TIGHT), but it is **not**
a decision-grade scored seam and must never rank names. The engine-ready spec is in §8.

---

## 1. Pre-registered gates vs results (PRIMARY trial, SOFR 2018-04→2026-06)

Gates frozen in `research/HK_CANADA_H5_PREREG.md` §5, committed before any run
(commit `10b3fe7f1f`, timestamp precedes the analysis code commit).

| Gate (pre-registered) | Bar | Result | Pass? |
|---|---|---|---|
| **GO-1 direction** | EASY mean > TIGHT mean at BOTH 1m & 3m | +0.017 (1m), +0.034 (3m) — both positive | ✅ |
| **GO-2 drawdown separation** | TIGHT left-tail materially worse (≥1.5× at 3m OR ≤ EASY−5pp) | 3m p5: −16.4% (T) vs −10.5% (E) = −5.9pp gap; maxdd −49% (T) vs −21% (E) = 2.3× | ✅ |
| **GO-3 HAC-t on EASY−TIGHT diff @3m** | ≥ 1.5 (conditioner bar, not 2.0) | **1.10** | ❌ |
| **GO-4 split-half sign stability @3m** | same sign both halves | +0.045 (2018–2022) & +0.034 (2022–2026), both positive | ✅ |
| **GO-5 episodes per leg** | ≥ 4 | EASY 5, TIGHT 14 (debounced) | ✅ |

**Four of five gates pass; GO-3 (statistical power) fails.** Per the pre-registered
verdict table, *direction holds + drawdown separation holds + HAC-t < 1.5* ⇒
**ACCRUE**. This was the explicitly pre-stated expected outcome ("the *shape* is right
but the power is structurally too low to call it now").

### Per-horizon detail (PRIMARY)

| Horizon | mean EASY | mean TIGHT | diff | t_diff (HAC) | median E/T | p5 E/T | min E/T | n_E / n_T |
|---|---|---|---|---|---|---|---|---|
| 1m (21bd) | +1.46% | −0.27% | +1.73% | 1.33 | — | −6.6% / −11.4% | −14.4% / −25.0% | 435 / 603 |
| 3m (63bd) | +2.73% | −0.71% | +3.44% | 1.10 | +3.0% / −2.1% | −10.5% / −16.4% | −17.4% / −23.3% | 435 / 592 |

The EASY leg alone is marginally positive (HAC-t 1.69 @1m, 1.11 @3m); the TIGHT leg is
flat-to-negative (t −0.28 @1m, −0.36 @3m). The signal is a **left-tail / drawdown
conditioner**, not a mean-return alpha — exactly what a size-only conditioner should be.

*Window honesty:* the HIBOR−USD-spread percentile needs 60 SOFR observations, and SOFR
itself starts 2018-04-02, so the first ~59 business days of the nominal window are
unlabeled (the `agg_balance` percentile is available from pre-2018 history, but the
composite `E` needs both legs). The effective PRIMARY window is therefore ~**2018-07 →
2026-06**. This costs no bias — it is simply the earliest date a HIBOR−SOFR spread
percentile can honestly exist.

---

## 2. SECONDARY trial (spliced DFF→SOFR, 2002→) — capped at ACCRUE by construction

USD leg = effective fed funds (FRED **DFF**, `data/fred/DFF.parquet`) before 2018-04-02,
spliced to SOFR after. Window 2002-01→2026-06.

- **Splice is clean:** SOFR−DFF basis over the 2018→ overlap (2059 days) is mean
  **−0.21 bp**, std 8.3 bp, [p5 −6.0, p95 +7.1] bp — a fraction of a HIBOR percentile
  bin. **Zero episodes straddle the 2018-04 boundary** (the percentile windows reset
  cleanly). The labeled discontinuity is materially negligible here.
- **Direction holds, weaker:** diff +0.5% @1m (t 0.70), +1.05% @3m (t **0.59**);
  drawdown separation persists (EASY-only maxdd −34% vs TIGHT-only −59%).
- **DSR 0.14** (program n_trials=30). Verdict: **ACCRUE**, capped by pre-reg — a
  spliced-rate conditioner cannot be decision-grade. The 24-year splice adds episodes
  but dilutes the signal (the pre-2018 O/N rate regime is a different funding world).

**BH-FDR across the 2 decision trials (α=0.10):** neither rejects (primary q=0.545,
secondary q=0.558). Consistent with ACCRUE — this is not a multiple-testing survivor.

---

## 3. Split-half sign stability

SOFR window split at its median date **2022-06-28**. EASY−TIGHT 3m diff:
- First half (2018-04 → 2022-06): **+4.51%** (t 1.18)
- Second half (2022-06 → 2026-06): **+3.44%** (t 0.92)

**Sign agrees in both halves** — GO-4 satisfied. The magnitude is stable (within ~1pp),
which is stronger than a bare sign match. The signal is not a single-episode artifact
(e.g. it is not carried solely by the 2020 COVID liquidity flood).

---

## 4. Effective-N honesty (the binding constraint)

This is why the verdict is ACCRUE and not GO. **Daily rows dramatically overstate the
independent sample:**

- **Block-bootstrap effective-N** (`bootstrap_effective_t`) on the contiguous EASY-long
  / TIGHT-short daily overlay returns **t_eff = 2030 / 2030, ratio 1.0** — i.e. daily
  HSI returns carry negligible positive autocorrelation, so the bootstrap does *not*
  deflate the row count. This is a trap: it makes the daily t-stat look well-powered
  when it is not, because the **signal** is a persistent multi-month regime block, not
  a daily event. The independence that matters is at the *regime-episode* level.
- **Independent debounced episodes (the honest binding N):** EASY = **5** (3 of them
  ≥30 days), TIGHT = **14** (8 of them ≥30 days). Several short TIGHT "episodes" in
  2022–23 are fragments of one tightening cycle broken by the ≤5-bd hysteresis gap, so
  the *economically distinct* TIGHT count is closer to **~8**. Pre-registered
  expectation was 4–8 EASY and 4–8 TIGHT; EASY landed in range, TIGHT slightly above
  (fragmentation), both consistent with a low-power conditioner.
- **Bootstrap Sharpe CI** on the overlay: [−0.07, 0.67, 1.39], P(Sharpe>0) = 0.96 —
  the lower bound crosses zero. Directionally reliable, not decision-grade.

The 21 debounced episodes across ~19 economically-distinct liquidity swings over 8
years is the true multiple-testing-relevant N. At that N, a 3m HAC-t of 1.10 is a
respectable directional signal that **cannot** reach t≥2 (let alone DSR≥0.90) without
more time. **DSR (overlay, n_trials=30) = 0.30** — far below the 0.90 scored-seam gate,
exactly as pre-registered; H5 is reported *as* a conditioner precisely so this number
is visible and H5 is not smuggled in as an edge.

---

## 5. Robustness (reported, not decision trials)

| Variant | 1m diff (t) | 3m diff (t) | Sign |
|---|---|---|---|
| **base** (1m HIBOR, ±33) | +1.73% (1.33) | +3.44% (1.10) | + |
| R1 O/N HIBOR | +3.82% (3.46) | +7.77% (3.03) | + (much stronger) |
| R2 threshold ±25 | +2.09% (1.74) | +3.45% (1.17) | + |
| R2 threshold ±40 | +1.17% (0.89) | +3.81% (1.16) | + |
| R3 balance-only | +1.86% (1.60) | +6.81% (2.31) | + |
| R3 spread-only | −0.42% (−0.28) | −0.36% (−0.12) | **− (flips)** |

**Two findings.** (i) The composite is **sign-stable in 5 of 6 variants** — it does not
flip under thresholds, tenor, or the balance leg. (ii) **The signal lives in
`agg_balance`, not the HIBOR−USD spread.** R3_balance-only is the *strongest* clean
variant (t 2.31 @3m); R3_spread-only is a null that flips sign. The HIBOR−USD spread,
despite being the peg-arbitrage mechanism, adds noise, not power, over this window
(HK's post-2020 balance was so large that HIBOR often stayed anchored regardless).
R1's O/N-HIBOR strength (t 3.0) is *not* promoted — it was pre-registered as a
robustness variant, not the primary, and O/N HIBOR is spike-prone; swapping it in
post-hoc would be trial-shopping.

**Implication for the W4 spec:** weight the conditioner toward the balance-quantile
leg; keep the spread leg for interpretability but expect it to contribute little.

---

## 6. Exploratory (labeled, NON-EVIDENTIAL — informs H1 only, no gate)

**Does southbound net flow run stronger in EASY regimes?** Yes, directionally.
Over the 2018-06 → 2026-07 overlap (411 EASY days / 573 TIGHT days):

| | mean net (HKD mn) | median net | % positive days |
|---|---|---|---|
| EASY | 3,324 | 2,668 | 80.0% |
| TIGHT | 2,324 | 1,802 | 75.7% |

Southbound demand is ~43% higher (mean) in EASY regimes. This is **descriptive only**
— no significance test, no gate, cannot produce a GO. It flags one thing for H1
(masterplan §3): **H1's southbound holding-Δ leg should itself be conditioned on the
H5 regime**, since the flow it measures is regime-dependent. Non-evidential.

---

## 7. What this does NOT show (pre-committed)

- **No alpha, no ranking.** H5 never ranks names; it sizes index exposure. The
  EASY-mean is only marginally positive (t≈1.1); the usable content is left-tail
  separation, not directional return.
- **Not decision-grade.** DSR 0.30 (primary) / 0.14 (secondary) vs the 0.90
  scored-seam gate. By construction (few episodes) it cannot reach that bar now.
  A low DSR here is the *correct* label, not a failure.
- **The spliced 2002→ leg is not a clean long history.** Although the SOFR−DFF basis
  is tiny, the pre-2018 funding regime (unsecured O/N, different HK peg-band mechanics
  pre-2005) is a different world; the secondary is ACCRUE-capped and dilutive.
- **No causality.** The regime is *coincident*. Global risk-off can simultaneously
  tighten HK funding AND sell HK equities (common driver) — reverse/common causality
  is not ruled out. The conditioner is a correlational risk-sizing tell, nothing more.
- **Survivorship: N/A, stamped.** The target is the HSI *index level* (reconstituted
  by HSI Ltd), not a current-constituent name panel — no survivorship bound is needed
  or applicable. (Contrast H1/H3/H4, which do need bounds.) Stated as a decision, not
  an omission.
- **Suspension/halt:** the index does not halt for weeks; forward returns use actual
  traded closes only (no ffill across gaps), and rate/HKMA inputs are ffill-capped at
  ≤3 bd staleness (staler ⇒ date excluded).

---

## 8. Engine-ready regime spec (for a future W4 conditioner — NOT wired)

A W4 exposure conditioner would consume the frozen labels below. This is a **spec, not
an import.** No live engine or board reads it.

```python
H5_PEG_LIQUIDITY_CONDITIONER = {
    "grade": "conditioner",            # sizes exposure; NEVER ranks names
    "verdict": "ACCRUE",               # not decision-grade; re-run 2028-01
    "market": "HK", "target": "HSI",
    "usd_leg": {"primary": "ofr:FNYR-SOFR-A (2018-04->)",
                "secondary_splice": "fred:DFF (<2018-04) -> SOFR",  # ACCRUE-capped
                "basis_sofr_minus_dff_bp": {"mean": -0.21, "std": 8.33}},
    "inputs": {"agg_balance": "hkma/interbank_liquidity:agg_balance",
               "hibor_1m":   "hkma/interbank_liquidity:hibor_1m"},
    "pct_lookback_bd": 252,            # trailing own-history percentile (non-stationary-safe)
    "composite": "E = pct(agg_balance,252) - pct(hibor_1m - usd_leg,252)",  # high=easy
    "thresholds": {"EASY": "E >= +33", "TIGHT": "E <= -33", "NEUTRAL": "otherwise"},
    "debounce": {"open_bd": 10, "gap_bd": 5},   # hysteresis for episode independence
    "stale_cap_bd": 3,                 # rate/hkma ffill cap; staler => excluded
    "leg_weighting_note": "balance-quantile leg carries the signal (R3 t=2.31@3m); "
                          "spread leg is near-null (R3 flips) — weight toward balance.",
    "empirical_2018_2026": {
        "easy_day_frac": 0.19, "tight_day_frac": 0.27, "neutral_day_frac": 0.54,
        "episodes_easy": 5, "episodes_tight": 14,   # ~8 economically-distinct tight
        "fwd_3m_mean_easy": 0.0273, "fwd_3m_mean_tight": -0.0071,
        "fwd_3m_p5_easy": -0.1051,  "fwd_3m_p5_tight": -0.1642,
        "strat_maxdd_easy_pct": -21.0, "strat_maxdd_tight_pct": -49.2,
    },
    "usage": "SIZE only: e.g. de-risk HK exposure in TIGHT, permit full in EASY. "
             "Do NOT use to rank or select names. Do NOT treat as an edge.",
    "reproduce": "PYTHONPATH=. python3 scripts/h5_peg_liquidity_phase0.py",
}
```

---

## 9. Reproduction & provenance

- **Pre-reg:** `research/HK_CANADA_H5_PREREG.md` (commit `10b3fe7f1f`, before any run).
- **Code:** `scripts/h5_peg_liquidity_phase0.py`
  (`PYTHONPATH=. python3 scripts/h5_peg_liquidity_phase0.py`).
- **Primitives:** `engine/validation.py` (newey_west_tstat, benjamini_hochberg,
  deflated_sharpe with program n_trials=30, bootstrap_effective_t, block_bootstrap_ci).
- **Data ranges verified pre-reg:** HKMA 2002-01→2026-06; SOFR 2018-04→2026-06;
  DFF 1954→2026; HSI 1986→2026; southbound 2014-11→2026-07.
- **Registry:** experiment `h5-peg-liquidity` seeded in
  `data/experiments/registry_seed.json`, come-back **2028-01-15**.
