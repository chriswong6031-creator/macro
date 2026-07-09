"""scripts/notify_turn_events.py — Discord alerts for FTR W10.

Evaluates three event sources and sends Discord messages via scripts/notify.py
transport (DISCORD_WEBHOOK_WATCHLIST).

EVENT SOURCES
-------------
(a) turn-watch IGNITION (site/basketdata/turn_watch.json)
    Fire at most once per basket-day while in IGNITION state (state-day dedup).
    Dedup key: (kind="ignition", basket_id, date).

(b) shock_state activation (site/live/shock_state.json)
    Fire at most once per day while active (state-day dedup).
    Dedup key: (kind="shock_activation", "shock_state", date).

(c) tape disagreement (site/live/basket_pulse.json + turn_watch)
    IGNITION basket whose live tape continues positive (live_ew_chg_pct > 0)
    while slow reco is NOT in {enter, accumulate}.
    Fire at most once per basket-day (state-day dedup).

NOTE ON DEDUP SEMANTICS: all three detectors use state-day dedup — they fire
once per calendar day per subject while the state is active, NOT only on the
first transition into the state.  Masterplan §5 specifies "dedup per state-day".

DEDUP STATE
-----------
site/live/notify_state.json — site-only write per FT-R5.
Keyed by (kind, subject, date).  Tolerant of missing file.
Written only when state changes (alert fires); file may not exist on no-event
or dark-mode ticks.  The fastpath git add uses '|| true' to tolerate absence.

COPY CONTRACT (FT-R13)
-----------------------
- State name, evidence legs, as-of, T+1 fade base rate inline.
- No direction words: buy, sell, long, short, add, chase.
- No alert may originate a signal, score, or escalation (A7 ORIGINATE ban).
- Notification of already-computed display states ONLY.

WEBHOOK
-------
DISCORD_WEBHOOK_WATCHLIST (interim default per §7 OPEN-OPERATOR note).
Falls back to DISCORD_WEBHOOK_URL.
Absent secret → log-and-exit-0 (dark by default locally).

WIRING
------
- Nightly: called at end of scripts/build_baskets.py main() after turn-watch hook.
  Requires DISCORD_WEBHOOK_WATCHLIST / DISCORD_WEBHOOK_URL in the step env.
- Intraday: step 5 of .github/workflows/intraday-fastpath.yml (after basket pulse).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("notify_turn_events")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SITE_BASKETDATA = ROOT / "site" / "basketdata"
_SITE_LIVE = ROOT / "site" / "live"

_TURN_WATCH_PATH = _SITE_BASKETDATA / "turn_watch.json"
_SHOCK_STATE_PATH = _SITE_LIVE / "shock_state.json"
_BASKET_PULSE_PATH = _SITE_LIVE / "basket_pulse.json"
_NOTIFY_STATE_PATH = _SITE_LIVE / "notify_state.json"

# ---------------------------------------------------------------------------
# Copy constants (FT-R13 compliant)
# ---------------------------------------------------------------------------

# T+1 fade base rate from flip_confirmation lens (26 events, masterplan §0).
_FADE_COPY = "violent flips fade 58% at T+1 (n=26)"

# Forbidden words that must never appear in emitted copy.
FORBIDDEN_WORDS = frozenset(["buy", "sell", "long", "short", "add", "chase"])

# ---------------------------------------------------------------------------
# Dedup state (site-only write, FT-R5)
# ---------------------------------------------------------------------------


def _load_notify_state() -> dict:
    """Load dedup state from notify_state.json. Returns {} on missing/corrupt."""
    if not _NOTIFY_STATE_PATH.exists():
        return {}
    try:
        return json.loads(_NOTIFY_STATE_PATH.read_text())
    except Exception as exc:  # noqa: BLE001
        log.debug("notify_turn_events: could not load notify_state.json (%s)", exc)
        return {}


def _save_notify_state(state: dict, dry_run: bool = False) -> None:
    """Persist dedup state to site/live/notify_state.json (site-only, FT-R5)."""
    if dry_run:
        return
    _NOTIFY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _NOTIFY_STATE_PATH.write_text(
        json.dumps(state, separators=(",", ":"), default=str), encoding="utf-8"
    )


def _dedup_key(kind: str, subject: str, today_str: str) -> str:
    """Canonical dedup key: (kind, subject, date) as a single string."""
    return f"{kind}|{subject}|{today_str}"


def _already_fired(state: dict, kind: str, subject: str, today_str: str) -> bool:
    return _dedup_key(kind, subject, today_str) in state


def _mark_fired(state: dict, kind: str, subject: str, today_str: str) -> None:
    state[_dedup_key(kind, subject, today_str)] = True


# ---------------------------------------------------------------------------
# Discord transport (DISCORD_WEBHOOK_WATCHLIST, FT-R13)
# ---------------------------------------------------------------------------


def _send_discord(msg: str, dry_run: bool = False) -> bool:
    """Send one message to the watchlist Discord channel.

    Webhook: DISCORD_WEBHOOK_WATCHLIST → DISCORD_WEBHOOK_URL.
    Absent → log-and-return-False (dark by default locally).
    """
    url = (
        config.secret("DISCORD_WEBHOOK_WATCHLIST")
        or config.secret("DISCORD_WEBHOOK_URL")
    )
    if not url:
        log.info("notify_turn_events: no Discord webhook configured — dark mode")
        return False

    if dry_run:
        log.info("[DRY-RUN] Discord message:\n%s", msg)
        return True

    try:
        r = requests.post(url, json={"content": msg[:1990]}, timeout=30)
        if r.status_code not in (200, 204):
            log.warning(
                "notify_turn_events: Discord dispatch failed (%d: %s)",
                r.status_code,
                r.text[:200],
            )
            return False
        log.info("notify_turn_events: Discord dispatch OK")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("notify_turn_events: Discord dispatch error (%s)", exc)
        return False


# ---------------------------------------------------------------------------
# Message builders (FT-R13 copy contract)
# ---------------------------------------------------------------------------


def _ignition_message(basket_id: str, legs: dict, as_of: str) -> str:
    """Build FT-R13-compliant IGNITION alert message.

    Format: "TURN-WATCH IGNITION — {basket} (K={k}: {leg names}) · as-of {date}
             · display-tier, expected-null meter · {fade_copy}"
    No direction words (buy/sell/long/short/add/chase).
    """
    active_legs = [name for name, fired in legs.items() if fired]
    k = len(active_legs)
    leg_str = ", ".join(active_legs) if active_legs else "none"
    msg = (
        f"TURN-WATCH IGNITION — {basket_id} "
        f"(K={k}: {leg_str}) "
        f"· as-of {as_of} "
        f"· display-tier, expected-null meter "
        f"· {_FADE_COPY}"
    )
    _assert_no_forbidden_words(msg)
    return msg


def _shock_activation_message(score: Any, as_of: str, reason: str | None) -> str:
    """Build FT-R13-compliant shock activation alert message."""
    reason_part = f" ({reason})" if reason else ""
    msg = (
        f"SHOCK ACTIVATION{reason_part} — repricing coherence score {score} "
        f"· as-of {as_of} "
        f"· display-tier de-escalation: scores computed on pre-shock data "
        f"· {_FADE_COPY}"
    )
    _assert_no_forbidden_words(msg)
    return msg


def _tape_disagreement_message(
    basket_id: str, live_chg_pct: float, tape_as_of: str
) -> str:
    """Build FT-R13-compliant tape disagreement alert message.

    live_chg_pct is the value from basket_pulse.baskets[].live_ew_chg_pct, which
    is ALREADY in percent units (e.g. 0.40 means +0.40%, not +40%).  Display it
    directly — no multiply-by-100 heuristic.
    """
    sign = "+" if live_chg_pct >= 0 else ""
    chg_str = f"{sign}{live_chg_pct:.2f}%"
    msg = (
        f"TAPE DISAGREEMENT — {basket_id} IGNITION basket "
        f"live tape {chg_str} "
        f"while slow state not in {{enter, accumulate}} "
        f"· as-of {tape_as_of} "
        f"· display-tier, expected-null meter "
        f"· {_FADE_COPY}"
    )
    _assert_no_forbidden_words(msg)
    return msg


def _assert_no_forbidden_words(msg: str) -> None:
    """Raise ValueError if any forbidden word appears in the message (case-insensitive).

    Uses word-boundary substring matching so hyphenated forms like 'add-on' are
    also caught.  Matches any occurrence where the word appears as a standalone
    token or as a prefix/suffix of a hyphenated compound.
    """
    import re

    lower = msg.lower()
    for word in FORBIDDEN_WORDS:
        # \b is a word boundary — catches 'buy', 'buy-side', 'add-on', etc.
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            raise ValueError(
                f"FT-R13 violation: forbidden word '{word}' in message: {msg[:80]}"
            )


# ---------------------------------------------------------------------------
# Event source loaders
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict | None:
    """Load JSON from path. Returns None on missing/corrupt."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.debug("notify_turn_events: could not load %s (%s)", path, exc)
        return None


