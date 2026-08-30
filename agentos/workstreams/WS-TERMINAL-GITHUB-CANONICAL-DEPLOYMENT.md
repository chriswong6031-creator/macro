# WS-TERMINAL-GITHUB-CANONICAL-DEPLOYMENT

## Objective

Make GitHub the canonical implementation/evidence truth for Mastermind Terminal and make production reproducibly deployable from one accepted GitHub SHA through a mechanically observable receipt, runtime/browser proof and loud drift detection.

## Authority

- Chairman commission: autonomous Sol CEO ownership through production-proven completion.
- Canonical operation: `terminal-github-canonical-deploy-20260829-sol-001`.
- Canonical GitHub carrier: `mastermindx-market-intelligence/mastermind-terminal#483`.
- Protected Skillpack: `mastermindx-market-intelligence/Mastermind@e3d1fe6bb454df10212ce6e13bf2e4e5160f7eb5`.
- Skillpack identity: `mastermind.sol_skillpack.v1` version `1.0.1`; bootstrap major `1` compatible.
- This workstream is the Agent OS durable projection of Terminal issue #483. It is not a second operation or execution carrier.

## State

- Status: `ACTIVE / UNKNOWN_STOP_ON_PRODUCTION_MUTATION`.
- Terminal audit anchor: `afbc839e89c9e91d715c67872c44cf49895ee575`.
- Macro main at workstream creation: `2a45075ddb1139d3bcab6c6402f483040e0f6378`.
- Production mutation is prohibited until current deployed SHA and every implementation-relevant GitHub↔host delta are classified read-only.
- Repository-only architecture, audit tooling and tests may proceed.

## Aspiration

`accepted GitHub SHA → reproducible build → production deployment → immutable receipt → runtime/browser proof → drift detection`

A fresh operator must be able to determine what production is running, whether its source is clean and whether it matches accepted GitHub without SSH archaeology.

## Capability Ledger

| Capability | State | Current evidence / gap |
|---|---|---|
| GitHub default branch declared implementation authority | `BUILT_NOT_PROVEN` | `DEPLOY.md` and `AGENTS.md` say GitHub is canonical; repository description and legacy deploy script still say VPS/box reconciliation |
| One canonical deploy controller | `BROKEN` | accepted tree contains `ops/terminal-build.sh` and `scripts/deploy_terminal.sh`, each asserting deployment authority |
| Explicit accepted-SHA deployment | `NOT_BUILT` | VPS controller selects latest `origin/master` rather than requiring a full SHA |
| Production topology | `PARTIAL` | historical host/path/service evidence exists; current runtime path is not freshly proven |
| Current deployed SHA | `UNKNOWN_STOP` | `.deployment-id` mechanism exists, but no current durable/external receipt was found |
| Host implementation delta | `UNKNOWN_STOP` | tracked, untracked and ignored implementation files are not yet classified |
| Read-only pre-deploy source audit | `NOT_BUILT` | current controller resets/cleans before proving safety |
| Structured deploy receipt | `NOT_BUILT` | no versioned receipt records accepted/deployed SHA, time, cleanliness, health and rollback |
| Deployment drift sentinel | `NOT_BUILT` | no loud accepted-versus-deployed and source-cleanliness check |
| Rollback | `BUILT_NOT_PROVEN` | script path exists; no current real rollback proof or durable receipt |
| Merge-on-green controller safety | `PARTIAL` | trusted default-branch code, same-repo gating and exact-head checks are strong; generic admin/API bypass remains |
| Branch/ruleset authority | `PARTIAL` | classic non-admin protection with three required checks; no ruleset |
| Repository security/dependency baseline | `PARTIAL` | no CODEOWNERS; secret scanning and push protection disabled |
| Private-repository readiness | `UNKNOWN_STOP` | operator/deploy authentication, private-safe fetches and rollback must be proven first |
| Macro producer / Terminal consumer boundary | `PROVEN_LIVE` | current architecture keeps canonical upstream data ownership in Macro; must be preserved |

## Architecture Truth

1. GitHub default branch owns Terminal implementation truth.
2. Deployment must consume one explicit full accepted commit SHA, never a moving branch reference or arbitrary local HEAD.
3. Production must not originate ordinary source changes.
4. Unknown production-only implementation state is `UNKNOWN_STOP`; it is never permission to reset, clean, delete or overwrite.
5. One canonical deploy controller remains after replacement and rollback are production-proven; no parallel lifecycle is created.
6. Runtime data, secrets and host-local configuration retain explicit host/runtime ownership outside Git.
7. GitHub plus machine-readable runtime receipts are sufficient; no second deployment database, scheduler or Executive OS is permitted.
8. Macro remains the canonical producer of its data/contracts. Terminal remains an explicit consumer and must expose absent/stale/schema-mismatch/partial-coverage/upstream-unavailable failure states.
9. CI success, merge, deploy, runtime health, browser proof and final acceptance are distinct evidence states.
10. Repository visibility changes only after private-safe ChatGPT/Codex/operator access, deploy authentication, build fetches and rollback are proven.

