---
workstream: WS:FUNDAMENTAL-FORENSICS
session: cursor/ff-1p2r-takeover
model: fable
ended_because: blocked
prs: [5898]
decisions:
  - DEC:FF-1-ACCESSION-PREFIX-IS-TRANSMITTER
  - DEC:FF-1-PRIOR-COMPLETE-FAILS-CLOSED
  - DEC:FF-1-RECOVERY-NOT-COMMISSIONED
discoveries:
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
mission: >
  Apply the adversarial review of the FF-1P2R kernel on PR #5898, keep
  current-quarter discovery, do not merge, do not dispatch production.
state_before: >
  Kernel commit 62ea29e implemented Sol's 12 rulings. Adversarial review
  FAIL: accession[:10]==row CIK rejects the live MSFT canary
  0001193125-26-323660 vs CIK 0000789019; _load_prior_context bootstrapped
  from a sha-verified complete receipt with a missing index block.
changed:
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: Drop accession[:10]==subject CIK equality; keep row==path bind and accession shape. Fail closed on corrupt prior-complete missing index. Tighten latest-complete head schema/status/run_key bind. Recount CF-deferred after byte-budget stop. Do not rewrite latest-observation to a failed head after CAS miss.
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: Admit the live MSFT agent-filed accession. Prove corrupt prior-complete does not re-bootstrap. Drive latest-complete CAS via written=False rather than a pre-write raise.
  - path: tests/test_fundamental_forensics_edgar_index.py
    what: Quiet Q4 poll after rollover keeps the SEC source clock.
  - path: tests/fixtures/r2_delivery_macro_evidence_files.v1.tsv
    what: Repin broad_sec_store.py (2212 / fe641eeb) plus main-inherited receipt drift (site_access, synapse, research_vault, build_options_flow) so the PREFIX move can pass the census.
  - path: tests/fixtures/r2_delivery_macro_anchor_lines.v1.tsv
    what: Move PREFIX fingerprint to line 56; retarget 10 unique fingerprints that shifted after the main merge.
  - path: config/r2_delivery_plane_classification.v1.json
    what: Move fundamental_forensics_broad_sec_source evidence to line 56 and retarget the same 10 inherited anchors.
  - path: agentos/decisions/DEC-FF-1-ACCESSION-PREFIX-IS-TRANSMITTER.md
    what: Record that Sol ruling 7's three-identity equality is not implementable on live master.idx.
  - path: agentos/decisions/DEC-FF-1-PRIOR-COMPLETE-FAILS-CLOSED.md
    what: Corrupt latest-complete is a stop, not a second genesis.
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: Status stays blocked. FF-1P2R BUILT_NOT_PROVEN. Escalate accession-prefix deviation to Sol.
verified:
  - claim: "Targeted FF-1 kernel suites are green after the review repair — 59 passed."
    command: "python3 -m pytest tests/test_fundamental_forensics_edgar_index.py tests/test_fundamental_forensics_broad_sec.py -q"
    result: "59 passed"
  - claim: "FF-1 kernel plus lane, collector, and R2 census are green — 103 passed."
    command: "python3 -m pytest tests/test_fundamental_forensics_edgar_index.py tests/test_fundamental_forensics_broad_sec.py tests/test_filing_forensics_broad_sec_lane.py tests/test_edgar_forensics_collector.py tests/test_r2_delivery_plane_classification.py -q"
    result: "103 passed"
  - claim: "AgentOS validate is green on the new DEC/handoff/WS records."
    command: "python3 scripts/agentos.py validate"
    result: "0 error(s), 13 unrelated warning(s)"
  - claim: "Trigger closure GAP 0, DAG OK, skip-only 0, workflow YAML OK."
    command: "python3 scripts/check_ci_trigger_closure.py; python3 scripts/check_dag_conformance.py; python3 scripts/check_skip_only_suites.py; python3 scripts/check_workflow_yaml.py .github/workflows"
    result: "TRIGGER GAP 0; DAG conformance OK (2 pre-existing suspect drifts); SKIP-ONLY 0; workflow YAML OK 93 files"
  - claim: "Unrun-suite audit has 0 strictly dark suites."
    command: "python3 scripts/audit_unrun_tests.py"
    result: "STRICTLY DARK (also untriggerable) : 0"
unverified:
  - claim: "GitHub required packs/fences on the post-repair head will conclude green."
    what_would_verify: "After push, wait for ci.yml packs plus fences.yml on the exact new SHA; do not merge."
  - claim: "A production incremental on Research R2 will finish a 2837-issuer index baseline inside 90 minutes with one master.zip GET."
    what_would_verify: "Only after Sol merges #5898 and authorizes one explicit incremental dispatch."
unresolved:
  - "Sol must ratify DEC:FF-1-ACCESSION-PREFIX-IS-TRANSMITTER. Ruling 7 as written cannot parse live EDGAR."
  - "FF-1 is not PROVEN_LIVE and is not done."
  - "FF-1R July recovery is NOT_BUILT. Live Q3 index candidates were 2560 rows / 2541 unique CIKs with filed_on >= 2026-07-12."
  - "Previous-quarter weekly reconciliation is SPEC_ONLY / NOT_BUILT."
next_actions:
  - "Sol reviews PR #5898 unmerged, including the accession-prefix deviation."
  - "Do not merge, do not dispatch production incremental, do not dispatch July recovery."
  - "Do not start FF-1R or FF-2."
do_not_redo:
  - "Do not restore accession[:10]==subject CIK. That fails the live MSFT 10-K canary."
  - "Do not bootstrap from a sha-verified latest-complete missing index state."
  - "Do not ship a second mutable processed pointer at indexes/quarters/<q>/latest.json."
  - "Do not redesign accepted current-quarter EDGAR master-index discovery."
  - "Do not ship recovery that fetches Submissions for every pending CIK before Company Facts."
  - "Do not download submissions.zip or companyfacts.zip."
danger_areas:
  - "Push target is origin/claude/ff-1p2-bulk-census (PR #5898). Do not open a second PR. Local branch is cursor/ff-1p2r-takeover."
  - "A stray origin/cursor/ff-1p2r-takeover may exist from an earlier builder push; it is not the PR branch."
  - "Sparse worktrees omit data/; never write into omitted data/ or site/."
  - "main has no branch protection; do not arm GitHub auto-merge. Do not squash-merge this PR."
---

Kernel review follow-up is implemented. Latest-complete remains the sole
processed authority. Recovery remains fail-closed. Return the PR to Sol
unmerged.
