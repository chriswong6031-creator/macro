# `mastermind status` — CEO brief specification

Status: **SPEC (proposed)**. Deliverable 5 of the Agent OS handoff.
Implemented by `scripts/agentos.py brief` in Phase 2.

---

## §0 Design law

> **The brief's job is suppression, not summarization.**

A summary of 50 workers is 50 lines the CEO must read. A brief is ~15 lines because most of what
happened does not require the CEO — and the system can *tell*, because `needs_ceo` is a declared
field on the workstream record, not a judgment made at render time.

Four rules:

1. **Escalation is authored, never inferred.** A workstream appears under WHAT NEEDS YOU only if
   its owning session wrote a `needs_ceo` block. No heuristic promotes anything. This is what
   keeps the section at 2–3 items with 50 workers instead of 20.
2. **Autonomous progress is counted, not narrated.** "9 progressing autonomously" is one line.
   The detail is one command away and stays there.
3. **Every claim carries its source.** A brief line that cannot be opened is a rumor.
4. **Degraded inputs are stated.** A brief that silently omits a repo it could not read looks
   identical to a brief where nothing is happening. That is the single most dangerous possible
   failure of this artifact, and I4 exists for it.

---

## §1 Invocation

```bash
python3 scripts/agentos.py brief                      # since last invocation
python3 scripts/agentos.py brief --since 24h          # or 1h / 7d / overnight / 2026-08-11
python3 scripts/agentos.py brief --full               # include autonomous detail
python3 scripts/agentos.py brief --json               # ceo_brief.v1
python3 scripts/agentos.py brief --now <iso>          # freeze the clock (reproducibility)
python3 scripts/agentos.py brief --no-remember        # do not record this check-in
python3 scripts/agentos.py brief --scan-uncommitted   # add the per-worktree dirty scan
```

`--scan-uncommitted` is OPT-IN because it costs one `git status` per checkout: measured
276 live worktrees on the primary host, most carrying a multi-GB `data/` tree, which put
a plain `brief` past 120 seconds. Its absence is stated in `degraded` rather than
silently skipped — a CEO command nobody waits for is a CEO command nobody runs.

Reads only local artifacts: `agentos/`, `data/governance/active_builds.json`, `git worktree list`,
`git log`. **No network call, no GitHub API hit** — the freshness of PR state is inherited from
the nightly ABM sweep. This is deliberate: the 5,000/hr REST bucket is shared across every
session and hook, and `ship_loop_guard.py` fails closed when it is exhausted. A CEO command that
could contribute to blocking the fleet would be a bad trade for a few minutes of freshness.

`--since` with no value uses the timestamp of the previous invocation, stored in
`data/governance/.ceo_brief_last` — so "what changed since I last looked" is the default question.

---

## §2 Exact output — REGENERATED FROM THE STORE, not hand-written

Reproduce it exactly:

```bash
python3 scripts/agentos.py brief --now 2026-08-12T14:00:00Z --since 7d --no-remember
```

