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
from datetime import date, datetime, timedelta, timezone
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
# IMPORTANT-1 repair (2026-09-05 independent review): data_as_of/render_release must be
# routed through the SAME corruption check as last_attempted/last_successful — a corrupt
# value on EITHER of these two kinds must never enter the published `clocks` block and
# must never sit beside state=healthy/reason="ok".
#
# ROUND-3 REBASE (2026-09-06 independent review): the test immediately below used to
# assert the WRONG verdict for this exact shape. `last_date` is
# collectors/base.py's group-MAX OBSERVATION date across a source's own stored series —
# never an as-of instant — so a nightly_lane receipt never truthfully binds data_as_of
# at all (see engine/capability_health.py's module docstring and
# scripts/build_capability_health.py::nightly_lane_facts, round-3 item 1). The REAL
# fred/yahoo shape is a fact carrying ONLY last_attempted/last_successful; this must
# read HEALTHY, never the false-red the round-2 IMPORTANT-1 repair produced. The
# corruption law itself is UNCHANGED and still applies in full to a source that
# genuinely binds data_as_of (test_important1_round3_output_health_artifact_can_still_
# bind_data_as_of_and_corrupt, immediately after).
# ---------------------------------------------------------------------------

def test_important1_live_repro_fred_shape_future_dated_data_as_of_never_reads_healthy():
    """THE LIVE REPRO, CORRECTED: a lane entry with a valid, FRESH checked_at (so
    last_attempted and last_successful both read clean) and NO data_as_of key at all —
    the REAL fred/yahoo shape after round-3 (a nightly_lane fact never carries
    data_as_of; its `last_date` is an observation date, not an as-of instant). This
    must read state=healthy, reason="ok", with no data_as_of published and no
    corruption reason — never the could_not_look/clock_value_future_dated the round-2
    repair produced for this exact healthy lane."""
    cap = _cap("fred_repro", [{"type": "nightly_lane", "ref": "fred",
                                "clocks": ["last_attempted", "last_successful"]}])
    fact = {
        "readable": True,
        "last_attempted": FRESH,
        "last_successful": FRESH,
        # no data_as_of key — a nightly_lane receipt never binds one (round-3)
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] == CH.STATE_HEALTHY, (
        "an honest attempt/success clock pair with no as-of binding must read healthy"
    )
    assert rec["assessment_status"] == CH.ASSESSMENT_COMPLETE
    assert not any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec["reason_codes"])
    assert "data_as_of" not in rec["clocks"] or rec["clocks"]["data_as_of"] is None
    assert rec["reason"] == "ok"
    assert not rec["reason_codes"]


def test_important1_round3_output_health_artifact_can_still_bind_data_as_of_and_corrupt():
    """ROUND-3 companion to the rebased fred repro above (item 2: 'ADD a genuine-
    corruption data_as_of fixture through the output_health/artifact fact path'):
    an `output_health_artifact` source GENUINELY binds data_as_of (resolve_output_health's
    already-judged source_asof — a real as-of instant), so the corruption law must still
    fire there in full. Losing data_as_of semantics for `nightly_lane` (round-3) must
    never be read as 'the corruption law was weakened' — it is untouched for the source
    type that actually has as-of semantics."""
    cap = _cap("oh_asof_corrupt", [{"type": "output_health_artifact", "ref": "a",
                                     "clocks": ["data_as_of"]}])
    far_future = "2028-01-01T00:00:00+00:00"
    fact = {
        "readable": True, "corrupt": False,
        "state": CH.STATE_HEALTHY, "assessment_status": "complete",
        "data_as_of": far_future,
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None, "a genuinely-bound as-of instant corruption must still block healthy"
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec["reason_codes"])
    assert "data_as_of" not in rec["clocks"] or rec["clocks"]["data_as_of"] is None
    assert rec["reason"] != "ok"


