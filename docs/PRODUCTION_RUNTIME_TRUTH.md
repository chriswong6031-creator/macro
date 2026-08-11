# Production runtime truth

Source code says what Mastermind-X can do. Runtime truth says what the production system is actually doing.

## Ownership and scope

Macro Admin owns the project-level runtime view for all three repositories:

- `mastermindx-market-intelligence/macro`
- `mastermindx-market-intelligence/mastermind-terminal`
- `mastermindx-market-intelligence/Mastermind`

The durable owner is `config/production_topology.yml`. It records stable release contracts, VPS services, scheduled systems, data planes, bridges, storage, and provider relationships. It does not replace the Global Semantic System Map. Stable runtime IDs are the join key; `semantic_program_id` stays `null` until a Semantic Map program ID is adjudicated, and may then contain only one bounded stable ID rather than duplicated architecture prose.

This layer is observability only. It does not deploy code, restart services, run analytical producers, change portfolio state, or alter signal, rank, gate, sizing, or trading authority.

## Census and adjudication

The topology was adjudicated from repository deployment contracts and the VPS runtime census, not inferred from GitHub alone.

| Area | Primary authority |
|---|---|
| Macro release and services | `app/deploy/update.sh`, deploy unit files, `/opt/macro`, local Macro health |
| Terminal release and refresh | Terminal `DEPLOY.md`, `ops/terminal-build.sh`, `ops/terminal-data`, `/opt/terminal/.gitsrc`, `.deployment-id` |
| Portfolio release and scheduler | `scripts/deploy_from_git.sh`, `scripts/deploy_code_to_vps.sh`, `app/scheduler.py`, authoritative systemd drop-in, `.deployed_git_sha` |
| Cross-repo evidence | Terminal intel/manifest artifacts, the Portfolio Macro mount and context anchors, the sanitized Mastermind feedback summary |
| Storage and providers | existing R2 sentinel evidence, expected Supabase migration, live-state mount, bounded provider-health ledger summary |

When sources disagree, the runtime collector reports the disagreement as named state. It does not silently choose the more favorable answer. A GitHub SHA, deployed marker, process SHA, health probe, and data receipt answer different questions and remain separate.

## Privacy boundary

Runtime state is volatile operational data. It is private, authenticated, generated on demand, and never committed or published to a public object store. The JSON schema is a whitelist; the collector must construct output field by field rather than serialize commands, environments, process objects, HTTP bodies, logs, or source artifacts.

Every snapshot carries `checked_at` and `valid_until`. A reader must reject or visibly mark a response after `valid_until`; `snapshot_expired()` and the report renderer enforce that boundary. An expired snapshot is never evidence that production is still healthy. `coverage` reports independently derived expected and emitted record counts, missing IDs, evidence gaps, and unresolved owners so a partial census cannot masquerade as a complete green view. Duplicate topology IDs fail collection.

The runtime response must never contain credentials, cookies, environment values, credential identifiers, database URLs, private holdings, fills, balances, user data, raw logs, stack traces, or arbitrary command lines. Provider and Neural Web evidence is reduced to bounded status/count fields; raw ledgers and raw health payloads are not passed through.

Durable topology may contain reviewed non-secret localhost URLs, unit names, and VPS paths because those are stable operational contracts. It contains no current SHA, timestamp, health result, or other volatile snapshot.

## On-demand interfaces

The supported collection model is one bounded invocation of the shared collector, for example:

```bash
python scripts/build_project_runtime_state.py --vps --check
```

The command observes existing markers, unit metadata, local health endpoints, and receipts. It prints or returns one `mastermind.runtime_state.v1` document and does not write a tracked snapshot by default.

Macro Admin may expose the same collector through an authenticated, read-only `GET /api/runtime-state` route. The route must run on demand, return the schema-validated response directly, apply the same field whitelist, and reject unauthenticated access. The CLI and route are two entry points to one collector; neither creates a daemon or a new scheduler.

## State vocabulary

