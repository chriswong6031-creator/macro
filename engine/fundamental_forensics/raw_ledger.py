"""Immutable, bitemporal raw-fact ledger primitives.

This module is deliberately a *kernel*, not a database adapter.  It models the
things that must survive every later mapping decision: a document-local XBRL
fact occurrence, its context and unit, its exact source identity, and the
distinct clocks which say when the source existed and when our system could
actually have used it.

Two rules are intentionally non-negotiable:

* appending a correction, amendment, or recast creates a new immutable event;
  no existing event can be changed in place; and
* point-in-time selection always applies the requested clock before choosing a
  vintage.  A record which was parsed or published later cannot leak into an
  earlier system replay.

The objects are small enough to be serialized to Parquet/JSON elsewhere, but
have no storage, network, or third-party-package dependency themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import (
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Subnormal,
    Underflow,
    localcontext,
)
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping


RAW_LEDGER_SCHEMA = "fundamental_forensics.raw_ledger/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_XBRL_ACCURACY_MAGNITUDE = 10_000
MAX_DECIMAL_SOURCE_CHARS = 100_000
MAX_DECIMAL_CANONICAL_CHARS = 100_000
HARD_MAX_RAW_LEDGER_EVENTS = 1_000_000
# Snapshot restores accept only the canonical JSON representation emitted by
# this module.  Keep a per-fact ceiling as well as a ledger ceiling so a valid
# event count cannot still turn an untrusted restore into a multi-gigabyte
# allocation.
HARD_MAX_RAW_FACT_WIRE_BYTES = 2 * 1024 * 1024
HARD_MAX_RAW_LEDGER_WIRE_BYTES = 512 * 1024 * 1024
MAX_SOURCE_SPAN_OFFSET = (1 << 63) - 1
# Raw-ledger identities are retained rather than displayed verbatim, so they
# need hard admission bounds even though their normal SEC/XBRL values are much
# smaller.  The typed-member allowance deliberately remains generous: typed
# XBRL dimensions can contain canonical XML fragments rather than only QName
# tokens.
MAX_TEXT_CHARS = 16 * 1024
# Text-block facts can be materially larger than identifier fields, but a
# single lexical token still needs an explicit admission boundary before it is
# copied into an immutable occurrence ID or serialized provenance record.
MAX_RAW_TOKEN_BYTES = 1 * 1024 * 1024
MAX_DATE_TEXT_CHARS = 64
MAX_UTC_TEXT_CHARS = 128
MAX_DIMENSION_PAIRS = 64
MAX_UNIT_MEASURES = 32
MAX_TYPED_DIMENSION_MEMBER_BYTES = 64 * 1024
MAX_DIMENSION_MEMBER_NODES = 4_096
MAX_DIMENSION_MEMBER_DEPTH = 64
# Duplicate arbitration uses retained raw decimals, not the smaller
# decimal128 query contract.  These bounds cover the raw fixed-point wire
# limit plus bounded XBRL accuracy metadata while remaining independent of
# an importer's process-global Decimal context.
RAW_DUPLICATE_DECIMAL_PRECISION = 2 * MAX_DECIMAL_CANONICAL_CHARS + 8
RAW_DUPLICATE_DECIMAL_EMIN = -(
    2 * MAX_DECIMAL_CANONICAL_CHARS + 2 * MAX_XBRL_ACCURACY_MAGNITUDE + 8
)
RAW_DUPLICATE_DECIMAL_EMAX = -RAW_DUPLICATE_DECIMAL_EMIN


class AvailabilityStatus(str, Enum):
    """An explicit result state; absence is never silently converted to zero."""

    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    NOT_EVALUABLE = "not_evaluable"


class ReplayClock(str, Enum):
    """Which knowledge clock gates a named vintage view."""

    SOURCE_EVENT = "source_event"
    SYSTEM = "system"


class VintagePolicy(str, Enum):
    """Named, replay-safe policies rather than mutable ``is_latest`` flags."""

    # "Original" is a source-vintage question.  It must remain distinct from
    # the first thing the application happened to record during a backfill.
    SOURCE_ORIGINAL = "source_original"
    FIRST_SYSTEM_KNOWN = "first_system_known"
    LATEST = "latest"
    AS_OF = "as_of"
    # Kept as an enum alias for callers that used the old symbolic spelling.
    ORIGINAL = "source_original"


class FactEventType(str, Enum):
    """Why a new raw occurrence exists in the event history."""

    FILED = "filed"
    AMENDMENT = "amendment"
    COMPARATIVE_RECAST = "comparative_recast"
    RESTATEMENT = "restatement"
    SOURCE_CORRECTION = "source_correction"
    PARSER_CORRECTION = "parser_correction"
    MAPPING_CORRECTION = "mapping_correction"
    XBRL_CONFIRMATION = "xbrl_confirmation"
    WITHDRAWN = "withdrawn"


# A readable alias for callers that use "revision" terminology in their
# ingestion contracts.  The source event type is intentionally the same thing:
# it describes why a new immutable occurrence entered the ledger.
RevisionEventType = FactEventType


_REVISION_TYPES = frozenset(
    {
        FactEventType.AMENDMENT,
        FactEventType.COMPARATIVE_RECAST,
        FactEventType.RESTATEMENT,
        FactEventType.SOURCE_CORRECTION,
        FactEventType.PARSER_CORRECTION,
        FactEventType.MAPPING_CORRECTION,
        FactEventType.XBRL_CONFIRMATION,
        FactEventType.WITHDRAWN,
    }
)


def _vintage_policy(value: VintagePolicy | str) -> VintagePolicy:
    """Parse a policy with one explicit legacy spelling.

    ``original`` used to be ambiguous for actual-system replay.  It now maps
    only to the unambiguous source-original policy; callers wanting the first
    artifact the system knew must ask for ``first_system_known``.
    """
    if isinstance(value, VintagePolicy):
        return value
    text = str(value).strip().lower()
    if text == "original":
        return VintagePolicy.SOURCE_ORIGINAL
    return VintagePolicy(text)


def _bounded_text(
    value: Any,
    *,
    field_name: str,
    maximum_bytes: int,
    required: bool,
    strip: bool = True,
) -> str:
    if isinstance(value, float):
        raise ValueError(f"{field_name} cannot be a binary float")
    if value is None:
        text = ""
    else:
        try:
            text = str(value)
        except Exception as exc:
            raise ValueError(f"{field_name} cannot be converted to text") from exc
    if strip:
        text = text.strip()
    if required and not text:
        raise ValueError(f"{field_name} is required")
    try:
        byte_length = len(text.encode("utf-8"))
    except UnicodeError as exc:
        raise ValueError(f"{field_name} is not valid UTF-8 text") from exc
    if byte_length > maximum_bytes:
        raise ValueError(f"{field_name} exceeds bounded text length")
    return text


def _require_text(
    value: Any,
    *,
    field_name: str,
    maximum_bytes: int = MAX_TEXT_CHARS,
) -> str:
    return _bounded_text(
        value,
        field_name=field_name,
        maximum_bytes=maximum_bytes,
        required=True,
    )


def _parse_date(value: str | date, *, field_name: str) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a date, not datetime")
    if isinstance(value, date):
        return value
    text = _bounded_text(
        value,
        field_name=field_name,
        maximum_bytes=MAX_DATE_TEXT_CHARS,
        required=True,
        strip=False,
    )
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc


def parse_utc(value: str | datetime | None, *, field_name: str) -> datetime | None:
    """Parse an aware timestamp and normalize it to UTC.

    A naive timestamp is rejected.  Treating a machine-local time as a source
    availability clock is an easy way to introduce untestable PIT leakage.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _bounded_text(
            value,
            field_name=field_name,
            maximum_bytes=MAX_UTC_TEXT_CHARS,
            required=True,
        )
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid {field_name}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def decimal_text(value: Decimal | str | int | None) -> str | None:
    """Canonical, non-exponent decimal text while retaining a missing value."""
    if value is None or value == "":
        return None
    if isinstance(value, float):
        raise ValueError("binary float values are forbidden; pass Decimal or source text")
    if isinstance(value, Decimal):
        parsed = value
    else:
        try:
            source_text = str(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid parsed_value of type {type(value).__name__}"
            ) from exc
        if len(source_text) > MAX_DECIMAL_SOURCE_CHARS:
            raise ValueError("parsed_value source text exceeds bounded length")
        try:
            parsed = Decimal(source_text)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"invalid parsed_value: {source_text!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"parsed_value must be finite: {value!r}")
    if parsed == 0:
        return "0"
    sign, digits, exponent = parsed.as_tuple()
    # Fixed-point formatting expands the exponent.  Bound that expansion
    # before ``format`` so a token such as ``1e999999999`` cannot request
    # gigabytes of memory.  This ceiling is far above legitimate filing data.
    decimal_position = len(digits) + exponent
    if exponent >= 0:
        canonical_size = sign + len(digits) + exponent
    elif decimal_position > 0:
        canonical_size = sign + len(digits) + 1
    else:
        canonical_size = sign + 2 + (-decimal_position) + len(digits)
    if canonical_size > MAX_DECIMAL_CANONICAL_CHARS:
        raise ValueError("parsed_value fixed-point expansion exceeds bounded length")
    text = format(parsed, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return utc_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, float):
        raise ValueError("binary floats are not permitted in canonical financial identities")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_jsonable(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ),
        )
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _strict_wire_mapping(
    value: Any,
    *,
    field_name: str,
    expected_fields: frozenset[str],
) -> dict[str, Any]:
    """Read an untrusted JSON object once, with a finite key budget.

    A normal decoded JSON object is a ``dict``, but accepting ``Mapping``
    keeps the public decoder convenient for callers while preventing a custom
    mapping from yielding an unbounded or duplicate field stream.
    """
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    try:
        iterator = iter(value.items())
    except Exception as exc:
        raise ValueError(f"{field_name} items cannot be iterated") from exc
    admitted: dict[str, Any] = {}
    while len(admitted) < len(expected_fields):
        try:
            pair = next(iterator)
        except StopIteration:
            break
        except Exception as exc:
            raise ValueError(f"{field_name} items failed during bounded read") from exc
        try:
            key, item = pair
        except Exception as exc:
            raise ValueError(f"{field_name} items must contain key/value pairs") from exc
        if type(key) is not str or key not in expected_fields:
            raise ValueError(f"{field_name} has an unsupported field")
        if key in admitted:
            raise ValueError(f"{field_name} has a duplicate field: {key}")
        admitted[key] = item
    try:
        next(iterator)
    except StopIteration:
        pass
    except Exception as exc:
        raise ValueError(f"{field_name} items failed during bounded read") from exc
    else:
        raise ValueError(f"{field_name} has too many fields")
    missing = expected_fields.difference(admitted)
    if missing:
        raise ValueError(f"{field_name} is missing canonical fields: {sorted(missing)!r}")
    return admitted


