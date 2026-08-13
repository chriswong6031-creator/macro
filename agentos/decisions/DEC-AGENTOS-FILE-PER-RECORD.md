---
key: AGENTOS-FILE-PER-RECORD
question: >
  What storage mechanism should hold Agent OS records, given 20-50 concurrent workers across
  multiple machines and repositories?
answer: >
  Git-tracked Markdown with YAML frontmatter, one record per file, plus generated views.
  No database, no daemon, no event bus, no service.
rationale: >
  One file per record makes concurrent writes conflict-free: 50 sessions creating 50 distinct
  files merge trivially in git, while any shared append target produces guaranteed conflicts.
  Frontmatter plus prose keeps machine truth and human truth in one artifact so they cannot
  drift. It is house idiom twice over — the memory system is one-fact-per-file with an index,
  and DO_NOT_REBUILD.md mints stable keys and compiles machine output — so it needs no new
  concepts, no new infrastructure, and no operational burden.
alternatives:
  - option: Append to a shared JSONL event log
    why_not: >
      Guaranteed merge conflicts at 20-50 concurrent writers. This is the specific failure the
      one-file-per-record rule exists to prevent.
  - option: Extend Mastermind data/governance/governance.jsonl
    why_not: >
      Verified not git-tracked (see DSC:GOVERNANCE-JSONL-NOT-TRACKED); it is single-machine
      runtime state and cannot carry cross-machine, cross-repo memory. It remains correct as
      the local authority audit trail.
  - option: SQLite
    why_not: >
      Binary, unmergeable in git, invisible in PR review. Correct for the hot single-machine
      plane, where control_plane/executive_runtime.py already uses it well for leases and
      heartbeats.
  - option: Postgres, a daemon, or a message bus
    why_not: >
      Census §6.4 forbids new schedulers, queues, and buses. Adds operational burden with no
      offsetting property at this scale.
evidence:
  - "cd Mastermind && git ls-files | grep governance.jsonl -> empty"
  - "control_plane/governance.py:70 — resolves data/governance/governance.jsonl"
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §6.4 — no new schedulers, queues, or buses"
  - "Memory system convention: one fact per file plus MEMORY.md index"
affects: [WS:AGENT-OS, "agentos/**"]
confidence: high
reversibility: costly
decided_by: opus-architecture-session
decided_at: 2026-08-12
---

## Grounds

Reversibility is `costly` rather than `easy` because once records exist and are cited by key
across PRs and masterplans, migrating the store means rewriting citations. The mitigation is
that the format is plain text in git: a migration is mechanical, not lossy.
