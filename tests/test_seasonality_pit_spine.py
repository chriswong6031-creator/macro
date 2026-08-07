"""W1A/W1C — the point-in-time universe read adapter and its honest unavailables.

The store this adapter reads is three weeks deep and the panel it serves is
twenty-five years deep, so most of these tests assert an UNAVAILABLE rather than
a value.  That is deliberate: an adapter that quietly returned today's ticker
for a 2015 query would be the exact backward identity leak the program forbids,
and it would pass any test suite that only checked the happy path.

The synthetic store is built in ``tmp_path`` (the house pattern from
``tests/test_stock_seasonality_engine.py``) so nothing here depends on the
committed ``data/`` tree; one structural test reads the real store if it exists
and skips cleanly if it does not.
"""
from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.seasonality import universe

ROOT = Path(__file__).resolve().parents[1]
REAL_SNAPSHOTS = ROOT / universe.SNAPSHOT_SUBPATH

# The four limitations the ownership registry actually declares.  Deliberate
# cross-file tripwire: editing
# ``config/sector_intelligence_ownership.yml:registrations.security_identity_and_corporate_actions.limitations``
# reddens this suite, because the adapter's coverage claims are that entry read
# verbatim and a silent registry edit would silently change what the panel
# claims it can answer.
REGISTERED_LIMITATIONS = (
    "us_exchange_roster_only",
    "incomplete_corporate_action_history",
    "no_private_companies",
    "no_global_security_master",
)


# --- synthetic store --------------------------------------------------------


def _write_registry(root: Path, *, limitations=REGISTERED_LIMITATIONS) -> None:
    """Materialise the ownership registry entry the adapter reads."""
    path = root / universe.REGISTRY_SUBPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "sector_intelligence_ownership.v1",
        universe.REGISTRY_SECTION: {
            universe.REGISTRY_KEY: {
                "canonical_owner": "market_data_security_master",
                "implementation_state": "bootstrap_only_not_registered_as_complete_master",
                "writer": {
                    "module": "collectors.symbol_directory",
                    "storage_class": "private_point_in_time_snapshots",
                    "schema": universe.SNAPSHOT_SCHEMA,
                },
                "limitations": list(limitations),
            }
        },
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _row(symbol: str, name: str, **overrides) -> dict:
    row = {
        "symbol": symbol,
        "security_name": name,
        "exchange": "NASDAQ",
        "etf": False,
        "test_issue": False,
        "is_preferred": False,
        "source": "nasdaqlisted",
    }
    row.update(overrides)
    return row


def _write_snapshots(root: Path, rows_by_date: dict[str, list[dict]]) -> None:
    store = root / universe.SNAPSHOT_SUBPATH
    store.mkdir(parents=True, exist_ok=True)
    for day, rows in rows_by_date.items():
        frame = pd.DataFrame([dict(row, date=day) for row in rows])
        frame.to_parquet(store / f"{day}.parquet")


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """A four-snapshot roster carrying every acceptance case at once.

    * ``OLDCO`` → ``NEWCO``: a rename on 2026-03-01, no stable id to link them.
    * ``GONECO``: acquired away after 2026-02-01 — historical membership only.
    * ``GAPCO``: listed, absent for one snapshot, listed again — a listing gap.
    * ``DUALA``/``DUALB``: two share classes of one issuer, unlinkable.
    * ``SHELLCO``: a dormant shell, kept, because there is no liquidity column.
    * ``TESTCO``/``PFDCO``: structurally excluded from membership by declared rule.
    """
    _write_registry(tmp_path)
    common = [
        _row("DUALA", "Dual Issuer Inc. - Class A Common Stock"),
        _row("DUALB", "Dual Issuer Inc. - Class B Common Stock"),
        _row("SHELLCO", "Dormant Shell Corp. - Common Stock"),
        _row("TESTCO", "NASDAQ TEST STOCK", test_issue=True),
        _row("PFDCO", "Preferred Issuer Inc. - 6.5% Series A Preferred", is_preferred=True),
    ]
    _write_snapshots(
        tmp_path,
        {
            "2026-02-01": common
            + [
                _row("OLDCO", "Old Name Therapeutics Inc. - Common Stock"),
                _row("GONECO", "Acquired Bio Inc. - Common Stock"),
                _row("GAPCO", "Gap Listing Inc. - Common Stock"),
            ],
            "2026-03-01": common
            + [
                _row("NEWCO", "New Name Therapeutics Inc. - Common Stock"),
            ],
            "2026-04-01": common
            + [
                _row("NEWCO", "New Name Therapeutics Inc. - Common Stock"),
                _row("GAPCO", "Gap Listing Inc. - Common Stock"),
            ],
            "2026-05-01": common
            + [
                _row("NEWCO", "New Name Therapeutics Inc. - Common Stock"),
                _row("GAPCO", "Gap Listing Inc. - Common Stock"),
            ],
        },
    )
    return tmp_path


# --- store enumeration ------------------------------------------------------


def test_snapshot_dates_are_sorted_and_ignore_unparseable_names(store: Path):
    (store / universe.SNAPSHOT_SUBPATH / "latest.parquet").write_bytes(b"")
    (store / universe.SNAPSHOT_SUBPATH / "2026-13-99.parquet").write_bytes(b"")
    assert universe.snapshot_dates(store) == [
        date(2026, 2, 1),
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
    ]
    assert universe.earliest_snapshot(store) == date(2026, 2, 1)


def test_an_empty_store_has_no_earliest_and_answers_nothing(tmp_path: Path):
    _write_registry(tmp_path)
    assert universe.snapshot_dates(tmp_path) == []
    assert universe.earliest_snapshot(tmp_path) is None
    read = universe.resolve_security_asof("NEWCO", date(2026, 4, 1), root=tmp_path)
    assert read.available is False
    assert read.security is None
    assert read.unavailable_reason == universe.REASON_NO_SNAPSHOT


