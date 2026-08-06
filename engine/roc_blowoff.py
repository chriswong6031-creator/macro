"""engine/roc_blowoff.py — blow-off (terminal) risk context for a single name.

DISPLAY TIER — **ZERO SCORE AUTHORITY**.  Nothing here ranks, admits, sizes, gates or
vetoes anything.  It computes one boolean plus its three legs so a board card and the
per-stock page can print a risk-context chip; ``blowoff_risk`` is listed in
:data:`engine.us_board_rank.ZERO_SCORE_AUTHORITY` and a byte-identity test
(``tests/test_roc_blowoff.py``) pins that rank/stage/featured output is the same with
the fields present and with them absent.

WHAT IT MEASURES (the only claim the chip is allowed to make)
    Source: ``research/prophet_us_audit/roc_extremes_battery.py`` — the S-ROC12-TERM
    detector (``roc12_term_legs``) — and its committed verdict in
    ``roc_extremes_battery_results.json``:

        verdict POSITIVE · top-proximity 24.18% (fires) vs 19.32% (p80-90 controls)
        diff +4.86pp, month-block CI95 [+1.93, +8.11], n_event 22,014 / n_control 79,039
        H=21 drawdown matched median delta -2.471pp, CI95 [-3.163, -1.825]
        PM4 redundancy fence vs ext_z: max |rho| 0.4323 < 0.85 — NOT redundant

    "Top-proximity" is the fraction of events whose maximum close over [t, t+62]
    already occurred inside [t, t+5] — i.e. the extreme marked the local top.  Roughly
    three in four fires are therefore NOT the top; the chip copy says so out loud.

CONSTRUCTION — mirrored leg-for-leg from ``roc12_term_legs``.  Do not tune anything in
the constant block: the rates above were produced by exactly these numbers, and a
changed window makes the printed rate a claim about a population that was never
measured.  ``tests/test_roc_blowoff.py`` imports the battery by path and asserts this
module's fire mask is *identical* to the battery's on a synthetic panel, so the mirror
is verified rather than asserted.

    burst_mover    the own-history p97 of 5-session ROC (rolling 252d, min_periods 126)
                   is >= +15% — "this name is capable of 15%-a-week bursts", evaluated
                   AT the bar, so membership drifts with history and never looks ahead.
    near_high_63   close >= 95% of its own trailing 63-session high (an uptrend leg).
    fire           12-session ROC >= its OWN trailing p99 (rolling 252d quantile,
                   min_periods 126).

    NOTE ON THE FIRE LEG.  The battery fires on ``roc12 >= roll_q(roc12, 252, 0.99)`` —
    the trailing 0.99 QUANTILE — not on ``pct_rank(roc12, 252) >= 0.99``.  The two agree
    on almost every bar but are not the same test, and the measured 24.18% belongs to
    the quantile arm.  ``blowoff_risk`` therefore uses the quantile leg; ``roc12_pctile``
    is carried beside it as the display number ("how extreme, 0-1") and as the leg the
    battery's CONTROL arm used ([0.80, 0.90)).

BACKWARD-ONLY.  Every leg at bar t reads bars <= t.  :func:`assess` truncates to a
fixed tail before computing (see :data:`TAIL_BARS`); the truncation is exact, not an
approximation, and ``test_tail_truncation_is_exact`` pins it.

DISTINCT FROM ext_z.  The board already carries an ext_z-based anti-chase read
("Stretched unusually far above its trend line…", ``antichase_shadow_blocked``).  That
is a *different, separately measured* construction (px/SMA200 z-score) and the PM4
fence read above shows the two are not redundant (max |rho| 0.43).  The chip label is
"Blow-off risk", never the bare word "Extended" — see the comment where both render in
``templates/dashboard.html.j2``.
"""
from __future__ import annotations

import math

import pandas as pd

# ── constants mirrored from research/prophet_us_audit/roc_extremes_battery.py ──────
# roc12_term_legs() defaults + pct_rank/roll_q windows.  FROZEN: see module docstring.
ROC5_N = 5
ROC12_N = 12
RANK_WINDOW = 252
RANK_MIN_PERIODS = 126
MOVER_Q = 0.97
MOVER_MIN = 0.15
HIGH_WINDOW = 63
NEAR_HIGH = 0.05
FIRE_Q = 0.99
# Control band the measured 19.32% base rate came from — carried so the copy's "vs 19%
# base" is traceable to a construction, not to a remembered number.
CONTROL_BAND = (0.80, 0.90)

# The battery's panel floor: a name needed >= 300 bars to be measured at all
# (roc_extremes_battery.MIN_BARS).  A shorter name gets NO read rather than a read the
# measurement never covered.  This also matches build_stock_library._one(min_days=300).
MIN_BARS = 300