| State | Meaning |
|---|---|
| `healthy` | Existing evidence satisfies the component contract. |
| `degraded` | The component works with a named reduction or fallback. |
| `failed` | A required probe or run definitively failed. |
| `stale` | Valid evidence exists but is older than its declared freshness bound. |
| `missing` | A required unit, marker, receipt, artifact, or schema proof is absent. |
| `indeterminate` | Available evidence cannot support a truthful verdict. |
| `not_due` | A scheduled system has no run due in the evaluated window. |
| `ran_no_change` | The job ran successfully and correctly published no content change. |
| `in_progress` | A bounded scheduler run started after its latest completion and remains within its runtime contract. |
| `disabled` | The component is intentionally disabled by its contract. |
| `operator_armed` | An optional system is expected to run only after explicit operator arming. |

`disabled`, `operator_armed`, `not_due`, and `ran_no_change` are not failures. Summary output is a count by named state and section; there is no composite health score.

Systemd unit state remains raw unit evidence (`active`, `inactive`, `failed`, and related states). The collector adjudicates that evidence against `expected_state` before assigning the component-level vocabulary above.

## Release and freshness semantics

Each deployable repository reports deployed SHA, canonical branch SHA, runtime SHA when the runtime exposes one, deployment lag, and runtime match independently. Lag is not automatically failure: the repository's deployment contract decides whether exact match is required or advisory. Macro's selective-restart process mismatch is `indeterminate` without a changed-path deploy receipt; it is never silently green. Portfolio's archive marker is exact deployed release identity, while the running-process identity remains `indeterminate` until `/health` exposes the marker SHA; service liveness is reported separately.

Freshness comes from existing producer receipts or small manifests whenever possible. A missing receipt is `missing`; an unreadable or ambiguous receipt is `indeterminate`; an old valid receipt is `stale`. A successful no-op is `ran_no_change` only when the producer emits evidence that it ran and intentionally made no change.

Bridge health is independent of producer and consumer health. A healthy Macro API plus stale Terminal intel is a bridge problem. A healthy Portfolio scheduler plus stale feedback summary is a publication problem. Graceful fallback must not convert either into green.

## Limits

- This is a point-in-time observation, not a historical monitoring system or uptime SLA.
- No new background daemon, high-frequency timer, monitoring vendor, or deployment control plane is introduced.
- Terminal native shells are clients, not VPS services, and are excluded.
- Terminal's expected Supabase migration is known, but runtime migration proof remains `indeterminate` until a safe authenticated schema receipt exists.
- Macro checkout identity is not an atomic served-static receipt, and Terminal's current marker proves the web build rather than every optional sidecar sync. Those producer limitations remain explicit instead of being promoted to stronger claims.
- Cron-only jobs have weaker evidence than systemd timers or the Portfolio scheduler API; absent durable run evidence remains visible as `indeterminate`.
- All 22 Portfolio scheduler IDs are represented separately. `vps_state_sync` is explicitly disabled on the authoritative VPS by its producer contract. A newer unfinished start is `in_progress`, a run beyond its declared maximum is `failed`, and last-success age is checked against daily/intraday or weekly bounds; an earlier successful finish cannot hide a dead registration.
- Localhost probes prove the origin process at collection time, not every CDN edge or signed-in browser path.
- Provider availability is an operational capacity observation, never permission to expose account identity or credentials.
- Provider state uses only reviewed rung roles, bounded counts, and the latest dated outcome per role; raw error details and provider identifiers never leave the source ledger.
- Macro→Terminal currently has consumer-side exemplar evidence rather than a bridge-wide completion receipt, so a fresh exemplar remains `degraded` instead of false-green. Macro→Portfolio proves the reviewed consumer mount plus the context artifact, not that every downstream calculation consumed it.
- The collector does not inspect private portfolio economics. Portfolio visibility is limited to release identity, scheduler/run metadata, sanitized bridge evidence, and high-level storage state.
- A live-state directory's existence proves availability only and remains `indeterminate` until a bounded schema/freshness receipt exists.
