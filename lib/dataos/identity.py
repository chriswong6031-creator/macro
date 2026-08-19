"""Identity spine — a symbol is NEVER an identity (Data OS §D2).

WHY THIS FILE EXISTS.  ``lib/ticker_aliases.py`` records the incident in its own
docstring: Marsh McLennan changed its NYSE symbol MMC -> MRSH on 2026-01-14
(symbol change only — same listing, same CUSIP, legal name unchanged), Yahoo
migrated the whole history onto MRSH, and the membership's MMC started 404-ing as
"possibly delisted, no price data found".  ``scripts/fetch_basket_extras`` carried
the MMC->MRSH entry while its sibling ``scripts/fetch_basket_ohlcv`` carried only
FI->FISV, so **data/baskets/ohlcv/MMC.parquet came to never exist**: the deep store
skipped Marsh on every run since the store was created (2026-06-19), and for the
seven months after the rename the ``insurance`` basket rendered on 18/19 members and
``us_sector_financials`` on 75/76.  Nothing went red.  The site simply drew one
fewer line.

That is a 7-month silent production loss caused by a two-entry dict living in one
collector and not its sibling.  The repair in that file was the right local repair —
ONE map, imported by every lane.  This module is the general form of it: an identity
that does not move when a symbol moves, and a time-scoped alias table that can answer
"what did this vendor call this security on that date" instead of "what does it call
it now".

THE SHAPES (§D2), and why each is what it is:

    Issuer    ``ISS:<inception listing key>``   ISS:US-XNYS-MMC
    Security  ``SEC:<inception listing key>``   SEC:US-XNYS-MMC
    Listing   ``<CC>-<MIC>-<CODE>``  (bare)     US-XNYS-MMC
    Symbol    a plain string, venue+time scoped MRSH today, MMC before 2026-01-14
    Vendor id an alias ROW, never a key         yahoo:MRSH

* Bare ``<CC>-<MIC>-<CODE>`` is **already in production** for the China estate
  (``CN-XSHG-600519``, ``CN-XSHE-000001``, ``CN-XBSE-920163``, per
  ``research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md``).  Adopting it
  unchanged means zero migration there.
* The two genuinely-new and easily-conflated concepts (issuer, security) carry a
  VISIBLE type prefix, so a grep, a parquet dump or a log line tells you which
  concept you are holding.  Type-visibility is what makes misuse hard, which is the
  whole point.
* ``<CODE>`` is the code the listing carried **at inception**, never the current one.
  That is what makes the id survive the exact event that motivates the project:
  Marsh stays ``US-XNYS-MMC`` after MMC->MRSH; Fiserv stays ``US-XNAS-FISV`` after
  FISV->FI.
* **No allocator, no counter, no hash.**  Two parallel sessions minting the same
  security independently produce the SAME id.  This repo routinely runs 20+
  concurrent worktrees; a sequential counter would be a permanent merge-conflict
  surface.
* Ticker reuse on the same venue after a delisting is the one collision case:
  disambiguate explicitly with a ``.2`` suffix (``US-XNYS-MMC.2``).  Rare, greppable,
  never silent.

MINT ONCE AND STORE.  The derivation here is the *allocator*; the value written into
the master is the *authority*.  A later correction to inception facts never re-mints —
it appends an alias row.  This mirrors the CN spine's generation-atomic pointer
promotion and satisfies ``DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY`` (no run clock ever
enters identity).

STDLIB ONLY.  Imported by thin CI lanes and by collectors that must not pay a pandas
import to translate a ticker.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum

__all__ = [
    "IdentityError",
    "XNYS", "XNAS", "XASE", "XSHG", "XSHE", "XBSE", "XHKG", "XTSE", "XTSX",
    "KNOWN_MICS",
    "ListingKey",
    "parse_listing_key",
    "security_id",
    "issuer_id",
    "listing_id",
    "parse_id",
    "option_contract_id",
    "parse_option_contract_id",
    "future_id",
    "parse_future_id",
    "index_id",
    "parse_index_id",
    "fx_id",
    "parse_fx_id",
    "CNBoard",
    "cn_board",
    "is_legacy_bse_code",
    "normalize_cn_symbol",
    "normalize_hk_symbol",
    "AliasRow",
    "VendorAliasTable",
    "SecurityIssuerRow",
    "IssuerMaster",
]


class IdentityError(ValueError):
    """A string that cannot be a lawful identity.

    Deliberately a ``ValueError`` subclass: every raise site here is "you handed me
    a malformed id", and callers that already guard parsing with ``except
    ValueError`` keep working.  It is a raise and never a ``None`` return, because a
    silently-degraded identity is the failure class this module exists to end.
    """


# ── MIC (ISO 10383) — the venue authority, §D2 ────────────────────────────────
# Only the venues this repo actually carries.  The list is deliberately CLOSED:
# minting an id on an unknown venue is a decision a human makes once, in a diff,
# not something a normalizer guesses at 03:00 during a nightly.
XNYS = "XNYS"   # New York Stock Exchange
XNAS = "XNAS"   # Nasdaq
XASE = "XASE"   # NYSE American (ex-AMEX)
XSHG = "XSHG"   # Shanghai Stock Exchange
XSHE = "XSHE"   # Shenzhen Stock Exchange
XBSE = "XBSE"   # Beijing Stock Exchange
XHKG = "XHKG"   # Hong Kong Exchanges
XTSE = "XTSE"   # Toronto Stock Exchange
XTSX = "XTSX"   # TSX Venture Exchange

KNOWN_MICS: frozenset[str] = frozenset(
    {XNYS, XNAS, XASE, XSHG, XSHE, XBSE, XHKG, XTSE, XTSX}
)

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
# A listing CODE may carry '.' and '-' (BRK.B, BRK-B): both are real US class
# suffixes.  A '.'-plus-DIGITS tail is the disambiguator and is stripped before
# this pattern is applied, so 'BRK.B' stays one code while 'MMC.2' does not.
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*$")
_DISAMBIGUATOR_RE = re.compile(r"^(?P<code>.+)\.(?P<n>[0-9]+)$")


@dataclass(frozen=True, slots=True)
class ListingKey:
    """One security on one venue: ``<CC>-<MIC>-<CODE>[.N]``.

    ``code`` is the INCEPTION code, never today's symbol — see the module
    docstring.  ``disambiguator`` is ``None`` for the first listing to ever carry
    this code on this venue, and an integer >= 2 for a later reuse of a retired
    ticker (``US-XNYS-MMC.2``).  ``.1`` is rejected rather than accepted-as-first:
    two spellings of one identity is exactly the ambiguity this type removes.
    """

    country: str
    mic: str
    code: str
    disambiguator: int | None = None

    def __post_init__(self) -> None:
        if not _COUNTRY_RE.match(self.country or ""):
            raise IdentityError(
                f"country must be a 2-letter ISO 3166-1 alpha-2 code, got {self.country!r}"
            )
        if self.mic not in KNOWN_MICS:
            raise IdentityError(
                f"unknown MIC {self.mic!r} — the venue list in lib/dataos/identity.py is "
                f"closed on purpose; add it there with a comment naming the estate that "
                f"needs it. Known: {', '.join(sorted(KNOWN_MICS))}"
            )
        if not _CODE_RE.match(self.code or ""):
            raise IdentityError(
                f"listing code must be uppercase alphanumeric (with '.'/'-' for class "
                f"suffixes), got {self.code!r}"
            )
        if self.disambiguator is not None:
            if isinstance(self.disambiguator, bool) or not isinstance(self.disambiguator, int):
                raise IdentityError(
                    f"disambiguator must be an int >= 2, got {self.disambiguator!r}"
                )
            if self.disambiguator < 2:
                raise IdentityError(
                    "disambiguator starts at 2 — the FIRST listing to carry a code is "
                    f"unsuffixed, so '.{self.disambiguator}' would be a second spelling "
                    "of the same identity"
                )

    def render(self) -> str:
        """The bare listing key: ``US-XNYS-MMC`` / ``US-XNYS-MMC.2``."""
        tail = f".{self.disambiguator}" if self.disambiguator is not None else ""
        return f"{self.country}-{self.mic}-{self.code}{tail}"

    def __str__(self) -> str:  # so an f-string can never print the repr by accident
        return self.render()


def parse_listing_key(text: str) -> ListingKey:
    """``"US-XNYS-MMC.2"`` -> ``ListingKey('US', 'XNYS', 'MMC', 2)``.

    Splits on the FIRST TWO hyphens only: the code itself may contain one
    (``US-XNYS-BRK-B``).  A trailing ``.<digits>`` is the disambiguator; any other
    dotted tail (``BRK.B``) stays part of the code.
    """
    if not isinstance(text, str):
        raise IdentityError(f"listing key must be a string, got {type(text).__name__}")
    raw = text.strip()
    parts = raw.split("-", 2)
    if len(parts) != 3 or not all(parts):
        raise IdentityError(
            f"malformed listing key {text!r} — expected <CC>-<MIC>-<CODE>[.N], "
            "e.g. US-XNYS-MMC or CN-XSHG-600519"
        )
    country, mic, tail = parts
    disambiguator: int | None = None
    m = _DISAMBIGUATOR_RE.match(tail)
    if m:
        tail = m.group("code")
        disambiguator = int(m.group("n"))
    return ListingKey(country.upper(), mic.upper(), tail.upper(), disambiguator)


def _as_listing_key(value: ListingKey | str) -> ListingKey:
    return value if isinstance(value, ListingKey) else parse_listing_key(value)


def listing_id(listing_key: ListingKey | str) -> str:
    """The bare listing id — ``US-XNYS-MMC``.  Deliberately un-prefixed (§D2)."""
    return _as_listing_key(listing_key).render()


def security_id(listing_key: ListingKey | str) -> str:
    """``SEC:US-XNYS-MMC`` — the legal instrument / share class."""
    return f"SEC:{_as_listing_key(listing_key).render()}"


def issuer_id(listing_key: ListingKey | str) -> str:
    """``ISS:US-XNYS-MMC`` — the economic entity behind the security."""
    return f"ISS:{_as_listing_key(listing_key).render()}"


_ID_PREFIXES = {"ISS": "issuer", "SEC": "security"}


def parse_id(text: str) -> tuple[str, ListingKey]:
    """``"SEC:US-XNYS-MMC"`` -> ``("security", ListingKey(...))``.

    ``kind`` is one of ``issuer`` / ``security`` / ``listing``.  Instrument-class
    ids (``OPT:``/``FUT:``/``IDX:``/``FX:``) are NOT listing keys and raise here —
    they have their own parsers, and returning a half-truth for them is how a
    concept confusion gets written to a store.
    """
    if not isinstance(text, str):
        raise IdentityError(f"id must be a string, got {type(text).__name__}")
    raw = text.strip()
    if ":" not in raw:
        return "listing", parse_listing_key(raw)
    prefix, _, rest = raw.partition(":")
    kind = _ID_PREFIXES.get(prefix.upper())
    if kind is None:
        raise IdentityError(
            f"{prefix!r} is not an issuer/security prefix — {raw!r} is not a listing "
            "identity. OPT:/FUT:/IDX:/FX: have their own parsers."
        )
    return kind, parse_listing_key(rest)


# ── Instrument classes (§D2) ──────────────────────────────────────────────────
_RIGHTS = ("C", "P")
_STRIKE_SCALE = Decimal(1000)
_STRIKE_DIGITS = 8
_OPTION_RE = re.compile(
    r"^OPT:(?P<listing>[^:]+):(?P<expiry>[0-9]{8}):(?P<right>[CP]):(?P<strike>[0-9]{8})$"
)
_FUTURE_RE = re.compile(r"^FUT:(?P<mic>[A-Z0-9]{4}):(?P<root>[A-Z0-9]+):(?P<month>[0-9]{6})$")
_INDEX_RE = re.compile(r"^IDX:(?P<provider>[A-Z0-9]+)-(?P<code>[A-Z0-9.]+)$")
_FX_RE = re.compile(r"^FX:(?P<base>[A-Z]{3})(?P<quote>[A-Z]{3})$")


def _strike_decimal(strike: Decimal | str | int) -> Decimal:
    """Coerce a strike to Decimal, REFUSING float.

    ``float`` is rejected rather than converted because a binary float on a strike
    is a correctness bug, not a formatting preference: 250.10 is not representable,
    so ``Decimal(250.10) * 1000`` is 250099.99999999997 and the id silently becomes
    a different contract.  Pass ``Decimal("250.10")`` or the string ``"250.10"``.
    """
    if isinstance(strike, float):
        raise IdentityError(
            "strike must be Decimal/str/int, never float — binary float cannot "
            f"represent most strikes exactly (got {strike!r}); pass Decimal(\"{strike}\")"
        )
    if isinstance(strike, Decimal):
        return strike
    try:
        return Decimal(str(strike).strip())
    except (InvalidOperation, ValueError) as exc:
        raise IdentityError(f"strike {strike!r} is not a decimal number") from exc


def option_contract_id(
    underlying_listing_key: ListingKey | str,
    expiry: date,
    right: str,
    strike: Decimal | str | int,
) -> str:
    """``OPT:US-XNAS-AAPL:20260918:C:00250000`` (§D2).

    Strike is carried as ``strike x 1000``, zero-padded to 8 digits, so a
    tenth-of-a-cent strike is exact and lexical order is numeric order.  The OCC/OSI
    symbol and any vendor contract id are ALIASES of this, never the key.
    """
    lk = _as_listing_key(underlying_listing_key)
    if not isinstance(expiry, date):
        raise IdentityError(f"expiry must be a datetime.date, got {type(expiry).__name__}")
    r = str(right).strip().upper()
    if r not in _RIGHTS:
        raise IdentityError(f"right must be 'C' or 'P', got {right!r}")
    scaled = _strike_decimal(strike) * _STRIKE_SCALE
    if scaled != scaled.to_integral_value():
        raise IdentityError(
            f"strike {strike!r} is finer than a tenth of a cent — x1000 leaves {scaled}, "
            "which this id form cannot carry without rounding"
        )
    units = int(scaled)
    if units <= 0 or units >= 10 ** _STRIKE_DIGITS:
        raise IdentityError(
            f"strike {strike!r} out of range for an {_STRIKE_DIGITS}-digit x1000 field "
            f"(0 < strike < {10 ** _STRIKE_DIGITS / 1000:g})"
        )
    return (
        f"OPT:{lk.render()}:{expiry.strftime('%Y%m%d')}:{r}:{units:0{_STRIKE_DIGITS}d}"
    )


def parse_option_contract_id(text: str) -> tuple[ListingKey, date, str, Decimal]:
    """Inverse of :func:`option_contract_id` -> ``(underlying, expiry, right, strike)``.

    The strike comes back as a ``Decimal`` scaled down by 1000, so
    ``parse(option_contract_id(...))`` round-trips exactly for every strike the
    forward direction accepted.
    """
    if not isinstance(text, str):
        raise IdentityError(f"option id must be a string, got {type(text).__name__}")
    m = _OPTION_RE.match(text.strip())
    if not m:
        raise IdentityError(
            f"malformed option contract id {text!r} — expected "
            "OPT:<listing key>:<YYYYMMDD>:<C|P>:<strike x1000, 8 digits>"
        )
    lk = parse_listing_key(m.group("listing"))
    raw = m.group("expiry")
    try:
        expiry = date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError as exc:
        raise IdentityError(f"option id {text!r} carries an impossible expiry {raw!r}") from exc
    strike = Decimal(m.group("strike")) / _STRIKE_SCALE
    return lk, expiry, m.group("right"), strike


def future_id(mic: str, root: str, contract_month: str | date) -> str:
    """``FUT:XCBF:VX:202609`` — venue, root, delivery month (§D2).

    ``contract_month`` is ``"YYYYMM"`` or any ``date`` in that month.  The MIC is
    NOT validated against :data:`KNOWN_MICS`: the futures estate touches venues no
    equity listing here does, and a normalizer that refuses an unfamiliar futures
    venue would block work it has no authority over.
    """
    m = str(mic).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", m):
        raise IdentityError(f"future MIC must be 4 alphanumerics, got {mic!r}")
    r = str(root).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]+", r):
        raise IdentityError(f"future root must be alphanumeric, got {root!r}")
    if isinstance(contract_month, date):
        month = contract_month.strftime("%Y%m")
    else:
        month = str(contract_month).strip()
        if not re.fullmatch(r"[0-9]{6}", month) or not 1 <= int(month[4:6]) <= 12:
            raise IdentityError(f"contract month must be YYYYMM, got {contract_month!r}")
    return f"FUT:{m}:{r}:{month}"


def parse_future_id(text: str) -> tuple[str, str, str]:
    """Inverse of :func:`future_id` -> ``(mic, root, "YYYYMM")``."""
    m = _FUTURE_RE.match(str(text).strip())
    if not m or not 1 <= int(m.group("month")[4:6]) <= 12:
        raise IdentityError(
            f"malformed future id {text!r} — expected FUT:<MIC>:<root>:<YYYYMM>"
        )
    return m.group("mic"), m.group("root"), m.group("month")


def index_id(provider: str, code: str) -> str:
    """``IDX:SPDJI-SPX`` — the index PROVIDER is part of the identity (§D2).

    Two providers publish differently-constructed indices under colliding short
    codes; dropping the provider is how "the S&P 500" silently becomes whichever
    vendor answered.
    """
    p = str(provider).strip().upper()
    c = str(code).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]+", p):
        raise IdentityError(f"index provider must be alphanumeric, got {provider!r}")
    if not re.fullmatch(r"[A-Z0-9.]+", c):
        raise IdentityError(f"index code must be alphanumeric, got {code!r}")
    return f"IDX:{p}-{c}"


def parse_index_id(text: str) -> tuple[str, str]:
    """Inverse of :func:`index_id` -> ``(provider, code)``."""
    m = _INDEX_RE.match(str(text).strip())
    if not m:
        raise IdentityError(f"malformed index id {text!r} — expected IDX:<provider>-<code>")
    return m.group("provider"), m.group("code")


def fx_id(base: str, quote: str) -> str:
    """``FX:USDCNH`` — ordered pair, base first (§D2)."""
    b = str(base).strip().upper()
    q = str(quote).strip().upper()
    for label, cur in (("base", b), ("quote", q)):
        if not re.fullmatch(r"[A-Z]{3}", cur):
            raise IdentityError(f"fx {label} must be a 3-letter code, got {cur!r}")
    if b == q:
        raise IdentityError(f"fx pair needs two different currencies, got {b}/{q}")
    return f"FX:{b}{q}"


def parse_fx_id(text: str) -> tuple[str, str]:
    """Inverse of :func:`fx_id` -> ``(base, quote)``."""
    m = _FX_RE.match(str(text).strip())
    if not m:
        raise IdentityError(f"malformed fx id {text!r} — expected FX:<BASE><QUOTE>")
    return m.group("base"), m.group("quote")


# ── China A-share normalization (§D2) ─────────────────────────────────────────
# The REAL divergence measured here: TuShare emits `600519.SH` while the repository
# ticker is `600519.SS` (research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:
# "Repository tickers are 600519.SS, 000001.SZ and 920163.BJ ... stable IDs are
# CN-XSHG-600519, CN-XSHE-000001, CN-XBSE-920163").  Two spellings of one listing,
# one of which is also a legitimate US-vendor suffix, is precisely the class of
# ambiguity that has to die at the boundary rather than inside a join.

class CNBoard(Enum):
    """Which A-share board a code belongs to.

    The ranges are NOT inferred here — they are the spine contract's, verbatim:
    "SH 688/689 is STAR; the official SZ 300000-309999 allocation is ChiNext
    (including the 309800-309999 CDR range); BJ is BSE; other admitted A code
    families are main board."

    ``BSE`` is reachable ONLY from a canonical ``920xxx`` code.  The old BJ families
    are aliases and are refused rather than classified — :func:`is_legacy_bse_code`.
    """

    MAIN = "MAIN"
    STAR = "STAR"
    CHINEXT = "CHINEXT"
    BSE = "BSE"


_CN_SUFFIX_MICS = {
    "SH": XSHG,   # TuShare / exchange spelling
    "SS": XSHG,   # repository ticker + Yahoo spelling — the divergence, §D2
    "SZ": XSHE,
    "BJ": XBSE,
}
_CN_CODE_RE = re.compile(r"^[0-9]{6}$")


def is_legacy_bse_code(code: str) -> bool:
    """Is this a pre-920xxx BJ code family — i.e. an ALIAS, never a canonical key?

    The 4xxxxx / 8xxxxx families (43xxxx, 83xxxx, 87xxxx, 88xxxx and the old
    third-board 40xxxx/42xxxx transfers) are the codes a BSE listing carried before
    the 920xxx allocation.  The spine contract is explicit and says it twice: "Old BJ
    codes remain aliases. Every canonical BSE mapping target must be ``920xxx``", and
    "other admitted A code families are main board"
    (research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:89-92).
    """
    c = str(code).strip()
    return bool(_CN_CODE_RE.match(c)) and c.startswith(("4", "8"))


def _refuse_legacy_bse(code: str, symbol: object = None) -> None:
    """Raise for an alias code.  Called before ANY key is minted from one.

    WHY REFUSE RATHER THAN CLASSIFY.  Returning ``CNBoard.BSE`` here read as harmless
    — the listing really is on the BSE — but it fed ``_cn_mic_from_code`` -> ``XBSE``
    and minted ``CN-XBSE-430047`` as a CANONICAL key.  That is two identities for one
    security: ``SEC:CN-XBSE-920163`` from the canonical feed and
    ``SEC:CN-XBSE-430047`` from a legacy TuShare pull, joining as different securities
    in the security master with neither side visibly wrong.  It is the exact
    duplicate-identity failure this module was written to end, produced by the module.

    This file holds no ``bse_mapping`` table, so it has no authority to resolve the
    alias to its 920xxx target; that is the alias table's job.  Fail closed, which is
    what the rest of the file already does when it is handed two facts it cannot
    reconcile.
    """
    shown = symbol if symbol is not None else code
    raise IdentityError(
        f"{shown!r} is an old BJ code family (4xxxxx/8xxxxx) — those are ALIASES, and "
        "every canonical BSE mapping target must be 920xxx (CN spine contract). This "
        "module has no bse_mapping table and will not mint a canonical key from an "
        "alias; resolve it through the vendor alias table first."
    )


def cn_board(code: str) -> CNBoard:
    """Board for a 6-digit A-share code, per the spine contract's ranges.

    RAISES on an old BJ alias code — see :func:`_refuse_legacy_bse`.  It is not that
    the board is unknown (it is the BSE); it is that answering at all invites the
    caller to key on the code, which is precisely the defect.
    """
    c = str(code).strip()
    if not _CN_CODE_RE.match(c):
        raise IdentityError(f"A-share code must be 6 digits, got {code!r}")
    if c.startswith(("688", "689")):
        return CNBoard.STAR
    if 300000 <= int(c) <= 309999:
        return CNBoard.CHINEXT
    if c.startswith("920"):
        return CNBoard.BSE
    if is_legacy_bse_code(c):
        _refuse_legacy_bse(c)
    return CNBoard.MAIN


def _cn_mic_from_code(code: str) -> str:
    board = cn_board(code)
    if board is CNBoard.STAR:
        return XSHG
    if board is CNBoard.CHINEXT:
        return XSHE
    if board is CNBoard.BSE:
        return XBSE
    if code.startswith(("6", "9")):     # 6xxxxx main board, 900xxx SH B-shares
        return XSHG
    if code.startswith(("0", "2", "3")):  # 00xxxx/30xxxx main board, 200xxx SZ B-shares
        return XSHE
    raise IdentityError(
        f"A-share code {code!r} is in no admitted family (SH 6/9, SZ 0/2/3, BJ 920) — "
        "pass an explicit .SH/.SS/.SZ/.BJ suffix if this is a real listing"
    )


def normalize_cn_symbol(symbol: str) -> ListingKey:
    """Any in-the-wild A-share spelling -> the canonical ``CN-<MIC>-<code>`` key.

    Accepts ``600519.SH`` (TuShare), ``600519.SS`` (repository ticker / Yahoo),
    ``600519`` (bare), ``sh600519`` (EastMoney-style prefix), and the ``.SZ`` /
    ``.BJ`` families, in any case and with surrounding whitespace.

    An explicit venue suffix is CROSS-CHECKED against the code range and a conflict
    RAISES: ``600519.SZ`` is not a Shenzhen listing with a typo, it is two facts that
    cannot both be true, and picking one silently is how a Shanghai tape ends up
    stored under a Shenzhen key.
    """
    if not isinstance(symbol, str):
        raise IdentityError(f"CN symbol must be a string, got {type(symbol).__name__}")
    raw = symbol.strip().upper()
    if not raw:
        raise IdentityError("CN symbol is empty")
    declared: str | None = None
    if "." in raw:
        code, _, suffix = raw.partition(".")
        declared = _CN_SUFFIX_MICS.get(suffix)
        if declared is None:
            raise IdentityError(
                f"unknown A-share venue suffix {suffix!r} in {symbol!r} "
                f"(known: {', '.join(sorted(_CN_SUFFIX_MICS))})"
            )
    elif raw[:2] in _CN_SUFFIX_MICS and len(raw) == 8:
        declared = _CN_SUFFIX_MICS[raw[:2]]
        code = raw[2:]
    else:
        code = raw
    if not _CN_CODE_RE.match(code):
        raise IdentityError(
            f"{symbol!r} does not contain a 6-digit A-share code (got {code!r})"
        )
    # BEFORE the declared-venue fallback below, which trusts an explicit suffix on an
    # unrecognised family.  That trust is right when the VENUE is the doubt and wrong
    # here: `430047.BJ` says "this is on the BSE", which is true and still does not
    # make `430047` a canonical key.
    if is_legacy_bse_code(code):
        _refuse_legacy_bse(code, symbol)
    try:
        inferred = _cn_mic_from_code(code)
    except IdentityError:
        if declared is None:
            raise
        inferred = declared   # unknown family + an explicit venue: trust the caller
    if declared is not None and declared != inferred:
        raise IdentityError(
            f"{symbol!r} declares venue {declared} but code {code} belongs to {inferred} "
            f"({cn_board(code).value} board) — refusing to guess which fact is wrong"
        )
    return ListingKey("CN", inferred, code)


def normalize_hk_symbol(symbol: str) -> ListingKey:
    """``700`` / ``0700`` / ``0700.HK`` / ``00700`` -> ``HK-XHKG-00700``.

    HKEX board lots are quoted under 1-to-5 digit codes depending on the vendor;
    the canonical form is the exchange's own 5-digit zero-padded code, so
    ``normalize_hk_symbol('700') == normalize_hk_symbol('0700.HK')``.
    """
    if not isinstance(symbol, str):
        raise IdentityError(f"HK symbol must be a string, got {type(symbol).__name__}")
    raw = symbol.strip().upper()
    if raw.endswith(".HK"):
        raw = raw[: -len(".HK")]
    raw = raw.strip()
    if not raw.isdigit() or len(raw) > 5:
        raise IdentityError(
            f"HK symbol must be up to 5 digits (optionally '.HK'-suffixed), got {symbol!r}"
        )
    if int(raw) == 0:
        raise IdentityError(f"HK code 0 is not a listing ({symbol!r})")
    return ListingKey("HK", XHKG, raw.zfill(5))


# ── Vendor alias table (§D2) — the translation layer ──────────────────────────
def _as_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise IdentityError(f"alias validity bound must be an ISO date, got {value!r}") from exc


@dataclass(frozen=True, slots=True)
class AliasRow:
    """One ``(vendor, vendor_symbol, security_id)`` binding, valid over a date range.

    ``valid_from`` is INCLUSIVE and ``valid_to`` is EXCLUSIVE — ``valid_to`` is the
    first day the row no longer holds.  An inclusive end would make the changeover
    day ambiguous (two rows valid at once on 2026-01-14, which is exactly the day
    the MMC/MRSH answer has to be unambiguous).  ``None`` on either side is an open
    bound.

    THE DATE IS THE ROW'S OWN CLOCK, AND A VENDOR SPACE DECLARES WHICH CLOCK IT RUNS
    ON.  A DATED row answers HISTORICAL NAMING — "what did this space call the
    security ON that day".  It is NOT a fetch-symbol or store-key resolver, because a
    vendor that renames typically migrates the WHOLE history onto the new name: Yahoo
    serves Marsh's entire tape under ``MRSH`` and ``data/stocks/ECHO.parquet`` holds
    EchoStar's spliced history back to 2008, so a backfill that asked a dated row what
    Yahoo called it in 2020 and then REQUESTED that answer would get "possibly
    delisted, no price data found" — the seven-month ``insurance`` 18/19 outage in a
    new costume.  The CURRENT-CATALOG question ("what string do I use today, for a bar
    of any date") is answered by a separate vendor space carrying ONE OPEN-BOUNDED row
    per security; ``config/dataset_registry.yml::reference.vendor_aliases`` names both
    families, and ``scripts/build_security_master.py`` emits them.
    """

    vendor: str
    vendor_symbol: str
    security_id: str
    valid_from: date | None = None
    valid_to: date | None = None

    def covers(self, on: date) -> bool:
        if self.valid_from is not None and on < self.valid_from:
            return False
        if self.valid_to is not None and on >= self.valid_to:
            return False
        return True

    def overlaps(self, other: "AliasRow") -> bool:
        lo = max((d for d in (self.valid_from, other.valid_from) if d is not None), default=None)
        hi = min((d for d in (self.valid_to, other.valid_to) if d is not None), default=None)
        return lo is None or hi is None or lo < hi


class VendorAliasTable:
    """Time-scoped vendor-symbol <-> security-id translation.  NO I/O.

    This is the general form of ``lib/ticker_aliases.py``.  That module holds a
    two-entry, Yahoo-only, TIMELESS dict — which is why it can say "MMC means MRSH"
    but cannot say "MMC meant MMC before 2026-01-14".  A backfill that reads history
    through a timeless map re-labels the past, and nothing downstream can see it.

    Both directions are required to be UNAMBIGUOUS in time: constructing a table
    where two rows for one ``(vendor, vendor_symbol)`` — or one
    ``(vendor, security_id)`` — overlap raises, because a translation layer that can
    return either of two answers is not a translation layer.  Loading is from plain
    mappings (:meth:`from_records`); reading a file is the caller's job, so this
    class stays importable in a lane with no filesystem.
    """

    __slots__ = ("_rows",)

    def __init__(self, rows: list[AliasRow] | tuple[AliasRow, ...] = ()) -> None:
        self._rows: tuple[AliasRow, ...] = tuple(rows)
        self._assert_unambiguous()

    @classmethod
    def from_records(cls, records) -> "VendorAliasTable":
        """Build from a list of dicts (a YAML/JSON payload the caller already read)."""
        rows: list[AliasRow] = []
        for i, rec in enumerate(records or ()):
            try:
                rows.append(
                    AliasRow(
                        vendor=str(rec["vendor"]),
                        vendor_symbol=str(rec["vendor_symbol"]),
                        security_id=str(rec["security_id"]),
                        valid_from=_as_date(rec.get("valid_from")),
                        valid_to=_as_date(rec.get("valid_to")),
                    )
                )
            except KeyError as exc:
                raise IdentityError(f"alias record {i} is missing {exc.args[0]!r}") from exc
        return cls(rows)

    @property
    def rows(self) -> tuple[AliasRow, ...]:
        return self._rows

    def _assert_unambiguous(self) -> None:
        for field in ("vendor_symbol", "security_id"):
            buckets: dict[tuple[str, str], list[AliasRow]] = {}
            for row in self._rows:
                buckets.setdefault((row.vendor, getattr(row, field)), []).append(row)
            for (vendor, value), group in buckets.items():
                for i, a in enumerate(group):
                    for b in group[i + 1:]:
                        if a.overlaps(b):
                            raise IdentityError(
                                f"ambiguous alias table: {vendor}/{value} is covered by two "
                                f"overlapping rows ({a.valid_from}..{a.valid_to} and "
                                f"{b.valid_from}..{b.valid_to}) — one of them needs a bound"
                            )

    def resolve(self, vendor: str, vendor_symbol: str, on: date) -> str | None:
        """What security did *vendor* mean by *vendor_symbol* on *on*?  ``None`` = unmapped."""
        for row in self._rows:
            if row.vendor == vendor and row.vendor_symbol == vendor_symbol and row.covers(on):
                return row.security_id
        return None

    def vendor_symbol_for(self, vendor: str, security_id_: str, on: date) -> str | None:
        """What did *vendor* call *security_id_* on *on*?  ``None`` = the vendor had no name."""
        for row in self._rows:
            if row.vendor == vendor and row.security_id == security_id_ and row.covers(on):
                return row.vendor_symbol
        return None


# ── Issuer master reader (§D2B1) — the economic-entity axis over the security master ──
def _null_to_none(value: object) -> object | None:
    """``None`` for ``None`` OR a ``float('nan')`` cell; the value unchanged otherwise.

    STDLIB-ONLY NaN check (no ``pandas`` import in this module): ``float('nan') !=
    float('nan')`` is the one universal, dependency-free way to detect it — every
    other float compares equal to itself.  See :meth:`IssuerMaster.from_records`.
    """
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # noqa: PLR0124 — the NaN test itself
        return None
    return value


@dataclass(frozen=True, slots=True)
class SecurityIssuerRow:
    """One ``security_master.parquet`` row's issuer axis, as read by :class:`IssuerMaster`.

    Carries only the columns the issuer reader needs — not a copy of the whole master
    row shape, so a future master column never forces a change here.
    """

    security_id: str
    issuer_id: str | None
    issuer_state: str
    listing_key: str


class IssuerMaster:
    """Issuer <-> security lookups over the committed security-master rows.  NO I/O.

    ``scripts/build_security_master.py`` is the ALLOCATOR/AUTHORITY for the issuer
    axis (mint-once, era-gated correction, spec D2B1 §2/§4); this class is the ONE
    canonical READER (spec §3 "Reader API" — no competing issuer allocator or reader
    anywhere else).  Construct it from the security master's rows via
    :meth:`from_records`; reading the parquet is the caller's job, exactly like
    :class:`VendorAliasTable`.

    HISTORICAL LIMITATION (spec §5).  CIK evidence is a CURRENT-registrant
    observation: the newest ``data/symbol_directory/cik_map/*.parquet`` snapshot
    proves who owns a ticker TODAY, never what the issuer mapping was on a past date
    — it does not prove what the issuer mapping was in 2015.  This reader therefore
    carries NO ``asof`` parameter and answers only "which securities does this issuer
    own, right now" / "what is this security's issuer, right now" — the answer is
    canonical for CURRENT identity and must never be read as a historical lineage
    claim.  (This is the issuer-axis analogue of the two-clock law
    :class:`VendorAliasTable` enforces for vendor symbols — a current observation
    answering a historical question is exactly the defect that class exists to
    prevent, one layer up.)
    """

    __slots__ = ("_by_security", "_by_issuer")

    def __init__(self, rows: list[SecurityIssuerRow] | tuple[SecurityIssuerRow, ...] = ()) -> None:
        by_security: dict[str, SecurityIssuerRow] = {}
        by_issuer: dict[str, list[str]] = {}
        for row in rows:
            by_security[row.security_id] = row
            if row.issuer_id is not None:
                by_issuer.setdefault(row.issuer_id, []).append(row.security_id)
        self._by_security = by_security
        self._by_issuer: dict[str, tuple[str, ...]] = {
            k: tuple(sorted(v)) for k, v in by_issuer.items()
        }

    @classmethod
    def from_records(cls, records) -> "IssuerMaster":
        """Build from a list of dicts — a ``security_master.parquet`` read the caller
        already did (``to_dict("records")`` or equivalent).

        NaN-SAFE WITHOUT PANDAS (V4-D2B1 FIX 3 / M1).  This module is stdlib-only
        (module docstring), so it cannot reach for ``pd.isna``.  A ``pandas``
        ``to_dict("records")`` round-trip can hand back a genuine ``float('nan')`` —
        never Python ``None`` — for a null cell in a nullable string column that also
        carries real strings (the same trap ``scripts/build_security_master.py``
        documents at its own ``_read_existing``/``_write_parquet``).  ``value is None``
        alone misses it, and NaN is TRUTHY, so the old ``rec.get(...) or ""`` fallback
        used for ``issuer_state``/``listing_key`` would also stringify a NaN cell into
        the literal string ``"nan"`` rather than treating it as absent.  A NaN
        ``issuer_id`` must index as NO issuer, never the string ``'nan'``.
        """
        rows: list[SecurityIssuerRow] = []
        for i, rec in enumerate(records or ()):
            try:
                sec = str(rec["security_id"])
            except KeyError as exc:
                raise IdentityError(
                    f"security master record {i} is missing {exc.args[0]!r}"
                ) from exc
            issuer = _null_to_none(rec.get("issuer_id"))
            state = _null_to_none(rec.get("issuer_state"))
            listing_key = _null_to_none(rec.get("listing_key"))
            rows.append(
                SecurityIssuerRow(
                    security_id=sec,
                    issuer_id=None if issuer is None else str(issuer),
                    issuer_state=str(state) if state is not None else "",
                    listing_key=str(listing_key) if listing_key is not None else "",
                )
            )
        return cls(rows)

    @property
    def rows(self) -> tuple[SecurityIssuerRow, ...]:
        return tuple(self._by_security.values())

    def issuer_of_security(self, security_id: str) -> str | None:
        """This security's CURRENT issuer_id, or ``None`` (unknown security, or a
        known one with no evidenced/legacy issuer_id — spec §3 ``NO_ISSUER_EVIDENCE``
        + null case)."""
        row = self._by_security.get(security_id)
        return row.issuer_id if row is not None else None

    def securities_of_issuer(self, issuer_id_: str) -> tuple[str, ...]:
        """Every ``security_id`` CURRENTLY carrying this ``issuer_id`` — the §9.7
        canonical query.  Sorted; empty tuple if the issuer id is unknown or unused."""
        return self._by_issuer.get(issuer_id_, ())
