"""Precision-first, document-row-scoped registration-fee-table observations.

This is deliberately narrower than an instrument or issuer-state engine.  It
reads the retained *complete submission* identified by a source manifest,
locates an exact primary or ``EX-FILING FEES`` child table inside those immutable
bytes, and emits only row/security-scoped directly displayed cells. It never totals rows, infers
remaining capacity, treats a registration as an active instrument, or creates
a dilution/risk/probability claim.

The complete submission is the canonical parser path. Wave 1 does not retain a
separate ``EX-FILING FEES`` manifest, but the child remains inside the verified
submission bytes and retains exact child/table/row/cell provenance here.
"""
from __future__ import annotations

import builtins
import _markupbase as _stdlib_markupbase
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import MISSING, dataclass, fields as dataclass_fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import dis
import hashlib
import hmac
import html as _stdlib_html
import html.entities as _stdlib_html_entities
import html.parser as _stdlib_html_parser
from html.parser import HTMLParser
import inspect
from importlib.metadata import version as distribution_version
import json
from pathlib import Path
import re
import sys
import sysconfig
from types import CodeType, MappingProxyType, ModuleType
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.event_spine import make_stable_span
from engine.capital_structure.source_identity import (
    validate_manifest_content_binding,
    validate_manifest_ledger,
    validate_manifest_retained_bytes_binding,
)


_JSONSCHEMA_RELEASE = "4.26.0"
if distribution_version("jsonschema") != _JSONSCHEMA_RELEASE:
    raise RuntimeError(
        f"document-term authority requires jsonschema {_JSONSCHEMA_RELEASE}"
    )


DOCUMENT_TERM_SCHEMA = "capital_structure.document_term_observation.v1"
PARSER_VERSION = "capital-structure-document-terms/1.1.0"


@dataclass(frozen=True)
class SemanticEntrypoint:
    """One named executable root in a released parser's semantic closure."""

    role: str
    implementation: Callable[..., Any]


@dataclass(frozen=True)
class SemanticDispatchRoot:
    """A concrete receiver plus methods invoked through its MRO at runtime."""

    role: str
    receiver: type[Any]
    methods: tuple[str, ...]
    data_attributes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParserRuntimeBundle:
    """Reviewed exact runtime-dispatch digest for one supported interpreter."""

    dependency_count: int
    dependency_manifest_sha256: str
    implementation_sha256: str


@dataclass(frozen=True)
class ParserRuntimeFingerprint:
    """Reviewed CPython ABI and trusted on-disk stdlib source identity."""

    implementation: str
    version_info: tuple[int, int, int, str, int]
    cache_tag: str
    stdlib_source_sha256: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ParserSemanticBundle:
    """Portable project golden; runtime authority has a separate trust root."""

    entrypoints: tuple[SemanticEntrypoint, ...]
    dispatch_roots: tuple[SemanticDispatchRoot, ...]
    dependency_count: int
    dependency_manifest_sha256: str


@dataclass(frozen=True)
class ParserRegistration:
    """One retained deterministic extractor implementation.

    Parser versions are evidence provenance, not free-form release labels. A
    historic direct row is trusted only when its declared version remains in
    this closed registry, its project implementation matches the portable
    release golden, and its inherited runtime matches an immutable reviewed
    build/source/digest allowlist entry.
    """

    version: str
    implementation_sha256: str
    extractor: Callable[[Mapping[str, Any], bytes | None, str], list[dict[str, Any]]]
    semantic_bundle: ParserSemanticBundle


@dataclass(frozen=True)
class _TestParserLane:
    """Opaque, explicit capability lane for synthetic historical-parser tests."""

    capability: object
    registrations: Mapping[str, ParserRegistration]


_PRIVATE_TEST_PARSER_CAPABILITY = object()


@dataclass(frozen=True)
class _AuthorityPolicy:
    """Sealed source/schema gates captured independently from parser releases."""

    entrypoints: tuple[SemanticEntrypoint, ...]
    dependency_count: int
    dependency_manifest_sha256: str
    implementation_sha256: str
    alias_bindings: tuple[tuple[str, Callable[..., Any]], ...]
    manifest_ledger_validator: Callable[[Sequence[Mapping[str, Any]]], None]
    manifest_content_validator: Callable[[Mapping[str, Any]], None]
    retained_bytes_validator: Callable[[Mapping[str, Any], bytes | None], None]

# The names mirror direct SEC table headers.  Their economic type/unit is row
# dependent: an "amount to be registered" can be shares, units, securities, or
# debt principal.  Never attach a generic unit before reading the security row.
TERM_NAMES = (
    "amount_to_be_registered",
    "proposed_maximum_offering_price_per_unit",
    "proposed_maximum_aggregate_offering_price",
    "registration_fee",
    "filing_fee_rate",
)

REGISTRATION_FEE_FORMS = frozenset({
    "S-1", "S-1/A", "F-1", "F-1/A", "S-3", "S-3/A", "S-3ASR",
    "F-3", "F-3/A", "F-3ASR", "F-10", "F-10/A", "1-A", "1-A/A", "1-A POS",
})

