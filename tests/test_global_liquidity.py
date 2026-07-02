"""Pure-function tests for the global central-bank liquidity leaf — no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import global_liquidity as gl  # noqa: E402

_IDX = pd.date_range("2018-01-05", periods=200, freq="W-FRI")


def test_bank_usd_conversions():
    raw = pd.Series(np.full(len(_IDX), 100.0), index=_IDX)        # 100 (raw units)
    # USD leg (Fed): fx None -> just ×unit_mult
    assert gl.bank_usd(raw, 1.0e6, None).iloc[-1] == 100.0 * 1e6
    # EUR leg: local ×1.10 (EURUSD multiply)
    fx_eur = pd.Series(np.full(len(_IDX), 1.10), index=_IDX)
    assert abs(gl.bank_usd(raw, 1.0e6, fx_eur).iloc[-1] - 100.0 * 1e6 * 1.10) < 1
    # JPY leg: invert handled by passing 1/fx -> local /150
    fx_jpy_inv = pd.Series(np.full(len(_IDX), 1.0 / 150.0), index=_IDX)
    assert abs(gl.bank_usd(raw, 1.0e8, fx_jpy_inv).iloc[-1] - 100.0 * 1e8 / 150.0) < 1e3


def test_aggregate_sums_where_all_present():
    a = pd.Series(np.linspace(1e12, 2e12, len(_IDX)), index=_IDX)
    b = pd.Series(np.linspace(3e12, 4e12, len(_IDX)), index=_IDX[50:].union(_IDX[:50]))
    df = gl.aggregate({"fed": a, "ecb": b})
    assert "total" in df and not df.empty
    assert abs(df["total"].iloc[-1] - (df["fed"].iloc[-1] + df["ecb"].iloc[-1])) < 1


def test_impulse_pct():
    s = pd.Series(np.arange(1.0, 121.0), index=pd.date_range("2020-01-03", periods=120, freq="W-FRI"))
    # 13-week change of a +1/wk ramp at the end: (120-107)/107
    assert abs(gl._impulse(s, 13) - (13.0 / 107.0 * 100.0)) < 1e-6
    assert gl._impulse(s, 999) is None


def test_snapshot_smoke(monkeypatch):
    raw = pd.Series(np.linspace(8.0e6, 9.0e6, len(_IDX)), index=_IDX)   # WALCL-like $mn
    monkeypatch.setattr(gl, "_fred_series", lambda sid: raw.copy())
    monkeypatch.setattr(gl, "_fx_to_usd", lambda key, inv: pd.Series(1.10, index=_IDX))
    cfg = {"banks": {
        "fed": {"series": "WALCL", "unit_mult": 1e6, "fx": None, "invert": False, "label_en": "Fed", "label_zh": "美联储"},
        "ecb": {"series": "ECBASSETSW", "unit_mult": 1e6, "fx": "EURUSD=X", "invert": False, "label_en": "ECB", "label_zh": "欧洲央行"}},
        "impulse_windows_w": [13, 52]}
    s = gl.snapshot(cfg)
    assert s and s["n_banks"] == 2 and s["total_usd_tn"] > 0
    assert s["state"] in ("expanding", "contracting", "flat")
    assert abs(sum(b["share"] for b in s["banks"]) - 100.0) < 0.5
    assert "13w" in s["impulse_pct"] and len(s["spark"]) > 0


def test_snapshot_degrades_no_data(monkeypatch):
    monkeypatch.setattr(gl, "_fred_series", lambda sid: None)
    assert gl.snapshot({"banks": {"fed": {"series": "WALCL"}}}) is None


# INTL-51 — per-bank as-of dates must be surfaced in the snapshot
def test_snapshot_asof_by_bank(monkeypatch):
    """snapshot() must return asof_by_bank with a date per bank and expose raw_asof on each bank dict."""
    raw = pd.Series(np.linspace(8.0e6, 9.0e6, len(_IDX)), index=_IDX)
    monkeypatch.setattr(gl, "_fred_series", lambda sid: raw.copy())
    monkeypatch.setattr(gl, "_fx_to_usd", lambda key, inv: pd.Series(1.10, index=_IDX))
    cfg = {"banks": {
        "fed": {"series": "WALCL",      "unit_mult": 1e6, "fx": None,       "invert": False, "label_en": "Fed", "label_zh": "美联储"},
        "ecb": {"series": "ECBASSETSW", "unit_mult": 1e6, "fx": "EURUSD=X", "invert": False, "label_en": "ECB", "label_zh": "欧洲央行"}},
        "impulse_windows_w": [13, 52]}
    s = gl.snapshot(cfg)
    assert s is not None
    # asof_by_bank must be a dict with a key per bank
    asof_map = s.get("asof_by_bank")
    assert isinstance(asof_map, dict)
    assert set(asof_map.keys()) == {"fed", "ecb"}
    # Each value must be a non-empty date string
    for bid, asof_str in asof_map.items():
        assert isinstance(asof_str, str) and len(asof_str) == 10, \
            f"bank {bid!r}: asof_by_bank value should be YYYY-MM-DD, got {asof_str!r}"
    # Each bank dict in the banks list must also carry raw_asof
    for b in s["banks"]:
        assert "raw_asof" in b, f"bank {b['id']!r} dict missing raw_asof"
        assert isinstance(b["raw_asof"], str) and len(b["raw_asof"]) == 10
