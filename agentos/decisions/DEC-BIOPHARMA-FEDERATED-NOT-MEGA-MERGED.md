---
key: BIOPHARMA-FEDERATED-NOT-MEGA-MERGED
question: >
  Should BioCatalyst, Biopharma Seasonality/Cycle Intelligence, Market Memory,
  Financial Intelligence Fabric, Defense Procurement, and future specialist
  lobes be paused and amalgamated into one central build program?
answer: >
  No. Adopt a federated architecture. Keep each specialist lobe responsible for
  its own domain truth, product workflow, rights, corrections, and outcome
  semantics. Keep Market Memory, Neural Web, FIF, Capital Structure, Options,
  Prophet, Terminal, and Portfolio as horizontal or downstream systems with
  bounded contracts. Form Biopharma Cycle Intelligence as the biopharma market-
  episode, expectation, historical-response, peer-read-through, and prospective-
  learning subprogram under the existing biocatalyst semantic parent. Freeze
  only overlapping post-P0 alpha/asymmetry/Prophet expansion and current broad
  Seasonality runtime expansion until the BCI-0 archaeology and contract freeze
  complete. Independent production recovery and accepted specialist waves may
  continue.
rationale: >
  The programs solve different jobs and have different owners, clocks, source
  rights, identity obligations, products, and failure domains. A mega-merge
  would create an unbounded critical path and make every specialist lobe wait on
  unrelated work. Leaving them fully independent without a federation freeze
  would create duplicate event stores, identity joins, analogue engines,
  financial packets, temporal vocabularies, Neural Web dimensions, and Prophet
  inputs. The existing estate already provides the correct separation: the
  semantic registry has one biocatalyst parent and a separate horizontal Market
  Memory data plane; Market Memory explicitly forbids becoming another domain
  truth engine; Company Intelligence now exposes a correction-safe
  event_workspace.v1 precedent; BioCatalyst has a real but bounded truth plane;
  FIF and Defense have their own extensive source/product roadmaps; and Prophet
  already has an evidence-family arena. Federation preserves their ambitions
  while making ports, authority, and no-rebuild boundaries explicit.
alternatives:
  - option: Pause all specialist work and merge every program into BCI
    why_not: >
      This would make BCI responsible for clinical truth, financial statements,
      procurement truth, general historical retrieval, options truth, user
      state, portfolio decisions, and Prophet. It would destroy bounded
      ownership, create one impossible release train, and turn infrastructure
      integration into a substitute for useful domain products.
  - option: Let every lobe continue independently and integrate later
    why_not: >
      Later integration without a present architecture freeze would encourage
      parallel temporal contracts, identity joins, episode stores, analogue
      engines, context fields, and authority semantics. Those collisions are
      expensive to unwind after data has accrued.
  - option: Absorb Market Memory into BCI but leave other lobes independent
    why_not: >
      Market Memory is a cross-domain cognitive/data plane intended to serve
      biopharma, defense, earnings, options, and future lobes. Making it
      biopharma-owned would either narrow the company-wide capability or cause a
      second general memory system to appear elsewhere.
  - option: Keep BioCatalyst and the old Seasonality program as two peer programs
    why_not: >
      The semantic registry already assigns clinical clocks, seasonality, and
      event evidence to the biocatalyst parent. A second peer owner would blur
      source truth and market intelligence. BCI should be a governed subprogram
      until BCI-0 proves a separate semantic card is necessary.
evidence:
  - config/mastermind_programs.yml: biocatalyst owns biopharma event, clinical, and seasonality intelligence; market-memory is a separate data plane
  - engine/neuralweb/market_memory.py: explicitly a read-only composition and not another analogue engine; market_memory.as_known_at.v1 is the shared temporal seam
  - research/BIOPHARMA_SEASONALITY_INTELLIGENCE_HANDOFF_2026-08-16.md: event-study, model/calibration, and Prophet modules are built but disconnected
  - app/seasonality.py: handler-only research surface deliberately registers no router
  - PR #5810 / 9d91bf877da4: BioCatalyst P0-C1 typed hydration states merged without changing source truth or Prophet
  - PR #5817 / 5d600641bc35: real AAPL event_workspace.v1 with immutable sibling publication and correction replay merged context-only
  - PR #5809: FIF-1R remains an independently reviewed financial_intelligence_packet.v1 and FIF-2 is explicitly stopped
  - PR #5814 / 810d6ae0b443: Defense D0R archaeology merged while D1 remains a separate authorization
  - PR #5805 / e1ec8865ac92: Market Memory M0A first-cause repair merged; M0B remains gated on prospective proof
  - mastermind/brain/neural_web_context.py plus config/mastermind_programs.yml known_unresolveds: cross-repo Neural Web authority requires separate hardening before richer BCI contradictions
  - research/DO_NOT_REBUILD.md: one-writer, one-owner, no parallel truth or hidden authority constraints
affects:
  - WS:BIOPHARMA-CYCLE-INTELLIGENCE
  - WS:MARKET-MEMORY-W2C
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - biocatalyst
  - market-memory
  - neural-web
  - prophet
  - engine/seasonality/**
  - engine/biocatalyst/**
  - engine/company_intelligence/**
  - engine/neuralweb/**
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-16
review_by: 2026-08-17
---

This decision is proposed on the BCI architecture branch and becomes durable
company architecture only when the Chairman accepts or amends the draft PR.
It grants no runtime, schema, source, product, Neural Web, Prophet, Portfolio,
or trading authority.
