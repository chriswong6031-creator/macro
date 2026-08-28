---
key: OPERATOR-CONTINUITY-REALM-REBINDING-LAW
question: >
  How does Mastermind preserve Fable/Codex-Sol responsibility when a paid Claude/Codex execution
  realm exhausts capacity or must move hosts, without binding company identity to a provider
  account/native app or creating another scheduler/session store?
answer: >
  Preserve logical responsibility at the existing root Job + executive seat + accepted logical
  dialogue/session level. A provider/account/auth-home/placement change always ends/reconciles the
  current Executive Attempt, requeues the same lawful Job through existing Runtime law, claims a
  new already-eligible Worker realm through Model Router + Capacity Fabric, starts a fresh
  provider-native session through the existing Operator Harness/provider adapter, and supplies one
  immutable Executive-PREPARED continuation capsule. EFFECT_UNKNOWN blocks movement. Same-realm
  exact process/session recovery may remain inside one Attempt only through existing OHF predicates.
  V1 automatic quota rollover is limited to canonically non-modifying Attempts. Slack, Control
  Room, Steward and optional OpenClaw project/actuate bounded views only; none owns lifecycle,
  placement, failover, Slack identity or memory.
rationale: >
  Native desktop sessions and paid account identities are not durable organizational identity.
  Existing Executive Runtime/OHF already owns Attempt/session/process reconciliation; Capacity
  Fabric already owns provider/account placement; Wake owns exact current-target attention; Agent
  Relay owns bounded conversation projection. Extending those owners avoids a second queue,
  provider scheduler, session DB or retry plane while allowing the paid subscription estate to
  become one governed workforce.
alternatives:
  - option: Move/rename native Claude or Codex desktop app conversations between accounts
    why_not: Provider-native conversations cannot be safely transplanted across auth realms and GUI automation is not a canonical execution contract.
  - option: Let OpenClaw own worker sessions/failover/Slack bindings
    why_not: That would duplicate Executive lifecycle, Capacity Fabric selection and Agent Relay session/dialogue authority.
  - option: Treat Claude account numbers or Slack principals as Worker identity
    why_not: Provider/Slack identity is execution/transport evidence only and cannot establish Executive authority or continuity.
evidence:
  - "Mastermind PR #181 / merge b901dee0272a99b8a1d60385848b99b7273e8261"
  - "Mastermind docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md"
  - "Mastermind docs/superpowers/plans/2026-08-27-operator-continuity-program-index.md"
  - "Mastermind control_plane/operator_harness_contract.py ATTEMPT_BOUNDARY_MATRIX"
  - "Macro WS:EXECUTIVE-CAPACITY-FABRIC current owner law"
affects:
  - WS:EXECUTIVE-CAPACITY-FABRIC
  - WS:CHAIRMAN-CONTROL-ROOM
  - Executive Wake Fabric
  - Operator Harness / Executive OS
confidence: high
reversibility: costly
decided_by: chairman-approved-ceo-sol
decided_at: 2026-08-27
---

## Frozen operating consequences

1. Claude Code / supported Agent SDK surfaces and Codex App Server are machine-operable substrates; native apps remain cockpits/manual surfaces.
2. Cross-account/provider/placement continuity creates a new Attempt and fresh provider-native session. Same Job/seat/commission remains stable.
3. One target Attempt receives at most one immutable prepared `mastermind.operator_continuation.v1`; retries reuse its exact identity/bytes.
4. Native Claude realm readiness requires isolated host/principal auth, `WORKER_CONTEXT_AUTH_READY`, and proof the selected auth source is native claude.ai subscription login under the real Worker environment.
5. Native auth readiness is not canonical quota identity. OCR-2C must bind/version Shared AI Provider Control before automatic Claude placement.
6. One Claude preflight executable/contract family exists: `ops/executive_os/claude-worker-preflight.py`; PF1 reuses it.
7. V1 quota rollover is non-modifying only. Write-capable/effect-uncertain interruptions remain reconciliation-required with zero replacement claim/session.
8. This ruling does not change Capacity Fabric's current H0 -> P0 -> CF2-I dependency order and does not reopen CF1/CF2-F.
