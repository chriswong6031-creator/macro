"""Hermetic tests for Oracle P9 — Hypothesis Inbox.

engine/oracle/hypothesis_inbox.py

All fixtures are SYNTHETIC — no real data files, no network.
numpy + pandas only (no scipy, no sklearn, no LLM calls).

Test inventory
--------------
A. outside_envelope_fires:
     A planted Tier-S episode with matured 21d outcome OUTSIDE the analogue
     envelope fires an analogue_surprise row.

B. inside_envelope_silent:
     Same setup but realized outcome INSIDE the envelope → no row.

C. detection_miss_fires:
     Planted 3-sigma 10-session rs-change with no episode → fires.

D. detection_miss_active_episode_silent:
     Same 3-sigma move WITH an active episode → stays silent.

E. detection_miss_flood_cap:
     More than 10 candidates → truncated to 10 rows, truncation logged.

F. screen_live_divergence_dedup_per_month:
     Same compound fires once in a month, not twice.

G. first_run_silent_seed:
     First run (no state file) → no rows written, state seeded.

H. torn_inbox_line_tolerated:
     A planted torn JSON line in the inbox does not crash; subsequent read
     skips it and proceeds normally.

I. collector1_crash_does_not_block_collector2:
     Monkeypatched crash in collector 1 (analogue_surprise) does not stop
     detection_miss from running.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest import mock
from datetime import datetime, timezone, date

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers: synthetic fixture builders
# ---------------------------------------------------------------------------

def _make_oracle_dir(tmp_path: Path) -> Path:
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True)
    return oracle_dir


def _make_panel_s(oracle_dir: Path, nodes: list[str], n_dates: int = 30,
                  start: str = "2026-01-02") -> None:
    """Write a synthetic panel_s.parquet under oracle_dir."""
    dates = pd.bdate_range(start=start, periods=n_dates)
    rows = []
    rng = np.random.default_rng(42)
    for node in nodes:
        for d in dates:
            rows.append({
                "node": node,
                "date": d,
                "rs": float(rng.normal(0, 0.01)),
                "ret": float(rng.normal(0, 0.01)),
                "accel_z": float(rng.normal(0, 1)),
                "cohesion": float(rng.uniform(0.3, 0.9)),
                "breadth_50": float(rng.uniform(0.3, 0.9)),
                "washout_w": 0.0,
            })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    df.to_parquet(oracle_dir / "panel_s.parquet")


def _make_panel_s_with_outlier(oracle_dir: Path, nodes: list[str], outlier_node: str,
                                n_dates: int = 30, start: str = "2026-01-02") -> None:
    """Write panel_s with an outlier node that has a +4sigma 10-session move."""
    dates = pd.bdate_range(start=start, periods=n_dates)
    rows = []
    rng = np.random.default_rng(42)
    for node in nodes:
        base_rs = 0.0
        for i, d in enumerate(dates):
            if node == outlier_node and i >= n_dates - 10:
                # Large positive move in last 10 sessions
                delta = 0.05
            else:
                delta = float(rng.normal(0, 0.001))
            base_rs += delta
            rows.append({
                "node": node,
                "date": d,
                "rs": base_rs,
                "ret": delta,
                "accel_z": float(rng.normal(0, 1)),
                "cohesion": float(rng.uniform(0.3, 0.9)),
                "breadth_50": float(rng.uniform(0.3, 0.9)),
                "washout_w": 0.0,
            })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    df.to_parquet(oracle_dir / "panel_s.parquet")


def _make_episodes_s(oracle_dir: Path, episodes: list[dict] | None = None) -> None:
    """Write synthetic episodes_s.parquet."""
    if episodes is None:
        episodes = []
    if not episodes:
        # Empty episodes
        df = pd.DataFrame(columns=[
            "episode_id", "node", "direction", "onset_date",
            "confirmed_date", "undeniable_date", "exhausted_date",
            "outcome_rs_21d", "outcome_mature_21d",
            "outcome_rs_5d", "outcome_mature_5d",
            "outcome_rs_63d", "outcome_mature_63d",
            "peak_accel_z", "breadth_at_onset", "cohesion_at_onset",
            "cohesion_chg_at_onset", "regime_vix_pctile",
            "regime_spy_above_200d", "two_sided", "survivorship_flagged",
        ])
    else:
        df = pd.DataFrame(episodes)
    # Ensure date columns are datetime
    for col in ["onset_date", "confirmed_date", "exhausted_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    df.to_parquet(oracle_dir / "episodes_s.parquet")


def _make_episodes_m(oracle_dir: Path, episodes: list[dict] | None = None) -> None:
    """Write synthetic episodes_m.parquet."""
    if episodes is None:
        episodes = []
    if not episodes:
        df = pd.DataFrame(columns=[
            "episode_id", "node", "direction", "onset_date",
            "confirmed_date", "undeniable_date", "exhausted_date",
            "outcome_rs_21d", "outcome_mature_21d",
        ])
    else:
        df = pd.DataFrame(episodes)
    for col in ["onset_date", "confirmed_date", "exhausted_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    df.to_parquet(oracle_dir / "episodes_m.parquet")


def _make_panel_m(oracle_dir: Path, nodes: list[str], n_dates: int = 30,
                  start: str = "2026-01-02") -> None:
    """Write a synthetic panel_m.parquet."""
    dates = pd.bdate_range(start=start, periods=n_dates)
    rows = []
    rng = np.random.default_rng(99)
    for node in nodes:
        base_rs = 0.0
        for d in dates:
            delta = float(rng.normal(0, 0.001))
            base_rs += delta
            rows.append({
                "node": node,
                "date": d,
                "rs": base_rs,
                "ret": delta,
                "accel_z": float(rng.normal(0, 1)),
                "cohesion": float(rng.uniform(0.3, 0.9)),
                "breadth_50": float(rng.uniform(0.3, 0.9)),
                "washout_w": 0.0,
            })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    df.to_parquet(oracle_dir / "panel_m.parquet")


# ---------------------------------------------------------------------------
# A. outside_envelope_fires
# ---------------------------------------------------------------------------

def test_outside_envelope_fires(tmp_path: Path, monkeypatch) -> None:
    """Planted episode with matured 21d outcome OUTSIDE analogue envelope fires."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    nodes = ["XLK", "XLF", "XLE", "XLB", "XLC"]
    # Panel must span from before the analogue episodes (2024-01-01) to after the query onset
    # (2026-07-10) to give find_analogues enough session indices to pass the leakage law.
    # 670 business days ≈ 2024-01-02 to 2026-07-10.
    _make_panel_s(oracle_dir, nodes, n_dates=670, start="2024-01-02")

    # Analogue episodes (old, well before 2026-07-04) with known 21d outcomes
    analogues = []
    onset_dates = pd.bdate_range("2024-01-01", periods=7)
    for i, d in enumerate(onset_dates):
        analogues.append({
            "episode_id": f"XLK::in::{d.date()}::hist{i}",
            "node": nodes[i % len(nodes)],
            "direction": "in",
            "onset_date": d,
            "confirmed_date": d + pd.Timedelta(days=5),
            "undeniable_date": None,
            "exhausted_date": d + pd.Timedelta(days=30),
            "outcome_rs_21d": 0.03 + i * 0.005,  # range ~3-6%
            "outcome_mature_21d": True,
            "outcome_rs_5d": 0.01,
            "outcome_mature_5d": True,
            "outcome_rs_63d": 0.05,
            "outcome_mature_63d": True,
            "peak_accel_z": 2.5,
            "breadth_at_onset": 0.6,
            "cohesion_at_onset": 0.5,
            "cohesion_chg_at_onset": 0.1,
            "regime_vix_pctile": 0.4,
            "regime_spy_above_200d": 1.0,
            "two_sided": False,
            "survivorship_flagged": False,
        })

    # Query episode: onset AFTER 2026-07-04, matured, outcome WAY outside [3-6%] envelope
    query_episode = {
        "episode_id": "XLK::in::2026-07-10::99",
        "node": "XLK",
        "direction": "in",
        "onset_date": pd.Timestamp("2026-07-10"),
        "confirmed_date": pd.Timestamp("2026-07-15"),
        "undeniable_date": None,
        "exhausted_date": None,
        "outcome_rs_21d": 0.20,      # 20% — WAY above the ~3-6% envelope
        "outcome_mature_21d": True,
        "outcome_rs_5d": 0.05,
        "outcome_mature_5d": True,
        "outcome_rs_63d": None,
        "outcome_mature_63d": False,
        "peak_accel_z": 2.5,
        "breadth_at_onset": 0.6,
        "cohesion_at_onset": 0.5,
        "cohesion_chg_at_onset": 0.1,
        "regime_vix_pctile": 0.4,
        "regime_spy_above_200d": 1.0,
        "two_sided": False,
        "survivorship_flagged": False,
    }

    all_episodes = analogues + [query_episode]
    _make_episodes_s(oracle_dir, all_episodes)

    # Pre-seed state (NOT first run) — empty graded list
    state_path = oracle_dir / "hypothesis_state.json"
    state_path.write_text(json.dumps({"graded_episode_ids": []}))

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox
    counts = run_hypothesis_inbox(data_dir)

    # Should fire at least 1 analogue_surprise row
    assert counts["analogue_surprise"] >= 1, (
        f"Expected analogue_surprise >= 1, got {counts}"
    )

    # Verify row in inbox
    inbox_path = oracle_dir / "hypothesis_inbox.jsonl"
    assert inbox_path.exists()
    rows = [json.loads(l) for l in inbox_path.read_text().splitlines() if l.strip()]
    surprise_rows = [r for r in rows if r.get("type") == "analogue_surprise"]
    assert len(surprise_rows) >= 1
    row = surprise_rows[0]
    assert row["node"] == "XLK"
    assert row["realized_da_21d"] == pytest.approx(0.20, abs=0.001)
    assert row["envelope_hi"] < 0.20  # outside
    assert row["converted"] is None


