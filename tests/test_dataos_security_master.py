"""Regression teeth for the security master + the time-scoped vendor alias table (DOS-1.1).

WHAT THIS SUITE IS FOR.  ``tests/test_dataos_identity.py`` pins the identity VOCABULARY
against hand-built rows; nothing pinned the ARTIFACTS the vocabulary was built to
produce.  The two renames below are the whole reason the Data OS identity spine exists,
and each is a measured production defect, not a hypothetical:

* **MMC -> MRSH, 2026-01-14.**  Marsh McLennan changed its NYSE symbol (same listing,
  same CUSIP).  Yahoo migrated the whole history onto MRSH while
  ``scripts/fetch_basket_ohlcv`` carried only the FI->FISV entry, so
  ``data/baskets/ohlcv/MMC.parquet`` came to never exist: the ``insurance`` basket
  rendered 18/19 members and ``us_sector_financials`` 75/76 for SEVEN MONTHS and
  nothing went red (``lib/ticker_aliases.py`` module docstring).
* **SATS -> ECHO, 2026-06-24.**  EchoStar is logged TWICE in
  ``data/signal_archive/track_record.parquet`` — SATS 128 rows and ECHO 128 rows,
  identical ``(date, type)`` key sets, all 39 identity columns byte-identical — so
  every hit-rate, forward-return and drawdown statistic over that ledger
  DOUBLE-WEIGHTS one name (``engine/ledger_identity.py`` module docstring).  A table
  that knew MMC and not SATS would have reproduced the exact fragmentation being fixed.

Both halves are tested: the COMMITTED artifacts (which is what a consumer would read)
and the pure functions over fixtures (which is what a future change would break first).

TWO CLOCKS, PINNED APART (adversarial review, 2026-08-13).  A rename gives a security
two names and there are two different questions about them, so the table carries two
FAMILIES of vendor space and this suite refuses to let them be confused:

* HISTORICAL NAMING (``yahoo``, ``membership``, ``ledger``) — "what did this space call
  it ON that day", DATED across the rename.
* CURRENT CATALOG (``yahoo_fetch``, ``store``) — "what string do I use TODAY, for a bar
  of ANY date", ONE open-bounded row at today's symbol.

Reading the first as the second is the seven-month MMC outage in a new costume: Yahoo
migrated Marsh's WHOLE history onto MRSH, so a §11.4 backfill of 2020 that requested the
historically-correct ``MMC`` gets "possibly delisted, no price data found".

Run: python -m pytest tests/test_dataos_security_master.py -q
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.dataos.identity import (  # noqa: E402
    AliasRow,
    IdentityError,
    VendorAliasTable,
)
from lib.dataos.registry import DatasetStatus, load_registry  # noqa: E402
from scripts import build_security_master as BUILD  # noqa: E402

MASTER_PATH = ROOT / "data" / "reference" / "security_master.parquet"
ALIASES_PATH = ROOT / "data" / "reference" / "vendor_aliases.parquet"
RECEIPT_PATH = ROOT / "data" / "reference" / "_receipt.json"
MANIFEST_PATH = ROOT / ".github" / "ci" / "legacy-jobs.yml"

#: The remedy printed by every freshness/staleness assertion below.  One command.
REBUILD = "python3 scripts/build_security_master.py --report"

#: The two ids the whole task is about.  Both are the INCEPTION code, never today's
#: symbol: Marsh trades as MRSH today and EchoStar as ECHO, and an id built on either
#: would move the next time a symbol moves — which is the defect, not the fix.
MMC_ID = "SEC:US-XNYS-MMC"
SATS_ID = "SEC:US-XNAS-SATS"

MMC_RENAME = date(2026, 1, 14)
SATS_RENAME = date(2026, 6, 24)


# ── committed artifacts ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def master() -> pd.DataFrame:
    assert MASTER_PATH.is_file(), (
        f"{MASTER_PATH} is missing — config/dataset_registry.yml marks "
        "reference.security_master PRODUCED, and gate G1 says a row may not claim a "
        "store that does not exist"
    )
    return pd.read_parquet(MASTER_PATH)


@pytest.fixture(scope="module")
def aliases() -> pd.DataFrame:
    assert ALIASES_PATH.is_file(), f"{ALIASES_PATH} is missing (gate G1)"
    return pd.read_parquet(ALIASES_PATH)


@pytest.fixture(scope="module")
def table(aliases: pd.DataFrame) -> VendorAliasTable:
    """The COMMITTED table, read through the one canonical reader and nothing else."""
    records = [
        {
            "vendor": row["vendor"],
            "vendor_symbol": row["vendor_symbol"],
            "security_id": row["security_id"],
            "valid_from": BUILD._normalize_bound(row["valid_from"]),
            "valid_to": BUILD._normalize_bound(row["valid_to"]),
        }
        for row in aliases.to_dict("records")
    ]
    return VendorAliasTable.from_records(records)


@pytest.fixture(scope="module")
def receipt() -> dict:
    assert RECEIPT_PATH.is_file(), f"{RECEIPT_PATH} is missing"
    return json.loads(RECEIPT_PATH.read_text())


# ── THE MMC BOUNDARY ──────────────────────────────────────────────────────────
def test_mmc_and_mrsh_are_one_security_and_the_table_answers_differently_either_side(
    table: VendorAliasTable,
) -> None:
    """The 7-month silent loss, expressed as an assertion.

    Interval convention: ``valid_from`` INCLUSIVE, ``valid_to`` EXCLUSIVE.  So the
    boundary date 2026-01-14 falls on the **NEW** side — on that day the answer is
    MRSH and MMC is already out of scope.  That is the point of the half-open
    convention: an inclusive end would leave BOTH rows valid on 2026-01-14, which is
    exactly the day the answer has to be unambiguous.
    """
    assert table.resolve("yahoo", "MMC", date(2026, 1, 13)) == MMC_ID
    assert table.resolve("yahoo", "MRSH", date(2026, 1, 15)) == MMC_ID

    # DIFFERENTLY either side — not merely "both resolve".
    assert table.resolve("yahoo", "MRSH", date(2026, 1, 13)) is None
    assert table.resolve("yahoo", "MMC", date(2026, 1, 15)) is None

    # The exact boundary date, both symbols, on the NEW side.
    assert table.resolve("yahoo", "MRSH", MMC_RENAME) == MMC_ID
    assert table.resolve("yahoo", "MMC", MMC_RENAME) is None


def test_the_membership_key_did_not_move_when_the_vendor_symbol_did(
    table: VendorAliasTable,
) -> None:
    """`breadth.ticker_fixups` pins MRSH back to MMC: THIS join key is stable by charter.

    The two spaces disagreeing is the NORMAL state, and expressing it is what the table
    is for — ``lib/ticker_aliases.py``: "Site copy, page slugs and ledger keys keep the
    membership ticker; this only ever decides what string goes to the vendor."
    """
    for on in (date(2026, 1, 13), MMC_RENAME, date(2026, 1, 15)):
        assert table.resolve("membership", "MMC", on) == MMC_ID
    # ...and no MRSH membership row was invented on the other side of the boundary.
    assert table.resolve("membership", "MRSH", date(2026, 1, 15)) is None


def test_the_membership_key_DID_move_for_echostar_and_the_table_says_so(
    table: VendorAliasTable,
) -> None:
    """The half that shipped wrong on 2026-08-12 and was caught in review a day later.

    The membership space does NOT generalise from Marsh.  `breadth.ticker_fixups` pins
    MRSH back to MMC — Marsh's repo-side key deliberately did not move — while
    `quality.ticker_key_migrations` ratifies SATS->ECHO, which IS the repo-side key
    moving on 2026-06-24 (``data/stocks/SATS.parquet`` no longer exists;
    ``data/stocks/ECHO.parquet`` holds the spliced history).  The first cut gave the
    membership space one open-bounded row at ``ECHO``, so EchoStar's entire repo-side
    PAST was re-labelled ECHO and ``resolve("membership", "SATS", <any date>)`` was
    ``None`` — the repo's own stored key, unresolvable — which is precisely the
    timeless-map defect the time-scoping exists to end, shipped inside the artifact
    that ends it.  Invisible because no test asked the membership question for SATS.
    """
    assert table.resolve("membership", "SATS", date(2026, 1, 1)) == SATS_ID
    assert table.resolve("membership", "SATS", date(2026, 6, 23)) == SATS_ID
    assert table.resolve("membership", "SATS", SATS_RENAME) is None
    assert table.resolve("membership", "ECHO", SATS_RENAME) == SATS_ID
    assert table.resolve("membership", "ECHO", date(2026, 6, 23)) is None
    # The inverse is the assertion that would have failed first: on 2026-01-01 the repo
    # called EchoStar SATS, and a table that answers "ECHO" has re-labelled the past.
    assert table.vendor_symbol_for("membership", SATS_ID, date(2026, 1, 1)) == "SATS"
    assert table.vendor_symbol_for("membership", SATS_ID, SATS_RENAME) == "ECHO"


# ── THE TWO CLOCKS ────────────────────────────────────────────────────────────
def test_the_current_catalog_space_reproduces_the_live_fetch_symbol_at_every_date(
    table: VendorAliasTable,
) -> None:
    """`yahoo_fetch` is the row family `supersedes: lib/ticker_aliases.py` rests on.

    ``lib.ticker_aliases.fetch_symbol`` is TIMELESS on purpose: Yahoo migrated Marsh's
    whole history onto MRSH, so the string to REQUEST is MRSH for a 2020 bar just as
    much as for a 2026 one.  A table whose only Yahoo rows were the historical ones
    would return "MMC" for 2020 and a backfill that believed it would get "possibly
    delisted, no price data found" — the seven-month ``insurance`` 18/19 outage, again,
    from the dataset built to prevent it.
    """
    from lib import ticker_aliases

    for key, security in (("MMC", MMC_ID), ("FI", "SEC:US-XNAS-FISV"), ("ECHO", SATS_ID)):
        expected = ticker_aliases.fetch_symbol(key)
        for on in (date(2019, 1, 2), date(2020, 1, 2), MMC_RENAME, SATS_RENAME,
                   date(2026, 8, 1)):
            assert table.vendor_symbol_for("yahoo_fetch", security, on) == expected, (
                f"{key} at {on}: the current catalog must not move with the row's date"
            )
            assert table.resolve("yahoo_fetch", expected, on) == security


def test_the_current_catalog_store_space_names_the_file_that_actually_exists(
    table: VendorAliasTable,
) -> None:
    """`store` is the key `data/stocks/`, `data/baskets/ohlcv/` and the archive carry TODAY.

    Verified against the tree: ``data/stocks/SATS.parquet`` does not exist and
    ``data/stocks/ECHO.parquet`` holds EchoStar back to 2008-01-02, while Marsh went the
    other way — fetched under MRSH, STORED under MMC, so ``data/baskets/ohlcv/MMC.parquet``
    is the file that exists.  One open row per security, for every date.
    """
    for security, key in ((SATS_ID, "ECHO"), (MMC_ID, "MMC"), ("SEC:US-XNAS-FISV", "FI")):
        for on in (date(2008, 1, 2), date(2020, 1, 2), date(2026, 8, 1)):
            assert table.vendor_symbol_for("store", security, on) == key
            assert table.resolve("store", key, on) == security


def test_the_two_clocks_disagree_and_neither_may_be_read_as_the_other(
    table: VendorAliasTable,
) -> None:
    """The distinction, asserted — so §11.4 cannot quietly swap one family for the other.

    On 2020-01-02 Yahoo CALLED Marsh "MMC" (historical, true) and you REQUEST it as
    "MRSH" (current catalog, also true).  Both answers are needed and they are different
    strings; a single space cannot carry both, and a consumer that picks the wrong one
    fails silently, which is the whole reason the families have different names.
    """
    on = date(2020, 1, 2)
    assert table.vendor_symbol_for("yahoo", MMC_ID, on) == "MMC"
    assert table.vendor_symbol_for("yahoo_fetch", MMC_ID, on) == "MRSH"
    assert table.vendor_symbol_for("yahoo", MMC_ID, on) != table.vendor_symbol_for(
        "yahoo_fetch", MMC_ID, on
    )
    # And the historical space is NOT a store resolver either: on 2020-01-02 the repo
    # keyed EchoStar SATS, while the file that holds that bar today is ECHO.parquet.
    assert table.vendor_symbol_for("membership", SATS_ID, on) == "SATS"
    assert table.vendor_symbol_for("store", SATS_ID, on) == "ECHO"


def test_every_ledger_name_echostar_was_ever_logged_under_resolves_to_one_security(
    table: VendorAliasTable,
) -> None:
    """The headline defect, made answerable — the reason SATS is in this table at all.

    ``engine/ledger_identity.py`` measures it: ``data/signal_archive/track_record.parquet``
    carries SATS 128 rows and ECHO 128 rows with IDENTICAL ``(date, type)`` key sets
    spanning 2008-11-25 -> 2026-04-23 — one physical fire logged twice — so every
    hit-rate and forward-return statistic over the ledger DOUBLE-WEIGHTS EchoStar.

    Both spans end BEFORE the 2026-06-24 rename, which is what makes the two clocks
    load-bearing rather than academic: the dead SATS rows are answered by the HISTORICAL
    ledger space at their own row dates, and the live ECHO rows — written under the key
    the repo had already migrated to — by the CURRENT-CATALOG store space, which does
    not move with the row's date.  Asking one space for both is how the first cut
    collapsed zero of the 128 pairs.
    """
    for on in (date(2008, 11, 25), date(2020, 1, 2), date(2026, 4, 23)):
        assert table.resolve("ledger", "SATS", on) == SATS_ID
        assert table.resolve("store", "ECHO", on) == SATS_ID


# ── THE SATS BOUNDARY ─────────────────────────────────────────────────────────
def test_sats_and_echo_are_one_security_and_the_table_answers_differently_either_side(
    table: VendorAliasTable,
) -> None:
    """Same shape as MMC, at 2026-06-24, and for the same reason: one physical name.

    ``engine/ledger_identity.py`` measured what a bare-string key did to the ledger; a
    table that answered this question would have made the double count impossible to
    write.  2026-06-24 is on the NEW side, same half-open convention as MMC.
    """
    assert table.resolve("yahoo", "SATS", date(2026, 6, 23)) == SATS_ID
    assert table.resolve("yahoo", "ECHO", date(2026, 6, 25)) == SATS_ID

    assert table.resolve("yahoo", "ECHO", date(2026, 6, 23)) is None
    assert table.resolve("yahoo", "SATS", date(2026, 6, 25)) is None

    assert table.resolve("yahoo", "ECHO", SATS_RENAME) == SATS_ID
    assert table.resolve("yahoo", "SATS", SATS_RENAME) is None


def test_the_ledger_key_space_carries_the_same_dated_boundary(
    table: VendorAliasTable,
) -> None:
    """`quality.ticker_key_migrations` (SATS -> ECHO) is the space the double count lived in."""
    assert table.resolve("ledger", "SATS", date(2026, 6, 23)) == SATS_ID
    assert table.resolve("ledger", "SATS", SATS_RENAME) is None
    assert table.resolve("ledger", "ECHO", SATS_RENAME) == SATS_ID


def test_the_two_renames_do_not_collapse_into_one_security(table: VendorAliasTable) -> None:
    """Two renames, two securities — a table that merged them would be worse than none."""
    assert MMC_ID != SATS_ID
    assert table.resolve("yahoo", "MRSH", date(2026, 7, 1)) != table.resolve(
        "yahoo", "ECHO", date(2026, 7, 1)
    )


# ── ROUND TRIP ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "vendor,security,on,expected",
    [
        ("yahoo", MMC_ID, date(2026, 1, 13), "MMC"),
        ("yahoo", MMC_ID, MMC_RENAME, "MRSH"),
        ("yahoo", MMC_ID, date(2026, 1, 15), "MRSH"),
        ("yahoo", SATS_ID, date(2026, 6, 23), "SATS"),
        ("yahoo", SATS_ID, SATS_RENAME, "ECHO"),
        ("ledger", SATS_ID, date(2026, 6, 23), "SATS"),
        ("ledger", SATS_ID, date(2026, 6, 25), "ECHO"),
        ("membership", MMC_ID, date(2026, 1, 15), "MMC"),
        # The membership row for the one case where the repo's OWN key moved. Its
        # absence here is what let the timeless `membership/ECHO` row ship.
        ("membership", SATS_ID, date(2026, 6, 23), "SATS"),
        ("membership", SATS_ID, SATS_RENAME, "ECHO"),
        ("membership", "SEC:US-XNAS-FISV", date(2026, 1, 15), "FI"),
        ("yahoo", "SEC:US-XNAS-FISV", date(2026, 1, 15), "FISV"),
        # CURRENT CATALOG: the same answer on both sides of both boundaries, which is
        # the property that makes it a fetch/store resolver and the historical rows not.
        ("yahoo_fetch", MMC_ID, date(2020, 1, 2), "MRSH"),
        ("yahoo_fetch", MMC_ID, date(2026, 1, 13), "MRSH"),
        ("yahoo_fetch", SATS_ID, date(2026, 6, 23), "ECHO"),
        ("yahoo_fetch", "SEC:US-XNAS-FISV", date(2026, 1, 15), "FISV"),
        ("store", MMC_ID, date(2020, 1, 2), "MMC"),
        ("store", SATS_ID, date(2020, 1, 2), "ECHO"),
        ("store", "SEC:US-XNAS-FISV", date(2026, 1, 15), "FI"),
    ],
)
def test_vendor_symbol_for_inverts_resolve_on_both_sides(
    table: VendorAliasTable, vendor: str, security: str, on: date, expected: str
) -> None:
    """The direction ``lib/ticker_aliases.py`` cannot express at all.

    A timeless map re-labels the past on a backfill and nothing downstream can see it;
    the inverse has to be time-scoped too, or "what did this vendor call this security
    in 2025" has no answer.
    """
    assert table.vendor_symbol_for(vendor, security, on) == expected
    assert table.resolve(vendor, expected, on) == security


def test_fiserv_is_carried_with_open_bounds_because_the_date_is_not_citable(
    table: VendorAliasTable,
) -> None:
    """The vendor LAGS this one, and an invented date would be a fabricated fact.

    Yahoo still serves Fiserv under the pre-rename FISV
    (``lib.ticker_aliases.YAHOO_FETCH_ALIASES["FI"] == "FISV"``) and so does the
    exchange symbol directory, while this repo's key is FI.  There is no changeover DAY
    to scope and no in-repo source for the 2023 change, so both rows are open-bounded —
    the honest ABSENCE of a boundary claim rather than a guessed one.
    """
    for on in (date(2019, 1, 2), date(2023, 6, 1), date(2026, 8, 1)):
        assert table.resolve("yahoo", "FISV", on) == "SEC:US-XNAS-FISV"
        assert table.resolve("membership", "FI", on) == "SEC:US-XNAS-FISV"


def test_b_is_fail_closed_until_identity_scoped_continuation_and_reuse_exist(
    master: pd.DataFrame, aliases: pd.DataFrame, receipt: dict
) -> None:
    """A bare GOLD->B pair would merge Barrick with the later Gold.com reuse.

    NYSE B also had a different prior issuer (Barnes Group), so minting an
    open-bounded B alias is independently false.  DOS coverage may be incomplete and
    conspicuous; it may not manufacture a continuous identity to make coverage green.
    """
    assert "SEC:US-XNYS-B" not in set(master["security_id"])
    assert aliases.loc[aliases["vendor_symbol"] == "B"].empty
    assert "B" in receipt["coverage"]["unresolved_names"]
    exceptions = {row["key"]: row for row in receipt["identity_exceptions"]}
    assert set(exceptions) == {"B", "GOLD"}
    assert exceptions["B"]["status"] == "deferred_no_mint"
    assert "Barnes Group" in exceptions["B"]["reason"]
    assert "GOLD->B" in exceptions["B"]["reason"]
    assert "Gold.com" in exceptions["B"]["reason"]
    assert "fail-closed" in exceptions["B"]["reason"]
    assert exceptions["GOLD"]["status"] == "disclosed_existing_alias"
    assert "not issuer-safe" in exceptions["GOLD"]["reason"]
    assert "must not be treated as Barrick/miner history" in exceptions["GOLD"]["reason"]


def test_resolver_refuses_to_mint_b_even_when_the_current_directory_resolves_it() -> None:
    universe = {"B": {"first_seen": date(2023, 5, 9)}}
    [result] = BUILD.resolve_universe(universe, {}, {"B": "N"}, "2026-08-14")
    assert result.key == "B"
    assert result.listing_key is None
    assert result.reason == BUILD.DEFERRED_IDENTITY_KEYS["B"]["reason"]


# ── THE MASTER ────────────────────────────────────────────────────────────────
def test_the_master_mints_on_the_inception_code_not_on_todays_symbol(
    master: pd.DataFrame,
) -> None:
    """State-aware replacement of the old bare ``SEC:->ISS:`` prefix-swap assertion
    (V4-D2B1, per the frozen contract's instruction to update this test to "the new
    law: state-aware; RESOLVED groups share canonical ids").  MMC and SATS are each
    the sole member of their own CIK-evidenced group, so the swap still holds for
    them AS A COROLLARY of mint-once + a single-member canonical tie-break — it is no
    longer a bare invariant of every row (GOOG/GOOGL below is the counter-example)."""
    rows = master.set_index("security_id")
    for security, mic, code in ((MMC_ID, "XNYS", "MMC"), (SATS_ID, "XNAS", "SATS")):
        assert security in rows.index, f"{security} missing from the committed master"
        row = rows.loc[security]
        assert row["mic"] == mic
        assert row["inception_code"] == code
        assert row["issuer_id"] == security.replace("SEC:", "ISS:")
        assert row["listing_key"] == security.replace("SEC:", "")
        assert row["issuer_state"] == "RESOLVED"
        assert row["issuer_cik"], f"{security} should carry CIK evidence"
    # Neither of today's symbols may have minted an id of its own.
    assert "SEC:US-XNYS-MRSH" not in rows.index
    assert "SEC:US-XNAS-ECHO" not in rows.index


# ── V4-D2B1: issuer axis ────────────────────────────────────────────────────────
GOOG_ID = "SEC:US-XNAS-GOOG"
GOOGL_ID = "SEC:US-XNAS-GOOGL"
CANONICAL_GOOG_ISSUER = "ISS:US-XNAS-GOOG"


@pytest.fixture(scope="module")
def issuer_master() -> pd.DataFrame:
    path = ROOT / "data" / "reference" / BUILD.ISSUER_MASTER_NAME
    assert path.is_file(), f"{path} is missing (gate G1)"
    return pd.read_parquet(path)


@pytest.fixture(scope="module")
def issuer_migrations() -> pd.DataFrame:
    path = ROOT / "data" / "reference" / BUILD.ISSUER_MIGRATIONS_NAME
    assert path.is_file(), f"{path} is missing (gate G1)"
    return pd.read_parquet(path)


def test_goog_and_googl_are_two_securities_and_one_issuer(master: pd.DataFrame) -> None:
    """The regression V4-D2B1 exists to make possible (mirrors
    tests/test_theme_graph_identity_resolution.py's flipped GOOG/GOOGL assertion).

    Mutation control (1): GOOG/GOOGL landing on two DIFFERENT issuer_ids again must
    fail this test.
    """
    rows = master.set_index("security_id")
    assert GOOG_ID in rows.index and GOOGL_ID in rows.index
    # Mutation control (2): security_id/listing_key are NEVER touched by the era —
    # still two distinct securities.
    assert GOOG_ID != GOOGL_ID
    assert rows.loc[GOOG_ID, "listing_key"] != rows.loc[GOOGL_ID, "listing_key"]
    goog_issuer = rows.loc[GOOG_ID, "issuer_id"]
    googl_issuer = rows.loc[GOOGL_ID, "issuer_id"]
    assert goog_issuer == googl_issuer == CANONICAL_GOOG_ISSUER
    for security_id_ in (GOOG_ID, GOOGL_ID):
        assert rows.loc[security_id_, "issuer_state"] == "RESOLVED"
        assert rows.loc[security_id_, "issuer_cik"] == "0001652044"


def test_googl_is_the_migrated_member_not_goog(
    master: pd.DataFrame, issuer_migrations: pd.DataFrame,
) -> None:
    """Rule 4 (lowest full listing key) picks GOOG as canonical — GOOGL is the row
    whose issuer_id VALUE actually changed, so it is the one with a receipt."""
    row = issuer_migrations.loc[issuer_migrations["security_id"] == GOOGL_ID]
    assert len(row) == 1, "GOOGL must carry exactly one migration receipt row"
    r = row.iloc[0]
    assert r["old_issuer_id"] == "ISS:US-XNAS-GOOGL"
    assert r["new_issuer_id"] == CANONICAL_GOOG_ISSUER
    assert r["reason"] == BUILD.ERA_ISSUER_CORRECTION
    assert r["evidence_cik"] == "0001652044"
    # GOOG itself never moved (it already WAS its own canonical value) — no receipt row.
    assert issuer_migrations.loc[issuer_migrations["security_id"] == GOOG_ID].empty
    assert not issuer_migrations.empty, "issuer_migrations.parquet must be non-empty"


def test_brk_b_resolves_via_dash_normalization_as_a_single_member_group(
    master: pd.DataFrame,
) -> None:
    rows = master.set_index("security_id")
    row = rows.loc["SEC:US-XNYS-BRK.B"]
    assert row["issuer_state"] == "RESOLVED"
    assert row["issuer_cik"] == "0001067983"
    assert row["issuer_id"] == "ISS:US-XNYS-BRK.B", "single-member group keeps its own id"
    # BRK.A is not in this master — no fabricated second security (spec §11).
    assert "SEC:US-XNYS-BRK.A" not in rows.index


def test_gold_is_deferred_and_excluded_from_grouping(master: pd.DataFrame) -> None:
    """GOLD's committed issuer_id predates this era and is RETAINED, unevidenced —
    never repointed by CIK, because the current 'GOLD' ticker's registrant (per the
    live CIK map) is Gold.com, not the master's Barrick-era GOLD security (spec §9
    EQR/VMRK note; the same reuse defect motivates the exception)."""
    row = master.set_index("inception_code").loc["GOLD"]
    assert row["issuer_state"] == "DEFERRED_IDENTITY_EXCEPTION"
    assert row["issuer_id"] == "ISS:US-XNYS-GOLD", "legacy value retained, never cleared"
    assert row["issuer_cik"] is None or pd.isna(row["issuer_cik"])


def test_ibit_resolves_to_the_trusts_own_cik(master: pd.DataFrame) -> None:
    row = master.set_index("inception_code").loc["IBIT"]
    assert row["issuer_state"] == "RESOLVED"
    assert row["issuer_cik"] == "0001980994"


def test_no_issuer_evidence_rows_retain_their_legacy_value(master: pd.DataFrame) -> None:
    """AEP/CTRA/TPH (measured misses) and FISV (current symbol FI misses the map) —
    spec §11: legacy issuer_id retained, aggregation-forbidden, self-heals later."""
    rows = master.set_index("inception_code")
    for code in ("AEP", "CTRA", "TPH", "FISV"):
        row = rows.loc[code]
        assert row["issuer_state"] == "NO_ISSUER_EVIDENCE", code
        assert row["issuer_id"] == f"ISS:{row['listing_key']}", code
        assert row["issuer_cik"] is None or pd.isna(row["issuer_cik"]), code


def test_rddt_enters_resolved_from_current_seeds(master: pd.DataFrame) -> None:
    """The staleness heal (spec §9/§11): RDDT was the RED case on main; this master's
    regeneration is the lawful fix, and it arrives already RESOLVED."""
    row = master.set_index("inception_code").loc["RDDT"]
    assert row["issuer_state"] == "RESOLVED"
    assert row["issuer_id"] == "ISS:US-XNYS-RDDT"


def test_issuer_master_has_one_row_per_distinct_issuer_id(
    master: pd.DataFrame, issuer_master: pd.DataFrame,
) -> None:
    assert issuer_master["issuer_id"].is_unique
    assert set(issuer_master["issuer_id"]) == set(master["issuer_id"].dropna())
    row = issuer_master.set_index("issuer_id").loc[CANONICAL_GOOG_ISSUER]
    assert row["n_securities"] == 2
    assert row["cik"] == "0001652044"
    assert row["evidence_source"] == "sec_company_tickers"
    assert row["era"] == BUILD.ERA_ISSUER_CORRECTION


def test_issuer_migrations_never_touches_security_id_or_listing_key(
    master: pd.DataFrame, issuer_migrations: pd.DataFrame,
) -> None:
    """Mutation control (8): a migration row is about the issuer_id column only."""
    by_sec = master.set_index("security_id")
    for _, row in issuer_migrations.iterrows():
        assert row["security_id"] in by_sec.index
        assert by_sec.loc[row["security_id"], "listing_key"] == row["listing_key"]
        assert row["old_issuer_id"] != row["new_issuer_id"]


def test_the_issuer_axis_is_registered_in_the_dataset_registry() -> None:
    declared = load_registry().get("reference.security_master").schema
    for column in ("issuer_state", "issuer_cik", "issuer_evidence_snapshot"):
        assert column in declared, column
    assert declared["issuer_id"]["nullable"] is True
    assert load_registry().get("reference.issuer_master").status is DatasetStatus.PRODUCED
    assert load_registry().get("reference.issuer_migrations").status is DatasetStatus.PRODUCED


# ── V4-D2B1 FIX 7 (m1) — a ticker seen with 2+ distinct CIKs is AMBIGUOUS, never
# a silent first-wins resolution ─────────────────────────────────────────────────
def test_load_cik_map_removes_a_ticker_seen_with_two_distinct_ciks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ticker appearing twice with DIFFERENT CIKs on the same snapshot must be
    dropped from ``mapping`` entirely (never a silent first-wins pick) and named in
    the returned ``ambiguous_tickers`` set instead."""
    cik_map_dir = tmp_path / "cik_map"
    cik_map_dir.mkdir()
    pd.DataFrame([
        {"ticker": "DUP", "cik": 1, "title": "Company One"},
        {"ticker": "DUP", "cik": 2, "title": "Company Two"},
        {"ticker": "CLEAN", "cik": 3, "title": "Company Three"},
    ]).to_parquet(cik_map_dir / "2026-08-19.parquet", index=False)
    monkeypatch.setattr(BUILD, "CIK_MAP_DIR", cik_map_dir)

    mapping, snapshot_date, path, ambiguous = BUILD.load_cik_map()
    assert snapshot_date == "2026-08-19"
    assert "DUP" not in mapping, "an ambiguous ticker must never resolve first-wins"
    assert ambiguous == frozenset({"DUP"})
    assert mapping["CLEAN"] == ("0000000003", "Company Three")


