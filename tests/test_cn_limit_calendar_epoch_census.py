from __future__ import annotations

import calendar as calendar_module
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.research import cn_limit_calendar_epoch_census as census


def _year_dates(year: int) -> list[date]:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    out = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def _exchange_rows(
    exchange: str,
    years: list[int],
    *,
    closed_weekdays: tuple[int, ...] = (5, 6),
    skip_dates: frozenset[date] = frozenset(),
) -> list[dict]:
    """Build a full, internally-consistent trade-calendar row set for one
    exchange across ``years``, with a valid pretrade_date chain threaded
    across the whole span (the census checks the chain per exchange across
    the entire frame, not per partition)."""

    rows: list[dict] = []
    last_open: date | None = None
    for year in years:
        for d in _year_dates(year):
            if d in skip_dates:
                continue
            is_open = 0 if d.weekday() in closed_weekdays else 1
            # First-ever row's pretrade_date is unverifiable and skipped by
            # the census (last_open is None), so any placeholder is fine.
            pretrade = last_open.isoformat() if last_open else (d - timedelta(days=1)).isoformat()
            rows.append(
                {
                    "exchange": exchange,
                    "cal_date": d.isoformat(),
                    "is_open": is_open,
                    "pretrade_date": pretrade,
                }
            )
            if is_open:
                last_open = d
    return rows


def _write_partition(cal_dir: Path, year: int, rows: list[dict]) -> None:
    cal_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=["exchange", "cal_date", "is_open", "pretrade_date"])
    frame["is_open"] = frame["is_open"].astype("Int64")
    frame.to_parquet(cal_dir / f"year={year}.parquet")


def _write_store(
    tmp_path: Path,
    rows_by_year_and_exchange: dict[int, dict[str, list[dict]]],
) -> Path:
    """rows_by_year_and_exchange[year][exchange] -> list of rows; a missing
    exchange key for a year means zero rows for that exchange that year
    (the real-1991 shape). All rows for a year land in one partition file,
    matching the real store's layout."""

    store = tmp_path / "china_tushare_spine"
    cal_dir = census._calendar_dir(store)
    for year, per_exchange in sorted(rows_by_year_and_exchange.items()):
        rows: list[dict] = []
        for exchange in census.EXCHANGES:
            rows.extend(per_exchange.get(exchange, []))
        _write_partition(cal_dir, year, rows)
    return store


# --------------------------------------------------------------------------
# Fixtures: clean two-year store
# --------------------------------------------------------------------------


def _clean_two_year_store(tmp_path: Path, *, years: tuple[int, int] = (2001, 2002)) -> Path:
    year_list = list(years)
    sse_rows = _exchange_rows("SSE", year_list)
    szse_rows = _exchange_rows("SZSE", year_list)
    by_year: dict[int, dict[str, list[dict]]] = {y: {} for y in year_list}
    for row in sse_rows:
        by_year[int(row["cal_date"][:4])].setdefault("SSE", []).append(row)
    for row in szse_rows:
        by_year[int(row["cal_date"][:4])].setdefault("SZSE", []).append(row)
    return _write_store(tmp_path, by_year)


def test_clean_two_year_store_epoch_is_first_year(tmp_path):
    store = _clean_two_year_store(tmp_path, years=(2001, 2002))
    result = census.build_census(store)

    assert [r.year for r in result.years] == [2001, 2002]
    for record in result.years:
        assert record.complete is True
        assert record.joint is True
        assert record.parity_mismatch == 0
    assert result.integrity.partition_purity_ok is True
    assert result.integrity.duplicate_key_rows == 0
    for exchange in census.EXCHANGES:
        report = result.integrity.exchanges[exchange]
        assert report.pretrade_violations == ()
        assert report.missing_dates == ()

    assert result.epoch == 2001


# --------------------------------------------------------------------------
# Real 1991 shape: first year missing one exchange entirely
# --------------------------------------------------------------------------


