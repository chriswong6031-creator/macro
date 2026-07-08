"""Tests for scripts/build_factor_intelligence_state.py.

Follows tmp_path + monkeypatch conventions of tests/test_world_state.py.
All synthetic fixtures; ZERO real data/ writes.

Tests
-----
a) no panel → artifact written, panel.available=false, gaps populated,
   hypotheses not-visible-in-tree, exit 0
b) synthetic panel + ledgers + standouts → digest values correct, history row
   appended, fire_coordinates rows written with correct fields incl. top_contrib_streams
c) same-day rerun → no duplicate history/fire rows
d) allowed_actions always has may_rank=false, may_originate=false, authority_source present
e) site mirror byte-identical to data copy
f) (W1) contrib prefix fix: REAL production column names (contrib_mkt_20d etc.) produce
   non-empty top_contrib_streams
g) (W1) personality enrichment: snapshot_fresh basis on fire_coordinates rows when
   stock_personality.json present
h) (W1) carry-forward date matching: panel date lags board as_of → rows still found
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_factor_intelligence_state import (
    build_factor_intelligence_state,
    _dumps_safe,
    _load_jsonl_as_of_keys,
    _load_jsonl_ticker_keys,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AS_OF = "2026-07-03"


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _make_synthetic_panel(root: Path, as_of: str) -> None:
    """Create a minimal synthetic panel with the columns the builder needs."""
    panel_dir = root / "data" / "factordata" / "panel"
    month = as_of[:7]
    part_dir = panel_dir / month
    part_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    tickers = ["AAPL", "MSFT", "GOOGL"]
    # Fill 65 dates (above 60-date floor)
    import pandas as _pd
    dates = _pd.bdate_range(end=as_of, periods=65).strftime("%Y-%m-%d").tolist()
    for d in dates:
        for t in tickers:
            rows.append({
                "date": d,
                "ticker": t,
                "style_regime": "growth",
                "style_regime_pending": None,
                "dna_class": "quality_growth",
                "alibi_share_20d": 0.45 if t == "AAPL" else 0.85,
                "twin_bleed_flag": t == "MSFT",
                "twin_rel_20d": -0.02 if t == "MSFT" else 0.01,
                "alpha_z_house": 1.2,
                # R-CI2a: REAL production column names (contrib_<stream>_20d)
                "contrib_mkt_20d": 0.05,
                "contrib_sector_20d": 0.03,
                "contrib_growth_20d": -0.01,
            })
    df = pd.DataFrame(rows)
    df.to_parquet(part_dir / "panel.parquet", index=False)


def _make_standouts(root: Path, as_of: str, tickers: list[str]) -> None:
    buy = [{"ticker": t, "signal": {"tier_cascade": "T1"}} for t in tickers]
    _write_json(root / "site" / "factordata" / "us_standouts.json", {
        "as_of": as_of,
        "buy": buy,
        "reduce": [],
    })


def _make_contradictions(root: Path, as_of: str) -> None:
    rec = {
        "pair_id": f"borrowed_strength:MSFT:{as_of}",
        "a": {"artifact": "us_standouts.json", "reading": "T1 fire for MSFT"},
        "b": {"reading": f"alibi_share_20d=0.8500 >= Q80=0.7200 (...)"},
        "kind": "label-tension",
        "severity": "note",
        "as_of": as_of,
        "note": "test",
        "display_only": True,
        "ticker": "MSFT",
        "date": as_of,
    }
    _write_jsonl(root / "data" / "neuralweb" / "factor_contradictions.jsonl", [rec])


def _make_firings(root: Path, as_of: str) -> None:
    row = {"trigger_key": f"borrowed_strength:MSFT:{as_of}", "asof": as_of, "scope_key": "MSFT"}
    _write_jsonl(root / "data" / "reflexes" / "factor_attention" / "firings.jsonl", [row])


def _make_probation(root: Path) -> None:
    _write_json(root / "data" / "reflexes" / "factor_attention" / "probation.json", {
        "granted": False, "tier": "A0/A1 shadow", "reason": "insufficient-n",
    })


def _patch_world_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch _compose_factor_weather to return a stub (no real panel needed)."""
    def _fake_weather(root=None):
        return {
            "style_regime": "growth",
            "style_regime_pending": None,
            "style_regime_hold_days": 5,
            "factor_leader": "profitability",
            "factor_leader_ic": 0.014,
            "etf_pulse_summary": "IWF/IWD_20d=+0.0100",
            "ratio_iwf_iwd_20d": 0.01,
            "ratio_qqq_spy_20d": 0.02,
            "ratio_iwm_spy_20d": -0.01,
            "display_only": True,
        }
    monkeypatch.setattr(
        "scripts.build_factor_intelligence_state._build_factor_weather_block",
        lambda repo, gaps: _fake_weather(),
    )


