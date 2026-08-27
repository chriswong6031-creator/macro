"""Tests for the forward shadow book (engine/shadow_book.py).

The load-bearing invariant is the LEAK GUARD: a horizon must NEVER be graded before it has
fully elapsed (grading an open horizon would silently inflate the realized IC). Plus
append-only/idempotent snapshots and a grade() that recovers a known cross-sectional IC."""
import numpy as np
import pandas as pd
import pytest

from engine import shadow_book as SB


def _closes(n=200, tickers=("A", "B", "C", "D"), start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(0)
    return pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0, 0.01, n)) for t in tickers}, index=idx)


def test_snapshot_append_only_idempotent(tmp_path):
    book = str(tmp_path / "book.jsonl")
    recs = [{"ticker": "A", "score": 80}, {"ticker": "B", "score": 40}]
    assert SB.snapshot("2024-03-01", recs, horizons=(5, 21), path=book) == 2
    assert SB.snapshot("2024-03-01", recs, horizons=(5, 21), path=book) == 0   # idempotent
    df = SB.load_book(book)
    assert len(df) == 2 and set(df["ticker"]) == {"A", "B"}


def test_maturation_leak_guard(tmp_path):
    """A horizon is matured ONLY once its h-th forward bar has elapsed (<= asof)."""
    book = str(tmp_path / "book.jsonl")
    closes = _closes()
    d0 = closes.index[50]
    SB.snapshot(d0, [{"ticker": t, "score": i} for i, t in enumerate(closes.columns)],
                horizons=(5, 21), path=book)
    # before any horizon elapses -> nothing matured
    assert SB.mature(closes.index[51], closes, path=book).empty
    # h=5 ends at index 55; asof just below -> still nothing
    assert SB.mature(closes.index[54], closes, path=book).empty
    # asof == index 55 -> ONLY the 5d horizon matures, never the 21d
    m = SB.mature(closes.index[55], closes, path=book)
    assert set(m["horizon"]) == {5}
    # asof past index 71 -> both horizons mature
    m2 = SB.mature(closes.index[80], closes, path=book)
    assert set(m2["horizon"]) == {5, 21}


def test_mature_forward_return_correct(tmp_path):
    book = str(tmp_path / "book.jsonl")
    closes = _closes()
    p0 = 50
    d0 = closes.index[p0]
    SB.snapshot(d0, [{"ticker": "A", "score": 1}], horizons=(5,), path=book)
    m = SB.mature(closes.index[80], closes, path=book)
    exp = closes.iloc[p0 + 5]["A"] / closes.iloc[p0]["A"] - 1.0
    assert m.iloc[0]["fwd_ret"] == pytest.approx(exp, rel=1e-9)


def test_grade_recovers_known_ic():
    """grade() on a synthetic matured book where score perfectly ranks forward return
    must report a mean IC ≈ +1 (and the reverse ≈ -1)."""
    rows = []
    for di in range(8):                       # >=6 dates so ic_summary computes
        for t in range(12):
            rows.append({"date": f"2024-0{1+di//4}-{10+di:02d}", "ticker": f"T{t}",
                         "horizon": 21, "score": float(t), "percentile": float(t),
                         "fwd_ret": float(t) * 0.001})   # forward return increases with score
    g = SB.grade(pd.DataFrame(rows))
    assert g["by_horizon"]["h21"]["ic"]["mean_ic"] == pytest.approx(1.0, abs=1e-6)
    # flip the score -> IC flips sign
    flipped = pd.DataFrame(rows).assign(score=lambda d: -d["score"])
    gf = SB.grade(flipped)
    assert gf["by_horizon"]["h21"]["ic"]["mean_ic"] == pytest.approx(-1.0, abs=1e-6)


def test_grade_empty_book():
    g = SB.grade(pd.DataFrame())
    assert g["n_matured"] == 0 and g["by_horizon"] == {}


def _matured_panel(n_dates=40, n_names=12, h=21, ret_of=None):
    """Synthetic matured frame on a business-day grid with real end_dates (date + h bars),
    the shape mature() emits. `ret_of(score)` maps score -> forward return."""
    ret_of = ret_of or (lambda s: s * 0.001)
    idx = pd.bdate_range("2024-01-01", periods=n_dates + h + 1)
    rows = []
    for di in range(n_dates):
        for t in range(n_names):
            rows.append({"date": str(idx[di].date()), "ticker": f"T{t}", "horizon": h,
                         "score": float(t), "percentile": float(t),
                         "fwd_ret": ret_of(float(t)),
                         "end_date": str(idx[di + h].date())})
    return pd.DataFrame(rows)


def test_grade_hac_lag_requested_is_overlap_but_t_suppressed_short():
    """Daily snapshots graded on an h-bar forward window overlap h deep: the requested
    HAC lag must be h itself. But a series that cannot carry that lag (n < 3h) must
    SUPPRESS t/p rather than publish one from the L~n-degenerate Bartlett estimator
    (gamma_0 cancels at L=n-1; red-team 2026-08-26 measured t INFLATING 4.04->6.82)."""
    g = SB.grade(_matured_panel(n_dates=40, h=21))
    ic = g["by_horizon"]["h21"]["ic"]
    assert ic["hac_lags_requested"] == 21
    assert ic["hac_lags"] == 21          # 40 IC dates > 21 -> no clamp on the lag itself
    assert ic["t_hac"] is None and ic["p_hac"] is None
    assert "cannot carry" in ic["t_suppressed"]
    # 40 daily dates with 21-bar windows collapse to exactly 2 non-overlapping episodes
    assert g["by_horizon"]["h21"]["n_indep_windows"] == 2
    assert g["by_horizon"]["h21"]["verdict"] == "building"     # prereg §3 floor


