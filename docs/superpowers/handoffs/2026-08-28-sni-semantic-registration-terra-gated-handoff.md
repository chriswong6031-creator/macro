# SNI Semantic Registration — Gated Terra Handoff

**Operation key:** `sni-semantic-registration-20260828-001`  
**State:** PRECOMMISSION / START-GATED  
**RECEIVER_MODE:** OPEN_PICKUP until the Chairman delivers this packet to a concrete eligible Terra account/session.  
**PREFERRED_AVENUE:** Terra  
**ACCOUNT_BINDING:** CHAIRMAN_SELECTS  
**RECEIVER_BINDING_MODE:** CAPACITY_SELECTABLE  
**WHY:** This is a bounded records/semantic-registry change with an exact plan, one repository, deterministic generated output, and explicit validation commands.  
**WHY NOT FABLE:** Principal continuity and architecture reconstruction are unnecessary; any new ownership/authority fork must return to Sol rather than be decided inside this operation.

GitHub presence is **not** a receiver assignment. No worker may self-claim this operation merely by finding this file. When the Chairman deliberately delivers it to a concrete eligible Terra account/session, that live delivery is the receiver assignment and the selected worker must immediately perform the pickup handshake below.

## Observable mission

Register `single-name-intelligence` in the existing canonical Mastermind semantic registry, create the durable `WS:SINGLE-NAME-INTELLIGENCE-OS` Agent OS workstream under that exact program key, close the SNI-1 registry gate, and stop before any SNI-1A contract implementation.

## Why it matters

SNI is already architecturally distinct from Market Timing, Fundamental Forensics, Earnings Intelligence, China System, Options Intelligence, Terminal, and Portfolio. Until the canonical semantic program exists, the durable SNI workstream cannot validate honestly and every later implementation wave lacks a lawful organizational parent.

## Authority / precedence

Read in this order before START:

1. current protected Mastermind Sol Skillpack at pickup time;
2. merged SNI-0 architecture: `docs/superpowers/specs/2026-08-28-single-name-intelligence-os-design.md`;
3. merged SNI-1 design: `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md`;
4. binding identity amendment: `docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md`;
5. `DEC:SNI-IDENTITY-AUTHORITY-CHAIN`;
6. exact execution plan: `docs/superpowers/plans/2026-08-28-sni-semantic-registration.md`;
7. current `config/mastermind_programs.yml`, system-map generator/tests, and Agent OS validator on the actual pickup base.

If current `main` contains a newer colliding semantic-system or SNI source, stop with `DECISION_REQUEST` rather than silently rewriting the plan.

## Pickup / watcher / START contract

Upon deliberate Chairman delivery to the selected Terra account/session:

1. Emit `PICKUP_ACK sni-semantic-registration-20260828-001` with the actual receiver identity. ACK means pickup only.
2. Read this packet, the exact plan, current protected Skillpack, current `main`, PR #6613, and PR #6615.
3. Arm the required exact-carrier continuation path and emit a truthful `WATCH_ARMED` receipt before ending the pickup turn. If the current surface cannot arm a watcher after the canonical tool-first checks, return the accepted typed `WATCH_UNAVAILABLE` with the exact checked surface/error.
4. **Do not START while any gate below is false.** Report the held gate and remain in the same operation/carrier.
5. Once every gate is clear, emit a separate `START sni-semantic-registration-20260828-001` and execute only this mission.

### START gates

All must be true:

- PR #6613 is merged into current `main` and its exact merged SNI-1 architecture includes the identity-authority amendment;
- PR #6615 (or its reconciled exact successor containing the two execution plans) is merged into current `main`;
- current `main` is re-read immediately before branch/worktree creation;
- `config/mastermind_programs.yml` still lacks `single-name-intelligence` (otherwise reconcile rather than duplicate);
- no open/current branch or PR is already implementing this exact semantic registration;
- no newer canonical source has assigned SNI to a different parent program.

## Exact scope

Follow `docs/superpowers/plans/2026-08-28-sni-semantic-registration.md` task-by-task. Expected change surface:

