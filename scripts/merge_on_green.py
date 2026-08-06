#!/usr/bin/env python3
"""Squash-merge pull requests labeled `merge-on-green` once their checks conclude.

WHY THIS EXISTS (operator ruling 2026-07-28, "can you actually fix this").
The merge-on-CONCLUDED-checks law is correct — a pending check is not a pass, and
an `--admin` merge mid-flight used to cancel the PR's own proof run (#3867) — but
it turned every session into a CI hostage, holding its turn 20-60 minutes purely
to watch packs it cannot influence.

Every GitHub-native fix is structurally unavailable on this account:

  * A user-account ruleset cannot grant the github-actions app a bypass (422,
    organization-only), so the lanes cannot be exempted from a rule.
  * ANY required-status-check rule — ruleset or classic branch protection — would
    also block the render/nightly lanes' direct `GITHUB_TOKEN` pushes to main,
    breaking the deploy path to fix the merge path.
  * `gh pr merge --auto --squash` is not a wait at all: with no branch protection
    there are no required checks to gate on, so auto-merge merges IMMEDIATELY
    (verified PR #3889, 2026-07-28 — merged ~1 min after arming, packs pending).

So the release valve is account-side: a session arms its PR with the
`merge-on-green` label and stops; this sweeper wakes when `ci`, `fences`, or the
source-main `integration-baseline` concludes, with a ten-minute cron retained as
a recovery net. It performs the merge the session would otherwise have sat there
waiting to perform. The discipline is unchanged — nothing merges until every
check has CONCLUDED clean — only the waiting moved off the session.

MAIN-RED CIRCUIT BREAKER. PR checks prove a head against the base GitHub gave it;
they do not prove that the rapidly moving source main remains healthy after later
merges. `integration-baseline.yml` publishes one fast verdict for each source or
control-plane descendant on main. This sweeper reads the latest run before it
looks at PRs. Pending, red, missing, or non-ancestral baseline evidence pauses
ordinary merges. Exactly one explicitly labelled `main-red-repair` PR may be
considered per sweep, and it still needs every one of its own checks green. That
is the escape hatch which prevents a circuit breaker from deadlocking its repair.

TOKENS. Reads use `READ_TOKEN` (in Actions the job's own `GITHUB_TOKEN`, whose
per-repository quota is separate from the shared account pool that
`ship_loop_guard.py` and every parallel session draw on — a 10-minute sweep must
not spend the budget those depend on). Writes use `MERGE_TOKEN`, an
`ADMIN_GH_TOKEN` PAT when present, because a merge performed with `GITHUB_TOKEN`
does not fire push-triggered workflows: render.yml would never see the sweeper's
merge. On the `GITHUB_TOKEN` fallback the merge still lands and the VPS's 3-minute
pull plus the nightly `scope=all` re-render still deliver it — degraded, not
broken.

STALE BASES. A clean head whose merge GitHub refuses is not automatically a
human's problem. main takes ~19 commits in 3 hours here while a pack run takes
~30 minutes, so a pull request routinely goes green and is stale before its own
proof finishes. That used to end at `merge-blocked`, waiting for someone to
rebase by hand — which is how a one-hour-old pull request becomes a three-day-old
one. The sweeper now asks GitHub to merge main into the head itself
(`update-branch`); if GitHub declines, the conflict is real and the label is
applied exactly as before. The merge gate is unchanged: an updated head is
UNPROVEN until its fresh checks conclude, and a later sweep judges it on those.

CONCURRENT SWEEPS ARE ALLOWED (2026-08-06). The workflow no longer serialises
this lane. The old `concurrency: {group: merge-on-green, cancel-in-progress:
false}` did not serialise WORK — it serialised the wait for a GitHub-hosted
runner, which is 25-107 minutes here because `ci` and `fences` saturate the same
pool, while the sweep itself takes 46 seconds. GitHub keeps one pending run per
group and cancels it on each new arrival, so with triggers every 50 s the lane
managed 0 successful sweeps in 100 consecutive runs. The full measurement is in
.github/workflows/merge-on-green.yml.

Overlap is safe because this is a LEVEL-TRIGGERED RECONCILER: every run re-lists
the labeled pull requests and re-derives every verdict from GitHub's live state,
and no state is carried between runs. Losing a wake-up therefore costs nothing so
long as some sweep runs; running two at once costs a few duplicate reads. The one
genuine race — a losing sweep reading "another sweep already merged this" as a
conflict and labelling a merged PR `merge-blocked` — is guarded by
`already_settled`, which is called before any 405/409 is allowed to mean conflict.

Individual pull-request outcomes are ANNOTATIONS, never job failures: one PR with
a red check must not fail a sweep that also had clean PRs to merge. The process
exits non-zero only when the sweep itself could not run.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GITHUB_API = "https://api.github.com"
MERGE_ON_GREEN_LABEL = "merge-on-green"
MERGE_BLOCKED_LABEL = "merge-blocked"
MAIN_RED_REPAIR_LABEL = "main-red-repair"
BASELINE_WORKFLOW = "integration-baseline.yml"
# The conclusions that count as "this check did not fail". `neutral` and
# `skipped` are the shapes a path-filtered or deliberately-inert job publishes.
CLEAN_CONCLUSIONS = {"success", "neutral", "skipped"}
# `_head_check_runs`' cap in .claude/hooks/ship_loop_guard.py, for the same
# fail-closed reason: PR #3629's head carried 101 check runs, so a single
# `per_page=100` call hid the tail and a red past page one went unseen.
CHECK_RUN_PAGE_CAP = 5
REQUEST_TIMEOUT_SECONDS = 30


def _annotate(level: str, title: str, message: str) -> None:
    """Emit a GitHub Actions annotation.

    House law (CI-guarded by tests/test_gh_annotation_line_start.py): the `::`
    token must START the line, so this is a bare `print` with `flush=True` and
    never a logger call — every logger here prefixes the level, which turns
    `::warning ...` into `WARNING ::warning ...` and GitHub silently drops it.
    `flush` is load-bearing because stdout is block-buffered when piped in CI.
    """
    print(f"::{level} title={title}::{message}", flush=True)


def _request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """One GitHub API call, returning (status, parsed body) instead of raising.

    A 405/409 from the merge endpoint is a ROUTINE outcome (conflict, dirty,
    not mergeable) that this sweeper must classify rather than crash on, so HTTP
    errors are returned like any other status. A body that is empty or not JSON
    parses to None; callers key on the status.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "macro-dashboard-merge-on-green",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
            return int(response.status), (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            parsed = None
        return int(exc.code), parsed


def is_spurious_check(name: str) -> bool:
    """The known-spurious Cloudflare check this repo has always ignored.

    Matched on both tokens rather than an exact string so a renamed variant of
    the same app's context keeps being excluded.
    """
    lowered = name.lower()
    return "workers builds" in lowered and "macro" in lowered


def label_names(pull: dict[str, Any]) -> set[str]:
    return {str((label or {}).get("name") or "") for label in (pull.get("labels") or [])}


def decide_verdict(runs: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """The whole merge decision, as a pure function over a head's check runs.

    Returns ``(verdict, names)``:

      ``unproven`` — the head carries NO non-spurious check runs. Never merged.
        A docs-only PR that matched no `paths:` filter is genuinely unproven, and
        a head whose only run is the spurious Cloudflare X is the same thing
        wearing a check. (The literal "zero check runs" rule would merge that
        second shape, which is why the count is taken AFTER the spurious filter.)
      ``pending`` — something has not concluded. Wait for the next sweep; a
        pending check is not a pass, and labeling `merge-blocked` now would be
        premature and would burn the one-shot comment on a race.
      ``blocked`` — everything concluded and at least one non-spurious check is a
        bad conclusion. Names the offenders for the comment.
      ``clean`` — every non-spurious check concluded in CLEAN_CONCLUSIONS.

    Pending OUTRANKS blocked here, which is deliberate and is the one place this
    differs from the ship-loop guard's own labeled-handoff verdict. This function
    gates an IRREVERSIBLE, noisy action (merge, or label + comment), so it waits
    for full information; the guard gates only a message to a session that can
    act on a red immediately, so there red outranks pending.
    """
    considered = [run for run in runs if not is_spurious_check(str(run.get("name") or ""))]
    if not considered:
        return "unproven", []
    pending = [
        str(run.get("name") or "unnamed check")
        for run in considered
        if run.get("status") != "completed"
    ]
    if pending:
        return "pending", pending
    bad = [
        f"{run.get('name') or 'unnamed check'} ({run.get('conclusion')})"
        for run in considered
        if run.get("conclusion") not in CLEAN_CONCLUSIONS
    ]
    if bad:
        return "blocked", bad
    return "clean", []


def head_check_runs(repo: str, head_sha: str, token: str) -> list[dict[str, Any]]:
    """Every check run on ``head_sha``, paginated to the end (fail-closed).

    Mirrors the guard's `_head_check_runs`: a short page means nothing is left, a
    full page keeps paging, and the 5-page cap bounds a pathological head. Under-
    reading here could only hide a red, so the cap is generous.
    """
    runs: list[dict[str, Any]] = []
    for page in range(1, CHECK_RUN_PAGE_CAP + 1):
        query = urllib.parse.urlencode({"per_page": "100", "page": str(page)})
        status, payload = _request(
            "GET", f"{GITHUB_API}/repos/{repo}/commits/{head_sha}/check-runs?{query}", token
        )
        if status >= 400 or not isinstance(payload, dict):
            raise RuntimeError(f"check-run listing failed: HTTP {status}")
        batch = payload.get("check_runs") or []
        runs.extend(batch)
        total = int(payload.get("total_count") or 0)
        if len(batch) < 100 or (total and len(runs) >= total):
            break
    return runs


def labeled_pulls(repo: str, token: str) -> list[dict[str, Any]]:
    """Open pull requests carrying `merge-on-green`.

    One listing call, filtered client-side: the pulls endpoint has no label
    parameter, and the issues-search alternative costs a separate quota pool.
    """
    query = urllib.parse.urlencode({"state": "open", "per_page": "100"})
    status, payload = _request("GET", f"{GITHUB_API}/repos/{repo}/pulls?{query}", token)
    if status >= 400 or not isinstance(payload, list):
        raise RuntimeError(f"pull-request listing failed: HTTP {status}")
    return [pull for pull in payload if MERGE_ON_GREEN_LABEL in label_names(pull)]


def integration_baseline_state(repo: str, token: str) -> tuple[str, str]:
    """Return ``(state, detail)`` for the newest source-main baseline proof.

    States are ``green``, ``pending``, ``red``, or ``unproven``. Only ``green``
    admits ordinary pull requests. The latest run's SHA must be an ancestor of
    current main: a successful proof from an abandoned history is not evidence.

    Data/site-only commits intentionally do not trigger the baseline workflow.
    Their current-main descendants therefore accept the latest source proof when
    GitHub's compare endpoint confirms ancestry.

    A ``cancelled`` newest run is SKIPPED, not read as red. `integration-baseline.yml`
    runs under `concurrency: integration-baseline-main` with `cancel-in-progress: true`,
    so any push to main that lands while a baseline is in flight cancels it — a routine
    event on a branch this repo pushes to every few minutes, and NOT evidence that main
    is broken. Reading `per_page=1` and treating `cancelled` as a non-clean conclusion
    latched this breaker red for 8.5h on 2026-08-05 (run 31014967682, cancelled 14:23Z)
    and held 49 armed PRs behind it until a baseline was dispatched by hand. The walk
    below falls through superseded runs to the newest one that actually CONCLUDED, and
    still fails closed: a genuine `failure`/`timed_out` stops the walk and returns red,
    and an all-cancelled window returns ``unproven`` rather than green.
    """
    workflow = urllib.parse.quote(BASELINE_WORKFLOW, safe="")
    query = urllib.parse.urlencode({"branch": "main", "per_page": "20"})
    status, payload = _request(
        "GET",
        f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/runs?{query}",
        token,
    )
    if status >= 400 or not isinstance(payload, dict):
        raise RuntimeError(f"integration-baseline listing failed: HTTP {status}")
    runs = payload.get("workflow_runs") or []
    if not runs:
        return "unproven", "integration-baseline has not published a run"

    # An in-flight newest run is genuinely pending; older ones cannot overrule it.
    if str(runs[0].get("status") or "").lower() != "completed":
        head = runs[0]
        return "pending", (
            f"{str(head.get('head_sha') or '')[:12] or 'unknown-sha'} "
            f"{str(head.get('html_url') or '')}"
        ).strip()

    run = next(
        (
            candidate
            for candidate in runs
            if str(candidate.get("status") or "").lower() == "completed"
            and str(candidate.get("conclusion") or "").lower() != "cancelled"
        ),
        None,
    )
    if run is None:
        return "unproven", (
            f"the last {len(runs)} integration-baseline runs were all cancelled "
            "(superseded by concurrency); none concluded"
        )
    run_status = str(run.get("status") or "").lower()
    conclusion = str(run.get("conclusion") or "").lower()
    run_sha = str(run.get("head_sha") or "")
    run_url = str(run.get("html_url") or "")
    detail = f"{run_sha[:12] or 'unknown-sha'} {run_url}".strip()
    if run_status != "completed":
        return "pending", detail

    ref_status, ref_payload = _request(
        "GET", f"{GITHUB_API}/repos/{repo}/git/ref/heads/main", token
    )
    if ref_status >= 400 or not isinstance(ref_payload, dict):
        raise RuntimeError(f"main ref lookup failed: HTTP {ref_status}")
    main_sha = str(((ref_payload.get("object") or {}).get("sha")) or "")
    if not run_sha or not main_sha:
        return "unproven", f"baseline/main SHA missing ({detail})"

    if run_sha != main_sha:
        compare_status, compare_payload = _request(
            "GET", f"{GITHUB_API}/repos/{repo}/compare/{run_sha}...{main_sha}", token
        )
        relation = str((compare_payload or {}).get("status") or "")
        if compare_status >= 400 or relation not in {"ahead", "identical"}:
            return "unproven", (
                f"baseline {run_sha[:12]} is not proven ancestral to main "
                f"{main_sha[:12]} (HTTP {compare_status}, {relation or 'unknown'})"
            )

    if conclusion in CLEAN_CONCLUSIONS:
        return "green", detail
    return "red", f"{conclusion or 'missing conclusion'} at {detail}"


def mark_blocked(repo: str, pull: dict[str, Any], message: str, token: str) -> bool:
    """Add `merge-blocked` and explain it — but only on the transition.

    The comment is posted ONLY in the same call path that actually ADDS the
    label. A sweep runs every 10 minutes, so commenting on every pass over an
    already-blocked pull request would post ~144 comments a day.
    """
    number = pull.get("number")
    if MERGE_BLOCKED_LABEL in label_names(pull):
        return False
    status, _ = _request(
        "POST",
        f"{GITHUB_API}/repos/{repo}/issues/{number}/labels",
        token,
        {"labels": [MERGE_BLOCKED_LABEL]},
    )
    if status >= 400:
        _annotate("warning", "merge-on-green", f"PR #{number}: could not label (HTTP {status}).")
        return False
    _request(
        "POST",
        f"{GITHUB_API}/repos/{repo}/issues/{number}/comments",
        token,
        {"body": message},
    )
    return True


def clear_blocked(repo: str, pull: dict[str, Any], token: str) -> None:
    """Drop a stale `merge-blocked` after a successful merge. Best-effort."""
    if MERGE_BLOCKED_LABEL not in label_names(pull):
        return
    label = urllib.parse.quote(MERGE_BLOCKED_LABEL)
    _request(
        "DELETE",
        f"{GITHUB_API}/repos/{repo}/issues/{pull.get('number')}/labels/{label}",
        token,
    )


def delete_head_ref(repo: str, pull: dict[str, Any], token: str) -> None:
    """Tidy the merged branch. Best-effort — a surviving branch is harmless."""
    ref = str((pull.get("head") or {}).get("ref") or "")
    if not ref:
        return
    _request(
        "DELETE",
        f"{GITHUB_API}/repos/{repo}/git/refs/heads/{urllib.parse.quote(ref)}",
        token,
    )


def already_settled(repo: str, number: Any, token: str) -> tuple[bool, str]:
    """Did this pull request already merge (or close) out from under this sweep?

    WHY (2026-08-06). Sweeps may now overlap. The workflow-level `concurrency`
    group that used to serialise them was removed because it did not serialise
    work — it serialised a multi-hour wait for a GitHub-hosted runner, and killed
    98 of 100 consecutive sweeps in the pending slot while doing it (see the
    postmortem in .github/workflows/merge-on-green.yml).

    Overlapping sweeps are safe by construction almost everywhere: this script is
    a level-triggered reconciler that re-reads every labeled pull request and
    re-derives every verdict from GitHub's live state, carrying nothing across
    runs. Re-reading a check twice costs a call and changes nothing; two sweeps
    racing the same squash merge cannot double-merge, because GitHub answers the
    loser 405/409.

    There is exactly ONE unsafe spot, and it is this one. `sweep_pull` reads a
    405/409 as "the base moved or the branch conflicts", tries `update-branch`,
    and on refusal applies `merge-blocked` plus a one-shot comment saying *not
    merging*. Against a pull request another sweep merged one second earlier,
    every one of those steps is wrong: update-branch answers 422 on a merged PR,
    so the loser would label a SUCCESSFULLY MERGED pull request `merge-blocked`
    and comment a falsehood on it — and because `mark_blocked` fires its comment
    only on the label transition, that lie is the one that sticks.

    So before a refused merge is allowed to mean "conflict", ask GitHub what the
    pull request actually is now.

    FAILS CLOSED. An unreadable answer returns ``(False, "")``, which falls
    through to the pre-existing update-branch/label path. That is noisier but it
    is exactly the behaviour that shipped before this guard existed, so a broken
    read can never cause a merge or suppress a genuine conflict report.
    """
    status, payload = _request("GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}", token)
    if status >= 400 or not isinstance(payload, dict):
        return False, ""
    if payload.get("merged") is True:
        return True, "merged"
    if str(payload.get("state") or "").lower() == "closed":
        return True, "closed"
    return False, ""


def update_branch(repo: str, pull: dict[str, Any], token: str) -> bool:
    """Merge `main` into a clean-but-stale head. True when GitHub accepted it.

    ONLY reached for a pull request whose every check already concluded clean and
    whose merge GitHub then refused. The refusal splits two ways and only one of
    them is a human's problem:

      * the base moved under us — the head is fine, it is simply no longer merge-
        able against the newer main. GitHub can fast-forward that itself, and the
        resulting head re-runs CI before anything merges.
      * a real content conflict — update-branch answers 422 and the caller falls
        through to `merge-blocked`, exactly as before.

    This is the fix for the observed failure mode: main takes ~19 commits in 3
    hours while a pack run takes ~30 minutes, so a pull request can go green and
    be stale before its own proof finishes. Every such head then waits for a human
    to rebase it by hand, which is how a one-hour-old pull request becomes a
    three-day-old one. Nothing here weakens the merge gate — an updated head is
    unproven until its fresh checks conclude, and the next sweep judges it on
    those.
    """
    number = pull.get("number")
    status, body = _request(
        "PUT",
        f"{GITHUB_API}/repos/{repo}/pulls/{number}/update-branch",
        token,
        {"expected_head_sha": str((pull.get("head") or {}).get("sha") or "")},
    )
    if status in {200, 202}:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: checks were clean but the base had moved — merged main "
            "into the head. Its fresh checks decide the merge on a later sweep.",
        )
        return True
    detail = str((body or {}).get("message") or f"HTTP {status}")
    print(
        f"PR #{number}: update-branch declined ({detail}) — treating as a real conflict.",
        flush=True,
    )
    return False


def sweep_pull(
    repo: str, pull: dict[str, Any], read_token: str, merge_token: str
) -> str:
    """Judge and, when clean, merge one labeled pull request. Returns the verdict."""
    number = pull.get("number")
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    if not head_sha:
        _annotate("warning", "merge-on-green", f"PR #{number}: no head sha; skipped.")
        return "unproven"

    runs = head_check_runs(repo, head_sha, read_token)
    verdict, names = decide_verdict(runs)

    if verdict == "pending":
        print(
            f"PR #{number}: {len(names)} check(s) still running "
            f"({', '.join(names[:6])}) — waiting for the next sweep.",
            flush=True,
        )
        return verdict

    if verdict == "unproven":
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: head {head_sha[:12]} carries no non-spurious check runs, so "
            "nothing proves it — the sweeper will never merge it. Merge it manually once "
            "you are satisfied, or push a change that triggers CI.",
        )
        return verdict

    if verdict == "blocked":
        added = mark_blocked(
            repo,
            pull,
            (
                "`merge-on-green` sweeper: **not merging.** These checks concluded "
                "red on the head commit:\n\n"
                + "\n".join(f"- `{name}`" for name in names)
                + "\n\nThe sweeper never merges a red pull request. Fix the cause and "
                "re-run the failed job (the label stays armed, so the next sweep merges "
                "once the head is clean), or remove `merge-on-green` to take it manual. "
                "The known-spurious `Workers Builds: macro` check is already ignored."
            ),
            merge_token,
        )
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: red checks ({', '.join(names[:6])}); "
            + ("labeled merge-blocked." if added else "already labeled merge-blocked."),
        )
        return verdict

    status, body = _request(
        "PUT",
        f"{GITHUB_API}/repos/{repo}/pulls/{number}/merge",
        merge_token,
        {"merge_method": "squash"},
    )
    if status == 200:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: every check concluded clean — squash-merged "
            f"({str((body or {}).get('sha') or '')[:12]}).",
        )
        clear_blocked(repo, pull, merge_token)
        delete_head_ref(repo, pull, merge_token)
        return "merged"

    if status in {405, 409}:
        # GitHub's "not mergeable" pair: 405 for a blocked/dirty merge, 409 for a
        # base that moved under us. Only the second is genuinely a human's
        # problem-free case, so try to clear it before reaching for a label.
        detail = str((body or {}).get("message") or f"HTTP {status}")
        # ...but a THIRD shape produces the same 405/409 now that sweeps overlap:
        # another sweep merged this pull request between our check read and our
        # merge call. Treating that as a conflict would label a merged PR
        # `merge-blocked` and comment a falsehood on it. Ask before accusing.
        settled, how = already_settled(repo, number, read_token)
        if settled:
            _annotate(
                "notice",
                "merge-on-green",
                f"PR #{number}: already {how} by the time this sweep called merge — "
                "a concurrent sweep won the race. Nothing to do, nothing labeled.",
            )
            return f"already-{how}"
        if update_branch(repo, pull, merge_token):
            # The head now carries main. It is UNPROVEN until its fresh checks
            # conclude, so nothing merges on this pass and the label stays armed
            # for the sweep that judges those checks. Any stale `merge-blocked`
            # from an earlier pass is cleared: the branch is moving again.
            clear_blocked(repo, pull, merge_token)
            return "updated"
        mark_blocked(
            repo,
            pull,
            (
                "`merge-on-green` sweeper: **not merging.** Every check was clean, but "
                f"GitHub refused the squash merge: _{detail}_\n\n"
                "The sweeper then tried to merge `main` into this branch itself and "
                "GitHub declined that too, which means a REAL content conflict rather "
                "than a stale base. Resolve it by hand and the next sweep will pick it "
                "up (the label stays armed)."
            ),
            merge_token,
        )
        _annotate("warning", "merge-on-green", f"PR #{number}: merge refused — {detail}")
        return "conflict"

    _annotate(
        "warning",
        "merge-on-green",
        f"PR #{number}: merge call failed with HTTP {status}; leaving it armed for the "
        "next sweep.",
    )
    return "error"


