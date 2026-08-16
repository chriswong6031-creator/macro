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
    # W3A: the Finviz theme tree is a MEMBERSHIP source, not a basket family. It earns a
    # market here so its tickers mint company ids in the right namespace (and inherit
    # every ratified identity break automatically); it never mints basket ids — the
    # guard refuses `basket:finviz_themes:*` outright (plan §9.11).
    "finviz_themes": "us",
}

MARKETS: tuple[str, ...] = ("us", "cn", "hk", "ca", "intl")

#: Suites that exist for COMPANY identity only. A basket id in one of these namespaces
#: is a category error — the source has no baskets, only local themes.
NON_BASKET_SUITES: frozenset[str] = frozenset({"finviz_themes"})

#: Local-theme source families. Extending this is deliberate, exactly like SUITE_MARKET:
#: a new family arrives with its own rights row and its own id space.
LOCAL_THEME_FAMILIES: dict[str, str] = {"finviz": "us", "ths": "cn"}

#: The grammar every minted company id must satisfy — mirrored by the guard
#: (scripts/check_theme_graph_contracts.py) so a violation cannot reach the store.
COMPANY_ID_RE = re.compile(r"^co:(us|cn|hk|ca|intl):[A-Za-z0-9.\-]+(#[0-9]+)?$")
#: Local-theme ids: `ltheme:<family>:<source_local_id>`. The local id is the SOURCE's own
#: key — a Finviz subtheme key, or a 同花顺 concept CODE. Chinese concept names never enter
#: an id: they are labels, they are not stable, and an id has to round-trip through this
#: regex, every parquet, and every URL that ever quotes it.
LOCAL_THEME_ID_RE = re.compile(r"^ltheme:(finviz|ths):[A-Za-z0-9_.\-]+$")
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
    if suite in NON_BASKET_SUITES:
        raise ValueError(
            f"suite {suite!r} has no baskets — it is registered for company identity "
            f"only. Its concepts are local_theme nodes (ltheme:…); minting a basket id "
            f"here would give the same source two vocabularies for one thing")
    bid = ("" if basket_id is None else str(basket_id)).strip()
    if not bid:
        raise ValueError("empty basket id")
    return f"basket:{suite}:{bid}"


def local_theme_node_id(family: str, source_local_id: object) -> str:
    """``ltheme:<family>:<source_local_id>`` for a SOURCE-LOCAL theme concept.

    A local theme is the source's own concept at the source's own grain — a Finviz
    subtheme, a 同花顺 concept board. It is deliberately NOT canonical GMI vocabulary:
    the canonical plane is `theme:*`, and the two meet only through a curated EXPRESSES
    edge. Unknown family, empty id, or an id outside the grammar → refuse.
    """
    fam = str(family or "").strip().lower()
    if fam not in LOCAL_THEME_FAMILIES:
        raise ValueError(
            f"unknown local-theme family {fam!r} — add it to LOCAL_THEME_FAMILIES "
            f"deliberately, with its rights row; families do not default into existence")
    local = ("" if source_local_id is None else str(source_local_id)).strip()
    if not local:
        raise ValueError(f"empty source-local id for family {fam!r}")
    node_id = f"ltheme:{fam}:{local}"
    if not LOCAL_THEME_ID_RE.match(node_id):
        raise ValueError(
            f"local-theme id {node_id!r} does not match {LOCAL_THEME_ID_RE.pattern} — "
            f"source keys that cannot be expressed (中文 names, spaces, '/') are resolved "
            f"to a stable code BEFORE they reach an id, never squeezed into one")
    return node_id


def market_for_local_theme_family(family: str) -> str:
    fam = str(family or "").strip().lower()
    try:
        return LOCAL_THEME_FAMILIES[fam]
    except KeyError:
        raise ValueError(f"unknown local-theme family {fam!r}") from None


def symbol_variants(symbol: object) -> tuple[str, ...]:
    """The dot/dash spellings of one listing, normalised, most-canonical first.

    Vendors disagree about class shares: Finviz writes ``BRK-B`` where another feed
    writes ``BRK.B``. They are ONE company, and minting both spellings would produce a
    variant twin whose two halves each carry half the memberships — invisible in every
    count and wrong in every breadth answer.
    """
    sym = normalise_symbol(symbol)
    out = [sym]
    for other in (sym.replace(".", "-"), sym.replace("-", ".")):
        if other != sym and other not in out:
            out.append(other)
    return tuple(out)


def resolve_symbol_variant(suite: str, symbol: object, known_ids: object, *,
                           breaks: dict[tuple[str, str], int] | None = None
                           ) -> tuple[str, bool]:
    """``(node_id, was_variant)`` — resolve to an EXISTING node before minting a new one.

    ``known_ids`` is any container of node ids already minted in this build. The exact
    spelling wins when it is already known; otherwise a dot/dash variant that is already
    known wins; otherwise the exact spelling is minted fresh.
    """
    ids = known_ids if hasattr(known_ids, "__contains__") else set(known_ids)
    variants = symbol_variants(symbol)
    exact = company_node_id(suite, variants[0], breaks=breaks)
    if exact in ids:
        return exact, False
    for other in variants[1:]:
        candidate = company_node_id(suite, other, breaks=breaks)
        if candidate in ids:
            return candidate, True
    return exact, False


def etf_node_id(symbol: object) -> str:
    """``etf:<SYMBOL>``. ETFs are market-agnostic in the id — the proxy relationship
    to a basket carries the market, and the same ETF may proxy baskets in two suites."""
    return f"etf:{normalise_symbol(symbol)}"
