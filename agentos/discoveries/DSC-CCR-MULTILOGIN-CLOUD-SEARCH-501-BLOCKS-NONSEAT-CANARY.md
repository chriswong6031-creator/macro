---
key: CCR-MULTILOGIN-CLOUD-SEARCH-501-BLOCKS-NONSEAT-CANARY
claim: >
  On 2026-08-24 the exact merged-runtime MAS-115 canary could reach Multilogin
  cloud and local-launcher transports with a present Keychain credential, but
  the authenticated cloud profile-search request returned HTTP 501 with a
  357-byte non-JSON body. The accepted complete-inventory gate therefore
  failed closed before any disposable-profile start request.
falsifier: >
  Revalidate the current official Multilogin profile-search contract, then run
  `python3` from the protected Mastermind runtime with a reviewed one-shot
  equivalent of `BoundedHttpClient._mlx_profile_search` that emits only status,
  byte count and schema predicates. The current blocker is falsified when it
  returns HTTP 200 with the accepted bounded JSON envelope and a complete
  stable census without emitting response content, credential, profile
  identifiers or names.
so_what: >
  A reachable endpoint is not a usable lifecycle contract. Future P0B work
  must prove the read-only cloud census independently before requesting a new
  lifecycle authorization; HTTP 501/non-JSON remains VENDOR_ERROR and grants
  no blind retry, cross-profile fallback, direct-start bypass or Chairman-seat
  operation.
kind: constraint
verified_at: 2026-08-24
verified_by: "Mastermind PR #139 merge 933382619541; python3 live v2 canary plus bounded shape/status probe; no response body or private identity emitted"
scope:
  - mastermind
  - integrations/chairman_surfaces/nonseat_canary_vendors.py
  - WS:CHAIRMAN-CONTROL-ROOM
  - MAS-115
confidence: verified
---

This records a current external blocker, not a claim that Multilogin can never
restore or replace the profile-search surface. Re-read the official contract
before changing code because the vendor surface is temporally unstable.
