"""Per-job / per-band runtime telemetry for the nightly (.github/workflows/daily.yml).

W2 of research/NIGHTLY_RESILIENCE_AND_LIVE_TRANSITION_MASTERPLAN_2026-08-06.md:
every timeout cap in daily.yml's history (engine 70→120→150→200→240, collect
100→150→185→240, tech_lab 40→120) was raised only AFTER nights died at the cap
— the 2026-08-05/06 engine kills at ~205m vs a 200m cap froze the boards for
six days. This module makes the creep visible BEFORE a kill night:

  * ``mark --band <name>``   — called between a job's major step groups; records
    "band <name> starts now" in a runner-temp state file.
  * ``finish --cap-minutes N`` — the job's last step (``if: always()``): closes
    the bands, appends one JSON row to ``data/ops/nightly_timings/<job>.jsonl``
    and emits a line-start ``::warning`` when elapsed exceeds 85% of the cap.
  * ``backfill --jobs-json <file>`` — one-off local seeding of the ledger from a
    ``gh api .../actions/runs/<id>/jobs`` payload (job-level rows, no bands).

The job name and run id come from the standard Actions env (GITHUB_JOB,
GITHUB_RUN_ID), so the workflow steps cannot mislabel a job by copy-paste; the
only per-job argument is the cap, which tests/test_nightly_timings.py pins to
the job's actual ``timeout-minutes``.

Telemetry law: this module must NEVER fail a nightly job. The CLI entrypoint
fails open (prints a line-start ``::warning`` and exits 0 on any error); tests
call the inner functions directly so the fail-open can't swallow assertions.

Annotation law (tests/test_gh_annotation_line_start.py): every ``::warning`` /
``::notice`` here is a bare ``print(..., flush=True)`` — never a logger.

Run: .venv/bin/python -m pytest tests/test_nightly_timings.py -q
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LEDGER_DIR = Path("data/ops/nightly_timings")
WARN_PCT = 85.0


# ---------------------------------------------------------------------------
# runner-temp state (start stamp + band marks), keyed by run id + job so a
# leftover file from a previous run on the same self-hosted runner can never
# pollute tonight's row.
# ---------------------------------------------------------------------------

def _state_dir() -> Path:
    for var in ("NIGHTLY_TIMINGS_STATE_DIR", "RUNNER_TEMP"):
        v = os.environ.get(var)
        if v:
            return Path(v)
    return Path(tempfile.gettempdir())


def _job() -> str:
    return os.environ.get("GITHUB_JOB", "local")


def _run_id() -> str:
    return os.environ.get("GITHUB_RUN_ID", "local")


def start_path(job: str | None = None) -> Path:
    job = job or _job()
    return _state_dir() / f"nightly-timings-{_run_id()}-{job}-start"


def marks_path(job: str | None = None) -> Path:
    job = job or _job()
    return _state_dir() / f"nightly-timings-{_run_id()}-{job}-marks.jsonl"


def cmd_mark(band: str, now: float | None = None) -> None:
    """Record that band ``band`` starts now (ends at the next mark or finish)."""
    now = time.time() if now is None else now
    p = marks_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": round(now, 3), "band": band}) + "\n")


def _read_start() -> float | None:
    try:
        return float(start_path().read_text().strip())
    except (OSError, ValueError):
        return None


def _read_marks() -> list[dict]:
    out: list[dict] = []
    try:
        text = marks_path().read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            out.append({"t": float(row["t"]), "band": str(row["band"])})
        except (ValueError, KeyError, TypeError):
            continue
    out.sort(key=lambda r: r["t"])
    return out


# ---------------------------------------------------------------------------
# finish: compute bands + elapsed, append the ledger row, trip the 85% wire
# ---------------------------------------------------------------------------

def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_bands(job_start: float | None, marks: list[dict], now: float) -> list[dict]:
    """Band durations: job_start→mark1 is the implicit ``startup`` band
    (checkout + venv + pip — measured 3s→14.5m on the 14k-file tree), then each
    mark runs to the next, and the last mark runs to ``now``."""
    bands: list[dict] = []
    if marks:
        if job_start is not None and marks[0]["t"] - job_start > 0.5:
            bands.append({"band": "startup", "seconds": round(marks[0]["t"] - job_start)})
        for cur, nxt in zip(marks, marks[1:]):
            bands.append({"band": cur["band"], "seconds": round(nxt["t"] - cur["t"])})
        bands.append({"band": marks[-1]["band"], "seconds": round(now - marks[-1]["t"])})
    return bands


def append_row(ledger_dir: Path, row: dict) -> Path:
    path = ledger_dir / f"{row['job']}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    return path


def cmd_finish(cap_minutes: float, ledger_dir: Path, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    job = _job()
    marks = _read_marks()
    job_start = _read_start()
    if job_start is None and marks:
        job_start = marks[0]["t"]

    row: dict = {
        "date": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d"),
        "workflow": os.environ.get("GITHUB_WORKFLOW", "daily"),
        "job": job,
        "run_id": _run_id(),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "runner": os.environ.get("RUNNER_NAME", ""),
        "cap_minutes": cap_minutes,
        "end": _iso(now),
    }

    if job_start is None:
        # Dark telemetry must be LOUD — a tripwire that silently records nothing
        # is the exact failure mode W2 exists to end (the 40m tech_lab cap
        # cancelled its own ::warning step for 8 straight nights).
        row.update({"start": None, "elapsed_minutes": None, "pct_of_cap": None,
                    "bands": [], "telemetry": "dark"})
        print(f"::warning title=nightly timings dark::{job}: no job-start stamp or band "
              "marks found in RUNNER_TEMP — the timings row for this night has no elapsed "
              "time and the 85% budget tripwire CANNOT fire. Check the job's "
              "'timings — job start mark (W2)' step.", flush=True)
        append_row(ledger_dir, row)
        return row

    elapsed_min = (now - job_start) / 60.0
    pct = 100.0 * elapsed_min / cap_minutes if cap_minutes else None
    bands = compute_bands(job_start, marks, now)
    row.update({
        "start": _iso(job_start),
        "elapsed_minutes": round(elapsed_min, 1),
        "pct_of_cap": round(pct, 1) if pct is not None else None,
        "bands": bands,
    })
    append_row(ledger_dir, row)

    band_txt = ", ".join(f"{b['band']} {b['seconds'] / 60:.1f}m" for b in bands) or "(no bands)"
    print(f"nightly-timings: {job} elapsed {elapsed_min:.1f}m of {cap_minutes:g}m cap "
          f"({pct:.0f}%) — {band_txt}", flush=True)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"- timings · **{job}**: {elapsed_min:.1f}m / {cap_minutes:g}m "
                         f"cap ({pct:.0f}%){' · **>85% BUDGET TRIPWIRE**' if pct > WARN_PCT else ''}\n")
        except OSError:
            pass

    if pct is not None and pct > WARN_PCT:
        # The W2 tripwire. Every cap raise in daily.yml's history happened AFTER
        # a kill night; this line is the BEFORE. Bare print at line start —
        # never a logger (tests/test_gh_annotation_line_start.py).
        print(f"::warning title=nightly budget 85% tripwire::{job} used {pct:.0f}% of its "
              f"{cap_minutes:g}m timeout-minutes ({elapsed_min:.1f}m). Caps in this file "
              "have only ever been raised AFTER nights died at them (engine 200→240 cost "
              "6 stale-board days, 2026-08-05/06) — re-budget or trim the workload NOW, "
              "before a kill night. Trend: python3 scripts/nightly_timings_report.py "
              f"(ledger data/ops/nightly_timings/{job}.jsonl; masterplan W2).", flush=True)
    return row


# ---------------------------------------------------------------------------
# backfill: seed the ledger from a `gh api .../actions/runs/<id>/jobs` payload
# (one-off, local; job-level rows only — bands need the in-job marks)
# ---------------------------------------------------------------------------

def daily_caps(workflow_path: Path) -> dict[str, float]:
    """job-key → timeout-minutes for daily.yml's instrumented (self-hosted) jobs."""
    import yaml  # local-only path; the runner-side mark/finish path stays stdlib

    doc = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    caps: dict[str, float] = {}
    for key, spec in (doc.get("jobs") or {}).items():
        if not isinstance(spec, dict):
            continue
        runs_on = spec.get("runs-on")
        cap = spec.get("timeout-minutes")
        if cap is None or not isinstance(runs_on, list) or "self-hosted" not in runs_on:
            continue
        caps[key] = float(cap)
    return caps


