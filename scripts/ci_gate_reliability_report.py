#!/usr/bin/env python3
"""Measure why the merge train stalls: main's green rate and the gate's data coupling.

Two numbers explain a two-week backlog, and neither is a bug in the sweeper.

**Green rate.** `main` — with no pull-request diff in it at all — passes its own
`ci.yml` gate well under half the time. Every mechanism downstream assumes the
opposite: `merge_on_green` refuses to merge a red head even when the red is
inherited, and its base-inherited excuse needs a FRESH GREEN PROOF of main to
compare against. Below ~50% that proof is usually stale or red, so each session
inherits main's red, cannot merge, and pays to heal main before its own work can
land. That toll — not session inefficiency — is where the compute goes.

**Data coupling.** The merge gate runs ~194 legacy jobs and most of them assert
against the *committed data tree*, which the nightly rewrites ~250 commits a day.
Gating a merge on that many assertions over data that moves under them is
arithmetically hostile: at a per-job wrong-footing probability p across N coupled
jobs, P(all green) ~= (1-p)^N, and the observed rate falls out of it.

Neither number is a judgement about any test. A receipt over live data is a
legitimate instrument; it is just not a merge precondition, because a pull
request cannot make yesterday's dividend calendar agree with today's parquet.

Usage
-----
    python3 scripts/ci_gate_reliability_report.py                 # both sections
    python3 scripts/ci_gate_reliability_report.py --coupling      # offline only
    python3 scripts/ci_gate_reliability_report.py --limit 200     # deeper history
    python3 scripts/ci_gate_reliability_report.py --json          # machine readable

The coupling section is a pure static read of `.github/ci/legacy-jobs.yml` plus
the suites it names, so it works offline and in a sparse worktree. The green-rate
section shells out to `gh` and degrades to a stated skip when that is unavailable
rather than reporting a number it did not measure.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".github" / "ci" / "legacy-jobs.yml"

#: A ``run:`` line names its suites as plain paths; this recovers them without
#: pretending to parse a shell.
SUITE_RE = re.compile(r"(?:^|\s)((?:tests|research|engine|scripts)/[\w/.\-]+\.py)")

#: A suite is data-coupled when it reads the committed tree rather than a fixture
#: it builds itself. `tmp_path` suites match none of these; a suite that opens
#: `data/...`, resolves `REPO / "data"`, or calls a loader that does, match.
DATA_READ_RE = re.compile(
    r"""["']data/"""
    r"""|/\s*["']data["']"""
    r"""|\bdata_dir\b"""
    r"""|\bDATA_DIR\b"""
    r"""|\bread_parquet\b"""
    r"""|\bload_closes\b""",
)

CLEAN = "success"


def _suites_for(job: dict) -> set[str]:
    found: set[str] = set()
    for step in job.get("steps") or []:
        for match in SUITE_RE.finditer(str(step.get("run") or "")):
            found.add(match.group(1))
    return found


def _reads_committed_data(suite: str) -> bool | None:
    """True/False, or None when the file is not on disk (sparse worktree)."""
    path = ROOT / suite
    if not path.is_file():
        return None
    try:
        return bool(DATA_READ_RE.search(path.read_text(encoding="utf-8")))
    except OSError:
        return None


def measure_coupling() -> dict:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs") or {}

    coupled: list[tuple[str, int, int]] = []
    pure: list[str] = []
    unresolved: list[str] = []

    for name, job in jobs.items():
        suites = _suites_for(job)
        if not suites:
            unresolved.append(name)
            continue
        verdicts = [_reads_committed_data(s) for s in sorted(suites)]
        readable = [v for v in verdicts if v is not None]
        if not readable:
            unresolved.append(name)
            continue
        hits = sum(1 for v in readable if v)
        if hits:
            coupled.append((name, hits, len(readable)))
        else:
            pure.append(name)

    classified = len(coupled) + len(pure)
    return {
        "jobs_total": len(jobs),
        "data_coupled": len(coupled),
        "code_only": len(pure),
        "unresolved": len(unresolved),
        "classified": classified,
        "coupled_pct": (100.0 * len(coupled) / classified) if classified else 0.0,
        "worst": sorted(coupled, key=lambda row: -row[1])[:15],
    }


def measure_green_rate(limit: int) -> dict:
    """Conclusions of main's own `ci.yml` runs. No PR diff is involved in any of them."""
    try:
        raw = subprocess.run(
            [
                "gh", "run", "list", "--workflow", "ci.yml", "--branch", "main",
                "--limit", str(limit),
                "--json", "conclusion,status,createdAt",
            ],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"skipped": f"gh unavailable: {exc}"}
    if raw.returncode != 0:
        return {"skipped": f"gh exited {raw.returncode}: {raw.stderr.strip()[:200]}"}
    try:
        runs = json.loads(raw.stdout or "[]")
    except json.JSONDecodeError as exc:
        return {"skipped": f"unparseable gh output: {exc}"}

    done = [r for r in runs if r.get("status") == "completed"]
    if not done:
        return {"skipped": "no completed runs returned"}
    tally = Counter(str(r.get("conclusion") or "?") for r in done)
    stamps = sorted(str(r.get("createdAt") or "") for r in done)
    return {
        "completed": len(done),
        "conclusions": dict(tally),
        "green": tally.get(CLEAN, 0),
        "green_pct": 100.0 * tally.get(CLEAN, 0) / len(done),
        "window": [stamps[0], stamps[-1]],
    }


def _render(report: dict) -> str:
    out: list[str] = ["merge-gate reliability", "=" * 22, ""]

    green = report.get("green_rate") or {}
    if "skipped" in green:
        out += [f"main green rate: NOT MEASURED ({green['skipped']})", ""]
    elif green:
        out += [
            f"main green rate: {green['green']}/{green['completed']} = "
            f"{green['green_pct']:.1f}%   [{green['window'][0]} -> {green['window'][1]}]",
            f"  conclusions: {green['conclusions']}",
            "  (these are main's OWN ci.yml runs — no pull-request diff in any of them)",
            "",
        ]

    cup = report["coupling"]
    out += [
        f"merge-gate legacy jobs: {cup['jobs_total']}",
        f"  assert against the committed data tree: {cup['data_coupled']}",
        f"  code-only:                              {cup['code_only']}",
        f"  unresolved (no readable suite on disk): {cup['unresolved']}",
        f"  => {cup['coupled_pct']:.0f}% of classified merge-gate jobs are data-coupled",
        "",
        "most data-coupled jobs (suites reading data / suites classified):",
    ]
    out += [f"   {name:42s} {hits}/{total}" for name, hits, total in cup["worst"]]
    if cup["unresolved"]:
        out += ["", f"note: {cup['unresolved']} job(s) unclassified — a sparse worktree "
                    "hides suites; run `python3 scripts/worktree_sparse.py full` for a "
                    "complete count."]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coupling", action="store_true",
                        help="static coupling section only; never calls gh")
    parser.add_argument("--limit", type=int, default=100,
                        help="how many of main's ci.yml runs to tally (default 100)")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    report: dict = {"coupling": measure_coupling()}
    if not args.coupling:
        report["green_rate"] = measure_green_rate(args.limit)

    print(json.dumps(report, indent=2) if args.json else _render(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
