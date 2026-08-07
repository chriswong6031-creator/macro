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

A GREEN CAN GO STALE WITHOUT GOING RED (operator ruling 2026-08-06). Everything
above judges a head's checks. Nothing above asked WHEN they were computed, and a
check proves the head against the base it was handed, not against the base that
exists at merge time. PR #4583 is the worked example:

    07:42Z  #4583's head is pushed; its `ci` run starts and concludes success
    10:26Z  #4607 merges tests/test_us_reclaim_veto_packet.py onto main — a guard
            that pins a copy of the CT_BOTH_FAIL / CT_RECLAIM_FAIL constants
    22:51Z  #4583 merges on the 07:42 green, ~15 hours old and never re-run

The green was HONEST. That guard did not exist in the tree the 07:42 run tested.
#4583 changed those constants, main went red, and 18 open pull requests inherited
a `ci-pack-1` failure until #4645 repaired it.

CORRECTION, because the record is wrong where someone will look for it: #4645's
commit message attributes this to a ci.yml path-filter gap. It was not one. At
#4583's OWN merge commit (9aca28d248c) `engine/signal_quality.py` was covered
TWICE in `on.pull_request.paths` — explicitly at line 169 and again by `engine/**`
at line 312. Every path filter was correct; the proof was simply old. Widening
`paths` would have changed nothing, which is precisely why the fix has to be about
TIME, not coverage.

So before an otherwise-clean pull request is merged, `ProofFreshness` asks whether
main has taken a commit, since that proof was computed, inside the PR's TESTED
SURFACE. If it has, nothing merges: the head is handed to `update-branch` and its
fresh checks decide on a later sweep. If it has not, the existing green still
means what it said. That is the operator's chosen option — NOT strict
up-to-date-with-main, which would serialise a 60-PR queue into days.

Individual pull-request outcomes are ANNOTATIONS, never job failures: one PR with
a red check must not fail a sweep that also had clean PRs to merge. The process
exits non-zero only when the sweep itself could not run.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:  # imported as `scripts.merge_on_green` (the test pack, and any other caller)
    from scripts.gh_path_filter import NEGATION_PREFIX, matching_patterns
except ImportError:  # run as `python3 scripts/merge_on_green.py` (the workflow step)
    from gh_path_filter import NEGATION_PREFIX, matching_patterns  # type: ignore[no-redef]

GITHUB_API = "https://api.github.com"
MERGE_ON_GREEN_LABEL = "merge-on-green"
MERGE_BLOCKED_LABEL = "merge-blocked"
MAIN_RED_REPAIR_LABEL = "main-red-repair"
BASELINE_WORKFLOW = "integration-baseline.yml"
WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
# The conclusions that count as "this check did not fail". `neutral` and
# `skipped` are the shapes a path-filtered or deliberately-inert job publishes.
CLEAN_CONCLUSIONS = {"success", "neutral", "skipped"}
# `_head_check_runs`' cap in .claude/hooks/ship_loop_guard.py, for the same
# fail-closed reason: PR #3629's head carried 101 check runs, so a single
# `per_page=100` call hid the tail and a red past page one went unseen.
CHECK_RUN_PAGE_CAP = 5
REQUEST_TIMEOUT_SECONDS = 30

