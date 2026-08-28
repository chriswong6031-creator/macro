#!/usr/bin/env python3
"""Census: earliest jointly-complete SSE/SZSE mainland trading calendar epoch.

WHY THIS EXISTS.  The CN limit-up alpha exact plane currently anchors its
calendar to ``CALENDAR_HISTORY_START = date(1991, 1, 1)``
(``collectors/china_tushare_spine.py``), then demands exact SSE/SZSE
calendar-day equality from that anchor forward.  SZSE calendar collection for
1991 lands 182 rows against SSE's 365 for the same civil year, so that check
fails closed and blocks every downstream stage (see
``research/cn_limit_alpha_sol`` and the CN limit-alpha program handoffs for
the incident record).  The AI CEO ruled that the plane may re-anchor only to a
frozen "jointly complete mainland calendar epoch" -- and only after an
outcome-blind source census independently proves that epoch, year by year,
against the landed private spine store.

THIS SCRIPT IS THAT CENSUS.  It measures; it never decides the epoch value
and it never edits the collector.  A separate PR consumes this script's
output to change ``CALENDAR_HISTORY_START`` (or whatever constant replaces
it) -- that is explicitly out of scope here.

OUTCOME-BLINDNESS.  Every calendar year present in the store is printed to
stdout, in ascending year order, before any decision is made or reported.
A year that fails a criterion is printed exactly like a year that passes it;
nothing is filtered, summarized away, or hidden ahead of the full table.

NETWORK-FREE.  This module imports no TuShare client, makes no HTTP request,
and touches no vendor token.  It only reads Parquet partitions and one JSON
state file already landed on disk under the private store root.  It is
strictly read-only with respect to that store -- it never writes into it.

SIX RULING CRITERIA (measured per calendar year, per exchange, and jointly):
  1. partition purity      -- every row lands in the partition file matching
                               its own calendar year (``reference/trade_calendar/
                               year=YYYY.parquet`` holds only calendar year YYYY).
  2. no duplicate keys      -- (exchange, cal_date) is unique across the store.
  3. per-exchange completeness -- each exchange reports exactly 365 (366 in a
                               leap year) distinct civil dates for the year.
  4. open/closed parity     -- on every civil date both exchanges observe,
                               ``is_open`` agrees (``-1`` sentinel = no shared
                               dates at all -- never treated as passing).
  5. pretrade_date chain    -- each exchange's ``pretrade_date`` equals the
                               most recent strictly-prior open session (the
                               first-ever row per exchange is unverifiable and
                               is skipped, never counted as a violation).
  6. continuity              -- no missing civil date inside each exchange's
                               own observed span.

DECISION RULE (applied only after the full per-year table above is emitted):
the earliest year Y such that EVERY year from Y through the last observed
year is jointly complete (criteria 3+4 combined, "joint").  This is a
TRAILING rule: an early jointly-complete year followed by a later broken year
is never selected as the epoch -- only an unbroken run reaching the most
recent observed year counts.

Usage (read-only, no network)::

    python3 scripts/research/cn_limit_calendar_epoch_census.py
    python3 scripts/research/cn_limit_calendar_epoch_census.py \
        --store /path/to/china_tushare_spine \
        --json /tmp/epoch_census.json --markdown /tmp/epoch_census.md \
        --fail-under-epoch 1992
"""

from __future__ import annotations

import argparse
import calendar as calendar_module
import json
import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

SCHEMA_VERSION = "cn_limit_calendar_epoch_census/v1"

EXCHANGES: tuple[str, ...] = ("SSE", "SZSE")
REQUIRED_CALENDAR_COLUMNS = frozenset({"exchange", "cal_date", "is_open", "pretrade_date"})

# Mirrors ``collectors.china_tushare_spine.DEFAULT_STORE`` without importing
# that module -- this script must stay independent of collector internals.
DEFAULT_STORE = Path(
    os.environ.get(
        "CN_TUSHARE_SPINE_STORE",
        str(Path.home() / ".local" / "share" / "macro-dashboard" / "china_tushare_spine"),
    )
)

DECISION_RULE_PROSE = (
    "Earliest year Y such that every year from Y through the last observed "
    "year is jointly complete (both exchanges report the exact civil-day "
    "count for that year -- 365, or 366 in a leap year -- and agree on "
    "is_open for every civil date both exchanges observe). This is a "
    "trailing rule: an early jointly-complete year followed by a later "
    "broken year is never selected; only an unbroken run reaching the most "
    "recently observed year counts as the epoch."
)


class CalendarStoreError(RuntimeError):
    """Raised when the store's trade-calendar partitions cannot be read."""


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _calendar_dir(store: Path) -> Path:
    return store / "reference" / "trade_calendar"