# --- no look-ahead ----------------------------------------------------------


def test_a_date_between_snapshots_reads_the_EARLIER_one(store: Path):
    """The greatest snapshot <= asof, never the nearest and never a later one."""
    read = universe.resolve_security_asof("NEWCO", date(2026, 3, 20), root=store)
    assert read.available is True
    assert read.snapshot_date == date(2026, 3, 1)
    assert read.security["as_known_on"] == "2026-03-01"


def test_a_name_that_only_exists_LATER_is_invisible_earlier(store: Path):
    """NEWCO exists from 2026-03-01. Asking on 2026-02-15 must not find it."""
    read = universe.resolve_security_asof("NEWCO", date(2026, 2, 15), root=store)
    assert read.available is False
    assert read.security is None
    assert read.snapshot_date == date(2026, 2, 1)
    assert read.unavailable_reason == universe.REASON_SYMBOL_ABSENT


def test_no_read_ever_selects_a_snapshot_later_than_asof(store: Path):
    for day in (date(2026, 1, 1), date(2026, 2, 28), date(2026, 3, 31), date(2026, 6, 30)):
        for read in (
            universe.resolve_security_asof("DUALA", day, root=store),
            universe.membership_asof(day, root=store),
        ):
            assert read.snapshot_date is None or read.snapshot_date <= day


# --- the headline regression: nothing current leaks backward ----------------


def test_before_the_earliest_snapshot_is_unavailable_not_the_current_roster(store: Path):
    read = universe.resolve_security_asof("DUALA", date(2015, 1, 1), root=store)
    assert read.available is False
    assert read.security is None
    assert read.snapshot_date is None
    assert read.unavailable_reason == universe.REASON_NO_SNAPSHOT
    assert read.coverage_class == universe.COVERAGE_CLASS_ROSTER
    assert read.limitations == REGISTERED_LIMITATIONS


def test_no_current_ticker_and_no_current_sector_leak_backward(store: Path):
    """The headline case: a 2015 query resolves nothing about today's roster."""
    current = universe.membership_asof(date(2026, 5, 1), root=store)
    assert current.available is True
    assert "NEWCO" in current.security["symbols"]

    membership_2015 = universe.membership_asof(date(2015, 1, 1), root=store)
    assert membership_2015.available is False
    assert membership_2015.security is None

    for symbol in current.security["symbols"]:
        read = universe.resolve_security_asof(symbol, date(2015, 1, 1), root=store)
        assert read.available is False, symbol
        assert read.security is None, symbol
        assert read.snapshot_date is None, symbol

    # And where a name IS resolvable, sector is still None — the roster has no
    # sector column, so a current sector cannot be back-stamped onto history.
    resolved = universe.resolve_security_asof("DUALA", date(2026, 5, 1), root=store)
    assert resolved.security["sector"] is None
    assert resolved.security["sector_availability"] == universe.SECTOR_AVAILABILITY


# --- acceptance case: ticker rename -----------------------------------------

def test_a_rename_has_no_stable_security_id_so_the_link_is_UNAVAILABLE(store: Path):
    """OLDCO becomes NEWCO. The roster cannot say they are one security."""
    before = universe.resolve_security_asof("OLDCO", date(2026, 2, 15), root=store)
    after = universe.resolve_security_asof("NEWCO", date(2026, 3, 15), root=store)
    assert before.available is True and after.available is True

    # Honest unavailable, expressed as absent fields rather than a guessed link.
    assert before.security["security_id"] is None
    assert after.security["security_id"] is None
    assert before.security["issuer_id"] is None
    assert after.security["issuer_id"] is None
    assert before.security["identity_linkage"] == universe.IDENTITY_LINKAGE

    # The old ticker does not resurrect after the rename, and the new one does
    # not reach back before it.
    assert universe.resolve_security_asof("OLDCO", date(2026, 3, 15), root=store).available is False
    assert universe.resolve_security_asof("NEWCO", date(2026, 2, 15), root=store).available is False


# --- acceptance case: acquired / delisted name ------------------------------


def test_an_acquired_name_stays_in_HISTORICAL_membership_and_leaves_the_current(store: Path):
    then = universe.membership_asof(date(2026, 2, 15), root=store)
    now = universe.membership_asof(date(2026, 5, 1), root=store)
    assert "GONECO" in then.security["symbols"]
    assert "GONECO" not in now.security["symbols"]

    assert universe.resolve_security_asof("GONECO", date(2026, 2, 15), root=store).available is True
    gone = universe.resolve_security_asof("GONECO", date(2026, 5, 1), root=store)
    assert gone.available is False
    assert gone.unavailable_reason == universe.REASON_SYMBOL_ABSENT
    assert gone.security is None


# --- acceptance case: listing gap -------------------------------------------


def test_a_listing_gap_is_reported_absent_not_carried_forward(store: Path):
    """GAPCO is present, then absent, then present. The gap must read absent."""
    assert universe.resolve_security_asof("GAPCO", date(2026, 2, 15), root=store).available is True
    gap = universe.resolve_security_asof("GAPCO", date(2026, 3, 15), root=store)
    assert gap.available is False
    assert gap.unavailable_reason == universe.REASON_SYMBOL_ABSENT
    assert gap.snapshot_date == date(2026, 3, 1)
    assert universe.resolve_security_asof("GAPCO", date(2026, 4, 15), root=store).available is True

    assert "GAPCO" not in universe.membership_asof(date(2026, 3, 15), root=store).security["symbols"]


