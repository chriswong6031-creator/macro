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

W-L1 of research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md adds a second layer
to ``finish``: **per-source attribution**. 178 registered collectors run inside
ONE opaque ``collectors`` band (~130m of a ~140m collect job), and the plan is
to move day-cadence sources off the nightly path — but you cannot argue which
collector to move until the ledger says how long each one took. Per-adapter
``elapsed_sec`` already exists in ``data/run_status.json``; ``finish`` copies it
(read-only — this module never writes that file) into the row it is already
appending, so the evidence costs one JSON read per job and measures nothing new.

Three properties are load-bearing, and each is pinned by a test:

  1. **A missing measurement is NULL, never 0.** A source that ran but carries no
     timing (``timings`` in scripts/collect.py is keyed by REGISTRY KEY while the
     status row is keyed by ``FetchResult.source``, so the two pseudo-sources and
     any key/source mismatch land untimed) is recorded as ``null`` and named in
     the printed line. Zero would make the slowest unknown read as the fastest
     source — the exact inversion this data exists to prevent.
  2. **The residue is published, not distributed.** ``attributed_sec +
     residue_sec == band_sec`` exactly; whatever the adapters do not explain
     stays a visible remainder. That remainder IS the finding (measured
     2026-08-09: 23.1m of the 130.1m collectors band is not adapter time at all).
  3. **Attribution is windowed by the job's own band boundaries.** run_status is
     a cumulative store written by several lanes (asia-close writes the same
     file), so only sources whose ``checked_at`` falls inside a band of THIS run
     are attributed; everything else is counted as ``unmatched``, never folded in.

Two honest limits, restated in the ledger and the reader: the concurrent
host-group phase overlaps, so ``attributed_sec`` is summed adapter wall-clock and
over-counts against a band's real elapsed (making ``residue_sec`` a LOWER bound
on non-adapter time, and negative when overlap dominates); and a foreign lane
writing run_status inside this job's window would be attributed here — the
per-band ``batches`` list exists so that shows up instead of hiding.

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
#: Read-only input for per-source attribution (W-L1). Relative to the repo root,
#: matching config.yml `storage.run_status_file`; the runner always runs from
#: GITHUB_WORKSPACE. Kept as a literal instead of importing lib.config so this
#: module stays stdlib-only on the runner path.
DEFAULT_RUN_STATUS = Path("data/run_status.json")
WARN_PCT = 85.0
#: How many sources the printed attribution line names before it truncates. The
#: LEDGER always carries every matched source; this bounds one log line only.
TOP_SOURCES_PRINTED = 8


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


def band_windows(job_start: float | None, marks: list[dict],
                 now: float) -> list[tuple[str, float, float]]:
    """``[(band, start_epoch, end_epoch)]`` — the band boundaries themselves.

    job_start→mark1 is the implicit ``startup`` band (checkout + venv + pip —
    measured 3s→14.5m on the 14k-file tree), then each mark runs to the next,
    and the last mark runs to ``now``.

    ``compute_bands`` (durations) and the W-L1 attribution (which source fell in
    which band) both derive from THIS function, so the window a source is
    charged to can never drift from the duration it is charged against.
    """
    windows: list[tuple[str, float, float]] = []
    if marks:
        if job_start is not None and marks[0]["t"] - job_start > 0.5:
            windows.append(("startup", job_start, marks[0]["t"]))
        for cur, nxt in zip(marks, marks[1:]):
            windows.append((cur["band"], cur["t"], nxt["t"]))
        windows.append((marks[-1]["band"], marks[-1]["t"], now))
    return windows


def compute_bands(job_start: float | None, marks: list[dict], now: float) -> list[dict]:
    """Band durations, in band order (see ``band_windows`` for the boundaries)."""
    return [{"band": band, "seconds": round(end - start)}
            for band, start, end in band_windows(job_start, marks, now)]


# ---------------------------------------------------------------------------
# W-L1: per-source attribution from data/run_status.json (read-only)
# ---------------------------------------------------------------------------

