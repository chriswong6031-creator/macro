---
key: COMPANY-DIALOGUE-OBSERVATION-IS-NOT-CALLER-AUTH
claim: >
  The protected Executive dialogue observation client derives its returned actor
  from the same current-worker snapshot. That observation does not independently
  authenticate the process calling a terminal Company Dialogue MCP bridge.
falsifier: >
  From a Mastermind checkout, run
  `git show 0d9cf2f58f9a6a1fe895d5d199abc18735201e24:integrations/slack_agent_dialogue/executive_observation_client.py`
  and
  `git show 0d9cf2f58f9a6a1fe895d5d199abc18735201e24:integrations/slack_agent_dialogue/company_dialogue_runtime_binding.py`.
  Inspect _active, resolve and the WP-3 caller comparison. This claim is false
  if that exact observer constructs actor from independently authenticated
  launching-process identity rather than from its current-worker snapshot.
  For a later proposed bridge, hold trusted caller A fixed while the current
  snapshot advances to B and demonstrate refusal before any downstream send;
  that resolves the composition risk without rewriting the historical finding.
so_what: >
  Keep issue466 with its existing owner. Reuse observation and WP-3 validation,
  but require an independent trusted Operator-Harness launch identity. Hold
  caller A fixed while the current snapshot advances to B and require zero
  downstream send. Do not copy the observed actor into caller authentication.
kind: architecture
verified_at: 2026-09-05
verified_by: >
  GitHub.fetch_file Mastermind@0d9cf2f58f9a6a1fe895d5d199abc18735201e24
  integrations/slack_agent_dialogue/executive_observation_client.py,
  blob f0c56d625c0a14a221486d2519ecf26f55eaee62, _active and resolve;
  company_dialogue_runtime_binding.py, blob e7edc7153c3012b298a9f9998eab24f2e75e0c61;
  issue466 source-preflight comment5550369972.
scope:
  - WS:SOL-CAPABILITY-FABRIC
  - WS:CHAIRMAN-CONTROL-ROOM
  - mastermind:integrations/mastermind_company_mcp/
  - mastermind:integrations/slack_agent_dialogue/
confidence: verified
---
# Composition boundary

The existing observer can describe current worker B to an old process A.
Constructing caller=B from that observation and comparing B to B cannot prove
that A is allowed to act. This is a counterexample to that proposed composition,
not a reported exploit of a deployed bridge or a defect in observer-only use.

Current-fact observation source exists. An independently trusted terminal
launch-identity seam and installed/armed accessibility were not established by
this archaeology. Do not convert that limit into a blanket claim that no safe
port exists. The issue466 owner must name the actual existing Harness seam or
return its exact bounded extension requirement before changing runtime source.

Peer UID alone, model-selected flags/environment, a static binding file and
fresh observation actor text cannot replace process/Attempt/generation binding.
The async observation client and synchronous gateway resolver also require an
explicit per-call composition, not a stale cache or nested event loop.

Existing carrier: C0BSBM78V1N/1788519240.998129. Preserve one lifecycle, binding
owner, service, currentness validator and source writer. No source, permission,
provider, installed service, deployment or production effect follows.
