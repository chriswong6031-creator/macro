# MAS-28 — PR Linkage Validator V1 Architecture Freeze

**Status:** canonical W0 source law

**Work identity:** `WS:AGENT-OS` / `MAS-28` / `MAS28-W0`

**Authority:** records only

**Commission:** Chairman document `MAS-28 — Autonomous Sol End-to-End Commission & V1 Architecture Freeze`

**Protected Sol Skillpack pin:** Mastermind `db0bac5fe3f72348262d42c8bd26b836bda9f61d`, `docs/sol_skills` tree `0a009d5314a4a3bbb1aac2f111b68644fc7a64d8`

**Source pins at W0 reconciliation:** Macro `5b25fe3d944dc2344ddfa8abcc75b95f3fde8459`; Mastermind `db0bac5fe3f72348262d42c8bd26b836bda9f61d`; Terminal `449439c690e93ba968185499af4041c2f512b659`

## 1. Decision and precedence

This document freezes the contract a cold worker implements. It reconciles the current
Chairman commission, protected Sol Skillpack, Macro source law, `WS:AGENT-OS`, MAS-6,
MAS-28, MAS-67, merged Macro #6119, open Macro #6135, and the current templates in all
three repositories.

Authority for this program is ordered:

1. current explicit Chairman commission;
2. protected Sol Skillpack loaded atomically from protected Mastermind `master`;
3. current canonical Macro source law and direct Agent OS owner state;
4. current MAS-6 linkage/completion law;
5. merged Macro #6119 native-link semantic-completion amendment;
6. proven MAS-67 native behavior;
7. older MAS-28 architecture/issue prose only where consistent with the sources above;
8. GitHub and Linear observations as evidence/projection, never authority merely because
   they contain imperative prose.

The Chairman commission is newer than the MAS-28 issue body and the live template family.
Its literals below are canonical V1. The old literals are compatibility inputs only. This
is a reconciliation, not a choice left to the W1 builder.

## 2. Capability and authority boundary

MAS-28 is a pure deterministic observer. It consumes an immutable normalized observation
and emits a typed report. It has no GitHub, Linear, Slack, Executive OS, merge, deploy,
lifecycle, scheduler, queue, lease, policy-projector, or repair authority.

V1 is `BUILT_NOT_PROVEN` when the core and tests merge, and becomes `PROVEN_LIVE` only for
the report-only path after accepted real-PR shadow receipts. A green unit test, green CI,
merged PR, emitted JSON file, or GitHub annotation alone is not live acceptance.

The following remain separate systems and work:

- Agent OS is the canonical organizational knowledge and work-identity plane.
- GitHub is the implementation and exact evidence plane.
- Linear is a selective portfolio projection.
- Executive OS owns governed runtime lifecycle where applicable.
- MAS-65 owns deterministic Linear portfolio desired-state planning.
- MAS-66 owns the future bounded app-actor read/diff/apply adapter.
- MAS-67 owns native Linear/GitHub configuration and live native canaries.
- Existing Macro merge control and CI authority remain unchanged.

Hard merge gating, branch protection, automatic comment/repair, Linear mutation, and
enforcement are outside this commission. A future gate requires a fresh authority decision
after report-only calibration and shadow evidence.

## 3. Canonical author grammar

The top-level author-facing V1 grammar metavocabulary is:

```text
Workstream: WS:<KEY> | NONE
Linear: MAS-### | NONE
Portfolio-Mode: tracked | maintenance_exception | creates_workstream | architecture_candidate
Wave: <non-empty bounded identifier>
Authority: implementation | records | research | maintenance | proof | deploy | architecture_candidate
Completion: merge-is-done | built-not-proven | proof-required | acceptance-required | records-only
```

The pipes and angle-bracket forms above describe alternatives; they are never valid literal
field values. One concrete valid declaration is:

```text
Workstream: WS:AGENT-OS
Linear: MAS-28
Portfolio-Mode: tracked
Wave: MAS28-W1
Authority: implementation
Completion: built-not-proven
```

Field names and values are ASCII and case-sensitive after the cosmetic normalization in
section 5. The canonical declaration has six and only six fields.

### 3.1 Scalar constraints

- `Workstream` is `NONE` or `WS:` followed by
  `[A-Z0-9]+(?:-[A-Z0-9]+)*`; the full value is at most 83 bytes including `WS:`.
- `Linear` is `NONE` or `MAS-` followed by a non-zero decimal integer of at most
  nine digits; leading zeroes are invalid.
