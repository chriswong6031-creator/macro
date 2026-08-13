"""Price canonicalization — the flagship fix (Data OS §D4).

NAMING LAW: **no stored price column may be named ``close``, ``price`` or ``value``
without a basis suffix.**  Columns are ``{field}_{basis}``.

WHY.  Today, same ticker, same date, three stores, FOUR numbers, all called some form
of "close" (measured, NVDA 2024-06-03)::

    data/stocks/NVDA.parquet            close        114.80   true basis: close_tradj
    data/yahoo/NVDA.parquet             close        114.80   true basis: close_tradj
    data/yahoo/NVDA.parquet             close_price  115.00   true basis: close_sadj
    data/massive_stock_day/NVDA.parquet close       1150.00   true basis: close_raw

``collectors/yahoo.py`` documents this correctly — but only in a docstring, and the
names invert intuition: ``close`` is the total-return series while ``close_price`` is
the traded basis, described in-repo as "the correct basis for all structure math
(ZigZag, detrended osc, DCL/failed-cycle, drawdown-from-ATH)".  ``data/stocks/*.parquet``
carries only the ``_tradj`` series, so the basis the house itself calls correct for
structure math is ABSENT from the store that 132 files read.  And ``data/stocks`` has
no ``open`` column at all.

A column name that does not say its basis is not a naming preference — it is an
unlabelled unit.  ``DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`` is the in-repo precedent
that this is a stop-ship event, not a tidiness complaint: an entire CN limit-alpha
program was stopped because a vendor-*adjusted* price was used where the exchange's
*raw print* was the only lawful input.  A limit-up test against an adjusted tape does
not fail loudly; it answers a slightly different question, forever.

ADJUSTED PRICES ARE POINT-IN-TIME QUANTITIES.  A series adjusted today differs from
the same series adjusted a year ago, because a corporate action since then re-scaled
all prior history.  Therefore an adjusted series is reproducible ONLY if the
adjustment vintage is recorded — every adjusted dataset carries ``adjustment_asof``
(see ``lib/dataos/temporal.py`` for why an unrecorded vintage is a silent
latest-value read) — and the only fully reproducible storage is ``_raw`` plus a
corporate-action factor table, with ``_sadj``/``_tradj`` derived on read.

Migration is staged because the blast radius is 132 files: **V1 labels** (the registry
declares each store's true basis, a reader shim exposes basis-suffixed names, a guard
forbids new unqualified ``close``); **V2 stores raw + factors** and derives.  This
module is the V1 vocabulary.

SESSION AND VENUE ARE PART OF PRICE IDENTITY, not metadata.  A consolidated-tape last
print is NOT the official closing auction price, and today nothing in the schema
distinguishes them — hence :class:`Session` and :class:`VenueScope`.

STDLIB ONLY.
"""
from __future__ import annotations

from enum import Enum, StrEnum

__all__ = [
    "PriceError",
    "AdjustmentBasis",
    "PriceField",
    "Session",
    "VenueScope",
    "canonical_column",
    "parse_column",
    "AMBIGUOUS_NAMES",
    "is_ambiguous",
    "KNOWN_STORE_BASES",
    "STORES_WITHOUT_OPEN",
]


class PriceError(ValueError):
    """A price column name that does not declare what it is."""


class AdjustmentBasis(StrEnum):
    """What a price number has already been divided by (§D4).

    ``StrEnum`` so the member IS the column suffix — ``f"close_{basis}"`` cannot
    drift from :func:`canonical_column`.
    """

    RAW = "raw"
    SADJ = "sadj"
    TRADJ = "tradj"

    @property
    def describes(self) -> str:
        """One prose line: what this number actually is."""
        return _BASIS_PROSE[self][0]

    @property
    def lawful_for(self) -> tuple[str, ...]:
        """Uses this basis is the CORRECT input for."""
        return _BASIS_PROSE[self][1]

    @property
    def unlawful_for(self) -> tuple[str, ...]:
        """Uses this basis silently answers a different question for.

        Not "discouraged" — ``DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`` is the
        precedent that one of these entries already cost a whole program.
        """
        return _BASIS_PROSE[self][2]


_BASIS_PROSE: dict[AdjustmentBasis, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    AdjustmentBasis.RAW: (
        "the price actually printed on the exchange, in quote currency, unadjusted",
        (
            "limit-price and tick-size work",
            "exchange-rule tests (limit-up/limit-down, price bands)",
            "execution simulation",
            "accounting and tax lots",
        ),
        (
            "multi-year return math (a split makes the series discontinuous)",
        ),
    ),
    AdjustmentBasis.SADJ: (
        "split and share-count adjusted only — a continuous quantity series that "
        "still tracks the traded price level",
        (
            "structure math (ZigZag, detrended oscillators, DCL/failed-cycle)",
            "technical levels and drawdown-from-ATH",
            "chart continuity",
        ),
        (
            "performance attribution (distributions are missing, so total return is understated)",
        ),
    ),
    AdjustmentBasis.TRADJ: (
        "total-return adjusted — splits plus distributions reinvested",
        (
            "performance and return math",
            "benchmark-relative attribution",
        ),
        (
            "anything compared against a printed price (a level nobody ever traded at)",
            "limit-price / exchange-rule work — see DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT",
        ),
    ),
}


