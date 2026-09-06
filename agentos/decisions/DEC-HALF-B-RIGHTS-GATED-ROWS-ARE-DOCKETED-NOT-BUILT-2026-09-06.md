---
key: HALF-B-RIGHTS-GATED-ROWS-ARE-DOCKETED-NOT-BUILT-2026-09-06
question: >
  Twenty F00C ledger rows are blocked on a licensed source, an upstream owner
  review or an upstream acceptance rather than on engineering. What terminal
  state does Half-B record for them?
answer: >
  DOCKETED_TERMINAL_HALF_B. Each row is recorded once in a rights/upstream-gate
  docket with four fields — the verbatim missing source or upstream decision,
  the named party who can open it, the authority ceiling that would apply if it
  opened, and the one bounded first slice on the day it opens. Nothing is
  commissioned, scheduled or budgeted against any of them.
rationale: >
  The customer must reach a true answer from a records path; a null is printed
  in plain words, never fabricated; a public substitute for a licensed source
  is a proposal to open a gate, not a licence to build.
alternatives:
  - option: Change granular_disposition on the twenty rows to a new token
    why_not: >
      That column is the canonical denominator for the F00C closure summary and
      the F04 exact-capability closure map, and the F00-integrator handoff
      forbids re-deriving the admitted denominator. The terminal state is
      carried in next_bounded_child instead.
  - option: Add two new columns to the ledger CSV
    why_not: >
      A schema change rewrites all 130 rows' bytes and collides head-on with
      sibling packet B-F12-5 editing the same file in the same wave.
  - option: Build a public-source substitute for one of the licensed feeds
    why_not: >
      Charter 9.1 forbids commissioning rights-gated rows as builds before an
      explicit Chairman/commercial gate.
evidence:
  - "Ledger round-trip proven byte-identical: 84,597 bytes, sha256 77d4162499a02b61, csv QUOTE_MINIMAL lineterminator CRLF."
  - "engine/credit_momentum.py:1406-1427 — the only quantity is par_value summed per fund: ETF-held par, not issuer debt outstanding."
  - "engine/credit_momentum.py:278-285 — _load_issuer_registry reads data/corp_bonds/issuer_themes.json; a theme registry, not a canonical issuer join."
  - "engine/credit_momentum.py:1-3 — DISPLAY-TIER / NOT VALIDATED, authority all-false."
  - "engine/stock_fundamentals.py:1815 — 'Consensus ratings & price targets remain unwired'; no equity consensus-estimate source exists in the repo."
  - "agentos/handoffs/MARKET-ONTOLOGY-F00-META-CEO-CONTINUITY-PRODUCT-RESET-2026-09-05.md:333-334 — charter 10.3 repair text."
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_F04_EXACT_CAPABILITY_CLOSURE_MAP_2026-09-04.md:7 — granular_disposition is the canonical denominator."
affects:
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_HALF_B_RIGHTS_AND_UPSTREAM_GATE_DOCKET_2026-09-06.md"
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv"
confidence: high
reversibility: easy
decided_by: sonnet-builder-b-f09-7
decided_at: 2026-09-06
---

## Supersession path

A Chairman/commercial gate, a concluded K1 Evidence Foundation store review, or K2-C
acceptance each supersede this docket's line for the rows they cover — the row moves
from `DOCKETED_TERMINAL_HALF_B` to its named first bounded slice once that gate opens.
Until any such gate opens, this record is the refusal any session tempted to "just
build a public substitute" must read: the gated rows above stay records-only, and no
wave may commission a build against them on its own initiative.