# --- the tested-surface gate --------------------------------------------------
#
# Trees that DEFINE what "proven" means. A main commit touching one of them has
# changed the jobs, the packs, or the path filters themselves, so no pull request's
# existing green still describes the checks that would run now. Always re-prove,
# whatever the PR's own footprint is.
CI_DEFINITION_TREES = (".github/workflows/", ".github/ci/")
# Trees this repository's OWN lanes rewrite on main, continuously, without a human
# editing anything: render.yml bakes `site/` out of `templates/`, and the nightly is
# the sole advancer of the `data/` ledgers (house law). A main commit whose ENTIRE
# file set lies inside them is a bake, not an edit, and cannot invalidate a proof —
# the render lane re-derives `site/` from source after the merge regardless, and a
# nightly artifact that genuinely breaks main is caught by `integration-baseline`,
# the circuit breaker this same sweep already reads before any merge. So the risk is
# handed to an existing independent gate, not dropped.
#
# This exclusion is LOAD-BEARING, and here is the measurement that makes it so
# (400 main commits, 32.8 h, 2026-08-06). 330 of the 400 — 82% — are pure bakes.
# Counting them puts a surface-touching commit inside 96% of 35-minute windows,
# which is strict up-to-date-with-main wearing a filter, and it livelocks outright
# any pull request that touches `site/` itself: 18-26 expected re-prove cycles,
# i.e. it would never merge. Excluding them, the WORST pull request in that window
# needs ~2.9 cycles and the median ~1.5.
#
# It is deliberately CONJUNCTIVE and commit-level: one source file anywhere in the
# commit and the whole commit is judged normally. This is a classifier for "was
# this a pipeline bake", never a hole punched in the surface itself.
PIPELINE_TREES = ("data/", "site/")
# One listing call per sweep buys this many of main's newest commits (~8 h at the
# measured 12 commits/h). A proof older than the window cannot be judged, so it is
# re-proven — which is the right answer for a 15-hour-old green anyway (#4583).
MAIN_TIMELINE_PAGE = 100
# Per-commit file listings are fetched once per SHA and shared by every pull request
# in the sweep, so this caps the sweep, not the PR count. A pull request needing more
# than this many commits classified is re-proven without spending any of them.
MAIN_COMMIT_FILE_CAP = 50
# GitHub truncates a commit's `files` array at 300. A truncated list could hide the
# one source file that makes a commit not-a-bake, so a truncated commit is treated as
# touching everything.
COMMIT_FILES_TRUNCATED_AT = 300
# `/pulls/{n}/files` pages, 100 each. A pull request bigger than this has a footprint
# we cannot fully see, and an UNDER-read footprint under-detects, so it is re-proven.
PR_FILE_PAGE_CAP = 3
# A check run's `started_at` is when its JOB started, not when the run was created —
# and the base a run tests is fixed at CREATION. On this repository's saturated pool
# that gap has been measured at 25m38s (see .github/workflows/merge-on-green.yml), so
# the window is widened by this much before asking what main did. It is a partial
# cover, not a complete one: a job that queued longer than this can still leave a
# commit outside the window. Widening it further trades directly against churn.
PROOF_BASE_SKEW_SECONDS = 1800


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


# ── the tested-surface gate ──────────────────────────────────────────────────


