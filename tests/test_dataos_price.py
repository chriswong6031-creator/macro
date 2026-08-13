"""Price basis naming law (Data OS §D4) — ``lib/dataos/price.py``.

The measured defect these tests encode: same ticker, same date, three stores, FOUR
numbers, all called some form of "close" (NVDA 2024-06-03 — 114.80 / 114.80 / 115.00
/ 1150.00).  ``KNOWN_STORE_BASES`` is documentation-as-code, so
``test_known_store_bases_carries_the_measured_truth`` is what stops that measurement
being edited back into a guess.

Pure unit tests; nothing here opens a parquet.

Run: .venv/bin/python -m pytest tests/test_dataos_price.py -q
"""

from __future__ import annotations

import itertools

import pytest

from lib.dataos.price import (
    AMBIGUOUS_NAMES,
    KNOWN_STORE_BASES,
    STORES_WITHOUT_OPEN,
    AdjustmentBasis,
    PriceError,
    PriceField,
    Session,
    VenueScope,
    canonical_column,
    is_ambiguous,
    parse_column,
)


# ── the vocabulary ───────────────────────────────────────────────────────────
def test_the_three_bases_and_ten_fields_are_exactly_the_spec_sets() -> None:
    assert {b.value for b in AdjustmentBasis} == {"raw", "sadj", "tradj"}
    assert {f.value for f in PriceField} == {
        "open", "high", "low", "close", "last", "vwap", "settle", "bid", "ask", "mid"
    }


def test_session_and_venue_scope_are_part_of_price_identity() -> None:
    """A consolidated-tape last print is NOT the official closing auction price."""
    assert {s.value for s in Session} == {
        "pre", "regular", "post", "overnight", "auction_open", "auction_close"
    }
    assert {v.value for v in VenueScope} == {"primary", "consolidated"}


@pytest.mark.parametrize("basis", list(AdjustmentBasis))
def test_every_basis_states_what_it_is_and_what_it_may_not_be_used_for(basis) -> None:
    assert basis.describes and len(basis.describes) > 20
    assert basis.lawful_for and all(isinstance(s, str) for s in basis.lawful_for)
    assert basis.unlawful_for and all(isinstance(s, str) for s in basis.unlawful_for)
    assert not set(basis.lawful_for) & set(basis.unlawful_for)


def test_the_raw_basis_owns_exchange_rule_work_and_tradj_is_barred_from_it() -> None:
    """``DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`` — using an adjusted price where the
    raw print was the only lawful input stop-shipped a whole program."""
    assert any("limit-price" in s for s in AdjustmentBasis.RAW.lawful_for)
    assert any("KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT" in s
               for s in AdjustmentBasis.TRADJ.unlawful_for)


# ── canonical_column / parse_column ──────────────────────────────────────────
def test_canonical_column_matches_the_spec_example() -> None:
    assert canonical_column(PriceField.CLOSE, AdjustmentBasis.TRADJ) == "close_tradj"


@pytest.mark.parametrize(
    "field, basis", list(itertools.product(PriceField, AdjustmentBasis))
)
def test_parse_column_inverts_canonical_column_over_the_full_cross_product(
    field: PriceField, basis: AdjustmentBasis
) -> None:
    assert parse_column(canonical_column(field, basis)) == (field, basis)


def test_canonical_column_accepts_plain_strings_too() -> None:
    assert canonical_column("close", "tradj") == "close_tradj"
    assert canonical_column("CLOSE", "TRADJ") == "close_tradj"


@pytest.mark.parametrize("bad", ["closing", "close_adjusted", "tradj_close", "cloze_raw"])
def test_canonical_column_refuses_a_field_or_basis_it_does_not_know(bad: str) -> None:
    with pytest.raises(PriceError):
        parse_column(bad)