def load_calendar_frame(store: Path) -> pd.DataFrame:
    """Load and concatenate every ``year=YYYY.parquet`` trade-calendar partition.

    Each row is tagged with its own partition's declared year
    (``__partition_year``, from the filename) and its true calendar year
    (``year``, derived from ``cal_date``) so partition-purity violations are
    detectable rather than silently merged away.
    """

    cal_dir = _calendar_dir(store)
    if not cal_dir.is_dir():
        raise CalendarStoreError(f"trade calendar directory not found: {cal_dir}")

    paths = sorted(cal_dir.glob("year=*.parquet"))
    if not paths:
        raise CalendarStoreError(f"no year=*.parquet partitions under {cal_dir}")

    frames: list[pd.DataFrame] = []
    for path in paths:
        try:
            partition_year = int(path.stem.split("=", 1)[1])
        except (IndexError, ValueError) as exc:
            raise CalendarStoreError(f"unparseable partition filename: {path.name}") from exc
        try:
            stamped = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001 - store I/O failure must fail the census
            raise CalendarStoreError(f"failed to read {path}: {exc}") from exc
        missing = REQUIRED_CALENDAR_COLUMNS - set(stamped.columns)
        if missing:
            raise CalendarStoreError(f"{path} missing required columns: {sorted(missing)}")
        stamped = stamped.copy()
        stamped["__partition_year"] = partition_year
        frames.append(stamped)

    frame = pd.concat(frames, ignore_index=True)
    try:
        frame["date"] = pd.to_datetime(frame["cal_date"], errors="raise").dt.date
    except (ValueError, TypeError) as exc:
        raise CalendarStoreError(f"unparseable cal_date value under {cal_dir}: {exc}") from exc
    frame["year"] = frame["date"].map(lambda d: d.year)
    return frame


# --------------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExchangeIntegrity:
    exchange: str
    rows: int
    span_start: str | None
    span_end: str | None
    pretrade_violations: tuple[dict[str, str], ...]
    missing_dates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "rows": self.rows,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "pretrade_violation_count": len(self.pretrade_violations),
            "pretrade_violations": list(self.pretrade_violations),
            "missing_civil_date_count": len(self.missing_dates),
            "missing_civil_dates": list(self.missing_dates),
        }


@dataclass(frozen=True)
class IntegrityReport:
    partition_purity_ok: bool
    partition_impure_rows: int
    duplicate_key_rows: int
    exchanges: dict[str, ExchangeIntegrity]

    def to_dict(self) -> dict[str, Any]:
        return {
            "partition_purity_ok": self.partition_purity_ok,
            "partition_impure_rows": self.partition_impure_rows,
            "duplicate_key_rows": self.duplicate_key_rows,
            "exchanges": {ex: rep.to_dict() for ex, rep in self.exchanges.items()},
        }


def _pretrade_violations(sub: pd.DataFrame) -> tuple[dict[str, str], ...]:
    """Walk one exchange's rows ascending by date, verifying the pretrade chain.

    ``pretrade_date`` must equal the most recent STRICTLY PRIOR open session.
    The first row in the exchange's history is unverifiable (its predecessor
    is out of range) and is skipped rather than counted as a violation.
    """

    ordered = sub.sort_values("date")
    violations: list[dict[str, str]] = []
    last_open: date | None = None
    for row in ordered.itertuples(index=False):
        row_date = row.date
        is_open = row.is_open
        pretrade = row.pretrade_date
        if last_open is not None and str(pretrade) != last_open.isoformat():
            violations.append(
                {
                    "date": row_date.isoformat(),
                    "pretrade_date": str(pretrade),
                    "expected_prior_open_date": last_open.isoformat(),
                }
            )
        if is_open == 1:
            last_open = row_date
    return tuple(violations)


def _missing_civil_dates(dates: pd.Series) -> tuple[str, ...]:
    """Return civil dates missing inside ``dates``'s own observed span."""

    unique_dates = sorted(set(dates))
    if not unique_dates:
        return ()
    span = pd.date_range(unique_dates[0], unique_dates[-1], freq="D").date
    missing = sorted(set(span) - set(unique_dates))
    return tuple(d.isoformat() for d in missing)


