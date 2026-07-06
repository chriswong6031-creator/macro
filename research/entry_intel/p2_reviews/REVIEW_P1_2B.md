# REVIEW — P1.2b Taxonomy Extension (Re-tag + Mini-PREREG)

**Reviewer:** Opus subagent (Entry Intelligence, Phase-2 review)
**Date:** 2026-07-05
**Build under review:** PR #1471, branch `ei/p1-2b-taxonomy` (NOTE: task named `ei/p2-board-stack`, which does not exist on origin; reviewed the actual builder branch)
**Spec:** `research/entry_intel/P1_2B_TAXONOMY_EXTENSION_SPEC.md`
**Artifacts inspected:** `run_P1_2B.py`, `RESULTS.md`, `results.json` (committed); `data/replay/replay_boarded.parquet` + `data/replay/replay_boarded_p12b.parquet` (present locally, not committed per R9)
**Method:** cumulative PR diff read via `git show origin/…`; every AC re-derived independently from the two parquets (no reliance on builder-reported numbers).

---

## Verdict: FINDINGS (buildable-upon, with one deviation logged for the record)

The build is scientifically sound and the stage may be built upon. All byte-identity gates and coverage gates pass under independent reproduction, the mini-PREREG is honest (0/16 BH-significant, no candidate laundered upward), and the outcome (both codes KEEP-by-default) is robust to the one spec deviation found. No BLOCKING finding. Two ADVISORY findings are logged: a documented departure from the spec §2.1 priority rule (the `board_rank_cutoff` override), and an internal spec contradiction that the builder resolved reasonably but silently.

---

## Independent reproduction (all figures below re-derived from the parquets, not taken from the report)

| Check | Reproduced value | Report / json value | Match |
|---|---|---|---|
| Rows (orig / p12b) | 961,656 / 961,656 | 961,656 | ✅ |
| Columns differing whole-frame (orig vs p12b, original order) | **only `rejection_reason`** | (asserted) | ✅ |
| V1 fire byte-identity | True, 57,640 fire rows | PASS, 57,640 | ✅ |
| V2 near-miss identity (excl. rejection_reason) | True, 17,587 rows | PASS, 17,587 | ✅ |
| V2b verdict_type whole-frame identity | True | PASS | ✅ |
| freshness_expired tagged (whole frame) | 8,789 (all near_miss, all from NaN) | 8,789 | ✅ |
| freshness_expired verdict-grade in-era | 7,319 | 7,319 | ✅ |
| tier_cutoff tagged (whole frame) | 158 (121 from board_rank_cutoff + 37 from NaN) | 158 | ✅ |
| tier_cutoff verdict-grade in-era | 131 (100 rejection + 31 near_miss) | 131 | ✅ |
| primary verdict-grade rows in era | 834,267 | 834,267 | ✅ |
| board_fire pool (vg, in-era) | 11,069 | 11,069 | ✅ |
| stamped (survivor_bias=True) | 0 | 0 | ✅ |
| min raw p across all 16 trials | 0.5025 | (0.5025) | ✅ |
| BH significant @ q≤0.10 (m=16) | 0 (rank-1 threshold 0.00625 ≪ 0.5025) | 0 | ✅ |

Every headline number in the builder report reproduces exactly.

---

## Per-acceptance-criterion verdicts

**AC-1 (harness change correctness) — PASS.**
V1, V2, V2b all reproduce True independently; whole-frame diff touches only `rejection_reason`. V3 coverage: freshness_expired=7,319 (in [1,000–30,000]) and tier_cutoff=131 (in [50–400]); both ≥50 verdict-grade floor met. Confirmed.

**AC-2 (no verdict contamination) — PASS with an ADVISORY caveat.**
P1.2b produces verdicts only for `freshness_expired` and `tier_cutoff`; it does not re-open or re-derive any of the five original P1.2 verdicts, and the P2.2 candidate list is empty. The original P1.2 verdicts live in the original artifact / P1.2 RESULTS, which is untouched. **However:** the re-tag overwrote 100 verdict-grade `board_rank_cutoff` rows (13,676 → 13,576 vg in the p12b artifact). Because P1.2b never re-runs board_rank_cutoff *from the p12b artifact*, this does not contaminate any live verdict — but the p12b artifact is no longer a faithful superset of the P1.2 board_rank_cutoff cohort. Any future study that (wrongly) re-derives board_rank_cutoff from `replay_boarded_p12b.parquet` would get a mutated cohort. Logged as ADVISORY-1.

**AC-3 (INCONCLUSIVE is honest) — PASS on the AC-3 floor; deviates from the §3.4 POWER NOTE floor.**
tier_cutoff n_survived=10. AC-3 (§3.7) sets the INCONCLUSIVE floor at n<10, so n=10 is above it and the builder returns KEEP+THIN — literally AC-3-compliant. But §3.4 POWER NOTE (binding) says "If n < 25 after Step 3 pruning … return INCONCLUSIVE and label THIN." n=10 < 25 ⇒ §3.4 mandates INCONCLUSIVE. The spec is internally contradictory (n<10 in AC-3 vs n<25 in §3.4). The builder followed the AC-3 floor. **Practical impact is nil:** all 8 tier_cutoff trials have p≥0.57, so the verdict is KEEP-by-default (= "no candidate advances") whether labelled KEEP-THIN or INCONCLUSIVE-THIN; nothing is laundered to P2.2 either way. Logged as ADVISORY-2 for label hygiene only.

