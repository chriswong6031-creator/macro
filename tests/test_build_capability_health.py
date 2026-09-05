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


def _write_run_status(root: Path, sources: dict, *, last_run: str | None = None) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    doc = {"sources": sources}
    if last_run is not None:
        doc["last_run"] = last_run
    (root / "data" / "run_status.json").write_text(json.dumps(doc), encoding="utf-8")


def _lane_cap(cap_id: str, ref: str, **overrides) -> dict:
    base = {
        "id": cap_id,
        "label_en": cap_id,
        "owner": "test",
        "artifacts": [],
        "receipt_sources": [
            {"type": "nightly_lane", "ref": ref,
             "clocks": ["last_attempted", "last_successful", "data_as_of"]}
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
    assert fact["data_as_of"] == "2026-09-04"


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


def test_naive_now_from_temporal_utc_still_raises_through_build():
    with pytest.raises(TemporalError):
        CH.resolve_capability_health(
            capabilities=[_lane_cap("x", "x")],
            receipts={"x": [{"readable": True, "last_attempted": FRESH}]},
            now=datetime(2026, 9, 4, 12, 0, 0),
        )
