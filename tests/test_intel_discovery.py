"""Pure-function tests for engine/intel_discovery.py — the off-desk discovery scan."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from engine import intel_discovery as D  # noqa: E402

_TODAY = date(2026, 6, 21)


def _quiet(t, sig=60, channels=None, extended=False, crowd_pen=0.0, opt=1, activity=0.3, rs=5.0):
    # crowd.penalty is on the producer's 0–15 scale (radar_plus._crowd_penalty)
    return {"ticker": t, "state": "QUIET", "signal_score": sig, "edge_score": 50,
            "channels": channels if channels is not None else ["congress_buy", "material_8k"],
            "extended": extended, "crowd": {"penalty": crowd_pen},
            "options": {"lean": opt}, "activity": activity, "rs_vs_spy_60d": rs}


# --------------------------------------------------------------------------- #
# radar QUIET-but-accumulating
# --------------------------------------------------------------------------- #
def test_radar_quiet_admits_multichannel_uncrowded():
    cands = D.scan_radar_quiet([_quiet("BIIB", sig=58,
                                channels=["clinical_phase3_start", "congress_buy", "fda_label_expansion"])])
    assert cands and cands[0]["ticker"] == "BIIB"
    assert cands[0]["source"] == "radar_quiet" and cands[0]["disc_score"] > 0
    assert cands[0]["n_channels"] == 3


def test_radar_quiet_excludes_thin_crowded_extended_nonquiet():
    rows = [
        _quiet("ONE", channels=["congress_buy"]),                 # only 1 leading channel
        _quiet("CRWD", crowd_pen=10.0),                          # crowded on the 0–15 scale (>0.25 normalized)
        _quiet("EXT", extended=True),                             # extended → anti-chase
        {"ticker": "UP", "state": "CONFIRMED_UP", "signal_score": 80,
         "channels": ["congress_buy", "material_8k"]},            # not QUIET (already on desk)
        _quiet("LOW", sig=30),                                    # signal below floor
    ]
    got = {c["ticker"] for c in D.scan_radar_quiet(rows)}
    assert got == set()                                          # all five correctly excluded


def test_radar_quiet_admits_small_real_crowd_penalty():
    # a name with a SMALL real crowd hit (0–15 scale) is still admitted (the gate is graded,
    # not penalty==0) — guards the unit-mismatch regression.
    cands = D.scan_radar_quiet([_quiet("OK", crowd_pen=3.0)])    # 3/15 = 0.2 < 0.25 → admitted
    assert cands and cands[0]["ticker"] == "OK"


def test_federal_velocity_lumpy_single_award_capped_and_flagged():
    pd = pytest.importorskip("pandas")
    idx = pd.date_range("2025-01-01", periods=10, freq="MS")
    # flat ~$1M/mo baseline, then ONE $500M award in the last month = lumpy, not a ramp
    df = pd.DataFrame({"LUMP": [1e6] * 9 + [5e8]}, index=idx)
    c = D.scan_federal_velocity(df, min_recent_usd=1e6)[0]
    assert c["lumpy"] is True and c["disc_score"] <= 0.50
    assert "one large" in c["reason"].lower() and "%" not in c["reason"]


def test_federal_velocity_sparse_prior_is_provisional_not_saturated():
    pd = pytest.importorskip("pandas")
    idx = pd.date_range("2025-01-01", periods=10, freq="MS")
    # near-zero lumpy prior then a surge → must NOT saturate to a top-tier 0.85
    df = pd.DataFrame({"SP": [0, 0, 0, 0, 5e5, 0, 0, 4e6, 4e6, 4e6]}, index=idx)
    out = {c["ticker"]: c for c in D.scan_federal_velocity(df, min_recent_usd=1e6)}
    if "SP" in out:                                             # admitted at all
        assert out["SP"]["disc_score"] <= 0.55                 # never the saturated 0.85


def test_radar_quiet_runup_haircut():
    fresh = D.scan_radar_quiet([_quiet("A", rs=0.0)])[0]["disc_score"]
    run = D.scan_radar_quiet([_quiet("A", rs=110.0)])[0]["disc_score"]
    assert fresh > run                                          # a big prior run-up is docked


# --------------------------------------------------------------------------- #
# federal contract-award velocity
# --------------------------------------------------------------------------- #
def _frame():
    pd = pytest.importorskip("pandas")
    idx = pd.date_range("2025-01-01", periods=10, freq="MS")
    return pd.DataFrame({                                       # realistic obligated-$ magnitudes
        "ACCEL": [1e6] * 7 + [5e6, 6e6, 7e6],                  # real ramp off a $1M/mo base
        "FLAT":  [3e6] * 10,                                    # steady → ~0 accel
        "DECEL": [5e6] * 7 + [1e5, 1e5, 1e5],                  # collapsing
        "TINY":  [1e4] * 10,                                    # recent sum $30k < the $2M floor
    }, index=idx)


def test_federal_velocity_flags_acceleration_only():
    out = {c["ticker"]: c for c in D.scan_federal_velocity(_frame())}
    assert "ACCEL" in out and out["ACCEL"]["accel"] > 0 and out["ACCEL"]["lumpy"] is False
    assert "DECEL" not in out                                   # decelerating excluded
    assert "TINY" not in out                                    # below $ floor excluded
    assert out["ACCEL"]["source"] == "federal_velocity"


def test_federal_velocity_empty_safe():
    assert D.scan_federal_velocity(None) == []


# --------------------------------------------------------------------------- #
# build — off-desk marking + dedup
# --------------------------------------------------------------------------- #
def test_build_marks_off_desk_and_dedups():
    radar = [_quiet("INUNI", channels=["congress_buy", "material_8k"]),
             _quiet("OFF", channels=["clinical_phase3_start", "fda_label_expansion"])]
    out = D.build(radar, None, bundle_universe={"INUNI"}, today=_TODAY)
    bt = out["by_ticker"]
    assert bt["INUNI"]["off_desk"] is False and bt["OFF"]["off_desk"] is True
    assert out["n_off_desk"] == 1 and out["schema"] == D.SCHEMA
    assert [c["ticker"] for c in out["off_desk"]] == ["OFF"]


def test_build_degrades_on_empty():
    out = D.build(None, None, bundle_universe=set(), today=_TODAY)
    assert out["n"] == 0 and out["off_desk"] == [] and out["candidates"] == []
