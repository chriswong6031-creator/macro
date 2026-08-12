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

REDUNDANT FULL SWEEPS ARE COALESCED (2026-08-11). The old workflow-wide constant
group did not serialise WORK — it serialised the 25-107 minute wait for a shared
GitHub-hosted runner while triggers arrived every ~50 seconds, yielding 0
successful sweeps in 100 runs. The job now has a dedicated runner and a job-level
group: success/schedule/dispatch events share one level-triggered `sweep`, while
failure marker passes are keyed by head SHA so different reds cannot swallow one
another. The full measurement is in .github/workflows/merge-on-green.yml.

This remains a LEVEL-TRIGGERED RECONCILER: every full run re-lists the labeled
pull requests and re-derives every verdict from GitHub's live state. Its one
durable state bit is the controller-owned refresh lease label, which serialises
the single fairness re-proof admitted above a saturated CI cap; the label is itself
reconciled from live PR/check state. Losing a redundant full wake-up therefore
costs nothing so long as one sweep runs. Live-state race guards remain defense in depth for
pre-deploy jobs and out-of-band callers: `already_settled` and the expected-head
reread prevent a stale actor from labeling a merged or newly advanced PR as a
conflict.

A GREEN CAN GO STALE WITHOUT GOING RED (operator ruling 2026-08-06). Everything
above judges a head's checks. Nothing above asked WHICH exact main SHA they tested,
and a check proves the head against the base it was handed, not against the base
that exists at merge time. PR #4583 is the worked example:

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

So before an otherwise-clean pull request is merged, `ProofFreshness` reads the
immutable base SHA recorded on the exact head's pull-request checks, then asks
whether newer main commits entered the PR's TESTED SURFACE. If they did, nothing
merges: the head is handed to `update-branch` and its fresh checks decide on a later
sweep. If they did not, the existing green still means what it said. That is the
operator's chosen option — NOT strict up-to-date-with-main, which would serialise a
60-PR queue into days. Missing proof identity defers WITHOUT changing the branch:
mutating code cannot repair a control-plane read, and doing so would self-reprove
forever.

