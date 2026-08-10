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

THE SWEEPER CAN STARVE ITSELF (measured 2026-08-07). Everything above spends API
calls without ever asking how many are left. `READ_TOKEN` is the job's own
`GITHUB_TOKEN`, whose Actions quota is **1,000 requests per hour PER REPOSITORY**
— shared by every concurrent sweep and by every other lane in this repo that
reads with `GITHUB_TOKEN`. A full sweep of the armed backlog costs roughly

    1 listing + ~3 baseline + 1 main timeline + ~6 walking main for a proved
      commit + 1 per pull request (check runs) + ~4 per pull request that is
      clean-but-refused (files, merge, settled, update-branch)

which run 31148157570 (04:39Z, 93 pull requests: 84 blocked / 5 conflict /
4 pending) spent as ~121 calls in 82 seconds. The `workflow_run` trigger fires
far more often than that budget allows — 23-28 non-skipped sweeps in the 02Z
hour — so 28 x 121 = ~3,400 calls against a 1,000/hr bucket. The bucket empties,
every later sweep 403s on its FIRST call, and because sweeps keep firing they
keep consuming each refill. Measured outage: continuous failure 03:34Z-04:38Z,
recovery at 04:39Z, one clean hourly window.

That is a self-sustaining deadlock, and it is the mechanism behind this repo's
recurring armed backlog: a big backlog makes each sweep expensive, the token
starves, nothing merges, the backlog stays big.

So the sweep is now BUDGET-AWARE, in three places. It preflights `GET
/rate_limit` (which does not itself count against the core budget) and DEFERS —
exit 0 with a notice, never a red run — when the remaining budget cannot fund a
useful pass. It evaluates at most `MAX_PULLS_PER_SWEEP` pull requests per run,
in a rotating order that no pull request can be starved out of, and it says which
ones it deferred. And it re-reads the budget as it goes, stopping cleanly rather
than dying half-way through on a 403. A deferred sweep merges strictly FEWER pull
requests than a full one, never more.

A COMMIT WALK CANNOT FIND MAIN'S PROOF ON A HIGH-VELOCITY BRANCH (measured
2026-08-08). The base-inherited-red path below is the mechanism that drains the
armed backlog after a main-red episode, and for its first two weeks it was
STRUCTURALLY INERT. It asked "which checks are green on main?" by walking main
newest->oldest over a fixed budget of the last 20 commits, looking for one that
published `ci-pack-*`. Two facts of this repository make that walk unable to
succeed:

  * `ci.yml` has NO `push` trigger — its `on:` is `pull_request` +
    `workflow_dispatch` only. main is therefore proven ONLY when somebody runs
    `gh workflow run ci.yml --ref main` by hand, a couple of times a day at best.
  * main takes ~24 commits per 2 HOURS from the nightly and wire lanes
    (press-wire, earnings-wire, research_vault, whitehouse, `data:` timings).
    They are `[skip ci]` or path-filtered, so they publish ambient checks
    (`sweep`, `wire`, `immune`, `monitor`, ...) and never a pack.

So the 20-commit window spanned ~100 MINUTES while the newest real proof of main
sat 117 COMMITS / 12 HOURS back. Run live against this repository, the walk
returned 18 ambient names and zero `ci-pack-*`, while 31 armed pull requests were
blocked on `ci-pack-2`, 29 on `ci-pack-3`, and main's newest completed ci.yml run
(4b61c11a16f8, 11:20:04Z) had all four packs `success`. "every failing check is
clean on main" was therefore false for every one of them, forever: 48 armed pull
requests, ~40 of them also carrying `merge-blocked`, needing a human audit every
day.

This is VELOCITY-DEPENDENT, which is why it "used to work". PR #4968 repaired a
different halt condition in the same walk but kept the fixed 20-commit budget, so
it worked on the day it landed (a dispatch happened to be recent) and decayed back
as the wire lanes got busier. Any commit-count budget has the same fate.

`main_proof` therefore stops walking commits and asks for the thing actually
wanted — the newest concluded run of each proof workflow on main, and its per-job
conclusions — in 4 requests instead of up to 20, against the same `READ_TOKEN`
budget that starved this sweeper on 2026-08-07. And because the answer is only as
good as its freshness, `ensure_main_baseline` lets the sweep ORDER the proof it
needs rather than waiting for a human to dispatch one.

REFRESHES ARE CAPPED TOO, and for a second reason. `update-branch` is the
sweeper's answer to three different situations — a stale-but-clean proof, a merge
GitHub refused, and (since the base-inherited-red path in `main_proof`)
a red the PR inherited from a main that has since been healed. That third one is
the dangerous one at scale, because it makes a large fraction of the backlog
eligible AT ONCE: the measured shape was 84 of 93 armed pull requests red on the
same `ci-pack-1/2/3`. Each refresh is a write call AND a fresh `ci` run, which
takes 36-91 minutes on an 8-runner self-hosted pool. Uncapped, the first sweep
after that path shipped would have queued ~84 pack runs from a single 46-second
job — a multi-day CI jam, and a much worse outage than the one being repaired.
`MAX_REFRESHES_PER_SWEEP` drains the same backlog over ~11 sweeps instead, which
at the observed sweep rate is well under an hour. A pull request whose refresh
this sweep could not fund is left ARMED AND UNLABELED, never `merge-blocked` —
it has done nothing wrong, and `mark_blocked`'s comment is one-shot, so a false
accusation would be the one that sticks.

Individual pull-request outcomes are ANNOTATIONS, never job failures: one PR with
a red check must not fail a sweep that also had clean PRs to merge. The process
exits non-zero only when the sweep itself could not run — and a sweep the API
budget deferred DID run, correctly, so that exits 0.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

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
# A workflow-level catch-all is allowed to START the selector so a brand-new
# repository root cannot bypass CI.  It is not, by itself, evidence that every
# file affects every check.  Treating ``**`` as a tested-surface entry makes any
# main commit overlap every pull request and recreates the strict update-branch
# livelock that the freshness gate was built to avoid.  ``load_pr_gates`` keeps
# this provenance separately and the decision below fails closed only when a
# path is covered by the catch-all and by no more specific ownership entry.
START_ONLY_PATH_PATTERNS = frozenset({"**"})
# The conclusions that count as "this check did not fail". `neutral` and
# `skipped` are the shapes a path-filtered or deliberately-inert job publishes.
#
# Membership here means "did not fail" and NEVER "passed" — do not read it as the
# latter, and do not evict `skipped` to try to make it mean the latter. A ci.yml
# pack that legitimately skips on a `paths:` filter is a real clean result, so
# `skipped` has to stay; what stops an ALL-skipped head from reading clean is
# `decide_verdict`'s separate affirmative-pass requirement, not this set.
CLEAN_CONCLUSIONS = {"success", "neutral", "skipped"}
# `_head_check_runs`' cap in .claude/hooks/ship_loop_guard.py, for the same
# fail-closed reason: PR #3629's head carried 101 check runs, so a single
# `per_page=100` call hid the tail and a red past page one went unseen.
CHECK_RUN_PAGE_CAP = 5
REQUEST_TIMEOUT_SECONDS = 30

# --- the API budget -----------------------------------------------------------
#
# `READ_TOKEN` is the job's own GITHUB_TOKEN: 1,000 requests/hour PER REPOSITORY,
# shared by every concurrent sweep and by every other GITHUB_TOKEN reader in this
# repo. All the numbers below are derived from run 31148157570's measured cost —
# ~121 calls for 93 pull requests, i.e. ~1 call per pull request plus the fixed
# overhead and ~4 more for each clean-but-refused one.
#
# MAX_PULLS_PER_SWEEP is the load-bearing one. The observed peak sweep rate is 28
# non-skipped runs in an hour, so a sweep must cost at most 1000/28 = ~35 calls to
# be sustainable at that rate. Fixed overhead against READ_TOKEN is ~9 (1 listing +
# ~3 baseline + 1 main timeline + 4 for `main_proof` — two workflows x (newest run +
# its jobs)); `ensure_main_baseline`'s 2 calls are charged to MERGE_TOKEN, a
# different bucket, and are deliberately NOT counted here. The `fixed = 12` this
# floor was sized against therefore now carries ~3 calls of headroom rather than
# being exact, which is the safe direction. That leaves ~23. 25 is the chosen cap:
# marginally above that steady-state
# figure, because the sweep rate only peaks at 28 and RATE_LIMIT_RESERVE stops the
# pass cleanly if a run does overshoot. Uncapped, the same 28 sweeps cost ~3,400
# calls and empty the bucket in the first 8 of them.
MAX_PULLS_PER_SWEEP = 25
# Do not START a sweep below this. A capped pass needs ~12 fixed + 25 x up-to-5 +
# a few writes ~= 150 in its worst shape, so 200 both funds the pass and leaves the
# last fifth of the bucket to the OTHER lanes that read main with GITHUB_TOKEN —
# a merge sweeper starving render.yml would just move the outage.
RATE_LIMIT_FLOOR = 200
# Stop MID-sweep below this. Covers the in-flight pull request's remaining writes
# (merge, label, comment, delete-ref) plus the calls that can be spent between two
# budget polls, so the stop is clean rather than a 403 half-way through.
RATE_LIMIT_RESERVE = 60
# Poll `GET /rate_limit` every N evaluated pull requests rather than every one. It
# costs no core budget but it is still a round trip; at <=5 calls per pull request
# the reserve above comfortably covers the at-most-25 calls spent between polls.
BUDGET_RECHECK_EVERY = 5
# Each `update-branch` is a write AND a fresh CI run on a saturated pool (36-91
# minutes, 8 self-hosted runners). The base-inherited-red path makes most of a red
# backlog eligible at once — measured 84 of 93 armed pull requests — so uncapped,
# one 46-second sweep would queue ~84 pack runs and jam CI for days. 8 drains the
# same backlog over ~11 sweeps, which at the observed sweep rate is under an hour.
MAX_REFRESHES_PER_SWEEP = 8
# The rotation advances by MAX_PULLS_PER_SWEEP every bucket, so every armed pull
# request enters the window within ceil(N / cap) buckets — ~40 minutes for a
# 93-PR backlog. Ten minutes matches the recovery cron; the sweeper keeps NO state
# between runs (it is a level-triggered reconciler), so the clock IS the cursor.
ROTATION_BUCKET_SECONDS = 600

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


