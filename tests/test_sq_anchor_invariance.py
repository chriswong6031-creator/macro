"""A §7 marker stream is a function of the PRICE HISTORY, never of the caller's slice.

Binding ruling: ``research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md``
(era ``sq-abs-session-2026-08-06``, ship requirement 3). Sibling battery for the cascade
layer: ``tests/test_session_anchor_invariance.py``.

THE DEFECT THESE PIN. ``signal_quality`` built all four of its grids with pandas ``2B``/
``3B`` bins, whose edges anchor to the SERIES' FIRST timestamp. Measured on the 2026-08-06
tape, end-to-end through ``gate()``, dropping ONE leading bar from the 238 data/stocks
names: 238/238 moved their last §7 marker date, 91 changed the last marker's IDENTITY
(PEP ``buy/block``↔``cut``, SW ``sell``↔``rebuy/block``), 95 flipped ``ticks``, 11 flipped
gate ELIGIBILITY and 3 flipped the final ``is_buyable`` verdict. So while the CASCADE layer
had been start-invariant since ``abs-session-2026-08-06``, ``gate()`` end-to-end was not,
and the four production history depths each read a different marker stream for one name.
The bins additionally MIS-SPLIT every bucket spanning a market holiday.

WHAT INVARIANCE MEANS HERE, EXACTLY — the same two-part answer the cascade battery gives,
because the same two mechanisms are in play and only one of them was a defect:

* **STRUCTURAL** (the repair): bucket membership is now a function of
  ``(reference calendar, date)`` alone, so every window of a name shares ONE grid. Asserted
  BIT-EXACTLY on the bucket closes below — before the repair this failed on every name.
* **NUMERICAL** (inherent, and not removable): every indicator here is EWM-based
  (``ewm(span=...)``, Wilder RSI), and an EWM depends on ALL prior bars. Dropping leading
  bars therefore perturbs later values by an amount that DECAYS with depth. Measured across
  all 238 data/stocks names at k=3 (reports/sq_anchor_blast_radius.md §3): **0 movers** on
  every field a board, a chart or a ledger reads, 190 of 238 marker streams identical END TO
  END, and the other 48 differing only in their own first weeks — the worst case being a
  2023 listing whose warm-up head is 2024, with the deep names' residuals decades old. It is
  asserted SEPARATELY and by name below, so a future reader can tell which guarantee is
  which instead of inferring it from a tolerance.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import session_anchor as sa
from engine import signal_gate
from engine import signal_quality as sq
from engine.signal_quality import ANCHOR_ERA
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
    short weeks whose bins the old business-day resample mis-split."""
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
    """(e) shallow-history variant — the breadth/smallcap cache depth's shape."""
    idx = _sess(n); i = np.arange(n)
    return _walk(idx, 0.4 * i / n + 0.13 * np.sin(2 * np.pi * i / 40), seed, 0.007)


FIXTURES = {
    "uptrend_sinusoid": _uptrend(),
    "downtrend_then_V": _down_then_v(),
    "holiday_span": _holiday_span(),
    "halted_3_sessions": _halted(),
    "depth_400": _depth(400),
}
KS = [1, 2, 3, 4, 5, 6]

#: Every ``analyze()`` field the anchor determines. ``markers`` — the VALIDATED trade
#: stream — is compared dict-for-dict, which is the strongest form of this claim.
#: ``risk_flags``/``early_markers`` are the two DISPLAY-ONLY date lists and are handled in
#: their own section: they ride the shallowest EWMs and are the only place the numerical
#: residual can still tip a boolean.
ANALYZE_FIELDS = ("markers", "asof", "state", "above200", "weekly_bull",
                  "trail_stop", "trail_breach", "early_now", "anchor_era")
#: Gate verdict fields. ``history_bars``/``young_history``/``null_legs``/``veto_legs_null``
#: are excluded BY DEFINITION — they report how much history was passed, which is the one
#: thing a truncation legitimately changes.
GATE_FIELDS = ("eligible", "tier", "sub", "reason", "tier_cascade", "ticks", "fresh_bars",
               "sq_anchor_era", "anchor_era")


