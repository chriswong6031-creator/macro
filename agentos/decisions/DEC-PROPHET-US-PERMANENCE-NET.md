---
key: PROPHET-US-PERMANENCE-NET
question: >
  After the August 2026 27-day US Prophet Live freeze (dark with every process
  signal green), how should the estate be hardened against the SAME class of
  blind spot recurring — a new parallel watchdog/registry, or extensions of the
  three existing instruments (scripts/freshness_sentinel.py,
  scripts/check_nightly_liveness.py, scripts/prophet_rescue.py)?
answer: >
  Extend the three existing instruments; never build a parallel JSON-registry
  design. PR-1 adds: four additive checks to freshness_sentinel.py (a new
  us_standouts SURFACES entry with two new generic surface-spec extensions —
  cross_field_asof and non_vacuous; an intake-identity check on the existing
  prophet_us surface; a served-vs-R2 pass_ts agreement check on prophet_live;
  a heartbeat write into the existing /live/staleness.json artifact); a new
  Check E in check_nightly_liveness.py that reads that heartbeat from the
  GitHub failure domain, plus the same intake-identity check on Check C's
  existing index read, plus a lane-latch exemption so an acceptance-step red
  cannot be quietly downgraded; an extension of prophet_rescue.py's existing
  NO_COHORT verdict (not a new verdict) with the same intake-identity
  predicate, an hourly cron closing a 10-hour daily coverage hole, and one
  triage line in its issue template; and one brand-new file,
  scripts/prophet_board_acceptance.py, run as a step inside daily.yml's ENGINE
  job immediately after the step that writes the Prophet board — an
  alarm-never-a-gate that checks the run's own output against itself before
  any other instrument gets a chance to.
rationale: >
  The incident review found the failure mode was not "no watchdog" — it was
  three real watchdogs each blind to one specific shape (a semantic-clock
  freeze under a moving mtime; a UI date mislabel reading as fresh; a warn-only
  exit-0 instrument nobody escalated on; a dedup window swallowing a real
  page). A fourth parallel instrument (a JSON registry of "known-good" states,
  considered and rejected — see alternatives) would have inherited the SAME
  failure-domain-sharing risk every prior instrument already carries and added
  a FIFTH thing that could itself go stale silently. Extending the three
  existing, already-tested, already-deployed instruments means every new check
  inherits their existing verdict discipline (blind != breach; a network
  failure degrades to INDETERMINATE, never a false green) for free, and keeps
  the fleet's mental model at three watchdogs plus one acceptance alarm rather
  than an ever-growing pile of independent scripts nobody remembers to check.
  The acceptance script is new BECAUSE none of the three existing instruments
  can occupy its position in time: all three grade the estate from OUTSIDE the
  run that produced it, on a later cadence, so none of them can say "this
  run's own board is internally consistent" at the moment the bytes are still
  on the runner's disk. It runs alarm-only (continue-on-error) because a
  publish-time internal-consistency check is exactly the kind of instrument
  that must never itself become a second way to take the nightly down.
