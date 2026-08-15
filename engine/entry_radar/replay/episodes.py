"""Episode derivation for the W5 replay (prereg §3, §5, §6, §10-hygiene).

WHAT THIS MODULE OWNS, AND WHAT IT REFUSES TO OWN
-------------------------------------------------
It turns detector output into CANDIDATE RECORDS — one per lawful episode, carrying
its decision clock, its arm history, its washout low and its refusal flags.  It
does NOT compute indicator math (the frozen W3 engines do), and it does NOT resolve
``P0``.

The P0 split is the load-bearing design decision here.  §6 sets ``P0`` for a
confirmed-bar detector to *the first trade after ``known_at``* — the opening print
of the first RTH minute bar of the session after the knowability session — with
``next_session_close`` as the only lawful fallback when that minute window is
refused.  That is a NETWORK fact, and this package is network-free.  So the shape
is two-phase:

    cands = g0_candidates(...)                     # pure, PIT, no prices fetched
    p0, basis = <runner resolves via minute fetch> # scripts/ side, §5 mechanics
    ref   = finalize_episode(cand, p0=..., ...)    # -> outcomes.EpisodeRef

:class:`outcomes.EpisodeRef` is frozen, so there is no "fill it in later" path and
no half-built episode can reach the outcome stage.  Every detector goes through the
same :func:`finalize_episode`, which is also where the §14 G-6 holdout fence fires:
an episode whose decision session is past the boundary raises rather than returning.

THE §10 HYGIENE CLOCKS LIVE HERE, NOT IN W3
--------------------------------------------
``run_c1``/``run_c2`` return a per-PATH trace and say so
(``challengers.py:864-873``): "the clocks that END an episode — CANDIDATE
resolving at H, ARMED/TURNING expiring at 15 sessions, and the re-arm eligibility
that follows — belong to the live evaluator (PR-4) and the nightly reconciler
(PR-5)".  :func:`c1_c2_episodes` is the PR-5 half: it drives the frozen engines
session by session with confirmed closes advancing per session, and stitches the
per-session traces into §10 episodes using the exported primitive
``challengers.rearm_eligible``.

REFUSALS ARE DATA (§5).  A session whose minute window cannot be fetched is
REFUSED — recorded with its reason, never approximated from EOD values.  The
injected ``minute_reader`` returning ``None`` IS that signal; there is no fallback
path in this module that manufactures a tape.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.entry_radar import indicator_core as ic
from engine.entry_radar.replay import gates, outcomes, prereg

#: Detector ids as they appear on replay rows (§1 arena).
G0 = "G0_GREY_DOT@1"
C1 = "C1_1D_LIVE_WASHOUT@1"
C2 = "C2_1D_TURN@1"
C3 = "C3_1D_4H_RECOVERY@1"
C5 = "C5_BOTTOM_WATCH@1"
INCUMBENT = "INCUMBENT_2W_STOCHRSI"     # Q5 comparator, NOT an arena detector

#: §10: ARMED/TURNING without candidate-promotion expires after this many sessions.
ARM_EXPIRY_SESSIONS = 15

#: A5.3 law: C2 means C2a in every confirmatory statistic; c2b–c2f are exploratory.
C2_PRIMARY_VARIANT = "c2a_kd_cross"


class EpisodeError(RuntimeError):
    """A malformed episode input.  Named rather than absorbed into a null episode."""


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _close_series(daily: pd.DataFrame | pd.Series) -> pd.Series:
    if isinstance(daily, pd.Series):
        series = daily
    else:
        col = ("c" if "c" in daily.columns
               else "close" if "close" in daily.columns else None)
        if col is None:
            raise EpisodeError(f"daily frame has no close column: {list(daily.columns)}")
        series = daily[col]
    out = pd.Series(pd.to_numeric(pd.Series(series).to_numpy(), errors="coerce"),
                    index=pd.DatetimeIndex(pd.Series(series).index).normalize(),
                    dtype=float).dropna()
    return out[~out.index.duplicated(keep="last")].sort_index()


def _session_at_or_before(index: pd.DatetimeIndex, when: date) -> date | None:
    """The last actual session at or before ``when``, or None before the first bar.

    This is the knowability map §3 needs in three places (the 2W incumbent's fired
    bucket, a dot's ``known_ts``, a watch's ``signal_known_ts``): a label that is
    not itself a trading session must resolve to the last session that HAD data,
    never to the next one — resolving forward would date a decision by a bar the
    decider could not have seen.
    """
    pos = int(index.searchsorted(pd.Timestamp(when), side="right")) - 1
    return None if pos < 0 else pd.Timestamp(index[pos]).date()


def _trailing_min_low(daily: pd.DataFrame, decision: date, sessions: int) -> float | None:
    """Min daily LOW over the trailing ``sessions`` ending at the decision session.

    The frozen §7 washout low for G0/C5/incumbent (the NC-2 proximity window).
    Falls back to closes when the plane carries no lows — flagged by the caller as
    a close-proxy, which excludes the episode from the primary false-start read the
    same way a close-proxy ATR does.
    """
    frame = daily
    col = "l" if "l" in frame.columns else "low" if "low" in frame.columns else None
    if col is None:
        col = "c" if "c" in frame.columns else "close" if "close" in frame.columns else None
    if col is None:
        return None
    series = pd.to_numeric(frame[col], errors="coerce")
    index = pd.DatetimeIndex(frame.index).normalize()
    pos = int(index.searchsorted(pd.Timestamp(decision), side="right")) - 1
    if pos < 0:
        return None
    lo = max(0, pos - int(sessions) + 1)
    window = series.iloc[lo: pos + 1].dropna()
    return None if window.empty else float(window.min())


def _a0(daily: pd.DataFrame, decision: date) -> tuple[float | None, str]:
    """§6 A0: Wilder ATR(14) as of the PRIOR confirmed close, on the episode's plane.

    Returns ``(a0, atr_basis)``.  ``atr_basis`` is ``true_range_daily_ohlc`` only
    when real highs and lows were used; a close-only plane yields ``close_proxy``,
    and ``outcomes._false_start`` excludes those from the primary read (contract
    §10) instead of quietly normalising by a smaller number.
    """
    index = pd.DatetimeIndex(daily.index).normalize()
    pos = int(index.searchsorted(pd.Timestamp(decision), side="right")) - 1
    if pos < 0:
        return None, "absent"
    high = daily.get("h", daily.get("high"))
    low = daily.get("l", daily.get("low"))
    close = daily.get("c", daily.get("close"))
    if close is None:
        return None, "absent"
    if high is None or low is None or not (pd.notna(high).any() and pd.notna(low).any()):
        high = low = close
        basis = "close_proxy"
    else:
        basis = "true_range_daily_ohlc"
    series = ic.atr14_prior_confirmed(high, low, close)
    if pos >= len(series):
        return None, basis
    value = float(pd.Series(series).iloc[pos])
    if not np.isfinite(value) or value <= 0:
        return None, basis
    return value, basis


def confirmed_k(daily: pd.DataFrame | pd.Series) -> pd.Series:
    """Confirmed 1D StochRSI %K on the plane's closes — clause B of the false start.

    Handed to :func:`finalize_episode` as the forward slice ``confirmed_k_fwd``,
    which is what ``outcomes._false_start`` reads for "the confirmed K re-enters
    below 20".  Computed once per name by the caller; this is the one place the
    series' definition lives.
    """
    closes = _close_series(daily)
    k, _d = ic.stoch_rsi_kd(closes)
    return pd.Series(np.asarray(k, dtype=float), index=closes.index)


# --------------------------------------------------------------------------- #
# candidate records -> EpisodeRef
# --------------------------------------------------------------------------- #
def finalize_episode(cand: Mapping[str, Any], *, p0: float, p0_basis: str,
                     a0: float | None, atr_basis: str,
                     washout_low: float | None, cohort: str = "unassigned",
                     regime: str = "unknown", c32: bool | None = None,
                     confirmed_k_fwd: Sequence[float] | None = None,
                     extra: Mapping[str, Any] | None = None) -> outcomes.EpisodeRef:
    """Turn a pre-P0 candidate record into the frozen :class:`outcomes.EpisodeRef`.

    ONE constructor for every detector, so the §14 G-6 holdout fence
    (:func:`gates.check_decision_in_era`) is unskippable: it fires here, before the
    row exists, rather than at some later filter a new call site could forget.

    ``confirmed_k_fwd`` is the forward slice of :func:`confirmed_k` aligned to
    sessions D+1..D+H; it rides ``extra`` because that is where
    ``outcomes._false_start`` looks for it.  Absent => clause B is UNEVALUABLE and
    is reported so, never silently False.
    """
    decision = cand["decision_session"]
    decision = decision if isinstance(decision, date) else pd.Timestamp(decision).date()
    gates.check_decision_in_era(decision)
    payload: dict[str, Any] = dict(cand.get("extra") or {})
    payload.update(dict(extra or {}))
    for key in ("candidate_at", "first_armed_at", "refusals", "variant",
                "detector_spec_hash", "provenance", "known_ts", "ts"):
        if key in cand and key not in payload:
            payload[key] = cand[key]
    if confirmed_k_fwd is not None:
        payload["confirmed_k_fwd"] = list(confirmed_k_fwd)
    first_armed = cand.get("first_armed_session")
    if first_armed is not None and not isinstance(first_armed, date):
        first_armed = pd.Timestamp(first_armed).date()
    return outcomes.EpisodeRef(
        ticker=str(cand["ticker"]), detector_id=str(cand["detector_id"]),
        panel=str(cand.get("panel", "")), decision_session=decision,
        p0=float(p0), p0_basis=str(p0_basis), a0=a0, atr_basis=str(atr_basis),
        washout_low=washout_low, first_armed_session=first_armed,
        cohort=str(cohort), regime=str(regime), c32=c32, extra=payload)


# --------------------------------------------------------------------------- #
# G0 — the staged Terminal emitter's dots
# --------------------------------------------------------------------------- #
def g0_candidates(ticker: str, dots: Sequence[Mapping[str, Any]],
                  daily_ohlc: pd.DataFrame, *, panel: str = "B",
                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pre-P0 G0 candidate records from the staged emitter's dot stream (§3).

    ``dots`` is ``scripts/entry_radar_stage_terminal.run_name(...)["dots"]`` —
    ``[{"ts", "known_ts"}, ...]`` over the UNCAPPED §3.1 population.

    DECISION CLOCK IS ``known_ts``, NEVER ``ts``.  ``ts`` is the 3D bar's OPEN
    date; the value only became observable at the bar's last session, which is what
    ``known_ts`` carries.  A dot whose ``known_ts`` is null is a REFUSAL (it has no
    decision clock at all) and is counted, never dated from ``ts``.

    Returns ``(candidates, refusals)``.  The decision SESSION is the last actual
    session at or before ``known_ts`` on this name's plane — a ``known_ts`` that
    is not itself a trading session (a holiday label) resolves backwards.
    """
    index = pd.DatetimeIndex(daily_ohlc.index).normalize()
    cands: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    seen: set[date] = set()
    for dot in dots or ():
        known = dot.get("known_ts")
        if not known:
            refusals.append({"ticker": ticker, "detector_id": G0, "ts": dot.get("ts"),
                             "reason": "null_known_ts"})
            continue
        session = _session_at_or_before(index, pd.Timestamp(known).date())
        if session is None:
            refusals.append({"ticker": ticker, "detector_id": G0, "ts": dot.get("ts"),
                             "known_ts": str(known), "reason": "no_session_at_or_before"})
            continue
        if session in seen:
            # §10: one live episode per (ticker, detector_id).  Two dots resolving
            # to one decision session are ONE episode; the duplicate is disclosed.
            refusals.append({"ticker": ticker, "detector_id": G0, "ts": dot.get("ts"),
                             "known_ts": str(known),
                             "reason": "duplicate_decision_session"})
            continue
        seen.add(session)
        cands.append({
            "ticker": ticker, "detector_id": G0, "panel": panel,
            "decision_session": session, "ts": dot.get("ts"),
            "known_ts": str(known), "first_armed_session": session,
            "p0_basis_required": "first_trade_after_known_at",
            "washout_low_window": prereg.WASHOUT_LOW_FALLBACK_SESSIONS,
        })
    return cands, refusals


