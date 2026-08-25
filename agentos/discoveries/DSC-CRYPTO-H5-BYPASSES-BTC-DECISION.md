---
key: CRYPTO-H5-BYPASSES-BTC-DECISION
claim: >
  On current main, Crypto H5 derives its total crypto budget directly from
  vector/signals.alloc_optimal in scripts/build_crypto.py::_allocation instead of
  consuming the P0A btc.decision/v1 projection, so H5 bypasses P0A integrity gates.
falsifier: >
  Inspect scripts/build_crypto.py::_allocation and its caller at main
  ce4a33aeeed779530942560c5b05f4df8ab0306c. If H5 total exposure is sourced from
  a btc.decision/v1 status/final object rather than latest["alloc_optimal"], this
  claim is false.
so_what: >
  P0B must remove the H5 decision-bearing raw budget read and prove that
  btc.decision/v1 unavailable states propagate to H5 as unavailable instead of a
  stale, zeroed or recomputed allocation.
kind: architecture
verified_at: 2026-08-24
verified_by: >
  GitHub reads of scripts/build_crypto.py, engine/btc_decision.py and
  site/crypto.html at main ce4a33aeeed779530942560c5b05f4df8ab0306c
scope:
  - crypto-intelligence
  - scripts/build_crypto.py
  - scripts/build_vector.py
  - templates/crypto.html.j2
confidence: verified
---

# Crypto H5 bypasses the governed BTC decision projection

The happy-path number can look correct while the authority boundary is wrong. Both
Vector and H5 currently reach the same underlying `alloc_optimal` value, but Vector
first validates it through `btc.decision/v1` and H5 does not.

That distinction becomes observable under exactly the states P0A was built to guard:
an unexplained raw/final mismatch, malformed current or prior authority data, or an
invalid override seam. Vector can correctly become unavailable while H5 continues to
render a portfolio budget from the raw column.

P0B therefore needs adversarial tests, not only a happy-path 100% example. The key
falsifier is whether an integrity-invalid DecisionState can still produce an H5 split.