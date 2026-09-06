"""RED-first tests for engine/credit_window.py — the HY/IG bond issuance
window gate (packet B-F09-2). Fixtures build tiny parquet files under
tmp_path/{fred,archive,yahoo}/; every test passes root=tmp_path."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import credit_window as cw


def _write_series(path, values, start="2024-01-01"):
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start=start, periods=len(values))
    df = pd.DataFrame({"value": values}, index=idx)
    df.to_parquet(path)


def _write_close(path, values, start="2024-01-01"):
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start=start, periods=len(values))
    df = pd.DataFrame({"close": values}, index=idx)
    df.to_parquet(path)


def test_scored_flag_is_false():
    assert cw.SCORED is False


def test_input_state_spread_range_thresholds():
    assert cw.input_state("spread_range", 0) == "open"
    assert cw.input_state("spread_range", 33.0) == "open"
    assert cw.input_state("spread_range", 33.1) == "neutral"
    assert cw.input_state("spread_range", 66.0) == "neutral"
    assert cw.input_state("spread_range", 66.1) == "shut"
    assert cw.input_state("spread_range", 100) == "shut"


def test_input_state_spread_drift_thresholds():
    assert cw.input_state("spread_drift", -20) == "open"
    assert cw.input_state("spread_drift", -15) == "open"
    assert cw.input_state("spread_drift", -14.9) == "neutral"
    assert cw.input_state("spread_drift", 24.9) == "neutral"
    assert cw.input_state("spread_drift", 25) == "shut"
    assert cw.input_state("spread_drift", 60) == "shut"


def test_input_state_rates_vol_thresholds():
    assert cw.input_state("rates_vol", 0) == "open"
    assert cw.input_state("rates_vol", 40) == "open"
    assert cw.input_state("rates_vol", 40.1) == "neutral"
    assert cw.input_state("rates_vol", 75) == "neutral"
    assert cw.input_state("rates_vol", 75.1) == "shut"
    assert cw.input_state("rates_vol", 100) == "shut"


def test_input_state_none_is_unknown():
    for key in ("spread_range", "spread_drift", "rates_vol", "anything"):
        assert cw.input_state(key, None) == "unknown"


def test_segment_open_requires_two_open_inputs():
    state, n, low = cw.segment_state(["open", "neutral", "neutral"])
    assert state == "neutral"
    assert state != "open"


def test_segment_not_evaluable_below_min_inputs():
    assert cw.segment_state(["open", "unknown", "unknown"]) == ("not_evaluable", 1, True)
    state, n, low = cw.segment_state(["unknown", "unknown", "unknown"])
    assert state == "not_evaluable"
    assert n == 0
    assert low is True
    assert state != "open"


def test_window_state_null_path_when_hy_series_missing(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)
    out = cw.window_state(root=tmp_path)
    segs = {s["key"]: s for s in out["segments"]}
    assert segs["hy"]["state"] == "not_evaluable"
    assert segs["hy"]["rail"] is None
    assert segs["ig"]["state"] != "not_evaluable"


def test_window_state_null_path_when_move_missing(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260)
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)
    out = cw.window_state(root=tmp_path)
    for seg in out["segments"]:
        assert seg["low_confidence"] is True


def test_as_of_propagates_per_input_and_to_top_level(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260, start="2024-01-01")
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260, start="2024-01-01")
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260, start="2024-01-01")
    out = cw.window_state(root=tmp_path)
    for seg in out["segments"]:
        for inp in seg["inputs"]:
            assert inp["as_of"] is not None
    assert out["as_of"] == max(
        i["as_of"] for seg in out["segments"] for i in seg["inputs"] if i["as_of"]
    )


def test_calendar_null_is_declared(tmp_path):
    out = cw.window_state(root=tmp_path)
    assert out["calendar"] == {"available": False, "reason": "no_upcoming_deal_calendar_source"}
    assert out["research_only"] is True


def test_no_issuer_identity_or_par_fields(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260)
    _write_series(tmp_path / "fred" / f"{cw.FRED_IG}.parquet", [1.0] * 260)
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)
    out = cw.window_state(root=tmp_path)
    banned = {"issuer", "issuer_name", "isin", "cusip", "ticker", "par", "notional",
              "holdings", "name_match"}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k not in banned
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)


def test_module_is_pure_and_writes_nothing(tmp_path):
    _write_series(tmp_path / "fred" / f"{cw.FRED_HY}.parquet", [3.0] * 260)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    cw.window_state(root=tmp_path)
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert before == after


def test_not_imported_by_any_scoring_module():
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    scoring_dirs = [root / "engine"]
    hits = []
    for d in scoring_dirs:
        for f in d.glob("*.py"):
            if f.name in ("credit_window.py",):
                continue
            if "score" not in f.name and "regime" not in f.name and "axis" not in f.name:
                continue
            try:
                tree = ast.parse(f.read_text())
            except Exception:  # noqa: BLE001
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and "credit_window" in node.module:
                    hits.append(f.name)
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "credit_window" in alias.name:
                            hits.append(f.name)
    assert hits == []


def test_rail_absent_when_spread_range_unknown(tmp_path):
    _write_close(tmp_path / "yahoo" / f"{cw.MOVE_TICKER}.parquet", [80.0] * 260)
    out = cw.window_state(root=tmp_path)
    for seg in out["segments"]:
        assert seg["rail"] is None