def _strict_wire_list(
    value: Any,
    *,
    field_name: str,
    maximum: int,
) -> list[Any]:
    """Admit a JSON array without trusting a sequence subclass iterator."""
    if type(value) is not list:
        raise TypeError(f"{field_name} must be a JSON array")
    if len(value) > maximum:
        raise ValueError(f"{field_name} exceeds bounded item count {maximum}")
    return value


def _strict_wire_required_text(
    value: Any,
    *,
    field_name: str,
    maximum_bytes: int = MAX_TEXT_CHARS,
    strip: bool = True,
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a JSON string")
    return _bounded_text(
        value,
        field_name=field_name,
        maximum_bytes=maximum_bytes,
        required=True,
        strip=strip,
    )


def _strict_wire_optional_text(
    value: Any,
    *,
    field_name: str,
    maximum_bytes: int = MAX_TEXT_CHARS,
    strip: bool = True,
    allow_empty: bool = False,
) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a JSON string or null")
    return _bounded_text(
        value,
        field_name=field_name,
        maximum_bytes=maximum_bytes,
        required=not allow_empty,
        strip=strip,
    )


def _strict_wire_bool(value: Any, *, field_name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be a JSON boolean")
    return value


def _strict_wire_integer(value: Any, *, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be a JSON integer")
    return value


def _strict_wire_dimension_mapping(
    value: Any,
    *,
    field_name: str,
    maximum_member_bytes: int,
) -> dict[str, str]:
    """Admit only the exact string-to-string shape emitted by FactContext."""
    if type(value) is not dict:
        raise TypeError(f"{field_name} must be a JSON object")
    if len(value) > MAX_DIMENSION_PAIRS:
        raise ValueError(f"{field_name} exceeds bounded dimension count")
    for axis, member in value.items():
        if type(axis) is not str:
            raise TypeError(f"{field_name} axes must be canonical JSON strings")
        if type(member) is not str:
            raise TypeError(f"{field_name} members must be canonical JSON strings")
        _strict_wire_required_text(axis, field_name=f"{field_name} axis")
        _strict_wire_required_text(
            member,
            field_name=f"{field_name} member",
            maximum_bytes=maximum_member_bytes,
        )
    return value


def _canonical_wire_bytes(value: Any, *, field_name: str, maximum: int) -> bytes:
    """Serialize a validated wire fragment with a precise byte admission cap."""
    try:
        encoded = canonical_json(value).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"{field_name} is not canonical JSON") from exc
    if len(encoded) > maximum:
        raise ValueError(f"{field_name} exceeds bounded wire size {maximum}")
    return encoded


def stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def _bounded_dimension_member_json(value: Any, *, field_name: str) -> str:
    """Canonicalize a structured typed member with finite traversal bounds.

    Raw typed dimensions commonly arrive as XML snippets, which remain plain
    text elsewhere in ``_canonical_pairs``.  Structured representations are
    also useful during parser transitions, but must not allow a cyclic graph,
    an unbounded iterator, or an oversized JSON tree to reach the generic
    canonicalizer first.
    """
    node_count = 0
    estimated_bytes = 0
    active_containers: set[int] = set()

    def add_text(text: str, *, label: str) -> None:
        nonlocal estimated_bytes
        try:
            size = len(text.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError(f"{label} is not valid UTF-8 text") from exc
        if size > MAX_TYPED_DIMENSION_MEMBER_BYTES:
            raise ValueError(f"{field_name} member exceeds bounded serialized size")
        estimated_bytes += size + 2
        if estimated_bytes > MAX_TYPED_DIMENSION_MEMBER_BYTES:
            raise ValueError(f"{field_name} member exceeds bounded serialized size")

    def normalize(item: Any, *, depth: int) -> Any:
        nonlocal node_count, estimated_bytes
        if depth > MAX_DIMENSION_MEMBER_DEPTH:
            raise ValueError(f"{field_name} member exceeds bounded nesting depth")
        node_count += 1
        if node_count > MAX_DIMENSION_MEMBER_NODES:
            raise ValueError(f"{field_name} member exceeds bounded node count")
        if isinstance(item, Enum):
            return normalize(item.value, depth=depth + 1)
        if isinstance(item, str):
            add_text(item, label=f"{field_name} member")
            return item
        if item is None or isinstance(item, bool):
            estimated_bytes += 5
            return item
        if isinstance(item, int):
            # Avoid converting a giant arbitrary-precision integer merely to
            # learn it is too large for the serialized member contract.
            if item.bit_length() > MAX_TYPED_DIMENSION_MEMBER_BYTES * 8:
                raise ValueError(f"{field_name} member exceeds bounded serialized size")
            add_text(str(item), label=f"{field_name} member")
            return item
        if isinstance(item, Decimal):
            text = decimal_text(item) or "0"
            add_text(text, label=f"{field_name} member")
            return text
        if isinstance(item, datetime):
            text = utc_text(item) or ""
            add_text(text, label=f"{field_name} member")
            return text
        if isinstance(item, date):
            text = item.isoformat()
            add_text(text, label=f"{field_name} member")
            return text
        if isinstance(item, float):
            raise ValueError("binary floats are not permitted in canonical financial identities")

        if isinstance(item, Mapping):
            identity = id(item)
            if identity in active_containers:
                raise ValueError(f"{field_name} member contains a cycle")
            active_containers.add(identity)
            try:
                try:
                    iterator = iter(item.items())
                except Exception as exc:
                    raise ValueError(f"{field_name} member mapping is not iterable") from exc
                pairs: list[tuple[str, Any]] = []
                while True:
                    try:
                        pair = next(iterator)
                    except StopIteration:
                        break
                    except Exception as exc:
                        raise ValueError(
                            f"{field_name} member mapping failed during bounded read"
                        ) from exc
                    try:
                        key, nested = pair
                    except Exception as exc:
                        raise ValueError(
                            f"{field_name} member mapping entry is malformed"
                        ) from exc
                    try:
                        key_text = str(key)
                    except Exception as exc:
                        raise ValueError(
                            f"{field_name} member mapping key cannot be converted to text"
                        ) from exc
                    add_text(key_text, label=f"{field_name} member mapping key")
                    pairs.append((key_text, normalize(nested, depth=depth + 1)))
                # Match ``_jsonable``: stringified keys are sorted before a
                # mapping is formed, with a stable last value for duplicates.
                normalized: dict[str, Any] = {}
                for key_text, nested in sorted(pairs, key=lambda pair: pair[0]):
                    normalized[key_text] = nested
                return normalized
            finally:
                active_containers.remove(identity)

        if isinstance(item, (list, tuple, set, frozenset)):
            identity = id(item)
            if identity in active_containers:
                raise ValueError(f"{field_name} member contains a cycle")
            active_containers.add(identity)
            try:
                try:
                    iterator = iter(item)
                except Exception as exc:
                    raise ValueError(f"{field_name} member sequence is not iterable") from exc
                normalized_items: list[Any] = []
                while True:
                    try:
                        nested = next(iterator)
                    except StopIteration:
                        break
                    except Exception as exc:
                        raise ValueError(
                            f"{field_name} member sequence failed during bounded read"
                        ) from exc
                    normalized_items.append(normalize(nested, depth=depth + 1))
                if isinstance(item, (set, frozenset)):
                    normalized_items.sort(
                        key=lambda nested: json.dumps(
                            nested,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                            allow_nan=False,
                        )
                    )
                return normalized_items
            finally:
                active_containers.remove(identity)

        try:
            converter = getattr(item, "to_dict", None)
        except Exception as exc:
            raise ValueError(f"{field_name} member cannot be canonicalized") from exc
        if converter is not None:
            if not callable(converter):
                raise ValueError(f"{field_name} member cannot be canonicalized")
            identity = id(item)
            if identity in active_containers:
                raise ValueError(f"{field_name} member contains a cycle")
            active_containers.add(identity)
            try:
                try:
                    converted = converter()
                except Exception as exc:
                    raise ValueError(f"{field_name} member cannot be canonicalized") from exc
                return normalize(converted, depth=depth + 1)
            finally:
                active_containers.remove(identity)

        raise ValueError(f"{field_name} member cannot be canonicalized")

    normalized = normalize(value, depth=0)
    try:
        encoded = canonical_json(normalized).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(f"{field_name} member cannot be canonicalized") from exc
    if len(encoded) > MAX_TYPED_DIMENSION_MEMBER_BYTES:
        raise ValueError(f"{field_name} member exceeds bounded serialized size")
    return encoded.decode("utf-8")


def _canonical_pairs(
    value: Mapping[str, Any] | Iterable[tuple[str, Any]] | None,
    *,
    field_name: str,
) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    try:
        pairs = value.items() if isinstance(value, Mapping) else value
        iterator = iter(pairs)
    except Exception as exc:
        raise ValueError(f"{field_name} must be an iterable of (axis, member) pairs") from exc
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    while True:
        try:
            item = next(iterator)
        except StopIteration:
            break
        except Exception as exc:
            raise ValueError(f"{field_name} iterable failed during bounded read") from exc
        if len(out) >= MAX_DIMENSION_PAIRS:
            raise ValueError(f"{field_name} exceeds bounded dimension pair count")
        try:
            raw_key, raw_member = item
        except Exception as exc:
            raise ValueError(f"{field_name} must contain (axis, member) pairs") from exc
        axis = _require_text(raw_key, field_name=f"{field_name} axis")
        if axis in seen:
            raise ValueError(f"{field_name} contains duplicate axis: {axis}")
        seen.add(axis)
        if isinstance(raw_member, (Mapping, list, tuple, set, frozenset)):
            member = _bounded_dimension_member_json(raw_member, field_name=field_name)
        else:
            member = _require_text(
                raw_member,
                field_name=f"{field_name} member",
                maximum_bytes=(
                    MAX_TYPED_DIMENSION_MEMBER_BYTES
                    if field_name == "typed_dimensions"
                    else MAX_TEXT_CHARS
                ),
            )
        out.append((axis, member))
    return tuple(sorted(out))


@dataclass(frozen=True)
class SourceIdentity:
    """Stable identity of the exact document/body that contained an occurrence."""

    source: str
    entity_id: str
    accession: str
    document_id: str
    body_sha256: str
    source_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _require_text(self.source, field_name="source"))
        object.__setattr__(self, "entity_id", _require_text(self.entity_id, field_name="entity_id"))
        object.__setattr__(self, "accession", _require_text(self.accession, field_name="accession"))
        object.__setattr__(self, "document_id", _require_text(self.document_id, field_name="document_id"))
        body_sha256 = _require_text(self.body_sha256, field_name="body_sha256")
        if not _SHA256_RE.fullmatch(body_sha256):
            raise ValueError("body_sha256 must be lowercase 64-hex")
        object.__setattr__(self, "body_sha256", body_sha256)
        if self.source_url is not None:
            object.__setattr__(self, "source_url", _require_text(self.source_url, field_name="source_url"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "entity_id": self.entity_id,
            "accession": self.accession,
            "document_id": self.document_id,
            "body_sha256": self.body_sha256,
            "source_url": self.source_url,
        }


@dataclass(frozen=True)
class FactContext:
    """Document-local XBRL context plus globally comparable economic semantics."""

    context_id: str
    entity_scheme: str
    entity_identifier: str
    instant: date | str | None = None
    start: date | str | None = None
    end: date | str | None = None
    explicit_dimensions: Mapping[str, Any] | tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    typed_dimensions: Mapping[str, Any] | tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_id", _require_text(self.context_id, field_name="context_id"))
        object.__setattr__(self, "entity_scheme", _require_text(self.entity_scheme, field_name="entity_scheme"))
        object.__setattr__(
            self, "entity_identifier", _require_text(self.entity_identifier, field_name="entity_identifier")
        )
        instant = _parse_date(self.instant, field_name="instant") if self.instant is not None else None
        start = _parse_date(self.start, field_name="start") if self.start is not None else None
        end = _parse_date(self.end, field_name="end") if self.end is not None else None
        if instant is not None and (start is not None or end is not None):
            raise ValueError("context must be either instant or duration, never both")
        if instant is None and (start is None or end is None):
            raise ValueError("duration context requires both start and end")
        if start is not None and end is not None and start >= end:
            raise ValueError("context start must precede end")
        explicit = _canonical_pairs(self.explicit_dimensions, field_name="explicit_dimensions")
        typed = _canonical_pairs(self.typed_dimensions, field_name="typed_dimensions")
        overlap = {axis for axis, _ in explicit}.intersection(axis for axis, _ in typed)
        if overlap:
            raise ValueError(f"a context axis cannot be both explicit and typed: {sorted(overlap)!r}")
        object.__setattr__(self, "instant", instant)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "explicit_dimensions", explicit)
        object.__setattr__(self, "typed_dimensions", typed)

    @property
    def is_instant(self) -> bool:
        return self.instant is not None

    @property
    def semantic_key(self) -> str:
        return stable_id(
            "context",
            self.entity_scheme,
            self.entity_identifier,
            self.instant,
            self.start,
            self.end,
            self.explicit_dimensions,
            self.typed_dimensions,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "entity_scheme": self.entity_scheme,
            "entity_identifier": self.entity_identifier,
            "instant": self.instant.isoformat() if self.instant else None,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "explicit_dimensions": dict(self.explicit_dimensions),
            "typed_dimensions": dict(self.typed_dimensions),
            "semantic_key": self.semantic_key,
        }


def _bounded_unit_measures(
    value: tuple[str, ...] | list[str],
    *,
    field_name: str,
    item_field_name: str,
) -> tuple[str, ...]:
    """Freeze a small XBRL measure collection without trusting a subclass iterator."""
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be a tuple or list, not a scalar string")
    try:
        declared_length = len(value)
    except Exception as exc:
        raise ValueError(f"{field_name} cannot be measured") from exc
    if declared_length > MAX_UNIT_MEASURES:
        raise ValueError(f"{field_name} exceeds bounded measure count")
    try:
        iterator = iter(value)
    except Exception as exc:
        raise ValueError(f"{field_name} is not iterable") from exc
    out: list[str] = []
    while len(out) < MAX_UNIT_MEASURES:
        try:
            item = next(iterator)
        except StopIteration:
            return tuple(sorted(out))
        except Exception as exc:
            raise ValueError(f"{field_name} iterable failed during bounded read") from exc
        out.append(_require_text(item, field_name=item_field_name))
    try:
        next(iterator)
    except StopIteration:
        return tuple(sorted(out))
    except Exception as exc:
        raise ValueError(f"{field_name} iterable failed during bounded read") from exc
    raise ValueError(f"{field_name} exceeds bounded measure count")


@dataclass(frozen=True)
class FactUnit:
    """XBRL unit identity, including compound numerator/denominator units."""

    unit_id: str
    measures: tuple[str, ...] | list[str]
    denominator_measures: tuple[str, ...] | list[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        unit_id = _require_text(self.unit_id, field_name="unit_id")
        measures = _bounded_unit_measures(
            self.measures,
            field_name="unit measures",
            item_field_name="unit measure",
        )
        denominator = _bounded_unit_measures(
            self.denominator_measures,
            field_name="unit denominator measures",
            item_field_name="unit denominator measure",
        )
        if not measures:
            raise ValueError("unit requires at least one numerator measure")
        if len(set(measures)) != len(measures) or len(set(denominator)) != len(denominator):
            raise ValueError("unit measures must not contain duplicates")
        object.__setattr__(self, "unit_id", unit_id)
        object.__setattr__(self, "measures", measures)
        object.__setattr__(self, "denominator_measures", denominator)

    @property
    def semantic_key(self) -> str:
        return stable_id("unit", self.measures, self.denominator_measures)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "measures": list(self.measures),
            "denominator_measures": list(self.denominator_measures),
            "semantic_key": self.semantic_key,
        }


def _normalized_decimals(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    text = _require_text(value, field_name="decimals")
    if text.upper() == "INF":
        return "INF"
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ValueError("decimals must be an integer or INF") from exc
    if abs(parsed) > MAX_XBRL_ACCURACY_MAGNITUDE:
        raise ValueError("decimals magnitude exceeds the bounded XBRL accuracy limit")
    return str(parsed)


def _normalized_precision(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    text = _require_text(value, field_name="precision")
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ValueError("precision must be a positive integer") from exc
    if parsed <= 0 or parsed > MAX_XBRL_ACCURACY_MAGNITUDE:
        raise ValueError("precision must be a positive bounded integer")
    return str(parsed)


@dataclass(frozen=True)
class TemporalClocks:
    """Source, transaction, rule, computation, and publication clocks.

    ``accepted_at`` is deliberately optional: an undated source can still be
    preserved and used in a system-time view, but it is explicitly unavailable
    in source-event replay rather than being treated as if it were timely.
    """

    recorded_at: datetime | str
    accepted_at: datetime | str | None = None
    mapping_available_at: datetime | str | None = None
    computed_at: datetime | str | None = None
    published_at: datetime | str | None = None

    def __post_init__(self) -> None:
        recorded = parse_utc(self.recorded_at, field_name="recorded_at")
        accepted = parse_utc(self.accepted_at, field_name="accepted_at")
        mapping = parse_utc(self.mapping_available_at, field_name="mapping_available_at")
        computed = parse_utc(self.computed_at, field_name="computed_at")
        published = parse_utc(self.published_at, field_name="published_at")
        if recorded is None:  # pragma: no cover - static typing and required argument guard this
            raise ValueError("recorded_at is required")
        if accepted is not None and accepted > recorded:
            raise ValueError("accepted_at cannot be after recorded_at")
        if computed is not None:
            prerequisite = max(value for value in (recorded, mapping) if value is not None)
            if computed < prerequisite:
                raise ValueError("computed_at cannot precede recorded_at or mapping_available_at")
        if published is not None:
            prerequisite_values = [recorded]
            if mapping is not None:
                prerequisite_values.append(mapping)
            if computed is not None:
                prerequisite_values.append(computed)
            if published < max(prerequisite_values):
                raise ValueError("published_at cannot precede its available prerequisites")
        object.__setattr__(self, "recorded_at", recorded)
        object.__setattr__(self, "accepted_at", accepted)
        object.__setattr__(self, "mapping_available_at", mapping)
        object.__setattr__(self, "computed_at", computed)
        object.__setattr__(self, "published_at", published)

    @property
    def source_ready_at(self) -> datetime | None:
        return self.accepted_at

    @property
    def source_event_at(self) -> datetime | None:
        """Compatibility spelling for the accepted/publication event clock."""
        return self.accepted_at

    @property
    def system_ready_at(self) -> datetime:
        """Latest required known-time clock for the artifact that exists here."""
        return max(
            value
            for value in (
                self.recorded_at,
                self.mapping_available_at,
                self.computed_at,
                self.published_at,
            )
            if value is not None
        )

    def ready_at(self, clock: ReplayClock | str) -> datetime | None:
        mode = ReplayClock(clock)
        return self.source_ready_at if mode is ReplayClock.SOURCE_EVENT else self.system_ready_at

    def to_dict(self) -> dict[str, str | None]:
        return {
            "accepted_at": utc_text(self.accepted_at),
            "recorded_at": utc_text(self.recorded_at),
            "mapping_available_at": utc_text(self.mapping_available_at),
            "computed_at": utc_text(self.computed_at),
            "published_at": utc_text(self.published_at),
        }


@dataclass(frozen=True)
class RawFactOccurrence:
    """One uncollapsed source occurrence; duplicate occurrences stay distinct."""

    source: SourceIdentity
    concept_qname: str
    context: FactContext
    clocks: TemporalClocks
    unit: FactUnit | None = None
    # ``False`` means the source plane did not expose dimensional context at
    # all.  It is materially different from a known-empty context and must not
    # be treated as proof that a fact is consolidated/dimensionless.
    dimensions_known: bool = True
    # Source-local discriminator for byte-identical occurrences.  It changes
    # immutable occurrence identity, but not economic or duplicate grouping.
    source_occurrence_key: str | None = None
    raw_token: str | None = None
    parsed_value: Decimal | str | int | None = None
    is_nil: bool = False
    xml_lang: str | None = None
    decimals: str | None = None
    precision: str | None = None
    inline_format: str | None = None
    inline_sign: str | None = None
    inline_scale: int | None = None
    hidden: bool = False
    source_span: tuple[int, int] | None = None
    event_type: FactEventType | str = FactEventType.FILED
    revision_of: str | None = None
    occurrence_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceIdentity):
            raise TypeError("source must be SourceIdentity")
        if not isinstance(self.context, FactContext):
            raise TypeError("context must be FactContext")
        if not isinstance(self.clocks, TemporalClocks):
            raise TypeError("clocks must be TemporalClocks")
        if self.source.entity_id != self.context.entity_identifier:
            raise ValueError("source entity_id must equal context entity_identifier")
        if self.unit is not None and not isinstance(self.unit, FactUnit):
            raise TypeError("unit must be FactUnit when supplied")
        if not isinstance(self.dimensions_known, bool):
            raise TypeError("dimensions_known must be a boolean")
        if not isinstance(self.is_nil, bool):
            raise TypeError("is_nil must be a boolean")
        if not isinstance(self.hidden, bool):
            raise TypeError("hidden must be a boolean")
        concept = _require_text(self.concept_qname, field_name="concept_qname")
        event_type = FactEventType(self.event_type)
        raw_token = (
            _bounded_text(
                self.raw_token,
                field_name="raw_token",
                maximum_bytes=MAX_RAW_TOKEN_BYTES,
                required=False,
                # The source token is evidence rather than a display label;
                # whitespace is therefore part of its immutable identity.
                strip=False,
            )
            if self.raw_token is not None
            else None
        )
        xml_lang = (
            _bounded_text(
                self.xml_lang,
                field_name="xml_lang",
                maximum_bytes=MAX_TEXT_CHARS,
                required=False,
                strip=False,
            )
            if self.xml_lang is not None
            else None
        )
        inline_format = (
            _bounded_text(
                self.inline_format,
                field_name="inline_format",
                maximum_bytes=MAX_TEXT_CHARS,
                required=False,
                strip=False,
            )
            if self.inline_format is not None
            else None
        )
        parsed = decimal_text(self.parsed_value)
        if self.is_nil and parsed is not None:
            raise ValueError("a nil fact cannot have a parsed_value")
        if not self.is_nil and raw_token is None and parsed is None:
            raise ValueError("a non-nil fact requires raw_token or parsed_value")
        if parsed is not None and self.unit is None:
            raise ValueError("numeric facts require a unit")
        decimals = _normalized_decimals(self.decimals)
        precision = _normalized_precision(self.precision)
        if decimals is not None and precision is not None:
            raise ValueError("a fact cannot carry both decimals and precision")
        if self.source_span is not None:
            try:
                start, end = self.source_span
            except (TypeError, ValueError) as exc:
                raise ValueError("source_span must be a (start, end) pair") from exc
            if (
                type(start) is not int
                or type(end) is not int
                or start < 0
                or end < start
            ):
                raise ValueError("source_span must be a non-negative increasing byte/DOM span")
            if start > MAX_SOURCE_SPAN_OFFSET or end > MAX_SOURCE_SPAN_OFFSET:
                raise ValueError("source_span exceeds bounded signed 64-bit offset")
            object.__setattr__(self, "source_span", (start, end))
        inline_sign = self.inline_sign
        if inline_sign is not None and (
            not isinstance(inline_sign, str) or inline_sign not in {"+", "-"}
        ):
            raise ValueError("inline_sign must be '+' or '-'")
        inline_scale = self.inline_scale
        if inline_scale is not None and (
            isinstance(inline_scale, bool) or not isinstance(inline_scale, int)
        ):
            raise ValueError("inline_scale must be an integer")
        if inline_scale is not None and abs(inline_scale) > MAX_XBRL_ACCURACY_MAGNITUDE:
            raise ValueError("inline_scale magnitude exceeds the bounded XBRL accuracy limit")
        if event_type in _REVISION_TYPES and not self.revision_of:
            raise ValueError(f"{event_type.value} event requires revision_of")
        if event_type is FactEventType.FILED and self.revision_of is not None:
            raise ValueError("a filed event cannot have revision_of; use a typed revision event")
        revision_of = _require_text(self.revision_of, field_name="revision_of") if self.revision_of else None
        source_occurrence_key = (
            _require_text(
                self.source_occurrence_key,
                field_name="source_occurrence_key",
            )
            if self.source_occurrence_key is not None
            else None
        )
        identity_payload = {
            "source": self.source.to_dict(),
            "concept_qname": concept,
            "context": self.context.to_dict(),
            "unit": self.unit.to_dict() if self.unit else None,
            "dimensions_known": self.dimensions_known,
            "source_occurrence_key": source_occurrence_key,
            "raw_token": raw_token,
            "parsed_value": parsed,
            "is_nil": self.is_nil,
            "xml_lang": xml_lang,
            "decimals": decimals,
            "precision": precision,
            "inline_format": inline_format,
            "inline_sign": inline_sign,
            "inline_scale": inline_scale,
            "hidden": self.hidden,
            "source_span": self.source_span,
            "event_type": event_type.value,
            "revision_of": revision_of,
            # Availability is part of an immutable occurrence identity.  A
            # later-retained or later-governed rendering is a new event, not
            # the same occurrence with a mutable clock.
            "clocks": self.clocks.to_dict(),
        }
        expected_occurrence_id = stable_id("rawfact", identity_payload)
        if self.occurrence_id is not None:
            supplied_occurrence_id = _require_text(
                self.occurrence_id,
                field_name="occurrence_id",
            )
            if supplied_occurrence_id != expected_occurrence_id:
                raise ValueError(
                    "occurrence_id does not match canonical occurrence identity"
                )
        object.__setattr__(self, "concept_qname", concept)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "revision_of", revision_of)
        object.__setattr__(self, "raw_token", raw_token)
        object.__setattr__(self, "parsed_value", parsed)
        object.__setattr__(self, "is_nil", self.is_nil)
        object.__setattr__(self, "xml_lang", xml_lang)
        object.__setattr__(self, "decimals", decimals)
        object.__setattr__(self, "precision", precision)
        object.__setattr__(self, "inline_format", inline_format)
        object.__setattr__(self, "inline_sign", inline_sign)
        object.__setattr__(self, "inline_scale", inline_scale)
        object.__setattr__(self, "hidden", self.hidden)
        object.__setattr__(self, "source_occurrence_key", source_occurrence_key)
        object.__setattr__(self, "occurrence_id", expected_occurrence_id)

    @property
    def logical_key(self) -> str:
        """Economic identity excluding document, source span, value, and vintage."""
        return stable_id(
            "rawfact_lineage",
            self.source.source,
            self.source.entity_id,
            self.concept_qname,
            self.context.semantic_key,
            self.unit.semantic_key if self.unit else None,
        )

    @property
    def duplicate_group_key(self) -> str:
        """Identity of repeated source occurrences of one XBRL data point.

        This is deliberately narrower than ``logical_key``: different filing
        vintages are candidates for a temporal view, while two source spans in
        one immutable document must first agree before either can be selected.
        """
        return stable_id(
            "rawfact_duplicate",
            self.source.source,
            self.source.entity_id,
            self.source.accession,
            self.source.document_id,
            self.source.body_sha256,
            self.concept_qname,
            self.context.semantic_key,
            self.unit.semantic_key if self.unit else None,
            self.dimensions_known,
            self.xml_lang,
            self.event_type.value,
            self.revision_of,
        )

    @property
    def is_withdrawn(self) -> bool:
        return self.event_type is FactEventType.WITHDRAWN

    @property
    def accepted_at(self) -> datetime | None:
        return self.clocks.accepted_at

    @property
    def source_event_at(self) -> datetime | None:
        return self.clocks.source_event_at

    @property
    def recorded_at(self) -> datetime:
        return self.clocks.recorded_at

    @property
    def mapping_available_at(self) -> datetime | None:
        return self.clocks.mapping_available_at

    @property
    def computed_at(self) -> datetime | None:
        return self.clocks.computed_at

    @property
    def published_at(self) -> datetime | None:
        return self.clocks.published_at

    def ready_at(self, clock: ReplayClock | str) -> datetime | None:
        return self.clocks.ready_at(clock)

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurrence_id": self.occurrence_id,
            "logical_key": self.logical_key,
            "duplicate_group_key": self.duplicate_group_key,
            "source": self.source.to_dict(),
            "concept_qname": self.concept_qname,
            "context": self.context.to_dict(),
            "unit": self.unit.to_dict() if self.unit else None,
            "dimensions_known": self.dimensions_known,
            "source_occurrence_key": self.source_occurrence_key,
            "raw_token": self.raw_token,
            "parsed_value": self.parsed_value,
            "is_nil": self.is_nil,
            "xml_lang": self.xml_lang,
            "decimals": self.decimals,
            "precision": self.precision,
            "inline_format": self.inline_format,
            "inline_sign": self.inline_sign,
            "inline_scale": self.inline_scale,
            "hidden": self.hidden,
            "source_span": list(self.source_span) if self.source_span else None,
            "event_type": self.event_type.value,
            "revision_of": self.revision_of,
            "clocks": self.clocks.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RawFactOccurrence":
        """Restore one occurrence from an already-decoded canonical mapping.

        The raw ledger is an evidence boundary.  Derived identifiers, context
        and unit semantic keys, source spans, and every availability clock are
        verified by reconstructing the immutable occurrence.  Mapping inputs
        cannot preserve duplicate JSON keys or original byte spelling; external
        payloads must enter through :meth:`RawFactLedger.from_json_bytes`.
        """
        raw = _strict_wire_mapping(
            value,
            field_name="raw fact occurrence",
            expected_fields=frozenset(
                {
                    "occurrence_id",
                    "logical_key",
                    "duplicate_group_key",
                    "source",
                    "concept_qname",
                    "context",
                    "unit",
                    "dimensions_known",
                    "source_occurrence_key",
                    "raw_token",
                    "parsed_value",
                    "is_nil",
                    "xml_lang",
                    "decimals",
                    "precision",
                    "inline_format",
                    "inline_sign",
                    "inline_scale",
                    "hidden",
                    "source_span",
                    "event_type",
                    "revision_of",
                    "clocks",
                }
            ),
        )
        source_raw = _strict_wire_mapping(
            raw["source"],
            field_name="raw fact source",
            expected_fields=frozenset(
                {
                    "source",
                    "entity_id",
                    "accession",
                    "document_id",
                    "body_sha256",
                    "source_url",
                }
            ),
        )
        source = SourceIdentity(
            source=_strict_wire_required_text(source_raw["source"], field_name="source.source"),
            entity_id=_strict_wire_required_text(source_raw["entity_id"], field_name="source.entity_id"),
            accession=_strict_wire_required_text(source_raw["accession"], field_name="source.accession"),
            document_id=_strict_wire_required_text(source_raw["document_id"], field_name="source.document_id"),
            body_sha256=_strict_wire_required_text(source_raw["body_sha256"], field_name="source.body_sha256"),
            source_url=_strict_wire_optional_text(source_raw["source_url"], field_name="source.source_url"),
        )

        context_raw = _strict_wire_mapping(
            raw["context"],
            field_name="raw fact context",
            expected_fields=frozenset(
                {
                    "context_id",
                    "entity_scheme",
                    "entity_identifier",
                    "instant",
                    "start",
                    "end",
                    "explicit_dimensions",
                    "typed_dimensions",
                    "semantic_key",
                }
            ),
        )
        explicit_dimensions = _strict_wire_dimension_mapping(
            context_raw["explicit_dimensions"],
            field_name="context.explicit_dimensions",
            maximum_member_bytes=MAX_TEXT_CHARS,
        )
        typed_dimensions = _strict_wire_dimension_mapping(
            context_raw["typed_dimensions"],
            field_name="context.typed_dimensions",
            maximum_member_bytes=MAX_TYPED_DIMENSION_MEMBER_BYTES,
        )
        context = FactContext(
            context_id=_strict_wire_required_text(context_raw["context_id"], field_name="context.context_id"),
            entity_scheme=_strict_wire_required_text(context_raw["entity_scheme"], field_name="context.entity_scheme"),
            entity_identifier=_strict_wire_required_text(
                context_raw["entity_identifier"], field_name="context.entity_identifier"
            ),
            instant=_strict_wire_optional_text(context_raw["instant"], field_name="context.instant", strip=False),
            start=_strict_wire_optional_text(context_raw["start"], field_name="context.start", strip=False),
            end=_strict_wire_optional_text(context_raw["end"], field_name="context.end", strip=False),
            explicit_dimensions=explicit_dimensions,
            typed_dimensions=typed_dimensions,
        )
        if (
            _strict_wire_required_text(context_raw["semantic_key"], field_name="context.semantic_key")
            != context.semantic_key
        ):
            raise ValueError("context.semantic_key does not match canonical context identity")

        unit_raw = raw["unit"]
        unit: FactUnit | None
        if unit_raw is None:
            unit = None
        else:
            unit_fields = _strict_wire_mapping(
                unit_raw,
                field_name="raw fact unit",
                expected_fields=frozenset(
                    {
                        "unit_id",
                        "measures",
                        "denominator_measures",
                        "semantic_key",
                    }
                ),
            )
            measures = _strict_wire_list(
                unit_fields["measures"],
                field_name="unit.measures",
                maximum=MAX_UNIT_MEASURES,
            )
            denominator_measures = _strict_wire_list(
                unit_fields["denominator_measures"],
                field_name="unit.denominator_measures",
                maximum=MAX_UNIT_MEASURES,
            )
            for index, measure in enumerate(measures):
                _strict_wire_required_text(measure, field_name=f"unit.measures[{index}]")
            for index, measure in enumerate(denominator_measures):
                _strict_wire_required_text(
                    measure,
                    field_name=f"unit.denominator_measures[{index}]",
                )
            unit = FactUnit(
                unit_id=_strict_wire_required_text(unit_fields["unit_id"], field_name="unit.unit_id"),
                measures=measures,
                denominator_measures=denominator_measures,
            )
            if (
                _strict_wire_required_text(unit_fields["semantic_key"], field_name="unit.semantic_key")
                != unit.semantic_key
            ):
                raise ValueError("unit.semantic_key does not match canonical unit identity")

        clocks_raw = _strict_wire_mapping(
            raw["clocks"],
            field_name="raw fact clocks",
            expected_fields=frozenset(
                {
                    "accepted_at",
                    "recorded_at",
                    "mapping_available_at",
                    "computed_at",
                    "published_at",
                }
            ),
        )
        clocks = TemporalClocks(
            accepted_at=_strict_wire_optional_text(clocks_raw["accepted_at"], field_name="clocks.accepted_at"),
            recorded_at=_strict_wire_required_text(clocks_raw["recorded_at"], field_name="clocks.recorded_at"),
            mapping_available_at=_strict_wire_optional_text(
                clocks_raw["mapping_available_at"], field_name="clocks.mapping_available_at"
            ),
            computed_at=_strict_wire_optional_text(clocks_raw["computed_at"], field_name="clocks.computed_at"),
            published_at=_strict_wire_optional_text(clocks_raw["published_at"], field_name="clocks.published_at"),
        )

        source_span_raw = raw["source_span"]
        source_span: tuple[int, int] | None
        if source_span_raw is None:
            source_span = None
        else:
            source_span_parts = _strict_wire_list(
                source_span_raw,
                field_name="source_span",
                maximum=2,
            )
            if len(source_span_parts) != 2:
                raise ValueError("source_span must contain exactly two integers")
            start = _strict_wire_integer(source_span_parts[0], field_name="source_span[0]")
            end = _strict_wire_integer(source_span_parts[1], field_name="source_span[1]")
            if start < 0 or end < start:
                raise ValueError("source_span must be a non-negative increasing byte/DOM span")
            if start > MAX_SOURCE_SPAN_OFFSET or end > MAX_SOURCE_SPAN_OFFSET:
                raise ValueError("source_span exceeds bounded signed 64-bit offset")
            source_span = (
                start,
                end,
            )

        result = cls(
            source=source,
            concept_qname=_strict_wire_required_text(raw["concept_qname"], field_name="concept_qname"),
            context=context,
            clocks=clocks,
            unit=unit,
            dimensions_known=_strict_wire_bool(raw["dimensions_known"], field_name="dimensions_known"),
            source_occurrence_key=_strict_wire_optional_text(
                raw["source_occurrence_key"], field_name="source_occurrence_key"
            ),
            raw_token=_strict_wire_optional_text(
                raw["raw_token"],
                field_name="raw_token",
                maximum_bytes=MAX_RAW_TOKEN_BYTES,
                strip=False,
                allow_empty=True,
            ),
            parsed_value=_strict_wire_optional_text(
                raw["parsed_value"],
                field_name="parsed_value",
                maximum_bytes=MAX_DECIMAL_SOURCE_CHARS,
                strip=False,
            ),
            is_nil=_strict_wire_bool(raw["is_nil"], field_name="is_nil"),
            xml_lang=_strict_wire_optional_text(
                raw["xml_lang"],
                field_name="xml_lang",
                strip=False,
                allow_empty=True,
            ),
            decimals=_strict_wire_optional_text(raw["decimals"], field_name="decimals"),
            precision=_strict_wire_optional_text(raw["precision"], field_name="precision"),
            inline_format=_strict_wire_optional_text(
                raw["inline_format"],
                field_name="inline_format",
                strip=False,
                allow_empty=True,
            ),
            inline_sign=_strict_wire_optional_text(raw["inline_sign"], field_name="inline_sign", strip=False),
            inline_scale=(
                _strict_wire_integer(raw["inline_scale"], field_name="inline_scale")
                if raw["inline_scale"] is not None
                else None
            ),
            hidden=_strict_wire_bool(raw["hidden"], field_name="hidden"),
            source_span=source_span,
            event_type=_strict_wire_required_text(raw["event_type"], field_name="event_type"),
            revision_of=_strict_wire_optional_text(raw["revision_of"], field_name="revision_of"),
            occurrence_id=_strict_wire_required_text(raw["occurrence_id"], field_name="occurrence_id"),
        )
        if (
            _strict_wire_required_text(raw["logical_key"], field_name="logical_key")
            != result.logical_key
        ):
            raise ValueError("logical_key does not match canonical raw fact identity")
        if (
            _strict_wire_required_text(raw["duplicate_group_key"], field_name="duplicate_group_key")
            != result.duplicate_group_key
        ):
            raise ValueError("duplicate_group_key does not match canonical raw fact identity")

        canonical_raw = _canonical_wire_bytes(
            raw,
            field_name="raw fact occurrence",
            maximum=HARD_MAX_RAW_FACT_WIRE_BYTES,
        )
        canonical_result = _canonical_wire_bytes(
            result.to_dict(),
            field_name="canonical raw fact occurrence",
            maximum=HARD_MAX_RAW_FACT_WIRE_BYTES,
        )
        if canonical_raw != canonical_result:
            raise ValueError("raw fact occurrence is not canonical JSON wire data")
        return result


def _raw_duplicate_decimal_context() -> Context:
    """Return an isolated Decimal context for raw duplicate arbitration."""
    context = Context(
        prec=RAW_DUPLICATE_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=RAW_DUPLICATE_DECIMAL_EMIN,
        Emax=RAW_DUPLICATE_DECIMAL_EMAX,
        capitals=1,
        clamp=0,
    )
    for signal in (InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal):
        context.traps[signal] = True
    return context


def _rounding_tolerance_in_context(item: RawFactOccurrence) -> Decimal:
    """Maximum one-sided rounding error implied by XBRL decimals/precision."""
    if item.parsed_value is None:
        return Decimal("0")
    if item.decimals is not None:
        if item.decimals == "INF":
            return Decimal("0")
        return Decimal("0.5").scaleb(-int(item.decimals))
    if item.precision is not None:
        value = Decimal(item.parsed_value)
        if value == 0:
            # A zero with only significant-digit precision is not enough to
            # justify treating a nonzero duplicate as equal.
            return Decimal("0")
        exponent = value.copy_abs().adjusted() - int(item.precision) + 1
        return Decimal("0.5").scaleb(exponent)
    return Decimal("0")


def _rounding_tolerance(item: RawFactOccurrence) -> Decimal:
    """Ambient-context-independent public tolerance calculation."""
    try:
        with localcontext(_raw_duplicate_decimal_context()):
            return _rounding_tolerance_in_context(item)
    except (DecimalException, OverflowError) as exc:
        raise ValueError("raw fact rounding tolerance exceeds bounded decimal contract") from exc


def _duplicate_interval(item: RawFactOccurrence) -> tuple[Decimal, Decimal]:
    """Return the inclusive decimal interval admitted by one duplicate fact."""
    value = +Decimal(item.parsed_value)
    tolerance = _rounding_tolerance_in_context(item)
    return value - tolerance, value + tolerance


def _duplicates_agree(items: Iterable[RawFactOccurrence]) -> bool:
    """Check exact or tolerance-overlapping values before a duplicate collapse."""
    values = tuple(items)
    if len(values) < 2:
        return True
    if len({item.is_nil for item in values}) != 1:
        return False
    if values[0].is_nil:
        return True
    numeric = [item.parsed_value is not None for item in values]
    if any(numeric) and not all(numeric):
        return False
    if not any(numeric):
        return len({item.raw_token for item in values}) == 1
    try:
        with localcontext(_raw_duplicate_decimal_context()):
            # In one dimension, the old all-pairs tolerance condition is
            # exactly intersection of the individual closed intervals.  Keep
            # only their largest lower bound and smallest upper bound so a
            # one-million-row duplicate group remains linear rather than
            # quadratic.
            lower_bound: Decimal | None = None
            upper_bound: Decimal | None = None
            for item in values:
                lower, upper = _duplicate_interval(item)
                lower_bound = lower if lower_bound is None or lower > lower_bound else lower_bound
                upper_bound = upper if upper_bound is None or upper < upper_bound else upper_bound
                if lower_bound > upper_bound:
                    return False
            return True
    except (DecimalException, OverflowError, ValueError):
        # A raw value which cannot be compared under the explicit bounded
        # contract cannot establish duplicate equivalence by borrowing an
        # importer's ambient Decimal context.
        return False


def _canonical_duplicate_representative(items: Iterable[RawFactOccurrence]) -> RawFactOccurrence:
    """Stable display representative after all copies have proved compatible."""
    return min(
        items,
        key=lambda item: (
            item.source_span is None,
            item.source_span or (0, 0),
            item.occurrence_id,
        ),
    )


def make_raw_fact(
    *,
    source: SourceIdentity,
    concept_qname: str,
    context: FactContext,
    recorded_at: datetime | str,
    accepted_at: datetime | str | None = None,
    mapping_available_at: datetime | str | None = None,
    computed_at: datetime | str | None = None,
    published_at: datetime | str | None = None,
    **kwargs: Any,
) -> RawFactOccurrence:
    """Convenience constructor for callers whose source payload has flat clocks."""
    return RawFactOccurrence(
        source=source,
        concept_qname=concept_qname,
        context=context,
        clocks=TemporalClocks(
            accepted_at=accepted_at,
            recorded_at=recorded_at,
            mapping_available_at=mapping_available_at,
            computed_at=computed_at,
            published_at=published_at,
        ),
        **kwargs,
    )


@dataclass(frozen=True)
class LedgerSelection:
    """A selected vintage or a typed, inspectable non-result."""

    status: AvailabilityStatus
    clock: ReplayClock
    policy: VintagePolicy
    as_of: datetime
    logical_key: str
    occurrence: RawFactOccurrence | None = None
    reason: str | None = None
    candidate_occurrence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        clock = ReplayClock(self.clock)
        policy = _vintage_policy(self.policy)
        as_of = parse_utc(self.as_of, field_name="as_of")
        if as_of is None:  # pragma: no cover - required type prevents it
            raise ValueError("as_of is required")
        if self.status is AvailabilityStatus.AVAILABLE and self.occurrence is None:
            raise ValueError("available selection requires an occurrence")
        if self.status is not AvailabilityStatus.AVAILABLE and self.occurrence is not None:
            raise ValueError("non-available selection cannot expose an occurrence")
        object.__setattr__(self, "clock", clock)
        object.__setattr__(self, "policy", policy)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "logical_key", _require_text(self.logical_key, field_name="logical_key"))
        object.__setattr__(self, "candidate_occurrence_ids", tuple(sorted(set(self.candidate_occurrence_ids))))

    @property
    def is_available(self) -> bool:
        return self.status is AvailabilityStatus.AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "clock": self.clock.value,
            "policy": self.policy.value,
            "as_of": utc_text(self.as_of),
            "logical_key": self.logical_key,
            "occurrence_id": self.occurrence.occurrence_id if self.occurrence else None,
            "reason": self.reason,
            "candidate_occurrence_ids": list(self.candidate_occurrence_ids),
        }


