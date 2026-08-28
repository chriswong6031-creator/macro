# M1 Macro Consumer Hardening — Architecture Design

Date: 2026-08-26
Status: DESIGN ACCEPTED — Chairman approval is recorded on canonical carrier #6432; no runtime mutation is authorized by this document
Chairman intent: harden the B1-A continuation so M1 private-repository migration, runtime recovery, proof, and future maintenance proceed smoothly without repeated archaeology or accidental scope collision.
Canonical execution carrier: GitHub issue #6432 (`Macro private-repository cutover — M1 legacy consumer retirement and authenticated fetch`)
Linear projection: MAS-137; aggregate readiness projection: MAS-140
Protected Sol Skillpack used for the original design: `mastermindx-market-intelligence/Mastermind@ebff50d65b09a2753b6cb9bea3cb2548522932e4` (`mastermind.sol_skillpack.v1`, v1.0.0, bootstrap major 1 compatible)
Macro design base: `7d7734d073b0a63cd01fad31dcfbd5ded57abb56`
Release reconciliation: on 2026-08-27, Sol atomically reloaded the current protected Skillpack at `mastermindx-market-intelligence/Mastermind@af43f356f4f7f34cb3514d1d1099b50444af8487`, reconciled this carrier onto Macro `main` at `463bb3b4b708a4748fc65a04250366ca94205186`, and found no material conflict with the governing B1 decisions or current runner/CI ownership boundaries.

## 1. Outcome

The primary operational job is not merely to change a few Git remotes. It is to make every load-bearing M1 dependency on the canonical Macro repository **obvious, correctly owned, least-privilege authenticated, fail-closed, and production-provable** before the repository becomes private.

The end state is:

1. a fresh operator can run one bounded, read-only census on the M1 and immediately see every loaded/recent Macro-dependent service, the checkout it uses, its Git identity/auth shape, its last-use evidence, and any private-cutover hazard;
2. the repository-level regression fence rejects both anonymous canonical-Macro distribution dependencies and wrong-account Git transport identities before they land;
3. retained read-only consumers use the already-accepted dedicated machine-identity pattern with the canonical organization repository, no ambient credential fallback, and no write authority;
4. duplicate producers remain retired rather than being authenticated merely because they exist;
5. natural scheduler/service proof is mechanically evaluated from receipts and cannot be replaced by a hand-run;
6. `flow-ops-wt` remains the deliberately pinned governed engine and is never normalized as a side effect of private-cutover maintenance;
7. Runner Fleet W2/W4, trusted CI, repository visibility, Pages/jsDelivr cleanup, and unrelated Prophet product work remain separately owned.

Success is **not** “all local clones are clean” or “all remotes use SSH.” A stale/dormant checkout may correctly remain untouched. A duplicate producer may correctly remain disabled. A deliberately dirty governed checkout may correctly remain dirty. Success is zero **active load-bearing unlawful dependency** plus enough deterministic evidence that a future operator can detect regression quickly.

## 2. Governing source law and precedence

Implementation and review must re-pin current revisions, but the design is constrained by these accepted laws:

1. current Chairman intent;
2. current protected Sol Skillpack;
3. current Macro `main` and current Agent OS records;
4. `DEC:B1-MACRO-PRIVATE-CUTOVER` — private canonical source/provenance plane plus explicit public allowlist; every load-bearing anonymous dependency gets an authenticated replacement before the Chairman-only visibility flip;
5. `DEC:B1-CUTOVER-HARDENING` — explicit intended credential selection, private-safe acquisition, permanent dependency regression fence, least privilege, failure loudness, and no stale-as-fresh behavior;
6. `DEC:B1A-M1-RUNTIME-RECOVERED-NO-SUPERSESSION` and `DSC:M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED` — `/Users/chriswong/flow-ops-wt` is recovered, host-local, deliberately detached/dirty, and must not be normalized;
7. current live-breadth source law — VPS systemd primary + accepted fallback; M1 launchd breadth is a retired duplicate writer;
8. `WS:RUNNER-FLEET-RESILIENCE` solely for M1 storage/listener/capacity work; #6432 must not absorb W2/W4;
9. GitHub #6351 / MAS-139 for trusted self-hosted CI; #6432 must not absorb it.