def main() -> int:
    repo = os.environ.get("GH_REPO", "").strip()
    read_token = os.environ.get("READ_TOKEN", "").strip()
    # The PAT is what makes a sweeper merge fire push-triggered workflows; the
    # job token is a working fallback (see the module docstring).
    merge_token = os.environ.get("MERGE_TOKEN", "").strip() or read_token
    if not repo:
        _annotate("error", "merge-on-green", "GH_REPO is not set; nothing to sweep.")
        return 1

    try:
        pulls = labeled_pulls(repo, read_token)
    except Exception as exc:
        _annotate("error", "merge-on-green", f"Could not list pull requests: {exc}")
        return 1

    if not pulls:
        print(f"No open pull requests labeled {MERGE_ON_GREEN_LABEL}.", flush=True)
        return 0

    try:
        baseline_state, baseline_detail = integration_baseline_state(repo, read_token)
    except Exception as exc:
        # Fail closed. An unavailable circuit breaker must never silently become
        # permission to merge; the schedule/workflow_run recovery will retry.
        _annotate(
            "error",
            "merge-on-green",
            f"Could not establish integration-baseline state: {exc}; no PRs swept.",
        )
        return 1

    if baseline_state != "green":
        _annotate(
            "warning",
            "main-red circuit breaker",
            f"integration-baseline is {baseline_state} ({baseline_detail}). Ordinary "
            f"merges are paused; one `{MAIN_RED_REPAIR_LABEL}` PR may be considered.",
        )

    tally: dict[str, int] = {}
    repair_slot_used = False
    for pull in pulls:
        if baseline_state != "green":
            is_repair = MAIN_RED_REPAIR_LABEL in label_names(pull)
            if not is_repair or repair_slot_used:
                number = pull.get("number")
                print(
                    f"PR #{number}: source main baseline is {baseline_state}; "
                    "leaving it armed behind the circuit breaker.",
                    flush=True,
                )
                verdict = "baseline-blocked"
                tally[verdict] = tally.get(verdict, 0) + 1
                continue
            # At most one repair candidate per pass. Even two individually green
            # repairs have not been jointly proven against the broken baseline.
            repair_slot_used = True
        try:
            verdict = sweep_pull(repo, pull, read_token, merge_token)
        except Exception as exc:
            # One bad pull request must never fail a sweep that had clean work to
            # do. The next run retries it; the label is still armed.
            _annotate(
                "warning",
                "merge-on-green",
                f"PR #{pull.get('number')}: sweep failed ({exc}); retrying next run.",
            )
            verdict = "error"
        tally[verdict] = tally.get(verdict, 0) + 1

    print(
        "merge-on-green sweep complete: "
        + ", ".join(f"{count} {verdict}" for verdict, count in sorted(tally.items())),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
