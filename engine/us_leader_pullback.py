"""engine/us_leader_pullback.py — the LEADER-PULLBACK organ (US), display tier.

DISPLAY-ONLY. Authority block: tier=display, horizon_role=context,
may_rank/gate/size/escalate = false. Nothing in the pick chain imports this module;
this module imports nothing from prophet/board/rank code. Wiring into boards or plans
is a LATER PR — this file is the organ, and `research/prophet_us_audit/
leader_pullback_replay.py` is its evidence.

WHY IT EXISTS
-------------
`research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(d) / §6.9 R4. The shipped
US early-entry machinery is built around WASHOUT-IGNITION: a deep base, a cohort, and a
turn from below the 200dMA. The NVDA/AVGO/ADAM class never washes out — high-RS leaders
take a shallow, controlled retrace with the long trend intact, reset the daily oscillator,
and resume. That population is invisible to a washout detector by construction, and the
lateness forensic (§6.9) measured the cost: nothing admits on the earliest mechanical
evidence, so even the patience-status picks were up hard over the prior two sessions at
admission. This lane is the ABOVE-200 complement to the washout lane — it exists to catch
the RESET, before the resumption run.

WHAT IT PRODUCES
----------------
A per-name DAILY state frame (`evaluate`) and its last row as a display dict (`latest`).
No file is written by this module — no `site/`, no `data/`, no ledger. The states:

    LEADER      high-RS name in an intact uptrend; no qualifying pullback in progress
    PULLBACK    a controlled retrace inside the band, still above the 200dMA
    RESET_TURN  the daily oscillator reset and turned up inside that pullback
    RESUMED     price left the top of the entry zone (or the anchored VWAP) after a turn
    NONE        the leader/structure conditions do not hold

MATH — REUSED, NEVER FORKED
---------------------------
`_stoch_rsi_kd` and `_rsi_macd` are imported from `engine.confluence_tiers`, so this lane
reads the SAME StochRSI %K/%D and the SAME RSI-MACD histogram the shipped cascade reads
(faithful Wilder RSI via `engine.technicals.rsi`, NOT price MACD). Both are evaluated on
the DAILY series here — the 2D/3D bucket grids belong to the confirmation tiers; the
whole point of this lane is that it fires before them.

CLOSE-BASIS DEFINITIONS (stated, because they are load-bearing)
---------------------------------------------------------------
The US research stores this lane is measured on carry CLOSE and VOLUME, no intraday
high/low. So every "high" and "low" here is a CLOSE high / CLOSE low: the 52-week high,
the 20-session high, the pullback depth and the reset low are all close-basis. An
intraday-basis restatement would print deeper drawdowns and different reset lows; it is
a different measurement, not a refinement of this one.

The anchored VWAP is `sum(close × volume) / sum(volume)` from the pullback start — the
typical-price (HLC3) form used on charting surfaces is NOT available from a close-only
store. When a name carries no usable volume the anchored VWAP is NULL and says so
(`avwap_null_reason`); it is never fabricated, and the resumption test falls back to the
zone's own top, which is disclosed on the row.

THE LEADER LEGS GATE ENTRY, NOT CONTINUATION
--------------------------------------------
`rs_pct >= RS_TOP_PCT` and the 52-week-high recency are checked when an episode OPENS and
NOT on every bar thereafter. This is deliberate and it is the difference between a lane
that works and one that eats itself: a leader's own pullback lowers its trailing
126-session return, so requiring top-quartile RS THROUGHOUT would evict exactly the names
whose retrace is deep enough to be worth buying. Measured on the operator's own cases,
AVGO's percentile sagged to 0.728 and ADAM's to 0.649 mid-pullback while both remained in
their episodes; NVDA fell to 0.522 at its low and never entered one. The `leg_rs` /
`leg_52w` columns keep reporting the CURRENT reading on every row, so a decayed leader is
visible, never hidden — they simply stop gating once the episode is open. The trend floor
(`close > 200dMA`) and the depth band DO keep gating every bar: those are what the lane
means by "controlled".

PIT LAW
-------
Every leg reads bars at or before the evaluated session. `rs_pct` is supplied by the
caller as a PIT cross-sectional percentile (see `rs_excess_percentile`) — this module
never reaches for a cross-section itself, so a single-name call can never leak one.

CONSTANTS ARE v0 AND REVISABLE
------------------------------
The eight numbers in the CONSTRUCTION CONSTANTS block below are the v0 pre-registration
for this lane: they are named ONCE, here, printed in `CONSTANTS`, and stamped into every
artifact that measures them. They were chosen from the structure the operator receipts
describe, NOT fitted to make those receipts fire. They are revisable — but only through
the §6.6 discipline (a re-measurement at the chartered horizon, n >= 50 per cell,
sign-stable across two half-splits, on era-stamped episodes), never by tuning until a
known winner lights up (`DNR:KILL-OUTCOME-AUDITION`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.confluence_tiers import _rsi_macd, _stoch_rsi_kd

__all__ = [
    "AUTHORITY", "DISCLOSURE", "SCHEMA", "CONSTANTS", "CONSTRUCTION_ERA",
    "STATE_LEADER", "STATE_PULLBACK", "STATE_RESET_TURN", "STATE_RESUMED", "STATE_NONE",
    "STATES", "evaluate", "latest", "rs_excess_percentile",
]

# ---------------------------------------------------------------------------
# Authority block (invariant — display tier, zero authority)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

DISCLOSURE = (
    "Display-tier entry lane, v0 constants, ungauntleted. One member of the US entry "
    "battery (§6.8d) beside washout-ignition and the flow-confirmation chips — no claim "
    "that any single lane is the answer. This organ ranks nothing, gates nothing, sizes "
    "nothing and escalates nothing; it emits a per-name daily state and a structure-"
    "anchored zone. Its forward behaviour is measured in "
    "research/prophet_us_audit/LEADER_PULLBACK_REPLAY_2026-08-08.md; promotion to any "
    "authority tier requires the pre-registered §6.6 gate, not this file."
)

SCHEMA = "us_leader_pullback.v0"

#: The construction ERA these states belong to. Any constant change mints a NEW string,
#: so a graded population change is dated and labelled rather than silent (the DT-R16
#: family discipline, mirroring confluence_tiers.ANCHOR_ERA).
CONSTRUCTION_ERA = "leader-pullback-v0-2026-08-08"

# ---------------------------------------------------------------------------
# CONSTRUCTION CONSTANTS — v0, pre-registered, named once, printed
# ---------------------------------------------------------------------------

#: Relative-strength lookback in sessions. 126 ~= 6 calendar months.
RS_LOOKBACK = 126

#: LEADER admits the top quartile of the graded cross-section by RS. `rs_pct` is a
#: percentile in [0, 1]; 0.75 is the quartile boundary.
RS_TOP_PCT = 0.75

#: 52-week high lookback in sessions (close basis).
HIGH_52W_LOOKBACK = 252

#: "Made a 52-week high RECENTLY" — sessions since the last close-basis 52-week high.
HIGH_52W_RECENCY = 60

#: The reference high a pullback is measured from, at the moment the episode OPENS.
PULLBACK_HIGH_LOOKBACK = 20

#: Controlled-retrace band. Below the floor there is no pullback to buy; above the ceiling
#: the name has left this lane's population — a >20% drawdown is the washout lane's
#: business, not a leader's shallow reset.
PULLBACK_DEPTH_MIN = 0.05
PULLBACK_DEPTH_MAX = 0.20

#: Sessions from the pullback's anchor high before an un-reset pullback goes STALE. A
#: leader that has drifted sideways for five weeks is no longer resetting; it is basing,
#: which is a different construction.
PULLBACK_MAX_AGE = 25

#: The trend floor. This lane is the ABOVE-200 complement to the washout lane: losing the
#: 200dMA ends the episode here rather than deepening it.
TREND_MA = 200

#: The oscillator must have actually RESET — daily StochRSI %K below this level at some
#: point since the pullback's anchor high — before a %K-over-%D cross counts as a turn.
STOCH_RESET_MAX = 30.0

#: Consecutive session-over-session increases required of the daily RSI-MACD histogram
#: on the turn bar. 2 means h[t] > h[t-1] > h[t-2].
HIST_RISE_SESSIONS = 2

#: The entry zone covers the lower ZONE_BAND_FRACTION of the pullback's own range.
ZONE_BAND_FRACTION = 0.5

#: Sessions the RESUMED label is held after the resumption print before the episode
#: closes. A display state, not a position.
RESUMED_HOLD_SESSIONS = 20

#: Minimum daily bars before any state is emitted. The binding leg is the 52-week high
#: (HIGH_52W_LOOKBACK) plus the RSI-MACD warm-up; 260 is the house US research floor.
MIN_HISTORY_BARS = 260

CONSTANTS = {
    "rs_lookback": RS_LOOKBACK,
    "rs_top_pct": RS_TOP_PCT,
    "high_52w_lookback": HIGH_52W_LOOKBACK,
    "high_52w_recency": HIGH_52W_RECENCY,
    "pullback_high_lookback": PULLBACK_HIGH_LOOKBACK,
    "pullback_depth_min": PULLBACK_DEPTH_MIN,
    "pullback_depth_max": PULLBACK_DEPTH_MAX,
    "pullback_max_age": PULLBACK_MAX_AGE,
    "trend_ma": TREND_MA,
    "stoch_reset_max": STOCH_RESET_MAX,
    "hist_rise_sessions": HIST_RISE_SESSIONS,
    "zone_band_fraction": ZONE_BAND_FRACTION,
    "resumed_hold_sessions": RESUMED_HOLD_SESSIONS,
    "min_history_bars": MIN_HISTORY_BARS,
    "construction_era": CONSTRUCTION_ERA,
    "price_basis": "close-only (no intraday high/low in the US research stores)",
    "avwap_form": "sum(close*volume)/sum(volume) from the pullback anchor high",
}

STATE_LEADER = "LEADER"
STATE_PULLBACK = "PULLBACK"
STATE_RESET_TURN = "RESET_TURN"
STATE_RESUMED = "RESUMED"
STATE_NONE = "NONE"
STATES = (STATE_NONE, STATE_LEADER, STATE_PULLBACK, STATE_RESET_TURN, STATE_RESUMED)

#: Episode-closing reasons, emitted on the row where the episode ends.
END_BELOW_TREND = "below_200dma"
END_TOO_DEEP = "depth_exceeded_band"
END_STALE = "pullback_stale"
END_RECOVERED = "recovered_without_reset"
END_RECLAIMED = "anchor_high_reclaimed"
END_HOLD_EXPIRED = "resumed_hold_expired"

_COLUMNS = (
    "state", "days_in_state", "pullback_depth", "reset_low", "zone_low", "zone_high",
    "zone_band", "zone_basis", "zone_undercut", "pullback_high", "pullback_start",
    "pullback_age", "avwap", "avwap_null_reason", "rs_pct", "sessions_since_52w_high",
    "stoch_k", "stoch_d", "hist", "leg_rs", "leg_52w", "leg_depth", "leg_above_200",
    "leg_age", "leg_k_dip", "leg_k_cross", "leg_hist_rising", "episode_end_reason",
    "null_reason",
)


# ---------------------------------------------------------------------------
# Cross-sectional relative strength (PIT) — supplied TO the organ, never taken by it
# ---------------------------------------------------------------------------

def rs_excess_percentile(
    px_wide: pd.DataFrame,
    bench_close: pd.Series,
    *,
    lookback: int = RS_LOOKBACK,
) -> pd.DataFrame:
    """PIT cross-sectional percentile of `lookback`-session excess return vs a benchmark.

    `px_wide` is a date x ticker close frame on ONE adjustment basis; `bench_close` is the
    benchmark (SPY) close on the SAME basis. Returns a frame of percentiles in [0, 1],
    NaN wherever the name has no `lookback`-session return on that date — a name with no
    return is ABSENT from the cross-section, never imputed to the middle of it.

    HONEST NOTE ON THE BENCHMARK LEG: subtracting the benchmark return is a per-date
    CONSTANT, so `rank(excess) == rank(raw return)` and the SPY subtraction does not move
    the ordering this percentile expresses. It is retained because the excess is the
    quantity the lane reports and the quantity any future absolute-RS gate would read —
    but nothing here should be described as "vs SPY" in the sense of the benchmark doing
    selection work. It is not doing any.
    """
    if px_wide.empty:
        return px_wide.copy()
    bench = pd.to_numeric(bench_close, errors="coerce").reindex(px_wide.index).ffill()
    name_ret = px_wide / px_wide.shift(lookback) - 1.0
    bench_ret = bench / bench.shift(lookback) - 1.0
    excess = name_ret.sub(bench_ret, axis=0)
    return excess.rank(axis=1, pct=True)


# ---------------------------------------------------------------------------
# Vectorized leg precompute
# ---------------------------------------------------------------------------

def _sessions_since_true(mask: np.ndarray) -> np.ndarray:
    """Sessions since `mask` was last True, as float with NaN before the first True."""
    pos = np.arange(len(mask), dtype="float64")
    last = pd.Series(np.where(mask, pos, np.nan)).ffill().to_numpy()
    return pos - last


def _trailing_high_anchor(c: np.ndarray, window: int) -> np.ndarray:
    """Position of the LAST occurrence of the trailing-`window` close max, per session.

    NaN for the first `window - 1` sessions. The LAST occurrence is the right anchor: a
    pullback starts at the most recent print of its reference high, not the first one.
    """
    n = len(c)
    out = np.full(n, np.nan)
    if n < window:
        return out
    win = np.lib.stride_tricks.sliding_window_view(c, window)
    # argmax on the reversed window finds the LAST maximum.
    off = (window - 1) - np.argmax(win[:, ::-1], axis=1)
    out[window - 1:] = np.arange(window - 1, n) - (window - 1) + off
    return out


def _legs(close: pd.Series, volume: pd.Series | None, rs_pct: pd.Series | None) -> dict:
    c = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    c = c[~c.index.duplicated(keep="last")]
    idx = c.index
    arr = c.to_numpy(dtype="float64")

    k, d = _stoch_rsi_kd(c)
    m, s = _rsi_macd(c)
    h = m - s
    ma = c.rolling(TREND_MA, min_periods=TREND_MA).mean()
    roll_hi_20 = c.rolling(PULLBACK_HIGH_LOOKBACK, min_periods=PULLBACK_HIGH_LOOKBACK).max()
    roll_hi_52w = c.rolling(HIGH_52W_LOOKBACK, min_periods=HIGH_52W_LOOKBACK).max()

    # A close AT the trailing max IS the 52-week high (close basis).
    is_52w_high = (arr >= roll_hi_52w.to_numpy() - 1e-12) & np.isfinite(roll_hi_52w.to_numpy())
    since_52w = _sessions_since_true(is_52w_high)

    # "rising over the last HIST_RISE_SESSIONS sessions" = strictly increasing on EACH of
    # the last HIST_RISE_SESSIONS steps, i.e. h[t] > h[t-1] > ... > h[t-HIST_RISE_SESSIONS].
    hp = h.to_numpy(dtype="float64")
    rising = np.zeros(len(arr), dtype=bool)
    if len(arr) > HIST_RISE_SESSIONS:
        ok = np.ones(len(arr) - HIST_RISE_SESSIONS, dtype=bool)
        for step in range(HIST_RISE_SESSIONS):
            hi = hp[HIST_RISE_SESSIONS - step:len(arr) - step]
            lo = hp[HIST_RISE_SESSIONS - step - 1:len(arr) - step - 1]
            ok &= hi > lo
        rising[HIST_RISE_SESSIONS:] = ok

    kp, dp = k.to_numpy(dtype="float64"), d.to_numpy(dtype="float64")
    kx = np.zeros(len(arr), dtype=bool)
    if len(arr) > 1:
        kx[1:] = (kp[1:] > dp[1:]) & (kp[:-1] <= dp[:-1])

    if rs_pct is None:
        rs = np.full(len(arr), np.nan)
    else:
        rs = pd.to_numeric(rs_pct, errors="coerce").reindex(idx).to_numpy(dtype="float64")

    if volume is None:
        vol = None
    else:
        v = pd.to_numeric(volume, errors="coerce").reindex(idx)
        vol = v.to_numpy(dtype="float64")
        if not np.isfinite(vol).any() or np.nansum(vol) <= 0:
            vol = None

    return {
        "index": idx, "close": arr, "k": kp, "d": dp, "hist": hp, "ma": ma.to_numpy(dtype="float64"),
        "roll_hi_20": roll_hi_20.to_numpy(dtype="float64"),
        "anchor_pos": _trailing_high_anchor(arr, PULLBACK_HIGH_LOOKBACK),
        "since_52w": since_52w, "rs": rs, "kx": kx, "rising": rising, "vol": vol,
    }


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------

def evaluate(
    close: pd.Series,
    *,
    rs_pct: pd.Series | None = None,
    volume: pd.Series | None = None,
) -> pd.DataFrame:
    """Per-session LEADER-PULLBACK state frame for one name.

    Parameters
    ----------
    close : daily close series (DatetimeIndex).
    rs_pct : PIT cross-sectional RS percentile in [0, 1], aligned to `close`'s dates.
        None (or NaN on a date) makes the LEADER leg UNKNOWN, not False — the row prints
        `null_reason="rs_pct_unavailable"` and no state is claimed. An organ that treated
        a missing cross-section as "not a leader" would silently report a full board of
        NONE on the night the cross-section broke.
    volume : daily volume aligned to `close`. Absent or all-zero volume nulls the anchored
        VWAP (`avwap_null_reason`); it is never fabricated.

    Returns a frame indexed by `close`'s dates with the `_COLUMNS` schema. `days_in_state`
    counts sessions INCLUDING the current one (1 on the first day of a state).
    """
    L = _legs(close, volume, rs_pct)
    idx = L["index"]
    n = len(idx)
    if n == 0:
        return pd.DataFrame(columns=list(_COLUMNS))

    c, k, dd_, hist = L["close"], L["k"], L["d"], L["hist"]
    ma, roll20, anchor_pos = L["ma"], L["roll_hi_20"], L["anchor_pos"]
    since_52w, rs, kx, rising, vol = L["since_52w"], L["rs"], L["kx"], L["rising"], L["vol"]

    if vol is None:
        cum_pv = cum_v = None
        avwap_null = "no_volume_in_store"
    else:
        v = np.nan_to_num(vol, nan=0.0)
        cum_pv = np.cumsum(c * v)
        cum_v = np.cumsum(v)
        avwap_null = None

    rows = [None] * n
    state = STATE_NONE
    state_start = 0
    ep: dict | None = None

    def _avwap(start_pos: int, i: int) -> float | None:
        if cum_v is None:
            return None
        base_pv = cum_pv[start_pos - 1] if start_pos > 0 else 0.0
        base_v = cum_v[start_pos - 1] if start_pos > 0 else 0.0
        tot_v = cum_v[i] - base_v
        if not np.isfinite(tot_v) or tot_v <= 0:
            return None
        return float((cum_pv[i] - base_pv) / tot_v)

    def _blank(i: int, reason: str | None) -> dict:
        return {
            "state": None, "days_in_state": None, "pullback_depth": None, "reset_low": None,
            "zone_low": None, "zone_high": None, "zone_band": None, "zone_basis": None,
            "zone_undercut": None, "pullback_high": None, "pullback_start": None,
            "pullback_age": None, "avwap": None, "avwap_null_reason": avwap_null,
            "rs_pct": float(rs[i]) if np.isfinite(rs[i]) else None,
            "sessions_since_52w_high": None, "stoch_k": None, "stoch_d": None, "hist": None,
            "leg_rs": None, "leg_52w": None, "leg_depth": None, "leg_above_200": None,
            "leg_age": None, "leg_k_dip": None, "leg_k_cross": None, "leg_hist_rising": None,
            "episode_end_reason": None, "null_reason": reason,
        }

    for i in range(n):
        if i + 1 < MIN_HISTORY_BARS:
            rows[i] = _blank(i, f"needs {MIN_HISTORY_BARS} daily bars, has {i + 1}")
            state, state_start, ep = STATE_NONE, i, None
            continue
        cold = [nm for nm, arr_ in (("200dma", ma), ("20d_high", roll20),
                                    ("pullback_anchor", anchor_pos), ("stoch_k", k),
                                    ("stoch_d", dd_), ("rsi_macd_hist", hist))
                if not np.isfinite(arr_[i])]
        if cold:
            # A flat or perfectly monotonic series pins Wilder RSI, which makes the
            # StochRSI range zero and %K undefined. Name the input, never guess a state.
            rows[i] = _blank(i, "indicator not warm: " + ", ".join(cold))
            state, state_start, ep = STATE_NONE, i, None
            continue
        if not np.isfinite(rs[i]):
            rows[i] = _blank(i, "rs_pct_unavailable")
            state, state_start, ep = STATE_NONE, i, None
            continue

        px = c[i]
        leg_rs = bool(rs[i] >= RS_TOP_PCT)
        leg_52w = bool(np.isfinite(since_52w[i]) and since_52w[i] <= HIGH_52W_RECENCY)
        leader_ok = leg_rs and leg_52w
        above_200 = bool(px > ma[i])
        end_reason = None

        # --- episode maintenance -------------------------------------------------
        if ep is not None:
            if k[i] < STOCH_RESET_MAX:
                ep["k_dipped"] = True
            if px < ep["reset_low"]:
                ep["reset_low"] = float(px)
            depth = 1.0 - px / ep["high"]
            age = i - ep["start_pos"]

            if not above_200:
                end_reason = END_BELOW_TREND
            elif depth > PULLBACK_DEPTH_MAX:
                end_reason = END_TOO_DEEP
            elif px >= ep["high"]:
                end_reason = END_RECLAIMED
            elif state == STATE_PULLBACK and depth < PULLBACK_DEPTH_MIN:
                end_reason = END_RECOVERED
            elif state == STATE_PULLBACK and age > PULLBACK_MAX_AGE:
                end_reason = END_STALE
            elif state == STATE_RESUMED and (i - ep["resumed_pos"]) > RESUMED_HOLD_SESSIONS:
                end_reason = END_HOLD_EXPIRED

            if end_reason is not None:
                ep = None
                new_state = STATE_LEADER if leader_ok else STATE_NONE
                if new_state != state:
                    state, state_start = new_state, i

        # --- episode opening -----------------------------------------------------
        # An episode never opens on the bar another one ENDED: that bar's job is to report
        # the ending. Episodes ARE re-openable a bar later — a name that broke the band can
        # re-qualify once its trailing-20 reference high has re-formed — and the LEADER legs
        # (top-quartile RS, a 52-week high inside HIGH_52W_RECENCY, above the 200dMA) are
        # what keep that from degenerating into a falling-knife lane.
        if ep is None and end_reason is None:
            depth20 = 1.0 - px / roll20[i] if np.isfinite(roll20[i]) and roll20[i] > 0 else np.nan
            in_band = bool(
                np.isfinite(depth20)
                and PULLBACK_DEPTH_MIN <= depth20 <= PULLBACK_DEPTH_MAX
            )
            if leader_ok and in_band and above_200:
                start_pos = int(anchor_pos[i])
                seg = c[start_pos:i + 1]
                ep = {
                    "start_pos": start_pos,
                    "high": float(roll20[i]),
                    "reset_low": float(np.nanmin(seg)),
                    "k_dipped": bool(np.nanmin(k[start_pos:i + 1]) < STOCH_RESET_MAX)
                    if np.isfinite(k[start_pos:i + 1]).any() else False,
                    "reset_pos": None, "resumed_pos": None,
                    "zone_low": None, "zone_high": None, "zone_band": None,
                }
                state, state_start = STATE_PULLBACK, i
            else:
                new_state = STATE_LEADER if leader_ok else STATE_NONE
                if new_state != state:
                    state, state_start = new_state, i

        # --- transitions INSIDE the episode --------------------------------------
        # Runs AFTER the opening block so a pullback that opens on the very bar its
        # oscillator turns can print RESET_TURN that same session — this lane's whole
        # purpose is to not be a bar late. RESUMED can never share a bar with the turn:
        # the resumption is the NEXT thing that happens, by construction.
        if ep is not None and end_reason is None:
            if state == STATE_PULLBACK and ep["k_dipped"] and kx[i] and rising[i]:
                state, state_start = STATE_RESET_TURN, i
                ep["reset_pos"] = i
                ep["zone_low"] = float(ep["reset_low"])
                ep["zone_band"] = float(ep["high"] - ep["reset_low"])
                ep["zone_high"] = float(ep["reset_low"] + ZONE_BAND_FRACTION * ep["zone_band"])
            elif state == STATE_RESET_TURN:
                av_now = _avwap(ep["start_pos"], i)
                if px > ep["zone_high"] or (av_now is not None and px > av_now):
                    state, state_start = STATE_RESUMED, i
                    ep["resumed_pos"] = i

        # --- emit ----------------------------------------------------------------
        if ep is None:
            rows[i] = {
                "state": state, "days_in_state": i - state_start + 1,
                "pullback_depth": None, "reset_low": None, "zone_low": None,
                "zone_high": None, "zone_band": None, "zone_basis": None,
                "zone_undercut": None, "pullback_high": None, "pullback_start": None,
                "pullback_age": None, "avwap": None, "avwap_null_reason": avwap_null,
                "rs_pct": float(rs[i]), "sessions_since_52w_high":
                    float(since_52w[i]) if np.isfinite(since_52w[i]) else None,
                "stoch_k": float(k[i]), "stoch_d": float(dd_[i]), "hist": float(hist[i]),
                "leg_rs": leg_rs, "leg_52w": leg_52w, "leg_depth": None,
                "leg_above_200": above_200, "leg_age": None, "leg_k_dip": None,
                "leg_k_cross": bool(kx[i]), "leg_hist_rising": bool(rising[i]),
                "episode_end_reason": end_reason, "null_reason": None,
            }
            continue

        depth = 1.0 - px / ep["high"]
        age = i - ep["start_pos"]
        av = _avwap(ep["start_pos"], i)
        zl, zh = ep["zone_low"], ep["zone_high"]
        rows[i] = {
            "state": state, "days_in_state": i - state_start + 1,
            "pullback_depth": float(depth), "reset_low": float(ep["reset_low"]),
            "zone_low": zl, "zone_high": zh, "zone_band": ep["zone_band"],
            "zone_basis": "pullback_range_close_basis" if zl is not None else None,
            "zone_undercut": bool(px < zl) if zl is not None else None,
            "pullback_high": float(ep["high"]),
            "pullback_start": idx[ep["start_pos"]], "pullback_age": int(age),
            "avwap": av, "avwap_null_reason": avwap_null if av is None else None,
            "rs_pct": float(rs[i]),
            "sessions_since_52w_high": float(since_52w[i]) if np.isfinite(since_52w[i]) else None,
            "stoch_k": float(k[i]), "stoch_d": float(dd_[i]), "hist": float(hist[i]),
            "leg_rs": leg_rs, "leg_52w": leg_52w,
            "leg_depth": bool(PULLBACK_DEPTH_MIN <= depth <= PULLBACK_DEPTH_MAX),
            "leg_above_200": above_200, "leg_age": bool(age <= PULLBACK_MAX_AGE),
            "leg_k_dip": bool(ep["k_dipped"]), "leg_k_cross": bool(kx[i]),
            "leg_hist_rising": bool(rising[i]), "episode_end_reason": end_reason,
            "null_reason": None,
        }

    out = pd.DataFrame(rows, index=idx)
    return out[list(_COLUMNS)]


def latest(
    close: pd.Series,
    *,
    rs_pct: pd.Series | None = None,
    volume: pd.Series | None = None,
) -> dict:
    """The last evaluated session as a JSON-safe display dict (numpy scalars cast out)."""
    frame = evaluate(close, rs_pct=rs_pct, volume=volume)
    if frame.empty:
        return {"schema": SCHEMA, "construction_era": CONSTRUCTION_ERA,
                "asof": None, "state": None, "null_reason": "no_price_history"}
    row = frame.iloc[-1]
    out = {"schema": SCHEMA, "construction_era": CONSTRUCTION_ERA,
           "asof": str(frame.index[-1].date())}
    for col in _COLUMNS:
        v = row[col]
        if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v):
            out[col] = None
        elif isinstance(v, (bool, np.bool_)):
            out[col] = bool(v)
        elif isinstance(v, (int, np.integer)):
            out[col] = int(v)
        elif isinstance(v, (float, np.floating)):
            out[col] = float(v)
        elif isinstance(v, pd.Timestamp):
            out[col] = str(v.date())
        else:
            out[col] = str(v)
    return out
