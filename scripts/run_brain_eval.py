#!/usr/bin/env python3
"""Weekly offline answer-quality eval over the Mastermind response log (W2).

    python scripts/run_brain_eval.py [--dry-run] [--limit N] [--no-benchmark]

Runs once a week (.github/workflows/brain-eval.yml, Sunday 13:00 UTC) and does
four things, in this order:

  1. REFRESH   admin.mastermind_logs.refresh() pulls new response-log objects
               from R2 into data/mastermind/response_log.jsonl. Absent creds are
               a graceful no-op — the pass then grades whatever the local ledger
               already holds rather than aborting.
  2. SAMPLE    the last SAMPLE_DAYS days, error rows excluded: EVERY pro-lane
               row plus up to MAX_FAST fast-lane rows newest-first, hard-capped
               at MAX_JUDGED. Pro is small and expensive per turn (it is the
               lane that gets the hard questions), so it is never sampled away;
               fast is high-volume, so it is capped.
  3. JUDGE     engine.neuralweb.response_eval — mechanical checks always, the
               LLM judge unless --dry-run. Results MERGE into the existing eval
               sidecar under auto_* keys.
  4. SUMMARISE data/mastermind/eval_summary_latest.json + one R2 copy per ISO
               week, plus ONE ::notice line for the Actions run page.

WHY THE SIDECAR AND NOT THE LEDGER: data/mastermind/response_log.jsonl mirrors
R2 and is immutable. Every verdict — operator or machine — lives in
data/mastermind/response_eval.jsonl and is overlaid at read time by id. This
script writes ONLY the auto_* namespace, merged over whatever is already there,
so an operator's grade/thumb/star/tags/note and the contradiction tier's
contra_* verdict all survive a weekly pass untouched (the same non-clobber idiom
as admin.mastermind_logs.classify_contradictions).

INTERNAL QA TELEMETRY ONLY. Nothing this script writes may reach site/ or any
user-facing surface — see the CONSTRAINT in engine/neuralweb/response_eval.py.
Both output files are gitignored; the R2 copy is on the private data plane.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admin import mastermind_logs as _ml       # noqa: E402
from engine.neuralweb import response_eval as _re  # noqa: E402

log = logging.getLogger("run_brain_eval")

# Sampling policy.
SAMPLE_DAYS = 7
MAX_FAST = 120
MAX_JUDGED = 150

SUMMARY_NAME = "eval_summary_latest.json"
R2_SUMMARY_PREFIX = "mastermind_response_evals/summary"

_EVAL_SCHEMA = "mastermind.response_eval.v1"
_SUMMARY_SCHEMA = "mastermind.eval_summary.v1"
# Bound the tag census in the summary — the taxonomy is 7 long, this is slack.
_TOP_TAGS = 7


# ---------------------------------------------------------------------------
# Ledger read + sampling
# ---------------------------------------------------------------------------

def _ledger_rows(root: Path) -> list[dict]:
    """Every row in the local ledger, bounded by the admin module's read cap."""
    return _ml._read_jsonl(_ml._log_path(root), _ml._READ_CAP)


