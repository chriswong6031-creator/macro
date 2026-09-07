"""tests/test_build_capability_health.py — F13 V1 BUILDER-level acceptance suite.

Repair 2026-09-04 (independent Opus review, finding I8: "zero tests on
scripts/build_capability_health.py"). engine/capability_health.py's own pure-join laws
are pinned in tests/test_capability_health.py; THIS suite pins the ADAPTER's wiring —
the parts a pure-engine test cannot reach: reading data/run_status.json, mapping
collectors/base.py's status vocabulary onto receipt facts, failing closed on a bad
registry, wiring the previous-state file, CLI exit codes, and the sparse-worktree
default-output guard. Every fixture is built under ``tmp_path`` — nothing here asserts
on the live ``config/capability_health.yml`` or a live ``data/run_status.json``, except
the one deliberate ref-reality check (M6) that binds the SHIPPED registry to the real
``config/synapse.yml`` and ``scripts/collect.py`` — read statically, never imported, so
an optional dependency missing in this environment (e.g. ``yfinance``) can never flip
that test red for an unrelated reason.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import scripts.build_capability_health as BUILD  # noqa: E402
from engine import capability_health as CH  # noqa: E402
from lib.dataos.temporal import TemporalError  # noqa: E402

NOW = datetime(2026, 9, 4, 20, 0, 0, tzinfo=timezone.utc)
FRESH = "2026-09-04T18:00:00+00:00"
OLD = "2026-08-01T00:00:00+00:00"


def _write_registry(root: Path, capabilities: list[dict]) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "capability_health.yml").write_text(
        yaml.safe_dump({"capabilities": capabilities}), encoding="utf-8"
    )


def _write_run_status(
    root: Path, sources: dict, *, last_run: str | None = None, stale_series=None,
) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    doc = {"sources": sources}
    if last_run is not None:
        doc["last_run"] = last_run
    if stale_series is not None:
        doc["stale_series"] = stale_series
    (root / "data" / "run_status.json").write_text(json.dumps(doc), encoding="utf-8")


def _lane_cap(cap_id: str, ref: str, **overrides) -> dict:
    # ROUND-3 repair (2026-09-06 independent review, item 1): a nightly_lane source
    # never truthfully binds data_as_of (see engine/capability_health.py's module
    # docstring and scripts/build_capability_health.py::nightly_lane_facts) — the
    # default fixture here matches the corrected production registry shape.
    base = {
        "id": cap_id,
        "label_en": cap_id,
        "owner": "test",
        "artifacts": [],
        "receipt_sources": [
            {"type": "nightly_lane", "ref": ref,
             "clocks": ["last_attempted", "last_successful"]}
        ],
        "stale_after_hours": 30,
        "next_action_hint": "n/a",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# C1 — a collector status of 'failed' must never read as healthy through the builder
# ---------------------------------------------------------------------------

def test_c1_failed_lane_status_never_reads_healthy(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "failed", "checked_at": FRESH,
                                        "error": "boom"}})
    facts = BUILD.nightly_lane_facts(tmp_path, ["x"])
    fact = facts["x"]
    assert fact["readable"] is True
    assert fact.get("last_successful") is None, (
        "a 'failed' status must never fabricate a last_successful clock"
    )
    # And end to end through the engine: never healthy.
    cap = _lane_cap("cap", "x")
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"cap": [fact]}, now=NOW
    )
    rec = view["capabilities"][0]
    assert rec["state"] != CH.STATE_HEALTHY
    assert rec["state"] is None  # no prior success known -> could_not_look
    assert rec["reason"] != "ok"


def test_c1_dead_lane_status_never_reads_healthy(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "dead", "checked_at": FRESH}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact.get("last_successful") is None
    cap = _lane_cap("cap", "x")
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"cap": [fact]}, now=NOW)
    assert view["capabilities"][0]["state"] != CH.STATE_HEALTHY


# ---------------------------------------------------------------------------
# C2 — a failed lane + an ok sibling must read non-healthy REGARDLESS of source order
# ---------------------------------------------------------------------------

def test_c2_failed_plus_ok_sibling_both_orderings_agree(tmp_path):
    _write_run_status(tmp_path, {
        "good": {"status": "ok", "checked_at": FRESH, "last_date": "2026-09-04"},
        "bad": {"status": "failed", "checked_at": FRESH, "error": "boom"},
    })
    facts = BUILD.nightly_lane_facts(tmp_path, ["good", "bad"])

    cap_order_a = _lane_cap("cap_a", "good", receipt_sources=[
        {"type": "nightly_lane", "ref": "good", "clocks": ["last_attempted", "last_successful"]},
        {"type": "nightly_lane", "ref": "bad", "clocks": ["last_attempted", "last_successful"]},
    ])
    view_a = CH.resolve_capability_health(
        capabilities=[cap_order_a],
        receipts={"cap_a": [facts["good"], facts["bad"]]},
        now=NOW,
    )

    cap_order_b = _lane_cap("cap_b", "bad", receipt_sources=[
        {"type": "nightly_lane", "ref": "bad", "clocks": ["last_attempted", "last_successful"]},
        {"type": "nightly_lane", "ref": "good", "clocks": ["last_attempted", "last_successful"]},
    ])
    view_b = CH.resolve_capability_health(
        capabilities=[cap_order_b],
        receipts={"cap_b": [facts["bad"], facts["good"]]},
        now=NOW,
    )

    state_a = view_a["capabilities"][0]["state"]
    state_b = view_b["capabilities"][0]["state"]
    assert state_a == state_b, "the fold must not depend on declaration/iteration order"
    assert state_a != CH.STATE_HEALTHY
    # The 'good' lane's real success must never be laundered into a clean verdict for
    # the 'bad' lane, nor vice versa (C2's cross-source-union bug).
    assert state_a is None  # 'bad' has no prior success -> could_not_look governs


# ---------------------------------------------------------------------------
# C3 — malformed/missing/duplicate/orphan-dependency registry fails CLOSED
# ---------------------------------------------------------------------------

def test_c3_missing_registry_file_raises_and_never_writes(tmp_path):
    out = tmp_path / "state.json"
    with pytest.raises(BUILD.RegistryError):
        BUILD.build(tmp_path, now=NOW, receipts_root=tmp_path)
    assert not out.exists()


def test_c3_registry_not_a_mapping_raises(tmp_path):
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "capability_health.yml").write_text("- just\n- a\n- list\n")
    with pytest.raises(BUILD.RegistryError, match="did not parse to a mapping"):
        BUILD.load_registry(tmp_path)


def test_c3_missing_capabilities_key_raises(tmp_path):
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "capability_health.yml").write_text("other_key: 1\n")
    with pytest.raises(BUILD.RegistryError, match="no 'capabilities' key"):
        BUILD.load_registry(tmp_path)


def test_c3_empty_capabilities_list_raises(tmp_path):
    _write_registry(tmp_path, [])
    with pytest.raises(BUILD.RegistryError, match="empty or not a list"):
        BUILD.load_registry(tmp_path)


def test_c3_duplicate_capability_id_raises(tmp_path):
    _write_registry(tmp_path, [_lane_cap("dup", "x"), _lane_cap("dup", "y")])
    with pytest.raises(BUILD.RegistryError, match="duplicate capability id"):
        BUILD.load_registry(tmp_path)


def test_c3_unresolvable_depends_on_raises(tmp_path):
    cap = _lane_cap("orphan", "x", **{"depends_on": ["does-not-exist"]})
    _write_registry(tmp_path, [cap])
    with pytest.raises(BUILD.RegistryError, match="not a registered capability id"):
        BUILD.load_registry(tmp_path)


def test_c3_main_exits_nonzero_and_never_writes_over_last_good_state(tmp_path):
    """A GOOD build writes an artifact; a SUBSEQUENT malformed-registry build must exit
    non-zero and leave that artifact byte-for-byte untouched (never a silent
    zero-capability overwrite)."""
    out = tmp_path / "state.json"
    _write_registry(tmp_path, [_lane_cap("good_cap", "x")])
    _write_run_status(tmp_path, {"x": {"status": "ok", "checked_at": FRESH,
                                        "last_date": "2026-09-04"}})
    rc = BUILD.main([
        "--root", str(tmp_path), "--out", str(out), "--receipts-root", str(tmp_path),
        "--now", NOW.isoformat(),
    ])
    assert rc == 0
    assert out.exists()
    before = out.read_bytes()

    # Now corrupt the registry (duplicate id) and rebuild at the SAME --out.
    _write_registry(tmp_path, [_lane_cap("dup", "x"), _lane_cap("dup", "y")])
    rc2 = BUILD.main([
        "--root", str(tmp_path), "--out", str(out), "--receipts-root", str(tmp_path),
        "--now", NOW.isoformat(),
    ])
    assert rc2 != 0
    after = out.read_bytes()
    assert before == after, "a malformed registry must never overwrite last-good state"


# ---------------------------------------------------------------------------
# I5 — collector status -> fact mapping (ok/stale/failed/dead/blocked/skipped)
# ---------------------------------------------------------------------------

def test_i5_status_ok_supplies_success_and_attempt(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "ok", "checked_at": FRESH,
                                        "last_date": "2026-09-04"}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact["last_attempted"] == FRESH
    assert fact["last_successful"] == FRESH
    # ROUND-3 repair (item 1): `last_date` is an observation date, never an as-of
    # instant — nightly_lane_facts must never map it onto data_as_of, in any branch.
    assert "data_as_of" not in fact


def test_i5_status_stale_sets_explicit_stale_state(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "stale", "checked_at": FRESH,
                                        "last_date": "2020-01-01"}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact.get("state") == CH.STATE_STALE
    cap = _lane_cap("cap", "x")
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"cap": [fact]}, now=NOW)
    assert view["capabilities"][0]["state"] == CH.STATE_STALE


def test_i5_status_blocked_sets_rights_blocked(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "blocked", "checked_at": FRESH,
                                        "error": "known bot-block"}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact.get("rights_blocked") is True
    assert "bot-block" in fact.get("rights_detail", "")
    cap = _lane_cap("cap", "x")
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"cap": [fact]}, now=NOW)
    rec = view["capabilities"][0]
    assert rec["state"] == CH.STATE_UNAVAILABLE
    assert any(c.startswith(CH.REASON_RIGHTS_BLOCKED) for c in rec["reason_codes"])
    assert not any(c.startswith(CH.REASON_FAILURE_AFTER_SUCCESS) for c in rec["reason_codes"])


def test_i5_status_skipped_supplies_no_clock_at_all(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "skipped"}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert "last_attempted" not in fact
    assert "last_successful" not in fact
    assert fact.get("rights_blocked") is not True
    cap = _lane_cap("cap", "x")
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"cap": [fact]}, now=NOW)
    rec = view["capabilities"][0]
    # no clock evidence at all -> could_not_look, never a fabricated failure/degraded
    assert rec["state"] is None
    assert any(c.startswith(CH.REASON_NO_CLOCK_EVIDENCE) for c in rec["reason_codes"])


# ---------------------------------------------------------------------------
# MINOR-1 repair: a collector status OUTSIDE the six-value vocabulary (or a source entry
# with NO status key at all) must resolve to a typed `blind_reason` disclosure, never
# the generic "attempted, no prior success" fallthrough. Live shape:
# scripts/collect.py:891's `options_flow_creds` writes {"status": "check_failed", ...}.
# ---------------------------------------------------------------------------

def test_minor1_check_failed_status_yields_typed_unknown_status_disclosure(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "check_failed", "checked_at": FRESH,
                                        "error": "boom"}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact.get("blind_reason") == "unknown_collector_status:x:check_failed"

    cap = _lane_cap("cap", "x")
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"cap": [fact]}, now=NOW)
    rec = view["capabilities"][0]
    assert rec["state"] is None
    assert rec["assessment_status"] == CH.ASSESSMENT_COULD_NOT_LOOK
    assert any(c.startswith(CH.REASON_UNKNOWN_COLLECTOR_STATUS) for c in rec["reason_codes"])
    assert not any(c.startswith(CH.REASON_NO_PRIOR_SUCCESS) for c in rec["reason_codes"]), (
        "an unrecognized status must never be laundered into the ordinary "
        "'attempted, no prior success' read"
    )
    assert rec["reason"] != "ok"


def test_minor1_missing_status_key_yields_typed_unknown_status_disclosure(tmp_path):
    """No `status` key at all — not even an empty string — must ALSO be disclosed by
    name, not silently treated as some other recognized status."""
    _write_run_status(tmp_path, {"x": {"checked_at": FRESH}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact.get("blind_reason") == "unknown_collector_status:x:<missing>"

    cap = _lane_cap("cap", "x")
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"cap": [fact]}, now=NOW)
    rec = view["capabilities"][0]
    assert rec["state"] is None
    assert any(c.startswith(CH.REASON_UNKNOWN_COLLECTOR_STATUS) for c in rec["reason_codes"])


def test_minor1_known_statuses_never_get_a_blind_reason(tmp_path):
    """Regression guard: every RECOGNIZED status must be untouched by this repair."""
    _write_run_status(tmp_path, {
        "ok_src": {"status": "ok", "checked_at": FRESH, "last_date": "2026-09-04"},
        "stale_src": {"status": "stale", "checked_at": FRESH, "last_date": "2020-01-01"},
        "failed_src": {"status": "failed", "checked_at": FRESH},
        "dead_src": {"status": "dead", "checked_at": FRESH},
        "blocked_src": {"status": "blocked", "checked_at": FRESH},
        "skipped_src": {"status": "skipped"},
    })
    refs = ["ok_src", "stale_src", "failed_src", "dead_src", "blocked_src", "skipped_src"]
    facts = BUILD.nightly_lane_facts(tmp_path, refs)
    for ref in refs:
        assert "blind_reason" not in facts[ref], f"{ref} must not get a blind_reason"


# ---------------------------------------------------------------------------
# I6 — previous-state wiring through main(): transition diff is no longer dead
# ---------------------------------------------------------------------------

def test_i6_main_wires_previous_state_across_two_runs(tmp_path):
    out = tmp_path / "state.json"
    _write_registry(tmp_path, [_lane_cap("cap", "x")])
    _write_run_status(tmp_path, {"x": {"status": "ok", "checked_at": FRESH,
                                        "last_date": "2026-09-04"}})

    rc1 = BUILD.main([
        "--root", str(tmp_path), "--out", str(out), "--receipts-root", str(tmp_path),
        "--now", NOW.isoformat(),
    ])
    assert rc1 == 0
    first = json.loads(out.read_text())
    assert first["capabilities"][0]["transition"] == {
        "prev_seen": False, "prev_state": None, "state": CH.STATE_HEALTHY,
    }

    later = (NOW + timedelta(hours=1)).isoformat()
    rc2 = BUILD.main([
        "--root", str(tmp_path), "--out", str(out), "--receipts-root", str(tmp_path),
        "--now", later,
    ])
    assert rc2 == 0
    second = json.loads(out.read_text())
    assert second["capabilities"][0]["transition"]["prev_seen"] is True
    assert second["capabilities"][0]["transition"]["prev_state"] == CH.STATE_HEALTHY


def test_i6_load_previous_returns_none_for_absent_or_unparseable_file(tmp_path):
    assert BUILD.load_previous(tmp_path / "does-not-exist.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert BUILD.load_previous(bad) is None


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------

def test_main_exit_code_2_on_naive_now(tmp_path, capsys):
    rc = BUILD.main(["--root", str(tmp_path), "--out", str(tmp_path / "s.json"),
                      "--now", "2026-09-04T00:00:00"])
    assert rc == 2
    assert not (tmp_path / "s.json").exists()
    err = capsys.readouterr().out
    assert "::error" in err


def test_main_exit_code_2_on_unparseable_now(tmp_path):
    rc = BUILD.main(["--root", str(tmp_path), "--out", str(tmp_path / "s.json"),
                      "--now", "not-a-date-at-all"])
    assert rc == 2
    assert not (tmp_path / "s.json").exists()


def test_main_exit_code_1_on_malformed_registry(tmp_path):
    rc = BUILD.main(["--root", str(tmp_path), "--out", str(tmp_path / "s.json"),
                      "--now", NOW.isoformat()])
    assert rc == 1
    assert not (tmp_path / "s.json").exists()


def test_main_exit_code_0_on_good_registry(tmp_path):
    _write_registry(tmp_path, [_lane_cap("cap", "x")])
    _write_run_status(tmp_path, {"x": {"status": "ok", "checked_at": FRESH,
                                        "last_date": "2026-09-04"}})
    rc = BUILD.main([
        "--root", str(tmp_path), "--out", str(tmp_path / "s.json"),
        "--receipts-root", str(tmp_path), "--now", NOW.isoformat(),
    ])
    assert rc == 0
    assert (tmp_path / "s.json").exists()


# ---------------------------------------------------------------------------
# M5 — sparse-worktree default-output guard (explicit --out is always allowed)
# ---------------------------------------------------------------------------

def test_m5_sparse_guard_is_none_outside_a_git_worktree(tmp_path):
    # tmp_path is not a git repo at all — missing_dirs() must answer [] rather than
    # raising or falsely tripping the guard.
    assert BUILD._sparse_default_out_guard(tmp_path) is None


def test_minor3_sparse_guard_refuses_default_out_when_data_dir_is_missing(tmp_path, monkeypatch):
    """MINOR-3 repair: the suite previously had only the negative case above (a stub
    that always returns None passed it trivially). This is the POSITIVE case — a
    worktree where `data/` really is one of the sparse-omitted top-level dirs — and it
    must both (a) make `_sparse_default_out_guard` return a non-None refusal message and
    (b) make `main()` actually refuse to write the DEFAULT output path: exit non-zero,
    write nothing."""
    import scripts.worktree_sparse as WORKTREE_SPARSE

    monkeypatch.setattr(WORKTREE_SPARSE, "missing_dirs", lambda root: {"data"})

    guard = BUILD._sparse_default_out_guard(tmp_path)
    assert guard is not None
    assert "data" in guard

    _write_registry(tmp_path, [_lane_cap("cap", "x")])
    _write_run_status(tmp_path, {"x": {"status": "ok", "checked_at": FRESH,
                                        "last_date": "2026-09-04"}})
    default_out = tmp_path / "data" / "capability_health" / "state.json"
    rc = BUILD.main([
        "--root", str(tmp_path), "--receipts-root", str(tmp_path), "--now", NOW.isoformat(),
        # deliberately NO --out — this must hit the DEFAULT-path guard
    ])
    assert rc == 2
    assert not default_out.exists()


def test_minor3_sparse_guard_never_fires_with_an_explicit_out(tmp_path, monkeypatch):
    """The guard must never apply to an explicit --out, even when data/ is missing —
    tests/evidence runs/CI all rely on this."""
    import scripts.worktree_sparse as WORKTREE_SPARSE

    monkeypatch.setattr(WORKTREE_SPARSE, "missing_dirs", lambda root: {"data"})
    _write_registry(tmp_path, [_lane_cap("cap", "x")])
    _write_run_status(tmp_path, {"x": {"status": "ok", "checked_at": FRESH,
                                        "last_date": "2026-09-04"}})
    out = tmp_path / "explicit.json"
    rc = BUILD.main([
        "--root", str(tmp_path), "--out", str(out), "--receipts-root", str(tmp_path),
        "--now", NOW.isoformat(),
    ])
    assert rc == 0
    assert out.exists()


# ---------------------------------------------------------------------------
# MINOR-4 repair: rights_detail is capped in length — an unbounded third-party error
# string (collect.py's own additive status dicts bypass collectors/base.py's redactor)
# must never ride, uncapped, into a COMMITTED artifact.
# ---------------------------------------------------------------------------

def test_minor4_rights_detail_is_capped_in_length(tmp_path):
    huge_error = "leaky-third-party-text-" * 50   # well over 300 chars
    assert len(huge_error) > BUILD._RIGHTS_DETAIL_MAX_CHARS
    _write_run_status(tmp_path, {"x": {"status": "blocked", "checked_at": FRESH,
                                        "error": huge_error}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact["rights_detail"] == huge_error[:BUILD._RIGHTS_DETAIL_MAX_CHARS]
    assert len(fact["rights_detail"]) == BUILD._RIGHTS_DETAIL_MAX_CHARS


def test_minor4_rights_detail_short_text_is_untouched(tmp_path):
    _write_run_status(tmp_path, {"x": {"status": "blocked", "checked_at": FRESH,
                                        "error": "known bot-block"}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["x"])["x"]
    assert fact["rights_detail"] == "known bot-block"


# ---------------------------------------------------------------------------
# ROUND-3 REBASE (2026-09-06 independent review): the round-2 IMPORTANT-1 repair
# fixed a real false-GREEN (a corrupt clock reading as healthy) by introducing a false-
# RED — `last_date` is collectors/base.py's group-MAX OBSERVATION date across a
# source's own stored series (fred's real FEDTARMD FOMC-projection shape can legitimately
# carry a `last_date` years in the future on a completely healthy lane), NOT an as-of
# instant, yet the round-2 builder mapped it straight onto `data_as_of` — so this exact
# HEALTHY shape published `could_not_look` / `clock_value_future_dated` forever. The fix
# (round-3, item 1) removes the `last_date` -> `data_as_of` mapping from
# nightly_lane_facts ENTIRELY: a nightly_lane fact now carries only
# last_attempted/last_successful, so the fred-2028 shape must resolve HEALTHY, with no
# data_as_of key published anywhere and no corruption reason at all.
# ---------------------------------------------------------------------------

def test_important1_live_repro_fred_2028_shape_never_reads_healthy_end_to_end(tmp_path):
    _write_run_status(tmp_path, {"fred": {"status": "ok", "checked_at": FRESH,
                                           "last_date": "2028-01-01"}})
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]
    assert fact["last_attempted"] == FRESH
    assert fact["last_successful"] == FRESH
    # round-3: `last_date` is READ off run_status.json (the ok/checked_at path still
    # consults it for nothing else) but is NEVER surfaced as data_as_of any more.
    assert "data_as_of" not in fact

    cap = _lane_cap("market_reference_repro", "fred")
    view = CH.resolve_capability_health(capabilities=[cap], receipts={"market_reference_repro": [fact]}, now=NOW)
    rec = view["capabilities"][0]
    assert rec["state"] == CH.STATE_HEALTHY, (
        "a fresh attempt/success clock pair with no genuine as-of binding must read "
        "healthy — a legitimately far-future OBSERVATION date on a nightly_lane source "
        "must never brand the lane corrupt"
    )
    assert rec["reason"] == "ok"
    assert not rec["reason_codes"]
    assert not any(c.startswith(CH.REASON_CLOCK_FUTURE_DATED) for c in rec["reason_codes"])
    # data_as_of was never a clock this source binds any more — never published.
    assert "data_as_of" not in rec["clocks"] or rec["clocks"]["data_as_of"] is None


def test_important1_live_repro_via_main_writes_healthy_not_could_not_look(tmp_path):
    """Same repro end-to-end through main(), asserting on the WRITTEN artifact — this is
    the scratchpad evidence-run shape the commission asks for. ROUND-3 REBASE: this used
    to assert could_not_look — the WRONG verdict for a healthy lane (see block comment
    above)."""
    _write_registry(tmp_path, [_lane_cap("market_reference_repro", "fred")])
    _write_run_status(tmp_path, {"fred": {"status": "ok", "checked_at": FRESH,
                                           "last_date": "2028-01-01"}})
    out = tmp_path / "state.json"
    rc = BUILD.main([
        "--root", str(tmp_path), "--out", str(out), "--receipts-root", str(tmp_path),
        "--now", NOW.isoformat(), "--json",
    ])
    assert rc == 0
    doc = json.loads(out.read_text())
    rec = doc["capabilities"][0]
    assert rec["state"] == CH.STATE_HEALTHY
    assert rec["reason"] == "ok"
    assert doc["summary"]["by_state"] == {CH.STATE_HEALTHY: 1}
    assert doc["summary"]["by_assessment_status"] == {CH.ASSESSMENT_COMPLETE: 1}
    assert "data_as_of" not in rec["clocks"] or rec["clocks"]["data_as_of"] is None


# ---------------------------------------------------------------------------
# ROUND-5 repair (item 1, round-4 review finding): the round-3 removal of
# `last_date` -> `data_as_of` left the nightly-lane DATA-FRESHNESS axis unrepresented —
# `status` derives from the SAME group-max `last` a forward-dated projection series
# poisons, so a genuinely frozen SIBLING series (e.g. CPIAUCSL stale 308d in the same
# `fred` group as FEDTARMD) reads healthy/ok on run clocks alone. The honest per-series
# receipt already exists: run_status["stale_series"], written by
# collectors/base.py's detect_stale_series/_write_stale_series explicitly "for the
# health surface" and immune to the group-max poisoning.
# ---------------------------------------------------------------------------

def test_round5_status_ok_plus_matching_stale_series_row_forces_stale_not_healthy(tmp_path):
    """THE bug this repair fixes: a fresh, healthy-looking ok/checked_at pair for a
    group that ALSO has a frozen sibling series must never read healthy."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{
            "group": "fred", "series": "CPIAUCSL", "last_obs": "2025-11-01",
            "cadence_days": 30, "age_days": 308, "detected_at": FRESH,
        }],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]
    assert fact["last_attempted"] == FRESH
    assert fact["last_successful"] == FRESH
    assert fact.get("state") == CH.STATE_STALE, (
        "a matching stale_series row must force an explicit stale state even though "
        "the group-max status/checked_at pair reads ok/fresh"
    )
    assert "CPIAUCSL" in fact.get("state_detail", "")
    assert "308" in fact.get("state_detail", "")

    cap = _lane_cap("market_reference_repro", "fred")
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"market_reference_repro": [fact]}, now=NOW,
    )
    rec = view["capabilities"][0]
    assert rec["state"] == CH.STATE_STALE
    assert rec["state"] != CH.STATE_HEALTHY
    assert any(
        "CPIAUCSL" in row["detail"] and "308" in row["detail"] for row in rec["evidence"]
    )


