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
python3 scripts/agentos.py brief --now 2026-08-14T19:00:00Z --since 7d --no-remember \
  | sed -E 's/[0-9]+ worktrees/<live> worktrees/g'
```

```
MASTERMIND STATUS — 2026-08-14 19:00 UTC
since the last 7d (2026-08-07 19:00 UTC, 168h ago)

  13 workstreams:  12 active · 0 awaiting CI · 1 blocked · 7 done this window
  Inputs: active_builds 16h old · <live> worktrees
  ⚠ DEGRADED (3) — this brief is incomplete:
      active_builds.v1 merged window is TRUNCATED — a merged PR may
      read 'unknown'
      mastermind:config/strategic_state.yml absent from the working
      tree — read from local ref origin/HEAD (stale Mastermind
      checkout; p0_active uses the ref copy)
      uncommitted-work scan skipped over <live> worktrees (one `git
      status` each) — re-run with --scan-uncommitted for stranded
      work

━━ WHAT NEEDS YOU ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 1. WS:WATCHLIST-PORTFOLIO-CEO — 1 unfinished wave(s)
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

━━ BLOCKED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 • WS:GMI-THEME-GRAPH — Global Market Intelligence theme graph
   Waiting on the scheduled Saturday 2026-08-15 scrape. External
   dependency, on time — not stalled.

━━ FINISHED (the last 7d) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 ✅ WS:AGENT-OS W1 — Phase 1 — adoption: CLAUDE.md/AGENTS.md sections, handoff protocol in use, <=10 backfilled decisions  #5556
 ✅ WS:AGENT-OS W0 — Architecture + Phase 0 scaffolding (schemas, validator, seeded records)  #5472
 ✅ WS:AGENT-OS W2 — Phase 2 — status generator + mastermind status CEO brief  #5472
 ✅ WS:GMI-THEME-GRAPH R1 — R1 answered (#5402)  #5402
 ✅ WS:WATCHLIST-PORTFOLIO-CEO P0-HUSK — P0 husk cured — 6-file shell, graded plane walled, shim trap closed  #5463
 ✅ WS:WATCHLIST-PORTFOLIO-CEO W0 — Initial revamp shipped  #5457
 ✅ WS:PROPHET-US-ENTRY-TIMING W0 — Queue drain + backfill  #5370

━━ RUNNING (no action needed) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 12 active · 0 awaiting CI · 0 awaiting review · 0 proposed.
 1 open PR(s) cited by a wave. 0 stale claim(s); 0 claim(s) with no live worktree.
                                     → agentos.py brief --full

 10 hygiene warning(s) — agentos.py brief --full

```

**Why this section is generated and not illustrated.** The hand-written version of this
section shipped three defects that a regenerated one cannot have: a `WS:EXECUTIVE-OS`
line for a workstream that does not exist in the store, workstream keys truncated to fit
the column, and `blocks_waves: 2` against a single real queued wave. A worked example
that disagrees with the artifact is worse than no example, because it teaches the reader
a shape the tool does not produce. Regenerate this block whenever the format changes.

**Current source truth.** This block was regenerated from the Phase 2b closeout worktree and
authored store on 2026-08-14 by the printed pinned pipeline; it is not a hand-adjusted illustration.
The pipeline normalizes only the volatile live-worktree census so the promised exact replay
does not change when an unrelated checkout is added or removed.
The parent brief's DEGRADED block truthfully records a truncated PR join, P0 read from the
Mastermind clone's local ref, and the intentionally skipped deep worktree scan. Those auxiliary
facts do not contaminate the machine-only `readiness.degraded` envelope. Regenerate the whole
block whenever the format or authored store changes.

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

**Readiness is machine-only in this brief.** Charter P7 gives the ranked-queue concept to
Mastermind `brain/improvement_agenda.py`. The text renderer therefore emits no readiness
list. Both JSON views carry the same non-ranked `agentos.readiness.v1` envelope for the agenda
to consume: one record for each workstream (`wave: null`) and wave, sorted only by identity.
The record has exactly `workstream`, `wave`, `state`, `reason_code`, `reason`, `depends_on`,
`unmet_dependencies`, and `source`; the envelope has exactly `schema`, `records`, and
`degraded`. No P0, claim, unblock-count, next-action, or priority field is admitted.

Dependencies retain their authored graph identity: `WS:<KEY>` for workstream dependencies and
`WS:<CURRENT>#<WAVE>` for local wave dependencies. A wave's effective dependency set is the
canonical sorted union of its parent workstream edges and authored local edges.
`unmet_dependencies` is a subset of that union; terminal workstreams (`done`, `killed`) and
waves (`done`, `dropped`) retain dependency provenance but report no unmet dependencies.
`readiness.degraded` names only invalid or ambiguous workstream authoring that excluded or
invalidated an identity. Auxiliary PR/P0/worktree degradation remains in parent
`inputs.degraded`. The agenda
must treat an excluded or duplicate dependency source as unavailable, not ordinarily unmet:
the ambiguous identity/waves and surviving proposed/todo dependents emit `unknown` /
`status_unknown`, with the canonical dependency named. The agenda may combine this input with
its own evidence, but Agent OS does not order the records by importance. Full ruling:
`DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA`.


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
  "blocked": [...], "finished": [...],
  "readiness": {
    "schema": "agentos.readiness.v1",
    "records": [
      {"workstream": "WATCHLIST-PORTFOLIO-CEO", "wave": null,
       "state": "in_progress", "reason_code": "status_in_progress",
       "reason": "Authored workstream status is active.",
       "depends_on": [], "unmet_dependencies": [],
       "source": "agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md"},
      {"workstream": "WATCHLIST-PORTFOLIO-CEO", "wave": "W1",
       "state": "ready", "reason_code": "dependencies_satisfied",
       "reason": "All declared dependencies are done.",
       "depends_on": ["WS:WATCHLIST-PORTFOLIO-CEO#P0-HUSK"],
       "unmet_dependencies": [],
       "source": "agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md"}
    ],
    "degraded": []
  },
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
| CEO becomes the dispatcher | Human brief renders no readiness list; the machine envelope is read-only input and assigns nothing. |
| Brief burns GitHub quota | Zero network calls; PR state inherited from the nightly sweep (§1) |
| Brief disagrees with reality | Every line cites a file or PR the CEO can open; the artifact wins over the summary |
| Two ranked lists disagree | Only the improvement agenda renders a ranked queue; readiness records are identity-sorted and contain no ranking inputs (§3, `DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA`) |
| Record says one thing, execution did another | `record_disagrees_with_execution` warnings: a wave not `done` behind a merged PR, or a `waves[].pr` absent from `active_builds.v1` |
| Worked example drifts from the tool | §2 is regenerated from the store by a printed command, never hand-written |
