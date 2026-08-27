# Prophet US Permanence Net

**Date:** 2026-08-27 (commissioned as PR-1, ROUTE: build, off a Fable/main-loop
adjudication of the August 2026 27-day US Prophet Live freeze)
**Status:** PR-1 delivered (this document); PR-2+ not commissioned
**Extends:** `research/NIGHTLY_RESILIENCE_AND_LIVE_TRANSITION_MASTERPLAN_2026-08-06.md`
(the freshness_sentinel/check_nightly_liveness/prophet_rescue instruments this
program extends), `research/PROPHET_US_AVAILABILITY_HARDENING_2026-08-14.md`
(prophet_rescue.py's own founding incident)
**Does not create:** a fourth parallel watchdog, a shared JSON surface
registry, a hard gate on the nightly deploy, or any change to
`engine/signal_quality.py`, `engine/prophet_bridge.py`,
`publication_required()`, B1's schedule-only reconcile step trigger, or any
pre-existing SURFACES budget.

---

## §0 ACCEPTANCE GATES

PR-1 is **not done unless**:

1. **Every targeted suite is green**, reported with tallies:
   `python3 -m pytest tests/test_prophet_surface_net.py tests/test_prophet_rescue.py
   tests/test_freshness_sentinel.py tests/test_check_surface_freshness.py
   tests/test_gh_annotation_line_start.py tests/test_nightly_liveness.py -q`
   — 354 passed, 0 failed (measured 2026-08-27, sparse worktree; `data/`,
   `site/`, `mockups/`, `verify_shots/` not checked out and not read by these
   suites).
2. **`python3 scripts/agentos.py validate` exits 0** with
   `agentos/decisions/DEC-PROPHET-US-PERMANENCE-NET.md` in the tree.
3. **The new test file is wired into a CI run**, not just committed:
   `.github/ci/legacy-jobs.yml`'s "prophet rescue lane" step runs
   `tests/test_prophet_surface_net.py` alongside its four siblings, and
   `.github/workflows/ci.yml`'s contract-delta path list carries
   `scripts/prophet_board_acceptance.py` + `tests/test_prophet_surface_net.py`
   as a pair (the `check_surface_freshness.py` precedent).
4. **The branch is pushed and a PR is open**, not armed for merge-on-green and
   not merged — the commissioning session reviews and owns the merge per the
   ROUTE:build contract.
5. **Two production proofs, NOT gated on this PR's merge** (tracked here so a
   later session can close them without re-deriving what "done" means):
   - **First acceptance-step pass on a scheduled `daily.yml` run.**
     `scripts/prophet_board_acceptance.py` must be OBSERVED to run inside a
     real scheduled (not `workflow_dispatch`) nightly and either pass cleanly
     or print its `::error title=prophet-board-acceptance::` annotation with a
     diagnosable message. Until this is observed, the acceptance script is
     BUILT_NOT_PROVEN — its unit tests pin its logic against synthetic
     fixtures, not against a real nightly's actual on-disk shape at that exact
     point in the job.
   - **First Check E heartbeat grade against the live sentinel.**
     `scripts/check_nightly_liveness.py`'s Check E must be observed reading a
     REAL `/live/staleness.json` (served from the VPS, carrying the
     `heartbeat` key this PR adds to `scripts/freshness_sentinel.py`) rather
     than a synthetic fixture. Until the VPS's `macro-sentinel.timer` runs a
     pass with this PR's code, Check E is BUILT_NOT_PROVEN against the real
     artifact shape.
   Per the standing law on hardcoded clocks and unproven builds
   (`research/DO_NOT_REBUILD.md` epistemics discipline): do not claim either
   proof from a green unit-test run, and never dispatch `daily.yml` or the
   VPS sentinel timer manually to manufacture it — both fire on their own
   schedules, and the honest report is "not yet observed" until they do.

---

## Background — the August 2026 incident