def compute_integrity(frame: pd.DataFrame) -> IntegrityReport:
    impure = frame[frame["year"] != frame["__partition_year"]]
    duplicate_rows = int(frame.duplicated(subset=["exchange", "cal_date"]).sum())

    exchange_reports: dict[str, ExchangeIntegrity] = {}
    for exchange in EXCHANGES:
        sub = frame[frame["exchange"] == exchange]
        if sub.empty:
            exchange_reports[exchange] = ExchangeIntegrity(
                exchange=exchange,
                rows=0,
                span_start=None,
                span_end=None,
                pretrade_violations=(),
                missing_dates=(),
            )
            continue
        span_start = min(sub["date"])
        span_end = max(sub["date"])
        exchange_reports[exchange] = ExchangeIntegrity(
            exchange=exchange,
            rows=int(len(sub)),
            span_start=span_start.isoformat(),
            span_end=span_end.isoformat(),
            pretrade_violations=_pretrade_violations(sub),
            missing_dates=_missing_civil_dates(sub["date"]),
        )

    return IntegrityReport(
        partition_purity_ok=bool(impure.empty),
        partition_impure_rows=int(len(impure)),
        duplicate_key_rows=duplicate_rows,
        exchanges=exchange_reports,
    )


# --------------------------------------------------------------------------
# Per-year records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class YearRecord:
    year: int
    want: int
    sse_unique: int
    sse_open: int
    szse_unique: int
    szse_open: int
    shared: int
    parity_mismatch: int
    complete: bool
    joint: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "want": self.want,
            "SSE": self.sse_unique,
            "SSE_open": self.sse_open,
            "SZSE": self.szse_unique,
            "SZSE_open": self.szse_open,
            "shared": self.shared,
            "parity_mismatch": self.parity_mismatch,
            "complete": self.complete,
            "joint": self.joint,
        }


def compute_year_records(frame: pd.DataFrame) -> list[YearRecord]:
    """Compute one record per true calendar year present in ``frame``.

    A year with zero rows for one exchange reports 0 for that exchange and
    ``joint=False`` -- it never crashes and never imputes a value. ``shared``
    is the count of civil dates both exchanges observe that year;
    ``parity_mismatch`` is the sentinel ``-1`` when there are no shared dates
    at all, which must never be treated as passing.
    """

    years = sorted(int(y) for y in frame["year"].unique())
    records: list[YearRecord] = []
    for year in years:
        block = frame[frame["year"] == year]
        want = 366 if calendar_module.isleap(year) else 365

        unique_count: dict[str, int] = {}
        open_count: dict[str, int] = {}
        is_open_by_date: dict[str, pd.Series] = {}
        for exchange in EXCHANGES:
            sub = block[block["exchange"] == exchange]
            unique_count[exchange] = int(sub["date"].nunique())
            open_count[exchange] = int((sub["is_open"] == 1).sum())
            # Duplicate (exchange, cal_date) keys are counted separately by
            # compute_integrity(); keep the first observation here so a
            # duplicate can never crash the shared-date parity join below.
            is_open_by_date[exchange] = (
                sub.drop_duplicates(subset="date", keep="first").set_index("date")["is_open"]
            )

        sse_series = is_open_by_date["SSE"]
        szse_series = is_open_by_date["SZSE"]
        shared = sse_series.index.intersection(szse_series.index)
        if len(shared):
            parity_mismatch = int((sse_series.loc[shared] != szse_series.loc[shared]).sum())
        else:
            parity_mismatch = -1

        complete = unique_count["SSE"] == want and unique_count["SZSE"] == want
        joint = bool(complete and parity_mismatch == 0)

        records.append(
            YearRecord(
                year=year,
                want=want,
                sse_unique=unique_count["SSE"],
                sse_open=open_count["SSE"],
                szse_unique=unique_count["SZSE"],
                szse_open=open_count["SZSE"],
                shared=int(len(shared)),
                parity_mismatch=parity_mismatch,
                complete=bool(complete),
                joint=joint,
            )
        )
    return records


def decide_epoch(records: Sequence[YearRecord]) -> int | None:
    """Trailing decision rule: earliest year of the unbroken joint run ending
    at the last observed year. ``records`` must be sorted ascending by year."""

    epoch: int | None = None
    for record in reversed(records):
        if not record.joint:
            break
        epoch = record.year
    return epoch


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CensusResult:
    store: Path
    generated_at: str
    years: list[YearRecord]
    integrity: IntegrityReport
    epoch: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "store": str(self.store),
            "generated_at": self.generated_at,
            "years": [record.to_dict() for record in self.years],
            "integrity": self.integrity.to_dict(),
            "decision_rule": DECISION_RULE_PROSE,
            "earliest_jointly_complete_epoch": self.epoch,
        }


