# Mastermind Agent OS — canonical state schema

Status: **SCHEMA (proposed)**. Companion to `MASTERMIND_AGENT_OS_ARCHITECTURE.md`.
Machine copies: `agentos/schema/*.schema.yml`. Validator: `python3 scripts/agentos.py validate`.

---

## §0 Conventions that apply to every record

**Physical form.** One record = one file = YAML frontmatter + Markdown body. Frontmatter is the
machine-readable truth; the body is the human-readable truth. Both live in one artifact so they
cannot drift apart — the same contract `config/strategic_state.yml` and
`config/authority_map.yml` already use, and the same shape as the memory system.

**Keys.** Short UPPER-KEBAB, unique within its type, **never renumbered, never reused**.
Cited as `WS:<KEY>` / `DEC:<KEY>` / `DSC:<KEY>` — never by row or line number. This is inherited
verbatim from the `DNR:<KEY>` convention, which exists because row-number citations have already
mis-resolved in production (2026-08-05).

**There is exactly ONE citation shape, and a bare key is a hard error.** `depends_on: [FOO]`
is not a citation; it must be `depends_on: [WS:FOO]`. This is enforced rather than tolerated
because the tolerant version failed silently in the worst available way: a bare key in
`depends_on` was DROPPED with 0 errors and 0 warnings (verified — `depends_on:
[TOTALLY-NONEXISTENT]` exited 0), while the same key written `WS:TOTALLY-NONEXISTENT`
hard-errored. The dropped edge never reached the cycle check or the readiness graph walk,
so the dependency graph the whole design rests on was quietly incomplete with no signal.

**Timestamps.** ISO-8601 UTC (`2026-08-12T14:00:00Z`). Dates alone as `YYYY-MM-DD`. Relative
dates ("last Tuesday") are a validation error — they are unreadable six months later.

**Provenance is required on every factual claim.** `verified_at` + `verified_by`, where
`verified_by` is a command, a `file:line`, or a PR number. A claim with no provenance is an
assumption, and the schema makes you say which one it is.

**Fail-closed on schema, fail-open on join.** A malformed record hard-fails validation (I4). A
*dangling* reference — a PR that no longer exists, a sibling repo not checked out — degrades the
generated view with a warning and exit 0.

**Repo-relative paths always**, from the repository root, with a `repo:` prefix when not Macro
(`terminal:app/routes/portfolio.tsx`).

---

## §1 Workstream — `agentos/workstreams/WS-<KEY>.md`

The unit of work identity: a coherent objective with waves, owners, dependencies, and a next
action. Target cardinality **20–40 live**. This is the join key that makes everything else cheap.

### Fields

