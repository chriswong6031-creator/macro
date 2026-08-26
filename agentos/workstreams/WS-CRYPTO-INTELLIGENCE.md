---
key: CRYPTO-INTELLIGENCE
title: Governed crypto intelligence and decision presentation
objective: >
  Keep BTC Vector and adjacent crypto surfaces provenance-honest, with one
  declared authority for every decision-bearing output and advisory evidence
  unable to silently override it. Each wave is complete only at its separately
  authorized acceptance boundary.
status: blocked
program: crypto-intelligence
repos: [macro]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: specified
waves:
  - id: P0A
    title: BTC Decision Authority Closure on Vector
    status: done
    pr: 6294
    note: >
      PROVEN_LIVE is durably closed. Sol accepted source head
      9ce6ce711602f6bb4986ed59ea84d70b704f3eac; release reconciliation head
      e573a341e406532748a9ba62e69e8c5444341630 passed exact-head CI, fence and
      authority workflows and PR #6294 merged at 2026-08-24T09:02:31Z as
      f039c86ae037cf75238cfdd1f3d732d9b643dbb7. PR #6395 then closed the stale
      organizational residue and separately commissioned P0B as merge
      0ee40fa28c64be0dc2a7d9f2e463bd68a70809ba. The accepted P0A live ruling is
      not reopened by P0B.
  - id: P0B
    title: Crypto H5 authority closure
    status: in_progress
    depends_on: [P0A]
    next_action: >
      Do not submit a CEO runtime request while the current protected Sol Skillpack
      keeps the Personal-Pro modifying path dependency-gated. Resume only after a
      production-proven write path is canonically released; then load a fresh
      MMX/SOL_STATE_V1, prove the required Slack/Relay/admission gates, re-run the
      Macro main/open-PR collision fence and admit exactly one P0B implementation
      carrier. Implement DEC:CRYPTO-H5-BTC-BUDGET-AUTHORITY and return PR,
      exact-head tests and real H5 browser proof to Sol.
next_action: >
  Unblock the canonical Executive OS Personal-Pro modifying path under its owning
  program. Current protected Mastermind 51f9942733b86e550bb9169d2a43462bd28e774f
  still requires B2/C2 production proof before EXECOS/CEO_REQUEST_V1 and a fresh
  MMX/SOL_STATE_V1 handshake. Independent S0-R1/MAS-112 and C1/MAS-109 principal
  provisioning remain concrete gates. Once those and all then-current COMMISSION_WAVE
  gates are production-proven, re-run P0B's collision fence and admit one
  implementation attempt. Do not create a substitute runtime carrier.
blocked_by:
  - >
    Current protected Mastermind Skillpack at
    51f9942733b86e550bb9169d2a43462bd28e774f, docs/sol_skills/COMMISSION_WAVE.md,
    states that EXECOS/CEO_REQUEST_V1 may be used only after B2/C2 have proven it
    and that any missing runtime/transport gate forbids submission.
  - >
    No fresh MMX/SOL_STATE_V1 was recovered from the connected Slack principal;
    #ceo-control-room contains only older setup/operating messages and no
    discoverable #sol-runtime channel was available during the current gate check.
  - >
    Mastermind PR #146 merged G7 autonomy-arm implementation as protected merge
    51f9942733b86e550bb9169d2a43462bd28e774f, but its own completion class is
    proof-required and explicitly leaves exact host install, provider readiness,
    arm, boot re-attestation, one bounded real intent, disarm/re-arm and Agent OS
    closeout outstanding. Merge therefore is not production admission proof.
  - >
    DSC:PERSONAL-PRO-INGRESS-PRINCIPAL-GAP — the current Slack workspace does not
    expose a qualified disposable S0-R1 fixture bot in C0BRUL9F2V7 and does not
    expose the dedicated production Relay bot in prepared private C1 channel
    C0BSGABKBFY. Historical S0 fixture credentials are unsafe to reuse until secure
    rotation/revocation because a later token-isolation proof recorded model-visible
    exposure.
  - >
    Accepted Personal-Pro source law requires S0-R1 PASS plus accepted C1 before B2,
    then accepted B2 plus C2 production modifying canary before a real P0B CEO
    operation may be called admitted.
