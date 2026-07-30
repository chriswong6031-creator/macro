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

DEBOUNCE (G0.5, CSP-R2 — a 1-tick state flip is a killed class), on BOTH paths.
A cross needs ``debounce_passes`` CONSECUTIVE passes inside the interval. One pass
is ``crossing_unconfirmed``: an INTERNAL marker, carried in ``internal`` and in the
event spool for measurement, never the public ``state``. Falling through
``trigger * (1 - fade_buffer_pct/100)`` fades the name and resets the counter, so a
re-cross pays the full two passes again.

The BOARD path is debounced the same way, symmetrically. It was not, and a board
name whose price straddled its fade level by four cents (90.02 / 89.98 on a 90.00
level) flipped forming↔at_risk on every pass — the exact killed class, on the path
where the name is already on a published board. Now a breach that does not clear
the buffer needs ``debounce_passes`` consecutive failing passes to publish
``at_risk``, and recovery needs the same going back; a move that clears the buffer
is decisive immediately in either direction.

VOCABULARY IS LOAD-BEARING (G0.6 + operator 2026-07-27). Nothing here says fired,
confirmed, refuted or validated. The nightly build is the only thing that confirms,
and falsifier language is never front-facing.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any

from engine.prophet_live.interval import in_probed_band, interval_contains, lower_edge

log = logging.getLogger(__name__)

SCHEMA = "prophet_live.states/v1"

#: The only states a payload may carry. No "fired"/"confirmed"/"refuted" anywhere.
PUBLIC_STATES: tuple[str, ...] = ("dormant", "near", "forming", "faded", "at_risk", "dark")

#: Internal markers for a single un-debounced pass. NONE of these is a state; they
#: ride in ``internal`` and in the spool so the debounce itself is measurable.
CROSSING_UNCONFIRMED = "crossing_unconfirmed"
AT_RISK_UNCONFIRMED = "at_risk_unconfirmed"
RECOVERY_UNCONFIRMED = "recovery_unconfirmed"

#: Which side of the buyable range a breach happened on. A drop means the name came
#: back toward the entry; an overrun means it ran past where the gate still admits it.
VIA_DROP = "drop"
VIA_OVERRUN = "overrun"


def _breach_side(px: float, lo: float | None, hi: float | None) -> str:
    """``drop`` when the price fell below the range, ``overrun`` when it ran above it."""
    if hi is not None and px > float(hi):
        return VIA_OVERRUN
    return VIA_DROP


def _inward_clear(px: float, lo: float | None, hi: float | None, buf: float) -> bool:
    """True when the price is comfortably back INSIDE the range, past the buffer.

    The symmetric partner of the outward buffer: a decisive move back in resolves an
    ``at_risk`` immediately, while a marginal one still pays the debounce.
    """
    if lo is not None and px < float(lo) * (1.0 + buf):
        return False
    if hi is not None and px > float(hi) * (1.0 - buf):
        return False
    return True