def test_a_repeated_identical_cik_is_not_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ticker repeated with the SAME CIK (e.g. a duplicated source row) is not an
    ambiguity — only a DIFFERING second CIK removes the ticker."""
    cik_map_dir = tmp_path / "cik_map"
    cik_map_dir.mkdir()
    pd.DataFrame([
        {"ticker": "SAME", "cik": 5, "title": "Company Five"},
        {"ticker": "SAME", "cik": 5, "title": "Company Five"},
    ]).to_parquet(cik_map_dir / "2026-08-19.parquet", index=False)
    monkeypatch.setattr(BUILD, "CIK_MAP_DIR", cik_map_dir)

    mapping, _snap, _path, ambiguous = BUILD.load_cik_map()
    assert ambiguous == frozenset()
    assert mapping["SAME"] == ("0000000005", "Company Five")


def test_an_ambiguous_ticker_types_its_security_ambiguous_not_a_silent_miss() -> None:
    """FIX 7: a security whose evidence join key hits the ambiguous set must be typed
    ``AMBIGUOUS`` (spec §3, reserved/fail-closed) — never silently read as a plain
    evidence-miss (``NO_ISSUER_EVIDENCE``), which would misreport "no evidence" for a
    ticker that actually has TOO MUCH, conflicting evidence."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNAS-DUP", "issuer_id": "ISS:US-XNAS-DUP",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-DUP", "mic": "XNAS", "inception_code": "DUP"},
    ]
    # DUP is intentionally ABSENT from cik_map (load_cik_map would have removed it) —
    # the ambiguous_tickers set is the ONLY signal apply_issuer_correction sees.
    out_rows, migrations = BUILD.apply_issuer_correction(
        rows, {}, "2026-08-19", now, ambiguous_tickers=frozenset({"DUP"}))
    assert out_rows[0]["issuer_state"] == "AMBIGUOUS"
    assert out_rows[0]["issuer_id"] == "ISS:US-XNAS-DUP", "legacy value retained, never cleared"
    assert out_rows[0]["issuer_cik"] is None
    assert migrations == []

    # Idempotency: the same (still-ambiguous) inputs re-produce the same outcome.
    again_rows, again_migrations = BUILD.apply_issuer_correction(
        out_rows, {}, "2026-08-19", now, ambiguous_tickers=frozenset({"DUP"}))
    assert again_rows == out_rows
    assert again_migrations == []

    # N1 heal: AMBIGUOUS is a source-snapshot artifact, NOT a terminal state — the
    # very next CLEAN weekly map (ticker carries exactly one CIK, ambiguous set
    # empty) must settle the row.  Evidence agreeing with the retained legacy value
    # heals to RESOLVED; RESOLVED/DEFERRED/EVIDENCE_CONFLICT stay mint-once.
    healed_rows, healed_migrations = BUILD.apply_issuer_correction(
        again_rows, {"DUP": ("0001234567", "DUP CORP")}, "2026-08-26", now,
        ambiguous_tickers=frozenset())
    assert healed_rows[0]["issuer_state"] == "RESOLVED"
    assert healed_rows[0]["issuer_id"] == "ISS:US-XNAS-DUP", "value stable across the heal"
    assert healed_rows[0]["issuer_cik"] == "0001234567"
    assert healed_migrations == []


# ── V4-D2B1: pure functions over fixtures ───────────────────────────────────────
def test_current_symbol_walks_the_same_chain_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    """The forward mirror of :func:`BUILD._inception_code` — same rename records,
    opposite direction, landing on the security's own current symbol."""
    assert BUILD._current_symbol("MMC") == "MRSH"
    assert BUILD._current_symbol("SATS") == "ECHO"
    # The vendor-lag case: this repo's OWN rename record says the current symbol is
    # FI even though Yahoo still serves FISV — §1 asks for THIS repo's record, not
    # whatever a lagging vendor currently serves.
    assert BUILD._current_symbol("FISV") == "FI"
    assert BUILD._current_symbol("AAPL") == "AAPL"
    assert BUILD._evidence_join_key("BRK.B") == "BRK-B"


def test_pick_canonical_member_applies_rule_4_on_a_tie(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rules 1-2 have no in-repo data source and can never fire (spec §2); only rule 3
    (lowest MIC) then rule 4 (lowest full listing key, the D2B1 extension) ever do."""
    goog = {"listing_key": "US-XNAS-GOOG", "mic": "XNAS"}
    googl = {"listing_key": "US-XNAS-GOOGL", "mic": "XNAS"}
    assert BUILD._pick_canonical_member([goog, googl]) is goog
    assert BUILD._pick_canonical_member([googl, goog]) is goog
    assert BUILD._pick_canonical_member([goog]) is goog
    # A lower MIC beats a lexicographically-lower key on a higher MIC.
    nyse_a = {"listing_key": "US-XNYS-AAA", "mic": "XNYS"}
    nasdaq_z = {"listing_key": "US-XNAS-ZZZ", "mic": "XNAS"}
    assert BUILD._pick_canonical_member([nyse_a, nasdaq_z]) is nasdaq_z


def test_apply_issuer_correction_groups_by_cik_and_is_idempotent() -> None:
    """Pure-function proof over a hand-built fixture — the whole era in miniature.

    ``allowlist`` is passed explicitly (FIX 5 / M3): this test's synthetic CIK
    "0000000001" is not in the real config/issuer_group_allowlist.yml, and this test
    is about grouping mechanics/idempotency, not the allowlist gate — that gate has
    its own dedicated tests below.
    """
    now = "2026-08-19T00:00:00"
    allowlist = frozenset({"0000000001"})
    rows = [
        {"security_id": "SEC:US-XNAS-AAA", "issuer_id": "ISS:US-XNAS-AAA",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-AAA", "mic": "XNAS", "inception_code": "AAA"},
        {"security_id": "SEC:US-XNAS-BBB", "issuer_id": "ISS:US-XNAS-BBB",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-BBB", "mic": "XNAS", "inception_code": "BBB"},
        {"security_id": "SEC:US-XNAS-CCC", "issuer_id": "ISS:US-XNAS-CCC",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-CCC", "mic": "XNAS", "inception_code": "CCC"},
    ]
    cik_map = {"AAA": ("0000000001", "Test Co A"), "BBB": ("0000000001", "Test Co A")}
    # CCC has no evidence at all — NO_ISSUER_EVIDENCE, legacy value retained.

    out_rows, migrations = BUILD.apply_issuer_correction(
        rows, cik_map, "2026-08-15", now, allowlist=allowlist)
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNAS-AAA"]["issuer_state"] == "RESOLVED"
    assert by_id["SEC:US-XNAS-BBB"]["issuer_state"] == "RESOLVED"
    assert by_id["SEC:US-XNAS-AAA"]["issuer_id"] == by_id["SEC:US-XNAS-BBB"]["issuer_id"]
    assert by_id["SEC:US-XNAS-CCC"]["issuer_state"] == "NO_ISSUER_EVIDENCE"
    assert by_id["SEC:US-XNAS-CCC"]["issuer_id"] == "ISS:US-XNAS-CCC", "legacy value retained"
    # None of these three "existed before" (no _existed_before marker) — a brand-new
    # mint's first assignment is not a migration.
    assert migrations == []

    # Idempotent: a second pass over the SAME (now-stamped) rows is a byte-stable
    # no-op — every row's issuer_state is already set, so `pending` is empty.
    again_rows, again_migrations = BUILD.apply_issuer_correction(
        out_rows, cik_map, "2026-08-15", now, allowlist=allowlist)
    assert again_rows == out_rows
    assert again_migrations == []


def test_apply_issuer_correction_records_a_migration_only_for_a_preexisting_row() -> None:
    """Mutation control (9) reversed as a positive assertion: a genuine repoint of an
    _existed_before row DOES get a migration row; a brand-new mint sharing that same
    CIK does NOT (spec §3: "one row per security whose issuer_id VALUE changed")."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNAS-OLD", "issuer_id": "ISS:US-XNAS-OLD",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-OLD", "mic": "XNAS", "inception_code": "OLD",
         "_existed_before": True},
        {"security_id": "SEC:US-XNAS-NEW", "issuer_id": None,
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-NEW", "mic": "XNAS", "inception_code": "NEW"},
    ]
    cik_map = {"OLD": ("0000000009", "Shared Co"), "NEW": ("0000000009", "Shared Co")}
    # A new 2-member group — needs an explicit allowlist (FIX 5), unrelated to what
    # this test actually proves (migration-receipt mechanics).
    out_rows, migrations = BUILD.apply_issuer_correction(
        rows, cik_map, "2026-08-15", now, allowlist=frozenset({"0000000009"}))
    assert len(migrations) == 1
    assert migrations[0]["security_id"] == "SEC:US-XNAS-OLD"
    assert migrations[0]["old_issuer_id"] == "ISS:US-XNAS-OLD"


def test_a_later_pending_security_adopts_an_already_resolved_groups_issuer_id() -> None:
    """Mint-once for issuers (spec §2): membership growing never re-derives the
    canonical id — it is ADOPTED from whichever member the group already settled on."""
    now = "2026-08-19T00:00:00"
    already_resolved = {
        "security_id": "SEC:US-XNAS-FIRST", "issuer_id": "ISS:US-XNAS-FIRST",
        "issuer_state": "RESOLVED", "issuer_cik": "0000000042",
        "issuer_evidence_snapshot": "2026-08-01",
        "listing_key": "US-XNAS-FIRST", "mic": "XNAS", "inception_code": "FIRST",
    }
    new_member = {
        "security_id": "SEC:US-XNAS-AAAAA", "issuer_id": None, "issuer_state": None,
        "issuer_cik": None, "issuer_evidence_snapshot": None,
        "listing_key": "US-XNAS-AAAAA", "mic": "XNAS", "inception_code": "AAAAA",
    }
    cik_map = {"AAAAA": ("0000000042", "Shared Co")}
    out_rows, _migrations = BUILD.apply_issuer_correction(
        [already_resolved, new_member], cik_map, "2026-08-19", now)
    by_id = {r["security_id"]: r for r in out_rows}
    # AAAAA sorts before FIRST, so a fresh tie-break would have picked AAAAA — but the
    # group already had a RESOLVED canonical id, which must be ADOPTED, not re-derived.
    assert by_id["SEC:US-XNAS-AAAAA"]["issuer_id"] == "ISS:US-XNAS-FIRST"


def test_a_brand_new_evidence_less_row_gets_no_fallback_mint() -> None:
    """Mutation control (3): the abolished per-listing fallback must NOT come back —
    a brand-new row (no prior stored issuer_id) with no CIK evidence stays NULL,
    never a freshly minted ``ISS:<own listing key>``."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNAS-NOEV", "issuer_id": None,
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-NOEV", "mic": "XNAS", "inception_code": "NOEV"},
    ]
    out_rows, migrations = BUILD.apply_issuer_correction(rows, {}, "2026-08-19", now)
    assert out_rows[0]["issuer_state"] == "NO_ISSUER_EVIDENCE"
    assert out_rows[0]["issuer_id"] is None, "no fallback mint for an evidence-less new row"
    assert migrations == []


def test_two_different_ciks_never_merge_into_one_group() -> None:
    """Mutation control (5): distinct CIK evidence must never force-merge — the
    group key IS the CIK string, with no fuzzy or partial matching anywhere."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNAS-AAA", "issuer_id": "ISS:US-XNAS-AAA",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-AAA", "mic": "XNAS", "inception_code": "AAA"},
        {"security_id": "SEC:US-XNAS-BBB", "issuer_id": "ISS:US-XNAS-BBB",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-BBB", "mic": "XNAS", "inception_code": "BBB"},
    ]
    cik_map = {"AAA": ("0000000001", "Company One"), "BBB": ("0000000002", "Company Two")}
    out_rows, migrations = BUILD.apply_issuer_correction(rows, cik_map, "2026-08-19", now)
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNAS-AAA"]["issuer_id"] == "ISS:US-XNAS-AAA"
    assert by_id["SEC:US-XNAS-BBB"]["issuer_id"] == "ISS:US-XNAS-BBB"
    assert by_id["SEC:US-XNAS-AAA"]["issuer_id"] != by_id["SEC:US-XNAS-BBB"]["issuer_id"]
    assert migrations == [], "single-member groups that already held their own id don't migrate"