owns_paths:
  - "engine/btc_decision.py"
  - "contracts/btc_decision.schema.json"
  - "scripts/build_vector.py"
  - "templates/vector.html.j2"
  - "tests/test_btc_decision.py"
  - "scripts/build_crypto.py"
  - "templates/crypto.html.j2"
  - "tests/test_crypto_wave2.py"
decisions:
  - "DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED"
  - "DEC:CRYPTO-H5-BTC-BUDGET-AUTHORITY"
discoveries:
  - "DSC:CRYPTO-H5-BYPASSES-BTC-DECISION"
  - "DSC:PERSONAL-PRO-INGRESS-PRINCIPAL-GAP"
landmines:
  - >
    A direct H5 read of signals.alloc_optimal can produce the same happy-path
    number as btc.decision/v1 while still bypassing its integrity gates. P0B proof
    must include malformed and override cases, not only a 100% happy path.
  - >
    MAS-106 is the immutable failed original S0 experiment. The only authorized
    framed retry is MAS-112/S0-R1; do not reopen MAS-106 or create S0-R2.
  - >
    Historical bot U0BST4WG996 existed, but its then-active OAuth credential later
    crossed a model-visible app-settings boundary and is treated as compromised.
    Known bot identity is not current credential-safety proof.
  - >
    Private #sol-runtime C0BSGABKBFY now exists with Chris + ChatGPT1/2/3 only.
    Channel creation is topology preparation, not a Relay installation, C1 PASS,
    Executive admission or product execution claim.
  - >
    Executive G7 does not replace the Personal-Pro Slack admission sequence for Sol
    under the current protected Skillpack. Closed PR #6400 explored and rejected that
    bypass interpretation; do not revive it.
  - >
    Existing public #ceo-control-room C0BRDFZPLHK is not the frozen private B2/C2
    target. Do not use it for production modifying commands; reconcile that topology
    only after B2 is explicitly released.
  - >
    Economically meaningful raw/final allocation drift without an active named
    override is an integrity failure; only representation jitter is tolerated.
  - >
    The most-recent non-null prior allocation is continuity authority. Invalid,
    non-finite or out-of-range content fails closed instead of searching older rows.
  - >
    site/vector.html and site/crypto.html are regenerated publication artifacts.
    Reconcile their branch ownership against current main at release; never treat
    generated bytes as a second decision or organizational truth source.
  - >
    Slack tool availability, a merged autonomy-arm implementation or an Agent OS
    in_progress label is not Executive admission. A canonical Job receipt remains
    required before P0B can be called QUEUED or EXECUTING.
do_not_redo:
  - >
    Do not restore the retired midterm calendar veto or create a second
    allocation/override authority.
  - >
    Do not reopen P0A. PR #6294 and the accepted PROVEN_LIVE boundary are closed;
    P0B begins from that authority contract.
  - >
    Do not reopen Macro #6400. It was closed unmerged after rejecting a G7 bypass
    of Personal-Pro Slack admission. #6397 merged as the P0B runtime-gate
    reconcile; do not re-litigate that carrier.
  - >
    Do not reuse the exposed historical S0 bot credential or inspect Slack secret
    fields through model-visible browser/admin tooling.
  - >
    Do not use employee/ChatGPT Slack credentials as the C1 Relay, and do not bypass
    S0-R1/C1/B2/C2 through G7 local CLI, GitHub, Linear, MCP or another Slack action.
  - >
    Do not expand P0B into alerts, a new crypto optimizer, recommender removal,
    ETH/alt model promotion, navigation work or broader cockpit redesign.
  - >
    Do not bypass the Executive OS admission block by treating a Slack post,
    GitHub branch/issue, Linear assignment, merged G7 code or another carrier as a
    runtime Job.
