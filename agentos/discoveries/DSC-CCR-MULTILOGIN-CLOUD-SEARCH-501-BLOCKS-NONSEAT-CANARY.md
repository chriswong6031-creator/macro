---
key: CCR-MULTILOGIN-CLOUD-SEARCH-501-BLOCKS-NONSEAT-CANARY
claim: >
  On 2026-08-24 the exact merged-runtime MAS-115 canary could reach Multilogin
  cloud and local-launcher transports with a present Keychain credential, but
  the authenticated cloud profile-search request returned HTTP 501 with a
  357-byte non-JSON body. A later bounded, read-only official-contract probe
  sent the same credential to the authenticated local-launcher status endpoint
  and received HTTP 401 with a bounded JSON error envelope. The stored
  three-segment JWT is therefore not a currently accepted Multilogin automation
  bearer; Keychain presence did not prove validity. The accepted
  complete-inventory gate failed closed before any disposable-profile start
  request.
falsifier: >
  Enroll a current Multilogin automation token through a secret-owning native
  credential boundary with `python3 scripts/mas115_setup.py credential --vendor
  multilogin`, revalidate the current official profile-search and launcher
  contracts, then run reviewed read-only probes from the protected Mastermind
  runtime that emit only status, byte count and schema predicates. The current
  blocker is falsified when the launcher accepts the bearer and profile search
  returns HTTP 200 with the accepted bounded JSON envelope and a complete stable
  census, without emitting response content, credential, profile identifiers or
  names.
so_what: >
  A present credential and reachable endpoint are not a usable lifecycle
  contract. Future P0B work must refresh the automation bearer through the
  vendor-supported secret boundary and prove launcher authentication plus the
  read-only cloud census independently before requesting a new lifecycle
  authorization. HTTP 501/non-JSON and authenticated launcher HTTP 401 remain
  VENDOR_ERROR and grant no blind retry, cross-profile fallback, direct-start
  bypass or Chairman-seat operation.
kind: constraint
verified_at: 2026-08-24
verified_by: "Mastermind PR #139 merge 933382619541; python3 live v2 canary plus bounded official-contract cloud and launcher shape/status probes; no response body or private identity emitted"
scope:
  - mastermind
  - integrations/chairman_surfaces/nonseat_canary_vendors.py
  - WS:CHAIRMAN-CONTROL-ROOM
  - MAS-115
confidence: verified
---

This records a current credential and external-contract blocker, not a claim
that Multilogin can never restore or replace the profile-search surface. Re-read
the official contract before changing code because the vendor surface is
temporally unstable. Do not infer the credential's expiry time or claims by
decoding or printing it; the accepted authenticated-launcher result is the
bounded validity test.