# --------------------------------------------------------------------------- #
# C5 — the staged emitter's bottom-watch stream
# --------------------------------------------------------------------------- #
def c5_candidates_from_watches(ticker: str, watches: Sequence[Mapping[str, Any]],
                               daily_ohlc: pd.DataFrame, *, panel: str = "B",
                               ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pre-P0 C5 candidate records from the emitter's ``bottom_watches`` (§3).

    Decision clock = the event's knowability stamp (``known_ts`` on the emitter's
    watch dict, which ``contracts`` stamps as ``signal_known_ts`` on the artifact).
    A watch with a null clock is a REFUSAL and is counted — the same rule as G0,
    for the same reason.

    These rows are RESEARCH DERIVATIONS.  They never mutate or duplicate the
    production ``mastermind.entry_event.v1`` store, and the A4.7
    ``pre_channel_reconstruction`` honesty is inherited into the disclosure text.
    """
    index = pd.DatetimeIndex(daily_ohlc.index).normalize()
    cands: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    seen: set[date] = set()
    for watch in watches or ():
        known = watch.get("known_ts") or watch.get("signal_known_ts")
        if not known:
            refusals.append({"ticker": ticker, "detector_id": C5,
                             "ts": watch.get("ts"), "reason": "null_known_ts"})
            continue
        session = _session_at_or_before(index, pd.Timestamp(known).date())
        if session is None:
            refusals.append({"ticker": ticker, "detector_id": C5,
                             "ts": watch.get("ts"), "known_ts": str(known),
                             "reason": "no_session_at_or_before"})
            continue
        if session in seen:
            refusals.append({"ticker": ticker, "detector_id": C5,
                             "ts": watch.get("ts"), "known_ts": str(known),
                             "reason": "duplicate_decision_session"})
            continue
        seen.add(session)
        cands.append({
            "ticker": ticker, "detector_id": C5, "panel": panel,
            "decision_session": session, "ts": watch.get("ts"),
            "known_ts": str(known), "first_armed_session": session,
            "variant": watch.get("kind"),
            "p0_basis_required": "first_trade_after_known_at",
            "washout_low_window": prereg.WASHOUT_LOW_FALLBACK_SESSIONS,
            "extra": {"kind": watch.get("kind"), "quality": watch.get("quality"),
                      "scored": watch.get("scored"),
                      "pre_channel_reconstruction": True},
        })
    return cands, refusals


# --------------------------------------------------------------------------- #
# incumbent gauge (Q5 comparator)
# --------------------------------------------------------------------------- #
def incumbent_fires(ticker: str, close: pd.Series) -> list[date]:
    """The PSS §7 incumbent entry gauge's fire sessions (§3, family "S").

    Verbatim construction, from ``scripts/research/ptt_w1_persistence_of_fit.py``
    (``bars_for`` rung "2W" + ``tool_dates`` family "S")::

        bars = close.resample("W-FRI").last().dropna().iloc[::2]   # 2W anchor-A
        k, d = stoch_rsi_kd(bars)
        fire = cross_up(k, d) & (k.shift(1) < 20)

    KNOWABILITY.  A 2W bar's label is a Friday that may not be a trading session at
    all, and its value is only observable once the bucket's last actual session has
    closed.  Each fire is therefore mapped to the last actual DAILY session at or
    before its 2W label — the §6 confirmed-bar law, stated as a map rather than
    assumed by using the label directly.

    ``canon`` is imported lazily so this module stays importable without pulling
    the oscillator stack into a caller that only wants the dataclasses.
    """
    from engine import canon  # local: the pinned oscillator family (R-A)

    closes = _close_series(close)
    if closes.empty:
        return []
    bars = closes.resample("W-FRI").last().dropna().iloc[::2]
    if len(bars) < 3:
        return []
    k, d = canon.stoch_rsi_kd(bars)
    fired = (canon.crossover(k, d) & (k.shift(1) < ic.OVERSOLD)).fillna(False)
    index = pd.DatetimeIndex(closes.index)
    out: list[date] = []
    for label in bars.index[fired.to_numpy(dtype=bool)]:
        session = _session_at_or_before(index, pd.Timestamp(label).date())
        if session is not None and (not out or session != out[-1]):
            out.append(session)
    return out


def incumbent_candidates(ticker: str, daily_ohlc: pd.DataFrame, *, panel: str = "B",
                         ) -> list[dict[str, Any]]:
    """Pre-P0 records for the incumbent gauge — same shape as every other detector."""
    closes = _close_series(daily_ohlc)
    return [{
        "ticker": ticker, "detector_id": INCUMBENT, "panel": panel,
        "decision_session": session, "first_armed_session": session,
        "p0_basis_required": "first_trade_after_known_at",
        "washout_low_window": prereg.WASHOUT_LOW_FALLBACK_SESSIONS,
    } for session in incumbent_fires(ticker, closes)]


# --------------------------------------------------------------------------- #
# §5 superset screen (fetch budget only)
# --------------------------------------------------------------------------- #
def c1_screen_sessions(daily_vendor: pd.DataFrame,
                       sessions: Sequence[date] | None = None) -> list[date]:
    """Sessions where a C1 arm is POSSIBLE — a pure necessary-condition filter (§5).

    The screen appends the session's own LOW as a provisional close to the
    confirmed closes through D−1 and keeps the session iff the resulting StochRSI
    ``K < 20``.

    WHY THE LOW.  %K is monotone increasing in the provisional close (§7.1), and
    every value the live sampler could ever observe intraday is ≥ the session's raw
    low.  So K(low) is the MINIMUM K the session can produce: if K(low) ≥ 20, no
    sampled path on that session can put K below 20, and no lawful C1 arm can occur
    there.  The screen can therefore only remove sessions that could not have
    fired — it can neither create nor destroy an episode, which is what makes it a
    fetch-budget device rather than a detector change.  (§15's mutation control
    proves the direction: swapping the LOW for the CLOSE changes the set.)
    """
    frame = daily_vendor
    close_col = ("c" if "c" in frame.columns
                 else "close" if "close" in frame.columns else None)
    low_col = ("l" if "l" in frame.columns
               else "low" if "low" in frame.columns else close_col)
    if close_col is None:
        raise EpisodeError(f"screen needs a close column; got {list(frame.columns)}")
    closes = pd.to_numeric(frame[close_col], errors="coerce").astype(float)
    lows = pd.to_numeric(frame[low_col], errors="coerce").astype(float)
    index = pd.DatetimeIndex(frame.index).normalize()
    wanted = (None if sessions is None
              else {pd.Timestamp(s).normalize() for s in sessions})

    out: list[date] = []
    base = closes.to_numpy(dtype=float)
    low_arr = lows.to_numpy(dtype=float)
    for pos in range(1, len(index)):
        if wanted is not None and index[pos] not in wanted:
            continue
        provisional = low_arr[pos]
        if not np.isfinite(provisional):
            continue
        series = pd.Series(np.append(base[:pos], provisional))
        k, _d = ic.stoch_rsi_kd(series)
        k_val = ic.last_finite(k)
        if k_val is not None and k_val < ic.OVERSOLD:
            out.append(pd.Timestamp(index[pos]).date())
    return out


# --------------------------------------------------------------------------- #
# C1 / C2 — driving the frozen W3 engines session by session
# --------------------------------------------------------------------------- #
def _daily_history(daily_vendor: pd.DataFrame, *, price_basis: str, vintage: str):
    """Wrap a vendor daily frame as ``challengers.DailyHistory`` (high/low/close)."""
    from engine.entry_radar.challengers import DailyHistory  # local: frozen W3 API

    frame = daily_vendor.rename(columns={"c": "close", "h": "high", "l": "low",
                                         "o": "open", "v": "volume"})
    missing = [c for c in ("high", "low", "close") if c not in frame.columns]
    if missing:
        raise EpisodeError(f"C1/C2 need a full OHLC plane; missing {missing}")
    frame = frame.copy()
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return DailyHistory(frame=frame, price_basis=price_basis, vintage=vintage)


def c1_c2_episodes(ticker: str, daily_vendor: pd.DataFrame,
                   minute_reader: Callable[[str, date], Any | None],
                   sessions_to_eval: Sequence[date], *, panel: str = "A",
                   price_basis: str = "adjusted", vintage: str = "",
                   ) -> dict[str, Any]:
    """Replay C1/C2 across ``sessions_to_eval`` under §10 hygiene.

    MECHANICS, in the order they matter:

    1. Per session, the injected ``minute_reader(ticker, session)`` supplies that
       session's tape (a ``challengers.SessionTape``, or a row list this function
       parses).  ``None`` means the window could not be fetched: the session is
       REFUSED, recorded with its reason, and NOT approximated from EOD values (§5).
    2. ``challengers.build_observation_path`` builds the A5.1 sampled path from the
       confirmed daily history — which ``DailyHistory.confirmed_through`` cuts
       STRICTLY before the session, so today's close is never even loaded — plus the
       one appended provisional close per observation.
    3. ``run_c1``/``run_c2`` evaluate the frozen laws on that path.  Nothing here
       re-implements an indicator or a firing rule.
    4. The per-session traces are stitched into §10 episodes: one live episode per
       ticker; an ARMED episode with no candidate EXPIRES after
       :data:`ARM_EXPIRY_SESSIONS`; a CANDIDATE resolves at H; after an episode ends,
       a re-arm requires ``challengers.rearm_eligible`` (confirmed K > 50 for 2
       consecutive sessions, or 15 elapsed).

    C1's candidate is the FIRST ARM (A5.2: ``candidate_at ≡ first_armed_at``), so at
    most one C1 candidate per episode.  C2 emits the first fire per episode × variant
    (A5.3); only ``c2a_kd_cross`` is confirmatory.

    Returns ``{"episodes": [...pre-P0 candidate dicts...], "refusals": [...],
    "path_observations": {session_iso: n_observations}}``.
    """
    from engine.entry_radar.challengers import (  # local: frozen W3 API
        SessionTape, build_observation_path, rearm_eligible, run_c1, run_c2)
    from engine.entry_radar.four_hour import tape_from_rows

    daily = _daily_history(daily_vendor, price_basis=price_basis, vintage=vintage)
    k_confirmed = confirmed_k(daily_vendor)

    episodes: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    observations: dict[str, int] = {}

    live: dict[str, Any] | None = None      # the open C1 episode, if any
    ended_at_pos: int | None = None         # position (in sessions) the last one ended
    ordered = sorted({pd.Timestamp(s).date() for s in sessions_to_eval})
    index = pd.DatetimeIndex(daily_vendor.index).normalize()

    for step, session in enumerate(ordered):
        tape = _tape_for(minute_reader, ticker, session, SessionTape, tape_from_rows,
                         price_basis=price_basis, vintage=vintage)
        if tape is None:
            refusals.append({"ticker": ticker, "detector_id": C1, "session": session,
                             "reason": "minute_window_refused"})
            continue
        path = build_observation_path(ticker=ticker, daily=daily, tapes=[tape])
        observations[session.isoformat()] = len(path)
        if not path:
            refusals.append({"ticker": ticker, "detector_id": C1, "session": session,
                             "reason": "empty_rth_tape"})
            continue

        # ---- §10: close out a live episode whose clocks have run out ----------
        if live is not None:
            elapsed = step - live["armed_step"]
            if live["candidate_at"] is None and elapsed >= ARM_EXPIRY_SESSIONS:
                live["end_reason"] = "expired_armed_no_candidate"
                ended_at_pos, live = step, None
            elif (live["candidate_at"] is not None
                  and elapsed >= prereg.HORIZON_PRIMARY):
                live["end_reason"] = "resolved_at_horizon"
                ended_at_pos, live = step, None

        # ---- §10: a new episode may only arm when re-arm eligibility holds ----
        if live is None and ended_at_pos is not None:
            since = [_k_at(k_confirmed, index, ordered[p])
                     for p in range(ended_at_pos, step)]
            if not rearm_eligible(since, step - ended_at_pos):
                refusals.append({"ticker": ticker, "detector_id": C1,
                                 "session": session, "reason": "suppressed_by_rearm"})
                continue

        c1 = run_c1(path)
        c1_episode = c1.episode
        if c1_episode is not None and live is None:
            live = {"ticker": ticker, "detector_id": C1, "panel": panel,
                    "decision_session": session, "armed_step": step,
                    "first_armed_session": session,
                    "first_armed_at": c1_episode.first_armed_at,
                    "candidate_at": c1_episode.candidate_at,
                    "p0_basis_required": "sampled_last_trade_at_decision",
                    "sampled_close_at_decision": _sampled_at(path,
                                                             c1_episode.candidate_at),
                    "end_reason": None, "c2_variants_fired": {}}
            episodes.append(live)
        elif c1_episode is not None and live is not None:
            # A second arm inside a nonterminal episode is a PATH observation, not
            # a second candidate (A5.2) — recorded, never promoted.
            live.setdefault("extra_arms", []).append(session.isoformat())

        if live is None:
            continue

        # ---- C2 inside the live C1 episode -----------------------------------
        c2 = run_c2(path, c1_episode if c1_episode is not None
                    else _synthetic_c1(live))
        for variant, fires in (c2.fires or {}).items():
            if not fires or variant in live["c2_variants_fired"]:
                continue
            live["c2_variants_fired"][variant] = session.isoformat()
            episodes.append({
                "ticker": ticker, "detector_id": C2, "panel": panel,
                "variant": variant, "decision_session": session,
                "first_armed_session": live["first_armed_session"],
                "candidate_at": fires[0],
                "p0_basis_required": "sampled_last_trade_at_decision",
                "sampled_close_at_decision": _sampled_at(path, fires[0]),
                "confirmatory": variant == C2_PRIMARY_VARIANT,
                "c1_decision_session": live["decision_session"],
            })
    return {"episodes": episodes, "refusals": refusals,
            "path_observations": observations}


def _tape_for(minute_reader: Callable[[str, date], Any | None], ticker: str,
              session: date, session_tape_cls, tape_from_rows, *,
              price_basis: str, vintage: str):
    """Normalise whatever the injected reader returns into a ``SessionTape``.

    A reader may hand back a ``SessionTape`` (fixtures, the C3 protocol shape) or
    the compact ``[iso_start, o, h, l, c, v]`` rows a vendor response parses into.
    ``None`` is the REFUSAL signal and is passed straight through; an EMPTY row
    list is a different fact (the window fetched and held no RTH prints) and
    becomes an empty tape, which the observation path then reports as unavailable.
    """
    try:
        raw = minute_reader(ticker, session)
    except Exception as exc:  # noqa: BLE001 — a reader fault is a refusal, not a crash
        raise EpisodeError(f"minute_reader({ticker}, {session}) raised {exc!r}") from exc
    if raw is None:
        return None
    if isinstance(raw, session_tape_cls):
        return raw
    if isinstance(raw, pd.DataFrame):
        # the vendor client's native shape (columns t,o,h,l,c,v) — convert to
        # the [iso_start, o, h, l, c, v] rows tape_from_rows parses; iterating
        # a DataFrame directly would yield COLUMN NAMES (the measured seam bug)
        rows = [[pd.Timestamp(r.t).isoformat(), r.o, r.h, r.l, r.c, r.v]
                for r in raw.itertuples(index=False)]
        return tape_from_rows(session, rows, price_basis=price_basis, vintage=vintage)
    return tape_from_rows(session, list(raw), price_basis=price_basis, vintage=vintage)


def _synthetic_c1(live: Mapping[str, Any]):
    """A minimal stand-in carrying the live episode's ``first_armed_at``.

    ``run_c2``'s eligibility reads exactly two things off the C1 episode —
    ``first_armed_at`` and the event ids ``lawful_evidence_refs`` filters — so a
    multi-session episode whose arm happened on an EARLIER session needs an object
    that says when it armed.  Building a real ``DetectorEpisode`` here would mint a
    second episode object for one §10 episode; this carries the clock and nothing
    else, and its empty event list means C2 readings cite no evidence they could
    not have seen.
    """
    class _ArmClock:
        first_armed_at = live.get("first_armed_at")
        event_ids: list[str] = []
        event_ts: dict[str, str] = {}
    return _ArmClock()


def _sampled_at(path: Sequence[Any], observed_at: str | None) -> float | None:
    """The sampled provisional close at the firing observation — §6's LIVE ``P0``."""
    if not observed_at:
        return None
    for obs in path:
        if getattr(obs, "observed_at", None) == observed_at:
            value = getattr(obs, "sampled_close", None)
            return None if value is None else float(value)
    return None


