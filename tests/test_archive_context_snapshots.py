"""Tests for scripts/archive_context_snapshots.py.

Validates keep-FIRST semantics, absent-safety for every source,
freshness cutoffs, new VSB W2 columns, and old-schema backward compatibility.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.archive_context_snapshots import (
    _build_row,
    _append,
    _read_regime,
    _read_market_state,
    _read_fear_greed,
    _read_fg_us,
    _read_vol_weather,
    _read_raw_vol,
    _read_rsp_spy_ratio,
    _read_breadth_split,
    _stale_cutoff,
    ARCHIVE_FILE,
    main,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _make_price_df(dates: list[str], values: list[float], col: str = "close") -> pd.DataFrame:
    """Create a small price DataFrame with a DatetimeIndex."""
    idx = pd.to_datetime(dates)
    return pd.DataFrame({col: values}, index=idx)


# ── _build_row ────────────────────────────────────────────────────────────────

def test_build_row_full():
    regime = {
        "date": "2026-07-06",
        "quad": "Q1",
        "liquidity_overlay": "neutral",
        "cycle_tag": "mid",
        "transition_state": "TRANSITIONING",
        "confidence": 0.42,
        "vol_regime": {"regime": "normalizing"},
    }
    ms = {"verdict": "RISK_OFF", "score": 40}
    row = _build_row(regime, ms, fear_greed=55.0)
    assert row["date"] == "2026-07-06"
    assert row["quad"] == "Q1"
    assert row["liquidity"] == "neutral"
    assert row["cycle_tag"] == "mid"
    assert row["transition_state"] == "TRANSITIONING"
    assert row["regime_confidence"] == pytest.approx(0.42)
    assert row["market_verdict"] == "RISK_OFF"
    assert row["market_score"] == 40
    assert row["vol_regime_verdict"] == "normalizing"
    assert row["fear_greed_composite"] == pytest.approx(55.0)


def test_build_row_absent_sources():
    """Empty dicts + None fear_greed -> all optional fields None (never crash)."""
    row = _build_row({}, {}, None)
    assert row["quad"] is None
    assert row["market_verdict"] is None
    assert row["fear_greed_composite"] is None
    # date falls back to UTC today string — just check it is a non-empty string
    assert isinstance(row["date"], str) and len(row["date"]) == 10


def test_build_row_new_columns_all_none_when_absent():
    """New VSB W2 columns are None when no extra dicts supplied."""
    row = _build_row({}, {}, None)
    # fg_us columns
    assert row["fg_dial_us"] is None
    assert row["fg_n_legs"] is None
    assert row["fg_as_of"] is None
    # vol weather columns
    assert row["vix_pctile_252"] is None
    assert row["vix_chg5d_pctile"] is None
    assert row["vvix_vix_ratio"] is None
    assert row["vix9d_vix3m"] is None
    assert row["vol_weather_as_of"] is None
    # raw vol columns
    assert row["vix_close"] is None
    assert row["vix1d"] is None
    assert row["dspx"] is None
    assert row["vixeq"] is None
    assert row["cor1m"] is None
    assert row["cor3m"] is None
    # ratio
    assert row["rsp_spy_ratio"] is None
    # breadth split columns
    assert row["ai_breadth_spread_50"] is None
    assert row["ai_pct50"] is None
    assert row["nonai_pct50"] is None
    assert row["breadth_split_as_of"] is None


def test_build_row_new_columns_populated():
    """New columns land correctly when dicts are supplied."""
    fg_us = {"fg_dial_us": 54, "fg_n_legs": 11, "fg_as_of": "2026-07-14"}
    vol_weather = {
        "vix_pctile_252": 0.32, "vix_chg5d_pctile": 0.45,
        "vvix_vix_ratio": 5.2, "vix9d_vix3m": 0.88, "vol_weather_as_of": "2026-07-14",
    }
    raw_vol = {
        "vix_close": 16.3, "vix1d": 10.5, "dspx": 1100.0,
        "vixeq": 14.5, "cor1m": 0.45, "cor3m": 0.38,
    }
    breadth_split = {
        "ai_breadth_spread_50": 12.5, "ai_pct50": 0.65,
        "nonai_pct50": 0.40, "breadth_split_as_of": "2026-07-14",
    }
    row = _build_row(
        {"date": "2026-07-14"}, {}, None,
        fg_us=fg_us, vol_weather=vol_weather, raw_vol=raw_vol,
        rsp_spy_ratio=0.4823, breadth_split=breadth_split,
    )
    assert row["fg_dial_us"] == 54
    assert row["fg_n_legs"] == 11
    assert row["fg_as_of"] == "2026-07-14"
    assert row["vix_pctile_252"] == pytest.approx(0.32)
    assert row["vix_chg5d_pctile"] == pytest.approx(0.45)
    assert row["vvix_vix_ratio"] == pytest.approx(5.2)
    assert row["vix9d_vix3m"] == pytest.approx(0.88)
    assert row["vol_weather_as_of"] == "2026-07-14"
    assert row["vix_close"] == pytest.approx(16.3)
    assert row["vix1d"] == pytest.approx(10.5)
    assert row["dspx"] == pytest.approx(1100.0)
    assert row["vixeq"] == pytest.approx(14.5)
    assert row["cor1m"] == pytest.approx(0.45)
    assert row["cor3m"] == pytest.approx(0.38)
    assert row["rsp_spy_ratio"] == pytest.approx(0.4823)
    assert row["ai_breadth_spread_50"] == pytest.approx(12.5)
    assert row["ai_pct50"] == pytest.approx(0.65)
    assert row["nonai_pct50"] == pytest.approx(0.40)
    assert row["breadth_split_as_of"] == "2026-07-14"


# ── _append keep-FIRST ────────────────────────────────────────────────────────

def test_append_creates_parquet_on_first_write(tmp_path):
    archive_path = tmp_path / ARCHIVE_FILE
    row = {"date": "2026-07-06", "quad": "Q1", "liquidity": "neutral",
           "cycle_tag": "mid", "transition_state": "CALM",
           "regime_confidence": 0.5, "market_verdict": "NEUTRAL",
           "market_score": 60, "vol_regime_verdict": "low", "fear_greed_composite": 50.0}
    written = _append(archive_path, row)
    assert written is True
    assert archive_path.exists()
    df = pd.read_parquet(archive_path)
    assert list(df["date"]) == ["2026-07-06"]
    assert df.loc[0, "quad"] == "Q1"


def test_append_keep_first_same_date(tmp_path):
    """Second write for the same date must be a no-op (keep-FIRST)."""
    archive_path = tmp_path / ARCHIVE_FILE
    row1 = {"date": "2026-07-06", "quad": "Q1", "liquidity": "neutral",
            "cycle_tag": "mid", "transition_state": "CALM",
            "regime_confidence": 0.5, "market_verdict": "RISK_ON",
            "market_score": 70, "vol_regime_verdict": "low", "fear_greed_composite": 60.0}
    row2 = {**row1, "quad": "Q9"}  # same date, different quad
    _append(archive_path, row1)
    written2 = _append(archive_path, row2)
    assert written2 is False
    df = pd.read_parquet(archive_path)
    assert df["quad"].tolist() == ["Q1"]  # original row preserved


def test_append_different_dates_accumulate(tmp_path):
    """Each new date appends a new row."""
    archive_path = tmp_path / ARCHIVE_FILE
    for d in ["2026-07-04", "2026-07-05", "2026-07-06"]:
        row = {"date": d, "quad": "Q2", "liquidity": "loose",
               "cycle_tag": "early", "transition_state": "STABLE",
               "regime_confidence": 0.7, "market_verdict": "RISK_ON",
               "market_score": 80, "vol_regime_verdict": "low", "fear_greed_composite": 55.0}
        _append(archive_path, row)
    df = pd.read_parquet(archive_path)
    assert list(df["date"]) == ["2026-07-04", "2026-07-05", "2026-07-06"]


# ── old-schema backward compatibility ─────────────────────────────────────────

def test_old_schema_parquet_concat_with_new_row(tmp_path):
    """An old parquet lacking the new VSB W2 columns must merge cleanly.

    pd.concat with schema-merge fills missing new-columns with NaN for old rows
    while the new row carries the new values.  This test proves that behavior.
    """
    archive_path = tmp_path / ARCHIVE_FILE
    # Write an old-schema row (only original columns)
    old_row = {
        "logged_at": "2026-01-01T00:00:00+00:00",
        "date": "2026-01-01", "quad": "Q3", "liquidity": "tight",
        "cycle_tag": "late", "transition_state": "STABLE",
        "regime_confidence": 0.8, "market_verdict": "RISK_OFF",
        "market_score": 20, "vol_regime_verdict": "stress", "fear_greed_composite": 25.0,
    }
    pd.DataFrame([old_row]).to_parquet(archive_path, index=False)

    # Now append a new-schema row with all new columns
    new_row = {
        "date": "2026-07-14", "quad": "Q1", "liquidity": "loose",
        "cycle_tag": "mid", "transition_state": "CALM",
        "regime_confidence": 0.6, "market_verdict": "RISK_ON",
        "market_score": 75, "vol_regime_verdict": "low", "fear_greed_composite": 60.0,
        "fg_dial_us": 54, "fg_n_legs": 11, "fg_as_of": "2026-07-14",
        "vix_pctile_252": 0.30, "vix_chg5d_pctile": 0.40,
        "vvix_vix_ratio": 5.1, "vix9d_vix3m": 0.87, "vol_weather_as_of": "2026-07-14",
        "vix_close": 16.3, "vix1d": 10.5, "dspx": 1100.0,
        "vixeq": 14.5, "cor1m": 0.45, "cor3m": 0.38,
        "rsp_spy_ratio": 0.48,
        "ai_breadth_spread_50": 12.0, "ai_pct50": 0.65,
        "nonai_pct50": 0.40, "breadth_split_as_of": "2026-07-14",
    }
    written = _append(archive_path, new_row)
    assert written is True

    df = pd.read_parquet(archive_path)
    assert len(df) == 2
    # Old row: new columns must be NaN (not crash)
    old_r = df[df["date"] == "2026-01-01"].iloc[0]
    assert pd.isna(old_r["fg_dial_us"])
    assert pd.isna(old_r["vix_close"])
    assert pd.isna(old_r["rsp_spy_ratio"])
    assert pd.isna(old_r["ai_breadth_spread_50"])
    # New row: values must be present
    new_r = df[df["date"] == "2026-07-14"].iloc[0]
    assert new_r["fg_dial_us"] == 54
    assert new_r["vix_close"] == pytest.approx(16.3)
    assert new_r["rsp_spy_ratio"] == pytest.approx(0.48)


# ── absent-safety ─────────────────────────────────────────────────────────────

def test_read_regime_absent(tmp_path):
    """Missing file returns empty dict, never crashes."""
    d = _read_regime(tmp_path)
    assert d == {}


def test_read_market_state_absent(tmp_path):
    d = _read_market_state(tmp_path)
    assert d == {}


def test_read_fear_greed_absent(tmp_path):
    result = _read_fear_greed(tmp_path)
    assert result is None


def test_read_fear_greed_present(tmp_path):
    """Reads the most recent fear_greed value from parquet."""
    df = pd.DataFrame({"fear_greed": [20, 22, 25]},
                      index=pd.to_datetime(["2026-07-03", "2026-07-04", "2026-07-05"]))
    df.index.name = "date"
    _write_parquet(tmp_path / "sentiment_crypto" / "fear_greed.parquet", df.reset_index())
    result = _read_fear_greed(tmp_path)
    assert result == pytest.approx(25.0)


def test_read_fg_us_absent(tmp_path):
    """Missing fear_greed.json -> all fg_us columns None."""
    result = _read_fg_us(tmp_path)
    assert result["fg_dial_us"] is None
    assert result["fg_n_legs"] is None
    assert result["fg_as_of"] is None


def test_read_fg_us_present(tmp_path):
    """Valid fear_greed.json -> dial, n_legs, as_of extracted."""
    _write_json(
        tmp_path / "site" / "basketdata" / "fear_greed.json",
        {"dial": 54, "n_legs_qualifying": 11, "as_of": "2026-07-14",
         "label_en": "Neutral", "label_zh": "中性"},
    )
    result = _read_fg_us(tmp_path)
    assert result["fg_dial_us"] == 54
    assert result["fg_n_legs"] == 11
    assert result["fg_as_of"] == "2026-07-14"


def test_read_vol_weather_absent(tmp_path):
    """Missing vol_weather.json -> all columns None."""
    result = _read_vol_weather(tmp_path)
    assert result["vix_pctile_252"] is None
    assert result["vix_chg5d_pctile"] is None
    assert result["vvix_vix_ratio"] is None
    assert result["vix9d_vix3m"] is None
    assert result["vol_weather_as_of"] is None


def test_read_vol_weather_present(tmp_path):
    """Valid vol_weather.json with expected chip structure -> values extracted."""
    _write_json(
        tmp_path / "site" / "basketdata" / "vol_weather.json",
        {
            "as_of": "2026-07-14",
            "chips": [
                {"key": "vix_level", "pctile": 0.32, "value": 16.3},
                {"key": "vix_velocity", "pctile": 0.45, "value": -0.5},
                {"key": "vvix_vix", "pctile": 0.55, "value": 5.2},
                {"key": "term_slope", "pctile": 0.60, "value": 0.88},
            ],
        },
    )
    result = _read_vol_weather(tmp_path)
    assert result["vix_pctile_252"] == pytest.approx(0.32)
    assert result["vix_chg5d_pctile"] == pytest.approx(0.45)
    assert result["vvix_vix_ratio"] == pytest.approx(5.2)
    assert result["vix9d_vix3m"] == pytest.approx(0.88)
    assert result["vol_weather_as_of"] == "2026-07-14"


def test_read_breadth_split_absent(tmp_path):
    """Missing breadth_split.json -> all columns None."""
    result = _read_breadth_split(tmp_path)
    assert result["ai_breadth_spread_50"] is None
    assert result["ai_pct50"] is None
    assert result["nonai_pct50"] is None
    assert result["breadth_split_as_of"] is None


def test_read_breadth_split_present(tmp_path):
    """Valid breadth_split.json -> values extracted from latest key."""
    _write_json(
        tmp_path / "site" / "basketdata" / "breadth_split.json",
        {
            "as_of": "2026-07-14",
            "latest": {
                "spread_50": 12.5,
                "ai_pct50": 0.65,
                "nonai_pct50": 0.40,
            },
        },
    )
    result = _read_breadth_split(tmp_path)
    assert result["ai_breadth_spread_50"] == pytest.approx(12.5)
    assert result["ai_pct50"] == pytest.approx(0.65)
    assert result["nonai_pct50"] == pytest.approx(0.40)
    assert result["breadth_split_as_of"] == "2026-07-14"


# ── staleness cutoff tests ─────────────────────────────────────────────────────

def test_stale_cutoff_fresh():
    """A store date 3 days before the row date is fresh (within 7-day window)."""
    assert not _stale_cutoff(pd.Timestamp("2026-07-10"), "2026-07-13", days=7)


def test_stale_cutoff_exactly_on_boundary():
    """Exactly 7 days apart is NOT stale (boundary inclusive)."""
    assert not _stale_cutoff(pd.Timestamp("2026-07-06"), "2026-07-13", days=7)


def test_stale_cutoff_stale():
    """A store date 8+ days before the row date is stale."""
    assert _stale_cutoff(pd.Timestamp("2026-06-13"), "2026-07-13", days=7)


def test_stale_cutoff_none_date_is_stale():
    """None last_idx_date always returns stale."""
    assert _stale_cutoff(None, "2026-07-13")


def test_read_raw_vol_vix_close_stale(tmp_path, monkeypatch):
    """VIX store whose last date is 30 days before the row date -> vix_close None."""
    # Build a tiny _VIX parquet that is stale
    row_date = "2026-07-13"
    stale_date = "2026-06-13"   # 30 days before row_date
    vix_df = _make_price_df([stale_date], [20.0], col="close")

    # Monkeypatch store.read at the module level used by archive_context_snapshots
    import scripts.archive_context_snapshots as _mod

    def _fake_store_read(group, name):
        if group == "yahoo" and name == "_VIX":
            return vix_df
        return None

    monkeypatch.setattr(_mod.store, "read", _fake_store_read)
    # Also patch config.data_dir so cboe reads fail gracefully (no cboe dir)
    monkeypatch.setattr(_mod.config, "data_dir", lambda: tmp_path)

    result = _read_raw_vol(row_date)
    assert result["vix_close"] is None, "stale VIX must be None"
    # CBOE files absent -> also None
    assert result["vix1d"] is None
    assert result["dspx"] is None


def test_read_raw_vol_vix_close_fresh(tmp_path, monkeypatch):
    """VIX store with a fresh date -> vix_close populated."""
    row_date = "2026-07-13"
    vix_df = _make_price_df(["2026-07-12"], [16.3], col="close")

    import scripts.archive_context_snapshots as _mod

    def _fake_store_read(group, name):
        if group == "yahoo" and name == "_VIX":
            return vix_df
        return None

    monkeypatch.setattr(_mod.store, "read", _fake_store_read)
    monkeypatch.setattr(_mod.config, "data_dir", lambda: tmp_path)

    result = _read_raw_vol(row_date)
    assert result["vix_close"] == pytest.approx(16.3)


def test_read_raw_vol_cboe_present(tmp_path, monkeypatch):
    """Present cboe parquets with fresh dates -> values populated."""
    row_date = "2026-07-13"

    import scripts.archive_context_snapshots as _mod

    # Store.read returns None for all (vix_close will be None)
    monkeypatch.setattr(_mod.store, "read", lambda g, n: None)
    monkeypatch.setattr(_mod.config, "data_dir", lambda: tmp_path)

    # Write fixture cboe parquets
    cboe_dir = tmp_path / "cboe"
    cboe_dir.mkdir(parents=True)
    for name, val in [("vix1d", 10.5), ("dspx", 1100.0), ("vixeq", 14.5),
                      ("cor1m", 0.45), ("cor3m", 0.38)]:
        df = _make_price_df(["2026-07-13"], [val], col="close")
        df.to_parquet(cboe_dir / f"{name}.parquet")

    result = _read_raw_vol(row_date)
    assert result["vix1d"] == pytest.approx(10.5)
    assert result["dspx"] == pytest.approx(1100.0)
    assert result["vixeq"] == pytest.approx(14.5)
    assert result["cor1m"] == pytest.approx(0.45)
    assert result["cor3m"] == pytest.approx(0.38)


def test_read_rsp_spy_ratio_absent(monkeypatch):
    """Both stores absent -> ratio None."""
    import scripts.archive_context_snapshots as _mod
    monkeypatch.setattr(_mod.store, "read", lambda g, n: None)
    result = _read_rsp_spy_ratio("2026-07-13")
    assert result is None


def test_read_rsp_spy_ratio_present(monkeypatch):
    """Both stores present and fresh -> ratio computed."""
    import scripts.archive_context_snapshots as _mod

    rsp_df = _make_price_df(["2026-07-12", "2026-07-13"], [200.0, 205.0])
    spy_df = _make_price_df(["2026-07-12", "2026-07-13"], [400.0, 410.0])

    def _fake_read(group, name):
        if group == "yahoo" and name == "RSP":
            return rsp_df
        if group == "yahoo" and name == "SPY":
            return spy_df
        return None

    monkeypatch.setattr(_mod.store, "read", _fake_read)
    result = _read_rsp_spy_ratio("2026-07-13")
    assert result == pytest.approx(205.0 / 410.0)


def test_read_rsp_spy_ratio_stale(monkeypatch):
    """RSP/SPY stores stale (30 days before row date) -> ratio None."""
    import scripts.archive_context_snapshots as _mod

    rsp_df = _make_price_df(["2026-06-01"], [200.0])
    spy_df = _make_price_df(["2026-06-01"], [400.0])

    def _fake_read(group, name):
        if group == "yahoo" and name == "RSP":
            return rsp_df
        if group == "yahoo" and name == "SPY":
            return spy_df
        return None

    monkeypatch.setattr(_mod.store, "read", _fake_read)
    result = _read_rsp_spy_ratio("2026-07-13")
    assert result is None


# ── main() integration ────────────────────────────────────────────────────────

def test_main_absent_safe(tmp_path, monkeypatch):
    """main() must exit 0 with no source files present."""
    import scripts.archive_context_snapshots as _mod
    monkeypatch.setattr(_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_mod.config, "ROOT", tmp_path)
    monkeypatch.setattr(_mod.store, "read", lambda g, n: None)
    rc = main()
    assert rc == 0


def test_main_writes_and_keep_first(tmp_path, monkeypatch):
    """main() writes one row then is a no-op on re-run for the same date."""
    import scripts.archive_context_snapshots as _mod
    monkeypatch.setattr(_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_mod.config, "ROOT", tmp_path)
    monkeypatch.setattr(_mod.store, "read", lambda g, n: None)

    regime = {
        "date": "2026-07-06", "quad": "Q1", "liquidity_overlay": "neutral",
        "cycle_tag": "mid", "transition_state": "CALM", "confidence": 0.55,
        "vol_regime": {"regime": "low"},
    }
    ms = {"verdict": "RISK_ON", "score": 75}
    _write_json(tmp_path / "regime" / "latest.json", regime)
    _write_json(tmp_path / "market_state" / "latest.json", ms)

    rc1 = main()
    assert rc1 == 0
    archive = tmp_path / "signal_archive" / ARCHIVE_FILE
    assert archive.exists()
    df = pd.read_parquet(archive)
    assert len(df) == 1
    assert df.loc[0, "quad"] == "Q1"

    rc2 = main()
    assert rc2 == 0
    df2 = pd.read_parquet(archive)
    assert len(df2) == 1  # keep-FIRST: no duplicate row added


def test_main_with_fixture_jsons_values_land(tmp_path, monkeypatch):
    """Fixture JSONs for all new sources -> values appear in the archived row."""
    import scripts.archive_context_snapshots as _mod
    monkeypatch.setattr(_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_mod.config, "ROOT", tmp_path)
    monkeypatch.setattr(_mod.store, "read", lambda g, n: None)

    row_date = "2026-07-14"
    # regime JSON
    _write_json(tmp_path / "regime" / "latest.json", {"date": row_date, "quad": "Q2"})
    # US fear_greed
    _write_json(
        tmp_path / "site" / "basketdata" / "fear_greed.json",
        {"dial": 54, "n_legs_qualifying": 11, "as_of": row_date},
    )
    # vol_weather
    _write_json(
        tmp_path / "site" / "basketdata" / "vol_weather.json",
        {
            "as_of": row_date,
            "chips": [
                {"key": "vix_level", "pctile": 0.32, "value": 16.0},
                {"key": "vix_velocity", "pctile": 0.45, "value": -0.3},
                {"key": "vvix_vix", "pctile": 0.55, "value": 5.1},
                {"key": "term_slope", "pctile": 0.6, "value": 0.87},
            ],
        },
    )
    # breadth_split
    _write_json(
        tmp_path / "site" / "basketdata" / "breadth_split.json",
        {"as_of": row_date, "latest": {"spread_50": 12.5, "ai_pct50": 0.65, "nonai_pct50": 0.40}},
    )
    # Fresh cboe parquets
    cboe_dir = tmp_path / "cboe"
    cboe_dir.mkdir(parents=True)
    for name, val in [("vix1d", 9.9), ("dspx", 1050.0), ("vixeq", 13.8),
                      ("cor1m", 0.43), ("cor3m", 0.37)]:
        _make_price_df([row_date], [val]).to_parquet(cboe_dir / f"{name}.parquet")

    rc = main()
    assert rc == 0
    df = pd.read_parquet(tmp_path / "signal_archive" / ARCHIVE_FILE)
    assert len(df) == 1
    r = df.iloc[0]
    assert r["fg_dial_us"] == 54
    assert r["fg_n_legs"] == 11
    assert r["vix_pctile_252"] == pytest.approx(0.32)
    assert r["vix_chg5d_pctile"] == pytest.approx(0.45)
    assert r["vvix_vix_ratio"] == pytest.approx(5.1)
    assert r["vix9d_vix3m"] == pytest.approx(0.87)
    assert r["vix1d"] == pytest.approx(9.9)
    assert r["dspx"] == pytest.approx(1050.0)
    assert r["vixeq"] == pytest.approx(13.8)
    assert r["cor1m"] == pytest.approx(0.43)
    assert r["cor3m"] == pytest.approx(0.37)
    assert r["ai_breadth_spread_50"] == pytest.approx(12.5)
    assert r["ai_pct50"] == pytest.approx(0.65)
    assert r["nonai_pct50"] == pytest.approx(0.40)