def _parse_checked_at(value: object) -> float | None:
    """ISO-8601 ``checked_at`` → epoch seconds, or None when it cannot be read.

    collect.py writes ``datetime.now(timezone.utc).isoformat()`` (offset form);
    a ``Z`` suffix and a naive stamp (read as UTC) are accepted too, because an
    unparseable timestamp must fall out as *unmatched* rather than be silently
    charged to some band.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def _elapsed_of(record: object) -> float | None:
    """``elapsed_sec`` as a float, or None when there is NO measurement.

    A measured 0.0 stays 0.0 and an absent/garbage value stays None: collapsing
    the second into the first would make an untimed source read as the fastest
    one in the ledger, which is the one wrong answer this row must never give.
    """
    if not isinstance(record, dict):
        return None
    raw = record.get("elapsed_sec")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    return value if value == value and abs(value) != float("inf") else None  # NaN/inf → no measurement


def attribute_sources(windows: list[tuple[str, float, float]], sources: dict,
                      from_path: Path | str = DEFAULT_RUN_STATUS) -> dict:
    """Charge each run_status source to the band whose window contains its write.

    Returns the ``source_attribution`` block. Per band:
    ``attributed_sec + residue_sec == band_sec`` exactly — the residue is
    published, never distributed across the sources that failed to explain it.
    """
    charged: dict[int, list[tuple[str, float | None]]] = {i: [] for i in range(len(windows))}
    batches: dict[int, dict[str, int]] = {i: {} for i in range(len(windows))}
    unmatched = 0
    undated = 0

    for name, record in sorted(sources.items()):
        checked_at = _parse_checked_at(record.get("checked_at") if isinstance(record, dict) else None)
        if checked_at is None:
            undated += 1
            unmatched += 1
            continue
        idx = None
        for i, (_band, start, end) in enumerate(windows):
            # Half-open except at the tail, so a status write landing exactly on
            # `now` (the finish step's own instant) still belongs to a band.
            if start <= checked_at < end or (i == len(windows) - 1 and checked_at == end):
                idx = i
                break
        if idx is None:
            unmatched += 1
            continue
        charged[idx].append((str(name), _elapsed_of(record)))
        # Bucketed to the SECOND. collect.py stamps every source in one
        # write_status call with its own `datetime.now()`, so the raw strings are
        # microsecond-unique: keying on them turned one write of 126 sources into
        # 126 "batches" and 6.9 KB of ledger row that told the reader nothing.
        # One bucket per write is the diagnostic — it is how a foreign lane
        # writing inside this window shows up as a second batch.
        batch = _iso(checked_at)
        batches[idx][batch] = batches[idx].get(batch, 0) + 1

    band_rows: list[dict] = []
    nulls_all: list[str] = []
    for i, (band, start, end) in enumerate(windows):
        rows = charged[i]
        if not rows:
            continue
        band_sec = round(end - start)
        measured = [(n, e) for n, e in rows if e is not None]
        nulls = sorted(n for n, e in rows if e is None)
        nulls_all.extend(nulls)
        attributed = round(float(sum(e for _n, e in measured)), 1)
        # The identity gate: publish the remainder instead of spreading it.
        residue = round(float(band_sec) - attributed, 1)
        ordered = sorted(measured, key=lambda ne: (-ne[1], ne[0]))
        band_rows.append({
            "band": band,
            "band_sec": band_sec,
            "attributed_sec": attributed,
            "residue_sec": residue,
            "n_sources": len(rows),
            "n_null_elapsed": len(nulls),
            "batches": [{"checked_at": stamp, "n": n}
                        for stamp, n in sorted(batches[i].items())],
            # name → measured seconds, or null when the source ran untimed.
            # Slowest first; the untimed tail keeps its explicit null.
            "sources": {**{n: e for n, e in ordered}, **{n: None for n in nulls}},
        })

    return {
        "from": str(from_path),
        "read": "ok",
        "recorded": len(sources),
        "matched": sum(len(charged[i]) for i in range(len(windows))),
        "unmatched": unmatched,
        "undated": undated,
        "null_elapsed": sorted(set(nulls_all)),
        "bands": band_rows,
    }


def read_run_status_sources(path: Path) -> tuple[dict, str]:
    """``(sources, read_state)`` — never raises; a missing/garbage file is a
    labelled no-op, not a lost timings row (telemetry must not fail a night)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "missing"
    except (OSError, ValueError):
        return {}, "unreadable"
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, dict):
        return {}, "unreadable"
    return sources, "ok"


