# Macro HOLD / dialogue semantics separation — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute this plan task-by-task in one isolated worktree. Do not improvise architecture — the design is frozen. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve `HOLD-FOR-SOL` as a hard merge barrier while making a green `PARKED` hold terminal only for the current ship/merge attempt — not terminal for the reciprocal worker↔Sol child dialogue, which stays resumable on the same child/carrier/branch/PR until an explicit same-carrier Sol `STOP`.

**Architecture:** One deterministic pure helper `_parked_message(probe)` extracted from `main()` in `scripts/ship_loop_hold_wrapper.py`, plus aligned source law across `CLAUDE.md`, `AGENTS.md` and three Agent OS decision records. Probe, eligibility, green-check requirement, pending/red behavior and branch namespaces are byte-semantically unchanged. The hook remains a non-authoritative message surface: it states obligations, never watcher or Slack state.

**Tech Stack:** Python 3 standard library only (no new dependency), pytest, Markdown, Agent OS YAML-frontmatter decision records.

**Spec:** `docs/superpowers/specs/2026-09-01-macro-hold-dialogue-separation-design.md`

## Global constraints

- **Nine-path ceiling.** Exactly the nine paths frozen in the carrier; a tenth requires `DECISION_REQUEST / PATH_CEILING` first.
- Do not change `_hold_probe`, `_parked_hold`, `_hold_block`, hold eligibility, the green-check requirement, pending/red behavior, or branch namespaces.
- Do not touch `.claude/hooks/ship_loop_guard.py`, workflows, settings, existing held PRs, native task stores, RuntimeBinding, Slack runtime, Executive OS, or any merge/retry authority.
- No blanket release of any existing hold. No watcher/task/lifecycle/queue/retry store. No automatic successor or new wave.
- `parked` remains the sole terminal exit and still demands every binding check concluded green.
- Spec and plan commit **first**; failing tests **before** production or docs edits.
- Focused suites only — this is a sparse worktree; no full-suite run.

## Task 1 — spec and plan (no source effect)

- [ ] Write `docs/superpowers/specs/2026-09-01-macro-hold-dialogue-separation-design.md`.
- [ ] Write this plan with a complete header (goal, architecture, stack, spec path) and no placeholders.
- [ ] Commit both before any other edit.

## Task 2 — RED

- [ ] Add `test_parked_message_separates_ship_terminal_from_dialogue_terminal` to `tests/test_ship_loop_hold_wrapper.py`: assert the message contains `SHIP LOOP PARKED`, `not SHIPPED`, `dialogue remains nonterminal`, `only explicit Sol STOP`, `same child`, `same carrier`; assert it does **not** claim the worker/child/session is terminal and does not reduce continuation to "wait for Sol".
- [ ] Add `test_parked_message_requires_truthful_continuation_receipt_before_yield`: assert both `WATCH_ARMED` and `WATCH_UNAVAILABLE` appear as truthful alternatives and that an exact-carrier RESULT/HOLD is required; assert the message never claims a watcher was actually armed.
- [ ] Add a hook-authority test: the message elects no Sol, creates no successor, and asserts no Slack state.
- [ ] Add a source-law parity test across `CLAUDE.md`, `AGENTS.md`, `DEC-SOL-HOLD-IS-A-MERGE-BARRIER`, `DEC-SESSION-LENGTH-IS-NOT-A-COST-CONTROL`, `DEC-HOLD-PARKS-SHIP-NOT-DIALOGUE`: all five agree on ship attempt ≠ reciprocal dialogue and on explicit Sol STOP.
- [ ] Add a permission-boundary test proving `PARKED` still forbids merge/Ready/auto-merge/render/deploy/retry.
- [ ] Run focused RED and record the exact expected failures.

## Task 3 — GREEN (smallest change)

- [ ] Extract `_parked_message(probe) -> dict[str, str]` in `scripts/ship_loop_hold_wrapper.py`; call it from `main()`'s `parked` branch. Pure function: no git, GitHub, network or filesystem access.
- [ ] Compose the message to the frozen §6 content. Keep `_parked_hold`'s return shape.
- [ ] Run focused GREEN.

## Task 4 — source law

- [ ] `agentos/decisions/DEC-HOLD-PARKS-SHIP-NOT-DIALOGUE.md` — new record; `supersedes` is not used (this refines rather than replaces), and the two amended records cross-reference it.
- [ ] `agentos/decisions/DEC-SOL-HOLD-IS-A-MERGE-BARRIER.md` — replace "terminal for the current session" with ship-attempt-terminal wording; merge-barrier authority unchanged.
- [ ] `agentos/decisions/DEC-SESSION-LENGTH-IS-NOT-A-COST-CONTROL.md` — align its restated PARKED clause.
- [ ] `CLAUDE.md` and `AGENTS.md` — same correction at each conflating site, preserving every surrounding prohibition.

## Task 5 — mutation / falsifier verification

Each must FAIL when the clause is removed, proving the assertion is load-bearing:

- [ ] deleting "only explicit Sol STOP" fails;
- [ ] replacing "dialogue remains nonterminal" with session/child-terminal wording fails;
- [ ] deleting the `WATCH_UNAVAILABLE` alternative fails;
- [ ] allowing `PARKED` before green checks still fails existing tests;
- [ ] allowing merge/Ready/auto-merge from `PARKED` still fails source assertions.

## Task 6 — validation and release

- [ ] `python3 -m pytest tests/test_ship_loop_hold_wrapper.py -q`
- [ ] `python3 scripts/agentos.py validate`
- [ ] relevant ship-loop / semantic / fence suites required by current `CLAUDE.md`
- [ ] `python3 -m py_compile scripts/ship_loop_hold_wrapper.py`
- [ ] `git diff --check`
- [ ] One ordinary PR. Arm `merge-on-green` only if no HOLD text exists on it. Stay through exact-head CI and merge/live readback unless Sol converts it to a hold.
- [ ] Post `RESULT` on the exact carrier; re-arm the continuation watcher; treat the RESULT as nonterminal until a same-carrier Sol edge.
