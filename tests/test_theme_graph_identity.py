"""Permanent node identity for the GMI theme graph (masterplan §4.1).

WHAT THESE PROTECT. A company node id identifies the COMPANY that held a symbol, not
the symbol. Ticker strings get recycled, and a store that keys on the bare ticker
silently merges two companies' histories into one node — every membership, breadth and
survivorship answer downstream then inherits the merge, with nothing raising anywhere.
So the id carries an epoch, epochs come only from ratified rows, and every failure mode
of the minting path is fail-CLOSED: an unknown suite, an empty symbol and a symbol the
grammar cannot express all raise rather than producing an id that will not round-trip.

Fixture-only: the breaks table is always passed in explicitly, so nothing here depends
on the live config/theme_graph_identity_breaks.yml (which is empty today — a test that
passed BECAUSE it is empty would say nothing).
"""
from __future__ import annotations

import pytest

from engine.theme_graph import identity

SUITE_TO_MARKET = {
    "baskets": "us",
    "baskets_china": "cn",
    "baskets_china_ths": "cn",
    "baskets_hk": "hk",
    "baskets_canada": "ca",
    "baskets_intl": "intl",
}


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("suite,market", sorted(SUITE_TO_MARKET.items()))
def test_every_suite_mints_into_its_own_market(suite, market):
    assert identity.company_node_id(suite, "AAPL", breaks={}) == f"co:{market}:AAPL"


def test_the_suite_map_covers_every_suite_the_materializer_reads():
    """A suite the materializer builds but identity does not know would refuse the whole
    family at mint time — the two lists must not drift apart."""
    from engine.theme_graph import materialize

    assert set(materialize.SUITES) == set(identity.SUITE_MARKET) == set(SUITE_TO_MARKET)


def test_an_unknown_suite_is_refused_rather_than_defaulted():
    with pytest.raises(ValueError, match="unknown membership suite"):
        identity.company_node_id("baskets_atlantis", "AAPL", breaks={})


@pytest.mark.parametrize("symbol", [None, "", "   "])
def test_an_empty_symbol_is_fail_closed(symbol):
    with pytest.raises(ValueError, match="empty symbol"):
        identity.company_node_id("baskets", symbol, breaks={})


@pytest.mark.parametrize("symbol", ["['XLP', 'XLU']", "600000.SS ??", "a/b", "x y"])
def test_a_symbol_outside_the_grammar_is_refused_not_mangled(symbol):
    """The `defensives` basket carries etf_proxy as a LIST, and a str()-and-hope read of
    it produced exactly the first of these. Minting it would put an id in the store that
    the guard's regex then rejects — better to refuse at the source."""
    with pytest.raises(ValueError, match="node-id grammar"):
        identity.company_node_id("baskets", symbol, breaks={})


@pytest.mark.parametrize("raw,expected", [
    ("aapl", "AAPL"), (" 600783.SS ", "600783.SS"), ("brk.b", "BRK.B"),
    ("ry.to", "RY.TO"), ("2330.tw", "2330.TW"),
])
def test_symbols_normalise_to_one_spelling(raw, expected):
    assert identity.company_node_id("baskets", raw, breaks={}) == f"co:us:{expected}"


# ---------------------------------------------------------------------------
# Epochs
# ---------------------------------------------------------------------------

def _breaks_file(tmp_path, rows):
    import yaml

    p = tmp_path / "identity_breaks.yml"
    p.write_text(yaml.safe_dump({"breaks": rows}, allow_unicode=True), encoding="utf-8")
    return p


def test_epoch_one_is_implicit_and_carries_no_suffix():
    assert identity.identity_epoch("us", "AAPL", breaks={}) == 1
    assert "#" not in identity.company_node_id("baskets", "AAPL", breaks={})


def test_a_ratified_break_moves_the_id_to_the_next_epoch(tmp_path):
    path = _breaks_file(tmp_path, [{
        "symbol": "zomb", "market": "us", "break_date": "2024-03-01",
        "prior_node_retired_as": "co:us:ZOMB", "new_epoch": 2,
        "evidence": "fixture", "ratified_by": "fixture",
    }])
    table = identity.load_breaks(path)
    assert table == {("us", "ZOMB"): 2}
    assert identity.company_node_id("baskets", "ZOMB", breaks=table) == "co:us:ZOMB#2"
    # ...and only for that market: the same string on another exchange is another company.
    assert identity.company_node_id("baskets_hk", "ZOMB", breaks=table) == "co:hk:ZOMB"