def _diff(a: dict, b: dict, fields) -> dict:
    return {f: (a.get(f), b.get(f)) for f in fields if a.get(f) != b.get(f)}


# --------------------------------------------------------------------------- #
# 1. THE STRUCTURAL CLAIM — the grid itself, with no EWM anywhere in it
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(FIXTURES))
@pytest.mark.parametrize("k", KS)
@pytest.mark.parametrize("n", [2, 3])
def test_the_bucket_grid_is_bit_identical_regardless_of_leading_history(name, k, n):
    """The whole repair, isolated: ``_tf_grid`` has no indicator in it, so this test can
    ONLY fail structurally. Before the anchor it failed on every fixture and every k."""
    c = FIXTURES[name]
    a, b = sq._tf_grid(c, n), sq._tf_grid(c.iloc[k:], n)
    shared = a.close.index.intersection(b.close.index)
    assert len(shared) >= len(b.close) - 1, (
        f"{name}: only {len(shared)} of {len(b.close)} truncated buckets share a label with "
        f"the full series — the grid is still phased to the caller's slice")
    assert (a.close.loc[shared].to_numpy() == b.close.loc[shared].to_numpy()).all()
    assert (a.last_session.loc[shared].to_numpy()
            == b.last_session.loc[shared].to_numpy()).all(), (
        "a bucket's last session moved with the series start — confirmation_date would "
        "anchor two windows of one name on different closes")


def test_only_the_leading_partial_bucket_may_carry_a_different_label():
    """The single legitimate seam, named so it can never grow.

    A truncation can start MID-bucket. That bucket's OPEN-date label is then the first
    session the caller actually handed over — which is not a phase error, it is the caller
    withholding sessions. Every bucket after it must match exactly.
    """
    c = _uptrend()
    for k in KS:
        a, b = sq._tf_grid(c, 3), sq._tf_grid(c.iloc[k:], 3)
        orphans = b.close.index.difference(a.close.index)
        assert len(orphans) <= 1, f"k={k}: {len(orphans)} truncated labels are not in the full grid"
        if len(orphans):
            assert orphans[0] == b.close.index[0], "only the LEADING bucket may re-label"


# --------------------------------------------------------------------------- #
# 2. START-INVARIANCE end to end — the charter's ship requirement 3
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(FIXTURES))
@pytest.mark.parametrize("k", KS)
def test_analyze_is_identical_regardless_of_leading_history(name, k):
    """``analyze(c) == analyze(c[k:])`` on the validated marker stream and every state
    field, k = 1..6. Before the repair, one dropped leading bar moved the last marker date
    on 238/238 real names and changed 91 of their identities."""
    c = FIXTURES[name]
    base, trunc = sq.analyze("TEST", c), sq.analyze("TEST", c.iloc[k:])
    assert base is not None and trunc is not None
    assert _diff(base, trunc, ANALYZE_FIELDS) == {}, (
        f"{name}: dropping {k} leading bar(s) changed the §7 payload — the buckets are "
        f"still phased to the caller's slice")


@pytest.mark.parametrize("name", sorted(FIXTURES))
@pytest.mark.parametrize("k", KS)
def test_the_gate_verdict_is_identical_regardless_of_leading_history(name, k):
    """END-TO-END, the path a board actually reads. This is the assertion the cascade's own
    battery could not make: its layer was invariant while ``gate()`` was not, because the
    §7 marker stream feeding ``take_active``/``take_date`` still moved."""
    c = FIXTURES[name]
    a, b = signal_gate.gate("TEST", c), signal_gate.gate("TEST", c.iloc[k:])
    assert _diff(a, b, GATE_FIELDS) == {}, f"{name}: k={k} moved a gate verdict field"
    assert signal_gate.is_buyable(a) == signal_gate.is_buyable(b), (
        f"{name}: k={k} flipped the final buy verdict")


def test_a_holiday_span_no_longer_moves_when_one_bar_is_dropped():
    """The measured headline, as a test: k=1 used to move 238/238 last-marker dates.

    A holiday-dense span is the worst case for the retired business-day bins, which
    mis-split every bucket containing a closure. Here NOTHING moves.
    """
    c = FIXTURES["holiday_span"]
    base, trunc = sq.analyze("TEST", c), sq.analyze("TEST", c.iloc[1:])
    assert base["markers"] == trunc["markers"]
    assert len(base["markers"]) > 10, "fixture must carry a real marker stream"
    assert base["asof"] == trunc["asof"]


