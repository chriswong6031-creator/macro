---
key: CN-COMMERCIAL-SUPPLY-DILIGENCE
title: Commercial PRC supply-chain / alt-data diligence
objective: >
  Decide whether any licensed PRC corporate or supply-chain provider can lawfully
  cut Mastermind normalization debt (entity IDs, A/H, effective dates, persist,
  derived-feature, customer-facing derived display). Done = a written buy/no-buy
  verdict with primary-source license evidence, not a terminal table count.
status: parked
program: china-system
repos: [macro]
owner: chairman
class: research
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - research/CN_COMMERCIAL_SUPPLY_CHAIN_DILIGENCE_2026_08_19.md
decisions:
  - DEC:CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE
discoveries:
  - DSC:CN-TERMINAL-LICENSE-FORBIDS-MASTERMIND-DISPLAY
do_not_redo:
  - Do not buy a Wind / Choice / iFinD seat because the terminal has 产业链 or 供应链 screens.
  - Do not use a campus CSMAR / CNRDS login as a Mastermind product source.
  - Do not substitute a QCC / Tianyancha / 企查查 registry or KYC graph for 年报 top-5 disclosure edges.
  - Do not reopen procurement without the written OEM grant named in DEC:CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE.
landmines:
  - Public ToS and sales pages describe internal-system embedding. That is not customer-facing derived display.
  - Tianyancha geo-blocks the United States. An onshore 工商 API is not a default-network spine.
  - QCC public ToS §8.1 forbids derivative datasets, scoring systems, and redistribution.
  - TuShare personal tokens remain non-commercial; that is CN-A, not a reason to buy Wind.
waves:
  - id: W0
    title: GROK-CN-E commercial diligence (this packet)
    status: done
    next_action: >
      Land the research note, DEC, and DSC. Do not open a vendor conversation.
      Park the workstream until a written OEM grant exists.
next_action: >
  Do not purchase. Resume only if a named vendor returns a written grant covering
  API + persist + derived-feature + customer-facing derived display of disclosure
  (年报 top-5 / SDB-class) edges. Otherwise leave supply-chain on the public
  CNInfo floor and CN-B identity work.
---

GROK-CN-E compared commercial providers only where they could cut normalization
debt and allow lawful Mastermind-derived use. Verdict: no public 2026-08-19
license clears persist + derive + display. Full evidence:
`research/CN_COMMERCIAL_SUPPLY_CHAIN_DILIGENCE_2026_08_19.md`.
