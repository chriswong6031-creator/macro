# REVIEW — FINAL CUMULATIVE (P2 board stack) · PR #1472 · branch `ei/p2-board-stack`

**Reviewer:** Opus 4.8 subagent (Entry Intelligence, Phase-2 — final mergeability review)
**Date:** 2026-07-05
**PR state:** OPEN, `mergeable: MERGEABLE` (gh)
**Commits reviewed (cumulative):** 44c7adf1 (contract v2) → 4b1b1f49 (realbuild verify) → fbf920ee (4-defect fix-pack) → 189f489f (P2.1a shadow gate) → 4bebc067 (P2.1b concordance-halt artifact)
**Binding:** R1–R10 (masterplan), R-P2.1 (flip floor = 100 clusters + 2 quarters), R-P2.2 (single concordance authority = P2.1b §3.3), R7 (additive-lanes), R10 (liquidity/display-only), t-macro law, P0_MEASUREMENT_MEMO §6
**Specs:** `P2_4_BOARD_CONTRACT_V2_DESIGN.md` (+Amendments a/b/c), `P2_1A_ANTICHASE_GATE_PREREG.md`, `P2_1B_RANKWEIGHT_PREREG.md §3.3`
**Prior reviews consumed:** REVIEW_P2_4.md (CLEAN+adv), REVIEW_P2_1A.md (CLEAN+2adv), VERIFY_P2_4_REALBUILD.md (PARTIAL), VERIFY_P2_4_FIXPACK.md (PASS)
**Method:** read-only. `gh pr diff/view`, `git show origin/ei/p2-board-stack:<path>`, `git diff origin/main...branch`, read-only pandas/json on committed artifacts. No shared-checkout mutation, no merge, no git write ops.

## VERDICT: CLEAN — #1472 is mergeable under R8.

Zero blocking findings. Ranking neutrality holds end-to-end **at both the code level and the committed-artifact level**. The concordance halt held: no shadow-weight wiring exists in the diff. Zero enforcement on `antichase_shadow_blocked`. All prior-review findings are either fixed-and-verified (the 4 fix-pack defects) or carried forward as documented non-blocking advisories.

---

## Diff scope (full PR)
`git diff --stat origin/main...origin/ei/p2-board-stack` — 10 files, +1046/−12:
- `scripts/build_stock_library.py` (+262) — Steps A–H, all additive/label/ledger
- `templates/dashboard.html.j2` (+69) — lane/200DMA/ext_z/antichase chips + lane_counts pill
- `data/species/registry.json` (+103/−1) — F3_ANTICHASE entry
- `scripts/p2_1b_concordance_check.py` (+212) + `p1_runs/P1_3/concordance_check.json` (+27) — halt artifact
- `p2_reviews/VERIFY_P2_4_REALBUILD.md`, `VERIFY_P2_4_FIXPACK.md` — verify docs
- `site/factordata/{setups,signal_gate,us_standouts}.json` — rebuild snapshots (see §Area 8)

No `engine/` file touched. No `stock_score.py` / `extension.py` touched. Confirmed via `git diff --name-only`.

---

## Per-area PASS/FAIL

### Area 1 — Ranking neutrality end-to-end — **PASS**
- **Code:** `_combine_key`, `_asort`, `_atier`, `_entry_ok`, `_alpha_key`, `blend_sorted` appear in added lines **only inside comments/docstrings** — zero code mutation. Per-commit audit of all 5 commits: the only hits in 44c7adf1 are the scope-boundary docstring (L47–48) and the tier-fallback comments. Grep of the entire PR diff for `blend_sorted|f1_bonus|f2_bonus|f1_weight|f2_weight|shadow_weight|rank_bonus|rank_adj|reweight` → **NO MATCHES**.
- `buyable`/`_recovery_cands`/`watch`/`buyable_trend[:120]` are READ, never filtered/reassigned. `_tag()` mutates only display fields (`align_tier`, `lane`) and runs *after* the alpha sort; it does not feed back into ordering.
- `rank_by` in `us_standouts.json` header stays `"bottoming-alignment"` (verified on committed artifact: main and branch both `"bottoming-alignment"`).
- **Artifact-level proof:** on the 18 buy rows common to main and branch `us_standouts.json` (same `as_of=2026-07-02`, same `gate_go=False`), **zero** ranking-relevant field values changed (`composite_z`, `alpha`, `entry_ok`, `gate`, `setup`, `cycle_state` all identical). The only per-row key additions are `above_trend` + `weekly_phase`; zero keys removed.

