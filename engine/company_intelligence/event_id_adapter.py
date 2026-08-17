"""Bidirectional adapter: canonical issuer event ⇄ both shipped ticker ids.

Two ticker-keyed schemes are already live and neither may be rewritten
(handoff §Wave 1.3):

* ``engine/company_intelligence/contracts.py::stable_event_id`` →
  ``"cie_" + sha256(f"{TICKER}|{YEAR}|Q{QUARTER}")[:24]``
* ``engine/earnings_narrative/contracts.py::event_key`` →
  ``f"{TICKER}/{TRANSCRIPT_ID}"``

Both start from a ticker, so an issuer reporting one quarter under two listings
mints two logical events.  This module makes those ids ALIASES of one canonical
issuer-keyed event instead of competing identities.

The direction that needs an index is ``cie_… → canonical``: the id is a
truncated sha256 and cannot be inverted, so the mapping has to be recorded when
the event is minted.  ``TICKER/YYYYQn`` is structured text and can also be
resolved directly through the point-in-time registry, which is the path that
catches a symbol whose issuer changed between quarters.

Both live minting functions are CALLED here rather than reimplemented, so a
change to either goes red in this adapter's tests instead of silently
de-aliasing every historical deep link.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping

from .contracts import ContractError, safe_ticker, stable_event_id
from .contracts import event_key as company_intelligence_event_key
from .events import CompanyEvent, FiscalPeriod, canonical_event_id, parse_canonical_event_id
from .identity import IssuerRegistry
from ..earnings_narrative.contracts import event_key as earnings_narrative_event_key
from ..earnings_narrative.public_wire import wire_slug


_NARRATIVE_KEY_RE = re.compile(r"^(?P<ticker>[^/]+)/(?P<period>\d{4}Q[1-4])$")
_CIE_ID_RE = re.compile(r"^cie_[0-9a-f]{24}$")
_CANONICAL_ID_RE = re.compile(r"^evt_cik\d{10}_\d{4}(?:q[1-4]|fy)_[a-z0-9]+$")
_PUBLIC_SLUG_RE = re.compile(
    r"^(?P<slug_ticker>[a-z0-9.-]+)-(?P<period>\d{4}q[1-4])-call-record$"
)


class AliasError(ContractError):
    """A legacy id cannot be resolved to exactly one canonical event."""


def company_intelligence_alias(ticker: object, period: FiscalPeriod) -> str:
    """The live ``cie_…`` id for one listing of an event."""
    if period.quarter is None:
        raise AliasError("the cie_ scheme has no annual form")
    return stable_event_id(ticker, period.year, period.quarter)


def earnings_narrative_alias(ticker: object, period: FiscalPeriod) -> str:
    """The live ``TICKER/YYYYQn`` transcript event key for one listing."""
    if period.quarter is None:
        raise AliasError("the transcript key scheme has no annual form")
    return earnings_narrative_event_key(
        {"ticker": safe_ticker(ticker), "transcript_id": f"{period.year}Q{period.quarter}"}
    )


def public_wire_alias(ticker: object, period: FiscalPeriod) -> str:
    """The compiler-owned public Wire slug for one listing of an event."""
    if period.quarter is None:
        raise AliasError("the public wire slug has no annual form")
    return wire_slug(safe_ticker(ticker), f"{period.year}Q{period.quarter}")


def parse_earnings_narrative_key(key: object) -> tuple[str, FiscalPeriod]:
    match = _NARRATIVE_KEY_RE.fullmatch(str(key or "").strip())
    if match is None:
        raise AliasError(f"not an earnings_narrative event key: {key!r}")
    period_text = match.group("period")
    return (
        safe_ticker(match.group("ticker")),
        FiscalPeriod(year=int(period_text[:4]), quarter=int(period_text[-1])),
    )


@dataclass(frozen=True, slots=True)
class EventAliases:
    """Every legacy id that resolves to one canonical event."""

    canonical_event_id: str
    company_id: str
    fiscal_period: FiscalPeriod
    tickers: tuple[str, ...]
    company_intelligence_ids: tuple[str, ...]
    earnings_narrative_keys: tuple[str, ...]
    public_slugs: tuple[str, ...] = ()

    @property
    def listing_keyed_id_count(self) -> int:
        """What a listing-keyed scheme would have counted for this ONE event."""
        return len(set(self.company_intelligence_ids))

    def all_legacy_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((
            *self.company_intelligence_ids,
            *self.earnings_narrative_keys,
            *self.public_slugs,
        )))

    def to_payload(self) -> dict[str, Any]:
        return {
            "canonical_event_id": self.canonical_event_id,
            "company_id": self.company_id,
            "fiscal_period": self.fiscal_period.to_payload(),
            "tickers": list(self.tickers),
            "company_intelligence_ids": list(self.company_intelligence_ids),
            "earnings_narrative_keys": list(self.earnings_narrative_keys),
            "public_slugs": list(self.public_slugs),
            "listing_keyed_id_count": self.listing_keyed_id_count,
        }


def aliases_for(
    company_id: object,
    fiscal_period: FiscalPeriod,
    tickers: Iterable[object],
    *,
    event_type: str = "earnings_results",
) -> EventAliases:
    """Mint the canonical id and every legacy alias for one issuer event."""
    symbols = tuple(dict.fromkeys(safe_ticker(ticker) for ticker in tickers))
    if not symbols:
        raise AliasError("an event with no listing has no legacy alias")
    canonical = canonical_event_id(company_id, fiscal_period, event_type)
    issuer, _, _ = parse_canonical_event_id(canonical)
    return EventAliases(
        canonical_event_id=canonical,
        company_id=issuer,
        fiscal_period=fiscal_period,
        tickers=symbols,
        company_intelligence_ids=tuple(
            company_intelligence_alias(symbol, fiscal_period) for symbol in symbols
        ),
        earnings_narrative_keys=tuple(
            earnings_narrative_alias(symbol, fiscal_period) for symbol in symbols
        ),
        public_slugs=tuple(
            public_wire_alias(symbol, fiscal_period) for symbol in symbols
        ),
    )


def aliases_for_event(event: CompanyEvent, tickers: Iterable[object]) -> EventAliases:
    return aliases_for(
        event.company_id, event.fiscal_period, tickers, event_type=event.event_type
    )


class EventAliasIndex:
    """The resolvable map from every legacy id back to one canonical event."""

    def __init__(self) -> None:
        self._by_cie: dict[str, str] = {}
        self._by_narrative: dict[str, str] = {}
        self._by_slug: dict[str, str] = {}
        self._aliases: dict[str, EventAliases] = {}

    def __len__(self) -> int:
        return len(self._aliases)

    @property
    def canonical_event_ids(self) -> tuple[str, ...]:
        return tuple(self._aliases)

    @property
    def company_intelligence_ids(self) -> tuple[str, ...]:
        return tuple(self._by_cie)

    def register(self, aliases: EventAliases) -> EventAliases:
        existing = self._aliases.get(aliases.canonical_event_id)
        if existing is not None:
            merged_tickers = tuple(dict.fromkeys((*existing.tickers, *aliases.tickers)))
            aliases = aliases_for(
                existing.company_id,
                existing.fiscal_period,
                merged_tickers,
                event_type=_event_type_of(existing.canonical_event_id),
            )
        for legacy, table in (
            (aliases.company_intelligence_ids, self._by_cie),
            (aliases.earnings_narrative_keys, self._by_narrative),
            (aliases.public_slugs, self._by_slug),
        ):
            for key in legacy:
                owner = table.get(key)
                if owner is not None and owner != aliases.canonical_event_id:
                    raise AliasError(
                        f"legacy id {key} already resolves to {owner}; it cannot also mean "
                        f"{aliases.canonical_event_id}"
                    )
                table[key] = aliases.canonical_event_id
        self._aliases[aliases.canonical_event_id] = aliases
        return aliases

    def register_event(self, event: CompanyEvent, tickers: Iterable[object]) -> EventAliases:
        return self.register(aliases_for_event(event, tickers))

    def aliases(self, canonical_event_id_: object) -> EventAliases:
        try:
            return self._aliases[str(canonical_event_id_)]
        except KeyError:
            raise AliasError(f"unregistered canonical event: {canonical_event_id_!r}") from None

    def to_canonical(self, legacy_id: object) -> str:
        """Resolve a canonical id or either live alias scheme to the event."""
        text = str(legacy_id or "").strip()
        if _CANONICAL_ID_RE.fullmatch(text):
            if text in self._aliases:
                return text
            raise AliasError(f"unindexed canonical event: {text}") from None
        if _CIE_ID_RE.fullmatch(text):
            try:
                return self._by_cie[text]
            except KeyError:
                raise AliasError(f"unindexed cie_ id: {text}") from None
        if _NARRATIVE_KEY_RE.fullmatch(text):
            try:
                return self._by_narrative[text]
            except KeyError:
                raise AliasError(f"unindexed transcript event key: {text}") from None
        if _PUBLIC_SLUG_RE.fullmatch(text):
            try:
                return self._by_slug[text]
            except KeyError:
                raise AliasError(f"unindexed public wire slug: {text}") from None
        raise AliasError(f"not a known legacy event id: {legacy_id!r}")

    def resolve_narrative_key(
        self, key: object, *, registry: IssuerRegistry, asof: object
    ) -> str:
        """Resolve ``TICKER/YYYYQn`` through the point-in-time registry.

        Independent of the index on purpose: this is the path that notices a
        symbol whose issuer changed between quarters, where an index built at
        mint time would happily return the old owner.
        """
        ticker, period = parse_earnings_narrative_key(key)
        resolved = registry.resolve_ticker(ticker, asof=asof)
        if resolved is None:
            raise AliasError(
                f"{ticker} maps to no issuer at {asof}; the event cannot be attributed"
            )
        return canonical_event_id(resolved.company_id, period, "earnings_results")

    def coverage(self) -> dict[str, int]:
        """Issuer coverage vs listing coverage — docket §4.2 rule 8.

        Their difference is the expected consequence of share classes and dual
        listings, and is never to be reported as missing data.
        """
        return {
            "canonical_events": len(self._aliases),
            "listing_keyed_ids": len(self._by_cie),
            "issuers": len({record.company_id for record in self._aliases.values()}),
        }


def _event_type_of(canonical: str) -> str:
    return parse_canonical_event_id(canonical)[2]


def legacy_ids_for_context_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """Both legacy ids for a v1 context event row, recomputed not copied."""
    ticker = safe_ticker(row.get("ticker"))
    year = int(row["fiscal_year"])
    quarter = int(row["fiscal_quarter"])
    return (
        stable_event_id(ticker, year, quarter),
        earnings_narrative_event_key({"ticker": ticker, "transcript_id": f"{year}Q{quarter}"}),
    )


def company_intelligence_event_key_for(ticker: object, period: FiscalPeriod) -> str:
    """The live ``TICKER|YYYY|Qn`` key, exposed so callers stop re-deriving it."""
    if period.quarter is None:
        raise AliasError("the cie_ scheme has no annual form")
    return company_intelligence_event_key(ticker, period.year, period.quarter)
