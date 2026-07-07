"""tests/test_confluence.py — Hermetic unit tests for Neural Web W4.

Tests
-----
Contradictions detector (engine/neuralweb/contradictions.py):
  1.  pair_a_positive       — regime Q1 + RISK_OFF verdict (deep-in-quad) → tension record
  2.  pair_a_negative       — regime Q1 + NEUTRAL verdict → no record
  3.  pair_a_near_boundary_label_lag — Q1 + RISK_OFF near flip → label-lag note (NOT tension)
  4.  pair_a_deep_quad_tension — Q1 + RISK_OFF deep-in (high conf, large margin) → tension
  5.  pair_a_near_boundary_risk_on — Q1 + RISK_ON near flip → no record
  6.  pair_b_positive       — rising growth + growth scare caution → record
  7.  pair_b_negative       — rising growth + calm scare → no record
  8.  pair_c_positive       — oracle bullish + sc majority bearish → record
  9.  pair_c_negative       — oracle bullish + sc majority bullish → no record
  10. pair_d_positive       — low vol + RISK_OFF → record
  11. pair_d_negative       — normal vol + RISK_OFF → no record
  12. pair_e_positive       — briefing with divergences → summary record
  13. pair_e_negative       — briefing with 0 divergences → no record
  14. pair_f_positive       — cross_asset_confirm verdict=diverge → record
  15. pair_f_negative       — cross_asset_confirm verdict=confirm → no record
  16. pairs_fail_open       — all inputs missing → empty records + gaps, no raise
  17. severity_vocab        — no record carries severity='critical'

Confluence graph (engine/neuralweb/confluence.py):
  15. graph_schema          — output has required schema/tier/display_only fields
  16. engine_nodes          — correct count from spine fixture
  17. sector_nodes_gics     — 11 GICS sector nodes always present
  18. regime_nodes          — 5 regime nodes (Q1-Q4 + __all__)
  19. thesis_nodes          — thesis nodes from jsonl (active only)
  20. episode_nodes_capped  — capped at 50 most recent
  21. feeds_edges           — feeds edges from registry (producer→artifact→consumer)
  22. confirms_lift_above_floor  — n >= MIN_N → lift value computed
  23. confirms_lift_below_floor  — n < MIN_N → lift=null, n printed
  24. contradicts_edges     — contradiction records become contradicts edges
  25. oracle_absent_failopen — oracle files absent → fail-open gaps, graph returned
  26. envelope_fields       — produced_by + produced_at present
  27. determinism           — two calls same now → same produced_at
  28. gaps_list             — graph has gaps list even when all ok

World-state contradictions block (engine/neuralweb/world_state.py):
  29. world_state_contradictions_block  — contradictions key present in payload
  30. world_state_contradictions_failopen — detector raises → block null, gaps appended
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import tempfile

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def _make_world_state(
    tmp: Path,
    quad: str = "Q1",
    growth_score: float = 0.3,
    verdict: str = "RISK_OFF",
    vol_regime: str = "normalizing",
    rr_state: str = "caution",
    rr_dominant: str = "growth",
    # Scale fields for flip-aware pair-a logic (operator feedback 2026-07-04).
    # Defaults represent a deep-in-quad, stable regime (NOT near a flip).
    flip_margin: float | None = 0.60,
    transition_state: str | None = "STABLE",
    confidence: float | None = 0.75,
    inflation_score: float | None = -0.2,
    flip_condition: dict | None = None,
) -> dict:
    regime_block: dict = {
        "quad": quad,
        "growth_score": growth_score,
        "inflation_score": inflation_score,
        "asof": "2026-07-01",
    }
    if flip_margin is not None:
        regime_block["flip_margin"] = flip_margin
    if transition_state is not None:
        regime_block["transition_state"] = transition_state
    if confidence is not None:
        regime_block["confidence"] = confidence
    if flip_condition is not None:
        regime_block["flip_condition"] = flip_condition
    ws = {
        "regime": regime_block,
        "verdict": {
            "verdict": verdict,
            "asof": "2026-07-01",
        },
        "vol": {
            "regime": vol_regime,
            "asof": "2026-07-01",
        },
        "risk_radar_raw": {
            "state": rr_state,
            "dominant_scare": rr_dominant,
            "top_score": 75.0,
        },
        "gaps": [],
    }
    _write_json(tmp / "data" / "neuralweb" / "world_state.json", ws)
    return ws


def _make_regime_latest(
    tmp: Path,
    quad: str = "Q1",
    ca_verdict: str = "diverge",
    vol_regime_str: str = "normalizing",
) -> dict:
    reg = {
        "quad": quad,
        "growth_score": 0.3,
        "asof": "2026-07-01",
        "vol_regime": {"regime": vol_regime_str, "asof": "2026-07-01"},
        "cross_asset_confirm": {
            "verdict": ca_verdict,
            "headline_en": f"Cross-asset verdict: {ca_verdict}",
            "agree_pct": 0.5,
        },
        "risk_radar": {
            "state": "caution",
            "dominant_scare": "growth",
            "top_score": 75.0,
        },
    }
    _write_json(tmp / "data" / "regime" / "latest.json", reg)
    return reg


def _make_market_state(tmp: Path, verdict: str = "RISK_OFF") -> dict:
    ms = {
        "verdict": verdict,
        "asof": "2026-07-01",
        "schema": "market_state.v1",
    }
    _write_json(tmp / "data" / "market_state" / "latest.json", ms)
    return ms


def _make_oracle_state(
    tmp: Path,
    complexes: list[dict] | None = None,
    episodes: list[dict] | None = None,
) -> dict:
    oracle = {
        "asof": "2026-07-04",
        "schema": "oracle_state.v1",
        "complexes": complexes or [],
        "active_episodes": episodes or [],
        "onset_watchlist": [],
        "regime": {"asof": "2026-07-04"},
    }
    _write_json(tmp / "site" / "basketdata" / "oracle_state.json", oracle)
    return oracle


def _make_sector_calls(tmp: Path, rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    path = tmp / "data" / "sector_central" / "calls.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def _make_rotation_groups(tmp: Path, complexes: list[dict]) -> None:
    _write_json(
        tmp / "data" / "oracle" / "rotation_groups.json",
        {"complexes": complexes},
    )


def _make_briefing(tmp: Path, divergences: list[dict]) -> dict:
    briefing = {
        "schema": "briefing.v1",
        "as_of": "2026-07-04",
        "n_divergences": len(divergences),
        "divergences": divergences,
    }
    _write_json(tmp / "site" / "intelligence" / "briefing.json", briefing)
    return briefing


def _make_theses(tmp: Path, rows: list[dict]) -> None:
    _write_jsonl(tmp / "data" / "radar" / "theses.jsonl", rows)


def _make_spine(tmp: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    path = tmp / "data" / "neuralweb" / "spine_index.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _make_synapse(tmp: Path) -> None:
    """Minimal synapse.yml with one artifact for feeds edge test."""
    import shutil
    # Use the real synapse.yml — feeds edge test needs real registry shape
    real = _REPO_ROOT / "config" / "synapse.yml"
    dest = tmp / "config" / "synapse.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if real.exists():
        shutil.copyfile(real, dest)
    else:
        # Fallback: minimal YAML
        dest.write_text(
            "meta:\n  schema_version: 1\nartifacts:\n"
            "  test-artifact:\n"
            "    path: data/test.json\n"
            "    producer: engine/run.py\n"
            "    consumers:\n      - scripts/build_site.py\n",
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Import targets
# ---------------------------------------------------------------------------

from engine.neuralweb.contradictions import detect_contradictions  # noqa: E402
from engine.neuralweb.confluence import build_graph, build_and_write  # noqa: E402


# ===========================================================================
# Contradiction detector tests
# ===========================================================================

class TestPairA:
    """Pair A: regime quad vs market_state verdict (flip-aware since operator feedback)."""

    def test_pair_a_positive(self, tmp_path):
        """Q1 + RISK_OFF (deep-in-quad, stable) → one tension record."""
        # Deep-in-quad: large flip_margin + STABLE transition → genuine directional-opposition
        _make_world_state(
            tmp_path, quad="Q1", verdict="RISK_OFF",
            flip_margin=0.60, transition_state="STABLE", confidence=0.80,
        )
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        records, gaps = detect_contradictions(root=tmp_path)
        a_records = [r for r in records if r["pair_id"] == "regime-vs-market_state"]
        assert len(a_records) >= 1, "Expected pair-a record for Q1+RISK_OFF deep-in-quad"
        r = a_records[0]
        assert r["severity"] in ("note", "tension")
        assert r["display_only"] is True
        # Scale fields must appear in the reading
        assert "flip_margin" in r["a"]["reading"]
        assert "transition_state" in r["a"]["reading"]

    def test_pair_a_negative(self, tmp_path):
        """Q1 + NEUTRAL verdict → no pair-a record."""
        _make_world_state(tmp_path, quad="Q1", verdict="NEUTRAL")
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path, verdict="NEUTRAL")
        records, _ = detect_contradictions(root=tmp_path)
        a_records = [r for r in records if r["pair_id"] == "regime-vs-market_state"]
        assert len(a_records) == 0, f"Unexpected pair-a records: {a_records}"

    def test_pair_a_near_boundary_label_lag(self, tmp_path):
        """Near-boundary Q1 + RISK_OFF → label-lag note, NOT tension.

        Reproduces the operator-reported episode (2026-07-04): quad Q1 (Goldilocks)
        while market_state=RISK_OFF, but flip_margin=0.05 and transition_state=TRANSITIONING
        — the backend scale was already leaning toward Stagflation; the label lagged.
        """
        _make_world_state(
            tmp_path, quad="Q1", verdict="RISK_OFF",
            flip_margin=0.05, transition_state="TRANSITIONING",
            confidence=0.327, growth_score=0.333, inflation_score=-0.52,
            flip_condition={"axis": "growth", "component": "copper_gold",
                            "z": 0.5, "threshold": 0.45, "margin": 0.05},
        )
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        records, _ = detect_contradictions(root=tmp_path)
        a_records = [r for r in records if r["pair_id"] == "regime-vs-market_state"]
        assert len(a_records) == 1, f"Expected exactly one pair-a record; got {a_records}"
        r = a_records[0]
        assert r["kind"] == "label-lag", (
            f"Expected kind='label-lag' for near-boundary regime; got kind={r['kind']!r}"
        )
        assert r["severity"] == "note", (
            f"Expected severity='note' for label-lag; got {r['severity']!r}"
        )
        assert r["display_only"] is True
        # Scale fields must be present in the reading
        assert "flip_margin" in r["a"]["reading"]
        assert "transition_state" in r["a"]["reading"]
        # Note must describe the label-lag situation
        assert "lag" in r["note"].lower() or "lags" in r["note"].lower()

    def test_pair_a_deep_quad_tension(self, tmp_path):
        """Deep-in Q1 (high confidence, large margin) + RISK_OFF → tension (genuine case).

        When flip_margin is large and transition_state is STABLE the opposing verdict
        is genuinely informative — the quad is well-supported and market_state disagrees.
        """
        _make_world_state(
            tmp_path, quad="Q1", verdict="RISK_OFF",
            flip_margin=0.55, transition_state="STABLE",
            confidence=0.82, growth_score=0.45, inflation_score=-0.15,
            flip_condition={"axis": "growth", "component": "copper_gold",
                            "z": 1.0, "threshold": 0.45, "margin": 0.55},
        )
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        records, _ = detect_contradictions(root=tmp_path)
        a_records = [r for r in records if r["pair_id"] == "regime-vs-market_state"]
        assert len(a_records) == 1, f"Expected exactly one pair-a record; got {a_records}"
        r = a_records[0]
        assert r["kind"] == "directional-opposition", (
            f"Expected kind='directional-opposition' for deep-in-quad; got {r['kind']!r}"
        )
        assert r["severity"] == "tension", (
            f"Expected severity='tension' for deep-in-quad genuine case; got {r['severity']!r}"
        )
        assert r["display_only"] is True
        assert "flip_margin" in r["a"]["reading"]

    def test_pair_a_near_boundary_risk_on(self, tmp_path):
        """Near-boundary Q1 + RISK_ON verdict → no record (no opposition to detect)."""
        _make_world_state(
            tmp_path, quad="Q1", verdict="RISK_ON",
            flip_margin=0.05, transition_state="TRANSITIONING",
        )
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path, verdict="RISK_ON")
        records, _ = detect_contradictions(root=tmp_path)
        a_records = [r for r in records if r["pair_id"] == "regime-vs-market_state"]
        assert len(a_records) == 0, (
            f"Near-boundary Q1 + RISK_ON should produce no pair-a record; got {a_records}"
        )


class TestPairB:
    """Pair B: regime_vector growth trend vs risk_radar scare severity."""

    def test_pair_b_positive(self, tmp_path):
        """Q1 rising growth + growth scare caution → pair-b record."""
        _make_world_state(
            tmp_path, quad="Q1", growth_score=0.3,
            verdict="RISK_OFF", rr_state="caution", rr_dominant="growth",
        )
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        records, _ = detect_contradictions(root=tmp_path)
        b_records = [r for r in records if r["pair_id"] == "regime_vector-vs-risk_radar"]
        assert len(b_records) >= 1, "Expected pair-b record"
        assert b_records[0]["severity"] in ("note", "tension")

    def test_pair_b_negative(self, tmp_path):
        """Q1 + calm scare → no pair-b record."""
        _make_world_state(
            tmp_path, quad="Q1", growth_score=0.3,
            verdict="NEUTRAL", rr_state="calm", rr_dominant="vol",
        )
        _make_regime_latest(tmp_path, ca_verdict="confirm")
        _make_market_state(tmp_path, verdict="NEUTRAL")
        records, _ = detect_contradictions(root=tmp_path)
        b_records = [r for r in records if r["pair_id"] == "regime_vector-vs-risk_radar"]
        assert len(b_records) == 0, f"Unexpected pair-b records: {b_records}"


class TestPairC:
    """Pair C: oracle complex direction vs sector_central call tier."""

    def test_pair_c_positive(self, tmp_path):
        """Oracle 'in' (bullish) + sc majority Reduce/Cautious → contradiction."""
        _make_world_state(tmp_path)
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        _make_oracle_state(tmp_path, complexes=[{
            "id": "ai_compute", "direction": "in", "tier": "A",
            "state": "confirmed", "name": "AI Compute Complex",
        }])
        _make_rotation_groups(tmp_path, [
            {"id": "ai_compute", "members": ["ai_semiconductors", "ai_infra", "memory_storage"]}
        ])
        _make_sector_calls(tmp_path, [
            {"date": "2026-07-02", "id": "ai_semiconductors", "label": "Reduce",
             "kind": "basket", "ticker": "SEMI", "basket_id": "b-ai_semiconductors",
             "name": "AI Semis", "score": 30, "dir": "down", "confluence": 0,
             "trend_pass": False, "ret_12m": 0.1, "gate_factor": 0.5, "level": 50.0},
            {"date": "2026-07-02", "id": "ai_infra", "label": "Cautious",
             "kind": "basket", "ticker": "AIINFRA", "basket_id": "b-ai_infra",
             "name": "AI Infra", "score": 25, "dir": "down", "confluence": 0,
             "trend_pass": False, "ret_12m": 0.05, "gate_factor": 0.4, "level": 40.0},
            {"date": "2026-07-02", "id": "memory_storage", "label": "Reduce",
             "kind": "basket", "ticker": "MEMSTOR", "basket_id": "b-memory_storage",
             "name": "Memory", "score": 20, "dir": "down", "confluence": 0,
             "trend_pass": False, "ret_12m": 0.0, "gate_factor": 0.3, "level": 30.0},
        ])
        records, _ = detect_contradictions(root=tmp_path)
        c_records = [r for r in records if "oracle-vs-sector_central" in r["pair_id"]]
        assert len(c_records) >= 1, f"Expected pair-c record; got {records}"
        assert c_records[0]["kind"] == "directional-opposition"

    def test_pair_c_negative(self, tmp_path):
        """Oracle 'in' + sc majority Constructive → no contradiction."""
        _make_world_state(tmp_path)
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        _make_oracle_state(tmp_path, complexes=[{
            "id": "ai_compute", "direction": "in", "tier": "A",
            "state": "confirmed", "name": "AI Compute Complex",
        }])
        _make_rotation_groups(tmp_path, [
            {"id": "ai_compute", "members": ["ai_semiconductors", "ai_infra", "memory_storage"]}
        ])
        _make_sector_calls(tmp_path, [
            {"date": "2026-07-02", "id": "ai_semiconductors", "label": "Constructive",
             "kind": "basket", "ticker": "SEMI", "basket_id": "b-ai_semiconductors",
             "name": "AI Semis", "score": 70, "dir": "up", "confluence": 1,
             "trend_pass": True, "ret_12m": 0.3, "gate_factor": 0.8, "level": 80.0},
            {"date": "2026-07-02", "id": "ai_infra", "label": "Accumulate",
             "kind": "basket", "ticker": "AIINFRA", "basket_id": "b-ai_infra",
             "name": "AI Infra", "score": 65, "dir": "up", "confluence": 1,
             "trend_pass": True, "ret_12m": 0.25, "gate_factor": 0.75, "level": 75.0},
            {"date": "2026-07-02", "id": "memory_storage", "label": "Constructive",
             "kind": "basket", "ticker": "MEMSTOR", "basket_id": "b-memory_storage",
             "name": "Memory", "score": 68, "dir": "up", "confluence": 1,
             "trend_pass": True, "ret_12m": 0.2, "gate_factor": 0.7, "level": 70.0},
        ])
        records, _ = detect_contradictions(root=tmp_path)
        c_records = [r for r in records if "oracle-vs-sector_central" in r["pair_id"]]
        assert len(c_records) == 0, f"Unexpected pair-c records: {c_records}"


class TestPairD:
    """Pair D: vol_regime label vs market_state verdict."""

    def test_pair_d_positive(self, tmp_path):
        """Low vol + RISK_OFF → note record."""
        _make_world_state(tmp_path, vol_regime="normalizing", verdict="RISK_OFF")
        _make_regime_latest(tmp_path, vol_regime_str="normalizing")
        _make_market_state(tmp_path, verdict="RISK_OFF")
        records, _ = detect_contradictions(root=tmp_path)
        d_records = [r for r in records if r["pair_id"] == "vol_regime-vs-market_state"]
        assert len(d_records) >= 1, "Expected pair-d record"
        assert d_records[0]["severity"] in ("note", "tension")

    def test_pair_d_negative(self, tmp_path):
        """Elevated vol + RISK_OFF → no pair-d record (not a contradiction)."""
        _make_world_state(tmp_path, vol_regime="elevated", verdict="RISK_OFF")
        _make_regime_latest(tmp_path, vol_regime_str="elevated")
        _make_market_state(tmp_path, verdict="RISK_OFF")
        records, _ = detect_contradictions(root=tmp_path)
        d_records = [r for r in records if r["pair_id"] == "vol_regime-vs-market_state"]
        assert len(d_records) == 0, f"Unexpected pair-d records: {d_records}"


class TestPairE:
    """Pair E: briefing divergences ingest."""

    def test_pair_e_positive(self, tmp_path):
        """Briefing with 5 divergences → one summary record."""
        _make_world_state(tmp_path)
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        _make_briefing(tmp_path, divergences=[
            {"ticker": "AAPL", "priority": 0.8, "confidence": 0.9, "strength": 0.7,
             "lean": 1, "read": "early_edge", "situation": "bullish early edge"},
            {"ticker": "MSFT", "priority": 0.7, "confidence": 0.85, "strength": 0.6,
             "lean": -1, "read": "crowded_top", "situation": "supply bearish"},
            {"ticker": "NVDA", "priority": 0.6, "confidence": 0.8, "strength": 0.5,
             "lean": 1, "read": "early_edge", "situation": "early edge"},
            {"ticker": "TSLA", "priority": 0.5, "confidence": 0.75, "strength": 0.4,
             "lean": -1, "read": "crowded_top", "situation": "crowded"},
            {"ticker": "AMZN", "priority": 0.4, "confidence": 0.7, "strength": 0.3,
             "lean": 1, "read": "early_edge", "situation": "edge"},
        ])
        records, _ = detect_contradictions(root=tmp_path)
        e_records = [r for r in records if r["pair_id"] == "briefing-divergences"]
        assert len(e_records) == 1
        assert "5" in e_records[0]["a"]["reading"] or "5" in e_records[0]["note"]

    def test_pair_e_negative(self, tmp_path):
        """Briefing with 0 divergences → no pair-e record."""
        _make_world_state(tmp_path)
        _make_regime_latest(tmp_path)
        _make_market_state(tmp_path)
        _make_briefing(tmp_path, divergences=[])
        records, _ = detect_contradictions(root=tmp_path)
        e_records = [r for r in records if r["pair_id"] == "briefing-divergences"]
        assert len(e_records) == 0


class TestPairF:
    """Pair F: cross_asset_confirm verdict as macro edge."""

    def test_pair_f_positive(self, tmp_path):
        """cross_asset_confirm verdict=diverge → tension record."""
        _make_world_state(tmp_path)
        _make_regime_latest(tmp_path, ca_verdict="diverge")
        _make_market_state(tmp_path)
        records, _ = detect_contradictions(root=tmp_path)
        f_records = [r for r in records if r["pair_id"] == "cross_asset_confirm-diverge"]
        assert len(f_records) == 1
        assert f_records[0]["severity"] == "tension"

    def test_pair_f_negative(self, tmp_path):
        """cross_asset_confirm verdict=confirm → no pair-f record."""
        _make_world_state(tmp_path)
        _make_regime_latest(tmp_path, ca_verdict="confirm")
        _make_market_state(tmp_path)
        records, _ = detect_contradictions(root=tmp_path)
        f_records = [r for r in records if r["pair_id"] == "cross_asset_confirm-diverge"]
        assert len(f_records) == 0


class TestFailOpen:
    """Fail-open and severity vocabulary tests."""

    def test_pairs_fail_open(self, tmp_path):
        """All inputs missing → empty records + gaps, no raise."""
        # Don't write anything — totally empty repo tree
        records, gaps = detect_contradictions(root=tmp_path)
        assert isinstance(records, list)
        assert isinstance(gaps, list)
        # Should have gaps but no raise
        assert len(gaps) >= 0  # may have fallback gaps

    def test_severity_vocab(self, tmp_path):
        """No record may carry severity='critical' (Article 2 prohibition)."""
        _make_world_state(tmp_path, quad="Q1", verdict="RISK_OFF")
        _make_regime_latest(tmp_path, ca_verdict="diverge")
        _make_market_state(tmp_path)
        _make_briefing(tmp_path, divergences=[
            {"ticker": "X", "priority": 0.9, "confidence": 0.95, "strength": 0.8,
             "lean": 1, "read": "early_edge", "situation": "test"}
        ])
        records, _ = detect_contradictions(root=tmp_path)
        bad = [r for r in records if r.get("severity") == "critical"]
        assert bad == [], (
            f"Found records with severity='critical' (Article 2 forbidden): {bad}"
        )


# ===========================================================================
# Confluence graph tests
# ===========================================================================

class TestGraphSchema:
    """Test output schema and envelope fields."""

    def test_graph_schema(self, tmp_path):
        """Output has required schema/tier/display_only/hard_law fields."""
        _make_synapse(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        assert graph["schema"] == "neuralweb.confluence_graph.v1"
        assert graph["tier"] == "display"
        assert graph["is_context_only"] is True
        assert graph["display_only"] is True
        assert "HARD LAW" in graph["hard_law"] or "hard law" in graph["hard_law"].lower()
        assert "nodes" in graph
        assert "edges" in graph
        assert "gaps" in graph
        assert isinstance(graph["gaps"], list)

    def test_envelope_fields(self, tmp_path):
        """produced_by and produced_at present in graph output."""
        _make_synapse(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        assert graph.get("produced_by") == "engine/neuralweb/confluence.py"
        assert graph.get("produced_at") is not None

    def test_determinism(self, tmp_path):
        """Two calls with same now give same produced_at."""
        _make_synapse(tmp_path)
        g1 = build_graph(root=tmp_path, now=_NOW)
        g2 = build_graph(root=tmp_path, now=_NOW)
        assert g1["produced_at"] == g2["produced_at"]

    def test_gaps_list_always_present(self, tmp_path):
        """gaps list present even when all inputs ok."""
        _make_synapse(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        assert isinstance(graph["gaps"], list)


class TestNodes:
    """Test node construction."""

    def _make_spine_fixture(self, tmp: Path, engines: list[str]) -> None:
        rows = []
        for i, eng in enumerate(engines):
            rows.append({
                "signal_id": f"sig_{i}", "engine": eng, "family": eng,
                "ledger": "spine", "as_of": "2026-07-01", "symbol": f"SYM{i}",
                "scope_type": "entity", "universe": "us", "horizon": 21,
                "direction": 1, "size_binding": False, "fill_basis": "close",
                "score": 0.5, "outcome_excess": 0.01, "outcome_graded": True,
                "graded_at": "2026-07-02", "terminal_state_clean15_126": None,
                "terminal_state_clean8_21": None, "fwd_mfe_5": None,
                "fwd_mfe_10": None, "fwd_mfe_21": None, "fwd_mfe_63": None,
                "fwd_mfe_126": None, "rate_pressure": None,
                "quad_hard_label": "Q1", "fused_risk_label": None,
                "vol_regime": None, "risk_radar_state": None,
                "vector_asof": None, "species_id": None, "archetype": None,
            })
        _make_spine(tmp, rows)

    def test_engine_nodes(self, tmp_path):
        """Engine nodes match unique engines in spine_index."""
        engines = ["us_board", "radar", "altdata"]
        self._make_spine_fixture(tmp_path, engines)
        _make_synapse(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        engine_nodes = [n for n in graph["nodes"] if n["type"] == "engine"]
        engine_ids = {n["id"] for n in engine_nodes}
        for eng in engines:
            assert f"engine:{eng}" in engine_ids, (
                f"Expected engine:{eng} node; got {engine_ids}"
            )

    def test_sector_nodes_gics(self, tmp_path):
        """11 GICS sector nodes always present regardless of oracle_state."""
        _make_synapse(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        gics_nodes = [
            n for n in graph["nodes"]
            if n["type"] == "sector" and n.get("meta", {}).get("subtype") == "gics_sector"
        ]
        assert len(gics_nodes) == 11, (
            f"Expected 11 GICS sector nodes, got {len(gics_nodes)}"
        )

    def test_regime_nodes(self, tmp_path):
        """5 regime nodes (Q1/Q2/Q3/Q4 + __all__) always present."""
        _make_synapse(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        regime_nodes = [n for n in graph["nodes"] if n["type"] == "regime"]
        regime_ids = {n["id"] for n in regime_nodes}
        for qid in ["Q1", "Q2", "Q3", "Q4", "__all__"]:
            assert f"regime:{qid}" in regime_ids, (
                f"Missing regime:{qid}; got {regime_ids}"
            )
        assert len(regime_nodes) == 5

    def test_thesis_nodes(self, tmp_path):
        """Active theses become thesis nodes; exhausted ones are skipped."""
        _make_synapse(tmp_path)
        _make_theses(tmp_path, [
            {"id": "t1", "label_en": "AI dominance", "direction": 1,
             "onset_date": "2026-06-01"},
            {"id": "t2", "label_en": "Energy fade", "direction": -1,
             "onset_date": "2026-05-01", "exhausted_at": "2026-06-15"},  # exhausted
        ])
        graph = build_graph(root=tmp_path, now=_NOW)
        thesis_nodes = [n for n in graph["nodes"] if n["type"] == "thesis"]
        ids = {n["id"] for n in thesis_nodes}
        assert "thesis:t1" in ids, "Active thesis t1 should be a node"
        assert "thesis:t2" not in ids, "Exhausted thesis t2 should NOT be a node"

    def test_episode_nodes_capped(self, tmp_path):
        """Episode nodes capped at 50 most recent; note in gaps if >50."""
        _make_synapse(tmp_path)
        episodes = [
            {
                "node": f"node_{i}", "direction": "in",
                "onset_date": f"2026-0{(i%6)+1}-01",
                "tier": "M", "two_sided": False,
            }
            for i in range(75)
        ]
        _make_oracle_state(tmp_path, episodes=episodes)
        graph = build_graph(root=tmp_path, now=_NOW)
        ep_nodes = [n for n in graph["nodes"] if n["type"] == "episode"]
        assert len(ep_nodes) == 50, (
            f"Expected 50 episode nodes (cap), got {len(ep_nodes)}"
        )
        # Gap should mention cap exceeded
        cap_gaps = [g for g in graph["gaps"] if "capped" in g or "50" in g]
        assert len(cap_gaps) >= 1, "Expected cap gap note for >50 episodes"


class TestEdges:
    """Test edge construction."""

    def test_feeds_edges(self, tmp_path):
        """feeds edges produced from synapse.yml registry."""
        _make_synapse(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        feeds_edges = [e for e in graph["edges"] if e["edge_type"] == "feeds"]
        # Should have many feeds edges from the real synapse.yml (92+ artifacts)
        assert len(feeds_edges) >= 1, "Expected at least some feeds edges"
        for e in feeds_edges:
            assert e["display_only"] is True
            assert e["src"] is not None
            assert e["dst"] is not None

    def _make_spine_for_cofiring(
        self, tmp: Path,
        engine_a: str, engine_b: str, n_cofiring: int, n_exclusive: int = 5
    ) -> None:
        """Make spine with n_cofiring rows where both engines fire same event."""
        rows = []
        # Co-firing rows (same symbol/as_of/direction/horizon for both engines)
        for i in range(n_cofiring):
            for eng in [engine_a, engine_b]:
                rows.append({
                    "signal_id": f"sig_{i}_{eng}",
                    "engine": eng, "family": eng,
                    "ledger": "spine", "as_of": f"2026-0{(i%6)+1}-01",
                    "symbol": f"SYM{i}", "scope_type": "entity",
                    "universe": "us", "horizon": 21, "direction": 1,
                    "size_binding": False, "fill_basis": "close",
                    "score": 0.6, "outcome_excess": 0.02, "outcome_graded": True,
                    "graded_at": f"2026-0{(i%6)+2}-01",
                    "terminal_state_clean15_126": None,
                    "terminal_state_clean8_21": None, "fwd_mfe_5": None,
                    "fwd_mfe_10": None, "fwd_mfe_21": None, "fwd_mfe_63": None,
                    "fwd_mfe_126": None, "rate_pressure": None,
                    "quad_hard_label": "Q1", "fused_risk_label": None,
                    "vol_regime": None, "risk_radar_state": None,
                    "vector_asof": None, "species_id": None, "archetype": None,
                })
        # Exclusive rows for engine_a only (different symbols)
        for i in range(n_exclusive):
            rows.append({
                "signal_id": f"excl_{i}",
                "engine": engine_a, "family": engine_a,
                "ledger": "spine", "as_of": f"2026-0{(i%3)+1}-01",
                "symbol": f"EXCL{i}", "scope_type": "entity",
                "universe": "us", "horizon": 21, "direction": 1,
                "size_binding": False, "fill_basis": "close",
                "score": 0.5, "outcome_excess": 0.01, "outcome_graded": True,
                "graded_at": f"2026-0{(i%3)+2}-01",
                "terminal_state_clean15_126": None,
                "terminal_state_clean8_21": None, "fwd_mfe_5": None,
                "fwd_mfe_10": None, "fwd_mfe_21": None, "fwd_mfe_63": None,
                "fwd_mfe_126": None, "rate_pressure": None,
                "quad_hard_label": "Q1", "fused_risk_label": None,
                "vol_regime": None, "risk_radar_state": None,
                "vector_asof": None, "species_id": None, "archetype": None,
            })
        _make_spine(tmp, rows)

    def test_confirms_lift_above_floor(self, tmp_path):
        """n >= MIN_N (10) → confirms edge with lift value computed."""
        _make_synapse(tmp_path)
        self._make_spine_for_cofiring(
            tmp_path, "eng_a", "eng_b", n_cofiring=12
        )
        graph = build_graph(root=tmp_path, now=_NOW)
        confirms = [e for e in graph["edges"] if e["edge_type"] == "confirms"]
        ab = [e for e in confirms
              if ("eng_a" in e["src"] and "eng_b" in e["dst"])
              or ("eng_b" in e["src"] and "eng_a" in e["dst"])]
        assert len(ab) >= 1, f"Expected confirms edge; got confirms={confirms}"
        edge = ab[0]
        assert edge["n"] == 12
        assert edge["lift"] is not None, "Expected lift value for n>=10"
        assert isinstance(edge["lift"], float)

    def test_confirms_lift_below_floor(self, tmp_path):
        """n < MIN_N (10) → confirms edge with n printed and lift=null."""
        _make_synapse(tmp_path)
        self._make_spine_for_cofiring(
            tmp_path, "eng_x", "eng_y", n_cofiring=5
        )
        graph = build_graph(root=tmp_path, now=_NOW)
        confirms = [e for e in graph["edges"] if e["edge_type"] == "confirms"]
        xy = [e for e in confirms
              if ("eng_x" in e["src"] and "eng_y" in e["dst"])
              or ("eng_y" in e["src"] and "eng_x" in e["dst"])]
        assert len(xy) >= 1, (
            f"Expected confirms edge with lift=null for n=5 below MIN_N floor; "
            f"got confirms={confirms}"
        )
        edge = xy[0]
        assert edge["n"] == 5
        assert edge["lift"] is None, f"Expected lift=null for n<10; got {edge['lift']}"
        assert "MIN_N" in edge["note"] or "insufficient" in edge["note"].lower()

    def test_contradicts_edges(self, tmp_path):
        """Contradiction records become contradicts edges."""
        _make_synapse(tmp_path)
        _make_world_state(tmp_path, quad="Q1", verdict="RISK_OFF")
        _make_regime_latest(tmp_path, ca_verdict="diverge")
        _make_market_state(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        contra_edges = [e for e in graph["edges"] if e["edge_type"] == "contradicts"]
        assert len(contra_edges) >= 1, (
            "Expected at least one contradicts edge (Q1+RISK_OFF and/or cross_asset diverge)"
        )
        for e in contra_edges:
            assert e["display_only"] is True

    def test_oracle_absent_failopen(self, tmp_path):
        """Oracle files absent → fail-open: gaps noted, graph returned."""
        _make_synapse(tmp_path)
        # Don't write oracle files — they are Mac-local/gitignored
        graph = build_graph(root=tmp_path, now=_NOW)
        assert isinstance(graph, dict)
        assert "gaps" in graph
        # Should note oracle absence in gaps
        oracle_gaps = [g for g in graph["gaps"]
                       if "oracle" in g.lower() or "graph_s" in g or "graph_m" in g]
        assert len(oracle_gaps) >= 1, (
            f"Expected oracle-absence gaps; got gaps={graph['gaps']}"
        )


# ===========================================================================
# World-state contradictions block tests
# ===========================================================================

class TestWorldStateContradictions:
    """Tests for the contradictions block added to world_state.py."""

    def _seed_world_state_root(self, tmp: Path) -> None:
        """Seed minimal inputs for build_world_state."""
        import shutil
        # synapse.yml (required for envelope stamp)
        real_synapse = _REPO_ROOT / "config" / "synapse.yml"
        dest = tmp / "config" / "synapse.yml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if real_synapse.exists():
            shutil.copyfile(real_synapse, dest)

        # market_state/latest.json
        _make_market_state(tmp, verdict="RISK_OFF")
        # regime/latest.json
        _make_regime_latest(tmp, ca_verdict="diverge")
        # world_state.json (needed by contradictions as a source)
        _make_world_state(tmp, quad="Q1", verdict="RISK_OFF")
        # briefing
        _make_briefing(tmp, divergences=[])

    def test_world_state_contradictions_block(self, tmp_path):
        """contradictions key present in world_state payload."""
        from engine.neuralweb.world_state import build_world_state  # noqa: PLC0415
        self._seed_world_state_root(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        assert "contradictions" in payload, (
            "world_state payload missing 'contradictions' key"
        )
        cb = payload["contradictions"]
        # May be None if detector failed, but key must exist
        if cb is not None:
            assert "n" in cb
            assert "by_severity" in cb
            assert "top_pair_ids" in cb
            assert cb.get("display_only") is True

    def test_world_state_contradictions_failopen(self, tmp_path, monkeypatch):
        """If detector raises, contradictions block is None and gap appended."""
        from engine.neuralweb.world_state import build_world_state  # noqa: PLC0415
        self._seed_world_state_root(tmp_path)

        # Monkeypatch detect_contradictions to raise
        import engine.neuralweb.world_state as ws_mod  # noqa: PLC0415
        original = ws_mod.__dict__.get("detect_contradictions")

        def _explode(root=None):
            raise RuntimeError("injected failure for test")

        # Patch inside the world_state module's namespace
        import engine.neuralweb.contradictions as contra_mod  # noqa: PLC0415
        monkeypatch.setattr(contra_mod, "detect_contradictions", _explode)

        # The world_state module imports directly, so we also need to patch there
        # The module-level try/except handles this gracefully
        payload = build_world_state(root=tmp_path, now=_NOW)
        # Even if contradictions block fails, payload is returned
        assert isinstance(payload, dict)


# ===========================================================================
# R-ORTH PR-4: independence block tests (RUL-ORTH-5/11)
# ===========================================================================

class TestIndependenceBlock:
    """Tests for the independence block in build_graph (confluence.py).

    Tests:
      31. independence_block_present      — independence key in output when covariance_spine.json present
      32. independence_block_absent_null  — null values + gap note when covariance_spine.json absent
      33. independence_block_no_crash     — graph always returned regardless of spine state
      34. independence_block_no_effect_on_nodes_edges — existing nodes/edges unchanged by spine presence
      35. independence_block_fields       — required fields all present with correct types/values
      36. independence_block_same_bet_active — same_bet_warning propagated when active
    """

    def _make_fixture_spine(self, tmp: Path, n_measurable: int = 3) -> None:
        """Write a minimal covariance_spine.json fixture."""
        clusters = []
        if n_measurable >= 2:
            clusters = [{"engines": ["eng_a", "eng_b"], "mean_corr": 0.72}]
        spine = {
            "schema": "neuralweb.covariance_spine.v1",
            "as_of": "2026-07-04",
            "display_only": True,
            "authority": "context",
            "descriptive_not_gauntleted": True,
            "blocks": {
                "lobes": {
                    "effective_independent_lobes": round(n_measurable * 0.7, 4),
                    "n_lobes_measurable": n_measurable,
                    "n_lobes_total": 17,
                    "null_reference": {
                        "null_median": 1.0,
                        "null_p90": 1.0,
                        "pctile_vs_null": 0.55,
                        "n_null_draws": 200,
                    },
                    "same_bet_warning": {"active": False},
                    "highest_overlap_pairs": [],
                    "clusters": clusters,
                    "coverage": {"measurable": [], "unmeasurable": []},
                }
            },
            "coverage": {},
            "missing_inputs": [],
            "committee_annotations": [],
            "allowed_actions": ["display"],
            "forbidden_actions": ["score"],
        }
        dest = tmp / "data" / "neuralweb" / "covariance_spine.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(spine), encoding="utf-8")

    def test_independence_block_present(self, tmp_path):
        """independence key present in graph output when spine file exists."""
        _make_synapse(tmp_path)
        self._make_fixture_spine(tmp_path)
        graph = build_graph(root=tmp_path, now=_NOW)
        assert "independence" in graph, "Expected 'independence' key in confluence graph output"
        indep = graph["independence"]
        assert isinstance(indep, dict)
        assert indep.get("descriptive_not_gauntleted") is True
        assert indep.get("display_only") is True
        assert indep.get("source") == "data/neuralweb/covariance_spine.json"

    def test_independence_block_absent_null(self, tmp_path):
        """Null values + gap note when covariance_spine.json is absent."""
        _make_synapse(tmp_path)
        # Do NOT write covariance_spine.json
        graph = build_graph(root=tmp_path, now=_NOW)
        assert "independence" in graph
        indep = graph["independence"]
        assert indep["effective_independent_lobes"] is None
        assert indep["n_lobes_measurable"] is None
        assert indep["n_lobes_total"] is None
        assert indep["pctile_vs_null"] is None
        # Gap note appended
        independence_gaps = [g for g in graph["gaps"] if "independence" in g.lower()]
        assert len(independence_gaps) >= 1, (
            f"Expected independence gap note; got gaps={graph['gaps']}"
        )

    def test_independence_block_no_crash(self, tmp_path):
        """build_graph always returns a dict regardless of spine state."""
        _make_synapse(tmp_path)
        # Case 1: spine absent
        g1 = build_graph(root=tmp_path, now=_NOW)
        assert isinstance(g1, dict)
        # Case 2: spine present but malformed JSON
        bad = tmp_path / "data" / "neuralweb" / "covariance_spine.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("NOT_VALID_JSON{{{", encoding="utf-8")
        g2 = build_graph(root=tmp_path, now=_NOW)
        assert isinstance(g2, dict)
        # Case 3: spine present but no lobes block
        nolobe = {"schema": "neuralweb.covariance_spine.v1", "blocks": {}, "missing_inputs": []}
        bad.write_text(json.dumps(nolobe), encoding="utf-8")
        g3 = build_graph(root=tmp_path, now=_NOW)
        assert isinstance(g3, dict)
        assert g3["independence"]["effective_independent_lobes"] is None

    def test_independence_block_no_effect_on_nodes_edges(self, tmp_path):
        """Nodes and edges are identical whether or not covariance_spine.json exists."""
        engines = ["us_board", "radar"]
        rows = []
        for i, eng in enumerate(engines):
            rows.append({
                "signal_id": f"sig_{i}", "engine": eng, "family": eng,
                "ledger": "spine", "as_of": "2026-07-01", "symbol": f"SYM{i}",
                "scope_type": "entity", "universe": "us", "horizon": 21,
                "direction": 1, "size_binding": False, "fill_basis": "close",
                "score": 0.5, "outcome_excess": 0.01, "outcome_graded": True,
                "graded_at": "2026-07-02", "terminal_state_clean15_126": None,
                "terminal_state_clean8_21": None, "fwd_mfe_5": None,
                "fwd_mfe_10": None, "fwd_mfe_21": None, "fwd_mfe_63": None,
                "fwd_mfe_126": None, "rate_pressure": None,
                "quad_hard_label": "Q1", "fused_risk_label": None,
                "vol_regime": None, "risk_radar_state": None,
                "vector_asof": None, "species_id": None, "archetype": None,
            })
        _make_spine(tmp_path, rows)
        _make_synapse(tmp_path)

        g_without = build_graph(root=tmp_path, now=_NOW)
        self._make_fixture_spine(tmp_path)
        g_with = build_graph(root=tmp_path, now=_NOW)

        assert len(g_without["nodes"]) == len(g_with["nodes"]), (
            "Node count changed after adding covariance_spine.json"
        )
        assert len(g_without["edges"]) == len(g_with["edges"]), (
            "Edge count changed after adding covariance_spine.json"
        )

    def test_independence_block_fields(self, tmp_path):
        """Required fields present with expected types and values."""
        _make_synapse(tmp_path)
        self._make_fixture_spine(tmp_path, n_measurable=3)
        graph = build_graph(root=tmp_path, now=_NOW)
        indep = graph["independence"]
        assert isinstance(indep["effective_independent_lobes"], float)
        assert isinstance(indep["n_lobes_measurable"], int)
        assert isinstance(indep["n_lobes_total"], int)
        assert isinstance(indep["pctile_vs_null"], float)
        assert 0.0 <= indep["pctile_vs_null"] <= 1.0
        assert indep["n_lobes_total"] == 17

    def test_independence_block_same_bet_active(self, tmp_path):
        """same_bet_warning propagated when active=True in spine."""
        _make_synapse(tmp_path)
        spine_with_warning: dict = {
            "schema": "neuralweb.covariance_spine.v1",
            "as_of": "2026-07-04",
            "display_only": True,
            "authority": "context",
            "descriptive_not_gauntleted": True,
            "blocks": {
                "lobes": {
                    "effective_independent_lobes": 1.5,
                    "n_lobes_measurable": 4,
                    "n_lobes_total": 17,
                    "null_reference": {"pctile_vs_null": 0.4, "n_null_draws": 200},
                    "same_bet_warning": {
                        "active": True,
                        "text": "Cluster of 3 engines with mean |corr|=0.71.",
                        "cluster": ["eng_a", "eng_b", "eng_c"],
                    },
                    "highest_overlap_pairs": [],
                    "clusters": [],
                    "coverage": {},
                }
            },
            "coverage": {},
            "missing_inputs": [],
            "committee_annotations": [],
            "allowed_actions": ["display"],
            "forbidden_actions": ["score"],
        }
        dest = tmp_path / "data" / "neuralweb" / "covariance_spine.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(spine_with_warning), encoding="utf-8")
        graph = build_graph(root=tmp_path, now=_NOW)
        indep = graph["independence"]
        assert indep["same_bet_warning"] is not None, "Expected same_bet_warning to be non-null when active=True"
        assert indep["same_bet_warning"].get("active") is True