def attribution_lines(attribution: dict) -> list[str]:
    """The job-log form of the attribution block — plain prints, never annotations.

    Nulls and the residue are named HERE as well as in the ledger: "printed, not
    hidden" is the gate, and a fact that only exists in a jsonl nobody opens is
    hidden. These are deliberately NOT ``::warning``s — every night has the same
    two untimed pseudo-sources (polygon_gex_accrual / options_flow_creds), so an
    annotation would be a scheduled alarm that trains people to ignore it.
    """
    lines: list[str] = []
    if attribution.get("read") != "ok":
        lines.append(f"nightly-timings attribution: {attribution.get('from')} "
                     f"{attribution.get('read')} — no per-source attribution this run")
        return lines
    for band in attribution.get("bands") or []:
        band_min = band["band_sec"] / 60.0
        attributed_min = band["attributed_sec"] / 60.0
        residue_min = band["residue_sec"] / 60.0
        pct = (100.0 * band["residue_sec"] / band["band_sec"]) if band["band_sec"] else 0.0
        note = "" if band["residue_sec"] >= 0 else \
            " (negative: summed adapter time exceeds the band — concurrent host-groups overlap)"
        top = [f"{name} {sec / 60:.1f}m"
               for name, sec in band["sources"].items()
               if sec is not None][:TOP_SOURCES_PRINTED]
        lines.append(
            f"nightly-timings attribution: {band['band']} {band_min:.1f}m = "
            f"{band['n_sources']} source(s) {attributed_min:.1f}m + residue "
            f"{residue_min:.1f}m ({pct:.0f}% of the band){note} · slowest: "
            + ", ".join(top))
    nulls = attribution.get("null_elapsed") or []
    if nulls:
        lines.append(
            f"nightly-timings attribution: {len(nulls)} source(s) ran with NO elapsed "
            f"measurement — recorded as null, never 0: {', '.join(nulls)}")
    unmatched = attribution.get("unmatched") or 0
    if unmatched:
        lines.append(
            f"nightly-timings attribution: {unmatched} of {attribution.get('recorded')} "
            f"run_status source(s) were written outside this job's bands (other lanes / "
            f"earlier nights) and are NOT attributed here"
            + (f"; {attribution['undated']} carried no readable checked_at"
               if attribution.get("undated") else ""))
    return lines


def append_row(ledger_dir: Path, row: dict) -> Path:
    path = ledger_dir / f"{row['job']}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    return path


def cmd_finish(cap_minutes: float, ledger_dir: Path, now: float | None = None,
               run_status_path: Path | None = None) -> dict:
    now = time.time() if now is None else now
    run_status_path = DEFAULT_RUN_STATUS if run_status_path is None else run_status_path
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
    windows = band_windows(job_start, marks, now)
    bands = compute_bands(job_start, marks, now)

    # W-L1 attribution. Read-only, best-effort, and bounded by the same telemetry
    # law as the rest of this module: an unreadable run_status costs the row its
    # attribution block, never the row itself.
    sources, read_state = read_run_status_sources(run_status_path)
    if read_state == "ok":
        attribution = attribute_sources(windows, sources, run_status_path)
    else:
        attribution = {"from": str(run_status_path), "read": read_state, "recorded": 0,
                       "matched": 0, "unmatched": 0, "undated": 0,
                       "null_elapsed": [], "bands": []}

    row.update({
        "start": _iso(job_start),
        "elapsed_minutes": round(elapsed_min, 1),
        "pct_of_cap": round(pct, 1) if pct is not None else None,
        "bands": bands,
        "source_attribution": attribution,
    })
    append_row(ledger_dir, row)

    band_txt = ", ".join(f"{b['band']} {b['seconds'] / 60:.1f}m" for b in bands) or "(no bands)"
    print(f"nightly-timings: {job} elapsed {elapsed_min:.1f}m of {cap_minutes:g}m cap "
          f"({pct:.0f}%) — {band_txt}", flush=True)
    for line in attribution_lines(attribution):
        print(line, flush=True)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"- timings · **{job}**: {elapsed_min:.1f}m / {cap_minutes:g}m "
                         f"cap ({pct:.0f}%){' · **>85% BUDGET TRIPWIRE**' if pct > WARN_PCT else ''}\n")
                for band in attribution.get("bands") or []:
                    fh.write(f"  - attribution · `{band['band']}` {band['band_sec'] / 60:.1f}m = "
                             f"{band['n_sources']} source(s) {band['attributed_sec'] / 60:.1f}m "
                             f"+ residue {band['residue_sec'] / 60:.1f}m"
                             + (f" · {band['n_null_elapsed']} with no elapsed measurement (null)"
                                if band["n_null_elapsed"] else "") + "\n")
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
    f.add_argument("--run-status", type=Path, default=DEFAULT_RUN_STATUS,
                   help="read-only source of per-adapter elapsed_sec (W-L1 attribution)")

    b = sub.add_parser("backfill", help="seed the ledger from a gh api jobs payload")
    b.add_argument("--jobs-json", type=Path, required=True)
    b.add_argument("--workflow", type=Path, default=Path(".github/workflows/daily.yml"))
    b.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR)

    args = ap.parse_args(argv)
    if args.cmd == "mark":
        cmd_mark(args.band)
    elif args.cmd == "finish":
        cmd_finish(args.cap_minutes, args.ledger_dir, run_status_path=args.run_status)
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