def test_successive_breaks_resolve_to_the_highest_ratified_epoch(tmp_path):
    rows = [
        {"symbol": "ZOMB", "market": "us", "break_date": "2024-03-01",
         "prior_node_retired_as": "co:us:ZOMB", "new_epoch": 2,
         "evidence": "fixture", "ratified_by": "fixture"},
        {"symbol": "ZOMB", "market": "us", "break_date": "2025-09-09",
         "prior_node_retired_as": "co:us:ZOMB#2", "new_epoch": 3,
         "evidence": "fixture", "ratified_by": "fixture"},
    ]
    table = identity.load_breaks(_breaks_file(tmp_path, rows))
    assert identity.company_node_id("baskets", "ZOMB", breaks=table) == "co:us:ZOMB#3"


def test_an_unratifiable_break_row_is_ignored_rather_than_half_applied(tmp_path):
    """epoch < 2 is not a break, and a row missing its market or symbol cannot name a
    node — neither may quietly move an id."""
    table = identity.load_breaks(_breaks_file(tmp_path, [
        {"symbol": "AAA", "market": "us", "new_epoch": 1},
        {"symbol": "", "market": "us", "new_epoch": 2},
        {"symbol": "BBB", "market": "", "new_epoch": 2},
    ]))
    assert table == {}


def test_a_missing_breaks_file_means_no_breaks(tmp_path):
    assert identity.load_breaks(tmp_path / "nope.yml") == {}


def test_the_committed_breaks_file_parses_and_declares_its_rows():
    """The scaffold ships with zero rows. That is a statement about RATIFICATIONS, not
    about the world, and it must still be a well-formed table."""
    table = identity.load_breaks()
    assert isinstance(table, dict)
    assert all(len(k) == 2 and v >= 2 for k, v in table.items())


# ---------------------------------------------------------------------------
# Round-trip against the grammar the guard enforces
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("suite", sorted(SUITE_TO_MARKET))
@pytest.mark.parametrize("symbol", ["AAPL", "600783.SS", "0700.HK", "RY.TO", "BRK.B"])
def test_every_minted_company_id_matches_the_guards_regex(suite, symbol):
    node_id = identity.company_node_id(suite, symbol, breaks={})
    assert identity.COMPANY_ID_RE.match(node_id), node_id


def test_an_epoch_suffixed_id_also_matches_the_guards_regex(tmp_path):
    table = identity.load_breaks(_breaks_file(tmp_path, [
        {"symbol": "600783.SS", "market": "cn", "new_epoch": 7}]))
    node_id = identity.company_node_id("baskets_china", "600783.SS", breaks=table)
    assert node_id == "co:cn:600783.SS#7"
    assert identity.COMPANY_ID_RE.match(node_id)


# ---------------------------------------------------------------------------
# The other three id families
# ---------------------------------------------------------------------------

def test_theme_basket_and_etf_ids():
    assert identity.theme_node_id("solar") == "theme:solar"
    assert identity.basket_node_id("baskets_china_ths", "thsc301079") == \
        "basket:baskets_china_ths:thsc301079"
    assert identity.etf_node_id("tan") == "etf:TAN"


def test_basket_ids_are_suite_qualified():
    """Basket ids are unique only WITHIN their own membership document, so an unqualified
    id would collide the moment two suites both name a basket the same thing."""
    assert identity.basket_node_id("baskets", "solar") != \
        identity.basket_node_id("baskets_china", "solar")


@pytest.mark.parametrize("fn,arg", [
    (identity.theme_node_id, ""), (identity.theme_node_id, None),
    (identity.etf_node_id, ""), (identity.etf_node_id, None),
])
def test_the_other_families_are_fail_closed_too(fn, arg):
    with pytest.raises(ValueError):
        fn(arg)


def test_an_empty_basket_id_is_refused():
    with pytest.raises(ValueError, match="empty basket id"):
        identity.basket_node_id("baskets", "")
