---
key: CNLI-EXACT-CENT-PRIMARY
question: >
  What data qualifies as authority-grade ground truth for first-board
  outcomes?
answer: >
  Only the exact plane: unadjusted nominal prices, same-key vendor exact legal
  limits (stk_limit), integer-cent equality (close_cents == up_limit_cents),
  positive-volume eligibility, and complete point-in-time universe receipts.
  Adjusted prices, reconstructed limit ratios, and tolerant primary labels
  never carry exact-event or trading authority.
rationale: >
  The binding 2026-08-10 stop-ship (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT) was
  caused precisely by back-adjusted prices, reconstructed ratios, tolerant
  primary labels, and ties-to-even rounding standing in for legal limits. A
  limit-up is a legal integer-cent equality at the venue, not a percentage
  band on an adjusted series; any tolerance or reconstruction reintroduces
  silent label error at exactly the boundary the program predicts. Tolerant
  pattern-tier detection remains lawful for mechanism/design research only,
  and is never promoted into targets, calibration, or grades.
alternatives:
  - option: Back-adjusted tape with reconstructed limit ratios
    why_not: >
      The withdrawn W1-W3 substrate; total kill under
      DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT. Restoration in any form is
      forbidden.
  - option: Tolerant (epsilon-band) primary event labels on raw prices
    why_not: >
      Tolerance at the label boundary manufactures and deletes events at the
      exact decision margin; permitted only as pattern-tier research witness,
      never as the authority-grade target.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §1.2, §6.1, §12"
  - "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT"
  - "research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "collectors/china_tushare_spine.py"
  - "research/cn_limit/"
confidence: high
reversibility: one_way
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze restating the standing kill as the program's
positive data law. Reversibility is one_way because the kill row itself is a
registry-blocked design; no session may soften it.
