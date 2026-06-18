"""Tests for the display-only policy leaves: fed_stance + policy_rotation_check."""
from __future__ import annotations

import pandas as pd

from engine import fed_stance as fs
from engine import policy_rotation_check as prc


# ---------------- fed_stance ----------------
def test_fed_stance_hawkish_from_market_and_guidance():
    out = fs.snapshot({"fed_path": {"implied_cuts_12m": -0.6, "gap": {"gap_bp": 38, "lean_en": "market more hawkish"}},
                       "catalyst_tone": {"guidance_direction": "tightening"}})
    assert out["stance"] == "hawkish" and out["color"] == "down"
    assert out["is_context_only"] is True and any("hike" in d for d in out["drivers_en"])


def test_fed_stance_dovish():
    out = fs.snapshot({"fed_path": {"implied_cuts_12m": 2.0, "gap": {}}, "catalyst_tone": {"guidance_direction": "easing"}})
    assert out["stance"] == "dovish" and out["color"] == "up"


def test_fed_stance_neutral():
    out = fs.snapshot({"fed_path": {"implied_cuts_12m": 0.5, "gap": {}}, "catalyst_tone": {"guidance_direction": "on_hold"}})
    assert out["stance"] == "neutral"


def test_fed_stance_unknown_when_empty():
    out = fs.snapshot({})
    assert out["stance"] == "unknown" and out["is_context_only"] is True


# ---------------- policy_rotation_check ----------------
def _series(vals):
    return pd.Series(vals, index=pd.date_range("2026-01-01", periods=len(vals)))


def test_rel_relative_to_spy():
    closes = {"XX": _series([100, 100, 103]), "SPY": _series([100, 100, 100])}
    rel = prc._rel("XX", None, 2, lambda t, r: closes.get(t))
    assert rel == 0.03                      # +3% vs a flat SPY
    assert prc._rel("MISSING", None, 2, lambda t, r: closes.get(t)) is None


def test_check_verdicts():
    closes = {
        "XX": _series([100, 100, 110]), "YY": _series([100, 100, 108]),   # strong (theme A working)
        "ZZ": _series([100, 100, 95]),                                     # weak  (theme B lagging)
        "SPY": _series([100, 100, 100]),
    }
    intel = {"rotation": {"targeted": [
        {"theme_en": "A", "proxies": ["XX", "YY"]},
        {"theme_en": "B", "proxies": ["ZZ"]},
        {"theme_en": "C", "proxies": ["NOPE"]},      # no data -> na
    ]}}
    out = prc.check(intel, root=None, window=2, loader=lambda t, r: closes.get(t))
    assert out["themes"]["A"]["verdict"] == "working" and out["themes"]["A"]["n"] == 2
    assert out["themes"]["B"]["verdict"] == "lagging"
    assert out["themes"]["C"]["verdict"] == "na" and out["themes"]["C"]["n"] == 0


def test_check_gld_alias_resolves():
    closes = {"GC_F": _series([100, 100, 105]), "SPY": _series([100, 100, 100])}
    intel = {"rotation": {"targeted": [{"theme_en": "Gold", "proxies": ["GLD"]}]}}
    out = prc.check(intel, root=None, window=2, loader=lambda t, r: closes.get(t))
    assert out["themes"]["Gold"]["verdict"] == "working"   # GLD -> GC_F resolved
