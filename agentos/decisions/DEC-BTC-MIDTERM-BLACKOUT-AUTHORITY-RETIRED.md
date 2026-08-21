---
key: BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED
question: >
  May the US midterm-election calendar continue to force the final BTC allocation
  to cash when the measured BTC engine is constructive?
answer: >
  No. The Chairman overruled the mechanism on 2026-08-20 after the 2026 tape
  contradicted its forced-cash stance. The midterm-blackout rule is retired from
  allocation authority. Its historical implementation and forward-grading ledger
  may remain for attribution, but election-cycle history is context-only and may
  not gate, size, suppress, or rewrite final BTC exposure.
rationale: >
  The override was an n=3 calendar prior applied after the measured allocation
  engine, so it could output 0% BTC even while the dashboard's scored tape was
  RISK-ON. The repository's own attribution called the sample illustrative rather
  than calibrated, DNR:KILL-ELECTION-CYCLE already refuted election cycles as a
  standalone signal, and DNR:KILL-LAUNDERED-OVERRIDE-GATES forbids human conviction
  masquerading as model output. The live contradiction is therefore evidence of
  the known construction failure, not a reason to retune the calendar window.
alternatives:
  - option: Move the 2026 staged re-entry window earlier
    why_not: >
      This preserves calendar authority and merely fits a new release date after
      observing the rally. It would repeat the same post-hoc override pattern.
  - option: Keep the gate but release it after a new all-time-high confirmation
    why_not: >
      The engine would still suppress a constructive tape until an extreme lagging
      condition fired. Calendar conviction would continue to outrank measured risk.
  - option: Delete all historical gate code and grading artifacts
    why_not: >
      Erasing the audit trail would destroy useful attribution evidence. Retirement
      requires zero authority, not deletion of the record of what was tried.
evidence:
  - "Chairman instruction, 2026-08-20: 'Overrule the btc gate mechanism that dictates midterm election years are no hold risk off periods For BTC. This has effectively failed as BTC has lifted off.'"
  - "User-provided BTC Vector screenshot, 2026-08-20: RISK-ON and Master Read +31 while the final allocation remained WAIT IN CASH at 0-0%"
  - "reports/btc-gate-attribution.md: n=3 path shapes; illustrative, not calibrated"
  - "research/DO_NOT_REBUILD.md DNR:KILL-ELECTION-CYCLE and DNR:KILL-LAUNDERED-OVERRIDE-GATES"
  - "config.yml vector.allocation.midterm_gate.enabled=false and production regression tests"
affects: ["config.yml", "engine/btc_overrides.py", "scripts/build_btc_strategy.py", "templates/btc_strategy.html.j2", "templates/vector.html.j2", "DNR:KILL-BTC-MIDTERM-BLACKOUT-AUTHORITY"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-20
---

## Operational meaning

The production configuration keeps `vector.allocation.midterm_gate.enabled: false`.
`alloc_*` is therefore the measured engine output, `override_active` remains false,
and subscriber surfaces must not show the election calendar as a reason to wait in cash.

The standalone calendar mask, historical attribution report, and forward ledger remain
available for honest post-mortem grading. They have no route back into allocation.

## What would reverse this

Only a new explicit operator ruling after independently registered evidence establishes
allocation value beyond the n=3 historical calendar sample. A rally, drawdown, election,
or change to the projected bottom window is not by itself reactivation authority.
