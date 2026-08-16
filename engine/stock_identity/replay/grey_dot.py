"""The grey anticipation dot: the Macro producer, its washout context, and the Terminal twin.

Three objects live here, and they are deliberately **not** collapsed into one:

``grey_dot_macro``
    The Macro producer's own ``early`` column, read off
    :func:`engine.signal_quality.signal_frame` — never re-derived. Every fire ships with
    ``in_washout_context`` set, so the family is published as a **dual series**: the
    as-recorded reading (all fires) and the as-restated reading (fires today's promotion
    rule would carve out to ``amber_early``) are both available from one store, and the
    as-restated view is expressed through typed ``promoted_by`` edges rather than by
    deleting rows (registration §3, review finding 13b).

``grey_dot_terminal``
    A **Class B locked-spec port** of the Terminal twin (Live Entry Radar contract §3.1),
    measured as a separate era-pinned expert. G-8 forbids running Terminal internals and
    the twin persists nothing, so a Macro-side port with a declared parity fixture is the
    only lawful route. Parity against ``grey_dot_macro`` is **reported as counts of
    agreeing and disagreeing fire dates** and the two families are kept separate
    regardless of the result (archaeology §4.5 item 2).

``washout_context``
    The Terminal promotion context ``W1 ∧ (W2a ∨ W2b) ∧ W3`` (Radar contract §3.4). It is
    the amber carve-out condition and the base predicate of :mod:`..bottom_watch`.

**No ruler content.** Nothing here measures lead, lag, distance, or outcome.

Divergence axes between the twins, stated up front so the parity counts can be read
(none of these are defects; they are the two implementations' actual differences):

1. **Oscillator family.** ``signal_quality`` imports ``engine.technicals.rsi`` (bare
   ``ewm``); the Terminal spec is the SMA-seeded RMA family (``engine.canon.rsi``, ==
   Pine ``ta.rsi``). The port pins canon, per the indicator-core law.
2. **2D bucketing.** Macro cuts 2D on the absolute session anchor (``_tf_grid``); the
   Terminal spec uses calendar ``resample("2B")`` with availability at each bucket's last
   actual session and a PIT searchsorted join onto the 3D row's ``known_ts``.
3. **The rising leg.** Macro requires TWO rising 2D histogram bars and reads the prior
   CLOSED bar (``.shift(1)``); the Terminal spec requires exactly ONE strictly-greater bar
   with no magnitude or sign requirement.
4. **The RSI ceiling.** Macro carries ``rsi14 < 65`` on the 3D bar; the Terminal spec's
   dot has no such leg.

**Named deviation of the port (honest limitation).** The Terminal's 3D grid is
*per-symbol listing-anchored* (``gi = arange(n) + bar_anchor``); ``bar_anchor`` is not
reproducible from anything committed in this repo, so the port cuts its 3D bars on the
Macro absolute session anchor. This is recorded in the family registry's ``parity_notes``
and means the parity counts below are a LOWER bound on twin agreement-or-disagreement
attributable to the four axes above — the anchor axis is held fixed, not measured.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Registration §2 scoped allowlist.
from engine import canon
from engine.signal_quality import (
    ANCHOR_ERA as SQ_ANCHOR_ERA,
    BUY_RSI_MAX,
    CONF_W,
    MA_LEN,
    OS,
    RSI_LEN,
    signal_frame,
)

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grid import KNOWN_BASIS_BUCKET, macro_grid

__all__ = [
    "MACRO_FAMILY_KEY",
    "TERMINAL_FAMILY_KEY",
    "MACRO_ERA",
    "TERMINAL_ERA",
    "macro_constants",
    "terminal_constants",
    "washout_context",
    "macro_fires",
    "terminal_fires",
    "parity_counts",
]

MACRO_FAMILY_KEY = "grey_dot_macro"
TERMINAL_FAMILY_KEY = "grey_dot_terminal"

#: Minted from the producer's own module constant, not invented.
MACRO_ERA = SQ_ANCHOR_ERA
#: The Terminal's own era string, recorded by the Radar contract §3.1 ("SIGNAL_ERA").
TERMINAL_ERA = "gc_v2_wo2"

#: Radar contract §3.4 constants, verbatim.
W2A_DRAWDOWN = -0.35
W2A_LOOKBACK_SESSIONS = 252
W2B_MONTHS = 3
W3_LOOKBACK_BARS = 8


def macro_constants() -> dict[str, Any]:
    """The producer's formula constants, READ OFF the module (registration §3)."""
    return {
        "producer": "engine.signal_quality:signal_frame.early",
        "anchor_era": SQ_ANCHOR_ERA,
        "grid_sessions": 3,
        "fast_grid_sessions": 2,
        "rsi_len": RSI_LEN,
        "conf_w": CONF_W,
        "os_band": OS,
        "buy_rsi_max": BUY_RSI_MAX,
        "ma_len": MA_LEN,
        "rsi_family": "engine.technicals.rsi (bare ewm) — the family signal_quality imports",
        "legs": (
            "stochBullCross(k,d) & rolling(CONF_W).min(d) < OS & rising 2D RSI-MACD "
            "histogram on the prior CLOSED 2D bar (two bars) & (weeklyBull | fromOS) & "
            "rsi14 < BUY_RSI_MAX"
        ),
    }