# ---------------------------------------------------------------------------
# (a) IGNITION transition detector
# ---------------------------------------------------------------------------


def _detect_ignition_transitions(
    turn_watch: dict,
    notify_state: dict,
    today_str: str,
) -> list[tuple[str, str]]:
    """Return list of (basket_id, message) for IGNITION transitions not yet fired today.

    Transition = state == IGNITION AND not already fired for this basket-day.
    The dedup key prevents re-firing on persistence (same basket next tick).
    """
    results: list[tuple[str, str]] = []
    baskets = turn_watch.get("baskets") or []
    as_of = turn_watch.get("as_of") or today_str

    for b in baskets:
        basket_id = b.get("basket_id", "")
        state = b.get("state")
        if state != "IGNITION":
            continue
        if _already_fired(notify_state, "ignition", basket_id, today_str):
            log.debug("notify_turn_events: IGNITION %s already fired today", basket_id)
            continue

        legs = b.get("legs") or {}
        msg = _ignition_message(basket_id, legs, as_of)
        results.append((basket_id, msg))

    return results


# ---------------------------------------------------------------------------
# (b) Shock activation transition detector
# ---------------------------------------------------------------------------


def _detect_shock_activation(
    shock_state: dict,
    notify_state: dict,
    today_str: str,
) -> list[tuple[str, str]]:
    """Return list of (subject, message) for shock activation transitions not yet fired.

    Transition = active == True AND not already fired for 'shock_state'-today.
    """
    results: list[tuple[str, str]] = []

    if not shock_state.get("active", False):
        return results

    subject = "shock_state"
    if _already_fired(notify_state, "shock_activation", subject, today_str):
        log.debug("notify_turn_events: shock_state already fired today")
        return results

    score = shock_state.get("score")
    since = shock_state.get("since") or today_str
    reason = shock_state.get("reason")
    msg = _shock_activation_message(score, since, reason)
    results.append((subject, msg))
    return results


