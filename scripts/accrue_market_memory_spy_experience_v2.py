"""Experience-v2 accrual for Market Memory W2C M0D v2.

This is the v2-only accrual script.  It reads from technicals-v2 and
sources-spy-rest-v1, writes to experience-v2, and enforces the strict
prospective activation policy.

V1 script roots are UNCHANGED by this module.  This module does NOT:
- repair/supersede/alter v1 abstentions
- write to experience-v1, technicals-v1, or any other v1 root
- expose credentials (keyless)

Activation: strict prospective.  Two conditions must both hold:
  (a) Registration on origin/main: the v2 registration JSON
      (config/market_memory_spy_experience_registration.v2.json) is present in
      the deployed repository.  Production deploy from origin/main is the
      registration-on-main half — this module does NOT scrape git log.
  (b) Verified install: a deploy-written install marker exists at
      ``<experience_root>/.v2_install_verified``.  update.sh writes this marker
      once (create-once, idempotent) after the experience-v2 units are installed.

Runtime refuses/abstains for sessions whose XNYS regular open is not strictly
after both conditions above.

Admission window: [04:30:00Z, 04:45:00Z) on D+1.  Accrual outside this window
is refused with an explicit abstain status.

Timer target: 04:32Z on D+1 (after the 04:30Z v1 timer).  Persistent=false
on the timer so a catch-up run cannot accrue at a random hour.

Session derivation: timers fire on D+1; session = D is derived via
derive_morning_session() which requires now >= 04:05Z and T-1 to be an XNYS
session.  Pass ``session=`` explicitly to override (tests).
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

log = logging.getLogger(__name__)

DEFAULT_EXPERIENCE_V2_ROOT = Path(
    "/var/lib/macro-market-memory/state/experience-v2"
)
DEFAULT_SOURCE_ROOT = Path(
    "/var/lib/macro-market-memory/state/sources-spy-rest-v1"
)
DEFAULT_TECHNICALS_V2_ROOT = Path(
    "/var/lib/macro-market-memory/state/technicals-v2"
)

# Admission window constants (M2): [04:30:00Z, 04:45:00Z) on D+1
_ADMISSION_WINDOW_OPEN_HOUR = 4
_ADMISSION_WINDOW_OPEN_MINUTE = 30
_ADMISSION_WINDOW_CLOSE_HOUR = 4
_ADMISSION_WINDOW_CLOSE_MINUTE = 45

V2_INSTALL_MARKER_FILENAME = ".v2_install_verified"

REGISTRATION_SCHEMA_V2 = "market_memory.spy_experience_registration.v2"
EXPERIENCE_V2_RECORD_SCHEMA = "market_memory.spy_experience_v2_record.v1"
EXPERIENCE_V2_HEAD_SCHEMA = "market_memory.spy_experience_v2_head.v1"


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class ExperienceV2Error(RuntimeError):
    """Base error for experience-v2 accrual."""


class ExperienceV2ActivationError(ExperienceV2Error):
    """Activation preconditions not met — abstain."""


class ExperienceV2SourceError(ExperienceV2Error):
    """Required source data unavailable."""


# ---------------------------------------------------------------------------
# Activation guard
# ---------------------------------------------------------------------------


def _read_install_marker(experience_root: Path) -> str | None:
    """Return the install timestamp string if the marker file exists."""
    marker = experience_root / V2_INSTALL_MARKER_FILENAME
    if not marker.exists():
        return None
    try:
        return marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def check_activation(
    experience_root: Path,
    *,
    session: date,
    clock: Any = None,
) -> None:
    """Raise ExperienceV2ActivationError if session is not strictly post-activation.

    The activation policy is:
        first_xnys_regular_open_strictly_after_registration_on_origin_main
        _AND_verified_install

    Both conditions must hold.  Missing install marker → abstain.

    B4: install_date may be a non-session (Saturday, holiday).
    Computes the first XNYS regular session whose open is strictly after the
    install timestamp (datetime, not date) — never raises TypeError.
    """
    from lib import nyse_calendar  # noqa: PLC0415

    install_ts_str = _read_install_marker(experience_root)
    if install_ts_str is None:
        raise ExperienceV2ActivationError(
            f"v2 install marker missing at "
            f"{experience_root / V2_INSTALL_MARKER_FILENAME}; "
            "refusing session (prospective activation not verified)"
        )

    # The activation epoch is the datetime the install marker was written.
    try:
        install_ts = datetime.fromisoformat(
            install_ts_str.replace("Z", "+00:00")
        )
        install_date = install_ts.date()
    except ValueError:
        raise ExperienceV2ActivationError(
            f"v2 install marker has invalid timestamp: {install_ts_str!r}"
        ) from None

    # Find first XNYS session whose regular open is strictly after install_ts.
    # session_n_forward(d, 1) returns None when d is not a session (TypeError).
    # Fix: if install_date is a session, use the existing session_n_forward path.
    # If not (weekend/holiday), find the first session after install_date.
    if nyse_calendar.is_session(install_date):
        next_eligible = nyse_calendar.session_n_forward(install_date, 1)
        if next_eligible is None:
            raise ExperienceV2ActivationError(
                f"cannot determine next XNYS session after install date "
                f"{install_date.isoformat()}"
            )
    else:
        # Non-session install day: find first XNYS session strictly after install_date.
        from lib.nyse_calendar import sessions_between  # noqa: PLC0415
        from datetime import timedelta as _td  # noqa: PLC0415
        search_end = install_date + _td(days=14)
        future = sessions_between(install_date + _td(days=1), search_end)
        if not future:
            raise ExperienceV2ActivationError(
                f"no XNYS session found within 14 days of install date "
                f"{install_date.isoformat()}"
            )
        next_eligible = future[0]

    if session < next_eligible:
        raise ExperienceV2ActivationError(
            f"session {session.isoformat()} is not strictly after install date "
            f"{install_date.isoformat()}; earliest eligible is "
            f"{next_eligible.isoformat()}"
        )


# ---------------------------------------------------------------------------
# Registration loader
# ---------------------------------------------------------------------------


def load_registration_v2(repository_root: str | Path) -> dict[str, Any]:
    """Load and validate the v2 registration JSON."""
    from engine.neuralweb.market_memory_experience_accrual import (  # noqa: PLC0415
        _expected_registration_spec_v2,
        REGISTRATION_SCHEMA_V2 as _SCHEMA,
    )

    reg_path = (
        Path(repository_root) / "config" /
        "market_memory_spy_experience_registration.v2.json"
    )
    if not reg_path.exists():
        raise ExperienceV2Error(f"v2 registration not found: {reg_path}")
    data = json.loads(reg_path.read_bytes())
    if data.get("schema") != _SCHEMA:
        raise ExperienceV2Error(
            f"v2 registration schema mismatch: {data.get('schema')!r}"
        )
    if data.get("spec") != _expected_registration_spec_v2():
        raise ExperienceV2Error("v2 registration spec drift (file differs from code)")
    return data


# ---------------------------------------------------------------------------
# Source data reader
# ---------------------------------------------------------------------------


def _read_sealed_bar(source_root: Path, *, session: date) -> dict[str, Any] | None:
    """Read opportunity-eligible sealed bar for session from sources-spy-rest-v1."""
    from scripts.capture_market_memory_technicals_v2 import (  # noqa: PLC0415
        validate_spy_rest_source_root,
    )
    from engine.neuralweb.market_memory_sources_spy import (  # noqa: PLC0415
        SPY_FAMILY,
        _validate_spy_rest_receipt,
        _read_receipt_copies_by_validate,
        _read_store_object,
        _object_path,
        _MAX_OBJECT_BYTES,
    )
    from engine.neuralweb.market_memory_source_kernel import (  # noqa: PLC0415
        _load_store_state,
        SourceNotFound,
        SourceStoreError,
        _store_manifest_path,
    )
    from engine.neuralweb import market_memory as _mm  # noqa: PLC0415

    validated = validate_spy_rest_source_root(source_root)
    if not _store_manifest_path(validated).exists():
        return None
    try:
        state = _load_store_state(validated, family=SPY_FAMILY, authority=dict(_mm.AUTHORITY))
    except Exception:  # noqa: BLE001
        return None
    session_str = session.isoformat()
    for entry in reversed(state.generation["receipts"]):
        try:
            receipt, _ = _read_receipt_copies_by_validate(
                validated, entry,
                store_id=state.manifest["store_id"],
                validate_fn=_validate_spy_rest_receipt,
            )
        except Exception:  # noqa: BLE001
            continue
        if receipt.get("session") != session_str:
            continue
        if not receipt.get("quality", {}).get("opportunity_eligible", False):
            continue
        try:
            artifact, _ = _read_store_object(
                _object_path(validated, receipt["artifact_sha256"]),
                limit=_MAX_OBJECT_BYTES,
                label="SPY REST source object",
            )
        except Exception:  # noqa: BLE001
            continue
        if artifact.get("results"):
            return {
                "session": session_str,
                "bar": artifact["results"][0],
                "source_generation_id": state.generation["generation_id"],
            }
    return None


def _read_technical_capture(
    technicals_v2_root: Path, *, session: date
) -> dict[str, Any] | None:
    """Return the technicals-v2 capture receipt for session, or None."""
    from scripts.capture_market_memory_technicals_v2 import (  # noqa: PLC0415
        read_latest_capture_for_session,
    )
    return read_latest_capture_for_session(technicals_v2_root, session=session)


# ---------------------------------------------------------------------------
# Experience-v2 store
# ---------------------------------------------------------------------------


def _experience_v2_records_dir(root: Path) -> Path:
    return root / "records"


def _experience_v2_head_path(root: Path) -> Path:
    return root / "EXP_V2_HEAD.json"


def _canonical_bytes_v2(value: Any) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _write_create_once_v2(path: Path, value: Any, *, label: str) -> None:
    body = _canonical_bytes_v2(value)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        return  # idempotent
    try:
        view = memoryview(body)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_head_v2(root: Path, head: dict[str, Any]) -> None:
    body = _canonical_bytes_v2(head)
    path = _experience_v2_head_path(root)
    tmp = root / f".EXP_V2_HEAD.tmp.{os.getpid()}"
    try:
        fd = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(body)
            while view:
                n = os.write(fd, view)
                view = view[n:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _write_install_marker(experience_root: Path, timestamp: str) -> None:
    """Write the v2 install marker (idempotent)."""
    marker = experience_root / V2_INSTALL_MARKER_FILENAME
    experience_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not marker.exists():
        try:
            fd = os.open(
                marker,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                data = (timestamp + "\n").encode("utf-8")
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
        except FileExistsError:
            pass


# ---------------------------------------------------------------------------
# Accrual entry point
# ---------------------------------------------------------------------------


def validate_experience_v2_store_root(root: str | Path) -> Path:
    """Validate that root ends in experience-v2 under a state/ parent (B6).

    v2 accrual must NEVER write to experience-v1.
    """
    from engine.neuralweb.market_memory_experience_accrual import (  # noqa: PLC0415
        MarketMemoryExperienceStoreError,
    )
    import os as _os  # noqa: PLC0415

    unresolved = Path(root).expanduser()
    absolute = Path(_os.path.abspath(_os.fspath(unresolved)))
    if absolute.name != "experience-v2" or absolute.parent.name != "state":
        raise MarketMemoryExperienceStoreError(
            "v2 experience store root must end in state/experience-v2 "
            f"(got {absolute!r}) — refusing to write experience-v1 or other paths"
        )
    return absolute


def accrue_spy_experience_v2(
    repository_root: str | Path,
    *,
    experience_root: str | Path,
    source_root: str | Path,
    technicals_v2_root: str | Path,
    session: date | None = None,
    clock: Any = None,
) -> dict[str, Any]:
    """Accrue experience-v2 for session.

    Returns a result dict with keys: status, session, message.
    """
    clock_fn = clock or (lambda: datetime.now(timezone.utc))
    now = clock_fn()

    # B6: Validate root before any other logic — this guard must never be bypassed by
    # early returns for admission window, session derivation, or any other path.
    exp_root = validate_experience_v2_store_root(experience_root)

    if session is None:
        # B2: timers fire at 04:32Z on D+1; derive session D via helper.
        from engine.neuralweb.market_memory_sources_spy import derive_morning_session  # noqa: PLC0415
        derived = derive_morning_session(now)
        if derived is None:
            return {
                "status": "no_session",
                "session": None,
                "message": (
                    f"cannot derive session from current time {now.isoformat()} "
                    "(before 04:05Z or T-1 is not an XNYS session)"
                ),
            }
        session = derived

    # M2: Enforce admission window [04:30:00Z, 04:45:00Z) on now, always —
    # even when session is passed explicitly. Outside the window means no accrual;
    # create-once semantics would poison the record slot if we ran early.
    utc_now = now.astimezone(timezone.utc)
    today = utc_now.date()
    admission_open = datetime.combine(
        today,
        time(_ADMISSION_WINDOW_OPEN_HOUR, _ADMISSION_WINDOW_OPEN_MINUTE),
        tzinfo=timezone.utc,
    )
    admission_close = datetime.combine(
        today,
        time(_ADMISSION_WINDOW_CLOSE_HOUR, _ADMISSION_WINDOW_CLOSE_MINUTE),
        tzinfo=timezone.utc,
    )
    if not (admission_open <= utc_now < admission_close):
        return {
            "status": "outside_admission_window",
            "session": session.isoformat(),
            "message": (
                f"experience-v2 accrual outside admission window "
                f"[{admission_open.isoformat()}Z, {admission_close.isoformat()}Z): "
                f"now={utc_now.isoformat()}"
            ),
        }

    source_path = Path(source_root)
    tech_path = Path(technicals_v2_root)

    # Load + validate registration
    reg = load_registration_v2(repository_root)
    registration_id = reg["registration_id"]

    # Ensure install marker is written (deploy step writes it; if missing, abstain)
    check_activation(exp_root, session=session, clock=clock_fn)

    session_str = session.isoformat()

    # Check idempotency
    records_dir = _experience_v2_records_dir(exp_root)
    record_path = records_dir / f"{session_str}.json"
    if record_path.exists():
        existing = json.loads(record_path.read_bytes())
        return {
            "status": "already_present",
            "session": session_str,
            "registration_id": registration_id,
            "message": f"v2 record already exists for {session_str}",
            "record": existing,
        }

    # Read sealed bar
    sealed = _read_sealed_bar(source_path, session=session)
    if sealed is None:
        record = {
            "schema": EXPERIENCE_V2_RECORD_SCHEMA,
            "session": session_str,
            "registration_id": registration_id,
            "disposition": "abstained",
            "reason": "no_opportunity_eligible_sealed_bar",
            "recorded_at": now.isoformat().replace("+00:00", "Z"),
        }
        _write_create_once_v2(record_path, record, label=f"exp-v2 abstain {session_str}")
        _advance_head_v2(exp_root, session_str, registration_id, record)
        return {
            "status": "abstained",
            "session": session_str,
            "registration_id": registration_id,
            "message": f"no sealed bar for {session_str}",
        }

    # Read technicals
    tech_capture = _read_technical_capture(tech_path, session=session)
    if tech_capture is None:
        record = {
            "schema": EXPERIENCE_V2_RECORD_SCHEMA,
            "session": session_str,
            "registration_id": registration_id,
            "disposition": "abstained",
            "reason": "no_technicals_v2_capture",
            "recorded_at": now.isoformat().replace("+00:00", "Z"),
        }
        _write_create_once_v2(record_path, record, label=f"exp-v2 abstain-tech {session_str}")
        _advance_head_v2(exp_root, session_str, registration_id, record)
        return {
            "status": "abstained",
            "session": session_str,
            "registration_id": registration_id,
            "message": f"no technicals-v2 capture for {session_str}",
        }

    feature_obj = tech_capture.get("feature_object", {})
    close_ratio = feature_obj.get("state", {}).get("price", {}).get(
        "raw_close_ratio_20_sessions"
    )

    # M6: abstain if lookback is incomplete (close_ratio is None).
    # Do NOT set disposition: admitted with a null ratio.
    if close_ratio is None:
        record = {
            "schema": EXPERIENCE_V2_RECORD_SCHEMA,
            "session": session_str,
            "registration_id": registration_id,
            "disposition": "abstained",
            "reason": "lookback_incomplete",
            "recorded_at": now.isoformat().replace("+00:00", "Z"),
        }
        _write_create_once_v2(record_path, record, label=f"exp-v2 abstain-lookback {session_str}")
        _advance_head_v2(exp_root, session_str, registration_id, record)
        return {
            "status": "abstained",
            "session": session_str,
            "registration_id": registration_id,
            "message": f"lookback incomplete for {session_str}: raw_close_ratio_20_sessions is None",
        }

    record = {
        "schema": EXPERIENCE_V2_RECORD_SCHEMA,
        "session": session_str,
        "registration_id": registration_id,
        "disposition": "admitted",
        "source_generation_id": sealed["source_generation_id"],
        "technical_capture_id": tech_capture.get("capture_id"),
        "feature": {
            "session": session_str,
            "profile": "market_memory.private.spy_experience_accrual.v2",
            "ticker": "SPY",
            "regular_session_close_authenticated": False,
            "price_basis": "unadjusted_daily_aggregate_sealed_rest_bar",
            "price_raw_close_ratio_20_sessions": close_ratio,
        },
        "recorded_at": now.isoformat().replace("+00:00", "Z"),
    }

    _write_create_once_v2(record_path, record, label=f"exp-v2 {session_str}")
    _advance_head_v2(exp_root, session_str, registration_id, record)

    return {
        "status": "admitted",
        "session": session_str,
        "registration_id": registration_id,
        "message": f"v2 admitted for {session_str}",
        "feature": record["feature"],
    }


def _advance_head_v2(
    exp_root: Path,
    session_str: str,
    registration_id: str,
    record: dict[str, Any],
) -> None:
    exp_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    head = {
        "schema": EXPERIENCE_V2_HEAD_SCHEMA,
        "registration_id": registration_id,
        "latest_session": session_str,
        "latest_disposition": record.get("disposition"),
    }
    _write_head_v2(exp_root, head)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Accrue experience-v2 from sealed REST source + technicals-v2"
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_REPO,
        help="Repository root (default: %(default)s)",
    )
    parser.add_argument(
        "--experience-root",
        type=Path,
        default=DEFAULT_EXPERIENCE_V2_ROOT,
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
    )
    parser.add_argument(
        "--technicals-v2-root",
        type=Path,
        default=DEFAULT_TECHNICALS_V2_ROOT,
    )
    parser.add_argument(
        "--session",
        type=date.fromisoformat,
        default=None,
    )
    parser.add_argument(
        "--write-install-marker",
        action="store_true",
        help="Write the v2 install marker (deploy step)",
    )
    return parser.parse_args(argv)


def _main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv)

    if args.write_install_marker:
        exp_root = validate_experience_v2_store_root(args.experience_root)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _write_install_marker(exp_root, now)
        log.info("v2 install marker written: %s", now)
        return 0

    try:
        result = accrue_spy_experience_v2(
            repository_root=args.repository_root,
            experience_root=args.experience_root,
            source_root=args.source_root,
            technicals_v2_root=args.technicals_v2_root,
            session=args.session,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ExperienceV2ActivationError as exc:
        log.warning("v2 activation check failed (abstaining): %s", exc)
        print(json.dumps({"status": "abstained", "reason": str(exc)}, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("v2 accrual failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
