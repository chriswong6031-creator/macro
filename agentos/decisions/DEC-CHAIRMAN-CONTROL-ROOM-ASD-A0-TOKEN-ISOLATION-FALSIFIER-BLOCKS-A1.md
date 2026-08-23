---
key: CHAIRMAN-CONTROL-ROOM-ASD-A0-TOKEN-ISOLATION-FALSIFIER-BLOCKS-A1
question: >
  After the MAS-125 A0 Slack fixture inspection exposed an active disposable bot
  credential to model-visible browser-tool output, should ASD continue into A1,
  move to another carrier, or stop and recover the credential boundary first?
answer: >
  Accept the A0 falsifier and stop. Treat the disposable fixture credential as
  compromised and unusable. A1, A2, A3 and A4 remain unstarted. Resume A0 only on
  the existing MAS-125 branch/PR after a human/admin securely revokes or rotates
  the credential outside every model-visible surface, then add and prove one
  minimal allowlist-only metadata verifier whose secret input arrives through the
  existing Keychain/stdin boundary. A fresh clean A0 return and explicit Sol
  release are required before A1 may begin.
rationale: >
  Token isolation was a hard precondition, not a cleanup item. Continuing after
  the credential crossed into model-visible output would make the safety proof
  false and could spread the secret into transcripts, logs, argv, environment,
  GitHub, Linear or Slack prose. The failure falsifies the authenticated browser
  inspection surface; it does not yet falsify the bounded, storeless Agent Relay
  product thesis. Keeping one existing carrier prevents duplicate attempts and
  preserves the source-law rule that an ambiguous or failed modifying path does
  not silently fail over to another identity or transport.
alternatives:
  - option: Continue A1 using the disposable fixture bot or its current token
    why_not: >
      Rejected. The token is compromised and the A0 hard stop explicitly precedes
      all implementation.
  - option: Create a fresh app, token, branch or parallel MAS-125 implementation
    why_not: >
      Rejected. That would bypass the accepted falsifier, duplicate the carrier,
      and leave the unsafe verification surface unresolved.
  - option: Rotate or inspect the token through another model-visible browser/tool path
    why_not: >
      Rejected. Recovery must happen through a secure human/admin boundary and
      must not reproduce the same exposure mechanism.
  - option: Kill the Active-Session Dialogue architecture entirely
    why_not: >
      Rejected at this evidence level. The observed failure is specific to the
      credential-verification surface; the deterministic storeless protocol and
      injected-client architecture remain untested rather than disproven.
evidence:
  - "Mastermind PR #125 exact head 9847f1bc7eaed881a5d8b5684e24edd2a80b7497 — one-file A0 falsifier return"
  - "Mastermind PR #125 review 5001858914 — Sol HOLD and ordered recovery gate"
  - "Mastermind CI run 32623161918 — SUCCESS on the exact failure-return head"
  - "Slack #s0-sol-carrier-test current membership — fixture bot U0BST4WG996 remains present; membership does not prove credential validity or revocation"
  - "Slack official token law — revocation/uninstall invalidates token authority; a human-admin action is required here because the token value may not enter model-visible tooling"
affects:
  - WS:CHAIRMAN-CONTROL-ROOM
  - mastermind:research/MASTERMIND_ACTIVE_SESSION_EXECUTIVE_DIALOGUE_F0_ARCHITECTURE_AND_FABLE01_COMMISSION_2026-08-22.md
  - mastermind:integrations/slack_agent_dialogue/**
  - mastermind:scripts/*agent*dialogue*
  - Linear:MAS-125
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

## Operational consequence

`ASD-A0A1` is active but security-blocked. PR #125 remains the sole carrier and
stays DRAFT / HOLD-FOR-SOL. Its failure record is accepted as evidence but is not
implementation acceptance and is not merge authority.

The first external action is exactly one secure human/admin revocation or rotation
of the exposed disposable fixture credential. No old or replacement secret value
may be pasted into chat, Slack, GitHub, Linear, argv, environment variables, shell
history, files, receipts or model-visible browser output.

After that action is confirmed through a non-secret receipt, the same carrier may
implement only the minimal credential-safe metadata verifier and finish the
remaining A0 falsifiers. A1 remains held until Sol reviews a fresh clean A0 return.
