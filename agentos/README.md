# `agentos/` — the Mastermind Agent OS knowledge plane

**Read this before writing anything here.** Architecture:
[`research/MASTERMIND_AGENT_OS_ARCHITECTURE.md`](../research/MASTERMIND_AGENT_OS_ARCHITECTURE.md).

---

## What this is

The organization's durable answer to four questions:

| Question | Record | Directory |
|---|---|---|
| What work exists, who owns it, what's next? | **Workstream** | `workstreams/WS-<KEY>.md` |
| Why did we choose this? | **Decision** | `decisions/DEC-<KEY>.md` |
| What did we learn about the system? | **Discovery** | `discoveries/DSC-<KEY>.md` |
| Where did the last session leave off? | **Handoff** | `handoffs/<WS-KEY>-<date>.md` |

## What this is NOT

> **It never decides whether something may run.**

No gate, no lease with teeth, no dispatch, no scheduler, no authority grant. That is
architecture invariant **I1**, and it is the reason this store is not a second control plane.
Execution is owned by two live planes that already exist and must not be rebuilt:

- **Claude Code sessions** → Macro `.claude/hooks/`, `scripts/ci_handoff_contract.py`,
  `.github/workflows/merge-on-green.yml`
- **Codex worker processes** → Mastermind `control_plane/` (`executive_runtime.py` and siblings)

If a change here would let `agentos/` block or start execution, it belongs in one of those,
not here.

---

## Rules

1. **One record per file.** Never append two records to one file — with 20–50 concurrent
   workers a shared append target is a guaranteed merge conflict. New files merge cleanly.
2. **Keys are UPPER-KEBAB, unique, and never reused or renumbered.** Cite as `WS:<KEY>`,
   `DEC:<KEY>`, `DSC:<KEY>` — **never** by row or line number. Row-number citations have
   already mis-resolved in this org (2026-08-05). **The colon is not decoration:** a bare
   `depends_on: [FOO]` is a hard error, because the tolerant version dropped the edge
   silently (0 errors, 0 warnings) and left the dependency graph quietly incomplete.
3. **Frontmatter is machine truth; the body is human truth.** Both in one file so they cannot
   drift apart.
4. **Every factual claim carries provenance** — `verified_by` naming a command, a `file:line`,
   or a PR.
5. **Decisions are superseded, never deleted.** Set `superseded_by` on the old record and
   `supersedes` on the new one. Both survive; that is how "why does this exist?" stays
   answerable.
6. **Discoveries need both admission gates** — a `falsifier` (what would disprove it) and a
   `so_what` (what a future session does differently). Missing either means it is a log line,
   not memory.
7. **`docs/AGENT_OS_STATE.md` and `data/governance/agent_os_state.json` are generated.**
   Never hand-edit them. The **nightly is the only regenerator** — do not add a drift guard
   that makes every record-touching PR commit a regenerated copy, which would put two
   independent record edits into conflict on a shared file (see
   `decisions/DEC-AGENTOS-NIGHTLY-IS-THE-ONLY-REGENERATOR.md`).
8. **Do not write `created` or `updated`.** They are derived from `git log` by the
   generator. Hand-typing them made every session rewrite the same line and made
   staleness circular.

---

## Validate

```bash
python3 scripts/agentos.py validate
```

Exit 1 on a **malformed** record (fail-closed on schema — a bad record is a lie about the
organization). Exit 0 with warnings on a missing join input (fail-open on join — a missing
sibling repo must never red the nightly).

**Work STATE never hard-fails.** `validate` runs unscoped on every PR in the fleet, over the
whole store, so a hard rule keyed on state would be a fleet-wide gate on a knowledge record —
and it is reachable with no bad record anywhere: two sessions each marking a different wave
done merge cleanly and the merged tree used to exit 1. Status-vs-wave rollup,
`blocked`/`blocked_by` pairing, staleness, claim expiry and record-vs-execution disagreement
are all warnings, reported by `status` and `brief`.

---

## Read the state

```bash
python3 scripts/agentos.py status          # writes both generated artifacts
python3 scripts/agentos.py status --dry-run
python3 scripts/agentos.py brief           # the CEO view
python3 scripts/agentos.py brief --full --since 7d
python3 scripts/agentos.py brief --json    # ceo_brief.v1

python3 scripts/agentos.py compile-context --workstream PROPHET-US-ENTRY-TIMING
python3 scripts/agentos.py compile-context "reduce prophet late entry" --text --budget 4000
```

`compile-context` is what a session picking up work should read first: a **bounded,
cited, read-only** `context_bundle.v1` — higher law (DNR rows, the P0, the program row)
above the workstream state, then current decisions, fresh discoveries, the latest
handoff, and artifact pointers, with every excluded, budget-omitted and unreadable input
named rather than silently dropped. It exits **0** with honest degradation (an ambiguous
task, an unbuilt index, an absent sibling repo, a citation that no longer resolves, and —
for a free-text task — an absent store all report and carry on) and exits 1 only when
`--workstream` NAMES a workstream that does not exist, whose OWN frontmatter is malformed,
or whose store is absent. Naming is an assertion and gets the strict answer; free text is a
question and gets an honest one.