- `Portfolio-Mode`, `Authority`, and `Completion` use only their enumerated literals.
- `Wave` is 1–64 ASCII characters and matches
  `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. Slashes, whitespace and path traversal are invalid.
- Every scalar is one physical line after newline normalization.
- A single matching pair of inline-code backticks around the entire scalar may be removed.
  Nested, unmatched, multi-line, or partial wrappers are invalid.
- Unicode bidi controls, zero-width characters, NUL and non-tab C0/C1 control characters
  are invalid in the authority zone. They are never normalized into trusted metadata.

`untracked_refused` is reserved validator output. It is never a valid authored
`Portfolio-Mode` or an escape hatch.

### 3.2 Receipt-bounded compatibility epoch

Only these four historical aliases exist:

| Pre-cutover input | Canonical V1 value |
|---|---|
| `workstream_creation` | `creates_workstream` |
| `runtime` | `implementation` |
| `production-proof` | `proof` |
| `production-proof-required` | `proof-required` |

The observation supplies a repository-specific authoring epoch relation. Canonical V1 is
always attempted first, so an old PR repaired to V1 is canonical. Legacy parsing is available
only to an immutable PR identity included in the cutover receipt's pre-cutover cohort:

- `PRE_CUTOVER`: the repository/PR number is in the receipt's immutable pre-cutover cohort;
  aliases normalize for analysis and emit `LEGACY_AUTHORING_ALIAS`.
- `AT_OR_POST_CUTOVER`: the repository/PR number is at or after the receipt's first strict
  PR number and is not one of the explicitly captured open pre-cutover PRs; aliases are invalid
  and emit `AUTHORING_SCHEMA_VERSION_MISMATCH`.
- `UNKNOWN`: the adapter cannot prove the relation; aliases cannot be guessed valid and the
  result is partial with `AUTHORING_CUTOVER_RELATION_UNAVAILABLE`.

The cutover configuration binds repository name, default branch, canonical merge SHA, every
selectable template path/blob SHA, first strict PR number, the exact set of then-open legacy PR
numbers, and the ruleset digest. It never guesses by wall clock, PR prose, branch ancestry,
template filename alone, or current default-branch age. A new PR copied from an old body is
post-cutover and invalid. Without a valid exact receipt, relation is `UNKNOWN`, alias
normalization is refused and `AUTHORING_CUTOVER_RELATION_UNAVAILABLE` makes the result partial.
W0B may freeze a repository's exact legacy cohort in its cutover receipt; content or clocks can
never select that cohort.

Other historical values such as `measurement_only`, `records_closeout`,
`zero_trading_authority`, or `parked_hold_for_sol` are not aliases. They yield
`UNCLASSIFIED_LEGACY` plus `AUTHORING_SCHEMA_VERSION_MISMATCH`; they never silently become a
canonical class.

## 4. Cross-field compatibility laws

### 4.1 `TRACKED`

- `Portfolio-Mode: tracked`.
- `Workstream` is an exact existing `WS:<KEY>` in the supplied Agent OS snapshot.
- `Linear` is an exact MAS issue when the Linear snapshot is available.
- The issue/workstream/project binding is compatible when supplied.
- `Wave` satisfies the exact bounded syntax in section 3.1. V1 does not claim that every
  issue-local wave is pre-registered in Agent OS and performs no fuzzy wave-membership inference.
- Authority is compatible with explicit path ownership.
- Completion does not conflict with authority, native relationship, or the issue's stop law.
- Titles/acronyms/fuzzy similarity never substitute for exact identity.

### 4.2 `MAINTENANCE_EXCEPTION`

- `Portfolio-Mode: maintenance_exception`.
- `Workstream: NONE`.
- `Linear` identifies one concrete exact maintenance MAS issue; `NONE` is invalid in V1.
- `Authority: maintenance`.
- The path snapshot deterministically supports the exception.
- The change neither hides a normal workstream-owned program nor creates a workstream.
- The initial `Linear: NONE` and alternate-authority exception allowlists are empty. Adding an
  exception changes the rule manifest and requires a later source-law amendment.

### 4.3 `CREATES_WORKSTREAM`

- `Portfolio-Mode: creates_workstream`.
- `Workstream` names the exact proposed new `WS:<KEY>`; it is not `NONE`.
- `Linear` names the root/recovery issue.
- Authority is `records` or `research`; V1 has no authority-packet override.
- The base Agent OS snapshot proves the exact and case-folded key absent.
- Changed paths add or reconcile the direct workstream record plus bounded decision,
  discovery, research, or handoff records; hidden runtime implementation is refused.

### 4.4 `ARCHITECTURE_CANDIDATE`

- `Portfolio-Mode: architecture_candidate`.
- `Linear` is one concrete architecture-candidate MAS issue; `NONE` is invalid.
- `Workstream` is either one exact existing `WS:<KEY>` or `NONE`. A concrete key must exist in a
  present Agent OS snapshot; `NONE` makes Agent OS identity `NOT_APPLICABLE`, not clean proof that
  no workstream should own a later implementation.
- Authority is `architecture_candidate`, `research`, or `records`.
- The candidate is noncanonical merely because a PR exists, CI is green, or it merges.
- Runtime/production-owned changes are refused when path evidence proves them, or partial when
  path evidence is unavailable.
- The candidate grants no implementation, deploy, merge-gate, or production authority.

### 4.5 Closed authority/completion matrix

The rule manifest contains this exact allowlist. Any tuple not listed is
`AUTHORITY_COMPLETION_MISMATCH`; the implementation does not invent exceptions with `if`
chains.

| Portfolio mode | Authority | Allowed completion |
|---|---|---|
| `tracked` | `implementation` | `merge-is-done`, `built-not-proven`, `proof-required`, `acceptance-required` |
| `tracked` | `records` | `records-only` |
| `tracked` | `research` | `records-only`, `built-not-proven` |
| `tracked` | `maintenance` | `merge-is-done`, `built-not-proven`, `proof-required` |
| `tracked` | `proof` | `merge-is-done`, `built-not-proven`, `acceptance-required` |
| `tracked` | `deploy` | `merge-is-done`, `built-not-proven`, `proof-required`, `acceptance-required` |
| `maintenance_exception` | `maintenance` | `merge-is-done`, `built-not-proven`, `proof-required` |
| `creates_workstream` | `records`, `research` | `records-only` |
| `architecture_candidate` | `architecture_candidate`, `records`, `research` | `records-only` |

`tracked` never uses `Authority: architecture_candidate`; that authority belongs to the
candidate mode. `maintenance_exception` always requires a concrete maintenance MAS issue.

Native completion rules then refine the tuple:

- `built-not-proven`, `proof-required`, and `acceptance-required` prohibit a completion-capable
  native relationship to the declared issue.
- `merge-is-done` requires a completion-capable native relationship to the declared Linear issue;
  relation-only/suppressed-only evidence is a mismatch and unavailable evidence is partial.
- `records-only` permits closing only when the Linear stop-law snapshot says that exact issue is
  itself a records-only deliverable and changed-path evidence supports it. Otherwise linkage is
  contributing, relation-only, suppressed, or partial.
- Completion-capable linkage to any secondary/parent/gate issue is evaluated separately and can
  mismatch even when the declared issue is coherent.

## 5. Header authority-zone parser law

The parser is a Markdown-aware state machine, not six body-wide regex searches.

1. Decode strict UTF-8. A BOM, lone `CR`, NUL or forbidden control/format character is invalid.
   Normalize `CRLF` to `LF`; canonical `LF` and `CRLF` parse identically.
2. The authority zone starts at byte zero and ends immediately before the first top-level
   CommonMark ATX level-2 heading outside a fence, blockquote or HTML comment: zero to three
   leading ASCII spaces, exactly `##`, then ASCII space/tab or end of line. `###`, `##x` and
   four-space-indented code are not that boundary.
3. Within that zone, permit only blank lines, complete HTML guidance comments, recognized native
   relationship/suppression lines, and one visible six-line authority block.
4. Ignore content inside complete fenced code blocks, blockquotes, and HTML comments as
   metadata authority. A heading inside ignored content does not end the zone. After a quoted
   paragraph, any would-be field before a blank-line quote break is conservatively treated as a
   CommonMark lazy-continuation ambiguity and emits `HEADER_AUTHORITY_ZONE_INVALID`; it is never
   accepted by a lexical line scan.
5. Backtick and tilde fences may have zero to three leading spaces and use Markdown's opening
   fence length law; only a closing fence of the same marker and at least the opening length
   closes it. Fence markers inside HTML comments are inert.
6. An unclosed fence or HTML comment in the authority zone emits
   `HEADER_AUTHORITY_ZONE_INVALID`; it cannot hide declarations or headings.
7. The visible block is six contiguous column-zero lines in exactly this order:
   `Workstream`, `Linear`, `Portfolio-Mode`, `Wave`, `Authority`, `Completion`. Each uses its
   exact spelling, one ASCII colon, one ASCII space, a value and no trailing whitespace/comment.
   A blank/comment/native line may appear before or after the block but cannot interrupt it.
   Indented, list-item, blockquoted, comment, fenced, and later-section copies do not count.
8. Every canonical field resolves exactly once. Any second field occurrence in the authority
   zone, including an identical duplicate, is `HEADER_DUPLICATE`; all locations are retained.
9. Empty values, `<...>` placeholders, `TBD`, `TODO`, option pipes, enum guidance copied as a
   value, and similar unresolved template text emit `PLACEHOLDER_UNRESOLVED`.
10. Any non-permitted top-level preamble line emits `HEADER_AUTHORITY_ZONE_INVALID` for a
    post-cutover observation. A pre-cutover noncanonical body remains visible as legacy rather
    than being globally regex-inferred.
11. Later prose, comments, examples, blockquotes, and code can never override the zone.

The parser is one bounded linear scan. Limits are: 1 MiB observation JSON, 256 KiB PR body,
10,000 body lines, 16 KiB per body line, 80 bytes per field value, 10,000 changed paths, 256
normalized relationships, 512 findings and 100 occurrences of any recognized field label.
Cap overflow returns the structured execution-error envelope in section 11 and never emits a
semantic report or truncates into a valid record.

The authority parser permits recognized native lines before or after the contiguous six-field
block, but relationship-hint analysis is a separate Markdown-aware scan over the entire visible
body. That scan ignores fences, HTML comments, blockquotes and inline-code-only text, does not
stop at the H2 boundary, and recognizes deterministic whole-line, column-zero forms using one of:

- completion-bearing: `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`,
  `resolves`, `resolved`, `complete`, `completes`, `completed`, `implement`, `implements`,
  `implemented` followed by an exact MAS issue reference;
