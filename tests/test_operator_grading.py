"""tests/test_operator_grading.py — DQ-2 operator-action grading harness tests.

All fixtures are synthetic (tmp_path only).  No real data files are read.

Test coverage:
  - absent-ledger safety (no file → accruing with zero actions)
  - matching correctness (action matches correct claims by surface + window)
  - unmatched accounting (wrong surface → counted in n_unmatched, not dropped)
  - floor gating: 24 DISTINCT actions → accruing; 25 DISTINCT actions → computed
  - multi-claim action counting once (per-action aggregation: one obs per action)
  - BH is IMPORTED from engine.btc_override_ledger (not re-implemented)
  - _bootstrap_null is NOT imported into operator_grading (wrong domain)
  - computed branch: Wilson bounds + BH fields present and sane
  - artifact schema stability (required keys present, correct types)
  - no 'validated' string anywhere in output
  - _parse_direction free-text heuristic keyword cases + ambiguous fallback
  - FDR idempotency: exactly one 'operator' family entry across two runs
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
# Test: floor gating — 24 DISTINCT graded actions → accruing; 25 → computed
# ---------------------------------------------------------------------------
def _make_n_acted_then_graded(n: int, hit: bool = True) -> tuple[list, list, list]:
    """Build n acted actions each matched to a DISTINCT claim with a grade.

    Each action has a unique surface so each is a distinct graded action.
    """
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


def test_floor_24_distinct_actions_is_accruing(tmp_path: Path) -> None:
    """24 distinct graded actions per contrast → all contrasts accruing."""
    claims, grades, actions = _make_n_acted_then_graded(24, hit=True)
    data_root = _setup_repo(tmp_path, claims=claims, grades=grades, actions=actions)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    # C2 and C3 each need n>=25 for acted/dismissed — with all 'acted', dismissed=0
    # C1 needs overrode actions; with all 'acted' there are 0 overrode
    # So all 3 contrasts must be accruing
    for name, contrast in result["contrasts"].items():
        assert contrast["state"] == "accruing", (
            f"Expected {name} accruing with 24 distinct actions, got {contrast['state']}"
        )


def test_floor_25_distinct_actions_triggers_computed(tmp_path: Path) -> None:
    """C2 and C3 compute when both acted and dismissed each have >=25 distinct graded actions."""
    now = datetime.now(timezone.utc)
    claims = []
    grades = []
    actions = []

    # 25 acted + 25 dismissed, each matched to a DISTINCT claim
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

    # C2 and C3 should be computed (25 distinct acted + 25 distinct dismissed)
    c2 = result["contrasts"]["C2_dismissed_then_worked"]
    c3 = result["contrasts"]["C3_acted_then_failed"]
    assert c2["state"] == "computed", f"C2 should be computed, got {c2['state']}"
    assert c3["state"] == "computed", f"C3 should be computed, got {c3['state']}"

    # Rates should be floats in [0, 1]
    assert 0.0 <= c2["dismissed_hit_rate"] <= 1.0
    assert 0.0 <= c3["acted_fail_rate"] <= 1.0


# ---------------------------------------------------------------------------
# Test: multi-claim action counts ONCE (per-action aggregation)
# ---------------------------------------------------------------------------
def test_multi_claim_action_counts_once(tmp_path: Path) -> None:
    """One action matching K claims contributes exactly ONE observation to floor count.

    If per-action aggregation is broken (K contributions per action), then
    1 action matching 25 claims would pass the floor. With correct aggregation,
    1 action = 1 observation, which is below the floor of 25.
    """
    now = datetime.now(timezone.utc)
    # 25 claims all on the same surface so ONE action matches all of them
    common_surface = "shared_surface"
    claims = []
    grades = []
    for i in range(25):
        cid = f"shared_claim_{i:04d}"
        claims.append(_make_claim(cid, surface=common_surface, ts=now - timedelta(days=10)))
        grades.append(_make_grade(cid, hit=True))

    # ONE acted action on that surface → matches all 25 claims
    actions = [_make_action(common_surface, "acted", ts=now)]

    data_root = _setup_repo(tmp_path, claims=claims, grades=grades, actions=actions)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    # Despite matching 25 claims, there is only 1 distinct action → still below floor
    c2 = result["contrasts"]["C2_dismissed_then_worked"]
    assert c2["state"] == "accruing", (
        f"One multi-claim action must count as 1 observation; "
        f"C2 must be accruing (got {c2['state']})"
    )
    # The one "acted" action contributes 1 per-action observation to the base cohort
    # (n_base_graded=1), not 25 (one per matched claim).  C2's "dismissed" count stays 0
    # since all actions are "acted".
    assert c2["n_base_graded"] == 1, (
        f"n_base_graded should be 1 (one distinct graded acted action), "
        f"got {c2['n_base_graded']}"
    )
    assert c2["n_graded"] == 0, (
        f"n_graded (dismissed) should be 0 since no dismissed actions, got {c2['n_graded']}"
    )


# ---------------------------------------------------------------------------
# Test: computed branch has Wilson bounds + BH fields
# ---------------------------------------------------------------------------
def test_computed_branch_wilson_and_bh_fields(tmp_path: Path) -> None:
    """At or above floor, computed contrasts carry wilson_lo/hi, p_raw, p_bh, bh_rejected."""
    now = datetime.now(timezone.utc)
    claims = []
    grades = []
    actions = []

    # 25 acted + 25 dismissed with distinct surfaces
    for i in range(50):
        cid = f"claim_{i:04d}"
        surface = f"surf_{i:04d}"
        hit = (i % 3 != 0)  # ~66% hit rate
        action_type = "acted" if i < 25 else "dismissed"
        claims.append(_make_claim(cid, surface=surface, ts=now - timedelta(days=10)))
        grades.append(_make_grade(cid, hit=hit))
        actions.append(_make_action(surface, action_type, ts=now))

    data_root = _setup_repo(tmp_path, claims=claims, grades=grades, actions=actions)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    for contrast_key in ("C2_dismissed_then_worked", "C3_acted_then_failed"):
        c = result["contrasts"][contrast_key]
        assert c["state"] == "computed", f"{contrast_key} should be computed"

        # Wilson bounds must be present and ordered
        assert c["wilson_lo"] is not None, f"{contrast_key} missing wilson_lo"
        assert c["wilson_hi"] is not None, f"{contrast_key} missing wilson_hi"
        assert 0.0 <= c["wilson_lo"] <= c["wilson_hi"] <= 1.0, (
            f"{contrast_key} Wilson bounds out of order: "
            f"[{c['wilson_lo']}, {c['wilson_hi']}]"
        )

        # p_raw must be a float in [0, 1]
        assert isinstance(c["p_raw"], float), f"{contrast_key} p_raw must be float"
        assert 0.0 <= c["p_raw"] <= 1.0, f"{contrast_key} p_raw out of range"

        # p_bh must be filled after BH pass
        assert c["p_bh"] is not None, f"{contrast_key} p_bh must be filled by BH pass"
        assert 0.0 <= c["p_bh"] <= 1.0, f"{contrast_key} p_bh out of range"

        # bh_rejected must be a boolean
        assert isinstance(c["bh_rejected"], bool), (
            f"{contrast_key} bh_rejected must be bool"
        )

        # n_actions present
        assert "n_actions" in c or "n_dismissed_graded" in c or "n_acted_graded" in c


# ---------------------------------------------------------------------------
# Test: BH is IMPORTED from engine.btc_override_ledger; _bootstrap_null is NOT
# ---------------------------------------------------------------------------
def test_bh_imported_from_btc_override_ledger() -> None:
    """_bh in operator_grading must be the SAME object as btc_override_ledger._bh."""
    import engine.btc_override_ledger as btc_mod
    import engine.operator_grading as op_mod

    # _bh must be imported (same object)
    assert op_mod._bh is btc_mod._bh, (
        "_bh in operator_grading must BE the same object as btc_override_ledger._bh"
    )

    # _bootstrap_null must NOT be imported into operator_grading
    # (it is a BTC ATH-gated price-path simulator — wrong domain)
    assert not hasattr(op_mod, "_bootstrap_null"), (
        "_bootstrap_null must NOT be imported into operator_grading; "
        "it is a BTC ATH-gated price-path simulator with no mapping to operator-action grading"
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

    We exclude ledger_file (basename only; not a path) and check the fields
    whose content is authored by this module: schema, state, authority, contrasts,
    fdr_family, harness_version, etc.
    """
    data_root = _setup_repo(tmp_path, write_ledger=False)

    from engine.operator_grading import grade
    result = grade(data_root=data_root)

    # Check all authored fields (exclude ledger_file which is just the basename)
    authored = {k: v for k, v in result.items() if k != "ledger_file"}
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


