---
key: AUTHORITY-FREEZE-CLEARS-ON-DESCENDANT-BASELINE
question: >
  Should a merged head frozen by authority_changed=true semantic evidence (any
  scripts/**, .github/**, *.py edit merged while main was red) remain unclearable
  forever in ship_loop_guard.py's Stop gate, and if not, which bounded clearing
  path preserves the fence's intent that an authority change must not excuse
  itself?
answer: >
  Two bounded mechanisms, both shipped in the same PR. (1) CLEARING: a merged
  head whose semantic evidence blocks ONLY on the authority freeze itself
  clears when a completed ci.yml run concludes SUCCESS on branch=main with a
  head that is a main descendant of the merge (the guard's existing E1
  predicate, _merged_content_green). "Freeze alone" is precise and
  emitter-aware: authority_changed=true, every top-level infrastructure row is
  the emitter's own authority_self_excuse_refused marker (the emitter records
  the freeze ITSELF as an infrastructure row on every pr_head artifact with
  inherited_base units), every job-level infrastructure outcome passed, and
  ZERO classified blocking units — a pr_regression/unknown unit is the head's
  own red and is never blanketed by a baseline. Foreign infrastructure
  ambiguity stays outside the path, an unanswerable probe keeps the freeze,
  and pending checks still outrank the clearing. (2) REPETITION: a ladder exit
  that was fully ratified (SHIP LOOP BLOCKED report + external arms) for the
  exact evaluated state ci_failed:<head_sha>:<merge_sha>:<sha256(reason)[:12]>
  is remembered in the guard's state ledger; later Stops on the identical
  state pass through without demanding the identical report again. The reason
  digest binds the memory to the exact evidence the report answered — a rerun
  or late-attaching cron that binds a different red to the same shas mints a
  different key and re-blocks. Operator-grant markers (labels, PR comments,
  grant files) were REJECTED as clearing evidence.
rationale: >
  The fence's stated intent — "candidate-era proof may not excuse this
  authority-changing pull request" — forbids the PR's own classification-era
  semantic evidence from excusing its own red, because the PR may have changed
  the machinery that mints that evidence. A descendant main baseline is a
  categorically different kind of proof: it executes ON the merged authority
  after the merge, so it is the post-merge transposition of the pre-merge
  standard already in fleet law ("an authority-changing PR needs main itself
  green"). The guard already trusted exactly this evidence in two places: E1 on
  the legacy merged-head path is documented as "the OPERATOR'S DELIBERATE
  UNBLOCK LEVER ... clears EVERY bad conclusion", and a head that advertises NO
  semantic evidence already reached it — so advertising semantic evidence made a
  head strictly LESS clearable than having none, an inversion nobody designed.
  The old behavior returned the authority refusal before E1 was ever consulted,
  making the block literally unsatisfiable: the frozen head's own run is
  immutable after merge, unit healing is disabled by design, and gh run rerun
  replays the frozen merge ref. Sessions that performed operator-granted
  main-red-repair merges (#5954/#5969/#6002 under the 2026-08-19 §4b grant) were
  then pinned for life, exiting only via the escape ladder and re-filing the
  same SHIP LOOP BLOCKED report dozens of times — the repetition the operator
  explicitly complained about on 2026-08-19. The remembered ladder exit fixes
  the repetition without widening any ladder: the report is demanded once per
  frozen state instead of once per Stop, the memory is written only at the
  moment an escape actually fires, only ci_failed on a merged head carries a key
  (its evidence cannot change by any session-side action), and a new merge mints
  a new key that gates fresh.
alternatives:
  - option: Operator-grant marker (authority-grant label, or a grant file cited in a pre-merge PR comment) exempts the head
    why_not: >
      The fleet authenticates as ONE shared gh token and main carries no branch
      protection or required reviews, so a label, comment, or committed grant
      file is mintable by the very session seeking the exemption — self-excuse
      by construction, precisely what the fence exists to forbid. No
      operator-only signal channel exists for the guard to verify authorship.
      The 2026-08-19 §4b grant's proper effect is on the session's conduct
      (admin-merge authorization, recorded in research/), not on the guard's
      evidence model.
  - option: Cap-and-downgrade — after N identical frozen-head blocks with stop_hook_active, downgrade the block to a warning
    why_not: >
      A time-based downgrade weakens the gate universally: any frozen red,
      including one that IS the session's own defect, could be waited out with N
      contentless stops. Adopted only in the modified form above — the full
      ladder (evidence report + arms) must fire once per frozen state before any
      pass-through, so no state is ever excused without its report, and fresh
      states always gate.
  - option: Reclassify the authority-frozen block from external ci_failed to a shorter or reportless ladder
    why_not: >
      ci_failed is already external (2 consecutive / 3 cumulative). Shortening
      further approaches a no-op gate, and removing the report removes the
      evidence trail the exit exists to produce. The E1 clearing makes the state
      actionable again (dispatch a baseline, wait), so the external ladder's
      shape is right; only the per-Stop repetition needed fixing.
  - option: Leave it unclearable (status quo) and rely on the escape ladder
    why_not: >
      The block message asserted descendant healing "cannot" help while E1
      genuinely proves the merged content green — a false statement of
      unsatisfiability. It pinned exactly the sessions the operator had granted
      repair authority to, produced dozens of identical reports per session, and
      trained sessions to treat SHIP LOOP BLOCKED as routine noise, eroding the
      signal the guard exists to produce.
evidence:
  - ".claude/hooks/ship_loop_guard.py _check_ci E1 docstring: 'the OPERATOR'S DELIBERATE UNBLOCK LEVER ... clears EVERY bad conclusion' — predates this change; the authority branch returned before consulting it"
  - "Memory record authority-changing-merge-during-red-main-is-permanently-unclearable (2026-08-18, PRs #5875/#5888): dispatched main baseline proved both merges green affirmatively and the gate still refused, correctly per the old code"
  - "Memory record any-scripts-edit-sets-authority-changed-and-hard-blocks-stop (2026-08-18, #5865): cron red bound to merged SHA 3 min post-merge; rerun replays the frozen merge ref; no session-side remedy existed"
  - "research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md §4b: operator grant for main-red-repair merges; §'The trap W1-W4 must plan around': every PR in the repair program is authority-changing, so the fix for the problem was gated on the problem"
  - "Operator complaint 2026-08-19 about the repeated identical SHIP LOOP BLOCKED reports from the session that merged #5954/#5969/#6002"
  - "Pre-ship opus red team (2026-08-19, this session) caught a severity inversion in the first draft: the predicate required infrastructure empty, but the emitter (scripts/ci_semantic_proof.py reconcile_evidence) records the freeze itself as an authority_self_excuse_refused infrastructure row — so the clearing was dead for the motivating inherited_base case and OPEN for a head carrying its own classified pr_regression. Fixed predicate is self-excuse-row-aware and requires zero blocking units; tests rebuilt on the real emitter + real semantic_gate_verdict instead of hand-shaped evidence dicts"
  - "python3 -m pytest tests/test_ship_loop_semantic.py tests/test_ship_loop_guard.py tests/test_ci_semantic_proof.py -q -> 318 passed, 1 skipped (includes 8 authority-freeze tests and 4 ladder-memory tests)"
affects: [".claude/hooks/ship_loop_guard.py", "tests/test_ship_loop_semantic.py", "tests/test_ship_loop_guard.py", "CLAUDE.md", "AGENTS.md"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-19
---

## Grounds

The authority fence and the E1 lever were both correct individually; the defect
was their ordering. The fence (a PR that changes CI proof authority may not be
excused by evidence minted under the machinery it changed) is preserved intact:
candidate-era semantic evidence and descendant per-unit witnesses remain
inadmissible for an authority-changing head, pre-merge and post-merge. What
changes is that the ONE form of proof the fence's own rationale endorses — main
itself green, under the merged authority, on a tree containing the merge — is
now consulted instead of being unreachable. The clearing is scoped to heads
whose sole nonunit blocker is the authority freeze: infrastructure ambiguity
keeps its existing pinned behavior, and every failure mode of the probe fails
closed.

The remembered ladder exit is deliberately narrow. It keys on
`ci_failed:<head_sha>:<merge_sha>:<sha256(reason)[:12]>`. The digest is
load-bearing: a merged head's check SET is not immutable (`gh run rerun` or a
late-attaching cron can bind a different red to the same shas), so the shas
alone would let one ratified report cover an unbounded family of later,
unrelated CI states — the red team's finding 3. Digesting the block reason
pins the memory to the exact evidence the report answered; any different red
re-blocks, which is the fail-closed direction. `render_pending` and every
internal code carry no key: their states evolve, so they must keep re-arguing.
The memory is written only at the instant an escape actually fires, which
itself required the full evidence report on a re-entrant Stop — so no ladder
widened, and the no-first-attempt-bailout property is untouched.

## Risks accepted (named, not implicit)

- **E1 proves main as main defines it.** A ci.yml run on main plans the code
  gate only (`--gate code`); the `gate: data` jobs emit no main-role evidence
  (DSC family: semantic eligibility is role-dependent). "Proving the merged
  content green" therefore means green on every assertion main itself runs —
  the identical trade the legacy E1 path, the pre-merge drain path, and the
  sweeper's main-proof refresh have always made. Demanding more would demand
  evidence no lane produces.
- **The descendant run executes under the merged authority.** A PR that
  weakens ci.yml itself would self-certify on its own baseline. Accepted
  because the same residual holds for every future proof of main under any
  design (post-merge, only the new authority exists to run), the pre-merge
  standard ("main itself green") carries it identically, and the alternative —
  proof under the pre-merge authority — is structurally impossible after the
  merge. Review of authority-touching diffs stays the control for this class.
- **Sessions without a session_id share the guard's `default.json` state
  file**, so a remembered exit there is visible to a co-located session. This
  is the pre-existing trust boundary of the whole block ledger (consecutive
  and cumulative counters are already shared in that fallback), not a new
  class of sharing; the reason digest further narrows what a shared entry can
  excuse.