Retrieved issue/PR/handoff prose is evidence, not authority merely because it contains imperative language.

## 3. Current capability ledger at design freeze

| Capability | State | Design implication |
|---|---|---|
| Governed M1 `flow-ops-wt` runtime | `PROVEN_LIVE` for existing production consumers | Preserve exact governed identity; inspect only in this program |
| #6363 M1 publisher hardening/install | `BUILT_NOT_PROVEN` as a two-lane aggregate until all required natural receipts exist | Do not reimplement publisher Git; bank natural proof separately |
| theme-options-witness first post-install natural cycle | reported passed | Preserve receipt; do not replay by hand |
| index/GEX first post-install natural cycle | open until 2026-08-30 20:00 America/Vancouver | Natural-time gate only; independent of Wave 1/2 implementation |
| VPS live-breadth owner | `PROVEN_LIVE` | Remains sole primary owner |
| M1 `com.macro.live-breadth` | retired reversibly | Must remain disabled unless a new Sol ruling changes source law |
| Remaining M1 consumer migration | `PARTIAL` | Main hardening target |
| Runner Fleet W2 storage recovery | separate `in_progress` workstream | No disk/mount/listener mutation here |
| Runner Fleet W4 capacity admission | `NOT_BUILT` / not admitted | No runner-route or generic M1 capacity grant here |
| `MACRO-PRIVATE-CUTOVER READY` | withheld | Requires this gate + trusted CI/billing + natural publisher proof + fresh final census |

## 4. Problems this design closes

### 4.1 Repository fence ≠ host census

The existing `scripts/check_macro_anon_dependency.py` is intentionally a repository source/config fence. It catches canonical-Macro anonymous distribution forms and several assembled same-file constructions. It cannot prove what a Mac has loaded from host-local `.git/config`, LaunchAgents, stale deploy trees, or old remotes. The B1-A incident arose precisely in that gap.

### 4.2 “Authenticated” can still mean the wrong repository identity

The current fence is optimized for anonymous/public distribution hazards. An old account transport such as:

```text
git@github.com:chriswong6031-creator/macro.git
ssh://git@github.com/chriswong6031-creator/macro.git
```

can be authenticated while still violating the canonical organization identity and private-cutover law. The M1 estate has contained this class of remote. The permanent fence must distinguish lawful human GitHub citations from executable/config Git transport targets while rejecting the old owner.

### 4.3 Different consumer types need different authority

The two publisher lanes legitimately need a write-capable deploy identity and already use `scripts/macro_machine_git.py`. Ordinary retained consumer/update trees do not. Giving them the publisher key merely to standardize tooling would violate least privilege.

The design therefore **does not create a new credential store and does not reuse the publisher write key**. Read-only consumers use the accepted read-only deploy-key/config pattern already proven in B1 Day-6: canonical SSH remote, explicit key selection, no agent fallback, no credential helper/URL rewrite, and push denial.

### 4.4 Natural-time proof is currently too interpretive

The design must make it hard for a future session to accidentally call a manual run “production proof.” A verifier should evaluate evidence from an already-occurring scheduled execution; it must not itself trigger the service.

### 4.5 Host tree drift creates ownership ambiguity

`hub-ops-wt` was recently refreshed only for a four-file import closure by another production program, while the tree remained otherwise stale/dirty and a separate repoint task was named. Any new migration must reconcile that carrier/current state first. Absence of an open PR is not proof that a host-side operation is unowned.

## 5. Architecture overview

This design adds **observation and deterministic validation**, not another lifecycle/control plane.

```text
M1 launchd + bounded local checkout roots
        |
        v
read-only consumer inspector
        |
        +--> structured ephemeral census JSON
        +--> concise operator table
        |
        v
Sol/source-law classification
  KEEP_AUTHENTICATE | RETIRE_DUPLICATE | DORMANT_NO_ACTION | UNKNOWN_STOP
        |
        +--> retained consumers: existing read-only machine Git pattern
        +--> duplicates: reversible retirement only
        +--> dormant: no mutation
        +--> unknown: stop for Sol
        |
        v
real scheduled/service execution
        |
        v
read-only natural/service receipt verifier
        |
        v
Agent OS + #6432 evidence / Linear projection
```

