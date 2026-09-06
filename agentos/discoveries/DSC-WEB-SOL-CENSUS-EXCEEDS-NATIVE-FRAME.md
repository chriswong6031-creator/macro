---
key: WEB-SOL-CENSUS-EXCEEDS-NATIVE-FRAME
claim: >
  The complete 128-row profile-local Web-Sol census fixture is 72,049 JSON
  bytes and therefore cannot traverse the existing 65,536-byte native payload
  guard unchanged. A lossless fixed-order compact prototype reduced that same
  fixture to 31,105 bytes. Later whole-receipt analyses fit beneath a proposed
  60 KiB ceiling only under explicit closed domains: an exact-codec executed
  bound is 36,476 bytes under its declared caps, while an independent wider
  timestamp/header-number arithmetic bound is 37,173 bytes (39,477 with its
  alternate ASCII-escaping serializer). Those bounds are conditional protocol
  evidence, not proof that C2 exists or that every future schema fits.
falsifier: >
  Re-run the immutable #502 collector fixture and #511 experiment against the
  cited native codec and show any of: the raw complete fixture is at most
  65,536 bytes; the compact form fails exact lossless expansion; the current
  65,536-byte payload guard admits one byte more; or a value accepted by the
  final enforced C2 domains makes the complete one-frame receipt exceed its
  frozen ceiling. A final schema/domain/serializer change also invalidates the
  recorded envelope bounds until they are recomputed.
so_what: >
  C2 must not forward the raw snapshot, raise the shared native guard, or add a
  chunk/reassembly plane merely because the sample is too large. Freeze one
  closed receipt shape and legal value domains, retain all rows/counts/null and
  correction semantics, encode losslessly in one frame, reject unknown fields,
  invalid types, non-finite values and over-budget strings, and test legal
  maximum-width producer-to-native-to-consumer fixtures. Non-null model or
  effort labels require serialized UTF-8 byte budgets and a new whole-envelope
  calculation; character counts and silent truncation are insufficient.
kind: constraint
verified_at: 2026-09-06
verified_by: >
  Mastermind PR #511 head 7fa0ac5aad2f5fa706ec4cc1f205d7badf1647ae;
  accepted review 5126459108; comments 5561976614 and 5562048121; source
  experiment head 23640979dd4773a1d3fa972c61cfd9dba634d9e5;
  protected census source #502 merge c5fe346fc6ffe865232454c07fc9aefec46951fe.
scope:
  - mastermindx-market-intelligence/Mastermind#502
  - mastermindx-market-intelligence/Mastermind#511
  - integrations/chairman_surfaces/web_sol_extension/census_core.js
  - integrations/chairman_surfaces/_web_sol_native_host_impl.py
  - integrations/chairman_surfaces/web_sol_protocol.py
confidence: verified
---