def test_round5_status_ok_with_no_matching_stale_series_row_still_reads_healthy(tmp_path):
    """Composition law (round-5): absence of a matching stale_series row, plus
    status=ok, IS the honest "healthy" read — a stale_series array that exists but
    names a DIFFERENT group must never leak into this ref's verdict."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{
            "group": "yahoo", "series": "SPY", "last_obs": "2026-09-01",
            "cadence_days": 1, "age_days": 3, "detected_at": FRESH,
        }],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]
    assert fact.get("state") is None
    assert "state_detail" not in fact

    cap = _lane_cap("market_reference_repro", "fred")
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"market_reference_repro": [fact]}, now=NOW,
    )
    rec = view["capabilities"][0]
    assert rec["state"] == CH.STATE_HEALTHY
    assert rec["reason"] == "ok"


def test_round5_status_ok_with_no_stale_series_key_at_all_still_reads_healthy(tmp_path):
    """Older receipts (no `stale_series` key at all) must be tolerated, not treated as
    malformed — the join is purely additive."""
    _write_run_status(tmp_path, {"fred": {"status": "ok", "checked_at": FRESH,
                                           "last_date": "2028-01-01"}})
    assert "stale_series" not in json.loads((tmp_path / "data" / "run_status.json").read_text())
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]
    assert fact.get("state") is None
    cap = _lane_cap("market_reference_repro", "fred")
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"market_reference_repro": [fact]}, now=NOW,
    )
    assert view["capabilities"][0]["state"] == CH.STATE_HEALTHY


def test_round5_malformed_stale_series_rows_are_skipped_fail_safe(tmp_path):
    """A non-dict row, and a row missing/carrying a non-string `group`, must never by
    themselves brand a source corrupt or force a spurious stale verdict on an
    unrelated ref."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[
            "not-a-dict",
            {"series": "NO_GROUP_FIELD", "age_days": 99},
            {"group": 12345, "series": "NON_STRING_GROUP", "age_days": 99},
            {"group": "", "series": "EMPTY_GROUP", "age_days": 99},
        ],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]
    assert fact.get("state") is None, "malformed rows must never match any real ref"
    assert fact["readable"] is True
    assert fact["corrupt"] is False


