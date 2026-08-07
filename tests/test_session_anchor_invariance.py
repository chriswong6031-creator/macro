"""A cascade verdict is a function of the PRICE HISTORY, never of the caller's slice.

Binding ruling: ``research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md``
(era ``abs-session-2026-08-06``, charter §SHIP req 3).

THE DEFECT THESE PIN. ``confluence_tiers._tf_bars`` used ``resample("2B"/"3B")``, whose bin
edges anchor to the SERIES' FIRST timestamp. One dropped leading bar flipped the tier on
13/232 data/stocks names and the not-topped veto on 27/232; the deep data/stocks loader and
the 2014-start baskets/ohlcv loader disagreed about live buyability on the SAME night for
NUE/PEP/WMT (buyable from one store only) and ECL/SW (inverted). ``_completed_resample``'s
``"2W-FRI"`` carried the same defect class into the S1/S2 badges.

WHAT INVARIANCE MEANS HERE, EXACTLY. The repair removes the STRUCTURAL dependence: bucket
membership is now a function of ``(reference calendar, date)`` alone, so every window of the
same name shares one grid. It does NOT — and cannot — remove the NUMERICAL one: every
indicator in this module is EWM-based (``ewm(span=...)``, Wilder RSI), and an EWM has
infinite memory, so dropping leading bars perturbs later values by an amount that decays with
depth (measured: 4.6e-3 on the 2D histogram at 205 bars, 0.0 by 900). On a deep store that is
below display precision and the verdicts are bit-identical; on a shallow one it can still tip
a hard threshold on a knife-edge day. Both halves are asserted separately below, so a future
reader can tell which guarantee is which instead of inferring it from a loose tolerance.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import confluence_tiers as ct
from engine import session_anchor as sa
from engine import signal_gate
from engine.confluence_tiers import ANCHOR_ERA, LEG_WARMUP_BARS, MA200_WARMUP_BARS
from lib import nyse_calendar

# Real NYSE sessions — real phases, real holidays. Fixtures are built ON these so a bucket
# boundary in a test means the same thing it means in production.
_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2005, 1, 1), date(2026, 8, 4))))


def _sess(n: int) -> pd.DatetimeIndex:
    """The last ``n`` real NYSE sessions ending 2026-08-04."""
    return _SESSIONS[len(_SESSIONS) - n:]


def _walk(idx: pd.DatetimeIndex, lg: np.ndarray, seed: int, vol: float) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(lg + np.cumsum(rng.normal(0.0, vol, len(idx)))), index=idx)


def _uptrend(n: int = 900, seed: int = 1) -> pd.Series:
    """(a) smooth uptrend + sinusoid — crosses fire regularly."""
    idx = _sess(n); i = np.arange(n)
    return _walk(idx, 0.5 * i / n + 0.12 * np.sin(2 * np.pi * i / 45), seed, 0.006)


def _down_then_v(n: int = 900, seed: int = 2) -> pd.Series:
    """(b) long downtrend then a V — a fresh cross near the END, the repaint-prone shape."""
    idx = _sess(n); i = np.arange(n)
    lg = np.where(i < n * 0.8, -0.8 * i / n, -0.64 + 2.2 * (i - n * 0.8) / n)
    return _walk(idx, lg, seed, 0.007)


def _holiday_span(seed: int = 3) -> pd.Series:
    """(c) a span that certainly contains Thanksgiving, Christmas and July-4 weeks — the
    short weeks whose bins the old calendar-anchored resample mis-split."""
    idx = _SESSIONS[(_SESSIONS >= pd.Timestamp("2021-06-01"))
                    & (_SESSIONS <= pd.Timestamp("2025-01-31"))]
    i = np.arange(len(idx))
    return _walk(idx, 0.3 * i / len(idx) + 0.15 * np.sin(2 * np.pi * i / 38), seed, 0.008)


def _halted(n: int = 900, seed: int = 4) -> pd.Series:
    """(d) three sessions missing mid-stream — a halt. The dates are absent from the series
    but present in the REFERENCE, so the buckets must simply skip them."""
    s = _uptrend(n, seed)
    return s.drop(s.index[[400, 401, 402]])


def _depth(n: int, seed: int = 5) -> pd.Series:
    """(e) shallow-history variants — the breadth/smallcap cache depths' shape."""
    idx = _sess(n); i = np.arange(n)
    return _walk(idx, 0.4 * i / n + 0.13 * np.sin(2 * np.pi * i / 40), seed, 0.007)


