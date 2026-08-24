---
key: ASD-MODEL-VISIBLE-SETTINGS-CAN-EXPOSE-LIVE-CREDENTIALS
claim: >
  An authenticated third-party app/settings page may render a live credential into its DOM or
  browser inspection surface, so read-only model-visible inspection is not a safe way to verify
  credential metadata. MAS-125 A0 observed this on a disposable Slack fixture app: the active bot
  credential crossed into model-visible browser-tool output even though it was never intentionally
  transcribed or committed.
falsifier: >
  The claim is falsified only if the verification path prevents credential-bearing fields from
  entering the model/tool boundary in the first place and a synthetic credential test proves that
  only allowlisted non-secret metadata can be emitted. Redaction after browser/tool capture does not
  falsify the claim because the secret has already crossed the forbidden boundary.
so_what: >
  Future Slack/vendor credential verification for ASD, P0B or adjacent local integrations must not
  inspect live credentials through model-visible settings pages, DOM/DevTools or ordinary command
  output. Use a human-controlled secure source and a narrow helper/verifier whose contract emits
  only allowlisted non-secret facts and fixed opaque errors. Reuse Mastermind's reviewed Keychain
  to stdin-only secret-delivery pattern conceptually; do not invent a generic secret service or
  new credential/state plane.
kind: landmine
verified_at: 2026-08-23
verified_by: "Mastermind PR #125 head 9847f1bc7eaed881a5d8b5684e24edd2a80b7497; Sol review 5001858914"
scope:
  - mastermind
  - macro
  - WS:CHAIRMAN-CONTROL-ROOM
  - MAS-125
  - MAS-115
confidence: verified
---

## Safety state

The disposable Slack fixture credential observed during MAS-125 A0 is treated as compromised until
a human/admin securely revokes or rotates it outside any model-visible tool. This discovery records
no credential value and does not claim revocation has occurred.

A0 correctly stopped before A1. The incident is evidence against the verification surface, not a
ruling that a storeless Agent Relay is impossible. Recovery stays on the same Mastermind PR #125
carrier and requires a clean A0 rerun after credential rotation/revocation and verifier proof.
