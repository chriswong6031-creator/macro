"""engine.prophet_live.cn_states — the CN evaluator state machine (CN-PR-1, spec §5).

Stdlib + :mod:`engine.prophet_live.live_states` + :mod:`engine.prophet_live.cn_clock`.
No pandas, no network, no filesystem. The driver owns I/O; this module owns the
decisions so the replay battery can drive the whole pass with three dicts.

PUBLIC STATES are the US set, unchanged: dormant / near / forming / faded /
at_risk / unknown / dark. The CN overlay is ``market_status`` (orthogonal):
trading | session_break | limit_up_locked | limit_down_locked | unavailable |
suspended_suspected.

FREEZE PHASES (spec §2): pre_open, session_break, closing_auction — a pass may
RUN but public states do not transition. Price / age / market_status refresh;
debounce counters ride through intact.

CLOSE PASS (spec §5): in ``post_close``, a name is close-observed when its quote
is stamped at/after 15:00 CST with basis ∈ {regular, day}, or the price is
stable across two post-close passes. First pass that clears 80% of the ARMED
set publishes ``close_board`` and stamps ``first_close_board_at``. Below the
floor by 15:15 CST: publish what is observable with ``close_pending: true``.
Never manufacture a close.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from engine.prophet_live import cn_clock
from engine.prophet_live import live_states as LS
from engine.prophet_live.interval import (
    DEFAULT_PACK_ADJUSTMENT,
    LIVE_QUOTE_ADJUSTMENT,
    basis_audit,
)

log = logging.getLogger(__name__)

SCHEMA = "cn_prophet_live.states/v1"
MARKET = "CN"

CLOSE_COVERAGE_FLOOR = 0.80
CLOSE_BASES = frozenset({"regular", "day"})
SUSPENDED_TOKENS = frozenset({"suspended", "halt", "halted", "delisted"})

#: Presentation overlay, orthogonal to the public state machine (spec §2).
MARKET_STATUSES: tuple[str, ...] = (
    "trading", "session_break", "limit_up_locked", "limit_down_locked",
    "unavailable", "suspended_suspected",
)


def _utc(now: datetime | None) -> datetime:
    t = now or datetime.now(timezone.utc)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _iso(now: datetime) -> str:
    return _utc(now).isoformat(timespec="seconds").replace("+00:00", "Z")


def _quote_ts(quote: dict[str, Any] | None) -> datetime | None:
    if not isinstance(quote, dict):
        return None
    raw = quote.get("quote_ts") or quote.get("ts")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    ms = quote.get("ts_ms") or quote.get("quote_ts_ms")
    try:
        if ms is not None:
            return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return None


def _prev_close(quote: dict[str, Any] | None) -> float | None:
    if not isinstance(quote, dict):
        return None
    for k in ("prev_close", "previous_close", "prevClose"):
        try:
            v = float(quote[k])
        except (KeyError, TypeError, ValueError):
            continue
        if v > 0:
            return v
    return None


def market_status(ticker: Any, quote: dict[str, Any] | None, *,
                  phase: str, quote_age_min: float | None,
                  max_age_min: float) -> str:
    """Per-name presentation overlay (spec §2). Never a state-machine input."""
    if not quote or quote.get("price") is None:
        return "unavailable"
    token = str(quote.get("market_status") or quote.get("status") or "").strip().lower()
    if token in SUSPENDED_TOKENS:
        return "suspended_suspected"
    if quote_age_min is None or float(quote_age_min) > float(max_age_min):
        return "unavailable"
    lock = cn_clock.limit_lock_status(
        quote.get("price"), _prev_close(quote), cn_clock.limit_pct_for(ticker),
    )
    if lock:
        return lock
    if phase == "session_break":
        return "session_break"
    return "trading"


def close_observed(quote: dict[str, Any] | None, *, now: datetime,
                   prev: dict[str, Any] | None = None) -> bool:
    """True when this name has a lawful close print (spec §5)."""
    if not quote or quote.get("price") is None:
        return False
    ts = _quote_ts(quote)
    floor = cn_clock.session_close_utc(now)
    if ts is not None and ts >= floor:
        basis = str(quote.get("price_basis") or quote.get("basis") or "").lower()
        if basis in CLOSE_BASES:
            return True
    # Two-pass stable after 15:00 CST: same fen, both post-close.
    if prev and ts is not None and ts >= floor:
        try:
            a = round(float(quote["price"]), 2)
            b = round(float(prev.get("price")), 2)
        except (TypeError, ValueError):
            return False
        return a == b and a > 0
    return False


def _freeze_row(prev: dict[str, Any] | None, *, price: Any,
                quote_age_min: float | None, status: str,
                quote_ts: datetime | None) -> dict[str, Any]:
    """Refresh tape fields; keep the public state and debounce counters."""
    row = dict(prev or {"state": "dormant"})
    if price is not None:
        try:
            row["price"] = round(float(price), 4)
        except (TypeError, ValueError):
            pass
    if quote_age_min is not None:
        row["quote_age_min"] = round(float(quote_age_min), 1)
        row["quote_age_sec"] = int(round(float(quote_age_min) * 60.0))
    if quote_ts is not None:
        row["quote_ts"] = _iso(quote_ts)
    row["market_status"] = status
    return row


def dark_artifact(reason: str, *, now: datetime, cfg: dict[str, Any],
                  pack_as_of: str | None = None, detail: str | None = None,
                  quote_asof: str | None = None, delay_min: float | None = None,
                  carry: dict[str, Any] | None = None) -> dict[str, Any]:
    ph = cn_clock.phase(now)
    sess = cn_clock.session_date(now).isoformat()
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "market": MARKET,
        "status": "dark",
        "reason": reason,
        "session": sess,
        "built_at": _iso(now),
        "market_phase": ph,
        "revision": "intraday_provisional",
        "close_pending": False,
        "names": {},
        "close_board": None,
        "dark": {"reason": reason},
        "liveness": {
            "expected_session": cn_clock.last_completed_session(now),
            "market_phase": ph,
            "failure_stage": reason,
            "failure_reason": detail or reason,
        },
        "meta": {
            "pass_ts": _iso(now),
            "session": sess,
            "market_phase": ph,
            "pack_as_of": pack_as_of,
            "expected_session": cn_clock.last_completed_session(now),
            "quote_asof": quote_asof,
            "delay_min": delay_min,
            "dark_counts": {reason: 1},
            "unknown_counts": {},
        },
    }
    if detail:
        out["meta"]["detail"] = detail
    if carry:
        out["prev_states"] = carry
    return out


def _armed_names(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for tkr, entry in (pack.get("names") or {}).items():
        if entry.get("probed") and (
                entry.get("trigger_px") is not None or entry.get("fade_px") is not None
                or entry.get("buyable_in_band")):
            out[tkr] = entry
    return out


def assemble_close_board(names: dict[str, dict[str, Any]],
                         pack: dict[str, Any],
                         observed: set[str],
                         *, now: datetime, coverage_pct: float,
                         pending: bool) -> dict[str, Any]:
    """Frozen nightly lanes restated at close states + armed crosses that are forming."""
    lanes: dict[str, list[dict[str, Any]]] = {
        "featured": [], "more_actionable": [], "forming": [], "cross": [],
    }
    for tkr, st in names.items():
        if tkr not in observed:
            continue
        entry = (pack.get("names") or {}).get(tkr) or {}
        frozen = entry.get("frozen") or {}
        lane = str(frozen.get("lane") or ("cross" if not entry.get("center_buyable")
                                          else "forming"))
        row = {
            "ticker": tkr,
            "state": st.get("state"),
            "market_status": st.get("market_status"),
            "price": st.get("price"),
            "frozen": frozen,
            "revision": "close_provisional",
        }
        if lane in lanes:
            lanes[lane].append(row)
        elif st.get("state") in {"forming", "at_risk"} and not entry.get("center_buyable"):
            lanes["cross"].append(row)
        else:
            lanes.setdefault(lane, []).append(row)
    return {
        "revision": "close_provisional",
        "first_close_board_at": None if pending else _iso(now),
        "close_coverage_pct": round(float(coverage_pct), 1),
        "close_pending": bool(pending),
        "lanes": {k: v for k, v in lanes.items() if v},
    }


def evaluate(pack: dict[str, Any] | None, quotes: dict[str, Any],
             prev: dict[str, Any] | None, *, now: datetime, cfg: dict[str, Any],
             quote_asof: str | None = None, delay_min: float | None = None,
             quote_age_of: Callable[[dict], float | None] | None = None) -> dict[str, Any]:
    """One CN evaluator pass. ``cfg`` is :func:`live_states.live_cfg` output."""
    ts = _utc(now)
    ph = cn_clock.phase(ts)
    sess = cn_clock.session_date(ts).isoformat()
    expected = cn_clock.last_completed_session(ts)
    max_age = float(cfg.get("quote_max_age_min") or LS._FALLBACK_MAX_AGE_MIN)  # noqa: SLF001
    delay = float(delay_min or 0.0)

    prev_states: dict[str, Any] = {}
    if isinstance(prev, dict) and str((prev.get("session") or
                                       (prev.get("meta") or {}).get("session"))) == sess:
        prev_states = prev.get("names") or prev.get("states") or prev.get("prev_states") or {}
    dark_kw = {"quote_asof": quote_asof, "delay_min": delay_min, "carry": prev_states}

    if not pack or not isinstance(pack.get("names"), dict):
        return dark_artifact("no_pack", now=ts, cfg=cfg, **dark_kw)
    pack_as_of = str(pack.get("as_of") or "")
    if pack_as_of != expected:
        return dark_artifact(
            "stale_pack", now=ts, cfg=cfg, pack_as_of=pack_as_of, **dark_kw,
            detail=f"pack as_of={pack_as_of or 'none'} != last completed session {expected}")

    audit = basis_audit(pack.get("names") or {}, quotes,
                        tol_pct=cfg.get("basis_tolerance_pct", 0.25))
    gaps = audit["gaps"]
    pack_adjustment = pack.get("price_adjustment") or DEFAULT_PACK_ADJUSTMENT

    freeze = ph in cn_clock.FREEZE_PHASES
    names: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    dark_counts: dict[str, int] = {}
    unknown_counts: dict[str, int] = {}
    counts: dict[str, int] = {}
    unprobed: dict[str, int] = {}
    observed: set[str] = set()

    for tkr, entry in (pack.get("names") or {}).items():
        if not entry.get("probed"):
            r = str(entry.get("skip") or "not_probed")
            unprobed[r] = unprobed.get(r, 0) + 1
            continue
        q = quotes.get(tkr) or {}
        px = q.get("price")
        qts = _quote_ts(q)
        if quote_age_of and q:
            age = quote_age_of(q)
        else:
            age = cn_clock.quote_age_min(qts, ts, delay_floor_min=delay)
        status = market_status(tkr, q if q else None, phase=ph,
                               quote_age_min=age, max_age_min=max_age)
        prev_row = prev_states.get(tkr)

        if freeze and prev_row and prev_row.get("state") not in (None, "dark", "unknown"):
            st = _freeze_row(prev_row, price=px, quote_age_min=age,
                             status=status, quote_ts=qts)
        else:
            st = LS.name_state(entry, price=px, quote_age_min=age,
                               prev=prev_row, now=ts, cfg=cfg,
                               basis_gap_pct=gaps.get(tkr))
            st["market_status"] = status
            if qts is not None:
                st["quote_ts"] = _iso(qts)
            if age is not None:
                st["quote_age_sec"] = int(round(float(age) * 60.0))
            if not freeze:
                events.extend(LS.transitions(tkr, st, prev_row, now=ts))

        frozen = entry.get("frozen")
        if frozen:
            st["frozen"] = frozen
        st["prev_close_feed"] = _prev_close(q)
        st["as_of_close_pack"] = entry.get("as_of_close")
        names[tkr] = st
        counts[st.get("state") or "dark"] = counts.get(st.get("state") or "dark", 0) + 1
        if st.get("state") == "dark":
            r = str(st.get("reason") or "unknown")
            dark_counts[r] = dark_counts.get(r, 0) + 1
        elif st.get("state") == "unknown":
            r = str(st.get("reason") or "unspecified")
            unknown_counts[r] = unknown_counts.get(r, 0) + 1
        if ph == "post_close" and close_observed(q, now=ts, prev=prev_row):
            observed.add(tkr)

    armed = _armed_names(pack)
    armed_n = len(armed) or sum(1 for e in (pack.get("names") or {}).values()
                                if e.get("probed"))
    observable_n = sum(1 for s in names.values()
                       if s.get("state") not in LS.NO_VERDICT_STATES)
    coverage_pct = (100.0 * observable_n / armed_n) if armed_n else 0.0

    close_board = None
    close_pending = False
    first_close_at = None
    if ph == "post_close" and armed_n:
        close_cov = (100.0 * len(observed) / armed_n) if armed_n else 0.0
        pending = (len(observed) / armed_n) < CLOSE_COVERAGE_FLOOR
        # post_close is [15:00, 15:15); the honesty deadline IS 15:15, so the last
        # lawful ticks are the minute before. Publish the observable remnant then
        # rather than waiting for an instant the phase has already left.
        at_deadline = ts + timedelta(minutes=1) >= cn_clock.post_close_deadline(ts)
        if pending and at_deadline:
            close_pending = True
            close_board = assemble_close_board(
                names, pack, observed, now=ts, coverage_pct=close_cov, pending=True)
        elif not pending:
            close_board = assemble_close_board(
                names, pack, observed, now=ts, coverage_pct=close_cov, pending=False)
            first_close_at = close_board["first_close_board_at"]
        else:
            close_pending = True

    if isinstance(prev, dict) and prev.get("close_board") and not close_board:
        # Later post-close ticks keep a previously published board (revise upward).
        close_board = prev.get("close_board")
        first_close_at = (close_board or {}).get("first_close_board_at") or (
            (prev.get("liveness") or {}).get("first_close_board_at"))

    revision = "close_provisional" if (close_board and not close_pending) else "intraday_provisional"
    return {
        "schema": SCHEMA,
        "market": MARKET,
        "status": "live",
        "session": sess,
        "built_at": _iso(ts),
        "market_phase": ph,
        "pack_as_of": pack_as_of,
        "revision": revision,
        "close_pending": close_pending,
        "quote_source": None,
        "delay_floor_min": delay,
        "coverage": {
            "universe_n": int((pack.get("meta") or {}).get("universe_n") or len(pack.get("names") or {})),
            "armed_n": armed_n,
            "observable_n": observable_n,
            "coverage_pct": round(coverage_pct, 1),
        },
        "repaint_disclosure": (pack.get("meta") or {}).get("repaint_disclosure")
        or {"t2_repaint_pct": 15.1},
        "names": names,
        "close_board": close_board,
        "events": events,
        "dark": None,
        "liveness": {
            "expected_session": expected,
            "market_phase": ph,
            "source": None,
            "source_asof": quote_asof,
            "quote_age_sec_p50": _p50_age_sec(names),
            "universe_n": int((pack.get("meta") or {}).get("universe_n") or 0),
            "observable_n": observable_n,
            "candidate_n": counts.get("forming", 0) + counts.get("near", 0),
            "coverage_pct": round(coverage_pct, 1),
            "evaluation_started_at": _iso(ts),
            "artifact_written_at": None,
            "close_observed_at": _iso(ts) if observed else None,
            "first_close_board_at": first_close_at,
            "provisional_revision": revision,
            "canonical_revision": None,
            "confirmation_status": None,
            "failure_stage": None,
            "failure_reason": None,
        },
        "meta": {
            "pass_ts": _iso(ts),
            "session": sess,
            "market_phase": ph,
            "quote_asof": quote_asof,
            "delay_min": delay_min,
            "pack_as_of": pack_as_of,
            "pack_built_at": pack.get("built_at"),
            "expected_session": expected,
            "quotes_n": len(quotes),
            "evaluated_n": len(names),
            "states": counts,
            "dark_counts": dark_counts,
            "unknown_counts": unknown_counts,
            "unprobed": unprobed,
            "unprobed_n": sum(unprobed.values()),
            "events_n": len(events),
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


def _p50_age_sec(names: dict[str, dict[str, Any]]) -> float | None:
    ages = [float(s["quote_age_sec"]) for s in names.values()
            if s.get("quote_age_sec") is not None]
    if not ages:
        return None
    ages.sort()
    return ages[len(ages) // 2]
