"""engine.prophet_live.cn_states — the mainland intraday state machine (CN-PR-1, pure).

Stdlib only: no pandas, no network, no filesystem. :mod:`scripts.cn_live_evaluator`
owns every side effect (quote load, R2 get/put, the served write); this module owns
the decisions, so the whole pass is drivable from a test with three dicts — the same
split :mod:`engine.prophet_live.live_states` uses for the US lane.

LANE LAW (spec §5, inherited verbatim from the US program):
  * NO ``data/`` WRITES ANYWHERE ON THIS PATH and no git. The lane runs ~70 times a
    session; ``asia-close`` is the sole writer of ``data/cn_prophet_live/`` and the
    only thing that confirms, grades or advances a ledger.
  * The NIGHTLY IS THE SINGLE WRITER of the canonical board. Nothing here scores,
    ranks or re-derives a signal: it compares a delayed price to levels the arm
    already measured, and the frozen score/rank/lane ride the pack unchanged.
  * KILL SWITCH ``CN_PROPHET_LIVE_NO_PUBLISH=1`` refuses every publish on this lane
    (:func:`publish_json`), separate from the US ``PROPHET_LIVE_NO_PUBLISH``.

WHAT IS REUSED AND WHAT IS NOT. The US module's PURE machinery — the debounce,
the two-edge hysteresis, the SINCE clock, the dark-vs-unknown split, the levels
vocabulary — is imported and driven, not copied: one definition of "a cross needs
two consecutive passes" for the whole estate. What could NOT be reused is every
function in it that hardcodes ET or the NYSE calendar (``et_clock``, ``session_et``,
``session_phase``, ``in_window``, ``last_completed_session``), because the mainland
clock is not the US clock with different numbers (see :mod:`engine.prophet_live.cn_clock`).
Those have CN twins HERE. ``live_states`` itself is not edited.

THE FOUR CN-SPECIFIC CORRECTNESS RULES, each with a dedicated test:

  a. QUOTE AGE IS MEASURED AGAINST THE SESSION, NEVER THE WALL CLOCK. See
     :func:`engine.prophet_live.cn_clock.expected_latest_quote_time`. A quote stamped
     11:29 read at 13:02 CST is FRESH; one stamped 10:15 read at 14:30 is STALE.
  b. THE LUNCH BREAK FREEZES TRANSITIONS. During ``session_break`` (and ``pre_open``
     and the ``closing_auction``) a pass still runs, still refreshes price and
     ``market_status``, and still publishes — but no public state changes, no fade
     fires, and the debounce counters carry intact. The artifact stamps
     ``market_phase`` so a reader can never mistake a frozen state for a fresh verdict.
  c. A STALE PACK DARKS THE WHOLE ARTIFACT. ``pack.as_of`` must equal the last
     completed mainland session; otherwise ``dark(stale_pack)`` with ``prev_states``
     carried, so a settlement failure degrades the NEXT session honestly instead of
     evaluating today's tape against N-2 thresholds.
  d. ONE PRICE BASIS. The pack's levels are prices on the split+dividend adjusted
     ``data/china_stocks`` store; the tape is a raw vendor print. Both are named on
     every payload and :func:`engine.prophet_live.interval.basis_audit` asserts per
     name that they still describe the same scale. Past tolerance that NAME goes dark
     with ``basis_mismatch`` — never silently mixed, and never the whole board.

AND THE TWO CN HONESTY RULES THE US LANE HAS NO WORD FOR:

  e. A LIMIT-LOCKED PRICE IS A REAL PRICE. A name pinned at ±10/20% has traded; the
     state machine evaluates it exactly like any other and the ``market_status``
     overlay names the regime. A one-price session is not a missing observation, and
     collapsing the two would delete the single most informative thing an A-share
     tape says all day.
  f. NO QUOTE MEANS ``unavailable``, NEVER YESTERDAY'S PRICE. A name the feed does
     not carry — or carries past the freshness ceiling — publishes no price at all.
     When the rest of the board IS observable the overlay says
     ``suspended_suspected`` (停牌 is the overwhelmingly likely cause of one silent
     name on a healthy tape); when it is not, it says ``unavailable`` and the
     board-level ``coverage_pct`` carries the disclosure. Neither ever fills.

VOCABULARY IS LOAD-BEARING. Nothing here says fired, confirmed, refuted or
validated, and no falsifier language reaches a user surface (operator 2026-07-27).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from engine.prophet_live import cn_clock
from engine.prophet_live import live_states as LS
from engine.prophet_live import r2io
from engine.prophet_live.interval import (
    DEFAULT_PACK_ADJUSTMENT,
    LIVE_QUOTE_ADJUSTMENT,
    basis_audit,
)

log = logging.getLogger(__name__)

SCHEMA = "cn_prophet_live.states/v1"
EVENTS_SCHEMA = "cn_prophet_live.events/v1"

# ─────────────────────────────────────────────────────────────────────────────
# R2 keys. THEY LIVE IN THE STDLIB-ONLY MODULE on purpose — the same reason
# :mod:`engine.prophet_live.interval` exists. The pack builder needs pandas and the
# evaluator installs none, so a key defined in ``cn_pack`` would drag pandas onto
# the */5 lane's import path. ``cn_pack`` imports these from here instead.
# ─────────────────────────────────────────────────────────────────────────────

CN_PACK_KEY = "live_flow/cn_prophet_live_armed.json"
CN_LIVE_KEY = "live_flow/cn_prophet_live.json"
CN_EVENTS_PREFIX = "live_flow/cn_prophet_live_events"

#: The kill switch, deliberately its OWN variable rather than a second reader of the
#: US one: the two lanes run on the same box at different hours, and standing down
#: the mainland evaluator must not require standing down the US one (or vice versa).
NO_PUBLISH_ENV = "CN_PROPHET_LIVE_NO_PUBLISH"

#: Per-name presentation overlay (spec §2), ORTHOGONAL to the public state. The state
#: machine answers "what is this name doing about its armed level"; this answers "what
#: regime is the tape in for this name". A row carries exactly one of each.
MARKET_STATUSES: tuple[str, ...] = ("trading", "session_break", "limit_up_locked",
                                    "limit_down_locked", "unavailable",
                                    "suspended_suspected")

#: The two artifact revisions. ``close_provisional`` is the post-close board; the
#: nightly's own rebuild later supersedes it with `canonical` through the CN-PR-2
#: confirmation receipt. NOTHING here ever writes `canonical`.
REVISION_INTRADAY = "intraday_provisional"
REVISION_CLOSE = "close_provisional"

#: What share of the ARMED set must be close-observed before a close board may be
#: assembled (spec §5). Below it the artifact publishes what it can see with
#: ``close_pending: true`` — it never manufactures a close.
CLOSE_COVERAGE_FLOOR_PCT = 80.0

#: Vendor price bases that can carry a SETTLED close. ``regular`` is Yahoo spark's
#: ``regularMarketPrice`` stamp, ``day`` the daily-bar rung. A ``prev``/``minute``/
#: ``trade`` basis after 07:00 UTC is not evidence of a close, it is evidence of a
#: rung that has not settled yet.
CLOSE_BASES: frozenset[str] = frozenset({"regular", "day"})

#: The T2 repaint rate this program discloses on every payload (spec §6). It is a
#: MEASURED constant from the arming-side census that motivated the mandatory event
#: latch (the 300363.SZ class: 86 un-fire events over 78 names in 12 sessions), NOT
#: something this lane recomputes — a live lane that re-derived its own repaint rate
#: would be grading itself. The surface renders it as a tooltip, never as a state.
T2_REPAINT_PCT = 15.1

#: Config block name. Falls through to the US ``prophet_live`` block for everything it
#: does not override, so the derived quote-age ceiling
#: (``live.delayed_min + quote_slack_min``) has ONE definition estate-wide.
CFG_BLOCK = "cn_prophet_live"


def cn_live_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve the CN evaluator config: ``cn_prophet_live`` over ``prophet_live``.

    The DERIVED ceiling is inherited, not re-derived: ``live_cfg`` already resolves
    ``quote_max_age_min`` to ``live.delayed_min + quote_slack_min`` (15 + 10 = 25
    today) precisely so a hardcoded number cannot outlive a real-time entitlement. The
    CN block then overrides only what genuinely differs — and today that is nothing
    but the slack, which is left alone. What CN does differently is not the ceiling,
    it is WHAT THE AGE IS MEASURED AGAINST (rule (a) above).
    """
    out = LS.live_cfg(cfg)
    try:
        block = (cfg or {}).get(CFG_BLOCK) or {}
        for k, v in block.items():
            if k in ("window_et", "confirm_window_start"):
                # US-clock keys. A CN override of them would be meaningless at best
                # and an hour-wrong window at worst; the CN clock owns those answers.
                continue
            if isinstance(out.get(k), dict) and isinstance(v, dict):
                out[k] = {**out[k], **v}
            elif k in out and out[k] is not None and not isinstance(out[k], dict):
                out[k] = type(out[k])(v)
            else:
                out[k] = v
        if block.get("quote_max_age_min") is not None:
            out["quote_max_age_min"] = float(block["quote_max_age_min"])
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_states: bad %s config (%s) — US defaults stand", CFG_BLOCK, exc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Publishing (the ONE side effect this module owns, because the kill switch has to
# be enforced at the write and nowhere else)
# ─────────────────────────────────────────────────────────────────────────────

