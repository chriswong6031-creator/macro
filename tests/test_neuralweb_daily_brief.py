"""tests/test_neuralweb_daily_brief.py — Unit tests for engine.neuralweb.daily_brief (PR-D).

Covers BUILD CONTRACT:
 1.  First run without prior history — what_changed contains first_run record
 2.  Cortex degraded → P1 operator_attention + status degraded
 3.  Stale lobe from health fixture → what_is_stale populated
 4.  Contradiction id disappearing → delta_vs_prior no_longer_present
     and the word 'resolved' is ABSENT from all produced strings
 5.  Contradiction count increase → P2 operator_attention
 6.  Bottom-sensor as_of advance → what_changed lobe_refresh
 7.  --finalize upserts history idempotently (run twice same as_of → one row)
 8.  phase field engine vs final
 9.  NO trading verbs in any produced string (verb blacklist)
 10. site copy written alongside data copy
 11. Malformed/missing inputs → gaps + exit 0
 12. qi never read (world_state fixture with qi sentinel → assert untouched/absent)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.daily_brief import (  # noqa: E402
    TRADING_VERBS,
    _brief_status,
    _build_brain_run,
    _contradiction_delta,
    _detect_changes,
    _load_contradictions,
    build,
    upsert_history,
    write,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_health(
    tmp_path: Path,
    *,
    overall_status: str = "ok",
    cortex_status: str = "fresh",
    cortex_degraded: bool = False,
    lobes: list[dict] | None = None,
    conformance_misses: list[dict] | None = None,
) -> dict:
    cortex_run_status = {
        "degraded": cortex_degraded,
        "degradation_reason": "zero_tool_calls" if cortex_degraded else None,
        "tool_call_batches": 0 if cortex_degraded else 2,
        "individual_tool_calls": 0 if cortex_degraded else 18,
        "context_stale": False,
    }
    h = {
        "schema": "neuralweb.health.v1",
        "produced_at": "2026-07-06T10:00:00+00:00",
        "as_of": "2026-07-06T09:00:00+00:00",
        "overall_status": overall_status,
        "lobes": lobes or [],
        "cortex": {
            "cortex_source": "current_run",
            "status": cortex_status,
            "memo_as_of": "2026-07-06T08:00:00+00:00",
            "run_status": cortex_run_status,
        },
        "workflow_conformance_misses": conformance_misses or [],
        "summary_counts": {
            "total_lobes": len(lobes or []),
            "fresh": 0,
            "fresh_partial": 0,
            "stale": 0,
            "missing": 0,
            "degraded": 0,
            "not_locally_verifiable": 0,
            "unknown": 0,
            "cortex_status": cortex_status,
        },
    }
    p = tmp_path / "data" / "neuralweb" / "health.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(h), encoding="utf-8")
    return h


def _make_world_state(tmp_path: Path, *, extra_keys: dict | None = None) -> dict:
    ws = {
        "as_of": "2026-07-06T09:00:00+00:00",
        "live_overlay": {"stale": False},
        "regime": {"quad": "goldilocks"},
    }
    if extra_keys:
        ws.update(extra_keys)
    p = tmp_path / "data" / "neuralweb" / "world_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ws), encoding="utf-8")
    return ws


def _make_graph(tmp_path: Path, contradiction_records: list[dict] | None = None) -> dict:
    g = {
        "contradiction_records": contradiction_records or [],
        "contradiction_summary": {
            "count": len(contradiction_records or []),
        },
    }
    p = tmp_path / "site" / "neuralwebdata" / "confluence_graph.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(g), encoding="utf-8")
    return g


def _make_mastermind_context(tmp_path: Path) -> dict:
    mc = {
        "as_of": "2026-07-06T09:00:00+00:00",
        "lobes": {
            "contradictions": {"records": [], "count": 0},
        },
    }
    p = tmp_path / "data" / "neuralweb" / "mastermind_context.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mc), encoding="utf-8")
    return mc


def _make_cortex_memo(tmp_path: Path, *, degraded: bool = False) -> dict:
    memo = {
        "as_of": "2026-07-06T08:00:00+00:00",
        "run_status": {
            "degraded": degraded,
            "degradation_reason": "zero_tool_calls" if degraded else None,
            "tool_call_batches": 0 if degraded else 2,
            "individual_tool_calls": 0 if degraded else 18,
            "context_stale": False,
        },
    }
    p = tmp_path / "data" / "neuralweb" / "cortex" / "memo.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(memo), encoding="utf-8")
    return memo


def _make_minimal_root(tmp_path: Path) -> Path:
    """Create required directories."""
    (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _collect_all_strings(obj: object) -> list[str]:
    """Recursively collect all string values from a nested dict/list."""
    results: list[str] = []
    if isinstance(obj, str):
        results.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_collect_all_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_collect_all_strings(item))
    return results


# ---------------------------------------------------------------------------
# 1. First run without prior history
# ---------------------------------------------------------------------------

def test_first_run_no_history(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)

    assert brief["schema"] == "neuralweb.daily_brief.v1"
    assert brief["phase"] == "engine"
    kinds = [c["kind"] for c in brief["what_changed"]]
    assert "first_run" in kinds, f"Expected first_run in what_changed, got: {kinds}"


# ---------------------------------------------------------------------------
# 2. Cortex degraded → P1 + status degraded
# ---------------------------------------------------------------------------

def test_cortex_degraded_p1(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(
        tmp_path,
        overall_status="degraded",
        cortex_status="degraded",
        cortex_degraded=True,
    )
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path, degraded=True)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)

    assert brief["status"] == "degraded"
    p1_items = [a for a in brief["operator_attention"] if a["priority"] == 1]
    areas = [a["area"] for a in p1_items]
    assert "cortex" in areas, f"Expected cortex P1, got attention areas: {areas}"


# ---------------------------------------------------------------------------
# 3. Stale lobe → what_is_stale populated
# ---------------------------------------------------------------------------

def test_stale_lobe_in_what_is_stale(tmp_path):
    _make_minimal_root(tmp_path)
    stale_lobe = {
        "id": "world-state",
        "path": "data/neuralweb/world_state.json",
        "status": "stale",
        "as_of": "2026-07-04T10:00:00+00:00",
        "age_hours": 48.0,
        "freshness_sla_hours": 30.0,
        "row_count": None,
        "gaps": [],
    }
    _make_health(tmp_path, overall_status="warn", lobes=[stale_lobe])
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)

    stale_ids = [s["id"] for s in brief["what_is_stale"]]
    assert "world-state" in stale_ids, f"Expected world-state in stale list: {stale_ids}"


# ---------------------------------------------------------------------------
# 3b. what_is_stale ordering: SLA breaches first, never buried under
#     never-yet-produced ledgers (kind field: stale > degraded > missing)
# ---------------------------------------------------------------------------

def test_what_is_stale_orders_sla_breach_first(tmp_path):
    """REGRESSION: a genuinely overdue lobe (e.g. nasdaq-internals 72h vs 30h SLA)
    must lead what_is_stale, not sit behind 15 never-yet-existing ledgers with
    SLA 9999 — the template caps display at 3 items, so ordering IS the fix.
    Each item carries kind ('stale'|'degraded'|'missing'); list is sorted
    stale > degraded > missing, most-overdue first within 'stale'."""
    _make_minimal_root(tmp_path)

    lobes: list[dict] = []
    # 15 placeholder ledgers that have never been produced (SLA 9999)
    for i in range(15):
        lobes.append({
            "id": f"never-built-ledger-{i:02d}",
            "path": f"data/neuralweb/never_{i:02d}.jsonl",
            "status": "missing",
            "as_of": None,
            "age_hours": None,
            "freshness_sla_hours": 9999,
            "row_count": None,
            "gaps": [],
        })
    # One self-reported degraded lobe
    lobes.append({
        "id": "some-degraded-lobe",
        "path": "data/neuralweb/some_degraded.json",
        "status": "degraded",
        "as_of": "2026-07-06T08:00:00+00:00",
        "age_hours": 5.0,
        "freshness_sla_hours": 30.0,
        "row_count": None,
        "gaps": ["degraded: self-reported"],
    })
    # Two genuine SLA breaches — the 72h one must lead the whole list
    lobes.append({
        "id": "mildly-late-lobe",
        "path": "data/neuralweb/mildly_late.json",
        "status": "stale",
        "as_of": "2026-07-05T08:00:00+00:00",
        "age_hours": 40.0,
        "freshness_sla_hours": 30.0,
        "row_count": None,
        "gaps": [],
    })
    lobes.append({
        "id": "nasdaq-internals",
        "path": "site/marketdata/nasdaq_internals.json",
        "status": "stale",
        "as_of": "2026-07-03T08:00:00+00:00",
        "age_hours": 72.0,
        "freshness_sla_hours": 30.0,
        "row_count": None,
        "gaps": [],
    })

    _make_health(tmp_path, overall_status="warn", lobes=lobes)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)
    stale = brief["what_is_stale"]

    # Most-overdue SLA breach leads; missing never buries it
    assert stale[0]["id"] == "nasdaq-internals", [s["id"] for s in stale[:4]]
    assert stale[0]["kind"] == "stale"
    assert stale[1]["id"] == "mildly-late-lobe"
    assert stale[2]["kind"] == "degraded"

    # kind ordering is monotone: stale > degraded > missing
    order = {"stale": 0, "degraded": 1, "missing": 2}
    kinds = [s["kind"] for s in stale]
    assert kinds == sorted(kinds, key=lambda k: order[k]), kinds
    assert kinds.count("stale") == 2
    assert kinds.count("missing") == 15

    # Backward-compatible shape: original keys intact, 'kind' additive
    for s in stale:
        for key in ("id", "as_of", "age_hours", "freshness_sla_hours", "severity", "kind"):
            assert key in s, f"missing key {key!r} in {s}"


# ---------------------------------------------------------------------------
# 4. Contradiction id disappearing → no_longer_present, never 'resolved'
# ---------------------------------------------------------------------------

def test_contradiction_disappears_no_longer_present(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    # Current graph has no contradictions
    _make_graph(tmp_path, contradiction_records=[])
    _make_mastermind_context(tmp_path)

    # Simulate prior snapshot with contradiction C42 present
    prior_snap = {
        "as_of": "2026-07-05T09:00:00+00:00",
        "lobe_status": {},
        "contradiction_count": 1,
        "contradiction_ids": ["C42"],
        "cortex_status": "fresh",
    }

    # Test _contradiction_delta directly
    current_records: list[dict] = []
    delta = _contradiction_delta(current_records, prior_snap)

    no_longer = [d for d in delta if d.get("delta_vs_prior") == "no_longer_present"]
    assert len(no_longer) == 1
    assert no_longer[0]["id"] == "C42"

    # Assert the word 'resolved' never appears
    all_strings = _collect_all_strings(delta)
    for s in all_strings:
        assert "resolved" not in s.lower(), f"Forbidden word 'resolved' found: {s!r}"


# ---------------------------------------------------------------------------
# 5. Contradiction count increase → P2 operator_attention
# ---------------------------------------------------------------------------

def test_contradiction_increase_p2(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)

    # Two contradictions in graph
    records = [
        {"id": "C1", "description": "test contradiction 1", "severity": "note"},
        {"id": "C2", "description": "test contradiction 2", "severity": "note"},
    ]
    _make_graph(tmp_path, contradiction_records=records)
    _make_mastermind_context(tmp_path)

    # Write a prior history with no contradictions
    hist_path = tmp_path / "data" / "neuralweb" / "daily_brief_history.jsonl"
    prior_row = {
        "as_of": "2026-07-05T09:00:00+00:00",
        "produced_at": "2026-07-05T10:00:00+00:00",
        "status": "ok",
        "phase": "final",
        "snapshot": {
            "as_of": "2026-07-05T09:00:00+00:00",
            "lobe_status": {},
            "contradiction_count": 0,
            "contradiction_ids": [],
            "cortex_status": "fresh",
        },
    }
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text(json.dumps(prior_row) + "\n", encoding="utf-8")

    brief = build(root=tmp_path)

    p2_items = [a for a in brief["operator_attention"] if a["priority"] == 2]
    areas = [a["area"] for a in p2_items]
    assert "contradictions" in areas, f"Expected contradictions P2, got: {areas}"


# ---------------------------------------------------------------------------
# 6. Bottom-sensor as_of advance → what_changed lobe_refresh
# ---------------------------------------------------------------------------

def test_lobe_refresh_detected(tmp_path):
    _make_minimal_root(tmp_path)

    fresh_lobe = {
        "id": "bottom-sensors-json",
        "path": "site/neuralwebdata/bottom_sensors.json",
        "status": "fresh",
        "as_of": "2026-07-06T08:00:00+00:00",
        "age_hours": 2.0,
        "freshness_sla_hours": 30.0,
        "row_count": 200,
        "gaps": [],
    }
    _make_health(tmp_path, lobes=[fresh_lobe])
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    # Prior history: same lobe with older as_of and fewer rows
    hist_path = tmp_path / "data" / "neuralweb" / "daily_brief_history.jsonl"
    prior_row = {
        "as_of": "2026-07-05T08:00:00+00:00",
        "produced_at": "2026-07-05T10:00:00+00:00",
        "status": "ok",
        "phase": "final",
        "snapshot": {
            "as_of": "2026-07-05T08:00:00+00:00",
            "lobe_status": {
                "bottom-sensors-json": {
                    "as_of": "2026-07-05T08:00:00+00:00",
                    "status": "fresh",
                    "row_count": 180,
                },
            },
            "contradiction_count": 0,
            "contradiction_ids": [],
            "cortex_status": "fresh",
        },
    }
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text(json.dumps(prior_row) + "\n", encoding="utf-8")

    brief = build(root=tmp_path)

    kinds = [c["kind"] for c in brief["what_changed"]]
    assert "lobe_refresh" in kinds, f"Expected lobe_refresh in what_changed kinds: {kinds}"


# ---------------------------------------------------------------------------
# 7. --finalize upserts history idempotently
# ---------------------------------------------------------------------------

def test_finalize_idempotent(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    payload = build(root=tmp_path, phase="final")
    write(payload, root=tmp_path)

    # Upsert twice with same as_of
    upsert_history(payload, root=tmp_path)
    upsert_history(payload, root=tmp_path)

    hist_path = tmp_path / "data" / "neuralweb" / "daily_brief_history.jsonl"
    rows = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
    as_of = payload.get("as_of")
    matching = [r for r in rows if r.get("as_of") == as_of]
    assert len(matching) == 1, f"Expected exactly 1 row for as_of={as_of}, got {len(matching)}"


# ---------------------------------------------------------------------------
# 8. phase field engine vs final
# ---------------------------------------------------------------------------

def test_phase_field(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    engine_brief = build(root=tmp_path, phase="engine")
    assert engine_brief["phase"] == "engine"

    final_brief = build(root=tmp_path, phase="final")
    assert final_brief["phase"] == "final"


# ---------------------------------------------------------------------------
# 9. NO trading verbs in any produced string
# ---------------------------------------------------------------------------

def test_no_trading_verbs(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)
    all_strings = _collect_all_strings(brief)
    for s in all_strings:
        tokens = s.lower().split()
        for verb in TRADING_VERBS:
            assert verb not in tokens, (
                f"Trading verb '{verb}' found in output string: {s!r}"
            )


# ---------------------------------------------------------------------------
# 9b. Trading verb in upstream contradiction description → scrubbed, not emitted
# ---------------------------------------------------------------------------

def test_trading_verb_in_contradiction_description_is_scrubbed(tmp_path):
    """If an upstream contradiction record carries a trading verb in its description,
    _contradiction_delta must redact it before it enters the artifact.
    The verb must be absent from the produced summary; the record must still appear."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    # Contradiction record whose description contains a trading verb verbatim
    records = [
        {
            "id": "C99",
            "description": "model wants to BUY semis aggressively",
            "severity": "tension",
        }
    ]
    _make_graph(tmp_path, contradiction_records=records)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)

    # The record must appear in what_contradicted
    ids = [c["id"] for c in brief["what_contradicted"]]
    assert "C99" in ids, f"C99 not found in what_contradicted: {ids}"

    # No trading verb may appear in any produced string
    all_strings = _collect_all_strings(brief)
    for s in all_strings:
        tokens = s.lower().split()
        for verb in TRADING_VERBS:
            assert verb not in tokens, (
                f"Trading verb '{verb}' leaked into output string: {s!r}"
            )

    # Specifically confirm the C99 summary was scrubbed
    c99 = next(c for c in brief["what_contradicted"] if c["id"] == "C99")
    assert "buy" not in c99["summary"].lower(), (
        f"Trading verb 'buy' not scrubbed from contradiction summary: {c99['summary']!r}"
    )
    assert "[redacted]" in c99["summary"], (
        f"Expected '[redacted]' marker in scrubbed summary: {c99['summary']!r}"
    )


