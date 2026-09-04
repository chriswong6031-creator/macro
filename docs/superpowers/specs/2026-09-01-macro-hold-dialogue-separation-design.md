# Macro HOLD / dialogue semantics separation — design

**Operation:** `macro-hold-dialogue-separation-20260901-sol-001`
**Authority:** Sol architecture freeze, carrier `C0BSBM78V1N/1788308863.375689`
**Status:** frozen design. An implementer executes it; it is not re-opened during implementation.

## 1. The defect

Repository law currently collapses five distinct facts into one word. `PARKED` is
described as "terminal for the current session", which is true of the **ship/merge
attempt** and false of the **worker↔Sol dialogue**. The conflation appears at four
source-law sites and once at runtime:

| Site | Current text |
|---|---|
| `agentos/decisions/DEC-SOL-HOLD-IS-A-MERGE-BARRIER.md` (`answer`) | "the delivery state is **PARKED / HOLD-FOR-SOL**: it is terminal for the current session" |
| `CLAUDE.md` §Shared workspace + completion | "That state is `PARKED`: terminal for the current session" |
| `CLAUDE.md` §Merge on CONCLUDED checks | "`PARKED / HOLD-FOR-SOL`: terminal for the current session" |
| `AGENTS.md` §The one non-merge terminal state / §merge discipline | "PARKED is terminal for the current session" |
| `scripts/ship_loop_hold_wrapper.py` `main()` | "This is a terminal PARKED state … Do not re-enter the ship loop unless Sol releases the hold." |

A worker reading these correctly concludes it must stop *everything*. It therefore
stops the reciprocal dialogue too — leaving Sol waiting on a child that has silently
disappeared, which Mastermind `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` §1 forbids:
"Silence is never a terminal receipt."

The mirror-image failure is already known and must not be re-introduced: PR #6608
took 121 consecutive blocks because a lawful hold was told to merge. The repair for
*that* corrected advice without widening permission. This repair does the same.

## 2. Five distinct facts

These are separate and must never be inferred from one another:

1. **task/wave boundary** — a checkpoint in a program (`DEC:SESSION-LENGTH-IS-NOT-A-COST-CONTROL`);
2. **PR merge hold** — `HOLD-FOR-SOL`, a hard merge barrier on every merge path;
3. **reasoning-session yield** — the provider turn ends; the child is not closed;
4. **child `STOP`** — an explicit same-carrier Sol terminal edge;
5. **program completion** — the whole mission is delivered.

`PARKED` is terminal for (2)'s current ship attempt and permits (3). It asserts
nothing about (1), (4) or (5).

## 3. The rule

**`HOLD-FOR-SOL` remains a hard merge barrier, unchanged and unweakened.** Every
eligibility gate stays exactly as it is: exact head pushed, worktree clean, PR draft,
no `merge-on-green`, native auto-merge null, Sol authority and Sol release condition
recorded, and **every binding check concluded green**. Ready/merge/auto-merge/render/
deploy/retry remain forbidden. `PARKED` still means unmerged, not SHIPPED, not
deployed, not live.

**`PARKED` is terminal for the current ship/merge attempt only.** The reciprocal
worker↔Sol child dialogue remains **nonterminal**. The same child, carrier, branch and
PR remain resumable on a later same-carrier Sol `CONTINUE` / `RULING` /
`REQUEST_REPAIR`. Only an explicit same-carrier Sol `STOP` / `ACCEPTED / STOP` /
`CLOSED / STOP` closes the child.

**Yielding has a price.** Before a worker yields at `PARKED` it must already have
posted one exact-carrier `RESULT / HOLD-FOR-SOL` and must have established a truthful
continuation path — `WATCH_ARMED` (a real, verified registration) or `WATCH_UNAVAILABLE`
naming the checked surface and the exact failure. Saying "waiting for Sol" is not a
continuation path and does not satisfy this.

## 4. What the hook may and may not say

The Stop wrapper is a **non-authoritative message surface**. It may state the
obligations above. It may **not**:

- claim a watcher is actually armed, or assert any watcher state;
- infer, report, or depend on Slack state;
- elect or name a specific Sol;
- create a successor, a new wave, a task, a queue, a retry, or a RuntimeBinding;
- grant merge, release, or Ready permission.

It states the *obligation* to have a continuation receipt; it never claims the
receipt exists. That distinction is the difference between guidance and a false
green, and it is asserted by test.

## 5. Implementation shape

Extract the existing green-`PARKED` response body into one deterministic helper:

```python
def _parked_message(probe: dict[str, Any]) -> dict[str, str]:
    """Compose the terminal PARKED systemMessage. Pure; no I/O, no probing."""
```

`main()` calls it for the `status == "parked"` branch and prints the result. The
helper is pure — it performs no git, GitHub, network or filesystem access, so it is
directly unit-testable from a plain dict.

**Byte-semantically unchanged:** `_hold_probe`, `_parked_hold`, `_hold_block`,
`_hold_protocol_is_complete`, `_field`, eligibility, the green-check requirement, the
pending and red paths, branch namespaces, and delegation. `_parked_hold` keeps its
existing return shape for the canonical regression suite. Pending and red remain
`decision: block`.

## 6. Required message content

The composed message must state all of:

- `SHIP LOOP PARKED`;
- unmerged, `not SHIPPED`, not deployed, not live;
- merge / Ready / auto-merge / render / deploy / retry still forbidden;
- terminal for the **ship/merge attempt** only;
- `dialogue remains nonterminal`;
- before yield: exact-carrier RESULT / HOLD-FOR-SOL plus a truthful `WATCH_ARMED` or
  `WATCH_UNAVAILABLE`;
- the same child / same carrier / branch / PR resume on Sol `CONTINUE` or
  `REQUEST_REPAIR`;
- `only explicit Sol STOP` (or `ACCEPTED / STOP`, `CLOSED / STOP`) closes the child.

It must **not** state that the worker, child, or session is terminal, and must not
reduce the continuation obligation to "wait for Sol".

## 7. Source-law parity

`CLAUDE.md`, `AGENTS.md`, `DEC-SOL-HOLD-IS-A-MERGE-BARRIER`,
`DEC-SESSION-LENGTH-IS-NOT-A-COST-CONTROL` and the new
`DEC-HOLD-PARKS-SHIP-NOT-DIALOGUE` must agree that the ship attempt is not the
reciprocal dialogue and that only an explicit Sol STOP closes the child. A parity
test asserts this across all five files, so a future edit to one cannot silently
re-open the conflation in another.

## 8. Non-goals

No blanket release of any existing hold. No change to the CI-green requirement. No
watcher, task, lifecycle, queue, retry or RuntimeBinding store. No change to
`.claude/hooks/ship_loop_guard.py`, workflows, settings, existing held PRs, native
task stores, Slack runtime, or Executive OS. No automatic successor or new wave.

## 9. Falsifiers

The repair is wrong if any of these hold after it lands:

- a `PARKED` state can be reached with a pending or red binding check;
- a `PARKED` message can be read as permission to merge, mark ready, arm auto-merge,
  render, deploy or retry;
- the hook claims a watcher is armed, or asserts/infers Slack state;
- a worker can lawfully yield at `PARKED` with no posted RESULT/HOLD and no truthful
  `WATCH_ARMED` / `WATCH_UNAVAILABLE`;
- a child can be closed by anything other than an explicit same-carrier Sol STOP;
- the five source-law files disagree about any of the above.