The inspector JSON is a receipt/artifact, **not a durable registry**. Agent OS remains organizational truth; GitHub remains implementation/evidence truth; launchd/Git/filesystem remain runtime evidence. No daemon, database, cursor, inventory service, or scheduler is added.

## 6. Component A — M1 Macro consumer inspector

### 6.1 Mission

Provide a deterministic, report-only view of the M1 Macro dependency estate so a fresh operator does not rediscover it by ad-hoc shell archaeology.

Expected implementation shape: one focused script plus tests, likely under `scripts/` and `tests/`. Final filenames are an implementation detail; the contract below is frozen.

### 6.2 Invocation boundary

The inspector runs **locally on the target host** or through an operator-controlled remote shell that executes the same local script. The script itself does not contain SSH/Tailscale credentials and does not become a remote-execution service.

It accepts bounded explicit roots and/or discovers roots only from loaded/recent service definitions. It must not recursively crawl the whole filesystem.

### 6.3 Evidence inputs

The inspector may read:

- launchd loaded/enabled state and plist metadata for the current user/system domains that the operator explicitly selects;
- plist program arguments, WorkingDirectory and environment-variable **names**;
- process command lines only as needed to associate a live process with a service/checkout;
- local repository `HEAD`, porcelain/dirty count, worktree type, remote URLs, selected local/worktree Git config relevant to authentication, and `FETCH_HEAD` metadata;
- bounded recent stdout/stderr/log metadata and last-execution evidence where the service already records it;
- filesystem ownership/mode for referenced machine-key paths, but never private-key bytes;
- exact service entrypoint paths and artifacts/products read/written when statically observable from the service definition or known runbook inputs.

### 6.4 Explicitly forbidden reads/outputs

The inspector must never print or persist:

- private key bytes;
- token values;
- `.env` contents;
- arbitrary environment values;
- credential helper output;
- secret-bearing command stderr;
- full unrestricted process environments.

Environment evidence is names/presence only. Key evidence is path class + existence + owner/mode/link-count shape only.

### 6.5 Output contract

The primary machine-readable result should be versioned, for example:

```json
{
  "schema": "macro.m1_consumer_census.v1",
  "observed_at": "<offset-aware timestamp>",
  "host": {"hostname": "<name>", "hardware": "<model if available>"},
  "services": [
    {
      "service_id": "com.example.service",
      "loaded": true,
      "enabled": true,
      "active": false,
      "entrypoint": "/absolute/path/to/script",
      "working_directory": "/absolute/path",
      "checkout": {
        "path": "/absolute/path",
        "head": "<sha-or-null>",
        "detached": false,
        "dirty_tracked_count": 0,
        "dirty_untracked_count": 0,
        "remote_urls": ["<redacted-safe URL identity>"],
        "fetch_head_mtime": "<timestamp-or-null>"
      },
      "git_identity": {
        "canonical_repo": true,
        "wrong_owner": false,
        "anonymous_transport": false,
        "explicit_machine_identity": true,
        "ambient_fallback_possible": false,
        "write_capability_observed": false
      },
      "last_execution": "<bounded evidence-or-null>",
      "hazards": []
    }
  ]
}
```

The operator table is derived from the same in-memory model and must not become a second contract.

### 6.6 What the inspector does **not** decide

It may deterministically label evidence such as `wrong_owner=true`, `loaded=false`, or `explicit_machine_identity=false`.

It must **not** autonomously decide organizational classifications such as `KEEP_AUTHENTICATE` or `RETIRE_DUPLICATE`, because those require current source law and architecture. Classification remains a Sol/operator act recorded in #6432/Agent OS.

### 6.7 Fail behavior

- unreadable service definition → report `inspection_error`, do not omit it silently;
- ambiguous checkout mapping → report ambiguity;
- malformed Git config → report hazard;
- inaccessible log → report unknown evidence, not “never ran”;
- unknown active Macro consumer → `UNKNOWN_STOP` at the operator classification layer;
- one bad entry must not erase the rest of the census, but the command exits nonzero if any inspection error/hazard makes the census incomplete for cutover purposes.

