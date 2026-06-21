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
# --------------------------------------------------------------------------- #
# insider opportunistic-cluster feed
# --------------------------------------------------------------------------- #
def _panel(rows):
    pd = pytest.importorskip("pandas")
    return pd.DataFrame(rows)


def test_insider_cluster_detects_open_market_breadth():
    pd = pytest.importorskip("pandas")
    base = {"trans_date": "2026-03-20", "usd": 200000.0, "is_officer": True}
    rows = [{**base, "ticker": "ABCD", "code": "P", "rptownercik": i} for i in range(4)]  # 4 distinct buyers
    rows += [{**base, "ticker": "ABCD", "code": "P", "rptownercik": 0}]                    # dup insider (still 4)
    cands = D.scan_insider_clusters(_panel(rows), min_buyers=3, min_usd=1e5)
    assert cands and cands[0]["ticker"] == "ABCD"
    assert cands[0]["opp_buyers"] == 4 and cands[0]["source"] == "insider_cluster"
    assert cands[0]["disc_score"] <= 0.45                       # lagging confirmer is capped


def test_insider_cluster_excludes_junk_grants_sales_and_thin():
    pd = pytest.importorskip("pandas")
    base = {"trans_date": "2026-03-20", "usd": 5e5, "is_officer": True}
    rows = []
    rows += [{**base, "ticker": "NONE", "code": "P", "rptownercik": i} for i in range(5)]   # sentinel junk
    rows += [{**base, "ticker": "GRNT", "code": "A", "rptownercik": i} for i in range(5)]   # grants (not P)
    rows += [{**base, "ticker": "SELL", "code": "S", "rptownercik": i} for i in range(5)]   # sales
    rows += [{**base, "ticker": "THIN", "code": "P", "rptownercik": i} for i in range(2)]   # only 2 buyers
    got = {c["ticker"] for c in D.scan_insider_clusters(_panel(rows), min_buyers=3, min_usd=1e5)}
    assert got == set()                                         # all correctly excluded


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


# --------------------------------------------------------------------------- #
# Feed 4 — activist beneficial-ownership (Schedule 13D / 13G→13D flip)
# --------------------------------------------------------------------------- #
def _reg(state="activist", signal="high", n_13d=1, is_flip=False,
         latest_date="2026-06-18", filer="STARBOARD VALUE"):
    return {"state": state, "signal": signal, "n_13d": n_13d, "n_13g": 0,
            "is_flip": is_flip, "latest_date": latest_date, "latest_filer": filer}


def test_activist_admits_high_signal_only():
    regime = {"ACT": _reg(), "PAS": _reg(state="passive", signal="low"),
              "CUST": _reg(state="custodial", signal="noise")}
    cands = D.scan_activist_ownership(regime, None, _TODAY)
    assert [c["ticker"] for c in cands] == ["ACT"]
    assert cands[0]["source"] == "activist_ownership" and cands[0]["validated"] is False


def test_activist_flip_outranks_plain_and_capped():
    regime = {"FLIP": _reg(state="flip", is_flip=True, n_13d=2),
              "PLAIN": _reg()}
    cands = D.scan_activist_ownership(regime, None, _TODAY)
    assert cands[0]["ticker"] == "FLIP"                       # flip is the higher-signal escalation
    assert all(c["disc_score"] <= D._ACTIVIST_CAP_MEASURING for c in cands)


def test_activist_stale_filing_dropped():
    regime = {"OLD": _reg(latest_date="2026-01-01")}          # >90d before today → not a discovery
    assert D.scan_activist_ownership(regime, None, _TODAY) == []


def test_activist_scored_gate_lifts_cap_and_tags():
    regime = {"ACT": _reg()}
    measuring = D.scan_activist_ownership(regime, None, _TODAY)[0]
    scored = D.scan_activist_ownership(regime, {"scored": True, "lead_horizon": 21}, _TODAY)[0]
    assert scored["disc_score"] > measuring["disc_score"]     # validated → leading-tier cap
    assert scored["validated"] is True and scored["lead_horizon"] == 21
    assert scored["disc_score"] <= D._ACTIVIST_CAP_SCORED


def test_build_includes_activist_feed():
    out = D.build(None, None, bundle_universe={"OWNED"}, today=_TODAY,
                  ownership={"OFFD": _reg(), "OWNED": _reg(state="flip", is_flip=True)})
    assert out["sources"]["activist_ownership"] == 2
    assert out["by_ticker"]["OFFD"]["off_desk"] is True
    assert out["by_ticker"]["OWNED"]["off_desk"] is False


# --------------------------------------------------------------------------- #
# Feed 5 — index-reconstitution forced flow (gate-controlled)
# --------------------------------------------------------------------------- #
def _chg(t, kind="add", index="sp500", d="2026-06-16"):
    return {"ticker": t, "kind": kind, "index": index, "d": d}


def test_recon_dormant_without_scored_gate():
    chgs = [_chg("NEW")]
    assert D.scan_index_reconstitution(chgs, None, _TODAY) == []          # no gate → dormant
    assert D.scan_index_reconstitution(chgs, {"scored": True, "add_scored": False}, _TODAY) == []


def test_recon_emits_adds_when_validated_with_index_tier():
    chgs = [_chg("BIG", index="sp500"), _chg("SMALL", index="sp600")]
    cands = D.scan_index_reconstitution(chgs, {"add_scored": True}, _TODAY)
    assert [c["ticker"] for c in cands] == ["BIG", "SMALL"]               # sp500 tier > sp600
    assert cands[0]["source"] == "index_reconstitution"
    assert cands[0]["disc_score"] > cands[1]["disc_score"]


def test_recon_drops_deletes_and_stale():
    chgs = [_chg("DEL", kind="delete"), _chg("OLD", d="2026-05-01")]      # delete + >15d stale
    assert D.scan_index_reconstitution(chgs, {"add_scored": True}, _TODAY) == []


def test_build_recon_gate_controlled():
    chgs = [_chg("ADDED")]
    off = D.build(None, None, bundle_universe=set(), today=_TODAY,
                  index_changes=chgs, recon_gate={"add_scored": False})
    assert off["sources"]["index_reconstitution"] == 0                   # dormant
    on = D.build(None, None, bundle_universe=set(), today=_TODAY,
                 index_changes=chgs, recon_gate={"add_scored": True})
    assert on["sources"]["index_reconstitution"] == 1