# ---------------------------------------------------------------------------
# B. inside_envelope_silent
# ---------------------------------------------------------------------------

def test_inside_envelope_silent(tmp_path: Path) -> None:
    """Planted episode outcome INSIDE the analogue envelope → no row written."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    nodes = ["XLK", "XLF", "XLE", "XLB", "XLC"]
    _make_panel_s(oracle_dir, nodes, n_dates=670, start="2024-01-02")

    analogues = []
    onset_dates = pd.bdate_range("2024-01-01", periods=7)
    for i, d in enumerate(onset_dates):
        analogues.append({
            "episode_id": f"XLK::in::{d.date()}::hist{i}",
            "node": nodes[i % len(nodes)],
            "direction": "in",
            "onset_date": d,
            "confirmed_date": d + pd.Timedelta(days=5),
            "undeniable_date": None,
            "exhausted_date": d + pd.Timedelta(days=30),
            "outcome_rs_21d": 0.03 + i * 0.005,
            "outcome_mature_21d": True,
            "outcome_rs_5d": 0.01,
            "outcome_mature_5d": True,
            "outcome_rs_63d": 0.05,
            "outcome_mature_63d": True,
            "peak_accel_z": 2.5,
            "breadth_at_onset": 0.6,
            "cohesion_at_onset": 0.5,
            "cohesion_chg_at_onset": 0.1,
            "regime_vix_pctile": 0.4,
            "regime_spy_above_200d": 1.0,
            "two_sided": False,
            "survivorship_flagged": False,
        })

    # Query: outcome INSIDE the envelope (4%)
    query_episode = {
        "episode_id": "XLK::in::2026-07-10::99",
        "node": "XLK",
        "direction": "in",
        "onset_date": pd.Timestamp("2026-07-10"),
        "confirmed_date": pd.Timestamp("2026-07-15"),
        "undeniable_date": None,
        "exhausted_date": None,
        "outcome_rs_21d": 0.04,      # 4% — squarely inside [3-6%] envelope
        "outcome_mature_21d": True,
        "outcome_rs_5d": 0.01,
        "outcome_mature_5d": True,
        "outcome_rs_63d": None,
        "outcome_mature_63d": False,
        "peak_accel_z": 2.5,
        "breadth_at_onset": 0.6,
        "cohesion_at_onset": 0.5,
        "cohesion_chg_at_onset": 0.1,
        "regime_vix_pctile": 0.4,
        "regime_spy_above_200d": 1.0,
        "two_sided": False,
        "survivorship_flagged": False,
    }

    all_episodes = analogues + [query_episode]
    _make_episodes_s(oracle_dir, all_episodes)

    state_path = oracle_dir / "hypothesis_state.json"
    state_path.write_text(json.dumps({"graded_episode_ids": []}))

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox
    counts = run_hypothesis_inbox(data_dir)

    assert counts["analogue_surprise"] == 0, (
        f"Expected 0 analogue_surprise rows (inside envelope), got {counts}"
    )


# ---------------------------------------------------------------------------
# C. detection_miss_fires
# ---------------------------------------------------------------------------

def test_detection_miss_fires(tmp_path: Path) -> None:
    """3-sigma 10-session rs-change with no episode → detection_miss row fires."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    nodes = ["XLK", "XLF", "XLE", "XLB", "XLC", "XLU", "XLV"]
    outlier = "XLK"
    _make_panel_s_with_outlier(oracle_dir, nodes, outlier_node=outlier, n_dates=25)
    _make_episodes_s(oracle_dir)  # empty episodes
    _make_episodes_m(oracle_dir)

    # Pre-seed state (not first run)
    state_path = oracle_dir / "hypothesis_state.json"
    state_path.write_text(json.dumps({"graded_episode_ids": []}))

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox
    counts = run_hypothesis_inbox(data_dir)

    assert counts["detection_miss"] >= 1, (
        f"Expected at least 1 detection_miss row, got {counts}"
    )

    inbox_path = oracle_dir / "hypothesis_inbox.jsonl"
    rows = [json.loads(l) for l in inbox_path.read_text().splitlines() if l.strip()]
    dm_rows = [r for r in rows if r.get("type") == "detection_miss"]
    assert any(r["node"] == outlier for r in dm_rows), (
        f"Expected outlier node {outlier} in detection_miss rows, got {[r['node'] for r in dm_rows]}"
    )