# --- acceptance case: dual-class ambiguity ----------------------------------


def test_dual_class_lines_resolve_separately_and_cannot_be_linked(store: Path):
    a = universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store)
    b = universe.resolve_security_asof("DUALB", date(2026, 4, 15), root=store)
    assert a.available is True and b.available is True
    assert a.security["symbol"] == "DUALA" and b.security["symbol"] == "DUALB"
    # The honest unavailable: no issuer identifier exists, so nothing in this
    # plane can assert that the two lines are one issuer.
    assert a.security["issuer_id"] is None and b.security["issuer_id"] is None
    assert universe.coverage_report(store)["cannot_answer"].count("dual_class_issuer_linkage") == 1


# --- acceptance case: dormant shell, declared rule, never a blacklist -------


def test_a_dormant_shell_is_kept_and_the_liquidity_RULE_is_declared_unapplied(store: Path):
    membership = universe.membership_asof(date(2026, 5, 1), root=store)
    assert "SHELLCO" in membership.security["symbols"]
    assert membership.security["liquidity_screen_applied"] is False
    assert membership.security["liquidity_screen"] == universe.LIQUIDITY_SCREEN_STATE
    assert "no_ticker_blacklist" in membership.security["rules"]


def test_membership_excludes_by_declared_structural_rule_only(store: Path):
    membership = universe.membership_asof(date(2026, 5, 1), root=store)
    symbols = membership.security["symbols"]
    assert "TESTCO" not in symbols
    assert "PFDCO" not in symbols
    assert membership.security["excluded_test_issue"] == 1
    assert membership.security["excluded_preferred"] == 1
    assert membership.security["n_symbols"] == len(symbols)


def test_the_module_carries_no_hardcoded_ticker_blacklist():
    source = (ROOT / "engine" / "seasonality" / "universe.py").read_text(encoding="utf-8")
    for banned in ("BLACKLIST", "blacklist = ", "EXCLUDED_TICKERS", "DENYLIST"):
        assert banned not in source, banned


# --- acceptance case: split / special dividend vintage ----------------------


def test_corporate_actions_are_unavailable_for_every_argument_combination(store: Path):
    days = [date(2015, 1, 1), date(2026, 2, 1), date(2026, 3, 15), date(2030, 1, 1)]
    for symbol in ("DUALA", "NEWCO", "OLDCO", "NOSUCH", ""):
        for day in days:
            read = universe.corporate_actions_asof(symbol, day, root=store)
            assert read.available is False
            assert read.security is None
            assert read.blocker == universe.UNRESOLVED_BLOCKER
            assert read.unavailable_reason == universe.REASON_CORPORATE_ACTIONS


def test_no_code_path_in_corporate_actions_can_return_available():
    source = (ROOT / "engine" / "seasonality" / "universe.py").read_text(encoding="utf-8")
    body = source.split("def corporate_actions_asof", 1)[1].split("\ndef ", 1)[0]
    assert "available=True" not in body


def test_price_adjustment_vintage_is_current_vendor_and_not_point_in_time():
    vintage = universe.price_adjustment_vintage()
    assert vintage["point_in_time"] is False
    assert vintage["vintage"] == "current_vendor_vintage"
    assert vintage["note"]
    assert vintage["blocker"] == universe.UNRESOLVED_BLOCKER


def test_a_split_or_special_dividend_asof_is_unavailable_on_both_planes(store: Path):
    """The vintage question has two halves and neither one is answerable."""
    actions = universe.corporate_actions_asof("DUALA", date(2026, 4, 15), root=store)
    assert actions.available is False
    assert "incomplete_corporate_action_history" in actions.limitations
    assert universe.price_adjustment_vintage()["point_in_time"] is False


# --- registry binding -------------------------------------------------------


def test_limitations_are_carried_verbatim_from_the_registry(store: Path):
    for read in (
        universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store),
        universe.membership_asof(date(2026, 4, 15), root=store),
        universe.corporate_actions_asof("DUALA", date(2026, 4, 15), root=store),
    ):
        assert read.limitations == REGISTERED_LIMITATIONS


def test_a_changed_registry_changes_the_adapter_so_it_cannot_drift(tmp_path: Path):
    _write_registry(tmp_path, limitations=("us_exchange_roster_only", "some_new_declared_limit"))
    _write_snapshots(tmp_path, {"2026-02-01": [_row("DUALA", "Dual Issuer Inc.")]})
    read = universe.resolve_security_asof("DUALA", date(2026, 2, 1), root=tmp_path)
    assert read.limitations == ("us_exchange_roster_only", "some_new_declared_limit")


def test_a_missing_registry_entry_FAILS_CLOSED(tmp_path: Path):
    """No registration means no coverage claim — not a default coverage claim."""
    _write_snapshots(tmp_path, {"2026-02-01": [_row("DUALA", "Dual Issuer Inc.")]})
    for read in (
        universe.resolve_security_asof("DUALA", date(2026, 2, 1), root=tmp_path),
        universe.membership_asof(date(2026, 2, 1), root=tmp_path),
    ):
        assert read.available is False
        assert read.security is None
        assert read.unavailable_reason == universe.REASON_REGISTRY_MISSING
        assert read.coverage_class == universe.COVERAGE_CLASS_UNREGISTERED
        assert read.limitations == ()
        assert read.blocker == universe.UNRESOLVED_BLOCKER


def test_an_empty_limitations_list_is_not_a_coverage_upgrade(tmp_path: Path):
    _write_registry(tmp_path, limitations=())
    _write_snapshots(tmp_path, {"2026-02-01": [_row("DUALA", "Dual Issuer Inc.")]})
    read = universe.resolve_security_asof("DUALA", date(2026, 2, 1), root=tmp_path)
    assert read.available is False
    assert read.coverage_class == universe.COVERAGE_CLASS_UNREGISTERED


