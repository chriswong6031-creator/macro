# H2a — SFC Reportable Short Positions — Phase-0 Report

**VERDICT: LEVEL = ACCRUE · Δ4w = NO-GO. Both correct-signed, neither decision-grade.**
The reportable-short-pressure signal points the **right way** — names with a high
own-history short book (days-to-cover percentile) and names whose short book is *rising*
both **underperform** the HSI over the next 4 weeks, exactly as the short-constraint
literature (Chang-Cheng-Yu) predicts — and the negative sign is **stable across both
split-halves** for both trials. But on the PRIMARY days-to-cover normalization the edge
is **too weak to clear the pre-registered bars**: the LEVEL Q5−Q1 spread is −0.39%/4w at
**HAC-t = −1.81** (bar |t| ≥ 2.0), **DSR = 0.32** (bar 0.90), and it **fails BH-FDR**
(q = 0.14 > 0.10). LEVEL lands in the pre-registered **ACCRUE** band (right sign + right
shape + power just short); Δ4w is weaker still (HAC-t = −0.98, DSR = 0.11) → **NO-GO**.
Re-run when the H4 expanded-HSCI universe lands (broadens the cross-section beyond the
157 large-caps the ≥0.02% threshold observes). **Nothing is wired.**

**This is a well-powered NO-GO/ACCRUE, not an underpowered one.** 666 weekly
cross-sections, 13.6 years, effective-N t_eff = 189 (LEVEL). The signal simply does not
carry a decision-grade cross-sectional edge *on the large/liquid universe the SFC ≥0.02%
threshold can see*. A respectable, pre-registered outcome.

---

## 1. Pre-registered gates vs results

Gates frozen in `research/HK_CANADA_H2a_PREREG.md` §5, committed **before any run**
(commit `bc0796822d`; the data store `1b8d04209f` and this analysis both post-date it —
the prereg timestamp is the audit trail). PRIMARY normalization = **days-to-cover**
(`shorted_shares / trailing-63d ADV-shares`), own-history percentile over 104 weeks.
Forward window starts **T+7 calendar days** after each SFC position date (real
publication lag). Expected sign **NEGATIVE** per trial.

### TRIAL 1 — LEVEL (own-history percentile of days-to-cover)

| Gate (pre-registered) | Bar | Result | Pass? |
|---|---|---|---|
| **G1 sign correct** | mean IC < 0 AND Q5−Q1 < 0 | IC = −0.0074, Q5−Q1 = **−0.39%**/4w | ✅ |
| **G2 HAC-t on Q5−Q1** | \|t\| ≥ 2.0 (lags = 3) | **−1.81** | ❌ |
| **G3 BH-FDR** | q ≤ 0.10 (2-trial family) | p = 0.071 → **q = 0.142** | ❌ |
| **G4 DSR** | ≥ 0.90 (n_trials = 30, t_eff = 189) | **0.317** | ❌ |
| **G5 split-half sign** | both halves negative | −0.0002 (H1) & −0.0077 (H2), both neg | ✅ |
| **G6 effective-N** | t_eff ≥ 60 | **189** | ✅ |
| **G7 survivorship bound** | worst-case-imputed sign stays negative | −0.39% (held; see §4) | ✅ |

Sign correct + shape right (G1, G5, G6, G7 pass) but power short (G2/G3/G4 fail) ⇒ per
the pre-registered verdict table (**"Sign correct AND HAC-t ≥ 1.5 but < 2.0 … → ACCRUE"**)
this is **ACCRUE**. HAC-t = −1.81 sits in the [1.5, 2.0) ACCRUE band.

### TRIAL 2 — Δ4w (4-week change in short-pressure percentile)

| Gate | Bar | Result | Pass? |
|---|---|---|---|
| **G1 sign correct** | IC < 0 AND Q5−Q1 < 0 | IC = −0.0090, Q5−Q1 = **−0.20%** | ✅ |
| **G2 HAC-t** | \|t\| ≥ 2.0 | **−0.98** | ❌ |
| **G3 BH-FDR** | q ≤ 0.10 | p = 0.330 → q = 0.330 | ❌ |
| **G4 DSR** | ≥ 0.90 | **0.105** | ❌ |
| **G5 split-half** | both negative | −0.0034 & −0.0007, both neg | ✅ |
| **G6 effective-N** | t_eff ≥ 60 | **210** | ✅ |