def terminal_constants() -> dict[str, Any]:
    """The Terminal locked spec, from Live Entry Radar contract §3.1 (cited, not guessed)."""
    return {
        "producer": "charting-app/signal_layer/confluence_v2.py::early_dots (locked-spec port)",
        "spec_source": "research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md §3.1",
        "signal_era": TERMINAL_ERA,
        "rsi_family": "engine.canon.rsi (SMA-seeded RMA, == Pine ta.rsi)",
        "rsi_len": canon.RSI_LEN,
        "macd_fast": canon.FAST_LEN,
        "macd_slow": canon.BASE_LEN,
        "macd_signal": canon.SIG_LEN,
        "stoch_len": canon.STOCH_LEN,
        "smooth_k": canon.SMOOTH_K,
        "smooth_d": canon.SMOOTH_D,
        "os_band": canon.OS,
        "conf_w": canon.CONF_W,
        "two_day_bucketing": 'pandas resample("2B").last().dropna(), left-edge label',
        "two_day_availability": "each 2B bucket's LAST actual session",
        "pit_join": "per 3D row, newest 2D state whose availability <= that row's known_ts",
        "rising_leg": "2D hist > 2D hist.shift(1) — exactly one bar, strictly greater",
        "legs": "dot = crossover(K,D) & (D.rolling(8).min() < 20) & PIT-mapped(rising2)",
        "port_deviation": (
            "3D bars cut on the Macro absolute session anchor; the Terminal's per-symbol "
            "listing anchor (bar_anchor) is not reproducible from committed artifacts"
        ),
    }


# ---------------------------------------------------------------------------
# PIT helpers
# ---------------------------------------------------------------------------
def _pit_take(
    source_known: pd.DatetimeIndex, source_vals: np.ndarray, target_known: pd.DatetimeIndex
) -> np.ndarray:
    """For each target date, the newest source value whose availability date is <= it.

    Radar §3.1's searchsorted discipline. Positions with no available source value return
    ``np.nan`` (object-safe: callers cast).
    """
    if len(source_known) == 0:
        return np.full(len(target_known), np.nan)
    pos = np.asarray(source_known).searchsorted(np.asarray(target_known), side="right") - 1
    out = np.full(len(target_known), np.nan, dtype="float64")
    ok = pos >= 0
    out[ok] = np.asarray(source_vals, dtype="float64")[pos[ok]]
    return out


def _period_last_session(daily: pd.Series, rule: str) -> pd.DataFrame:
    """Resample to ``rule`` and PIT-relabel each bucket to its LAST ACTUAL session.

    The label a resample produces is a calendar fact (a month-end, a Friday, a left edge)
    that the instrument may never have traded; the date the value became knowable is the
    bucket's last real session, so that is what is carried and what every PIT join keys on
    (Radar §3.1's searchsorted discipline).

    **The trailing bucket is always dropped.** Whether the final bucket has closed is not
    decidable from the series alone for every rule here (``2B``'s left-edge label in
    particular), so the conservative rule is the one that cannot leak: one completed bucket
    of context is forgone at the very end of history rather than risk reading a bucket
    whose value still moves. Returns a positionally-indexed frame of ``known`` and ``close``.
    """
    s = pd.to_numeric(daily, errors="coerce").dropna().sort_index()
    if s.empty:
        return pd.DataFrame({"known": pd.Series(dtype="datetime64[ns]"),
                             "close": pd.Series(dtype="float64")})
    grp = s.resample(rule)
    vals = grp.last().dropna()
    if vals.empty:
        return pd.DataFrame({"known": pd.Series(dtype="datetime64[ns]"),
                             "close": pd.Series(dtype="float64")})
    last = grp.apply(lambda x: x.index[-1] if len(x) else pd.NaT).reindex(vals.index)
    out = pd.DataFrame(
        {"known": pd.DatetimeIndex(last), "close": vals.to_numpy(dtype="float64")}
    ).reset_index(drop=True)
    return out.iloc[:-1].reset_index(drop=True)


