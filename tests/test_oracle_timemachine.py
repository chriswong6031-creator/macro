"""Hermetic tests for engine/oracle/timemachine.py — Oracle P6 Time Machine.

ALL fixtures are synthetic (no network, no real data files).
Tests:

(a) Chunk values reconcile with panel values (quantization tolerance 0.005)
(b) Chunk size budget: each chunk < 400 KB serialised
(c) Episode feed dates match underlying DataFrame (onset_date round-trip)
(d) Manifest lists every chunk file produced
(e) No NaN leakage into JSON (null/None instead)
(f) Registry ids are dense 0-based integers
(g) Tier-M skips months where accel_z is 100% null
(h) Tier-M emits all trading days (daily granularity, no Friday-only filter)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.timemachine import (
    build_registry_s,
    build_registry_m,
    build_chunks_s,
    build_chunks_m,
    build_episode_feed,
    build_manifest,
)


# ── synthetic fixtures ────────────────────────────────────────────────────────

def _make_panel(
    nodes: list[str],
    dates: list[str],
    rs_seed: int = 0,
    accel_z_seed: int = 1,
    null_accel_fraction: float = 0.0,
) -> pd.DataFrame:
    """Minimal panel with rs + accel_z; optional NaN injection for accel_z."""
    rng = np.random.default_rng(rs_seed)
    az_rng = np.random.default_rng(accel_z_seed)
    records = []
    ts_dates = pd.to_datetime(dates)
    for dt in ts_dates:
        for n in nodes:
            rs = float(rng.normal(0, 0.05))
            az = float(az_rng.normal(0, 1))
            if null_accel_fraction > 0 and az_rng.random() < null_accel_fraction:
                az = float("nan")
            records.append({"node": n, "date": dt, "rs": rs, "accel_z": az})
    df = pd.DataFrame(records).set_index(["node", "date"])
    return df


def _friday_dates(n: int = 8, start: str = "2022-02-04") -> list[str]:
    """Return n consecutive Fridays starting from start (which must be a Friday)."""
    base = pd.Timestamp(start)
    assert base.weekday() == 4, "start must be Friday"
    return [(base + pd.Timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(n)]


def _make_episodes(nodes: list[str]) -> pd.DataFrame:
    """Minimal episodes DataFrame with all required columns."""
    records = [
        {
            "episode_id": f"{n}::in::2022-03-04::1",
            "node": n,
            "direction": "in",
            "onset_date": pd.Timestamp("2022-03-04"),
            "confirmed_date": pd.Timestamp("2022-03-10"),
            "undeniable_date": pd.Timestamp("2022-03-18"),
            "exhausted_date": pd.Timestamp("2022-04-01"),
            "two_sided": True,
            "paired_episode_id": f"{n}::out::2022-03-04::1",
            "peak_accel_z": 2.5,
            "survivorship_flagged": False,
        }
        for i, n in enumerate(nodes)
    ]
    return pd.DataFrame(records)


def _simple_registry(n: int = 3, tier: str = "m") -> list[dict]:
    names = [f"node{i}" for i in range(n)]
    return [
        {"id": i, "name": n, "name_zh": None, "theme": "TestTheme", "tier": tier}
        for i, n in enumerate(names)
    ]


# ── (a) Chunk values reconcile with panel values ──────────────────────────────

def test_chunk_values_match_panel_s():
    """Tier-S chunk rs/accel_z matches panel values within quantization tolerance."""
    nodes = ["XLK", "XLE", "XLV"]
    # Use daily dates spanning two quarters so we get two chunks
    dates = pd.bdate_range("2022-01-03", "2022-06-30").strftime("%Y-%m-%d").tolist()
    panel = _make_panel(nodes, dates, rs_seed=10)
    registry = [
        {"id": i, "name": n, "name_zh": None, "theme": "Sectors", "tier": "s"}
        for i, n in enumerate(nodes)
    ]
    chunks = build_chunks_s(panel, registry)
    assert len(chunks) >= 2, "Expected at least two quarterly chunks"

    chunk = chunks[0]
    date_str = chunk["dates"][0]
    date_ts = pd.Timestamp(date_str)

    # Look up same values from panel
    for reg in registry:
        nid = str(reg["id"])
        name = reg["name"]
        vals_in_chunk = chunk["data"][nid]
        # First date's values
        chunk_rs, chunk_az = vals_in_chunk[0]
        panel_rs = float(panel.loc[(name, date_ts), "rs"])
        panel_az = float(panel.loc[(name, date_ts), "accel_z"])
        # Tolerance: rounding to 2dp means max error of 0.005
        assert abs(chunk_rs - panel_rs) <= 0.005, (
            f"{name} rs mismatch: chunk={chunk_rs} panel={panel_rs:.4f}"
        )
        assert abs(chunk_az - panel_az) <= 0.005, (
            f"{name} accel_z mismatch: chunk={chunk_az} panel={panel_az:.4f}"
        )


def test_chunk_values_match_panel_m():
    """Tier-M chunk values match panel (daily granularity, all trading days)."""
    nodes = [f"node{i}" for i in range(5)]
    # Build a month of daily data
    dates = pd.bdate_range("2022-02-01", "2022-02-28").strftime("%Y-%m-%d").tolist()
    panel = _make_panel(nodes, dates, rs_seed=20)
    registry = _simple_registry(5)

    chunks = build_chunks_m(panel, registry)
    assert len(chunks) >= 1

    chunk = chunks[0]
    # All panel dates for the month must appear in the chunk
    assert set(chunk["dates"]) == set(dates), (
        "Tier-M chunk should contain all trading days, not just Fridays"
    )

    # Spot-check values for first date
    date_ts = pd.Timestamp(chunk["dates"][0])
    for reg in registry:
        nid = str(reg["id"])
        name = reg["name"]
        try:
            panel_rs = float(panel.loc[(name, date_ts), "rs"])
            panel_az = float(panel.loc[(name, date_ts), "accel_z"])
        except KeyError:
            continue
        v = chunk["data"][nid][0]
        if v is not None:
            assert abs(v[0] - panel_rs) <= 0.005
            if v[1] is not None and not math.isnan(panel_az):
                assert abs(v[1] - panel_az) <= 0.005


# ── (b) Chunk size budget < 400 KB ───────────────────────────────────────────

def test_chunk_size_budget_s():
    """Each Tier-S quarterly chunk serialises to < 400 KB."""
    nodes = [f"X{i:02d}" for i in range(11)]
    # One quarter of daily data
    dates = pd.bdate_range("2022-01-03", "2022-03-31").strftime("%Y-%m-%d").tolist()
    panel = _make_panel(nodes, dates)
    registry = [
        {"id": i, "name": n, "name_zh": None, "theme": "S", "tier": "s"}
        for i, n in enumerate(nodes)
    ]
    chunks = build_chunks_s(panel, registry)
    for chunk in chunks:
        obj = {"dates": chunk["dates"], "data": chunk["data"]}
        size = len(json.dumps(obj, separators=(",", ":")))
        assert size < 400 * 1024, (
            f"Chunk {chunk['period']} exceeds 400 KB: {size / 1024:.1f} KB"
        )


def test_chunk_size_budget_m():
    """Each Tier-M monthly chunk serialises to < 400 KB (daily granularity)."""
    nodes = [f"node{i}" for i in range(354)]  # full node count
    # Use a full month of daily trading days (~21 dates) — realistic daily budget
    daily_dates = pd.bdate_range("2022-02-01", "2022-02-28").strftime("%Y-%m-%d").tolist()
    panel = _make_panel(nodes, daily_dates)
    registry = [
        {"id": i, "name": n, "name_zh": None, "theme": "T", "tier": "subsector"}
        for i, n in enumerate(nodes)
    ]
    chunks = build_chunks_m(panel, registry)
    for chunk in chunks:
        obj = {"dates": chunk["dates"], "data": chunk["data"]}
        size = len(json.dumps(obj, separators=(",", ":")))
        assert size < 400 * 1024, (
            f"Chunk {chunk['period']} exceeds 400 KB: {size / 1024:.1f} KB"
        )


# ── (c) Episode feed dates match DataFrame ────────────────────────────────────

def test_episode_feed_dates_match():
    """Episode onset_date round-trips correctly through the feed."""
    nodes = ["alpha", "beta", "gamma"]
    ep_m = _make_episodes(nodes)
    ep_s = _make_episodes(["XLK"])
    feed = build_episode_feed(ep_m, ep_s)

    assert "episodes" in feed
    assert "presets" in feed

    # Find an episode for 'alpha'
    alpha_ep = next((e for e in feed["episodes"] if e["node"] == "alpha"), None)
    assert alpha_ep is not None
    assert alpha_ep["onset_date"] == "2022-03-04"
    assert alpha_ep["confirmed_date"] == "2022-03-10"
    assert alpha_ep["direction"] == "in"
    assert alpha_ep["peak_accel_z"] == 2.5


def test_episode_feed_no_nan():
    """Episode feed values must not contain float('nan')."""
    ep_m = _make_episodes(["alpha"])
    ep_s = _make_episodes(["XLE"])
    # Inject NaN into peak_accel_z for one record
    ep_m_nan = ep_m.copy()
    ep_m_nan.loc[ep_m_nan.index[0], "peak_accel_z"] = float("nan")
    feed = build_episode_feed(ep_m_nan, ep_s)
    raw = json.dumps(feed)
    assert "NaN" not in raw, "NaN leaked into JSON (must be null)"


# ── (d) Manifest lists every chunk ───────────────────────────────────────────

def test_manifest_lists_all_chunks():
    """Manifest chunk list matches the chunk objects produced."""
    nodes_s = ["XLK", "XLE"]
    dates_s = pd.bdate_range("2022-01-03", "2022-06-30").strftime("%Y-%m-%d").tolist()
    panel_s = _make_panel(nodes_s, dates_s)
    reg_s = [{"id": i, "name": n, "name_zh": None, "theme": "S", "tier": "s"}
             for i, n in enumerate(nodes_s)]
    chunks_s = build_chunks_s(panel_s, reg_s)

    nodes_m = ["nodeA", "nodeB"]
    dates_m = _friday_dates(8, "2022-02-04")
    panel_m = _make_panel(nodes_m, dates_m)
    reg_m = [{"id": i, "name": n, "name_zh": None, "theme": "T", "tier": "subsector"}
             for i, n in enumerate(nodes_m)]
    chunks_m = build_chunks_m(panel_m, reg_m)

    manifest = build_manifest(reg_s, reg_m, chunks_s, chunks_m)

    # Every chunk in chunks_s must appear in the manifest
    manifest_s_keys = {c["key"] for c in manifest["tiers"]["s"]["chunks"]}
    for chunk in chunks_s:
        assert chunk["period"] in manifest_s_keys, (
            f"Chunk {chunk['period']} missing from manifest Tier-S"
        )

    manifest_m_keys = {c["key"] for c in manifest["tiers"]["m"]["chunks"]}
    for chunk in chunks_m:
        assert chunk["period"] in manifest_m_keys, (
            f"Chunk {chunk['period']} missing from manifest Tier-M"
        )


# ── (e) No NaN leakage ────────────────────────────────────────────────────────

def test_no_nan_in_chunks():
    """NaN values must be serialised as null (None), not as float NaN."""
    nodes = ["XLK", "XLE"]
    dates = pd.bdate_range("2022-01-03", "2022-03-31").strftime("%Y-%m-%d").tolist()
    # Force NaN into accel_z for all entries
    panel = _make_panel(nodes, dates, null_accel_fraction=0.5)
    # Also zero out accel_z entirely for some nodes
    panel.loc[panel.index.get_level_values("node") == "XLK", "accel_z"] = float("nan")
    registry = [{"id": i, "name": n, "name_zh": None, "theme": "S", "tier": "s"}
                for i, n in enumerate(nodes)]
    chunks = build_chunks_s(panel, registry)
    for chunk in chunks:
        raw = json.dumps({"dates": chunk["dates"], "data": chunk["data"]},
                         separators=(",", ":"))
        assert "NaN" not in raw, f"NaN in chunk {chunk['period']}"
        assert "Infinity" not in raw


# ── (f) Registry ids are dense 0-based ───────────────────────────────────────

def test_registry_ids_dense():
    """Registry node ids must be 0, 1, 2, ..., n-1."""
    nodes_s = ["XLK", "XLE", "XLV", "XLF"]
    dates = pd.bdate_range("2022-01-03", "2022-03-31").strftime("%Y-%m-%d").tolist()
    panel_s = _make_panel(nodes_s, dates)
    reg_s = build_registry_s(panel_s)
    ids = [r["id"] for r in reg_s]
    assert ids == list(range(len(reg_s))), f"Non-dense ids: {ids}"


def test_registry_m_ids_dense():
    """Tier-M registry ids are dense regardless of tree-match status."""
    nodes_m = ["Artificial Intelligence", "unknown_basket", "nodeX"]
    dates = _friday_dates(4, "2022-02-04")
    panel_m = _make_panel(nodes_m, dates)
    # Minimal themes_tree: only 'Artificial Intelligence' is present
    themes_tree = [
        {
            "theme": "Artificial Intelligence",
            "key": "ai",
            "subsectors": [],
        }
    ]
    names_zh = {"themes": {"Artificial Intelligence": "人工智能"}, "subsectors": {}}
    reg_m = build_registry_m(panel_m, themes_tree, names_zh, baskets_data=[])
    ids = [r["id"] for r in reg_m]
    assert ids == list(range(len(reg_m)))


# ── (g) Tier-M skips months where accel_z is 100% null ───────────────────────

def test_tierm_skips_all_null_accel_months():
    """Months where accel_z is entirely NaN must be excluded from Tier-M chunks."""
    nodes = ["node0", "node1"]
    # Two months: first has all-null accel_z, second has real values
    null_dates = pd.bdate_range("2021-07-01", "2021-07-31").strftime("%Y-%m-%d").tolist()
    real_dates = _friday_dates(4, "2022-02-04")

    null_panel = _make_panel(nodes, null_dates, null_accel_fraction=1.0)
    real_panel = _make_panel(nodes, real_dates)
    # Force null panel accel_z to NaN explicitly (fraction=1.0 may not guarantee it)
    null_panel["accel_z"] = float("nan")

    combined = pd.concat([null_panel, real_panel])
    registry = _simple_registry(2)
    chunks = build_chunks_m(combined, registry)

    # Only the 2022-02 month should appear
    periods = [c["period"] for c in chunks]
    assert "2021M07" not in periods, "Null accel month should be skipped"
    assert any("2022" in p for p in periods), "Real month should be included"


# ── (h) Tier-M emits ALL trading days (daily granularity) ────────────────────

def test_tierm_daily_dates():
    """Tier-M chunk dates must include all trading days, not just Fridays."""
    nodes = ["node0", "node1"]
    # Full month of daily data — includes Mon-Fri
    all_dates = pd.bdate_range("2022-02-01", "2022-02-28").strftime("%Y-%m-%d").tolist()
    panel = _make_panel(nodes, all_dates)
    registry = _simple_registry(2)
    chunks = build_chunks_m(panel, registry)

    assert len(chunks) == 1, "Expected one chunk for 2022-02"
    chunk = chunks[0]

    # Must contain ALL panel dates for the month
    assert set(chunk["dates"]) == set(all_dates), (
        "Tier-M chunk should contain every trading day, not just Fridays"
    )
    # Must include at least one non-Friday weekday (Monday–Thursday)
    non_fri = [d for d in chunk["dates"] if pd.Timestamp(d).weekday() != 4]
    assert len(non_fri) > 0, "Expected non-Friday dates in daily Tier-M chunk"