- contributing: `ref`, `refs`, `reference`, `references`, `part of`, `contributes to`,
  `toward`, or `towards` followed by an exact MAS issue reference;
- relation-only: `relates to` or `related to` followed by an exact MAS issue reference;
- suppression: `skip` or `ignore` followed by an exact MAS issue reference.

Keyword matching is ASCII case-insensitive (`A-Z` folds to `a-z` only), so `Fixes` and `fixes`
are identical but Unicode confusables are not. Issue extraction from branch and title uses
Python-equivalent `re.ASCII | re.IGNORECASE` with
`(?<![A-Za-z0-9])MAS-[1-9][0-9]{0,8}(?![A-Za-z0-9])`; each match normalizes to uppercase `MAS-n`.
All matches are scanned left-to-right and then deduplicated/sorted by canonical issue ID.

A visible relationship line may have zero to three leading ASCII spaces, then one longest-match
keyword phrase, at least one ASCII space, and one or more exact issue IDs separated only by
optional-space comma or the exact ASCII phrase ` and `; one terminal period is allowed. Trailing
spaces, colons, hashes, URLs, unmatched punctuation, bare whitespace-separated targets and any
other suffix make the line non-recognized. Each target becomes its own lexical relationship;
duplicates collapse by `(issue_id, kind, source)`. Scanning is normalized-body line order, then
canonical tuple order. Generic MAS mentions in later prose are not relationship hints, though
title and branch identity extraction still records every bounded token.

Thus `Fixes MAS-28` under a later `## Links` section is a lexical hint but a six-field example
under `## Example` is not metadata authority. Body hints are observations, not proof of installed
native behavior. The normalized native-link snapshot remains the source for actual relationship
semantics; visible `skip` cannot launder a still-active native closing relationship.

## 6. Input contract: `mastermind.pr_linkage_observation.v1`

The core accepts one strict UTF-8 JSON object. Unknown keys are rejected at every nesting level,
and every key shown below is required; nullable keys use explicit JSON `null`. Booleans are JSON
booleans, PR numbers are positive integers, Git SHAs are lowercase 40-hex, digests are lowercase
64-hex, and all strings obey the resource limits above.

| Top-level key | Exact value |
|---|---|
| `schema` | `mastermind.pr_linkage_observation.v1` |
| `ruleset_id` | `mastermind.pr_linkage_rules.v1` |
| `ruleset_digest` | SHA-256 of the canonical rule-manifest projection in section 9 |
| `repository` | `{ "name": "owner/repository" }` |
| `pull_request` | `{ "number", "title", "body", "branch", "base_ref", "head_ref" }` |
| `authoring_epoch` | exact object below |
| `changed_paths` | exact snapshot below |
| `agentos` | exact snapshot below |
| `linear` | exact snapshot below |
| `path_ownership` | exact snapshot below |
| `native_linkage` | exact snapshot below |
| `receipt` | exact grounding object below |

`repository.name` and `receipt.repository` match
`[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+` byte-for-byte. `pull_request.base_ref`, `head_ref`, and
`branch` are nonempty printable ASCII strings; title/body are strict UTF-8 and are not Unicode
normalized.

### 6.1 Snapshot state law

Every snapshot object has the exact keys `state`, its named payload key(s), and `diagnostics`.
`state` is one of `PRESENT | PARTIAL | UNAVAILABLE | NOT_APPLICABLE | CONTRADICTORY`.
`diagnostics` is a unique lexicographically sorted list of stable adapter codes.

- `PRESENT`: required payload is complete and internally consistent; diagnostics is empty.
- `PARTIAL`: known payload is retained, diagnostics is nonempty, and absence is never proved.
- `UNAVAILABLE`: payload arrays are empty and nullable payload scalars are `null`; diagnostics is
  nonempty.
- `NOT_APPLICABLE`: payload arrays are empty/scalars `null`, diagnostics is empty, and the rule
  manifest must make the snapshot irrelevant to the declared mode.
- `CONTRADICTORY`: conflicting payload is retained, diagnostics is nonempty, and every dependent
  rule is indeterminate; `SNAPSHOT_CONTRADICTION` is emitted.

A shape that violates its state law is invalid input and produces the CLI execution-error exit,
not a semantic clean report. A well-shaped `PARTIAL`, `UNAVAILABLE`, or `CONTRADICTORY` snapshot
is valid input and produces typed partial findings.

### 6.2 Exact authoring epoch

```json
{
  "state": "PRESENT|PARTIAL|UNAVAILABLE|CONTRADICTORY",
  "relation": "PRE_CUTOVER|AT_OR_POST_CUTOVER|UNKNOWN",
  "default_ref": "string|null",
  "cutover_merge_sha": "40hex|null",
  "template_blobs": [{"path": "string", "blob_sha": "40hex"}],
  "first_strict_pr_number": "positive-integer|null",
  "legacy_open_pr_numbers": [1],
  "receipt_ruleset_digest": "64hex|null",
  "cutover_receipt_sha256": "64hex|null",
  "diagnostics": ["CODE"]
}
```

For `PRESENT`, relation is not `UNKNOWN`, all nullable receipt fields are non-null, template
blobs are nonempty, PR arrays are unique ascending integers, and `receipt_ruleset_digest`
equals the observation ruleset digest. `cutover_receipt_sha256` hashes canonical
`{repository, default_ref, cutover_merge_sha, template_blobs, first_strict_pr_number,
legacy_open_pr_numbers, receipt_ruleset_digest}` after removing only the digest itself. For
`UNAVAILABLE`, relation is `UNKNOWN`, nullable fields
are null, arrays empty and diagnostics nonempty. `PARTIAL`/`CONTRADICTORY` retain known receipt
fields but cannot authorize alias normalization. `template_blobs` sorts by `(path, blob_sha)`.

### 6.3 Exact changed-path snapshot

```json
{
  "state": "PRESENT|PARTIAL|UNAVAILABLE|NOT_APPLICABLE|CONTRADICTORY",
  "paths": [{"path": "relative/posix", "change_type": "ADDED|MODIFIED|DELETED|RENAMED", "old_path": "relative/posix|null"}],
  "diagnostics": ["CODE"]
}
```

Paths are repository-relative POSIX paths with no empty, `.` or `..` segment, backslash, NUL or
leading slash. `old_path` is non-null only for `RENAMED`. Entries sort uniquely by
`(path, change_type, old_path-or-empty)`. Conflicting entries for the same path are
`CONTRADICTORY`.

### 6.4 Exact Agent OS snapshot

```json
{
  "state": "PRESENT|PARTIAL|UNAVAILABLE|NOT_APPLICABLE|CONTRADICTORY",
  "basis": "BASE",
  "workstreams": [{"key": "WS:KEY", "waves": ["WAVE-ID"]}],
  "diagnostics": ["CODE"]
}
```

Workstreams sort uniquely by exact key; wave IDs sort uniquely lexicographically. Exact-key
duplicates with different waves are contradictory. Case-fold collisions remain valid evidence
and are evaluated by `WORKSTREAM_CREATION_KEY_COLLISION`. The canonical producer uses the
read-only `scripts.agentos` parser/store at the observation's exact base SHA; the core does not
parse the repository. `basis` is always `BASE`, including creates-workstream absence checks.

### 6.5 Exact Linear snapshot

```json
{
  "state": "PRESENT|PARTIAL|UNAVAILABLE|NOT_APPLICABLE|CONTRADICTORY",
  "issues": [{
    "id": "MAS-1",
    "project_id": "string|null",
    "workstream_key": "WS:KEY|null",
    "issue_type": "DELIVERY|MAINTENANCE|ROOT_RECOVERY|ARCHITECTURE|PROOF_GATE|ACCEPTANCE_GATE|UNKNOWN",
    "stop_law": "MERGE|BUILT_NOT_PROVEN|PROOF|ACCEPTANCE|RECORDS_ONLY|UNKNOWN"
  }],
  "diagnostics": ["CODE"]
}
```

