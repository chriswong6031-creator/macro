"""Acceptance tests for engine.china_sector_cycles_grader — the forward-log grader that
closes the CN cycles falsifiability loop. Five pinned criteria:

  1. LOOK-AHEAD-FREE: forward windows anchor at the FIRST close STRICTLY AFTER the stamp
     date (bar i+1); the tainted marker-date variant computes a DIFFERENT number and the
     grader REFUSES the tainted convention outright (the engine/signal_quality.py trap —
     +5.7pp/10d of leak from marker-date grading; see tests/test_signal_quality_no_leak.py).
  2. PIT-JOIN INTEGRITY: keep-first per (date, id); no partial windows; a stamp with no
     realized future bars is pending, never graded.
  3. HONEST NULLS: the return channel's expected-null is a first-class output.
  4. VERDICT GATING: below MIN_EARN_N -> "accruing", full stop; the drawdown channel earns
     only on a zero-excluding CI; the return/calibration channels can NEVER earn.
  5. NO POINT FORECASTS: display copy stays conditional, context-only.
"""
import numpy as np
import pandas as pd
import pytest

from engine import china_sector_cycles_grader as g


# ------------------------------------------------------------------ fixtures ----

def _series(vals, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series([float(v) for v in vals], index=idx)


def _rising(n, start="2024-01-01"):
    return _series(100.0 * (1.005 ** np.arange(n)), start)


def _falling(n, start="2024-01-01"):
    return _series(100.0 * (0.99 ** np.arange(n)), start)


def _flat(n, start="2024-01-01"):
    return _series(np.full(n, 100.0), start)


def _row(date, sid, **kw):
    base = {"date": date, "id": sid, "kind": "sector", "name": sid, "phase": "Expansion",
            "pos": 50.0, "osc_slope": 0.0, "signature": 50.0, "signal": None,
            "above200d": True, "rs_63d": 0.0, "rs_rank": 1,
            "proj_next": None, "proj_central": None}
    base.update(kw)
    return base


def _stamp_dates(cal, lo, hi):
    return [str(cal[i].date()) for i in range(lo, hi)]


N_BARS = 200
CAL = pd.bdate_range("2024-01-01", periods=N_BARS)


# ============================================================ 1 · LOOK-AHEAD-FREE ----

def test_forward_anchor_is_first_close_strictly_after_stamp_and_differs_from_tainted():
    """A +20% gap on the bar AFTER the stamp must NOT be credited to the stamp. The
    strict bar-i+1 anchor yields 0%; the tainted marker-date anchor yields +20% — the
    exact leak signal_quality's marker-date grading embedded."""
    k, h = 50, 5
    vals = np.full(120, 100.0)
    vals[k + 1:] = 120.0                      # the jump lands on bar k+1
    px = _series(vals)
    stamp = px.index[k]                       # stamp ON bar k (a settled close)

    w = g._fwd(px, stamp, h)
    assert w is not None
    assert w["entry"] > stamp, "entry must be STRICTLY after the stamp date"
    assert w["entry"] == px.index[k + 1]
    assert w["ret"] == pytest.approx(0.0, abs=1e-12)

    # the TAINTED variant (marker-date anchor, bar i) — computed locally, never by the grader
    j0 = int(px.index.searchsorted(stamp, side="left"))
    tainted_ret = float(px.iloc[j0 + h] / px.iloc[j0] - 1.0)
    assert tainted_ret == pytest.approx(0.20, abs=1e-12)
    assert w["ret"] != tainted_ret, "strict and tainted conventions must differ on this tape"


def test_weekend_stamp_anchors_on_next_trading_bar():
    px = _flat(60)
    saturday = px.index[10] + pd.Timedelta(days=5 - px.index[10].weekday())  # that week's Sat
    w = g._fwd(px, saturday, 5)
    assert w is not None and w["entry"] > saturday
    assert w["entry"].weekday() < 5


def test_grader_refuses_the_tainted_convention():
    log = pd.DataFrame([_row("2024-03-01", "801001")])
    prices = {"801001": _flat(100)}
    for bad in ("stamp_date", "marker_date", ""):
        with pytest.raises(ValueError, match="look-ahead"):
            g.grade(log, prices, None, convention=bad)


# ======================================================== 2 · PIT-JOIN INTEGRITY ----

def test_keep_first_per_date_id_and_pending_never_graded():
    px = _falling(N_BARS)
    d = str(CAL[50].date())
    log = pd.DataFrame([
        _row(d, "801001", phase="Peak"),               # the FIRST stamp — must win
        _row(d, "801001", phase="Recovery"),           # later duplicate — must be dropped
        _row(str(CAL[-1].date()), "801001", phase="Peak"),   # stamp on the LAST bar: 0 future bars
        _row("2030-01-01", "801001", phase="Peak"),    # future stamp: nothing realized
    ])
    card = g.grade(log, {"801001": px}, None)
    dd = card["channels"]["drawdown"]["states"]
    assert dd["phase_peak"]["21"]["n_matured"] == 1          # keep-first kept the Peak stamp
    ret = card["channels"]["return"]["states"]
    assert ret["phase_recovery"]["21"]["n_matured"] == 0     # the duplicate never graded
    assert ret["phase_recovery"]["21"]["n_pending"] == 0
    assert dd["phase_peak"]["21"]["n_pending"] == 2          # last-bar + future stamps pend
    assert card["log"]["n_rows"] == 3                        # de-duped ledger size


def test_partial_windows_are_pending_not_graded():
    px = _flat(N_BARS)
    d = str(CAL[N_BARS - 10].date())                          # only 9 future bars < h=21
    log = pd.DataFrame([_row(d, "801001", phase="Peak")])
    card = g.grade(log, {"801001": px}, None)
    cell = card["channels"]["drawdown"]["states"]["phase_peak"]["21"]
    assert cell["n_matured"] == 0 and cell["n_pending"] == 1
    assert cell["verdict"] == "accruing"


# ============================================================= 3 · HONEST NULLS ----

def _coinflip_setup(n_dates=30, n_ids_side=10):
    """600 matured Recovery stamps whose forward SHCOMP-relative returns are exactly
    half positive / half negative — the Phase-0 coin-flip null, realized."""
    prices, rows = {}, []
    bench = _flat(N_BARS)
    for k in range(n_ids_side):
        prices[f"up{k}"] = _rising(N_BARS)
        prices[f"dn{k}"] = _falling(N_BARS)
    for d in _stamp_dates(CAL, 40, 40 + n_dates):
        for sid in prices:
            rows.append(_row(d, sid, phase="Recovery"))
    return pd.DataFrame(rows), prices, bench


def test_return_null_is_first_class_and_coinflip_falsifies():
    log, prices, bench = _coinflip_setup()
    card = g.grade(log, prices, bench)
    nul = card["return_null"]
    assert nul["expected"] is True
    assert "0/152" in nul["prior_en"]                       # the Phase-0 prior, stated
    cell = card["channels"]["return"]["states"]["phase_recovery"]["21"]
    assert cell["n_matured"] == 600
    assert cell["cond_rate"] == pytest.approx(0.5, abs=0.01)
    # Wilson CI at n=600 rules out even base+5pp -> the directional claim is FALSIFIED
    assert cell["verdict"] == "falsified"
    assert "phase_recovery" in nul["status_en"]             # reported, never hidden


def test_return_null_status_reports_accruing_when_nothing_matured():
    px = _flat(N_BARS)
    log = pd.DataFrame([_row(str(CAL[-1].date()), "801001", phase="Recovery")])
    card = g.grade(log, {"801001": px}, _flat(N_BARS))
    assert "accruing" in card["return_null"]["status_en"]


# ============================================================ 4 · VERDICT GATING ----

def test_below_min_n_is_accruing_full_stop_even_with_a_monster_effect():
    """10 matured Peak stamps with catastrophic forward drawdowns: still 'accruing'."""
    prices = {"801001": _falling(N_BARS)}
    rows = [_row(d, "801001", phase="Peak") for d in _stamp_dates(CAL, 40, 50)]
    card = g.grade(pd.DataFrame(rows), prices, None)
    cell = card["channels"]["drawdown"]["states"]["phase_peak"]["21"]
    assert cell["n_matured"] == 10 < g.MIN_EARN_N
    assert cell["cond_mean_maxdd"] < -0.15                   # the effect is enormous...
    assert cell["verdict"] == "accruing"                     # ...and the verdict ignores it


def _two_id_setup(peak_series, other_series, n_dates=60):
    prices = {"801001": peak_series, "801002": other_series}
    rows = []
    for d in _stamp_dates(CAL, 40, 40 + n_dates):
        rows.append(_row(d, "801001", phase="Peak"))
        rows.append(_row(d, "801002", phase="Expansion"))
    return pd.DataFrame(rows), prices


def test_drawdown_channel_earns_only_on_zero_excluding_ci():
    log, prices = _two_id_setup(_falling(N_BARS), _rising(N_BARS))
    card = g.grade(log, prices, None)
    cell = card["channels"]["drawdown"]["states"]["phase_peak"]["21"]
    assert cell["n_matured"] == 60 >= g.MIN_EARN_N
    assert cell["effect"] < 0 and cell["ci"][1] < 0          # conditional strictly deeper
    assert cell["verdict"] == "earning"
    assert card["channels"]["drawdown"]["sizing_eligible"] is True


def test_drawdown_channel_falsifies_when_conditional_is_shallower():
    log, prices = _two_id_setup(_rising(N_BARS), _falling(N_BARS))   # Peak stamps ride the calm tape
    card = g.grade(log, prices, None)
    cell = card["channels"]["drawdown"]["states"]["phase_peak"]["21"]
    assert cell["n_matured"] == 60
    assert cell["effect"] > 0 and cell["ci"][0] > 0          # strictly SHALLOWER than base
    assert cell["verdict"] == "falsified"


def test_return_channel_can_never_earn_even_when_the_ci_clears():
    """60 Recovery stamps that ALL beat the benchmark: doctrine caps the verdict at
    'inconclusive' — this grader never emits a directional trading verdict."""
    prices = {"win": _rising(N_BARS), "801099": _falling(N_BARS)}
    rows = []
    for d in _stamp_dates(CAL, 40, 100):
        rows.append(_row(d, "win", phase="Recovery"))
        rows.append(_row(d, "801099", phase="Expansion"))    # dilutes the base rate to ~0.5
    card = g.grade(pd.DataFrame(rows), prices, _flat(N_BARS))
    cell = card["channels"]["return"]["states"]["phase_recovery"]["21"]
    assert cell["n_matured"] == 60 and cell["cond_rate"] == 1.0
    assert cell["ci"][0] > cell["base_rate"] + g.RETURN_MIN_EDGE   # the CI clears, and yet:
    assert cell["verdict"] == "inconclusive"
    assert card["channels"]["return"]["sizing_eligible"] is False


def test_calibration_hit_rate_brier_and_gating():
    prices = {"801001": _rising(N_BARS)}
    good = [_row(d, "801001", proj_next="peak") for d in _stamp_dates(CAL, 40, 100)]
    card = g.grade(pd.DataFrame(good), prices, None)
    cell = card["channels"]["calibration"]["states"]["proj_peak"]["21"]
    assert cell["hit_rate"] == 1.0 and cell["brier"] == 0.0
    assert cell["verdict"] == "inconclusive"                 # perfect ≠ earning (not the sizing channel)

    bad = [_row(d, "801001", proj_next="trough") for d in _stamp_dates(CAL, 40, 100)]
    card = g.grade(pd.DataFrame(bad), prices, None)
    cell = card["channels"]["calibration"]["states"]["proj_trough"]["21"]
    assert cell["hit_rate"] == 0.0 and cell["brier"] == 1.0
    assert cell["verdict"] == "falsified"                    # can't even match a coin-flip
    assert card["channels"]["calibration"]["sizing_eligible"] is False


# ========================================================= 5 · NO POINT FORECASTS ----

def test_scorecard_copy_is_conditional_display_only():
    log, prices = _two_id_setup(_falling(N_BARS), _rising(N_BARS))
    card = g.grade(log, prices, None)
    assert card["is_context_only"] is True
    assert "not a forecast" in card["caveat_en"]
    assert card["convention"] == g.CONVENTION
    assert card["gates"]["min_earn_n"] == g.MIN_EARN_N       # the gate is published, not implicit
    assert card["channels"]["return"]["sizing_eligible"] is False
    assert card["channels"]["calibration"]["sizing_eligible"] is False


# ================================================================ never-raise ----

def test_never_raises_and_returns_empty_on_missing_input(monkeypatch, tmp_path):
    assert g.grade(None, {"x": _flat(50)}, None) == {}
    assert g.grade(pd.DataFrame(), {"x": _flat(50)}, None) == {}
    assert g.grade(pd.DataFrame([_row("2024-03-01", "801001")]), {}, None) == {}
    assert g.grade(pd.DataFrame({"foo": [1]}), {"x": _flat(50)}, None) == {}
    # rows missing every optional column still grade (never-raise, degrade-soft)
    lean = pd.DataFrame([{"date": str(CAL[50].date()), "id": "801001"}])
    card = g.grade(lean, {"801001": _flat(N_BARS)}, None)
    assert card and card["log"]["n_rows"] == 1
    # compute() with no forward log on disk -> {}
    import lib.config as config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert g.compute() == {}


def test_unpriced_ids_are_counted_not_dropped_silently():
    log = pd.DataFrame([_row(str(CAL[50].date()), "b-ghost", phase="Peak"),
                        _row(str(CAL[50].date()), "801001", phase="Peak")])
    card = g.grade(log, {"801001": _flat(N_BARS)}, None)
    assert card["log"]["n_unpriced"] == 1


def test_earliest_maturity_projection_when_log_is_young():
    px = _flat(N_BARS)
    log = pd.DataFrame([_row(str(CAL[-2].date()), "801001", phase="Peak")])
    card = g.grade(log, {"801001": px}, None)
    em = card["log"]["earliest_maturity"]["21"]
    assert em["matured"] is False and em["projected"] is True
    assert pd.Timestamp(em["date"]) > CAL[-1]
