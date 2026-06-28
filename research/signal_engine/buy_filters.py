"""Buy-side filter — THE KEEPER, in one reusable place (CHARTER §5 "✅ THE KEEPER").

The validated risk overlay that turns a raw confluence BUY*/RE-BUY into a graded
entry: **reclaim-and-hold + bearish-divergence veto + 200-day-MA as a confidence
bar-raiser (NOT a hard gate).** Designed on Tencent/BABA, it held out across all 110
US deep-history names — average max drawdown **−23.7% → −15.5%, shallower on 84% of
names** (`test_buyfilter.py`). It is a DRAWDOWN / entry-quality tool, never alpha
(read `CHARTER.md` §2 before you touch it).

WHY THIS MODULE EXISTS
----------------------
The keeper logic was born inside two diagnostic scripts (`diagnose_v2.refined_buy`,
`diagnose_tencent_baba.{swing_points,divergence_at}`) and was re-implemented for
production in `engine/signal_quality.py` (`_swing_highs`/`_bear_div`/`_buy_filter`).
This file is the single, dependency-light, **doctested** home for that math so new
research and tests import ONE canonical surface instead of copy-pasting from a
diagnostic. The four functions reproduce `engine/signal_quality.py` **exactly** —
that production module is the source of truth (CHARTER §4); keep them in lock-step.

  * `engine/signal_quality.py`  — production twin (writes the brain leaf + chart markers)
  * `diagnose_v2.refined_buy`    — legacy research twin (kept importable for in-flight
                                   sessions; returns TAKE/BLOCK strings, no "pending")

The expected `sig` frame is the one returned by `confluence.compute_signals` /
`engine.signal_quality.signal_frame`: a 3D-bar DataFrame with at least the columns
`close`, `macd`, `above200`, `w_bull` (leak-free, forward-only, confirmed pivots).

Doctest:  python3 -m doctest research/signal_engine/buy_filters.py -v
"""
from __future__ import annotations

import pandas as pd  # noqa: F401  (used by the doctests' namespace)

__all__ = ["swing_highs", "bearish_divergence", "reclaim_and_hold", "buy_filter_verdict"]


def swing_highs(s, w: int = 2) -> list[int]:
    """Indices of local maxima on the 3D series (``w`` bars confirmed each side).

    Confirmed pivots only — a bar is a swing high iff it is the max of the
    symmetric ``2*w+1`` window centred on it, so the last ``w`` bars can never be
    pivots (no repaint). Identical to ``engine.signal_quality._swing_highs``.

    >>> swing_highs(pd.Series([1, 2, 5, 2, 1, 3, 9, 3, 1]), w=2)
    [2, 6]
    >>> swing_highs(pd.Series([1.0, 2.0, 3.0]), w=2)   # too short to confirm any pivot
    []
    """
    v = s.to_numpy()
    return [i for i in range(w, len(v) - w) if v[i] == v[i - w:i + w + 1].max()]


def bearish_divergence(i, close, macd, hi, look: int = 12) -> bool:
    """True iff the last two swing highs within ``look`` bars of ``i`` show price
    making a HIGHER high while RSI-MACD makes a LOWER high (classic bearish
    divergence → veto the buy). Identical to ``engine.signal_quality._bear_div``.

    ``hi`` is the precomputed output of :func:`swing_highs` on ``close``.

    >>> close = pd.Series([1.0, 2.0, 5.0, 2.0, 1.0, 2.0, 6.0, 2.0, 1.0])
    >>> macd  = pd.Series([0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    >>> hi = swing_highs(close)
    >>> hi
    [2, 6]
    >>> bearish_divergence(6, close, macd, hi)   # price 5->6 (HH) but macd 3->1 (LH)
    True
    >>> macd_up = pd.Series([0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.0])
    >>> bearish_divergence(6, close, macd_up, hi)  # macd 3->5 (HH too) -> no divergence
    False
    """
    cv, mv = close.to_numpy(), macd.to_numpy()
    rh = [h for h in hi if i - look < h <= i]
    # bool(...) so the canonical surface returns a real Python bool (the production
    # twin _bear_div returns numpy bool_; same truth value, cleaner type here).
    return bool(len(rh) >= 2 and cv[rh[-1]] > cv[rh[-2]] and mv[rh[-1]] < mv[rh[-2]])