# ---------------------------------------------------------------------------
# The Terminal washout context (Radar contract §3.4) — W1 ∧ (W2a ∨ W2b) ∧ W3
# ---------------------------------------------------------------------------
def washout_context(
    daily_close: pd.Series,
    *,
    bar_known: pd.DatetimeIndex,
    d3: pd.Series | None = None,
    below_200: pd.Series | None = None,
) -> pd.DataFrame:
    """``W1 ∧ (W2a ∨ W2b) ∧ W3`` evaluated at each 3D bar's ``known_ts``.

    Parameters
    ----------
    daily_close
        The daily close of the instrument (the plane's own series).
    bar_known
        The known-ts of each 3D bar — every leg is PIT-joined onto these dates, so no leg
        can read a bucket that had not closed when the bar became knowable.
    d3
        The 3D StochRSI %D line the caller's own dot implementation uses. W3 must read the
        SAME %D the dot read, so it is passed in rather than re-derived.
    below_200
        Optional pre-computed "3D close below the 200-session average" flag on the same
        rows. When absent it is derived from the daily 200-session mean, PIT-joined.

    Returns a frame on ``bar_known``'s positional order with the four legs and ``washed``.
    """
    n = len(bar_known)
    if n == 0:
        return pd.DataFrame(
            {c: pd.Series(dtype="bool") for c in ("w1", "w2a", "w2b", "w3", "washed")}
        )
    bk = pd.DatetimeIndex(bar_known)
    close = pd.to_numeric(daily_close, errors="coerce").dropna().sort_index()

    # --- W1: monthly RSI-MACD bear ∧ below 200DMA ∧ 2W RSI-MACD not bull ---------
    monthly = _period_last_session(close, "ME")
    if len(monthly) >= canon.BASE_LEN + canon.SIG_LEN:
        m_line, m_sig = canon.rsi_macd(pd.Series(monthly["close"].to_numpy()))
        m_bear = (m_line < m_sig).fillna(False).to_numpy(dtype="float64")
    else:
        m_bear = np.zeros(len(monthly), dtype="float64")
    w1_monthly = _pit_take(pd.DatetimeIndex(monthly["known"]), m_bear, bk) > 0.5

    biweekly = _period_last_session(close, "2W-FRI")
    if len(biweekly) >= canon.BASE_LEN + canon.SIG_LEN:
        b_line, b_sig = canon.rsi_macd(pd.Series(biweekly["close"].to_numpy()))
        b_bull = (b_line >= b_sig).fillna(False).to_numpy(dtype="float64")
    else:
        b_bull = np.zeros(len(biweekly), dtype="float64")
    w1_2w_not_bull = ~(_pit_take(pd.DatetimeIndex(biweekly["known"]), b_bull, bk) > 0.5)

    if below_200 is not None:
        w1_below = np.asarray(below_200, dtype=bool)
    else:
        ma = close.rolling(MA_LEN).mean()
        below = (close < ma).fillna(False).to_numpy(dtype="float64")
        w1_below = _pit_take(pd.DatetimeIndex(close.index), below, bk) > 0.5
    w1 = w1_monthly & w1_below & w1_2w_not_bull

    # --- W2a: 252-session drawdown <= -35% --------------------------------------
    peak = close.rolling(W2A_LOOKBACK_SESSIONS, min_periods=1).max()
    dd = (close / peak - 1.0).to_numpy(dtype="float64")
    w2a = _pit_take(pd.DatetimeIndex(close.index), dd, bk) <= W2A_DRAWDOWN

    # --- W2b: prior-closed monthly StochRSI-D < 20 for >= 3 consecutive months ---
    if len(monthly) >= canon.STOCH_LEN + canon.SMOOTH_K + canon.SMOOTH_D:
        _mk, md = canon.stoch_rsi_kd(pd.Series(monthly["close"].to_numpy()))
        deep = (md < canon.OS).fillna(False)
        streak = deep.shift(1).fillna(False).rolling(W2B_MONTHS).min().fillna(0)
        w2b_src = streak.to_numpy(dtype="float64")
    else:
        w2b_src = np.zeros(len(monthly), dtype="float64")
    w2b = _pit_take(pd.DatetimeIndex(monthly["known"]), w2b_src, bk) > 0.5

    # --- W3: 3D StochRSI-D oversold visit within 8 bars (min_periods=1) ----------
    if d3 is None:
        w3 = np.zeros(n, dtype=bool)
    else:
        dd3 = pd.Series(np.asarray(d3, dtype="float64"))
        w3 = (
            dd3.rolling(W3_LOOKBACK_BARS, min_periods=1).min() < canon.OS
        ).fillna(False).to_numpy()

    washed = w1 & (w2a | w2b) & w3
    return pd.DataFrame(
        {"w1": w1, "w2a": w2a, "w2b": w2b, "w3": w3, "washed": washed}
    )