_DOCUMENT_RE = re.compile(br"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)
_TEXT_RE = re.compile(br"<TEXT>\s*(.*?)(?:</TEXT>|$)", re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(br"<table\b[^>]*>.*?</table\s*>", re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(br"<tr\b[^>]*>.*?</tr\s*>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(
    br"<(td|th)\b([^>]*)>(.*?)</\1\s*>", re.IGNORECASE | re.DOTALL,
)
_COLSPAN_RE = re.compile(br"\bcolspan\s*=\s*[\"']?\s*(\d+)", re.IGNORECASE)
_TYPE_RE = re.compile(br"<TYPE>\s*([^\r\n<]+)", re.IGNORECASE)
_SEQUENCE_RE = re.compile(br"<SEQUENCE>\s*([^\r\n<]+)", re.IGNORECASE)
_FILENAME_RE = re.compile(br"<FILENAME>\s*([^\r\n<]+)", re.IGNORECASE)
_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
_SIMPLE_NUMBER_RE = re.compile(r"^\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)$")
_DENOMINATED_RATE_RE = re.compile(
    r"^\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s+per\s+"
    r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)$",
    re.IGNORECASE,
)
_BYTE_LOCATOR_RE = re.compile(r"bytes:(\d+)-(\d+)$")
_SEMANTIC_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCUMENT_TERM_SCHEMA_PATH = (
    _SEMANTIC_REPO_ROOT
    / "contracts"
    / "capital_structure_document_term_observation.schema.json"
)
# These source files contain the inherited HTML dispatch, character-reference
# conversion/data, and the regular-expression entrypoint used by that dispatch.
# Their paths are resolved beneath the active interpreter's stdlib root and
# must also be the live modules' actual origins.  The tuple is deliberately a
# reviewed closed inventory rather than a runtime-discovered module walk.
_PARSER_RUNTIME_STDLIB_SOURCES = (
    ("_markupbase", "_markupbase.py", _stdlib_markupbase),
    ("html", "html/__init__.py", _stdlib_html),
    ("html.entities", "html/entities.py", _stdlib_html_entities),
    ("html.parser", "html/parser.py", _stdlib_html_parser),
    ("re", "re/__init__.py", re),
)
_DOCUMENT_TERM_SCHEMA_SHA256 = (
    "7098f3f4e6e17185da1b7c2ee1d79fa5966e0ac3cfb96c0d6385573f0a0bf78c"
)
_ZERO_AUTHORITY_KEYS = frozenset({
    "authority",
    "instrument_authority",
    "capacity_authority",
    "risk_authority",
    "probability_authority",
    "rank_authority",
    "sizing_authority",
    "entry_authority",
    "trade_authority",
    "prophet_authority",
    "may_rank",
    "may_gate",
    "may_size",
    "may_recommend",
    "may_trade",
})


class DocumentTermCompileDegraded(RuntimeError):
    """One retained source object could not be read exactly; do not publish a partial run."""

    def __init__(self, failures: Sequence[Mapping[str, Any]]):
        self.failures = [dict(item) for item in failures]
        super().__init__(
            "capital-structure document-term compile degraded with "
            f"{len(self.failures)} source failure(s)"
        )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _digest_id(prefix: str, body: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]


def _parse_time(value: Any, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: Any, field: str) -> str:
    return _parse_time(value, field).isoformat().replace("+00:00", "Z")


def _assert_zero_authority(value: Any, *, path: str = "<root>") -> None:
    """Reject any attempt to smuggle decision authority into direct facts."""
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}" if path != "<root>" else key
            if key in _ZERO_AUTHORITY_KEYS or key.endswith("_authority"):
                raise ValueError(
                    "document-term zero-authority invariant violation at "
                    f"{child_path}"
                )
            _assert_zero_authority(item, path=child_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_zero_authority(item, path=f"{path}[{index}]")


_SCHEMA_DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
_SCHEMA_DATETIME_RE = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z",
)
_SCHEMA_URI_SCHEME_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*:")


def _schema_date_format(instance: Any) -> bool:
    if not isinstance(instance, str):
        return True
    if _SCHEMA_DATE_RE.fullmatch(instance) is None:
        return False
    try:
        date.fromisoformat(instance)
    except ValueError:
        return False
    return True


def _schema_datetime_format(instance: Any) -> bool:
    if not isinstance(instance, str):
        return True
    if _SCHEMA_DATETIME_RE.fullmatch(instance) is None:
        return False
    try:
        parsed = datetime.fromisoformat(
            instance[:-1] + "+00:00" if instance.endswith("Z") else instance,
        )
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _schema_uri_format(instance: Any) -> bool:
    if not isinstance(instance, str):
        return True
    if (
        _SCHEMA_URI_SCHEME_RE.match(instance) is None
        or any(character.isspace() or ord(character) < 32 for character in instance)
    ):
        return False
    try:
        return bool(urlsplit(instance).scheme)
    except ValueError:
        return False


_SCHEMA_FORMAT_BINDINGS = (
    ("date", _schema_date_format, ()),
    ("date-time", _schema_datetime_format, ()),
    ("uri", _schema_uri_format, ()),
)


def _make_document_term_contract_validator(
    schema_path: Path,
    schema_sha256: str,
    validator_class: type[Any],
    format_checker_class: type[Any],
    schema_format_bindings: tuple[
        tuple[str, Callable[[Any], bool], tuple[type[BaseException], ...]], ...
    ],
) -> Callable[[], Callable[[Mapping[str, Any]], Any]]:
    """Prebuild and seal the actually invoked schema-validation method."""
    def descriptor_functions(value: Any) -> tuple[Callable[..., Any], ...]:
        if inspect.isfunction(value):
            return (value,)
        if isinstance(value, (staticmethod, classmethod)):
            return (value.__func__,)
        if isinstance(value, property):
            return tuple(
                function
                for function in (value.fget, value.fset, value.fdel)
                if function is not None
            )
        return ()

    def descriptor_codes(value: Any) -> tuple[CodeType, ...]:
        return tuple(
            function.__code__ for function in descriptor_functions(value)
        )

    def function_dependency_bindings(
        roots: Sequence[Callable[..., Any]],
    ) -> tuple[
        tuple[
            Callable[..., Any],
            CodeType,
            tuple[tuple[str, Any, CodeType | None], ...],
        ],
        ...,
    ]:
        pending = list(roots)
        seen: set[Callable[..., Any]] = set()
        bindings: list[
            tuple[
                Callable[..., Any],
                CodeType,
                tuple[tuple[str, Any, CodeType | None], ...],
            ]
        ] = []
        while pending:
            function = pending.pop()
            if not inspect.isfunction(function) or function in seen:
                continue
            seen.add(function)
            globals_bound: list[tuple[str, Any, CodeType | None]] = []
            for name in sorted(set(function.__code__.co_names)):
                if name not in function.__globals__:
                    continue
                value = function.__globals__[name]
                globals_bound.append(
                    (name, value, getattr(value, "__code__", None)),
                )
                if (
                    inspect.isfunction(value)
                    and str(value.__module__).startswith(
                        ("jsonschema.", "referencing."),
                    )
                ):
                    pending.append(value)
            bindings.append(
                (function, function.__code__, tuple(globals_bound)),
            )
        return tuple(
            sorted(
                bindings,
                key=lambda item: (
                    str(item[0].__module__), str(item[0].__qualname__),
                ),
            ),
        )

    def execution_surface(
        cls: type[Any],
    ) -> tuple[tuple[str, Any, tuple[CodeType, ...]], ...]:
        names = {
            name
            for owner in cls.__mro__
            if owner is not object
            for name, value in vars(owner).items()
            if callable(value)
            or isinstance(value, (staticmethod, classmethod, property))
        }
        bindings: list[tuple[str, Any, tuple[CodeType, ...]]] = []
        for name in sorted(names):
            for owner in cls.__mro__:
                if name in vars(owner):
                    descriptor = vars(owner)[name]
                    bindings.append((name, descriptor, descriptor_codes(descriptor)))
                    break
        return tuple(bindings)

    encoded = schema_path.read_bytes()
    if not hmac.compare_digest(hashlib.sha256(encoded).hexdigest(), schema_sha256):
        raise ValueError("document-term observation schema release digest mismatch")
    schema = json.loads(encoded.decode("utf-8"))
    validator_class.check_schema(schema)
    original_iter_errors = validator_class.iter_errors
    validator_registry_bindings = tuple(
        (keyword, implementation, getattr(implementation, "__code__", None))
        for keyword, implementation in sorted(validator_class.VALIDATORS.items())
    )
    type_checker_bindings = tuple(
        (name, implementation, getattr(implementation, "__code__", None))
        for name, implementation in sorted(
            validator_class.TYPE_CHECKER._type_checkers.items(),
        )
    )
    format_checker_bindings = tuple(
        (
            name,
            implementation,
            getattr(implementation, "__code__", None),
            raises,
        )
        for name, implementation, raises in schema_format_bindings
    )
    execution_surfaces = (
        (validator_class, execution_surface(validator_class)),
        (format_checker_class, execution_surface(format_checker_class)),
    )
    dependency_roots = [
        implementation
        for _name, implementation, _code in (
            *validator_registry_bindings,
            *type_checker_bindings,
        )
    ]
    dependency_roots.extend(
        implementation
        for _name, implementation, _code, _raises in format_checker_bindings
    )
    validator_runtime_methods = frozenset({
        "__init__", "__attrs_post_init__", "iter_errors", "descend",
        "evolve", "is_type", "_validate_reference", "is_valid",
    })
    format_checker_runtime_methods = frozenset({
        "__init__", "check", "conforms",
    })
    dependency_roots.extend(
        function
        for cls, bindings in execution_surfaces
        for name, descriptor, _codes in bindings
        if name in (
            validator_runtime_methods
            if cls is validator_class
            else format_checker_runtime_methods
        )
        for function in descriptor_functions(descriptor)
    )
    schema_execution_dependencies = function_dependency_bindings(dependency_roots)

    def _document_term_contract_validator() -> Callable[[Mapping[str, Any]], Any]:
        """Recheck schema bytes and executable class bindings before each use."""
        current = schema_path.read_bytes()
        digest = hashlib.sha256(current).hexdigest()
        if not hmac.compare_digest(digest, schema_sha256):
            raise ValueError("document-term observation schema release digest mismatch")
        for cls, bindings in execution_surfaces:
            for name, expected, expected_codes in bindings:
                actual_owner = next(
                    (owner for owner in cls.__mro__ if name in vars(owner)),
                    None,
                )
                if (
                    actual_owner is None
                    or vars(actual_owner)[name] is not expected
                ):
                    raise ValueError(
                        "document-term schema validator executable binding changed"
                    )
                actual_codes = descriptor_codes(vars(actual_owner)[name])
                if (
                    len(actual_codes) != len(expected_codes)
                    or any(
                        actual is not expected_code
                        for actual, expected_code in zip(
                            actual_codes, expected_codes, strict=True,
                        )
                    )
                ):
                    raise ValueError(
                        "document-term schema validator executable binding changed"
                    )
        for function, expected_code, globals_bound in schema_execution_dependencies:
            if function.__code__ is not expected_code:
                raise ValueError(
                    "document-term schema validator executable binding changed"
                )
            for name, expected, expected_code in globals_bound:
                if name not in function.__globals__:
                    raise ValueError(
                        "document-term schema validator executable binding changed"
                    )
                actual = function.__globals__[name]
                if (
                    actual is not expected
                    or getattr(actual, "__code__", None) is not expected_code
                ):
                    raise ValueError(
                        "document-term schema validator executable binding changed"
                    )
        current_registry = validator_class.VALIDATORS
        if set(current_registry) != {
            name
            for name, _implementation, _code in validator_registry_bindings
        }:
            raise ValueError(
                "document-term schema validator executable binding changed"
            )
        for keyword, expected_implementation, expected_code in (
            validator_registry_bindings
        ):
            implementation = current_registry[keyword]
            if (
                implementation is not expected_implementation
                or getattr(implementation, "__code__", None) is not expected_code
            ):
                raise ValueError(
                    "document-term schema validator executable binding changed"
                )
        current_type_checkers = validator_class.TYPE_CHECKER._type_checkers
        if set(current_type_checkers) != {
            name for name, _implementation, _code in type_checker_bindings
        }:
            raise ValueError(
                "document-term schema validator executable binding changed"
            )
        for name, expected_implementation, expected_code in type_checker_bindings:
            implementation = current_type_checkers[name]
            if (
                implementation is not expected_implementation
                or getattr(implementation, "__code__", None) is not expected_code
            ):
                raise ValueError(
                    "document-term schema validator executable binding changed"
                )
        format_checker = format_checker_class(formats=())
        if format_checker.checkers:
            raise ValueError(
                "document-term schema validator executable binding changed"
            )
        current_format_checkers = MappingProxyType({
            name: (implementation, raises)
            for name, implementation, _code, raises in format_checker_bindings
        })
        format_checker.checkers = current_format_checkers
        for name, expected_implementation, expected_code, expected_raises in (
            format_checker_bindings
        ):
            implementation, raises = current_format_checkers[name]
            if (
                implementation is not expected_implementation
                or getattr(implementation, "__code__", None) is not expected_code
                or raises != expected_raises
            ):
                raise ValueError(
                    "document-term schema validator executable binding changed"
                )
        fresh_schema = json.loads(current.decode("utf-8"))
        validator = validator_class(
            fresh_schema, format_checker=format_checker,
        )
        return original_iter_errors.__get__(validator, validator_class)

    return _document_term_contract_validator


_document_term_contract_validator = _make_document_term_contract_validator(
    _DOCUMENT_TERM_SCHEMA_PATH,
    _DOCUMENT_TERM_SCHEMA_SHA256,
    Draft202012Validator, FormatChecker, _SCHEMA_FORMAT_BINDINGS,
)


def _validate_document_term_records_contract(
    records: Sequence[Mapping[str, Any]], *, label: str,
) -> None:
    """Apply the closed schema and zero-authority law to every admitted row."""
    iter_errors = _document_term_contract_validator()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"{label} row {index} must be an object")
        _assert_zero_authority(record)
        errors = sorted(
            iter_errors(record),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            joined = "; ".join(
                f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
                f"{error.message}"
                for error in errors[:5]
            )
            raise ValueError(
                f"{label} row {index} document-term contract violation: {joined}"
            )


def _make_validate_document_term_contract(
    policy_validator: Callable[[], _AuthorityPolicy],
    records_contract_validator: Callable[..., None],
) -> Callable[[Mapping[str, Any]], None]:
    """Build a sealed single-record contract gate for downstream projections."""
    def validate_document_term_contract(record: Mapping[str, Any]) -> None:
        """Admit one direct row through the closed schema and zero-authority law."""
        if globals().get("_validated_authority_policy") is not policy_validator:
            raise ValueError("document-term authority policy validator binding changed")
        if (
            globals().get("_validate_document_term_records_contract")
            is not records_contract_validator
        ):
            raise ValueError("document-term closed-contract binding changed")
        policy_validator()
        records_contract_validator(
            [record], label="document-term single-record contract",
        )

    return validate_document_term_contract


def _decode(raw: bytes) -> str:
    """Decode only for structural parsing; all evidence hashes retain source bytes."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _tag_value(block: bytes, pattern: re.Pattern[bytes]) -> str | None:
    match = pattern.search(block)
    if not match:
        return None
    return _decode(match.group(1)).strip() or None


def _normalized_form(value: str) -> str:
    return " ".join(value.upper().split())


@dataclass(frozen=True)
class SubmissionDocument:
    document_type: str
    sequence: str | None
    filename: str | None
    text: bytes
    text_start: int
    text_end: int


def _eligible_documents(raw: bytes, form: str) -> list[SubmissionDocument]:
    """Return exact primary and EX-FILING FEES SGML TEXT segments.

    Modern EDGAR filings commonly put the structured fee table in a dedicated
    ``EX-FILING FEES`` child.  Because the retained complete submission contains
    every child, no additional network/source-manifest dependency is required.
    """
    wanted = _normalized_form(form)
    candidates: list[SubmissionDocument] = []
    for block_match in _DOCUMENT_RE.finditer(raw):
        block = block_match.group(1)
        document_type = _tag_value(block, _TYPE_RE)
        if not document_type:
            continue
        normalized = _normalized_form(document_type)
        if normalized not in {wanted, "EX-FILING FEES"}:
            continue
        text_match = _TEXT_RE.search(block)
        if not text_match:
            continue
        absolute_start = block_match.start(1) + text_match.start(1)
        candidates.append(SubmissionDocument(
            document_type=normalized,
            sequence=_tag_value(block, _SEQUENCE_RE),
            filename=_tag_value(block, _FILENAME_RE),
            text=text_match.group(1),
            text_start=absolute_start,
            text_end=absolute_start + len(text_match.group(1)),
        ))
    return candidates


class _CellText(HTMLParser):
    """Decode one cell while excluding explicit superscript footnote markers."""

    def __init__(self) -> None:
        # Name the inherited implementation explicitly. The released semantic
        # bundle separately pins this exact descriptor and all ``self.*``
        # dispatch reachable from it, rather than trusting the base-class name.
        HTMLParser.__init__(self, convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "sup":
            self._ignored_depth += 1
        elif lowered == "br" and not self._ignored_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "sup" and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def _label(value: str) -> str:
    cleaned = _clean_text(value).lower()
    cleaned = re.sub(r"\(\s*\d+\s*\)", "", cleaned)
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def _term_for_header(value: str) -> str | None:
    normalized = _label(value)
    if "amount to be registered" in normalized:
        return "amount_to_be_registered"
    if "proposed maximum offering price per unit" in normalized:
        return "proposed_maximum_offering_price_per_unit"
    if "proposed maximum aggregate offering price" in normalized:
        return "proposed_maximum_aggregate_offering_price"
    if "amount of registration fee" in normalized or "amount of filing fee" in normalized:
        return "registration_fee"
    if normalized == "fee rate" or "filing fee rate" in normalized:
        return "filing_fee_rate"
    return None


@dataclass(frozen=True)
class TableCell:
    raw: bytes
    text: str
    start: int
    end: int
    column_start: int
    column_span: int


@dataclass(frozen=True)
class TableRow:
    raw: bytes
    start: int
    end: int
    cells: tuple[TableCell, ...]

    def cell_at(self, column: int) -> TableCell | None:
        for cell in self.cells:
            if cell.column_start <= column < cell.column_start + cell.column_span:
                return cell
        return None


@dataclass(frozen=True)
class FeeTable:
    raw: bytes
    start: int
    end: int
    document: SubmissionDocument
    table_index: int
    rows: tuple[TableRow, ...]
    header_index: int
    columns: Mapping[str, int]
    security_column: int | None
    duplicate_headers: tuple[str, ...]


def _cell_text(raw_inner: bytes) -> str:
    parser = _CellText()
    try:
        parser.feed(_decode(raw_inner))
        parser.close()
    except Exception:  # noqa: BLE001 - malformed public HTML becomes a safe empty cell
        return ""
    return _clean_text(parser.text())


def _table_rows(table_raw: bytes, absolute_start: int) -> tuple[TableRow, ...]:
    rows: list[TableRow] = []
    for row_match in _ROW_RE.finditer(table_raw):
        row_raw = row_match.group(0)
        row_start = absolute_start + row_match.start()
        cells: list[TableCell] = []
        column = 0
        for cell_match in _CELL_RE.finditer(row_raw):
            attrs = cell_match.group(2)
            colspan_match = _COLSPAN_RE.search(attrs)
            span = max(1, int(colspan_match.group(1))) if colspan_match else 1
            cell_start = row_start + cell_match.start()
            cell_raw = cell_match.group(0)
            cells.append(TableCell(
                raw=cell_raw,
                text=_cell_text(cell_match.group(3)),
                start=cell_start,
                end=cell_start + len(cell_raw),
                column_start=column,
                column_span=span,
            ))
            column += span
        if cells:
            rows.append(TableRow(
                raw=row_raw, start=row_start, end=row_start + len(row_raw),
                cells=tuple(cells),
            ))
    return tuple(rows)


def _security_header(value: str) -> bool:
    normalized = _label(value)
    return (
        ("title of each class" in normalized and "securit" in normalized)
        or normalized in {"security type", "title of securities", "security class title"}
    )


def _parse_fee_tables(document: SubmissionDocument, start_index: int) -> list[FeeTable]:
    """Find only tables whose actual cells name direct SEC fee-table fields."""
    candidates: list[FeeTable] = []
    for local_index, match in enumerate(_TABLE_RE.finditer(document.text)):
        absolute_start = document.text_start + match.start()
        rows = _table_rows(match.group(0), absolute_start)
        header_index = -1
        columns: dict[str, int] = {}
        security_column: int | None = None
        duplicate_headers: set[str] = set()
        for index, row in enumerate(rows):
            found: dict[str, int] = {}
            for cell in row.cells:
                name = _term_for_header(cell.text)
                if name is not None:
                    if name in found:
                        duplicate_headers.add(name)
                    else:
                        found[name] = cell.column_start
                if _security_header(cell.text):
                    if security_column is not None:
                        duplicate_headers.add("security_title")
                    else:
                        security_column = cell.column_start
            if len(found) >= 2:
                header_index = index
                columns = found
                break
        if header_index >= 0:
            candidates.append(FeeTable(
                raw=match.group(0), start=absolute_start,
                end=document.text_start + match.end(), document=document,
                table_index=start_index + local_index, rows=rows,
                header_index=header_index, columns=columns,
                security_column=security_column,
                duplicate_headers=tuple(sorted(duplicate_headers)),
            ))
    return candidates


@dataclass(frozen=True)
class ParsedNumber:
    disposition: str
    reason: str
    value: str | None
    scale: str | None


def _decimal_string(value: str) -> str | None:
    try:
        parsed = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _strip_footnote_markers(value: str) -> str:
    cleaned = value.strip()
    marker = r"(?:\(\s*\d+\s*\)|\[\s*\d+\s*\]|[*†‡]+)"
    prior = None
    while prior != cleaned:
        prior = cleaned
        cleaned = re.sub(rf"^{marker}\s*", "", cleaned)
        cleaned = re.sub(rf"\s*{marker}$", "", cleaned)
    return cleaned.strip()


def _parse_number(raw_text: str, *, allow_denominated_rate: bool = False) -> ParsedNumber:
    """Parse a complete cell, never the first convenient numeric substring."""
    visible = _clean_text(raw_text)
    if not visible or visible.lower() in {"n/a", "na", "not applicable", "--", "—", "-"}:
        return ParsedNumber("unavailable", "header_without_direct_value", None, None)
    cleaned = _strip_footnote_markers(visible)
    if allow_denominated_rate:
        rate = _DENOMINATED_RATE_RE.fullmatch(cleaned)
        if rate:
            numerator = _decimal_string(rate.group(1))
            denominator = _decimal_string(rate.group(2))
            if numerator is not None and denominator not in {None, "0"}:
                return ParsedNumber("observed", "direct_table_value", numerator, denominator)
    simple = _SIMPLE_NUMBER_RE.fullmatch(cleaned)
    if simple:
        parsed = _decimal_string(simple.group(1))
        if parsed is not None:
            return ParsedNumber("observed", "direct_table_value", parsed, "1")
    tokens = _NUMBER_TOKEN_RE.findall(cleaned)
    if len(tokens) > 1:
        return ParsedNumber("ambiguous", "multiple_numeric_tokens", None, None)
    return ParsedNumber("ambiguous", "unsupported_dimensional_value", None, None)


def _root_span(manifest: Mapping[str, Any]) -> dict[str, str]:
    document = manifest.get("document") or {}
    manifest_id = str(manifest["manifest_id"])
    digest = str(document.get("content_sha256") or "")
    byte_length = int(document.get("byte_length") or 0)
    for raw_span in manifest.get("spans") or []:
        if not isinstance(raw_span, Mapping):
            continue
        if (
            str(raw_span.get("text_sha256") or "").lower() == digest.lower()
            and str(raw_span.get("locator_type") or "") == "document"
            and str(raw_span.get("locator") or "") == f"bytes:0-{byte_length}"
        ):
            return {
                "manifest_id": manifest_id,
                "span_id": str(raw_span["span_id"]),
                "locator_type": "document",
                "locator": str(raw_span["locator"]),
                "text_sha256": digest,
            }
    # The manifest contract normally makes this unreachable. Preserve a direct
    # deterministic fallback so the caller gets a clear contract failure later.
    return make_stable_span(
        manifest_id, b"", locator_type="document", locator=f"bytes:0-{byte_length}"
    )


def _child_locator(document: SubmissionDocument) -> str:
    return (
        f"type={document.document_type}:sequence={document.sequence or 'unknown'}:"
        f"filename={document.filename or 'unknown'}"
    )


def _table_span(manifest_id: str, table: FeeTable) -> dict[str, str]:
    return make_stable_span(
        manifest_id,
        table.raw,
        locator_type="table",
        locator=(
            f"complete_submission:{_child_locator(table.document)}:"
            f"table={table.table_index}:bytes:{table.start}-{table.end}"
        ),
    )


def _row_span(manifest_id: str, table: FeeTable, row: TableRow, row_index: int) -> dict[str, str]:
    return make_stable_span(
        manifest_id, row.raw, locator_type="text_range",
        locator=(
            f"complete_submission:{_child_locator(table.document)}:table={table.table_index}:"
            f"row={row_index}:bytes:{row.start}-{row.end}"
        ),
    )


def _cell_span(
    manifest_id: str, table: FeeTable, row: TableRow, row_index: int,
    cell: TableCell, role: str,
) -> dict[str, str]:
    return make_stable_span(
        manifest_id, cell.raw, locator_type="text_range",
        locator=(
            f"complete_submission:{_child_locator(table.document)}:table={table.table_index}:"
            f"row={row_index}:cell={cell.column_start}:role={role}:bytes:{cell.start}-{cell.end}"
        ),
    )


def _unique_spans(spans: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for span in spans:
        span_id = str(span.get("span_id") or "")
        if span_id and span_id not in seen:
            seen.add(span_id)
            output.append(dict(span))
    return output


def _document_evidence(
    manifest: Mapping[str, Any], spans: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    document = manifest.get("document") or {}
    rights = manifest.get("rights") or {}
    privacy = manifest.get("privacy") or {}
    return {
        "source_manifest_id": str(manifest["manifest_id"]),
        "source_document_sha256": str(document["content_sha256"]),
        "rights_class": str(rights.get("redistribution_class") or "unknown"),
        "privacy_classification": str(privacy.get("classification") or "unknown"),
        "contains_personal_data": bool(privacy.get("contains_personal_data")),
        "publication": {
            "disposition": "public_fact_only",
            "excerpt_char_count": 0,
            "personal_data_redacted": False,
        },
        "spans": _unique_spans(spans),
    }


def _empty_value() -> dict[str, Any]:
    return {"raw_text": None, "value": None, "unit": None, "currency": None, "scale": None}


def _direct_value(
    raw_text: str, value: str, unit: str, currency: str | None, scale: str,
) -> dict[str, Any]:
    return {
        "raw_text": raw_text[:500], "value": value, "unit": unit,
        "currency": currency, "scale": scale,
    }


def _row_id(manifest_id: str, table: FeeTable, row: TableRow) -> str:
    return _digest_id(
        "fee-row:cs:",
        {"manifest_id": manifest_id, "table_start": table.start, "row_start": row.start, "row_end": row.end},
    )


def _logical_observation_id(manifest_id: str, row_id: str | None, name: str) -> str:
    return _digest_id(
        "document-term-slot:cs:",
        {"manifest_id": manifest_id, "row_id": row_id or "document", "term": name},
    )


def _classify_security(title: str) -> str:
    normalized = _label(title)
    if not normalized:
        return "unknown"
    if "preferred" in normalized and any(token in normalized for token in ("stock", "share")):
        return "preferred_stock"
    if any(token in normalized for token in ("common stock", "ordinary share", "common share")):
        return "common_stock"
    if any(token in normalized for token in ("debt", "note", "bond", "debenture")):
        return "debt"
    if "unit" in normalized:
        return "units"
    if any(token in normalized for token in ("warrant", "right", "option")):
        return "warrants"
    return "other"


def _term_semantics(
    name: str, security_classification: str, *, rate_scale: str | None = None,
) -> tuple[str, str | None, str | None]:
    if name == "amount_to_be_registered":
        if security_classification in {"common_stock", "preferred_stock"}:
            return "share_count", "shares", None
        if security_classification == "debt":
            return "principal_amount", "USD", "USD"
        if security_classification == "units":
            return "quantity", "units", None
        if security_classification == "warrants":
            return "quantity", "securities", None
        return "quantity", None, None
    if name == "proposed_maximum_offering_price_per_unit":
        if security_classification in {"common_stock", "preferred_stock"}:
            return "price", "USD/share", "USD"
        if security_classification == "units":
            return "price", "USD/unit", "USD"
        if security_classification == "warrants":
            return "price", "USD/security", "USD"
        return "price", None, None
    if name in {"proposed_maximum_aggregate_offering_price", "registration_fee"}:
        return "amount", "USD", "USD"
    if name == "filing_fee_rate":
        if rate_scale not in {None, "1"}:
            return "rate", "USD_per_USD", "USD"
        return "rate", "rate", None
    raise ValueError(f"unsupported direct fee-table term {name!r}")


def _document_term_type(name: str) -> str:
    return {
        "amount_to_be_registered": "quantity",
        "proposed_maximum_offering_price_per_unit": "price",
        "proposed_maximum_aggregate_offering_price": "amount",
        "registration_fee": "amount",
        "filing_fee_rate": "rate",
    }[name]


def _empty_security() -> dict[str, Any]:
    return {
        "row_id": None, "table_index": None, "row_index": None,
        "title_raw": None, "title_normalized": None, "classification": "unknown",
    }


def _security_for_row(
    manifest_id: str, table: FeeTable, row: TableRow, row_index: int,
) -> tuple[dict[str, Any], TableCell | None]:
    title_cell = row.cell_at(table.security_column) if table.security_column is not None else None
    title = _clean_text(title_cell.text) if title_cell is not None else ""
    classification = _classify_security(title)
    return ({
        "row_id": _row_id(manifest_id, table, row),
        "table_index": table.table_index,
        "row_index": row_index,
        "title_raw": title or None,
        "title_normalized": _label(title) or None,
        "classification": classification,
    }, title_cell)


def _base_record(
    manifest: Mapping[str, Any],
    name: str,
    *,
    disposition: str,
    reason: str,
    reported: Mapping[str, Any],
    evidence: Mapping[str, Any],
    source_available_at: str,
    term_type: str,
    security: Mapping[str, Any] | None = None,
    child_document: SubmissionDocument | None = None,
    parser_version: str,
) -> dict[str, Any]:
    filing = manifest.get("filing") or {}
    document = manifest.get("document") or {}
    parser_deferred = reason in {"manifest_parser_not_eligible", "manifest_corruption_not_clean"}
    needs_review = disposition == "ambiguous" or parser_deferred
    security_record = dict(security or _empty_security())
    row_id = security_record.get("row_id")
    return {
        "schema": DOCUMENT_TERM_SCHEMA,
        "logical_observation_id": _logical_observation_id(str(manifest["manifest_id"]), row_id, name),
        "issuer_id": str((manifest.get("issuer") or {})["issuer_id"]),
        "filing": {
            "accession": str(filing["accession"]), "form": str(filing["form"]),
            "filing_date": filing.get("filing_date"), "accepted_at": filing.get("accepted_at"),
        },
        "document": {
            "source_manifest_id": str(manifest["manifest_id"]),
            "source_id": str(manifest["source_id"]), "document_role": "complete_submission",
            "canonical_url": str(document["canonical_url"]),
            "content_sha256": str(document["content_sha256"]).lower(),
            "child_document_type": child_document.document_type if child_document else None,
            "child_sequence": child_document.sequence if child_document else None,
            "child_filename": child_document.filename if child_document else None,
            "child_text_start": child_document.text_start if child_document else None,
            "child_text_end": child_document.text_end if child_document else None,
        },
        "security": security_record,
        "term": {"name": name, "term_type": term_type, "scope": "registration_fee_table_row"},
        "state": {"disposition": disposition, "reason": reason},
        "reported": dict(reported),
        # This first slice is a unit-preserving transcription, not a conversion.
        "normalized": dict(reported),
        "evidence": dict(evidence),
        "extraction": {
            "method": "deferred" if parser_deferred else "deterministic",
            "parser_version": parser_version,
            "review_status": "deferred" if needs_review else "unreviewed",
        },
        "relationships": {"amends": [], "supersedes": [], "contradiction_ids": []},
        "point_in_time": {"source_available_at": source_available_at},
    }


def _records_for_manifest_v1_1_0(
    manifest: Mapping[str, Any], raw: bytes | None, parser_version: str,
) -> list[dict[str, Any]]:
    """Build row/security-scoped direct observations for one complete submission."""
    source_available_at = _iso((manifest.get("retrieval") or {}).get("first_seen_at"), "retrieval.first_seen_at")
    root = _root_span(manifest)
    parser = manifest.get("parser") or {}
    if str(parser.get("corruption_state") or "") != "clean":
        reason = "manifest_corruption_not_clean"
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at,
                         parser_version=parser_version)
            for name in TERM_NAMES
        ]
    if str(parser.get("eligibility") or "") != "eligible":
        reason = "manifest_parser_not_eligible"
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at,
                         parser_version=parser_version)
            for name in TERM_NAMES
        ]
    assert raw is not None
    documents = _eligible_documents(raw, str((manifest.get("filing") or {}).get("form") or ""))
    if not documents:
        reason = "eligible_document_not_found"
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at,
                         parser_version=parser_version)
            for name in TERM_NAMES
        ]
    tables: list[FeeTable] = []
    table_cursor = 0
    for child in documents:
        tables.extend(_parse_fee_tables(child, table_cursor))
        table_cursor += len(_TABLE_RE.findall(child.text))
    if not tables:
        reason = "fee_table_not_detected"
        child = documents[0] if len(documents) == 1 else None
        return [
            _base_record(manifest, name, disposition="unavailable", reason=reason,
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, [root]), source_available_at=source_available_at,
                         child_document=child, parser_version=parser_version)
            for name in TERM_NAMES
        ]
    spans = [_table_span(str(manifest["manifest_id"]), table) for table in tables]
    if len(tables) != 1:
        return [
            _base_record(manifest, name, disposition="ambiguous", reason="multiple_fee_tables_detected",
                         reported=_empty_value(), term_type=_document_term_type(name),
                         evidence=_document_evidence(manifest, spans), source_available_at=source_available_at,
                         parser_version=parser_version)
            for name in TERM_NAMES
        ]

    table = tables[0]
    if table.duplicate_headers:
        return [
            _base_record(
                manifest, name, disposition="ambiguous", reason="duplicate_header_mapping",
                reported=_empty_value(), term_type=_document_term_type(name),
                evidence=_document_evidence(manifest, spans), source_available_at=source_available_at,
                child_document=table.document, parser_version=parser_version,
            )
            for name in TERM_NAMES
        ]
    if table.security_column is None:
        return [
            _base_record(
                manifest, name, disposition="ambiguous", reason="unit_semantics_ambiguous",
                reported=_empty_value(), term_type=_document_term_type(name),
                evidence=_document_evidence(manifest, spans), source_available_at=source_available_at,
                child_document=table.document, parser_version=parser_version,
            )
            for name in TERM_NAMES
        ]
    records: list[dict[str, Any]] = []
    data_rows = [
        (row_index, row)
        for row_index, row in enumerate(table.rows[table.header_index + 1:], start=table.header_index + 1)
        if any(
            (cell := row.cell_at(column)) is not None and bool(_clean_text(cell.text))
            for column in table.columns.values()
        )
    ]
    if not data_rows:
        return [
            _base_record(
                manifest, name, disposition="unavailable", reason="header_without_direct_value",
                reported=_empty_value(), term_type=_document_term_type(name),
                evidence=_document_evidence(manifest, spans), source_available_at=source_available_at,
                child_document=table.document, parser_version=parser_version,
            )
            for name in TERM_NAMES
        ]

    manifest_id = str(manifest["manifest_id"])
    table_span = spans[0]
    for row_index, row in data_rows:
        security, title_cell = _security_for_row(manifest_id, table, row, row_index)
        row_span = _row_span(manifest_id, table, row, row_index)
        base_spans: list[Mapping[str, Any]] = [table_span, row_span]
        if title_cell is not None:
            base_spans.append(_cell_span(manifest_id, table, row, row_index, title_cell, "security_title"))
        title_present = bool(security.get("title_raw"))
        classification = str(security["classification"])
        for name in TERM_NAMES:
            column = table.columns.get(name)
            cell = row.cell_at(column) if column is not None else None
            term_spans = list(base_spans)
            if cell is not None:
                term_spans.append(_cell_span(manifest_id, table, row, row_index, cell, name))
            parsed = _parse_number(
                cell.text if cell is not None else "",
                allow_denominated_rate=name == "filing_fee_rate",
            )
            term_type, unit, currency = _term_semantics(
                name, classification, rate_scale=parsed.scale,
            )
            disposition = parsed.disposition
            reason = parsed.reason
            if disposition == "observed" and (not title_present or unit is None):
                disposition = "ambiguous"
                reason = "unit_semantics_ambiguous"
            reported = (
                _direct_value(cell.text, str(parsed.value), str(unit), currency, str(parsed.scale))
                if disposition == "observed" and cell is not None and parsed.value is not None
                and parsed.scale is not None and unit is not None
                else _empty_value()
            )
            records.append(_base_record(
                manifest, name, disposition=disposition, reason=reason,
                reported=reported, term_type=term_type,
                evidence=_document_evidence(manifest, term_spans),
                source_available_at=source_available_at, security=security,
                child_document=table.document, parser_version=parser_version,
            ))
    return records


def _clone_json_value(value: Any) -> Any:
    """Copy only the immutable JSON value model admitted by observation contracts."""
    if isinstance(value, Mapping):
        return {key: _clone_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone_json_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clone_json_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"unsupported document-term semantic value: {type(value).__name__}")


def _semantic_body(record: Mapping[str, Any]) -> dict[str, Any]:
    """Source-derived correction body, excluding only versioning metadata.

    A parser release label alone is never a fact correction. Requiring a change
    in this body prevents a rehashed phantom v2 from manufacturing a second
    point-in-time version of the same extraction.
    """
    body = _clone_json_value(dict(record))
    body.pop("observation_id", None)
    body.pop("version", None)
    body.pop("point_in_time", None)
    relationships = dict(body.get("relationships") or {})
    relationships["supersedes"] = []
    body["relationships"] = relationships
    extraction = dict(body.get("extraction") or {})
    extraction.pop("parser_version", None)
    body["extraction"] = extraction
    return body


def observation_id_for(record: Mapping[str, Any]) -> str:
    body = _clone_json_value(dict(record))
    body.pop("observation_id", None)
    return _digest_id("document-term:cs:", body)


def _materialize_observation(
    candidate: dict[str, Any], prior: Mapping[str, Any] | None, generated_at: str,
) -> dict[str, Any]:
    """Attach immutable correction identity and the system-availability clock."""
    if _parse_time(generated_at, "generated_at") < _parse_time(
        (candidate.get("point_in_time") or {}).get("source_available_at"),
        "source_available_at",
    ):
        raise ValueError("generated_at cannot precede retained source availability")
    correction_version = (
        1 if prior is None
        else int((prior.get("version") or {}).get("correction_version") or 0) + 1
    )
    prior_id = None if prior is None else str(prior["observation_id"])
    if prior is not None:
        prior_time = _parse_time(
            (prior.get("point_in_time") or {}).get("available_at"), "prior.available_at",
        )
        if _parse_time(generated_at, "generated_at") <= prior_time:
            raise ValueError(
                "generated_at must be later than a corrected document-term observation"
            )
    candidate["relationships"] = {
        "amends": [],
        "supersedes": [] if prior_id is None else [prior_id],
        "contradiction_ids": [],
    }
    candidate["version"] = {
        "immutable_record": True,
        "correction_version": correction_version,
        "correction_of": prior_id,
    }
    candidate["point_in_time"]["available_at"] = generated_at
    candidate["observation_id"] = observation_id_for(candidate)
    return candidate


def _selected_registration_manifests(
    manifests: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Select the exact immutable complete submissions eligible for this parser."""
    selected = [
        dict(row) for row in manifests
        if str(row.get("source_system") or "") == "sec_edgar"
        and str((row.get("document") or {}).get("document_role") or "")
        == "complete_submission"
        and _normalized_form(str((row.get("filing") or {}).get("form") or ""))
        in REGISTRATION_FEE_FORMS
    ]
    selected.sort(key=lambda row: str(row.get("manifest_id") or ""))
    return selected


def _semantic_code_descriptor(code: CodeType) -> dict[str, Any]:
    """Canonical executable material, excluding filenames and source line tables."""
    constants = list(code.co_consts)
    if constants and isinstance(constants[0], str):
        # Function/class docstrings do not alter executable semantics.
        constants[0] = None
    return {
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "nlocals": code.co_nlocals,
        "stacksize": code.co_stacksize,
        "flags": code.co_flags,
        "bytecode": code.co_code.hex(),
        "exceptiontable": code.co_exceptiontable.hex(),
        "constants": [_semantic_code_constant(value) for value in constants],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
    }


def _semantic_code_constant(value: Any) -> Any:
    if isinstance(value, CodeType):
        return {"code": _semantic_code_descriptor(value)}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, (float, complex)):
        return {type(value).__name__: repr(value)}
    if value is Ellipsis:
        return {"ellipsis": True}
    if isinstance(value, tuple):
        return {"tuple": [_semantic_code_constant(item) for item in value]}
    if isinstance(value, frozenset):
        encoded = [_semantic_code_constant(item) for item in value]
        return {"frozenset": sorted(encoded, key=_semantic_sort_key)}
    raise ValueError(
        "document-term parser code contains unsupported constant "
        f"{type(value).__name__}"
    )