## 7. Component B — stronger canonical-Macro dependency fence

### 7.1 Preserve existing behavior

Do not weaken the current detection of:

- `raw.githubusercontent.com/<canonical-or-old-owner>/macro/...`;
- GitHub Pages mirror;
- jsDelivr `gh` mirror;
- anonymous GitHub API byte reads;
- bare anonymous HTTPS clone/fetch targets;
- GitHub byte-serving archive/raw/release/raw-query paths;
- current assembled/same-file Python cases;
- precise third-party/citation allowances.

### 7.2 Add wrong-account transport coverage

Executable/config surfaces must also reject canonical-Macro acquisition/update targets using the old personal owner through at least:

- SCP-style SSH: `git@github.com:chriswong6031-creator/macro.git`;
- `ssh://git@github.com/chriswong6031-creator/macro.git` and equivalent trailing-slash form;
- old-owner HTTPS repo roots already covered by the anonymous rule;
- command/config constructions that set a Git remote to the old owner where the literal identity is statically visible.

The canonical organization SSH form remains allowed where the call site is expected to be authenticated. Human links to old PR/commit history may remain lawful citations; the guard must remain transport/data-dependency-specific rather than banning the old owner string globally.

### 7.3 No false “security by grep” claim

The fence remains a deterministic repository regression guard, not a proof of all runtime dataflow. The host inspector is the complementary runtime-estate evidence source. Documentation/tests must say this explicitly.

## 8. Component C — retained read-only consumer Git contract

### 8.1 No new credential plane

Do not create a credential broker, key registry, token service, secrets database, or wrapper that competes with accepted Git/SSH behavior.

For an existing retained checkout such as `hub-ops-wt`, the preferred migration is to configure the checkout/service to use the existing accepted dedicated **read-only** deploy-key pattern directly.

### 8.2 Required properties

A `KEEP_AUTHENTICATE` consumer passes only if all applicable properties are proven:

- literal canonical remote identity: `git@github.com:mastermindx-market-intelligence/macro.git`;
- dedicated repo-scoped read-only deploy key, not the publisher write key;
- key owner/mode/path shape accepted by existing source law;
- `BatchMode=yes`;
- `IdentitiesOnly=yes`;
- no SSH-agent identity fallback (`IdentityAgent=none` or equivalent accepted isolation);
- no credential helper or `url.*.insteadOf` rewrite that can redirect the canonical literal;
- no secret embedded in remote URL;
- missing/bad credential fails loudly;
- fetch/update failure cannot advance freshness or make stale data appear fresh;
- dry-run or equivalent write attempt proves push denied;
- existing checkout/product semantics remain unchanged except transport/auth identity.

### 8.3 Existing write publisher boundary

`scripts/macro_machine_git.py` remains the write-capable publisher seam for the two existing publisher lanes. It must not become the generic consumer update mechanism merely for convenience.

If implementation discovers genuinely duplicated low-level SSH validation code that is unsafe to maintain separately, stop and return an extraction proposal to Sol rather than silently widening this wave into a Git-auth framework refactor.

### 8.4 `flow-ops-wt` special rule

`/Users/chriswong/flow-ops-wt` is not a disposable checkout and is not a migration target in this program. Inspector evidence may read its exact HEAD/status identity. No reset, clean, pull, rebase, checkout, sparse migration, remote normalization, or partial-file refresh is permitted.

## 9. Component D — natural/service receipt verifier

### 9.1 Mission

Deterministically evaluate an already-occurring scheduled/service execution against the proof contract without triggering it.

### 9.2 Non-triggering law

The verifier must not call `launchctl kickstart`, run the launcher, invoke the production script, or alter scheduler state. Its inputs are pre-existing logs/files/service metadata plus explicit expected identities supplied by the operator/current accepted handoff.

### 9.3 Expected arguments

The verifier should take explicit values rather than embedding live company state in code, including where applicable:

- service/lane identity;
- expected natural execution window and timezone/offset;
- expected hardened launcher path;
- expected checkout path;
- expected canonical remote identity;
- expected governed engine HEAD/status identity when the lane depends on `flow-ops-wt`;
- log/output paths to inspect.

### 9.4 Receipt contract