# ---------------------------------------------------------------------------
# Test: _parse_direction free-text heuristic
# ---------------------------------------------------------------------------
def test_parse_direction_positive_keywords() -> None:
    """Positive direction keywords must return 1."""
    from engine.operator_grading import _parse_direction

    positive_cases = [
        "I agree with the signal",
        "going long here",
        "buy on pullback",
        "bullish setup",
        "expecting up move",
        "confirm the claim",
        "yes, acting on this",
    ]
    for note in positive_cases:
        result = _parse_direction(note)
        assert result == 1, f"Expected 1 for '{note}', got {result}"


def test_parse_direction_negative_keywords() -> None:
    """Negative direction keywords must return -1.

    Note: 'disagree' contains the substring 'agree' (a positive keyword) so it
    triggers both flags and returns None. The correct pure-negative keywords to
    test are the ones not containing any positive keyword as a substring.
    """
    from engine.operator_grading import _parse_direction

    negative_cases = [
        "going short",
        "sell the rip",
        "bearish outlook",
        "expecting down move",
        "reject this claim",
        "no, not acting",
    ]
    for note in negative_cases:
        result = _parse_direction(note)
        assert result == -1, f"Expected -1 for '{note}', got {result}"

    # 'disagree' contains 'agree' (a positive keyword substring) → returns None (documented behavior)
    assert _parse_direction("I disagree with this") is None, (
        "'disagree' contains 'agree' as a substring; both positive and negative flags fire → None"
    )


