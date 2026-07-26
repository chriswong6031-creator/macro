#!/usr/bin/env python3
"""Enforce Macro Dashboard's commit -> PR -> merge -> live completion contract.

SessionStart records a baseline so a shared checkout's pre-existing dirt is never
mistaken for work from this session. Stop blocks when session-created changes are
uncommitted, unpushed, unmerged, still rendering, or not yet present on production.
Repository rules remain the source of truth; this hook makes them executable.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LIVE_HEALTH_URL = "https://mastermind-x.com/api/health"
GITHUB_API_HOST = "api.github.com"
EXTERNAL_BLOCKERS = {
    "github_unreachable",
    "github_rate_limited",
    "ci_failed",
    "render_pending",
    "render_failed",
    "live_unreachable",
    "live_stale",
}


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False))


def _run(root: Path, *args: str, timeout: int = 45) -> str:
    proc = subprocess.run(
        args,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail[:500]}")
    return proc.stdout.strip()


def _run_raw(root: Path, *args: str, timeout: int = 45) -> str:
    """Run git while preserving porcelain's leading status column."""
    proc = subprocess.run(
        args,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail[:500]}")
    return proc.stdout


def _repo_root(payload: dict[str, Any]) -> Path | None:
    candidates = [
        os.environ.get("CLAUDE_PROJECT_DIR"),
        payload.get("cwd"),
        os.getcwd(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            root = Path(candidate).resolve()
            found = _run(root, "git", "rev-parse", "--show-toplevel")
            return Path(found)
        except Exception:
            continue
    return None


def _state_path(root: Path, payload: dict[str, Any]) -> Path:
    session = re.sub(r"[^A-Za-z0-9_.-]", "_", str(payload.get("session_id") or "default"))
    repo_key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    directory = Path(tempfile.gettempdir()) / "macro-claude-ship-sessions" / repo_key
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{session}.json"


def _file_digest(path: Path) -> str:
    try:
        if path.is_file() and not path.is_symlink():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        if path.is_symlink():
            return "symlink:" + os.readlink(path)
    except OSError:
        pass
    return "missing"


def _fingerprint(root: Path) -> dict[str, str]:
    """Return path -> status/content hash for the current dirty set."""
    output = _run_raw(
        root,
        "git",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        timeout=90,
    )
    result: dict[str, str] = {}
    for line in output.splitlines():
        if len(line) < 4:
            continue
        status, display_path = line[:2], line[3:]
        # For rename records, the destination is the content-bearing path.
        path = display_path.rsplit(" -> ", 1)[-1].strip('"')
        result[path] = f"{status}:{_file_digest(root / path)}"
    return result


def _changed_since_baseline(baseline: dict[str, str], now: dict[str, str]) -> list[str]:
    return sorted(path for path in set(baseline) | set(now) if baseline.get(path) != now.get(path))


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save(path: Path, state: dict[str, Any]) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _github_slug(root: Path) -> tuple[str, str]:
    remote = _run(root, "git", "remote", "get-url", "origin")
    match = re.search(r"github\.com[/:]([^/]+)/([^/\s]+?)(?:\.git)?$", remote)
    if not match:
        raise RuntimeError(f"origin is not a GitHub repository: {remote}")
    return match.group(1), match.group(2)


class RateLimited(RuntimeError):
    """A GitHub call failed because the request quota is spent, not because it was unreachable."""


_TOKEN_CACHE: str | None = None


def _github_token() -> str:
    """Return a GitHub credential: env vars first, then the already-authenticated CLI.

    Claude Code sessions set none of the token env vars, which silently dropped
    every guard evaluation onto the anonymous 60-request/hour-per-IP quota. A
    Stop evaluation spends up to four calls, so a busy session exhausted the
    budget and the guard then failed closed on `github_unreachable` for the rest
    of the hour (measured 2026-07-25: anonymous 0/60 while `gh` held 4998/5000).

    The CLI fallback stores no secret — it reuses the credential `gh auth login`
    already placed on this machine. A missing or logged-out `gh` degrades to the
    previous anonymous behaviour rather than failing.

    Cached for the process lifetime so one evaluation spawns `gh` at most once.
    """
    global _TOKEN_CACHE
    if _TOKEN_CACHE is not None:
        return _TOKEN_CACHE

    token = ""
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            token = value
            break
    if not token:
        try:
            proc = subprocess.run(
                ("gh", "auth", "token"),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                token = proc.stdout.strip()
        except Exception:
            token = ""

    _TOKEN_CACHE = token
    return token


def _http_failure(exc: urllib.error.HTTPError) -> RuntimeError:
    """Classify an HTTP failure so a spent quota does not read as a broken repo.

    `HTTP Error 403: rate limit exceeded` sent sessions hunting for network,
    permission, and remote faults that did not exist. GitHub marks the real
    cause in the response headers, so name it.
    """
    headers = exc.headers or {}
    if exc.code in {403, 429} and headers.get("X-RateLimit-Remaining") == "0":
        limit = headers.get("X-RateLimit-Limit") or "?"
        reset = str(headers.get("X-RateLimit-Reset") or "")
        when = ""
        if reset.isdigit():
            stamp = datetime.fromtimestamp(int(reset), timezone.utc)
            when = f", resets {stamp.strftime('%H:%M:%SZ')}"
        if _github_token():
            hint = "Wait for the reset; no repository or network fault is implied."
        else:
            hint = (
                "The guard is running UNAUTHENTICATED on the 60/hour per-IP quota. "
                "Run `gh auth login` (or export GH_TOKEN) to get the 5000/hour quota."
            )
        return RateLimited(f"GitHub API quota spent (0/{limit}{when}). {hint}")
    return RuntimeError(f"GitHub API request failed: HTTP {exc.code} {exc.reason}.")


def _get_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "macro-dashboard-ship-loop-guard",
    }
    # Authenticate to GitHub and nowhere else. This helper also fetches the
    # public production health endpoint, and attaching the credential to that
    # request would hand a repo-scoped token to an unrelated host.
    if urllib.parse.urlsplit(url).hostname == GITHUB_API_HOST:
        token = _github_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise _http_failure(exc) from exc


def _github_block_code(exc: Exception) -> str:
    """Spent quota and unreachable API are both external, but they are not the same problem."""
    return "github_rate_limited" if isinstance(exc, RateLimited) else "github_unreachable"


def _latest_merged_pr(owner: str, repo: str, branch: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {"state": "closed", "head": f"{owner}:{branch}", "base": "main", "per_page": "20"}
    )
    pulls = _get_json(f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}")
    merged = [pull for pull in pulls if pull.get("merged_at")]
    return max(merged, key=lambda pull: pull.get("merged_at") or "") if merged else None


def _failing_ci_message(display: list[str]) -> str:
    """The blocking verdict for reds this pull request genuinely owns.

    `_stop` keys `ci_failed` off the "Failing" prefix, so every blocking variant
    must keep it.
    """
    return (
        "Failing CI: "
        + ", ".join(display[:8])
        + ". These run against the merged pull request's own head commit, so a later "
        "fix on main does not clear them: re-run the failed job "
        "(`gh run rerun --failed <run-id>`) once the cause is fixed, or carry the fix "
        "through a follow-up pull request with green CI of its own."
    )


def _head_check_runs(owner: str, repo: str, head_sha: str) -> list[dict[str, Any]]:
    """Every check run on ``head_sha``, following pagination to the end.

    A single `per_page=100` call silently truncated: PR #3629's head carries 101
    check runs, so a red beyond the first page was invisible and the gate failed
    OPEN — the one direction it may never fail. A short page means nothing is
    left; a full page with no `total_count` keeps paging rather than guessing the
    tail away. The 5-page cap bounds a pathological head's share of the API budget.
    """
    endpoint = f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/check-runs"
    runs: list[dict[str, Any]] = []
    for page in range(1, 6):
        query = urllib.parse.urlencode({"per_page": "100", "page": str(page)})
        payload = _get_json(f"{endpoint}?{query}")
        batch = payload.get("check_runs") or []
        runs.extend(batch)
        total = int(payload.get("total_count") or 0)
        if len(batch) < 100 or (total and len(runs) >= total):
            break
    return runs


def _started_stamp(run: dict[str, Any], *keys: str) -> str:
    """First non-empty stamp among ``keys`` — workflow runs and check runs name it differently."""
    for key in keys:
        value = str(run.get(key) or "")
        if value:
            return value
    return ""


def _parse_stamp(value: str) -> datetime | None:
    """A GitHub `...Z` stamp as a datetime, or None when it is absent or malformed."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _merged_content_green(
    root: Path, owner: str, repo: str, merge_sha: str
) -> dict[str, Any] | None:
    """A completed+success ci.yml run whose head is a main DESCENDANT of ``merge_sha``.

    A descendant's tree contains the merge, so a full green run there proves the
    merged content passes — categorically stronger than arguing about any single
    check name. Ancestry alone is load-bearing, so unlike ``_render_status`` there
    is deliberately no created_at floor: a descendant carried this merge whenever
    its run happened.

    The fetch is best-effort because the candidate heads are brand-new main
    commits this checkout may not know yet, while a fixture or offline checkout
    must still be able to answer from its local view rather than erroring out.
    """
    if not merge_sha:
        return None
    try:
        _run(root, "git", "fetch", "origin", "main", timeout=90)
    except Exception:
        pass
    query = urllib.parse.urlencode({"branch": "main", "per_page": "20"})
    endpoint = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/ci.yml/runs"
    for run in _get_json(f"{endpoint}?{query}").get("workflow_runs", []):
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            continue
        head = str(run.get("head_sha") or "")
        if head and _is_ancestor(root, merge_sha, head):
            return run
    return None


def _base_side_confirmations(
    owner: str,
    repo: str,
    head_sha: str,
    head_branch: str,
    merged_at: str,
    reference: str,
    names: list[str],
) -> dict[str, dict[str, str]]:
    """For each name in ``names``, the sibling heads that failed it before this merge.

    Returns name -> {sibling head_branch: sibling head_sha}. Independence is
    structural: a distinct head_branch that is not ours, on a sha that is not ours.
    Candidate runs must be `failure` runs created inside [merged_at - 24h,
    merged_at) — only a red that predates our merge is provably not caused by our
    merged content reaching the sibling's moving base.

    Candidates are keyed BY HEAD SHA, never per branch. A branch whose newer head
    dodged the defect does not retract the red its older head recorded: on the
    2026-07-26 live replay w2-support-page's 13:22 head had `ci-pack-1` green, and
    per-branch keep-newest silently discarded that branch's valid 12:51 red.

    Probe order is PROXIMITY to ``reference`` — the moment our own red started —
    not newest-first. This class of base-side defect is a temporal STRIPE (the
    chronicle red depends on the base vintage the merge ref happened to catch), so
    the siblings that ran nearest our failing check are the most probative, and
    proximity is immune to a burst of newer candidates crowding the listing.
    Newest-first UNDER-CONFIRMED a true base-side red in the field: with merged_at
    13:24:17Z and our `ci-pack-1` red started 12:06:25Z, a 13:14–13:22Z burst of
    other sessions' pushes filled the top five candidate slots and every one had
    `ci-pack-1` GREEN (their runs failed on other checks), while the 11:59–12:17Z
    band around our own red held `ci-pack-1` completed+failure on SIX of seven
    distinct branches (outbox 12:07:08, cool-allen 12:04:51, w1-china 12:09:53,
    zealous 12:10:30, inline-shim 11:59:41, pss-f2 12:17:30; only jolly 12:00:48
    was green). An undated candidate cannot be ranked and sorts last.

    A confirmation is matched by CHECK SUITE, never by the check run's own clock.
    `github.sha` is frozen at event time, so `started_at` on a check run measures
    queue latency, not tree vintage: under runner contention (load ~44) a run
    created 13:22:00 had its `ci-pack-1` job start at 13:25:04 — after the merge —
    while still testing the pre-merge tree. The suite id is the precise linkage
    (workflow runs carry `check_suite_id`, check runs carry `check_suite.id`): a
    rerun replaces check runs within the SAME suite and replays the frozen tree, so
    it stays valid evidence, whereas a fresh post-merge pull_request event mints a
    NEW suite and is not. A missing suite id on either side is not a confirmation.

    Costs one listing call plus one probe per candidate head (at most 8). The probe
    is UNFILTERED so a single call answers every candidate name; truncation there
    can only UNDER-confirm, which keeps the red.
    """
    if not (merged_at and head_branch and names):
        return {}
    merged_dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
    floor = (merged_dt - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    reference_dt = _parse_stamp(reference) or merged_dt

    def in_window(stamp: str) -> bool:
        # GitHub emits second-precision `...Z` stamps, so plain string compares
        # are ordering-correct (same reasoning as `_render_status`).
        return bool(stamp) and floor <= stamp < merged_at

    def run_start(run: dict[str, Any]) -> str:
        return _started_stamp(run, "run_started_at", "created_at")

    def proximity(run: dict[str, Any]) -> tuple[int, timedelta]:
        parsed = _parse_stamp(run_start(run))
        if parsed is None:
            return 1, timedelta(0)
        return 0, abs(parsed - reference_dt)

    endpoint = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/ci.yml/runs"
    query = urllib.parse.urlencode({"event": "pull_request", "per_page": "100"})
    candidates: dict[str, dict[str, Any]] = {}
    for run in _get_json(f"{endpoint}?{query}").get("workflow_runs", []):
        if run.get("conclusion") != "failure":
            continue
        branch = str(run.get("head_branch") or "")
        sha = str(run.get("head_sha") or "")
        if not branch or branch == head_branch or not sha or sha == head_sha:
            continue
        if not in_window(run_start(run)):
            continue
        # One probe per head sha. The listing is newest-first, so the first run
        # seen for a sha is the one whose suite owns that head's current checks.
        candidates.setdefault(sha, run)

    wanted = set(names)
    found: dict[str, dict[str, str]] = {}
    for probe in sorted(candidates.values(), key=proximity)[:8]:
        sha = str(probe.get("head_sha") or "")
        branch = str(probe.get("head_branch") or "")
        suite = probe.get("check_suite_id")
        listing = _get_json(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs"
            f"?{urllib.parse.urlencode({'per_page': '100'})}"
        ).get("check_runs", [])
        for run in listing:
            name = str(run.get("name") or "")
            if name not in wanted:
                continue
            if run.get("status") != "completed" or run.get("conclusion") != "failure":
                continue
            run_suite = (run.get("check_suite") or {}).get("id")
            if suite is None or run_suite is None or run_suite != suite:
                continue
            # Keyed by branch: two heads of one branch are one independent observation.
            found.setdefault(name, {})[branch] = sha
        if all(len(found.get(name) or {}) >= 2 for name in wanted):
            break
    return found


def _check_ci(
    root: Path,
    owner: str,
    repo: str,
    head_sha: str,
    merge_sha: str,
    merged_at: str,
    head_branch: str,
) -> tuple[bool, str]:
    """Judge the merged pull request's OWN head commit, then ask whose red it is.

    Head-only scoring stays deliberate: main's combined status is the product of
    every concurrent session's merges, so scoring against it would let an
    unrelated green main mask this pull request's red check (and an unrelated red
    one block a clean ship). The head commit is the only sha that answers "did
    THIS work pass".

    What a head sha cannot answer is WHOSE red it is. A defect already on main at
    pull time lands on the pull request's merge ref, and there it is PERMANENT:
    `gh run rerun` replays the frozen `refs/pull/N/merge` tree — a merged pull
    request's merge ref never recomputes against a healed base — and a follow-up
    pull request is impossible when the fix is already on main. Observed
    2026-07-26: the chronicle gate-1 staleness window (heal owned by PR #3634,
    still open) pinned merged PR #3629's `ci-pack-1` red forever; earlier #3503
    inherited a `tier-gate` red from #3488 the same way. Both sessions shipped
    green work and were forced into the `SHIP LOOP BLOCKED:` escape.

    The obvious comparisons are structurally unavailable in THIS repo (verified
    2026-07-26). ci.yml triggers on `pull_request` + `workflow_dispatch` ONLY, so
    main commits carry ZERO ci.yml check runs — merge base 8773e511b79 held only
    third-party "Workers Builds"/"Supabase Preview" app runs — which kills
    "compare the same check on the merge-base sha". ci-main-heartbeat.yml is
    schedule-only and mirrors a curated subset of individual pure-guard job names
    (nav-gap, tier-gate, …); it never runs `ci-pack-N`, which is exactly where
    suite failures like the chronicle pair surface, so name-matching against
    heartbeat conclusions cannot reach a pack. And a pack's legacy member names
    exist only as `if: false` definitions that publish `skipped` check runs —
    member granularity is not available at all.

    So the evidence model uses the two sources that DO exist.

    E1, merged-content-green (strongest; clears EVERY bad conclusion): a
    completed+success ci.yml run on branch=main whose head_sha is a main
    descendant of merge_sha. A descendant's tree contains the merge, so one full
    green run there proves the merged content passes and no per-name argument is
    needed. No ci.yml run on main has ever existed (total_count=0 today), which is
    the point: E1 is the OPERATOR'S DELIBERATE UNBLOCK LEVER — dispatch ci.yml on
    main once the base-side cause is healed and every pinned session clears at
    once. This mirrors `_render_status` accepting a dispatched render on a
    descendant.

    E2, base-side-red confirmation (per check name, `failure` conclusions only):
    the SAME name concluded `failure` on at least TWO INDEPENDENT concurrent
    sibling pull-request heads — distinct head_branch values, neither ours, on
    shas that are not ours — in runs created before this merge and no more than 24h
    before it. Run-level conclusions are NEVER evidence: in the 2026-07-26
    12:50–13:03Z window three sibling ci.yml runs (gracious-moser, brain-symmetric,
    brain-consistency) concluded failure with `ci-pack-1` GREEN — their own bugs —
    so nothing short of a per-head probe of the same NAME counts. The candidate run
    must PREDATE merged_at: an open pull request's merge ref recomputes against the
    moving base, so a post-merge sibling red can have OUR merged content as its
    cause. Inside that window, heads are probed in order of PROXIMITY to the moment
    our own red started (this defect class is a temporal stripe in the base
    vintage), and the second hop matches on CHECK SUITE rather than on the check
    run's clock (a job queued late under contention still tests the event-frozen
    tree). Both rules replaced weaker ones that under-confirmed a genuine base-side
    red on the live replay; `_base_side_confirmations` carries the dated evidence.
    The bar is two distinct BRANCHES — several heads of one branch count once —
    because pack-level names are the coarsest granularity available (see above):
    `ci-pack-1` fronts many jobs, so one sibling sharing the name is a real
    coincidence rather than a shared cause. Evidence is contemporaneous by
    construction (one listing page is roughly the last few hours on this repo),
    which matches when the guard actually evaluates: right after the merge.

    Fail-closed throughout. A lone sibling confirmation keeps the red. An absent
    merged_at, head_branch, or merge_sha skips the gate that depends on it rather
    than assuming it, and a missing check-suite id on either side of a probe is not
    a confirmation. The two gates degrade independently — either one's failure
    means "that gate found no exclusions" and is named in the reason, never a
    reclassified or swallowed verdict. Conclusions other than `failure`
    (cancelled, timed_out) are not E2-excludable, because rerunning the frozen
    tree genuinely can green those, while E1 clears them wholesale by proving the
    content. Pending checks keep the "CI still running" verdict even when every
    bad check is excluded. And the head listing is paginated for the same
    fail-closed reason: PR #3629's head carries 101 check runs, so the old single
    `per_page=100` call could hide a red past the first page.
    """
    runs = _head_check_runs(owner, repo, head_sha)
    if not runs:
        return False, "No CI check runs were found for the pull-request head."
    bad: list[tuple[str, str]] = []
    pending: list[str] = []
    failure_starts: list[str] = []
    for run in runs:
        name = str(run.get("name") or "unnamed check")
        lowered = name.lower()
        if "workers builds" in lowered and "macro" in lowered:
            continue
        if run.get("status") != "completed":
            pending.append(name)
        elif run.get("conclusion") not in {"success", "neutral", "skipped"}:
            conclusion = str(run.get("conclusion"))
            bad.append((name, conclusion))
            if conclusion == "failure":
                stamp = _started_stamp(run, "started_at")
                if stamp:
                    failure_starts.append(stamp)
    if not bad:
        # The green path costs exactly one API call and touches no git: evidence
        # is only ever gathered to argue about a red.
        if pending:
            return False, "CI still running: " + ", ".join(pending[:8])
        return True, ""

    display = {entry: f"{entry[0]} ({entry[1]})" for entry in bad}
    excluded: set[tuple[str, str]] = set()
    evidence: dict[str, list[str]] = {}
    notes: list[str] = []
    unavailable: list[str] = []

    try:
        green = _merged_content_green(root, owner, repo, merge_sha)
    except Exception as exc:
        green = None
        unavailable.append(f"merged-content-green: {str(exc)[:200].strip()}")
    if green is not None:
        excluded.update(bad)
        proof = str(green.get("head_sha") or "")
        notes.append(
            "Ignored failing CI on the merged head: "
            + ", ".join(display[entry] for entry in bad[:8])
            + f" — full ci.yml run {green.get('id')} concluded success on main descendant "
            f"{proof[:12]}, proving the merged content green; the head's red is pinned to "
            "the frozen pull_request merge ref (base-side)."
        )
    else:
        names: list[str] = []
        for name, conclusion in bad:
            if conclusion == "failure" and name not in names:
                names.append(name)
        # Proximity anchor: when OUR OWN red started. Same-format `...Z` stamps, so
        # the string min is the earliest one. Nothing dated falls back to the merge.
        reference = min(failure_starts) if failure_starts else merged_at
        try:
            confirmations = _base_side_confirmations(
                owner, repo, head_sha, head_branch, merged_at, reference, names
            )
        except Exception as exc:
            confirmations = {}
            unavailable.append(f"base-side confirmation: {str(exc)[:200].strip()}")
        for name in names:
            heads = confirmations.get(name) or {}
            if len(heads) < 2:
                continue
            cited = [f"{sha[:7]}@{branch}" for branch, sha in heads.items()]
            evidence[name] = cited
            excluded.add((name, "failure"))
            notes.append(
                f"Ignored base-side CI: {name} (failure) — the same check failed on "
                f"{len(heads)} independent concurrent PR head(s) ({', '.join(cited)}) before "
                "this merge; the red pre-existed on the shared base, and re-runs replay the "
                "frozen merge ref so it can never self-clear."
            )

    unexcluded = [display[entry] for entry in bad if entry not in excluded]
    if not unexcluded:
        # A still-running check outranks an exclusion: coverage is unknown, not clear.
        if pending:
            return False, "CI still running: " + ", ".join(pending[:8])
        return True, " ".join(notes)
    message = _failing_ci_message(unexcluded)
    if evidence:
        cited = "; ".join(f"{name} ({', '.join(evidence[name])})" for name in evidence)
        message = f"{message} (Ignored as base-side: {cited}.)"
    if unavailable:
        message = f"{message} (Base-side evidence unavailable: {'; '.join(unavailable)}.)"
    return False, message


# render.yml's push filter, verbatim. The three sweep scripts and lib/pages.py
# rewrite every page in site/ (shim injection, inline-CSS externalization, ?v=
# stamping, CSS preload hints), so the lane renders on them too — they were
# added to the workflow after #3558 shipped a sweep change that triggered
# nothing. Missing them here under-required a render, the fail-OPEN direction.
_RENDER_INPUT_PATHS = {
    "scripts/inject_data_base.py",
    "scripts/externalize_css.py",
    "scripts/optimize_assets.py",
    "lib/pages.py",
}
# `scripts/build_*.py`. GitHub path globs do not cross `/`, so neither does this
# — and the merits agree independently of that semantics: render.yml invokes
# nothing under `scripts/research/`, so a nested `build_*.py` there produces
# nothing in the lane and a render for it would be an unsatisfiable demand.
_RENDER_BUILDER = re.compile(r"^scripts/build_[^/]*\.py$")


def _plain_copy_pairs(root: Path) -> set[str]:
    """Names under ``templates/`` that also ship as a committed ``site/`` copy.

    Loaded from ``scripts/check_template_site_sync.find_pairs`` — the very
    enumeration CI's ui.template_site_sync gate walks — rather than re-deriving
    the rule here, so the exemption in ``_render_triggering_paths`` and the sync
    law can never drift apart as pairs are added or retired (56 today).

    Every failure path returns the empty set, which REQUIRES a render rather
    than skipping one: an unreadable pair list is ignorance, not permission.
    """
    module_path = root / "scripts" / "check_template_site_sync.py"
    # It is loaded by PATH, never registered in sys.modules, and its own
    # `sys.path.insert` is rolled back: reading the pair list must not leave a
    # repo root on the import path of whatever process is asking.
    saved_path = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location("_mm_template_site_sync", module_path)
        if spec is None or spec.loader is None:
            return set()
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {name for name, _tpl, _site in module.find_pairs(root)}
    except Exception:
        return set()
    finally:
        sys.path[:] = saved_path


def _render_triggering_paths(changed: list[str], pairs: set[str]) -> bool:
    """True when ``changed`` touches something the render lane actually produces.

    render.yml's push filter is `templates/**`, so ANY templates/ path used to
    demand a render. But the lane only produces two things: re-baked `.j2` pages
    and the `?v=` content-hash re-stamp. A paired PLAIN-COPY asset — a non-.j2
    file under templates/ that also ships as `site/<name>` — is neither. Its
    site/ copy is committed straight to main, and the VPS `macro-update` cron
    pulls main every 3 minutes, so those bytes are live within minutes whether
    render ever runs or not.

    Demanding a render for them was a real, recurring false gate. Observed
    2026-07-26 on PR #3671 (templates/mm_brain.js + site/mm_brain.js, no .j2):
    merged 14:30Z, VPS served the new bytes by 14:33Z, byte-verified at three
    successive box HEADs — and the guard still refused Stop with `render_pending`
    for 40+ minutes, while 28 of the last 30 render.yml runs concluded
    `cancelled` and none concluded `success` (a repo-wide treadmill jam from a
    concurrent merge spree, unrelated to the PR). House law forbids cancelling
    or re-running a shared in-flight render to unblock a session, so the only
    exit was the `SHIP LOOP BLOCKED:` escape — which reads as a failed ship when
    the deploy had in fact succeeded. `go-live-deploy-mechanics` has recorded
    this as "a real false gate" since #3464/#3486.

    KNOWN AND ACCEPTED LIMIT: the exemption gives up the `?v=` re-stamp for the
    assets that carry one. The Caddyfile pins `?v=`-carrying requests to
    `max-age=31536000, immutable` for an enumerated list (theme.js, live.js,
    theme.css, product-nav-icons.css, onboard.*, landing.css, account.js,
    nav_market.js, supabase.js, data_base.js, chat*.css, assets/{css,landing}/*),
    so for THOSE a warm-cache visitor keeps the old body until a render re-hashes
    the pages that reference them (`asset-stamp-frozen-not-stable`). Assets off
    that list — mm_brain.js among them, which is why #3671 was fully live — fall
    back to `max-age=300, must-revalidate` and go live on the next revalidate.
    New visitors always get fresh bytes either way. Trading a stamp refresh for
    an unsatisfiable gate is the operator's call, taken deliberately.

    A `.j2` page, a builder, a sweep script, or anything else under templates/
    (`templates/fonts/`, a subdirectory, an unpaired asset) still requires the
    render. So does a paired asset whose `site/` twin is NOT in the same commit:
    that is a one-sided edit the sync gate rejects anyway, and it means the live
    bytes have not moved. Fail-closed on everything the pair list cannot vouch for.
    """
    touched = set(changed)
    for item in changed:
        if item in _RENDER_INPUT_PATHS or _RENDER_BUILDER.match(item):
            return True
        if not item.startswith("templates/"):
            continue
        name = item[len("templates/") :]
        if name in pairs and f"site/{name}" in touched:
            continue
        return True
    return False


def _needs_render(root: Path, merge_sha: str, start_head: str, head: str) -> bool:
    """Whether a push-triggered render must exist for ``merge_sha``.

    Scoped to THIS merge's own diff, not the whole session range. render.yml's
    push trigger is path-filtered, so a push render attributable to this merge
    can exist if and only if merge_sha ITSELF touched those paths. (What
    SATISFIES the requirement is a separate question: ``_render_status`` accepts
    either the push render at merge_sha or a later successful render on a main
    descendant, per the shared-lane coalescing law. That widens coverage, not
    this requirement, which stays scoped as below.)

    start_head..head was the wrong basis on a shared main: this repo runs many
    concurrent sessions, and a session that syncs its worktree to origin/main
    sweeps every OTHER session's merges into that range. One unrelated
    templates/ merge then demanded a render on a merge commit that could never
    have produced one — an unsatisfiable block, not a real gap. (Observed
    2026-07-25: PR #3481 changed only .github/workflows/ci.yml, yet five
    template/builder files from concurrent merges set needs_render.)

    Within that scope, ``_render_triggering_paths`` asks the narrower question
    the gate actually cares about: not "would render.yml fire?" but "does this
    merge contain anything render PRODUCES?" — see its docstring for why a
    paired plain-copy asset is live without one.

    The pair list is read from the worktree, which carries this merge's files
    (the session's branch is what was merged). A worktree that cannot answer
    yields no pairs and therefore requires the render.
    """
    try:
        changed = _run(
            root, "git", "diff", "--name-only", f"{merge_sha}^", merge_sha
        ).splitlines()
    except Exception:
        # Root/orphan merge or unavailable parent — fall back to the session
        # range, which over-requires rather than under-requires a render.
        changed = _run(root, "git", "diff", "--name-only", start_head, head).splitlines()
    return _render_triggering_paths(changed, _plain_copy_pairs(root))


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Whether ``descendant``'s history contains ``ancestor`` (equal shas count).

    Every failure mode collapses to False on purpose: rc=1 means "not an
    ancestor" and rc=128 means the sha is unknown to this checkout, and neither
    one can establish that the descendant's tree carried the merge. Here both
    read the same way — not covering.
    """
    try:
        _run(root, "git", "merge-base", "--is-ancestor", ancestor, descendant)
        return True
    except Exception:
        return False


def _render_status(
    root: Path, owner: str, repo: str, merge_sha: str, merged_at: str
) -> tuple[str, str]:
    """Judge render COVERAGE for ``merge_sha``, not a dedicated run at that sha.

    render.yml is one shared coalescing lane (`concurrency.group: pipeline-render`
    with `cancel-in-progress: false`): a render already running always finishes,
    while a run still PENDING is superseded — GitHub displays it ``cancelled`` —
    the moment a newer merge queues its own. The survivor's scope-union `pick`
    step then renders every region dirty since its last covering watermark, so ONE
    success at any later main descendant covers every earlier merge in the train.
    AGENTS.md §"Shared render-lane safety" states exactly this: do not demand a
    dedicated successful run for every merge SHA.

    Requiring `head_sha == merge_sha` therefore made every merge-train member
    except the last unsatisfiable, and permanently — a superseded run can never
    re-conclude on its own. Observed 2026-07-26: PR #3572 merged as b4449443590,
    its push render 30190635141 was superseded-cancelled seconds later, and
    descendant run 30193723520 (push, main, 8f5cfe12a66) concluded ``success``
    with b4449443590 in its history — yet the guard returned ``failed`` forever
    and forced a manual ~50-minute rerun of work already covered.

    Coverage is now (a) a successful push render at merge_sha itself — one API
    call, the common case, unchanged — or (b) a successful later render whose
    head_sha is a main DESCENDANT of merge_sha. Descendants are the only runs
    whose checkout contained the merge; a sibling or pre-merge head rendered a
    tree without it. The ``merged_at`` floor is belt-and-braces (ancestry already
    excludes pre-merge heads, but a re-run of pre-merge history must not read as
    coverage). A candidate still in flight keeps the verdict at ``pending``: a
    queued or running render may yet deliver the coverage this merge needs.
    """
    endpoint = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/render.yml/runs"
    )

    exact_query = urllib.parse.urlencode(
        {"event": "push", "head_sha": merge_sha, "per_page": "20"}
    )
    exact = _get_json(f"{endpoint}?{exact_query}").get("workflow_runs", [])
    if any(
        run.get("status") == "completed" and run.get("conclusion") == "success"
        for run in exact
    ):
        return "success", ""

    # The descendant scan. Filter client-side: the endpoint takes one `event`
    # value only, and a rejected server-side parameter would 422 the whole guard.
    branch_query = urllib.parse.urlencode({"branch": "main", "per_page": "50"})
    listing = _get_json(f"{endpoint}?{branch_query}").get("workflow_runs", [])
    covering: list[dict[str, Any]] = []
    for run in listing:
        if run.get("event") not in {"push", "workflow_dispatch"}:
            continue
        created = str(run.get("created_at") or "")
        # GitHub emits second-precision `...Z` stamps, so a plain string compare
        # is ordering-correct. A missing stamp on either side skips the cutoff
        # rather than guessing at it.
        if created and merged_at and created < merged_at:
            continue
        head = str(run.get("head_sha") or "")
        if not head or not _is_ancestor(root, merge_sha, head):
            continue
        covering.append(run)
    if any(
        run.get("status") == "completed" and run.get("conclusion") == "success"
        for run in covering
    ):
        return "success", ""

    # An exact-sha run also appears in the branch listing; key on the run id so
    # the verdict below weighs it once.
    candidates = {run.get("id"): run for run in (*exact, *covering)}
    if not candidates:
        return "pending", "The required render workflow has not started yet."

    def _created(run: dict[str, Any]) -> str:
        return str(run.get("created_at") or "")

    in_flight = [run for run in candidates.values() if run.get("status") != "completed"]
    if in_flight:
        run = max(in_flight, key=_created)
        return "pending", f"Render workflow is {run.get('status') or 'pending'}."

    newest = max(candidates.values(), key=_created)
    return "failed", (
        f"Render workflow concluded {newest.get('conclusion') or 'unknown'} "
        f"(run {newest.get('id')}), and no later successful render on a main "
        "descendant of this merge exists yet: re-run that run "
        f"(`gh run rerun {newest.get('id')}`) once the cause is fixed, or dispatch "
        "render.yml on main. The lane unions every dirty scope since its last "
        "covering watermark, so one success at any later main commit covers this "
        "merge — a dedicated run at this exact sha is not required."
    )


def _find_commit(value: Any) -> str:
    """Find a plausible deployed git SHA in a health payload."""
    preferred = {"commit", "commit_sha", "git_sha", "git_commit", "revision", "sha"}
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in preferred and isinstance(child, str):
                match = re.search(r"\b[0-9a-f]{7,40}\b", child, re.I)
                if match:
                    return match.group(0)
        for child in value.values():
            found = _find_commit(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_commit(child)
            if found:
                return found
    return ""


def _block(
    path: Path,
    state: dict[str, Any],
    payload: dict[str, Any],
    code: str,
    reason: str,
) -> None:
    """Block Stop, except after a repeated and explicitly reported external blocker."""
    previous = state.get("last_blocker")
    count = int(state.get("blocker_count") or 0) + 1 if previous == code else 1
    state["last_blocker"] = code
    state["blocker_count"] = count
    _save(path, state)
    final = str(payload.get("last_assistant_message") or "").lstrip()
    if (
        code in EXTERNAL_BLOCKERS
        and payload.get("stop_hook_active")
        and count >= 2
        and final.startswith("SHIP LOOP BLOCKED:")
    ):
        return
    _emit(
        {
            "decision": "block",
            "reason": (
                f"SHIP LOOP {code}: {reason}\n"
                "Continue the task and complete commit → push → PR → CI → squash-merge → "
                "render/deploy → live verification. If the same genuine external blocker "
                "persists after another attempt, finish with `SHIP LOOP BLOCKED:` and the "
                "specific evidence."
            ),
        }
    )


def _session_start(root: Path, path: Path, payload: dict[str, Any]) -> None:
    source = str(payload.get("source") or "")
    state = _load(path)
    if state is None or source in {"startup", "clear"}:
        state = {
            "root": str(root),
            "start_head": _run(root, "git", "rev-parse", "HEAD"),
            "baseline": _fingerprint(root),
            "last_blocker": "",
            "blocker_count": 0,
        }
        _save(path, state)
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "MANDATORY SHIP LOOP: Repository rules grant standing approval for "
                    "commit, push, pull request, CI repair, same-day squash merge, deploy "
                    "waiting, and real-live verification. Work only in a fresh "
                    ".claude/worktrees/ claude/* branch. Do not stop at a local change, "
                    "commit, or open PR. This session's starting dirty files were recorded "
                    "and are excluded from enforcement."
                ),
            }
        }
    )


def _fast_forwarded_onto_main(root: Path) -> bool:
    """Whether HEAD is origin/main's own history with nothing of this session on top.

    The exemption above this one catches a session that never moved. A stand-down
    session — one assigned a defect that turns out to be already fixed on main,
    the common shape under the duplicate-fixes playbook — DOES move: it runs
    `git reset --hard origin/main` to verify the fix at tip before concluding,
    which walks HEAD off start_head while creating zero commits of its own.

    From there the full chain is unsatisfiable. GitHub refuses a zero-diff pull
    request ("No commits between main and <branch>"), and `unmerged` is not in
    EXTERNAL_BLOCKERS, so the repeated-blocker `SHIP LOOP BLOCKED:` escape never
    arms. Observed 2026-07-26 on claude/serene-colden-e5b716: the only exit was
    resetting BACK to start_head to re-qualify for the no-op exemption — a
    non-obvious and wasteful ritual for a session that verified and built nothing.

    Fail-closed, and the fetch is load-bearing. Ancestry has to be judged against
    origin's CURRENT tip, never a stale local ref this worktree happened to keep,
    so a fetch that does not SUCCEED means the exemption simply does not apply and
    the ordinary chain takes over — whose GitHub-side failures are escapable
    external blockers, so nothing is trapped by going offline. The ancestry test
    and the zero-ahead count are belt-and-braces statements of one claim; both
    must hold, and every git failure — a failed fetch, rc=1 for "not an ancestor",
    rc=128 for an origin/main this checkout cannot name — reads as "not exempt".

    Shipped sessions are untouched: a squash merge mints a NEW sha, so a merged
    branch head is never an ancestor of origin/main and still falls through to the
    merged-PR, CI, render, and live verification exactly as before.

    The branch gate must run BEFORE this, and that ordering is load-bearing rather
    than cosmetic. Ancestry proves POSITION, never authorship: a session that
    synced to someone else's fix and a session that committed its own work on main
    and pushed it straight to origin/main both end with HEAD equal to origin's tip
    and a zero ahead-count, and nothing here can tell them apart. The second one
    genuinely shipped something, so exempting it would skip the render and live
    gates on live work — fail-open, which this guard may never be. Running the
    branch check first leaves that session blocking on `unsafe_branch` and makes
    the exemption reachable only from a claude/* worktree branch, where a zero
    ahead-count really does mean nothing shippable exists.
    """
    try:
        _run(root, "git", "fetch", "origin", "main", timeout=90)
        _run(root, "git", "merge-base", "--is-ancestor", "HEAD", "origin/main")
        return _run(root, "git", "rev-list", "--count", "origin/main..HEAD") == "0"
    except Exception:
        return False


def _stop(root: Path, path: Path, payload: dict[str, Any]) -> None:
    state = _load(path)
    # Hooks can be installed during an already-running session. Fail open once so
    # that pre-hook work is not misclassified; every later session is enforced.
    if state is None:
        return

    baseline = state.get("baseline") or {}
    dirty = _changed_since_baseline(baseline, _fingerprint(root))
    if dirty:
        preview = ", ".join(dirty[:12])
        _block(path, state, payload, "uncommitted", f"Session-created changes remain: {preview}")
        return

    head = _run(root, "git", "rev-parse", "HEAD")
    if head == state.get("start_head"):
        return

    branch = _run(root, "git", "branch", "--show-current")
    if not branch or branch in {"main", "master"}:
        _block(path, state, payload, "unsafe_branch", f"Work is on {branch or 'detached HEAD'}.")
        return

    if _fast_forwarded_onto_main(root):
        return

    # A missing upstream means one of two opposite things: never pushed, or
    # pushed and merged, with the remote branch auto-deleted on merge. Blocking
    # here judged the second case as the first and made a COMPLETED ship
    # unsatisfiable — the branch is merged, so there is nothing left to push and
    # recreating it would be wrong. The merged-PR lookup below is what tells the
    # two apart (GitHub keeps serving a merged PR by head ref after the branch is
    # gone), so defer the verdict rather than pre-empt it.
    try:
        upstream = _run(root, "git", "rev-parse", "--abbrev-ref", "@{upstream}")
    except RuntimeError:
        upstream = ""
    if upstream:
        ahead = int(_run(root, "git", "rev-list", "--count", f"{upstream}..HEAD") or "0")
        if ahead:
            _block(path, state, payload, "unpushed", f"{ahead} commit(s) have not been pushed.")
            return

    try:
        owner, repo = _github_slug(root)
        pull = _latest_merged_pr(owner, repo, branch)
    except Exception as exc:
        _block(path, state, payload, _github_block_code(exc), str(exc))
        return
    if not pull:
        # No merged pull request: an absent upstream now genuinely means unpushed.
        if not upstream:
            _block(path, state, payload, "unpushed", f"{branch} has no upstream branch.")
        else:
            _block(
                path, state, payload, "unmerged", f"No merged main pull request found for {branch}."
            )
        return

    head_sha = str((pull.get("head") or {}).get("sha") or head)
    # The CI gate needs the merge's identity too: a red on the merged head may be
    # base-side, and only merge_sha (ancestry), merged_at (the pre-merge window),
    # and the pull request's own head ref (sibling independence) can show that.
    head_ref = str((pull.get("head") or {}).get("ref") or "")
    merge_sha = str(pull.get("merge_commit_sha") or "")
    merged_at = str(pull.get("merged_at") or "")
    try:
        ci_ok, ci_reason = _check_ci(
            root, owner, repo, head_sha, merge_sha, merged_at, head_ref
        )
    except Exception as exc:
        _block(path, state, payload, _github_block_code(exc), str(exc))
        return
    if not ci_ok:
        code = "ci_failed" if ci_reason.startswith("Failing") else "render_pending"
        _block(path, state, payload, code, ci_reason)
        return
    try:
        _run(root, "git", "fetch", "origin", "main", timeout=90)
        _run(root, "git", "merge-base", "--is-ancestor", merge_sha, "origin/main")
    except Exception as exc:
        _block(path, state, payload, "github_unreachable", f"Merge is not confirmed on origin/main: {exc}")
        return

    needs_render = _needs_render(root, merge_sha, str(state.get("start_head")), head)
    if needs_render:
        try:
            status, detail = _render_status(root, owner, repo, merge_sha, merged_at)
        except Exception as exc:
            _block(path, state, payload, _github_block_code(exc), str(exc))
            return
        if status != "success":
            _block(
                path,
                state,
                payload,
                "render_failed" if status == "failed" else "render_pending",
                detail,
            )
            return

    try:
        deployed = _find_commit(_get_json(LIVE_HEALTH_URL))
        if not deployed:
            raise RuntimeError("Production health response did not include a git commit.")
        deployed_full = _run(root, "git", "rev-parse", deployed)
        _run(root, "git", "merge-base", "--is-ancestor", merge_sha, deployed_full)
    except Exception as exc:
        _block(path, state, payload, "live_stale", f"Production does not yet contain the merge: {exc}")
        return

    if ci_reason:
        # A pass that rests on excluded reds is a judgement call; the operator has
        # to be able to audit which checks were ignored and on what evidence. It is
        # emitted only here, once every later gate has passed: hook stdout must
        # stay a single JSON object, and a systemMessage line ahead of a later
        # block line would make the whole output unparseable — silently defeating
        # that block, the one direction this guard may never fail.
        _emit({"systemMessage": f"Ship-loop CI gate: {ci_reason}"})

    try:
        path.unlink()
    except OSError:
        pass


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    root = _repo_root(payload)
    if root is None:
        return
    path = _state_path(root, payload)
    event = str(payload.get("hook_event_name") or "")
    try:
        if event == "SessionStart":
            _session_start(root, path, payload)
        elif event == "Stop":
            _stop(root, path, payload)
    except Exception as exc:
        # A broken enforcement hook must be visible, but must not brick Claude.
        if event == "Stop":
            _emit(
                {
                    "decision": "block",
                    "reason": (
                        "SHIP LOOP guard_error: The completion guard failed unexpectedly: "
                        f"{exc}. Repair `.claude/hooks/ship_loop_guard.py` before stopping."
                    ),
                }
            )


if __name__ == "__main__":
    main()
