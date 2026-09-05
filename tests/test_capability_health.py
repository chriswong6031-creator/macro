"""tests/test_capability_health.py — F13 V1 acceptance suite (capability health).

FIXTURE ROOTS ONLY, mirroring tests/test_output_health.py's own law: nothing here
asserts on the live ``config/capability_health.yml`` content or on the live estate's
health. Every scenario is built in memory. The 8 fixtures named (a)-(h) in the F13
commission are the ``test_fixture_*`` functions below, in the same order the commission
lists them.

REPAIR 2026-09-04 (independent Opus review, CONFIRMED by the F13 principal): this suite
was rewritten to pin the exact production mutants the review found —
  C1 — a lane fact with last_attempted but NO last_successful must never anchor healthy.
  C2 — last_attempted/last_successful must never be cross-source unioned before
       adjudication (source A's attempt vs source B's success).
  I3 — an unreadable source can never be masked by a healthy-reading sibling.
  I2/I4 — an unparseable or future-dated clock value is a CORRUPT receipt, not an absent
          one, and never reads fresh.
  M1 — a non-healthy record never renders its summary ``reason`` as "ok".
  M3 — an unrecognized state defaults to the WORST rank in a worst-of fold.
Fixture (a) now covers BOTH the "present but old success" shape and the C1 production
mutant (absent last_successful entirely); (b) adds a multi-source variant; (c) pins the
degraded/stale boundary with paired same-source clocks; (e) asserts STATE is capped at
degraded, not just that a reason is present.
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

def test_fixture_a1_failure_after_success_is_not_healthy():
    """A present-but-superseded success: last_attempted newer than a REAL, present
    last_successful. This must resolve to degraded/stale, never healthy."""
    cap = _cap("a1_cap", [{"type": "nightly_lane", "ref": "x",
                            "clocks": ["last_attempted", "last_successful"]}])
    fact = {
        "readable": True,
        "last_attempted": FRESH,   # the most recent attempt ...
        "last_successful": OLD,   # ... did NOT succeed; last proven success is old
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] != CH.STATE_HEALTHY
    assert rec["state"] in (CH.STATE_DEGRADED, CH.STATE_STALE)
    assert any(c.startswith(CH.REASON_FAILURE_AFTER_SUCCESS) for c in rec["reason_codes"])


def test_fixture_a2_production_mutant_absent_success_never_anchors_healthy():
    """THE PRODUCTION MUTANT (C1): last_attempted present, last_successful ABSENT
    entirely (not just old — never recorded at all). This source has no prior success
    to point to, so it must be could_not_look — never healthy, never "complete"."""
    cap = _cap("a2_cap", [{"type": "nightly_lane", "ref": "x",
                            "clocks": ["last_attempted"]}])
    fact = {"readable": True, "last_attempted": FRESH}
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None, "an attempt with no prior success must never read healthy"
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_NO_PRIOR_SUCCESS) for c in rec["reason_codes"])


# ---------------------------------------------------------------------------
# (b) missing telemetry/receipt -> could_not_look, never zero/ok
# ---------------------------------------------------------------------------

def test_fixture_b1_missing_receipt_is_could_not_look_not_ok():
    cap = _cap("b1_cap", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}])
    rec = _resolve_single(cap, {"readable": False})
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_RECEIPT_UNREADABLE) for c in rec["reason_codes"])
    assert rec["state"] != CH.STATE_HEALTHY


def test_fixture_b2_multi_source_unreadable_sibling_cannot_be_masked():
    """MULTI-SOURCE VARIANT (I3): one source is genuinely unreadable, the OTHER is a
    fully healthy, well-formed sibling (real ta/ts, both fresh). The unreadable source
    must still govern — a healthy sibling can never mask it."""
    cap = _cap("b2_cap", [
        {"type": "output_health_artifact", "ref": "a", "clocks": ["data_as_of"]},
        {"type": "nightly_lane", "ref": "b", "clocks": ["last_attempted", "last_successful"]},
    ])
    facts = [
        {"readable": False},
        {"readable": True, "last_attempted": FRESH, "last_successful": FRESH},
    ]
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"b2_cap": facts}, now=NOW)
    rec = view["capabilities"][0]
    assert rec["state"] is None, "an unreadable sibling must never be masked by a healthy one"
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_RECEIPT_UNREADABLE) for c in rec["reason_codes"])


# ---------------------------------------------------------------------------
# (c) attempted advanced but successful stale -> degraded/stale, not fresh
# ---------------------------------------------------------------------------

def test_fixture_c_stale_vs_degraded_boundary_paired_same_source_clocks():
    """Paired SAME-SOURCE clocks (never cross-source, per C2) pin the exact
    degraded/stale boundary: last_successful just INSIDE stale_after_hours reads
    degraded (attempt still ahead of it); just OUTSIDE reads stale."""
    stale_after = 6
    # last_attempted is fresher than last_successful in BOTH cases (an attempt happened
    # that did not itself prove a NEW success — a couple of minutes before NOW, always
    # strictly newer than the hours-old success clocks below) — the boundary is purely
    # the AGE of the last known success relative to stale_after_hours.
    recent_attempt = (NOW - timedelta(minutes=1)).isoformat()
    just_inside = (NOW - timedelta(hours=stale_after - 1)).isoformat()
    just_outside = (NOW - timedelta(hours=stale_after + 1)).isoformat()

    cap_inside = _cap(
        "c_inside", [{"type": "nightly_lane", "ref": "x",
                       "clocks": ["last_attempted", "last_successful"]}],
        stale_after_hours=stale_after,
    )
    rec_inside = _resolve_single(
        cap_inside,
        {"readable": True, "last_attempted": recent_attempt, "last_successful": just_inside},
    )
    assert rec_inside["state"] == CH.STATE_DEGRADED
    assert rec_inside["state"] != CH.STATE_HEALTHY

    cap_outside = _cap(
        "c_outside", [{"type": "nightly_lane", "ref": "x",
                        "clocks": ["last_attempted", "last_successful"]}],
        stale_after_hours=stale_after,
    )
    rec_outside = _resolve_single(
        cap_outside,
        {"readable": True, "last_attempted": recent_attempt, "last_successful": just_outside},
    )
    assert rec_outside["state"] == CH.STATE_STALE


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
# (e) deployment skew receipt (process commit != checkout commit) -> STATE capped
# ---------------------------------------------------------------------------

def test_fixture_e_deployment_skew_caps_state_at_degraded():
    cap = _cap("e_cap", [{"type": "nightly_lane", "ref": "x",
                           "clocks": ["last_attempted", "last_successful"]}])
    fact = {
        "readable": True,
        "last_attempted": FRESH,
        "last_successful": FRESH,   # would otherwise read HEALTHY
        "process_commit": "abc1111",
        "checkout_commit": "def2222",
    }
    rec = _resolve_single(cap, fact)
    # RULING: skew caps STATE at degraded, not just a reason on an otherwise-healthy row.
    assert rec["state"] == CH.STATE_DEGRADED
    assert any(c.startswith(CH.REASON_DEPLOYMENT_COMMIT_SKEW) for c in rec["reason_codes"])
    assert any(
        "abc1111" in row["detail"] and "def2222" in row["detail"] for row in rec["evidence"]
    )


def test_deployment_skew_never_upgrades_an_already_worse_state():
    """The skew cap is an upper bound on HEALTHY only — it must never claim to improve
    (or otherwise alter) a source that was already worse than degraded on its own
    clocks."""
    cap = _cap("e_worse_cap", [{"type": "nightly_lane", "ref": "x",
                                 "clocks": ["last_attempted", "last_successful"]}])
    fact = {
        "readable": True,
        "last_attempted": FRESH,
        "last_successful": OLD,   # already failure-after-success -> degraded/stale
        "process_commit": "abc1111",
        "checkout_commit": "def2222",
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] in (CH.STATE_DEGRADED, CH.STATE_STALE)


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
    # transition is visible in the SAME record, and prev_seen distinguishes "there WAS a
    # previous record" from "no history at all" (repair finding I6).
    assert rec["transition"] == {
        "prev_seen": True, "prev_state": CH.STATE_STALE, "state": rec["state"],
    }
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
    assert not any(c.startswith(CH.REASON_FAILURE_AFTER_SUCCESS) for c in rec["reason_codes"])


# ---------------------------------------------------------------------------
# (h) corrupted/truncated receipt bytes -> could_not_look, never clean
# ---------------------------------------------------------------------------

def test_fixture_h1_corrupt_receipt_flag_is_could_not_look_never_clean():
    cap = _cap("h1_cap", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}])
    fact = {"readable": True, "corrupt": True}
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_RECEIPT_CORRUPT) for c in rec["reason_codes"])


def test_fixture_h2_unparseable_clock_bytes_is_could_not_look_never_healthy():
    """I2: a clock value that is PRESENT but unparseable ("truncated bytes" in practice)
    must never be silently treated as absent-and-therefore-fine — it is corrupt."""
    cap = _cap("h2_cap", [{"type": "nightly_lane", "ref": "x",
                            "clocks": ["last_attempted", "last_successful"]}])
    fact = {"readable": True, "last_attempted": "\x00\x01garbage",
            "last_successful": FRESH}
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_CLOCK_UNPARSEABLE) for c in rec["reason_codes"])


def test_fixture_h3_future_dated_clock_is_corrupt_never_healthy_forever():
    """I4: a clock resolving beyond now + tolerance is corrupt, not a permanently-fresh
    reading."""
    cap = _cap("h3_cap", [{"type": "nightly_lane", "ref": "x",
                            "clocks": ["last_attempted", "last_successful"]}])
    future = (NOW + timedelta(days=3000)).isoformat()
    fact = {"readable": True, "last_attempted": future, "last_successful": future}
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec["reason_codes"])


def test_future_dated_clock_within_tolerance_is_not_corrupt():
    """A few minutes of clock skew must not be misread as corruption."""
    cap = _cap("skew_ok_cap", [{"type": "nightly_lane", "ref": "x",
                                 "clocks": ["last_attempted", "last_successful"]}])
    slightly_future = (NOW + timedelta(minutes=5)).isoformat()
    fact = {"readable": True, "last_attempted": slightly_future, "last_successful": slightly_future}
    rec = _resolve_single(cap, fact)
    assert rec["state"] == CH.STATE_HEALTHY


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
    # does not know): the source contributes nothing but a could_not_look verdict.
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
    assert rec_first["transition"] == {
        "prev_seen": False, "prev_state": None, "state": CH.STATE_HEALTHY,
    }

    # second run: previous state was stale, now healthy — the diff must show the move
    previous = {"t_cap": {"state": CH.STATE_STALE}}
    rec_second = _resolve_single(cap, fact, previous=previous)
    assert rec_second["transition"] == {
        "prev_seen": True, "prev_state": CH.STATE_STALE, "state": CH.STATE_HEALTHY,
    }
    # no separate transitions ledger is created anywhere — the diff lives ONLY inside
    # this same per-capability record.
    assert set(rec_second.keys()) >= {"id", "state", "transition", "reason_codes"}


def test_transition_prev_seen_distinguishes_no_history_from_prior_could_not_look():
    """I6: prev_state=None must not be ambiguous between 'never resolved before' and
    'resolved before and WAS could_not_look'."""
    cap = _cap("prev_seen_cap", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}])
    fact = {"readable": False}

    rec_never_seen = _resolve_single(cap, fact)
    assert rec_never_seen["transition"]["prev_seen"] is False
    assert rec_never_seen["transition"]["prev_state"] is None

    previous = {"prev_seen_cap": {"state": None}}
    rec_seen_but_blind = _resolve_single(cap, fact, previous=previous)
    assert rec_seen_but_blind["transition"]["prev_seen"] is True
    assert rec_seen_but_blind["transition"]["prev_state"] is None


# ---------------------------------------------------------------------------
# M1: a non-healthy record never renders its summary "reason" as "ok"
# ---------------------------------------------------------------------------

def test_reason_string_never_says_ok_when_state_is_not_healthy():
    cap = _cap("m1_cap", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}])
    rec = _resolve_single(cap, {"readable": False})
    assert rec["state"] is None
    assert rec["reason"] != "ok"

    cap2 = _cap("m1_cap2", [{"type": "nightly_lane", "ref": "x",
                              "clocks": ["last_attempted", "last_successful"]}])
    rec2 = _resolve_single(
        cap2, {"readable": True, "last_attempted": FRESH, "last_successful": OLD}
    )
    assert rec2["state"] != CH.STATE_HEALTHY
    assert rec2["reason"] != "ok"


def test_reason_string_says_ok_only_when_healthy():
    cap = _cap("m1_healthy_cap", [{"type": "nightly_lane", "ref": "x",
                                    "clocks": ["last_attempted", "last_successful"]}])
    rec = _resolve_single(cap, {"readable": True, "last_attempted": FRESH, "last_successful": FRESH})
    assert rec["state"] == CH.STATE_HEALTHY
    assert rec["reason"] == "ok"


# ---------------------------------------------------------------------------
# M3: _worst's unknown-state default is the WORST rank, not the healthiest
# ---------------------------------------------------------------------------

def test_worst_defaults_unknown_value_to_worst_rank():
    assert CH._worst(["not-a-real-state"]) == "not-a-real-state"
    assert CH._worst([CH.STATE_HEALTHY, "garbage-value"]) == "garbage-value"
    assert CH._worst([CH.STATE_HEALTHY]) == CH.STATE_HEALTHY
    assert CH._worst([None, CH.STATE_HEALTHY]) is None


# ---------------------------------------------------------------------------
# Additional coverage: zero receipt sources, an output_health_artifact-shaped fact
# (pre-judged verdict fold), and worst-of across contributions including None.
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
    assert any(c.startswith(CH.REASON_UPSTREAM_COULD_NOT_LOOK) for c in rec["reason_codes"])
    assert rec["reason"] != "ok"


def test_worst_of_multiple_healthy_sources_governs():
    """When every source DOES speak (no None contribution anywhere), worst-of picks the
    worst REAL state and the assessment is complete."""
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
    assert rec["assessment_status"] == CH.ASSESSMENT_COMPLETE


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


def test_duplicate_capability_id_deduplicates_in_engine_output():
    """Defense in depth (C3): even though the BUILDER is expected to refuse a duplicate
    registry outright, a direct engine caller must never see two rows for one id."""
    caps = [
        _cap("dup_id", [{"type": "nightly_lane", "ref": "x", "clocks": ["last_attempted"]}]),
        _cap("dup_id", [{"type": "nightly_lane", "ref": "y", "clocks": ["last_attempted"]}]),
    ]
    view = CH.resolve_capability_health(
        capabilities=caps, receipts={"dup_id": [{"readable": False}]}, now=NOW
    )
    ids = [c["id"] for c in view["capabilities"]]
    assert ids.count("dup_id") == 1


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