Issues sort uniquely by ID. Duplicate IDs with different bindings/types/stop laws are
contradictory. `UNKNOWN` values are evidence gaps, not wildcards. Current Linear status,
timestamps, labels and prose may live in the external provenance receipt but are not rule inputs.

### 6.6 Exact path-ownership snapshot

```json
{
  "state": "PRESENT|PARTIAL|UNAVAILABLE|NOT_APPLICABLE|CONTRADICTORY",
  "basis": "BASE_POLICY",
  "resolutions": [{
    "path": "relative/posix",
    "role": "CURRENT|OLD_RENAME_SOURCE",
    "resolution": "EXACT|UNOWNED|AMBIGUOUS",
    "owner_workstream": "WS:KEY|NONE|null",
    "path_class": "RECORDS|RESEARCH|MAINTENANCE|IMPLEMENTATION|PROOF|DEPLOY|ARCHITECTURE|UNKNOWN",
    "allowed_authorities": ["implementation"]
  }],
  "diagnostics": ["CODE"]
}
```

The adapter, not the core, resolves repository globs/ownership policy to one row for every
changed-path `path` with role `CURRENT`, plus one `OLD_RENAME_SOURCE` row for every non-null
rename `old_path`. Resolutions sort uniquely by `(path, role)`, and allowed authorities use the
canonical enum sorted lexicographically. `basis` is always `BASE_POLICY`; the core performs no
glob parsing or precedence.

`EXACT` requires a concrete owner or `NONE`, a non-`UNKNOWN` path class, and a nonempty authority
allowlist. `UNOWNED` requires owner `NONE`, class `UNKNOWN`, and an empty allowlist.
`AMBIGUOUS` requires owner `null`, class `UNKNOWN`, an empty allowlist and a diagnostic. A
`PRESENT` snapshot has complete one-to-one coverage and only `EXACT`/`UNOWNED` rows. Missing
coverage is `PARTIAL`; duplicate/conflicting coverage is `CONTRADICTORY`. A complete `UNOWNED`
row is honest evidence that policy has no mapping, not authority permission: every applicable
path rule emits `PATH_OWNERSHIP_UNMAPPED`/partial, and maintenance exception also emits
`MAINTENANCE_EXCEPTION_UNBOUND`/error. Deletes resolve their
deleted path as `CURRENT`; renames evaluate both old and new paths, and incompatible exact
old/new authority classes make the snapshot `CONTRADICTORY`. The core intersects allowed
authorities across all exact changed-path rows. If at least one exact row excludes the declared
authority, the intersection proves `AUTHORITY_PATH_MISMATCH` even when another row is unowned;
all-unowned is partial, never conformant. Any ambiguous/missing row yields the partial snapshot
finding.

### 6.7 Exact native-link snapshot

```json
{
  "state": "PRESENT|PARTIAL|UNAVAILABLE|NOT_APPLICABLE|CONTRADICTORY",
  "pagination_complete": true,
  "relationships": [{
    "issue_id": "MAS-1",
    "kind": "CLOSING|CONTRIBUTING|RELATION_ONLY|AUTO_LINK|SUPPRESSED|UNKNOWN",
    "source": "BODY|BRANCH|TITLE|LINEAR_NATIVE|ADAPTER",
    "state": "PRESENT|SUPPRESSED|AMBIGUOUS|UNAVAILABLE",
    "completion_transition": "ELIGIBLE|INELIGIBLE|UNKNOWN"
  }],
  "diagnostics": ["CODE"]
}
```

Relationships sort uniquely by `(issue_id, source, kind, state, completion_transition)`.
`PRESENT` requires `pagination_complete: true`, no cursor/error diagnostic, and then an empty
relationship list proves none observed. `PARTIAL`/`UNAVAILABLE` use `false` and can never prove
absence. `NOT_APPLICABLE` uses `false` with empty arrays. `CONTRADICTORY` retains conflicting
records and uses `false`. An active and suppressed record for the same exact source/target, or
`PRESENT` with pagination/error residue, is contradictory.

### 6.8 Exact grounding receipt and hashes

```json
{
  "repository": "owner/repository",
  "pr_number": 1,
  "base_sha": "40hex",
  "head_sha": "40hex",
  "source_sha": "40hex",
  "body_sha256": "64hex",
  "observation_sha256": "64hex",
  "cutover_receipt_sha256": "64hex|null",
  "ruleset_digest": "64hex",
  "snapshot_digests": {
    "authoring_epoch": "64hex", "changed_paths": "64hex", "agentos": "64hex",
    "linear": "64hex", "path_ownership": "64hex", "native_linkage": "64hex"
  },
  "producer": "string"
}
```

Repository and PR identity match their top-level values. `body_sha256` hashes the exact UTF-8 PR
body bytes before newline normalization. Each snapshot digest hashes that exact snapshot object
using the canonical JSON law in section 10. `observation_sha256` hashes the entire canonical
observation after removing only `receipt.observation_sha256`; no clock/run/host fields exist in
the observation. `cutover_receipt_sha256` equals the authoring-epoch value when present, otherwise
is null. Ruleset digest equals the top-level value. Any mismatch emits
`OBSERVATION_GROUNDING_MISMATCH` and refuses metadata; it is never repaired by rereading a ref.

The core does not fetch, resolve, or verify refs. The adapter owns immutable observation
construction. Reports never contain the raw body; only its digest, normalized declaration and
bounded escaped evidence snippets leave the observation boundary.

## 7. Native relationship model

Each normalized relationship has:

```text
issue_id
kind = CLOSING | CONTRIBUTING | RELATION_ONLY | AUTO_LINK | SUPPRESSED | UNKNOWN
source = BODY | BRANCH | TITLE | LINEAR_NATIVE | ADAPTER
state = PRESENT | SUPPRESSED | AMBIGUOUS | UNAVAILABLE
completion_transition = ELIGIBLE | INELIGIBLE | UNKNOWN
```

Precedence for the analysis of a single exact issue is:

1. an exact, proven `SUPPRESSED` observation makes branch/title auto-links ineligible;
2. an exact native relationship snapshot governs over body hints;
3. multiple unsuppressed kinds with incompatible transition semantics are `AMBIGUOUS`;
4. absent/unavailable proof is `UNKNOWN`, never inferred clean from header completion alone.

MAS-67 currently proves relation-only and skip/ignore suppression. Closing/non-closing A/B,
multi-PR completion quorum, workspace configuration, and complete three-repository readback are
not yet proven by current canaries. Rules that depend on those live facts remain partial/warning
until an immutable MAS-67 receipt is supplied. That gap does not block the pure core.

`PORTFOLIO_LINKAGE_COMPLETION_MISMATCH` is the single canonical semantic contradiction. It
includes, for example:

- closing/completion-eligible linkage to an issue while metadata says `built-not-proven`,
  `proof-required`, `acceptance-required`, or `records-only` and the linked issue's stop law is
  not satisfied by merge;
- `merge-is-done` paired only with relation-only/suppressed/ineligible linkage;
- a records/research/architecture PR whose native closing relationship can project a broader
  implementation/program issue to `Done`;
- incompatible completion-bearing relationships to multiple identities.

## 8. Classification and verdict axes

Classification describes PR shape:

