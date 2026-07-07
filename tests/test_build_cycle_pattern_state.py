"""tests/test_build_cycle_pattern_state.py — CPI P6 wave-1 adapter + lobe tests.

Covers
------
Builder (scripts/build_cycle_pattern_state.py):
1. fail_open_everything_missing — no live parquet, no model ledger, no truths:
   build() writes a VALID JSON with schema key, empty gate_status/entities,
   zeroed truth_summary, degraded_notes — and never raises.
2. schema_required_keys — populated fixture emits all required top-level keys.
3. gate_status_from_synthetic_ledger — verdicts are READ from the model ledger
   artifact (a synthetic ledger with a flipped verdict shows up verbatim; the
   builder never hardcodes PASS/PRIOR).
4. entities_latest_row_deterministic — latest row per entity, deterministic
   (family, native_id) ordering, parquet NaN → JSON null.
5. truth_summary_from_synthetic_registry — counts + last-5-by-created ids from
   a synthetic truths.jsonl via engine.cycle_pattern.truths.
6. no_nan_in_output — the emitted file contains no bare NaN literal.

NW wiring:
7. compose_cycle_pattern lobe — null fallback when the artifact is absent;
   counts + gate_status + display_only=True when present.
8. mastermind summarizer — gap note when absent; populated lobe when present.
9. cortex read tool — registered in _READ_TOOLS + _tool_schemas + ask_brain
   whitelist; dispatch returns the artifact (fail-open dict when absent).
10. schema/whitelist consistency — every _ASK_READ_TOOLS name has a cortex
    tool schema (the ask endpoint filters schemas by name).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_cycle_pattern_state import SCHEMA, build

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "schema", "asof", "model_epoch", "gate_status", "entities",
    "truth_summary", "display_only", "note",
}


def _synthetic_ledger(tmp_path: Path, up_1m: str = "PASS") -> Path:
    """Write a synthetic hazard model ledger with controllable verdicts."""
    ledger = {
        "turn_def_version": "price_testepoch",
        "ledger": {
            "up": {
                "1m": {"verdict": up_1m},
                "3m": {"verdict": "PRIOR"},
                "6m": {"verdict": "PRIOR"},
            },
            "down": {
                "1m": {"verdict": "PASS"},
                "3m": {"verdict": "PASS"},
                "6m": {"verdict": "PASS"},
            },
        },
    }
    p = tmp_path / "model_price_testepoch.json"
    p.write_text(json.dumps(ledger), encoding="utf-8")
    return p


def _synthetic_live_parquet(tmp_path: Path) -> None:
    """Write a two-entity, two-date live view (one NaN hazard row kept latest)."""
    import pandas as pd

    live_dir = tmp_path / "data" / "cycle_pattern"
    live_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([
        # ZZTOP: older row has hazard, newer row is the one that must win
        {"entity_id": "us_sector:ZZTOP", "native_id": "ZZTOP", "family": "us_sector",
         "date": pd.Timestamp("2026-07-01"), "phase": "Peak", "phase_v2": "Peak",
         "hazard_1m_p": 0.11, "hazard_1m_src": "MODEL",
         "hazard_3m_p": 0.22, "hazard_3m_src": "MODEL",
         "hazard_6m_p": 0.33, "hazard_6m_src": "MODEL"},
        {"entity_id": "us_sector:ZZTOP", "native_id": "ZZTOP", "family": "us_sector",
         "date": pd.Timestamp("2026-07-02"), "phase": "Downturn", "phase_v2": "Downturn",
         "hazard_1m_p": 0.44, "hazard_1m_src": "MODEL",
         "hazard_3m_p": 0.55, "hazard_3m_src": "MODEL",
         "hazard_6m_p": 0.66, "hazard_6m_src": "MODEL"},
        # AAA basket: NaN hazard (must serialize as null, not NaN)
        {"entity_id": "us_basket:aaa", "native_id": "aaa", "family": "us_basket",
         "date": pd.Timestamp("2026-07-02"), "phase": "Recovery", "phase_v2": None,
         "hazard_1m_p": float("nan"), "hazard_1m_src": None,
         "hazard_3m_p": float("nan"), "hazard_3m_src": None,
         "hazard_6m_p": float("nan"), "hazard_6m_src": None},
    ])
    df.to_parquet(live_dir / "state_daily_live.parquet", index=False)


def _synthetic_truths(tmp_path: Path) -> Path:
    """Write a synthetic truths.jsonl (7 truths; 1 superseded; 2 promoted_null)."""
    rows = []
    for i in range(1, 7):
        rows.append({
            "truth_id": f"CPT-{i:03d}", "version": 1,
            "status": "promoted_null" if i <= 2 else "display",
            "created": f"2026-07-{i:02d}T00:00:00+00:00",
        })
    # superseded truth must be excluded from active counts
    rows.append({"truth_id": "CPT-000", "version": 2, "status": "superseded",
                 "created": "2026-07-01T00:00:00+00:00"})
    p = tmp_path / "truths.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _run_build(tmp_path: Path, *, ledger: Path | None, truths: Path | None) -> dict:
    """Run build() against tmp_path with the given synthetic inputs."""
    missing = tmp_path / "nonexistent.json"
    with mock.patch("scripts.build_cycle_pattern_state._REPO_ROOT", tmp_path), \
         mock.patch("engine.hazard_score._MODEL_PATH", ledger or missing), \
         mock.patch("engine.cycle_pattern.truths.TRUTHS_PATH",
                    truths or (tmp_path / "no_truths.jsonl")):
        return build()


# ---------------------------------------------------------------------------
#  Builder tests
# ---------------------------------------------------------------------------

def test_fail_open_everything_missing(tmp_path):
    """All inputs absent → valid degraded JSON, never raises."""
    result = _run_build(tmp_path, ledger=None, truths=None)

    assert result["schema"] == SCHEMA
    assert result["gate_status"] == {}
    assert result["model_epoch"] is None
    assert result["entities"] == []
    assert result["truth_summary"] == {
        "n_active": 0, "n_promoted_null": 0, "latest_truth_ids": [],
    }
    assert result["display_only"] is True
    assert result.get("degraded_notes"), "degraded_notes must explain what was missing"

    # The written file must be valid JSON and round-trip identically
    out = tmp_path / "data" / "neuralweb" / "cycle_pattern_state.json"
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == SCHEMA


def test_schema_required_keys(tmp_path):
    """Populated fixture emits every required top-level key."""
    _synthetic_live_parquet(tmp_path)
    result = _run_build(tmp_path, ledger=_synthetic_ledger(tmp_path),
                        truths=_synthetic_truths(tmp_path))
    missing = _REQUIRED_KEYS - set(result.keys())
    assert not missing, f"Missing required keys: {missing}"
    assert "degraded_notes" not in result


def test_gate_status_from_synthetic_ledger(tmp_path):
    """gate_status must be read from the ledger artifact, not hardcoded."""
    # Flip up/1m to PRIOR — a hardcoded builder would still say PASS.
    result = _run_build(tmp_path, ledger=_synthetic_ledger(tmp_path, up_1m="PRIOR"),
                        truths=None)
    assert result["model_epoch"] == "price_testepoch"
    assert result["gate_status"]["up"] == {"1m": "PRIOR", "3m": "PRIOR", "6m": "PRIOR"}
    assert result["gate_status"]["down"] == {"1m": "PASS", "3m": "PASS", "6m": "PASS"}


def test_entities_latest_row_deterministic(tmp_path):
    """Latest row per entity wins; ordering is (family, native_id); NaN → null."""
    _synthetic_live_parquet(tmp_path)
    result = _run_build(tmp_path, ledger=_synthetic_ledger(tmp_path),
                        truths=None)
    ents = result["entities"]
    assert [e["native_id"] for e in ents] == ["aaa", "ZZTOP"]  # us_basket < us_sector

    zz = ents[1]
    assert zz["date"] == "2026-07-02"          # latest row won
    assert zz["phase_v2"] == "Downturn"
    assert zz["hazard_1m_p"] == pytest.approx(0.44)
    assert zz["hazard_src"] == {"1m": "MODEL", "3m": "MODEL", "6m": "MODEL"}

    aaa = ents[0]
    assert aaa["hazard_1m_p"] is None           # NaN must become null
    assert aaa["hazard_src"]["1m"] is None
    assert aaa["phase_v2"] == "Recovery"        # phase_v2 null → phase fallback


def test_truth_summary_from_synthetic_registry(tmp_path):
    """Counts + last-5-by-created ids from active truths only."""
    result = _run_build(tmp_path, ledger=None, truths=_synthetic_truths(tmp_path))
    ts = result["truth_summary"]
    assert ts["n_active"] == 6                 # superseded CPT-000 excluded
    assert ts["n_promoted_null"] == 2
    assert ts["latest_truth_ids"] == [
        "CPT-002", "CPT-003", "CPT-004", "CPT-005", "CPT-006",
    ]


def test_no_nan_in_output(tmp_path):
    """The emitted file must never contain a bare NaN literal (invalid JSON)."""
    _synthetic_live_parquet(tmp_path)
    _run_build(tmp_path, ledger=_synthetic_ledger(tmp_path),
               truths=_synthetic_truths(tmp_path))
    text = (tmp_path / "data" / "neuralweb" / "cycle_pattern_state.json").read_text(encoding="utf-8")
    assert "NaN" not in text
    json.loads(text)


# ---------------------------------------------------------------------------
#  world_state lobe
# ---------------------------------------------------------------------------

def _write_artifact(tmp_path: Path, n_entities: int = 2) -> None:
    art_dir = tmp_path / "data" / "neuralweb"
    art_dir.mkdir(parents=True, exist_ok=True)
    entities = [
        {"entity_id": f"us_sector:T{i}", "native_id": f"T{i}", "family": "us_sector",
         "phase_v2": "Peak", "hazard_1m_p": 0.4, "hazard_3m_p": 0.5,
         "hazard_6m_p": 0.6,
         "hazard_src": {"1m": "MODEL", "3m": "MODEL", "6m": "MODEL"},
         "date": "2026-07-02"}
        for i in range(n_entities)
    ]
    (art_dir / "cycle_pattern_state.json").write_text(json.dumps({
        "schema": SCHEMA, "asof": "2026-07-06", "model_epoch": "price_testepoch",
        "gate_status": {"up": {"1m": "PASS", "3m": "PRIOR", "6m": "PRIOR"},
                        "down": {"1m": "PASS", "3m": "PASS", "6m": "PASS"}},
        "entities": entities,
        "truth_summary": {"n_active": 3, "n_promoted_null": 1,
                          "latest_truth_ids": ["CPT-001"]},
        "display_only": True, "note": "test",
    }), encoding="utf-8")


def test_compose_cycle_pattern_absent(tmp_path):
    """Missing adapter artifact → null-filled lobe, display_only always True."""
    from engine.neuralweb.world_state import _compose_cycle_pattern
    lobe = _compose_cycle_pattern(root=tmp_path)
    assert lobe["display_only"] is True
    assert lobe["gate_status"] is None
    assert lobe["n_entities"] is None
    assert "note" in lobe


def test_compose_cycle_pattern_populated(tmp_path):
    """Populated artifact → counts + gate verdicts, no per-entity rows."""
    _write_artifact(tmp_path, n_entities=3)
    from engine.neuralweb.world_state import _compose_cycle_pattern
    lobe = _compose_cycle_pattern(root=tmp_path)
    assert lobe["display_only"] is True
    assert lobe["n_entities"] == 3
    assert lobe["n_with_hazard"] == 3
    assert lobe["families"] == {"us_sector": 3}
    assert lobe["gate_status"]["up"]["3m"] == "PRIOR"
    assert lobe["model_epoch"] == "price_testepoch"
    assert "entities" not in lobe  # counts-only in world_state


# ---------------------------------------------------------------------------
#  mastermind_context summarizer
# ---------------------------------------------------------------------------

def test_summarize_cycle_pattern_absent(tmp_path):
    from engine.neuralweb.mastermind_context import _summarize_cycle_pattern
    lobe, gap = _summarize_cycle_pattern(tmp_path)
    assert lobe == {}
    assert gap and "cycle_pattern_state.json" in gap


def test_summarize_cycle_pattern_populated(tmp_path):
    _write_artifact(tmp_path, n_entities=2)
    from engine.neuralweb.mastermind_context import (
        LOBE_SUMMARIZERS, _LOBE_TO_ARTIFACT_IDS, _summarize_cycle_pattern,
    )
    lobe, gap = _summarize_cycle_pattern(tmp_path)
    assert gap is None
    assert lobe["n_entities"] == 2
    assert lobe["gate_status"]["down"]["3m"] == "PASS"
    assert lobe["truth_summary"]["n_active"] == 3
    assert "standing_law" in lobe and "DISPLAY" in lobe["standing_law"].upper()
    # Registered in both lobe registries
    assert "cycle_pattern" in LOBE_SUMMARIZERS
    assert _LOBE_TO_ARTIFACT_IDS["cycle_pattern"] == ["cycle-pattern-state"]


# ---------------------------------------------------------------------------
#  cortex read tool + ask_brain whitelist
# ---------------------------------------------------------------------------

def test_read_tool_registered_everywhere():
    from engine.neuralweb.cortex import _READ_TOOLS, _tool_schemas
    from engine.neuralweb.ask_brain import _ASK_READ_TOOLS
    assert "read_cycle_pattern_state" in _READ_TOOLS
    assert "read_cycle_pattern_state" in _ASK_READ_TOOLS
    schema_names = {s["name"] for s in _tool_schemas()}
    assert "read_cycle_pattern_state" in schema_names
    # The tool description must carry the authority ceiling.
    desc = next(s["description"] for s in _tool_schemas()
                if s["name"] == "read_cycle_pattern_state")
    assert "never originate, score, or escalate" in desc.lower()


def test_ask_whitelist_schema_consistency():
    """Every ask-endpoint read tool must have a cortex schema (filter-by-name)."""
    from engine.neuralweb.cortex import _tool_schemas
    from engine.neuralweb.ask_brain import _ASK_READ_TOOLS
    schema_names = {s["name"] for s in _tool_schemas()}
    missing = set(_ASK_READ_TOOLS) - schema_names
    assert not missing, f"ask read tools without cortex schema: {missing}"


def test_read_tool_dispatch(tmp_path):
    from engine.neuralweb.cortex import _tool_read_cycle_pattern_state
    # Absent → fail-open with gaps
    out = _tool_read_cycle_pattern_state(tmp_path, {})
    assert out["is_context_only"] is True
    assert out["display_only"] is True
    assert out.get("gaps")
    # Present → artifact returned with mandate fields
    _write_artifact(tmp_path)
    out = _tool_read_cycle_pattern_state(tmp_path, {})
    assert out["schema"] == SCHEMA
    assert out["is_context_only"] is True
    assert out["display_only"] is True
    assert len(out["entities"]) == 2


def test_ask_brain_dispatch_routes_tool(tmp_path):
    from engine.neuralweb.ask_brain import _dispatch_read_tool
    _write_artifact(tmp_path)
    out = _dispatch_read_tool("read_cycle_pattern_state", {}, tmp_path)
    assert out.get("schema") == SCHEMA
    assert out["is_context_only"] is True
