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
  Reuse Mastermind PR 513 rather than remove deny lists, widen helpers into coding
  workers, raise concurrency, or create another router. The existing research-only
  parent uses its fixed active-book research server, so the four old portfolio
  servers can remain explicitly disabled with complete inert transports. Preserve
  the source/native distinction: unit tests and exported-schema validation do not
  prove installed role loading or real native-child permission inheritance.
kind: landmine
verified_at: 2026-09-06
verified_by: >
  Mastermind PR 513 head 137a8e490a9bb6e8c7eca225e53a3128971e9160;
  full changed module 52 passed; meaningful original REDs and three guard mutations;
  independent APPROVE 5126704695; refreshed hosted run 34062500773 passed503 modules;
  comments 5562263619 and5562600431 preserve the schema gap and unresolved release.
scope:
  - Mastermind/.codex/agents/*.toml
  - Mastermind/brain/codex_bridge.py
  - Mastermind/tests/test_codex_bridge.py
confidence: verified
---

# Native-role loading needs a behavioral boundary, not only schema validation

This discovery is source-level knowledge. It is not installed-provider evidence,
a release authorization, a new workstream, or an Executive lifecycle record.

## Exact evidence and repair

The original source is Mastermind protected
`f9e46a72d6102b0e94c897590fc58bac89eb4ea6`. The seven roles are `default`,
`explorer`, `worker`, `deep-reasoner`, `narrative-analyst`, `quant-coder`, and
`signal-scout`. Each had deny-only `bot`, `desk`, `china`, and `hk` MCP entries.

The implementation is
[Mastermind PR #513](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513),
head `137a8e490a9bb6e8c7eca225e53a3128971e9160`, tree
`9d33f5dc967f892f4073c41450d7aa16978c1e0c`, on
`codex/native-role-loadability-20260906-websol3`. Its nine-file delta adds complete
disabled descriptors to those entries and hardens the existing delegation guard.
It creates no new transport, route, provider, service, credential owner or store.

Parsed before/after comparisons preserve all other role values, including model,
effort, instructions, sandbox, deny lists and the research descriptor. The normal
three-thread ceiling and parent research/sealed-submission sequence remain unchanged.
These are read-only portfolio research helpers, not generic write-capable builders.

Actual native-host source tests produced seven original artifact failures, nine
original transport/sandbox-guard failures with three passing book controls, and
three malformed-list failures before their respective repairs. The final complete
bridge test module passed 52 cases. Three in-memory guard removals produced the
expected 6/3/3 failures, zero test errors and no source-byte change. Initial missing
packages were environment failures, not behavioral REDs. No model/provider turn
or native child was invoked by these tests.

The unchanged Source Continuity verifier returned `CHECKPOINT_VERIFIED` at
`2026-09-06T21:17:45Z`, digest
`510c08b1c6e2ca593bef8bb438c2b12aaf040c6b6b276972e1d7ba997ab55ca9`.
Local and remote head/tree matched, all dirt/unpushed counts were zero, and the PR
collision result was `DISJOINT`. It explicitly granted no merge, receiver transfer
or writer release. The then-current base was `c5fe346f`, whose eight #502 browser
census paths were disjoint; current-base hosted checks remain separate evidence.

## Why exported-schema green is insufficient

Upstream `openai/codex@be6e8eac029b183056b7e4402879f15d2c85f61b` exports
`codex-rs/core/config.schema.json`, verified Git blob
`fd463f4af1ed0b92dcde0af68ad539322f760196` (171,813 bytes).
All seven original and seven repaired ConfigToml projections passed that schema.
Only the role-wrapper metadata was removed from the projection, and all references
were checked as internal before evaluation. This result does not execute the Rust
loader: its custom transport condition is stronger than the exported schema.

Detailed receipts are preserved in
[the implementation checkpoint](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513#issuecomment-5562263619).
The native evidence directory is
`/Volumes/Mastermind/Mastermind/artifacts/native-role-loadability-20260906-websol3/`.
It contains test logs, mutation JUnit, exact-source manifests and the original
failed environment/auth-input attempts. It is evidence, not another state plane.

## Review accepted; source release still blocked

This section supersedes the earlier Draft/review-pending next action preserved at
Macro commit `59df878fd05a284f2834f43cfb1c6b8fdc065393`, without changing the source
finding or native-proof boundary.

Independent reviewer MastermindX1 submitted APPROVE `5126704695` at21:43:33Z on
exact head137a. The reviewer read the complete source and consumer, verified role
preservation, and independently ran three positive and46negative extracted-guard
controls. Those supporting controls are not a second full-module or native-parser
run. The review child was explicitly accepted/STOPped; no watcher was created.

At21:50:08Z, the unchanged canonical verifier returned `REMOTE_COMPLETE_VERIFIED`,
digest `6739eb4d6c262f78926d5d8729a738d0e235f8c1c39cc2e086fb28012cee1914`.
Local/remote head137a and tree9d33 matched, dirt/untracked/unpushed counts were zero,
current base wasc5, and collisions wereDISJOINT. Comment5562429934 then explicitly
accepted and STOPped the direct source-authoring child and declared
`BRANCH_WRITER_RELEASED`. The receipt itself granted no such authority.

A separate maintenance operation,
`native-role-loadability-source-release-20260906-websol3`, marked the PR Ready.
The first expected-head squash merge returned405, required test expected, with
canonical readback proving not merged. One bounded same-PR close/reopen refresh
was admitted and consumed; no source or review changed.

That new natural run34062500773/job101565395500 completed SUCCESS at22:18:27Z.
Its actual checkout was `31331874051c53afd81c9f9a5acfb3a393b0a191`, parents
`[c5fe346fc6ffe865232454c07fc9aefec46951fe,137a8e490a9bb6e8c7eca225e53a3128971e9160]`,
and integrated tree `4a8bc7357c01a218be0c82f7bfecca2171e0672d`. The full log reports
503 discovered/0excluded/503running test modules, with skipped cases disclosed.
Fresh source checks retained new test success plus CodeQL and three analyses green.

The subsequent expected-head merge nevertheless returned the same405. Immediate
PR readback again showed OPEN/READY/UNMERGED. Its synthetic merge ref moved to
`fabba191fabf0c724742ebf4bc9e31819e85bb96`, created22:22:30Z, with the same exact
ordered parents and integrated tree. This is an observed repeated required-check
association gap; its full underlying cause is not established. A same-tree object
must not be falsely described as the commit the runner actually executed.

The explicit HOLD and exact identities are recorded in
[comment5562600431](https://github.com/mastermindx-market-intelligence/Mastermind/pull/513#issuecomment-5562600431).
The one refresh budget is spent: no repeated close/reopen, merge loop, empty commit,
rebase, source join, alternate mutation carrier, admin bypass or direct status write.
The accepted source and review stay terminal and immutable. The maintenance operation
remains blocked, not silently completed. No merge or installation has occurred.

## Exact continuation and non-rebuild boundary

The immediate source-release action is for the existing GitHub release/CI owner to
resolve required-check association for the actual current merge object and tested
checkout, then obtain one fresh bounded release edge. Do not repeat semantic review
or ask Chris to allocate accounts. Native binary parsing and bounded child
capability inheritance remain independently unproven after any eventual source merge.

The existing Personal first-read child remains
`personal-mcp-first-read-e1-source-20260906-sol-001` on Slack
`C0BSBM78V1N/1788719305.919709`, under its existing controller. Its queued-entry repair
at local `8a5c43a17705c7690cf5e5d1244b70f3a9683a76` supersedes the earlier Task1 result
for that concern; its separately started Task2 continues within the same fourteen-file
scope. This discovery neither accepts that implementation nor starts another worker.

Existing Runtime/Cockpit owners retain authenticated-read and plural-observation
integration; #508 is not reimplemented here. The already-created consumer operation
`connected-office-a1-authenticated-steward-consumer-20260906-sol-001` remains on root
`C0BSBM78V1N/1788728906.514699`, last observed waiting on dependencies and capacity,
not ACKed or STARTed. #471/#455 provider harness, #491 return continuity, and
#502/#509 browser census/packaging owners remain separate.

A repaired helper definition is not fleet completion. The original outcome remains
real parent/child observations, attributable results, exact supervisor continuation,
independent review/repair, visible capability and explicit terminal closure.