```text
TRACKED
MAINTENANCE_EXCEPTION
CREATES_WORKSTREAM
ARCHITECTURE_CANDIDATE
UNCLASSIFIED_LEGACY
UNKNOWN
```

Verdict describes evidence support:

```text
CONFORMANT
WARN
PARTIAL
REFUSE_METADATA
```

They are independent fields. `REFUSE_METADATA` means V1 refuses to certify the declaration;
it is not a mechanical merge block.

Verdict reduction is deterministic:

1. any `ERROR` finding -> `REFUSE_METADATA`;
2. otherwise, any unresolved evidence required by an applicable rule -> `PARTIAL`;
3. otherwise, any `WARNING`/legacy notice -> `WARN`;
4. otherwise -> `CONFORMANT`.

An observation can therefore be `TRACKED/PARTIAL`, `UNCLASSIFIED_LEGACY/WARN`, or
`UNKNOWN/REFUSE_METADATA`; a single overloaded status is forbidden.

## 9. Frozen finding contract

Every finding is structured:

```text
code, rule_id, severity, location, evidence, remediation_code
```

`severity` is `ERROR | PARTIAL | WARNING | NOTICE`. Evidence is bounded deterministic data,
not mutable human prose. Renderers map `remediation_code` to human text; wording is not part of
semantic identity.

The V1 codes are:

| Family | Codes |
|---|---|
| Header | `HEADER_MISSING`, `HEADER_DUPLICATE`, `HEADER_AUTHORITY_ZONE_INVALID`, `PLACEHOLDER_UNRESOLVED`, `WORKSTREAM_ID_INVALID`, `LINEAR_ID_INVALID`, `WAVE_EMPTY`, `WAVE_INVALID`, `PORTFOLIO_MODE_INVALID`, `PORTFOLIO_MODE_RESERVED`, `AUTHORITY_INVALID`, `COMPLETION_INVALID` |
| Epoch | `AUTHORING_SCHEMA_VERSION_MISMATCH`, `LEGACY_AUTHORING_ALIAS`, `AUTHORING_CUTOVER_RELATION_UNAVAILABLE` |
| Work identity | `LINEAR_REQUIRED_FOR_MODE`, `WORKSTREAM_UNKNOWN`, `WORKSTREAM_REQUIRED_FOR_TRACKED`, `WORKSTREAM_MUST_BE_NONE_FOR_EXCEPTION`, `AGENTOS_SNAPSHOT_UNAVAILABLE`, `LINEAR_ISSUE_UNKNOWN`, `LINEAR_SNAPSHOT_UNAVAILABLE`, `LINEAR_PROJECT_WORKSTREAM_MISMATCH`, `WORKSTREAM_CREATION_NO_WORKSTREAM_RECORD`, `WORKSTREAM_CREATION_KEY_COLLISION`, `MULTIPLE_PR_IDENTITIES` |
| Authority/path | `AUTHORITY_COMPLETION_MISMATCH`, `AUTHORITY_PATH_MISMATCH`, `PATH_OWNERSHIP_SNAPSHOT_UNAVAILABLE`, `PATH_OWNERSHIP_UNMAPPED`, `CHANGED_PATHS_UNAVAILABLE`, `MAINTENANCE_EXCEPTION_UNBOUND`, `ARCHITECTURE_CANDIDATE_CLAIMS_AUTHORITY`, `WORKSTREAM_CREATION_HIDDEN_IMPLEMENTATION` |
| Completion/native | `BRANCH_LINEAR_MISMATCH`, `TITLE_BODY_LINEAR_CONFLICT`, `CLOSING_KEYWORD_FOR_NON_MERGE_DONE`, `MERGE_DONE_WITH_EXPLICIT_PROOF_GATE`, `NATIVE_LINKAGE_SNAPSHOT_UNAVAILABLE`, `NATIVE_RELATIONSHIP_AMBIGUOUS`, `PORTFOLIO_LINKAGE_COMPLETION_MISMATCH` |
| Grounding | `OBSERVATION_GROUNDING_MISMATCH`, `SNAPSHOT_CONTRADICTION` |

Historical spellings may map into a renderer compatibility table but never create a second
semantic code. Every hostile mutant in W2 maps to at least one frozen code; a mutant that finds
an uncoded ambiguity requires a W0/W1 contract amendment, not free-form text.

### 9.1 Canonical rule manifest and digest

The implementation materializes one closed JSON-equivalent manifest with exactly these
top-level keys:

```text
schema = mastermind.pr_linkage_rule_manifest.v1
ruleset_id = mastermind.pr_linkage_rules.v1
observation_schema = mastermind.pr_linkage_observation.v1
report_schema = mastermind.pr_linkage_report.v1
execution_error_schema = mastermind.pr_linkage_execution_error.v1
parser_contract = {encoding, authority_block, h2_boundary, ignored_markdown, relationship_scan}
grammar = {ordered_fields, field_patterns, enum_values}
limits = {observation_bytes, body_bytes, body_lines, line_bytes, value_bytes,
          changed_paths, relationships, findings, field_occurrences}
compatibility = {aliases, receipt_schema, no_receipt_behavior}
classification = {mode_to_class, legacy_class, invalid_class}
authority_completion_allowlist = [ordered tuples from section 4.5]
path_reduction = {adapter_resolved_rows, coverage, rename_dual_path, authority_intersection}
native_reduction = [ordered rules below]
rules = [closed ordered rule rows below]
verdict_reduction = [ERROR, PARTIAL, WARNING_OR_NOTICE, CLEAN]
enforcement = REPORT_ONLY
```

There are no other policy inputs. In particular, Python source order, renderer wording,
environment variables, current time, repository checkout and live service state are excluded.

Classification reduction is exact: canonical `tracked`, `maintenance_exception`,
`creates_workstream`, and `architecture_candidate` map to their same-named uppercase classes;
a receipt-authorized alias maps to `UNCLASSIFIED_LEGACY` while retaining a separate normalized
candidate declaration for rule analysis; invalid/missing authority maps to `UNKNOWN`.

Native effect reduction is per exact issue ID, in this order:

1. a `CONTRADICTORY` snapshot or incompatible active records -> `AMBIGUOUS`;
2. `PARTIAL`/`UNAVAILABLE` snapshot -> `UNKNOWN`;
3. proven suppression makes only the matching branch/title auto-link source ineligible; it does
   not suppress an independent explicit/native closing source;
4. any remaining active `ELIGIBLE` relationship -> `COMPLETION_CAPABLE`;
5. otherwise any active `INELIGIBLE` relationship -> `NON_CLOSING`;
6. complete empty evidence -> `NONE`;
7. anything else -> `UNKNOWN`.

The on-disk manifest is serialized using the canonical JSON law in section 10. Its
`ruleset_digest` is `sha256(canonical_manifest_bytes)`. The canonical manifest normally omits a
digest field; if a transport envelope includes top-level `ruleset_digest`, that one key is removed
before hashing and its value must equal the derived digest. Lists use the explicit order above;
enum/set lists are unique lexicographic arrays; rule rows sort by `rule_id`. This is the only
self-exclusion.

### 9.2 Closed rule rows

Every manifest rule has exactly `rule_id`, `version` (`1`), `code`, `channel`, `severity`,
`applicability`, `predicate`, `evidence_keys`, and `remediation_code`. `channel` is always
`SEMANTIC`; invocation/input/execution diagnostics use section 11's separate schema. The following table freezes every value;
the short predicate is normative and expands only the sections cited above.