A versioned result, for example `macro.publisher_natural_receipt.v1`, should state:

- observed service identity;
- natural-window match and source timestamp evidence;
- launcher/checkout identity match;
- canonical remote/auth identity match where observable;
- exit/result evidence;
- wrong-account redirect/fallback evidence absent/present/unknown;
- governed engine identity preserved/not preserved/unknown;
- product/artifact evidence expected from that lane;
- `pass`, `fail`, or `incomplete` plus machine-readable reasons.

`incomplete` is not promoted to pass.

### 9.5 Initial use

The open index/GEX natural proof on 2026-08-30 is the first high-value consumer of this verifier if the implementation lands beforehand. If it does not, the existing manual evidence contract remains controlling; the proof must not be delayed or synthetically replayed merely to wait for new tooling.

The index/GEX calendar receipt is an **independent private-readiness gate**, not a prerequisite to implement or close Wave 1/2 hardening. The verifier may bank it when available; absence of the calendar event before Wave 1/2 completion does not hold those waves open.

## 10. Classification and migration workflow

After a complete read-only census, every discovered current/recent consumer is classified exactly once:

### `KEEP_AUTHENTICATE`

Load-bearing and architecturally lawful. Migrate only its Git/auth transport boundary, preserving product/data semantics.

### `RETIRE_DUPLICATE`

Active but architecturally superseded. Reversibly disable/unload only after proving the canonical owner healthy. Do not “fix” its Git authentication.

### `DORMANT_NO_ACTION`

Not load-bearing and not currently executing. Record it; do not churn it merely for cleanliness.

### `UNKNOWN_STOP`

Evidence or source law is insufficient/conflicting. Stop before mutation and return to Sol.

The classification is recorded in the existing #6432 carrier and, when material/cross-session, Agent OS. It is not written into a new local inventory database.

## 11. `hub-ops-wt` collision rule

Before any authentication change to `hub-ops-wt`:

1. reconcile the named remote-repoint operation/task from the latest AD-1T1 handoff against current operator/host state;
2. prove whether another session/carrier is currently modifying or has already modified the same remote/auth seam;
3. capture current HEAD, dirty state, four-file closure identity, loaded consumers, remote/auth config and last-use evidence;
4. if effect is ambiguous, classify `EFFECT_UNKNOWN` and reconcile on the same carrier; never blind-retry through #6432;
5. do not perform another partial-file refresh as part of authentication migration;
6. if import/runtime bytes need broader reconciliation, stop and commission that separately.

This prevents a transport hardening change from turning into an accidental deployment-tree normalization.

## 12. Rollback law

Rollback must not reintroduce a forbidden dependency.

For an authenticated retained consumer, rollback may restore:

- prior service enablement state;
- prior known-good runtime bytes/config unrelated to forbidden Git identity;
- prior scheduler state;

but must **not** restore an old-account/anonymous Macro remote after that path has been ruled unlawful.

If safe rollback requires restoring the forbidden transport, stop for Sol; that indicates the migration was not independently reversible and should not have been applied under this wave.

For retired duplicate producers, rollback to re-enable is allowed only as the explicitly documented emergency reversal under the conditions recorded at retirement; it is not a normal private-cutover rollback.

## 13. Failure states and required response

| Failure | Response |
|---|---|
| active consumer cannot be mapped to a checkout/caller | `UNKNOWN_STOP` |
| another carrier owns same host remote/auth mutation | stop; reconcile carrier; no failover |
| machine key missing/ambiguous | no mutation; fail closed |
| auth works only via agent/global config/helper | reject |
| wrong-account transport remains active | cutover gate remains open |
| service update succeeds but product/freshness regresses | rollback safe non-forbidden change or stop for Sol |
| `flow-ops-wt` identity mutation required | reject design assumption; return to Sol |
| duplicate producer canonical owner unhealthy | do not retire; return to Sol |
| natural receipt source is missing/overwritten | `incomplete`; never hand-run to manufacture proof |
| inspector cannot establish complete active/recent census | cutover gate remains open |
| implementation requires new credential/control/inventory plane | stop; architecture review |
| Runner Fleet disk/listener problem encountered | route to W2/W4 owner; do not widen #6432 |

