"""scripts/grade_qledger.py — nightly qledger grading job (§2.2 W1-B1).

Desk-independent: loads every open claim from data/qledger/claims.jsonl, grades
each at every in-scope horizon (5/21/63d capped by claim horizon_d) once enough
trading days have elapsed and price coverage exists, then writes the result to
data/qledger/grades.jsonl and updates site/qledger/track_record.json.

IDEMPOTENT: a (claim_id, horizon_d) pair that already has a grade row is never
double-graded. Re-running the job on the same day is safe.

HEALTH: always emits a one-line summary to stdout and writes
data/qledger/run_status.json — broken != quiet.

WIRING (end-of-collect hook):
    The job is registered as an end-of-collect step in scripts/collect.py, so it
    runs nightly as part of the collection pipeline without a separate scheduler.
    It is also runnable standalone:

        python scripts/grade_qledger.py            # use repo root
        python scripts/grade_qledger.py --root /other/root
        python scripts/grade_qledger.py --dry-run  # compute only, no writes

PRICE FALLBACK ORDER (reusing engine.ai_desk._close_series):
  1. data/yahoo/<ticker>.parquet  — ~153 major names, SPY/XL* etc.
  2. S&P-1500 breadth-cache       — wider coverage for entity claims
  3. data/baskets/ohlcv/<ticker>.parquet — per-member basket OHLCV
  4. 510300.SS parquet            — CN macro bench (via breadth cache or yahoo)

If subject OR bench price is unavailable the horizon is counted in
n_blocked_by_coverage (not silently dropped) and the run_status records it.
Ungradeable claims (EVENT_DATE/SNAPSHOT_DATE timestamp_quality) are counted in
n_ungradeable.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Allow running as a top-level script (`python scripts/grade_qledger.py`).
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import qledger as q
from lib import config

log = logging.getLogger("grade_qledger")

_STATUS_FILE = ("data", "qledger", "run_status.json")


# --------------------------------------------------------------------------- #
# idempotency helper
# --------------------------------------------------------------------------- #
def _existing_grade_keys(root: Path) -> set[tuple]:
    """Set of (claim_id, horizon_d) pairs already written to grades.jsonl."""
    return {
        (g.get("claim_id"), int(g.get("horizon_d", -1)))
        for g in q.load_grades(root)
        if g.get("claim_id") is not None
    }


# --------------------------------------------------------------------------- #
# main grader
# --------------------------------------------------------------------------- #
def run(root: Path | str | None = None, today: date | None = None,
        dry_run: bool = False) -> dict:
    """Grade all open claims, write grades + track_record, return a summary dict.

    Parameters
    ----------
    root    : repo root (defaults to lib.config.ROOT).
    today   : reference date for maturity check (defaults to date.today()).
    dry_run : compute grades but do NOT write any files.

    Returns
    -------
    dict with keys: n_open, n_graded_today, n_blocked_by_coverage,
                    n_ungradeable, n_already_graded, generated_at.
    """
    root = Path(root) if root else config.ROOT
    today_dt = today or date.today()

    claims = q.load_claims(root)
    open_claims = [c for c in claims if c.get("status") == q.STATUS_OPEN]
    existing_keys = _existing_grade_keys(root)

    grades_p = root.joinpath(*q._GRADES_FILE)
    if not dry_run:
        grades_p.parent.mkdir(parents=True, exist_ok=True)

    n_open = len(open_claims)
    n_graded_today = 0
    n_blocked_by_coverage = 0
    n_ungradeable = 0
    n_already_graded = 0

    # Collect new grade rows; we'll write them in a single pass.
    new_rows: list[dict] = []

    for claim in open_claims:
        cid = claim.get("claim_id")

        # Check gradeable at all (timestamp_quality gate).
        gradeable, _ = q._embargo_ok(claim)
        if not gradeable:
            n_ungradeable += 1
            continue

        scope = claim.get("scope") or {}
        subject = scope.get("key")
        bench = claim.get("bench") or q._DEFAULT_BENCH
        control = claim.get("control")
        start = q._entry_date(claim)

        try:
            horizon_d = int(claim.get("horizon_d"))
        except Exception:  # noqa: BLE001
            n_ungradeable += 1
            continue

        for h in q.in_scope_horizons(horizon_d):
            key = (cid, h)
            if key in existing_keys:
                n_already_graded += 1
                continue

            legs = [subject, bench] + ([control] if control else [])
            if not q._matured(root, start, h, today_dt, legs):
                # Not yet elapsed or price not yet available — count as blocked.
                n_blocked_by_coverage += 1
                continue

            # grade_claim handles all the price maths; we filter to this horizon.
            rows = q.grade_claim(claim, root=root, today=today_dt)
            matched = [r for r in rows if int(r.get("horizon_d", -1)) == h]

            if matched:
                new_rows.extend(matched)
                n_graded_today += len(matched)
            else:
                # Matured but prices unavailable → coverage miss.
                n_blocked_by_coverage += 1

    # Write grades (append-only).
    if new_rows and not dry_run:
        with grades_p.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Recompute and emit track_record.json.
    if not dry_run:
        q.emit_track_record(root)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today_dt.isoformat(),
        "n_open": n_open,
        "n_graded_today": n_graded_today,
        "n_blocked_by_coverage": n_blocked_by_coverage,
        "n_ungradeable": n_ungradeable,
        "n_already_graded": n_already_graded,
        "dry_run": dry_run,
    }

    # Write run_status.json — broken != quiet.
    if not dry_run:
        status_p = root.joinpath(*_STATUS_FILE)
        status_p.parent.mkdir(parents=True, exist_ok=True)
        status_p.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    msg = (
        f"[grade_qledger] open={n_open} graded_today={n_graded_today} "
        f"blocked={n_blocked_by_coverage} ungradeable={n_ungradeable} "
        f"already_graded={n_already_graded}"
        + (" [DRY RUN]" if dry_run else "")
    )
    log.info(msg)
    print(msg, flush=True)

    return summary


# --------------------------------------------------------------------------- #
# collect.py end-of-collect hook
# --------------------------------------------------------------------------- #
def run_as_collect_step(root: Path | str | None = None) -> None:
    """Called from scripts/collect.py as an end-of-collect step. Non-fatal:
    a grader crash must not abort the nightly collection run."""
    try:
        run(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("[grade_qledger] grader crashed (non-fatal): %s", exc)


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Nightly qledger claim grader — grades open claims and "
                    "emits site/qledger/track_record.json.")
    p.add_argument("--root", default=None,
                   help="Repo root (default: lib.config.ROOT).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute grades but do not write any files.")
    p.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD) for back-testing.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    today_dt = date.fromisoformat(args.today) if args.today else None
    run(root=args.root, today=today_dt, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
