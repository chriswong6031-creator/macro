"""Apply the FROZEN §15 outcome handling after the lattice batch-2 run (results wave).

Everything this script writes was pre-committed in PREREGISTRATION.md §15 "Outcome handling
(frozen)" — it makes no judgments, it executes them:

  1. Factory: batch-1 (`lattice_v0`) candidates whose cell FAILED the within-family gate →
     `screened → numeric_rejected` transitions appended to data/research_factory/transitions.jsonl
     (validated via engine.research_factory.state.transition; kill evidence RF-10 = batch2.json).
     Candidates whose cell PASSED keep `screened` — their batch-2 evidence lives in the artifact's
     `batch1_candidate_resolutions` block (recorded, not mutated: pattern_candidates.jsonl is
     append-only).
  2. Truths (engine.cycle_pattern.truths):
     - LT2-020 FAILED → `cycle_truth_cn_downturn_broken_trend_tail_candidate_v1`:
       candidate → retired (its registered auto_demote_rule), and the scoped null truth
       `cycle_truth_cn_downturn_broken_trend_tail_null_v1` is appended.
     - `cycle_truth_lattice2_within_family_structure_v1` (display/structural) appended for the
       27-cell family-honest structure.
     - CPI-019 (`cycle_truth_lattice1_confirmatory_and_baseline_confound_v1`): monitoring metric
       satisfied → version-bump note append, status stays display.

Idempotent: every write is guarded by an existence check, so re-runs are no-ops.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.research_factory import state as rf_state  # noqa: E402
from engine.cycle_pattern import truths as T  # noqa: E402

_BATCH2 = _REPO / "data" / "cycle_pattern" / "lattice" / "batch2.json"
_CANDIDATES = _REPO / "data" / "cycle_pattern" / "pattern_candidates.jsonl"
_TRANSITIONS = _REPO / "data" / "research_factory" / "transitions.jsonl"
_VERDICT_DOC = "research/cycle_masterplan/CPI_LATTICE2_VERDICT.md"

_REASON_CODE = "lattice_batch2_within_family_fail"
_ACTOR = "fable"

_CAND_TRUTH = "cycle_truth_cn_downturn_broken_trend_tail_candidate_v1"
_NULL_TRUTH = "cycle_truth_cn_downturn_broken_trend_tail_null_v1"
_STRUCT_TRUTH = "cycle_truth_lattice2_within_family_structure_v1"
_CPI019 = "cycle_truth_lattice1_confirmatory_and_baseline_confound_v1"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return rows


def apply_factory_resolutions(artifact: dict, *, now: str) -> int:
    """Append screened→numeric_rejected transitions for failed batch-1 candidates (idempotent)."""
    resolutions = artifact.get("batch1_candidate_resolutions", [])
    rejects = {r["cell_key"]: r for r in resolutions if r["resolution"] == "numeric_rejected"}
    if not rejects:
        print("[factory] no numeric_rejected resolutions in artifact")
        return 0

    cands = [c for c in _load_jsonl(_CANDIDATES) if c.get("trial_family") == "lattice_v0"]
    by_key: dict[str, dict] = {}
    for c in cands:
        cid = c.get("candidate_id", "")
        # batch-1 id = rf-YYYYMMDD-cycle_pattern-<cell_key>; recover the cell key.
        parts = cid.split("-cycle_pattern-", 1)
        if len(parts) == 2:
            by_key[parts[1]] = c

    existing = {
        t.get("candidate_id")
        for t in _load_jsonl(_TRANSITIONS)
        if t.get("reason_code") == _REASON_CODE
    }

    # n_at_kill = the batch-2 cell's n_months (honest kill sample size, RF-10).
    def _key_of(c: dict) -> str:
        tp = ""
        if "trend_pass" in c and c["trend_pass"] is not None:
            tp = f"-trend_pass={float(c['trend_pass']):.0f}"
        return f"{c['lattice']}-{c['phase_v2']}-{c['family']}{tp}-{c['target']}"

    n_months_by_key = {_key_of(c): c.get("n_months") for c in artifact.get("cells", [])}

    art_rel = str(_BATCH2.relative_to(_REPO))
    written = 0
    with _TRANSITIONS.open("a", encoding="utf-8") as fh:
        for key, res in sorted(rejects.items()):
            cand = by_key.get(key)
            if cand is None:
                print(f"[factory] WARNING: no lattice_v0 candidate found for cell {key} — skipped")
                continue
            cid = cand["candidate_id"]
            if cid in existing:
                continue
            row = {
                "schema": "research_factory.transition.v1",
                "authority": "display_only",
                "candidate_id": cid,
                "from": "screened",
                "to": "numeric_rejected",
                "reason_code": _REASON_CODE,
                "reason_text": (
                    "PREREG §15 frozen outcome handling: the cell fails the within-family "
                    f"promotion gate in lattice batch 2 (batch2 gap_wf={res['batch2_gap_wf']}, "
                    f"batch1 xfam gap={res['batch1_gap']} — the §14 baseline confound)."
                ),
                "actor": _ACTOR,
                "actor_ref": "cycle-intelligence/lattice-batch2",
                "as_of": now,
                "artifact_refs": [art_rel],
                "kill_evidence": {
                    "n_at_kill": int(n_months_by_key.get(key) or 0),
                    "kill_class": "numeric_retest_fail",
                    "mde_at_n": None,
                    "gate_ref": art_rel,
                    "regime_split": None,
                    "source": "lattice_batch2_within_family_retest",
                },
            }
            rf_state.transition("screened", "numeric_rejected", _ACTOR, row, candidate=cand)
            fh.write(json.dumps(row) + "\n")
            written += 1
    print(f"[factory] wrote {written} screened→numeric_rejected transitions "
          f"({len(rejects)} resolutions, {len(rejects) - written} already present/skipped)")
    return written


def apply_truths(artifact: dict) -> None:
    nr = artifact["named_retest"]
    cell = nr["cell"]
    assert nr["found"] and not nr["passed"], "this script encodes the FAIL branch (frozen §15)"
    active = {t["truth_id"]: t for t in T.active_truths()}
    all_ids = {t.get("truth_id") for t in _load_jsonl(T.TRUTHS_PATH)}

    # (a) CPI-020: candidate → retired (auto_demote_rule).
    if _CAND_TRUTH in active and active[_CAND_TRUTH]["status"] == "candidate":
        T.transition_truth(
            _CAND_TRUTH, "retired", actor="cycle-intelligence/lattice-batch2",
            reason=(
                "§15 LT2-020 named re-test FAILED the frozen gate: within-family gap "
                f"{cell['gap']} CI95 {cell['ci95']} boot_p={cell['boot_p']} era=({cell['era_pre_sign']},"
                f"{cell['era_post_sign']}) — CI excludes 0 and era-stable but does not survive "
                "BH-FDR q=0.10 across the declared 135-cell family. Auto-demote per registered rule."
            ),
        )
        print(f"[truths] {_CAND_TRUTH}: candidate → retired")
    else:
        print(f"[truths] {_CAND_TRUTH}: already resolved — skipped")

    # (b) The scoped null truth recording the kill.
    if _NULL_TRUTH not in all_ids:
        T.append_truth({
            "truth_id": _NULL_TRUTH,
            "version": 1,
            "status": "promoted_null",
            "owner_program": "cycle-intelligence",
            "statement": (
                "The CN Downturn × broken-trend deep vol-adjusted 63d tail claim (batch-1 lead, "
                "ex-CPI-020) does NOT survive the §15 within-family re-test: gap vs CN's own "
                "Downturn baseline −0.0350 (CI95 [−0.0688, −0.0021], boot p=0.04, n=145 months, "
                "era-stable) — directionally persistent at ~60% smaller magnitude than the "
                "cross-family estimate (−0.0597; §14 baseline confound), and killed by BH-FDR "
                "q=0.10 across the declared 135-cell family. The risk-relevant survivor is the "
                "SAME cell on turn_event_3m: broken-trend CN downturns show a turn DEFICIT "
                "(−0.086, BH-pass) — longer downturns, unproven deeper tails."
            ),
            "effect_class": "null",
            "scope": {"families": ["cn_sector"], "regions": ["china"],
                      "sample": "hazard panel price_c4414dcb, embargoed <2024-01-01"},
            "target": "rdd_63d",
            "evidence_refs": [
                _VERDICT_DOC,
                "data/cycle_pattern/lattice/batch2.json",
                "research/cycle_masterplan/PREREGISTRATION.md",
            ],
            "n_summary": "145 months in-cell (within-family pool: cn_sector × Downturn)",
            "ci_summary": "gap_wf −0.0350 CI95 [−0.0688, −0.0021]; boot p=0.04; BH q=0.10 FAIL",
            "era_stability": "stable",
            "pit_class": "pit_pure",
            "allowed_consumers": ["neuralweb_context", "cycle_docs", "research_factory",
                                  "measurement_page"],
            "forbidden_consumers": ["board_rank", "oracle_escalation",
                                    "sector_central_direction_score", "position_sizing"],
            "falsifiers": [
                "A NEW preregistered trial naming this null clears a same-shape within-family "
                "gate on fresh (post-embargo or accrued) data, or on a declared family small "
                "enough that the observed effect size is powered."
            ],
            "monitoring": {"metric": None, "cadence": "annual review",
                           "auto_demote_rule": None},
            "created": "2026-07-06",
            "last_reviewed": "2026-07-06",
            "next_review_due": "2027-01-06",
            "notes": "The kill recorded per frozen §15 outcome handling (LT2-020 FAIL branch).",
        })
        print(f"[truths] appended {_NULL_TRUTH}")
    else:
        print(f"[truths] {_NULL_TRUTH}: already present — skipped")

    # (c) The batch-2 structural display truth.
    if _STRUCT_TRUTH not in all_ids:
        T.append_truth({
            "truth_id": _STRUCT_TRUTH,
            "version": 1,
            "status": "display",
            "owner_program": "cycle-intelligence",
            "statement": (
                "Lattice batch 2 (same 135 PIT-pure cells as batch 1, WITHIN-FAMILY baselines): "
                "27/135 promote under the frozen §15 gate. Phase-conditional turn-arrival and "
                "persistence structure is real WITHIN every family (not a family-composition "
                "artifact): turn arrival is phase-graded (Trough/Recovery/Downturn elevated, "
                "Expansion/Peak deferred), Recovery is fragile in all three families "
                "(persist −0.17 us / −0.17 country / −0.25 cn), Peak persists. Two vol-adjusted "
                "risk cells: Peak carries SHALLOWER rdd_63d tails within country (+0.049) and CN "
                "(+0.071) — KG-2/CPI-002 direction in stricter form. Trend integrity conditions "
                "turn arrival within family-phase: broken-trend CN downturns grind (turn deficit "
                "−0.086) while intact-trend ones resolve (+0.160). Confirmatory/structural — "
                "phase labels share mechanics with turn labels; these are NOT tradeable edges."
            ),
            "effect_class": "structural",
            "scope": {"families": ["us_sector", "country", "cn_sector"],
                      "regions": ["us", "global", "china"],
                      "sample": "hazard panel price_c4414dcb + W4.4 joins, embargoed <2024-01-01"},
            "target": "rdd_63d, turn_event_3m, phase_persist_3m vs within-family baselines",
            "evidence_refs": [
                _VERDICT_DOC,
                "data/cycle_pattern/lattice/batch2.json",
                "research/cycle_masterplan/PREREGISTRATION.md",
            ],
            "n_summary": "135 cells, 27 gate-passing, n_months 98–287 per promoted cell",
            "ci_summary": "all 27: within-family gap CI95 excl 0 + era sign agreement + BH q=0.10",
            "era_stability": "stable",
            "pit_class": "pit_pure",
            "allowed_consumers": ["neuralweb_context", "cycle_docs", "research_factory",
                                  "measurement_page"],
            "forbidden_consumers": ["board_rank", "oracle_escalation",
                                    "sector_central_direction_score", "position_sizing"],
            "falsifiers": [
                "A future batch on accrued/post-embargo data shows the within-family structure "
                "unstable (era flip or CI collapse) — demote to promoted_null scoped to the "
                "failing cells."
            ],
            "monitoring": {"metric": "next_lattice_batch_on_accrued_data",
                           "cadence": "next lattice batch",
                           "auto_demote_rule": None},
            "created": "2026-07-06",
            "last_reviewed": "2026-07-06",
            "next_review_due": "2026-10-06",
            "notes": ("27 factory candidates at screened (trial_family lattice_v1), authority "
                      "display_only. 33/48 batch-1 candidates numeric_rejected; 15 keep "
                      "screened with batch-2 evidence (artifact resolutions block)."),
        })
        print(f"[truths] appended {_STRUCT_TRUTH}")
    else:
        print(f"[truths] {_STRUCT_TRUTH}: already present — skipped")

    # (d) CPI-019: monitoring satisfied — note append (status stays display).
    cpi019 = active.get(_CPI019)
    if cpi019 and "batch2_within_family_retest satisfied" not in (cpi019.get("notes") or ""):
        T.transition_truth(
            _CPI019, "display", actor="cycle-intelligence/lattice-batch2",
            reason=(
                "batch2_within_family_retest satisfied: the confirmatory structure reproduces "
                "under within-family baselines (27/135, era-stable) — NOT a family-composition "
                "artifact. Falsifier answered; status unchanged."
            ),
        )
        print(f"[truths] {_CPI019}: monitoring note appended (display → display)")
    else:
        print(f"[truths] {_CPI019}: note already present — skipped")


def main() -> int:
    artifact = json.loads(_BATCH2.read_text())
    assert artifact.get("registered_ref") == "PREREGISTRATION.md §15"
    now = datetime.now(timezone.utc).isoformat()
    apply_factory_resolutions(artifact, now=now)
    apply_truths(artifact)
    print("[done] §15 frozen outcome handling applied (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