def test_the_adapter_never_writes_the_registry(store: Path):
    path = store / universe.REGISTRY_SUBPATH
    before = path.read_bytes()
    universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store)
    universe.membership_asof(date(2026, 4, 15), root=store)
    universe.coverage_report(store)
    assert path.read_bytes() == before


# --- read shape -------------------------------------------------------------


def test_every_entry_point_returns_a_UniverseRead_never_none_or_a_bare_ticker(store: Path):
    reads = [
        universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store),
        universe.resolve_security_asof("NOSUCH", date(2015, 1, 1), root=store),
        universe.corporate_actions_asof("DUALA", date(2026, 4, 15), root=store),
        universe.membership_asof(date(2026, 4, 15), root=store),
        universe.membership_asof(date(2015, 1, 1), root=store),
    ]
    for read in reads:
        assert isinstance(read, universe.UniverseRead)
        assert isinstance(read.asof, date)
        assert isinstance(read.coverage_class, str) and read.coverage_class
        assert isinstance(read.limitations, tuple)
        if read.available:
            assert isinstance(read.security, dict)
        else:
            assert read.security is None
            assert read.unavailable_reason


def test_a_read_cannot_be_constructed_in_an_inconsistent_state():
    with pytest.raises(ValueError):
        universe.UniverseRead(
            available=True,
            asof=date(2026, 1, 1),
            snapshot_date=None,
            security=None,
            unavailable_reason=None,
            blocker=None,
            coverage_class=universe.COVERAGE_CLASS_ROSTER,
        )
    with pytest.raises(ValueError):
        universe.UniverseRead(
            available=False,
            asof=date(2026, 1, 1),
            snapshot_date=None,
            security=None,
            unavailable_reason=None,
            blocker=None,
            coverage_class=universe.COVERAGE_CLASS_ROSTER,
        )


def test_as_dict_is_json_safe(store: Path):
    import json

    payload = universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store).as_dict()
    assert json.loads(json.dumps(payload))["snapshot_date"] == "2026-04-01"
    unavailable = universe.corporate_actions_asof("DUALA", date(2015, 1, 1), root=store).as_dict()
    assert json.loads(json.dumps(unavailable))["blocker"] == universe.UNRESOLVED_BLOCKER


def test_a_datetime_asof_is_accepted_and_a_non_date_is_rejected(store: Path):
    read = universe.resolve_security_asof("DUALA", datetime(2026, 4, 15, 13, 30), root=store)
    assert read.asof == date(2026, 4, 15)
    with pytest.raises(TypeError):
        universe.resolve_security_asof("DUALA", "2026-04-15", root=store)


# --- no wall clock ----------------------------------------------------------


def test_the_module_reads_no_wall_clock():
    """``asof`` is always explicit, so a read is reproducible from its arguments."""
    source = (ROOT / "engine" / "seasonality" / "universe.py").read_text(encoding="utf-8")
    for banned in ("date.today", "datetime.now", "utcnow", "time.time", "date.fromtimestamp"):
        assert banned not in source, banned


def test_the_same_arguments_give_the_same_answer(store: Path):
    first = universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store)
    second = universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store)
    assert first == second


# --- coverage report --------------------------------------------------------


def test_coverage_report_counts_the_store_and_lists_what_it_cannot_answer(store: Path):
    report = universe.coverage_report(store)
    assert report["schema"] == universe.COVERAGE_SCHEMA
    assert report["registered"] is True
    assert report["n_snapshots"] == 4
    assert report["earliest_snapshot"] == "2026-02-01"
    assert report["latest_snapshot"] == "2026-05-01"
    assert report["blocker"] == universe.UNRESOLVED_BLOCKER
    assert report["adapter_implementation_state"] == "unavailable_bootstrap_roster_only"
    assert report["price_adjustment"]["point_in_time"] is False
    for cannot in (
        "security_identity_before_earliest_snapshot",
        "corporate_actions_asof_any_date",
        "point_in_time_price_adjustment",
        "sector_classification_asof",
    ):
        assert cannot in report["cannot_answer"]
    # The honest shape: this plane says no more often than yes.
    assert len(report["cannot_answer"]) > len(report["can_answer"])


def test_coverage_report_on_an_unregistered_root_says_so(tmp_path: Path):
    report = universe.coverage_report(tmp_path)
    assert report["registered"] is False
    assert report["coverage_class"] == universe.COVERAGE_CLASS_UNREGISTERED
    assert report["limitations"] == []
    assert report["n_snapshots"] == 0
    assert report["earliest_snapshot"] is None


# --- the real committed store (structural only, skips cleanly) --------------


@pytest.mark.skipif(not REAL_SNAPSHOTS.is_dir(), reason="no committed snapshot store")
def test_the_real_store_parses_and_its_earliest_snapshot_is_not_in_the_future():
    dates = universe.snapshot_dates(ROOT)
    if not dates:
        pytest.skip("snapshot store present but empty")
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)
    earliest = universe.earliest_snapshot(ROOT)
    assert earliest == dates[0]
    assert earliest <= date.today()

    # Snapshot dates are UTC COLLECTION dates, so the newest file can legitimately
    # be one day ahead of a local calendar west of UTC — and no further.
    assert universe.latest_snapshot(ROOT) == dates[-1]
    assert dates[-1] <= date.today() + timedelta(days=1)

    report = universe.coverage_report(ROOT)
    assert report["registered"] is True
    assert tuple(report["limitations"]) == REGISTERED_LIMITATIONS
    assert report["n_snapshots"] == len(dates)