# ---------------------------------------------------------------------------
# D. detection_miss_active_episode_silent
# ---------------------------------------------------------------------------

def test_detection_miss_active_episode_silent(tmp_path: Path) -> None:
    """Same 3-sigma move WITH an active episode → stays silent."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    nodes = ["XLK", "XLF", "XLE", "XLB", "XLC", "XLU", "XLV"]
    outlier = "XLK"
    _make_panel_s_with_outlier(oracle_dir, nodes, outlier_node=outlier, n_dates=25)

    # Active episode for the outlier node within the window
    active_episode = {
        "episode_id": "XLK::in::2026-01-20::1",
        "node": "XLK",
        "direction": "in",
        "onset_date": pd.Timestamp("2026-01-20"),
        "confirmed_date": None,
        "exhausted_date": None,
        "outcome_rs_21d": None,
        "outcome_mature_21d": False,
    }
    _make_episodes_s(oracle_dir, [active_episode])
    _make_episodes_m(oracle_dir)

    state_path = oracle_dir / "hypothesis_state.json"
    state_path.write_text(json.dumps({"graded_episode_ids": []}))

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox
    counts = run_hypothesis_inbox(data_dir)

    inbox_path = oracle_dir / "hypothesis_inbox.jsonl"
    if inbox_path.exists():
        rows = [json.loads(l) for l in inbox_path.read_text().splitlines() if l.strip()]
        dm_rows = [r for r in rows if r.get("type") == "detection_miss" and r["node"] == outlier]
        assert len(dm_rows) == 0, (
            f"Expected no detection_miss for {outlier} (active episode present), got {dm_rows}"
        )


# ---------------------------------------------------------------------------
# E. detection_miss_flood_cap
# ---------------------------------------------------------------------------

def test_detection_miss_flood_cap(tmp_path: Path, caplog) -> None:
    """More than 10 candidates → truncated to 10 rows, truncation is logged."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    # Create 200 normal nodes near zero + 15 outlier nodes with massive moves.
    # With 200 normals (rs_chg≈0) anchoring the mean/std, the 15 outliers
    # (rs_chg≈1.0) achieve cross-sectional |z| ≈ 3.6 — comfortably above 2.0.
    # This ensures > _DETECTION_FLOOD_CAP candidates so the truncation fires.
    n_outliers = 15
    n_normal = 200
    outlier_nodes = [f"OUT{i:02d}" for i in range(n_outliers)]
    normal_nodes = [f"NRM{i:03d}" for i in range(n_normal)]
    nodes_all = outlier_nodes + normal_nodes
    n_dates = 25
    dates = pd.bdate_range(start="2026-01-02", periods=n_dates)
    rng = np.random.default_rng(77)
    rows = []
    for i, node in enumerate(nodes_all):
        base_rs = 0.0
        is_outlier = node.startswith("OUT")
        for j, d in enumerate(dates):
            if is_outlier and j >= n_dates - 10:
                delta = 0.10   # large positive move per session
            else:
                delta = float(rng.normal(0, 0.00001))  # near-zero noise
            base_rs += delta
            rows.append({
                "node": node,
                "date": d,
                "rs": base_rs,
                "ret": delta,
                "accel_z": float(rng.normal(0, 1)),
                "cohesion": 0.5,
                "breadth_50": 0.5,
                "washout_w": 0.0,
            })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    df.to_parquet(oracle_dir / "panel_s.parquet")

    # Minimal panel_m with different nodes (no overlap with outliers)
    _make_panel_m(oracle_dir, ["MNODE1", "MNODE2", "MNODE3"], n_dates=25)

    _make_episodes_s(oracle_dir)
    _make_episodes_m(oracle_dir)

    state_path = oracle_dir / "hypothesis_state.json"
    state_path.write_text(json.dumps({"graded_episode_ids": []}))

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox

    with caplog.at_level(logging.WARNING, logger="engine.oracle.hypothesis_inbox"):
        counts = run_hypothesis_inbox(data_dir)

    # Flood cap: at most 10 detection_miss rows
    assert counts["detection_miss"] <= 10, (
        f"Flood cap not respected: {counts['detection_miss']} rows (should be <= 10)"
    )

    # Truncation should be logged at WARNING level
    assert any("flood cap" in r.message.lower() or "truncat" in r.message.lower()
               for r in caplog.records), (
        "Expected a flood-cap warning log message"
    )