def _semantic_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _callable_identity(value: Any) -> str:
    module = str(getattr(value, "__module__", "") or "")
    qualname = str(
        getattr(value, "__qualname__", getattr(value, "__name__", type(value).__name__))
    )
    return f"{module}.{qualname}"


def _loaded_global_names(code: CodeType) -> tuple[str, ...]:
    names: set[str] = set()
    stack = [code]
    while stack:
        current = stack.pop()
        for instruction in dis.get_instructions(current):
            if instruction.opname in {"LOAD_GLOBAL", "LOAD_NAME"}:
                names.add(str(instruction.argval))
        stack.extend(
            constant for constant in current.co_consts if isinstance(constant, CodeType)
        )
    return tuple(sorted(names))


def _loaded_global_attribute_paths(
    code: CodeType,
) -> dict[str, tuple[tuple[str, ...], ...]]:
    """Discover static ``global.attr`` chains executed by a code object."""
    paths: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    stack = [code]
    while stack:
        current = stack.pop()
        instructions = list(dis.get_instructions(current))
        for index, instruction in enumerate(instructions):
            if instruction.opname not in {"LOAD_GLOBAL", "LOAD_NAME"}:
                continue
            path: list[str] = []
            for following in instructions[index + 1:]:
                if following.opname not in {"LOAD_ATTR", "LOAD_METHOD"}:
                    break
                path.append(str(following.argval))
                paths[str(instruction.argval)].add(tuple(path))
        stack.extend(
            constant for constant in current.co_consts if isinstance(constant, CodeType)
        )
    return {
        name: tuple(sorted(items))
        for name, items in sorted(paths.items())
    }


def _is_expandable_project_value(value: Any) -> bool:
    module = str(getattr(value, "__module__", "") or "")
    return module == __name__ or module.startswith("engine.capital_structure.")


def _is_stdlib_value(value: Any) -> bool:
    module = str(getattr(value, "__module__", "") or "").split(".", 1)[0]
    return module in sys.stdlib_module_names