alternatives:
  - option: >
      A single new JSON "surface registry" file that all watchdogs read from,
      replacing the three instruments' independently-duplicated SURFACES/
      MARKET_BOARDS/decide() logic with one shared source of truth.
    why_not: >
      Killed by adversarial (opus) review of the first design. A shared
      registry is a FIFTH thing that can go stale or be malformed, and a bug
      in the one shared reader would blind every watchdog that depends on it
      simultaneously — precisely the failure-domain-sharing this whole program
      exists to reduce. The three existing instruments are independent BY
      DESIGN (see each module's own docstring): freshness_sentinel runs on the
      VPS outside GitHub entirely; check_nightly_liveness runs GitHub-hosted,
      deliberately off the self-hosted pool the nightly runs on;
      prophet_rescue explicitly refuses to import engine.alert_triage so it
      can survive a broken engine tree. A shared registry module would erase
      that independence for marginal DRY savings on a ~10-line predicate.
  - option: >
      Import the shared intake-identity predicate from one module instead of
      duplicating it across freshness_sentinel.py, check_nightly_liveness.py,
      prophet_rescue.py, and prophet_board_acceptance.py.
    why_not: >
      Same failure-domain argument at smaller scale. A bug in one shared copy
      of the ~10-line intake-identity check would blind all four watchdogs
      identically — exactly the shape #5362 (one file, one bug, every
      downstream instrument dark) already taught this program to distrust.
      Four independently-maintained copies cost a small sync burden and buy
      genuine redundancy: an error in one instrument's copy leaves the other
      three unaffected.
  - option: >
      Make scripts/prophet_board_acceptance.py's failure BLOCK the nightly
      deploy (a hard gate) rather than alarm-only.
    why_not: >
      Explicitly out of scope per the commissioning packet ("an ALARM after
      publish, not a gate"). A brand-new internal-consistency check with zero
      production hours behind it is exactly the kind of thing that should not
      have the power to take a healthy nightly down on its own false positive;
      it earns gate authority, if ever, only after a measured production
      track record.
  - option: >
      Implement the full escalation ladder (item 3b: [DAY N] issue-title
      prefix + a distinct engine.alert_triage type_ per day-level) and the
      self-withdraw dispatch-cancel (item 3c) as originally commissioned.
    why_not: >
      Both conflict with standing, tested invariants this same file already
      carries. scripts/prophet_rescue.py's own module docstring states it
      calls its LOCAL stdlib push_ops_alert "rather than
      engine.alert_triage.push_ops_alert ON PURPOSE: this lane must survive a
      repo whose engine tree does not import" — routing the escalation ladder
      through engine.alert_triage as commissioned would undo that independence
      guarantee for the sake of one alert's dedup window. The self-withdraw
      cancel conflicts even more directly: prophet_rescue.py's own §0.4
      invariant (c) states "NEVER cancel anything. There is no cancel code
      path in this file and test_no_cancel_code_path_exists fails the build if
      one appears," and CLAUDE.md's standing house law states a kill is
      invisible to every staleness instrument owned here and "killing a
      genuinely wedged production run is an OPERATOR call — hand it over,
      don't take it." Both were deliberately withheld from this PR rather than
      improvised past a documented safety invariant; see GAPS in the
      commissioning packet and research/PROPHET_US_PERMANENCE_NET_2026-08-27.md.
  - option: (none considered) for the single-budget-shape choice below
    why_not: n/a
evidence:
  - "scripts/freshness_sentinel.py module docstring, PROPHET_MAX_SESSIONS_BEHIND / ARMED_PACK_MAX_SESSIONS_BEHIND / PROPHET_LIVE_MAX_AGE_MINUTES comments — the pre-existing 'breach by the second miss' shape this PR's new us_standouts entry and Check E reuse (asof_max_sessions_behind=1; 3 missed sentinel cadences)."
  - "python3 -m pytest tests/test_prophet_surface_net.py tests/test_prophet_rescue.py tests/test_freshness_sentinel.py tests/test_check_surface_freshness.py tests/test_gh_annotation_line_start.py tests/test_nightly_liveness.py -q — 354 passed (local run, sparse worktree; data/site/mockups/verify_shots not checked out, not read by these suites)."
  - "scripts/prophet_rescue.py:9-25 module docstring — the local push_ops_alert / no-engine-import design; scripts/prophet_rescue.py's §0.4(c) invariant + tests/test_prophet_rescue.py::test_no_cancel_code_path_exists — the cancel-path prohibition."
  - "site/prophet/index.json (origin/main, 2026-08-25 vintage, read via git show) — the real intake block shape this PR's HEALTHY_INTAKE test fixture mirrors (admitted 41 = 23 duplicate_id_blocked + 6 reorigination_blocked + 3 validation_failed + 9 originated; unaccounted 0; lossless true)."
  - "engine/prophet_live/r2io.py — LIVE_KEY = 'live_flow/prophet_live.json', the private/operational R2 mirror scripts/prophet_live_evaluator.py already publishes to and this PR's served-vs-R2 agreement check (freshness_sentinel.prophet_live_r2_agreement) reads, credentials via engine.prophet_live.r2io.client()."
affects:
  - "scripts/freshness_sentinel.py"
  - "scripts/check_nightly_liveness.py"
  - "scripts/prophet_rescue.py"
  - "scripts/prophet_board_acceptance.py"
  - ".github/workflows/daily.yml"
  - ".github/workflows/prophet-rescue.yml"
  - "research/PROPHET_US_PERMANENCE_NET_2026-08-27.md"
confidence: medium
reversibility: easy
decided_by: session (ROUTE:build worker, commissioned 2026-08-27)
decided_at: 2026-08-27
review_by: 2026-09-10
---

## One budget shape

Every session-grained freshness budget this PR adds (us_standouts
asof_max_sessions_behind, the intake-identity check) reuses
PROPHET_MAX_SESSIONS_BEHIND = 1 — the existing "breach by the second miss"
shape freshness_sentinel.py's prophet_us and armed-pack entries already use.
Check E's heartbeat budget (3 sentinel cadences = 90 minutes) and the
prophet_live R2-agreement budget (one 5-minute evaluator tick) are the two
NEW budget shapes this PR introduces, both because the artifacts they grade
(a 30-minute-cadence heartbeat; a 5-minute-cadence evaluator pass) run at a
finer grain than any session-based budget can express — see each constant's
own comment in-file for the specific incident it is sized against.

## The acceptance step's honest scope

scripts/prophet_board_acceptance.py is an ALARM AFTER PUBLISH, never a GATE.
It cannot see a run that never reaches its step (cancelled/wedged before it —
that class belongs to check_nightly_liveness.py and prophet_rescue.py), it is
a correct no-op on a night the engine job never runs (DST/weekend), and it is
withheld from blocking the deploy via `continue-on-error: true` specifically
because a zero-production-hours internal-consistency check must not itself
become a second way to take a healthy nightly down.

## Not done in this PR (see GAPS)

The escalation ladder ([DAY N] title + per-day-level alert type) and the
self-withdraw dispatch-cancel (items 3b/3c of the commissioning packet) are
both withheld — see the alternatives above for the specific standing
invariants each would have broken. Coverage for the paid card payload
(site/premiumdata/us_stocks.json), which templates/_us_board_cards.html.j2
and templates/_us_prophet_plan_cards.html.j2 both consume but which no SCOPE
item in the commissioning packet named, is left as a documented, test-pinned
gap (tests/test_prophet_surface_net.py::test_premium_payload_referenced_by_the_template_is_a_known_gap)
rather than an uncommissioned SURFACES entry.