def build_census(store: Path) -> CensusResult:
    frame = load_calendar_frame(store)
    integrity = compute_integrity(frame)
    years = compute_year_records(frame)
    epoch = decide_epoch(years)
    generated_at = datetime.now(timezone.utc).isoformat()
    return CensusResult(
        store=store,
        generated_at=generated_at,
        years=years,
        integrity=integrity,
        epoch=epoch,
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _print_year_table(years: Sequence[YearRecord]) -> None:
    header = (
        f"{'year':>6}  {'want':>4}  {'SSE':>6}  {'SSE_open':>8}  "
        f"{'SZSE':>6}  {'SZSE_open':>9}  {'shared':>6}  {'parity':>6}  "
        f"{'complete':>8}  {'joint':>5}"
    )
    print(header, flush=True)
    for record in years:
        print(
            f"{record.year:>6}  {record.want:>4}  {record.sse_unique:>6}  "
            f"{record.sse_open:>8}  {record.szse_unique:>6}  "
            f"{record.szse_open:>9}  {record.shared:>6}  "
            f"{record.parity_mismatch:>6}  {str(record.complete):>8}  "
            f"{str(record.joint):>5}",
            flush=True,
        )


def _print_integrity(integrity: IntegrityReport) -> None:
    print("", flush=True)
    print(
        f"partition purity: {'OK' if integrity.partition_purity_ok else 'IMPURE'} "
        f"({integrity.partition_impure_rows} impure rows); "
        f"duplicates: {integrity.duplicate_key_rows}",
        flush=True,
    )
    for exchange in EXCHANGES:
        report = integrity.exchanges.get(exchange)
        if report is None:
            continue
        print(
            f"{exchange:>4}  rows={report.rows}  "
            f"span={report.span_start}..{report.span_end}  "
            f"pretrade_violations={len(report.pretrade_violations)}  "
            f"missing={len(report.missing_dates)}",
            flush=True,
        )


def _render_markdown(result: CensusResult) -> str:
    epoch_text = str(result.epoch) if result.epoch is not None else "NONE"
    lines = [
        "# CN limit-up alpha -- joint SSE/SZSE calendar epoch census",
        "",
        f"- store: `{result.store}`",
        f"- generated_at: {result.generated_at}",
        f"- decision rule: {DECISION_RULE_PROSE}",
        f"- **EARLIEST_JOINTLY_COMPLETE_EPOCH: {epoch_text}**",
        "",
        "## Per-year",
        "",
        "| year | want | SSE | SSE_open | SZSE | SZSE_open | shared | "
        "parity_mismatch | complete | joint |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in result.years:
        lines.append(
            f"| {record.year} | {record.want} | {record.sse_unique} | "
            f"{record.sse_open} | {record.szse_unique} | {record.szse_open} | "
            f"{record.shared} | {record.parity_mismatch} | {record.complete} | "
            f"{record.joint} |"
        )
    lines += [
        "",
        "## Integrity",
        "",
        f"- partition purity: "
        f"{'OK' if result.integrity.partition_purity_ok else 'IMPURE'} "
        f"({result.integrity.partition_impure_rows} impure rows)",
        f"- duplicate keys: {result.integrity.duplicate_key_rows}",
        "",
    ]
    for exchange in EXCHANGES:
        report = result.integrity.exchanges.get(exchange)
        if report is None:
            continue
        lines.append(
            f"- {exchange}: rows={report.rows} "
            f"span={report.span_start}..{report.span_end} "
            f"pretrade_violations={len(report.pretrade_violations)} "
            f"missing_civil_dates={len(report.missing_dates)}"
        )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=DEFAULT_STORE,
        help="private TuShare spine store root (default: %(default)s)",
    )
    parser.add_argument(
        "--json", dest="json_out", type=Path, default=None, help="write the JSON receipt here"
    )
    parser.add_argument(
        "--markdown",
        dest="markdown_out",
        type=Path,
        default=None,
        help="write the Markdown receipt here",
    )
    parser.add_argument(
        "--fail-under-epoch",
        type=int,
        default=None,
        metavar="YYYY",
        help="exit non-zero if the computed epoch is later than this pinned year",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        result = build_census(args.store)
    except CalendarStoreError as exc:
        print(f"::error title=cn-limit-calendar-epoch-census::{exc}", flush=True)
        return 2

    print(
        f"joint SSE/SZSE calendar epoch census | store={result.store} | "
        f"years {result.years[0].year}..{result.years[-1].year} "
        f"(n={len(result.years)})",
        flush=True,
    )
    _print_year_table(result.years)
    _print_integrity(result.integrity)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.json_out}", flush=True)

    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(_render_markdown(result), encoding="utf-8")
        print(f"wrote {args.markdown_out}", flush=True)

    exit_code = 0
    if args.fail_under_epoch is not None:
        if result.epoch is None or result.epoch > args.fail_under_epoch:
            print(
                f"::error title=cn-limit-calendar-epoch-census::computed epoch "
                f"{result.epoch} is later than the pinned expectation "
                f"{args.fail_under_epoch}",
                flush=True,
            )
            exit_code = 1

    print("", flush=True)
    epoch_text = str(result.epoch) if result.epoch is not None else "NONE"
    print(f"EARLIEST_JOINTLY_COMPLETE_EPOCH: {epoch_text}", flush=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
