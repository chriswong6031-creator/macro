"""tests/test_lbnl_queue.py — hermetic tests for the LBNL interconnection-queue
collector and the engine._queue_pull() contract it feeds.

Three mandatory positive-control assertions:

1.  Percent-units contract: synthetic {"total_gw_yoy": 20.0} written to a
    tmp config-rooted path -> power_scarcity._queue_pull() returns 1.0.
    (20.0 / 20.0 = 1.0, within the ±2.0 clamp.)

2.  Fraction-unit tripwire: a value of 0.20 (which would be wrong — the
    reader expects percent, not a fraction) yields 0.01.
    Documents WHY the percent contract matters: if the collector emitted a
    fraction instead of a percent the signal would be ~100x too small and
    silently meaningless (0.01 instead of ~1.0 z-score).

3.  Collector transform tests: verify compute_yoy() arithmetic on a
    synthetic annual table, including edge cases.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from engine import power_scarcity as ps
from collectors.lbnl_queue import compute_yoy, _parse_annual_totals, _find_col


# ──────────────────────────────────────────────────────────────────────────────
# 1. POSITIVE-CONTROL: percent-units contract
#    synthetic {"total_gw_yoy": 20.0} → _queue_pull() == 1.0
# ──────────────────────────────────────────────────────────────────────────────

def test_queue_pull_percent_units_contract(monkeypatch, tmp_path):
    """MANDATORY positive-control: 20.0%/yr is the ~+1 z baseline per the engine
    contract (scales /20.0 → 1.0).  If this fails the reader or writer broke."""
    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text(
        json.dumps({"total_gw_yoy": 20.0})
    )
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    result = ps._queue_pull()
    assert result == 1.0, (
        f"Expected 1.0 (20.0 / 20.0), got {result!r}. "
        "Check that the collector emits PERCENT units (18.5 == +18.5%/yr), "
        "not fractions."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. FRACTION-UNIT TRIPWIRE
#    0.20 (wrong: fraction instead of percent) → _queue_pull() == 0.01
#    Documents the consequence of emitting the wrong unit.
# ──────────────────────────────────────────────────────────────────────────────

def test_queue_pull_fraction_unit_tripwire(monkeypatch, tmp_path):
    """MANDATORY tripwire: demonstrates why percent units matter.

    If the collector emitted a fraction (0.20) instead of a percent (20.0),
    the engine would receive 0.20 / 20.0 = 0.01 — a near-zero z-score that
    would silently make the queue-buildout leg worthless even in a capacity
    boom. This test documents that contract in an executable form."""
    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text(
        json.dumps({"total_gw_yoy": 0.20})
    )
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    result = ps._queue_pull()
    assert result == 0.01, (
        f"Expected 0.01 (0.20 / 20.0) — this tripwire confirms that a "
        f"fraction value (0.20) is nearly useless after /20.0 scaling. "
        f"Got {result!r}."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3. CLAMP: values outside ±2.0 are clamped
# ──────────────────────────────────────────────────────────────────────────────

def test_queue_pull_clamp_positive(monkeypatch, tmp_path):
    """40%/yr -> clamped to +2.0 (confirmed by existing test_power_scarcity.py)."""
    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text(
        json.dumps({"total_gw_yoy": 40.0})
    )
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    assert ps._queue_pull() == 2.0


def test_queue_pull_clamp_negative(monkeypatch, tmp_path):
    """-50%/yr -> clamped to -2.0."""
    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text(
        json.dumps({"total_gw_yoy": -50.0})
    )
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    assert ps._queue_pull() == -2.0


# ──────────────────────────────────────────────────────────────────────────────
# 4. ABSENT CACHE → None (graceful degradation)
# ──────────────────────────────────────────────────────────────────────────────

def test_queue_pull_absent_json(monkeypatch, tmp_path):
    """No JSON file → None; engine continues without the queue-buildout leg."""
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    assert ps._queue_pull() is None


def test_queue_pull_missing_key(monkeypatch, tmp_path):
    """JSON exists but lacks total_gw_yoy → None (extra keys are OK)."""
    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text(
        json.dumps({"asof_year": 2023, "total_gw": 2600.0})  # no yoy key
    )
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    assert ps._queue_pull() is None


def test_queue_pull_corrupt_json(monkeypatch, tmp_path):
    """Corrupt JSON → None; engine continues (network write mid-collect)."""
    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text("NOT_JSON{{{")
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    assert ps._queue_pull() is None


# ──────────────────────────────────────────────────────────────────────────────
# 5. COLLECTOR TRANSFORM: compute_yoy() arithmetic
# ──────────────────────────────────────────────────────────────────────────────

def _make_tbl(rows: list[tuple[int, float]]) -> pd.DataFrame:
    """Build a minimal (year, total_gw) table for compute_yoy testing."""
    years, gws = zip(*rows)
    return pd.DataFrame({"year": list(years), "total_gw": list(gws)})


def test_compute_yoy_basic():
    """Basic YoY: 1000 -> 1200 GW == +20.0%."""
    tbl = _make_tbl([(2022, 1000.0), (2023, 1200.0)])
    out = compute_yoy(tbl)
    assert out["total_gw_yoy"] == pytest.approx(20.0, abs=0.01)
    assert out["asof_year"] == 2023
    assert out["total_gw"] == pytest.approx(1200.0, abs=0.1)
    assert out["prior_year"] == 2022
    assert out["prior_gw"] == pytest.approx(1000.0, abs=0.1)


def test_compute_yoy_negative():
    """Declining queue: 1200 -> 900 GW == -25.0%."""
    tbl = _make_tbl([(2022, 1200.0), (2023, 900.0)])
    out = compute_yoy(tbl)
    assert out["total_gw_yoy"] == pytest.approx(-25.0, abs=0.01)


def test_compute_yoy_multi_year_uses_last_two():
    """With multiple years, only the last two are used for YoY."""
    tbl = _make_tbl([(2019, 800.0), (2020, 900.0), (2021, 950.0), (2022, 2000.0)])
    out = compute_yoy(tbl)
    # 950 -> 2000: +110.5%
    assert out["total_gw_yoy"] == pytest.approx(
        (2000.0 / 950.0 - 1.0) * 100.0, abs=0.01
    )
    assert out["asof_year"] == 2022


def test_compute_yoy_source_string():
    """source field names the as-of year."""
    tbl = _make_tbl([(2022, 1000.0), (2023, 1100.0)])
    out = compute_yoy(tbl)
    assert "2023" in out["source"]
    assert "LBNL" in out["source"]


def test_compute_yoy_collected_iso():
    """_collected is an ISO datetime string."""
    tbl = _make_tbl([(2022, 1000.0), (2023, 1100.0)])
    out = compute_yoy(tbl)
    # should parse without exception
    datetime.fromisoformat(out["_collected"].replace("Z", "+00:00"))


# ──────────────────────────────────────────────────────────────────────────────
# 6. _find_col: column lookup helper
# ──────────────────────────────────────────────────────────────────────────────

def test_find_col_exact():
    df = pd.DataFrame({"Year": [2023], "Total capacity (GW)": [1000.0]})
    assert _find_col(df, ("Year", "year")) == "Year"
    assert _find_col(df, ("Total capacity (GW)",)) == "Total capacity (GW)"


def test_find_col_case_insensitive():
    df = pd.DataFrame({"year": [2023], "gw": [1000.0]})
    assert _find_col(df, ("Year", "year")) == "year"


def test_find_col_missing():
    df = pd.DataFrame({"foo": [1], "bar": [2]})
    assert _find_col(df, ("Year", "year", "YEAR")) is None


# ──────────────────────────────────────────────────────────────────────────────
# 7. ADAPTER: fetch() graceful failure when network is unavailable
# ──────────────────────────────────────────────────────────────────────────────

def test_lbnl_adapter_raises_when_network_dead(monkeypatch):
    """When all URL attempts return None, fetch() raises RuntimeError (not swallows)."""
    from collectors.lbnl_queue import LbnlQueueAdapter, _try_fetch_xlsx
    monkeypatch.setattr(
        "collectors.lbnl_queue._try_fetch_xlsx", lambda year: None
    )
    adapter = LbnlQueueAdapter()
    with pytest.raises(RuntimeError, match="lbnl_queue"):
        adapter.fetch()


# ──────────────────────────────────────────────────────────────────────────────
# 8. INTEGRATION: compute_yoy output passes through _queue_pull correctly
#    (end-to-end test using the seed JSON format)
# ──────────────────────────────────────────────────────────────────────────────

def test_end_to_end_seed_format(monkeypatch, tmp_path):
    """The dict that compute_yoy() produces can be round-tripped through the
    _queue_pull() reader: write it as JSON, read it back, verify the z-score."""
    tbl = _make_tbl([(2022, 1000.0), (2023, 1200.0)])   # +20% -> z = 1.0
    seed = compute_yoy(tbl)

    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text(
        json.dumps(seed)
    )
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    z = ps._queue_pull()
    assert z == pytest.approx(1.0, abs=0.01), (
        f"compute_yoy output (+20% -> total_gw_yoy=20.0) should yield z=1.0, "
        f"got {z!r}"
    )