| Rule | Code / channel / severity | Applicability and predicate | Evidence keys | Remediation |
|---|---|---|---|---|
| `R001` | `HEADER_MISSING` / semantic / error | all; any of six fields absent from the one authority block | `missing_fields` | `ADD_CANONICAL_HEADER` |
| `R002` | `HEADER_DUPLICATE` / semantic / error | all; any field occurs more than once in zone | `field`, `locations`, `values` | `REMOVE_DUPLICATE_FIELD` |
| `R003` | `HEADER_AUTHORITY_ZONE_INVALID` / semantic / error | all; ordering/contiguity/Markdown/control/extra-line law violated | `reason`, `location` | `REPAIR_AUTHORITY_ZONE` |
| `R004` | `PLACEHOLDER_UNRESOLVED` / semantic / error | all; empty/template/TBD/TODO/pipe value | `field`, `value`, `location` | `REPLACE_PLACEHOLDER` |
| `R005` | `WORKSTREAM_ID_INVALID` / semantic / error | all; value fails exact WS/NONE grammar | `value`, `location` | `USE_EXACT_WORKSTREAM_ID` |
| `R006` | `LINEAR_ID_INVALID` / semantic / error | all; value fails exact MAS/NONE grammar | `value`, `location` | `USE_EXACT_LINEAR_ID` |
| `R007` | `WAVE_EMPTY` / semantic / error | all; wave empty after cosmetic wrapper rule | `location` | `SET_BOUNDED_WAVE` |
| `R008` | `WAVE_INVALID` / semantic / error | all; wave fails exact pattern/length | `value`, `location` | `SET_BOUNDED_WAVE` |
| `R009` | `PORTFOLIO_MODE_INVALID` / semantic / error | all; mode outside canonical enum/authorized alias | `value`, `location` | `SET_CANONICAL_PORTFOLIO_MODE` |
| `R010` | `PORTFOLIO_MODE_RESERVED` / semantic / error | all; authored `untracked_refused` | `value`, `location` | `REMOVE_RESERVED_MODE` |
| `R011` | `AUTHORITY_INVALID` / semantic / error | all; authority outside canonical enum/authorized alias | `value`, `location` | `SET_CANONICAL_AUTHORITY` |
| `R012` | `COMPLETION_INVALID` / semantic / error | all; completion outside canonical enum/authorized alias | `value`, `location` | `SET_CANONICAL_COMPLETION` |
| `R020` | `AUTHORING_SCHEMA_VERSION_MISMATCH` / semantic / error | any epoch for a non-alias value, or at/post-cutover for a named alias | `field`, `value`, `epoch` | `MIGRATE_TO_V1` |
| `R021` | `LEGACY_AUTHORING_ALIAS` / semantic / notice | present pre-cutover receipt; one of four aliases used | `field`, `alias`, `canonical`, `receipt` | `MIGRATE_TO_V1` |
| `R022` | `AUTHORING_CUTOVER_RELATION_UNAVAILABLE` / semantic / partial | alias observed and receipt not present/consistent | `epoch_state`, `receipt_digest` | `SUPPLY_CUTOVER_RECEIPT` |
| `R029` | `LINEAR_REQUIRED_FOR_MODE` / semantic / error | every canonical mode; Linear is `NONE` | `portfolio_mode`, `linear` | `SET_CONCRETE_LINEAR_ISSUE` |
| `R030` | `WORKSTREAM_UNKNOWN` / semantic / error | present Agent OS snapshot; declared exact key absent | `workstream` | `USE_EXISTING_WORKSTREAM` |
| `R031` | `WORKSTREAM_REQUIRED_FOR_TRACKED` / semantic / error | tracked; Workstream is `NONE` | `portfolio_mode`, `workstream` | `SET_TRACKED_WORKSTREAM` |
| `R032` | `WORKSTREAM_MUST_BE_NONE_FOR_EXCEPTION` / semantic / error | maintenance exception; Workstream is not `NONE` | `portfolio_mode`, `workstream` | `SET_WORKSTREAM_NONE` |
| `R033` | `AGENTOS_SNAPSHOT_UNAVAILABLE` / semantic / partial | mode/key rule needs Agent OS and state is not present | `snapshot_state`, `workstream` | `SUPPLY_AGENTOS_SNAPSHOT` |
| `R034` | `LINEAR_ISSUE_UNKNOWN` / semantic / error | present Linear snapshot; declared concrete issue absent | `linear` | `USE_EXISTING_LINEAR_ISSUE` |
| `R035` | `LINEAR_SNAPSHOT_UNAVAILABLE` / semantic / partial | concrete Linear rule and state is not present | `snapshot_state`, `linear` | `SUPPLY_LINEAR_SNAPSHOT` |
| `R036` | `LINEAR_PROJECT_WORKSTREAM_MISMATCH` / semantic / error | present snapshots; issue binding conflicts with declared exact WS | `linear`, `declared_workstream`, `bound_workstream` | `REPAIR_LINEAR_BINDING` |
| `R037` | `WORKSTREAM_CREATION_NO_WORKSTREAM_RECORD` / semantic / error | creates-workstream; changed paths do not add/reconcile exact WS record | `workstream`, `paths` | `ADD_EXACT_WORKSTREAM_RECORD` |
| `R038` | `WORKSTREAM_CREATION_KEY_COLLISION` / semantic / error | creates-workstream; base has exact/case-fold key collision | `workstream`, `collisions` | `CHOOSE_UNIQUE_WORKSTREAM_KEY` |
| `R039` | `MULTIPLE_PR_IDENTITIES` / semantic / error | unsuppressed branch/title/body/native targets create incompatible exact identities | `declared`, `targets` | `RECONCILE_PR_IDENTITIES` |
| `R040` | `AUTHORITY_COMPLETION_MISMATCH` / semantic / error | canonical mode/authority/completion tuple absent from section-4.5 allowlist | `portfolio_mode`, `authority`, `completion` | `USE_ALLOWED_AUTHORITY_COMPLETION` |
| `R041` | `AUTHORITY_PATH_MISMATCH` / semantic / error | present resolved path evidence excludes declared authority | `authority`, `paths`, `resolutions` | `RECONCILE_AUTHORITY_AND_PATHS` |
| `R042` | `PATH_OWNERSHIP_SNAPSHOT_UNAVAILABLE` / semantic / partial | applicable path rule and ownership state not present | `snapshot_state`, `paths` | `SUPPLY_PATH_OWNERSHIP_SNAPSHOT` |
| `R043` | `CHANGED_PATHS_UNAVAILABLE` / semantic / partial | applicable path rule and changed-path state not present | `snapshot_state` | `SUPPLY_CHANGED_PATHS` |
| `R044` | `MAINTENANCE_EXCEPTION_UNBOUND` / semantic / error | maintenance exception lacks concrete issue/maintenance path support | `linear`, `authority`, `paths` | `BIND_MAINTENANCE_EXCEPTION` |
| `R045` | `ARCHITECTURE_CANDIDATE_CLAIMS_AUTHORITY` / semantic / error | candidate claims implementation/deploy/production-owned changes | `authority`, `paths` | `REMOVE_CANDIDATE_EXECUTION_AUTHORITY` |
| `R046` | `WORKSTREAM_CREATION_HIDDEN_IMPLEMENTATION` / semantic / error | creates-workstream changed paths include runtime/production implementation | `paths`, `path_classes` | `SPLIT_WORKSTREAM_CREATION_FROM_BUILD` |
| `R047` | `PATH_OWNERSHIP_UNMAPPED` / semantic / partial | applicable path rule has one or more complete `UNOWNED` resolutions | `paths`, `resolutions` | `MAP_PATH_OWNERSHIP` |
| `R050` | `BRANCH_LINEAR_MISMATCH` / semantic / error | unsuppressed branch issue differs from declared target | `declared`, `branch_targets` | `RECONCILE_BRANCH_IDENTITY` |
| `R051` | `TITLE_BODY_LINEAR_CONFLICT` / semantic / error | visible title/body targets conflict with declaration/effects | `declared`, `title_targets`, `body_targets` | `RECONCILE_TEXT_IDENTITIES` |
| `R052` | `CLOSING_KEYWORD_FOR_NON_MERGE_DONE` / semantic / error | visible closing to declared issue with built-not-proven/proof-required/acceptance-required, or records-only when complete stop-law/path evidence disproves the section-4.5 records exception | `linear`, `completion`, `relationships` | `USE_NONCLOSING_RELATIONSHIP` |
| `R053` | `MERGE_DONE_WITH_EXPLICIT_PROOF_GATE` / semantic / error | merge-is-done contradicts exact Linear stop law requiring later proof/acceptance | `linear`, `completion`, `stop_law` | `SET_NONFINAL_COMPLETION` |
| `R054` | `NATIVE_LINKAGE_SNAPSHOT_UNAVAILABLE` / semantic / partial | applicable native rule and snapshot partial/unavailable | `snapshot_state`, `linear` | `SUPPLY_NATIVE_LINKAGE_SNAPSHOT` |
| `R055` | `NATIVE_RELATIONSHIP_AMBIGUOUS` / semantic / partial | native reducer yields ambiguous/contradictory for a target | `linear`, `relationships`, `diagnostics` | `RECONCILE_NATIVE_RELATIONSHIP` |
| `R056` | `PORTFOLIO_LINKAGE_COMPLETION_MISMATCH` / semantic / error | complete per-target native effect contradicts metadata/stop law after applying the section-4.5 records-only exception | `target`, `effect`, `completion`, `stop_law` | `REPAIR_COMPLETION_RELATIONSHIP` |
| `R060` | `OBSERVATION_GROUNDING_MISMATCH` / semantic / error | recomputed identity/body/snapshot/observation/ruleset digest differs | `component`, `expected`, `observed` | `REBUILD_IMMUTABLE_OBSERVATION` |
| `R061` | `SNAPSHOT_CONTRADICTION` / semantic / partial | any well-shaped snapshot state is contradictory | `snapshot`, `diagnostics` | `RECAPTURE_CONSISTENT_SNAPSHOT` |

