---
key: SESSION-LENGTH-IS-NOT-A-COST-CONTROL
question: >
  Frontier burn is context size × turn count. Does it follow that a session must STOP at
  each task boundary — one merged wave per session, long programs run as a chain of short
  sessions?
answer: >
  No. The measurement stands and its two real controls stand — (1) delegate execution to
  subagents, whose context is discarded on return so only the report lands; (2) budget what
  enters the orchestrator's context (targeted greps, line-ranged reads, capped command
  output, no screenshots or page dumps in the main loop) — but the third clause, "one
  session = one task boundary", is REPEALED (operator 2026-09-01). Session DURATION is not a
  billed quantity; context SIZE is, and the two surviving controls govern it directly. A
  merged, live-verified wave is a checkpoint, not a session end, and one session may carry a
  program end-to-end across many waves and many merges. The durable-state half survives as a
  WRITE rule rather than a STOP rule: keep program state in
  `research/*_CONTINUATION_HANDOFF_<date>.md` and `agentos/handoffs/` as you go, so work
  survives a clear, a crash, or an operator handoff — not so the session must end at one.
  Context figures (~200k / ~250k) are advisory targets, never a stop trigger. Unchanged:
  do NOT save tokens by cutting reasoning effort; DONE for ordinary work is still the merge;
  a ratified `PARKED / HOLD-FOR-SOL` is still never described as merged, shipped, or live.
rationale: >
  The repealed clause was derived from a correct measurement but did not follow from it. The
  2026-08-06 data shows cost = context × turns; it contains no term for wall-clock session
  length or for the number of task boundaries crossed. The worst measured session
  (`bf6ce626`, 3,539 turns, median 419k context) was expensive because of its CONTEXT, not
  because it spanned 16 branches — and the two surviving controls already attack context
  directly. In practice the stop rule made every long workflow a relay of amnesiac sessions:
  each successor paid to re-establish from a handoff doc what the predecessor already knew,
  which is a fresh-input cost the stop was supposed to be avoiding. Operator 2026-09-01, in
  the session that removed it: the boundary "is impeding end to end long workflows". The
  cheapest shape is therefore a LONG session held at SMALL context (delegate + budget), not
  a short session riding the ceiling.
alternatives:
  - option: Keep the boundary but raise the context thresholds
    why_not: "Preserves the same category error — it still gates on a proxy (session shape) instead of on context size, which the two surviving controls already govern directly."
  - option: Delete DEC:FRONTIER-BURN-IS-CONTEXT-TIMES-TURNS outright
    why_not: "Its measurement and its first two controls are still correct and load-bearing; agentos/README.md §5 forbids deleting decisions. Superseded and restated instead."
  - option: Leave the rule and let sessions ignore it in practice
    why_not: "Standing law that is routinely violated corrodes every other standing rule; and the ship-loop guard's authority depends on the law meaning what it says."
evidence:
  - "Operator directive 2026-09-01: 'Remove the one session one task thing from our repo or memory, as this is impeding end to end long workflows'"
  - "Superseded record: agentos/decisions/DEC-FRONTIER-BURN-IS-CONTEXT-TIMES-TURNS.md (measurement retained verbatim; only its clause (3) repealed)"
  - "Macro CLAUDE.md §Context economy, third bullet — rewritten in this PR"
  - "Macro AGENTS.md §Context economy, third bullet — rewritten in this PR"
  - "Enforcement census run before the edit: no hook, workflow, or test enforced the boundary (grep over .claude/hooks/, scripts/ship_loop_hold_wrapper.py) — it was prose law only, so the repeal needs no code change"
supersedes: ["DEC:FRONTIER-BURN-IS-CONTEXT-TIMES-TURNS"]
affects: ["CLAUDE.md", "AGENTS.md", "research/CI_LATENCY_AND_AUTONOMOUS_HEALING_MASTERPLAN.md", "research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md", "research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-09-01
---

## Grounds

This record carries forward, unchanged, the whole measurement basis of
`DEC:FRONTIER-BURN-IS-CONTEXT-TIMES-TURNS` — 3,043 local transcripts, week
2026-07-30→08-06; Fable = 1,902M weighted units (26% of all model burn, Opus 62%); of
Fable's own burn 62% cache reads / 21% cache writes / 17% output; per-turn floor
`0.1 × context`; delegation at 2.6% of tool calls against 76% direct
`Bash`/`Edit`/`Read`/`Write`. Nothing in that measurement is disputed or re-opened here.
What changes is one inference drawn from it.

The repealed clause treated session length as a proxy for context size. The proxy fails in
both directions: a short session that pulls whole files and page dumps into the main loop
bills at the ceiling, and a long session that delegates execution and reads narrowly stays
near 150k for its whole life. Because the cost model has no duration term, the correct
lever was never "stop sooner" — it is the two controls this record keeps.

The stop rule also had a cost the original analysis did not price: the handoff. Every
boundary crossing forces the successor to re-read a masterplan, a continuation doc, open
PRs, and the current wave's state — all of it fresh input at 10× cache-read rates — to
recover context the predecessor was already holding at the 0.1× discount. For a program of
N waves the rule pays that re-establishment cost N times.

## Scope of the repeal

Repealed: the mandate to stop at a merged task boundary, "one wave per session", and the
~250k checkpoint-and-clear directive as a *trigger*.

NOT repealed, and explicitly restated so nothing rides out with it:

- Delegation and context budgeting (controls 1 and 2) — unchanged and now the only controls.
- Do NOT save tokens by reducing reasoning effort — output is ~17% of burn.
- Durable state on disk. Continuation handoffs and `agentos/handoffs/` records are still
  written, now *as work proceeds* rather than as an exit ritual, and the Agent OS at-stop
  handoff obligation (`agentos/README.md`) is untouched.
- DONE for ordinary work is still commit → push → PR → CI → same-day squash-merge → live
  verification, owned by one session.
- `DEC:SOL-HOLD-IS-A-MERGE-BARRIER` and the `PARKED / HOLD-FOR-SOL` reporting rule — a
  ratified hold is still terminal for that PR's work and still never reported as shipped.

## What would reopen this

Measured evidence that long sessions cost more *at equal context size and turn count* —
i.e. a duration term appearing in the pricing model — or a harness change that makes
session length itself billed. Re-measure before extrapolating from the 2026-07-30 snapshot;
if long end-to-end sessions in practice drift upward in context rather than delegating,
the answer is to enforce controls 1 and 2, not to restore the boundary.
