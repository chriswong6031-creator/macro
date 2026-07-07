"""Apply the FROZEN §16 outcome handling after the TR-1 run (results wave).

Everything this script writes was pre-committed in PREREGISTRATION.md §16 "Outcome handling
(frozen)" — it makes no judgments, it executes them. The run produced 4 PASS / 6 (the 0/6
null branch did NOT fire), so per the frozen handling:

  1. Factory: one candidate per PASSING cell appended to
     data/cycle_pattern/pattern_candidates.jsonl — status 'screened', trial_family 'tr_v0',
     authority display_only (the §15 candidate conventions). Truth-guard cross-check via
     engine.research_factory.adapter_cycle_pattern.truth_guard (flag-only; results printed
     and recorded in the verdict doc).
  2. Truths (engine.cycle_pattern.truths): ONE display-class truth
     `cycle_truth_tr1_next_phase_softmax_skill_v1` scoped to the passing cells, with the
     failing cells named inside the statement (honest scope).
  3. NO null truth (frozen: the single scoped null is registered only on 0/6).
  4. No page/UI change; shipped-surface adoption is a SEPARATE wave.

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
from engine.research_factory.adapter_cycle_pattern import truth_guard  # noqa: E402

_ARTIFACT = _REPO / "data" / "cycle_pattern" / "tr_trials" / "tr1_transition.json"
_CANDIDATES = _REPO / "data" / "cycle_pattern" / "pattern_candidates.jsonl"
_VERDICT_DOC = "research/cycle_masterplan/CPI_TR1_VERDICT.md"

_SKILL_TRUTH = "cycle_truth_tr1_next_phase_softmax_skill_v1"
_TR_FAMILIES = ["us_sector", "country", "cn_sector"]
_TR_HORIZONS = ["1m", "3m"]


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


def _candidate_from_cell(fam: str, h: str, cell: dict, *, artifact_rel: str,
                         created_at: str) -> dict:
    """Project one PASSING cell into a factory candidate row (§15 conventions:
    status 'screened', trial_family 'tr_v0', authority display_only)."""
    cid = f"rf-{created_at[:10].replace('-', '')}-cycle_pattern-tr1-{fam}-{h}"
    return {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "domain": "cycle_pattern",
        "source": "cycle_pattern_scan",
        "candidate_type": "cycle_pattern_rule",
        "candidate_id": cid,
        "created_at": created_at,
        "status": "screened",
        "hypothesis": (f"next_phase_{h} in family {fam} is better predicted by the §16 "
                       f"multinomial softmax over existing PIT-pure hazard-panel columns "
                       f"than by the family-stratified empirical transition matrix"),
        "mechanism": ("model capacity over existing PIT-pure columns: continuous "
                      "within-phase state (pos_osc, osc_slope, momentum, rs, vol, leg age) "
                      "refines the discrete phase→next-phase matrix; no new covariates, "
                      "no macro/quad leak, no calibration layer (raw softmax)"),
        "statement": (f"TR1 cell family={fam} h={h}: OOS multiclass ΔBrier(baseline − model) "
                      f"+{cell['delta_brier']} (CI90 {cell['ci90']}, boot_p {cell['boot_p']}, "
                      f"years+ {cell['years_positive']}/{cell['n_years']}, BH q=0.10 pass; "
                      f"baseline Brier {cell['brier_baseline']} vs model {cell['brier_model']})"),
        "target": f"next_phase_{h}",
        "scope": {"families": [fam], "regions": [], "sample": "pre-2024 embargoed"},
        "trial_family": "tr_v0",
        "artifacts": {"evidence": artifact_rel, "delta_brier": cell["delta_brier"],
                      "ci90": cell["ci90"], "boot_p": cell["boot_p"],
                      "years_positive": cell["years_positive"], "n_years": cell["n_years"],
                      "n_oos": cell["n_oos"], "n_months": cell["n_months"]},
    }


def apply_factory_candidates(artifact: dict) -> list[dict]:
    """Append one screened candidate per PASSING cell (idempotent). Returns truth-guard flags."""
    art_rel = str(_ARTIFACT.relative_to(_REPO))
    created_at = artifact["run_at"]
    passing = [(fam, h, artifact["ledger"][fam][h])
               for fam in _TR_FAMILIES for h in _TR_HORIZONS
               if artifact["ledger"][fam].get(h, {}).get("verdict") == "PASS"]
    cands = [_candidate_from_cell(fam, h, cell, artifact_rel=art_rel, created_at=created_at)
             for fam, h, cell in passing]

    flags = truth_guard(cands)
    for f in flags:
        print(f"[truth-guard] FLAG {f['candidate_id']}: {f['reason']}")
    if not flags:
        print(f"[truth-guard] 0 flags across {len(cands)} candidates")

    existing = {c.get("candidate_id") for c in _load_jsonl(_CANDIDATES)}
    written = 0
    with _CANDIDATES.open("a", encoding="utf-8") as fh:
        for cand in cands:
            if cand["candidate_id"] in existing:
                continue
            fh.write(json.dumps(cand, default=str) + "\n")
            written += 1
    print(f"[factory] wrote {written} screened candidates (trial_family tr_v0) "
          f"({len(cands) - written} already present)")
    return flags


def apply_truths(artifact: dict) -> None:
    led = artifact["ledger"]
    n_pass = artifact["n_cells_pass"]
    assert n_pass == 4, "this script encodes the 4/6 PASS branch (frozen §16 handling)"
    all_ids = {t.get("truth_id") for t in T.load_truths()}
    if _SKILL_TRUTH in all_ids:
        print(f"[truths] {_SKILL_TRUTH}: already present — skipped")
        return
    T.append_truth({
        "truth_id": _SKILL_TRUTH,
        "version": 1,
        "status": "display",
        "owner_program": "cycle-intelligence",
        "statement": (
            "TR-1 (§16, the program's first gate-passing cells): a pure-numpy L2 softmax over "
            "EXISTING PIT-pure hazard-panel columns (current-phase one-hot + the shipped "
            "W2.5-bound feature set; no new covariates, no calibration layer) beats the "
            "family-stratified Laplace(α=1) transition-matrix baseline on OOS multiclass Brier "
            "in 4/6 frozen cells: all three families at 1m (ΔBrier +0.0030 us_sector / +0.0055 "
            "country / +0.0066 cn_sector — 2.7%/4.8%/6.1% of a strong baseline, CI90 excl 0, "
            "years+ 11/13/14 of 14, BH q=0.10) and country at 3m (+0.0027, 12/14). NOT "
            "established at 3m for us_sector (+0.0005, CI straddles, 8/14) or cn_sector "
            "(+0.0014, CI straddles). Mechanism is model capacity, not new information: "
            "continuous within-phase state (pos_osc/slope/momentum/age) anticipates phase-"
            "boundary crossings the discrete matrix cannot see — hence the 1m concentration. "
            "A display-class next-phase probability (masterplan C4), NOT a tradeable edge."
        ),
        "effect_class": "structural",
        "scope": {"families": ["us_sector", "country", "cn_sector"],
                  "regions": ["us", "global", "china"],
                  "sample": "hazard panel price_c4414dcb, embargoed <2024-01-01, "
                            "test years 2010-2023"},
        "target": "next_phase_1m_3m_multiclass_brier_vs_family_transition_matrix",
        "evidence_refs": [
            _VERDICT_DOC,
            "data/cycle_pattern/tr_trials/tr1_transition.json",
            "research/cycle_masterplan/PREREGISTRATION.md",
        ],
        "n_summary": (
            "16,429 pre-embargo person-period rows (16,323 labeled 1m / 16,177 labeled 3m), "
            "14 test years, 6-cell family budget; per-cell OOS n "
            f"{led['us_sector']['1m']['n_oos']}/{led['country']['1m']['n_oos']}/"
            f"{led['cn_sector']['1m']['n_oos']} (1m)"
        ),
        "ci_summary": (
            "passing cells: ΔBrier CI90 [+0.0015,+0.0047] us/1m, [+0.0040,+0.0070] country/1m, "
            "[+0.0051,+0.0082] cn/1m, [+0.0012,+0.0040] country/3m; all BH q=0.10; stability is "
            "YEAR-SIGN based (11-14 of 14 test years positive), not the §14 era split"
        ),
        "era_stability": "stable",
        "pit_class": "pit_pure",
        "allowed_consumers": ["neuralweb_context", "cycle_docs", "research_factory",
                              "measurement_page"],
        "forbidden_consumers": ["board_rank", "oracle_escalation",
                                "sector_central_direction_score", "position_sizing"],
        "falsifiers": [
            "A post-embargo (≥2024) re-run of the same frozen harness fails the same gate on "
            "the passing cells (CI90 no longer excludes 0 or year-sign stability collapses) — "
            "demote to promoted_null scoped to the failing cells.",
        ],
        "monitoring": {"metric": "tr1_post_embargo_retest",
                       "cadence": "next TR wave (or annual review)",
                       "auto_demote_rule": None},
        "created": "2026-07-06",
        "last_reviewed": "2026-07-06",
        "next_review_due": "2026-10-06",
        "notes": ("4 factory candidates at screened (trial_family tr_v0), authority "
                  "display_only, truth_guard 0 flags. The 2 failing 3m cells are recorded in "
                  "§16's results block and the artifact — NOT promoted nulls (the frozen "
                  "handling registers the scoped null only on 0/6). Raw softmax gated (no "
                  "calibration layer in v0, disclosed). Shipped-surface adoption is a "
                  "SEPARATE wave."),
    })
    print(f"[truths] appended {_SKILL_TRUTH}")


def main() -> int:
    artifact = json.loads(_ARTIFACT.read_text())
    assert artifact.get("registered_ref") == "PREREGISTRATION.md §16"
    apply_factory_candidates(artifact)
    apply_truths(artifact)
    print("[done] §16 frozen outcome handling applied (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
