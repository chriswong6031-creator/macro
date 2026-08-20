"""tests/test_market_books_js.py — market partitioning (templates/market_books.js).

`market_books.js` owns the ONE symbol -> market derivation the whole Portfolio Command
Center reads, plus the per-book aggregation and the FX-corruption guard. Every function
under test is pure and DOM-free (exported under node behind a `typeof module` guard,
exactly like risk_core.js), so we node-shell them and assert:

  - marketOf covers every suffix class in the vocabulary of record, and the macro
    bucket (^index / =F future / =X fx / DX-Y.NYB) never falls through to `us`
  - storeOf routes each market to its own per-ticker store, and us/crypto/macro share
    the US store (the only USD one)
  - the FX-corruption guard (A3 law 3): a non-USD name can never reach a weight sum
  - aggregation NEVER sums across currencies — HK$ and US$ stay in separate books
  - the strip only appears once a second market is actually present

Node is available on CI + dev Macs; the suite skips loudly when it is not (mirrors
tests/test_risk_core_js.py).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

MODULE = Path(__file__).resolve().parents[1] / "templates" / "market_books.js"


def _run(js_body: str, extra: dict | None = None) -> dict:
    """Load market_books.js under node, inject globals, run js_body, parse JSON stdout."""
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = textwrap.dedent(
        """
        var MB = require(%(mod)s);
        %(globs)s
        function OUT(o){ process.stdout.write(JSON.stringify(o)); }
        %(body)s
        """
    ) % {"mod": json.dumps(str(MODULE)), "globs": globs, "body": js_body}
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# marketOf — the derivation table, every suffix class
# ---------------------------------------------------------------------------
# (symbol, expected market). Mirrors terminal/lib/markets.ts so the two repos can
# never disagree about which book a symbol belongs to.
DERIVATION = [
    # plain US listings
    ("AAPL", "us"), ("NVDA", "us"), ("BRK-B", "us"), ("aapl", "us"),
    # China A-shares
    ("600519.SS", "cn"), ("000858.SZ", "cn"), ("430047.BJ", "cn"),
    # Hong Kong
    ("0700.HK", "hk"), ("9988.HK", "hk"),
    # Canada
    ("SHOP.TO", "ca"), ("ABC.V", "ca"), ("XYZ.NE", "ca"),
    # International (any other suffix)
    ("7203.T", "intl"), ("ASML.AS", "intl"), ("BMW.DE", "intl"), ("VOD.L", "intl"),
    # crypto
    ("BTC-USD", "crypto"), ("ETH-USD", "crypto"), ("SOL-USDT", "crypto"),
    # macro: indexes, futures, fx, and the one hardcoded dollar index
    ("^GSPC", "macro"), ("^VIX", "macro"),
    ("CL=F", "macro"), ("GC=F", "macro"),
    ("EURUSD=X", "macro"), ("JPY=X", "macro"),
    ("DX-Y.NYB", "macro"),
]


@needs_node
def test_market_of_derivation_table():
    out = _run(
        "var r={}; SYMS.forEach(function(s){ r[s]=MB.marketOf(s); }); OUT(r);",
        {"SYMS": [s for s, _ in DERIVATION]},
    )
    for sym, expected in DERIVATION:
        assert out[sym] == expected, f"{sym}: expected {expected}, got {out[sym]}"


@needs_node
def test_market_of_degenerate_inputs_never_throw():
    out = _run(
        "OUT({empty:MB.marketOf(''), nul:MB.marketOf(null), undef:MB.marketOf(undefined), "
        "num:MB.marketOf(123), dot:MB.marketOf('.')});"
    )
    # an unknown/blank symbol defaults to the US book rather than crashing the strip
    assert out["empty"] == "us" and out["nul"] == "us" and out["undef"] == "us"
    assert out["num"] == "us"
    assert out["dot"] == "us"


@needs_node
def test_dx_y_nyb_does_not_fall_through_to_intl():
    """DX-Y.NYB ends in `.NYB` — a 3-letter suffix that the generic branch would call
    `intl`. It is checked FIRST for exactly this reason; pin it so a refactor that
    reorders the branches fails loudly."""
    out = _run("OUT({m:MB.marketOf('DX-Y.NYB'), store:MB.storeOf('DX-Y.NYB')});")
    assert out["m"] == "macro"
    assert out["store"] == "stockdata"


# ---------------------------------------------------------------------------
# storeOf — per-market per-ticker stores
# ---------------------------------------------------------------------------
@needs_node
def test_store_routing():
    out = _run(
        "var r={}; SYMS.forEach(function(s){ r[s]=MB.storeOf(s); }); OUT(r);",
        {"SYMS": ["AAPL", "BTC-USD", "^GSPC", "600519.SS", "0700.HK", "SHOP.TO", "7203.T"]},
    )
    assert out["AAPL"] == "stockdata"
    assert out["BTC-USD"] == "stockdata"      # crypto lives in the US store
    assert out["^GSPC"] == "stockdata"        # so do indexes/commodities
    assert out["600519.SS"] == "chinastockdata"
    assert out["0700.HK"] == "hkstockdata"
    assert out["SHOP.TO"] == "canadastockdata"
    assert out["7203.T"] == "intlstockdata"


# ---------------------------------------------------------------------------
# FX-corruption guard (A3 law 3) — the binding one
# ---------------------------------------------------------------------------
@needs_node
def test_modeled_filter_excludes_every_non_usd_market():
    """The 9-factor model is USD and carries zero suffixed tickers. If an HKD/CNY/CAD
    dollar value reaches a weight sum, every book statistic downstream (factor shares,
    effective bets, correlations, MCTR) is silently wrong — and looks fine. This is the
    membership test that stops it."""
    out = _run(
        "OUT({flags:SYMS.map(MB.isModeled), only:MB.modeledOnly(SYMS), "
        "weights:MB.modeledWeights(W)});",
        {
            "SYMS": ["AAPL", "BTC-USD", "^GSPC", "0700.HK", "600519.SS", "SHOP.TO", "7203.T"],
            "W": {"AAPL": 1000, "0700.HK": 50000, "600519.SS": 30000,
                  "SHOP.TO": 2000, "BTC-USD": 500},
        },
    )
    assert out["flags"] == [True, True, True, False, False, False, False]
    assert out["only"] == ["AAPL", "BTC-USD", "^GSPC"]
    # the HK$ 50,000 / ¥30,000 / C$2,000 values are gone, not merely reordered
    assert out["weights"] == {"AAPL": 1000, "BTC-USD": 500}


@needs_node
def test_modeled_filter_handles_empty_and_null():
    out = _run(
        "OUT({a:MB.modeledOnly(null), b:MB.modeledOnly([]), "
        "c:MB.modeledWeights(null), d:MB.modeledWeights({})});"
    )
    assert out["a"] == [] and out["b"] == []
    assert out["c"] == {} and out["d"] == {}


# ---------------------------------------------------------------------------
# aggregation — never sums across currencies
# ---------------------------------------------------------------------------
MIXED_ROWS = [
    {"ticker": "AAPL", "shares": 10, "entry_price": 200, "status": "open"},
    {"ticker": "NVDA", "shares": 5, "entry_price": 100, "status": "open"},
    {"ticker": "0700.HK", "shares": 100, "entry_price": 400, "status": "open"},
    {"ticker": "SHOP.TO", "shares": 20, "entry_price": 150, "status": "open"},
    {"ticker": "MSFT", "shares": 3, "entry_price": 300, "status": "closed"},
]
PRICES = {"AAPL": 300, "NVDA": 200, "0700.HK": 500, "SHOP.TO": 200}


@needs_node
def test_aggregate_keeps_each_book_in_its_own_currency():
    out = _run(
        "var agg = MB.aggregate(ROWS, function(t){ return PX[t]; }); OUT(agg);",
        {"ROWS": MIXED_ROWS, "PRICES": PRICES, "PX": PRICES},
    )
    # one entry per book that holds an open position; NO combined total anywhere
    assert set(out.keys()) == {"us", "hk", "ca"}
    assert out["us"]["value"] == 10 * 300 + 5 * 200      # $4,000
    assert out["hk"]["value"] == 100 * 500               # HK$50,000
    assert out["ca"]["value"] == 20 * 200                # C$4,000
    assert out["us"]["ccy"] == "$"
    assert out["hk"]["ccy"] == "HK$"
    assert out["ca"]["ccy"] == "C$"
    # the closed MSFT row is excluded from the open-position book
    assert out["us"]["n"] == 2


@needs_node
def test_aggregate_returns_no_cross_book_total_key():
    """A regression guard on the SHAPE: if anyone ever adds a `total`/`all` key that
    sums books, this fails. Cross-currency addition is the bug class A3 law 2 bans."""
    out = _run(
        "var agg = MB.aggregate(ROWS, function(t){ return PX[t]; }); "
        "OUT({keys:Object.keys(agg).sort()});",
        {"ROWS": MIXED_ROWS, "PX": PRICES},
    )
    assert out["keys"] == ["ca", "hk", "us"]
    for forbidden in ("all", "total", "sum", "combined"):
        assert forbidden not in out["keys"]


@needs_node
def test_aggregate_falls_back_to_entry_price_and_flags_at_cost():
    out = _run(
        "var agg = MB.aggregate(ROWS, function(){ return null; }); OUT(agg);",
        {"ROWS": MIXED_ROWS},
    )
    # no price resolves anywhere -> every book is valued at cost and says so
    assert out["us"]["value"] == 10 * 200 + 5 * 100
    assert out["us"]["atCost"] is True and out["us"]["priced"] == 0
    assert out["hk"]["value"] == 100 * 400
    assert out["hk"]["atCost"] is True


@needs_node
def test_aggregate_ignores_rows_without_shares():
    out = _run(
        "OUT(MB.aggregate(ROWS, function(){ return 100; }));",
        {"ROWS": [{"ticker": "AAPL", "shares": None, "entry_price": 10, "status": "open"},
                  {"ticker": "AAPL", "shares": "", "entry_price": 10, "status": "open"}]},
    )
    # the book still counts the holdings, but contributes no fabricated value
    assert out["us"]["n"] == 2
    assert out["us"]["value"] == 0


# ---------------------------------------------------------------------------
# buildPortfolioModel / buildWatchlistModel — when the strip appears at all
#
# A1A (research/market_os/…A1A_COMMISSIONING…md §11) retired the old union
# `buildModel(watchSyms, rows, priceOf)` — a Watchlist name could paint the Portfolio's
# own market strip (`#bk_strip` lives in the Portfolio holdings toolbar). The two
# constructors below are now separate and PORTFOLIO ONLY drives the strip.
# ---------------------------------------------------------------------------
@needs_node
def test_strip_hidden_for_a_single_market_book():
    """Zero regression for single-market users: a US-only book must not grow a strip."""
    out = _run(
        "var m = MB.buildPortfolioModel(ROWS, function(){ return 100; }); "
        "OUT({show:m.show, present:m.present, nAll:m.nAll});",
        {"ROWS": [{"ticker": "AAPL", "shares": 1, "entry_price": 1, "status": "open"},
                  {"ticker": "NVDA", "shares": 1, "entry_price": 1, "status": "open"}]},
    )
    assert out["show"] is False
    assert out["present"] == ["us"]
    assert out["nAll"] == 2


@needs_node
def test_strip_appears_and_orders_books_canonically():
    out = _run(
        "var m = MB.buildPortfolioModel(ROWS, function(){ return 100; }); "
        "OUT({show:m.show, present:m.present, nAll:m.nAll});",
        {
            "ROWS": [
                {"ticker": "AAPL", "shares": 1, "entry_price": 1, "status": "open"},
                {"ticker": "0700.HK", "shares": 1, "entry_price": 1, "status": "open"},
                {"ticker": "^GSPC", "shares": 1, "entry_price": 1, "status": "open"},
                {"ticker": "SHOP.TO", "shares": 1, "entry_price": 1, "status": "open"},
                {"ticker": "BTC-USD", "shares": 1, "entry_price": 1, "status": "open"},
            ],
        },
    )
    assert out["show"] is True
    # canonical order: us, crypto, cn, hk, ca, intl, macro
    assert out["present"] == ["us", "crypto", "hk", "ca", "macro"]
    assert out["nAll"] == 5


@needs_node
def test_closed_positions_do_not_create_a_book():
    out = _run(
        "var m = MB.buildPortfolioModel(ROWS, function(){ return 100; }); OUT({present:m.present});",
        {"ROWS": [{"ticker": "0700.HK", "shares": 1, "entry_price": 1, "status": "closed"},
                  {"ticker": "AAPL", "shares": 1, "entry_price": 1, "status": "open"}]},
    )
    assert out["present"] == ["us"]


@needs_node
def test_buildPortfolioModel_never_admits_a_watchlist_only_name():
    """A1A defect 'population union': a Watchlist name in a market the Portfolio does
    not hold must NEVER appear in the Portfolio's own book model. This is the mutation
    pin for 'restore population union' — reintroducing the old `(watchSyms||[]).forEach
    (addName)` union line in buildPortfolioModel turns this red."""
    out = _run(
        "var m = MB.buildPortfolioModel(ROWS, function(){ return 100; }); "
        "OUT({present:m.present, nAll:m.nAll, hasHK:'0700.HK' in (m.members.hk||{})});",
        {"ROWS": [{"ticker": "AAPL", "shares": 1, "entry_price": 1, "status": "open"}]},
    )
    # only the US book exists — a watched HK name (never passed to this constructor at
    # all) cannot leak in because the constructor accepts no watchlist argument
    assert out["present"] == ["us"]
    assert out["nAll"] == 1
    assert out["hasHK"] is False


@needs_node
def test_buildWatchlistModel_is_watchlist_only_and_ignores_portfolio_shape():
    out = _run(
        "var m = MB.buildWatchlistModel(WATCH); "
        "OUT({present:m.present, nAll:m.nAll, agg:m.agg});",
        {"WATCH": ["AAPL", "0700.HK", "^GSPC"]},
    )
    assert out["present"] == ["us", "hk", "macro"]
    assert out["nAll"] == 3
    # the watchlist constructor never aggregates money — it has no portfolio rows
    assert out["agg"] == {}


# ---------------------------------------------------------------------------
# book metadata — currency prefixes are what the plates print
# ---------------------------------------------------------------------------
@needs_node
def test_book_currency_prefixes():
    out = _run("OUT({books:MB.BOOKS, order:MB.BOOK_ORDER});")
    assert out["order"] == ["us", "crypto", "cn", "hk", "ca", "intl", "macro"]
    assert out["books"]["us"]["ccy"] == "$"
    assert out["books"]["hk"]["ccy"] == "HK$"
    assert out["books"]["cn"]["ccy"] == "¥"
    assert out["books"]["ca"]["ccy"] == "C$"
    # intl deliberately asserts no currency — the plate tags it "local currency"
    assert out["books"]["intl"]["ccy"] == ""
    # every book carries bilingual names (zh parity is a hard gate)
    for key, meta in out["books"].items():
        assert meta["en"] and meta["zh"], f"{key} missing a bilingual name"


@needs_node
def test_seen_diff_is_exported_for_the_today_strip():
    """The 'changed since your last visit' count must not treat a NEWLY ADDED name as
    a change (there is no prior state to have moved from)."""
    out = _run(
        "var store={}; global.localStorage={getItem:function(k){return store[k]||null;},"
        "setItem:function(k,v){store[k]=String(v);},removeItem:function(k){delete store[k];}};"
        "var first = MB.seenDiff({AAPL:'RALLY ON', NVDA:'FRESH BUY'});"
        "var noChange = MB.seenDiff({AAPL:'RALLY ON', NVDA:'FRESH BUY'});"
        "var moved = MB.seenDiff({AAPL:'TOP WATCH', NVDA:'FRESH BUY'});"
        "var added = MB.seenDiff({AAPL:'TOP WATCH', NVDA:'FRESH BUY', MSFT:'DECLINE'});"
        "OUT({first:first, noChange:noChange, moved:moved, added:added});"
    )
    assert out["first"] == 0        # first visit: no prior snapshot to diff against
    assert out["noChange"] == 0     # identical snapshot -> nothing changed
    assert out["moved"] == 1        # AAPL moved RALLY ON -> TOP WATCH
    assert out["added"] == 0        # MSFT is new, not "changed"
