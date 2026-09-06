---
workstream: "WS:MARKET-OS"
session: sol/mo-f00-f13-fanout-manifest-20260826
model: sol
ended_because: complete
mission: >
  Provide one allocation manifest for the Market Ontology complete-parity multi-COO
  program so F00 can assign independent Fable domain leads without collapsing work
  into one thread or rediscovering operation identities.
state_before: >
  Complete-parity scope, current-public delta law, historical 1,556-row import gate
  and multi-COO topology are frozen on PR #6504; distinct F01-F13 durable handoffs now
  exist on the same carrier. Slack still provides DELIVERY_ONLY transport and no Fable
  ACK/EXECUTING state is inferred.
changed:
  - path: agentos/handoffs/MARKET-ONTOLOGY-F00-F13-FABLE-COO-FANOUT-MANIFEST-2026-08-26.md
    what: "Created the F00-F13 Fable COO allocation manifest binding lane operation keys, durable handoffs, Linear projection and allocation law."
verified:
  - claim: "Thirteen distinct domain handoffs exist with unique operation keys."
    command: "Current PR #6504 changed-file census."
    result: "PASS at manifest creation."
unverified:
  - claim: "Thirteen Fable seats are concurrently available."
    what_would_verify: "Explicit per-lane Fable ACKs."
unresolved:
  - "F00 and lane ACK/assignment states remain delivery-time/runtime facts, not GitHub assumptions."
next_actions:
  - "After #6504 is main-canonical, post one write-gate update to the original parity Slack carrier."
  - "F00 allocates available Fable seats using this manifest; each lane ACKs its exact operation key and current pickup/collision census."
do_not_redo:
  - "Do not mint substitute operation keys for the same F01-F13 lanes while these are unreconciled."
  - "Do not mark Linear In Progress from this manifest alone."
danger_areas:
  - "Duplicate Slack delivery from another Sol session; reconcile to earliest carrier and exact operation key rather than sending another top-level dispatch."
---

# Market Ontology complete parity — F00/F01–F13 COO allocation manifest

**Program operation:** `marketontology-complete-parity-fanout-20260826-sol-001`  
**F00 Linear:** `MAS-141`  
**Canonical product owner:** `WS:MARKET-OS`  
**Shared semantic owner:** `WS:ALPHA-INTELLIGENCE-INTEGRATION`

F00 is program-control/coverage/dependency integration. It does not serialize domain PRs. The following lanes are independent sustained Fable COO ownership envelopes; actual implementation remains one useful bounded carrier per child wave.