# --------------------------------------------------------------------------- #
# 3. LABEL CONVENTION — R-SQ2's OPEN-date semantics, re-derived independently
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_marker_date_is_a_real_traded_session_of_this_series(name):
    """R-SQ2. The charter's "Dates are 3D bar dates" is now literally true.

    The retired bins labelled the SYNTHETIC left edge, which could be a holiday belonging
    to no series at all — a marker nobody could have traded on, and a date a membership
    test against the daily index could never resolve.
    """
    c = FIXTURES[name]
    res = sq.analyze("TEST", c)
    days = {str(d.date()) for d in c.index}
    for m in res["markers"]:
        assert m["date"] in days, f"{name}: marker {m['date']} is not a session of this series"
    for lst in ("risk_flags", "early_markers"):
        for ds in res[lst]:
            assert ds in days, f"{name}: {lst} date {ds} is not a session of this series"


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_each_label_is_the_first_finite_close_of_its_own_absolute_bucket(name):
    """The OPEN-date rule, re-derived here from ``session_positions`` alone.

    Deliberately NOT asserted as ``position % 3 == 0``: after a halt a bucket's first
    TRADED bar can sit at any phase within it, so that pin would be wrong in exactly the
    case the anchor exists to handle. The checkable facts are that labels are strictly
    increasing in bucket id, and that each one is the FIRST finite close of its bucket.
    """
    c = FIXTURES[name]
    labels = sq.signal_frame(c).index
    pos = pd.Series(sa.session_positions(pd.DatetimeIndex(c.index), "US"), index=c.index)
    buckets = pos // 3
    ok = c.notna()
    expected = (pd.DataFrame({"d": c.index[ok], "b": buckets[ok].to_numpy()})
                .groupby("b")["d"].first())
    label_buckets = buckets.reindex(labels)
    assert label_buckets.is_monotonic_increasing and label_buckets.is_unique, (
        f"{name}: labels are not one-per-bucket in ascending bucket order")
    for lbl, b in zip(labels, label_buckets):
        assert lbl == expected.loc[b], (
            f"{name}: bucket {b} is labelled {lbl.date()} but its first traded session is "
            f"{expected.loc[b].date()}")


def test_a_bucket_label_can_sit_off_phase_after_a_halt():
    """The reason the label pin above is NOT ``position % 3 == 0``.

    If every label were phase-0 the rule would be trivially derivable from the calendar and
    the series would not matter — but a halted name's bucket opens on whichever session it
    actually traded. This asserts the fixture really exercises that, so the test above is
    not passing for a weaker reason than it claims.
    """
    c = FIXTURES["halted_3_sessions"]
    labels = sq.signal_frame(c).index
    phases = set(sa.session_positions(pd.DatetimeIndex(labels), "US") % 3)
    assert phases - {0}, "the halted fixture no longer produces an off-phase bucket open"


def test_confirmation_date_walks_the_same_grid_analyze_labelled():
    """The two halves of a confirmation read can no longer disagree by construction.

    They are one ``_tf_grid`` call now; before the anchor they were two independent
    resamples that agreed only while the caller passed identical history.
    """
    c = _uptrend()
    sig = sq.signal_frame(c).dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    lastday = sq._bucket_last_session(c).reindex(sig.index)
    mid = len(sig) // 2
    got = sq.confirmation_date(c, sig.index[mid])
    assert got == lastday.iloc[mid + sq.CONFIRM_BARS]
    # ...and it survives a truncation, which is the whole point
    assert sq.confirmation_date(c.iloc[6:], sig.index[mid]) == got


# --------------------------------------------------------------------------- #
# 4. THE ERA STAMP reaches every shape (R-SQ3)
# --------------------------------------------------------------------------- #

def test_anchor_era_rides_on_the_analyze_payload():
    res = sq.analyze("TEST", _uptrend())
    assert res["anchor_era"] == ANCHOR_ERA
    # placed right after `tf` so the §7 JSON stays readable
    assert list(res)[:4] == ["ticker", "asof", "tf", "anchor_era"]