def select_rows(rows: list[dict], *, days: int = SAMPLE_DAYS,
                max_fast: int = MAX_FAST, cap: int = MAX_JUDGED,
                now: datetime | None = None) -> list[dict]:
    """The week's judgeable sample: all pro-lane rows + capped fast-lane rows.

    Error rows are excluded — flags.error means the turn never produced a real
    answer, so grading it would score the transport, not the assistant. Both
    tiers sort newest-first and the whole sample is hard-capped at ``cap``; when
    the cap bites it eats fast rows first (pro is sliced only if pro ALONE
    exceeds the cap, which would itself be the story).
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    pro: list[dict] = []
    fast: list[dict] = []
    other: list[dict] = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        if (r.get("flags") or {}).get("error"):
            continue
        if _ml._parse_ts(r.get("ts")) < since:
            continue
        lane = str(r.get("lane") or "").strip().lower()
        if lane == "pro":
            pro.append(r)
        elif lane == "fast":
            fast.append(r)
        else:
            # A lane-less row (older terminal turns, an ask_brain sibling) is
            # still a real answer; it rides with the fast tier's budget rather
            # than being silently dropped from the corpus.
            other.append(r)

    key = lambda r: _ml._parse_ts(r.get("ts"))  # noqa: E731
    pro.sort(key=key, reverse=True)
    # fast and other share ONE budget, so they are merged BEFORE the slice — the
    # newest max_fast of the combined tail, not max_fast of each.
    tail = fast + other
    tail.sort(key=key, reverse=True)
    sample = pro[:cap] + tail[:max_fast]
    sample.sort(key=key, reverse=True)
    return sample[:cap]


# ---------------------------------------------------------------------------
# Sidecar merge (non-clobber)
# ---------------------------------------------------------------------------

def _merge_auto(root: Path, overlay: dict[str, dict], scored: dict) -> bool:
    """Write ONE auto_* verdict into the eval sidecar, merged over what is there.

    Mirrors admin.mastermind_logs.classify_contradictions exactly: start from the
    folded sidecar row for this id, update only this tier's namespaced keys, and
    setdefault (never assign) evaluator/updated_ts so an operator-rated row keeps
    reading as a human verdict in the panel. Returns False on a write problem —
    the caller counts it as a skip and keeps going.
    """
    rid = str(scored.get("id") or "")
    if not rid:
        return False
    merged = dict(overlay.get(rid) or {})
    merged.update({
        "id": rid,
        "schema": _EVAL_SCHEMA,
        "auto_total": scored.get("total"),
        "auto_passed": bool(scored.get("passed")),
        "auto_scores": scored.get("scores") or {},
        "auto_tags": scored.get("tags") or [],
        "auto_note": scored.get("note") or "",
        "auto_model": scored.get("judged_at_model") or "",
        "auto_judged_at": _ml._now_iso(),
    })
    merged.setdefault("evaluator", "auto_eval")
    merged.setdefault("updated_ts", merged["auto_judged_at"])
    try:
        _ml._append_jsonl(_ml._eval_path(root), merged)
    except Exception as exc:  # noqa: BLE001 — disk problem → skip this row only
        log.warning("run_brain_eval: sidecar append failed for %s (%s)", rid, exc)
        return False
    overlay[rid] = merged
    return True


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _blank_lane() -> dict:
    return {"n": 0, "judged": 0, "passed": 0, "pass_rate": None, "mean_total": None}


def build_summary(results: list[dict], benchmark: dict | None, *,
                  ingest: dict, refreshed: dict, dry_run: bool,
                  now: datetime | None = None) -> dict:
    """Roll the scored rows into the operator-facing weekly summary.

    Pass rates are conditioned on JUDGED rows, never on sampled rows: an
    unjudged row (dead key, unparseable reply twice) is a harness failure, and
    counting it as a fail would let a transport problem read as a quality
    collapse. ``judged`` vs ``n`` is printed per lane so the denominator is
    always visible — a pass rate over 3 of 90 rows is not a pass rate.
    """
    now = now or datetime.now(timezone.utc)
    iso = now.isocalendar()
    lanes: dict[str, dict] = {}
    tags: dict[str, int] = {}
    totals: list[int] = []
    hard_fails = 0
    mech_only: dict[str, int] = {}

    for res in results:
        lane = str(res.get("lane") or "unknown")
        row = lanes.setdefault(lane, _blank_lane())
        row["n"] += 1
        for t in res.get("tags") or []:
            tags[t] = tags.get(t, 0) + 1
        for t in (res.get("mech") or {}).get("tags") or []:
            mech_only[t] = mech_only.get(t, 0) + 1
        if res.get("hard_fail"):
            hard_fails += 1
        if not res.get("judged"):
            continue
        row["judged"] += 1
        if res.get("passed"):
            row["passed"] += 1
        tot = res.get("total")
        if isinstance(tot, int):
            row.setdefault("_totals", []).append(tot)
            totals.append(tot)

    for row in lanes.values():
        lane_totals = row.pop("_totals", [])
        if row["judged"]:
            row["pass_rate"] = round(row["passed"] / row["judged"], 3)
        if lane_totals:
            row["mean_total"] = round(sum(lane_totals) / len(lane_totals), 1)

    judged = sum(r["judged"] for r in lanes.values())
    passed = sum(r["passed"] for r in lanes.values())
    return {
        "schema": _SUMMARY_SCHEMA,
        "generated_at": _ml._now_iso(),
        "iso_week": f"{iso[0]}-W{iso[1]:02d}",
        "window_days": SAMPLE_DAYS,
        "dry_run": bool(dry_run),
        "pass_threshold": _re.PASS_THRESHOLD,
        "rubric_axes": dict(_re.RUBRIC),
        "sampled": len(results),
        "judged": judged,
        "passed": passed,
        "pass_rate": round(passed / judged, 3) if judged else None,
        "mean_total": round(sum(totals) / len(totals), 1) if totals else None,
        "hard_fails": hard_fails,
        "by_lane": lanes,
        "tags": dict(sorted(tags.items(), key=lambda kv: -kv[1])[:_TOP_TAGS]),
        "mechanical_tags": dict(sorted(mech_only.items(), key=lambda kv: -kv[1])[:_TOP_TAGS]),
        "benchmark": benchmark or {},
        "ingest": ingest or {},
        "refresh": {k: refreshed.get(k) for k in ("ok", "ingested", "note")},
    }


def _summary_path(root: Path) -> Path:
    return root.joinpath(*_ml._SUBDIR, SUMMARY_NAME)


def write_summary(root: Path, summary: dict) -> Path:
    p = _summary_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def upload_summary(summary: dict) -> tuple[bool, str]:
    """Copy the summary to R2 under one key per ISO week. (ok, note).

    Reuses lib.mastermind_response_log's own client so the eval plane rides the
    exact same credential ladder as the corpus it grades — a pass that could read
    the log can always write its summary. Absent creds/boto3 is a no-op, never a
    failure: the local file is the operator's copy and the R2 one is the archive.
    """
    try:
        from lib import mastermind_response_log as _mm

        s3 = _mm._client()
        bucket = os.environ.get("R2_BUCKET")
        if s3 is None or not bucket:
            return False, "no R2 creds — local summary only"
        key = f"{R2_SUMMARY_PREFIX}/{summary.get('iso_week') or 'unknown'}.json"
        s3.put_object(
            Bucket=bucket, Key=key,
            Body=json.dumps(summary, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return True, key
    except Exception as exc:  # noqa: BLE001
        return False, f"r2 upload failed: {exc}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _notice(summary: dict, r2_note: str) -> None:
    """The ONE Actions annotation for this run.

    Bare print at line start, flushed — NEVER through the logger. GitHub only
    parses a workflow command when '::' is the first thing on the line, and every
    logger in this repo prefixes the level, so a logged annotation is silently
    dropped (see tests/test_gh_annotation_line_start.py; shipped dead five times
    before #3587). stdout is block-buffered when piped in CI, hence flush.
    """
    lanes = " · ".join(
        f"{lane} {row['passed']}/{row['judged']}"
        + (f" ({row['pass_rate']:.0%})" if row.get("pass_rate") is not None else "")
        for lane, row in sorted(summary.get("by_lane", {}).items())
    ) or "no rows in window"
    bench = summary.get("benchmark") or {}
    bench_txt = (
        f"benchmark {bench.get('benchmark_id')} {bench.get('total')}/100 "
        f"{'PASS' if bench.get('passed') else 'FAIL'}"
        if bench.get("total") is not None
        else f"benchmark not scored ({bench.get('error') or 'skipped'})"
    )
    top = ", ".join(f"{t}×{n}" for t, n in (summary.get("tags") or {}).items()) or "none"
    print(
        f"::notice title=brain-eval::{summary.get('iso_week')} "
        f"sampled {summary.get('sampled')} · judged {summary.get('judged')} · "
        f"pass {lanes} · mean {summary.get('mean_total')} · {bench_txt} · "
        f"top tags: {top} · {r2_note}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Weekly offline answer-quality eval.")
    ap.add_argument("--dry-run", action="store_true",
                    help="mechanical checks only — no LLM calls, no R2 upload, "
                         "no sidecar writes")
    ap.add_argument("--limit", type=int, default=None,
                    help=f"override the judged-row cap (default {MAX_JUDGED})")
    ap.add_argument("--no-benchmark", action="store_true",
                    help="skip the frozen benchmark turn (corpus tier only)")
    ap.add_argument("--root", default=None, help="repo/data root override")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(args.root).resolve() if args.root else ROOT
    cap = MAX_JUDGED if args.limit is None else max(1, int(args.limit))

    # 1. Refresh. A dry run never touches the network; an absent cred is a no-op
    #    that leaves the local ledger as the corpus (refresh() reports it).
    if args.dry_run:
        refreshed = {"ok": False, "ingested": 0, "note": "dry_run — R2 not contacted"}
    else:
        refreshed = _ml.refresh(root=root)
        if not refreshed.get("ok"):
            log.warning("run_brain_eval: refresh did not ingest (%s) — grading the "
                        "local ledger as-is", refreshed.get("note"))

    rows = _ledger_rows(root)
    ingest = _ml.ingest_health(rows)
    sample = select_rows(rows, cap=cap)
    log.info("run_brain_eval: ledger=%d window=%dd sample=%d (cap %d)",
             len(rows), SAMPLE_DAYS, len(sample), cap)

    # 2. Judge. --dry-run injects a judge that never calls anything, so the
    #    mechanical tier still runs over the whole sample and the summary shape
    #    is identical — that is what makes the dry run a real smoke test.
    if args.dry_run:
        judge_fn = lambda _prompt: None            # noqa: E731
        judge_fn.model_id = "dry_run"              # type: ignore[attr-defined]
    else:
        judge_fn = _re.judge_via_llm_auth(root)

    overlay = _ml._eval_overlay(root)
    results: list[dict] = []
    written = 0
    for row in sample:
        scored = _re.score_response(row, judge_fn)
        results.append(scored)
        if not args.dry_run and _merge_auto(root, overlay, scored):
            written += 1

    # 3. Benchmark — once per run, never per row.
    benchmark: dict = {}
    if args.no_benchmark:
        benchmark = {"error": "skipped_by_flag"}
    elif args.dry_run:
        case = _re.load_benchmark()
        benchmark = {
            "benchmark_id": case.get("benchmark_id", ""),
            "error": "dry_run",
            "total": None,
            "passed": False,
            "fixture_loaded": bool(case),
        }
    else:
        benchmark = _re.run_benchmark(root, judge_fn)
        # The generated answer is a full market read; the summary is a dashboard
        # payload the admin panel renders. Keep the score, drop the prose.
        benchmark = {k: v for k, v in benchmark.items() if k not in ("answer", "mech")}

    # 4. Summarise.
    summary = build_summary(results, benchmark, ingest=ingest,
                            refreshed=refreshed, dry_run=args.dry_run)
    summary["sidecar_writes"] = written
    out = write_summary(root, summary)

    if args.dry_run:
        r2_ok, r2_note = False, "dry_run — no upload"
    else:
        r2_ok, r2_note = upload_summary(summary)
    summary["r2_key"] = r2_note if r2_ok else None
    if r2_ok:
        write_summary(root, summary)

    log.info("run_brain_eval: summary -> %s (r2: %s)", out, r2_note)
    _notice(summary, ("r2 " + r2_note) if r2_ok else r2_note)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