def test_important1_data_as_of_unparseable_garbage_never_enters_clocks():
    cap = _cap("da_garbage", [{"type": "output_health_artifact", "ref": "a",
                                "clocks": ["data_as_of"]}])
    fact = {
        "readable": True, "corrupt": False,
        "state": CH.STATE_HEALTHY, "assessment_status": "complete",
        "data_as_of": "\x00\x01not-a-date-or-instant",
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_CLOCK_UNPARSEABLE) and c.endswith(":data_as_of")
               for c in rec["reason_codes"])
    assert "data_as_of" not in rec["clocks"] or rec["clocks"]["data_as_of"] is None


def test_important1_data_as_of_year9999_is_future_dated_not_healthy():
    cap = _cap("da_9999", [{"type": "output_health_artifact", "ref": "a",
                             "clocks": ["data_as_of"]}])
    fact = {
        "readable": True, "corrupt": False,
        "state": CH.STATE_HEALTHY, "assessment_status": "complete",
        "data_as_of": "9999-12-31T00:00:00+00:00",
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec["reason_codes"])


def test_important1_render_release_unparseable_and_future_dated_never_healthy():
    """Same law, the OTHER previously-unchecked clock kind (render_release)."""
    cap_bad = _cap("rr_garbage", [{"type": "output_health_artifact", "ref": "a",
                                    "clocks": ["render_release"]}])
    fact_garbage = {
        "readable": True, "corrupt": False,
        "state": CH.STATE_HEALTHY, "assessment_status": "complete",
        "render_release": "not-a-timestamp-at-all",
    }
    rec_garbage = _resolve_single(cap_bad, fact_garbage)
    assert rec_garbage["state"] is None
    assert any(c.startswith(CH.REASON_CLOCK_UNPARSEABLE) for c in rec_garbage["reason_codes"])

    cap_future = _cap("rr_future", [{"type": "output_health_artifact", "ref": "a",
                                      "clocks": ["render_release"]}])
    future = (NOW + timedelta(days=3000)).isoformat()
    fact_future = {
        "readable": True, "corrupt": False,
        "state": CH.STATE_HEALTHY, "assessment_status": "complete",
        "render_release": future,
    }
    rec_future = _resolve_single(cap_future, fact_future)
    assert rec_future["state"] is None
    assert any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec_future["reason_codes"])


def test_important1_data_as_of_boundary_just_inside_and_outside_future_tolerance():
    """Pin the exact FUTURE_CLOCK_TOLERANCE boundary for data_as_of, the same way
    test_future_dated_clock_within_tolerance_is_not_corrupt pins it for last_attempted/
    last_successful — the boundary law must be identical across all four clock kinds."""
    just_inside = (NOW + timedelta(minutes=30)).isoformat()   # < 1h tolerance
    just_outside = (NOW + timedelta(hours=2)).isoformat()      # > 1h tolerance

    cap_inside = _cap("da_inside", [{"type": "output_health_artifact", "ref": "a",
                                      "clocks": ["data_as_of"]}])
    rec_inside = _resolve_single(cap_inside, {
        "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
        "assessment_status": "complete", "data_as_of": just_inside,
    })
    assert rec_inside["state"] == CH.STATE_HEALTHY
    assert rec_inside["clocks"]["data_as_of"] == just_inside

    cap_outside = _cap("da_outside", [{"type": "output_health_artifact", "ref": "a",
                                        "clocks": ["data_as_of"]}])
    rec_outside = _resolve_single(cap_outside, {
        "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
        "assessment_status": "complete", "data_as_of": just_outside,
    })
    assert rec_outside["state"] is None
    assert any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec_outside["reason_codes"])


def test_important1_corrupt_clock_outranks_an_otherwise_healthy_explicit_state():
    """A corrupt data_as_of must override an explicit upstream state=healthy — the whole
    point of the repair is that this can no longer coexist with reason='ok'."""
    cap = _cap("override_cap", [{"type": "output_health_artifact", "ref": "a",
                                  "clocks": ["data_as_of"]}])
    fact = {
        "readable": True, "corrupt": False,
        "state": CH.STATE_HEALTHY, "assessment_status": "complete",
        "data_as_of": "2099-01-01T00:00:00+00:00",
    }
    rec = _resolve_single(cap, fact)
    assert rec["state"] != CH.STATE_HEALTHY
    assert rec["reason"] != "ok"


