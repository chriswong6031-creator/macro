"""Gamma-flip repair (2026-08-01) — the hub flip must be a SPOT, not a strike-ladder artifact.

Regression cover for a confirmed live defect. `engine/options_hub._find_gamma_flip` used to
return the zero-crossing of the running partial sum of dealer gamma ACROSS THE STRIKE LADDER,
with gammas frozen at today's spot and no strike window. That answers "at which strike does
cumulative exposure change sign", not "at which SPOT does the regime change" — a different
mathematical object, whose docstring nonetheless claimed to mirror `gex_engine._gamma_flip`.

Measured on live public R2 the morning of the repair:
    SPY  flip 275.00  vs spot 741.69   (62.9% away)
    QQQ  flip 249.80  vs spot 683.55   (63.5% away)
    SPX  flip 8676.93 vs spot 7437.63  (above BOTH walls)
    IWM  flip None
while `gex_state`, which reaches the correct grid method through `gex_model.build_model`,
published SPY 752.2 against spot 750.72.

Full analysis: charting-app
docs/audits/2026-08-01-market-structure-core/gamma-flip-defect-rca.md

Run: .venv/bin/python -m tests.test_gamma_flip_repair
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import gex_engine  # noqa: E402
from engine.levels_engine import _flip_from_rows  # noqa: E402
from engine.options_hub import _find_gamma_flip  # noqa: E402


def _frame(spot, strikes, call_oi, put_oi, T=0.05, iv=0.20):
    """The per-contract frame `compute_gex` holds when it calls the flip finder."""
    rows = []
    for K in strikes:
        for is_call, oi in ((True, call_oi(K)), (False, put_oi(K))):
            rows.append({"K": float(K), "T": T, "iv": iv,
                         "oi_prev": float(oi), "is_call": is_call})
    return pd.DataFrame(rows)


def _balanced(spot=100.0, width=0.20, step=1.0):
    """Calls concentrated above spot, puts below — a normal index-ish book."""
    strikes = np.arange(spot * (1 - width), spot * (1 + width) + step, step)
    return _frame(
        spot, strikes,
        call_oi=lambda K: 500.0 if K >= spot else 100.0,
        put_oi=lambda K: 500.0 if K <= spot else 100.0,
    ), strikes


def test_flip_is_a_spot_near_the_money():
    """The repaired flip lands near spot, not in the deep tail."""
    spot = 100.0
    g, _ = _balanced(spot)
    flip = _find_gamma_flip(g, spot)
    assert flip is not None
    # The old cumulative-across-strikes method drove this far below spot; a real
    # zero-gamma spot for a book centred on 100 sits within a few percent of it.
    assert abs(flip - spot) / spot < 0.10, f"flip {flip} is {abs(flip-spot)/spot:.1%} from spot"


def test_agrees_with_the_engine_that_gex_state_uses():
    """The hub and gex_state must not publish two different flips for one book.

    This is the invariant whose violation was the entire defect: gex_state reaches
    `gex_engine._gamma_flip` through gex_model, the hub reached its own estimator.
    """
    spot = 100.0
    g, _ = _balanced(spot)
    hub_flip = _find_gamma_flip(g, spot)

    cfg = dict(gex_engine.DEFAULTS)
    chain = pd.DataFrame({
        "K": g["K"], "T": g["T"], "iv": g["iv"],
        "oi": g["oi_prev"], "is_call": g["is_call"],
    })
    engine_flip, _dist, _regime = gex_engine._gamma_flip(
        gex_engine._window(chain, spot, cfg), spot, cfg
    )
    assert engine_flip is not None
    assert hub_flip == engine_flip


def test_deep_ladder_does_not_drag_the_flip_into_the_tail():
    """The reproduction case: ladder DEPTH must not move the answer.

    Under the old method, extending the strike range was enough to walk the cumulative
    sum into the deep tail and change the published flip by tens of percent. A spot-grid
    flip is a property of the book, so widening the ladder around the same positioning
    leaves it essentially unchanged.
    """
    spot = 100.0
    shallow, _ = _balanced(spot, width=0.10, step=1.0)
    deep, _ = _balanced(spot, width=0.60, step=1.0)
    f_shallow = _find_gamma_flip(shallow, spot)
    f_deep = _find_gamma_flip(deep, spot)
    assert f_shallow is not None and f_deep is not None
    assert abs(f_shallow - f_deep) / spot < 0.02, (
        f"ladder depth moved the flip: {f_shallow} -> {f_deep}"
    )


def test_put_heavy_book_does_not_return_a_tail_strike():
    """A put-dominated book (the SPY/QQQ configuration) either has a near flip or None.

    It must never answer with a level 60%+ away, which is what the cumulative method did.
    """
    spot = 100.0
    strikes = np.arange(60.0, 141.0, 1.0)
    g = _frame(spot, strikes,
               call_oi=lambda K: 50.0,
               put_oi=lambda K: 2000.0 if K <= spot else 200.0)
    flip = _find_gamma_flip(g, spot)
    assert flip is None or abs(flip - spot) / spot < 0.30


def test_degenerate_inputs_return_none_not_a_number():
    empty = pd.DataFrame(columns=["K", "T", "iv", "oi_prev", "is_call"])
    assert _find_gamma_flip(empty, 100.0) is None
    g, _ = _balanced(100.0)
    assert _find_gamma_flip(g, 0.0) is None
    assert _find_gamma_flip(g, float("nan")) is None
    # zero OI everywhere -> nothing survives the window
    z = _frame(100.0, np.arange(90.0, 111.0), call_oi=lambda K: 0.0, put_oi=lambda K: 0.0)
    assert _find_gamma_flip(z, 100.0) is None


def test_levels_engine_fallback_is_retired():
    """A flip is not reconstructable from by_strike rows — the fallback must not guess."""
    rows = [{"strike": float(k), "gamma_net": float(v)}
            for k, v in zip(range(90, 111), range(-10, 11))]
    assert _flip_from_rows(rows) is None
    assert _flip_from_rows([]) is None


if __name__ == "__main__":
    fns = [
        test_flip_is_a_spot_near_the_money,
        test_agrees_with_the_engine_that_gex_state_uses,
        test_deep_ladder_does_not_drag_the_flip_into_the_tail,
        test_put_heavy_book_does_not_return_a_tail_strike,
        test_degenerate_inputs_return_none_not_a_number,
        test_levels_engine_fallback_is_retired,
    ]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all gamma-flip repair tests passed")