#: Transitions worth spooling. dormant/near/dark churn is not an event — it would
#: bury the product transitions under ~1.7k rows on the first pass of every day.
#: The three internal markers ride here too: measuring whether the debounce earns
#: its keep is a P0 goal, and that needs the passes it suppressed.
EVENT_KINDS: tuple[str, ...] = ("crossing_unconfirmed", "at_risk_unconfirmed",
                                "recovery_unconfirmed", "forming", "faded", "at_risk",
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


def session_phase(now: datetime | None) -> str:
    """``preopen`` before 09:30 ET, else ``rth``.

    Stamped on every artifact and event row: a state formed at 09:27 was read off a
    pre-open print, which is a materially different claim from one at 11:00, and the
    ledger cannot separate them after the fact without this.
    """
    return "preopen" if _mins(et_clock(now)) < _mins(time(9, 30)) else "rth"


def in_window(now: datetime | None, cfg: dict[str, Any] | None = None) -> bool:
    """True on a US TRADING DAY inside ``window_et`` [start, end + grace].

    Trading day, not merely a weekday: the NYSE calendar is consulted so the lane
    stands down on Thanksgiving instead of publishing ~80 passes against a tape that
    never opened. Fail-soft — an unavailable calendar degrades to the weekday check.
    """
    c = cfg if cfg is not None else live_cfg(None)
    try:
        t = et_clock(now)
        if t.weekday() >= 5:
            return False
        try:
            from lib.nyse_calendar import is_session  # noqa: PLC0415
            if not is_session(t.date()):
                return False
        except Exception as exc:  # noqa: BLE001
            log.warning("live_states: nyse calendar unavailable (%s) — weekday only", exc)
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
        # OUTSIDE THE PROBED BAND THE PACK KNOWS NOTHING. Asked before membership,
        # because interval_contains extrapolates happily: a board name gapping -30%
        # satisfied "no fade breach, no fade_hi breach" and read forming.
        if not in_probed_band(entry, px):
            return _dark("out_of_band", price=round(px, 4),
                         quote_age_min=round(float(quote_age_min), 1))
        holds = interval_contains(entry, px)
        if holds is None:
            return _dark("no_interval")

        lo = lower_edge(entry)
        hi = entry.get("fade_hi_px")
        on_board = bool(entry.get("center_buyable"))
        need = max(1, int(cfg.get("debounce_passes", 2)))
        buf = float(cfg.get("fade_buffer_pct", 0.5)) / 100.0
        prev_state = str(prev.get("state") or "")
        prev_passes = int(prev.get("passes") or 0)
        prev_fails = int(prev.get("fails") or 0)

        def _clears_outward() -> bool:
            """The breach is decisive — past the hysteresis buffer, either side."""
            if lo is not None and px < float(lo) * (1.0 - buf):
                return True
            return hi is not None and px > float(hi) * (1.0 + buf)

        out: dict[str, Any] = {"price": round(px, 4),
                               "quote_age_min": round(float(quote_age_min), 1)}

        if on_board:
            # Already admitted at last night's close, so there is no cross to
            # debounce — but a marginal breach of the fade level is still a 1-tick
            # flip and must not flap the public state (CSP-R2). Below the fade level
            # (or above the point the not-topped veto bites) the board pick would
            # lose its freshness at tonight's close: surfaced quietly, never a sell.
            out["entered"] = "board"
            if holds:
                out["passes"] = prev_passes + 1
                out["fails"] = 0
                if prev_state == "at_risk" and not _inward_clear(px, lo, hi, buf) \
                        and out["passes"] < need:
                    out["state"] = "at_risk"
                    out["internal"] = RECOVERY_UNCONFIRMED
                else:
                    out["state"] = "forming"
            else:
                out["passes"] = 0
                out["fails"] = prev_fails + 1
                if _clears_outward() or out["fails"] >= need:
                    out["state"] = "at_risk"
                    out["via"] = _breach_side(px, lo, hi)
                else:
                    out["state"] = prev_state if prev_state in ("forming", "at_risk") else "forming"
                    out["internal"] = AT_RISK_UNCONFIRMED
        elif not entry.get("buyable_in_band") or lo is None:
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
        elif prev_state == "forming" and float(lo) * (1.0 - buf) <= px < float(lo):
            # Inside the hysteresis band just below the trigger: still forming,
            # counter preserved, so a price sitting on the threshold cannot flap.
            out["state"] = "forming"
            out["passes"] = prev_passes
            out["entered"] = prev.get("entered") or "cross"
        elif prev_state in ("forming", "faded"):
            out["state"] = "faded"
            out["passes"] = 0
            out["entered"] = prev.get("entered") or "cross"
            # WHY it stopped holding. "faded" alone said "fallen through the buffer",
            # which is false for a name that ran up THROUGH the top of its buyable
            # range — the opposite trade, and it was polluting the kind axis the
            # ledger measures. P1 display must treat the two differently: a drop is
            # "it came back to you", an overrun is "don't chase".
            out["via"] = _breach_side(px, lo, hi)
        else:
            out["state"] = "near"
            out["passes"] = 0

        # M4: only a PUBLIC forming may carry the flag. It used to fire off `holds`
        # alone, so a single unconfirmed pass at 15:31 produced a
        # confirming-into-close event for a cross the lane had not yet published.
        if out["state"] == "forming" and holds and _mins(et_clock(now)) >= _mins(
                _parse_hhmm(cfg.get("confirm_window_start"), time(15, 30))):
            out["confirming_into_close"] = True

        # Which internal markers this name has already reached today. An oscillating
        # price re-asserts a marker on every other pass, and one spool row per tick
        # would drown the very thing the markers are for — measuring how often the
        # debounce suppressed something. One row per marker per name per session.
        seen = list(prev.get("internal_seen") or [])
        if out.get("internal") and out["internal"] not in seen:
            seen.append(out["internal"])
        if seen:
            out["internal_seen"] = seen
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
        # On the ROW, not just the artifact. The reconciler reads session_phase off the
        # event, so stamping it only in meta wrote None into every ledger row forever —
        # and a 09:27 pre-open print is a materially different claim from an 11:00 one.
        "session_phase": session_phase(now),
        "price": new.get("price"),
        "quote_age_min": new.get("quote_age_min"),
        "passes": new.get("passes"),
        "from": prev.get("state") or None,
        # M5: without this the ledger cannot tell a real intraday CROSS from a board
        # member's first-pass reading. The P0 receipt was ~108 board rows to 2 crosses
        # — the headline population would have been non-crosses, silently.
        "entered": new.get("entered"),
    }
    if new.get("via"):
        base["via"] = new["via"]
    if new.get("state") != prev.get("state") and new.get("state") in EVENT_KINDS:
        rows.append({**base, "kind": new["state"]})
    seen_before = set(prev.get("internal_seen") or [])
    for marker in (CROSSING_UNCONFIRMED, AT_RISK_UNCONFIRMED, RECOVERY_UNCONFIRMED):
        if new.get("internal") == marker and marker not in seen_before:
            rows.append({**base, "kind": marker})
    if new.get("confirming_into_close") and not prev.get("confirming_into_close"):
        rows.append({**base, "kind": "confirming_into_close"})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Whole pass
