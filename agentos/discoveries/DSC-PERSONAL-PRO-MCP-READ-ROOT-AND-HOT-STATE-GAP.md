---
key: PERSONAL-PRO-MCP-READ-ROOT-AND-HOT-STATE-GAP
claim: >
  At protected Mastermind c707b7c196b1a547cc9fc7fc43907bf2fdfb4c36,
  the direct readonly Executive MCP and authenticated Executive app bind all four
  lifecycle reads to repo_root, while the accepted Executive service contract
  explicitly separates runtime_root from proof_source_repository and
  proof_workspace_root. The intended production root split is therefore proven
  in source even though current installed-host availability is not. The selected
  production architecture preserves the existing five-tool MCP and Secure MCP
  Tunnel but routes its four reads through one dedicated read-only AF_UNIX port
  composed inside the existing ExecutiveControlService over the already-open
  canonical Runtime and trusted proof-source grounding. Direct production SQLite,
  a runtime-path argument in the tunnel process, broad Operator access, CeoIngress
  widening and a Steward/Executive super-MCP are rejected. Rich MCP orientation
  remains distinct from diagnostic admission hot state and cannot alone replace
  current write preflight.
falsifier: >
  In an approved current Mastermind checkout after verifying origin/master, run
  `git show origin/master:integrations/executive_mcp/adapter.py`,
  `git show origin/master:control_plane/executive_service.py`,
  `git show origin/master:ops/executive_os/control.json.template`,
  `git show origin/master:control_plane/executive_ceo_ingress.py`, and
  `git show origin/master:control_plane/executive_dialogue_observation.py`.
  A protected change that gives the existing MCP a canonical service-backed read
  path with equivalent least-privilege, source/runtime-generation and no-write
  semantics refutes the NOT_BUILT portion; a protected service contract no longer
  separating Runtime and proof source refutes the split-root claim. Separately,
  a current sanitized host receipt plus real Personal-account calls must bind the
  installed service, source, tool schema, tunnel association, canonical Runtime
  generation and freshness to supersede the production-proof limitation. A
  plugin scan, fresh generated_at, fixture result, missing checkout database,
  direct SQLite read or empty local Runtime cannot.
so_what: >
  Use the unchanged server first to classify Personal-Pro client case A/B/C/D,
  but treat that as client evidence only. For production, extend the existing
  Executive service with a dedicated read port and connect the existing MCP
  gateway to it; keep repo-local reads development/fixture-only. Do not implement
  while active PR 491 owns executive_service.py or PR 492 owns
  executive_inbox.py. Preserve CeoIngress as submit/status/hot-state, Steward as
  a separate truthful-PARTIAL organizational cockpit, and SOL_STATE/admission
  preflight until equivalent production proof and a protected amendment replace it.
kind: architecture
verified_at: 2026-09-05
verified_by: >
  GitHub.fetch of protected Mastermind branches/master at
  c707b7c196b1a547cc9fc7fc43907bf2fdfb4c36; same-SHA GitHub.fetch_file reads of
  integrations/executive_mcp/server.py, adapter.py and schemas.py,
  integrations/mastermind_executive_app/gateway.py and admission.py,
  control_plane/executive_inbox.py, executive_service.py,
  executive_ceo_ingress.py, executive_hot_state.py,
  executive_dialogue_observation.py, ops/executive_os/control.json.template,
  docs/EXECUTIVE_MCP.md, docs/CEO_INTENT_BRIDGE.md, and the protected Personal-Pro
  and Business surface architecture records. Existing collision evidence:
  Mastermind PRs #491, #492, #463 and #469. Steward limitation and disposition:
  issue #458 comment #5553996467. Detailed architecture freeze: Mastermind PR
  #489 head 3529b1a7567a0acbc4377270e487913fb9ccf1fd, still draft and production-inert.
scope:
  - executive-os
  - personal-pro
  - mastermind
  - agentos
confidence: verified
---

# Personal-Pro MCP connectivity is not canonical Executive readiness

This record distinguishes client eligibility, tool invocation, source grounding,
canonical Runtime fidelity and diagnostic admission readiness. No actual
Personal-Pro MCP call, privileged host read, account association, source
implementation or production effect occurred in the authoring session.

## Current direct gateway and canonical service disagree by design

The existing five-tool MCP remains the correct external product contract.
Readonly mode advertises four reads plus `submit_ceo_intent`, and refuses the
modifying tool with `production_write_disabled` before any production write path.

Its current read adapter, however, accepts one `repo_root`. Outside fixture mode
`GatewayConfig.runtime_root` returns that same root. State and Inbox use
`repo_root`; Job and intent status open the same root; Executive Inbox looks for
`data/control_plane/executive.sqlite3` beneath it. The authenticated Executive app
uses the same direct read gateway.

The accepted production control configuration is intentionally different:

- Runtime: `/var/db/mastermind-executive/control/db`;
- proof source: `/var/db/mastermind-executive/control/admin-checkout/<sha>`;
- job workspace: `/var/db/mastermind-executive/jobs/workspaces`.

`ExecutiveControlService` opens the authoritative Runtime and owns source
attestation under those distinct coordinates. Thus the direct repo-local gateway
cannot become a canonical production lifecycle reader merely by pointing it at
one of the roots. Current installed-host state may be stale, absent or blocked by
permissions, but the intended source topology is no longer ambiguous.

## Selected boundary

Keep the existing MCP server and private Secure MCP Tunnel. In production, its
surface process keeps only source/orientation access and calls a new read-only
local client. That client talks to a dedicated AF_UNIX listener composed inside
the existing Executive service. The listener receives the already-open Runtime
and trusted grounding provider and exposes exactly the four existing read
projections.

The pattern follows protected `executive_dialogue_observation`: closed schemas,
exact peer, default-disabled all-or-none configuration, one request per
connection, bounded bytes/time, symlink/foreign-inode refusal and no independent
daemon or store. The read principal must be distinct from Executive UID 450,
CeoIngress/Relay UID 452 and Agent Relay UID 457 unless a later host-security
review explicitly proves reuse safe.

The production surface may never access the Runtime database tree, general
Operator socket or CeoIngress submit socket. CeoIngress stays narrow. Intent
status reuses the same canonical resolver logic through the read service rather
than granting a read principal modification-socket access.

## Tool behavior

`executive_state` joins reviewed source orientation to canonical in-process hot
state and bounded lifecycle facts while preserving separate source/service/
Runtime generations and freshness. It is rich orientation, not a write token.

`executive_inbox` refactors the existing producer to accept the already-open
Runtime separately from source context. It is not copied into a second Inbox.
Current strict-v2 provenance work remains under PR #492.

`executive_job` returns one exact Job only; there is no list-all, dispatch or
Operator surface. `ceo_intent_status` reuses existing exact intent-resolution
semantics and receives no submission authority.

If the Personal account rejects the mixed manifest only after tunnel/auth/schema
causes are excluded, a four-read projection of the same registry/gateway/client
is permitted. It is not another backend.

## Steward and hot-state roles remain separate

Steward/Secretary supplies organizational responsibility and attention context.
Current PR #463 and product ruling #5553996467 truthfully leave four fact families
PARTIAL/DEGRADED. It must not synthesize missing Runtime binding, requested action,
objective or surface-health facts and must not absorb the Executive read plane.

Direct canonical MCP is the target primary **rich** Executive orientation path.
`MMX/SOL_STATE_V1` / `executive_hot_state` remains compact admission and
transport-health evidence, write preflight and outage telemetry. Current law does
not change until production proof and a protected amendment activate that role
split. C1's original effect must still be reconciled.

## No-code canary and production proof

The unchanged Personal-Pro canary still answers whether the account associates
the tunnel, scans the mixed manifest, exposes/enables the tools, invokes reads
and blocks or exposes modify. It does not prove the canonical service backend.

Production proof additionally binds server source/version/schema, surface source
SHA, service generation, canonical Runtime high-water, trusted proof-source
identity, freshness and independent owner-native read agreement. Missing or
unreadable Runtime is unavailable, not zero; absent legitimate Job/intent IDs
leave those tests NOT_EXERCISED rather than fabricated.

A production outage must remain visible. The surface never falls back to
repo-local lifecycle reads, direct SQLite or the broad Operator socket. A new
wrapper timestamp cannot refresh old state.

## Implementation hold and collision law

No build is released by this record. PR #491 owns Executive service/dialogue
paths on a STARTed nonterminal Runtime Continuity carrier. PR #492 owns Executive
Inbox. PR #463 owns the Steward slice, PR #469 owns separate BSC metadata, and
the W3C carrier owns native host/install observation. Obtain terminal/release or
a jointly authorized path transfer before one canonical-read vertical starts.

The complete product contract, data/time/null/failure semantics, execution DAG,
acceptance matrix and source manifest are in
[Mastermind PR #489](https://github.com/mastermindx-market-intelligence/Mastermind/pull/489).
This discovery is the durable organizational landmine, not another API, Runtime,
queue, memory or control plane.

The Personal-Pro census remains on
[its exact carrier](https://mastermindxgroup.slack.com/archives/C0BSBM78V1N/p1788605608765019),
operation `personal-pro-executive-read-census-20260905-sol-001`. At the last read
it was `DELIVERY_UNCONSUMED`, with no receiver ACK or START. Do not infer progress
or send a replacement operation.

C1 Step D remains `EFFECT_UNKNOWN` on its original RuntimeBinding at
`C0BSBM78V1N/1787889177.672699`. S0-R1, B2 and C2 retain their gates. Neither this
source freeze nor any records merge authorizes replay, installation, account
change, provider action or production write.
