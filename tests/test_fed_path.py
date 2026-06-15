"""Pure-function tests for the Fed policy-path leaf + ZQ/SR3 collector — no network.

The live fetch (Yahoo ZQ/SR3, FRED FEDTARMD) throttles the sandbox, so these drive
the deterministic math on synthetic prices/dots — the global-liquidity playbook.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import rate_futures as rf  # noqa: E402
from engine import fed_path as fp  # noqa: E402

_CFG = {"horizons_m": [1, 3, 6, 12], "max_months": 18}


# --------------------------------------------------------------------------- #
# collector: contract generation
# --------------------------------------------------------------------------- #
def test_gen_contracts_monthly_rolls_off_asof():
    cs = rf.gen_contracts("ZQ", ["CBT"], "monthly", 14, date(2026, 6, 12))
    assert len(cs) == 14
    # first contract = the run month; symbol uses the CME month code
    assert (cs[0]["year"], cs[0]["month"]) == (2026, 6)
    assert cs[0]["symbols"][0] == "ZQM26.CBT"   # M = June
    # consecutive months, wrapping the year
    assert (cs[7]["year"], cs[7]["month"]) == (2027, 1)
    assert cs[7]["symbols"][0] == "ZQF27.CBT"   # F = January


def test_gen_contracts_quarterly_imm_only():
    qs = rf.gen_contracts("SR3", ["CME"], "quarterly", 4, date(2026, 6, 12))
    months = [(c["year"], c["month"]) for c in qs]
    assert months == [(2026, 6), (2026, 9), (2026, 12), (2027, 3)]
    assert all(c["month"] in (3, 6, 9, 12) for c in qs)


def test_gen_contracts_multiple_exchange_candidates():
    cs = rf.gen_contracts("ZQ", ["CBT", "NYB"], "monthly", 1, date(2026, 6, 1))
    assert cs[0]["symbols"] == ["ZQM26.CBT", "ZQM26.NYB"]


# --------------------------------------------------------------------------- #
# collector: implied-path interpolation
# --------------------------------------------------------------------------- #
def _synthetic_strip(asof: date, n: int, cut_per_month: float):
    """Monthly ZQ strip that prices `cut_per_month` of cuts each month from 4.33%."""
    idx = pd.bdate_range("2026-05-15", "2026-06-12")
    cs = rf.gen_contracts("ZQ", ["CBT"], "monthly", n, asof)
    out = {}
    for c in cs:
        ma = rf._months_diff(c["year"], c["month"], asof.year, asof.month)
        rate = 4.33 - cut_per_month * ma
        out[(c["year"], c["month"])] = pd.Series(100.0 - rate, index=idx)
    return out


def test_implied_path_interpolates_to_horizons():
    strip = _synthetic_strip(date(2026, 6, 12), 14, 0.10)
    path = rf.implied_path(strip, [1, 3, 6, 12], 18, "monthly")
    assert list(path.columns) == ["m1", "m3", "m6", "m12"]
    row = path.iloc[-1]
    # monthly centre offset 0.5 → horizon h maps to rate 4.33 − 0.10*(h−0.5)
    assert abs(row["m1"] - (4.33 - 0.10 * 0.5)) < 1e-6
    assert abs(row["m12"] - (4.33 - 0.10 * 11.5)) < 1e-6
    # monotone decreasing as the market prices steady cuts
    assert row["m1"] > row["m3"] > row["m6"] > row["m12"]


def test_implied_path_never_extrapolates_beyond_strip():
    # only 2 monthly contracts → strip spans ~0.5..1.5 months; 6m/12m must be None
    strip = _synthetic_strip(date(2026, 6, 12), 2, 0.10)
    path = rf.implied_path(strip, [1, 3, 6, 12], 18, "monthly")
    row = path.iloc[-1]
    assert row["m1"] is not None
    assert pd.isna(row.get("m6")) or row.get("m6") is None
    assert pd.isna(row.get("m12")) or row.get("m12") is None


def test_implied_path_empty_input():
    assert rf.implied_path({}, [1, 3], 18, "monthly").empty


# --------------------------------------------------------------------------- #
# engine: dot-plot parsing
# --------------------------------------------------------------------------- #
def test_dots_by_year_keeps_forward_and_latest_write():
    s = pd.Series({
        pd.Timestamp("2024-12-31"): 4.50,   # past year — dropped
        pd.Timestamp("2026-12-31"): 3.90,
        pd.Timestamp("2027-12-31"): 3.40,
    })
    dots = fp._dots_by_year(s, 2026)
    assert [d["year"] for d in dots] == [2026, 2027]
    assert dots[0]["median"] == 3.9


def test_dots_by_year_none_and_empty():
    assert fp._dots_by_year(None, 2026) == []
    assert fp._dots_by_year(pd.Series(dtype=float), 2026) == []


# --------------------------------------------------------------------------- #
# engine: the lean classifier
# --------------------------------------------------------------------------- #
def test_lean_thresholds():
    assert fp._lean(4)[0] == "market ≈ the Fed"      # < half a 25bp move
    assert fp._lean(-40)[0] == "market more dovish than the Fed"
    assert fp._lean(40)[0] == "market more hawkish than the Fed"
    assert fp._lean(None)[0] == "—"


# --------------------------------------------------------------------------- #
# engine: compute()
# --------------------------------------------------------------------------- #
def _dots():
    return pd.Series({pd.Timestamp("2026-12-31"): 3.875,
                      pd.Timestamp("2027-12-31"): 3.375})


def test_compute_full_path_and_gap():
    zq = {"m1": 4.30, "m3": 4.12, "m6": 3.92, "m12": 3.55}
    out = fp.compute(asof=pd.Timestamp("2026-06-12"), policy_rate=4.33,
                     target_low=4.25, target_high=4.50, dot_series=_dots(),
                     zq_path_row=zq, sofr_path_row=None, zq_front_implied=4.31,
                     ntfs=-0.42, curve_tp_adj=-0.15, rate_exp_proxy=-0.55, cfg=_CFG)
    assert out["target_mid"] == 4.38
    assert out["implied"]["m12"] == 3.55
    # (4.33 − 3.55) / 0.25 ≈ 3 cuts
    assert out["implied_cuts_12m"] == 3
    assert out["implied_bp_12m"] == -78
    # gap at end-2026 (June→Dec = 6m) compares the 6m-implied to the 2026 dot
    assert out["gap"]["horizon_label"] == "end-2026"
    assert out["gap"]["horizon_months"] == 6
    assert out["gap"]["market"] == 3.92
    assert out["gap"]["fed_dot"] == 3.875
    assert out["gap"]["gap_bp"] == 4
    assert out["gap"]["lean_en"] == "market ≈ the Fed"
    assert out["implied_source_en"] == "ZQ fed-funds futures"
    # display-only contract — no scored leg should ever appear
    assert "score" not in out and "mrs" not in out


def test_compute_prefers_zq_then_sofr():
    sofr = {"m1": 4.25, "m12": 3.40}
    out = fp.compute(asof=pd.Timestamp("2026-06-12"), policy_rate=4.33,
                     target_low=4.25, target_high=4.50, dot_series=None,
                     zq_path_row=None, sofr_path_row=sofr, zq_front_implied=4.31,
                     ntfs=None, curve_tp_adj=None, rate_exp_proxy=None, cfg=_CFG)
    assert out["implied_source_en"] == "SR3 SOFR futures"
    assert out["implied"]["m12"] == 3.40


def test_compute_degraded_no_strip_no_dots():
    out = fp.compute(asof=pd.Timestamp("2026-06-12"), policy_rate=4.33,
                     target_low=4.25, target_high=4.50, dot_series=None,
                     zq_path_row=None, sofr_path_row=None, zq_front_implied=4.31,
                     ntfs=-0.2, curve_tp_adj=None, rate_exp_proxy=-0.5, cfg=_CFG)
    assert out["implied_source_en"] == "ZQ front (30d) only"
    assert out["implied"].get("m1") == 4.31
    # no far horizon → no fabricated cut count, no gap
    assert out["implied_cuts_12m"] is None
    assert out["gap"] is None
    assert out["dots"] == []
    assert out["headline_en"].startswith("Policy set at")


def test_compute_far_dot_shows_dots_but_no_gap():
    # a single 2028 dot is >12m out → cannot compare against the 12m strip
    out = fp.compute(asof=pd.Timestamp("2026-06-12"), policy_rate=4.33,
                     target_low=4.25, target_high=4.50,
                     dot_series=pd.Series({pd.Timestamp("2028-12-31"): 3.0}),
                     zq_path_row={"m1": 4.3, "m12": 3.6}, sofr_path_row=None,
                     zq_front_implied=4.3, ntfs=0.1, curve_tp_adj=0.0,
                     rate_exp_proxy=0.0, cfg=_CFG)
    assert out["gap"] is None
    assert [d["year"] for d in out["dots"]] == [2028]


def test_compute_all_empty_returns_none():
    assert fp.compute(asof=pd.Timestamp("2026-06-12"), policy_rate=None,
                      target_low=None, target_high=None, dot_series=None,
                      zq_path_row=None, sofr_path_row=None, zq_front_implied=None,
                      ntfs=None, curve_tp_adj=None, rate_exp_proxy=None, cfg=_CFG) is None
