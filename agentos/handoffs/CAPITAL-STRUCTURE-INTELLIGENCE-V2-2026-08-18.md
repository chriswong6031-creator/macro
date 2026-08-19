---
workstream: "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
session: cursor-grok-4.6/cs-intel-v2-masterplan
model: local
ended_because: complete
mission: >
  Sol AMEND of PR #5901: rebase onto current origin/main, replace W1
  push-time file merge with the existing whole-generation append-only fence,
  harden evidence identity to occurrence+bytes, repair Grok vs Fable
  provenance, return the same W0 PR green, and stop. No W1 production code.
state_before: >
  PR #5901 was frozen at ec62e498 with identity dual-read hashing a declared
  subset, keep-first wording, and CS-owned content-aware merge of
  source_manifest.jsonl. Sol reviewed against 71fbb0c, verdict AMEND. Origin
  main has since advanced to ad1aa0a4. Agent OS records attributed the freeze
  to coo-fable. Handoff model was already local (schema has no grok).
changed:
  - path: research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md
    what: Sol AMEND — occurrence+bytes evidence_id, whole-generation fence, current-main re-audit, W1 handoff rewritten.
  - path: agentos/decisions/DEC-CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES.md
    what: New identity ruling; supersedes DEC:CS-V2-IDENTITY-DUAL-READ.
  - path: agentos/decisions/DEC-CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE.md
    what: New publication ruling; supersedes DEC:CS-V2-GIT-REMAINS-GENERATION-SELECTOR while restating Git selector.
  - path: agentos/decisions/DEC-CS-V2-IDENTITY-DUAL-READ.md
    what: Marked superseded; proposer provenance corrected to cursor-grok-4.6.
  - path: agentos/decisions/DEC-CS-V2-GIT-REMAINS-GENERATION-SELECTOR.md
    what: Marked superseded; Git-selector answer restated by successor.
  - path: agentos/decisions/DEC-CS-V2-SIX-QUESTION-ONTOLOGY.md
    what: Provenance repaired; Sol-accepted, not reopened.
  - path: agentos/decisions/DEC-CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG.md
    what: Provenance repaired; Sol-accepted, not reopened.
  - path: agentos/discoveries/DSC-CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE.md
    what: so_what retargeted from file merge to whole-generation fence.
  - path: agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md
    what: W1 retitled; needs_ceo retargeted to AMEND acceptance; owner remains coo-fable.
  - path: agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-18.md
    what: Continuation of the same-day W0 handoff after Sol AMEND.
decisions:
  - DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES
  - DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE
  - DEC:CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG
  - DEC:CS-V2-SIX-QUESTION-ONTOLOGY
discoveries:
  - DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS
  - DSC:CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE
  - DSC:CS-THROUGHPUT-HEALTHY-HORIZON-STALE
  - DSC:CS-INSTRUMENT-AND-LIFECYCLE-COMPILERS-NOT-NIGHTLY
  - DSC:CS-EVENT-EDGES-NEAR-ZERO
verified:
  - claim: origin/main after fetch is ad1aa0a4ab3db659c3ac76834b2c07f5ff7b6ddc.
    command: git fetch origin && git rev-parse origin/main
    result: ad1aa0a4ab3db659c3ac76834b2c07f5ff7b6ddc
  - claim: 71fbb0c is an ancestor of origin/main; the only first-parent since 71fbb0c is a press-wire tick.
    command: git log --oneline 71fbb0c68b63322d97c30aac0776ab7c83205642..origin/main
    result: ad1aa0a4ab3d press-wire tick; data/marketing/press_wire only
  - claim: PR branch rebased cleanly onto origin/main (3 commits, no conflicts).
    command: git -C .claude/worktrees/cs-intel-v2-masterplan rebase origin/main
    result: Successfully rebased; HEAD 2a9657a then amended in this session
  - claim: source_manifest.jsonl is not in config/append_only_artifacts.json; only government-revenue is enrolled.
    command: git show origin/main:config/append_only_artifacts.json
    result: families[0].key = government-revenue; no capital-structure family
  - claim: CS job push has no append-only fence; collect unstages CS paths then fences only collect artifacts.
    command: rg -n "push_append_only_fence|data/capital_structure" .github/workflows/daily.yml
    result: unstage at 649; fence at 761/787 in collect; CS add 1303; CS -X theirs 1332
  - claim: manifest_id_for hashes the full body minus manifest_id.
    command: sed -n '136,141p' engine/capital_structure/source_identity.py
    result: body.pop("manifest_id"); sha256(canonical_manifest_bytes(body))
  - claim: Handoff schema model enum has no grok; local is the truthful existing value for a Cursor Grok session.
    command: git show origin/main:agentos/schema/handoff.schema.yml
    result: "enum: [fable, opus, sonnet, haiku, codex, local]"
unverified:
  - claim: Required CI packs and fences conclude green on the amended head.
    what_would_verify: gh pr checks after push; wait for concluded packs; do not merge
  - claim: DilutionTracker.com primary site still HTTP 500 after this session.
    what_would_verify: curl -I https://dilutiontracker.com on a later date
unresolved:
  - Sol/Chairman acceptance of this amended W0 freeze (needs_ceo on the workstream)
  - Operator choice among the three remaining global collect-concurrency options in DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE
  - Nasdaq Rule 5635 post-2020 amendments vs the 2018/2020 SEC SRO order text used in the masterplan
next_actions:
  - Push the rebased amended branch to PR #5901, drive CI green, leave merge-on-green off, do not squash-merge
  - Hand the PR back to Sol for architecture acceptance
  - Do not start Wave 1 production code
  - Do not raise MAX_FILINGS or drain historical backlog as a substitute for live-tail
do_not_redo:
  - Reopen PR 5792 ingestion freeze without new evidence
  - et_gate mutex for concurrent collect
  - Rewrite historical manifest_id strings
  - merge=union on source_manifest.jsonl
  - Push-time content-aware merge of source_manifest.jsonl
  - Attribute this W0 research to Fable
  - BioCatalyst-specific capital ledger
  - Opaque Capital Structure score
  - Encode Release 33-11418 as current law
  - Second SEC collector or share-count truth plane
  - Reopen six-question ontology, live-tail split, Git-selector boundary, BioCatalyst PIT seam, prophet_authority=false
danger_areas:
  - Sparse worktrees truncate data/capital_structure writes
  - Live row counts in health.json will move; treat them as dated observations
  - Subset-hashing v2 manifest_id against a row that still carries clocks trips validate_manifest_ledger
  - Calling the append-only fence from collect cannot protect CS; collect unstages those paths
  - Mixing a merged manifest with an unmerged compiled generation is a silent product lie
---

W0 architecture freeze amended after Sol review. Executor of this research
and AMEND is Cursor Grok 4.6 (`model: local` because the Agent OS handoff
enum has no grok). COO Fable remains the program-owner seat, not the
proposer of these rulings. Wave 1 is specified in masterplan section 19 and
is not started. prophet_authority remains false. Do not merge.