class _SemanticClosureBuilder:
    """Encode portable release roots or an exact inherited-runtime digest."""

    def __init__(self, *, stable_stdlib_dispatch: bool = True) -> None:
        self.nodes: dict[str, Any] = {}
        self._expanded: set[str] = set()
        self._stable_stdlib_dispatch = stable_stdlib_dispatch

    def _put(self, key: str, descriptor: Any) -> None:
        prior = self.nodes.get(key)
        if prior is not None and prior != descriptor:
            raise ValueError(f"document-term parser semantic node collision: {key}")
        self.nodes[key] = descriptor

    def _reference(self, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, str)):
            return {"kind": "literal", "value": value}
        if isinstance(value, bytes):
            return {"kind": "bytes", "hex": value.hex()}
        if isinstance(value, CodeType):
            return {"kind": "code", "descriptor": _semantic_code_descriptor(value)}
        if isinstance(value, (float, complex, Decimal)):
            return {"kind": type(value).__name__, "value": str(value)}
        if isinstance(value, Path):
            try:
                relative = value.resolve().relative_to(_SEMANTIC_REPO_ROOT)
            except ValueError as exc:
                raise ValueError(
                    "document-term parser semantic closure path is outside repo root"
                ) from exc
            return {"kind": "repo_path", "value": relative.as_posix()}
        if isinstance(value, re.Pattern):
            pattern = value.pattern
            return {
                "kind": "regex",
                "pattern": pattern.hex() if isinstance(pattern, bytes) else pattern,
                "pattern_type": "bytes" if isinstance(pattern, bytes) else "str",
                "flags": value.flags,
            }
        if isinstance(value, tuple):
            return {"kind": "tuple", "items": [self._reference(item) for item in value]}
        if isinstance(value, frozenset):
            items = [self._reference(item) for item in value]
            return {"kind": "frozenset", "items": sorted(items, key=_semantic_sort_key)}
        if not self._stable_stdlib_dispatch and isinstance(value, list):
            return {
                "kind": "runtime_list",
                "items": [self._reference(item) for item in value],
            }
        if not self._stable_stdlib_dispatch and isinstance(value, dict):
            items = [
                [self._reference(key), self._reference(item)]
                for key, item in value.items()
            ]
            return {
                "kind": "runtime_dict",
                "items": sorted(items, key=_semantic_sort_key),
            }
        if not self._stable_stdlib_dispatch and isinstance(value, set):
            items = [self._reference(item) for item in value]
            return {
                "kind": "runtime_set",
                "items": sorted(items, key=_semantic_sort_key),
            }
        if not self._stable_stdlib_dispatch and isinstance(value, bytearray):
            return {"kind": "runtime_bytearray", "hex": bytes(value).hex()}
        if isinstance(value, ModuleType):
            return {
                "kind": "module",
                "name": value.__name__,
                "version": str(getattr(value, "__version__", "") or ""),
            }
        if inspect.isfunction(value):
            return {"kind": "function", "identity": _callable_identity(value)}
        if inspect.ismethod(value):
            return {
                "kind": "bound_method",
                "identity": _callable_identity(value.__func__),
                "receiver_class": _callable_identity(type(value.__self__)),
            }
        if isinstance(value, (staticmethod, classmethod)):
            return {
                "kind": type(value).__name__,
                "identity": _callable_identity(value.__func__),
            }
        if inspect.isbuiltin(value):
            descriptor = {"kind": "builtin", "identity": _callable_identity(value)}
            bound_self = getattr(value, "__self__", None)
            if bound_self is not None and not isinstance(bound_self, ModuleType):
                descriptor["bound_self"] = self._reference(bound_self)
            return descriptor
        if inspect.ismethoddescriptor(value):
            owner = getattr(value, "__objclass__", None)
            return {
                "kind": "method_descriptor",
                "identity": _callable_identity(value),
                "owner": _callable_identity(owner) if inspect.isclass(owner) else None,
            }
        if isinstance(value, property):
            return {
                "kind": "property",
                "get": _callable_identity(value.fget) if value.fget else None,
                "set": _callable_identity(value.fset) if value.fset else None,
                "delete": _callable_identity(value.fdel) if value.fdel else None,
            }
        if inspect.isdatadescriptor(value):
            owner = getattr(value, "__objclass__", None)
            return {
                "kind": "data_descriptor",
                "identity": _callable_identity(value),
                "owner": _callable_identity(owner) if inspect.isclass(owner) else None,
            }
        if (
            type(value).__module__ == "operator"
            and type(value).__qualname__ == "methodcaller"
        ):
            return {"kind": "operator.methodcaller", "value": repr(value)}
        if (
            type(value).__module__ == "referencing._core"
            and type(value).__qualname__ == "Registry"
        ):
            return {
                "kind": "referencing.Registry",
                "class": _callable_identity(type(value)),
                "value": repr(value),
            }
        if (
            type(value).__module__ == "jsonschema._utils"
            and type(value).__qualname__ == "Unset"
        ):
            return {
                "kind": "jsonschema.Unset",
                "class": _callable_identity(type(value)),
                "value": repr(value),
            }
        if (
            type(value).__module__ == "jsonschema._utils"
            and type(value).__qualname__ == "URIDict"
        ):
            return {
                "kind": "jsonschema.URIDict",
                "items": [
                    [str(key), self._reference(item)]
                    for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                ],
            }
        if inspect.isclass(value):
            return {"kind": "class", "identity": _callable_identity(value)}
        if isinstance(value, (list, dict, set, bytearray)):
            raise ValueError(
                "document-term parser semantic closure depends on mutable global "
                f"{type(value).__name__}"
            )
        raise ValueError(
            "document-term parser semantic closure cannot encode "
            f"{type(value).__module__}.{type(value).__qualname__}"
        )

    def bind(self, key: str, value: Any, *, expand: bool) -> None:
        self._put(f"binding:{key}", self._reference(value))
        if inspect.isfunction(value):
            self._walk_function(value, expand=expand)
        elif inspect.isclass(value):
            self._walk_class(value, expand=expand)

    def _should_expand_function_dependency(self, value: Any) -> bool:
        if _is_expandable_project_value(value):
            return True
        return (
            not self._stable_stdlib_dispatch
            and inspect.isfunction(value)
            and str(getattr(value, "__module__", "") or "") == "html"
        )

    def _walk_function(self, function: Callable[..., Any], *, expand: bool) -> None:
        identity = _callable_identity(function)
        node_key = f"function:{identity}"
        descriptor: dict[str, Any] = {
            "identity": identity,
            "default_count": len(function.__defaults__ or ()),
            "kwdefault_names": sorted((function.__kwdefaults__ or {}).keys()),
            "closure_names": list(function.__code__.co_freevars),
            "stdlib_runtime_primitive": (
                self._stable_stdlib_dispatch
                and _is_stdlib_value(function)
                and not expand
            ),
        }
        if not descriptor["stdlib_runtime_primitive"]:
            descriptor["code"] = _semantic_code_descriptor(function.__code__)
            descriptor["global_names"] = list(_loaded_global_names(function.__code__))
            descriptor["global_attribute_paths"] = {
                name: [list(path) for path in paths]
                for name, paths in _loaded_global_attribute_paths(function.__code__).items()
            }
        self._put(node_key, descriptor)
        if not expand or node_key in self._expanded:
            return
        self._expanded.add(node_key)

        builtin_namespace = function.__globals__.get("__builtins__", builtins.__dict__)
        if isinstance(builtin_namespace, ModuleType):
            builtin_namespace = vars(builtin_namespace)
        attribute_paths = _loaded_global_attribute_paths(function.__code__)
        for name in _loaded_global_names(function.__code__):
            if name in function.__globals__:
                value = function.__globals__[name]
                origin = "global"
            elif name in builtin_namespace:
                value = builtin_namespace[name]
                origin = "builtin"
            else:
                raise ValueError(
                    f"document-term parser executable has unresolved global {identity}:{name}"
                )
            self.bind(
                f"{node_key}.{origin}.{name}", value,
                expand=self._should_expand_function_dependency(value),
            )
            if isinstance(value, ModuleType):
                for path in attribute_paths.get(name, ()):
                    attribute_value: Any = value
                    for attribute in path:
                        if not hasattr(attribute_value, attribute):
                            raise ValueError(
                                "document-term parser module attribute is unresolved: "
                                f"{identity}:{name}.{'.'.join(path)}"
                            )
                        attribute_value = getattr(attribute_value, attribute)
                    self.bind(
                        f"{node_key}.{origin}.{name}.attribute.{'.'.join(path)}",
                        attribute_value,
                        expand=self._should_expand_function_dependency(
                            attribute_value,
                        ),
                    )

        for index, value in enumerate(function.__defaults__ or ()):
            self.bind(
                f"{node_key}.default.{index}", value,
                expand=(
                    expand and self._should_expand_function_dependency(value)
                ),
            )
        for name, value in sorted((function.__kwdefaults__ or {}).items()):
            self.bind(
                f"{node_key}.kwdefault.{name}", value,
                expand=(
                    expand and self._should_expand_function_dependency(value)
                ),
            )
        closure = function.__closure__ or ()
        if len(closure) != len(function.__code__.co_freevars):
            raise ValueError(f"document-term parser closure arity mismatch for {identity}")
        for name, cell in zip(function.__code__.co_freevars, closure, strict=True):
            try:
                value = cell.cell_contents
            except ValueError as exc:
                raise ValueError(
                    f"document-term parser executable has empty closure cell {identity}:{name}"
                ) from exc
            self.bind(
                f"{node_key}.closure.{name}", value,
                expand=(
                    expand and self._should_expand_function_dependency(value)
                ),
            )

    def _walk_class(self, cls: type[Any], *, expand: bool) -> None:
        identity = _callable_identity(cls)
        node_key = f"class:{identity}"
        descriptor: dict[str, Any] = {
            "identity": identity,
            "bases": [_callable_identity(base) for base in cls.__bases__],
            "dataclass": None,
        }
        generated_dataclass_methods: set[str] = set()
        if is_dataclass(cls):
            generated_dataclass_methods = {
                "__init__", "__repr__", "__eq__", "__hash__",
                "__setattr__", "__delattr__",
            }
            params = cls.__dataclass_params__
            descriptor["dataclass"] = {
                name: bool(getattr(params, name))
                for name in (
                    "init", "repr", "eq", "order", "unsafe_hash", "frozen",
                    "match_args", "kw_only", "slots", "weakref_slot",
                )
                if hasattr(params, name)
            }
            descriptor["fields"] = [
                {
                    "name": field.name,
                    "init": field.init,
                    "repr": field.repr,
                    "hash": field.hash,
                    "compare": field.compare,
                    "kw_only": field.kw_only,
                    "has_default": field.default is not MISSING,
                    "has_default_factory": field.default_factory is not MISSING,
                }
                for field in dataclass_fields(cls)
            ]
        self._put(node_key, descriptor)
        if not expand or node_key in self._expanded:
            return
        self._expanded.add(node_key)
        for name, raw_value in sorted(vars(cls).items()):
            value = raw_value
            if isinstance(raw_value, (staticmethod, classmethod)):
                value = raw_value.__func__
            if inspect.isfunction(value):
                if name in generated_dataclass_methods:
                    continue
                self.bind(f"{node_key}.attribute.{name}", value, expand=True)
            elif isinstance(value, property):
                for role, accessor in (
                    ("get", value.fget), ("set", value.fset), ("delete", value.fdel),
                ):
                    if accessor is not None:
                        self.bind(
                            f"{node_key}.property.{name}.{role}", accessor, expand=True,
                        )
            elif not name.startswith("__"):
                self.bind(
                    f"{node_key}.attribute.{name}", value,
                    expand=_is_expandable_project_value(value),
                )

    @staticmethod
    def _mro_descriptor(
        receiver: type[Any], name: str, *, owner: type[Any] | None = None,
    ) -> tuple[type[Any], Any] | None:
        candidates = (owner,) if owner is not None else receiver.__mro__
        for candidate in candidates:
            if candidate is not None and name in vars(candidate):
                return candidate, vars(candidate)[name]
        return None

    def bind_dispatch_root(self, root: SemanticDispatchRoot) -> None:
        """Bind declared dispatch ABI plus recursively reached runtime behavior.

        Release mode records stable stdlib identities under the supported Python
        major/minor ABI. Runtime mode recursively walks exact inherited methods,
        helpers, subclass callbacks, globals, descriptors, and class data. The
        latter is captured once per process and compared again on every use.
        """
        if not inspect.isclass(root.receiver) or not root.methods:
            raise ValueError(
                f"document-term parser dispatch root {root.role!r} is malformed"
            )
        self._put(
            f"dispatch_root:{root.role}",
            {
                "receiver": _callable_identity(root.receiver),
                "mro": [_callable_identity(base) for base in root.receiver.__mro__],
                "methods": list(root.methods),
                "data_attributes": list(root.data_attributes),
            },
        )
        for name in root.data_attributes:
            resolved = self._mro_descriptor(root.receiver, name)
            if resolved is None:
                raise ValueError(
                    "document-term parser dispatch data is unresolved: "
                    f"{_callable_identity(root.receiver)}.{name}"
                )
            owner, value = resolved
            descriptor = {
                "receiver": _callable_identity(root.receiver),
                "implementing_class": _callable_identity(owner),
                "name": name,
                "descriptor_kind": type(value).__name__,
                "process_local_seal": True,
            }
            if not self._stable_stdlib_dispatch:
                descriptor["value"] = self._reference(value)
            self._put(
                f"dispatch_data:{_callable_identity(root.receiver)}."
                f"{_callable_identity(owner)}.{name}",
                descriptor,
            )
        for method in root.methods:
            self._walk_dispatch_method(root.receiver, method)

    def _walk_dispatch_method(
        self,
        receiver: type[Any],
        name: str,
        *,
        owner: type[Any] | None = None,
    ) -> None:
        resolved = self._mro_descriptor(receiver, name, owner=owner)
        if resolved is None:
            raise ValueError(
                "document-term parser dynamic dispatch is unresolved: "
                f"{_callable_identity(receiver)}.{name}"
            )
        implementing_class, raw_value = resolved
        descriptor_kind = type(raw_value).__name__
        value = raw_value.__func__ if isinstance(
            raw_value, (staticmethod, classmethod),
        ) else raw_value
        key = (
            f"dispatch:{_callable_identity(receiver)}."
            f"{_callable_identity(implementing_class)}.{name}"
        )
        descriptor: dict[str, Any] = {
            "receiver": _callable_identity(receiver),
            "implementing_class": _callable_identity(implementing_class),
            "name": name,
            "descriptor_kind": descriptor_kind,
            "implementation": self._reference(value),
        }
        function: Callable[..., Any] | None = None
        if inspect.isfunction(value):
            function = value
        elif isinstance(value, property) and value.fget is not None:
            function = value.fget
            descriptor["property_access"] = "get"
        if function is not None:
            if self._stable_stdlib_dispatch and _is_stdlib_value(function):
                descriptor["stdlib_contract"] = {
                    "identity": _callable_identity(function),
                    "runtime": [sys.version_info.major, sys.version_info.minor],
                    "process_local_seal": True,
                }
                self._put(key, descriptor)
                return
            descriptor.update({
                "code": _semantic_code_descriptor(function.__code__),
                "global_names": list(_loaded_global_names(function.__code__)),
                "global_attribute_paths": {
                    global_name: [list(path) for path in paths]
                    for global_name, paths in _loaded_global_attribute_paths(
                        function.__code__,
                    ).items()
                },
                "defaults": [
                    self._reference(item) for item in (function.__defaults__ or ())
                ],
                "kwdefaults": {
                    default_name: self._reference(item)
                    for default_name, item in sorted(
                        (function.__kwdefaults__ or {}).items(),
                    )
                },
            })
        self._put(key, descriptor)
        if key in self._expanded or function is None:
            return
        self._expanded.add(key)

        # co_names is a conservative upper bound on attributes reached through
        # ``self``. Resolve only callable descriptors on the concrete receiver;
        # instance data and unrelated globals are deliberately excluded.
        for dynamic_name in sorted(set(function.__code__.co_names)):
            dynamic = self._mro_descriptor(receiver, dynamic_name)
            if dynamic is None:
                continue
            dynamic_owner, dynamic_raw_value = dynamic
            dynamic_value = (
                dynamic_raw_value.__func__
                if isinstance(dynamic_raw_value, (staticmethod, classmethod))
                else dynamic_raw_value
            )
            self._put(
                f"{key}.receiver_attribute.{dynamic_name}",
                {
                    "implementing_class": _callable_identity(dynamic_owner),
                    "descriptor_kind": type(dynamic_raw_value).__name__,
                    "value": self._reference(dynamic_value),
                },
            )
            if not (
                callable(dynamic_value) or isinstance(dynamic_value, property)
            ):
                continue
            self._walk_dispatch_method(receiver, dynamic_name)

        # Resolve zero-argument ``super()`` calls against the concrete receiver
        # MRO. A same-named method may already have been visited through
        # ordinary ``self`` dispatch, but the next implementation is distinct
        # executable authority (for example HTMLParser.reset ->
        # ParserBase.reset) and must be pinned separately.
        if "super" in _loaded_global_names(function.__code__):
            receiver_mro = receiver.__mro__
            try:
                next_owner_index = receiver_mro.index(implementing_class) + 1
            except ValueError as exc:
                raise ValueError(
                    "document-term parser dispatch owner is outside receiver MRO: "
                    f"{_callable_identity(implementing_class)}"
                ) from exc
            for super_name in sorted(set(function.__code__.co_names)):
                for base in receiver_mro[next_owner_index:]:
                    if super_name not in vars(base):
                        continue
                    super_raw_value = vars(base)[super_name]
                    super_value = (
                        super_raw_value.__func__
                        if isinstance(super_raw_value, (staticmethod, classmethod))
                        else super_raw_value
                    )
                    self._put(
                        f"{key}.super_attribute.{_callable_identity(base)}.{super_name}",
                        {
                            "implementing_class": _callable_identity(base),
                            "descriptor_kind": type(super_raw_value).__name__,
                            "value": self._reference(super_value),
                        },
                    )
                    if callable(super_value) or isinstance(
                        super_value, property,
                    ):
                        self._walk_dispatch_method(
                            receiver, super_name, owner=base,
                        )
                    break

        builtin_namespace = function.__globals__.get("__builtins__", builtins.__dict__)
        if isinstance(builtin_namespace, ModuleType):
            builtin_namespace = vars(builtin_namespace)
        attribute_paths = _loaded_global_attribute_paths(function.__code__)
        for global_name in _loaded_global_names(function.__code__):
            if global_name in function.__globals__:
                global_value = function.__globals__[global_name]
                origin = "global"
            elif global_name in builtin_namespace:
                global_value = builtin_namespace[global_name]
                origin = "builtin"
            else:
                raise ValueError(
                    "document-term parser dispatch has unresolved global: "
                    f"{_callable_identity(function)}:{global_name}"
                )
            global_key = f"{key}.{origin}.{global_name}"
            self._put(global_key, self._reference(global_value))
            if not self._stable_stdlib_dispatch and inspect.isfunction(global_value):
                self.bind(
                    f"{global_key}.runtime_callable",
                    global_value,
                    expand=self._should_expand_function_dependency(global_value),
                )
            if not isinstance(global_value, (ModuleType, type)):
                continue
            for path in attribute_paths.get(global_name, ()):
                attribute_value: Any = global_value
                for attribute in path:
                    if not hasattr(attribute_value, attribute):
                        raise ValueError(
                            "document-term parser dispatch attribute is unresolved: "
                            f"{_callable_identity(function)}:{global_name}."
                            f"{'.'.join(path)}"
                        )
                    attribute_value = getattr(attribute_value, attribute)
                attribute_key = f"{global_key}.attribute.{'.'.join(path)}"
                self._put(attribute_key, self._reference(attribute_value))
                if (
                    not self._stable_stdlib_dispatch
                    and inspect.isfunction(attribute_value)
                ):
                    self.bind(
                        f"{attribute_key}.runtime_callable",
                        attribute_value,
                        expand=self._should_expand_function_dependency(
                            attribute_value,
                        ),
                    )
                if (
                    inspect.isclass(global_value)
                    and global_value in receiver.__mro__
                    and len(path) == 1
                    and self._mro_descriptor(receiver, path[0], owner=global_value)
                    is not None
                ):
                    # Explicit base-method calls (for example
                    # HTMLParser.__init__) still dispatch their internal
                    # ``self`` callbacks against the concrete subclass.
                    self._walk_dispatch_method(
                        receiver, path[0], owner=global_value,
                    )