### Area 2 — Zero enforcement on `antichase_shadow_blocked` — **PASS**
- Token appears at exactly 3 sites: Step G set-site (else-branch → `False`), Step H ledger read, template `{% if %}` chip render. **No conditional anywhere drops/moves/reorders/gates a row on it.** No `continue`/`del`/`pop`/`filter`/`gate_go` keyed on the flag.
- `_all_buy_rows` is finalized (L2298) and placed in `wide["buy"]` (L2312) *before* Step G runs (L2335). Step G mutates in place only.
- Committed artifact: all 42 buy+watch rows remain present (18+24); `#blocked=0` on this snapshot (ext_z absent → `False`), so enforcement is trivially null even in the degenerate case.

### Area 3 — No shadow-weight wiring (concordance halt held, R-P2.2) — **PASS**
- Concordance check verdict = **REPROBE_REQUIRED** (66.40% < 90% floor). F1 shadow does **not** ship.
- Diff contains **no** `blend_sorted` modification, **no** `f1_bonus`/`f2_bonus` wiring, **no** score-composite change. Verified by grep + full read of the build diff. The PR *title/commit-44c7adf1 message* say "shadow weights," but the AS-BUILT diff contains none — the halt (4bebc067) blocked them by design. This is correct, not a discrepancy to fix (title is cosmetic; code is authoritative).

### Area 4 — Row-set preservation (fix-pack backed) — **PASS**
- VERIFY_P2_4_REALBUILD.md: on identical data, v1 vs v2 → buy set IDENTICAL (18/18), laggards IDENTICAL (12/12); watch diverged by 1 name (STAA↔MCRI) attributed to pre-existing `ProcessPoolExecutor` nondeterminism at the 24-slot boundary — **not introduced by v2** (ranking code byte-identical to main confirms this).
- VERIFY_P2_4_FIXPACK.md: `above_trend` 0%→100% (buy 18/18, watch 24/24); `above_trend == signal.above200` agreement 10/10; watch `lane` None→"watch" (lane_counts null-key eliminated); zh tooltip fixed.

### Area 5 — F3_ANTICHASE registry entry (R-P2.1 floors) — **PASS**
- Valid JSON. `deployment_status=chip`, `validation_status=phase0_passed`, `market_scope=[US]`, trials `[T21,T22,T24]`.
- Flip criteria C1 (≥100 clusters AND ≥2 quarters) / C2 (Wilson 95% LB on D>0 @63d) / C3 (sign-stable both halves); rollback RB1/RB2/RB3; `flip_floor_clusters=100`, `flip_floor_quarters=2` — **matches R-P2.1 and PREREG §2.2 exactly**. Signed quantity D = stop_out(blocked)−stop_out(unblocked); C2 lower-bound>0 and RB1 upper-bound<0 match §2.2/§5 with no sign inversion.
- `ledger_binding.ledger = data/signal_archive/antichase_shadow_ledger.parquet` — matches the writer path.

### Area 6 — Ledger writer safety — **PASS**
- Path: `config.data_dir() / "signal_archive" / "antichase_shadow_ledger.parquet"`. `lib.config.data_dir()` resolves to `.../data`; `data/signal_archive/` is the **production** forward-outcome archive (holds `allocation_us.parquet`, `baskets.parquet`, etc.), matching the sibling idiom in `calibrate_baskets.py`, `ab_risk_gate.py`, `engine/signal_archive.py`. This is the correct PRODUCTION dir **by design** for live accrual (the verification runs used copies; production writes here). ✔ per task mandate.
- **Never-fatal:** whole block wrapped in `except Exception … # noqa: BLE001 — shadow ledger is never fatal` → `log.debug(...skipped...)`. Matches the established repo convention (10+ sibling BLE001 uses).
- **Keep-first dedup:** `_seen_shadow = set(zip(old.asof, old.ticker))`; new rows skipped when `(asof,ticker) in _seen_shadow`. Append-only concat, keep-FIRST per (asof,ticker).
- Records both blocked and unblocked rows (control group for C2 Wilson bound). Schema: asof/ticker/lane/ext_z/antichase_shadow_blocked/flip_eligible=False/flip_criteria_met=False/gate_state="shadow"/logged_at.
- Sentinel-staging: `data/` is git-tracked and committed via the broad `git add data/` glob (daily.yml/asia-close.yml) — no staging-gap; sentinel-commit-step-staging-gap law not tripped.