# ---------------------------------------------------------------------------
# MINOR-5 repair: an upstream `assessment_status: partial` with no explicit state and no
# clock evidence must be named truthfully, not folded into the generic
# REASON_NO_CLOCK_EVIDENCE bucket.
# ---------------------------------------------------------------------------

def test_minor5_upstream_partial_with_no_state_is_named_truthfully():
    cap = _cap("partial_blind_cap", [{"type": "output_health_artifact", "ref": "a",
                                       "clocks": ["data_as_of"]}])
    fact = {"readable": True, "corrupt": False, "state": None, "assessment_status": "partial"}
    rec = _resolve_single(cap, fact)
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_UPSTREAM_PARTIAL_BLIND) for c in rec["reason_codes"])
    # the OLD misleading name must never appear for this specific cause
    assert not any(c.startswith(CH.REASON_NO_CLOCK_EVIDENCE) for c in rec["reason_codes"])
    assert rec["reason"] != "ok"


# ---------------------------------------------------------------------------
# ROUND-3 item 3: date-grain FUTURE tolerance is widened to 26h (a bare calendar-date
# value can legitimately lead a UTC `now` by as much as a UTC+14 timezone offset plus
# ordinary skew); an INSTANT-grain value keeps the tight 1h tolerance pinned above by
# test_future_dated_clock_within_tolerance_is_not_corrupt /
# test_important1_data_as_of_boundary_just_inside_and_outside_future_tolerance.
# ---------------------------------------------------------------------------

def test_round3_date_grain_future_tolerance_boundary_just_inside_and_outside():
    """Pin the exact 26h date-grain boundary the same way the 1h instant-grain boundary
    is pinned elsewhere. A bare date resolves to midnight UTC on that date, so `now` is
    chosen per-case to land the delta just inside/outside 26h."""
    date_value = "2026-09-06"  # reads as midnight UTC 2026-09-06T00:00:00+00:00
    now_inside = datetime(2026, 9, 4, 22, 0, 1, tzinfo=timezone.utc)     # 25h59m59s ahead
    now_outside = datetime(2026, 9, 4, 21, 59, 59, tzinfo=timezone.utc)  # 26h00m01s ahead

    cap_inside = _cap("date_grain_inside", [{"type": "output_health_artifact", "ref": "a",
                                              "clocks": ["data_as_of"]}])
    view_inside = CH.resolve_capability_health(
        capabilities=[cap_inside],
        receipts={"date_grain_inside": [{
            "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
            "assessment_status": "complete", "data_as_of": date_value,
        }]},
        now=now_inside,
    )
    rec_inside = view_inside["capabilities"][0]
    assert rec_inside["state"] == CH.STATE_HEALTHY
    assert rec_inside["clocks"]["data_as_of"] == date_value

    cap_outside = _cap("date_grain_outside", [{"type": "output_health_artifact", "ref": "a",
                                                "clocks": ["data_as_of"]}])
    view_outside = CH.resolve_capability_health(
        capabilities=[cap_outside],
        receipts={"date_grain_outside": [{
            "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
            "assessment_status": "complete", "data_as_of": date_value,
        }]},
        now=now_outside,
    )
    rec_outside = view_outside["capabilities"][0]
    assert rec_outside["state"] is None
    assert any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec_outside["reason_codes"])


def test_round3_date_grain_lead_within_utc14_window_is_not_corrupt():
    """The concrete example from the commission: a `2026-09-06` date value at
    now=2026-09-05T22:30Z (a 1.5h absolute lead) is a legitimate UTC+14 calendar-date
    lead, never corruption."""
    now = datetime(2026, 9, 5, 22, 30, 0, tzinfo=timezone.utc)
    cap = _cap("utc14_lead", [{"type": "output_health_artifact", "ref": "a",
                                "clocks": ["data_as_of"]}])
    view = CH.resolve_capability_health(
        capabilities=[cap],
        receipts={"utc14_lead": [{
            "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
            "assessment_status": "complete", "data_as_of": "2026-09-06",
        }]},
        now=now,
    )
    rec = view["capabilities"][0]
    assert rec["state"] == CH.STATE_HEALTHY
    assert rec["reason"] == "ok"


