"""A COILED chip / mtf_upturn trend chip is a function of the PRICE HISTORY, never of
the caller's slice.

Binding ruling: research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md,
§Sibling triage chip (2) — era ``coiled-mtf-abs-session-2026-08-06`` covering BOTH
``engine/coiled`` (bull_div + fire_recent grids) and ``engine/mtf_upturn``
(the trend.d3 display chip). One era, one PR, one graded surface family (the
US/CN standout boards' display + rank chips).

THE DEFECT THESE PIN. Both modules cut their 3D/2D grids with pandas
``resample("3B"/"2B")``, whose bin edges anchor to the SERIES' FIRST timestamp.
Measured 2026-08-06 over 99 deep US names, dropping ONE leading bar flipped
``coiled.bull_div`` on 10/99, ``coiled.fire_recent`` on 70/99 and the
``mtf_upturn`` trend.d3 chip on 49/99 — and the US standout universe mixes deep
``data/stocks`` histories with ROLLING ~3y breadth caches whose window start
creeps forward every refresh, so these payloads re-phased build-to-build with
ZERO price action (fake day-over-day ``fire_ticks`` deltas on the graded board).

WHAT INVARIANCE MEANS HERE, EXACTLY (same split as the confluence battery):
the repair removes the STRUCTURAL slice-dependence — bucket membership is now a
function of ``(reference calendar, date)`` alone. It does NOT remove the
NUMERICAL one: every indicator involved is EWM-based, so a truncation perturbs
later values by an amount that decays with depth. On the deep fixtures below the
payloads must be BIT-IDENTICAL; the shallow fixtures assert the same at the
depths the production caches actually serve (400+ bars — fire_recent refuses
<300 outright), where the boolean/int payloads are empirically stable too.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import coiled
from engine import mtf_upturn
from lib import nyse_calendar

# Real NYSE sessions — real phases, real holidays (the confluence battery's convention).
_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2005, 1, 1), date(2026, 8, 4))))


def _sess(n: int) -> pd.DatetimeIndex:
    return _SESSIONS[len(_SESSIONS) - n:]


def _walk(idx: pd.DatetimeIndex, lg: np.ndarray, seed: int, vol: float) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(lg + np.cumsum(rng.normal(0.0, vol, len(idx)))), index=idx)


def _uptrend(n: int = 900, seed: int = 1) -> pd.Series:
    """(a) smooth uptrend + sinusoid — crosses fire regularly."""
    idx = _sess(n); i = np.arange(n)
    return _walk(idx, 0.5 * i / n + 0.12 * np.sin(2 * np.pi * i / 45), seed, 0.006)


def _down_then_v(n: int = 900, seed: int = 2) -> pd.Series:
    """(b) long downtrend then a V — a fresh fire near the END, the repaint-prone shape."""
    idx = _sess(n); i = np.arange(n)
    lg = np.where(i < n * 0.8, -0.8 * i / n, -0.64 + 2.2 * (i - n * 0.8) / n)
    return _walk(idx, lg, seed, 0.007)


def _holiday_span(seed: int = 3) -> pd.Series:
    """(c) certainly contains Thanksgiving, Christmas and July-4 weeks — the short weeks
    whose bins the old calendar-anchored resample mis-split."""
    idx = _SESSIONS[(_SESSIONS >= pd.Timestamp("2021-06-01"))
                    & (_SESSIONS <= pd.Timestamp("2025-01-31"))]
    i = np.arange(len(idx))
    return _walk(idx, 0.3 * i / len(idx) + 0.15 * np.sin(2 * np.pi * i / 38), seed, 0.008)


def _halted(n: int = 900, seed: int = 4) -> pd.Series:
    """(d) three sessions missing mid-stream — a halt. The dates are absent from the
    series but present in the REFERENCE, so the buckets must simply skip them."""
    s = _uptrend(n, seed)
    return s.drop(s.index[[400, 401, 402]])


def _depth(n: int, seed: int = 5) -> pd.Series:
    """(e) shallow-history variants — the breadth/smallcap cache depths' shape."""
    idx = _sess(n); i = np.arange(n)
    return _walk(idx, 0.4 * i / n + 0.13 * np.sin(2 * np.pi * i / 40), seed, 0.007)


#: Deep fixtures (>=800 bars) — EWM memory has decayed; payloads must be BIT-IDENTICAL.
DEEP_FIXTURES = {
    "uptrend_sinusoid": _uptrend(),
    "downtrend_then_V": _down_then_v(),
    "holiday_span": _holiday_span(),
    "halted_3_sessions": _halted(),
}
#: Shallow depth variants at the depths production actually serves off the rolling
#: caches. fire_recent hard-refuses <300 bars, so 320 exercises its floor region.
SHALLOW_FIXTURES = {"depth_320": _depth(320), "depth_400": _depth(400)}

