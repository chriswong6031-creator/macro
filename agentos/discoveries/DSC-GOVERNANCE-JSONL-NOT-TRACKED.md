---
key: GOVERNANCE-JSONL-NOT-TRACKED
claim: >
  Mastermind's governance.jsonl is local runtime state, not git-tracked, so it cannot carry
  cross-machine or cross-repo organizational memory.
falsifier: >
  cd /Users/chriswong/Documents/Cluade/Mastermind && git ls-files | grep governance.jsonl
  — a non-empty result disproves this.
so_what: >
  Any design proposing governance.jsonl as the home for durable organizational memory is
  wrong and should be redirected to a git-tracked store. It remains correct and unchanged as
  the single-machine authority audit trail.
kind: architecture
verified_at: 2026-08-12
verified_by: "git ls-files (empty result for governance.jsonl); control_plane/governance.py:70 resolves data/governance/governance.jsonl"
scope: [mastermind, "WS:AGENT-OS"]
confidence: verified
---

## Detail

`control_plane/governance.py` writes one JSON object per line to
`data/governance/governance.jsonl`. `git ls-files` in the Mastermind checkout returns no such
path, and sibling `data/` JSONL paths are gitignored. The census (§5.4) proposes adding ~3
event types to this ledger, which remains correct for its purpose — a local authority audit
trail — and is simply not a candidate home for cross-repo org memory.