def test_grade_t_published_when_series_carries_lag():
    """Once n >= 3h the correction is real: t publishes at the full overlap lag, and
    a perfectly-ranking score shows a positive t with no suppression note."""
    g = SB.grade(_matured_panel(n_dates=70, h=21))
    ic = g["by_horizon"]["h21"]["ic"]
    assert ic["hac_lags"] == 21 and ic["hac_lags_requested"] == 21
    assert ic["t_hac"] is not None and ic["t_hac"] > 0
    assert "t_suppressed" not in ic


def test_grade_hac_lag_clamps_on_short_series():
    """A book shorter than its own overlap cannot carry the full correction: the
    effective lag is n-1, the request stays visible beside it, and t is suppressed."""
    g = SB.grade(_matured_panel(n_dates=10, h=21))
    ic = g["by_horizon"]["h21"]["ic"]
    assert ic["hac_lags_requested"] == 21
    assert ic["hac_lags"] == 9
    assert ic["t_hac"] is None and "cannot carry" in ic["t_suppressed"]


def test_grade_verdict_floor():
    """Prereg §3: 'building' below 6 matured clusters / 2 quarters of history; the
    floor-met state defers to §2 adjudication, never auto-stamps PASS/NULL."""
    g = SB.grade(_matured_panel(n_dates=140, h=21))
    v = g["by_horizon"]["h21"]["verdict"]
    assert v.startswith("sample_floor_met")
    assert "PREREGISTRATION" in v


def test_clark_west_positive_on_predictive_score():
    """A score that maps linearly onto forward returns must show genuine OOS content:
    positive cw_t, oos_r2 near 1, and forecasts only on dates with a fully-closed prior."""
    m = _matured_panel(n_dates=100, h=21)
    cw = SB.grade(m)["by_horizon"]["h21"]["clark_west"]
    # earliest eligible date needs >= _CW_MIN_PRIOR_ROWS closed rows AND >= 3 closed dates:
    # with h=21 and 12 names/date, first forecast at date index >= 26 -> 74 eligible dates,
    # which also clears the 3*21 suppression floor
    assert 0 < cw["n_dates"] <= 100 - 26
    assert cw["cw_t"] is not None and cw["cw_t"] > 0
    assert cw["oos_r2"] is not None and cw["oos_r2"] > 0.9
    assert cw["hac_lags_requested"] == 21


def test_clark_west_t_suppressed_on_short_eligible_series():
    """Eligible CW dates below 3h: oos_r2 may print (>=8 dates) but cw_t/cw_p are
    suppressed with the degeneracy note — same rule as the IC series."""
    cw = SB.grade(_matured_panel(n_dates=40, h=21))["by_horizon"]["h21"]["clark_west"]
    assert 8 <= cw["n_dates"] < 63
    assert cw["cw_t"] is None and cw["cw_p"] is None
    assert "cannot carry" in cw["t_suppressed"]
    assert cw["oos_r2"] is not None


def test_clark_west_oos_r2_needs_eight_dates():
    """A pooled R2 from a couple of forecast dates is noise wearing a number: below 8
    eligible dates oos_r2 must be None (t is already None via newey_west's own floor)."""
    cw = SB.grade(_matured_panel(n_dates=32, h=21))["by_horizon"]["h21"]["clark_west"]
    assert 0 < cw["n_dates"] < 8
    assert cw["oos_r2"] is None and cw["cw_t"] is None


def test_clark_west_leak_guard_no_open_prior():
    """With too few dates for any prior window to have CLOSED before a later snapshot,
    Clark-West must emit nothing rather than fit on open (leaking) windows."""
    cw = SB.grade(_matured_panel(n_dates=15, h=21))["by_horizon"]["h21"]["clark_west"]
    assert cw["n_dates"] == 0 and "cw_t" not in cw


def test_clark_west_requires_end_date():
    """A matured frame with no end_date column (pre-schema rows) cannot form a leak-free
    prior; the CW block must degrade to an explicit note, never a silent fit."""
    m = _matured_panel(n_dates=30, h=21).drop(columns=["end_date"])
    cw = SB.grade(m)["by_horizon"]["h21"]["clark_west"]
    assert cw["n_dates"] == 0 and "no end_date" in cw.get("note", "")


def test_indep_windows_count_only_ic_dates():
    """A thin date (below the 10-name IC floor) contributes no IC and must not pad
    n_indep_windows — the field the registry says to lead every read with."""
    m = _matured_panel(n_dates=40, h=21)
    idx = pd.bdate_range("2024-01-01", periods=80)
    thin = pd.DataFrame([{"date": str(idx[60].date()), "ticker": f"T{t}", "horizon": 21,
                          "score": float(t), "percentile": float(t),
                          "fwd_ret": float(t) * 0.001, "end_date": str(idx[60 + 15].date())}
                         for t in range(5)])
    g = SB.grade(pd.concat([m, thin], ignore_index=True))
    # unfiltered the thin date would open a third disjoint window; filtered it cannot
    assert g["by_horizon"]["h21"]["n_indep_windows"] == 2