The US Prophet Live 5-minute evaluator's `pass_ts` froze at
`2026-07-30T17:20:53Z` and stayed frozen for 27 days while the served file's
own mtime moved on schedule the entire time (the evaluator rewrote the file
whole, every 5 minutes, with the SAME frozen payload). Every process signal
read green: the workflow ran, the file re-published, no check flagged a
staleness verdict, because nothing anywhere graded the artifact's own semantic
clock (`meta.pass_ts`) — every existing instrument graded either a different
artifact, a coarser cadence, or an mtime that cannot see a re-stamped freeze.
In parallel, a UI date mislabel let a stale board read as fresh to a human
glance; the one instrument that DID name the board's exact path
(`scripts/check_surface_freshness.py`-adjacent work) was warn-only and exited
0; pages routed through a webhook whose dedup window (`engine/alert_triage.py`
push_ops_alert, default 6h) could swallow a real re-fire; and open
`prophet-outage` issues sat unread for five days because nothing escalated a
persisting breach.

An opus red-team of the first proposed fix (a new parallel JSON "surface
registry" all watchdogs would read from) rejected it: a shared registry is a
fifth thing that can itself go stale, and a bug in the one shared reader would
blind every dependent watchdog identically — the same failure-domain-sharing
class that let the 27-day freeze go unseen. The mandate for PR-1: **small,
additive extensions of the three existing instruments, plus one new
publish-time alarm that occupies a position in time none of the three can
reach** (they all grade from outside the run that produced the artifact, on a
later cadence; the acceptance script grades the run's own bytes before it
leaves the runner).

---

## What PR-1 delivers

### 1. `scripts/freshness_sentinel.py` — four additive checks

- **`us_standouts` SURFACES entry** (item 1a): the served board of record
  (`site/factordata/us_standouts.json`), one layer above the Prophet plan
  index — a frozen board here is upstream of everything the existing
  `prophet_us` entry can see. Two new GENERIC surface-spec extensions land
  with it, usable by any future surface: `cross_field_asof` (asserts one
  field equals a second, nested field — here `as_of == staleness.price_through`,
  the same re-stamp trap the module docstring documents at length one layer
  down) and `non_vacuous` (asserts named list/dict fields are non-empty — here
  `buy` and `lane_counts`).
- **Intake-identity check on `prophet_us`** (item 1b): a new
  `intake_identity_breach()` predicate, wired onto the EXISTING `prophet_us`
  surface via a new `intake_identity: True` spec key. `source_asof`'s own
  budget and comment are untouched.
- **`prophet_live` served-vs-R2 agreement** (item 1c): a new
  `prophet_live_r2_agreement()` function, called from `run()` only when the
  served read of `/live/prophet_live.json` succeeded (i.e. only when the
  live-window gate already decided the artifact is in scope). Compares the
  served file's `meta.pass_ts` against the SAME artifact's mirror in the
  private/operational R2 bucket (`engine.prophet_live.r2io.LIVE_KEY`, read via
  a lazy, failure-guarded `boto3` client). Absent credentials degrade to a
  named stderr warning, never a page; a parsed divergence beyond one 5-minute
  evaluator tick is a breach.
- **Heartbeat write** (item 1d): `run()` now writes a `heartbeat` block
  (`last_pass_utc`, `cadence_minutes`, a per-surface status summary) into the
  existing `/live/staleness.json` artifact, additive alongside every
  pre-existing top-level key. Verified first: `scripts/build_output_health.py`
  is the only other module touching this path, and it only READS it —
  `freshness_sentinel.py` is the sole writer, so there is no other writer's
  key to clobber.

### 2. `scripts/check_nightly_liveness.py`

- **The same intake-identity check on Check C's existing index read** (item
  2a), independent of `MARKET_BOARDS`, which stays untouched.
