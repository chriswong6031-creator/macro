---
key: GLOBAL-LIQUIDITY-TRANSMISSION
title: Global Liquidity Transmission perception lobe
objective: >
  Build the governed measurement plane specified by Mastermind issue #117 without
  acquiring trading authority. Done means the state producer, downstream reader,
  causal transmission lab, and accepted product surface each pass their separately
  commissioned gates with explicit point-in-time and quality receipts.
status: awaiting_review
program: policy-transmission-intelligence
repos: [macro, mastermind]
owner: ceo-sol
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - config/global_liquidity_transmission_v1.yml
  - engine/global_liquidity_transmission.py
  - scripts/build_global_liquidity_transmission.py
  - data/global_liquidity_transmission/**
  - site/liquiditydata/global_liquidity_transmission.json
  - research/GLOBAL_LIQUIDITY_*.md
discoveries:
  - DSC:BOJ-ASSETS-REQUIRE-MONTH-END-ANCHOR
artifacts:
  - research/GLOBAL_LIQUIDITY_DATA_CENSUS_2026-08-22.md
  - research/GLOBAL_LIQUIDITY_TRANSMISSION_STATE_METHODOLOGY_2026-08-22.md
  - data/global_liquidity_transmission/state_history.parquet
  - data/global_liquidity_transmission/factor_comparison_btc_4w.json
  - site/liquiditydata/global_liquidity_transmission.json
waves:
  - id: W-LIQ.0
    title: Architecture and orchestration freeze in Mastermind issues 117 and 123
    status: done
  - id: W-LIQ.1
    title: Macro data census and state-quality-freshness producer
    status: done
  - id: W-LIQ.2
    title: Mastermind reader and Market View shadow plane
    status: todo
    depends_on: [W-LIQ.1]
  - id: W-LIQ.3
    title: Shock registry and causal transmission lab
    status: todo
    depends_on: [W-LIQ.2]
  - id: W-LIQ.4
    title: Repricing gap engine
    status: todo
    depends_on: [W-LIQ.3]
  - id: W-LIQ.5
    title: Product and chart surface
    status: todo
    depends_on: [W-LIQ.4]
  - id: W-LIQ.6
    title: Learning, calibration, and promotion governance
    status: todo
    depends_on: [W-LIQ.3]
landmines:
  - "The existing engine/global_liquidity.py uses JPNASSETS provider labels directly; do not reuse its monthly timestamp kernel for causal work."
  - "Availability lag is not a vintage archive: ECB and BoJ historical revisions remain a declared limitation."
  - "A null global credit impulse is the correct result until comparable release-stamped coverage exists; never coerce US C&I and China TSF into one scalar."
do_not_redo:
  - "Do not add a second global-liquidity collector before re-running the committed census against existing stores."
  - "Do not revive discontinued EZ/JP/KR/GB M2 parquets or admit China M2/NFCI/ANFCI into the causal state without a governed vintage solution."
  - "Do not build W-LIQ.2 or later waves from this Macro producer PR; issue #123 gives Sol cross-repo sequencing and acceptance authority."
next_action: Sol reviews and either accepts the W-LIQ.1 schema/PIT limitations or specifies a bounded repair before commissioning W-LIQ.2.
---

## Boundary

The Global Liquidity Transmission system is a perception lobe. W-LIQ.1 owns
state measurement and receipts only. The later shock, curve, gap, product, and
learning waves remain unstarted and cannot infer authority from the presence of
the state artifact.

## Current result

W-LIQ.1 is code- and evidence-complete, with a causal weekly backfill through
2026-08-21 and an explicitly weak research-only BTC comparison. It is awaiting
Sol review under Mastermind issue #123 and is not merged, deployed, or accepted.
