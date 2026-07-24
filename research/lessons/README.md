# Lessons ledger — the operator/system error bank

One atomic lesson per file, append-only, canonical. This is the durable home for the
anecdotal evidence the desk keeps paying for: failed calls, process breaks, design
failures, ops surprises. Postmortems (`research/POSTMORTEM_*.md`) hold the deep narrative;
a lesson file is the distilled, indexable unit — one failure mode, one candidate rule.

## Why this exists (and why it is NOT a second knowledge base)

CXI-R12 forbids a hand-maintained retrieval store parallel to canonical sources. This
ledger IS a canonical source: plain research docs, versioned in-repo, indexed by the Macro
Context Index like every other research file, visible to the operator through the Obsidian
brain vault (which is a *view* over `research/` — never edit the vault copies). Anything
downstream (a compiled `lessons.jsonl` for Neural Web / committee context, a Dataview MOC)
must be DERIVED and rebuildable from these files, never hand-maintained in parallel.

## Epistemics contract (house law applied to lessons)

- A lesson is an **anecdote — n=1**. It ships to this ledger freely (display-tier: nulls
  and failures are printed, not hidden). It is NOT yet a rule.
- Each lesson names its **candidate rule(s)**. Promotion is class-dependent:
  - **process / design / ops** rules that are structurally obvious promote by explicit
    ruling → a `DO_NOT_REBUILD.md` row, a CLAUDE.md law, or a CI guard. Record where.
  - **market** rules (anything claiming how the tape behaves) stay CANDIDATE until they
    clear a pre-registered gauntlet like any other signal. An anecdote never gates sizing,
    ranking, or authority-tier copy on its own.
- **Rhymes are the real signal.** Before writing a new lesson, grep this directory for the
  same failure mode. The second or third occurrence of a rhyme is the trigger to charter a
  study or promote a rule — one spectacular failure is a story; a repeated failure is a law
  waiting to be written.
- A lesson that later proves wrong gets `status: refuted` and stays in the ledger — the
  ledger's own errors are also evidence.

## File contract

Name: `LESSON_YYYYMMDD_<SLUG>.md`. Frontmatter:

```yaml
---
id: L-YYYYMMDD-n
date: YYYY-MM-DD
title: one-line imperative lesson
class: process | market | design | ops | epistemics
program: <program slug or "desk">
incident: <one-line what-happened>
status: candidate | promoted | refuted
promoted_to: <registry row / law / guard, when status=promoted>
sources: [<postmortem/masterplan/PR refs>]
---
```

Body: **What happened** (2-5 lines, concrete numbers) · **Why (mechanism)** · **The rule**
(imperative, falsifiable where possible) · **Rhymes** (links to sibling lessons/postmortems).

## Backfill queue (prior postmortems not yet distilled)

- `POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md`
- `POSTMORTEM_20260716_DEFENSIVE_ROTATION_MISS_BY_FABLE.md`
- `POSTMORTEM_20260722_CROSSOVERS_VS_CAPEX_BIND_BY_FABLE.md`
