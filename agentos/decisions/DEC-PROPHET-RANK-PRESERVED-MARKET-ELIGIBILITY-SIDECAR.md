---
key: PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR
question: >
  When market risk must restrict what Prophet presents as actionable, does
  Grey Deer mutate the Prophet board (rank, population, admission), or attach
  a separate eligibility layer after rank?
answer: >
  Sidecar only, after rank. Risk never mutates raw Prophet rank, population,
  admission, or board bytes. A board-hash/source-session-bound sidecar
  (prophet.market_eligibility/v1) controls only actionability after canonical
  rank, records one disposition per raw candidate, fails closed on board-hash
  mismatch, and preserves every counterfactual: a suppressed candidate remains
  visible in All Ranked and keeps accruing its counterfactual outcome. No
  client-side join may invent eligibility.
rationale: >
  Prophet's raw board is a frozen owner (Prophet V4) and its track record is
  the company's evidence base — mutating rank or hiding candidates would
  destroy the counterfactual that later proves (or refutes) whether protection
  helped, and would make the temporary-policy expiry unable to restore state
  honestly. Binding the sidecar to the exact board hash prevents the
  wrong-board failure mode (sidecar referencing a regenerated board). Keeping
  eligibility server-side keeps authority out of the browser (law 6).
alternatives:
  - option: Filter or re-rank the board at build time under active risk
    why_not: >
      Rewrites the canonical population, erases counterfactuals, contaminates
      the Prophet track-record cohort, and violates the Prophet V4 freeze —
      explicitly banned by command packet law 5.
  - option: Hide suppressed candidates from all views
    why_not: >
      Silent deletion — the freeze (§8.3) requires suppressed candidates to
      stay visible with raw rank, policy rule, expiry, and restoration
      conditions printed; hiding them also blinds GD-11 grading.
  - option: Let the browser join envelope state onto board rows
    why_not: >
      Client-side authority: divergent joins across surfaces, no fail-closed
      hash binding, and hazard/policy computation would leave the server-side
      plane (law 6).
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §8 (sidecar contract, no silent deletion, plan origination, re-entry law)"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §11 GD-6A/GD-6B acceptance (raw board bytes/hash unchanged; fail-closed on mismatch)"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "prophet"
  - "prophet-us"
  - "prophet-cn"
  - "site/factordata/us_prophet_market_eligibility.json (future)"
  - "site/factordata/china_prophet_market_eligibility.json (future)"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19 (§8), consistent with the Prophet V4
freeze's ownership of raw rank/admission (command packet precedence §2.5).

## What would reopen this

Only a joint act by the Prophet program owner and Sol changing Prophet V4
rank/admission semantics themselves. No Grey Deer wave, replay result, or
policy urgency reopens board mutation — under incident pressure the sidecar's
scope may widen only through the policy vocabulary and its own authority
gates, never through the board.
