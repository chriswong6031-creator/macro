"""Bitcoin Vector CONVICTION layer tests — pure functions, no network.

Guards the honest no-edge labeling (TOSS-UP / LEAN / EDGE) so a near-50/50 prob
can never silently render as a confident directional call. Calibrated to the
MEASURED reliable-cell up-rate spread (51.9-57.1% at 7d). See D-vec-CONV.

Run: .venv/bin/python -m tests.test_vector_conviction
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_vector import _conviction, _conviction_why, _cond_up_prob, _tape_sign  # noqa: E402
from lib import config  # noqa: E402

MIN_N = 20


def _state(p_bull, n, tilt, tape, vsign, bands=(3, 7)):
    return _conviction(p_bull, n, tilt, tape, vsign, MIN_N, bands)["state"]


def test_band_table():
    """The conviction state for representative (p_bull, n, tilt, tape, verdict) inputs."""
    cases = [
        # today's live readings — both must be the honest coin-flip
        ((47, 1351, -5, -1, -1), "TOSS-UP"),   # mid 7d
        ((48, 1351, -5, -1, +1), "TOSS-UP"),   # short 3d (verdict +1 bounce, still no edge)
        ((50, 1351, 0, 0, 0), "TOSS-UP"),      # dead centre
        ((53, 1351, -5, -1, -1), "TOSS-UP"),   # |p-50|=3 boundary stays TOSS-UP
        # genuine leans inside the reliable spread
        ((56, 1351, 5, 1, 1), "LEAN"),         # |p-50|=6, reliable cell, tape confirms
        ((55, 295, 5, 1, 1), "LEAN"),          # moderate cell (n=295) mild lean survives
        ((44, 1351, -5, -1, -1), "LEAN"),      # symmetric bear lean
        # EDGE only when corroborated
        ((62, 600, 5, 1, 1), "EDGE"),          # reliable + tape + verdict all agree
        ((62, 600, 5, -1, 1), "LEAN"),         # tape conflict demotes EDGE -> LEAN
        ((62, 600, 5, 1, -1), "LEAN"),         # verdict disagreement demotes EDGE -> LEAN
        ((62, 100, 5, 1, 1), "TOSS-UP"),       # n<300: a big lean from a thin cell is noise
        # thin-cell gate: bear/low_risk style (n<min) can never print a lean
        ((23, 26, 0, -1, -1), "TOSS-UP"),      # n>min but EDGE-sized lean on a thin cell -> no edge
        ((31, 15, -5, -1, -1), "TOSS-UP"),     # n<min_cell_n hard gate
    ]
    bad = [(a, exp, _state(*a)) for a, exp in cases if _state(*a) != exp]
    assert not bad, f"conviction band mismatches: {bad}"


def test_direction_and_caps():
    c = _conviction(47, 1351, -5, -1, -1, MIN_N, (3, 7))
    assert c["dir"] == -1 and c["p_bear"] == 53 and c["p_bull"] == 47
    assert c["lean"] == 3 and c["conf"] == "reliable"
    # confirmed checkmark requires tape AND tilt to agree with the prob direction
    assert _conviction(56, 1351, 5, 1, 1, MIN_N, (3, 7))["confirmed"] is True
    assert _conviction(56, 1351, -5, 1, 1, MIN_N, (3, 7))["confirmed"] is False  # tilt disagrees
    # an EDGE can never survive under a disagreeing verdict (silent-contradiction guard)
    assert _conviction(75, 1351, 5, 1, -1, MIN_N, (3, 7))["state"] != "EDGE"


def test_tape_sign():
    rows = [{"key": "D", "trend": "down"}, {"key": "3D", "trend": "down"},
            {"key": "W", "trend": "down"}, {"key": "2W", "trend": "up"}]
    assert _tape_sign(rows, {"D", "3D"}) == -1
    assert _tape_sign(rows, {"W", "2W"}) == 0      # one up + one down -> mixed
    assert _tape_sign(rows, {"ME"}) == 0           # missing keys -> neutral


def test_why_line_is_honest():
    c = _conviction(47, 1351, -5, -1, -1, MIN_N, (3, 7))
    en, zh = _conviction_why(c, "bear / high risk", 1351, 7)
    assert "coin-flip" in en and "1,351" in en and "53/47" in en
    assert "抛硬币" in zh


def test_missing_prob_is_tossup():
    c = _conviction(None, None, None, 0, 0, MIN_N, (3, 7))
    assert c["state"] == "TOSS-UP" and c["p_bull"] == 50


def _prior_df(phase, pct):
    idx = pd.date_range("2020-01-01", periods=80, freq="D")
    return pd.DataFrame({"close": pd.Series(np.linspace(100, 110, 80), index=idx),
                         "momentum_state": "bull",
                         "cphase_phase": phase, "cphase_pct": pct}, index=idx)


def test_cycle_phase_prior_sign_and_cap():
    """The bottom-anchored 1064/364 phase drives the soft cycle prior: markup up,
    markdown down, flipping inside the top/bottom reversal zone — never beyond the cap."""
    cfg = config.load()["vector"]["scenarios"]
    cap, h = cfg["cycle_tilt_pp"], cfg["prob_horizon_d"]
    tilt = lambda ph, p: _cond_up_prob(_prior_df(ph, p), cfg, h)[3]
    assert tilt("markup", 0.40) == cap        # mid-markup tilts up by the full cap
    assert tilt("markdown", 0.40) == -cap     # mid-markdown tilts down
    assert tilt("markdown", 0.95) == cap      # bottom reversal zone flips to up
    assert tilt("markup", 0.95) == -cap       # top reversal zone flips to down
    assert all(abs(tilt(*c)) <= cap for c in
               [("markup", 0.4), ("markdown", 0.4), ("markdown", 0.95), ("markup", 0.95)])


if __name__ == "__main__":
    for fn in [test_band_table, test_direction_and_caps, test_tape_sign,
               test_why_line_is_honest, test_missing_prob_is_tossup,
               test_cycle_phase_prior_sign_and_cap]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all vector conviction tests passed")