# ---------------------------------------------------------------------------
# ROUND-3 item 6: the bare-date fallback must accept a real `datetime.date` object
# (PyYAML's unquoted-date shape) equivalently to an ISO date STRING.
# ---------------------------------------------------------------------------

def test_round3_bare_date_object_accepted_equivalently_to_iso_string():
    cap_str = _cap("date_obj_str", [{"type": "output_health_artifact", "ref": "a",
                                      "clocks": ["data_as_of"]}])
    rec_str = _resolve_single(cap_str, {
        "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
        "assessment_status": "complete", "data_as_of": "2026-09-04",
    })
    assert rec_str["state"] == CH.STATE_HEALTHY

    cap_obj = _cap("date_obj_real", [{"type": "output_health_artifact", "ref": "a",
                                       "clocks": ["data_as_of"]}])
    rec_obj = _resolve_single(cap_obj, {
        "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
        "assessment_status": "complete", "data_as_of": date(2026, 9, 4),
    })
    assert rec_obj["state"] == CH.STATE_HEALTHY
    assert rec_obj["clocks"]["data_as_of"] == date(2026, 9, 4)


def test_round3_bare_date_object_far_future_is_still_corrupt():
    """A real `datetime.date` object must be routed through the SAME future-dated
    corruption check as an ISO date string — never silently accepted as unparseable-
    and-therefore-ignored, and never accepted as fresh."""
    cap = _cap("date_obj_future", [{"type": "output_health_artifact", "ref": "a",
                                     "clocks": ["data_as_of"]}])
    rec = _resolve_single(cap, {
        "readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
        "assessment_status": "complete", "data_as_of": date(2028, 1, 1),
    })
    assert rec["state"] is None
    assert any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec["reason_codes"])


# ---------------------------------------------------------------------------
# ROUND-3 item 7: the capability-level display `clocks` merge ("most recent across
# sources wins") must be order-independent for DATE-GRAIN values too — it used to route
# through `_as_utc` alone, which cannot read a bare date at all, degenerating to "first
# non-None wins".
# ---------------------------------------------------------------------------

def test_round3_display_clock_merge_is_order_independent_for_date_grain_values():
    older, newer = "2026-09-01", "2026-09-04"

    cap_a = _cap("merge_order_a", [
        {"type": "output_health_artifact", "ref": "older", "clocks": ["data_as_of"]},
        {"type": "output_health_artifact", "ref": "newer", "clocks": ["data_as_of"]},
    ])
    view_a = CH.resolve_capability_health(
        capabilities=[cap_a],
        receipts={"merge_order_a": [
            {"readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
             "assessment_status": "complete", "data_as_of": older},
            {"readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
             "assessment_status": "complete", "data_as_of": newer},
        ]},
        now=NOW,
    )
    assert view_a["capabilities"][0]["clocks"]["data_as_of"] == newer

    cap_b = _cap("merge_order_b", [
        {"type": "output_health_artifact", "ref": "newer", "clocks": ["data_as_of"]},
        {"type": "output_health_artifact", "ref": "older", "clocks": ["data_as_of"]},
    ])
    view_b = CH.resolve_capability_health(
        capabilities=[cap_b],
        receipts={"merge_order_b": [
            {"readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
             "assessment_status": "complete", "data_as_of": newer},
            {"readable": True, "corrupt": False, "state": CH.STATE_HEALTHY,
             "assessment_status": "complete", "data_as_of": older},
        ]},
        now=NOW,
    )
    assert view_b["capabilities"][0]["clocks"]["data_as_of"] == newer, (
        "the fold must not depend on receipt_sources declaration order"
    )


# ---------------------------------------------------------------------------
# ROUND-3 item 4: any third-party-derived text (blind_reason, rights_detail) entering
# reason_codes/evidence/reason must be length-capped and reason-join-safe AT THE ENGINE
# BOUNDARY — independent of whatever an individual adapter already does.
# ---------------------------------------------------------------------------

