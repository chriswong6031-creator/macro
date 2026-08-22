"""Credentialed SPY REST daily-bar seal owner for Market Memory W2C M0D.

This is the sole production source owner for the sources-spy-rest-v1 family.
It runs as a systemd oneshot under macro-market-memory-source-spy-rest.service,
triggered at 04:00:00 UTC on D+1 with a 5-minute timeout covering the full
seal window.

Network and credentials: uses MASSIVE_API_KEY / POLYGON_API_KEY (LoadCredential
from a dedicated /etc/macro-market-memory-spy-rest/ path).  Does NOT use
EnvironmentFile=/etc/macro-api.env.

Credentials are read from the systemd CREDENTIALS_DIRECTORY (LoadCredential ids
MASSIVE_API_KEY and POLYGON_API_KEY).  Falls back to the environment only when
CREDENTIALS_DIRECTORY is unset (test mode).

Seal window: [04:00:00Z, 04:05:00Z) on D+1.

After the window closes the module evaluates the stability predicate and writes
ONE generation if stable.  Polls during the window are not generations.

Missing credentials → exit 1 (systemd oneshot failure, not a silent skip).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import stat
import sys
import time as time_module
from collections.abc import Callable, Mapping
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL_SECONDS = 10
_SEAL_WINDOW_SECONDS = 300  # 5 minutes
_DEFAULT_STORE_ROOT = Path("/var/lib/macro-market-memory/state/sources-spy-rest-v1")
_DEFAULT_REPOSITORY_ROOT = Path("/opt/macro")

_MAX_CREDENTIAL_BYTES = 4096


# ---------------------------------------------------------------------------
# Fetch helpers (re-use massive_close.py's KEY_ENVS and _default_fetch)
# ---------------------------------------------------------------------------


def _read_credential_from_directory(credential_name: str, directory: Path) -> str | None:
    """Read one credential file from a systemd CREDENTIALS_DIRECTORY.

    Matches the sibling pattern in capture_market_memory_option_oi.py:
    O_NOFOLLOW, regular file, no NUL/CR, strip one trailing newline, ASCII.
    Returns None if the file does not exist (not all keys need to be present).
    Raises on any security violation.
    """
    cred_path = directory / credential_name
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(cred_path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(
            f"systemd credential {credential_name!r} is unavailable: {exc}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                f"systemd credential {credential_name!r} is not a regular file"
            )
        body = os.read(descriptor, _MAX_CREDENTIAL_BYTES + 1)
    finally:
        os.close(descriptor)
    if not body or len(body) > _MAX_CREDENTIAL_BYTES or b"\x00" in body:
        raise RuntimeError(
            f"systemd credential {credential_name!r} has invalid byte length"
        )
    if body.endswith(b"\n"):
        body = body[:-1]
    if b"\n" in body or b"\r" in body:
        raise RuntimeError(
            f"systemd credential {credential_name!r} must contain one token"
        )
    try:
        return body.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"systemd credential {credential_name!r} must be ASCII"
        ) from exc


def _build_fetcher() -> Callable[[str, Mapping[str, Any] | None], Any] | None:
    """Build a fetcher using MASSIVE_API_KEY / POLYGON_API_KEY.

    Production: reads from systemd CREDENTIALS_DIRECTORY (LoadCredential).
    Test fallback: reads from os.environ when CREDENTIALS_DIRECTORY is unset.
    Returns None when no key is found (caller treats this as no_credentials).
    """
    from engine.close_pass.massive_close import KEY_ENVS, _default_fetch  # noqa: PLC0415

    credentials_dir_str = os.environ.get("CREDENTIALS_DIRECTORY")
    if credentials_dir_str:
        cred_dir = Path(credentials_dir_str)
        if not cred_dir.is_absolute() or cred_dir.is_symlink() or not cred_dir.is_dir():
            log.error("CREDENTIALS_DIRECTORY is inadmissible: %s", credentials_dir_str)
            return None
        for name in KEY_ENVS:
            try:
                value = _read_credential_from_directory(name, cred_dir)
            except RuntimeError as exc:
                log.error("credential read error for %s: %s", name, exc)
                return None
            if value:
                value = value.strip()
                if value:
                    try:
                        return _default_fetch(value)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("http client unavailable: %s", exc)
                        return None
        log.error("no API key found in CREDENTIALS_DIRECTORY (%s)", "/".join(KEY_ENVS))
        return None

    # Test fallback: read from environment
    for name in KEY_ENVS:
        value = (os.environ.get(name) or "").strip()
        if value:
            try:
                return _default_fetch(value)
            except Exception as exc:  # noqa: BLE001
                log.warning("http client unavailable: %s", exc)
                return None
    log.error("no API key (%s unset)", "/".join(KEY_ENVS))
    return None


def _fetch_spy_daily_bar(
    session: date,
    fetcher: Callable[[str, Mapping[str, Any] | None], Any],
) -> tuple[str, list[Any]]:
    """Fetch SPY daily bar for session using the REST v2 aggregates endpoint.

    Returns (status, results) where status is one of:
    'valid_bar', 'no_bar', 'transport_error', 'malformed'
    """
    from engine.close_pass.massive_close import DEFAULT_BASE_URL  # noqa: PLC0415

    session_str = session.isoformat()
    path = f"/v2/aggs/ticker/SPY/range/1/day/{session_str}/{session_str}"
    params = {"adjusted": "false"}
    try:
        payload = fetcher(path, params)
    except Exception as exc:  # noqa: BLE001
        log.warning("transport error fetching SPY daily bar: %s", exc)
        return "transport_error", []

    if payload is None:
        return "transport_error", []

    if not isinstance(payload, dict):
        return "malformed", []

    status = str(payload.get("status", "")).lower()
    results = payload.get("results")

    if status not in ("ok", "success"):
        if not results:
            return "no_bar", []
        return "malformed", []

    if not isinstance(results, list):
        return "no_bar", []

    return "ok_results", results


# ---------------------------------------------------------------------------
# REST lookback helper (M6)
# ---------------------------------------------------------------------------


def _fetch_lookback_closes_from_rest(
    current_session: date,
    *,
    fetcher: Callable,
    n: int = 20,
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fetch up to ``n`` prior session closes from REST to supplement store lookback.

    Returns a list of {"session": str, "close": float} dicts, most-recent-first.
    Appends to ``existing`` (already fetched from the store).  Does NOT fetch
    for D itself — only for sessions BEFORE current_session.
    This is supplemental: if the store already has enough, we skip REST.
    """
    from lib import nyse_calendar  # noqa: PLC0415
    from engine.close_pass.massive_close import DEFAULT_BASE_URL  # noqa: PLC0415

    existing_sessions = {row["session"] for row in (existing or [])}
    results: list[dict[str, Any]] = list(existing or [])

    # Walk backwards from current_session - 1
    candidate = current_session - timedelta(days=1)
    attempts = 0
    while len(results) < n and attempts < n + 14:
        attempts += 1
        if not nyse_calendar.is_session(candidate):
            candidate -= timedelta(days=1)
            continue
        session_str = candidate.isoformat()
        if session_str in existing_sessions:
            candidate -= timedelta(days=1)
            continue
        path = f"/v2/aggs/ticker/SPY/range/1/day/{session_str}/{session_str}"
        params = {"adjusted": "false"}
        try:
            payload = fetcher(path, params)
        except Exception:  # noqa: BLE001
            candidate -= timedelta(days=1)
            continue
        if not isinstance(payload, dict):
            candidate -= timedelta(days=1)
            continue
        bar_results = payload.get("results")
        if not isinstance(bar_results, list) or not bar_results:
            candidate -= timedelta(days=1)
            continue
        bar = bar_results[0]
        close = bar.get("c") if isinstance(bar, dict) else None
        if close is not None:
            results.append({"session": session_str, "close": close})
            existing_sessions.add(session_str)
        candidate -= timedelta(days=1)

    # Sort most-recent-first
    results.sort(key=lambda r: r["session"], reverse=True)
    return results[:n]


