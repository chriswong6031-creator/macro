---
key: MARKET-OS-IDENTITY-PRIMITIVES-EXIST-COMPOSITION-MISSING
claim: >
  Market OS universe expansion is no longer blocked because the canonical current
  issuer-CIK reader and current alias-to-security normalizer are absent. Both primitives
  exist on Macro main. The remaining gap is that the AAPL-only security_state.v1
  producer/compiler does not compose or consume them through a reusable owner-proven
  subject boundary.
falsifier: >
  Run `python3 -m pytest tests/test_dataos_identity.py
  tests/test_intelligence_workspace_identity_market.py -q` on current Macro main and
  show that `lib.dataos.identity.IssuerMaster.cik_of_issuer` does not expose normalized
  current owner-backed CIK evidence or fails to refuse conflicts, or show that
  `engine.intelligence_workspace.entity.DataOSIdentityNormalizer` cannot resolve the
  current store alias through VendorAliasTable to a canonical active SEC:* identity.
  Separately, inspect `engine/security_state.py` and
  `scripts/build_stock_library.py` and show that the production compiler/producer is
  already subject-parameterized rather than pinned to AAPL.
so_what: >
  The next Market OS Security Truth wave must extend the existing security_state.v1
  composition path, not create a CIK service, namespace renderer, identity database,
  alias store, or second security-state plane. It must consume current Data OS owners,
  preserve refusal-first identity/cardinality/correction law, and prove one non-AAPL
  issuer through the real publication and dossier path.
kind: architecture
verified_at: 2026-09-04
verified_by: >
  Current-source inspection at Macro 084848bd23130989ec6b1089d674b3f63e72c2aa:
  lib/dataos/identity.py carries SecurityIssuerRow.issuer_cik and
  IssuerMaster.cik_of_issuer; engine/intelligence_workspace/entity.py carries
  DataOSIdentityNormalizer; engine/security_state.py and scripts/build_stock_library.py
  remain explicitly AAPL-only. Canonical PRE_START implementation source is Macro issue
  #6824 under operation market-os-b1a-r1-msft-security-truth-20260903-sol-001.
scope:
  - macro
  - terminal-user-services
  - WS:MARKET-OS
  - lib/dataos/identity.py
  - engine/intelligence_workspace/entity.py
  - engine/security_state.py
  - scripts/build_stock_library.py
confidence: verified
---

## Current-source evidence

`lib/dataos/identity.py` now includes `issuer_cik` on `SecurityIssuerRow`. The
canonical `IssuerMaster` normalizes the value to the SEC ten-digit spelling, excludes
security-axis tombstones from active issuer aggregation, returns `None` for absent
current evidence, and refuses conflicting non-null CIK observations through
`cik_of_issuer()`.

`engine/intelligence_workspace/entity.py::DataOSIdentityNormalizer` already reads the
committed Data OS security master and vendor-alias artifacts, resolves current `store`
aliases through `VendorAliasTable`, validates canonical `SEC:*` identity inside the
frozen US-equity scope, and preserves active/superseded/retired state. It mints no new
identifier and owns no process cache.

The consumer has not caught up. `engine/security_state.py` still carries pinned AAPL
security, issuer, listing, ticker, CIK, event grammar, K1 consumer text, output identity,
and failure-shell identity. `scripts/build_stock_library.py` still labels the stage
AAPL-only, reads raw master artifacts around the pinned compiler, and selects only
`SECURITY_STATE_TICKERS = ("AAPL",)`.

## Boundary ruling

The smallest lawful repair is one immutable owner-proven subject assembled outside the
pure compiler and reused by success, refusal, K1 binding, event matching, last-good, and
compiler-failure paths. Data OS, Company Intelligence, Evidence Foundation, the existing
security_state.v1 schema, the existing publication lane, and the existing dossier remain
their own authorities.

A new CIK service, generic namespace store, security-state schema family, or publication
lane would duplicate current owners and is rejected. A change to an owner path is allowed
only after a focused RED proves an actual owner defect rather than a Market OS adoption
gap.

## Continuation

Macro issue #6824 is the sole canonical Git source for the bounded MSFT implementation
operation. At this discovery's creation the operation remains PRE_START: Executive OS is
in fixture mode with its runtime database absent and the control service unavailable; no
Job, Attempt, Worker, Slack child, implementation branch, implementation PR, or START
exists.
