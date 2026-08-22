"""Keyless SPY REST technical projection for Market Memory W2C M0D v2.

This is the sole W2C M0D v2 technical projector.  It reads ONLY the sealed
REST daily bar from sources-spy-rest-v1, computes the close ratio over the
most recent 20 sessions, and writes to technicals-v2.

Profile: market_memory.private.spy_rth_price_fullday_activity_daily_aggregate.v2

Isolation contracts:
- Keyless: no MASSIVE_API_KEY, POLYGON_API_KEY, or any credential
- Does NOT read public R2, technicals-v1, or CPI sources
- Does NOT write technicals-v1 (InaccessiblePaths in the service unit)
- Reads only from sources-spy-rest-v1 (already-sealed evidence)

Freeze:
- O/H/L/C = XNYS regular-session (from sealed bar)
- V/n = provider full-market-day activity (from sealed bar)
- regular_session_close_authenticated = true
- feature key = price.raw_close_ratio_20_sessions

Time: projected around 04:07Z after seal closes at 04:05Z.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import logging
import math
import os
import re
import stat
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4
import sys

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# V2 profile constants
# ---------------------------------------------------------------------------

STORE_PROFILE_V2 = (
    "market_memory.private.spy_rth_price_fullday_activity_daily_aggregate.v2"
)
CAPTURE_RECEIPT_SCHEMA_V2 = (
    "market_memory.technicals_actual_output_capture_receipt.spy_rest.v2"
)
STORE_SCHEMA_V2 = "market_memory.technicals_actual_output_store.spy_rest.v2"
GENERATION_SCHEMA_V2 = "market_memory.actual_output_store_generation.spy_rest.v2"
HEAD_SCHEMA_V2 = "market_memory.actual_output_store_head.spy_rest.v2"

DEFAULT_TECHNICALS_V2_ROOT = Path(
    "/var/lib/macro-market-memory/state/technicals-v2"
)
DEFAULT_SOURCE_ROOT = Path(
    "/var/lib/macro-market-memory/state/sources-spy-rest-v1"
)

# Leaf name guards
_TECHNICALS_V2_LEAF = "technicals-v2"
_SOURCE_SPY_LEAF = "sources-spy-rest-v1"

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_SESSION = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

_MAX_STORE_BYTES = 64 * 1024
_MAX_CAPTURE_BYTES = 256 * 1024
_MAX_HEAD_BYTES = 16 * 1024
_MAX_GENERATION_BYTES = 4 * 1024 * 1024
_MAX_GENERATION_CAPTURES = 4_096


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TechnicalsV2Error(RuntimeError):
    """Base error for technicals-v2 projector."""


class TechnicalsV2SourceError(TechnicalsV2Error):
    """The sealed REST source is missing or invalid."""


class TechnicalsV2StoreError(TechnicalsV2Error):
    """The technicals-v2 store cannot be written."""


# ---------------------------------------------------------------------------
# Store root guards
# ---------------------------------------------------------------------------


def validate_technicals_v2_store_root(root: str | Path) -> Path:
    """Validate root ends in technicals-v2."""
    supplied = Path(root).expanduser()
    if supplied.is_symlink():
        raise TechnicalsV2StoreError("technicals-v2 root is a symlink")
    candidate = supplied.resolve()
    if candidate.name != _TECHNICALS_V2_LEAF:
        raise TechnicalsV2StoreError(
            f"technicals-v2 root must end in {_TECHNICALS_V2_LEAF!r}, "
            f"got {candidate.name!r}"
        )
    # Refuse v1 root
    if "technicals-v1" in str(candidate):
        raise TechnicalsV2StoreError(
            "technicals-v2 projector refuses to write technicals-v1 root"
        )
    return candidate


def validate_spy_rest_source_root(root: str | Path) -> Path:
    """Validate root ends in sources-spy-rest-v1."""
    supplied = Path(root).expanduser()
    if supplied.is_symlink():
        raise TechnicalsV2SourceError("SPY REST source root is a symlink")
    candidate = supplied.resolve()
    if candidate.name != _SOURCE_SPY_LEAF:
        raise TechnicalsV2SourceError(
            f"SPY REST source root must end in {_SOURCE_SPY_LEAF!r}, "
            f"got {candidate.name!r}"
        )
    return candidate


# ---------------------------------------------------------------------------
# Canonical JSON helpers
# ---------------------------------------------------------------------------


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_id(prefix: str, value: dict[str, Any], *, field: str) -> str:
    core = copy.deepcopy(value)
    core[field] = ""
    return prefix + sha256(_canonical_bytes(core)).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Read sealed SPY REST bar
# ---------------------------------------------------------------------------


def _read_sealed_bar_for_session(
    source_root: Path,
    *,
    session: date,
) -> dict[str, Any] | None:
    """Read the most recent sealed SPY REST bar for session from the store.

    Returns the bar dict (results[0]) or None if not found.
    """
    from engine.neuralweb.market_memory_sources_spy import (  # noqa: PLC0415
        SPY_FAMILY,
        _validate_spy_rest_receipt,
        _load_store_state,
        _read_receipt_copies_by_validate,
        _read_store_object,
        _object_path,
        DEFAULT_STORE_ROOT,
        _MAX_OBJECT_BYTES,
    )
    from engine.neuralweb.market_memory_source_kernel import (  # noqa: PLC0415
        _load_store_state as kernel_load_state,
        SourceNotFound,
        SourceStoreError,
    )
    from engine.neuralweb import market_memory as _mm  # noqa: PLC0415

    # Check that the store manifest exists
    from engine.neuralweb.market_memory_source_kernel import (  # noqa: PLC0415
        _store_manifest_path,
    )
    if not _store_manifest_path(source_root).exists():
        return None

    try:
        state = kernel_load_state(
            source_root, family=SPY_FAMILY, authority=dict(_mm.AUTHORITY)
        )
    except (SourceStoreError, SourceNotFound, Exception):
        return None

    session_str = session.isoformat()
    # Iterate receipts looking for this session
    for entry in reversed(state.generation["receipts"]):
        try:
            receipt, _ = _read_receipt_copies_by_validate(
                source_root,
                entry,
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
                _object_path(source_root, receipt["artifact_sha256"]),
                limit=_MAX_OBJECT_BYTES,
                label="SPY REST source object",
            )
        except Exception:  # noqa: BLE001
            continue
        results = artifact.get("results", [])
        lookback = artifact.get("lookback_closes_20")
        if results:
            return {"bar": results[0], "session": session_str, "lookback": lookback}
    return None


# ---------------------------------------------------------------------------
# Close ratio computation
# ---------------------------------------------------------------------------


def _compute_close_ratio_20(
    current_close: float,
    lookback: list[dict[str, Any]] | None,
) -> float | None:
    """Compute current_close / closes[n-1] (the close 20 sessions back).

    Returns None if lookback is unavailable or too short.
    """
    if not lookback or len(lookback) < 20:
        return None
    anchor_close = None
    # lookback is most-recent-first; take index 19 for "20 sessions back"
    row = lookback[19] if len(lookback) > 19 else lookback[-1]
    anchor_close = row.get("close")
    if anchor_close is None:
        return None
    try:
        anchor = float(anchor_close)
        if not math.isfinite(anchor) or anchor <= 0:
            return None
        current = float(current_close)
        if not math.isfinite(current) or current <= 0:
            return None
        return current / anchor
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Store IO helpers
# ---------------------------------------------------------------------------


def _mkdir_v2(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise TechnicalsV2StoreError(
            f"cannot create technicals-v2 directory: {exc}"
        ) from exc


def _write_json_v2(path: Path, value: Any, *, label: str) -> None:
    body = _canonical_bytes(value)
    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    _mkdir_v2(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(tmp, flags, 0o600)
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(tmp, path, follow_symlinks=False)
        except FileExistsError:
            pass  # idempotent
    except (TechnicalsV2StoreError, TechnicalsV2SourceError):
        raise
    except OSError as exc:
        raise TechnicalsV2StoreError(f"cannot write {label}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_path_v2(root: Path, *parts: str) -> Path:
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise TechnicalsV2StoreError("technicals-v2 path is a symlink")
    return cursor


def _store_head_path(root: Path) -> Path:
    return _safe_path_v2(root, "TECH_HEAD.json")


def _generation_path_v2(root: Path, generation_id: str) -> Path:
    digest = generation_id.removeprefix("mmtechv2gen_")
    return _safe_path_v2(root, "generations", digest[:2], f"{generation_id}.json")


def _capture_path_v2(root: Path, capture_id: str) -> Path:
    digest = capture_id.removeprefix("mmtechv2cap_")
    return _safe_path_v2(root, "captures", digest[:2], f"{capture_id}.json")


# ---------------------------------------------------------------------------
# Store manifest
# ---------------------------------------------------------------------------


def _store_manifest_path_v2(root: Path) -> Path:
    return _safe_path_v2(root, "TECH_STORE.json")


def _new_store_manifest_v2() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": STORE_SCHEMA_V2,
        "store_id": "",
        "profile": STORE_PROFILE_V2,
        "nonce": uuid4().hex,
    }
    manifest["store_id"] = _content_id("mmtechv2store_", manifest, field="store_id")
    return manifest


def _ensure_store_v2(root: Path) -> dict[str, Any]:
    _mkdir_v2(root)
    manifest_path = _store_manifest_path_v2(root)
    if manifest_path.exists():
        body = manifest_path.read_bytes()
        manifest = json.loads(body)
        if manifest.get("schema") != STORE_SCHEMA_V2:
            raise TechnicalsV2StoreError("technicals-v2 store schema mismatch")
        return manifest
    manifest = _new_store_manifest_v2()
    _write_json_v2(manifest_path, manifest, label="technicals-v2 store manifest")
    return manifest


# ---------------------------------------------------------------------------
# Generation management
# ---------------------------------------------------------------------------


def _load_head_v2(root: Path) -> dict[str, Any] | None:
    head_path = _store_head_path(root)
    if not head_path.exists():
        return None
    try:
        return json.loads(head_path.read_bytes())
    except Exception:  # noqa: BLE001
        return None


def _write_head_v2(root: Path, head: dict[str, Any]) -> None:
    body = _canonical_bytes(head)
    path = _store_head_path(root)
    tmp = root / f".TECH_HEAD.tmp.{os.getpid()}.{uuid4().hex}"
    descriptor = None
    try:
        descriptor = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(tmp, path)
    except OSError as exc:
        raise TechnicalsV2StoreError("cannot advance technicals-v2 HEAD") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Capture receipt
# ---------------------------------------------------------------------------


def _build_capture_receipt_v2(
    *,
    store_id: str,
    session: date,
    bar: dict[str, Any],
    close_ratio_20: float | None,
    captured_at: str,
    source_generation_id: str,
) -> dict[str, Any]:
    o = bar.get("o")
    h = bar.get("h")
    l = bar.get("l")
    c = bar.get("c")
    v = bar.get("v")
    n = bar.get("n")
    receipt: dict[str, Any] = {
        "schema": CAPTURE_RECEIPT_SCHEMA_V2,
        "capture_id": "",
        "store_id": store_id,
        "profile": STORE_PROFILE_V2,
        "session": session.isoformat(),
        "captured_at": captured_at,
        "source_generation_id": source_generation_id,
        "feature_object": {
            "session": session.isoformat(),
            "profile": STORE_PROFILE_V2,
            "ticker": "SPY",
            "regular_session_close_authenticated": False,
            "price_basis": "unadjusted_daily_aggregate_sealed_rest_bar",
            "state": {
                "open": o,
                "high": h,
                "low": l,
                "end_close": c,
                "volume": v,
                "trade_count": n,
                "price": {
                    "raw_close_ratio_20_sessions": close_ratio_20,
                },
            },
        },
    }
    receipt["capture_id"] = _content_id("mmtechv2cap_", receipt, field="capture_id")
    return receipt


# ---------------------------------------------------------------------------
# Main capture function
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TechnicalsV2CaptureResult:
    session: date
    capture_id: str
    generation_id: str
    created: bool
    close_ratio_20: float | None
    source_generation_id: str


def capture_technicals_v2(
    *,
    source_root: str | Path,
    store_root: str | Path,
    session: date | None = None,
    clock: Any = None,
) -> TechnicalsV2CaptureResult:
    """Read sealed REST bar and write one technicals-v2 capture.

    Idempotent: a second call for the same session returns the existing capture
    with created=False.
    """
    clock_fn = clock or _utc_now

    validated_source = validate_spy_rest_source_root(source_root)
    validated_store = validate_technicals_v2_store_root(store_root)

    # Determine session (B2): timers fire at 04:07Z on D+1; use derive_morning_session.
    if session is None:
        now = clock_fn()
        from engine.neuralweb.market_memory_sources_spy import derive_morning_session  # noqa: PLC0415
        derived = derive_morning_session(now)
        if derived is None:
            raise TechnicalsV2SourceError(
                f"cannot derive session from current time {now.isoformat()} "
                "(before 04:05Z or T-1 is not an XNYS session); "
                "pass session= explicitly"
            )
        session = derived

    session_str = session.isoformat()

    # Read the sealed bar
    sealed_data = _read_sealed_bar_for_session(validated_source, session=session)
    if sealed_data is None:
        raise TechnicalsV2SourceError(
            f"no opportunity-eligible sealed bar for session {session_str} "
            f"in source root {validated_source}"
        )

    bar = sealed_data["bar"]
    lookback = sealed_data.get("lookback")

    close = bar.get("c")
    if close is None or not math.isfinite(float(close)):
        raise TechnicalsV2SourceError(
            f"sealed bar for {session_str} has invalid close: {close!r}"
        )

    close_ratio_20 = _compute_close_ratio_20(float(close), lookback)

    # Get source generation id
    from engine.neuralweb.market_memory_sources_spy import (  # noqa: PLC0415
        SPY_FAMILY,
        _load_store_state,
    )
    from engine.neuralweb.market_memory_source_kernel import (  # noqa: PLC0415
        _load_store_state as kernel_load_state,
    )
    from engine.neuralweb import market_memory as _mm  # noqa: PLC0415

    try:
        state = kernel_load_state(
            validated_source, family=SPY_FAMILY, authority=dict(_mm.AUTHORITY)
        )
        source_gen_id = state.generation["generation_id"]
    except Exception:  # noqa: BLE001
        source_gen_id = "unknown"

    captured_at = clock_fn().isoformat().replace("+00:00", "Z")

    # Write to store
    _mkdir_v2(validated_store)
    lock_path = _safe_path_v2(validated_store, ".writer.lock")
    lock_descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        manifest = _ensure_store_v2(validated_store)
        store_id = manifest["store_id"]

        # Check for existing capture with same session
        head = _load_head_v2(validated_store)
        if head is not None:
            gen_id = head.get("generation_id")
            if gen_id:
                try:
                    gen_path = _generation_path_v2(validated_store, gen_id)
                    if gen_path.exists():
                        gen = json.loads(gen_path.read_bytes())
                        for entry in gen.get("captures", []):
                            if entry.get("session") == session_str:
                                # Already captured
                                return TechnicalsV2CaptureResult(
                                    session=session,
                                    capture_id=entry["capture_id"],
                                    generation_id=gen_id,
                                    created=False,
                                    close_ratio_20=close_ratio_20,
                                    source_generation_id=source_gen_id,
                                )
                except Exception:  # noqa: BLE001
                    pass

        receipt = _build_capture_receipt_v2(
            store_id=store_id,
            session=session,
            bar=bar,
            close_ratio_20=close_ratio_20,
            captured_at=captured_at,
            source_generation_id=source_gen_id,
        )
        capture_id = receipt["capture_id"]

        # Write capture
        cap_path = _capture_path_v2(validated_store, capture_id)
        _write_json_v2(cap_path, receipt, label="technicals-v2 capture")

        # Build new generation
        prev_captures: list[dict[str, Any]] = []
        prev_gen_id = head.get("generation_id") if head else None
        if prev_gen_id:
            try:
                prev_gen_path = _generation_path_v2(validated_store, prev_gen_id)
                if prev_gen_path.exists():
                    prev_gen = json.loads(prev_gen_path.read_bytes())
                    prev_captures = list(prev_gen.get("captures", []))
            except Exception:  # noqa: BLE001
                pass

        if len(prev_captures) >= _MAX_GENERATION_CAPTURES:
            raise TechnicalsV2StoreError("technicals-v2 generation capacity exhausted")

        new_captures = prev_captures + [
            {"capture_id": capture_id, "session": session_str}
        ]
        generation: dict[str, Any] = {
            "schema": GENERATION_SCHEMA_V2,
            "generation_id": "",
            "store_id": store_id,
            "profile": STORE_PROFILE_V2,
            "previous_generation_id": prev_gen_id,
            "captures": sorted(new_captures, key=lambda r: r["capture_id"]),
        }
        generation["generation_id"] = _content_id(
            "mmtechv2gen_", generation, field="generation_id"
        )
        gen_id = generation["generation_id"]
        gen_body = _canonical_bytes(generation)

        gen_path = _generation_path_v2(validated_store, gen_id)
        _write_json_v2(gen_path, generation, label="technicals-v2 generation")

        new_head = {
            "schema": HEAD_SCHEMA_V2,
            "store_id": store_id,
            "generation_id": gen_id,
            "generation_sha256": sha256(gen_body).hexdigest(),
        }
        _write_head_v2(validated_store, new_head)

        return TechnicalsV2CaptureResult(
            session=session,
            capture_id=capture_id,
            generation_id=gen_id,
            created=True,
            close_ratio_20=close_ratio_20,
            source_generation_id=source_gen_id,
        )
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)


# ---------------------------------------------------------------------------
# Head reader for experience-v2 to consume
# ---------------------------------------------------------------------------


def read_technicals_v2_head(store_root: str | Path) -> dict[str, Any] | None:
    """Return the HEAD generation's capture list, or None."""
    validated = validate_technicals_v2_store_root(store_root)
    head = _load_head_v2(validated)
    if head is None:
        return None
    gen_id = head.get("generation_id")
    if not gen_id:
        return None
    gen_path = _generation_path_v2(validated, gen_id)
    if not gen_path.exists():
        return None
    gen = json.loads(gen_path.read_bytes())
    return gen


def read_latest_capture_for_session(
    store_root: str | Path, *, session: date
) -> dict[str, Any] | None:
    """Return the most recent capture receipt for session, or None."""
    validated = validate_technicals_v2_store_root(store_root)
    gen = read_technicals_v2_head(validated)
    if gen is None:
        return None
    session_str = session.isoformat()
    for entry in gen.get("captures", []):
        if entry.get("session") == session_str:
            cap_id = entry["capture_id"]
            cap_path = _capture_path_v2(validated, cap_id)
            if cap_path.exists():
                return json.loads(cap_path.read_bytes())
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture technicals-v2 from sealed REST source"
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="SPY REST source store root (default: %(default)s)",
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=DEFAULT_TECHNICALS_V2_ROOT,
        help="Technicals-v2 store root (default: %(default)s)",
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
        result = capture_technicals_v2(
            source_root=args.source_root,
            store_root=args.store_root,
            session=args.session,
        )
        receipt = {
            "schema": "market_memory.technicals_v2_capture_run.v1",
            "status": "created" if result.created else "already_present",
            "session": result.session.isoformat(),
            "capture_id": result.capture_id,
            "generation_id": result.generation_id,
            "close_ratio_20": result.close_ratio_20,
        }
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("technicals-v2 capture failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