#: Deep fixtures (>=800 bars) — EWM memory has decayed, so these assert BIT-EXACT invariance.
DEEP_FIXTURES = {
    "uptrend_sinusoid": _uptrend(),
    "downtrend_then_V": _down_then_v(),
    "holiday_span": _holiday_span(),
    "halted_3_sessions": _halted(),
}
#: Shallow depth variants. 210 (not 200) so a 6-bar drop cannot cross the 200dMA warmup —
#: that boundary is a DEPTH effect and gets its own test below rather than muddying this one.
SHALLOW_FIXTURES = {"depth_210": _depth(210), "depth_400": _depth(400)}

#: Every field the anchor determines. The length-encoding fields (`bars`, `young_history`,
#: `null_legs`, `veto_legs_null`) are excluded BY DEFINITION — they report how much history
#: was passed, which is the one thing a truncation legitimately changes.
ANCHOR_FIELDS = ("tier", "weight", "sub", "eligible", "bars_to_cross", "asof",
                 "not_topped", "ticks", "provisional", "htf", "above200", "anchor_era")
#: Display-only glyph feed. Its documented contract is the SIGN, not the digits (see the
#: `_hist_last` block in confluence_tiers) — and the digits carry EWM memory.
GLYPH_FIELDS = ("hist_d2", "hist_d3")


def _diff(a: dict, b: dict, fields) -> dict:
    return {f: (a.get(f), b.get(f)) for f in fields if a.get(f) != b.get(f)}


# --------------------------------------------------------------------------- #
# 1. START-INVARIANCE — the charter's requirement 3
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_cascade_is_bit_identical_on_a_deep_series_regardless_of_leading_history(name, k):
    """``cascade(c) == cascade(c[k:])`` on every signal field, k = 1..6.

    This is the whole repair. Before it, one dropped leading bar moved the 2D/3D bin edges
    and with them the tier, the freshness tick count and the not-topped veto.
    """
    c = DEEP_FIXTURES[name]
    base, trunc = ct.cascade(c), ct.cascade(c.iloc[k:])
    assert _diff(base, trunc, ANCHOR_FIELDS) == {}, (
        f"{name}: dropping {k} leading bar(s) changed the verdict — the buckets are still "
        f"phased to the caller's slice")
    assert _diff(base, trunc, GLYPH_FIELDS) == {}, (
        f"{name}: display histograms moved on a deep series, where EWM memory should have "
        f"decayed below display precision")


@pytest.mark.parametrize("name", sorted(SHALLOW_FIXTURES))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_cascade_signal_fields_are_invariant_on_a_shallow_series(name, k):
    """The same guarantee at breadth-cache depth. Every ANCHOR field is still exact; only the
    display glyphs are compared by SIGN, because at 210-400 bars the EWM warm-up has not yet
    decayed (measured below) and the glyph's contract is its sign."""
    c = SHALLOW_FIXTURES[name]
    base, trunc = ct.cascade(c), ct.cascade(c.iloc[k:])
    assert _diff(base, trunc, ANCHOR_FIELDS) == {}, (
        f"{name}: dropping {k} leading bar(s) changed an anchor-determined field")
    for f in GLYPH_FIELDS:
        a, b = base.get(f), trunc.get(f)
        assert (a is None) == (b is None), f"{name}: {f} nullness moved"
        if a is not None:
            assert np.sign(a) == np.sign(b), f"{name}: {f} SIGN flipped ({a} -> {b})"
            assert abs(a - b) < 0.05, f"{name}: {f} moved more than EWM memory explains"


def test_the_residual_slice_sensitivity_is_ewm_memory_and_decays_with_depth():
    """Name the residual instead of hiding it in a tolerance.

    Every indicator here is EWM-based, and an EWM depends on ALL prior bars, so a truncation
    perturbs later values by an amount that DECAYS with depth. That is a different animal
    from the bucket-phase defect (which was structural, unbounded, and did not decay). If
    this ever stops decaying, the anchor is leaking again.
    """
    drift = {}
    for n in (210, 400, 900):
        c = _uptrend(n)
        a, b = ct.cascade(c), ct.cascade(c.iloc[6:])
        drift[n] = abs((a["hist_d2"] or 0.0) - (b["hist_d2"] or 0.0))
    assert drift[900] == 0.0, "at 900 bars EWM memory must be below display precision"
    assert drift[900] <= drift[400] <= drift[210], f"drift is not decaying with depth: {drift}"


