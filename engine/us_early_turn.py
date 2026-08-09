"""engine.us_early_turn — the EARLY-TURN starter tier (ANTICIPATION §6.9 R3).

WHAT THIS IS
------------
US Prophet entry lateness decomposes (masterplan §6.9) into five causes, two of which
this module answers:

  (2) nothing admits on the EARLIEST mechanical evidence — the "dot signature";
  (5) entry = the asof close, with no structure zone.

The systematic answer is NOT predicting before evidence exists.  It is entering on the
earliest evidence tier at STARTER size with a structure-anchored zone, and letting the
slower confirmation ADD.  This module supplies the mechanical reads that decision needs:

  * :func:`turn_signature`  — the dot signature: a StochRSI %K cross up FROM WASHED plus
    a curling RSI-MACD histogram, on the daily and 2D grids.
  * :func:`extension_state` — the anti-chase read: %K on the daily AND the 3D grid, so
    a name that is stretched on both can be refused a market entry (NVDA acceptance).
  * :func:`reset_band`     — the pullback/reset band a wait plan waits AT.
  * :func:`basket_turn_context` / :func:`leader_pullback_context` — the two CONTEXTS
    that license a starter admission.  The signature alone never does.

INDICATOR PROVENANCE (binding)
------------------------------
Every indicator here is the repo's OWN, imported from :mod:`engine.confluence_tiers`:
``_stoch_rsi_kd`` (StochRSI %K/%D), ``_rsi_macd`` (the RSI-MACD pair whose difference is
the histogram), ``_tf_bars`` (the ABSOLUTE session-calendar 2D/3D grid — never
``resample``, see the session-anchor adjudication), ``_to_daily`` and ``_xup``.  There
is no parallel re-implementation of a stochastic or a MACD in this file, and there must
never be one: a second implementation is a second answer, and the board would then
disagree with the plan about whether a name crossed.

AUTHORITY
---------
DISPLAY / ADMISSION-CLASS tier only.  Nothing here originates a signal, a score, or a
rank; it re-CLASSES a row the entry ladder already admitted, and it can refuse a market
entry in favour of a zone.  No directional call is pinned (DNR:KILL-FORCED-CALLS).
Context-conditioned by construction: :func:`assess_early_turn` returns ``fired=False``
whenever neither context is present, no matter how clean the signature looks — four
anecdotes do not carry a promotion, and the §6.8(b) conditional table is what would.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from engine.confluence_tiers import (
    _rsi_macd,
    _stoch_rsi_kd,
    _tf_bars,
    _to_daily,
    _xup,
)

log = logging.getLogger(__name__)

SCHEMA = "us_early_turn.v1"
AUTHORITY = "display"

# ---------------------------------------------------------------------------
# Constants — v0, pre-registered, revisable ONLY by the §6.6 mechanics
# ---------------------------------------------------------------------------
#: %K at or below this reads as WASHED (the reset the cross must come out of).
#: 25 is the midpoint of the R4 receipt's "daily stoch reset <20-30" band.
STOCH_WASHED_MAX: float = 25.0
#: How many bars back the washed reading may sit and still count as "from washed".
#: A cross up that has no washed bar behind it is a mid-range wiggle, not a turn.
STOCH_WASHED_LOOKBACK: int = 10
#: %K at or above this reads as EXTENDED (the anti-chase side of the same ruler).
STOCH_EXTENDED_MIN: float = 80.0
#: Timeframe grids.  1 = daily; 2 = the 2D grid the dot signature reads; 3 = the 3D
#: grid the confluence tier confirms on (and the "3D signal" half of wait_reset).
TF_DAILY, TF_2D, TF_3D = 1, 2, 3
#: How recent the cross must be to count as a LIVE signature rather than history.
SIGNATURE_MAX_AGE_BARS: int = 3
#: Minimum daily bars before any read is honest.  RSI(14) → StochRSI(14) → smooth(3)
#: needs ~34 bars to be defined at all; 90 keeps the 3D grid non-degenerate too.
MIN_BARS: int = 90

#: us_basket_turn states that read as WASHOUT-MATURE — the pre/early-turn cohort a
#: starter belongs to.  CONFIRMED is deliberately NOT here: by the time a basket has
#: held TURNING for three sessions the starter window is the thing that already opened,
#: and admitting it would quietly turn the starter tier into a momentum tier.
WASHOUT_MATURE_STATES = frozenset({"WASHED_OUT", "BASING", "TURNING"})
#: The wider washout CONTEXT set — used for the zone-expiry conversion class (a V-shaped
#: recovery never revisits its band), where CONFIRMED is exactly the state that says the
#: V already happened.
WASHOUT_CONTEXT_STATES = WASHOUT_MATURE_STATES | frozenset({"CONFIRMED"})

_BASKET_ARTIFACT = ("basketdata", "us_basket_turn.json")
_MEMBERSHIP = ("baskets", "membership.json")
_NON_US_PREFIXES = ("cn_", "hk_", "ca_")


# ---------------------------------------------------------------------------
# Series plumbing
# ---------------------------------------------------------------------------

def _close_series(price_history: "pd.DataFrame | pd.Series | None",
                  asof: str | None = None) -> "pd.Series | None":
    """The PIT close series through ``asof``; ``None`` when unusable.

    The slice is POINT-IN-TIME on purpose: every caller here runs inside origination or
    a nightly re-evaluation, and a read that can see bars after the plan's price basis
    is a lookahead no downstream test would catch.
    """
    if price_history is None:
        return None
    if isinstance(price_history, pd.Series):
        s = price_history
    else:
        if getattr(price_history, "empty", True):
            return None
        cols = {str(c).lower(): c for c in price_history.columns}
        if "close" not in cols:
            return None
        s = price_history[cols["close"]]
    s = pd.Series(s).dropna()
    if s.empty:
        return None
    try:
        s.index = pd.to_datetime(s.index)
    except Exception:  # noqa: BLE001
        return None
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if asof:
        try:
            s = s[s.index <= pd.Timestamp(asof)]
        except Exception:  # noqa: BLE001
            return None
    return s if len(s) >= MIN_BARS else None


def _tf_projection(close: "pd.Series", timeframe: int
                   ) -> "tuple[pd.Series, pd.Series] | None":
    """``(k, hist)`` for ``timeframe``, projected back onto the DAILY index.

    ``timeframe=1`` is the daily series itself.  Anything else goes through
    ``_tf_bars`` — the absolute session-calendar grid — so the bucket edges are a
    function of the calendar and not of how much leading history the caller happened
    to pass (the session-anchor R1-R3 repair).  ``_to_daily`` then forward-fills the
    completed higher-timeframe bar onto daily dates, which is what makes "the 3D says
    X as of today" a well-defined statement.
    """
    try:
        if timeframe <= 1:
            k, _d = _stoch_rsi_kd(close)
            m, sig = _rsi_macd(close)
            return k, (m - sig)
        tf_close, known = _tf_bars(close, timeframe, "US")
        if tf_close is None or len(tf_close) < 40:
            return None
        k, _d = _stoch_rsi_kd(tf_close)
        m, sig = _rsi_macd(tf_close)
        di = close.index
        return _to_daily(k, known, di), _to_daily(m - sig, known, di)
    except Exception as exc:  # noqa: BLE001 — one unreadable name never kills a run
        log.info("us_early_turn: timeframe %s projection failed: %s", timeframe, exc)
        return None


def _last_finite(series: "pd.Series | None") -> float | None:
    if series is None or len(series) == 0:
        return None
    try:
        tail = pd.Series(series).dropna()
    except Exception:  # noqa: BLE001
        return None
    if tail.empty:
        return None
    value = float(tail.iloc[-1])
    return value if np.isfinite(value) else None


# ---------------------------------------------------------------------------
# The anti-chase read (NVDA acceptance: 3D signal AND daily stoch both > 80)
# ---------------------------------------------------------------------------

def extension_state(price_history: Any, asof: str | None = None) -> dict[str, Any]:
    """How stretched the name is on the daily AND the 3D grid.

    ``both_extended`` is the NVDA acceptance condition: the 3D (the timeframe the
    confluence tier confirms on) and the daily stochastic BOTH reading above
    :data:`STOCH_EXTENDED_MIN`.  A plan on such a name may only be a wait_reset zone
    plan — the entry ladder's own status word is not enough, because a name can carry
    ``buy_now`` from a daily-cycle read while both stochastics sit at 90.

    Every field is nullable and the nulls are NAMED (``source``/``reason``): a starved
    read and an honest "not extended" must never be indistinguishable, which is the
    whole reason the ext_z blackout (#4979) was a defect rather than a quiet zero.
    """
    out: dict[str, Any] = {
        "daily_stoch_k": None, "htf_stoch_k": None,
        "daily_extended": None, "htf_extended": None,
        "both_extended": False,
        "threshold": STOCH_EXTENDED_MIN,
        "htf_timeframe": TF_3D,
        "source": "price_store_stoch_rsi",
        "reason": None,
        "asof": asof,
    }
    close = _close_series(price_history, asof)
    if close is None:
        out["source"] = "unavailable"
        out["reason"] = f"fewer than {MIN_BARS} usable daily closes through {asof}"
        return out
    daily = _tf_projection(close, TF_DAILY)
    htf = _tf_projection(close, TF_3D)
    daily_k = _last_finite(daily[0]) if daily else None
    htf_k = _last_finite(htf[0]) if htf else None
    out["daily_stoch_k"] = round(daily_k, 2) if daily_k is not None else None
    out["htf_stoch_k"] = round(htf_k, 2) if htf_k is not None else None
    out["daily_extended"] = (daily_k >= STOCH_EXTENDED_MIN) if daily_k is not None else None
    out["htf_extended"] = (htf_k >= STOCH_EXTENDED_MIN) if htf_k is not None else None
    out["both_extended"] = bool(out["daily_extended"]) and bool(out["htf_extended"])
    if daily_k is None or htf_k is None:
        out["reason"] = "stochastic undefined on one or both timeframes"
    return out


# ---------------------------------------------------------------------------
# The dot signature
# ---------------------------------------------------------------------------

def turn_signature(price_history: Any, asof: str | None = None,
                   timeframe: int = TF_DAILY) -> dict[str, Any]:
    """The EARLY-TURN mechanical signature on one timeframe.

    FIRED := %K crossed up over %D within the last :data:`SIGNATURE_MAX_AGE_BARS` bars,
    the cross came OUT OF WASHED (a %K reading <= :data:`STOCH_WASHED_MAX` within
    :data:`STOCH_WASHED_LOOKBACK` bars before it), AND the RSI-MACD histogram is
    CURLING (rising on the latest bar).

    "Curling" is a first difference, not a sign test, and that is the point: the
    signature is supposed to fire BEFORE the histogram crosses zero — the cross is what
    the slower confluence tier already reports, 10-20% later (§6.9 cause 3).
    """
    out: dict[str, Any] = {
        "fired": False, "timeframe": timeframe,
        "stoch_k": None, "stoch_cross_up": False, "cross_age_bars": None,
        "from_washed": False, "washed_low": None,
        "hist": None, "hist_curling": False, "hist_delta": None,
        "reason": None, "asof": asof,
    }
    close = _close_series(price_history, asof)
    if close is None:
        out["reason"] = f"fewer than {MIN_BARS} usable daily closes through {asof}"
        return out
    projection = _tf_projection(close, timeframe)
    if projection is None:
        out["reason"] = f"timeframe {timeframe} projection unavailable"
        return out
    k_series, hist_series = projection
    try:
        _k, d_series = _stoch_rsi_kd(
            close if timeframe <= TF_DAILY else _tf_bars(close, timeframe, "US")[0])
        if timeframe > TF_DAILY:
            d_series = _to_daily(
                d_series, _tf_bars(close, timeframe, "US")[1], close.index)
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"stochastic %D unavailable: {exc}"
        return out

    k = pd.Series(k_series).astype(float)
    d = pd.Series(d_series).astype(float).reindex(k.index)
    hist = pd.Series(hist_series).astype(float).reindex(k.index)
    if k.dropna().empty or d.dropna().empty:
        out["reason"] = "stochastic undefined"
        return out

    out["stoch_k"] = round(float(k.dropna().iloc[-1]), 2)
    out["hist"] = round(float(hist.dropna().iloc[-1]), 6) if not hist.dropna().empty else None

    crosses = _xup(k, d).fillna(False).to_numpy()
    positions = np.flatnonzero(crosses)
    if positions.size == 0:
        out["reason"] = "no %K/%D cross up in the available history"
        return out
    last_pos = int(positions[-1])
    age = int(len(k) - 1 - last_pos)
    out["cross_age_bars"] = age
    out["stoch_cross_up"] = age <= SIGNATURE_MAX_AGE_BARS

    window_start = max(0, last_pos - STOCH_WASHED_LOOKBACK)
    prior = k.iloc[window_start:last_pos + 1].dropna()
    if not prior.empty:
        washed_low = float(prior.min())
        out["washed_low"] = round(washed_low, 2)
        out["from_washed"] = washed_low <= STOCH_WASHED_MAX

    hist_tail = hist.dropna()
    if len(hist_tail) >= 2:
        delta = float(hist_tail.iloc[-1] - hist_tail.iloc[-2])
        out["hist_delta"] = round(delta, 6)
        out["hist_curling"] = delta > 0.0

    out["fired"] = bool(
        out["stoch_cross_up"] and out["from_washed"] and out["hist_curling"])
    if not out["fired"] and out["reason"] is None:
        missing = [name for name, ok in (
            ("cross_up", out["stoch_cross_up"]),
            ("from_washed", out["from_washed"]),
            ("hist_curling", out["hist_curling"]),
        ) if not ok]
        out["reason"] = "signature incomplete: " + ", ".join(missing)
    return out


# ---------------------------------------------------------------------------
# Context (a) — washout maturity, from the us_basket_turn organ
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_basket_turn_membership(
    site_root: Path | None = None, data_root: Path | None = None
) -> dict[str, dict[str, Any]]:
    """``{TICKER: {state, basket_id, basket_name, data_session}}`` from us_basket_turn.

    Reads the ORGAN's published artifact (``site/basketdata/us_basket_turn.json``) and
    the curated membership it was computed over.  A ticker in several baskets keeps the
    MOST washed-out state by the cascade's own precedence, so a name that is washed in
    its own theme is not laundered into "NONE" by a broad index basket it also sits in.

    Returns ``{}`` on any absence — the callers all treat an empty context as "no
    starter licence", which is the fail-closed direction.
    """
    site = Path(site_root) if site_root else _repo_root() / "site"
    data = Path(data_root) if data_root else _repo_root() / "data"
    artifact_path = site.joinpath(*_BASKET_ARTIFACT)
    membership_path = data.joinpath(*_MEMBERSHIP)
    if not artifact_path.exists() or not membership_path.exists():
        log.info("us_early_turn: basket-turn context unavailable (%s / %s)",
                 artifact_path.exists(), membership_path.exists())
        return {}
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        membership = json.loads(membership_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("us_early_turn: basket-turn context unreadable (%s)", exc)
        return {}

    baskets = artifact.get("baskets") or {}
    curated = (membership.get("baskets") or {})
    # Precedence: the earlier a state sits in this tuple, the more washed it is.
    order = ("WASHED_OUT", "BASING", "TURNING", "CONFIRMED", "FALLING", "NONE")
    rank = {state: i for i, state in enumerate(order)}
    out: dict[str, dict[str, Any]] = {}
    for basket_id, meta in curated.items():
        if any(basket_id.startswith(prefix) for prefix in _NON_US_PREFIXES):
            continue
        row = baskets.get(basket_id)
        if not isinstance(row, Mapping):
            continue
        state = str(row.get("state") or "NONE").upper()
        for member in (meta.get("members") or []):
            ticker = str(member.get("ticker") or "").strip().upper()
            if not ticker or member.get("removed") is not None:
                continue
            prior = out.get(ticker)
            if prior is None or rank.get(state, 99) < rank.get(prior["state"], 99):
                out[ticker] = {
                    "state": state,
                    "basket_id": basket_id,
                    "basket_name": meta.get("name"),
                    "data_session": row.get("data_session"),
                }
    return out


def basket_turn_context(ticker: str,
                        membership: Mapping[str, Mapping[str, Any]] | None = None,
                        ) -> dict[str, Any]:
    """Washout context for one ticker.  ``membership`` is the map loaded once per run."""
    key = str(ticker or "").strip().upper()
    row = (membership or {}).get(key)
    if not row:
        return {
            "washout_mature": False, "washout_context": False,
            "state": None, "basket_id": None, "basket_name": None,
            "source": "us_basket_turn", "reason": "ticker is not an active US basket member",
        }
    state = str(row.get("state") or "NONE").upper()
    return {
        "washout_mature": state in WASHOUT_MATURE_STATES,
        "washout_context": state in WASHOUT_CONTEXT_STATES,
        "state": state,
        "basket_id": row.get("basket_id"),
        "basket_name": row.get("basket_name"),
        "data_session": row.get("data_session"),
        "source": "us_basket_turn",
        "reason": None,
    }


# ---------------------------------------------------------------------------
# Context (b) — leader pullback.  SEAM, not a stub with an opinion.
# ---------------------------------------------------------------------------

def leader_pullback_context(ticker: str, price_history: Any = None,
                            asof: str | None = None) -> dict[str, Any]:
    """Leader-pullback context for one ticker, from the organ that owns it.

    TODO(#5007): ``engine/us_leader_pullback.py`` is the chartered backend (R4 — the
    RS-leader universe, controlled retrace, daily stoch reset, resumption print, and
    the receipt that measured the ZONE reproducing at 7.26% → 2.29% entry-vs-low).  It
    had not merged when this shipped, so this function resolves it OPTIONALLY and
    returns a NAMED null when it is absent.  It deliberately does NOT approximate the
    organ locally: an RS-leader read invented here would be a second answer to a
    question another lane is measuring, and the ADAM/NVDA/AVGO receipts already showed
    how sensitive that read is to where in the pullback it is taken.

    Until it lands, the EARLY-TURN tier admits on WASHOUT context only, and says so.
    """
    out: dict[str, Any] = {
        "leader_pullback": False, "state": None,
        "source": "engine.us_leader_pullback", "reason": None,
    }
    try:
        from engine import us_leader_pullback  # noqa: PLC0415
    except ImportError:
        out["source"] = "unavailable"
        out["reason"] = (
            "engine.us_leader_pullback has not merged (#5007) — EARLY-TURN admits on "
            "washout context only")
        return out
    try:
        resolver = getattr(us_leader_pullback, "pullback_context", None)
        if resolver is None:
            out["source"] = "unavailable"
            out["reason"] = "engine.us_leader_pullback exposes no pullback_context()"
            return out
        ctx = resolver(ticker, price_history=price_history, asof=asof) or {}
        out.update({
            "leader_pullback": bool(ctx.get("leader_pullback")
                                    or ctx.get("state") in ("Continuation", "Ready")),
            "state": ctx.get("state"),
            "reason": ctx.get("reason"),
            "pullback_high": ctx.get("pullback_high"),
        })
    except Exception as exc:  # noqa: BLE001 — context is never fatal
        out["source"] = "error"
        out["reason"] = f"leader-pullback context failed: {exc}"
    return out


# ---------------------------------------------------------------------------
# The reset band a wait plan waits AT
# ---------------------------------------------------------------------------

def reset_band(price_history: Any, asof: str | None = None,
               atr_pct: float | None = None) -> dict[str, Any]:
    """The MA10/MA20 reset band below spot, depth-capped — the pullback entry.

    This is the SAME construction ``engine/entry_signal.assess`` applies to its wait
    statuses, and it reuses that module's own ``_ma``/``_atr_pct``/``_round_px`` rather
    than re-deriving them: the plan must wait at the band the board is showing, not at
    a second band computed a slightly different way.

    It exists here because a CONFIRMATION-status row carries the accumulate band, not a
    reset band — and a wait_reset plan on such a row (NVDA acceptance) needs the reset
    band the board never computed for it.
    """
    from engine.entry_signal import _atr_pct, _ma, _round_px  # noqa: PLC0415

    out: dict[str, Any] = {
        "low": None, "high": None, "basis": None, "spot": None,
        "reason": None, "source": "ma10_ma20_reset",
    }
    close = _close_series(price_history, asof)
    if close is None:
        out["reason"] = f"fewer than {MIN_BARS} usable daily closes through {asof}"
        out["source"] = "unavailable"
        return out
    spot = float(close.iloc[-1])
    if not np.isfinite(spot) or spot <= 0:
        out["reason"] = "last close is not a positive finite price"
        out["source"] = "unavailable"
        return out
    out["spot"] = _round_px(spot)
    atrp = atr_pct if atr_pct else _atr_pct(close, None)
    atr = spot * (float(atrp) / 100.0) if atrp else spot * 0.02
    ma10, ma20 = _ma(close, 10), _ma(close, 20)
    near = [x for x in (ma10, ma20) if x is not None and x < spot * 0.999]
    if near:
        high, low = max(near), min(near)
        basis = "MA10/MA20 reset"
    else:
        high, low = spot - 1.0 * atr, spot - 2.0 * atr
        basis = "1-2x ATR band (price already under both short MAs)"
    atr_frac = atr / spot if spot else 0.02
    deepest = spot * (1 - max(0.10, 3.0 * atr_frac))
    low = max(low, deepest)
    high = _round_px(high)
    low = _round_px(min(low, high) if high is not None else low)
    out.update({"low": low, "high": high, "basis": basis})
    return out


# ---------------------------------------------------------------------------
# The admission decision
# ---------------------------------------------------------------------------

def assess_early_turn(
    ticker: str,
    price_history: Any,
    *,
    asof: str | None = None,
    membership: Mapping[str, Mapping[str, Any]] | None = None,
    board_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Does this name qualify for the EARLY-TURN starter class?

    ``fired`` requires BOTH a mechanical signature (daily OR 2D) and a licensing
    CONTEXT (washout-mature basket membership, or leader-pullback once #5007 lands).
    A naked signature never fires: the §6.8(b) order was explicit that four anecdotes do
    not carry the promotion and only the conditional table would, so the unconditioned
    variant is not shipped even as a display chip.

    The board row is consulted ONLY as corroborating washout context (its bottoming
    lane), never as the signature — the whole point is a read the board's own state
    machine has not made yet.  The row's ``coiled.washout_ctx`` flag is deliberately not
    read: measured on the committed 2026-08-07 board it is true on 71 of 79 buy rows, so
    it carries no class information.
    """
    daily = turn_signature(price_history, asof=asof, timeframe=TF_DAILY)
    two_day = turn_signature(price_history, asof=asof, timeframe=TF_2D)
    washout = basket_turn_context(ticker, membership)
    leader = leader_pullback_context(ticker, price_history=price_history, asof=asof)

    board_washout = False
    board_reason = None
    if isinstance(board_row, Mapping):
        if str(board_row.get("lane") or "").strip().lower() == "bottoming":
            board_washout = True
            board_reason = "board lane=bottoming"

    signature_fired = bool(daily.get("fired") or two_day.get("fired"))
    context_fired = bool(washout.get("washout_mature") or leader.get("leader_pullback"))
    fired = signature_fired and context_fired

    if fired:
        reason = "signature + " + (
            "washout-mature basket" if washout.get("washout_mature")
            else "leader pullback")
    elif signature_fired:
        reason = ("signature fired but no licensing context — a naked dot is not a "
                  "starter admission")
    else:
        reason = daily.get("reason") or "no signature"

    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "ticker": str(ticker or "").strip().upper(),
        "asof": asof,
        "fired": fired,
        "signature_fired": signature_fired,
        "context_fired": context_fired,
        "signature_timeframes": [
            tf for tf, sig in ((TF_DAILY, daily), (TF_2D, two_day)) if sig.get("fired")
        ],
        "daily": daily,
        "two_day": two_day,
        "washout": washout,
        "leader_pullback": leader,
        # Corroboration only — it can never make `fired` true on its own.
        "board_washout_context": board_washout,
        "board_washout_reason": board_reason,
        "reason": reason,
    }