# ---------------------------------------------------------------------------
# F. screen_live_divergence_dedup_per_month
# ---------------------------------------------------------------------------

def test_screen_live_divergence_dedup_per_month(tmp_path: Path) -> None:
    """Same compound divergence fires once per month, not twice."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path
    compounds_dir = oracle_dir / "compounds"
    compounds_dir.mkdir(parents=True)

    # Create a compound with screened positive + live negative
    compound = {
        "id": "TEST_COMPOUND_A",
        "status": "accruing",
        "effect_63d": 0.015,       # screened: positive
        "live_n": 12,
        "live_effect": -0.008,     # live: negative → divergence
        "universe": {"tier": "s"},
        "horizons": [21, 63],
    }
    (compounds_dir / "registry.jsonl").write_text(json.dumps(compound) + "\n")

    # Create live_ledger with 12 mature rows, all negative excess_63d
    live_rows = []
    for i in range(12):
        live_rows.append({
            "compound_id": "TEST_COMPOUND_A",
            "node": f"XLK",
            "fire_date": f"2026-0{(i % 9) + 1}-01",
            "grammar_version": "1.1.0",
            "registered_at": "2026-06-01T00:00:00Z",
            "outcome_mature": True,
            "excess_21d": -0.005,
            "excess_63d": -0.008,   # negative
        })
    (compounds_dir / "live_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in live_rows) + "\n"
    )

    # Pre-seed state
    state_path = oracle_dir / "hypothesis_state.json"
    state_path.write_text(json.dumps({"graded_episode_ids": []}))

    _make_episodes_s(oracle_dir)
    _make_episodes_m(oracle_dir)
    _make_panel_s(oracle_dir, ["XLK"], n_dates=20)
    _make_panel_m(oracle_dir, ["XLK"], n_dates=20)

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox

    # Run once
    counts1 = run_hypothesis_inbox(data_dir)
    assert counts1["screen_live_divergence"] == 1, (
        f"Expected 1 screen_live_divergence on first run, got {counts1}"
    )

    # Run again same day (same month) → deduped: should not add another row
    counts2 = run_hypothesis_inbox(data_dir)
    assert counts2["screen_live_divergence"] == 0, (
        f"Expected 0 screen_live_divergence on second run (same month), got {counts2}"
    )


# ---------------------------------------------------------------------------
# G. first_run_silent_seed
# ---------------------------------------------------------------------------

def test_first_run_silent_seed(tmp_path: Path) -> None:
    """First run (no state file) → 0 rows written, state file created."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    nodes = ["XLK", "XLF", "XLE"]
    _make_panel_s_with_outlier(oracle_dir, nodes, outlier_node="XLK", n_dates=25)
    _make_episodes_s(oracle_dir)
    _make_episodes_m(oracle_dir)
    _make_panel_m(oracle_dir, nodes, n_dates=25)

    # No state file at all
    state_path = oracle_dir / "hypothesis_state.json"
    assert not state_path.exists()

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox
    counts = run_hypothesis_inbox(data_dir)

    # ALL collectors must produce 0 rows on first run
    assert counts["total"] == 0, (
        f"First run must produce 0 rows; got {counts}"
    )

    # State file must be created
    assert state_path.exists(), "hypothesis_state.json must be created after first run"
    state = json.loads(state_path.read_text())
    assert "graded_episode_ids" in state or "sentinel_log_line_count" in state, (
        "State must contain graded_episode_ids or sentinel_log_line_count after first run"
    )

    # Inbox should not exist (no rows → no file written)
    inbox_path = oracle_dir / "hypothesis_inbox.jsonl"
    if inbox_path.exists():
        lines = [l for l in inbox_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 0, f"First run: inbox must be empty, got {lines}"


# ---------------------------------------------------------------------------
# H. torn_inbox_line_tolerated
# ---------------------------------------------------------------------------

def test_torn_inbox_line_tolerated(tmp_path: Path) -> None:
    """A torn JSON line in the inbox is skipped; subsequent read proceeds normally."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    inbox_path = oracle_dir / "hypothesis_inbox.jsonl"

    # Plant a valid row followed by a torn line
    valid_row = {
        "id": "sentinel::panel_drift::2026-07-01T00:00:00+00:00",
        "type": "sentinel",
        "pit_stamp": "2026-07-01T00:00:00+00:00",
        "converted": None,
        "detail_en": "test row",
        "detail_zh": "test row zh",
    }
    torn_line = '{"id": "bad_json", "type": "sentinel", BROKEN'
    inbox_path.write_text(
        json.dumps(valid_row) + "\n" + torn_line + "\n"
    )

    # Read IDs — must not crash; torn line skipped; valid row ID extracted
    from engine.oracle.hypothesis_inbox import _read_inbox_ids
    ids = _read_inbox_ids(inbox_path)
    assert valid_row["id"] in ids, (
        f"Valid row ID should be in read_inbox_ids result; got {ids}"
    )
    # torn line should not appear as ID
    assert "bad_json" not in ids


# ---------------------------------------------------------------------------
# I. collector1_crash_does_not_block_collector2
# ---------------------------------------------------------------------------

def test_collector1_crash_does_not_block_collector2(tmp_path: Path, monkeypatch) -> None:
    """Monkeypatched crash in analogue_surprise doesn't stop detection_miss."""
    oracle_dir = _make_oracle_dir(tmp_path)
    data_dir = tmp_path

    nodes = ["XLK", "XLF", "XLE", "XLB", "XLC", "XLU", "XLV"]
    outlier = "XLK"
    _make_panel_s_with_outlier(oracle_dir, nodes, outlier_node=outlier, n_dates=25)
    _make_episodes_s(oracle_dir)
    _make_episodes_m(oracle_dir)
    _make_panel_m(oracle_dir, nodes, n_dates=25)

    state_path = oracle_dir / "hypothesis_state.json"
    state_path.write_text(json.dumps({"graded_episode_ids": []}))

    # Monkeypatch collector 1 to crash
    import engine.oracle.hypothesis_inbox as hib

    def _crashing_collector(*args, **kwargs):
        raise RuntimeError("simulated collector-1 crash")

    monkeypatch.setattr(hib, "_collect_analogue_surprise", _crashing_collector)

    from engine.oracle.hypothesis_inbox import run_hypothesis_inbox
    # Should not raise
    counts = run_hypothesis_inbox(data_dir)

    # analogue_surprise should be 0 (crashed), but detection_miss should still run
    assert counts["analogue_surprise"] == 0, "Crashed collector returns 0"
    # detection_miss should have fired since collector 2 is independent
    assert counts["detection_miss"] >= 1, (
        f"Collector 2 should have run despite collector 1 crash; got {counts}"
    )
