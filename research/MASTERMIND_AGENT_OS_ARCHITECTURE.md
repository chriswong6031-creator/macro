# Mastermind Agent OS — architecture

Status: **ARCHITECTURE (proposed)**. Opus session, 2026-08-12.
Commissioned by: `Mastermind Agent OS - CEO Control Plane V1 — Opus Architecture Handoff`.
Companion documents: `MASTERMIND_AGENT_OS_STATE_SCHEMA.md`, `MASTERMIND_AGENT_HANDOFF_PROTOCOL.md`,
`MASTERMIND_AGENT_OS_V1_IMPLEMENTATION_PLAN.md`, `MASTERMIND_CEO_BRIEF_SPEC.md`.

Authority: **architecture and advisory only.** Nothing in this document grants runtime
authority, gates a merge, or dispatches work. See §2 invariant I1.

---

## §0 Verdict — the brief's premise is half right, and the half that is wrong matters

The commissioning brief opens: *"The engineering capability is enormous. The coordination
layer is not."*

**The coordination layer is not missing. It exists twice, in two repositories, governing two
different worker populations — and neither one knows the other exists.**

| Plane | Governs | Where | Liveness |
|---|---|---|---|
| **Fleet law** | Claude Code *sessions* — commit→push→PR→arm→handoff→stop, worktree GC, model tier, GitHub quota | Macro `.claude/hooks/` (5 hooks), `scripts/ci_handoff_contract.py`, `.github/workflows/merge-on-green.yml`, `scripts/worktree_gc.py` | LIVE, battle-tested |
| **Executive OS** | Codex worker *processes* — durable job/attempt lifecycle, lease tokens, heartbeats, quota fences, LOST reconciliation, credential-free workspaces, capability grants | Mastermind `control_plane/` (`executive_runtime.py`, `executive_supervisor.py`, `executive_authority.py`, `executive_workspace.py`, `codex_worker.py`) | LIVE, Phase 1C-A as of 2026-08-12 03:53 |

What the brief describes as missing — task leases, heartbeats, stale detection, failure
recovery, authority tiers, CI watchers — **is built.** `executive_runtime.py` is a durable
SQLite queue with lease tokens and monotonic quota fences. `executive_supervisor.py` already
implements "after restart, treat an absent or ambiguous process as LOST, never success."
`ci_handoff.py` + the `merge-on-green` sweeper already implement the brief's PART X verbatim:
the expensive agent stops, a cheap 10-minute deterministic watcher observes CI, and work
resumes without the frontier model burning context.

Building any of that again would be the org's most expensive duplication to date.

### What is genuinely missing