@pytest.mark.skipif(not REAL_SNAPSHOTS.is_dir(), reason="no committed snapshot store")
def test_the_real_store_answers_a_2015_query_with_UNAVAILABLE():
    """Gate 5. The panel starts ~25 years back; this plane starts weeks back."""
    read = universe.resolve_security_asof("AAPL", date(2015, 1, 1), root=ROOT)
    assert read.available is False
    assert read.security is None
    assert read.snapshot_date is None
    assert read.unavailable_reason == universe.REASON_NO_SNAPSHOT
    assert read.coverage_class == universe.COVERAGE_CLASS_ROSTER
    assert read.limitations == REGISTERED_LIMITATIONS


# --- no unbounded FORWARD carry ---------------------------------------------


def test_an_asof_past_the_last_snapshot_plus_carry_is_UNAVAILABLE(store: Path):
    """The forward mirror of the backward leak: no roster for the year 2199."""
    latest = date(2026, 5, 1)
    edge = latest + timedelta(days=universe.MAX_FORWARD_CARRY_DAYS)
    for read in (
        universe.resolve_security_asof("DUALA", edge, root=store),
        universe.membership_asof(edge, root=store),
    ):
        assert read.available is True
        assert read.snapshot_date == latest
        assert read.snapshot_age_days == universe.MAX_FORWARD_CARRY_DAYS

    for day in (edge + timedelta(days=1), date(2030, 1, 1), date(2199, 12, 31), date.max):
        for read in (
            universe.resolve_security_asof("DUALA", day, root=store),
            universe.membership_asof(day, root=store),
        ):
            assert read.available is False, day
            assert read.security is None, day
            assert read.snapshot_date is None, day
            assert read.unavailable_reason == universe.REASON_ASOF_BEYOND_STORE, day


def test_the_two_off_the_end_reasons_are_told_apart(store: Path):
    before = universe.resolve_security_asof("DUALA", date(2015, 1, 1), root=store)
    after = universe.resolve_security_asof("DUALA", date(2030, 1, 1), root=store)
    assert before.unavailable_reason == universe.REASON_NO_SNAPSHOT
    assert after.unavailable_reason == universe.REASON_ASOF_BEYOND_STORE
    assert before.unavailable_reason != after.unavailable_reason


def test_every_available_read_discloses_how_stale_it_is(store: Path):
    """A 19-day-old roster is still an answer, but never an undated one."""
    resolved = universe.resolve_security_asof("NEWCO", date(2026, 3, 20), root=store)
    members = universe.membership_asof(date(2026, 3, 20), root=store)
    for read in (resolved, members):
        assert read.snapshot_date == date(2026, 3, 1)
        assert read.snapshot_age_days == 19
        assert read.as_dict()["snapshot_age_days"] == 19
    exact = universe.resolve_security_asof("NEWCO", date(2026, 3, 1), root=store)
    assert exact.snapshot_age_days == 0


def test_a_read_cannot_claim_an_age_without_a_snapshot():
    with pytest.raises(ValueError):
        universe.UniverseRead(
            available=False,
            asof=date(2026, 1, 1),
            snapshot_date=None,
            security=None,
            unavailable_reason=universe.REASON_NO_SNAPSHOT,
            blocker=None,
            coverage_class=universe.COVERAGE_CLASS_ROSTER,
            snapshot_age_days=3,
        )


def test_an_available_read_must_name_its_snapshot():
    with pytest.raises(ValueError):
        universe.UniverseRead(
            available=True,
            asof=date(2026, 1, 1),
            snapshot_date=None,
            security={"symbol": "X"},
            unavailable_reason=None,
            blocker=None,
            coverage_class=universe.COVERAGE_CLASS_ROSTER,
        )


# --- ticker collisions: ambiguous, never the first row ----------------------


@pytest.fixture()
def collision_store(tmp_path: Path) -> Path:
    """One snapshot carrying the committed store's real defect shape.

    ``NAN`` (a listed fund) and ``nan`` (an upstream ``NA`` NA-coercion
    artifact) case-fold onto the same key, exactly as they do in
    ``data/symbol_directory/snapshots/``.
    """
    _write_registry(tmp_path)
    _write_snapshots(
        tmp_path,
        {
            "2026-02-01": [
                _row("NAN", "Real Municipal Fund", exchange="N", source="otherlisted"),
                _row("nan", "Nano Labs Ltd - Class A", exchange="NASDAQ"),
                _row("SOLO", "Only One Line Inc. - Common Stock"),
            ]
        },
    )
    return tmp_path


def test_a_ticker_matching_two_rows_is_AMBIGUOUS_not_the_first_row(collision_store: Path):
    read = universe.resolve_security_asof("NAN", date(2026, 2, 1), root=collision_store)
    assert read.available is False
    assert read.security is None
    assert read.unavailable_reason == universe.REASON_SYMBOL_AMBIGUOUS
    assert read.snapshot_date == date(2026, 2, 1)
    assert read.blocker == universe.UNRESOLVED_BLOCKER
    assert read.detail["n_matching_rows"] == 2
    assert read.detail["matching_symbols"] == ["NAN", "nan"]
    assert sorted(read.detail["matching_exchanges"]) == ["N", "NASDAQ"]
    # No issuer name leaks out of an ambiguous read in any form.
    payload = read.as_dict()
    assert "Nano Labs" not in str(payload)
    assert "Real Municipal" not in str(payload)
    # An unambiguous line in the same snapshot still resolves.
    assert universe.resolve_security_asof("SOLO", date(2026, 2, 1), root=collision_store).available


