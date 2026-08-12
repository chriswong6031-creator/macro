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
   already mis-resolved in this org (2026-08-05).
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
   Never hand-edit them.

---

## Validate

```bash
python3 scripts/agentos.py validate
```

Exit 1 on a malformed record (**fail-closed on schema** — a bad record is a lie about the
organization). Exit 0 with warnings on a missing join input (**fail-open on join** — a missing
sibling repo or a rate-limited `gh` must never red the nightly).

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
wall-clock with no heartbeat. An expired claim reports `unclaimed` — a signal to look, not a
takeover.

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