def test_deferred_exception_rows_are_excluded_from_grouping_even_with_matching_cik() -> None:
    """Mutation control: an exception key must never join a CIK group, even when its
    join-key symbol happens to collide with evidence for a real group."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNYS-GOLD", "issuer_id": "ISS:US-XNYS-GOLD",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNYS-GOLD", "mic": "XNYS", "inception_code": "GOLD"},
    ]
    cik_map = {"GOLD": ("0000000099", "Gold.com, Inc.")}
    out_rows, migrations = BUILD.apply_issuer_correction(rows, cik_map, "2026-08-19", now)
    assert out_rows[0]["issuer_state"] == "DEFERRED_IDENTITY_EXCEPTION"
    assert out_rows[0]["issuer_id"] == "ISS:US-XNYS-GOLD", "never repointed to Gold.com's CIK"
    assert migrations == []


# ── V4-D2B1 FIX 1 (B1/M5) — NO_ISSUER_EVIDENCE rows are RE-EXAMINED every build ──
def _no_issuer_evidence_row(security_id: str, code: str, legacy_issuer_id: str | None,
                            *, mic: str = "XNAS") -> dict:
    listing_key = f"US-{mic}-{code}"
    return {
        "security_id": security_id, "issuer_id": legacy_issuer_id,
        "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
        "issuer_evidence_snapshot": None, "listing_key": listing_key, "mic": mic,
        "inception_code": code,
    }


def test_a_later_map_carrying_a_previously_unevidenced_ticker_heals_it_to_resolved() -> None:
    """B1 probe (a): a row stamped NO_ISSUER_EVIDENCE on a prior run is RE-EXAMINED
    when the NEXT map finally covers its ticker, and heals to RESOLVED with the SAME
    issuer_id value (own listing key — no other security shares the CIK)."""
    now = "2026-08-19T00:00:00"
    rows = [_no_issuer_evidence_row("SEC:US-XNAS-AEP", "AEP", "ISS:US-XNAS-AEP")]
    cik_map = {"AEP": ("0000004904", "AMERICAN ELECTRIC POWER CO INC")}
    out_rows, migrations = BUILD.apply_issuer_correction(rows, cik_map, "2026-08-25", now)
    row = out_rows[0]
    assert row["issuer_state"] == "RESOLVED"
    assert row["issuer_id"] == "ISS:US-XNAS-AEP", "SAME value — no other master row shares the CIK"
    assert row["issuer_cik"] == "0000004904"
    assert row["issuer_evidence_snapshot"] == "2026-08-25"
    # AEP was already NO_ISSUER_EVIDENCE (not _existed_before-marked here, but the
    # value did not change) — no migration row either way.
    assert migrations == []

    # Idempotent: re-running with the SAME map is byte-stable — RESOLVED is mint-once.
    again_rows, again_migrations = BUILD.apply_issuer_correction(out_rows, cik_map,
                                                                  "2026-08-25", now)
    assert again_rows == out_rows
    assert again_migrations == []


def test_a_later_map_grouping_a_legacy_row_into_another_group_yields_evidence_conflict() -> None:
    """B1 probe (b): fresh evidence groups a re-examined row with a DIFFERENT,
    already-committed canonical issuer than the row's own legacy value — the value
    must NOT be rewritten (frozen contract §2: recorded, never executed)."""
    now = "2026-08-19T00:00:00"
    rows = [
        # Already committed RESOLVED — the established canonical group.
        {"security_id": "SEC:US-XNAS-FIRST", "issuer_id": "ISS:US-XNAS-FIRST",
         "issuer_state": "RESOLVED", "issuer_cik": "0000000042",
         "issuer_evidence_snapshot": "2026-08-01",
         "listing_key": "US-XNAS-FIRST", "mic": "XNAS", "inception_code": "FIRST"},
        # A legacy NO_ISSUER_EVIDENCE row whose OWN value disagrees with that group.
        _no_issuer_evidence_row("SEC:US-XNAS-LEGACY", "LEGACY", "ISS:US-XNAS-LEGACY"),
    ]
    cik_map = {"LEGACY": ("0000000042", "Shared Co")}
    out_rows, migrations = BUILD.apply_issuer_correction(rows, cik_map, "2026-08-25", now)
    by_id = {r["security_id"]: r for r in out_rows}
    legacy = by_id["SEC:US-XNAS-LEGACY"]
    assert legacy["issuer_state"] == "EVIDENCE_CONFLICT"
    assert legacy["issuer_id"] == "ISS:US-XNAS-LEGACY", "value never rewritten"
    assert legacy["issuer_cik"] == "0000000042", "the DISAGREEING evidence CIK is stamped"
    assert legacy["issuer_evidence_snapshot"] == "2026-08-25"
    assert by_id["SEC:US-XNAS-FIRST"]["issuer_id"] == "ISS:US-XNAS-FIRST", "unaffected"
    assert migrations == []

    # Mint-once for EVIDENCE_CONFLICT too: a second pass never re-examines it.
    again_rows, again_migrations = BUILD.apply_issuer_correction(out_rows, cik_map,
                                                                  "2026-08-25", now)
    assert again_rows == out_rows
    assert again_migrations == []


def test_a_null_issuer_new_row_heals_to_a_minted_value_on_re_examination() -> None:
    """B1 probe (a) variant: a brand-new post-era row (issuer_id NULL, never minted)
    that missed evidence on its own run heals on a LATER map — adopting an existing
    committed group's canonical id when the CIK matches one."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNAS-ESTABLISHED", "issuer_id": "ISS:US-XNAS-ESTABLISHED",
         "issuer_state": "RESOLVED", "issuer_cik": "0000000077",
         "issuer_evidence_snapshot": "2026-08-01",
         "listing_key": "US-XNAS-ESTABLISHED", "mic": "XNAS", "inception_code": "ESTABLISHED"},
        _no_issuer_evidence_row("SEC:US-XNAS-NEWMISS", "NEWMISS", None),
    ]
    cik_map = {"NEWMISS": ("0000000077", "Shared Co")}
    out_rows, migrations = BUILD.apply_issuer_correction(rows, cik_map, "2026-08-25", now)
    by_id = {r["security_id"]: r for r in out_rows}
    healed = by_id["SEC:US-XNAS-NEWMISS"]
    assert healed["issuer_state"] == "RESOLVED"
    assert healed["issuer_id"] == "ISS:US-XNAS-ESTABLISHED", "adopts the existing group's id"
    # No prior stored value (issuer_id was None) — not a migration.
    assert migrations == []


def test_apply_issuer_correction_is_byte_stable_over_a_mixed_pending_set() -> None:
    """Idempotency across the FULL FIX 1 surface in one pass: an unstamped row, a
    healed NO_ISSUER_EVIDENCE row, a still-missing NO_ISSUER_EVIDENCE row, and an
    EVIDENCE_CONFLICT row must ALL be stable on a second run over the same map."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNAS-FIRST", "issuer_id": "ISS:US-XNAS-FIRST",
         "issuer_state": "RESOLVED", "issuer_cik": "0000000042",
         "issuer_evidence_snapshot": "2026-08-01",
         "listing_key": "US-XNAS-FIRST", "mic": "XNAS", "inception_code": "FIRST"},
        _no_issuer_evidence_row("SEC:US-XNAS-HEALS", "HEALS", "ISS:US-XNAS-HEALS"),
        _no_issuer_evidence_row("SEC:US-XNAS-STILLMISS", "STILLMISS", "ISS:US-XNAS-STILLMISS"),
        _no_issuer_evidence_row("SEC:US-XNAS-CONFLICTS", "CONFLICTS", "ISS:US-XNAS-CONFLICTS"),
    ]
    cik_map = {
        "HEALS": ("0000000099", "Solo Co"),
        "CONFLICTS": ("0000000042", "Shared Co"),
        # STILLMISS carries no entry — evidence-miss.
    }
    out_rows, _m = BUILD.apply_issuer_correction(rows, cik_map, "2026-08-25", now)
    again_rows, again_migrations = BUILD.apply_issuer_correction(out_rows, cik_map,
                                                                  "2026-08-25", now)
    assert again_rows == out_rows
    assert again_migrations == []


# ── V4-D2B1 FIX 5 (M3, latent) — issuer group allowlist gate ─────────────────────
def test_unallowlisted_cik_never_forms_a_new_multi_member_group(capsys) -> None:
    """A shared CIK is necessary but not sufficient evidence to group NEW securities
    for the first time (an SEC registrant can be a sponsor/trust for an ETP) —
    without a ratified config/issuer_group_allowlist.yml row, the era must refuse to
    group and record EVIDENCE_CONFLICT instead, never silently collapsing."""
    now = "2026-08-19T00:00:00"
    rows = [
        {"security_id": "SEC:US-XNAS-QQA", "issuer_id": "ISS:US-XNAS-QQA",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-QQA", "mic": "XNAS", "inception_code": "QQA"},
        {"security_id": "SEC:US-XNAS-QQB", "issuer_id": "ISS:US-XNAS-QQB",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-QQB", "mic": "XNAS", "inception_code": "QQB"},
    ]
    cik_map = {"QQA": ("0009999999", "Sponsor Trust"), "QQB": ("0009999999", "Sponsor Trust")}
    # allowlist=frozenset() (explicit, empty) — proves the refusal regardless of what
    # the real committed config/issuer_group_allowlist.yml happens to carry.
    out_rows, migrations = BUILD.apply_issuer_correction(
        rows, cik_map, "2026-08-19", now, allowlist=frozenset())
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNAS-QQA"]["issuer_state"] == "EVIDENCE_CONFLICT"
    assert by_id["SEC:US-XNAS-QQB"]["issuer_state"] == "EVIDENCE_CONFLICT"
    assert by_id["SEC:US-XNAS-QQA"]["issuer_id"] == "ISS:US-XNAS-QQA", "value never rewritten"
    assert by_id["SEC:US-XNAS-QQB"]["issuer_id"] == "ISS:US-XNAS-QQB"
    assert by_id["SEC:US-XNAS-QQA"]["issuer_cik"] == "0009999999"
    assert migrations == []
    out = capsys.readouterr().out
    warning_lines = [line for line in out.splitlines() if line.startswith("::warning")]
    assert warning_lines, out
    assert "0009999999" in warning_lines[0]


def test_allowlisted_cik_still_forms_a_new_multi_member_group() -> None:
    """The gate must not block a CIK that IS ratified — proven against a REAL
    allowlisted CIK (GOOG/GOOGL's, from the committed config/issuer_group_allowlist.yml,
    loaded via the default ``allowlist=None`` path) with two brand-new fixture rows."""
    now = "2026-08-19T00:00:00"
    real_goog_cik = "0001652044"
    assert real_goog_cik in BUILD._load_issuer_group_allowlist(), (
        "this test needs the real committed allowlist to carry the GOOG/GOOGL CIK"
    )
    rows = [
        {"security_id": "SEC:US-XNAS-ZZA", "issuer_id": "ISS:US-XNAS-ZZA",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-ZZA", "mic": "XNAS", "inception_code": "ZZA"},
        {"security_id": "SEC:US-XNAS-ZZB", "issuer_id": "ISS:US-XNAS-ZZB",
         "issuer_state": None, "issuer_cik": None, "issuer_evidence_snapshot": None,
         "listing_key": "US-XNAS-ZZB", "mic": "XNAS", "inception_code": "ZZB"},
    ]
    cik_map = {"ZZA": (real_goog_cik, "Alphabet Inc."), "ZZB": (real_goog_cik, "Alphabet Inc.")}
    out_rows, migrations = BUILD.apply_issuer_correction(rows, cik_map, "2026-08-19", now)
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNAS-ZZA"]["issuer_state"] == "RESOLVED"
    assert by_id["SEC:US-XNAS-ZZB"]["issuer_state"] == "RESOLVED"
    assert by_id["SEC:US-XNAS-ZZA"]["issuer_id"] == by_id["SEC:US-XNAS-ZZB"]["issuer_id"]


def test_allowlist_never_gates_adoption_of_an_already_established_group() -> None:
    """A CIK NOT in the allowlist must still allow a NEW member to ADOPT an
    ALREADY-established group (mint-once, spec §2) — the review happened when that
    group first formed; only forming a BRAND-NEW multi-member group is gated."""
    now = "2026-08-19T00:00:00"
    already_resolved = {
        "security_id": "SEC:US-XNAS-ANCHOR", "issuer_id": "ISS:US-XNAS-ANCHOR",
        "issuer_state": "RESOLVED", "issuer_cik": "0009999998",
        "issuer_evidence_snapshot": "2026-08-01",
        "listing_key": "US-XNAS-ANCHOR", "mic": "XNAS", "inception_code": "ANCHOR",
    }
    new_member = {
        "security_id": "SEC:US-XNAS-JOINER", "issuer_id": None, "issuer_state": None,
        "issuer_cik": None, "issuer_evidence_snapshot": None,
        "listing_key": "US-XNAS-JOINER", "mic": "XNAS", "inception_code": "JOINER",
    }
    cik_map = {"JOINER": ("0009999998", "Anchor Co")}
    out_rows, _m = BUILD.apply_issuer_correction(
        [already_resolved, new_member], cik_map, "2026-08-19", now, allowlist=frozenset())
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNAS-JOINER"]["issuer_state"] == "RESOLVED"
    assert by_id["SEC:US-XNAS-JOINER"]["issuer_id"] == "ISS:US-XNAS-ANCHOR"


# ── V4-D2B1-R1: VMRK duplicate-mint supersession + pending-transition fence ────
# research/prophet_v4/d2/D2B1_R1_FROZEN_CONTRACT_2026-08-20.md — the EQR->VMRK rename
# (SEC EDGAR CIK 0000906107, 8-K accession 0001140361-26-033377, Item 5.03) produced a
# duplicate mint (SEC:US-XNYS-VMRK) before this builder modelled the rename, because
# mint_master_rows keyed the mint join on listing_key only.  This section pins §7's
# nine hostile cases; §9's ten mutation controls are demonstrated by hand (apply,
# confirm the named test here goes red, revert) and receipted in the PR body/packet —
# they are not shipped as separate always-on tests.
EQR_ID = "SEC:US-XNYS-EQR"
VMRK_RENAME = date(2026, 8, 18)


def _lk(country: str, mic: str, code: str) -> "object":
    from lib.dataos.identity import ListingKey
    return ListingKey(country, mic, code)


# H2 — with the RenameEvent (the committed, real state): VMRK resolves to the
# existing EQR row; the membership-sourced EQR seed and the constituents-sourced VMRK
# seed dedup to ONE master row, no mint.
def test_h2_eqr_and_vmrk_dedup_to_one_master_row(master: pd.DataFrame) -> None:
    assert BUILD._current_symbol("EQR") == "VMRK"
    assert BUILD._inception_code("VMRK", None) == "EQR"
    eqr_rows = master[master["inception_code"] == "EQR"]
    assert len(eqr_rows) == 1
    assert eqr_rows.iloc[0]["security_id"] == EQR_ID
    assert eqr_rows.iloc[0]["listing_key"] == "US-XNYS-EQR"
    # No SECOND active row for VMRK — the only VMRK row is the superseded tombstone.
    vmrk_rows = master[master["inception_code"] == "VMRK"]
    assert len(vmrk_rows) == 1
    assert vmrk_rows.iloc[0]["security_state"] == "SUPERSEDED_DUPLICATE_MINT"
    assert vmrk_rows.iloc[0]["superseded_by"] == EQR_ID


def test_h9_705_rows_tombstone_byte_frozen_except_two_columns(master: pd.DataFrame) -> None:
    """705 pre-D2B2-US rows PLUS the D2B2-US GMI admission wave's ~508 new active
    rows; the tombstone differs from a plain active row's shape only in the two new
    columns — every OTHER column keeps the value it was minted with.  V4-D2B2-CN-HK
    added a separate CN/HK population to the same table (a DIFFERENT grain slice,
    `country` != "US"); V4-D2B2-US (this contract) admits ~508 more US rows on top
    of the 705 this test was originally written to pin — the byte-freeze assertions
    below still pin the SAME pre-existing VMRK tombstone row untouched by either
    wave, only the total-US-row-count changes."""
    assert len(master[master["country"] == "US"]) == 705 + 508
    tomb = master[master["security_id"] == "SEC:US-XNYS-VMRK"].iloc[0]
    assert tomb["issuer_state"] == "NO_ISSUER_EVIDENCE"
    assert pd.isna(tomb["issuer_id"])
    assert pd.isna(tomb["issuer_cik"])
    assert tomb["listing_key"] == "US-XNYS-VMRK"
    assert tomb["country"] == "US"
    assert tomb["mic"] == "XNYS"
    assert tomb["inception_code"] == "VMRK"


def test_the_dedicated_dataset_carries_exactly_one_correction_row() -> None:
    migrations = pd.read_parquet(ROOT / "data" / "reference" / "security_migrations.parquet")
    assert len(migrations) == 1
    row = migrations.iloc[0]
    assert row["security_id"] == "SEC:US-XNYS-VMRK"
    assert row["superseded_by"] == EQR_ID
    assert row["reason"] == "security_supersession_duplicate_mint_v1"
    assert "0001140361-26-033377" in row["evidence"]


def test_the_security_migrations_schema_matches_the_registry() -> None:
    declared = list(load_registry().get("reference.security_migrations").schema)
    emitted = list(pd.read_parquet(
        ROOT / "data" / "reference" / "security_migrations.parquet").columns)
    assert emitted == declared


def test_receipt_carries_the_security_axis_block(receipt: dict, master: pd.DataFrame) -> None:
    """``security.state_counts`` is a WHOLE-TABLE count (same convention as
    ``issuer.state_counts``) — V4-D2B2-CN-HK added ~1,100 active CN/HK rows to the
    same table, so ACTIVE is asserted against the committed master's own row count
    rather than the pre-D2B2 US-only magic number 704 (which
    ``test_h9_705_rows_tombstone_byte_frozen_except_two_columns`` still pins,
    scoped to ``country == "US"``)."""
    sec = receipt["security"]
    assert sec["era"] == "security_supersession_duplicate_mint_v1"
    assert sec["state_counts"]["ACTIVE"] == int((master["security_state"].isna()).sum())
    assert sec["state_counts"]["SUPERSEDED_DUPLICATE_MINT"] == 1
    assert receipt["pending_transition_refusals"] == []
    # AMENDMENT ruling 3 (M1): listing_continuity is no longer unconditionally empty
    # post-repair — the fence-scoped (plain-string) half IS empty except for a WBS
    # gap (VERIFIED pre-existing and unrelated to D2B2-US: an UNMODIFIED rebuild at
    # this same pin already reports WBS unaccounted — a symbol-directory/committed-
    # master staleness gap between the WBS row's own bake and the current
    # snapshot, not a regression this contract introduced). The GOLD row (a
    # registered DISCLOSED_IDENTITY_EXCEPTIONS entry, excluded from the fence
    # itself) is a typed, EXPLAINED entry — never silently dropped.
    assert receipt["listing_continuity"] == [
        "WBS", {"code": "GOLD", "explained": "identity_exception"},
    ]
    assert receipt["resurrection_refusals"] == []
    # AMENDMENT ruling 4 (M3) / ruling 6 (M5) — the two new disclosure blocks are
    # present and empty in the healthy post-repair state (no unregistered rename
    # duplicate exists, and no alias row needed pruning this run).
    assert receipt["unregistered_rename_duplicates"] == []
    assert receipt["vendor_alias_prunes"] == []


# H1 — race replay WITHOUT the RenameEvent: the fence refuses the VMRK mint.
def test_h1_race_replay_without_the_rename_event_the_fence_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", ())
    existing = [{
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "country": "US", "mic": "XNYS", "inception_code": "EQR",
        "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
        "security_state": None, "superseded_by": None,
    }]
    # EQR vanished from this build's seeds (the snapshot flip) — only VMRK resolves.
    resolutions = [
        BUILD.Resolution("VMRK", _lk("US", "XNYS", "VMRK"), "VMRK", "VMRK",
                         "fixture", date(2026, 8, 20)),
    ]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, existing, "2026-08-20T00:00:00", cik_map={},
    )
    assert lost and lost[0]["security_id"] == EQR_ID
    assert len(pending) == 1
    assert pending[0]["symbol"] == "VMRK"
    assert pending[0]["listing_key"] == "US-XNYS-VMRK"
    assert pending[0]["lost_rows"] == [EQR_ID]
    assert "VMRK" not in ids
    assert not any(r["security_id"] == "SEC:US-XNYS-VMRK" for r in rows), (
        "the fence must produce no new security_id"
    )
    assert notes == []


# H7 — a new symbol with its own independent CIK mints normally even while `lost` is
# non-empty (IPOs are not collateral damage of the fence).
def test_h7_independent_cik_evidence_mints_normally_despite_a_nonempty_lost_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", ())
    existing = [{
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "country": "US", "mic": "XNYS", "inception_code": "EQR",
        "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
        "security_state": None, "superseded_by": None,
    }]
    resolutions = [
        # EQR vanished (lost). NEWCO is a genuine new listing with its OWN CIK.
        BUILD.Resolution("NEWCO", _lk("US", "XNAS", "NEWCO"), "NEWCO", "NEWCO",
                         "fixture", date(2026, 8, 20)),
    ]
    cik_map = {"NEWCO": ("0009990001", "New Company Inc.")}
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, existing, "2026-08-20T00:00:00", cik_map=cik_map,
    )
    assert lost and lost[0]["security_id"] == EQR_ID
    assert pending == []
    assert ids["NEWCO"] == "SEC:US-XNAS-NEWCO"
    assert any(r["security_id"] == "SEC:US-XNAS-NEWCO" for r in rows)


def test_h7_a_shared_cik_with_a_lost_row_is_NOT_independent_and_still_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The independence check compares CIKs, not bare presence in the map — a
    candidate whose CIK matches a lost row's own CIK is not independent evidence."""
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", ())
    existing = [{
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "country": "US", "mic": "XNYS", "inception_code": "EQR",
        "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
        "security_state": None, "superseded_by": None,
    }]
    resolutions = [
        BUILD.Resolution("VMRK", _lk("US", "XNYS", "VMRK"), "VMRK", "VMRK",
                         "fixture", date(2026, 8, 20)),
    ]
    cik_map = {"VMRK": ("0000906107", "Vivmark Residential")}  # SAME cik as the lost row
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, existing, "2026-08-20T00:00:00", cik_map=cik_map,
    )
    assert len(pending) == 1, "a shared CIK with the lost row is not independent evidence"


# AMENDMENT ruling 2 (M2) — REPRODUCE-THEN-KILL the reviewer's exact scenario: a
# lost row with a NULL issuer_cik used to be silently dropped from `lost_ciks`
# entirely (`if r.get("issuer_cik")`), so it could never disqualify any candidate —
# a fresh mint with an evidenced CIK sailed through with ZERO refusals even though
# independence from the null-CIK lost row was never actually proven. Fixed:
# independence now requires EVERY fence-scoped lost row to carry a non-null CIK.
def test_m2_a_null_cik_lost_row_fails_closed_never_lets_a_candidate_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", ())
    existing = [{
        # The exact defect class: a lost row with NO evidenced issuer_cik — the
        # reviewer's own reproduction used a resurrection-adjacent NO_ISSUER_EVIDENCE
        # row exactly like this shape.
        "security_id": EQR_ID, "issuer_id": None,
        "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
        "issuer_evidence_snapshot": None, "listing_key": "US-XNYS-EQR",
        "country": "US", "mic": "XNYS", "inception_code": "EQR",
        "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
        "security_state": None, "superseded_by": None,
    }]
    resolutions = [
        # ZZZNEW is a genuine new listing with its OWN evidenced CIK — under the
        # pre-fix code this minted with ZERO refusals (the null lost-CIK vanished
        # from `lost_ciks` and "not in {}" is vacuously true for ANY candidate CIK).
        BUILD.Resolution("ZZZNEW", _lk("US", "XNAS", "ZZZNEW"), "ZZZNEW", "ZZZNEW",
                         "fixture", date(2026, 8, 20)),
    ]
    cik_map = {"ZZZNEW": ("0009990002", "Zzz New Inc.")}
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, existing, "2026-08-20T00:00:00", cik_map=cik_map,
    )
    assert lost and lost[0]["security_id"] == EQR_ID and lost[0]["issuer_cik"] is None
    assert len(pending) == 1, (
        "a null-CIK lost row must fail EVERY candidate closed (independence "
        "unprovable), never let one through — this is the reviewer's own "
        "reproduced defect (0 refusals, ZZZNEW minted)"
    )
    assert "ZZZNEW" not in ids
    assert not any(r["security_id"] == "SEC:US-XNAS-ZZZNEW" for r in rows)