def no_publish() -> bool:
    """True when the CN kill switch is set."""
    return os.environ.get(NO_PUBLISH_ENV, "").strip() not in ("", "0", "false")


def publish_json(key: str, payload: Any, *, s3=None) -> bool:
    """PUT one CN JSON object. False (never a raise) when refused or impossible.

    NOT :func:`engine.prophet_live.r2io.put_json`, deliberately: that function reads
    the US kill switch, so routing CN writes through it would make standing down one
    market stand down the other. The CLIENT construction is still shared (r2io owns
    the R2 endpoint/credential/checksum contract) — only the switch is CN's own.
    """
    if no_publish():
        print(f"::warning title=cn-prophet-live::{NO_PUBLISH_ENV} is set — refusing to "
              f"write {key}", flush=True)
        return False
    cl = s3 if s3 is not None else r2io.client()
    if cl is None:
        log.warning("cn_states: no R2 credentials — %s not published", key)
        return False
    try:
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_states: %s payload is not JSON-safe: %s", key, exc)
        return False
    try:
        cl.put_object(Bucket=r2io.bucket(), Key=key, Body=body,
                      ContentType="application/json")
        log.info("cn_states: published %s (%d bytes)", key, len(body))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_states: PUT %s failed: %s", key, exc)
        return False