A MERGED PULL REQUEST CAN DELIVER NOTHING (measured 2026-08-09). Every gate above
judges the head's CHECKS; none of them ever asked whether the head still contains
the pull request's WORK. Four armed pull requests (#5055 #5061 #5078 #5091) sat
through a day of update-branch/refresh cycles and came out with their branch heads
clobbered to content-identical-with-main — #5055's head at merge time,
6f9a7f63bfb, contained none of its files. Their checks were honestly green (they
tested what was effectively main's own content), the freshness gate was satisfied,
and the sweeper squash-merged EMPTY diffs: merge commits 455130e4faa, e7564f0fc7b,
db48f1d6aa9 and 0ae4270c76a all carry empty diffstats, the PRs read MERGED, and
zero files landed. (#5074, merged in the same drain, was NOT a phantom — its
squash landed a deliberately amended floor guard.) That is the worst outcome this
lane can produce, because it READS as success — the loss surfaced only when a
human verified the files on main by content, and recovery re-landed 14 files
byte-exact in #5198.

So `sweep_pull` now refuses ANY armed pull request whose live `base...head`
compare is EMPTY — unconditionally, immediately before the irreversible step. An
earlier draft of this invariant keyed on a DISAGREEMENT instead: live diff empty
while the PR's materialised files view still names files. The recovery lane
measured that shape VACUOUS — GitHub recomputes the files view against the
clobbered head, so all four phantoms' files lists read 0 files pre-merge and the
disagreement never occurs. Emptiness alone is the signal, and refusing on it
costs nothing: no legitimate armed pull request has an empty diff, because
squash-merging one records MERGED while delivering nothing — a phantom at worst,
a pointless no-op at best. The refusal labels `merge-blocked` and explains once,
naming the head SHA so the owner can find the good pre-clobber commit (or close
a genuinely empty pull request). See `live_diff_file_count` for the mechanism
and `update_branch` for the likely clobber source.

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
useful pass. It sizes the pull-request window from the live core limit (25 at the
historical 1,000/hour limit, up to 100 on Enterprise), in a rotating order that no
pull request can be starved out of, and it says which ones it deferred. And it
re-reads the budget as it goes, stopping cleanly rather than dying half-way
through on a 403. A deferred sweep merges strictly FEWER pull requests than a
full one, never more.

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
import secrets
import sys
import time
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
REFRESH_LEASE_LABEL = "merge-refresh-in-flight"
REFRESH_LEASE_COLOR = "1d76db"
REFRESH_LEASE_RECORD_PREFIX = "m1"
REFRESH_LEASE_DESCRIPTION = "Controller-owned merge-on-green refresh lease"
REFRESH_LEASE_GRACE_SECONDS = 10 * 60
REFRESH_LEASE_MAX_SECONDS = 2 * 60 * 60
BASELINE_WORKFLOW = "integration-baseline.yml"
SELF_WAKE_WORKFLOW = "merge-on-green.yml"
SELF_WAKE_MIN_INTERVAL_SECONDS = 60
SELF_WAKE_LOOKBACK = 10
SELF_WAKE_ATTEMPTS = 1
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
# Conclusions that prove neither a pass nor a code failure.  In particular, a
# superseded/cancelled runner is not evidence against the pull request and must
# never burn the one-shot ``merge-blocked`` comment.
INCOMPLETE_CONCLUSIONS = {"cancelled", "stale"}
# The two repository-owned proof workflows publish these exact anchors on every
# ordinary pull request.  Third-party successes are useful additional checks but
# can never substitute for the CI/fence proof the controller is meant to await.
REQUIRED_CI_ANCHORS = frozenset(f"ci-pack-{index}" for index in range(12))
REQUIRED_FENCE_ANCHOR = "fence-pack"
REQUIRED_FORK_FENCE_ANCHORS = frozenset(
    {"self-mod-fence", "capability-broker", "grader-manifest"}
)
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
# The historical 1,000/hour pool proved that 25 pull requests per sweep is
# sustainable: fixed overhead was ~12 calls and the common case costs ~1 call per
# pull request. The Enterprise transfer raised this repository's live limit to
# 15,000/hour, but the old fixed cap kept deferring a 29-pull backlog with 14,904
# calls still available (run 31536402658). Scale from the proven 25/1,000 ratio,
# but stop at the pull-list API's 100-item page. If the quota cannot be read, the
# known-safe 25 remains the fallback.
REFERENCE_CORE_LIMIT = 1_000
FALLBACK_PULL_CAP = 25
MAX_PULL_CAP = 100
# Fixed overhead and worst-case marginal cost used to shrink the window when the
# live bucket is partly spent. These are deliberately pessimistic: the merge writes
# normally charge MERGE_TOKEN, not READ_TOKEN, but counting them here makes an
# admitted window affordable even on the fallback token.
FULL_SWEEP_FIXED_REQUESTS = 81
MAX_REQUESTS_PER_PULL = 19
# A 25-pull reference pass now needs 81 fixed + 25 x up-to-19 + refresh headroom =
# 536 in its pessimistic shape, so the floor funds useful work while preserving
# room for other lanes in the ordinary cheaper shape. Larger buckets do
# not need a proportionally larger dead zone: `pull_cap` shrinks to what the
# remaining requests can actually afford.
RATE_LIMIT_FLOOR = 600
# A mark-only failure wake-up costs ~4-8 calls and protects a correctness marker,
# so it has a separate small floor instead of inheriting the full-sweep floor.
MARK_ONLY_RATE_LIMIT_FLOOR = 20
# Mid-sweep reserve. It covers the in-flight pull request's remaining reads and
# writes plus the calls spendable between two budget polls, so the stop is clean
# rather than a 403 half-way through.
RATE_LIMIT_RESERVE = 120
# Poll `GET /rate_limit` every N evaluated pull requests rather than every one. It
# costs no core budget but it is still a round trip; at <=18 calls per pull request
# (proof identity, live compare, and lease bookkeeping included) the reserve above
# covers one worst-case pull while the fixed preflight and live cap bound the pass.
BUDGET_RECHECK_EVERY = 5
# Each `update-branch` is a write AND a fresh CI run on a saturated pool (36-91
# minutes, 8 self-hosted runners). The base-inherited-red path makes most of a red
# backlog eligible at once — measured 84 of 93 armed pull requests — so uncapped,
# one 46-second sweep would queue ~84 pack runs and jam CI for days. 8 drains the
# same backlog over ~11 sweeps, which at the observed sweep rate is under an hour.
MAX_REFRESHES_PER_SWEEP = 8
# A per-sweep cap is not a load cap when completed workflows wake nearly one full
# sweep per minute.  Each refreshed pull request launches one ci.yml run with 12
# hosted jobs (plus fences), and on 2026-08-11 the shared pool was already pinned at
# 180/180.  Count every active pull-request ci.yml run — ordinary session work and
# controller re-proofs alike — and add no refreshes above this repo-wide ceiling.
# Eight proof runs are roughly half the hosted pool, leaving real capacity for the
# sessions the controller exists to serve.  This is intentionally conservative:
# an ordinary in-flight proof consumes the same runners as a controller-created one.
MAX_IN_FLIGHT_PR_PROOFS = 8
HIGH_LOAD_FAIR_REFRESHES = 1
ACTIVE_PR_PROOF_STATUSES = ("queued", "in_progress", "pending", "requested", "waiting")
# The rotation advances by the live pull cap every bucket, so every armed pull
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
CI_DEFINITION_TREES = (".github/ci/",)
# Stable proof publishers remain definitions even if the commit being classified
# removed or broke their `pull_request` trigger. Dynamic gates below add future PR
# workflows; this registry preserves historical identity for the two proofs the
# merger itself consumes.
MAIN_PROOF_WORKFLOWS = ("ci.yml", "fences.yml")
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
# one source file that makes a commit not-a-bake.  The classifier therefore fails
# closed unless the commit and its first parent have identical TOP-LEVEL Git-tree
# entries everywhere except `data/` and `site/`.  Comparing root tree object IDs is
# complete even for a 10,000-file bake: a change anywhere below a root changes that
# root's tree ID, while an unchanged source root is cryptographic proof that none of
# its descendants moved.
COMMIT_FILES_TRUNCATED_AT = 300
# `/pulls/{n}/files` pages, 100 each. A pull request bigger than this has a footprint
# we cannot fully see, and an UNDER-read footprint under-detects, so it is re-proven.
PR_FILE_PAGE_CAP = 3
OPEN_PULL_PAGE_CAP = 10


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


def is_actions_check(run: dict[str, Any]) -> bool:
    return str(((run.get("app") or {}).get("slug")) or "").lower() == "github-actions"


def proof_anchor_runs(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Newest repository-owned proof check for each anchor name.

    GitHub's check-runs endpoint normally applies ``filter=latest`` already, but
    choosing by id here keeps a rerun deterministic if an API/client ever returns
    both attempts.
    """
    anchors: dict[str, dict[str, Any]] = {}
    wanted = REQUIRED_CI_ANCHORS | {REQUIRED_FENCE_ANCHOR} | REQUIRED_FORK_FENCE_ANCHORS
    for run in runs:
        name = str(run.get("name") or "")
        if name not in wanted or not is_actions_check(run):
            continue
        previous = anchors.get(name)
        if previous is None or int(run.get("id") or 0) >= int(previous.get("id") or 0):
            anchors[name] = run
    return anchors


def proof_anchor_verdict(runs: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Affirmative CI/fence proof state for the exact head.

    ``clean`` requires all twelve CI packs plus either the same-repository
    ``fence-pack`` or all three fork fence contexts to have succeeded.  Missing,
    skipped, neutral or cancelled anchors are incomplete evidence, never a pass
    and never a code accusation.
    """
    anchors = proof_anchor_runs(runs)
    required = set(REQUIRED_CI_ANCHORS)
    standard_fence = anchors.get(REQUIRED_FENCE_ANCHOR)
    fork_fences_present = REQUIRED_FORK_FENCE_ANCHORS <= anchors.keys()
    if standard_fence is not None and (
        standard_fence.get("conclusion") != "skipped" or not fork_fences_present
    ):
        required.add(REQUIRED_FENCE_ANCHOR)
    elif fork_fences_present:
        required.update(REQUIRED_FORK_FENCE_ANCHORS)
    else:
        required.add(REQUIRED_FENCE_ANCHOR)

    missing = sorted(required - anchors.keys())
    if missing:
        return "incomplete", missing
    pending = sorted(
        name for name in required if anchors[name].get("status") != "completed"
    )
    if pending:
        return "pending", pending
    bad = sorted(
        f"{name} ({anchors[name].get('conclusion')})"
        for name in required
        if anchors[name].get("conclusion")
        not in ({"success"} | CLEAN_CONCLUSIONS | INCOMPLETE_CONCLUSIONS)
    )
    if bad:
        return "blocked", bad
    incomplete = sorted(
        name
        for name in required
        if anchors[name].get("conclusion") != "success"
    )
    if incomplete:
        return "incomplete", incomplete
    return "clean", sorted(required)


def proof_anchor_work_is_active(runs: list[dict[str, Any]]) -> bool:
    """Whether any repository proof anchor is still actively executing."""
    return any(
        run.get("status") != "completed"
        for run in proof_anchor_runs(runs).values()
    )


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
    incomplete = [
        str(run.get("name") or "unnamed check")
        for run in considered
        if str(run.get("conclusion") or "").lower() in INCOMPLETE_CONCLUSIONS
    ]
    if incomplete:
        return "incomplete", incomplete
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
    # This cannot block an ordinary path-filtered PR, and that argument survived the
    # dynamic-matrix conversion (2026-08-11) — but it now rests on a DIFFERENT job,
    # so read it as rewritten rather than as unchanged. ci.yml is still `paths:`-
    # filtered at the WORKFLOW level, so a non-matching PR gets no run at all and was
    # already `unproven` before this line existed. What changed is inside the run.
    # `ci-pack`'s only job-level `if:` used to be `action != 'closed'`, true for every
    # event that opens or updates a pull request, so all twelve packs launched on
    # every head and a head with real packs necessarily carried real successes. It now
    # ALSO carries `needs.ci-plan.outputs.has_work == 'true'`, so a PR whose changed
    # paths select no legacy job publishes NO pack success at all — under the old
    # argument that head would be permanently `unproven`, which would make the no-work
    # fast path the one shape that can never merge.
    #
    # `ci-gate` IS THE ANCHOR that replaces the pack. `ci-plan` runs on every
    # non-closed event, and `ci-gate` is `if: always() && action != 'closed'` with
    # `needs: [ci-plan, ci-pack]`, so both publish a real conclusion whatever the
    # matrix did — and on the no-work path `ci-gate` exits 0 on the planner's
    # AFFIRMATIVE proof, so it concludes `success`, not `skipped`. Every head CI
    # actually looked at therefore carries at least one genuine pass, pack or no pack.
    # A mixed head (one selected pack green beside a path-skipped one) still reads
    # `clean`, and a head publishing only a SUBSET of `ci-pack-*` is clean on that
    # subset: an unselected pack is ABSENT, not failing, and nothing below enumerates
    # the names it expects to see. Pinned in `tests/test_merge_on_green.py` under
    # "the DYNAMIC pack matrix (Wave B)".
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
    total = 0
    for page in range(1, CHECK_RUN_PAGE_CAP + 1):
        query = urllib.parse.urlencode(
            {"per_page": "100", "page": str(page), "filter": "latest"}
        )
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
    if total > len(runs):
        raise RuntimeError(
            f"check-run listing for {head_sha[:12]} was truncated at {len(runs)} "
            f"of {total}; refusing to judge a hidden tail"
        )
    return runs


# ── the tested-surface gate ──────────────────────────────────────────────────


def _parse_dt(value: Any) -> dt.datetime | None:
    """GitHub's timestamp as a TZ-AWARE datetime. None when unusable.

    A naive value is normalised to UTC: GitHub always sends UTC (``...Z``), and
    silently interpreting a hypothetical missing offset in the runner's local zone
    would skew the main-baseline age comparison.
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

    Unreadable CONTENT after an exact base is known is ``True`` — re-prove. An
    unreadable proof identity is ``None`` — defer without mutation, because changing
    a branch cannot repair missing control-plane evidence. A surface that silently
    resolves to "nothing changed" would turn the gate into a no-op that reviews as
    protection, which is the single worst outcome available here.
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
        # A workflow changes the PR proof only when it actually runs on pull
        # requests. Dispatch-only/render/publisher workflow edits do not change
        # what a PR's green means and must not send the entire queue through CI
        # again. `load_pr_gates` is the source of truth, so a future PR workflow
        # joins this set automatically.
        self.ci_definition_files = {
            f".github/workflows/{name}"
            for gate in gates
            if (name := str(gate.get("workflow") or ""))
        } | {
            f".github/workflows/{name}" for name in MAIN_PROOF_WORKFLOWS
        }
        # Newest first, as GitHub returns them.
        self.commits = commits
        self._commit_files: dict[str, tuple[list[str], bool]] = {}
        self._commit_tree_shas: dict[str, str] = {}
        self._root_trees: dict[str, dict[str, tuple[str, str, str]]] = {}
        self._pr_files: dict[Any, list[str] | None] = {}
        # Exact checked head -> newest main commit already contained by that head.
        # This is a compatibility fallback for older/external check records that do
        # not expose the exact pull_request base SHA used by the primary path below.
        self._merge_bases: dict[str, str | None] = {}
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
            if not sha:
                raise RuntimeError("main commit listing contains an entry with no SHA")
            commits.append({"sha": sha})
        if not commits:
            # Unreachable against a real repository, and permitting it would hand
            # the gate a free "main never moved" for every pull request.
            raise RuntimeError("main commit listing came back empty")
        return cls(repo, token, gates, commits)

    # -- reads ----------------------------------------------------------------

    @property
    def snapshot_tip(self) -> str:
        """Exact main tip whose timeline this instance classified."""
        return str((self.commits[0] if self.commits else {}).get("sha") or "")

    def _root_tree(self, tree_sha: str) -> dict[str, tuple[str, str, str]]:
        """Complete top-level tree entries keyed by path, cached by tree object ID.

        This deliberately does NOT request ``recursive=1``.  The proof only needs
        to know which top-level subtrees changed, and the non-recursive response is
        small enough that GitHub's recursive-tree truncation limit is irrelevant.
        """
        cached = self._root_trees.get(tree_sha)
        if cached is not None:
            return cached
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{self.repo}/git/trees/{tree_sha}",
            self.token,
        )
        if status >= 400 or not isinstance(payload, dict):
            raise _read_failed(status, payload, f"root tree {tree_sha[:12]} unreadable")
        if payload.get("truncated") is True:
            raise RuntimeError(f"root tree {tree_sha[:12]} was truncated")
        entries: dict[str, tuple[str, str, str]] = {}
        for raw in payload.get("tree") or []:
            entry = raw or {}
            path = str(entry.get("path") or "")
            if not path:
                continue
            entries[path] = (
                str(entry.get("type") or ""),
                str(entry.get("mode") or ""),
                str(entry.get("sha") or ""),
            )
        if not entries:
            raise RuntimeError(f"root tree {tree_sha[:12]} had no usable entries")
        self._root_trees[tree_sha] = entries
        return entries

    def _commit_tree_sha(self, commit_sha: str) -> str:
        cached = self._commit_tree_shas.get(commit_sha)
        if cached:
            return cached
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{self.repo}/git/commits/{commit_sha}",
            self.token,
        )
        if status >= 400 or not isinstance(payload, dict):
            raise _read_failed(
                status, payload, f"git commit {commit_sha[:12]} unreadable"
            )
        tree_sha = str(((payload.get("tree") or {}).get("sha")) or "")
        if not tree_sha:
            raise RuntimeError(f"git commit {commit_sha[:12]} has no root tree")
        self._commit_tree_shas[commit_sha] = tree_sha
        return tree_sha

    def _truncated_pipeline_paths(
        self, sha: str, payload: dict[str, Any]
    ) -> list[str] | None:
        """Prove a truncated commit changed only complete pipeline subtrees.

        ``None`` means the proof could not be made and the caller must keep the
        commit truncated/fail-closed.  Synthetic paths are sufficient downstream:
        their only role is to enter the existing all-in-PIPELINE_TREES branch.
        """
        current_tree = str(
            ((((payload.get("commit") or {}).get("tree")) or {}).get("sha")) or ""
        )
        parents = payload.get("parents") or []
        parent_sha = str(((parents[0] if parents else {}) or {}).get("sha") or "")
        if not current_tree or not parent_sha:
            return None
        self._commit_tree_shas[sha] = current_tree
        try:
            parent_tree = self._commit_tree_sha(parent_sha)
            current_entries = self._root_tree(current_tree)
            parent_entries = self._root_tree(parent_tree)
        except RuntimeError:
            return None

        changed_roots = {
            path
            for path in current_entries.keys() | parent_entries.keys()
            if current_entries.get(path) != parent_entries.get(path)
        }
        pipeline_roots = {prefix.rstrip("/") for prefix in PIPELINE_TREES}
        if not changed_roots or not changed_roots <= pipeline_roots:
            return None
        # A pipeline root may be added/deleted, but whenever it exists it must still
        # be a tree. A tree-to-blob replacement named `data` is not `data/**`.
        for root in changed_roots:
            for entry in (parent_entries.get(root), current_entries.get(root)):
                if entry is not None and entry[0] != "tree":
                    return None
        return [f"{root}/__bulk_pipeline_tree__" for root in sorted(changed_roots)]

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
        names = [name for name in files if name]
        truncated = len(files) >= COMMIT_FILES_TRUNCATED_AT
        if truncated:
            proven_pipeline_paths = self._truncated_pipeline_paths(sha, payload)
            if proven_pipeline_paths is not None:
                names = proven_pipeline_paths
                truncated = False
        answer = (names, truncated)
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

    def included_main_base(self, pull: dict[str, Any]) -> str | None:
        """Newest snapshot-main commit already contained by the exact checked head.

        The primary proof identity comes directly from each check run's immutable
        pull-request event metadata. This compare exists only as a compatibility
        path: when that metadata is absent, affirmative containment of the ENTIRE
        frozen main tip is strong enough to accept the proof. Any older merge base,
        unreadable response, or incomplete payload returns ``None`` to the caller,
        which defers without updating the branch.
        """
        head_sha = str((pull.get("head") or {}).get("sha") or "")
        if not head_sha:
            return None
        if head_sha in self._merge_bases:
            return self._merge_bases[head_sha]

        snapshot_tip = self.snapshot_tip
        if not snapshot_tip:
            self._merge_bases[head_sha] = None
            return None
        encoded_tip = urllib.parse.quote(snapshot_tip, safe="")
        encoded_head = urllib.parse.quote(head_sha, safe="")
        try:
            status, payload = _request(
                "GET",
                f"{GITHUB_API}/repos/{self.repo}/compare/"
                f"{encoded_tip}...{encoded_head}?per_page=1",
                self.token,
            )
        except Exception:
            answer = None
        else:
            answer = None
            if status < 400 and isinstance(payload, dict):
                candidate = str(
                    ((payload.get("merge_base_commit") or {}).get("sha")) or ""
                )
                answer = candidate or None
        self._merge_bases[head_sha] = answer
        return answer

    def exact_proof_base(
        self, pull: dict[str, Any], runs: list[dict[str, Any]]
    ) -> tuple[str | None, str]:
        """Exact main SHA the current head's GitHub Actions proof tested.

        A ``pull_request`` check run already carries the immutable event identity
        needed here: ``pull_requests[].base.sha`` beside the exact PR number and
        head SHA.  That is strictly stronger than inferring the base from job start
        times.  In particular, runner queue time can never make a SHA ambiguous.

        Every non-spurious GitHub Actions run must agree.  Missing, mismatched or
        contradictory metadata is *indeterminate*, not stale: changing the branch
        cannot repair a control-plane read, and treating one as staleness recreates
        the self-reproof loop this controller exists to end.
        """
        number = str(pull.get("number") or "")
        head_sha = str((pull.get("head") or {}).get("sha") or "").lower()
        if not number or not head_sha:
            return None, "the pull request has no exact number/head identity"

        bases: set[str] = set()
        anchors = proof_anchor_runs(runs)
        for run in anchors.values():
            matches: set[str] = set()
            associations = run.get("pull_requests")
            if not isinstance(associations, list):
                return None, (
                    f"GitHub Actions check {str(run.get('name') or '?')!r} has no "
                    "pull-request base metadata"
                )
            for raw in associations:
                association = raw or {}
                associated_number = str(association.get("number") or "")
                associated_head = str(
                    ((association.get("head") or {}).get("sha")) or ""
                ).lower()
                base_sha = str(
                    ((association.get("base") or {}).get("sha")) or ""
                ).lower()
                if associated_number == number and associated_head == head_sha and base_sha:
                    matches.add(base_sha)
            if len(matches) != 1:
                return None, (
                    f"GitHub Actions check {str(run.get('name') or '?')!r} does not "
                    f"identify exactly one base for PR #{number} at {head_sha[:12]}"
                )
            bases.update(matches)

        if not anchors:
            return None, "no repository-owned proof anchor identifies the proof base"
        if not bases:
            return None, "the repository-owned proof anchors expose no base SHA"
        # A rerun can legitimately carry a newer base while older anchors on the
        # unchanged head retain their original event base.  The oldest base visible
        # in the frozen main timeline is the conservative authority: classifying
        # every commit after it can only request extra proof, never skip a change.
        positions = {
            str(commit.get("sha") or "").lower(): index
            for index, commit in enumerate(self.commits)
        }
        visible = [(positions[base], base) for base in bases if base in positions]
        if len(visible) == len(bases):
            _index, oldest = max(visible)
            detail = (
                ""
                if len(bases) == 1
                else "proof anchors reported multiple ancestry-ordered bases; "
                "using the oldest conservatively"
            )
            return oldest, detail
        if visible:
            shown = ", ".join(sorted(base[:12] for base in bases if base not in positions))
            return None, (
                "proof anchors mix a visible base with base(s) outside the frozen "
                f"main window ({shown}); their ancestry cannot be ordered safely"
            )
        if len(bases) == 1:
            return next(iter(bases)), "proof base predates the frozen main window"
        shown = ", ".join(sorted(base[:12] for base in bases))
        return None, f"proof anchor base(s) lie outside the frozen main window ({shown})"

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

    def stale_for(
        self, pull: dict[str, Any], runs: list[dict[str, Any]]
    ) -> tuple[bool | None, str]:
        """Freshness verdict for one clean head.

        ``True`` means an affirmative base/content change requires re-proof;
        ``False`` means the exact proof is current; ``None`` means the proof base
        cannot be established and the caller must defer without mutating the head.
        """
        number = pull.get("number")
        proof_base, metadata_problem = self.exact_proof_base(pull, runs)
        if proof_base:
            for index, commit in enumerate(self.commits):
                if str(commit.get("sha") or "").lower() != proof_base:
                    continue
                window = self.commits[:index]
                if not window:
                    return False, (
                        f"the exact checked proof base is the frozen main tip "
                        f"{proof_base[:12]}"
                    )
                break
            else:
                return True, (
                    f"the exact checked proof base {proof_base[:12]} predates or is "
                    f"outside the newest {len(self.commits)} main commits this sweep "
                    "can classify"
                )
        else:
            # Compatibility fallback: a check on exact head H necessarily includes
            # every ancestor of H.  The merge base between frozen main and H is
            # therefore a conservative lower bound even when Actions omitted event
            # metadata: classify *all* main commits after it.  This may request one
            # extra update, but once that update is in H it cannot self-invalidate
            # again.  An unreadable/out-of-window ancestry answer still defers.
            included_base = self.included_main_base(pull)
            if included_base:
                for index, commit in enumerate(self.commits):
                    if str(commit.get("sha") or "").lower() != included_base.lower():
                        continue
                    window = self.commits[:index]
                    if not window:
                        return False, (
                            "the exact checked head contains the frozen main tip "
                            f"{included_base[:12]} despite unavailable proof metadata"
                        )
                    break
                else:
                    return None, (
                        metadata_problem
                        + f"; conservative merge base {included_base[:12]} is outside "
                        "the frozen main window"
                    )
            else:
                return None, metadata_problem + "; head ancestry could not be established"

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
            if any(
                name.startswith(CI_DEFINITION_TREES)
                or name in self.ci_definition_files
                for name in files
            ):
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

    Discovery is paginated independently of the evaluation cap.  Otherwise an
    older armed pull request beyond the first 100 open pulls is invisible forever;
    wall-clock rotation cannot rotate something it never discovered.
    """
    pulls: list[dict[str, Any]] = []
    for page in range(1, OPEN_PULL_PAGE_CAP + 1):
        query = urllib.parse.urlencode(
            {"state": "open", "per_page": "100", "page": str(page)}
        )
        status, payload = _request(
            "GET", f"{GITHUB_API}/repos/{repo}/pulls?{query}", token
        )
        if status >= 400 or not isinstance(payload, list):
            raise _read_failed(status, payload, "pull-request listing failed")
        pulls.extend(pull for pull in payload if isinstance(pull, dict))
        if len(payload) < 100:
            break
    else:
        raise RuntimeError(
            f"open pull discovery reached its {OPEN_PULL_PAGE_CAP * 100}-pull safety "
            "cap; refusing a permanently truncated queue"
        )
    return [pull for pull in pulls if MERGE_ON_GREEN_LABEL in label_names(pull)]


def is_sweep_candidate(pull: dict[str, Any]) -> bool:
    """Static authorization shape for an armed merge candidate."""
    return (
        str(pull.get("state") or "open").lower() == "open"
        and pull.get("draft") is not True
        and str(((pull.get("base") or {}).get("ref")) or "main") == "main"
        and MERGE_ON_GREEN_LABEL in label_names(pull)
    )


def in_flight_pr_proofs(repo: str, token: str) -> int | None:
    """Repo-wide active pull-request ``ci.yml`` runs, or ``None`` if unreadable.

    This is the controller's workload circuit breaker.  A per-sweep refresh cap
    does not bound anything when green workflow completions start another sweep
    every minute; active Actions runs are the durable state shared by those sweeps.
    Five tiny ``per_page=1`` reads use GitHub's own status index and ``total_count``
    so proofs outside the pull-list/evaluation window still consume capacity.

    Unreadable is deliberately ``None`` rather than zero.  The caller pauses only
    NEW ``update-branch`` work while continuing to judge and merge already-proven
    heads; an API blip must not be interpreted as an empty runner pool.
    """
    total = 0
    for run_status in ACTIVE_PR_PROOF_STATUSES:
        query = urllib.parse.urlencode(
            {
                "event": "pull_request",
                "status": run_status,
                "per_page": "1",
            }
        )
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/actions/workflows/ci.yml/runs?{query}",
            token,
        )
        count = (payload or {}).get("total_count") if isinstance(payload, dict) else None
        if (
            status >= 400
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            return None
        total += count
    return total


def refresh_lease_reservation_count(
    repo: str,
    token: str,
    lease: "RefreshLease",
    pulls: list[dict[str, Any]],
) -> int:
    """Unindexed controller workload represented only by the durable lease.

    The global Actions census already counts an owner's current ``ci.yml`` run as
    soon as GitHub registers it.  Counting the same workload again as a durable
    reservation underfills the eight-proof pool for the entire 30-90 minute run:
    seven real proofs plus one double-counted owner looked full in production.

    Keep the reservation only across the actual update-branch -> Actions indexing
    gap.  An unreadable or malformed run lookup is conservatively unindexed.  Once
    an exact-current-head CI run is visible, its queued/in-progress state is already
    in :func:`in_flight_pr_proofs`; a completed run consumes no hosted capacity and
    the ordinary owner reconciliation releases the lease later in this sweep.
    """
    if lease.owner_number is None:
        return 0
    owner = next(
        (pull for pull in pulls if str(pull.get("number")) == str(lease.owner_number)),
        None,
    )
    current_head = str((((owner or {}).get("head") or {}).get("sha")) or "").lower()
    generation_head = str(lease.generation_head_sha or "").lower()
    if (
        len(current_head) != 40
        or len(generation_head) != 40
        or current_head == generation_head
    ):
        return 1

    query = urllib.parse.urlencode(
        {
            "event": "pull_request",
            "head_sha": current_head,
            "per_page": "1",
        }
    )
    try:
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/actions/workflows/ci.yml/runs?{query}",
            token,
        )
    except Exception:
        return 1
    runs = (payload or {}).get("workflow_runs") if isinstance(payload, dict) else None
    count = (payload or {}).get("total_count") if isinstance(payload, dict) else None
    if (
        status >= 400
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or not isinstance(runs, list)
    ):
        return 1
    if count == 0 or not runs:
        return 1
    observed_head = str(((runs[0] or {}).get("head_sha")) or "").lower()
    return 0 if observed_head == current_head else 1


def serialized_refresh_authority(
    repo: str, token: str, current_run_id: str, trigger_conclusion: str
) -> bool:
    """Affirm that branch refreshes run only inside the serialized sweep lane.

    The durable label and its description are safety fences, not a compare-and-swap
    primitive. Mutual exclusion therefore comes from the workflow's job-level
    ``sweep`` concurrency group. Refusing mutation outside the exact in-progress
    default-branch workflow run turns that orchestration contract into an explicit
    code boundary instead of an assumption an out-of-band caller can bypass.
    """
    if not current_run_id.isdigit() or trigger_conclusion not in {"", "success"}:
        return False
    try:
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/actions/runs/{current_run_id}",
            token,
        )
    except Exception:
        return False
    repository = (payload or {}).get("repository") if isinstance(payload, dict) else {}
    return bool(
        status == 200
        and isinstance(payload, dict)
        and str(payload.get("id") or "") == current_run_id
        and str(payload.get("status") or "") == "in_progress"
        and str(payload.get("path") or "") == ".github/workflows/merge-on-green.yml"
        and str(payload.get("head_branch") or "") == "main"
        and str((repository or {}).get("full_name") or "") == repo
        and str(payload.get("event") or "")
        in {"workflow_run", "schedule", "workflow_dispatch"}
    )


