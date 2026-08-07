"""The canonical EDGAR filing key: the exact pair ``(cik, accession)``.

FROZEN CONTRACT — ``research/EARNINGS_WAVE1_CONTRACT_FREEZE_2026-08-06.md`` Q2.
Before this module the estate's two EDGAR readers shared exactly ``{ticker}``:

* ``collectors/edgar_earnings_8k.py`` emitted
  ``{ticker, cik, filing_date, acceptance_datetime, items}`` and **no accession**;
* ``engine/marketing/edgar_earnings_wire.py`` emitted
  ``{id, accession, ticker, when, ...}`` and **no cik**, no ``filing_date``, and a
  ``when`` that was wall-clock-at-processing rather than a source timestamp.

Neither field set was a superset of the other, so the two planes could not be
joined at any level.  Both readers now carry the full key and this module is the
one place that decides what "the same filing" means.

WHY NOT ``(cik, filing_date)`` WITH A TOLERANCE WINDOW
------------------------------------------------------
Two reasons, and the first alone is disqualifying:

1. The programme's acceptance requires that *availability timestamps prove no
   consumer outran the source*.  A fuzzy date join cannot support that claim —
   it asserts a correspondence it never checked.
2. An 8-K/A amendment is a **different filing** of the **same event**.  A date
   join collapses the amendment into its original and the correction becomes
   invisible; keying on the accession keeps them distinct filings, and
   ``engine.earnings_release.binding`` is what re-groups them into one event.

``JOIN_DATE_TOLERANCE_DAYS`` is therefore 0 and there is no parameter to change
it.  ``join_filings`` never reads a date at all.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping

# The join reads (cik, accession) and nothing else.  Documented as a constant so
# a future caller cannot "just widen it a day" without deleting this line.
JOIN_DATE_TOLERANCE_DAYS = 0
JOIN_KEY_FIELDS: tuple[str, ...] = ("cik", "accession")

# EDGAR accession numbers are 10 digits (the filer agent), 2 digits (year), and
# 6 digits (sequence).  They travel both dashed and undashed; the canonical
# spelling here is dashed, matching the submissions JSON's own ``accessionNumber``.
_ACCESSION_RE = re.compile(r"\A(\d{10})-?(\d{2})-?(\d{6})\Z")
_CIK_RE = re.compile(r"\A(?:CIK)?0*(\d{1,10})\Z", re.IGNORECASE)


class FilingIdentityError(ValueError):
    """The supplied value cannot be used as part of a canonical filing key."""


def normalize_accession(value: object) -> str:
    """Return the canonical dashed accession, or raise.

    Accepts the dashed and undashed spellings that EDGAR uses interchangeably.
    Anything else is refused rather than coerced: a half-parsed accession is a
    silent mis-join, which is the exact failure this key exists to prevent.

    >>> normalize_accession("0000320193-24-000005")
    '0000320193-24-000005'
    >>> normalize_accession("000032019324000005")
    '0000320193-24-000005'
    """
    text = str(value or "").strip()
    match = _ACCESSION_RE.match(text)
    if match is None:
        raise FilingIdentityError(f"not an EDGAR accession number: {value!r}")
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def normalize_cik(value: object) -> int:
    """Return the CIK as a bare integer, or raise.

    Accepts ``320193``, ``"320193"``, ``"0000320193"`` and ``"CIK0000320193"``.
    Booleans are refused explicitly — ``isinstance(True, int)`` is True in
    Python, and a ``True`` reaching a key would silently become CIK 1.
    """
    if isinstance(value, bool):
        raise FilingIdentityError(f"not a CIK: {value!r}")
    if isinstance(value, int):
        if value <= 0 or value > 9_999_999_999:
            raise FilingIdentityError(f"not a CIK: {value!r}")
        return int(value)
    match = _CIK_RE.match(str(value or "").strip())
    if match is None:
        raise FilingIdentityError(f"not a CIK: {value!r}")
    cik = int(match.group(1))
    if cik <= 0:
        raise FilingIdentityError(f"not a CIK: {value!r}")
    return cik


@dataclass(frozen=True, order=True)
class FilingKey:
    """One EDGAR submission, identified the only correction-stable way."""

    cik: int
    accession: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cik", normalize_cik(self.cik))
        object.__setattr__(self, "accession", normalize_accession(self.accession))

    @property
    def key(self) -> str:
        """A single opaque string form, safe as a dict key or a file name."""
        return f"{self.cik:010d}:{self.accession}"

    @classmethod
    def parse(cls, text: object) -> FilingKey:
        raw = str(text or "")
        if ":" not in raw:
            raise FilingIdentityError(f"not a filing key: {text!r}")
        cik, _, accession = raw.partition(":")
        return cls(cik=normalize_cik(cik), accession=normalize_accession(accession))

    def to_dict(self) -> dict[str, Any]:
        return {"cik": self.cik, "accession": self.accession, "filing_key": self.key}


def _first_present(row: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def filing_key_from_8k_row(row: Mapping[str, Any]) -> FilingKey:
    """Key one ``collectors.edgar_earnings_8k`` store row.

    Raises ``FilingIdentityError`` on a legacy row that predates accession
    capture.  That is deliberate: such a row genuinely cannot be joined, and
    returning a partial key would let a caller believe otherwise.
    """
    if not isinstance(row, Mapping):
        raise FilingIdentityError("8-K row must be a mapping")
    accession = _first_present(row, ("accession", "accession_number", "accessionNumber"))
    if accession is None:
        raise FilingIdentityError(
            "8-K row carries no accession — pre-Wave-1B rows cannot be joined"
        )
    cik = _first_present(row, ("cik", "CIK"))
    if cik is None:
        raise FilingIdentityError("8-K row carries no cik")
    return FilingKey(cik=cik, accession=accession)


def filing_key_from_wire_event(event: Mapping[str, Any]) -> FilingKey:
    """Key one ``engine.marketing.edgar_earnings_wire`` event.

    ``id`` is ``f"{ticker}-{accession}"`` and is deliberately NOT parsed here —
    a ticker is an alias with a validity window, not a durable key (docket
    §4.2 rule 3), and splitting on ``-`` would break on ``BRK-B``.
    """
    if not isinstance(event, Mapping):
        raise FilingIdentityError("wire event must be a mapping")
    accession = _first_present(event, ("accession", "accession_number"))
    if accession is None:
        raise FilingIdentityError("wire event carries no accession")
    cik = _first_present(event, ("cik", "CIK"))
    if cik is None:
        raise FilingIdentityError(
            "wire event carries no cik — pre-Wave-1B events cannot be joined"
        )
    return FilingKey(cik=cik, accession=accession)


@dataclass(frozen=True)
class JoinedFiling:
    """One 8-K store row and one wire event proven to be the same submission."""

    filing_key: FilingKey
    collector_row: Mapping[str, Any]
    wire_event: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "filing_key": self.filing_key.key,
            "cik": self.filing_key.cik,
            "accession": self.filing_key.accession,
        }


@dataclass(frozen=True)
class JoinResult:
    """The outcome of an exact ``(cik, accession)`` join.

    ``unjoinable_*`` is not the same as ``unmatched_*``: a row that cannot even
    be keyed (a legacy row with no accession, a wire event with no cik) is
    reported separately from one that was keyed and found no partner.  Folding
    the two together would hide a schema regression behind a coverage number.
    """

    joined: tuple[JoinedFiling, ...]
    unmatched_collector: tuple[Mapping[str, Any], ...]
    unmatched_wire: tuple[Mapping[str, Any], ...]
    unjoinable_collector: tuple[tuple[Mapping[str, Any], str], ...]
    unjoinable_wire: tuple[tuple[Mapping[str, Any], str], ...]
    joined_on: tuple[str, ...] = JOIN_KEY_FIELDS
    date_tolerance_days: int = JOIN_DATE_TOLERANCE_DAYS

    def as_dict(self) -> dict[str, Any]:
        return {
            "joined": len(self.joined),
            "unmatched_collector": len(self.unmatched_collector),
            "unmatched_wire": len(self.unmatched_wire),
            "unjoinable_collector": len(self.unjoinable_collector),
            "unjoinable_wire": len(self.unjoinable_wire),
            "joined_on": list(self.joined_on),
            "date_tolerance_days": self.date_tolerance_days,
        }


def join_filings(
    collector_rows: Iterable[Mapping[str, Any]],
    wire_events: Iterable[Mapping[str, Any]],
) -> JoinResult:
    """Exact inner join of the two EDGAR planes on ``(cik, accession)``.

    No date is read on either side, so no tolerance window can exist.  Two
    filings by the same issuer on the same day with different accessions stay
    two filings; an amendment never collapses into its original here.
    """
    keyed_collector: dict[str, Mapping[str, Any]] = {}
    unjoinable_collector: list[tuple[Mapping[str, Any], str]] = []
    for row in collector_rows:
        try:
            key = filing_key_from_8k_row(row)
        except FilingIdentityError as exc:
            unjoinable_collector.append((row, str(exc)))
            continue
        keyed_collector.setdefault(key.key, row)

    keyed_wire: dict[str, Mapping[str, Any]] = {}
    unjoinable_wire: list[tuple[Mapping[str, Any], str]] = []
    for event in wire_events:
        try:
            key = filing_key_from_wire_event(event)
        except FilingIdentityError as exc:
            unjoinable_wire.append((event, str(exc)))
            continue
        keyed_wire.setdefault(key.key, event)

    joined: list[JoinedFiling] = []
    for key_text in sorted(set(keyed_collector) & set(keyed_wire)):
        joined.append(
            JoinedFiling(
                filing_key=FilingKey.parse(key_text),
                collector_row=keyed_collector[key_text],
                wire_event=keyed_wire[key_text],
            )
        )

    unmatched_collector = tuple(
        keyed_collector[k] for k in sorted(set(keyed_collector) - set(keyed_wire))
    )
    unmatched_wire = tuple(
        keyed_wire[k] for k in sorted(set(keyed_wire) - set(keyed_collector))
    )
    return JoinResult(
        joined=tuple(joined),
        unmatched_collector=unmatched_collector,
        unmatched_wire=unmatched_wire,
        unjoinable_collector=tuple(unjoinable_collector),
        unjoinable_wire=tuple(unjoinable_wire),
    )


__all__ = [
    "FilingIdentityError",
    "FilingKey",
    "JOIN_DATE_TOLERANCE_DAYS",
    "JOIN_KEY_FIELDS",
    "JoinResult",
    "JoinedFiling",
    "filing_key_from_8k_row",
    "filing_key_from_wire_event",
    "join_filings",
    "normalize_accession",
    "normalize_cik",
]