def reclaim_and_hold(i, sig, n):
    """The reclaim-and-hold gate + 200-MA bar-raiser (divergence veto handled by
    :func:`buy_filter_verdict`). Mirrors the body of
    ``engine.signal_quality._buy_filter`` after its bear-div check.

    Returns ``(take, reason)`` where ``take`` is ``True`` / ``False`` / ``None``:

      * **None**  → *pending*: the last 1-2 bars cannot confirm yet (no look-ahead).
      * In a confirmed regime (above 200-MA *or* weekly up): TAKE iff the next bar
        holds above the entry bar ("reclaim and hold"); else BLOCK.
      * In a counter-trend regime (below 200-MA **and** weekly down) the bar is
        raised: require the hold **and** a 200-MA reclaim within the next two bars.

    >>> sig = pd.DataFrame({
    ...     "close":    [10.0, 11.0, 10.5, 9.0, 9.5, 10.0],
    ...     "above200": [True, True, False, False, False, False],
    ...     "w_bull":   [True, True, False, False, False, False],
    ...     "macd":     [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    ... })
    >>> n = len(sig)
    >>> reclaim_and_hold(0, sig, n)    # uptrend, next bar 11>10 holds
    (True, 'held confirmation')
    >>> reclaim_and_hold(1, sig, n)    # next bar 10.5<11 fails the hold
    (False, 'failed reclaim-and-hold')
    >>> reclaim_and_hold(2, sig, n)    # counter-trend, never reclaims the 200-MA
    (False, 'counter-trend, no 200-reclaim/hold')
    >>> reclaim_and_hold(5, sig, n)    # last bar -> cannot confirm yet
    (None, 'pending confirmation')
    """
    c, a = sig["close"], sig["above200"]
    if i + 1 >= n:
        return None, "pending confirmation"
    held = bool(c.iloc[i + 1] > c.iloc[i])
    below, wkdn = (not bool(a.iloc[i])), (not bool(sig["w_bull"].iloc[i]))
    if below and wkdn:                                   # counter-trend: raise the bar
        if i + 2 >= n:
            return None, "pending confirmation"
        reclaim = bool(a.iloc[i + 1]) or bool(a.iloc[i + 2])
        ok = held and reclaim
        return ok, ("reclaimed 200 & held" if ok else "counter-trend, no 200-reclaim/hold")
    return held, ("held confirmation" if held else "failed reclaim-and-hold")


def buy_filter_verdict(i, sig):
    """Grade a raw confluence buy at bar ``i`` of frame ``sig``.

    Returns ``(verdict, reason)`` with ``verdict`` in ``{"take", "block",
    "pending"}`` — the exact quality strings of the chart-marker contract
    (CHARTER §7). Order of operations (identical to
    ``engine.signal_quality._buy_filter``):

      1. **bearish-divergence veto** → ``"block"``;
      2. else :func:`reclaim_and_hold` → ``True`` ⇒ ``"take"``, ``False`` ⇒
         ``"block"``, ``None`` ⇒ ``"pending"``.

    Caller is responsible for only invoking this on bars where a raw buy fired
    (``sig["CB"]`` or ``sig["revBuy"]``). Swing highs are recomputed here for a
    self-contained call; for tight loops precompute ``hi`` once and call
    :func:`bearish_divergence` + :func:`reclaim_and_hold` directly (the production
    twin does exactly that).

    >>> sig = pd.DataFrame({
    ...     "close":    [10.0, 9.0, 11.0, 10.0, 12.0, 13.0],
    ...     "above200": [True] * 6,
    ...     "w_bull":   [True] * 6,
    ...     "macd":     [0.0, 0.0, 1.0, 0.0, 2.0, 0.0],
    ... })
    >>> buy_filter_verdict(3, sig)            # uptrend, holds next bar, no divergence
    ('take', 'held confirmation')
    >>> div = pd.DataFrame({
    ...     "close":    [1.0, 2.0, 5.0, 2.0, 1.0, 2.0, 6.0, 5.0, 4.0],
    ...     "above200": [True] * 9,
    ...     "w_bull":   [True] * 9,
    ...     "macd":     [0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
    ... })
    >>> buy_filter_verdict(6, div)            # price HH + macd LH -> vetoed
    ('block', 'veto: bearish divergence')
    """
    n = len(sig)
    hi = swing_highs(sig["close"])
    if bearish_divergence(i, sig["close"], sig["macd"], hi):
        return "block", "veto: bearish divergence"
    ok, reason = reclaim_and_hold(i, sig, n)
    if ok is None:
        return "pending", reason
    return ("take" if ok else "block"), reason


if __name__ == "__main__":   # pragma: no cover
    import doctest
    fails, _ = doctest.testmod(verbose=False)
    print("buy_filters doctests:", "OK" if not fails else f"{fails} FAILED")