# ---------------------------------------------------------------------------
# Test (a): no panel → artifact written with honest gaps
# ---------------------------------------------------------------------------

def test_no_panel_honest_gaps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No panel → artifact written, panel.available=False, gaps populated, hypotheses not-visible."""
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    # Artifact is always written
    assert state["schema"] == "neuralweb.factor_intelligence_state.v1"
    assert state["as_of"] == _AS_OF
    assert state["is_context_only"] is True
    assert state["display_only"] is True

    # Panel block: available=False
    assert state["panel"]["available"] is False
    assert state["panel"]["history_floor_met"] is False

    # Gaps populated (no-panel note)
    assert any("no-panel" in g or "absent" in g.lower() for g in state["gaps"])

    # Hypotheses: all not-visible-in-tree
    for i in range(1, 6):
        assert state["hypotheses"][f"h{i}"]["status"] == "not-visible-in-tree"
        assert state["hypotheses"][f"h{i}"]["authority"] == "display"

    # Data artifact was written to disk
    data_path = tmp_path / "data" / "neuralweb" / "factor_intelligence_state.json"
    assert data_path.exists()

    # Site mirror exists
    site_path = tmp_path / "site" / "neuralwebdata" / "factor_intelligence_state.json"
    assert site_path.exists()

    # History row exists
    hist_path = tmp_path / "data" / "factordata" / "factor_state_history.jsonl"
    assert hist_path.exists()
    rows = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["as_of"] == _AS_OF


# ---------------------------------------------------------------------------
# Test (b): synthetic panel + ledgers → digest and coordinates correct
# ---------------------------------------------------------------------------

def test_synthetic_panel_digest_and_coords(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthetic panel: history digest correct, fire_coordinates with top_contrib_streams."""
    _make_synthetic_panel(tmp_path, _AS_OF)
    _make_standouts(tmp_path, _AS_OF, ["AAPL", "MSFT"])
    _make_contradictions(tmp_path, _AS_OF)
    _make_firings(tmp_path, _AS_OF)
    _make_probation(tmp_path)
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    # Panel available
    assert state["panel"]["available"] is True
    assert state["panel"]["history_floor_met"] is True
    assert state["panel"]["n_dates"] is not None and state["panel"]["n_dates"] >= 60

    # Contradictions: MSFT should show up
    pair_g = state["contradictions"]["pair_g"]
    assert pair_g["n_today"] == 1
    assert pair_g["dormant"] is False
    assert pair_g["latest"][0]["ticker"] == "MSFT"
    # alibi_share_20d extracted from b.reading
    assert pair_g["latest"][0]["alibi_share_20d"] == pytest.approx(0.85, abs=0.01)

    # Attention block: n_firings from our stub
    att = state["attention"]["factor_attention"]
    assert att["n_firings"] == 1
    assert att["granted"] is False

    # History digest
    hist_path = tmp_path / "data" / "factordata" / "factor_state_history.jsonl"
    rows = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["as_of"] == _AS_OF
    assert row["style_regime"] == "growth"
    assert row["panel_n_dates"] is not None and row["panel_n_dates"] >= 60
    assert row["dna_distribution"].get("quality_growth", 0) > 0
    # alibi cross-sectional stats
    assert row["alibi_cross_median"] is not None
    assert row["alibi_cross_q80"] is not None

    # Fire coordinates: AAPL and MSFT with top_contrib_streams
    fire_path = tmp_path / "data" / "factordata" / "fire_coordinates.jsonl"
    assert fire_path.exists()
    fire_rows = [json.loads(l) for l in fire_path.read_text().splitlines() if l.strip()]
    assert len(fire_rows) == 2
    tickers_in_coords = {r["ticker"] for r in fire_rows}
    assert "AAPL" in tickers_in_coords
    assert "MSFT" in tickers_in_coords
    for fr in fire_rows:
        assert fr["factor_model"] == "v1"
        assert fr["as_of"] == _AS_OF
        assert fr["tier"] == "T1"
        assert "top_contrib_streams" in fr
        # R-CI2a: REAL column names (contrib_mkt_20d etc.) must produce non-empty list
        assert isinstance(fr["top_contrib_streams"], list)
        assert len(fr["top_contrib_streams"]) >= 1, (
            f"top_contrib_streams empty — contrib prefix fix may have regressed: {fr}"
        )
        # All entries are stream names (strings) extracted from between 'contrib_' and '_20d'
        for s in fr["top_contrib_streams"]:
            assert isinstance(s, str)
            # stream names must not contain the prefix/suffix artifacts
            assert not s.startswith("contrib_"), f"stream key still has 'contrib_' prefix: {s}"
            assert not s.endswith("_20d"), f"stream key still has '_20d' suffix: {s}"
        # dna_class is present (from synthetic panel)
        assert fr["dna_class"] == "quality_growth"
        # v2 schema fields present
        assert "fire_coord_schema" in fr, "v2 schema field missing"
        assert fr["fire_coord_schema"] == "fire_coordinates.v2"
        # personality_basis field present
        assert "personality_basis" in fr, "personality_basis field missing from v2 schema"
        # No disallowed fields
        for bad in ("rank", "score", "recommendation", "buy", "sell", "hold"):
            assert bad not in fr