## 14. Implementation decomposition

The architecture is implemented as three independently reviewable vertical waves. Use semantic names; do not introduce another ambiguous `B1-A/B1-B` shorthand.

### Wave 1 — M1 Consumer Visibility

Observable capability: a fresh operator can produce a complete bounded M1 Macro consumer census and CI rejects old-owner transport regressions.

Expected scope:

- report-only consumer inspector + deterministic unit/fixture tests;
- extend `check_macro_anon_dependency.py` and its tests for wrong-account Git transport;
- documentation of inspector output/failure contract;
- no M1 mutation;
- no credential provisioning.

Acceptance:

- synthetic non-vacuity tests for every newly banned transport shape;
- precision tests for lawful citations/canonical SSH;
- inspector fixtures cover loaded, disabled, dormant, wrong-owner, anonymous, explicit-auth, malformed/ambiguous and deliberately dirty governed checkout states;
- secret-redaction tests;
- real M1 read-only census run captured in #6432;
- zero change to service/repository/runtime state during census.

Stop after returning the census/classification packet. Wave 1 does not automatically mutate Wave 2 targets.

### Wave 2 — M1 Canonical Git Migration

Observable capability: every in-scope `KEEP_AUTHENTICATE` current M1 consumer uses canonical-org dedicated read-only machine Git; every duplicate is retired or already retired; dormant/unknown items are handled according to classification.

Precondition: Wave 1 PASS + collision reconciliation for each target.

Expected first target: `hub-ops-wt`, only if its separate repoint ownership is resolved and current source law still classifies its consumers `KEEP_AUTHENTICATE`.

Acceptance per retained consumer:

- pre-state captured;
- canonical org remote exact;
- read-only key identity proven;
- no ambient fallback;
- wrong-account/anonymous negative controls;
- push denied;
- real service/scheduler execution succeeds;
- product/data output unchanged at promised semantics;
- safe rollback documented;
- no `flow-ops-wt` mutation;
- post-state inspector clean for that consumer.

Stop if any consumer becomes `UNKNOWN_STOP`; do not absorb its diagnosis into the migration.

### Wave 3 — M1 Consumer Production Proof + Closeout

Observable capability: a fresh read-only census shows zero active unlawful Macro dependencies, required natural/service receipts for **consumer changes made by this program** are banked, and durable/projection state accurately reflects the remaining private-cutover gates.

Acceptance:

- complete post-migration M1 census;
- zero active wrong-owner/anonymous load-bearing dependencies;
- `com.macro.live-breadth` remains disabled and VPS owner remains healthy;
- every retained modified service has real-path proof;
- applicable negative auth/fallback tests pass;
- natural/service verifier receipts for modified consumers are banked where applicable without synthetic dispatch;
- the independent index/GEX calendar receipt is reconciled if it has naturally occurred by closeout, but its calendar timing does not block Wave 1/2 completion;
- Agent OS decision/discovery/handoff/workstream updates pass validation;
- MAS-137 projection reconciled to canonical state;
- MAS-140 still withholds overall READY until independent trusted-CI/billing and natural-time gates are satisfied;
- no private visibility flip.

## 15. Testing strategy

### Deterministic unit tests

- parsing launchd/service fixture shapes;
- mapping service → entrypoint → checkout;
- Git remote normalization/classification;
- canonical organization vs old owner;
- HTTPS anonymous vs SSH explicit identity;
- malformed/multiple remotes;
- detached dirty governed checkout reporting without treating it as failure by itself;
- secret-value redaction;
- wrong-account fence non-vacuity and precision;
- receipt verifier time-window/timezone behavior;
- receipt verifier `pass/fail/incomplete` reasons.

### Integration tests

Use temporary local Git repositories and synthetic plists/logs. Do not require production secrets. Prove that canonical read-only shapes are recognized and old-owner/anonymous shapes are rejected.

### Real host proof

Read-only inspector proof runs on M1 before migration and after migration. Actual Git/auth changes require the existing #6432 operator flow and pre/post host evidence. Production service proof must come from the real service/scheduler path.

## 16. Observability and learning

This hardening is successful if it reduces repeated archaeology and catches drift before the private flip. Record at least:

- number of discovered current/recent Macro-dependent services;
- number classified per category;
- count of active wrong-owner/anonymous dependencies before/after;
- inspector unknown/error count;
- time from cold start to complete census;
- any regression-fence hits in later PRs;
- natural/service receipt pass/fail/incomplete reasons.

These metrics can live in normal receipts/PR evidence. Do not build a telemetry service or new database for them.

## 17. Explicit non-goals

- no repository PUBLIC→PRIVATE visibility mutation;
- no Pages disable or jsDelivr purge in these waves;
- no trusted-CI implementation (#6351 owns it);
- no Runner Fleet W2 storage move/delete/mount/listener action;
- no W4 M1 capacity admission or generic `macstudio` label;
- no `flow-ops-wt` reset/clean/pull/rebase/remote normalization/partial refresh;
- no new scheduler, queue, registry, lifecycle database, credential broker, watchdog or daemon;
- no blanket cleanup of every stale checkout;
- no publisher-write-key reuse for read-only consumers;
- no broad Git-auth framework refactor unless a separate architecture review rules it necessary;
- no MAS-79/MAS-80/MAS-81 Prophet public-object work;
- no history rewrite.

## 18. Architecture invariants

These must remain true through all implementation waves:

1. **one canonical repository identity:** `mastermindx-market-intelligence/macro`;
2. **one logical host mutation / one carrier until reconciled;**
3. **observation is not authority:** inspector evidence cannot retire a producer by itself;
4. **least privilege:** read-only consumers never inherit publisher write authority;
5. **no silent fallback:** missing auth is a visible failure, never anonymous/public fallback;
6. **stale cannot look fresh:** failed refresh cannot advance freshness state;
7. **governed pin preservation:** `flow-ops-wt` remains intentionally detached/dirty unless a future explicit Sol ruling supersedes it;
8. **duplicate writers stay retired:** private-readiness work cannot recreate a third breadth writer;
9. **natural means natural:** proof verifiers observe, never dispatch;
10. **separate workstreams stay separate:** consumer hardening cannot become runner/storage/CI/private-visibility work;
11. **no new truth store:** census/receipt JSON is ephemeral evidence, not canonical organizational state;
12. **green tests are not production proof:** real service/scheduler evidence is still required.

## 19. Design alternatives rejected

### “Just repoint the remaining remotes”

Rejected as insufficient. It closes today’s symptoms but preserves the host-observability gap that produced the incident.

### “Authenticate every stale checkout”

Rejected. Dormant tooling is not automatically load-bearing; touching it adds risk with no capability gain.

### “Use the publisher machine-Git wrapper everywhere”

Rejected. It carries write authority by design and is not appropriate for ordinary consumers.

### “Build a durable M1 service inventory/agent”

Rejected. Agent OS/GitHub/runtime already own truth. A new registry/daemon would duplicate control state.

### “Fold disk recovery and M1 runner return into this program”

Rejected. W2/W4 have their own accepted source law, thresholds and admission sequence.

## 20. Definition of done for this hardening program

This design program is complete only when:

- Wave 1 inspection/fence capability is merged and real-host proven;
- every current/recent M1 Macro dependency is classified;
- every active retained consumer is canonical-org, least-privilege authenticated and real-path proven;
- every active duplicate is retired under source law;
- dormant items are explicitly recorded without unnecessary churn;
- unknowns are resolved or continue to hold the cutover gate;
- post-migration census reports zero active unlawful dependencies;
- every natural/service receipt required by **consumer mutations in this program** is banked; the independent index/GEX calendar receipt remains a MAS-140/private-readiness gate and does not block Wave 1/2 completion;
- durable Agent OS state and Linear projections match canonical evidence;
- overall `MACRO-PRIVATE-CUTOVER READY` remains withheld until its independent gates truly close.

The Chairman-only visibility flip is outside this design’s completion boundary.

## 21. Immediate continuation after design approval

After this design PR is reviewed and accepted, Sol should create a detailed implementation plan and commission **Wave 1 — M1 Consumer Visibility** first. No Wave 2 M1 mutation begins until Wave 1 returns a complete read-only census/classification packet and the `hub-ops-wt` remote-repoint ownership collision is reconciled.