| Field | Req | Type | Notes |
|---|---|---|---|
| `key` | ✅ | UPPER-KEBAB | Matches filename. `PROPHET-US-ENTRY-TIMING` |
| `title` | ✅ | string | One line, human. No internal codenames without expansion. |
| `objective` | ✅ | string | 1–3 sentences: what "done" means in observable terms. |
| `status` | ✅ | enum | `proposed` · `active` · `blocked` · `awaiting_ci` · `awaiting_review` · `done` · `parked` · `killed` |
| `program` | ✅ | string | Key from `config/mastermind_programs.yml`. Validated to exist. |
| `p0` | ◻ | string | P0 id from Mastermind `config/strategic_state.yml`. Joined by `status` when that sibling checkout is present: an unknown id warns, an absent checkout populates `degraded` and leaves `p0_active` unknown (fail-open, I4). `validate` does not touch it — a record's validity must not depend on which checkouts exist on the machine. |
| `repos` | ✅ | list | Any of `macro` · `terminal` · `mastermind`. |
| `owner` | ✅ | string | Accountable seat/human — `chairman`, `coo-fable`, `codex`, `claude-fleet`. Not a session id. |
| `class` | ✅ | enum | `research` · `build` · `design` · `adjudication` · `mechanical`. Routing input (§10 architecture). |
| `blast_radius` | ✅ | enum | `reversible` · `user_facing` · `irreversible`. Sets verification budget. |
| `ambiguity` | ✅ | enum | `specified` · `scoped` · `open`. Routing input. |
| `owns_paths` | ◻ | list[glob] | Repo-relative globs this workstream expects to modify. Collision input. |
| `depends_on` | ◻ | list[`WS:<KEY>`] | Hard dependencies. Cycles are a validation error. |
| `blocked_by` | ◻ | list[string] | Free text + citation. Present ⟺ `status: blocked`. |
| `waves` | ✅ | list[Wave] | See §1.1. At least one. |
| `decisions` | ◻ | list[`DEC:<KEY>`] | |
| `discoveries` | ◻ | list[`DSC:<KEY>`] | |
| `landmines` | ◻ | list[string] | Free text; each cites a `DSC:` or `file:line`. Fed straight to the context compiler. |
| `do_not_redo` | ◻ | list[string] | Investigated and settled. Each cites evidence. |
| `artifacts` | ◻ | list[path] | Masterplans, handoffs, benchmark outputs. |
| `runtime_ref` | ◻ | object | `{service, deployed_sha, freshness_artifact}`. Interface to the runtime-truth program; Agent OS never discovers these itself. |
| `claim` | ◻ | object | `{by, at, expires}`. **Advisory only — blocks nothing.** |
| `needs_ceo` | ◻ | object | `{question, options, recommendation, by_when}`. Presence promotes it into the CEO brief. |
| `wait` | ◻ | object | `{kind, review_after, condition}`. **Declared intentional inactivity — schedules nothing, gates nothing.** See §1.2. Also valid per wave. |
| `next_action` | ✅ | string | The single next concrete action. Not a goal — a command, a file, or a decision. |
| `created` / `updated` | ✖ | — | **DERIVED, never authored.** The generator computes them from `git log` over the record file. Writing them by hand made every session touching a record rewrite the same line — the one verified concurrent-edit conflict site in this schema — and made staleness circular, since the field asserting freshness was typed by the session claiming it. |

### §1.1 Wave (inline)

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✅ | string | House idiom: `W0`, `W1`, `1A`, `P-A1`. |
| `title` | ✅ | string | |
| `status` | ✅ | enum | `todo` · `in_progress` · `awaiting_ci` · `done` · `dropped` |
| `pr` | ◻ | int \| list[int] | Joined to `active_builds.v1` at generation. |
| `depends_on` | ◻ | list[wave id] | Within this workstream. |
| `next_action` | ◻ | string | Overrides the workstream-level one while `in_progress`. |
| `wait` | ◻ | object | Same closed contract as the workstream-scope field. See §1.2. |

**Waves exist so there is no Task store.** They carry the two things a PR genuinely cannot
(`depends_on`, `next_action`) at ~4 fields instead of 20, and they match the W0/W1/W2 decomposition
every masterplan in this repo already uses. See architecture §3 and conflict C1.

### §1.2 Typed intentional wait (`wait`) — optional, at workstream OR wave scope

A workstream can be quiet for two entirely different reasons: it was abandoned, or its author
decided that waiting IS the correct next move — the sample has to mature, an operator has to act,
a counterparty has to answer, a calendar window has to arrive. Nothing in the record distinguished
those, so the only way to tell was to read `next_action` prose and guess. `wait` is the author
saying which one it is, in a shape a reader can trust without parsing English.

| Field | Req | Type | Notes |
|---|---|---|---|
| `kind` | ✅ | enum | `natural_evidence` · `external_dependency` · `calendar_window` · `external_action`. |
| `review_after` | ✅ | date | Date-only `YYYY-MM-DD`. The date a **human looks again** — not a predicted resolution, not an expiry, not a timer. |
| `condition` | ✅ | string | Non-empty opaque human context. **Never parsed** for authority, action, or completion. |

**The contract is CLOSED.** Unknown fields are a hard `bad-wait` error at both scopes, validated by
one shared rule. An open vocabulary would let each author mint a private reason, and "why is this
still sitting here" would need a parser again — which is the thing this field exists to remove.