# ---------------------------------------------------------------------------
# Seal observation loop
# ---------------------------------------------------------------------------


def _collect_seal_observations(
    session: date,
    *,
    seal_open: datetime,
    seal_close: datetime,
    fetcher: Callable | None,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[list[Any], dict[str, list[Any]]]:
    """Poll during [seal_open, seal_close) and collect observations.

    Returns (observations, results_cache) where results_cache maps each
    valid-bar digest to the last seen results[] payload for that digest.
    This cache is the canonical payload for M5: the caller must NOT re-fetch
    after the window closes — a post-window vendor change must not discard a
    stable seal.
    """
    from engine.neuralweb.market_memory_sources_spy import (  # noqa: PLC0415
        SealObservation,
        _results_digest,
        _validate_single_bar,
    )

    clock_fn = clock or (lambda: datetime.now(timezone.utc))
    sleep_fn = sleeper or time_module.sleep
    observations: list[SealObservation] = []
    # digest → last seen results[] for that digest (M5: persist, don't refetch)
    results_cache: dict[str, list[Any]] = {}

    while True:
        now = clock_fn()
        if now >= seal_close:
            break

        if fetcher is None:
            obs = SealObservation(
                observed_at=now,
                status="transport_error",
                digest=None,
            )
        else:
            raw_status, results = _fetch_spy_daily_bar(session, fetcher)
            if raw_status == "transport_error":
                obs = SealObservation(
                    observed_at=now,
                    status="transport_error",
                    digest=None,
                )
            elif raw_status == "no_bar" or not results:
                obs = SealObservation(
                    observed_at=now,
                    status="no_bar",
                    digest=None,
                )
            elif raw_status == "malformed":
                obs = SealObservation(
                    observed_at=now,
                    status="malformed",
                    digest=None,
                )
            else:
                # ok_results — validate
                if len(results) != 1:
                    obs = SealObservation(
                        observed_at=now,
                        status="malformed",
                        digest=None,
                    )
                else:
                    valid, reason = _validate_single_bar(results[0], session_date=session)
                    if not valid:
                        log.debug("bar validation failed: %s", reason)
                        obs = SealObservation(
                            observed_at=now,
                            status="malformed",
                            digest=None,
                        )
                    else:
                        try:
                            digest = _results_digest(results)
                        except Exception as exc:  # noqa: BLE001
                            log.warning("digest error: %s", exc)
                            obs = SealObservation(
                                observed_at=now,
                                status="malformed",
                                digest=None,
                            )
                        else:
                            obs = SealObservation(
                                observed_at=now,
                                status="valid_bar",
                                digest=digest,
                            )
                            # Cache the results for this digest (M5)
                            results_cache[digest] = list(results)

        observations.append(obs)
        log.debug("seal obs %s: status=%s digest=%s", now.isoformat(), obs.status, obs.digest)

        # Sleep until next poll or seal_close, whichever comes first
        next_poll = now + timedelta(seconds=_POLL_INTERVAL_SECONDS)
        sleep_until = min(next_poll, seal_close)
        remaining = (sleep_until - clock_fn()).total_seconds()
        if remaining > 0:
            sleep_fn(remaining)

    return observations, results_cache


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def ingest_spy_rest_source(
    *,
    store_root: str | Path = _DEFAULT_STORE_ROOT,
    session: date | None = None,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
    fetcher: Callable | None = None,
) -> dict[str, Any]:
    """Run the seal owner for session D.

    If session is None, derives session from the current time (must be in
    the D+1 seal window).  If session is provided, validates it directly.

    Returns a run receipt dict.
    """
    from engine.neuralweb.market_memory_sources_spy import (  # noqa: PLC0415
        SealObservation,
        SealState,
        evaluate_seal_predicate,
        intake_spy_rest_bar,
        seal_window_for_session,
        session_for_seal_time,
        _results_digest,
        _validate_single_bar,
    )

    clock_fn = clock or (lambda: datetime.now(timezone.utc))
    sleep_fn = sleeper or time_module.sleep

    now = clock_fn()

    if session is None:
        derived = session_for_seal_time(now)
        if derived is None:
            raise RuntimeError(
                f"current time {now.isoformat()} is not within any seal window; "
                "pass session= explicitly for testing"
            )
        session = derived

    seal_open, seal_close = seal_window_for_session(session)

    # Refuse a prior or future session relative to the seal window
    if now >= seal_close and session < (now.date() - timedelta(days=1)):
        raise RuntimeError(
            f"seal window for session {session} is in the past (now={now.isoformat()})"
        )

    log.info(
        "SPY REST seal owner starting: session=%s window=[%s, %s)",
        session,
        seal_open.isoformat(),
        seal_close.isoformat(),
    )

    # Build fetcher if not injected
    if fetcher is None:
        fetcher = _build_fetcher()
        if fetcher is None:
            return {
                "schema": "market_memory.spy_rest_source_intake_run.v1",
                "status": "no_credentials",
                "session": session.isoformat(),
                "source_id": "massive_rest:SPY:unadjusted_daily",
                "generation_id": None,
                "created": False,
            }

    # Wait until seal window opens if we're early
    early_wait = (seal_open - clock_fn()).total_seconds()
    if early_wait > 0:
        log.info("waiting %.1fs for seal window to open", early_wait)
        sleep_fn(early_wait)

    # Collect observations during the window; also receive the results cache (M5)
    raw_observations, results_cache = _collect_seal_observations(
        session,
        seal_open=seal_open,
        seal_close=seal_close,
        fetcher=fetcher,
        clock=clock,
        sleeper=sleeper,
    )

    sealed_at = clock_fn().isoformat().replace("+00:00", "Z")

    # Evaluate stability predicate
    seal_state = evaluate_seal_predicate(
        raw_observations,
        session=session,
        seal_open=seal_open,
        seal_close=seal_close,
    )

    log.info(
        "seal predicate: opportunity_eligible=%s reason=%s",
        seal_state.opportunity_eligible,
        seal_state.reason,
    )

    if not seal_state.opportunity_eligible:
        return {
            "schema": "market_memory.spy_rest_source_intake_run.v1",
            "status": "not_eligible",
            "session": session.isoformat(),
            "source_id": "massive_rest:SPY:unadjusted_daily",
            "reason": seal_state.reason,
            "generation_id": None,
            "created": False,
        }

    # Use the cached in-window results whose digest satisfied the predicate (M5).
    # Do NOT re-fetch after the window closes — a post-window vendor change must
    # not discard a stable seal.  A later different set of bytes appends a new
    # generation; they must not mutate the sealed object.
    results = results_cache.get(seal_state.bar_digest or "")
    if not results:
        return {
            "schema": "market_memory.spy_rest_source_intake_run.v1",
            "status": "post_seal_fetch_failed",
            "session": session.isoformat(),
            "source_id": "massive_rest:SPY:unadjusted_daily",
            "reason": "sealed digest not found in in-window results cache",
            "generation_id": None,
            "created": False,
        }

    # Build lookback closes: try the store first, then fall back to REST (M6).
    from engine.neuralweb.market_memory_sources_spy import build_lookback_closes  # noqa: PLC0415
    try:
        lookback = build_lookback_closes(store_root, current_session=session, n=20)
    except Exception as exc:  # noqa: BLE001
        log.warning("store lookback fetch failed: %s", exc)
        lookback = []

    if len(lookback) < 20 and fetcher is not None:
        # Supplement from REST for prior XNYS sessions (M6).
        # Fetch at most 20 prior sessions.  This MUST NOT substitute for a
        # missing D seal — we only get here after a stable D seal is confirmed.
        try:
            lookback = _fetch_lookback_closes_from_rest(
                session, fetcher=fetcher, n=20, existing=lookback
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("REST lookback fetch failed (continuing without): %s", exc)

    lookback = lookback if lookback else None

    observed_at = clock_fn().isoformat().replace("+00:00", "Z")

    # Attach the artifact to the seal state for reference
    from engine.neuralweb.market_memory_sources_spy import SealState as SS  # noqa: PLC0415
    enriched_state = SS(
        session=seal_state.session,
        sealed=seal_state.sealed,
        stable=seal_state.stable,
        opportunity_eligible=seal_state.opportunity_eligible,
        bar_digest=seal_state.bar_digest,
        bar_artifact=None,
        transcript=seal_state.transcript,
        reason=seal_state.reason,
    )

    stored = intake_spy_rest_bar(
        store_root,
        session=session,
        seal_state=enriched_state,
        results=results,
        lookback_closes=lookback,
        sealed_at=sealed_at,
        observed_at=observed_at,
    )

    return {
        "schema": "market_memory.spy_rest_source_intake_run.v1",
        "status": "created" if stored.created else "already_present",
        "session": session.isoformat(),
        "source_id": "massive_rest:SPY:unadjusted_daily",
        "generation_id": stored.generation_id,
        "created": stored.created,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seal owner for SPY REST daily-bar source evidence"
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=_DEFAULT_STORE_ROOT,
        help="Private source-store root (default: %(default)s)",
    )
    parser.add_argument(
        "--session",
        type=date.fromisoformat,
        default=None,
        help="Session date YYYY-MM-DD (default: derived from current time)",
    )
    return parser.parse_args(argv)


def _main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv)
    try:
        receipt = ingest_spy_rest_source(
            store_root=args.store_root,
            session=args.session,
        )
        print(json.dumps(receipt, indent=2, sort_keys=True))
        # Missing credentials → exit 1 (systemd sees failure, not silent skip)
        if receipt.get("status") == "no_credentials":
            log.error("no API credentials available — systemd LoadCredential not set")
            return 1
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("SPY REST seal owner failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
