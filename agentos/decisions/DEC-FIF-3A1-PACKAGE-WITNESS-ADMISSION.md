---
key: FIF-3A1-PACKAGE-WITNESS-ADMISSION
question: >
  How strictly must FIF-3A1 admit the committed AAPL filing package,
  and how may the response describe its authority?
answer: >
  Recompute index.json SHA/length; verify the exact 93-member inventory
  against the manifest; fail on duplicate/missing/extra members; stored
  members must be members of that index; retain and hash the SEC
  submissions witness for acceptance/form/report/primary-document and bind
  those manifest fields to it; the capture process mints fixture_recorded_at.
  The response is a committed golden fixture, non-attested, context/display-only.
  It is not a production issuer service.
rationale: >
  Sol REQUEST_CHANGES on PR #6268. A hand-edited recorded_at and unbound
  acceptance clock made the package look live-authoritative. Hostile
  mutations of index, inventory, and witness must fail closed.
alternatives:
  - option: Trust the committed manifest without recomputing the index
    why_not: The inventory can drift from the archive index.
  - option: Call this a production issuer service once AAPL reconstructs
    why_not: Attested admission and production coverage are NOT_BUILT.
evidence:
  - "tests/fixtures/fundamental_forensics/aapl_10k_2025/sec_submissions_witness.json sha256 6449489eef577b096abeb79f5375b7df9c95c23e4765a075222a765a19124d83 364 bytes"
  - "index sha256 d61dde83df2dde7d63041e443321eab963b245e4c0090ba6240ce1711329de83 8936 bytes"
  - "scripts/capture_fif3a1_aapl_package.py calls mint_fixture_recorded_at"
  - "hostile mutation tests in tests/test_fundamental_forensics_financial_statement_service.py"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_graph.py
  - tests/fixtures/fundamental_forensics/aapl_10k_2025/
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

Package admission is fail-closed. Delivery authority stays fixture/display-only.
