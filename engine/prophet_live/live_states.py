"""engine.prophet_live.live_states — the */5 intraday state machine (P0 D3, pure).

Stdlib only: no pandas, no network, no filesystem. The evaluator script owns every
side effect (quote load, R2 get/put); this module owns the decisions, so the whole
state machine is drivable from a test with three dicts.

WHAT IT DECIDES. Given tonight's armed pack, a delayed quote view and the previous
pass's artifact, each name gets one PUBLIC state:

    dormant   no provisional close in the armed band is buyable
    near      inside the band, live price below the trigger (or one unconfirmed
              pass above it — see the debounce note)
    forming   the gate is satisfied at the live price
    faded     it was forming today and the price has fallen through the buffer
    at_risk   a name that IS on tonight's board has traded to where tonight's
              verdict would flip — down through its fade level, or up past the
              point the not-topped veto bites
    dark      nothing honest can be said (no quote, stale quote, irregular gate)

Names the pack never probed are not in ``states`` at all: the budget or the data
stopped us, the tape cannot settle it, and ~1.2k identical dark rows would say
nothing that ``meta.unprobed`` does not. The pack remains the per-name census.

plus the flag ``confirming_into_close`` from ``confirm_window_start`` ET onward
while conditions still hold — close-dependence shrinks as the session ends, so
that is the strongest honest moment the lane has.

DEBOUNCE (G0.5, CSP-R2 — a 1-tick state flip is a killed class). A cross needs
``debounce_passes`` CONSECUTIVE passes above the trigger. One pass is
``crossing_unconfirmed``: an INTERNAL marker, carried in ``internal`` and in the
event spool for measurement, never the public ``state``. Falling through
``trigger * (1 - fade_buffer_pct/100)`` fades the name and resets the counter, so a
re-cross pays the full two passes again.

VOCABULARY IS LOAD-BEARING (G0.6 + operator 2026-07-27). Nothing here says fired,
confirmed, refuted or validated. The nightly build is the only thing that confirms,
and falsifier language is never front-facing.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from engine.prophet_live.interval import interval_contains, lower_edge

log = logging.getLogger(__name__)

SCHEMA = "prophet_live.states/v1"

#: The only states a payload may carry. No "fired"/"confirmed"/"refuted" anywhere.
PUBLIC_STATES: tuple[str, ...] = ("dormant", "near", "forming", "faded", "at_risk", "dark")

#: Internal marker for a single unconfirmed pass above the trigger. NOT a state.
CROSSING_UNCONFIRMED = "crossing_unconfirmed"

#: Transitions worth spooling. dormant/near/dark churn is not an event — it would
#: bury the product transitions under ~1.7k rows on the first pass of every day.
EVENT_KINDS: tuple[str, ...] = ("crossing_unconfirmed", "forming", "faded", "at_risk",
                                "confirming_into_close")

try:
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    _ET: ZoneInfo | None = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - tzdata missing
    _ET = None

#: Fallback offset when tzdata is missing, matching hot_tape's choice: EDT, so a
#: host without tzdata keeps the behaviour of the window we shipped rather than
#: sliding it an hour.
_ET_FALLBACK_HOURS = 4

_DEFAULTS: dict[str, Any] = {
    # ET, never UTC — a UTC-pinned window is an hour wrong for half the year.
    # 09:25 catches the pre-open pass; 16:15 records the close-side state.
    "window_et": {"start": "09:25", "end": "16:15"},
    # GitHub cron is best-effort and regularly lands minutes late; grace on the END
    # only, so the last pass of the day is not silently dropped.
    "window_grace_min": 10,
    "debounce_passes": 2,
    # Percent below the trigger a forming name must fall to FADE. Hysteresis, so a
    # price oscillating on the threshold does not flap the public state.
    "fade_buffer_pct": 0.5,
    "confirm_window_start": "15:30",
    # Hot-tape convention: a quote older than this cannot describe the current tape.
    "quote_max_age_min": 12,
}


def live_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve the evaluator config: ``config.yml prophet_live`` over in-code defaults."""
    out: dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v)
                           for k, v in _DEFAULTS.items()}
    try:
        block = (cfg or {}).get("prophet_live") or {}
        for k, dv in _DEFAULTS.items():
            if k not in block:
                continue
            if isinstance(dv, dict):
                out[k] = {**dv, **(block[k] or {})}
            else:
                out[k] = type(dv)(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("live_states: bad prophet_live config (%s) — using defaults", exc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Clock
# ─────────────────────────────────────────────────────────────────────────────

def _utc(now: datetime | None) -> datetime:
    t = now or datetime.now(timezone.utc)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def et_clock(now: datetime | None) -> datetime:
    """``now`` on the US-Eastern wall clock (UTC-4 fallback without tzdata)."""
    t = _utc(now)
    if _ET is not None:
        return t.astimezone(_ET)
    return t - timedelta(hours=_ET_FALLBACK_HOURS)


def _parse_hhmm(raw: Any, default: time) -> time:
    try:
        h, m = str(raw).strip().split(":")[:2]
        return time(int(h), int(m))
    except Exception:  # noqa: BLE001
        return default


def _mins(t: datetime | time) -> float:
    return t.hour * 60.0 + t.minute + getattr(t, "second", 0) / 60.0


def in_window(now: datetime | None, cfg: dict[str, Any] | None = None) -> bool:
    """True on an ET weekday inside ``window_et`` [start, end + grace]."""
    c = cfg if cfg is not None else live_cfg(None)
    try:
        t = et_clock(now)
        if t.weekday() >= 5:
            return False
        w = c.get("window_et") or {}
        start = _parse_hhmm(w.get("start"), time(9, 25))
        end = _parse_hhmm(w.get("end"), time(16, 15))
        try:
            grace = float(c.get("window_grace_min", 10))
        except (TypeError, ValueError):
            grace = 10.0
        return _mins(start) <= _mins(t) <= _mins(end) + max(0.0, grace)
    except Exception as exc:  # noqa: BLE001
        log.warning("live_states.in_window failed: %s", exc)
        return False


def session_et(now: datetime | None) -> str:
    """The ET calendar date of this pass — the key that resets the day's debounce."""
    return et_clock(now).date().isoformat()


def last_completed_session(now: datetime | None = None) -> str:
    """The most recent COMPLETED US session date, ET-aware.

    Delegates to ``lib.nyse_calendar.expected_last_session`` (pure rule arithmetic,
    stdlib, holiday-aware) — the pack's ``as_of`` must equal this or the whole
    artifact ships dark. During RTH that is the PRIOR session, which is exactly the
    bar tonight's pack was armed on.
    """
    try:
        from lib.nyse_calendar import expected_last_session  # noqa: PLC0415
        return expected_last_session(_utc(now)).isoformat()
    except Exception as exc:  # noqa: BLE001
        log.warning("live_states: nyse calendar unavailable (%s) — weekday fallback", exc)
        d = et_clock(now).date()
        d = d - timedelta(days=1)
        while d.weekday() >= 5:
            d = d - timedelta(days=1)
        return d.isoformat()


def _iso(now: datetime) -> str:
    return _utc(now).isoformat(timespec="seconds").replace("+00:00", "Z")


# ─────────────────────────────────────────────────────────────────────────────
# Per-name decision
# ─────────────────────────────────────────────────────────────────────────────

def _dark(reason: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"state": "dark", "reason": reason}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def name_state(entry: dict[str, Any], *, price: float | None, quote_age_min: float | None,
               prev: dict[str, Any] | None, now: datetime, cfg: dict[str, Any]) -> dict[str, Any]:
    """One name's state this pass. Never raises; unknowns become ``dark`` with a reason."""
    prev = prev or {}
    try:
        if not entry.get("probed"):
            return _dark(str(entry.get("skip") or "not_probed"))
        if entry.get("state") == "irregular":
            return _dark("irregular_gate")
        if price is None:
            return _dark("no_quote")
        max_age = float(cfg.get("quote_max_age_min", 12))
        if quote_age_min is None or float(quote_age_min) > max_age:
            return _dark("stale_quote", quote_age_min=(round(float(quote_age_min), 1)
                                                       if quote_age_min is not None else None))

        px = float(price)
        holds = interval_contains(entry, px)
        if holds is None:
            return _dark("no_interval")

        lo = lower_edge(entry)
        on_board = bool(entry.get("center_buyable"))
        need = max(1, int(cfg.get("debounce_passes", 2)))
        buf = float(cfg.get("fade_buffer_pct", 0.5)) / 100.0
        prev_state = str(prev.get("state") or "")
        prev_passes = int(prev.get("passes") or 0)

        out: dict[str, Any] = {"price": round(px, 4), "quote_age_min": round(float(quote_age_min), 1)}

        if on_board:
            # Already admitted at last night's close, so there is no cross to
            # debounce: the question is only whether the live price still keeps the
            # gate satisfied. Below the fade level the board pick would lose its
            # freshness at tonight's close — surfaced quietly, never as a sell call.
            out["entered"] = "board"
            out["passes"] = None
            out["state"] = "forming" if holds else "at_risk"
        elif not entry.get("buyable_in_band"):
            out["state"] = "dormant"
            out["passes"] = 0
        elif lo is None:
            out["state"] = "dormant"
            out["passes"] = 0
        elif holds:
            # The whole interval, not just the trigger: a price ABOVE fade_hi_px has
            # run past where the gate still accepts the name (the not-topped veto),
            # so it is emphatically not a cross. Keying the debounce off `px >= lo`
            # alone promoted a runaway to forming on its second pass.
            passes = prev_passes + 1
            out["passes"] = passes
            out["entered"] = "cross"
            if passes >= need:
                out["state"] = "forming"
            else:
                # One pass inside the interval is NOT a public state (G0.5).
                out["state"] = "near"
                out["internal"] = CROSSING_UNCONFIRMED
        elif prev_state == "forming" and lo * (1.0 - buf) <= px < lo:
            # Inside the hysteresis band just below the trigger: still forming,
            # counter preserved, so a price sitting on the threshold cannot flap.
            out["state"] = "forming"
            out["passes"] = prev_passes
            out["entered"] = prev.get("entered") or "cross"
        elif prev_state in ("forming", "faded"):
            out["state"] = "faded"
            out["passes"] = 0
        else:
            out["state"] = "near"
            out["passes"] = 0

        if _mins(et_clock(now)) >= _mins(_parse_hhmm(cfg.get("confirm_window_start"),
                                                    time(15, 30))) and holds:
            out["confirming_into_close"] = True
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("live_states.name_state failed: %s", exc)
        return _dark(f"eval_error: {exc}")


def transitions(ticker: str, new: dict[str, Any], prev: dict[str, Any] | None, *,
                now: datetime) -> list[dict[str, Any]]:
    """The event rows this name earns this pass (only :data:`EVENT_KINDS`)."""
    prev = prev or {}
    rows: list[dict[str, Any]] = []
    base = {
        "ticker": ticker,
        "ts": _iso(now),
        "price": new.get("price"),
        "quote_age_min": new.get("quote_age_min"),
        "passes": new.get("passes"),
        "from": prev.get("state") or None,
    }
    if new.get("state") != prev.get("state") and new.get("state") in EVENT_KINDS:
        rows.append({**base, "kind": new["state"]})
    if new.get("internal") == CROSSING_UNCONFIRMED and prev.get("internal") != CROSSING_UNCONFIRMED:
        rows.append({**base, "kind": CROSSING_UNCONFIRMED})
    if new.get("confirming_into_close") and not prev.get("confirming_into_close"):
        rows.append({**base, "kind": "confirming_into_close"})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Whole pass
# ─────────────────────────────────────────────────────────────────────────────

def dark_artifact(reason: str, *, now: datetime, cfg: dict[str, Any],
                  pack_as_of: str | None = None, detail: str | None = None) -> dict[str, Any]:
    """A whole-artifact dark payload. No states — a guessed state is the failure."""
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "dark",
        "reason": reason,
        "states": {},
        "meta": {
            "pass_ts": _iso(now),
            "session_et": session_et(now),
            "pack_as_of": pack_as_of,
            "expected_session": last_completed_session(now),
            "dark_counts": {reason: 1},
        },
    }
    if detail:
        out["meta"]["detail"] = detail
    return out


def evaluate(pack: dict[str, Any] | None, quotes: dict[str, Any], prev: dict[str, Any] | None,
             *, now: datetime, cfg: dict[str, Any],
             quote_asof: str | None = None, delay_min: int | None = None,
             quote_age_of=None) -> dict[str, Any]:
    """One evaluator pass.

    ``quotes`` is ``load_live_quotes()["quotes"]`` — ``{ticker: {price, ts_ms, …}}``.
    ``quote_age_of(quote)`` returns that quote's age in minutes (the caller owns it
    so this module stays clock-and-I/O free beyond ``now``).

    HARD STALENESS GATE: ``pack.as_of`` must equal the last completed session, else
    the WHOLE artifact ships dark. Evaluating yesterday's triggers against today's
    tape is the one failure this lane must never have (masterplan §7).
    """
    if not pack or not isinstance(pack.get("names"), dict):
        return dark_artifact("no_pack", now=now, cfg=cfg)
    pack_as_of = str(pack.get("as_of") or "")
    expected = last_completed_session(now)
    if pack_as_of != expected:
        return dark_artifact("stale_pack", now=now, cfg=cfg, pack_as_of=pack_as_of,
                             detail=f"pack as_of={pack_as_of or 'none'} != last completed session {expected}")

    sess = session_et(now)
    prev_states: dict[str, Any] = {}
    if isinstance(prev, dict) and ((prev.get("meta") or {}).get("session_et") == sess):
        prev_states = prev.get("states") or {}

    states: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    dark_counts: dict[str, int] = {}
    counts: dict[str, int] = {}
    unprobed: dict[str, int] = {}
    for tkr, entry in (pack.get("names") or {}).items():
        if not entry.get("probed"):
            # The pack could not sweep this name — a budget cut or a data problem, not
            # anything the tape can settle. It is counted by reason in meta.unprobed
            # and left OUT of `states`, so `states` means "names this pass can actually
            # speak about". Carrying ~1.2k identical dark rows instead would triple the
            # artifact and say nothing the count does not; the PACK is the per-name
            # census and keeps every skip reason.
            r = str(entry.get("skip") or "not_probed")
            unprobed[r] = unprobed.get(r, 0) + 1
            continue
        q = quotes.get(tkr) or {}
        px = q.get("price")
        age = quote_age_of(q) if (quote_age_of and q) else None
        st = name_state(entry, price=px, quote_age_min=age,
                        prev=prev_states.get(tkr), now=now, cfg=cfg)
        states[tkr] = st
        counts[st["state"]] = counts.get(st["state"], 0) + 1
        if st["state"] == "dark":
            r = str(st.get("reason") or "unknown")
            dark_counts[r] = dark_counts.get(r, 0) + 1
        events.extend(transitions(tkr, st, prev_states.get(tkr), now=now))

    return {
        "schema": SCHEMA,
        "status": "live",
        "states": states,
        "events": events,
        "meta": {
            "pass_ts": _iso(now),
            "session_et": sess,
            "quote_asof": quote_asof,
            # House convention: the VENDOR delay floor, not a measured latency. The
            # per-name measured age rides on each state as quote_age_min.
            "delay_min": delay_min,
            "pack_as_of": pack_as_of,
            "pack_built_at": pack.get("built_at"),
            "expected_session": expected,
            "quotes_n": len(quotes),
            "evaluated_n": len(states),
            "states": counts,
            "dark_counts": dark_counts,
            # Coverage, per pass and per reason: what the pack never armed. A consumer
            # that reads evaluated_n as the universe is claiming coverage it has not got.
            "unprobed": unprobed,
            "unprobed_n": sum(unprobed.values()),
            "events_n": len(events),
        },
    }