def events_key(session: str, stamp: str) -> str:
    """``live_flow/cn_prophet_live_events/<YYYY-MM-DD>/<HHMMSS>.json`` — one per pass.

    Object-per-pass, never read-modify-write: two passes cannot both be holding the
    day's file, so nothing can lose a row (the shared-``.tmp`` erasure class).
    """
    return f"{CN_EVENTS_PREFIX}/{session}/{stamp}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Quotes
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(value: Any) -> datetime | None:
    """A quote's timestamp as an aware UTC datetime, from either shape.

    TWO SHAPES REACH THIS LANE and they do not share a field. The local VPS plane
    (``live_verify._quotes_from_snapshot``) carries ``ts_ms`` epoch milliseconds; a
    direct ``engine.live_quotes.fetch_quotes`` call carries ``quote_ts`` ISO. Both
    are normalised HERE, once, so nothing downstream has to know which source a row
    came from — and so a row with neither reads as "not measured" rather than "now".
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        num = float(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    # Epoch milliseconds (the local plane's ts_ms). Seconds would put every quote in
    # 1970, which the freshness gate would read as "very stale" rather than as a bug,
    # so the magnitude check is a real guard and not defensive noise.
    if num > 1e11:
        num /= 1000.0
    try:
        return datetime.fromtimestamp(num, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def normalize_quote(q: Any) -> dict[str, Any] | None:
    """One quote in this lane's shape, or None when it carries no usable price.

    ``{price, prev_close, quote_ts (datetime|None), quote_ts_iso, price_basis, source}``.
    A row with no price is dropped rather than kept with ``price: None``: a quote that
    cannot answer "what is it trading at" is not a quote, and keeping it would make
    ``observable_n`` count rows instead of observations.
    """
    if not isinstance(q, dict):
        return None
    px = q.get("price")
    if px is None:
        return None
    try:
        price = float(px)
    except (TypeError, ValueError):
        return None
    if not (price > 0):
        return None
    ts = _parse_ts(q.get("quote_ts") if q.get("quote_ts") is not None else q.get("ts_ms"))
    prev = q.get("prev_close")
    try:
        prev = float(prev) if prev is not None else None
    except (TypeError, ValueError):
        prev = None
    return {
        "price": price,
        "prev_close": prev,
        "quote_ts": ts,
        "quote_ts_iso": _iso(ts) if ts is not None else None,
        "price_basis": (str(q["price_basis"]) if q.get("price_basis") else None),
        "source": (str(q["source"]) if q.get("source") else None),
    }


def normalize_quotes(quotes: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """:func:`normalize_quote` over a whole view, upper-cased keys, unusable dropped."""
    out: dict[str, dict[str, Any]] = {}
    for tkr, q in (quotes or {}).items():
        n = normalize_quote(q)
        if n is not None:
            out[str(tkr).upper()] = n
    return out


def _iso(t: datetime | None) -> str | None:
    if t is None:
        return None
    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ─────────────────────────────────────────────────────────────────────────────
# The market_status overlay
# ─────────────────────────────────────────────────────────────────────────────

def market_status(ticker: str, quote: dict[str, Any] | None, *, phase: str,
                  fresh: bool, board_observable: bool) -> str:
    """The presentation overlay for one name. Precedence is deliberate and tested.

    1. NO LAWFUL OBSERVATION beats everything — a name we cannot see has no regime.
       ``suspended_suspected`` when the REST of the board is readable (one silent name
       on a healthy A-share tape is overwhelmingly a 停牌, not a feed hole);
       ``unavailable`` when it is not, because attributing a board-wide outage to
       1,700 simultaneous suspensions is a confidently wrong cause.
    2. LIMIT LOCK beats the phase. A name pinned at its band edge is the single most
       informative thing an A-share tape prints, and a lunchtime reader still needs to
       know the morning ended one-price (rule (e) above).
    3. ``session_break`` — the tape is shut, not stale.
    4. ``trading``.
    """
    if quote is None or not fresh:
        return "suspended_suspected" if board_observable else "unavailable"
    lock = cn_clock.limit_lock_status(quote.get("price"), quote.get("prev_close"),
                                      cn_clock.limit_pct_for(ticker))
    if lock:
        return lock
    if phase == "session_break":
        return "session_break"
    return "trading"


# ─────────────────────────────────────────────────────────────────────────────
# Whole-artifact shapes
# ─────────────────────────────────────────────────────────────────────────────

def _liveness(*, now: datetime, phase: str, session: str, source: str | None,
              source_asof: str | None, universe_n: int, observable_n: int,
              candidate_n: int, coverage_pct: float | None,
              ages_sec: list[float] | None = None,
              started_at: str | None = None,
              close_observed_at: str | None = None,
              first_close_board_at: str | None = None,
              revision: str = REVISION_INTRADAY,
              failure_stage: str | None = None,
              failure_reason: str | None = None) -> dict[str, Any]:
    """The §6 liveness record, written EVERY pass — dark passes included.

    ``runtime_visible_at`` / ``browser_visible_at`` are deliberately ABSENT: they are
    measured by the sentinel reader and the browser acceptance instrument, never
    self-reported (#5222 — a producer that grades its own visibility always passes).
    """
    ages = sorted(a for a in (ages_sec or []) if a is not None)
    p50 = round(ages[len(ages) // 2], 1) if ages else None
    return {
        "expected_session": session,
        "market_phase": phase,
        "source": source,
        "source_asof": source_asof,
        "quote_age_sec_p50": p50,
        "universe_n": int(universe_n),
        "observable_n": int(observable_n),
        "candidate_n": int(candidate_n),
        "coverage_pct": coverage_pct,
        "evaluation_started_at": started_at or _iso(now),
        "artifact_written_at": _iso(now),
        "close_observed_at": close_observed_at,
        "first_close_board_at": first_close_board_at,
        "provisional_revision": revision,
        # The nightly's canonical rebuild fills these through the CN-PR-2 receipt.
        # Present-and-null on every payload so a consumer never has to tell "not yet
        # confirmed" from "this payload predates the field".
        "canonical_revision": None,
        "confirmation_status": None,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
    }


def dark_artifact(reason: str, *, now: datetime, session: str, phase: str,
                  pack_as_of: str | None = None, detail: str | None = None,
                  quote_source: str | None = None, quote_asof: str | None = None,
                  delay_min: int | None = None,
                  carry: dict[str, Any] | None = None,
                  failure_stage: str | None = None) -> dict[str, Any]:
    """A whole-artifact dark payload. No states — a guessed state is the failure.

    ``carry`` preserves the SAME SESSION's previous per-name states under
    ``prev_states``. Without it a single dark pass wipes the session's debounce: the
    PUT replaces ``names`` with ``{}``, the next pass finds no predecessor, and every
    name that had banked a confirming pass starts over — so one stale-pack pass could
    cost the whole session its crosses. The dark payload still publishes NO state of
    its own; ``prev_states`` is history, explicitly labelled.
    """
    return {
        "schema": SCHEMA,
        "session": session,
        "built_at": _iso(now),
        "market_phase": phase,
        "pack_as_of": pack_as_of,
        "revision": REVISION_INTRADAY,
        "close_pending": False,
        "quote_source": quote_source,
        "delay_floor_min": delay_min,
        "coverage": {"universe_n": 0, "armed_n": 0, "observable_n": 0,
                     "coverage_pct": None},
        "repaint_disclosure": {"t2_repaint_pct": T2_REPAINT_PCT},
        "names": {},
        "close_board": None,
        "liveness": _liveness(now=now, phase=phase, session=session,
                              source=quote_source, source_asof=quote_asof,
                              universe_n=0, observable_n=0, candidate_n=0,
                              coverage_pct=None,
                              failure_stage=failure_stage or "evaluator",
                              failure_reason=reason),
        "prev_states": dict(carry or {}),
        "dark": {"reason": reason, **({"detail": detail} if detail else {})},
        "events": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# The pass
# ─────────────────────────────────────────────────────────────────────────────

def resolve_prev(prev: dict[str, Any] | None, *, session: str, phase: str,
                 last_session: str) -> tuple[dict[str, Any], str | None]:
    """``(prev_states, carried_from_session)`` for this pass.

    SAME SESSION is the ordinary case and carries everything — counters included.

    PRE-OPEN carries the PRIOR session's public states for display (spec §2: "states
    carry over from prior session close, marked ``pre_open``") with the DEBOUNCE
    COUNTERS ZEROED. Carrying the counters across a session boundary would let a
    cross banked at yesterday's close confirm on the first tick of today, which is
    precisely the 1-tick promotion the debounce exists to prevent.
    """
    if not isinstance(prev, dict):
        return {}, None
    prev_session = str(prev.get("session") or "")
    states = prev.get("names") or prev.get("prev_states") or {}
    if not isinstance(states, dict):
        return {}, None
    if prev_session == session:
        return dict(states), None
    if phase == "pre_open" and prev_session == last_session:
        carried = {}
        for tkr, st in states.items():
            if not isinstance(st, dict):
                continue
            carried[tkr] = {"state": st.get("state"), "since_ts": st.get("since_ts"),
                            "prior_public": st.get("prior_public"),
                            "prior_since_ts": st.get("prior_since_ts"),
                            "entered": st.get("entered"),
                            "passes": 0, "fails": 0}
        return carried, prev_session
    return {}, None


def _frozen_row(prev_row: dict[str, Any] | None, *, base: dict[str, Any],
                phase: str) -> dict[str, Any]:
    """One name's row on a FROZEN pass (rule (b)): carry the verdict, refresh the tape.

    A frozen pass is not a dark pass and not a skipped pass. The price, the quote age
    and the ``market_status`` are all genuinely NEW information — a name that went
    limit-up in the last minute of the morning must show it through lunch — while the
    STATE, the SINCE clock and the debounce counters are exactly what the last
    evaluating pass left. Nothing is inferred and nothing decays.

    With no carried verdict at all (the day's first pre-open pass, or a name that
    appeared mid-session) the row reports ``unknown``: there is no verdict to freeze,
    and the honest answer to "what is this name's state" before the market has opened
    is that the lane has not taken one. ``unknown`` is not ``dark`` — the tape is fine
    and the pack is fine; nobody has evaluated yet (``live_states``: UNKNOWN IS NOT DARK).
    """
    row = dict(base)
    prev_row = prev_row or {}
    state = str(prev_row.get("state") or "")
    if state and state in LS.PUBLIC_STATES:
        row["state"] = state
        for k in ("since_ts", "prior_public", "prior_since_ts", "entered", "passes",
                  "fails", "internal_seen", "cross_level_px", "fade_px", "fade_hi_px",
                  "dark_reason"):
            if prev_row.get(k) is not None:
                row[k] = prev_row[k]
    else:
        row["state"] = "unknown"
        row["dark_reason"] = f"frozen_no_prior:{phase}"
    row["frozen_phase"] = phase
    return row


def _name_row(entry: dict[str, Any], *, ticker: str, quote: dict[str, Any] | None,
              age_min: float | None, prev_row: dict[str, Any] | None,
              now: datetime, cfg: dict[str, Any], phase: str, fresh: bool,
              board_observable: bool, basis_gap: float | None,
              frozen: bool) -> dict[str, Any]:
    """One published per-name row (spec §6 field contract)."""
    px = quote.get("price") if quote else None
    base: dict[str, Any] = {
        "market_status": market_status(ticker, quote, phase=phase, fresh=fresh,
                                       board_observable=board_observable),
        "price": (round(float(px), 4) if px is not None else None),
        "quote_ts": (quote or {}).get("quote_ts_iso"),
        "quote_age_sec": (round(float(age_min) * 60.0) if age_min is not None else None),
        "price_basis": (quote or {}).get("price_basis"),
        "prev_close_feed": (quote or {}).get("prev_close"),
        "as_of_close_pack": entry.get("as_of_close"),
        "band_lo_px": entry.get("band_lo_px"),
        "band_hi_px": entry.get("band_hi_px"),
        "frozen": entry.get("frozen") or {},
        "dark_reason": None,
    }
    # The armed level, under the key that says what the number MEANS for this row —
    # the ``live_states`` LEVELS contract, republished verbatim (never re-rounded: the
    # pack already rounded each edge INTO the buyable region).
    if entry.get("trigger_px") is not None:
        base["trigger_px"] = entry["trigger_px"]
    if entry.get("fade_px") is not None:
        base["fade_px"] = entry["fade_px"]
    if entry.get("fade_hi_px") is not None:
        base["fade_hi_px"] = entry["fade_hi_px"]

    if frozen:
        return _frozen_row(prev_row, base=base, phase=phase)

    # The US state machine, driven — not copied. ``_resolve_state`` is private the same
    # way ``live_verify._quotes_from_snapshot`` is private and read by the US evaluator:
    # a second copy of the debounce is how two markets end up disagreeing about what a
    # cross is.
    st = LS._resolve_state(  # noqa: SLF001
        entry, price=(None if not fresh else px),
        quote_age_min=(age_min if fresh else None),
        prev=(prev_row or {}), now=now, cfg=cfg, basis_gap_pct=basis_gap)
    # CONFIRMING-INTO-CLOSE IS AN ET FLAG AND MUST NOT SURVIVE INTO A CN PAYLOAD.
    # ``_resolve_state`` raises it off ``et_clock(now) >= confirm_window_start``; a CN
    # afternoon pass at 06:00 UTC is 02:00 ET, and the CN morning at 01:30 UTC is
    # 21:30 ET the day before — which clears a 15:30 window and would raise the flag on
    # every single morning pass. It is popped and re-derived on the mainland clock.
    st.pop("confirming_into_close", None)
    st = LS._stamp_since(st, prev_row or {}, now)  # noqa: SLF001
    if st.get("state") == "forming" and phase in ("afternoon", "closing_auction") \
            and cn_clock.cst_clock(now).time() >= _confirm_from(cfg):
        st["confirming_into_close"] = True

    row = dict(base)
    reason = st.pop("reason", None)
    row.update(st)
    if reason:
        row["dark_reason"] = reason
    return row


def _confirm_from(cfg: dict[str, Any]):
    """CST wall time from which a held ``forming`` counts as confirming into the close.

    Default 14:30 — the last half hour of continuous trading, the mainland twin of the
    US 15:30 rule and for the same reason: close-dependence shrinks as the session
    ends, so that is the strongest honest moment this lane has.
    """
    from datetime import time as _time  # noqa: PLC0415
    raw = str(cfg.get("cn_confirm_window_start") or "14:30")
    try:
        h, m = raw.split(":")[:2]
        return _time(int(h), int(m))
    except Exception:  # noqa: BLE001
        return _time(14, 30)


def transitions(ticker: str, new: dict[str, Any], prev: dict[str, Any] | None, *,
                now: datetime, phase: str, session: str) -> list[dict[str, Any]]:
    """The event rows this name earns this pass — CN twin of ``live_states.transitions``.

    Same ``EVENT_KINDS`` and the same one-row-per-marker-per-name-per-session rule
    (a second copy of the marker list is how the fade marker's three siblings got
    spooled for a year while it did not exist). What differs is the phase stamp: the
    reconciler needs to know a state was taken in the ``morning`` and not the
    ``closing_auction``, and the US ``preopen|rth`` axis cannot say that.
    """
    prev = prev or {}
    rows: list[dict[str, Any]] = []
    base = {
        "ticker": ticker,
        "ts": _iso(now),
        "session": session,
        "market_phase": phase,
        "market_status": new.get("market_status"),
        "price": new.get("price"),
        "quote_age_sec": new.get("quote_age_sec"),
        "passes": new.get("passes"),
        "from": prev.get("state") or None,
        "entered": new.get("entered"),
    }
    if new.get("via"):
        base["via"] = new["via"]
    if new.get("state") != prev.get("state") and new.get("state") in LS.EVENT_KINDS:
        rows.append({**base, "kind": new["state"]})
    seen_before = set(prev.get("internal_seen") or [])
    for marker in LS.INTERNAL_MARKERS:
        if new.get("internal") == marker and marker not in seen_before:
            row = {**base, "kind": marker}
            if new.get("internal_via"):
                row.setdefault("via", new["internal_via"])
            rows.append(row)
    if new.get("confirming_into_close") and not prev.get("confirming_into_close"):
        rows.append({**base, "kind": "confirming_into_close"})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Close pass (spec §5)
# ─────────────────────────────────────────────────────────────────────────────

def close_observability(quote: dict[str, Any] | None, prev_row: dict[str, Any] | None,
                        *, now: datetime) -> tuple[bool, str, dict[str, Any]]:
    """``(observed, why, carry)`` for one name's close.

    TWO WAYS TO OBSERVE A CLOSE, and the second exists because the first cannot be
    relied on alone:

      SETTLED PRINT   ``quote_ts >= 07:00 UTC`` AND ``price_basis in {regular, day}``
                      — the vendor's own settled regular-market stamp. Clean, but a
                      vendor that is slow to re-stamp the basis field would never
                      produce it and the board would hang forever on a real close.
      STABLE TWICE    the same price, unchanged, across two passes both taken after
                      07:00 UTC. A tape that has stopped moving after the close has
                      closed; two passes is the same debounce discipline the state
                      machine uses, for the same reason.

    A print stamped BEFORE 07:00 UTC is refused under both rules however stable it is:
    it is a 14:5x print, and calling it a close is exactly the manufactured close §18
    forbids.
    """
    carry: dict[str, Any] = {}
    if not quote:
        return False, "no_quote", carry
    ts = quote.get("quote_ts")
    close_at = cn_clock.session_close_utc(now)
    px = quote.get("price")
    if ts is None or ts < close_at:
        # Pre-close print. Do NOT start the stability counter on it — a price stable
        # from 14:30 through 15:02 would otherwise "observe" a close that never
        # printed.
        return False, "pre_close_print", carry
    if str(quote.get("price_basis") or "") in CLOSE_BASES:
        return True, "settled_print", {"post_close_px": px, "post_close_passes": 1}
    prev_px = (prev_row or {}).get("post_close_px")
    prev_n = int((prev_row or {}).get("post_close_passes") or 0)
    same = prev_px is not None and px is not None and abs(float(prev_px) - float(px)) < 1e-9
    carry = {"post_close_px": px, "post_close_passes": (prev_n + 1) if same else 1}
    if same and prev_n >= 1:
        return True, "stable_two_passes", carry
    return False, "awaiting_second_pass", carry


def close_board(names: dict[str, dict[str, Any]], pack_names: dict[str, Any],
                observed: dict[str, bool]) -> list[dict[str, Any]]:
    """Ordered close-board membership (spec §5). NO client-side scoring, ever.

    Membership is exactly two populations and both come from the payload:

      1. THE FROZEN NIGHTLY LANES, restated at their close states. Order is the
         nightly's own — ``frozen.board_order``, captured at arm time — so this
         function re-STATES a board, it never re-RANKS one. That is what keeps
         §11's "no new scoring authority" true of the close path.
      2. ARMED CROSS NAMES that are ``forming`` at the close: a name that crossed
         into the gate during the session and held there. They sort after the board
         by construction (their ``board_order`` is absent) and among themselves by
         ticker, so the order is deterministic across reruns.

    Only CLOSE-OBSERVED names appear. A board name we could not observe is left OUT
    of the board rather than carried at its intraday state — the board is a claim
    about the close, and a row in it that is not a close is the lie this section
    exists to prevent. The caller publishes ``close_coverage_pct`` beside it.
    """
    rows: list[dict[str, Any]] = []
    for tkr, row in names.items():
        if not observed.get(tkr):
            continue
        entry = pack_names.get(tkr) or {}
        frozen = entry.get("frozen") or {}
        lane = frozen.get("lane")
        order = frozen.get("board_order")
        state = row.get("state")
        if lane and order is not None:
            rows.append({"ticker": tkr, "lane": lane, "board_order": int(order),
                         "state": state, "market_status": row.get("market_status"),
                         "price": row.get("price"), "since_ts": row.get("since_ts"),
                         "frozen": frozen, "revision": REVISION_CLOSE,
                         "member_via": "nightly_lane"})
        elif state == "forming":
            rows.append({"ticker": tkr, "lane": lane, "board_order": None,
                         "state": state, "market_status": row.get("market_status"),
                         "price": row.get("price"), "since_ts": row.get("since_ts"),
                         "frozen": frozen, "revision": REVISION_CLOSE,
                         "member_via": "armed_cross"})
    rows.sort(key=lambda r: (r["board_order"] is None,
                             r["board_order"] if r["board_order"] is not None else 0,
                             r["ticker"]))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# evaluate()
# ─────────────────────────────────────────────────────────────────────────────

def evaluate(pack: dict[str, Any] | None, quotes: dict[str, Any],
             prev: dict[str, Any] | None, *, now: datetime, cfg: dict[str, Any],
             quote_source: str | None = None, quote_asof: str | None = None,
             delay_min: int | None = None,
             started_at: datetime | None = None) -> dict[str, Any]:
    """One evaluator pass — the whole ``cn_prophet_live.states/v1`` payload.

    ``quotes`` is already normalised (:func:`normalize_quotes`). ``prev`` is the
    previous published artifact, read authenticated so a CDN-cached copy can never
    corrupt the debounce counters.
    """
    phase = cn_clock.phase(now)
    session = cn_clock.session_date(now).isoformat()
    expected = cn_clock.last_completed_session(now)
    prev_states, carried_from = resolve_prev(prev, session=session, phase=phase,
                                             last_session=expected)
    dark_kw = {"session": session, "phase": phase, "quote_source": quote_source,
               "quote_asof": quote_asof, "delay_min": delay_min, "carry": prev_states}

    if not pack or not isinstance(pack.get("names"), dict):
        return dark_artifact("no_pack", now=now, failure_stage="pack_missing", **dark_kw)
    pack_as_of = str(pack.get("as_of") or "")
    if pack_as_of != expected:
        # RULE (c). Yesterday's thresholds are never evaluated against today's tape.
        return dark_artifact(
            "stale_pack", now=now, pack_as_of=pack_as_of, failure_stage="pack_stale",
            detail=f"pack as_of={pack_as_of or 'none'} != last completed CN session "
                   f"{expected}", **dark_kw)

    pack_names: dict[str, Any] = pack.get("names") or {}
    tol = cfg.get("basis_tolerance_pct", 0.25)
    audit = basis_audit(pack_names, quotes, tol_pct=tol)
    gaps = audit["gaps"]
    raw_adj = pack.get("price_adjustment")
    pack_adjustment = raw_adj if isinstance(raw_adj, str) and raw_adj else DEFAULT_PACK_ADJUSTMENT
    max_age = float(cfg.get("quote_max_age_min", 25.0))
    frozen_pass = phase in cn_clock.FREEZE_PHASES
    post_close = phase == "post_close"

    # PASS ONE — freshness only. ``board_observable`` decides whether a silent name
    # reads as suspected-suspended or as unavailable, so it has to be known BEFORE the
    # first row is written. Cheap: one dict lookup and one subtraction per name.
    evaluable = [t for t, e in pack_names.items() if e.get("probed")]
    ages: dict[str, float | None] = {}
    fresh_by: dict[str, bool] = {}
    for tkr in evaluable:
        q = quotes.get(tkr)
        age = cn_clock.quote_age_min(q.get("quote_ts") if q else None, now)
        ages[tkr] = age
        fresh_by[tkr] = bool(q and age is not None and age <= max_age)
    observable_n = sum(1 for t in evaluable if fresh_by[t])
    board_observable = bool(evaluable) and (observable_n * 2 >= len(evaluable))

    names: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    state_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    dark_counts: dict[str, int] = {}
    unprobed: dict[str, int] = {}
    close_observed: dict[str, bool] = {}
    close_reasons: dict[str, int] = {}

    for tkr, entry in pack_names.items():
        if not entry.get("probed"):
            # The pack could not sweep this name — a budget cut or a data problem, not
            # anything the tape can settle. Counted by reason and left OUT of ``names``,
            # so ``names`` means "names this pass can actually speak about".
            r = str(entry.get("skip") or "not_probed")
            unprobed[r] = unprobed.get(r, 0) + 1
            continue
        q = quotes.get(tkr)
        prev_row = prev_states.get(tkr)
        row = _name_row(entry, ticker=tkr, quote=q, age_min=ages[tkr],
                        prev_row=prev_row, now=now, cfg=cfg, phase=phase,
                        fresh=fresh_by[tkr], board_observable=board_observable,
                        basis_gap=gaps.get(tkr), frozen=frozen_pass)
        if post_close:
            ok, why, carry = close_observability(q if fresh_by[tkr] else None,
                                                 prev_row, now=now)
            close_observed[tkr] = ok
            close_reasons[why] = close_reasons.get(why, 0) + 1
            row.update(carry)
            row["close_observed"] = ok
            row["close_observed_via"] = why if ok else None
        names[tkr] = row
        st = str(row.get("state") or "unknown")
        state_counts[st] = state_counts.get(st, 0) + 1
        ms = str(row.get("market_status") or "unavailable")
        status_counts[ms] = status_counts.get(ms, 0) + 1
        if st == "dark":
            r = str(row.get("dark_reason") or "unspecified")
            dark_counts[r] = dark_counts.get(r, 0) + 1
        if not frozen_pass:
            events.extend(transitions(tkr, row, prev_row, now=now, phase=phase,
                                      session=session))

    armed_n = len(names)
    coverage_pct = round(observable_n / armed_n * 100.0, 1) if armed_n else None

    # THE CLOSE BOARD (spec §5). Never manufactured: below the floor the artifact
    # publishes what it can genuinely observe and says so.
    board: dict[str, Any] | None = None
    revision = REVISION_INTRADAY
    close_pending = False
    prev_first_board = ((prev or {}).get("liveness") or {}).get("first_close_board_at") \
        if str((prev or {}).get("session") or "") == session else None
    first_close_board_at = prev_first_board
    close_observed_at = None
    if post_close:
        close_n = sum(1 for v in close_observed.values() if v)
        close_cov = round(close_n / armed_n * 100.0, 1) if armed_n else 0.0
        close_observed_at = _iso(now) if close_n else None
        rows = close_board(names, pack_names, close_observed)
        if close_cov >= CLOSE_COVERAGE_FLOOR_PCT:
            revision = REVISION_CLOSE
            first_close_board_at = prev_first_board or _iso(now)
            board = {"revision": REVISION_CLOSE, "close_coverage_pct": close_cov,
                     "close_pending": False, "observed_n": close_n,
                     "armed_n": armed_n, "rows": rows,
                     "observability": dict(sorted(close_reasons.items())),
                     "first_close_board_at": first_close_board_at}
        else:
            # BELOW THE FLOOR. Publish the observable subset, keep intraday semantics,
            # and say `close_pending`. Past 07:15 UTC this is the FINAL honest answer
            # for the session — the settlement lane supersedes it hours later, and a
            # fabricated close would be indistinguishable from a real one forever.
            close_pending = True
            board = {"revision": REVISION_INTRADAY, "close_coverage_pct": close_cov,
                     "close_pending": True, "observed_n": close_n,
                     "armed_n": armed_n, "rows": rows,
                     "observability": dict(sorted(close_reasons.items())),
                     "past_deadline": now >= cn_clock.post_close_deadline(now),
                     "first_close_board_at": None}

    art: dict[str, Any] = {
        "schema": SCHEMA,
        "session": session,
        "built_at": _iso(now),
        "market_phase": phase,
        "pack_as_of": pack_as_of,
        "revision": revision,
        "close_pending": close_pending,
        "quote_source": quote_source,
        "delay_floor_min": delay_min,
        "coverage": {
            # ``armed_n`` here is the EVALUABLE set — pack entries the probe actually
            # swept — because that is the denominator ``observable_n`` is measured
            # against. The pack's own armed-with-a-threshold count rides in
            # ``liveness.candidate_n``, and the two are deliberately not merged.
            "universe_n": int(((pack.get("meta") or {}).get("universe_n")) or 0),
            "armed_n": armed_n,
            "observable_n": observable_n,
            "coverage_pct": coverage_pct,
        },
        "repaint_disclosure": {"t2_repaint_pct": T2_REPAINT_PCT},
        "names": names,
        "close_board": board,
        "liveness": _liveness(
            now=now, phase=phase, session=session, source=quote_source,
            source_asof=quote_asof,
            universe_n=int(((pack.get("meta") or {}).get("universe_n")) or 0),
            observable_n=observable_n,
            candidate_n=int(((pack.get("meta") or {}).get("armed_n")) or 0),
            coverage_pct=coverage_pct,
            ages_sec=[a * 60.0 for a in ages.values() if a is not None],
            started_at=_iso(started_at) if started_at else None,
            close_observed_at=close_observed_at,
            first_close_board_at=first_close_board_at,
            revision=revision),
        "dark": None,
        "events": events,
        "meta": {
            # Diagnostics, not product. Kept in their own block so the §6 top level
            # stays exactly the contract the client reads.
            "expected_session": expected,
            "pack_built_at": pack.get("built_at"),
            "carried_from_session": carried_from,
            "frozen_pass": frozen_pass,
            "quotes_n": len(quotes),
            "evaluated_n": armed_n,
            "states": state_counts,
            "market_status_counts": status_counts,
            "dark_counts": dark_counts,
            "unprobed": unprobed,
            "unprobed_n": sum(unprobed.values()),
            "events_n": len(events),
            "quote_max_age_min": max_age,
            "price_adjustment": {
                "levels": pack_adjustment,
                "quote": LIVE_QUOTE_ADJUSTMENT,
                "tol_pct": audit["tol_pct"],
                "checked_n": audit["checked_n"],
                "unchecked_n": audit["unchecked_n"],
                "mismatched_n": len(audit["mismatched"]),
                "mismatched": audit["mismatched"],
            },
        },
    }
    if prev_states and frozen_pass:
        # A frozen pass republishes its inputs' provenance so a reader can see the
        # states are carried, not re-measured.
        art["meta"]["frozen_from_n"] = len(prev_states)
    return art