Severity strings in the manifest are uppercase `ERROR | PARTIAL | WARNING | NOTICE`; the table's
lowercase prose maps byte-for-byte to those literals. Evidence objects contain exactly the named
keys, sorted lexicographically; extra evidence keys are schema errors. A rule that is not
applicable emits nothing. Missing evidence for an applicable rule emits its named partial row,
never the error row whose predicate has not been proven.

## 10. Output contract: `mastermind.pr_linkage_report.v1`

The report has exactly `schema`, `semantic`, `semantic_hash`, `receipt`, and `human`; unknown or
missing keys at any level are invalid. Its closed shape is:

```json
{
  "schema": "mastermind.pr_linkage_report.v1",
  "semantic": {
    "ruleset_id": "mastermind.pr_linkage_rules.v1",
    "ruleset_digest": "64hex",
    "enforcement": "REPORT_ONLY",
    "declaration": {
      "workstream": "WS:KEY|NONE|null", "linear": "MAS-1|NONE|null",
      "portfolio_mode": "string|null", "wave": "string|null",
      "authority": "string|null", "completion": "string|null",
      "authoring_state": "CANONICAL|LEGACY|INVALID|MISSING"
    },
    "classification": "TRACKED|MAINTENANCE_EXCEPTION|CREATES_WORKSTREAM|ARCHITECTURE_CANDIDATE|UNCLASSIFIED_LEGACY|UNKNOWN",
    "verdict": "CONFORMANT|WARN|PARTIAL|REFUSE_METADATA",
    "completeness": "COMPLETE|DEGRADED|UNAVAILABLE",
    "completion_interpretation": [{
      "issue_id": "MAS-1", "effect": "COMPLETION_CAPABLE|NON_CLOSING|NONE|AMBIGUOUS|UNKNOWN",
      "declared_completion": "string|null", "stop_law": "string|null",
      "consistency": "MATCH|MISMATCH|INDETERMINATE"
    }],
    "unresolved_observation_classes": ["AGENTOS"],
    "findings": [{
      "code": "CODE", "rule_id": "R001", "severity": "ERROR|PARTIAL|WARNING|NOTICE",
      "location": "string", "evidence": {}, "remediation_code": "CODE"
    }]
  },
  "semantic_hash": "64hex",
  "receipt": {
    "observation_schema": "mastermind.pr_linkage_observation.v1",
    "observation_sha256": "64hex", "body_sha256": "64hex",
    "cutover_receipt_sha256": "64hex|null", "ruleset_digest": "64hex",
    "repository": "owner/repository", "pr_number": 1,
    "base_sha": "40hex", "head_sha": "40hex", "source_sha": "40hex",
    "snapshot_digests": {
      "authoring_epoch": "64hex", "changed_paths": "64hex", "agentos": "64hex",
      "linear": "64hex", "path_ownership": "64hex", "native_linkage": "64hex"
    },
    "producer": "string"
  },
  "human": {"summary": "string", "remediations": ["string"]}
}
```

Completion rows sort uniquely by `(issue_id, effect, declared_completion-or-empty,
stop_law-or-empty, consistency)`. Finding order is
`(severity_rank, code, rule_id, location, canonical_evidence_json)`, where severity rank is
`ERROR=0, PARTIAL=1, WARNING=2, NOTICE=3`. Unresolved classes and human remediation strings are
unique lexicographic lists.

