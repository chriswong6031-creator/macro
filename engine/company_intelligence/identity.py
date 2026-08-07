"""``company_identity.v1`` — issuer, security, and listing identity.

Docket §4.2 rules this and the shipped estate contradicts it: both live event-id
schemes start from a ticker, so one issuer quarter published under two listings
mints two logical events.  The rules implemented here are the docket's:

1. ``company_id`` identifies the legal issuer (CIK-anchored).
2. ``security_id`` identifies one listed security or share class.
3. ``ticker`` is an alias with ``valid_from``/``valid_to``, never a durable key.
4. Dual classes share an issuer and remain distinct securities.
6. Events attach to the reporting entity; market reactions attach to securities.

Ticker resolution is point-in-time on purpose.  A mapping registered today must
not retroactively re-attribute an event that predates it — otherwise a reused
symbol silently rewrites another issuer's history, which is the exact defect the
rule exists to prevent.  Where the mapping is ambiguous the resolver refuses:
a guessed issuer is worse than a typed absence.

This module adds a versioned convergence layer.  It rewrites nothing: v1
``contracts.py`` is untouched and stays authoritative for the v1 wire.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any, Iterable, Iterator, Mapping

from .contracts import ContractError, parse_date, safe_ticker


IDENTITY_SCHEMA = "company_identity.v1"
AUTHORITY = "context_only"

# The floor a registry uses when a source supplies no window at all.  It is a
# real date rather than ``None`` so every alias comparison is a date comparison
# and no code path can accidentally treat "unknown" as "always".
ALIAS_EPOCH = date(1970, 1, 1)

_CIK_RE = re.compile(r"^\d{1,10}$")
_MIC_RE = re.compile(r"^[A-Z0-9]{4}$")
_SHARE_CLASS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class IdentityError(ContractError):
    """The identity graph cannot be trusted to attribute an event."""


def company_id_for_cik(cik: object) -> str:
    """Return the canonical CIK-anchored issuer id, e.g. ``cik:0000320193``."""
    text = str(cik if cik is not None else "").strip()
    if text.lower().startswith("cik:"):
        text = text[4:]
    text = text.lstrip("0") or "0"
    if not _CIK_RE.fullmatch(text):
        raise IdentityError(f"not a CIK: {cik!r}")
    return "cik:" + text.zfill(10)


def security_id_for(mic: object, ticker: object) -> str:
    """Return the canonical listed-security id, e.g. ``xnas:AAPL``."""
    market = str(mic or "").strip().upper()
    if not _MIC_RE.fullmatch(market):
        raise IdentityError(f"not a MIC: {mic!r}")
    return f"{market.lower()}:{safe_ticker(ticker)}"


def _as_date(value: object, *, field_name: str) -> date:
    if isinstance(value, date):
        return value
    return parse_date(value, field=field_name)


@dataclass(frozen=True, slots=True)
class ListingAlias:
    """One ticker alias on one venue, valid over a half-open date window.

    ``valid_to`` is EXCLUSIVE.  A closed window that included its end date would
    let two issuers own the same symbol on the changeover day, which is exactly
    the ambiguity the resolver has to refuse.
    """

    ticker: str
    mic: str
    share_class: str
    trading_currency: str
    is_primary: bool = False
    valid_from: date = ALIAS_EPOCH
    valid_to: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", safe_ticker(self.ticker))
        market = str(self.mic or "").strip().upper()
        if not _MIC_RE.fullmatch(market):
            raise IdentityError(f"not a MIC: {self.mic!r}")
        object.__setattr__(self, "mic", market)
        share_class = str(self.share_class or "").strip()
        if not _SHARE_CLASS_RE.fullmatch(share_class):
            raise IdentityError(f"unsupported share class: {self.share_class!r}")
        object.__setattr__(self, "share_class", share_class)
        currency = str(self.trading_currency or "").strip().upper()
        if not _CURRENCY_RE.fullmatch(currency):
            raise IdentityError(f"not an ISO currency: {self.trading_currency!r}")
        object.__setattr__(self, "trading_currency", currency)
        object.__setattr__(self, "valid_from", _as_date(self.valid_from, field_name="valid_from"))
        if self.valid_to is not None:
            valid_to = _as_date(self.valid_to, field_name="valid_to")
            if valid_to <= self.valid_from:
                raise IdentityError(
                    f"{self.ticker}: valid_to {valid_to} is not after valid_from {self.valid_from}"
                )
            object.__setattr__(self, "valid_to", valid_to)
        object.__setattr__(self, "is_primary", bool(self.is_primary))

    @property
    def security_id(self) -> str:
        return security_id_for(self.mic, self.ticker)

    def covers(self, asof: date) -> bool:
        if asof < self.valid_from:
            return False
        return self.valid_to is None or asof < self.valid_to

    def overlaps(self, other: "ListingAlias") -> bool:
        if self.ticker != other.ticker:
            return False
        left_end = self.valid_to or date.max
        right_end = other.valid_to or date.max
        return self.valid_from < right_end and other.valid_from < left_end

    def to_payload(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "ticker": self.ticker,
            "mic": self.mic,
            "share_class": self.share_class,
            "trading_currency": self.trading_currency,
            "is_primary": self.is_primary,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
        }


@dataclass(frozen=True, slots=True)
class IssuerIdentity:
    """One legal issuer / reporting entity and every listing it has carried."""

    company_id: str
    display_name: str
    fiscal_year_end_month: int
    reporting_currency: str
    listings: tuple[ListingAlias, ...] = field(default_factory=tuple)
    issuer_kind: str = "general"
    external_ids: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", company_id_for_cik(self.company_id))
        name = str(self.display_name or "").strip()
        if not name or len(name) > 240:
            raise IdentityError(f"unusable issuer display name: {self.display_name!r}")
        object.__setattr__(self, "display_name", name)
        month = self.fiscal_year_end_month
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise IdentityError(f"fiscal_year_end_month out of range: {month!r}")
        currency = str(self.reporting_currency or "").strip().upper()
        if not _CURRENCY_RE.fullmatch(currency):
            raise IdentityError(f"not an ISO currency: {self.reporting_currency!r}")
        object.__setattr__(self, "reporting_currency", currency)
        listings = tuple(self.listings)
        if not listings:
            raise IdentityError(f"{self.company_id}: an issuer with no listing cannot be resolved")
        seen: set[str] = set()
        for listing in listings:
            if not isinstance(listing, ListingAlias):
                raise IdentityError("listings must be ListingAlias records")
            if listing.security_id in seen:
                raise IdentityError(f"{self.company_id}: duplicate security_id {listing.security_id}")
            seen.add(listing.security_id)
        object.__setattr__(self, "listings", listings)
        object.__setattr__(self, "external_ids", dict(self.external_ids or {}))

    @property
    def cik(self) -> str:
        return self.company_id.split(":", 1)[1]

    def listings_at(self, asof: date) -> tuple[ListingAlias, ...]:
        return tuple(listing for listing in self.listings if listing.covers(asof))

    def security_ids_at(self, asof: date) -> tuple[str, ...]:
        return tuple(listing.security_id for listing in self.listings_at(asof))

    def tickers_at(self, asof: date) -> tuple[str, ...]:
        return tuple(listing.ticker for listing in self.listings_at(asof))

    def primary_listing_at(self, asof: date) -> ListingAlias | None:
        covering = self.listings_at(asof)
        for listing in covering:
            if listing.is_primary:
                return listing
        return covering[0] if covering else None

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": IDENTITY_SCHEMA,
            "authority": AUTHORITY,
            "company_id": self.company_id,
            "cik": self.cik,
            "display_name": self.display_name,
            "issuer_kind": self.issuer_kind,
            "fiscal_year_end_month": self.fiscal_year_end_month,
            "reporting_currency": self.reporting_currency,
            "external_ids": dict(self.external_ids),
            "listings": [listing.to_payload() for listing in self.listings],
        }


@dataclass(frozen=True, slots=True)
class ListingResolution:
    """The point-in-time answer to "which issuer did this symbol mean then?"."""

    company_id: str
    security_id: str
    ticker: str
    asof: date
    listing: ListingAlias


class IssuerRegistry:
    """Point-in-time ticker → issuer resolution over a set of issuers."""

    def __init__(self, issuers: Iterable[IssuerIdentity] = ()) -> None:
        self._issuers: dict[str, IssuerIdentity] = {}
        self._by_ticker: dict[str, list[tuple[str, ListingAlias]]] = {}
        for issuer in issuers:
            self.register(issuer)

    def __len__(self) -> int:
        return len(self._issuers)

    def __iter__(self) -> Iterator[IssuerIdentity]:
        return iter(self._issuers.values())

    def register(self, issuer: IssuerIdentity) -> None:
        if issuer.company_id in self._issuers:
            raise IdentityError(f"issuer already registered: {issuer.company_id}")
        for listing in issuer.listings:
            for other_company_id, other in self._by_ticker.get(listing.ticker, ()):
                if other.overlaps(listing):
                    raise IdentityError(
                        f"{listing.ticker} is claimed by both {other_company_id} and "
                        f"{issuer.company_id} over overlapping windows"
                    )
        self._issuers[issuer.company_id] = issuer
        for listing in issuer.listings:
            self._by_ticker.setdefault(listing.ticker, []).append((issuer.company_id, listing))

    def issuer(self, company_id: object) -> IssuerIdentity:
        key = company_id_for_cik(company_id)
        try:
            return self._issuers[key]
        except KeyError:
            raise IdentityError(f"unknown issuer: {key}") from None

    def get(self, company_id: object) -> IssuerIdentity | None:
        try:
            return self.issuer(company_id)
        except IdentityError:
            return None

    def resolve_ticker(self, ticker: object, *, asof: object) -> ListingResolution | None:
        """Resolve a symbol as of a date, or return ``None``.

        ``None`` is a typed absence the caller must render, not an error to
        swallow: a symbol with no alias covering ``asof`` genuinely did not
        belong to anyone we know at that instant.
        """
        symbol = safe_ticker(ticker)
        when = _as_date(asof, field_name="asof")
        matches = [
            (company_id, listing)
            for company_id, listing in self._by_ticker.get(symbol, ())
            if listing.covers(when)
        ]
        if not matches:
            return None
        if len(matches) > 1:
            owners = sorted({company_id for company_id, _ in matches})
            raise IdentityError(
                f"{symbol} resolves to {len(owners)} issuers at {when.isoformat()}: {owners}"
            )
        company_id, listing = matches[0]
        return ListingResolution(
            company_id=company_id,
            security_id=listing.security_id,
            ticker=symbol,
            asof=when,
            listing=listing,
        )

    def siblings_of(self, ticker: object, *, asof: object) -> tuple[str, ...]:
        """Every ticker of the issuer that owned ``ticker`` at ``asof``.

        This is the measurable form of docket §4.2 rule 4: the sibling set is
        what a listing-keyed scheme counts twice.
        """
        resolved = self.resolve_ticker(ticker, asof=asof)
        if resolved is None:
            return ()
        return self.issuer(resolved.company_id).tickers_at(_as_date(asof, field_name="asof"))
