---
workstream: WS:PROPHET-CONDITIONAL-FUSION
title: Prophet Conditional Fusion — PR-3D-R1 same-stamp revision + atomic persist + 08-17 session bootstrap
date: 2026-08-18
session: claude/prophet-fusion-pr3d-r1
model: local
ended_because: ci_handoff
prs: []
repo: mastermindx-market-intelligence/macro
mission: >
  PR-3D-R1 only. Make W3 correctly handle multiple Prophet publications under
  one economic stamp_date (first durable complete observation wins; later
  same-stamp revisions visible and refused). Then commission PR-3D
  sessions/status from the already-prospective 2026-08-17 W3 parts. Not PR-3E.
state_before: >
  PR-3D #5890 merged (47aaa603). 2026-08-17 paired/family/coverage exist on
  main (blobs 4486cd6199b465431b0e1f27b1057e87b1aaf628 /
  6885cfc4f5c180177ed307953f3b67b2021e0371 /
  dc5edb4082b536adcbb5d3fbc1b22af8a57f6d2e). sessions.jsonl absent. Natural
  us_prophet_ledgers run 32084697588 job 95749508810 raised W3ConflictError on
  F1_TECHNICAL_CONFLUENCE 3.696969697 vs 3.8484848485; keep-first held the
  frozen family bytes; persist-after-family-raise dropped session/status;
  nightly red loop. w3 wave still todo. Final #5890 did not edit daily.yml or
  dag.yml; CLI maps --nightly onto require_board_as_of.
changed:
  - path: engine/us_prophet_w3.py
    what: >
      Same-stamp revision semantics on a complete frozen observation
      (SAME_STAMP_REVISION_REFUSED, nonfatal); identity conflict on a
      brand-new/incomplete stamp still fatal; preflight+rollback so a new
      stamp cannot land paired-without-family; session receipts bind
      paired/family/coverage fingerprints; bootstrap sessions.jsonl from
      frozen W3 parts; status exposes same_stamp_revisions_refused.
  - path: tests/test_us_prophet_w3.py
    what: "R1 adversarial tests 1-15 covering identical retry, F1 3.6969→3.8484,
      no float tolerance, paired/coverage revision, incomplete fail-closed,
      atomic rollback, 65/65 bootstrap, missing-date cannot bootstrap."
  - path: agentos/discoveries/DSC-PROPHET-BOARD-ASOF-IS-ECONOMIC-SESSION-ID.md
    what: "Board as_of is an economic session id, not a publication version."
  - path: agentos/decisions/DEC-W3-FIRST-DURABLE-COMPLETE-OBSERVATION-WINS.md
    what: "First durable complete W3 observation wins; later same-stamp
      publications are refused revisions. Product republish policy unchanged."
  - path: agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md
    what: "Cite DEC/DSC; w3 stays todo; next_action is natural ledgers proof."
  - path: agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-18-PR3D-R1.md
    what: "This repair handoff. Production acceptance still unverified."
verified:
  - claim: "W3 unit tests including R1 revision/bootstrap/atomic cases are green"
    command: "\"/Users/chriswong/Documents/Cluade/Macro Dashboard/.venv/bin/python\" -m pytest tests/test_us_prophet_w3.py -q --tb=short"
    result: "56 passed"
  - claim: "off-engine lane, DAG conformance, exclusive-scope closure, and grades tests are green"
    command: "\"/Users/chriswong/Documents/Cluade/Macro Dashboard/.venv/bin/python\" -m pytest tests/test_prophet_off_engine_lane.py tests/test_dag_conformance.py tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure tests/test_us_prophet_grades.py -q --tb=line"
    result: "143 passed"
  - claim: "AgentOS store validates with 0 errors after DEC/DSC"
    command: "\"/Users/chriswong/Documents/Cluade/Macro Dashboard/.venv/bin/python\" scripts/agentos.py validate"
    result: "0 error(s); 8 pre-existing warnings on other workstreams"
unverified:
  - claim: "CI packs on the R1 PR conclude green (or spurious-only Workers X)"
    what_would_verify: "gh pr checks after packs conclude"
  - claim: "the next NATURAL us_prophet_ledgers run executes merged R1, writes sessions.jsonl, leaves the three 2026-08-17 blobs byte-identical, commissions status (paired N=1 unmatured), and refuses a same-stamp revised structural receipt without crashing"
    what_would_verify: >
      After merge, watch the next natural us_prophet_ledgers (do not dispatch
      a second daily). git rev-parse origin/main:data/us_prophet_rank/w3/paired/2026-08/2026-08-17.parquet
      (and family/coverage) still the pinned blobs; sessions.jsonl exists;
      status.json commissioned=true paired_sessions_accrued>=1 matured_h10=0.
unresolved:
  - "PRODUCTION PROOF is still required. Do not mark w3 done until the natural ledgers run lands."
  - "Do not start PR-3E, C2-C5, or Prophet V4."
  - "Do not rewrite the 2026-08-17 W3 paired/family/coverage parts."
  - "Do not read C1-vs-shadow IC/delta/HAC/p-value/winner."
next_actions:
  - "Open/merge PR-3D-R1; arm merge-on-green; stay until squash-merged."
  - "Watch the next NATURAL us_prophet_ledgers run. Do not cancel. Do not dispatch over an in-flight daily."
  - "If that run proves the PASS PATH: records-only acceptance handoff, set w3 wave done, record paired N and matured H10 N without comparative results, next_action = automatic W3 accrual."
  - "If it fails: name the first causal defect and STOP. Do not broaden."
do_not_redo:
  - "Do not change C1, floors, families, SELECTION_ERA, board definition, or the grader."
  - "Do not edit daily.yml or config/dag.yml unless a demonstrated production contract requires it. --nightly already maps to require_board_as_of in the CLI."
  - "Do not treat #5878 reconstruction as a W3 session (DEC:W3-PROSPECTIVE-SAMPLE-IGNORES-GENERIC-BACKFILL)."
  - "Do not count same-stamp publication retries as independent sessions."
  - "Do not latest-wins / average / float-tolerate W3 identity fields."
  - "Do not change general Prophet republish policy to version as_of."
danger_areas:
  - "A write into omitted sparse data/ truncates committed parquets. This repair must not git-add the 08-17 parts."
  - "session_missing / degraded_or_unpaired remain terminal; bootstrap only complete frozen observations."
  - "Comparison surface must stay unreachable below honest-N=20."
  - "Cancelling a live daily.yml is forbidden; it is invisible to every staleness instrument."
decisions:
  - DEC:W3-FIRST-DURABLE-COMPLETE-OBSERVATION-WINS
  - DEC:W3-PROSPECTIVE-SAMPLE-IGNORES-GENERIC-BACKFILL
discoveries:
  - DSC:PROPHET-BOARD-ASOF-IS-ECONOMIC-SESSION-ID
---

## What landed in this repair

Keep-first still holds the frozen 2026-08-17 observation. The repair makes a
later same-stamp Prophet publication a visible refused revision instead of a
nightly crash, persists PR-3D session/status even when the revision is
refused, and commits a brand-new stamp's three grains only after an in-memory
preflight (rollback if a later grain write fails).

sessions.jsonl for 2026-08-17 is intentionally not committed in this PR. The
next natural `us_prophet_ledgers` run bootstraps it from the frozen parts
(65 paired / 65 pending / unmatured). That is not market-data backfill.

## PASS PATH (production)

Only after the natural ledgers run proves the bullets in `unverified`:
update this workstream, set w3 done, no PR-3E.
