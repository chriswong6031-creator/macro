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

#: us_leader_pullback states that read as LEADER-PULLBACK context — the organ's own
#: vocabulary for "uptrend intact + controlled reset": an OPEN pullback episode in a
#: high-RS leader (top-quartile RS and a 52-week high at the open, above the 200dMA and
#: inside the 5-20% depth band on every bar thereafter).  PULLBACK is the retrace itself;
#: RESET_TURN is that same episode after its daily oscillator reset and turned.
#:
#: RESUMED is deliberately NOT here, for exactly the reason CONFIRMED is absent from
#: :data:`WASHOUT_MATURE_STATES`: price has already left the top of the entry zone, so
#: the starter window is the thing that already opened and admitting it would quietly
#: turn the starter tier into a momentum tier.  LEADER is absent because it is the state
#: for a leader with NO qualifying pullback in progress — an intact uptrend with nothing
#: to reset into is a chase licence, not a starter licence.  NONE covers nothing.
LEADER_PULLBACK_CONTEXT_STATES = frozenset({"PULLBACK", "RESET_TURN"})

#: The EXHAUSTIVE context vocabulary.  Every licensing context an EARLY-TURN row can
#: disclose is one of these two names; ``context_sources`` on the emitted row is an
#: ordered subset of this tuple and can never carry anything else.
CONTEXT_WASHOUT = "washout"
CONTEXT_LEADER_PULLBACK = "leader_pullback"
CONTEXT_SOURCES: tuple[str, ...] = (CONTEXT_WASHOUT, CONTEXT_LEADER_PULLBACK)
#: Plain-word label per context, used in the emitted ``reason``.
_CONTEXT_LABELS = {
    CONTEXT_WASHOUT: "washout-mature basket",
    CONTEXT_LEADER_PULLBACK: "leader pullback",
}

_BASKET_ARTIFACT = ("basketdata", "us_basket_turn.json")
_MEMBERSHIP = ("baskets", "membership.json")
_LEADER_ARTIFACT = ("anticipationdata", "us_leader_pullback.json")
_LEADER_SCHEMA = "us_leader_pullback.v0"
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
# Context (b) — leader pullback, from the us_leader_pullback organ (#5007)
# ---------------------------------------------------------------------------

def load_leader_pullback_states(
    site_root: Path | None = None
) -> dict[str, dict[str, Any]]:
    """``{TICKER: <us_leader_pullback.latest() row>}`` — the organ's coverage this run.

    WHY A MAP AND NOT A PER-NAME CALL.  ``engine.us_leader_pullback`` writes no file by
    design, and its state needs ``rs_pct`` — a PIT CROSS-SECTIONAL percentile the organ
    refuses to reach for itself, precisely so a single-name call can never leak one.  A
    per-name series therefore cannot produce a state, and an RS read invented here would
    be a second answer to the question that lane measures (the ADAM/NVDA/AVGO receipts
    showed how sensitive it is to WHERE in the pullback it is taken).  So coverage
    arrives as a per-run MAP, published by whoever holds the cross-section — exactly the
    shape :func:`load_basket_turn_membership` gives the washout half.

    Accepts ``{"schema": ..., "states": {TICKER: row}}`` or a bare ``{TICKER: row}``.

    Returns ``{}`` on ANY absence — no artifact, unreadable JSON, wrong schema.  No
    nightly builder publishes this artifact yet, so on a live run today this returns
    ``{}``, every name reads NOT leader-context, and :func:`leader_pullback_context`
    says so by name.  That is the fail-closed direction: a starter class is a licence,
    and a licence that cannot be resolved is not granted.
    """
    site = Path(site_root) if site_root else _repo_root() / "site"
    path = site.joinpath(*_LEADER_ARTIFACT)
    if not path.exists():
        log.info("us_early_turn: leader-pullback coverage unavailable (%s)", path)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("us_early_turn: leader-pullback coverage unreadable (%s)", exc)
        return {}
    if not isinstance(payload, Mapping):
        return {}
    schema = str(payload.get("schema") or "")
    if schema and not schema.startswith(_LEADER_SCHEMA.rsplit(".", 1)[0]):
        log.warning("us_early_turn: leader-pullback coverage has schema %s, expected %s",
                    schema, _LEADER_SCHEMA)
        return {}
    raw = payload.get("states") if "states" in payload else payload
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for ticker, row in raw.items():
        key = str(ticker or "").strip().upper()
        if key and isinstance(row, Mapping):
            out[key] = dict(row)
    return out


