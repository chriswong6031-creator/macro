---
key: MARKET-ONTOLOGY-K1-VOCABULARY-EXCLUDES-TXI-CHAIN-STATE
claim: >
  The frozen K1 evidence vocabulary (contracts/evidence_foundation/vocabulary.v1.json,
  version 1.0.0) admits `txi.episode_transition` as an owner store but lists
  `txi.chain_state` under `excluded_derived_heads`, so a current transmission chain
  head cannot carry a validated K1 EvidenceRef today; only recorded episode
  transitions can.
falsifier: >
  python3 -c "import json;v=json.load(open('contracts/evidence_foundation/vocabulary.v1.json'));print('txi.chain_state' in v['excluded_derived_heads'], 'txi.episode_transition' in v['owner_stores'])"
  printing anything other than `True True` at the current main, or a later
  vocabulary version that admits `txi.chain_state` as an owner store.
so_what: >
  Any composer that renders a CURRENT chain head (F04 X1 /api/ontology/explorer/v1,
  future S1 event→trace surfaces) must show a typed K1-binding limitation for the
  head and may claim `available` evidence only after an actual EvidenceRef
  validation against `txi.episode_transition` rows; counting matching JSON objects
  is not a reference. The Sol X1 ruling grants a NARROW current-head exception for
  X1 only, so no other lane may cite "K1 has no producer" or widen the exception
  without a vocabulary bump. Do not build a second evidence library to bridge it.
kind: constraint
verified_at: 2026-09-05
verified_by: >
  contracts/evidence_foundation/vocabulary.v1.json:130 (owner_stores.txi.episode_transition)
  and :168 (excluded_derived_heads) at origin/main a232b1743e54; lib/evidence_foundation.py:747
  is the only non-test source branch keyed on `txi.episode_transition`; Sol F04 X1 rulings
  1788598030.999859 / 1788600811.886279 on Slack root C0BSBM78V1N/1788584226.926809.
scope:
  - mastermindx-market-intelligence/macro
  - contracts/evidence_foundation/**
  - engine/transmission_*.py
  - WS:MARKET-OS
confidence: verified
---

# What the vocabulary actually says

`contracts/evidence_foundation/vocabulary.v1.json` is the K1 freeze
(`research/evidence_mesh/K1_EVIDENCE_FOUNDATION_CONTRACT_FREEZE_2026-08-23.md`).
Its `owner_stores` map carries twelve stores including `txi.episode_transition`;
its `excluded_derived_heads` list names `txi.chain_state` alongside
`theme_graph.current_head`, `earnings.workspace_marker`,
`qledger.evidence_clock_start` and `evidence_clock.review_rollup`. A derived head is
excluded by design: it is a projection over owner rows, not an owner row, so a
reference to it would not be immutable.

# Why sessions get this wrong

The F04 X1 first return and an early F00 assessment both phrased the gap as
"no production K1 producer exists". That is the wrong altitude: the producer exists
for transitions; the CURRENT head is what has no admitted identity. The correct
user-facing shape is a typed limitation on the head plus real references on the
transitions that changed it. Sol's X1 exception (root 1788584226.926809) permits
the current-head composition for X1 alone and forbids treating a count of
chain-matching objects as `available` references.
