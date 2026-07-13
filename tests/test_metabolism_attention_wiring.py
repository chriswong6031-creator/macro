"""tests/test_metabolism_attention_wiring.py — V9 Attention Economy wiring tests.

COVERAGE:
  AW-1  _apply_attention_ordering: regular items permute by weight; forced_floor
        and prior_demoted items keep exact absolute positions.
  AW-2  _apply_attention_ordering: absent/empty allocation → order unchanged.
  AW-3  _apply_attention_ordering: never raises on junk allocation.
  AW-4  Agenda trim under attention: trimmed-away regular items are the
        lowest-weight ones; forced-floor and demoted invariants hold.
  AW-5  orchestrator_brain Part 5h: system prompt contains "Attention Allocation"
        section; with a fixture file it lists FOCUS lobe ids.
  AW-6  orchestrator_brain Part 5h: absent file → "(attention allocation absent
        — accruing)".
  AW-7  propose skip path: DORMANT lobe writes empty docket, makes no LLM call.
  AW-8  propose exemption path (False,"urgent_fix_exemption") runs single-lobe
        normally (no empty-docket short-circuit).
  AW-9  build dispatch ordering: FOCUS lobe dispatched first; adjudication order
        preserved within band; zero rows dropped.

All tests are HERMETIC (tmp_path roots, no network, no real LLM calls).
The attention module (engine/metabolism/attention.py) may not exist on disk
when this runs (sibling builder).  Where the module is absent we inject a
minimal stub via sys.modules monkeypatching so the wiring code under test
can import it.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tmp_root(tmp_path: Path) -> Path:
    """Build a minimal metabolism directory tree."""
    for sub in [
        "data/metabolism/dockets",
        "data/metabolism/journal",
        "data/metabolism/agenda",
        "data/metabolism/fitness",
        "config",
    ]:
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _make_attention_module(
    band_map: dict[str, str] | None = None,
    weight_map: dict[str, float] | None = None,
    priority_map: dict[str, int] | None = None,
    allocation: dict | None = None,
) -> types.ModuleType:
    """Return a minimal stub for engine.metabolism.attention."""
    _BAND_WEIGHTS = {"FOCUS": 1.0, "STANDARD": 0.6, "MAINTENANCE": 0.2, "DORMANT": 0.0}
    _BAND_PRIORITIES = {"FOCUS": 0, "STANDARD": 1, "MAINTENANCE": 2, "DORMANT": 3}

    m = types.ModuleType("engine.metabolism.attention")

    def load_allocation(root=None):
        return allocation or {}

    def band_for(lobe_id, allocation=None, root=None):
        if band_map and lobe_id in band_map:
            return band_map[lobe_id]
        return "STANDARD"

    def weight_for(lobe_id, allocation=None, root=None):
        if weight_map and lobe_id in weight_map:
            return weight_map[lobe_id]
        b = band_for(lobe_id, allocation=allocation)
        return _BAND_WEIGHTS.get(b, 0.6)

    def effective_docket_size(lobe_id, base_size, root=None, allocation=None):
        b = band_for(lobe_id, root=root)
        if b == "DORMANT":
            return 0
        share = _BAND_WEIGHTS.get(b, 0.6)
        return max(1, int(base_size * share))

    def propose_skip(lobe_id, root=None, allocation=None):
        b = band_for(lobe_id, root=root)
        if b == "DORMANT":
            return True, "attention_dormant"
        return False, ""

    def dispatch_priority(lobe_id, allocation=None, root=None):
        if priority_map and lobe_id in priority_map:
            return priority_map[lobe_id]
        b = band_for(lobe_id, root=root)
        return _BAND_PRIORITIES.get(b, 1)

    m.load_allocation = load_allocation
    m.band_for = band_for
    m.weight_for = weight_for
    m.effective_docket_size = effective_docket_size
    m.propose_skip = propose_skip
    m.dispatch_priority = dispatch_priority
    return m


def _inject_attention(monkeypatch, *, band_map=None, weight_map=None,
                      priority_map=None, allocation=None):
    """Inject the attention stub into sys.modules."""
    stub = _make_attention_module(
        band_map=band_map,
        weight_map=weight_map,
        priority_map=priority_map,
        allocation=allocation,
    )
    monkeypatch.setitem(sys.modules, "engine.metabolism.attention", stub)
    # Also inject under the engine.metabolism namespace if it exists.
    pkg = sys.modules.get("engine.metabolism")
    if pkg is not None:
        monkeypatch.setattr(pkg, "attention", stub, raising=False)
    return stub


def _make_item(title: str, lobe: str | None = None, *, forced_floor: bool = False,
               prior_demoted: bool = False) -> dict[str, Any]:
    return {
        "title": title,
        "bucket": "NOVEL_BUILD",
        "severity": "low",
        "target_lobe": lobe,
        "rationale": "",
        "dedup_hash": title[:12],
        "forced_floor": forced_floor,
        **({"prior_demoted": True, "prior_bucket": "test"} if prior_demoted else {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# AW-1: _apply_attention_ordering permutes regular items by weight,
#        forced_floor and prior_demoted keep absolute positions.
# ─────────────────────────────────────────────────────────────────────────────

def test_aw1_attention_ordering_permutes_regular(monkeypatch):
    """Regular items permute by descending weight; pinned items stay put."""
    from engine.metabolism.agenda import _apply_attention_ordering

    _inject_attention(monkeypatch, weight_map={
        "lobe_a": 1.0,   # FOCUS
        "lobe_b": 0.2,   # MAINTENANCE
        "lobe_c": 0.6,   # STANDARD
    })

    # Arrangement: regular-b at idx-0, forced at idx-1, regular-a at idx-2,
    # demoted at idx-3, regular-c at idx-4.
    items = [
        _make_item("B low weight", lobe="lobe_b"),          # idx 0 — regular
        _make_item("FLOOR item", forced_floor=True),         # idx 1 — pinned
        _make_item("A high weight", lobe="lobe_a"),          # idx 2 — regular
        _make_item("DEMOTED item", prior_demoted=True),      # idx 3 — pinned
        _make_item("C mid weight", lobe="lobe_c"),           # idx 4 — regular
    ]

    allocation = {}  # stub ignores allocation arg
    result = _apply_attention_ordering(items, allocation)

    # Pinned items must stay at their original absolute indices.
    assert result[1]["forced_floor"] is True, "forced_floor must stay at idx 1"
    assert result[3].get("prior_demoted") is True, "prior_demoted must stay at idx 3"

    # Regular slots (0, 2, 4) must be sorted by descending weight:
    # lobe_a (1.0) > lobe_c (0.6) > lobe_b (0.2)
    regular_titles = [result[0]["title"], result[2]["title"], result[4]["title"]]
    assert regular_titles == ["A high weight", "C mid weight", "B low weight"], (
        f"Expected weight-descending order in regular slots, got {regular_titles}"
    )

    # Total length unchanged.
    assert len(result) == len(items)


# ─────────────────────────────────────────────────────────────────────────────
# AW-2: absent/empty allocation → order unchanged
# ─────────────────────────────────────────────────────────────────────────────

def test_aw2_absent_allocation_unchanged(monkeypatch):
    """When attention module absent, items are returned in original order."""
    # Remove the attention module if it's present.
    monkeypatch.setitem(sys.modules, "engine.metabolism.attention",
                        None)  # type: ignore[arg-type]

    from engine.metabolism.agenda import _apply_attention_ordering

    items = [
        _make_item("first", lobe="lobe_a"),
        _make_item("second", lobe="lobe_b"),
    ]
    result = _apply_attention_ordering(items, None)
    assert [i["title"] for i in result] == ["first", "second"]


def test_aw2b_empty_allocation_unchanged(monkeypatch):
    """With empty allocation dict, items are returned in original order."""
    _inject_attention(monkeypatch, weight_map={})  # all lobes → 0.6 (same weight)

    from engine.metabolism.agenda import _apply_attention_ordering

    items = [
        _make_item("X", lobe="lobe_x"),
        _make_item("Y", lobe="lobe_y"),
    ]
    original_order = [i["title"] for i in items]
    result = _apply_attention_ordering(items, {})
    # All equal weight → stable sort preserves original order.
    assert [i["title"] for i in result] == original_order


# ─────────────────────────────────────────────────────────────────────────────
# AW-3: never raises on junk allocation
# ─────────────────────────────────────────────────────────────────────────────

def test_aw3_never_raises_junk(monkeypatch):
    """_apply_attention_ordering never raises on malformed inputs."""
    _inject_attention(monkeypatch)

    from engine.metabolism.agenda import _apply_attention_ordering

    # Junk allocation — function must not raise.
    result = _apply_attention_ordering(
        [_make_item("item", lobe="x")],
        {"this": "is", "junk": 42},
    )
    assert len(result) == 1

    # None items list.
    result2 = _apply_attention_ordering([], None)
    assert result2 == []

    # Item with no target_lobe.
    result3 = _apply_attention_ordering(
        [_make_item("no_lobe", lobe=None)], {}
    )
    assert len(result3) == 1


# ─────────────────────────────────────────────────────────────────────────────
# AW-4: agenda trim — lowest-weight regular items trimmed first;
#        forced-floor and demoted visibility invariants hold.
# ─────────────────────────────────────────────────────────────────────────────

def test_aw4_trim_lowest_weight_first(monkeypatch, tmp_path):
    """When over max_docket_size, regular items with lowest attention are trimmed."""
    _inject_attention(monkeypatch, weight_map={
        "lobe_hi": 1.0,
        "lobe_lo": 0.0,  # DORMANT weight
    })

    from engine.metabolism.agenda import _build_agenda_inner

    root = _tmp_root(tmp_path)

    # Write a budget config that caps at 2.
    budget = {"max_docket_size": 2, "prior_demote_min_n": 5, "prior_demote_hit_rate": 0.25}
    (root / "config" / "metabolism_budget.yml").write_text(
        "max_docket_size: 2\nprior_demote_min_n: 5\nprior_demote_hit_rate: 0.25\n",
        encoding="utf-8",
    )

    # 3 regular items (2 hi, 1 lo), 1 forced-floor — total 4 > cap 2.
    # After trim: forced_floor always kept (1 slot), then 1 regular hi kept,
    # lo regular trimmed.
    raw_items = [
        {"title": "lo weight item", "bucket": "NOVEL_BUILD", "severity": "low",
         "target_lobe": "lobe_lo", "rationale": ""},
        {"title": "hi weight item 1", "bucket": "NOVEL_BUILD", "severity": "low",
         "target_lobe": "lobe_hi", "rationale": ""},
        {"title": "hi weight item 2", "bucket": "NOVEL_BUILD", "severity": "low",
         "target_lobe": "lobe_hi", "rationale": ""},
    ]
    floor_item_summary = "CRITICAL floor trigger"
    floor_row = {
        "insight_id": "i-001",
        "severity": "high",
        "kind": "anomaly",
        "summary": floor_item_summary,
        "entities": ["lobe_hi"],
        "emitter": "test",
        "evidence_ref": "none",
    }

    # Patch everything that _build_agenda_inner touches externally.
    with patch("engine.metabolism.agenda.get_open_rows", return_value=[floor_row]), \
         patch("engine.metabolism.agenda.build_organism_state", return_value={}), \
         patch("engine.metabolism.agenda._build_orchestrator_system", return_value="sys"), \
         patch("engine.metabolism.agenda._call_llm", return_value=(
             json.dumps({"items": raw_items}), None, "mock"
         )), \
         patch("engine.metabolism.agenda._load_killed_topics", return_value=set()), \
         patch("engine.metabolism.agenda._load_active_build_hashes", return_value=set()):
        result = _build_agenda_inner(
            cycle_id="test-trim",
            root=root,
            providers=[{"provider": "mock"}],
            model="test",
            max_docket_size=2,
        )

    items = result["items"]
    titles = [i["title"] for i in items]

    # Forced-floor item must be present.
    assert any(i.get("forced_floor") for i in items), "forced-floor item must survive trim"

    # 'lo weight item' must be trimmed (lowest attention weight).
    assert "lo weight item" not in titles, (
        f"Lowest-weight item should be trimmed, but got: {titles}"
    )

    # Cap must be respected.
    assert len(items) <= 2, f"Expected at most 2 items, got {len(items)}: {titles}"


# ─────────────────────────────────────────────────────────────────────────────
# AW-5: orchestrator_brain Part 5h — "Attention Allocation" section present;
#        FOCUS lobes listed when fixture file present.
# ─────────────────────────────────────────────────────────────────────────────

def test_aw5_system_prompt_contains_allocation_section(tmp_path):
    """System prompt contains 'Attention Allocation' with FOCUS lobes from fixture."""
    root = _tmp_root(tmp_path)

    # Write a fixture allocation file.
    alloc = {
        "schema": "metabolism.attention.v1",
        "cycle_id": "test-cycle",
        "as_of": "2026-07-12",
        "generated_by": "metabolism_attention",
        "provider": "mock",
        "degraded_reason": None,
        "allocations": {
            "world-state": {"band": "FOCUS", "weight": 1.0, "structural_band": "CRITICAL",
                            "llm_band": "FOCUS", "floored": False, "rationale": "core NW feeder"},
            "til": {"band": "STANDARD", "weight": 0.6, "structural_band": "HIGH",
                    "llm_band": "STANDARD", "floored": False, "rationale": "active"},
            "ancillary-display": {"band": "DORMANT", "weight": 0.0,
                                  "structural_band": "ANCILLARY",
                                  "llm_band": "DORMANT", "floored": False,
                                  "rationale": "no NW consumers"},
        },
        "focus_lobes": ["world-state"],
        "authority": {"is_context_only": True},
    }
    alloc_path = root / "data" / "metabolism" / "attention_allocation.json"
    alloc_path.parent.mkdir(parents=True, exist_ok=True)
    alloc_path.write_text(json.dumps(alloc), encoding="utf-8")

    from engine.metabolism.orchestrator_brain import _build_orchestrator_system

    prompt = _build_orchestrator_system(model="test", role="orchestrator", root=root)

    assert "Attention Allocation" in prompt, "System prompt must contain 'Attention Allocation'"
    assert "FOCUS" in prompt, "FOCUS band must appear in prompt"
    assert "world-state" in prompt, "FOCUS lobe id must appear in prompt"
    assert "DORMANT" in prompt, "DORMANT band must appear in prompt"
    assert "ancillary-display" in prompt, "DORMANT lobe id must appear in prompt"


# ─────────────────────────────────────────────────────────────────────────────
# AW-6: absent allocation file → "(attention allocation absent — accruing)"
# ─────────────────────────────────────────────────────────────────────────────

def test_aw6_absent_allocation_fallback(tmp_path):
    """With no attention_allocation.json, prompt shows the 'absent' message."""
    root = _tmp_root(tmp_path)
    # Ensure no allocation file exists.
    alloc_path = root / "data" / "metabolism" / "attention_allocation.json"
    if alloc_path.exists():
        alloc_path.unlink()

    from engine.metabolism.orchestrator_brain import _build_orchestrator_system

    prompt = _build_orchestrator_system(model="test", role="orchestrator", root=root)

    assert "Attention Allocation" in prompt
    assert "attention allocation absent" in prompt.lower(), (
        f"Expected 'attention allocation absent' in prompt, got excerpt: "
        f"{prompt[prompt.find('Attention Allocation'):prompt.find('Attention Allocation')+200]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AW-7: propose skip path — DORMANT lobe writes empty docket, no LLM call
# ─────────────────────────────────────────────────────────────────────────────

def test_aw7_dormant_skip_writes_empty_docket(monkeypatch, tmp_path):
    """When attention.propose_skip returns (True, 'attention_dormant'), _run_all_lobes
    writes an empty docket for that lobe and makes no LLM call."""
    root = _tmp_root(tmp_path)

    # Stub attention: 'dormant-lobe' is DORMANT, 'til' is STANDARD.
    _inject_attention(monkeypatch, band_map={
        "dormant-lobe": "DORMANT",
        "til": "STANDARD",
    })

    # Write a minimal lobe_charters.yml so _discover_loop_managed_lobes finds lobes.
    charters = {
        "charters": {
            "til": {
                "lifecycle_state": "active",
                "fitness_sensors": [{"id": "ic", "store": "s"}],
            },
            "dormant-lobe": {
                "lifecycle_state": "active",
                "fitness_sensors": [{"id": "ic", "store": "s"}],
            },
        }
    }
    import yaml  # type: ignore[import]
    (root / "config" / "lobe_charters.yml").write_text(
        yaml.dump(charters), encoding="utf-8",
    )

    # Track LLM calls — should NEVER fire for 'dormant-lobe'.
    _llm_called_lobes: list[str] = []

    def _fake_run_single_lobe(args, _root, lobe, cycle_id):
        _llm_called_lobes.append(lobe)

    import scripts.metabolism_propose as _propose_mod
    monkeypatch.setattr(_propose_mod, "_run_single_lobe", _fake_run_single_lobe)

    # Also stub journal to not require filesystem.
    monkeypatch.setitem(
        sys.modules,
        "scripts.metabolism_journal",
        _stub_journal_module(),
    )

    import argparse
    args = argparse.Namespace(
        cycle_id="test-dormant-001",
        root=str(root),
        today=None,
        max_docket_size=None,
        lane="test",
        all_lobes=True,
        dry_run=True,
    )

    from scripts.metabolism_propose import _run_all_lobes
    _run_all_lobes(args, root)

    # 'til' was dispatched normally.
    assert "til" in _llm_called_lobes, "til should have run normally"
    # 'dormant-lobe' was NOT dispatched (attention skip).
    assert "dormant-lobe" not in _llm_called_lobes, (
        "dormant-lobe should have been skipped via attention gate"
    )

    # Empty docket file must exist for dormant-lobe.
    docket_path = root / "data" / "metabolism" / "dockets" / "test-dormant-001-dormant-lobe.json"
    assert docket_path.exists(), (
        f"Empty docket must be written for dormant-lobe skip, expected at {docket_path}"
    )
    docket = json.loads(docket_path.read_text(encoding="utf-8"))
    assert docket.get("schema") == "metabolism.docket.v1"
    assert docket.get("proposals") == [] or docket.get("proposals") is None or \
           len(docket.get("proposals", [])) == 0, "Empty docket must have no proposals"
    assert "attention_dormant" in str(docket.get("degraded_reason", "")), (
        f"degraded_reason must note attention skip, got: {docket.get('degraded_reason')}"
    )


def _stub_journal_module() -> types.ModuleType:
    """Return a minimal stub for scripts.metabolism_journal."""
    m = types.ModuleType("scripts.metabolism_journal")

    def new_cycle_id():
        return "stub-cycle-001"

    def start_stage(cycle_id, stage, root=None):
        pass

    def finish_stage(cycle_id, stage, status, *, note=None, artifacts=None,
                     next_stage=None, root=None):
        pass

    m.new_cycle_id = new_cycle_id
    m.start_stage = start_stage
    m.finish_stage = finish_stage
    return m


# ─────────────────────────────────────────────────────────────────────────────
# AW-8: exemption path (False, "urgent_fix_exemption") runs single-lobe normally
# ─────────────────────────────────────────────────────────────────────────────

def test_aw8_exemption_runs_normally(monkeypatch, tmp_path):
    """When propose_skip returns (False, 'urgent_fix_exemption'), the lobe runs normally."""
    root = _tmp_root(tmp_path)

    # All lobes have propose_skip = (False, "urgent_fix_exemption")
    stub = _make_attention_module()

    def _skip_override(lobe_id, root=None, allocation=None):
        return False, "urgent_fix_exemption"

    stub.propose_skip = _skip_override
    monkeypatch.setitem(sys.modules, "engine.metabolism.attention", stub)

    charters = {
        "charters": {
            "til": {
                "lifecycle_state": "active",
                "fitness_sensors": [{"id": "ic", "store": "s"}],
            },
        }
    }
    import yaml
    (root / "config" / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")

    _called: list[str] = []

    def _fake_run_single_lobe(args, _root, lobe, cycle_id):
        _called.append(lobe)

    import scripts.metabolism_propose as _pm
    monkeypatch.setattr(_pm, "_run_single_lobe", _fake_run_single_lobe)
    monkeypatch.setitem(sys.modules, "scripts.metabolism_journal", _stub_journal_module())

    import argparse
    args = argparse.Namespace(
        cycle_id="test-exempt-001", root=str(root), today=None,
        max_docket_size=None, lane="test", all_lobes=True, dry_run=True,
    )
    from scripts.metabolism_propose import _run_all_lobes
    _run_all_lobes(args, root)

    assert "til" in _called, "Exempted lobe must still run single-lobe path"


# ─────────────────────────────────────────────────────────────────────────────
# AW-9: build dispatch ordering — FOCUS first, adjudication order preserved
#        within band, zero rows dropped.
#
# HONESTY NOTE (review 2026-07-12): production dockets are single-lobe today
# (propose.py stamps the docket-level lobe on every proposal), so this in-lane
# sort is DEFENSE-IN-DEPTH for a future multi-lobe docket shape.  The live
# R-V9-9 enforcement point is attention.rank_cycle_ids — the scheduled BUILD
# workflow's pick among open propose branches (tested in
# tests/test_metabolism_attention.py::TestRankCycleIds).
# ─────────────────────────────────────────────────────────────────────────────

def test_aw9_dispatch_ordering(monkeypatch, tmp_path):
    """In-lane sort mechanism: FOCUS lobe rows first; within same band
    adjudication order preserved; zero rows dropped.  (Multi-lobe docket is
    synthetic — see honesty note above.)"""
    _inject_attention(monkeypatch, priority_map={
        "lobe_focus": 0,     # FOCUS
        "lobe_std_a": 1,     # STANDARD
        "lobe_std_b": 1,     # STANDARD
        "lobe_maint": 2,     # MAINTENANCE
    })

    # Build a synthetic docket with 4 proposals in adjudication order:
    # std_b, focus, maint, std_a
    docket = {
        "schema": "metabolism.docket.v1",
        "cycle_id": "test-build-001",
        "lobe": "lobe_std_a",
        "proposals": [
            {"proposal_id": "p-std-b",  "lobe": "lobe_std_b",  "title": "std b",  "target_files": []},
            {"proposal_id": "p-focus",  "lobe": "lobe_focus",  "title": "focus",  "target_files": []},
            {"proposal_id": "p-maint",  "lobe": "lobe_maint",  "title": "maint",  "target_files": []},
            {"proposal_id": "p-std-a",  "lobe": "lobe_std_a",  "title": "std a",  "target_files": []},
        ],
    }
    docket_path = tmp_path / "dockets" / "test-build-001.json"
    docket_path.parent.mkdir(parents=True, exist_ok=True)
    docket_path.write_text(json.dumps(docket), encoding="utf-8")

    # Track dispatch order.
    _dispatched_order: list[str] = []

    def _fake_two_key_granted(cycle_id, pid, dp, root=None):
        return True  # all granted

    def _fake_is_construction_parked(prop, root=None):
        return False

    def _fake_find_reject(pid, root=None):
        return None

    def _fake_claim(cycle_id, pid, lobe, target_files, root=None, dry_run=False):
        return {"claimed": True, "collision_files": [], "ts": ""}

    def _fake_create_wt(branch, root=None, dry_run=False):
        return {"wt_path": str(tmp_path / "wt"), "error": None}

    def _fake_dispatch(proposal, wt_path, branch, cap_id, cycle_id=None,
                       target_files=None, root=None, dry_run=False, remediation=None):
        _dispatched_order.append(proposal.get("proposal_id", "?"))
        return {"dispatched": True, "reason": "dispatched"}

    def _fake_open_pr(branch, cycle_id, proposal, dry_run=False):
        return {"opened": False, "stub": True}

    def _fake_gc(branch, root=None):
        pass

    def _fake_pick_key(root=None, exclude=None):
        return "cap-test"

    import scripts.metabolism_build as _bm

    with patch.object(_bm, "_is_paused", return_value=False), \
         patch.object(_bm, "_is_two_key_granted", _fake_two_key_granted), \
         patch.object(_bm, "_is_construction_parked", _fake_is_construction_parked), \
         patch.object(_bm, "_find_reject_for_proposal", _fake_find_reject), \
         patch.object(_bm, "claim_proposal", _fake_claim), \
         patch.object(_bm, "_build_branch_name", return_value="metabolism/build-test"), \
         patch.object(_bm, "_create_build_worktree", _fake_create_wt), \
         patch.object(_bm, "_dispatch_build_session", _fake_dispatch), \
         patch.object(_bm, "_open_draft_pr", _fake_open_pr), \
         patch.object(_bm, "_gc_worktree", _fake_gc), \
         patch.object(_bm, "_pick_build_key", _fake_pick_key):
        # Also stub the stale-running sweep.
        with patch("scripts.metabolism_gc.sweep_stale_running_markers",
                   return_value={"swept": 0}, create=True):
            from scripts.metabolism_build import run_build_lane
            results = run_build_lane(
                "test-build-001",
                str(docket_path),
                root=tmp_path,
                dry_run=False,
            )

    # Verify no rows dropped.
    assert len(_dispatched_order) == 4, (
        f"Expected 4 dispatched proposals, got {len(_dispatched_order)}: {_dispatched_order}"
    )

    # Verify FOCUS first.
    assert _dispatched_order[0] == "p-focus", (
        f"FOCUS lobe must be dispatched first, got {_dispatched_order[0]}"
    )

    # Verify MAINTENANCE last.
    assert _dispatched_order[-1] == "p-maint", (
        f"MAINTENANCE lobe must be dispatched last, got {_dispatched_order[-1]}"
    )

    # Within STANDARD band: adjudication order preserved (std_b before std_a).
    std_positions = {pid: i for i, pid in enumerate(_dispatched_order)}
    assert std_positions["p-std-b"] < std_positions["p-std-a"], (
        "Within STANDARD band, original adjudication order (std_b before std_a) must hold"
    )