def _k_at(k_series: pd.Series, index: pd.DatetimeIndex, session: date) -> float | None:
    pos = int(index.searchsorted(pd.Timestamp(session), side="right")) - 1
    if pos < 0 or pos >= len(k_series):
        return None
    value = float(k_series.iloc[pos])
    return value if np.isfinite(value) else None


# --------------------------------------------------------------------------- #
# C3 — the 4H recovery detector
# --------------------------------------------------------------------------- #
def c3_episodes(ticker: str, daily_vendor: pd.DataFrame,
                intraday_reader: Callable[[str, date], Any | None],
                sessions: Sequence[date], *, panel: str = "A",
                price_basis: str = "adjusted", vintage: str = "",
                ) -> dict[str, Any]:
    """Replay C3 (§3): arm on a knowable confirmed-daily washout, fire on the 4H turn.

    The 4H grid is built by the frozen ``four_hour.four_hour_buckets`` from the same
    injected minute source C1/C2 use — one substrate, so the W3-1 basis gate sees
    agreeing bases.  ``now=None`` treats each replayed session as fully elapsed,
    which is the replay case the primitive documents.

    A session whose window is refused contributes NO buckets and is recorded in the
    refusal census.  It is not skipped silently: a C3 arm that expires because its
    turn session was unfetchable is a measured refusal, not a measured non-fire.
    """
    from engine.entry_radar.challengers import SessionTape  # local: frozen W3 API
    from engine.entry_radar.four_hour import (four_hour_buckets, run_c3,
                                              tape_from_rows)

    daily = _daily_history(daily_vendor, price_basis=price_basis, vintage=vintage)
    buckets_by_session: list[tuple[date, tuple[Any, ...]]] = []
    refusals: list[dict[str, Any]] = []
    for session in sorted({pd.Timestamp(s).date() for s in sessions}):
        tape = _tape_for(intraday_reader, ticker, session, SessionTape, tape_from_rows,
                         price_basis=price_basis, vintage=vintage)
        if tape is None:
            refusals.append({"ticker": ticker, "detector_id": C3, "session": session,
                             "reason": "minute_window_refused"})
            continue
        buckets_by_session.append((session, four_hour_buckets(tape, now=None)))

    if not buckets_by_session:
        return {"episodes": [], "refusals": refusals, "armed_at": None, "turns": ()}

    run = run_c3(ticker=ticker, daily=daily, buckets_by_session=buckets_by_session)
    episodes: list[dict[str, Any]] = []
    for episode in run.episodes:
        if episode.candidate_at is None:
            refusals.append({"ticker": ticker, "detector_id": C3,
                             "session": (pd.Timestamp(run.armed_session).date()
                                         if run.armed_session else None),
                             "reason": "armed_no_candidate"})
            continue
        decision = pd.Timestamp(episode.candidate_at).tz_convert(
            "America/New_York").date() if _tz_aware(episode.candidate_at) else \
            pd.Timestamp(episode.candidate_at).date()
        episodes.append({
            "ticker": ticker, "detector_id": C3, "panel": panel,
            "decision_session": decision, "candidate_at": episode.candidate_at,
            "first_armed_session": (pd.Timestamp(run.armed_session).date()
                                    if run.armed_session else None),
            "first_armed_at": run.armed_at,
            "p0_basis_required": "first_trade_after_known_at",
            "washout_low_window": None,
        })
    return {"episodes": episodes, "refusals": refusals, "armed_at": run.armed_at,
            "turns": run.turns}


