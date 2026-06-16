"""Tests for the China Income Vector allocation engine (engine/china_allocation.py).

Validates the strategy invariants on the real on-disk China data: variant weights are
proper, the diversified blend genuinely beats CSI 300 buy & hold on Sharpe AND drawdown,
the variants are risk-ordered, the blend has no look-ahead, the momentum overlay does NOT
improve (the honest finding), and the leaf stays DISPLAY-ONLY (never imports the regime).

Run as a script:  python -m tests.test_china_allocation   (or via pytest)
"""
from __future__ import annotations

import pandas as pd

from engine import china_allocation as ca

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")
    assert cond, f"{name} {detail}"


def test_variant_weights_sum_to_one():
    for v, spec in ca.VARIANTS.items():
        tot = sum(spec["weights"].values())
        check(f"{v} weights sum to 1.0", abs(tot - 1.0) < 1e-9, f"sum={tot}")


def test_blend_no_lookahead():
    """blend_returns is a same-bar weighted mean (constant-mix) minus a flat drag — no
    shifting, no future data leaks into a bar."""
    idx = pd.date_range("2020-01-01", periods=50, freq="B")
    rets = pd.DataFrame({"income": 0.01, "gold": -0.005, "bond": 0.002}, index=idx)
    w = {"income": 0.5, "gold": 0.3, "bond": 0.2}
    out = ca.blend_returns(w, rets, cost_pp=0.0)
    manual = 0.5 * 0.01 + 0.3 * -0.005 + 0.2 * 0.002
    check("blend == same-bar weighted mean (no look-ahead)",
          float((out - manual).abs().max()) < 1e-12, f"max diff {(out-manual).abs().max()}")


def test_backtest_beats_csi300_on_sharpe_and_drawdown():
    bt = ca.backtest("balanced")
    if bt.get("error"):
        print("  SKIP  no china data on disk")
        return
    bench = bt.get("bench_csi300", {})
    check("balanced Sharpe > CSI300 buy&hold Sharpe",
          bt["sharpe"] > bench.get("sharpe", 99), f"{bt['sharpe']} vs {bench.get('sharpe')}")
    check("balanced drawdown shallower than CSI300 (less negative)",
          bt["maxdd"] > bench.get("maxdd", -99), f"{bt['maxdd']} vs {bench.get('maxdd')}")
    check("balanced bootstrap Sharpe CI lower bound > 0",
          bt.get("bootstrap", {}).get("sharpe_ci", [-1])[0] > 0, str(bt.get("bootstrap")))


def test_variants_risk_ordered():
    bts = {v: ca.backtest(v) for v in ("conservative", "balanced", "growth")}
    if any(b.get("error") for b in bts.values()):
        print("  SKIP  no china data on disk")
        return
    # shallower (less negative) drawdown for the more defensive variant
    check("conservative drawdown shallower than growth",
          bts["conservative"]["maxdd"] > bts["growth"]["maxdd"],
          f"{bts['conservative']['maxdd']} vs {bts['growth']['maxdd']}")


def test_momentum_overlay_does_not_improve():
    ab = ca.momentum_overlay_ab("balanced")
    if not ab:
        print("  SKIP  no china data on disk")
        return
    # The honest finding: a trend overlay must NOT beat the static blend on Sharpe in China.
    check("momentum overlay does not improve Sharpe (static wins/ties)",
          ab["overlay"]["sharpe"] <= ab["static"]["sharpe"] + 0.05 and ab["helps"] is False,
          f"static {ab['static']['sharpe']} vs overlay {ab['overlay']['sharpe']}")


def test_card_and_snapshot_shape():
    card = ca.latest_card("balanced")
    if not card.get("present"):
        print("  SKIP  no china data on disk")
        return
    check("card growth_w + defensive_w == 100", card["growth_w"] + card["defensive_w"] == 100,
          f"{card['growth_w']}+{card['defensive_w']}")
    snap = ca.snapshot()
    for k in ("as_of", "variants", "curves", "momentum_ab", "current", "card", "alt_cores"):
        check(f"snapshot has '{k}'", k in snap)
    check("snapshot is display_only", snap.get("display_only") is True)
    import json
    check("snapshot is JSON-serializable", bool(json.dumps(snap, default=str)))


def test_display_only_invariant():
    """The allocation leaf must never import the scored regime stack (it is descriptive,
    never fed back into china_axes / china_regime / china_playbook). Checks real import
    statements, not docstring prose."""
    import inspect
    import_lines = [ln for ln in inspect.getsource(ca).splitlines()
                    if ln.strip().startswith(("import ", "from "))]
    blob = "\n".join(import_lines)
    for forbidden in ("china_axes", "china_regime", "china_playbook"):
        check(f"china_allocation does not import {forbidden}", forbidden not in blob)


def main() -> int:
    for fn in (test_variant_weights_sum_to_one, test_blend_no_lookahead,
               test_backtest_beats_csi300_on_sharpe_and_drawdown, test_variants_risk_ordered,
               test_momentum_overlay_does_not_improve, test_card_and_snapshot_shape,
               test_display_only_invariant):
        print(f"\n{fn.__name__}")
        try:
            fn()
        except AssertionError as e:
            print(f"  (assertion) {e}")
    print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
