"""RC-R14 China rotation-event detector port — tests for:

1. engine/sector_legs_china.py — basket-level close series loader
2. engine/rotation_events.run_nightly — data_subdir parameterization (China path)
3. Append-only ledger regression (RC-R2 law) on China subdir
4. US no-change regression: existing US tests all pass; additionally verify that
   calling run_nightly with data_subdir="rotation_events_china" does NOT write
   to the US "rotation_events" directory.

All tests are synthetic / hermetic — no live data, no network calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import rotation_events as re_
from engine import sector_legs_china


# ──────────────────────────────────────────────────────────── fixtures ────


def _series(vals) -> pd.Series:
    idx = pd.bdate_range("2024-01-02", periods=len(vals))
    return pd.Series(list(vals), index=idx, dtype=float)


def _blowoff_leg(n_flat=280, runup=20, crash=6) -> pd.Series:
    vals = [100.0] * n_flat
    for _ in range(runup):
        vals.append(vals[-1] * 1.02)
    for _ in range(crash):
        vals.append(vals[-1] * 0.96)
    return _series(vals)


def _turn_leg(n_flat=280, decline=20, rise=6) -> pd.Series:
    vals = [100.0] * n_flat
    for _ in range(decline):
        vals.append(vals[-1] * 0.992)
    for _ in range(rise):
        vals.append(vals[-1] * 1.012)
    return _series(vals)


def _aligned_pair():
    a, b = _blowoff_leg(), _turn_leg()
    n = min(len(a), len(b))
    a, b = a.iloc[-n:], b.iloc[-n:]
    b.index = a.index
    return a, b


def _cn_sectors(a, b):
    """Minimal China-shaped sectors dict for step_pairs / run_nightly."""
    cfg = {
        "key": "cn_tech", "etf": None,
        "name_en": "Technology & AI", "name_zh": "科技与AI",
        "legs": [
            {"key": "cn_semis",      "tier": "primary",   "name_en": "Semiconductors",      "name_zh": "半导体"},
            {"key": "cn_ai_compute", "tier": "primary",   "name_en": "AI Compute & Optics", "name_zh": "AI算力与光模块"},
        ],
    }
    ew_etf = (a + b) / 2          # synthesised pseudo-ETF close
    return {"cn_tech": {"cfg": cfg, "etf_close": ew_etf,
                         "legs": {"cn_semis": a, "cn_ai_compute": b},
                         "leg_meta": {}}}


# ──────────────────────────────────────── sector_legs_china loader tests ────


def _make_fake_baskets_json(tmp_path: Path, n_bars: int = 250) -> dict:
    """Write a synthetic baskets.json under tmp_path/chinabasketdata/ and return its path."""
    import math
    dates = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=n_bars)]
    # basket a: blowoff series (normalized level)
    vals_a = [1.0 + i * 0.002 for i in range(n_bars)]
    # basket b: turn series (normalized level)
    vals_b = [1.0 - i * 0.001 for i in range(min(200, n_bars))] + [1.0 - 0.2 + j * 0.003 for j in range(max(0, n_bars - 200))]
    basket_dir = tmp_path / "chinabasketdata"
    basket_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "baskets": [
            {"id": "cn_semis",      "name": "Semiconductors",      "name_zh": "半导体",      "n_members": 22},
            {"id": "cn_ai_compute", "name": "AI Compute & Optics", "name_zh": "AI算力与光模块", "n_members": 17},
        ],
        "chart": {
            "dates": dates,
            "baskets": {
                "cn_semis":      vals_a,
                "cn_ai_compute": vals_b,
            },
        },
    }
    p = basket_dir / "baskets.json"
    p.write_text(json.dumps(data, ensure_ascii=False))
    return data


def test_sector_legs_china_loads_series_from_baskets_json(tmp_path):
    """sector_legs_china.sector_closes() must return series from a fake baskets.json."""
    _make_fake_baskets_json(tmp_path, n_bars=250)
    # Minimal registry with two legs matching the fake data
    registry = {
        "version": "1.0", "region": "china",
        "sectors": [
            {
                "key": "cn_tech",
                "name_en": "Technology & AI", "name_zh": "科技与AI",
                "legs": [
                    {"key": "cn_semis",      "basket_cn": "cn_semis",      "tier": "primary",   "name_en": "Semiconductors",      "name_zh": "半导体"},
                    {"key": "cn_ai_compute", "basket_cn": "cn_ai_compute", "tier": "primary",   "name_en": "AI Compute",          "name_zh": "AI算力"},
                ],
            }
        ],
    }
    sectors = sector_legs_china.sector_closes(site_dir=tmp_path, registry=registry)
    assert "cn_tech" in sectors
    s = sectors["cn_tech"]
    assert "cn_semis" in s["legs"]
    assert "cn_ai_compute" in s["legs"]
    assert isinstance(s["legs"]["cn_semis"], pd.Series)
    assert len(s["legs"]["cn_semis"]) >= sector_legs_china.MIN_BARS
    # etf_close must be synthesised (mean of legs)
    assert s["etf_close"] is not None
    assert len(s["etf_close"]) > 0


def test_sector_legs_china_skips_missing_basket(tmp_path):
    """A basket_cn key absent from baskets.json logs + skips the leg gracefully."""
    _make_fake_baskets_json(tmp_path, n_bars=250)
    registry = {
        "version": "1.0", "region": "china",
        "sectors": [
            {
                "key": "cn_tech",
                "name_en": "Technology & AI", "name_zh": "科技与AI",
                "legs": [
                    {"key": "cn_semis",      "basket_cn": "cn_semis",      "tier": "primary",   "name_en": "Semiconductors", "name_zh": "半导体"},
                    {"key": "cn_ghost",      "basket_cn": "cn_nonexistent","tier": "secondary", "name_en": "Ghost",           "name_zh": "幽灵"},
                ],
            }
        ],
    }
    sectors = sector_legs_china.sector_closes(site_dir=tmp_path, registry=registry)
    # Sector has only 1 resolved leg → skipped (< 2)
    assert "cn_tech" not in sectors


def test_sector_legs_china_skips_sector_with_one_leg(tmp_path):
    """Sectors with fewer than 2 resolved legs are dropped entirely."""
    _make_fake_baskets_json(tmp_path, n_bars=250)
    registry = {
        "version": "1.0", "region": "china",
        "sectors": [
            {
                "key": "cn_lone",
                "name_en": "Lonely Sector", "name_zh": "孤单板块",
                "legs": [
                    {"key": "cn_semis", "basket_cn": "cn_semis", "tier": "primary", "name_en": "Semis", "name_zh": "芯片"},
                ],
            }
        ],
    }
    sectors = sector_legs_china.sector_closes(site_dir=tmp_path, registry=registry)
    assert "cn_lone" not in sectors


def test_sector_legs_china_missing_baskets_json(tmp_path):
    """sector_closes() returns {} if baskets.json doesn't exist."""
    registry = {"version": "1.0", "region": "china", "sectors": []}
    sectors = sector_legs_china.sector_closes(site_dir=tmp_path, registry=registry)
    assert sectors == {}