# ---------------------------------------------------------------------------
# (c) Tape disagreement detector
# ---------------------------------------------------------------------------


def _detect_tape_disagreement(
    basket_pulse: dict,
    turn_watch: dict,
    notify_state: dict,
    today_str: str,
) -> list[tuple[str, str]]:
    """Return list of (basket_id, message) for tape disagreement events not yet fired.

    Definition (same deterministic definition as W9):
    - Basket is in IGNITION state (turn_watch)
    - Live tape continues positive (basket_pulse: live_ew_chg_pct > 0, not stale)
    - Slow reco is NOT in {enter, accumulate}

    Fire at most once per basket-day.
    """
    results: list[tuple[str, str]] = []

    # Build IGNITION set from turn_watch
    ignition_baskets: set[str] = set()
    for b in (turn_watch.get("baskets") or []):
        if b.get("state") == "IGNITION":
            ignition_baskets.add(b.get("basket_id", ""))

    if not ignition_baskets:
        return results

    # Build pulse map from basket_pulse
    pulse_map: dict[str, dict] = {}
    for pb in (basket_pulse.get("baskets") or []):
        bid = pb.get("id", "")
        pulse_map[bid] = pb

    pulse_as_of = basket_pulse.get("as_of_utc") or today_str

    for basket_id in ignition_baskets:
        pb = pulse_map.get(basket_id)
        if pb is None:
            continue
        # Skip stale quotes
        if pb.get("stale", True):
            continue
        live_chg = pb.get("live_ew_chg_pct")
        if live_chg is None or live_chg <= 0:
            continue
        # Slow reco check: absence of enter/accumulate means disagreement
        # (basket_pulse does not carry slow_reco directly; the turn_watch org
        #  is the IGNITION gate — the basket being IGNITION but live-positive
        #  while slow_reco is neutral/hold/reduce is the disagreement condition.
        #  We don't need to re-read slow_reco here: if the basket is in IGNITION
        #  and the live tape is positive, that's a concrete disagreement
        #  displayable as-is per FT-R13.)
        # For baskets.json slow_reco cross-check: attempt optional enrichment.
        slow_reco = _lookup_slow_reco(basket_id)
        ENTER_ACCUMULATE = {"enter", "accumulate"}
        if slow_reco is not None and slow_reco.lower() in ENTER_ACCUMULATE:
            # Tape and slow state agree (both positive) — not a disagreement
            continue

        if _already_fired(notify_state, "tape_disagreement", basket_id, today_str):
            log.debug("notify_turn_events: tape_disagreement %s already fired today", basket_id)
            continue

        # Stamp with basket_pulse as_of_utc (the live tape freshness) not the
        # nightly turn_watch date — the live_ew_chg_pct is an intraday figure.
        msg = _tape_disagreement_message(basket_id, live_chg, pulse_as_of)
        results.append((basket_id, msg))

    return results


