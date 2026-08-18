---
key: AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION
question: >
  May AD-1's first user-facing research-priority layer keep v1.1's semantics, where
  salience (d1/d3), dealer mechanics (GEX/gex_confirm), absolute skew level, event
  premium, and Prophet context all contribute to a single directional research score?
answer: >
  No. v1.2 separates the axes. Machine LONG/SHORT requires exactly two independent
  hypothesis legs plus material activity: Q_oi (contract-matched ΔOI robust z) and
  Q_skew (skew-CHANGE robust z, never absolute level), each at |0.50|+, same sign,
  with D_salience >= 0.60. Salience (d1/d3) has zero direction sign. GEX/gex_confirm
  has zero direction-origination authority (caution may only reduce qualified-LONG
  actionability, x0.75). Tick-rule flow is structurally absent from direction while
  data/options_flow/signing_gate.json direction_reliable is false. Event premium is
  cross-sectional context without historical-mispricing claims until >=3 same-name
  events exist. asymmetry_score/probabilities/expected-edge stay null/UNCALIBRATED at
  AD-1 (evidence_strength + research_priority_score are the honest fields). Prophet is
  a display-only echo with zero rank authority (M_prophet = 1.0 always); AD-5 owns the
  first score-level confluence.
rationale: >
  The authority ladder (observed fact → qualified inference → display-tier hypothesis →
  outcome measurement → calibrated forecast → bounded Prophet authority) breaks if rung
  three overstates unsigned EOD observations: AD-6 would calibrate a contaminated family
  and AD-5/AD-7 would inherit wrong semantics. Source contracts themselves bound the
  authority: OCC/OIC mechanics make OI unsigned position quantity; the signing gate
  records direction_reliable=false (net_sign_recovery 0.4108); engine/gex_confirm.py
  self-defines as a long-thesis verifier that "cannot manufacture a buy"; absolute
  equity skew is structurally negative (the house gex_confirm contract already uses
  risk-reversal CHANGE for this reason). The v1.2 read-only preflight proved the
  corrected law remains non-vacuous on real data (session 2026-08-13: 95.7% eligible,
  LONG 3 / SHORT 7 / VOLATILITY 152 / RISK_ONLY 29 / NO_SIGNAL 165, 64 ranked cards)
  — the collapse from v1.1's 69/46 directional labels is the intended correction, and
  thresholds were not tuned to restore the old counts.
alternatives:
  - option: Keep v1.1 semantics (any two of F_D/gex/skew-level qualify direction)
    why_not: rejected by Sol AD-1P0 ruling — lets salience, a long-only verifier, and a structurally biased level originate direction the sources cannot support
  - option: Drop machine direction entirely at AD-1 (salience-only board)
    why_not: discards the two lawful hypothesis legs the literature supports (ΔOI, smirk-shape change) and would make AD-6 calibration impossible for the direction family
affects:
  - "WS:ADVANCED-DATA-OPTIONS"
  - options-intelligence
  - research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
evidence:
  - "Sol AD-1P0 ruling (2026-08-18) — semantic-authority freeze handoff"
  - "data/options_flow/signing_gate.json: direction_reliable=false, net_sign_recovery=0.4108"
  - "engine/gex_confirm.py:1-30 — dealer-gamma verifier/confirmer for a long entry; cannot manufacture a buy"
  - "v1.2 read-only preflight at audit head 6482f876ba7f, session 2026-08-13 (AD-1 handoff §5.4)"
  - "OIC/OCC FAQ; Fodor-Krieger-Doran; Kehrle-Puhan; Xing-Zhang-Zhao; Soebhag; Dim-Eraker-Vilkov (AD-1 handoff appendix)"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-18
---

Scope: governs `intel_brief_heuristic/v1.2` and every later Advanced Data scoring
version until superseded. Activating `Q_flow` (tape direction), raising any threshold,
or granting mechanics/salience direction authority requires a new model_version and
explicit review — never a silent edit. Complements `DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT`
(vocabulary keeps SHORT; this record governs what may *qualify* it).