def _parse_iso(value: Any) -> float | None:
    """GitHub's `2026-08-05T07:42:13Z` as an epoch float. None when unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def load_pr_gates(workflows_dir: Path = WORKFLOWS_DIR) -> list[dict[str, Any]]:
    """Every `on.pull_request` workflow and the `paths:` filter it declares.

    ``patterns is None`` means the workflow declares no filter and starts on every
    pull request — it therefore says NOTHING about which files affect its verdict,
    and contributes no entries to any surface. Reading that silence as "everything"
    is the strict option the operator rejected; reading it as "nothing" is what the
    ruling asks for ("the `paths` entries that select the PR's jobs").

    RAISES, and the caller aborts the sweep, when:

      * the directory is missing or holds no `on.pull_request` workflow — the most
        likely cause is a sparse-checkout that stopped fetching it, and a surface
        derived from nothing is the no-op-that-reviews-as-protection this gate
        exists to avoid;
      * no PR-triggered workflow declares a `paths:` filter at all — same reason;
      * a filter contains a `!` negation, which `gh_path_filter` does not model.
        Refusing loudly beats mis-evaluating a surface nobody re-derived.
    """
    try:
        import yaml  # local: the sweeper is the only caller and it installs it
    except ImportError as exc:  # pragma: no cover - environment, not logic
        raise RuntimeError(f"PyYAML is unavailable, so no path filter can be read: {exc}")

    if not workflows_dir.is_dir():
        raise RuntimeError(f"{workflows_dir} is not a directory (sparse-checkout?)")

    gates: list[dict[str, Any]] = []
    for path in sorted(workflows_dir.glob("*.yml")):
        try:
            payload = yaml.safe_load(path.read_text(errors="ignore"))
        except yaml.YAMLError:
            continue
        if not isinstance(payload, dict):
            continue
        # PyYAML resolves the bare key `on:` to the boolean True (YAML 1.1).
        block = payload[True] if True in payload else payload.get("on")
        if not isinstance(block, dict) or "pull_request" not in block:
            continue
        trigger = block.get("pull_request")
        patterns = None
        if isinstance(trigger, dict) and isinstance(trigger.get("paths"), list):
            patterns = [str(entry) for entry in trigger["paths"]]
            negated = [entry for entry in patterns if entry.startswith(NEGATION_PREFIX)]
            if negated:
                raise RuntimeError(
                    f"{path.name} uses `!` negation in on.pull_request.paths "
                    f"({negated[0]}), which the shared matcher does not model"
                )
        gates.append({"workflow": path.name, "patterns": patterns})

    if not gates:
        raise RuntimeError(f"no on.pull_request workflow found under {workflows_dir}")
    if not any(gate["patterns"] is not None for gate in gates):
        raise RuntimeError(
            f"no PR-triggered workflow under {workflows_dir} declares a paths filter"
        )
    return gates


class ProofFreshness:
    """Per-sweep answer to: has main moved under this pull request's proof?

    Built ONCE per sweep and shared by every pull request, which is the whole cost
    story. The main timeline is one listing call; each commit's file list is fetched
    at most once per sweep no matter how many pull requests consult it; and a pull
    request's own file list is read only when the window actually contains a
    candidate, which the 82%-are-bakes measurement makes the common case.

    EVERY answer this class cannot compute is ``True`` — re-prove. A surface that
    silently resolves to "nothing changed" would turn the gate into a no-op that
    reviews as protection, which is the single worst outcome available here.
    """

    def __init__(
        self,
        repo: str,
        token: str,
        gates: list[dict[str, Any]],
        commits: list[dict[str, Any]],
    ) -> None:
        self.repo = repo
        self.token = token
        self.gates = gates
        # Newest first, as GitHub returns them.
        self.commits = commits
        self._commit_files: dict[str, tuple[list[str], bool]] = {}
        self._pr_files: dict[Any, list[str] | None] = {}
        self.commit_file_reads = 0

    # -- construction ---------------------------------------------------------

    @classmethod
    def build(
        cls,
        repo: str,
        token: str,
        workflows_dir: Path = WORKFLOWS_DIR,
    ) -> "ProofFreshness":
        """Load the gates and main's recent history. Raises; the caller aborts."""
        gates = load_pr_gates(workflows_dir)
        query = urllib.parse.urlencode(
            {"sha": "main", "per_page": str(MAIN_TIMELINE_PAGE)}
        )
        status, payload = _request(
            "GET", f"{GITHUB_API}/repos/{repo}/commits?{query}", token
        )
        if status >= 400 or not isinstance(payload, list):
            raise RuntimeError(f"main commit listing failed: HTTP {status}")
        commits: list[dict[str, Any]] = []
        for entry in payload:
            sha = str((entry or {}).get("sha") or "")
            committer = ((entry or {}).get("commit") or {}).get("committer") or {}
            when = _parse_iso(committer.get("date"))
            if not sha or when is None:
                raise RuntimeError(f"main commit {sha[:12] or '?'} has no usable date")
            commits.append({"sha": sha, "when": when})
        if not commits:
            # Unreachable against a real repository, and permitting it would hand
            # the gate a free "main never moved" for every pull request.
            raise RuntimeError("main commit listing came back empty")
        return cls(repo, token, gates, commits)

    # -- reads ----------------------------------------------------------------

    def files_of(self, sha: str) -> tuple[list[str], bool]:
        """``(files, truncated)`` for one main commit. Cached for the whole sweep."""
        cached = self._commit_files.get(sha)
        if cached is not None:
            return cached
        status, payload = _request(
            "GET", f"{GITHUB_API}/repos/{self.repo}/commits/{sha}", self.token
        )
        self.commit_file_reads += 1
        if status >= 400 or not isinstance(payload, dict):
            raise RuntimeError(f"commit {sha[:12]} unreadable: HTTP {status}")
        files = [
            str((entry or {}).get("filename") or "") for entry in (payload.get("files") or [])
        ]
        answer = ([name for name in files if name], len(files) >= COMMIT_FILES_TRUNCATED_AT)
        self._commit_files[sha] = answer
        return answer

    def pull_files(self, number: Any) -> list[str] | None:
        """The pull request's own changed files, or None when they cannot be seen."""
        if number in self._pr_files:
            return self._pr_files[number]
        names: list[str] = []
        answer: list[str] | None = names
        for page in range(1, PR_FILE_PAGE_CAP + 1):
            query = urllib.parse.urlencode({"per_page": "100", "page": str(page)})
            status, payload = _request(
                "GET",
                f"{GITHUB_API}/repos/{self.repo}/pulls/{number}/files?{query}",
                self.token,
            )
            if status >= 400 or not isinstance(payload, list):
                answer = None
                break
            names.extend(str((entry or {}).get("filename") or "") for entry in payload)
            if len(payload) < 100:
                break
        else:
            # Every page was full: the footprint is truncated, and an UNDER-read
            # footprint under-detects. Not knowing is re-prove, never merge.
            answer = None
        self._pr_files[number] = answer
        return answer

    # -- the decision ---------------------------------------------------------

    def surface_of(self, number: Any) -> set[str] | None:
        """The `paths` entries this pull request's OWN files satisfy.

        A gate's entry is in the surface when some file the pull request changed
        matches it. That is what makes this the CHOSEN option rather than the
        rejected strict one: `site/**` is in the surface of a pull request that
        edits `site/`, and is not in the surface of one that does not.

        None means undeterminable — which includes the empty result. A pull request
        whose files satisfy no entry of any path-filtered gate has a surface that
        "silently resolves to the empty set", and merging on that would be the
        no-op this gate exists to prevent.
        """
        files = self.pull_files(number)
        if files is None:
            return None
        surface: set[str] = set()
        for gate in self.gates:
            for name in files:
                surface.update(matching_patterns(name, gate["patterns"]))
        return surface or None

    def proof_instant(self, runs: list[dict[str, Any]]) -> float | None:
        """When this head's proof was computed, as an epoch float.

        The OLDEST `started_at` across the non-spurious runs, not the newest. A
        proof is exactly as fresh as its stalest member: a single check re-run at
        T+5h does not re-date the hundred checks from T, and reading the newest
        would let one rerun launder an entire stale proof — the #4583 shape in
        miniature. `PROOF_BASE_SKEW_SECONDS` then covers the queue wait between the
        run's creation (which fixes the base it tests) and its first job starting.

        None when any considered run carries no usable timestamp: an unstamped
        proof cannot be dated, and an undatable proof is re-proven.
        """
        considered = [
            run for run in runs if not is_spurious_check(str(run.get("name") or ""))
        ]
        if not considered:
            return None
        stamps = [_parse_iso(run.get("started_at")) for run in considered]
        if any(stamp is None for stamp in stamps):
            return None
        return min(stamp for stamp in stamps if stamp is not None) - PROOF_BASE_SKEW_SECONDS

    def stale_for(
        self, pull: dict[str, Any], runs: list[dict[str, Any]]
    ) -> tuple[bool, str]:
        """``(must_reprove, reason)`` for one pull request whose checks are clean."""
        number = pull.get("number")
        when = self.proof_instant(runs)
        if when is None:
            return True, (
                "its checks carry no usable start time, so the proof cannot be dated"
            )

        window = [commit for commit in self.commits if commit["when"] > when]
        if not window:
            return False, "main has taken no commits since the proof was computed"
        if len(window) == len(self.commits) and len(self.commits) >= MAIN_TIMELINE_PAGE:
            return True, (
                f"the proof predates all {len(self.commits)} main commits this sweep "
                "can see, so what main did in between cannot be established"
            )
        if len(window) > MAIN_COMMIT_FILE_CAP:
            return True, (
                f"main has taken {len(window)} commits since the proof, more than the "
                f"{MAIN_COMMIT_FILE_CAP} this sweep will classify"
            )

        candidates: set[str] = set()
        for commit in window:
            try:
                files, truncated = self.files_of(commit["sha"])
            except RuntimeError as exc:
                return True, f"a main commit since the proof could not be read ({exc})"
            if truncated:
                return True, (
                    f"main commit {commit['sha'][:12]} changed too many files to list, "
                    "so it cannot be shown to be outside the surface"
                )
            if any(name.startswith(CI_DEFINITION_TREES) for name in files):
                return True, (
                    f"main commit {commit['sha'][:12]} changed the check definitions "
                    "themselves, so no existing green describes the checks that run now"
                )
            if files and all(name.startswith(PIPELINE_TREES) for name in files):
                continue  # a render/nightly bake, not an edit
            for name in files:
                for gate in self.gates:
                    candidates.update(matching_patterns(name, gate["patterns"]))

        if not candidates:
            return False, (
                f"main took {len(window)} commit(s) since the proof, none of them "
                "inside any gate's path filter"
            )

        surface = self.surface_of(number)
        if surface is None:
            return True, (
                "the pull request's own changed files could not be established, so "
                "its tested surface is unknown"
            )
        hit = sorted(candidates & surface)
        if hit:
            return True, (
                f"main touched {', '.join(hit[:4])} since the proof was computed — "
                "inside this pull request's tested surface"
            )
        return False, (
            f"main took {len(window)} commit(s) since the proof, none inside this "
            "pull request's tested surface"
        )


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