# ───────────────────────── run_nightly data_subdir parameterization ────


def test_run_nightly_china_writes_to_china_subdir(tmp_path):
    """run_nightly(..., data_subdir='rotation_events_china') must write state/ledger
    under data_dir/rotation_events_china — NOT under data_dir/rotation_events."""
    a, b = _aligned_pair()
    sectors = _cn_sectors(a, b)
    payload = re_.run_nightly(sectors, tmp_path,
                              generated_utc="test",
                              data_subdir="rotation_events_china")
    assert payload["schema"] == "rotation_events.v1"
    assert payload["authority"]["may_gate"] is False
    # China paths must exist
    assert (tmp_path / "rotation_events_china" / "state.json").exists()
    assert (tmp_path / "rotation_events_china" / "events.jsonl").exists()
    # US paths must NOT be created (isolation guarantee)
    assert not (tmp_path / "rotation_events").exists()


def test_run_nightly_china_does_not_touch_us_state(tmp_path):
    """Running the China builder must not read or write the US state file."""
    a, b = _aligned_pair()
    # Pre-create a US state so we can confirm it is untouched
    us_dir = tmp_path / "rotation_events"
    us_dir.mkdir()
    us_state_p = us_dir / "state.json"
    us_state_p.write_text('{"active":{},"closed":{}}')
    mtime_before = us_state_p.stat().st_mtime

    re_.run_nightly(_cn_sectors(a, b), tmp_path,
                    generated_utc="test",
                    data_subdir="rotation_events_china")
    assert us_state_p.stat().st_mtime == mtime_before, "US state.json was touched by China builder"