def leader_pullback_context(ticker: str, price_history: Any = None,
                            asof: str | None = None, *,
                            states: Mapping[str, Mapping[str, Any]] | None = None,
                            ) -> dict[str, Any]:
    """Leader-pullback context for one ticker, from the organ that owns it (#5007).

    ``leader_pullback`` is true when the organ's state for the name is in
    :data:`LEADER_PULLBACK_CONTEXT_STATES` — an OPEN, controlled pullback episode in a
    high-RS leader, before the resumption print.  The state is read exactly as the organ
    published it: v0 constants, ungauntleted, and carrying that lane's two known v0
    limitations (an RS percentile measured AT the low is depressed by the pullback
    itself; the ADAM two-leg timing case).  Neither is tuned here — this is a CONSUMER.

    CONTEXT, NOT ADMISSION.  The organ's own replay graded RESET_TURN a NULL as a
    standalone signal and RETAINED it as a confluence input; licensing a signature that
    fired on its own evidence is exactly that role.  Nothing here originates a signal.

    ``price_history`` is accepted for call-shape compatibility and deliberately NOT read
    — see :func:`load_leader_pullback_states` for why a per-name series cannot produce
    this state.  ``asof`` IS read, as a PIT guard: an organ row dated after the caller's
    price basis is refused rather than used, because a context computed on bars the plan
    could not see is a lookahead no downstream test would catch.

    Fails CLOSED on every absence, each with its own named reason: no coverage
    published, ticker outside the organ's universe, a row the organ itself nulled, or a
    row that postdates ``asof``.  A name the organ does not cover is NOT leader-context.
    """
    out: dict[str, Any] = {
        "leader_pullback": False, "state": None, "pullback_high": None,
        "days_in_state": None, "construction_era": None, "state_asof": None,
        "context_states": sorted(LEADER_PULLBACK_CONTEXT_STATES),
        "source": "unavailable", "reason": None,
    }
    key = str(ticker or "").strip().upper()
    try:
        coverage = load_leader_pullback_states() if states is None else states
    except Exception as exc:  # noqa: BLE001 — context is never fatal
        out["source"] = "error"
        out["reason"] = f"leader-pullback coverage failed: {exc}"
        return out
    if not coverage:
        out["reason"] = ("the leader-pullback organ published no coverage for this run "
                         "— EARLY-TURN admits on washout context only")
        return out
    row = coverage.get(key)
    if not isinstance(row, Mapping):
        out["reason"] = "ticker is outside the leader-pullback organ's universe"
        return out

    state_asof = row.get("asof")
    out["state_asof"] = state_asof
    out["construction_era"] = row.get("construction_era")
    if asof and state_asof and str(state_asof) > str(asof):
        out["reason"] = (f"leader-pullback state is dated {state_asof}, after the price "
                         f"basis {asof} — refused as a lookahead")
        return out

    state = row.get("state")
    if state is None:
        out["reason"] = (f"the organ nulled this name: "
                         f"{row.get('null_reason') or 'no state emitted'}")
        return out

    state = str(state).upper()
    out.update({
        "leader_pullback": state in LEADER_PULLBACK_CONTEXT_STATES,
        "state": state,
        "pullback_high": row.get("pullback_high"),
        "days_in_state": row.get("days_in_state"),
        "source": "us_leader_pullback",
        "reason": None if state in LEADER_PULLBACK_CONTEXT_STATES else (
            f"organ state {state} is not an open controlled pullback"),
    })
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
# UNION ADMISSION — the measured recall spine (bake-off §A2)
# ---------------------------------------------------------------------------
#: Era stamp for the admission CLASS this leg mints (#4942 era-stamp law).  A row that
#: admitted under a different construction must never be compared with one that admitted
#: under this one without the stamp being visible on both.
UNION_ADMISSION_ERA = "union-admission-v1-2026-08-11"