**It executes nothing (I1).** No scheduler, no queue, no wake, no timer, no status transition, no
completion, no gate reads this field. It is testimony carried into `agent_os_state.v1` and
`context_bundle.v1` for a reader, and that is its entire reach.

**A past `review_after` stays schema-valid.** It is an OVERDUE REVIEW, not an expired lease —
degrading it automatically would be this file deciding something, and a review nobody performed is
exactly the fact a reader needs to see.

**Absence is never inferred.** A record with no `wait` is making no claim at all — it is not
thereby "abandoned", and a record WITH one is not thereby "alive". Like `claim`, presence is an
author's note in git, never evidence that anyone is working now.

### Example — a real, current workstream

```yaml
---
key: PROPHET-US-ENTRY-TIMING
title: US Prophet structural late-entry diagnosis and reduction
objective: >
  Diagnose and materially reduce structural late-entry behavior in US Prophet
  without unacceptable false-positive cost. Done = a measured entry-timing delta
  on held-out episodes with the false-positive cost printed alongside.
status: active
program: prophet-us
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: open
owns_paths:
  - engine/prophet_*.py
  - engine/cn_prophet_audit.py
depends_on: []
waves:
  - id: W0
    title: Queue drain + backfill
    status: done
    pr: 5370
  - id: W1
    title: Verify the 22:30Z bake lands clean
    status: in_progress
    next_action: >
      Read the 22:30Z bake log for the first post-backfill run; first-run-bomb
      law applies — a first run after a backfill is not evidence of steady state.
  - id: W2
    title: Entry-timing delta measurement on held-out episodes
    status: todo
    depends_on: [W1]
decisions: [DEC-PROPHET-EYES-OPEN-SCOPE]
discoveries: [DSC-FIRST-RUN-BOMB]
landmines:
  - "A first bake after backfill always looks anomalous — see DSC:FIRST-RUN-BOMB."
do_not_redo:
  - "Queue drain root-caused and fixed in #5370; do not re-diagnose the queue."
artifacts:
  - research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md
claim:
  by: claude/prophet-bake-verify-7f3a21
  at: 2026-08-12T09:00:00Z
  expires: 2026-08-15T00:00:00Z
next_action: Verify the 22:30Z bake (W1).
created: 2026-08-05
updated: 2026-08-12
---

## Context
US Prophet enters positions structurally late. ...

## Why this matters now
P0 `US_PROPHET_ENTRY_TIMING` is one of five active company objectives. ...
```

---

## §2 Decision — `agentos/decisions/DEC-<KEY>.md`

**The organizational memory of WHY.** Closes G1. Written at the moment of choosing, by whoever
chooses — not reconstructed later, because reconstruction is exactly what fails.

### Fields

| Field | Req | Type | Notes |
|---|---|---|---|
| `key` | ✅ | UPPER-KEBAB | |
| `question` | ✅ | string | The fork, as a question. If it can't be phrased as a question, it isn't a decision. |
| `answer` | ✅ | string | What was chosen. One or two sentences. |
| `rationale` | ✅ | string | **Why.** The load-bearing field of the entire system. |
| `alternatives` | ✅ | list[{option, why_not}] | ≥1 required. A decision with no rejected alternative is a default, and should say so: `option: "(none considered)"`. |
| `evidence` | ✅ | list[string] | Commands run, `file:line`, PR numbers, measurements. |
| `affects` | ✅ | list | `WS:` keys, programs, or path globs. |
| `confidence` | ✅ | enum | `high` · `medium` · `low` — of the *decision*, not the evidence. |
| `reversibility` | ✅ | enum | `easy` · `costly` · `one_way` |
| `decided_by` | ✅ | string | Seat: `chairman` · `ceo-sol` · `coo-fable` · session id. |
| `decided_at` | ✅ | date | |
| `supersedes` | ◻ | list[`DEC:`] | |
| `superseded_by` | ◻ | `DEC:` | Set on the OLD record when a new one lands. Never delete. |
| `review_by` | ◻ | date | For decisions taken under acknowledged uncertainty. |