def _set_local_label(payload: dict[str, Any], name: str, present: bool) -> None:
    """Keep an already-read issue/PR payload coherent after a label write."""
    labels = list(payload.get("labels") or [])
    labels = [label for label in labels if str((label or {}).get("name") or "") != name]
    if present:
        labels.append({"name": name})
    payload["labels"] = labels


def open_refresh_lease_issues(repo: str, token: str) -> list[dict[str, Any]] | None:
    """Open pull-request issues carrying the controller's durable refresh lease.

    The issues endpoint can filter by label and, unlike the one-page pull listing,
    cannot silently hide an older owner behind 100 newer pull requests. Closed
    pull requests are intentionally absent: a closed owner cannot consume the live
    lane, and successful merge cleanup removes the cosmetic label best-effort.
    """
    query = urllib.parse.urlencode(
        {"state": "open", "labels": REFRESH_LEASE_LABEL, "per_page": "100"}
    )
    status, payload = _request(
        "GET", f"{GITHUB_API}/repos/{repo}/issues?{query}", token
    )
    if status >= 400 or not isinstance(payload, list):
        return None
    return [issue for issue in payload if isinstance(issue, dict) and issue.get("pull_request")]


def _remove_refresh_lease_label(repo: str, number: Any, token: str) -> bool:
    """Delete one durable lease label; an already-absent label is success."""
    encoded = urllib.parse.quote(REFRESH_LEASE_LABEL, safe="")
    try:
        status, _ = _request(
            "DELETE",
            f"{GITHUB_API}/repos/{repo}/issues/{number}/labels/{encoded}",
            token,
        )
    except Exception as exc:
        _annotate(
            "error",
            "merge-on-green refresh lease",
            f"PR #{number}: could not release `{REFRESH_LEASE_LABEL}` ({exc}).",
        )
        return False
    if status in {200, 204, 404}:
        return True
    _annotate(
        "error",
        "merge-on-green refresh lease",
        f"PR #{number}: could not release `{REFRESH_LEASE_LABEL}` (HTTP {status}).",
    )
    return False


def refresh_lease_acquired_at(repo: str, number: Any, token: str) -> str:
    """Timestamp of the newest lease-label event, when GitHub exposes it.

    Only serialized full sweeps mutate the lease, so this is a watchdog clock—not
    a concurrency generation fence.  Issue ``updated_at`` is intentionally not
    authority because comments and unrelated labels mutate it.
    """
    query = urllib.parse.urlencode({"per_page": "100"})
    try:
        status, events = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/issues/{number}/events?{query}",
            token,
        )
    except Exception:
        return ""
    if status >= 400 or not isinstance(events, list):
        return ""
    matches = [
        str(event.get("created_at") or "")
        for event in events
        if isinstance(event, dict)
        and str(event.get("event") or "") == "labeled"
        and str(((event.get("label") or {}).get("name")) or "") == REFRESH_LEASE_LABEL
    ]
    return matches[-1] if matches else ""


def refresh_lease_record(
    number: Any,
    head_sha: str,
    acquired_at: str | None = None,
    generation_id: str | None = None,
) -> str:
    """Encode the workload generation in the repository label description.

    A label on its own identifies only a pull request.  It cannot distinguish the
    already-green pre-update head from the new head whose proof the controller paid
    to launch.  The description is the durable generation record shared by later
    sweeps: owner, exact pre-update head, and acquisition time.  It stays below
    GitHub's 100-character label-description limit.
    """
    parsed_when = _parse_dt(acquired_at) if acquired_at else dt.datetime.now(dt.timezone.utc)
    if parsed_when is None:
        raise ValueError("refresh lease acquisition time is invalid")
    epoch = int(parsed_when.timestamp())
    generation = generation_id or secrets.token_hex(6)
    return (
        f"{REFRESH_LEASE_RECORD_PREFIX} p={int(number)} "
        f"h={str(head_sha).lower()} t={epoch} g={generation}"
    )