# ---------------------------------------------------------------------------
# grey_dot_macro
# ---------------------------------------------------------------------------
def _frame_for(df: pd.DataFrame) -> pd.DataFrame:
    """``signal_frame`` on the plane's own series — the producer's own function, unmodified.

    The band is supplied wherever the plane carries it, which is exactly what the
    production callers do.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else None
    low = df["low"].astype(float) if "low" in df.columns else None
    return signal_frame(close, high, low, market="US")


def macro_fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Every ``signal_frame.early`` fire on completed 3D buckets, with washout context.

    Returns ``(event rows, diagnostics frame)``. The diagnostics frame carries the fire's
    grid coordinates and the four washout legs; it is a build-time receipt, not an artifact.
    """
    close = df["close"].astype(float)
    frame = _frame_for(df)
    if frame is None or frame.empty or "early" not in frame:
        return [], pd.DataFrame()

    grid = macro_grid(close, 3)
    if len(grid) != len(frame):
        # The frame is cut on the same grid; a mismatch means one of them saw a different
        # history and the honest move is to skip rather than align by guessing.
        return [], pd.DataFrame()

    completed = grid.completed_mask()
    fired = frame["early"].fillna(False).to_numpy().astype(bool) & completed

    ctx = washout_context(
        close,
        bar_known=pd.DatetimeIndex(grid.known.to_numpy()),
        d3=frame["d"],
        below_200=(~frame["above200"].fillna(False).astype(bool)).to_numpy(),
    )

    rows: list[dict[str, Any]] = []
    diag: list[dict[str, Any]] = []
    for i in np.flatnonzero(fired):
        signal_ts = pd.Timestamp(grid.label[i])
        known_ts = pd.Timestamp(grid.known.iloc[i])
        washed = bool(ctx["washed"].iloc[i])
        rows.append(
            ev.make_event(
                family_key=MACRO_FAMILY_KEY,
                producer="engine.signal_quality:signal_frame",
                family="grey_dot",
                subtype="early",
                stage="ANTICIPATION",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="3D",
                signal_ts=signal_ts,
                signal_known_ts=known_ts,
                known_basis=KNOWN_BASIS_BUCKET,
                signal_era=MACRO_ERA,
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="replay_recomputed",
                provenance_class="R",
                family_first_available=family_first_available,
                scored_authority=False,
                spec_postdates_history=False,
                in_washout_context=washed,
                context={
                    "w1": bool(ctx["w1"].iloc[i]),
                    "w2a": bool(ctx["w2a"].iloc[i]),
                    "w2b": bool(ctx["w2b"].iloc[i]),
                    "w3": bool(ctx["w3"].iloc[i]),
                },
            )
        )
        diag.append(
            {"symbol": symbol, "signal_ts": signal_ts, "signal_known_ts": known_ts,
             "washed": washed}
        )
    return rows, pd.DataFrame(diag)


