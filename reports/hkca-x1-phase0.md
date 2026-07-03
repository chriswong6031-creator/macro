# X1 — A-Twin Read-Through — Phase-0 Report

**VERDICT: (a) A-3M-reversal read-through = NO-GO · (b) A-1M-momentum lead = ACCRUE (near-GO) · (c) double-cheap interaction = NO-GO (refuted).**
The A-share twin's *reversal* state does NOT read through to rank the H leg's forward
return (primary trial (a): rank-IC −0.007 at 3m, t −0.28; the drift-free long/short is
*negative*, t −1.01 — the only positive number, the +1.71% top-5 long-only excess, is the
TR-vs-price dividend drift plus shared HK/China beta, not ranking skill). The A twin's
*1-month momentum* DOES carry a weak, sign-stable, H-own-return-orthogonal read-through
into the H leg (trial (b): rank-IC +0.034 at ~1m, HAC-t 1.67; survives the H-own-return
control keeping 80% of magnitude; FDR-reject; split-half + era stable) — **but it lands in
the ACCRUE band, not GO: IC-t 1.67 < 2.0, L/S-t 1.51 < 2.0, DSR 0.846 < 0.90.** The
double-cheap cell (c) does NOT beat H-discount-alone (+3.09% vs +3.00%, and the panel is
+2.40%), so the A-washout adds nothing on top of H3's premium — the interaction premium is
refuted. **This is not the program's first GO.** Nothing is wired.

Pre-registered: `research/HK_CANADA_X1_PREREG.md` (committed BEFORE any run — see git
commit `6b34a91ef9`, timestamp precedes the result commit). Code:
`research/hk_x1_atwin_readthrough.py`. Raw: `research/hk_x1_results.json`.
**Data state:** 25 A/H pairs (`data/hk_ah_panel/pairs.json`), per-name A closes
`data/china_stocks/*.parquet` + H closes `data/hk_stocks/*.parquet` (all 25 present, joint
depth 1053–6386 days, fresh to **2026-07-03**), HSI `data/hk/_HSI.parquet` (→2026-07-03),
premium `data/hk_ah_panel/premium.parquet` (5711×25) — read from the session worktree
absolute path (gitignored/R2).

---

## 1. Gates vs results

Binding horizon per trial: (a) 3m, (b) ~1m. All 7 gates must pass for GO (prereg §7).

| Gate | Requirement | (a) A-3M-rev @3m | (b) A-1M-mom @~1m |
|---|---|---|---|
| 1 rank-IC > 0 both horizons, same sign | IC>0 @binding & @2nd | **−0.007 / −0.020 (both <0)** ❌ | **+0.034 / +0.014 (both >0)** ✅ |
| 2 HAC-t ≥ 2.0 on top-5 AND L/S | both ≥ 2.0 | top5 2.09 ✅ / **L/S −1.01** ❌ | top5 3.09 ✅ / **L/S 1.51** ❌ |
| 3 BH-FDR reject (q ≤ 0.10) | q ≤ 0.10 | q 0.046 ✅ | q 0.005 ✅ |
| 4 DSR ≥ 0.90 (budget 36, t_eff) | ≥ 0.90 | **0.542** ❌ | **0.846** ❌ |
| 5 split-half AND era sign-stable | no flip | +0.015/+0.019; +0.017/+0.017 ✅ | +0.006/+0.016; +0.007/+0.015 ✅ |
| 6 C1: resid-vs-H-own-ret IC keeps sign & ≥50% mag | sign + ≥50% | IC≈0 → control undefined n/a | keep 80%, sign OK ✅ |
| 7 survivorship: edge survives both haircuts | no vanish/flip | IC −0.015 / −0.007 (stays ≤0) ❌ | (a-only; b not haircut) — |