def parse_refresh_lease_record(description: Any) -> tuple[int, str, str, str] | None:
    """Decode a generation record, rejecting partial or manually edited state."""
    parts = str(description or "").split()
    if len(parts) != 5 or parts[0] != REFRESH_LEASE_RECORD_PREFIX:
        return None
    fields: dict[str, str] = {}
    for part in parts[1:]:
        key, separator, value = part.partition("=")
        if not separator or not key or not value:
            return None
        fields[key] = value
    raw_number = fields.get("p", "")
    head_sha = fields.get("h", "").lower()
    raw_epoch = fields.get("t", "")
    generation_id = fields.get("g", "").lower()
    if (
        not raw_number.isdigit()
        or len(head_sha) != 40
        or any(character not in "0123456789abcdef" for character in head_sha)
        or not raw_epoch.isdigit()
        or len(generation_id) != 12
        or any(character not in "0123456789abcdef" for character in generation_id)
    ):
        return None
    try:
        acquired_at = dt.datetime.fromtimestamp(
            int(raw_epoch), tz=dt.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None
    return int(raw_number), head_sha, acquired_at, generation_id


def read_refresh_lease_record(
    repo: str, token: str
) -> tuple[int, str, str, str] | None:
    """Read the single repository-scoped generation register."""
    readable, record = read_refresh_lease_register(repo, token)
    return record if readable else None


def read_refresh_lease_register(
    repo: str, token: str
) -> tuple[bool, tuple[int, str, str, str] | None]:
    """Read ``(authoritative, record)`` without conflating absence and outage."""
    encoded = urllib.parse.quote(REFRESH_LEASE_LABEL, safe="")
    try:
        status, payload = _request(
            "GET", f"{GITHUB_API}/repos/{repo}/labels/{encoded}", token
        )
    except Exception:
        return False, None
    if status == 404:
        return True, None
    if status != 200 or not isinstance(payload, dict):
        return False, None
    description = str(payload.get("description") or "")
    if description == REFRESH_LEASE_DESCRIPTION:
        return True, None
    record = parse_refresh_lease_record(description)
    return (record is not None), record


class RefreshLease:
    """Durable owner of the single controller refresh allowed under saturation.

    The job-level ``sweep`` concurrency group serialises full controllers. The
    GitHub label carries that ownership across runs and across the seconds between
    ``update-branch`` accepting a write and Actions registering the new proof. A
    failed/ambiguous claim never authorises the write: a later sweep first observes
    the durable label and decides from live state.
    """

    def __init__(
        self,
        repo: str,
        read_token: str,
        write_token: str,
        *,
        owner_number: Any = None,
        owner_updated_at: str = "",
        generation_head_sha: str = "",
        generation_id: str = "",
        readable: bool = True,
    ) -> None:
        self.repo = repo
        self.read_token = read_token
        self.write_token = write_token
        self.owner_number = int(owner_number) if str(owner_number or "").isdigit() else None
        self.owner_acquired_at = owner_updated_at
        self.generation_head_sha = str(generation_head_sha or "").lower()
        self.generation_id = str(generation_id or "").lower()
        self.readable = readable
        self.claim_attempted = False
        self.released_numbers: set[int] = set()
        self._label_ready: bool | None = None

    @property
    def generation_record(self) -> tuple[int, str, str, str] | None:
        if (
            self.owner_number is None
            or not self.generation_head_sha
            or not self.owner_acquired_at
            or not self.generation_id
        ):
            return None
        return (
            self.owner_number,
            self.generation_head_sha,
            self.owner_acquired_at,
            self.generation_id,
        )

    def record_is_current(self) -> bool:
        expected = self.generation_record
        return expected is not None and read_refresh_lease_record(
            self.repo, self.read_token
        ) == expected

    def owns(self, pull: dict[str, Any]) -> bool:
        number = pull.get("number")
        return self.owner_number is not None and str(number) == str(self.owner_number)

    def owner_is_old(self, *, now: float | None = None) -> bool:
        parsed = _parse_dt(self.owner_acquired_at)
        if parsed is None:
            return True
        stamp = parsed.timestamp()
        current = time.time() if now is None else now
        # A client-written future time must not create an immortal reservation.
        # Server label-event time replaces it when available; absent that evidence,
        # an impossible clock is treated as expired and rebuilt fail-closed.
        if stamp > current + SELF_WAKE_MIN_INTERVAL_SECONDS:
            return True
        return current - stamp >= REFRESH_LEASE_GRACE_SECONDS

    def owner_exceeded_max_age(self, *, now: float | None = None) -> bool:
        parsed = _parse_dt(self.owner_acquired_at)
        if parsed is None:
            return True
        current = time.time() if now is None else now
        stamp = parsed.timestamp()
        if stamp > current + SELF_WAKE_MIN_INTERVAL_SECONDS:
            return True
        return current - stamp >= REFRESH_LEASE_MAX_SECONDS

    def _write_generation_record(self, number: Any, head_sha: str) -> bool:
        """Create/update and affirm the exact generation before claiming.

        The label definition is a repository-scoped single register.  Normal full
        sweeps are serialized, while the final read-back plus owner census makes a
        pre-deploy/manual overlap fail closed instead of authorising two writes.
        """
        acquired_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        description = refresh_lease_record(number, head_sha, acquired_at)
        encoded = urllib.parse.quote(REFRESH_LEASE_LABEL, safe="")
        try:
            status, current = _request(
                "GET", f"{GITHUB_API}/repos/{self.repo}/labels/{encoded}", self.read_token
            )
            if status == 404:
                write_status, _ = _request(
                    "POST",
                    f"{GITHUB_API}/repos/{self.repo}/labels",
                    self.write_token,
                    {
                        "name": REFRESH_LEASE_LABEL,
                        "color": REFRESH_LEASE_COLOR,
                        "description": description,
                    },
                )
            elif status == 200 and isinstance(current, dict):
                write_status, _ = _request(
                    "PATCH",
                    f"{GITHUB_API}/repos/{self.repo}/labels/{encoded}",
                    self.write_token,
                    {
                        "new_name": REFRESH_LEASE_LABEL,
                        "color": REFRESH_LEASE_COLOR,
                        "description": description,
                    },
                )
            else:
                return False
            # Every mutating response is potentially ambiguous, and 422 is also
            # validation/throttling. Only an exact read-back authorises the issue
            # label or the CI-producing update.
            verify_status, verified = _request(
                "GET", f"{GITHUB_API}/repos/{self.repo}/labels/{encoded}", self.read_token
            )
            if (
                verify_status != 200
                or not isinstance(verified, dict)
                or str(verified.get("description") or "") != description
            ):
                return False
            self._label_ready = True
            parsed = parse_refresh_lease_record(description)
            if parsed is None:
                return False
            (
                _owner,
                self.generation_head_sha,
                self.owner_acquired_at,
                self.generation_id,
            ) = parsed
            return True
        except Exception as exc:
            _annotate(
                "error",
                "merge-on-green refresh lease",
                f"Could not persist the `{REFRESH_LEASE_LABEL}` generation record "
                f"({exc}); no refresh write is authorised.",
            )
            self._label_ready = False
            return False

    def _issue_has_claim_labels(self, number: Any) -> bool:
        """Read the owner issue directly, bypassing the lagging label index."""
        try:
            status, payload = _request(
                "GET", f"{GITHUB_API}/repos/{self.repo}/issues/{number}", self.read_token
            )
        except Exception:
            return False
        labels = (
            label_names(payload)
            if status < 400 and isinstance(payload, dict)
            else set()
        )
        return {MERGE_ON_GREEN_LABEL, REFRESH_LEASE_LABEL}.issubset(labels)

    def claim(self, pull: dict[str, Any]) -> bool:
        """Claim before ``update-branch``; ambiguity fails closed."""
        number = pull.get("number")
        head_sha = str(((pull.get("head") or {}).get("sha")) or "").lower()
        if not self.readable or not number or len(head_sha) != 40:
            return False
        if str(number).isdigit() and int(number) in self.released_numbers:
            return False
        if self.owns(pull):
            # A generation may authorize exactly one update of its recorded head.
            # Once update-branch moved the live head, later sweeps only reconcile
            # that workload; they must never use the same label for a second update.
            return bool(
                self.generation_head_sha
                and head_sha == self.generation_head_sha
                and self.record_is_current()
            )
        if self.owner_number is not None or self.claim_attempted:
            return False
        # Set before any network write. A timeout may mean the server accepted it,
        # so this process must never try a different pull request afterward.
        self.claim_attempted = True
        if not self._write_generation_record(number, head_sha):
            return False
        try:
            status, _ = _request(
                "POST",
                f"{GITHUB_API}/repos/{self.repo}/issues/{number}/labels",
                self.write_token,
                {"labels": [REFRESH_LEASE_LABEL]},
            )
        except Exception:
            status = 599
        if status >= 400 and not self._issue_has_claim_labels(number):
            _annotate(
                "error",
                "merge-on-green refresh lease",
                f"PR #{number}: could not affirm `{REFRESH_LEASE_LABEL}` before "
                "update-branch; no refresh write was attempted.",
            )
            return False
        # GitHub's label-filtered issues index is eventually consistent: immediately
        # after the POST it can legitimately omit this just-confirmed owner. Prove
        # the claimant through the strongly scoped issue read, while the filtered
        # census remains responsible for finding every *other* indexed owner. The
        # exact generation register is reread below and immediately before PUT, so
        # a concurrent claimant still wins or loses fail-closed.
        claimant_affirmed = self._issue_has_claim_labels(number)
        try:
            observed = open_refresh_lease_issues(self.repo, self.read_token)
        except Exception:
            observed = None
        armed_numbers = (
            [
                int(issue.get("number"))
                for issue in observed
                if str(issue.get("number") or "").isdigit()
                and MERGE_ON_GREEN_LABEL in label_names(issue)
            ]
            if observed is not None
            else []
        )
        armed_numbers = sorted(set(armed_numbers))
        other_armed_numbers = [
            owner for owner in armed_numbers if owner != int(number)
        ]
        observed_record = read_refresh_lease_record(self.repo, self.read_token)
        intended_record = (
            int(number),
            self.generation_head_sha,
            self.owner_acquired_at,
            self.generation_id,
        )
        if (
            observed is None
            or not claimant_affirmed
            or other_armed_numbers
            or observed_record != intended_record
        ):
            # If the record changed, a newer same-PR generation may own the one
            # indistinguishable issue-label association. An old actor must never
            # delete it. If the record is still ours but the census disagrees, the
            # partial claim is ours to clean up.
            record_changed = observed_record != intended_record
            cleaned = False
            if not record_changed:
                cleaned = _remove_refresh_lease_label(
                    self.repo, number, self.write_token
                )
            if record_changed or not cleaned:
                self.readable = False
            _annotate(
                "error",
                "merge-on-green refresh lease",
                f"PR #{number}: post-claim census did not prove it is the sole "
                f"refresh owner with its exact generation record (observed "
                f"{armed_numbers if observed is not None else 'unreadable'}); no "
                "update-branch write was attempted"
                + (
                    "; the failed claimant label was removed."
                    if cleaned
                    else "; ownership changed or cleanup was ambiguous, so this "
                    "sweep retained the label and failed closed."
                ),
            )
            return False
        record_number, record_head, record_acquired_at, record_generation_id = observed_record
        self.owner_number = int(number)
        self.owner_acquired_at = record_acquired_at
        self.generation_head_sha = record_head
        self.generation_id = record_generation_id
        _set_local_label(pull, REFRESH_LEASE_LABEL, True)
        _annotate(
            "notice",
            "merge-on-green refresh lease",
            f"PR #{number}: acquired the one durable high-load refresh lease.",
        )
        return True

    def release(self, pull: dict[str, Any], reason: str) -> bool:
        """Release a definitive owner; failure leaves ownership fail-closed."""
        if not self.owns(pull) and REFRESH_LEASE_LABEL not in label_names(pull):
            return True
        number = pull.get("number")
        # A settled generation must never reacquire in this same sweep, even when
        # GitHub accepts the delete but loses the response.  Keeping owner_number on
        # an ambiguous delete prevents any different claimant too: fail closed in
        # both directions.
        if str(number).isdigit():
            self.released_numbers.add(int(number))
        if self.owns(pull) and self.generation_head_sha:
            if not self.record_is_current():
                _annotate(
                    "error",
                    "merge-on-green refresh lease",
                    f"PR #{number}: generation register changed before release; "
                    "the issue label was retained so an old sweep cannot erase a "
                    "newer reservation.",
                )
                self.readable = False
                return False
        if not _remove_refresh_lease_label(self.repo, number, self.write_token):
            return False
        _set_local_label(pull, REFRESH_LEASE_LABEL, False)
        if str(number) == str(self.owner_number):
            self.owner_number = None
            self.owner_acquired_at = ""
            self.generation_head_sha = ""
            self.generation_id = ""
        _annotate(
            "notice",
            "merge-on-green refresh lease",
            f"PR #{number}: released the refresh lease ({reason}).",
        )
        return True


def prepare_refresh_lease(
    repo: str,
    read_token: str,
    write_token: str,
    pulls: list[dict[str, Any]],
) -> tuple[RefreshLease, list[dict[str, Any]]]:
    """Load/clean the durable owner and inject it when the pull page omitted it."""
    try:
        issues = open_refresh_lease_issues(repo, read_token)
    except Exception as exc:
        _annotate(
            "error",
            "merge-on-green refresh lease",
            f"Could not census refresh leases ({exc}); high-load refreshes paused.",
        )
        return RefreshLease(repo, read_token, write_token, readable=False), pulls
    if issues is None:
        _annotate(
            "error",
            "merge-on-green refresh lease",
            "Could not census refresh leases; high-load refreshes paused.",
        )
        return RefreshLease(repo, read_token, write_token, readable=False), pulls

    # The label-filtered issues index is eventually consistent. A previous sweep's
    # accepted owner can be absent here for a few seconds even though its direct
    # issue and the exact generation register are already durable. Recover that
    # owner before any new claim may overwrite the register. This is the sequential
    # half of the serialization invariant; the workflow authority check below
    # excludes overlapping refresh writers.
    register_readable, generation = read_refresh_lease_register(repo, read_token)
    if not register_readable:
        _annotate(
            "error",
            "merge-on-green refresh lease",
            "The generation register is unreadable or malformed; high-load "
            "refreshes paused rather than assuming no prior owner.",
        )
        return RefreshLease(repo, read_token, write_token, readable=False), pulls
    if generation is not None and not any(
        str(issue.get("number")) == str(generation[0]) for issue in issues
    ):
        try:
            owner_status, owner_issue = _request(
                "GET",
                f"{GITHUB_API}/repos/{repo}/issues/{generation[0]}",
                read_token,
            )
        except Exception:
            owner_status, owner_issue = 599, None
        valid_owner_shape = bool(
            owner_status == 200
            and isinstance(owner_issue, dict)
            and str(owner_issue.get("number") or "") == str(generation[0])
            and str(owner_issue.get("state") or "") in {"open", "closed"}
            and isinstance(owner_issue.get("labels"), list)
            and owner_issue.get("pull_request")
        )
        if owner_status not in {200, 404} or (
            owner_status == 200 and not valid_owner_shape
        ):
            _annotate(
                "error",
                "merge-on-green refresh lease",
                f"Generation register points to PR #{generation[0]}, but its direct "
                "issue state is unreadable; high-load refreshes paused.",
            )
            return RefreshLease(repo, read_token, write_token, readable=False), pulls
        if (
            valid_owner_shape
            and str(owner_issue.get("state") or "") == "open"
            and REFRESH_LEASE_LABEL in label_names(owner_issue)
        ):
            issues = [owner_issue, *issues]

    armed_issues: list[dict[str, Any]] = []
    cleanup_failed = False
    for issue in issues:
        if MERGE_ON_GREEN_LABEL in label_names(issue):
            armed_issues.append(issue)
            continue
        number = issue.get("number")
        if not _remove_refresh_lease_label(repo, number, write_token):
            cleanup_failed = True
        else:
            _annotate(
                "notice",
                "merge-on-green refresh lease",
                f"PR #{number}: removed an orphan lease from a disarmed pull request.",
            )

    if len(armed_issues) > 1:
        # A label is not a CAS. A manual/pre-deploy overlap may have launched work
        # for either owner before this sweep sees both associations. Deleting either
        # one would guess which irreversible write happened, so fail closed and wait
        # for an operator or a later unambiguous lifecycle transition.
        shown = ", ".join(f"#{issue.get('number')}" for issue in armed_issues)
        if generation is not None:
            quarantine_expired = RefreshLease(
                repo,
                read_token,
                write_token,
                owner_number=generation[0],
                owner_updated_at=generation[2],
                generation_head_sha=generation[1],
                generation_id=generation[3],
            ).owner_exceeded_max_age()
        else:
            # A legacy/malformed register still gets bounded recovery, but only
            # from GitHub's server-stamped label events for EVERY association.
            event_times = [
                refresh_lease_acquired_at(repo, issue.get("number"), read_token)
                for issue in armed_issues
            ]
            quarantine_expired = bool(event_times) and all(
                stamp
                and RefreshLease(
                    repo,
                    read_token,
                    write_token,
                    owner_number=issue.get("number"),
                    owner_updated_at=stamp,
                ).owner_exceeded_max_age()
                for issue, stamp in zip(armed_issues, event_times)
            )
        if quarantine_expired:
            cleaned_all = True
            for issue in armed_issues:
                number = issue.get("number")
                cleaned_all = (
                    _remove_refresh_lease_label(repo, number, write_token)
                    and cleaned_all
                )
                for pull in pulls:
                    if str(pull.get("number")) == str(number):
                        _set_local_label(pull, REFRESH_LEASE_LABEL, False)
            if cleaned_all:
                _annotate(
                    "warning",
                    "merge-on-green refresh lease",
                    f"Expired duplicate-owner quarantine ({shown}) exceeded the "
                    f"{REFRESH_LEASE_MAX_SECONDS // 3600}-hour hard bound; removed "
                    "all associations so the next candidate can create a freshly "
                    "fenced generation.",
                )
                return RefreshLease(repo, read_token, write_token), pulls
        _annotate(
            "error",
            "merge-on-green refresh lease",
            f"Multiple refresh owners exist ({shown}); generation register points "
            f"to #{generation[0] if generation is not None else 'unreadable'}. "
            "No label or branch is mutated because prior update disposition is "
            "ambiguous.",
        )
        return RefreshLease(repo, read_token, write_token, readable=False), pulls
    if cleanup_failed:
        return RefreshLease(repo, read_token, write_token, readable=False), pulls
    if not armed_issues:
        return RefreshLease(repo, read_token, write_token), pulls

    issue = armed_issues[0]
    number = issue.get("number")
    owner = next((pull for pull in pulls if str(pull.get("number")) == str(number)), None)
    if owner is None:
        try:
            status, payload = _request(
                "GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}", read_token
            )
        except Exception:
            status, payload = 599, None
        if status >= 400 or not isinstance(payload, dict):
            _annotate(
                "error",
                "merge-on-green refresh lease",
                f"PR #{number}: lease owner was outside the pull page and could not "
                "be read; high-load refreshes paused.",
            )
            return RefreshLease(repo, read_token, write_token, readable=False), pulls
        owner = payload
        if not is_sweep_candidate(owner):
            if _remove_refresh_lease_label(repo, number, write_token):
                return RefreshLease(repo, read_token, write_token), pulls
            return RefreshLease(repo, read_token, write_token, readable=False), pulls
        pulls = [owner, *pulls]
    elif not is_sweep_candidate(owner):
        if _remove_refresh_lease_label(repo, number, write_token):
            pulls = [pull for pull in pulls if str(pull.get("number")) != str(number)]
            return RefreshLease(repo, read_token, write_token), pulls
        return RefreshLease(repo, read_token, write_token, readable=False), pulls
    _set_local_label(owner, REFRESH_LEASE_LABEL, True)
    acquired_at = refresh_lease_acquired_at(repo, number, read_token)
    generation_head_sha = ""
    generation_id = ""
    if generation is not None and str(generation[0]) == str(number):
        (
            _record_number,
            generation_head_sha,
            record_acquired_at,
            generation_id,
        ) = generation
        acquired_at = record_acquired_at
    else:
        _annotate(
            "warning",
            "merge-on-green refresh lease",
            f"PR #{number}: existing lease has no valid generation record. It will "
            "be retained through the grace period, then released and re-created "
            "before any new refresh write.",
        )
    return (
        RefreshLease(
            repo,
            read_token,
            write_token,
            owner_number=number,
            owner_updated_at=acquired_at or str(issue.get("updated_at") or ""),
            generation_head_sha=generation_head_sha,
            generation_id=generation_id,
        ),
        pulls,
    )


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


def pull_cap_for_limit(limit: Any) -> int:
    """Pull requests a full sweep may inspect under an API core limit.

    The 25-at-1,000 baseline is measured production behavior, not a guessed
    request cost. Scaling that ratio preserves the old budget share after an
    account-tier change; the 100 ceiling matches the single pull-list page and
    keeps one reconciliation bounded. An unreadable or malformed limit falls
    back to the known-safe baseline.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        return FALLBACK_PULL_CAP
    return min(
        MAX_PULL_CAP,
        max(FALLBACK_PULL_CAP, limit * FALLBACK_PULL_CAP // REFERENCE_CORE_LIMIT),
    )


def pull_cap_for_budget(
    remaining: Any,
    limit: Any,
    *,
    reserve: int = RATE_LIMIT_RESERVE,
    max_refreshes: int = MAX_REFRESHES_PER_SWEEP,
) -> int:
    """Quota-scaled cap narrowed to what the remaining bucket can afford."""
    quota_cap = pull_cap_for_limit(limit)
    if not isinstance(remaining, int) or isinstance(remaining, bool):
        return quota_cap
    spendable = (
        remaining - reserve - FULL_SWEEP_FIXED_REQUESTS - max_refreshes
    )
    affordable = max(1, spendable // MAX_REQUESTS_PER_PULL)
    return min(quota_cap, affordable)


class SweepBudget:
    """How much API budget this sweep may spend, asked repeatedly as it spends it.

    One object per sweep. Four questions, four answers:

      `preflight()`   — may this sweep start at all?
      `pull_cap`      — how wide may this live-quota sweep be?
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
        mark_only_floor: int = MARK_ONLY_RATE_LIMIT_FLOOR,
        reserve: int = RATE_LIMIT_RESERVE,
        recheck_every: int = BUDGET_RECHECK_EVERY,
        max_refreshes: int = MAX_REFRESHES_PER_SWEEP,
    ) -> None:
        self.token = token
        self.floor = floor
        self.mark_only_floor = mark_only_floor
        self.reserve = reserve
        self.recheck_every = max(1, recheck_every)
        self.max_refreshes = max_refreshes
        self.refreshes_used = 0
        self.refresh_context = ""
        self.refresh_lease: RefreshLease | None = None
        self.requires_refresh_lease = False
        self.refresh_authorized = False
        self.observed_anchor_states: dict[Any, str] = {}
        self.polls = 0
        self.last_seen: int | None = None
        self.last_limit: int | None = None

    def _poll(self) -> tuple[int, int] | None:
        reading = core_rate_limit(self.token)
        self.polls += 1
        if reading is not None:
            self.last_seen, self.last_limit = reading
        return reading

    @property
    def pull_cap(self) -> int:
        """The current full-sweep window, safe-fallback when quota is unreadable."""
        return pull_cap_for_budget(
            self.last_seen,
            self.last_limit,
            reserve=self.reserve,
            max_refreshes=self.max_refreshes,
        )

    def preflight(self, *, mark_only: bool = False) -> tuple[bool, str]:
        """``(may_sweep, detail)``. False means defer — exit 0, not a red run."""
        reading = self._poll()
        if reading is None:
            return True, "the rate limit could not be read; sweeping anyway"
        remaining, limit = reading
        floor = self.mark_only_floor if mark_only else self.floor
        if remaining < floor:
            work = "failure-marker pass" if mark_only else f"{self.pull_cap}-pull sweep"
            return False, (
                f"only {remaining} of {limit} core API requests remain, below the "
                f"{floor} a {work} needs. Nothing was swept and nothing "
                "is broken — the budget refills hourly and the next trigger retries"
            )
        work = "failure-marker pass" if mark_only else f"full-sweep cap {self.pull_cap}"
        return True, (
            f"{remaining} of {limit} core API requests available; "
            f"{work}"
        )

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

    def take_refresh(self, pull: dict[str, Any] | None = None) -> bool:
        """Consume one `update-branch` slot. False when this sweep has spent them.

        Consumed on the ATTEMPT, not on success. The slot bounds API calls as well
        as triggered CI runs, and a refused attempt still spent a call; a sweep that
        could retry indefinitely on 422s would bound neither. At saturation, the
        durable lease must be affirmed before the attempt is consumed or sent.
        """
        if not self.refresh_authorized or self.refreshes_used >= self.max_refreshes:
            return False
        if self.requires_refresh_lease:
            if pull is None or self.refresh_lease is None:
                return False
            if not self.refresh_lease.claim(pull):
                return False
        self.refreshes_used += 1
        return True


