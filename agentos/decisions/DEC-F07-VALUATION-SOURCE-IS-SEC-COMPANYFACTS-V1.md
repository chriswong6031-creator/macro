---
key: F07-VALUATION-SOURCE-IS-SEC-COMPANYFACTS-V1
question: >
  F07 (Valuation/Scenario) rows MO-PAID-022/026/035/037 were BLOCKED_RIGHTS pending a
  valuation-source ruling: what may V1 valuation use as inputs, given that no equity
  consensus-estimate source exists in the repo and licensing one is a spend decision?
answer: >
  V1 valuation inputs are SEC companyfacts reported fundamentals (public domain, already
  collected by collectors/fundamental_forensics_companyfacts.py and
  collectors/sec_capital_structure_companyfacts.py). No consensus estimates, price targets, or
  analyst ratings are used or displayed until a licensed source is contracted by the Chairman.
  Scenarios are user-visible AssumptionChange deltas (growth, margin, multiple) applied to the
  reported base, shown as an implied per-share value range with as-of and source on every
  number; ceiling research_display_only; no probability or confidence language. MO-PAID-022
  is buildable now under this ruling; MO-PAID-035 (consensus-dependent DCF/comps) stays
  deferred until a rights-cleared consensus source exists.
rationale: >
  The Chairman override tells the Meta-CEOs to finish the program without waiting for rulings;
  choosing a free, already-collected, public-domain input requires no spend and no new rights,
  so it is within Meta-CEO authority. Reported fundamentals are the only defensible valuation
  base a retail fintech user can audit, and printing the assumptions in plain words satisfies
  the F07 do_not_redo (no hidden spreadsheet truth, no unexplained probability).
alternatives:
  - option: "Wait for a Chairman consensus-source licensing decision."
    why_not: "Blocks all of F07 on a spend decision nobody has asked for; V1 does not need it."
  - option: "Use Finnhub recommendation snapshots already in the repo as a proxy for consensus."
    why_not: "engine/stock_fundamentals.py:1815 records that consensus ratings and price targets remain unwired and their redistribution rights are unverified."
  - option: "Let an LLM estimate forward numbers."
    why_not: "LLMs never originate market facts, scores, or estimates (fleet law A7)."
evidence:
  - "ledger rows MO-PAID-022 / MO-PAID-035 (research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv): 'consensus source nonexistent (verified negative)'"
  - "git ls-tree origin/main collectors/ engine/: fundamental_forensics_companyfacts.py (2371 lines), sec_capital_structure_companyfacts.py, capital_structure/companyfacts_authenticated_read.py exist"
  - "Charter §5 'F06 and F07 note' and §10 assign the dependency resolution to Meta-CEO B"
affects:
  - "WS:MARKET-OS"
  - "F07 lane"
  - "engine/valuation_scenario.py (new, packet B-F07-1)"
confidence: medium
reversibility: easy
decided_by: "session 7cd4fae1-1ed9-41c2-adb4-1e5c6b0fbc5b (Meta-CEO B, Claude3, under the Chairman override of 2026-09-05)"
decided_at: 2026-09-06
review_by: 2026-10-06
---

Packet B-F07-1 (Wave B1) implements the first surface on the AAPL stock page. If the Chairman
later licenses a consensus source, a successor DEC widens the input set; this record is not
deleted.
