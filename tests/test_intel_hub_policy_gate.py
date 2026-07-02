"""intel_hub policy-lean gate (W0 fix, QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md §4 brief 1).

A low- or absent-conviction policy facet must contribute NOTHING:
  - dirs["policy"] must be None  (not the raw direction)
  - early_edge flag must not fire
  - policy_aligned / policy_conflict flags must not fire
  - gap_mult must equal the no-policy baseline (gap unchanged)

Audit finding: build_policy_index stores conviction but all downstream consumption
sites read the lean direction without checking it, so a low-conviction thesis steered
dirs["policy"], fired early_edge, and inflated gap_mult.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.intel_hub import (  # noqa: E402
    _dirs,
    _dossier,
    _leading_gap,
    _policy_usable,
    build_policy_index,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _make_policy_facet(conviction: str | None, dir_: int = 1) -> dict:
    return {"dir": dir_, "lean": "overweight", "conviction": conviction,
            "actor": "Fed", "thesis": "test thesis", "horizon_d": 90, "via": "direct"}


def _make_v(with_alt: bool = True) -> dict:
    """Minimal per-ticker facet bundle — enough for _dirs / _leading_gap / _dossier."""
    alt = {"signal_score": 75, "action": "BUY", "extended": False} if with_alt else {}
    radar = {"state": "POSITIVE_DIVERGENCE", "lifecycle": "forming"}
    news = {"sentiment_lean": "pos", "sentiment_score": 0.1, "n_recent": 0,
            "sectors": ["XLK"], "name": "ACME Corp", "baskets": []}
    return {"alt": alt, "radar": radar, "news": news}


def _empty_pidx() -> dict:
    return {"by_ticker": {}, "by_sector": {}, "regime": None}


# --------------------------------------------------------------------------- #
# _policy_usable
# --------------------------------------------------------------------------- #

def test_policy_usable_high_conviction():
    assert _policy_usable({"conviction": "high", "dir": 1}) is True


def test_policy_usable_medium_conviction():
    assert _policy_usable({"conviction": "medium", "dir": 1}) is True


def test_policy_usable_low_conviction_is_false():
    assert _policy_usable({"conviction": "low", "dir": 1}) is False


def test_policy_usable_none_conviction_is_false():
    assert _policy_usable({"conviction": None, "dir": 1}) is False


def test_policy_usable_none_facet_is_false():
    assert _policy_usable(None) is False


# --------------------------------------------------------------------------- #
# _dirs — low-conviction facet must yield dirs["policy"] == None
# --------------------------------------------------------------------------- #

def test_dirs_policy_none_when_low_conviction():
    facet = _make_policy_facet(conviction="low", dir_=1)
    v = _make_v()
    d = _dirs(v, facet)
    assert d["policy"] is None, (
        f"Expected dirs['policy']=None for low-conviction facet, got {d['policy']}"
    )


def test_dirs_policy_none_when_no_conviction():
    facet = _make_policy_facet(conviction=None, dir_=1)
    v = _make_v()
    d = _dirs(v, facet)
    assert d["policy"] is None


def test_dirs_policy_set_when_high_conviction():
    facet = _make_policy_facet(conviction="high", dir_=1)
    v = _make_v()
    d = _dirs(v, facet)
    assert d["policy"] == 1


# --------------------------------------------------------------------------- #
# _leading_gap — low-conviction policy must not contribute to lag_up or lag_present
# --------------------------------------------------------------------------- #

def test_leading_gap_unchanged_by_low_conviction_policy():
    """A low-conviction policy facet must not affect lag_up or lag_present vs no policy.

    We use a minimal bundle with no news/standout so policy is the only candidate
    lagging desk, isolating exactly what the gate should suppress.
    """
    # strip news/standout so only alt + radar (leading) + policy (lagging candidate) remain
    v_minimal = {"alt": {"signal_score": 75, "action": "BUY", "extended": False},
                 "radar": {"state": "POSITIVE_DIVERGENCE", "lifecycle": "forming"}}
    low_facet = _make_policy_facet(conviction="low", dir_=1)
    high_facet = _make_policy_facet(conviction="high", dir_=1)

    dirs_low = _dirs(v_minimal, low_facet)
    dirs_high = _dirs(v_minimal, high_facet)

    gap_low = _leading_gap(v_minimal, dirs_low)
    gap_high = _leading_gap(v_minimal, dirs_high)

    # low-conviction: policy must not appear in lag_up or lag_present at all
    assert gap_low["lag_up"] == 0, (
        f"low-conviction policy should not contribute to lag_up, got {gap_low['lag_up']}"
    )
    assert gap_low["lag_present"] == 0, (
        f"low-conviction policy should not appear in lag_present, got {gap_low['lag_present']}"
    )

    # high-conviction policy dir=1: should add to lag_up (lag_up counts upward lagging desks)
    assert gap_high["lag_up"] == 1, (
        f"high-conviction policy dir=1 should add 1 to lag_up, got {gap_high['lag_up']}"
    )
    # and should count as present
    assert gap_high["lag_present"] == 1


# --------------------------------------------------------------------------- #
# early_edge flag — must NOT fire when conviction is low
# --------------------------------------------------------------------------- #

def test_early_edge_does_not_fire_for_low_conviction_policy():
    """The primary audit finding: low-conviction policy was triggering early_edge."""
    v = _make_v(with_alt=True)
    # low-conviction overweight → should NOT fire early_edge
    low_facet = _make_policy_facet(conviction="low", dir_=1)
    pidx = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
    import datetime, tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    today = datetime.date(2026, 7, 2)
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "early_edge" not in d["flags"], (
        f"early_edge must not fire for low-conviction policy; flags={d['flags']}"
    )


def test_early_edge_fires_for_high_conviction_policy():
    """Sanity: high-conviction policy + stealth conditions should fire early_edge."""
    v = _make_v(with_alt=True)
    # quiet news + alt=1 + radar POSITIVE_DIVERGENCE + usable policy dir=1 → early_edge
    high_facet = _make_policy_facet(conviction="high", dir_=1)
    pidx = {"by_ticker": {"ACME": high_facet}, "by_sector": {}, "regime": None}
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "early_edge" in d["flags"], (
        f"early_edge should fire for high-conviction policy; flags={d['flags']}"
    )


# --------------------------------------------------------------------------- #
# policy_aligned / policy_conflict — must not fire for low-conviction facets
# --------------------------------------------------------------------------- #

def test_policy_aligned_does_not_fire_for_low_conviction():
    v = _make_v(with_alt=True)
    low_facet = _make_policy_facet(conviction="low", dir_=1)
    pidx = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "policy_aligned" not in d["flags"], f"flags={d['flags']}"
    assert "policy_conflict" not in d["flags"], f"flags={d['flags']}"


def test_policy_conflict_does_not_fire_for_low_conviction():
    v = _make_v(with_alt=True)
    # low-conviction bearish policy against a bullish name
    low_facet = _make_policy_facet(conviction="low", dir_=-1)
    pidx = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch
    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        d = _dossier("ACME", v, pidx, vel)
    assert "policy_conflict" not in d["flags"], f"flags={d['flags']}"


# --------------------------------------------------------------------------- #
# gap_mult — low-conviction policy must not inflate gap, so gap_mult equals the
# no-policy value.  gap_mult = 1.0 + 0.15 * max(-2, min(2, gap["gap"])).
# With no policy contribution the gap is determined by leading desks only.
# --------------------------------------------------------------------------- #

def test_gap_mult_equals_no_policy_when_low_conviction():
    """opportunity_score and gap_mult must be the same whether policy is low-conviction
    or absent entirely — the no-policy baseline."""
    import tempfile
    from pathlib import Path as P
    from unittest.mock import patch

    v = _make_v(with_alt=True)
    vel = {"ACME": {"n_recent": 0, "prior_avg": None, "accel": None, "spike": False}}

    with patch("engine.intel_hub._velocity_ledger_path", return_value=P(tempfile.mkdtemp()) / "x.jsonl"):
        # no policy
        d_none = _dossier("ACME", v, _empty_pidx(), vel)
        # low-conviction policy that would have inflated gap if ungated
        low_facet = _make_policy_facet(conviction="low", dir_=1)
        pidx_low = {"by_ticker": {"ACME": low_facet}, "by_sector": {}, "regime": None}
        d_low = _dossier("ACME", v, pidx_low, vel)

    assert d_low["opportunity_score"] == d_none["opportunity_score"], (
        f"low-conviction policy must not change opportunity: "
        f"no-policy={d_none['opportunity_score']} low={d_low['opportunity_score']}"
    )
    assert d_low["leading_gap"] == d_none["leading_gap"], (
        f"leading_gap must be identical: no-policy={d_none['leading_gap']} low={d_low['leading_gap']}"
    )