#: How far back along main to look for a commit that actually published checks.
#: Measured 2026-08-07 on the last 14 main commits: NINE carried no check runs at
#: all — `[skip ci]` press-wire ticks, earnings-wire publishes, research_vault
#: catalogs, whitehouse alert updates — and the tip had none either. The newest
#: commit with concluded packs sat 5 back. 20 clears that with room; a main whose
#: last 20 commits are all skip-ci is a main nothing has proved, and the walk
#: correctly returns an empty set there.
MAIN_PROOF_WALK = 20


def main_clean_check_names(repo: str, token: str) -> set[str]:
    """Non-spurious check names that concluded CLEAN on the newest PROVED main commit.

    Read ONCE per sweep and shared by every pull request, because it answers a
    question about main, not about any PR.

    NOT the tip. main's tip is usually a commit that never ran CI: this repo pushes
    `[skip ci]` wire ticks and research_vault catalogs to main every few minutes, and
    ci.yml is path-filtered on top of that. Reading the tip alone returned a set with
    no packs in it almost always, which would have left this whole mechanism inert —
    it would have looked like it worked while never firing. So walk newest->oldest and
    answer from the first commit that published ANY concluded non-spurious check, the
    same shape `integration_baseline_state` already uses for the breaker.

    This exists to tell two reds apart that look identical on a PR:

      * the PR broke something — its red is its own, and blocking is correct;
      * main was red when the PR last ran, the PR inherited that failure, and main
        has since been healed — the red describes a base that no longer exists.

    The second shape is what regenerates the armed backlog. Every time main goes
    red, every armed PR inherits it (measured 2026-08-07: ci-pack-2 red on 62 of
    100 armed PRs and ci-pack-3 on 62, both already healed on main by #4752 and
    #4767) — and `sweep_pull` used to return at `blocked` BEFORE reaching the
    staleness path, so nothing ever re-tested them. They sat until a human ran
    `update-branch` by hand, one at a time. The sweeper's own header records an
    earlier round of exactly this: "#4583 changed those constants, main went red,
    and 18 open pull requests inherited a ci-pack-1 failure until #4645 repaired
    it."

    Stops at the first PROVED commit and answers from that one alone — it does not
    union across commits. A union would let a check that passed four commits ago
    excuse a red the very next commit introduced.

    FAILS CLOSED at every exit: an unreadable main, a walk that finds no proved
    commit, or any exception all return an EMPTY set, and an empty set can never be
    a superset of a non-empty failing set, so the caller falls through to the
    unchanged `merge-blocked` path. Not knowing what main proves is never permission
    to refresh anything.
    """
    try:
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/commits?sha=main&per_page={MAIN_PROOF_WALK}",
            token,
        )
        if status >= 400 or not isinstance(payload, list):
            return set()
        for commit in payload:
            sha = str((commit or {}).get("sha") or "")
            if not sha:
                continue
            considered = [
                run
                for run in head_check_runs(repo, sha, token)
                if not is_spurious_check(str(run.get("name") or ""))
                and run.get("status") == "completed"
            ]
            if not considered:
                continue  # a skip-ci / path-filtered commit proves nothing either way
            return {
                str(run.get("name") or "")
                for run in considered
                if run.get("conclusion") in CLEAN_CONCLUSIONS
            }
    except Exception:  # noqa: BLE001 — a diagnostic must never fail a sweep
        return set()
    return set()


