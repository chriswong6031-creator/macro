# P2_1B_F1_REPROBE — CONFORMANCE REVIEW

**Reviewer:** Opus subagent (Entry Intelligence program, Fable orchestration)
**Date:** 2026-07-05
**Artifacts reviewed:** `run_P2_1B_F1_reprobe.py`, `results.json`, `RESULTS.md`, `_run.log`
**Binding:** PREREG `P2_1B_RANKWEIGHT_PREREG.md` §3.3/§6/§8/§11; P0_MEASUREMENT_MEMO §6; masterplan R1–R10
**Method:** independent recompute from raw data (`/tmp/f1_reprobe_verify.py`, written from scratch — did NOT import or call the runner's script)

## VERDICT: CLEAN

The reprobe is a faithful, reproducible re-encoding of F1 on production COILED values. Every task-mandated check passes on independent recomputation. The headline claim — the P1.3 F1 RW ship-qualifying safety-net effect (T09, 63d stop-out) **reverses sign** from −4.55pp (proxy, favorable) to **+3.34pp (production, unfavorable)** — is reproduced exactly by the reviewer's own code. The verdict `PROMOTION_DIES_PROXY_ONLY` follows mechanically from the PREREG rule.

---

## Independent verification results (reviewer's own compute path)

| # | Task-mandated check | Runner claim | Reviewer independent recompute | Match |
|---|---|---|---|---|
| — | Replay MD5 | `906175f9eb8...` | `906175f9eb8caa351ed6d7d5c56265d3` | ✓ |
| — | engine/coiled.py == 4bebc06716 | byte-identical | `git diff 4bebc06716 -- engine/coiled.py` empty | ✓ |
| — | Population census | 49,939 fires / 22,295 clusters / survivor_bias=0 | 49,939 / 22,295 / 0; pairs 1:1 with fires | ✓ |
| **1** | Production washout genuinely PIT | — | 20 spot name-dates recomputed via own PIT slice + `washout_ctx`; all ran clean (0 errors), all had ≥308 PIT bars → bool (consistent with None-rule) | ✓ |
| **1** | Consistent with concordance artifact | True=36734/False=10448/None=2757, conc=0.664046, pf_pt=15743 | **True=36734 / False=10448 / None=2757 / conc=0.664046 / pf_pt=15743** (full recompute of all 49,939 pairs) | ✓ exact |
| **2** | Calibration control genuine (≥50 draws) | neg rej=0.085 (200 draws, seed 777); pos perm_p=2.0e-4 | reviewer seed=9999, 60 draws: **rej=0.067 ≤ 0.12, KS-p=0.876**; pos perm_p=2.0e-4 | ✓ PASS |
| **3** | BH family = 10 registered, no extras | m=10, family `P2_1B_f1_concordance_reprobe`, n_survive=8 | 10 trials T01–T10, all factor=F1; reviewer BH recompute n_survive=8, min=0.00033; per-trial survives all match | ✓ |
| **4** | Side-by-side numbers reproduce (≥3 incl. headline) | T09 +3.3435pp; T02 −15.107pp; T04 −0.866pp | **T09 +3.3435 (nA=27403 nB=19779, rA=0.63716 rB=0.60372); T02 −15.1068 (36734/10448); T04 −0.8658**; T09 halves H1 +1.9188 / H2 +4.9938; midpoint 2024-05-13 | ✓ exact |
| **5** | Verdict follows PREREG rule mechanically | PROMOTION_DIES_PROXY_ONLY | T09 survives_bh=T, sign_stable=T, not-thin, **favorable=F** → survived_favorable=F → promotion_survives=F → DIES | ✓ |
| — | Proxy-side provenance | copied from P1_3 | side_by_side proxy fields == `P1_3/results.json` trials exactly (0 mismatches) | ✓ |

Full recompute of all 49,939 production washout values matched the concordance artifact's aggregate exactly. Because that aggregate is a deterministic function of the per-pair values, exact aggregate agreement plus clean spot-recomputes establishes the per-name PIT values are genuine.

---

## The one interpretive judgment (resolved: conformant)

**PREREG §3.3 literal text** (lines 118, 444) states the reprobe ship criterion as "BH-survive + sign-stable + n_clusters ≥ 25" — it does not literally enumerate a fourth "favorable-direction" boolean. The runner's `survived_favorable()` adds `delta_favorable` as a fourth condition. I checked whether this is a faithful reading or an added hurdle that improperly killed the promotion.

**Resolved conformant.** T09 on production is BH-surviving, sign-stable, and above the 25-cluster floor (n_ep_A=13,088) — so under a pure-literal reading that ignores direction, the shadow would "ship" a promotion whose measured effect is **+3.34pp *higher* stop-out**. That is logically incoherent with the promotion's own basis:

- **§6.2** defines the safety-net axis as `D_f = stop_out(bonus) − stop_out(non-bonus)` and states explicitly **"D_f < 0 is the favorable direction,"** requiring `Wilson_upper(D_f) < 0` to flip. The flip criterion *is* directional.
- **§6.6** makes the production T09 direction (D_f = +3.34pp, bonus cohort stop-out credibly *higher*) the **shadow-falsification** signature, not a confirmation.
- The **species evidence stack** (line 270) names the ship-qualifying effect as "T09 63d stop-out Δ=**−4.55pp** ... sign-stable" — a *favorable* (negative) delta.

Requiring `delta_favorable` therefore operationalizes §6.2/§6.6 faithfully; dropping it would ship a "safety-net" tilt that increases stop-outs, contradicting the very criterion (§6.2) that authorizes the flip. The runner's reading is not merely acceptable — it is the only defensible one. Verdict is mechanically correct.

---

## Secondary conformance observations (all clean)

- **Concordance reproduction gate** ran before the grid and reproduced exactly; the run did not proceed on broken provenance.
- **Negative calibration control ran before the grid** (mandatory per PREREG), on the production encoding, and passed on both the runner's seed (rej 0.085, 200 draws) and the reviewer's independent seed (rej 0.067, 60 draws).
- **Sanity gate** (param/perm divergence, the P1.3 round-1 defect signature) did not trip — confirmed in `_run.log` and `results.json.sanity_gate.tripped=false`.
- **No extra trials** presented as primary; BH family is exactly the 10 PREREG-registered trial IDs.
- **F2 correctly scoped out** — RESULTS.md states F2's evidence base is not proxy-sourced and may proceed independently per §11. This matches PREREG §11.
- **Proxy numbers not fabricated** — all side-by-side proxy-column values equal `P1_3/results.json` verbatim.

## Minor note (non-blocking, no action required)

`research/entry_intel/p1_runs/P1_3/concordance_check.json` — referenced by the runner (`CONCORDANCE_JSON`, line 68) and cited in RESULTS.md — is absent from the current working tree (present in git at commit `4bebc06716`, from which the reviewer confirmed the reference values). The run does **not** depend on the file: `CONCORDANCE_REF` is hard-coded (lines 84–91) and matches the committed artifact bit-for-bit, and `CONCORDANCE_JSON` is assigned but never read in the executed path. No impact on conformance or reproducibility. Likely deleted by a concurrent worktree checkout.

## Blocking findings
None.

## Advisory findings
1. `concordance_check.json` missing from working tree (present at 4bebc06716; run does not read it). Cosmetic — restore for artifact completeness if the P1_3 dir is to be self-contained.