**(a) fails gates 1, 2, 4, 7 → NO-GO.** **(b) passes 1, 3, 5, 6; fails 2 (L/S), 4 (DSR) →
ACCRUE per prereg §8** ("IC>0 both horizons, HAC-t ≥ 1.5 at binding, FDR-reject, but
DSR < 0.90 → ACCRUE — near-GO"; binding IC-t 1.67 ≥ 1.5).

### Full numbers

| trial | horizon | rank-IC | IC HAC-t | top-5 excess | top5 HAC-t | L/S mean | L/S t | DSR | t_eff | n | C1 keep |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **(a) A-3M-rev** | **3m** | **−0.007** | −0.28 | +1.71% | 2.09 | −0.79% | −1.01 | **0.542** | 129 | 215 | 1.49\* |
| (a) A-3M-rev | 1m | −0.020 | −1.03 | +0.48% | 1.14 | −0.26% | −0.61 | 0.174 | 218 | 218 | 0.52 |
| **(b) A-1M-mom** | **~1m** | **+0.034** | 1.67 | +1.14% | 3.09 | +0.67% | 1.51 | **0.846** | 209 | 220 | 0.80 |
| (b) A-1M-mom | ~2w | +0.014 | 0.83 | +0.58% | 2.09 | +0.28% | 0.98 | 0.561 | 220 | 220 | 2.13\* |

\* C1 keep-fraction is spurious when the raw IC is ≈0 (dividing a near-zero residual IC by
a near-zero raw IC) — read C1 only for trial (b) @~1m where the raw IC is meaningfully
non-zero (keep 0.80, sign-preserved: the read-through is NOT the H leg's own dead price
state relabeled).

BH-FDR (α=0.10, family = 5 binding+secondary excess p-values): a_rev_63 q=0.046 (reject),
b_mom_21 q=0.005 (reject), b_mom_10 q=0.046 (reject), c_double q=0.005 (reject),
a_rev_21 q=0.253 (no). FDR rejects the *long-only excess* p's — but the long-only excess is
drift-contaminated; the drift-free binding legs (rank-IC, L/S) are what the verdict rests on.

---

## 2. Why (a) is a NO-GO — the honest diagnosis

The A-3M-reversal read-through has **exactly one positive number: the +1.71% top-5
long-only excess (HAC-t 2.09)**. Every drift-free measure is flat or negative:
- **rank-IC = −0.007 (t −0.28)** at 3m and **−0.020 (t −1.03)** at 1m — the signal does
  not rank H forward returns; if anything, weakly the wrong way.
- **dividend-neutral L/S = −0.79% (t −1.01)** — the top-minus-bottom of the A-washout
  signal *loses* on the H leg.
- **survivorship haircuts** (drop 5 youngest pairs; deep-core ≥12y) leave the IC negative
  (−0.015, −0.007) — the null is not a fragile-pair artifact.

The +1.71% top-5 is therefore the **TR-vs-price dividend drift** (H legs are dividend-
adjusted total return, HSI is a price index → any long-only H basket beats the HSI by the
dividend yield) plus the shared HK/China beta of a concentrated 5-name basket — NOT
A-state ranking skill. Pre-registered §9 named this exact contamination; the L/S and
rank-IC are the drift-free binding legs, and both say NO-GO.

**Positive control (instrument check, prereg-spirit §3.4):** on these same 25 A-names the
A-3M-reversal signal predicting the A leg's OWN forward 63d return has rank-IC +0.018
(t 0.70, hit 54.5%) — correctly-signed but weak. So the validated broad-universe
china-reversal edge (+0.56%/mo on 388 names) is *thin on this 25-name large-cap dual-listed
subset* to begin with, and it does not survive the crossing into the H leg. The read-through
null is real, not a broken instrument.

## 3. Trial (b) — the near-GO, and why it stays ACCRUE

The A twin's **1-month momentum** does carry a weak read-through into the H leg's next
~month: rank-IC +0.034 (t 1.67), same sign at ~2w (+0.014), FDR-reject, split-half stable
(+0.006 → +0.016), era-stable across the 2016-12 Shenzhen-Connect break (+0.007 pre /
+0.015 post — larger post-segmentation, consistent with the mechanism, read with the
2024–26 dividend-tax-cycle confound in mind). It **survives the key C1 control**: residualized
against the H leg's own trailing 1M return it keeps 80% of magnitude with the sign intact —
so this is not the (dead, H4-killed) H-side momentum re-expressed; the A leg carries
*incremental* short-horizon information. The sign matches the pre-registered lead-lag story
(A discovers China-local info first; H catches up).

But it is **not GO**: the two drift-free significance legs both land at 1.5–1.7 (IC-t 1.67,
L/S-t 1.51), below the 2.0 bar; DSR is 0.846, below 0.90 at the program budget of 36 and
t_eff 209. Per prereg §8 this is precisely the **ACCRUE — near-GO** band (the H3 outcome
shape). The +3.09 top-5 t is drift-inflated and is not the binding number. Do not torture
0.846/1.67 into a GO.

## 4. Trial (c) — double-cheap interaction refuted (ACCRUE-capped)

The candidate "about to run" cell — A-washout (A-reversal top-tercile) AND H-discount-extreme
(premium own-pctile top-tercile) — has forward-3m excess **+3.09% (HAC-t 3.08)**. But:
- **H-discount-alone = +3.00% (t 3.86)** — statistically stronger than the double cell.
- **A-washout-alone = +2.00% (t 2.66)** — weaker.
- **panel mean = +2.40% (t 3.68)**.

So the double cell does **not** exceed H-discount-alone, and barely clears the panel. Adding
the A-washout condition on top of the H3 premium buys nothing (it just concentrates into the
H-discount names, whose +3.00% is the whole effect). **The interaction premium is refuted** —
there is no synergistic "double-cheap" cell; H3's premium tilt already contains what little
edge exists here. Capped at ACCRUE by construction regardless (subset-of-subset, prereg §8).

## 5. Split-half, era, effective-N, survivorship

- **Split-half (median-date):** (a) +0.015→+0.019 (a's long-only drift is stable but the
  IC/L/S are the binding null); (b) +0.006→+0.016, sign-stable, stronger recent.
- **Era (2016-12 SZ-Connect break):** (a) +0.017/+0.017; (b) +0.007 pre / +0.015 post.
  No flips. (b)'s larger post-segmentation number sits inside the 2024–26 dividend-tax
  confound → not clean OOS.
- **Effective-N:** binding t_eff (block-bootstrap, block=3 on the monthly excess) = 129 (a,
  3m) / 209 (b, ~1m) — pre-stated expectation "≈120–140 at 3m" landed. The 25-pair
  cross-section is one correlated HK/China basket → breadth adds signal, not independent
  time; t_eff (not 25×T) is the honest sample, as pre-registered.
- **Survivorship (a):** dropping the 5 youngest pairs → IC −0.015; deep-core ≥12y → IC
  −0.007. The (a) null is robust to the fragility/inclusion haircut (it does not flip
  positive). These bounds cover inclusion+fragility, NOT delisting survivorship (no PIT
  dual-listing registry in-tree) → the reported (b) IC remains an UPPER bound.

---

## 6. What this does NOT show (pre-committed, prereg §9)

- **No causal segmentation-lead mechanism** — (b) is a cross-sectional association between
  A 1M momentum and H forward, confounded with shared China/HK beta, sector, size, and the
  same 2024–2026 southbound dividend-tax cycle that confounds H3.
- **No true PIT market-cap / size control** — none in-tree; the C1 (H-own-return) and the
  premium controls bound but do not eliminate a size bet in (b).
- **No delisting-survivorship correction** — reported (b) IC is an UPPER bound.
- **A-close TR-vs-price adjustment unasserted** — mitigated by the within-history-z
  transform (invariant to constant drift) but a non-constant adjustment could bias the z.
- **TR-vs-price benchmark mismatch** — the +1.71% (a) and +1.14% (b) *long-only* excess
  each carry a positive dividend drift; the drift-free rank-IC and L/S are the binding legs
  and are what the verdicts rest on. This is why (a)'s single positive number is not skill.
- **25 names, one correlated basket** — cross-sectional breadth is not independent time;
  (b) is an edge *candidate* on the deepest matched panel we have, not an institutional
  claim. The FX control (prereg C2) was subsumed into the premium-level control (no clean
  in-tree CNH/HKD series at build); an FX-carry component of (b) cannot be fully ruled out.

---

## 7. Registry / next

Registry entry appended at the END of `data/experiments/registry_seed.json` experiments
array (`hkca_x1_atwin_readthrough`, status `accrue` on leg (b), come-back 2027-07 as the
matched panel deepens). **NO WIRING** — nothing enters any board, composite, or engine.
The one lead worth accruing is **(b) A-1M-momentum lead** (near-GO, orthogonal to the dead
H-side factor); (a) reversal read-through and (c) the double-cheap interaction are killed.