class PriceField(StrEnum):
    """Which price on the bar/quote (§D4)."""

    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    LAST = "last"
    VWAP = "vwap"
    SETTLE = "settle"
    BID = "bid"
    ASK = "ask"
    MID = "mid"


class Session(StrEnum):
    """Which trading session produced the print (§D4) — part of identity, not metadata."""

    PRE = "pre"
    REGULAR = "regular"
    POST = "post"
    OVERNIGHT = "overnight"
    AUCTION_OPEN = "auction_open"
    AUCTION_CLOSE = "auction_close"


class VenueScope(Enum):
    """Whose tape the print came off (§D4).

    ``PRIMARY`` is the listing venue's own book — the only source of an official
    closing auction price.  ``CONSOLIDATED`` is the aggregated tape, whose last print
    is frequently an off-exchange trade at a different price and a different instant.
    Nothing in the schema distinguishes them today, which is why this exists.
    """

    PRIMARY = "primary"
    CONSOLIDATED = "consolidated"


def canonical_column(field: PriceField | str, basis: AdjustmentBasis | str) -> str:
    """``(CLOSE, TRADJ)`` -> ``"close_tradj"``.  The only lawful stored name."""
    f = field if isinstance(field, PriceField) else _coerce(PriceField, field, "price field")
    b = basis if isinstance(basis, AdjustmentBasis) else _coerce(
        AdjustmentBasis, basis, "adjustment basis"
    )
    return f"{f.value}_{b.value}"


def _coerce(enum_cls, value, label: str):
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError as exc:
        allowed = ", ".join(m.value for m in enum_cls)
        raise PriceError(f"unknown {label} {value!r} (known: {allowed})") from exc


def parse_column(name: str) -> tuple[PriceField, AdjustmentBasis]:
    """Inverse of :func:`canonical_column`.

    Raises :class:`PriceError` on anything that is not exactly ``{field}_{basis}`` —
    including the ambiguous legacy names, whose whole problem is that no honest
    ``(field, basis)`` pair can be recovered from them.
    """
    if not isinstance(name, str):
        raise PriceError(f"column name must be a string, got {type(name).__name__}")
    text = name.strip().lower()
    if "_" not in text:
        raise PriceError(
            f"{name!r} carries no basis suffix — a bare price name is an unlabelled unit "
            f"(§D4 naming law); expected one of {{field}}_{{raw|sadj|tradj}}"
        )
    field_part, _, basis_part = text.rpartition("_")
    try:
        field = PriceField(field_part)
        basis = AdjustmentBasis(basis_part)
    except ValueError as exc:
        raise PriceError(
            f"{name!r} is not a canonical price column — expected {{field}}_{{basis}} with "
            f"field in ({', '.join(m.value for m in PriceField)}) and basis in "
            f"({', '.join(m.value for m in AdjustmentBasis)})"
        ) from exc
    return field, basis


#: Names that name a number without naming what the number IS.  Every one of these
#: is live in the tree today and means a DIFFERENT basis depending on which store you
#: opened — ``close`` alone means ``close_tradj`` in ``data/stocks`` and ``data/yahoo``
#: but ``close_raw`` in ``data/massive_stock_day``.
AMBIGUOUS_NAMES: frozenset[str] = frozenset(
    {"close", "price", "value", "last", "px", "close_price", "adj_close", "adjclose"}
)


def is_ambiguous(name: str) -> bool:
    """True when a column name does not declare its adjustment basis.

    Case- and whitespace-insensitive; ``"close_tradj"`` is False because it says what
    it is, ``"Close"`` is True because it does not.
    """
    if not isinstance(name, str):
        return False
    return name.strip().lower() in AMBIGUOUS_NAMES


#: MEASURED truth of the stores that exist today — documentation as code, keyed
#: ``"<store>:<stored column name>"``.  Source: the §D4 measurement quoted in this
#: module's docstring (NVDA 2024-06-03: data/stocks close 114.80, data/yahoo close
#: 114.80, data/yahoo close_price 115.00, data/massive_stock_day close 1150.00).
#:
#: This map is what makes the V1 migration possible without touching 132 readers: a
#: shim can expose the basis-suffixed name for a store's legacy column because the
#: basis is written down here, once, from a measurement rather than from a guess.
#: Every entry needs a re-measurement before it is edited — the whole point is that
#: none of these are inferable from the column NAME.
KNOWN_STORE_BASES: dict[str, AdjustmentBasis] = {
    "data/stocks:close": AdjustmentBasis.TRADJ,
    "data/yahoo:close": AdjustmentBasis.TRADJ,
    "data/yahoo:close_price": AdjustmentBasis.SADJ,
    "data/massive_stock_day:close": AdjustmentBasis.RAW,
}

#: Stores with NO ``open`` column at all.  ``data/stocks`` is close-only, which is why
#: an OHLC-shaped read against it returns a frame that is quietly missing a leg rather
#: than raising.
STORES_WITHOUT_OPEN: frozenset[str] = frozenset({"data/stocks"})
