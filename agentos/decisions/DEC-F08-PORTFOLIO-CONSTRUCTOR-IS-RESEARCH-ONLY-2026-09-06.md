---
key: F08-PORTFOLIO-CONSTRUCTOR-IS-RESEARCH-ONLY-2026-09-06
type: decision
status: active
workstream: MARKET-OS
question: >
  Packet B-F08-4 (terminal, "what your holdings actually look like") ships a per-user
  concentration/factor/liquidity readout over Terminal `portfolio_positions`, and its ledger
  row MO-DELTA-003 is a standing F08 portfolio-constructor row proposing role/weight targets
  over that same holdings surface. Does the F08 portfolio constructor get any execution
  capability -- order routing, a broker hook, or persisted role/weight targets -- in V1, or
  is it research-only, and if research-only, is target STORAGE itself in scope now?
answer: >
  Research-only, non-execution, for V1 and for as far ahead as this record stands: no order
  routing, no broker hook of any kind, and no persistence of computed role/weight targets in
  V1. Every surface that renders a constructor-proposed target (role or weight) carries an
  explicit research-only sentence stating the number is a research proposal, not an
  instruction, and is never wired to any execution path. Target STORAGE is explicitly out of
  scope for this record and for V1 -- it is a later slice, to be sequenced (and separately
  ruled on, including its own privacy/duplication/rights review) only after the constructor
  law itself is settled, which is what this record does.
rationale: >
  MO-DELTA-003's own ledger ceiling is `human_research_only` with the explicit line
  "non-execution - no silent rebalance/size", and its child is named exactly
  "F08 lane constructor law (forward scope); non-execution constraint stands" -- the row
  was written to be closed by a decision, not a build. The F08 architecture freeze (
  research/MARKET_ONTOLOGY_F08_ARCHITECTURE_FREEZE_2026-09-05.md) states the same ceiling
  twice: its no-rebuild redlines list "research Portfolio Constructor output never becomes
  execution/sizing authority", and §9 states "Portfolio Constructor remains
  research-proposal-only, clearly separated from any live book surface." The adjacent
  B-F08-4 readout packet is a read-time projection over the user's own existing rows with no
  new store and no scheduler; the moment either that readout or a constructor surface
  suggests a target weight as an instruction rather than a proposal, it stops being decision
  support and becomes sizing authority, which F08's do_not_redo forbids outright (no second
  holdings store / portfolio state model / risk engine / alert scheduler / local offline
  truth; research weights must not become execution/sizing authority). Ruling research-only
  now, with target storage explicitly deferred, keeps the constructor law bounded to exactly
  what MO-DELTA-003 asked for -- a forward-scope decision -- and stops a later builder from
  reading "role/weight targets" as license to wire a persistence layer or a broker call
  before the sequencing the ledger itself specifies has happened.
alternatives:
  - option: "Build an execution-capable constructor now (order routing or a broker-hook route from a computed target to a live trade)."
    why_not: "No rights/regulatory review for order execution exists anywhere in the F08 lane, no broker integration exists in the Terminal or macro stack, and this is precisely the F08 do_not_redo redline ('research weights must not become execution/sizing authority') and the MO-DELTA-003 ceiling ('non-execution - no silent rebalance/size'). Reversing this would require its own Chairman/commercial-gate ruling, exactly as F09's rights-gated rows do, and is not something a feature packet may back into."
  - option: "Persist computed role/weight targets in V1 even while keeping them non-executable (store the numbers, just don't act on them)."
    why_not: "MO-DELTA-003's own child description names target storage as a later slice -- the ledger's sequencing puts it after this constructor-law decision, not inside it. Storing targets now would stand up persistence (and its own duplication/fold/rights questions, per the F08 duplicate-row law) ahead of a dedicated design and review, and risks quietly becoming the seed of the very second holdings-adjacent store the F08 freeze's owner table forbids."
evidence:
  - "wave_b3_plan.json packet B-F08-4 ledger_rows: 'MO-DELTA-003 (constructor-law decision only: the DEC recording that role/weight targets are research-only and non-execution; target storage stays a later slice)'"
  - "wave_b3_plan.json packet B-F08-4 spec_sources: \"Ledger MO-DELTA-003: ceiling human_research_only, 'non-execution - no silent rebalance/size'; child 'F08 lane constructor law (forward scope); non-execution constraint stands'\""
  - "research/MARKET_ONTOLOGY_F08_ARCHITECTURE_FREEZE_2026-09-05.md §9: 'Portfolio Constructor remains research-proposal-only, clearly separated from any live book surface.'"
  - "research/MARKET_ONTOLOGY_F08_ARCHITECTURE_FREEZE_2026-09-05.md §1 no-rebuild redlines: 'research Portfolio Constructor output never becomes execution/sizing authority.'"
  - "wave_b3_plan.json packet B-F08-4 spec_sources, F08 do_not_redo (charter 9.2, quoted): '... research weights must not become execution/sizing authority.'"
  - "wave_b3_plan.json packet B-F08-4 acceptance clause: 'Not done unless nothing in the surface suggests a trade, a target weight, a rebalance or a size, and the paired DEC records the F08 constructor law: role/weight targets are research-only, non-execution, and never sizing authority (F08 do_not_redo; MO-DELTA-003's non-execution constraint).'"
affects:
  - "F08 lane (macro + terminal): every current and future portfolio-constructor or target-weight surface"
  - "terminal/components/PortfolioView.tsx and terminal/lib/portfolioRisk.ts (packet B-F08-4, whose owned_paths list this DEC's own path as its paired records PR)"
  - "WS:MARKET-OS"
confidence: high
reversibility: costly
decided_by: "Meta-CEO B (Claude3 seat), session 7cd4fae1-1ed9-41c2-adb4-1e5c6b0fbc5b, under DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06"
decided_at: 2026-09-06
review_by: 2026-12-06
related:
  - "DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06"
  - "WS:MARKET-OS"
---

The F08 portfolio constructor (role/weight targets over a user's holdings) is research-only
and non-execution in V1: no order routing, no broker hook, and no persisted targets. Every
surface that shows a constructor-proposed target carries an explicit research-only sentence.
Target storage is a later, separately-ruled slice per the ledger's own sequencing, not part
of this decision. Reversing to an execution-capable constructor needs its own
Chairman/commercial-gate ruling; this record does not grant one.