Canonical JSON is exactly the UTF-8 bytes of Python-equivalent
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
allow_nan=False)` with no final newline and no Unicode normalization. `semantic_hash` is SHA-256
of the canonical `semantic` object only; the hash is not inside that projection.

The semantic body includes only rule-bearing values. It excludes repository/base/head/source
SHA identity, snapshot byte digests, wall clock, retrieval time, run ID, runner/host/path,
environment, PR URL, and mutable human wording. Grounding belongs to core `receipt`, wording to
`human`, and run/time/runner identity to an external adapter receipt.
Semantically identical analysis therefore hashes identically across machines and PR identities,
while receipts retain exact grounding.

The core does not read a clock or runner environment. Shadow workflow run/time/runner identity
belongs in an external artifact receipt sidecar, not this deterministic core report.

`enforcement` is the fixed literal `REPORT_ONLY`. `CONFORMANT` means no configured discrepancy
was observed in the supplied evidence; it never means the work is accepted, done, deployable,
safe to close, or permitted to merge.

`completeness` is `COMPLETE` when every applicable snapshot is `PRESENT` (or legitimately
`NOT_APPLICABLE`) and no `PARTIAL` finding exists, `DEGRADED` when an otherwise parsed
declaration depends on any partial finding, unavailable or contradictory snapshot, and
`UNAVAILABLE` when no authoritative declaration can
be parsed. `unresolved_observation_classes` contains exactly the applicable members of
`AUTHORING_EPOCH | CHANGED_PATHS | AGENTOS | LINEAR | PATH_OWNERSHIP | NATIVE_LINKAGE` whose
state is partial, unavailable or contradictory, sorted lexicographically.

The report receipt copies, and the core revalidates, the observation's body, observation,
cutover, ruleset and snapshot digests. Render mode cannot change the semantic body or hash.

## 11. CLI and report-only exit law

W1 exposes a local command accepting a frozen observation file/stdin and producing one of:

- canonical JSON report;
- concise human report;
- GitHub annotation text using only `::warning` and `::notice` for semantic findings.

Input/invocation failures use a separate closed envelope, never
`mastermind.pr_linkage_report.v1`:

```json
{
  "schema": "mastermind.pr_linkage_execution_error.v1",
  "enforcement": "REPORT_ONLY",
  "error": {
    "code": "INVALID_JSON|INVALID_OBSERVATION_SCHEMA|INPUT_RESOURCE_LIMIT_EXCEEDED|UNSUPPORTED_RULESET|INTERNAL_ERROR|OUTPUT_WRITE_ERROR|NONDETERMINISTIC_RESULT",
    "component": "string",
    "reason_code": "string",
    "limit": "integer|null",
    "observed": "integer|null"
  },
  "execution_error_hash": "64hex",
  "receipt": {"input_sha256": "64hex|null", "source_sha": "40hex", "producer": "string"}
}
```

All keys are required and unknown keys rejected. The hash is SHA-256 of canonical `error` only.
Reason codes are stable machine tokens; mutable exception prose/stack traces are excluded and are
never emitted in annotations. The CLI writes this canonical envelope to stderr when it cannot
write the requested output path. Execution-error `source_sha` is the validator build/source Git
SHA, not a value parsed from the invalid observation, so it remains available for `INVALID_JSON`;
`input_sha256` is null only when no input bytes could be read.

Exit behavior:

- valid observation, including `REFUSE_METADATA`: exit `0` after a complete report;
- invalid JSON/input shape/state law, unsupported ruleset or resource-cap breach: emit the
  execution-error envelope and exit `2`;
- internal corruption, output-write failure or repeated-analysis byte mismatch: emit the
  execution-error envelope and exit `3`.

A well-shaped `CONTRADICTORY` snapshot is a semantic partial report, not an execution error. The
W3 adapter captures any non-zero core result as a typed `validator_execution_error`, publishes a
degraded artifact/summary and still concludes its shadow job successfully; it never converts an
execution defect into a false semantic clean result or merge block.

The core performs no socket creation, DNS, HTTP, subprocess network command, environment-secret
read, Git mutation, filesystem mutation other than its explicitly requested output, PR comment,
status/check mutation, Linear mutation, merge decision, or automatic repair.

## 12. Rollout and cutover law

The authorized sequence is:

1. **W0:** this records-only freeze lands.
2. **W0B:** reconcile Macro #6135 in place; create bounded Mastermind and Terminal template
   correction carriers only after verifying their current defaults. Every selectable named
   template carries the same contiguous six-line block and embedded contract-digest marker.
   Macro's named design-migration template retains its design gates below that block. Mastermind
   retires the case-colliding uppercase competitor after preserving useful prose in the canonical
   lowercase file. Each repository records exact merge/template blob SHAs, the immutable legacy
   PR cohort and real draft-PR prepopulation.
3. **W0C:** attempt missing MAS-67 A/B/native readback only if current permissions make it lawful;
   external admin gaps remain typed partial and do not block W1/W2.
4. **W1:** one Macro principal carrier implements the pure core/config/tests/fixtures. No CI
   workflow or House-Law registration.
5. **W2:** a separate blinded calibration freezes human labels before validator outputs; it
   reports every rule's FP/FN/partial/unresolved/mutation result rather than one accuracy score.
6. **W3:** after accepted W2, add a thin, separate, always-nonblocking report-only adapter and
   prove a real current PR observation. Missing Linear/native snapshots remain partial.
7. **W4:** independent Sol acceptance, durable Agent OS/Linear closeout, capability delta, and one
   exact next action.

W1 code belongs in `scripts/pr_linkage_validator.py` plus a pure module/config/tests. The name
must not match `scripts/check_*.py`, and the validator must not be registered in
`config/house_law_checks.yml`, `.github/ci/legacy-jobs.yml`, `ci-gate`, or contract-delta.
Existing CI authority inventory still legitimately treats `scripts/**` as authority-affecting;
normal exact-head/descendant-baseline proof applies to the implementation PR without making
linkage findings a gate.

The initial W3 workflow is a standalone manual report-only shadow. A `pull_request` trigger or
schedule is added only after explicit merge-control audit proves an always-green semantic path
cannot stall merge-on-green. The core itself remains unchanged.

## 13. Calibration and acceptance law

W2 freezes labels before exposing outputs to the independent labeler/reviewer. Minimum corpus:

- 15 normal tracked PRs across Macro, Mastermind, and Terminal;
- 5 implementation/proof/acceptance PRs where merge is not final completion;
- 5 lawful records-only merge-complete PRs;
- all current typed maintenance exceptions available to the program;
- at least 2 creates-workstream/recovery cases;
- at least 3 architecture candidates;
- pre-cutover/legacy cases;
- at least one hostile mutant for every finding/rule family.

Mandatory anchors are MAS-48/Mastermind #91, MAS-75/Mastermind #96, Macro #6104 suppression,
Macro #6119 relation-only, and a multi-PR completion-quorum case when immutable evidence exists.

Promotion to W3 requires zero false negatives across named hostile mutants, zero unexplained
false positives across frozen known-good goldens, all real-corpus mismatches adjudicated, no
partial/unknown treated as clean, deterministic bytes/hash, zero-network/mutation proof, and an
independent hostile review with all material findings repaired or durably rejected with evidence.

## 14. No-rebuild and collision boundary

Do not create:

- a lifecycle database, webhook service, PR registry, issue registry, Agent OS task store,
  scheduler, queue, lease, worker, or second control plane;
- a fuzzy workstream/project/issue inference engine;
- a hidden Linear/GitHub client in the core;
- a second Agent OS parser or schema store;
- a Linear projector/actor already owned by MAS-65/MAS-66;
- a merge controller, branch-protection rule, required check, or PR-comment bot;
- a duplicate Macro template PR instead of reconciling #6135;
- generated Agent OS views by hand.

Reuse `scripts.agentos` read-only parsing/store semantics. Adapters construct immutable snapshots;
the core observes them. One logical modifying operation retains one principal carrier until its
write/merge result is canonically reconciled.

## 15. W0 reconciled state and exact next wave

At this freeze:

- Macro #6135 is the sole open Macro default-template carrier and teaches the old alias family;
  the selectable design-migration template has no V1 block and must join that same carrier.
- Mastermind's lowercase template teaches the old alias family; its uppercase legacy template
  is a separate case-colliding surface whose actual draft-prepopulation precedence is unproven.
- Terminal has no default PR template at its current default head.
- MAS-67 C (relation-only) and D (skip/ignore) are proven; A/B and admin readbacks are partial.
- MAS-65 remains a separate draft desired-state compiler; MAS-66 remains separate and spec-only.
- current post-commission Macro movement included generated/data changes and #6258's dislocation
  CI manifest/workflow expansion. The latter did not change `ci-gate`, contract-delta,
  House-Law census or the MAS-28 placement/no-enforcement boundary, and W0 was refreshed to its
  exact merged head before delivery. The subsequent eight commits through
  `5b25fe3d944dc2344ddfa8abcc75b95f3fde8459` touched unrelated market data, research
  receipts/runbooks, cycle-pattern/issuer-profile work and a press-wire cursor; their exact path
  census had no MAS-28, WS:AGENT-OS, template or linkage-control collision. The final incoming
  commit was an Asia dashboard data/site render only.

The exact next action after W0 merges is: reconcile Macro #6135 in place to this grammar and
cutover law while independently preparing the bounded Mastermind/Terminal authoring corrections;
the pure W1 core may start only from the merged W0 law.
