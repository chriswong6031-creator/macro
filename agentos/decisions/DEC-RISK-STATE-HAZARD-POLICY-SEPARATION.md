---
key: RISK-STATE-HAZARD-POLICY-SEPARATION
question: >
  Does Mastermind answer "what regime persists," "is a specific transition
  becoming dangerous," and "what actions are currently permitted" with one
  blended market-risk representation, or as separate orthogonal fields?
answer: >
  Separate, permanently. Slow measured state, transition hazard, repair, data
  quality, coherence, and capital policy are orthogonal fields
  (measured_state / hazard_stage / repair_state / data_state / coherence_state
  plus a display-only capital-posture projection). No score may stand in for
  them, and no field may be silently blended into another. A slow Risk-on state
  may lawfully coexist with a critical hazard and a protective policy — that
  coexistence is the exact transition the product exists to detect.
rationale: >
  The August 2026 incident was a company-level product failure, not a cosmetic
  one: Slow Market State stayed green while leadership was broken, long-end
  rates stressed duration assets, volatility accelerated, high-beta technology
  was liquidated, China risk warnings were stale, and defensive rotation was
  already visible. Individual organs existed, but the product had no canonical
  semantic separation between "trend still intact," "turn hazard rising," and
  "what users/Prophet should do" — so the calm blend won. Blending also
  destroys accountability: a single number cannot carry separate clocks,
  separate falsifiers, or separate authority.
alternatives:
  - option: One universal weighted risk score (a "risk=83" composite)
    why_not: >
      The blended construction is exactly what failed in the incident; a
      composite hides the transition inside the average, cannot be graded
      per-mechanism, and inherits the legacy engine/risk_state.py problem of
      fused weights nobody can audit. Banned in scored/authority paths by the
      freeze (§1) and command packet law 2.
  - option: Hazard as a modifier that discounts the measured-state score
    why_not: >
      Same blend with extra steps — the user still sees one number move, cannot
      tell measured trend from imminent-turn risk, and stale hazard inputs
      would silently un-discount the score back toward calm.
  - option: Keep organs separate but with no canonical envelope semantics
    why_not: >
      That is the status quo that failed: organs existed, semantics did not.
      Fragmented truth makes every consumer invent its own fusion.
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §1-§2 (frozen thesis and orthogonal state model)"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §1 (incident description), §5 laws 1-2"
  - "Capability ledger: command packet §4 — slow trend PROVEN_LIVE while imminent-hazard architecture PARTIAL/NOT_BUILT"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "market-regime-risk"
  - "engine/risk_envelope.py (future)"
  - "site/riskdata/risk_envelope.json (future)"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19, commissioned by Chairman Chris after the
August 2026 risk episode. The three-answer thesis is the frozen product core;
this packet's execution work may harden sequencing but may not reopen it.

## What would reopen this

Only a Chairman/Sol product re-architecture. A session finding the separation
awkward to implement, or a reviewer preferring one number, is explicitly not
grounds — the command packet routes any pressure to blend back to Sol as a
program-level stop condition (§20).
