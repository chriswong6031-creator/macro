"""Guard: §7 marker-date forward-return grading embeds look-ahead — FORBIDDEN (CN-1 §W6-CN).

engine.signal_quality._buy_filter resolves a buy marker's 'take'/'block' label using bars i+1 (and
i+2 on the counter-trend branch): a name is 'take' only if the NEXT bar closed UP (held) — and, when
below the 200MA, only if it reclaimed within 2 bars. The marker's ``date`` is therefore NOT the
earliest date the label was knowable; grading forward returns *from the marker date* leaks the
confirmation bars into the "forward" window (measured +5.7pp/10d aggregate look-ahead).

These tests pin the load-bearing FACT structurally (no fragile fixture-direction assertion): the
label reads FUTURE bars, so the earliest legal anchor for any forward-return grade is the close at
which the label became knowable — the rule china_standout_track enforces (board-date close → T+1
fill). If _buy_filter is ever refactored to not consult i+1/i+2, these guards must be revisited.
"""
import numpy as np
import pandas as pd

from engine import signal_quality as sq


def _sig_for(close: pd.Series) -> pd.DataFrame:
    """The cleaned signal frame _buy_filter operates on (drops the warm-up NaNs)."""
    sig = sq.signal_frame(close, None, None)
    return sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])


def test_buy_filter_take_label_depends_on_the_NEXT_bar():
    """held = c[i+1] > c[i]: flip only bar i+1 and a 'take' must become a 'block'. Pure look-ahead."""
    t = np.arange(420)
    idx = pd.bdate_range("2024-01-01", periods=420)
    close = pd.Series(100 + 10 * np.sin(t / 25) + 0.10 * t + 3 * np.sin(t / 6), index=idx)
    sig = _sig_for(close)
    n = len(sig)

    # find a bar that is a buy cross, above the 200MA (so the simple `held` branch applies), whose
    # i+1 close is up (a natural 'take') — then prove flipping ONLY i+1 changes the verdict.
    flipped = False
    for i in range(n - 3):
        is_buy = bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i])
        above = bool(sig["above200"].iloc[i])
        if not (is_buy and above):
            continue
        take, _ = sq._buy_filter(i, sig, False, n)
        if take is not True:
            continue
        # now crush bar i+1 below bar i in a COPY of the frame → held must go False → not a take.
        s2 = sig.copy()
        s2.iloc[i + 1, s2.columns.get_loc("close")] = float(s2["close"].iloc[i]) * 0.5
        take2, _ = sq._buy_filter(i, s2, False, n)
        assert take2 is False, "flipping only the FUTURE bar i+1 must overturn the 'take' label"
        flipped = True
        break
    assert flipped, "fixture must expose at least one above-200 'take' buy cross"


def test_pending_when_future_bar_is_unavailable():
    """At the last bar the label CANNOT be known (needs i+1) → 'pending', never a booked 'take'.
    This is exactly why a live board must anchor a grade on a PAST, resolved bar, not the marker."""
    t = np.arange(300)
    idx = pd.bdate_range("2024-01-01", periods=300)
    close = pd.Series(100 + 8 * np.sin(t / 20) + 0.08 * t, index=idx)
    sig = _sig_for(close)
    n = len(sig)
    take, reason = sq._buy_filter(n - 1, sig, False, n)   # last bar: i+1 does not exist
    assert take is None and reason == "pending confirmation"


def test_analyze_marker_dates_are_pre_resolution_anchors():
    """End-to-end: every 'take'/'block' buy marker's date is a CROSS-bar date; its label needed the
    following bar(s). So a forward-return grader keyed on marker['date'] would start its window
    BEFORE the label was knowable — the leak the guard forbids. We assert the invariant holds for the
    whole marker stream: for each resolved buy marker there is at least one later bar in the frame
    (the confirmation bar the label consumed), i.e. no resolved label sits on the final bar."""
    t = np.arange(420)
    idx = pd.bdate_range("2024-01-01", periods=420)
    close = pd.Series(100 + 10 * np.sin(t / 25) + 0.10 * t + 3 * np.sin(t / 6), index=idx)
    res = sq.analyze("SYNTH", close)
    buys = [m for m in res["markers"]
            if m.get("type") in ("buy", "rebuy") and m.get("quality") in ("take", "block")]
    assert buys, "fixture must produce resolved buy markers"
    last_bar = res["asof"]
    for m in buys:
        # a resolved (take/block) label required a bar AFTER the marker → it cannot be the last bar.
        assert m["date"] < last_bar, (
            f"resolved buy marker {m['date']} sits on/after the last bar {last_bar} — impossible "
            "unless the label peeked; marker-date grading would embed that peek")


# --------------------------------------------------------------------------- #
# confirmation_date — the anchor a forward return is ALLOWED to use
# --------------------------------------------------------------------------- #
def _synth(periods: int = 420) -> pd.Series:
    t = np.arange(periods)
    return pd.Series(100 + 10 * np.sin(t / 25) + 0.10 * t + 3 * np.sin(t / 6),
                     index=pd.bdate_range("2024-01-01", periods=periods))