# Only the last bar is displayed, and the longest lookback is 252 rolling bars of a
# 12-session ROC = 264 closes.  Truncating to a fixed tail makes the read O(1) per name
# instead of O(len(history)) and is EXACT, not approximate: with >= 264 bars the last
# bar's 252-window is completely inside the tail.  400 is that bound plus margin.
TAIL_BARS = 400

# ── canonical chip copy (ONE source of truth) ─────────────────────────────────────
# The surfaces carry the literal text (house idiom — board copy lives in the template);
# tests/test_roc_blowoff.py asserts both surfaces still match these strings, so the two
# renderings cannot drift apart.  Every number below is quoted from the results JSON.
CHIP_EN = "Blow-off risk"
CHIP_ZH = "冲顶风险"
HOVER_EN = (
    "12-day move at its own 1-in-100 extreme near highs. Historically within 5 "
    "sessions of a local top 24% of the time (vs 19% base); next-21-session "
    "drawdowns ran ~2.5pp deeper. 3 of 4 such extremes are still not the top — "
    "risk context, not a sell signal."
)
HOVER_ZH = (
    "12日涨幅处于自身历史百分之一的极值，且贴近高点。历史上此类情形有24%在5个交易日内"
    "就是局部顶部（基准19%）；其后21个交易日的回撤中位数深约2.5个百分点。四次中仍有"
    "三次并非顶部——这是风险背景，不是卖出信号。"
)

# The keys this module stamps.  Named once so the authority-hygiene test and
# us_board_rank's disclosure list cannot drift from what actually gets written.
FIELDS = ("roc12_pctile", "burst_mover", "near_high_63", "blowoff_risk")


# ── primitives (same construction as the battery's pct_rank / roll_q / roc) ────────
def _roc(px: pd.Series, n: int) -> pd.Series:
    """n-session rate of change."""
    return px / px.shift(n) - 1.0


def _roll_q(obj: pd.Series, window: int, q: float, min_periods: int) -> pd.Series:
    """Trailing quantile of the own history (no lookahead)."""
    return obj.rolling(window, min_periods=min_periods).quantile(q)


def _pct_rank(obj: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Percentile of the latest value inside its OWN trailing window (no lookahead)."""
    return obj.rolling(window, min_periods=min_periods).rank(pct=True)


def legs(close) -> pd.DataFrame:
    """Per-bar leg frame for one close series.

    Mirrors ``roc12_term_legs`` leg-for-leg; ``blowoff_risk`` is that function's
    ``fire`` mask.  NaN comparisons are already ``False`` in pandas, so a warm-up bar
    reads "no fire" rather than raising — the same fail-closed behaviour the battery
    relies on.
    """
    c = pd.Series(close).astype(float)
    r5 = _roc(c, ROC5_N)
    p97_5 = _roll_q(r5, RANK_WINDOW, MOVER_Q, RANK_MIN_PERIODS)
    mover = p97_5 >= MOVER_MIN
    hi63 = c.rolling(HIGH_WINDOW, min_periods=HIGH_WINDOW).max()
    near = c >= (1.0 - NEAR_HIGH) * hi63
    r12 = _roc(c, ROC12_N)
    q99 = _roll_q(r12, RANK_WINDOW, FIRE_Q, RANK_MIN_PERIODS)
    p12 = _pct_rank(r12, RANK_WINDOW, RANK_MIN_PERIODS)
    base = mover & near
    return pd.DataFrame({
        "roc12": r12,
        "roc12_pctile": p12,
        "burst_mover": mover,
        "near_high_63": near,
        "roc12_ge_own_p99": r12 >= q99,
        "blowoff_risk": base & (r12 >= q99),
    })


def _round_or_none(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 4) if math.isfinite(number) else None


def assess(close) -> dict | None:
    """Latest-bar blow-off read for one name, or ``None`` when it cannot be measured.

    Returns ``{asof, roc12_pctile, burst_mover, near_high_63, blowoff_risk}``.  The
    read is stamped from the store's LAST BAR (``asof``), never from the wall clock —
    a stale price series yields a stale ``asof``, visible to the reader, rather than a
    read that silently claims today.

    ``None`` is returned for a series shorter than :data:`MIN_BARS`, which is the
    population the battery measured.  A short name gets no chip and no default.
    """
    c = pd.Series(close).dropna().astype(float)
    if len(c) < MIN_BARS:
        return None
    tail = c.iloc[-TAIL_BARS:] if len(c) > TAIL_BARS else c
    last = legs(tail).iloc[-1]
    asof = None
    try:
        asof = str(pd.Timestamp(tail.index[-1]).date())
    except (TypeError, ValueError, AttributeError):
        asof = None
    return {
        "asof": asof,
        "roc12_pctile": _round_or_none(last["roc12_pctile"]),
        "burst_mover": bool(last["burst_mover"]),
        "near_high_63": bool(last["near_high_63"]),
        "blowoff_risk": bool(last["blowoff_risk"]),
    }