### Relationship to `DO_NOT_REBUILD.md`

**DNR keeps kill authority.** They are different concepts, so P7 is satisfied:

| | DNR | DEC |
|---|---|---|
| Records | *kills, laws, holds* — what must NOT be built | *choices* — what WAS chosen and why |
| Enforcement | CI-compiled blocklists, hard-fail | none (I1) |
| Cite as | `DNR:<KEY>` | `DEC:<KEY>` |

A decision that kills a topic writes **both**: a `DEC-*` with the reasoning, and a DNR row citing
it. That is the existing append convention, now with a durable home for the grounds instead of
"keep grounds in the source doc."

### Example

```yaml
---
key: AGENTOS-NO-TASK-STORE
question: >
  Should Agent OS V1 carry a first-class Task entity with per-task records, as the
  commissioning brief requests?
answer: >
  No. Work decomposes into waves inline in the workstream record. PRs remain the
  execution object.
rationale: >
  Census §5.6 already adjudicated that sub-PR granularity is unnecessary for MVP and
  named a task queue an explicit non-goal. A 20-field per-task ritual fails the brief's
  own principle 3 (minimal friction) at 50 workers, and PR + workstream already carry
  18 of the 20 requested fields between them. Waves supply the only two a PR genuinely
  lacks — depends_on and next_action — at ~4 fields, and match the W0/W1/W2 idiom every
  masterplan already uses.
alternatives:
  - option: Full Task registry as specified in the brief PART II
    why_not: >
      Duplicates active_builds.v1 at finer granularity; thousands of rows that rot
      within a week; contradicts merged census §5.6.
  - option: Tasks as GitHub Issues
    why_not: >
      Puts the work registry behind the 5,000/hr shared REST bucket that
      gh_quota_guard.py exists to protect. Read-locality is the scaling property.
evidence:
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §5.6 (merged #5356, 2026-08-11 21:01)"
  - "scripts/build_active_build_map.py docstring — active_builds.v1 is PR-granular, advisory"
  - "Macro CLAUDE.md §GitHub quota — REST core pool is one shared 5,000/hr bucket"
affects: [WS:AGENT-OS]
confidence: medium
reversibility: easy
decided_by: opus-architecture-session
decided_at: 2026-08-12
review_by: 2026-09-12
---

## Grounds
...

## What would reverse this
If the CEO wants work items that exist before any PR and are assigned to workers by
someone other than the worker, a real task store is required. That is a dispatcher and
would belong in control_plane/, not here. Tracked as conflict C1.
```

---

## §3 Discovery — `agentos/discoveries/DSC-<KEY>.md`

High-value session findings that must survive the session and **must cross the account
boundary** — closing G2, since account-local Claude memory is unreadable to Codex workers.

### The two admission gates

A discovery is written **only if both hold**. This is the anti-hoarding mechanism:

1. **Falsifiable** — states a system fact a named command or file read could disprove.
2. **Load-bearing** — names what a future session would do differently.

"The exporter feels slow" fails both. "`export_rows()` drops non-ASCII filenames; repro
`pytest tests/test_export.py::test_unicode`; any export fix must start here" passes both.

### Fields

| Field | Req | Type | Notes |
|---|---|---|---|
| `key` | ✅ | UPPER-KEBAB | |
| `claim` | ✅ | string | One sentence. The fact itself. |
| `falsifier` | ✅ | string | **The command or read that would disprove it.** Required — this is gate 1, made structural. |
| `so_what` | ✅ | string | What a future session does differently. This is gate 2. |
| `kind` | ✅ | enum | `architecture` · `data` · `landmine` · `dead_code` · `constraint` · `runtime` |
| `verified_at` | ✅ | date | |
| `verified_by` | ✅ | string | Command, `file:line`, or PR. |
| `scope` | ✅ | list | Repos, programs, or path globs it applies to. |
| `confidence` | ✅ | enum | `verified` · `probable` · `suspected` |
| `cited_by` | ◻ | list | Auto-maintained by the generator. Drives GC. |
| `superseded_by` | ◻ | `DSC:` | |
| `expires` | ◻ | date | Default: `verified_at` + 90d if never cited. Flagged, never auto-deleted. |