# ─────────────────────────────────────────────────────────────────────────────

def dark_artifact(reason: str, *, now: datetime, cfg: dict[str, Any],
                  pack_as_of: str | None = None, detail: str | None = None,
                  quote_asof: str | None = None, delay_min: int | None = None,
                  carry: dict[str, Any] | None = None) -> dict[str, Any]:
    """A whole-artifact dark payload. No states — a guessed state is the failure.

    ``carry`` preserves the SAME SESSION's previous per-name states under
    ``prev_states``. Without it a single dark pass wiped the day's debounce: the PUT
    replaced ``states`` with ``{}``, the next pass found no predecessor, and every
    name that had already banked a confirming pass had to start over — so one stale
    quote artifact could cost the session its crosses. The dark payload still
    publishes NO state of its own; ``prev_states`` is history, explicitly labelled.
    """
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "dark",
        "reason": reason,
        "states": {},
        "meta": {
            "pass_ts": _iso(now),
            "session_et": session_et(now),
            "session_phase": session_phase(now),
            "pack_as_of": pack_as_of,
            "expected_session": last_completed_session(now),
            # Freshness travels even on a dark pass: a consumer must be able to see
            # HOW stale the tape was when we declined to speak.
            "quote_asof": quote_asof,
            "delay_min": delay_min,
            "dark_counts": {reason: 1},
        },
    }
    if detail:
        out["meta"]["detail"] = detail
    if carry:
        out["prev_states"] = carry
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
    sess = session_et(now)
    # Resolve the predecessor FIRST so a dark pass can carry it forward instead of
    # wiping the session's debounce (see dark_artifact).
    prev_states: dict[str, Any] = {}
    if isinstance(prev, dict) and ((prev.get("meta") or {}).get("session_et") == sess):
        prev_states = prev.get("states") or prev.get("prev_states") or {}
    dark_kw = {"quote_asof": quote_asof, "delay_min": delay_min, "carry": prev_states}

    if not pack or not isinstance(pack.get("names"), dict):
        return dark_artifact("no_pack", now=now, cfg=cfg, **dark_kw)
    pack_as_of = str(pack.get("as_of") or "")
    expected = last_completed_session(now)
    if pack_as_of != expected:
        return dark_artifact(
            "stale_pack", now=now, cfg=cfg, pack_as_of=pack_as_of, **dark_kw,
            detail=f"pack as_of={pack_as_of or 'none'} != last completed session {expected}")

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
            "session_phase": session_phase(now),
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