def test_sq_anchor_era_reaches_every_gate_shape():
    v = signal_gate.gate("TEST", _uptrend())
    assert v["sq_anchor_era"] == ANCHOR_ERA
    assert signal_gate.compact(v)["sq_anchor_era"] == ANCHOR_ERA
    assert signal_gate.buy_signal(v)["sq_anchor_era"] == ANCHOR_ERA
    # a BLANK board row is still a post-era row
    assert signal_gate.buy_signal(None)["sq_anchor_era"] == ANCHOR_ERA
    # ...and so is the thin-history refusal, which is the row a cohort audit most needs
    thin = signal_gate.gate("TEST", _depth(40))
    assert thin["reason"] == "insufficient history"
    assert thin["sq_anchor_era"] == ANCHOR_ERA
    assert signal_gate.verdict(None)["sq_anchor_era"] == ANCHOR_ERA


def test_the_two_eras_are_distinct_and_both_travel():
    """A verdict is produced by TWO bucketing grids and must be placeable against BOTH.

    They were re-anchored in different PRs, so one stamp cannot stand for the other.
    """
    v = signal_gate.gate("TEST", _uptrend())
    from engine.confluence_tiers import ANCHOR_ERA as CASCADE_ERA
    assert v["anchor_era"] == CASCADE_ERA
    assert v["sq_anchor_era"] == ANCHOR_ERA != CASCADE_ERA


# --------------------------------------------------------------------------- #
# 5. THE NUMERICAL RESIDUAL — named, bounded, and shown to decay
# --------------------------------------------------------------------------- #

def test_the_residual_is_ewm_memory_and_decays_with_bucket_depth():
    """Name the residual instead of hiding it in a tolerance.

    Every indicator here is EWM-based, so a truncation perturbs later values by an amount
    that decays with depth. That is a DIFFERENT animal from the bucket-phase defect, which
    was structural, unbounded, did not decay, and reached the last bar. If this ever stops
    decaying, the anchor is leaking again.
    """
    c = _uptrend()
    a, b = sq.signal_frame(c), sq.signal_frame(c.iloc[6:])
    shared = a.index.intersection(b.index)
    d = (a.loc[shared, "macd"] - b.loc[shared, "macd"]).abs()
    # the bucket CLOSES carry no EWM at all and must be exact
    assert (a.loc[shared, "close"].to_numpy() == b.loc[shared, "close"].to_numpy()).all()
    deciles = [float(d.iloc[q].max()) for q in np.array_split(np.arange(len(shared)), 10)]
    tail = [x for x in deciles if not np.isnan(x)]
    assert tail[-1] < 1e-3, f"residual has not decayed by the live edge: {tail[-1]}"
    assert tail == sorted(tail, reverse=True), f"residual is not decaying monotonically: {tail}"


@pytest.mark.parametrize("name", sorted(FIXTURES))
@pytest.mark.parametrize("k", KS)
def test_the_display_only_date_lists_agree_except_inside_the_warmup(name, k):
    """``risk_flags`` and ``early_markers`` are the two DISPLAY-ONLY lists, and the only
    place the EWM residual can still tip a boolean.

    Both ride the shallowest EWMs (the span-8 trailing trend; the 2D histogram's rising
    test), so a knife-edge bar deep in the warm-up can flip. The claim asserted here is the
    one a reader depends on: any disagreement lies in the OLD half of the stream, never near
    the live edge. Measured on real data at k=3 the most recent such disagreement across all
    238 data/stocks names is decades old (reports/sq_anchor_blast_radius.md §3).
    """
    c = FIXTURES[name]
    a, b = sq.analyze("TEST", c), sq.analyze("TEST", c.iloc[k:])
    labels = list(sq.signal_frame(c).index)
    midpoint = str(labels[len(labels) // 2].date())
    for field in ("risk_flags", "early_markers"):
        disagreements = set(a[field]) ^ set(b[field])
        recent = [d for d in disagreements if d > midpoint]
        assert not recent, (
            f"{name}: k={k} moved {field} in the RECENT half of the stream ({recent}) — "
            f"that is not EWM warm-up, that is the anchor leaking")