def test_round5_matching_group_row_with_unparseable_detail_fields_still_forces_stale(tmp_path):
    """A row that DOES match the group but carries unparseable/missing series/
    age_days/last_obs must still force the stale state — the JOIN is the group match,
    not the cleanliness of the row's other fields (never silently read as healthy)."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{"group": "fred", "age_days": "not-a-number"}],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]
    assert fact.get("state") == CH.STATE_STALE
    assert isinstance(fact.get("state_detail"), str) and fact["state_detail"]

    cap = _lane_cap("market_reference_repro", "fred")
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"market_reference_repro": [fact]}, now=NOW,
    )
    assert view["capabilities"][0]["state"] == CH.STATE_STALE


def test_round5_stale_series_join_does_not_apply_to_failed_status(tmp_path):
    """Restricted scope: a stale_series row persisting from a PRIOR successful run
    must never downgrade THIS run's failed/dead attempt into a milder explicit stale
    — could_not_look (attempted, no prior success) is the more honest, worse verdict
    and must not be silently softened."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "failed", "checked_at": FRESH, "error": "boom"}},
        stale_series=[{
            "group": "fred", "series": "CPIAUCSL", "last_obs": "2025-11-01",
            "cadence_days": 30, "age_days": 308, "detected_at": FRESH,
        }],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]
    assert fact.get("state") is None
    assert "state_detail" not in fact
    cap = _lane_cap("market_reference_repro", "fred")
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"market_reference_repro": [fact]}, now=NOW,
    )
    assert view["capabilities"][0]["state"] is None


