---
key: ASD-MODEL-VISIBLE-OAUTH-INSPECTION-BREAKS-TOKEN-ISOLATION
claim: >
  The authenticated Slack OAuth settings inspection path used by MAS-125 can
  return an active bot credential through model-visible browser-tool output and
  therefore does not preserve the required token-isolation boundary.
falsifier: >
  After secure human/admin credential rotation, run the replacement metadata
  verifier with synthetic secret-shaped fixtures and the approved Keychain/stdin
  boundary; disprove this claim only if every model-visible success/error/receipt
  surface emits allowlisted non-secret metadata or fixed opaque error codes and no
  raw credential-shaped value. Do not re-run the quarantined browser inspection.
so_what: >
  Future ASD sessions must never inspect authenticated Slack OAuth/token settings
  through a model-visible browser or generic tool. Credential rotation is a human
  admin act; automation may receive a secret only through the narrow existing
  Keychain/stdin pattern and may expose only allowlisted metadata.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  Mastermind PR #125 exact head 9847f1bc7eaed881a5d8b5684e24edd2a80b7497,
  failure return and Sol review 5001858914
scope:
  - WS:CHAIRMAN-CONTROL-ROOM
  - mastermind:integrations/slack_agent_dialogue/**
  - mastermind:scripts/*agent*dialogue*
  - Slack app A0BS2DMVDC4
confidence: verified
---

## Boundary clarified

The secret value is deliberately absent from this record and every cited durable
surface. The finding concerns the verification mechanism, not the protocol thesis
and not all browser automation globally.

Slack channel membership, app presence, a successful OAuth page load, or prose
saying a token was rotated cannot release the gate. The recovery evidence must be
a non-secret receipt from the secure admin boundary plus the verifier's synthetic
no-leak tests and clean A0 return.
