---
key: CODEX-NATIVE-ROLE-LOADABILITY-AND-SCHEMA-GAP
claim: >
  The seven Mastermind native Codex helper definitions at f9e46a72 contain 28
  deny-only MCP entries that lack the transport required by Codex 0.147.0's
  standalone-role deserializer, while that version's exported ConfigToml JSON
  Schema accepts all seven original files and therefore cannot detect this defect.
falsifier: >
  Inspect openai/codex at be6e8eac029b183056b7e4402879f15d2c85f61b:
  codex-rs/core/src/config/agent_roles.rs and codex-rs/config/src/mcp_types.rs.
  A role path that merges parent transports before typed deserialization, or a
  successful native parse of the original transport-less entries on that exact
  version, would contradict the loader finding. Re-run the exact exported schema
  against the original ConfigToml projections; an error on missing transports
  would contradict the separately observed schema limitation.
so_what: >
  Reuse protected Mastermind PR 513 rather than remove deny lists, widen helpers
  into coding workers, raise concurrency, or create another router. The existing
  research-only parent uses its fixed active-book research server, so the four
  old portfolio servers remain explicitly disabled with complete inert transports.
  Source protection and current integration tests do not prove installed native
  role loading or real child permission inheritance. Read actual strict required-
  check policy before interpreting a green but refused merge as a missing CI run.
kind: landmine
verified_at: 2026-09-07
verified_by: >
  Mastermind #513 protected release 87fcea41a0357ff59c615ecced73645364a42567;
  independent APPROVE 5126704695 on unchanged semantic head137a8e49;
  exact integrated bridge module52 passed; hosted run34068695038 passed506 modules;
  comments5563203137,5563382492 and5563403657 record strict policy, acceptance and
  protected parent/tree/nine-blob readback. Native execution remains unproven.
