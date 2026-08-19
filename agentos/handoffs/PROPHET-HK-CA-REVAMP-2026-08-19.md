---
workstream: WS:PROPHET-HK-CA-REVAMP
session: fable-handoff-hk-canada-prophet-c7c63d (branches claude/prophet-hk-ca-revamp-workstream, claude/ca-truth-canonical-board, claude/prophet-hk-ca-revamp-ca-truth-handoff)
model: fable
ended_because: complete
mission: >
  Wave 0 (collision/consumer preflight) + Wave 1 (CA-TRUTH: one canonical
  Canada Prophet board per session) of the HK+Canada Prophet revamp, per
  research/PROPHET_HK_CANADA_REVAMP_EXECUTION_PACKET_2026_08_18.md.
state_before: >
  origin/main at a7cfd4bef589 carried the frozen defect: build_canada_library
  main() applied a _combine_key composite re-sort + entry_open_first AFTER
  compute_canada_standouts stamped Branch-B board_pos/rank_basis, so the
  canada_standouts.json artifact's row order contradicted its own stamps; the
  page rendered a separately computed object (build_canada.py:1444 recompute,
  overlay-enriched, Branch-B order); the CA board ledger stamped no
  board_definition (all 382 rows legacy-pooled). No workstream existed.
changed:
  - path: agentos/workstreams/WS-PROPHET-HK-CA-REVAMP.md
    what: minted (PR #5923, merged 3ccf8e6d42f6); updated with CA-TRUTH state (this PR)
  - path: research/PROPHET_HK_CANADA_REVAMP_EXECUTION_PACKET_2026_08_18.md
    what: committed the hardened execution packet as the integration artifact (PR #5923)
  - path: scripts/build_canada_library.py
    what: >
      PR #5926 (merged e495570eb5d8): CA_BOARD_DEFINITION="ca_prophet_branch_b_v1"
      + CA_BOARD_AUTHORITY="screen" constants; _build_canonical_board() builds the
      ONE canonical board (compute_canada_standouts -> order-neutral enrichment ->
      watch -> authority stamps: board_definition/authority/selection_status/
      official_pick_authority=false/legacy_buy_key_semantics); composite re-sort
      and entry_open_first re-sort DELETED; _write_canada_standouts() extracted;
      main(alpha, overlay) returns the canonical board; overlay=None resolves via
      _last_rendered_overlay() from data/canada_regime/latest.json; canonical
      rank_setups pinned n_lag=6 (page laggard strip stays 6 names).
  - path: scripts/build_canada.py
    what: >
      passes overlay into main(); page recompute DELETED (vm["setups"] IS the
      returned canonical object); _canada_board_ledger stamps
      board_definition=CA_BOARD_DEFINITION on every appended row (buy + watch).
  - path: scripts/export_signal_contracts.py
    what: canada_standouts entry 1.2.0 -> 1.3.0; six new optional_fields; honest note
  - path: site/factordata/contracts/artifact_manifest.json
    what: regenerated (canada entry only; golden_signals hunk deliberately reverted in sparse tree)
  - path: tests/test_canada_canonical_board.py
    what: >
      new suite: SSOT (executed write==return, not grep), artifact/page/ledger
      parity, no-second-sort behavioral fixture, authority stamps, ledger
      definition stamps, keep-first legacy protection via real append_board,
      laggards<=6 pin, persisted-overlay fallback, page-rederive token absence.
  - path: .github/ci/legacy-jobs.yml
    what: wired the new suite into the render-guard job (workflow-yaml gate requirement)
verified:
  - claim: all six mutation kills fail a test (incl. both realistic page-re-sort forms)
    command: hand-applied mutations a-f, pytest; see PR #5926 body + comments
    result: each mutation fails >=1 named test; residual (novel raw sorted()) documented
  - claim: targeted suite green
    command: python3 -m pytest tests/test_canada_build.py tests/test_contract_drift.py tests/test_board_ledger.py tests/test_canada_canonical_board.py -q
    result: 111 passed
  - claim: PR adds zero CI reds of its own
    command: name-level diff of CI_PACK_FAILED_JOBS between PR run 32219820200/32235291661 and main's own proofs
    result: every PR red matched a main-baseline red by job name; final rebased run 32248024285 fully green
  - claim: merge bytes landed on origin/main
    command: git diff ae6fd32b origin/main -- <owned files>; git show origin/main:.github/ci/legacy-jobs.yml | grep test_canada_canonical_board
    result: 4 core files byte-identical; wiring hunk at legacy-jobs.yml:1768/1776; manifest 1.3.0 with six fields
  - claim: merge live on production
    command: curl -sfL https://mastermind-x.com/api/health (checkout field) + git merge-base --is-ancestor e495570e <checkout>
    result: checkout 1a073430be1 contains e495570e
  - claim: bot:canada_book is a stale-manifest declaration
    command: census across macro/Mastermind/charting-app (grep + git log -S over full history)
    result: zero live consumers; only production reader of canada_standouts.json is check_nightly_liveness.py (as_of only)
unverified:
  - claim: first owed-session settlement (artifact/page/ledger cohort parity + definition stamps on the production reader)
    what_would_verify: >
      After the first nightly rendering Canada on/after e495570e (TSX session
      2026-08-19, nightly ~02-08Z 2026-08-20): fetch the served
      factordata/canada_standouts.json — expect board_definition=
      ca_prophet_branch_b_v1, official_pick_authority=false, rows ordered by
      board_pos exactly; served canada.html stocks board order == artifact buy
      order; data/board_ledger/ca_board.parquet rows for that session carry the
      definition; the 382 legacy rows unchanged.
  - claim: era-fence cost lands as declared (CA scorecard stays accruing, legacy rows out of rank_ic)
    what_would_verify: board_ledger.scorecard("CA") after the first stamped session grades
unresolved:
  - merge-on-green full sweeps were storm-cancelled for ~4h on 2026-08-19 (event
    passes share the schedule's concurrency group); the source-main semantic
    circuit breaker held 23-27 armed PRs; drained ~16:04Z. Fleet CI-plane lanes
    (#5938/#5954/#5964) own the structural fix — not this workstream.
next_actions:
  - Execute the settlement receipt above; record it in the workstream (wave ca-truth -> done).
  - >
    Open LEDGER-ERA (packet §7) — definition-scope current-definition selection
    metrics in engine/board_ledger.scorecard (hit_rate/n/n_buy/by_group), keep
    pooled legacy queryable as historical_context, HK behavior unchanged,
    keep-FIRST untouched. Required tests + mutation kills listed in packet §7.3.
  - Only after LEDGER-ERA — shadow substrate (packet §9), then HK discovery / CA intel per the wave graph.
do_not_redo:
  - Do not re-census bot:canada_book (stale-manifest verdict above, evidence in PR #5926 body).
  - Do not backfill board_definition onto the 382 legacy CA ledger rows or delete them (packet STOPs; era-fence cost is declared and accepted).
  - Do not re-open the overlay=None design — _last_rendered_overlay() is the ruling (page-rendered overlay is the consistency source for standalone lanes).
  - Do not migrate board-ledger identity to (date,ticker,board_definition) (packet §8).
danger_areas:
  - >
    _branch_b_order stamps board_pos at ordering time; ANY later sort of any
    projection recreates the defect. Guards — behavioral parity tests + token
    absence test on build_canada.py; a novel raw sorted() would evade — the
    owed-session digest receipt (§17) is the production backstop.
  - Editing .github/ci/legacy-jobs.yml globally invalidates path scoping (full
    194-job manifest) — expect inherited live-data reds if run overlaps a nightly.
  - The rank_setups objects alias row dicts with the canada_setups.json path;
    canada_setups.json is written BEFORE _build_canonical_board on purpose.
prs: [5923, 5926]
---

# Session narrative (cold-stranger summary)

Wave 0: pinned main, confirmed the frozen anchors byte-identical, cleared
collisions (no owning workstream/PR/worktree; only DNR near-miss is US-scoped
KILL-PROPHET-POP-MERGE), resolved `bot:canada_book` = stale manifest.

Wave 1 (CA-TRUTH): built via a Sonnet builder against a frozen spec, then an
Opus adversarial review (7 lanes). Review outcomes: F1 era-fence activation cost
= accepted + declared (PR body section); F2 standalone-lane overlay divergence =
fixed via `_last_rendered_overlay()`; F3 laggards 6→12 page regression = fixed
(`n_lag=6` + pin test); F4 grep-theater = replaced with an executed
write==return test. CI: one genuine red (workflow-yaml — new suite unwired)
fixed by wiring; every other red name-matched main's own baseline during a
fleet-wide live-data rotation. Merged by the merge-on-green sweeper on a fully
green rebased head over a green main; bytes and liveness verified.
