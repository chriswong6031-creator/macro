# C-BANK Phase-0 — Bank-Earnings-Season Clustering + PEAD

## **VERDICT: NO-GO on both legs. The Canadian-bank season leg REFUTES its directional prior (Financials sleeve slightly UNDER-performs the TSX inside the ±2w bank-earnings windows, not over); the PEAD leg is degenerate (18 beats vs 2 misses on 20 events — no testable contrast). Nothing is wired. This is a clean, pre-registered null — a respectable W2 outcome.**

Pre-registered in `research/CBANK_PREREG.md` (committed 2026-07-03 as a separate commit BEFORE any
test ran — the commit timestamp is the audit trail). Script: `scripts/cbank_phase0.py`. Reports-only
per masterplan W2 acceptance; NO engine/board wiring.

---

## 1. Pre-registered gates vs results

| # | Trial | Effective-N | HAC t (gate ≥2.5) | BH-FDR reject (α.10) | DSR (gate ≥0.90) | Split-half sign | **Verdict** |
|---|-------|-------------|-------------------|----------------------|------------------|-----------------|-------------|
| 1 | Season **XFN.TO** (2001→) | 101 in / 102 out episodes | **−2.05** (wrong sign) | reject (q=.08) but sign is contrary | **0.013** | agree (both −) | **NO-GO** |
| 2 | Season **ZEB.TO** (2010→) | 65 in / 66 out episodes | 0.04 (null) | no (q=.97) | 0.17 | **FLIPS** (+ then −) | **NO-GO** |
| 3 | PEAD beat−miss **1w** | 18 beat / 2 miss | — (uncomputable) | — | — | — | **NO-GO (degenerate)** |
| 4 | PEAD beat−miss **2w** | 18 beat / 2 miss | — | — | — | — | **NO-GO (degenerate)** |
| 5 | PEAD beat−miss **4w** | 18 beat / 2 miss | — | — | — | — | **NO-GO (degenerate)** |

Program-level DSR `n_trials = 30` (masterplan §6, not the 5-trial family count). BH-FDR applied within
family: season family {XFN, ZEB}; PEAD family {1w, 2w, 4w} — PEAD produced no computable p-values so BH
is empty.

### The season contrast, in economic terms
The XFN in−out episode contrast is **−0.49%** per season-quarter, HAC t=−2.05 (p=0.04). But daily:
in-window sleeve-excess = **+1.73 bps/day**, out-window = **+1.98 bps/day** — a difference of **−0.24
bps/day**. Both are positive because they are dominated by the Financials dividend carry (XFN close is
total-return, `^GSPTSE` is a price index — see §4). The "effect" is a −0.24 bps/day drift that
compounds to a marginally-significant but **economically negligible** −0.49% over the ~20-trading-day
window. The DSR of a long-XFN-inside-windows strategy net of the out-of-window drift is **0.013** —
nowhere near tradeable. Per-season decomposition: only **May** is meaningfully negative (−1.6 bps/day);
Feb/Aug/Dec are ~flat-to-positive. There is no coherent, sizeable season edge.

**Why NO-GO and not KILL:** the pre-reg reserved KILL for a wrong-sign effect at |t|≥2.0 that you would
actively FADE. At −0.24 bps/day with DSR 0.013, there is nothing to fade — the honest label is a null
with a weak contrary lean, i.e. NO-GO. The directional prior (in > out) is **refuted**; ZEB's sign-flip
across halves confirms there is no stable positive season effect to be found.

### PEAD: degenerate class balance (the pre-stated under-power, made concrete)
Across the 5 in-panel banks × 4 quarters = **20 events**, **18 were beats and only 2 were misses**
(Canadian big-6 beat ~90% of the time in this 2025-26 window). A beat-minus-miss drift contrast on
n_miss=2 is not estimable — no HAC t is defensible. Raw beat-side drift (sector-neutral) is +0.33% /
+0.18% / +0.48% at 1/2/4w, but with no miss counterfactual this is just "banks drift up after reporting
in an up market," not a surprise response. **NO-GO** on all three horizons.

---

## 2. Split-half sign-stability

- **XFN:** early-half in-episode mean +0.12%, late-half +0.58%; both below the out-of-window mean →
  contrast sign **agrees (negative) in both halves**. Stable, but stably in the *wrong* direction for the
  hypothesis — corroborates NO-GO, not GO.
- **ZEB:** early +0.91%, late +0.64%; contrast sign **flips** (positive early, negative late). An
  unstable, non-reproducible effect — exactly what a non-existent edge looks like.

