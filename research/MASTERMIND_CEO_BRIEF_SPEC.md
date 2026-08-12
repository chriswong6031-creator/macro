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
python3 scripts/agentos.py brief --since 24h          # or 1h / overnight / 2026-08-11
python3 scripts/agentos.py brief --full               # include autonomous detail
python3 scripts/agentos.py brief --json               # ceo_brief.v1
```

Reads only local artifacts: `agentos/`, `data/governance/active_builds.json`, `git worktree list`,
`git log`. **No network call, no GitHub API hit** — the freshness of PR state is inherited from
the nightly ABM sweep. This is deliberate: the 5,000/hr REST bucket is shared across every
session and hook, and `ship_loop_guard.py` fails closed when it is exhausted. A CEO command that
could contribute to blocking the fleet would be a bad trade for a few minutes of freshness.

`--since` with no value uses the timestamp of the previous invocation, stored in
`data/governance/.ceo_brief_last` — so "what changed since I last looked" is the default question.

---

## §2 Exact output — current Mastermind workstreams, 2026-08-12

```
MASTERMIND STATUS — 2026-08-12 14:00 UTC
since your last check-in (2026-08-11 19:30 UTC, 18h ago)

  24 workstreams:  16 active · 3 awaiting CI · 2 blocked · 3 done this window
  Inputs: workstreams@14:00 · active_builds@06:00 (8h old) · 31 worktrees

━━ WHAT NEEDS YOU ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 1. WS:WATCHLIST-PORTFOLIO-CEO — product decision, blocks W1
    Portfolio and Watchlist persistence: one table or two?
      A) Single positions table + kind discriminator  ← recommended
         Terminal /portfolio already has zero portfolio_positions references,
         so the migration cost is near zero today and rises once W1 ships.
      B) Separate tables, join at read time
    Wanted by 2026-08-14 · 2 waves queued behind this
    → agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md

 2. WS:AGENT-OS — scope ruling, blocks Phase 1
    Two conflicts between your Agent OS brief and the merged Phase 0 census:
      C1  Task registry: brief asks for one, census §5.6 ruled it a non-goal.
          Recommend siding with the census (waves inside workstreams).
      C2  Session tracking: brief asks for heartbeats, census §6.3 forbids
          the service. Recommend the advisory claim instead.
    → research/MASTERMIND_AGENT_OS_ARCHITECTURE.md §13

━━ BLOCKED ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 • WS:CN-LIMIT-ALPHA — STOP-SHIP held since 08-10, by your ruling.
   W1–W3 must not be cited. P-A2 is accrual-gated. Not stale; holding correctly.
 • WS:GMI-THEME-GRAPH — waiting on the Sat 2026-08-15 scrape. External, on time.

━━ FINISHED (18h) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 ✅ WS:EXECUTIVE-OS         1C-A secure launchd supervisor        #25
 ✅ WS:WATCHLIST-PORTFOLIO  P0 husk cured — 6-file shell          #5463
 ✅ WS:PROPHET-US           queue drained, backfill complete      #5370

━━ RUNNING (no action needed) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 16 active · 9 progressing autonomously · 3 awaiting CI (2 armed
 merge-on-green, 1 in packs) · 4 awaiting review.
 Oldest unmerged armed PR: 4h. No stale claims.
                                          → mastermind status --full

━━ START NEXT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 1. WS:PROPHET-US W2 — entry-timing delta on held-out episodes.
    Unblocked by #5370. P0 US_PROPHET_ENTRY_TIMING. Highest-value open wave.
 2. WS:AGENT-OS Phase 1 — adoption. Unblocked once C1/C2 are ruled.
 3. WS:WATCHLIST-PORTFOLIO W1 — blocked on decision 1 above.
```

**Verification note.** The window counts and the shape are illustrative of the format. Every
*named* item is real and traceable: PR #5463 (Watchlist P0 husk), #5370 (Prophet backfill),
#25 (Executive OS Phase 1C-A, 2026-08-12 03:53), the CN limit-up STOP-SHIP of 2026-08-10, and
the 2026-08-15 GMI scrape date. Phase 2's implementation computes all counts from
`agent_os_state.v1` rather than asserting them.

---

## §3 Section contracts

| Section | Source | Ordering | Cap | Omitted when |
|---|---|---|---|---|
| Header counts | `agent_os_state.v1` | — | — | never |
| Inputs line | generator `inputs` block | — | — | never — staleness is load-bearing |
| **WHAT NEEDS YOU** | `needs_ceo` present | `by_when`, then blocked-wave count | 5 (overflow counted) | empty → "Nothing needs you." |
| BLOCKED | `status: blocked` | longest blocked first | 5 | empty |
| FINISHED | waves→`done` in window | recency | 8 | empty |
| RUNNING | everything else | — | rolled to counts | never |
| START NEXT | `todo` waves, deps satisfied | P0 alignment, then unblock-count | 3 | empty |

**START NEXT ranking**, in order: (1) all `depends_on` satisfied; (2) maps to an active P0 in
`strategic_state.yml`; (3) unblocks the most other waves; (4) not currently claimed. Deterministic
— no model in the loop, so the brief is reproducible and arguable.

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
  "blocked": [...], "finished": [...], "start_next": [...],
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
| CEO becomes the dispatcher | START NEXT is *unblocked work*, not assignments. Nothing is assigned to anyone. |
| Brief burns GitHub quota | Zero network calls; PR state inherited from the nightly sweep (§1) |
| Brief disagrees with reality | Every line cites a file or PR the CEO can open; the artifact wins over the summary |