def test_the_200dma_boundary_is_a_depth_effect_not_an_anchor_effect():
    """The one field a truncation may legitimately move, and why (R8).

    ``above200`` needs 200 daily bars. Truncating a 200-bar series below that makes the
    average genuinely unknowable, so the field goes NULL — never False (the PLTR precedent) —
    and says so in ``null_legs``. This is a DEPTH effect, disclosed; the anchor is not
    involved and must not be blamed for it.
    """
    c = _depth(MA200_WARMUP_BARS)
    full, cut = ct.cascade(c), ct.cascade(c.iloc[6:])
    assert full["above200"] in (True, False)
    assert cut["above200"] is None and cut["above200"] is not False
    assert "above200" in cut["null_legs"] and "above200" not in (full["null_legs"] or {})
    # everything the ANCHOR owns is still identical across that same truncation
    assert _diff(full, cut, tuple(f for f in ANCHOR_FIELDS if f != "above200")) == {}


# --------------------------------------------------------------------------- #
# 2. tier_stream truncation stability
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
def test_tier_stream_agrees_on_the_shared_tail_after_a_truncation(name):
    """The vectorized twin must be start-invariant too, or the completed-basis replay would
    measure its own phase disagreement and report it as repaint."""
    c = DEEP_FIXTURES[name]
    a, b = ct.tier_stream(c), ct.tier_stream(c.iloc[3:])
    assert not a.empty and not b.empty
    shared = a.index.intersection(b.index)[-60:]
    assert len(shared) == 60
    for col in ("tier", "ticks", "not_topped", "eligible", "sub"):
        left = a.loc[shared, col].fillna(-1).to_numpy()
        right = b.loc[shared, col].fillna(-1).to_numpy()
        n_diff = int((left != right).sum())
        assert n_diff == 0, f"{name}: tier_stream '{col}' differs on {n_diff}/60 shared rows"


# --------------------------------------------------------------------------- #
# 3. the anchor itself
# --------------------------------------------------------------------------- #

def test_session_positions_are_exact_ordinals_in_the_reference():
    R = sa.reference_sessions("US")
    assert R[0] == pd.Timestamp("1950-01-03")
    probe = pd.DatetimeIndex([R[0], R[1], R[5000], R[-1]])
    pos = sa.session_positions(probe)
    assert list(pos) == [0, 1, 5000, len(R) - 1]
    assert list(R[pos]) == list(probe)          # the position round-trips to the date


def test_a_date_absent_from_the_reference_takes_the_NEXT_sessions_position():
    """A synthetic Saturday (bdate fixtures produce none, but off-calendar intl sessions do)
    must resolve DETERMINISTICALLY — to the next session — never to something the series
    start could influence."""
    fri, sat, mon = (pd.Timestamp("2026-08-07"), pd.Timestamp("2026-08-08"),
                     pd.Timestamp("2026-08-10"))
    p = sa.session_positions(pd.DatetimeIndex([fri, sat, mon]))
    assert p[0] + 1 == p[1] == p[2], f"a Saturday must share Monday's position, got {p}"
    # a HOLIDAY behaves the same way (2025-07-04 is a full-day closure)
    q = sa.session_positions(pd.DatetimeIndex(["2025-07-03", "2025-07-04", "2025-07-07"]))
    assert q[0] + 1 == q[1] == q[2]


def test_dates_beyond_the_reference_end_extend_consecutively():
    """A stale CN/HK/CA reference beside a fresher name store. Rank extension, in order."""
    R = sa.reference_sessions("US")
    beyond = pd.DatetimeIndex([R[-1] + pd.Timedelta(days=d) for d in (1, 2, 3)])
    assert list(sa.session_positions(beyond)) == [len(R), len(R) + 1, len(R) + 2]


def test_dates_before_the_reference_start_mirror_backwards():
    R = sa.reference_sessions("US")
    before = pd.DatetimeIndex([R[0] - pd.Timedelta(days=d) for d in (5, 3, 1)])
    assert list(sa.session_positions(before)) == [-3, -2, -1]


