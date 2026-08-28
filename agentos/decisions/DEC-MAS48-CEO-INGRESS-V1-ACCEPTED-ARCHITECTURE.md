---
key: MAS48-CEO-INGRESS-V1-ACCEPTED-ARCHITECTURE
question: >
  What architecture, implementation state and transport proof law now govern the
  Personal-Pro Sol Executive writeback path after PR-A/R0 and the real S0 carrier
  falsifier?
answer: >
  Mastermind PR #91 remains the parent dedicated-ingress architecture; #96 remains
  the exact PR-A security/lifecycle/implementation law; #99 remains the Personal-Pro
  shell, hot-state and read-before-write amendment; #100 merged the hermetic PR-A
  implementation; and #103 accepted the additive diagnostic state-read law. The real
  MAS-106 S0 experiment has now falsified one narrower assumption from #99: the hosted
  ChatGPT Slack send action is not byte-transparent for the complete source message.
  In private channel C0BRUL9F2V7, ChatGPT2's intended two-line inert request arrived
  with an appended `Sent using @ChatGPT` attribution line before the fixture bot
  consumed it. MAS-106 therefore closes BLOCK / REJECTED_BY_DESIGN for the original
  exact-whole-message carrier. Mastermind PR #107, merged as
  013cff6e84e738494b2aa502b9d04fbef920fff8, is the accepted narrow response: the
  canonical command payload is exactly the first two lines (discriminator + one
  single-line JSON object) and a platform attribution may exist only as a strictly
  validated, non-authoritative trailer. MAS-112 / S0-R1 owns the one allowed framed
  retry. If S0-R1 blocks on any approved seat, direct ChatGPT-to-Slack command
  transport is rejected for V1; there is no S0-R2 special-case spiral. B1/C1 read-side
  work remains independent. B1 now exists as Mastermind draft PR #106 but is not
  accepted: Sol found a wrapper-hash architecture blocker at head
  462fe2d55a3314e8360df45d46a665a4fa96a71b and issued REQUEST_CHANGES. B2 remains
  held until accepted C1 + S0-R1 PASS + explicit Sol release. Executive SQLite remains
  the sole Job/Attempt/Worker/Event lifecycle authority; Slack remains transport/hot
  state, never a second lifecycle or authority store.
rationale: >
  The Chairman's product job remains preserving the Personal-Pro cognition seat while
  giving it one recoverable, least-privilege path into canonical Executive admission.
  The S0 result is valuable because it found a platform transformation before any
  production write authority existed. Treating the failure as evidence and amending
  only the transport framing preserves the product thesis without laundering a failed
  test into success. The payload/trailer split is acceptable only because business
  meaning, operation identity and future Executive fingerprinting derive exclusively
  from the exact two-line payload span; the attribution trailer grants no authority and
  is not a signature. A second framing failure would show the direct Slack action is too
  unstable for V1 and must trigger a different carrier architecture rather than more
  string-specific exceptions or persistence.
alternatives:
  - option: Keep the old exact-whole-message contract and call the attribution harmless
    why_not: >
      The frozen S0 kill gate explicitly required message preservation. The platform
      altered the source before the consumer boundary, so calling the original test a
      pass would erase the falsifier and weaken future review.
  - option: Strip `Sent using @ChatGPT` ad hoc inside B2
    why_not: >
      Hidden suffix stripping would silently change an accepted carrier contract in
      implementation, accept unreviewed trailing content, and turn platform-specific
      text into an undocumented normalization authority. Framing must be reviewed and
      proven separately first.
  - option: Use another Slack action path because it happens not to append attribution
    why_not: >
      An implementation inconsistency is not a reviewed carrier contract. Switching
      actions merely to dodge the footer would bypass S0 rather than solve the product
      requirement.
  - option: Add a Slack lifecycle/dedupe/replay database to absorb transport instability
    why_not: >
      Executive OS already owns canonical lifecycle/idempotency. A second durable store
      would create a competing control plane and does not solve payload authenticity.
  - option: Block B1/C1 because inbound S0 failed
    why_not: >
      B1/C1 are the outbound read plane. Their capability and security boundaries do not
      depend on ChatGPT-authored inbound command bytes; the read lane remains independently
      useful and should continue while B2 stays held.
evidence:
  - "Mastermind PR #91 merged e61e48904302d0aae53baeab0e2681ee3fbec97d — parent dedicated CeoIngress architecture"
  - "Mastermind PR #96 merged 5f9016f2db45acf60d4344656d85dfc496b87252 — exact PR-A law"
  - "Mastermind PR #99 merged b02630fc1f3587672390b383998b28cb3206202f — Personal-Pro shell/read-before-write amendment"
  - "Mastermind PR #100 merged ada77ab927394c5e406108f2e0d48d96bd89a785 — hermetic PR-A implementation"
  - "Mastermind PR #103 merged 974b809f6861dab064bb24224df2ba6f8dfa3c91 — records-only R0 state-read law"
  - "MAS-106 live Slack source parent 1787365906.166729 from ChatGPT2 U0BSB73JWNL included platform attribution after the intended two-line payload"
  - "S0 fixture receipt event Ev0BRSHM32MR / reply 1787365907.186509 measured received bytes=238 and SHA-256=7819e97f6920221d18f05bb28cd29cf6645f3a99e39de1fb6180479f20f0546f"
  - "MAS-106 is Done / REJECTED_BY_DESIGN for the original exact-whole-message carrier"
  - "Mastermind PR #107 merged 013cff6e84e738494b2aa502b9d04fbef920fff8 — carrier framing amendment; exact-head CI 32547727757 PASS"
  - "Linear MAS-112 is the distinct S0-R1 framed-carrier proof and blocks MAS-102/B2"
  - "Mastermind PR #106 is draft/HOLD-FOR-SOL B1 implementation; CI 32480617183 PASS on original head 462fe2d55a3314e8360df45d46a665a4fa96a71b, but Sol REQUEST_CHANGES remains current for the outer SOL_STATE wrapper-hash defect"
  - "Linear MAS-109/C1 depends on accepted B1 but not S0-R1; MAS-102/B2 depends on C1 + S0-R1 + explicit Sol release"
