"""Tests for the DISPLAY-ONLY HK southbound-vs-price divergence chip (P1b):
engine.china_internals.southbound_price_divergence truth table + guards, the
display-only invariant, and the bilingual hk.html.j2 panel. Synthetic store
(no network). See research/HK_SOUTHBOUND_DIVERGENCE_SPEC.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_internals as ci  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def _net(direction: str, n: int = 400) -> pd.Series:
    """Southbound net daily series. Constant baseline (z=0 / dead-zone) with the
    final 63d ramped strongly +/- to force flow_z up/down."""
    idx = pd.bdate_range("2022-01-01", periods=n)
    net = np.full(n, 1.0)
    if direction == "up":
        net[-63:] = 50.0
    elif direction == "down":
        net[-63:] = -50.0
    return pd.Series(net, index=idx)


def _close(direction: str, n: int = 400) -> pd.Series:
    idx = pd.bdate_range("2022-01-01", periods=n)
    if direction == "up":
        c = np.linspace(100, 160, n)        # 63d return well above +2%
    elif direction == "down":
        c = np.linspace(160, 100, n)        # well below -2%
    else:
        c = np.full(n, 100.0)               # flat -> dead-zone
    return pd.Series(c, index=idx)


def _patch(monkeypatch, net_dir, px_dir, *, net_len=400, px_cols=("close",), with_sb=True):
    sb = None
    if with_sb:
        sb = pd.DataFrame({"net": _net(net_dir, net_len), "hold_mktcap": 1000.0})
    pxs = _close(px_dir)
    px = pd.DataFrame({c: pxs for c in px_cols})

    def fake_read(group, name):
        if group == "china_connect" and name == "southbound":
            return sb
        if group == "hk" and name == "^HSI":
            return px
        return None
    monkeypatch.setattr(ci.store, "read", fake_read)


# ---- 1. divergence truth table ----------------------------------------------
@pytest.mark.parametrize("net_dir,px_dir,expected", [
    ("up", "up", "confirms"),
    ("down", "down", "confirms"),
    ("up", "down", "diverges"),
    ("down", "up", "diverges"),
    ("flat", "up", "mixed"),     # flow in dead-zone
    ("up", "flat", "mixed"),     # price in dead-zone
])
def test_divergence_truth_table(monkeypatch, net_dir, px_dir, expected):
    _patch(monkeypatch, net_dir, px_dir)
    d = ci.southbound_price_divergence()
    assert d["state"] == expected, (net_dir, px_dir, d)


# ---- 2. chip shape ----------------------------------------------------------
def test_chip_shape(monkeypatch):
    _patch(monkeypatch, "up", "up")
    d = ci.southbound_price_divergence()
    assert set(d) == {"state", "flow_z", "px_ret_pct", "window_d"}
    assert d["window_d"] == 63
    assert isinstance(d["flow_z"], float) and isinstance(d["px_ret_pct"], float)
    assert isinstance(d["state"], str)


# ---- 3. guards / insufficient ------------------------------------------------
def test_insufficient_short_history(monkeypatch):
    _patch(monkeypatch, "up", "up", net_len=50)        # < window + 20
    d = ci.southbound_price_divergence()
    assert d["state"] == "insufficient" and "n_flow" in d


def test_none_when_missing_close(monkeypatch):
    _patch(monkeypatch, "up", "up", px_cols=("open",))  # no 'close' column
    assert ci.southbound_price_divergence() is None


def test_none_when_missing_southbound(monkeypatch):
    _patch(monkeypatch, "up", "up", with_sb=False)
    assert ci.southbound_price_divergence() is None


# ---- 4. display-only invariant (load-bearing) -------------------------------
def test_display_only_invariant():
    for f in ("engine/hk_axes.py", "engine/hk_regime.py"):
        assert "southbound_price_divergence" not in (ROOT / f).read_text(), f
    import engine.hk_axes as hx
    import engine.hk_regime as hr
    assert not hasattr(hx, "southbound_price_divergence")
    assert not hasattr(hr, "southbound_price_divergence")


# ---- 5. bilingual render -----------------------------------------------------
def _render_panel(sb_divergence):
    from jinja2 import Environment, FileSystemLoader
    src = (TEMPLATES / "hk.html.j2").read_text()
    macros = src[: src.index("<!DOCTYPE")]                          # t() + help() macros
    start = src.index("<!-- ===== SOUTHBOUND vs PRICE DIVERGENCE")
    end = src.index("<!-- ===================== HKMA PEG FUNDING")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    return env.from_string(macros + src[start:end]).render(
        internals={"sb_divergence": sb_divergence})


@pytest.mark.parametrize("state,en,zh", [
    ("confirms", "Confirms", "同向"),
    ("diverges", "Diverges", "背离"),
    ("mixed", "Mixed", "中性"),
])
def test_bilingual_render_states(state, en, zh):
    html = _render_panel({"state": state, "flow_z": 1.2, "px_ret_pct": 3.4, "window_d": 63})
    assert "Southbound vs price" in html and "南向 vs 价格" in html
    assert en in html and zh in html


def test_render_insufficient():
    html = _render_panel({"state": "insufficient", "n_flow": 10, "n_px": 400})
    assert "Not enough history to compare." in html and "历史数据不足" in html