def test_a_collision_collapses_ONE_membership_row_and_says_so(collision_store: Path):
    membership = universe.membership_asof(date(2026, 2, 1), root=collision_store).security
    assert membership["n_rows_in_snapshot"] == 3
    assert membership["excluded_duplicate_symbol_rows"] == 1
    assert membership["n_symbols"] == 2
    assert (
        membership["n_rows_in_snapshot"]
        - membership["excluded_test_issue"]
        - membership["excluded_preferred"]
        - membership["excluded_duplicate_symbol_rows"]
        == membership["n_symbols"]
    )


def test_membership_counts_reconcile_exactly(store: Path):
    membership = universe.membership_asof(date(2026, 5, 1), root=store).security
    assert (
        membership["n_rows_in_snapshot"]
        - membership["excluded_test_issue"]
        - membership["excluded_preferred"]
        - membership["excluded_duplicate_symbol_rows"]
        == membership["n_symbols"]
    )


def test_a_lookup_is_case_and_whitespace_normalised(store: Path):
    for query in ("dualb", "  DUALB  ", " DuAlB\t"):
        read = universe.resolve_security_asof(query, date(2026, 4, 15), root=store)
        assert read.available is True, query
        assert read.security["symbol"] == "DUALB", query


# --- membership is roster membership, NOT a common-equity universe ----------


def test_ETFs_are_kept_and_DECLARED_not_silently_included(tmp_path: Path):
    _write_registry(tmp_path)
    _write_snapshots(
        tmp_path,
        {
            "2026-02-01": [
                _row("EQTY", "Equity Inc. - Common Stock"),
                _row("SPDR", "An Index ETF", etf=True),
                _row("QQQX", "Another Index ETF", etf=True),
            ]
        },
    )
    membership = universe.membership_asof(date(2026, 2, 1), root=tmp_path).security
    assert set(membership["symbols"]) == {"EQTY", "SPDR", "QQQX"}
    # Kept — but a caller can subtract them without re-reading the parquet, and
    # the payload never lets "roster membership" read as "common equity".
    assert set(membership["etf_symbols"]) == {"SPDR", "QQQX"}
    assert membership["n_etf_symbols"] == 2
    assert membership["etf_screen_applied"] is False
    assert membership["etf_screen"] == universe.ETF_SCREEN_STATE
    assert "etf_lines_kept_and_flagged_not_excluded" in membership["rules"]
    assert membership["screens_applied"]["etf_lines_excluded"] is False


def test_declared_rules_are_reported_as_APPLIED_only_where_they_ran(store: Path):
    membership = universe.membership_asof(date(2026, 5, 1), root=store).security
    applied = membership["screens_applied"]
    assert applied["test_issue_rows_excluded"] is True
    assert applied["preferred_lines_excluded"] is True
    assert applied["etf_lines_excluded"] is False
    assert applied["liquidity_screen_applied"] is False


def test_membership_is_exactly_the_declared_filters_with_no_hidden_exclusions(tmp_path: Path):
    """Behavioural twin of the blacklist grep: a named exclusion would show here."""
    _write_registry(tmp_path)
    listed = ["AAPL", "BRK-A", "ZZZ", "GME", "SPCE", "HKD", "AMTD", "DWAC", "NAN2", "X"]
    _write_snapshots(
        tmp_path,
        {
            "2026-02-01": [_row(sym, f"{sym} Inc. - Common Stock") for sym in listed]
            + [
                _row("TSTX", "TEST STOCK", test_issue=True),
                _row("PFDX", "Preferred Line", is_preferred=True),
            ]
        },
    )
    membership = universe.membership_asof(date(2026, 2, 1), root=tmp_path).security
    assert set(membership["symbols"]) == set(listed)
    assert membership["excluded_test_issue"] == 1
    assert membership["excluded_preferred"] == 1


# --- a thin or corrupt snapshot is UNAVAILABLE, never a stamped read --------


def test_a_corrupt_snapshot_is_unavailable_not_a_stamped_payload(store: Path):
    (store / universe.SNAPSHOT_SUBPATH / "2026-06-01.parquet").write_bytes(b"not parquet at all")
    for read in (
        universe.resolve_security_asof("DUALA", date(2026, 6, 1), root=store),
        universe.membership_asof(date(2026, 6, 1), root=store),
    ):
        assert read.available is False
        assert read.security is None
        assert read.unavailable_reason == universe.REASON_SNAPSHOT_UNREADABLE
        assert read.snapshot_date == date(2026, 6, 1)


def test_a_snapshot_missing_a_declared_column_is_OFF_SCHEMA_not_a_quiet_zero(store: Path):
    """``excluded_preferred: 0`` must never mean "the column is gone"."""
    store_dir = store / universe.SNAPSHOT_SUBPATH
    thin = pd.DataFrame(
        [
            {
                "date": "2026-06-01",
                "symbol": "THIN",
                "security_name": "Thin Schema Inc.",
                "exchange": "NASDAQ",
                "etf": False,
                "test_issue": False,
                "source": "nasdaqlisted",
            }
        ]
    )  # no is_preferred column
    thin.to_parquet(store_dir / "2026-06-01.parquet")
    membership = universe.membership_asof(date(2026, 6, 1), root=store)
    assert membership.available is False
    assert membership.security is None
    assert membership.unavailable_reason == universe.REASON_SNAPSHOT_UNREADABLE
    resolved = universe.resolve_security_asof("THIN", date(2026, 6, 1), root=store)
    assert resolved.available is False
    assert resolved.unavailable_reason == universe.REASON_SNAPSHOT_UNREADABLE
    # And the schema stamp is not handed out to a file that is not this schema.
    assert "THIN" not in str(membership.as_dict())