ALL_FIXTURES = {**DEEP_FIXTURES, **SHALLOW_FIXTURES}

ERA = "coiled-mtf-abs-session-2026-08-06"


# --------------------------------------------------------------------------- #
# 1. START-INVARIANCE — the whole repair
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_bull_div_is_invariant_to_leading_history(name, k):
    """``bull_div(c) == bull_div(c[k:])``, k = 1..6. Before the repair one dropped
    leading bar re-phased the 3D bins and flipped the divergence verdict on 10/99
    deep US names."""
    c = ALL_FIXTURES[name]
    assert coiled.bull_div(c) == coiled.bull_div(c.iloc[k:]), (
        f"{name}: dropping {k} leading bar(s) flipped bull_div — the 3D grid is still "
        f"phased to the caller's slice")


@pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_fire_recent_payload_is_invariant_to_leading_history(name, k):
    """The ENTIRE fire payload — fire, ticks, src, era — bit-identical under truncation.

    ``ticks`` is bars-since-fire counted from the series END, so it is slice-invariant
    exactly when the fire DAY is; before the repair the 3B/2B bin phase moved the fire
    day itself (70/99 names at k=1), which is what minted fake day-over-day
    ``fire_ticks`` deltas out of pure window drift."""
    c = ALL_FIXTURES[name]
    base, trunc = coiled.fire_recent(c), coiled.fire_recent(c.iloc[k:])
    assert base == trunc, (
        f"{name}: dropping {k} leading bar(s) changed fire_recent "
        f"({base} -> {trunc})")


@pytest.mark.parametrize("name", sorted(ALL_FIXTURES))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_mtf_trend_d3_chip_is_invariant_to_leading_history(name, k):
    """The trend.d3 {pos, bars_since_cross} chip (dashboard MTF checklist) must not
    move when a loader hands in a different amount of leading history. Before the
    repair it flipped on 49/99 deep US names at k=1 and re-phased build-to-build
    off the rolling breadth caches."""
    c = ALL_FIXTURES[name]
    base = mtf_upturn._build_trend_fields(c)["d3"]
    trunc = mtf_upturn._build_trend_fields(c.iloc[k:])["d3"]
    assert base == trunc, (
        f"{name}: dropping {k} leading bar(s) moved trend.d3 ({base} -> {trunc})")


def test_washout_ctx_needed_no_repair_and_stays_slice_stable_on_the_shared_window():
    """The adjudication measured washout_ctx at 0 flips (pure trailing-window daily
    arithmetic — no grid). Pin that it STAYS that way on the battery shapes."""
    for name, c in ALL_FIXTURES.items():
        for k in (1, 2, 3):
            assert coiled.washout_ctx(c) == coiled.washout_ctx(c.iloc[k:]), (
                f"{name}: washout_ctx moved at k={k} — it must remain grid-free")


# --------------------------------------------------------------------------- #
# 2. Grid geometry — the label convention is load-bearing
# --------------------------------------------------------------------------- #

def test_tf_close_labels_are_the_buckets_last_traded_session():
    """``_tf_close`` must index each bucket by its LAST traded session (the known
    date): downstream both callers ffill/searchsorted on that index, so a label that
    is not a real bar of THIS series would shift every daily mapping."""
    c = _uptrend(60)
    for n in (2, 3):
        s = coiled._tf_close(c, n, "US")
        assert s.index.isin(c.index).all(), "labels must be real traded bars"
        assert s.index.is_monotonic_increasing and not s.index.has_duplicates
        # values are the CLOSE at that label — the bucket's last close by definition
        pd.testing.assert_series_equal(s, c.reindex(s.index), check_names=False)
        # buckets partition the series: session_positions // n changes at every label
        from engine import session_anchor as sa
        b = sa.session_positions(c.index, "US") // n
        n_buckets = len(np.unique(b))
        assert len(s) == n_buckets, "one row per bucket, no empty/duplicate buckets"


def test_a_halt_shrinks_a_bucket_but_never_rephases_the_grid():
    """Dates absent from the series but present in the reference simply drop out of
    their bucket; every bucket AFTER the halt keeps its identity. (The old bdate
    bins re-cut everything downstream of any missing row.)"""
    full = _uptrend(900, seed=4)
    halted = full.drop(full.index[[400, 401, 402]])
    a = coiled._tf_close(full, 3, "US")
    b = coiled._tf_close(halted, 3, "US")
    shared_tail = a.index.intersection(b.index)[-60:]
    pd.testing.assert_series_equal(a.reindex(shared_tail), b.reindex(shared_tail))