```
MASTERMIND STATUS — 2026-08-12 14:00 UTC
since the last 7d (2026-08-05 14:00 UTC, 168h ago)

  6 workstreams:  4 active · 0 awaiting CI · 2 blocked · 0 done this window
  Inputs: active_builds 36h old · 244 worktrees
  ⚠ DEGRADED (4) — this brief is incomplete:
      active_builds.v1 merged window is TRUNCATED — a merged PR may
      read 'unknown'
      mastermind:config/strategic_state.yml absent from the working
      tree and all local refs — p0 ids unvalidated, P0 ranking
      neutral (this Mastermind clone predates config/strategic_state.yml)
      uncommitted-work scan skipped over 244 worktrees (one `git
      status` each) — re-run with --scan-uncommitted for stranded
      work
      active_builds.v1 is 36h old — PR state predates the last
      nightly sweep

━━ WHAT NEEDS YOU ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 1. WS:WATCHLIST-PORTFOLIO-CEO — blocks 1 wave(s)
    Portfolio and Watchlist persistence: one table or two?
      A) Single positions table with a kind discriminator  ← recommended
      B) Separate tables, joined at read time
    Recommendation:
      Single positions table with a kind discriminator. Terminal
      /portfolio currently has zero portfolio_positions
      references, so the migration cost is near zero today and
      rises once W1 ships against either shape.
    Wanted by 2026-08-14
    → agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md
 2. WS:AGENT-OS — blocks 5 wave(s)
    Three conflicts. C1 — task registry: the brief asks for a
    first-class Task entity; census §5.6 ruled sub-PR granularity
    a non-goal. C2 — session tracking: the brief asks for
    heartbeats and stale-task detection; census §6.3 forbids a
    session-tracking service. C3 — ranked work: the CEO brief's
    UNBLOCKED is a ranked next-work list, and
    config/strategic_state.yml:16 gives that concept to
    brain/improvement_agenda.py.
      A) Side with the census on C1/C2; keep UNBLOCKED as readiness-only on C3
      B) Override the census: build a real task store and a session registry
      C) Fold readiness into the improvement agenda and retire UNBLOCKED here
    Recommendation:
      Side with the census on both. Waves supply the dependency
      graph and next-action the brief actually needs at ~4
      fields instead of 20; the advisory claim plus git worktree
      list and PR-collision data cover the collision goal.
      Override C1 only if you want work items assigned to
      workers by someone other than the worker — that is a
      dispatcher, and it belongs in control_plane/.
    Wanted by 2026-08-19
    → agentos/workstreams/WS-AGENT-OS.md

━━ BLOCKED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 • WS:CN-LIMIT-ALPHA — China limit-up alpha research
   STOP-SHIP held since 2026-08-10 by operator ruling: grade
   NEITHER arm, and never cite the pre-charter research waves
   (see the landmine below for what those are).
 • WS:GMI-THEME-GRAPH — Global Market Intelligence theme graph
   Waiting on the scheduled Saturday 2026-08-15 scrape. External
   dependency, on time — not stalled.

━━ RUNNING (no action needed) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 4 active · 0 awaiting CI · 0 awaiting review · 0 proposed.
 0 open PR(s) cited by a wave. 0 stale claim(s); 0 claim(s) with no live worktree.
                                     → agentos.py brief --full

━━ UNBLOCKED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 Readiness only — which waves CAN start (dependencies satisfied).
 It is NOT the company's priority order:
 brain/improvement_agenda.py owns the ranked work queue (Charter
 P7). Ask that list what matters most; ask this one what is
 unblocked.

 1. WS:WATCHLIST-PORTFOLIO-CEO W1 — Persistence model implementation
    agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md

 1 hygiene warning(s) — agentos.py brief --full
```

**Why this section is generated and not illustrated.** The hand-written version of this
section shipped three defects that a regenerated one cannot have: a `WS:EXECUTIVE-OS`
line for a workstream that does not exist in the store, workstream keys truncated to fit
the column, and `blocks_waves: 2` against a single real queued wave. A worked example
that disagrees with the artifact is worse than no example, because it teaches the reader
a shape the tool does not produce. Regenerate this block whenever the format changes.

**Read the DEGRADED block as part of the output, not as noise.** The run above was taken
on a developer machine where `active_builds.json` was 36h stale, the Mastermind sibling
checkout carried no `strategic_state.yml`, and the worktree scan was skipped. Every one
of those facts is printed. That is §0 rule 4 working: the same brief with those lines
suppressed would be indistinguishable from a brief where nothing is happening.

---

## §3 Section contracts

| Section | Source | Ordering | Cap | Omitted when |
|---|---|---|---|---|
| Header counts | `agent_os_state.v1` | — | — | never |
| Inputs line | generator `inputs` block | — | — | never — staleness is load-bearing |
| **WHAT NEEDS YOU** | `needs_ceo` present | `by_when`, then unfinished-wave count | 5 + overflow line | empty → "Nothing needs you." |
| BLOCKED | `status: blocked` | `record_stale_days` desc | 5 + overflow line | empty |
| FINISHED | waves→`done` in window | recency | 8 + overflow line | empty |
| RUNNING | everything else | — | rolled to counts | never |
| UNBLOCKED | `todo` waves, deps satisfied | P0 alignment, then unblock-count | 3 + overflow line | empty |

**UNBLOCKED ranking**, in order: (1) all `depends_on` satisfied; (2) maps to an active P0 in
`strategic_state.yml`; (3) unblocks the most other waves; (4) not currently claimed. Deterministic
— no model in the loop, so the brief is reproducible and arguable.