## Open Work

### Wave 0 — production archaeology

- Read-only worker commission delivered in Slack `#agent-dispatch` at message `1788053391.344359`.
- Required result: exact runtime topology, service definitions, source/live trees, deployed marker, full classified GitHub↔host delta, config/data/secrets boundaries, deploy/restart/health/rollback mechanisms and a sanitized JSON receipt.
- Lifecycle at creation: `DELIVERY_ONLY / PENDING_PICKUP`; ACK, Executive OS admission, START, completion and watcher stop remain distinct.

### Wave 1 — deterministic source audit

- Add a deterministic, read-only, test-covered audit command.
- Emit versioned JSON.
- Fail closed on missing/invalid deployed SHA, dirty tracked files, unexplained host-only implementation, ignored implementation candidates or source/canonical divergence.
- Integrate it as a required preflight before any later deploy mutation.

### Wave 2 — exact-SHA deploy and receipts

- Reconcile every Wave-0 delta before mutation.
- Require an explicit accepted full SHA and prove it is accepted on the canonical branch.
- Build from immutable source, preflight source state, deploy, write atomic receipt, prove health and record rollback.
- Retire the legacy local-rsync path only after replacement and rollback pass real production proof.

### Wave 3 — repository authority/security

- Add CODEOWNERS for `.github`, deployment, operations and production-critical paths.
- Install strongest compatible native ruleset/no-generic-bypass posture.
- Preserve squash/native auto-merge and the safe merge-on-green controller.
- Disable merge/rebase commits; minimize default `GITHUB_TOKEN`; enable useful native security/dependency maintenance.
- Coordinate shared house-standard decisions with the GitHub Estate Governor.

### Wave 4 — production acceptance and visibility

- Deploy an accepted SHA through the real canonical path.
- Prove deployed SHA, clean source, health, real data, upstream failure states, responsive browser surfaces and rollback.
- Prove private-safe access/deploy/rollback and execute the lawful visibility decision.

## Gates

- `GATE-PRODUCTION-TRUTH`: current deployed SHA/runtime path/source delta is unproven. Owner: read-only production archaeology worker. Unblock: sanitized deterministic receipt with every delta classified.
- `GATE-PRIVATE-SAFE`: private repository access/deploy/build/rollback is unproven. Owner: Sol after exact-SHA path exists. Unblock: successful private-safe dry run or equivalent access/deploy proof.
- `GATE-HOUSE-STANDARD`: final native ruleset/bypass/security settings must not conflict with parallel GitHub Estate Governance. Owner: Sol coordination. Unblock: current house-standard ruling or explicit scoped exception.

## Failure States

- Missing or malformed deployment marker: `UNKNOWN_STOP`.
- Marker SHA not accepted on canonical GitHub branch: `UNKNOWN_STOP`.
- Tracked production edit or deletion: `UNKNOWN_STOP`.
- Host-only/ignored implementation candidate: `UNKNOWN_STOP` until classified/reconciled.
- Runtime built from a source other than the marker SHA: `UNKNOWN_STOP`.
- Rollback without a durable receipt: loud drift failure.
- Fresh Terminal code with absent/stale/schema-incompatible/partial Macro artifact: explicit degraded/unavailable state, never silent healthy.
- GitHub/production divergence outside an explicitly active deployment interval: loud failure.

## Production Acceptance

Completion requires all of the following, separately evidenced:

- current production source/runtime truth recovered;
- any VPS↔Git source delta reconciled without loss;
- exact accepted-SHA deployment and mechanically observable receipt;
- clean source and drift sentinel proof;
- native repository authority/security baseline;
- real production health, data and responsive browser proof;
- rollback proof and receipt;
- lawful visibility decision executed;
- canonical GitHub issue, this workstream and selective Linear projection current;
- no duplicate controller, lifecycle, truth store or data ownership plane.

## Links

- Canonical carrier: https://github.com/mastermindx-market-intelligence/mastermind-terminal/issues/483
- Slack production-audit dispatch: https://mastermindxgroup.slack.com/archives/C0BSBM78V1N/p1788053391344359
- Terminal repository: https://github.com/mastermindx-market-intelligence/mastermind-terminal
- Protected Skillpack commit: https://github.com/mastermindx-market-intelligence/Mastermind/commit/e3d1fe6bb454df10212ce6e13bf2e4e5160f7eb5

## Update History

- 2026-08-29 — Sol re-bootstrapped from protected Skillpack, recovered current Terminal/Macro GitHub truth, completed GitHub/Agent OS/Linear/Slack collision census, froze architecture, opened canonical Terminal issue #483, and delivered the read-only production archaeology commission. Production mutation remains `UNKNOWN_STOP`.