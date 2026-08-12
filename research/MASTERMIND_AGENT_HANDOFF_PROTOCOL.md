# Mastermind agent handoff protocol

Status: **PROTOCOL (proposed)**. Companion to `MASTERMIND_AGENT_OS_ARCHITECTURE.md` §7.
Applies to: every Claude, Codex, Fable, and local-model session doing substantive work.
Machine schema: `agentos/schema/handoff.schema.yml`.

---

## §0 What this replaces, and what it does not

The org already writes handoffs — 48 of them in Macro `research/` alone, plus the
`research/*_CONTINUATION_HANDOFF_<date>.md` session-chain convention that long programs run on.
**The good ones are excellent. There is no floor.** A heading census across the existing set
found essentially one distinct opening structure per document.

This protocol does not replace the convention; it **schematizes the strongest instance of it.**
The reference shape is `SCRIPT_IMPORT_PIN_BURNDOWN_CONTINUATION_HANDOFF_2026-08-09.md`:

```
§0 State
§1 What is LEFT — three items, in order
§2 Things that will bite the next session
§3 Bugs the burn-down turned up (all repaired, all real)
§4 Not in scope, do not adopt
```

That document already contains the two sections weak handoffs always omit — **§2 danger areas**
and **§4 do-not-redo**. The protocol makes those mandatory, adds machine-readable frontmatter so
the context compiler can consume them, and otherwise gets out of the way.

**Long masterplans keep their own `research/` home.** A handoff record is a *pointer plus the
delta*, not a migration of the prose. `artifacts:` links the masterplan; the body stays where
it is.

---

## §1 When a handoff is required

Write one when **any** holds:

1. The session claimed a workstream (`claim.by` was set) and is now stopping — for any reason,
   including `ci_handoff.py` release, context budget, or a blocker.
2. The work is unfinished and someone will continue it.
3. The session produced a decision or a discovery worth carrying (`DEC-*` / `DSC-*` minted).
4. The session hit a blocker only a human or another agent can clear.

**Not required for:** a one-file fix that merged clean with nothing learned; a read-only
question answered in chat; a session whose entire output is already a merged PR with a complete
description and no residue.

The natural moment is the one the session is already stopping at. Under the Macro fleet law that
is immediately before `python3 scripts/ci_handoff.py` — the work is committed, pushed, PR'd, and
armed; nothing is in flight; the facts are fresh. Writing it there costs one artifact at a
boundary that already exists.

---

## §2 The contract, in one sentence

> **A handoff is complete when a competent stranger with no access to your session can pick up
> the work from its text alone.**

This is the cold-stranger test, and it is the only acceptance criterion. Two banned habits it
rules out immediately:

- *"See the discussion above"* — there is no above. The next reader has your file, not your
  session.
- *"Implemented feature, tests pass"* — names no command, no file, no residue, and no danger.
  It is a status ping, not a handoff.

---

## §3 Machine-readable form

Frontmatter of `agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md`. Field table in
`MASTERMIND_AGENT_OS_STATE_SCHEMA.md` §4.

```yaml
---
workstream: WS:PROPHET-US-ENTRY-TIMING
session: claude/prophet-bake-verify-7f3a21
model: opus
ended_because: ci_handoff        # complete | ci_handoff | blocked | context_budget | crashed

mission: >
  Verify the 22:30Z Prophet bake lands clean after the #5370 backfill, and record
  whether the entry-timing measurement (W2) can start.

state_before: >
  #5370 merged; queue drained; backfill complete. No post-backfill bake had been
  read by any session. W1 was the only in-progress wave.

changed:
  - path: engine/prophet/bake_report.py
    what: "Print per-slice row counts so a partial bake is visible in the log."
  - path: tests/test_bake_report.py
    what: "Case: partial bake must not read as success."

prs: [5412]

verified:
  - claim: "A partial bake now fails the report instead of passing silently."
    command: "pytest tests/test_bake_report.py::test_partial_bake_fails"
    result: "1 passed; fails on pre-change code (git stash verified)"
  - claim: "The 22:30Z bake produced all 30 slices."
    command: "python3 -m scripts.bake_status --date 2026-08-12"
    result: "30/30 slices, 0 gaps"

unverified:
  - claim: "Entry-timing delta is measurable on the held-out set."
    what_would_verify: "Run scripts/prophet_entry_delta.py --holdout 2026-Q2; not run — W2 not started."

decisions: [DEC-BAKE-PARTIAL-IS-FAILURE]
discoveries: [DSC-FIRST-RUN-BOMB]

unresolved:
  - "Whether the 3-slice gap seen on 08-10 was the same partial-bake class or a distinct fault."

next_actions:
  - "Start W2: run scripts/prophet_entry_delta.py --holdout 2026-Q2 and print the false-positive cost alongside the delta."
  - "Backfill-check 08-10's 3-slice gap against the new partial-bake detector."

do_not_redo:
  - "Queue drain was root-caused and fixed in #5370 — do not re-diagnose the queue."
  - "The bake scheduler was audited this session and is correct; the fault was in reporting, not scheduling (engine/prophet/bake_report.py:88)."

danger_areas:
  - "A first bake after any backfill looks anomalous by construction — see DSC:FIRST-RUN-BOMB. Do not treat run #1 as steady state."
  - "bake_report.py is imported by the nightly; a raise here reds the whole nightly, not just the report."
---
```

