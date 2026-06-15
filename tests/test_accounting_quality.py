"""Accounting-quality read (engine/stock_fundamentals.py :: _accounting_quality).

A DISPLAY-ONLY context chip on the single-stock page that composes the
cross-sectional accruals / profitability / investment / payout factor z-scores
(all oriented HIGH = good) with single-period ratios and — where the companyfacts
collector has run — multi-year trends, into a clean / watch / warning verdict.

These tests pin the verdict logic, the accruals SIGN convention (a recurring trap:
a HIGH accruals factor-z means LOW accruals = good, while a RISING (ni-cfo)/assets
trend means deteriorating), graceful degradation when inputs are thin, and the
load-bearing honesty invariant: the read must NEVER feed a scored output.
"""
from __future__ import annotations

from lib import config
from engine import stock_fundamentals as sf
from engine.stock_fundamentals import _accounting_quality, _aq_accruals_series


# ---- builders ---------------------------------------------------------------
def _rows(accruals_path, gross_margin=None, shares=None):
    """Per-FY statement rows realising a given (ni-cfo)/assets path. assets fixed
    at 1000 so accruals_t == (ni - cfo) / 1000; ni fixed, cfo backed out."""
    n = len(accruals_path)
    gm = gross_margin or [40.0] * n
    sh = shares or [100.0] * n
    out = []
    for i, acc in enumerate(accruals_path):
        ni = 100.0
        cfo = ni - acc * 1000.0           # acc = (ni - cfo)/assets  ->  cfo = ni - acc*assets
        out.append({"fy": 2020 + i, "ni": ni, "cfo": cfo, "assets": 1000.0,
                    "revenue": 1000.0, "gross_profit": gm[i] * 10.0, "shares": sh[i]})
    return out


def _states(aq):
    return {r["key"]: r["state"] for r in aq["reads"]}


# ---- verdict thresholds -----------------------------------------------------
def test_clean_when_everything_good():
    fac = {"accruals": 0.8, "profitability": 0.9, "investment": 0.6, "payout": 0.3}
    fin = {"raw": {"cfo": 120, "ni": 100}, "accruals": -0.01, "asset_growth": 5.0,
           "gross_margin": 45, "debt_to_assets": 20}
    aq = _accounting_quality(fac, fin, None, None)
    assert aq["verdict"] == "clean"
    assert aq["n_caution"] == 0
    st = _states(aq)
    assert st["earnings_quality"] == "good" and st["pricing_power"] == "good"
    # no companyfacts trend -> honest "latest filing" basis
    assert aq["basis"] == "latest filing + peer ranks"


def test_warn_on_deterioration_stack():
    """Rising accruals + margin compression + dilution + grey Altman -> warning,
    and the flagship multi-year copy is produced verbatim."""
    rows = _rows([0.0, 0.01, 0.025, 0.05], gross_margin=[40.0, 39.1, 36.0, 33.6],
                 shares=[100, 104, 110, 118])
    my = {"gross_margin": [40.0, 39.1, 36.0, 33.6],
          "altman": {"z": 2.1, "zone": "grey"}, "piotroski": {"score": 3, "of": 9}}
    fin = {"raw": {"cfo": 80, "ni": 130}, "accruals": 0.05, "asset_growth": 23.0,
           "gross_margin": 33.6, "debt_to_assets": 35}
    fac = {"accruals": -0.9, "profitability": -0.7, "investment": -0.8, "payout": -0.2}
    aq = _accounting_quality(fac, fin, my, rows)
    assert aq["verdict"] == "warn"
    assert aq["n_caution"] >= 2
    assert aq["basis"] == "multi-year trend + peer ranks"
    eq = next(r for r in aq["reads"] if r["key"] == "earnings_quality")
    assert eq["state"] == "caution"
    assert eq["detail"] == "accruals trending up over 4 fiscal years — earnings increasingly not cash-backed"
    cap = next(r for r in aq["reads"] if r["key"] == "capital_discipline")
    assert "dilution" in cap["detail"]