@pytest.mark.parametrize("ticker,market", [
    ("AAPL", "US"), ("BRK.B", "US"), (None, "US"), ("", "US"),
    ("000001.SS", "CN"), ("300750.SZ", "CN"), ("300750.sz", "CN"),   # case-insensitive
    ("2800.HK", "HK"), ("2800.hk", "HK"),
    ("SHOP.TO", "CA"), ("ABC.V", "CA"),
    ("NVDA.TV", "US"),          # ".TV" must NOT match the ".V" suffix
])
def test_market_for_ticker(ticker, market):
    assert sa.market_for_ticker(ticker) == market


def test_an_unknown_market_string_resolves_to_the_us_reference():
    """R1's disclosed behaviour for the intl library: start-invariance holds under ANY fixed
    reference, so an unmapped suffix routes to US openly rather than guessing."""
    assert sa.reference_sessions("INTL") is sa.reference_sessions("US")


def test_a_missing_reference_store_raises_rather_than_falling_back(monkeypatch, tmp_path):
    """House law: a fallback chain hides absence from every rung. A CN name silently bucketed
    on NYSE sessions would be wrong in a way nothing downstream could see."""
    monkeypatch.setattr(sa, "_data_root", lambda: tmp_path)
    monkeypatch.setattr(sa, "_REF_CACHE", {})
    with pytest.raises(FileNotFoundError, match="CN"):
        sa.reference_sessions("CN")


# --------------------------------------------------------------------------- #
# 4. F6 — the veto's unknowable leg is DISCLOSED, and the fail-open is PINNED
# --------------------------------------------------------------------------- #

def _f6_fixture() -> pd.Series:
    """175 real sessions whose 3D StochRSI legs read CONSTRUCTIVE (k>=d, both far below the
    overbought band) while the 3D RSI-MACD is still NaN — i.e. exactly the 159-231 bar cohort
    in which ``macd_bear`` cannot be evaluated at all."""
    idx = _sess(175); i = np.arange(175)
    return _walk(idx, -0.20 * i / 175 + 0.10 * np.sin(2 * np.pi * i / 30 + np.pi / 3), 1, 0.002)


def test_veto_legs_null_names_the_leg_the_history_cannot_check():
    v = ct.cascade(_f6_fixture())
    assert v["bars"] == 175
    assert v["veto_legs_null"] == {
        "macd_bear": f"needs {LEG_WARMUP_BARS['m3_s3']} daily bars, has 175"}, (
        "the veto's macd_bear leg is structurally unknowable at 175 bars and must say so")


def test_the_veto_fails_open_on_an_unknowable_leg_and_that_is_the_decision():
    """R4, pinned deliberately. ``float(nan) < float(nan)`` is False, so below m3_s3's warmup
    the macd_bear leg cannot veto and ``not_topped`` rests on the two stoch legs alone.

    Tri-stating it would read falsy in every ``if not not_topped`` consumer and blank the
    whole 159-231 bar cohort — silently reversing the operator's 2026-08-05 floor lift. So the
    arithmetic stands and the gap is DISCLOSED. This test exists so that a future reader
    changing it has to change a test that says why.
    """
    c = _f6_fixture()
    v = ct.cascade(c)
    # the two legs that ARE checked read constructive...
    ss3, sk3 = ct._tf_bars(c, 3)
    k3, d3 = ct._stoch_rsi_kd(ss3)
    m3, _s3 = ct._rsi_macd(ss3)
    k3_d, d3_d = ct._to_daily(k3, sk3, c.index), ct._to_daily(d3, sk3, c.index)
    m3_d = ct._to_daily(m3, sk3, c.index)
    assert float(k3_d.iloc[-1]) < ct.OB and float(d3_d.iloc[-1]) < ct.OB   # not overbought
    assert float(k3_d.iloc[-1]) >= float(d3_d.iloc[-1])                    # not bearish-crossed
    # ...and the third is NOT knowable at all
    assert pd.isna(m3_d.iloc[-1]), "fixture no longer exercises the unknowable macd leg"
    # so the veto passes, on two legs of three, and says which one it could not check
    assert v["not_topped"] is True
    assert "macd_bear" in v["veto_legs_null"]
    # the fail-open is not academic: this name reaches the board on it
    assert v["tier"] is not None and v["eligible"] is True