def sweep_order(
    pulls: list[dict[str, Any]],
    *,
    trigger_head_sha: str = "",
    refresh_lease_number: Any = None,
    now: float | None = None,
    cap: int = FALLBACK_PULL_CAP,
    bucket_seconds: int = ROTATION_BUCKET_SECONDS,
) -> list[dict[str, Any]]:
    """Order the armed pull requests so a capped sweep is fair AND useful.

    Three tiers, then a rotation:

      0. `main-red-repair` — the circuit breaker admits exactly one of these per
         sweep when main is red, so it must never fall outside the cap; a repair
         deferred to the next sweep is the whole repo deferred with it.
      1. the durable refresh-lease owner. It must stay inside the evaluation cap
         until its proof settles, even when it is older than the first pull page.
      2. the head the TRIGGERING workflow run just concluded on. The sweeper wakes
         because some run went green; that run's own pull request is the single
         most likely merge in the backlog, and putting it first is what keeps the
         cap from adding latency to the case the trigger exists to serve.
      3. everything else, rotated.

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
    lease_number = str(refresh_lease_number or "")

    def rank(entry: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, pull = entry
        if MAIN_RED_REPAIR_LABEL in label_names(pull):
            tier = 0
        elif lease_number and str(pull.get("number") or "") == lease_number:
            tier = 1
        elif wanted and str((pull.get("head") or {}).get("sha") or "").lower() == wanted:
            tier = 2
        else:
            tier = 3
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

    if conclusion == "success":
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
    between pre-deploy/out-of-band sweeps, and the window between a successful
    dispatch and the run becoming visible.
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
#:
#: THE TWO SIDES PUBLISH DIFFERENT PACK SETS since the dynamic-matrix conversion
#: (2026-08-11), and that asymmetry is load-bearing rather than a defect to tidy away.
#: A pull request now publishes only the `ci-pack-*` its changed paths selected — any
#: subset of the twelve, sometimes none at all — because `ci-pack` is gated on
#: `needs.ci-plan.outputs.has_work`. Main is proven by a `workflow_dispatch`, which
#: passes no `--changed-from`, so the planner has no changed set, widens to the full
#: suite by the fail-safe rule, and still runs all twelve. That asymmetry is exactly
#: what keeps the base-inherited-red refresh viable: a PR can only go red on a name
#: main's baseline also publishes, so `bad_names <= clean_names` still has something to
#: be a subset OF. Narrow main's baseline to a changed set and this mechanism goes
#: quiet with no red anywhere to show for it — the 2026-08-08 backlog shape, arrived at
#: from the other direction. `ci-gate` is the stable AGGREGATE name, published on every
#: non-closed event by both sides; it is the one to hand branch protection or an
#: external controller, since no individual `ci-pack-N` is guaranteed to appear.
#:
#: `MAIN_PROOF_WORKFLOWS` itself now lives with the tested-surface gate above (#5397,
#: which needs it to build `.github/workflows/<name>` before this point in the file).
#: This block stays here because it documents WHY those two workflows are the proof
#: and what the anchor position means, which is what `MAIN_BASELINE_WORKFLOW` reads.
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
#: The job-level group now coalesces full sweeps, but this interval remains defense in
#: depth for pre-deploy jobs and out-of-band callers: "is one already running?" is a
#: read-then-write race that more than one actor can win. That
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
#: (`ci-plan`, all twelve `ci-pack-*`, `ci-gate`, `fence-pack`, `self-mod-fence`,
#: `capability-broker`, `grader-manifest`) is `success`; the only `skipped` entries are
#: the fork-fallback jobs, which GitHub reports under their UNEVALUATED `name:`
#: expression and so can never collide with a real check name. That accident is exactly
#: why this must be pinned rather than left implicit — the first statically-named
#: conditional job added to either workflow would end it. Main still publishes all
#: twelve packs because its baseline is a `workflow_dispatch` with no `--changed-from`
#: (see MAIN_PROOF_WORKFLOWS); a PULL REQUEST may publish any subset, but a pack that
#: never launched there is a name absent from the head, not a `skipped` job here.
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
        # fences evidence — laundering a stale proof with one newer component.
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
      * they were a read-then-write race between pre-deploy/out-of-band sweeps;
        until 2026-08-09 a raced dispatch even CANCELLED the
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


def red_check_comment(names: list[str]) -> str:
    """The refusal a red head gets, worded ONCE for both callers.

    The full sweep and the failure-wake-up `mark_only_pass` post the same refusal
    for the same reason, so the copy lives in one place. Two hand-maintained copies
    of a comment that TEACHES A LAW ("here is how you take this pull request
    manual") is two chances to teach half of it, and the half omitted below was the
    one that mattered on 2026-08-11.
    """
    return (
        "`merge-on-green` sweeper: **not merging.** These checks concluded "
        "red on the head commit:\n\n"
        + "\n".join(f"- `{name}`" for name in names)
        + "\n\nThe sweeper never merges a red pull request. Fix the cause and "
        "re-run the failed job (the label stays armed, so the next sweep merges "
        "once the head is clean), or remove `merge-on-green` to take it manual — "
        "but do not take it manual SILENTLY: in the same act, leave a marker "
        "(`merge-blocked`, or a comment naming who owns the merge and why) and own "
        "it through to merged-or-handed-back. An unlabeled, uncommented disarm is "
        "invisible to every other session AND to this sweeper, which only ever "
        "looks at labeled pull requests (PR #5291, 2026-08-11).\n\n"
        "The known-spurious `Workers Builds: macro` check is already ignored."
    )


def mark_blocked(repo: str, pull: dict[str, Any], message: str, token: str) -> bool:
    """Add `merge-blocked` and explain it — but only on the transition.

    The comment is posted ONLY in the same call path that actually ADDS the
    label. A sweep runs every 10 minutes, so commenting on every pass over an
    already-blocked pull request would post ~144 comments a day.

    A FAILED LABEL WRITE MUST NOT SILENCE THE EXPLANATION (2026-08-11, PR #5291).
    This used to warn into the run log on an HTTP >= 400 from the label endpoint and
    return WITHOUT commenting, so a 403 / 422 / momentary 502 there left the pull
    request carrying NO visible marker at all — the entire record of the refusal was
    one line in a run log nobody reads, on a lane whose whole job is to leave the
    reason where the owner will find it. The label and the comment are two
    independent ways of saying the same thing, so losing one is a reason to lean
    HARDER on the other, never to go quiet.

    Both writes are therefore attempted and both are checked, a failure of either is
    an `::error` rather than a warning (a lost marker is the loss of the only visible
    signal, not a curiosity), and the return value now answers the question the
    callers actually ask — did a NEW marker land? — instead of "did the label call
    return 2xx". Already-labeled still returns False without commenting: that is the
    one-shot rule, and it is unchanged.
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
    labeled = status < 400
    if not labeled:
        _annotate(
            "error",
            "merge-on-green",
            f"PR #{number}: could not add `{MERGE_BLOCKED_LABEL}` (HTTP {status}); "
            "posting the explanation anyway so the refusal stays visible on the "
            "pull request.",
        )
    comment_status, _ = _request(
        "POST",
        f"{GITHUB_API}/repos/{repo}/issues/{number}/comments",
        token,
        {"body": message},
    )
    commented = comment_status < 400
    if not commented:
        _annotate(
            "error",
            "merge-on-green",
            f"PR #{number}: could not post the explanatory comment "
            f"(HTTP {comment_status})."
            + (
                ""
                if labeled
                else " The label failed too, so this refusal left NO visible marker "
                "on the pull request — only this run log."
            ),
        )
    return labeled or commented


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


def live_diff_state(
    repo: str, pull: dict[str, Any], token: str
) -> tuple[int, str] | None:
    """``(file_count, live_base_sha)`` for the LIVE ``base...head`` compare.

    This is the GROUND-TRUTH answer to "what would this squash merge apply",
    computed from the refs as they stand NOW. The pull request's own `files` view
    is deliberately NOT consulted as a cross-check: an earlier draft of the
    invariant keyed on live-vs-view disagreement, and the recovery lane measured
    that shape vacuous — GitHub recomputes the files view against a clobbered
    head, so all four 2026-08-09 phantoms' files lists read 0 files pre-merge and
    a disagreement never occurs. Emptiness of this compare alone is the signal
    `sweep_pull` refuses on.

    The base SHA is returned too because the merge endpoint's ``sha`` fence protects
    only the PR HEAD.  If main moved after :class:`ProofFreshness` took its snapshot,
    a long sweep could otherwise merge against a base it never classified.  The
    caller requires this live base to equal the frozen snapshot tip and retries on
    the next level-triggered sweep when it does not. GitHub exposes no atomic
    base-SHA compare-and-swap on this merge endpoint, so a tiny read-to-PUT race
    remains; eliminating that last gap requires branch protection/native merge
    queue semantics, while the exact-head SHA fence still closes the head side.

    Cost: one READ_TOKEN GET per pull request that reaches the merge step, inside
    RATE_LIMIT_RESERVE's headroom. ``per_page=1`` bounds the commits array; ``files``
    rides the first page, and only its EMPTINESS is consulted, so GitHub's 300-file
    truncation cannot flip the answer (truncation needs >=300 files, and any answer
    above zero already means "proceed").

    The head side is the exact SHA this sweep judged, not the branch name: the
    checks and the freshness gate were both computed for that SHA, and a branch
    that moved since is a different question (the next sweep's). The base side
    falls back to "main" when the listing payload carried no base ref — every
    armed pull request here targets main, and a wrong-base compare can only make
    the diff LARGER, which reads "proceed", i.e. the pre-invariant behaviour.
    """
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    if not head_sha:
        return None
    base_ref = str((pull.get("base") or {}).get("ref") or "main")
    basehead = f"{urllib.parse.quote(base_ref, safe='/')}...{head_sha}"
    status, payload = _request(
        "GET",
        f"{GITHUB_API}/repos/{repo}/compare/{basehead}?per_page=1",
        token,
    )
    if status >= 400 or not isinstance(payload, dict):
        return None
    files = payload.get("files")
    live_base_sha = str(((payload.get("base_commit") or {}).get("sha")) or "")
    if not isinstance(files, list) or not live_base_sha:
        return None
    return len(files), live_base_sha


def live_diff_file_count(repo: str, pull: dict[str, Any], token: str) -> int | None:
    """Backward-compatible file-count view of :func:`live_diff_state`."""
    state = live_diff_state(repo, pull, token)
    return state[0] if state is not None else None


def live_main_sha(repo: str, token: str) -> str | None:
    """Exact current main ref, immediately before an irreversible merge call."""
    try:
        status, payload = _request(
            "GET", f"{GITHUB_API}/repos/{repo}/git/ref/heads/main", token
        )
    except Exception:
        return None
    if status >= 400 or not isinstance(payload, dict):
        return None
    return str(((payload.get("object") or {}).get("sha")) or "") or None


def already_settled(repo: str, number: Any, token: str) -> tuple[bool, str]:
    """Did this pull request already merge (or close) out from under this sweep?

    WHY (2026-08-06). Sweeps could overlap, and pre-deploy or out-of-band runs can
    still race. The workflow-level `concurrency` group that used to serialise them
    was removed because it did not serialise
    work — it serialised a multi-hour wait for a GitHub-hosted runner, and killed
    98 of 100 consecutive sweeps in the pending slot while doing it (see the
    postmortem in .github/workflows/merge-on-green.yml).

    Raced sweeps are safe by construction almost everywhere: this script is
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


def pull_disposition(
    repo: str,
    number: Any,
    expected_head_sha: str,
    token: str,
) -> tuple[str, str, str]:
    """Current PR disposition after a write raced live state.

    Returns ``(kind, live_head_sha, mergeable_state)`` where kind is ``merged``,
    ``closed``, ``head-moved``, ``open`` or ``unreadable``. A changed head is
    deliberately distinct from a conflict: it proves only that another updater
    or the owner moved the ref after this sweep judged it. The new head must be
    checked on a later pass; accusing it of a content conflict would be stale.
    """
    status, payload = _request(
        "GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}", token
    )
    if status >= 400 or not isinstance(payload, dict):
        return "unreadable", "", ""
    if payload.get("merged") is True:
        return "merged", "", ""
    if str(payload.get("state") or "").lower() == "closed":
        return "closed", "", ""
    live_head = str(((payload.get("head") or {}).get("sha")) or "")
    mergeable_state = str(payload.get("mergeable_state") or "").lower()
    if expected_head_sha and live_head and live_head != expected_head_sha:
        return "head-moved", live_head, mergeable_state
    return "open", live_head, mergeable_state


def live_authorized_pull(
    repo: str,
    pull: dict[str, Any],
    token: str,
    *,
    require_refresh_lease: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    """Re-read the mutable authorization immediately before a write.

    The merge/update SHA parameters fence only the head object.  They do not fence
    the user's arm label, draft state, target branch, or open state; acting from the
    earlier pull listing after any of those changed would exceed the controller's
    authority.
    """
    number = pull.get("number")
    expected_head = str(((pull.get("head") or {}).get("sha")) or "")
    try:
        status, live = _request(
            "GET", f"{GITHUB_API}/repos/{repo}/pulls/{number}", token
        )
    except Exception as exc:
        _annotate(
            "warning",
            "merge-on-green authorization",
            f"PR #{number}: live authorization read failed ({exc}).",
        )
        return None, "authorization-unreadable"
    if status >= 400 or not isinstance(live, dict):
        _annotate(
            "warning",
            "merge-on-green authorization",
            f"PR #{number}: live authorization read returned HTTP {status}.",
        )
        return None, "authorization-unreadable"
    if live.get("merged") is True:
        return None, "already-merged"
    if str(live.get("state") or "").lower() != "open":
        return None, "already-closed"
    live_head = str(((live.get("head") or {}).get("sha")) or "")
    if not expected_head or live_head != expected_head:
        return None, "head-moved"
    if live.get("draft") is True:
        return None, "draft"
    if str(((live.get("base") or {}).get("ref")) or "") != "main":
        return None, "wrong-base"
    labels = label_names(live)
    if MERGE_ON_GREEN_LABEL not in labels:
        return None, "disarmed"
    if require_refresh_lease and REFRESH_LEASE_LABEL not in labels:
        return None, "lease-lost"
    return live, "authorized"


def expected_head_mismatch(detail: str) -> bool:
    """Does GitHub definitively say the expected-SHA fence rejected a moved head?"""
    normalized = " ".join(detail.lower().replace("’", "'").split())
    mismatch = any(
        phrase in normalized
        for phrase in ("didn't match", "did not match", "does not match")
    )
    return (
        "expected head sha" in normalized
        and mismatch
        and ("current head" in normalized or "head ref" in normalized)
    )


def update_branch_conflict(detail: str) -> bool:
    """Affirmative conflict language, not a generic 422 validation response."""
    normalized = " ".join(detail.lower().split())
    return "merge conflict" in normalized or "merge conflicts" in normalized


def update_branch(repo: str, pull: dict[str, Any], token: str) -> str:
    """Merge `main` into a judged head and classify any live-state race.

    ONLY reached for a pull request whose every check already concluded clean and
    whose merge GitHub then refused. The refusal splits two ways and only one of
    them is a human's problem:

      * the base moved under us — the head is fine, it is simply no longer merge-
        able against the newer main. GitHub can fast-forward that itself, and the
        resulting head re-runs CI before anything merges.
      * another actor changed the head after this sweep read its checks — the
        expected-SHA update is correctly refused, and the caller leaves the new
        head armed and unblocked for a fresh judgment;
      * a real content conflict — update-branch answers 422 while the head is
        unchanged and the caller falls through to `merge-blocked`.

    This is the fix for the observed failure mode: main takes ~19 commits in 3
    hours while a pack run takes ~30 minutes, so a pull request can go green and
    be stale before its own proof finishes. Every such head then waits for a human
    to rebase it by hand, which is how a one-hour-old pull request becomes a
    three-day-old one. Nothing here weakens the merge gate — an updated head is
    unproven until its fresh checks conclude, and the next sweep judges it on
    those.

    NOT the clobber vector, for the record (the 2026-08-09 phantom merges). When
    four armed heads were found clobbered to content-identical-with-main after a
    day of refresh cycles, this call was the obvious suspect — it is the thing
    that keeps touching armed heads. It is exonerated by its own failure mode:
    GitHub's server-side update-branch NEVER auto-resolves a conflict, it answers
    422 and the caller falls through to `merge-blocked`, so it can add merge
    commits but cannot invent a resolution that takes main's side. The likely
    source is the fleet's LOCAL refresh work between sweeps — a session resolves
    a refresh/rebase conflict in a worktree and force-pushes — where two known
    mechanisms produce exactly this shape: (a) bulk conflict auto-resolution
    taking main wholesale (`-X theirs` / `checkout --theirs`-style) during
    backlog drains, and/or (b) `git rerere` replaying a SIBLING pull request's
    "take main's version" resolution onto a different conflict in the same file,
    marker-free and status-clean (measured 2026-08-07 on #4821/#4822;
    `rerere.enabled` is false at repo level now, but the shared `.git/rr-cache` —
    worktrees share `.git` — still carries those recorded resolutions, and any
    worktree or `-c` override that re-enables it replays them). Either way the
    head ends content-identical with main, its checks go green on main's own
    content, and only the live compare can tell — which is why the
    clobbered-head invariant in `sweep_pull` sits at the merge itself, not here.
    The clobber mechanism is deliberately NOT fixed in this file: it lives in the
    fleet's local tooling, and the invariant makes it non-catastrophic.
    """
    number = pull.get("number")
    expected_head_sha = str((pull.get("head") or {}).get("sha") or "")
    status, body = _request(
        "PUT",
        f"{GITHUB_API}/repos/{repo}/pulls/{number}/update-branch",
        token,
        {"expected_head_sha": expected_head_sha},
    )
    if status in {200, 202}:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: checks were clean but the base had moved — merged main "
            "into the head. Its fresh checks decide the merge on a later sweep.",
        )
        return "updated"
    detail = str((body or {}).get("message") or f"HTTP {status}")
    if status == 422 and expected_head_mismatch(detail):
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: expected head {expected_head_sha[:12]} was no longer "
            "the current head when update-branch ran. Another updater "
            "or the owner won the race; leaving the new head armed and unblocked "
            "for its fresh checks.",
        )
        return "head-moved"
    if status == 422:
        disposition, live_head, mergeable_state = pull_disposition(
            repo, number, expected_head_sha, token
        )
        if disposition in {"merged", "closed"}:
            _annotate(
                "notice",
                "merge-on-green",
                f"PR #{number}: already {disposition} by the time update-branch ran — "
                "a concurrent sweep won the race. Nothing to do, nothing labeled.",
            )
            return f"already-{disposition}"
        if disposition == "head-moved":
            _annotate(
                "notice",
                "merge-on-green",
                f"PR #{number}: head moved from {expected_head_sha[:12]} to "
                f"{live_head[:12]} while update-branch was in flight. Another updater "
                "or the owner won the race; leaving the new head armed and unblocked "
                "for its fresh checks.",
            )
            return "head-moved"
        if mergeable_state == "dirty" or update_branch_conflict(detail):
            print(
                f"PR #{number}: update-branch declined ({detail}) — treating as a real "
                "conflict based on affirmative conflict evidence.",
                flush=True,
            )
            return "declined"
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: update-branch returned an unclassified 422 ({detail}); "
            "GitHub also uses 422 for validation and endpoint throttling, so this "
            "stays armed for retry instead of receiving a permanent conflict marker.",
        )
        return "retry"
    _annotate(
        "warning",
        "merge-on-green",
        f"PR #{number}: update-branch failed with HTTP {status} ({detail}); leaving "
        "it armed and unlabeled for a later retry, not calling an API failure a "
        "content conflict.",
    )
    return "retry"


def attempt_update_branch(
    repo: str,
    pull: dict[str, Any],
    token: str,
    budget: "SweepBudget | None",
    why: str,
) -> str:
    """The sole gateway to ``update_branch`` and its workload/lease admission."""
    live, disposition = live_authorized_pull(repo, pull, token)
    if live is None:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{pull.get('number')}: update authorization changed "
            f"({disposition}); no branch write attempted.",
        )
        return disposition
    if budget is None:
        _annotate(
            "error",
            "merge-on-green refresh authority",
            f"PR #{pull.get('number')}: update-branch admission has no serialized "
            "sweep budget; no branch write attempted.",
        )
        return "refresh-deferred"
    if not budget.take_refresh(live):
        return refresh_deferred(pull.get("number"), why, budget)
    if budget.requires_refresh_lease:
        live, disposition = live_authorized_pull(
            repo, live, token, require_refresh_lease=True
        )
        if live is None:
            _annotate(
                "notice",
                "merge-on-green",
                f"PR #{pull.get('number')}: refresh lease authorization changed "
                f"({disposition}); no branch write attempted.",
            )
            return disposition
        if budget.refresh_lease is None or not budget.refresh_lease.record_is_current():
            _annotate(
                "warning",
                "merge-on-green refresh lease",
                f"PR #{pull.get('number')}: generation register changed immediately "
                "before update-branch; no write attempted.",
            )
            return "lease-lost"
    return update_branch(repo, live, token)


def refresh_deferred(
    number: Any, why: str, budget: "SweepBudget | None" = None
) -> str:
    """Leave a pull request untouched because the refresh budget is spent.

    NOT a `merge-blocked`, deliberately. The pull request has done nothing wrong —
    this sweep simply ran out of `update-branch` slots — so labelling it would be
    a false accusation, and `mark_blocked`'s comment is one-shot, so the false one
    would be the one that sticks. It stays armed and the next sweep refreshes it.
    """
    _annotate(
        "notice",
        "merge-on-green",
        f"PR #{number}: {why}, but this sweep has "
        + (
            f"{budget.refreshes_used}/{budget.max_refreshes} effective "
            "`update-branch` attempt(s) in use"
            if budget is not None
            else f"spent its {MAX_REFRESHES_PER_SWEEP} `update-branch` slots"
        )
        + (
            f" ({budget.refresh_context})"
            if budget is not None and budget.refresh_context
            else ""
        )
        + ". Controller state is unchanged; a later sweep picks it up.",
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

    …UNLESS another sweep merged it a second ago. Pre-deploy or out-of-band sweeps
    can both judge this pull request clean and stale; the loser's
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
    update_result = attempt_update_branch(
        repo,
        pull,
        merge_token,
        budget,
        f"its proof is stale ({reason})",
    )
    if update_result == "refresh-deferred":
        return update_result
    if update_result == "updated":
        # The branch is moving again, so any `merge-blocked` from an earlier pass
        # has stopped being true.
        clear_blocked(repo, pull, merge_token)
        return "re-proving"
    if update_result == "head-moved":
        clear_blocked(repo, pull, merge_token)
        return update_result
    if update_result == "retry":
        return "update-retry"
    if update_result.startswith("already-"):
        return update_result
    if update_result != "declined":
        return update_result
    settled, how = already_settled(repo, number, read_token)
    if settled:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: already {how} by the time this sweep tried to re-prove it "
            "— a concurrent sweep won the race. Nothing to do, nothing labeled.",
        )
        return f"already-{how}"
    live_pull, authorization = live_authorized_pull(repo, pull, read_token)
    if live_pull is None:
        return authorization
    pull = live_pull
    added = mark_blocked(
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
        f"PR #{number}: stale proof and update-branch declined — "
        + (
            "marker written."
            if added
            else "no new marker (already labeled, or both writes failed above)."
        ),
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
    reconcile_only: bool = False,
) -> str:
    """Judge and, when clean, merge one labeled pull request. Returns the verdict.

    ``freshness`` is REQUIRED and has no default on purpose. A default would let a
    caller that forgot to build it merge on an unidentified green forever, which is the
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
    anchor_verdict, anchor_names = proof_anchor_verdict(runs)
    if budget is not None:
        budget.observed_anchor_states[number] = anchor_verdict
    lease = budget.refresh_lease if budget is not None else None
    settled_owner_generation = False
    if lease is not None and lease.owns(pull):
        live_head_sha = head_sha.lower()
        generation_advanced = bool(
            lease.generation_head_sha
            and live_head_sha != lease.generation_head_sha
        )

        def release_live_generation(reason: str) -> bool:
            live_generation_pull, authorization = live_authorized_pull(
                repo, pull, read_token, require_refresh_lease=True
            )
            if (
                live_generation_pull is None
                or str(
                    ((live_generation_pull.get("head") or {}).get("sha")) or ""
                ).lower()
                != live_head_sha
                or not lease.record_is_current()
            ):
                _annotate(
                    "warning",
                    "merge-on-green refresh lease",
                    f"PR #{number}: generation settlement authorization changed "
                    f"({authorization}); retained for a fresh sweep.",
                )
                return False
            return lease.release(live_generation_pull, reason)

        if generation_advanced and anchor_verdict in {"clean", "blocked"}:
            # The exact repository-owned proof workload this lease reserved has
            # settled on a head newer than the pre-update generation. Release BEFORE
            # any stale/refused-merge path can attempt another update. The same PR is
            # excluded from reacquisition for the rest of this sweep, allowing a
            # later candidate to claim the one high-load lane.
            settled_owner_generation = True
            released = release_live_generation(
                f"leased proof generation settled {anchor_verdict}",
            )
            if not released:
                return "lease-release-retry"
        elif generation_advanced and anchor_verdict in {"pending", "incomplete"}:
            active_anchor_work = proof_anchor_work_is_active(runs)
            expired = (
                lease.owner_exceeded_max_age()
                if active_anchor_work
                else lease.owner_is_old()
            )
            if expired:
                if not release_live_generation(
                    "leased proof did not settle before its "
                    + ("hard timeout" if active_anchor_work else "registration grace"),
                ):
                    return "lease-release-retry"
                return "lease-rotation-deferred"
            return (
                "lease-generation-pending"
                if active_anchor_work
                else "lease-generation-incomplete"
            )
        elif not generation_advanced:
            # update-branch has not visibly advanced the recorded pre-update head.
            # Old checks on that same head cannot describe the leased generation.
            # Wait without re-entering any refresh path; after grace, rotate and let
            # a later sweep create a fresh generation record.
            if lease.owner_is_old():
                if not release_live_generation(
                    "refresh head never advanced inside the lease grace period"
                ):
                    return "lease-release-retry"
                return "lease-rotation-deferred"
            return "lease-generation-waiting"
        if reconcile_only:
            # The source-main circuit breaker is red. This call exists only so a
            # durable workload reservation can settle/expire; it must never turn
            # ordinary PR proof into permission to merge through a red baseline.
            return "baseline-blocked"
    verdict, names = decide_verdict(runs)
    if verdict == "clean":
        if anchor_verdict != "clean":
            verdict, names = anchor_verdict, anchor_names

    if verdict == "pending":
        print(
            f"PR #{number}: {len(names)} check(s) still running "
            f"({', '.join(names[:6])}) — waiting for the next sweep.",
            flush=True,
        )
        return verdict

    if verdict in {"unproven", "incomplete"}:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: head {head_sha[:12]} has no complete affirmative ci/fences "
            f"proof ({', '.join(names[:6]) or 'no check runs'}). Nothing is merged or "
            "accused; a fresh proof event or branch update can supply the missing anchors. "
            "If this head intentionally has no CI, dispose of it manually.",
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
                update_result = attempt_update_branch(
                    repo,
                    pull,
                    merge_token,
                    budget,
                    "its red checks are all green on main, so it needs a refresh",
                )
                if update_result == "refresh-deferred":
                    return update_result
                if update_result == "updated":
                    clear_blocked(repo, pull, merge_token)
                    print(
                        f"PR #{number}: red checks ({', '.join(sorted(bad_names)[:6])}) "
                        "are all green on a main proved since they ran — the base moved "
                        "under it. Refreshed; its fresh checks decide on a later sweep.",
                        flush=True,
                    )
                    return "rebased"
                if update_result == "head-moved":
                    clear_blocked(repo, pull, merge_token)
                    return update_result
                if update_result == "retry":
                    return "update-retry"
                if update_result.startswith("already-"):
                    return update_result
                if update_result != "declined":
                    return update_result

        if blocked_names is not None:
            # What this sweep could not answer, for `ensure_main_baseline`.
            blocked_names |= bad_names

        live_pull, authorization = live_authorized_pull(repo, pull, read_token)
        if live_pull is None:
            return authorization
        pull = live_pull
        added = mark_blocked(repo, pull, red_check_comment(names), merge_token)
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: red checks ({', '.join(names[:6])}); "
            + (
                "marker written."
                if added
                else "no new marker (already labeled, or both writes failed above)."
            ),
        )
        return verdict

    # Every check concluded clean. The remaining question is not WHETHER the head is
    # proven but WHICH exact main SHA its pull_request event tested. GitHub records
    # that SHA on the check run itself; timestamps are not proof identity. An
    # unavailable identity defers without mutation because update-branch cannot
    # repair a control-plane read failure.
    try:
        stale, reason = freshness.stale_for(pull, runs)
    except Exception as exc:  # a broken read must never become permission to merge
        stale, reason = None, f"the tested-surface check itself failed ({exc})"
    if stale is None:
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: exact proof freshness is indeterminate ({reason}). "
            "Left armed without update-branch; the next sweep re-reads the evidence.",
        )
        return "freshness-deferred"
    if stale:
        if settled_owner_generation:
            _annotate(
                "notice",
                "merge-on-green refresh lease",
                f"PR #{number}: its leased proof generation settled but main moved "
                "again. Rotating the high-load lane before this pull request may "
                "request another generation.",
            )
            return "lease-rotation-deferred"
        return reprove(repo, pull, reason, read_token, merge_token, budget)
    print(f"PR #{number}: proof still current — {reason}.", flush=True)

    # THE CLOBBERED-HEAD INVARIANT (the 2026-08-09 phantom merges: #5055 #5061
    # #5078 #5091 — module docstring; #5074 in the same drain was not one).
    # Everything above judged the head's CHECKS; nothing asked whether the head
    # still CONTAINS the pull request's work. A head clobbered to content-
    # identical-with-main during refresh cycles is green for free — its checks
    # tested main's own content — and squash-merging it creates an empty commit
    # that reads MERGED while zero files land. The refusal is UNCONDITIONAL on an
    # empty live diff: the earlier disagreement shape (empty live diff while the
    # PR's files view still names files) was measured vacuous, because GitHub
    # recomputes the files view against the clobbered head — all four phantoms
    # read 0 files pre-merge. And no legitimate armed pull request has an empty
    # diff: merging one records MERGED while delivering nothing, so blocking
    # costs nothing. One live compare, after every cheaper gate has passed and
    # immediately before the irreversible step. Likely clobber source:
    # `update_branch`'s docstring.
    live_state = live_diff_state(repo, pull, read_token)
    if live_state is None:
        # Fail closed WITHOUT accusing: a broken read must never become
        # permission to merge, but a blip is not evidence of a clobber either —
        # and `mark_blocked`'s comment is one-shot, so a false accusation would
        # be the one that sticks. Armed, unlabeled, retried next sweep.
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: the live base...head compare could not be read, so "
            "the clobbered-head invariant cannot run — not merging on partial "
            "information. Left armed for the next sweep.",
        )
        return "error"
    live_files, live_base_sha = live_state
    if not freshness.snapshot_tip or live_base_sha != freshness.snapshot_tip:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: main moved from freshness snapshot "
            f"{freshness.snapshot_tip[:12] or '?'} to {live_base_sha[:12]} before "
            "the merge call. The exact-head proof is intact, but this sweep has not "
            "classified the new base; left armed for a fresh snapshot.",
        )
        return "main-moved"
    if live_files == 0:
        live_pull, authorization = live_authorized_pull(repo, pull, read_token)
        if live_pull is None:
            return authorization
        pull = live_pull
        added = mark_blocked(
            repo,
            pull,
            (
                "`merge-on-green` sweeper: **not merging.** Every check "
                "concluded clean, but the live `base...head` compare for this "
                "pull request is EMPTY: squash-merging it would create an empty "
                "commit that reads MERGED while delivering nothing. No "
                "legitimate armed pull request has an empty diff, so the "
                "sweeper refuses unconditionally.\n\n"
                "The usual cause is a CLOBBERED HEAD — the 2026-08-09 phantom "
                "merges (#5055 #5061 #5078 #5091): a refresh-cycle conflict "
                "resolution took main wholesale (and/or a `git rerere` replay "
                "of a sibling's resolution), leaving the branch head "
                "content-identical with main, so its checks passed on main's "
                "own content and GitHub's recomputed files view read 0 files. "
                f"Head at refusal time: `{head_sha}`. The good content "
                "survives at this branch's PRE-CLOBBER commits — walk the "
                "branch's `git log`/reflog (or a parked worktree) for the last "
                "head whose `base...head` diff matches this pull request's "
                "intent, force-push the branch back to it, and the next sweep "
                "judges the restored head on its fresh checks (the label stays "
                "armed).\n\n"
                "If instead this pull request is GENUINELY empty — its content "
                "already landed via a sibling, or it never had any — close it "
                "rather than merge it: an empty squash records a MERGED state "
                "that delivered nothing, which is exactly the record this "
                "refusal exists to prevent."
            ),
            merge_token,
        )
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: live base...head diff is EMPTY — head "
            f"{head_sha[:12]} carries no changes against main (clobbered head, "
            "or a superseded/empty pull request); merge refused. "
            + (
                "Marker written."
                if added
                else "No new marker (already labeled, or both writes failed above)."
            ),
        )
        return "empty-diff"

    # The listing/check snapshot is not authorization.  Re-read the PR after the
    # live diff and immediately before the irreversible call so a user disarm,
    # draft conversion, retarget, close, or head push cannot be auto-merged from a
    # stale payload.  GitHub's merge `sha` fences only the final item in that list.
    live_pull, authorization = live_authorized_pull(repo, pull, read_token)
    if live_pull is None:
        if authorization == "head-moved":
            clear_blocked(repo, pull, merge_token)
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: merge authorization changed ({authorization}); left "
            "untouched for a fresh sweep.",
        )
        return authorization
    pull = live_pull

    # Narrow the merge endpoint's missing base-SHA fence to the final network
    # round trip. GitHub can atomically fence only the head here; a true base CAS
    # remains the reason native merge queue is the long-term end state.
    final_main_sha = live_main_sha(repo, read_token)
    if final_main_sha is None:
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: final main-ref fence was unreadable; not merging on "
            "partial base state.",
        )
        return "main-ref-unreadable"
    if final_main_sha != freshness.snapshot_tip:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: main advanced to {final_main_sha[:12]} after final "
            "authorization; ending this snapshot before the merge call.",
        )
        return "main-moved"

    def finish_ambiguous_merge(cause: str) -> str:
        """Consume this snapshot after a merge whose outcome is not definitive."""
        # The server may have accepted the irreversible write before the response
        # body/connection failed. Never continue this main snapshot on an ambiguous
        # outcome: first ask the PR, then hand the whole snapshot to the next sweep
        # even when that re-read also fails.
        try:
            settled, how = already_settled(repo, number, read_token)
        except Exception as reread_exc:
            settled, how = False, ""
            detail = f"; disposition re-read also failed ({reread_exc})"
        else:
            detail = ""
        if settled:
            _annotate(
                "notice",
                "merge-on-green",
                f"PR #{number}: merge response was ambiguous ({cause}), but the "
                f"live pull request is already {how}. Treating the snapshot as "
                "consumed.",
            )
            return f"already-{how}"
        _annotate(
            "warning",
            "merge-on-green",
            f"PR #{number}: merge response was ambiguous ({cause}) and its outcome "
            f"could not be confirmed{detail}. No conflict/update action taken; "
            "ending this snapshot so the next sweep can re-read live state.",
        )
        return "merge-unknown"

    try:
        status, body = _request(
            "PUT",
            f"{GITHUB_API}/repos/{repo}/pulls/{number}/merge",
            merge_token,
            {"merge_method": "squash", "sha": head_sha},
        )
    except Exception as exc:
        return finish_ambiguous_merge(f"transport error: {exc}")

    # GitHub or an intermediary can emit a server response after the merge write
    # was accepted. A 5xx is therefore not affirmative refusal evidence; classify
    # it exactly like a truncated connection and never keep using this base snapshot.
    if 500 <= status < 600:
        message = str((body or {}).get("message") or f"HTTP {status}")
        return finish_ambiguous_merge(f"HTTP {status}: {message}")

    if status == 200:
        _annotate(
            "notice",
            "merge-on-green",
            f"PR #{number}: every check concluded clean — squash-merged "
            f"({str((body or {}).get('sha') or '')[:12]}).",
        )
        # Cleanup is genuinely best-effort. A label/ref read can fail after GitHub
        # has accepted the merge; that must never hide the `merged` verdict and let
        # main() continue using a snapshot the accepted write already consumed.
        for cleanup_name, cleanup in (("clear merge-blocked", clear_blocked),):
            try:
                cleanup(repo, pull, merge_token)
            except Exception as exc:
                _annotate(
                    "warning",
                    "merge-on-green cleanup",
                    f"PR #{number}: squash merge succeeded, but could not "
                    f"{cleanup_name} ({exc}). Merge remains successful.",
                )
        return "merged"

    if status in {405, 409}:
        # GitHub's "not mergeable" pair: 405 for a blocked/dirty merge, 409 for a
        # base that moved under us. Only the second is genuinely a human's
        # problem-free case, so try to clear it before reaching for a label.
        detail = str((body or {}).get("message") or f"HTTP {status}")
        # ...but a THIRD shape produces the same 405/409 when sweeps race:
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
        update_result = attempt_update_branch(
            repo,
            pull,
            merge_token,
            budget,
            f"GitHub refused the merge ({detail})",
        )
        if update_result == "refresh-deferred":
            # No slots/lease left to fast-forward it, and the refusal may be
            # nothing but a stale base — never fall through to `merge-blocked`.
            return update_result
        if update_result == "updated":
            # The head now carries main. It is UNPROVEN until its fresh checks
            # conclude, so nothing merges on this pass and the label stays armed
            # for the sweep that judges those checks. Any stale `merge-blocked`
            # from an earlier pass is cleared: the branch is moving again.
            clear_blocked(repo, pull, merge_token)
            return "updated"
        if update_result == "head-moved":
            clear_blocked(repo, pull, merge_token)
            return update_result
        if update_result == "retry":
            return "update-retry"
        if update_result.startswith("already-"):
            return update_result
        if update_result != "declined":
            return update_result
        live_pull, authorization = live_authorized_pull(repo, pull, read_token)
        if live_pull is None:
            return authorization
        pull = live_pull
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