#: Both 3D StochRSI lines strictly under this AT THE CROSS BAR.  This is the operator's
#: "the crossover must be done under the 20 line", measured in the bake-off as C1.
UNION_OS_BAND: float = 20.0
#: The 1D MACD-RSI confirm may already be IN FORCE at the 3D knowability date, provided
#: its last cross-up printed within this many sessions.
UNION_1D_RECENT_SESSIONS: int = 5
#: Otherwise the confirm may still ARRIVE: the first fresh 1D cross-up within this many
#: sessions after knowability fires the admission at THAT session.
UNION_1D_WAIT_SESSIONS: int = 10
#: Context badge only (§A2 "proximity, not durability"): the deepest 3D %K print in the
#: buckets before the cross, and the threshold that reads as a zero-bound tag.
UNION_ZERO_BOUND: float = 2.0
UNION_ZERO_LOOKBACK_BARS: int = 10
#: Context badges: the decline the fire sits in, and the relative-strength window.
UNION_DECLINE_WINDOW: int = 126
UNION_RS_WINDOW: int = 63
UNION_MA_LEN: int = 200

#: The two legs of the measured union.  ``relaxed_cross`` is the recall spine; ``early_dot``
#: is the anticipation chip the store already publishes.  Named, never numbered.
UNION_LEG_CROSS = "relaxed_cross"
UNION_LEG_DOT = "early_dot"
UNION_LEGS: tuple[str, ...] = (UNION_LEG_CROSS, UNION_LEG_DOT)


def _union_relaxed_cross_fires(close: "pd.Series") -> "list[tuple[int, int, dict]]":
    """Fire positions for the RELAXED washout-cross leg, on the daily index.

    Returns ``[(fire_pos, cross_bar_row, badge_inputs)]``.  The 3D grid comes from
    :func:`engine.confluence_tiers._tf_bars`, whose index IS each bucket's last session —
    so a 3D event is stamped at the close on which it became knowable (G0.4) with no
    open-label round trip.
    """
    tf_close, _known = _tf_bars(close, TF_3D, "US")
    if tf_close is None or len(tf_close) < 40:
        return []
    k, d = _stoch_rsi_kd(tf_close)
    deep = (k < UNION_OS_BAND) & (d < UNION_OS_BAND)
    sel = (_xup(k, d) & deep).fillna(False).to_numpy()
    if not sel.any():
        return []
    # deepest %K in the buckets BEFORE the cross — the zero-bound context badge
    k_prior_min = k.shift(1).rolling(UNION_ZERO_LOOKBACK_BARS, min_periods=1).min()

    macd1, sig1 = _rsi_macd(close)
    in_force = (macd1 >= sig1).fillna(False).to_numpy()
    xup1 = _xup(macd1, sig1).fillna(False).to_numpy()
    di = close.index
    kn_pos = di.searchsorted(pd.DatetimeIndex(tf_close.index), side="left")

    out: list[tuple[int, int, dict]] = []
    for row in np.flatnonzero(sel):
        i = int(kn_pos[row])
        if i >= len(di) or di[i] != tf_close.index[row]:
            continue                      # bucket-last not a session of THIS series
        badges = {"k_at_cross": float(k.iloc[row]) if np.isfinite(k.iloc[row]) else None,
                  "d_at_cross": float(d.iloc[row]) if np.isfinite(d.iloc[row]) else None,
                  "k_prior_min": (float(k_prior_min.iloc[row])
                                  if np.isfinite(k_prior_min.iloc[row]) else None)}
        prior = np.flatnonzero(xup1[: i + 1])
        recent = prior.size and (i - int(prior[-1])) <= UNION_1D_RECENT_SESSIONS
        if in_force[i] and recent:
            out.append((i, int(row), {**badges, "confirm": "in_force"}))
            continue
        nxt = np.flatnonzero(xup1[i + 1: i + 1 + UNION_1D_WAIT_SESSIONS])
        if nxt.size:
            j = i + 1 + int(nxt[0])
            out.append((j, int(row), {**badges, "confirm": "arrived",
                                      "wait_sessions": j - i}))
        # no confirm inside the window: the washout cross alone never admits
    return out