scope:
  - Mastermind/.codex/agents/*.toml
  - Mastermind/brain/codex_bridge.py
  - Mastermind/tests/test_codex_bridge.py
confidence: verified
---

# Native-role loading needs a behavioral boundary, not only schema validation

This is source-level organizational knowledge, not an installed-provider receipt,
release authorization, workstream, scheduler, or Executive lifecycle record.

## Current result: protected source, installed use still unproven

[Mastermind PR #513](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513)
merged at **2026-09-07T00:30:10Z**. Its protected squash release is
`87fcea41a0357ff59c615ecced73645364a42567`, sole parent
`ef02058ba9356808e41937dab054f00043f89c1e`, tree
`4665dd63913a089078cb94a32d974e2f65230d10`.

The actual protected ref equaled that release at00:32:56Z. The complete commit
census contained exactly nine changed files, with every blob equal to the reviewed
semantic candidate. GitHub verified the squash commit's signature. This is
**SOURCE_PROTECTED / BUILT_NOT_PROVEN for installed native use**.

This disposition supersedes the open/unmerged/release-blocked next action in
[the prior record at4726beb8](https://github.com/mastermindx-market-intelligence/macro/blob/4726beb832aef0405d4b68854e7ad3c730903937/agentos/discoveries/DSC-CODEX-NATIVE-ROLE-LOADABILITY-AND-SCHEMA-GAP.md).
That immutable record retains the failed attempts and historical checks. The
original defect, schema finding, read-only limits and native-proof requirements
are not superseded. Macro publication of this discovery is itself a separate
records-review/release process; it must not be confused with the protected
Mastermind implementation.

## Original defect and bounded repair

Original source: `f9e46a72d6102b0e94c897590fc58bac89eb4ea6`. Seven roles:
`default`, `explorer`, `worker`, `deep-reasoner`, `narrative-analyst`, `quant-coder`
and `signal-scout`. Each had deny-only `bot`, `desk`, `china` and `hk` MCP entries.

The upstream standalone role loader constructs its typed configuration before
parent overlays. The custom MCP transport conversion requires a command or URL;
a deny list, or `enabled=false` alone, cannot supply the absent transport.
The repair adds `command="false"` plus real boolean `enabled=false` to those same
28 entries, and hardens the existing parent guard against transport/type/deny-list
and sandbox drift before its launch path. It adds no transport service or policy
store. The disabled command is not invoked by the source tests or this release.

All nine reviewed files retain their exact semantic blobs: seven role profiles,
`brain/codex_bridge.py` and `tests/test_codex_bridge.py`. Models, reasoning effort,
instructions, denied tools, read-only sandbox, fixed active-book research server,
three-thread ceiling and the existing research-parent/separate-submission sequence
remain unchanged. These are portfolio research helpers, not generic write-capable
engineering workers. No trading, sizing, provider, account, Runtime or worker
lifecycle authority was widened.

## Schema green would have missed this defect

Exact upstream source is `openai/codex@be6e8eac029b183056b7e4402879f15d2c85f61b`.
Its exported `codex-rs/core/config.schema.json` was verified as Git blob
`fd463f4af1ed0b92dcde0af68ad539322f760196`,171813bytes.

All seven original and seven repaired ConfigToml projections passed that schema.
Only role-wrapper metadata was omitted; external reference acquisition was
rejected. This **14/14 static result is nondiscriminating**. The exported schema
is weaker than the actual custom Rust transport conversion and does not execute
native role loading. Detailed original evidence is preserved in
[comment5562263619](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513#issuecomment-5562263619).

## Discriminating source and independent evidence

Original artifact tests produced seven failures; original transport/sandbox guard
checks produced nine failures alongside three passing valid-book controls; three
malformed-list cases failed before their typed-list correction. The completed
changed test module passed52 cases. Three in-memory guard removals caused the
expected6/3/3 failures, zero test errors and unchanged source bytes. Missing-package
attempts were environment failures, not behavioral REDs.

Non-author MastermindX1 submitted **APPROVE5126704695** on semantic head
`137a8e490a9bb6e8c7eca225e53a3128971e9160`, tree
`9d33f5dc967f892f4073c41450d7aa16978c1e0c`. The reviewer examined the complete delta,
upstream loader and existing real consumer, and independently ran three positive
and46 negative extracted-guard controls. Those controls are not a second complete
module run or a native parser. Do not sum these evidence populations.

Canonical CHECKPOINT_VERIFIED and REMOTE_COMPLETE_VERIFIED receipts established
then-current local/remote source identity. Remote-complete digest:
`6739eb4d6c262f78926d5d8729a738d0e235f8c1c39cc2e086fb28012cee1914`.
The later explicit source acceptance/STOP and writer release, not the receipt
alone, ended the builder. The independent review child also received explicit STOP.

## Required-check refusal resolved by actual policy and current integration

Two earlier expected-head merges returned405, required `test` expected. One
close/reopen refresh was consumed; both earlier hosted generations passed503 test
modules. Synthetic merge object IDs changed despite identical parents and tree.
Those failures remain real history; they were not proof that another full test
run, permission bypass, or invented status was warranted.

At **2026-09-06T23:55:26Z**, the authorized Mac's existing GitHub CLI principal read
the actual classic required-status-check policy:

```json
{"strict":true,"contexts":["test"],"checks":[{"context":"test","app_id":15368}]}
```

No credential was extracted, changed or persisted and no protection rule changed.
The previously omitted requirement was an up-to-date branch. This provided a
concrete integration requirement; it did not establish every observed connector
projection discrepancy's underlying cause. The current same-carrier ruling is
[comment5563203137](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513#issuecomment-5563203137).

One history-preserving integration was published on the existing branch:
`73dadab1f0f4bb983c9e78703873cc027286c63d`, ordered parents
`[137a8e490a9bb6e8c7eca225e53a3128971e9160,ef02058ba9356808e41937dab054f00043f89c1e]`.
Its complete tree equals `4665dd63913a089078cb94a32d974e2f65230d10`.
Native Git merge-tree and the connected GitHub tree construction agree. Every
owned blob equals the reviewed head; every nonowned blob equals the current base.
This meets an observed platform requirement, not an ancestry-only cosmetic join.
All remote source/ref/merge effects stayed on the existing GitHub connection.

An isolated archive of that exact tree ran the complete bridge module:
**52 passed in2.28s, exit0**, empty stderr, nine source hashes unchanged.
Natural hosted run **34068695038**, job **101581952557**, actually checked out
`f3d1190beeda4a00d74270fb0e01f3bd5a8783df`, parents[current base,integration head],
with the identical tree. Its full repository gate reported
**506 discovered /0 excluded /506 running test modules**, with skips disclosed.
These are modules, not cases. Required test, CodeQL and all three configured
language/workflow analyses completed SUCCESS. Source-only release acceptance
[5563382492](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513#issuecomment-5563382492)
preceded one expected-integration-head squash merge; protected readback followed.

No force push, rebase, empty commit, extra refresh, alternate merge carrier,
protection weakening or direct status write was used. The source-writing worktree
remains clean at its historical semantic head, not falsely called synchronized
with the later remote integration. It is a released workspace, not an active writer.

## Local waiter loss does not erase hosted truth or authorize replay

The finite tool-only CI watcher for34068695038 started00:06:02Z. Its output stopped
at00:18:10Z and its terminal result file was absent. At00:32:56Z, the original PID
was absent and an independent parsed process census found zero exact matching
`gh run watch34068695038` processes, including absolute executable paths.
**Its final exit is unknown.** No replacement, kill or retry was performed.
GitHub's actual terminal checks and complete log independently prove hosted CI.

Release operation `native-role-loadability-source-release-20260906-websol3` received
explicit terminal acceptance/STOP in
[comment5563403657](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513#issuecomment-5563403657).
No delayed waiter output may reopen it. Independent seat/Root/sibling continuations
remain untouched. Exact protected readback receipt SHA256:
`d4b39f7aa96b6ebb56883ef19d2adc6a37bbe87ff1ce2b50951bd8d0276eb884`.

Evidence remains under the existing native directory:
`/Volumes/Mastermind/Mastermind/artifacts/native-role-loadability-20260906-websol3/`.
It is evidence, not a replacement process, effect, retry or lifecycle database.

## Exact next action and no-rebuild boundary

The remaining helper-specific gate is **lawful installed/native proof**, not another
source repair or merge attempt. It must bind the actual binary and configuration,
exercise default and named roles through the intended read-only parent, and observe
real child capability inheritance with zero portfolio mutation. Previously
TOOL_BLOCKED parser/provider/shared-environment probes must not be reproduced
through another tool or delegated worker. A blocked probe is not a missing receipt
to fabricate; native acceptance remains unproven until a permitted proof exists.

A static Mac package census at00:15:31Z identified npm/platform manifests claiming
Codex0.147.0 and hashed the installed binary without executing it. This does not
prove upstream binary authenticity, worker PATH selection, loaded roles or child
permissions. A public release-asset comparison failed before download; no binary
comparison or successful native probe is claimed.

Preserve the existing Personal first-read operation and original carrier
`C0BSBM78V1N/1788719305.919709`, its controller/Terra and current repair grants.
Preserve Steward, Runtime/Cockpit, Connected Office, provider harness, exact
continuation and browser owners. No duplicate worker, discovery, workstream,
router, native helper registry or release queue is created by this record.

The overall program remains PARTIAL: real authenticated reads, useful parent/child
observation, attributable results, exact supervisor continuation, independent
review/repair and explicit terminal closure must still be demonstrated end-to-end.