def test_a_full_depth_name_discloses_no_veto_legs():
    assert ct.cascade(_uptrend(900))["veto_legs_null"] == {}


# --------------------------------------------------------------------------- #
# 5. era stamp reaches every return
# --------------------------------------------------------------------------- #

def test_anchor_era_is_on_every_cascade_return_shape():
    graded = ct.cascade(_uptrend(900))
    assert graded["anchor_era"] == ANCHOR_ERA
    # a computed BLANK (graded math ran, no tier fired) — `asof` is the discriminator
    blank = ct.cascade(_down_then_v(900))
    assert blank["anchor_era"] == ANCHOR_ERA
    # the THIN-history refusal
    thin = ct.cascade(_depth(40))
    assert thin["asof"] is None and thin["anchor_era"] == ANCHOR_ERA
    # the EXCEPT path — a non-numeric series blows up inside the indicator math
    boom = ct.cascade(pd.Series(list("abcdefghij") * 30, index=_sess(300)))
    assert boom["tier"] is None and boom["anchor_era"] == ANCHOR_ERA
    assert boom["veto_legs_null"] is None       # nothing was measured, so nothing is claimed


def test_anchor_era_is_a_tier_stream_column():
    st = ct.tier_stream(_uptrend(900))
    assert "anchor_era" in st.columns
    assert set(st["anchor_era"].unique()) == {ANCHOR_ERA}


def test_anchor_era_reaches_the_gate_verdict_and_the_slim_board_dict():
    v = signal_gate.gate("TEST", _uptrend(900))
    assert v["anchor_era"] == ANCHOR_ERA
    assert "anchor_era" in signal_gate.compact(v)
    assert signal_gate.buy_signal(v)["anchor_era"] == ANCHOR_ERA
    # veto disclosure rides beside null_legs on the full verdict
    assert isinstance(v["veto_legs_null"], dict)
    # a BLANK verdict is still a post-era row
    assert signal_gate.buy_signal(None)["anchor_era"] == ANCHOR_ERA
    thin = signal_gate.gate("TEST", _depth(40))
    assert thin["anchor_era"] == ANCHOR_ERA


# --------------------------------------------------------------------------- #
# 6. the 2W fortnight phase (R6)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
def test_2w_fortnight_buckets_are_identical_regardless_of_series_start(name):
    """R6. pandas phases a ``2W-FRI`` bin to the series' first timestamp, so the S1/S2 badges
    moved with the caller's slice; the absolute fortnight (epoch Friday 1970-01-02) does not.

    Both the LABELS and the KNOWN-DATES are compared: the label drives the completed-only tail
    drop, the known-date drives every downstream daily mapping.
    """
    c = DEEP_FIXTURES[name]
    ra, ka = ct._completed_resample(c, "2W-FRI")
    rb, kb = ct._completed_resample(c.iloc[5:], "2W-FRI")
    shared = ra.index.intersection(rb.index)
    # only the leading bucket(s) the truncation ate may be missing
    assert len(ra.index.difference(rb.index)) <= 1
    assert len(shared) >= len(ra) - 1
    assert list(shared) == sorted(shared), "labels must stay ascending and unique"
    assert (ka.loc[shared].to_numpy() == kb.loc[shared].to_numpy()).all(), (
        f"{name}: a fortnight bucket's known-date moved with the series start")
    assert np.allclose(ra.loc[shared].to_numpy(), rb.loc[shared].to_numpy()), (
        f"{name}: a fortnight bucket's close moved with the series start")


def test_2w_labels_are_pair_end_fridays_on_the_absolute_grid():
    """The phase origin is checkable arithmetic, not a magic number: every label is a Friday,
    and consecutive labels are exactly 14 days apart."""
    raw, _kn = ct._completed_resample(_uptrend(900), "2W-FRI")
    labels = pd.DatetimeIndex(raw.index)
    assert (labels.dayofweek == 4).all(), "every fortnight label must be a Friday"
    gaps = labels.to_series().diff().dropna().dt.days.unique()
    assert set(gaps) <= {14}, f"fortnight labels must step by 14 days, saw {gaps}"
    # and the grid is anchored to the epoch Friday, not to this series
    assert ((labels - ct._EPOCH_FRIDAY).days % 14 == 7).all()