# H8 — a seed rendering a SUPERSEDED listing key never resurrects it.
def test_h8_a_resolution_hitting_a_tombstone_is_a_typed_refusal_not_a_resurrection() -> None:
    existing = [
        {
            "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
            "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
            "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
            "country": "US", "mic": "XNYS", "inception_code": "EQR",
            "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
            "security_state": None, "superseded_by": None,
        },
        {
            "security_id": "SEC:US-XNYS-VMRK", "issuer_id": None,
            "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
            "issuer_evidence_snapshot": None, "listing_key": "US-XNYS-VMRK",
            "country": "US", "mic": "XNYS", "inception_code": "VMRK",
            "effective_at": "2026-08-20T00:00:00", "ingested_at": "2026-08-20T01:30:18",
            "security_state": "SUPERSEDED_DUPLICATE_MINT", "superseded_by": EQR_ID,
        },
    ]
    resolutions = [
        BUILD.Resolution("VMRK2", _lk("US", "XNYS", "VMRK"), "VMRK", "VMRK",
                         "fixture", date(2026, 8, 20)),
    ]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, existing, "2026-08-20T00:00:00", cik_map={},
    )
    assert "VMRK2" not in ids, "never a silent resurrection"
    assert len(refusals) == 1
    assert refusals[0]["security_id"] == "SEC:US-XNYS-VMRK"
    assert refusals[0]["security_state"] == "SUPERSEDED_DUPLICATE_MINT"
    assert refusals[0]["superseded_by"] == EQR_ID
    # And the tombstone itself is carried through untouched — never deleted.
    assert any(r["security_id"] == "SEC:US-XNYS-VMRK" for r in rows)


# ── AMENDMENT ruling 4 (M3) — SECURITY_SUPERSESSIONS is an EXACT listing-key
# registry; a RenameEvent-implied bare-code match on a DIFFERENT venue must NEVER
# auto-tombstone (the reviewer's cross-MIC scenario) — it is disclosed instead.
def test_m3_the_registry_matches_the_committed_vmrk_entry_exactly() -> None:
    assert len(BUILD.SECURITY_SUPERSESSIONS) == 1
    entry = BUILD.SECURITY_SUPERSESSIONS[0]
    assert entry.listing_key == "US-XNYS-VMRK"
    assert entry.canonical_id == EQR_ID
    assert "0001140361-26-033377" in entry.evidence


def test_m3_reproduce_then_kill_the_cross_mic_auto_tombstone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REPRODUCE (the pre-fix defect): the OLD code matched any row whose bare
    inception code equalled a RenameEvent's `.new`, on ANY venue — a genuinely
    independent NASDAQ listing sharing VMRK's bare code as its OWN inception code
    got auto-tombstoned onto EQR. KILL: the fixed code matches SECURITY_SUPERSESSIONS
    entries by EXACT listing_key only, so the cross-MIC row must survive untouched
    and the mismatch must surface as a disclosure, never an execution.
    """
    eqr_row = {
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "country": "US", "mic": "XNYS", "inception_code": "EQR",
        "security_state": None, "superseded_by": None,
    }
    # A genuinely independent NASDAQ listing that happens to carry "VMRK" as its OWN
    # bare inception code — a different venue, a different real company.
    cross_mic_row = {
        "security_id": "SEC:US-XNAS-VMRK", "issuer_id": None,
        "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
        "issuer_evidence_snapshot": None, "listing_key": "US-XNAS-VMRK",
        "country": "US", "mic": "XNAS", "inception_code": "VMRK",
        "security_state": None, "superseded_by": None,
    }
    rows = [dict(eqr_row), dict(cross_mic_row)]
    # `ids` mirrors what mint_master_rows would really produce: "VMRK" as a SEED KEY
    # walks the real EQR->VMRK rename chain to the canonical EQR_ID — the cross-MIC
    # row is a DIFFERENT, independent listing that merely happens to share the bare
    # code "VMRK" on XNAS; its id is never a VALUE `ids` maps any seed key to.
    ids = {"EQR": EQR_ID, "VMRK": EQR_ID}

    # REPRODUCE: the pre-amendment matcher (bare inception-code match on ANY venue).
    def pre_fix_match(rows, ids):
        freshly = []
        for event in BUILD.RENAME_EVENTS:
            canonical_id = ids.get(event.new)
            if canonical_id is None:
                continue
            for row in rows:
                if row.get("security_state"):
                    continue
                if row["security_id"] == canonical_id:
                    continue
                try:
                    _c, _m, code = str(row["listing_key"]).split("-", 2)
                except ValueError:
                    continue
                if code.upper() != event.new:
                    continue
                row["security_state"] = BUILD.SECURITY_STATE_SUPERSEDED_DUPLICATE_MINT
                row["superseded_by"] = canonical_id
                freshly.append(row)
        return rows, freshly
    reproduced_rows, reproduced_freshly = pre_fix_match([dict(eqr_row), dict(cross_mic_row)], ids)
    reproduced = {r["security_id"]: r for r in reproduced_rows}
    assert reproduced["SEC:US-XNAS-VMRK"]["security_state"] == "SUPERSEDED_DUPLICATE_MINT", (
        "reproduction failed — the pre-fix matcher was expected to WRONGLY tombstone "
        "the cross-MIC row onto EQR"
    )

    # KILL: the fixed function must leave the cross-MIC row untouched.
    out_rows, freshly_superseded = BUILD.apply_security_supersession(rows, ids)
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNAS-VMRK"]["security_state"] is None, (
        "the EXACT-listing-key registry must never tombstone a cross-MIC row that "
        "merely shares the bare inception code"
    )
    assert freshly_superseded == []

    # And the mismatch is DISCLOSED, never silently dropped.
    disclosures = BUILD.detect_unregistered_rename_duplicates(out_rows)
    assert len(disclosures) == 1
    assert disclosures[0]["security_id"] == "SEC:US-XNAS-VMRK"


def test_m3_the_registered_exact_key_still_supersedes_normally() -> None:
    """The positive direction: a row whose listing_key EXACTLY matches the
    registered entry IS corrected — the fix narrows the match, it does not disable
    it."""
    eqr_row = {
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "country": "US", "mic": "XNYS", "inception_code": "EQR",
        "security_state": None, "superseded_by": None,
    }
    dup_row = {
        "security_id": "SEC:US-XNYS-VMRK", "issuer_id": None,
        "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
        "issuer_evidence_snapshot": None, "listing_key": "US-XNYS-VMRK",
        "country": "US", "mic": "XNYS", "inception_code": "VMRK",
        "security_state": None, "superseded_by": None,
    }
    out_rows, freshly_superseded = BUILD.apply_security_supersession(
        [eqr_row, dup_row], {"EQR": EQR_ID, "VMRK": "SEC:US-XNYS-VMRK"})
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNYS-VMRK"]["security_state"] == "SUPERSEDED_DUPLICATE_MINT"
    assert by_id["SEC:US-XNYS-VMRK"]["superseded_by"] == EQR_ID
    assert len(freshly_superseded) == 1
    assert BUILD.detect_unregistered_rename_duplicates(out_rows) == []


# ── AMENDMENT ruling 5 (M4) — dedup discriminator is each seed's CURRENT symbol,
# not the shared inception_code (which is structurally always equal whenever two
# resolutions reach the collision branch at all — the dead-code defect).
def test_m4_two_resolutions_sharing_a_current_symbol_dedup_lawfully() -> None:
    """The H2 shape as a direct unit test of mint_master_rows: EQR (root) and VMRK
    (chain member) both render US-XNYS-EQR and both walk to the SAME current symbol
    (VMRK) — dedup, no collision note, both map to the SAME freshly-minted id."""
    resolutions = [
        BUILD.Resolution("EQR", _lk("US", "XNYS", "EQR"), "EQR", "EQR",
                         "fixture", date(2020, 1, 1)),
        BUILD.Resolution("VMRK", _lk("US", "XNYS", "EQR"), "EQR", "EQR",
                         "fixture", date(2026, 8, 20)),
    ]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-20T00:00:00", cik_map={},
    )
    assert notes == [], "same current symbol must dedup lawfully, never a collision note"
    assert ids["EQR"] == ids["VMRK"] == EQR_ID
    assert len([r for r in rows if r["security_id"] == EQR_ID]) == 1


def test_m4_reproduce_then_kill_the_dead_collision_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REPRODUCE: the pre-fix discriminator (`res.inception_code`) is structurally
    ALWAYS equal whenever two resolutions share a rendered listing key (the key is
    literally built from the inception code), so the collision `notes.append` branch
    was DEAD — 0 resolutions could ever reach it. KILL: with a genuine ticker-REUSE
    fixture (two DIFFERENT raw seed identities that happen to render the same listing
    key but answer DIFFERENT current symbols), the fixed discriminator fires the
    collision note; the OLD discriminator would have silently deduped them instead.
    """
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", ())
    # Two independent Resolution objects manufactured to share a rendered listing
    # key (as the ONLY real path there — via resolve_universe — forces) while their
    # RAW seed keys answer DIFFERENT current symbols (no chain connects them).
    res_a = BUILD.Resolution("OLD1", _lk("US", "XNYS", "SHARED"), "SHARED", "OLD1",
                             "fixture", date(2020, 1, 1))
    res_b = BUILD.Resolution("OLD2", _lk("US", "XNYS", "SHARED"), "SHARED", "OLD2",
                             "fixture", date(2021, 1, 1))
    assert BUILD._current_symbol("OLD1") == "OLD1"
    assert BUILD._current_symbol("OLD2") == "OLD2"

    # REPRODUCE: the pre-fix discriminator compared `res.inception_code`, which is
    # "SHARED" for BOTH — always equal, so the pre-fix code would silently dedup.
    assert res_a.inception_code == res_b.inception_code == "SHARED", (
        "reproduction precondition — the dead discriminator's own equality holds"
    )

    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        [res_a, res_b], [], "2026-08-20T00:00:00", cik_map={},
    )
    assert notes, (
        "the fixed discriminator (_current_symbol of the RAW seed key) must fire "
        "the collision note for a genuine reuse — the pre-fix inception_code "
        "comparison could never distinguish this case (dead code)"
    )
    assert "collision" in notes[0]
    assert ids["OLD1"] == ids["OLD2"], (
        "collision still assigns a (shared, ambiguous) id — spec §5 leaves the "
        "human-ratified '.2' disambiguator as the resolution, not a crash"
    )


# ── AMENDMENT ruling 3 (M1) — the fence-scoped lost set excludes ONLY registered
# identity exceptions; the listing_continuity census discloses them as typed,
# EXPLAINED entries rather than silently dropping them.
def test_m1_a_registered_exception_loss_is_explained_not_silently_dropped() -> None:
    gold_row = {
        "security_id": "SEC:US-XNYS-GOLD", "issuer_id": None,
        "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
        "issuer_evidence_snapshot": None, "listing_key": "US-XNYS-GOLD",
        "country": "US", "mic": "XNYS", "inception_code": "GOLD",
        "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
        "security_state": None, "superseded_by": None,
    }
    fence_lost, exception_lost = BUILD._compute_lost([gold_row], [], {})
    assert fence_lost == [], (
        "a registered identity exception must NEVER gate the fence — its "
        "permanently-null CIK would otherwise jam all future minting"
    )
    assert len(exception_lost) == 1
    assert exception_lost[0]["security_id"] == "SEC:US-XNYS-GOLD"


def test_m1_a_genuine_unexplained_loss_still_gates_the_fence() -> None:
    """The OTHER direction: a row that is NOT a registered exception still lands in
    fence_lost (gates minting) and would still surface as a plain listing_continuity
    string, never silently folded into the explained bucket."""
    eqr_row = {
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "country": "US", "mic": "XNYS", "inception_code": "EQR",
        "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
        "security_state": None, "superseded_by": None,
    }
    fence_lost, exception_lost = BUILD._compute_lost([eqr_row], [], {})
    assert exception_lost == []
    assert len(fence_lost) == 1
    assert fence_lost[0]["security_id"] == EQR_ID


