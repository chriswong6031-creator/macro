"""Hermetic tests for engine/china_radar_ic.py — the CN radar IC grader.

All tests are self-contained (tmp_path, synthetic data, monkeypatched prices).
No live data, no network, no side-effects on the real store.

Key assertions
--------------
(a) Degrade-safe: no ledger / empty ledger → valid dict, n_matured 0, never raises.
(b) Output shape matches signal_governor._radar_reading('cn') expectations:
    governor reads by_horizon[h]["ic_daily_hac"] for mean_ic / t_hac / n_days,
    and by_horizon[h]["n_matured"]; while dormant → trust 1.0.
(c) Synthetic dense ledger with ≥6 dates each with ≥10 events DOES produce an
    ic_daily_hac dict with t_hac (proves the HAC path works when data is dense).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import engine.china_radar_ic as cric
from engine import signal_governor as gov


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_ledger(tmp_path: Path, rows: list[dict]) -> None:
    """Write a synthetic ledger.parquet to data/china_radar/."""
    d = tmp_path / "data" / "china_radar"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(d / "ledger.parquet", index=False)


def _write_price(tmp_path: Path, ticker: str, group: str,
                 start: str, end: str, ret: float) -> None:
    """Write data/<group>/<ticker>.parquet: close grows monotonically from 100."""
    d = tmp_path / "data" / group
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, end, freq="B")
    close = pd.Series(
        [100.0 * (1.0 + ret * i / max(len(idx) - 1, 1)) for i in range(len(idx))],
        index=idx,
    )
    pd.DataFrame({"close": close}).to_parquet(d / f"{ticker}.parquet")


def _ledger_row(
    etf: str, fired_date: str, sign: str = "positive", signal_value: float = 5.0,
) -> dict:
    return {
        "event_id": f"{etf}|{fired_date}",
        "fired_date": fired_date,
        "pair": f"sig->{etf}",
        "signal_key": "test_signal",
        "family": None,
        "sector_etf": etf,
        "sector_en": "Test Sector",
        "sector_zh": "测试",
        "sign": sign,
        "rs_at_fire": 0.0,
        "signal_value": signal_value,
    }


# ---------------------------------------------------------------------------
# (a) Degrade-safe: no ledger
# ---------------------------------------------------------------------------

def test_no_ledger_returns_valid_dict(tmp_path):
    """compute_ic with no ledger file → valid schema, n_matured=0, never raises."""
    result = cric.compute_ic(today=date(2026, 7, 22), root=tmp_path)
    assert result["schema"] == cric.SCHEMA
    assert result["n_matured"] == 0
    assert result["ic_all"] is None
    assert "by_horizon" in result
    for h_str, blk in result["by_horizon"].items():
        assert "n_matured" in blk
        assert "ic_daily_hac" in blk
        assert blk["n_matured"] == 0


def test_empty_ledger_returns_valid_dict(tmp_path):
    """Empty ledger parquet → same degrade path."""
    _write_ledger(tmp_path, [])
    result = cric.compute_ic(today=date(2026, 7, 22), root=tmp_path)
    assert result["schema"] == cric.SCHEMA
    assert result["n_matured"] == 0
    assert "by_horizon" in result


def test_all_events_too_fresh_n_matured_zero(tmp_path):
    """Events fired yesterday are too fresh to mature at any horizon."""
    yesterday = (date(2026, 7, 22) - timedelta(days=1)).isoformat()
    rows = [_ledger_row("512200.SS", yesterday) for _ in range(5)]
    _write_ledger(tmp_path, rows)
    result = cric.compute_ic(today=date(2026, 7, 22), root=tmp_path)
    for h_str, blk in result["by_horizon"].items():
        assert blk["n_matured"] == 0, f"h={h_str}: expected 0 matured, got {blk['n_matured']}"


def test_venue_row_skipped_gracefully(tmp_path):
    """Rows with sector_etf=None (venue pairs) must not cause errors."""
    rows = [
        {
            "event_id": "venue|2026-06-20",
            "fired_date": "2026-06-20",
            "pair": "venue_offshore_gap->china",
            "signal_key": "venue_offshore_gap",
            "family": "venue",
            "sector_etf": None,
            "sector_en": "CSI 300",
            "sector_zh": "沪深300",
            "sign": "positive",
            "rs_at_fire": 5.0,
            "signal_value": 5.0,
        }
    ]
    _write_ledger(tmp_path, rows)
    result = cric.compute_ic(today=date(2026, 7, 22), root=tmp_path)
    # venue rows are skipped (no sector_etf) → n_matured 0 for all horizons
    assert result["n_matured"] == 0


# ---------------------------------------------------------------------------
# (b) Output shape matches signal_governor._radar_reading('cn')
# ---------------------------------------------------------------------------

def test_governor_reads_dormant_output(tmp_path):
    """With sparse CN data the governor must return trust=1.0 for the radar signal.

    We test the real governor._radar_reading path by pointing it at a tmp file
    that matches the shape compute_ic emits.
    """
    # Write a minimal but schema-valid radar_ic.json in the governor's expected location
    out_p = tmp_path / "data" / "china_hub" / "radar_ic.json"
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Simulate the sparse/dormant output (n_days < 6)
    dormant_payload = {
        "schema": cric.SCHEMA,
        "as_of": "2026-07-22",
        "generated_at": "2026-07-22T00:00:00+00:00",
        "n_events": 16,
        "n_matured": 0,
        "ic_all": None,
        "note": "Accruing — dormant",
        "by_horizon": {
            "5":  {"n_matured": 0, "ic_all": None, "ic_daily_hac": {"n_days": 0}, "by_sign": {}},
            "10": {"n_matured": 0, "ic_all": None, "ic_daily_hac": {"n_days": 0}, "by_sign": {}},
            "21": {"n_matured": 0, "ic_all": None, "ic_daily_hac": {"n_days": 0}, "by_sign": {}},
        },
    }
    out_p.write_text(json.dumps(dormant_payload))

    rr = gov._radar_reading(tmp_path, region="cn")
    reading = rr["reading"]
    coverage = rr["coverage"]

    # Dormant: no valid HAC horizon → reading is None
    assert reading is None, f"Expected None reading (dormant), got {reading}"

    # _gate with no reading → trust 1.0
    gate_result = gov._gate("radar", reading, coverage)
    assert gate_result["trust"] == 1.0
    assert gate_result["demoted"] is False


def test_output_schema_fields_present(tmp_path):
    """compute_ic returns all fields the governor walks."""
    result = cric.compute_ic(today=date(2026, 7, 22), root=tmp_path)
    assert "by_horizon" in result
    for h_str, blk in result["by_horizon"].items():
        # Fields _pick_reading and _coverage access
        assert "n_matured" in blk, f"h={h_str}: missing n_matured"
        assert "ic_daily_hac" in blk, f"h={h_str}: missing ic_daily_hac"
        hac = blk["ic_daily_hac"]
        # Dormant form: {"n_days": k}
        # Gradeable form: {"mean_ic":..., "t_hac":..., "n":...}
        assert ("n_days" in hac) or ("t_hac" in hac), (
            f"h={h_str}: ic_daily_hac has neither n_days nor t_hac: {hac}"
        )


# ---------------------------------------------------------------------------
# (c) Dense synthetic ledger → ic_daily_hac with t_hac
# ---------------------------------------------------------------------------

def test_dense_synthetic_ledger_produces_valid_hac(tmp_path):
    """With ≥6 dates each with ≥10 sector events, daily-HAC must return a t_hac.

    We fabricate events fired on 8 dates, 12 ETFs each, monotonically scored,
    and mock _fwd_rel_return to return a return proportional to signed_score.
    With consistent positive alignment the daily IC series should be uniformly
    positive, and ic_summary should return a valid t_hac.
    """
    N_DATES = 8
    N_ETFS = 12
    today = date(2026, 7, 22)
    # Fired dates: 30d, 31d, ..., 37d before today — all mature at h=5 and h=10
    base = today - timedelta(days=30 + N_DATES)
    fired_dates = [(base + timedelta(days=i)).isoformat() for i in range(N_DATES)]

    # Build ETF tickers and signal values: ETF0 weakest (sv=1), ETF11 strongest (sv=12)
    etfs = [f"ETF{i:02d}.SS" for i in range(N_ETFS)]
    signal_values = [float(i + 1) for i in range(N_ETFS)]  # 1..12

    rows = []
    for fd in fired_dates:
        for etf, sv in zip(etfs, signal_values):
            rows.append(_ledger_row(etf, fd, sign="positive", signal_value=sv))
    _write_ledger(tmp_path, rows)

    # Mock _fwd_rel_return: return proportional to signed signal_value (monotonic alignment)
    # signed_score = signal_value * 1 (all positive sign).  fwd return = sv * 0.001
    sv_map = {etf: sv for etf, sv in zip(etfs, signal_values)}

    def _mock_fwd(etf, root, start_date, horizon_d, _bench_cache=None):
        return sv_map.get(etf, 0.0) * 0.001

    with patch.object(cric, "_fwd_rel_return", side_effect=_mock_fwd):
        result = cric.compute_ic(today=today, horizons=(5, 10), root=tmp_path)

    # Check the h=5 block — that's where all dates will be matured
    blk5 = result["by_horizon"].get("5", {})
    assert blk5["n_matured"] == N_DATES * N_ETFS, (
        f"Expected {N_DATES * N_ETFS} matured, got {blk5['n_matured']}"
    )

    hac5 = blk5.get("ic_daily_hac", {})
    # Must have produced a valid HAC result (not the dormant {"n_days": k} form)
    assert "t_hac" in hac5, (
        f"Expected ic_daily_hac to have t_hac with dense data, got: {hac5}"
    )
    assert hac5["t_hac"] is not None
    # Monotonic alignment → positive mean IC and positive t_hac
    assert hac5.get("mean_ic", 0) > 0, f"Expected positive mean_ic, got {hac5}"
    assert hac5.get("t_hac", 0) > 0, f"Expected positive t_hac, got {hac5}"


def test_by_sign_accuracy(tmp_path):
    """by_sign['positive'].dir_accuracy should be 1.0 when all positive events
    have positive CSI300-relative returns."""
    today = date(2026, 7, 22)
    fired = (today - timedelta(days=30)).isoformat()
    etfs = [f"ETF{i}.SS" for i in range(4)]
    rows = [_ledger_row(e, fired, sign="positive", signal_value=float(i + 1))
            for i, e in enumerate(etfs)]
    _write_ledger(tmp_path, rows)

    fwd_map = {f"ETF{i}.SS": 0.01 * (i + 1) for i in range(4)}  # all positive

    def _mock_fwd(etf, root, start_date, horizon_d, _bench_cache=None):
        return fwd_map.get(etf)

    with patch.object(cric, "_fwd_rel_return", side_effect=_mock_fwd):
        result = cric.compute_ic(today=today, horizons=(5,), root=tmp_path)

    blk = result["by_horizon"]["5"]
    assert blk["n_matured"] == 4
    assert "positive" in blk["by_sign"]
    assert blk["by_sign"]["positive"]["dir_accuracy"] == 1.0


def test_negative_sign_dir_accuracy(tmp_path):
    """by_sign['negative'].dir_accuracy should be 1.0 when all negative events
    have negative CSI300-relative returns."""
    today = date(2026, 7, 22)
    fired = (today - timedelta(days=30)).isoformat()
    etfs = [f"ETFN{i}.SS" for i in range(4)]
    rows = [_ledger_row(e, fired, sign="negative", signal_value=-float(i + 1))
            for i, e in enumerate(etfs)]
    _write_ledger(tmp_path, rows)

    fwd_map = {f"ETFN{i}.SS": -0.01 * (i + 1) for i in range(4)}  # all negative (bearish = correct)

    def _mock_fwd(etf, root, start_date, horizon_d, _bench_cache=None):
        return fwd_map.get(etf)

    with patch.object(cric, "_fwd_rel_return", side_effect=_mock_fwd):
        result = cric.compute_ic(today=today, horizons=(5,), root=tmp_path)

    blk = result["by_horizon"]["5"]
    assert blk["n_matured"] == 4
    assert "negative" in blk["by_sign"]
    assert blk["by_sign"]["negative"]["dir_accuracy"] == 1.0


def test_write_creates_json_file(tmp_path):
    """compute_ic must write data/china_hub/radar_ic.json."""
    cric.compute_ic(today=date(2026, 7, 22), root=tmp_path)
    out_p = tmp_path / "data" / "china_hub" / "radar_ic.json"
    assert out_p.exists(), "Expected data/china_hub/radar_ic.json to be written"
    payload = json.loads(out_p.read_text())
    assert payload["schema"] == cric.SCHEMA
    assert "by_horizon" in payload
