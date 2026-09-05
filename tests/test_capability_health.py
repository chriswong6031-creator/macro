"""tests/test_capability_health.py — F13 V1 acceptance suite (capability health).

FIXTURE ROOTS ONLY, mirroring tests/test_output_health.py's own law: nothing here
asserts on the live ``config/capability_health.yml`` content or on the live estate's
health. Every scenario is built in memory. The 8 fixtures named (a)-(h) in the F13
commission are the ``test_fixture_*`` functions below, in the same order the commission
lists them.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from engine import capability_health as CH  # noqa: E402

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
FRESH = "2026-09-04T06:00:00+00:00"    # 6h before NOW — inside a 48h stale budget
OLD = "2026-08-01T06:00:00+00:00"      # well outside any reasonable stale budget


def _cap(cap_id: str, sources: list[dict], **overrides) -> dict:
    base = {
        "id": cap_id,
        "label_en": f"Test — {cap_id}",
        "owner": "test-owner",
        "artifacts": [f"data/{cap_id}.json"],
        "receipt_sources": sources,
        "stale_after_hours": 48,
        "next_action_hint": "check the fixture",
    }
    base.update(overrides)
    return base


def _resolve_single(cap: dict, fact: dict | None, **kwargs) -> dict:
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={cap["id"]: [fact]}, now=NOW, **kwargs
    )
    assert len(view["capabilities"]) == 1
    return view["capabilities"][0]


# ---------------------------------------------------------------------------
# (a) failure-after-success -> not healthy
# ---------------------------------------------------------------------------

def test_fixture_a_failure_after_success_is_not_healthy():
    cap = _cap("a_cap", [{"type": "nightly_lane", "ref": "x",
                           "clocks": ["last_attempted", "last_successful"]}])
    fact = {
        "readable": True,
        "last_attempted": FRESH,   # the most recent attempt ...
        "last_successful": OLD,   # ... did NOT succeed; last proven success is old
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] != CH.STATE_HEALTHY
    assert rec["state"] in (CH.STATE_DEGRADED, CH.STATE_STALE)
    assert CH.REASON_FAILURE_AFTER_SUCCESS in rec["reason_codes"]


# ---------------------------------------------------------------------------
# (b) missing telemetry/receipt -> could_not_look, never zero/ok
# ---------------------------------------------------------------------------

def test_fixture_b_missing_receipt_is_could_not_look_not_ok():
    cap = _cap("b_cap", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}])
    rec = _resolve_single(cap, {"readable": False})
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_ALL_SOURCES_UNREADABLE) for c in rec["reason_codes"])
    # never silently renders as a clean/zero state
    assert rec["state"] != CH.STATE_HEALTHY


# ---------------------------------------------------------------------------
# (c) attempted advanced but successful stale -> degraded/stale, not fresh
# ---------------------------------------------------------------------------

def test_fixture_c_attempted_advanced_success_stale_is_not_fresh():
    cap = _cap(
        "c_cap",
        [{"type": "nightly_lane", "ref": "x",
          "clocks": ["last_attempted", "last_successful"]}],
        stale_after_hours=6,
    )
    fact = {"readable": True, "last_attempted": FRESH, "last_successful": FRESH}
    # last_successful itself is beyond the 6h stale budget relative to NOW (6h old).
    old_success = (NOW - timedelta(hours=200)).isoformat()
    fact = {"readable": True, "last_attempted": FRESH, "last_successful": old_success}
    rec = _resolve_single(cap, fact)
    assert rec["state"] in (CH.STATE_DEGRADED, CH.STATE_STALE)
    assert rec["state"] != CH.STATE_HEALTHY


# ---------------------------------------------------------------------------
# (d) dependency outage -> dependent capability degraded, no failover
# ---------------------------------------------------------------------------

def test_fixture_d_dependency_outage_degrades_dependent_with_no_failover():
    upstream = _cap("upstream", [{"type": "nightly_lane", "ref": "x",
                                   "clocks": ["last_attempted", "last_successful"]}])
    downstream = _cap(
        "downstream",
        [{"type": "nightly_lane", "ref": "y",
          "clocks": ["last_attempted", "last_successful"]}],
        depends_on=["upstream"],
    )
    receipts = {
        # upstream is definitively broken (last_attempted way newer than last_successful)
        "upstream": [{"readable": True, "last_attempted": FRESH, "last_successful": OLD}],
        # downstream's OWN receipt is perfectly healthy
        "downstream": [{"readable": True, "last_attempted": FRESH, "last_successful": FRESH}],
    }
    view = CH.resolve_capability_health(
        capabilities=[upstream, downstream], receipts=receipts, now=NOW
    )
    by_id = {r["id"]: r for r in view["capabilities"]}
    assert by_id["upstream"]["state"] != CH.STATE_HEALTHY
    # downstream is capped to degraded by the dependency — never silently healed to
    # healthy by its own (otherwise-healthy) receipt. "No failover" = its own healthy
    # evidence never overrides the propagated dependency outage.
    assert by_id["downstream"]["state"] == CH.STATE_DEGRADED
    assert any(
        c.startswith(CH.REASON_DEPENDENCY_DEGRADED) for c in by_id["downstream"]["reason_codes"]
    )


# ---------------------------------------------------------------------------
# (e) deployment skew receipt (process commit != checkout commit) -> surfaced
# ---------------------------------------------------------------------------

def test_fixture_e_deployment_skew_is_surfaced():
    cap = _cap("e_cap", [{"type": "nightly_lane", "ref": "x",
                           "clocks": ["last_attempted", "last_successful"]}])
    fact = {
        "readable": True,
        "last_attempted": FRESH,
        "last_successful": FRESH,
        "process_commit": "abc1111",
        "checkout_commit": "def2222",
    }
    rec = _resolve_single(cap, fact)
    assert any(c.startswith(CH.REASON_DEPLOYMENT_COMMIT_SKEW) for c in rec["reason_codes"])
    assert any(
        "abc1111" in row["detail"] and "def2222" in row["detail"] for row in rec["evidence"]
    )


# ---------------------------------------------------------------------------
# (f) correction/replay receipt -> transition visible, original clocks preserved
# ---------------------------------------------------------------------------

def test_fixture_f_correction_replay_keeps_transition_and_original_clock():
    cap = _cap("f_cap", [{"type": "nightly_lane", "ref": "x",
                           "clocks": ["last_attempted", "last_successful", "data_as_of"]}])
    original_asof = "2026-08-20T00:00:00+00:00"
    corrected_asof = "2026-08-25T00:00:00+00:00"
    fact = {
        "readable": True,
        "last_attempted": FRESH,
        "last_successful": FRESH,
        "data_as_of": corrected_asof,
        "replay_of": original_asof,
    }
    previous = {"f_cap": {"state": CH.STATE_STALE}}
    rec = _resolve_single(cap, fact, previous=previous)
    # transition is visible in the SAME record
    assert rec["transition"] == {"prev_state": CH.STATE_STALE, "state": rec["state"]}
    # the correction is disclosed, and the ORIGINAL clock value is preserved (in
    # evidence) rather than silently overwritten with no trace
    assert any(c.startswith(CH.REASON_CORRECTION_REPLAY) for c in rec["reason_codes"])
    assert any(original_asof in row["detail"] for row in rec["evidence"])
    # the new data_as_of still governs the clock the record displays
    assert rec["clocks"]["data_as_of"] == corrected_asof


# ---------------------------------------------------------------------------
# (g) rights-block receipt -> typed unavailable + rights reason, not failure
# ---------------------------------------------------------------------------

def test_fixture_g_rights_block_is_typed_unavailable_not_failure():
    cap = _cap("g_cap", [{"type": "nightly_lane", "ref": "x",
                           "clocks": ["last_attempted", "last_successful"]}])
    fact = {
        "readable": True,
        "last_attempted": FRESH,
        "last_successful": FRESH,
        "rights_blocked": True,
        "rights_detail": "anonymous GET -> HTTP 401; registration wall",
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] == CH.STATE_UNAVAILABLE
    assert any(c.startswith(CH.REASON_RIGHTS_BLOCKED) for c in rec["reason_codes"])
    # never mistaken for a generic failure-after-success read
    assert CH.REASON_FAILURE_AFTER_SUCCESS not in rec["reason_codes"]


# ---------------------------------------------------------------------------
# (h) corrupted/truncated receipt bytes -> could_not_look, never clean
# ---------------------------------------------------------------------------

def test_fixture_h_corrupt_receipt_is_could_not_look_never_clean():
    cap = _cap("h_cap", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}])
    fact = {"readable": True, "corrupt": True}
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_RECEIPT_CORRUPT) for c in rec["reason_codes"])


# ---------------------------------------------------------------------------
# Registry-schema validation: every receipt_source type resolvable; unknown fails closed
# ---------------------------------------------------------------------------

def test_registry_validation_accepts_known_types():
    caps = [
        _cap("valid_cap", [
            {"type": "output_health_artifact", "ref": "some-artifact", "clocks": ["data_as_of"]},
            {"type": "nightly_lane", "ref": "fred", "clocks": ["last_attempted"]},
            {"type": "provider_rung", "ref": "ask-brain", "clocks": ["last_attempted"]},
            {"type": "sentinel_probe", "ref": "prophet_us", "clocks": ["data_as_of"]},
        ]),
    ]
    assert CH.validate_registry(caps) == []


def test_registry_validation_fails_closed_on_unknown_type():
    caps = [_cap("bad_cap", [{"type": "carrier_pigeon", "ref": "x"}])]
    problems = CH.validate_registry(caps)
    assert problems, "an unknown receipt_source type must be reported, not silently accepted"
    assert any("carrier_pigeon" in p and "unknown type" in p for p in problems)

    # AND the resolver itself fails closed on it (never invents a verdict for a type it
    # does not know): the source contributes nothing but unreadability.
    rec = _resolve_single(caps[0], {"readable": True, "last_attempted": FRESH})
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_UNKNOWN_RECEIPT_TYPE) for c in rec["reason_codes"])


def test_registry_validation_catches_missing_ref_dup_id_and_bad_depends_on():
    caps = [
        {"id": "dup", "receipt_sources": [{"type": "nightly_lane", "ref": "x"}]},
        {"id": "dup", "receipt_sources": [{"type": "nightly_lane"}]},  # missing ref + dup id
        {"id": "orphan", "receipt_sources": [{"type": "nightly_lane", "ref": "y"}],
         "depends_on": ["does-not-exist"]},
    ]
    problems = CH.validate_registry(caps)
    assert any("duplicate capability id" in p for p in problems)
    assert any("missing a non-empty 'ref'" in p for p in problems)
    assert any("does-not-exist" in p and "not a registered capability id" in p for p in problems)


def test_registry_validation_rejects_no_receipt_sources():
    caps = [{"id": "empty_cap", "receipt_sources": []}]
    problems = CH.validate_registry(caps)
    assert any("no receipt_sources declared" in p for p in problems)


# ---------------------------------------------------------------------------
# Transition-diff test
# ---------------------------------------------------------------------------

def test_transition_diff_embedded_in_the_single_output_record():
    cap = _cap("t_cap", [{"type": "nightly_lane", "ref": "x",
                           "clocks": ["last_attempted", "last_successful"]}])
    fact = {"readable": True, "last_attempted": FRESH, "last_successful": FRESH}

    # first run: no previous state at all
    rec_first = _resolve_single(cap, fact)
    assert rec_first["transition"] == {"prev_state": None, "state": CH.STATE_HEALTHY}

    # second run: previous state was stale, now healthy — the diff must show the move
    previous = {"t_cap": {"state": CH.STATE_STALE}}
    rec_second = _resolve_single(cap, fact, previous=previous)
    assert rec_second["transition"] == {"prev_state": CH.STATE_STALE, "state": CH.STATE_HEALTHY}
    # no separate transitions ledger is created anywhere — the diff lives ONLY inside
    # this same per-capability record.
    assert set(rec_second.keys()) >= {"id", "state", "transition", "reason_codes"}


# ---------------------------------------------------------------------------
# Additional coverage: zero receipt sources, unknown never renders as ok, worst-of fold,
# and an output_health_artifact-shaped fact (pre-judged verdict fold).
# ---------------------------------------------------------------------------

def test_zero_receipt_sources_is_could_not_look():
    cap = {"id": "no_sources", "receipt_sources": []}
    rec = _resolve_single(cap, None)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert CH.REASON_NO_RECEIPT_SOURCES in rec["reason_codes"]


def test_output_health_artifact_fact_folds_upstream_verdict_verbatim():
    cap = _cap("oh_cap", [{"type": "output_health_artifact", "ref": "some-artifact",
                            "clocks": ["data_as_of"]}])
    fact = {
        "readable": True,
        "corrupt": False,
        "state": CH.STATE_DEGRADED,
        "assessment_status": "partial",
        "data_as_of": FRESH,
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] == CH.STATE_DEGRADED
    assert rec["clocks"]["data_as_of"] == FRESH


def test_output_health_artifact_could_not_look_upstream_propagates():
    cap = _cap("oh_blind", [{"type": "output_health_artifact", "ref": "some-artifact",
                              "clocks": ["data_as_of"]}])
    fact = {"readable": True, "corrupt": False, "state": None, "assessment_status": "could_not_look"}
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK


def test_worst_of_multiple_sources_governs():
    cap = _cap("multi_cap", [
        {"type": "output_health_artifact", "ref": "a", "clocks": ["data_as_of"]},
        {"type": "output_health_artifact", "ref": "b", "clocks": ["data_as_of"]},
    ])
    facts = [
        {"readable": True, "state": CH.STATE_HEALTHY, "assessment_status": "complete"},
        {"readable": True, "state": CH.STATE_UNAVAILABLE, "assessment_status": "complete"},
    ]
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"multi_cap": facts}, now=NOW
    )
    rec = view["capabilities"][0]
    assert rec["state"] == CH.STATE_UNAVAILABLE


def test_summary_never_tallies_a_null_state_as_a_real_one():
    cap_ok = _cap("ok_cap", [{"type": "nightly_lane", "ref": "x",
                               "clocks": ["last_attempted", "last_successful"]}])
    cap_blind = _cap("blind_cap", [{"type": "nightly_lane", "ref": "y", "clocks": ["last_attempted"]}])
    receipts = {
        "ok_cap": [{"readable": True, "last_attempted": FRESH, "last_successful": FRESH}],
        "blind_cap": [{"readable": False}],
    }
    view = CH.resolve_capability_health(
        capabilities=[cap_ok, cap_blind], receipts=receipts, now=NOW
    )
    summary = view["summary"]
    assert summary["by_state"].get("null") == 1
    assert summary["by_state"].get(CH.STATE_HEALTHY) == 1
    assert summary["by_assessment_status"][CH.ASSESSMENT_COULD_NOT_LOOK] == 1


def test_json_serializable_end_to_end():
    cap = _cap("json_cap", [{"type": "nightly_lane", "ref": "x",
                              "clocks": ["last_attempted", "last_successful"]}])
    view = CH.resolve_capability_health(
        capabilities=[cap],
        receipts={"json_cap": [{"readable": True, "last_attempted": FRESH, "last_successful": FRESH}]},
        now=NOW,
    )
    json.dumps(view)  # must not raise


def test_naive_datetime_is_refused():
    import pytest
    from lib.dataos.temporal import TemporalError

    cap = _cap("naive_cap", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}])
    with pytest.raises(TemporalError):
        CH.resolve_capability_health(
            capabilities=[cap],
            receipts={"naive_cap": [{"readable": True, "last_attempted": FRESH}]},
            now=datetime(2026, 9, 4, 12, 0, 0),  # naive — no tzinfo
        )