def test_m1_accepted_residual_a_rename_of_a_quarantined_listing_mints_without_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented accepted residual (AMENDMENT ruling 3): a rename of an
    exception-quarantined listing (e.g. GOLD -> a hypothetical GLDC) can mint a NEW
    id without a fence refusal, because the quarantined row is excluded from
    fence_lost entirely — this cannot corrupt a clean identity (the quarantined row
    was never the newcomer's identity) and the adjacent explained census line keeps
    it visible."""
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", ())
    gold_row = {
        "security_id": "SEC:US-XNYS-GOLD", "issuer_id": None,
        "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
        "issuer_evidence_snapshot": None, "listing_key": "US-XNYS-GOLD",
        "country": "US", "mic": "XNYS", "inception_code": "GOLD",
        "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
        "security_state": None, "superseded_by": None,
    }
    resolutions = [
        BUILD.Resolution("GLDC", _lk("US", "XNYS", "GLDC"), "GLDC", "GLDC",
                         "fixture", date(2026, 8, 20)),
    ]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [gold_row], "2026-08-20T00:00:00", cik_map={},
    )
    assert pending == [], (
        "a quarantined identity-exception row must never gate the fence — the "
        "documented accepted residual"
    )
    assert ids["GLDC"] == "SEC:US-XNYS-GLDC"
    assert exc_lost and exc_lost[0]["security_id"] == "SEC:US-XNYS-GOLD"


# ── AMENDMENT ruling 6 (M5) — a committed alias row may be pruned ONLY when it
# points at a superseded security_id; a fresh row overlapping a committed row that
# points at an ACTIVE id is now a fail-closed build error, never a silent
# last-write-wins replacement.
def _alias_dict(vendor: str, symbol: str, sec: str, vf: str | None, vt: str | None) -> dict:
    return {"vendor": vendor, "vendor_symbol": symbol, "security_id": sec,
            "valid_from": vf, "valid_to": vt, "ingested_at": "2026-08-13T00:00:00"}


def test_m5_a_row_pointing_at_a_superseded_id_is_pruned_and_receipted() -> None:
    existing = [_alias_dict("yahoo", "VMRK", "SEC:US-XNYS-VMRK", None, None)]
    fresh: list[AliasRow] = []
    kept, pruned = BUILD._prune_stale_aliases(existing, fresh, frozenset({"SEC:US-XNYS-VMRK"}))
    assert kept == []
    assert len(pruned) == 1
    assert pruned[0]["security_id"] == "SEC:US-XNYS-VMRK"


def test_m5_reproduce_then_kill_the_silent_active_id_replacement() -> None:
    """REPRODUCE (the pre-fix defect): ANY committed row overlapping a fresh row —
    even one pointing at a perfectly ACTIVE id — was silently dropped ("ambiguity-
    conflicting" class 2), an undisclosed last-write-wins replacement on an
    append-only dataset. KILL: the fixed function refuses instead, fail-closed."""
    existing = [_alias_dict("store", "EQR", EQR_ID, None, None)]  # fully open, ACTIVE id
    fresh = [AliasRow("store", "EQR", EQR_ID, None, date(2026, 8, 18))]  # overlaps

    # REPRODUCE: the pre-fix "ambiguity-conflicting" class silently dropped this.
    ex_row = AliasRow("store", "EQR", EQR_ID, None, None)
    assert ex_row.overlaps(fresh[0]), "reproduction precondition — the rows do overlap"

    # KILL: the fixed function raises instead of silently pruning.
    with pytest.raises(BUILD.VendorAliasPruneConflict):
        BUILD._prune_stale_aliases(existing, fresh, frozenset())


def test_m5_a_byte_identical_row_is_not_a_conflict() -> None:
    """Ordinary merge dedup, not a conflict — this never touches a fresh row's own
    side and must not spuriously raise."""
    existing = [_alias_dict("yahoo", "MMC", MMC_ID, None, "2026-01-14")]
    fresh = [AliasRow("yahoo", "MMC", MMC_ID, None, date(2026, 1, 14))]
    kept, pruned = BUILD._prune_stale_aliases(existing, fresh, frozenset())
    assert kept == existing
    assert pruned == []


def test_m5_a_non_overlapping_row_for_the_same_active_id_is_kept() -> None:
    """A fresh row for a DIFFERENT, non-overlapping time range against the same
    active security_id must not trip the fail-closed guard at all."""
    existing = [_alias_dict("yahoo", "MMC", MMC_ID, None, "2026-01-14")]
    fresh = [AliasRow("yahoo", "MRSH", MMC_ID, date(2026, 1, 14), None)]
    kept, pruned = BUILD._prune_stale_aliases(existing, fresh, frozenset())
    assert kept == existing
    assert pruned == []


# H3 — a hostile future map EQR->0000931182 (live-real, per E3: SEC's company_tickers
# now maps the bare string "EQR" to a DIFFERENT registrant, ERP Operating LP). The
# continuing row's evidence join key is its CURRENT symbol (VMRK), never the reused
# bare string "EQR" — this must never bind.
def test_h3_the_reassignment_trap_never_binds_to_the_bare_old_string() -> None:
    assert BUILD._evidence_join_key("VMRK") == "VMRK"
    # A hostile map keyed on the bare string "EQR" (the reassigned CIK, per E3) is
    # simply never consulted: the evidence join key for VMRK's inception code is
    # "VMRK", not "EQR", so a cik_map entry for "EQR" cannot reach this row at all.
    hostile_cik_map = {"EQR": ("0000931182", "ERP Operating Limited Partnership")}
    rows = [{
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "mic": "XNYS", "inception_code": "EQR",
    }]
    out_rows, migrations = BUILD.apply_issuer_correction(
        rows, hostile_cik_map, "2026-08-25", "2026-08-25T00:00:00")
    assert out_rows[0]["issuer_state"] == "RESOLVED", "mint-once — already resolved, never reopened"
    assert out_rows[0]["issuer_cik"] == "0000906107", "never rebound to the reassigned CIK"
    assert migrations == []


# H4 — a hostile future map VMRK->0000906107 (the CORRECT registrant CIK, arriving on
# a later weekly snapshot): the tombstone stays unexamined/unresolved — no allowlist
# trip, no EVIDENCE_CONFLICT on the EQR row.
def test_h4_a_future_map_naming_the_tombstones_own_registrant_never_reopens_it() -> None:
    tombstone = {
        "security_id": "SEC:US-XNYS-VMRK", "issuer_id": None,
        "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
        "issuer_evidence_snapshot": None, "listing_key": "US-XNYS-VMRK",
        "mic": "XNYS", "inception_code": "VMRK",
        "security_state": "SUPERSEDED_DUPLICATE_MINT", "superseded_by": EQR_ID,
    }
    eqr_row = {
        "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
        "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
        "mic": "XNYS", "inception_code": "EQR",
    }
    hostile_cik_map = {"VMRK": ("0000906107", "Vivmark Residential")}
    out_rows, migrations = BUILD.apply_issuer_correction(
        [tombstone, eqr_row], hostile_cik_map, "2026-08-25", "2026-08-25T00:00:00")
    by_id = {r["security_id"]: r for r in out_rows}
    # The tombstone's issuer axis is byte-frozen — never re-examined.
    assert by_id["SEC:US-XNYS-VMRK"]["issuer_state"] == "NO_ISSUER_EVIDENCE"
    assert by_id["SEC:US-XNYS-VMRK"]["issuer_id"] is None
    # No EVIDENCE_CONFLICT on the (untouched) EQR row either.
    assert by_id[EQR_ID]["issuer_state"] == "RESOLVED"
    assert migrations == []


# H5 — AVB: typed exit only, never joined to VMRK on any axis.
def test_h5_avb_is_exit_typed_only_never_joined_to_vmrk() -> None:
    from lib import delisted_symbols
    delisted_symbols.ledger.cache_clear()
    row = delisted_symbols.ledger().get("AVB")
    assert row is not None, "config/delisted_symbols.yml must carry an AVB row"
    assert row["reason"] == "acquisition"
    assert row.get("successor_ticker") is None, (
        "AVB must never carry a successor_ticker — that would splice it onto VMRK's tape"
    )


def test_h5_avb_master_row_is_retained_with_its_own_issuer_history(master: pd.DataFrame) -> None:
    avb = master[master["inception_code"] == "AVB"]
    assert len(avb) == 1
    assert avb.iloc[0]["security_id"] == "SEC:US-XNYS-AVB"
    assert avb.iloc[0]["issuer_cik"] == "0000915912"
    assert pd.isna(avb.iloc[0]["security_state"]), "AVB is exit-typed, never security-superseded"


def test_h5_avb_leaves_unresolved_names_and_no_avb_vmrk_alias_exists(
    receipt: dict, aliases: pd.DataFrame,
) -> None:
    assert "AVB" not in receipt["coverage"]["unresolved_names"]
    assert "EQR" not in receipt["coverage"]["unresolved_names"]
    avb_id = "SEC:US-XNYS-AVB"
    joined = aliases[(aliases["security_id"] == EQR_ID)
                     & (aliases["vendor_symbol"] == "AVB")]
    assert joined.empty, "AVB must never alias onto the VMRK/EQR security"
    joined2 = aliases[(aliases["security_id"] == avb_id)
                      & (aliases["vendor_symbol"].isin(["VMRK"]))]
    assert joined2.empty, "VMRK must never alias onto the AVB security"


# ── AMENDMENT ruling 1 (B1, BLOCKER) — H10: an end-to-end build() run through BOTH
# refusal classes must complete: receipts disclose, ::warning fires, NO exception,
# and every artifact writes. REPRODUCE (before the fix): build_alias_rows did
# `sec = ids[res.key]` unconditionally for every resolved-listing-key resolution —
# a refused resolution (pending-transition OR resurrection) never gets an `ids`
# entry, so this raised `KeyError` and build() crashed AFTER printing the
# ::warning but BEFORE writing a single artifact. On the real nightly seam this
# meant the fence could never actually ship its own disclosure.
def test_h10_end_to_end_build_survives_both_refusal_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", ())
    monkeypatch.setattr(BUILD, "load_universe", lambda: {
        # VMRK: resolves to listing key US-XNYS-VMRK, which the pre-seeded master
        # already carries as a TOMBSTONE -> resurrection refusal.
        "VMRK": {"sources": ["fixture"], "first_seen": date(2026, 8, 20)},
        # NEWCO: a listing-key MISS with no independent CIK evidence while EQR
        # (below) is unaccounted-for this build -> pending-transition refusal.
        "NEWCO": {"sources": ["fixture"], "first_seen": date(2026, 8, 20)},
    })
    monkeypatch.setattr(BUILD, "load_delisted", lambda: {})
    monkeypatch.setattr(
        BUILD, "load_directory",
        lambda: ({"VMRK": "N", "NEWCO": "NASDAQ"}, {}, "2026-08-20", None),
    )
    monkeypatch.setattr(BUILD, "load_cik_map", lambda: ({}, None, None, frozenset()))
    monkeypatch.setattr(BUILD, "load_config_maps", lambda: ({}, {}))
    # This fixture exercises the pre-existing VMRK/NEWCO fence shapes in isolation —
    # keep it hermetic against the real committed theme graph (D2B2-US adds its own
    # dedicated fixtures below).
    monkeypatch.setattr(BUILD, "load_gmi_us_seeds", lambda: [])

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    existing_rows = [
        {
            # EQR: active, and NOT re-derived this build (not in the fixture
            # universe above) -> the fence's `lost` set.
            "security_id": EQR_ID, "issuer_id": "ISS:US-XNYS-EQR",
            "issuer_state": "RESOLVED", "issuer_cik": "0000906107",
            "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-EQR",
            "country": "US", "mic": "XNYS", "inception_code": "EQR",
            "effective_at": "2023-05-09T00:00:00", "ingested_at": "2026-08-13T00:00:00",
            "security_state": None, "superseded_by": None,
        },
        {
            # The tombstone VMRK's own resolution will hit.
            "security_id": "SEC:US-XNYS-VMRK", "issuer_id": None,
            "issuer_state": "NO_ISSUER_EVIDENCE", "issuer_cik": None,
            "issuer_evidence_snapshot": None, "listing_key": "US-XNYS-VMRK",
            "country": "US", "mic": "XNYS", "inception_code": "VMRK",
            "effective_at": "2026-08-20T00:00:00", "ingested_at": "2026-08-20T01:30:18",
            "security_state": "SUPERSEDED_DUPLICATE_MINT", "superseded_by": EQR_ID,
        },
    ]
    BUILD._write_parquet(existing_rows, BUILD.MASTER_COLUMNS,
                         out_dir / BUILD.MASTER_NAME, BUILD.MASTER_DTYPES)
    capsys.readouterr()

    # KILL: this must not raise (the pre-fix code crashed here with KeyError).
    receipt = BUILD.build(out_dir, allow_missing_evidence=True)

    assert len(receipt["resurrection_refusals"]) == 1
    assert receipt["resurrection_refusals"][0]["security_id"] == "SEC:US-XNYS-VMRK"
    assert len(receipt["pending_transition_refusals"]) == 1
    assert receipt["pending_transition_refusals"][0]["symbol"] == "NEWCO"

    out = capsys.readouterr().out
    assert "::warning" in out
    assert "resurrection-refusal" in out
    assert "pending-transition" in out

    # Every artifact actually wrote (the crash used to happen AFTER the mint stage
    # but BEFORE any _write_parquet call).
    for name in (BUILD.MASTER_NAME, BUILD.ALIASES_NAME, BUILD.ISSUER_MASTER_NAME,
                BUILD.ISSUER_MIGRATIONS_NAME, BUILD.SECURITY_MIGRATIONS_NAME,
                BUILD.RECEIPT_NAME):
        assert (out_dir / name).exists(), f"{name} must be written — build() did not crash"

    # Neither refused resolution contributed ANY alias row.
    aliases_out = pd.read_parquet(out_dir / BUILD.ALIASES_NAME)
    assert not (aliases_out["vendor_symbol"] == "NEWCO").any()
    assert not aliases_out["security_id"].isin(["SEC:US-XNAS-NEWCO"]).any()


# §6.1 — sidecar assertions (re-derived; see tests/test_theme_graph_identity_resolution.py
# for the full sidecar suite; these pin the specific V4-D2B1-R1 post-state).
def test_the_master_reader_excludes_the_tombstone_from_issuer_aggregation() -> None:
    from lib.dataos.identity import IssuerMaster, SecurityIssuerRow

    rows = [
        SecurityIssuerRow(security_id=EQR_ID, issuer_id="ISS:US-XNYS-EQR",
                          issuer_state="RESOLVED", listing_key="US-XNYS-EQR"),
        SecurityIssuerRow(security_id="SEC:US-XNYS-VMRK", issuer_id="ISS:US-XNYS-EQR",
                          issuer_state="RESOLVED", listing_key="US-XNYS-VMRK",
                          security_state="SUPERSEDED_DUPLICATE_MINT",
                          superseded_by=EQR_ID),
    ]
    reader = IssuerMaster(rows)
    assert reader.securities_of_issuer("ISS:US-XNYS-EQR") == (EQR_ID,), (
        "a superseded row must never appear in the issuer's roster, even if it were "
        "hypothetically stamped with the same issuer_id"
    )
    assert reader.security_state_of("SEC:US-XNYS-VMRK") == "SUPERSEDED_DUPLICATE_MINT"
    assert reader.superseded_by_of("SEC:US-XNYS-VMRK") == EQR_ID
    assert reader.security_state_of(EQR_ID) is None
    assert reader.superseded_by_of(EQR_ID) is None


def test_the_master_grain_is_one_row_per_security(master: pd.DataFrame) -> None:
    assert master["security_id"].is_unique
    assert master["listing_key"].is_unique
    assert not master["security_id"].isna().any()


def test_every_alias_points_at_a_security_the_master_carries(
    master: pd.DataFrame, aliases: pd.DataFrame
) -> None:
    """Referential integrity — the alias table declares reference.security_master as its input."""
    orphans = sorted(set(aliases["security_id"]) - set(master["security_id"]))
    assert orphans == [], f"alias rows referencing no master row: {orphans[:10]}"


# ── SCHEMA CONFORMANCE ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "dataset_id,path",
    [
        ("reference.security_master", MASTER_PATH),
        ("reference.vendor_aliases", ALIASES_PATH),
    ],
)
def test_emitted_columns_are_exactly_the_registry_schema(dataset_id: str, path: Path) -> None:
    """The registry is the CONTRACT, not a description of whatever the builder emitted.

    Equality in both directions on purpose: a missing column breaks a consumer, and an
    extra undeclared one is a field nobody agreed to maintain.
    """
    declared = list(load_registry().get(dataset_id).schema)
    emitted = list(pd.read_parquet(path).columns)
    assert emitted == declared


def test_every_produced_row_names_a_real_store_and_a_real_producer() -> None:
    """Gate G1, executable: "every PRODUCED row's storage path exists and its producer
    is a real symbol".  A registry that lists a dataset which does not exist is worse
    than no registry, because the next session builds against it
    (``lib/dataos/registry.py`` module docstring).

    Templated paths (``data/stocks/{ticker}.parquet``) are checked at the deepest
    literal directory — the per-ticker leaf is a naming rule, not a promise about one
    file.
    """
    for contract in load_registry().all():
        if contract.status is not DatasetStatus.PRODUCED:
            continue
        storage = str(contract.storage)
        literal = storage.split("{", 1)[0]
        target = ROOT / (literal if literal.endswith("/") else literal)
        if "{" in storage:
            target = ROOT / Path(literal).parent
        assert target.exists(), f"{contract.dataset_id}: storage {storage!r} does not exist"

        producer = str(contract.producer)
        if producer.endswith(".py"):
            assert (ROOT / producer).is_file(), (
                f"{contract.dataset_id}: producer {producer!r} is not a file in this tree"
            )


# ── COVERAGE IS MEASURED, NEVER ASSERTED COMPLETE ─────────────────────────────
def test_the_receipt_reports_coverage_as_numbers_that_add_up(receipt: dict) -> None:
    """DOS-1.1 asks for "N of M resolved, K unresolved, listed by name" — a REPORTED
    number.  This deliberately does NOT assert 100%: eight seed names have no venue
    this repo can evidence (an ADR absent from the exchange directory, a Cboe-listed
    name whose MIC is not in the closed ``KNOWN_MICS`` list), and minting them onto a
    guessed venue would produce a stable, wrong id — the one mistake §5 says this
    scheme cannot self-heal.  What IS asserted is that the arithmetic is honest and the
    unresolved names are printed rather than hidden.
    """
    coverage = receipt["coverage"]
    for field in ("total", "resolved", "unresolved"):
        assert isinstance(coverage[field], int), field
    assert coverage["resolved"] + coverage["unresolved"] == coverage["total"]
    assert coverage["total"] > 0
    assert len(coverage["unresolved_names"]) == coverage["unresolved"]
    assert coverage["unresolved_names"] == sorted(coverage["unresolved_names"])


def test_the_receipt_carries_provenance_for_every_input(receipt: dict) -> None:
    """`code_version` + per-input sha256: lineage is "walk the DAG, read the receipts"."""
    assert receipt["producer"] == "scripts/build_security_master.py"
    assert receipt["generated_at"]
    assert set(receipt["dataset_ids"]) == {
        "reference.security_master",
        "reference.vendor_aliases",
        "reference.issuer_master",
        "reference.issuer_migrations",
        "reference.security_migrations",
    }
    inputs = receipt["inputs"]
    assert inputs, "a receipt with no inputs cannot support a lineage query"
    for name, digest in inputs.items():
        assert (ROOT / name).exists(), f"receipt names an input that is not in the tree: {name}"
        assert digest is None or len(digest) == 64, name
    for required in ("data/breadth/constituents.parquet", "data/baskets/membership.json",
                     "config/delisted_symbols.yml", "lib/ticker_aliases.py"):
        assert required in inputs, f"{required} is a seed and must be hashed in the receipt"


def test_the_receipt_row_counts_match_the_artifacts(
    receipt: dict, master: pd.DataFrame, aliases: pd.DataFrame
) -> None:
    assert receipt["row_counts"]["security_master"] == len(master)
    assert receipt["row_counts"]["vendor_aliases"] == len(aliases)


def test_the_dated_renames_are_recorded_with_their_evidence(receipt: dict) -> None:
    """A date lifted out of prose has to carry the prose that justified it."""
    events = {(e["old"], e["new"]): e for e in receipt["rename_events"]}
    assert events[("MMC", "MRSH")]["on"] == MMC_RENAME.isoformat()
    assert events[("SATS", "ECHO")]["on"] == SATS_RENAME.isoformat()
    for event in events.values():
        assert event["evidence"].strip(), event
        assert event["vendors"]


# ── MINT ONCE AND STORE ───────────────────────────────────────────────────────
def test_rebuilding_never_changes_an_existing_security_id(tmp_path: Path) -> None:
    """Run the builder twice; no id may move, and the bodies must be byte-identical.

    Idempotence is the whole point of a derived id (spec §4): "re-running the nightly
    must not create a second identity for an unchanged security".
    """
    first = BUILD.build(tmp_path)
    before = pd.read_parquet(tmp_path / BUILD.MASTER_NAME)
    master_bytes = (tmp_path / BUILD.MASTER_NAME).read_bytes()
    alias_bytes = (tmp_path / BUILD.ALIASES_NAME).read_bytes()

    second = BUILD.build(tmp_path)
    after = pd.read_parquet(tmp_path / BUILD.MASTER_NAME)

    assert dict(zip(before["listing_key"], before["security_id"])) == dict(
        zip(after["listing_key"], after["security_id"])
    )
    assert (tmp_path / BUILD.MASTER_NAME).read_bytes() == master_bytes
    assert (tmp_path / BUILD.ALIASES_NAME).read_bytes() == alias_bytes
    assert first["coverage"] == second["coverage"]


def test_the_stored_id_is_the_authority_not_the_derivation(tmp_path: Path) -> None:
    """Mint-once-and-store, proven the only way it can be: by disagreeing with the mint.

    A merely deterministic builder passes a run-it-twice check for the wrong reason —
    it re-derives the same string.  So this rewrites a committed ``security_id`` to a
    value the derivation would NEVER produce and asserts the rebuild keeps it.  That is
    the property §D2 needs: a later correction appends an alias, it never re-mints.

    The alias file is removed first on purpose.  An id correction that does not also
    re-derive the aliases legitimately leaves two live rows for one
    ``(vendor, vendor_symbol)``, and ``VendorAliasTable`` refuses that at construction —
    fail-closed, and a separate property (see the ambiguity test below).
    """
    BUILD.build(tmp_path)
    frame = pd.read_parquet(tmp_path / BUILD.MASTER_NAME)
    forced = "SEC:US-XNYS-NOTAMINT"
    frame.loc[frame["listing_key"] == "US-XNYS-MMC", "security_id"] = forced
    rows = [
        {k: BUILD._normalize_datetime(v) if k in BUILD.MASTER_DTYPES else v
         for k, v in record.items()}
        for record in frame.to_dict("records")
    ]
    BUILD._write_parquet(rows, BUILD.MASTER_COLUMNS, tmp_path / BUILD.MASTER_NAME,
                         BUILD.MASTER_DTYPES)
    (tmp_path / BUILD.ALIASES_NAME).unlink()

    BUILD.build(tmp_path)
    rebuilt = pd.read_parquet(tmp_path / BUILD.MASTER_NAME)
    stored = rebuilt.loc[rebuilt["listing_key"] == "US-XNYS-MMC", "security_id"]
    assert list(stored) == [forced], "the derivation overwrote a stored id — that is a re-mint"
    assert MMC_ID not in set(rebuilt["security_id"]), "a second id was minted for one security"

    aliases = pd.read_parquet(tmp_path / BUILD.ALIASES_NAME)
    yahoo_mmc = aliases[(aliases["vendor"] == "yahoo") & (aliases["vendor_symbol"] == "MMC")]
    assert list(yahoo_mmc["security_id"]) == [forced], (
        "aliases must follow the STORED id, not the freshly derived one"
    )


# ── FRESHNESS: nothing SCHEDULES this producer, so a test is the clock ────────
def _alias_grain(frame: pd.DataFrame) -> set[tuple]:
    return {
        (str(r["vendor"]), str(r["vendor_symbol"]), str(r["security_id"]),
         BUILD._normalize_bound(r["valid_from"]), BUILD._normalize_bound(r["valid_to"]))
        for r in frame.to_dict("records")
    }


def test_the_committed_artifact_is_not_stale_against_the_current_seeds(
    tmp_path: Path, master: pd.DataFrame, aliases: pd.DataFrame
) -> None:
    """The freshness contract, because NOTHING RUNS THE PRODUCER (review, 2026-08-13).

    ``grep -rn build_security_master .github/ ops/`` returns the ci.yml path filter and
    nothing else: no workflow, no cron, no nightly step.  The seeds move underneath it
    anyway — ``data/symbol_directory/snapshots/`` gains a file per night and
    ``data/baskets/membership.json`` churns on every universe change — so without this
    the registry could claim a PRODUCED dataset while the artifact described a seed set
    from weeks ago and every check stayed green forever.  That is gate G1's failure
    ("a registry listing a dataset that does not exist is worse than no registry") one
    step downstream: the row is true about the PATH and false about the CONTENT.

    The shape is a rebuild ON TOP OF the committed artifact, which is exactly what a
    real re-run does — ``mint_master_rows``/``merge_alias_rows`` are append-only, so a
    name LEAVING the seeds correctly changes nothing and cannot red this.  What reds it
    is a seed change that would ADD a security or an alias row, i.e. precisely the
    moment a re-run is owed.  ``frequency: on_demand`` in the registry says the same
    thing in the contract; this makes it enforceable.
    """
    shutil.copy(MASTER_PATH, tmp_path / BUILD.MASTER_NAME)
    shutil.copy(ALIASES_PATH, tmp_path / BUILD.ALIASES_NAME)
    BUILD.build(tmp_path)

    rebuilt_master = pd.read_parquet(tmp_path / BUILD.MASTER_NAME)
    added = sorted(set(rebuilt_master["listing_key"]) - set(master["listing_key"]))
    assert added == [], (
        f"the current seeds resolve {len(added)} listing key(s) the committed "
        f"security master does not carry: {added[:10]} — the artifact is STALE. "
        f"Re-run `{REBUILD}` and commit data/reference/."
    )
    # An id may never MOVE either: mint-once is what the whole artifact is for.
    committed_ids = dict(zip(master["listing_key"], master["security_id"]))
    rebuilt_ids = dict(zip(rebuilt_master["listing_key"], rebuilt_master["security_id"]))
    moved = {k: (v, rebuilt_ids[k]) for k, v in committed_ids.items() if rebuilt_ids[k] != v}
    assert moved == {}, f"a rebuild re-minted a stored security_id: {moved}"

    rebuilt_aliases = pd.read_parquet(tmp_path / BUILD.ALIASES_NAME)
    new_rows = sorted(_alias_grain(rebuilt_aliases) - _alias_grain(aliases))
    assert new_rows == [], (
        f"the current seeds support {len(new_rows)} alias row(s) the committed table "
        f"does not carry: {new_rows[:5]} — re-run `{REBUILD}` and commit data/reference/."
    )


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    receipt = BUILD.build(tmp_path, dry_run=True)
    assert receipt["coverage"]["total"] > 0
    assert not (tmp_path / BUILD.MASTER_NAME).exists()
    assert not (tmp_path / BUILD.ALIASES_NAME).exists()
    assert not (tmp_path / BUILD.RECEIPT_NAME).exists()


def test_the_cli_reports_the_coverage_line_verbatim(tmp_path: Path, capsys) -> None:
    """The report format DOS-1.1 asks for, and the GitHub annotation form the house
    requires: a bare print at column 0, because a prefixing logger emits
    "WARNING ::warning …" and GitHub silently drops it."""
    assert BUILD.main(["--out", str(tmp_path), "--dry-run", "--report"]) == 0
    out = capsys.readouterr().out
    # The FIRST non-annotation line, never bare `splitlines()[0]`: from an EMPTY
    # `tmp_path` (no committed master at all) every GMI-US seed becomes an admission
    # target, so a genuine (D2B2-US §3/§4) eligibility ``::warning`` can legitimately
    # print DURING the mint stage, before `_report()`'s own coverage line — exactly
    # like the pre-existing pending-transition/resurrection ``::warning``s already do
    # in other fixtures; only the ORDER relative to the report is new here.
    lines = out.splitlines()
    first = next(line for line in lines if not line.startswith("::"))
    assert " resolved, " in first and first.endswith(" unresolved")
    assert "/" in first.split(" resolved")[0]
    annotations = [line for line in out.splitlines() if "::warning" in line]
    for line in annotations:
        assert line.startswith("::"), f"annotation does not start its line: {line!r}"


# ── PURE FUNCTIONS OVER FIXTURES ──────────────────────────────────────────────
def test_inception_code_walks_a_rename_chain_to_its_root() -> None:
    """Both sides of a chain resolve to the ROOT, and the directory spelling never wins.

    MMC is the case that matters: the repo's key is the OLD symbol while the venue's
    current spelling is the NEW one, so reaching for the directory would mint
    ``US-XNYS-MRSH`` — an id built on today's symbol.
    """
    assert BUILD._inception_code("MMC", "MRSH") == "MMC"
    assert BUILD._inception_code("MRSH", "MRSH") == "MMC"
    assert BUILD._inception_code("ECHO", "ECHO") == "SATS"
    assert BUILD._inception_code("SATS", None) == "SATS"
    assert BUILD._inception_code("FI", "FISV") == "FISV"
    # No rename recorded: the venue is the authority on its own code spelling.
    assert BUILD._inception_code("BRK-B", "BRK.B") == "BRK.B"
    assert BUILD._inception_code("AAPL", "AAPL") == "AAPL"


def test_class_notation_variants_cover_both_spellings() -> None:
    assert BUILD._class_notation_variants("BRK-B") == ("BRK-B", "BRK.B")
    assert BUILD._class_notation_variants("BRK.B") == ("BRK.B", "BRK-B")
    assert BUILD._class_notation_variants("AAPL") == ("AAPL",)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("NaT", None),
        (float("nan"), None),
        (date(2026, 1, 14), "2026-01-14"),
        ("2026-01-14", "2026-01-14"),
        (pd.Timestamp("2026-01-14"), "2026-01-14"),
    ],
)
def test_open_bounds_survive_every_shape_pandas_can_return(value, expected) -> None:
    """A parquet null comes back as None, NaN or NaT depending on the inferred dtype.
    All three mean OPEN BOUND; a builder that treated one of them as a date string
    would silently close an interval."""
    assert BUILD._normalize_bound(value) == expected


def test_an_ambiguous_table_is_refused_at_construction() -> None:
    """G2-flavoured: the guard is shown RED on a deliberately broken input.

    Two overlapping rows for one ``(vendor, vendor_symbol)`` means the translation layer
    could return either of two answers, which is not a translation layer.  The builder
    round-trips every row through this constructor before writing, so an ambiguous table
    fails at write time rather than in a consumer.
    """
    with pytest.raises(IdentityError):
        VendorAliasTable([
            AliasRow("yahoo", "MMC", MMC_ID, None, MMC_RENAME),
            AliasRow("yahoo", "MMC", "SEC:US-XNYS-OTHER", None, None),
        ])
    # The committed pairing is the NON-overlapping form of the same two rows.
    VendorAliasTable([
        AliasRow("yahoo", "MMC", MMC_ID, None, MMC_RENAME),
        AliasRow("yahoo", "MRSH", MMC_ID, MMC_RENAME, None),
    ])


def test_alias_rows_are_built_dated_for_a_rename_and_open_otherwise() -> None:
    """The builder's alias construction, over a two-name fixture rather than the seeds."""
    from lib.dataos.identity import ListingKey

    resolutions = [
        BUILD.Resolution("MMC", ListingKey("US", "XNYS", "MMC"), "MMC", "MRSH",
                         "fixture", date(2023, 1, 3)),
        BUILD.Resolution("AAPL", ListingKey("US", "XNAS", "AAPL"), "AAPL", "AAPL",
                         "fixture", date(2023, 1, 3)),
    ]
    ids = {"MMC": MMC_ID, "AAPL": "SEC:US-XNAS-AAPL"}
    rows = BUILD.build_alias_rows(resolutions, ids)
    by_pair = {(r.vendor, r.vendor_symbol): r for r in rows}

    assert by_pair[("yahoo", "MMC")].valid_to == MMC_RENAME
    assert by_pair[("yahoo", "MMC")].valid_from is None
    assert by_pair[("yahoo", "MRSH")].valid_from == MMC_RENAME
    assert by_pair[("yahoo", "MRSH")].valid_to is None
    assert by_pair[("membership", "MMC")].valid_from is None
    assert by_pair[("membership", "MMC")].valid_to is None
    # An unrenamed name gets one open row per space and no dated pair at all.
    assert by_pair[("yahoo", "AAPL")].valid_from is None
    assert by_pair[("membership", "AAPL")].valid_to is None
    assert ("ledger", "AAPL") not in by_pair
    # The CURRENT-CATALOG family is open-bounded even across a rename — that is what
    # distinguishes it, and a dated row here would make it a second historical space.
    assert by_pair[("yahoo_fetch", "MRSH")].valid_from is None
    assert by_pair[("yahoo_fetch", "MRSH")].valid_to is None
    assert by_pair[("store", "MMC")].valid_to is None
    assert ("yahoo_fetch", "MMC") not in by_pair
    assert ("store", "MRSH") not in by_pair
    assert by_pair[("yahoo_fetch", "AAPL")].valid_to is None
    assert by_pair[("store", "AAPL")].valid_to is None
    VendorAliasTable(rows)  # and the fixture table is unambiguous


def test_every_rename_the_repo_records_is_modelled_by_the_builder() -> None:
    """The next rename must not be able to land silently.

    ``breadth.ticker_fixups`` and ``quality.ticker_key_migrations`` are one-line,
    TIMELESS maps.  Adding a pair to either without adding a dated event here would
    leave the alias table answering the OLD pairing forever — the exact shape of the
    seven-month MMC loss, one layer up.  Today both maps are fully modelled.
    """
    fixups, migrations = BUILD.load_config_maps()
    assert fixups, "breadth.ticker_fixups vanished — the seed this builder reads is gone"
    assert migrations, "quality.ticker_key_migrations vanished"
    assert BUILD.unmodelled_renames(fixups, migrations) == []
    # And the detector has teeth: an unmodelled pair is REPORTED, not swallowed.
    assert BUILD.unmodelled_renames({"OLDX": "NEWX"}, {}) != []


def test_an_unmodelled_rename_FAILS_the_builder_it_does_not_merely_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A `::warning` + exit 0 makes a silent-loss detector advisory (review 2026-08-13).

    ``receipt['notes']`` carries only two things and neither may pass: a rename the
    repo's own timeless maps record that this builder does not model, and a listing-key
    COLLISION (spec §5: an operator-ratified `.2`, never a guess).  Shown RED on a
    deliberately broken input and green on the real one, in the same test (gate G2).
    """
    real = BUILD.load_config_maps
    monkeypatch.setattr(
        BUILD, "load_config_maps",
        lambda: ({**real()[0], "NEWNAME": "OLDNAME"}, real()[1]),
    )
    assert BUILD.main(["--out", str(tmp_path), "--dry-run"]) == 1
    out = capsys.readouterr().out
    assert "NEWNAME->OLDNAME" in out
    assert any(line.startswith("::warning") for line in out.splitlines())

    monkeypatch.setattr(BUILD, "load_config_maps", real)
    assert BUILD.main(["--out", str(tmp_path), "--dry-run"]) == 0
    # Coverage is deliberately NOT in that set: DOS-1.1 asks for it to be REPORTED.
    assert "unresolved" in capsys.readouterr().out


def test_the_rename_maps_live_in_a_file_that_can_reach_this_suite() -> None:
    """The detector above must be REACHABLE from the edit that trips it.

    Both timeless rename maps live in root ``config.yml``, and the next rename lands the
    way both modelled ones did: one line in ``breadth.ticker_fixups`` or
    ``quality.ticker_key_migrations``.  Measured 2026-08-13: a ``config.yml``-only diff
    selected 48 of 186 legacy jobs and ``house-law-registry`` — the only job that names
    this suite — was NOT among them, because scope inference cannot own a repository-ROOT
    file at all (``run_ci_pack.SCOPE_REFERENCE_RE`` and
    ``ci_scope_dependencies._PATH_LITERAL`` both require a tracked directory prefix).
    A detector nothing can reach is a detector nothing has.

    The fix is a DECLARED scope entry, and this pins it.  Reading the manifest is enough
    and importing ``run_ci_pack`` would not be: its dependency closure would be folded
    into this job's own inferred scope, which is the thing under test.
    """
    manifest = yaml.safe_load(MANIFEST_PATH.read_text())
    job = manifest["jobs"]["house-law-registry"]
    assert "config.yml" in (job.get("paths") or []), (
        "house-law-registry must DECLARE root config.yml: it is where both timeless "
        "rename maps live, and no derived scope can ever own a repo-root file"
    )
    commands = "\n".join(str(s["run"]) for s in job["steps"] if "run" in s)
    assert "tests/test_dataos_security_master.py" in commands, (
        "the declared config.yml scope only helps while THIS suite runs in that job"
    )
    # And the workflow can actually start on that file, or the scope is decorative.
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    triggers = (workflow.get("on") or workflow.get(True))["pull_request"]["paths"]
    assert "config.yml" in triggers


# ── V4-D2B1: nightly fail-closed refresh seam (§7) ──────────────────────────────
def test_nightly_refuses_non_fatally_on_a_missing_identity_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    monkeypatch.setattr(BUILD, "CONSTITUENTS", tmp_path / "does-not-exist.parquet")
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    out = capsys.readouterr().out
    assert "::warning" in out
    assert not (tmp_path / BUILD.MASTER_NAME).exists()


def test_nightly_is_a_byte_stable_noop_when_inputs_are_unchanged(
    tmp_path: Path, capsys,
) -> None:
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    before = {
        name: (tmp_path / name).read_bytes()
        for name in BUILD._NIGHTLY_ARTIFACT_NAMES
    }
    before_receipt = (tmp_path / BUILD.RECEIPT_NAME).read_bytes()

    assert BUILD.run_nightly_refresh(tmp_path) == 0
    out = capsys.readouterr().out
    assert "byte-stable no-op" in out
    for name in BUILD._NIGHTLY_ARTIFACT_NAMES:
        assert (tmp_path / name).read_bytes() == before[name], name
    assert (tmp_path / BUILD.RECEIPT_NAME).read_bytes() == before_receipt, (
        "generated_at must NOT be re-stamped on a no-op nightly run"
    )


def test_nightly_regenerates_and_restamps_only_when_inputs_advance(
    tmp_path: Path, capsys,
) -> None:
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    before_master = (tmp_path / BUILD.MASTER_NAME).read_bytes()

    # Force a stored id to a value the derivation would never produce (the same
    # "mint-once, not merely deterministic" trick as test_the_stored_id_is_the_
    # authority_not_the_derivation) — the master itself now differs, so a fresh
    # nightly run must regenerate and re-stamp.
    frame = pd.read_parquet(tmp_path / BUILD.MASTER_NAME)
    frame.loc[frame["listing_key"] == "US-XNYS-MMC", "issuer_state"] = None
    frame.loc[frame["listing_key"] == "US-XNYS-MMC", "issuer_id"] = "ISS:US-XNYS-FORCED"
    rows = [
        {k: BUILD._normalize_datetime(v) if k in BUILD.MASTER_DTYPES else v
         for k, v in record.items()}
        for record in frame.to_dict("records")
    ]
    BUILD._write_parquet(rows, BUILD.MASTER_COLUMNS, tmp_path / BUILD.MASTER_NAME,
                         BUILD.MASTER_DTYPES)
    forced_bytes = (tmp_path / BUILD.MASTER_NAME).read_bytes()
    assert forced_bytes != before_master

    assert BUILD.run_nightly_refresh(tmp_path) == 0
    out = capsys.readouterr().out
    assert "regenerated" in out
    # Content-based proof (robust to same-second wall-clock stamps, unlike comparing
    # generated_at strings): the forced value is gone — the era re-derived it — and
    # the artifact is no longer the forced bytes.
    after = pd.read_parquet(tmp_path / BUILD.MASTER_NAME)
    mmc = after.loc[after["listing_key"] == "US-XNYS-MMC"].iloc[0]
    assert mmc["issuer_id"] != "ISS:US-XNYS-FORCED"
    assert mmc["issuer_state"] == "RESOLVED"
    assert (tmp_path / BUILD.MASTER_NAME).read_bytes() != forced_bytes


def test_nightly_restores_last_good_on_an_unmodelled_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """§7 fail-closed law (a)-adjacent: a config defect (the two things
    ``receipt['notes']`` ever carries) must never produce a falsely fresh generation
    — every artifact, INCLUDING the receipt, is restored to its prior bytes."""
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    before = {name: (tmp_path / name).read_bytes() for name in BUILD._NIGHTLY_ARTIFACT_NAMES}
    before_receipt = (tmp_path / BUILD.RECEIPT_NAME).read_bytes()

    real = BUILD.load_config_maps
    monkeypatch.setattr(
        BUILD, "load_config_maps",
        lambda: ({**real()[0], "NEWNAME": "OLDNAME"}, real()[1]),
    )
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    out = capsys.readouterr().out
    assert "::warning" in out
    for name in BUILD._NIGHTLY_ARTIFACT_NAMES:
        assert (tmp_path / name).read_bytes() == before[name], name
    assert (tmp_path / BUILD.RECEIPT_NAME).read_bytes() == before_receipt


def test_nightly_restores_last_good_on_a_vendor_alias_prune_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """AMENDMENT §3 (2026-08-20, re-verification) — MAJOR regression fix.

    ``VendorAliasPruneConflict`` used to subclass ``SystemExit`` (a ``BaseException``
    sibling to ``Exception``), so it ESCAPED :func:`BUILD.run_nightly_refresh`'s
    ``except Exception`` handler entirely: the seam's "always returns 0" invariant
    broke, ``_restore_artifacts`` never ran, and NOT ONE ``::warning`` was printed —
    silent process-exit-1, on exactly the future dated-rename path AMENDMENT §2
    documents will fire (the `store` space has no VMRK answer until the same-id
    refinement carve-out lands, and ANY future dated RenameEvent on a name whose
    committed alias rows are still open-bounded now hits this same conflict).

    Forces it the way the reviewer did: a NEW dated RenameEvent on AAPL (a real
    committed security whose `yahoo`/`membership` alias rows are open-bounded,
    valid_from=valid_to=None) — the fresh build tries to date-split those open rows,
    which collides with the committed open rows under AMENDMENT ruling 6 (M5)'s
    fail-closed law.
    """
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    before = {name: (tmp_path / name).read_bytes() for name in BUILD._NIGHTLY_ARTIFACT_NAMES}
    before_receipt = (tmp_path / BUILD.RECEIPT_NAME).read_bytes()

    fake_event = BUILD.RenameEvent(
        old="AAPL", new="ZZZFUTURENAME", on=date(2099, 1, 1),
        vendors=(BUILD.VENDOR_YAHOO, BUILD.VENDOR_MEMBERSHIP),
        evidence="fixture: forcing a vendor_alias_prune_conflict on a stable security",
    )
    monkeypatch.setattr(BUILD, "RENAME_EVENTS", BUILD.RENAME_EVENTS + (fake_event,))

    assert BUILD.run_nightly_refresh(tmp_path) == 0, (
        "the nightly seam must ALWAYS return 0 — a VendorAliasPruneConflict is a "
        "curation-required refusal, never a crash"
    )
    out = capsys.readouterr().out
    assert "::warning" in out, "a silent escape must never happen again"
    assert "security-master-nightly-prune-conflict" in out, (
        "the DEDICATED warning title, not the generic build-failure one"
    )
    assert "curation required" in out
    for name in BUILD._NIGHTLY_ARTIFACT_NAMES:
        assert (tmp_path / name).read_bytes() == before[name], (
            f"{name} must be byte-restored to last-good"
        )
    assert (tmp_path / BUILD.RECEIPT_NAME).read_bytes() == before_receipt, (
        "generated_at must NOT be re-stamped"
    )


def test_vendor_alias_prune_conflict_is_a_plain_exception_not_systemexit() -> None:
    """The exact defect class, pinned directly: SystemExit is a BaseException
    sibling to Exception and is NEVER caught by `except Exception`."""
    assert issubclass(BUILD.VendorAliasPruneConflict, Exception)
    assert not issubclass(BUILD.VendorAliasPruneConflict, SystemExit)


def test_nightly_refuses_on_a_missing_cik_map_evidence_rail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """V4-D2B1 escape #11 (frozen contract §7 law (a)): ``load_cik_map()`` silently
    degrades to an empty mapping when ``CIK_MAP_DIR`` is missing/empty/unreadable —
    correct for the one-shot ``build()``/``main()`` CLI path (a fresh mint with no CIK
    evidence yet is a valid state), but the nightly refresh calling the SAME ``build()``
    would then regenerate a falsely-fresh artifact where the issuer axis silently mints
    NO_ISSUER_EVIDENCE for every row and the receipt carries no ``notes`` to catch it.
    First establish a last-good baseline, then point CIK_MAP_DIR at a directory that
    does not exist and prove the refresh REFUSES rather than silently regenerating.
    """
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    before = {name: (tmp_path / name).read_bytes() for name in BUILD._NIGHTLY_ARTIFACT_NAMES}
    before_receipt = (tmp_path / BUILD.RECEIPT_NAME).read_bytes()

    capsys.readouterr()  # drop the baseline run's own ::notice
    monkeypatch.setattr(BUILD, "CIK_MAP_DIR", tmp_path / "no-such-cik-map-dir")
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    out = capsys.readouterr().out
    warning_lines = [line for line in out.splitlines() if line.startswith("::warning")]
    assert warning_lines, out
    assert "cik_map" in warning_lines[0]
    for name in BUILD._NIGHTLY_ARTIFACT_NAMES:
        assert (tmp_path / name).read_bytes() == before[name], name
    assert (tmp_path / BUILD.RECEIPT_NAME).read_bytes() == before_receipt, (
        "generated_at must NOT be re-stamped when the CIK evidence rail is missing"
    )


# ── V4-D2B1 FIX 2 (B2/n2) — listing-snapshots rail preflight ────────────────────
def test_nightly_refuses_on_a_missing_symbol_directory_snapshot_rail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """The B2 probe: ``load_directory()`` silently degrades to ``({}, {}, None, None)``
    when ``SYMBOL_DIR_SNAPSHOTS`` is missing/empty — pre-FIX-2 the nightly's required
    rails covered the 5 seed files + the CIK rail but NOT this one, so a nightly run
    over an empty snapshots dir would resolve almost nothing yet still stamp a fresh
    generation and a success ``::notice``. Same pattern as the CIK-map probe above:
    establish a last-good baseline, then point SYMBOL_DIR_SNAPSHOTS at a directory
    that does not exist and prove the refresh REFUSES, byte-identical artifacts.
    """
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    before = {name: (tmp_path / name).read_bytes() for name in BUILD._NIGHTLY_ARTIFACT_NAMES}
    before_receipt = (tmp_path / BUILD.RECEIPT_NAME).read_bytes()

    capsys.readouterr()  # drop the baseline run's own ::notice
    monkeypatch.setattr(BUILD, "SYMBOL_DIR_SNAPSHOTS", tmp_path / "no-such-snapshots-dir")
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    out = capsys.readouterr().out
    warning_lines = [line for line in out.splitlines() if line.startswith("::warning")]
    assert warning_lines, out
    assert "symbol_directory" in warning_lines[0] or "snapshot" in warning_lines[0]
    for name in BUILD._NIGHTLY_ARTIFACT_NAMES:
        assert (tmp_path / name).read_bytes() == before[name], name
    assert (tmp_path / BUILD.RECEIPT_NAME).read_bytes() == before_receipt, (
        "generated_at must NOT be re-stamped when the listing-snapshots rail is missing"
    )


def test_nightly_receipt_names_every_rail_even_when_absent(tmp_path: Path) -> None:
    """FIX 2 (n2): receipt['inputs'] must ALWAYS name every rail key — including the
    listing-snapshots and cik_map directories — never silently drop one because its
    newest file happened to be absent. Proven against the real committed inputs
    (both rails present here), and pinned by name so a future silent-drop regression
    is caught even though this fixture cannot exercise the null-value branch without
    monkeypatching (that shape is covered by the two refusal tests above/below —
    a refused nightly run never reaches receipt construction at all)."""
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    receipt = json.loads((tmp_path / BUILD.RECEIPT_NAME).read_text())
    inputs = receipt["inputs"]
    assert "data/symbol_directory/snapshots" in inputs
    assert "data/symbol_directory/cik_map" in inputs
    assert inputs["data/symbol_directory/snapshots"] is not None
    assert inputs["data/symbol_directory/cik_map"] is not None


# ── V4-D2B1 FIX 2 (B2) — manual build() path hardening ──────────────────────────
def test_manual_build_raises_without_the_flag_on_a_missing_cik_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The B1-amplifier this closes: a manual run on a bare checkout (no
    data/symbol_directory/cik_map at all) would otherwise silently stamp every row
    NO_ISSUER_EVIDENCE. build() now raises IdentityError unless the caller explicitly
    opts out."""
    monkeypatch.setattr(BUILD, "CIK_MAP_DIR", tmp_path / "no-such-cik-map-dir")
    with pytest.raises(IdentityError, match="cik_map"):
        BUILD.build(tmp_path / "out", dry_run=True)

    # The escape hatch works and is explicit.
    receipt = BUILD.build(tmp_path / "out", dry_run=True, allow_missing_evidence=True)
    assert receipt["cik_map_snapshot"] is None


def test_main_allow_missing_evidence_flag_wires_through_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    monkeypatch.setattr(BUILD, "CIK_MAP_DIR", tmp_path / "no-such-cik-map-dir")
    rc = BUILD.main(["--out", str(tmp_path / "out"), "--dry-run", "--allow-missing-evidence"])
    out = capsys.readouterr().out
    assert rc == 0
    assert any(line.startswith("::warning") and "allow-missing-evidence" in line
               for line in out.splitlines()), out

    # Without the flag, main() propagates the raise (no swallow).
    with pytest.raises(IdentityError):
        BUILD.main(["--out", str(tmp_path / "out2"), "--dry-run"])


# ── V4-D2B1 FIX 4 (M2) — mid-build failure restores ALL artifacts ───────────────
def test_nightly_restores_artifacts_on_a_mid_build_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """A failure INSIDE build(), after the FIRST artifact write but before the rest,
    must not leave a torn state: every artifact including the receipt is restored to
    last-good. The first ``_write_parquet`` call (MASTER_NAME) is made to write
    GENUINELY DIFFERENT bytes than the pristine baseline (proving the restore below
    reverts real content, not a no-op), then the SECOND call (ALIASES_NAME) raises.
    """
    assert BUILD.run_nightly_refresh(tmp_path) == 0
    before = {name: (tmp_path / name).read_bytes() for name in BUILD._NIGHTLY_ARTIFACT_NAMES}
    before_receipt = (tmp_path / BUILD.RECEIPT_NAME).read_bytes()
    capsys.readouterr()

    real_write = BUILD._write_parquet
    calls = {"n": 0}

    def flaky_write(rows, columns, path, dtypes):
        calls["n"] += 1
        if calls["n"] == 1:
            mutated = [dict(r) for r in rows]
            if mutated:
                mutated[0] = {**mutated[0], "ingested_at": "1999-01-01T00:00:00"}
            return real_write(mutated, columns, path, dtypes)
        if calls["n"] == 2:
            raise RuntimeError("injected mid-build failure")
        return real_write(rows, columns, path, dtypes)

    monkeypatch.setattr(BUILD, "_write_parquet", flaky_write)

    assert BUILD.run_nightly_refresh(tmp_path) == 0
    out = capsys.readouterr().out
    assert "::warning" in out
    for name in BUILD._NIGHTLY_ARTIFACT_NAMES:
        assert (tmp_path / name).read_bytes() == before[name], name
    assert (tmp_path / BUILD.RECEIPT_NAME).read_bytes() == before_receipt


# ── V4-D2B1 FIX 9 (n3) — era_migrations_total alongside migrations_this_run ─────
def test_receipt_carries_era_migrations_total_alongside_this_run(receipt: dict,
                                                                  issuer_migrations: pd.DataFrame
                                                                  ) -> None:
    """"migrations_this_run: 0" alone cannot be read as "no migrations ever" — the
    receipt must also carry the ALL-TIME count."""
    assert receipt["issuer"]["era_migrations_total"] == len(issuer_migrations)
    assert receipt["issuer"]["era_migrations_total"] >= receipt["issuer"]["migrations_this_run"]


def test_an_unresolved_name_mints_nothing() -> None:
    """A venue this repo cannot evidence produces a REPORT line, never a guessed id."""
    resolutions = [
        BUILD.Resolution("CBOE", None, None, None, "fixture", None,
                         "exchange code 'Z' has no MIC in KNOWN_MICS"),
    ]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-13T00:00:00"
    )
    assert rows == []
    assert ids == {}
    assert notes == []
    assert refusals == []
    assert pending == []
    assert lost == []
    assert BUILD.build_alias_rows(resolutions, ids) == []


# ── V4-D2B2-CN-HK — China/HK canonical identity admission ──────────────────────
# `research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md` is the binding
# spec.  Every fixture below runs against the REAL committed evidence (CNInfo
# `data/china_filings/filings.parquet`, SFC+HKEX `data/hk_shorts/*.parquet`) and the
# REAL committed master/sidecar this PR bakes — the D2A precedent's own law
# ("the suite must run on the real committed parquets — planted-AAPL-only is
# insufficient", handoff §14) extended to this child.

CN_HK_NODES = ROOT / "data" / "theme_graph" / "nodes.parquet"
CN_HK_FILINGS = ROOT / "data" / "china_filings" / "filings.parquet"


@pytest.fixture(scope="module")
def cn_hk_seeds() -> list[dict]:
    return BUILD.load_cn_hk_seeds()


@pytest.fixture(scope="module")
def cninfo_evidence() -> dict:
    evidence, _newest = BUILD.load_cninfo_evidence()
    return evidence


@pytest.fixture(scope="module")
def hk_evidence() -> dict:
    evidence, _newest = BUILD.load_hk_shorts_evidence()
    return evidence


def test_cn_hk_seeds_are_exactly_the_graphs_own_company_population(
    cn_hk_seeds: list[dict],
) -> None:
    """The target population is read from `data/theme_graph/nodes.parquet` (upstream
    graph truth), never the derived sidecar — and it must equal every kind=="company"
    node whose market is cn/hk, with no filtering by current resolution state
    (mint-once idempotency in `mint_cn_hk_rows` is what makes re-passing the full
    population safe on every run)."""
    nodes = pd.read_parquet(CN_HK_NODES)
    company = nodes[nodes["kind"] == "company"]
    expected_cn = set(company.loc[company["market_scope"] == "cn", "node_id"])
    expected_hk = set(company.loc[company["market_scope"] == "hk", "node_id"])
    got_cn = {s["node_id"] for s in cn_hk_seeds if s["market"] == "cn"}
    got_hk = {s["node_id"] for s in cn_hk_seeds if s["market"] == "hk"}
    assert got_cn == expected_cn
    assert got_hk == expected_hk


def test_cn_hk_seeds_symbol_matches_the_nodes_own_suffixed_spelling(
    cn_hk_seeds: list[dict],
) -> None:
    by_node = {s["node_id"]: s["symbol"] for s in cn_hk_seeds}
    assert by_node["co:cn:601398.SS"] == "601398.SS"
    assert by_node["co:hk:1398.HK"] == "1398.HK"


# ── Hostile fixture 1: A/H dual listing (ICBC) ──────────────────────────────────
def test_hostile_ah_dual_listing_icbc_stays_two_securities_no_shared_issuer(
    master: pd.DataFrame,
) -> None:
    """ICBC's A-share (co:cn:601398.SS) and H-share (co:hk:1398.HK) are ONE issuer
    per the spec's worked example (`ISS:CN-XSHG-601398` — never minted here) but
    TWO securities, TWO listings — boundary 6: A/H dual listings remain separate
    securities/listings, sharing an issuer only on deterministic evidence.  This era
    introduces NO CN/HK issuer-evidence class at all (boundary 4), so the two rows
    are never grouped — the safe, disclosed, zero-fabrication outcome."""
    a = master[master["security_id"] == "SEC:CN-XSHG-601398"]
    h = master[master["security_id"] == "SEC:HK-XHKG-01398"]
    assert len(a) == 1 and len(h) == 1
    assert a.iloc[0]["listing_key"] != h.iloc[0]["listing_key"]
    assert a.iloc[0]["security_id"] != h.iloc[0]["security_id"]
    # Never grouped: both null, never coincidentally sharing a fabricated value.
    assert pd.isna(a.iloc[0]["issuer_id"])
    assert pd.isna(h.iloc[0]["issuer_id"])
    assert a.iloc[0]["issuer_state"] == "NO_ISSUER_EVIDENCE"
    assert h.iloc[0]["issuer_state"] == "NO_ISSUER_EVIDENCE"


# ── Hostile fixture 2: renamed security (current-identity-only semantics) ───────
def test_hostile_renamed_security_mints_once_never_two_rows(
    master: pd.DataFrame, cninfo_evidence: dict,
) -> None:
    """sec_code 300223 is REAL disclosed-name-change evidence in the committed
    CNInfo window: "北京君正" through 2026-07-06, renamed to "君正股份" as of
    2026-08-17 (VERIFIED at the D2B2 pin).  `security_master.parquet` has no name
    column at all (boundary 7: current-identity-only, no fabricated historical name
    lineage) — the mint must produce exactly ONE row for this code regardless, and
    `effective_at` must be the EARLIEST dated observation (2026-07-06), never the
    rename date and never a listing date."""
    rows = master[master["inception_code"] == "300223"]
    rows = rows[rows["country"] == "CN"]
    assert len(rows) == 1, "a name change inside the evidence window minted a second row"
    row = rows.iloc[0]
    assert row["security_id"] == "SEC:CN-XSHE-300223"
    assert "legal_name" not in master.columns and "sec_name" not in master.columns
    assert "300223" in cninfo_evidence
    assert cninfo_evidence["300223"]["effective_at"] <= "2026-07-06"


# ── Hostile fixture 3: SOE / naming-collision risk, never fuzzy-grouped ─────────
def test_hostile_soe_naming_collision_never_grouped(master: pd.DataFrame) -> None:
    """Bank of China (601988, "中国银行") and China Pacific Insurance (601601,
    "中国太保") share the "中国" state-enterprise naming prefix a NAME-similarity
    heuristic could wrongly treat as one family — the exact forbidden vocabulary
    (boundary 6: "no name/fuzzy/LLM grouping"; D2B1 issuer law commission §6).  This
    builder consults no name at all for CN/HK issuer identity, so the two rows are
    provably independent: distinct security_id, distinct listing_key, both
    unresolved-issuer (never null-coincidentally-equal, never merged)."""
    boc = master[master["security_id"] == "SEC:CN-XSHG-601988"].iloc[0]
    cpic = master[master["security_id"] == "SEC:CN-XSHG-601601"].iloc[0]
    assert boc["listing_key"] != cpic["listing_key"]
    assert pd.isna(boc["issuer_id"]) and pd.isna(cpic["issuer_id"])
    assert boc["issuer_state"] == cpic["issuer_state"] == "NO_ISSUER_EVIDENCE"


# ── Hostile fixture 4: unresolved issuer ─────────────────────────────────────────
def test_hostile_unresolved_issuer_is_the_uniform_cn_hk_state(master: pd.DataFrame) -> None:
    """Every CN/HK row minted this era carries `issuer_state=NO_ISSUER_EVIDENCE`,
    `issuer_id=None` — no issuer-evidence class exists for CN/HK yet (disclosed
    limitation, boundary 4), so EVERY admitted row demonstrates the "unresolved
    issuer" case, not just a hand-picked one."""
    cn_hk = master[master["country"].isin(["CN", "HK"])]
    assert len(cn_hk) > 1000, "the CN/HK admission did not land"
    assert (cn_hk["issuer_state"] == "NO_ISSUER_EVIDENCE").all()
    assert cn_hk["issuer_id"].isna().all()
    assert cn_hk["issuer_cik"].isna().all()


# ── Hostile fixture 5: alias-only vendor id (the ordinary CN/HK path) ───────────
def test_hostile_alias_only_vendor_id_every_cn_hk_row_has_a_theme_graph_alias(
    master: pd.DataFrame, aliases: pd.DataFrame,
) -> None:
    """`inception_code` is always the BARE code (spec §3.1) and never string-equals
    the GMI node's suffix-qualified `source_native_symbol` — so D2A rule 5 (exact
    inception-code match) can NEVER resolve a CN/HK node; every admission here is
    reached ONLY through a vendor-alias row (`vendor=theme_graph_native`).  This is
    not a hand-picked edge case: it is the universal path for this admission."""
    cn_hk = master[master["country"].isin(["CN", "HK"])]
    theme_graph_aliases = aliases[aliases["vendor"] == "theme_graph_native"]
    assert set(theme_graph_aliases["security_id"]) == set(cn_hk["security_id"])
    # And the exact-match path genuinely would not have worked:
    for _, row in cn_hk.sample(min(25, len(cn_hk)), random_state=0).iterrows():
        alias_row = theme_graph_aliases[theme_graph_aliases["security_id"] == row["security_id"]]
        assert len(alias_row) == 1
        assert alias_row.iloc[0]["vendor_symbol"] != row["inception_code"]
        assert alias_row.iloc[0]["valid_from"] is None or pd.isna(alias_row.iloc[0]["valid_from"])
        assert alias_row.iloc[0]["valid_to"] is None or pd.isna(alias_row.iloc[0]["valid_to"])


# ── Complete accounting (boundary 8: resolved + refused == target N) ────────────
def test_cn_hk_complete_accounting_matches_the_committed_receipt(
    receipt: dict, master: pd.DataFrame,
) -> None:
    block = receipt["china_hk_admission"]
    # resolved_total is CUMULATIVE (mint-once across runs) — only on the very first
    # from-scratch bake does resolved_total == resolved_this_run; the committed
    # receipt this fixture reads is already past that run (a later steady-state
    # regeneration re-derived every prior mint with resolved_this_run=0), so the
    # invariant this test actually pins is the closed-accounting one the D2B2-CN-HK
    # AND D2B2-US contracts both state: resolved_total + refused == target_n.
    for m in ("cn", "hk"):
        assert (block["resolved_total"][m] + block["refused_this_run"][m]
                == block["target_n"][m])
    cn_hk_master = master[master["country"].isin(["CN", "HK"])]
    assert len(cn_hk_master) == block["resolved_total"]["cn"] + block["resolved_total"]["hk"]


def test_cn_hk_admission_is_disclosed_never_asserted_as_completeness(receipt: dict) -> None:
    """A refused CN code is NAMED (boundary 8: no silent drop), and the receipt
    states its evidence sources rather than claiming the admission is exhaustive."""
    block = receipt["china_hk_admission"]
    assert block["refused_this_run"]["cn"] > 0, (
        "the fixture assumes at least one CN code lacks committed CNInfo evidence "
        "in the window — re-check the D2B2 pin if this assertion changes"
    )
    reasons = {r["reason"] for r in block["refusals_this_run"]["cn"]}
    assert reasons <= {"no_committed_primary_source_evidence"} or all(
        r.startswith("unparseable_symbol") or r == "no_committed_primary_source_evidence"
        for r in reasons
    )
    assert "evidence_sources" in block and "cn" in block["evidence_sources"]
    assert "evidence_sources" in block and "hk" in block["evidence_sources"]


# ── Mint-once idempotency, market-scoped (the false-"lost" regression this stage
#    introduced and then fixed — see build()'s existing_us_rows/existing_cn_hk_rows
#    split) ───────────────────────────────────────────────────────────────────
def test_mint_cn_hk_rows_is_idempotent_and_never_re_touches_a_prior_mint() -> None:
    now = "2026-08-20T00:00:00"
    seeds = [{"node_id": "co:cn:600519.SS", "market": "cn", "symbol": "600519.SS"}]
    evidence = {"600519": {"effective_at": "2026-01-01"}}
    rows1, aliases1, cov1 = BUILD.mint_cn_hk_rows([], seeds, evidence, {}, now)
    assert cov1["resolved_this_run"]["cn"] == 1
    assert len(rows1) == 1
    rows2, aliases2, cov2 = BUILD.mint_cn_hk_rows(rows1, seeds, evidence, {}, "2026-08-21T00:00:00")
    assert cov2["resolved_this_run"]["cn"] == 0, "a second run re-minted an already-minted row"
    assert rows2 == rows1
    assert aliases2 == []


def test_mint_cn_hk_rows_refuses_without_silently_dropping() -> None:
    now = "2026-08-20T00:00:00"
    seeds = [
        {"node_id": "co:cn:999999.SS", "market": "cn", "symbol": "999999.SS"},
        {"node_id": "co:hk:1.HK", "market": "hk", "symbol": "1.HK"},
    ]
    rows, aliases, cov = BUILD.mint_cn_hk_rows([], seeds, {}, {}, now)
    assert rows == []
    assert aliases == []
    assert cov["refused_this_run"] == {"cn": 1, "hk": 1}
    assert cov["refusals_this_run"]["cn"][0]["reason"] == "no_committed_primary_source_evidence"
    assert cov["refusals_this_run"]["hk"][0]["reason"] == "no_committed_primary_source_evidence"


def test_mint_cn_hk_rows_types_an_unparseable_symbol_refusal() -> None:
    now = "2026-08-20T00:00:00"
    seeds = [{"node_id": "co:cn:NOTACODE", "market": "cn", "symbol": "NOTACODE"}]
    rows, aliases, cov = BUILD.mint_cn_hk_rows([], seeds, {}, {}, now)
    assert rows == []
    assert cov["refusals_this_run"]["cn"][0]["reason"].startswith("unparseable_symbol")


# ── D2A rule 4 (F1 cross-market equality) is trivially satisfied ────────────────
def test_cn_hk_rows_country_agrees_with_their_own_mic(master: pd.DataFrame) -> None:
    """Every minted CN row is on a CN MIC (XSHG/XSHE/XBSE) and every HK row is on
    XHKG — F1's cross-market guard in the D2A sidecar (§4 amendment) can never fire
    against a row this builder minted, because `listing_key`'s own MIC is derived
    deterministically from the code (`lib.dataos.identity.normalize_cn_symbol` /
    `normalize_hk_symbol`), never declared independently of it."""
    cn_hk = master[master["country"].isin(["CN", "HK"])]
    cn = cn_hk[cn_hk["country"] == "CN"]
    hk = cn_hk[cn_hk["country"] == "HK"]
    assert set(cn["mic"]) <= {"XSHG", "XSHE", "XBSE"}
    assert set(hk["mic"]) <= {"XHKG"}


# ── US existing identity fixtures unchanged (boundary "US existing identity
#    fixtures remain behaviorally unchanged") ────────────────────────────────────
def test_us_coverage_is_unchanged_by_the_cn_hk_admission(receipt: dict) -> None:
    """The CN/HK admission stage runs entirely additively (a SEPARATE US-rows-only
    input to `mint_master_rows`, see build()'s `existing_us_rows` split) — the
    `coverage` block stays scoped to the same legacy curated universe either way
    (`total`/`resolved`/`unresolved` below drift only with that universe's OWN
    seeds — basket membership churn since the CN/HK bake, not CN/HK or D2B2-US;
    VERIFIED an unmodified rebuild at this same pin already reports 712/702/10,
    WBS newly unresolved — a pre-existing, unrelated symbol-directory staleness
    gap).  `issuer.state_counts.RESOLVED` DOES move — the D2B2-US wave (this
    contract) admits ~508 new US securities with CIK-evidenced issuers on top of
    the pre-existing 699."""
    assert receipt["coverage"]["total"] == 712
    assert receipt["coverage"]["resolved"] == 702
    assert receipt["coverage"]["unresolved"] == 10
    assert receipt["issuer"]["state_counts"]["RESOLVED"] >= 699
    assert receipt["security"]["state_counts"]["SUPERSEDED_DUPLICATE_MINT"] == 1


# ── V4-D2B2-US — GMI-U.S. canonical identity admission ─────────────────────────
# research/prophet_v4/d2/D2B2_US_FROZEN_CONTRACT_2026-08-21.md — Sol's second bounded
# child of V4-D2: admit the current source-supported U.S. GMI company population into
# the canonical Data OS security master through the EXISTING resolve_universe()/
# mint_master_rows() pipeline (§0 — deliberately NOT a separate mint stage like
# D2B2-CN-HK, because U.S. targets carry both evidence rails and must hit the R1
# fence structurally).  §9 hostile-case matrix, items 1-16.


def _res(key: str, mic: str, code: str, exchange_symbol: str | None = None,
        venue_source: str | None = "fixture") -> "object":
    """One RESOLVED fixture Resolution — the shape a real directory-matched GMI
    candidate carries going into :func:`BUILD.mint_master_rows`."""
    return BUILD.Resolution(
        key, _lk("US", mic, code), code, exchange_symbol or key, venue_source, None,
    )


# 1-3: structural common-equity eligibility (§3) — a GMI-seeded candidate that
# resolves to a real venue is STILL refused, never minted, when the directory's own
# structural flag says it is not common equity.  Name-substring screening is
# forbidden as a refusal basis (§3 RULING) — every check below reads a flag.
def test_gmi_us_etf_masquerade_refused_never_minted() -> None:
    resolutions = [_res("FAKEETF", "XNAS", "FAKEETF")]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00",
        cik_map={"FAKEETF": ("0001234567", "Fake ETF Sponsor")},
        gmi_admission_targets=frozenset({"FAKEETF"}),
        directory_flags={"FAKEETF": {"etf": True, "test_issue": False, "is_preferred": False}},
    )
    assert rows == []
    assert "FAKEETF" not in ids
    assert [r["code"] for r in gmi_refusals] == ["not_common_equity_etf"]
    assert gmi_refusals[0]["symbol"] == "FAKEETF"


