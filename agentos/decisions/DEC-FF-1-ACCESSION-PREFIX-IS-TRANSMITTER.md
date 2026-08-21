---
key: FF-1-ACCESSION-PREFIX-IS-TRANSMITTER
question: >
  Must a current-quarter master.idx row fail closed when accession[:10] does
  not equal the canonical subject CIK, as Sol's FF-1P2R ruling 7 three-identity
  bind specified?
answer: >
  No. Bind row CIK to path CIK, and require accession *shape*
  (10-2-6 ASCII digits). Do not require accession[:10] == subject CIK.
  An EDGAR accession number is prefixed with the transmitting filer/agent
  CIK, not the subject issuer. The live Q3 canary already contains the
  counterexample: MSFT CIK 0000789019 with 10-K 0001193125-26-323660.
rationale: >
  Implementing the three-identity equality as written would reject the live
  master index and fail every production poll. Row-vs-path CIK still binds
  the subject identity (edgar/data/<unpadded-cik>/<accession>.txt). Accession
  shape still rejects malformed tokens. Sol's synthetic mix-up example
  (Apple row/path with a Microsoft-prefixed accession sitting in Apple's
  directory) is not how agent-filed 10-Ks appear; those keep the issuer
  path CIK and carry the agent's accession prefix.
alternatives:
  - option: Keep accession[:10] == row CIK and fail closed on mismatch
    why_not: Reproduced against the in-repo canary; MSFT 10-K would raise edgar_index_cik_mismatch and kill the poll.
  - option: Repair/rewrite the accession prefix to the subject CIK
    why_not: Identity must never be repaired. The prefix is real transmitter identity.
  - option: Skip agent-filed rows silently
    why_not: That would drop the live MSFT 10-K from discovery.
evidence:
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
  - "Canary line 16: MSFT 10-K 0001193125-26-323660 against canonical CIK 0000789019."
  - "Adversarial review of 62ea29e reproduced REJECTED edgar_index_cik_mismatch | accession prefix '0001193125' does not match row CIK '0000789019'."
  - "python3 -m pytest tests/test_fundamental_forensics_broad_sec.py::test_agent_filed_accession_is_admitted_when_row_matches_path -q → passed"
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - tests/test_fundamental_forensics_broad_sec.py
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-21
review_by: 2026-08-22
---

Escalate to Sol: ruling 7 as frozen text cannot be satisfied by real SEC
master.idx data. This PR implements the production-safe remainder (ASCII
digit row CIK, row==path bind, accession shape) and records the deviation.