def not_available(
    *,
    clock: ReplayClock | str,
    policy: VintagePolicy | str,
    as_of: datetime | str,
    logical_key: str,
    reason: str,
    candidate_occurrence_ids: Iterable[str] = (),
) -> LedgerSelection:
    return LedgerSelection(
        status=AvailabilityStatus.NOT_AVAILABLE,
        clock=ReplayClock(clock),
        policy=_vintage_policy(policy),
        as_of=parse_utc(as_of, field_name="as_of"),
        logical_key=logical_key,
        reason=_require_text(reason, field_name="reason"),
        candidate_occurrence_ids=tuple(candidate_occurrence_ids),
    )


def not_evaluable(
    *,
    clock: ReplayClock | str,
    policy: VintagePolicy | str,
    as_of: datetime | str,
    logical_key: str,
    reason: str,
    candidate_occurrence_ids: Iterable[str] = (),
) -> LedgerSelection:
    return LedgerSelection(
        status=AvailabilityStatus.NOT_EVALUABLE,
        clock=ReplayClock(clock),
        policy=_vintage_policy(policy),
        as_of=parse_utc(as_of, field_name="as_of"),
        logical_key=logical_key,
        reason=_require_text(reason, field_name="reason"),
        candidate_occurrence_ids=tuple(candidate_occurrence_ids),
    )


