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
