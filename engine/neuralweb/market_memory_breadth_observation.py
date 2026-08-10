"""Clock-free projection of the current US breadth actual output.

This is the W1B.3A source adapter, not a historical breadth database.  It binds
the current Git-owned ``breadth.parquet`` tip to the current Git-owned
constituent roster, canary identity configuration, and reviewed XNYS calendar
module.  Only the last breadth row is projected.  Earlier rows are never
promoted to operational point-in-time observations because the upstream file
is recomputed with today's constituent membership.

The projector deliberately has no wall clock.  ``observed_at`` and
``available_at`` belong to the private append-only store's first durable write,
which is a later W1B.3A boundary.  Source and snapshot IDs therefore remain
stable across retries and code-only commits: the source ID binds the frozen
profile, tip session, and four exact SHA-256 values; the snapshot ID binds only
that source occurrence, the frozen transform, and the semantic state.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, NoReturn

import pandas as pd
import pyarrow.parquet as pq
from pandas.api.types import is_float_dtype, is_integer_dtype, is_string_dtype

SOURCE_OBSERVATION_SCHEMA = "market_memory.breadth_source_observation.v1"
SNAPSHOT_SCHEMA = "market_memory.breadth_factors_snapshot.v1"
PROFILE = "sp500_current_membership_breadth.v1"
TRANSFORM_VERSION = "market_memory.breadth_factors_transform.v1"

_SOURCE_PATHS = {
    "breadth_actual_output": "data/breadth/breadth.parquet",
    "current_constituents": "data/breadth/constituents.parquet",
    "canary_identity_config": "config/market_memory_canary.v1.json",
    "xnys_calendar_module": "lib/nyse_calendar.py",
}
_SOURCE_ROLES = tuple(_SOURCE_PATHS)
_SOURCE_LIMITS = {
    "breadth_actual_output": 8 * 1024 * 1024,
    "current_constituents": 2 * 1024 * 1024,
    "canary_identity_config": 32 * 1024,
    "xnys_calendar_module": 256 * 1024,
}
_BREADTH_COLUMNS = (
    "n_members",
    "pct_above_50",
    "pct_above_200",
    "nh",
    "nl",
    "adv",
    "dec",
    "ad_line",
)
_BREADTH_INTEGER_COLUMNS = frozenset({"n_members", "nh", "nl", "adv", "dec", "ad_line"})
_CONSTITUENT_COLUMNS = ("name", "sector")
_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_GIT_OID = _COMMIT
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_SESSION = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_SNAPSHOT_ID = re.compile(r"mmsnap_[a-f0-9]{64}\Z")
_SOURCE_OBSERVATION_ID = re.compile(r"mmbreadthsrc_[a-f0-9]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,19}\Z")
_MAX_BREADTH_ROWS = 50_000
_MIN_BREADTH_ROWS = 1_000
_MIN_CONSTITUENTS = 400
_MAX_CONSTITUENTS = 600
_MIN_PRICED_COVERAGE = 0.90
_MAX_PARQUET_ROW_GROUPS = 32
_MAX_BREADTH_UNCOMPRESSED_BYTES = 8 * 1024 * 1024
_MAX_CONSTITUENTS_UNCOMPRESSED_BYTES = 2 * 1024 * 1024
_MAX_CONSTITUENT_NAME_BYTES = 512
_MAX_CONSTITUENT_SECTOR_BYTES = 128
_CALENDAR_MIN_YEAR = 1962
_CALENDAR_MAX_YEAR = 2100
_CALENDAR_SHA256_V1 = "7c9167fd416babb64c3067ae7e6237615011ad79e26d826e57005486496410ce"
_CANARY_CONFIG_SHA256_V1 = (
    "5e7823e48866b2c0828122b65f684ed5872c6816a6224f61e44db4c03d129b33"
)

_ONE_OFF_CLOSURES_V1 = frozenset(
    {
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2018, 12, 5),
        date(2025, 1, 9),
    }
)


def _authority_v1() -> dict[str, Any]:
    """Construct the frozen v1 authority without a mutable shared registry."""

    return {
        "tier": "display",
        "horizon_role": "context",
        "context_only": True,
        "proposal_weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "may_trade": False,
        "may_originate": False,
        "may_select_options_candidate": False,
        "may_execute": False,
        "may_write_options_episode": False,
        "may_append_outcome": False,
        "may_train_prophet": False,
    }


def _canary_config_v1() -> dict[str, Any]:
    """Construct the exact frozen v1 canary literal for each validation."""

    return {
        "schema": "market_memory.canary_identity_config.v1",
        "symbol": "SPY",
        "subject": {
            "canonical_key": "US:ETF:SPDR_SP_500_ETF_TRUST",
            "subject_id": (
                "mmsecurity_5fc37e8db34f74314b654c910ea8bacfa7de8b5d2d067f2e5421c9d5745ceb4c"
            ),
            "instrument_key": "US:ARCX:SPY:USD",
            "instrument_id": (
                "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f55f77198420959aadd8922d1045c3fea"
            ),
            "identity_version": (
                "mmidentityv_65ec5e55473e953b55fa2d146f40e8b56dfae2e68a3df7423405db1034d16903"
            ),
            "mic": "ARCX",
            "currency": "USD",
        },
        "universe": {
            "canonical_key": "US_MARKET_CONTEXT_CANARY",
            "universe_id": (
                "mmuniverse_5f6904b77722f506a8d1d6f283ef69678a1ec7df3b2c1fc25cc1a15a3a4e8e6a"
            ),
            "membership_status": "market_scope",
        },
        "calendar": {
            "canonical_key": "US_CASH_EQUITIES",
            "calendar_id": (
                "mmcalendar_a102c5367c17f9c0b4df3af5c2826824fc112935ec76e6d18d55833f53644e0c"
            ),
            "market_session": "XNYS_REGULAR",
            "rules_version": "lib.nyse_calendar.full_day_closures.v1",
            "coverage": "full_day_closures_only",
            "quality": {
                "status": "degraded",
                "flags": ["partial_coverage"],
                "staleness_seconds": 0,
                "imputed": False,
            },
        },
        "authority": _authority_v1(),
    }


_TEMPORAL_POLICY = {
    "current_tip_only": True,
    "historical_rows_operational": False,
    "availability_clock_owner": "private_breadth_store_first_durable_write",
    "projector_samples_clock": False,
}
_LIMITATIONS = {
    "current_membership_only": True,
    "current_membership_survivor_bias": True,
    "historical_constituent_point_in_time": False,
    "calendar_coverage": "full_day_closures_only",
    "calendar_partial_coverage": True,
    "ad_line_excluded": True,
}
_QUALITY = {
    "status": "degraded",
    "flags": ["partial_coverage"],
    "actual_output_source": True,
    "current_tip_only": True,
    "imputed": False,
    "training_eligible": False,
    "promotion_eligible": False,
}


class MarketMemoryBreadthObservationError(ValueError):
    """The current breadth source or its clock-free projection is inadmissible."""


@dataclass(frozen=True)
class PinnedBreadthInputs:
    """Exact immutable source bodies read from one pinned repository tip."""

    pinned_commit: str
    breadth_body: bytes
    constituents_body: bytes
    canary_config_body: bytes
    calendar_module_body: bytes
    git_blob_oids: tuple[tuple[str, str], ...]

    def detached(self) -> PinnedBreadthInputs:
        """Return a defensive copy for a caller-owned validation boundary."""

        return copy.deepcopy(self)


@dataclass(frozen=True)
class BreadthSnapshotBundle:
    """Exact raw inputs plus canonical source and feature-object bytes."""

    pinned_inputs: PinnedBreadthInputs
    source_observation: dict[str, Any]
    source_observation_bytes: bytes
    feature_object: dict[str, Any]
    feature_object_bytes: bytes

    def detached(self) -> BreadthSnapshotBundle:
        """Return a defensive copy so consumers cannot mutate validated objects."""

        return copy.deepcopy(self)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryBreadthObservationError(
            "breadth projection must be finite canonical JSON"
        ) from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _require_exact_bytes(value: object, *, role: str) -> bytes:
    if type(value) is not bytes:
        raise MarketMemoryBreadthObservationError(
            f"{role} must be exact immutable bytes"
        )
    limit = _SOURCE_LIMITS[role]
    if not value or len(value) > limit:
        raise MarketMemoryBreadthObservationError(
            f"{role} is empty or exceeds its byte bound"
        )
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON token {value}")


def _strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise MarketMemoryBreadthObservationError(
            f"{label} must be strict UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise MarketMemoryBreadthObservationError(f"{label} must be a JSON object")
    return payload


def _git(root: Path, *args: str, text: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=text,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MarketMemoryBreadthObservationError(
            "cannot bind breadth intake to Git"
        ) from exc
    return result.stdout


def _safe_stable_read(path: Path, *, role: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise MarketMemoryBreadthObservationError(f"{role} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MarketMemoryBreadthObservationError(
            f"{role} must be a regular non-symlink"
        )
    limit = _SOURCE_LIMITS[role]
    if metadata.st_size <= 0 or metadata.st_size > limit:
        raise MarketMemoryBreadthObservationError(
            f"{role} is empty or exceeds its byte bound"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryBreadthObservationError(
            f"{role} could not be opened safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        path_after = path.lstat()
    except OSError as exc:
        raise MarketMemoryBreadthObservationError(
            f"{role} changed during its stable read"
        ) from exc
    finally:
        os.close(descriptor)
    body = b"".join(chunks)
    identities = {
        (
            item.st_dev,
            item.st_ino,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
            stat.S_IFMT(item.st_mode),
        )
        for item in (before, after, path_after)
    }
    if (
        len(identities) != 1
        or not stat.S_ISREG(after.st_mode)
        or len(body) != after.st_size
        or len(body) > limit
    ):
        raise MarketMemoryBreadthObservationError(
            f"{role} changed during its stable read"
        )
    return body


def _full_head_commit(root: Path) -> str:
    value = str(_git(root, "rev-parse", "--verify", "HEAD^{commit}", text=True)).strip()
    if not _COMMIT.fullmatch(value):
        raise MarketMemoryBreadthObservationError("repository HEAD is malformed")
    return value


def read_pinned_breadth_inputs(
    repository_root: str | Path,
    *,
    pinned_commit: str,
) -> PinnedBreadthInputs:
    """Stable-read four worktree files and prove exact ownership by ``HEAD``.

    The explicit full commit prevents a caller from racing the source against a
    moving branch name.  A dirty replacement, symlink, filter-transformed file,
    detached older commit, or HEAD change during the read fails closed.
    """

    if type(pinned_commit) is not str or not _COMMIT.fullmatch(pinned_commit):
        raise MarketMemoryBreadthObservationError(
            "pinned_commit must be one full lowercase Git object ID"
        )
    root = Path(repository_root).expanduser().resolve()
    if not root.is_dir():
        raise MarketMemoryBreadthObservationError("repository root is unavailable")
    top = str(_git(root, "rev-parse", "--show-toplevel", text=True)).strip()
    if Path(top).resolve() != root:
        raise MarketMemoryBreadthObservationError(
            "repository root must be the exact worktree top level"
        )
    if _full_head_commit(root) != pinned_commit:
        raise MarketMemoryBreadthObservationError(
            "pinned_commit is not the current repository tip"
        )

    bodies: dict[str, bytes] = {}
    blob_oids: list[tuple[str, str]] = []
    for role in _SOURCE_ROLES:
        repo_path = _SOURCE_PATHS[role]
        body = _safe_stable_read(root / repo_path, role=role)
        tracked = _git(root, "show", f"{pinned_commit}:{repo_path}")
        if type(tracked) is not bytes or body != tracked:
            raise MarketMemoryBreadthObservationError(
                f"{role} bytes differ from the pinned Git object"
            )
        object_type = str(
            _git(root, "cat-file", "-t", f"{pinned_commit}:{repo_path}", text=True)
        ).strip()
        blob_oid = str(
            _git(root, "rev-parse", f"{pinned_commit}:{repo_path}", text=True)
        ).strip()
        if object_type != "blob" or not _GIT_OID.fullmatch(blob_oid):
            raise MarketMemoryBreadthObservationError(
                f"{role} is not one canonical Git blob"
            )
        bodies[role] = body
        blob_oids.append((role, blob_oid))

    if _full_head_commit(root) != pinned_commit:
        raise MarketMemoryBreadthObservationError(
            "repository HEAD changed during breadth intake"
        )
    return PinnedBreadthInputs(
        pinned_commit=pinned_commit,
        breadth_body=bodies["breadth_actual_output"],
        constituents_body=bodies["current_constituents"],
        canary_config_body=bodies["canary_identity_config"],
        calendar_module_body=bodies["xnys_calendar_module"],
        git_blob_oids=tuple(blob_oids),
    )


def _git_blob_oid(body: bytes, *, hexadecimal_length: int) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    if hexadecimal_length == 40:
        # This reproduces Git's object identity; it is not a security decision.
        return hashlib.sha1(framed).hexdigest()
    if hexadecimal_length == 64:
        return hashlib.sha256(framed).hexdigest()
    raise MarketMemoryBreadthObservationError("unsupported Git object format")


def _validated_inputs(value: PinnedBreadthInputs) -> PinnedBreadthInputs:
    if type(value) is not PinnedBreadthInputs:
        raise MarketMemoryBreadthObservationError(
            "breadth inputs must use the frozen PinnedBreadthInputs boundary"
        )
    if type(value.pinned_commit) is not str or not _COMMIT.fullmatch(
        value.pinned_commit
    ):
        raise MarketMemoryBreadthObservationError("pinned Git commit is malformed")
    bodies = {
        "breadth_actual_output": _require_exact_bytes(
            value.breadth_body, role="breadth_actual_output"
        ),
        "current_constituents": _require_exact_bytes(
            value.constituents_body, role="current_constituents"
        ),
        "canary_identity_config": _require_exact_bytes(
            value.canary_config_body, role="canary_identity_config"
        ),
        "xnys_calendar_module": _require_exact_bytes(
            value.calendar_module_body, role="xnys_calendar_module"
        ),
    }
    if type(value.git_blob_oids) is not tuple or any(
        type(item) is not tuple or len(item) != 2 for item in value.git_blob_oids
    ):
        raise MarketMemoryBreadthObservationError(
            "Git blob references must be exact role/OID pairs"
        )
    if tuple(item[0] for item in value.git_blob_oids) != _SOURCE_ROLES:
        raise MarketMemoryBreadthObservationError(
            "Git blob references are incomplete or out of order"
        )
    if len({role for role, _ in value.git_blob_oids}) != len(_SOURCE_ROLES):
        raise MarketMemoryBreadthObservationError("Git blob roles are duplicated")
    for role, oid in value.git_blob_oids:
        if type(role) is not str or type(oid) is not str or not _GIT_OID.fullmatch(oid):
            raise MarketMemoryBreadthObservationError("Git blob reference is malformed")
        expected = _git_blob_oid(bodies[role], hexadecimal_length=len(oid))
        if oid != expected:
            raise MarketMemoryBreadthObservationError(
                f"{role} Git blob ID does not bind its exact bytes"
            )
    return value.detached()


def _validate_canary_config(body: bytes) -> dict[str, Any]:
    if _sha256(body) != _CANARY_CONFIG_SHA256_V1:
        raise MarketMemoryBreadthObservationError(
            "canary identity config does not match the frozen v1 SHA-256"
        )
    raw = _strict_json_object(body, label="canary identity config")
    expected = _canary_config_v1()
    if raw != expected:
        raise MarketMemoryBreadthObservationError(
            "canary identity config does not match the frozen v1 literal"
        )
    return expected


def _validate_calendar_module(body: bytes) -> None:
    if _sha256(body) != _CALENDAR_SHA256_V1:
        raise MarketMemoryBreadthObservationError(
            "XNYS calendar module does not match the frozen v1 SHA-256"
        )


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed_fixed_holiday(value: date) -> date:
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def _frozen_v1_holidays(year: int) -> frozenset[date]:
    if type(year) is not int or not _CALENDAR_MIN_YEAR <= year <= _CALENDAR_MAX_YEAR:
        raise MarketMemoryBreadthObservationError(
            "frozen XNYS calendar supports only years 1962 through 2100"
        )
    holidays: set[date] = set()
    new_year = date(year, 1, 1)
    if new_year.weekday() == 6:
        holidays.add(new_year + timedelta(days=1))
    elif new_year.weekday() != 5:
        holidays.add(new_year)
    if year >= 1998:
        holidays.add(_nth_weekday(year, 1, 0, 3))
    holidays.add(_nth_weekday(year, 2, 0, 3))
    holidays.add(_easter(year) - timedelta(days=2))
    holidays.add(_last_weekday(year, 5, 0))
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(date(year, 6, 19)))
    holidays.add(_observed_fixed_holiday(date(year, 7, 4)))
    holidays.add(_nth_weekday(year, 9, 0, 1))
    holidays.add(_nth_weekday(year, 11, 3, 4))
    holidays.add(_observed_fixed_holiday(date(year, 12, 25)))
    return frozenset(item for item in holidays if item.year == year)


def is_frozen_v1_xnys_session(value: date) -> bool:
    """Return whether ``value`` is a session under the frozen v1 rules."""

    if type(value) is not date:
        raise MarketMemoryBreadthObservationError(
            "frozen XNYS session evaluator requires an exact date"
        )
    if not _CALENDAR_MIN_YEAR <= value.year <= _CALENDAR_MAX_YEAR:
        raise MarketMemoryBreadthObservationError(
            "frozen XNYS calendar supports only years 1962 through 2100"
        )
    return (
        value.weekday() < 5
        and value not in _frozen_v1_holidays(value.year)
        and value not in _ONE_OFF_CLOSURES_V1
    )


def last_frozen_v1_xnys_session_on_or_before(value: date) -> date:
    """Return the latest frozen-v1 session on/before one supported date."""

    if type(value) is not date:
        raise MarketMemoryBreadthObservationError(
            "frozen XNYS session evaluator requires an exact date"
        )
    if not _CALENDAR_MIN_YEAR <= value.year <= _CALENDAR_MAX_YEAR:
        raise MarketMemoryBreadthObservationError(
            "frozen XNYS calendar supports only years 1962 through 2100"
        )
    candidate = value
    for _ in range(31):
        if candidate.year < _CALENDAR_MIN_YEAR:
            break
        if is_frozen_v1_xnys_session(candidate):
            return candidate
        candidate -= timedelta(days=1)
    raise MarketMemoryBreadthObservationError(
        "no frozen XNYS session exists in the supported prior 31 days"
    )


def _read_parquet(
    body: bytes,
    *,
    label: str,
    expected_physical_columns: tuple[str, ...],
    minimum_rows: int,
    maximum_rows: int,
    maximum_uncompressed_bytes: int,
) -> pd.DataFrame:
    """Preflight bounded metadata before materializing an Arrow table."""

    try:
        parquet_file = pq.ParquetFile(io.BytesIO(body))
        metadata = parquet_file.metadata
    except Exception as exc:  # pyarrow exposes several backend-specific errors
        raise MarketMemoryBreadthObservationError(
            f"{label} does not have readable bounded parquet metadata"
        ) from exc
    if metadata is None:
        raise MarketMemoryBreadthObservationError(f"{label} has no parquet metadata")
    if not minimum_rows <= metadata.num_rows <= maximum_rows:
        raise MarketMemoryBreadthObservationError(
            f"{label} metadata row count is outside its frozen bound"
        )
    if metadata.num_columns != len(expected_physical_columns):
        raise MarketMemoryBreadthObservationError(
            f"{label} metadata column count is not canonical"
        )
    if not 1 <= metadata.num_row_groups <= _MAX_PARQUET_ROW_GROUPS:
        raise MarketMemoryBreadthObservationError(
            f"{label} metadata row-group count is outside its frozen bound"
        )
    if tuple(parquet_file.schema_arrow.names) != expected_physical_columns:
        raise MarketMemoryBreadthObservationError(
            f"{label} metadata columns or order are not canonical"
        )
    total_uncompressed_bytes = 0
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        if row_group.num_rows < 0 or row_group.num_columns != metadata.num_columns:
            raise MarketMemoryBreadthObservationError(
                f"{label} row-group metadata is malformed"
            )
        for column_index in range(row_group.num_columns):
            size = row_group.column(column_index).total_uncompressed_size
            if type(size) is not int or size < 0:
                raise MarketMemoryBreadthObservationError(
                    f"{label} uncompressed column size is malformed"
                )
            total_uncompressed_bytes += size
            if total_uncompressed_bytes > maximum_uncompressed_bytes:
                raise MarketMemoryBreadthObservationError(
                    f"{label} exceeds its total uncompressed byte bound"
                )
    try:
        table = parquet_file.read(use_threads=False)
        if (
            table.num_rows != metadata.num_rows
            or table.num_columns != metadata.num_columns
        ):
            raise MarketMemoryBreadthObservationError(
                f"{label} materialized shape differs from its metadata"
            )
        frame = table.to_pandas()
    except MarketMemoryBreadthObservationError:
        raise
    except Exception as exc:  # pyarrow/pandas expose backend-specific failures
        raise MarketMemoryBreadthObservationError(
            f"{label} could not be safely materialized"
        ) from exc
    if not isinstance(frame, pd.DataFrame):
        raise MarketMemoryBreadthObservationError(f"{label} is not tabular")
    return frame


def _validated_breadth_tip(body: bytes) -> tuple[str, dict[str, int | float]]:
    frame = _read_parquet(
        body,
        label="breadth actual output",
        expected_physical_columns=(*_BREADTH_COLUMNS, "Date"),
        minimum_rows=_MIN_BREADTH_ROWS,
        maximum_rows=_MAX_BREADTH_ROWS,
        maximum_uncompressed_bytes=_MAX_BREADTH_UNCOMPRESSED_BYTES,
    )
    if not _MIN_BREADTH_ROWS <= len(frame) <= _MAX_BREADTH_ROWS:
        raise MarketMemoryBreadthObservationError(
            "breadth row count is outside the frozen operational bound"
        )
    if tuple(frame.columns) != _BREADTH_COLUMNS:
        raise MarketMemoryBreadthObservationError(
            "breadth parquet columns or order are not canonical"
        )
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.name != "Date":
        raise MarketMemoryBreadthObservationError(
            "breadth parquet requires the canonical Date index"
        )
    if (
        frame.index.tz is not None
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
        or (frame.index != frame.index.normalize()).any()
    ):
        raise MarketMemoryBreadthObservationError(
            "breadth session index is duplicated, unordered, zoned, or non-midnight"
        )
    for column in _BREADTH_COLUMNS:
        dtype = frame[column].dtype
        if column in _BREADTH_INTEGER_COLUMNS:
            valid_dtype = is_integer_dtype(dtype) and not isinstance(
                dtype, pd.BooleanDtype
            )
        else:
            valid_dtype = is_float_dtype(dtype)
        if not valid_dtype:
            raise MarketMemoryBreadthObservationError(
                f"breadth column {column} has a noncanonical dtype"
            )

    tip_timestamp = frame.index[-1]
    tip_date = tip_timestamp.date()
    if not is_frozen_v1_xnys_session(tip_date):
        raise MarketMemoryBreadthObservationError(
            "breadth tip is not an XNYS cash-equity session"
        )
    tip = frame.iloc[-1]
    values: dict[str, int | float] = {}
    for column in _BREADTH_COLUMNS:
        raw = tip[column]
        try:
            finite = math.isfinite(float(raw))
        except (TypeError, ValueError, OverflowError) as exc:
            raise MarketMemoryBreadthObservationError(
                f"breadth tip {column} is not numeric"
            ) from exc
        if not finite:
            raise MarketMemoryBreadthObservationError(
                f"breadth tip {column} is non-finite"
            )
        values[column] = int(raw) if column in _BREADTH_INTEGER_COLUMNS else float(raw)

    n_members = int(values["n_members"])
    if not _MIN_CONSTITUENTS <= n_members <= _MAX_CONSTITUENTS:
        raise MarketMemoryBreadthObservationError(
            "breadth tip priced-member count is implausible"
        )
    for column in ("pct_above_50", "pct_above_200"):
        if not 0.0 <= float(values[column]) <= 100.0:
            raise MarketMemoryBreadthObservationError(
                f"breadth tip {column} is outside percent bounds"
            )
    for column in ("nh", "nl", "adv", "dec"):
        if not 0 <= int(values[column]) <= n_members:
            raise MarketMemoryBreadthObservationError(
                f"breadth tip {column} exceeds member bounds"
            )
    if int(values["adv"]) + int(values["dec"]) > n_members:
        raise MarketMemoryBreadthObservationError(
            "breadth tip advancers and decliners exceed priced members"
        )
    return tip_date.isoformat(), values


def _validated_constituents(body: bytes) -> int:
    frame = _read_parquet(
        body,
        label="current constituents",
        expected_physical_columns=(*_CONSTITUENT_COLUMNS, "symbol"),
        minimum_rows=_MIN_CONSTITUENTS,
        maximum_rows=_MAX_CONSTITUENTS,
        maximum_uncompressed_bytes=_MAX_CONSTITUENTS_UNCOMPRESSED_BYTES,
    )
    if not _MIN_CONSTITUENTS <= len(frame) <= _MAX_CONSTITUENTS:
        raise MarketMemoryBreadthObservationError(
            "current constituent count is outside the frozen bound"
        )
    if tuple(frame.columns) != _CONSTITUENT_COLUMNS:
        raise MarketMemoryBreadthObservationError(
            "current constituent columns or order are not canonical"
        )
    if frame.index.name != "symbol" or frame.index.has_duplicates:
        raise MarketMemoryBreadthObservationError(
            "current constituent symbol index is missing or duplicated"
        )
    if any(not is_string_dtype(frame[column].dtype) for column in frame.columns):
        raise MarketMemoryBreadthObservationError(
            "current constituent columns must remain strings"
        )
    if frame.isna().any(axis=None):
        raise MarketMemoryBreadthObservationError(
            "current constituent rows cannot contain nulls"
        )
    symbols = frame.index.tolist()
    if any(
        type(symbol) is not str or not _SYMBOL.fullmatch(symbol) for symbol in symbols
    ):
        raise MarketMemoryBreadthObservationError(
            "current constituent symbols are not canonical"
        )
    for column in _CONSTITUENT_COLUMNS:
        byte_limit = (
            _MAX_CONSTITUENT_NAME_BYTES
            if column == "name"
            else _MAX_CONSTITUENT_SECTOR_BYTES
        )
        for value in frame[column].tolist():
            if type(value) is not str or not value or value != value.strip():
                raise MarketMemoryBreadthObservationError(
                    f"current constituent {column} values are not exact text"
                )
            if len(value.encode("utf-8")) > byte_limit:
                raise MarketMemoryBreadthObservationError(
                    f"current constituent {column} exceeds its UTF-8 byte bound"
                )
    return len(frame)


def _artifact_refs(
    inputs: PinnedBreadthInputs,
) -> dict[str, dict[str, str | int]]:
    bodies = {
        "breadth_actual_output": inputs.breadth_body,
        "current_constituents": inputs.constituents_body,
        "canary_identity_config": inputs.canary_config_body,
        "xnys_calendar_module": inputs.calendar_module_body,
    }
    oids = dict(inputs.git_blob_oids)
    return {
        role: {
            "repo_path": _SOURCE_PATHS[role],
            "sha256": _sha256(bodies[role]),
            "bytes": len(bodies[role]),
            "git_blob_oid": oids[role],
        }
        for role in _SOURCE_ROLES
    }


def _source_observation_id(
    *, session: str, sources: Mapping[str, Mapping[str, Any]]
) -> str:
    core = {
        "profile": PROFILE,
        "session": session,
        "source_sha256": {role: sources[role]["sha256"] for role in _SOURCE_ROLES},
    }
    return "mmbreadthsrc_" + _sha256(_canonical_bytes(core))


def _snapshot_id(*, source_observation_id: str, state: Mapping[str, Any]) -> str:
    core = {
        "source_observation_id": source_observation_id,
        "transform_version": TRANSFORM_VERSION,
        "semantic_value": dict(state),
    }
    return "mmsnap_" + _sha256(_canonical_bytes(core))


def project_current_breadth_snapshot(
    inputs: PinnedBreadthInputs,
) -> BreadthSnapshotBundle:
    """Purely project the current breadth tip without sampling a clock."""

    checked = _validated_inputs(inputs)
    config = _validate_canary_config(checked.canary_config_body)
    _validate_calendar_module(checked.calendar_module_body)
    session, raw_tip = _validated_breadth_tip(checked.breadth_body)
    constituent_count = _validated_constituents(checked.constituents_body)
    n_members = int(raw_tip["n_members"])
    priced_member_coverage = n_members / constituent_count
    if not _MIN_PRICED_COVERAGE <= priced_member_coverage <= 1.0:
        raise MarketMemoryBreadthObservationError(
            "priced-member coverage is outside the frozen sane bound"
        )

    sources = _artifact_refs(checked)
    source_observation_id = _source_observation_id(session=session, sources=sources)
    source_observation = {
        "schema": SOURCE_OBSERVATION_SCHEMA,
        "source_observation_id": source_observation_id,
        "profile": PROFILE,
        "session": session,
        "sources": sources,
        "temporal_policy": copy.deepcopy(_TEMPORAL_POLICY),
        "limitations": copy.deepcopy(_LIMITATIONS),
        "authority": _authority_v1(),
    }
    source_observation_bytes = _canonical_bytes(source_observation)

    subject_config = config["subject"]
    state = {
        "n_members": n_members,
        "constituent_count": constituent_count,
        "priced_member_coverage": priced_member_coverage,
        "pct_above_50": float(raw_tip["pct_above_50"]),
        "pct_above_200": float(raw_tip["pct_above_200"]),
        "new_highs": int(raw_tip["nh"]),
        "new_lows": int(raw_tip["nl"]),
        "advancers": int(raw_tip["adv"]),
        "decliners": int(raw_tip["dec"]),
    }
    feature_object = {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_id": _snapshot_id(
            source_observation_id=source_observation_id,
            state=state,
        ),
        "source_observation_id": source_observation_id,
        "session": session,
        "transform_version": TRANSFORM_VERSION,
        "subject": {
            "symbol": config["symbol"],
            "subject_id": subject_config["subject_id"],
            "instrument_id": subject_config["instrument_id"],
            "identity_version": subject_config["identity_version"],
            "mic": subject_config["mic"],
            "currency": subject_config["currency"],
            "universe_id": config["universe"]["universe_id"],
            "calendar_id": config["calendar"]["calendar_id"],
            "market_session": config["calendar"]["market_session"],
        },
        "state": state,
        "quality": copy.deepcopy(_QUALITY),
        "limitations": copy.deepcopy(_LIMITATIONS),
        "authority": _authority_v1(),
    }
    feature_object_bytes = _canonical_bytes(feature_object)
    return BreadthSnapshotBundle(
        pinned_inputs=checked,
        source_observation=source_observation,
        source_observation_bytes=source_observation_bytes,
        feature_object=feature_object,
        feature_object_bytes=feature_object_bytes,
    )


def build_current_breadth_snapshot(
    repository_root: str | Path,
    *,
    pinned_commit: str,
) -> BreadthSnapshotBundle:
    """Read one exact repository tip and return its clock-free projection."""

    return project_current_breadth_snapshot(
        read_pinned_breadth_inputs(
            repository_root,
            pinned_commit=pinned_commit,
        )
    )


def validate_breadth_snapshot_bundle(
    value: BreadthSnapshotBundle,
) -> BreadthSnapshotBundle:
    """Revalidate detached raw/source/feature bytes without filesystem or Git.

    This is the consumer boundary used after a private store reloads raw CAS
    bodies.  Reprojection authenticates source hashes, Git-blob hashes, parquet
    semantics, IDs, and both exact canonical JSON bodies before any receipt can
    refer to the bundle.
    """

    if type(value) is not BreadthSnapshotBundle:
        raise MarketMemoryBreadthObservationError(
            "breadth snapshot must use the frozen bundle boundary"
        )
    if (
        type(value.source_observation) is not dict
        or type(value.feature_object) is not dict
    ):
        raise MarketMemoryBreadthObservationError(
            "breadth source and feature objects must be dictionaries"
        )
    if (
        type(value.source_observation_bytes) is not bytes
        or type(value.feature_object_bytes) is not bytes
    ):
        raise MarketMemoryBreadthObservationError(
            "breadth source and feature bodies must be exact immutable bytes"
        )
    if value.source_observation_bytes != _canonical_bytes(value.source_observation):
        raise MarketMemoryBreadthObservationError(
            "breadth source observation bytes are noncanonical or tampered"
        )
    if value.feature_object_bytes != _canonical_bytes(value.feature_object):
        raise MarketMemoryBreadthObservationError(
            "breadth feature object bytes are noncanonical or tampered"
        )
    rebuilt = project_current_breadth_snapshot(value.pinned_inputs)
    if (
        value.source_observation != rebuilt.source_observation
        or value.source_observation_bytes != rebuilt.source_observation_bytes
        or value.feature_object != rebuilt.feature_object
        or value.feature_object_bytes != rebuilt.feature_object_bytes
    ):
        raise MarketMemoryBreadthObservationError(
            "breadth bundle does not reproduce from its exact raw CAS bodies"
        )
    if not _SOURCE_OBSERVATION_ID.fullmatch(
        rebuilt.source_observation["source_observation_id"]
    ) or not _SNAPSHOT_ID.fullmatch(rebuilt.feature_object["snapshot_id"]):
        raise MarketMemoryBreadthObservationError("breadth object IDs are malformed")
    return rebuilt.detached()


__all__ = [
    "PROFILE",
    "SNAPSHOT_SCHEMA",
    "SOURCE_OBSERVATION_SCHEMA",
    "TRANSFORM_VERSION",
    "BreadthSnapshotBundle",
    "MarketMemoryBreadthObservationError",
    "PinnedBreadthInputs",
    "build_current_breadth_snapshot",
    "is_frozen_v1_xnys_session",
    "last_frozen_v1_xnys_session_on_or_before",
    "project_current_breadth_snapshot",
    "read_pinned_breadth_inputs",
    "validate_breadth_snapshot_bundle",
]