- `config/mastermind_programs.yml`;
- `tests/test_mastermind_system_map.py`;
- generated `docs/MASTERMIND_SYSTEM_MAP.md`;
- new `agentos/workstreams/WS-SINGLE-NAME-INTELLIGENCE-OS.md`;
- `research/single_name_intelligence/SNI1_PROGRAM_REGISTRY_GATE_2026-08-28.md`.

Use the repository's existing system-map generator and Agent OS validator. Create no parallel registry or lifecycle store.

## Non-goals

Do not:

- implement SNI-1A schema or Python validator;
- change Data OS identity;
- read or modify owner data planes;
- create Terminal UI/routes;
- create a forecast, score, signal, rank, gate, sizing or trade authority;
- purchase/activate HKEX data;
- modify Stock Identity, Earnings, Capital Structure, China/HK, Options, qledger/Evaluation OS, Prophet or Portfolio ownership;
- add a product surface merely because the program is registered;
- absorb the separate SNI-1A operation.

## Required semantic boundary

The registered program must remain a project-scope composition/research/product owner with `context_only` authority. It may own derived reference-twin composition, the single-name experience, SNI-specific residual/response/forecast research definitions, and projection of forecast memory through existing owners. It must explicitly not own upstream identity/events/fundamentals/capital/options/China/market-data/graph/forecast-ledger/portfolio truth.

Data OS remains canonical `ISS:` / `SEC:` / listing identity authority. SNI relationship records never mint those namespaces.

## Ordered execution

1. Create isolated branch/worktree from current `main` after all START gates clear.
2. Write the focused failing system-map test and update expected program census 60→61.
3. Add exactly one `single-name-intelligence` program entry with existing relationship vocabulary and no live product-surface claim.
4. Regenerate `docs/MASTERMIND_SYSTEM_MAP.md` via the existing generator.
5. Run the focused semantic-map tests.
6. Create `WS-SINGLE-NAME-INTELLIGENCE-OS` exactly under `program: single-name-intelligence`.
7. Mark the historical registry gate satisfied without deleting the historical finding.
8. Run `python3 scripts/agentos.py validate` and the existing Agent OS test modules.
9. Open one bounded PR. Do not merge it yourself unless the current commission explicitly grants that authority; return it to Sol for review.

## Acceptance tests

At minimum, produce receipts for:

```bash
python3 -m pytest tests/test_mastermind_system_map.py -q
python3 scripts/agentos.py validate
```

Also run the repository's existing Agent OS test modules discovered by `git ls-files 'tests/test_agentos*.py'` and report the exact command/result. Hosted CI must be green on the exact PR head before Sol acceptance.

The generated semantic map must be deterministic and produced by the existing generator; hand-editing `docs/MASTERMIND_SYSTEM_MAP.md` fails the mission.

## Failure states

Return `BLOCKED`/`DECISION_REQUEST` rather than improvising if:

- parent architecture/planning PRs are not merged;
- `single-name-intelligence` already exists with different semantics;
- program census expectations changed for unrelated new programs and the plan's 60→61 assumption is stale;
- another worker already owns the same semantic registration paths;
- Agent OS rejects the proposed workstream for a reason other than the expected pre-registration missing key;
- current registry vocabulary cannot express the frozen SNI relationships without widening the semantic schema;
- tests expose a current semantic-system inconsistency not caused by this operation.

## Return packet

Return in the exact carrier with:

- `RESULT sni-semantic-registration-20260828-001` or typed blocker/decision request;
- branch and exact head SHA;
- PR number/URL;
- base SHA used at START;
- exact changed-file list;
- test commands/results;
- hosted-CI state;
- whether `scripts/agentos.py validate` accepts `WS:SINGLE-NAME-INTELLIGENCE-OS`;
- any discovered collision or newer ownership ruling;
- explicit statement that SNI-1A code was not started.

After a nonterminal return, re-arm the continuation path. After Sol issues terminal `SOL ACCEPTED / STOP` or `SOL STOP`, stop this operation, disarm the temporary watcher/wait path, and do not infer authority for SNI-1A. SNI-1A requires its own fresh operation key, delivery, pickup, watcher, START and review cycle.
