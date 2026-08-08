"""admin.program_watch — the seasonality program watch, on the operator's console.

Reads the committed ``data/seasonality/program_watch.json`` written nightly by
``scripts/build_program_watch.py`` and serves it to the authed admin console.
No write path, no public access (RUL-8: auth wall stays; this is a GET-only reader).

Why the admin console is the right home for it: each tripwire carries an
``operator_prompt`` (a ready-to-paste session brief) plus module names, PR-shaped
instructions and ``research/`` doc paths.  That is operator vocabulary — module
paths, PR shapes, internal state words — and it belongs on the operator surface
rather than laundered into customer language on a public page.  It is NOT a
secrecy claim: the artifact is committed to a **public** repository, so the auth
wall keeps this content off the *product*, not off the internet.  Nothing that is
genuinely private (credentials, customer data) may be put into the artifact on the
strength of this panel being authed.

Failure discipline is ``key_alerts.panel``'s: **never raises**.  Every failure mode
is a returned state with a plain-words ``note`` — an unread watch must never render
as a quiet one:

  * file absent            → available=False, note says the nightly has not run;
  * unparseable JSON       → available=False, note names the parse failure;
  * unexpected ``schema``  → available=False, note refuses rather than rendering
                             fields this console does not understand;
  * oversized file         → available=False, note names the size (the ``_MAX_*``
                             guard idiom in ``admin.alerts``).

Two clocks, deliberately kept apart (they are NOT interchangeable):

  * ``asof`` / ``stale_days`` — the artifact's **market as-of**.  ``resolve_asof``
    in the producer stamps it from ``site/seasonalitydata/index.json``'s ``as_of``,
    so it is a *trading* date: it legitimately sits 2-4 calendar days behind the
    wall clock across a weekend or a holiday, on a perfectly healthy nightly.
  * ``built_at`` / ``built_days`` — when the artifact FILE was last written in this
    checkout (mtime).  The nightly rewrites and commits it whenever its content
    changes, which is every trading day, so this is the closest thing the reader
    has to a producer-run stamp.

``freshness`` combines them into one verdict with copy that states what was
*observed* and never diagnoses a cause the reader cannot see.  Both thresholds are
sized to the trading calendar (a 3-day weekend legitimately spans ~4 days between
writes, a 4-day holiday weekend ~6), because an alarm that is lit on ordinary
Tuesdays is an alarm the operator learns to scroll past — the same failure the
panel exists to prevent, one level up.

Ordering is load-bearing: ``fired`` first, then ``unavailable``, then any state
this reader does not recognise, and only then ``waiting``.  The operator must not
have to scroll past quiet rows to reach the one that needs them, and a state the
producer invented after this console was written is news, not noise: it is counted
in ``counts["other"]`` so the header line can never read "all quiet" above it.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

#: The only artifact dialect this panel understands.  Kept as a literal rather
#: than imported from engine.seasonality.program_watch — the admin package reads
#: committed artifacts and never imports the engine.
WATCH_SCHEMA = "seasonality.program_watch.v1"

_MAX_BYTES = 2_000_000     # guard against an unexpectedly huge artifact
_MAX_TRIPWIRES = 40        # guard against an unexpectedly long tripwire list

#: fired first, then unavailable, then anything unrecognised, then waiting.
#: An unknown state outranks `waiting`: this console cannot tell whether it is
#: quiet, so it must not be filed behind the rows that certainly are.
_STATE_RANK = {"fired": 0, "unavailable": 1, "waiting": 3}
_UNKNOWN_RANK = 2

#: Days the artifact FILE may go unwritten before that is worth saying out loud.
#: A 4-day holiday weekend legitimately spans ~6 days between content changes
#: (last trading day Wednesday → next written artifact the following Tuesday).
_BUILD_STALE_DAYS = 6.0
#: Days the market as-of may sit behind the wall clock before the same.  A long
#: weekend puts a healthy watch ~4.5 days behind; beyond that it is not calendar.
_ASOF_LAG_DAYS = 5.0

_FIELDS = ("key", "state", "headline", "why", "operator_prompt", "handoff_doc", "evidence")


def _watch_path():
    from .paths import DATA
    return DATA / "seasonality" / "program_watch.json"


def _parse_ts(ts) -> datetime | None:
    """Parse a producer timestamp. Offset-aware forms keep their offset.

    ``datetime.fromisoformat`` covers the real dialects (date-only, ``T``-separated,
    ``Z``-suffixed, ``±HH:MM``); the strptime ladder stays as a fallback for the
    looser space-separated forms.  Dropping a timezone offset (the previous
    behaviour) silently mis-ages a timestamp by up to 14h.
    """
    if ts is None or isinstance(ts, bool):
        return None
    s = str(ts).strip()
    if not s:
        return None
    iso = s[:-1] + "+00:00" if s[-1:] in ("Z", "z") else s
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        dt = None
    if dt is None:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s[: len(fmt) + 2], fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _age_days(ts) -> float | None:
    dt = _parse_ts(ts)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def _freshness(asof, stale_days: float | None, built_at: str | None,
               built_days: float | None) -> dict:
    """One verdict over the two clocks — facts only, never a diagnosed cause.

    ``level`` is ``ok`` | ``unknown`` | ``stale``.  ``unknown`` is deliberately a
    stated state and not silence: a watch whose age cannot be read must not render
    identically to a fresh one.
    """
    written = ""
    if built_days is not None:
        written = f" The artifact file was last written {built_days:.1f} days ago"
        written += f" ({built_at} UTC)." if built_at else "."

    if stale_days is not None and stale_days < -0.5:
        return {
            "level": "unknown",
            "note": (
                f"The as-of on this watch ({asof}) is dated in the future — "
                f"{abs(stale_days):.1f} days ahead of this server's clock. One of the two "
                "is wrong, so treat every age below as unreliable." + written
            ),
        }

    if stale_days is None:
        return {
            "level": "unknown",
            "note": (
                f"This watch's age cannot be read: its as-of is {asof!r}, which is not a "
                "date this console can parse. Freshness below is unknown, not fresh."
                + written
            ),
        }

    if built_days is not None and built_days > _BUILD_STALE_DAYS:
        return {
            "level": "stale",
            "note": (
                f"The artifact file has not been rewritten in {built_days:.1f} days"
                + (f" (last written {built_at} UTC)" if built_at else "")
                + f", and its as-of is {asof}. The nightly rewrites it whenever the watch "
                "changes, which is every trading day — longer than a holiday weekend "
                "means the step that writes it (scripts/build_program_watch.py) is worth "
                "checking before you trust the rows below."
            ),
        }

    if stale_days > _ASOF_LAG_DAYS:
        return {
            "level": "stale",
            "note": (
                f"The as-of on this watch ({asof}) is {stale_days:.1f} days behind now. A "
                "market as-of legitimately lags a few days over a weekend or a holiday; "
                "this is further behind than the calendar explains, so the rows below may "
                "be describing a system that has since moved." + written
            ),
        }

    return {"level": "ok", "note": None}


def _unavailable(note: str) -> dict:
    return {
        "available": False,
        "note": note,
        "asof": None,
        "stale_days": None,
        "built_at": None,
        "built_days": None,
        "freshness": {"level": "unknown", "note": note},
        "counts": {"fired": 0, "waiting": 0, "unavailable": 0, "other": 0},
        "tripwires": [],
        "truncated": False,
    }


def panel() -> dict:
    """The seasonality program-watch payload. Never raises; every failure is a state.

    Returns
    -------
    {
      "available": bool,
      "note": str | None,          # why it is unavailable, in plain operator words
      "asof": str | None,          # the artifact's MARKET as-of (a trading date)
      "stale_days": float | None,  # age of that as-of — lags the clock by design
      "built_at": str | None,      # when the artifact file was last written (UTC)
      "built_days": float | None,  # age of that write — the producer-run proxy
      "freshness": {"level": "ok"|"unknown"|"stale", "note": str | None},
      "counts": {"fired": int, "waiting": int, "unavailable": int, "other": int},
      "truncated": bool,           # tripwire list hit the cap
      "tripwires": [{key, state, headline, why, operator_prompt, handoff_doc, evidence}, ...]
    }
    """
    try:
        p = _watch_path()
    except Exception as exc:  # noqa: BLE001 — a broken path resolve is still a state
        logger.warning("program_watch path resolve failed: %s", exc)
        return _unavailable(f"program watch path could not be resolved: {exc}")

    built_at: str | None = None
    built_days: float | None = None
    try:
        if not p.exists():
            return _unavailable(
                "No program watch artifact yet — the nightly has not run here, or this "
                "deploy carries no data/ tree. It is built by scripts/build_program_watch.py "
                "and committed to data/seasonality/program_watch.json."
            )
        stat = p.stat()
        size = stat.st_size
        if size > _MAX_BYTES:
            return _unavailable(
                f"Program watch artifact is {size:,} bytes, over the {_MAX_BYTES:,}-byte "
                "reader cap — not reading it. The producer is emitting something "
                "unexpected; check scripts/build_program_watch.py before trusting this lane."
            )
        try:
            written = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            built_at = written.strftime("%Y-%m-%dT%H:%M:%S")
            built_days = (datetime.now(timezone.utc) - written).total_seconds() / 86400.0
        except Exception:  # noqa: BLE001 — an unreadable mtime is a missing clock, not a failure
            built_at, built_days = None, None
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("program_watch read failed: %s", exc)
        return _unavailable(
            f"Program watch artifact could not be read as JSON ({exc}) — the file exists "
            "but is corrupt or half-written. This is not an all-clear."
        )

    if not isinstance(raw, dict):
        return _unavailable(
            "Program watch artifact is not an object at the top level — refusing to read "
            "it rather than guessing at its shape."
        )

    schema = raw.get("schema")
    if schema != WATCH_SCHEMA:
        return _unavailable(
            f"Program watch artifact declares schema {schema!r}, but this console only "
            f"understands {WATCH_SCHEMA!r} — refusing to render fields it does not "
            "understand. The producer changed; teach admin/program_watch.py the new dialect."
        )

    rows_in = raw.get("tripwires")
    if not isinstance(rows_in, list):
        return _unavailable(
            "Program watch artifact carries no tripwire list — the schema matched but the "
            "'tripwires' key is missing or not a list, so there is nothing to show."
        )

    rows: list[dict] = []
    for r in rows_in:
        if not isinstance(r, dict):
            continue
        row = {f: r.get(f) for f in _FIELDS}
        row["state"] = str(row.get("state") or "").strip().lower() or "unavailable"
        rows.append(row)

    # Counts are of ALL rows (before the display cap), and every row lands in a
    # bucket: a state this reader does not know is counted under "other" so the
    # header can never read "0 fired · 0 no-read · 0 waiting" above a visible row.
    counts = {"fired": 0, "waiting": 0, "unavailable": 0, "other": 0}
    for r in rows:
        counts[r["state"] if r["state"] in counts else "other"] += 1

    # Stable sort: fired → unavailable → unknown → waiting, preserving the
    # artifact's own (deterministic) order inside each state.
    rows.sort(key=lambda r: _STATE_RANK.get(r["state"], _UNKNOWN_RANK))

    asof = raw.get("asof")
    stale_days = _age_days(asof)
    return {
        "available": True,
        "note": None,
        "asof": asof,
        "stale_days": stale_days,
        "built_at": built_at,
        "built_days": built_days,
        "freshness": _freshness(asof, stale_days, built_at, built_days),
        "counts": counts,
        "truncated": len(rows) > _MAX_TRIPWIRES,
        "tripwires": rows[:_MAX_TRIPWIRES],
    }