def test_single_isolated_caution_stays_clean():
    # one flag among up to 5 relative reads is the modal state -> still broadly clean
    # (the breakdown still surfaces the caution; only 2+ concerns escalate to watch)
    fac = {"accruals": -0.9, "profitability": 0.2, "investment": 0.1, "payout": 0.0}
    fin = {"raw": {"cfo": 90, "ni": 100}, "accruals": 0.02, "asset_growth": 8.0,
           "gross_margin": 30, "debt_to_assets": 25}
    aq = _accounting_quality(fac, fin, None, None)
    assert aq["n_caution"] == 1 and aq["verdict"] == "clean"
    assert _states(aq)["earnings_quality"] == "caution"


# ---- sign convention (the trap) --------------------------------------------
def test_high_accruals_factor_z_reads_good():
    """HIGH accruals factor-z == LOW accruals == cash-backed earnings == good."""
    fac = {"accruals": 1.2}
    fin = {"raw": {"cfo": 130, "ni": 100}, "accruals": -0.03, "debt_to_assets": 15}
    aq = _accounting_quality(fac, fin, None, None)
    assert _states(aq)["earnings_quality"] == "good"


def test_rising_accruals_trend_reads_caution_without_factor_z():
    """A deteriorating (ni-cfo)/assets PATH must flag caution on its own, even when
    the cross-sectional factor-z is absent — proving the trend path, not just the z."""
    rows = _rows([0.0, 0.02, 0.04, 0.06])
    fin = {"raw": {"cfo": 40, "ni": 100}, "accruals": 0.06, "debt_to_assets": 20}
    aq = _accounting_quality({}, fin, None, rows)
    eq = next(r for r in aq["reads"] if r["key"] == "earnings_quality")
    assert eq["state"] == "caution"
    assert "trending up" in eq["detail"]


def test_falling_accruals_trend_reads_good():
    rows = _rows([0.06, 0.04, 0.02, 0.0])
    fin = {"raw": {"cfo": 100, "ni": 100}, "accruals": 0.0, "debt_to_assets": 20}
    aq = _accounting_quality({}, fin, None, rows)
    assert _states(aq)["earnings_quality"] == "good"


# ---- corroborator + severe combo -------------------------------------------
def test_piotroski_can_only_downgrade_a_clean_read():
    fac = {"accruals": 0.8, "profitability": 0.9, "investment": 0.6, "payout": 0.3}
    fin = {"raw": {"cfo": 120, "ni": 100}, "accruals": -0.01, "asset_growth": 5.0,
           "gross_margin": 45, "debt_to_assets": 20}
    clean = _accounting_quality(fac, fin, {"piotroski": {"score": 8, "of": 9}}, None)
    assert clean["verdict"] == "clean"          # strong F-score does not inflate
    weak = _accounting_quality(fac, fin, {"piotroski": {"score": 2, "of": 9}}, None)
    assert weak["verdict"] == "watch"           # weak F-score downgrades clean -> watch


def test_altman_distress_flags_balance_sheet():
    fin = {"raw": {"cfo": 100, "ni": 100}, "accruals": 0.0, "debt_to_assets": 30}
    aq = _accounting_quality({"accruals": 0.2}, fin,
                             {"altman": {"z": 1.2, "zone": "distress"}}, None)
    bs = next(r for r in aq["reads"] if r["key"] == "balance_sheet")
    assert bs["state"] == "caution" and "distress" in bs["detail"]


# ---- graceful degradation ---------------------------------------------------
def test_none_when_nothing_computable():
    assert _accounting_quality(None, None, None, None) is None


def test_none_when_below_min_reads():
    # only the earnings-quality read is computable -> 1 < min_reads (2) -> hidden
    assert _accounting_quality({"accruals": 0.1}, None, None, None) is None


def test_missing_fields_never_raise():
    assert _accounting_quality({}, {"raw": {}}, {}, []) is None
    # weird/None-laden rows must be skipped, not crash
    assert _aq_accruals_series([{"fy": 2020, "ni": None, "cfo": 1, "assets": 10}]) == []
    assert _aq_accruals_series([{"fy": 2020, "ni": 5, "cfo": 1, "assets": 0}]) == []  # zero assets
    aq = _accounting_quality({"accruals": -0.9, "profitability": -0.8}, {"raw": {}}, None, None)
    assert aq is not None and aq["verdict"] in ("watch", "warn")