def failing_check_names(runs: list[dict[str, Any]]) -> set[str]:
    """Bare names of the non-spurious checks that concluded badly on a head.

    Derived from the runs rather than parsed back out of `decide_verdict`'s
    display strings, which carry a " (conclusion)" suffix — re-deriving keeps the
    comparison exact and independent of that formatting.
    """
    return {
        str(run.get("name") or "")
        for run in runs
        if not is_spurious_check(str(run.get("name") or ""))
        and run.get("status") == "completed"
        and run.get("conclusion") not in CLEAN_CONCLUSIONS
    }


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


def reprove(
    repo: str, pull: dict[str, Any], reason: str, read_token: str, merge_token: str
) -> str:
    """Refuse to merge a clean-but-stale proof; hand the head back to CI.

    `update-branch` is the sanctioned path and already exists: it merges main into
    the head, which makes the head UNPROVEN until its fresh checks conclude, and a
    later sweep judges it on those. Nothing about the merge gate is weakened here —
    this only stops a green from outliving the base it was computed against.

    When GitHub declines the update the head genuinely conflicts with main, which no
    number of sweeps will fix, so it is labeled and explained exactly once.

    …UNLESS another sweep merged it a second ago. Sweeps overlap by design, so two
    of them can both judge this pull request clean and stale; the loser's
    update-branch answers 422 because the pull request is MERGED, and labelling that
    `merge-blocked` with a one-shot "not merging" comment is #4647's hazard arriving
    through a new door. `already_settled` is asked before any accusation here for
    exactly the same reason it is asked on a refused merge.
    """
    number = pull.get("number")
    _annotate(
        "notice",
        "merge-on-green",
        f"PR #{number}: checks are clean but the proof is stale — {reason}. Merging "
        "main into the head; its fresh checks decide on a later sweep.",
    )
    if update_branch(repo, pull, merge_token):
        # The branch is moving again, so any `merge-blocked` from an earlier pass
        # has stopped being true.
        clear_blocked(repo, pull, merge_token)
        return "re-proving"
    settled, how = already_settled(repo, number, read_token)
    if settled:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: already {how} by the time this sweep tried to re-prove it "
            "— a concurrent sweep won the race. Nothing to do, nothing labeled.",
        )
        return f"already-{how}"
    mark_blocked(
        repo,
        pull,
        (
            "`merge-on-green` sweeper: **not merging.** Every check concluded clean, "
            f"but the proof is no longer trustworthy: {reason}.\n\n"
            "A check proves the head against the base it was handed, not against the "
            "base that exists at merge time — that is how PR #4583's honest 15-hour-old "
            "green turned main red. The sweeper tried to merge `main` into this branch "
            "so fresh checks could re-prove it, and GitHub declined, which means a REAL "
            "content conflict. Resolve it by hand and the next sweep will pick it up "
            "(the label stays armed)."
        ),
        merge_token,
    )
    _annotate(
        "warning",
        "merge-on-green",
        f"PR #{number}: stale proof and update-branch declined — labeled merge-blocked.",
    )
    return "conflict"


