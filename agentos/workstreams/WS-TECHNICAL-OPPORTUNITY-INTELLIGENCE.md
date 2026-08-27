---
key: TECHNICAL-OPPORTUNITY-INTELLIGENCE
title: Technical Opportunity Intelligence — multi-timeframe setup, trigger, path, and remaining-opportunity system
objective: >
  Build one causal technical perception layer for U.S. equities that surfaces both
  Forming/Armed opportunities before a move and Triggered/Confirmed opportunities after
  evidence arrives, with explicit trigger, invalidation, confirmation cost, chase,
  contradiction, and remaining-opportunity semantics. Done for the first vertical when
  Compression Release is proven on completed Weekly/Daily/4H inputs, produces real
  two-queue occurrences in production, renders in the product and Terminal, accrues
  prospective evidence, and receives a Sol species-by-species authority ruling.
status: active
program: market-timing-intelligence
repos: [macro, terminal]
owner: ceo-sol
class: research
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_
  - research/technical_opportunity/
  - agentos/workstreams/WS-TECHNICAL-OPPORTUNITY-INTELLIGENCE.md
  - agentos/decisions/DEC-TECHNICAL-OPPORTUNITY-INTELLIGENCE-
  - agentos/discoveries/DSC-TECHNICAL-
  - agentos/handoffs/TECHNICAL-OPPORTUNITY-INTELLIGENCE-
decisions:
  - DEC:TECHNICAL-OPPORTUNITY-INTELLIGENCE-CANONICAL-OWNERSHIP-AND-TWO-QUEUE-LAW
discoveries:
  - DSC:TECHNICAL-CONFLUENCE-V1-EXCLUDES-TECH-LAB-FAMILIES
  - DSC:TECHNICAL-4H-RESEARCH-PANEL-NOT-PROVEN
waves:
  - id: W0
    title: Architecture freeze, evidence contract, data/clock contract, and durable records
    status: awaiting_ci
    pr: 6570
    next_action: >
      Adjudicate exact-head Agent OS validation and PR CI on #6570, then complete Sol
      records-only acceptance. Do not commission W1, W2-0, runtime, or signal work before
      W0 is accepted and merged.
  - id: W1
    title: Public-method and local-estate Technical Evidence Census
    status: todo
    depends_on: [W0]
  - id: W2-0
    title: Daily/Weekly/4H data, clock, correction, coverage, rights, and Terminal-parity archaeology
    status: todo
    depends_on: [W0]
  - id: W2
    title: Bounded existing-owner data substrate extension, only if W2-0 authorizes it
    status: todo
    depends_on: [W2-0]
  - id: W3
    title: Compression Release upside/downside preregistration and phase-zero family tournament
    status: todo
    depends_on: [W1, W2-0]
  - id: W4
    title: Current per-security occurrence engine and two-queue snapshot
    status: todo
    depends_on: [W3]
  - id: W5
    title: Technical Opportunity Radar, security detail, and Terminal vertical
    status: todo
    depends_on: [W4]
  - id: W6
    title: Production shadow accrual and real-path proof
    status: todo
    depends_on: [W5]
  - id: W7
    title: Sol species-by-species kill, version, accrue, display, or bounded-consumer adjudication
    status: todo
    depends_on: [W6]
  - id: W8
    title: Bottom/top reversal vertical using Durable Bottom and Setup Species law
    status: todo
    depends_on: [W7]
landmines:
  - "Live Entry Radar owns tactical 5-minute entry events; this program must not create another radar, WebSocket plane, entry-event store, or tactical evaluator."
  - "Setup Species is the canonical scientific registry; a new technical-species registry is a duplicate control plane."
  - "The current confluence miner is a Combo-v1 benchmark, not the complete technical estate and not an entry-timing authority."
  - "The U.S. 390-minute regular session does not divide evenly into four-hour bars; research and Terminal clocks must be measured and versioned."
  - "Entitlement or a successful API call is not proof of historical point-in-time availability, corrections, rights, or universe coverage."
  - "Downside breakdown research starts with zero directional-short authority."
do_not_redo:
  - "Do not build a universal technical score or average Forming/Armed with Triggered/Confirmed."
  - "Do not redo per-name in-sample outcome audition (DNR:KILL-OUTCOME-AUDITION)."
  - "Do not repackage killed PSS standalone timers or hard gates under new names."
  - "Do not merge the setup population into Prophet's graded board (DNR:KILL-PROPHET-POP-MERGE)."
  - "Do not let an LLM originate a signal, rank, gate, size, numeric confidence, or trade."
  - "Do not begin Compression Release outcome testing until W1 and W2-0 are both accepted."
artifacts:
  - research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-27.md
  - research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_W1_EVIDENCE_CENSUS_HANDOFF_2026-08-27.md
  - research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_W2_DATA_CLOCK_HANDOFF_2026-08-27.md
  - agentos/handoffs/TECHNICAL-OPPORTUNITY-INTELLIGENCE-2026-08-27.md
next_action: >
  Complete exact-head W0 validation and Sol review on draft PR #6570. Only after
  merge may W1 Evidence Census and W2-0 Data/Clock Archaeology start on separate
  disjoint carriers; both must return before W3 preregistration or outcome testing.
---

## Boundary note

This workstream is the broad technical-perception program under
`market-timing-intelligence`. It does not subsume `WS:LIVE-ENTRY-RADAR`,
`WS:STOCK-IDENTITY`, or `WS:PROPHET-US-ENTRY-TIMING`; it consumes or hands off
through their declared boundaries.