# --------------------------------------------------------------------------- #
# 3. The era stamp — one era, both modules, every payload
# --------------------------------------------------------------------------- #

def test_one_era_string_covers_both_modules():
    """The two modules ship in one PR and one graded surface family; a grader must
    be able to fence BOTH re-draws on a single boundary."""
    assert coiled.ANCHOR_ERA == ERA
    assert mtf_upturn.ANCHOR_ERA == ERA


def test_assess_payload_carries_the_era_on_every_path():
    """assess() IS the persisted us_standouts/china_standouts ``coiled`` block —
    the graders (grade_us_board, china_standout_track) and any day-over-day differ
    fence the one-time re-draw on this field."""
    ok = coiled.assess(True, 0.5, True)
    assert ok["anchor_era"] == ERA
    # the never-raise fallback path must declare its era too (a comparison on a
    # non-numeric cohort_frac raises inside, exercising the except branch)
    crash = coiled.assess(object(), object(), object())
    assert crash["anchor_era"] == ERA


def test_fire_recent_payload_carries_the_era_on_every_path():
    c = _uptrend(400)
    assert coiled.fire_recent(c)["anchor_era"] == ERA
    # the <300-bar refusal path
    assert coiled.fire_recent(c.iloc[:100])["anchor_era"] == ERA


def test_mtf_artifacts_carry_the_era(monkeypatch, tmp_path):
    """Both site artifacts (US tickers map + CN members map) must declare the era at
    the top level so a reader of site/stockdata/mtf_upturn.json can fence the one-time
    trend.d3 re-draw without consulting the repo."""
    monkeypatch.setattr(mtf_upturn, "_build_universe", lambda data_root=None: {})
    monkeypatch.setattr(mtf_upturn, "_build_cn_universe", lambda data_root=None: {})
    us = mtf_upturn.compute(data_root=tmp_path)
    cn = mtf_upturn.compute_cn(data_root=tmp_path)
    assert us["anchor_era"] == ERA
    assert cn["anchor_era"] == ERA
    assert any("coiled-mtf-abs-session-2026-08-06" in a for a in us.get("amendments", []))


# --------------------------------------------------------------------------- #
# 4. Market routing — the CN lane must cut CN buckets on the CN calendar
# --------------------------------------------------------------------------- #

def test_compute_symbol_threads_the_market_to_both_3d_consumers(monkeypatch):
    """``_compute_symbol`` serves the US and CN lanes off the same code path; the
    symbol suffix is the only place the calendar distinction is visible. Both 3D
    consumers — the d3_confluence leg AND the trend.d3 chip — must receive it."""
    seen = {}

    def fake_leg(close, market="US"):
        seen["leg"] = market
        return False

    def fake_trend(close, market="US"):
        seen["trend"] = market
        return {"d": {}, "d3": {}, "w": {}, "w2": {}}

    monkeypatch.setattr(mtf_upturn, "_leg_d3_confluence", fake_leg)
    monkeypatch.setattr(mtf_upturn, "_build_trend_fields", fake_trend)
    c = _uptrend(400)
    mtf_upturn._compute_symbol("600519.SS", c, "NONE", 0)
    assert seen == {"leg": "CN", "trend": "CN"}
    seen.clear()
    mtf_upturn._compute_symbol("AAPL", c, "NONE", 0)
    assert seen == {"leg": "US", "trend": "US"}


def _cn_reference_available() -> bool:
    try:
        from lib import config
        return (config.data_dir() / "china" / "000001.SS.parquet").exists()
    except Exception:
        return False


@pytest.mark.skipif(not _cn_reference_available(),
                    reason="CN session reference store absent from this checkout")
@pytest.mark.parametrize("k", [1, 2, 3])
def test_cn_market_invariance_on_the_cn_reference(k):
    """The same start-invariance guarantee under the CN calendar (tracked reference
    store data/china/000001.SS.parquet). A synthetic walk on real CN sessions."""
    from engine import session_anchor as sa
    R = sa.reference_sessions("CN")
    idx = R[-500:]
    i = np.arange(len(idx))
    rng = np.random.default_rng(9)
    c = pd.Series(100 * np.exp(0.4 * i / len(i) + 0.13 * np.sin(2 * np.pi * i / 40)
                               + np.cumsum(rng.normal(0.0, 0.007, len(i)))), index=idx)
    assert coiled.bull_div(c, market="CN") == coiled.bull_div(c.iloc[k:], market="CN")
    assert coiled.fire_recent(c, market="CN") == coiled.fire_recent(c.iloc[k:], market="CN")
    d3a = mtf_upturn._build_trend_fields(c, market="CN")["d3"]
    d3b = mtf_upturn._build_trend_fields(c.iloc[k:], market="CN")["d3"]
    assert d3a == d3b
