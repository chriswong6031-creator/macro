"""Ticker SHAPE — the one place a string is judged to be a symbol.

Two levels, deliberately different, because the two jobs are different:

  • EMITTERS gate STRICT (``valid_us_ticker``): the US-equity shape check that decides
    which strings may become ticker KEYS in a published artifact. Everything else is
    excluded WITH A COUNT — never silently. A silent drop is how ``CONSECUTIVE``,
    ``()``, ``ASX:PEX`` and friends sat in the hub snapshot ledger for 26 days before
    anyone noticed the upstream feed had changed shape.
  • BOUNDARIES tripwire PERMISSIVE (``plausible_symbol``): accepts any plausible
    exchange form (0700.HK, 600519.SS, BTC-USD, ANANTRAJ) and only asks "could this be
    a symbol at all?". A boundary guard COUNTS and ANNOTATES; it must never drop —
    dropping there would hide the emitter regression the tripwire exists to expose.

Prefix ruling: exchange-prefixed forms like ``ASX:PEX`` are EXCLUDED-WITH-COUNT at
emitters, never stripped-and-mapped. Stripping the prefix collides with real US symbols
(PEX is a listed US ETF), and a prefix→exchange mapping table would silently alias
foreign issuers into the US ticker namespace — precisely the corruption these gates exist
to prevent. An unmapped foreign symbol is a visible exclusion; a mis-mapped one is a lie.

Dependency-free on purpose (stdlib ``re`` only) so the lightest-import boundary modules
can adopt the tripwire without dragging pandas or config in behind it.
"""
from __future__ import annotations

import re

# String forms of an ABSENT value — coercion survivors that carry no ticker at all.
_MISSING = {"", "nan", "none", "nat", "null", "<na>"}

# Tickers that survive string coercion but are NOT real symbols — placeholder junk
# ("N/A" from a filing with no assigned ticker, etc.) that must never become a
# convergence record on any channel. Paired with a shape check below.
TICKER_JUNK = {"NA", "N/A", "N.A.", "NAN", "NONE", "NULL", "TBD", "TBA", "NOTAV",
               "UNKNOWN", "PRIVATE", "VARIOUS", "MULTIPLE", "-", "—", "?"}

# US-equity ticker shape: starts with a letter, then alnum, with an optional
# .-/-suffixed share class (BRK.B / BRK-B). Rejects "N/A" (slash), spaces, commas.
US_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,8}([.\-][A-Z0-9]{1,3})?$")

# Any-exchange plausible shape: digit-first roots (0700.HK, 600519.SS), longer non-US
# roots (ANANTRAJ), and 4-char suffixes (BTC-USD). Wider than the US gate BY DESIGN —
# this is the tripwire alphabet, not the emitter alphabet, so a legitimate foreign symbol
# arriving at a boundary does not raise a false alarm about an emitter regression.
PLAUSIBLE_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9]{0,9}([.\-][A-Z0-9]{1,4})?$")


def valid_us_ticker(v) -> str | None:
    """A canonical, validated US ticker, or None. Rejects placeholder junk ('N/A' and
    friends) and shape-invalid strings so no garbage name reaches a published artifact.
    This is the single hygiene gate every emitter routes its ticker keys through.

    Case is normalized for the CHECK only — the stripped ORIGINAL is returned, so an
    emitter's existing key universe is byte-identical for every string that passes."""
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in _MISSING:
        return None
    u = s.upper()
    if u in TICKER_JUNK or not US_TICKER_RE.match(u):
        return None
    return s


def plausible_symbol(v) -> bool:
    """Could this string be a symbol on ANY exchange? The permissive boundary tripwire.

    True for US and non-US forms alike (AAPL, BRK.B, 0700.HK, 600519.SS, BTC-USD,
    ANANTRAJ). False only for strings no venue would list: prose ("CONSECUTIVE"),
    punctuation ("()"), exchange-prefixed composites ("ASX:PEX"), and the junk set.
    Callers COUNT and ANNOTATE on False — they do not drop."""
    if v is None:
        return False
    s = str(v).strip()
    if s.lower() in _MISSING:
        return False
    u = s.upper()
    return u not in TICKER_JUNK and bool(PLAUSIBLE_SYMBOL_RE.match(u))
