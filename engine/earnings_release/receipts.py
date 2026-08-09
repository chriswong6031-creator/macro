"""Byte-replayable span receipts over a supplied release body.

The discipline is copied from ``engine.earnings_narrative.contracts``
(``_RECEIPT_KEYS`` / ``receipt_for_span``): a receipt is only worth storing if a
later reader can re-open the original bytes, re-slice them, re-hash them, and
get the same answer.  ``receipt_for_literal`` therefore replays every receipt it
mints **before returning it**, so an unreplayable receipt can never leave this
module.

Why a second receipt type rather than reusing the transcript one: the transcript
receipt is segment-indexed (``segment_index`` into a JSON body's segment list).
A filing body is one flat document, and
``engine.fundamental_forensics.disclosure_diff`` already supplies exact
character/byte coordinates into it.  The invariants are the same; the coordinate
space is not.

The receipt binds the FIGURE, not merely some bytes.  Replay checks four things
in order, and any one of them failing raises:

1. the whole source still hashes to ``source_sha256``;
2. the byte slice still hashes to ``span_sha256``;
3. the slice still decodes to exactly ``span_text``;
4. the slice still yields ``value_text`` after the same deterministic
   normalization the extractor used.

Check 4 is what makes a one-digit tamper fail rather than merely shift.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html as _html
import re
from typing import Any, Mapping

RECEIPT_SCHEMA = "earnings_release.span_receipt/v1"

RECEIPT_KEYS = frozenset({
    "schema", "source_sha256", "char_start", "char_end", "byte_start", "byte_end",
    "span_sha256", "span_bytes", "span_text", "value_text", "value_text_sha256",
})

_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")
# U+00A0 NO-BREAK SPACE arrives as &#160; in every EDGAR table cell; U+200B
# ZERO WIDTH SPACE is EDGAR's typesetting spacer and must not survive into a
# compared value.
_INVISIBLE = str.maketrans({" ": " ", "​": "", " ": " ", "﻿": ""})


class ReceiptError(ValueError):
    """A receipt could not be minted from the supplied coordinates."""


class ReceiptReplayError(ReceiptError):
    """A stored receipt does not reproduce against the source it names."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def visible_text(markup: str) -> str:
    """Strip tags, resolve entities, normalize invisible space — deterministically.

    This is the ONLY normalization a receipt replay is allowed to apply, so that
    "the bytes still say the same number" is a checkable statement rather than a
    negotiable one.
    """
    text = _TAG_RE.sub(" ", markup)
    text = _html.unescape(text)
    text = text.translate(_INVISIBLE)
    return _WS_RE.sub(" ", text).strip()


@dataclass(frozen=True)
class SpanReceipt:
    """Exact source coordinates plus everything needed to prove them again."""

    source_sha256: str
    char_start: int
    char_end: int
    byte_start: int
    byte_end: int
    span_sha256: str
    span_bytes: int
    span_text: str
    value_text: str
    value_text_sha256: str
    schema: str = RECEIPT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_sha256": self.source_sha256,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "span_sha256": self.span_sha256,
            "span_bytes": self.span_bytes,
            "span_text": self.span_text,
            "value_text": self.value_text,
            "value_text_sha256": self.value_text_sha256,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SpanReceipt:
        if not isinstance(payload, Mapping):
            raise ReceiptError("receipt must be a mapping")
        actual = set(payload)
        if actual != RECEIPT_KEYS:
            missing = sorted(RECEIPT_KEYS - actual)
            unknown = sorted(actual - RECEIPT_KEYS)
            raise ReceiptError(
                f"receipt fields mismatch (missing={missing}, unsupported={unknown})"
            )
        if payload["schema"] != RECEIPT_SCHEMA:
            raise ReceiptError(f"unsupported receipt schema {payload['schema']!r}")
        return cls(
            source_sha256=str(payload["source_sha256"]),
            char_start=int(payload["char_start"]),
            char_end=int(payload["char_end"]),
            byte_start=int(payload["byte_start"]),
            byte_end=int(payload["byte_end"]),
            span_sha256=str(payload["span_sha256"]),
            span_bytes=int(payload["span_bytes"]),
            span_text=str(payload["span_text"]),
            value_text=str(payload["value_text"]),
            value_text_sha256=str(payload["value_text_sha256"]),
        )


