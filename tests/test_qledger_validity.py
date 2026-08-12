"""Pins the three metric-validity invariants of the Universal Scoreboard.

Each test states the reading it forbids and why that reading is silent. The
negative controls matter as much as the positives: an auditor that flags
everything is as useless as one that flags nothing, and only the negative
controls prove this one discriminates.
"""
from __future__ import annotations

import json

import pytest

from engine.qledger_validity import (
    SEVERITY_INVALID,
    SEVERITY_NOTE,
    Finding,
    audit,
    may_pool_signed_excess,
    may_report_hit_rate,
    profile_families,
)


def _claim(family: str, cid: str, direction: int, horizon: int = 5, **extra):
    return {
        "claim_family": family,
        "claim_id": cid,
        "direction": direction,
        "horizon_d": horizon,
        **extra,
    }


def _grade(cid: str, horizon: int):
    return {"claim_id": cid, "horizon_d": horizon}


# --------------------------------------------------------------------------- #
# V1 — signed excess may not be pooled across directions
# --------------------------------------------------------------------------- #
def test_mixed_direction_family_may_not_pool_signed_excess():
    """grades.excess is RAW, so a correct bearish call contributes negative excess."""
    claims = [_claim("m", "a", 1), _claim("m", "b", -1)]
    grades = [_grade("a", 5), _grade("b", 5)]
    codes = {f.code for f in audit(claims, grades)}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" in codes


def test_single_direction_family_may_pool_signed_excess():
    """Negative control: one sign means the pooled mean is interpretable."""
    claims = [_claim("h", "c", 1), _claim("h", "d", 1)]
    grades = [_grade("c", 5), _grade("d", 5)]
    codes = {f.code for f in audit(claims, grades)}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes


def test_placebo_rows_do_not_decide_a_real_familys_direction_profile():
    """A synthetic control row must never flip a real family's reporting rights."""
    claims = [
        _claim("h", "c", 1),
        _claim("h", "d", 1),
        _claim("h", "p", -1, is_placebo=True),
    ]
    grades = [_grade("c", 5), _grade("d", 5)]
    codes = {f.code for f in audit(claims, grades)}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes


# --------------------------------------------------------------------------- #
# V2 — a salience family has no hit rate
# --------------------------------------------------------------------------- #
def test_salience_family_may_not_report_a_hit_rate():
    """direction==0 asserts importance, not direction, so `hit` is undefined."""
    claims = [_claim("s", "e", 0), _claim("s", "f", 0)]
    grades = [_grade("e", 5), _grade("f", 5)]
    findings = audit(claims, grades)
    hits = [f for f in findings if f.code == "HIT_RATE_ON_A_SALIENCE_FAMILY"]
    assert hits and hits[0].severity == SEVERITY_INVALID


def test_salience_family_may_still_pool_excess():
    """With no directional claims there is no sign convention to violate."""
    claims = [_claim("s", "e", 0), _claim("s", "f", 0)]
    grades = [_grade("e", 5), _grade("f", 5)]
    codes = {f.code for f in audit(claims, grades)}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes


# --------------------------------------------------------------------------- #
# V3 — a verdict may only be read at the family's declared ruler
# --------------------------------------------------------------------------- #
def test_grades_short_of_the_declared_horizon_are_accruing_not_a_verdict():
    """DNR:KILL-OFFHORIZON-VERDICTS — a 63d claim read at 5d is not a record."""
    claims = [_claim("l", "g", 1, horizon=63)]
    grades = [_grade("g", 5), _grade("g", 21)]
    findings = [f for f in audit(claims, grades) if f.code == "OFF_HORIZON_VERDICT"]
    assert findings and findings[0].severity == SEVERITY_NOTE
    assert "63" in findings[0].detail


