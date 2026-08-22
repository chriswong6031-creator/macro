"""Credentialed SPY REST daily-bar seal owner for Market Memory W2C M0D.

This is the sole production source owner for the sources-spy-rest-v1 family.
It runs as a systemd oneshot under macro-market-memory-source-spy-rest.service,
triggered at 04:00:00 UTC on D+1 with a 5-minute timeout covering the full
seal window.

Network and credentials: uses MASSIVE_API_KEY / POLYGON_API_KEY (LoadCredential
from a dedicated /etc/macro-market-memory-spy-rest/ path).  Does NOT use
EnvironmentFile=/etc/macro-api.env.

Seal window: [04:00:00Z, 04:05:00Z) on D+1.

After the window closes the module evaluates the stability predicate and writes
ONE generation if stable.  Polls during the window are not generations.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
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


# ---------------------------------------------------------------------------
# Fetch helpers (re-use massive_close.py's KEY_ENVS and _default_fetch)
# ---------------------------------------------------------------------------


def _build_fetcher() -> Callable[[str, Mapping[str, Any] | None], Any] | None:
    """Build a fetcher using MASSIVE_API_KEY / POLYGON_API_KEY from env."""
    from engine.close_pass.massive_close import KEY_ENVS, _default_fetch  # noqa: PLC0415

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
) -> list[dict[str, Any]]:
    """Poll during [seal_open, seal_close) and collect observations."""
    from engine.neuralweb.market_memory_sources_spy import (  # noqa: PLC0415
        SealObservation,
        _results_digest,
        _validate_single_bar,
    )

    clock_fn = clock or (lambda: datetime.now(timezone.utc))
    sleep_fn = sleeper or time_module.sleep
    observations: list[SealObservation] = []

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

        observations.append(obs)
        log.debug("seal obs %s: status=%s digest=%s", now.isoformat(), obs.status, obs.digest)

        # Sleep until next poll or seal_close, whichever comes first
        next_poll = now + timedelta(seconds=_POLL_INTERVAL_SECONDS)
        sleep_until = min(next_poll, seal_close)
        remaining = (sleep_until - clock_fn()).total_seconds()
        if remaining > 0:
            sleep_fn(remaining)

    return observations


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

    # Collect observations during the window
    raw_observations = _collect_seal_observations(
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

    # Fetch the canonical results for the stable digest
    raw_status, results = _fetch_spy_daily_bar(session, fetcher)
    if raw_status not in ("ok_results",) or not results:
        return {
            "schema": "market_memory.spy_rest_source_intake_run.v1",
            "status": "post_seal_fetch_failed",
            "session": session.isoformat(),
            "source_id": "massive_rest:SPY:unadjusted_daily",
            "reason": f"post-seal canonical fetch failed: {raw_status}",
            "generation_id": None,
            "created": False,
        }

    # Build lookback closes (best-effort)
    from engine.neuralweb.market_memory_sources_spy import build_lookback_closes  # noqa: PLC0415
    try:
        lookback = build_lookback_closes(store_root, current_session=session, n=20)
    except Exception as exc:  # noqa: BLE001
        log.warning("lookback fetch failed (continuing without): %s", exc)
        lookback = None

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
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("SPY REST seal owner failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