def replay_receipt(receipt: SpanReceipt | Mapping[str, Any], *, source: str) -> str:
    """Re-derive every hash and re-slice the bytes.  Raise on any disagreement.

    Returns the replayed ``value_text`` so a caller cannot "verify" a receipt
    and then go on using a different string.
    """
    row = receipt if isinstance(receipt, SpanReceipt) else SpanReceipt.from_dict(receipt)

    encoded = source.encode("utf-8")
    if sha256_bytes(encoded) != row.source_sha256:
        raise ReceiptReplayError(
            "source_sha256 does not match the supplied source — the receipt "
            "belongs to a different document revision"
        )
    if row.byte_start < 0 or row.byte_end < row.byte_start or row.byte_end > len(encoded):
        raise ReceiptReplayError("byte span is outside the source")
    if row.byte_end - row.byte_start != row.span_bytes:
        raise ReceiptReplayError("span_bytes disagrees with the byte span")

    slice_bytes = encoded[row.byte_start:row.byte_end]
    if sha256_bytes(slice_bytes) != row.span_sha256:
        raise ReceiptReplayError("span_sha256 mismatch — the source bytes changed")
    try:
        slice_text = slice_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - guarded by char alignment
        raise ReceiptReplayError("byte span does not start on a character boundary") from exc
    if slice_text != row.span_text:
        raise ReceiptReplayError("span_text mismatch — the source bytes changed")

    # Character coordinates are an aid for humans and for narrowing; they must
    # still agree with the authoritative byte coordinates.
    if source[row.char_start:row.char_end] != row.span_text:
        raise ReceiptReplayError("char span and byte span disagree")

    replayed_value = visible_text(slice_text)
    if replayed_value != row.value_text:
        raise ReceiptReplayError(
            f"replayed value {replayed_value!r} does not match the receipt's "
            f"{row.value_text!r} — the figure at this location changed"
        )
    if sha256_text(replayed_value) != row.value_text_sha256:
        raise ReceiptReplayError("value_text_sha256 mismatch")
    return replayed_value


def byte_offsets(source: str, char_start: int, char_end: int) -> tuple[int, int]:
    """UTF-8 byte offsets for a code-point range."""
    return (
        len(source[:char_start].encode("utf-8")),
        len(source[:char_end].encode("utf-8")),
    )


def receipt_for_char_span(
    *,
    source: str,
    source_sha256: str,
    char_start: int,
    char_end: int,
) -> SpanReceipt:
    """Mint a receipt for an exact code-point range and replay it before returning."""
    if char_start < 0 or char_end < char_start or char_end > len(source):
        raise ReceiptError("char span is outside the source")
    span_text = source[char_start:char_end]
    byte_start, byte_end = byte_offsets(source, char_start, char_end)
    value_text = visible_text(span_text)
    receipt = SpanReceipt(
        source_sha256=source_sha256,
        char_start=char_start,
        char_end=char_end,
        byte_start=byte_start,
        byte_end=byte_end,
        span_sha256=sha256_text(span_text),
        span_bytes=byte_end - byte_start,
        span_text=span_text,
        value_text=value_text,
        value_text_sha256=sha256_text(value_text),
    )
    # Non-negotiable: a receipt that cannot be replayed never leaves this module.
    replay_receipt(receipt, source=source)
    return receipt


def mask_markup(window: str) -> str:
    """Blank every tag to same-length spaces, preserving character offsets.

    Without this, locating the literal ``2.18`` inside one EDGAR table cell can
    land inside ``<td style="width:2.18%">`` — real EX-99.1 markup carries
    percentage column widths on every cell, so a bare substring search points
    the receipt at a stylesheet instead of at the figure.  Masking rather than
    stripping keeps offsets aligned with the untouched source.
    """
    return _TAG_RE.sub(lambda match: " " * len(match.group(0)), window)


def receipt_for_literal(
    *,
    source: str,
    source_sha256: str,
    search_start: int,
    search_end: int,
    literal: str,
) -> SpanReceipt:
    """Mint a receipt for the UNIQUE occurrence of ``literal`` inside a window.

    The search ignores markup (see ``mask_markup``) and requires uniqueness.
    Uniqueness is required, not preferred: if the literal appears twice inside
    the window there is no fact of the matter about which one the extractor
    read, and a receipt pointing at "one of them" is not evidence — the caller
    is expected to turn the ``ReceiptError`` into a typed absence.
    """
    if not literal:
        raise ReceiptError("cannot locate an empty literal")
    if search_start < 0 or search_end < search_start or search_end > len(source):
        raise ReceiptError("search window is outside the source")
    window = mask_markup(source[search_start:search_end])
    first = window.find(literal)
    if first < 0:
        raise ReceiptError(f"literal {literal!r} does not occur in the window")
    if window.find(literal, first + 1) >= 0:
        raise ReceiptError(
            f"literal {literal!r} occurs more than once in the window — "
            "ambiguous location, refusing to mint a receipt"
        )
    char_start = search_start + first
    return receipt_for_char_span(
        source=source,
        source_sha256=source_sha256,
        char_start=char_start,
        char_end=char_start + len(literal),
    )


__all__ = [
    "RECEIPT_KEYS",
    "RECEIPT_SCHEMA",
    "ReceiptError",
    "ReceiptReplayError",
    "SpanReceipt",
    "byte_offsets",
    "mask_markup",
    "receipt_for_char_span",
    "receipt_for_literal",
    "replay_receipt",
    "sha256_bytes",
    "sha256_text",
    "visible_text",
]