def sweep_pull(
    repo: str,
    pull: dict[str, Any],
    read_token: str,
    merge_token: str,
    freshness: "ProofFreshness",
    main_clean: set[str] | None = None,
) -> str:
    """Judge and, when clean, merge one labeled pull request. Returns the verdict.

    ``freshness`` is REQUIRED and has no default on purpose. A default would let a
    caller that forgot to build it merge on an undated green forever, which is the
    exact failure this parameter exists to close; making it required turns that
    mistake into a TypeError at the call site instead of a silent no-op.

    ``main_clean`` — the check names currently green on main's tip, from
    :func:`main_clean_check_names`. It only ever WIDENS what a red PR may do (see
    the base-inherited-red branch), never what a clean one may merge, so unlike
    ``freshness`` a missing value is safe: it defaults to the empty set, which
    reproduces the pre-2026-08-07 behaviour exactly.
    """
    main_clean = main_clean or set()
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
        # A red inherited from a base that has since been healed is not this pull
        # request's red. Every failing check being GREEN on main's tip is the
        # signature: the PR ran against an older main, main was repaired, and
        # nothing has re-tested the PR since. Refresh it and let its fresh checks
        # decide on a later sweep — the same courtesy the clean-but-stale path
        # below has always had, which this branch simply reaches first.
        #
        # Narrow on purpose. If even ONE failing check is not currently clean on
        # main, this is not a base-inherited red and the old path runs unchanged,
        # so a genuine regression can never be refreshed out of sight. `main_clean`
        # is empty whenever main was unreadable, and an empty set is never a
        # superset of a non-empty failing set — so the degraded case blocks too.
        #
        # Self-terminating: update-branch answers 422 when the head is already
        # current, which is exactly the case where the red must be the PR's own,
        # and the call falls through to `merge-blocked` below. So a PR cannot be
        # refreshed twice for the same red, and no loop is possible.
        bad_names = failing_check_names(runs)
        if bad_names and main_clean and bad_names <= main_clean:
            if update_branch(repo, pull, merge_token):
                clear_blocked(repo, pull, merge_token)
                print(
                    f"PR #{number}: red checks ({', '.join(sorted(bad_names)[:6])}) "
                    "are all green on main — the base moved under it. Refreshed; its "
                    "fresh checks decide on a later sweep.",
                    flush=True,
                )
                return "rebased"

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

    # Every check concluded clean. The remaining question is not WHETHER the head is
    # proven but WHEN — a green computed against a base main has since moved past may
    # no longer describe the merge (#4583). Fails closed: any answer this cannot
    # compute is "re-prove".
    try:
        stale, reason = freshness.stale_for(pull, runs)
    except Exception as exc:  # a broken read must never become permission to merge
        stale, reason = True, f"the tested-surface check itself failed ({exc})"
    if stale:
        return reprove(repo, pull, reason, read_token, merge_token)
    print(f"PR #{number}: proof still current — {reason}.", flush=True)

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

    try:
        freshness = ProofFreshness.build(repo, read_token)
    except Exception as exc:
        # Sweep-level, so it aborts rather than re-proving 60 pull requests one by
        # one: a missing path filter or an unreadable main history is a broken
        # sweeper, not 60 stale proofs, and mass `update-branch` would burn a CI run
        # per pull request to answer a question the sweep never actually asked.
        # Fails closed in the only direction that matters — nothing merges.
        _annotate(
            "error",
            "merge-on-green",
            f"Could not establish the tested-surface gate: {exc}; no PRs swept.",
        )
        return 1

    # One read of main's tip, shared by every pull request in the sweep. Never
    # fatal: an empty set disables the base-inherited-red refresh and every PR
    # falls through to the unchanged blocking path.
    main_clean = main_clean_check_names(repo, read_token)
    if not main_clean:
        _annotate(
            "notice",
            "merge-on-green",
            "main's tip published no clean non-spurious checks (or was unreadable) — "
            "base-inherited reds will be labeled merge-blocked as before, not refreshed.",
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
            verdict = sweep_pull(
                repo, pull, read_token, merge_token, freshness, main_clean
            )
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
        + ", ".join(f"{count} {verdict}" for verdict, count in sorted(tally.items()))
        + f" ({freshness.commit_file_reads} main commit(s) classified)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
