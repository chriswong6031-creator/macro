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


# --------------------------------------------------------------------------- #
# T3 — the GATE mode, and the emitters it gates.
#
# Before T3 the only mode was the permissive whole-store audit, whose --strict
# was UNSATISFIABLE: every one of its 11 'invalid' findings on the live corpus is
# a property of the corpus (radar will always hold both directions;
# us_importance_v0 will always be salience), so no emitter work could turn it
# green. GATE mode audits what is actually PUBLISHED instead, which is both
# satisfiable and attributable.
# --------------------------------------------------------------------------- #
def test_gate_mode_fires_only_when_the_illegal_metric_is_actually_published():
    mixed = [_claim("m", "a", 1), _claim("m", "b", -1)]
    grades = [{"claim_id": "a", "horizon_d": 5}, {"claim_id": "b", "horizon_d": 5}]

    published = {f.code for f in audit(mixed, grades, reported_metrics={"m": {"excess_mean"}})}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" in published

    magnitude = {f.code for f in audit(mixed, grades,
                                       reported_metrics={"m": {"mean_abs_excess", "hit_rate"}})}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in magnitude


def test_gate_mode_treats_wilson_ci_low_as_a_hit_rate():
    """A CI on the hit rate is a hit rate by another name."""
    salience = [_claim("s", "a", 0), _claim("s", "b", 0)]
    grades = [{"claim_id": "a", "horizon_d": 5}, {"claim_id": "b", "horizon_d": 5}]
    codes = {f.code for f in audit(salience, grades, reported_metrics={"s": {"wilson_ci_low"}})}
    assert "HIT_RATE_ON_A_SALIENCE_FAMILY" in codes


def test_a_group_that_publishes_nothing_is_silent():
    """No entry in reported_metrics means nothing is read, so nothing can be misread."""
    mixed = [_claim("m", "a", 1), _claim("m", "b", -1)]
    grades = [{"claim_id": "a", "horizon_d": 5}, {"claim_id": "b", "horizon_d": 5}]
    assert audit(mixed, grades, reported_metrics={}) == []


def test_desk_grouping_catches_a_mix_no_single_family_shows():
    """by_desk is published too, and two clean families can make a dirty desk."""
    claims = [
        {"claim_family": "up", "desk": "d", "claim_id": "a", "direction": 1, "horizon_d": 5},
        {"claim_family": "down", "desk": "d", "claim_id": "b", "direction": -1, "horizon_d": 5},
    ]
    grades = [{"claim_id": "a", "horizon_d": 5}, {"claim_id": "b", "horizon_d": 5}]
    by_family = {f.code for f in audit(claims, grades, group_by="family",
                                       reported_metrics={"up": {"excess_mean"},
                                                         "down": {"excess_mean"}})}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" not in by_family
    by_desk = {f.code for f in audit(claims, grades, group_by="desk",
                                     reported_metrics={"d": {"excess_mean"}})}
    assert "SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS" in by_desk


def test_the_gate_reads_the_published_artifact_not_the_producer():
    """Non-vacuity: the map must come from an artifact that CAN disagree.

    engine.qledger._aggregate picks its keys with the same predicates this gate
    checks, so a reported_metrics map derived by calling it could never fail
    (memory: receipt-written-from-the-same-variable). Deriving from the
    published track_record.json is what keeps the gate able to fire.
    """
    cli = _load_cli()
    fam, desk = cli.derive_reported_metrics({
        "by_family": {"radar": {"5": {"n_obs": 3, "excess_mean": -0.003}}},
        "by_desk": {"narrative": {"5": {"n_obs": 3, "hit_rate": None}}},
        "promotion_readiness": {
            "us_importance_v0": {"63": {"hit_rate": None, "n_dates": 0}},
            "_duel_context": {"whitehouse": {"challenger_excess_mean_5d": -0.0026}},
        },
    })
    assert fam["radar"] == {"excess_mean"}
    assert fam["us_importance_v0"] == {"hit_rate"}
    assert fam["whitehouse"] == {"excess_mean"}
    assert desk["narrative"] == {"hit_rate"}


def test_aggregate_never_emits_a_key_its_own_profile_forbids():
    """The tripwire the gate cannot be: a direct check on the emitter itself.

    GATE mode audits the published artifact, so a freshly-broken _aggregate is
    only caught on the NEXT nightly. This closes that window at the source.
    """
    from engine import qledger as q

    claims = [
        {"claim_family": "mixed", "desk": "d", "claim_id": "a", "direction": 1,
         "horizon_d": 5, "asof": "2026-08-01"},
        {"claim_family": "mixed", "desk": "d", "claim_id": "b", "direction": -1,
         "horizon_d": 5, "asof": "2026-08-01"},
        {"claim_family": "sal", "desk": "s", "claim_id": "c", "direction": 0,
         "horizon_d": 5, "asof": "2026-08-01"},
        {"claim_family": "up", "desk": "u", "claim_id": "e", "direction": 1,
         "horizon_d": 5, "asof": "2026-08-01"},
    ]
    grades = [
        {"claim_id": "a", "horizon_d": 5, "excess": 0.02, "hit": True},
        {"claim_id": "b", "horizon_d": 5, "excess": -0.04, "hit": True},
        {"claim_id": "c", "horizon_d": 5, "excess": 0.01, "hit": None},
        {"claim_id": "e", "horizon_d": 5, "excess": 0.03, "hit": False},
    ]
    cells = q._aggregate(claims, grades, "family", 5)

    # Mixed direction: the signed pooled mean is withdrawn, the magnitude ships.
    assert "excess_mean" not in cells["mixed"]
    assert cells["mixed"]["mean_abs_excess"] == pytest.approx(0.03)
    assert "hit_rate" in cells["mixed"]

    # Salience-only: no hit rate, no CI on it, but pooling excess stays legal.
    assert "hit_rate" not in cells["sal"]
    assert "wilson_ci_low" not in cells["sal"]
    assert cells["sal"]["excess_mean"] == pytest.approx(0.01)

    # Direction-homogeneous: nothing changes.
    assert cells["up"]["excess_mean"] == pytest.approx(0.03)
    assert cells["up"]["hit_rate"] == 0.0

    # The key sets must agree with the predicates for EVERY group, both groupings.
    for group_by in ("family", "desk"):
        profiles = profile_families(claims, group_by=group_by)
        for key, cell in q._aggregate(claims, grades, group_by, 5).items():
            prof = profiles[key]
            assert ("hit_rate" in cell) == may_report_hit_rate(prof)
            assert ("wilson_ci_low" in cell) == may_report_hit_rate(prof)
            assert ("excess_mean" in cell) == may_pool_signed_excess(prof)
            assert ("mean_abs_excess" in cell) != may_pool_signed_excess(prof)