def _event_order(item: RawFactOccurrence, clock: ReplayClock) -> tuple[datetime, str]:
    ready = item.ready_at(clock)
    if ready is None:  # caller filters source-clock undated records first
        raise ValueError("cannot order an event with an unavailable replay clock")
    return ready, item.occurrence_id


def _bounded_event_tuple(
    value: Iterable[RawFactOccurrence],
    *,
    maximum: int,
    label: str,
) -> tuple[RawFactOccurrence, ...]:
    """Normalize an event iterable once without trusting it to terminate."""
    if type(value) is tuple:
        if len(value) > maximum:
            raise ValueError(f"{label} exceeds bounded event count {maximum}")
        return value
    try:
        iterator = iter(value)
    except Exception as exc:
        raise TypeError(f"{label} must be an iterable of raw fact occurrences") from exc
    events: list[RawFactOccurrence] = []
    while len(events) <= maximum:
        try:
            event = next(iterator)
        except StopIteration:
            return tuple(events)
        except Exception as exc:
            raise ValueError(f"{label} iterable failed during bounded read") from exc
        if len(events) == maximum:
            raise ValueError(f"{label} exceeds bounded event count {maximum}")
        if not isinstance(event, RawFactOccurrence):
            raise TypeError(
                f"{label} must contain RawFactOccurrence instances"
            )
        events.append(event)
    raise AssertionError("bounded raw ledger normalization did not terminate")