---

## §4 Human-readable form

The body below the frontmatter. Five sections, in this order. **Prose, not shorthand** — no
arrow chains, no codenames invented mid-session, no abbreviations the next reader must decode.

```markdown
## §0 State — what is true right now
Two or three sentences. If the reader stops here, they must hold a correct belief
about where the work stands. Lead with the outcome, failures included with counts.

## §1 What is LEFT — in order
Numbered, ordered by what should happen first. Each item concrete enough to execute:
a command, a file, a decision to make. Name the blocker inline if there is one.

## §2 What will bite you
The landmines. Every non-obvious way this area breaks. This is the section that
saves the next session hours, and the one most often skipped. If you were surprised
by something this session, it belongs here.

## §3 What was decided and found
One line per DEC/DSC minted, with its key. The reasoning lives in the record; this
is the index.

## §4 Not in scope — do not adopt
What you deliberately did not do, and why. Prevents the next session from
"helpfully" expanding scope into something already ruled out.
```

---

## §5 The quality floor

A handoff fails review if any of these is true. These are the observed failure modes, made
checkable:

| # | Failure | Why it fails |
|---|---|---|
| 1 | A `verified` claim names no command | "Tests pass" is testimony, not evidence. The next session cannot re-run a claim with no command. |
| 2 | `unverified` is absent | Absent ≠ empty. An empty list is a real answer; a missing key means nobody asked. |
| 3 | `danger_areas` is empty on a session that hit any surprise | If something surprised you, it will surprise the next reader. |
| 4 | `next_actions` contains a goal, not an action | "Improve entry timing" is the workstream objective. "Run X with args Y" is a next action. |
| 5 | Any "see above" / "as discussed" / undefined mid-session codename | Fails the cold-stranger test by construction. |
| 6 | `do_not_redo` omits an investigation that consumed real time | The single highest-value field: the org's own measure is that 55–80% of proposals duplicate settled work. |
| 7 | `changed` lists paths with no `what` | A diff is already in git; the handoff exists to say *why* each path moved. |

---

## §6 How the next session consumes it

```bash
python3 scripts/agentos.py compile-context --workstream PROPHET-US-ENTRY-TIMING
```

Returns a bounded, cited bundle: the workstream record, its **most recent handoff**, non-superseded
decisions, non-stale discoveries, landmines, `do_not_redo`, open PRs from `active_builds.v1`, and
`owns_paths`. Excluded by field — superseded decisions, stale discoveries, other programs' work.

Two rules for the receiving session:

- **The bundle is testimony, not observation.** It points at evidence; it is not evidence. Open
  the primary artifact before building on any claim, and where the bundle and the artifact
  disagree, the artifact wins — and the disagreement is itself worth reporting.
- **`do_not_redo` is binding unless refuted with new evidence.** Re-investigating a settled item
  is the duplication this whole layer exists to prevent. If you think a `do_not_redo` entry is
  wrong, say so explicitly and cite what changed.

---

## §7 Crash recovery

For `ended_because: crashed` there is no orderly write. Recovery order, cheapest first:

1. **The last handoff for the workstream** — the durable checkpoint.
2. **The workstream record's `next_action`** — updated at wave boundaries, so it is usually
   fresher than the last handoff.
3. **Git**: `git log --oneline <branch>`, `git status` in the worktree named by `claim.by`.
4. **`active_builds.v1`** for PR/CI state, and `git worktree list` for occupancy.

An expired `claim` on an `active` workstream with no recent handoff is exactly the signature of a
dead session. The generator reports it as `unclaimed` — a signal to look, never an automatic
takeover, because a locked or long-running worktree is legitimately allowed to be quiet.

---

## §8 Worked bad→good example

**Bad** (representative of the failure mode the brief names):

> Implemented the bake fix. Tests pass. Should be good to merge.

Fails floor items 1, 2, 3, 6, 7 — no command, no unverified list, no danger areas, no
do-not-redo, no per-path reason.

**Good** (same work, protocol-compliant §0):

> The 22:30Z bake is clean — 30/30 slices, 0 gaps (`python3 -m scripts.bake_status --date
> 2026-08-12`). The real finding is that partial bakes were reading as success:
> `bake_report.py` printed a summary without per-slice counts, so the 3-slice gap on 08-10
> went unnoticed for two days. PR #5412 adds per-slice counts and a test that fails on the
> pre-change code. W2 (entry-timing delta) is unblocked but not started. One thing will bite
> you: a first bake after any backfill looks anomalous by construction — do not read run #1
> as steady state.

Every claim carries its command; the unverified item is named; the landmine is stated; the
scope boundary is explicit.