affects:
  - WS:AGENT-OS
  - MAS-9
  - MAS-48
  - MAS-75
  - MAS-101
  - MAS-102
  - MAS-106
  - MAS-107
  - MAS-108
  - MAS-109
  - MAS-110
  - MAS-112
  - agentos/decisions/DEC-SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY.md
  - research/MASTERMIND_SLACK_AGENT_EVENT_BRIDGE_CONTRACT_2026-08-20.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-22
---

## Authority and supersession scope

This decision does **not** reverse `DEC:SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY`.
Slack remains transport/acknowledgement/hot-state projection, not runtime or canonical lifecycle.

Technical precedence is now:

1. Chairman/Sol product outcome and Mastermind #91 parent architecture;
2. Mastermind #96 PR-A law, including its R2/R1 precedence in their scopes;
3. Mastermind #99 Personal-Pro shell/read-before-write/evaluation law;
4. merged PR-A source from #100;
5. Mastermind #103 R0 diagnostic read law;
6. **Mastermind #107 carrier-framing amendment for inbound Slack source-message semantics**;
7. current source contracts and Macro #6071 layer law;
8. Linear/Slack as projection/transport evidence only.

#107 supersedes only the #99/MAS-106 assumption that the complete ChatGPT-authored Slack source
must arrive byte-identical. It does not weaken sender/channel/event eligibility, Executive policy,
grounding, replay/idempotency, effect-unknown reconciliation, no-new-store law, or PR-A/R0.

## Current capability ledger

- `SHELL-1 / MAS-110`: `PROVEN_LIVE`.
- `PR-A / MAS-75`: `BUILT_NOT_PROVEN` at the product level; local admission/status is merged.
- `R0 / MAS-107`: `SPEC_ONLY`; source law is merged.
- `B1 / MAS-108`: `BUILT_NOT_PROVEN` candidate only on draft PR #106; **not accepted** while Sol's wrapper-hash REQUEST_CHANGES is open.
- `C1 / MAS-109`: `NOT_BUILT`; starts only after B1 acceptance/merge and owns production read proof.
- `S0 V1 / MAS-106`: `REJECTED_BY_DESIGN` for exact-whole-message ChatGPT→Slack command transport.
- `S0-R1 / MAS-112`: `NOT_BUILT`; one framed-carrier proof is authorized.
- `B2 / MAS-102`: `NOT_BUILT / HELD` behind accepted C1 + S0-R1 PASS + explicit Sol release.
- `C2 / MAS-101`: `NOT_BUILT / HELD` behind accepted B2.
- `MAS-48`: `PARTIAL`.

## Framed carrier law

For S0-R1 and any later B2 only after explicit release:

```text
EXECOS/CEO_REQUEST_V1
{one canonical single-line JSON object}
<optional exact reviewed platform attribution trailer>
```

The **canonical payload span** is exactly lines 1 and 2. The trailer is transport evidence only.
It grants no authority, is not a signature, and is excluded from business normalization,
operation identity, request fingerprinting and future deterministic `slack-*` intent identity.

Unknown/additional trailer text, leading prose, raw third business lines, a second discriminator,
or platform mutation inside either payload line must refuse.

Full received Slack text remains bounded at 4,500 UTF-8 bytes; the two-line payload span is bounded
at 4,350 bytes to reserve measured attribution overhead. No truncation.

Before canonical submit, the Relay must reread the exact source and rerun the same strict framing
parser. Payload drift or invalid trailer refuses. Once canonical synchronous submit starts, later
edit/delete still cannot cancel it; canonical Executive status wins.

If S0-R1 blocks, direct ChatGPT→Slack command transport is rejected for V1. Do not add S0-R2,
change Slack action paths opportunistically, or fail over to MCP/GitHub/Linear/file comments.

## Binding control-plane laws that remain unchanged

- Executive SQLite is the sole Job/Attempt/Worker/Event lifecycle authority.
- `control_plane.ceo_intent.submit_intent` remains the canonical v1 mutation sink.
- Relay never reaches the broad Operator dispatcher or direct SQLite.
- trusted Executive code derives privileged fields; retrieved/project/Slack/Linear prose grants no authority.
- accepted intent wins replay before current grounding; stale uncommitted requests refuse rather than silently re-ground.
- effect-unknown mutation outcomes reconcile canonical status before any retry; no cross-carrier failover.
- handler drain, startup latch and opaque dependency-error laws remain binding.
- CEO admission readiness remains distinct from worker/provider/Wake readiness.
- QUEUED/JOB_CREATED with `dispatched=false` proves admission only.

## Exact continuation

Primary independent lanes:

1. **B1 / PR #106:** Codex must repair the outer `MMX/SOL_STATE_V1.state_hash` so it hashes wrapper semantic content, not merely the embedded Executive snapshot. Sol then resumes adversarial review on the new exact head. C1 cannot start before B1 acceptance/merge.
2. **S0-R1 / MAS-112:** reuse the existing disposable fixture only if still secret-safe and run the full three-seat strict framed-carrier proof from #107. Zero Executive mutation. On PASS, preserve the receipt for later B2; on BLOCK, reject direct Slack command transport for V1.

Only after accepted C1 **and** S0-R1 PASS may Sol explicitly release B2. C2 remains after B2 only.
