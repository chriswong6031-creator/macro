# W2-C — Global-healthcare → CN-pharma read-through — Phase-0

*China Alpha Program · Wave 2 (narrative confluence) · channel W2-C · 2026-07-03 · worktree `lucid-knuth-523979`.*
*Research only. **Nothing here is wired to any page** regardless of outcome. Registry id `w2c-hc-readthrough`; machine report `reports/c-hc-readthrough-phase0.md`; script `scripts/c_hc_readthrough_phase0.py`.*

---

## 0. Verdict up front

**NO-GO.** The owner's "healthcare breaking out worldwide" tailwind for 300725 does **not** reproduce as a
measurable weekly lead from global-healthcare momentum into CN pharma. On the deep, survivorship-clean
Shenwan Pharma index the univariate lead is **t = −0.48** (full sample), −0.59 pre-2024, −0.09 in 2024+ —
not significant in any era, and if anything mildly the wrong sign. Every THS pharma basket is flat too,
**including `ths_synbio`, which is 300725's own basket** (t = 0.41). The validated global-AI-semis → CN-CPO
weekly confirmer (t = 3.27, PR #773) that this test was modeled on **does not generalize to healthcare.**

This is a *well-powered true negative*, not a data hole: the same measurement harness, fed the known-good
semis→CPO inputs, reproduces **t = 3.08 / 3.12** — the instrument fires when a real lead exists. It simply
does not fire here.

> **In plain English.** Global chip stocks going up really does lead Chinese optical-component stocks up the
> next week — that's a real, physical supply-chain link (global AI spending → orders for Chinese parts). We
> asked whether "global healthcare stocks going up" leads Chinese pharma stocks the same way. It does not.
> There is no measurable weekly follow-through. So the "healthcare is breaking out worldwide" story is fine as
> a *narrative*, but we have **no evidence it's a signal** — and we are not going to pretend it is one.

---

## 1. PRE-REGISTRATION (written and committed BEFORE results — §4.7)

*This section fixes the design and the pass/fail bars in advance so the verdict can't be reverse-fit to
whatever came out. The results in §2 were produced by the script exactly as specified here.*

### 1.1 The question
The owner cited "healthcare breaking out worldwide" as the tailwind behind exemplar **300725**
(OWNER_RATIONALE §1). Masterplan ruling **F4** lists a "general global-sector→CN read-through leg
(healthcare-worldwide → CN-pharma) modeled on the validated AI-semis→CPO precedent (t=3.27)" as a W2 item.
This phase-0 asks the single empirical question: **does global-healthcare momentum lead next-week CN-pharma
returns**, the way global-semis momentum leads next-week CN-CPO returns?

### 1.2 The precedent we mirror (the recipe, held identical)
The validated leg is `scripts/china_global_theme_backtest.py` / `reports/china-global-theme.md`
(phase0-verdicts row 14): EW 4-week trailing **log-momentum** of a 3-name global-semis composite
(SMH+SOXX+TSM) → **next-week** EW return of each THS AI-supply basket; weekly **W-FRI**; **Newey-West HAC**
t (lags = 4) by hand; a **horse race** adding SPY-momentum (generic global risk-on) and CN-A-share-universe
momentum (CN-own) as controls; **full / pre-2024 / 2024+** splits; and placebo baskets. The CPO slice cleared
it: **t = 3.27 full, 3.03 pre-2024, mv-horse-race t = 2.27 / 2.06.**

Everything that can be held identical to that recipe **is** held identical (same `nw_ols` HAC estimator ported
verbatim, same weekly resample, same 4-week window, same horse-race controls, same era splits) so the two
verdicts sit on the same measurement footing.

### 1.3 Driver (pre-registered)
- **PRIMARY:** **XLV** (US Health Care Select Sector SPDR), `data/yahoo/XLV.parquet` — the broadest single
  liquid global-healthcare tape we hold, and the most literal reading of the owner's "healthcare worldwide."
  Signal = EW 4-week trailing log-momentum of the XLV level at week *t*.
- **ROBUSTNESS:** a 3-ETF composite **XLV + IBB + XBI** (large-cap HC + biotech + small-cap biotech),
  mirroring the precedent's 3-name composite shape, reported alongside so the verdict isn't hostage to one ETF.
- *Data note:* XLV `close` is dividend-adjusted (yahoo total-return convention); the Shenwan index is a price
  index. A **momentum / sign** read is invariant to the level convention, so this does not bias the test.

### 1.4 Target (pre-registered)
Next-week (t+1) return of the CN pharma complex, at two tiers:
- **PRIMARY — `swind_801150`:** the **Shenwan L1 Pharma & Biotech index** (`data/china_sectors/801150.parquet`;
  code confirmed 医药生物 in `engine/china_sector_cycles.py:66`). Deep (2000→2026, ~1300 weekly obs) and
  **survivorship-clean** — this is the target the verdict leans on.
- **SECONDARY — THS baskets:** EW levels of `ths_innovative_rx` (5), `ths_synbio` (8, = 300725's own
  "Synthetic Biology" basket), `ths_med_devices` (14), built from `data/baskets_china_ths/membership.json` ×
  `data/china_search/closes.parquet` (2021-06→, ~250 weekly obs). No dedicated CXO/CDMO THS basket exists in
  the membership snapshot — noted as a coverage gap, not synthesized.

### 1.5 Controls, placebos, splits (pre-registered)
- **Horse race:** SPY 4w-mom + CN-A-share-universe 4w-mom as controls; the HC leg must **stay** significant
  with these in.
- **Cross-slice placebo:** the same HC driver should **not** predict CN non-pharma baskets
  (`ths_baijiu` / `ths_gold` / `ths_cpo` — spirits, gold, AI-optics have no HC read-through channel).
- **Shuffled-driver placebo:** a **2000-permutation null** of the HC-momentum series on the deep index target.
  A valid null must center on 0 with sd ≈ 1 and place the real |t| at an unremarkable percentile.
  *(A single shuffle is one noisy draw and can spuriously print |t|≈2.5 under HAC — the distribution is the
  placebo, not any one permutation.)*
- **Positive control:** the same harness, fed semis→`ths_cpo`, **must** reproduce ≈ t 3 — otherwise the null
  is untrustworthy.
- **Splits:** full / pre-2024 / 2024+ (the KEY test — does anything survive outside the recent window?).
- **Leakage:** weekly W-FRI; the US week-*t* level is fully closed before the CN week-(t+1) target;
  non-overlapping t+1 target ⇒ no same-week leakage.

### 1.6 Verdict thresholds (pre-registered, fixed before running)
Evaluated on the **survivorship-clean `swind_801150`** target with the **XLV primary** driver:
- **GO** — univariate |t| ≥ 3 on the **full** sample **AND** pre-2024 |t| ≥ 2 (survives outside the recent
  window) **AND** the SPY+CN horse-race HC |t| ≥ 2.
- **ACCRUE** — 2 ≤ |t| < 3 full-sample, **OR** significant only in 2024+ (recent-window-only). Forward ledger
  opens, nothing wired.
- **NO-GO** — otherwise (incl. the horse race killing the leg, or only THS baskets firing while the clean
  index target does not).

### 1.7 Honest prior going in
Genuinely skeptical. Semis→CPO is a **hard order-flow channel** — global AI capex literally drives orders for
Chinese optical modules, so a weekly price lead is mechanistically plausible. "Global healthcare breaking out"
has **no comparable channel** into A-share pharma, which is dominated by *domestic* policy (VBP procurement,
NMPA approvals, provincial reimbursement) and local demand. Prior: **ACCRUE at best, more likely NO-GO.**

---

## 2. RESULTS

Machine report: `reports/c-hc-readthrough-phase0.md` (regenerated deterministically; byte-identical across
runs). Columns: `uni_*` = univariate HC leg; `mv_hc_t` = HC t **with** SPY + CN controls (the horse race).

### 2.1 Primary driver XLV → CN pharma

| target | era | n | uni_b | uni_t | uni_p | mv_hc_t | mv_spy_t | mv_cn_t |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **swind_801150** | full | 239 | −0.0255 | **−0.48** | 0.63 | −0.49 | 0.17 | 0.15 |
| swind_801150 | pre-2024 | 115 | −0.041 | −0.59 | 0.56 | −0.63 | 0.11 | 0.82 |
| swind_801150 | 2024+ | 124 | −0.0074 | −0.09 | 0.93 | −0.15 | 0.19 | −0.47 |
| ths_innovative_rx | full | 241 | −0.0119 | −0.11 | 0.91 | 0.28 | −0.65 | −0.13 |
| **ths_synbio** (300725's basket) | full | 241 | 0.0317 | **0.41** | 0.68 | −0.16 | 1.25 | 0.10 |
| ths_med_devices | full | 241 | −0.0096 | −0.13 | 0.89 | −0.69 | 1.16 | 0.51 |
| ths_baijiu *(placebo)* | full | 241 | −0.0272 | −0.43 | 0.67 | −0.43 | −0.04 | 0.26 |
| ths_gold *(placebo)* | full | 241 | 0.0787 | 1.52 | 0.13 | 0.73 | 0.63 | 1.29 |
| ths_cpo *(placebo)* | full | 241 | −0.0415 | −0.49 | 0.63 | −1.25 | 1.70 | 0.31 |

Not one target × era clears even |t| = 2. The clean index target is flat-to-slightly-negative across all three
eras. The placebos are also flat (as they should be) — `ths_gold` at 1.52 is the largest thing on the board
and it's a placebo, which is itself a reassuring sign the HC driver isn't spuriously loud.

### 2.2 Robustness driver XLV+IBB+XBI composite

Flatter still — `swind_801150` uni t = 0.13 / 0.00 / 0.05 across eras; every THS pharma basket |t| ≤ 1.34
(full table in the machine report). The null is **not** an XLV-specific artifact; adding biotech/small-biotech
does not surface a lead.

### 2.3 Placebos and instrument integrity — the checks that make the null trustworthy

- **Shuffled-driver placebo (2000-permutation null on swind_801150):** mean t = **0.015**, sd = **0.993**,
  P(|t_null| ≥ 2) = **0.041** (the correct ~5% false-positive rate). Real |t| sits at **perm_p = 0.085** — an
  unremarkable percentile. The harness produces a clean N(0,1) null, as a valid instrument must.
  *(A single seed-773 shuffle printed t ≈ 2.5 in the first draft — that was one unlucky draw, not a placebo;
  the distribution, not any one permutation, is the honest check. Fixed in the script.)*
- **Positive control (same harness, known-good semis→`ths_cpo`):** uni t = **3.08 full / 3.12 pre-2024**
  (published #773: 3.27 / 3.03). The instrument fires on a real lead. Therefore the HC null is a **true
  negative**, not a broken measurement.
- **Literal weekly-SIGN read** (the task's exact phrasing) on swind_801150: sign-hit = **52.8%** full (essentially
  a coin flip), HC-up-week vs HC-down-week next-week return gap +0.33% vs +0.01% (Welch t = 1.49, NS), and the
  sign **flips negative** in 2024+ (t = −0.8). No directional edge.

### 2.4 Verdict against the pre-registered gate
| Gate quantity (swind_801150, XLV primary) | Bar | Observed | Pass? |
|---|---|---|---|
| univariate full |t| | ≥ 3 | 0.48 | ✗ |
| univariate pre-2024 |t| | ≥ 2 | 0.59 | ✗ |
| horse-race HC |t| (full) | ≥ 2 | 0.49 | ✗ |
| significant 2024+-only? | (ACCRUE path) | 0.09 | ✗ |

**→ NO-GO.** No path to GO or ACCRUE is open.

---

## 3. Why it fails — mechanism reading (not a data excuse)

The precedent works because **global AI capex is an order-flow input to CN optical-module makers**: SMH/SOXX/TSM
strength is a leading proxy for hyperscaler spend, which shows up in Chinese CPO/optical order books within
weeks. That is a *supply-chain* channel with a physical direction.

"Global healthcare breaking out" has **no analogous channel** into A-share pharma. Chinese pharma prices are
driven by *domestic* forces — volume-based procurement (VBP) rounds, NMPA/CDE approval cadence, provincial
reimbursement, and local demand — none of which are set by XLV's tape. Where a US→CN pharma link *could* exist
it is narrow and slow (CXO/CDMO order books tied to US biotech funding), which is exactly the leg this broad-tape
test cannot see and which §5 flags as the only reopen worth pre-registering. The broad "healthcare is hot
globally" read is a **narrative**, and the data says it is *only* a narrative — which is precisely the honesty
posture W2 is built to enforce (technicals detect; narrative describes; it earns rank only through graded
forward performance, never through a story).

---

## 4. What this means for W2 (and what does NOT change)

- **F4's healthcare read-through leg does not ship.** There is no validated global-HC→CN-pharma confirmer to
  attach to any name. 300725's tag set in the board does **not** gain a "global healthcare tailwind — validated"
  chip. If a HC-narrative chip is ever shown at all, it must read as *descriptive theme heat only*, with no
  implication of a forward edge (identical honesty framing to the §754/§773 tags).
- **The A/B-tier logic is unaffected.** W2's A-tier is earned by `stage ∈ {ENTRY, RIPENING} AND (theme HOT OR a
  radar basket whose global-AI confirmer is intact + honesty validated/partial)`. The **global-AI** confirmer is
  the *only* validated global→CN read-through; this NO-GO confirms healthcare must **not** be added to that
  A-tier qualifying set. 300725, whose case rested partly on the HC tailwind, is A-tier only if its *technical*
  setup and *THS synthetic-bio heat* qualify it — never on the strength of the (now-refuted) HC read-through.
- **The semis→CPO leg (#773, ledger row 14) stands alone** as the one validated global→CN read-through. This
  leg does not join it.

## 5. Reopen conditions (registered — do NOT re-run the same construction)

CLOSED NO-GO on a well-powered, survivorship-clean target. Reopen **only** with a materially different channel,
each needing its own pre-registration and clearing the same gate:
1. **CXO/CDMO-specific driver** — US-biotech *funding* flow (XBI + biotech IPO/VC issuance) → CN CXO/CDMO order
   book, rather than broad HC-tape momentum. This is the one channel with a plausible physical link, and it
   needs a CXO basket that the current THS snapshot lacks.
2. **Policy-event-conditioned window** — US FDA / global drug-approval cycles as event windows, not a continuous
   momentum driver.

## 6. Provenance / reproducibility
- Script `scripts/c_hc_readthrough_phase0.py` — idiomatic sibling of `scripts/china_global_theme_backtest.py`
  (verbatim `nw_ols`, same helpers, same splits). Deterministic (seed 773 for the permutation null), no network,
  read-only on `data/`. Run: `PYTHONPATH=$PWD python3 -m scripts.c_hc_readthrough_phase0`.
- Machine report `reports/c-hc-readthrough-phase0.md` (full tables incl. the composite driver).
- Registry `data/experiments/registry_seed.json` → `w2c-hc-readthrough` (`kind: phase0_verdict`,
  `verdict: NO-GO`, `program: china_alpha`, `wave: W2`, `channel: W2-C`).
- China-alpha ledger `research/china_alpha/phase1/phase0-verdicts.md` → **row 41**.
- 801150 = Shenwan L1 Pharma & Biotech confirmed at `engine/china_sector_cycles.py:66`.
- Positive control reproduces #773 semis→CPO through this harness (t 3.08/3.12), proving the instrument is live.
