---
key: FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3
question: >
  After FIF-2A/FIF-2B/FIF-2C are fixture-proven on main, should FIF-2D
  still build a dedicated pre-real-source trace endpoint, and does the
  masterplan's company-statement service remain in FIF-2?
answer: >
  No. FIF-2 is DONE / FIXTURE_PROVEN SERVICE SUBSTRATE. A dedicated
  pre-real-source trace route is rejected at this stage because governed
  query and packet receipts already carry reversible cell evidence. The
  masterplan's company-statement service requirement moves into FIF-3,
  because authoritative statement presentation requires the filing-native
  statement tree that FIF-3 itself is commissioned to build. This is a
  narrow sequencing supersession. The broader FIF thesis is unchanged.
  FIF-1 remains FROZEN. Accepted FIF-2A/B/C behavior remains FROZEN.
rationale: >
  Sol sequenced FIF-3A1 after FIF-2C landed. A fixture-only FIF-2D trace
  endpoint would duplicate evidence already present on MetricMatrix cells
  and financial_intelligence_packet.v1 receipts, while still being unable
  to present filing-native statement order. Statement reconstruction is
  not an HTTP adapter over the frozen packet; it requires a presentation
  graph built from a real issuer package. Keeping statements in FIF-2
  would either fake a tree from the 50-metric registry or reopen FIF-2
  after it is a proven substrate.
alternatives:
  - option: Build FIF-2D as a dedicated /financial/trace endpoint over FIP1
    why_not: >
      Governed query/packet receipts already carry reversible cell evidence.
      A pre-real-source trace route is rejected at this stage.
  - option: Keep company statements in FIF-2 as a registry-ordered grid
    why_not: >
      That silently reorders filing-native rows into the 50-metric catalog
      and is not as-reported statement presentation.
  - option: Leave FIF-2 in_progress until a production issuer is admitted
    why_not: >
      Production issuer admission is still blocked on the attested writer
      credential. That is FIF-3+/Wave-0B, not a reason to keep the fixture
      service substrate open.
evidence:
  - "Sol FIF-3A1 commission 2026-08-22: FIF-2 DONE / FIXTURE_PROVEN SERVICE SUBSTRATE; do not build fixture-only FIF-2D; statements move into FIF-3"
  - "FIF-2A PR #5983; FIF-2B PR #6157; FIF-2C PR #6235; acceptance records PR #6254"
  - "research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md FIF-2 endpoint list includes company statements and cell trace; statement_cell.v1 at lines 731-742"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-22
---

FIF-2 is complete as a fixture-proven query/revision/packet substrate.
FIF-2D is not started and is not the next build. Company-statement
presentation and any future source-drawer over a filing-native tree are
FIF-3 work. The masterplan end-state is not rewritten.