### Example

```yaml
---
key: GOVERNANCE-JSONL-NOT-TRACKED
claim: >
  Mastermind's governance.jsonl is local runtime state, not git-tracked, so it cannot
  carry cross-machine or cross-repo organizational memory.
falsifier: >
  cd Mastermind && git ls-files | grep governance.jsonl
  — a non-empty result disproves this.
so_what: >
  Any design that proposes governance.jsonl as the home for durable org memory is
  wrong and should be redirected to a git-tracked store. It remains correct as the
  single-machine authority audit trail.
kind: architecture
verified_at: 2026-08-12
verified_by: "git ls-files (empty result); control_plane/governance.py:70 resolves data/governance/governance.jsonl"
scope: [mastermind, WS:AGENT-OS]
confidence: verified
---

## Detail
`control_plane/governance.py` writes to `data/governance/governance.jsonl`. `data/` paths
of this class are gitignored and the file is absent from `git ls-files`. ...
```

---

## §4 Handoff — `agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md`

Full specification, including the prose body template and the quality floor:
`MASTERMIND_AGENT_HANDOFF_PROTOCOL.md`. Handoffs **are** validated and counted (§6 rule
12) and their `DSC:` citations count toward the discovery citation total — a finding
whose only reader was a handoff used to age into a 90-day GC candidate. Frontmatter
contract:

| Field | Req | Notes |
|---|---|---|
| `workstream` | ✅ | `WS:<KEY>` |
| `session` | ✅ | Branch or worktree name |
| `model` | ✅ | `fable` · `opus` · `sonnet` · `codex` |
| `mission` | ✅ | What this session set out to do |
| `state_before` | ✅ | What was true at start |
| `changed` | ✅ | list[{path, what}] |
| `prs` | ◻ | list[int] |
| `verified` | ✅ | list[{claim, command, result}] — **each claim names the command that backs it** |
| `unverified` | ✅ | list[{claim, what_would_verify}] — empty list is a valid, meaningful answer |
| `decisions` / `discoveries` | ◻ | `DEC:` / `DSC:` keys minted this session |
| `unresolved` | ✅ | Open questions |
| `next_actions` | ✅ | Ordered; each concrete enough to execute |
| `do_not_redo` | ✅ | Investigated and settled, with evidence |
| `danger_areas` | ✅ | What breaks easily here |
| `ended_because` | ✅ | `complete` · `ci_handoff` · `blocked` · `context_budget` · `crashed` |

`verified` / `unverified` as separate required lists is deliberate: it makes "tests pass" —
the failure mode the brief names — structurally impossible to write without saying which
command produced it.

---

## §5 Generated views (not authored — I3)

### `data/governance/agent_os_state.json` — `agent_os_state.v1`

```json
{
  "schema": "agent_os_state.v1",
  "generated_at": "2026-08-12T14:00:00Z",
  "generator": "scripts/agentos.py status",
  "inputs": {
    "workstreams": 24,
    "active_builds": "data/governance/active_builds.json@2026-08-12T06:00:00Z",
    "worktrees": 31,
    "degraded": ["terminal repo not checked out — terminal workstreams show stale PR state"]
  },
  "workstreams": [
    {
      "key": "PROPHET-US-ENTRY-TIMING",
      "status": "active", "program": "prophet-us", "p0": "US_PROPHET_ENTRY_TIMING",
      "owner": "coo-fable", "next_action": "Verify the 22:30Z bake (W1).",
      "waves": {"done": 1, "in_progress": 1, "todo": 1},
      "wait": null,
      "prs": [{"number": 5370, "state": "merged"}],
      "claim": {"by": "claude/prophet-bake-verify-7f3a21", "expires": "2026-08-15T00:00:00Z", "stale": false},
      "needs_ceo": null,
      "collisions": []
    }
  ],
  "needs_ceo": [
    {"workstream": "WATCHLIST-PORTFOLIO-CEO",
     "question": "Portfolio vs Watchlist persistence model",
     "recommendation": "Single positions table with a kind discriminator",
     "by_when": "2026-08-14"}
  ],
  "readiness": {
    "schema": "agentos.readiness.v1",
    "records": [
      {"workstream": "PROPHET-US-ENTRY-TIMING", "wave": null,
       "state": "in_progress", "reason_code": "status_in_progress",
       "reason": "Authored workstream status is active.",
       "depends_on": [], "unmet_dependencies": [],
       "source": "agentos/workstreams/WS-PROPHET-US-ENTRY-TIMING.md"}
    ],
    "degraded": []
  },
  "warnings": ["DSC-OLD-FINDING uncited for 94d — GC candidate"]
}
```