class RateLimited(RuntimeError):
    """A read GitHub refused for rate-limit reasons, primary or secondary.

    Distinct from `RuntimeError` because the two demand opposite reactions. A
    broken sweep is a red run someone must look at; a rate-limited sweep is a
    sweep that correctly declined to run, and turning that into a red run is how
    a starved lane buries its own diagnosis under 17 identical failures.
    """

    def __init__(self, message: str, *, retry_after: int | None = None, secondary: bool = False):
        super().__init__(message)
        self.retry_after = retry_after
        self.secondary = secondary


# `_request` records the last response's headers here so callers can tell a
# quota 403 from a permissions 403. A module global rather than a wider return
# type on purpose: `_request`'s `(status, payload)` shape is the seam every test
# in tests/test_merge_on_green.py monkeypatches, and widening it would rewrite
# the whole pack to buy a diagnostic. A monkeypatched `_request` simply leaves
# this empty, which degrades the classifier to body-only — the safe direction.
_LAST_RESPONSE_HEADERS: dict[str, str] = {}


def last_response_headers() -> dict[str, str]:
    """Lower-cased headers of the most recent real HTTP response."""
    return dict(_LAST_RESPONSE_HEADERS)


def _record_headers(raw: Any) -> None:
    _LAST_RESPONSE_HEADERS.clear()
    try:
        items = raw.items()
    except AttributeError:
        return
    for key, value in items:
        _LAST_RESPONSE_HEADERS[str(key).lower()] = str(value)


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

    Response headers land in `last_response_headers()`. `x-ratelimit-remaining`
    and `retry-after` are the only evidence that separates "the budget is gone"
    from "this token may not do that", and both arrive ONLY in the headers.
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
            _record_headers(getattr(response, "headers", None))
            body = response.read()
            return int(response.status), (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        _record_headers(getattr(exc, "headers", None))
        body = exc.read() if hasattr(exc, "read") else b""
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            parsed = None
        return int(exc.code), parsed


def _api_message(payload: Any) -> str:
    """GitHub's own explanation of a failure, when the body carried one."""
    if isinstance(payload, dict):
        message = str(payload.get("message") or "").strip()
        if message:
            return message
    return ""


def rate_limit_refusal(
    status: int, payload: Any, headers: dict[str, str] | None = None
) -> RateLimited | None:
    """Classify one failed API answer: rate limit, or something else?

    Pure, so the discrimination is testable without a network — and it is worth
    discriminating, because for the whole 2026-08-07 outage the operator saw only
    `pull-request listing failed: HTTP 403`, which reads identically whether the
    quota is gone, a burst tripped a SECONDARY limit, or the token lost a scope.

    Returns a `RateLimited` only on POSITIVE evidence:

      * `x-ratelimit-remaining: 0`     — primary quota, the measured cause here;
      * a `retry-after` header          — GitHub's secondary/abuse throttle;
      * a body that says so             — "API rate limit exceeded", "secondary
                                          rate limit", "abuse detection".

    Everything else returns None and stays a hard error. A 403 with no such
    evidence is far more likely a permissions regression, and silently downgrading
    that to "deferred, exit 0" would hide a genuinely broken lane behind a notice —
    the one failure mode worse than the outage this function documents.
    """
    if status not in {403, 429}:
        return None
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    message = _api_message(payload)
    lowered = message.lower()

    retry_after: int | None = None
    raw_retry = headers.get("retry-after", "").strip()
    if raw_retry.isdigit():
        retry_after = int(raw_retry)

    remaining = headers.get("x-ratelimit-remaining", "").strip()
    exhausted = remaining.isdigit() and int(remaining) == 0
    secondary = "secondary rate limit" in lowered or "abuse detection" in lowered
    primary = exhausted or "api rate limit exceeded" in lowered

    if not (secondary or primary or retry_after is not None):
        return None

    kind = "secondary (burst) rate limit" if secondary else "primary API quota"
    parts = [f"HTTP {status}: {kind} reached"]
    if message:
        parts.append(f"GitHub said {message!r}")
    if exhausted:
        reset = headers.get("x-ratelimit-reset", "").strip()
        limit = headers.get("x-ratelimit-limit", "").strip() or "?"
        window = f", window resets at epoch {reset}" if reset.isdigit() else ""
        parts.append(f"0 of {limit} requests left{window}")
    if retry_after is not None:
        parts.append(f"retry-after {retry_after}s")
    return RateLimited("; ".join(parts), retry_after=retry_after, secondary=secondary)


def _read_failed(status: int, payload: Any, what: str) -> RuntimeError:
    """The exception a failed READ should raise: RateLimited, or a named error.

    Every read helper funnels its failure through here so a quota 403 is a
    deferral everywhere and an unexplained one is loud everywhere, and so
    GitHub's own message reaches the Actions log instead of a bare status code.
    """
    refusal = rate_limit_refusal(status, payload, last_response_headers())
    if refusal is not None:
        return refusal
    message = _api_message(payload)
    return RuntimeError(f"{what}: HTTP {status}" + (f" ({message})" if message else ""))


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

      ``unproven`` — nothing on the head affirmatively PASSED. Never merged. Three
        shapes arrive here. A docs-only PR that matched no `paths:` filter carries
        no check runs at all. A head whose only run is the spurious Cloudflare X is
        the same nothing wearing a check — which is why the count is taken AFTER
        the spurious filter, since a literal "zero check runs" rule would merge it.
        And a head whose every surviving check concluded `skipped`/`neutral` is that
        same nothing wearing a name the spurious filter does not know (#4779, below).
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
    # AN ABSENCE OF FAILURE IS NOT A PASS (#4779, measured 2026-08-06 during the
    # Actions major outage #4743 documents). #4779's `pull_request` webhook was
    # dropped, so ci.yml scheduled NO run, and the head carried exactly two checks:
    #
    #     Supabase Preview        completed  skipped
    #     Workers Builds: macro   completed  failure
    #
    # `is_spurious_check` knows the Cloudflare X and filters it, but nothing knew
    # `Supabase Preview`, so it survived into `considered`, made it non-empty, and
    # the `unproven` branch above never fired. Nothing was pending; `skipped` is in
    # CLEAN_CONCLUSIONS; `bad` was empty. Verdict: `clean` — squash-merge a head with
    # ZERO CI evidence, which is the exact outcome the `unproven` rule exists to
    # prevent, defeated by a third-party integration the filter cannot enumerate.
    #
    # So the gate is an AFFIRMATIVE pass, not the absence of a red: enumerating every
    # third-party app that might publish an inert check is a blocklist that loses to
    # the next integration someone installs, while "at least one check actually
    # succeeded" holds for all of them without naming any. Widening
    # `is_spurious_check` would have fixed #4779 and not the next one.
    #
    # This cannot block an ordinary path-filtered PR. ci.yml is `paths:`-filtered at
    # the WORKFLOW level, so a non-matching PR gets no run at all and was already
    # `unproven` before this line existed; `ci-pack`'s only job-level `if:` is
    # `action != 'closed'`, which is true for every event that opens or updates a
    # pull request. A head with real packs therefore carries real successes, and a
    # mixed head (one success + one path-skipped pack) still reads `clean`.
    if not any(run.get("conclusion") == "success" for run in considered):
        return "unproven", []
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
            raise _read_failed(status, payload, "check-run listing failed")
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


def _parse_dt(value: Any) -> dt.datetime | None:
    """The same stamp as a TZ-AWARE datetime. None when unusable.

    Separate from `_parse_iso` rather than layered on it, because the two want
    opposite things from a naive input. `_parse_iso` produces an epoch float, and
    `datetime.timestamp()` on a naive value silently interprets it in the RUNNER's
    local zone; this one is compared against other datetimes, where a naive value
    is not merely skewed but a `TypeError`. GitHub always sends UTC (`...Z`), so a
    missing offset is normalised to UTC here — the alternative, refusing it, would
    turn a hypothetical API formatting change into a silent gate that never opens.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


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
      * no PR-triggered workflow declares a specific (non-catch-all) path at all
        — same reason;
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
        start_only_patterns: list[str] = []
        if isinstance(trigger, dict) and isinstance(trigger.get("paths"), list):
            declared_patterns = [str(entry) for entry in trigger["paths"]]
            negated = [
                entry for entry in declared_patterns if entry.startswith(NEGATION_PREFIX)
            ]
            if negated:
                raise RuntimeError(
                    f"{path.name} uses `!` negation in on.pull_request.paths "
                    f"({negated[0]}), which the shared matcher does not model"
                )
            start_only_patterns = [
                entry
                for entry in declared_patterns
                if entry in START_ONLY_PATH_PATTERNS
            ]
            patterns = [
                entry
                for entry in declared_patterns
                if entry not in START_ONLY_PATH_PATTERNS
            ]
        gates.append(
            {
                "workflow": path.name,
                "patterns": patterns,
                "start_only_patterns": start_only_patterns,
            }
        )

    if not gates:
        raise RuntimeError(f"no on.pull_request workflow found under {workflows_dir}")
    if not any(gate["patterns"] for gate in gates):
        raise RuntimeError(
            f"no PR-triggered workflow under {workflows_dir} declares a paths "
            "filter with a specific non-catch-all entry"
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
            raise _read_failed(status, payload, "main commit listing failed")
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
            raise _read_failed(status, payload, f"commit {sha[:12]} unreadable")
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
                matched_specific = False
                matched_start_only = False
                for gate in self.gates:
                    matches = matching_patterns(name, gate["patterns"])
                    candidates.update(matches)
                    matched_specific = matched_specific or bool(matches)
                    matched_start_only = matched_start_only or bool(
                        matching_patterns(
                            name, gate.get("start_only_patterns") or []
                        )
                    )
                if matched_start_only and not matched_specific:
                    return True, (
                        f"main commit {commit['sha'][:12]} touched {name}, which is "
                        "covered only by a workflow start catch-all and has no "
                        "specific tested-surface owner"
                    )

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
        raise _read_failed(status, payload, "pull-request listing failed")
    return [pull for pull in payload if MERGE_ON_GREEN_LABEL in label_names(pull)]


# ── the API budget ───────────────────────────────────────────────────────────


def core_rate_limit(token: str) -> tuple[int, int] | None:
    """``(remaining, limit)`` for the core REST pool, or None when unreadable.

    `GET /rate_limit` is the one endpoint that does NOT count against the core
    budget, which is what makes a preflight possible at all: asking "can I afford
    this sweep" cannot itself be the call that makes the answer no.

    FAILS OPEN — an unreadable answer returns None and the caller sweeps anyway.
    That is deliberate and it is the opposite of the fail-closed choices elsewhere
    in this file, because the risks are not symmetric. Every fail-closed gate here
    protects a MERGE; this one only protects a budget, and a budget check that can
    wedge the whole lane when GitHub hiccups would be a worse outage than the one
    it prevents. The 403 handling on the real calls is the backstop.
    """
    status, payload = _request("GET", f"{GITHUB_API}/rate_limit", token)
    if status >= 400 or not isinstance(payload, dict):
        return None
    core = (payload.get("resources") or {}).get("core") or {}
    remaining, limit = core.get("remaining"), core.get("limit")
    if not isinstance(remaining, int) or not isinstance(limit, int):
        return None
    return remaining, limit


class SweepBudget:
    """How much API budget this sweep may spend, asked repeatedly as it spends it.

    One object per sweep. Three questions, three answers:

      `preflight()`   — may this sweep start at all?
      `may_continue()`— may it evaluate another pull request?
      `take_refresh()`— may it spend an `update-branch` (a write AND a CI run)?

    Every method fails OPEN on an unreadable budget, for the reason in
    `core_rate_limit`. None of them can ever authorise a merge that the check
    gates would refuse — they only ever make the sweep do LESS.
    """

    def __init__(
        self,
        token: str,
        *,
        floor: int = RATE_LIMIT_FLOOR,
        reserve: int = RATE_LIMIT_RESERVE,
        recheck_every: int = BUDGET_RECHECK_EVERY,
        max_refreshes: int = MAX_REFRESHES_PER_SWEEP,
    ) -> None:
        self.token = token
        self.floor = floor
        self.reserve = reserve
        self.recheck_every = max(1, recheck_every)
        self.max_refreshes = max_refreshes
        self.refreshes_used = 0
        self.polls = 0
        self.last_seen: int | None = None

    def _poll(self) -> tuple[int, int] | None:
        reading = core_rate_limit(self.token)
        self.polls += 1
        if reading is not None:
            self.last_seen = reading[0]
        return reading

    def preflight(self) -> tuple[bool, str]:
        """``(may_sweep, detail)``. False means defer — exit 0, not a red run."""
        reading = self._poll()
        if reading is None:
            return True, "the rate limit could not be read; sweeping anyway"
        remaining, limit = reading
        if remaining < self.floor:
            return False, (
                f"only {remaining} of {limit} core API requests remain, below the "
                f"{self.floor} a capped sweep needs. Nothing was swept and nothing "
                "is broken — the budget refills hourly and the next trigger retries"
            )
        return True, f"{remaining} of {limit} core API requests available"

    def may_continue(self, evaluated: int) -> tuple[bool, str]:
        """``(keep_going, detail)`` before evaluating pull request number N.

        Polled every `recheck_every` pull requests rather than every one: the
        endpoint costs no core budget but it is still a round trip, and the
        reserve is sized to cover everything spendable between two polls.
        """
        if evaluated % self.recheck_every:
            return True, ""
        reading = self._poll()
        if reading is None:
            return True, ""
        remaining, limit = reading
        if remaining < self.reserve:
            return False, (
                f"only {remaining} of {limit} core API requests remain, below the "
                f"{self.reserve} reserved to finish cleanly"
            )
        return True, ""

    def take_refresh(self) -> bool:
        """Consume one `update-branch` slot. False when this sweep has spent them.

        Consumed on the ATTEMPT, not on success. The slot bounds API calls as well
        as triggered CI runs, and a refused attempt still spent a call; a sweep that
        could retry indefinitely on 422s would bound neither.
        """
        if self.refreshes_used >= self.max_refreshes:
            return False
        self.refreshes_used += 1
        return True


def sweep_order(
    pulls: list[dict[str, Any]],
    *,
    trigger_head_sha: str = "",
    now: float | None = None,
    cap: int = MAX_PULLS_PER_SWEEP,
    bucket_seconds: int = ROTATION_BUCKET_SECONDS,
) -> list[dict[str, Any]]:
    """Order the armed pull requests so a capped sweep is fair AND useful.

    Three tiers, then a rotation:

      0. `main-red-repair` — the circuit breaker admits exactly one of these per
         sweep when main is red, so it must never fall outside the cap; a repair
         deferred to the next sweep is the whole repo deferred with it.
      1. the head the TRIGGERING workflow run just concluded on. The sweeper wakes
         because some run went green; that run's own pull request is the single
         most likely merge in the backlog, and putting it first is what keeps the
         cap from adding latency to the case the trigger exists to serve.
      2. everything else, rotated.

    The rotation is what makes the cap fair. This script keeps NO state between
    runs — it is a level-triggered reconciler, and that property is load-bearing
    for the overlapping-sweep safety argument — so it cannot remember where the
    last sweep stopped. The wall clock is the cursor instead: the window start
    advances by `cap` every `bucket_seconds`, which walks the whole ring and
    therefore reaches every pull request within ceil(N / cap) buckets no matter
    how long it has sat. Sorting by `updated_at` was the obvious alternative and
    it starves: a pull request nothing acts on never has its timestamp bumped, so
    it would hold its place — or lose it — forever.

    The rotation applies WITHIN tier 0 as well, which is what keeps two armed
    repairs taking turns. Only the first repair in the order gets the single
    per-sweep repair slot, so a permanently-red repair that always sorted first
    would hold that slot forever and its sibling — possibly the one that actually
    fixes main — would never be evaluated at all.
    """
    if not pulls:
        return []
    stable = sorted(pulls, key=lambda pull: int(pull.get("number") or 0))
    span = len(stable)
    when = int(dt.datetime.now(dt.timezone.utc).timestamp() if now is None else now)
    offset = ((when // max(1, bucket_seconds)) * max(1, cap)) % span
    wanted = str(trigger_head_sha or "").strip().lower()

    def rank(entry: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, pull = entry
        if MAIN_RED_REPAIR_LABEL in label_names(pull):
            tier = 0
        elif wanted and str((pull.get("head") or {}).get("sha") or "").lower() == wanted:
            tier = 1
        else:
            tier = 2
        return (tier, (index - offset) % span, int(pull.get("number") or 0))

    return [pull for _index, pull in sorted(enumerate(stable), key=rank)]


#: How old the newest CONCLUDED baseline may be and still authorise merges. A green
#: proof is evidence about the SHA it ran on; main keeps moving under it, so past some
#: horizon the accumulated unproven history outweighs the proof. Six hours is one
#: `ci-main-heartbeat` period — the cadence at which this repository already considers
#: main's health re-checkable — and ~3x the staleness observed during the 2026-08-08
#: incident (the newest concluded baseline was 1.75h old), so it bounds the age without
#: re-creating the block it replaces. A stale green reports ``pending`` WITH ITS AGE and
#: the dispatch to run, so a sweep log names this cause instead of any other non-green.
BASELINE_MAX_AGE_HOURS = 6
#: Number of newest integration-baseline runs examined in one API request. During
#: the 2026-08-09 queue incident, 25 cancelled/in-flight runs sat above a fresh
#: concluded green, so the former 20-run window falsely reported main as unproven.
#: GitHub permits 100 here; one bounded request keeps the control-plane cost fixed
#: while leaving enough room to reach the newest real verdict under churn.
INTEGRATION_BASELINE_RUN_LOOKBACK = 100
#: Minimum gap between two sweeper-ordered `integration-baseline.yml` dispatches, and
#: the reason `ensure_integration_baseline` can be safe at all. MUCH shorter than
#: `MAIN_BASELINE_MIN_INTERVAL_MINUTES` (30, for ci.yml) because this workflow is the
#: cheap one: ~7 min median lifetime against ci.yml's 30-34, so 15 gives a dispatched
#: proof two median lifetimes to conclude and open the breaker before another is
#: considered, while still bounding the rate to 4/hour in the worst case.
#:
#: LOAD-BEARING, NOT POLITENESS. `integration-baseline.yml` carries
#: `concurrency: integration-baseline-main` with `cancel-in-progress: false`, so a
#: redundant dispatch cannot kill a RUNNING baseline — that half is safe. But GitHub
#: keeps exactly ONE PENDING run per group and cancels the previous one on every new
#: arrival (measured in this repository, 2026-08-06), and `pending` includes the wait
#: for a runner, which was 75-94 minutes on the saturated hosted pool this whole repair
#: is about. A raced dispatch therefore throws away a queued proof's accumulated queue
#: position and sends its replacement to the back — the livelock shape, reached by
#: trying to escape it. Hence: in-flight is refused outright, and the floor bounds what
#: the in-flight check cannot see.
INTEGRATION_BASELINE_MIN_INTERVAL_MINUTES = 15


def _baseline_age_hours(run: dict[str, Any], now: dt.datetime | None = None) -> float | None:
    """Hours since the baseline proof's commit entered the queue. None when undated.

    Anchored on ``created_at`` — the moment the proved SHA was pushed — and NOT on
    ``updated_at``, because the question is how much unproven main history has piled
    up behind the proof, not how recently a runner finished with it. Under the queue
    saturation this gate exists to survive those differ by over an hour, and only the
    conservative anchor answers the question actually being asked. The fallbacks exist
    so a single renamed field cannot re-halt the lane; `ensure_main_baseline` dates the
    same runs the same way.
    """
    for field in ("created_at", "run_started_at", "updated_at"):
        stamp = _parse_dt(run.get(field))
        if stamp is not None:
            when = now or dt.datetime.now(dt.timezone.utc)
            return (when - stamp).total_seconds() / 3600.0
    return None


def integration_baseline_state(repo: str, token: str) -> tuple[str, str]:
    """Return ``(state, detail)`` for the newest source-main baseline proof.

    States are ``green``, ``pending``, ``red``, or ``unproven``. Only ``green``
    admits ordinary pull requests. The chosen run's SHA must be an ancestor of
    current main: a successful proof from an abandoned history is not evidence.

    Data/site-only commits intentionally do not trigger the baseline workflow.
    Their current-main descendants therefore accept the latest source proof when
    GitHub's compare endpoint confirms ancestry.

    A ``cancelled`` newest run is SKIPPED, not read as red. `integration-baseline.yml`
    runs under `concurrency: integration-baseline-main`, so a push to main that lands
    while a baseline is pending supersedes it — a routine event on a branch this repo
    pushes to every few minutes, and NOT evidence that main is broken. Reading
    `per_page=1` and treating `cancelled` as a non-clean conclusion latched this breaker
    red for 8.5h on 2026-08-05 (run 31014967682, cancelled 14:23Z) and held 49 armed PRs
    behind it until a baseline was dispatched by hand.

    AN IN-FLIGHT NEWEST RUN IS SKIPPED FOR THE SAME REASON (2026-08-08). This function
    used to read `runs[0]`'s status first and return ``pending`` whenever it was not
    `completed`, so a `queued` run OUTRANKED a concluded green underneath it. That is
    the same category error #4638 fixed for `cancelled`: **a run that has not concluded
    is NO INFORMATION**. A concluded green is positive evidence about a real SHA; a
    queued run is the ABSENCE of evidence, and halting on absence is not fail-closed —
    it is fail-blind, and it fails in the direction that stops the repository.

    Measured 2026-08-08, main GREEN: the newest concluded baseline was `success` at
    05:00:51Z, with a `queued` run from 05:31Z (waiting 75+ min on a saturated hosted
    pool) and a `pending` one from 06:45Z stacked on top. The breaker therefore reported
    ``pending``, and each of the last 8 successful sweeps ended
    `25 baseline-blocked, 71 cap-deferred` — ZERO pull requests evaluated, 8 merges in
    24h against 43 created. `integration-baseline.yml` triggers on every source push to
    main and the wire/nightly lanes push every few minutes, so under load a baseline is
    almost always in flight: the old rule made "almost always blocked" the steady state.
    integration-baseline.yml's own 2026-08-07 note already named this half of the defect
    ("the circuit breaker reads a never-concluding newest run as `pending`, and pending
    blocks ordinary merges") when it flipped `cancel-in-progress` to false.

    Every fail-closed property is kept. One bounded 100-run listing falls through to
    the newest run that
    actually CONCLUDED and decides on that one: a genuine `failure`/`timed_out` stops
    the walk and returns ``red`` (an in-flight run can never launder a red, and an older
    green is never reached past one), the ancestry check still applies to whichever run
    is chosen, a window with nothing concluded in it returns ``unproven``, a read
    failure still raises, and only ``green`` admits ordinary pull requests. What is new
    is that a green must also be FRESH: past `BASELINE_MAX_AGE_HOURS` it yields
    ``pending``, because "main was proven six hours and two hundred commits ago" is a
    different claim from "main is proven".
    """
    workflow = urllib.parse.quote(BASELINE_WORKFLOW, safe="")
    query = urllib.parse.urlencode(
        {"branch": "main", "per_page": str(INTEGRATION_BASELINE_RUN_LOOKBACK)}
    )
    status, payload = _request(
        "GET",
        f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/runs?{query}",
        token,
    )
    if status >= 400 or not isinstance(payload, dict):
        raise _read_failed(status, payload, "integration-baseline listing failed")
    runs = payload.get("workflow_runs") or []
    if not runs:
        return "unproven", "integration-baseline has not published a run"

    # Walk to the newest run that actually CONCLUDED. An in-flight run and a
    # `cancelled` one are skipped for the same reason: neither is evidence about main.
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
        in_flight = sum(
            1 for candidate in runs if str(candidate.get("status") or "").lower() != "completed"
        )
        return "unproven", (
            f"none of the last {len(runs)} integration-baseline runs concluded "
            f"({in_flight} still in flight, {len(runs) - in_flight} cancelled/superseded)"
        )
    conclusion = str(run.get("conclusion") or "").lower()
    run_sha = str(run.get("head_sha") or "")
    run_url = str(run.get("html_url") or "")
    detail = f"{run_sha[:12] or 'unknown-sha'} {run_url}".strip()

    ref_status, ref_payload = _request(
        "GET", f"{GITHUB_API}/repos/{repo}/git/ref/heads/main", token
    )
    if ref_status >= 400 or not isinstance(ref_payload, dict):
        raise _read_failed(ref_status, ref_payload, "main ref lookup failed")
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
        age = _baseline_age_hours(run)
        if age is None:
            return "pending", f"newest concluded baseline could not be dated ({detail})"
        if age > BASELINE_MAX_AGE_HOURS:
            return "pending", (
                f"newest concluded baseline is {age:.1f}h old, past the "
                f"{BASELINE_MAX_AGE_HOURS}h freshness bound ({detail}) — "
                f"`gh workflow run {BASELINE_WORKFLOW} --ref main` re-proves it, and "
                "ensure_integration_baseline orders it automatically unless the "
                "in-flight/interval guard suppressed the dispatch"
            )
        return "green", detail
    return "red", f"{conclusion or 'missing conclusion'} at {detail}"


def ensure_integration_baseline(repo: str, token: str, baseline_state: str) -> str:
    """Order a fresh source baseline when the breaker has aged its OWN proof out.

    `BASELINE_MAX_AGE_HOURS` without this function is the very defect it was added
    alongside: a gate that halts on the absence of evidence and has no way to produce
    any. `integration-baseline.yml` does have a `push` trigger, but its `paths:` filter
    deliberately excludes data/site publisher commits — so the only pushes that re-prove
    main are SOURCE pushes, and the only source pushes to main are merges. A stale green
    therefore blocks merges, which stops the pushes, which keeps it stale: a quieter
    deadlock than the in-flight one, and one that needed a human who knew to run
    `gh workflow run integration-baseline.yml --ref main`. The only escapes were that
    dispatch and the single `main-red-repair` slot. So the sweeper orders it itself.

    ONLY the stale-green reason dispatches, and the reason is RE-DERIVED from the runs
    rather than parsed back out of the state's display string (the lesson
    `failing_check_names` records: display strings are for humans, decisions are made
    from data). Concretely, all of these must hold:

      1. the breaker said ``pending`` — never ``red`` (main is broken; a new baseline
         would faithfully re-prove the same red and change nothing), never ``unproven``
         (nothing concluded to be stale — something is already in flight or every run
         was superseded), never ``green``, and never a read failure, which raises out of
         `integration_baseline_state` and aborts the sweep before this is reached;
      2. the newest CONCLUDED run is clean and older than `BASELINE_MAX_AGE_HOURS`.
         An UNDATABLE one does not qualify: age unknown is not age exceeded, and
         dispatching on it would make an unparseable timestamp a dispatch loop;
      3. the anti-stampede guard below.

    (3) COPIES `ensure_main_baseline`'s SHAPE ON PURPOSE — one query for the newest run
    at ANY status, then two refusals: a newest run that has not concluded means a proof
    is already coming, and a newest run created inside
    `INTEGRATION_BASELINE_MIN_INTERVAL_MINUTES` means one was ordered too recently to
    order another. That single rule covers the `requested`/`waiting`/`pending` statuses
    a `status=in_progress`+`status=queued` pair would miss, the read-then-write race
    between overlapping sweeps (this workflow deliberately carries no `concurrency:`
    block), and the window between a successful dispatch and the run becoming visible.
    See `INTEGRATION_BASELINE_MIN_INTERVAL_MINUTES` for why a raced dispatch is
    genuinely harmful here rather than merely wasteful. It is a BOUND, not a lock:
    two sweeps inside the same second still see the same pre-dispatch state, and what
    saves them is the group's `cancel-in-progress: false`, which means the loser of that
    race is a pending run replaced by an equivalent one and never a running proof.
    An UNREADABLE answer is treated as "something is running" — one sweep of latency
    instead of a stampede.

    NEVER FATAL. Every failure path logs and returns a short string for the sweep
    summary; a sweep that merged pull requests correctly must not go red because it
    could not order a baseline.
    """
    try:
        if baseline_state != "pending":
            return f"not needed (breaker is {baseline_state})"
        workflow = urllib.parse.quote(BASELINE_WORKFLOW, safe="")
        query = urllib.parse.urlencode(
            {"branch": "main", "per_page": str(INTEGRATION_BASELINE_RUN_LOOKBACK)}
        )
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/runs?{query}",
            token,
        )
        if status >= 400 or not isinstance(payload, dict):
            return f"skipped (could not read the baseline runs: HTTP {status})"
        runs = payload.get("workflow_runs") or []
        concluded = next(
            (
                candidate
                for candidate in runs
                if str(candidate.get("status") or "").lower() == "completed"
                and str(candidate.get("conclusion") or "").lower() != "cancelled"
            ),
            None,
        )
        if concluded is None:
            return "not needed (no concluded baseline to be stale)"
        if str(concluded.get("conclusion") or "").lower() not in CLEAN_CONCLUSIONS:
            return "not needed (the newest concluded baseline is not green)"
        age = _baseline_age_hours(concluded)
        if age is None:
            return "skipped (the newest concluded baseline has no usable timestamp)"
        if age <= BASELINE_MAX_AGE_HOURS:
            return f"not needed (the proof is {age:.1f}h old)"

        newest = next(iter(runs), None)
        if isinstance(newest, dict):
            state = str(newest.get("status") or "unknown").lower()
            if state != "completed":
                return f"skipped (a baseline is already {state})"
            created = _parse_dt(newest.get("created_at"))
            if created is None:
                # Undatable here means the interval cannot be enforced, and the
                # interval is the only bound on the dispatch rate. Refuse.
                return "skipped (the newest baseline run has no usable created_at)"
            minutes = (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 60
            if minutes < INTEGRATION_BASELINE_MIN_INTERVAL_MINUTES:
                return (
                    f"skipped (a baseline was ordered {minutes:.0f} min ago, inside the "
                    f"{INTEGRATION_BASELINE_MIN_INTERVAL_MINUTES} min floor)"
                )

        status, body = _request(
            "POST",
            f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
            token,
            {"ref": "main"},
        )
        if status in {201, 204}:
            _annotate(
                "notice",
                "merge-on-green",
                f"Dispatched {BASELINE_WORKFLOW} on main: the newest CONCLUDED baseline "
                f"is {age:.1f}h old, past the {BASELINE_MAX_AGE_HOURS}h freshness bound, "
                "so ordinary merges are paused. Only SOURCE pushes re-trigger that "
                "workflow and only merges make source pushes, so nothing else would "
                "have re-proven main; the next sweep reads the result. This sweep stays "
                "paused — ordering the evidence is not the same as having it.",
            )
            return "dispatched"
        _annotate(
            "warning",
            "merge-on-green",
            f"Could not dispatch {BASELINE_WORKFLOW} on main (HTTP {status}"
            + (f": {_api_message(body)}" if _api_message(body) else "")
            + f"). The {age:.1f}h-old proof stays stale and ordinary merges stay "
            f"paused until a source push or `gh workflow run {BASELINE_WORKFLOW} "
            "--ref main` re-proves main; the sweep itself is unaffected.",
        )
        return f"dispatch failed (HTTP {status})"
    except Exception as exc:  # noqa: BLE001 — ordering a baseline must never fail a sweep
        _annotate(
            "warning",
            "merge-on-green",
            f"Source-baseline dispatch raised {exc!r}; the sweep is otherwise unaffected.",
        )
        return "dispatch error"


#: The workflows whose runs on main constitute "main is proven". `ci.yml` publishes
#: the `ci-pack-*` checks the armed backlog is overwhelmingly red on (31 pull requests
#: on `ci-pack-2` and 29 on `ci-pack-3` when this was measured); `fences.yml` publishes
#: `fence-pack` and the three always-on fence contexts, and a `fence-pack` red must be
#: refreshable for exactly the same reason a pack red is. The FIRST entry is the anchor:
#: it supplies the reported head sha, and it is the workflow `ensure_main_baseline`
#: dispatches, because it is the one with no `push` trigger to dispatch itself.
MAIN_PROOF_WORKFLOWS = ("ci.yml", "fences.yml")
MAIN_BASELINE_WORKFLOW = MAIN_PROOF_WORKFLOWS[0]
#: How many completed runs to look back through, per workflow, for one that CONCLUDED.
#: `status=completed` includes `cancelled`, and until 2026-08-09 `fences.yml` cancelled
#: newest-wins on every push to main — ~24 commits per 2 hours meant a large minority
#: of its runs were superseded rather than judged (2 of the newest 8 on 2026-08-08;
#: ALL TEN during the 11:40Z push burst of 2026-08-09, which zeroed the whole fences
#: proof and helped pin the fleet). #5136 exempts main pushes from the cancel, so a
#: fences run on main now CONCLUDES — but the walk stays: older cancelled runs remain
#: in the listing, operators and timeouts still cancel, and reading `per_page=1` would
#: let any one of them zero out the whole proof, re-creating the intermittently-inert
#: mechanism this function exists to end. The same shape already burned this file once:
#: `integration_baseline_state` latched the breaker red for 8.5h on a cancelled newest
#: run. 10 is one request either way — the walk costs nothing extra.
MAIN_PROOF_RUN_WALK = 10
#: Above this age, main's proof is too old to answer today's reds and the sweep orders a
#: fresh one (see `ensure_main_baseline`). Three hours is chosen against the two clocks
#: that matter: a ci.yml run here takes 30-34 minutes, so the sweep is never dispatching
#: on top of a proof that is merely mid-flight, and the measured gap this repair exists
#: to close was 12 HOURS, so anything in this range is a decisive improvement while
#: leaving the hosted pool ~8 baselines a day at worst.
MAIN_PROOF_MAX_AGE_HOURS = 3
#: The floor between two sweeper-ordered baselines, and the STRUCTURAL bound on the
#: dispatch rate — the one guard that does not depend on the proof being datable.
#:
#: Sweeps overlap by design (merge-on-green.yml carries no `concurrency:` block, and
#: `ci`/`fences`/`integration-baseline` completions can wake three within seconds), so
#: "is one already running?" is a read-then-write race that all of them can win. That
#: race used to be catastrophic rather than wasteful: ci.yml ran every ref under
#: `cancel-in-progress: true`, so a dispatch on main landed in `ci-refs/heads/main`
#: and a SECOND dispatch CANCELLED THE FIRST — 31148430602/31151246743 (2026-08-07,
#: 53 minutes apart), then the 2026-08-09 cascade (31309720615 killed 44 minutes
#: in-progress by 31311537537, itself killed while still queued by 31311693575),
#: where armed-PR sessions pulling the documented lever faster than a 30-45 minute
#: run can conclude meant NO main proof ever concluded at all. The operator call an
#: earlier revision of this comment declined to make unilaterally has now been made
#: (2026-08-09, #5136): ci.yml keeps `cancel-in-progress` FALSE for every
#: `workflow_dispatch` (and fences.yml for everything but `pull_request` events), so
#: a raced dispatch can no longer kill a RUNNING proof — the loser lands in the
#: group's single pending slot, the same shape integration-baseline already has
#: (see INTEGRATION_BASELINE_MIN_INTERVAL_MINUTES).
#:
#: The interval therefore remains load-bearing, but against the smaller harms: a
#: raced dispatch overwrites the QUEUED run, discarding its accumulated queue
#: position (the re-pinned ref SHA is at least as fresh, so correctness is
#: unharmed), and every dispatch spends quota. 30 minutes is just under a run's own
#: 30-34 minute duration, so in the normal case the newest run is still in flight
#: and the status check answers first; the interval covers the two gaps that check
#: cannot: the seconds between a dispatch and the new run becoming visible in the
#: API, and racing sweeps that all read the pre-dispatch state. It is a rate BOUND,
#: not a lock — a stateless level-triggered reconciler has nowhere to hold a lock.
MAIN_BASELINE_MIN_INTERVAL_MINUTES = 30
#: What counts as main PROVING a name, which is NOT the same question `CLEAN_CONCLUSIONS`
#: answers. That set's own comment says membership means "did not fail" and NEVER
#: "passed", and `decide_verdict` supplies the affirmative-pass requirement separately —
#: #4779: "an absence of failure is not a pass". `clean_names` has no such backstop: it
#: is asserted evidence that main is GREEN on a name, used to excuse that name's red on a
#: pull request, so here "did not fail" MUST be read as "passed".
#:
#: A `skipped` job on the baseline is the dangerous one. It is legitimate on a PR head (a
#: path-filtered pack that skips is a real clean result, which is why `CLEAN_CONCLUSIONS`
#: keeps `skipped` and must not be narrowed), but on main it means the job did not run,
#: and treating that as proof would excuse a red on a check that produced no verdict.
#: Costs nothing today: every real job on main's newest ci.yml + fences.yml runs
#: (`ci-pack-0..3`, `fence-pack`, `self-mod-fence`, `capability-broker`, `grader-manifest`)
#: is `success`; the only `skipped` entries are the fork-fallback jobs, which GitHub
#: reports under their UNEVALUATED `name:` expression and so can never collide with a real
#: check name. That accident is exactly why this must be pinned rather than left implicit —
#: the first statically-named conditional job added to either workflow would end it.
PROOF_CLEAN_CONCLUSIONS = {"success"}


@dataclass(frozen=True)
class MainProof:
    """What main is currently proven to pass, and WHEN it was proven.

    ``clean_names`` — job names main PASSED (`PROOF_CLEAN_CONCLUSIONS`, not
      `CLEAN_CONCLUSIONS` — see that constant), unioned across
      `MAIN_PROOF_WORKFLOWS`. Only ever WIDENS what a red pull request may do.
    ``proved_at``   — tz-aware UTC. The OLDEST of the per-workflow newest
      completions, because a proof is only as fresh as its stalest component.
      ``None`` means undatable, which the timestamp gate reads as "no".
    ``head_sha``    — the main commit the anchor workflow's run was computed on.
    ``source``      — a short human string for the sweep log; on failure it says WHY
      there is no proof, which is the line a future session greps for.

    EMPTY IS NOT THE SAME AS UNDATED, and conflating them is a live incident, not a
    tidiness point. A main whose packs all FAILED yields no clean names, but it was
    still proven, at a knowable instant — 4 of the newest 10 main ci.yml runs were
    `failure` when this was measured. Dating that proof `None` made
    `ensure_main_baseline`'s age gate unable to fire, so every sweep with a blocked
    pull request ordered another baseline, which came back red, which dispatched
    again: measured 10 dispatches in 10 consecutive sweeps, ~164 hosted jobs/day
    against an intended ceiling of 8. So an all-red baseline returns an EMPTY
    ``clean_names`` (nothing may be refreshed — correct) with a REAL ``proved_at``
    (nothing needs re-proving — also correct), and only an UNREADABLE run is undated.

    Frozen because it is built once and read by every pull request in the sweep; a
    mutable shared answer is how one pull request's evaluation would silently
    change another's.
    """

    clean_names: frozenset[str]
    proved_at: dt.datetime | None
    head_sha: str
    source: str

    def age_hours(self, now: dt.datetime | None = None) -> float | None:
        """How old the proof is, in hours. None when it could not be dated."""
        if self.proved_at is None:
            return None
        when = now or dt.datetime.now(dt.timezone.utc)
        return (when - self.proved_at).total_seconds() / 3600.0

    def describe(self) -> str:
        """One phrase for the sweep summary — never raises, always says something.

        The names and the date are reported INDEPENDENTLY, because they fail
        independently: a proven-red main has a date and no names, and an unreadable
        one has neither. Collapsing both into "none" is how the dispatch-loop
        incident printed "never proven" about a main that had just been proven red.
        """
        age = self.age_hours()
        aged = "undated" if age is None else f"{age:.1f}h old"
        names = (
            f"{len(self.clean_names)} clean name(s)" if self.clean_names else "NO clean name"
        )
        return (
            f"main proof: {names} at {self.head_sha[:12] or 'unknown-sha'}, "
            f"{aged} ({self.source})"
        )


def _newest_concluded_main_run(
    repo: str, workflow: str, token: str
) -> tuple[dict[str, Any] | None, str]:
    """``(run, detail)`` for the newest run of ``workflow`` on main that CONCLUDED.

    ``run`` is None when there is nothing usable, and ``detail`` then says why — with
    the HTTP status when there was one. Those causes are not interchangeable: a
    rate-limited read, a permissions regression and a genuinely absent run all used to
    render as "has no concluded run on main", and this whole repair exists because the
    old mechanism was inert AND its log could not say why.

    Skips `cancelled` runs rather than answering from them — see MAIN_PROOF_RUN_WALK.
    """
    query = urllib.parse.urlencode(
        {"branch": "main", "status": "completed", "per_page": str(MAIN_PROOF_RUN_WALK)}
    )
    status, payload = _request(
        "GET",
        f"{GITHUB_API}/repos/{repo}/actions/workflows/"
        f"{urllib.parse.quote(workflow, safe='')}/runs?{query}",
        token,
    )
    if status >= 400:
        return None, f"{workflow} run listing failed (HTTP {status})"
    if not isinstance(payload, dict):
        return None, f"{workflow} run listing returned an unusable payload"
    seen = 0
    for run in payload.get("workflow_runs") or []:
        if not isinstance(run, dict):
            continue
        seen += 1
        if str(run.get("conclusion") or "").lower() == "cancelled":
            continue
        if run.get("id") is None:
            return None, f"{workflow}'s newest concluded run carries no id"
        return run, ""
    if seen:
        return None, (
            f"{workflow}'s newest {seen} completed run(s) on main were all cancelled"
        )
    return None, f"{workflow} has no completed run on main"


def _run_clean_jobs(
    repo: str, run_id: Any, token: str
) -> tuple[tuple[frozenset[str], dt.datetime | None] | None, str]:
    """``(resolved, why)``. ``resolved`` is None ONLY when the run could not be READ.

    ``resolved`` is ``(names main PASSED, when the run's verdict landed)``; ``why``
    carries the HTTP status when the read failed, for the same reason
    `_newest_concluded_main_run` does — "unreadable" and "read fine, proved nothing"
    have opposite causes and opposite fixes, and the sweep log has to say which.

    PER JOB, not per run. A run whose overall conclusion is `failure` still proves
    every pack that passed inside it, and that distinction is most of the value here:
    a main whose `ci-pack-2` is green and `ci-pack-3` is red must refresh the pull
    requests red on 2 and keep blocking the ones red on 3.

    PASSED, not "did not fail" — `PROOF_CLEAN_CONCLUSIONS`, see that constant for why
    this is deliberately stricter than `CLEAN_CONCLUSIONS`.

    THE RETURN VALUE ANSWERS TWO SEPARATE QUESTIONS, and an earlier revision answered
    them with one `None` for both. "I could not read this run" and "I read it and every
    job failed" are opposite facts: the first must leave the proof undated, the second
    must date it — an all-red main is PROVEN, just proven red. Collapsing them made the
    age gate in `ensure_main_baseline` unfireable and turned a red main into an
    unbounded dispatch loop (10 dispatches in 10 sweeps, measured). So a run that reads
    is always ``(names, when)`` even when ``names`` is empty, and ``None`` means only
    that the read failed.

    ``when`` is the newest completion among the CLEAN jobs when there are any, and
    among all considered jobs otherwise. The first is the conservative choice for
    `proof_postdates_failures` (a later red inside the same run must not re-date the
    green that excuses a pull request); the second only ever applies when
    ``clean_names`` is empty, where nothing can be excused at all and the date is used
    purely to say "main was proven this recently, do not order another baseline".
    Either way it is None if any job in the dating set carries an unusable
    `completed_at` — an undatable component makes the proof undatable rather than
    optimistically dated, and `MAIN_BASELINE_MIN_INTERVAL_MINUTES` bounds the dispatch
    rate in that case instead.

    Under-reading is safe here and over-reading is not, which is why the single
    `per_page=100` page needs no truncation guard: a job past the first page is a job
    missing from `clean_names`, and a missing clean name can only WITHHOLD a refresh.
    """
    if run_id is None:
        return None, "the run carries no id"
    status, payload = _request(
        "GET", f"{GITHUB_API}/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token
    )
    if status >= 400:
        return None, f"run {run_id}'s job listing failed (HTTP {status})"
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return None, f"run {run_id}'s job listing returned an unusable payload"
    jobs = payload["jobs"]
    clean: set[str] = set()
    clean_stamps: list[dt.datetime | None] = []
    considered_stamps: list[dt.datetime | None] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = str(job.get("name") or "")
        if not name or is_spurious_check(name):
            continue
        if str(job.get("status") or "").lower() != "completed":
            continue
        when = _parse_dt(job.get("completed_at"))
        considered_stamps.append(when)
        if str(job.get("conclusion") or "").lower() not in PROOF_CLEAN_CONCLUSIONS:
            continue
        clean.add(name)
        clean_stamps.append(when)
    dating = clean_stamps if clean else considered_stamps
    if not dating or any(stamp is None for stamp in dating):
        return (frozenset(clean), None), ""
    return (frozenset(clean), max(stamp for stamp in dating if stamp is not None)), ""


def main_proof(repo: str, token: str) -> MainProof:
    """What main currently proves, resolved from its WORKFLOW RUNS. 4 requests.

    Read ONCE per sweep and shared by every pull request, because it answers a
    question about main, not about any pull request.

    This exists to tell two reds apart that look identical on a pull request:

      * the pull request broke something — its red is its own, and blocking is
        correct;
      * main was red when the pull request last ran, the pull request inherited that
        failure, and main has since been healed — the red describes a base that no
        longer exists.

    The second shape is what regenerates the armed backlog, and answering it is what
    drains one: every time main goes red, every armed pull request inherits it.

    WHY NOT A COMMIT WALK. This used to ask the question by walking main's last 20
    commits for one that published `ci-pack-*`. That cannot succeed here and the
    reason is arithmetic, not a bug in the loop: `ci.yml` has no `push` trigger, so
    main is proven only by a manual `gh workflow run ci.yml --ref main` a couple of
    times a day, while the nightly and wire lanes push ~24 `[skip ci]` / path-filtered
    commits per 2 HOURS. Measured 2026-08-08, the 20-commit window spanned ~100
    minutes and the newest real proof of main sat 117 COMMITS / 12 HOURS back; the
    walk returned 18 ambient names (`sweep`, `wire`, `immune`, `monitor`, ...) and
    ZERO packs, while 31 armed pull requests were blocked on `ci-pack-2` and 29 on
    `ci-pack-3` — all four packs `success` on main's newest ci.yml run. Raising the
    commit budget only buys time: PR #4968 fixed a different halt condition in the
    same walk, worked the day it landed, and decayed back as the wire lanes got
    busier. A workflow-run lookup has no window to outgrow.

    It is also CHEAPER, which matters because the budget it is charged against is the
    one that starved this sweeper on 2026-08-07: 4 requests (two workflows x newest
    run + its jobs) against up to 20 for the walk, on a `READ_TOKEN` whose quota is
    1,000/hour PER REPOSITORY and shared by every concurrent sweep.

    FAILS CLOSED ON WHAT IT CANNOT READ. A non-200, a missing run, an unparseable
    payload or any exception returns an EMPTY, UNDATED proof, and an empty set can
    never be a superset of a non-empty failing set, so the caller falls through to the
    unchanged `merge-blocked` path. Not knowing what main proves is never permission to
    refresh anything. That rule applies to the WHOLE union, not per workflow: half a
    proof would let a `fence-pack` red be excused by a ci.yml run that says nothing
    about fences.

    A RED WORKFLOW IS NOT AN UNREADABLE ONE. If a run reads and simply passed nothing,
    its names are absent from the union — which already blocks every refresh that
    depended on them — but the proof keeps its DATE, and the other workflow keeps its
    names. Zeroing the union there would be wrong twice: it would discard a genuinely
    green `fences.yml` because `ci.yml` is red, and it would leave the proof undated,
    which is the shape that turned a red main into an unbounded baseline-dispatch loop.

    No exception escapes — the pre-existing "a diagnostic must never fail a sweep"
    property is preserved, and the sweep degrades to its pre-2026-08-07 behaviour.
    """
    try:
        names: set[str] = set()
        stamps: list[dt.datetime | None] = []
        sources: list[str] = []
        head_sha = ""
        for index, workflow in enumerate(MAIN_PROOF_WORKFLOWS):
            run, why = _newest_concluded_main_run(repo, workflow, token)
            if run is None:
                return MainProof(frozenset(), None, "", why)
            run_sha = str(run.get("head_sha") or "")
            resolved, why = _run_clean_jobs(repo, run.get("id"), token)
            if resolved is None:
                return MainProof(frozenset(), None, "", f"{workflow} {why}")
            workflow_names, workflow_at = resolved
            names |= set(workflow_names)
            stamps.append(workflow_at)
            sources.append(
                f"{workflow}@{run_sha[:12] or '?'}"
                + (f" ({len(workflow_names)} passed)" if workflow_names else " (RED: nothing passed)")
            )
            if index == 0:
                head_sha = run_sha
        # The OLDEST of the per-workflow newest completions. A proof is exactly as
        # fresh as its stalest component: fences.yml runs on every push to main and is
        # therefore minutes old, while ci.yml's newest dispatch may be half a day
        # back, and taking the newer of the two would date the ci evidence by the
        # fences evidence — laundering a stale proof exactly the way `proof_instant`
        # refuses to let one re-run launder a hundred stale checks.
        proved_at = None if any(stamp is None for stamp in stamps) else min(
            stamp for stamp in stamps if stamp is not None
        )
        return MainProof(frozenset(names), proved_at, head_sha, " + ".join(sources))
    except Exception as exc:  # noqa: BLE001 — a diagnostic must never fail a sweep
        return MainProof(frozenset(), None, "", f"main proof lookup raised {exc!r}"[:200])


def proof_postdates_failures(proof: MainProof, runs: list[dict[str, Any]]) -> bool:
    """Was main proven AFTER this head's failing checks concluded?

    THE CLAIM THE REFRESH MAKES IS TEMPORAL. "Your red checks are all green on main"
    only means "main was healed since you ran" if the healing proof is NEWER than the
    red. If main's green PREDATES the failure, the pull request ran against an
    already-proven-green main and the red is its OWN — refreshing it would rebase a
    genuine regression out of sight, which is the one outcome the narrowness of that
    branch exists to prevent. The name comparison alone cannot see this.

    IT IS ALSO THE LOOP GUARD, and that is not a bonus — it is required now that the
    path can actually fire. The branch used to argue that no loop was possible because
    `update-branch` answers 422 on an already-current head. That reasoning assumes a
    STATIC main and is false here: main takes ~24 commits per 2 hours, so a head is
    never "already current" for long, and a pull request that comes back red on the
    same pack would be refreshed again on the very next sweep — 4 hosted packs x ~60
    pull requests per round, indefinitely, on a pool that takes 30-34 minutes per run.
    With this gate a refresh makes the pull request's checks NEWER than the proof, so
    it cannot be refreshed again until main is genuinely re-proven: one refresh per
    pull request per main proof, structurally.

    FAILS CLOSED. An undatable proof, no failing runs to compare against, or a failing
    run with a missing or unparseable `completed_at` all return False — and False
    means "block as before", never "refresh".
    """
    if proof.proved_at is None:
        return False
    failing = [
        run
        for run in runs
        if not is_spurious_check(str(run.get("name") or ""))
        and run.get("status") == "completed"
        and run.get("conclusion") not in CLEAN_CONCLUSIONS
    ]
    if not failing:
        return False
    newest: dt.datetime | None = None
    for run in failing:
        when = _parse_dt(run.get("completed_at"))
        if when is None:
            return False
        if newest is None or when > newest:
            newest = when
    return newest is not None and proof.proved_at > newest


def ensure_main_baseline(
    repo: str, proof: MainProof, blocked_names: set[str], token: str
) -> str:
    """Order a fresh proof of main when the sweep could not answer its own backlog.

    THE SWEEPER'S ANSWER IS ONLY AS GOOD AS MAIN'S PROOF, and until now that proof
    depended entirely on a human remembering to run `gh workflow run ci.yml --ref
    main`. `ci.yml` has no `push` trigger — see `main_proof` — so on a branch taking
    ~24 commits per 2 hours the evidence the refresh path needs was measured 12 HOURS
    stale while 48 pull requests sat armed. Repairing the lookup without repairing the
    supply would have fixed the mechanism and left the daily audit in place.

    So the sweep dispatches the baseline itself, but ONLY when all three hold:

      1. the proof is undatable or older than MAIN_PROOF_MAX_AGE_HOURS;
      2. at least one pull request this sweep evaluated was blocked on a non-spurious
         check — i.e. the staleness actually COST something. An idle repository never
         dispatches, however old its proof is; a proof nothing needed is not a problem;
      3. the newest ci.yml run on main has CONCLUDED and was created at least
         MAIN_BASELINE_MIN_INTERVAL_MINUTES ago.

    (3) IS THE ANTI-STAMPEDE GUARD and it is load-bearing. It is ONE query for the
    newest run at any status, not the two `status=in_progress` / `status=queued`
    queries an earlier revision used, and the difference is not cosmetic:

      * those two left `requested`, `waiting` and `pending` entirely unchecked;
      * they were a read-then-write race between overlapping sweeps (this workflow
        deliberately carries no `concurrency:` block, and three wake-ups can arrive
        within seconds); until 2026-08-09 a raced dispatch even CANCELLED the
        in-flight proof (ci.yml then cancelled newest-wins on every ref — #5136
        exempts dispatches, so the racing loser merely overwrites the queued
        pending slot);
      * they could not see the window between a successful dispatch and the new run
        becoming visible in the API.

    The created-at interval covers all three, bounds the dispatch rate even when
    several sweeps race, and costs one call instead of two. It is a BOUND, not a lock —
    sweeps inside the same second still see the same pre-dispatch state. An UNREADABLE
    answer is treated as "something is running", the direction that costs one sweep of
    latency rather than a stampede.

    (1) and (2) are asked FIRST because they are free; only a sweep that has already
    decided it wants a baseline spends a call asking whether it may have one.

    NEVER FATAL. Every failure path logs and returns; a sweep that merged pull requests
    correctly must not go red because it could not order a baseline. Returns a short
    string for the sweep summary.
    """
    try:
        age = proof.age_hours()
        if age is not None and age <= MAIN_PROOF_MAX_AGE_HOURS:
            return f"not needed (proof is {age:.1f}h old)"
        if not blocked_names:
            return "not needed (no pull request was blocked on a check)"
        workflow = urllib.parse.quote(MAIN_BASELINE_WORKFLOW, safe="")
        query = urllib.parse.urlencode({"branch": "main", "per_page": "1"})
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/runs?{query}",
            token,
        )
        if status >= 400 or not isinstance(payload, dict):
            return f"skipped (could not read the newest baseline run: HTTP {status})"
        newest = next(iter(payload.get("workflow_runs") or []), None)
        if isinstance(newest, dict):
            state = str(newest.get("status") or "unknown").lower()
            if state != "completed":
                return f"skipped (the newest baseline is {state})"
            created = _parse_dt(newest.get("created_at"))
            if created is None:
                # Undatable here means the interval cannot be enforced, and the
                # interval is the only bound on the dispatch rate. Refuse.
                return "skipped (the newest baseline run has no usable created_at)"
            minutes = (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 60
            if minutes < MAIN_BASELINE_MIN_INTERVAL_MINUTES:
                return (
                    f"skipped (a baseline was ordered {minutes:.0f} min ago, inside the "
                    f"{MAIN_BASELINE_MIN_INTERVAL_MINUTES} min floor)"
                )
        status, body = _request(
            "POST",
            f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
            token,
            {"ref": "main"},
        )
        if status in {201, 204}:
            # NEVER "never proven" on an undated proof: main may have been proven and
            # proven RED, which reads identically here and has the opposite cause. The
            # proof's own `source` is the thing that distinguishes them, so print it.
            aged = f"undated ({proof.source})" if age is None else f"{age:.1f}h old"
            _annotate(
                "notice",
                "merge-on-green",
                f"Dispatched {MAIN_BASELINE_WORKFLOW} on main: this sweep left pull "
                f"requests blocked on {len(blocked_names)} distinct check(s) "
                f"({', '.join(sorted(blocked_names)[:6])}) while main's own proof is "
                f"{aged}, so it could not tell an inherited red from a real one. "
                f"{MAIN_BASELINE_WORKFLOW} has no `push` trigger, so nothing else "
                "re-proves main; the next sweep judges those reds against the result.",
            )
            return "dispatched"
        _annotate(
            "warning",
            "merge-on-green",
            f"Could not dispatch {MAIN_BASELINE_WORKFLOW} on main (HTTP {status}"
            + (f": {_api_message(body)}" if _api_message(body) else "")
            + "). Base-inherited reds stay blocked until main is proven; the sweep "
            "itself is unaffected.",
        )
        return f"dispatch failed (HTTP {status})"
    except Exception as exc:  # noqa: BLE001 — ordering a baseline must never fail a sweep
        _annotate(
            "warning",
            "merge-on-green",
            f"Baseline dispatch raised {exc!r}; the sweep is otherwise unaffected.",
        )
        return "dispatch error"


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


def refresh_deferred(number: Any, why: str) -> str:
    """Leave a pull request untouched because the refresh budget is spent.

    NOT a `merge-blocked`, deliberately. The pull request has done nothing wrong —
    this sweep simply ran out of `update-branch` slots — so labelling it would be
    a false accusation, and `mark_blocked`'s comment is one-shot, so the false one
    would be the one that sticks. It stays armed and the next sweep refreshes it.
    """
    _annotate(
        "notice",
        "merge-on-green",
        f"PR #{number}: {why}, but this sweep has spent its "
        f"{MAX_REFRESHES_PER_SWEEP} `update-branch` slots. Left armed and unlabeled; "
        "the next sweep picks it up.",
    )
    return "refresh-deferred"


def reprove(
    repo: str,
    pull: dict[str, Any],
    reason: str,
    read_token: str,
    merge_token: str,
    budget: "SweepBudget | None" = None,
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
    if budget is not None and not budget.take_refresh():
        return refresh_deferred(number, f"its proof is stale ({reason})")
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
    proof: "MainProof | None" = None,
    budget: "SweepBudget | None" = None,
    blocked_names: set[str] | None = None,
) -> str:
    """Judge and, when clean, merge one labeled pull request. Returns the verdict.

    ``freshness`` is REQUIRED and has no default on purpose. A default would let a
    caller that forgot to build it merge on an undated green forever, which is the
    exact failure this parameter exists to close; making it required turns that
    mistake into a TypeError at the call site instead of a silent no-op.

    ``proof`` — what main is currently proven to pass and when, from
    :func:`main_proof`. It only ever WIDENS what a red PR may do (see the
    base-inherited-red branch), never what a clean one may merge, so unlike
    ``freshness`` a missing value is safe: it defaults to an empty proof, which
    reproduces the pre-2026-08-07 behaviour exactly.

    ``budget`` is the same shape of optional: it only ever WITHHOLDS
    `update-branch` slots, so its absent form (no cap) reproduces the uncapped
    behaviour and it can never authorise a merge the check gates would refuse.

    ``blocked_names`` is an OUT-parameter, not an input: the sweep passes a set for
    this function to record what its blocked pull requests were blocked ON, which is
    the evidence :func:`ensure_main_baseline` needs to decide whether a stale main
    proof actually cost anything this pass. Nothing here reads it, so it cannot
    influence any verdict.
    """
    if proof is None:
        proof = MainProof(frozenset(), None, "", "no proof supplied")
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
        # request's red. Every failing check being GREEN on a main proved SINCE they
        # ran is the signature: the PR ran against an older main, main was repaired,
        # and nothing has re-tested the PR since. Refresh it and let its fresh checks
        # decide on a later sweep — the same courtesy the clean-but-stale path
        # below has always had, which this branch simply reaches first.
        #
        # Narrow on purpose, in TWO dimensions. If even ONE failing check is not
        # currently clean on main, this is not a base-inherited red and the old path
        # runs unchanged, so a genuine regression can never be refreshed out of
        # sight. `proof.clean_names` is empty whenever main was unreadable, and an
        # empty set is never a superset of a non-empty failing set — so the degraded
        # case blocks too. And the proof must POSTDATE the failures: main being green
        # BEFORE this head ran is evidence the red is the pull request's own.
        #
        # The timestamp rule is also what makes this branch terminate. It used to
        # argue that update-branch's 422 on an already-current head made a loop
        # impossible — but that assumes a STATIC main, and main takes ~24 commits per
        # 2 hours here, so a head is never "already current" for long and a PR that
        # came back red on the same pack would be refreshed again on the next sweep:
        # 4 hosted packs x ~60 pull requests per round, indefinitely. A refresh makes
        # the PR's checks newer than the proof, so it cannot be refreshed again until
        # main is genuinely re-proven — one refresh per PR per main proof.
        bad_names = failing_check_names(runs)
        if bad_names and proof.clean_names and bad_names <= proof.clean_names:
            if not proof_postdates_failures(proof, runs):
                # GREPPABLE ON PURPOSE. This line is how a future session tells "main's
                # proof is too old to answer this" apart from "this red is genuinely
                # yours" — the two are indistinguishable in the `merge-blocked` comment,
                # and mistaking the first for the second is the audit that cost a human
                # every morning for a fortnight.
                proved = (
                    proof.proved_at.isoformat() if proof.proved_at is not None else "never"
                )
                latest = max(
                    (
                        run.get("completed_at") or "?"
                        for run in runs
                        if str(run.get("name") or "") in bad_names
                    ),
                    default="?",
                )
                print(
                    f"PR #{number}: main-proof-too-old — its red checks "
                    f"({', '.join(sorted(bad_names)[:6])}) are all clean on main, but "
                    f"main was proven at {proved} and those checks concluded at "
                    f"{latest}. A proof that predates the failure does not excuse it, "
                    "so this blocks as usual.",
                    flush=True,
                )
            else:
                # THIS is the branch the refresh cap exists for. A main-red episode
                # makes most of the armed backlog eligible at once (84 of 93 measured),
                # and every refresh queues a fresh 36-91 minute `ci` run onto an
                # 8-runner pool. Deferring is NOT `merge-blocked`: nothing is wrong with
                # the pull request, so it stays armed and unlabeled for the next sweep.
                if budget is not None and not budget.take_refresh():
                    return refresh_deferred(
                        number,
                        "its red checks are all green on main, so it needs a refresh",
                    )
                if update_branch(repo, pull, merge_token):
                    clear_blocked(repo, pull, merge_token)
                    print(
                        f"PR #{number}: red checks ({', '.join(sorted(bad_names)[:6])}) "
                        "are all green on a main proved since they ran — the base moved "
                        "under it. Refreshed; its fresh checks decide on a later sweep.",
                        flush=True,
                    )
                    return "rebased"

        if blocked_names is not None:
            # What this sweep could not answer, for `ensure_main_baseline`.
            blocked_names |= bad_names

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
        return reprove(repo, pull, reason, read_token, merge_token, budget)
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
        if budget is not None and not budget.take_refresh():
            # No slots left to fast-forward it, and the refusal may be nothing but
            # a stale base — so this must NOT fall through to `merge-blocked`.
            return refresh_deferred(number, f"GitHub refused the merge ({detail})")
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
    # The head the `workflow_run` that woke this sweep concluded on, when there was
    # one. Empty for the cron and for workflow_dispatch, which is harmless — it only
    # promotes a pull request within the per-sweep cap, never past a gate.
    trigger_head_sha = os.environ.get("TRIGGER_HEAD_SHA", "").strip()
    if not repo:
        _annotate("error", "merge-on-green", "GH_REPO is not set; nothing to sweep.")
        return 1

    # Preflight the budget BEFORE the first real call. A starved sweeper that keeps
    # firing consumes each hourly refill on its own 403s and never recovers; a
    # deferral is a deliberate, logged no-op and exits 0, because a red run here is
    # noise that masks the genuine failures this lane also reports.
    budget = SweepBudget(read_token)
    may_sweep, budget_detail = budget.preflight()
    if not may_sweep:
        _annotate("notice", "merge-on-green", f"Sweep deferred: {budget_detail}.")
        return 0
    print(f"API budget: {budget_detail}.", flush=True)

    try:
        pulls = labeled_pulls(repo, read_token)
    except RateLimited as exc:
        _annotate("warning", "merge-on-green", f"Sweep deferred: {exc}. No PRs swept.")
        return 0
    except Exception as exc:
        _annotate("error", "merge-on-green", f"Could not list pull requests: {exc}")
        return 1

    if not pulls:
        print(f"No open pull requests labeled {MERGE_ON_GREEN_LABEL}.", flush=True)
        return 0

    try:
        baseline_state, baseline_detail = integration_baseline_state(repo, read_token)
    except RateLimited as exc:
        _annotate("warning", "merge-on-green", f"Sweep deferred: {exc}. No PRs swept.")
        return 0
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

    # BEFORE the pull-request pass, deliberately — the opposite of `ensure_main_baseline`
    # below, and for the opposite reason. That one needs to know what this sweep could
    # not answer, which only exists after the pass. This one's input is the breaker state
    # it already has, and its output is a workflow run whose queue wait is the whole
    # problem, so every second spent sweeping first is a second added to the pause it is
    # trying to end. It does NOT unblock this sweep: ordering evidence is not having it.
    # Never fatal — it returns a string, it does not raise.
    source_baseline = ensure_integration_baseline(repo, merge_token, baseline_state)

    try:
        freshness = ProofFreshness.build(repo, read_token)
    except RateLimited as exc:
        _annotate("warning", "merge-on-green", f"Sweep deferred: {exc}. No PRs swept.")
        return 0
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

    # One lookup of what main is proven to pass, shared by every pull request in the
    # sweep. Never fatal: an empty proof disables the base-inherited-red refresh and
    # every PR falls through to the unchanged blocking path.
    proof = main_proof(repo, read_token)
    if not proof.clean_names:
        _annotate(
            "notice",
            "merge-on-green",
            f"main has no usable proof ({proof.source}) — base-inherited reds will be "
            "labeled merge-blocked as before, not refreshed.",
        )
    else:
        print(proof.describe() + ".", flush=True)

    ordered = sweep_order(pulls, trigger_head_sha=trigger_head_sha)
    considered = ordered[:MAX_PULLS_PER_SWEEP]
    deferred = ordered[MAX_PULLS_PER_SWEEP:]

    tally: dict[str, int] = {}
    # Filled by `sweep_pull` with the check names it had to leave a pull request
    # blocked on. `ensure_main_baseline` reads it to decide whether a stale main proof
    # actually cost this sweep anything — an idle repository never orders a baseline.
    blocked_names: set[str] = set()
    if deferred:
        # NO SILENT CAPS. A sweep that quietly evaluated a quarter of the backlog
        # would look identical in the log to one that evaluated all of it, and the
        # difference is the entire reason this lane stopped working.
        shown = ", ".join(f"#{pull.get('number')}" for pull in deferred[:20])
        more = f" (+{len(deferred) - 20} more)" if len(deferred) > 20 else ""
        _annotate(
            "notice",
            "merge-on-green",
            f"Per-sweep cap: evaluating {len(considered)} of {len(ordered)} armed pull "
            "requests. READ_TOKEN's quota is 1,000 requests/hour per repository and a "
            f"full pass of this backlog costs ~{len(ordered)} of them, so an uncapped "
            "sweep at this trigger rate empties the bucket and every later sweep 403s. "
            f"The order rotates every {ROTATION_BUCKET_SECONDS // 60} minutes, so no "
            f"pull request can be starved. Deferred to a later sweep: {shown}{more}.",
        )
        tally["cap-deferred"] = len(deferred)

    repair_slot_used = False
    for index, pull in enumerate(considered):
        keep_going, why = budget.may_continue(index)
        if not keep_going:
            left = len(considered) - index
            _annotate(
                "warning",
                "merge-on-green",
                f"Stopping after {index} of {len(considered)} pull requests — {why}. "
                f"The remaining {left} stay armed and unlabeled; the budget refills "
                "hourly and the next sweep resumes. Nothing was merged on partial "
                "information.",
            )
            tally["budget-deferred"] = tally.get("budget-deferred", 0) + left
            break
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
                repo, pull, read_token, merge_token, freshness, proof, budget,
                blocked_names,
            )
        except RateLimited as exc:
            # The budget ran out between two polls. Stop the sweep rather than
            # spending the rest of it on 403s — every one of those is a call the
            # NEXT sweep needed, which is the loop that made this outage permanent.
            left = len(considered) - index
            _annotate(
                "warning",
                "merge-on-green",
                f"Stopping at PR #{pull.get('number')} ({index} of {len(considered)} "
                f"done) — {exc}. The remaining {left} stay armed and unlabeled.",
            )
            tally["budget-deferred"] = tally.get("budget-deferred", 0) + left
            break
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

    # AFTER the pull-request pass, deliberately: the dispatch decision needs to see
    # what this sweep was actually unable to answer, which only exists once the pass
    # has run. Never fatal — it returns a string, it does not raise.
    baseline = ensure_main_baseline(repo, proof, blocked_names, merge_token)

    print(
        "merge-on-green sweep complete: "
        + ", ".join(f"{count} {verdict}" for verdict, count in sorted(tally.items()))
        + f" ({freshness.commit_file_reads} main commit(s) classified, "
        + f"{budget.refreshes_used}/{MAX_REFRESHES_PER_SWEEP} refresh slot(s) used, "
        + f"~{budget.last_seen if budget.last_seen is not None else '?'} API requests left"
        + f"; {proof.describe()}; baseline: {baseline}"
        + f"; source-baseline: {source_baseline})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
