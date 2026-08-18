---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/defense-d1-1-agency-semantic
model: local
ended_because: ci_handoff
prs: [5856]
decisions:
  - DEC:D11F-PIT-SAFE-AGENCY-FALLBACK
discoveries:
  - DSC:GOVREV-AGENCY-STRINGIFY-IS-COLLECTOR-THEN-ACTION-OMIT

mission: >
  D1.1F PIT-safe agency provenance: an action may display an awarding agency
  only from its own source-asserted fields or from a same-award snapshot
  already known at that action's known_at. Finish existing PR #5856. No D2.

state_before: >
  PR #5856 had canonicalize_agency and latest-snapshot inherit. Its tested
  base was 33f7bdde, before #5857 repaired the ONTO US-board leak. Operator
  accepted the canonicalize work and required PIT-qualified fallback plus
  current-main ancestry before merge.

changed:
  - path: engine/government_revenue/award_events.py
    what: >
      Replaced latest-snapshot agency index with PIT candidates selected by
      known_at DESC, version DESC, source identity ASC. Direct action agency
      requires source_field_presence. Fallback writes
      award_snapshot_agency_fallback.v1 into evidence.derivations.
  - path: tests/test_government_revenue_award_events.py
    what: >
      Adversarial tests A-F plus P00032 provenance, NASA, and true-missing
      action agency. Replay invariance compares the full T1 action payload.
  - path: agentos/decisions/DEC-D11F-PIT-SAFE-AGENCY-FALLBACK.md
    what: PIT fallback supersedes latest-at-cutoff inherit.
  - path: agentos/decisions/DEC-D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT.md
    what: Marked superseded_by DEC:D11F-PIT-SAFE-AGENCY-FALLBACK.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: D1.1 next_action is finish #5856 D1.1F; D2 still unauthorized.

verified:
  - claim: Focused Government Revenue suites pass on current-main ancestry after PIT change.
    command: >
      python -m pytest tests/test_government_revenue_award_events.py
      tests/test_government_revenue_workspace.py
      tests/test_government_revenue_ui.py
      tests/test_build_government_revenue.py
      tests/test_government_revenue_api_auth.py -q
    result: 176 passed
  - claim: Future snapshot cannot fill an earlier action; replay keeps event_id and payload.
    command: >
      python -m pytest tests/test_government_revenue_award_events.py -k d11f -q
    result: 6 passed including replay identity/payload equality
  - claim: Branch contains origin/main 448c33d86f8e and #5857 95d39c24ab17.
    command: git merge-base --is-ancestor origin/main HEAD && git merge-base --is-ancestor 95d39c24ab17 HEAD
    result: both ancestors present; US board gate diff vs origin/main is empty

unverified:
  - claim: Entitled production Change Tape shows at least two real human agency names and P00032 as Department of Defense / DISA.
    what_would_verify: >
      site_full session on https://www.mastermind-x.com/government_revenue.html
      after merge plus government-revenue-live rebuild of workspace.json
  - claim: Candidate Radar remains 22 and Budget/Opportunities remain typed failures.
    what_would_verify: Same entitled session; bearer candidates total=22; budget 503; SAM SOURCE_UNAVAILABLE

unresolved:
  - Full repository CI on the rebased #5856 head has not concluded yet.
  - Entitled production proof waits on merge plus government-revenue-live rebuild.

next_actions:
  - Push rebased #5856, wait for required CI on current-main ancestry, squash-merge.
  - Wait for government-revenue-live; prove entitled desk; record bundle/graph ids; stop.
  - Do not start D2.

do_not_redo:
  - Do not parse Python in the browser.
  - Do not rewrite collector hashes.
  - Do not merge funding_agency into awarding agency.
  - Do not inherit a snapshot with known_at after the action known_at.
  - Do not start D2 or merge #5424.
  - Do not weaken the US board gate or undo #5857.

danger_areas:
  - Event IDs omit agency; only PIT filtering keeps payload immutable across rebuilds.
  - source_field_presence as a dict of True fields; a carried awarding_agency cell is not evidence.
  - Live page is government_revenue.html (underscore).
---

D1.1F keeps projector canonicalize and forbids future-snapshot inherit.
D2 remains unauthorized.