def _union_early_dot_fires(close: "pd.Series") -> "list[tuple[int, int, dict]]":
    """Fire positions for the DOT leg, read from the engine's own ``early`` column.

    The dot is NOT re-derived here: :func:`engine.signal_quality.signal_frame` owns that
    definition and this reads its output, so the deck and the published store can never
    disagree about whether a name dotted.  ``signal_frame`` is close-driven for this leg,
    so a close-only history is exact.
    """
    try:
        from engine.signal_quality import signal_frame
    except Exception as exc:  # noqa: BLE001
        log.info("us_early_turn: dot leg unavailable (%s)", exc)
        return []
    try:
        frame = signal_frame(close, market="US")
    except Exception as exc:  # noqa: BLE001
        log.info("us_early_turn: signal_frame failed (%s)", exc)
        return []
    if frame is None or len(frame) == 0 or "early" not in frame:
        return []
    tf_close, _known = _tf_bars(close, TF_3D, "US")
    if tf_close is None or len(tf_close) != len(frame):
        # The two grids are the same bucketing; a length mismatch means one of them saw a
        # different history and the honest move is to skip the leg rather than guess.
        return []
    sel = frame["early"].fillna(False).to_numpy().astype(bool)
    di = close.index
    kn_pos = di.searchsorted(pd.DatetimeIndex(tf_close.index), side="left")
    out: list[tuple[int, int, dict]] = []
    for row in np.flatnonzero(sel):
        i = int(kn_pos[row])
        if i < len(di) and di[i] == tf_close.index[row]:
            out.append((i, int(row), {}))
    return out


def _union_badges(close: "pd.Series", pos: int, cross: Mapping[str, Any] | None,
                  benchmark: "pd.Series | None") -> dict[str, Any]:
    """DISPLAY-tier context carried on an admitted row.

    Every value here is texture, never a rank or tier input: the bake-off's §R8 ledger
    plus the footprint study's §A3 found no static feature that survives risk
    equalization, so nothing on this row may imply reliability or ordering.
    """
    c = close.to_numpy(dtype="float64")
    spot = float(c[pos])
    badges: dict[str, Any] = {
        "era": UNION_ADMISSION_ERA,
        "k_at_cross": None, "zero_bound": None, "decline_depth": None,
        "above_200": None, "rs_63": None,
    }
    if cross:
        kx = cross.get("k_at_cross")
        badges["k_at_cross"] = round(float(kx), 2) if kx is not None else None
        kmin = cross.get("k_prior_min")
        badges["zero_bound"] = (bool(kmin <= UNION_ZERO_BOUND) if kmin is not None
                                else None)
    a = max(0, pos - UNION_DECLINE_WINDOW)
    hi = float(np.nanmax(c[a: pos + 1]))
    if np.isfinite(hi) and hi > 0:
        badges["decline_depth"] = round(spot / hi - 1.0, 4)
    if pos + 1 >= UNION_MA_LEN:
        ma = float(np.nanmean(c[pos + 1 - UNION_MA_LEN: pos + 1]))
        if np.isfinite(ma) and ma > 0:
            badges["above_200"] = bool(spot > ma)
    if pos >= UNION_RS_WINDOW and c[pos - UNION_RS_WINDOW] > 0:
        own = spot / c[pos - UNION_RS_WINDOW] - 1.0
        if benchmark is None or len(benchmark) == 0:
            badges["rs_63"] = None            # no benchmark loaded: a null, never a zero
        else:
            di = close.index
            b = pd.Series(benchmark).dropna()
            i1 = int(b.index.searchsorted(di[pos], side="right")) - 1
            i0 = int(b.index.searchsorted(di[pos - UNION_RS_WINDOW], side="right")) - 1
            if i0 >= 0 and i1 > i0 and float(b.iloc[i0]) > 0:
                badges["rs_63"] = round(
                    float(own - (float(b.iloc[i1]) / float(b.iloc[i0]) - 1.0)), 4)
    return badges


