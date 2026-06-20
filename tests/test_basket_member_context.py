"""Tests for engine.basket_member_context (within-basket leader-vs-chase, display-only)."""
import numpy as np
import pandas as pd
import pytest

from engine import basket_member_context as bmc


def _ramp(ret_pct: float, periods: int = 21, base: float = 100.0) -> list[float]:
    """A series whose 20-day return (last / iloc[-21] - 1) equals ret_pct/100."""
    return list(np.linspace(base, base * (1.0 + ret_pct / 100.0), periods))


# --------------------------------------------------------------- pure classifier
def test_classify_parabolic_is_always_a_chase():
    # own-history parabolic flag: a chase regardless of cohort position (even if barely extended)
    assert bmc.classify_member(5.0, -20.0, 0.99, "parabolic") == ("beyond", True)


def test_classify_leader_extended_with_theme():
    # extended (>=20% over 200d), only +3pp above the cohort median, and leads on RS -> leader
    assert bmc.classify_member(32.0, 3.0, 0.90, "steady") == ("leader", False)


def test_classify_beyond_when_far_past_cohort():
    # extended AND >10pp above the basket median -> the genuine chase, even if it also "leads"
    assert bmc.classify_member(60.0, 31.0, 1.0, "stretched") == ("beyond", False)


def test_classify_extended_midpack():
    # extended, in-line with the cohort, but NOT leading -> mild-caution "extended"
    assert bmc.classify_member(29.0, 0.0, 0.40, "steady") == ("extended", False)


def test_classify_laggard_has_room():
    # lagging on RS and not extended -> catch-up territory
    assert bmc.classify_member(4.0, -25.0, 0.20, "steady") == ("laggard", False)


def test_classify_in_range_default():
    assert bmc.classify_member(12.0, -2.0, 0.50, "steady") == ("in_range", False)


def test_classify_na_without_reads():
    assert bmc.classify_member(None, None, 0.5, "steady") == ("na", False)
    assert bmc.classify_member(25.0, 1.0, None, "steady") == ("na", False)


def test_band_labels_parabolic_override():
    en, zh, tone = bmc._band_labels("beyond", True)
    assert en == "Parabolic — chase" and tone == "neg"
    en2, _, tone2 = bmc._band_labels("leader", False)
    assert en2 == "Leader · time the entry" and tone2 == "pos"


# --------------------------------------------------------------- helpers
def test_ret20_and_mt():
    assert bmc._ret20(pd.Series(_ramp(10.0))) == pytest.approx(10.0, abs=1e-6)
    assert bmc._ret20(pd.Series([100.0] * 10)) is None     # too short
    assert bmc._mt({"symbol": "MSFT"}) == "MSFT"


def test_live_members_window_mask():
    last = pd.Timestamp("2024-01-10")
    members = [
        {"ticker": "A", "added": "2020-01-01"},                          # live
        {"ticker": "B", "added": "2020-01-01", "removed": "2023-06-01"},  # removed before today
        {"ticker": "C", "added": "2025-01-01"},                          # added in the future
    ]
    live = bmc._live_members(members, {"A", "B", "C"}, last)
    assert [m["ticker"] for m in live] == ["A"]


# --------------------------------------------------------------- theme cross-section
def _theme_fixture():
    # one basket, whole theme extended (~+30% over 200d) but distinct profiles.
    specs = {
        "LEAD":   {"ext": 32.0, "grade": "steady",    "ret20": 40.0},  # leads, in-line stretch
        "MID":    {"ext": 29.0, "grade": "steady",    "ret20": 10.0},  # extended, mid-pack
        "BEYOND": {"ext": 60.0, "grade": "stretched", "ret20": 35.0},  # far past the cohort
        "PARA":   {"ext": 24.0, "grade": "parabolic", "ret20": 20.0},  # own-history radioactive
        "LAG":    {"ext": 4.0,  "grade": "steady",    "ret20": 2.0},   # lagging, room
    }
    idx = pd.date_range("2024-01-01", periods=21, freq="B")
    closes = pd.DataFrame({t: _ramp(s["ret20"]) for t, s in specs.items()}, index=idx)
    ext_sig = {t: {"ext": s["ext"], "ext_z": 0.0, "grade": s["grade"], "near_52wh": 0.9}
               for t, s in specs.items()}
    b = {"id": "t1", "name": "Test theme", "members": [
        {"ticker": t, "name": t, "added": "2020-01-01"} for t in specs]}
    return closes, ext_sig, b, idx.max()


def test_theme_rows_leader_vs_chase_split():
    closes, ext_sig, b, last = _theme_fixture()
    row = bmc._theme_rows(closes, ext_sig, "t1", b, last)
    assert row is not None
    bands = {m["ticker"]: m["band"] for m in row["members"]}
    assert bands["LEAD"] == "leader"
    assert bands["BEYOND"] == "beyond"
    assert bands["PARA"] == "beyond"                       # parabolic folds into the chase bucket
    assert bands["MID"] == "extended"
    assert bands["LAG"] == "laggard"
    # the parabolic name keeps its radioactive label
    para = next(m for m in row["members"] if m["ticker"] == "PARA")
    assert para["parabolic"] is True and para["band_en"] == "Parabolic — chase"
    # ext_rel is measured against the basket median (29)
    lead = next(m for m in row["members"] if m["ticker"] == "LEAD")
    assert lead["ext_rel"] == pytest.approx(3.0, abs=0.1)
    # headline counts + hot flag
    assert row["n_leaders"] == 1 and row["n_beyond"] == 2 and row["hot"] is True
    assert row["median_ext"] == pytest.approx(29.0, abs=0.1)


def test_theme_rows_too_thin_returns_none():
    closes, ext_sig, b, last = _theme_fixture()
    b2 = {"id": "t2", "name": "Thin", "members": b["members"][:3]}   # only 3 < MIN_MEMBERS
    assert bmc._theme_rows(closes, ext_sig, "t2", b2, last) is None


# --------------------------------------------------------------- region smoke
@pytest.mark.parametrize("region", ["us", "cn", "hk", "ca"])
def test_compute_region_smoke(region):
    out = bmc.compute_member_context(region)
    if out is None:
        pytest.skip(f"no {region} baskets cache present")
    assert out["region"] in (region, "us")
    assert out["themes"]
    # every member carries a band + display labels; by_ticker reverse index is populated
    m0 = out["themes"][0]["members"][0]
    assert m0["band"] in bmc.BANDS and m0["band_en"]
    assert isinstance(out["by_ticker"], dict) and out["by_ticker"]
    # hot themes sort to the front
    hot_flags = [t["hot"] for t in out["themes"]]
    assert hot_flags == sorted(hot_flags, reverse=True)
