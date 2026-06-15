"""Tests for the DISPLAY-ONLY OKX retail positioning chips (P1a): rubik parse in
collectors/okx.py, the btc_signals.leverage display columns, the contrarian lean
label, and the bilingual vector.html.j2 chips. Load-bearing invariant: these
symbols NEVER enter scoring. See research/OKX_RETAIL_CHIPS_SPEC.md."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.okx import OkxAdapter  # noqa: E402
from engine import btc_signals  # noqa: E402
from lib import config  # noqa: E402
from scripts.build_vector import _okx_ls_lean  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _adapter(payload):
    a = OkxAdapter()                                   # reads config (has the rubik URLs)
    a.http_get = lambda *args, **kw: _FakeResp(payload)
    return a


# ---- 1. rubik parse (incl. the buy/sell column-order gotcha) -----------------
def test_ls_ratio_parse():
    # newest-first rows [ts_ms, ratio]; include a duplicate date to exercise sort/dedup
    payload = {"data": [["1718064000000", "1.85"], ["1717977600000", "1.40"],
                        ["1717977600000", "1.41"]]}
    df = _adapter(payload)._ls_account_ratio()
    assert list(df.columns) == ["ls_ratio"]
    assert df.index.is_monotonic_increasing
    assert pd.api.types.is_float_dtype(df["ls_ratio"])
    assert _adapter({"data": []})._ls_account_ratio() is None


def test_taker_parse_buy_sell_order():
    # rows are [ts, sellVol, buyVol] -> buy_ratio = buy/(buy+sell). Forcing known
    # values catches a silent buy/sell column flip.
    payload = {"data": [["1718064000000", "300", "100"],   # later ts: sell 300, buy 100 -> 0.25
                        ["1717977600000", "100", "300"]]}   # earlier ts: sell 100, buy 300 -> 0.75
    df = _adapter(payload)._taker_volume()
    assert list(df.columns) == ["taker_buy_ratio"]
    assert df["taker_buy_ratio"].between(0, 1).all()
    assert df["taker_buy_ratio"].iloc[0] == pytest.approx(0.75)   # earliest first after sort
    assert df["taker_buy_ratio"].iloc[-1] == pytest.approx(0.25)
    # zero-volume guard -> NaN -> dropped, no crash / no divide-by-zero
    z = _adapter({"data": [["1718064000000", "0", "0"]]})._taker_volume()
    assert z is not None and z.empty


# ---- 2. signal columns + contrarian lean label ------------------------------
def test_leverage_chip_columns():
    n = 400
    idx = pd.bdate_range("2024-01-01", periods=n)
    ls = pd.Series(1.2 + 0.3 * np.sin(np.arange(n) / 20), index=idx)
    tk = pd.Series(0.5 + 0.05 * np.sin(np.arange(n) / 15), index=idx)
    inp = {"price": pd.DataFrame({"close": pd.Series(100 + np.arange(n) * 0.1, index=idx)}),
           "okx_ls_ratio": ls, "okx_taker_buy": tk}
    lev = btc_signals.leverage(inp, config.load()["vector"]["leverage"])
    for c in ("okx_ls_ratio", "okx_ls_ratio_pctile", "okx_ls_ratio_z",
              "okx_taker_buy", "okx_taker_buy_pctile"):
        assert c in lev.columns
    assert lev["okx_ls_ratio_pctile"].dropna().between(0, 100).all()


def test_lean_label():
    assert _okx_ls_lean(2.0) == "crowded_long"      # z > 1.5
    assert _okx_ls_lean(-2.0) == "crowded_short"    # z < -1.5
    assert _okx_ls_lean(0.0) == "balanced"
    assert _okx_ls_lean(None) == "balanced"
    assert _okx_ls_lean(float("nan")) == "balanced"


# ---- 3. display-only invariant (load-bearing) -------------------------------
def test_display_only_invariant():
    for sym in ("okx_ls_ratio", "okx_taker_buy", "okx_ls_ratio_z"):
        assert sym not in (ROOT / "engine" / "axes.py").read_text()
        assert sym not in (ROOT / "engine" / "regime.py").read_text()
    # the new columns must NOT feed leverage_stress: slice the parts/weights
    # construction (up to the leverage_stress assignment) — the chips live AFTER it
    src = inspect.getsource(btc_signals.leverage)
    stress_block = src.split("parts, weights = [], []")[1].split('out["leverage_stress"]')[0]
    assert "okx_ls" not in stress_block and "okx_taker" not in stress_block
    # nor the allocation / compute_all scoring paths
    assert "okx_ls_ratio" not in inspect.getsource(btc_signals.allocation)


# ---- 4. bilingual render (contrarian framing ships) -------------------------
def _render_chips(leverage):
    from jinja2 import Environment, FileSystemLoader
    src = (TEMPLATES / "vector.html.j2").read_text()
    macros = src[: src.index("<!DOCTYPE")]                       # includes the t() macro
    start = src.index("{% if leverage.okx_ls_ratio is not none %}")
    end = src.index("      {% if leverage.cme_basis is not none %}")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    return env.from_string(macros + src[start:end]).render(leverage=leverage)


_BASE = {"okx_ls_ratio": 1.85, "okx_ls_pctile": 92, "okx_ls_z": 2.1,
         "okx_taker_buy": 0.54, "okx_taker_pctile": 70, "okx_ls_lean": "crowded_long"}


def test_bilingual_render():
    html = _render_chips(_BASE)
    assert "OKX retail long/short (accounts)" in html and "OKX 散户多空比（账户数）" in html
    assert "OKX taker buy/sell flow" in html and "OKX 主动买卖盘占比" in html
    # contrarian framing for a crowded-long read, both languages
    assert "crowded longs (contrarian caution, not a buy)" in html
    assert "多头拥挤（反向警示，非买入信号）" in html
    # neutral/contrarian: crowded-long must never be painted as a positive/buy signal
    assert 'class="pos"' not in html


def test_render_crowded_short_branch():
    html = _render_chips({**_BASE, "okx_ls_z": -2.0, "okx_ls_lean": "crowded_short"})
    assert "crowded shorts (capitulation context)" in html and "空头拥挤（投降式背景）" in html
