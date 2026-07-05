# P1.1 SEPARABILITY — CONFORMANCE REVIEW (Opus reviewer)

**Reviewer:** Opus subagent, Entry Intelligence program
**Review date:** 2026-07-05
**Artifacts audited:** `run_P1_1_SEPARABILITY.py`, `RESULTS.md`, `results.json` (not the runner's summary)
**Independent recompute source:** `data/replay/replay_boarded.parquet` (961,656 rows)

## FINAL VERDICT: CONFORMANT (with 4 ADVISORY findings; 0 BLOCKING)

The study conforms to the approved PREREG grid. All primary statistics, the top-line verdict statistic, the BH family, the census counts, and the survivor logic reproduce independently to the reported precision. Five features (dist_52wh, cohort_washout_proximity, ext_z, ext_atr, weekly_phase) are validly designated SURVIVORS per PREREG §7. No unregistered trial is presented as primary. The advisory items concern disclosure/presentation nuances, not correctness of the verdict.

---

## Per-check results

### CHECK 1 — Trial-grid adherence: **PASS**
- 22 trials executed = 11 features × 2 horizons, exactly the registered grid (PREREG §5, §12; m=22). `results.json` family size = 22, confirmed.
- Feature→column mapping matches the frozen list. `weekly_phase` correctly routed to the pre-registered Kruskal–Wallis branch (§6.1). `adv_dollar_21d` correctly forced to HYGIENE-ONLY (R10) regardless of BH outcome.
- No unregistered feature or horizon appears. `post_hoc_trials_recorded` = [] is truthful — I found none.

### CHECK 2 — Era / stamp discipline: **PASS**
- Primary = `verdict_grade==True & horizon_censored==False`. Independently reproduced: **834,267 rows** (exact).
- Effective window stated as 2022-06-30 → 2026-07-02 (v1.1 Amendment 1). Recomputed signal_date range in primary = **2022-06-30 → 2025-12-29**, inside the window. Assertions in-script guard the bounds.
- `survivor_bias` is False for 100% of rows (961,656) — dataset carries no pre-2021 stamped rows; "context appendix N/A" is truthful.
- `horizon_censored==True` rows (127,389) excluded; this set is the exact complement of verdict_grade==False (127,389). Runner reports both as 127,389 — consistent with the on-disk structure (verified: verdict_grade==True ⟺ horizon_censored==False in this snapshot).
- Mandatory survivor-bias stamp text present in RESULTS.md.

### CHECK 3 — Independent recompute (≥3 headline numbers incl. top-line): **PASS**
Recomputed against the parquet from scratch (mismatch threshold >1%):

| Statistic | Reported | Recomputed | Match |
|---|---|---|---|
| n_primary | 834,267 | 834,267 | exact |
| n_week_clusters | 184 | 184 | exact |
| good_21d base rate | 0.4137 | 0.4137 | exact |
| good_63d base rate | 0.3539 | 0.3539 | exact |
| **dist_52wh ρ_21d (top-line stat)** | **-0.0845** | **-0.0845** | **exact** |
| cohort_washout ρ_21d | 0.0773 | 0.0773 | exact |
| ext_z ρ_21d | -0.0707 | -0.0707 | exact |
| ext_atr ρ_21d | -0.0593 | -0.0593 | exact |
| dist_52wh CR1 p_two_21d | 1.2906e-08 | 1.291e-08 (G=184) | exact |
| weekly_phase KW H_21d | 1571.9 | 1571.91 | exact |
| verdict-grade fires | 49,939 | 49,939 | exact (matches APPROVAL §3) |
| align_tier coverage | 110,392 | 110,392 | exact |
| rs_sector_quartile coverage | 776,439 | 776,439 | exact |

No mismatch >1% on any recomputed number.

### CHECK 4 — BH family: **PASS**
- Family size = 22, FDR q ≤ 0.10, one pooled family across 11 features × 2 horizons per §6.3. Independently re-ran BH over the 22 `p_one` values: **max absolute deviation in adjusted q = 0** vs reported. Monotone step-up and the `× m / rank` threshold are implemented correctly (family size uses m=22, not n_valid — correct).
- p-value pooling matches the registered definition (one-tailed Spearman p in the pre-registered direction; KW p used as-is for weekly_phase, non-directional as registered).
- Sign-stability halves executed as registered: chronological split at the week-cluster midpoint (92/92 weeks, split 2024-W13 / 2024-W14). Binary sign-agreement gate, no split-point tuning. Verified independently that BH passers = {ext_z, ext_atr, alignment_quality, weekly_phase, dist_52wh, cohort_washout_proximity} (6, excl. hygiene); alignment_quality flips sign (h1 +0.080 / h2 -0.011 at 21d) → correctly reclassified UNSTABLE and excluded from the P3 list. Sign-flip rate 1/6 = 16.7% ≤ 50% — reproduced.

### CHECK 5 — n-floors / INSUFFICIENT-POWER: **PASS**
- Effective-N floor = 50 week clusters (PREREG §3, §8). Observed 184 ≥ 50 → power met, correctly not returning INSUFFICIENT-POWER. `insufficient_power_cells` = [] is truthful.
- No borrowing of pre-2021 rows (none exist). Episode-clustered inference honored via CR1 at G=184 clusters, not row count. Effective-N printed alongside statistics.

### CHECK 6 — Honesty surface: **PASS (with advisories)**
- RESULTS.md leads with **VERDICT: SURVIVORS-FOUND** on line 3. Plain-English box present (§"In plain English"). Full 22-row BH table, coverage table, both-halves ρ table, leak audit, sign-flip section, and masterplan §9 status row all present. HYGIENE-ONLY annotation on adv_dollar_21d present. INVERTED-SIGN flags present on knife_z, rs_vs_sector_quartile, side_200dma (features that moved opposite their §5 hypothesis) — correctly printed, direction not re-chosen post-hoc.
- No explicit `board_rank_unresolved` column exists in this snapshot; treated as N/A — acceptable (APPROVAL §4 is conditional "where applicable").

---

## ADVISORY findings (non-blocking)

**A1 — `cohort_washout_proximity` is 100% proxy-sourced; stamp not surfaced prominently.**
`washout_proximity_proxy == True` for **100%** of primary rows (verified). This feature is SURVIVOR rank #2 forwarded to P3. The RESULTS.md leak-audit item #4 acknowledges the proxy stamp exists but frames it as merely "not used as a feature," and does NOT disclose that the *entire* washout signal is proxy-derived. Per memo §6 the honesty surface should carry a proxy stamp on any proxy-sourced feature that feeds downstream. RECOMMENDATION: P3.2 handoff must carry an explicit "PROXY-SOURCED (100%)" stamp on cohort_washout_proximity before any promotion PREREG. (adv_dollar_21d_proxy is 0% — clean; it is hygiene-only anyway.)

**A2 — weekly_phase KW p-value is analytical (iid), not clustered.**
PREREG §6.2 mandates cluster-robust inference for "all 22 tests." The runner applied CR1 clustering to the 20 Spearman tests (permitted equivalent) but used non-clustered `scipy.stats.kruskal` for the 2 weekly_phase cells, justified as "immaterial (H=1571, p≈0)." This is a technically registered-grid deviation (clustering omitted on 2/22 cells). It is immaterial to the verdict: (a) weekly_phase's separate binary sign-stability gate is clustering-agnostic and passes, and (b) even a large clustering deflation cannot lift q≈0 above 0.10. Flagged for the record as a declared substitution, not improvisation. Not blocking.

**A3 — AUC permutation replaced by analytical Mann–Whitney U.**
PREREG §6.1 registered AUC permutation (n_perm=10,000, seed=42). Runner substituted analytical MWU (declared, runtime-justified on cost). Acceptable because AUC is explicitly supplemental and NOT used for BH or any verdict (§6.1). No primary result depends on it. Advisory only.

**A4 — `cohort_washout_proximity` type mismatch (continuous → binary) + per-feature verdict replicated across horizons.**
(i) PREREG §5 #11 labels the feature "continuous"; replay ships it as bool. Runner discloses this in the coverage note; Spearman on a binary is a valid point-biserial — methodologically sound, honestly flagged. (ii) The `verdict` field in results.json is stamped at feature level and copied onto both horizon rows (e.g., ext_atr 63d shows verdict=SURVIVOR despite that row being BH-fail + sign-unstable). This is correct per §7 ("BH q≤0.10 in at least one horizon AND sign-stable") — the surviving horizon (21d) is the one that carries the sign-stability requirement — but the JSON presentation could mislead a reader scanning a single 63d row. Descriptive nuance; no statistical error. Also note weekly_phase's KW is non-directional and its bucket means are non-monotonic (bear_recovering highest, rolling lowest) — the "earlier→better" ordinal story is loose; P3 should treat weekly_phase as a categorical separator, not a monotone rank.

---

## Recompute ledger (for the orchestrator)
n_primary 834,267 ✓ · week_clusters 184 ✓ · good_21d 0.4137 ✓ · good_63d 0.3539 ✓ · dist_52wh ρ_21d -0.0845 ✓ (TOP-LINE) · CR1 p_two 1.291e-08 ✓ · BH family m=22, max q-diff 0 ✓ · KW H 1571.91 ✓ · fires 49,939 ✓ · survivors=5, unstable=1, flip-rate 16.7% ✓
