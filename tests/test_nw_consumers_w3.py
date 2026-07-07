"""tests/test_nw_consumers_w3.py — W3 consumer integration tests.

Covers:
 1.  daily_brief why_the_tape_moved — pathway case (primary + alternates)
 2.  daily_brief why_the_tape_moved — no_pathway case (honest reason)
 3.  daily_brief why_the_tape_moved — absent artifact case (honest placeholder)
 4.  daily_brief stale enrichment — support_impact embed from health.json
 5.  daily_brief stale enrichment — absent support_impact is a no-op
 6.  ask_brain whitelist includes read_mechanism_pathways
 7.  ask_brain dispatch — absent artifact → structured gap (not error)
 8.  ask_brain dispatch — present artifact → is_context_only always true
 9.  ask_brain dispatch — refuses write-like tool name
 10. cortex _READ_TOOLS includes read_mechanism_pathways
 11. cortex _tool_schemas includes read_mechanism_pathways schema entry
 12. cortex dispatch — absent artifact → structured gap
 13. admin _section_mechanism_pathways — present artifact → required keys
 14. admin _section_mechanism_pathways — absent artifact → available=False
 15. admin _section_mechanism_pathways — history tail emission mix
 16. admin panel() includes mechanism_pathways key
 17. admin no engine imports (static check)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_MP_SCHEMA = "neuralweb.mechanism_pathways.v1"


def _make_mp_artifact(
    tmp_path: Path,
    *,
    has_pathway: bool = True,
    no_pathway_reason: str | None = None,
    family: str = "real_rate_shock",
    direction_en: str = "rates rising",
    coverage_score: float | None = 0.75,
    coverage_basis: str | None = None,
    coherence: str = "supported",
    stale_legs: list[str] | None = None,
    nodes: list[dict] | None = None,
    alternates: list[dict] | None = None,
) -> dict:
    """Write mechanism_pathways.json into tmp_path and return the artifact."""
    stale_legs = stale_legs or []
    nodes = nodes or []
    alternates = alternates or []

    pathways: list[dict] = []
    if has_pathway:
        pw = {
            "family": family,
            "driver": family,
            "pathway_role": "primary",
            "as_of": "2026-07-06",
            "direction_en": direction_en,
            "direction_zh": "",
            "confidence_ceiling": "context_only",
            "coverage_score": coverage_score,
            "coherence": coherence,
            "stale_legs": stale_legs,
            "nodes": nodes,
            "edges": [],
        }
        if coverage_basis is not None:
            pw["coverage_basis"] = coverage_basis
        pathways.append(pw)
        pathways.extend(alternates)

    artifact: dict = {
        "schema": _MP_SCHEMA,
        "as_of": "2026-07-06",
        "display_only": True,
        "not_a_signal": True,
        "authority": {"tier": "display", "display_only": True},
        "pathways": pathways,
    }
    if no_pathway_reason is not None:
        artifact["no_pathway"] = {"reason": no_pathway_reason, "printed": True}

    dest = tmp_path / "data" / "neuralweb" / "mechanism_pathways.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(artifact), encoding="utf-8")
    return artifact


def _make_health_with_stale(
    tmp_path: Path,
    *,
    lobe_id: str = "regime-latest",
    support_impact: dict | None = None,
) -> dict:
    """Write health.json with one stale lobe (optionally with support_impact)."""
    lobe: dict = {
        "id": lobe_id,
        "status": "stale",
        "as_of": "2026-07-01T00:00:00+00:00",
        "age_hours": 120.0,
        "freshness_sla_hours": 30,
    }
    if support_impact is not None:
        lobe["support_impact"] = support_impact

    h = {
        "schema": "neuralweb.health.v1",
        "as_of": "2026-07-06T09:00:00+00:00",
        "overall_status": "warn",
        "lobes": [lobe],
        "cortex": {"status": "fresh", "run_status": {}},
        "workflow_conformance_misses": [],
        "summary_counts": {
            "total_lobes": 1, "fresh": 0, "stale": 1,
            "fresh_partial": 0, "missing": 0, "degraded": 0,
            "not_locally_verifiable": 0, "unknown": 0, "cortex_status": "fresh",
        },
    }
    dest = tmp_path / "data" / "neuralweb" / "health.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(h), encoding="utf-8")
    return h


def _minimal_root(tmp_path: Path) -> Path:
    """Create required directory skeleton."""
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# 1–3. daily_brief why_the_tape_moved section
# ---------------------------------------------------------------------------

def test_why_the_tape_moved_pathway_case(tmp_path):
    """With a valid pathway, why_the_tape_moved.available=True and primary block present."""
    from engine.neuralweb.daily_brief import (
        _load_mechanism_pathways,
        _build_why_the_tape_moved,
    )
    _make_mp_artifact(
        tmp_path,
        nodes=[
            {"node_id": "leg_0", "pathway_role": "required_leg", "entity": "2y_treasury"},
            {"node_id": "leg_1", "pathway_role": "required_leg", "entity": "real_yield"},
        ],
        alternates=[
            {"family": "credit_stress", "driver": "credit_stress", "pathway_role": "alternate",
             "direction_en": "credit widening", "coverage_score": 0.5, "coherence": "partial",
             "stale_legs": [], "nodes": [], "edges": []},
        ],
    )
    mp = _load_mechanism_pathways(tmp_path)
    assert mp is not None
    section = _build_why_the_tape_moved(mp)

    assert section["available"] is True
    primary = section["primary"]
    assert primary["family"] == "real_rate_shock"
    assert primary["direction"] == "rates rising"
    assert primary["coverage"] == 0.75
    assert primary["coherence"] == "supported"
    assert primary["stale_legs_count"] == 0
    assert "2y_treasury" in primary["evidence_legs"]
    assert "real_yield" in primary["evidence_legs"]
    assert "credit_stress" in section["alternates"]


def test_why_the_tape_moved_no_pathway_case(tmp_path):
    """When pathways is empty, why_the_tape_moved shows no_pathway reason honestly."""
    from engine.neuralweb.daily_brief import (
        _load_mechanism_pathways,
        _build_why_the_tape_moved,
    )
    _make_mp_artifact(
        tmp_path,
        has_pathway=False,
        no_pathway_reason="no_attributable_driver",
    )
    mp = _load_mechanism_pathways(tmp_path)
    section = _build_why_the_tape_moved(mp)

    assert section["available"] is True
    assert "no_pathway" in section
    assert section["no_pathway"]["reason"] == "no_attributable_driver"
    assert "no_attributable_driver" in section.get("note", "")


def test_why_the_tape_moved_absent_artifact(tmp_path):
    """When mechanism_pathways.json is absent, section returns available=False with honest note."""
    from engine.neuralweb.daily_brief import (
        _load_mechanism_pathways,
        _build_why_the_tape_moved,
    )
    # Do NOT write the artifact
    mp = _load_mechanism_pathways(tmp_path)
    assert mp is None
    section = _build_why_the_tape_moved(mp)

    assert section["available"] is False
    assert "note" in section
    assert "not yet" in section["note"].lower()


def test_build_includes_why_the_tape_moved(tmp_path):
    """build() always includes why_the_tape_moved key regardless of artifact presence."""
    from engine.neuralweb.daily_brief import build

    _minimal_root(tmp_path)
    # No artifact — should still include the key
    result = build(root=tmp_path)
    assert "why_the_tape_moved" in result

    # With artifact
    _make_mp_artifact(tmp_path)
    result2 = build(root=tmp_path)
    assert "why_the_tape_moved" in result2
    assert result2["why_the_tape_moved"]["available"] is True


def test_why_the_tape_moved_coverage_basis_scare(tmp_path):
    """Scare-trigger pathways (coverage_score=null, coverage_basis='scare_trigger') display basis."""
    from engine.neuralweb.daily_brief import _load_mechanism_pathways, _build_why_the_tape_moved

    _make_mp_artifact(
        tmp_path,
        coverage_score=None,
        coverage_basis="scare_trigger",
    )
    mp = _load_mechanism_pathways(tmp_path)
    section = _build_why_the_tape_moved(mp)

    assert section["available"] is True
    assert section["primary"]["coverage"] == "scare_trigger"


# ---------------------------------------------------------------------------
# 4–5. daily_brief stale enrichment with support_impact
# ---------------------------------------------------------------------------

def test_stale_enrichment_with_support_impact(tmp_path):
    """Stale lobes with support_impact get a support_impact_note appended."""
    from engine.neuralweb.daily_brief import _build_stale, _enrich_stale_with_support_impact

    health = _make_health_with_stale(
        tmp_path,
        lobe_id="regime-latest",
        support_impact={
            "downstream_count": 3,
            "direct_consumers": ["daily_brief.py", "committee.html.j2", "ask_brain.py"],
        },
    )

    stale = _build_stale(health)
    assert any(s["id"] == "regime-latest" for s in stale)

    enriched = _enrich_stale_with_support_impact(stale, health)
    stale_item = next(s for s in enriched if s["id"] == "regime-latest")
    assert "support_impact_note" in stale_item
    note = stale_item["support_impact_note"]
    assert "3 downstream" in note
    assert "daily_brief.py" in note
    # cap at 3 names
    assert note.count(",") <= 2


def test_stale_enrichment_absent_support_impact(tmp_path):
    """Stale lobes without support_impact are returned unchanged."""
    from engine.neuralweb.daily_brief import _build_stale, _enrich_stale_with_support_impact

    health = _make_health_with_stale(tmp_path, lobe_id="some-lobe")

    stale = _build_stale(health)
    enriched = _enrich_stale_with_support_impact(stale, health)

    # No crash; support_impact_note not present
    for item in enriched:
        assert "support_impact_note" not in item


def test_stale_enrichment_no_health(tmp_path):
    """_enrich_stale_with_support_impact is a no-op when health is None."""
    from engine.neuralweb.daily_brief import _enrich_stale_with_support_impact

    stale = [{"id": "x", "severity": "warn"}]
    result = _enrich_stale_with_support_impact(stale, None)
    assert result == stale


def test_build_stale_enrichment_integrated(tmp_path):
    """build() enriches stale lobes with support_impact_note when health has the embed."""
    from engine.neuralweb.daily_brief import build

    _minimal_root(tmp_path)
    _make_health_with_stale(
        tmp_path,
        lobe_id="regime-latest",
        support_impact={"downstream_count": 2, "direct_consumers": ["a.py", "b.py"]},
    )
    result = build(root=tmp_path)
    stale = result.get("what_is_stale") or []
    stale_item = next((s for s in stale if s.get("id") == "regime-latest"), None)
    assert stale_item is not None
    assert "support_impact_note" in stale_item


# ---------------------------------------------------------------------------
# 6–9. ask_brain whitelist and dispatch
# ---------------------------------------------------------------------------

def test_ask_brain_whitelist_includes_read_mechanism_pathways():
    """read_mechanism_pathways is in ask_brain._ASK_READ_TOOLS."""
    from engine.neuralweb import ask_brain as ab
    assert "read_mechanism_pathways" in ab._ASK_READ_TOOLS


def test_ask_brain_dispatch_absent_artifact(tmp_path):
    """_dispatch_read_tool('read_mechanism_pathways') with absent file → structured gap."""
    from engine.neuralweb import ask_brain as ab

    result = ab._dispatch_read_tool("read_mechanism_pathways", {}, tmp_path)
    # Must not be a whitelist refusal error
    if "error" in result:
        assert "not allowed" not in result["error"]
    # Must be structured gap
    assert result.get("is_context_only") is True
    assert "gaps" in result or "note" in result


def test_ask_brain_dispatch_present_artifact(tmp_path):
    """_dispatch_read_tool('read_mechanism_pathways') with present file → is_context_only True."""
    from engine.neuralweb import ask_brain as ab

    _make_mp_artifact(tmp_path)
    result = ab._dispatch_read_tool("read_mechanism_pathways", {}, tmp_path)
    assert "error" not in result
    assert result.get("is_context_only") is True
    assert result.get("schema") == _MP_SCHEMA


def test_ask_brain_dispatch_refuses_write_tool_for_mechanism(tmp_path):
    """A hypothetical write tool is refused regardless of 'mechanism' in the name."""
    from engine.neuralweb import ask_brain as ab

    result = ab._dispatch_read_tool("write_mechanism_pathways", {}, tmp_path)
    assert "error" in result
    assert "not allowed" in result["error"]


# ---------------------------------------------------------------------------
# 10–12. cortex _READ_TOOLS and dispatch
# ---------------------------------------------------------------------------

def test_cortex_read_tools_includes_read_mechanism_pathways():
    """read_mechanism_pathways is in cortex._READ_TOOLS."""
    from engine.neuralweb import cortex
    assert "read_mechanism_pathways" in cortex._READ_TOOLS


def test_cortex_tool_schemas_includes_read_mechanism_pathways():
    """_tool_schemas() includes a read_mechanism_pathways entry."""
    from engine.neuralweb.cortex import _tool_schemas
    schemas = _tool_schemas()
    names = {s["name"] for s in schemas}
    assert "read_mechanism_pathways" in names
    # Write tools must remain absent
    assert "flag_attention" in names  # write tools live in _tool_schemas() but not _READ_TOOLS  # write tools ARE in _tool_schemas but not in _READ_TOOLS


def test_cortex_dispatch_absent_artifact(tmp_path):
    """cortex _tool_read_mechanism_pathways with absent file → structured gap."""
    from engine.neuralweb.cortex import _tool_read_mechanism_pathways

    result = _tool_read_mechanism_pathways(tmp_path, {})
    assert result.get("is_context_only") is True
    assert "gaps" in result


def test_cortex_dispatch_present_artifact(tmp_path):
    """cortex _tool_read_mechanism_pathways with present file → schema present."""
    from engine.neuralweb.cortex import _tool_read_mechanism_pathways

    _make_mp_artifact(tmp_path)
    result = _tool_read_mechanism_pathways(tmp_path, {})
    assert result.get("schema") == _MP_SCHEMA
    assert result.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 13–16. admin _section_mechanism_pathways and panel()
# ---------------------------------------------------------------------------

def _make_mp_artifact_for_admin(root: Path, *, has_pathway: bool = True) -> None:
    _make_mp_artifact(root, has_pathway=has_pathway,
                      no_pathway_reason=None if has_pathway else "no_attributable_driver")


def _make_mp_history_for_admin(root: Path, rows: list[dict]) -> None:
    dest = root / "data" / "neuralweb" / "mechanism_pathways_history.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _patch_mp_paths(neural_web_mod, root: Path):
    old_json = neural_web_mod._NW_MECHANISM_PATHWAYS_JSON
    old_hist = neural_web_mod._NW_MECHANISM_PATHWAYS_HISTORY_JSONL
    neural_web_mod._NW_MECHANISM_PATHWAYS_JSON = root / "data" / "neuralweb" / "mechanism_pathways.json"
    neural_web_mod._NW_MECHANISM_PATHWAYS_HISTORY_JSONL = root / "data" / "neuralweb" / "mechanism_pathways_history.jsonl"
    return old_json, old_hist


def _restore_mp_paths(neural_web_mod, old_json, old_hist):
    neural_web_mod._NW_MECHANISM_PATHWAYS_JSON = old_json
    neural_web_mod._NW_MECHANISM_PATHWAYS_HISTORY_JSONL = old_hist


def test_admin_section_mechanism_pathways_present(tmp_path):
    """With artifact present, _section_mechanism_pathways returns required keys."""
    from admin import neural_web

    _make_mp_artifact_for_admin(tmp_path)
    old_json, old_hist = _patch_mp_paths(neural_web, tmp_path)
    try:
        section = neural_web._section_mechanism_pathways()
    finally:
        _restore_mp_paths(neural_web, old_json, old_hist)

    assert section["available"] is True
    assert "current" in section
    assert "history_emission_mix" in section
    cur = section["current"]
    assert cur["has_pathway"] is True
    assert cur["primary_family"] == "real_rate_shock"
    assert cur["coherence"] == "supported"
    assert isinstance(cur["stale_legs"], list)
    assert cur["stale_legs_count"] == 0


def test_admin_section_mechanism_pathways_absent(tmp_path):
    """With artifact absent, _section_mechanism_pathways returns available=False."""
    from admin import neural_web

    old_json, old_hist = _patch_mp_paths(neural_web, tmp_path)
    try:
        section = neural_web._section_mechanism_pathways()
    finally:
        _restore_mp_paths(neural_web, old_json, old_hist)

    assert section["available"] is False
    assert "note" in section


def test_admin_section_mechanism_pathways_history_mix(tmp_path):
    """History tail emission mix counts pathway vs no_pathway rows correctly."""
    from admin import neural_web

    _make_mp_artifact_for_admin(tmp_path)
    # 5 pathway rows + 3 no_pathway rows
    history_rows = (
        [{"as_of": f"2026-07-0{i}", "schema": _MP_SCHEMA, "pathways_count": 1, "primary_family": "real_rate_shock", "no_pathway_reason": None} for i in range(1, 6)]
        + [{"as_of": f"2026-07-0{i}", "schema": _MP_SCHEMA, "pathways_count": 0, "primary_family": None, "no_pathway_reason": "no_attributable_driver"} for i in range(6, 9)]
    )
    _make_mp_history_for_admin(tmp_path, history_rows)

    old_json, old_hist = _patch_mp_paths(neural_web, tmp_path)
    try:
        section = neural_web._section_mechanism_pathways()
    finally:
        _restore_mp_paths(neural_web, old_json, old_hist)

    mix = section["history_emission_mix"]
    assert mix["available"] is True
    assert mix["tail_rows"] == 8
    assert mix["pathway_count"] == 5
    assert mix["no_pathway_count"] == 3
    assert "no_attributable_driver" in mix["no_pathway_reasons"]
    assert mix["no_pathway_reasons"]["no_attributable_driver"] == 3


def test_admin_panel_includes_mechanism_pathways():
    """panel() returns a mechanism_pathways key at top level."""
    from admin import neural_web

    d = neural_web.panel()
    assert "mechanism_pathways" in d, "Missing mechanism_pathways section in panel()"
    mp_sec = d["mechanism_pathways"]
    assert "available" in mp_sec


# ---------------------------------------------------------------------------
# 17. admin no engine imports (W3 additions)
# ---------------------------------------------------------------------------

def test_no_engine_imports_w3():
    """admin/neural_web.py additions in W3 must not add bare engine/scripts imports."""
    src = (Path(__file__).resolve().parent.parent / "admin" / "neural_web.py").read_text()
    import_lines = [
        line for line in src.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith('"""')
        and not line.strip().startswith("'")
    ]
    code = "\n".join(import_lines)
    forbidden = [
        ("from engine", "engine module import"),
        ("import engine", "engine module import"),
        ("from scripts", "scripts module import"),
        ("import scripts", "scripts module import"),
        ("subprocess.run", "subprocess.run call"),
        ("subprocess.Popen", "subprocess.Popen call"),
        ("import subprocess", "subprocess import"),
    ]
    for pattern, label in forbidden:
        assert pattern not in code, f"Forbidden {label!r} found in non-comment lines"