# ---------------------------------------------------------------------------
# Test (c): same-day rerun → no duplicate history/fire rows
# ---------------------------------------------------------------------------

def test_same_day_rerun_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running twice on the same as_of does not duplicate history or fire rows."""
    _make_synthetic_panel(tmp_path, _AS_OF)
    _make_standouts(tmp_path, _AS_OF, ["AAPL"])
    _patch_world_state(monkeypatch)

    build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)
    build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    hist_path = tmp_path / "data" / "factordata" / "factor_state_history.jsonl"
    hist_rows = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
    # Exactly 1 history row despite 2 runs
    assert len(hist_rows) == 1

    fire_path = tmp_path / "data" / "factordata" / "fire_coordinates.jsonl"
    if fire_path.exists():
        fire_rows = [json.loads(l) for l in fire_path.read_text().splitlines() if l.strip()]
        # Each (as_of, ticker) pair appears exactly once
        keys = [(r["as_of"], r["ticker"]) for r in fire_rows]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Test (d): allowed_actions always correct (RUL-NW9)
# ---------------------------------------------------------------------------

def test_allowed_actions_always_correct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """allowed_actions always has may_rank=False, may_originate=False, authority_source present."""
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)
    aa = state["allowed_actions"]

    assert aa["may_rank"] is False
    assert aa["may_originate"] is False
    assert aa["may_deescalate"] is False
    assert "authority_source" in aa
    assert "constitution.grant_authority" in aa["authority_source"]
    assert "mirror, never a switch" in aa["authority_source"]


# ---------------------------------------------------------------------------
# Test (e): site mirror byte-identical to data copy
# ---------------------------------------------------------------------------

def test_site_mirror_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """site/neuralwebdata/factor_intelligence_state.json is byte-identical to data copy."""
    _patch_world_state(monkeypatch)

    build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    data_path = tmp_path / "data" / "neuralweb" / "factor_intelligence_state.json"
    site_path = tmp_path / "site" / "neuralwebdata" / "factor_intelligence_state.json"

    assert data_path.exists(), "data copy missing"
    assert site_path.exists(), "site mirror missing"
    assert data_path.read_bytes() == site_path.read_bytes(), "site mirror not byte-identical"


# ---------------------------------------------------------------------------
# Test: board_coordinates absent when panel absent
# ---------------------------------------------------------------------------

def test_board_coords_empty_no_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no panel, latest_board_coordinates is empty list."""
    _make_standouts(tmp_path, _AS_OF, ["AAPL", "MSFT"])
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)
    assert state["latest_board_coordinates"] == []
    # Gap note present
    assert any("board_coord" in g.lower() or "board" in g.lower() for g in state["gaps"])