`degraded` and `warnings` are first-class: a view that silently omits a missing input reads as
"everything is fine," which is the failure I4 exists to prevent.

The two degradation scopes are intentionally different. Parent `inputs.degraded` reports all
missing or stale auxiliary joins used by the broader status view. `readiness.degraded` reports
only hard workstream-authoring problems that excluded or made ambiguous a readiness identity;
PR state, P0, and worktree health do not participate in readiness and therefore never appear
there.
For a wave, effective `depends_on` is the canonical sorted union of parent workstream edges
(`WS:<KEY>`) and authored local wave edges (`WS:<CURRENT>#<WAVE>`). Terminal workstreams
(`done`, `killed`) and waves (`done`, `dropped`) retain those edges but emit no
`unmet_dependencies`. If a dependency target was excluded as malformed or retained under a
duplicate identity, readiness cannot assert ordinary blocking: the ambiguous identity and its
waves emit `unknown` / `status_unknown`, and any surviving proposed/todo dependent does the
same with the unavailable canonical ref named.

**Envelope vs pure section.** `generated_at`, `inputs.worktrees`,
`inputs.active_builds_age_hours`, and `inputs.degraded` are the volatile ENVELOPE and are
excluded from the byte-identity guarantee. `workstreams`, `needs_ceo`, the complete
`readiness` envelope, and `warnings` are a pure function of the authored records plus the join
inputs, and are
compared byte-for-byte across runs by `tests/test_agentos_status.py`. The split is what
makes the test meaningful: a byte-identity test that required a frozen clock to pass at
all would hide real nondeterminism inside the records themselves. Both are proven — the
whole file with `--now` pinned, and the pure section with the wall clock live.

**One regenerator: the nightly, and only the nightly.** `daily.yml` runs
`scripts/agentos.py status` immediately after `build_active_build_map.py`, whose output
is its PR-state input. There is deliberately **no** CI drift guard forcing every
record-touching PR to commit a regenerated copy: that would put two independent record
edits into conflict on a shared generated file neither author wrote, which is precisely
the write pattern invariant I2 exists to prevent. The artifacts may be up to ~24h stale
and they print their own input ages, so staleness is visible rather than assumed away.
Reasoning: `agentos/decisions/DEC-AGENTOS-NIGHTLY-IS-THE-ONLY-REGENERATOR.md`.

### `docs/AGENT_OS_STATE.md`

Human mirror of the same data, DO-NOT-EDIT banner, regenerated by the same command. Same
authored-vs-generated discipline as `docs/MASTERMIND_SYSTEM_MAP.md` and `docs/ACTIVE_BUILD_MAP.md`.

---

## §6 Validation rules (`scripts/agentos.py validate`)

**The line is MERGE REACHABILITY, and it is where it is for a measured reason.**
`validate` runs on every PR in the fleet, unscoped, over the WHOLE store — job
`self-mod-fence` in `.github/ci/legacy-jobs.yml`, which `infer_job_scopes()` gives an
empty path scope. So a hard rule that keys on the *state* of the work is a fleet-wide
fail-closed gate on a knowledge record, which makes invariant I1 operationally false.
It is also reachable with no bad record anywhere. Reproduced end to end on the
pre-change code: branch A marks one wave `done` (exit 0), branch B marks another
`dropped` (exit 0), `git merge` is clean, and the merged tree exits **1** on
`active-but-complete`. Two green PRs, a red main, and nothing to fix.

