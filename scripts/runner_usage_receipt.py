#!/usr/bin/env python3
"""Where the Actions minutes go: a quota-bounded hosted-vs-self-hosted receipt.

OPERATOR TOOL. Deliberately NOT wired into any workflow — run it by hand before
and after a migration wave (charter §13/§15) and paste the receipt into the PR.

    python3 scripts/runner_usage_receipt.py --days 7
    python3 scripts/runner_usage_receipt.py --days 3 --sample-jobs 4 --out receipt.md

THE QUOTA IS THE DESIGN CONSTRAINT, NOT AN AFTERTHOUGHT. `gh` authenticates as a
single account token, so REST's 5,000/hr `core` pool is shared by every parallel
session, the babysitter lane, and the fleet hooks — including
`.claude/hooks/ship_loop_guard.py`, which spends up to 4 REST calls per Stop and
FAILS CLOSED when rate-limited. An observability tool that empties that bucket
blocks the very sessions it was meant to inform. Therefore:

  * a HARD cap of 25 REST calls per invocation, counted (not estimated) and
    enforced — the tool degrades to a smaller sample and SAYS SO rather than
    spending its way to a complete answer;
  * never `--paginate`, and never the check-runs endpoint (~130 checks/PR here);
  * `gh run list --limit N` is charged as ceil(N/100) calls, because that is what
    it actually costs behind the CLI;
  * a preflight `gh api rate_limit` reading, printed in the receipt, so a thin
    remaining budget is visible in the artifact rather than discovered later.

WHAT IT CAN AND CANNOT SEE. Run COUNTS in the window are exact. Runner placement
is derived two ways and both are labelled in the output: statically, from each
workflow's `runs-on` in the LOCAL tree (which is a property of the current
checkout, not of the historical runs being counted), and empirically for ci.yml
and fences.yml by reading `runner_name` from the jobs API of a small sample of
recent completed runs. Durations for sampled runs are real job durations; for
everything else the tool reports run WALL-CLOCK (created→updated), which includes
queue time and is an over-estimate of billable minutes. None of this is a billing
API reading — for dollars, use the org billing endpoint, which is what the
267,066-minute figure in research/CI_SELFHOSTED_MIGRATION_WAVE1.md §1 came from.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
REGISTRY = ROOT / ".github" / "runner-policy.yml"

MAX_REST_CALLS = 25
# The two lanes Wave 1 moved; sampling is spent here because these are the only
# workflows whose placement CHANGED and therefore the only ones worth verifying
# empirically rather than reading off the local tree.
REFINE_WORKFLOWS = ("ci.yml", "fences.yml")
HOSTED_LABEL_RE = re.compile(r"^(ubuntu|macos|windows)-", re.IGNORECASE)
# GitHub-hosted runners report names like "GitHub Actions 12"; self-hosted report
# the name the operator registered (pc-render-3, mac-builder-4, ...).
HOSTED_RUNNER_NAME_RE = re.compile(r"^(github[- ]actions|hosted)", re.IGNORECASE)


class Budget:
    """A counted REST allowance. Refusal is a reported outcome, never an exception."""

    def __init__(self, cap: int = MAX_REST_CALLS) -> None:
        self.cap = cap
        self.spent = 0
        self.refused = 0

    def take(self, cost: int = 1) -> bool:
        if self.spent + cost > self.cap:
            self.refused += 1
            return False
        self.spent += cost
        return True


def _gh(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, cwd=str(ROOT)
    )
    return proc.returncode, (proc.stdout if proc.returncode == 0 else proc.stderr)


def _gh_json(args: list[str]) -> object | None:
    code, out = _gh(args)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# ── static placement from the local tree ─────────────────────────────────────

def _classify_runs_on(runs_on: object) -> str:
    """hosted | self-hosted | mixed | opaque, from a `runs-on` value."""
    if runs_on is None:
        return "opaque"
    if isinstance(runs_on, dict):
        labels = runs_on.get("labels") or []
        return _classify_runs_on(list(labels) if not isinstance(labels, str) else [labels])
    if isinstance(runs_on, list):
        hosted = any(
            HOSTED_LABEL_RE.match(str(x).strip()) for x in runs_on if "${{" not in str(x)
        )
        selfh = any(str(x).strip() == "self-hosted" for x in runs_on)
        if hosted and selfh:
            return "mixed"
        if selfh:
            return "self-hosted"
        return "hosted" if hosted else "opaque"
    text = str(runs_on)
    if "${{" in text:
        hosted = bool(re.search(r"['\"](ubuntu|macos|windows)-[a-z0-9._-]+['\"]", text, re.I))
        selfh = "self-hosted" in text
        if hosted and selfh:
            return "mixed"
        if selfh:
            return "self-hosted"
        return "hosted" if hosted else "opaque"
    if HOSTED_LABEL_RE.match(text.strip()):
        return "hosted"
    if text.strip() == "self-hosted":
        return "self-hosted"
    return "opaque"


def static_placement() -> dict[str, dict[str, str]]:
    """{workflow file name: {job id: class}} from the current checkout."""
    out: dict[str, dict[str, str]] = {}
    for path in sorted(WORKFLOWS_DIR.iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        try:
            doc = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
            continue
        jobs = {}
        for job_id, job in doc["jobs"].items():
            if not isinstance(job, dict):
                continue
            if "runs-on" not in job and "uses" in job:
                continue
            jobs[str(job_id)] = _classify_runs_on(job.get("runs-on"))
        out[path.name] = jobs
    return out


def workflow_name_to_file() -> dict[str, str]:
    """`gh run list` reports the workflow's NAME; map it back to its file."""
    mapping: dict[str, str] = {}
    for path in sorted(WORKFLOWS_DIR.iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        try:
            doc = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(doc, dict) and doc.get("name"):
            mapping.setdefault(str(doc["name"]), path.name)
    return mapping


def pending_migration_entries() -> list[dict]:
    try:
        registry = yaml.safe_load(REGISTRY.read_text())
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(registry, dict):
        return []
    return [
        entry
        for entry in (registry.get("hosted_exceptions") or [])
        if isinstance(entry, dict) and entry.get("class") == "pending-migration"
    ]


# ── sampling ─────────────────────────────────────────────────────────────────

def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect(days: int, sample_jobs: int, budget: Budget) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_date = since.date().isoformat()

    rate_before = None
    if budget.take(1):
        rate_before = _gh_json(["api", "rate_limit", "--jq", ".resources.core"])

    # ONE listing call for the whole window. 400 is ~4 pages; on a repo running
    # ~40 runs/hr that covers roughly half a day, so short windows are exact and
    # long ones are explicitly reported as truncated.
    limit = 400
    runs: list[dict] = []
    truncated = False
    if budget.take(math.ceil(limit / 100)):
        data = _gh_json(
            [
                "run",
                "list",
                "--limit",
                str(limit),
                "--created",
                f">={since_date}",
                "--json",
                "databaseId,workflowName,status,conclusion,createdAt,updatedAt,event",
            ]
        )
        if isinstance(data, list):
            runs = data
            truncated = len(runs) >= limit

    per_workflow: dict[str, dict] = defaultdict(
        lambda: {"runs": 0, "wall_seconds": 0.0, "conclusions": defaultdict(int)}
    )
    for run in runs:
        name = str(run.get("workflowName", "?"))
        row = per_workflow[name]
        row["runs"] += 1
        row["conclusions"][str(run.get("conclusion") or run.get("status") or "?")] += 1
        start, end = _parse_ts(run.get("createdAt")), _parse_ts(run.get("updatedAt"))
        if start and end and end > start:
            row["wall_seconds"] += (end - start).total_seconds()

    # Empirical placement for the migrated lanes only.
    name_to_file = workflow_name_to_file()
    file_to_name = {v: k for k, v in name_to_file.items()}
    samples: dict[str, dict] = {}
    for wf_file in REFINE_WORKFLOWS:
        wf_name = file_to_name.get(wf_file)
        if not wf_name:
            continue
        candidates = [
            r
            for r in runs
            if r.get("workflowName") == wf_name and r.get("status") == "completed"
        ][:sample_jobs]
        seen_runners: dict[str, int] = defaultdict(int)
        job_seconds = 0.0
        sampled = 0
        for run in candidates:
            if not budget.take(1):
                break
            payload = _gh_json(
                [
                    "api",
                    f"repos/{{owner}}/{{repo}}/actions/runs/{run['databaseId']}/jobs",
                    "--jq",
                    "[.jobs[] | {name, runner_name, started_at, completed_at}]",
                ]
            )
            if not isinstance(payload, list):
                continue
            sampled += 1
            for job in payload:
                runner = str(job.get("runner_name") or "unknown")
                kind = "hosted" if HOSTED_RUNNER_NAME_RE.match(runner) else "self-hosted"
                seen_runners[f"{kind}:{runner}"] += 1
                start, end = _parse_ts(job.get("started_at")), _parse_ts(job.get("completed_at"))
                if start and end and end > start:
                    job_seconds += (end - start).total_seconds()
        samples[wf_file] = {
            "runs_available": sum(
                1 for r in runs if r.get("workflowName") == wf_name
            ),
            "runs_sampled": sampled,
            "runner_hits": dict(sorted(seen_runners.items())),
            "sampled_job_minutes": round(job_seconds / 60, 1),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": days,
        "since": since_date,
        "rest_calls_spent": budget.spent,
        "rest_calls_cap": budget.cap,
        "rest_calls_refused": budget.refused,
        "core_rate_limit_before": rate_before,
        "runs_seen": len(runs),
        "listing_truncated": truncated,
        "per_workflow": {
            name: {
                "runs": row["runs"],
                "wall_minutes": round(row["wall_seconds"] / 60, 1),
                "conclusions": dict(row["conclusions"]),
            }
            for name, row in sorted(
                per_workflow.items(), key=lambda kv: -kv[1]["runs"]
            )
        },
        "samples": samples,
    }


# ── rendering ────────────────────────────────────────────────────────────────

def render_markdown(data: dict, placement: dict[str, dict[str, str]]) -> str:
    name_to_file = workflow_name_to_file()
    lines: list[str] = []
    add = lines.append
    add("# Runner usage receipt")
    add("")
    add(
        f"- generated: `{data['generated_at']}` · window: last **{data['window_days']}d** "
        f"(since {data['since']})"
    )
    add(
        f"- REST calls: **{data['rest_calls_spent']}/{data['rest_calls_cap']}** "
        f"(refused {data['rest_calls_refused']}) — shared 5,000/hr `core` bucket"
    )
    core = data.get("core_rate_limit_before") or {}
    if core:
        add(f"- core remaining before this run: **{core.get('remaining', '?')}**")
    add(f"- runs seen: **{data['runs_seen']}**"
        + (" — **LISTING TRUNCATED**, counts are a lower bound" if data["listing_truncated"] else ""))
    add("")
    add("## Runs per workflow in window")
    add("")
    add("| workflow | runs | wall-clock min | static placement (local tree) |")
    add("|---|---:|---:|---|")
    for name, row in data["per_workflow"].items():
        wf_file = name_to_file.get(name, "?")
        classes = placement.get(wf_file, {})
        summary = ", ".join(sorted(set(classes.values()))) or "unknown"
        add(f"| `{name}` | {row['runs']} | {row['wall_minutes']} | {summary} |")
    add("")
    add("> Wall-clock is created→updated and INCLUDES queue time, so it over-states")
    add("> billable minutes. Static placement is a property of the CURRENT checkout,")
    add("> not of the historical runs counted above.")
    add("")
    add("## Empirical placement (sampled `runner_name`)")
    add("")
    if not data["samples"]:
        add("_no samples taken (budget exhausted or workflows absent)._")
    for wf_file, sample in data["samples"].items():
        add(
            f"- **{wf_file}** — sampled {sample['runs_sampled']} of "
            f"{sample['runs_available']} run(s); {sample['sampled_job_minutes']} job-min"
        )
        for runner, hits in sample["runner_hits"].items():
            add(f"  - `{runner}` × {hits}")
        if sample["runs_sampled"] == 0:
            add("  - _no completed runs sampled — placement unverified for this lane._")
    add("")
    add("## Remaining hosted debt (`pending-migration`)")
    add("")
    pending = pending_migration_entries()
    add(f"{len(pending)} registered `pending-migration` job(s) — the Wave-2 worklist:")
    add("")
    by_workflow: dict[str, list[str]] = defaultdict(list)
    for entry in pending:
        by_workflow[str(entry.get("workflow", "?"))].append(str(entry.get("job", "?")))
    for workflow in sorted(by_workflow):
        add(f"- `{workflow}` → {', '.join(sorted(by_workflow[workflow]))}")
    add("")
    add("## Honest limits")
    add("")
    add("- Run counts are exact only when the listing is not truncated (see header).")
    add("- Durations are job-level ONLY for sampled runs; everything else is wall-clock.")
    add("- Nothing here is a billing reading. Dollars come from the org billing API.")
    add("- `runner_name` classification assumes GitHub-hosted runners are named")
    add("  `GitHub Actions N`; a self-hosted runner registered under that name would")
    add("  be misread (none exist in this fleet as of 2026-08-12).")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--sample-jobs", type=int, default=8)
    parser.add_argument("--out", default=None, help="write receipt here instead of stdout")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)

    if not shutil.which("gh"):
        print("FAIL: `gh` is not on PATH — this tool reads the GitHub API through it.")
        return 2

    budget = Budget()
    data = collect(days=args.days, sample_jobs=args.sample_jobs, budget=budget)
    placement = static_placement()

    if args.json_only:
        payload = json.dumps(data, indent=2, sort_keys=True)
    else:
        payload = render_markdown(data, placement) + "\n```json\n" + json.dumps(
            data, indent=2, sort_keys=True
        ) + "\n```\n"

    if args.out:
        Path(args.out).write_text(payload)
        print(f"wrote {args.out} ({budget.spent}/{budget.cap} REST calls spent)")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
