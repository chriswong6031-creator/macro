# C7 — Canada Momentum Keystone · Phase-0 PRE-REGISTRATION

**Battery:** C7 (HK/Canada masterplan §4.1 C7, trial-ledger §6.1). **Branch:** `hkca-w2-c7`.
**Author:** research agent (Opus). **Pre-reg committed:** before any run (this commit is the audit trail).
**Wiring:** NONE. Reports only (masterplan W2 acceptance). No live engine/board touched.

---

> **ERRATA / ADDENDUM (2026-07-03) — HK reference numbers superseded; the pre-registered text
> below is preserved as committed.** The HK pins cited in §0 and §1.1 (`mom_res` LS Sharpe
> −0.22 full / −0.35 modern, DSR 0.00) came from the pre-2026-06-18 **73-name**
> `data/hk_search/closes_deep.parquet` panel. The panel expanded to **157 names** (2026-06-18
> stamp); the live harness (`scripts/hk_residual_alpha_phase0`) now gives `mom_res` IC +0.012
> (t_HAC 1.28), LS Sharpe **+0.17 full / +0.31 modern**, DSR 0.28/0.33 — still fails DSR in every
> window. The expansion sign-flipped a near-zero Sharpe, not the verdict: the HK **KILL stands on
> DSR/IC grounds, not sign**, so the §0 honest prior (`mom_res` on CA prior-lean NO-GO by analogy)
> is unchanged. The **§1.1 acceptance gate is superseded** by the masterplan §4.1 C7 re-wording
> (PR #1047): the fork must reproduce, **to the digit, a same-day fresh run of
> `scripts/hk_residual_alpha_phase0` on the current HK panel — never a frozen numeric pin**; the
> ±0.05 tolerance around −0.22/−0.35 is void. (§3's "the HK `mom_res` outcome" KILL example: on
> the live panel the HK result maps to this doc's NO-GO band — near-zero-positive Sharpe, DSR
> near 0 — while the house verdict label remains KILL.) Reference:
> `reports/hk-residual-alpha-phase0.md` (regenerated).

---

## 0. Question & honest prior

**Question.** On Canada, does cross-sectional momentum (total OR beta-stripped residual) predict
forward returns strongly enough to become the standout-board *rank basis* — measured on THIS market,
under the house validation constitution (HAC t, BH-FDR within family, program-level DSR ≥ 0.90,
split-half sign-stability, independent-episode effective-N)?

**Why this is the keystone.** Masterplan §4.1 C7 verdict branches gate the whole CA board:
- **Branch A** — ANY leg GO → that leg becomes the CA rank basis, cited.
- **Branch B** — ALL NO-GO and no other C-leg GO'd → the board falls to the ripe-list contract
  (§5.0) permanently, composite suppressed, tier=screen. *A planned outcome, not a failure.*

**Honest priors (pre-stated, per masterplan §4.1):**
- HK precedent (`reports/hk-residual-alpha-phase0.md`) says the *residual* construction is **dead**
  on a beta-dominated Asian large-cap panel: `mom_res` LS Sharpe −0.22 full / −0.35 modern, DSR 0.00
  *(numbers superseded — see Errata 2026-07-03 above; prior-lean unchanged)*.
  So `mom_res` on CA is prior-lean NO-GO by analogy.
- Canada literature (Foerster et al. and the TSX momentum literature) says **total-return** momentum
  is plausible on Canadian equities.
- The **ETF (sector-sleeve) leg is the strongest-powered** (25y of history vs 5y for names) and is
  the leg most likely to reach the DSR bar. Names leg is 5y / ~60 monthly rebalances → borderline
  power; state it up front.
- Net expectation: this battery is **more likely to resolve NO-GO / ACCRUE than GO**. That is a
  respectable, pre-committed outcome (masterplan W4 has a planned zero-GO Branch B).

---

## 1. Harness — a REAL FORK (masterplan §0.1(4))

`scripts/residual_alpha_phase0.py` is US-hardwired (SPY, GICS→SPDR, `_closes()` US breadth). The
existing HK fork `scripts/hk_residual_alpha_phase0.py` reuses `score_panel`/`quintile_ls`/`ew_peer`
from that base on a deep HK panel. C7 forks **`scripts/canada_residual_alpha_phase0.py`**, mirroring
the HK fork's structure, parameterized for:

- **market benchmark** `^GSPTSE` (`data/canada/_GSPTSE.parquet`, `close` col, 1979→).
- **names close panel** `data/canada_search/closes.parquet` (219 .TO names, 2021-06-14→2026-06-30).
- **sector map** from `data/canada_search/members.parquet` (`sector` col; 11 GICS-ish sectors).
- **sector-ETF panel** `data/canada/{XEG,XFN,XGD,XMA,XIT,XUT,XRE,XST,XCG,XCD,ZEB,XBM}.TO.parquet`.
  Per-pair inception stated: XEG/XFN/XGD/XMA/XIT/XUT/XRE/XST/XCG/XCD 2001-03→; **XBM 2012-01-24→**.

### 1.1 ACCEPTANCE GATE (mandatory, before any CA run)
The fork MUST reproduce the known **HK kill** when pointed at the HK configuration
(`reports/hk-residual-alpha-phase0.md`): `mom_res` LS Sharpe ≈ **−0.22 full / −0.35 modern**,
tolerance **±0.05**. Achieved by importing the SAME shared `score_panel`/`quintile_ls`/`ew_peer`
that the HK fork uses and running the HK panel through the fork's own code path. If it cannot
reproduce within tolerance, the fork is fixed before CA runs; the reproduction numbers are pasted
into the report. (No CA verdict on an unvalidated harness.)

*(Gate superseded — see Errata 2026-07-03 above: per masterplan §4.1 C7 (PR #1047) the fork must
reproduce, to the digit, a **same-day fresh run** of `scripts/hk_residual_alpha_phase0` on the
current HK panel — never the frozen −0.22/−0.35 pin, which the 2026-06-18 73→157 panel expansion
sign-flipped to +0.17/+0.31 while leaving the KILL intact.)*

### 1.2 Construction (fixed before running)
Mirrors the shared harness exactly (betas causal, lagged 1d, shrink 0.66; formation 252d skip 21d =
"12-1"; forward horizon 21d; monthly rebalance grid; next-bar fill via `.shift(-horizon)` forward
returns and `pos = w.shift(1)` on the LS book):

- **`mom_tot`** = total-return 12-1 momentum (formation sum of daily returns, skip last 21d).
- **`mom_res`** = residual (beta-stripped) 12-1 momentum.
  - **Names leg:** full market+sector residual `e_i = r_i − b_m·m − b_s·s̃` (s̃ = EW-peer sector
    return orthogonalized to market), identical to the HK/US/CN construction.
  - **ETF leg:** the 12 ETFs are each their own singleton sector, so the sector-orthogonalization
    leg is **degenerate** (sector return ≡ own return ⇒ residual → 0). Confirmed by construction.
    The ETF-leg `mom_res` therefore strips **market beta only**: `e = r_etf − b_m·m_gsptse`
    (rolling causal 252d beta, lagged 1d, shrink 0.66). This is a documented, honest fork-specific
    code path, not the base construction. Stated here so it is pre-registered, not a post-hoc choice.

### 1.3 Fills, suspension, survivorship
- **Next-bar fills:** forward returns from `.shift(-horizon)`; LS positions `w.shift(1)` (base harness).
- **Suspension/halt:** CA .TO large-caps rarely halt for weeks (unlike HK); the panel is daily-clean
  2021→. No silent ffill through multi-day gaps introduced beyond the base harness behavior. Any name
  with a >5-day interior gap in its formation window contributes NaN (dropped that date) — inherited
  from the base `pct_change(fill_method=None)` + `min_periods`.
- **Survivorship BOUND (not stamp):** `data/canada_search/closes.parquet` is **current-constituent**
  (219 names on today's TSX composite membership); no dead-name store ex-US. The names leg is
  survivorship-biased UP (delisted losers absent → momentum long-short flattered). We report this as
  a **bound**: a names-leg GO is treated as an *optimistic upper bound*; a names-leg NO-GO is
  *conservative* (survivorship only helps momentum, so a fail on the survivor panel is a strong fail).
  The ETF leg is survivorship-clean (ETFs are the sleeves themselves, continuously listed).

---

## 2. Pre-registered trials (exactly 4)

| # | Signal  | Universe                    | Panel span (expected)        | Effective-N basis                          | Decision-grade? |
|---|---------|-----------------------------|------------------------------|--------------------------------------------|-----------------|
| 1 | mom_tot | names monthly 2021→ (~60)   | 2021-06→2026-06, ~48–54 rebal | independent monthly xsec ≈ 24 (2 non-overlap 21d/mo → ~half) | Borderline power |
| 2 | mom_res | names monthly 2021→ (~60)   | same                         | same                                       | Borderline; prior NO-GO (HK analogy) |
| 3 | mom_tot | sector-ETFs monthly 2001→ (12) | 2002→2026, ~285 rebal (XBM 2012→) | ~24 indep years × sector cycles; ~285 monthly xsec | **YES (strongest)** |
| 4 | mom_res | sector-ETFs monthly 2001→ (12) | same                         | same                                       | YES |

BH-FDR is applied **within the family of 4** (the C7 family). The IC scorecard emits additional
diagnostic rows (`ir_res`, `rev_st`, `acc_res`, `|SN` variants) inherited from the shared harness;
these are **diagnostic, NOT pre-registered decision trials** and are excluded from the C7 GO decision
(they are labeled as such in the report). The 4 trials above are the only ones eligible for a GO/NO-GO.

---

## 3. Pre-registered GATES (constitution)

A trial is **GO** only if ALL of the following hold (pre-committed thresholds):

1. **IC direction & HAC t:** mean rank-IC > 0 AND Newey-West HAC t ≥ **2.0** (matches the house bar;
   `ic_summary` periods_per_year=12).
2. **BH-FDR within the C7 family (α=0.10):** the trial's HAC p-value survives BH across the 4 trials.
3. **Deflated Sharpe ≥ 0.90** on the top-vs-bottom-quintile dollar-neutral net-of-5bps LS backtest,
   computed with **program-level `n_trials = 30`** (masterplan §6 — every config across both markets,
   NOT just this family). `deflated_sharpe(...)` legacy `n_trials=30` path.
4. **Split-half sign-stability:** the LS net-return sign (and IC sign) must be the SAME in the first
   and second time-half of the panel. A sign flip across halves ⇒ NOT GO (fragile / regime-specific).
5. **Effective-N honesty:** report the independent-episode / independent-monthly-xsec count, not the
   row count. A trial whose effective-N cannot support DSR≥0.90 is capped at **ACCRUE** regardless of
   point estimate.

**Verdict mapping (pre-committed):**
- **GO** — all 5 gates pass.
- **ACCRUE** — positive point estimate (IC>0, LS Sharpe>0) but at least one of {HAC t<2.0, fails FDR,
  DSR<0.90, split-half borderline} while direction is stable. A marginal result is ACCRUE, never
  tortured into GO.
- **NO-GO** — IC≈0 or LS Sharpe≈0/positive-but-DSR-near-0, direction unstable or economically null.
- **KILL** — negative LS Sharpe / anti-predictive IC (the HK `mom_res` outcome). A KILL means the
  construction is actively harmful and must never be wired.

**Branch trigger (pre-committed, masterplan §4.1):**
- If **any** of trials 1–4 is GO → Branch **A**: that leg becomes the CA rank basis (the ETF leg
  ranks names via sector membership; the names leg ranks names directly). Report states which.
- If **all 4** are NO-GO/KILL/ACCRUE (no GO) → Branch **B**: the CA board runs the **ripe-list
  contract (§5.0) permanently**, composite suppressed, tier=screen. Stated as planned success.

---

## 4. Deliverables
1. `scripts/canada_residual_alpha_phase0.py` (the fork; acceptance-gated).
2. `reports/c7-canada-momentum-phase0.md` — **verdict in bold** first, HK-reproduction numbers,
   pre-reg-gates-vs-results table, split-half, effective-N honesty, survivorship bound, and an
   explicit "what this does NOT show" paragraph.
3. `data/experiments/registry_seed.json` entry (id `c7_canada_momentum`, maturation, come_back_on).
4. NO wiring.

---

## 5. What this pre-reg deliberately does NOT claim
- It does not claim the names leg can reach DSR≥0.90 (5y / ~24 independent monthly xsec is thin;
  it is pre-flagged borderline → likely ACCRUE at best).
- It does not claim survivorship neutrality for the names leg (bounded, not stamped).
- It does not test name-level "catch-up gap" (masterplan dropped it; empirical sign against).
- It does not test any construction other than the 4 pre-registered trials for a GO decision.
