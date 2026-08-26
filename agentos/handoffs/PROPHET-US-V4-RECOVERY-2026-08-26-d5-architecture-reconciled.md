---
workstream: WS:PROPHET-US-V4-RECOVERY
session: mas122-d5-amend
model: opus
ended_because: blocked
prs: [6275, 6405]
decisions:
  - DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS
  - DEC:PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY
discoveries:
  - DSC:PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1
  - DSC:PROPHET-D5-EARNINGS-COVERAGE-OVERLAPS-B1-CANDIDATE-POOL
mission: >
  Under a direct Chairman commission: reconcile stale Prophet V4 program state, close
  B1's natural-production acceptance, reconcile the open Cell F / D5 architecture
  carrier into one canonical truth, and build the first real D5 Earnings vertical.
  This session completed the reconciliation half and is blocked on a natural-time gate
  for the acceptance half.
state_before: >
  B1 merged 2026-08-26T00:13:07Z as 878930b3b2f9849e120391fa461ed528f32d2e3c (PR #6405)
  and sat at BUILT_PENDING_NATURAL_ACCEPTANCE with no production generation. PR #6275
  was open, non-draft, unlabeled, 853 commits behind main, carrying the frozen
  2026-08-22 Cell F D5 evidence contract plus a stale copy of this workstream record.
  D5 runtime was blocked behind B1 acceptance.
changed:
  - path: research/prophet_v4/flagship_cells/CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md
    what: >
      New binding amendment document A7-A13 continuing the A1-A6 series. A7 closes the
      point-in-time seam by naming the revision-chain reader as the only lawful
      decision-time Earnings access path and forbidding read_event_workspace there,
      with a normative clock binding table from the contract's abstract clock names to
      owner-native field names. A8 binds the contract's REQUIRED decision_cut to
      B1-owned opened_at/opened_session and sets tradable_at NOT_ASSERTED until V4-B4.
      A9 requires episode_ref to pin the B1 generation_id. A10 makes the missingness
      vocabulary a cross-family superset with a per-family mintable register. A11
      corrects the canonical-episode gate to MERGED / BUILT_NOT_PROVEN. A12 corrects the
      Earnings trajectory row. A13 closes the episode-to-Earnings identity bridge.
  - path: research/prophet_v4/flagship_cells/CELL_F_D5_EVIDENCE_TRANSLATION_AND_TRAJECTORY_CONTRACT_2026-08-22.md
    what: >
      Ten inline AMENDED 2026-08-26 markers inserted at each superseded clause so a
      builder cannot read stale law without seeing the override. The 2026-08-22 body is
      otherwise preserved exactly as authored.
  - path: agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md
    what: >
      Conflict resolved main-side. Carries main's bytes plus only the D5 additions the
      carrier intended, plus a fourth do_not_redo fencing the non-PIT-safe Earnings
      readers and an updated d5 wave title recording the reconciliation.
  - path: agentos/discoveries/DSC-PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1.md
    what: >
      Status note recording that the falsifier is half met - implementation now exists,
      real production episode proof does not - so the discovery still stands and D5
      runtime remains blocked.
  - path: research/prophet_v4/B1_NATURAL_ACCEPTANCE_PROBE.md
    what: >
      Read-only acceptance probe for the B1 natural gate, asserting the acceptance contract
      through B1's own canonical reader so it cannot drift from the plane it checks. Validated
      at 30 checks / 0 fail against a real generation from B1's own nightly test.
  - path: agentos/discoveries/DSC-PROPHET-D5-EARNINGS-COVERAGE-OVERLAPS-B1-CANDIDATE-POOL.md
    what: >
      New discovery fixing the honest acceptance shape for the first D5 vertical: which
      issuers the Earnings owner covers, which of them are in B1's candidate pool, and
      why a NOT_COVERED majority is the truth rather than an adapter bug.
verified:
  - claim: >
      The carrier no longer reverts merged truth. Its workstream copy is main's bytes
      plus 27 added lines, with the one removed line being the d5 wave title's own
      closing line, replaced by an extended one.
    command: "git diff origin/main -- agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md"
    result: "27 insertions, 1 deletion; no ratified content removed"
  - claim: Agent OS records remain schema-clean after every edit in this wave.
    command: "python3 scripts/agentos.py validate"
    result: "760 records, 0 error(s), 43 pre-existing review-overdue warnings"
  - claim: >
      read_event_workspace is not point-in-time safe - it honours only event_id and
      always resolves the current published marker/generation.
    command: "sed -n '581,622p;524,548p' engine/neuralweb/company_intelligence_reader.py"
    result: "no as-of/cutoff/generation parameter; resolves manifest['generation_id'] at :532"
  - claim: >
      B1 emits no decision or tradability clock, which is why the contract's REQUIRED
      decision_cut had no owner before A8.
    command: "grep -n 'decision\\|tradab' engine/us_candidate_episode.py"
    result: "only opened_session and observation_session; no decision_at, no tradable_at"
  - claim: >
      The episode-to-Earnings identity bridge exists in the issuer master but is not
      exposed by the canonical Data OS reader.
    command: "sed -n '188,196p' scripts/build_security_master.py; sed -n '760,779p' lib/dataos/identity.py"
    result: "ISSUER_MASTER_COLUMNS carries issuer_id and cik; SecurityIssuerRow carries neither cik nor any accessor for it"
  - claim: >
      B1's real committed TURN WATCH input is intact and every row satisfies B1's intake
      predicate, so the natural run has valid anchored observations to reconcile.
    command: "git show origin/main:data/us_prophet_rank/episode_inputs/turn_watch/2026-08-25.json, then replay engine.us_candidate_episode_intake.turn_watch_observations gates over its rows"
    result: "content_sha256 recomputes exactly; 1790/1790 rows ANCHORED_OK; zero structural suppressions"
  - claim: >
      The B1 acceptance probe validates a real generation end to end through B1's own
      canonical reader.
    command: "python3 -m pytest tests/test_us_candidate_episode_reconciler.py::test_natural_nightly_opens_once_and_publishes_exact_derived_targets --basetemp=/tmp/b1bt, then run the probe against the produced store"
    result: "30 checks, 0 FAIL against a real published generation"
  - claim: >
      The scheduled run in flight during this session did NOT execute B1, despite its
      job checking out ref main after the merge.
    command: "gh api repos/mastermindx-market-intelligence/macro/actions/jobs/98084842822/logs --allow-escape-sequences"
    result: "no reconcile_us_candidate_episodes step in the job's step list; GitHub pins the workflow definition to the triggering commit"
unverified:
  - claim: Identity resolution will succeed for PHM/KBH/TOL in the natural run.
    what_would_verify: >
      The natural generation's episodes actually carrying those securities, or its
      suppressions naming IDENTITY_UNRESOLVED / ISSUER_UNRESOLVED for them. The Data OS
      spine could not be simulated in this sparse checkout.
  - claim: The Earnings owner's covered issuer set is exactly the five CIKs found.
    what_would_verify: >
      Enumerating published objects under the company_intelligence/event_workspaces
      nest on R2 rather than inferring coverage from issuer_profiles.py.
  - claim: The amendment's own rules are correct.
    what_would_verify: >
      The independent hostile review commissioned against
      CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md, whose verdict must be folded in
      before this carrier merges.
unresolved:
  - >
    B1 natural acceptance is gated on a natural-time event that had not occurred when
    this record was written. The qualifying run is the first ordinary scheduled
    daily.yml firing whose HEAD contains 878930b3b2f9. On the EDT regime that is the
    cron "30 22" line; the previous night's equivalent reached us_prophet_ledgers about
    8.5 hours after firing because the single self-hosted Mac Studio serialises jobs.
  - >
    A13 clause 1: the issuer_id to cik bridge needs a bounded, owner-coordinated
    extension of the canonical Data OS issuer reader. Until that lands the D5
    episode-to-Earnings join is UNRESOLVED and must be reported as such.
  - >
    tradable_at has no owner until V4-B4 exists. A8 sets it NOT_ASSERTED with a named
    basis rather than synthesising one.
next_actions:
  - >
    Fold the independent amendment review's findings into PR #6275, then merge it once
    every binding check has CONCLUDED. The standing red ci-authority/codex/merge-queue-pilot
    is the designed inactive-base negative control (scripts/merge_on_green.py:656) and is
    excluded when ci-authority/main and the ci-authority aggregate are green.
  - >
    Wait for the first ordinary scheduled daily.yml run whose HEAD contains 878930b3b2f9.
    Do NOT dispatch, rerun, replay, cancel, or use report mode. Confirm event=schedule,
    that et_gate kept the run, and that the job log actually contains the step
    "Prophet B1 - reconcile canonical candidate episodes".
  - >
    Run the acceptance probe against the produced store. It is committed with this wave at
    research/prophet_v4/B1_NATURAL_ACCEPTANCE_PROBE.md, which carries the script inline plus
    how to run it and how to read a failure. It materialises data/us_prophet_rank/episodes
    from a git ref with git archive, so it needs no full checkout and works in a sparse tree:
    python3 b1_acceptance_probe.py --repo <worktree> --ref origin/main. It was validated at
    30 checks / 0 fail against a real generation from B1's own nightly test. Then have a fresh
    independent critic attack the same evidence packet - the probe is a floor, not acceptance.
  - >
    Ship a small records-only B1 acceptance PR marking B1 accepted at its true scope and
    explicitly releasing D5 runtime. Only after that merges may D5 runtime work begin.
  - >
    Build the first D5 Earnings vertical per the amended contract: owner-issued episode
    only, revision-chain reader with the decision-cut filter, issuer_id to cik bridge or
    IDENTITY_UNRESOLVED, all authority flags false, fusion_bindings empty, exposed
    through the existing read-only Prophet Lab router in app/prophet_lab.py, which today
    has exactly two routes and no per-entity detail path.
do_not_redo:
  - >
    Do not re-review whether PR #6275 should be superseded. It was adversarially reviewed
    against current main on 2026-08-26 and the disposition is AMEND: the epistemic core
    was checked against current code and survives. Superseding it would discard correct,
    non-obvious law.
  - >
    Do not re-run the Phase A stale-work sweep. Five targeted regex passes over the whole
    of agentos/, research/ and docs/ found zero wording instructing an A1R re-run, an
    Aug-14 replay, a K1 or K2-B redo, or a second B1. Every hit was a prohibition. Phase A
    needed no repair.
  - >
    Do not treat a scheduled run whose HEAD predates the B1 merge as a qualifying natural
    run because its jobs check out ref main. The workflow definition is pinned to the
    triggering commit, so a newly merged workflow STEP cannot appear in an already-started
    run - only library code is refreshed. Measured against run 32908543584.
  - >
    Do not read Earnings decision-time evidence through read_event_workspace or
    read_current_event_workspace, and do not "simplify" the revision-chain filter back to
    them. They resolve the current generation while still carrying a pre-cut
    lifecycle.source_available_at, so the wrong reading passes every stated acceptance
    test while shipping post-cut corrected values as decision-time belief. Equally, do not
    filter admission on source_available_at alone: admission is the conjunction with
    observed_at <= cut. An independent review caught the single-clock version of this rule in
    the first draft of A7, where it would have re-opened the very lookahead hole the
    amendment exists to close.
  - >
    Do not join B1 episodes to Earnings events on company_id equality, and do not fall
    back to a ticker-string join when the issuer bridge fails. The two company_id fields
    are different identifier namespaces.
  - >
    Do not widen the Earnings owner's issuer coverage to make a D5 demo produce more
    non-empty families. Coverage is that owner's operation; a NOT_COVERED majority is the
    truth.
danger_areas:
  - >
    agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md is edited by several concurrent
    waves. A stale branch copy can auto-merge in the branch's favour and silently delete
    ratified content including safety do_not_redo rules. Always diff a branch's copy
    against current main before merging anything that touches it.
  - >
    This worktree is SPARSE: data/, site/, mockups/, verify_shots/ are not on disk. Read
    production artifacts out of git with git show or git archive rather than opting into a
    full checkout, and never git add -A an unexpected data/ diff in a sparse tree.
  - >
    The B1 nightly step is schedule-only and hard-failing by design. A crash there reds
    us_prophet_ledgers rather than degrading quietly, which is intended - do not add
    continue-on-error to make a red go away.
  - >
    The Earnings revision walk is a SOURCE-revision reader, not a body-revision reader.
    _receipt_from_revision derives source_sha256 only from a source whose kind is
    issuer_release, and _dedupe_carry_forward_hops collapses consecutive equal values, so an
    event with no issuer_release source collapses to one revision and body-only corrections
    are invisible through the only lawful decision-time path. That is why A7 requires a typed
    correction_lineage_state and forbids rendering NOT_OBSERVABLE as "no correction".
  - >
    The Earnings correction path is UNEXERCISED in production. A live read of
    read_event_source_revisions on the AAPL event returns exactly one revision in
    lifecycle_state complete, so no published event carries a multi-generation
    correction chain today. A builder developing against live data will never meet a
    correction and can ship the non-PIT-safe reader with no symptom at all, until the
    first real correction lands and silently rewrites decision-time history. Prove the
    correction law against a constructed two-generation chain driven through the real
    reader, never against live data alone.
  - >
    The nightly runner serialises jobs on one self-hosted machine, so a natural run can
    take many hours to reach us_prophet_ledgers. Queue delay is acceptable and is not
    evidence that anything is wedged. Never cancel a production lane to unblock a session.
---

The reconciliation half of this commission is done; the acceptance half is held by a
natural-time gate that no lawful act can shorten. The two halves are deliberately
separable: the amended architecture is correct and mergeable on its own, and B1
acceptance needs only the probe plus a fresh critic once the qualifying scheduled run
produces its first generation. A session resuming here should start by confirming
whether that run has fired, using the run's HEAD ancestry and the job's actual step
list rather than checkout ancestry.