Hard-fail is therefore reserved for properties a clean textual merge of two
individually-valid records **cannot produce**.

**Hard-fail (exit 1) — malformation only:**

1. Unparseable frontmatter; unknown or missing required field; wrong enum value.
2. Duplicate key within a type; filename ≠ `key`.
3. `program` not present in `config/mastermind_programs.yml`. (A registry rename reds
   the renaming PR's own run, where the record is fixed — not a stranger's.)
4. Cycle in workstream `depends_on`, or in wave `depends_on`.
5. **Citation shape**: a bare key where a `PREFIX:KEY` citation belongs.
6. Dangling `DEC:`/`DSC:`/`WS:` reference to a key that does not exist.
7. `superseded_by` not reciprocated by `supersedes`.
8. Relative date strings; missing `verified_by` on a discovery.
9. `alternatives` empty on a decision.
10. No wave on a workstream.
11. **Discovery admission gates, as SHAPE**: `verified_by` and `falsifier` must each
    carry something runnable or openable — a command, a `file:line`, a `#PR`, or a URL.
    A non-empty check passes `falsifier: "no"` and `verified_by: vibes`, which is
    exactly the record the gates exist to refuse. Shape only: this cannot judge whether
    the command is the *right* one and does not pretend to.
12. **Handoff frontmatter**: required fields, `unverified` PRESENT (an empty list is a
    valid answer, its absence is not), every `verified[i]` naming its `command`, every
    `changed[i]` naming its `what`, and a body that does not say "see above" to a reader
    who cannot see above.

**Warn (exit 0) — work STATE and hygiene, never blocking. Reported by `status`/`brief`:**

- `status: active` while every wave is `done`/`dropped`.
- `status: blocked` with empty `blocked_by`, or the reverse.
- `record_disagrees_with_execution`: a wave that is not `done` behind a merged PR, or a
  `waves[].pr` absent from `active_builds.v1`.
- Workstream not touched in git for >30d while `status: active` (git-derived, not
  self-reported).
- Claim expired (`unclaimed`).
- Discovery >90d with zero `cited_by` (GC candidate).
- Decision past `review_by`.
- `owns_paths` overlapping another active workstream (collision signal).
- Referenced PR absent from `active_builds.v1` (may just be stale — fail-open per I4).
- **Phantom citation**: an `artifacts:` entry, or the static base of an `owns_paths:` glob, that
  does not exist. Warning rather than hard, because a `repo:`-prefixed path lives in a sibling
  checkout and a path may legitimately not exist yet. Added after the Phase 0 seeding itself
  cited `engine/prophet/**` (no such directory) and a masterplan filename missing its
  `_BY_FABLE` suffix — a rule with a demonstrated failure, not a speculative one.

The split is exactly I4: a malformed record is a lie about the org and must stop the writer; a
missing *join* is incomplete information and must not stop anyone.

---

## §7 Field-count check (friction budget)

The brief's principle 3: *"if agents need to fill out a 30-field form after every action,
nobody will use this system."*

| Record | Required fields | Auto-derivable | **Hand-authored** | Written when |
|---|---|---|---|---|
| Workstream (create) | 12 | 3 (`created`, `updated`, `repos`) | **9** | once, at workstream birth |
| Workstream (update) | — | `updated` | **1–2** (`status`, `next_action`) | at wave boundaries |
| Decision | 11 | 2 (`decided_at`, `decided_by`) | **9** | at the moment of choosing |
| Discovery | 9 | 2 | **7** | when both gates pass — rare by design |
| Handoff | 14 | 4 | **10** | once per session, at the existing `ci_handoff.py` stop |

The steady-state cost for a working session is **1–2 fields at a wave boundary**. Everything
heavier is written at a moment the session was already stopping to write prose. Phase 4 moves
`status`, `prs`, and `updated` to hook auto-capture, taking the steady-state cost to ~0.