# ---------------------------------------------------------------------------
# M6 — shipped-registry ref-reality: every ref actually resolves to a real definition.
# Read STATICALLY (AST for collect.py, yaml for synapse.yml) — never imported, so an
# environment missing an optional collector dependency (e.g. yfinance) can never flip
# this test red for an unrelated reason.
# ---------------------------------------------------------------------------

def _collect_py_lane_keys() -> set[str]:
    """The literal source-key strings in scripts/collect.py's all_adapters() 'specs'
    list, extracted by parsing the AST — no import, no optional-dependency fragility."""
    tree = ast.parse((REPO / "scripts" / "collect.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "all_adapters":
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "specs" for t in stmt.targets)
                    and isinstance(stmt.value, ast.List)
                ):
                    keys: set[str] = set()
                    for elt in stmt.value.elts:
                        if isinstance(elt, ast.Tuple) and elt.elts:
                            first = elt.elts[0]
                            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                                keys.add(first.value)
                    return keys
    return set()


def _synapse_artifact_ids() -> set[str]:
    doc = yaml.safe_load((REPO / "config" / "synapse.yml").read_text(encoding="utf-8"))
    return set((doc or {}).get("artifacts") or {})


def test_m6_shipped_registry_output_health_artifact_refs_exist_in_synapse():
    doc = yaml.safe_load(
        (REPO / "config" / "capability_health.yml").read_text(encoding="utf-8")
    )
    synapse_ids = _synapse_artifact_ids()
    checked = 0
    for cap in doc["capabilities"]:
        for decl in cap["receipt_sources"]:
            if decl["type"] == "output_health_artifact":
                checked += 1
                assert decl["ref"] in synapse_ids, (
                    f"{cap['id']}: output_health_artifact ref {decl['ref']!r} is not a "
                    f"config/synapse.yml artifact id"
                )
    assert checked > 0, "expected at least one output_health_artifact ref in the shipped registry"


