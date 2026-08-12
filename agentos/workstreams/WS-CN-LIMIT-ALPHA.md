---
key: CN-LIMIT-ALPHA
title: China limit-up alpha research
objective: >
  Establish whether mainland limit-up mechanics carry tradeable, gauntlet-survivable
  signal. Done = a promotion-grade verdict, or a recorded kill.
status: blocked
program: china-system
repos: [macro]
owner: chairman
class: research
blast_radius: reversible
ambiguity: open
blocked_by:
  - "STOP-SHIP held since 2026-08-10 by operator ruling: grade NEITHER arm; W1-W3 must not be cited anywhere."
waves:
  - id: W-P0
    title: Charter + P0 scope
    status: done
  - id: P-A1
    title: First accrual arm
    status: awaiting_ci
    pr: 5438
  - id: P-A2
    title: Second arm
    status: todo
    depends_on: [P-A1]
    next_action: Accrual-gated; do not start until P-A1 accrues.
landmines:
  - "W1-W3 results are under STOP-SHIP and must never be cited as evidence, including in passing."
next_action: Hold. P-A1 is armed; P-A2 is accrual-gated.
created: 2026-07-30
updated: 2026-08-12
---

## Context

Under an explicit operator STOP-SHIP since 2026-08-10. The charter and W-P0 merged
2026-08-12; P-A1 (#5438) is armed. The block is a deliberate ruling, not a defect — it is
recorded here so no future session "helpfully" grades an arm or cites W1–W3.
