"""Trend reader for the nightly timings ledger (masterplan W2's "one reader script").

Reads data/ops/nightly_timings/<job>.jsonl (written nightly by
scripts/nightly_timings.py via each daily.yml job's final step) and prints a
per-job budget table over the last N nights: median/max elapsed, percent of the
job's timeout-minutes cap, and how many nights crossed the 85% tripwire —
so caps get re-budgeted from trend data BEFORE a kill night, not after.

Usage:  python3 scripts/nightly_timings_report.py [--nights 14] [--bands]
Stdlib-only; read-only; safe to run anywhere.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

DEFAULT_LEDGER_DIR = Path("data/ops/nightly_timings")
WARN_PCT = 85.0
WATCH_PCT = 70.0  # median above this = creep worth re-budgeting proactively


def load_rows(ledger_dir: Path) -> dict[str, list[dict]]:
    jobs: dict[str, list[dict]] = {}
    for path in sorted(ledger_dir.glob("*.jsonl")):
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("elapsed_minutes") is not None:
                rows.append(row)
        if rows:
            jobs[path.stem] = rows
    return jobs


def report(ledger_dir: Path, nights: int, show_bands: bool) -> list[str]:
    jobs = load_rows(ledger_dir)
    out: list[str] = []
    if not jobs:
        out.append(f"no timings rows under {ledger_dir} — has the nightly run since W2 shipped?")
        return out

    header = (f"{'job':<24} {'cap':>5} {'nights':>6} {'median':>8} {'max':>8} "
              f"{'med%':>5} {'max%':>5} {'>85%':>5}  flag")
    out.append(header)
    out.append("-" * len(header))
    for job, rows in sorted(jobs.items()):
        recent = sorted(rows, key=lambda r: (r.get("date", ""), r.get("end", "")))[-nights:]
        elapsed = [float(r["elapsed_minutes"]) for r in recent]
        cap = float(recent[-1].get("cap_minutes") or 0)
        med = statistics.median(elapsed)
        mx = max(elapsed)
        med_pct = 100.0 * med / cap if cap else 0.0
        max_pct = 100.0 * mx / cap if cap else 0.0
        breaches = sum(1 for e in elapsed if cap and 100.0 * e / cap > WARN_PCT)
        flag = ""
        if breaches:
            flag = "TRIPWIRE — re-budget or trim NOW"
        elif med_pct > WATCH_PCT:
            flag = "creep watch (median >70% of cap)"
        out.append(f"{job:<24} {cap:>4.0f}m {len(recent):>6} {med:>7.1f}m {mx:>7.1f}m "
                   f"{med_pct:>4.0f}% {max_pct:>4.0f}% {breaches:>5}  {flag}")

        if show_bands:
            band_vals: dict[str, list[float]] = {}
            band_order: list[str] = []
            for r in recent:
                for b in r.get("bands") or []:
                    if b["band"] not in band_vals:
                        band_vals[b["band"]] = []
                        band_order.append(b["band"])
                    band_vals[b["band"]].append(float(b["seconds"]) / 60.0)
            for band in band_order:
                vals = band_vals[band]
                out.append(f"    · {band:<20} median {statistics.median(vals):>6.1f}m  "
                           f"max {max(vals):>6.1f}m  ({len(vals)} nights)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR)
    ap.add_argument("--nights", type=int, default=14)
    ap.add_argument("--bands", action="store_true", help="also print per-band medians")
    args = ap.parse_args(argv)
    for line in report(args.ledger_dir, args.nights, args.bands):
        print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