def test_m6_shipped_registry_nightly_lane_refs_exist_in_collect_py():
    doc = yaml.safe_load(
        (REPO / "config" / "capability_health.yml").read_text(encoding="utf-8")
    )
    lane_keys = _collect_py_lane_keys()
    assert lane_keys, "expected to find scripts.collect.all_adapters' specs list statically"
    checked = 0
    for cap in doc["capabilities"]:
        for decl in cap["receipt_sources"]:
            if decl["type"] == "nightly_lane" and decl["ref"] != "__global__":
                checked += 1
                assert decl["ref"] in lane_keys, (
                    f"{cap['id']}: nightly_lane ref {decl['ref']!r} is not a key in "
                    f"scripts.collect.all_adapters()"
                )
    assert checked > 0, "expected at least one non-__global__ nightly_lane ref in the shipped registry"


def test_minor2_shipped_registry_declares_bilingual_label_and_next_action():
    """MINOR-2 repair: the repo's UI law is bilingual EN/ZH (CLAUDE.md §Ops) and
    `label_en`/`next_action_hint` foreshadowed a ZH slot that was left empty. Every
    capability in the SHIPPED registry must now carry a non-empty `label_zh` and
    `next_action_hint_zh` plain-sentence translation alongside the EN text, so a future
    UI consumer never discovers an EN-only registry by surprise."""
    doc = yaml.safe_load(
        (REPO / "config" / "capability_health.yml").read_text(encoding="utf-8")
    )
    caps = doc["capabilities"]
    assert caps, "expected at least one capability in the shipped registry"
    for cap in caps:
        label_zh = cap.get("label_zh")
        hint_zh = cap.get("next_action_hint_zh")
        assert isinstance(label_zh, str) and label_zh.strip(), (
            f"{cap['id']}: missing non-empty label_zh"
        )
        assert isinstance(hint_zh, str) and hint_zh.strip(), (
            f"{cap['id']}: missing non-empty next_action_hint_zh"
        )