The Executive OS Phase 0 census (`research/EXECUTIVE_OS_PHASE0_CENSUS.md`, merged
2026-08-11 21:01, PR #5356) names the gap itself, in its own duplication register §2 item 9:

> **Decision provenance distributed across four homes** (DNR rows, 52 adjudication docs,
> masterplan amendments, account-local memory) with no single ledger.

**The census did not defer the mechanism — it chose one, and this document overrides that
choice.** Saying it "deferred" was a misreading, corrected here: census §5 row 4 specifies
precisely *"Add ~3 event types: `executive_decision`, `objective_set/retired`,
`experiment_judged`"* on the existing `governance.jsonl`, with unification as *"a citation
convention across three live ledgers"*, and it states **"Explicit non-goal: a new unified
store."** `agentos/decisions/` is a new store. That is an override, and it is escalated as
**conflict C4** in §13 rather than presented as filling a vacancy.

The override has one specific ground, verified this session: **`governance.jsonl` is not
git-tracked.** `control_plane/governance.py:70` resolves it to `data/governance/governance.jsonl`
and `git ls-files` returns nothing for that path — it is single-machine runtime state, so it
cannot carry cross-machine, cross-repo organizational memory no matter how many event types it
gains. The census's mechanism is right for the *local authority audit trail* and stays; it
cannot be right for the durable org record. Direction of truth, stated so the two do not fork:
**the `executive_decision` event stays in `governance.jsonl` as the local audit row; `DEC:<KEY>`
is the durable record, and the event cites the key.**

Concretely, six gaps survive everything that is built:

| # | Gap | Evidence |
|---|---|---|
| **G1** | **WHY is not recorded.** Positive architectural decisions have no home. `DO_NOT_REBUILD.md` records *kills* with minted keys and CI-compiled blocklists — the strongest provenance mechanism in the org — but nothing records "we chose X over Y because Z." | Census §2.9; DNR §1–4 are `KILL-`/`LAW-`/`HOLD-` only |
| **G2** | **Discoveries die at the account boundary.** Session knowledge lives in `~/.claude/projects/<p>/memory/*.md`. Macro CLAUDE.md states plainly: *"Account-local Claude memory is not automatically shared with Codex or other accounts."* A Codex worker cannot read a single one. | Macro CLAUDE.md §Shared workspace |
| **G3** | **Handoffs have no schema.** 48 `*HANDOFF*` docs in Macro `research/`. Sampled first-headings are almost all distinct — 8 different opening structures across 8 files. The good ones are excellent; there is no floor. | `ls research/*HANDOFF*`, heading census |
| **G4** | **No work identity between "program" and "PR."** 59 programs (`config/mastermind_programs.yml`, architectural, durable) and hundreds of PRs (ephemeral). The thing the CEO actually asks about — *"7 active workstreams"* — has no machine object. It exists only as prose inside 137 masterplans. | Census §1.8; `mastermind_programs.yml` ontology |
| **G5** | **No CEO rollup.** `docs/ACTIVE_BUILD_MAP.md` is PR-shaped and advisory. It cannot answer "what needs me" because nothing carries that flag. The census explicitly declined a department rollup for MVP (§5.8). | `scripts/build_active_build_map.py` docstring |
| **G6** | **Context compilation is a working prototype held at advisory.** `scripts/context_index_query.py` already emits a cited `context_packet.v1` with an `--mode adjudication`. It is advisory while benchmark gates are red. | Macro CLAUDE.md §Context Index |

**The Agent OS V1 is the layer that closes G1–G6 and nothing else.** It is a *knowledge and
work-identity plane*. It is not a third control plane, and §2 makes that structurally
enforceable rather than merely promised.

### `DNR:KILL-PARALLEL-KNOWLEDGE-BASE` — the standing kill this design must clear

House law requires citing `research/DO_NOT_REBUILD.md` before proposing new work. **The first
draft of this architecture did not, and the omission was material** — one row is squarely on
point (`research/DO_NOT_REBUILD.md`, §1, `CXI-R12`, 2026-07-18):

> **KILL-PARALLEL-KNOWLEDGE-BASE** — *Second hand-maintained knowledge base / wiki / RAG memory
> service parallel to canonical sources (agents required to write session knowledge into a
> separate database).* **FORBIDDEN** — knowledge retrieval is the Macro Context Index (derived,
> rebuildable, canonical-sources-keep-truth); a hand-curated parallel store is the ratified
> program's named degenerate form.

Read honestly, `DSC-*` is the closest thing in this design to the killed form: it is session
knowledge, written by agents, into a store that did not exist before. The kill is not evaded by
noting that `agentos/` is Markdown rather than a database — that would be a technicality, and
the DNR preamble is explicit that a killed topic needs **new evidence and an explicit ruling**,
not a re-description. Three properties distinguish this design from the killed form, and each
is checkable:

1. **Not parallel — canonical.** The kill's operative word is *parallel to canonical sources*.
   `DEC-*` and `DSC-*` hold facts with **no other home**: a positive decision's rationale, and a
   cross-account discovery. There is no canonical source they shadow, so there is no second copy
   to drift. Where a canonical source *does* exist, this design defers to it by name — DNR keeps
   kill authority, `mastermind_programs.yml` keeps the org chart, masterplans keep the prose,
   `governance.jsonl` keeps the local audit trail.
2. **Retrieval stays CXI.** The kill's stated ground is that *knowledge retrieval is the Macro
   Context Index*. This design builds no retriever: §8 explicitly declines one, and Phase 3
   registers `agentos/**` as a **corpus** for `context_index_query.py`. The index over these
   records remains derived and rebuildable; only the records themselves are authored.
3. **New evidence the ruling could not have weighed.** CXI-R12 ruled on 2026-07-18. **G2 — that
   account-local Claude memory is structurally unreadable to Codex workers — is not a retrieval
   problem and CXI cannot close it**, because CXI indexes repository content and account-local
   memory is not repository content. A Codex session cannot read one of those files no matter
   how good the index is.

**This is an argument, not a ruling.** Per the DNR preamble, only the operator/Fable can clear a
killed topic. It is escalated as **conflict C5** in §13 and carried on `WS:AGENT-OS` as a
`needs_ceo` item. Until it is ruled: Phase 0 (records that exist) stands, and **Phase 1 must not
mandate that sessions write `DSC-*`** — that mandate is the precise thing the row forbids.

### Binding constraints this design inherits

Three already-adjudicated rulings constrain any answer, and this design honors all three:

1. **`duplicate_control_planes: prohibited`** — a standing constraint in Mastermind
   `config/strategic_state.yml`, changeable only by a recorded Chairman/CEO decision.
2. **Census §6 binding non-goals for Phase 1** — no second control plane; no worker/session
   tracking service; no new schedulers, queues, or buses; no auto-arming authority anywhere.
3. **Charter V2 P7 — one source of truth per concept.**

Parts of the commissioning brief collide with constraint 2, and this design overrides two
prior adjudications (census §5.4 and a standing DNR kill). All five are flagged rather than
silently resolved. See §13.

---

## §1 What already exists (reconnaissance result)

PART I of the brief asked for a repository census. One was performed 12 hours before this
session and merged: `research/EXECUTIVE_OS_PHASE0_CENSUS.md` (~45 components). This section
does not repeat it — it records only what the Agent OS must bind to, verified this session.

**Useful existing primitives (KEEP — the Agent OS reads these, never replaces them):**

| Primitive | What it is | Agent OS relationship |
|---|---|---|
| `config/mastermind_programs.yml` → `docs/MASTERMIND_SYSTEM_MAP.md` | 59 programs, 6 category-departments, ontology with lifecycle + `owns`/`does_not_own` + `decision_boundary.authority_class`, 3-repo baselines, `known_unresolveds` | **Parent key.** Every workstream declares `program:` pointing here. The org chart is not re-created. |
| `docs/ACTIVE_BUILD_MAP.md` + `data/governance/active_builds.json` (`active_builds.v1`) + `docs/PROJECT_ACTIVE_BUILD_MAP.md` | Nightly-generated open PRs, file collisions, recent merges; advisory, fail-open on `gh` failure | **Execution truth, imported.** Agent OS never polls GitHub per-agent; it joins this artifact. |
| `research/DO_NOT_REBUILD.md` + `config/compiled_kill_registry.yml` + `config/signal_foundry_blocklist.yml` + `blocklist_regen_guard` hook | Append-only kill/law/hold ledger, minted stable keys, `DNR:<KEY>` citation law, CI-enforced compilation | **Precedent and sibling.** Decisions adopt its exact idiom. DNR keeps kill authority; Agent OS records the positive half. |
| `scripts/context_index_query.py` + `config/context_index.yml` | `search`/`open`/`recent`/`explain`/`status`, `context_packet.v1`, `--mode adjudication`, cross-project via `--projects` | **The context compiler.** Extended with new corpora, not replaced. |
| `.claude/hooks/ship_loop_guard.py`, `scripts/ci_handoff_contract.py`, `merge-on-green.yml` | Session completion contract; deterministic 10-min CI sweeper | **Session lifecycle.** Agent OS emits a handoff at the same boundary; it does not re-implement the gate. |
| Mastermind `control_plane/executive_*.py` | Durable process lifecycle, leases, heartbeats, authority grants | **Hot plane.** Emits events into the Agent OS cold plane at lifecycle boundaries (§6). |
| Mastermind `config/strategic_state.yml` + `research/MASTERMIND_CHARTER_V2.md` | Company phase, north star, 5 P0 objectives, resource policy, constraints; P1–P10 constitution | **Strategy key.** Workstreams declare `p0:` pointing at a P0 id. Agent OS never restates strategy. |
| 137 masterplans + 48 handoffs in `research/` | Deep durable state; `§0 ACCEPTANCE GATES` convention; session-chain handoffs | **Body text.** Records point *into* these; prose is never migrated. |

**Redundant / obsolete (already adjudicated — not this program's work):** census §2 lists 12
duplications and §3 lists the absorb/deprecate/delete set. The Agent OS adds no new dependency
on anything on the DEPRECATE or DELETE list.

**Things that should become canonical (this program's proposal):** the `workstream` as the unit
of work identity (§3), the minted-key record as the unit of provenance (§4), and the handoff
record as the unit of session continuity (§7).

---

## §2 Principles and invariants

The brief's principle set is adopted in full. Four invariants make them structural rather
than aspirational — each is a *checkable property*, and I1 is what keeps this from becoming
the third control plane.

> **I1 — The Agent OS never decides whether something may run.**
> It has no gate, no lease with teeth, no dispatch, no scheduler, no authority grant. It
> records what work exists, what was decided, what was learned, and what is next. If a
> proposed feature would let Agent OS *block or start* execution, that feature is out of
> scope by construction and belongs to `control_plane/` (processes) or the Macro hook layer
> (sessions). **This is the test that distinguishes it from a control plane, and it is the
> reason it does not violate `duplicate_control_planes`.**

**I1 acceptance gate, phrased so a reviewer can check it rather than believe it.** For
any phase: *no runtime, scheduler, hook, or seat consumes `agent_os_state.v1` or
`ceo_brief.v1` to decide what to RUN.* The brief is a human-read view. Note this test is
BROADER than "can it block" — Mastermind `config/strategic_state.yml:13-18` defines a
second control plane as **any execution path that reads an artifact to decide what to
run**, so a scheduled task or push transport that consumed the brief would qualify even
though it blocks nothing. Adding one is a separate recorded ruling, not an implementation
detail.

Phase 2's own answer, stated for the record: `status` and `brief` read records,
`data/governance/active_builds.json` and `git worktree list`; they write two derived
files and exit 0 unconditionally; nothing reads those files at runtime. `validate` is the
one component that can exit non-zero, and its hard rules were narrowed to malformation
for exactly this reason — a state-keyed hard rule made a knowledge record able to red
every armed PR in the fleet, which made I1 operationally false while the document still
claimed it (reproduced: two individually-valid records, one clean merge, exit 1).

> **I2 — One writer per fact, one file per record.**
> No record is written by two mechanisms. No two records may be appended to the same file.
> This is not style: with 20–50 concurrent workers across worktrees, a shared append target
> is a guaranteed merge conflict. The org already learned this — the memory system is
> one-fact-per-file for exactly this reason. File creation merges cleanly in git; line
> appends do not.

> **I3 — Derived state is never hand-edited; authored state is never generated.**
> `agentos/` holds authored records. `docs/AGENT_OS_STATE.md` and
> `data/governance/agent_os_state.json` are generated and carry a DO-NOT-EDIT banner.
> Regeneration is a pure function over authored records + already-generated artifacts.

> **I4 — Fail-open on read, fail-closed on schema.**
> A missing or unreachable input (GitHub down, `gh` rate-limited, a sibling repo absent)
> degrades the *view* with a printed warning and exit 0 — never reds the nightly. This
> mirrors `build_active_build_map.py`, which is fail-open by design. A **malformed authored
> record** is the opposite: it hard-fails validation, because a silently-empty workstream set
> means a CEO brief that under-reports reality.

Adopted from the brief, restated as design law:

- **Compile context, do not dump it.** (§8)
- **Preserve WHY.** Code records what; the decision record records why. (§4)
- **Git remains authoritative for code.** Agent OS stores no code state, only pointers.
- **Minimal friction.** Every field is either auto-derivable, or it is required at exactly one
  moment a session is already stopping to write prose. (§10)
- **Design for 10×.** Nothing centralized-synchronous; see §12.

---

## §3 The state model

Five levels. **Only one of them is a new store.**

```
STRATEGY      strategic_state.yml  P0 objectives (5)          Mastermind, exists
                      │
ARCHITECTURE  mastermind_programs.yml  programs (59)          Macro, exists
                      │
WORK IDENTITY   ►  agentos/workstreams/  workstreams (~20-40)  ◄  NEW — the join key
                      │
EXECUTION       waves (inside the workstream record)          NEW, lightweight
                      │
              GitHub PRs / active_builds.v1                   exists, imported
```

### Why `workstream` is the missing entity

The org has an architectural registry (59 programs — durable, changes rarely) and PRs
(hundreds — ephemeral, machine-native). Between them sits the thing the CEO actually asks
about and the thing every masterplan is actually *about*: a coherent objective with waves,
owners, dependencies, and a next action. Today it exists only as prose. Giving it an ID is
what makes every other feature in the brief cheap:

- "What is happening?" = list workstreams by status. (PART IX)
- "Who owns this subsystem?" = workstreams declare `owns_paths`. (PART VII)
- "What can start next?" = workstreams declare `depends_on`. (PART X)
- "What context does this task need?" = follow the workstream's own links. (PART VI)

**Cardinality is the design constraint that makes it work.** ~20–40 live workstreams is a set
a human can read and a session can maintain. A *task* registry would be thousands of rows and
would rot within a week — which is precisely why census §5.6 ruled PR granularity sufficient.

### Why there is deliberately no `Task` store

The brief's PART II asks for a Task entity with 20 fields. **I am declining that, and this is
a genuine disagreement worth stating plainly** (§13 records it as an open CEO decision).

Reasons: census §5.6 already adjudicated *"Sub-PR task granularity is not needed for MVP"* and
*"Explicit non-goal: task queue"*; a 20-field-per-task ritual violates the brief's own
principle 3 (minimal friction) at 50 workers; and PR + workstream already carry 18 of the 20
requested fields between them.

What replaces it: **waves**. Every masterplan in this repo already decomposes work as W0/W1/W2
— this is settled house idiom, not an invention. A wave is 4 fields (`id`, `title`, `status`,
`pr`) inline in the workstream record. The two fields PRs genuinely lack — `depends_on` and
`next_action` — are carried by the wave. No separate store, no per-task update ritual, and the
dependency graph the brief asks for in PART X becomes expressible.

### Entity summary

| Entity | Store | New? | Cardinality | Written by |
|---|---|---|---|---|
| Program | `config/mastermind_programs.yml` | no | 59 | operator, rarely |
| P0 objective | Mastermind `config/strategic_state.yml` | no | 5 | Chairman/CEO seat |
| **Workstream** | `agentos/workstreams/<ID>.md` | **yes** | 20–40 live | owning session |
| Wave | inline in workstream | **yes** | 3–8 per workstream | owning session |
| **Decision** | `agentos/decisions/DEC-<KEY>.md` | **yes** | grows slowly | any session, at the moment of choosing |
| **Discovery** | `agentos/discoveries/DSC-<KEY>.md` | **yes** | grows, GC'd | any session |
| **Handoff** | `agentos/handoffs/<WS>-<date>.md` | **yes** | one per session-chain link | ending session |
| Kill / law / hold | `research/DO_NOT_REBUILD.md` | no | append-only | adjudicating session |
| PR / CI / merge state | `active_builds.v1` (generated) | no | hundreds | `build_active_build_map.py` |
| Session / process | `control_plane/` SQLite + `git worktree list` | no | live | runtime |
| Runtime truth | separate workstream (§11) | no | — | that program |

Full field-level schemas with worked examples: `MASTERMIND_AGENT_OS_STATE_SCHEMA.md`.

---

## §4 Storage architecture

**Decision: git-tracked Markdown with YAML frontmatter, one file per record, plus generated
views. No database, no daemon, no event bus, no service.**

### The boring baseline, and what it fails

The most boring option is the census's own position: *convention only* — cite the four existing
provenance homes, add no store. It is cheapest and it is right about most things. It fails on
exactly two checkable points, which is why a mechanism is warranted:

1. **It cannot cross the account boundary (G2).** Account-local memory is invisible to Codex
   sessions no matter how good the convention. A convention cannot make an unreadable file
   readable.
2. **It has no join key (G4/G5).** With nothing linking masterplan → decision → PR, no rollup
   can be generated, so "what needs me" stays a manual reconstruction.

Everything the convention *can* do, it keeps doing: DNR retains kill authority; masterplans
retain the deep prose; `governance.jsonl` retains the local authority audit trail.

### Mechanism comparison

| Mechanism | Verdict | Reason |
|---|---|---|
| **File-per-record, git-tracked, YAML frontmatter + prose** | **CHOSEN** | Conflict-free concurrent writes (I2). Human- and machine-readable in one artifact. Versioned, diffable, reviewable, recoverable by `git revert`. Zero new infrastructure. Already the house idiom twice over: memory files (frontmatter + body + index) and DNR (minted keys + compiled output). |
| Append to a shared JSONL | rejected | Guaranteed merge conflicts at 20–50 writers. Violates I2. |
| Extend Mastermind `governance.jsonl` | rejected as the *home* | **Verified this session: it is not git-tracked** — `governance.py` writes to `data/governance/governance.jsonl`, and `git ls-files` returns no such path. It is single-machine runtime state and cannot carry cross-machine, cross-repo org memory. It stays exactly what it is. |
| SQLite | rejected for the cold plane | Binary, unmergeable in git, invisible in PR review. Correct for the *hot* single-machine plane, where `executive_runtime.py` already uses it well. |
| Postgres / daemon / message bus | rejected | Census §6.4 forbids new schedulers, queues, buses. Ops burden with no offsetting property. |
| Vector database | rejected for V1 | The brief itself warns against it. §8 shows the link graph makes retrieval a lookup, not a search problem. |
| GitHub Issues | rejected | Puts org memory behind the 5,000/hr shared REST bucket that `gh_quota_guard.py` exists to protect. Read-locality is the whole scaling property (§12). |

### Layout

```
agentos/
├── README.md                     ← the 30-line contract a cold session reads first
├── schema/
│   ├── workstream.schema.yml
│   ├── decision.schema.yml
│   ├── discovery.schema.yml
│   └── handoff.schema.yml
├── workstreams/   WS-<SLUG>.md
├── decisions/     DEC-<SLUG>.md
├── discoveries/   DSC-<SLUG>.md
└── handoffs/      <WS-SLUG>-<YYYY-MM-DD>.md

docs/AGENT_OS_STATE.md                     ← generated, DO NOT EDIT (human)
data/governance/agent_os_state.json        ← generated, agent_os_state.v1 (machine)
scripts/agentos.py                         ← validate | status | brief | compile-context
```

**Home repository: Macro Dashboard.** The fleet law, the hooks, ABM, DNR, and the context index
all live here; the census calls Macro's layer *"the de-facto Executive OS today"* (§1.8); and
most sessions run here. Cross-repo sessions write through `scripts/agentos.py` against the
sibling checkout, the same way they already read Macro conventions today.

**This does not violate Macro CLAUDE.md's "no second strategic state, control plane, or
authority map."** The store contains none of those three: no strategy (it points at
`strategic_state.yml`), no authority (I1 — it gates nothing), no dispatch. It is the same class
of artifact as DNR and ABM, both of which already live in Macro and are explicit KEEPs in the
census.

### Key minting

Adopts the DNR convention exactly, because it is proven and CI-enforced: short UPPER-KEBAB,
unique file-wide, **never renumbered or reused**, cited as `WS:<KEY>` / `DEC:<KEY>` /
`DSC:<KEY>`. Citation by row/line number is banned — the org has already been burned by
row-number citations mis-resolving after a reflow (2026-08-05).

---

## §5 Memory architecture

The brief's five layers map onto stores that mostly exist. The Agent OS supplies B/C/D
durability and, critically, the **promotion and expiry rules** — the difference between memory
and hoarding.

| Layer | Content | Home | Status |
|---|---|---|---|
| **A — Constitutional** | Charter V2 P1–P10; Macro CLAUDE.md / AGENTS.md fleet law; NW constitution A0–A7; DNR kills/laws | exists (4 homes, deliberately) | unchanged |
| **B — System** | Subsystem responsibility, ownership, pipeline relationships | `mastermind_programs.yml` + **`DEC-*` records** | decisions are new |
| **C — Project state** | Active workstreams, wave status, blockers, PR state | **`agentos/workstreams/`** + imported `active_builds.v1` | workstreams are new |
| **D — Session** | Discoveries, landmines, handoffs | **`DSC-*` + `agentos/handoffs/`** | new; today account-local (G2) |
| **E — Ephemeral** | Logs, scratch, tool output | scratchpad, run logs | **must not enter `agentos/`** |

### Promotion rules (D → B/A)

A discovery is written only if it passes **both** gates. This is the anti-hoarding mechanism
and it is deliberately strict:

1. **Falsifiable** — it states a fact about the system that a named command or file read could
   disprove. "The exporter feels slow" fails. "`export_rows()` drops rows whose filename is
   non-ASCII; repro `pytest tests/test_export.py::test_unicode`" passes.
2. **Load-bearing** — it names what a future session would *do differently*. A discovery that
   changes no future action is a log line, not memory.

Promotion D→B happens when a discovery is cited by ≥2 workstreams or by a decision: it is then
restated in the owning `DEC-*` or in `mastermind_programs.yml`. Promotion B→A (constitutional)
is an operator/COO act only, and lands in CLAUDE.md/AGENTS.md or the Charter — never automatic.

### Retention, staleness, GC

- Every record carries `verified_at` and `verified_by` (a command, a PR, or a file:line).
- A discovery older than **90 days** with zero inbound citations is flagged `stale` by
  `agentos.py validate` and is a candidate for deletion in the next sweep. Flagged, never
  auto-deleted — the same report-first posture as `worktree_gc.py`, which deletes only while
  `config/worktree_gc.json` is explicitly `armed: true`.
- A workstream whose `claim.expires` has passed is reported `unclaimed`; the record survives.
- **Supersession, never deletion, for decisions.** `DEC-A` superseded by `DEC-B` sets
  `superseded_by: DEC-B` on A and `supersedes: [DEC-A]` on B. Both survive. This is what makes
  "three days later an agent decides it looks weird and changes it" recoverable: the record is
  found by the file it names, and it says why.

### Relationship to account-local Claude memory

Account-local memory (`~/.claude/.../memory/*.md`) **stays** — it is fast, personal, and
excellent. The rule that resolves the overlap: **anything another agent needs in order to not
repeat your work belongs in `agentos/`; anything that is about how *you* work stays local.**
Concretely, `metadata.type: project` and cross-session traps graduate to `DSC-*`; `user` and
`feedback` memories do not.

---

## §6 The hot plane / cold plane split

This is the single most important structural idea in this document, because it is what lets
the Agent OS coexist with two live control planes instead of competing with them.

| | **Hot plane** | **Cold plane** |
|---|---|---|
| Question | *Is it running right now?* | *What exists, why, and what's next?* |
| Owner | `control_plane/` SQLite (processes); hooks + `git worktree list` (sessions) | `agentos/` git records |
| Scope | one machine, sub-second, transactional | all machines, all repos, durable |
| Medium | SQLite, PIDs, lease tokens, heartbeats | Markdown files in git |
| Lifetime | minutes–hours | months–years |
| On crash | reconcile to LOST, retry | unchanged; it is the recovery input |

Traffic between them is **one-directional and event-shaped**: the hot plane emits a record into
the cold plane at exactly three lifecycle boundaries — workstream claimed, wave completed,
handoff written. The cold plane never calls into the hot plane. This keeps I1 true by
construction: a store that is only ever *written to* by the runtime cannot gate the runtime.

Choosing SQLite for the hot plane and git files for the cold plane is not inconsistency — it is
the same reasoning applied to two different problems. Leases and heartbeats need transactions
on one machine; org memory needs review, history, and conflict-free concurrent authorship.

---

## §7 Handoff architecture

Full specification: `MASTERMIND_AGENT_HANDOFF_PROTOCOL.md`. Architecture-level points:

The protocol **schematizes the best handoff shape already in the repo rather than inventing
one.** The strongest sampled example (`SCRIPT_IMPORT_PIN_BURNDOWN_CONTINUATION_HANDOFF_2026-08-09.md`)
uses: `§0 State` · `§1 What is LEFT (in order)` · `§2 Things that will bite the next session` ·
`§3 Bugs found (all repaired)` · `§4 Not in scope, do not adopt`. That is already almost exactly
the brief's requested shape — including the two sections that matter most and that weak handoffs
always omit: **Danger Areas** (§2) and **Do Not Redo** (§4). The protocol makes that structure
the required floor and adds machine-readable frontmatter.

Two design commitments:

- **The handoff is the recovery bundle.** The brief's PART XI question — *"where did this agent
  leave off?"* — is answered by the most recent handoff for a workstream, not by reconstructing
  from git. Sessions crash; the handoff is written at the same moment `ci_handoff.py` is already
  being run, so it costs one extra artifact at a boundary the session was already stopping at.
- **`do_not_redo` is a first-class field, not prose.** It is the single highest-leverage field
  in the schema: the org's own measurement is that 55–80% of external proposals duplicate work
  already built, in flight, or killed (DNR preamble). A machine-readable `do_not_redo` feeds the
  context compiler directly, so the next session is *told* before it starts.

---

## §8 Context compilation

**Do not build a new retrieval system. `scripts/context_index_query.py` already emits a cited
`context_packet.v1` with an `--mode adjudication`, and it already supports cross-project queries.**

The reason context compilation has been hard is not retrieval quality — it is that **there was
no join key.** Once a workstream record exists and names its own program, P0, decisions,
discoveries, owned paths, PRs, and landmines, compiling context for "Fix Prophet early-admission
gating" stops being a search problem and becomes a *graph walk that terminates*:

```
task text ──► context_index_query.py search      (existing, ranked, cited)
                        │
                        ▼
              nearest WS:<KEY>                   (new join key)
                        │
    ┌───────────────────┼──────────────────┬─────────────────┐
    ▼                   ▼                  ▼                 ▼
 program +         DEC-* cited        DSC-* cited       waves → PRs
 charter P0        (not superseded)   (not stale)       → active_builds.v1
    │                   │                  │                 │
    └───────────────────┴──────────────────┴─────────────────┘
                        ▼
              CONTEXT BUNDLE  (bounded, cited, omission-listed)
```

Three properties earn their place:

- **Bounded by construction.** The bundle is capped (default ~8k tokens) and each section has a
  budget. A bundle that would exceed it drops lowest-rank items and **says so** — an omission
  list, never a silent truncation.
- **Exclusion is explicit.** Superseded decisions, stale discoveries, and workstreams from other
  programs are excluded *by field*, not by relevance guessing. This is what the brief's PART VI
  asks for ("omit … old superseded decisions") and it is deterministic.
- **Everything is cited.** Every line carries `file:line` or a key, so the receiving session can
  open the primary artifact. A compiled bundle is testimony; the source is the evidence.

**No vector database in V1.** With 20–40 workstreams the graph walk dominates; embeddings would
add an index to maintain, a rebuild cadence, and a failure mode, in exchange for recall the
join already provides. Revisit only if a measured miss-rate justifies it — and the benchmark
harness for that already exists at `research/context_index/BENCHMARK_RESULTS.md`.

---

## §9 Ownership and collision prevention

**Census §6.3 is binding: no worker/session tracking service.** Sessions stay emergent;
FleetView is the product answer. This design honors that and still satisfies the brief's PART VII
goal, because the *goal* (don't do the same work twice) is separable from the *mechanism*
(a heartbeat service) the brief assumed.

Collision prevention is already three-layered and live:

1. **File collisions** — `build_active_build_map.py` computes overlapping changed files across
   open PRs, nightly.
2. **Worktree occupancy** — `git worktree list` shows every live checkout, branch, and lock. The
   org's own hard-won rule is that a collision check that reads only PRs and not worktrees is
   incomplete.
3. **Program boundaries** — `mastermind_programs.yml` `owns` / `does_not_own`.

Agent OS adds exactly one thing: an **advisory claim** on the workstream record.

```yaml
claim:
  by: claude/prophet-entry-timing-a1b2c3    # branch or worktree name
  at: 2026-08-12T14:00:00Z
  expires: 2026-08-12T22:00:00Z             # default +12h — session scale, not day scale
```

It is a **note, not a lock** (I1): it has no enforcement, blocks nothing, and expires by
wall-clock with no heartbeat, no daemon, and no liveness probe. A session reads claims before
starting and is *warned*; it is never stopped. An expired claim reports `unclaimed` — a stale
claim is a signal to look, not a blocker. This is the smallest thing that answers "is someone
already on this?" without becoming the session-tracking service the census forbids.

**What a claim can and cannot prevent — stated, because the difference is large.** A claim
is a file in a git repository, so it is unreadable by any other session until it MERGES:
PR, CI, and a sweeper cycle that runs every 10 minutes, unbounded when main is red. The
honest claim is therefore that it prevents **day-scale** collisions — "someone took this
workstream on Tuesday and is still on it" — and prevents **nothing** at the same-hour
scale. Same-hour collision prevention already comes free and instantly from
`git worktree list`, which is layer 2 above and needs no merge.

Two consequences follow. First, `expires` defaults to **12 hours**, not 72: a claim that
outlives the session that wrote it by three days describes a session that no longer
exists, and the org's own measured session scale is hours, not days. Second, `status`
joins each claim against live worktree occupancy and reports `worktree_live: false` when
the claiming branch has no checkout — a claim with no live worktree is the cheap,
immediate tell that the holder is gone, and it costs one local git call rather than a
heartbeat service.

---

## §10 Routing

**Do not build a router.** The routing law already exists as prose plus an executable guard:
Macro CLAUDE.md §Model routing (the tier table, the design lane, the build lane, the Fable
gate) enforced by `.claude/hooks/model_routing_guard.py`, which denies unrouted spawns.
Mastermind `config/agents.yml` seats the reasoning roles.

Agent OS contributes **inputs**, not a decision engine. Each workstream and wave carries three
declared dimensions:

| Dimension | Values | Drives |
|---|---|---|
| `class` | `research` · `build` · `design` · `adjudication` · `mechanical` | agent type (`builder` / `designer` / `reviewer` / `Explore`) |
| `blast_radius` | `reversible` · `user_facing` · `irreversible` | verification budget (fable-mode §2.2) and gating tier (§11) |
| `ambiguity` | `specified` · `scoped` · `open` | model tier; `open` + high blast radius is the Fable gate's actual signature |

A deterministic table maps these to the existing tiers — no ML, no learned router. The brief's
question *"what is the cheapest competent intelligence capable of doing this correctly?"* is
answered by a lookup. When the table and CLAUDE.md disagree, **CLAUDE.md wins**; the table is a
convenience view over the law, never a second law (P7).

---

## §11 GitHub, CI, runtime, and security boundaries

**GitHub (PART XIII).** Agent OS consumes; it never polls. `build_active_build_map.py` makes
**one** nightly authenticated sweep and writes `active_builds.v1`; every session reads that
local file. This is not a stylistic preference — the 5,000/hr REST `core` pool is a *single
shared bucket* across every parallel session, the sweeper, and the hooks, and
`ship_loop_guard.py` **fails closed** when rate-limited. Per-agent polling would block the very
Stop the polling was for. `gh_quota_guard.py` exists because this has already happened.

**CI waiting (PART X).** Already solved, and worth naming precisely because the brief lists it
as missing: `scripts/ci_handoff.py` releases the expensive session the moment its PR is armed
and proven-not-red; `.github/workflows/merge-on-green.yml` runs every 10 minutes on a
GitHub-hosted runner and squash-merges on concluded-clean. That is exactly *"expensive
intelligence active only when expensive intelligence is needed."* Agent OS adds one thing: the
handoff record written at the same boundary, so the *next* session resumes with context rather
than rediscovering it.

**Runtime truth (PART II).** Not this program's work. Agent OS defines only the interface: a
workstream may carry `runtime_ref` (deployed SHA, service, freshness artifact) pointing at the
runtime-truth program's artifacts. Agent OS never discovers runtime facts itself.

**Security tiers (PART XV).** Already exist and are not re-declared: Mastermind
`config/authority_map.yml` (A0–A7, cited as `authority_map.yml A<n>` — never bare `A<n>`, since
two ladders with colliding numbering exist per census §2.1), enforced by
`control_plane/executive_authority.py` for worker capability grants and `packet_gate.py` at the
chokepoint. On the fleet side: `ship_loop_guard.py`, `model_routing_guard.py`, `gh_quota_guard.py`.

Agent OS's own security surface is small and stated: it is **write-only-by-humans-and-sessions,
read-by-everyone, and gates nothing** (I1). Its `blast_radius` field is an *input* to those
existing gates. Per census §6.6, no new surface auto-arms: `agentos.py` ships in validate-and-
report mode, and any future enforcement is a separately recorded ruling.

---

## §12 Scaling to 20–50 workers

The brief's closing question is *"if Mastermind has 20–50 simultaneous AI workers, what is the
smallest control plane that lets one CEO direct the organization without becoming the
dispatcher?"* The scaling argument, property by property:

| Property | Mechanism | Why it holds at 50 |
|---|---|---|
| **Conflict-free writes** | one file per record (I2) | 50 sessions creating 50 distinct files merge trivially. No shared append target anywhere. |
| **No read amplification** | all reads are local file reads | Zero network per read. The 5,000/hr GitHub bucket is touched once nightly by one job, not 50× per hour by 50 workers. |
| **No central coordinator** | no daemon, no queue, no bus | Nothing to saturate, nothing whose failure stops the org. Git is the transport, and it already scales. |
| **CEO attention is O(1), not O(workers)** | `needs_ceo` is a declared field; the brief filters on it | 50 workers produce ~3 escalations, not 50 status lines. Suppression is by construction (§ CEO brief), not by summarization. |
| **Bounded per-agent context** | compiled bundles, capped and omission-listed (§8) | Adding workers does not grow any individual agent's context. |
| **Graceful degradation** | fail-open reads (I4) | A missing sibling repo or a rate-limited `gh` degrades the view; it never blocks a worker. |

**Where it would actually break, stated honestly:** the human-scale assumption is ~20–40 live
workstreams. At 200+, `AGENT_OS_STATE.md` stops being readable and the CEO brief needs
per-department rollups (census §5.8 declined these for MVP, correctly). That is a Phase-4
concern with a known answer — group by the 6 existing category-departments — and it is a
*view* change, not a storage change. The storage layer is indifferent to record count.

**The answer to the closing question, in one paragraph:** the smallest sufficient control plane
is *three planes, two of which already exist and must not be rebuilt* — the fleet law governing
Claude sessions, the Executive OS governing Codex processes, and a new thin knowledge plane
(~20–40 workstream records, minted-key decisions and discoveries, schema'd handoffs, one
generator, one CLI) that gives the two execution planes a shared vocabulary and gives the CEO
one generated page with a `needs_ceo` filter. The CEO stops being the dispatcher not because
work is auto-assigned, but because **the queue, the dependencies, and the escalations become
readable without reconstruction.** Total genuinely-new code: one directory of records, ~400 LOC
of validator/generator, and four schema files.

---

## §13 What NOT to build — and five conflicts the CEO must rule on

**Not building (settled by prior adjudication, restated so no future session re-proposes):**

1. **No third control plane.** Census §6.1. I1 is the structural guarantee.
2. **No session/worker tracking service.** Census §6.3. §9's advisory claim is the substitute.
3. **No new scheduler, queue, or bus.** Census §6.4. Git + the existing nightly are the transport.
4. **No vector database in V1.** §8; the join key makes it unnecessary until measured otherwise.
5. **No unified store that absorbs DNR, `governance.jsonl`, or masterplans.** Census §5.4. Agent
   OS adds the *missing* record types and cites the rest. P7 is satisfied because the concepts
   differ — DNR owns kills, Agent OS owns positive decisions.
6. **No auto-arming authority.** Census §6.6. `agentos.py` ships in report mode.
7. **No Kubernetes, no agent social network, no Git replacement, no speculative AI scheduler.**
   The brief's PART XVIII list, adopted verbatim.

**Five genuine conflicts. I am flagging rather than silently resolving them, because all
five are the Chairman's call. C4 and C5 were found by adversarial review of this document's
own first draft — C5 is a standing DNR kill the draft failed to cite at all:**

> **C1 — Task registry.** The brief (PART II, PART XVI) asks for a first-class Task entity with
> ~20 fields. Census §5.6 ruled sub-PR granularity unnecessary and a task queue an explicit
> non-goal. **My recommendation: side with the census** — waves-inside-workstreams (§3) deliver
> the dependency graph and next-action the brief actually needs, at roughly 4 fields instead of
> 20. **What would flip me:** if the CEO wants work items that exist *before* any PR and are
> assigned to specific workers by someone other than the worker, a real task store is required.
> That is a dispatcher, and it would need to live in `control_plane/`, not here.

> **C3 — Ranked work.** The CEO brief's START NEXT is a deterministic ranked list of next
> work. Mastermind `config/strategic_state.yml:16` assigns that concept to
> `brain/improvement_agenda.py` — "owns the ranked work queue" — inside a comment block
> that names Charter P7 as the reason the file exists, and census §5.3 calls the agenda
> "the only ranked, evidence-cited priority engine in the org". **My recommendation: keep
> START NEXT as a stated READINESS view and leave priority with the agenda.** They are
> different concepts computed from different inputs, and the brief now says so in prose on
> every render rather than presenting a rival ordering silently. **What would flip me:** if
> the CEO wants one list, it should be the agenda's, extended with a readiness column fed
> by `agent_os_state.v1` — that retires START NEXT here rather than duplicating it.
> Recorded with alternatives and evidence in
> `agentos/decisions/DEC-AGENTOS-START-NEXT-VS-AGENDA.md`.

> **C2 — Session tracking.** The brief (PART VII, PART XIV) asks for active-session tracking,
> heartbeats, and stale-task detection. Census §6.3 forbids a session tracking service and names
> FleetView as the product answer. **My recommendation: side with the census** — §9's advisory
> claim plus the live `git worktree list` and PR-collision machinery cover the actual goal.
> **What would flip me:** repeated real collisions that the claim + worktree check demonstrably
> failed to prevent. That is measurable; until it is measured, the heartbeat service is the more
> expensive guess.

> **C4 — Overriding census §5.4.** The census specified the mechanism for decision provenance —
> ~3 new event types on the existing `governance.jsonl` plus a citation convention — and stated
> **"Explicit non-goal: a new unified store."** `agentos/decisions/` overrides that. **My
> recommendation: confirm the override**, on the one ground in §0: `governance.jsonl` is not
> git-tracked (`control_plane/governance.py:70` → `data/governance/governance.jsonl`;
> `git ls-files` empty), so it is single-machine runtime state and cannot hold cross-machine org
> memory whatever event types it gains. **What would flip me:** a decision to make
> `governance.jsonl` git-tracked and replicated — then the census's mechanism is strictly
> simpler and `agentos/decisions/` should be retired into it.

> **C5 — Clearing `DNR:KILL-PARALLEL-KNOWLEDGE-BASE`.** A standing kill (CXI-R12, 2026-07-18)
> forbids "a second hand-maintained knowledge base … agents required to write session knowledge
> into a separate database". `DSC-*` is the closest thing here to that form, and **only the
> operator/Fable can clear a killed topic** — I cannot self-certify it. The argument is in §0:
> the records are canonical rather than parallel, retrieval stays with CXI, and G2 (account-local
> memory is unreadable to Codex) is new evidence the 2026-07-18 ruling could not have weighed,
> because CXI indexes repo content and account-local memory is not repo content. **Until ruled:
> Phase 0 stands, and Phase 1 must NOT mandate that sessions write `DSC-*`** — the mandate is
> precisely what the row forbids. **What would flip me:** a ruling that the CXI corpus plus
> masterplan prose is sufficient for cross-account knowledge, which would retire `DSC-*` and keep
> `DEC-*` and handoffs.

---

## §14 Dogfood — the current organization in this model

PART XVII's test: if the architecture cannot represent today's actual chaos, it is wrong. These
six workstreams are **seeded and validating** in `agentos/workstreams/` as of this PR — not a
worked example, the actual committed records:

| Workstream key | Program (real registry key) | P0 | Status | Waves | Needs CEO |
|---|---|---|---|---|---|
| `WS:AGENT-OS` | `project-active-build-control` | `EXECUTIVE_OS` | active | W0 ▶ · W1–W4 ◻ | **yes — C1 and C2** |
| `WS:PROPHET-US-ENTRY-TIMING` | `prophet-us` | `US_PROPHET_ENTRY_TIMING` | active | W0 ✅ · W1 ▶ · W2 ◻ | no |
| `WS:WATCHLIST-PORTFOLIO-CEO` | `terminal-user-services` | `PRODUCT_TRUST_COHERENCE` | active | W0 ✅ · P0-husk ✅ · W1 ◻ | **yes — persistence model** |
| `WS:GMI-THEME-GRAPH` | `gmi-theme-graph` | — | blocked | W0–W2 ✅ · W3 ◻ | no (external wait, on time) |
| `WS:CN-LIMIT-ALPHA` | `china-system` | — | blocked | W-P0 ✅ · P-A1 ⏳ · P-A2 ◻ | no (operator STOP-SHIP) |
| `WS:MACRO-CONTEXT-INDEX` | `macro-context-index` | — | active | W0 ✅ · W1 ▶ · W2 ◻ | no |

Four observations from doing this, which are themselves the validation:

1. **Every field populated from artifacts that already exist** — program registry keys, strategic
   state P0 ids, merged PR numbers, masterplan wave labels. Nothing required invention, which is
   the test that the model matches reality rather than a diagram.
2. **`needs_ceo` self-populated to 2 of 6.** That is the brief's PART IX suppression property
   demonstrated on real data, not asserted.
3. **The two `blocked` records are blocked for opposite reasons** — one on an external scrape
   arriving on schedule, one on a standing operator STOP-SHIP. Both are healthy. The CEO brief
   must distinguish "blocked and on time" from "blocked and rotting", which is why `blocked_by`
   is required prose rather than a boolean.
4. **The model refused to represent one workstream, and that was the right behavior.** The
   Executive OS — the org's largest live infrastructure program, five merged PRs and its own
   `control_plane/` module set — **has no row in the 59-program registry**, so no valid `program`
   parent exists for it. Rather than attach it to an approximate parent, the seeding stopped and
   recorded `DSC:EXECUTIVE-OS-NO-PROGRAM-ROW`. A validated foreign key caught a real registry
   gap on day one; that is the whole argument for making `program` a checked field.

---

## §15 Sequencing

Full detail with per-phase objectives, dependencies, agent class, and validation:
`MASTERMIND_AGENT_OS_V1_IMPLEMENTATION_PLAN.md`.

| Phase | Objective | Effort | Unlocks |
|---|---|---|---|
| **0** | Directory, 4 schemas, `agentos.py validate`, 6 seeded workstreams | ~1 day | The join key exists |
| **1** | Handoff protocol adopted; `DEC`/`DSC` written by live sessions | ~2 days | WHY and discoveries survive; G1/G2 closed |
| **2** | `agentos.py status` + generated state page + `mastermind status` brief | ~1 day | CEO reads one page; G5 closed |
| **3** | `compile-context` over the existing context index | ~2 days | Targeted bundles; G6 closed |
| **4** | Hook auto-capture at ship-loop boundaries | ~1 day | Friction → near zero |

Phases 1–3 are parallelizable across sessions once Phase 0 lands. **Phase 0 is the only
blocking dependency**, and it is deliberately small enough to be one PR.

---

## §16 Open questions

1. **C1 (task registry) and C2 (session tracking)** — §13. Chairman's call; both default to the
   census position until ruled otherwise.
2. **Cross-repo write ergonomics.** Terminal and Mastermind sessions must write records into the
   Macro checkout. Phase 0 uses a path-resolved CLI. If that proves frictional in practice, the
   fallback is per-repo `agentos/` directories with a merge step at generation — strictly worse
   for P7, so it is a fallback and not the plan.
3. **Handoff enforcement.** Should `ship_loop_guard.py` eventually *require* a handoff record for
   a workstream-claimed session? Per census §6.6, not in V1 — report-mode first, and enforcement
   only as a separately recorded ruling once the format has proven itself in use.
