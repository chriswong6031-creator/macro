---
workstream: "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
session: claude/cs-intel-v2-masterplan
model: local
ended_because: complete
mission: >
  Recover the Capital Structure Intelligence product thesis, audit current
  main and the live estate, refresh competitor and primary-source regulatory
  research, and freeze V2 architecture plus ordered waves. Docs and Agent OS
  only. Do not start Wave 1. Do not drain the historical backlog.
state_before: >
  PR 5792 had closed the ingestion freeze. Sol had audited main at
  a49e448d024f641d48ebc3fa9c54bdcc4ddbd76a. No WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2
  record existed. Production retained filings but latest filing date was still
  2026-07-31. No V2 masterplan existed.
changed:
  - path: research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md
    what: Canonical V2 masterplan, capability ledger, identity and publication rulings, live-tail split, six-question ontology, real-data compositions, Wave 1 handoff.
  - path: config/mastermind_programs.yml
    what: Point capital-structure-intelligence canonical_docs at the V2 masterplan, contract, and 2026-08-01 teardown instead of STOCK_FUNDAMENTALS_PLAN.md.
  - path: agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md
    what: New workstream awaiting Sol/Chairman review; W0 in progress; W1-W7 todo.
  - path: agentos/decisions/DEC-CS-V2-IDENTITY-DUAL-READ.md
    what: Forward-only dual-read identity; no historical ID rewrite; no merge=union.
  - path: agentos/decisions/DEC-CS-V2-GIT-REMAINS-GENERATION-SELECTOR.md
    what: Git stays compiled-generation selector; R2 stays evidence store; no new publication plane.
  - path: agentos/decisions/DEC-CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG.md
    what: LIVE_TAIL / RECOVERY / HISTORICAL_BACKFILL; compiler age is not horizon.
  - path: agentos/decisions/DEC-CS-V2-SIX-QUESTION-ONTOLOGY.md
    what: Authorization vs eligibility vs remaining capacity vs economic supply vs funding need vs observed issuance.
  - path: agentos/discoveries/DSC-CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS.md
    what: manifest_id hashes retrieval clocks; DNR sibling; sequential remint masked.
  - path: agentos/discoveries/DSC-CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE.md
    what: source_manifest.jsonl unspecified merge plus CS -X theirs lost-update.
  - path: agentos/discoveries/DSC-CS-THROUGHPUT-HEALTHY-HORIZON-STALE.md
    what: Dated 2026-08-18 proof that health ok does not mean current filings.
  - path: agentos/discoveries/DSC-CS-INSTRUMENT-AND-LIFECYCLE-COMPILERS-NOT-NIGHTLY.md
    what: Candidate-term and registration-lifecycle compilers exist and are not in daily.yml.
  - path: agentos/discoveries/DSC-CS-EVENT-EDGES-NEAR-ZERO.md
    what: Freeze generation has 600 event versions and 1 edge.
decisions:
  - DEC:CS-V2-IDENTITY-DUAL-READ
  - DEC:CS-V2-GIT-REMAINS-GENERATION-SELECTOR
  - DEC:CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG
  - DEC:CS-V2-SIX-QUESTION-ONTOLOGY
discoveries:
  - DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS
  - DSC:CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE
  - DSC:CS-THROUGHPUT-HEALTHY-HORIZON-STALE
  - DSC:CS-INSTRUMENT-AND-LIFECYCLE-COMPILERS-NOT-NIGHTLY
  - DSC:CS-EVENT-EDGES-NEAR-ZERO