def test_gmi_us_test_issue_refused_never_minted() -> None:
    resolutions = [_res("FAKETEST", "XNAS", "FAKETEST")]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00",
        cik_map={"FAKETEST": ("0001234568", "Fake Test Issuer")},
        gmi_admission_targets=frozenset({"FAKETEST"}),
        directory_flags={"FAKETEST": {"etf": False, "test_issue": True, "is_preferred": False}},
    )
    assert rows == []
    assert "FAKETEST" not in ids
    assert [r["code"] for r in gmi_refusals] == ["not_common_equity_test_issue"]


def test_gmi_us_preferred_refused_never_minted() -> None:
    resolutions = [_res("FAKEPFD", "XNAS", "FAKEPFD")]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00",
        cik_map={"FAKEPFD": ("0001234569", "Fake Preferred Issuer")},
        gmi_admission_targets=frozenset({"FAKEPFD"}),
        directory_flags={"FAKEPFD": {"etf": False, "test_issue": False, "is_preferred": True}},
    )
    assert rows == []
    assert "FAKEPFD" not in ids
    assert [r["code"] for r in gmi_refusals] == ["not_common_equity_preferred"]


# 4: unsupported venue — real committed data, single expected instance (CBOE/Z), and
# the closed MIC list is asserted unchanged (widening it is out of scope, §4/§13).
def test_gmi_us_unsupported_venue_real_data_cboe(receipt: dict) -> None:
    assert BUILD.EXCHANGE_MIC == {"NASDAQ": "XNAS", "N": "XNYS", "A": "XASE"}
    block = receipt["us_gmi_admission"]
    cboe = [r for r in block["refusals_this_run"] if r["symbol"] == "CBOE"]
    assert len(cboe) == 1
    assert cboe[0]["code"] == "unsupported_venue"


