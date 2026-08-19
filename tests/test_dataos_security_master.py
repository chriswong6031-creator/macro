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

    # Mint-once: a second pass never re-examines an AMBIGUOUS row.
    again_rows, again_migrations = BUILD.apply_issuer_correction(
        out_rows, {}, "2026-08-19", now, ambiguous_tickers=frozenset({"DUP"}))
    assert again_rows == out_rows
    assert again_migrations == []


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
    first = out.splitlines()[0]
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
    """The B2 probe: ``load_directory()`` silently degrades to ``({}, None, None)``
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
    rows, ids, notes = BUILD.mint_master_rows(resolutions, [], "2026-08-13T00:00:00")
    assert rows == []
    assert ids == {}
    assert notes == []
    assert BUILD.build_alias_rows(resolutions, ids) == []