verified:
  - claim: Freeze SHA origin/main is ec62e4981c10d1ce7d6379cb9475747d49f790f1 after fetch and fast-forward.
    command: git fetch origin && git rev-parse origin/main
    result: ec62e4981c10d1ce7d6379cb9475747d49f790f1
  - claim: Capital Structure producer paths are unchanged from Sol SHA a49e448d to freeze SHA.
    command: git diff --stat a49e448d024f641d48ebc3fa9c54bdcc4ddbd76a..ec62e4981c10d1ce7d6379cb9475747d49f790f1 -- collectors/sec_capital_structure.py engine/capital_structure scripts/ app/capital_structure.py data/capital_structure .github/workflows/daily.yml .github/runner-policy.yml engine/research_vault/r2_store.py config/house_law_checks.yml config/sector_intelligence_ownership.yml
    result: empty diff
  - claim: Freeze generation latest filing date is 2026-07-31 with 200 selected, 200 retained, 19018 pending, health verdict ok.
    command: python3 -c "import json; from pathlib import Path; h=json.loads(Path('data/capital_structure/health.json').read_text()); print(h['latest_source_filing_date'], h['counters']['selected'], h['counters']['verified_retained_sources'], h['backlog']['pending'], h['verdict'])"
    result: 2026-07-31 200 200 19018 ok
  - claim: Projection has 426 issuers, freshness fresh on compiler age, eight unavailable capabilities, and 1 event edge in telemetry.
    command: python3 -c "import json; from pathlib import Path; p=json.loads(Path('data/capital_structure/projection.json').read_text()); t=json.loads(Path('data/capital_structure/telemetry.json').read_text()); print(len(p['records']), p['coverage']['freshness'], p['unavailable'], t['counts']['event_edges'], t['counts']['event_versions'])"
    result: 426 fresh eight unavailable caps; event_edges 1; event_versions 600
  - claim: manifest_id_for hashes the full body minus manifest_id.
    command: sed -n '136,141p' engine/capital_structure/source_identity.py
    result: body = dict(record); body.pop("manifest_id"); sha256(canonical_manifest_bytes(body))
  - claim: source_manifest.jsonl is absent from .gitattributes.
    command: rg capital_structure .gitattributes
    result: no matches
  - claim: instrument and registration-lifecycle compilers are not in daily.yml.
    command: rg compile_capital_structure_instrument\|compile_capital_structure_registration .github/workflows/daily.yml
    result: no matches
unverified:
  - claim: Required CI packs and fences conclude green on this docs PR head.
    what_would_verify: gh pr checks after push; wait for concluded packs; do not merge
  - claim: DilutionTracker.com primary site still HTTP 500 after this session.
    what_would_verify: curl -I https://dilutiontracker.com on a later date; KB was live 2026-08-18
unresolved:
  - Sol/Chairman architecture acceptance of the V2 freeze
  - Operator choice among the three remaining global collect-concurrency options in DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE
  - Whether Git remains generation selector after operator review (this freeze says yes until that ruling)
  - Nasdaq Rule 5635 post-2020 amendments vs the 2018/2020 SEC SRO order text used in the masterplan
next_actions:
  - Open this research PR, drive CI green, leave merge-on-green off, do not squash-merge
  - Hand the PR to Sol/Chairman for architecture review
  - Do not start Wave 1 identity implementation
  - Do not raise MAX_FILINGS or drain historical backlog as a substitute for live-tail
do_not_redo:
  - Reopen PR 5792 ingestion freeze without new evidence
  - et_gate mutex for concurrent collect
  - Rewrite historical manifest_id strings
  - merge=union on source_manifest.jsonl
  - BioCatalyst-specific capital ledger
  - Opaque Capital Structure score
  - Encode Release 33-11418 as current law
  - Second SEC collector or share-count truth plane
danger_areas:
  - Sparse worktrees truncate data/capital_structure writes; this worktree is full checkout
  - Live row counts in health.json will move; treat them as dated observations
  - Dual-read identity if implemented carelessly will rewrite PIT receipts
  - CS push -X theirs can clobber the JSONL; do not "fix" that with merge=union
---

W0 architecture freeze is written and awaiting Sol/Chairman. Wave 1 is specified
in masterplan section 19 and is not started. prophet_authority remains false.