# ---------------------------------------------------------------------------
# 10. Site copy written alongside data copy
# ---------------------------------------------------------------------------

def test_site_copy_written(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    payload = build(root=tmp_path)
    write(payload, root=tmp_path)

    data_path = tmp_path / "data" / "neuralweb" / "daily_brief.json"
    site_path = tmp_path / "site" / "neuralwebdata" / "daily_brief.json"

    assert data_path.exists(), "data copy not written"
    assert site_path.exists(), "site copy not written"

    # Both files must have same content
    assert data_path.read_bytes() == site_path.read_bytes(), "data and site copies differ"


# ---------------------------------------------------------------------------
# 11. Malformed/missing inputs → gaps + exit 0
# ---------------------------------------------------------------------------

def test_missing_inputs_gaps(tmp_path):
    """With NO input files at all, build must succeed with explicit gaps."""
    _make_minimal_root(tmp_path)
    # No health.json, no world_state, no memo, no graph, no history

    brief = build(root=tmp_path)

    assert brief["schema"] == "neuralweb.daily_brief.v1"
    gaps = brief.get("_gaps", [])
    assert len(gaps) > 0, "Expected gap notes when inputs missing"
    # Status must be degraded when health missing
    assert brief["status"] == "degraded"


def test_malformed_health_json(tmp_path):
    """Malformed health.json (wrong schema) → treated as missing."""
    _make_minimal_root(tmp_path)
    p = tmp_path / "data" / "neuralweb" / "health.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"schema": "wrong.v99", "garbage": true}', encoding="utf-8")

    brief = build(root=tmp_path)

    assert brief["schema"] == "neuralweb.daily_brief.v1"
    gaps = brief.get("_gaps", [])
    assert any("health" in g.lower() for g in gaps), f"Expected health gap note, got: {gaps}"


def test_cli_exits_zero_on_missing_inputs(tmp_path):
    """build_neuralweb_brief.py exits 0 even with no input files."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_neuralweb_brief",
        _REPO_ROOT / "scripts" / "build_neuralweb_brief.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    _make_minimal_root(tmp_path)
    rc = mod.main(["--root", str(tmp_path)])
    assert rc == 0, f"Expected exit 0, got {rc}"


def test_cli_finalize_exits_zero_on_missing_inputs(tmp_path):
    """build_neuralweb_brief --finalize exits 0 even with no input files."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_neuralweb_brief",
        _REPO_ROOT / "scripts" / "build_neuralweb_brief.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    _make_minimal_root(tmp_path)
    rc = mod.main(["--root", str(tmp_path), "--finalize"])
    assert rc == 0, f"Expected exit 0, got {rc}"


# ---------------------------------------------------------------------------
# 12. qi never read
# ---------------------------------------------------------------------------

def test_qi_not_in_brief(tmp_path):
    """world_state with qi key must not appear in brief output anywhere."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path, extra_keys={"qi": {"SENTINEL": "qi_value_sentinel_xyzzy"}})
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)

    all_strings = _collect_all_strings(brief)
    for s in all_strings:
        assert "qi_value_sentinel_xyzzy" not in s, (
            f"qi sentinel value found in brief output — qi domain was read: {s!r}"
        )
    # Also verify 'qi' key not propagated as a section
    assert "qi" not in brief, "qi key must not appear at top level of brief"


# ---------------------------------------------------------------------------
# Additional coverage: _build_brain_run
# ---------------------------------------------------------------------------

def test_brain_run_degraded_summary():
    health = {
        "schema": "neuralweb.health.v1",
        "cortex": {
            "status": "degraded",
            "memo_as_of": "2026-07-06T08:00:00+00:00",
            "run_status": {
                "degraded": True,
                "degradation_reason": "zero_tool_calls",
                "tool_call_batches": 0,
                "individual_tool_calls": 0,
                "context_stale": False,
            },
        },
    }
    br = _build_brain_run(health, None)
    assert br["cortex_status"] == "degraded"
    assert "zero_tool_calls" in br["summary"]


def test_brain_run_no_health():
    br = _build_brain_run(None, None)
    assert br["cortex_status"] == "unknown"
    assert br["summary"] is not None


# ---------------------------------------------------------------------------
# _brief_status: cortex-degraded floors at warn (OPERATOR RULING 2026-07-12 —
# deliberation is opportunistic under the shared-OAuth-quota design)
# ---------------------------------------------------------------------------

def test_brief_status_no_health_degraded():
    assert _brief_status(None, {}) == "degraded"


def test_brief_status_overall_degraded_wins():
    health = {"overall_status": "degraded"}
    assert _brief_status(health, {"cortex_status": "ok"}) == "degraded"


def test_brief_status_cortex_degraded_floors_at_warn():
    health = {"overall_status": "ok"}
    assert _brief_status(health, {"cortex_status": "degraded"}) == "warn"
    assert _brief_status(health, {"cortex_status": "missing"}) == "warn"
    assert _brief_status(health, {"cortex_status": "warn"}) == "warn"


def test_brief_status_all_ok():
    health = {"overall_status": "ok"}
    assert _brief_status(health, {"cortex_status": "ok"}) == "ok"


# ---------------------------------------------------------------------------
# Additional coverage: _detect_changes
# ---------------------------------------------------------------------------

def test_detect_as_of_advanced():
    cur = {
        "as_of": "2026-07-06T09:00:00+00:00",
        "lobe_status": {},
        "contradiction_count": 0,
        "contradiction_ids": [],
        "cortex_status": "fresh",
    }
    prev = {
        "as_of": "2026-07-05T09:00:00+00:00",
        "lobe_status": {},
        "contradiction_count": 0,
        "contradiction_ids": [],
        "cortex_status": "fresh",
    }
    changes = _detect_changes(cur, prev)
    kinds = [c["kind"] for c in changes]
    assert "as_of_advanced" in kinds


def test_detect_cortex_status_changed():
    cur = {
        "as_of": "2026-07-06T09:00:00+00:00",
        "lobe_status": {},
        "contradiction_count": 0,
        "contradiction_ids": [],
        "cortex_status": "degraded",
    }
    prev = {
        "as_of": "2026-07-06T09:00:00+00:00",
        "lobe_status": {},
        "contradiction_count": 0,
        "contradiction_ids": [],
        "cortex_status": "fresh",
    }
    changes = _detect_changes(cur, prev)
    kinds = [c["kind"] for c in changes]
    assert "cortex_status_changed" in kinds


# ---------------------------------------------------------------------------
# Additional: schema field presence
# ---------------------------------------------------------------------------

def test_brief_schema_fields(tmp_path):
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    brief = build(root=tmp_path)

    required = [
        "schema", "produced_at", "as_of", "status", "phase",
        "did_the_brain_run", "what_changed", "what_contradicted",
        "what_is_stale", "operator_attention", "candidate_watch", "caveats",
    ]
    for field in required:
        assert field in brief, f"Missing required field: {field!r}"

    assert brief["status"] in ("ok", "warn", "degraded")
    assert brief["phase"] in ("engine", "final")
    assert isinstance(brief["caveats"], list)
    assert len(brief["caveats"]) > 0


# ---------------------------------------------------------------------------
# Evidence Clock section tests (EC-R5)
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "evidence_clock_sample.json"


def _write_evidence_clock(tmp_path: Path, fixture_path: Path | None = None) -> None:
    """Write evidence_clock.json into the tmp_path data/ tree."""
    dest = tmp_path / "data" / "neuralweb" / "evidence_clock.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fixture_path is None:
        fixture_path = _FIXTURE_PATH
    dest.write_bytes(fixture_path.read_bytes())


def test_evidence_clock_section_present_with_artifact(tmp_path):
    """With evidence_clock.json present, section is available with counts + morning_line."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)
    _write_evidence_clock(tmp_path)

    brief = build(root=tmp_path)

    ec = brief.get("evidence_clock")
    assert ec is not None, "evidence_clock key missing from brief"
    assert ec["available"] is True
    assert "counts" in ec
    assert "morning_line" in ec
    assert isinstance(ec["counts"], dict)
    # Counts should have state keys
    for state_key in ("overdue", "due", "accruing"):
        assert state_key in ec["counts"], f"counts missing state key: {state_key}"
    # morning_line is non-empty
    assert ec["morning_line"], "morning_line should be non-empty"
    # as_of is present
    assert ec.get("as_of") == "2026-07-06"
    # top_due present (fixture has a due row)
    assert ec["top_due"] is not None
    assert "clock_id" in ec["top_due"]


def test_evidence_clock_section_absent_artifact(tmp_path):
    """Without evidence_clock.json, section is available=False and gap is noted."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)
    # Do NOT write evidence_clock.json

    brief = build(root=tmp_path)

    ec = brief.get("evidence_clock")
    assert ec is not None, "evidence_clock key missing even when artifact absent"
    assert ec["available"] is False

    # Gap should be recorded
    gaps = brief.get("_gaps", [])
    assert any("evidence_clock" in g for g in gaps), (
        f"Expected evidence_clock gap note, got: {gaps}"
    )


def test_evidence_clock_overdue_p3_attention(tmp_path):
    """When overdue > 0, operator_attention gets a P3 evidence_clock item."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)
    _write_evidence_clock(tmp_path)  # fixture has 1 overdue row

    brief = build(root=tmp_path)

    p3_items = [a for a in brief["operator_attention"] if a["priority"] == 3]
    ec_items = [a for a in p3_items if a.get("area") == "evidence_clock"]
    assert ec_items, (
        "Expected a P3 evidence_clock operator_attention item when overdue > 0; "
        f"got p3 items: {p3_items}"
    )
    assert "overdue" in ec_items[0]["summary"].lower()
    assert "Observatory" in ec_items[0]["summary"]


def test_evidence_clock_no_p3_when_no_overdue(tmp_path):
    """When overdue == 0, no P3 evidence_clock attention item is added."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    # Write a clock with zero overdue
    import json as _json
    no_overdue = {
        "schema": "neuralweb.evidence_clock.v1",
        "as_of": "2026-07-06",
        "generated_utc": "2026-07-06T10:00:00Z",
        "authority": "display_only",
        "summary": {
            "n_rows": 1,
            "by_state": {
                "overdue": 0, "due": 0, "human_review": 0, "missing": 0,
                "stale": 0, "blocked": 0, "not_ready": 0,
                "promotion_eligible": 0, "accruing": 1,
            },
            "n_acknowledged": 0,
            "top_due": None,
            "morning_line": "1 accruing.",
        },
        "rows": [],
        "gaps": [],
        "caveats": [],
    }
    dest = tmp_path / "data" / "neuralweb" / "evidence_clock.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_json.dumps(no_overdue), encoding="utf-8")

    brief = build(root=tmp_path)

    ec_p3_items = [
        a for a in brief["operator_attention"]
        if a.get("priority") == 3 and a.get("area") == "evidence_clock"
    ]
    assert not ec_p3_items, (
        f"Expected no P3 evidence_clock item when overdue=0, got: {ec_p3_items}"
    )


def test_evidence_clock_counts_only_no_internal_prose(tmp_path):
    """Evidence clock section must not contain blocking_reason or readiness detail."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)
    _write_evidence_clock(tmp_path)

    brief = build(root=tmp_path)
    ec = brief.get("evidence_clock", {})

    # The public section must not contain row-level detail
    assert "rows" not in ec, "evidence_clock section must not contain row-level rows"
    assert "queue" not in ec, "evidence_clock section must not contain queue (internal)"

    # Verify no blocking_reason leaked into section strings
    all_strings = _collect_all_strings(ec)
    for s in all_strings:
        assert "blocking_reason" not in s, (
            f"blocking_reason key leaked into evidence_clock section: {s!r}"
        )
        assert "not refreshed since" not in s, (
            f"internal prose leaked into evidence_clock section: {s!r}"
        )


def test_evidence_clock_malformed_schema(tmp_path):
    """evidence_clock.json with wrong schema → available=False, no crash."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    import json as _json
    dest = tmp_path / "data" / "neuralweb" / "evidence_clock.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_json.dumps({"schema": "wrong.v99", "garbage": True}), encoding="utf-8")

    brief = build(root=tmp_path)

    ec = brief.get("evidence_clock", {})
    assert ec["available"] is False


# ---------------------------------------------------------------------------
# R2 type-drift / hostile-artifact tests (opus review)
# ---------------------------------------------------------------------------

def _write_ec_raw(tmp_path: Path, payload: dict) -> None:
    """Write a raw evidence_clock payload (schema pre-set) to the fixture tree."""
    dest = tmp_path / "data" / "neuralweb" / "evidence_clock.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload), encoding="utf-8")


def test_evidence_clock_summary_as_list_no_crash(tmp_path):
    """summary is a list (type drift) → build() must not raise; available=True counts default 0."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    _write_ec_raw(tmp_path, {
        "schema": "neuralweb.evidence_clock.v1",
        "as_of": "2026-07-06",
        "generated_utc": "2026-07-06T10:00:00Z",
        "authority": "display_only",
        "summary": ["should", "be", "a", "dict"],  # type-drifted
        "rows": [],
        "caveats": [],
    })

    brief = build(root=tmp_path)
    assert brief["schema"] == "neuralweb.daily_brief.v1"
    ec = brief.get("evidence_clock", {})
    assert ec["available"] is True
    # All counts should default to 0
    for k in ("overdue", "due", "accruing"):
        assert ec["counts"][k] == 0, f"count for {k!r} should be 0 when summary drifted"


