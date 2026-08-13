---
key: FRONTIER-BURN-IS-CONTEXT-TIMES-TURNS
question: >
  What actually drives frontier-model spend in fleet sessions, and what operating policy
  follows from it?
answer: >
  Burn is context size × turn count — the per-turn cost floor is ~0.1 × context, so a
  turn at 800k context costs ~5× a turn at 150k before the model does anything. Policy:
  (1) delegate execution to subagents — their context is discarded on return, only the
  report lands; (2) budget what enters the orchestrator's context — targeted greps and
  line-ranged reads, capped command output, no screenshots or page dumps in the main
  loop; (3) one session = one task boundary — long programs run as chains of short
  sessions over durable on-disk state, checkpointing past ~250k rather than riding to
  auto-compaction. Explicit non-goal: do NOT save tokens by cutting reasoning effort.
rationale: >
  Measured 2026-08-06 across 3,043 local transcripts (week 2026-07-30→08-06): of all
  Fable burn, 62% was cache reads, 21% cache writes, and only 17% output — so the cost is
  re-reading context, not thinking, and cutting effort degrades the model for at most a
  sixth of the cost. The worst session ran 3,539 turns at median 419k context (max 879k)
  and alone cost 11.6% of the week's FABLE burn (Fable was 26% of all model burn that
  week; Opus 62%); its ≥400k-context turns were 52% of turns but 67% of its burn. Riding
  context to auto-compaction is the most expensive pattern because compaction fires near
  the ceiling, so every approach turn bills at the ceiling rate — and no configurable
  threshold or self-compaction exists. Delegation was 2.6% of tool calls while 76% of
  Fable's main-loop tool calls were direct Bash/Edit/Read/Write: the frontier loop was
  grinding, not orchestrating. Modelled remediation (delegate execution, hold ~150k)
  cuts the measured top sessions ~66% with the same work done.
alternatives:
  - option: Save tokens by lowering reasoning effort
    why_not: "Output is 17% of burn; quality degrades for ≤1/6 of the cost. Rejected explicitly in fleet law."
  - option: Avoid prompt caching to dodge cache-read line items
    why_not: "Cache reads are the 0.1× DISCOUNT; the alternative is paying 10× fresh-input for the same tokens."
  - option: Ride one long session to auto-compaction and let the harness trim
    why_not: "Compaction fires at the ceiling, so the whole approach bills at ceiling rate — the measured worst case."
evidence:
  - "Macro CLAUDE.md §Context economy — measured numbers inline; section entered 2026-08-06 (git log -S); this record follows its scoping (per-Fable, main-loop) where the AGENTS.md rendering is looser"
  - "Macro AGENTS.md §Context economy (frontier burn is CONTEXT × TURNS)"
  - "Measurement basis: 3,043 local transcripts, week 2026-07-30→08-06, quoted in both files"
affects: ["CLAUDE.md", "AGENTS.md"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-06
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1). This is a measurement-derived policy. Where
the two cited renderings diverge, this record takes CLAUDE.md's tighter scoping — the
11.6% figure is a share of the week's FABLE burn (not of an all-frontier budget), and
the 76%/2.6% tool-call split is Fable's main-loop aggregate for the week (not one
session's) — because CLAUDE.md carries the fuller measurement context (26% Fable / 62%
Opus of all model burn). Attribution: analysis + standing law authored by the fleet →
coo-fable.

## What would reopen this

A pricing model change (per-token cache economics), a configurable compaction threshold,
or harness-side context management that changes the per-turn floor. The measurement is a
week-of-2026-07-30 snapshot; if session shapes change materially, re-measure before
extrapolating. Related: `DEC:OPUS-BUILDS-SONNET-EXPLORES-FABLE-GATED` (who executes what
the orchestrator delegates).