# ────────────────────────── append-only ledger regression (RC-R2 law) ────


def test_ledger_append_only_never_truncated(tmp_path):
    """A second nightly run MUST append to the ledger, never overwrite it.
    No existing row's content must change between runs."""
    a, b = _aligned_pair()
    sectors = _cn_sectors(a, b)

    # First run
    re_.run_nightly(sectors, tmp_path,
                    generated_utc="run1",
                    data_subdir="rotation_events_china")
    ledger_p = tmp_path / "rotation_events_china" / "events.jsonl"
    lines_after_run1 = ledger_p.read_text().strip().splitlines()
    assert lines_after_run1, "ledger empty after first run"

    # Second run — same conditions
    re_.run_nightly(sectors, tmp_path,
                    generated_utc="run2",
                    data_subdir="rotation_events_china")
    lines_after_run2 = ledger_p.read_text().strip().splitlines()

    # Ledger may only grow (RC-R2: append-only)
    assert len(lines_after_run2) >= len(lines_after_run1), \
        "ledger shrank between runs — RC-R2 violation"
    # All rows from run1 must still appear verbatim at the start
    for i, line in enumerate(lines_after_run1):
        assert lines_after_run2[i] == line, \
            f"ledger row {i} was mutated between runs — RC-R2 violation"


def test_ledger_rows_are_valid_json(tmp_path):
    """Every line in the ledger must be parseable JSON with required fields."""
    a, b = _aligned_pair()
    re_.run_nightly(_cn_sectors(a, b), tmp_path,
                    generated_utc="test",
                    data_subdir="rotation_events_china")
    ledger_p = tmp_path / "rotation_events_china" / "events.jsonl"
    for line in ledger_p.read_text().strip().splitlines():
        row = json.loads(line)            # must not raise
        assert "ts" in row
        assert "event" in row
        assert row["event"] in ("created", "closed")


# ─────────────────────── China detector fires on synthetic legs ────────


def test_china_detector_fires_on_blowoff_turn_pair(tmp_path):
    """The core detector must fire on China-shaped synthetic legs (same as US —
    prove the China path is wired end-to-end, not just the loader)."""
    a, b = _aligned_pair()
    sectors = _cn_sectors(a, b)
    payload = re_.run_nightly(sectors, tmp_path,
                              generated_utc="test",
                              data_subdir="rotation_events_china")
    # Must have at least one active event or coldstart replay
    assert payload["active"] or payload["coldstart"], \
        "detector did not fire on synthetic blowoff/turn pair for China"
    # Ensure bilingual copy present
    if payload["active"]:
        ev = payload["active"][0]
        assert "Rotation" in ev["copy_en"] or "rotation" in ev["copy_en"].lower()
        assert "轮动" in ev["copy_zh"]


def test_china_event_copy_uses_china_leg_names():
    """Verify that _copy() uses the names from the Chinese config, not US names."""
    a, b = _aligned_pair()
    sectors = _cn_sectors(a, b)
    state, active, created, closed = re_.step_pairs(sectors, {})
    if active:
        ev = active[0]
        # leg names must match what we put in the cfg
        assert ev["from_leg"]["name_en"] in ("Semiconductors", "AI Compute & Optics")
        assert ev["to_leg"]["name_zh"] in ("半导体", "AI算力与光模块")


# ──────────────────── severity with China tiers (both primary) ────────


def test_china_severity_both_primary_is_major():
    """Two primary-tier legs → major (same rule as US)."""
    rc = {"blowoff": {"drawdown_pct": 0.20, "peak_date": "x", "runup_pct": .3, "runup_z": 3},
          "turn": {"low_date": "x", "off_low_pct": 0.09, "reclaimed": True},
          "ratio": {}}
    assert re_.severity({"tier": "primary"}, {"tier": "primary"}, rc) == "major"
