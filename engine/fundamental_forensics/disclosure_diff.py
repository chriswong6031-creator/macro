"""Deterministic, offline filing-disclosure normalization and structural diffs.

This module is deliberately a source-text engine, not a narrative classifier.
It turns supplied 10-K/10-Q HTML or text into stable sections and blocks, retains
byte/character source coordinates, aligns two filings without network access,
and emits transparent review findings.  It does not make an assertion about
management intent, legal materiality, or an economic outcome.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from enum import Enum
from functools import cached_property, lru_cache
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from bisect import bisect_left, bisect_right
from typing import Any, Iterable, Mapping, Sequence
import unicodedata

from .models import canonical_json, stable_id


DISCLOSURE_DIFF_SCHEMA = "fundamental_forensics.disclosure_diff/v1"
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "fundamental_forensics_disclosure_diff.v1.json"
)
_MAX_EXCERPT_MINIMUM = 80
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[.'-][A-Za-z0-9]+)?", re.UNICODE)
_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?", re.UNICODE)
_ITEM_HEADING_RE = re.compile(r"^(?:part\s+[ivx]+\.?\s*)?item\s+\d+[a-z]?\.?\s+", re.I)
_ITEM_BOUNDARY_RE = re.compile(r"^(?:part\s+[ivx]+\.?\s*)?item\s+(\d+[a-z]?)\b", re.I)
_BYTE_CHECKPOINT_CHARS = 256
_MAX_FUZZY_CANDIDATES_PER_BLOCK = 4
_SECTION_NEIGHBORHOOD = 16
_TOPIC_NEIGHBORHOOD = 8
_MIN_FUZZY_TOKEN_JACCARD = 0.08
_LONG_SIMILARITY_CHARS = 4_096
_LONG_SEQUENCE_TOKENS = 512
_COARSE_EDIT_CHARS = 960
_INLINE_TOKEN_RE = re.compile(
    r"\d+(?:,\d{3})*(?:\.\d+)?%?|[A-Za-z]+(?:[-'][A-Za-z]+)?|[^\s\w]",
    re.UNICODE,
)


class BlockKind(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"


class DisclosureFindingState(str, Enum):
    TRIGGERED = "triggered"
    CLEAR = "clear"
    NOT_EVALUABLE = "not_evaluable"


class Applicability(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUABLE = "not_evaluable"


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).replace("\xa0", " ")).strip()


def _matching_text(value: str) -> str:
    return _compact_text(value).casefold()


def _token_words(value: str) -> tuple[str, ...]:
    return tuple(match.group(0).casefold() for match in _WORD_RE.finditer(value))


@lru_cache(maxsize=16_384)
def _cached_word_tokens(value: str) -> tuple[str, ...]:
    """Bound repeat tokenization during one long-lived API worker.

    Candidate selection intentionally revisits a block a few times.  A bounded
    cache keeps that work linear without retaining an unbounded filing corpus in
    memory across requests.
    """
    return _token_words(value)


def _canonical_decimal(value: float) -> str:
    try:
        output = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"invalid decimal: {value!r}") from exc
    text = format(output, "f").rstrip("0").rstrip(".")
    return text or "0"


def _form_base(form: str | None) -> str | None:
    return form.upper().replace("/A", "").strip() if form else None


def _safe_excerpt(source: str, start: int, end: int, limit: int) -> str:
    text = source[max(0, start):max(0, end)]
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


@dataclass(frozen=True)
class SourceSpan:
    """Exact source coordinates, expressed in Unicode code points and UTF-8 bytes."""

    source_sha256: str
    char_start: int
    char_end: int
    byte_start: int
    byte_end: int
    line_start: int
    column_start: int
    line_end: int
    column_end: int
    offset_unit: str = "unicode_codepoint"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_sha256": self.source_sha256,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "line_start": self.line_start,
            "column_start": self.column_start,
            "line_end": self.line_end,
            "column_end": self.column_end,
            "offset_unit": self.offset_unit,
        }


@dataclass(frozen=True)
class _SourceLocator:
    """O(n) source index with O(checkpoint) exact UTF-8 offset lookups.

    Full Inline XBRL can have thousands of table cells.  Computing a byte offset
    with ``len(source[:offset].encode())`` for each one is quadratic.  This
    locator stores line starts and sparse byte-prefix checkpoints once per
    document; each later lookup encodes at most 256 Unicode code points.
    """

    source: str = field(repr=False, compare=False)
    source_sha256: str
    line_starts: tuple[int, ...]
    byte_prefixes: tuple[int, ...]
    checkpoint_chars: int = _BYTE_CHECKPOINT_CHARS

    @classmethod
    def build(cls, source: str, source_sha256: str) -> _SourceLocator:
        line_starts = [0]
        line_starts.extend(index + 1 for index, char in enumerate(source) if char == "\n")
        byte_prefixes = [0]
        total = 0
        for checkpoint in range(1, len(source) // _BYTE_CHECKPOINT_CHARS + 1):
            start = (checkpoint - 1) * _BYTE_CHECKPOINT_CHARS
            end = checkpoint * _BYTE_CHECKPOINT_CHARS
            total += len(source[start:end].encode("utf-8"))
            byte_prefixes.append(total)
        return cls(
            source=source,
            source_sha256=source_sha256,
            line_starts=tuple(line_starts),
            byte_prefixes=tuple(byte_prefixes),
        )

    def byte_offset(self, char_offset: int) -> int:
        position = max(0, min(len(self.source), char_offset))
        checkpoint = position // self.checkpoint_chars
        checkpoint_start = checkpoint * self.checkpoint_chars
        return self.byte_prefixes[checkpoint] + len(self.source[checkpoint_start:position].encode("utf-8"))

    def line_column(self, char_offset: int) -> tuple[int, int]:
        position = max(0, min(len(self.source), char_offset))
        index = bisect_right(self.line_starts, position) - 1
        line_start = self.line_starts[max(0, index)]
        return index + 1, position - line_start

    def span(self, start: int, end: int) -> SourceSpan:
        start = max(0, min(len(self.source), start))
        end = max(start, min(len(self.source), end))
        line_start, column_start = self.line_column(start)
        line_end, column_end = self.line_column(end)
        return SourceSpan(
            source_sha256=self.source_sha256,
            char_start=start,
            char_end=end,
            byte_start=self.byte_offset(start),
            byte_end=self.byte_offset(end),
            line_start=line_start,
            column_start=column_start,
            line_end=line_end,
            column_end=column_end,
        )


@dataclass(frozen=True)
class SourceReceipt:
    """Portable evidence pointer.  The span is authoritative; excerpts are bounded aids."""

    accession: str
    form: str | None
    source_url: str | None
    source_sha256: str
    source_span: SourceSpan
    source_excerpt: str
    block_id: str | None = None
    section_id: str | None = None
    cell_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "form": self.form,
            "source_url": self.source_url,
            "source_sha256": self.source_sha256,
            "source_span": self.source_span.to_dict(),
            "source_excerpt": self.source_excerpt,
            "block_id": self.block_id,
            "section_id": self.section_id,
            "cell_id": self.cell_id,
        }


@dataclass(frozen=True)
class TableCell:
    cell_id: str
    row_index: int
    column_index: int
    text: str
    source_span: SourceSpan

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "row_index": self.row_index,
            "column_index": self.column_index,
            "text": self.text,
            "source_span": self.source_span.to_dict(),
        }


@dataclass(frozen=True)
class NormalizedTable:
    table_id: str
    rows: tuple[tuple[TableCell, ...], ...]

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(len(row) for row in self.rows)

    def text(self) -> str:
        return "\n".join(" | ".join(cell.text for cell in row) for row in self.rows)

    @cached_property
    def _cached_matching_signature(self) -> str:
        return _NUMBER_RE.sub("<number>", _matching_text(self.text()))

    def matching_signature(self) -> str:
        return self._cached_matching_signature

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "shape": list(self.shape),
            "rows": [[cell.to_dict() for cell in row] for row in self.rows],
        }


@dataclass(frozen=True)
class DisclosureBlock:
    block_id: str
    kind: BlockKind
    source_order: int
    text: str
    matching_text: str
    section_id: str
    section_key: str
    topic_keys: tuple[str, ...]
    source_span: SourceSpan
    table: NormalizedTable | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "kind": self.kind.value,
            "source_order": self.source_order,
            "text": self.text,
            "matching_text": self.matching_text,
            "section_id": self.section_id,
            "section_key": self.section_key,
            "topic_keys": list(self.topic_keys),
            "source_span": self.source_span.to_dict(),
            "table": self.table.to_dict() if self.table else None,
        }


@dataclass(frozen=True)
class DisclosureSection:
    section_id: str
    key: str
    label_key: str
    labels: tuple[tuple[str, str], ...]
    heading_block_id: str | None
    source_order: int
    source_span: SourceSpan

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "key": self.key,
            "label_key": self.label_key,
            "labels": dict(self.labels),
            "heading_block_id": self.heading_block_id,
            "source_order": self.source_order,
            "source_span": self.source_span.to_dict(),
        }


@dataclass(frozen=True)
class DisclosureDocument:
    document_id: str
    entity_cik: str | None
    accession: str
    form: str | None
    filed_at: str | None
    report_date: str | None
    source_url: str | None
    content_type: str
    source_sha256: str
    raw_source: str = field(repr=False, compare=False)
    source_locator: _SourceLocator = field(repr=False, compare=False)
    sections: tuple[DisclosureSection, ...] = ()
    blocks: tuple[DisclosureBlock, ...] = ()

    def receipt_for_span(
        self,
        span: SourceSpan,
        *,
        block_id: str | None = None,
        section_id: str | None = None,
        cell_id: str | None = None,
        excerpt_chars: int = 360,
    ) -> SourceReceipt:
        return SourceReceipt(
            accession=self.accession,
            form=self.form,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
            source_span=span,
            source_excerpt=_safe_excerpt(
                self.raw_source, span.char_start, span.char_end, max(_MAX_EXCERPT_MINIMUM, excerpt_chars)
            ),
            block_id=block_id,
            section_id=section_id,
            cell_id=cell_id,
        )

    def receipt_for_block(self, block: DisclosureBlock, *, excerpt_chars: int = 360) -> SourceReceipt:
        return self.receipt_for_span(
            block.source_span,
            block_id=block.block_id,
            section_id=block.section_id,
            excerpt_chars=excerpt_chars,
        )

    def document_receipt(self, *, excerpt_chars: int = 360) -> SourceReceipt:
        return self.receipt_for_span(
            self.source_locator.span(0, min(len(self.raw_source), max(1, excerpt_chars))),
            excerpt_chars=excerpt_chars,
        )

    def to_dict(
        self,
        *,
        include_source_text: bool = False,
        max_source_chars: int = 16_384,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "document_id": self.document_id,
            "entity_cik": self.entity_cik,
            "accession": self.accession,
            "form": self.form,
            "filed_at": self.filed_at,
            "report_date": self.report_date,
            "source_url": self.source_url,
            "content_type": self.content_type,
            "source_sha256": self.source_sha256,
            "source_chars": len(self.raw_source),
            "sections": [item.to_dict() for item in self.sections],
            "blocks": [item.to_dict() for item in self.blocks],
        }
        if include_source_text:
            bound = max(0, max_source_chars)
            payload["source_text"] = self.raw_source[:bound]
            payload["source_text_truncated"] = len(self.raw_source) > bound
        return payload


@dataclass(frozen=True)
class SectionRule:
    key: str
    label_key: str
    labels: tuple[tuple[str, str], ...]
    forms: tuple[str, ...]
    patterns: tuple[str, ...]

    def matches(self, text: str, form: str | None) -> bool:
        if self.forms and _form_base(form) not in self.forms:
            return False
        return any(re.search(pattern, text, re.I) is not None for pattern in self.patterns)


@dataclass(frozen=True)
class TopicRule:
    key: str
    patterns: tuple[str, ...]

    def matches(self, text: str) -> bool:
        return any(re.search(pattern, text, re.I) is not None for pattern in self.patterns)


@dataclass(frozen=True)
class DisclosureDetectorSpec:
    detector_id: str
    order: int
    label_key: str
    labels: tuple[tuple[str, str], ...]
    priority: str
    options: tuple[tuple[str, Any], ...]
    benign_explanation: str
    limitations: tuple[str, ...]

    def option(self, name: str, default: Any = None) -> Any:
        return dict(self.options).get(name, default)


@dataclass(frozen=True)
class DisclosureDiffRegistry:
    schema: str
    version: str
    source_excerpt_chars: int
    max_embedded_source_chars: int
    sections: tuple[SectionRule, ...]
    topics: tuple[TopicRule, ...]
    boilerplate_patterns: tuple[str, ...]
    auditor_pattern: str
    detectors: tuple[DisclosureDetectorSpec, ...]

    def section_for_heading(self, text: str, form: str | None) -> SectionRule | None:
        for rule in self.sections:
            if rule.matches(text, form):
                return rule
        return None

    def topic_keys_for(self, text: str, section_key: str) -> tuple[str, ...]:
        keys = {section_key} if section_key != "preamble" else set()
        for rule in self.topics:
            if rule.matches(text):
                keys.add(rule.key)
        return tuple(sorted(keys))

    def detector(self, detector_id: str) -> DisclosureDetectorSpec:
        return next(item for item in self.detectors if item.detector_id == detector_id)


def registry_from_dict(raw: Mapping[str, Any]) -> DisclosureDiffRegistry:
    if raw.get("schema") != "fundamental_forensics.disclosure_diff.registry/v1":
        raise ValueError("unsupported disclosure-diff registry schema")
    section_rules: list[SectionRule] = []
    for item in raw.get("sections", []):
        labels = tuple(sorted((str(k), str(v)) for k, v in dict(item["labels"]).items()))
        if not {"en", "zh-Hans"}.issubset(dict(labels)):
            raise ValueError(f"section {item.get('key')} must include en and zh-Hans labels")
        section_rules.append(
            SectionRule(
                key=str(item["key"]),
                label_key=str(item["label_key"]),
                labels=labels,
                forms=tuple(sorted(_form_base(str(form)) or "" for form in item.get("forms", []))),
                patterns=tuple(str(pattern) for pattern in item.get("patterns", [])),
            )
        )
    topics = tuple(
        TopicRule(key=str(item["key"]), patterns=tuple(str(pattern) for pattern in item.get("patterns", [])))
        for item in raw.get("topics", [])
    )
    detectors: list[DisclosureDetectorSpec] = []
    for item in raw.get("detectors", []):
        labels = tuple(sorted((str(k), str(v)) for k, v in dict(item["labels"]).items()))
        if not {"en", "zh-Hans"}.issubset(dict(labels)):
            raise ValueError(f"detector {item.get('detector_id')} must include en and zh-Hans labels")
        options = tuple(
            sorted(
                (str(key), value)
                for key, value in item.items()
                if key
                not in {
                    "detector_id", "order", "label_key", "labels", "priority",
                    "benign_explanation", "limitations",
                }
            )
        )
        detectors.append(
            DisclosureDetectorSpec(
                detector_id=str(item["detector_id"]),
                order=int(item["order"]),
                label_key=str(item["label_key"]),
                labels=labels,
                priority=str(item["priority"]),
                options=options,
                benign_explanation=str(item["benign_explanation"]),
                limitations=tuple(sorted(str(value) for value in item.get("limitations", []))),
            )
        )
    detectors.sort(key=lambda item: (item.order, item.detector_id))
    return DisclosureDiffRegistry(
        schema=str(raw["schema"]),
        version=str(raw["version"]),
        source_excerpt_chars=int(raw.get("source_excerpt_chars", 360)),
        max_embedded_source_chars=int(raw.get("max_embedded_source_chars", 16_384)),
        sections=tuple(section_rules),
        topics=topics,
        boilerplate_patterns=tuple(str(item) for item in raw.get("boilerplate_patterns", [])),
        auditor_pattern=str(raw["auditor_pattern"]),
        detectors=tuple(detectors),
    )


def load_disclosure_diff_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> DisclosureDiffRegistry:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("disclosure-diff registry must be an object")
    return registry_from_dict(raw)


@dataclass
class _RawCell:
    start: int
    end: int
    text_parts: list[str]


@dataclass
class _RawTable:
    start: int
    end: int | None = None
    rows: list[list[_RawCell]] = field(default_factory=list)
    current_row: list[_RawCell] | None = None
    current_cell: _RawCell | None = None


@dataclass
class _RawBlock:
    kind: BlockKind
    start: int
    end: int
    text: str
    table_rows: tuple[tuple[_RawCell, ...], ...] = ()


@dataclass
class _Capture:
    tag: str
    start: int
    text_parts: list[str] = field(default_factory=list)
    has_block_child: bool = False


class _HtmlBlockExtractor(HTMLParser):
    """Small lossless-enough extractor for SEC-style HTML without third-party parsers."""

    _BLOCK_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "div", "blockquote", "dd", "dt"})
    _NONVISIBLE_TAGS = frozenset({
        "script", "style", "noscript", "head", "title", "template", "svg",
        "ix:hidden", "ix:header", "ix:references", "ix:resources",
        "ix:exclude", "ix:relationship",
        "xbrli:context", "xbrli:unit", "link:schemaref", "link:linkbaseref",
    })
    _VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.line_starts = self._line_starts(source)
        self.blocks: list[_RawBlock] = []
        self.captures: list[_Capture] = []
        self.tables: list[_RawTable] = []
        # This is deliberately a subtree depth, not just a stack of hidden
        # tags.  SEC metadata often nests ordinary ``div``/``span`` elements
        # under a hidden wrapper; treating only the outer tag as ignored can
        # leak text as soon as a child happens to have the same tag name.
        self.ignored_depth = 0

    @staticmethod
    def _line_starts(source: str) -> tuple[int, ...]:
        starts = [0]
        starts.extend(index + 1 for index, char in enumerate(source) if char == "\n")
        return tuple(starts)

    def _offset(self) -> int:
        line, column = self.getpos()
        if line <= 0 or line > len(self.line_starts):
            return len(self.source)
        return min(len(self.source), self.line_starts[line - 1] + column)

    def _tag_end(self, start: int) -> int:
        close = self.source.find(">", start)
        return len(self.source) if close < 0 else close + 1

    def _mark_block_child(self) -> None:
        for capture in self.captures:
            if capture.tag == "div":
                capture.has_block_child = True

    @classmethod
    def _is_nonvisible(cls, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in cls._NONVISIBLE_TAGS:
            return True
        attr_map = {str(name).casefold(): (value or "") for name, value in attrs}
        if "hidden" in attr_map:
            return True
        if attr_map.get("aria-hidden", "").casefold() == "true":
            return True
        style = re.sub(r"\s+", "", attr_map.get("style", "").casefold())
        if "display:none" in style or "visibility:hidden" in style:
            return True
        classes = set(attr_map.get("class", "").casefold().split())
        return bool({"hidden", "ix-hidden", "inline-xbrl-hidden"} & classes)

    def _append_text(self, value: str) -> None:
        if self.ignored_depth:
            return
        if self.tables:
            table = self.tables[-1]
            if table.current_cell is not None:
                table.current_cell.text_parts.append(value)
            return
        for capture in self.captures:
            capture.text_parts.append(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        start = self._offset()
        if self.ignored_depth:
            if tag not in self._VOID_TAGS:
                self.ignored_depth += 1
            return
        if self._is_nonvisible(tag, attrs):
            if tag not in self._VOID_TAGS:
                self.ignored_depth = 1
            return
        if tag == "br":
            self._append_text(" ")
            return
        if tag == "table":
            self._mark_block_child()
            self.tables.append(_RawTable(start=start))
            return
        if self.tables:
            table = self.tables[-1]
            if tag == "tr":
                if table.current_row is not None and table.current_row:
                    table.rows.append(table.current_row)
                table.current_row = []
            elif tag in {"td", "th"}:
                if table.current_row is None:
                    table.current_row = []
                cell = _RawCell(start=start, end=start, text_parts=[])
                table.current_row.append(cell)
                table.current_cell = cell
            return
        if tag in self._BLOCK_TAGS:
            self._mark_block_child()
            self.captures.append(_Capture(tag=tag, start=start))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def handle_entityref(self, name: str) -> None:
        self._append_text(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self._append_text(html.unescape(f"&#{name};"))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        start = self._offset()
        end = self._tag_end(start)
        if self.ignored_depth:
            if tag not in self._VOID_TAGS:
                self.ignored_depth -= 1
            return
        if self.tables:
            table = self.tables[-1]
            if tag in {"td", "th"} and table.current_cell is not None:
                table.current_cell.end = end
                table.current_cell = None
                return
            if tag == "tr":
                if table.current_row is not None and table.current_row:
                    table.rows.append(table.current_row)
                table.current_row = None
                return
            if tag == "table":
                if table.current_row is not None and table.current_row:
                    table.rows.append(table.current_row)
                table.end = end
                self.tables.pop()
                rows = tuple(tuple(row) for row in table.rows)
                text = "\n".join(
                    " | ".join(_compact_text("".join(cell.text_parts)) for cell in row) for row in rows
                )
                if _compact_text(text):
                    self.blocks.append(_RawBlock(BlockKind.TABLE, table.start, end, text, rows))
                return
            return
        matching_index = next(
            (index for index in range(len(self.captures) - 1, -1, -1) if self.captures[index].tag == tag),
            None,
        )
        if matching_index is None:
            return
        trailing = self.captures[matching_index:]
        del self.captures[matching_index:]
        for capture in reversed(trailing):
            text = _compact_text("".join(capture.text_parts))
            if not text or (capture.tag == "div" and capture.has_block_child):
                continue
            kind = BlockKind.HEADING if capture.tag.startswith("h") and len(capture.tag) == 2 else BlockKind.PARAGRAPH
            self.blocks.append(_RawBlock(kind, capture.start, end, text))

    def finish(self) -> tuple[_RawBlock, ...]:
        self.close()
        end = len(self.source)
        for table in self.tables:
            if table.current_row is not None and table.current_row:
                table.rows.append(table.current_row)
            rows = tuple(tuple(row) for row in table.rows)
            text = "\n".join(
                " | ".join(_compact_text("".join(cell.text_parts)) for cell in row) for row in rows
            )
            if _compact_text(text):
                self.blocks.append(_RawBlock(BlockKind.TABLE, table.start, end, text, rows))
        for capture in self.captures:
            text = _compact_text("".join(capture.text_parts))
            if text and not (capture.tag == "div" and capture.has_block_child):
                kind = BlockKind.HEADING if capture.tag.startswith("h") and len(capture.tag) == 2 else BlockKind.PARAGRAPH
                self.blocks.append(_RawBlock(kind, capture.start, end, text))
        unique: dict[tuple[str, int, int, str], _RawBlock] = {}
        for block in self.blocks:
            unique[(block.kind.value, block.start, block.end, block.text)] = block
        return tuple(sorted(unique.values(), key=lambda item: (item.start, item.end, item.kind.value, item.text)))


def _looks_like_heading(text: str, registry: DisclosureDiffRegistry, form: str | None) -> bool:
    compact = _compact_text(text)
    if not compact or len(compact) > 180:
        return False
    if _ITEM_HEADING_RE.match(compact):
        return True
    if registry.section_for_heading(compact, form) is not None:
        return True
    letters = re.sub(r"[^A-Za-z]", "", compact)
    return len(letters) >= 4 and compact == compact.upper() and len(compact.split()) <= 12


def _generic_item_section_rule(text: str) -> SectionRule | None:
    """Create a deterministic boundary for an SEC Item outside our named taxonomy.

    Named sections such as Item 1A and Item 7 retain their bilingual registry
    keys. Unregistered Item headings still have to end the preceding section;
    otherwise Risk Factors can incorrectly swallow Items 1B through 6, and
    Controls can swallow proxy-reference Items 10 through 14.
    """
    compact = _compact_text(text)
    match = _ITEM_BOUNDARY_RE.match(compact)
    if match is None:
        return None
    item_key = re.sub(r"[^0-9a-z]", "", match.group(1).casefold())
    if not item_key:
        return None
    key = f"item_{item_key}"
    label = compact[:180]
    return SectionRule(
        key=key,
        label_key=f"disclosure.section.{key}",
        labels=(("en", label), ("zh-Hans", label)),
        forms=(),
        patterns=(),
    )


def _plain_table_block(lines: Sequence[tuple[int, str]], source: str) -> _RawBlock:
    rows: list[tuple[_RawCell, ...]] = []
    for line_start, line in lines:
        raw = line.rstrip("\r\n")
        pieces = raw.split("|")
        if raw.lstrip().startswith("|"):
            pieces = pieces[1:]
            offset = raw.find("|") + 1
        else:
            offset = 0
        if raw.rstrip().endswith("|") and pieces:
            pieces = pieces[:-1]
        cells: list[_RawCell] = []
        cursor = offset
        for piece in pieces:
            local = raw.find(piece, cursor)
            if local < 0:
                local = cursor
            start = line_start + local
            end = start + len(piece)
            cells.append(_RawCell(start=start, end=end, text_parts=[piece]))
            cursor = local + len(piece) + 1
        if cells:
            rows.append(tuple(cells))
    start = lines[0][0]
    end = lines[-1][0] + len(lines[-1][1])
    text = "\n".join(" | ".join(_compact_text("".join(cell.text_parts)) for cell in row) for row in rows)
    return _RawBlock(BlockKind.TABLE, start, end, text, tuple(rows))


def _plain_text_blocks(source: str, registry: DisclosureDiffRegistry, form: str | None) -> tuple[_RawBlock, ...]:
    lines: list[tuple[int, str]] = []
    offset = 0
    for line in source.splitlines(keepends=True):
        lines.append((offset, line))
        offset += len(line)
    if not lines and source:
        lines.append((0, source))

    output: list[_RawBlock] = []
    paragraph: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        nonempty = [(start, line) for start, line in paragraph if _compact_text(line)]
        paragraph = []
        if not nonempty:
            return
        if len(nonempty) >= 2 and all("|" in line for _, line in nonempty):
            output.append(_plain_table_block(nonempty, source))
            return
        start = nonempty[0][0]
        end = nonempty[-1][0] + len(nonempty[-1][1])
        text = _compact_text(" ".join(line.strip() for _, line in nonempty))
        if text:
            output.append(_RawBlock(BlockKind.PARAGRAPH, start, end, text))

    for start, line in lines:
        compact = _compact_text(line)
        if not compact:
            flush()
            continue
        if _looks_like_heading(compact, registry, form):
            flush()
            output.append(_RawBlock(BlockKind.HEADING, start, start + len(line), compact))
            continue
        paragraph.append((start, line))
    flush()
    return tuple(sorted(output, key=lambda item: (item.start, item.end, item.kind.value, item.text)))


def _raw_blocks(source: str, content_type: str, registry: DisclosureDiffRegistry, form: str | None) -> tuple[_RawBlock, ...]:
    if content_type == "html":
        parser = _HtmlBlockExtractor(source)
        parser.feed(source)
        blocks = parser.finish()
        # A malformed HTML response may contain no semantic tags.  In that case
        # a plain-text fallback preserves the supplied text rather than emitting
        # an empty disclosure corpus.
        if blocks:
            return blocks
    return _plain_text_blocks(source, registry, form)


def _normalize_input(document: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    if not isinstance(document, Mapping):
        raise TypeError("filing document must be a mapping")
    raw = dict(document)
    content: Any = raw.get("content")
    content_type = str(raw.get("content_type") or "").casefold()
    if content is None and "html" in raw:
        content = raw["html"]
        content_type = content_type or "html"
    if content is None and "text" in raw:
        content = raw["text"]
        content_type = content_type or "text"
    if content is None and "source_text" in raw:
        content = raw["source_text"]
    if not isinstance(content, str) or not content:
        raise ValueError("filing document requires non-empty content, html, text, or source_text")
    if content_type not in {"html", "text"}:
        content_type = "html" if re.search(r"<\s*(?:html|body|p|div|table|h[1-6])\b", content, re.I) else "text"
    accession = str(raw.get("accession") or "").strip()
    if not accession:
        raise ValueError("filing document requires accession")
    return raw, content, content_type


def normalize_filing(
    document: Mapping[str, Any],
    *,
    registry: DisclosureDiffRegistry | Mapping[str, Any] | None = None,
) -> DisclosureDocument:
    """Normalize supplied filing content without I/O or an implicit clock.

    ``content`` can be HTML or text.  Every generated node retains a span into
    that exact supplied string and its SHA-256, allowing a later consumer to
    re-open the original source and verify the receipt byte-for-byte.
    """
    config = (
        load_disclosure_diff_registry()
        if registry is None
        else registry_from_dict(registry) if isinstance(registry, Mapping) else registry
    )
    raw, source, content_type = _normalize_input(document)
    accession = str(raw["accession"]).strip()
    form = str(raw["form"]).strip() if raw.get("form") is not None else None
    entity_cik = str(raw["entity_cik"]).strip() if raw.get("entity_cik") is not None else None
    filed_at = str(raw.get("filed_at") or raw.get("filing_date") or "").strip() or None
    report_date = str(raw.get("report_date") or "").strip() or None
    source_url = str(raw.get("source_url")).strip() if raw.get("source_url") else None
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    source_locator = _SourceLocator.build(source, source_sha256)
    document_id = stable_id(
        "disclosure_document",
        entity_cik,
        accession,
        form,
        filed_at,
        report_date,
        source_url,
        source_sha256,
    )
    raw_blocks = _raw_blocks(source, content_type, config, form)

    first_span = source_locator.span(0, min(len(source), max(1, len(source))))
    preamble_id = stable_id("disclosure_section", document_id, "preamble", first_span.to_dict())
    preamble = DisclosureSection(
        section_id=preamble_id,
        key="preamble",
        label_key="disclosure.section.preamble",
        labels=(("en", "Preamble"), ("zh-Hans", "前言")),
        heading_block_id=None,
        source_order=-1,
        source_span=first_span,
    )
    sections: list[DisclosureSection] = [preamble]
    blocks: list[DisclosureBlock] = []
    current_section = preamble

    for source_order, raw_block in enumerate(raw_blocks):
        text = _compact_text(raw_block.text)
        if not text:
            continue
        span = source_locator.span(raw_block.start, raw_block.end)
        # SEC Inline XBRL frequently renders Item labels in styled <p>/<div>
        # nodes instead of h1-h6. Promote only deterministic heading-shaped
        # paragraphs before section routing; the receipt remains the original
        # HTML span.
        block_kind = (
            BlockKind.HEADING
            if raw_block.kind is BlockKind.HEADING
            or (raw_block.kind is BlockKind.PARAGRAPH and _looks_like_heading(text, config, form))
            else raw_block.kind
        )
        potential_rule = config.section_for_heading(text, form) if block_kind is BlockKind.HEADING else None
        if potential_rule is None and block_kind is BlockKind.HEADING:
            potential_rule = _generic_item_section_rule(text)
        provisional_key = potential_rule.key if potential_rule else current_section.key
        provisional_id = stable_id(
            "disclosure_block",
            document_id,
            block_kind.value,
            provisional_key,
            text,
            span.to_dict(),
        )
        if potential_rule is not None:
            section_id = stable_id(
                "disclosure_section",
                document_id,
                potential_rule.key,
                potential_rule.label_key,
                provisional_id,
                span.to_dict(),
            )
            current_section = DisclosureSection(
                section_id=section_id,
                key=potential_rule.key,
                label_key=potential_rule.label_key,
                labels=potential_rule.labels,
                heading_block_id=provisional_id,
                source_order=source_order,
                source_span=span,
            )
            sections.append(current_section)
        table: NormalizedTable | None = None
        if raw_block.kind is BlockKind.TABLE:
            table_id = stable_id("disclosure_table", provisional_id, text, span.to_dict())
            rows: list[tuple[TableCell, ...]] = []
            for row_index, row in enumerate(raw_block.table_rows):
                cells: list[TableCell] = []
                for column_index, raw_cell in enumerate(row):
                    cell_span = source_locator.span(raw_cell.start, raw_cell.end)
                    cell_text = _compact_text("".join(raw_cell.text_parts))
                    cell_id = stable_id(
                        "disclosure_table_cell", table_id, row_index, column_index, cell_text, cell_span.to_dict()
                    )
                    cells.append(
                        TableCell(
                            cell_id=cell_id,
                            row_index=row_index,
                            column_index=column_index,
                            text=cell_text,
                            source_span=cell_span,
                        )
                    )
                if cells:
                    rows.append(tuple(cells))
            table = NormalizedTable(table_id=table_id, rows=tuple(rows))
            text = table.text()
        block_id = stable_id(
            "disclosure_block",
            document_id,
            block_kind.value,
            current_section.key,
            text,
            span.to_dict(),
        )
        # A newly classified heading's section ID derives from this same final
        # block identity. Rebuild the section once to avoid an index-derived ID.
        if potential_rule is not None:
            section_id = stable_id(
                "disclosure_section",
                document_id,
                potential_rule.key,
                potential_rule.label_key,
                block_id,
                span.to_dict(),
            )
            current_section = DisclosureSection(
                section_id=section_id,
                key=potential_rule.key,
                label_key=potential_rule.label_key,
                labels=potential_rule.labels,
                heading_block_id=block_id,
                source_order=source_order,
                source_span=span,
            )
            sections[-1] = current_section
        blocks.append(
            DisclosureBlock(
                block_id=block_id,
                kind=block_kind,
                source_order=source_order,
                text=text,
                matching_text=_matching_text(text),
                section_id=current_section.section_id,
                section_key=current_section.key,
                topic_keys=config.topic_keys_for(text, current_section.key),
                source_span=span,
                table=table,
            )
        )
    return DisclosureDocument(
        document_id=document_id,
        entity_cik=entity_cik,
        accession=accession,
        form=form,
        filed_at=filed_at,
        report_date=report_date,
        source_url=source_url,
        content_type=content_type,
        source_sha256=source_sha256,
        raw_source=source,
        source_locator=source_locator,
        sections=tuple(sections),
        blocks=tuple(blocks),
    )


@dataclass(frozen=True)
class InlineEdit:
    operation: str
    prior_text: str
    current_text: str
    contains_numeric: bool
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "prior_text": self.prior_text,
            "current_text": self.current_text,
            "contains_numeric": self.contains_numeric,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class AlignedComparison:
    comparison_id: str
    relation: str
    prior_block_id: str | None
    current_block_id: str | None
    prior_section_id: str | None
    current_section_id: str | None
    section_key: str | None
    similarity: str | None
    suppressed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "relation": self.relation,
            "prior_block_id": self.prior_block_id,
            "current_block_id": self.current_block_id,
            "prior_section_id": self.prior_section_id,
            "current_section_id": self.current_section_id,
            "section_key": self.section_key,
            "similarity": self.similarity,
            "suppressed": self.suppressed,
        }


@dataclass(frozen=True)
class RedlineOp:
    op_id: str
    operation: str
    comparison_id: str
    section_key: str | None
    prior_block_id: str | None
    current_block_id: str | None
    prior_receipt: SourceReceipt | None
    current_receipt: SourceReceipt | None
    changed_token_ratio: str | None
    changed_token_count: int
    numeric_changed: bool
    inline_edits: tuple[InlineEdit, ...]
    suppressed: bool = False
    parent_op_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_id": self.op_id,
            "operation": self.operation,
            "comparison_id": self.comparison_id,
            "section_key": self.section_key,
            "prior_block_id": self.prior_block_id,
            "current_block_id": self.current_block_id,
            "prior_receipt": self.prior_receipt.to_dict() if self.prior_receipt else None,
            "current_receipt": self.current_receipt.to_dict() if self.current_receipt else None,
            "changed_token_ratio": self.changed_token_ratio,
            "changed_token_count": self.changed_token_count,
            "numeric_changed": self.numeric_changed,
            "inline_edits": [item.to_dict() for item in self.inline_edits],
            "suppressed": self.suppressed,
            "parent_op_id": self.parent_op_id,
        }


@dataclass(frozen=True)
class DisclosureFinding:
    finding_id: str
    detector_id: str
    detector_version: str
    label_key: str
    labels: tuple[tuple[str, str], ...]
    state: DisclosureFindingState
    applicability: Applicability
    priority: str
    review_level: str
    prior_accession: str
    current_accession: str
    prior_section_ids: tuple[str, ...]
    current_section_ids: tuple[str, ...]
    evidence_receipts: tuple[SourceReceipt, ...]
    why_flagged: tuple[tuple[str, str], ...]
    benign_explanation: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "label_key": self.label_key,
            "labels": dict(self.labels),
            "state": self.state.value,
            "applicability": self.applicability.value,
            "priority": self.priority,
            "review_level": self.review_level,
            "prior_accession": self.prior_accession,
            "current_accession": self.current_accession,
            "prior_section_ids": list(self.prior_section_ids),
            "current_section_ids": list(self.current_section_ids),
            "evidence_receipts": [item.to_dict() for item in self.evidence_receipts],
            "why_flagged": dict(self.why_flagged),
            "benign_explanation": self.benign_explanation,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class DisclosureComparison:
    comparison_id: str
    schema: str
    engine_version: str
    prior: DisclosureDocument
    current: DisclosureDocument
    comparisons: tuple[AlignedComparison, ...]
    redline_ops: tuple[RedlineOp, ...]
    findings: tuple[DisclosureFinding, ...]
    limitations: tuple[str, ...]
    include_source_text: bool = False
    max_source_chars: int = 16_384

    def to_dict(
        self,
        *,
        include_source_text: bool | None = None,
        max_source_chars: int | None = None,
    ) -> dict[str, Any]:
        include = self.include_source_text if include_source_text is None else include_source_text
        bound = self.max_source_chars if max_source_chars is None else max_source_chars
        return {
            "schema": self.schema,
            "comparison_id": self.comparison_id,
            "engine_version": self.engine_version,
            "prior_document": self.prior.to_dict(
                include_source_text=include, max_source_chars=bound
            ),
            "current_document": self.current.to_dict(
                include_source_text=include, max_source_chars=bound
            ),
            "sections": {
                "prior": [item.to_dict() for item in self.prior.sections],
                "current": [item.to_dict() for item in self.current.sections],
            },
            "comparisons": [item.to_dict() for item in self.comparisons],
            "redline_ops": [item.to_dict() for item in self.redline_ops],
            "findings": [item.to_dict() for item in self.findings],
            "limitations": list(self.limitations),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


def _block_fingerprint(block: DisclosureBlock) -> str:
    return block.matching_text


def _counter_overlap_ratio(before: Sequence[str], after: Sequence[str]) -> float:
    """Order-insensitive, multiplicity-aware ratio for very long text.

    ``SequenceMatcher`` can have pathological runtime on long repeated SEC
    boilerplate.  A multiset overlap preserves meaningful word-count changes,
    treats equal text exactly, and has bounded linear behavior.  It is used
    only after structural candidate filtering, never as a broad corpus search.
    """
    if not before and not after:
        return 1.0
    if not before or not after:
        return 0.0
    common = sum((Counter(before) & Counter(after)).values())
    return common / max(len(before), len(after))


def _long_word_similarity(prior_text: str, current_text: str) -> float:
    """Fast, deterministic similarity for long prose and table signatures."""
    before = _cached_word_tokens(prior_text)
    after = _cached_word_tokens(current_text)
    if before == after:
        return 1.0
    # For extremely long or repeated sequences, even token-level matching with
    # autojunk can spend disproportionate time seeking anchors.  The bounded
    # multiset route is intentionally coarse and is paired with a similarly
    # coarse inline redline marker below.
    if max(len(before), len(after)) > _LONG_SEQUENCE_TOKENS:
        return _counter_overlap_ratio(before, after)
    ordered_ratio = SequenceMatcher(None, before, after, autojunk=True).ratio()
    # ``autojunk`` deliberately removes very common words from a long input.
    # In repetitive filing prose that can leave only a one-off table value or
    # paragraph number as an anchor, understating otherwise clear continuity.
    # Retain the larger multiplicity-aware lexical overlap once the sequence is
    # long enough for autojunk to activate; section/locality constraints still
    # prevent this from becoming a global bag-of-words matcher.
    if max(len(before), len(after)) >= 200:
        return max(ordered_ratio, _counter_overlap_ratio(before, after))
    return ordered_ratio


def _table_similarity(prior: DisclosureBlock, current: DisclosureBlock) -> float:
    if prior.table is None or current.table is None:
        return 0.0
    return _long_word_similarity(prior.table.matching_signature(), current.table.matching_signature())


def _block_similarity(prior: DisclosureBlock, current: DisclosureBlock) -> float:
    if prior.kind is not current.kind:
        return 0.0
    if prior.kind is BlockKind.TABLE:
        return _table_similarity(prior, current)
    if prior.matching_text == current.matching_text:
        return 1.0
    # Character-level matching is fragile on repeated SEC prose even when a
    # paragraph is only a few kilobytes.  Structural candidates already share
    # a section/topic and a lexical fingerprint, so word-token order is the
    # useful signal here for every residual paragraph, not just the longest.
    return _long_word_similarity(prior.matching_text, current.matching_text)


def _bounded_redline_text(value: str, *, limit: int = _COARSE_EDIT_CHARS) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    if limit <= 1:  # pragma: no cover - internal constant is contract-bound
        return value[:limit], True
    head = (limit - 1) // 2
    tail = limit - head - 1
    return value[:head] + "…" + value[-tail:], True


def _coarse_inline_edit(
    operation: str,
    prior_text: str,
    current_text: str,
) -> InlineEdit:
    prior_excerpt, prior_truncated = _bounded_redline_text(prior_text)
    current_excerpt, current_truncated = _bounded_redline_text(current_text)
    return InlineEdit(
        operation=operation,
        prior_text=prior_excerpt,
        current_text=current_excerpt,
        contains_numeric=bool(_NUMBER_RE.search(prior_text) or _NUMBER_RE.search(current_text)),
        truncated=prior_truncated or current_truncated,
    )


def _inline_edits(prior_text: str, current_text: str) -> tuple[InlineEdit, ...]:
    if prior_text == current_text:
        return ()
    before = _INLINE_TOKEN_RE.findall(prior_text)
    after = _INLINE_TOKEN_RE.findall(current_text)
    max_tokens = max(len(before), len(after))
    if max_tokens > _LONG_SEQUENCE_TOKENS or max(len(prior_text), len(current_text)) > _LONG_SIMILARITY_CHARS:
        operation = "replace" if before and after else "delete" if before else "insert"
        return (_coarse_inline_edit(operation, prior_text, current_text),)
    matcher = SequenceMatcher(
        None,
        [item.casefold() for item in before],
        [item.casefold() for item in after],
        autojunk=True,
    )
    edits: list[InlineEdit] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        prior_part = " ".join(before[i1:i2])
        current_part = " ".join(after[j1:j2])
        numeric = bool(_NUMBER_RE.search(prior_part) or _NUMBER_RE.search(current_part))
        edits.append(
            InlineEdit(
                operation={"replace": "replace", "delete": "delete", "insert": "insert"}[tag],
                prior_text=prior_part,
                current_text=current_part,
                contains_numeric=numeric,
            )
        )
    return tuple(edits)


def _change_stats(prior_text: str, current_text: str) -> tuple[str, int, bool, tuple[InlineEdit, ...]]:
    if prior_text == current_text:
        return "0", 0, False, ()
    before = _token_words(prior_text)
    after = _token_words(current_text)
    max_tokens = max(len(before), len(after))
    if max_tokens > _LONG_SEQUENCE_TOKENS:
        common = sum((Counter(before) & Counter(after)).values())
        changed = max_tokens - common
        # A word-order change still deserves a transparent non-zero redline,
        # even though a multiset has the same members.
        if changed == 0:
            changed = 1
    else:
        matcher = SequenceMatcher(None, before, after, autojunk=True)
        changed = sum(
            max(i2 - i1, j2 - j1)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != "equal"
        )
    ratio = changed / max(1, max(len(before), len(after)))
    edits = _inline_edits(prior_text, current_text)
    numeric_changed = bool(
        tuple(_NUMBER_RE.findall(prior_text)) != tuple(_NUMBER_RE.findall(current_text))
        or any(item.contains_numeric for item in edits)
    )
    return _canonical_decimal(ratio), changed, numeric_changed, edits


def _is_boilerplate(text: str, registry: DisclosureDiffRegistry) -> bool:
    return any(re.search(pattern, text, re.I) is not None for pattern in registry.boilerplate_patterns)


def _receipt_for_cell(document: DisclosureDocument, block: DisclosureBlock, cell: TableCell, registry: DisclosureDiffRegistry) -> SourceReceipt:
    return document.receipt_for_span(
        cell.source_span,
        block_id=block.block_id,
        section_id=block.section_id,
        cell_id=cell.cell_id,
        excerpt_chars=registry.source_excerpt_chars,
    )


def _make_comparison(
    relation: str,
    prior: DisclosureBlock | None,
    current: DisclosureBlock | None,
    *,
    similarity: float | None,
    suppressed: bool,
    engine_version: str,
) -> AlignedComparison:
    section_key = current.section_key if current else prior.section_key if prior else None
    comparison_id = stable_id(
        "disclosure_alignment",
        engine_version,
        relation,
        prior.block_id if prior else None,
        current.block_id if current else None,
        section_key,
        _canonical_decimal(similarity) if similarity is not None else None,
        suppressed,
    )
    return AlignedComparison(
        comparison_id=comparison_id,
        relation=relation,
        prior_block_id=prior.block_id if prior else None,
        current_block_id=current.block_id if current else None,
        prior_section_id=prior.section_id if prior else None,
        current_section_id=current.section_id if current else None,
        section_key=section_key,
        similarity=_canonical_decimal(similarity) if similarity is not None else None,
        suppressed=suppressed,
    )


def _make_redline(
    comparison: AlignedComparison,
    prior_document: DisclosureDocument,
    current_document: DisclosureDocument,
    prior: DisclosureBlock | None,
    current: DisclosureBlock | None,
    registry: DisclosureDiffRegistry,
    *,
    parent_op_id: str | None = None,
) -> RedlineOp:
    if prior is not None and current is not None:
        ratio, count, numeric, edits = _change_stats(prior.text, current.text)
    elif prior is not None:
        words = _token_words(prior.text)
        ratio, count, numeric, edits = "1", len(words), bool(_NUMBER_RE.search(prior.text)), (
            _coarse_inline_edit("delete", prior.text, ""),
        )
    elif current is not None:
        words = _token_words(current.text)
        ratio, count, numeric, edits = "1", len(words), bool(_NUMBER_RE.search(current.text)), (
            _coarse_inline_edit("insert", "", current.text),
        )
    else:  # pragma: no cover - internal contract
        raise ValueError("redline requires prior or current block")
    operation = comparison.relation
    op_id = stable_id(
        "disclosure_redline",
        registry.version,
        comparison.comparison_id,
        operation,
        ratio,
        count,
        numeric,
        tuple(item.to_dict() for item in edits),
        parent_op_id,
    )
    return RedlineOp(
        op_id=op_id,
        operation=operation,
        comparison_id=comparison.comparison_id,
        section_key=comparison.section_key,
        prior_block_id=prior.block_id if prior else None,
        current_block_id=current.block_id if current else None,
        prior_receipt=prior_document.receipt_for_block(prior, excerpt_chars=registry.source_excerpt_chars) if prior else None,
        current_receipt=current_document.receipt_for_block(current, excerpt_chars=registry.source_excerpt_chars) if current else None,
        changed_token_ratio=ratio,
        changed_token_count=count,
        numeric_changed=numeric,
        inline_edits=edits,
        suppressed=comparison.suppressed,
        parent_op_id=parent_op_id,
    )


def _table_cell_redlines(
    parent: RedlineOp,
    prior_document: DisclosureDocument,
    current_document: DisclosureDocument,
    prior: DisclosureBlock,
    current: DisclosureBlock,
    registry: DisclosureDiffRegistry,
) -> tuple[RedlineOp, ...]:
    if prior.table is None or current.table is None:
        return ()
    rows: list[RedlineOp] = []
    for row_index, (old_row, new_row) in enumerate(zip(prior.table.rows, current.table.rows)):
        for column_index, (old_cell, new_cell) in enumerate(zip(old_row, new_row)):
            if old_cell.text == new_cell.text:
                continue
            ratio, count, numeric, edits = _change_stats(old_cell.text, new_cell.text)
            op_id = stable_id(
                "disclosure_table_cell_redline",
                registry.version,
                parent.op_id,
                row_index,
                column_index,
                old_cell.cell_id,
                new_cell.cell_id,
                ratio,
                tuple(item.to_dict() for item in edits),
            )
            rows.append(
                RedlineOp(
                    op_id=op_id,
                    operation="table_cell_changed",
                    comparison_id=parent.comparison_id,
                    section_key=parent.section_key,
                    prior_block_id=prior.block_id,
                    current_block_id=current.block_id,
                    prior_receipt=_receipt_for_cell(prior_document, prior, old_cell, registry),
                    current_receipt=_receipt_for_cell(current_document, current, new_cell, registry),
                    changed_token_ratio=ratio,
                    changed_token_count=count,
                    numeric_changed=numeric,
                    inline_edits=edits,
                    parent_op_id=parent.op_id,
                )
            )
    return tuple(rows)


def _compatible_for_fuzzy(prior: DisclosureBlock, current: DisclosureBlock) -> bool:
    if prior.kind is not current.kind:
        return False
    if prior.section_key == current.section_key:
        return True
    return bool(set(prior.topic_keys) & set(current.topic_keys))


@dataclass(frozen=True)
class _OrderedBlockIndex:
    blocks: tuple[DisclosureBlock, ...]
    source_orders: tuple[int, ...]
    positions: Mapping[str, int]

    @classmethod
    def build(cls, blocks: Iterable[DisclosureBlock]) -> _OrderedBlockIndex:
        ordered = tuple(sorted(blocks, key=lambda item: (item.source_order, item.block_id)))
        return cls(
            blocks=ordered,
            source_orders=tuple(item.source_order for item in ordered),
            positions={item.block_id: index for index, item in enumerate(ordered)},
        )

    def position_for(self, block_id: str) -> int | None:
        return self.positions.get(block_id)

    def neighborhood(self, target: float, radius: int) -> tuple[DisclosureBlock, ...]:
        if not self.blocks:
            return ()
        center = bisect_left(self.source_orders, target)
        low = max(0, center - radius)
        high = min(len(self.blocks), center + radius + 1)
        return self.blocks[low:high]


def _build_indexes(
    blocks: Iterable[DisclosureBlock],
) -> tuple[dict[tuple[BlockKind, str], _OrderedBlockIndex], dict[tuple[BlockKind, str], _OrderedBlockIndex]]:
    by_section: dict[tuple[BlockKind, str], list[DisclosureBlock]] = {}
    by_topic: dict[tuple[BlockKind, str], list[DisclosureBlock]] = {}
    for block in blocks:
        by_section.setdefault((block.kind, block.section_key), []).append(block)
        for topic in block.topic_keys:
            by_topic.setdefault((block.kind, topic), []).append(block)
    return (
        {key: _OrderedBlockIndex.build(items) for key, items in by_section.items()},
        {key: _OrderedBlockIndex.build(items) for key, items in by_topic.items()},
    )


def _position_scaled(old_index: int | None, old_count: int, current_index: _OrderedBlockIndex) -> float:
    if old_index is None or old_count <= 0 or not current_index.blocks:
        return 0.0
    # Source-order neighborhoods use the position within a comparable section or
    # topic, not global document offsets, so inserted tables do not explode the
    # candidate set for a later section.
    fraction = (old_index + 0.5) / old_count
    target_position = min(len(current_index.blocks) - 1, max(0, int(fraction * len(current_index.blocks))))
    return float(current_index.source_orders[target_position])


def _fingerprint_tokens(block: DisclosureBlock) -> frozenset[str]:
    source = block.table.matching_signature() if block.table else block.matching_text
    # Very short common words are poor anchors in SEC prose and cause false
    # cross-pairing.  They are intentionally excluded from the bounded index.
    return frozenset(token for token in _cached_word_tokens(source) if len(token) >= 3)


def _cheap_candidate_score(
    prior: DisclosureBlock,
    current: DisclosureBlock,
    token_cache: Mapping[str, frozenset[str]],
    token_lengths: Mapping[str, int],
) -> float | None:
    old_tokens = token_cache[prior.block_id]
    new_tokens = token_cache[current.block_id]
    if prior.kind is BlockKind.TABLE and prior.table and current.table:
        if prior.table.matching_signature() == current.table.matching_signature():
            return 2.0
    if not old_tokens or not new_tokens:
        return None
    shared = len(old_tokens & new_tokens)
    if not shared:
        return None
    union = len(old_tokens | new_tokens)
    jaccard = shared / union
    if jaccard < _MIN_FUZZY_TOKEN_JACCARD:
        return None
    old_size = max(1, token_lengths[prior.block_id])
    new_size = max(1, token_lengths[current.block_id])
    length_fit = min(old_size, new_size) / max(old_size, new_size)
    if length_fit < 0.20:
        return None
    return jaccard + length_fit * 0.10


def _bounded_fuzzy_candidates(
    prior_blocks: Iterable[DisclosureBlock],
    current_blocks: Iterable[DisclosureBlock],
) -> tuple[tuple[DisclosureBlock, DisclosureBlock], ...]:
    """Generate at most a small constant number of plausible pairs per block.

    Exact-content alignment happens before this path.  For the residual text,
    we only inspect nearby blocks in the same section or explicit shared topic,
    filter by cheap token/length fingerprints, and leave all ambiguous text as
    transparent added/removed records.  This is intentionally not an attempt to
    solve a global fuzzy matching problem for a full Inline XBRL document.
    """
    old_items = tuple(sorted(prior_blocks, key=lambda item: (item.source_order, item.block_id)))
    new_items = tuple(sorted(current_blocks, key=lambda item: (item.source_order, item.block_id)))
    old_sections, old_topics = _build_indexes(old_items)
    new_sections, new_topics = _build_indexes(new_items)
    token_cache = {item.block_id: _fingerprint_tokens(item) for item in (*old_items, *new_items)}
    token_lengths = {
        item.block_id: len(
            _cached_word_tokens(item.table.matching_signature() if item.table else item.matching_text)
        )
        for item in (*old_items, *new_items)
    }
    pairs: list[tuple[DisclosureBlock, DisclosureBlock]] = []
    for old in old_items:
        candidates: dict[str, tuple[DisclosureBlock, float]] = {}
        section_key = (old.kind, old.section_key)
        old_section = old_sections.get(section_key)
        new_section = new_sections.get(section_key)
        if old_section and new_section:
            target = _position_scaled(old_section.position_for(old.block_id), len(old_section.blocks), new_section)
            for new in new_section.neighborhood(target, _SECTION_NEIGHBORHOOD):
                candidates[new.block_id] = (new, abs(new.source_order - target))
        for topic in old.topic_keys:
            topic_key = (old.kind, topic)
            old_topic = old_topics.get(topic_key)
            new_topic = new_topics.get(topic_key)
            if old_topic is None or new_topic is None:
                continue
            target = _position_scaled(old_topic.position_for(old.block_id), len(old_topic.blocks), new_topic)
            for new in new_topic.neighborhood(target, _TOPIC_NEIGHBORHOOD):
                prior_choice = candidates.get(new.block_id)
                distance = abs(new.source_order - target)
                if prior_choice is None or distance < prior_choice[1]:
                    candidates[new.block_id] = (new, distance)
        scored: list[tuple[float, float, int, str, DisclosureBlock]] = []
        for new, distance in candidates.values():
            if not _compatible_for_fuzzy(old, new):
                continue
            score = _cheap_candidate_score(old, new, token_cache, token_lengths)
            if score is None:
                continue
            scored.append((-score, distance, new.source_order, new.block_id, new))
        for _, _, _, _, new in sorted(scored)[:_MAX_FUZZY_CANDIDATES_PER_BLOCK]:
            pairs.append((old, new))
    return tuple(pairs)


def _build_alignment(
    prior_document: DisclosureDocument,
    current_document: DisclosureDocument,
    registry: DisclosureDiffRegistry,
) -> tuple[tuple[AlignedComparison, ...], tuple[RedlineOp, ...]]:
    """Match exact text globally first, then same-topic structural edits.

    Matching exact content before fuzzy text is what prevents a moved paragraph
    from appearing as an unrelated deletion and insertion.
    """
    old_remaining = {item.block_id: item for item in prior_document.blocks}
    new_remaining = {item.block_id: item for item in current_document.blocks}
    aligned: list[tuple[AlignedComparison, DisclosureBlock | None, DisclosureBlock | None]] = []

    old_by_text: dict[str, list[DisclosureBlock]] = {}
    new_by_text: dict[str, list[DisclosureBlock]] = {}
    for block in prior_document.blocks:
        old_by_text.setdefault(_block_fingerprint(block), []).append(block)
    for block in current_document.blocks:
        new_by_text.setdefault(_block_fingerprint(block), []).append(block)
    for fingerprint in sorted(set(old_by_text) & set(new_by_text)):
        old_items = sorted(old_by_text[fingerprint], key=lambda item: (item.section_key, item.source_order, item.block_id))
        new_items = sorted(new_by_text[fingerprint], key=lambda item: (item.section_key, item.source_order, item.block_id))
        pairs: list[tuple[DisclosureBlock, DisclosureBlock]] = []
        available_new = list(new_items)
        for old in old_items:
            same_section = next((item for item in available_new if item.section_key == old.section_key), None)
            if same_section is not None:
                available_new.remove(same_section)
                pairs.append((old, same_section))
        remaining_old = [item for item in old_items if all(item.block_id != old.block_id for old, _ in pairs)]
        for old, new in zip(remaining_old, available_new):
            pairs.append((old, new))
        for old, new in sorted(pairs, key=lambda item: (item[0].source_order, item[1].source_order, item[0].block_id, item[1].block_id)):
            old_remaining.pop(old.block_id, None)
            new_remaining.pop(new.block_id, None)
            relation = "unchanged" if old.section_key == new.section_key else "moved"
            aligned.append((_make_comparison(relation, old, new, similarity=1.0, suppressed=False, engine_version=registry.version), old, new))

    candidates: list[tuple[float, str, int, int, DisclosureBlock, DisclosureBlock]] = []
    for old, new in _bounded_fuzzy_candidates(old_remaining.values(), new_remaining.values()):
        similarity = _block_similarity(old, new)
        threshold = 0.45 if old.kind is BlockKind.TABLE else 0.50
        if similarity >= threshold:
            candidates.append((-similarity, old.section_key, old.source_order, new.source_order, old, new))
    for negative_similarity, _, _, _, old, new in sorted(candidates, key=lambda item: (item[0], item[1], item[2], item[3], item[4].block_id, item[5].block_id)):
        if old.block_id not in old_remaining or new.block_id not in new_remaining:
            continue
        old_remaining.pop(old.block_id)
        new_remaining.pop(new.block_id)
        similarity = -negative_similarity
        suppressed = _is_boilerplate(old.text, registry) and _is_boilerplate(new.text, registry)
        relation = "suppressed_boilerplate" if suppressed else "modified"
        aligned.append((_make_comparison(relation, old, new, similarity=similarity, suppressed=suppressed, engine_version=registry.version), old, new))

    for old in sorted(old_remaining.values(), key=lambda item: (item.source_order, item.block_id)):
        suppressed = _is_boilerplate(old.text, registry)
        relation = "suppressed_boilerplate" if suppressed else "removed"
        aligned.append((_make_comparison(relation, old, None, similarity=None, suppressed=suppressed, engine_version=registry.version), old, None))
    for new in sorted(new_remaining.values(), key=lambda item: (item.source_order, item.block_id)):
        suppressed = _is_boilerplate(new.text, registry)
        relation = "suppressed_boilerplate" if suppressed else "added"
        aligned.append((_make_comparison(relation, None, new, similarity=None, suppressed=suppressed, engine_version=registry.version), None, new))

    aligned.sort(
        key=lambda item: (
            item[1].source_order if item[1] else 10**9,
            item[2].source_order if item[2] else 10**9,
            item[0].relation,
            item[0].comparison_id,
        )
    )
    comparisons = tuple(item[0] for item in aligned)
    redlines: list[RedlineOp] = []
    for comparison, old, new in aligned:
        redline = _make_redline(comparison, prior_document, current_document, old, new, registry)
        redlines.append(redline)
        if comparison.relation == "modified" and old is not None and new is not None:
            redlines.extend(_table_cell_redlines(redline, prior_document, current_document, old, new, registry))
    redlines.sort(key=lambda item: (item.parent_op_id or "", item.op_id))
    return comparisons, tuple(redlines)


def _blocks_for_topics(document: DisclosureDocument, topic_keys: Iterable[str]) -> tuple[DisclosureBlock, ...]:
    wanted = set(topic_keys)
    return tuple(
        block
        for block in document.blocks
        if block.section_key in wanted or bool(wanted & set(block.topic_keys))
    )


_LOCAL_HEADING_CONNECTORS = frozenset({"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"})
_LOCAL_HEADING_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_PAGE_CHROME_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z .,&-]*\|\s*)?20\d{2}\s+Form\s+10-[KQ]\s*\|\s*\d+",
    re.I,
)


def _looks_like_local_heading(text: str) -> bool:
    """Recognize short title-case note labels without reclassifying the corpus.

    Many Inline XBRL filings wrap subheadings such as ``Inventories`` in a
    styled paragraph.  They should bound a detector-local neighborhood, but
    promoting every title-cased phrase globally would overclassify prose.
    """
    compact = _compact_text(text)
    if not compact or len(compact) > 110 or len(compact.split()) > 12:
        return False
    if re.search(r"[.!?:;|%]", compact):
        return False
    words = _LOCAL_HEADING_WORD_RE.findall(compact)
    if not words or len(words) != len(compact.split()):
        return False
    return all(word[0].isupper() or word.casefold() in _LOCAL_HEADING_CONNECTORS for word in words)


def _is_page_chrome(text: str) -> bool:
    compact = _compact_text(text)
    return compact.casefold() == "table of contents" or _PAGE_CHROME_RE.fullmatch(compact) is not None


def _revenue_policy_scope_blocks(
    document: DisclosureDocument,
    spec: DisclosureDetectorSpec,
) -> tuple[DisclosureBlock, ...]:
    """Return a narrow policy scope by explicit block IDs, never inherited section.

    A legal filing can use a ``Revenue Recognition`` heading followed by
    hundreds of unrelated note blocks before another canonical SEC Item title.
    The normalizer deliberately preserves that structural inheritance for
    broad exploration, but the policy-change detector must be stricter: it
    admits only direct, versioned policy-rule hits and a small source-order
    neighborhood after an explicit policy heading.  A title-case subheading
    ends that neighborhood even when it was encoded as a paragraph in HTML.
    """
    direct_patterns = tuple(str(pattern) for pattern in spec.option("scope_direct_patterns", ()))
    heading_patterns = tuple(str(pattern) for pattern in spec.option("scope_heading_patterns", ()))
    try:
        neighbor_limit = int(spec.option("scope_heading_neighbor_limit", 8))
    except (TypeError, ValueError) as exc:
        raise ValueError("revenue policy scope_heading_neighbor_limit must be an integer") from exc
    if neighbor_limit < 0 or neighbor_limit > 24:
        raise ValueError("revenue policy scope_heading_neighbor_limit must be between 0 and 24")
    if not direct_patterns and not heading_patterns:
        return ()
    direct_rules = tuple(re.compile(pattern, re.I) for pattern in direct_patterns)
    heading_rules = tuple(re.compile(pattern, re.I) for pattern in heading_patterns)
    ordered = tuple(sorted(document.blocks, key=lambda block: (block.source_order, block.block_id)))
    selected: dict[str, DisclosureBlock] = {}
    for index, block in enumerate(ordered):
        if any(rule.search(block.text) is not None for rule in direct_rules):
            selected[block.block_id] = block
        is_anchor = (
            block.kind is BlockKind.HEADING
            and any(rule.fullmatch(_compact_text(block.text)) is not None for rule in heading_rules)
        )
        if not is_anchor:
            continue
        selected[block.block_id] = block
        if neighbor_limit == 0:
            continue
        admitted = 0
        for candidate in ordered[index + 1:]:
            if _is_page_chrome(candidate.text):
                continue
            if candidate.kind is BlockKind.HEADING or _looks_like_local_heading(candidate.text):
                break
            selected[candidate.block_id] = candidate
            admitted += 1
            if admitted >= neighbor_limit:
                break
    return tuple(sorted(selected.values(), key=lambda block: (block.source_order, block.block_id)))


def _section_ids(blocks: Iterable[DisclosureBlock]) -> tuple[str, ...]:
    return tuple(sorted({item.section_id for item in blocks}))


def _dedupe_receipts(receipts: Iterable[SourceReceipt]) -> tuple[SourceReceipt, ...]:
    deduped: dict[tuple[str, str | None, str | None, str | None, int, int], SourceReceipt] = {}
    for receipt in receipts:
        key = (
            receipt.accession,
            receipt.block_id,
            receipt.section_id,
            receipt.cell_id,
            receipt.source_span.char_start,
            receipt.source_span.char_end,
        )
        deduped[key] = receipt
    return tuple(
        sorted(
            deduped.values(),
            key=lambda item: (
                item.accession,
                item.source_span.char_start,
                item.source_span.char_end,
                item.block_id or "",
                item.cell_id or "",
            ),
        )
    )


def _review_level(state: DisclosureFindingState, applicability: Applicability) -> str:
    if state is DisclosureFindingState.TRIGGERED:
        return "manual_review"
    if applicability is Applicability.NOT_EVALUABLE:
        return "insufficient_evidence"
    if applicability is Applicability.NOT_APPLICABLE:
        return "not_applicable"
    return "no_review"


def _finding(
    spec: DisclosureDetectorSpec,
    comparison: DisclosureComparison | None,
    prior: DisclosureDocument,
    current: DisclosureDocument,
    *,
    state: DisclosureFindingState,
    applicability: Applicability,
    prior_blocks: Iterable[DisclosureBlock] = (),
    current_blocks: Iterable[DisclosureBlock] = (),
    receipts: Iterable[SourceReceipt] = (),
    why_flagged: Mapping[str, str | int | float] = (),
    extra_limitations: Iterable[str] = (),
) -> DisclosureFinding:
    old_blocks = tuple(prior_blocks)
    new_blocks = tuple(current_blocks)
    evidence = list(receipts)
    if not evidence:
        # Every outcome, including not-applicable and not-evaluable, points to
        # an actual supplied source rather than an invented absence receipt.
        evidence.extend((prior.document_receipt(), current.document_receipt()))
    why = tuple(sorted((str(key), str(value)) for key, value in dict(why_flagged).items()))
    limitations = tuple(sorted(set(spec.limitations) | {str(value) for value in extra_limitations}))
    evidence_tuple = _dedupe_receipts(evidence)
    review_level = _review_level(state, applicability)
    finding_id = stable_id(
        "disclosure_finding",
        spec.detector_id,
        spec.order,
        prior.document_id,
        current.document_id,
        state.value,
        applicability.value,
        tuple(item.block_id for item in old_blocks),
        tuple(item.block_id for item in new_blocks),
        tuple(item.to_dict() for item in evidence_tuple),
        why,
        limitations,
    )
    return DisclosureFinding(
        finding_id=finding_id,
        detector_id=spec.detector_id,
        detector_version=(comparison.engine_version if comparison is not None else "filing-disclosure-diff/v1"),
        label_key=spec.label_key,
        labels=spec.labels,
        state=state,
        applicability=applicability,
        priority=spec.priority,
        review_level=review_level,
        prior_accession=prior.accession,
        current_accession=current.accession,
        prior_section_ids=_section_ids(old_blocks),
        current_section_ids=_section_ids(new_blocks),
        evidence_receipts=evidence_tuple,
        why_flagged=why,
        benign_explanation=spec.benign_explanation,
        limitations=limitations,
    )


def _same_reporting_form(prior: DisclosureDocument, current: DisclosureDocument) -> bool:
    return _form_base(prior.form) == _form_base(current.form) and _form_base(prior.form) is not None


def _kpi_matches(
    document: DisclosureDocument,
    patterns: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[DisclosureBlock, ...]]:
    matches: dict[str, list[DisclosureBlock]] = {}
    for item in patterns:
        key = str(item["key"])
        pattern = str(item["pattern"])
        for block in document.blocks:
            if block.kind is BlockKind.HEADING or re.search(pattern, block.text, re.I) is None:
                continue
            # A word that happens to be present in descriptive prose is not a
            # KPI candidate until the same block carries a disclosed numeric value.
            if _NUMBER_RE.search(block.text) is None:
                continue
            matches.setdefault(key, []).append(block)
    return {key: tuple(sorted(value, key=lambda block: (block.source_order, block.block_id))) for key, value in matches.items()}


def _detect_kpi_disappearance(
    spec: DisclosureDetectorSpec,
    comparison: DisclosureComparison,
    registry: DisclosureDiffRegistry,
) -> DisclosureFinding:
    prior, current = comparison.prior, comparison.current
    if not _same_reporting_form(prior, current):
        return _finding(
            spec, comparison, prior, current,
            state=DisclosureFindingState.NOT_EVALUABLE,
            applicability=Applicability.NOT_EVALUABLE,
            why_flagged={"reason": "same_reporting_form_required"},
            extra_limitations=("cross_form_kpi_cadence_is_not_comparable",),
        )
    patterns = spec.option("kpi_patterns", ())
    prior_matches = _kpi_matches(prior, patterns)
    current_matches = _kpi_matches(current, patterns)
    if not prior_matches:
        return _finding(
            spec, comparison, prior, current,
            state=DisclosureFindingState.CLEAR,
            applicability=Applicability.NOT_APPLICABLE,
            why_flagged={"reason": "no_numeric_kpi_candidate_in_prior"},
        )
    missing = sorted(set(prior_matches) - set(current_matches))
    relevant_prior = tuple(block for key in missing for block in prior_matches[key])
    retained_prior = tuple(block for key in sorted(set(prior_matches) & set(current_matches)) for block in prior_matches[key])
    relevant_current = tuple(
        block for key in sorted(set(prior_matches) & set(current_matches)) for block in current_matches[key]
    )
    evidence: list[SourceReceipt] = [prior.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in relevant_prior]
    if missing:
        # Evidence the current search scope with a real section/block receipt.
        scope = _blocks_for_topics(current, ("mda", "business", "financial_statements"))
        if scope:
            evidence.append(current.receipt_for_block(scope[0], excerpt_chars=registry.source_excerpt_chars))
    else:
        evidence.extend(current.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in relevant_current)
    return _finding(
        spec, comparison, prior, current,
        state=DisclosureFindingState.TRIGGERED if missing else DisclosureFindingState.CLEAR,
        applicability=Applicability.APPLICABLE,
        prior_blocks=relevant_prior or retained_prior,
        current_blocks=relevant_current,
        receipts=evidence,
        why_flagged={
            "prior_kpi_keys": ",".join(sorted(prior_matches)),
            "current_kpi_keys": ",".join(sorted(current_matches)),
            "missing_kpi_keys": ",".join(missing),
            "missing_kpi_count": len(missing),
        },
        extra_limitations=("absence_is_measured_within_supplied_filing_text",),
    )


def _op_blocks(
    op: RedlineOp,
    prior_by_id: Mapping[str, DisclosureBlock],
    current_by_id: Mapping[str, DisclosureBlock],
) -> tuple[DisclosureBlock | None, DisclosureBlock | None]:
    return (
        prior_by_id.get(op.prior_block_id) if op.prior_block_id else None,
        current_by_id.get(op.current_block_id) if op.current_block_id else None,
    )


def _relevant_redlines(
    comparison: DisclosureComparison,
    section_or_topics: Iterable[str],
) -> tuple[RedlineOp, ...]:
    wanted = set(section_or_topics)
    prior_by_id = {block.block_id: block for block in comparison.prior.blocks}
    current_by_id = {block.block_id: block for block in comparison.current.blocks}
    selected: list[RedlineOp] = []
    for op in comparison.redline_ops:
        if op.parent_op_id is not None or op.suppressed or op.operation in {"unchanged", "moved"}:
            continue
        old, new = _op_blocks(op, prior_by_id, current_by_id)
        blocks = tuple(item for item in (old, new) if item is not None)
        if op.section_key in wanted or any(wanted & (set(item.topic_keys) | {item.section_key}) for item in blocks):
            selected.append(op)
    return tuple(sorted(selected, key=lambda item: item.op_id))


def _relevant_redlines_for_block_scope(
    comparison: DisclosureComparison,
    prior_blocks: Iterable[DisclosureBlock],
    current_blocks: Iterable[DisclosureBlock],
) -> tuple[RedlineOp, ...]:
    """Select top-level redlines only when a concrete scoped block participates."""
    prior_ids = {block.block_id for block in prior_blocks}
    current_ids = {block.block_id for block in current_blocks}
    selected = [
        op
        for op in comparison.redline_ops
        if op.parent_op_id is None
        and not op.suppressed
        and op.operation not in {"unchanged", "moved"}
        and (op.prior_block_id in prior_ids or op.current_block_id in current_ids)
    ]
    return tuple(sorted(selected, key=lambda item: item.op_id))


def _risk_factor_scope_blocks(document: DisclosureDocument) -> tuple[DisclosureBlock, ...]:
    """Return the concrete canonical risk section, not phrase hits elsewhere."""
    candidates = tuple(block for block in document.blocks if block.section_key == "risk_factors")
    if not candidates:
        return ()
    anchors = [
        block
        for block in candidates
        if block.kind is BlockKind.HEADING and _ITEM_HEADING_RE.match(block.text)
    ]
    if anchors:
        section_id = anchors[-1].section_id
    else:
        # A short-form or synthetic filing may title the section simply "Risk
        # Factors". Choose the largest concrete section instance so a TOC label
        # cannot outrank the actual disclosure body.
        counts = Counter(block.section_id for block in candidates)
        section_id = sorted(counts, key=lambda key: (-counts[key], key))[0]
    return tuple(block for block in candidates if block.section_id == section_id)


def _passes_change_floor(op: RedlineOp, spec: DisclosureDetectorSpec) -> bool:
    if op.operation in {"added", "removed"}:
        return op.changed_token_count >= int(spec.option("min_changed_tokens", 1))
    try:
        ratio = Decimal(op.changed_token_ratio or "0")
    except InvalidOperation:  # pragma: no cover - contract-bound caller
        ratio = Decimal("0")
    return ratio >= Decimal(str(spec.option("min_changed_token_ratio", "0"))) and op.changed_token_count >= int(spec.option("min_changed_tokens", 1))


def _detect_risk_wording_change(
    spec: DisclosureDetectorSpec,
    comparison: DisclosureComparison,
    registry: DisclosureDiffRegistry,
) -> DisclosureFinding:
    prior, current = comparison.prior, comparison.current
    old_blocks = _risk_factor_scope_blocks(prior)
    new_blocks = _risk_factor_scope_blocks(current)
    if not old_blocks or not new_blocks:
        return _finding(
            spec, comparison, prior, current,
            state=DisclosureFindingState.NOT_EVALUABLE,
            applicability=Applicability.NOT_EVALUABLE,
            prior_blocks=old_blocks,
            current_blocks=new_blocks,
            receipts=[
                *(prior.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in old_blocks[:1]),
                *(current.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in new_blocks[:1]),
            ],
            why_flagged={"reason": "risk_factor_section_missing", "prior_blocks": len(old_blocks), "current_blocks": len(new_blocks)},
        )
    changed = tuple(
        op
        for op in _relevant_redlines_for_block_scope(comparison, old_blocks, new_blocks)
        if _passes_change_floor(op, spec)
    )
    prior_by_id = {block.block_id: block for block in prior.blocks}
    current_by_id = {block.block_id: block for block in current.blocks}
    evidence: list[SourceReceipt] = []
    relevant_old: list[DisclosureBlock] = []
    relevant_new: list[DisclosureBlock] = []
    for op in changed:
        old, new = _op_blocks(op, prior_by_id, current_by_id)
        if old:
            relevant_old.append(old)
        if new:
            relevant_new.append(new)
        evidence.extend(item for item in (op.prior_receipt, op.current_receipt) if item is not None)
    if not evidence:
        evidence.extend((prior.receipt_for_block(old_blocks[0], excerpt_chars=registry.source_excerpt_chars), current.receipt_for_block(new_blocks[0], excerpt_chars=registry.source_excerpt_chars)))
    return _finding(
        spec, comparison, prior, current,
        state=DisclosureFindingState.TRIGGERED if changed else DisclosureFindingState.CLEAR,
        applicability=Applicability.APPLICABLE,
        prior_blocks=relevant_old or old_blocks[:1],
        current_blocks=relevant_new or new_blocks[:1],
        receipts=evidence,
        why_flagged={
            "changed_paragraph_count": len(changed),
            "min_changed_token_ratio": spec.option("min_changed_token_ratio", "0"),
            "min_changed_tokens": spec.option("min_changed_tokens", 0),
        },
    )


def _detect_revenue_policy_change(
    spec: DisclosureDetectorSpec,
    comparison: DisclosureComparison,
    registry: DisclosureDiffRegistry,
) -> DisclosureFinding:
    prior, current = comparison.prior, comparison.current
    old_blocks = _revenue_policy_scope_blocks(prior, spec)
    new_blocks = _revenue_policy_scope_blocks(current, spec)
    if not old_blocks and not new_blocks:
        return _finding(
            spec, comparison, prior, current,
            state=DisclosureFindingState.CLEAR,
            applicability=Applicability.NOT_APPLICABLE,
            why_flagged={"reason": "no_direct_revenue_policy_scope_detected"},
        )
    if not old_blocks or not new_blocks:
        return _finding(
            spec, comparison, prior, current,
            state=DisclosureFindingState.NOT_EVALUABLE,
            applicability=Applicability.NOT_EVALUABLE,
            prior_blocks=old_blocks,
            current_blocks=new_blocks,
            receipts=[
                *(prior.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in old_blocks[:1]),
                *(current.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in new_blocks[:1]),
            ],
            why_flagged={
                "reason": "policy_disclosure_missing_in_one_filing",
                "prior_scoped_block_count": len(old_blocks),
                "current_scoped_block_count": len(new_blocks),
            },
            extra_limitations=("policy_scope_uses_direct_rules_and_bounded_heading_neighbors",),
        )
    changed = tuple(
        op
        for op in _relevant_redlines_for_block_scope(comparison, old_blocks, new_blocks)
        if _passes_change_floor(op, spec)
    )
    prior_by_id = {block.block_id: block for block in prior.blocks}
    current_by_id = {block.block_id: block for block in current.blocks}
    relevant_old: list[DisclosureBlock] = []
    relevant_new: list[DisclosureBlock] = []
    evidence: list[SourceReceipt] = []
    for op in changed:
        old, new = _op_blocks(op, prior_by_id, current_by_id)
        if old:
            relevant_old.append(old)
        if new:
            relevant_new.append(new)
        evidence.extend(item for item in (op.prior_receipt, op.current_receipt) if item is not None)
    if not evidence:
        evidence.extend((prior.receipt_for_block(old_blocks[0], excerpt_chars=registry.source_excerpt_chars), current.receipt_for_block(new_blocks[0], excerpt_chars=registry.source_excerpt_chars)))
    return _finding(
        spec, comparison, prior, current,
        state=DisclosureFindingState.TRIGGERED if changed else DisclosureFindingState.CLEAR,
        applicability=Applicability.APPLICABLE,
        prior_blocks=relevant_old or old_blocks[:1],
        current_blocks=relevant_new or new_blocks[:1],
        receipts=evidence,
        why_flagged={
            "changed_policy_block_count": len(changed),
            "min_changed_token_ratio": spec.option("min_changed_token_ratio", "0"),
            "min_changed_tokens": spec.option("min_changed_tokens", 0),
            "prior_scoped_block_count": len(old_blocks),
            "current_scoped_block_count": len(new_blocks),
        },
        extra_limitations=("policy_scope_uses_direct_rules_and_bounded_heading_neighbors",),
    )


def _auditor_candidates(
    document: DisclosureDocument,
    registry: DisclosureDiffRegistry,
) -> tuple[tuple[str, DisclosureBlock], ...]:
    scoped = _blocks_for_topics(document, ("auditor_report", "auditor"))
    if not scoped:
        scoped = document.blocks
    candidates: list[tuple[str, DisclosureBlock]] = []
    for block in scoped:
        for match in re.finditer(registry.auditor_pattern, block.text, re.I):
            firm = _compact_text(match.group(0))
            # Generic legal suffixes are not firms on their own.
            if re.fullmatch(r"(?:llp|p\.c\.|pllc)", firm, re.I):
                continue
            canonical = re.sub(r"[^a-z0-9]", "", firm.casefold())
            candidates.append((canonical, block))
    unique: dict[tuple[str, str], tuple[str, DisclosureBlock]] = {}
    for canonical, block in candidates:
        unique[(canonical, block.block_id)] = (canonical, block)
    return tuple(sorted(unique.values(), key=lambda item: (item[0], item[1].source_order, item[1].block_id)))


def _detect_auditor_change(
    spec: DisclosureDetectorSpec,
    comparison: DisclosureComparison,
    registry: DisclosureDiffRegistry,
) -> DisclosureFinding:
    prior, current = comparison.prior, comparison.current
    old_candidates = _auditor_candidates(prior, registry)
    new_candidates = _auditor_candidates(current, registry)
    if not old_candidates or not new_candidates:
        old_blocks = tuple(block for _, block in old_candidates)
        new_blocks = tuple(block for _, block in new_candidates)
        return _finding(
            spec, comparison, prior, current,
            state=DisclosureFindingState.NOT_EVALUABLE,
            applicability=Applicability.NOT_EVALUABLE,
            prior_blocks=old_blocks,
            current_blocks=new_blocks,
            receipts=[
                *(prior.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in old_blocks[:1]),
                *(current.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in new_blocks[:1]),
            ],
            why_flagged={"reason": "auditor_firm_not_extracted", "prior_candidate_count": len(old_candidates), "current_candidate_count": len(new_candidates)},
        )
    old_firm, old_block = old_candidates[0]
    new_firm, new_block = new_candidates[0]
    return _finding(
        spec, comparison, prior, current,
        state=DisclosureFindingState.TRIGGERED if old_firm != new_firm else DisclosureFindingState.CLEAR,
        applicability=Applicability.APPLICABLE,
        prior_blocks=(old_block,),
        current_blocks=(new_block,),
        receipts=(
            prior.receipt_for_block(old_block, excerpt_chars=registry.source_excerpt_chars),
            current.receipt_for_block(new_block, excerpt_chars=registry.source_excerpt_chars),
        ),
        why_flagged={"prior_auditor": old_firm, "current_auditor": new_firm, "firm_changed": str(old_firm != new_firm).lower()},
    )


def _sentences(value: str) -> tuple[str, ...]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", _compact_text(value))
    return tuple(chunk for chunk in chunks if chunk)


def _icfr_status(blocks: Iterable[DisclosureBlock]) -> str:
    text = " ".join(block.text for block in blocks)
    sentences = _sentences(text)
    positive_weakness = False
    for sentence in sentences:
        if re.search(r"\bmaterial weakness(?:es)?\b", sentence, re.I) is None:
            continue
        negated = re.search(
            r"\b(?:no|not|none|without|did not identify|has not identified|have not identified)\b.{0,64}\bmaterial weakness(?:es)?\b",
            sentence,
            re.I,
        )
        if negated is None:
            positive_weakness = True
            break
    if positive_weakness:
        return "material_weakness"
    if re.search(r"\b(?:not effective|ineffective)\b", text, re.I):
        return "ineffective"
    if re.search(r"\beffective\b", text, re.I):
        return "effective"
    return "unknown"


def _detect_icfr_change(
    spec: DisclosureDetectorSpec,
    comparison: DisclosureComparison,
    registry: DisclosureDiffRegistry,
) -> DisclosureFinding:
    prior, current = comparison.prior, comparison.current
    old_blocks = _blocks_for_topics(prior, ("controls", "icfr"))
    new_blocks = _blocks_for_topics(current, ("controls", "icfr"))
    if not old_blocks or not new_blocks:
        return _finding(
            spec, comparison, prior, current,
            state=DisclosureFindingState.NOT_EVALUABLE,
            applicability=Applicability.NOT_EVALUABLE,
            prior_blocks=old_blocks,
            current_blocks=new_blocks,
            receipts=[
                *(prior.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in old_blocks[:2]),
                *(current.receipt_for_block(block, excerpt_chars=registry.source_excerpt_chars) for block in new_blocks[:2]),
            ],
            why_flagged={"reason": "icfr_controls_disclosure_missing", "prior_blocks": len(old_blocks), "current_blocks": len(new_blocks)},
        )
    prior_status = _icfr_status(old_blocks)
    current_status = _icfr_status(new_blocks)
    return _finding(
        spec, comparison, prior, current,
        state=DisclosureFindingState.TRIGGERED if prior_status != current_status else DisclosureFindingState.CLEAR,
        applicability=Applicability.APPLICABLE,
        prior_blocks=old_blocks,
        current_blocks=new_blocks,
        receipts=(
            prior.receipt_for_block(old_blocks[0], excerpt_chars=registry.source_excerpt_chars),
            current.receipt_for_block(new_blocks[0], excerpt_chars=registry.source_excerpt_chars),
        ),
        why_flagged={"prior_icfr_status": prior_status, "current_icfr_status": current_status, "status_changed": str(prior_status != current_status).lower()},
    )


def evaluate_disclosure_detectors(
    comparison: DisclosureComparison,
    registry: DisclosureDiffRegistry,
) -> tuple[DisclosureFinding, ...]:
    """Evaluate the fixed disclosure detector pack with explicit null states."""
    handlers = {
        "kpi_disappearance": _detect_kpi_disappearance,
        "risk_factor_wording_change": _detect_risk_wording_change,
        "revenue_recognition_policy_change": _detect_revenue_policy_change,
        "auditor_change": _detect_auditor_change,
        "icfr_material_weakness_change": _detect_icfr_change,
    }
    findings: list[DisclosureFinding] = []
    for spec in registry.detectors:
        try:
            handler = handlers[spec.detector_id]
        except KeyError as exc:
            raise ValueError(f"unknown disclosure detector: {spec.detector_id}") from exc
        findings.append(handler(spec, comparison, registry))
    return tuple(sorted(findings, key=lambda item: item.detector_id))


def _apply_metadata(document: Mapping[str, Any], metadata: Mapping[str, Any] | None, side: str) -> dict[str, Any]:
    """Fill only missing, shared metadata; supplied filing fields always win."""
    output = dict(document)
    if not metadata:
        return output
    for key in ("entity_cik", "source_url", "form", "filed_at", "report_date"):
        side_key = f"{side}_{key}"
        if not output.get(key) and metadata.get(side_key) is not None:
            output[key] = metadata[side_key]
        elif not output.get(key) and metadata.get(key) is not None:
            output[key] = metadata[key]
    return output


def compare_filings(
    prior_document: Mapping[str, Any],
    current_document: Mapping[str, Any],
    *,
    registry: DisclosureDiffRegistry | Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    include_source_text: bool = False,
    max_source_chars: int | None = None,
) -> DisclosureComparison:
    """Return a JSON-serializable, reproducible redline between two supplied filings.

    The engine reads no network and depends only on the two input bodies plus a
    versioned local registry. ``metadata`` may supply shared filing metadata
    when it is absent from an input, but cannot overwrite explicit input values.
    Source bodies stay out of the default serialization; use ``to_dict`` with
    ``include_source_text=True`` for a bounded debugging/export view.
    """
    config = (
        load_disclosure_diff_registry()
        if registry is None
        else registry_from_dict(registry) if isinstance(registry, Mapping) else registry
    )
    if max_source_chars is not None and max_source_chars < 0:
        raise ValueError("max_source_chars must be non-negative")
    embedded_source_limit = (
        min(config.max_embedded_source_chars, max_source_chars)
        if max_source_chars is not None
        else config.max_embedded_source_chars
    )
    prior = normalize_filing(_apply_metadata(prior_document, metadata, "prior"), registry=config)
    current = normalize_filing(_apply_metadata(current_document, metadata, "current"), registry=config)
    comparisons, redlines = _build_alignment(prior, current, config)
    provisional_id = stable_id(
        "disclosure_comparison",
        config.version,
        prior.document_id,
        current.document_id,
        tuple(item.comparison_id for item in comparisons),
        tuple(item.op_id for item in redlines),
    )
    provisional = DisclosureComparison(
        comparison_id=provisional_id,
        schema=DISCLOSURE_DIFF_SCHEMA,
        engine_version=config.version,
        prior=prior,
        current=current,
        comparisons=comparisons,
        redline_ops=redlines,
        findings=(),
        limitations=(
            "deterministic_source_text_only",
            "no_legal_materiality_determination",
            "no_economic_outcome_or_management_motive_inference",
            "section_and_entity_extraction_are_pattern_based",
        ),
        include_source_text=include_source_text,
        max_source_chars=embedded_source_limit,
    )
    findings = evaluate_disclosure_detectors(provisional, config)
    comparison_id = stable_id(
        "disclosure_comparison",
        config.version,
        prior.document_id,
        current.document_id,
        tuple(item.comparison_id for item in comparisons),
        tuple(item.op_id for item in redlines),
        tuple(item.finding_id for item in findings),
    )
    return DisclosureComparison(
        comparison_id=comparison_id,
        schema=DISCLOSURE_DIFF_SCHEMA,
        engine_version=config.version,
        prior=prior,
        current=current,
        comparisons=comparisons,
        redline_ops=redlines,
        findings=findings,
        limitations=provisional.limitations,
        include_source_text=include_source_text,
        max_source_chars=embedded_source_limit,
    )


__all__ = [
    "Applicability",
    "BlockKind",
    "DISCLOSURE_DIFF_SCHEMA",
    "DisclosureComparison",
    "DisclosureDiffRegistry",
    "DisclosureFinding",
    "DisclosureFindingState",
    "SourceReceipt",
    "SourceSpan",
    "compare_filings",
    "evaluate_disclosure_detectors",
    "load_disclosure_diff_registry",
    "normalize_filing",
    "registry_from_dict",
]
