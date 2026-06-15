"""Tests for engine/stock_fundamentals.py (the single-stock panel assembler).

pytest is not installed in the venv — run as a plain script: python tests/test_stock_fundamentals.py
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_fundamentals as SF  # noqa: E402


def test_num_and_clean():
    assert SF._num(float("nan")) is None
    assert SF._num(float("inf")) is None
    assert SF._num("x") is None
    assert SF._num(3) == 3.0
    cleaned = SF._clean({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2}})
    assert cleaned == {"a": None, "b": [1.0, None], "c": {"d": 2}}
    # the cleaned structure must be valid JSON with no NaN/Infinity tokens
    s = json.dumps(cleaned)
    assert "NaN" not in s and "Infinity" not in s


def test_archetype_unprofitable_veto_fires_first():
    # a strong-quality name that is unprofitable must NOT read "quality"
    fac = {"value": 0.0, "quality": 2.0, "profitability": 2.0,
           "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    a = SF._archetype(fac, ni=-50.0, net_margin=-10.0, nm_top_thr=20.0)
    assert a["key"] == "speculative_unprofitable"


def test_archetype_cascade():
    base = {"value": 0.0, "quality": 0.0, "profitability": 0.0,
            "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    # high beta + high vol (negative low_* z) → high_beta_momentum
    hb = dict(base, low_beta=-0.8, low_vol=-0.6)
    assert SF._archetype(hb, 10, 5, 30)["key"] == "high_beta_momentum"
    # high payout + low vol + low beta → dividend_defensive
    dd = dict(base, payout=0.8, low_vol=0.6, low_beta=0.5)
    assert SF._archetype(dd, 10, 5, 30)["key"] == "dividend_defensive"
    # high quality + profitable + not expensive → quality_compounder
    qc = dict(base, quality=0.8, profitability=0.5)
    assert SF._archetype(qc, 10, 5, 30)["key"] == "quality_compounder"
    # quality gate can pass via top-tercile net margin even when profitability z is missing
    qc2 = dict(base, quality=0.8, profitability=None)
    assert SF._archetype(qc2, 10, net_margin=40.0, nm_top_thr=30.0)["key"] == "quality_compounder"
    # cheap on value, quality not high → deep_value
    dv = dict(base, value=1.0, quality=0.0)
    assert SF._archetype(dv, 10, 5, 30)["key"] == "deep_value"
    # nothing dominates → mixed
    assert SF._archetype(base, 10, 5, 30)["key"] == "mixed"
    # missing factor row → None
    assert SF._archetype(None, 10, 5, 30) is None


def test_archetype_shape():
    fac = {"value": 1.0, "quality": 0.0, "profitability": 0.0,
           "payout": 0.0, "low_vol": 0.0, "low_beta": 0.0}
    a = SF._archetype(fac, 10, 5, 30)
    for k in ("key", "label", "label_zh", "confidence", "conf_word", "why", "why_zh"):
        assert k in a
    assert a["key"] in SF.ARCHETYPES
    assert 0.0 <= a["confidence"] <= 1.0
    assert a["conf_word"] in ("high", "moderate", "low")


def test_earnings_includes_sue_z():
    # a full earnings row + the validated SUE z surfaces both, next to each other
    row = {"next_date": "2026-07-30", "next_time": "time-pre-market", "eps_forecast": 1.86,
           "surprises": [{"qtr": "Mar 2026", "eps": 2.01, "consensus": 1.92, "surprise_pct": 4.7}]}
    e = SF._earnings(row, 1.466)
    assert e["sue_z"] == 1.47                       # rounded to 2dp
    assert e["next_date"] == "2026-07-30"
    assert e["next_time"] == "pre-market"
    assert e["summary"]["beats"] == 1


def test_earnings_sue_only_block():
    # SUE is itself an earnings read: a name with NO Nasdaq next-date/surprises but a
    # SUE z still returns an earnings block (the chip surfaces alone).
    e = SF._earnings(None, 1.0)
    assert e is not None and e["sue_z"] == 1.0
    assert e["next_date"] is None and e["surprises"] == [] and e["summary"] is None
    assert SF._earnings({}, 2.4)["sue_z"] == 2.4


def test_earnings_none_when_nothing_to_show():
    assert SF._earnings(None, None) is None
    assert SF._earnings({}, None) is None
    # a NaN SUE with no other earnings data is nothing to show
    assert SF._earnings(None, float("nan")) is None


def test_earnings_sue_nan_coerced_json_safe():
    # a NaN SUE alongside a real next-date keeps the block but nulls the z (JSON-safe)
    e = SF._earnings({"next_date": "2026-07-30"}, float("nan"))
    assert e is not None and e["sue_z"] is None
    assert "NaN" not in json.dumps(SF._clean(e))


def test_mktcap_tier():
    assert SF._mktcap_tier(None) is None
    assert SF._mktcap_tier(500)["key"] == "mega"
    assert SF._mktcap_tier(50)["key"] == "large"
    assert SF._mktcap_tier(5)["key"] == "mid"
    assert SF._mktcap_tier(1)["key"] == "small"


def test_panels_smoke():
    """If the EDGAR cache exists, panels() must return JSON-safe blocks for a
    decent slice of the universe. Skips cleanly when data isn't present."""
    p = SF.panels()
    if not p:
        print("  (no edgar fundamentals cache — panels() smoke skipped)")
        return
    assert len(p) > 100
    # whole structure must serialize as valid JSON (no NaN/Infinity tokens)
    s = json.dumps(p, default=str)
    assert "NaN" not in s and "Infinity" not in s
    sample = next(iter(p.values()))
    # blocks present are from the known set; archetype key is valid when present
    assert set(sample).issubset({"profile", "valuation", "financials",
                                 "factors", "positioning", "analyst", "earnings"})
    for rec in list(p.values())[:200]:
        arch = (rec.get("profile") or {}).get("archetype")
        if arch:
            assert arch["key"] in SF.ARCHETYPES
        fac = rec.get("factors")
        if fac and fac.get("fundamental_score") is not None:
            assert -100 <= fac["fundamental_score"] <= 100


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(_run())
