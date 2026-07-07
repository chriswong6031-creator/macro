"""Apply the FROZEN §17 outcome handling after the IX-1 run (results wave).

Everything this script writes was pre-committed in PREREGISTRATION.md §17 "Outcome handling
(frozen)" — it makes no judgments, it executes them. The run produced 0 PASS / 4 (the 0/4
null branch FIRED), so per the frozen handling:

  1. Truths (engine.cycle_pattern.truths): ONE scoped null truth
     `cycle_truth_ix1_index_transfer_null_v1` — "the member-trained hazard does not
     transfer to index level against index age-pooled KM" — with the down cells' passing
     CI/BH legs and the year-concentration named inside the statement (honest scope: the
     null is about the frozen conjunction, i.e. reliability, not the pooled point
     estimate), and the §17 falsifiers (stacking trial / post-embargo accrual) as the
     reopening conditions.
  2. NO factory candidates (frozen: candidates are written only on PASS).
  3. No page/UI change; the markets.html US-row engine-backing wave is moot on 0/4.
     Exploration tables (full pre-embargo index KM + per-entity ΔBrier decomposition)
     ship inside the artifact.

Idempotent: every write is guarded by an existence check, so re-runs are no-ops.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.cycle_pattern import truths as T  # noqa: E402

_ARTIFACT = _REPO / "data" / "cycle_pattern" / "ix_trials" / "ix1_transfer.json"
_VERDICT_DOC = "research/cycle_masterplan/CPI_IX1_VERDICT.md"

_NULL_TRUTH = "cycle_truth_ix1_index_transfer_null_v1"


def apply_truths(artifact: dict) -> None:
    n_pass = artifact["n_cells_pass"]
    assert n_pass == 0, "this script encodes the 0/4 null branch (frozen §17 handling)"
    led = artifact["ledger"]
    all_ids = {t.get("truth_id") for t in T.load_truths()}
    if _NULL_TRUTH in all_ids:
        print(f"[truths] {_NULL_TRUTH}: already present — skipped")
        return
    T.append_truth({
        "truth_id": _NULL_TRUTH,
        "version": 1,
        "status": "promoted_null",
        "owner_program": "cycle-intelligence",
        "statement": (
            "IX-1 (§17): the member-trained W4.2 hazard model does NOT transfer to index-level "
            "entities (SPY + 7 blocs) against each index's own age-pooled KM under the frozen "
            "gate — 0/4 cells (CI90 positive AND BH q=0.10 AND years+ >= 9). Up cells show no "
            "earned skill (1m dBrier +0.0099, CI90 [-0.0056,+0.0247], 8/14 years; 3m -0.0018, "
            "straddles). Down cells show REAL pooled improvement (1m +0.0335, CI90 "
            "[+0.0084,+0.0590], p 0.011; 3m +0.0290, CI90 [+0.0129,+0.0455], p 0.001; both "
            "BH-pass) that FAILS the sign-stability leg (5/13 and 7/13 vs bar >=9): the gain is "
            "year-concentrated (2021 year-mean +0.31/+0.25 dominates; 2020 harmful -0.16) — "
            "episodic, not reliable. Scoped to THIS transfer recipe: member-fit L2 logistic + "
            "member train-fold standardization + member-fit per-fold PAV, no index-row fitting, "
            "no index covariates (sync/phase-breadth/dispersion RESERVED, unused). NOT a claim "
            "that index-level turn hazards are unpredictable."
        ),
        "effect_class": "null",
        "scope": {"families": ["us_market", "bloc"],
                  "regions": ["us", "global"],
                  "sample": "index panel panel_index_v0 (8 entities, epoch price_c4414dcb), "
                            "member panel price_c4414dcb, embargoed <2024-01-01, "
                            "test years 2010-2023"},
        "target": "index_level_turn_event_1m_3m_brier_vs_index_km",
        "evidence_refs": [
            _VERDICT_DOC,
            "data/cycle_pattern/ix_trials/ix1_transfer.json",
            "research/cycle_masterplan/PREREGISTRATION.md",
        ],
        "n_summary": (
            "1,815 pre-embargo index person-period rows; OOS "
            f"{led['up']['1m']['n_oos']} up rows / {led['down']['1m']['n_oos']} down rows; "
            "model arm trained on 16,429 member rows; 14 up / 13 down test years (2017 has "
            "zero index down-leg rows); 4-cell family budget"
        ),
        "ci_summary": (
            "up: CI90 [-0.0056,+0.0247] (1m) / [-0.0195,+0.0135] (3m), both straddle 0, no BH; "
            "down: CI90 [+0.0084,+0.0590] (1m) / [+0.0129,+0.0455] (3m), both exclude 0 AND "
            "survive BH — killed by the sign-stability leg (5/13, 7/13 vs frozen bar >=9)"
        ),
        "era_stability": "fragile",
        "pit_class": "pit_pure",
        "allowed_consumers": ["neuralweb_context", "cycle_docs", "research_factory",
                              "measurement_page"],
        "forbidden_consumers": ["board_rank", "oracle_escalation",
                                "sector_central_direction_score", "position_sizing"],
        "falsifiers": [
            "The §17-named index-covariate STACKING trial (member transfer scores + "
            "sync/phase-breadth/dispersion fit at index level) under a NEW registration naming "
            "this null clears its gate.",
            "A post-embargo (>=2024) accrual re-run of the same frozen §17 harness under a NEW "
            "registration clears the same gate (added down-leg years directly test the failed "
            "sign-stability leg).",
        ],
        "monitoring": {"metric": "ix1_post_embargo_retest",
                       "cadence": "next IX wave (or annual review)",
                       "auto_demote_rule": None},
        "created": "2026-07-07",
        "last_reviewed": "2026-07-07",
        "next_review_due": "2027-01-07",
        "notes": ("The frozen 0/4 branch: ONE scoped null, NO factory candidates, page/UI "
                  "unchanged (the markets.html engine-backing wave is moot). era_stability "
                  "'fragile' records the down cells' year-concentration — the failed leg IS the "
                  "finding. The member model's quad/liquidity dummies are revision-optimistic "
                  "(P-D5-1), which flatters the MODEL arm; the null verdict is therefore "
                  "conservative in that direction. Down-cell per-entity decomposition is broad "
                  "(7/8 entities positive at 1m, SPY largest +0.095, ILF sole drag) — a "
                  "single-era, not single-entity, artifact."),
    })
    print(f"[truths] appended {_NULL_TRUTH}")


def main() -> int:
    artifact = json.loads(_ARTIFACT.read_text())
    assert artifact.get("registered_ref") == "PREREGISTRATION.md §17"
    assert artifact.get("trial_family") == "rf.cycle_pattern.ix_v0"
    apply_truths(artifact)
    print("[factory] 0 candidates written (frozen §17 handling: candidates only on PASS)")
    print("[done] §17 frozen outcome handling applied (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