def test_minor2_resolved_record_publishes_label_zh_and_next_action_zh():
    """engine.capability_health._record must carry the registry's ZH fields through to
    the resolved record unchanged, alongside (never instead of) the EN fields."""
    cap = {
        "id": "bilingual_cap",
        "label_en": "English Label",
        "label_zh": "中文标签",
        "owner": "test-owner",
        "artifacts": ["data/bilingual_cap.json"],
        "receipt_sources": [
            {"type": "output_health_artifact", "ref": "a", "clocks": ["data_as_of"]}
        ],
        "stale_after_hours": 48,
        "next_action_hint": "check the fixture",
        "next_action_hint_zh": "检查该样例",
    }
    fact = {
        "readable": True, "corrupt": False,
        "last_attempted": FRESH, "last_successful": FRESH,
    }
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"bilingual_cap": [fact]}, now=NOW
    )
    rec = view["capabilities"][0]
    assert rec["label_en"] == "English Label"
    assert rec["label_zh"] == "中文标签"
    assert rec["next_action"] == "check the fixture"
    assert rec["next_action_zh"] == "检查该样例"


def test_naive_now_from_temporal_utc_still_raises_through_build():
    with pytest.raises(TemporalError):
        CH.resolve_capability_health(
            capabilities=[_lane_cap("x", "x")],
            receipts={"x": [{"readable": True, "last_attempted": FRESH}]},
            now=datetime(2026, 9, 4, 12, 0, 0),
        )