`token_estimate` prices the whole payload — every item's citation fields, not just its
prose, plus the `excluded`/`omitted_due_to_budget`/`degraded` tails — so it may exceed
`--budget`: the workstream block, higher law and those tails are never dropped. Whenever it
does, the overrun and its composition are named in `degraded`, so the number is never bare.

Both `status` and `brief` **always exit 0** (invariant I1), and all three make **zero
network calls**: PR state comes only
from the local `data/governance/active_builds.json` written by the nightly ABM sweep. The
5,000/hr REST bucket is shared with `ship_loop_guard.py`, which fails CLOSED when it is
exhausted, so a status command that burned quota could block the Stop it was reporting on.
Anything unreadable still lands in the parent view's `inputs.degraded` and is printed,
never suppressed. The narrower readiness envelope does not inherit unrelated join health.

Both machine views carry the same non-ranked `readiness` envelope:

```json
{"schema": "agentos.readiness.v1", "records": [...], "degraded": [...]}
```

It emits one identity-sorted record for each workstream (`wave: null`) and each wave.
Records contain only `state`, `reason_code`/`reason`, canonical authored dependency refs,
unmet refs, and `source`; they contain no P0, claim, unblock-count, next-action, or ranking
field. Workstream dependencies are `WS:<KEY>` and local wave dependencies are
`WS:<CURRENT>#<WAVE>`; a wave's effective `depends_on` is the union of its parent
workstream edges and its authored local wave edges. Terminal workstreams (`done` or `killed`)
and terminal waves (`done` or `dropped`) report state `done` and no unmet dependencies while
retaining those authored edges as provenance. The envelope's `degraded` names only invalid
or ambiguous workstream authoring that removes or invalidates a readiness identity.
Missing/truncated PR state, P0 context, and worktree occupancy remain visible in parent
`inputs.degraded` but cannot make the graph-only feed look incomplete. An excluded or duplicate
dependency source is not confidently "unmet":
its own retained identity (if any), its waves, and surviving proposed/todo dependents emit
`unknown` / `status_unknown` with the unavailable canonical dependency named. The human brief
deliberately renders no readiness list. Mastermind's
improvement agenda consumes the envelope and remains the sole ranked queue
(`DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA`).

---

## Writing a record

Copy the nearest existing record and edit it. Field tables and worked examples live in
[`research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`](../research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md);
machine mirrors are in `schema/`.

**Steady-state cost is 1–2 fields at a wave boundary** (`status`, `next_action`). Everything
heavier is written at a moment you were already stopping to write prose — minting a decision as
you make it, or writing a handoff where you already run `ci_handoff.py`.

### Before starting work

```bash
grep -rl "owns_paths" agentos/workstreams/ | xargs grep -l "<the path you intend to touch>"
git worktree list        # a PR-only collision check is incomplete
```

A `claim` on a workstream is **advisory**: it warns you, it never stops you, and it expires by
wall-clock with no heartbeat. An expired claim reports `no claim note` — a signal to look, not a
takeover.

**Never present a claim note as live activity (Chairman ruling C2, 2026-08-12).** It is an
author's note in git, not evidence that anyone is working right now. Live worker and job state
belongs to the Executive OS runtime (`control_plane/`), which holds the real lease tokens and
heartbeats; same-hour occupancy evidence is `git worktree list`. A surface may **display** those;
it must never compute or arbitrate liveness itself — that would be the second runtime authority
invariant I1 exists to prevent. See `decisions/DEC-AGENTOS-CLAIMS-ARE-NOT-LIVE-ACTIVITY.md`.

**Know what a claim can actually prevent.** It is a file in git, so no other session can read
it until it MERGES — PR, CI, and a sweeper cycle that runs every 10 minutes and is unbounded
when main is red. It prevents **day-scale** collisions and prevents **nothing** at the
same-hour scale; `git worktree list` above is what covers the same hour, instantly and for
free. That is why `expires` defaults to +12h rather than +72h, and why `status` reports
`worktree_live: false` when a claiming branch has no live checkout.

---

## Relationship to the stores that already exist

| Store | Owns | Agent OS relationship |
|---|---|---|
| `config/mastermind_programs.yml` | 59 programs, the org chart | **parent key** — workstreams cite it, never restate it |
| Mastermind `config/strategic_state.yml` | company phase, 5 P0 objectives | **strategy key** — workstreams cite `p0:` |
| `research/DO_NOT_REBUILD.md` | kills, laws, holds (`DNR:<KEY>`) | **sibling** — DNR keeps kill authority; a killing decision writes both |
| `docs/ACTIVE_BUILD_MAP.md` / `active_builds.v1` | open PRs, collisions, merges | **imported** — joined at generation; Agent OS never polls GitHub |
| `research/*MASTERPLAN*` / `*HANDOFF*` | deep prose | **pointed at** via `artifacts:` — never migrated |
| Account-local Claude memory | how *you* work | stays local; cross-session facts graduate to `DSC-*` |
| Mastermind `brain/improvement_agenda.py` | **the** ranked "what should we do next?" queue | **canonical for priority** — Agent OS feeds it the non-ranked `agentos.readiness.v1` envelope; the human brief renders no competing list (`DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA`) |
| Mastermind `control_plane/` | live worker/job state, leases, heartbeats | **canonical for liveness** — display it, never re-derive it (`DEC:AGENTOS-CLAIMS-ARE-NOT-LIVE-ACTIVITY`) |
