"""Sentry wiring for the VPS serving tier (and any other process that opts in).

WHY THIS EXISTS
---------------
Before this module the only trace of a serving-tier fault was a line in
``journalctl -u macro-api`` on the droplet.  A 500 on a paid route, a
``paywall router not mounted`` degrade, a mailer exception inside a
BackgroundTask — all of it died on the box unless someone happened to SSH in
and read the journal.  Sentry gives those faults a destination.

DESIGN RULES (all three are load-bearing — do not "simplify" them away)
----------------------------------------------------------------------
1. **Dependency-optional.**  ``sentry_sdk`` is a soft dependency.  If the
   package is absent from the venv (fresh box, a pip install that failed
   mid-pull, a lane venv that never got it) this module no-ops.  Observability
   must never be the reason ``/api`` fails to start.
2. **Never raises.**  Every failure path returns ``False``.  ``init_sentry()``
   is called before the FastAPI app object exists; an exception there is an
   unbootable API.
3. **DSN comes from the environment, never from git.**  ``SENTRY_DSN`` lives in
   ``/etc/macro-api.env`` (root-only, 0600) alongside the Stripe/Supabase
   secrets.  A Sentry DSN is a write-only ingest key rather than a true secret,
   but keeping it in the env file is what lets the operator rotate it, point
   staging at a different project, or kill ingestion entirely (unset the var,
   restart) without a code change and a render cycle.

The whole module is also **idempotent**: uvicorn's reloader, a re-import under
a different module name, and a lane that calls it twice all collapse to one
``sentry_sdk.init``.

ENVIRONMENT KNOBS (all optional except the DSN)
-----------------------------------------------
SENTRY_DSN                          absent => this module is a no-op
SENTRY_ENVIRONMENT                  default "production"
SENTRY_RELEASE                      default: the deployed git SHA if resolvable
SENTRY_TRACES_SAMPLE_RATE           default 0.1  (see COST note below)
SENTRY_PROFILE_SESSION_SAMPLE_RATE  default 0.0  (profiling off by default)
SENTRY_SEND_DEFAULT_PII             default 1 — request headers + client IP
SENTRY_ENABLE_LOGS                  default 1 — forward ``logging`` records

COST note: Sentry's own quickstart hands out ``traces_sample_rate=1.0`` and
``profile_session_sample_rate=1.0``.  That is a *getting-started* setting: on
this box it would trace every one of the /api/flow/* polls (the tape page polls
several routes on a seconds-long cadence) plus every Caddy-fronted static-gate
check, which burns the transaction quota in hours and adds a profiler thread to
a process that already runs on a 1-2 vCPU droplet.  The default here is 10% of
transactions and no profiling.  Errors are NOT sampled — every exception is
still captured at 100%.  To match the quickstart exactly, put
``SENTRY_TRACES_SAMPLE_RATE=1.0`` and ``SENTRY_PROFILE_SESSION_SAMPLE_RATE=1.0``
in ``/etc/macro-api.env`` and restart the unit.

PII note: ``send_default_pii=True`` attaches request headers and the client IP.
Sentry's default event scrubber (on unless explicitly disabled) still strips
``Authorization``, ``Cookie``, ``X-Api-Key`` and friends, so the Supabase
bearer token does not leave the box.  Set ``SENTRY_SEND_DEFAULT_PII=0`` to drop
headers and IPs entirely.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

log = logging.getLogger("macro.observability")

# Module-level latch. Guards against a double init from the uvicorn reloader or
# from a lane that imports both this module and a caller that already armed it.
_INITIALIZED = False


def _announce(message: str) -> None:
    """Emit a startup line that actually SURVIVES to the journal.

    FOUND LIVE (2026-08-20, immediately after #6115 deployed): the arm line was
    a ``log.info`` and never appeared in ``journalctl -u macro-api`` — so the
    runbook's documented verification step could not work, and "is Sentry on?"
    had no cheap answer at the exact moment it was first asked.

    Cause: uvicorn's LOGGING_CONFIG configures ONLY the ``uvicorn``,
    ``uvicorn.error`` and ``uvicorn.access`` loggers and leaves the root logger
    at its default WARNING. Verified on the box:

        uvicorn configured loggers: ['uvicorn', 'uvicorn.error', 'uvicorn.access']
        root logger level: 30 WARNING
        macro.observability effective level: WARNING

    So every ``log.info`` from this module is dropped, while the ``log.warning``
    failure paths come through fine. Rather than have a library module reach in
    and mutate the host application's logging config, the one-shot startup
    banner goes to stdout — which systemd captures for the unit regardless of
    any logging configuration. `flush` is load-bearing: stdout is block-buffered
    when it is a pipe (which it is under systemd), so an unflushed banner sits
    in the buffer instead of reaching the journal.

    The line is still ALSO sent through the logger, so an operator who has
    configured INFO-level logging gets it in structured form too.
    """
    print(message, flush=True)
    log.info("%s", message)


def _flag(name: str, default: bool) -> bool:
    """Read a 0/1-style env flag. Anything unparseable falls back to *default*."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _rate(name: str, default: float) -> float:
    """Read a sample rate, clamped to [0.0, 1.0]. Junk falls back to *default*."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        log.warning("observability: %s=%r is not a number; using %s", name, raw, default)
        return default
    # NaN fails every comparison, so an `if value < 0 or value > 1` guard would
    # fail OPEN and hand NaN straight to the SDK. Test for finiteness first.
    if value != value:  # NaN
        log.warning("observability: %s=%r is NaN; using %s", name, raw, default)
        return default
    return min(1.0, max(0.0, value))


def _release() -> str | None:
    """Best-effort deployed release id: SENTRY_RELEASE, else the checkout's SHA."""
    explicit = os.environ.get("SENTRY_RELEASE", "").strip()
    if explicit:
        return explicit
    repo = os.environ.get("MACRO_REPO", "/opt/macro")
    try:
        sha = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
    except Exception:  # git absent, repo unreadable, timeout — all non-fatal
        return None
    return sha[:12] or None


def init_sentry(component: str) -> bool:
    """Arm Sentry for *component* (e.g. ``"macro-api"``).

    Returns True when this call armed the SDK, False in every other case —
    already armed, no DSN configured, ``sentry_sdk`` not installed, or the init
    itself blew up. Never raises.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return False

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        _announce("observability: SENTRY_DSN unset; Sentry disabled for %s" % component)
        return False

    try:
        import sentry_sdk
    except Exception as exc:  # noqa: BLE001 — a missing/broken SDK must not kill boot
        log.warning("observability: sentry_sdk unavailable (%r); Sentry disabled", exc)
        return False

    options: dict[str, Any] = {
        "dsn": dsn,
        "environment": os.environ.get("SENTRY_ENVIRONMENT", "production"),
        "send_default_pii": _flag("SENTRY_SEND_DEFAULT_PII", True),
        "enable_logs": _flag("SENTRY_ENABLE_LOGS", True),
        "traces_sample_rate": _rate("SENTRY_TRACES_SAMPLE_RATE", 0.1),
        "profile_session_sample_rate": _rate("SENTRY_PROFILE_SESSION_SAMPLE_RATE", 0.0),
    }
    release = _release()
    if release:
        options["release"] = release

    try:
        sentry_sdk.init(**options)
    except TypeError as exc:
        # An older sentry-sdk on the box may not accept the newer top-level
        # kwargs (``enable_logs`` graduated out of ``_experiments`` in 2.35).
        # Retry with the portable core rather than leaving Sentry dark.
        log.warning("observability: sentry init rejected an option (%r); retrying minimal", exc)
        for optional in ("enable_logs", "profile_session_sample_rate"):
            options.pop(optional, None)
        try:
            sentry_sdk.init(**options)
        except Exception as exc2:  # noqa: BLE001
            log.warning("observability: sentry init failed (%r); Sentry disabled", exc2)
            return False
    except Exception as exc:  # noqa: BLE001
        log.warning("observability: sentry init failed (%r); Sentry disabled", exc)
        return False

    try:
        sentry_sdk.set_tag("component", component)
    except Exception:  # noqa: BLE001 — tagging is cosmetic
        pass

    _INITIALIZED = True
    _announce(
        "observability: Sentry armed for %s (env=%s release=%s traces=%s profiles=%s)"
        % (
            component, options["environment"], release or "-",
            options.get("traces_sample_rate"),
            options.get("profile_session_sample_rate", "n/a"),
        )
    )
    return True


def sentry_armed() -> bool:
    """True once :func:`init_sentry` has successfully armed the SDK."""
    return _INITIALIZED