# ---------------------------------------------------------------------------
# ROUND-6 repair (2026-09-06 independent review, MAJOR-1): the round-5 stale_series
# join had no recovery path. `collectors/base.py`'s `_write_stale_series` merges by
# (group, series) and never prunes a recovered series — `detect_stale_series` only
# ever RETURNS still-frozen rows, so a series that recovers simply stops being
# written and its row (with its now-stale `detected_at`) sits unpruned forever. RED
# before this repair: one frozen-tail detection in group `fred` forced
# `market_reference` to `stale` on EVERY subsequent run, even once the series
# recovered and every run read `status=ok` with a fresh success clock.
# ---------------------------------------------------------------------------

def test_round6_stale_series_recency_gate_lets_a_recovered_series_read_healthy(tmp_path):
    """The motivating exemplar: a stale_series row detected long ago (OLD, ~34 days
    before NOW — far past the recency window) whose series has since recovered (fresh
    status=ok/checked_at) must no longer force `stale` — the row's silence since OLD is
    evidence of recovery, since a STILL-frozen series would have been re-detected (and
    its detected_at refreshed) on every one of the nightly runs since."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{
            "group": "fred", "series": "CPIAUCSL", "last_obs": "2025-11-01",
            "cadence_days": 30, "age_days": 308, "detected_at": OLD,
        }],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"], now=NOW)["fred"]
    assert fact.get("state") is None, (
        "an un-refreshed stale_series row older than the recency window must stop "
        "forcing stale once the series has had time to recover"
    )
    assert "state_detail" not in fact

    cap = _lane_cap("market_reference_repro", "fred")
    view = CH.resolve_capability_health(
        capabilities=[cap], receipts={"market_reference_repro": [fact]}, now=NOW,
    )
    rec = view["capabilities"][0]
    assert rec["state"] == CH.STATE_HEALTHY, (
        "a recovered series must be able to read healthy again, not be poisoned "
        "forever by one historical detection"
    )


def test_round6_stale_series_recency_gate_still_forces_stale_when_recently_detected(tmp_path):
    """The recency gate discounts only a row that has gone SILENT — a row detected
    recently (the series is STILL being re-flagged run after run) must keep forcing
    stale even though `now` is now supplied to the join. This is the round-5 behavior,
    unchanged for the still-frozen case."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{
            "group": "fred", "series": "CPIAUCSL", "last_obs": "2025-11-01",
            "cadence_days": 30, "age_days": 308, "detected_at": FRESH,
        }],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"], now=NOW)["fred"]
    assert fact.get("state") == CH.STATE_STALE
    assert "CPIAUCSL" in fact.get("state_detail", "")
    assert "308" in fact.get("state_detail", "")


