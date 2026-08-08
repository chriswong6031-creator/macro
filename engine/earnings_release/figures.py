"""Deterministic figure extraction from an earnings release body.

NO MODEL, NO INFERENCE.  Every number this module emits was read out of an exact
source location, and every number it declines to emit is reported as a **typed
absence** carrying the reason.  The governing law is handoff §Wave 1.5, restated
by the contract freeze: *a number without basis, units, period, and source is
ABSENT, not guessed.*

That is a deliberately expensive rule and it is the point.  Concretely:

* **Basis is never defaulted.**  A figure is ``gaap`` only under a caption that
  says so — the condensed consolidated statements are, by their own heading, the
  GAAP financial statements — or ``non_gaap`` under an explicit
  ``non-GAAP`` / ``adjusted`` / ``reconciliation`` signal.  A number under
  neither lands as ``basis_undeclared``.  Defaulting EPS to GAAP is exactly how
  an adjusted print gets compared against a GAAP estimate.
* **Currency is read off the column, not assumed.**  These statements typeset
  ``$`` on the first and total lines of a column only, so the first currency
  symbol seen in a column governs that column.  A column that never declares one
  lands as ``currency_undeclared``.
* **Per-share rows do not inherit the table's scale.**  ``(In millions)`` on the
  statement caption does not make ``$2.18`` two million dollars.  The bare
  ``Basic`` / ``Diluted`` labels are also scope-gated: the identical labels
  appear under ``Shares used in computing earnings per share``, where the value
  is a share count.  Reading that row as EPS is a real, shipped-elsewhere bug
  class, so the scope test is mandatory rather than a nicety.
* **An absence carries no value field at all**, so it cannot be read as zero.

Output is ``context_only``.  Nothing here ranks, sizes, gates or escalates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Any, Iterable, Mapping, Sequence

from engine.fundamental_forensics.disclosure_diff import (
    BlockKind,
    DisclosureBlock,
    DisclosureDocument,
    TableCell,
)

from .receipts import ReceiptError, SpanReceipt, receipt_for_literal

FIGURES_SCHEMA = "earnings_release.figures/v1"
AUTHORITY = "context_only"


class Basis(str, Enum):
    GAAP = "gaap"
    NON_GAAP = "non_gaap"


class ValueKind(str, Enum):
    MONETARY = "monetary"
    PER_SHARE = "per_share"
    PERCENT = "percent"


class AbsenceReason(str, Enum):
    """Why a figure is absent.  Every value here is a *finding*, not an error."""

    CONCEPT_NOT_PRESENT = "concept_not_present"
    BASIS_UNDECLARED = "basis_undeclared"
    UNITS_UNDECLARED = "units_undeclared"
    CURRENCY_UNDECLARED = "currency_undeclared"
    PERIOD_UNDECLARED = "period_undeclared"
    VALUE_AMBIGUOUS = "value_ambiguous"
    RECEIPT_NOT_REPLAYABLE = "receipt_not_replayable"


# The roster is what "absent" is measured against.  Without a declared roster,
# silence and absence are indistinguishable and a coverage number means nothing.
CONCEPT_ROSTER: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "gross_margin_pct",
    "operating_income",
    "net_income",
    "eps_basic",
    "eps_diluted",
    "operating_cash_flow",
    "capital_expenditures",
    "guidance_revenue_low",
    "guidance_revenue_high",
)

_UNIT_BY_SCALE = {
    "thousands": "usd_thousands",
    "millions": "usd_millions",
    "billions": "usd_billions",
}
_SCALE_FACTOR = {"usd_thousands": 1e3, "usd_millions": 1e6, "usd_billions": 1e9}

_UNITS_CAPTION_RE = re.compile(
    r"\b(?:in|dollars in|amounts in|figures in)\s+(thousands|millions|billions)\b", re.I
)
_CURRENCY_WORD_RE = re.compile(r"\b(?:U\.?S\.?\s+dollars|US\$|USD)\b", re.I)
_CURRENCY_SYMBOL = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}

# A GAAP statement says so in its own caption.  This is reading the document,
# not assuming a default.
_GAAP_CAPTION_RE = re.compile(
    r"condensed\s+consolidated\s+(?:statements?|balance)|"
    r"consolidated\s+statements?\s+of\s+(?:operations|income|cash\s+flows)|"
    r"\bU\.?S\.?\s+GAAP\b|\bGAAP\s+(?:results|measures|basis)\b",
    re.I,
)
_NON_GAAP_CAPTION_RE = re.compile(
    r"non-?GAAP|reconciliation\s+of\s+|\badjusted\s+(?:results|measures|basis)\b", re.I
)
_NON_GAAP_INLINE_RE = re.compile(r"non-?GAAP|\badjusted\b", re.I)

_NUMERIC_CELL_RE = re.compile(r"\A\(?-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?\Z")
_BARE_NUMERIC_RE = re.compile(r"\A\(?-?\d+(?:\.\d+)?\)?%?\Z")
_FOOTNOTE_CELL_RE = re.compile(r"\A\(\d{1,2}\)\Z")
_FOOTNOTE_SUFFIX_RE = re.compile(r"\s*\(\d{1,2}\)\s*\Z")
_DATE_CELL_RE = re.compile(
    r"\A(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),?\s+(\d{4})\Z",
    re.I,
)
_PERIOD_PREFIX_RE = re.compile(
    r"\b(?:three|six|nine|twelve|three-?month|first|second|third|fourth)\b.*\b"
    r"(?:month|quarter|year)s?\b.*\b(?:ended|ending)\b|"
    r"\b(?:month|quarter|year)s?\s+(?:ended|ending)\b",
    re.I,
)
_SEGMENT_SCOPE_RE = re.compile(r"by\s+(?:reportable\s+)?segment|segment\s+(?:results|revenue)", re.I)
_SHARE_COUNT_SCOPE_RE = re.compile(r"shares\s+used|weighted[- ]average\s+shares", re.I)
_PER_SHARE_SCOPE_RE = re.compile(r"per\s+(?:common\s+)?share", re.I)
_TOTAL_LABEL_RE = re.compile(r"\Atotal\b", re.I)

_GUIDANCE_SENTENCE_RE = re.compile(
    r"\b(?:expect|expects|expecting|guidance|outlook|anticipat\w*|forecast\w*|"
    r"we\s+are\s+guiding|guiding)\b",
    re.I,
)
_GUIDANCE_RANGE_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(billion|million|thousand)?\s*"
    r"(?:to|through|[-–—])\s*"
    r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(billion|million|thousand)?",
    re.I,
)
_GUIDANCE_PERIOD_RE = re.compile(
    r"\b(?:for|in)\s+(?:the\s+)?(?:(first|second|third|fourth|next|current)\s+)?"
    r"(?:fiscal\s+)?(quarter|year)\b(?:\s+(?:of\s+)?(?:fiscal\s+)?(\d{4}))?",
    re.I,
)
_GUIDANCE_MAGNITUDE = {"thousand": "usd_thousands", "million": "usd_millions", "billion": "usd_billions"}


@dataclass(frozen=True)
class _RowRule:
    """A label pattern and what concept it produces for each observed kind."""

    pattern: re.Pattern[str]
    kind_to_concept: Mapping[str, str]
    scope_required: re.Pattern[str] | None = None
    scope_forbidden: re.Pattern[str] | None = None


_ROW_RULES: tuple[_RowRule, ...] = (
    _RowRule(
        re.compile(r"\A(?:total\s+)?(?:net\s+)?(?:sales|revenues?)\Z", re.I),
        {ValueKind.MONETARY.value: "revenue"},
    ),
    _RowRule(
        re.compile(r"\Agross\s+(?:margin|profit)(?:\s+percentage|\s+%)?\Z", re.I),
        {ValueKind.MONETARY.value: "gross_profit", ValueKind.PERCENT.value: "gross_margin_pct"},
    ),
    _RowRule(
        re.compile(r"\A(?:total\s+)?operating\s+(?:income|margin)\Z|\Aincome\s+from\s+operations\Z", re.I),
        {ValueKind.MONETARY.value: "operating_income", ValueKind.PERCENT.value: "operating_margin_pct"},
    ),
    _RowRule(
        re.compile(r"\Anet\s+(?:income|loss)(?:\s*\(loss\))?\Z", re.I),
        {ValueKind.MONETARY.value: "net_income"},
    ),
    _RowRule(
        re.compile(
            r"\A(?:net\s+)?cash\s+(?:generated\s+by|provided\s+by|from|used\s+in)\s+"
            r"operating\s+activities\Z",
            re.I,
        ),
        {ValueKind.MONETARY.value: "operating_cash_flow"},
    ),
    _RowRule(
        re.compile(
            r"\A(?:payments\s+for\s+)?(?:acquisition\s+of\s+|purchases?\s+of\s+)?"
            r"(?:property,?\s+plant\s+and\s+equipment|property\s+and\s+equipment|"
            r"capital\s+expenditures)\Z",
            re.I,
        ),
        {ValueKind.MONETARY.value: "capital_expenditures"},
    ),
    # Bare Basic/Diluted: valid ONLY under a per-share scope and never under a
    # share-count scope, where the identical labels carry share counts.
    _RowRule(
        re.compile(r"\Abasic\Z", re.I),
        {ValueKind.PER_SHARE.value: "eps_basic"},
        scope_required=_PER_SHARE_SCOPE_RE,
        scope_forbidden=_SHARE_COUNT_SCOPE_RE,
    ),
    _RowRule(
        re.compile(r"\Adiluted\Z", re.I),
        {ValueKind.PER_SHARE.value: "eps_diluted"},
        scope_required=_PER_SHARE_SCOPE_RE,
        scope_forbidden=_SHARE_COUNT_SCOPE_RE,
    ),
    _RowRule(
        re.compile(
            r"\A(?:adjusted\s+|non-?GAAP\s+)?basic\s+(?:net\s+)?"
            r"(?:income|earnings|loss)\s+per\s+(?:common\s+)?share\b",
            re.I,
        ),
        {ValueKind.PER_SHARE.value: "eps_basic"},
        scope_forbidden=_SHARE_COUNT_SCOPE_RE,
    ),
    _RowRule(
        re.compile(
            r"\A(?:adjusted\s+|non-?GAAP\s+)?diluted\s+(?:net\s+)?"
            r"(?:income|earnings|loss)\s+per\s+(?:common\s+)?share\b",
            re.I,
        ),
        {ValueKind.PER_SHARE.value: "eps_diluted"},
        scope_forbidden=_SHARE_COUNT_SCOPE_RE,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Public records
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReleaseFigure:
    """One number that survived every requirement, with its exact location."""

    concept: str
    label: str
    value: float
    basis: str
    units: str
    currency: str | None
    period_label: str
    period_end: str
    receipt: SpanReceipt
    scale_factor: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "label": self.label,
            "value": self.value,
            "basis": self.basis,
            "units": self.units,
            "currency": self.currency,
            "period_label": self.period_label,
            "period_end": self.period_end,
            "scale_factor": self.scale_factor,
            "receipt": self.receipt.to_dict(),
        }


@dataclass(frozen=True)
class TypedAbsence:
    """A figure that is NOT present, and why.

    There is deliberately no ``value`` field.  An absence that carried a null
    would be one careless ``or 0`` away from becoming a reported zero.
    """

    concept: str
    reason: str
    detail: str
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "reason": self.reason,
            "detail": self.detail,
            "label": self.label,
        }


@dataclass(frozen=True)
class ReleaseFigureSet:
    """Everything read out of one release body, plus everything refused."""

    figures: tuple[ReleaseFigure, ...] = ()
    absences: tuple[TypedAbsence, ...] = ()
    schema: str = FIGURES_SCHEMA
    authority: str = AUTHORITY

    def concepts(self) -> frozenset[str]:
        return frozenset(figure.concept for figure in self.figures)

    def figure(self, concept: str, *, basis: str | None = None) -> ReleaseFigure | None:
        for item in self.figures:
            if item.concept == concept and (basis is None or item.basis == basis):
                return item
        return None

    def absence(self, concept: str) -> TypedAbsence | None:
        for item in self.absences:
            if item.concept == concept:
                return item
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "authority": self.authority,
            "figures": [item.to_dict() for item in self.figures],
            "absences": [item.to_dict() for item in self.absences],
            "bound_count": len(self.figures),
            "absent_count": len(self.absences),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Small deterministic readers
# ─────────────────────────────────────────────────────────────────────────────

def parse_numeric(text: str) -> tuple[float, str] | None:
    """Return ``(value, kind_hint)`` for a statement cell, or None.

    ``(50)`` is negative fifty — the accounting convention, not a footnote:
    ``_FOOTNOTE_CELL_RE`` is applied by the caller before this, so a bare
    ``(1)``/``(2)`` marker never reaches here.
    """
    raw = text.strip()
    if not raw:
        return None
    if not (_NUMERIC_CELL_RE.match(raw) or _BARE_NUMERIC_RE.match(raw)):
        return None
    kind = ValueKind.PERCENT.value if raw.endswith("%") else ""
    body = raw.rstrip("%")
    negative = body.startswith("(") and body.endswith(")")
    if negative:
        body = body[1:-1]
    body = body.replace(",", "")
    if not body or body in {"-", "."}:
        return None
    try:
        value = float(body)
    except ValueError:
        return None
    if negative:
        value = -value
    return value, kind


def parse_statement_date(text: str) -> str | None:
    match = _DATE_CELL_RE.match(text.strip())
    if match is None:
        return None
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            parsed = datetime.strptime(
                f"{match.group(1)} {match.group(2)} {match.group(3)}", fmt
            )
        except ValueError:
            continue
        return parsed.date().isoformat()
    return None


@dataclass
class _Context:
    """Document-order state: what the last caption declared."""

    units: str | None = None
    units_source: str = ""
    currency_from_caption: str | None = None
    basis: str | None = None
    basis_source: str = ""

    def observe(self, text: str) -> None:
        units = _UNITS_CAPTION_RE.search(text)
        if units:
            self.units = _UNIT_BY_SCALE[units.group(1).lower()]
            self.units_source = text
        if _CURRENCY_WORD_RE.search(text):
            self.currency_from_caption = "USD"
        # Non-GAAP is checked first: "Reconciliation of GAAP to non-GAAP"
        # matches both patterns and is a non-GAAP scope.
        if _NON_GAAP_CAPTION_RE.search(text):
            self.basis, self.basis_source = Basis.NON_GAAP.value, text
        elif _GAAP_CAPTION_RE.search(text):
            self.basis, self.basis_source = Basis.GAAP.value, text

    def reset_table_scope(self) -> None:
        """Forget the units/currency captions once their table is consumed.

        ``(In millions)`` is a typesetting statement about ONE table and never
        carries to the next; a release that omits it above a supplemental table
        has not declared units there, and the figures must land as absences.
        The GAAP / non-GAAP declaration is deliberately NOT reset — a release
        states it as a section header precisely because it governs everything
        presented until the next such header.
        """
        self.units = None
        self.units_source = ""
        self.currency_from_caption = None


@dataclass(frozen=True)
class _Column:
    index: int
    period_label: str
    period_end: str


def _non_empty(cells: Sequence[TableCell]) -> list[TableCell]:
    return [cell for cell in cells if cell.text.strip()]


def _row_is_header(cells: Sequence[TableCell]) -> bool:
    populated = _non_empty(cells)
    if not populated:
        return True
    return not any(parse_numeric(cell.text) is not None for cell in populated)


def _columns_for_table(block: DisclosureBlock) -> tuple[_Column, ...]:
    """Derive the period each value column reports, from the header rows only.

    A table whose header never names a date yields no columns, and every figure
    in it becomes a ``period_undeclared`` absence.  That is the correct answer:
    a revenue number with no period is not a fact about a quarter.
    """
    if block.table is None:
        return ()
    prefix = ""
    dates: list[str] = []
    labels: list[str] = []
    for row in block.table.rows:
        if not _row_is_header(row):
            break
        populated = _non_empty(row)
        if not populated:
            continue
        texts = [cell.text.strip() for cell in populated]
        parsed = [parse_statement_date(text) for text in texts]
        if parsed and all(item is not None for item in parsed):
            dates = [item for item in parsed if item is not None]
            labels = texts
            continue
        if len(texts) == 1 and _PERIOD_PREFIX_RE.search(texts[0]):
            prefix = texts[0]
    return tuple(
        _Column(
            index=index,
            period_label=f"{prefix} {labels[index]}".strip() if prefix else labels[index],
            period_end=value,
        )
        for index, value in enumerate(dates)
    )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "unnamed"


# ─────────────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────────────

def _receipt_or_absence(
    *,
    document: DisclosureDocument,
    cell: TableCell,
    literal: str,
    concept: str,
    label: str,
    absences: list[TypedAbsence],
) -> SpanReceipt | None:
    try:
        return receipt_for_literal(
            source=document.raw_source,
            source_sha256=document.source_sha256,
            search_start=cell.source_span.char_start,
            search_end=cell.source_span.char_end,
            literal=literal,
        )
    except ReceiptError as exc:
        absences.append(
            TypedAbsence(
                concept=concept,
                reason=AbsenceReason.VALUE_AMBIGUOUS.value,
                detail=f"no unique source location for {literal!r}: {exc}",
                label=label,
            )
        )
        return None


def _extract_table(
    document: DisclosureDocument,
    block: DisclosureBlock,
    context: _Context,
    figures: list[ReleaseFigure],
    absences: list[TypedAbsence],
) -> None:
    if block.table is None:
        return
    columns = _columns_for_table(block)
    column_currency: dict[int, str] = {}
    scope = ""
    # "Header" is a position, not a shape.  A value-less row BEFORE the first
    # data row is a column header; the identical shape AFTER it is a scope
    # caption ("Earnings per share:", "(1) Net sales by reportable segment:").
    # Conflating the two silently drops every scope in the table, which drops
    # EPS (the bare Basic/Diluted labels need their scope) and every segment.
    seen_data_row = False

    for row in block.table.rows:
        populated = _non_empty(row)
        if not populated:
            continue
        if not seen_data_row and _row_is_header(row):
            # Header rows may still carry a units caption typeset inside the
            # table rather than above it.
            for cell in populated:
                context.observe(cell.text)
            continue
        if any(parse_numeric(cell.text) is not None for cell in populated):
            seen_data_row = True

        # Label: the first non-empty cell, stepping over a bare footnote marker
        # — EDGAR typesets "(1)" in its own cell before the real label.
        cursor = 0
        while cursor < len(populated) and _FOOTNOTE_CELL_RE.match(populated[cursor].text.strip()):
            cursor += 1
        if cursor >= len(populated):
            continue
        label_cell = populated[cursor]
        label = _FOOTNOTE_SUFFIX_RE.sub("", label_cell.text.strip())
        rest = populated[cursor + 1:]

        # Value cells, in column order, skipping currency symbols and footnotes.
        values: list[tuple[TableCell, float, str]] = []
        pending_currency: str | None = None
        currency_for_value: list[str | None] = []
        for cell in rest:
            text = cell.text.strip()
            if text in _CURRENCY_SYMBOL:
                pending_currency = _CURRENCY_SYMBOL[text]
                continue
            if _FOOTNOTE_CELL_RE.match(text):
                continue
            parsed = parse_numeric(text)
            if parsed is None:
                continue
            values.append((cell, parsed[0], parsed[1]))
            currency_for_value.append(pending_currency)
            pending_currency = None

        if not values:
            # A label-only row is a scope caption: "Earnings per share:",
            # "(1) Net sales by reportable segment:".
            if label:
                scope = label
                context.observe(label)
            continue

        # Only the first (current-period) column is bound.  A prior-year column
        # is a different period and would need its own concept namespace.
        cell, value, kind_hint = values[0]
        currency = currency_for_value[0]
        if currency:
            column_currency.setdefault(0, currency)
        currency = column_currency.get(0) or context.currency_from_caption

        _bind_row(
            document=document,
            cell=cell,
            value=value,
            kind_hint=kind_hint,
            label=label,
            scope=scope,
            context=context,
            currency=currency,
            columns=columns,
            figures=figures,
            absences=absences,
        )


def _observed_kind(
    *, kind_hint: str, label: str, scope: str, currency: str | None, context: _Context
) -> str | None:
    if kind_hint == ValueKind.PERCENT.value:
        return ValueKind.PERCENT.value
    if _PER_SHARE_SCOPE_RE.search(scope) or _PER_SHARE_SCOPE_RE.search(label):
        return ValueKind.PER_SHARE.value
    if currency or context.units:
        return ValueKind.MONETARY.value
    return None


def _bind_row(
    *,
    document: DisclosureDocument,
    cell: TableCell,
    value: float,
    kind_hint: str,
    label: str,
    scope: str,
    context: _Context,
    currency: str | None,
    columns: tuple[_Column, ...],
    figures: list[ReleaseFigure],
    absences: list[TypedAbsence],
) -> None:
    kind = _observed_kind(
        kind_hint=kind_hint, label=label, scope=scope, currency=currency, context=context
    )
    concept = _concept_for(label=label, scope=scope, kind=kind)
    if concept is None:
        return

    literal = cell.text.strip()
    basis = _basis_for(label=label, scope=scope, context=context)
    if basis is None:
        absences.append(TypedAbsence(
            concept=concept,
            reason=AbsenceReason.BASIS_UNDECLARED.value,
            detail="no GAAP or non-GAAP caption governs this row; refusing to default a basis",
            label=label,
        ))
        return
    if kind is None:
        absences.append(TypedAbsence(
            concept=concept,
            reason=AbsenceReason.UNITS_UNDECLARED.value,
            detail="no units caption and no currency symbol govern this value",
            label=label,
        ))
        return
    if kind == ValueKind.MONETARY.value:
        if context.units is None:
            absences.append(TypedAbsence(
                concept=concept,
                reason=AbsenceReason.UNITS_UNDECLARED.value,
                detail="no '(In thousands/millions/billions)' caption governs this table",
                label=label,
            ))
            return
        if currency is None:
            absences.append(TypedAbsence(
                concept=concept,
                reason=AbsenceReason.CURRENCY_UNDECLARED.value,
                detail="no currency symbol governs this column and no caption names one",
                label=label,
            ))
            return
        units, scale = context.units, _SCALE_FACTOR[context.units]
    elif kind == ValueKind.PER_SHARE.value:
        if currency is None:
            absences.append(TypedAbsence(
                concept=concept,
                reason=AbsenceReason.CURRENCY_UNDECLARED.value,
                detail="a per-share amount with no currency symbol is not a price",
                label=label,
            ))
            return
        # A per-share amount never inherits the statement's (In millions) scale.
        units, scale = "per_share", 1.0
    else:
        units, scale, currency = "percent", 1.0, None

    if not columns:
        absences.append(TypedAbsence(
            concept=concept,
            reason=AbsenceReason.PERIOD_UNDECLARED.value,
            detail="the table header names no period end date",
            label=label,
        ))
        return

    receipt = _receipt_or_absence(
        document=document, cell=cell, literal=literal,
        concept=concept, label=label, absences=absences,
    )
    if receipt is None:
        return

    figures.append(ReleaseFigure(
        concept=concept,
        label=label,
        value=value,
        basis=basis,
        units=units,
        currency=currency,
        period_label=columns[0].period_label,
        period_end=columns[0].period_end,
        receipt=receipt,
        scale_factor=scale,
    ))


def _concept_for(*, label: str, scope: str, kind: str | None) -> str | None:
    if not label:
        return None
    if _SEGMENT_SCOPE_RE.search(scope):
        # Under a segment breakdown, the "Total" line is the same fact the
        # statement already reported; emitting it again would double-count.
        if _TOTAL_LABEL_RE.match(label) or kind != ValueKind.MONETARY.value:
            return None
        return f"segment_revenue:{_slugify(label)}"
    for rule in _ROW_RULES:
        if not rule.pattern.match(label):
            continue
        if rule.scope_forbidden is not None and rule.scope_forbidden.search(scope):
            return None
        if rule.scope_required is not None and not (
            rule.scope_required.search(scope) or rule.scope_required.search(label)
        ):
            return None
        if kind is None:
            # Kind is unknown, but the label matched a roster concept: report
            # the concept so the caller learns WHICH figure went unbound.
            return next(iter(rule.kind_to_concept.values()))
        return rule.kind_to_concept.get(kind)
    if _NON_GAAP_CAPTION_RE.search(scope) and kind == ValueKind.MONETARY.value:
        return f"non_gaap_adjustment:{_slugify(label)}"
    return None


def _basis_for(*, label: str, scope: str, context: _Context) -> str | None:
    if _NON_GAAP_INLINE_RE.search(label) or _NON_GAAP_INLINE_RE.search(scope):
        return Basis.NON_GAAP.value
    return context.basis


def _extract_guidance(
    document: DisclosureDocument,
    block: DisclosureBlock,
    figures: list[ReleaseFigure],
    absences: list[TypedAbsence],
    seen: set[str],
) -> None:
    text = block.text
    if not _GUIDANCE_SENTENCE_RE.search(text):
        return
    match = _GUIDANCE_RANGE_RE.search(text)
    if match is None:
        return
    low_literal, low_mag, high_literal, high_mag = (
        match.group(1), match.group(2), match.group(3), match.group(4)
    )
    # "$72.8 billion to $78.6 billion" and "$72.8 to $78.6 billion" both occur;
    # the trailing magnitude governs both endpoints when the first omits it.
    magnitude = (low_mag or high_mag or "").lower()

    concept_stem = "guidance_revenue"
    if _NON_GAAP_INLINE_RE.search(text) and re.search(r"per\s+share|EPS", text, re.I):
        concept_stem, magnitude_units = "guidance_eps", "per_share"
    elif re.search(r"per\s+share|EPS", text, re.I):
        concept_stem, magnitude_units = "guidance_eps", "per_share"
    elif magnitude:
        magnitude_units = _GUIDANCE_MAGNITUDE[magnitude]
    else:
        magnitude_units = ""

    basis = Basis.NON_GAAP.value if _NON_GAAP_INLINE_RE.search(text) else None
    period = _GUIDANCE_PERIOD_RE.search(text)

    for suffix, literal in (("low", low_literal), ("high", high_literal)):
        concept = f"{concept_stem}_{suffix}"
        if concept in seen:
            continue
        seen.add(concept)
        if basis is None:
            absences.append(TypedAbsence(
                concept=concept,
                reason=AbsenceReason.BASIS_UNDECLARED.value,
                detail="guidance sentence names neither GAAP nor non-GAAP; "
                       "refusing to default a basis for a forward figure",
                label=None,
            ))
            continue
        if not magnitude_units:
            absences.append(TypedAbsence(
                concept=concept,
                reason=AbsenceReason.UNITS_UNDECLARED.value,
                detail="guidance range states no magnitude (thousand/million/billion)",
                label=None,
            ))
            continue
        if period is None:
            absences.append(TypedAbsence(
                concept=concept,
                reason=AbsenceReason.PERIOD_UNDECLARED.value,
                detail="guidance sentence names no period",
                label=None,
            ))
            continue
        try:
            receipt = receipt_for_literal(
                source=document.raw_source,
                source_sha256=document.source_sha256,
                search_start=block.source_span.char_start,
                search_end=block.source_span.char_end,
                literal=literal,
            )
        except ReceiptError as exc:
            absences.append(TypedAbsence(
                concept=concept,
                reason=AbsenceReason.VALUE_AMBIGUOUS.value,
                detail=f"no unique source location for {literal!r}: {exc}",
                label=None,
            ))
            continue
        qualifier, unit_word, year = period.group(1), period.group(2), period.group(3)
        period_label = " ".join(
            part for part in ("the", qualifier, unit_word, year) if part
        ).strip()
        figures.append(ReleaseFigure(
            concept=concept,
            label=period_label,
            value=float(literal.replace(",", "")),
            basis=basis,
            units=magnitude_units,
            currency="USD",
            period_label=period_label,
            # A guidance window has no reported period end; the label is the
            # only period identity the document declares.
            period_end="",
            receipt=receipt,
            scale_factor=_SCALE_FACTOR.get(magnitude_units, 1.0),
        ))


def _resolve_restatements(
    figures: list[ReleaseFigure], absences: list[TypedAbsence]
) -> tuple[list[ReleaseFigure], list[TypedAbsence]]:
    """Collapse identical restatements; refuse contradictory ones.

    A press release states the same fact more than once by design — net income
    heads the statement of operations and opens the cash-flow statement, and
    total net sales is repeated under every segment breakdown.  Two readings
    that AGREE on (concept, basis, period, value) are one fact and collapse.

    Two readings that DISAGREE are not a fact at all.  Keeping the first would
    make the answer depend on document order, so both are dropped and the
    conflict is reported as a typed absence.
    """
    grouped: dict[tuple[str, str, str], list[ReleaseFigure]] = {}
    for figure in figures:
        grouped.setdefault((figure.concept, figure.basis, figure.period_end), []).append(figure)

    kept: list[ReleaseFigure] = []
    extra: list[TypedAbsence] = []
    for (concept, basis, period_end), rows in grouped.items():
        values = {row.value for row in rows}
        if len(values) == 1:
            kept.append(rows[0])
            continue
        extra.append(TypedAbsence(
            concept=concept,
            reason=AbsenceReason.VALUE_AMBIGUOUS.value,
            detail=(
                f"{len(rows)} rows report {concept} for {period_end or 'this period'} "
                f"on a {basis} basis with different values "
                f"({', '.join(format(value, 'g') for value in sorted(values))}) — "
                "refusing to pick one by document order"
            ),
            label=rows[0].label,
        ))
    kept.sort(key=lambda row: (row.concept, row.basis, row.period_end))
    return kept, absences + extra


def extract_release_figures(
    document: DisclosureDocument,
    *,
    roster: Iterable[str] = CONCEPT_ROSTER,
) -> ReleaseFigureSet:
    """Read every roster concept out of a normalized release body.

    Emits one ``ReleaseFigure`` per concept it could bind to an exact, replayed
    source location, and one ``TypedAbsence`` per roster concept it could not.
    """
    figures: list[ReleaseFigure] = []
    absences: list[TypedAbsence] = []
    context = _Context()
    guidance_seen: set[str] = set()

    for block in document.blocks:
        if block.kind is BlockKind.TABLE:
            _extract_table(document, block, context, figures, absences)
            context.reset_table_scope()
            continue
        context.observe(block.text)
        if block.kind is BlockKind.PARAGRAPH:
            _extract_guidance(document, block, figures, absences, guidance_seen)

    figures, absences = _resolve_restatements(figures, absences)

    bound = {figure.concept for figure in figures}
    # An absence is a statement about the RELEASE, not about one row.  A release
    # that reports operating cash flow with full provenance in the cash-flow
    # statement and again, undeclared, in a supplemental table has reported it;
    # emitting both a figure and an absence for one concept is a contradiction,
    # not extra candour.
    absences = [item for item in absences if item.concept not in bound]
    reported_absent = {absence.concept for absence in absences}
    for concept in roster:
        if concept in bound or concept in reported_absent:
            continue
        absences.append(TypedAbsence(
            concept=concept,
            reason=AbsenceReason.CONCEPT_NOT_PRESENT.value,
            detail="no row or sentence in this release reports this concept",
            label=None,
        ))

    return ReleaseFigureSet(
        figures=tuple(figures),
        absences=tuple(sorted(absences, key=lambda item: (item.concept, item.reason))),
    )


__all__ = [
    "AUTHORITY",
    "AbsenceReason",
    "Basis",
    "CONCEPT_ROSTER",
    "FIGURES_SCHEMA",
    "ReleaseFigure",
    "ReleaseFigureSet",
    "TypedAbsence",
    "ValueKind",
    "extract_release_figures",
    "parse_numeric",
    "parse_statement_date",
]