def cmd_backfill(jobs_json: Path, workflow_path: Path, ledger_dir: Path) -> int:
    payload = json.loads(jobs_json.read_text(encoding="utf-8"))
    caps = daily_caps(workflow_path)
    n = 0
    for j in payload.get("jobs", []):
        name, started, completed = j.get("name"), j.get("started_at"), j.get("completed_at")
        if name not in caps or not started or not completed:
            continue
        t0 = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        t1 = datetime.strptime(completed, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        elapsed_min = (t1 - t0).total_seconds() / 60.0
        if elapsed_min <= 0:
            continue
        cap = caps[name]
        append_row(ledger_dir, {
            "date": t0.strftime("%Y-%m-%d"),
            "workflow": "daily",
            "job": name,
            "run_id": str(j.get("run_id", "")),
            "run_attempt": str(j.get("run_attempt", "")),
            "runner": j.get("runner_name") or "",
            "cap_minutes": cap,
            "start": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_minutes": round(elapsed_min, 1),
            "pct_of_cap": round(100.0 * elapsed_min / cap, 1),
            "bands": [],
            "source": "backfill-gh-api",
            "conclusion": j.get("conclusion") or "",
        })
        n += 1
    print(f"backfilled {n} job rows into {ledger_dir}", flush=True)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mark", help="record that a named band starts now")
    m.add_argument("--band", required=True)

    f = sub.add_parser("finish", help="append the ledger row + 85% budget tripwire")
    f.add_argument("--cap-minutes", type=float, required=True)
    f.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR)

    b = sub.add_parser("backfill", help="seed the ledger from a gh api jobs payload")
    b.add_argument("--jobs-json", type=Path, required=True)
    b.add_argument("--workflow", type=Path, default=Path(".github/workflows/daily.yml"))
    b.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR)

    args = ap.parse_args(argv)
    if args.cmd == "mark":
        cmd_mark(args.band)
    elif args.cmd == "finish":
        cmd_finish(args.cap_minutes, args.ledger_dir)
    else:
        cmd_backfill(args.jobs_json, args.workflow, args.ledger_dir)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — telemetry must never fail a nightly job
        print(f"::warning title=nightly timings error::{_job()}: {type(exc).__name__}: "
              f"{exc} — no timings row this night (non-fatal)", flush=True)
        sys.exit(0)