def test_a_symbol_only_snapshot_never_gets_the_schema_stamp(tmp_path: Path):
    _write_registry(tmp_path)
    store_dir = tmp_path / universe.SNAPSHOT_SUBPATH
    store_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"symbol": "ONLY"}]).to_parquet(store_dir / "2026-02-01.parquet")
    read = universe.resolve_security_asof("ONLY", date(2026, 2, 1), root=tmp_path)
    assert read.available is False
    assert read.unavailable_reason == universe.REASON_SNAPSHOT_UNREADABLE
    assert universe.SNAPSHOT_SCHEMA not in str(read.as_dict()["security"])


def test_a_rewritten_snapshot_is_re_read_not_served_from_cache(tmp_path: Path):
    _write_registry(tmp_path)
    _write_snapshots(tmp_path, {"2026-02-01": [_row("FIRST", "First Inc.")]})
    first = universe.membership_asof(date(2026, 2, 1), root=tmp_path)
    assert set(first.security["symbols"]) == {"FIRST"}
    _write_snapshots(
        tmp_path,
        {"2026-02-01": [_row("FIRST", "First Inc."), _row("SECOND", "Second Inc.")]},
    )
    second = universe.membership_asof(date(2026, 2, 1), root=tmp_path)
    assert set(second.security["symbols"]) == {"FIRST", "SECOND"}


# --- the store path follows the WRITER's configured data_dir ----------------


def test_the_reader_follows_storage_data_dir_so_it_cannot_desync_from_the_writer(tmp_path: Path):
    _write_registry(tmp_path)
    (tmp_path / "config.yml").write_text(
        yaml.safe_dump({"storage": {"data_dir": "data_relocated"}}), encoding="utf-8"
    )
    store_dir = tmp_path / "data_relocated" / "symbol_directory" / "snapshots"
    store_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([dict(_row("MOVED", "Relocated Inc."), date="2026-02-01")])
    frame.to_parquet(store_dir / "2026-02-01.parquet")

    assert universe.snapshot_store(tmp_path) == store_dir
    assert universe.snapshot_dates(tmp_path) == [date(2026, 2, 1)]
    read = universe.resolve_security_asof("MOVED", date(2026, 2, 1), root=tmp_path)
    assert read.available is True
    assert universe.coverage_report(tmp_path)["snapshot_root"] == str(store_dir)


def test_without_a_config_the_store_is_the_default_data_dir(store: Path):
    assert universe.snapshot_store(store) == store / universe.SNAPSHOT_SUBPATH


# --- registry failures are told apart ---------------------------------------


def test_a_malformed_registry_is_UNREADABLE_not_reported_as_missing(tmp_path: Path):
    path = tmp_path / universe.REGISTRY_SUBPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("registrations: [this: is: not: valid", encoding="utf-8")
    _write_snapshots(tmp_path, {"2026-02-01": [_row("DUALA", "Dual Issuer Inc.")]})
    read = universe.resolve_security_asof("DUALA", date(2026, 2, 1), root=tmp_path)
    assert read.available is False
    assert read.unavailable_reason == universe.REASON_REGISTRY_UNREADABLE
    assert read.unavailable_reason != universe.REASON_REGISTRY_MISSING
    assert read.coverage_class == universe.COVERAGE_CLASS_UNREGISTERED


def test_an_empty_limitations_list_says_WHY_it_is_not_a_coverage_claim(tmp_path: Path):
    _write_registry(tmp_path, limitations=())
    _write_snapshots(tmp_path, {"2026-02-01": [_row("DUALA", "Dual Issuer Inc.")]})
    read = universe.resolve_security_asof("DUALA", date(2026, 2, 1), root=tmp_path)
    assert read.unavailable_reason == universe.REASON_REGISTRY_NO_LIMITATIONS


def test_the_coverage_class_is_READ_from_the_registry_not_restated(tmp_path: Path):
    """A registry edit moves the class; a hardcoded class would not."""
    _write_registry(tmp_path, limitations=("global_security_master_complete", "full_actions"))
    _write_snapshots(tmp_path, {"2026-02-01": [_row("DUALA", "Dual Issuer Inc.")]})
    read = universe.resolve_security_asof("DUALA", date(2026, 2, 1), root=tmp_path)
    assert read.coverage_class == "global_security_master_complete"
    assert read.coverage_class != universe.COVERAGE_CLASS_ROSTER
    assert universe.coverage_report(tmp_path)["coverage_class"] == "global_security_master_complete"


# --- the disclosure payload carries the whole disclosure --------------------


def test_as_dict_carries_every_disclosure_field(store: Path):
    payload = universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store).as_dict()
    assert payload["available"] is True
    assert payload["limitations"] == list(REGISTERED_LIMITATIONS)
    assert payload["coverage_class"] == universe.COVERAGE_CLASS_ROSTER
    assert payload["unavailable_reason"] is None
    assert payload["snapshot_age_days"] == 14
    assert payload["snapshot_date_basis"] == universe.SNAPSHOT_DATE_BASIS
    assert payload["adapter_registration"] == universe.ADAPTER_REGISTRATION
    assert payload["adapter_implementation_state"] == universe.ADAPTER_IMPLEMENTATION_STATE

    unavailable = universe.membership_asof(date(2015, 1, 1), root=store).as_dict()
    assert unavailable["available"] is False
    assert unavailable["unavailable_reason"] == universe.REASON_NO_SNAPSHOT
    assert unavailable["limitations"] == list(REGISTERED_LIMITATIONS)
    assert unavailable["adapter_implementation_state"] == universe.ADAPTER_IMPLEMENTATION_STATE