**UNBLOCKED is NOT the company's ranked work queue, and the section says so on every
render.** Charter P7 (one source of truth per concept) gives the ranked-queue concept to
Mastermind `brain/improvement_agenda.py`, and census §5.3 calls it "the only ranked,
evidence-cited priority engine in the org". Readiness and priority are different
concepts with different inputs — readiness comes from the wave dependency graph, which
only Agent OS holds; priority comes from accountability-fused evidence, which only the
agenda holds. A wave can be perfectly ready and correctly last in line. The failure P7
guards against is two lists that both claim to answer the same question and disagree, so
the fix is that each list states its question: a fixed scope line renders above the
items in both the text and JSON forms (`unblocked_scope`), and the direction of truth
is stated — **priority wins; UNBLOCKED is only telling you the work is startable.**
Full reasoning, alternatives, and what would reverse it:
`agentos/decisions/DEC-AGENTOS-START-NEXT-VS-AGENDA.md`. Escalated as conflict **C3**.

Deriving the section from the agenda instead was rejected on evidence: `data/agenda/` is
gitignored and VPS-authoritative, absent in a fresh checkout, and the alternative read
path is the live VPS API — which would break the zero-network contract in §1 for the
sake of a list this command is not trying to produce.


### Two contracts the first implementation broke, now pinned by test

**Every capped section names what it dropped.** A brief that prints 5 of 7 blocked
workstreams and says nothing reads exactly like a brief where only 5 are blocked. Each
capped section emits `… +N more <noun> (--full)`, and `--full` renders the complete list.
Only `needs_ceo` had this originally; the other three truncated silently.

**`record_stale_days`, not `blocked_days`.** The blocked ordering is by days since the
record file was last committed — all that is derivable without an authored `blocked_since`.
Calling it "days blocked" and the ordering "longest blocked first" claimed a measurement
nobody took: a record edited yesterday for an unrelated reason read as freshly blocked.

**The `← recommended` arrow is exact, never inferred by substring.** An option is marked
only when the recommendation OPENS with it and exactly one option qualifies; ambiguous prose
gets no arrow. The substring form marked the REJECTED option whenever the prose named it in
order to reject it — and the arrow is the thing the CEO acts on.

---

## §4 `--full`

Adds, below RUNNING: every active workstream as one line (`key · owner · wave · next_action ·
claim age`); every open PR grouped by workstream with CI state; collision warnings from
overlapping `owns_paths`; and hygiene warnings (stale claims, uncited discoveries past 90d,
decisions past `review_by`).

---

## §5 `--json` — `ceo_brief.v1`

```json
{
  "schema": "ceo_brief.v1",
  "generated_at": "2026-08-12T14:00:00Z",
  "since": "2026-08-11T19:30:00Z",
  "counts": {"total": 24, "active": 16, "awaiting_ci": 3, "blocked": 2, "done_in_window": 3},
  "inputs": {"active_builds_age_hours": 8, "worktrees": 31, "degraded": []},
  "needs_ceo": [
    {"workstream": "WATCHLIST-PORTFOLIO-CEO",
     "question": "Portfolio and Watchlist persistence: one table or two?",
     "options": ["Single positions table + kind discriminator", "Separate tables, join at read time"],
     "recommendation": "Single positions table + kind discriminator",
     "by_when": "2026-08-14", "blocks_waves": 2,
     "source": "agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md"}
  ],
  "blocked": [...], "finished": [...], "unblocked": [...],
  "warnings": []
}
```

Machine form exists so the brief can later be delivered by other transports (a scheduled task, a
push notification, a dashboard) **without re-deriving any of this logic** — one generator, many
renderers. P7.

---

## §6 Failure modes this format is built against

| Failure | Guard |
|---|---|
| Brief grows with worker count | Only `needs_ceo` reaches the top section; everything else rolls to counts (§0.1) |
| Stale data reads as "quiet" | Inputs line always prints artifact ages; `degraded` is never suppressed |
| Everything looks urgent | Escalation is authored, not inferred — a session must deliberately write `needs_ceo` |
| CEO becomes the dispatcher | UNBLOCKED is *unblocked work*, not assignments. Nothing is assigned to anyone. |
| Brief burns GitHub quota | Zero network calls; PR state inherited from the nightly sweep (§1) |
| Brief disagrees with reality | Every line cites a file or PR the CEO can open; the artifact wins over the summary |
| Two ranked lists disagree | UNBLOCKED renders its scope line every time and defers to the improvement agenda on priority (§3, `DEC:AGENTOS-START-NEXT-VS-AGENDA`) |
| Record says one thing, execution did another | `record_disagrees_with_execution` warnings: a wave not `done` behind a merged PR, or a `waves[].pr` absent from `active_builds.v1` |
| Worked example drifts from the tool | §2 is regenerated from the store by a printed command, never hand-written |
