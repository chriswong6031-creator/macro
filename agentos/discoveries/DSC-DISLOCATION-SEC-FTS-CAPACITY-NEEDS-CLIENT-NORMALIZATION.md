---
key: DISLOCATION-SEC-FTS-CAPACITY-NEEDS-CLIENT-NORMALIZATION
claim: >
  A frozen SEC full-text-search lexicon has ample 2016-2025 and 2022-2025
  candidate capacity for every P0 temporary-event and control family, but SEC
  form results include amendments and broad query cells can hit the 10,000-result
  ceiling, so complete extraction requires client-side form normalization,
  recursive date sharding, pagination and deterministic deduplication.
falsifier: >
  gh run view 32354807631 --repo mastermindx-market-intelligence/macro --log;
  zero capacity in a primary family, no observed 8-K/A or 6-K/A mismatch, or no
  capped cells would disprove the stated measurements.
so_what: >
  Candidate scarcity is not P0's blocker. P0-S0 must freeze query receipts,
  fully enumerate leaf cells below the cap, preserve amendments as corrections
  and hash-order candidates before any model sees documents.
kind: data
verified_at: 2026-08-20
verified_by: "gh run view 32354807631 --repo mastermindx-market-intelligence/macro --log; artifact 9401355421"
scope: [macro, alpha-intelligence, WS:ALPHA-INTELLIGENCE-INTEGRATION]
confidence: verified
---

## Measurements

- Frozen lexicon SHA-256:
  `c164b5b3d0cfa8365a685e88662b00d8ad338957886fd51771286bf3c137cb58`.
- Output SHA-256:
  `24d691251c0f2bedb1d15d283bdd33df938f5e81030d116b23318b40cdacbe35`.
- All 292 query/form/window cells completed behind a market-data firewall.
- Observed form mismatches were `8-K/A` and `6-K/A`.
- Twenty cells reached the 10,000-result ceiling.
- Search hits remain unclassified candidates, never events.