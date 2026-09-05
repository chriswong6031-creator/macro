---
key: MARKET-OS-IDENTITY-PRIMITIVES-EXIST-COMPOSITION-MISSING
claim: >
  Current Data OS already owns normalized current issuer-CIK evidence and current
  alias-to-canonical-security resolution; at the 2026-09-05 reconciliation point Macro
  main had not adopted them through a general Security State subject, while open PR
  #6831 preserved the bounded owner-composition implementation but remained unmerged
  and unproven in production.
falsifier: >
  On current Macro main, inspect lib/dataos/identity.py,
  engine/intelligence_workspace/entity.py, engine/security_state.py,
  scripts/security_state_producer.py, and scripts/build_stock_library.py. Disprove this
  discovery by showing that IssuerMaster.cik_of_issuer or DataOSIdentityNormalizer no
  longer provides the stated owner evidence, or by showing that the complete #6831
  subject-composition behavior is already protected and produces a verified non-AAPL
  Security State through the live publication and dossier path.
so_what: >
  Extend and release the existing security_state.v1 composition path instead of creating
  a CIK service, namespace renderer, identity database, alias store, second
  security-state schema, or publication plane. Treat #6831 as BUILT_NOT_PROVEN source:
  first close durable review and current-base release gates, then prove MSFT through the
  real stock-library, R2, dossier, and responsive-browser journey before admitting the
  separate chart-first cockpit.
kind: architecture
verified_at: 2026-09-05
verified_by: >
  GitHub read of Macro main 72ef56eb6ec7b536b74d5e8927ead8766539b502;
  PR #6831 at fca73b7aff73d9b8bbcc0a7161f5bef4a4e98209 / tree
  c80ddd5e750c3c9199fa0562958e28a1abc45b8a with an eight-path changed-file census;
  and the complete implementation carrier C0BSBM78V1N/1788512916.722649 through its
  immutable RESULT and later release holds.
scope:
  - macro
  - terminal-user-services
  - "WS:MARKET-OS"
  - lib/dataos/identity.py
  - engine/intelligence_workspace/entity.py
  - engine/security_state.py
  - scripts/security_state_producer.py
  - scripts/build_stock_library.py
confidence: verified
---

## Reconciled source evidence

`lib/dataos/identity.py` owns normalized current issuer CIK evidence through
`IssuerMaster.cik_of_issuer()`. `engine/intelligence_workspace/entity.py` owns current
store-alias resolution through `DataOSIdentityNormalizer` and the committed
`VendorAliasTable`; neither primitive requires a new Market OS identity plane.

Macro PR #6831 is the sole implementation carrier for the bounded second-issuer repair.
Its preserved semantic head is `fca73b7aff73d9b8bbcc0a7161f5bef4a4e98209`, tree
`c80ddd5e750c3c9199fa0562958e28a1abc45b8a`. The effective source surface is exactly:

1. `.github/ci/legacy-jobs.yml`
2. `engine/security_state.py`
3. `scripts/build_stock_library.py`
4. `scripts/security_state_producer.py`
5. `tests/fixtures/security_state/golden_aapl_expected_output.json`
6. `tests/fixtures/security_state/golden_msft_input.json`
7. `tests/test_security_state_contract.py`
8. `tests/test_security_state_view_model.py`

The candidate composes one immutable owner-proven subject across security, issuer,
listing, ticker alias, current CIK, owner evidence, success/failure output, R1-R9, K1,
semantic hashing, and subject-bound last-good behavior. It preserves
`found | not_published | fetch_failed`, refuses target identity mismatch, and enables
AAPL plus MSFT without creating rank, gate, signal, forecast, execution, or trade
authority.

## Capability boundary

The source is **BUILT_NOT_PROVEN / PRODUCTION_INERT**. Exact-head CI and supporting
semantic review evidence exist, but #6831 remains Open, Draft, Hold, and unmerged. No
durable attributable non-author GitHub verdict, accepted current-base release, published
MSFT R2 object, dossier/browser proof, deployment, or production acceptance is inferred.

`MO-PAID-020` owns this prerequisite. `MO-PAID-021` remains the separate chart-first
Ticker Workspace and may not be pulled into the source repair. Canonical save and My
Market remain with the existing personal-state owners; the Research Screener remains a
later GMI/F07-dependent wave.