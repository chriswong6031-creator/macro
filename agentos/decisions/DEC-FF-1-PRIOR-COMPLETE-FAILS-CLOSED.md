---
key: FF-1-PRIOR-COMPLETE-FAILS-CLOSED
question: >
  If latest-complete exists, is sha-verified complete, and its receipt lacks a
  well-formed index-discovery block, may the next incremental poll bootstrap
  the current quarter as if no prior complete existed?
answer: >
  No. Bootstrap only when latest-complete is absent. A sha-verified complete
  receipt missing or malformed index state is corrupt prior and must raise
  BroadSecError (issuer_manifest_invalid). Do not re-baseline, do not fetch
  nothing and republish latest-complete.
rationale: >
  Re-baselining from a corrupt complete head marks the entire current-quarter
  relevant set unchanged, fetches zero issuers, and can publish a fresh
  complete pointer that silently discards every filing since the corruption.
  Sol's SPEC 2 already said never bootstrap from corrupt latest-complete.
alternatives:
  - option: Treat missing index as bootstrap True
    why_not: Fail-open. That is how a verified-complete receipt would wipe the quarter.
  - option: Ignore the prior complete and list_prefix snapshots
    why_not: Forbidden. latest-complete is the sole processed authority.
evidence:
  - "engine/fundamental_forensics/broad_sec_store.py _load_prior_context raises when index is not a dict or year/quarter/snapshot_sha256 are incomplete."
  - "python3 -m pytest tests/test_fundamental_forensics_broad_sec.py::test_prior_complete_without_index_state_fails_closed -q → passed; latest-complete bytes unchanged"
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - tests/test_fundamental_forensics_broad_sec.py
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-21
---

Corrupt prior-complete is a stop, not a second genesis.
