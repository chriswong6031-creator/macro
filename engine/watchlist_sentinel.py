"""engine/watchlist_sentinel.py — Watchlist Buy-Zone Sentinel (Codex docket B6).

Pure logic: given (watched tickers, today's per-ticker states, yesterday's per-ticker
states, cooldown map) return alert rows when a ticker ENTERS the clean buy window.

Design rules
------------
- ZERO network calls, zero LLM calls, zero file I/O.  All state is passed in.
- No new signals — only reads already-computed engine states.
- Alert only on ENTER of the clean window (transition-detection, not steady-state).
  Cooldown: skip the same ticker for 5 sessions after it last alerted, unless it
  left and re-entered the window in the interim.
- Emitted strings are descriptive only (state names, codes, dates).
  No advice verbs ("buy", "sell", "add", "avoid") beyond quoting engine state labels.

Clean-window rule (deterministic, composed from already-computed keys)
----------------------------------------------------------------------
  ENTER = (
      entry_signal.status in {"buy_now", "partial"}
      OR (signal_gate.eligible AND signal_gate.tier_cascade IS NOT NULL)
  )
  AND NOT earnings_blackout.in_blackout
  AND extension_grade NOT IN {"parabolic", "stretched"}

State schema for today_states / yesterday_states
-------------------------------------------------
Per-ticker dict (all keys optional — sentinel is None-safe):
  {
    "entry_status":    str | None,   # from entry_signal.status
    "gate_eligible":   bool | None,  # from signal_gate: eligible
    "gate_tier":       str | None,   # from signal_gate: tier_cascade
    "in_blackout":     bool | None,  # from earnings_blackout
    "extension_grade": str | None,   # from extension: grade
    "as_of":           str | None,   # YYYY-MM-DD date string
  }

Cooldown map schema
-------------------
  {ticker: {"last_alert": "YYYY-MM-DD", "last_in_window": bool, "sessions_since": int}}

Return schema (one entry per newly alerting ticker)
---------------------------------------------------
  {
    "ticker":       str,
    "state_entered": str,   # human-readable window-entry label
    "reasons":      [str],  # entry_status, gate tier, veto codes
    "as_of":        str,
    "entry_status": str | None,
    "gate_tier":    str | None,
    "in_blackout":  bool,
    "extension_grade": str | None,
    "alert_id_key": str,    # stable key for alert_triage sha256 ID
  }
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

# entry_signal status values that represent an open buy window
_OPEN_STATUSES: frozenset[str] = frozenset({"buy_now", "partial"})

# extension grades that veto the window regardless of other states
_BLOCKED_GRADES: frozenset[str] = frozenset({"parabolic", "stretched"})

# sessions before a same-window re-alert is permitted
COOLDOWN_SESSIONS: int = 5


def _in_window(state: dict[str, Any]) -> bool:
    """Return True when a ticker's state satisfies the clean-window rule.

    Parameters
    ----------
    state:
        Per-ticker state dict (all keys are optional — missing = fail-open toward safe).
    """
    entry_status: str | None = state.get("entry_status")
    gate_eligible: bool | None = state.get("gate_eligible")
    gate_tier: str | None = state.get("gate_tier")
    in_blackout: bool | None = state.get("in_blackout")
    extension_grade: str | None = state.get("extension_grade")

    # Earnings blackout veto
    if in_blackout is True:
        return False

    # Extension veto (parabolic / stretched)
    if extension_grade in _BLOCKED_GRADES:
        return False

    # Entry condition: either entry_signal says buy_now/partial,
    # OR signal_gate shows a fresh eligible cross (eligible=True AND tier_cascade set)
    entry_open = (entry_status in _OPEN_STATUSES) or (
        gate_eligible is True and gate_tier is not None
    )
    return entry_open


def _reason_codes(state: dict[str, Any]) -> list[str]:
    """Build human-readable reason phrases describing why the window is open."""
    reasons: list[str] = []
    entry_status = state.get("entry_status")
    gate_tier = state.get("gate_tier")
    gate_eligible = state.get("gate_eligible")
    extension_grade = state.get("extension_grade")

    if entry_status in _OPEN_STATUSES:
        reasons.append(f"entry_status={entry_status}")
    if gate_eligible is True and gate_tier is not None:
        reasons.append(f"gate_tier={gate_tier}")
    if extension_grade and extension_grade not in _BLOCKED_GRADES:
        reasons.append(f"extension={extension_grade}")
    if not reasons:
        reasons.append("window_open")
    return reasons


def _cooldown_blocks(
    ticker: str,
    prev_in_window: bool,
    cooldown: dict[str, dict[str, Any]],
    today_str: str,
) -> bool:
    """Return True when the cooldown suppresses this ticker.

    Cooldown is lifted when the ticker LEFT the window since its last alert
    (prev_in_window=False while still in cooldown → the window closed, so the
    next ENTER is a genuine re-entry and is permitted).
    """
    entry = cooldown.get(ticker)
    if entry is None:
        return False  # no history — permit

    sessions_since: int = entry.get("sessions_since", COOLDOWN_SESSIONS + 1)
    last_in_window: bool = entry.get("last_in_window", False)

    # If the ticker was NOT in the window yesterday, the window has closed/re-opened;
    # treat this as a genuine new entry regardless of cooldown.
    if not prev_in_window:
        return False

    # Still continuously in window: apply cooldown
    if sessions_since < COOLDOWN_SESSIONS:
        log.debug(
            "watchlist_sentinel: %s in cooldown (%d/%d sessions)",
            ticker,
            sessions_since,
            COOLDOWN_SESSIONS,
        )
        return True

    return False


def run_sentinel(
    watched_tickers: list[str],
    today_states: dict[str, dict[str, Any]],
    yesterday_states: dict[str, dict[str, Any]],
    cooldown: dict[str, dict[str, Any]],
    today_str: str | None = None,
) -> list[dict[str, Any]]:
    """Run the watchlist buy-zone sentinel.

    Parameters
    ----------
    watched_tickers:
        List of ticker symbols in the operator watchlist.
    today_states:
        {ticker: state_dict} with today's engine outputs (see module docstring).
    yesterday_states:
        {ticker: state_dict} with yesterday's engine outputs.
    cooldown:
        Mutable cooldown map.  This function does NOT mutate it — the caller
        persists the updated map after collecting results.
    today_str:
        ISO date string for the alert.  Defaults to today's date.

    Returns
    -------
    list[dict]
        Alert rows for tickers that ENTERED the clean window today.
        Empty when no tickers entered, or when watched_tickers is empty.
    """
    if not watched_tickers:
        return []

    today_str = today_str or date.today().isoformat()
    alerts: list[dict[str, Any]] = []

    for ticker in watched_tickers:
        if not isinstance(ticker, str) or not ticker.strip():
            continue
        ticker = ticker.strip().upper()

        today_state = today_states.get(ticker) or {}
        yesterday_state = yesterday_states.get(ticker) or {}

        today_in = _in_window(today_state)
        yesterday_in = _in_window(yesterday_state)

        # Only alert on ENTER (was not in window yesterday, is in window today)
        if not today_in or yesterday_in:
            if today_in and yesterday_in:
                log.debug("watchlist_sentinel: %s — already in window (no new entry)", ticker)
            continue

        # Check cooldown (blocks if still in continuous window within cooldown window)
        if _cooldown_blocks(ticker, yesterday_in, cooldown, today_str):
            continue

        reasons = _reason_codes(today_state)
        alerts.append(
            {
                "ticker": ticker,
                "state_entered": "buy_zone_enter",
                "reasons": reasons,
                "as_of": today_str,
                "entry_status": today_state.get("entry_status"),
                "gate_tier": today_state.get("gate_tier"),
                "in_blackout": bool(today_state.get("in_blackout")),
                "extension_grade": today_state.get("extension_grade"),
                # Stable key for alert_triage sha256 ID generation
                "alert_id_key": f"watchlist|buy_zone_enter|{ticker}|{today_str}",
            }
        )
        log.info(
            "watchlist_sentinel: %s entered buy zone — %s",
            ticker,
            "; ".join(reasons),
        )

    return alerts


def update_cooldown(
    cooldown: dict[str, dict[str, Any]],
    watched_tickers: list[str],
    today_states: dict[str, dict[str, Any]],
    newly_alerted: list[dict[str, Any]],
    today_str: str,
) -> dict[str, dict[str, Any]]:
    """Advance the cooldown map for the next nightly run.

    Rules:
    - For every watched ticker: record whether it is in-window today
      and increment sessions_since if it is still in-window.
    - For tickers that just alerted: reset sessions_since to 0 (fresh alert).
    - For tickers that LEFT the window: clear their cooldown entry so the
      next ENTER is detected cleanly.

    Parameters
    ----------
    cooldown:
        Current cooldown map (not mutated; a new dict is returned).
    watched_tickers:
        List of ticker symbols.
    today_states:
        Today's per-ticker state dicts.
    newly_alerted:
        Alert rows produced by run_sentinel() this run.
    today_str:
        ISO date string.

    Returns
    -------
    dict
        Updated cooldown map.
    """
    alerted_set = {a["ticker"] for a in newly_alerted}
    new_map: dict[str, dict[str, Any]] = {}

    for ticker in watched_tickers:
        if not isinstance(ticker, str) or not ticker.strip():
            continue
        ticker = ticker.strip().upper()
        state = today_states.get(ticker) or {}
        in_win = _in_window(state)

        if not in_win:
            # Window closed — drop from cooldown so next entry is detected fresh
            continue

        old = cooldown.get(ticker) or {}
        if ticker in alerted_set:
            # Just alerted — start fresh cooldown
            new_map[ticker] = {
                "last_alert": today_str,
                "last_in_window": True,
                "sessions_since": 0,
            }
        else:
            # Still in window but not alerting
            sessions = old.get("sessions_since", COOLDOWN_SESSIONS)
            new_map[ticker] = {
                "last_alert": old.get("last_alert", today_str),
                "last_in_window": True,
                "sessions_since": sessions + 1,
            }

    return new_map


def format_discord_message(alert: dict[str, Any]) -> str:
    """Format one alert row as a plain Discord message (no advice verbs).

    Example output:
        WATCHLIST · NVDA entered buy zone — entry_status=buy_now; gate_tier=T2;
        extension=steady. No earnings blackout. (2026-07-08)
    """
    ticker = alert.get("ticker", "?")
    reasons = "; ".join(alert.get("reasons") or [])
    as_of = alert.get("as_of", "")
    blackout_note = (
        "earnings blackout active"
        if alert.get("in_blackout")
        else "no earnings blackout"
    )
    ext = alert.get("extension_grade") or "normal"
    return (
        f"WATCHLIST · {ticker} entered buy zone — {reasons}; "
        f"extension {ext}; {blackout_note}. ({as_of})"
    )