def test_first_year_missing_one_exchange_epoch_is_second_year(tmp_path):
    year1, year2 = 2001, 2002
    # SZSE history begins in year2 only -- zero SZSE rows land for year1,
    # exactly like the real store's 1991 partition. SSE spans both years
    # with one continuous pretrade chain.
    sse_rows = _exchange_rows("SSE", [year1, year2])
    szse_rows = _exchange_rows("SZSE", [year2])

    by_year: dict[int, dict[str, list[dict]]] = {year1: {}, year2: {}}
    for row in sse_rows:
        by_year[int(row["cal_date"][:4])].setdefault("SSE", []).append(row)
    for row in szse_rows:
        by_year[int(row["cal_date"][:4])].setdefault("SZSE", []).append(row)

    store = _write_store(tmp_path, by_year)
    result = census.build_census(store)

    assert [r.year for r in result.years] == [year1, year2]
    first, second = result.years
    assert first.szse_unique == 0
    assert first.szse_open == 0
    assert first.shared == 0
    assert first.parity_mismatch == -1
    assert first.complete is False
    assert first.joint is False

    assert second.complete is True
    assert second.joint is True
    assert second.parity_mismatch == 0

    assert result.epoch == year2


# --------------------------------------------------------------------------
# Genuine open/closed parity mismatch on one shared date
# --------------------------------------------------------------------------


def test_parity_mismatch_on_shared_date_breaks_joint(tmp_path):
    year = 2001
    sse_rows = _exchange_rows("SSE", [year])
    szse_rows = _exchange_rows("SZSE", [year])

    # Flip is_open for one shared Wednesday (an ordinary open day for both)
    # on the SZSE side only.
    flip_target = None
    for row in szse_rows:
        d = date.fromisoformat(row["cal_date"])
        if d.weekday() == 2 and row["is_open"] == 1:
            flip_target = row["cal_date"]
            row["is_open"] = 0
            break
    assert flip_target is not None

    by_year = {year: {"SSE": sse_rows, "SZSE": szse_rows}}
    store = _write_store(tmp_path, by_year)
    result = census.build_census(store)

    (record,) = result.years
    assert record.parity_mismatch == 1
    assert record.joint is False
    assert result.epoch is None


# --------------------------------------------------------------------------
# Broken pretrade_date chain
# --------------------------------------------------------------------------


def test_broken_pretrade_chain_reports_offending_date(tmp_path):
    year = 2001
    sse_rows = _exchange_rows("SSE", [year])
    szse_rows = _exchange_rows("SZSE", [year])

    # Corrupt the pretrade_date of some open day well past the first row so
    # it no longer matches the true most-recent-prior-open session.
    target_index = None
    for i, row in enumerate(sse_rows):
        if row["is_open"] == 1 and i > 10:
            target_index = i
            break
    assert target_index is not None
    offending_date = sse_rows[target_index]["cal_date"]
    sse_rows[target_index] = dict(sse_rows[target_index])
    sse_rows[target_index]["pretrade_date"] = "1900-01-01"

    by_year = {year: {"SSE": sse_rows, "SZSE": szse_rows}}
    store = _write_store(tmp_path, by_year)
    result = census.build_census(store)

    report = result.integrity.exchanges["SSE"]
    assert len(report.pretrade_violations) == 1
    violation = report.pretrade_violations[0]
    assert violation["date"] == offending_date
    assert violation["pretrade_date"] == "1900-01-01"
    assert violation["expected_prior_open_date"] != "1900-01-01"

    assert result.integrity.exchanges["SZSE"].pretrade_violations == ()


# --------------------------------------------------------------------------
# Missing civil date inside an exchange's span (continuity violation)
# --------------------------------------------------------------------------


def test_missing_civil_date_reports_continuity_violation(tmp_path):
    year = 2001
    missing_day = date(2001, 6, 15)
    sse_rows = _exchange_rows("SSE", [year], skip_dates=frozenset({missing_day}))
    szse_rows = _exchange_rows("SZSE", [year])

    by_year = {year: {"SSE": sse_rows, "SZSE": szse_rows}}
    store = _write_store(tmp_path, by_year)
    result = census.build_census(store)

    report = result.integrity.exchanges["SSE"]
    assert report.missing_dates == (missing_day.isoformat(),)
    # SSE lost one civil date, so it can no longer report the full year.
    (record,) = result.years
    assert record.sse_unique == 364
    assert record.complete is False
    assert record.joint is False


# --------------------------------------------------------------------------
# Leap year requiring 366, supplied only 365
# --------------------------------------------------------------------------