@dataclass(frozen=True)
class RawFactLedger:
    """Persistent-value-style append-only ledger of ``RawFactOccurrence`` events."""

    events: tuple[RawFactOccurrence, ...] = field(default_factory=tuple)
    schema: str = RAW_LEDGER_SCHEMA
    _events_by_logical_key: Mapping[str, tuple[RawFactOccurrence, ...]] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.schema != RAW_LEDGER_SCHEMA:
            raise ValueError(f"unsupported raw ledger schema: {self.schema}")
        events = _bounded_event_tuple(
            self.events,
            maximum=HARD_MAX_RAW_LEDGER_EVENTS,
            label="raw ledger events",
        )
        # Freeze before validation so a generator is consumed exactly once and
        # a hostile mutable iterable cannot swap the retained sequence after
        # its invariants were checked.
        object.__setattr__(self, "events", events)
        seen: set[str] = set()
        by_id: dict[str, RawFactOccurrence] = {}
        lineage_max_accepted: dict[str, datetime | None] = {}
        events_by_logical_key: dict[str, list[RawFactOccurrence]] = {}
        for event in events:
            if not isinstance(event, RawFactOccurrence):
                raise TypeError("raw ledger events must be RawFactOccurrence instances")
            if event.occurrence_id in seen:
                raise ValueError(f"duplicate occurrence_id: {event.occurrence_id}")
            event_logical_key = event.logical_key
            parent_id = event.revision_of
            lineage_accepted = event.accepted_at
            if parent_id:
                parent = by_id.get(parent_id)
                if parent is None:
                    raise ValueError(
                        f"revision {event.occurrence_id} must be appended after parent {parent_id}"
                    )
                if parent.logical_key != event_logical_key:
                    raise ValueError("a revision must preserve its economic logical_key")
                # Retention order may legitimately differ during a backfill,
                # but a source revision cannot precede the source event it
                # revises.  Without this guard, source-event replay could
                # expose a child value before its parent filing existed.
                ancestor_max = lineage_max_accepted[parent_id]
                if (
                    ancestor_max is not None
                    and event.accepted_at is not None
                    and event.accepted_at < ancestor_max
                ):
                    raise ValueError(
                        "a revision accepted_at cannot precede a known ancestor"
                    )
                if ancestor_max is not None and (
                    lineage_accepted is None or ancestor_max > lineage_accepted
                ):
                    lineage_accepted = ancestor_max
            seen.add(event.occurrence_id)
            by_id[event.occurrence_id] = event
            events_by_logical_key.setdefault(event_logical_key, []).append(event)
            lineage_max_accepted[event.occurrence_id] = lineage_accepted
        # ``events`` is already an immutable tuple in append order.  Freeze a
        # logical-key index at the same boundary so select_all does not turn a
        # ledger with many concepts into a repeated full-ledger scan.
        object.__setattr__(
            self,
            "_events_by_logical_key",
            MappingProxyType(
                {
                    key: tuple(group)
                    for key, group in events_by_logical_key.items()
                }
            ),
        )

    def append(self, event: RawFactOccurrence) -> "RawFactLedger":
        """Return a new ledger; existing events are never changed or replaced."""
        if event.occurrence_id in {item.occurrence_id for item in self.events}:
            raise ValueError(f"occurrence_id already exists; immutable ledger cannot overwrite it: {event.occurrence_id}")
        return RawFactLedger(events=self.events + (event,), schema=self.schema)

    def extend(self, events: Iterable[RawFactOccurrence]) -> "RawFactLedger":
        # Materialize a caller's bounded batch once and validate the combined
        # ledger once. Repeated ``append`` reconstructed every growing prefix,
        # turning a normal batch ingest into quadratic work.
        incoming = _bounded_event_tuple(
            events,
            maximum=HARD_MAX_RAW_LEDGER_EVENTS - len(self.events),
            label="raw ledger extension",
        )
        if not incoming:
            return self
        return RawFactLedger(events=self.events + incoming, schema=self.schema)

    def by_id(self, occurrence_id: str) -> RawFactOccurrence | None:
        return next((item for item in self.events if item.occurrence_id == occurrence_id), None)

    def events_for(self, logical_key: str) -> tuple[RawFactOccurrence, ...]:
        return self._events_by_logical_key.get(logical_key, ())

    def revision_chain(self, occurrence_id: str) -> tuple[RawFactOccurrence, ...]:
        """Return parent-to-child immutable lineage for one event."""
        index = {item.occurrence_id: item for item in self.events}
        current = index.get(occurrence_id)
        if current is None:
            return ()
        chain: list[RawFactOccurrence] = [current]
        while current.revision_of:
            current = index[current.revision_of]
            chain.append(current)
        return tuple(reversed(chain))

    def select(
        self,
        logical_key: str,
        *,
        as_of: datetime | str,
        clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
        policy: VintagePolicy | str = VintagePolicy.AS_OF,
    ) -> LedgerSelection:
        """Select a named vintage without looking beyond ``as_of``.

        ``source_original`` means the earliest source-event root *visible at
        the requested replay cutoff*. A later backfill may reveal an older
        filing in a newer replay, but cannot alter an earlier replay by being
        inspected in advance.
        ``first_system_known`` is a separate policy and only makes sense for a
        system replay.  ``latest``/``as_of`` choose the latest fully resolved
        duplicate group known at the cutoff.
        """
        normalized_key = _require_text(logical_key, field_name="logical_key")
        cutoff = parse_utc(as_of, field_name="as_of")
        if cutoff is None:  # pragma: no cover - required parameter
            raise ValueError("as_of is required")
        replay_clock = ReplayClock(clock)
        vintage_policy = _vintage_policy(policy)
        candidates = self.events_for(normalized_key)
        candidate_by_id = {item.occurrence_id: item for item in candidates}

        lineage_depth_by_id: dict[str, int] = {}
        source_ready_by_id: dict[str, datetime | None] = {}
        system_ready_by_id: dict[str, datetime] = {}
        for item in candidates:
            parent_id = item.revision_of
            own_source_ready = item.ready_at(ReplayClock.SOURCE_EVENT)
            own_system_ready = item.ready_at(ReplayClock.SYSTEM)
            if own_system_ready is None:  # pragma: no cover - recorded_at is mandatory
                raise ValueError("raw fact system availability clock is missing")
            if parent_id is None:
                lineage_depth_by_id[item.occurrence_id] = 0
                source_ready_by_id[item.occurrence_id] = own_source_ready
                system_ready_by_id[item.occurrence_id] = own_system_ready
                continue
            parent = candidate_by_id.get(parent_id)
            if parent is None:  # pragma: no cover - ledger constructor validates parents
                raise ValueError("raw fact revision parent is missing")
            lineage_depth_by_id[item.occurrence_id] = (
                lineage_depth_by_id[parent_id] + 1
            )
            parent_source_ready = source_ready_by_id[parent_id]
            source_ready_by_id[item.occurrence_id] = (
                max(parent_source_ready, own_source_ready)
                if parent_source_ready is not None and own_source_ready is not None
                else None
            )
            # A revision cannot be exposed before the complete lineage that
            # gives ``revision_of`` meaning is visible. This also prevents a
            # pre-parent replay from leaking the future parent's identifier.
            system_ready_by_id[item.occurrence_id] = max(
                system_ready_by_id[parent_id],
                own_system_ready,
            )

        def lineage_depth(item: RawFactOccurrence) -> int:
            return lineage_depth_by_id[item.occurrence_id]

        def lineage_ready_at(
            item: RawFactOccurrence,
            clock_value: ReplayClock,
        ) -> datetime | None:
            return (
                source_ready_by_id[item.occurrence_id]
                if clock_value is ReplayClock.SOURCE_EVENT
                else system_ready_by_id[item.occurrence_id]
            )

        def replay_item_ready(item: RawFactOccurrence) -> datetime | None:
            return lineage_ready_at(item, replay_clock)

        def group_lineage_ready(
            items: Iterable[RawFactOccurrence],
            clock_value: ReplayClock,
        ) -> datetime | None:
            readiness = [lineage_ready_at(item, clock_value) for item in items]
            if not readiness or any(value is None for value in readiness):
                return None
            return max(value for value in readiness if value is not None)

        def ids_for(
            selected_groups: Iterable[tuple[RawFactOccurrence, ...]],
        ) -> tuple[str, ...]:
            allowed = {
                item.occurrence_id
                for group in selected_groups
                for item in group
            }
            return tuple(
                item.occurrence_id
                for item in candidates
                if item.occurrence_id in allowed
            )

        visible_group_items: dict[str, list[RawFactOccurrence]] = {}
        for item in candidates:
            ready = replay_item_ready(item)
            if ready is not None and ready <= cutoff:
                visible_group_items.setdefault(
                    item.duplicate_group_key,
                    [],
                ).append(item)

        visible_groups: list[
            tuple[str, tuple[RawFactOccurrence, ...], datetime]
        ] = []
        for group_key, group_items in visible_group_items.items():
            group = tuple(group_items)
            ready = group_lineage_ready(group, replay_clock)
            if ready is not None:  # every member was individually gated above
                visible_groups.append((group_key, group, ready))
        visible_ids = ids_for(item[1] for item in visible_groups)

        if (
            vintage_policy is VintagePolicy.FIRST_SYSTEM_KNOWN
            and replay_clock is not ReplayClock.SYSTEM
        ):
            return not_evaluable(
                clock=replay_clock,
                policy=vintage_policy,
                as_of=cutoff,
                logical_key=normalized_key,
                reason="first_system_known requires clock=system",
                candidate_occurrence_ids=visible_ids,
            )

        # Absence, an undated source event, and one or many future-only events
        # are intentionally indistinguishable at this replay cutoff.  Their
        # exact clocks, identifiers, multiplicity, and failure reason are all
        # information from outside the selected replay view.
        if not visible_groups:
            return not_available(
                clock=replay_clock,
                policy=vintage_policy,
                as_of=cutoff,
                logical_key=normalized_key,
                reason="no raw occurrence was available at the requested cutoff",
                candidate_occurrence_ids=(),
            )

        selected_group: tuple[RawFactOccurrence, ...] | None = None
        if vintage_policy is VintagePolicy.SOURCE_ORIGINAL:
            # Original is resolved only from the replay-visible source plane.
            # Scanning a root retained after this cutoff would cause later
            # backfills to rewrite earlier point-in-time answers.
            source_ordered: list[
                tuple[datetime, tuple[RawFactOccurrence, ...]]
            ] = []
            for _, group, _ in visible_groups:
                # Original means a source-lineage root, not merely whichever
                # event carries the smallest timestamp.  The latter would let
                # a malformed or backfilled child masquerade as the original.
                if any(item.revision_of is not None for item in group):
                    continue
                source_ready = group_lineage_ready(
                    group,
                    ReplayClock.SOURCE_EVENT,
                )
                if source_ready is None:
                    return not_available(
                        clock=replay_clock,
                        policy=vintage_policy,
                        as_of=cutoff,
                        logical_key=normalized_key,
                        reason="source_original is unavailable because an occurrence lacks accepted_at",
                        candidate_occurrence_ids=visible_ids,
                    )
                source_ordered.append((source_ready, group))
            if not source_ordered:
                return not_available(
                    clock=replay_clock,
                    policy=vintage_policy,
                    as_of=cutoff,
                    logical_key=normalized_key,
                    reason=(
                        "no source-original occurrence was available at the requested cutoff"
                    ),
                    candidate_occurrence_ids=visible_ids,
                )
            earliest = min(item[0] for item in source_ordered)
            tied_originals = [
                item[1] for item in source_ordered if item[0] == earliest
            ]
            if len(tied_originals) != 1:
                return not_evaluable(
                    clock=replay_clock,
                    policy=vintage_policy,
                    as_of=cutoff,
                    logical_key=normalized_key,
                    reason=(
                        "multiple source-original roots share equal semantic precedence"
                    ),
                    candidate_occurrence_ids=ids_for(tied_originals),
                )
            selected_group = tied_originals[0]
            selected_ready = group_lineage_ready(selected_group, replay_clock)
            if selected_ready is None or selected_ready > cutoff:
                return not_available(
                    clock=replay_clock,
                    policy=vintage_policy,
                    as_of=cutoff,
                    logical_key=normalized_key,
                    reason="the source-original occurrence was not available at the requested cutoff",
                    candidate_occurrence_ids=visible_ids,
                )
        else:
            eligible_groups: list[
                tuple[
                    datetime,
                    datetime,
                    datetime,
                    int,
                    tuple[RawFactOccurrence, ...],
                ]
            ] = []
            for _, group, ready in visible_groups:
                source_ready = group_lineage_ready(
                    group,
                    ReplayClock.SOURCE_EVENT,
                )
                recorded_order = max(item.recorded_at for item in group)
                # An undated source remains orderable in actual-system replay
                # by retention time; unknown never becomes an artificial
                # year-one source event.
                source_order = source_ready or recorded_order
                depth = max(lineage_depth(item) for item in group)
                eligible_groups.append(
                    (ready, source_order, recorded_order, depth, group)
                )
            if not eligible_groups:
                return not_available(
                    clock=replay_clock,
                    policy=vintage_policy,
                    as_of=cutoff,
                    logical_key=normalized_key,
                    reason=(
                        "accepted_at is unavailable for source-event replay"
                        if replay_clock is ReplayClock.SOURCE_EVENT
                        else "no fully resolved occurrence was available at the requested cutoff"
                    ),
                    candidate_occurrence_ids=(),
                )
            if vintage_policy is VintagePolicy.FIRST_SYSTEM_KNOWN:
                # First-system-known is a transaction-time question. If a
                # later source vintage was retained first during a backfill,
                # recorded_at—not source acceptance—wins a publish-batch tie.
                rank = lambda item: (item[0], item[2], item[1], item[3])
                best_rank = min(rank(item) for item in eligible_groups)
            else:
                # Latest/as-of is a source-vintage question after availability
                # gating. System readiness determines only whether a group is
                # admissible; source time and revision depth choose the
                # vintage. This prevents a later-retained old filing from
                # outranking a newer source filing during a backfill.
                rank = lambda item: (item[1], item[3])
                best_rank = max(rank(item) for item in eligible_groups)
            tied = [item for item in eligible_groups if rank(item) == best_rank]
            if len(tied) != 1:
                tied_groups = [item[4] for item in tied]
                return not_evaluable(
                    clock=replay_clock,
                    policy=vintage_policy,
                    as_of=cutoff,
                    logical_key=normalized_key,
                    reason=(
                        "multiple eligible source vintages share equal semantic precedence"
                    ),
                    candidate_occurrence_ids=ids_for(tied_groups),
                )
            selected_group = tied[0][4]

        if selected_group is None:  # pragma: no cover - exhaustive policy handling above
            raise AssertionError("vintage policy did not select a duplicate group")
        if any(item.is_withdrawn for item in selected_group):
            return not_available(
                clock=replay_clock,
                policy=vintage_policy,
                as_of=cutoff,
                logical_key=normalized_key,
                reason="selected source vintage is withdrawn",
                candidate_occurrence_ids=visible_ids,
            )
        if not _duplicates_agree(selected_group):
            return not_evaluable(
                clock=replay_clock,
                policy=vintage_policy,
                as_of=cutoff,
                logical_key=normalized_key,
                reason="conflicting duplicate raw facts cannot be selected",
                candidate_occurrence_ids=visible_ids,
            )
        chosen = _canonical_duplicate_representative(selected_group)
        return LedgerSelection(
            status=AvailabilityStatus.AVAILABLE,
            clock=replay_clock,
            policy=vintage_policy,
            as_of=cutoff,
            logical_key=normalized_key,
            occurrence=chosen,
            candidate_occurrence_ids=visible_ids,
        )

    def select_all(
        self,
        *,
        as_of: datetime | str,
        clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
        policy: VintagePolicy | str = VintagePolicy.AS_OF,
    ) -> tuple[LedgerSelection, ...]:
        keys = sorted(self._events_by_logical_key)
        return tuple(self.select(key, as_of=as_of, clock=clock, policy=policy) for key in keys)

    def select_original(
        self,
        logical_key: str,
        *,
        as_of: datetime | str,
        clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
    ) -> LedgerSelection:
        return self.select(
            logical_key,
            as_of=as_of,
            clock=clock,
            policy=VintagePolicy.SOURCE_ORIGINAL,
        )

    def select_first_system_known(
        self,
        logical_key: str,
        *,
        as_of: datetime | str,
    ) -> LedgerSelection:
        return self.select(
            logical_key,
            as_of=as_of,
            clock=ReplayClock.SYSTEM,
            policy=VintagePolicy.FIRST_SYSTEM_KNOWN,
        )

    def select_latest(
        self,
        logical_key: str,
        *,
        as_of: datetime | str,
        clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
    ) -> LedgerSelection:
        return self.select(logical_key, as_of=as_of, clock=clock, policy=VintagePolicy.LATEST)

    def select_as_of(
        self,
        logical_key: str,
        *,
        as_of: datetime | str,
        clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
    ) -> LedgerSelection:
        return self.select(logical_key, as_of=as_of, clock=clock, policy=VintagePolicy.AS_OF)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "events": [item.to_dict() for item in self.events],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RawFactLedger":
        """Restore from an already-decoded canonical raw-ledger mapping.

        This validates the exact value shape emitted by :meth:`to_dict`, but a
        Python mapping cannot prove that the original JSON had unique keys or
        canonical byte spelling.  Use :meth:`from_json_bytes` at every external
        snapshot boundary.
        """
        raw = _strict_wire_mapping(
            value,
            field_name="raw fact ledger",
            expected_fields=frozenset({"schema", "events"}),
        )
        schema = _strict_wire_required_text(
            raw["schema"],
            field_name="schema",
            strip=False,
        )
        event_wires = _strict_wire_list(
            raw["events"],
            field_name="raw ledger events",
            maximum=HARD_MAX_RAW_LEDGER_EVENTS,
        )

        # Start with the exact compact representation of an empty canonical
        # ledger.  Each additional array member contributes its canonical
        # bytes plus one comma after the first item, so no whole-ledger JSON
        # string needs to be materialized before the aggregate size is known.
        wire_bytes = len(canonical_json({"schema": schema, "events": []}).encode("utf-8"))
        if wire_bytes > HARD_MAX_RAW_LEDGER_WIRE_BYTES:
            raise ValueError(
                "raw fact ledger exceeds bounded wire size "
                f"{HARD_MAX_RAW_LEDGER_WIRE_BYTES}"
            )
        events: list[RawFactOccurrence] = []
        for index, event_wire in enumerate(event_wires):
            event = RawFactOccurrence.from_dict(event_wire)
            wire_bytes += len(canonical_json(event.to_dict()).encode("utf-8"))
            if index:
                wire_bytes += 1
            if wire_bytes > HARD_MAX_RAW_LEDGER_WIRE_BYTES:
                raise ValueError(
                    "raw fact ledger exceeds bounded wire size "
                    f"{HARD_MAX_RAW_LEDGER_WIRE_BYTES}"
                )
            events.append(event)

        # Constructor validation is deliberately retained: it checks ID
        # uniqueness, revision parent order, economic-key preservation, and
        # source-event lineage chronology after every event has passed its own
        # canonical decoder.
        return cls(events=tuple(events), schema=schema)

    @classmethod
    def from_json_bytes(cls, value: bytes) -> "RawFactLedger":
        """Restore an external canonical JSON payload without lossy pre-decoding.

        The byte ceiling is enforced before UTF-8 decoding or JSON parsing.
        Every object is parsed with duplicate-key rejection, then the restored
        ledger must serialize to the exact same canonical bytes.
        """
        if type(value) is not bytes:
            raise TypeError("raw fact ledger payload must be bytes")
        if len(value) > HARD_MAX_RAW_LEDGER_WIRE_BYTES:
            raise ValueError(
                "raw fact ledger exceeds bounded wire size "
                f"{HARD_MAX_RAW_LEDGER_WIRE_BYTES} before parsing"
            )
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("raw fact ledger payload is not valid UTF-8") from exc

        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            parsed: dict[str, Any] = {}
            for key, item in pairs:
                if key in parsed:
                    raise ValueError(
                        f"raw fact ledger JSON contains duplicate object key: {key}"
                    )
                parsed[key] = item
            return parsed

        def reject_nonfinite_constant(constant: str) -> Any:
            raise ValueError(
                f"raw fact ledger JSON contains non-finite number: {constant}"
            )

        try:
            decoded = json.loads(
                text,
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=reject_nonfinite_constant,
            )
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValueError(f"raw fact ledger payload is invalid JSON: {exc}") from exc
        ledger = cls.from_dict(decoded)
        canonical = _canonical_wire_bytes(
            ledger.to_dict(),
            field_name="raw fact ledger",
            maximum=HARD_MAX_RAW_LEDGER_WIRE_BYTES,
        )
        if value != canonical:
            raise ValueError("raw fact ledger payload is not the exact canonical JSON bytes")
        return ledger


def select_vintage(
    events: Iterable[RawFactOccurrence],
    logical_key: str,
    *,
    as_of: datetime | str,
    clock: ReplayClock | str = ReplayClock.SOURCE_EVENT,
    policy: VintagePolicy | str = VintagePolicy.AS_OF,
) -> LedgerSelection:
    """Functional convenience wrapper for an ephemeral immutable ledger."""
    normalized = _bounded_event_tuple(
        events,
        maximum=HARD_MAX_RAW_LEDGER_EVENTS,
        label="raw ledger events",
    )
    return RawFactLedger(normalized).select(
        logical_key,
        as_of=as_of,
        clock=clock,
        policy=policy,
    )
