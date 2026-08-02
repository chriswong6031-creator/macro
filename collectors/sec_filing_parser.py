"""Strict, bounded, offline SEC XBRL and Inline XBRL parser.

The parser deliberately implements a small evidence contract rather than a
general XML, HTML, or XBRL processor.  It never recovers malformed markup,
resolves an external resource, loads a taxonomy, or guesses an unknown Inline
XBRL transformation.  Every emitted object remains tied to an exact byte range
in the supplied filing member.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
from bisect import bisect_left
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
import sys
from types import MappingProxyType
from typing import Any, Mapping
from xml.parsers import expat


SEC_FILING_PARSER_SCHEMA = "fundamental_forensics.sec_filing_parser/v1"
SEC_FILING_PARSER_PROFILE = "strict_offline_ixbrl/v1"
SEC_FILING_PARSER_VERSION = "1"
# Stable semantic compatibility authority.  It changes only when the
# deterministic grammar/value algorithms change; runtime library versions are
# observed provenance and must not invalidate retained evidence on replay.
SEC_FILING_PARSER_ALGORITHM_FINGERPRINT = "91bcf478ce54131677929138732113f24bba04a88ef7ccb37d4f299b5df38b52"

XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
XML = "http://www.w3.org/XML/1998/namespace"
XHTML = "http://www.w3.org/1999/xhtml"
XINCLUDE = "http://www.w3.org/2001/XInclude"
LINK = "http://www.xbrl.org/2003/linkbase"
# This parser deliberately admits one Inline XBRL profile.  Treating the 1.0
# and 1.1 vocabularies as interchangeable would make otherwise-invalid
# documents look canonical, particularly around continuations and headers.
IX11 = "http://www.xbrl.org/2013/inlineXBRL"
IX10 = "http://www.xbrl.org/2008/inlineXBRL"
IX_NAMESPACES = frozenset({IX11})
LEGACY_IX_NAMESPACES = frozenset({IX10})
TRR3 = "http://www.xbrl.org/inlineXBRL/transformation/2015-02-26"
TRR4 = "http://www.xbrl.org/inlineXBRL/transformation/2020-02-12"

SUPPORTED_TRANSFORMS: Mapping[str, str] = {
    f"{{{TRR3}}}nocontent": "empty",
    f"{{{TRR3}}}numcommadecimal": "numeric_comma_decimal",
    f"{{{TRR3}}}numdotdecimal": "numeric_dot_decimal",
    f"{{{TRR3}}}zerodash": "zero",
    f"{{{TRR4}}}fixed-empty": "empty",
    f"{{{TRR4}}}fixed-zero": "zero",
    f"{{{TRR4}}}num-comma-decimal": "numeric_comma_decimal_relaxed",
    f"{{{TRR4}}}num-dot-decimal": "numeric_dot_decimal_relaxed",
}

_HARD_LIMITS = MappingProxyType({
    "max_bytes": 32 * 1024 * 1024,
    "max_nodes": 100_000,
    "max_depth": 128,
    "max_attributes_per_element": 256,
    "max_total_attributes": 500_000,
    "max_attribute_bytes": 256 * 1024,
    "max_total_attribute_bytes": 16 * 1024 * 1024,
    "max_name_bytes": 4 * 1024,
    "max_namespaces_per_element": 64,
    "max_in_scope_namespaces": 64,
    "max_total_namespace_bytes": 8 * 1024 * 1024,
    "max_text_bytes": 16 * 1024 * 1024,
    "max_text_events": 100_000,
    "max_fact_text_bytes": 1 * 1024 * 1024,
    "max_contexts": 5_000,
    "max_units": 2_000,
    "max_facts": 10_000,
    "max_continuations": 10_000,
    "max_continuation_chain": 16,
    "max_dimensions_per_context": 256,
    "max_measures_per_unit": 256,
    "max_abs_scale": 308,
    "max_output_bytes": 24 * 1024 * 1024,
    "max_metadata_bytes": 16 * 1024,
})
# Public immutable admission profile.  A deployment may replace the mapping
# with lower values before a parse; `_limits_snapshot` always clamps those
# values to the non-configurable hard ceilings above.
PARSER_LIMITS: Mapping[str, int] = _HARD_LIMITS

_TOP_FIELDS = frozenset(
    {"schema", "parser", "source", "document", "contexts", "units", "continuations", "facts", "diagnostics", "coverage"}
)
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")
_NUMERIC_RE = re.compile(r"^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")
_NCNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$"
)
_FORBIDDEN_DECL_RE = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_XML_DECL_RE = re.compile(br"^(?:\xef\xbb\xbf)?\s*<\?xml\s+([^?]*)\?>", re.IGNORECASE)
_ENCODING_RE = re.compile(br"\bencoding\s*=\s*(['\"])([^'\"]+)\1", re.IGNORECASE)
# Keep integer conversion far below CPython's configurable string-to-int
# threshold.  These attributes are tiny semantic controls, never quantities
# whose unbounded lexical length is useful to this evidence profile.
_MAX_INTEGER_LEXICAL_DIGITS = 64


class SecFilingParseError(ValueError):
    """The filing member cannot satisfy the strict offline parse contract."""


def _qname(raw: str) -> str:
    if "}" not in raw:
        return raw
    uri, local = raw.split("}", 1)
    return f"{{{uri}}}{local}"


def _split_qname(name: str) -> tuple[str | None, str]:
    if name.startswith("{") and "}" in name:
        uri, local = name[1:].split("}", 1)
        return uri, local
    return None, name


def _attr(node: "_Node", local: str, uri: str | None = None) -> str | None:
    key = f"{{{uri}}}{local}" if uri else local
    return node.attrs.get(key)


def _span(start: int, end: int) -> dict[str, int]:
    return {"start": start, "end": end}


@dataclass
class _TextEvent:
    start: int
    value: str
    # An exclusion is relative to the fact being reconstructed.  A nested
    # fact inside an outer ix:exclude must still retain its own text.
    exclude_ancestors: tuple["_Node", ...]
    owner: "_Node | None" = None
    end: int | None = None


class _TextEvents(list[_TextEvent]):
    """Source-ordered events with a precomputed bisect index."""

    starts: list[int]

    def finalize(self) -> None:
        self.starts = [item.start for item in self]


@dataclass
class _Node:
    qname: str
    lexical_name: str
    attrs: dict[str, str]
    namespaces: dict[str, str]
    start: int
    start_tag_end: int
    self_closing: bool
    parent: "_Node | None"
    children: list["_Node"] = field(default_factory=list)
    end: int | None = None

    @property
    def namespace(self) -> str | None:
        return _split_qname(self.qname)[0]

    @property
    def local(self) -> str:
        return _split_qname(self.qname)[1]


def _tag_end(content: bytes, start: int) -> int:
    quote = 0
    index = start + 1
    while index < len(content):
        byte = content[index]
        if quote:
            if byte == quote:
                quote = 0
        elif byte in (34, 39):
            quote = byte
        elif byte == 62:
            return index + 1
        index += 1
    raise SecFilingParseError("unterminated XML tag")


def _lexical_element_name(content: bytes, start: int, tag_end: int) -> str:
    match = re.match(br"<\s*([^\s/>]+)", content[start:tag_end])
    if match is None:
        raise SecFilingParseError("cannot recover lexical element name")
    try:
        return match.group(1).decode("utf-8", "strict")
    except UnicodeError as exc:
        raise SecFilingParseError("element name is not valid UTF-8") from exc


def _safe_document_name(value: Any) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise SecFilingParseError("document_name must be non-empty normalized text")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise SecFilingParseError("document_name is not valid UTF-8") from exc
    parts = value.split("/")
    if (
        len(encoded) > _HARD_LIMITS["max_metadata_bytes"]
        or not _SAFE_NAME_RE.fullmatch(value)
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise SecFilingParseError("document_name is not a safe archive member name")
    return value


def _resolve_qname(value: str, namespaces: Mapping[str, str], *, field_name: str) -> str:
    if not value or value != value.strip() or any(char.isspace() for char in value):
        raise SecFilingParseError(f"{field_name} is not a normalized QName")
    if value.count(":") > 1:
        raise SecFilingParseError(f"{field_name} is not a lexical QName")
    if ":" in value:
        prefix, local = value.split(":", 1)
        if not _NCNAME_RE.fullmatch(prefix) or not _NCNAME_RE.fullmatch(local):
            raise SecFilingParseError(f"{field_name} is not a lexical QName")
        uri = namespaces.get(prefix)
        if uri is None:
            raise SecFilingParseError(f"{field_name} contains an unbound QName")
        return f"{{{uri}}}{local}"
    if not _NCNAME_RE.fullmatch(value):
        raise SecFilingParseError(f"{field_name} is not a lexical QName")
    uri = namespaces.get("")
    return f"{{{uri}}}{value}" if uri else value


def _resolve_required_qname(value: str, namespaces: Mapping[str, str], *, field_name: str) -> str:
    resolved = _resolve_qname(value, namespaces, field_name=field_name)
    if not resolved.startswith("{"):
        raise SecFilingParseError(f"{field_name} must resolve to a namespace")
    return resolved


def _resolve_prefixed_qname(value: str, namespaces: Mapping[str, str], *, field_name: str) -> str:
    """Resolve an XBRL QName-valued field whose vocabulary requires a prefix."""
    if value.count(":") != 1:
        raise SecFilingParseError(f"{field_name} must be a prefixed QName")
    return _resolve_required_qname(value, namespaces, field_name=field_name)


def _normalized_identifier(value: str | None, *, field_name: str) -> str:
    if value is None or not value or value != value.strip() or any(char.isspace() for char in value):
        raise SecFilingParseError(f"{field_name} is required and normalized")
    if not _NCNAME_RE.fullmatch(value):
        raise SecFilingParseError(f"{field_name} is not a valid XML NCName")
    return value


class _TreeBuilder:
    def __init__(self, content: bytes, limits: Mapping[str, int]):
        self.content = content
        self.limits = limits
        # An explicit UTF-8 override prevents a contradictory XML declaration
        # from making Expat reinterpret already-admitted UTF-8 bytes.
        self.parser = expat.ParserCreate("UTF-8", namespace_separator="}")
        self.parser.buffer_text = False
        self.parser.ordered_attributes = True
        self.parser.specified_attributes = True
        self.parser.StartElementHandler = self.start
        self.parser.EndElementHandler = self.end
        self.parser.CharacterDataHandler = self.text
        self.parser.StartNamespaceDeclHandler = self.namespace_start
        self.parser.EndNamespaceDeclHandler = lambda _prefix: None
        self.parser.StartDoctypeDeclHandler = self.forbidden
        self.parser.EntityDeclHandler = self.forbidden
        self.parser.UnparsedEntityDeclHandler = self.forbidden
        self.parser.NotationDeclHandler = self.forbidden
        self.parser.SkippedEntityHandler = self.forbidden
        self.parser.ExternalEntityRefHandler = self.external
        self.parser.StartCdataSectionHandler = self.boundary
        self.parser.EndCdataSectionHandler = self.boundary
        self.parser.CommentHandler = lambda _text: self.boundary()
        self.parser.ProcessingInstructionHandler = lambda _target, _data: self.boundary()
        self.parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        try:
            self.parser.UseForeignDTD(False)
        except AttributeError:  # pragma: no cover - all supported CPython builds expose it.
            pass
        self.stack: list[_Node] = []
        self.nodes: list[_Node] = []
        self.text_events: _TextEvents = _TextEvents()
        self.pending_text: _TextEvent | None = None
        self.pending_namespaces: list[tuple[str, str | None]] = []
        self.total_attributes = 0
        self.total_attribute_bytes = 0
        self.total_namespace_bytes = 0
        self.pending_namespace_bytes = 0
        self.total_text_bytes = 0
        self.root: _Node | None = None

    def _index(self) -> int:
        return int(self.parser.CurrentByteIndex)

    def _close_pending(self, at: int) -> None:
        if self.pending_text is not None:
            if at < self.pending_text.start or at > len(self.content):
                raise SecFilingParseError("XML parser reported an invalid byte boundary")
            self.pending_text.end = at
            self.pending_text = None

    def boundary(self, *_args: Any) -> None:
        self._close_pending(self._index())

    def namespace_start(self, prefix: str | None, uri: str | None) -> None:
        encoded = (prefix or "").encode("utf-8", "strict")
        if uri is not None:
            encoded += uri.encode("utf-8", "strict")
        if len(self.pending_namespaces) >= self.limits["max_namespaces_per_element"]:
            raise SecFilingParseError("per-element namespace declaration attribute limit exceeded")
        self.pending_namespace_bytes += len(encoded)
        self.total_namespace_bytes += len(encoded)
        if self.pending_namespace_bytes > self.limits["max_attribute_bytes"]:
            raise SecFilingParseError("per-element namespace declaration bytes exceeded")
        if self.total_namespace_bytes > self.limits["max_total_namespace_bytes"]:
            raise SecFilingParseError("total namespace declaration bytes exceeded")
        # Namespace declarations are attributes for document accounting too;
        # otherwise an xmlns flood bypasses the public attr caps.
        self.total_attribute_bytes += len(encoded)
        if self.total_attribute_bytes > self.limits["max_total_attribute_bytes"]:
            raise SecFilingParseError("total XML attribute byte limit exceeded")
        self.pending_namespaces.append((prefix or "", uri))

    def forbidden(self, *_args: Any) -> None:
        raise SecFilingParseError("DTD and entity declarations are forbidden")

    def external(self, *_args: Any) -> int:
        raise SecFilingParseError("external entity resolution is forbidden")

    def start(self, raw_name: str, raw_attrs: list[str]) -> None:
        start = self._index()
        self._close_pending(start)
        if len(self.nodes) >= self.limits["max_nodes"]:
            raise SecFilingParseError("XML node limit exceeded")
        if len(self.stack) + 1 > self.limits["max_depth"]:
            raise SecFilingParseError("XML depth limit exceeded")
        if len(raw_attrs) % 2:
            raise SecFilingParseError("XML parser returned malformed attributes")
        attr_count = len(raw_attrs) // 2 + len(self.pending_namespaces)
        if attr_count > self.limits["max_attributes_per_element"]:
            raise SecFilingParseError("per-element attribute limit exceeded")
        self.total_attributes += attr_count
        if self.total_attributes > self.limits["max_total_attributes"]:
            raise SecFilingParseError("total attribute limit exceeded")
        attrs: dict[str, str] = {}
        element_attribute_bytes = self.pending_namespace_bytes
        for index in range(0, len(raw_attrs), 2):
            name = _qname(raw_attrs[index])
            if name in attrs:
                raise SecFilingParseError("duplicate XML attribute")
            value = raw_attrs[index + 1]
            try:
                byte_count = len(raw_attrs[index].encode("utf-8", "strict")) + len(value.encode("utf-8", "strict"))
            except UnicodeError as exc:
                raise SecFilingParseError("XML attribute is not valid UTF-8") from exc
            if len(raw_attrs[index].encode("utf-8", "strict")) > self.limits["max_name_bytes"]:
                raise SecFilingParseError("XML attribute name byte limit exceeded")
            element_attribute_bytes += byte_count
            self.total_attribute_bytes += byte_count
            if element_attribute_bytes > self.limits["max_attribute_bytes"]:
                raise SecFilingParseError("per-element XML attribute byte limit exceeded")
            if self.total_attribute_bytes > self.limits["max_total_attribute_bytes"]:
                raise SecFilingParseError("total XML attribute byte limit exceeded")
            attrs[name] = value
        parent = self.stack[-1] if self.stack else None
        namespaces = dict(parent.namespaces) if parent else {"xml": XML}
        for prefix, uri in self.pending_namespaces:
            if uri is None:
                namespaces.pop(prefix, None)
            else:
                namespaces[prefix] = uri
        if len(namespaces) > self.limits["max_in_scope_namespaces"]:
            raise SecFilingParseError("in-scope namespace limit exceeded")
        self.pending_namespaces.clear()
        end = _tag_end(self.content, start)
        lexical = _lexical_element_name(self.content, start, end)
        if len(lexical.encode("utf-8", "strict")) > self.limits["max_name_bytes"]:
            raise SecFilingParseError("XML element name byte limit exceeded")
        self_closing = self.content[start:end].rstrip().endswith(b"/>")
        node = _Node(
            qname=_qname(raw_name),
            lexical_name=lexical,
            attrs=attrs,
            namespaces=namespaces,
            start=start,
            start_tag_end=end,
            self_closing=self_closing,
            parent=parent,
        )
        if node.namespace == XINCLUDE:
            raise SecFilingParseError("XInclude is forbidden")
        if parent:
            parent.children.append(node)
        elif self.root is not None:
            raise SecFilingParseError("multiple XML roots are forbidden")
        else:
            self.root = node
        self.nodes.append(node)
        self.stack.append(node)
        self.pending_namespace_bytes = 0

    def end(self, _raw_name: str) -> None:
        index = self._index()
        self._close_pending(index)
        if not self.stack:
            raise SecFilingParseError("XML element stack underflow")
        node = self.stack.pop()
        node.end = index if node.self_closing else _tag_end(self.content, index)

    def text(self, value: str) -> None:
        if not value:
            return
        if len(self.text_events) >= self.limits["max_text_events"]:
            raise SecFilingParseError("XML text event limit exceeded")
        index = self._index()
        self._close_pending(index)
        encoded_length = len(value.encode("utf-8", "strict"))
        self.total_text_bytes += encoded_length
        if self.total_text_bytes > self.limits["max_text_bytes"]:
            raise SecFilingParseError("XML text limit exceeded")
        excludes = tuple(
            node for node in self.stack if node.namespace in IX_NAMESPACES and node.local == "exclude"
        )
        event = _TextEvent(start=index, value=value, exclude_ancestors=excludes, owner=self.stack[-1])
        self.text_events.append(event)
        self.pending_text = event

    def build(self) -> tuple[_Node, list[_Node], list[_TextEvent]]:
        try:
            self.parser.Parse(self.content, True)
            self._close_pending(len(self.content))
        except SecFilingParseError:
            raise
        except (expat.ExpatError, UnicodeError, ValueError, OverflowError) as exc:
            raise SecFilingParseError(f"malformed or unsafe XML: {exc}") from exc
        if self.root is None or self.stack:
            raise SecFilingParseError("XML document has no complete root")
        if any(node.end is None for node in self.nodes) or any(event.end is None for event in self.text_events):
            raise SecFilingParseError("XML parser did not close every byte span")
        self.text_events.finalize()
        return self.root, self.nodes, self.text_events


def _descendants(node: _Node) -> list[_Node]:
    out: list[_Node] = []
    stack = list(reversed(node.children))
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(reversed(current.children))
    return out


def _first(node: _Node, uri: str, local: str) -> _Node | None:
    return next(
        (item for item in _descendants(node) if item.namespace == uri and item.local == local),
        None,
    )


def _is_descendant(node: _Node, ancestor: _Node) -> bool:
    current: _Node | None = node
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _events_for(node: _Node, events: list[_TextEvent], *, excluded: bool) -> list[_TextEvent]:
    assert node.end is not None
    # Text events are already source ordered.  The custom list avoids a full
    # scan for every fact/continuation in large filings.
    starts = events.starts if isinstance(events, _TextEvents) else [item.start for item in events]
    left = bisect_left(starts, node.start_tag_end)
    right = bisect_left(starts, int(node.end))
    selected: list[_TextEvent] = []
    for item in events[left:right]:
        relative_excluded = any(_is_descendant(exclude, node) for exclude in item.exclude_ancestors)
        if relative_excluded is excluded:
            selected.append(item)
    return selected


def _event_spans(events: list[_TextEvent]) -> list[dict[str, int]]:
    return [_span(event.start, int(event.end)) for event in events]


def _text_value(node: _Node, events: list[_TextEvent], *, include_excluded: bool = False) -> str:
    selected = _events_for(node, events, excluded=False)
    if include_excluded:
        selected += _events_for(node, events, excluded=True)
        selected.sort(key=lambda event: event.start)
    return "".join(event.value for event in selected)


def _node_text_bytes(value: str, limits: Mapping[str, int], *, field_name: str) -> str:
    if len(value.encode("utf-8", "strict")) > limits["max_fact_text_bytes"]:
        raise SecFilingParseError(f"{field_name} text byte limit exceeded")
    return value


def _trim_text(value: str) -> str:
    return " ".join(value.split())


def _parse_bool(value: str | None, *, field_name: str) -> bool:
    if value is None:
        return False
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    raise SecFilingParseError(f"{field_name} must be an XML boolean")


def _checked_integer(value: str, *, field_name: str) -> int:
    """Parse a bounded XML integer without leaking runtime conversion errors."""
    if not _INTEGER_RE.fullmatch(value):
        raise SecFilingParseError(f"{field_name} must be an integer")
    digits = value[1:] if value[:1] in {"+", "-"} else value
    if len(digits) > _MAX_INTEGER_LEXICAL_DIGITS:
        raise SecFilingParseError(f"{field_name} integer lexical value exceeds its safety limit")
    try:
        return int(value)
    except (ValueError, OverflowError) as exc:  # Defensive across Python runtimes.
        raise SecFilingParseError(f"{field_name} must be an integer") from exc


def _validate_accuracy_lexicals(
    decimals: str | None, precision: str | None, *, field_name: str = "fact"
) -> None:
    """Validate the shared decimals/precision lexical contract."""
    if decimals is not None and precision is not None:
        raise SecFilingParseError(f"{field_name} cannot specify both decimals and precision")
    for label, lexical in (("decimals", decimals), ("precision", precision)):
        if lexical is not None and lexical != "INF":
            parsed = _checked_integer(lexical, field_name=f"{field_name} {label}")
            if label == "precision" and parsed <= 0:
                raise SecFilingParseError(f"{field_name} precision must be positive or INF")


def _optional_integer(value: str | None, *, field_name: str, absolute_maximum: int) -> int | None:
    if value is None:
        return None
    result = _checked_integer(value, field_name=field_name)
    if abs(result) > absolute_maximum:
        raise SecFilingParseError(f"{field_name} exceeds its safety limit")
    return result


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise SecFilingParseError("numeric value is not finite")
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _numeric_lexical(value: str, *, transform: str) -> str:
    """Apply only the declared registry lexical language; never guess groups.

    TRR3 keeps conventional three-digit groups.  TRR4 intentionally relaxes
    group placement, but still permits only its declared separator family and
    never treats both decimal separators as interchangeable.
    """
    text = value.strip()
    if transform == "identity_numeric":
        if not _NUMERIC_RE.fullmatch(text):
            raise SecFilingParseError("numeric lexical value is invalid")
        return text
    if transform == "numeric_dot_decimal":
        pattern = r"^(?:[0-9]{1,3}(?:[, \u00a0][0-9]{3})+|[0-9]+)(?:\.[0-9]+)?$"
        if not re.fullmatch(pattern, text):
            raise SecFilingParseError("numeric dot-decimal lexical value is invalid")
        return re.sub(r"[, \u00a0]", "", text)
    if transform == "numeric_comma_decimal":
        pattern = r"^(?:[0-9]{1,3}(?:[. \u00a0][0-9]{3})+|[0-9]+)(?:,[0-9]+)?$"
        if not re.fullmatch(pattern, text):
            raise SecFilingParseError("numeric comma-decimal lexical value is invalid")
        return re.sub(r"[. \u00a0]", "", text).replace(",", ".")
    if transform == "numeric_dot_decimal_relaxed":
        # TRR4: separators other than the dot may occur in the integer part;
        # whitespace is a legal digit separator.  A dot can occur only once,
        # as the decimal separator.
        if not re.fullmatch(r"(?:[0-9]|[, \u00a0])*(?:\.(?:[0-9]|[ \u00a0])+)?", text):
            raise SecFilingParseError("TRR4 dot-decimal lexical value is invalid")
        integer, dot, fraction = text.partition(".")
        if (not dot and not any("0" <= char <= "9" for char in integer)) or (dot and not any("0" <= char <= "9" for char in fraction)):
            raise SecFilingParseError("TRR4 dot-decimal lexical value is invalid")
        return re.sub(r"[, \u00a0]", "", integer) + ("." + re.sub(r"[ \u00a0]", "", fraction) if dot else "")
    if transform == "numeric_comma_decimal_relaxed":
        if not re.fullmatch(r"(?:[0-9]|[. \u00a0])*(?:,(?:[0-9]|[ \u00a0])+)?", text):
            raise SecFilingParseError("TRR4 comma-decimal lexical value is invalid")
        integer, comma, fraction = text.partition(",")
        if (not comma and not any("0" <= char <= "9" for char in integer)) or (comma and not any("0" <= char <= "9" for char in fraction)):
            raise SecFilingParseError("TRR4 comma-decimal lexical value is invalid")
        return re.sub(r"[. \u00a0]", "", integer) + ("." + re.sub(r"[ \u00a0]", "", fraction) if comma else "")
    raise SecFilingParseError("unknown numeric lexical algorithm")


def _apply_numeric(
    raw: str,
    *,
    format_qname: str | None,
    sign: str | None,
    scale: int | None,
    inline: bool = True,
) -> tuple[str | None, str | None, str]:
    if format_qname is None:
        kind = "identity_numeric"
    else:
        kind = SUPPORTED_TRANSFORMS.get(format_qname)
        if kind is None:
            return None, None, "unsupported_transform"
    try:
        if inline and sign not in {None, "-"}:
            raise SecFilingParseError("Inline XBRL sign must be '-' when present")
        if not inline and sign is not None:
            raise SecFilingParseError("native XBRL numeric value cannot carry an Inline sign")
        if kind == "empty":
            return None, None, "invalid_value"
        if kind == "zero":
            if format_qname and format_qname.startswith("{" + TRR3 + "}"):
                # TRR3 zerodash has a small, closed dash vocabulary.
                compact = raw.strip()
                if compact not in {"-", "\u058a", "\u05be", "‐", "‑", "‒", "–", "—", "―", "﹘", "﹣", "－"}:
                    raise SecFilingParseError("zerodash transform received an invalid dash")
            # TRR4 fixed-zero accepts any xs:string input by definition.
            transformed = "0"
        elif kind == "numeric_comma_decimal":
            transformed = _numeric_lexical(raw, transform="numeric_comma_decimal")
        elif kind == "numeric_dot_decimal":
            transformed = _numeric_lexical(raw, transform="numeric_dot_decimal")
        elif kind == "numeric_comma_decimal_relaxed":
            transformed = _numeric_lexical(raw, transform="numeric_comma_decimal_relaxed")
        elif kind == "numeric_dot_decimal_relaxed":
            transformed = _numeric_lexical(raw, transform="numeric_dot_decimal_relaxed")
        else:
            if not inline:
                transformed = raw.strip()
                if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", transformed):
                    raise SecFilingParseError("native numeric lexical value is invalid")
            else:
                transformed = _numeric_lexical(raw, transform="identity_numeric")
        with localcontext() as context:
            context.prec = max(128, len(transformed) + abs(scale or 0) + 16)
            number = Decimal(transformed)
            if scale:
                number *= Decimal(10) ** scale
            # Inline processing is transform -> scale -> sign, not the
            # arithmetically-equivalent-but-semantically-misleading reverse.
            if sign == "-":
                number = -number
        return transformed, _decimal_text(number), "available"
    except (InvalidOperation, ArithmeticError, SecFilingParseError):
        return None, None, "invalid_value"


def _direct_text(node: _Node, events: list[_TextEvent]) -> str:
    return "".join(event.value for event in events if event.owner is node)


def _require_no_elements(node: _Node, *, field_name: str) -> None:
    if node.children:
        raise SecFilingParseError(f"{field_name} must not contain child elements")


def _date_or_datetime(value: str, *, field_name: str) -> tuple[str, date | datetime]:
    text = _trim_text(value)
    try:
        if _DATE_RE.fullmatch(text):
            return text, date.fromisoformat(text)
        if _DATETIME_RE.fullmatch(text):
            parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return text, parsed
    except ValueError as exc:
        raise SecFilingParseError(f"{field_name} is not a valid XBRL date/dateTime") from exc
    raise SecFilingParseError(f"{field_name} is not a valid XBRL date/dateTime")


def _dimension_records(
    container: _Node | None,
    events: list[_TextEvent],
    limits: Mapping[str, int],
    content: bytes,
    *,
    field_name: str,
) -> tuple[list[dict[str, Any]], list[_Node]]:
    if container is None:
        return [], []
    if container.attrs or _direct_text(container, events).strip():
        raise SecFilingParseError(f"context {field_name} has unsupported attributes or direct text")
    dimensions: list[dict[str, Any]] = []
    opaque: list[_Node] = []
    seen: set[str] = set()
    for child in container.children:
        if child.namespace != XBRLDI or child.local not in {"explicitMember", "typedMember"}:
            # A nested apparent dimension is opaque extension content, not a
            # promoted context dimension.  Its partial status prevents a
            # false completeness claim while retaining the source witness.
            opaque.append(child)
            continue
        if set(child.attrs) != {"dimension"}:
            raise SecFilingParseError("dimension member has unsupported attributes")
        if len(dimensions) >= limits["max_dimensions_per_context"]:
            raise SecFilingParseError("context dimension limit exceeded")
        dimension_qname = _resolve_prefixed_qname(
            _attr(child, "dimension") or "", child.namespaces, field_name="dimension"
        )
        if dimension_qname in seen:
            raise SecFilingParseError("context repeats a dimension")
        seen.add(dimension_qname)
        text_events = _events_for(child, events, excluded=False)
        if child.local == "explicitMember":
            _require_no_elements(child, field_name="explicit dimension")
            dimensions.append(
                {
                    "kind": "explicit",
                    "dimension_qname": dimension_qname,
                    "member_qname": _resolve_prefixed_qname(
                        _trim_text(_text_value(child, events)), child.namespaces, field_name="explicit member"
                    ),
                    "typed_value_xml": None,
                    "text_spans": _event_spans(text_events),
                    "source_span": _span(child.start, int(child.end)),
                }
            )
        else:
            if len(child.children) != 1 or _direct_text(child, events).strip():
                raise SecFilingParseError("typed dimension must contain exactly one typed value element")
            value = child.children[0]
            dimensions.append(
                {
                    "kind": "typed",
                    "dimension_qname": dimension_qname,
                    "member_qname": None,
                    "typed_value_xml": content[value.start : int(value.end)].decode("utf-8", "strict"),
                    "text_spans": _event_spans(text_events),
                    "source_span": _span(child.start, int(child.end)),
                }
            )
    return dimensions, opaque


def _context_record(
    node: _Node,
    events: list[_TextEvent],
    limits: Mapping[str, int],
    content: bytes,
) -> dict[str, Any]:
    context_id = _normalized_identifier(_attr(node, "id"), field_name="context id")
    if set(node.attrs) != {"id"}:
        raise SecFilingParseError(f"context {context_id} has unsupported attributes")
    if _direct_text(node, events).strip():
        raise SecFilingParseError(f"context {context_id} has unsupported direct text")
    children = node.children
    if len(children) not in {2, 3} or [child.local for child in children[:2]] != ["entity", "period"] or any(
        child.namespace != XBRLI for child in children[:2]
    ) or (len(children) == 3 and (children[2].namespace != XBRLI or children[2].local != "scenario")):
        raise SecFilingParseError(f"context {context_id} must contain entity, period, and optional scenario in order")
    entity_node, period_node = children[:2]
    if entity_node.attrs or period_node.attrs:
        raise SecFilingParseError(f"context {context_id} entity/period has unsupported attributes")
    if _direct_text(entity_node, events).strip() or _direct_text(period_node, events).strip():
        raise SecFilingParseError(f"context {context_id} entity/period has unsupported direct text")
    scenario = children[2] if len(children) == 3 else None
    if len(entity_node.children) not in {1, 2} or entity_node.children[0].namespace != XBRLI or entity_node.children[0].local != "identifier" or (
        len(entity_node.children) == 2 and (entity_node.children[1].namespace != XBRLI or entity_node.children[1].local != "segment")
    ):
        raise SecFilingParseError(f"context {context_id} has an invalid entity shape")
    identifier_node = entity_node.children[0]
    _require_no_elements(identifier_node, field_name="entity identifier")
    identifier = _trim_text(_text_value(identifier_node, events))
    scheme = _attr(identifier_node, "scheme")
    if not identifier or scheme is None or not scheme or scheme != scheme.strip() or any(char.isspace() for char in scheme):
        raise SecFilingParseError(f"context {context_id} has an invalid entity identifier")
    if set(identifier_node.attrs) != {"scheme"}:
        raise SecFilingParseError("entity identifier has unsupported attributes")
    period_children = period_node.children
    if len(period_children) == 1 and period_children[0].namespace == XBRLI and period_children[0].local == "instant":
        instant = period_children[0]
        if instant.attrs:
            raise SecFilingParseError("context instant has unsupported attributes")
        _require_no_elements(instant, field_name="context instant")
        instant_text, _instant_value = _date_or_datetime(_text_value(instant, events), field_name="context instant")
        period = {"kind": "instant", "instant_date": instant_text, "start_date": None, "end_date": None, "source_span": _span(period_node.start, int(period_node.end))}
    elif len(period_children) == 1 and period_children[0].namespace == XBRLI and period_children[0].local == "forever":
        forever = period_children[0]
        if forever.attrs:
            raise SecFilingParseError("context forever has unsupported attributes")
        _require_no_elements(forever, field_name="context forever")
        if _text_value(forever, events).strip():
            raise SecFilingParseError("context forever must be empty")
        period = {"kind": "forever", "instant_date": None, "start_date": None, "end_date": None, "source_span": _span(period_node.start, int(period_node.end))}
    elif len(period_children) == 2 and all(child.namespace == XBRLI for child in period_children) and [child.local for child in period_children] == ["startDate", "endDate"]:
        start_node, end_node = period_children
        if start_node.attrs or end_node.attrs:
            raise SecFilingParseError("context duration dates have unsupported attributes")
        _require_no_elements(start_node, field_name="context startDate")
        _require_no_elements(end_node, field_name="context endDate")
        start_text, start_value = _date_or_datetime(_text_value(start_node, events), field_name="context startDate")
        end_text, end_value = _date_or_datetime(_text_value(end_node, events), field_name="context endDate")
        if type(start_value) is not type(end_value) or start_value >= end_value:
            raise SecFilingParseError("context duration startDate must precede endDate with matching type")
        period = {"kind": "duration", "instant_date": None, "start_date": start_text, "end_date": end_text, "source_span": _span(period_node.start, int(period_node.end))}
    else:
        raise SecFilingParseError(f"context {context_id} has an invalid direct period shape")
    segment = entity_node.children[1] if len(entity_node.children) == 2 else None
    segment_dimensions, unknown_segment = _dimension_records(segment, events, limits, content, field_name="segment")
    scenario_dimensions, unknown_scenario = _dimension_records(scenario, events, limits, content, field_name="scenario")
    dimensions = sorted(segment_dimensions + scenario_dimensions, key=lambda item: item["source_span"]["start"])
    names = [item["dimension_qname"] for item in dimensions]
    if len(names) != len(set(names)):
        raise SecFilingParseError(f"context {context_id} repeats a dimension across segment/scenario")
    return {
        "context_id": context_id,
        "entity": {"identifier": identifier, "scheme": scheme, "source_span": _span(identifier_node.start, int(identifier_node.end))},
        "period": period,
        "dimensions": dimensions,
        "segment_content_status": "partial" if unknown_segment else "complete",
        "unknown_segment_spans": [_span(item.start, int(item.end)) for item in unknown_segment],
        "scenario_content_status": "partial" if unknown_scenario else "complete",
        "unknown_scenario_spans": [_span(item.start, int(item.end)) for item in unknown_scenario],
        "source_span": _span(node.start, int(node.end)),
    }


def _unit_record(node: _Node, events: list[_TextEvent], limits: Mapping[str, int]) -> dict[str, Any]:
    unit_id = _normalized_identifier(_attr(node, "id"), field_name="unit id")
    if set(node.attrs) != {"id"}:
        raise SecFilingParseError(f"unit {unit_id} has unsupported attributes")
    if _direct_text(node, events).strip():
        raise SecFilingParseError(f"unit {unit_id} has unsupported direct text")

    def measures(container: _Node) -> list[str]:
        if not container.children or len(container.children) > limits["max_measures_per_unit"]:
            raise SecFilingParseError(f"unit {unit_id} has an invalid measure count")
        values: list[str] = []
        for measure in container.children:
            if measure.namespace != XBRLI or measure.local != "measure":
                raise SecFilingParseError(f"unit {unit_id} has a non-direct measure")
            _require_no_elements(measure, field_name="unit measure")
            if measure.attrs:
                raise SecFilingParseError("unit measure has unsupported attributes")
            values.append(_resolve_prefixed_qname(_trim_text(_text_value(measure, events)), measure.namespaces, field_name="unit measure"))
        return values

    if all(child.namespace == XBRLI and child.local == "measure" for child in node.children):
        numerator, denominator = measures(node), []
    elif len(node.children) == 1 and node.children[0].namespace == XBRLI and node.children[0].local == "divide":
        divide = node.children[0]
        if divide.attrs or len(divide.children) != 2 or [child.local for child in divide.children] != ["unitNumerator", "unitDenominator"] or any(child.namespace != XBRLI for child in divide.children):
            raise SecFilingParseError(f"unit {unit_id} has an invalid direct divide shape")
        if divide.children[0].attrs or divide.children[1].attrs:
            raise SecFilingParseError("unit divide wrappers have unsupported attributes")
        if _direct_text(divide, events).strip() or _direct_text(divide.children[0], events).strip() or _direct_text(divide.children[1], events).strip():
            raise SecFilingParseError("unit divide wrappers have unsupported direct text")
        numerator, denominator = measures(divide.children[0]), measures(divide.children[1])
    else:
        raise SecFilingParseError(f"unit {unit_id} has an invalid direct measure/divide shape")
    if set(numerator).intersection(denominator):
        raise SecFilingParseError(f"unit {unit_id} repeats a measure on both divide sides")
    return {"unit_id": unit_id, "numerator_measures": numerator, "denominator_measures": denominator, "source_span": _span(node.start, int(node.end))}


def _has_ancestor(node: _Node, namespace: str, local: str) -> bool:
    current: _Node | None = node
    while current is not None:
        if current.namespace == namespace and current.local == local:
            return True
        current = current.parent
    return False


def _continuation_records(
    nodes: list[_Node], events: list[_TextEvent], limits: Mapping[str, int]
) -> tuple[list[dict[str, Any]], dict[str, _Node]]:
    continuation_nodes = [
        node for node in nodes if node.namespace in IX_NAMESPACES and node.local == "continuation"
    ]
    if len(continuation_nodes) > limits["max_continuations"]:
        raise SecFilingParseError("continuation limit exceeded")
    by_id: dict[str, _Node] = {}
    records: list[dict[str, Any]] = []
    for node in continuation_nodes:
        continuation_id = _normalized_identifier(_attr(node, "id"), field_name="continuation id")
        if continuation_id in by_id:
            raise SecFilingParseError("duplicate continuation id")
        if set(node.attrs) - {"id", "continuedAt"}:
            raise SecFilingParseError("continuation has unsupported attributes")
        if _has_ancestor(node.parent, IX11, "hidden"):
            raise SecFilingParseError("continuation must not be hidden")
        by_id[continuation_id] = node
        included = _events_for(node, events, excluded=False)
        excluded = _events_for(node, events, excluded=True)
        continued_at = _attr(node, "continuedAt")
        if continued_at is not None:
            _normalized_identifier(continued_at, field_name="continuation continuedAt")
        records.append(
            {
                "continuation_id": continuation_id,
                "continued_at": continued_at,
                "raw_value": "".join(item.value for item in included),
                "text_spans": _event_spans(included),
                "excluded_text_spans": _event_spans(excluded),
                "hidden": False,
                "source_span": _span(node.start, int(node.end)),
            }
        )
    return records, by_id


def _continuation_chains(
    fact_nodes: list[_Node],
    records: list[dict[str, Any]],
    by_id: Mapping[str, _Node],
    limits: Mapping[str, int],
) -> dict[int, list[str]]:
    continued_at_by_id = {item["continuation_id"]: item["continued_at"] for item in records}
    incoming: dict[str, int] = {key: 0 for key in by_id}
    roots: list[tuple[int, str]] = []
    fact_by_start = {node.start: node for node in fact_nodes}
    for node in fact_nodes:
        target = _attr(node, "continuedAt")
        if target is not None:
            if node.local != "nonNumeric":
                raise SecFilingParseError("continuedAt is permitted only on ix:nonNumeric facts")
            _normalized_identifier(target, field_name="fact continuedAt")
            if target not in by_id:
                raise SecFilingParseError("fact references a missing continuation")
            roots.append((node.start, target))
            incoming[target] += 1
    for source, target in continued_at_by_id.items():
        if target is not None:
            if target not in by_id:
                raise SecFilingParseError(f"continuation {source} references a missing continuation")
            incoming[target] += 1
    # Detect cycles before reporting a shared owner: a self loop necessarily
    # has an incoming reference from its fact and from itself, but the cycle is
    # the more precise structural failure.  This is a single linear graph pass.
    state: dict[str, int] = {key: 0 for key in by_id}  # 0 unseen, 1 visiting, 2 done
    for start_id in by_id:
        if state[start_id] == 2:
            continue
        path: list[str] = []
        current: str | None = start_id
        while current is not None and state[current] == 0:
            state[current] = 1
            path.append(current)
            if len(path) > limits["max_continuation_chain"]:
                raise SecFilingParseError("continuation chain limit exceeded")
            current = continued_at_by_id[current]
        if current is not None and state[current] == 1:
            raise SecFilingParseError("continuation cycle detected")
        for continuation_id in path:
            state[continuation_id] = 2
    # Validate exclusivity before walking roots.  With at most one incoming
    # edge, successful root walks are disjoint and therefore linear.
    if any(count > 1 for count in incoming.values()):
        raise SecFilingParseError("continuation is shared by multiple owners")
    chains: dict[int, list[str]] = {}
    reached: set[str] = set()
    for fact_start, target in roots:
        chain: list[str] = []
        local_seen: set[str] = set()
        current: str | None = target
        while current is not None:
            if current in local_seen:
                raise SecFilingParseError("continuation cycle detected")
            if len(chain) >= limits["max_continuation_chain"]:
                raise SecFilingParseError("continuation chain limit exceeded")
            local_seen.add(current)
            reached.add(current)
            chain.append(current)
            current = continued_at_by_id[current]
        chain_nodes = [fact_by_start[fact_start], *[by_id[continuation_id] for continuation_id in chain]]
        for left_index, left in enumerate(chain_nodes):
            if any(
                _is_descendant(right, left) or _is_descendant(left, right)
                for right in chain_nodes[left_index + 1 :]
            ):
                raise SecFilingParseError("continuation chain elements must not be ancestor/descendant related")
        chains[fact_start] = chain
    # Any disconnected chain is an orphan; detect a cycle in it in linear
    # time rather than starting a new walk from every node.
    state = {key: 0 for key in by_id}  # 0 unseen, 1 visiting, 2 done
    for root_chain in chains.values():
        for continuation_id in root_chain:
            state[continuation_id] = 2
    for start_id in by_id:
        if state[start_id] == 2:
            continue
        path: list[str] = []
        current: str | None = start_id
        while current is not None and state[current] == 0:
            state[current] = 1
            path.append(current)
            if len(path) > limits["max_continuation_chain"]:
                raise SecFilingParseError("continuation chain limit exceeded")
            current = continued_at_by_id[current]
        if current is not None and state[current] == 1:
            raise SecFilingParseError("continuation cycle detected")
        for continuation_id in path:
            state[continuation_id] = 2
    if set(by_id) != reached:
        raise SecFilingParseError("orphan continuation is not owned by a fact")
    return chains


def _fact_nodes(nodes: list[_Node], document_kind: str) -> list[_Node]:
    if document_kind == "inline_xbrl":
        return [
            node
            for node in nodes
            if node.namespace in IX_NAMESPACES
            and node.local in {"nonFraction", "nonNumeric", "fraction"}
        ]
    if document_kind == "xbrl_instance":
        return [
            node
            for node in nodes
            if node.namespace not in {XBRLI, XBRLDI, LINK, XSI}
            and _attr(node, "contextRef") is not None
        ]
    return []


def _assert_allowed_attrs(node: _Node, allowed: set[str], *, field_name: str) -> None:
    unexpected = set(node.attrs) - allowed
    if unexpected:
        raise SecFilingParseError(f"{field_name} has unsupported attributes")


def _apply_nonnumeric(raw: str, *, format_qname: str | None) -> tuple[str | None, str | None, str]:
    if format_qname is None:
        return raw, raw, "available"
    kind = SUPPORTED_TRANSFORMS.get(format_qname)
    if kind is None:
        return None, None, "unsupported_transform"
    if kind == "empty":
        return "", "", "available"
    transformed, normalized, status = _apply_numeric(
        raw, format_qname=format_qname, sign=None, scale=None, inline=True
    )
    return transformed, normalized, status


def _fact_accuracy(
    node: _Node,
    *,
    numeric: bool,
    nil: bool,
    inline: bool,
    limits: Mapping[str, int],
) -> tuple[str | None, str | None, str | None, int | None, str | None]:
    decimals = _attr(node, "decimals")
    precision = _attr(node, "precision")
    _validate_accuracy_lexicals(decimals, precision)
    sign = _attr(node, "sign")
    scale = _optional_integer(_attr(node, "scale"), field_name="fact scale", absolute_maximum=limits["max_abs_scale"])
    lexical_format = _attr(node, "format")
    format_qname = _resolve_prefixed_qname(lexical_format, node.namespaces, field_name="fact format") if lexical_format is not None else None
    if not numeric:
        if any(value is not None for value in (decimals, precision, sign, scale)):
            raise SecFilingParseError("non-numeric fact carries numeric attributes")
    elif not nil and (decimals is None and precision is None):
        raise SecFilingParseError("numeric fact must carry decimals or precision unless nil")
    if nil and any(value is not None for value in (decimals, precision, sign, scale, format_qname)):
        raise SecFilingParseError("nil fact cannot carry accuracy, transform, sign, or scale")
    if not inline and any(value is not None for value in (sign, scale, format_qname)):
        raise SecFilingParseError("native XBRL fact cannot carry Inline XBRL attributes")
    if inline and sign not in {None, "-"}:
        raise SecFilingParseError("Inline XBRL sign must be '-' when present")
    return decimals, precision, sign, scale, format_qname


def _fact_record(
    node: _Node,
    events: list[_TextEvent],
    continuation_chain: list[str],
    continuation_records: Mapping[str, Mapping[str, Any]],
    context_ids: set[str],
    unit_ids: set[str],
    limits: Mapping[str, int],
    *,
    inline: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    fact_id = _attr(node, "id")
    if fact_id is not None:
        _normalized_identifier(fact_id, field_name="fact id")
    if inline:
        lexical_name = _attr(node, "name")
        if lexical_name is None:
            raise SecFilingParseError("Inline XBRL fact is missing name QName")
        concept_qname = _resolve_prefixed_qname(lexical_name, node.namespaces, field_name="fact name")
        kind = {"nonFraction": "numeric", "nonNumeric": "nonnumeric", "fraction": "fraction"}[node.local]
    else:
        concept_qname = node.qname
        if not concept_qname.startswith("{"):
            raise SecFilingParseError("instance fact concept must resolve to a namespace")
        kind = "numeric" if _attr(node, "unitRef") is not None else "nonnumeric"
    context_ref = _attr(node, "contextRef")
    if context_ref is not None:
        _normalized_identifier(context_ref, field_name="fact contextRef")
    if context_ref is None or context_ref not in context_ids:
        raise SecFilingParseError("fact references a missing context")
    unit_ref = _attr(node, "unitRef")
    if unit_ref is not None:
        _normalized_identifier(unit_ref, field_name="fact unitRef")
    if kind in {"numeric", "fraction"}:
        if unit_ref is None or unit_ref not in unit_ids:
            raise SecFilingParseError("numeric fact references a missing unit")
    elif unit_ref is not None:
        raise SecFilingParseError("non-numeric fact cannot carry unitRef")

    nil = _parse_bool(_attr(node, "nil", XSI), field_name="xsi:nil")
    numeric = kind == "numeric"
    if inline:
        common = {"id", "name", "contextRef", f"{{{XSI}}}nil", f"{{{XML}}}lang"}
        if kind == "numeric":
            _assert_allowed_attrs(node, common | {"unitRef", "decimals", "precision", "format", "sign", "scale"}, field_name="ix:nonFraction")
        elif kind == "nonnumeric":
            _assert_allowed_attrs(node, common | {"format", "continuedAt"}, field_name="ix:nonNumeric")
        else:
            _assert_allowed_attrs(node, common | {"unitRef"}, field_name="ix:fraction")
    else:
        _assert_allowed_attrs(node, {"id", "contextRef", "unitRef", "decimals", "precision", f"{{{XSI}}}nil", f"{{{XML}}}lang"}, field_name="native XBRL fact")
    decimals, precision, sign, scale, format_qname = _fact_accuracy(
        node, numeric=numeric, nil=nil, inline=inline, limits=limits
    )
    if kind == "fraction" and any(value is not None for value in (decimals, precision, sign, scale, format_qname)):
        raise SecFilingParseError("ix:fraction cannot carry fact-level numeric transformation attributes")
    continued_at = _attr(node, "continuedAt")
    if continued_at is not None and (not inline or kind != "nonnumeric"):
        raise SecFilingParseError("continuedAt is permitted only on ix:nonNumeric facts")
    local_events = _events_for(node, events, excluded=False)
    excluded_events = _events_for(node, events, excluded=True)
    all_events = list(local_events)
    raw_parts = ["".join(event.value for event in local_events)]
    for continuation_id in continuation_chain:
        continuation = continuation_records[continuation_id]
        raw_parts.append(str(continuation["raw_value"]))
        all_events.extend(
            _TextEvent(span["start"], "", (), None, span["end"])
            for span in continuation["text_spans"]
        )
        excluded_events.extend(
            _TextEvent(span["start"], "", (), None, span["end"])
            for span in continuation["excluded_text_spans"]
        )
    # A continuation chain is a logical value sequence, not source order.
    # The continuation may precede the owning fact in the XHTML member, so
    # keep both included and excluded source witnesses in the same logical
    # order used to construct raw_value: fact-local material, then each link.
    raw = _node_text_bytes("".join(raw_parts), limits, field_name="fact")
    fraction: dict[str, Any] | None = None
    diagnostic: dict[str, Any] | None = None
    if nil:
        if raw or excluded_events or node.children:
            raise SecFilingParseError("nil fact must not contain content")
        transformed = None
        normalized = None
        status = "nil"
    elif kind == "nonnumeric":
        transformed, normalized, status = _apply_nonnumeric(raw, format_qname=format_qname)
    elif kind == "fraction":
        if continuation_chain:
            raise SecFilingParseError("ix:fraction cannot carry a continuation")
        if len(node.children) != 2 or [child.local for child in node.children] != ["numerator", "denominator"] or any(child.namespace != IX11 for child in node.children):
            raise SecFilingParseError("fraction must contain exactly one direct numerator and denominator")
        numerator_node, denominator_node = node.children
        for component in (numerator_node, denominator_node):
            # Component-level transforms are deliberately rejected, rather
            # than being normalized without enough retained provenance to
            # replay their individual algorithm inputs in this v1 wire.
            if component.attrs or component.children:
                raise SecFilingParseError("fraction component transforms and nested content are unsupported in this profile")
        numerator_raw = _node_text_bytes(_text_value(numerator_node, events), limits, field_name="fraction numerator")
        denominator_raw = _node_text_bytes(_text_value(denominator_node, events), limits, field_name="fraction denominator")
        numerator_transformed, numerator_normalized, n_status = _apply_numeric(
            numerator_raw, format_qname=None, sign=None, scale=None, inline=True
        )
        denominator_transformed, denominator_normalized, d_status = _apply_numeric(
            denominator_raw, format_qname=None, sign=None, scale=None, inline=True
        )
        status = "available" if n_status == d_status == "available" else "invalid_value"
        transformed = f"{numerator_raw}/{denominator_raw}" if status == "available" else None
        normalized = None
        fraction = {
            "numerator_raw": numerator_raw,
            "denominator_raw": denominator_raw,
            "numerator_normalized": numerator_normalized,
            "denominator_normalized": denominator_normalized,
        }
    else:
        transformed, normalized, status = _apply_numeric(
            raw, format_qname=format_qname, sign=sign, scale=scale, inline=inline
        )
    if status in {"unsupported_transform", "invalid_value"}:
        diagnostic = {
            "code": status,
            "fact_start": node.start,
            "format": format_qname,
        }
    return (
        {
            "fact_id": fact_id,
            "concept_qname": concept_qname,
            "kind": kind,
            "context_ref": context_ref,
            "unit_ref": unit_ref,
            "continuation_chain": continuation_chain,
            "raw_value": raw,
            "transformed_value": transformed,
            "normalized_value": normalized,
            "status": status,
            "nil": nil,
            "lang": _attr(node, "lang", XML),
            "decimals": decimals,
            "precision": precision,
            "format": format_qname,
            "sign": sign,
            "scale": scale,
            "hidden": inline and _has_ancestor(node.parent, IX11, "hidden"),
            "fraction": fraction,
            "text_spans": _event_spans(all_events),
            "excluded_text_spans": _event_spans(excluded_events),
            "source_span": _span(node.start, int(node.end)),
        },
        diagnostic,
    )


def _parser_metadata() -> dict[str, Any]:
    registry = [
        {"qname": qname, "kind": SUPPORTED_TRANSFORMS[qname]}
        for qname in sorted(SUPPORTED_TRANSFORMS)
    ]
    return {
        "profile": SEC_FILING_PARSER_PROFILE,
        "version": SEC_FILING_PARSER_VERSION,
        "algorithm_fingerprint": SEC_FILING_PARSER_ALGORITHM_FINGERPRINT,
        "library": "stdlib.xml.parsers.expat",
        "library_version": f"python-{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "xml_library_version": expat.EXPAT_VERSION,
        "transform_registry": registry,
    }


def _validate_parser_metadata(value: Any) -> None:
    metadata = _exact_dict(
        value,
        {"profile", "version", "algorithm_fingerprint", "library", "library_version", "xml_library_version", "transform_registry"},
        field_name="parser metadata",
    )
    if (
        metadata["profile"] != SEC_FILING_PARSER_PROFILE
        or metadata["version"] != SEC_FILING_PARSER_VERSION
        or metadata["algorithm_fingerprint"] != SEC_FILING_PARSER_ALGORITHM_FINGERPRINT
    ):
        raise SecFilingParseError("parser stable compatibility authority is not canonical")
    if not re.fullmatch(r"[a-f0-9]{64}", metadata["algorithm_fingerprint"]):
        raise SecFilingParseError("parser algorithm fingerprint is malformed")
    for field_name in ("library", "library_version", "xml_library_version"):
        _text(metadata[field_name], field_name=f"parser.{field_name}")
    expected_registry = [
        {"qname": qname, "kind": SUPPORTED_TRANSFORMS[qname]}
        for qname in sorted(SUPPORTED_TRANSFORMS)
    ]
    if metadata["transform_registry"] != expected_registry:
        raise SecFilingParseError("parser transform registry is not canonical")


def _semantic_result_bytes(value: Mapping[str, Any]) -> bytes:
    """Compare replay semantics while allowing observed runtime patch drift."""
    copy = json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    parser = copy["parser"]
    parser.pop("library", None)
    parser.pop("library_version", None)
    parser.pop("xml_library_version", None)
    return json.dumps(copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _limits_snapshot() -> dict[str, int]:
    expected = {
        "max_bytes",
        "max_nodes",
        "max_depth",
        "max_attributes_per_element",
        "max_total_attributes",
        "max_attribute_bytes",
        "max_total_attribute_bytes",
        "max_name_bytes",
        "max_namespaces_per_element",
        "max_in_scope_namespaces",
        "max_total_namespace_bytes",
        "max_text_bytes",
        "max_text_events",
        "max_fact_text_bytes",
        "max_contexts",
        "max_units",
        "max_facts",
        "max_continuations",
        "max_continuation_chain",
        "max_dimensions_per_context",
        "max_measures_per_unit",
        "max_abs_scale",
        "max_output_bytes",
        "max_metadata_bytes",
    }
    if set(PARSER_LIMITS) != expected:
        raise SecFilingParseError("parser limits contract is invalid")
    result: dict[str, int] = {}
    for key in sorted(expected):
        value = PARSER_LIMITS[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise SecFilingParseError(f"parser limit {key} is invalid")
        result[key] = min(value, _HARD_LIMITS[key])
    return result


def _inline_ancestor(node: _Node | None, local: str) -> bool:
    return _has_ancestor(node, IX11, local) if node is not None else False


def _nearest_inline_owner(node: _Node | None) -> _Node | None:
    """Return the nearest Inline XBRL semantic ancestor, if one exists."""
    while node is not None:
        if node.namespace == IX11:
            return node
        node = node.parent
    return None


def _validate_inline_ids(nodes: list[_Node]) -> None:
    """Apply the one-document Inline XBRL id namespace before graph linking."""
    id_bearing = {"continuation", "fraction", "nonFraction", "nonNumeric", "references"}
    seen: set[str] = set()
    for node in nodes:
        identifier = _attr(node, "id")
        if identifier is None:
            continue
        if node.namespace == IX11 and node.local not in id_bearing:
            raise SecFilingParseError(f"ix:{node.local} cannot carry an id in this parser profile")
        identifier = _normalized_identifier(identifier, field_name="Inline XBRL document id")
        if identifier in seen:
            raise SecFilingParseError("duplicate Inline XBRL id")
        seen.add(identifier)


def _validate_document_structure(
    root: _Node, nodes: list[_Node], events: list[_TextEvent], document_kind: str
) -> tuple[list[_Node], list[_Node], list[_Node]]:
    """Return admitted resources/facts after direct-grammar placement checks."""
    if document_kind == "other_xml":
        return [], [], []
    if document_kind == "xbrl_instance":
        contexts = [node for node in root.children if node.namespace == XBRLI and node.local == "context"]
        units = [node for node in root.children if node.namespace == XBRLI and node.local == "unit"]
        if any(node.namespace == XBRLI and node.local in {"context", "unit"} and node.parent is not root for node in nodes):
            raise SecFilingParseError("native XBRL context/unit must be direct xbrl children")
        candidates = _fact_nodes(nodes, document_kind)
        if any(node.parent is not root for node in candidates):
            raise SecFilingParseError("native XBRL fact candidate must be a direct xbrl child")
        return contexts, units, candidates

    if root.namespace != XHTML or root.local != "html":
        raise SecFilingParseError("Inline XBRL 1.1 root must be XHTML html")
    supported_ix = {"header", "resources", "references", "hidden", "nonFraction", "nonNumeric", "fraction", "numerator", "denominator", "exclude", "continuation"}
    for node in nodes:
        if node.namespace == IX11 and node.local not in supported_ix:
            raise SecFilingParseError(f"unsupported Inline XBRL semantic structure: ix:{node.local}")
    headers = [node for node in nodes if node.namespace == IX11 and node.local == "header"]
    if len(headers) != 1:
        raise SecFilingParseError("Inline XBRL 1.1 document must contain exactly one ix:header")
    header = headers[0]
    # iXBRL explicitly prohibits a header below XHTML head.  This single-file
    # profile additionally requires an XHTML body ancestor, but permits the
    # ordinary non-displaying wrapper used by real filings.
    if not _has_ancestor(header.parent, XHTML, "body"):
        raise SecFilingParseError("ix:header must be a descendant of XHTML body, not XHTML head")
    if any(ancestor.namespace == IX11 for ancestor in _ancestor_nodes(header.parent)):
        raise SecFilingParseError("ix:header must not be nested beneath Inline XBRL semantic content")
    _validate_inline_ids(nodes)
    resources = [node for node in nodes if node.namespace == IX11 and node.local == "resources"]
    if len(resources) != 1 or resources[0].parent is not header:
        raise SecFilingParseError("ix:resources must be the direct child of the ix:header")
    resource = resources[0]
    hidden_nodes = [node for node in nodes if node.namespace == IX11 and node.local == "hidden"]
    if len(hidden_nodes) > 1:
        raise SecFilingParseError("ix:header may contain at most one ix:hidden")
    # iXBRL 1.1 Table 9: (ix:hidden? ix:references* ix:resources?).  Exact
    # direct-child ordering is important: descendant scans otherwise make a
    # malformed header appear to expose canonical resources.
    stage = 0  # 0 hidden still allowed; 1 references; 2 resources complete.
    for child in header.children:
        if child.namespace != IX11:
            raise SecFilingParseError("ix:header has an unsupported direct child")
        if child.local == "hidden":
            if stage != 0:
                raise SecFilingParseError("ix:header direct children are out of required order")
            stage = 1
        elif child.local == "references":
            if stage == 2:
                raise SecFilingParseError("ix:header direct children are out of required order")
            stage = 1
        elif child.local == "resources":
            if stage == 2:
                raise SecFilingParseError("ix:header may contain at most one ix:resources")
            stage = 2
        else:
            raise SecFilingParseError("ix:header has an unsupported direct child")
    if _direct_text(header, events).strip():
        raise SecFilingParseError("ix:header cannot contain direct non-whitespace text")
    for references in (node for node in nodes if node.namespace == IX11 and node.local == "references"):
        if references.parent is not header:
            raise SecFilingParseError("ix:references must be a direct ix:header child")
    for hidden in hidden_nodes:
        if hidden.parent is not header:
            raise SecFilingParseError("ix:hidden must be a direct ix:header child")
        if not hidden.children or _direct_text(hidden, events).strip() or any(
            child.namespace != IX11 or child.local not in {"nonFraction", "nonNumeric", "fraction"}
            for child in hidden.children
        ):
            raise SecFilingParseError("ix:hidden must contain only direct Inline XBRL facts")
    if _direct_text(resource, events).strip() or any(
        child.namespace != XBRLI or child.local not in {"context", "unit"}
        for child in resource.children
    ):
        raise SecFilingParseError("ix:resources has unsupported direct content in this parser profile")
    contexts = [node for node in resource.children if node.namespace == XBRLI and node.local == "context"]
    units = [node for node in resource.children if node.namespace == XBRLI and node.local == "unit"]
    for node in nodes:
        if node.namespace == XBRLI and node.local in {"context", "unit"} and node.parent is not resource:
            raise SecFilingParseError("Inline XBRL context/unit must be direct ix:resources children")
    for node in nodes:
        if node.namespace == IX11 and node.local == "exclude":
            owner = _nearest_inline_owner(node.parent)
            if owner is None or owner.local not in {"continuation", "nonNumeric"}:
                raise SecFilingParseError("ix:exclude must be owned by ix:nonNumeric or ix:continuation")
    candidates = _fact_nodes(nodes, document_kind)
    for fact in candidates:
        if fact.local == "nonFraction" and fact.children:
            raise SecFilingParseError("ix:nonFraction child elements are unsupported in this parser profile")
        if fact.local in {"nonFraction", "fraction"} and any(
            descendant.namespace == IX11 and descendant.local in {"nonFraction", "fraction"}
            for descendant in _descendants(fact)
        ):
            raise SecFilingParseError("nested Inline XBRL numeric facts are unsupported in this parser profile")
    for fact in candidates:
        if _inline_ancestor(fact.parent, "resources"):
            raise SecFilingParseError("Inline XBRL fact cannot appear in ix:resources")
        if _inline_ancestor(fact.parent, "header") and not _inline_ancestor(fact.parent, "hidden"):
            raise SecFilingParseError("Inline XBRL fact in ix:header must be inside ix:hidden")
    for continuation in (node for node in nodes if node.namespace == IX11 and node.local == "continuation"):
        if _inline_ancestor(continuation.parent, "header"):
            raise SecFilingParseError("ix:continuation must not appear in ix:header")
    return contexts, units, candidates


def _ancestor_nodes(node: _Node | None) -> list[_Node]:
    result: list[_Node] = []
    while node is not None:
        result.append(node)
        node = node.parent
    return result


def parse_sec_filing_document(content: bytes, *, document_name: str) -> dict[str, Any]:
    """Parse one exact retained filing member without any external I/O."""
    limits = _limits_snapshot()
    name = _safe_document_name(document_name)
    if type(content) is not bytes:
        raise SecFilingParseError("content must be exact bytes")
    if not content or len(content) > limits["max_bytes"]:
        raise SecFilingParseError("content is empty or exceeds the byte limit")
    if b"\x00" in content:
        raise SecFilingParseError("NUL bytes are forbidden")
    try:
        content.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise SecFilingParseError("content is not strict UTF-8") from exc
    if _FORBIDDEN_DECL_RE.search(content):
        raise SecFilingParseError("DTD and entity declarations are forbidden")
    declaration = _XML_DECL_RE.match(content)
    if declaration is not None:
        encoding = _ENCODING_RE.search(declaration.group(1))
        if encoding is not None and encoding.group(2).lower() not in {b"utf-8", b"utf8"}:
            raise SecFilingParseError("XML declaration is not UTF-8")

    root, nodes, events = _TreeBuilder(content, limits).build()
    if any(
        node.namespace in LEGACY_IX_NAMESPACES or IX10 in node.namespaces.values()
        for node in nodes
    ):
        raise SecFilingParseError("legacy or mixed Inline XBRL namespace is not admitted by the 1.1 profile")
    inline_namespaces = sorted({node.namespace for node in nodes if node.namespace in IX_NAMESPACES})
    if inline_namespaces:
        document_kind = "inline_xbrl"
    elif root.namespace == XBRLI and root.local == "xbrl":
        document_kind = "xbrl_instance"
    else:
        document_kind = "other_xml"

    context_nodes, unit_nodes, facts_nodes = _validate_document_structure(root, nodes, events, document_kind)
    if len(context_nodes) > limits["max_contexts"]:
        raise SecFilingParseError("context limit exceeded")
    if len(unit_nodes) > limits["max_units"]:
        raise SecFilingParseError("unit limit exceeded")
    contexts = [_context_record(node, events, limits, content) for node in context_nodes]
    units = [_unit_record(node, events, limits) for node in unit_nodes]
    context_ids = [record["context_id"] for record in contexts]
    unit_ids = [record["unit_id"] for record in units]
    if len(set(context_ids)) != len(context_ids):
        raise SecFilingParseError("duplicate context id")
    if len(set(unit_ids)) != len(unit_ids):
        raise SecFilingParseError("duplicate unit id")

    continuations, continuation_nodes = (
        _continuation_records(nodes, events, limits) if document_kind == "inline_xbrl" else ([], {})
    )
    if len(facts_nodes) > limits["max_facts"]:
        raise SecFilingParseError("fact limit exceeded")
    chains = _continuation_chains(facts_nodes, continuations, continuation_nodes, limits)
    continuation_by_id = {item["continuation_id"]: item for item in continuations}
    facts: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for node in facts_nodes:
        fact, diagnostic = _fact_record(
            node,
            events,
            chains.get(node.start, []),
            continuation_by_id,
            set(context_ids),
            set(unit_ids),
            limits,
            inline=document_kind == "inline_xbrl",
        )
        facts.append(fact)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    for context in contexts:
        if context["segment_content_status"] == "partial":
            diagnostics.append(
                {
                    "code": "unknown_segment_content",
                    "context_id": context["context_id"],
                    "source_spans": context["unknown_segment_spans"],
                }
            )
        if context["scenario_content_status"] == "partial":
            diagnostics.append(
                {
                    "code": "unknown_scenario_content",
                    "context_id": context["context_id"],
                    "source_spans": context["unknown_scenario_spans"],
                }
            )
    diagnostics.sort(
        key=lambda item: (
            item.get("fact_start", item.get("source_spans", [{"start": 0}])[0]["start"]),
            item["code"],
        )
    )
    admitted_inventory = document_kind == "inline_xbrl"
    coverage = {
        "document_scope": "single_member",
        "fact_inventory_complete": admitted_inventory,
        "context_references_complete": document_kind != "other_xml",
        "unit_references_complete": document_kind != "other_xml",
        "continuation_graph_complete": document_kind == "inline_xbrl",
        "canonical_value_complete": admitted_inventory and all(
            fact["status"] not in {"unsupported_transform", "invalid_value"} for fact in facts
        ),
        "context_count": len(contexts),
        "unit_count": len(units),
        "continuation_count": len(continuations),
        "fact_count": len(facts),
        "diagnostic_count": len(diagnostics),
        "unknown_scenario_content_count": sum(
            context["scenario_content_status"] == "partial" for context in contexts
        ),
        "unknown_segment_content_count": sum(
            context["segment_content_status"] == "partial" for context in contexts
        ),
        "structural_validation_complete": document_kind != "other_xml",
        "ixds_validation_complete": False,
        "xbrl_schema_validation_complete": False,
        "taxonomy_validation_complete": False,
    }
    result = {
        "schema": SEC_FILING_PARSER_SCHEMA,
        "parser": _parser_metadata(),
        "source": {
            "document_name": name,
            "content_sha256": sha256(content).hexdigest(),
            "byte_length": len(content),
        },
        "document": {
            "kind": document_kind,
            "root_qname": root.qname,
            "root_lexical_name": root.lexical_name,
            "inline_namespaces": inline_namespaces,
            "inline_version": "1.1" if document_kind == "inline_xbrl" else None,
            "source_span": _span(root.start, int(root.end)),
        },
        "contexts": contexts,
        "units": units,
        "continuations": continuations,
        "facts": facts,
        "diagnostics": diagnostics,
        "coverage": coverage,
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > limits["max_output_bytes"]:
        raise SecFilingParseError("parser output byte limit exceeded")
    # Exercise the independent shape/derivation validator before releasing the
    # result.  Replay is intentionally omitted here to avoid parsing twice.
    return validate_sec_filing_parse_result(result)


def _exact_dict(value: Any, fields: set[str] | frozenset[str], *, field_name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(fields):
        raise SecFilingParseError(f"{field_name} has an invalid shape")
    return value


def _exact_list(value: Any, *, field_name: str, maximum: int) -> list[Any]:
    if type(value) is not list or len(value) > maximum:
        raise SecFilingParseError(f"{field_name} must be a bounded array")
    return value


def _text(value: Any, *, field_name: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or value != value.strip() or not value:
        raise SecFilingParseError(f"{field_name} must be normalized text")
    try:
        if len(value.encode("utf-8", "strict")) > _HARD_LIMITS["max_text_bytes"]:
            raise SecFilingParseError(f"{field_name} exceeds the text limit")
    except UnicodeError as exc:
        raise SecFilingParseError(f"{field_name} is not valid UTF-8") from exc
    return value


def _nullable_string(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SecFilingParseError(f"{field_name} must be text or null")
    try:
        if len(value.encode("utf-8", "strict")) > _HARD_LIMITS["max_text_bytes"]:
            raise SecFilingParseError(f"{field_name} exceeds the text limit")
    except UnicodeError as exc:
        raise SecFilingParseError(f"{field_name} is not valid UTF-8") from exc
    return value


def _clark_qname(value: Any, *, field_name: str, ascii_local: bool = True) -> str:
    """Require the exact Clark notation emitted by the parser."""
    text = _text(value, field_name=field_name)
    assert text is not None
    if not text.startswith("{") or "}" not in text:
        raise SecFilingParseError(f"{field_name} is not a Clark QName")
    uri, local = text[1:].split("}", 1)
    if (
        not uri
        or not local
        or any(char in "{}" for char in uri + local)
        or any(char.isspace() for char in local)
        or (ascii_local and not _NCNAME_RE.fullmatch(local))
    ):
        raise SecFilingParseError(f"{field_name} is not a Clark QName")
    return text


def _validated_span(value: Any, *, field_name: str, length: int) -> dict[str, int]:
    item = _exact_dict(value, {"start", "end"}, field_name=field_name)
    start, end = item["start"], item["end"]
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or not (0 <= start < end <= length)
    ):
        raise SecFilingParseError(f"{field_name} is outside source bytes")
    return item


def _span_list(value: Any, *, field_name: str, length: int) -> list[dict[str, int]]:
    items = _exact_list(value, field_name=field_name, maximum=_HARD_LIMITS["max_nodes"])
    prior = -1
    for index, item in enumerate(items):
        span = _validated_span(item, field_name=f"{field_name}[{index}]", length=length)
        if span["start"] <= prior:
            raise SecFilingParseError(f"{field_name} is not strictly source ordered")
        prior = span["start"]
    return items


def _logical_fact_span_list(
    value: Any,
    *,
    field_name: str,
    length: int,
    owners: list[Mapping[str, int]],
) -> list[dict[str, int]]:
    """Validate fact witnesses in value/continuation-chain logical order."""
    items = _exact_list(value, field_name=field_name, maximum=_HARD_LIMITS["max_nodes"])
    prior_owner = -1
    prior_start = -1
    for index, item in enumerate(items):
        span = _validated_span(item, field_name=f"{field_name}[{index}]", length=length)
        matching_owners = [
            owner_index
            for owner_index, owner in enumerate(owners)
            if span["start"] >= owner["start"] and span["end"] <= owner["end"]
        ]
        if len(matching_owners) != 1:
            raise SecFilingParseError(f"{field_name} is outside or ambiguous across logical owners")
        owner_index = matching_owners[0]
        if owner_index < prior_owner or (owner_index == prior_owner and span["start"] <= prior_start):
            raise SecFilingParseError(f"{field_name} is not in logical fact/continuation order")
        prior_owner, prior_start = owner_index, span["start"]
    return items


def _require_disjoint_spans(*span_lists: list[dict[str, int]], field_name: str) -> None:
    intervals = sorted(
        (span["start"], span["end"])
        for spans in span_lists
        for span in spans
    )
    prior_end = -1
    for start, end in intervals:
        if start < prior_end:
            raise SecFilingParseError(f"{field_name} overlap")
        prior_end = end


def _source_ordered(items: list[Any], *, field_name: str, length: int) -> None:
    prior = -1
    for index, value in enumerate(items):
        if type(value) is not dict or "source_span" not in value:
            raise SecFilingParseError(f"{field_name}[{index}] is missing source_span")
        span = _validated_span(value["source_span"], field_name=f"{field_name}[{index}].source_span", length=length)
        if span["start"] <= prior:
            raise SecFilingParseError(f"{field_name} must be strictly source ordered")
        prior = span["start"]


def _require_contained(inner: Mapping[str, int], outer: Mapping[str, int], *, field_name: str) -> None:
    if inner["start"] < outer["start"] or inner["end"] > outer["end"]:
        raise SecFilingParseError(f"{field_name} is outside its owning source span")


def _json_guard(value: Any, *, field_name: str, budget: list[int], depth: int = 0) -> None:
    budget[0] -= 1
    if budget[0] < 0 or depth > _HARD_LIMITS["max_depth"]:
        raise SecFilingParseError(f"{field_name} exceeds JSON safety limits")
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            _nullable_string(value, field_name=field_name)
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if value < -(1 << 63) or value > (1 << 63) - 1:
            raise SecFilingParseError(f"{field_name} integer is outside signed-64-bit range")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _json_guard(item, field_name=f"{field_name}[{index}]", budget=budget, depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                raise SecFilingParseError(f"{field_name} has a non-text key")
            _json_guard(item, field_name=f"{field_name}.{key}", budget=budget, depth=depth + 1)
        return
    raise SecFilingParseError(f"{field_name} contains a non-JSON value")


def validate_sec_filing_parse_result(
    value: Any, *, source_content: bytes | None = None
) -> dict[str, Any]:
    """Validate the fixed parser wire contract and optionally replay its bytes."""
    limits = _limits_snapshot()
    _json_guard(value, field_name="parse result", budget=[limits["max_nodes"] * 8])
    result = _exact_dict(value, _TOP_FIELDS, field_name="parse result")
    if result["schema"] != SEC_FILING_PARSER_SCHEMA:
        raise SecFilingParseError("unsupported parser result schema")
    _validate_parser_metadata(result["parser"])
    source = _exact_dict(
        result["source"], {"document_name", "content_sha256", "byte_length"}, field_name="source"
    )
    name = _safe_document_name(source["document_name"])
    digest = source["content_sha256"]
    length = source["byte_length"]
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise SecFilingParseError("source content_sha256 is invalid")
    if isinstance(length, bool) or not isinstance(length, int) or not (1 <= length <= limits["max_bytes"]):
        raise SecFilingParseError("source byte_length is invalid")

    document = _exact_dict(
        result["document"],
        {"kind", "root_qname", "root_lexical_name", "inline_namespaces", "inline_version", "source_span"},
        field_name="document",
    )
    if document["kind"] not in {"inline_xbrl", "xbrl_instance", "other_xml"}:
        raise SecFilingParseError("document kind is invalid")
    if document["kind"] in {"inline_xbrl", "xbrl_instance"}:
        _clark_qname(document["root_qname"], field_name="document.root_qname", ascii_local=False)
    else:
        _text(document["root_qname"], field_name="document.root_qname")
    _text(document["root_lexical_name"], field_name="document.root_lexical_name")
    inline_namespaces = _exact_list(
        document["inline_namespaces"], field_name="document.inline_namespaces", maximum=1
    )
    if inline_namespaces != [IX11] and inline_namespaces != []:
        raise SecFilingParseError("document inline_namespaces is not canonical")
    if (document["kind"] == "inline_xbrl") != bool(inline_namespaces):
        raise SecFilingParseError("document kind does not match Inline XBRL namespaces")
    if document["inline_version"] != ("1.1" if document["kind"] == "inline_xbrl" else None):
        raise SecFilingParseError("document inline version is not derived")
    expected_root_qname = {
        "inline_xbrl": f"{{{XHTML}}}html",
        "xbrl_instance": f"{{{XBRLI}}}xbrl",
    }.get(document["kind"])
    if expected_root_qname is not None and document["root_qname"] != expected_root_qname:
        raise SecFilingParseError("document root QName does not match its admitted kind")
    root_span = _validated_span(document["source_span"], field_name="document.source_span", length=length)

    contexts = _exact_list(result["contexts"], field_name="contexts", maximum=limits["max_contexts"])
    units = _exact_list(result["units"], field_name="units", maximum=limits["max_units"])
    continuations = _exact_list(
        result["continuations"], field_name="continuations", maximum=limits["max_continuations"]
    )
    facts = _exact_list(result["facts"], field_name="facts", maximum=limits["max_facts"])
    diagnostics = _exact_list(
        result["diagnostics"], field_name="diagnostics", maximum=limits["max_facts"] + (2 * limits["max_contexts"])
    )
    for label, items in (("contexts", contexts), ("units", units), ("continuations", continuations), ("facts", facts)):
        _source_ordered(items, field_name=label, length=length)
        for index, item in enumerate(items):
            _require_contained(item["source_span"], root_span, field_name=f"{label}[{index}].source_span")

    context_ids: set[str] = set()
    document_ids: set[str] = set()
    expected_context_diagnostics: list[dict[str, Any]] = []
    for index, raw in enumerate(contexts):
        item = _exact_dict(
            raw,
            {"context_id", "entity", "period", "dimensions", "segment_content_status", "unknown_segment_spans", "scenario_content_status", "unknown_scenario_spans", "source_span"},
            field_name=f"contexts[{index}]",
        )
        context_text = _text(item["context_id"], field_name=f"contexts[{index}].context_id")
        assert context_text is not None
        context_id = _normalized_identifier(context_text, field_name=f"contexts[{index}].context_id")
        if context_id in context_ids:
            raise SecFilingParseError("duplicate context id")
        if context_id in document_ids:
            raise SecFilingParseError("duplicate document id")
        context_ids.add(context_id)
        document_ids.add(context_id)
        context_span = item["source_span"]
        entity = _exact_dict(
            item["entity"], {"identifier", "scheme", "source_span"}, field_name=f"contexts[{index}].entity"
        )
        _text(entity["identifier"], field_name=f"contexts[{index}].entity.identifier")
        entity_scheme = _text(entity["scheme"], field_name=f"contexts[{index}].entity.scheme")
        assert entity_scheme is not None
        if any(char.isspace() for char in entity_scheme):
            raise SecFilingParseError("entity scheme contains whitespace")
        entity_span = _validated_span(entity["source_span"], field_name=f"contexts[{index}].entity.source_span", length=length)
        _require_contained(entity_span, context_span, field_name=f"contexts[{index}].entity.source_span")
        period = _exact_dict(
            item["period"], {"kind", "instant_date", "start_date", "end_date", "source_span"}, field_name=f"contexts[{index}].period"
        )
        period_span = _validated_span(period["source_span"], field_name=f"contexts[{index}].period.source_span", length=length)
        _require_contained(period_span, context_span, field_name=f"contexts[{index}].period.source_span")
        if period["kind"] == "instant":
            instant_text = _text(period["instant_date"], field_name="instant_date")
            assert instant_text is not None
            _date_or_datetime(instant_text, field_name="instant_date")
            if period["start_date"] is not None or period["end_date"] is not None:
                raise SecFilingParseError("instant context period shape is invalid")
        elif period["kind"] == "duration":
            start_text = _text(period["start_date"], field_name="start_date")
            end_text = _text(period["end_date"], field_name="end_date")
            assert start_text is not None and end_text is not None
            _start_raw, start_value = _date_or_datetime(start_text, field_name="start_date")
            _end_raw, end_value = _date_or_datetime(end_text, field_name="end_date")
            if type(start_value) is not type(end_value) or start_value >= end_value:
                raise SecFilingParseError("duration context period ordering is invalid")
            if period["instant_date"] is not None:
                raise SecFilingParseError("duration context period shape is invalid")
        elif period["kind"] == "forever":
            if any(period[key] is not None for key in ("instant_date", "start_date", "end_date")):
                raise SecFilingParseError("forever context period shape is invalid")
        else:
            raise SecFilingParseError("context period kind is invalid")
        dimensions = _exact_list(
            item["dimensions"], field_name=f"contexts[{index}].dimensions", maximum=limits["max_dimensions_per_context"]
        )
        dimension_names: set[str] = set()
        prior_dimension_start = -1
        for dimension_index, raw_dimension in enumerate(dimensions):
            dimension = _exact_dict(
                raw_dimension,
                {"kind", "dimension_qname", "member_qname", "typed_value_xml", "text_spans", "source_span"},
                field_name=f"contexts[{index}].dimensions[{dimension_index}]",
            )
            dimension_name = _clark_qname(dimension["dimension_qname"], field_name="dimension_qname")
            if dimension_name in dimension_names:
                raise SecFilingParseError("context repeats a dimension")
            dimension_names.add(dimension_name)
            dimension_span = _validated_span(dimension["source_span"], field_name="dimension.source_span", length=length)
            _require_contained(dimension_span, context_span, field_name="dimension.source_span")
            if dimension_span["start"] <= prior_dimension_start:
                raise SecFilingParseError("dimensions are not source ordered")
            prior_dimension_start = dimension_span["start"]
            dimension_text_spans = _span_list(dimension["text_spans"], field_name="dimension.text_spans", length=length)
            for text_span in dimension_text_spans:
                _require_contained(text_span, dimension_span, field_name="dimension.text_spans")
            if dimension["kind"] == "explicit":
                _clark_qname(dimension["member_qname"], field_name="member_qname")
                if dimension["typed_value_xml"] is not None:
                    raise SecFilingParseError("explicit dimension carries a typed value")
            elif dimension["kind"] == "typed":
                _nullable_string(dimension["typed_value_xml"], field_name="typed_value_xml")
                if not dimension["typed_value_xml"] or dimension["member_qname"] is not None:
                    raise SecFilingParseError("typed dimension shape is invalid")
            else:
                raise SecFilingParseError("dimension kind is invalid")
        unknown_segment_spans = _span_list(
            item["unknown_segment_spans"], field_name=f"contexts[{index}].unknown_segment_spans", length=length
        )
        for unknown_span in unknown_segment_spans:
            _require_contained(unknown_span, context_span, field_name="unknown_segment_spans")
        expected_segment_status = "partial" if unknown_segment_spans else "complete"
        if item["segment_content_status"] != expected_segment_status:
            raise SecFilingParseError("context segment coverage is not derived")
        if unknown_segment_spans:
            expected_context_diagnostics.append(
                {"code": "unknown_segment_content", "context_id": context_id, "source_spans": unknown_segment_spans}
            )
        unknown_spans = _span_list(
            item["unknown_scenario_spans"], field_name=f"contexts[{index}].unknown_scenario_spans", length=length
        )
        for unknown_span in unknown_spans:
            _require_contained(unknown_span, context_span, field_name="unknown_scenario_spans")
        expected_status = "partial" if unknown_spans else "complete"
        if item["scenario_content_status"] != expected_status:
            raise SecFilingParseError("context scenario coverage is not derived")
        if unknown_spans:
            expected_context_diagnostics.append(
                {"code": "unknown_scenario_content", "context_id": context_id, "source_spans": unknown_spans}
            )

    unit_ids: set[str] = set()
    for index, raw in enumerate(units):
        item = _exact_dict(
            raw, {"unit_id", "numerator_measures", "denominator_measures", "source_span"}, field_name=f"units[{index}]"
        )
        unit_text = _text(item["unit_id"], field_name=f"units[{index}].unit_id")
        assert unit_text is not None
        unit_id = _normalized_identifier(unit_text, field_name=f"units[{index}].unit_id")
        if unit_id in unit_ids:
            raise SecFilingParseError("duplicate unit id")
        if unit_id in document_ids:
            raise SecFilingParseError("duplicate document id")
        unit_ids.add(unit_id)
        document_ids.add(unit_id)
        numerator = _exact_list(item["numerator_measures"], field_name="numerator_measures", maximum=limits["max_attributes_per_element"])
        denominator = _exact_list(item["denominator_measures"], field_name="denominator_measures", maximum=limits["max_attributes_per_element"])
        if not numerator:
            raise SecFilingParseError("unit measures are invalid")
        for measure in numerator + denominator:
            _clark_qname(measure, field_name="unit measure")
        if set(numerator).intersection(denominator):
            raise SecFilingParseError("unit repeats a measure on both divide sides")

    continuation_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(continuations):
        item = _exact_dict(
            raw,
            {"continuation_id", "continued_at", "raw_value", "text_spans", "excluded_text_spans", "hidden", "source_span"},
            field_name=f"continuations[{index}]",
        )
        continuation_text = _text(item["continuation_id"], field_name="continuation_id")
        assert continuation_text is not None
        continuation_id = _normalized_identifier(continuation_text, field_name="continuation_id")
        if continuation_id in continuation_by_id:
            raise SecFilingParseError("duplicate continuation id")
        if continuation_id in document_ids:
            raise SecFilingParseError("duplicate document id")
        continued_at = _text(item["continued_at"], field_name="continued_at", nullable=True)
        if continued_at is not None:
            _normalized_identifier(continued_at, field_name="continued_at")
        continuation_raw = _nullable_string(item["raw_value"], field_name="continuation.raw_value")
        if continuation_raw is None:
            raise SecFilingParseError("continuation.raw_value must be text")
        continuation_span = item["source_span"]
        continuation_text_spans = _span_list(item["text_spans"], field_name="continuation.text_spans", length=length)
        continuation_excluded_spans = _span_list(item["excluded_text_spans"], field_name="continuation.excluded_text_spans", length=length)
        for text_span in continuation_text_spans + continuation_excluded_spans:
            _require_contained(text_span, continuation_span, field_name="continuation text span")
        _require_disjoint_spans(
            continuation_text_spans, continuation_excluded_spans, field_name="continuation text witnesses"
        )
        if type(item["hidden"]) is not bool:
            raise SecFilingParseError("continuation.hidden must be boolean")
        if item["hidden"] or document["kind"] != "inline_xbrl":
            raise SecFilingParseError("continuation placement is invalid")
        continuation_by_id[continuation_id] = item
        document_ids.add(continuation_id)
    for item in continuations:
        if item["continued_at"] is not None and item["continued_at"] not in continuation_by_id:
            raise SecFilingParseError("continuation references a missing continuation")

    fact_ids: set[str] = set()
    incoming: dict[str, int] = {key: 0 for key in continuation_by_id}
    expected_fact_diagnostics: list[dict[str, Any]] = []
    reached: set[str] = set()
    for index, raw in enumerate(facts):
        item = _exact_dict(
            raw,
            {"fact_id", "concept_qname", "kind", "context_ref", "unit_ref", "continuation_chain", "raw_value", "transformed_value", "normalized_value", "status", "nil", "lang", "decimals", "precision", "format", "sign", "scale", "hidden", "fraction", "text_spans", "excluded_text_spans", "source_span"},
            field_name=f"facts[{index}]",
        )
        fact_id = _text(item["fact_id"], field_name="fact_id", nullable=True)
        if fact_id is not None:
            fact_id = _normalized_identifier(fact_id, field_name="fact_id")
            if fact_id in fact_ids:
                raise SecFilingParseError("duplicate fact id")
            if fact_id in document_ids:
                raise SecFilingParseError("duplicate document id")
            fact_ids.add(fact_id)
            document_ids.add(fact_id)
        if item["kind"] not in {"numeric", "nonnumeric", "fraction"}:
            raise SecFilingParseError("fact kind is invalid")
        inline = document["kind"] == "inline_xbrl"
        _clark_qname(item["concept_qname"], field_name="concept_qname", ascii_local=inline)
        if document["kind"] == "other_xml":
            raise SecFilingParseError("other XML cannot carry admitted facts")
        context_ref = _text(item["context_ref"], field_name="context_ref")
        assert context_ref is not None
        _normalized_identifier(context_ref, field_name="context_ref")
        if context_ref not in context_ids:
            raise SecFilingParseError("fact references a missing context")
        unit_ref = _text(item["unit_ref"], field_name="unit_ref", nullable=True)
        if unit_ref is not None:
            _normalized_identifier(unit_ref, field_name="unit_ref")
        if item["kind"] in {"numeric", "fraction"} and unit_ref not in unit_ids:
            raise SecFilingParseError("numeric fact references a missing unit")
        if item["kind"] == "nonnumeric" and unit_ref is not None:
            raise SecFilingParseError("non-numeric fact cannot carry unitRef")
        if unit_ref is not None and unit_ref not in unit_ids:
            raise SecFilingParseError("fact references a missing unit")
        chain = _exact_list(item["continuation_chain"], field_name="continuation_chain", maximum=limits["max_continuation_chain"])
        if any(
            not isinstance(target, str)
            or _normalized_identifier(target, field_name="continuation_chain id") != target
            for target in chain
        ) or len(chain) != len(set(chain)) or any(target not in continuation_by_id for target in chain):
            raise SecFilingParseError("fact continuation_chain is invalid")
        if chain and (not inline or item["kind"] != "nonnumeric"):
            raise SecFilingParseError("only Inline XBRL nonNumeric facts may own continuations")
        if chain:
            incoming[chain[0]] += 1
        for position, continuation_id in enumerate(chain):
            reached.add(continuation_id)
            expected_next = chain[position + 1] if position + 1 < len(chain) else None
            if continuation_by_id[continuation_id]["continued_at"] != expected_next:
                raise SecFilingParseError("fact continuation_chain is not derived from continuation graph")
        raw_value = _nullable_string(item["raw_value"], field_name="fact.raw_value")
        if raw_value is None:
            raise SecFilingParseError("fact.raw_value must be text")
        _nullable_string(item["transformed_value"], field_name="fact.transformed_value")
        _nullable_string(item["normalized_value"], field_name="fact.normalized_value")
        if type(item["nil"]) is not bool or type(item["hidden"]) is not bool:
            raise SecFilingParseError("fact nil/hidden flags must be boolean")
        for field_name in ("lang", "decimals", "precision", "format", "sign"):
            _nullable_string(item[field_name], field_name=f"fact.{field_name}")
        _validate_accuracy_lexicals(item["decimals"], item["precision"])
        if item["format"] is not None:
            _clark_qname(item["format"], field_name="fact.format")
        scale = item["scale"]
        if scale is not None and (
            isinstance(scale, bool) or not isinstance(scale, int) or abs(scale) > limits["max_abs_scale"]
        ):
            raise SecFilingParseError("fact scale is invalid")
        if item["decimals"] is not None and item["precision"] is not None:
            raise SecFilingParseError("fact cannot carry both decimals and precision")
        if item["kind"] == "numeric" and not item["nil"] and item["decimals"] is None and item["precision"] is None:
            raise SecFilingParseError("numeric fact lacks accuracy")
        if item["kind"] != "numeric" and any(item[field] is not None for field in ("decimals", "precision", "sign", "scale")):
            raise SecFilingParseError("non-numeric/fraction fact carries numeric attributes")
        if item["kind"] == "fraction" and item["format"] is not None:
            raise SecFilingParseError("fraction carries a format")
        if not inline and any(item[field] is not None for field in ("format", "sign", "scale")):
            raise SecFilingParseError("native fact carries Inline XBRL attributes")
        if not inline and item["hidden"]:
            raise SecFilingParseError("native fact cannot be hidden")
        if inline and item["sign"] not in {None, "-"}:
            raise SecFilingParseError("Inline fact sign is invalid")
        if item["nil"] and any(item[field] is not None for field in ("decimals", "precision", "format", "sign", "scale")):
            raise SecFilingParseError("nil fact carries forbidden value attributes")
        owning_spans = [item["source_span"], *[continuation_by_id[target]["source_span"] for target in chain]]
        fact_text_spans = _logical_fact_span_list(
            item["text_spans"], field_name="fact.text_spans", length=length, owners=owning_spans
        )
        fact_excluded_spans = _logical_fact_span_list(
            item["excluded_text_spans"], field_name="fact.excluded_text_spans", length=length, owners=owning_spans
        )
        _require_disjoint_spans(fact_text_spans, fact_excluded_spans, field_name="fact text witnesses")
        continuation_raw_suffix = "".join(str(continuation_by_id[target]["raw_value"]) for target in chain)
        continuation_text_suffix = [
            span for target in chain for span in continuation_by_id[target]["text_spans"]
        ]
        continuation_excluded_suffix = [
            span for target in chain for span in continuation_by_id[target]["excluded_text_spans"]
        ]
        if chain and not raw_value.endswith(continuation_raw_suffix):
            raise SecFilingParseError("fact continuation text witnesses are not derived in logical order")
        if chain and continuation_text_suffix and fact_text_spans[-len(continuation_text_suffix):] != continuation_text_suffix:
            raise SecFilingParseError("fact continuation text witnesses are not derived in logical order")
        if chain and continuation_excluded_suffix and fact_excluded_spans[-len(continuation_excluded_suffix):] != continuation_excluded_suffix:
            raise SecFilingParseError("fact continuation excluded witnesses are not derived in logical order")
        local_text_count = len(fact_text_spans) - len(continuation_text_suffix)
        local_excluded_count = len(fact_excluded_spans) - len(continuation_excluded_suffix)
        if any(
            span["start"] < item["source_span"]["start"] or span["end"] > item["source_span"]["end"]
            for span in fact_text_spans[:local_text_count] + fact_excluded_spans[:local_excluded_count]
        ):
            raise SecFilingParseError("fact local text witnesses are outside the fact source span")
        status = item["status"]
        if status not in {"available", "nil", "unsupported_transform", "invalid_value"}:
            raise SecFilingParseError("fact status is invalid")
        expected_transformed: str | None
        expected_normalized: str | None
        expected_status: str
        if item["nil"]:
            expected_transformed, expected_normalized, expected_status = None, None, "nil"
            if item["fraction"] is not None or raw_value != "" or fact_text_spans or fact_excluded_spans or chain:
                raise SecFilingParseError("nil fact cannot carry fraction components")
        elif item["kind"] == "numeric":
            expected_transformed, expected_normalized, expected_status = _apply_numeric(
                item["raw_value"], format_qname=item["format"], sign=item["sign"], scale=scale, inline=inline
            )
            if item["fraction"] is not None:
                raise SecFilingParseError("numeric fact carries fraction components")
        elif item["kind"] == "nonnumeric":
            expected_transformed, expected_normalized, expected_status = _apply_nonnumeric(
                item["raw_value"], format_qname=item["format"]
            )
            if item["fraction"] is not None:
                raise SecFilingParseError("nonnumeric fact carries fraction components")
        else:
            fraction = _exact_dict(
                item["fraction"],
                {"numerator_raw", "denominator_raw", "numerator_normalized", "denominator_normalized"},
                field_name="fact.fraction",
            )
            for field_name in fraction:
                _nullable_string(fraction[field_name], field_name=f"fact.fraction.{field_name}")
            numerator_raw = fraction["numerator_raw"]
            denominator_raw = fraction["denominator_raw"]
            if numerator_raw is None or denominator_raw is None:
                raise SecFilingParseError("fraction raw components must be text")
            _nt, nn, ns = _apply_numeric(numerator_raw, format_qname=None, sign=None, scale=None, inline=True)
            _dt, dn, ds = _apply_numeric(denominator_raw, format_qname=None, sign=None, scale=None, inline=True)
            expected_status = "available" if ns == ds == "available" else "invalid_value"
            expected_transformed = (
                f"{numerator_raw}/{denominator_raw}"
                if expected_status == "available"
                else None
            )
            expected_normalized = None
            if fraction["numerator_normalized"] != nn or fraction["denominator_normalized"] != dn:
                raise SecFilingParseError("fraction normalization is not derived")
        if (
            item["transformed_value"] != expected_transformed
            or item["normalized_value"] != expected_normalized
            or status != expected_status
        ):
            raise SecFilingParseError("fact value/status is not derived")
        if status in {"unsupported_transform", "invalid_value"}:
            expected_fact_diagnostics.append(
                {"code": status, "fact_start": item["source_span"]["start"], "format": item["format"]}
            )

    for item in continuations:
        target = item["continued_at"]
        if target is not None:
            incoming[target] += 1
    if any(count > 1 for count in incoming.values()):
        raise SecFilingParseError("continuation is shared by multiple owners")
    if set(continuation_by_id) != reached:
        raise SecFilingParseError("orphan continuation is not owned by a fact")

    expected_diagnostics = expected_fact_diagnostics + expected_context_diagnostics
    expected_diagnostics.sort(
        key=lambda item: (
            item.get("fact_start", item.get("source_spans", [{"start": 0}])[0]["start"]), item["code"]
        )
    )
    if diagnostics != expected_diagnostics:
        raise SecFilingParseError("diagnostics are not derived from parser records")
    coverage = _exact_dict(
        result["coverage"],
        {"document_scope", "fact_inventory_complete", "context_references_complete", "unit_references_complete", "continuation_graph_complete", "canonical_value_complete", "context_count", "unit_count", "continuation_count", "fact_count", "diagnostic_count", "unknown_scenario_content_count", "unknown_segment_content_count", "structural_validation_complete", "ixds_validation_complete", "xbrl_schema_validation_complete", "taxonomy_validation_complete"},
        field_name="coverage",
    )
    admitted_inventory = document["kind"] == "inline_xbrl"
    expected_coverage = {
        "document_scope": "single_member",
        "fact_inventory_complete": admitted_inventory,
        "context_references_complete": document["kind"] != "other_xml",
        "unit_references_complete": document["kind"] != "other_xml",
        "continuation_graph_complete": document["kind"] == "inline_xbrl",
        "canonical_value_complete": admitted_inventory and all(
            fact["status"] not in {"unsupported_transform", "invalid_value"} for fact in facts
        ),
        "context_count": len(contexts),
        "unit_count": len(units),
        "continuation_count": len(continuations),
        "fact_count": len(facts),
        "diagnostic_count": len(diagnostics),
        "unknown_scenario_content_count": sum(item["code"] == "unknown_scenario_content" for item in expected_context_diagnostics),
        "unknown_segment_content_count": sum(item["code"] == "unknown_segment_content" for item in expected_context_diagnostics),
        "structural_validation_complete": document["kind"] != "other_xml",
        "ixds_validation_complete": False,
        "xbrl_schema_validation_complete": False,
        "taxonomy_validation_complete": False,
    }
    if coverage != expected_coverage:
        raise SecFilingParseError("coverage is not derived")

    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > limits["max_output_bytes"]:
        raise SecFilingParseError("parser output byte limit exceeded")
    if source_content is not None:
        if type(source_content) is not bytes:
            raise SecFilingParseError("source_content must be exact bytes")
        if len(source_content) != length or sha256(source_content).hexdigest() != digest:
            raise SecFilingParseError("source_content does not bind parser source witness")
        replay = parse_sec_filing_document(source_content, document_name=name)
        if _semantic_result_bytes(replay) != _semantic_result_bytes(result):
            raise SecFilingParseError("parse result does not equal canonical source replay")
    return result


__all__ = [
    "PARSER_LIMITS",
    "SEC_FILING_PARSER_ALGORITHM_FINGERPRINT",
    "SEC_FILING_PARSER_PROFILE",
    "SEC_FILING_PARSER_SCHEMA",
    "SEC_FILING_PARSER_VERSION",
    "SUPPORTED_TRANSFORMS",
    "SecFilingParseError",
    "parse_sec_filing_document",
    "validate_sec_filing_parse_result",
]