**AC-4 (BH discipline) — PASS.**
Independent BH over the 16 trials: family `ei_gate_pnl_p12b`, m=16, q≤0.10; rank-1 threshold = 0.10/16 = 0.00625; smallest observed p = 0.5025. 0/16 significant. No p-value crosses into the original m=72 `ei_gate_pnl` family. No DEMOTE/FLIP, empty P2.2 list. Confirmed.

**AC-5 (board-demotion confound remains open) — PASS.**
extension/knife/sector_cap_displaced are not re-tested; RESULTS §7 explicitly re-casts their P1.2 KEEP as non-informative per D2 and defers a demoted-vs-board_fire counterfactual to P1.2c/P2.2. Confirmed.

---

## Validation-gate spot-checks (executed, not trusted)

- **V1 / V2 / V2b:** re-ran the exact spec §2.3 assertions on the two parquets — all True. The only whole-frame column delta is `rejection_reason`; no fwd_ret / terminal_state / episode_id / survivor_bias field moved.
- **Re-tag surgery scope:** transition table is exactly {NaN→freshness_expired: 8,789; NaN→tier_cutoff: 37; board_rank_cutoff→tier_cutoff: 121}. No fire row re-tagged; no verdict_type migration.
- **freshness_expired carve-out:** 100% of the 8,789 are verdict_type=near_miss with near_miss_reason='freshness_expired' and were previously NaN — a clean, fully spec-§2.1-Change-1-compliant carve-out.

---

## Findings

### ADVISORY-1 — tier_cutoff re-tag overwrites 121 non-null `board_rank_cutoff` rows, violating the spec §2.1 priority rule
Spec §2.1 states verbatim: *"if `rejection_reason` is already non-null from another path, do not overwrite — the first-assigned reason wins. The above assignments only apply when `rejection_reason` is null or absent."* The build does the opposite for tier_cutoff: it tags **all** `gate_reason=='tier T4 (weight 0.4)'` rejection/near_miss rows, overwriting 121 rows that already held `board_rank_cutoff` (100 of them verdict-grade). Under the strict null-only rule, only the 37 previously-NaN near_miss rows qualify — which would yield ~37 tier_cutoff rows and **fail** the ≥50 V3/AC-1 floor. So the deviation was load-bearing for passing AC-1.

Mitigating context (why this is ADVISORY, not BLOCKING):
- The spec's own registered predicate for Change 2 — `verdict.get("tier_cascade") == "T4"` — returns **zero rows** in this substrate (the `tier_cascade` column never holds the string "T4"). The literal spec code contract is *unsatisfiable*; §1.1's prose (which cites the `gate_reason` "tier T4 (weight 0.4)" field and the ~131 count) is the only self-consistent reading. The builder followed §1.1's prose and count target.
- The RESULTS.md is fully transparent: §1 re-tag-logic and the §9 masterplan row both state the board_rank_cutoff override explicitly. No concealment.
- The override does not touch any live verdict (see AC-2).

Recommended follow-up (not blocking): a one-line spec amendment reconciling §2.1's null-only priority rule with §1.1's "override board_rank_cutoff" intent, so P1.2c does not inherit an ambiguous contract. Ideally the p12b artifact would retain a provenance column (e.g. `rejection_reason_p1.2`) so board_rank_cutoff can still be reconstructed from the p12b file.

### ADVISORY-2 — tier_cutoff verdict labelled KEEP-THIN where §3.4 POWER NOTE mandates INCONCLUSIVE-THIN
n_survived=10 < 25. §3.4 (binding) says n<25 ⇒ INCONCLUSIVE; AC-3 says n<10 ⇒ INCONCLUSIVE. The two floors contradict. The builder's `verdict_from_deltas()` uses the n<10 floor and returns KEEP. Practically inert (all p≥0.57 ⇒ KEEP-by-default either way; no P2.2 candidate). Recommend the tier_cutoff row read INCONCLUSIVE-THIN to match §3.4's stricter, more honest floor, and that the spec's two floors be reconciled.

---

## Non-findings verified clean
- No verdict_type migration anywhere (V2b holds).
- No pre-2021 / stamped-row borrowing to reach a floor (0 stamped; era filter 2022-06-30→2026-07-02 applied).
- Reads the p12b artifact only for the study (per §3.6); original parquet touched only for the re-tag/MD5/validation, as the spec requires.
- NOT-AVAILABLE-IN-SUBSTRATE text for event_blackout and cohort_null present verbatim (§2.4).
- All 10 required report sections (§5 report contract) present.
- Matched pool correctly restricted to `board_fire` only (2,471 matchable of 11,069) per the §3.1 confound fix.

---

## Bottom line
CLEAN-enough to build upon. Both new codes resolve to KEEP-by-default with 0/16 BH-significant; no gate-design candidate advances to P2.2. The single load-bearing deviation (board_rank_cutoff override) is transparently documented, does not alter any live verdict, and stems from an unsatisfiable literal predicate in the spec itself. Fix-forward items are spec-hygiene, not re-runs.
