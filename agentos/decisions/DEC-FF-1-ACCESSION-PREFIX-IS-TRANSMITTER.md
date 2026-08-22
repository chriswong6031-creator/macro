---
key: FF-1-ACCESSION-PREFIX-IS-TRANSMITTER
question: >
  Must a current-quarter master.idx row fail closed when accession[:10] does
  not equal the canonical subject CIK, as Sol's FF-1P2R ruling 7 three-identity
  bind specified?
answer: >
  No. The accession first 10 digits are the login/submitting CIK; the
  submitting CIK may belong to a third-party filing agent. Bind canonical
  subject identity by master.idx row CIK == edgar/data/<path-CIK>. Preserve
  the accession unchanged as exact source identity and require only the
  10-2-6 ASCII-digit shape. Do not require or restore
  accession[:10] == subject CIK. The live Q3 canary already contains the
  counterexample: MSFT CIK 0000789019 with 10-K 0001193125-26-323660.
rationale: >
  Accession-prefix equality conflates submitting identity with subject
  identity. The accession first 10 digits are the login/submitting CIK, which
  may identify a third-party filing agent; canonical subject identity is
  instead bound by master.idx row CIK == edgar/data/<path-CIK>. Implementing
  accession[:10] == subject CIK would reject the live master index and fail
  every production poll. The accession remains the exact SEC source identity
  and is accepted only when it has the 10-2-6 ASCII-digit shape; it is never
  repaired or rewritten.
alternatives:
  - option: Keep accession[:10] == row CIK and fail closed on mismatch
    why_not: Reproduced against the in-repo canary; MSFT 10-K would raise edgar_index_cik_mismatch and kill the poll.
  - option: Repair/rewrite the accession prefix to the subject CIK
    why_not: Identity must never be repaired. The prefix is real login/submitting identity.
  - option: Skip agent-filed rows silently
    why_not: That would drop the live MSFT 10-K from discovery.
evidence:
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
  - "Canary line 16: MSFT 10-K 0001193125-26-323660 against canonical CIK 0000789019."
  - "Adversarial review of 62ea29e reproduced REJECTED edgar_index_cik_mismatch | accession prefix '0001193125' does not match row CIK '0000789019'."
  - "python3 -m pytest tests/test_fundamental_forensics_broad_sec.py::test_agent_filed_accession_is_admitted_when_row_matches_path -q → passed"
  - "Sol verdict 2026-08-21: architecture pass; ratified DEC:FF-1-ACCESSION-PREFIX-IS-TRANSMITTER with login/submitting CIK terminology and no accession[:10] == subject CIK bind."
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - tests/test_fundamental_forensics_broad_sec.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-21
---

Sol ratified this identity separation on 2026-08-21. The accession first 10
digits remain the login/submitting CIK, which may belong to a third-party
filing agent; canonical subject identity remains the master.idx row CIK bound
to edgar/data/<path-CIK>. Do not restore accession[:10] == subject CIK.