def test_round6_stale_series_recency_gate_treats_missing_detected_at_as_fresh_fail_safe(tmp_path):
    """Fail-safe AMBIGUOUS, not fail-open: a row with no `detected_at` at all (or an
    unparseable one) must still force stale when `now` is supplied — only a row that
    POSITIVELY proves its own staleness may ever be discounted, matching the existing
    round-5 precedent that messy detail fields never cause a silent drop."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{"group": "fred", "series": "CPIAUCSL", "age_days": 308}],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"], now=NOW)["fred"]
    assert fact.get("state") == CH.STATE_STALE, (
        "a row with no detected_at must be treated as fresh (ambiguous, not proven "
        "stale) and still force the state"
    )

    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{
            "group": "fred", "series": "CPIAUCSL", "age_days": 308,
            "detected_at": "not-a-timestamp",
        }],
    )
    fact2 = BUILD.nightly_lane_facts(tmp_path, ["fred"], now=NOW)["fred"]
    assert fact2.get("state") == CH.STATE_STALE, (
        "an unparseable detected_at must likewise be treated as fresh, not dropped"
    )


def test_round6_stale_series_recency_gate_is_opt_in_via_now_backward_compatible(tmp_path):
    """Every pre-existing call site in this suite calls `nightly_lane_facts` without a
    `now` — production's own entry point (`gather_receipts`) always supplies one, but a
    caller that omits it must keep the prior fail-closed behavior (any matching row
    forces stale regardless of age) rather than silently changing meaning underneath
    an untouched call site."""
    _write_run_status(
        tmp_path,
        {"fred": {"status": "ok", "checked_at": FRESH, "last_date": "2028-01-01"}},
        stale_series=[{
            "group": "fred", "series": "CPIAUCSL", "last_obs": "2025-11-01",
            "cadence_days": 30, "age_days": 308, "detected_at": OLD,
        }],
    )
    fact = BUILD.nightly_lane_facts(tmp_path, ["fred"])["fred"]  # no now= supplied
    assert fact.get("state") == CH.STATE_STALE, (
        "omitting now= must preserve the prior behavior: an OLD detected_at still "
        "forces stale when no clock is supplied to gate on"
    )


# ---------------------------------------------------------------------------
# ROUND-6 repair (2026-09-06 independent review, MAJOR-2): the binding ruling's
# acceptance item — "every user-facing label/next-action in
# config/capability_health.yml is plain words EN/ZH" — verified directly against the
# SHIPPED registry, not a hand-built fixture. RED before this repair:
# prophet_us.next_action_hint named nightly-liveness.yml/site/prophet/index.json/
# scripts/prophet_rescue.py verbatim; stock_dossiers.label_en carried the raw slug
# "(R2 stockdata)" and its next_action_hint named could_not_look/mag7-regime-site/
# stock-personality-block/publish_r2; chronicle.next_action_hint named daily.yml/
# scripts/build_chronicle.py/"rc != 0" verbatim.
# ---------------------------------------------------------------------------

_PLAIN_LANGUAGE_FORBIDDEN_SUBSTRINGS = (
    ".py", ".yml", ".jsonl", "site/", "data/run_status", "scripts/",
    "could_not_look", "DARK", "PARTIAL", "rc != 0", "R2 stockdata",
    "mag7-regime-site", "stock-personality-block", "publish_r2",
    "nightly-liveness", "prophet_rescue", "source_asof",
    "collect/engine", "build_foresight", "build_chronicle",
)


def test_round6_shipped_registry_user_facing_strings_are_plain_language():
    doc = yaml.safe_load(
        (REPO / "config" / "capability_health.yml").read_text(encoding="utf-8")
    )
    caps = doc["capabilities"]
    assert caps, "expected at least one capability in the shipped registry"
    for cap in caps:
        for field in ("label_en", "label_zh", "next_action_hint", "next_action_hint_zh"):
            text = cap.get(field) or ""
            for bad in _PLAIN_LANGUAGE_FORBIDDEN_SUBSTRINGS:
                assert bad not in text, (
                    f"{cap['id']}.{field} contains raw internal text {bad!r}: {text!r}"
                )