def test_read_shape_is_well_formed():
    aq = _accounting_quality({"accruals": -0.9, "profitability": -0.8, "investment": -0.8},
                             {"raw": {"cfo": 1, "ni": 2}, "asset_growth": 60.0, "debt_to_assets": 70},
                             None, None)
    for r in aq["reads"]:
        assert set(r) >= {"key", "label", "label_zh", "state", "detail", "detail_zh"}
        assert r["state"] in ("good", "neutral", "caution")
    assert {"verdict", "headline", "headline_zh", "reads", "caveat", "caveat_zh"} <= set(aq)


# ---- working-capital read (v2: inventory / receivables vs sales) ------------
def _wc_rows(inv, recv, rev):
    """Statement rows carrying inventory / receivables / revenue series (equal len)."""
    return [{"fy": 2020 + i, "inventory": inv[i], "receivables": recv[i], "revenue": rev[i]}
            for i in range(len(rev))]


def test_working_capital_inventory_building_flags_demand():
    rows = _wc_rows(inv=[100, 120, 150, 185], recv=[40, 40, 41, 42], rev=[100, 104, 108, 112])
    aq = _accounting_quality({"profitability": 0.2}, {"raw": {}}, None, rows)
    wc = next(r for r in aq["reads"] if r["key"] == "working_capital")
    assert wc["state"] == "caution"
    assert "inventory" in wc["detail"] and "demand" in wc["detail"]


def test_working_capital_receivables_stretch_flags_revenue_quality():
    rows = _wc_rows(inv=[100, 101, 102, 103], recv=[50, 70, 95, 130], rev=[100, 104, 108, 112])
    aq = _accounting_quality({"profitability": 0.2}, {"raw": {}}, None, rows)
    wc = next(r for r in aq["reads"] if r["key"] == "working_capital")
    assert wc["state"] == "caution"
    assert "receivables" in wc["detail"] and "revenue-quality" in wc["detail"]


def test_working_capital_lean_reads_good():
    rows = _wc_rows(inv=[100, 98, 96, 94], recv=[50, 48, 46, 44], rev=[100, 115, 130, 150])
    aq = _accounting_quality({"profitability": 0.2}, {"raw": {}}, None, rows)
    wc = next(r for r in aq["reads"] if r["key"] == "working_capital")
    assert wc["state"] == "good"


def test_working_capital_absent_without_line_items():
    # pre-seed names (and banks with no inventory/receivables tags) just hide the read
    rows = [{"fy": 2020 + i, "ni": 100, "cfo": 100, "assets": 1000, "revenue": 1000} for i in range(4)]
    aq = _accounting_quality({"profitability": 0.2}, {"raw": {"cfo": 100, "ni": 100}}, None, rows)
    assert aq is not None and all(r["key"] != "working_capital" for r in aq["reads"])


def test_accrual_cluster_dedup_prevents_overwarn():
    # earnings_quality (aggregate accruals) + working_capital (the line items that drive
    # them) are ONE phenomenon. Here 3 reads flag (accruals + working-capital + pricing),
    # but the accrual pair de-dupes to one -> 2 effective cautions -> watch, NOT warn.
    rows = [{"fy": 2020 + i, "ni": 100, "cfo": 100 - 20 * i, "assets": 1000,
             "inventory": [100, 150, 200, 260][i], "receivables": [40, 40, 41, 42][i],
             "revenue": [100, 104, 108, 112][i]} for i in range(4)]
    aq = _accounting_quality({"profitability": -0.9},
                             {"raw": {"cfo": 40, "ni": 100}, "accruals": 0.06}, None, rows)
    st = {r["key"]: r["state"] for r in aq["reads"]}
    assert st["earnings_quality"] == "caution" and st["working_capital"] == "caution" \
        and st["pricing_power"] == "caution"
    assert aq["verdict"] == "watch"   # 3 raw cautions, accrual pair de-duped -> 2 -> watch


# ---- honesty invariant: DISPLAY-ONLY, never scored --------------------------
def test_invariant_not_consumed_by_the_scorer():
    """Load-bearing: the scored factor pipeline must never reference the read. If a
    future change wires accounting_quality into scoring, this fails loudly."""
    scorer = (config.ROOT / "engine" / "equity_factors.py").read_text()
    assert "accounting_quality" not in scorer
    assert "_accounting_quality" not in scorer
    # and it is not one of the cross-sectional factor legs / radar axes
    assert "accounting_quality" not in sf.RADAR_AXES