## 3. Effective-N honesty

- Season episodes are **non-overlapping by construction** (anchors ~13 weeks apart, windows ~4 weeks
  wide), so the episode count IS the independent-N: **101 (XFN) / 65 (ZEB)** in-window season-quarters.
  This meets the ledger's "~100 bank-quarters" for the season leg — the leg is decision-grade and it
  says NO.
- `bootstrap_effective_t` on the daily excess found **no autocorrelation reduction** (t_eff ≈ t_raw:
  2023/2023 for XFN, 1115/1296 for ZEB) — the daily sleeve-excess is not meaningfully persistent, so the
  sqrt(T) error bars are not inflated.
- PEAD effective-N = **independent bank-quarter events = 20**, of which only 2 are misses. The ledger
  flagged decision-grade at ~100 bank-quarters (25y of names). On 5y of names (which is all the panel
  has) the leg is structurally under-powered; the result confirms it.

## 4. Survivorship & data stamps

- **PEAD name panel** (`data/canada_search/closes.parquet`, 2021-06→2026-06) is CURRENT-CONSTITUENT
  (survivorship). Bound for the bank set specifically: **≈ nil** — no big-6 Canadian bank delisted in the
  sample; the survivors ARE the population. **NA.TO (National Bank) is absent** from both the earnings
  store and the close panel, so the leg is 5 banks, not the big-6 — a coverage gap, not survivorship.
- **Season ETF legs** (XFN 2001→, ZEB 2010→, `_GSPTSE` 1979→) are index products; survivorship is handled
  by the index methodology. Stamp: *ETF-level, index-methodology survivorship.*
- **Suspension/halt fill rule** (next-bar, roll ≤3 sessions else drop): 0 events dropped — Canadian big-6
  do not halt, so the rule was inert here (but pre-registered and applied).
- **Dividend-drift confounder (handled):** `^GSPTSE` is a price index; XFN/ZEB closes are total-return.
  Financials yield ~3-4%/yr, biasing raw sleeve-excess +3-4%/yr. The in−out **contrast** design cancels
  this constant carry (it is common to both window classes), which is why the reported daily in/out
  excesses are both ~+1.7-2.0 bps/day and the contrast is a clean −0.24 bps/day.

## 5. Exploratory (LABELED, NON-GATED, non-evidential — cannot promote)

Does the season-window contrast extend to the rate-sensitive sleeves (informs a future BoC-window
conditioner)?

| Sleeve | in-episodes | contrast/qtr | HAC t | DSR |
|--------|-------------|--------------|-------|-----|
| XUT.TO (utilities, 2012→) | 58 | +0.28% | 0.61 | 0.06 |
| XRE.TO (REITs, 2002→) | 95 | +0.55% | **1.90** | 0.17 |

Both are POSITIVE (opposite the Financials sleeve's negative sign), and XRE reaches t≈1.9 — a weak,
non-decision-grade hint that the rate-sensitive sleeve, not Financials, is where any bank-season-window
premium might live. This is a design pointer for the BoC-rate-window conditioner (C-BANK's sibling
mechanism), **not** evidence and **not** promotable. Note these were not in the pre-registered gated
trial list; treating them as gated would be post-hoc trial inflation.

---

## 6. What this does NOT show

- It does **not** show Canadian bank earnings are irrelevant to prices — only that a *fixed calendar
  ±2w sleeve-level window* has no positive excess vs the TSX, net of dividend carry. A per-event,
  intraday, or single-name construction could still carry signal; this battery tested the sleeve-window
  and the beat/miss contrast, nothing finer.
- It does **not** test PEAD with adequate power. 20 events (18/2 class split) cannot estimate a
  beat−miss drift. The ledger's decision-grade PEAD needs ~100 bank-quarters (25y of single-name history),
  which the in-tree 5y panel does not have. A future 25y single-name bank panel could revisit this — that
  is an ACCRUE-forward path for the PEAD leg specifically, not a GO here.
- It does **not** cover National Bank (NA.TO absent from the stores) — the "big-6" test is really big-5.
- The exploratory XUT/XRE hint is **not** a validated rate-sleeve season effect; it is a t≈1.9 pointer at
  a non-pre-registered construction, offered only to shape the BoC-window design.
- No claim about intraday or event-window (T0) returns — all fills are NEXT-BAR by construction.

## 7. Registry

Experiment `cbank_season_pead_phase0` registered in `data/experiments/registry_seed.json`: verdict
NO-GO (both legs); PEAD leg accrues toward a 25y single-name revisit (`come_back_on` set); nothing wired.