def test_confirmation_date_is_bucket_i_plus_2s_last_daily_session():
    """The derivation, checked against the 3B geometry re-derived independently here.

    A mid-panel marker: its bucket sits well inside the frame, so ``i + 2`` exists and
    the answer is that bucket's last DAILY session — not its label, which is the 3B
    bucket's LEFT edge and precedes even its own close.
    """
    close = _synth()
    sig = _sig_for(close)
    lastday = (pd.Series(close.index, index=close.index)
               .resample("3B").last().dropna().reindex(sig.index))
    mid = len(sig) // 2
    for i in (mid, mid + 7, mid + 13):
        got = sq.confirmation_date(close, sig.index[i])
        assert got == lastday.iloc[i + sq.CONFIRM_BARS]
        # ...and it is strictly LATER than the marker label, by more than one session:
        # that gap is the look-ahead the anchor exists to remove.
        assert got > sig.index[i]
        assert int((close.index > sig.index[i]).sum() - (close.index > got).sum()) >= 5


def test_a_marker_inside_its_own_confirmation_window_degrades_to_null():
    """Near the series end bar i+2 does not exist — the caller must get None, not a date.

    This is the live-edge case and the one that must never silently produce a number:
    a block whose confirmation close has not printed yet has no honest forward return,
    and the lanes turn this None into a disclosed ``pct_since: null``.
    """
    close = _synth()
    sig = _sig_for(close)
    for back in range(sq.CONFIRM_BARS):              # the last CONFIRM_BARS buckets
        assert sq.confirmation_date(close, sig.index[len(sig) - 1 - back]) is None
    # the first bucket that CAN confirm is exactly one further back — the boundary is
    # pinned from both sides so an off-by-one in either direction fails here.  It is
    # the same boundary _buy_filter draws with `if i + 2 >= n: pending confirmation`.
    edge = sig.index[len(sig) - 1 - sq.CONFIRM_BARS]
    lastday = (pd.Series(close.index, index=close.index)
               .resample("3B").last().dropna().reindex(sig.index))
    assert sq.confirmation_date(close, edge) == lastday.iloc[-1]
    # and it is the SAME boundary _buy_filter draws with `if i + 2 >= n: pending`
    assert sq._buy_filter(len(sig) - 1, sig, False, len(sig)) == (None, "pending confirmation")


def test_confirmation_date_refuses_a_date_that_is_not_a_bucket_label():
    """A marker off THIS series' 3B grid is unanswerable — never approximated.

    ``3B`` bins are anchored on the first index date, so a differently-trimmed copy of
    the series re-phases every label.  Returning the nearest bucket there would put the
    move on a bar the signal never saw, so the only safe answer is None.
    """
    close = _synth()
    sig = _sig_for(close)
    mid = sig.index[len(sig) // 2]
    assert sq.confirmation_date(close, mid) is not None
    for offset in (1, 2):                            # inside the bucket, not its label
        assert sq.confirmation_date(close, mid + pd.tseries.offsets.BDay(offset)) is None
    assert sq.confirmation_date(close, "2019-01-02") is None      # off the panel entirely


def test_confirmation_date_is_null_when_the_frame_cannot_be_built():
    """Too short for signal_frame → None. A short series is why the lanes print nulls."""
    assert sq.confirmation_date(_synth(60), "2024-02-01") is None
    assert sq.confirmation_date(pd.Series(dtype=float), "2024-02-01") is None
    assert sq.confirmation_date(_synth(), None) is None
    assert sq.confirmation_date(_synth(), "not-a-date") is None


def test_every_buy_filter_label_is_settled_by_bar_i_plus_CONFIRM_BARS():
    """Why CONFIRM_BARS is 2 and not 1 — the bound, re-derived rather than asserted.

    The plain branch reads only ``c[i+1]``, which would suggest 1.  It is reached only
    when ``bear`` is False, and ``bear`` runs ``_swing_highs(..., w=2)`` whose candidate
    list includes a swing high AT bar ``i`` — confirmed against ``v[i-2:i+3]``.  So
    perturbing bar ``i + 2`` alone can still flip a label, and an anchor at ``i + 1``
    would be measuring from a close that did not yet know the answer.
    """
    close = _synth()
    sig = _sig_for(close)
    highs = sig["high"]
    found = sq._swing_highs(highs)
    assert found, "fixture must produce swing highs"
    # every detected swing high is the max of a FIVE-bar window centred on itself, so
    # two bars after it are load-bearing in the decision
    values = highs.to_numpy()
    for j in found:
        assert len(values[j - 2:j + 3]) == 5
        assert values[j - 2:j + 3].max() == values[j]
    # ...and that is not academic: cut the series one bar short of j+2 and the swing
    # high at j is invisible, so `bear` at bar j cannot have been settled at j+1.
    j = max(h for h in found if h < len(sig) - 3)
    assert j not in sq._swing_highs(highs.iloc[: j + 2])
    assert j in sq._swing_highs(highs.iloc[: j + 3])
    # _bear_div's candidate window is `i - look < h <= i`, so a swing high AT bar i is
    # in scope for bar i's own bear test — which is what carries the bound to i+2.
    assert [h for h in found if j - 12 < h <= j][-1] == j
    assert sq.CONFIRM_BARS == 2