# ---------------------------------------------------------------------------
# grey_dot_terminal — the Class B locked-spec port
# ---------------------------------------------------------------------------
def _terminal_dot_mask(daily_close: pd.Series) -> tuple[np.ndarray, pd.Series, "object"]:
    """The Radar §3.1 dot on the 3D grid. Returns ``(mask, D-line, grid)``."""
    grid = macro_grid(daily_close, 3)
    if len(grid) < 90:
        return np.zeros(len(grid), dtype=bool), pd.Series(dtype="float64"), grid

    s3 = pd.Series(grid.close.to_numpy(dtype="float64"))
    k3, d3 = canon.stoch_rsi_kd(s3)
    stoch_bull = canon.crossover(k3, d3).fillna(False).to_numpy()
    from_os = (d3.rolling(canon.CONF_W).min() < canon.OS).fillna(False).to_numpy()

    # 2D leg: calendar resample("2B"), availability = each bucket's LAST actual session,
    # PIT-joined onto the 3D row's known_ts. This is the divergence axis the archaeology
    # flagged (§4.5 item 2) and the reason this family exists separately.
    two_b = _period_last_session(daily_close, "2B")
    if len(two_b) >= canon.BASE_LEN + canon.SIG_LEN:
        m2, sg2 = canon.rsi_macd(pd.Series(two_b["close"].to_numpy()))
        hist2 = m2 - sg2
        rising2 = (hist2 > hist2.shift(1)).fillna(False).to_numpy(dtype="float64")
    else:
        rising2 = np.zeros(len(two_b), dtype="float64")
    rising_on3 = _pit_take(
        pd.DatetimeIndex(two_b["known"]), rising2, pd.DatetimeIndex(grid.known.to_numpy())
    ) > 0.5

    mask = stoch_bull & from_os & rising_on3 & grid.completed_mask()
    return mask, d3, grid


def terminal_fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Every locked-spec Terminal-twin dot on completed 3D buckets."""
    close = df["close"].astype(float)
    mask, d3, grid = _terminal_dot_mask(close)
    if not mask.any():
        return [], pd.DataFrame()

    ctx = washout_context(
        close, bar_known=pd.DatetimeIndex(grid.known.to_numpy()), d3=d3
    )
    rows: list[dict[str, Any]] = []
    diag: list[dict[str, Any]] = []
    for i in np.flatnonzero(mask):
        signal_ts = pd.Timestamp(grid.label[i])
        known_ts = pd.Timestamp(grid.known.iloc[i])
        rows.append(
            ev.make_event(
                family_key=TERMINAL_FAMILY_KEY,
                producer=(
                    "charting-app confluence_v2::early_dots (locked-spec port, "
                    "Radar contract §3.1)"
                ),
                family="grey_dot",
                subtype="early",
                stage="ANTICIPATION",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="3D",
                signal_ts=signal_ts,
                signal_known_ts=known_ts,
                known_basis=KNOWN_BASIS_BUCKET,
                signal_era=TERMINAL_ERA,
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="replay_recomputed",
                provenance_class="B",
                family_first_available=family_first_available,
                scored_authority=False,
                spec_postdates_history=True,
                in_washout_context=bool(ctx["washed"].iloc[i]),
                context={"port": "locked_spec", "grid_anchor": "macro_absolute_session"},
            )
        )
        diag.append({"symbol": symbol, "signal_ts": signal_ts, "signal_known_ts": known_ts})
    return rows, pd.DataFrame(diag)


def parity_counts(macro: pd.DataFrame, terminal: pd.DataFrame) -> dict[str, Any]:
    """Agreeing / disagreeing FIRE DATES between the twins, per name and overall.

    A count, not a verdict, and never a metric: the two families stay separate whatever
    this says (registration §3). Dates are compared on ``signal_known_ts`` — the decision
    date both implementations agree to be keyed on (Radar §3.1: "Radar consumes known_ts
    as the decision date, never ts").
    """
    def _dates(df: pd.DataFrame) -> dict[str, set]:
        if df is None or df.empty:
            return {}
        out: dict[str, set] = {}
        for sym, sub in df.groupby("symbol"):
            out[str(sym)] = {pd.Timestamp(t).date() for t in sub["signal_known_ts"]}
        return out

    a, b = _dates(macro), _dates(terminal)
    per_name: dict[str, dict[str, int]] = {}
    for sym in sorted(set(a) | set(b)):
        sa, sb = a.get(sym, set()), b.get(sym, set())
        per_name[sym] = {
            "macro_only": len(sa - sb),
            "terminal_only": len(sb - sa),
            "agree": len(sa & sb),
            "macro_total": len(sa),
            "terminal_total": len(sb),
        }
    total = {
        "agree": sum(v["agree"] for v in per_name.values()),
        "macro_only": sum(v["macro_only"] for v in per_name.values()),
        "terminal_only": sum(v["terminal_only"] for v in per_name.values()),
        "macro_total": sum(v["macro_total"] for v in per_name.values()),
        "terminal_total": sum(v["terminal_total"] for v in per_name.values()),
        "n_names": len(per_name),
    }
    return {"per_name": per_name, "total": total}