| Lane | Linear | Operation key | Durable handoff | Primary owner |
|---|---|---|---|---|
| F01 Macro / Markets / Briefings | MAS-142 | `marketontology-f01-macro-markets-20260826-fable-001` | `MARKET-ONTOLOGY-F01-MACRO-MARKETS-BRIEFINGS-FABLE-COO-2026-08-26.md` | Market OS + current market owners |
| F02 Policy / Geo / Geospatial | MAS-143 | `marketontology-f02-policy-geo-20260826-fable-001` | `MARKET-ONTOLOGY-F02-POLICY-GEO-GEOSPATIAL-FABLE-COO-2026-08-26.md` | Market OS + policy/geo owners |
| F03 Options / Expression | MAS-144 | `marketontology-f03-options-expression-20260826-fable-001` | `MARKET-ONTOLOGY-F03-OPTIONS-EXPRESSION-FABLE-COO-2026-08-26.md` | Market OS + Options owner |
| F04 Ontology / Transmission / Opportunity | MAS-145 | `marketontology-f04-ontology-transmission-20260826-fable-001` | `MARKET-ONTOLOGY-F04-ONTOLOGY-TRANSMISSION-OPPORTUNITY-FABLE-COO-2026-08-26.md` | Alpha Integration + GMI/TXI |
| F05 Event / Impact / Catalyst | MAS-146 | `marketontology-f05-event-impact-20260826-fable-001` | `MARKET-ONTOLOGY-F05-EVENT-IMPACT-CATALYST-FABLE-COO-2026-08-26.md` | Alpha Integration + event owners |
| F06 Security / Ticker Workspace | MAS-147 | `marketontology-f06-security-workspace-20260826-fable-001` | `MARKET-ONTOLOGY-F06-SECURITY-TICKER-WORKSPACE-FABLE-COO-2026-08-26.md` | Market OS + Identity/Data OS |
| F07 Valuation / Assumptions / Scenario | MAS-148 | `marketontology-f07-valuation-scenario-20260826-fable-001` | `MARKET-ONTOLOGY-F07-VALUATION-SCENARIO-FABLE-COO-2026-08-26.md` | Market OS + FIF |
| F08 Portfolio / Alerts / Monitoring | MAS-149 | `marketontology-f08-portfolio-alerts-20260826-fable-001` | `MARKET-ONTOLOGY-F08-PORTFOLIO-ALERTS-FABLE-COO-2026-08-26.md` | Market OS + Portfolio owners |
| F09 Capital / Ownership / Materials | MAS-150 | `marketontology-f09-capital-materials-20260826-fable-001` | `MARKET-ONTOLOGY-F09-CAPITAL-OWNERSHIP-MATERIALS-FABLE-COO-2026-08-26.md` | Market OS + specialist owners |
| F10 Quant / ResearchStudy / Analogs | MAS-151 | `marketontology-f10-quant-analogs-20260826-fable-001` | `MARKET-ONTOLOGY-F10-QUANT-ANALOGS-FABLE-COO-2026-08-26.md` | Alpha Integration + Evaluation OS |
| F11 Human Research / Thesis / RMS | MAS-152 | `marketontology-f11-human-rms-20260826-fable-001` | `MARKET-ONTOLOGY-F11-HUMAN-RESEARCH-RMS-FABLE-COO-2026-08-26.md` | Market OS human research layer |
| F12 Team / Tenant / API / Platform | MAS-153 | `marketontology-f12-team-api-20260826-fable-001` | `MARKET-ONTOLOGY-F12-TEAM-TENANT-API-PLATFORM-FABLE-COO-2026-08-26.md` | Market OS + auth/tenant/delivery owners |
| F13 Ops / Learning / Reliability | MAS-154 | `marketontology-f13-ops-learning-20260826-fable-001` | `MARKET-ONTOLOGY-F13-OPS-LEARNING-RELIABILITY-FABLE-COO-2026-08-26.md` | Market OS + Eval/health/release owners |

## Allocation law

1. The first explicit Fable ACK for an operation key claims that lane; record pickup SHA and collision census.
2. F00 records lane state but does not create a second execution lifecycle. GitHub/Agent OS remain durable work truth; Executive OS owns runtime jobs when that path is genuinely used.
3. A lane may commission multiple bounded child workers/PRs concurrently with other lanes; two modifications that touch the same canonical owner/path must reconcile before writes.
4. If Fable capacity is limited, keep these separate lane identities and route well-specified child waves to frontier workers under the most relevant Fable lead. Do not merge lane identities to simplify staffing.
5. K2-C (`alpha-k2c-institutional-adapter-20260826-sol-001`) and K3-D (`alpha-k3d-economic-propagation-20260826-sol-001`) are separate already-landed operations from PR #6498 and are not F04/F10 substitutes.
6. No lane becomes `EXECUTING` from Slack delivery, Linear Todo/In Progress, branch creation or this manifest. Only explicit operator/runtime evidence advances execution state.

## F00 closure accounting

F00 reconciles three inventories:

- retained historical public P1: 1,556 detailed capability/method rows + 460 quality findings, exact-byte import gate open;
- authenticated paid baseline: 88/88 capability rows;
- current-public delta: living evidence-linked post-baseline features/method depth.

Every item ends as alias/covered, upgrade, new build, projection, context-only or explicit rejected-by-design with exact owner and proof state. No useful capability disappears because it was low priority or not yet alpha-producing.