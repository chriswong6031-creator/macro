"""HK southbound-vs-price DIVERGENCE chip — engine leaf + render + display-only guard.

The chip is DISPLAY-ONLY positioning-vs-price context (confirms / diverges / mixed /
insufficient), never a buy/sell and never scored. These tests pin:
  1. the deterministic divergence truth table,
  2. the chip dict shape (JSON-serializable, exact keys),
  3. the missing/short-data guards,
  4. the load-bearing DISPLAY-ONLY invariant (not wired into hk_axes / hk_regime),
  5. the bilingual template render of the actual hk.html.j2 chip block.

All compute tests stub `china_internals.store.read` with deterministic frames — no
network, no real parquet store.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from jinja2 import Environment

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import china_internals as ci  # noqa: E402

WINDOW = 63
N = 400


def _net(flow: str) -> pd.Series:
    """Synthetic southbound-net daily series whose window-cum z lands in a band."""
    idx = pd.date_range("2015-01-01", periods=N, freq="D")
    if flow == "flat":
        vals = [50.0] * N                                   # constant cum -> z == 0
    elif flow == "up":
        vals = [10.0] * (N - WINDOW) + [200.0] * WINDOW     # last quarter floods IN
    elif flow == "dn":
        vals = [200.0] * (N - WINDOW) + [10.0] * WINDOW     # last quarter dries up
    else:
        raise ValueError(flow)
    return pd.Series(vals, index=idx, name="net")


def _close(px: str) -> pd.Series:
    idx = pd.date_range("2015-01-01", periods=N, freq="D")
    if px == "flat":
        vals = [100.0] * N                                  # 0% over the window
    elif px == "up":
        vals = [100.0 * (1.001 ** i) for i in range(N)]     # ~+6.4% over 63d
    elif px == "dn":
        vals = [100.0 * (0.999 ** i) for i in range(N)]     # ~-6.0% over 63d
    else:
        raise ValueError(px)
    return pd.Series(vals, index=idx, name="close")


def _patch_store(monkeypatch, *, net=None, close=None, southbound=True, close_col=True):
    sb_df = None
    if southbound and net is not None:
        sb_df = net.to_frame("net")
    px_df = None
    if close is not None:
        px_df = close.to_frame("close" if close_col else "px")

    def fake_read(group, name):
        if (group, name) == ("china_connect", "southbound"):
            return sb_df
        if (group, name) == ("hk", "^HSI"):
            return px_df
        return None

    monkeypatch.setattr(ci.store, "read", fake_read)


# --------------------------------------------------------------------------- #
# 1. divergence truth table
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("flow,px,expected", [
    ("up", "up", "confirms"),    # both up
    ("dn", "dn", "confirms"),    # both down
    ("up", "dn", "diverges"),    # flow in, price down
    ("dn", "up", "diverges"),    # flow out, price up
    ("flat", "up", "mixed"),     # flow in dead-zone
    ("up", "flat", "mixed"),     # price in dead-zone
    ("flat", "flat", "mixed"),   # both dead-zone
])
def test_divergence_truth_table(monkeypatch, flow, px, expected):
    _patch_store(monkeypatch, net=_net(flow), close=_close(px))
    out = ci.southbound_price_divergence()
    assert out is not None and out["state"] == expected


def test_band_directions(monkeypatch):
    """The two numbers carry the direction: flow_z sign and price-return sign."""
    _patch_store(monkeypatch, net=_net("up"), close=_close("dn"))
    out = ci.southbound_price_divergence()
    assert out["state"] == "diverges"
    assert out["flow_z"] > 0.5            # flows accelerating IN
    assert out["px_ret_pct"] < -2.0       # price falling


# --------------------------------------------------------------------------- #
# 2. chip shape
# --------------------------------------------------------------------------- #
def test_chip_shape_and_json(monkeypatch):
    _patch_store(monkeypatch, net=_net("up"), close=_close("up"))
    out = ci.southbound_price_divergence()
    assert set(out) == {"state", "flow_z", "px_ret_pct", "window_d"}
    assert out["window_d"] == 63
    assert isinstance(out["state"], str)
    assert isinstance(out["flow_z"], float) and isinstance(out["px_ret_pct"], float)
    assert isinstance(out["window_d"], int)
    json.dumps(out)                       # must be JSON-serializable


def test_custom_window(monkeypatch):
    _patch_store(monkeypatch, net=_net("up"), close=_close("up"))
    out = ci.southbound_price_divergence(window=40)
    assert out["window_d"] == 40


# --------------------------------------------------------------------------- #
# 3. guards
# --------------------------------------------------------------------------- #
def test_insufficient_short_flow(monkeypatch):
    short = _net("up").iloc[:50]          # < window + 20
    _patch_store(monkeypatch, net=short, close=_close("up"))
    out = ci.southbound_price_divergence()
    assert out == {"state": "insufficient", "n_flow": 50, "n_px": N}


def test_none_when_close_column_missing(monkeypatch):
    _patch_store(monkeypatch, net=_net("up"), close=_close("up"), close_col=False)
    assert ci.southbound_price_divergence() is None


def test_none_when_southbound_missing(monkeypatch):
    _patch_store(monkeypatch, net=None, close=_close("up"), southbound=False)
    assert ci.southbound_price_divergence() is None


# --------------------------------------------------------------------------- #
# 4. DISPLAY-ONLY invariant (load-bearing): never wired into HK scoring
# --------------------------------------------------------------------------- #
def test_not_referenced_by_scoring_source():
    for mod in ("hk_axes.py", "hk_regime.py"):
        src = (ROOT / "engine" / mod).read_text()
        assert "southbound_price_divergence" not in src, \
            f"divergence chip must NOT be referenced in engine/{mod} (display-only)"


def test_scoring_modules_expose_no_divergence_symbol():
    from engine import hk_axes, hk_regime
    assert not hasattr(hk_axes, "southbound_price_divergence")
    assert not hasattr(hk_regime, "southbound_price_divergence")


# --------------------------------------------------------------------------- #
# 5. bilingual render of the REAL template chip block
# --------------------------------------------------------------------------- #
def _render_chip(divergence: dict) -> str:
    """Render the actual Flow-vs-price card extracted from templates/hk.html.j2
    (with its in-template t()/help() macros) — so the test tracks real markup drift.

    The standalone SOUTHBOUND-vs-PRICE chip was folded into the combined
    SOUTHBOUND & A/H panel by the HK dashboard UX overhaul (#2017); the
    divergence read now renders as the panel's "Flow vs price" card.
    """
    src = (ROOT / "templates" / "hk.html.j2").read_text()
    macros = src[: src.index("<!DOCTYPE")]
    start = src.index("<!-- ===================== SOUTHBOUND & A/H")
    # stop at the combined panel's closing region (it lives inside the mode!=macro
    # block) so the extracted fragment is balanced Jinja
    end = src.index("{% endif %}{# /mode != macro", start)
    chip = src[start:end]
    env = Environment(autoescape=False)
    tmpl = env.from_string(macros + chip)
    # Only sb_divergence supplied: the sibling southbound-flow and A/H cards
    # must gate themselves off without their data.
    return tmpl.render(internals={"sb_divergence": divergence}, ah=None)


@pytest.mark.parametrize("state,en_word,zh_word", [
    ("confirms", "Confirms", "同向"),
    ("diverges", "Diverges", "背离"),
    ("mixed", "Mixed", "中性"),
])
def test_bilingual_render_states(state, en_word, zh_word):
    html = _render_chip({"state": state, "flow_z": 1.2, "px_ret_pct": 3.4, "window_d": 63})
    assert "{{" not in html and "{%" not in html         # fully rendered
    assert "Flow vs price" in html and "资金 vs 价格" in html
    assert en_word in html and zh_word in html


def test_bilingual_render_insufficient():
    """insufficient → the Flow-vs-price card must not render at all.

    #2017 replaced the old in-chip honesty note ("Not enough history…") with a
    render guard (state != 'insufficient'): the honest degrade is now the card's
    absence, so no state words or stats may leak through.
    """
    html = _render_chip({"state": "insufficient", "n_flow": 50, "n_px": 400})
    assert "Flow vs price" not in html
    assert "资金 vs 价格" not in html
    # the stat-row (state/flow/price numbers) must NOT render for insufficient
    assert "σ" not in html