def _self_wake_runs(repo: str, token: str) -> list[dict[str, Any]] | None:
    query = urllib.parse.urlencode(
        {"event": "workflow_dispatch", "per_page": str(SELF_WAKE_LOOKBACK)}
    )
    try:
        status, payload = _request(
            "GET",
            f"{GITHUB_API}/repos/{repo}/actions/workflows/"
            f"{SELF_WAKE_WORKFLOW}/runs?{query}",
            token,
        )
    except Exception:
        return None
    runs = (payload or {}).get("workflow_runs") if isinstance(payload, dict) else None
    if status >= 400 or not isinstance(runs, list):
        return None
    return [run for run in runs if isinstance(run, dict)]


def ensure_self_wake(
    repo: str,
    read_token: str,
    write_token: str,
    current_run_id: str,
    reason: str,
) -> str:
    """Guarantee one bounded successor full sweep after a terminal snapshot.

    ``workflow_dispatch`` is the Actions-token recursion exception. Full sweeps
    share the job-level ``sweep`` concurrency key, so a successor coalesces with
    any one already pending. A 60-second start-to-start floor prevents a persistent
    base race or ambiguous merge endpoint from spinning the dedicated controller.
    """
    active = {"queued", "in_progress", "pending", "requested", "waiting"}

    def inspect() -> tuple[str, float | None]:
        runs = _self_wake_runs(repo, read_token)
        if runs is None:
            return "unreadable", None
        latest: float | None = None
        for run in runs:
            run_id = str(run.get("id") or "")
            parsed = _parse_dt(run.get("created_at"))
            if parsed is None:
                return "unreadable", None
            created = parsed.timestamp()
            latest = created if latest is None else max(latest, created)
            if run_id != str(current_run_id or "") and str(run.get("status") or "") in active:
                return "coalesced", latest
        return "clear", latest

    state, latest = inspect()
    if state == "unreadable":
        _annotate(
            "warning",
            "merge-on-green self-wake",
            f"Could not census controller dispatches after {reason}; dispatching "
            "boundedly anyway because duplicate successors coalesce in `sweep`.",
        )
        latest = None
    if state == "coalesced":
        return "coalesced with an existing successor"

    now = time.time()
    remaining = (
        max(0.0, SELF_WAKE_MIN_INTERVAL_SECONDS - (now - latest))
        if latest is not None
        else 0.0
    )
    if remaining:
        time.sleep(min(float(SELF_WAKE_MIN_INTERVAL_SECONDS), remaining))
        state, after_wait_latest = inspect()
        if state == "unreadable":
            _annotate(
                "warning",
                "merge-on-green self-wake",
                "Successor census was unreadable after cooldown; issuing a bounded "
                "dispatch because duplicate sweeps are coalesced.",
            )
        if state == "coalesced":
            return "coalesced during cooldown"
        if (
            after_wait_latest is not None
            and time.time() - after_wait_latest < SELF_WAKE_MIN_INTERVAL_SECONDS
        ):
            # A different dispatch may have started and already finished during the
            # wait. It is still the successor; do not violate the start-rate floor
            # merely because it is no longer in an active state at the re-read.
            return "coalesced with a newer completed successor"

    dispatch_url = (
        f"{GITHUB_API}/repos/{repo}/actions/workflows/"
        f"{SELF_WAKE_WORKFLOW}/dispatches"
    )
    last_failure = ""
    for attempt in range(SELF_WAKE_ATTEMPTS):
        try:
            status, _ = _request(
                "POST", dispatch_url, write_token, {"ref": "main"}
            )
        except Exception as exc:
            status = 599
            last_failure = f"transport error: {exc}"
        else:
            last_failure = f"HTTP {status}"
        if status in {200, 201, 204}:
            break
    else:
        _annotate(
            "warning",
            "merge-on-green self-wake",
            f"Could not affirm a successor after {reason} ({last_failure}) across "
            f"{SELF_WAKE_ATTEMPTS} bounded attempt(s); event and schedule recovery "
            "remain armed.",
        )
        return "dispatch-unconfirmed"
    _annotate(
        "notice",
        "merge-on-green self-wake",
        f"Dispatched one serialized successor sweep after {reason}.",
    )
    return "dispatched"


