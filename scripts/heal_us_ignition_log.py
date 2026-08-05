"""Heal data/ignition_log/us_ignition.jsonl — session stamps + weekend-dupe quarantine.

One-time-but-idempotent data heal (census PR #4564 charter §4, 2026-08-05). The
pre-fix logger keyed idempotency on the calendar as_of, so weekend nightly
re-runs re-logged Friday's tape under Saturday/Sunday/drifted-Monday dates —
6 of the first 20 rows were duplicate re-logs of a session already recorded.
This script:

1. INFERS each session-less row's underlying US trading session from its
   logged_at run time. The runner clock is America/Los_Angeles (verified
   against the nightly "engine: regime update" commit series):

     run at/after 16:00 PT -> session = last trading day <= the run's PT date
                              (an evening run snapshots that day's close)
     run before 16:00 PT   -> session = last trading day <  the run's PT date
                              (an early-hours run is the prior evening's
                              nightly drifted past midnight — its stores still
                              hold the previous session's tape)

2. QUARANTINES duplicate re-logs — rows whose inferred session an earlier row
   (by logged_at; first-writer-wins, the ledger's own idempotency law) already
   records — into us_ignition_quarantine.jsonl with a quarantine_reason.
   Nothing is deleted; graded fields are never touched.

3. STAMPS survivors with session + session_inferred=true and merges a
   quarantine provenance block into us_ignition_meta.json.

The trading-day walk skips weekends AND 2026 NYSE holidays, so an inferred
session is always a real session. Fail-closed guard: a row missing logged_at
aborts the whole heal (nothing written) — its session cannot be known.

Usage:
    python3 scripts/heal_us_ignition_log.py [--root DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_PT = ZoneInfo("America/Los_Angeles")
_EVENING_CUTOVER_HOUR = 16  # PT; US close is 13:00 PT — 16:00 gives margin

# NYSE full-closure holidays, 2026 — the trading-day walk steps over these so
# an inferred session is always a real session (the audited window
# 2026-07-10..2026-08-04 contains none; the set matters for any later re-run).
_US_HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}

_QUARANTINE_REASON = (
    "duplicate re-log of an already-recorded US session (pre-session-keying "
    "weekend/off-session nightly re-run; census PR #4564 charter §4)"
)


def _last_trading_day(d, inclusive: bool) -> str:
    """Last NYSE trading day <= d (inclusive) or < d (exclusive). d is a date."""
    cur = d if inclusive else d - timedelta(days=1)
    for _ in range(10):
        if cur.weekday() < 5 and str(cur) not in _US_HOLIDAYS_2026:
            return str(cur)
        cur -= timedelta(days=1)
    raise RuntimeError(f"no trading day found within 10 days before {d}")


def infer_session(logged_at: str) -> str:
    """Infer the US trading session a log row snapshots, from its run time."""
    ts = datetime.fromisoformat(logged_at)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    run_pt = ts.astimezone(_PT)
    inclusive = run_pt.hour >= _EVENING_CUTOVER_HOUR
    return _last_trading_day(run_pt.date(), inclusive=inclusive)


def heal(root: Path, dry_run: bool = False) -> dict:
    """Run the heal. Returns a summary dict. Idempotent: healed files no-op."""
    log_dir = root / "data" / "ignition_log"
    main_p = log_dir / "us_ignition.jsonl"
    quar_p = log_dir / "us_ignition_quarantine.jsonl"
    meta_p = log_dir / "us_ignition_meta.json"

    if not main_p.exists():
        return {"error": f"{main_p} not found"}

    rows: list[dict] = []
    for line in main_p.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    # 1. infer sessions for rows that lack a stamp
    n_inferred = 0
    for r in rows:
        if r.get("session"):
            continue
        if not r.get("logged_at"):
            raise SystemExit(
                f"FAIL-CLOSED: row asof={r.get('asof')} has no logged_at — "
                "cannot infer its session; heal aborted, nothing written."
            )
        r["session"] = infer_session(str(r["logged_at"]))
        r["session_inferred"] = True
        n_inferred += 1

    # 2. first-writer-wins per session (order by logged_at, the write order)
    rows_by_write_order = sorted(rows, key=lambda r: str(r.get("logged_at") or ""))
    kept_by_session: dict[str, dict] = {}
    quarantined: list[dict] = []
    for r in rows_by_write_order:
        sess = str(r["session"])
        if sess not in kept_by_session:
            kept_by_session[sess] = r
            continue
        kept = kept_by_session[sess]
        q = dict(r)
        q["quarantine_reason"] = _QUARANTINE_REASON
        q["quarantined_kept_row"] = {
            "asof": kept.get("asof"), "logged_at": kept.get("logged_at"),
        }
        q["quarantined_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        quarantined.append(q)

    survivors = sorted(kept_by_session.values(), key=lambda r: str(r["session"]))

    summary = {
        "n_rows_in": len(rows),
        "n_inferred": n_inferred,
        "n_survivors": len(survivors),
        "n_quarantined_now": len(quarantined),
        "quarantined_asofs": [q.get("asof") for q in quarantined],
        "sessions": [r["session"] for r in survivors],
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    if not quarantined and n_inferred == 0:
        summary["note"] = "already healed — nothing to do"
        return summary

    # 3. write: main log, quarantine (append-preserving), meta merge
    def _dump(rs: list[dict]) -> str:
        return "\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rs) + "\n"

    existing_quar: list[dict] = []
    if quar_p.exists():
        for line in quar_p.read_text().splitlines():
            line = line.strip()
            if line:
                existing_quar.append(json.loads(line))
    already = {(q.get("asof"), q.get("logged_at")) for q in existing_quar}
    new_quar = [q for q in quarantined if (q.get("asof"), q.get("logged_at")) not in already]

    main_p.write_text(_dump(survivors))
    if existing_quar or new_quar:
        quar_p.write_text(_dump(existing_quar + new_quar))

    meta: dict = {}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text())
        except Exception:  # noqa: BLE001
            meta = {}
    meta["quarantine"] = {
        "file": quar_p.name,
        "n_rows": len(existing_quar) + len(new_quar),
        "reason": _QUARANTINE_REASON,
        "healed_by": "scripts/heal_us_ignition_log.py",
        "last_heal": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo root (contains data/)")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args(argv)
    summary = heal(Path(args.root), dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 1 if summary.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