def test_leap_year_missing_a_day_is_not_complete(tmp_path):
    year = 2004
    assert calendar_module.isleap(year)
    leap_day = date(2004, 2, 29)
    # Skip Feb 29 consistently on both sides so parity still matches on every
    # date they DO share -- this isolates the completeness criterion.
    sse_rows = _exchange_rows("SSE", [year], skip_dates=frozenset({leap_day}))
    szse_rows = _exchange_rows("SZSE", [year], skip_dates=frozenset({leap_day}))

    by_year = {year: {"SSE": sse_rows, "SZSE": szse_rows}}
    store = _write_store(tmp_path, by_year)
    result = census.build_census(store)

    (record,) = result.years
    assert record.want == 366
    assert record.sse_unique == 365
    assert record.szse_unique == 365
    assert record.parity_mismatch == 0
    assert record.complete is False
    assert record.joint is False
    assert result.epoch is None


# --------------------------------------------------------------------------
# Trailing decision rule
# --------------------------------------------------------------------------


def test_decision_rule_is_trailing_not_earliest_pass(tmp_path):
    year1, year2, year3 = 2001, 2002, 2003
    sse_rows = _exchange_rows("SSE", [year1, year2, year3])
    szse_rows = _exchange_rows("SZSE", [year1, year2, year3])

    # Break year2 only: flip one shared Wednesday's is_open on SZSE.
    for row in szse_rows:
        d = date.fromisoformat(row["cal_date"])
        if d.year == year2 and d.weekday() == 2 and row["is_open"] == 1:
            row["is_open"] = 0
            break

    by_year = {year1: {"SSE": [], "SZSE": []}, year2: {}, year3: {}}
    for row in sse_rows:
        by_year.setdefault(int(row["cal_date"][:4]), {}).setdefault("SSE", []).append(row)
    for row in szse_rows:
        by_year.setdefault(int(row["cal_date"][:4]), {}).setdefault("SZSE", []).append(row)

    store = _write_store(tmp_path, by_year)
    result = census.build_census(store)

    by_year_record = {r.year: r for r in result.years}
    assert by_year_record[year1].joint is True
    assert by_year_record[year2].joint is False
    assert by_year_record[year3].joint is True

    # year1 is jointly complete but year2 breaks the trailing run, so the
    # epoch must be year3, never year1.
    assert result.epoch == year3


# --------------------------------------------------------------------------
# --fail-under-epoch
# --------------------------------------------------------------------------


def test_fail_under_epoch_nonzero_when_epoch_is_later_than_pin(tmp_path, capsys):
    store = _clean_two_year_store(tmp_path, years=(2001, 2002))
    # First year (2001) is broken so the epoch becomes 2002.
    cal_dir = census._calendar_dir(store)
    frame = pd.read_parquet(cal_dir / "year=2001.parquet")
    frame.loc[frame.index[0], "is_open"] = 1 - frame.loc[frame.index[0], "is_open"]
    # Make sure the flipped row is a genuinely shared date for both exchanges
    # so it actually produces a parity mismatch rather than a no-op.
    frame.to_parquet(cal_dir / "year=2001.parquet")

    exit_code = census.main(
        [
            "--store",
            str(store),
            "--fail-under-epoch",
            "2001",
        ]
    )
    out = capsys.readouterr().out
    assert "EARLIEST_JOINTLY_COMPLETE_EPOCH:" in out
    assert exit_code != 0


def test_fail_under_epoch_zero_when_epoch_meets_pin(tmp_path, capsys):
    store = _clean_two_year_store(tmp_path, years=(2001, 2002))
    exit_code = census.main(
        [
            "--store",
            str(store),
            "--fail-under-epoch",
            "2001",
        ]
    )
    out = capsys.readouterr().out
    assert "EARLIEST_JOINTLY_COMPLETE_EPOCH: 2001" in out
    assert exit_code == 0


# --------------------------------------------------------------------------
# CLI plumbing: store errors, JSON/Markdown receipts, stdout ordering
# --------------------------------------------------------------------------


def test_main_returns_nonzero_on_unreadable_store(tmp_path, capsys):
    missing_store = tmp_path / "does_not_exist"
    exit_code = census.main(["--store", str(missing_store)])
    assert exit_code != 0
    out = capsys.readouterr().out
    assert "EARLIEST_JOINTLY_COMPLETE_EPOCH" not in out