# ---------------------------------------------------------------------------
# Test: NaN values are coerced to null in JSON output
# ---------------------------------------------------------------------------

def test_nan_coerced_to_null(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NaN/Inf values are coerced to null in the JSON output (never 'NaN' literal)."""
    def _nan_weather(root=None):
        return {
            "style_regime": None, "style_regime_pending": None,
            "style_regime_hold_days": None, "factor_leader": None,
            "factor_leader_ic": float("nan"),  # intentionally NaN
            "etf_pulse_summary": None,
            "ratio_iwf_iwd_20d": float("inf"),
            "ratio_qqq_spy_20d": None, "ratio_iwm_spy_20d": None,
            "display_only": True,
        }
    monkeypatch.setattr(
        "scripts.build_factor_intelligence_state._build_factor_weather_block",
        lambda repo, gaps: _nan_weather(),
    )

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)
    data_path = tmp_path / "data" / "neuralweb" / "factor_intelligence_state.json"
    raw_text = data_path.read_text(encoding="utf-8")

    # JSON must not contain the literal 'NaN' or 'Infinity'
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text

    # Round-trip: must parse cleanly
    parsed = json.loads(raw_text)
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Test (B1 regression): panel absent → fire_coordinates gap in PERSISTED artifact
# ---------------------------------------------------------------------------

def test_b1_fire_coordinates_gap_in_persisted_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1 regression: with panel absent, persisted factor_intelligence_state.json gaps list
    contains the fire_coordinates gap note, and the history row's gaps_count matches
    the persisted artifact's len(gaps)."""
    # Provide standouts so the panel-absent branch of _build_fire_coordinates fires
    _make_standouts(tmp_path, _AS_OF, ["AAPL", "MSFT"])
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    # The returned state dict must contain the fire_coordinates gap
    fire_coord_gaps = [g for g in state["gaps"] if "fire_coordinates" in g and "panel absent" in g]
    assert fire_coord_gaps, (
        "Expected a 'fire_coordinates: panel absent' gap note in the in-memory state, "
        f"but gaps were: {state['gaps']}"
    )

    # The PERSISTED artifact must also contain the same gap note (B1: written after gap is appended)
    data_path = tmp_path / "data" / "neuralweb" / "factor_intelligence_state.json"
    assert data_path.exists(), "State artifact not written"
    persisted = json.loads(data_path.read_text(encoding="utf-8"))
    persisted_fire_gaps = [
        g for g in persisted["gaps"] if "fire_coordinates" in g and "panel absent" in g
    ]
    assert persisted_fire_gaps, (
        "B1 failure: fire_coordinates gap note was NOT present in the persisted artifact. "
        f"Persisted gaps: {persisted['gaps']}"
    )

    # History row's gaps_count must match the persisted artifact's len(gaps)
    hist_path = tmp_path / "data" / "factordata" / "factor_state_history.jsonl"
    assert hist_path.exists(), "History JSONL not written"
    hist_rows = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
    assert len(hist_rows) == 1
    history_gaps_count = hist_rows[0]["gaps_count"]
    persisted_gaps_count = len(persisted["gaps"])
    assert history_gaps_count == persisted_gaps_count, (
        f"B1 failure: history row gaps_count={history_gaps_count} != "
        f"persisted artifact len(gaps)={persisted_gaps_count}"
    )


# ---------------------------------------------------------------------------
# Test (B2): null-tier buy-lane entry → in board_coordinates, NOT in fire_coordinates
# ---------------------------------------------------------------------------

def _make_standouts_mixed_tier(root: Path, as_of: str) -> None:
    """Standouts with one T1-tier entry (AAPL) and one null-tier entry (HELD)."""
    buy = [
        {"ticker": "AAPL", "signal": {"tier_cascade": "T1", "eligible": True}},
        {"ticker": "HELD", "signal": {"tier_cascade": None, "eligible": False}},
    ]
    _write_json(root / "site" / "factordata" / "us_standouts.json", {
        "as_of": as_of,
        "buy": buy,
        "reduce": [],
    })


def test_b2_null_tier_entry_in_board_not_in_fire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B2: a buy-lane entry with tier_cascade=null appears in latest_board_coordinates
    (diagnostic context) but NOT in fire_coordinates (fire tape)."""
    _make_synthetic_panel(tmp_path, _AS_OF)
    # Extend the panel to include HELD ticker
    panel_dir = tmp_path / "data" / "factordata" / "panel"
    month = _AS_OF[:7]
    part_path = panel_dir / month / "panel.parquet"
    existing = pd.read_parquet(part_path)
    import pandas as _pd
    dates = _pd.bdate_range(end=_AS_OF, periods=65).strftime("%Y-%m-%d").tolist()
    extra_rows = [
        {
            "date": d, "ticker": "HELD", "style_regime": "value",
            "style_regime_pending": None, "dna_class": "value_deep",
            "alibi_share_20d": 0.3, "twin_bleed_flag": False,
            "twin_rel_20d": 0.0, "alpha_z_house": 0.5,
            # R-CI2a: REAL production column names
            "contrib_mkt_20d": 0.01, "contrib_sector_20d": 0.02, "contrib_growth_20d": 0.03,
        }
        for d in dates
    ]
    combined = _pd.concat([existing, _pd.DataFrame(extra_rows)], ignore_index=True)
    combined.to_parquet(part_path, index=False)

    _make_standouts_mixed_tier(tmp_path, _AS_OF)
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    # board_coordinates: HELD (null tier) should appear — it's diagnostic context for all buy-lane names
    board_tickers = {entry["ticker"] for entry in state["latest_board_coordinates"]}
    assert "HELD" in board_tickers, (
        f"B2: HELD (null-tier) should be in latest_board_coordinates, but got: {board_tickers}"
    )
    assert "AAPL" in board_tickers, "AAPL (T1) should also be in latest_board_coordinates"

    # fire_coordinates: HELD must NOT appear — null tier_cascade means not a fire
    fire_path = tmp_path / "data" / "factordata" / "fire_coordinates.jsonl"
    assert fire_path.exists(), "fire_coordinates.jsonl not written"
    fire_rows = [json.loads(l) for l in fire_path.read_text().splitlines() if l.strip()]
    fire_tickers = {r["ticker"] for r in fire_rows}
    assert "HELD" not in fire_tickers, (
        f"B2 failure: HELD (null-tier) should NOT be in fire_coordinates, but found: {fire_tickers}"
    )
    assert "AAPL" in fire_tickers, "AAPL (T1) should be in fire_coordinates"

    # A gap/info note about the skipped null-tier entry should be present
    null_tier_gaps = [g for g in state["gaps"] if "null" in g.lower() or "held" in g.lower() or "skipped" in g.lower()]
    assert null_tier_gaps, (
        f"B2: expected a gap note about null-tier skipped entries, gaps were: {state['gaps']}"
    )


# ---------------------------------------------------------------------------
# W1 Test (f): contrib prefix fix — REAL production column names
# ---------------------------------------------------------------------------

def test_w1_contrib_prefix_fix_real_column_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W1 R-CI2a: REAL production column names (contrib_mkt_20d, contrib_sector_20d,
    contrib_growth_20d) produce non-empty top_contrib_streams.

    This is the regression test for the _CONTRIB_PREFIX bug: the old code used
    'contrib_20d_' as a startswith prefix, which matches NOTHING because real
    columns are contrib_<stream>_20d not contrib_20d_<stream>.
    The fix uses _CONTRIB_PATTERN = re.compile(r'^contrib_([a-z_]+)_20d$').
    """
    _make_synthetic_panel(tmp_path, _AS_OF)
    _make_standouts(tmp_path, _AS_OF, ["AAPL", "MSFT", "GOOGL"])
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    fire_path = tmp_path / "data" / "factordata" / "fire_coordinates.jsonl"
    assert fire_path.exists(), "fire_coordinates.jsonl not written"
    fire_rows = [json.loads(l) for l in fire_path.read_text().splitlines() if l.strip()]
    assert len(fire_rows) == 3, f"expected 3 fire rows, got {len(fire_rows)}"

    for fr in fire_rows:
        streams = fr["top_contrib_streams"]
        assert isinstance(streams, list), "top_contrib_streams must be list"
        assert len(streams) >= 1, (
            f"R-CI2a regression: top_contrib_streams is empty for {fr['ticker']}. "
            f"Contrib prefix fix may not have landed. Full row: {fr}"
        )
        # Verify stream names are bare names (mkt, sector, growth) not full column names
        for s in streams:
            assert s in ("mkt", "sector", "size", "growth", "rates", "dollar",
                         "ai_theme", "china"), (
                f"stream name '{s}' is not a known stream key — "
                f"possible prefix/suffix leak from column name"
            )
        # Verify ordering is by descending |value|
        # contrib_mkt_20d=0.05 > contrib_sector_20d=0.03 > contrib_growth_20d=0.01
        assert streams[0] == "mkt", (
            f"expected 'mkt' as top stream (value 0.05), got '{streams[0]}'"
        )


# ---------------------------------------------------------------------------
# W1 Test (g): personality enrichment — snapshot_fresh basis
# ---------------------------------------------------------------------------

def _make_personality_json(root: Path, tickers: list[str]) -> None:
    """Write a minimal stock_personality.json for the given tickers."""
    per_ticker = {
        t: {
            "arch": "momentum_leader",
            "dna": "quality_growth",
            "chart": ["clean_uptrend", "mean_reversion_rubber_band"],
            "own": ["passive_index_magnet"],
            "micro": ["tight_spread_absorber"],
            "modes": ["normal"],
        }
        for t in tickers
    }
    p = root / "site" / "factordata" / "stock_personality.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema": "stock_personality.v1",
        "as_of": _AS_OF,
        "n_tickers": len(tickers),
        "per_ticker": per_ticker,
    }), encoding="utf-8")