def union_admission(price_history: Any, asof: str | None = None, *,
                    benchmark: Any = None) -> dict[str, Any]:
    """The UNION admission signature (bake-off §A2) — the measured recall spine.

    ``fired`` when the most recent union fire at or before ``asof`` is no older than
    :data:`SIGNATURE_MAX_AGE_BARS` — the same liveness scope every other signature in this
    module uses, so "live now" means one thing on the deck.

    The union is the two measured legs:

      (a) **relaxed washout cross** — a 3D StochRSI %K x %D bull cross with BOTH lines
          under 20 at the cross bar, confirmed by the 1D MACD-RSI either already in force
          (its last cross-up within 5 sessions) at the bucket's last close, or by the first
          fresh 1D cross-up within the next 10 sessions.  Fires at the confirming session.
      (b) **the dot** — the engine's own ``early`` leg, read from
          :func:`engine.signal_quality.signal_frame`, retained as the anticipation chip.

    STARTER GRADE ONLY.  This mints an admission CLASS; it never touches the scored gate,
    a tier, or a rank, and the badges it carries are texture (§A2: proximity, not
    durability — no durability tier is licensed by any measured feature).
    """
    out: dict[str, Any] = {
        "fired": False, "era": UNION_ADMISSION_ERA, "legs": [], "fire_date": None,
        "age_bars": None, "confirm": None, "wait_sessions": None,
        "badges": None, "reason": None, "asof": asof,
    }
    close = _close_series(price_history, asof)
    if close is None:
        out["reason"] = f"fewer than {MIN_BARS} usable daily closes through {asof}"
        return out
    try:
        cross_fires = _union_relaxed_cross_fires(close)
        dot_fires = _union_early_dot_fires(close)
    except Exception as exc:  # noqa: BLE001 — one unreadable name never kills a run
        log.info("us_early_turn: union admission failed: %s", exc)
        out["reason"] = f"union admission unavailable: {exc}"
        return out
    if not cross_fires and not dot_fires:
        out["reason"] = "no washout cross with a 1D confirm, and no dot, in this history"
        return out

    by_pos: dict[int, dict[str, Any]] = {}
    for pos, _row, meta in cross_fires:
        e = by_pos.setdefault(pos, {"legs": [], "cross": None})
        e["legs"].append(UNION_LEG_CROSS)
        e["cross"] = meta
    for pos, _row, _meta in dot_fires:
        e = by_pos.setdefault(pos, {"legs": [], "cross": None})
        e["legs"].append(UNION_LEG_DOT)

    last_pos = max(by_pos)
    entry = by_pos[last_pos]
    age = int(len(close) - 1 - last_pos)
    bench = None
    if benchmark is not None:
        try:
            bench = _close_series(benchmark, asof)
        except Exception:  # noqa: BLE001
            bench = None
    out["legs"] = [leg for leg in UNION_LEGS if leg in entry["legs"]]
    out["fire_date"] = str(pd.Timestamp(close.index[last_pos]).date())
    out["age_bars"] = age
    out["confirm"] = (entry["cross"] or {}).get("confirm")
    out["wait_sessions"] = (entry["cross"] or {}).get("wait_sessions")
    out["badges"] = _union_badges(close, last_pos, entry["cross"], bench)
    out["fired"] = age <= SIGNATURE_MAX_AGE_BARS
    if not out["fired"]:
        out["reason"] = (f"most recent union admission is {age} sessions old "
                         f"(live window is {SIGNATURE_MAX_AGE_BARS})")
    return out