### Area 7 — zh tooltip fix — **PASS**
- REVIEW_P2_4 ADVISORY-5 flagged ASCII `"趋势"` inside `data-tip-zh` truncating the Chinese continuation tooltip. Fix-pack fbf920ee replaced it with CJK corner brackets `「趋势」`. Confirmed present at branch `dashboard.html.j2` L2858. lane_counts pill zh-dict uses `.get(_ln, _ln)` fallback (no jinja-missing-key crash on unknown lane).
- AC-4 i18n guard: ran `check_title_i18n` on the branch template → **OK** (discriminating — the guard fires on real violations per #1095).

### Area 8 — Concordance artifact internal consistency — **PASS**
Arithmetic reconciles exactly:
- `n_prod_true+false+none = 36734+10448+2757 = 49939 = n_population` ✔
- `n_valid_pairs = 49939−2757 = 47182` ✔
- `n_agree/n_valid_pairs = 31331/47182 = 0.66405 = concordance_rate` ✔
- disagreements `108+15743 = 15851 = 47182−31331` ✔
- `15743/47182 = 33.4%` matches verdict_note ✔
- verdict `REPROBE_REQUIRED` because `0.664 < 0.90` ✔; direction `production_finds_more_washout` consistent with proxy_false_prod_true≫proxy_true_prod_false. F2 independence note present and correct (F2 not proxy-sourced).

### Area 9 — Site/factordata JSON churn — **PASS (benign rebuild snapshot)**
The three site JSONs differ in buy SET/ORDER between main and branch **despite same `as_of`** — resolved as a label-additive rebuild on evolved upstream data, NOT a re-ranking:
- Branch `us_standouts.json` = 18 buy (matches the fix-pack real-build run), `branch buy ⊆ main buy` (branch-only=∅; 3 main-only names CUBE/NJR/OGE fell off on the rebuild day's upstream data). rank_by unchanged.
- Since the ranking CODE is byte-identical to main (Area 1), the set difference cannot originate from this PR — it is a different-build-day snapshot. Confirmed by zero ranking-field drift on overlapping rows.
- `setups.json`: rank_by None→"alpha" (AC-6), every buy row now has non-null lane, lanes ∈ {bottoming, continuation}. `us_standouts.json` lane_counts = {continuation:10, bottoming:8, watch:24} (non-zero, no null key); AC-3 set-membership violations = NONE.

---

## Advisories carried forward (all non-blocking, no rank/gate/data impact)
1. **Stale committed site snapshots.** The committed `site/factordata/*.json` predate the P2.1a Step G field: `antichase_shadow_blocked` and `ext_z` are absent/None on 100% of rows in the committed artifact (built by fix-pack fbf920ee, *before* P2.1a 189f489f). The **code** sets both unconditionally on all buy+watch+laggard rows; the next production nightly populates them. Absence in the committed JSON is a rebuild-timing artifact, matching the established "site artifacts are rebuild snapshots" pattern. Recommend the orchestrator confirm ext_z/antichase fill on the first post-merge nightly.
2. **ext_z 0% in isolated worktree (data-environment).** Documented in VERIFY_P2_4_FIXPACK.md: crypto's 2026-07-05 row misaligns the concat date index in the isolated worktree → `ext_z.iloc[-1]=NaN`. Code structurally correct; production date alignment fills it. Until then, `ext_z=None → antichase_shadow_blocked=False` (fail-safe: zero blocks, zero enforcement).
3. **Gate keys off rounded ext_z** (REVIEW_P2_1A ADVISORY-2a): Step G reads `r["ext_z"]` = `round(ext_z,2)`; raw values in (2.000, 2.005] round to 2.00 and escape the `>2.0` test — ±0.005 boundary shift vs raw PARABOLIC_Z. Negligible; shadow-only; no neutrality impact.
4. **Ledger has no forward-outcome column** (REVIEW_P2_1A ADVISORY-1): the (asof,ticker) join to forward-grading infra for C1/C2/C3 is a monthly-review build, not part of this PR. Expected (chip rung ships now; ledger_fields rung deferred).
5. **`align_tier` emitted-vocabulary switch** (REVIEW_P2_4 ADVISORY-1 → **ratified** as Amendment (a)): `_eff_tier = conviction.alignment.tier or tier` emits PRIME/ARMED on trend rows. Ratified as canonical lane source; downstream (P2.1 ledger stratification, P3 rollups) must read both vocabularies — the `_PRIME_EQUIV`/`_ARMED_EQUIV` mapping handles this.
6. **Cosmetic:** `_NEAR_EQUIV` includes `bear_recovering`/`turning` (weekly_phase-domain, unreachable as align_tier) — Amendment (c) notes for future cleanup. Registry JSON lacks trailing newline (style nit).

---

## What could NOT be verified (honest gap)
Full nightly build over R2/Massive stores was not run (absent from git; R2 law). Populated-value assertions for `ext_z`/`antichase_shadow_blocked` on a real build are code-path-verified only. First post-merge nightly should confirm: (a) ext_z fills once date index aligns, (b) antichase_shadow_blocked/ledger row accrual to `data/signal_archive/antichase_shadow_ledger.parquet`, (c) lane_counts non-zero on live vocabulary. None of these gate mergeability — they are forward-monitoring items.

---

*Review completed 2026-07-05. Read-only; no merge, no shared-checkout mutation, no git write ops. This document is data for the Fable orchestrator.*