Sign correct but HAC-t = −0.98 < 1.5 ⇒ per the verdict table (**"Sign is FLAT / correct-sign
fails FDR and power below ACCRUE band → NO-GO"**) this is **NO-GO**. The change-of-percentile
signal is noisier than the level, exactly as the honest prior pre-stated ("Δ4w is the more
fragile of the two, ACCRUE-lean" — realized weaker than that, NO-GO).

**No wrong-sign / KILL outcome:** neither trial produced a significant *positive* sign, so
the direction discipline's WRONG-SIGN NO-GO / KILL branches did not fire. The literature
thesis is directionally *confirmed but sub-threshold*, not refuted-with-reverse-sign.

---

## 2. Per-trial detail

| Trial | n_wk | mean IC | IC HAC-t | mean Q5−Q1 (4w) | Q5−Q1 HAC-t | book Sharpe (wk) | t_eff | DSR |
|---|---|---|---|---|---|---|---|---|
| **LEVEL** | 666 | −0.0074 | −0.91 | **−0.394%** | **−1.81** | 0.115 | 189 | 0.317 |
| **Δ4w** | 662 | −0.0090 | −1.19 | −0.202% | −0.98 | 0.058 | 210 | 0.105 |

Q5 = highest short pressure; Q5−Q1 negative = high-short names underperform low-short
names — the pre-registered direction. The tradable book (long Q1 / low-short, short Q5 /
high-short) has a positive but small weekly Sharpe (0.115 LEVEL); annualized that is ~0.83
gross, but the DSR haircut against 30 program trials and the autocorrelation-honest
t_eff = 189 collapses it to 0.32 — well under the 0.90 door.

---

## 3. Robustness & diagnostics (pre-registered, non-decision)

- **Normalization fragility (SECONDARY `svl` = short-value / dollar-ADV).** LEVEL on the
  dollar-liquidity normalization gives Q5−Q1 = **−0.52%** at **HAC-t = −2.413** — which
  *crosses* the 2.0 bar. **The edge is real and normalization-sensitive:** the same short
  book, normalized by dollar-liquidity instead of share-liquidity, is significant; by
  share-liquidity (PRIMARY) it just misses. Per the prereg, a secondary/robustness variant
  **cannot upgrade** the PRIMARY verdict (that would be post-hoc normalization-shopping) —
  but it is decision-relevant evidence that this signal is genuinely on the edge of GO, and
  it is why LEVEL is ACCRUE (re-run worth doing) rather than NO-GO. Reported, not banked.
- **Lag-cost (T+0 vs T+7).** LEVEL Q5−Q1 is −0.50% at T+0 vs −0.39% at T+7 — the SFC
  7-day publication lag eats ~22% of the raw spread. Edge decays but survives the lag
  directionally; the lag is not the reason for the sub-threshold power (even T+0 would not
  clear |t| ≥ 2.0 on days-to-cover). The lag-honesty was worth enforcing: a naive T+0 test
  would have reported a 26% larger spread.

---

## 4. Survivorship bound (stamped)

The worst-case delisted-name imputation (§3 of prereg: any covered name exiting the SFC
file ≥ 8 weeks after a top-quintile short-pressure reading gets −40% imputed forward
excess) **changed the LEVEL Q5−Q1 by 0.00 pp** (−0.394% → −0.394%). **Reason, stated
honestly:** only **4** of our 157 covered names ever exit the SFC file (2392/3333/2150/0884.HK),
and all four are still current constituents in the price panel — they exited the SFC file
by **falling below the ≥0.02% reporting threshold (short covering)**, not by delisting, so
they retain real forward returns and the imputation (which only fires on names with *no*
forward return) had nothing to bite on. **The survivorship exposure for H2a is
structurally minimal:** the ≥0.02%-of-issued threshold universe is large-cap and stable,
and delisting-into-short is not a material path here. The bound is reported as trivially
satisfied — which is itself the finding, not a failure of the bound to be computed.

**Size skew (pre-registered quantification):** covered-panel median trailing-21d ADV =
**HKD 263M**, terciles at **HKD 139M / 504M** — a liquid, large-cap tilt. Any H2a result
is a claim about the **large/liquid end** of HK only. The small-cap short-crowding
mechanism (where the anomaly is typically strongest) is **unobservable** here because
those names rarely cross the ≥0.02% SFC threshold — this is the single biggest reason the
edge is sub-threshold, and it is exactly what the H4 expanded-HSCI universe (masterplan
§3) is being built to reach. **Re-run trigger: H4 universe collector lands.**

---

## 5. Coverage stamp

- **157 / 157** core `hk_stocks` names covered by the SFC file (union over all 721 weeks).
  The `coverage.json` figure of 153 is a stricter latest-date intersection; the
  backtest-relevant union is 157. **Coverage gate (≥ 60 for decision-grade) PASSES** by a
  wide margin — H2a ran as a ranker, not a context chip.
- 84,339 raw name-week signal rows; 666 usable weekly cross-sections (721 dates − ~55
  percentile warm-up weeks); median 484 SFC weeks per covered name.
- Suspension rule enforced: forward returns on real traded closes only, no ffill through
  halts, ≥ 15 of 21 forward bars required; weeks with < 20 valid names dropped.

---

## 6. Frozen signal spec (deliverable — NO WIRING)

Recorded so a future W4 ranker *could* consume it **iff** a re-run clears the door. This
is a spec, not an import. Current status: **ACCRUE (LEVEL) / NO-GO (Δ4w)** — not wired.

```json
{
  "battery": "H2a",
  "status": {"LEVEL": "ACCRUE", "DELTA4W": "NO-GO"},
  "normalization_primary": "days_to_cover = shorted_shares / mean(volume, 63td, asof<=t)",
  "signal_LEVEL": "own_history_percentile(days_to_cover, window=104w, min_prior=52)",
  "signal_DELTA4W": "pctile_t - pctile_{t-4w}",
  "expected_sign": "NEGATIVE (high/rising short pressure -> lower fwd excess; short leg = long Q1 / short Q5)",
  "publication_lag_days": 7,
  "forward_window_td": 21,
  "benchmark": "_HSI price return (name total-return minus HSI, LS-cancelling dividend bias)",
  "suspension_rule": "real closes only; >=15/21 fwd bars; drop halts; week min 20 names",
  "realized_LEVEL": {"n_wk": 666, "Q5mQ1_4w": -0.00394, "hac_t": -1.81, "dsr": 0.317, "t_eff": 189, "bh_q": 0.142},
  "realized_DELTA4W": {"n_wk": 662, "Q5mQ1_4w": -0.00202, "hac_t": -0.98, "dsr": 0.105, "t_eff": 210},
  "secondary_svl_LEVEL_hac_t": -2.413,
  "size_skew": {"median_ADV_hkd": 263000000, "note": "large/liquid-only; small-cap mechanism unobservable at >=0.02% threshold"},
  "rerun_trigger": "H4 expanded-HSCI universe collector lands (broadens cross-section)",
  "wired": false
}
```

---

## 7. What this does NOT show (pre-committed)

- Does **NOT** show a decision-grade (DSR ≥ 0.90) edge — LEVEL DSR = 0.32, Δ4w = 0.11.
- Does **NOT** show a small-cap short-crowding edge — the SFC ≥0.02% threshold observes
  shorts almost entirely on large/liquid names (median ADV HKD 263M); the mechanism's
  strongest regime is unobservable here. Any result is large/liquid-cap-only.
- The SECONDARY `svl` HAC-t = −2.41 does **NOT** upgrade the verdict — it is a non-decision
  robustness variant; treating it as the primary would be post-hoc normalization-shopping.
- Does **NOT** establish causality — short interest is a coincident constraint/sentiment
  proxy; reverse causality (falling prices attract shorts) and common-driver confounds are
  not ruled out.
- Does **NOT** survivorship-clean the panel — it bounds it (trivially, given only 4 covered
  names ever leave the SFC file, none by delisting).
- Does **NOT** conflate with H2b (sstoday short-sell turnover) — a different quantity, not
  in this battery.

---

## 8. Reproduce

```
PYTHONPATH=<repo-root> python3 research/h2a_phase0.py
# writes research/h2a_phase0_results.json
```
Inputs: `data/hk_shorts/positions.parquet` (committed `1b8d04209f`),
`data/hk_stocks/*.parquet`, `data/hk/_HSI.parquet`. Primitives:
`engine.validation.{rank_ic, newey_west_tstat, benjamini_hochberg, ret_moments,
bootstrap_effective_t, deflated_sharpe, dsr_verdict}`.