artifacts:
  - agentos/handoffs/CRYPTO-INTELLIGENCE-2026-08-23-p0a-btc-decision.md
  - agentos/handoffs/CRYPTO-INTELLIGENCE-2026-08-24-p0a-close-p0b-commission.md
  - agentos/handoffs/CRYPTO-INTELLIGENCE-2026-08-24-p0b-runtime-gate.md
  - agentos/handoffs/CRYPTO-INTELLIGENCE-2026-08-25-personal-pro-ingress-unblock.md
  - agentos/decisions/DEC-CRYPTO-H5-BTC-BUDGET-AUTHORITY.md
  - agentos/discoveries/DSC-CRYPTO-H5-BYPASSES-BTC-DECISION.md
  - agentos/discoveries/DSC-PERSONAL-PRO-INGRESS-PRINCIPAL-GAP.md
  - research/CRYPTO_COCKPIT_MASTERPLAN.md
  - contracts/btc_decision.schema.json
  - verify_shots/p0a_btc_decision/
---

## P0A close

P0A is complete at its accepted production boundary. Its durable implementation
truth is PR #6294 plus merge commit
`f039c86ae037cf75238cfdd1f3d732d9b643dbb7`; PR #6395 separately reconciled the
Agent OS close and commissioned P0B. The accepted PROVEN_LIVE ruling is closed and
must not be re-litigated during P0B.

## P0B commission

P0B is separately commissioned and organizationally in progress. Its sole observable
mission is to make Crypto H5 honor the authority claim it already shows the user:
Bitcoin DecisionState sets the total crypto budget, while the existing class overlay
only splits that available budget among BTC, ETH and altcoins, with cash as the
residual.

The current defect is structural rather than visual. `scripts/build_crypto.py`
currently rereads `signals.alloc_optimal` for H5 total exposure. That bypasses the
P0A integrity projection, so an integrity-invalid state can make Vector unavailable
while H5 remains actionable. `DEC:CRYPTO-H5-BTC-BUDGET-AUTHORITY` freezes the repair
boundary; `DSC:CRYPTO-H5-BYPASSES-BTC-DECISION` records the falsifiable current-state
finding. Integrity-invalid or unavailable DecisionState must make H5 non-actionable.

## P0B runtime admission gate

Sol repeated the runtime gate against current protected Mastermind
`51f9942733b86e550bb9169d2a43462bd28e774f`. The compatible v1.0.0 Skillpack still
requires a production-proven Personal-Pro write path, a fresh `MMX/SOL_STATE_V1`,
exact grounding, expected Slack workspace/private CEO channel/sender, Relay READY +
reconciliation COMPLETE, Executive admission readiness and one-carrier binding. It
also states that `EXECOS/CEO_REQUEST_V1` may be used only after B2/C2 have proven it.

The connected Slack read recovered no fresh `MMX/SOL_STATE_V1`; `#ceo-control-room`
contains only the older Aug-20 operating/setup messages and no `#sol-runtime` channel
was discoverable from the current principal. Mastermind PR #146/G7 is now merged,
but its own proof contract explicitly leaves production host install/readiness/arm/
real-intent/disarm-rearm proof outstanding. Therefore G7 merge does not satisfy the
current P0B admission handshake.

No modifying CEO request was submitted. There is still no P0B `operation_key`,
`intent_id`, `job_id`, canonical Job status or dispatch receipt. This is a clean
refusal-before-submit, not an ambiguous modification.

## Current Executive admission predecessor

Current protected Personal-Pro law remains PR-A -> R0 -> B1 -> C1 plus independent
S0-R1 -> B2 -> C2. B1 is now implementation truth: Mastermind #106 merged as
`607a4e13cd78261ba60e4f6ffae2a8212c9074fa` and current-base B1 wrapper-hash repair
#114 merged as `00d15138eeea715fd833ba772518b06ce274a9b7`.

S0 V1/MAS-106 is an immutable `REJECTED_BY_DESIGN` experiment. MAS-112 owns the one
framed S0-R1 retry and is still `NOT_BUILT`. C1/MAS-109 owns production private
SOL_STATE read proof and has no implementation/proof PR. Sol has created its required
private four-seat `#sol-runtime` channel `C0BSGABKBFY`, but the dedicated Relay bot and
least-privilege host principal remain unproven.

Therefore P0B is blocked upstream before B2. No current Executive operation identity or
Job exists for P0B, and no Slack/Linear/GitHub projection may imply otherwise.