@pytest.mark.parametrize("bad", ["close", "price", "value", "px", 17, None])
def test_parse_column_refuses_a_name_that_carries_no_basis(bad) -> None:
    """No honest ``(field, basis)`` pair can be recovered from an unqualified name —
    which is the whole problem."""
    with pytest.raises(PriceError):
        parse_column(bad)


def test_canonical_column_raises_on_an_unknown_basis() -> None:
    with pytest.raises(PriceError):
        canonical_column("close", "adjusted")


# ── the ambiguity census ─────────────────────────────────────────────────────
def test_is_ambiguous_is_true_for_close_and_false_for_close_tradj() -> None:
    assert is_ambiguous("close") is True
    assert is_ambiguous("close_tradj") is False


@pytest.mark.parametrize("name", sorted(AMBIGUOUS_NAMES))
def test_every_censused_ambiguous_name_is_flagged(name: str) -> None:
    assert is_ambiguous(name) is True
    assert is_ambiguous(name.upper()) is True      # case-insensitive
    assert is_ambiguous(f"  {name} ") is True      # whitespace-insensitive


def test_the_ambiguous_set_is_exactly_the_spec_list() -> None:
    assert AMBIGUOUS_NAMES == frozenset(
        {"close", "price", "value", "last", "px", "close_price", "adj_close", "adjclose"}
    )


@pytest.mark.parametrize(
    "field, basis", list(itertools.product(PriceField, AdjustmentBasis))
)
def test_no_canonical_name_is_ever_ambiguous(field, basis) -> None:
    """The naming law only works if the lawful names are disjoint from the banned ones."""
    assert is_ambiguous(canonical_column(field, basis)) is False


def test_is_ambiguous_does_not_explode_on_a_non_string() -> None:
    assert is_ambiguous(None) is False
    assert is_ambiguous(17) is False


# ── the measured truth of today's stores ─────────────────────────────────────
def test_known_store_bases_carries_the_measured_truth() -> None:
    """NVDA 2024-06-03: 114.80 / 114.80 / 115.00 / 1150.00, all named some form of
    "close".  Editing this map without re-measuring is the failure it prevents."""
    assert KNOWN_STORE_BASES == {
        "data/stocks:close": AdjustmentBasis.TRADJ,
        "data/yahoo:close": AdjustmentBasis.TRADJ,
        "data/yahoo:close_price": AdjustmentBasis.SADJ,
        "data/massive_stock_day:close": AdjustmentBasis.RAW,
    }


def test_the_same_column_name_means_different_bases_in_different_stores() -> None:
    """The defect in one assertion: `close` is total-return in two stores and the raw
    print in a third, a 10x difference on the same date."""
    assert (KNOWN_STORE_BASES["data/stocks:close"]
            is KNOWN_STORE_BASES["data/yahoo:close"]
            is AdjustmentBasis.TRADJ)
    assert KNOWN_STORE_BASES["data/massive_stock_day:close"] is AdjustmentBasis.RAW
    assert KNOWN_STORE_BASES["data/yahoo:close"] != KNOWN_STORE_BASES["data/massive_stock_day:close"]


def test_yahoos_two_columns_invert_intuition() -> None:
    """`close` is the TOTAL-RETURN series; `close_price` is the traded basis the repo
    itself calls "the correct basis for all structure math"."""
    assert KNOWN_STORE_BASES["data/yahoo:close"] is AdjustmentBasis.TRADJ
    assert KNOWN_STORE_BASES["data/yahoo:close_price"] is AdjustmentBasis.SADJ


def test_every_legacy_store_column_recorded_here_is_an_ambiguous_name() -> None:
    """That is why the map has to exist: not one of these names says what it is."""
    for key in KNOWN_STORE_BASES:
        assert is_ambiguous(key.split(":", 1)[1]) is True


def test_data_stocks_is_recorded_as_having_no_open_column() -> None:
    assert "data/stocks" in STORES_WITHOUT_OPEN
    assert "data/stocks:open" not in KNOWN_STORE_BASES
