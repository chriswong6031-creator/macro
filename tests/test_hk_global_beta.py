"""Per-stock global-risk beta engine tests (engine/hk_global_beta.py).

Synthetic-universe checks (no disk): the engine recovers each name's beta to the
risk factor, ranks high-beta names as amplifiers / low-beta as cushions, and
conditions the tilt correctly on the live risk_state. The HK per-name read is a
RISK EXPOSURE, not a selection alpha — see research/CHINA_HK_STOCK_SIGNALS.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import hk_global_beta as gb  # noqa: E402


def _synthetic(seed: int = 0):
    """14 names with KNOWN betas (0.0..1.3) to a global-risk factor over 400 bdays.
    closes = cumprod(beta*factor + small idio); factor passed as a returns series."""
    rng = np.random.default_rng(seed)
    n = 400
    dates = pd.bdate_range("2022-01-03", periods=n)
    f = rng.normal(0.0003, 0.011, n)                       # global-risk factor returns
    true = {f"T{i:02d}": b for i, b in enumerate(np.linspace(0.0, 1.3, 14))}
    closes = pd.DataFrame({t: pd.Series(100 * np.cumprod(1 + (b * f + rng.normal(0, 0.005, n))), index=dates)
                           for t, b in true.items()})
    factor = pd.Series(f, index=dates)
    names = {t: t for t in true}
    sectors = {t: "Tech" for t in true}
    return closes, factor, names, sectors, true


def test_tilt_conditioning():
    """The regime tilt is the actionable bit — verify every role × state combo."""
    assert gb._tilt("amplifier", "Risk-on") == "favored"
    assert gb._tilt("amplifier", "Risk-off") == "exposed"
    assert gb._tilt("cushion", "Risk-off") == "favored"
    assert gb._tilt("cushion", "Risk-on") == "lag"
    assert gb._tilt("neutral", "Risk-on") == "neutral"
    assert gb._tilt("amplifier", "Neutral") == "neutral"     # no tilt without a regime


def test_structure_and_recovery():
    closes, factor, names, sectors, true = _synthetic()
    out = gb.compute_global_betas(closes, factor, "Neutral", names, sectors,
                                  win=120, shrink=1.0, min_names=8)
    assert out is not None
    assert set(out) >= {"as_of", "n", "risk_state", "amplifiers", "cushions", "per_ticker"}
    assert out["n"] == 14 and out["risk_state"] == "Neutral"

    # estimated beta ranks monotonically with the TRUE beta (Spearman ~1)
    est = pd.Series({t: out["per_ticker"][t]["beta"] for t in out["per_ticker"]})
    tru = pd.Series(true)[est.index]
    assert est.corr(tru, method="spearman") > 0.9

    # the top amplifier has a materially higher TRUE beta than the top cushion
    assert true[out["amplifiers"][0]["ticker"]] > true[out["cushions"][0]["ticker"]] + 0.5
    assert out["amplifiers"][0]["role"] == "amplifier"
    assert out["cushions"][0]["role"] == "cushion"


def test_risk_state_flips_tilt():
    closes, factor, names, sectors, _ = _synthetic()
    on = gb.compute_global_betas(closes, factor, "Risk-on", names, sectors, win=120, min_names=8)
    off = gb.compute_global_betas(closes, factor, "Risk-off", names, sectors, win=120, min_names=8)
    assert on["amplifiers"][0]["tilt"] == "favored"          # amplifiers lead a risk-on tape
    assert off["amplifiers"][0]["tilt"] == "exposed"         # ...and take the drawdown in risk-off
    assert off["cushions"][0]["tilt"] == "favored"           # defensives favored in risk-off


def test_guards():
    closes, factor, names, sectors, _ = _synthetic()
    assert gb.compute_global_betas(pd.DataFrame(), factor, "Neutral") is None        # empty
    assert gb.compute_global_betas(closes.iloc[:, :3], factor, "Neutral", names, sectors,
                                   win=120, min_names=8) is None                      # too few names