# ---------------------------------------------------------------------------
# SETUP GEOMETRY — the early lane's own score (operator ruling 2026-08-11)
# ---------------------------------------------------------------------------
# A GEOMETRY score, never a probability score.  It answers "how good is the trade
# available RIGHT NOW", from three things a chart shows and nothing a backtest inferred:
#
#   (a) how far today's entry sits above the structural stop      (lower = better)
#   (b) whether the low that stop hangs under is a CONFIRMED pivot (cleaner = better)
#   (c) how far price has already travelled from the fire         (a chase = worse)
#
# (c) is why this is scored today and not on the signal's birthday: a fire that has run
# +10% off its low is a chase, and it must sort BELOW a fresh one no matter how good the
# original signature looked.
#
# What is deliberately NOT in here, and is test-pinned absent: any durability or P(win)
# claim, the §8 / footprint features that were nulled under risk-equalization, member-share
# theme breadth, and the retracted repeat-fire flag.  The basket TURNING/CONFIRMED read may
# sit BESIDE a row as display context — it has its own forward ledger — but it is not an
# input here.
#: Risk this far above the structural stop scores zero on the risk leg.  Not a threshold
#: anyone may act on — the ordering key's floor, so the leg cannot run away.
GEOMETRY_RISK_CAP: float = 0.15
#: Travel from the fire that fully spends the freshness leg (the operator's "+10% is a
#: chase" example).
GEOMETRY_CHASE_CAP: float = 0.10
#: How much of the score the freshness leg may take away.
GEOMETRY_DECAY_WEIGHT: float = 0.45
#: What a CONFIRMED reference pivot is worth against an unconfirmed raw low.
GEOMETRY_CONFIRMED_BONUS: float = 8.0
#: The decline-low lookback the structural stop hangs under, and the stop's own haircut —
#: the same P_low x 0.99 basis the bake-off measured stop-A survival on.
GEOMETRY_LOW_LOOKBACK: int = 45
GEOMETRY_STOP_K: float = 0.99
#: Radius of the confirmed swing low the stop-structure flag reads.
PIVOT_RADIUS_R3: int = 3

#: The stage a row is at.  A FACT column, never a score and never blended into one: the
#: early lane's geometry score and the confirmed lane's own score stay two numbers.
STAGE_EARLY = "EARLY"
STAGE_CONFIRMING = "CONFIRMING"
STAGE_CONFIRMED = "CONFIRMED"


def _confirmed_pivot_low(low: "np.ndarray", end: int) -> tuple[float | None, int | None]:
    """The most recent r3-CONFIRMED swing low knowable at ``end`` (pivot at p, strict min
    of lows[p-3..p+3], knowable at p+3)."""
    for p in range(end - PIVOT_RADIUS_R3, PIVOT_RADIUS_R3 - 1, -1):
        w = low[p - PIVOT_RADIUS_R3: p + PIVOT_RADIUS_R3 + 1]
        if len(w) < 2 * PIVOT_RADIUS_R3 + 1 or not np.isfinite(w).all():
            continue
        if low[p] < np.min(np.delete(w, PIVOT_RADIUS_R3)):
            return float(low[p]), int(p)
    return None, None