# 5: listing present, CIK absent -> no_registrant_cik (fixture — empirically zero
# among today's 533 targets, but the law still ships, §4).
def test_gmi_us_no_registrant_cik_fixture() -> None:
    resolutions = [_res("FAKENOCIK", "XNAS", "FAKENOCIK")]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00",
        cik_map={},  # FAKENOCIK deliberately absent
        gmi_admission_targets=frozenset({"FAKENOCIK"}),
        directory_flags={"FAKENOCIK": {"etf": False, "test_issue": False, "is_preferred": False}},
    )
    assert rows == []
    assert "FAKENOCIK" not in ids
    assert [r["code"] for r in gmi_refusals] == ["no_registrant_cik"]


# 6: CIK present, listing absent -> not_listed_cik_present (real-data EA).
def test_gmi_us_not_listed_cik_present_real_data_ea(receipt: dict) -> None:
    block = receipt["us_gmi_admission"]
    ea = [r for r in block["refusals_this_run"] if r["symbol"] == "EA"]
    assert len(ea) == 1
    assert ea[0]["code"] == "not_listed_cik_present"


# 7: neither rail -> not_listed_no_cik (real-data exemplar from the 21).
def test_gmi_us_not_listed_no_cik_real_data_exemplar(receipt: dict) -> None:
    block = receipt["us_gmi_admission"]
    no_cik = [r for r in block["refusals_this_run"] if r["code"] == "not_listed_no_cik"]
    assert len(no_cik) >= 1
    assert "STKL" in {r["symbol"] for r in no_cik}


# 8: ambiguous ticker -> CIK -> ambiguous_registrant (fixture forcing the
# ambiguous_tickers path — load_cik_map() itself removes an ambiguous ticker from
# the mapping, so a candidate hitting it is typed even though `cik_map` is blind).
def test_gmi_us_ambiguous_registrant_fixture() -> None:
    resolutions = [_res("FAKEAMBIG", "XNAS", "FAKEAMBIG")]
    rows, ids, notes, refusals, pending, lost, exc_lost, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00",
        cik_map={},  # load_cik_map() already popped an ambiguous ticker out of here
        gmi_admission_targets=frozenset({"FAKEAMBIG"}),
        directory_flags={"FAKEAMBIG": {"etf": False, "test_issue": False, "is_preferred": False}},
        ambiguous_tickers=frozenset({"FAKEAMBIG"}),
    )
    assert rows == []
    assert "FAKEAMBIG" not in ids
    assert [r["code"] for r in gmi_refusals] == ["ambiguous_registrant"]


# 9: reused ticker / pending-transition via the GMI seed path — NO new law (§4): the
# candidate hits the unchanged R1 fence and the refusal surfaces in the GMI
# accounting under its EXISTING typed reason, never a silent mint or drop.
# AMENDMENT R8 — exercises the REAL build() accounting path end to end (no
# re-implemented classification loop in the test body).
def test_gmi_us_pending_transition_fence_surfaces_in_gmi_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    existing_rows = [{
        "security_id": "SEC:US-XNYS-OLDCO", "issuer_id": None,
        "issuer_state": "RESOLVED", "issuer_cik": "0009000001",
        "issuer_evidence_snapshot": "2026-08-18", "listing_key": "US-XNYS-OLDCO",
        "country": "US", "mic": "XNYS", "inception_code": "OLDCO",
        "effective_at": "2020-01-01T00:00:00", "ingested_at": "2020-01-01T00:00:00",
        "security_state": None, "superseded_by": None,
    }]
    BUILD._write_parquet(existing_rows, BUILD.MASTER_COLUMNS,
                         out_dir / BUILD.MASTER_NAME, BUILD.MASTER_DTYPES)

    # Neither OLDCO nor NEWGMI is a legacy-curated key (empty universe) — OLDCO is
    # not re-derived this run (unaccounted -> the fence's `lost_rows`), and NEWGMI
    # is a GMI-only listing-key MISS with no independent CIK evidence -> the fence
    # refuses it (§5.2), exactly like a legacy candidate would.
    monkeypatch.setattr(BUILD, "load_universe", lambda: {})
    monkeypatch.setattr(BUILD, "load_delisted", lambda: {})
    monkeypatch.setattr(
        BUILD, "load_directory",
        lambda: ({"NEWGMI": "NASDAQ"},
                 {"NEWGMI": {"etf": False, "test_issue": False, "is_preferred": False}},
                 "2026-08-21", None),
    )
    monkeypatch.setattr(BUILD, "load_cik_map", lambda: ({}, None, None, frozenset()))
    monkeypatch.setattr(BUILD, "load_config_maps", lambda: ({}, {}))
    monkeypatch.setattr(
        BUILD, "load_gmi_us_seeds",
        lambda: [{"symbol": "NEWGMI", "node_id": "co:us:NEWGMI"}],
    )

    receipt = BUILD.build(out_dir, allow_missing_evidence=True)

    assert receipt["pending_transition_refusals"], "the fence must have fired"
    assert receipt["pending_transition_refusals"][0]["symbol"] == "NEWGMI"
    block = receipt["us_gmi_admission"]
    newgmi = [r for r in block["refusals_this_run"] if r["symbol"] == "NEWGMI"]
    assert len(newgmi) == 1
    assert newgmi[0]["code"] == "pending_transition_fence"
    # OLDCO carried forward unchanged (mint-once) — never re-minted, never dropped.
    master = pd.read_parquet(out_dir / BUILD.MASTER_NAME)
    oldco = master[master["security_id"] == "SEC:US-XNYS-OLDCO"]
    assert len(oldco) == 1


# 10: new clean IPO fixture -> mints once; a second run re-derives, never re-mints.
def test_gmi_us_new_clean_ipo_mints_once() -> None:
    resolutions = [_res("FAKEIPO", "XNAS", "FAKEIPO")]
    cik_map = {"FAKEIPO": ("0001234570", "Fake IPO Co")}
    flags = {"FAKEIPO": {"etf": False, "test_issue": False, "is_preferred": False}}
    targets = frozenset({"FAKEIPO"})

    rows1, ids1, *_r1, gmi1 = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00", cik_map=cik_map,
        gmi_admission_targets=targets, directory_flags=flags,
    )
    assert gmi1 == []
    assert len(rows1) == 1 and rows1[0]["security_id"] == "SEC:US-XNAS-FAKEIPO"
    minted_id = ids1["FAKEIPO"]

    rows2, ids2, *_r2, gmi2 = BUILD.mint_master_rows(
        resolutions, rows1, "2026-08-22T00:00:00", cik_map=cik_map,
        gmi_admission_targets=targets, directory_flags=flags,
    )
    assert gmi2 == []
    assert ids2["FAKEIPO"] == minted_id, "a second run re-minted an already-minted row"
    # Byte-stable modulo the `_existed_before` in-memory marker (row1's mint carries
    # none; row2's re-derivation of that same row carries it — never a declared
    # column, never written to parquet, see mint_master_rows' own docstring).
    strip = lambda rows: [{k: v for k, v in r.items() if k != "_existed_before"} for r in rows]
    assert strip(rows2) == strip(rows1), "re-derivation must be byte-stable, never a re-mint"