def test_round3_foreign_text_blind_reason_is_capped_and_join_safe():
    huge = ("x" * 50) + "; " + ("y" * 500)   # oversized AND contains the join separator
    assert len(huge) > CH.FOREIGN_TEXT_MAX_CHARS
    cap = _cap("blind_cap", [{"type": "nightly_lane", "ref": "x", "clocks": []}])
    rec = _resolve_single(cap, {"readable": True, "blind_reason": huge})
    assert rec["state"] is None
    assert all(len(c) <= CH.FOREIGN_TEXT_MAX_CHARS for c in rec["reason_codes"])
    # reason-join-safe: splitting the published `reason` on "; " must yield exactly as
    # many pieces as reason_codes — an embedded "; " inside a code would inflate this,
    # reading as extra, fabricated reason codes.
    assert len(rec["reason"].split("; ")) == len(rec["reason_codes"])
    for row in rec["evidence"]:
        assert len(row["detail"]) <= CH.FOREIGN_TEXT_MAX_CHARS
        assert "; " not in row["detail"]


def test_round3_foreign_text_rights_detail_is_capped_and_join_safe():
    huge_detail = ("bot-block-detail-" * 30) + "; fabricated-extra-code"
    assert len(huge_detail) > CH.FOREIGN_TEXT_MAX_CHARS
    cap = _cap("rights_cap", [{"type": "nightly_lane", "ref": "x",
                                "clocks": ["last_attempted", "last_successful"]}])
    rec = _resolve_single(cap, {
        "readable": True, "last_attempted": FRESH, "last_successful": FRESH,
        "rights_blocked": True, "rights_detail": huge_detail,
    })
    assert rec["state"] == CH.STATE_UNAVAILABLE
    for row in rec["evidence"]:
        assert len(row["detail"]) <= CH.FOREIGN_TEXT_MAX_CHARS
        assert "; " not in row["detail"]


def test_round3_foreign_text_short_clean_text_is_untouched():
    """Regression guard: ordinary short text must survive byte-for-byte."""
    cap = _cap("rights_clean", [{"type": "nightly_lane", "ref": "x",
                                  "clocks": ["last_attempted", "last_successful"]}])
    rec = _resolve_single(cap, {
        "readable": True, "last_attempted": FRESH, "last_successful": FRESH,
        "rights_blocked": True, "rights_detail": "known bot-block",
    })
    assert any(row["detail"] == "known bot-block" for row in rec["evidence"])


# ---------------------------------------------------------------------------
# MINOR-2 repair: validate_registry must fail closed on a LONGER depends_on cycle, not
# just a self-loop.
# ---------------------------------------------------------------------------

def test_minor2_validate_registry_detects_two_node_depends_on_cycle():
    caps = [
        _cap("cyc_a", [{"type": "nightly_lane", "ref": "x"}], depends_on=["cyc_b"]),
        _cap("cyc_b", [{"type": "nightly_lane", "ref": "y"}], depends_on=["cyc_a"]),
    ]
    problems = CH.validate_registry(caps)
    assert any("cycle" in p.lower() for p in problems), (
        "a -> b -> a must be reported; the pairwise self-loop/unresolvable-ref checks "
        "cannot see a longer cycle"
    )


def test_minor2_validate_registry_detects_three_node_depends_on_cycle():
    caps = [
        _cap("c1", [{"type": "nightly_lane", "ref": "x"}], depends_on=["c2"]),
        _cap("c2", [{"type": "nightly_lane", "ref": "y"}], depends_on=["c3"]),
        _cap("c3", [{"type": "nightly_lane", "ref": "z"}], depends_on=["c1"]),
    ]
    problems = CH.validate_registry(caps)
    assert any("cycle" in p.lower() for p in problems)


def test_minor2_validate_registry_accepts_an_acyclic_dependency_chain():
    """A straight-line dependency chain (never a cycle) must still validate clean."""
    caps = [
        _cap("root", [{"type": "nightly_lane", "ref": "x"}]),
        _cap("mid", [{"type": "nightly_lane", "ref": "y"}], depends_on=["root"]),
        _cap("leaf", [{"type": "nightly_lane", "ref": "z"}], depends_on=["mid"]),
    ]
    assert CH.validate_registry(caps) == []


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
