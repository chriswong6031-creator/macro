"""Permanent node identity for the theme graph (masterplan §4.1).

THE LAW: a company node id identifies the COMPANY that held a symbol, never the symbol.
Ticker strings are recycled — a delisting, then a different issuer taking the string —
and a store that keys on the bare ticker silently merges two companies' histories into
one node, which every membership, breadth and survivorship answer downstream then
inherits (the reused-ticker zombie law; `data/qledger/` and
``scripts/audit_reused_tickers.py`` exist because this happens).

So the id carries an EPOCH, and epochs come from exactly one place:
``config/theme_graph_identity_breaks.yml``, whose rows are ratified curated acts. A
builder can never decide on its own that two listings are different companies — the
decision has to be written down, with evidence, first. Epoch 1 is implicit (no suffix);
from epoch 2 the id ends ``#<epoch>``.

Fail-closed: an empty symbol, or one carrying characters the id grammar cannot express,
raises rather than minting an id that will not round-trip through the guard's regex.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

#: Which market a membership suite's members trade in. The suite → market map is the
#: only place the graph learns a company's market, so a new suite must land here
#: deliberately rather than defaulting into somebody else's namespace.
SUITE_MARKET: dict[str, str] = {
    "baskets": "us",
    "baskets_china": "cn",
    "baskets_china_ths": "cn",
    "baskets_hk": "hk",
    "baskets_canada": "ca",
    "baskets_intl": "intl",
}

MARKETS: tuple[str, ...] = ("us", "cn", "hk", "ca", "intl")

#: The grammar every minted company id must satisfy — mirrored by the guard
#: (scripts/check_theme_graph_contracts.py) so a violation cannot reach the store.
COMPANY_ID_RE = re.compile(r"^co:(us|cn|hk|ca|intl):[A-Za-z0-9.\-]+(#[0-9]+)?$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]+$")

BREAKS_FILE = "config/theme_graph_identity_breaks.yml"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def breaks_path() -> Path:
    return _repo_root() / BREAKS_FILE


@lru_cache(maxsize=8)
def _load_breaks(path: str) -> dict[tuple[str, str], int]:
    """{(market, SYMBOL): highest ratified epoch}. Missing file → no breaks."""
    p = Path(path)
    if not p.exists():
        return {}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[tuple[str, str], int] = {}
    for row in doc.get("breaks") or []:
        market = str(row.get("market", "")).strip().lower()
        symbol = str(row.get("symbol", "")).strip().upper()
        epoch = int(row.get("new_epoch", 0))
        if not market or not symbol or epoch < 2:
            continue
        key = (market, symbol)
        out[key] = max(out.get(key, 1), epoch)
    return out


def load_breaks(path: str | Path | None = None) -> dict[tuple[str, str], int]:
    """Ratified identity breaks as {(market, SYMBOL): epoch}. Cached per path."""
    return _load_breaks(str(Path(path) if path is not None else breaks_path()))


def market_for_suite(suite: str) -> str:
    """The market a suite's members trade in. Unknown suite → refuse (no default)."""
    try:
        return SUITE_MARKET[suite]
    except KeyError:
        raise ValueError(
            f"unknown membership suite {suite!r} — add it to SUITE_MARKET deliberately; "
            f"defaulting a market would file its companies under somebody else's ids"
        ) from None


def normalise_symbol(symbol: object) -> str:
    """Uppercased, whitespace-stripped symbol. Empty or unexpressible → refuse."""
    s = ("" if symbol is None else str(symbol)).strip().upper()
    if not s:
        raise ValueError("empty symbol — a company node cannot be minted without one")
    if not _SYMBOL_RE.match(s):
        raise ValueError(
            f"symbol {s!r} carries characters outside the node-id grammar "
            f"[A-Za-z0-9.-]; refusing to mint an id that will not round-trip")
    return s


def identity_epoch(market: str, symbol: object, *,
                   breaks: dict[tuple[str, str], int] | None = None) -> int:
    """Ratified epoch for (market, symbol). 1 unless a break row says otherwise."""
    table = load_breaks() if breaks is None else breaks
    return int(table.get((market, normalise_symbol(symbol)), 1))


def company_node_id(suite: str, symbol: object, *,
                    breaks: dict[tuple[str, str], int] | None = None) -> str:
    """``co:<market>:<SYMBOL>``, plus ``#<epoch>`` from epoch 2 on."""
    market = market_for_suite(suite)
    sym = normalise_symbol(symbol)
    epoch = identity_epoch(market, sym, breaks=breaks)
    node_id = f"co:{market}:{sym}" + (f"#{epoch}" if epoch >= 2 else "")
    if not COMPANY_ID_RE.match(node_id):  # pragma: no cover — defensive
        raise ValueError(f"minted company id {node_id!r} does not match the grammar")
    return node_id


def theme_node_id(theme_id: object) -> str:
    """``theme:<id>`` — the crosswalk row id, which is the canonical theme vocabulary."""
    tid = ("" if theme_id is None else str(theme_id)).strip()
    if not tid:
        raise ValueError("empty theme id")
    return f"theme:{tid}"


def basket_node_id(suite: str, basket_id: object) -> str:
    """``basket:<suite>:<basket_id>`` — suite-qualified, because basket ids are only
    unique within their own membership document."""
    market_for_suite(suite)  # refuse an unknown suite here too
    bid = ("" if basket_id is None else str(basket_id)).strip()
    if not bid:
        raise ValueError("empty basket id")
    return f"basket:{suite}:{bid}"


def etf_node_id(symbol: object) -> str:
    """``etf:<SYMBOL>``. ETFs are market-agnostic in the id — the proxy relationship
    to a basket carries the market, and the same ETF may proxy baskets in two suites."""
    return f"etf:{normalise_symbol(symbol)}"