def test_w1_personality_enrichment_snapshot_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W1 R-CI3: personality coordinates added to fire_coordinates rows with
    personality_basis='snapshot_fresh' when stock_personality.json is present.
    Tickers absent from the snapshot get personality_basis='absent'.
    """
    _make_synthetic_panel(tmp_path, _AS_OF)
    # AAPL has personality, MSFT does NOT
    _make_personality_json(tmp_path, ["AAPL"])
    _make_standouts(tmp_path, _AS_OF, ["AAPL", "MSFT"])
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=_AS_OF)

    fire_path = tmp_path / "data" / "factordata" / "fire_coordinates.jsonl"
    assert fire_path.exists()
    fire_rows = {
        r["ticker"]: r
        for r in (json.loads(l) for l in fire_path.read_text().splitlines() if l.strip())
    }

    # AAPL: personality_basis='snapshot_fresh', archetype present
    aapl = fire_rows["AAPL"]
    assert aapl["personality_basis"] == "snapshot_fresh", (
        f"expected snapshot_fresh for AAPL, got {aapl['personality_basis']}"
    )
    assert aapl["archetype"] == "momentum_leader"
    assert "clean_uptrend" in aapl["chart_primary"]
    assert aapl["modes"] == ["normal"]
    # v2 schema
    assert aapl["fire_coord_schema"] == "fire_coordinates.v2"

    # MSFT: personality_basis='absent', archetype=None
    msft = fire_rows["MSFT"]
    assert msft["personality_basis"] == "absent", (
        f"expected absent for MSFT (not in snapshot), got {msft['personality_basis']}"
    )
    assert msft["archetype"] is None

    # Regime keys present (may be None if no regime_vector in tmp_path — that's ok)
    for regime_key in ("quad_hard_label", "vol_regime", "risk_radar_state"):
        assert regime_key in aapl, f"v2 regime key '{regime_key}' missing from fire row"


# ---------------------------------------------------------------------------
# W1 Test (h): carry-forward date matching — panel lags behind board as_of
# ---------------------------------------------------------------------------

def _make_synthetic_panel_lagged(root: Path, panel_as_of: str, board_as_of: str) -> None:
    """Create panel where latest date = panel_as_of, but standouts board as_of > panel_as_of."""
    panel_dir = root / "data" / "factordata" / "panel"
    month = panel_as_of[:7]
    part_dir = panel_dir / month
    part_dir.mkdir(parents=True, exist_ok=True)

    import pandas as _pd
    dates = _pd.bdate_range(end=panel_as_of, periods=65).strftime("%Y-%m-%d").tolist()
    rows = []
    for d in dates:
        for t in ["AAPL"]:
            rows.append({
                "date": d, "ticker": t,
                "style_regime": "growth", "style_regime_pending": None,
                "dna_class": "quality_growth",
                "alibi_share_20d": 0.45, "twin_bleed_flag": False,
                "twin_rel_20d": 0.01, "alpha_z_house": 1.2,
                "contrib_mkt_20d": 0.07, "contrib_sector_20d": 0.02,
            })
    pd.DataFrame(rows).to_parquet(part_dir / "panel.parquet", index=False)

    # standouts board as_of is 3 days AHEAD of panel latest date
    _write_json(root / "site" / "factordata" / "us_standouts.json", {
        "as_of": board_as_of,
        "buy": [{"ticker": "AAPL", "signal": {"tier_cascade": "T1"}}],
        "reduce": [],
    })


def test_w1_carry_forward_date_matching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W1 R-CI2b: when panel latest date lags behind standouts board as_of,
    fire_coordinates still finds the ticker by carry-forward (date <= board_as_of).

    Before the fix, the code used exact-date match panel["date"] == board_as_of,
    which returns zero rows when the panel is behind.
    """
    panel_as_of = "2026-07-02"
    board_as_of = "2026-07-06"  # 4 trading days ahead of panel
    _make_synthetic_panel_lagged(tmp_path, panel_as_of, board_as_of)
    _patch_world_state(monkeypatch)

    state = build_factor_intelligence_state(root=tmp_path, as_of_date=board_as_of)

    fire_path = tmp_path / "data" / "factordata" / "fire_coordinates.jsonl"
    assert fire_path.exists(), "fire_coordinates.jsonl not written"
    fire_rows = [json.loads(l) for l in fire_path.read_text().splitlines() if l.strip()]

    assert len(fire_rows) == 1, (
        f"R-CI2b regression: expected 1 fire row but got {len(fire_rows)}. "
        f"Carry-forward date matching may not have landed. "
        f"Gaps: {state['gaps']}"
    )
    fr = fire_rows[0]
    assert fr["ticker"] == "AAPL"
    assert fr["as_of"] == board_as_of
    # panel_date should be the latest available (panel_as_of), not board_as_of
    assert fr["panel_date"] == panel_as_of, (
        f"expected panel_date={panel_as_of}, got {fr.get('panel_date')}"
    )
    # contrib streams should be non-empty (carry-forward row has contrib columns)
    assert len(fr["top_contrib_streams"]) >= 1, (
        f"expected non-empty top_contrib_streams, got {fr['top_contrib_streams']}"
    )
    # No agg_gaps note for AAPL
    agg_gap_notes = [g for g in state["gaps"] if "had no panel row" in g]
    assert not agg_gap_notes, (
        f"Carry-forward fix failure: unexpected 'no panel row' gap: {agg_gap_notes}"
    )
