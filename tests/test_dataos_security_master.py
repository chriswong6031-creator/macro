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
    rows = master.set_index("security_id")
    for security, mic, code in ((MMC_ID, "XNYS", "MMC"), (SATS_ID, "XNAS", "SATS")):
        assert security in rows.index, f"{security} missing from the committed master"
        row = rows.loc[security]
        assert row["mic"] == mic
        assert row["inception_code"] == code
        assert row["issuer_id"] == security.replace("SEC:", "ISS:")
        assert row["listing_key"] == security.replace("SEC:", "")
    # Neither of today's symbols may have minted an id of its own.
    assert "SEC:US-XNYS-MRSH" not in rows.index
    assert "SEC:US-XNAS-ECHO" not in rows.index


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