def _tz_aware(stamp: str) -> bool:
    try:
        return pd.Timestamp(stamp).tz is not None
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# washout low (§7, both forms)
# --------------------------------------------------------------------------- #
def washout_low(cand: Mapping[str, Any], daily: pd.DataFrame) -> float | None:
    """The episode washout low, in whichever of the two frozen §7 forms applies.

    * Episodes WITH an arm state (C1/C2/C3): the min daily low from
      ``first_armed_session`` through the decision session.
    * G0 / C5 / incumbent: the trailing-63-session minimum low ending at the
      decision session — the NC-2 proximity window, pre-declared in §7.
    """
    decision = cand["decision_session"]
    decision = decision if isinstance(decision, date) else pd.Timestamp(decision).date()
    window = cand.get("washout_low_window")
    if window:
        return _trailing_min_low(daily, decision, int(window))
    armed = cand.get("first_armed_session")
    if armed is None:
        return _trailing_min_low(daily, decision,
                                 prereg.WASHOUT_LOW_FALLBACK_SESSIONS)
    armed = armed if isinstance(armed, date) else pd.Timestamp(armed).date()
    index = pd.DatetimeIndex(daily.index).normalize()
    start = int(index.searchsorted(pd.Timestamp(armed), side="left"))
    stop = int(index.searchsorted(pd.Timestamp(decision), side="right"))
    if stop <= start:
        return None
    return _trailing_min_low(daily, decision, stop - start)


def forward_confirmed_k(k_series: pd.Series, decision: date,
                        horizon: int = prereg.HORIZON_PRIMARY) -> list[float]:
    """The confirmed-K slice aligned to sessions D+1..D+H (false-start clause B)."""
    index = pd.DatetimeIndex(k_series.index)
    pos = int(index.searchsorted(pd.Timestamp(decision), side="right"))
    return [float(v) for v in k_series.iloc[pos: pos + int(horizon)].to_numpy(dtype=float)]


__all__ = [
    "G0", "C1", "C2", "C3", "C5", "INCUMBENT", "ARM_EXPIRY_SESSIONS",
    "C2_PRIMARY_VARIANT", "EpisodeError", "confirmed_k", "finalize_episode",
    "g0_candidates", "c5_candidates_from_watches", "incumbent_fires",
    "incumbent_candidates", "c1_screen_sessions", "c1_c2_episodes", "c3_episodes",
    "washout_low", "forward_confirmed_k",
]
