"""Tripwire for a basket-membership snapshot plane going quietly cold.

WHY THIS EXISTS
---------------
The THS point-in-time membership store held TWO snapshots — 2026-06-30 and
2026-07-08 — and stopped, while every signal stayed green for six weeks. The
composition that produced it is worth stating exactly, because each part is
individually correct:

  * ``scripts/build_baskets_china_ths.py --snapshot`` runs nightly in asia-close
    band A. It hashes today's ``membership.json`` against the newest dated
    side-car, matches, logs "membership unchanged — dedup skip", exits 0.
    Content-dedup is right: membership moves on the vendor's schedule, not the
    trading calendar, and stamping ~3,500 identical rows a night would add
    ~1.3M rows/year that say nothing.
  * ``membership.json`` had not moved since 2026-06-30 because the two things
    that refresh it — the scraper ``collectors/china_ths_concepts.py`` and the
    seeder ``scripts/seed_china_ths_baskets.py`` — appeared in NO workflow at
    all. The 2026-07-08 file was a hand-run bundled with a feature commit.
  * A deduping writer and an unwired writer leave the IDENTICAL trace on disk:
    nothing. So ~35 green nights in a row proved only that the step ran.

That is the shape this guard is built against, and it is why the first axis is
not "is the store fresh" but "did the writer RUN". A freshness check that only
looks at the newest snapshot cannot see the difference between a plane that is
healthy-and-unchanged and a plane whose producer has been dead for a month.

THE THREE AXES
--------------
  cadence     — ``<suite>/snapshots/_cadence.json`` is rewritten by the snapshot
                writer on EVERY run, including the dedup skip. A stale
                ``checked_at`` means the writer itself stopped running: unwired
                step, dead lane, renamed module. This is the axis that would
                have caught the incident above on day four.
  source      — THS only. The weekly re-scrape
                (``scripts/scrape_ths_weekly.py``) leaves a receipt per attempt;
                a receipt with ``complete: true`` is the only thing that
                promotes a new raw side-car. No complete scrape inside the
                budget means the INPUT is frozen even if the writer is running
                perfectly — the second half of the incident, which the cadence
                axis alone cannot see.
  coherence   — the PIT parquet's newest ``snapshot_date`` must not lag the
                newest dated side-car. Catches the backfill silently not
                running: side-cars accrue on disk while the queryable store
                everybody reads stays where it was.

VERDICTS
--------
Advisory, always exit 0 (house idiom, mirroring
``scripts/check_tushare_freshness.py``): one cold membership plane must not red
a collection lane that landed every other store. The teeth are the
``::warning`` annotation and the ops-alert push.

A MISSING store is INDETERMINATE, never a breach — one ``::notice``, no alert.
Sparse agent checkouts do not carry ``data/``, and a suite's very first run has
no stamp, no receipt and no parquet by construction; calling either of those a
breach would train every reader to ignore this guard inside a week.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config  # noqa: E402

SUITE_THS = "baskets_china_ths"
SUITE_US = "baskets"

#: Suites audited, with the human label used in annotations.
SUITES: tuple[tuple[str, str], ...] = (
    (SUITE_THS, "同花顺 concept baskets"),
    (SUITE_US, "US thematic baskets"),
)

#: Days the snapshot WRITER may go without running before we say something.
#: 4 covers a weekend plus a holiday plus the lane's own once-a-day gate, so a
#: healthy nightly never trips it.
CADENCE_MAX_DAYS = 4

#: Days without a COMPLETE THS scrape receipt before we say something. The
#: re-scrape is weekly, so 10 is one missed week plus slack — a single throttled
#: Saturday stays quiet, two in a row do not.
SCRAPE_MAX_DAYS = 10

#: Only the THS suite has a scraped source. The US suite's membership.json is
#: hand-curated, so "the source is stale" is not a fault there — it is the
#: normal state of a document nobody edited this month.
SOURCE_AUDITED: frozenset[str] = frozenset({SUITE_THS})

FRESH = "fresh"
BREACH = "breach"
INDETERMINATE = "indeterminate"


# ---------------------------------------------------------------------------
# Pure evaluators — every one takes its inputs and its clock, so the tests need
# neither a live store nor a wall clock.
# ---------------------------------------------------------------------------

def _parse_ts(value: object) -> datetime | None:
    """A UTC datetime from an ISO-8601 stamp (date or date-time), else None."""
    s = str(value or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def evaluate_cadence(cadence: dict | None, now: datetime,
                     max_days: int = CADENCE_MAX_DAYS) -> tuple[str, str]:
    """(verdict, detail) for "did the snapshot writer run recently".

    An unparseable ``checked_at`` is a BREACH, not indeterminate: the file exists,
    so the writer is wired — it is the stamp that is wrong, and a guard that reads
    a malformed date as "no information" is the shape that lets a broken writer
    stay quiet forever.
    """
    if not cadence:
        return INDETERMINATE, "no _cadence.json (writer has never run here, or sparse checkout)"
    checked = _parse_ts(cadence.get("checked_at"))
    if checked is None:
        return BREACH, f"_cadence.json has an unreadable checked_at ({cadence.get('checked_at')!r})"
    age = (now - checked).total_seconds() / 86400.0
    detail = (f"snapshot writer last ran {checked:%Y-%m-%dT%H:%M:%SZ} "
              f"({age:.1f}d ago; budget {max_days}d)")
    return (BREACH if age > max_days else FRESH), detail


def evaluate_scrape(receipts: list[dict], now: datetime,
                    max_days: int = SCRAPE_MAX_DAYS) -> tuple[str, str]:
    """(verdict, detail) for "has a COMPLETE source scrape landed recently".

    Only ``complete: true`` receipts count. A run of ``complete: false`` receipts
    means the scrape is being attempted and failing, which is a breach with a
    different cause than no receipts at all — so the detail says which.
    """
    if not receipts:
        return INDETERMINATE, "no scrape receipts yet (re-scrape has never completed a run here)"
    dated = [(_parse_ts(r.get("date")), r) for r in receipts]
    complete = sorted(
        [(d, r) for d, r in dated if d is not None and r.get("complete") is True],
        key=lambda pair: pair[0])
    if not complete:
        attempts = len(receipts)
        newest = max((d for d, _r in dated if d is not None), default=None)
        return BREACH, (
            f"{attempts} scrape attempt(s) on record and NONE complete"
            + (f" (newest {newest:%Y-%m-%d})" if newest else "")
            + " — a partial scrape promotes no side-car, so the membership input is frozen")
    newest_dt, newest_receipt = complete[-1]
    age = (now - newest_dt).total_seconds() / 86400.0
    detail = (f"newest COMPLETE scrape {newest_dt:%Y-%m-%d} "
              f"({age:.1f}d ago; budget {max_days}d; "
              f"{newest_receipt.get('concepts_fetched')}/"
              f"{newest_receipt.get('concepts_attempted')} boards)")
    return (BREACH if age > max_days else FRESH), detail


def evaluate_coherence(parquet_max_date: str | None,
                       newest_side_car: str | None) -> tuple[str, str]:
    """(verdict, detail) for "did the side-cars reach the queryable store".

    Both sides missing is indeterminate. A side-car with no parquet at all is a
    BREACH: the ingest is the thing being audited, so "the store does not exist"
    is the strongest possible evidence that it never ran, not an absence of
    evidence.
    """
    if not newest_side_car:
        return INDETERMINATE, "no dated side-cars yet"
    if not parquet_max_date:
        return BREACH, (f"newest side-car {newest_side_car} but membership_history.parquet "
                        "is absent/empty — nothing is folding side-cars into the PIT store")
    if str(parquet_max_date) < str(newest_side_car):
        return BREACH, (f"PIT parquet stops at {parquet_max_date} while the newest side-car "
                        f"is {newest_side_car} — the backfill is not running")
    return FRESH, f"PIT parquet at {parquet_max_date} covers the newest side-car {newest_side_car}"


# ---------------------------------------------------------------------------
# Disk readers (thin — everything they return feeds a pure evaluator above)
# ---------------------------------------------------------------------------

def _read_cadence(suite: str) -> dict | None:
    p = config.data_dir() / suite / "snapshots" / "_cadence.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:  # noqa: BLE001 — an unreadable stamp is "no stamp"
        return None


def _read_receipts(suite: str) -> list[dict]:
    d = config.data_dir() / suite / "receipts"
    out: list[dict] = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("scrape_*.json")):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(blob, dict):
            out.append(blob)
    return out


def _newest_side_car(suite: str) -> str | None:
    d = config.data_dir() / suite / "snapshots"
    if not d.is_dir():
        return None
    dated = sorted(p.stem for p in d.glob("????-??-??.json"))
    return dated[-1] if dated else None


def _parquet_max_date(suite: str) -> str | None:
    p = config.data_dir() / suite / "membership_history.parquet"
    if not p.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_parquet(p, columns=["snapshot_date"])
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    return str(df["snapshot_date"].astype(str).max())


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def _push_alert(message: str) -> None:
    """Ops-alert push, FAIL-OPEN: the ::warning annotation is the guaranteed teeth."""
    try:
        from engine.alert_triage import push_ops_alert  # noqa: PLC0415

        push_ops_alert(
            source="check_membership_snapshot_freshness",
            type_="membership_snapshot_stale",
            message=message,
            severity="major",
            lane="collect",
            window_hours=20,  # suppress repeats inside one nightly window
        )
    except Exception:  # noqa: BLE001 — unreachable triage must not silence the guard
        pass


def audit_suite(suite: str, now: datetime) -> list[tuple[str, str, str]]:
    """[(axis, verdict, detail)] for one suite, read off disk."""
    rows = [("cadence", *evaluate_cadence(_read_cadence(suite), now))]
    if suite in SOURCE_AUDITED:
        rows.append(("source", *evaluate_scrape(_read_receipts(suite), now)))
    rows.append(("coherence", *evaluate_coherence(_parquet_max_date(suite),
                                                  _newest_side_car(suite))))
    return rows


def run(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    breaches: list[str] = []
    unknowns: list[str] = []
    for suite, label in SUITES:
        for axis, verdict, detail in audit_suite(suite, now):
            line = f"{suite} [{axis}]: {detail}"
            if verdict == BREACH:
                breaches.append(line)
            elif verdict == INDETERMINATE:
                unknowns.append(line)
            else:
                print(f"membership snapshot OK: {label} [{axis}] — {detail}")
    if unknowns:
        # Bare print, line-start, flushed: a logger prefixes the line and GitHub
        # silently drops the annotation (tests/test_gh_annotation_line_start.py).
        print("::notice title=membership snapshot indeterminate::"
              + "; ".join(unknowns)
              + ". Absent stores are NOT a breach — a sparse checkout carries no data/, "
                "and a suite's first run has no stamp, receipt or parquet by construction.",
              flush=True)
    if breaches:
        msg = ("; ".join(breaches)
               + ". A content-deduped snapshot writer that has been unwired and one whose "
                 "input has not changed leave the same trace on disk (nothing), which is how "
                 "the THS PIT store sat at 2 snapshots for six weeks with the nightly step "
                 "green ~35 nights running. Check that asia-close.yml still runs the weekly "
                 "THS re-scrape + `build_baskets_china_ths --snapshot`, and daily.yml still "
                 "runs `build_baskets --snapshot`.")
        print(f"::warning title=membership snapshot cadence stalled::{msg}", flush=True)
        _push_alert(msg)
    return 0  # advisory: never red a collection lane over a cold membership plane


def selftest() -> int:
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    fresh_stamp = {"checked_at": "2026-08-19T09:00:00Z"}
    old_stamp = {"checked_at": "2026-07-08T09:00:00Z"}
    complete = {"date": "2026-08-15", "complete": True,
                "concepts_fetched": 373, "concepts_attempted": 373}
    partial = {"date": "2026-08-15", "complete": False,
               "concepts_fetched": 200, "concepts_attempted": 373}
    checks = [
        (evaluate_cadence(None, now)[0] == INDETERMINATE,
         "a missing stamp is indeterminate, never a breach"),
        (evaluate_cadence(fresh_stamp, now)[0] == FRESH, "yesterday's run is fresh"),
        (evaluate_cadence(old_stamp, now)[0] == BREACH,
         "the 2026-07-08 freeze must read as a breach"),
        (evaluate_cadence({"checked_at": "not-a-date"}, now)[0] == BREACH,
         "an unreadable stamp must not read fresh"),
        (evaluate_scrape([], now)[0] == INDETERMINATE, "no receipts is indeterminate"),
        (evaluate_scrape([complete], now)[0] == FRESH, "a recent complete scrape is fresh"),
        (evaluate_scrape([partial], now)[0] == BREACH,
         "attempts that never complete are a breach — no side-car is promoted"),
        (evaluate_scrape([{"date": "2026-06-30", "complete": True}], now)[0] == BREACH,
         "a complete scrape older than the budget is a breach"),
        # The defect this guard exists for: the writer running perfectly on a
        # frozen input. Cadence alone reads FRESH there — only the source axis sees it.
        (evaluate_cadence(fresh_stamp, now)[0] == FRESH
         and evaluate_scrape([{"date": "2026-06-30", "complete": True}], now)[0] == BREACH,
         "a live writer on a frozen source must still breach"),
        (evaluate_coherence(None, None)[0] == INDETERMINATE, "an empty plane is indeterminate"),
        (evaluate_coherence(None, "2026-08-15")[0] == BREACH,
         "side-cars with no parquet at all is a breach"),
        (evaluate_coherence("2026-07-08", "2026-08-15")[0] == BREACH,
         "a parquet behind the newest side-car is a breach"),
        (evaluate_coherence("2026-08-15", "2026-08-15")[0] == FRESH, "caught up is fresh"),
        (evaluate_coherence("2026-08-16", "2026-08-15")[0] == FRESH,
         "a parquet AHEAD of the side-cars is fine — it also stamps membership.json direct"),
    ]
    bad = [m for ok, m in checks if not ok]
    for m in bad:
        print(f"selftest FAIL: {m}")
    print("check_membership_snapshot_freshness selftest: "
          + ("OK" if not bad else f"{len(bad)} failure(s)"))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true",
                    help="run verdict pins on synthetic inputs and exit")
    a = ap.parse_args(argv)
    return selftest() if a.selftest else run()


if __name__ == "__main__":
    raise SystemExit(main())