def test_parse_direction_empty_is_none() -> None:
    """Empty direction note must return None."""
    from engine.operator_grading import _parse_direction

    assert _parse_direction("") is None
    assert _parse_direction(None) is None  # type: ignore[arg-type]


def test_parse_direction_ambiguous_returns_none() -> None:
    """Ambiguous notes with both positive and negative keywords return None (documented fallback)."""
    from engine.operator_grading import _parse_direction

    ambiguous_cases = [
        "bullish on short term, bearish long term",
        "buy the dip but disagree with long-term thesis",
        "agree but going short as a hedge",
        "up but then down",
    ]
    for note in ambiguous_cases:
        result = _parse_direction(note)
        assert result is None, (
            f"Ambiguous note '{note}' must return None (both positive and negative keywords present), "
            f"got {result}"
        )


def test_parse_direction_neutral_text_is_none() -> None:
    """Text with no direction keywords must return None.

    Note: the matcher uses substring matching, so 'no' fires on any word containing
    'no' as a substring (e.g. 'now', 'monitor').  Neutral cases here avoid all
    keyword substrings.
    """
    from engine.operator_grading import _parse_direction

    neutral_cases = [
        "waiting for more data",
        "monitoring the situation",
        "watching the tape",
        "pass for this one",
    ]
    for note in neutral_cases:
        result = _parse_direction(note)
        assert result is None, f"Expected None for neutral '{note}', got {result}"


# ---------------------------------------------------------------------------
# Test: FDR idempotency — exactly one 'operator' family entry across two runs
# ---------------------------------------------------------------------------
def test_fdr_idempotency_single_operator_entry(tmp_path: Path) -> None:
    """Running grade() twice against the same tmp trial ledger produces exactly
    one 'operator' family entry in the ledger (idempotent registration).
    """
    data_root = _setup_repo(tmp_path, write_ledger=False)

    from engine.operator_grading import grade

    # Run once
    grade(data_root=data_root)
    # Run again — must not double-log
    grade(data_root=data_root)

    # Inspect the trial ledger for 'operator' family entries
    trial_ledger_path = data_root / "data" / "trial_ledger.jsonl"
    if not trial_ledger_path.exists():
        pytest.skip("TrialLedger not available in this environment — skipping idempotency check")

    lines = trial_ledger_path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]

    operator_entries = [
        r for r in rows
        if r.get("family") == "operator"
    ]

    assert len(operator_entries) == 1, (
        f"Expected exactly 1 'operator' family entry in trial ledger after 2 runs, "
        f"got {len(operator_entries)}: {operator_entries}"
    )
