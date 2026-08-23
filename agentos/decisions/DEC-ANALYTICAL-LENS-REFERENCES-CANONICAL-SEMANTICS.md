---
key: ANALYTICAL-LENS-REFERENCES-CANONICAL-SEMANTICS
question: >
  Should Fiscal-style custom metrics become a new Mastermind custom-metric registry,
  arbitrary formula engine, or reusable research primitive, and who owns the underlying
  semantics?
answer: >
  Treat a reusable Analytical Lens as a versioned deterministic expression over canonical
  owner-native inputs. For financial inputs it resolves through FIF metric/query semantics;
  other inputs remain owned by their specialist providers. The lens stores/references its
  definition and provenance, not a competing source truth. It starts display/context-only,
  uses a closed typed expression grammar, fails closed on unit/basis/period/dimension or
  coverage conflicts, and cannot feed Prophet/Fusion without a separate owner/Eval promotion.
  Any saved user definition must use/reconcile existing terminal-user-services user state;
  this decision creates no second metric or lens database.
rationale: >
  Fiscal Run 01 showed a useful user-generated CapEx/Revenue formula that persisted locally
  but was company-specific and undiscoverable in Screener, global Charting and another issuer.
  It also exposed a sign-semantic trap because CapEx was represented as a negative cash
  outflow. Mastermind can improve the workflow only if reuse is separated from truth:
  canonical metric owners define meaning, units, periods, dimensions and corrections;
  the lens composes those inputs deterministically and reveals its calculation. FIF already
  forbids a second financial semantic model/query kernel/metric registry.
alternatives:
  - option: Build a separate custom_metrics registry with copied financial facts
    why_not: It duplicates FIF semantics and will drift on revisions, units, dimensions and source mappings.
  - option: Allow arbitrary Python/SQL/JavaScript formulas
    why_not: Arbitrary execution defeats deterministic provenance, safety, comparability and bounded evaluation.
  - option: Let an LLM directly calculate and save free-form metrics
    why_not: Models may draft a lens but the executable form must compile into the closed deterministic grammar.
  - option: Make every saved lens automatically available in universe screening
    why_not: Arithmetic success does not prove cross-company semantic comparability or coverage.
evidence:
  - "research/market_os/FISCAL_RESEARCH_OS_ARCHITECTURE_DELTA_2026-08-22.md"
  - "WS:FINANCIAL-INTELLIGENCE-FABRIC: no second semantic model, query kernel or metric registry"
  - "Mastermind Fiscal recon PR #121 observations OBS-014/015/016/029/030 at head 758741b9b89d9ee641729a81af691ad608de4720"
  - "Fiscal observation: CapEx/Revenue remained negative under source-native cash-outflow sign; no silent normalization warning observed"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - WS:MARKET-OS
  - terminal-user-services
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-22
---

Safe default scope is `single_subject`. Cross-company projection requires a comparability contract;
universe screening additionally requires measured coverage. Missing is never zero, source-native sign
is preserved unless an explicit governed transform is selected, and every result must be reversible
to expression, resolved inputs, units/bases/periods, cutoff and source receipts.

At birth: `may_rank=false`, `may_gate=false`, `may_size=false`, `may_change_ENTRY_OPEN=false`, and
`may_originate_trade=false`.
