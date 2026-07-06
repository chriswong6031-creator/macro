"""tests/test_operator_grading.py — DQ-2 operator-action grading harness tests.

All fixtures are synthetic (tmp_path only).  No real data files are read.

Test coverage:
  - absent-ledger safety (no file → accruing with zero actions)
  - matching correctness (action matches correct claims by surface + window)
  - unmatched accounting (wrong surface → counted in n_unmatched, not dropped)
  - floor gating: 24 graded actions per contrast → accruing; 25 → computed
  - BH and bootstrap are IMPORTED from engine.btc_override_ledger (not re-implemented)
  - artifact schema stability (required keys present, correct types)
  - no 'validated' string anywhere in output
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "+00:00")


def _date_str(dt: datetime) -> str:
    return dt.date().isoformat()


def _make_claim(
    claim_id: str,
    surface: str,
    direction: int = 1,
    ts: datetime | None = None,
    check_by: datetime | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    ts = ts or now - timedelta(days=30)
    check_by = check_by or now + timedelta(days=33)
    return {
        "claim_id": claim_id,
        "surface": surface,
        "direction": direction,
        "timestamp": _iso(ts),
        "check_by": _date_str(check_by),
        "claim_family": "test_family",
        "desk": surface,
    }


def _make_grade(
    claim_id: str,
    hit: bool,
    excess: float = 0.05,
    horizon_d: int = 21,
) -> dict:
    return {
        "claim_id": claim_id,
        "horizon_d": horizon_d,
        "graded_at": _iso(datetime.now(timezone.utc)),
        "subject_ret": 0.06 if hit else -0.04,
        "bench_ret": 0.01,
        "excess": excess if hit else -excess,
        "hit": hit,
        "embargo_applied": False,
    }


def _make_action(
    surface: str,
    action: str = "acted",
    ts: datetime | None = None,
    direction_note: str = "",
) -> dict:
    ts = ts or datetime.now(timezone.utc)
    return {
        "ts": _iso(ts),
        "actor": "operator",
        "surface": surface,
        "action": action,
        "direction_note": direction_note,
        "latency_s": None,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _setup_repo(
    tmp_path: Path,
    claims: list[dict] | None = None,
    grades: list[dict] | None = None,
    actions: list[dict] | None = None,
    write_ledger: bool = True,
) -> Path:
    """Set up a minimal fake repo under tmp_path.  Returns data_root."""
    data_root = tmp_path / "repo"
    data_root.mkdir()

    # claims
    _write_jsonl(data_root / "data" / "qledger" / "claims.jsonl", claims or [])
    # grades
    _write_jsonl(data_root / "data" / "qledger" / "grades.jsonl", grades or [])
    # trial ledger (empty; auto-created by TrialLedger)
    (data_root / "data").mkdir(exist_ok=True)

    # operator ledger
    if write_ledger and actions is not None:
        _write_jsonl(data_root / "data" / "operator" / "action_ledger.jsonl", actions)

    return data_root


# ---------------------------------------------------------------------------
# Test: absent ledger file is safe
# ---------------------------------------------------------------------------
def test_absent_ledger_is_safe(tmp_path: Path) -> None:
    data_root = _setup_repo(tmp_path, write_ledger=False)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    assert result["n_actions_total"] == 0
    assert result["n_unmatched_actions"] == 0
    assert result["state"] == "accruing"
    assert result["ledger_present"] is False

    # All contrasts must be accruing
    for name, contrast in result["contrasts"].items():
        assert contrast["state"] == "accruing", f"{name} should be accruing"
        assert contrast["n_graded"] == 0


# ---------------------------------------------------------------------------
# Test: matching correctness — action matches claim by surface + window
# ---------------------------------------------------------------------------
def test_matching_correct_surface_and_window(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    claim = _make_claim("c1", surface="alert_alpha", ts=now - timedelta(days=10))
    grade_row = _make_grade("c1", hit=True)
    action = _make_action("alert_alpha", "acted", ts=now)

    data_root = _setup_repo(tmp_path, claims=[claim], grades=[grade_row], actions=[action])

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    assert result["n_actions_total"] == 1
    assert result["n_matched_actions"] == 1
    assert result["n_unmatched_actions"] == 0


# ---------------------------------------------------------------------------
# Test: unmatched accounting — wrong surface counted, not silently dropped
# ---------------------------------------------------------------------------
def test_unmatched_action_counted(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    claim = _make_claim("c1", surface="alert_alpha", ts=now - timedelta(days=10))
    grade_row = _make_grade("c1", hit=True)
    # action has a DIFFERENT surface — should be unmatched
    action = _make_action("totally_different_surface", "acted", ts=now)

    data_root = _setup_repo(tmp_path, claims=[claim], grades=[grade_row], actions=[action])

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    assert result["n_actions_total"] == 1
    assert result["n_unmatched_actions"] == 1
    assert result["n_matched_actions"] == 0


# ---------------------------------------------------------------------------
# Test: floor gating — 24 graded actions -> accruing; 25 -> computed
# ---------------------------------------------------------------------------
def _make_n_acted_then_graded(n: int, hit: bool = True) -> tuple[list, list, list]:
    """Build n acted actions each matched to a distinct claim with a grade."""
    now = datetime.now(timezone.utc)
    claims = []
    grades = []
    actions = []
    for i in range(n):
        cid = f"claim_{i:04d}"
        surface = f"alert_{i:04d}"
        claims.append(_make_claim(cid, surface=surface, ts=now - timedelta(days=10)))
        grades.append(_make_grade(cid, hit=hit))
        actions.append(_make_action(surface, "acted", ts=now))
    return claims, grades, actions


def test_floor_24_is_accruing(tmp_path: Path) -> None:
    claims, grades, actions = _make_n_acted_then_graded(24, hit=True)
    data_root = _setup_repo(tmp_path, claims=claims, grades=grades, actions=actions)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    # C2 and C3 each need n>=25 for acted/dismissed — with all 'acted', dismissed=0
    # C1 needs overrode actions; with all 'acted' there are 0 overrode
    # So all 3 contrasts must be accruing
    for name, contrast in result["contrasts"].items():
        assert contrast["state"] == "accruing", (
            f"Expected {name} accruing with 24 actions, got {contrast['state']}"
        )


def test_floor_25_acted_with_25_dismissed_triggers_computed(tmp_path: Path) -> None:
    """C2 and C3 compute when both acted and dismissed each have >=25 graded."""
    now = datetime.now(timezone.utc)
    claims = []
    grades = []
    actions = []

    # 25 acted + 25 dismissed, each matched to a distinct claim
    for i in range(50):
        cid = f"claim_{i:04d}"
        surface = f"alert_{i:04d}"
        hit = (i % 2 == 0)  # alternating hits
        action_type = "acted" if i < 25 else "dismissed"
        claims.append(_make_claim(cid, surface=surface, ts=now - timedelta(days=10)))
        grades.append(_make_grade(cid, hit=hit))
        actions.append(_make_action(surface, action_type, ts=now))

    data_root = _setup_repo(tmp_path, claims=claims, grades=grades, actions=actions)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    # C2 and C3 should be computed (25 acted + 25 dismissed)
    c2 = result["contrasts"]["C2_dismissed_then_worked"]
    c3 = result["contrasts"]["C3_acted_then_failed"]
    assert c2["state"] == "computed", f"C2 should be computed, got {c2['state']}"
    assert c3["state"] == "computed", f"C3 should be computed, got {c3['state']}"

    # Rates should be floats in [0, 1]
    assert 0.0 <= c2["dismissed_hit_rate"] <= 1.0
    assert 0.0 <= c3["acted_fail_rate"] <= 1.0


# ---------------------------------------------------------------------------
# Test: BH and bootstrap are IMPORTED (not re-implemented)
# ---------------------------------------------------------------------------
def test_bh_and_bootstrap_imported_from_btc_override_ledger() -> None:
    """Assert _bh and _bootstrap_null are imported from engine.btc_override_ledger."""
    import engine.btc_override_ledger as btc_mod
    import engine.operator_grading as op_mod

    # Verify they are the SAME objects (imported, not re-implemented)
    assert op_mod._bh is btc_mod._bh, (
        "_bh in operator_grading must BE the same object as btc_override_ledger._bh"
    )
    assert op_mod._bootstrap_null is btc_mod._bootstrap_null, (
        "_bootstrap_null in operator_grading must BE the same object as "
        "btc_override_ledger._bootstrap_null"
    )

    # Sanity-check that _bh is callable with the expected signature
    result = btc_mod._bh({"a": 0.05, "b": 0.03}, q=0.10, m=4)
    assert "a" in result and "b" in result
    assert "significant_at_q" in result["a"]


# ---------------------------------------------------------------------------
# Test: artifact schema stability
# ---------------------------------------------------------------------------
REQUIRED_TOP_LEVEL_KEYS = {
    "schema", "harness_version", "generated_at", "state",
    "fdr_family", "fdr_budget", "fdr_q", "wilson_floor",
    "ledger_present", "n_actions_total", "n_unmatched_actions",
    "n_matched_actions", "n_claims_loaded", "n_grades_loaded",
    "contrasts", "authority",
}
REQUIRED_CONTRAST_KEYS_ACCRUING = {"state", "n_actions", "n_matched", "n_graded"}


def test_artifact_schema_stability(tmp_path: Path) -> None:
    data_root = _setup_repo(tmp_path, write_ledger=False)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    missing = REQUIRED_TOP_LEVEL_KEYS - set(result.keys())
    assert not missing, f"Artifact missing required keys: {missing}"

    assert isinstance(result["schema"], str)
    assert result["schema"].startswith("operator_grading.")
    assert isinstance(result["contrasts"], dict)
    assert len(result["contrasts"]) == 3

    for name, contrast in result["contrasts"].items():
        assert "state" in contrast, f"contrast {name} missing 'state'"
        assert contrast["state"] in ("accruing", "computed"), (
            f"contrast {name} state must be accruing or computed"
        )


# ---------------------------------------------------------------------------
# Test: no 'validated' string in authored content fields
# ---------------------------------------------------------------------------
def test_no_validated_string_in_output(tmp_path: Path) -> None:
    """The word 'validated' must not appear in any authored field of the artifact.

    We exclude ledger_path (which may reflect a tmp_path name that contains
    'validated' due to the pytest test function name), and check the fields
    whose content is authored by this module: schema, state, authority, contrasts,
    fdr_family, harness_version, etc.
    """
    data_root = _setup_repo(tmp_path, write_ledger=False)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    # Check all authored fields (exclude ledger_path which reflects filesystem path)
    authored = {k: v for k, v in result.items() if k != "ledger_path"}
    authored_str = json.dumps(authored, default=str)

    assert "validated" not in authored_str.lower(), (
        "The word 'validated' must never appear in operator_grading authored output. "
        f"Found in: {authored_str[:400]}"
    )


# ---------------------------------------------------------------------------
# Test: multiple actions, mixed matched/unmatched
# ---------------------------------------------------------------------------
def test_mixed_matched_and_unmatched(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    claim = _make_claim("c1", surface="alert_x", ts=now - timedelta(days=5))
    grade_row = _make_grade("c1", hit=True)

    # 2 matching actions (correct surface) + 1 unmatched (wrong surface)
    actions = [
        _make_action("alert_x", "acted", ts=now),
        _make_action("alert_x", "dismissed", ts=now),
        _make_action("alert_z_unrelated", "acted", ts=now),
    ]

    data_root = _setup_repo(tmp_path, claims=[claim], grades=[grade_row], actions=actions)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    assert result["n_actions_total"] == 3
    assert result["n_unmatched_actions"] == 1
    assert result["n_matched_actions"] == 2


# ---------------------------------------------------------------------------
# Test: action outside claim window is not matched
# ---------------------------------------------------------------------------
def test_action_before_claim_window_not_matched(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    # Claim starts TOMORROW — action today is before the window
    claim = _make_claim("c1", surface="alert_y", ts=now + timedelta(days=1))
    grade_row = _make_grade("c1", hit=True)
    action = _make_action("alert_y", "acted", ts=now)

    data_root = _setup_repo(tmp_path, claims=[claim], grades=[grade_row], actions=[action])

    from engine.operator_grading import grade as grade_fn
    result = grade_fn(data_root=data_root)

    assert result["n_unmatched_actions"] == 1
    assert result["n_matched_actions"] == 0


# ---------------------------------------------------------------------------
# Test: FDR family and budget constants match spec
# ---------------------------------------------------------------------------
def test_fdr_constants() -> None:
    from engine.operator_grading import FDR_FAMILY, FDR_BUDGET, WILSON_FLOOR, FDR_Q

    assert FDR_FAMILY == "operator"
    assert FDR_BUDGET == 3
    assert WILSON_FLOOR == 25
    assert FDR_Q == 0.10


# ---------------------------------------------------------------------------
# Test: schema constant
# ---------------------------------------------------------------------------
def test_schema_constant() -> None:
    from engine.operator_grading import SCHEMA
    assert SCHEMA == "operator_grading.v1"