def lease_reconcile_pass(
    repo: str,
    read_token: str,
    write_token: str,
    trigger_head_sha: str,
    trigger_conclusion: str,
    current_run_id: str,
    trigger_created_at: str = "",
) -> int:
    """Level-trigger one serialized sweep; never inspect or mutate lease state.

    Cancelled/skipped bursts may coalesce across heads because the surviving job
    performs the same action.  Only the full ``sweep`` concurrency group owns the
    durable label, eliminating cross-group delete/claim races entirely.
    """
    try:
        leases = open_refresh_lease_issues(repo, read_token)
    except Exception:
        leases = None
    if leases:
        ensure_self_wake(
            repo,
            read_token,
            write_token,
            current_run_id,
            f"{trigger_conclusion or 'non-success'} leased proof completion",
        )
    else:
        print(
            "merge-on-green lease reconcile: no durable refresh owner; no full "
            "sweep dispatched.",
            flush=True,
        )
    return 0


def mark_only_pass(
    repo: str,
    read_token: str,
    merge_token: str,
    trigger_head_sha: str,
    budget: "SweepBudget | None" = None,
    current_run_id: str = "",
    trigger_created_at: str = "",
) -> int:
    """Leave a VISIBLE marker on the head a failed proof run just concluded on.

    WHY THIS EXISTS (2026-08-11, PR #5291). The job-level `if:` in
    .github/workflows/merge-on-green.yml used to skip every `failure` wake-up, and
    the essay there argued it "fails SAFE — a red PR simply stays armed and unmerged,
    which is the correct outcome either way". That assumed nothing else touches the
    label during the window in which the red is real but unmarked. Measured:

        02:05:18Z  ci run 31449929887 concludes FAILURE on #5291's head 9ce3c2ef
        02:13:32Z  another session runs `gh pr edit 5291 --remove-label merge-on-green`
        02:13:34Z  the arm label is gone: no `merge-blocked`, no comment, no marker
        02:13:41Z  the next sweep lists the ARMED pull requests — #5291 is not in it

    Eight minutes of red-and-unmarked, and then the pull request left the
    label-filtered world this sweeper lives in permanently: with the arm label gone
    the marker could never arrive on any later sweep, ever. The cron cannot be the
    answer — measured ~0.5 sweeps/hour against a nominal 6 — so the marker has to
    land BEFORE the window rather than after it, which means waking on the failure
    that opens it.

    DELIBERATELY NOT A SWEEP. This pass never merges, never `update-branch`es and
    never dispatches a proof baseline. It reads one head's checks and
    writes at most one marker, which is what keeps a failure wake-up affordable: ~4-8
    requests (listing + one check-run page + at most the 4-request proof lookup + two
    writes) against READ_TOKEN's 1,000/hr PER-REPOSITORY budget. Even at the measured
    ~26 failure wake-ups an hour that is well inside the bucket a real sweep needs,
    which is the only reason the `if:` may admit failures at all. Anything that would
    make this pass expensive belongs in the full sweep, not here.

    Always exits 0 on a red pull request: a red is the lane working, not a fault.
    """
    if not trigger_head_sha:
        print(
            "merge-on-green mark-only pass: the trigger carried no head sha, so there "
            "is nothing to mark. Only a `workflow_run` event has one — a cron or "
            "dispatch reaching here would be a routing bug, not a red pull request.",
            flush=True,
        )
        return 0

    try:
        pulls = labeled_pulls(repo, read_token)
    except RateLimited as exc:
        _annotate(
            "warning",
            "merge-on-green",
            f"Mark-only pass deferred: {exc}. Nothing marked.",
        )
        return 0
    except Exception as exc:
        _annotate("error", "merge-on-green", f"Could not list pull requests: {exc}")
        return 1

    wanted = trigger_head_sha.strip().lower()
    matching = [
        pull
        for pull in pulls
        if str((pull.get("head") or {}).get("sha") or "").lower() == wanted
    ]
    if not matching:
        print(
            "merge-on-green mark-only pass: no armed pull request sits at "
            f"{trigger_head_sha[:12]}, so there is nothing to mark. A PUSH SUPERSEDES "
            "ITS OWN RED — the failed run belongs to a head that has been replaced, "
            "and the successor head must never be accused of an ancestor's failure. "
            "The successor's own runs will conclude and wake their own pass.",
            flush=True,
        )
        return 0

    # Fetched at most ONCE, and only if a blocked verdict actually appears: a
    # wake-up whose head turns out to be pending or already green must not spend the
    # two-workflow proof lookup to discover that.
    proof: MainProof | None = None
    tally: dict[str, int] = {}
    for pull in matching:
        number = pull.get("number")
        head_sha = str((pull.get("head") or {}).get("sha") or "")
        try:
            runs = head_check_runs(repo, head_sha, read_token)
            verdict, names = decide_verdict(runs)
            if verdict != "blocked":
                # `pending`, `unproven` and `clean` are all the full sweep's business.
                # One failed run does not make the HEAD red (a rerun may still be
                # going), and nothing here may merge, so the only honest action is a
                # line in the log.
                print(
                    f"PR #{number}: the run that woke this pass failed, but the head's "
                    f"checks read `{verdict}` as a whole — nothing marked. The full "
                    "sweep owns every outcome except a marker on a settled red.",
                    flush=True,
                )
                tally[verdict] = tally.get(verdict, 0) + 1
                continue

            bad_names = failing_check_names(runs)
            if proof is None:
                proof = main_proof(repo, read_token)
            if bad_names and proof.clean_names and bad_names <= proof.clean_names:
                # Possibly a base-inherited red, and this pass is not equipped to
                # decide: the refresh-vs-block call needs `proof_postdates_failures`,
                # a refresh slot and an `update-branch`, all of which are the full
                # sweep's. Marking on the name overlap alone would post the one-shot
                # false-accusation comment on every armed head during a fleet-wide
                # stale-base red — the exact daily audit the main-proof-too-old note
                # in `sweep_pull` documents. Deferring costs a marker one sweep late;
                # marking wrongly costs a comment that can never be taken back.
                print(
                    f"PR #{number}: red checks "
                    f"({', '.join(sorted(bad_names)[:6])}) are all clean on main's own "
                    "proof, so this may be a base-inherited red rather than this pull "
                    "request's. Deferred to the full sweep, which owns the "
                    "refresh-vs-block decision; nothing marked.",
                    flush=True,
                )
                tally["base-red-deferred"] = tally.get("base-red-deferred", 0) + 1
                continue

            live_pull, authorization = live_authorized_pull(repo, pull, read_token)
            if live_pull is None:
                print(
                    f"PR #{number}: marker authorization changed ({authorization}); "
                    "nothing written from the stale failure event.",
                    flush=True,
                )
                tally[authorization] = tally.get(authorization, 0) + 1
                continue
            pull = live_pull
            added = mark_blocked(repo, pull, red_check_comment(names), merge_token)
            _annotate(
                "warning",
                "merge-on-green",
                f"PR #{number}: red checks ({', '.join(names[:6])}); "
                + (
                    "marker written."
                    if added
                    else "no new marker (already labeled, or both writes failed above)."
                ),
            )
            tally[verdict] = tally.get(verdict, 0) + 1
        except RateLimited as exc:
            _annotate(
                "warning",
                "merge-on-green",
                f"Mark-only pass stopped at PR #{number}: {exc}.",
            )
            break
        except Exception as exc:  # noqa: BLE001 — never fail the run over one PR
            _annotate(
                "warning",
                "merge-on-green",
                f"PR #{number}: mark-only pass failed ({exc}); the full sweep retries it.",
            )
            tally["error"] = tally.get("error", 0) + 1

    left = budget.last_seen if budget is not None else None
    print(
        "merge-on-green mark-only pass: "
        + f"{len(matching)} armed pull request(s) at {trigger_head_sha[:12]}; "
        + (
            ", ".join(f"{count} {verdict}" for verdict, count in sorted(tally.items()))
            or "nothing judged"
        )
        + f" (~{left if left is not None else '?'} API requests left; "
        + "no merge, no refresh, no baseline dispatch)",
        flush=True,
    )
    # The marker pass runs in a different concurrency group and therefore never
    # mutates the durable lease.  Wake one serialized full reconciliation so a
    # leased red/base-inherited-red owner is released or refreshed there.
    if any(REFRESH_LEASE_LABEL in label_names(pull) for pull in matching):
        ensure_self_wake(
            repo,
            read_token,
            merge_token,
            current_run_id,
            f"failure marker pass for leased head {trigger_head_sha[:12]}",
        )
    return 0


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
    # …and HOW it concluded. `failure` selects `mark_only_pass` below; every other
    # value (including the empty string the cron and workflow_dispatch supply) runs
    # the full sweep exactly as before.
    trigger_conclusion = os.environ.get("TRIGGER_CONCLUSION", "").strip().lower()
    current_run_id = os.environ.get("CURRENT_RUN_ID", "").strip()
    if not repo:
        _annotate("error", "merge-on-green", "GH_REPO is not set; nothing to sweep.")
        return 1

    # Preflight the budget BEFORE the first real call. A starved sweeper that keeps
    # firing consumes each hourly refill on its own 403s and never recovers; a
    # deferral is a deliberate, logged no-op and exits 0, because a red run here is
    # noise that masks the genuine failures this lane also reports.
    budget = SweepBudget(read_token)
    may_sweep, budget_detail = budget.preflight(
        mark_only=bool(trigger_conclusion and trigger_conclusion != "success")
    )
    if not may_sweep:
        _annotate("notice", "merge-on-green", f"Sweep deferred: {budget_detail}.")
        # Never recursively dispatch another full sweep while the bucket is below
        # its floor: that self-perpetuating retry storm was the original quota outage.
        # Workflow completions and the recovery schedule retry after budget refill.
        return 0
    print(f"API budget: {budget_detail}.", flush=True)

    # A FAILURE WAKE-UP MARKS; IT DOES NOT SWEEP (2026-08-11, PR #5291). The workflow
    # now runs this job on a failed proof run so a fresh red gets its marker in
    # seconds instead of waiting for the ~0.5/hr cron or for the next green anywhere
    # in the repository — see `mark_only_pass` for the eight-minute window that made
    # the old skip unsafe. It must NOT fall through into the full sweep: a red run
    # cannot make anything mergeable, and these wake-ups are ~5x more frequent than
    # the greens, so paying a full backlog pass for each of them would put the
    # per-repository READ_TOKEN bucket back where 2026-08-07 found it. The budget
    # preflight above still applies — a starved lane marks nothing either.
    if trigger_conclusion == "failure":
        if current_run_id:
            return mark_only_pass(
                repo,
                read_token,
                merge_token,
                trigger_head_sha,
                budget,
                current_run_id=current_run_id,
            )
        return mark_only_pass(repo, read_token, merge_token, trigger_head_sha, budget)
    if trigger_conclusion and trigger_conclusion != "success":
        return lease_reconcile_pass(
            repo,
            read_token,
            merge_token,
            trigger_head_sha,
            trigger_conclusion,
            current_run_id,
        )

    try:
        pulls = labeled_pulls(repo, read_token)
    except RateLimited as exc:
        _annotate("warning", "merge-on-green", f"Sweep deferred: {exc}. No PRs swept.")
        return 0
    except Exception as exc:
        _annotate("error", "merge-on-green", f"Could not list pull requests: {exc}")
        return 1

    refresh_lease, pulls = prepare_refresh_lease(
        repo, read_token, merge_token, pulls
    )
    budget.refresh_authorized = serialized_refresh_authority(
        repo, read_token, current_run_id, trigger_conclusion
    )
    if not budget.refresh_authorized:
        _annotate(
            "error",
            "merge-on-green refresh authority",
            "This process is not the affirmed in-progress default-branch "
            "merge-on-green sweep. Branch refreshes are disabled; already-proven "
            "heads may still be judged and merged.",
        )
    ineligible = [pull for pull in pulls if not is_sweep_candidate(pull)]
    for pull in ineligible:
        print(
            f"PR #{pull.get('number')}: armed but not an open, non-draft PR targeting "
            "main; controller will not refresh or merge it.",
            flush=True,
        )
    pulls = [pull for pull in pulls if is_sweep_candidate(pull)]
    if not pulls:
        print(
            f"No eligible open pull requests labeled {MERGE_ON_GREEN_LABEL}.",
            flush=True,
        )
        return 0

    # GLOBAL workload backpressure, before any branch mutation. The old cap of eight
    # PER SWEEP still launched dozens of CI runs when completed workflows started a
    # new full sweep roughly every minute. Active ci.yml runs are the durable state
    # shared by those sweeps, so only the genuinely free repo-wide slots remain
    # available to `take_refresh`. An unreadable census means zero NEW workload, not
    # zero merging: already-proven heads continue through every correctness gate.
    refresh_load_detail = ""
    try:
        active_pr_proofs = in_flight_pr_proofs(repo, read_token)
    except Exception as exc:
        active_pr_proofs = None
        refresh_load_detail = f"census failed ({exc}); new refreshes paused"
    budget.refresh_lease = refresh_lease
    # A durable owner closes the update-branch -> Actions indexing gap. Count only
    # the unindexed gap as an extra reservation: once an exact-current-head ci.yml
    # run is visible, GitHub's active-run census already includes that workload.
    reservation_count = refresh_lease_reservation_count(
        repo, read_token, refresh_lease, pulls
    )
    effective_active_proofs = (
        active_pr_proofs
        + reservation_count
        if active_pr_proofs is not None
        else None
    )
    if active_pr_proofs is None or not refresh_lease.readable:
        budget.max_refreshes = 0
        refresh_load_detail = refresh_load_detail or "census/lease unreadable; new refreshes paused"
    elif effective_active_proofs is not None and effective_active_proofs >= MAX_IN_FLIGHT_PR_PROOFS:
        # The hard cap alone can starve forever when session traffic never drops.
        # One durable lease is the fairness escape: at most one controller-owned
        # proof is admitted above the cap, and every later sweep sees the same owner.
        budget.max_refreshes = HIGH_LOAD_FAIR_REFRESHES
        budget.requires_refresh_lease = True
        refresh_load_detail = (
            f"{active_pr_proofs} indexed pull-request ci run(s) plus "
            f"{reservation_count} unindexed durable "
            f"reservation(s), global cap "
            f"{MAX_IN_FLIGHT_PR_PROOFS}; one durable high-load refresh lane "
            + (
                f"is owned by PR #{refresh_lease.owner_number}"
                if refresh_lease.owner_number is not None
                else "is available"
            )
        )
    else:
        available_refreshes = max(
            0, MAX_IN_FLIGHT_PR_PROOFS - int(effective_active_proofs or 0)
        )
        budget.max_refreshes = min(budget.max_refreshes, available_refreshes)
        refresh_load_detail = (
            f"{active_pr_proofs} indexed pull-request ci run(s) plus "
            f"{reservation_count} unindexed durable "
            f"reservation(s), global cap "
            f"{MAX_IN_FLIGHT_PR_PROOFS}, {budget.max_refreshes} refresh attempt(s) "
            "available this sweep"
        )
    budget.refresh_context = refresh_load_detail
    print(f"PR proof load: {refresh_load_detail}.", flush=True)

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

    pull_cap = budget.pull_cap
    ordered = sweep_order(
        pulls,
        trigger_head_sha=trigger_head_sha,
        refresh_lease_number=refresh_lease.owner_number,
        cap=pull_cap,
    )
    considered = ordered[:pull_cap]
    deferred = ordered[pull_cap:]

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
            f"requests. READ_TOKEN's observed core limit is "
            f"{budget.last_limit if budget.last_limit is not None else 'unreadable'} "
            f"requests/hour, which sets this pass's cap to {pull_cap}; an unreadable "
            f"limit falls back to {FALLBACK_PULL_CAP}. An uncapped sweep at high trigger "
            "volume can empty the bucket and make every later sweep 403. "
            f"The order rotates every {ROTATION_BUCKET_SECONDS // 60} minutes, so no "
            f"pull request can be starved. Deferred to a later sweep: {shown}{more}.",
        )
        tally["cap-deferred"] = len(deferred)

    repair_slot_used = False
    terminal_retry_reason = ""
    lease_watchdog_reason = ""
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
        reconcile_only = False
        if baseline_state != "green":
            is_repair = MAIN_RED_REPAIR_LABEL in label_names(pull)
            if not is_repair or repair_slot_used:
                if refresh_lease.owns(pull):
                    reconcile_only = True
                else:
                    number = pull.get("number")
                    print(
                        f"PR #{number}: source main baseline is {baseline_state}; "
                        "leaving it armed behind the circuit breaker.",
                        flush=True,
                    )
                    verdict = "baseline-blocked"
                    tally[verdict] = tally.get(verdict, 0) + 1
                    continue
            elif is_repair:
                # At most one repair candidate per pass. Even two individually green
                # repairs have not been jointly proven against the broken baseline.
                repair_slot_used = True
        try:
            sweep_options = {"reconcile_only": True} if reconcile_only else {}
            verdict = sweep_pull(
                repo, pull, read_token, merge_token, freshness, proof, budget,
                blocked_names, **sweep_options,
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
        if verdict in {
            "authorization-unreadable",
            "lease-lost",
            "lease-rotation-deferred",
            "lease-release-retry",
        }:
            lease_watchdog_reason = (
                f"refresh generation on PR #{pull.get('number')} returned {verdict}"
            )
        elif verdict in {
            "lease-generation-incomplete",
            "lease-generation-pending",
            "lease-generation-waiting",
        }:
            # Active ci/fences jobs generate their own completion wake. A minute-by-
            # minute full-sweep chain during a normal 30-90 minute proof would burn
            # the historical 1,000-request bucket. Missing/same-head states use the
            # 10-minute level-triggered schedule as a bounded watchdog; it needs at
            # most 12 passes over the two-hour hard TTL, not 120 self-dispatches.
            print(
                f"PR #{pull.get('number')}: refresh generation is {verdict}; "
                "workflow completion or the bounded recovery schedule supplies "
                "the next sweep without minute-by-minute self-dispatch.",
                flush=True,
            )
        if refresh_lease.owns(pull):
            release_reason = ""
            if verdict in {
                "blocked",
                "conflict",
                "empty-diff",
                "merged",
                "already-merged",
                "already-closed",
                "draft",
                "wrong-base",
                "disarmed",
            }:
                release_reason = f"owner reached definitive verdict {verdict}"
            elif verdict in {
                "updated",
                "re-proving",
                "rebased",
                "head-moved",
                "update-retry",
            }:
                # Bridge update-branch -> Actions indexing. If no workflow appears,
                # the chained sweep above eventually ages and releases the lease.
                lease_watchdog_reason = (
                    f"refresh write/retry on leased PR #{pull.get('number')}"
                )
            if release_reason:
                release_target = pull
                if verdict in {"blocked", "conflict", "empty-diff"}:
                    live_release_pull, release_authorization = live_authorized_pull(
                        repo, pull, read_token, require_refresh_lease=True
                    )
                    if live_release_pull is None:
                        lease_watchdog_reason = (
                            f"terminal lease release on PR #{pull.get('number')} "
                            f"lost authorization ({release_authorization})"
                        )
                        continue
                    release_target = live_release_pull
                if refresh_lease.release(release_target, release_reason):
                    lease_watchdog_reason = (
                        f"released refresh lease on PR #{pull.get('number')}"
                    )
                else:
                    lease_watchdog_reason = (
                        f"lease release retry on PR #{pull.get('number')}"
                    )
        if verdict in {"merged", "already-merged", "main-moved", "merge-unknown"}:
            # Main-dependent state above is one immutable snapshot. The merge just
            # advanced main, so using that snapshot for a second PR would skip the
            # first merge's definition/surface change. One merge consumes the
            # snapshot; the next level-triggered sweep rebuilds it from live main.
            left = len(considered) - index - 1
            if left:
                tally["snapshot-deferred"] = (
                    tally.get("snapshot-deferred", 0) + left
                )
            _annotate(
                "notice",
                "merge-on-green",
                f"PR #{pull.get('number')}: verdict {verdict} consumed or invalidated "
                "this immutable main freshness snapshot; ending it before judging "
                f"{left} remaining pull request(s).",
            )
            terminal_retry_reason = f"PR #{pull.get('number')} verdict {verdict}"
            break

    # AFTER the pull-request pass, deliberately: the dispatch decision needs to see
    # what this sweep was actually unable to answer, which only exists once the pass
    # has run. Never fatal — it returns a string, it does not raise.
    baseline = ensure_main_baseline(repo, proof, blocked_names, merge_token)

    wake_reason = terminal_retry_reason or lease_watchdog_reason
    if (
        not wake_reason
        and budget.requires_refresh_lease
        and refresh_lease.claim_attempted
        and refresh_lease.owner_number is None
    ):
        wake_reason = "high-load refresh claim was not durably affirmed"
    self_wake = (
        ensure_self_wake(
            repo,
            read_token,
            merge_token,
            current_run_id,
            wake_reason,
        )
        if wake_reason
        else "not needed"
    )

    print(
        "merge-on-green sweep complete: "
        + ", ".join(f"{count} {verdict}" for verdict, count in sorted(tally.items()))
        + f" ({freshness.commit_file_reads} main commit(s) classified, "
        + f"{budget.refreshes_used}/{budget.max_refreshes} effective refresh "
        f"slot(s) used ({budget.refresh_context}), "
        + f"~{budget.last_seen if budget.last_seen is not None else '?'} API requests left"
        + f"; {proof.describe()}; baseline: {baseline}"
        + f"; source-baseline: {source_baseline}; self-wake: {self_wake})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
