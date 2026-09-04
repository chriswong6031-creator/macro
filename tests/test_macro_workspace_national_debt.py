"""Composer tests for the US national_debt_liabilities workspace (F01 / R6).

RED-first: each degraded condition must produce the correct TYPED state and
never a zero / neutral / calm default. Covers: the COMPUTATION_REFUSED
headline shape (architecture 10.12 DOES define a two-axis blueprint, unlike
the NOT_APPLICABLE workspaces -- see national_debt.py's module docstring),
the four per-source cadence freshness laws (DTS 5d/4d, auctions 10d/7d, BIS
260d/30d -- with the mandatory 2025-12-31-at-age-247d hand-check -- and bonds
3d/3d), hand-computable TGA impulse / net-issuance sum+pace / withheld-tax
YoY derived reads, the leg-floor auction recent/baseline demand reads
(including fewer-than-window edge cases), the three-legged issuance/demand/
bond-desk contradiction (fires / stays silent on each leg), the eleven typed
NOT_COVERED debt-stock-gap pins, BIS attribution-in-prose, digest determinism
with genuinely-consumed-field mutations and unconsumed-field negative
controls, a prose scan for raw enum-token leaks, zh-narrative integrity,
schema validation, and a real-owner-artifact smoke build (data/bonds/latest.json).

    python3 -m pytest tests/test_macro_workspace_national_debt.py -x -q
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import contract, national_debt  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"
BUILT_DATE = dt.date(2026, 9, 4)
BONDS_LATEST = ROOT / "data" / "bonds" / "latest.json"


# --------------------------------------------------------------------------- #
# fixture helpers (small, hand-computable -- see the inline arithmetic notes
# next to every derived-value assertion below)
# --------------------------------------------------------------------------- #
def _daily_rows(end: dt.date, n_days: int, value: float) -> list[tuple[str, float]]:
    """``n_days`` CONSECUTIVE daily rows ending at (and including) ``end``,
    each valued ``value`` -- e.g. n_days=28 produces the 28 dates
    ``end-27 .. end``, exactly filling a trailing-28-day calendar window with
    real (never fabricated/ffilled) observations."""
    return [((end - dt.timedelta(days=i)).isoformat(), value) for i in range(n_days - 1, -1, -1)]


def _auction(date_str: str, sec_type: str | None, tenor: float | None,
             btc: float | None, hy: float | None) -> dict:
    return {"auction_date": date_str, "security_type": sec_type, "tenor_years": tenor,
            "bid_to_cover": btc, "high_yield": hy}


def _monthly_auctions(end: dt.date, btc_values: list[float]) -> list[dict]:
    """``len(btc_values)`` auctions spaced ~30 days apart, ending at ``end``
    (most recent last, ascending), each carrying the matching bid_to_cover
    (oldest-to-newest order matches ``btc_values``' own order). All auctions
    land within ``30 * (n-1)`` days of ``end`` -- comfortably inside the
    365-day baseline window for any n <= 12."""
    n = len(btc_values)
    dates = [end - dt.timedelta(days=30 * i) for i in range(n)]
    dates.reverse()  # ascending: oldest first, `end` last
    return [_auction(d.isoformat(), "Note", 10.0, btc, 4.0) for d, btc in zip(dates, btc_values)]


# -- TGA: anchor 2026-09-02 (age 2d -> CURRENT under DTS cadence 5d/4d). Hand
# -- verified: 2026-08-05 is EXACTLY 28 days before 2026-09-02 (Aug5->Aug31 =
# -- 26d, +Sep1,Sep2 = 2d, total 28d); 2026-06-03 is EXACTLY 91 days before
# -- 2026-09-02 (Jun3->Jun30=27d, +Jul(31)+Aug(31)+Sep(2) = 91d) -- both land
# -- at zero slack, well inside the 10-day lookback tolerance.
def _tga_rows() -> list[tuple[str, float]]:
    return [("2026-06-03", 500_000.0), ("2026-08-05", 600_000.0), ("2026-09-02", 650_000.0)]


# -- net issuance: 91 consecutive daily rows ending 2026-09-02 (age 2d ->
# -- CURRENT). Flat pace (100.0/day throughout) -> sum_4w=28*100=2800.0,
# -- sum_13w=91*100=9100.0, pace_delta=100.0-100.0=0.0 (no acceleration).
def _net_issuance_rows_flat() -> list[tuple[str, float]]:
    return _daily_rows(dt.date(2026, 9, 2), 91, 100.0)


# -- accelerating pace (used by the contradiction-fires test): first 63 days
# -- (91-28) at 100.0/day, last 28 days at 5000.0/day.
# -- sum_4w = 28*5000 = 140,000.0 -> avg4 = 5000.0
# -- sum_13w = 63*100 + 28*5000 = 6,300 + 140,000 = 146,300.0 -> avg13 = 146300/91
# -- pace_delta = 5000.0 - 146300/91 (~1607.6923) = ~3392.3077 ($mn/day), well
# -- above the 1000.0 flat band.
def _net_issuance_rows_accelerating() -> list[tuple[str, float]]:
    end = dt.date(2026, 9, 2)
    old = _daily_rows(end - dt.timedelta(days=28), 63, 100.0)
    recent = _daily_rows(end, 28, 5000.0)
    return old + recent


# -- withheld taxes: current 4w block (2026-08-06..2026-09-02, 28 rows @50.0,
# -- sum=1400.0) + year-ago 4w block (2025-08-06..2025-09-02, 28 rows @40.0,
# -- sum=1120.0). 2025-09-02 is EXACTLY 365 days before 2026-09-02 (no Feb-29
# -- between them -- 2026 is not a leap year) -> the YoY lookup finds the
# -- prior window at zero slack. yoy = (1400/1120 - 1)*100 = 25.0% exactly
# -- (1120 * 1.25 = 1400.0).
def _withheld_rows() -> list[tuple[str, float]]:
    return (_daily_rows(dt.date(2025, 9, 2), 28, 40.0)
            + _daily_rows(dt.date(2026, 9, 2), 28, 50.0))


# -- auctions: 12 monthly auctions ending 2026-09-01 (age 3d -> CURRENT under
# -- auction cadence 10d/7d). Oldest 4 @3.00 bid-to-cover, most recent 8
# -- @2.40 (weakening). recent_avg (last 8) = 2.40 exactly. baseline_avg (all
# -- 12, min_n=10 satisfied) = (4*3.00 + 8*2.40)/12 = (12.0+19.2)/12 = 2.60.
# -- spread = 2.40 - 2.60 = -0.20 (magnitude > the 0.10 flat band).
def _auction_rows_weakening() -> list[dict]:
    return _monthly_auctions(dt.date(2026, 9, 1), [3.00] * 4 + [2.40] * 8)


# -- flat/healthy auction demand (used as the non-contradiction baseline):
# -- 10 monthly auctions all @2.50 -> recent_avg=2.50, baseline_avg=2.50,
# -- spread=0.0.
def _auction_rows_flat() -> list[dict]:
    return _monthly_auctions(dt.date(2026, 9, 1), [2.50] * 10)


# -- BIS: quarterly, period-end dated. Latest print 2025-12-31 -- the
# -- MANDATORY 2026-09-04 hand-check date (age 247d; Dec31->Jan31=31,
# -- +Feb28+Mar31+Apr30+May31+Jun30+Jul31+Aug31+Sep4 = 31+28+31+30+31+30+31+31+4
# -- = 247) -- MUST read CURRENT under the 260d/30d BIS cadence (247<=260).
def _dsr_rows() -> list[tuple[str, float]]:
    return [("2025-09-30", 13.8), ("2025-12-31", 14.0)]


def _gap_rows() -> list[tuple[str, float]]:
    return [("2025-09-30", -2.0), ("2025-12-31", -1.5)]


# -- bonds_latest: the REAL owner artifact values (data/bonds/latest.json as
# -- read at authoring time), date 2026-09-03 (age 1d -> CURRENT under bonds
# -- cadence 3d/3d).
def _bonds_latest_healthy() -> dict:
    return {"date": "2026-09-03", "health_score": 89, "health_label": "healthy",
            "cycle_phase": "late", "verdict_en": "Bond health healthy (89/100).",
            "verdict_zh": "债券健康度健康（89/100）。"}


def _base_treasury_frames() -> dict:
    return {
        national_debt.TGA_KEY: _tga_rows(),
        national_debt.NET_ISSUANCE_KEY: _net_issuance_rows_flat(),
        national_debt.WITHHELD_KEY: _withheld_rows(),
    }


def _base_bis_frames() -> dict:
    return {national_debt.BIS_DSR_KEY: _dsr_rows(), national_debt.BIS_GAP_KEY: _gap_rows()}


_UNSET = object()  # sentinel: distinguishes "caller omitted the arg" (use the
# default fixture) from "caller explicitly passed None/empty" (a genuinely
# absent owner input) -- a plain ``=None`` default cannot tell those apart.


def _compose(treasury_frames=_UNSET, auction_rows=_UNSET, bis_frames=_UNSET,
             bonds_latest=_UNSET, **kw) -> dict:
    return national_debt.compose(
        _base_treasury_frames() if treasury_frames is _UNSET else treasury_frames,
        _auction_rows_flat() if auction_rows is _UNSET else auction_rows,
        _base_bis_frames() if bis_frames is _UNSET else bis_frames,
        _bonds_latest_healthy() if bonds_latest is _UNSET else bonds_latest,
        built_at=BUILT_AT, **kw,
    )


def _metric(snapshot: dict, metric_id: str) -> dict:
    return next(m for m in snapshot["metrics"]["items"] if m["metric_id"] == metric_id)


def _required(snapshot: dict, cid: str) -> dict:
    return next(c for c in snapshot["availability"]["required"] if c["component_id"] == cid)


def _implication(snapshot: dict, iid: str) -> dict | None:
    return next((i for i in snapshot["implications"]["items"] if i["implication_id"] == iid), None)


# --------------------------------------------------------------------------- #
# healthy baseline
# --------------------------------------------------------------------------- #
def test_baseline_all_required_sources_current() -> None:
    snap = _compose()
    assert snap["workspace"]["id"] == "national_debt_liabilities"
    assert snap["region"]["code"] == "US"
    for cid in ("tga", "net_issuance", "withheld_taxes", "auction_demand"):
        r = _required(snap, cid)
        assert r["freshness"] == "CURRENT", (cid, r)
        assert r["status"] == "PRESENT"
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["availability"]["coverage_ratio"] == 1.0


def test_optional_components_present_but_not_required() -> None:
    snap = _compose()
    all_c = snap["availability"]["required"]
    required_ids = {c["component_id"] for c in all_c if c["required"]}
    optional_ids = {c["component_id"] for c in all_c if not c["required"]}
    assert {"bis_household_dsr", "bis_credit_gap", "bond_desk_state"} == optional_ids
    assert not (optional_ids & required_ids)


def test_bis_and_bond_desk_missing_never_degrades_required_availability_state() -> None:
    snap = _compose(bis_frames=None, bonds_latest=None)
    assert snap["availability"]["state"] == "CURRENT"
    for cid in ("bis_household_dsr", "bis_credit_gap", "bond_desk_state"):
        opt = _required(snap, cid)
        assert opt["status"] == "ABSENT"
        assert opt["freshness"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# TGA: level + 4w/13w impulse (hand-computable)
# --------------------------------------------------------------------------- #
def test_tga_level_and_impulses() -> None:
    snap = _compose()
    level = _metric(snap, "tga_level")
    assert level["value"] == pytest.approx(650_000.0)
    assert level["unit"] == "usd_mn"
    imp4 = _metric(snap, "tga_impulse_4w")
    assert imp4["value"] == pytest.approx(650_000.0 - 600_000.0)  # = 50,000.0
    imp13 = _metric(snap, "tga_impulse_13w")
    assert imp13["value"] == pytest.approx(650_000.0 - 500_000.0)  # = 150,000.0


def test_tga_impulse_insufficient_history_when_only_latest_row() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.TGA_KEY] = [("2026-09-02", 650_000.0)]
    snap = _compose(treasury_frames=tf)
    imp4 = _metric(snap, "tga_impulse_4w")
    assert imp4["value"] is None
    assert imp4["status"] == "ABSENT"
    assert imp4["null_reason"] == "INSUFFICIENT_HISTORY"
    level = _metric(snap, "tga_level")
    assert level["value"] == pytest.approx(650_000.0)  # unaffected


def test_tga_never_rescaled_to_billions() -> None:
    snap = _compose()
    level = _metric(snap, "tga_level")
    assert level["unit"] == "usd_mn"
    assert level["value"] == pytest.approx(650_000.0)  # raw $mn, never /1000


# --------------------------------------------------------------------------- #
# net issuance: 4w/13w sums + the self-referential pace-acceleration read
# --------------------------------------------------------------------------- #
def test_net_issuance_sums_flat_pace() -> None:
    snap = _compose()
    sum4 = _metric(snap, "net_issuance_sum_4w")
    assert sum4["value"] == pytest.approx(28 * 100.0)  # = 2800.0
    sum13 = _metric(snap, "net_issuance_sum_13w")
    assert sum13["value"] == pytest.approx(91 * 100.0)  # = 9100.0
    pace = _metric(snap, "net_issuance_pace_delta_4w_vs_13w_avg_daily")
    assert pace["value"] == pytest.approx(0.0, abs=1e-9)


def test_net_issuance_pace_accelerating() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    snap = _compose(treasury_frames=tf)
    sum4 = _metric(snap, "net_issuance_sum_4w")
    assert sum4["value"] == pytest.approx(28 * 5000.0)  # = 140,000.0
    sum13 = _metric(snap, "net_issuance_sum_13w")
    assert sum13["value"] == pytest.approx(63 * 100.0 + 28 * 5000.0)  # = 146,300.0
    expected_pace = 5000.0 - (63 * 100.0 + 28 * 5000.0) / 91.0
    pace = _metric(snap, "net_issuance_pace_delta_4w_vs_13w_avg_daily")
    assert pace["value"] == pytest.approx(expected_pace, abs=1e-3)
    assert pace["value"] > national_debt._ISSUANCE_PACE_FLAT_BAND_MN_PER_DAY


def test_net_issuance_13w_insufficient_history_while_4w_still_computes() -> None:
    tf = _base_treasury_frames()
    # 15 consecutive rows ending 2026-09-02: all 15 land inside the 28d window
    # (15 >= _MIN_ROWS_4W=10 -> sum_4w computes) but the SAME 15 rows are also
    # all that's inside the 91d window (15 < _MIN_ROWS_13W=30 -> sum_13w
    # refused) -- an independence check between the two floors.
    tf[national_debt.NET_ISSUANCE_KEY] = _daily_rows(dt.date(2026, 9, 2), 15, 100.0)
    snap = _compose(treasury_frames=tf)
    sum4 = _metric(snap, "net_issuance_sum_4w")
    assert sum4["value"] == pytest.approx(15 * 100.0)
    sum13 = _metric(snap, "net_issuance_sum_13w")
    assert sum13["value"] is None
    assert sum13["null_reason"] == "INSUFFICIENT_HISTORY"
    pace = _metric(snap, "net_issuance_pace_delta_4w_vs_13w_avg_daily")
    assert pace["value"] is None
    assert pace["null_reason"] == "INSUFFICIENT_HISTORY"


def test_net_issuance_missing_entirely_is_source_failed() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = None
    snap = _compose(treasury_frames=tf)
    r = _required(snap, "net_issuance")
    assert r["status"] == "ABSENT"
    assert r["freshness"] == "SOURCE_FAILED"
    sum4 = _metric(snap, "net_issuance_sum_4w")
    assert sum4["value"] is None
    assert sum4["null_reason"] == "SOURCE_FAILED"
    # sibling TGA is unaffected
    assert _metric(snap, "tga_level")["value"] == pytest.approx(650_000.0)


# --------------------------------------------------------------------------- #
# withheld taxes: level + 4w sum + 4w-sum YoY (revenue nowcast)
# --------------------------------------------------------------------------- #
def test_withheld_taxes_level_sum_and_yoy() -> None:
    snap = _compose()
    level = _metric(snap, "withheld_taxes_level")
    assert level["value"] == pytest.approx(50.0)
    sum4 = _metric(snap, "withheld_taxes_sum_4w")
    assert sum4["value"] == pytest.approx(1400.0)
    yoy = _metric(snap, "withheld_taxes_yoy_4w")
    assert yoy["value"] == pytest.approx(25.0)  # (1400/1120 - 1) * 100 = 25.0 exactly
    assert yoy["status"] == "PRESENT"


def test_withheld_taxes_yoy_insufficient_history_when_no_year_ago_window() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.WITHHELD_KEY] = _daily_rows(dt.date(2026, 9, 2), 28, 50.0)  # current only
    snap = _compose(treasury_frames=tf)
    sum4 = _metric(snap, "withheld_taxes_sum_4w")
    assert sum4["value"] == pytest.approx(1400.0)  # unaffected
    yoy = _metric(snap, "withheld_taxes_yoy_4w")
    assert yoy["value"] is None
    assert yoy["null_reason"] == "INSUFFICIENT_HISTORY"


def test_withheld_taxes_yoy_refused_on_zero_base() -> None:
    tf = _base_treasury_frames()
    zero_prior = _daily_rows(dt.date(2025, 9, 2), 10, 0.0)  # 10 >= _MIN_ROWS_4W, sums to 0.0
    tf[national_debt.WITHHELD_KEY] = zero_prior + _daily_rows(dt.date(2026, 9, 2), 28, 50.0)
    snap = _compose(treasury_frames=tf)
    yoy = _metric(snap, "withheld_taxes_yoy_4w")
    assert yoy["value"] is None
    assert yoy["null_reason"] == "COMPUTATION_REFUSED"


def test_withheld_taxes_missing_entirely_is_source_failed() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.WITHHELD_KEY] = None
    snap = _compose(treasury_frames=tf)
    r = _required(snap, "withheld_taxes")
    assert r["status"] == "ABSENT"
    level = _metric(snap, "withheld_taxes_level")
    assert level["value"] is None
    assert level["null_reason"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# auction demand: recent vs trailing-year baseline, latest passthrough
# --------------------------------------------------------------------------- #
def test_auction_demand_recent_baseline_spread() -> None:
    snap = _compose(auction_rows=_auction_rows_weakening())
    recent = _metric(snap, "auction_bid_to_cover_recent_avg")
    assert recent["value"] == pytest.approx(2.40)
    baseline = _metric(snap, "auction_bid_to_cover_baseline_avg")
    assert baseline["value"] == pytest.approx((4 * 3.00 + 8 * 2.40) / 12)  # = 2.60
    spread = _metric(snap, "auction_demand_spread_recent_vs_baseline")
    assert spread["value"] == pytest.approx(2.40 - 2.60, abs=1e-9)  # = -0.20
    assert _metric(snap, "auction_recent_window_count")["value"] == 8
    assert _metric(snap, "auction_baseline_window_count")["value"] == 12


def test_auction_latest_passthrough() -> None:
    snap = _compose(auction_rows=_auction_rows_weakening())
    assert _metric(snap, "auction_latest_bid_to_cover")["value"] == pytest.approx(2.40)
    assert _metric(snap, "auction_latest_high_yield")["value"] == pytest.approx(4.0)
    assert _metric(snap, "auction_latest_security_type")["value"] == "Note"
    assert _metric(snap, "auction_latest_tenor_years")["value"] == pytest.approx(10.0)


def test_auction_latest_can_differ_from_bid_to_cover_latest() -> None:
    # the single most recent auction lacks a reported bid_to_cover (results
    # not yet posted) -- auction_latest_* describes THAT auction, while the
    # demand-average legs fall back to the latest auction that DOES carry one.
    rows = _auction_rows_weakening() + [
        _auction("2026-09-03", "Bill", 0.25, None, 4.55)]
    snap = _compose(auction_rows=rows)
    assert _metric(snap, "auction_latest_bid_to_cover")["value"] is None
    assert _metric(snap, "auction_latest_high_yield")["value"] == pytest.approx(4.55)
    assert _metric(snap, "auction_latest_security_type")["value"] == "Bill"
    # the demand read still anchors on the last auction WITH a bid_to_cover
    recent = _metric(snap, "auction_bid_to_cover_recent_avg")
    assert recent["value"] == pytest.approx(2.40)


def test_auction_recent_window_fewer_than_target_still_computes() -> None:
    # 7 auctions total (>= _AUCTION_MIN_RECENT=5, < _AUCTION_RECENT_WINDOW=8)
    # -- computed over however many are available, disclosed via the count.
    rows = _monthly_auctions(dt.date(2026, 9, 1), [2.50] * 7)
    snap = _compose(auction_rows=rows)
    recent = _metric(snap, "auction_bid_to_cover_recent_avg")
    assert recent["value"] == pytest.approx(2.50)
    assert _metric(snap, "auction_recent_window_count")["value"] == 7
    # baseline refused: 7 < _AUCTION_MIN_BASELINE=10
    baseline = _metric(snap, "auction_bid_to_cover_baseline_avg")
    assert baseline["value"] is None
    assert baseline["null_reason"] == "INSUFFICIENT_HISTORY"
    assert _metric(snap, "auction_baseline_window_count")["value"] == 7


def test_auction_recent_window_below_floor_is_refused() -> None:
    # 3 auctions total (< _AUCTION_MIN_RECENT=5) -- refused, never a
    # fabricated average over too few observations.
    rows = _monthly_auctions(dt.date(2026, 9, 1), [2.50] * 3)
    snap = _compose(auction_rows=rows)
    recent = _metric(snap, "auction_bid_to_cover_recent_avg")
    assert recent["value"] is None
    assert recent["null_reason"] == "INSUFFICIENT_HISTORY"
    assert _metric(snap, "auction_recent_window_count")["value"] == 3


def test_auction_rows_with_no_bid_to_cover_at_all_is_source_failed() -> None:
    rows = [_auction("2026-09-01", "Bill", 0.25, None, 4.5),
            _auction("2026-08-01", "Bill", 0.25, None, 4.6)]
    snap = _compose(auction_rows=rows)
    r = _required(snap, "auction_demand")
    assert r["status"] == "ABSENT"
    assert r["freshness"] == "SOURCE_FAILED"
    recent = _metric(snap, "auction_bid_to_cover_recent_avg")
    assert recent["value"] is None
    assert recent["null_reason"] == "SOURCE_FAILED"
    # the latest-auction passthrough is unaffected (it doesn't need bid_to_cover)
    assert _metric(snap, "auction_latest_security_type")["value"] == "Bill"


def test_auctions_missing_entirely_never_crashes() -> None:
    snap = _compose(auction_rows=None)
    r = _required(snap, "auction_demand")
    assert r["status"] == "ABSENT"
    assert _metric(snap, "auction_latest_bid_to_cover")["value"] is None
    assert _metric(snap, "auction_latest_security_type")["value"] is None


# --------------------------------------------------------------------------- #
# BIS: household DSR + credit-to-GDP gap (attribution-only, quarterly)
# --------------------------------------------------------------------------- #
def test_bis_dsr_and_gap_levels() -> None:
    snap = _compose()
    dsr = _metric(snap, "household_debt_service_ratio_level")
    assert dsr["value"] == pytest.approx(14.0)
    gap = _metric(snap, "credit_gap_level")
    assert gap["value"] == pytest.approx(-1.5)


def test_bis_hand_check_2025_12_31_reads_current_at_247d_age() -> None:
    # MANDATORY hand-check: the newest possible BIS print (2025-12-31) is
    # age 247 days on 2026-09-04 and MUST read CURRENT under the 260d/30d law.
    snap = _compose()
    assert _required(snap, "bis_household_dsr")["freshness"] == "CURRENT"
    assert _required(snap, "bis_credit_gap")["freshness"] == "CURRENT"
    assert national_debt._age_days(BUILT_AT, dt.date(2025, 12, 31)) == 247


def test_bis_missing_entirely_is_source_failed_never_degrades_required() -> None:
    snap = _compose(bis_frames={})
    r = _required(snap, "bis_household_dsr")
    assert r["status"] == "ABSENT"
    assert r["freshness"] == "SOURCE_FAILED"
    assert snap["availability"]["state"] == "CURRENT"  # optional never degrades required


def test_bis_attribution_in_prose() -> None:
    snap = _compose()
    dsr = _metric(snap, "household_debt_service_ratio_level")
    assert "Bank for International Settlements" in dsr["transformation"]
    gap = _metric(snap, "credit_gap_level")
    assert "Bank for International Settlements" in gap["transformation"]
    note = _implication(snap, "bis_attribution_note")
    assert note is not None
    assert "Bank for International Settlements" in note["text"]["en"]
    assert "国际清算银行" in note["text"]["zh"]


def test_bis_source_refs_use_the_prescribed_style() -> None:
    snap = _compose()
    assert _metric(snap, "household_debt_service_ratio_level")["source_refs"] == ["BIS:us_dsr"]
    assert _metric(snap, "credit_gap_level")["source_refs"] == ["BIS:us_gap"]


# --------------------------------------------------------------------------- #
# bond desk: a small coverage-read projection
# --------------------------------------------------------------------------- #
def test_bond_desk_passthrough() -> None:
    snap = _compose()
    assert _metric(snap, "bond_desk_health_score_level")["value"] == 89
    assert _metric(snap, "bond_desk_health_label")["value"] == "healthy"
    assert _metric(snap, "bond_desk_cycle_phase")["value"] == "late"


def test_bond_desk_verdict_prose_never_republished() -> None:
    snap = _compose()
    dumped = json.dumps(snap, ensure_ascii=False)
    assert "Bond health healthy (89/100)" not in dumped
    assert "债券健康度健康" not in dumped


def test_bond_desk_missing_is_source_failed() -> None:
    snap = _compose(bonds_latest=None)
    m = _metric(snap, "bond_desk_health_label")
    assert m["value"] is None
    assert m["null_reason"] == "SOURCE_FAILED"


# --------------------------------------------------------------------------- #
# typed-ABSENT remainder: the load-bearing debt-stock gap (NOT_COVERED pins)
# --------------------------------------------------------------------------- #
_NOT_COVERED_IDS_AND_SUBSTRINGS = [
    ("debt_outstanding_total", "Debt-to-the-Penny"),
    ("debt_held_by_public", "Debt-to-the-Penny"),
    ("debt_intragovernmental_holdings", "Debt-to-the-Penny"),
    ("fiscal_deficit_primary_balance", "Monthly Treasury Statement"),
    ("net_interest_burden", "MTS"),
    ("debt_weighted_average_maturity", "MSPD"),
    ("auction_tail_bp", "auction_rows"),
    ("auction_indirect_bidder_share", "auction_rows"),
    ("foreign_holdings_tic", "TIC"),
    ("contingent_liabilities", "Contingent liabilities"),
    ("debt_to_gdp_ratio", "GDP"),
]


@pytest.mark.parametrize("metric_id,substring", _NOT_COVERED_IDS_AND_SUBSTRINGS)
def test_not_covered_debt_stock_gap_pins(metric_id, substring) -> None:
    snap = _compose()
    m = _metric(snap, metric_id)
    assert m["value"] is None
    assert m["status"] == "ABSENT"
    assert m["null_reason"] == "NOT_COVERED"
    assert m["freshness"] == "NOT_COVERED"
    assert m["rights_state"] == "OPEN"  # NOT_COVERED is not a rights issue
    assert substring in m["transformation"]


def test_not_covered_remainder_never_estimated_from_net_issuance() -> None:
    snap = _compose()
    debt_stock = _metric(snap, "debt_outstanding_total")
    assert "net_issuance" in debt_stock["transformation"] or "net-issuance" in debt_stock["transformation"]
    assert debt_stock["value"] is None


def test_not_covered_count_matches_architecture_gap_list() -> None:
    snap = _compose()
    ids = {m["metric_id"] for m in snap["metrics"]["items"]}
    expected = {mid for mid, _ in _NOT_COVERED_IDS_AND_SUBSTRINGS}
    assert expected <= ids
    not_covered_count = sum(1 for m in snap["metrics"]["items"] if m["null_reason"] == "NOT_COVERED")
    assert not_covered_count == 11


def test_debt_stock_gap_disclosure_implication_present() -> None:
    snap = _compose()
    disc = _implication(snap, "debt_stock_gap_disclosure")
    assert disc is not None
    assert "2026-09-04" in disc["text"]["en"]
    assert "Debt-to-the-Penny" in disc["text"]["en"]


# --------------------------------------------------------------------------- #
# contradiction: issuance accelerating + demand weakening + desk still "calm"
# --------------------------------------------------------------------------- #
def test_contradiction_fires_on_all_three_legs() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    snap = _compose(treasury_frames=tf, auction_rows=_auction_rows_weakening(),
                     bonds_latest=_bonds_latest_healthy())
    c = snap["availability"]["contradiction"]
    assert c["present"] is True
    assert c["kind"] == "issuance_demand_stress_vs_bond_desk_calm"
    assert set(c["components"]) == {
        "net_issuance_pace_delta_4w_vs_13w_avg_daily",
        "auction_demand_spread_recent_vs_baseline", "bond_desk_health_label",
    }
    assert any("contradiction=issuance_demand_stress_vs_bond_desk_calm" in r
               for r in snap["availability"]["reasons"])
    pace = _metric(snap, "net_issuance_pace_delta_4w_vs_13w_avg_daily")
    assert pace["status"] == "DISAGREEMENT"
    assert pace["value"] is not None  # typed disagreement, never censored
    spread = _metric(snap, "auction_demand_spread_recent_vs_baseline")
    assert spread["status"] == "DISAGREEMENT"
    label = _metric(snap, "bond_desk_health_label")
    assert label["status"] == "DISAGREEMENT"
    assert any(i["implication_id"] == "contradiction_issuance_demand_stress_vs_bond_desk_calm"
               for i in snap["implications"]["items"])


def test_contradiction_silent_when_issuance_pace_flat() -> None:
    # flat pace (baseline treasury_frames) + weakening demand + calm desk
    snap = _compose(auction_rows=_auction_rows_weakening(), bonds_latest=_bonds_latest_healthy())
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_demand_not_weakening() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    snap = _compose(treasury_frames=tf, auction_rows=_auction_rows_flat(),
                     bonds_latest=_bonds_latest_healthy())
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_bond_desk_not_healthy() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    mixed = dict(_bonds_latest_healthy(), health_label="mixed")
    snap = _compose(treasury_frames=tf, auction_rows=_auction_rows_weakening(), bonds_latest=mixed)
    assert snap["availability"]["contradiction"]["present"] is False


def test_contradiction_silent_when_any_leg_missing() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    snap = _compose(treasury_frames=tf, auction_rows=_auction_rows_weakening(), bonds_latest=None)
    assert snap["availability"]["contradiction"]["present"] is False


def test_calm_bond_desk_label_is_scoped_to_healthy_only() -> None:
    assert national_debt._CALM_BOND_DESK_LABELS == frozenset({"healthy"})


# --------------------------------------------------------------------------- #
# headline: COMPUTATION_REFUSED, NOT NOT_APPLICABLE (architecture 10.12 has a
# real two-axis blueprint, unlike monetary_policy/liquidity_central_banks)
# --------------------------------------------------------------------------- #
def test_headline_is_computation_refused_not_not_applicable() -> None:
    snap = _compose()
    h = snap["headline"]
    assert h["state_id"] is None
    assert h["status"] == "ABSENT"
    assert h["null_reason"] == "COMPUTATION_REFUSED"
    assert h["null_reason"] != "NOT_APPLICABLE"
    assert h["quadrant"] == {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"}
    assert h["nearest_boundary"]["null_reason"] == "COMPUTATION_REFUSED"
    assert h["one_month_vector"]["null_reason"] == "COMPUTATION_REFUSED"
    assert h["hysteresis"]["applied"] is False
    assert "two-axis blueprint" in h["hysteresis"]["note"]


def test_axes_items_is_empty_by_design() -> None:
    snap = _compose()
    assert snap["axes"]["items"] == []


def test_headline_refusal_is_unconditional_regardless_of_data_completeness() -> None:
    # even a fully-populated, all-CURRENT build still refuses the headline --
    # this is a data-insufficiency refusal about the MISSING debt-stock/
    # interest-burden legs, not a per-build degraded state.
    snap = _compose()
    assert snap["availability"]["state"] == "CURRENT"
    assert snap["headline"]["null_reason"] == "COMPUTATION_REFUSED"


# --------------------------------------------------------------------------- #
# cadence / release-lag freshness law (unit-level, on the shared helper)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("age_days,cadence,grace,expected", [
    (0, 5, 4, "CURRENT"),
    (5, 5, 4, "CURRENT"),
    (6, 5, 4, "LATE_WITHIN_TOLERANCE"),
    (9, 5, 4, "LATE_WITHIN_TOLERANCE"),
    (10, 5, 4, "STALE_SOURCE"),
    (0, 10, 7, "CURRENT"),
    (10, 10, 7, "CURRENT"),
    (11, 10, 7, "LATE_WITHIN_TOLERANCE"),
    (17, 10, 7, "LATE_WITHIN_TOLERANCE"),
    (18, 10, 7, "STALE_SOURCE"),
    (0, 260, 30, "CURRENT"),
    (260, 260, 30, "CURRENT"),
    (261, 260, 30, "LATE_WITHIN_TOLERANCE"),
    (290, 260, 30, "LATE_WITHIN_TOLERANCE"),
    (291, 260, 30, "STALE_SOURCE"),
    (0, 3, 3, "CURRENT"),
    (3, 3, 3, "CURRENT"),
    (4, 3, 3, "LATE_WITHIN_TOLERANCE"),
    (6, 3, 3, "LATE_WITHIN_TOLERANCE"),
    (7, 3, 3, "STALE_SOURCE"),
])
def test_cadence_freshness_tiers(age_days, cadence, grace, expected) -> None:
    asof = BUILT_DATE - dt.timedelta(days=age_days)
    got = national_debt._cadence_freshness(BUILT_AT, asof, cadence, grace, True)
    assert got == expected


def test_cadence_freshness_absent_value_is_source_failed() -> None:
    assert national_debt._cadence_freshness(BUILT_AT, BUILT_DATE, 5, 4, False) == "SOURCE_FAILED"


def test_cadence_freshness_future_asof_is_source_failed() -> None:
    future = BUILT_DATE + dt.timedelta(days=5)
    assert national_debt._cadence_freshness(BUILT_AT, future, 5, 4, True) == "SOURCE_FAILED"


def test_dts_source_constants_read_current_on_2026_09_04_disk_truth() -> None:
    # real disk-truth check: tga/net_issuance/withheld_taxes all latest
    # 2026-09-02 (age 2d) on 2026-09-04 -- must read CURRENT.
    asof = dt.date(2026, 9, 2)
    got = national_debt._cadence_freshness(
        BUILT_AT, asof, national_debt._DTS_CADENCE_DAYS, national_debt._DTS_GRACE_DAYS, True)
    assert got == "CURRENT"


def test_bonds_desk_constant_reads_current_on_2026_09_04_disk_truth() -> None:
    asof = dt.date(2026, 9, 3)  # real data/bonds/latest.json date
    got = national_debt._cadence_freshness(
        BUILT_AT, asof, national_debt._BONDS_CADENCE_DAYS, national_debt._BONDS_GRACE_DAYS, True)
    assert got == "CURRENT"


# --------------------------------------------------------------------------- #
# digest determinism (contract.py's content_digest excludes generation/build
# provenance; identical owner input -> identical digest). Includes
# genuinely-consumed-field mutations AND unconsumed-field negative controls.
# --------------------------------------------------------------------------- #
def test_digest_is_deterministic_across_identical_input() -> None:
    snap1 = contract.finalize(_compose())
    snap2 = contract.finalize(_compose())
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]
    assert snap1["generation"]["generation_id"] == snap2["generation"]["generation_id"]


def test_digest_unaffected_by_code_version() -> None:
    snap1 = contract.finalize(_compose(code_version="abc123"))
    snap2 = contract.finalize(_compose(code_version="def456"))
    assert snap1["generation"]["content_sha256"] == snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_tga_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    tf2 = _base_treasury_frames()
    tf2[national_debt.TGA_KEY] = [("2026-06-03", 500_000.0), ("2026-08-05", 600_000.0),
                                   ("2026-09-02", 999_000.0)]
    snap2 = contract.finalize(_compose(treasury_frames=tf2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_auction_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    rows2 = copy.deepcopy(_auction_rows_flat())
    rows2[-1]["bid_to_cover"] = 9.99
    snap2 = contract.finalize(_compose(auction_rows=rows2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_bis_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    bf2 = _base_bis_frames()
    bf2[national_debt.BIS_DSR_KEY] = [("2025-09-30", 13.8), ("2025-12-31", 99.0)]
    snap2 = contract.finalize(_compose(bis_frames=bf2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_changes_when_consumed_bonds_field_changes() -> None:
    snap1 = contract.finalize(_compose())
    bl2 = dict(_bonds_latest_healthy(), health_score=1)
    snap2 = contract.finalize(_compose(bonds_latest=bl2))
    assert snap1["generation"]["content_sha256"] != snap2["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_treasury_frames_key() -> None:
    snap1 = contract.finalize(_compose())
    tf3 = _base_treasury_frames()
    tf3["unrelated_series"] = [("2026-09-02", 1.0)]  # never read by this composer
    snap3 = contract.finalize(_compose(treasury_frames=tf3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_row_tuple_element() -> None:
    snap1 = contract.finalize(_compose())
    tf4 = _base_treasury_frames()
    tf4[national_debt.TGA_KEY] = [
        ("2026-06-03", 500_000.0, "unrelated-extra-field"),
        ("2026-08-05", 600_000.0, {"nested": "also unrelated"}),
        ("2026-09-02", 650_000.0, None),
    ]
    snap4 = contract.finalize(_compose(treasury_frames=tf4))
    assert snap1["generation"]["content_sha256"] == snap4["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_auction_dict_key() -> None:
    snap1 = contract.finalize(_compose())
    rows5 = copy.deepcopy(_auction_rows_flat())
    for r in rows5:
        r["cusip"] = "UNUSED12345"  # never read by this composer
    snap5 = contract.finalize(_compose(auction_rows=rows5))
    assert snap1["generation"]["content_sha256"] == snap5["generation"]["content_sha256"]


def test_digest_unaffected_by_unconsumed_bonds_verdict_text() -> None:
    snap1 = contract.finalize(_compose())
    bl3 = dict(_bonds_latest_healthy(), verdict_en="some unrelated string this composer never reads")
    snap3 = contract.finalize(_compose(bonds_latest=bl3))
    assert snap1["generation"]["content_sha256"] == snap3["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# changes / method-version comparability
# --------------------------------------------------------------------------- #
def _prior(method=national_debt.METHOD_VERSION, tga_level=650_000.0,
           gen="national_debt_liabilities-US-deadbeefdeadbeef") -> dict:
    prior = _compose()
    prior["headline"]["method_version"] = method
    prior["headline"]["effective_date"] = "2026-08-21"
    prior["generation"]["generation_id"] = gen
    for m in prior["metrics"]["items"]:
        if m["metric_id"] == "tga_level":
            m["value"] = tga_level
    return prior


def test_changes_no_prior_yields_warmup() -> None:
    snap = _compose()
    assert snap["changes"]["comparability"] == "NO_PRIOR"
    assert snap["changes"]["null_reason"] == "WARMUP"


def test_changes_method_mismatch_refuses_numeric_comparison() -> None:
    snap = _compose(prior_snapshot=_prior(method="national_debt_liabilities.compose.v0"))
    assert snap["changes"]["comparability"] == "METHOD_CHANGED"
    assert snap["changes"]["deltas"] == []
    assert snap["changes"]["null_reason"] == "COMPUTATION_REFUSED"


def test_changes_comparable_prior_produces_deltas() -> None:
    snap = _compose(prior_snapshot=_prior(tga_level=600_000.0))
    assert snap["changes"]["comparability"] == "COMPARABLE"
    ids = {d["metric_id"] for d in snap["changes"]["deltas"]}
    assert ids == set(national_debt._TRACKED_CHANGE_METRICS)
    delta = next(d for d in snap["changes"]["deltas"] if d["metric_id"] == "tga_level")
    assert delta["prior_value"] == 600_000.0
    assert delta["current_value"] == pytest.approx(650_000.0)
    assert delta["delta"] == pytest.approx(50_000.0)


# --------------------------------------------------------------------------- #
# corrections / supersession honesty
# --------------------------------------------------------------------------- #
def test_corrections_none_for_first_print() -> None:
    snap = _compose()
    assert snap["corrections"]["correction_state"] == "none"
    assert snap["corrections"]["predecessor_generation_id"] is None


def test_corrections_superseded_when_same_period_value_changes() -> None:
    tf = _base_treasury_frames()
    prior_snap = contract.finalize(national_debt.compose(
        tf, _auction_rows_flat(), _base_bis_frames(), _bonds_latest_healthy(), built_at=BUILT_AT))
    tf2 = copy.deepcopy(tf)
    tf2[national_debt.TGA_KEY][-1] = ("2026-09-02", 700_000.0)  # same asof, revised value
    snap2 = national_debt.compose(
        tf2, _auction_rows_flat(), _base_bis_frames(), _bonds_latest_healthy(),
        built_at=BUILT_AT, prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "superseded"
    assert snap2["corrections"]["changed_fingerprints"]
    assert snap2["corrections"]["predecessor_generation_id"] == prior_snap["generation"]["generation_id"]


def test_corrections_none_when_reference_period_advances() -> None:
    tf = _base_treasury_frames()
    prior_snap = contract.finalize(national_debt.compose(
        tf, _auction_rows_flat(), _base_bis_frames(), _bonds_latest_healthy(), built_at=BUILT_AT))
    tf2 = copy.deepcopy(tf)
    tf2[national_debt.TGA_KEY] = tf2[national_debt.TGA_KEY] + [("2026-09-03", 655_000.0)]
    snap2 = national_debt.compose(
        tf2, _auction_rows_flat(), _base_bis_frames(), _bonds_latest_healthy(),
        built_at="2026-09-04T12:00:00Z", prior_snapshot=prior_snap)
    assert snap2["corrections"]["correction_state"] == "none"


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_baseline_snapshot_validates_against_the_closed_contract() -> None:
    snap = contract.finalize(_compose())
    contract.validate(snap)  # raises ContractError on any violation
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    assert snap["authority"]["can_originate_signal"] is False


def test_degraded_snapshot_still_validates() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = None
    snap = contract.finalize(national_debt.compose(
        tf, _auction_rows_weakening(), {}, None, built_at=BUILT_AT))
    contract.validate(snap)


def test_contradiction_snapshot_validates() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    snap = contract.finalize(national_debt.compose(
        tf, _auction_rows_weakening(), _base_bis_frames(), _bonds_latest_healthy(), built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["contradiction"]["present"] is True


def test_all_owner_inputs_missing_still_validates() -> None:
    snap = contract.finalize(national_debt.compose(None, None, None, None, built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["availability"]["state"] == "SOURCE_FAILED"
    assert snap["availability"]["coverage_ratio"] == 0.0


# --------------------------------------------------------------------------- #
# disclosure implications present
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("iid", [
    "headline_unavailable", "debt_stock_gap_disclosure",
    "fiscal_year_windowing_disclosure", "withheld_taxes_window_divergence_disclosure",
    "bis_attribution_note", "driver_bucket_naming_note",
])
def test_disclosure_implications_present(iid) -> None:
    snap = _compose()
    assert _implication(snap, iid) is not None


def test_driver_bucket_reuse_disclosed_in_drivers_and_implication() -> None:
    snap = _compose()
    balance_sheet_ids = {d["driver_id"] for d in snap["drivers"]["balance_sheet"]}
    rate_side_ids = {d["driver_id"] for d in snap["drivers"]["rate_side"]}
    assert "tga_impulse_13w" in balance_sheet_ids
    assert "household_debt_service_ratio_level" in rate_side_ids
    assert _implication(snap, "driver_bucket_naming_note") is not None


# --------------------------------------------------------------------------- #
# metric inventory
# --------------------------------------------------------------------------- #
def test_metric_ids_are_unique_and_stable_count() -> None:
    snap = _compose()
    ids = [m["metric_id"] for m in snap["metrics"]["items"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 34


# --------------------------------------------------------------------------- #
# disclosure prose: reader language only -- never a raw closed-vocabulary
# enum token (PRESENT/SOURCE_FAILED/etc.) inside a human-readable field.
# --------------------------------------------------------------------------- #
_RAW_ENUM_TOKENS = frozenset({
    "CURRENT", "LATE_WITHIN_TOLERANCE", "STALE_SOURCE", "NOT_YET_RELEASED",
    "SOURCE_FAILED", "RIGHTS_BLOCKED", "NOT_COVERED", "HISTORICAL_AS_KNOWN", "SIMULATED",
    "UNKNOWN", "NOT_APPLICABLE", "INSUFFICIENT_HISTORY", "WARMUP",
    "REVISION_PENDING_REBUILD", "DISAGREEMENT", "COMPUTATION_REFUSED", "OUT_OF_REGION",
    "PRESENT", "PARTIAL", "ABSENT",
})
_PROSE_KEYS = ("en", "zh", "note", "transformation")


def _find_raw_token_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _PROSE_KEYS and isinstance(v, str):
                for tok in _RAW_ENUM_TOKENS:
                    if tok in v:
                        leaks.append((f"{path}.{k}", tok, v))
            leaks.extend(_find_raw_token_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_raw_token_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_prose_fields_contain_no_raw_enum_tokens() -> None:
    # exercise every disclosure branch at once: contradiction fired, a
    # required leg missing, the typed-absent remainder always present.
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    tf[national_debt.WITHHELD_KEY] = None
    snap = _compose(treasury_frames=tf, auction_rows=_auction_rows_weakening(),
                     bonds_latest=_bonds_latest_healthy())
    leaks = _find_raw_token_leaks(snap)
    assert leaks == [], f"raw enum tokens leaked into prose field(s): {leaks}"


# --------------------------------------------------------------------------- #
# zh-label integrity: composer-authored English phrasing must never leak into
# the composer-authored zh sibling
# --------------------------------------------------------------------------- #
_COMPOSER_ENGLISH_PHRASES = (
    "This composer", "never rebranded", "a supply/demand stress signal",
    "cosmetic bucket reuse", "never ffill a flow", "load-bearing",
    "the desk has not itself flagged",
)


def _find_english_leaks(node, path: str = "$") -> list[tuple[str, str, str]]:
    leaks: list[tuple[str, str, str]] = []
    if isinstance(node, dict):
        zh = node.get("zh")
        if "en" in node and isinstance(zh, str):
            for phrase in _COMPOSER_ENGLISH_PHRASES:
                if phrase in zh:
                    leaks.append((path, phrase, zh))
        for k, v in node.items():
            leaks.extend(_find_english_leaks(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            leaks.extend(_find_english_leaks(v, f"{path}[{idx}]"))
    return leaks


def test_zh_narrative_never_embeds_composer_english_phrasing() -> None:
    tf = _base_treasury_frames()
    tf[national_debt.NET_ISSUANCE_KEY] = _net_issuance_rows_accelerating()
    snap = _compose(treasury_frames=tf, auction_rows=_auction_rows_weakening(),
                     bonds_latest=_bonds_latest_healthy())
    leaks = _find_english_leaks(snap)
    assert leaks == [], f"English phrasing leaked into zh field(s): {leaks}"


def test_zh_narrative_present_wherever_english_is_composer_authored() -> None:
    snap = _compose()
    for impl in snap["implications"]["items"]:
        assert impl["text"]["en"], impl
        assert impl["text"]["zh"], impl
    assert snap["workspace"]["title"]["zh"]
    assert snap["headline"]["subtitle"]["zh"]


# --------------------------------------------------------------------------- #
# real owner artifact (data/bonds/latest.json) -- skipped where absent, never
# fabricated. treasury/auction/BIS inputs stay synthetic (composed from
# parquet in build.py, not readable by this test suite directly).
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not BONDS_LATEST.exists(), reason="real bonds_latest owner artifact is absent")
def test_builds_and_validates_with_the_real_bonds_desk_artifact() -> None:
    bonds_latest = json.loads(BONDS_LATEST.read_text(encoding="utf-8"))
    snap = contract.finalize(national_debt.compose(
        _base_treasury_frames(), _auction_rows_flat(), _base_bis_frames(), bonds_latest,
        built_at=BUILT_AT))
    contract.validate(snap)
    assert snap["headline"]["state_id"] is None
    assert snap["axes"]["items"] == []
    assert snap["authority"]["can_size"] is False
    assert snap["authority"]["can_execute"] is False
    health_label_metric = _metric(snap, "bond_desk_health_label")
    assert health_label_metric["value"] == bonds_latest.get("health_label")
    # this composer never republishes the owner's own editorial verdict text
    dumped = json.dumps(snap, ensure_ascii=False)
    if bonds_latest.get("verdict_en"):
        assert bonds_latest["verdict_en"] not in dumped