- **New Check E** (item 2b): fetches `/live/staleness.json` anonymously
  (stdlib `urllib`, matching the module's existing transport discipline) and
  grades the sentinel's own heartbeat — a heartbeat older than 3 sentinel
  cadences (90 minutes) is a `fail_reason`, closing the loop the other way:
  this check watches the VPS sentinel FROM the GitHub failure domain, the
  same way the sentinel watches the rest of the estate from the VPS. A
  `_HEARTBEAT_NOT_REQUESTED` sentinel default means a caller that never
  mentions Check E (every pre-existing test in this file) gets nothing from
  it — not even a warning — so the ~180 pre-existing assertions on exact
  warning/fail_reason shapes are not retroactively broken.
- **The lane-latch acceptance exemption** (item 2c): at the LANE LATCH branch,
  a precomputed `acceptance_failed` fact (from a NEW, narrowly-scoped
  `fetch_run_jobs`/`job_failed_at_acceptance_step` pair, called at most once
  per wake and only when a run since the fire boundary actually failed to
  conclude with success) prevents the latch from downgrading a run whose
  board-acceptance step also failed to a quiet warning.

### 3. `scripts/prophet_rescue.py` + `.github/workflows/prophet-rescue.yml`

- **NO_COHORT extended, not duplicated** (item 3a): the same
  intake-identity predicate now also trips the EXISTING `NO_COHORT` verdict,
  alongside the original empty-cohort-with-eligible-candidates condition.
  `data_current` stays the precondition for both.
- **Hourly cron, full 24h coverage** (item 3d): replaced the two-line schedule
  (`"40 23 * * *"` + `"40 0-13 * * *"`, 15 wakes/day) with a single
  `"40 * * * *"`, closing the 13:40Z→23:40Z daytime hole. Verified: the
  `cancel-in-progress: false` concurrency group tolerates it — each run is
  capped at `timeout-minutes: 10`, an order of magnitude under the 60-minute
  wake interval.
- **Issue-template triage line** (item 3e): the receipt template now adds one
  line naming `gh api repos/{owner}/{repo}/rulesets` whenever a STALE or
  STRAND verdict fires, pointing at the GH013-freeze class documented in
  `research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md`.
- **Escalation ladder (item 3b) and self-withdraw cancel (item 3c): NOT
  DELIVERED.** See §Deviations below — both conflict with standing, tested
  invariants in this same file and in CLAUDE.md, and were withheld rather than
  improvised past a documented safety boundary.

### 4. `scripts/prophet_board_acceptance.py` (new) + one `daily.yml` step

A new post-publish alarm, run as the LAST prophet-owned step of the ENGINE
job, immediately after "Prophet nightly" and before "checkpoint Prophet
outputs to main" — same job, same runner, same on-disk bytes, so there is no
cross-job pull race. It asserts, for the session this run is producing: an
origination receipt exists for this run id WHEN the cohort is non-empty (a
zero-origination night legitimately writes none); the intake identity holds;
`us_standouts.as_of` equals both the expected session and its own
`staleness.price_through`; every index plan recorded for this session has its
plan file on disk; every newly-originated plan carries `recorded_at`. On
breach it prints one bare, line-start `::error title=prophet-board-acceptance::`
annotation (never through a logger — the house law
`tests/test_gh_annotation_line_start.py` enforces repo-wide), calls
`engine.alert_triage.push_ops_alert` with its own distinct `type_`
(`prophet_board_acceptance_failed`), and exits nonzero — under
`continue-on-error: true`, so it can never block the deploy. It is an ALARM,
never a GATE; see its own module docstring for the full honest-scope
statement (dead if the run is cancelled before it; a correct no-op on a
DST/weekend no-op night).

### 5. `tests/test_prophet_surface_net.py` (new)

Pins: the mechanism-agnostic template-dereference coverage contract (parses
`templates/dashboard.html.j2` + `_us_board_cards.html.j2` +
`_us_prophet_plan_cards.html.j2` for the artifacts they consume and asserts
each is named by a grader — `us_standouts` and the Prophet index pass; the
paid `premiumdata/us_stocks.json` payload is pinned as a KNOWN, documented gap
rather than silently covered, see §Deviations); the shared intake-identity
predicate across all four instruments (healthy/wipeout/unaccounted/wedge/
absent shapes); `recorded_at` presence; the acceptance script's behaviors
including its annotation line-start shape and its zero-cohort-no-receipt-owed
exemption; the lane-latch exemption; the heartbeat write→Check-E-grade round
trip; the served-vs-R2 agreement logic with R2 mocked via `monkeypatch`; the
NO_COHORT reuse and the issue-template triage line. Wired into
`.github/ci/legacy-jobs.yml`'s existing "prophet rescue lane" step and into
`.github/workflows/ci.yml`'s contract-delta path list.

### 6. Records

`agentos/decisions/DEC-PROPHET-US-PERMANENCE-NET.md` (this program's DEC) and
this masterplan.

---

## Deviations from the commissioning packet

1. **Item 3b (escalation ladder) — NOT IMPLEMENTED.** The commission asked
   for the `push_ops_alert` call to gain a distinct `type_` per day-level "so
   `engine/alert_triage.py`'s (source, type_) dedup window cannot swallow the
   ladder." But `scripts/prophet_rescue.py`'s own module docstring states,
   verbatim: *"Stdlib POST rather than `engine.alert_triage.push_ops_alert` ON
   PURPOSE: this lane must survive a repo whose engine tree does not import."*
   Routing the escalation ladder through `engine.alert_triage` as literally
   commissioned would undo that independence guarantee. Building the
   day-persistence tracking through the file's OWN dedup mechanism
   (`should_file_receipt` / `last_receipt_verdicts`, keyed on a per-session
   issue) instead would require reading and PATCHing prior days' issue titles
   — extra API calls this file's own documented "REST BUDGET" section pins to
   an exact count per wake, which a fully-correct ladder implementation could
   not respect without amendment. Given the direct conflict with a documented
   design decision AND the added complexity/risk to a safety-critical,
   heavily-tested 1500+ line file, this was deliberately deferred rather than
   improvised. A follow-up PR should either (a) get explicit sign-off to
   loosen the "never import engine.alert_triage" rule for this ONE call, or
   (b) design a day-tracking mechanism against `find_open_issue`'s ALREADY
   read issue list (it fetches up to 50 open `prophet-outage` issues per
   call — the day count can be derived from that same response with no new
   read) instead of the literal `type_`-based dedup escape the commission
   named.
2. **Item 3c (self-withdraw cancel) — NOT IMPLEMENTED.** The commission
   itself gated this on verification: *"verify the rescue workflow's token
   permissions allow the cancel API before wiring — if permissions forbid it,
   deliver the rest and record the gap."* The permission check passes
   (`actions: write` covers the cancel endpoint), but a DIFFERENT, more
   fundamental blocker applies: `scripts/prophet_rescue.py`'s own §0.4
   invariant (c) states *"NEVER cancel anything. There is no cancel code path
   in this file and `test_no_cancel_code_path_exists` fails the build if one
   appears"* — and CLAUDE.md's standing house law states *"killing a
   genuinely wedged production run is an OPERATOR call — hand it over, don't
   take it"* and that a cancel is *"invisible to every staleness instrument we
   own."* Adding ANY cancel code path here, however narrowly scoped, directly
   contradicts a deliberate, tested, and currently-enforced safety invariant.
   Per the commissioning packet's own instruction ("Where in-file comments
   contradict this commission, STOP on that item... report the conflict under
   DEVIATIONS rather than improvising"), this item is withheld. It should not
   be attempted by a future PR without an explicit operator ruling that
   supersedes both the in-file invariant and the CLAUDE.md law.
3. **Premium payload coverage — a documented gap, not a silent omission.**
   `templates/_us_board_cards.html.j2` and `_us_prophet_plan_cards.html.j2`
   both consume `site/premiumdata/us_stocks.json`, but no SCOPE item (1-4)
   named this artifact, so PR-1 adds no grader for it. Adding an
   uncommissioned `SURFACES` entry would have been scope creep beyond the
   frozen packet.
   `tests/test_prophet_surface_net.py::test_premium_payload_referenced_by_the_template_is_a_known_gap`
   pins this as a KNOWN gap (it fails loudly, on purpose, the day a future PR
   adds coverage and forgets to flip the assertion) rather than letting the
   coverage-contract test silently ignore it.