def test_off_horizon_finding_clears_once_the_declared_ruler_matures():
    """Negative control: this must be a maturity statement, not a permanent brand."""
    claims = [_claim("l", "g", 1, horizon=63)]
    grades = [_grade("g", 5), _grade("g", 21), _grade("g", 63)]
    codes = {f.code for f in audit(claims, grades)}
    assert "OFF_HORIZON_VERDICT" not in codes


def test_family_declaring_several_horizons_is_ruled_by_its_longest():
    """us_importance_v0 declares {5,21}; its ruler is 21, and 21 is present."""
    claims = [_claim("multi", "x", 1, horizon=5), _claim("multi", "y", 1, horizon=21)]
    grades = [_grade("x", 5), _grade("y", 21)]
    codes = {f.code for f in audit(claims, grades)}
    assert "OFF_HORIZON_VERDICT" not in codes

    grades_short = [_grade("x", 5), _grade("y", 5)]
    codes = {f.code for f in audit(claims, grades_short)}
    assert "OFF_HORIZON_VERDICT" in codes


# --------------------------------------------------------------------------- #
# Profile + schema mechanics
# --------------------------------------------------------------------------- #
def test_direction_and_horizon_are_read_from_strings_too():
    """The live store holds direction as a string ('1'/'-1'); coercion is load-bearing."""
    claims = [_claim("m", "a", "1"), _claim("m", "b", "-1")]
    profiles = profile_families(claims)
    assert profiles["m"].directions == {1, -1}
    assert not may_pool_signed_excess(profiles["m"])


def test_booleans_are_never_read_as_a_direction():
    """bool is an int subclass; a stray True must not become direction==1."""
    profiles = profile_families([_claim("b", "a", True)])
    assert profiles["b"].directions == set()


def test_reported_metrics_narrows_the_audit_to_what_a_caller_publishes():
    claims = [_claim("m", "a", 1), _claim("m", "b", -1)]
    grades = [_grade("a", 5), _grade("b", 5)]
    codes = {f.code for f in audit(claims, grades, reported_metrics={"m": {"hit_rate"}})}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in codes


def test_empty_corpus_yields_no_findings():
    assert audit([], []) == []


def test_finding_rejects_an_unknown_code_or_severity():
    with pytest.raises(ValueError):
        Finding(code="NOPE", family="f", severity=SEVERITY_INVALID, detail="")
    with pytest.raises(ValueError):
        Finding(code="OFF_HORIZON_VERDICT", family="f", severity="critical", detail="")


def test_may_report_hit_rate_requires_a_directional_claim():
    profiles = profile_families([_claim("s", "e", 0)])
    assert not may_report_hit_rate(profiles["s"])
    profiles = profile_families([_claim("d", "e", -1)])
    assert may_report_hit_rate(profiles["d"])


# --------------------------------------------------------------------------- #
# The --json contract (pins a defect found while testing the documented
# reproduce command: --json emitted ::notice lines, not JSON, when the store was
# absent — which is exactly the sparse-worktree and CI case).
# --------------------------------------------------------------------------- #
def _load_cli():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "check_qledger_metric_validity.py"
    spec = importlib.util.spec_from_file_location("_qmv_cli", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_json_payload_is_always_an_object_with_the_same_keys():
    cli = _load_cli()
    absent = json.loads(cli._json_payload(None, store_absent=True, missing=["a", "b"]))
    present = json.loads(cli._json_payload([], store_absent=False, n_claims=3, n_grades=4))
    assert absent.keys() == present.keys()
    for payload in (absent, present):
        assert isinstance(payload, dict)


def test_absent_store_reports_null_findings_not_an_empty_list():
    """"Could not look" must never be encodable as "looked and clean" (§9.2)."""
    cli = _load_cli()
    absent = json.loads(cli._json_payload(None, store_absent=True, missing=["x"]))
    assert absent["store_absent"] is True
    assert absent["findings"] is None
    assert absent["missing"] == ["x"]

    clean = json.loads(cli._json_payload([], store_absent=False, n_claims=0, n_grades=0))
    assert clean["store_absent"] is False
    assert clean["findings"] == []
