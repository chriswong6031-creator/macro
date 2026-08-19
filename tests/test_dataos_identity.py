"""Identity spine contracts (Data OS §D2) — ``lib/dataos/identity.py``.

The regression this suite exists for is the MMC->MRSH rename recorded in
``lib/ticker_aliases.py``: a timeless two-entry alias dict living in one collector
and not its sibling left ``data/baskets/ohlcv/MMC.parquet`` nonexistent for seven
months, and the `insurance` basket rendered 18/19 members with nothing going red.
``test_alias_table_answers_differently_either_side_of_the_mmc_rename`` is that
incident, pinned.

Pure unit tests: no ``data/`` read anywhere, so the suite is identical on a full
checkout and in a thin CI lane.

Run: .venv/bin/python -m pytest tests/test_dataos_identity.py -q
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from lib.dataos.identity import (
    XASE,
    XBSE,
    XHKG,
    XNAS,
    XNYS,
    XSHE,
    XSHG,
    XTSE,
    XTSX,
    AliasRow,
    CNBoard,
    IdentityError,
    IssuerMaster,
    KNOWN_MICS,
    ListingKey,
    SecurityIssuerRow,
    VendorAliasTable,
    cn_board,
    fx_id,
    future_id,
    index_id,
    issuer_id,
    listing_id,
    normalize_cn_symbol,
    normalize_hk_symbol,
    option_contract_id,
    parse_fx_id,
    parse_future_id,
    parse_id,
    parse_index_id,
    parse_listing_key,
    parse_option_contract_id,
    security_id,
)

MMC = ListingKey("US", XNYS, "MMC")
AAPL = ListingKey("US", XNAS, "AAPL")
MAOTAI = ListingKey("CN", XSHG, "600519")
TENCENT = ListingKey("HK", XHKG, "00700")


# ── listing keys ─────────────────────────────────────────────────────────────
def test_the_nine_venues_the_repo_actually_carries_are_all_known() -> None:
    assert KNOWN_MICS == {XNYS, XNAS, XASE, XSHG, XSHE, XBSE, XHKG, XTSE, XTSX}


@pytest.mark.parametrize(
    "key, rendered",
    [
        (MMC, "US-XNYS-MMC"),
        (ListingKey("US", XNYS, "MMC", 2), "US-XNYS-MMC.2"),
        (MAOTAI, "CN-XSHG-600519"),
        (ListingKey("CN", XSHE, "000001"), "CN-XSHE-000001"),
        (ListingKey("CN", XBSE, "920163"), "CN-XBSE-920163"),
        (TENCENT, "HK-XHKG-00700"),
        (ListingKey("US", XNYS, "BRK-B"), "US-XNYS-BRK-B"),
        (ListingKey("US", XNYS, "BRK.B"), "US-XNYS-BRK.B"),
    ],
)
def test_listing_key_round_trips_through_its_rendered_form(key: ListingKey, rendered: str) -> None:
    assert key.render() == rendered
    assert parse_listing_key(rendered) == key


def test_a_dotted_class_suffix_is_not_read_as_a_disambiguator() -> None:
    """``BRK.B`` is a share class; only a ``.<digits>`` tail is the collision suffix."""
    assert parse_listing_key("US-XNYS-BRK.B").code == "BRK.B"
    assert parse_listing_key("US-XNYS-BRK.B").disambiguator is None
    assert parse_listing_key("US-XNYS-MMC.2").disambiguator == 2


@pytest.mark.parametrize(
    "bad",
    ["", "MMC", "US-MMC", "US-XNYS-", "-XNYS-MMC", "USA-XNYS-MMC", "us-XXXX-MMC"],
)
def test_malformed_listing_keys_raise_rather_than_degrade(bad: str) -> None:
    with pytest.raises(IdentityError):
        parse_listing_key(bad)


def test_disambiguator_one_is_refused_as_a_second_spelling_of_the_first_listing() -> None:
    with pytest.raises(IdentityError):
        ListingKey("US", XNYS, "MMC", 1)


def test_an_unknown_mic_is_refused_because_the_venue_list_is_closed() -> None:
    with pytest.raises(IdentityError):
        ListingKey("US", "XXXX", "MMC")


# ── issuer / security / listing ids ──────────────────────────────────────────
def test_the_three_id_forms_round_trip_and_carry_a_visible_kind() -> None:
    assert security_id(MMC) == "SEC:US-XNYS-MMC"
    assert issuer_id(MMC) == "ISS:US-XNYS-MMC"
    assert listing_id(MMC) == "US-XNYS-MMC"
    assert parse_id("SEC:US-XNYS-MMC") == ("security", MMC)
    assert parse_id("ISS:US-XNYS-MMC") == ("issuer", MMC)
    assert parse_id("US-XNYS-MMC") == ("listing", MMC)


def test_ids_accept_a_rendered_key_as_well_as_the_object() -> None:
    assert security_id("CN-XSHG-600519") == security_id(MAOTAI)


def test_parse_id_refuses_an_instrument_class_id_instead_of_half_answering() -> None:
    """``OPT:``/``FUT:``/``IDX:``/``FX:`` are not listing keys; a half-truth here is
    how a concept confusion reaches a store."""
    for other in ("OPT:US-XNAS-AAPL:20260918:C:00250000", "FUT:XCBF:VX:202609",
                  "IDX:SPDJI-SPX", "FX:USDCNH"):
        with pytest.raises(IdentityError):
            parse_id(other)


def test_the_id_survives_the_rename_that_motivates_the_project() -> None:
    """MMC->MRSH changed the symbol, not the listing: the id is the INCEPTION code."""
    assert security_id(MMC) == "SEC:US-XNYS-MMC"
    assert security_id(ListingKey("US", XNAS, "FISV")) == "SEC:US-XNAS-FISV"


# ── option contract ids ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "strike, encoded",
    [
        ("250", "00250000"),
        ("250.50", "00250500"),      # fractional strike — the float-corruption case
        (Decimal("250.50"), "00250500"),
        ("4000", "04000000"),        # high strike
        ("0.125", "00000125"),       # sub-dollar, tenth-of-a-cent
        ("99999.999", "99999999"),   # the top of the 8-digit field
    ],
)
def test_option_contract_id_scales_the_strike_by_1000_into_eight_digits(
    strike, encoded: str
) -> None:
    oid = option_contract_id(AAPL, date(2026, 9, 18), "C", strike)
    assert oid == f"OPT:US-XNAS-AAPL:20260918:C:{encoded}"
    underlying, expiry, right, parsed_strike = parse_option_contract_id(oid)
    assert (underlying, expiry, right) == (AAPL, date(2026, 9, 18), "C")
    assert parsed_strike == Decimal(str(strike))


def test_option_contract_id_matches_the_spec_example() -> None:
    assert option_contract_id(AAPL, date(2026, 9, 18), "C", "250") == \
        "OPT:US-XNAS-AAPL:20260918:C:00250000"


def test_a_put_round_trips_too() -> None:
    oid = option_contract_id(AAPL, date(2026, 1, 16), "P", "175.25")
    assert oid == "OPT:US-XNAS-AAPL:20260116:P:00175250"
    assert parse_option_contract_id(oid)[2] == "P"


def test_a_float_strike_is_refused_because_binary_float_silently_mints_another_contract() -> None:
    with pytest.raises(IdentityError, match="never float"):
        option_contract_id(AAPL, date(2026, 9, 18), "C", 250.10)


def test_a_strike_finer_than_a_tenth_of_a_cent_raises_instead_of_rounding() -> None:
    with pytest.raises(IdentityError):
        option_contract_id(AAPL, date(2026, 9, 18), "C", "250.0001")


@pytest.mark.parametrize(
    "bad",
    [
        "OPT:US-XNAS-AAPL:20260918:X:00250000",   # not a right
        "OPT:US-XNAS-AAPL:2026918:C:00250000",    # short date
        "OPT:US-XNAS-AAPL:20260918:C:250000",     # unpadded strike
        "OPT:US-XNAS-AAPL:20261332:C:00250000",   # impossible month/day
        "US-XNAS-AAPL:20260918:C:00250000",       # no OPT prefix
    ],
)
def test_malformed_option_ids_raise(bad: str) -> None:
    with pytest.raises(IdentityError):
        parse_option_contract_id(bad)


# ── other instrument classes ─────────────────────────────────────────────────
def test_future_index_and_fx_ids_round_trip() -> None:
    assert future_id("XCBF", "VX", "202609") == "FUT:XCBF:VX:202609"
    assert parse_future_id("FUT:XCBF:VX:202609") == ("XCBF", "VX", "202609")
    assert future_id("XCBF", "vx", date(2026, 9, 16)) == "FUT:XCBF:VX:202609"

    assert index_id("SPDJI", "SPX") == "IDX:SPDJI-SPX"
    assert parse_index_id("IDX:SPDJI-SPX") == ("SPDJI", "SPX")

    assert fx_id("USD", "CNH") == "FX:USDCNH"
    assert parse_fx_id("FX:USDCNH") == ("USD", "CNH")


def test_fx_refuses_a_pair_of_one_currency_and_futures_refuse_a_thirteenth_month() -> None:
    with pytest.raises(IdentityError):
        fx_id("USD", "USD")
    with pytest.raises(IdentityError):
        future_id("XCBF", "VX", "202613")


# ── China A-share normalization ──────────────────────────────────────────────
def test_the_measured_tushare_vs_repository_divergence_normalizes_to_one_key() -> None:
    """TuShare emits ``600519.SH``; the repository ticker is ``600519.SS``."""
    keys = {
        normalize_cn_symbol("600519.SH"),
        normalize_cn_symbol("600519.SS"),
        normalize_cn_symbol("600519"),
        normalize_cn_symbol(" 600519.ss "),
        normalize_cn_symbol("SH600519"),
    }
    assert keys == {MAOTAI}
    assert MAOTAI.render() == "CN-XSHG-600519"


@pytest.mark.parametrize(
    "symbol, mic, board",
    [
        ("920163", XBSE, CNBoard.BSE),          # BSE — spine contract's canonical 920xxx
        ("920163.BJ", XBSE, CNBoard.BSE),
        ("688981", XSHG, CNBoard.STAR),         # STAR on Shanghai
        ("689009.SH", XSHG, CNBoard.STAR),
        ("300750", XSHE, CNBoard.CHINEXT),      # ChiNext on Shenzhen
        ("309999.SZ", XSHE, CNBoard.CHINEXT),   # top of the official 300000-309999 range
        ("600519", XSHG, CNBoard.MAIN),
        ("000001.SZ", XSHE, CNBoard.MAIN),
        ("002594", XSHE, CNBoard.MAIN),
    ],
)
def test_board_and_venue_follow_the_cn_spine_contract_ranges(
    symbol: str, mic: str, board: CNBoard
) -> None:
    key = normalize_cn_symbol(symbol)
    assert key.country == "CN"
    assert key.mic == mic
    assert cn_board(key.code) is board


def test_a_declared_venue_that_contradicts_the_code_range_raises() -> None:
    """``600519.SZ`` is two facts that cannot both be true — refuse to pick one."""
    with pytest.raises(IdentityError, match="refusing to guess"):
        normalize_cn_symbol("600519.SZ")


# ── old BJ codes are ALIASES, and this module cannot resolve them ────────────
#: The spine contract, twice: "Old BJ codes remain aliases. Every canonical BSE
#: mapping target must be ``920xxx``" and "other admitted A code families are main
#: board" (research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:89-92).
LEGACY_BJ_CODES = ["430047", "833819", "871981", "838275", "400001", "420001"]


@pytest.mark.parametrize("code", LEGACY_BJ_CODES)
def test_an_old_bj_alias_code_is_refused_rather_than_minted_as_a_canonical_key(
    code: str,
) -> None:
    """THE DUPLICATE-IDENTITY BUG THIS MODULE EXISTS TO END, produced by the module.

    ``430047`` is a historical ALIAS of a BSE security whose canonical code is
    ``920163``. Minting ``CN-XBSE-430047`` from it gives that one security two
    identities — ``SEC:CN-XBSE-920163`` from the canonical feed and
    ``SEC:CN-XBSE-430047`` from a legacy TuShare pull — which join as two different
    securities in the security master and are never reconciled, because neither side
    is wrong on its face.

    This module carries NO ``bse_mapping`` table, so it has no authority to resolve
    an alias to its canonical code. Refusing is the fail-closed behaviour the rest of
    the file already uses; the resolution belongs to the alias table.
    """
    with pytest.raises(IdentityError, match="920"):
        normalize_cn_symbol(code)
    with pytest.raises(IdentityError, match="920"):
        cn_board(code)


@pytest.mark.parametrize("code", LEGACY_BJ_CODES)
def test_an_explicit_bj_suffix_does_not_buy_an_alias_code_a_canonical_key(
    code: str,
) -> None:
    """The declared-venue escape hatch must NOT reach here.

    ``normalize_cn_symbol`` trusts an explicit suffix when the code family is unknown
    (``inferred = declared``). That is right for an unrecognised family and WRONG
    here: the venue was never the doubt. ``430047.BJ`` says "this is on the BSE",
    which is true and does not make ``430047`` a canonical key.
    """
    with pytest.raises(IdentityError, match="920"):
        normalize_cn_symbol(f"{code}.BJ")
    with pytest.raises(IdentityError, match="920"):
        normalize_cn_symbol(f"BJ{code}")


def test_the_canonical_bse_code_family_still_normalizes() -> None:
    """The refusal above is scoped to the alias families; 920xxx is unaffected."""
    key = normalize_cn_symbol("920163")
    assert key.render() == "CN-XBSE-920163"
    assert cn_board("920163") is CNBoard.BSE
    assert normalize_cn_symbol("920163.BJ") == key


def test_the_cdr_range_stays_chinext_on_shenzhen() -> None:
    """The other half of the contract sentence, which was already right: the official
    SZ 300000-309999 allocation is ChiNext INCLUDING the 309800-309999 CDR range."""
    for code in ("309800", "309999"):
        assert normalize_cn_symbol(code).render() == f"CN-XSHE-{code}"
        assert cn_board(code) is CNBoard.CHINEXT


@pytest.mark.parametrize("bad", ["", "60051", "6005199", "ABCDEF", "600519.XX", "600519.HK"])
def test_unusable_cn_symbols_raise(bad: str) -> None:
    with pytest.raises(IdentityError):
        normalize_cn_symbol(bad)


# ── Hong Kong ────────────────────────────────────────────────────────────────
def test_every_hk_spelling_pads_to_the_exchanges_five_digit_code() -> None:
    assert normalize_hk_symbol("700") == normalize_hk_symbol("0700.HK")
    assert normalize_hk_symbol("700") == TENCENT
    assert {normalize_hk_symbol(s) for s in ("700", "0700", "00700", "0700.HK", "700.hk")} == {
        TENCENT
    }
    assert TENCENT.render() == "HK-XHKG-00700"


@pytest.mark.parametrize("bad", ["", "007000", "70A", "0700.SS"])
def test_unusable_hk_symbols_raise(bad: str) -> None:
    with pytest.raises(IdentityError):
        normalize_hk_symbol(bad)


# ── the vendor alias table — the MMC/MRSH regression ─────────────────────────
RENAME = date(2026, 1, 14)

#: The incident, as rows.  ``valid_to`` is EXCLUSIVE, which is what makes the
#: changeover day itself unambiguous.
MMC_ALIASES = [
    {"vendor": "yahoo", "vendor_symbol": "MMC", "security_id": "SEC:US-XNYS-MMC",
     "valid_from": None, "valid_to": "2026-01-14"},
    {"vendor": "yahoo", "vendor_symbol": "MRSH", "security_id": "SEC:US-XNYS-MMC",
     "valid_from": "2026-01-14", "valid_to": None},
    # Fiserv: the vendor LAGS the rename — Yahoo still serves the pre-rename symbol.
    {"vendor": "yahoo", "vendor_symbol": "FISV", "security_id": "SEC:US-XNAS-FISV",
     "valid_from": None, "valid_to": None},
]


def test_alias_table_answers_differently_either_side_of_the_mmc_rename() -> None:
    """THE regression test for the seven-month silent production loss.

    ``lib/ticker_aliases.py`` is timeless, so it can say "MMC means MRSH" but cannot
    say "MMC meant MMC before 2026-01-14".  A backfill reading history through a
    timeless map re-labels the past and nothing downstream can see it.
    """
    table = VendorAliasTable.from_records(MMC_ALIASES)
    day_before, day_of = date(2026, 1, 13), RENAME

    # forward: vendor symbol -> security
    assert table.resolve("yahoo", "MMC", day_before) == "SEC:US-XNYS-MMC"
    assert table.resolve("yahoo", "MMC", day_of) is None
    assert table.resolve("yahoo", "MRSH", day_before) is None
    assert table.resolve("yahoo", "MRSH", day_of) == "SEC:US-XNYS-MMC"

    # reverse: security -> what the vendor called it that day
    assert table.vendor_symbol_for("yahoo", "SEC:US-XNYS-MMC", day_before) == "MMC"
    assert table.vendor_symbol_for("yahoo", "SEC:US-XNYS-MMC", day_of) == "MRSH"
    assert table.vendor_symbol_for("yahoo", "SEC:US-XNYS-MMC", date(2026, 8, 12)) == "MRSH"


def test_the_lagging_rename_direction_is_the_same_table() -> None:
    """Fiserv renamed FISV->FI in 2023 and Yahoo still serves the OLD symbol."""
    table = VendorAliasTable.from_records(MMC_ALIASES)
    assert table.vendor_symbol_for("yahoo", "SEC:US-XNAS-FISV", date(2026, 8, 12)) == "FISV"


def test_an_unmapped_symbol_returns_none_rather_than_guessing_identity() -> None:
    table = VendorAliasTable.from_records(MMC_ALIASES)
    assert table.resolve("yahoo", "NVDA", RENAME) is None
    assert table.resolve("tushare", "MMC", date(2020, 1, 1)) is None


def test_an_overlapping_pair_of_rows_is_refused_at_construction() -> None:
    """A translation layer that can return either of two answers is not one."""
    with pytest.raises(IdentityError, match="ambiguous alias table"):
        VendorAliasTable.from_records([
            {"vendor": "yahoo", "vendor_symbol": "MMC", "security_id": "SEC:US-XNYS-MMC",
             "valid_from": None, "valid_to": "2026-02-01"},
            {"vendor": "yahoo", "vendor_symbol": "MMC", "security_id": "SEC:US-XNYS-OTHER",
             "valid_from": "2026-01-14", "valid_to": None},
        ])


def test_alias_rows_carry_half_open_intervals() -> None:
    row = AliasRow("yahoo", "MMC", "SEC:US-XNYS-MMC", None, RENAME)
    assert row.covers(date(2026, 1, 13))
    assert not row.covers(RENAME)          # valid_to is EXCLUSIVE
    assert row.covers(date(1990, 1, 1))    # open lower bound


def test_a_record_missing_a_required_column_raises_with_the_column_named() -> None:
    with pytest.raises(IdentityError, match="security_id"):
        VendorAliasTable.from_records([{"vendor": "yahoo", "vendor_symbol": "MMC"}])


# ── the issuer master reader — V4-D2B1 (§3 Reader API) ─────────────────────────
def test_issuer_master_finds_securities_of_a_shared_issuer() -> None:
    """The §9.7 canonical query, pure over a hand-built record set — GOOG/GOOGL."""
    im = IssuerMaster.from_records([
        {"security_id": "SEC:US-XNAS-GOOG", "issuer_id": "ISS:US-XNAS-GOOG",
         "issuer_state": "RESOLVED", "listing_key": "US-XNAS-GOOG"},
        {"security_id": "SEC:US-XNAS-GOOGL", "issuer_id": "ISS:US-XNAS-GOOG",
         "issuer_state": "RESOLVED", "listing_key": "US-XNAS-GOOGL"},
        {"security_id": "SEC:US-XNYS-MMC", "issuer_id": "ISS:US-XNYS-MMC",
         "issuer_state": "RESOLVED", "listing_key": "US-XNYS-MMC"},
    ])
    assert im.securities_of_issuer("ISS:US-XNAS-GOOG") == (
        "SEC:US-XNAS-GOOG", "SEC:US-XNAS-GOOGL",
    )
    assert im.securities_of_issuer("ISS:US-XNYS-MMC") == ("SEC:US-XNYS-MMC",)
    assert im.issuer_of_security("SEC:US-XNAS-GOOGL") == "ISS:US-XNAS-GOOG"
    assert im.issuer_of_security("SEC:US-XNAS-GOOG") == "ISS:US-XNAS-GOOG"


def test_issuer_master_answers_none_never_a_guess() -> None:
    im = IssuerMaster.from_records([
        {"security_id": "SEC:US-XNAS-AEP", "issuer_id": None,
         "issuer_state": "NO_ISSUER_EVIDENCE", "listing_key": "US-XNAS-AEP"},
    ])
    assert im.issuer_of_security("SEC:US-XNAS-AEP") is None
    assert im.issuer_of_security("SEC:UNKNOWN") is None
    assert im.securities_of_issuer("ISS:UNKNOWN") == ()
    # A null-issuer row is never indexed under any issuer_id.
    assert im.securities_of_issuer(None) == ()  # type: ignore[arg-type]


def test_issuer_master_from_records_is_nan_safe_without_pandas() -> None:
    """V4-D2B1 FIX 3 (M1): a ``pandas`` ``to_dict("records")`` round-trip can hand
    back a genuine ``float('nan')`` — never ``None`` — for a null cell in a nullable
    string column that also carries real strings.  ``lib/dataos/identity.py`` is
    stdlib-only (module docstring) and must catch this WITHOUT importing pandas; a
    NaN ``issuer_id`` must index as NO issuer, never the literal string ``'nan'``.
    """
    nan = float("nan")
    im = IssuerMaster.from_records([
        {"security_id": "SEC:US-XNAS-AEP", "issuer_id": nan,
         "issuer_state": nan, "listing_key": nan},
        {"security_id": "SEC:US-XNAS-GOOG", "issuer_id": "ISS:US-XNAS-GOOG",
         "issuer_state": "RESOLVED", "listing_key": "US-XNAS-GOOG"},
    ])
    assert im.issuer_of_security("SEC:US-XNAS-AEP") is None
    # The literal string 'nan' must never appear as a key or a matchable issuer id.
    assert im.securities_of_issuer("nan") == ()
    assert "nan" not in im._by_issuer  # noqa: SLF001 — pinning the index directly
    assert im.issuer_of_security("SEC:US-XNAS-GOOG") == "ISS:US-XNAS-GOOG"


def test_issuer_master_from_records_requires_security_id() -> None:
    with pytest.raises(IdentityError, match="security_id"):
        IssuerMaster.from_records([{"issuer_id": "ISS:US-XNYS-MMC"}])


def test_security_issuer_row_is_a_frozen_pure_value() -> None:
    row = SecurityIssuerRow(security_id="SEC:US-XNYS-MMC", issuer_id="ISS:US-XNYS-MMC",
                            issuer_state="RESOLVED", listing_key="US-XNYS-MMC")
    with pytest.raises(Exception):  # noqa: BLE001 — frozen dataclass raises FrozenInstanceError
        row.security_id = "SEC:US-XNYS-OTHER"  # type: ignore[misc]


def test_issuer_id_and_parse_id_are_unchanged_by_the_issuer_axis() -> None:
    """Spec §2: grammar unchanged — ``issuer_id()``/``parse_id()`` stay pure
    renderers; WHICH listing key the builder passes to ``issuer_id()`` is what
    changed, not the function itself."""
    assert issuer_id(MMC) == "ISS:US-XNYS-MMC"
    assert parse_id("ISS:US-XNAS-GOOG") == ("issuer", ListingKey("US", XNAS, "GOOG"))