def _entrypoint_is_still_bound(entrypoint: SemanticEntrypoint) -> bool:
    implementation = entrypoint.implementation
    module = sys.modules.get(str(getattr(implementation, "__module__", "") or ""))
    name = str(getattr(implementation, "__name__", "") or "")
    return module is not None and name and getattr(module, name, None) is implementation


def _semantic_closure(
    entrypoints: Sequence[SemanticEntrypoint],
    dispatch_roots: Sequence[SemanticDispatchRoot] = (),
) -> tuple[tuple[str, ...], str, str]:
    """Return the graph, graph digest, and implementation digest for parser roots."""
    roles = [entrypoint.role for entrypoint in entrypoints]
    dispatch_roles = [root.role for root in dispatch_roots]
    if (
        len(roles) != len(set(roles))
        or len(dispatch_roles) != len(set(dispatch_roles))
        or set(roles) & set(dispatch_roles)
        or not roles
    ):
        raise ValueError("document-term parser semantic entrypoint roles must be unique")
    builder = _SemanticClosureBuilder()
    # Keep the project golden portable across reviewed 3.12 builds. Exact
    # micro-version, cache tag, stdlib source bytes, and live dispatch belong to
    # the separately validated runtime allowlist, not this project-code digest.
    builder._put("runtime:python", {
        "implementation": sys.implementation.name,
        "version": [sys.version_info.major, sys.version_info.minor],
    })
    for entrypoint in sorted(entrypoints, key=lambda item: item.role):
        if not inspect.isfunction(entrypoint.implementation):
            raise ValueError(
                f"document-term parser entrypoint {entrypoint.role!r} must be a function"
            )
        if not _entrypoint_is_still_bound(entrypoint):
            raise ValueError(
                f"document-term parser entrypoint binding changed: {entrypoint.role}"
            )
        builder.bind(
            f"root.{entrypoint.role}", entrypoint.implementation, expand=True,
        )
    for root in sorted(dispatch_roots, key=lambda item: item.role):
        builder.bind_dispatch_root(root)
    manifest = tuple(sorted(builder.nodes))
    payload = [
        {"node": node, "descriptor": builder.nodes[node]}
        for node in manifest
    ]
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    manifest_bytes = json.dumps(
        manifest, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return (
        manifest,
        hashlib.sha256(manifest_bytes).hexdigest(),
        hashlib.sha256(encoded).hexdigest(),
    )


def _runtime_dispatch_closure(
    dispatch_roots: Sequence[SemanticDispatchRoot],
) -> tuple[tuple[str, ...], str, str]:
    """Capture exact inherited runtime objects for reviewed runtime allowlists."""
    builder = _SemanticClosureBuilder(stable_stdlib_dispatch=False)
    builder._put("runtime:python_process", {
        "implementation": sys.implementation.name,
        "cache_tag": sys.implementation.cache_tag,
        "version": [
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        ],
    })
    for root in sorted(dispatch_roots, key=lambda item: item.role):
        builder.bind_dispatch_root(root)
    manifest = tuple(sorted(builder.nodes))
    payload = [
        {"node": node, "descriptor": builder.nodes[node]}
        for node in manifest
    ]
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    manifest_bytes = json.dumps(
        manifest, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return (
        manifest,
        hashlib.sha256(manifest_bytes).hexdigest(),
        hashlib.sha256(encoded).hexdigest(),
    )


def _make_parser_runtime_fingerprint(
    source_specs: tuple[tuple[str, str, ModuleType], ...],
    *,
    system: ModuleType,
    stdlib_path: Callable[[str], str],
    path_type: type[Path],
    path_resolve: Callable[..., Path],
    path_read_bytes: Callable[[Path], bytes],
    sha256: Callable[..., Any],
) -> Callable[[], ParserRuntimeFingerprint]:
    """Seal the reviewed source inventory and low-level identity primitives."""
    source_specs = tuple(source_specs)

    def _parser_runtime_fingerprint() -> ParserRuntimeFingerprint:
        if globals().get("_PARSER_RUNTIME_STDLIB_SOURCES") is not source_specs:
            raise ValueError("document-term parser runtime source inventory changed")
        if str(getattr(system.implementation, "name", "") or "") != "cpython":
            raise ValueError("document-term parser runtime requires CPython")
        try:
            stdlib_root = path_resolve(
                path_type(stdlib_path("stdlib")), strict=True,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError(
                "document-term parser runtime identity path is unavailable"
            ) from exc

        source_digests: list[tuple[str, str]] = []
        for module_name, relative_path, module in source_specs:
            if str(getattr(module, "__name__", "") or "") != module_name:
                raise ValueError(
                    "document-term parser runtime source module identity changed: "
                    f"{module_name}"
                )
            try:
                source_path = path_resolve(
                    stdlib_root.joinpath(*relative_path.split("/")), strict=True,
                )
                source_path.relative_to(stdlib_root)
                module_file = path_resolve(
                    path_type(str(getattr(module, "__file__", "") or "")),
                    strict=True,
                )
                spec = getattr(module, "__spec__", None)
                spec_origin = path_resolve(
                    path_type(str(getattr(spec, "origin", "") or "")),
                    strict=True,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ValueError(
                    "document-term parser runtime source path is unavailable: "
                    f"{relative_path}"
                ) from exc
            if (
                not source_path.is_file()
                or module_file != source_path
                or spec_origin != source_path
            ):
                raise ValueError(
                    "document-term parser runtime source origin mismatch: "
                    f"{relative_path}"
                )
            source_digests.append((
                relative_path,
                sha256(path_read_bytes(source_path)).hexdigest(),
            ))

        version_info = system.version_info
        return ParserRuntimeFingerprint(
            implementation=str(system.implementation.name),
            version_info=(
                int(version_info.major),
                int(version_info.minor),
                int(version_info.micro),
                str(version_info.releaselevel),
                int(version_info.serial),
            ),
            cache_tag=str(system.implementation.cache_tag or ""),
            stdlib_source_sha256=tuple(source_digests),
        )

    return _parser_runtime_fingerprint


_parser_runtime_fingerprint = _make_parser_runtime_fingerprint(
    _PARSER_RUNTIME_STDLIB_SOURCES,
    system=sys,
    stdlib_path=sysconfig.get_path,
    path_type=Path,
    path_resolve=Path.resolve,
    path_read_bytes=Path.read_bytes,
    sha256=hashlib.sha256,
)


def _parser_semantic_entrypoints(
    extractor: Callable[..., Any],
) -> tuple[SemanticEntrypoint, ...]:
    return (
        SemanticEntrypoint("extractor", extractor),
        SemanticEntrypoint("correction_identity", _semantic_body),
        SemanticEntrypoint("observation_identity", observation_id_for),
        SemanticEntrypoint("correction_materialization", _materialize_observation),
        SemanticEntrypoint("source_selection", _selected_registration_manifests),
    )


def _parser_semantic_dispatch_roots() -> tuple[SemanticDispatchRoot, ...]:
    return (
        SemanticDispatchRoot(
            role="cell_html_runtime",
            receiver=_CellText,
            methods=(
                "__new__",
                "__getattribute__",
                "__setattr__",
                "__init__",
                "feed",
                "close",
                "goahead",
                "reset",
                "updatepos",
                "handle_starttag",
                "handle_endtag",
                "handle_data",
                "text",
            ),
            data_attributes=("CDATA_CONTENT_ELEMENTS",),
        ),
    )


# Released golden closure for the only actual parser version. Production
# authority consults separately immutable registry, portable-digest, and exact
# process-runtime ledgers. Runtime insertion into a mutable test dictionary can
# therefore never mint parser authority.
_PARSER_V1_1_0_DEPENDENCY_COUNT = 263
_PARSER_V1_1_0_DEPENDENCY_MANIFEST_SHA256 = (
    "4939a46ef7ca1a9583f869de398692e6a8736fc4566c6a5f3860b95c5f6e6f0d"
)
_PARSER_V1_1_0_DISPATCH_ROOTS = _parser_semantic_dispatch_roots()

# Reviewed in clean ``-B`` subprocesses.  These literal entries are the runtime
# trust root: the current process may be compared with them, but it can never
# mint or promote an observed fingerprint/digest into release authority. The
# key is portable across hosts only when the CPython ABI and every governing
# stdlib source byte match; the separately pinned live dispatch digest then
# detects in-memory mutation.
# This detects ordinary source/runtime mutation; it is not a sandbox against a
# hostile bootstrap that already controls ``sys.modules``, file reads, or the
# hash primitive before this module starts. Such a threat requires a clean
# isolated worker and an externally verified/codesigned interpreter image.
_PARSER_V1_1_0_RUNTIME_ALLOWLIST = MappingProxyType({
    # python.org CPython 3.12.2
    ParserRuntimeFingerprint(
        implementation="cpython",
        version_info=(3, 12, 2, "final", 0),
        cache_tag="cpython-312",
        stdlib_source_sha256=(
            (
                "_markupbase.py",
                "cb14dd6f2e2439eb70b806cd49d19911363d424c2b6b9f4b73c9c08022d47030",
            ),
            (
                "html/__init__.py",
                "923d82d821e75e8d235392c10c145ab8587927b3faf9c952bbd48081eebd8522",
            ),
            (
                "html/entities.py",
                "d9c65fb2828dbc1f3e399058a341d51e9375ec5bca95a8e92599c41bd5b78bde",
            ),
            (
                "html/parser.py",
                "ab5a0a2fce2bec75d969dbe057b490ef574f9ac57cce9e0eaaf7a220b301e838",
            ),
            (
                "re/__init__.py",
                "8ff3c37c63b917fcf8dc8d50993a502292a3dc159e41de4f4018c72a53d1c07b",
            ),
        ),
    ): ParserRuntimeBundle(
        dependency_count=136,
        dependency_manifest_sha256=(
            "01a61026127c28d7877b1ae3f0011bcd5e9a55b216c434f134a354cc7328dbe7"
        ),
        implementation_sha256=(
            "8e252ee2e0fada926577b9140d6b54c0eb9672c0ab77e0421946fa1939ad6e6a"
        ),
    ),
    # Anaconda CPython 3.12.4
    ParserRuntimeFingerprint(
        implementation="cpython",
        version_info=(3, 12, 4, "final", 0),
        cache_tag="cpython-312",
        stdlib_source_sha256=(
            (
                "_markupbase.py",
                "cb14dd6f2e2439eb70b806cd49d19911363d424c2b6b9f4b73c9c08022d47030",
            ),
            (
                "html/__init__.py",
                "923d82d821e75e8d235392c10c145ab8587927b3faf9c952bbd48081eebd8522",
            ),
            (
                "html/entities.py",
                "d9c65fb2828dbc1f3e399058a341d51e9375ec5bca95a8e92599c41bd5b78bde",
            ),
            (
                "html/parser.py",
                "ab5a0a2fce2bec75d969dbe057b490ef574f9ac57cce9e0eaaf7a220b301e838",
            ),
            (
                "re/__init__.py",
                "8ff3c37c63b917fcf8dc8d50993a502292a3dc159e41de4f4018c72a53d1c07b",
            ),
        ),
    ): ParserRuntimeBundle(
        dependency_count=136,
        dependency_manifest_sha256=(
            "01a61026127c28d7877b1ae3f0011bcd5e9a55b216c434f134a354cc7328dbe7"
        ),
        implementation_sha256=(
            "963bc4b485f6c5431fec61a596ecae4f7d15601e9ec07eece71feec4ced53f26"
        ),
    ),
    # Production VPS /usr/bin/python3.12, measured 2026-08-02; Ubuntu 3.12.3
    # executable with distro security-backported 3.12.13 stdlib sources.
    ParserRuntimeFingerprint(
        implementation="cpython",
        version_info=(3, 12, 3, "final", 0),
        cache_tag="cpython-312",
        stdlib_source_sha256=(
            (
                "_markupbase.py",
                "cb14dd6f2e2439eb70b806cd49d19911363d424c2b6b9f4b73c9c08022d47030",
            ),
            (
                "html/__init__.py",
                "923d82d821e75e8d235392c10c145ab8587927b3faf9c952bbd48081eebd8522",
            ),
            (
                "html/entities.py",
                "d9c65fb2828dbc1f3e399058a341d51e9375ec5bca95a8e92599c41bd5b78bde",
            ),
            (
                "html/parser.py",
                "952f1d7dd5be98b6f78801c6904a38e3e2beceb4783efb76c5e22948f0a58092",
            ),
            (
                "re/__init__.py",
                "8ff3c37c63b917fcf8dc8d50993a502292a3dc159e41de4f4018c72a53d1c07b",
            ),
        ),
    ): ParserRuntimeBundle(
        dependency_count=132,
        dependency_manifest_sha256=(
            "9fe456c8bc69adf8d3379a44c2721f22ea816a1043edcd4b6916eb67470e35d5"
        ),
        implementation_sha256=(
            "8d01e79c7a378750afc6e74940f4747809f47da80ab8fbc84937ac3940c0b134"
        ),
    ),
    # Homebrew and GitHub Actions setup-python CPython 3.12.13. The Linux
    # reference was actions/python-versions 3.12.13-27650778726, archive SHA-256
    # ce7d511228f095b5ea1ad5568543388870f5964688303f9ddc24ba06c336bfba.
    ParserRuntimeFingerprint(
        implementation="cpython",
        version_info=(3, 12, 13, "final", 0),
        cache_tag="cpython-312",
        stdlib_source_sha256=(
            (
                "_markupbase.py",
                "cb14dd6f2e2439eb70b806cd49d19911363d424c2b6b9f4b73c9c08022d47030",
            ),
            (
                "html/__init__.py",
                "923d82d821e75e8d235392c10c145ab8587927b3faf9c952bbd48081eebd8522",
            ),
            (
                "html/entities.py",
                "d9c65fb2828dbc1f3e399058a341d51e9375ec5bca95a8e92599c41bd5b78bde",
            ),
            (
                "html/parser.py",
                "952f1d7dd5be98b6f78801c6904a38e3e2beceb4783efb76c5e22948f0a58092",
            ),
            (
                "re/__init__.py",
                "8ff3c37c63b917fcf8dc8d50993a502292a3dc159e41de4f4018c72a53d1c07b",
            ),
        ),
    ): ParserRuntimeBundle(
        dependency_count=132,
        dependency_manifest_sha256=(
            "9fe456c8bc69adf8d3379a44c2721f22ea816a1043edcd4b6916eb67470e35d5"
        ),
        implementation_sha256=(
            "c402418626c015f58aef7131f9421f9aca394016753adb2ae27d98c6e237c99b"
        ),
    ),
})


def _make_validate_released_parser_runtime(
    allowlist: Mapping[ParserRuntimeFingerprint, ParserRuntimeBundle],
    fingerprint_builder: Callable[[], ParserRuntimeFingerprint],
    runtime_dispatch_closure: Callable[
        [Sequence[SemanticDispatchRoot]], tuple[tuple[str, ...], str, str]
    ],
) -> Callable[[Sequence[SemanticDispatchRoot]], ParserRuntimeBundle]:
    """Seal immutable reviewed runtime records outside caller-controlled state."""
    allowed_fingerprints = tuple(allowlist)
    fingerprint_builder_code = fingerprint_builder.__code__
    runtime_dispatch_closure_code = runtime_dispatch_closure.__code__

    def _validate_released_parser_runtime(
        dispatch_roots: Sequence[SemanticDispatchRoot],
    ) -> ParserRuntimeBundle:
        if globals().get("_PARSER_V1_1_0_RUNTIME_ALLOWLIST") is not allowlist:
            raise ValueError("document-term parser runtime allowlist binding changed")
        if tuple(allowlist) != allowed_fingerprints:
            raise ValueError("document-term parser runtime allowlist keyset changed")
        if (
            globals().get("_parser_runtime_fingerprint") is not fingerprint_builder
            or fingerprint_builder.__code__ is not fingerprint_builder_code
        ):
            raise ValueError("document-term parser runtime fingerprint binding changed")
        if (
            globals().get("_runtime_dispatch_closure")
            is not runtime_dispatch_closure
            or runtime_dispatch_closure.__code__ is not runtime_dispatch_closure_code
        ):
            raise ValueError("document-term parser runtime closure binding changed")
        fingerprint = fingerprint_builder()
        expected = allowlist.get(fingerprint)
        if expected is None:
            raise ValueError(
                "document-term parser runtime fingerprint is not released"
            )
        runtime_manifest, runtime_manifest_sha256, runtime_digest = (
            runtime_dispatch_closure(dispatch_roots)
        )
        observed = ParserRuntimeBundle(
            dependency_count=len(runtime_manifest),
            dependency_manifest_sha256=runtime_manifest_sha256,
            implementation_sha256=runtime_digest,
        )
        if observed != expected:
            raise ValueError(
                "document-term parser runtime dispatch mismatch: "
                f"observed={observed!r}"
            )
        return expected

    return _validate_released_parser_runtime


_validate_released_parser_runtime = _make_validate_released_parser_runtime(
    _PARSER_V1_1_0_RUNTIME_ALLOWLIST,
    _parser_runtime_fingerprint,
    _runtime_dispatch_closure,
)
_RELEASED_PARSER_IMPLEMENTATION_DIGESTS = MappingProxyType({
    "capital-structure-document-terms/1.1.0": (
        "d47515272069bfc3f3f768b84b94a218f7f66e7c746e36a8702efd97c26af645"
    ),
})
_RELEASED_PARSER_VERSIONS = ("capital-structure-document-terms/1.1.0",)

_RELEASED_PARSER_REGISTRY = MappingProxyType({
    "capital-structure-document-terms/1.1.0": ParserRegistration(
        version="capital-structure-document-terms/1.1.0",
        implementation_sha256=_RELEASED_PARSER_IMPLEMENTATION_DIGESTS[
            "capital-structure-document-terms/1.1.0"
        ],
        extractor=_records_for_manifest_v1_1_0,
        semantic_bundle=ParserSemanticBundle(
            entrypoints=_parser_semantic_entrypoints(_records_for_manifest_v1_1_0),
            dispatch_roots=_PARSER_V1_1_0_DISPATCH_ROOTS,
            dependency_count=_PARSER_V1_1_0_DEPENDENCY_COUNT,
            dependency_manifest_sha256=_PARSER_V1_1_0_DEPENDENCY_MANIFEST_SHA256,
        ),
    ),
})

# Read-only compatibility surface for diagnostics. Public authority does not
# consult this alias, and MappingProxyType rejects item insertion.
_PARSER_REGISTRY = _RELEASED_PARSER_REGISTRY


def _validate_parser_registration_core(
    registration: ParserRegistration,
    *,
    semantic_closure: Callable[..., tuple[tuple[str, ...], str, str]],
) -> None:
    """Recompute and compare one registration's portable semantic bundle."""
    try:
        manifest, manifest_sha256, digest = semantic_closure(
            registration.semantic_bundle.entrypoints,
            registration.semantic_bundle.dispatch_roots,
        )
    except ValueError as exc:
        raise ValueError(
            f"document-term parser semantic closure mismatch for {registration.version}"
        ) from exc
    if (
        len(manifest) != registration.semantic_bundle.dependency_count
        or not hmac.compare_digest(
            manifest_sha256, registration.semantic_bundle.dependency_manifest_sha256,
        )
        or not hmac.compare_digest(digest, registration.implementation_sha256)
    ):
        raise ValueError(
            f"document-term parser semantic closure mismatch for {registration.version}"
        )
    extractor_roots = [
        entrypoint.implementation
        for entrypoint in registration.semantic_bundle.entrypoints
        if entrypoint.role == "extractor"
    ]
    if extractor_roots != [registration.extractor]:
        raise ValueError(
            f"document-term parser extractor root mismatch for {registration.version}"
        )


def _make_validate_parser_registration_static(
    registration_core: Callable[..., None],
    semantic_closure: Callable[..., tuple[tuple[str, ...], str, str]],
) -> Callable[[ParserRegistration], None]:
    registration_core_code = registration_core.__code__
    semantic_closure_code = semantic_closure.__code__

    def _validate_parser_registration_static(
        registration: ParserRegistration,
    ) -> None:
        if (
            globals().get("_validate_parser_registration_core")
            is not registration_core
            or registration_core.__code__ is not registration_core_code
        ):
            raise ValueError("document-term parser registration core binding changed")
        if (
            globals().get("_semantic_closure") is not semantic_closure
            or semantic_closure.__code__ is not semantic_closure_code
        ):
            raise ValueError("document-term parser semantic closure binding changed")
        registration_core(registration, semantic_closure=semantic_closure)

    return _validate_parser_registration_static


_validate_parser_registration_static = _make_validate_parser_registration_static(
    _validate_parser_registration_core,
    _semantic_closure,
)


def _make_validate_parser_registration(
    static_validator: Callable[[ParserRegistration], None],
    runtime_validator: Callable[
        [Sequence[SemanticDispatchRoot]], ParserRuntimeBundle
    ],
) -> Callable[[ParserRegistration], None]:
    static_validator_code = static_validator.__code__
    runtime_validator_code = runtime_validator.__code__

    def _validate_parser_registration(registration: ParserRegistration) -> None:
        if (
            globals().get("_validate_parser_registration_static")
            is not static_validator
            or static_validator.__code__ is not static_validator_code
        ):
            raise ValueError("document-term parser static validator binding changed")
        if (
            globals().get("_validate_released_parser_runtime")
            is not runtime_validator
            or runtime_validator.__code__ is not runtime_validator_code
        ):
            raise ValueError("document-term parser runtime validator binding changed")
        static_validator(registration)
        runtime_validator(
            registration.semantic_bundle.dispatch_roots,
        )

    return _validate_parser_registration


_validate_parser_registration = _make_validate_parser_registration(
    _validate_parser_registration_static,
    _validate_released_parser_runtime,
)


def _make_registered_parser(
    released_registry: Mapping[str, ParserRegistration],
    released_digests: Mapping[str, str],
    released_versions: tuple[str, ...],
    registration_validator: Callable[[ParserRegistration], None],
) -> Callable[[Any], ParserRegistration]:
    """Seal release maps in lexical cells, outside caller-controlled arguments."""
    def _registered_parser(version: Any) -> ParserRegistration:
        """Resolve only the separately pinned immutable production release maps."""
        if globals().get("_validate_parser_registration") is not registration_validator:
            raise ValueError("document-term parser validator binding changed")
        raw = str(version or "")
        if (
            tuple(released_registry) != released_versions
            or tuple(released_digests) != released_versions
        ):
            raise ValueError("document-term released parser registry keyset mismatch")
        expected_digest = released_digests.get(raw)
        registration = released_registry.get(raw)
        if (
            registration is None
            or expected_digest is None
        ):
            raise ValueError(f"document-term parser_version is not registered: {raw!r}")
        if (
            registration.version != raw
            or not hmac.compare_digest(
                registration.implementation_sha256, expected_digest,
            )
        ):
            raise ValueError(
                f"document-term released parser registry mismatch for {raw}"
            )
        registration_validator(registration)
        return registration

    return _registered_parser


_registered_parser = _make_registered_parser(
    _RELEASED_PARSER_REGISTRY,
    _RELEASED_PARSER_IMPLEMENTATION_DIGESTS,
    _RELEASED_PARSER_VERSIONS,
    _validate_parser_registration,
)


def _make_test_parser_lane(
    registrations: Sequence[ParserRegistration], *, capability: object,
) -> _TestParserLane:
    """Create an isolated historical-parser lane unavailable to public APIs."""
    if capability is not _PRIVATE_TEST_PARSER_CAPABILITY:
        raise ValueError("document-term test parser capability is invalid")
    by_version: dict[str, ParserRegistration] = {}
    for registration in registrations:
        if registration.version in _RELEASED_PARSER_VERSIONS:
            raise ValueError("test parser lane cannot shadow a released parser")
        if registration.version in by_version:
            raise ValueError("test parser lane contains a duplicate parser version")
        _validate_parser_registration(registration)
        by_version[registration.version] = registration
    return _TestParserLane(
        capability=capability, registrations=MappingProxyType(by_version),
    )


def _registered_test_parser(
    version: Any, *, lane: _TestParserLane, capability: object,
) -> ParserRegistration:
    if (
        capability is not _PRIVATE_TEST_PARSER_CAPABILITY
        or lane.capability is not capability
    ):
        raise ValueError("document-term test parser capability is invalid")
    raw = str(version or "")
    registration = lane.registrations.get(raw)
    if registration is None:
        return _registered_parser(raw)
    _validate_parser_registration(registration)
    return registration


def _records_for_manifest_with_resolver(
    manifest: Mapping[str, Any],
    raw: bytes | None,
    *,
    parser_version: str,
    parser_resolver: Callable[[Any], ParserRegistration],
) -> list[dict[str, Any]]:
    registration = parser_resolver(parser_version)
    return registration.extractor(manifest, raw, registration.version)


def _make_records_for_manifest(
    released_parser_resolver: Callable[[Any], ParserRegistration],
) -> Callable[..., list[dict[str, Any]]]:
    def _records_for_manifest(
        manifest: Mapping[str, Any],
        raw: bytes | None,
        *,
        parser_version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Re-derive one source with a released, version-pinned parser only."""
        if globals().get("_registered_parser") is not released_parser_resolver:
            raise ValueError("document-term released parser resolver binding changed")
        return _records_for_manifest_with_resolver(
            manifest,
            raw,
            parser_version=(
                PARSER_VERSION if parser_version is None else parser_version
            ),
            parser_resolver=released_parser_resolver,
        )

    return _records_for_manifest


_records_for_manifest = _make_records_for_manifest(_registered_parser)


def _self_check_parser_registry() -> None:
    """Check release-ledger shape without granting runtime parser authority.

    Import must remain available for projection-only API routes on an unknown
    interpreter. Exact runtime and semantic admission therefore stays in
    ``_registered_parser``, immediately before any released extractor can run.
    """
    if (
        tuple(_RELEASED_PARSER_REGISTRY) != _RELEASED_PARSER_VERSIONS
        or tuple(_RELEASED_PARSER_IMPLEMENTATION_DIGESTS)
        != _RELEASED_PARSER_VERSIONS
        or len(_PARSER_V1_1_0_RUNTIME_ALLOWLIST) != 4
    ):
        raise RuntimeError("document-term production parser registry is not release-exact")
    for version in _RELEASED_PARSER_VERSIONS:
        registration = _RELEASED_PARSER_REGISTRY[version]
        if (
            registration.version != version
            or registration.implementation_sha256
            != _RELEASED_PARSER_IMPLEMENTATION_DIGESTS[version]
        ):
            raise RuntimeError(
                f"document-term parser registry startup self-check failed for {version}"
            )


def _validate_observation_source_binding_core(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
    raw: bytes | None,
    *,
    parser_resolver: Callable[[Any], ParserRegistration],
    policy: _AuthorityPolicy,
) -> None:
    """Bind every mirrored field and byte span back to one immutable manifest."""
    policy.manifest_content_validator(manifest)
    policy.retained_bytes_validator(manifest, raw)
    manifest_id = str(manifest.get("manifest_id") or "")
    filing = record.get("filing") or {}
    manifest_filing = manifest.get("filing") or {}
    document = record.get("document") or {}
    manifest_document = manifest.get("document") or {}
    evidence = record.get("evidence") or {}
    expected_pairs = (
        (record.get("issuer_id"), (manifest.get("issuer") or {}).get("issuer_id"), "issuer_id"),
        (filing.get("accession"), manifest_filing.get("accession"), "filing.accession"),
        (filing.get("form"), manifest_filing.get("form"), "filing.form"),
        (filing.get("filing_date"), manifest_filing.get("filing_date"), "filing.filing_date"),
        (filing.get("accepted_at"), manifest_filing.get("accepted_at"), "filing.accepted_at"),
        (document.get("source_manifest_id"), manifest_id, "document.source_manifest_id"),
        (document.get("source_id"), manifest.get("source_id"), "document.source_id"),
        (document.get("canonical_url"), manifest_document.get("canonical_url"), "document.canonical_url"),
        (str(document.get("content_sha256") or "").lower(), str(manifest_document.get("content_sha256") or "").lower(), "document.content_sha256"),
        (evidence.get("source_manifest_id"), manifest_id, "evidence.source_manifest_id"),
        (str(evidence.get("source_document_sha256") or "").lower(), str(manifest_document.get("content_sha256") or "").lower(), "evidence.source_document_sha256"),
    )
    for actual, expected, label in expected_pairs:
        if actual != expected:
            raise ValueError(f"document term {label} is detached from source manifest")

    point_in_time = record.get("point_in_time") or {}
    manifest_source_time = _iso(
        (manifest.get("retrieval") or {}).get("first_seen_at"), "manifest.retrieval.first_seen_at",
    )
    if point_in_time.get("source_available_at") != manifest_source_time:
        raise ValueError("document term source_available_at is detached from source manifest")
    source_time = _parse_time(point_in_time.get("source_available_at"), "source_available_at")
    available_time = _parse_time(point_in_time.get("available_at"), "available_at")
    if available_time < source_time:
        raise ValueError("document term available_at precedes source_available_at")

    expected_digest = str(manifest_document.get("content_sha256") or "").lower()
    if raw is not None and hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError("document term source bytes fail manifest digest")

    child_fields = (
        document.get("child_document_type"), document.get("child_sequence"),
        document.get("child_filename"), document.get("child_text_start"),
        document.get("child_text_end"),
    )
    if any(value is not None for value in child_fields):
        if raw is None or document.get("child_text_start") is None or document.get("child_text_end") is None:
            raise ValueError("document term child provenance requires retained source bytes")
        matching_children = [
            child for child in _eligible_documents(raw, str(manifest_filing.get("form") or ""))
            if (
                child.document_type == document.get("child_document_type")
                and child.sequence == document.get("child_sequence")
                and child.filename == document.get("child_filename")
                and child.text_start == document.get("child_text_start")
                and child.text_end == document.get("child_text_end")
            )
        ]
        if len(matching_children) != 1:
            raise ValueError("document term child provenance does not resolve exactly")

    spans = evidence.get("spans") or []
    saw_exact_cell = False
    term_name = str((record.get("term") or {}).get("name") or "")
    source_slices: dict[str, bytes] = {}
    table_bounds: dict[int, tuple[int, int]] = {}
    row_bounds: dict[tuple[int, int], tuple[int, int]] = {}
    for span in spans:
        if str((span or {}).get("manifest_id") or "") != manifest_id:
            raise ValueError("document term span crosses source manifests")
        locator = str((span or {}).get("locator") or "")
        match = _BYTE_LOCATOR_RE.search(locator)
        if match is None:
            raise ValueError("document term span lacks an exact byte locator")
        start, end = int(match.group(1)), int(match.group(2))
        if start < 0 or end < start or end > int(manifest_document.get("byte_length") or 0):
            raise ValueError("document term span byte locator is out of bounds")
        locator_type = str((span or {}).get("locator_type") or "")
        if locator_type == "document":
            if start != 0 or end != int(manifest_document.get("byte_length") or 0):
                raise ValueError("document term root span is not the full retained document")
            actual_digest = expected_digest
        else:
            if raw is None:
                raise ValueError("document term derived span cannot be verified without source bytes")
            source_slice = raw[start:end]
            actual_digest = hashlib.sha256(source_slice).hexdigest()
            table_match = re.search(r":table=(\d+):", locator)
            row_match = re.search(r":row=(\d+):", locator)
            if locator_type == "table" and table_match:
                table_bounds[int(table_match.group(1))] = (start, end)
            if locator_type == "text_range" and table_match and row_match and ":cell=" not in locator:
                row_bounds[(int(table_match.group(1)), int(row_match.group(1)))] = (start, end)
            role_match = re.search(r":role=([^:]+):bytes:", locator)
            if role_match:
                source_slices[role_match.group(1)] = source_slice
            if locator_type == "text_range" and f"role={term_name}" in locator:
                saw_exact_cell = True
        if actual_digest != str((span or {}).get("text_sha256") or "").lower():
            raise ValueError("document term span hash is detached from source bytes")

    disposition = str((record.get("state") or {}).get("disposition") or "")
    reported = record.get("reported") or {}
    normalized = record.get("normalized") or {}
    if normalized != reported:
        raise ValueError("document term normalized value must preserve the direct dimensional fact")
    if disposition == "observed":
        if not isinstance(reported.get("value"), str) or not isinstance(reported.get("raw_text"), str):
            raise ValueError("observed document term lacks a direct decimal value")
        if not isinstance(reported.get("unit"), str) or not isinstance(reported.get("scale"), str):
            raise ValueError("observed document term lacks explicit dimensions")
        if not saw_exact_cell:
            raise ValueError("observed document term lacks an exact field-cell span")
        security = record.get("security") or {}
        expected_type, expected_unit, expected_currency = _term_semantics(
            term_name, str(security.get("classification") or "unknown"),
            rate_scale=str(reported.get("scale") or "1"),
        )
        if (
            (record.get("term") or {}).get("term_type") != expected_type
            or reported.get("unit") != expected_unit
            or reported.get("currency") != expected_currency
        ):
            raise ValueError("observed document term dimensions contradict its security row")
        term_slice = source_slices.get(term_name)
        if term_slice is None:
            raise ValueError("observed document term lacks a bound field cell")
        cell_match = _CELL_RE.fullmatch(term_slice)
        if cell_match is None or _cell_text(cell_match.group(3)) != reported.get("raw_text"):
            raise ValueError("observed document term raw text is detached from its field cell")
        reparsed = _parse_number(
            str(reported.get("raw_text") or ""),
            allow_denominated_rate=term_name == "filing_fee_rate",
        )
        if (
            reparsed.disposition != "observed"
            or reparsed.value != reported.get("value")
            or reparsed.scale != reported.get("scale")
        ):
            raise ValueError("observed document term value/scale does not round-trip its raw cell")
    elif any(reported.get(key) is not None for key in ("raw_text", "value", "unit", "currency", "scale")):
        raise ValueError("non-observed document term carries a guessed value")

    security = record.get("security") or {}
    row_id = security.get("row_id")
    if row_id is not None:
        table_index = security.get("table_index")
        row_index = security.get("row_index")
        table_bound = table_bounds.get(table_index)
        row_bound = row_bounds.get((table_index, row_index))
        if table_bound is None or row_bound is None:
            raise ValueError("document term row identity lacks exact table/row spans")
        expected_row_id = _digest_id(
            "fee-row:cs:",
            {
                "manifest_id": manifest_id, "table_start": table_bound[0],
                "row_start": row_bound[0], "row_end": row_bound[1],
            },
        )
        if row_id != expected_row_id:
            raise ValueError("document term row_id is detached from source bytes")
        title_slice = source_slices.get("security_title")
        if title_slice is None:
            raise ValueError("document term row lacks an exact security-title cell")
        title_match = _CELL_RE.fullmatch(title_slice)
        title = _cell_text(title_match.group(3)) if title_match is not None else ""
        if (
            security.get("title_raw") != (title or None)
            or security.get("title_normalized") != (_label(title) or None)
            or security.get("classification") != _classify_security(title)
        ):
            raise ValueError("document term security identity is detached from its title cell")

    # Hash-valid byte ranges alone do not prove that a row has retained the
    # correct role, state, value, or span identity. Rebuild it using the exact
    # *declared registered parser*, not today's active parser. This preserves a
    # legitimate old semantic result while rejecting an unknown/fake parser
    # version and a fabricated additional version of the same extraction.
    actual_extraction = record.get("extraction") or {}
    declared_version = actual_extraction.get("parser_version")
    expected_by_logical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in _records_for_manifest_with_resolver(
        manifest, raw, parser_version=str(declared_version or ""),
        parser_resolver=parser_resolver,
    ):
        expected_by_logical[str(candidate["logical_observation_id"])].append(candidate)
    logical = str(record.get("logical_observation_id") or "")
    expected_records = expected_by_logical.get(logical, [])
    if not expected_records:
        raise ValueError("document term logical_observation_id is detached from source bytes")
    if len(expected_records) != 1:
        raise ValueError("document term parser re-extraction has non-unique logical_observation_id")
    expected_record = _clone_json_value(expected_records[0])
    actual_record = _clone_json_value(dict(record))
    # These fields are appended by immutable materialization, not extracted
    # from the retained source. Supersedes is likewise chain metadata; every
    # other field and nested key must compare as one closed semantic object.
    for body in (actual_record, expected_record):
        body.pop("observation_id", None)
        body.pop("version", None)
        body.pop("point_in_time", None)
        relationships = dict(body.get("relationships") or {})
        relationships["supersedes"] = []
        body["relationships"] = relationships
    if actual_record != expected_record:
        if actual_record.get("state") != expected_record.get("state"):
            differing_field = "state"
        else:
            differing_field = next(
                field
                for field in sorted(set(actual_record) | set(expected_record))
                if field not in actual_record
                or field not in expected_record
                or actual_record[field] != expected_record[field]
            )
        raise ValueError(
            f"document term {differing_field} is detached from closed retained "
            "source semantics"
        )


def _make_validate_observation_source_binding(
    policy_validator: Callable[[], _AuthorityPolicy],
    released_parser_resolver: Callable[[Any], ParserRegistration],
    source_binding_core: Callable[..., None],
    records_contract_validator: Callable[..., None],
) -> Callable[..., None]:
    """Build the public gate with trust dependencies sealed in closure cells."""
    def validate_observation_source_binding(
        record: Mapping[str, Any],
        manifest: Mapping[str, Any],
        raw: bytes | None,
    ) -> None:
        """Validate one row through the sealed released-parser source gate."""
        if globals().get("_validated_authority_policy") is not policy_validator:
            raise ValueError("document-term authority policy validator binding changed")
        if globals().get("_registered_parser") is not released_parser_resolver:
            raise ValueError("document-term released parser resolver binding changed")
        if (
            globals().get("_validate_observation_source_binding_core")
            is not source_binding_core
        ):
            raise ValueError("document-term source-binding core binding changed")
        if (
            globals().get("_validate_document_term_records_contract")
            is not records_contract_validator
        ):
            raise ValueError("document-term closed-contract binding changed")
        policy = policy_validator()
        records_contract_validator(
            [record], label="document-term source binding",
        )
        source_binding_core(
            record, manifest, raw,
            parser_resolver=released_parser_resolver, policy=policy,
        )

    return validate_observation_source_binding


def _validate_document_term_source_authority_core(
    records: Sequence[Mapping[str, Any]],
    *,
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    parser_resolver: Callable[[Any], ParserRegistration],
    policy: _AuthorityPolicy,
) -> list[dict[str, Any]]:
    """Validate an entire direct ledger against manifests and exact retained bytes.

    The append-only history is necessary but not sufficient: every version must
    independently re-derive the same source fact.  This makes a historical
    parser correction auditable without allowing a rehashed null, issuer, span,
    or logical-slot rewrite to become a valid point-in-time observation.
    """
    sources = [deepcopy(dict(raw)) for raw in records]
    manifests = [deepcopy(dict(raw)) for raw in source_manifests]
    policy.manifest_ledger_validator(manifests)
    for manifest in manifests:
        policy.manifest_content_validator(manifest)
    _validate_document_term_history_core(
        sources, parser_resolver=parser_resolver,
    )

    manifests_by_id = {str(manifest["manifest_id"]): manifest for manifest in manifests}
    source_cache: dict[str, bytes] = {}
    for index, source in enumerate(sources):
        manifest_id = str((source.get("document") or {}).get("source_manifest_id") or "")
        manifest = manifests_by_id.get(manifest_id)
        if manifest is None:
            raise ValueError(f"document term row {index} source manifest is absent")
        raw = source_cache.get(manifest_id)
        if raw is None:
            loaded = source_reader(manifest)
            if not isinstance(loaded, bytes):
                raise ValueError(f"document term row {index} retained source bytes are unavailable")
            policy.retained_bytes_validator(manifest, loaded)
            source_cache[manifest_id] = loaded
            raw = loaded
        _validate_observation_source_binding_core(
            source, manifest, raw,
            parser_resolver=parser_resolver, policy=policy,
        )
    return sources


def _make_validate_document_term_source_authority(
    policy_validator: Callable[[], _AuthorityPolicy],
    released_parser_resolver: Callable[[Any], ParserRegistration],
    source_authority_core: Callable[..., list[dict[str, Any]]],
    records_contract_validator: Callable[..., None],
) -> Callable[..., list[dict[str, Any]]]:
    """Build the public source authority without injectable trust arguments."""
    def validate_document_term_source_authority(
        records: Sequence[Mapping[str, Any]],
        *,
        source_manifests: Sequence[Mapping[str, Any]],
        source_reader: Callable[[Mapping[str, Any]], bytes | None],
    ) -> list[dict[str, Any]]:
        """Validate a direct ledger through sealed released authority only."""
        if globals().get("_validated_authority_policy") is not policy_validator:
            raise ValueError("document-term authority policy validator binding changed")
        if globals().get("_registered_parser") is not released_parser_resolver:
            raise ValueError("document-term released parser resolver binding changed")
        if (
            globals().get("_validate_document_term_source_authority_core")
            is not source_authority_core
        ):
            raise ValueError("document-term source-authority core binding changed")
        if (
            globals().get("_validate_document_term_records_contract")
            is not records_contract_validator
        ):
            raise ValueError("document-term closed-contract binding changed")
        policy = policy_validator()
        records_contract_validator(
            records, label="document-term source authority",
        )
        return source_authority_core(
            records,
            source_manifests=source_manifests,
            source_reader=source_reader,
            parser_resolver=released_parser_resolver,
            policy=policy,
        )

    return validate_document_term_source_authority


def _validate_document_term_history_core(
    records: Sequence[Mapping[str, Any]],
    *,
    parser_resolver: Callable[[Any], ParserRegistration],
) -> None:
    """Validate immutable IDs, version chains, and non-retroactive corrections."""
    by_id: set[str] = set()
    by_logical: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    verified_parser_versions: set[str] = set()
    for index, raw in enumerate(records):
        record = dict(raw)
        observation_id = str(record.get("observation_id") or "")
        if observation_id != observation_id_for(record):
            raise ValueError(f"document term row {index} observation_id digest mismatch")
        if observation_id in by_id:
            raise ValueError(f"duplicate document term observation_id {observation_id}")
        by_id.add(observation_id)
        logical = str(record.get("logical_observation_id") or "")
        if not logical:
            raise ValueError(f"document term row {index} lacks logical_observation_id")
        parser_version = str((record.get("extraction") or {}).get("parser_version") or "")
        if parser_version not in verified_parser_versions:
            parser_resolver(parser_version)
            verified_parser_versions.add(parser_version)
        point_in_time = record.get("point_in_time") or {}
        if _parse_time(point_in_time.get("available_at"), "available_at") < _parse_time(
            point_in_time.get("source_available_at"), "source_available_at",
        ):
            raise ValueError(f"document term row {index} available_at precedes source_available_at")
        by_logical[logical].append(record)

    for logical, versions in by_logical.items():
        ordered = sorted(versions, key=lambda row: int((row.get("version") or {}).get("correction_version") or 0))
        expected = list(range(1, len(ordered) + 1))
        actual = [int((row.get("version") or {}).get("correction_version") or 0) for row in ordered]
        if actual != expected:
            raise ValueError(f"document term {logical} has non-contiguous correction versions")
        for number, record in enumerate(ordered, start=1):
            version = record.get("version") or {}
            prior = ordered[number - 2] if number > 1 else None
            supersedes = list((record.get("relationships") or {}).get("supersedes") or [])
            if number == 1:
                if version.get("correction_of") is not None or supersedes:
                    raise ValueError(f"document term {logical} v1 cannot be a correction")
            if prior is not None:
                if version.get("correction_of") != prior.get("observation_id"):
                    raise ValueError(f"document term {logical} correction does not point to prior version")
                if supersedes != [prior.get("observation_id")]:
                    raise ValueError(f"document term {logical} supersedes does not point to prior version")
                prior_time = _parse_time((prior.get("point_in_time") or {}).get("available_at"), "prior.available_at")
                current_time = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
                if current_time <= prior_time:
                    raise ValueError(f"document term {logical} correction is retroactive")
                if _semantic_body(record) == _semantic_body(prior):
                    raise ValueError(
                        f"document term {logical} correction duplicates prior source semantics"
                    )


def _make_validate_document_term_history(
    policy_validator: Callable[[], _AuthorityPolicy],
    released_parser_resolver: Callable[[Any], ParserRegistration],
    history_core: Callable[..., None],
    records_contract_validator: Callable[..., None],
) -> Callable[..., None]:
    """Build the public history gate without injectable trust arguments."""
    def validate_document_term_history(
        records: Sequence[Mapping[str, Any]],
    ) -> None:
        """Validate only closed-schema rows from immutable released parsers."""
        if globals().get("_validated_authority_policy") is not policy_validator:
            raise ValueError("document-term authority policy validator binding changed")
        if globals().get("_registered_parser") is not released_parser_resolver:
            raise ValueError("document-term released parser resolver binding changed")
        if globals().get("_validate_document_term_history_core") is not history_core:
            raise ValueError("document-term history core binding changed")
        if (
            globals().get("_validate_document_term_records_contract")
            is not records_contract_validator
        ):
            raise ValueError("document-term closed-contract binding changed")
        policy_validator()
        records_contract_validator(records, label="document-term history")
        history_core(records, parser_resolver=released_parser_resolver)

    return validate_document_term_history


def _current_document_terms_as_of_core(
    records: Sequence[Mapping[str, Any]], as_of: str,
    *, parser_resolver: Callable[[Any], ParserRegistration],
) -> list[dict[str, Any]]:
    """Return the latest immutable document-term version visible on system time."""
    _validate_document_term_history_core(records, parser_resolver=parser_resolver)
    cutoff = _parse_time(as_of, "as_of")
    visible: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        record = dict(raw)
        available_at = _parse_time((record.get("point_in_time") or {}).get("available_at"), "available_at")
        if available_at > cutoff:
            continue
        logical = str(record.get("logical_observation_id") or "")
        prior = visible.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            visible[logical] = record
    return [dict(visible[key]) for key in sorted(visible)]


def _make_current_document_terms_as_of(
    policy_validator: Callable[[], _AuthorityPolicy],
    released_parser_resolver: Callable[[Any], ParserRegistration],
    current_core: Callable[..., list[dict[str, Any]]],
    records_contract_validator: Callable[..., None],
) -> Callable[..., list[dict[str, Any]]]:
    """Build the public PIT gate without injectable trust arguments."""
    def current_document_terms_as_of(
        records: Sequence[Mapping[str, Any]],
        as_of: str,
    ) -> list[dict[str, Any]]:
        """Return current released-parser facts after closed contract admission."""
        if globals().get("_validated_authority_policy") is not policy_validator:
            raise ValueError("document-term authority policy validator binding changed")
        if globals().get("_registered_parser") is not released_parser_resolver:
            raise ValueError("document-term released parser resolver binding changed")
        if globals().get("_current_document_terms_as_of_core") is not current_core:
            raise ValueError("document-term current-as-of core binding changed")
        if (
            globals().get("_validate_document_term_records_contract")
            is not records_contract_validator
        ):
            raise ValueError("document-term closed-contract binding changed")
        policy_validator()
        records_contract_validator(
            records, label="document-term current-as-of",
        )
        return current_core(
            records, as_of, parser_resolver=released_parser_resolver,
        )

    return current_document_terms_as_of


def _compile_document_term_records_core(
    manifests: Sequence[Mapping[str, Any]],
    *,
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    existing_observations: Sequence[Mapping[str, Any]] = (),
    generated_at: str,
    rebuild: bool = False,
    parser_resolver: Callable[[Any], ParserRegistration],
    active_parser_version: str,
    policy: _AuthorityPolicy,
) -> dict[str, Any]:
    """Pure compile surface. ``source_reader`` must return exact manifest bytes.

    All in-scope source reads happen before any candidate is versioned. A missing
    or hash-mismatched object aborts the whole run, preserving the previous
    telemetry-last generation instead of publishing a misleading partial ledger.
    """
    manifest_rows = [dict(item) for item in manifests]
    policy.manifest_ledger_validator(manifest_rows)
    for manifest in manifest_rows:
        policy.manifest_content_validator(manifest)
    generated = _iso(generated_at, "generated_at")
    active_parser_version = parser_resolver(active_parser_version).version
    existing = [dict(item) for item in existing_observations]
    _validate_document_term_records_contract(
        existing, label="document-term compiler existing history",
    )
    _validate_document_term_history_core(
        existing, parser_resolver=parser_resolver,
    )

    current_by_logical: dict[str, Mapping[str, Any]] = {}
    for record in existing:
        logical = str(record["logical_observation_id"])
        prior = current_by_logical.get(logical)
        if prior is None or int((record.get("version") or {}).get("correction_version") or 0) > int((prior.get("version") or {}).get("correction_version") or 0):
            current_by_logical[logical] = record

    selected = _selected_registration_manifests(manifest_rows)
    current_by_manifest: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for prior in current_by_logical.values():
        current_by_manifest[str((prior.get("document") or {}).get("source_manifest_id") or "")].append(prior)
    materialize = [
        manifest for manifest in selected
        if rebuild
        or not current_by_manifest.get(str(manifest["manifest_id"]))
        or any(
            str((prior.get("extraction") or {}).get("parser_version") or "") != active_parser_version
            for prior in current_by_manifest[str(manifest["manifest_id"])]
        )
    ]
    failures: list[dict[str, Any]] = []
    source_bytes: dict[str, bytes] = {}
    for manifest in materialize:
        manifest_id = str(manifest["manifest_id"])
        raw = source_reader(manifest)
        expected = str((manifest.get("document") or {}).get("content_sha256") or "").lower()
        if raw is None:
            failures.append({"accession": (manifest.get("filing") or {}).get("accession"), "state": "source_bytes_unavailable", "errors": [manifest_id]})
            continue
        if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected:
            failures.append({"accession": (manifest.get("filing") or {}).get("accession"), "state": "source_bytes_digest_mismatch", "errors": [manifest_id]})
            continue
        try:
            policy.retained_bytes_validator(manifest, raw)
        except ValueError as exc:
            failures.append({"accession": (manifest.get("filing") or {}).get("accession"), "state": "source_identity_detached", "errors": [str(exc)]})
            continue
        source_bytes[manifest_id] = raw
    if failures:
        raise DocumentTermCompileDegraded(failures)

    incoming: list[dict[str, Any]] = []
    unchanged = 0
    for manifest in materialize:
        for candidate in _records_for_manifest_with_resolver(
            manifest,
            source_bytes[str(manifest["manifest_id"])],
            parser_version=active_parser_version,
            parser_resolver=parser_resolver,
        ):
            logical = str(candidate["logical_observation_id"])
            prior = current_by_logical.get(logical)
            if prior is not None and _semantic_body(prior) == _semantic_body(candidate):
                unchanged += 1
                continue
            _materialize_observation(candidate, prior, generated)
            _validate_document_term_records_contract(
                [candidate], label="document-term compiler candidate",
            )
            _validate_observation_source_binding_core(
                candidate,
                manifest,
                source_bytes[str(manifest["manifest_id"])],
                parser_resolver=parser_resolver,
                policy=policy,
            )
            incoming.append(candidate)
            current_by_logical[logical] = candidate

    output = [*existing, *incoming]
    _validate_document_term_records_contract(
        output, label="document-term compiler output",
    )
    _validate_document_term_source_authority_core(
        output,
        source_manifests=manifest_rows,
        source_reader=source_reader,
        parser_resolver=parser_resolver,
        policy=policy,
    )
    return {
        "observations": output,
        "new_observations": incoming,
        "counts": {
            "eligible_complete_submissions": len(selected),
            "processed_complete_submissions": len(materialize),
            "observations": len(output),
            "new_observations": len(incoming),
            "unchanged_observations": unchanged,
            "observed": sum(1 for row in output if (row.get("state") or {}).get("disposition") == "observed"),
            "unavailable": sum(1 for row in output if (row.get("state") or {}).get("disposition") == "unavailable"),
            "ambiguous": sum(1 for row in output if (row.get("state") or {}).get("disposition") == "ambiguous"),
        },
    }


def _make_compile_document_term_records(
    policy_validator: Callable[[], _AuthorityPolicy],
    released_parser_resolver: Callable[[Any], ParserRegistration],
    compiler_core: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    """Build the public compiler without injectable trust arguments."""
    def compile_document_term_records(
        manifests: Sequence[Mapping[str, Any]],
        *,
        source_reader: Callable[[Mapping[str, Any]], bytes | None],
        existing_observations: Sequence[Mapping[str, Any]] = (),
        generated_at: str,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        """Compile with only the immutable released parser/policy registries."""
        if globals().get("_validated_authority_policy") is not policy_validator:
            raise ValueError("document-term authority policy validator binding changed")
        if globals().get("_registered_parser") is not released_parser_resolver:
            raise ValueError("document-term released parser resolver binding changed")
        if globals().get("_compile_document_term_records_core") is not compiler_core:
            raise ValueError("document-term compiler core binding changed")
        policy = policy_validator()
        return compiler_core(
            manifests,
            source_reader=source_reader,
            existing_observations=existing_observations,
            generated_at=generated_at,
            rebuild=rebuild,
            parser_resolver=released_parser_resolver,
            active_parser_version=PARSER_VERSION,
            policy=policy,
        )

    return compile_document_term_records


def _test_lane_resolver(
    lane: _TestParserLane, *, capability: object,
) -> Callable[[Any], ParserRegistration]:
    if (
        capability is not _PRIVATE_TEST_PARSER_CAPABILITY
        or lane.capability is not capability
    ):
        raise ValueError("document-term test parser capability is invalid")

    def resolve(version: Any) -> ParserRegistration:
        return _registered_test_parser(
            version, lane=lane, capability=capability,
        )

    return resolve


def _compile_document_term_records_test_lane(
    manifests: Sequence[Mapping[str, Any]],
    *,
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    parser_lane: _TestParserLane,
    parser_version: str,
    capability: object,
    existing_observations: Sequence[Mapping[str, Any]] = (),
    generated_at: str,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Private synthetic-history compiler; never consulted by public APIs."""
    policy = _validated_authority_policy()
    return _compile_document_term_records_core(
        manifests,
        source_reader=source_reader,
        existing_observations=existing_observations,
        generated_at=generated_at,
        rebuild=rebuild,
        parser_resolver=_test_lane_resolver(parser_lane, capability=capability),
        active_parser_version=parser_version,
        policy=policy,
    )


def _validate_document_term_source_authority_test_lane(
    records: Sequence[Mapping[str, Any]],
    *,
    source_manifests: Sequence[Mapping[str, Any]],
    source_reader: Callable[[Mapping[str, Any]], bytes | None],
    parser_lane: _TestParserLane,
    capability: object,
) -> list[dict[str, Any]]:
    policy = _validated_authority_policy()
    _validate_document_term_records_contract(
        records, label="document-term private test source authority",
    )
    return _validate_document_term_source_authority_core(
        records,
        source_manifests=source_manifests,
        source_reader=source_reader,
        parser_resolver=_test_lane_resolver(parser_lane, capability=capability),
        policy=policy,
    )


def _current_document_terms_as_of_test_lane(
    records: Sequence[Mapping[str, Any]],
    as_of: str,
    *,
    parser_lane: _TestParserLane,
    capability: object,
) -> list[dict[str, Any]]:
    _validated_authority_policy()
    _validate_document_term_records_contract(
        records, label="document-term private test current-as-of",
    )
    return _current_document_terms_as_of_core(
        records,
        as_of,
        parser_resolver=_test_lane_resolver(parser_lane, capability=capability),
    )


def _authority_policy_entrypoints() -> tuple[SemanticEntrypoint, ...]:
    return (
        SemanticEntrypoint("manifest_ledger", validate_manifest_ledger),
        SemanticEntrypoint("manifest_content", validate_manifest_content_binding),
        SemanticEntrypoint(
            "retained_source_identity", validate_manifest_retained_bytes_binding,
        ),
        SemanticEntrypoint(
            "closed_observation_contract", _validate_document_term_records_contract,
        ),
        SemanticEntrypoint("zero_authority", _assert_zero_authority),
        SemanticEntrypoint(
            "observation_source_binding", _validate_observation_source_binding_core,
        ),
        SemanticEntrypoint("history", _validate_document_term_history_core),
        SemanticEntrypoint(
            "source_authority", _validate_document_term_source_authority_core,
        ),
        SemanticEntrypoint("current_as_of", _current_document_terms_as_of_core),
        SemanticEntrypoint("compiler", _compile_document_term_records_core),
    )


# Release goldens are recalculated only when the authority implementation or its
# closed schema intentionally changes. They are independent of parser-version
# goldens so a mutable parser registration can never rewrite trust policy.
_AUTHORITY_POLICY_DEPENDENCY_COUNT = 421
_AUTHORITY_POLICY_DEPENDENCY_MANIFEST_SHA256 = (
    "de327cf44e5e00e5a43e36f0f26ddc4ba71d3f2ea662a93c303d9af3a46142fa"
)
_AUTHORITY_POLICY_IMPLEMENTATION_SHA256 = (
    "3650894df320e83771b1d9c0de6fd658cde50e2d7533cb958fc835837c32a18c"
)

_AUTHORITY_POLICY = _AuthorityPolicy(
    entrypoints=_authority_policy_entrypoints(),
    dependency_count=_AUTHORITY_POLICY_DEPENDENCY_COUNT,
    dependency_manifest_sha256=_AUTHORITY_POLICY_DEPENDENCY_MANIFEST_SHA256,
    implementation_sha256=_AUTHORITY_POLICY_IMPLEMENTATION_SHA256,
    alias_bindings=(
        ("validate_manifest_ledger", validate_manifest_ledger),
        ("validate_manifest_content_binding", validate_manifest_content_binding),
        (
            "validate_manifest_retained_bytes_binding",
            validate_manifest_retained_bytes_binding,
        ),
        (
            "_validate_document_term_records_contract",
            _validate_document_term_records_contract,
        ),
        (
            "_validate_observation_source_binding_core",
            _validate_observation_source_binding_core,
        ),
        ("_validate_document_term_history_core", _validate_document_term_history_core),
        (
            "_validate_document_term_source_authority_core",
            _validate_document_term_source_authority_core,
        ),
        ("_current_document_terms_as_of_core", _current_document_terms_as_of_core),
        ("_compile_document_term_records_core", _compile_document_term_records_core),
    ),
    manifest_ledger_validator=validate_manifest_ledger,
    manifest_content_validator=validate_manifest_content_binding,
    retained_bytes_validator=validate_manifest_retained_bytes_binding,
)


def _make_validated_authority_policy(
    policy: _AuthorityPolicy,
    semantic_closure: Callable[..., tuple[tuple[str, ...], str, str]],
    digest_comparator: Callable[[str, str], bool],
) -> Callable[[], _AuthorityPolicy]:
    """Seal the policy object and integrity primitives outside call arguments."""
    def _validated_authority_policy() -> _AuthorityPolicy:
        """Recheck the sealed trust policy and imported aliases before each use."""
        if globals().get("_semantic_closure") is not semantic_closure:
            raise ValueError("document-term authority closure binding changed")
        for name, expected in policy.alias_bindings:
            if globals().get(name) is not expected:
                raise ValueError(
                    f"document-term authority policy binding changed: {name}"
                )
        try:
            manifest, manifest_sha256, implementation_sha256 = semantic_closure(
                policy.entrypoints,
            )
        except ValueError as exc:
            raise ValueError("document-term authority policy closure mismatch") from exc
        if (
            len(manifest) != policy.dependency_count
            or not digest_comparator(
                manifest_sha256, policy.dependency_manifest_sha256,
            )
            or not digest_comparator(
                implementation_sha256, policy.implementation_sha256,
            )
        ):
            raise ValueError("document-term authority policy closure mismatch")
        return policy

    return _validated_authority_policy


_validated_authority_policy = _make_validated_authority_policy(
    _AUTHORITY_POLICY, _semantic_closure, hmac.compare_digest,
)

validate_document_term_contract = _make_validate_document_term_contract(
    _validated_authority_policy,
    _validate_document_term_records_contract,
)
validate_observation_source_binding = _make_validate_observation_source_binding(
    _validated_authority_policy,
    _registered_parser,
    _validate_observation_source_binding_core,
    _validate_document_term_records_contract,
)
validate_document_term_source_authority = (
    _make_validate_document_term_source_authority(
        _validated_authority_policy,
        _registered_parser,
        _validate_document_term_source_authority_core,
        _validate_document_term_records_contract,
    )
)
validate_document_term_history = _make_validate_document_term_history(
    _validated_authority_policy,
    _registered_parser,
    _validate_document_term_history_core,
    _validate_document_term_records_contract,
)
current_document_terms_as_of = _make_current_document_terms_as_of(
    _validated_authority_policy,
    _registered_parser,
    _current_document_terms_as_of_core,
    _validate_document_term_records_contract,
)
compile_document_term_records = _make_compile_document_term_records(
    _validated_authority_policy,
    _registered_parser,
    _compile_document_term_records_core,
)


def _self_check_authority_policy() -> None:
    try:
        _validated_authority_policy()
    except ValueError as exc:
        raise RuntimeError(
            "document-term authority policy startup self-check failed"
        ) from exc


_self_check_parser_registry()
_self_check_authority_policy()