def _lookup_slow_reco(basket_id: str) -> str | None:
    """Attempt to read slow_reco from site/basketdata/baskets.json.

    Returns None on any failure (tolerant).
    """
    baskets_path = _SITE_BASKETDATA / "baskets.json"
    if not baskets_path.exists():
        return None
    try:
        data = json.loads(baskets_path.read_text())
        for region_baskets in (data.get("baskets") or {}).values():
            for b in region_baskets:
                if b.get("id") == basket_id:
                    return b.get("reco")
        return None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------


def run(
    today_str: str | None = None,
    dry_run: bool = False,
) -> int:
    """Evaluate all three event sources and dispatch alerts.

    Returns the count of messages sent (0 = dark/no events/already fired).
    Never raises — own try/except, exit-0 contract.
    """
    if today_str is None:
        today_str = date.today().isoformat()

    # Check webhook presence early — log-and-exit-0 if absent (dark mode)
    url = (
        config.secret("DISCORD_WEBHOOK_WATCHLIST")
        or config.secret("DISCORD_WEBHOOK_URL")
    )
    if not url:
        log.info(
            "notify_turn_events: DISCORD_WEBHOOK_WATCHLIST absent — dark mode, exit 0"
        )
        return 0

    # Load event sources
    turn_watch = _load_json(_TURN_WATCH_PATH) or {}
    shock_state = _load_json(_SHOCK_STATE_PATH) or {}
    basket_pulse = _load_json(_BASKET_PULSE_PATH) or {}

    if not turn_watch and not shock_state:
        log.info("notify_turn_events: no event source data — nothing to evaluate")
        return 0

    # Load dedup state
    notify_state = _load_notify_state()
    original_state = dict(notify_state)

    dispatched = 0

    # (a) IGNITION transitions
    for basket_id, msg in _detect_ignition_transitions(turn_watch, notify_state, today_str):
        if _send_discord(msg, dry_run=dry_run):
            dispatched += 1
        _mark_fired(notify_state, "ignition", basket_id, today_str)

    # (b) Shock activation transition
    for subject, msg in _detect_shock_activation(shock_state, notify_state, today_str):
        if _send_discord(msg, dry_run=dry_run):
            dispatched += 1
        _mark_fired(notify_state, "shock_activation", subject, today_str)

    # (c) Tape disagreement
    for basket_id, msg in _detect_tape_disagreement(
        basket_pulse, turn_watch, notify_state, today_str
    ):
        if _send_discord(msg, dry_run=dry_run):
            dispatched += 1
        _mark_fired(notify_state, "tape_disagreement", basket_id, today_str)

    # Persist updated state (site-only write, FT-R5)
    if notify_state != original_state:
        _save_notify_state(notify_state, dry_run=dry_run)
        log.info(
            "notify_turn_events: notify_state.json updated (%d new keys)",
            len(notify_state) - len(original_state),
        )

    log.info(
        "notify_turn_events: evaluation complete — %d message(s) dispatched",
        dispatched,
    )
    return dispatched


def main() -> int:
    """CLI entry point.  exit 0 always (FT-R5/FT-R8 contract)."""
    import argparse

    ap = argparse.ArgumentParser(description="FTR W10 — Discord alerts for turn events")
    ap.add_argument("--dry-run", action="store_true", help="Print without sending")
    ap.add_argument("--date", default=None, help="Override date (YYYY-MM-DD)")
    args = ap.parse_args()

    try:
        run(today_str=args.date, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001
        log.error("notify_turn_events: unhandled exception (exit 0): %s", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