def test_main_writes_json_and_markdown_receipts(tmp_path, capsys):
    store = _clean_two_year_store(tmp_path, years=(2001, 2002))
    json_path = tmp_path / "out" / "receipt.json"
    md_path = tmp_path / "out" / "receipt.md"

    exit_code = census.main(
        [
            "--store",
            str(store),
            "--json",
            str(json_path),
            "--markdown",
            str(md_path),
        ]
    )
    assert exit_code == 0

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["earliest_jointly_complete_epoch"] == 2001
    assert payload["store"] == str(store)
    assert len(payload["years"]) == 2
    assert "decision_rule" in payload
    assert "integrity" in payload
    assert payload["integrity"]["duplicate_key_rows"] == 0

    markdown_text = md_path.read_text(encoding="utf-8")
    assert "EARLIEST_JOINTLY_COMPLETE_EPOCH: 2001" in markdown_text


def test_main_prints_full_year_table_before_decision_line(tmp_path, capsys):
    store = _clean_two_year_store(tmp_path, years=(2001, 2002))
    exit_code = census.main(["--store", str(store)])
    assert exit_code == 0
    out = capsys.readouterr().out

    year_table_pos = out.index("2001")
    decision_pos = out.index("EARLIEST_JOINTLY_COMPLETE_EPOCH:")
    assert year_table_pos < decision_pos
    assert "2002" in out[:decision_pos]


def test_year_with_zero_rows_for_an_exchange_never_crashes(tmp_path):
    year = 2001
    sse_rows = _exchange_rows("SSE", [year])
    by_year = {year: {"SSE": sse_rows}}  # no SZSE key at all
    store = _write_store(tmp_path, by_year)

    result = census.build_census(store)
    (record,) = result.years
    assert record.szse_unique == 0
    assert record.szse_open == 0
    assert record.parity_mismatch == -1
    assert record.joint is False


def test_duplicate_keys_are_detected(tmp_path):
    year = 2001
    sse_rows = _exchange_rows("SSE", [year])
    szse_rows = _exchange_rows("SZSE", [year])
    # Duplicate one SSE row (same exchange + cal_date key).
    sse_rows.append(dict(sse_rows[5]))

    by_year = {year: {"SSE": sse_rows, "SZSE": szse_rows}}
    store = _write_store(tmp_path, by_year)
    result = census.build_census(store)

    assert result.integrity.duplicate_key_rows == 1


def test_partition_impurity_is_detected(tmp_path):
    # Put a 2002 row inside the year=2001.parquet partition file.
    store = tmp_path / "china_tushare_spine"
    cal_dir = census._calendar_dir(store)
    rows = _exchange_rows("SSE", [2001]) + _exchange_rows("SZSE", [2001])
    rows.append(
        {
            "exchange": "SSE",
            "cal_date": "2002-01-15",
            "is_open": 1,
            "pretrade_date": "2002-01-14",
        }
    )
    _write_partition(cal_dir, 2001, rows)

    result = census.build_census(store)
    assert result.integrity.partition_purity_ok is False
    assert result.integrity.partition_impure_rows == 1


def test_no_network_imports_in_module_source():
    """The census must never import a TuShare client or any network library.

    Only ``import``/``from ... import`` statement lines are checked -- the
    module's docstring legitimately *mentions* ``china_tushare_spine.py`` in
    prose to explain why the census exists, which must not trip this check.
    """
    source = Path(census.__file__).read_text(encoding="utf-8")
    forbidden = ("tushare", "requests", "urllib.request", "httpx", "socket")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    lowered_imports = "\n".join(import_lines).lower()
    for token in forbidden:
        assert token not in lowered_imports, f"forbidden network-shaped import found: {token}"
    # Belt-and-suspenders: the module must never import the collector itself.
    assert "china_tushare_spine" not in lowered_imports


def test_no_hardcoded_epoch_constant():
    # The module must not define a literal epoch year constant; the epoch is
    # always a computed field on CensusResult, never a module-level default.
    assert not hasattr(census, "EPOCH")
    assert not hasattr(census, "CALENDAR_EPOCH")
    assert not hasattr(census, "DEFAULT_EPOCH")