def setup_geometry(price_history: Any, asof: str | None = None, *,
                   union: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The early lane's GEOMETRY score — the trade available today, not the signal's age.

    Returns the three legs as data plus ``score`` (0-100, an ORDERING KEY for the deck's
    sort).  It is not a probability, it is not calibrated, and it never claims a name will
    work: two rows with the same score have the same geometry, nothing more.
    """
    out: dict[str, Any] = {
        "score": None, "risk_pct": None, "stop": None, "reference_low": None,
        "stop_confirmed": None, "chase_pct": None, "age_bars": None,
        "basis": "distance to the structural stop, how clean that stop is, "
                 "and how far price has travelled since the fire",
        "reason": None,
    }
    close = _close_series(price_history, asof)
    if close is None:
        out["reason"] = f"fewer than {MIN_BARS} usable daily closes through {asof}"
        return out
    lows = _low_series(price_history, close)
    c = close.to_numpy(dtype="float64")
    end = len(c) - 1
    spot = float(c[end])
    if not np.isfinite(spot) or spot <= 0:
        out["reason"] = "last close is not a positive finite price"
        return out

    a = max(0, end - GEOMETRY_LOW_LOOKBACK)
    raw_low = float(np.nanmin(lows[a: end + 1]))
    pivot_low, pivot_pos = _confirmed_pivot_low(lows, end)
    # The stop hangs under the decline low that is actually in force. When the most recent
    # CONFIRMED pivot is that same low, the stop is structurally clean; otherwise it is
    # hanging under a raw low the tape has not yet defended, and the row says so.
    confirmed = bool(pivot_low is not None and np.isfinite(raw_low)
                     and abs(pivot_low - raw_low) <= 1e-9)
    if not np.isfinite(raw_low) or raw_low <= 0:
        out["reason"] = "no usable decline low in the lookback"
        return out
    stop = raw_low * GEOMETRY_STOP_K
    if stop >= spot:
        out["reason"] = "price is at or below its own structural stop"
        return out
    risk = (spot - stop) / spot

    chase = None
    age = None
    if isinstance(union, Mapping) and union.get("fire_date"):
        try:
            fire_pos = int(close.index.searchsorted(pd.Timestamp(union["fire_date"]),
                                                    side="left"))
            if 0 <= fire_pos <= end and float(c[fire_pos]) > 0:
                chase = float(spot / float(c[fire_pos]) - 1.0)
                age = int(end - fire_pos)
        except Exception:  # noqa: BLE001
            chase = None

    risk_leg = 100.0 * max(0.0, 1.0 - risk / GEOMETRY_RISK_CAP)
    decay_leg = 0.0
    if chase is not None and chase > 0:
        decay_leg = (100.0 * GEOMETRY_DECAY_WEIGHT
                     * min(1.0, chase / GEOMETRY_CHASE_CAP))
    score = risk_leg + (GEOMETRY_CONFIRMED_BONUS if confirmed else 0.0) - decay_leg
    out.update({
        "score": round(max(0.0, min(100.0, score)), 2),
        "risk_pct": round(risk, 4),
        "stop": round(stop, 4),
        "reference_low": round(raw_low, 4),
        "stop_confirmed": confirmed,
        "confirmed_pivot_low": (round(pivot_low, 4) if pivot_low is not None else None),
        "chase_pct": (round(chase, 4) if chase is not None else None),
        "age_bars": age,
    })
    return out


def _low_series(price_history: Any, close: "pd.Series") -> "np.ndarray":
    """Daily lows aligned to ``close``; falls back to the close when no low is carried
    (a close-only name has no intrabar low to hang a stop under, and pretending otherwise
    would place the stop tighter than the tape can honour)."""
    try:
        if isinstance(price_history, pd.DataFrame):
            for name in ("low", "Low", "l"):
                if name in price_history.columns:
                    s = pd.Series(price_history[name]).astype(float)
                    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
                    return s.reindex(close.index).to_numpy(dtype="float64")
    except Exception:  # noqa: BLE001
        pass
    return close.to_numpy(dtype="float64")


# ---------------------------------------------------------------------------
# The admission decision
# ---------------------------------------------------------------------------

def assess_early_turn(
    ticker: str,
    price_history: Any,
    *,
    asof: str | None = None,
    membership: Mapping[str, Mapping[str, Any]] | None = None,
    leader_states: Mapping[str, Mapping[str, Any]] | None = None,
    board_row: Mapping[str, Any] | None = None,
    benchmark: Any = None,
) -> dict[str, Any]:
    """Does this name qualify for the EARLY-TURN starter class?

    ``fired`` requires BOTH a mechanical signature (daily OR 2D) and a licensing
    CONTEXT — washout-mature basket membership OR leader-pullback (§6.9, both backends
    live).  Which one licensed the row is DISCLOSED on it: ``context_sources`` is an
    ordered subset of :data:`CONTEXT_SOURCES`, empty when nothing licensed it and
    carrying BOTH names when a name is at once a washed-out basket member and a leader
    in a controlled retrace.  A naked signature never fires: the §6.8(b) order was
    explicit that four anecdotes do not carry the promotion and only the conditional
    table would, so the unconditioned variant is not shipped even as a display chip.

    ``membership`` and ``leader_states`` are the per-run context maps, loaded ONCE by
    the caller.  ``leader_states=None`` makes the leader half resolve its own coverage
    (and fail closed when there is none), so the two contexts are symmetrical from here
    down: neither can broaden the candidate set, and neither fires on its own.

    The board row is consulted ONLY as corroborating washout context (its bottoming
    lane), never as the signature — the whole point is a read the board's own state
    machine has not made yet.  The row's ``coiled.washout_ctx`` flag is deliberately not
    read: measured on the committed 2026-08-07 board it is true on 71 of 79 buy rows, so
    it carries no class information.
    """
    daily = turn_signature(price_history, asof=asof, timeframe=TF_DAILY)
    two_day = turn_signature(price_history, asof=asof, timeframe=TF_2D)
    union = union_admission(price_history, asof=asof, benchmark=benchmark)
    geometry = setup_geometry(price_history, asof=asof, union=union)
    washout = basket_turn_context(ticker, membership)
    leader = leader_pullback_context(ticker, price_history=price_history, asof=asof,
                                     states=leader_states)

    board_washout = False
    board_reason = None
    if isinstance(board_row, Mapping):
        if str(board_row.get("lane") or "").strip().lower() == "bottoming":
            board_washout = True
            board_reason = "board lane=bottoming"

    # The UNION is an additional SIGNATURE leg, not a bypass: §A2 wires it in as the recall
    # spine, and this module's standing law that a naked signature never admits is unchanged
    # — a union fire still needs a licensing context, exactly like the dot signature does.
    signature_fired = bool(daily.get("fired") or two_day.get("fired")
                           or union.get("fired"))
    # Ordered by CONTEXT_SOURCES so the disclosure is stable across runs, and BOTH names
    # survive when both licensed the row — "washout" alone would hide the second read.
    context_sources = [
        name for name, present in (
            (CONTEXT_WASHOUT, bool(washout.get("washout_mature"))),
            (CONTEXT_LEADER_PULLBACK, bool(leader.get("leader_pullback"))),
        ) if present
    ]
    context_fired = bool(context_sources)
    fired = signature_fired and context_fired

    if fired:
        reason = "signature + " + " + ".join(
            _CONTEXT_LABELS[name] for name in context_sources)
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
        # The per-name context disclosure: an ordered subset of CONTEXT_SOURCES.
        "context_sources": context_sources,
        "signature_timeframes": [
            tf for tf, sig in ((TF_DAILY, daily), (TF_2D, two_day)) if sig.get("fired")
        ],
        # The measured recall spine + the display-tier badges it carries (§A2). Named on
        # the row so a consumer can tell WHICH construction admitted it and under which era.
        "union": union,
        "union_fired": bool(union.get("fired")),
        "union_legs": list(union.get("legs") or []),
        "admission_era": UNION_ADMISSION_ERA if union.get("fired") else None,
        "context_badges": union.get("badges") if union.get("fired") else None,
        # The early lane's OWN score — geometry, and the deck's sort key for this lane.
        # It is never blended with the confirmed lane's score; `stage` is the fact column
        # that says which lane a row is reading from.
        "setup_geometry": geometry,
        "stage": STAGE_EARLY if union.get("fired") else None,
        "daily": daily,
        "two_day": two_day,
        "washout": washout,
        "leader_pullback": leader,
        # Corroboration only — it can never make `fired` true on its own.
        "board_washout_context": board_washout,
        "board_washout_reason": board_reason,
        "reason": reason,
    }