def test_an_available_read_still_discloses_the_registration_it_rests_on(store: Path):
    """The roster is a bootstrap registration even when it answers."""
    read = universe.resolve_security_asof("DUALA", date(2026, 4, 15), root=store)
    assert read.available is True
    assert read.adapter_implementation_state == "unavailable_bootstrap_roster_only"
    assert read.security["snapshot_date_basis"] == universe.SNAPSHOT_DATE_BASIS


def test_coverage_report_pins_the_whole_cannot_answer_list(store: Path):
    report = universe.coverage_report(store)
    assert report["cannot_answer"] == [
        "security_identity_before_earliest_snapshot",
        "security_identity_beyond_latest_snapshot_max_forward_carry",
        "corporate_actions_asof_any_date",
        "point_in_time_price_adjustment",
        "stable_security_or_issuer_identifier",
        "ticker_rename_linkage",
        "dual_class_issuer_linkage",
        "ambiguous_ticker_with_two_rows_in_one_snapshot",
        "sector_classification_asof",
        "common_equity_only_universe_etfs_are_not_screened_out",
        "non_us_listings_and_private_companies",
    ]
    assert report["max_forward_carry_days"] == universe.MAX_FORWARD_CARRY_DAYS
    assert report["snapshot_required_columns"] == list(universe.SNAPSHOT_REQUIRED_COLUMNS)
    assert report["snapshot_date_basis"] == universe.SNAPSHOT_DATE_BASIS


def test_the_nulls_are_scoped_to_the_REGISTERED_artifact_not_to_the_repo(store: Path):
    """A CIK map exists on the same collector; "cannot answer" must not overstate."""
    report = universe.coverage_report(store)
    assert "snapshots/" in report["cannot_answer_scope"]
    planes = report["planes_not_read_by_this_adapter"]
    assert len(planes) == 1
    cik = planes[0]
    assert cik["path"].endswith(str(Path("symbol_directory") / "cik_map"))
    assert cik["carries"] == "sec_cik_issuer_identifier_per_ticker"
    assert cik["written_by"] == "collectors.symbol_directory"
    assert "registered writer artifact" in cik["why_not_read"]


# --- no wall clock, enforced behaviourally ----------------------------------


def test_asof_and_root_are_REQUIRED_arguments_on_every_entry_point():
    """A defaulted ``asof`` is how a wall clock gets back in without the word."""
    for func in (
        universe.resolve_security_asof,
        universe.corporate_actions_asof,
        universe.membership_asof,
    ):
        params = inspect.signature(func).parameters
        assert params["asof"].default is inspect.Parameter.empty, func.__name__
        assert params["root"].default is inspect.Parameter.empty, func.__name__
        assert params["root"].kind is inspect.Parameter.KEYWORD_ONLY, func.__name__


def test_no_clock_CALL_survives_anywhere_in_the_module():
    """AST, not substring: ``datetime.today()`` evades a ``date.today`` grep."""
    source = (ROOT / "engine" / "seasonality" / "universe.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = {"today", "now", "utcnow", "fromtimestamp", "monotonic", "perf_counter", "time_ns"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in banned, node.attr
        if isinstance(node, ast.Name):
            assert node.id not in banned, node.id
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "time", alias.name
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "time", node.module


# --- the real committed store: the defects that live in it ------------------


@pytest.mark.skipif(not REAL_SNAPSHOTS.is_dir(), reason="no committed snapshot store")
def test_no_duplicated_ticker_in_the_real_store_resolves_to_one_of_its_rows():
    """The committed store carries ``NAN``/``nan``. Neither issuer may win."""
    latest = universe.latest_snapshot(ROOT)
    if latest is None:
        pytest.skip("snapshot store present but empty")
    frame = pd.read_parquet(REAL_SNAPSHOTS / f"{latest.isoformat()}.parquet")
    keys = frame["symbol"].astype(str).str.strip().str.upper()
    duplicated = sorted(set(keys[keys.duplicated()]))
    if not duplicated:
        pytest.skip("no case-folded ticker collision in the newest snapshot")
    for symbol in duplicated:
        read = universe.resolve_security_asof(symbol, latest, root=ROOT)
        assert read.available is False, symbol
        assert read.security is None, symbol
        assert read.unavailable_reason == universe.REASON_SYMBOL_AMBIGUOUS, symbol
        assert read.detail["n_matching_rows"] >= 2, symbol


@pytest.mark.skipif(not REAL_SNAPSHOTS.is_dir(), reason="no committed snapshot store")
def test_the_real_store_membership_reconciles_and_declares_its_ETFs():
    latest = universe.latest_snapshot(ROOT)
    if latest is None:
        pytest.skip("snapshot store present but empty")
    membership = universe.membership_asof(latest, root=ROOT)
    assert membership.available is True
    payload = membership.security
    assert (
        payload["n_rows_in_snapshot"]
        - payload["excluded_test_issue"]
        - payload["excluded_preferred"]
        - payload["excluded_duplicate_symbol_rows"]
        == payload["n_symbols"]
    )
    # Nearly half of this roster is an ETF line; the read must say so out loud.
    assert payload["n_etf_symbols"] > 0
    assert set(payload["etf_symbols"]).issubset(set(payload["symbols"]))
    assert payload["etf_screen_applied"] is False


@pytest.mark.skipif(not REAL_SNAPSHOTS.is_dir(), reason="no committed snapshot store")
def test_the_real_store_answers_a_year_2199_query_with_UNAVAILABLE():
    """Gate 5's forward twin: today's roster is not evidence about 2199."""
    read = universe.resolve_security_asof("AAPL", date(2199, 12, 31), root=ROOT)
    assert read.available is False
    assert read.security is None
    assert read.snapshot_date is None
    assert read.unavailable_reason == universe.REASON_ASOF_BEYOND_STORE