# 11: class shares — two GMI codes share ONE CIK and both list -> TWO securities
# (never collapsed to one), and issuer grouping happens ONLY where the EXISTING
# allowlist-gated law already allows it (§5: "no allowlist additions this wave") — a
# brand-new multi-member group on an un-allowlisted CIK is EVIDENCE_CONFLICT, not a
# fabricated group.
def test_gmi_us_class_shares_two_securities_issuer_grouping_per_existing_law() -> None:
    resolutions = [
        _res("FAKECLA", "XNAS", "FAKECLA"),
        _res("FAKECLB", "XNAS", "FAKECLB"),
    ]
    cik_map = {"FAKECLA": ("0001234571", "Fake Class Co"),
               "FAKECLB": ("0001234571", "Fake Class Co")}
    flags = {"FAKECLA": {"etf": False, "test_issue": False, "is_preferred": False},
             "FAKECLB": {"etf": False, "test_issue": False, "is_preferred": False}}
    targets = frozenset({"FAKECLA", "FAKECLB"})
    rows, ids, *_r, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00", cik_map=cik_map,
        gmi_admission_targets=targets, directory_flags=flags,
    )
    assert gmi_refusals == []
    assert {r["security_id"] for r in rows} == {"SEC:US-XNAS-FAKECLA", "SEC:US-XNAS-FAKECLB"}

    out_rows, migrations = BUILD.apply_issuer_correction(
        rows, cik_map, "2026-08-21", "2026-08-21T00:00:00",
        allowlist=frozenset(),  # no allowlist additions this wave — a REAL empty gate
    )
    by_id = {r["security_id"]: r for r in out_rows}
    assert by_id["SEC:US-XNAS-FAKECLA"]["issuer_state"] == "EVIDENCE_CONFLICT"
    assert by_id["SEC:US-XNAS-FAKECLB"]["issuer_state"] == "EVIDENCE_CONFLICT"
    assert migrations == []


# 12: same-CIK sponsor/trust pair (common + ETF) — the ETF is refused at the MINT
# decision (never becomes a row), so the common security settles as a lone,
# UNGATED single-member group — no issuer is ever fabricated for the refused ETF,
# because there is no row to fabricate one onto.
def test_gmi_us_same_cik_sponsor_trust_pair_common_mints_etf_refused() -> None:
    resolutions = [
        _res("FAKECOM", "XNAS", "FAKECOM"),
        _res("FAKEETFPAIR", "XNAS", "FAKEETFPAIR"),
    ]
    cik_map = {"FAKECOM": ("0001234572", "Fake Sponsor Trust"),
               "FAKEETFPAIR": ("0001234572", "Fake Sponsor Trust")}
    flags = {"FAKECOM": {"etf": False, "test_issue": False, "is_preferred": False},
             "FAKEETFPAIR": {"etf": True, "test_issue": False, "is_preferred": False}}
    targets = frozenset({"FAKECOM", "FAKEETFPAIR"})
    rows, ids, *_r, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00", cik_map=cik_map,
        gmi_admission_targets=targets, directory_flags=flags,
    )
    assert [r["symbol"] for r in gmi_refusals] == ["FAKEETFPAIR"]
    assert {r["security_id"] for r in rows} == {"SEC:US-XNAS-FAKECOM"}

    out_rows, migrations = BUILD.apply_issuer_correction(
        rows, cik_map, "2026-08-21", "2026-08-21T00:00:00", allowlist=frozenset(),
    )
    assert out_rows[0]["issuer_state"] == "RESOLVED", (
        "a single-member group is ungated — no fabricated relationship to the "
        "refused ETF is possible, because it was never minted"
    )
    assert out_rows[0]["issuer_id"] == "ISS:US-XNAS-FAKECOM"


# 13: LP common unit (real-data) — pins the §3 RULING: the six LP common-unit
# issuers are admissible through the SAME structural gates as every other candidate
# (all-false flags, registrant CIK present), never refused by name.
def test_gmi_us_lp_common_unit_mints_real_data(master: pd.DataFrame) -> None:
    for lp in ("ARLP", "BEP", "CQP", "ET", "UAN", "XIFR"):
        rows = master[(master["inception_code"] == lp) & (master["country"] == "US")]
        assert len(rows) == 1, f"{lp} must mint exactly one active US security"
        assert not rows.iloc[0]["security_state"] or pd.isna(rows.iloc[0]["security_state"])


# AMENDMENT R5 — a GMI-only candidate resolved via the EXIT LEDGER is eligibility-
# EXEMPT BY LAW: no structural-flag check runs at all (there is no directory row
# to consult), so it mints even with no `directory_flags` entry whatsoever.
def test_r5_exit_ledger_resolved_candidate_is_eligibility_exempt() -> None:
    resolutions = [
        BUILD.Resolution(
            "FAKEDELISTED", _lk("US", "XNYS", "FAKEDELISTED"), "FAKEDELISTED",
            None,  # exchange_symbol=None -> resolved via the exit ledger, not the directory
            "config/delisted_symbols.yml:FAKEDELISTED.exchange=NYSE", None,
        ),
    ]
    rows, ids, *_r, gmi_refusals = BUILD.mint_master_rows(
        resolutions, [], "2026-08-21T00:00:00",
        cik_map={"FAKEDELISTED": ("0001234573", "Fake Delisted Co")},
        gmi_admission_targets=frozenset({"FAKEDELISTED"}),
        directory_flags={},  # deliberately EMPTY — no directory row exists for a delisted name
    )
    assert gmi_refusals == []
    assert "FAKEDELISTED" in ids
    assert {r["security_id"] for r in rows} == {"SEC:US-XNYS-FAKEDELISTED"}


# AMENDMENT R5 — a DIRECTORY-resolved candidate MISSING a `directory_flags` entry
# is a hard fail-closed error, never a silent skip (a desync between `directory`
# and `directory_flags` — both built from the same snapshot row — is a bug worth
# crashing on).
def test_r5_directory_resolved_candidate_missing_flags_hard_fails() -> None:
    resolutions = [_res("FAKENOFLAGS", "XNAS", "FAKENOFLAGS")]
    with pytest.raises(IdentityError, match="structural-flags entry"):
        BUILD.mint_master_rows(
            resolutions, [], "2026-08-21T00:00:00",
            cik_map={"FAKENOFLAGS": ("0001234574", "Fake No-Flags Co")},
            gmi_admission_targets=frozenset({"FAKENOFLAGS"}),
            directory_flags={},  # desynced — FAKENOFLAGS resolved via directory but has no entry
        )


# AMENDMENT R12 — a venue-resolved candidate whose ListingKey construction itself
# fails (a malformed inception code) is typed `unrenderable_code`, never
# conflated with the (mic-found-but-unmapped) `unsupported_venue` class.
def test_r12_unrenderable_code_distinct_from_unsupported_venue() -> None:
    res = BUILD.Resolution(
        "FAKEBADCODE", None, None, "FAKEBADCODE",
        "data/symbol_directory/snapshots/2026-08-21.parquet:FAKEBADCODE.exchange=NASDAQ",
        None, "ListingKey code must match ^[A-Z0-9.]{1,10}$: got '???'",
    )
    refusal = BUILD._gmi_us_unresolved_refusal(res, {})
    assert refusal["code"] == "unrenderable_code"
    assert refusal["code"] != "unsupported_venue"

    unmapped = BUILD.Resolution(
        "FAKEZVENUE", None, None, None,
        "data/symbol_directory/snapshots/2026-08-21.parquet:FAKEZVENUE.exchange=Z",
        None, "listed on exchange code 'Z' ... which has no MIC in lib/dataos/identity.KNOWN_MICS",
    )
    assert BUILD._gmi_us_unresolved_refusal(unmapped, {})["code"] == "unsupported_venue"


# 14: accounting completeness — the R2 THREE-WAY invariant (resolved + refused +
# disclosed_exclusions == target_n), identity-exception disclosure, and zero
# unaccounted targets, against the COMMITTED receipt (real data).  AMENDMENT R2:
# `target_n` is now the FULL GMI-U.S. population (legacy overlap included), and
# the partition gained a THIRD bucket (`disclosed_exclusions`, R3's duplicate-
# claim collapse) — this test pins the CORRECTED, standing invariant.
def test_gmi_us_accounting_completeness_real_data(receipt: dict) -> None:
    block = receipt["us_gmi_admission"]
    assert (block["resolved_total"] + block["refused_this_run"]
            + len(block["disclosed_exclusions"])) == block["target_n"]
    assert len(block["refusals_this_run"]) == block["refused_this_run"]
    excluded_codes = {e["code"] for e in block["identity_exception_excluded"]}
    assert "B" in excluded_codes
    assert "GOLD" in excluded_codes
    # Every named refusal carries a non-empty typed code and reason (no silent drop).
    for r in block["refusals_this_run"]:
        assert r["symbol"] and r["code"] and r["reason"]
    # Every disclosed exclusion names a winning claimant with a real minted id.
    for d in block["disclosed_exclusions"]:
        assert d["symbol"] and d["winning_symbol"] and d["reason"]
        assert d["winning_security_id"], (
            f"{d['symbol']!r} discloses a winner {d['winning_symbol']!r} that "
            "never actually minted — the collapse must never point at nothing"
        )
    # The refusal closed set (§3/§4 + AMENDMENT R12) — every code observed today
    # must be a member; a new, unlisted code here would mean an unclassified
    # refusal class slipped through.
    closed_refusal_codes = {
        "not_common_equity_etf", "not_common_equity_test_issue",
        "not_common_equity_preferred", "unsupported_venue", "unrenderable_code",
        "no_registrant_cik", "ambiguous_registrant", "not_listed_cik_present",
        "not_listed_no_cik", "resurrection_refusal", "pending_transition_fence",
    }
    observed_codes = {r["code"] for r in block["refusals_this_run"]}
    assert observed_codes <= closed_refusal_codes, observed_codes - closed_refusal_codes


# 15: regression pins — CN 984 + HK 147 + the pre-existing 705 US rows byte-identical
# after the expansion run; legacy `coverage` block semantics unchanged (712-scope).
def test_gmi_us_regression_pins_cn_hk_and_legacy_us_unchanged(
    master: pd.DataFrame, receipt: dict,
) -> None:
    assert len(master[master["country"] == "CN"]) == 984
    assert len(master[master["country"] == "HK"]) == 147
    assert receipt["coverage"]["total"] == 712
    assert receipt["coverage"]["resolved"] == 702
    assert receipt["coverage"]["unresolved"] == 10


# 16: idempotency + run-2 stability — AMENDMENT R9 corrected law.  §8/§9.16's
# original "fence fired zero times on run 2" was wrongly phrased: the pin's own
# steady state carries `listing_continuity: [WBS, GOLD-identity-exception]` (WBS
# is a pre-existing, unrelated symbol-directory staleness gap — VERIFIED present
# on an unmodified rebuild at this pin, §9 item 4/6/7's own real-data fixtures).
# The CORRECT law: run 2's `listing_continuity` is IDENTICAL to run 1's (the
# expected steady set, not empty), zero pending-transition/resurrection
# refusals, `resolved_this_run == 0`, byte-identical artifacts.
def test_gmi_us_idempotent_run_2_stability_real_data(tmp_path: Path) -> None:
    shutil.copy(MASTER_PATH, tmp_path / BUILD.MASTER_NAME)
    shutil.copy(ALIASES_PATH, tmp_path / BUILD.ALIASES_NAME)
    issuer_master = ROOT / "data" / "reference" / BUILD.ISSUER_MASTER_NAME
    issuer_migrations = ROOT / "data" / "reference" / BUILD.ISSUER_MIGRATIONS_NAME
    security_migrations = ROOT / "data" / "reference" / BUILD.SECURITY_MIGRATIONS_NAME
    for src in (issuer_master, issuer_migrations, security_migrations):
        if src.exists():
            shutil.copy(src, tmp_path / src.name)

    run1 = BUILD.build(tmp_path)
    before_master = (tmp_path / BUILD.MASTER_NAME).read_bytes()
    before_aliases = (tmp_path / BUILD.ALIASES_NAME).read_bytes()

    run2 = BUILD.build(tmp_path)
    after_master = (tmp_path / BUILD.MASTER_NAME).read_bytes()
    after_aliases = (tmp_path / BUILD.ALIASES_NAME).read_bytes()

    assert after_master == before_master
    assert after_aliases == before_aliases
    # R9: run 2's steady-state listing_continuity is IDENTICAL to run 1's own
    # (self-consistent, R10 — never hardcode the exact WBS/GOLD shape here; the
    # dedicated real-data fixtures elsewhere already pin that shape).
    assert run2["listing_continuity"] == run1["listing_continuity"]
    assert run1["listing_continuity"], (
        "this pin is known to carry a non-empty steady-state listing_continuity "
        "(WBS + the GOLD identity exception) — an empty list here means the "
        "fixture assumption drifted, not that the law changed"
    )
    assert run2["pending_transition_refusals"] == []
    assert run2["resurrection_refusals"] == []
    gmi1, gmi2 = run1["us_gmi_admission"], run2["us_gmi_admission"]
    assert gmi2["resolved_this_run"] == 0
    assert gmi2["refusals_this_run"] == gmi1["refusals_this_run"]
    assert gmi2["resolved_total"] == gmi1["resolved_total"]
    assert gmi2["disclosed_exclusions"] == gmi1["disclosed_exclusions"]
    assert gmi2["target_n"] == gmi1["target_n"]


# AMENDMENT R3 fixture — the reviewer's NEWA/NEWAOLD counterexample: two GMI-only
# codes sharing a rename-chain root collide on a BRAND-NEW listing key (never
# pre-existing) — the v1 duplicate-claim guard only inspected pre-existing keys
# and would have let BOTH claimants reach build_alias_rows, which
# VendorAliasTable's own uniqueness law would then fail-closed refuse.  This
# proves the corrected law: build() completes, exactly one row mints, the loser
# is a named disclosure, and the R2 invariant holds.
def test_r3_newa_newaold_same_root_new_key_build_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    monkeypatch.setattr(BUILD, "load_universe", lambda: {})
    monkeypatch.setattr(BUILD, "load_delisted", lambda: {})
    monkeypatch.setattr(
        BUILD, "load_directory",
        lambda: (
            {"NEWA": "NASDAQ", "NEWAOLD": "NASDAQ"},
            {"NEWA": {"etf": False, "test_issue": False, "is_preferred": False},
             "NEWAOLD": {"etf": False, "test_issue": False, "is_preferred": False}},
            "2026-08-21", None,
        ),
    )
    monkeypatch.setattr(
        BUILD, "load_cik_map",
        lambda: (
            {"NEWA": ("0009999999", "New Root Co")}, "2026-08-21", None, frozenset(),
        ),
    )
    monkeypatch.setattr(BUILD, "load_config_maps", lambda: ({}, {}))
    monkeypatch.setattr(
        BUILD, "load_gmi_us_seeds",
        lambda: [
            {"symbol": "NEWA", "node_id": "co:us:NEWA"},
            {"symbol": "NEWAOLD", "node_id": "co:us:NEWAOLD"},
        ],
    )
    # NEWAOLD -> NEWA: an undated rename chain, so both codes' inception_code
    # walks resolve to the SAME root ("NEWAOLD") and therefore the SAME rendered
    # listing key — the exact reviewer counterexample shape, on a key neither
    # side has ever minted before.
    monkeypatch.setattr(BUILD, "UNDATED_RENAMES", (("NEWAOLD", "NEWA", "test fixture"),))

    receipt = BUILD.build(out_dir, allow_missing_evidence=True)  # must not crash

    master = pd.read_parquet(out_dir / BUILD.MASTER_NAME)
    us_new = master[master["inception_code"] == "NEWAOLD"]
    assert len(us_new) == 1, "exactly one row must mint for the collapsed pair"

    block = receipt["us_gmi_admission"]
    disclosed = {d["symbol"]: d for d in block["disclosed_exclusions"]}
    assert "NEWAOLD" in disclosed
    assert "NEWA" not in disclosed
    assert disclosed["NEWAOLD"]["winning_symbol"] == "NEWA"
    assert disclosed["NEWAOLD"]["winning_security_id"] == us_new.iloc[0]["security_id"]
    assert (block["resolved_total"] + block["refused_this_run"]
            + len(block["disclosed_exclusions"])) == block["target_n"]

    aliases = pd.read_parquet(out_dir / BUILD.ALIASES_NAME)  # must not have crashed
    assert not aliases.empty


# AMENDMENT R4(a) — from-EMPTY composition test.  R1's blocker fix: the §3/§4
# eligibility+CIK gate must NEVER touch a legacy-curated key, regardless of
# master state.  A from-scratch rebuild (no pre-run master to match a candidate
# against) is exactly the shape that exposed the v1 bug — AEP/CTRA/EQR/FI/FISV
# were wrongly refused, and ETHA/IBIT (curated ETFs) were wrongly gated on the
# structural-flag law that only applies to GMI-ONLY targets.
def test_r4a_from_empty_build_mints_legacy_gmi_overlap_codes(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    receipt = BUILD.build(out_dir, allow_missing_evidence=True)  # must not raise

    master = pd.read_parquet(out_dir / BUILD.MASTER_NAME)
    us_codes = set(master[master["country"] == "US"]["inception_code"])
    # AEP/CTRA/EQR: legacy keys with a real GMI seed twin — must mint regardless
    # of missing CIK evidence (AEP) or any structural flag (none of these are
    # ETFs, but the POINT is the gate never even runs for them).
    for code in ("AEP", "CTRA", "EQR"):
        assert code in us_codes, f"{code} must mint on a from-empty rebuild (R1)"
    # FI/FISV: the undated-rename chain collapses to ONE row at the shared root
    # (R3) — the root code itself must mint (test_fi_and_fisv_resolve_to_the_
    # same_security in test_theme_graph_identity_resolution.py pins the sidecar
    # side of this same fact).
    assert "FISV" in us_codes
    # ETHA/IBIT: curated ETFs — must mint DESPITE etf=True, because they are
    # legacy keys and R1's gate is GMI-only.
    for code in ("ETHA", "IBIT"):
        assert code in us_codes, (
            f"{code} is a curated ETF seed — it must mint on a from-empty "
            "rebuild; a missing row here means the eligibility gate wrongly "
            "caught a legacy key (R1 regression)"
        )
    block = receipt["us_gmi_admission"]
    assert (block["resolved_total"] + block["refused_this_run"]
            + len(block["disclosed_exclusions"])) == block["target_n"]


# AMENDMENT R4(b) — seeded-from-pin-baseline transition test.  The historical
# pre-D2B2-US master bytes are not separately committed (this contract's own
# canonical regeneration overwrote them, R7), so the baseline is reconstructed
# DETERMINISTICALLY from data the repo already carries: every committed US row
# whose `inception_code` is a GMI-ONLY (non-legacy) admission target is exactly
# what THIS wave admitted — stripping those rows and rebuilding reproduces the
# transition this contract's own bake performed, self-consistently (R10).
def test_r4b_transition_from_pin_baseline_matches_r2_shape(
    tmp_path: Path, master: pd.DataFrame, aliases: pd.DataFrame,
) -> None:
    legacy_keys = frozenset(BUILD.load_universe()) | frozenset(BUILD.load_delisted())
    gmi_seed_codes = frozenset(s["symbol"] for s in BUILD.load_gmi_us_seeds())
    identity_exc = frozenset(BUILD.DEFERRED_IDENTITY_KEYS) | frozenset(
        BUILD.DISCLOSED_IDENTITY_EXCEPTIONS)
    gmi_only_targets = gmi_seed_codes - legacy_keys - identity_exc
    assert gmi_only_targets, "fixture stale — no GMI-only targets left to strip"

    candidate = master[
        (master["country"] == "US")
        & master["inception_code"].isin(gmi_only_targets)
        & master["security_state"].isna()
    ]
    assert not candidate.empty, "fixture stale — nothing to strip from the baseline"
    # A GMI-only-target STRING can incidentally match a row that predates this
    # wave entirely (a stale duplicate graph node sharing a rename-chain root
    # with an already-legacy-minted security — co:us:SATS beside the legacy-
    # minted co:us:ECHO row, both rooted at inception_code="SATS"; SATS itself
    # is NOT a legacy key, so the string match alone cannot tell it apart from a
    # genuine admission).  Every ROW this wave actually minted shares ONE batch
    # `ingested_at` stamp (one `build()` call, one `now`); isolate that stamp
    # rather than trusting the code-string match alone.
    batch_stamp = candidate["ingested_at"].mode().iloc[0]
    is_gmi_only_admission_row = candidate["ingested_at"] == batch_stamp
    stripped_count = int(is_gmi_only_admission_row.sum())
    assert stripped_count > 0, "fixture stale — could not isolate the admission batch"
    stripped_ids = frozenset(candidate.loc[is_gmi_only_admission_row, "security_id"])
    baseline_master = master[~master["security_id"].isin(stripped_ids)].reset_index(drop=True)
    baseline_aliases = aliases[~aliases["security_id"].isin(stripped_ids)].reset_index(drop=True)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    baseline_master.to_parquet(out_dir / BUILD.MASTER_NAME, index=False)
    baseline_aliases.to_parquet(out_dir / BUILD.ALIASES_NAME, index=False)

    receipt = BUILD.build(out_dir)
    block = receipt["us_gmi_admission"]
    # Self-consistent (R10): the codes stripped are exactly the codes this run
    # must re-mint — every one of them should resolve back (nothing else in the
    # environment changed), so resolved_this_run reproduces the strip count.
    assert block["resolved_this_run"] == stripped_count
    assert block["refused_this_run"] == len(block["refusals_this_run"])
    assert (block["resolved_total"] + block["refused_this_run"]
            + len(block["disclosed_exclusions"])) == block["target_n"]
    # The named refusal SYMBOLS reproduce the committed receipt's own current
    # steady-state refusal set (R10 — cross-artifact consistency, never a
    # hardcoded literal count).
    committed_receipt = json.loads(RECEIPT_PATH.read_text())
    committed_symbols = {
        r["symbol"] for r in committed_receipt["us_gmi_admission"]["refusals_this_run"]
    }
    rebuilt_symbols = {r["symbol"] for r in block["refusals_this_run"]}
    assert rebuilt_symbols == committed_symbols