def test_evidence_clock_by_state_as_list_no_crash(tmp_path):
    """by_state is a list (type drift) → build() must not raise; counts default 0."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    _write_ec_raw(tmp_path, {
        "schema": "neuralweb.evidence_clock.v1",
        "as_of": "2026-07-06",
        "generated_utc": "2026-07-06T10:00:00Z",
        "authority": "display_only",
        "summary": {
            "n_rows": 0,
            "by_state": ["overdue", "due"],  # type-drifted: should be a dict
            "n_acknowledged": 0,
            "top_due": None,
            "morning_line": "artifact prose",
        },
        "rows": [],
        "caveats": [],
    })

    brief = build(root=tmp_path)
    ec = brief.get("evidence_clock", {})
    assert ec["available"] is True
    assert isinstance(ec["counts"], dict)
    for k in ("overdue", "due", "accruing"):
        assert isinstance(ec["counts"][k], int)
        assert ec["counts"][k] == 0


def test_evidence_clock_overdue_as_string_no_crash(tmp_path):
    """overdue count is a string (type drift) → coerced to 0; no TypeError on > 0."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    _write_ec_raw(tmp_path, {
        "schema": "neuralweb.evidence_clock.v1",
        "as_of": "2026-07-06",
        "generated_utc": "2026-07-06T10:00:00Z",
        "authority": "display_only",
        "summary": {
            "n_rows": 1,
            "by_state": {
                "overdue": "one",  # type-drifted: string instead of int
                "due": 0,
                "human_review": 0,
                "missing": 0,
                "stale": 0,
                "blocked": 0,
                "not_ready": 0,
                "promotion_eligible": 0,
                "accruing": 0,
            },
            "n_acknowledged": 0,
            "top_due": None,
            "morning_line": "drift prose",
        },
        "rows": [],
        "caveats": [],
    })

    # Must not raise TypeError on n_overdue > 0 comparison in P3 block
    brief = build(root=tmp_path)
    ec = brief.get("evidence_clock", {})
    assert ec["available"] is True
    # overdue coerced to 0 (string not int)
    assert ec["counts"]["overdue"] == 0


