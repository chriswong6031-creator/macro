"""Membership ticker -> the symbol the price vendor actually serves the series under.

ONE map, imported by every lane that fetches US equity prices by membership ticker.
It exists because a ticker rename desynchronises this repo from the vendor in BOTH
directions:

  * the vendor LAGS the rename — Fiserv became FI in 2023 and Yahoo still serves the
    series only under the pre-rename FISV symbol;
  * the vendor LEADS it — Marsh McLennan changed its NYSE symbol MMC -> MRSH on
    2026-01-14 (symbol change only: same listing, same CUSIP, legal name unchanged),
    Yahoo migrated the whole history onto MRSH, and the membership's MMC now 404s as
    "possibly delisted, no price data found".

Either way the repair has the same shape: FETCH under the value, STORE under the key,
so the membership ticker stays the stable join key across the site while the vendor
symbol is free to move underneath it.

WRITTEN ONCE AND IMPORTED, because the same map living in two collectors is precisely
how data/baskets/ohlcv/MMC.parquet came to never exist. scripts/fetch_basket_extras
carried the MMC->MRSH entry — its close-only store holds MMC with 897 rows through
2026-07-31 — while its sibling scripts/fetch_basket_ohlcv carried only FI->FISV, so the
DEEP store skipped Marsh on every run since the store was created (2026-06-19) and the
`insurance` basket rendered on 18/19 members and `us_sector_financials` on 75/76 for the
seven months after the rename. A shim present in one consumer hides a missing shim in
its sibling: adding a name here fixes every reader at once, adding it to one collector
fixes exactly that collector.

NOT a display map. Site copy, page slugs and ledger keys keep the membership ticker;
this only ever decides what string goes to the vendor.
"""
from __future__ import annotations

#: membership ticker -> yfinance symbol. Fetched under the value, stored under the key.
#: Keep an entry only while the vendor genuinely disagrees with the membership symbol —
#: verify with a live pull before adding one (a wrong entry silently stores another
#: company's tape under this ticker, which no downstream check can see).
YAHOO_FETCH_ALIASES: dict[str, str] = {
    "FI": "FISV",       # Fiserv renamed FISV->FI in 2023; Yahoo still serves the OLD symbol
    "MMC": "MRSH",      # Marsh McLennan renamed MMC->MRSH 2026-01-14; Yahoo serves the NEW symbol
    # "EQR": "VMRK" was removed 2026-08-28: the EQR->VMRK key migration (#4622 protocol,
    # operator-ratified) made VMRK the stable membership/store key everywhere (membership,
    # baskets/ohlcv, stocks, breadth constituents, open qledger claims), so the alias's
    # vendor target became a universe member — exactly the two-stores-for-one-company
    # leak scripts/check_symbol_rename_drift.py exists to refuse. Rename receipts: SEC
    # EDGAR CIK 0000906107, 8-K accession 0001140361-26-033377, Item 5.03, eff. 2026-08-18.
}

#: yfinance symbol -> membership ticker (the inverse; used to rename a fetched frame back).
YAHOO_STORE_KEYS: dict[str, str] = {v: k for k, v in YAHOO_FETCH_ALIASES.items()}


def fetch_symbol(ticker: str) -> str:
    """The vendor symbol to REQUEST for a membership ticker (identity when unaliased)."""
    return YAHOO_FETCH_ALIASES.get(ticker, ticker)


def store_key(symbol: str) -> str:
    """The membership ticker a fetched vendor symbol is STORED under (identity when unaliased)."""
    return YAHOO_STORE_KEYS.get(symbol, symbol)
