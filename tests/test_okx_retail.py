"""OKX retail positioning chips (P1a) — collector parse, chip shape, the
DISPLAY-ONLY invariant, and bilingual render. Pure compute + a snippet render;
no network.

Run: .venv/bin/python -m tests.test_okx_retail
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.okx import OkxAdapter  # noqa: E402
from engine import btc_signals  # noqa: E402
from scripts.build_vector import _okx_ls_lean, _r  # noqa: E402


class _Fake:
    """Minimal stand-in for a requests.Response with a .json()."""
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _adapter(payload):
    a = OkxAdapter.__new__(OkxAdapter)            # skip __init__/config load
    a.cfg = {"ls_ratio_url": "x", "taker_url": "x", "retries": 1}
    a.http_get = lambda *args, **kw: _Fake(payload)
    return a


def test_okx_ls_ratio_parse():
    """rubik long-short-account-ratio rows = [ts_ms, ratio]."""
    stub = {"data": [["1718000000000", "1.85"], ["1717913600000", "1.40"],
                     ["1717827200000", "2.02"]]}
    df = _adapter(stub)._ls_account_ratio()
    assert list(df.columns) == ["ls_ratio"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing and df.index.is_unique
    assert pd.api.types.is_numeric_dtype(df["ls_ratio"])
    assert (df.index.normalize() == df.index).all()          # date-normalized
    assert abs(df["ls_ratio"].iloc[-1] - 1.85) < 1e-9        # newest ts -> last row


def test_okx_taker_volume_parse_and_buysell_order():
    """rows are [ts, sellVol, buyVol]; buy share = buy/(buy+sell). A column flip
    would give 0.25 not 0.75. The sell=buy=0 row must be dropped by the np.nan
    divide-by-zero guard."""
    stub = {"data": [["1718000000000", "100", "300"],    # buy share = 300/400 = 0.75
                     ["1717913600000", "0", "0"]]}        # 0/0 -> nan -> dropped
    df = _adapter(stub)._taker_volume()
    assert list(df.columns) == ["taker_buy_ratio"]
    assert len(df) == 1                                   # the 0/0 row was dropped
    assert abs(df["taker_buy_ratio"].iloc[0] - 0.75) < 1e-9   # NOT 0.25 (buy/sell order)
    assert df["taker_buy_ratio"].between(0, 1).all()


def _leverage_inputs(ls_last: float = 2.5) -> dict:
    """Synthetic inputs: a price frame + a long/short series whose last value spikes
    so the z-score clears the crowded_long band (+ a flat taker series). No OI /
    funding -> those leverage branches no-op; the okx chips are what we exercise."""
    idx = pd.date_range("2025-01-01", periods=140, freq="D")
    close = pd.Series(np.linspace(40000, 60000, 140), index=idx)
    base = 1.0 + 0.04 * np.sin(np.arange(140))           # nonzero rolling std
    ls = pd.Series(base, index=idx)
    ls.iloc[-1] = ls_last                                 # spike -> high z
    taker = pd.Series(0.50 + 0.01 * np.cos(np.arange(140)), index=idx)
    return {"price": pd.DataFrame({"close": close}, index=idx),
            "okx_ls_ratio": ls, "okx_taker_buy": taker}


def test_chip_shape_and_lean_enum():
    out = btc_signals.leverage(_leverage_inputs(ls_last=2.5), {})   # cfg.get defaults
    for c in ("okx_ls_ratio", "okx_ls_ratio_pctile", "okx_ls_ratio_z",
              "okx_taker_buy", "okx_taker_buy_pctile"):
        assert c in out.columns, c
    last = out.iloc[-1]
    vm = {"okx_ls_ratio": _r(last.get("okx_ls_ratio"), 2),
          "okx_ls_pctile": _r(last.get("okx_ls_ratio_pctile"), 0),
          "okx_ls_z": _r(last.get("okx_ls_ratio_z"), 1),
          "okx_taker_buy": _r(last.get("okx_taker_buy"), 3),
          "okx_taker_pctile": _r(last.get("okx_taker_buy_pctile"), 0),
          "okx_ls_lean": _okx_ls_lean(last.get("okx_ls_ratio_z"))}
    assert isinstance(vm["okx_ls_ratio"], float) and isinstance(vm["okx_taker_buy"], float)
    assert vm["okx_ls_lean"] in {"crowded_long", "crowded_short", "balanced"}
    assert last["okx_ls_ratio_z"] > 1.5 and vm["okx_ls_lean"] == "crowded_long"
    assert 0.0 <= vm["okx_taker_buy"] <= 1.0                # taker buy share is a fraction
    # lean helper contract directly
    assert _okx_ls_lean(-2.0) == "crowded_short"
    assert _okx_ls_lean(0.3) == "balanced"
    assert _okx_ls_lean(None) == "balanced"
    assert _okx_ls_lean(float("nan")) == "balanced"


def test_display_only_invariant():
    """The load-bearing guard: the new chip symbols must NEVER enter any scoring or
    classification path — not axes, not regime.classify, not leverage_stress, not
    allocation, not the composite_state/composite_context classifiers."""
    syms = ("okx_ls_ratio", "okx_taker_buy", "okx_ls_ratio_z")
    for f in ("engine/axes.py", "engine/regime.py"):
        txt = (ROOT / f).read_text()
        for s in syms:
            assert s not in txt, f"{s} leaked into {f}"
    # leverage_stress = weighted mean of `parts`; assert no part (and not the
    # leverage_stress assignment itself) references the chips. This is robust to
    # WHERE the display columns are added in the function body.
    lev = inspect.getsource(btc_signals.leverage)
    append_lines = [ln for ln in lev.splitlines() if "parts.append" in ln]
    assert append_lines and not any("okx" in ln for ln in append_lines)
    stress_lines = [ln for ln in lev.splitlines() if "leverage_stress" in ln]
    assert stress_lines and not any("okx" in ln for ln in stress_lines)
    # allocation + compute_all wiring + the composite classifiers must not read them
    for fn in (btc_signals.allocation, btc_signals.compute_all,
               btc_signals.composite_state, btc_signals.composite_context):
        src = inspect.getsource(fn)
        assert "okx_ls" not in src and "okx_taker" not in src, fn.__name__


def test_bilingual_render():
    """Render the actual shipped chip markup (sliced from the template) through the
    bilingual t() macro and assert BOTH languages + the contrarian framing ship."""
    from jinja2 import Environment
    tmpl = (ROOT / "templates/vector.html.j2").read_text()
    start = tmpl.index("{% if leverage.okx_ls_ratio is not none %}")
    end = tmpl.index("{% if leverage.cme_basis is not none %}", start)
    macro = ("{% macro t(en, zh='') %}<span class=\"l-en\">{{ en }}</span>"
             "<span class=\"l-zh\">{{ zh if zh else en }}</span>{% endmacro %}")
    snippet = macro + "\n" + tmpl[start:end]
    html = Environment(autoescape=True).from_string(snippet).render(leverage={
        "okx_ls_ratio": 2.5, "okx_ls_pctile": 96, "okx_ls_z": 2.1,
        "okx_ls_lean": "crowded_long", "okx_taker_buy": 0.55, "okx_taker_pctile": 80})
    assert "OKX retail long/short" in html and "OKX 散户多空比" in html        # EN + ZH
    assert "OKX taker buy/sell flow" in html and "OKX 主动买卖盘占比" in html   # EN + ZH
    assert "crowded longs (contrarian caution, not a buy)" in html            # contrarian EN
    assert "多头拥挤（反向警示，非买入信号）" in html                              # contrarian ZH
    # the display-only honesty caveat ships bilingual in the template body
    # (prose gets copy-edited — pin the load-bearing phrases, case-insensitive EN)
    assert "display-only positioning context" in tmpl.lower()
    assert "不参与仓位或评分" in tmpl


if __name__ == "__main__":
    for fn in [test_okx_ls_ratio_parse, test_okx_taker_volume_parse_and_buysell_order,
               test_chip_shape_and_lean_enum, test_display_only_invariant,
               test_bilingual_render]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all OKX retail chip tests passed")