def test_evidence_clock_morning_line_no_artifact_passthrough(tmp_path):
    """Hostile artifact morning_line containing internal path/thesis string must
    NOT appear anywhere in the built section (public-leak guard R2)."""
    _make_minimal_root(tmp_path)
    _make_health(tmp_path)
    _make_world_state(tmp_path)
    _make_cortex_memo(tmp_path)
    _make_graph(tmp_path)
    _make_mastermind_context(tmp_path)

    HOSTILE_PROSE = "INTERNAL: data/neuralweb/secret_thesis — do not publish"
    _write_ec_raw(tmp_path, {
        "schema": "neuralweb.evidence_clock.v1",
        "as_of": "2026-07-06",
        "generated_utc": "2026-07-06T10:00:00Z",
        "authority": "display_only",
        "summary": {
            "n_rows": 2,
            "by_state": {
                "overdue": 1,
                "due": 1,
                "human_review": 0,
                "missing": 0,
                "stale": 0,
                "blocked": 0,
                "not_ready": 0,
                "promotion_eligible": 0,
                "accruing": 0,
            },
            "n_acknowledged": 0,
            "top_due": None,
            "morning_line": HOSTILE_PROSE,  # hostile: internal path/thesis
        },
        "rows": [],
        "caveats": [],
    })

    brief = build(root=tmp_path)
    ec = brief.get("evidence_clock", {})
    assert ec["available"] is True

    # The hostile prose must NOT appear anywhere in the built section
    all_strings = _collect_all_strings(ec)
    for s in all_strings:
        assert HOSTILE_PROSE not in s, (
            f"Artifact morning_line passthrough detected — hostile prose found in section: {s!r}"
        )
    # Confirm morning_line is local reconstruction (counts-based)
    assert "overdue" in ec["morning_line"] or "due" in ec["morning_line"], (
        f"morning_line should be reconstructed from counts, got: {ec['morning_line']!r}"
    )
