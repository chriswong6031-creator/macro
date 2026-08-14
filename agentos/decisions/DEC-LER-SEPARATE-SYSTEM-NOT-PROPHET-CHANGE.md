---
key: LER-SEPARATE-SYSTEM-NOT-PROPHET-CHANGE
question: >
  The operator finds U.S. entries frequently trigger too far into the daily-cycle recovery.
  Do we tune Prophet's validated entry gate to fire earlier, or build a separate real-time
  tactical entry system?
answer: >
  Build a new, separate system (Live Entry Radar, WS:LIVE-ENTRY-RADAR). Prophet's
  selection/gating logic stays byte-identical throughout the program. Radar deliberately
  trades confirmation for earlier timing, more false starts, and operator judgment; it may
  become a nullable Prophet input or a new validated entry lane only via a future promotion
  decision under Evaluation OS law. Three questions stay permanently separate: conviction
  (Prophet), safe-timing confluence (engine/entry_signal.py gate), and early-entry
  formation (Radar).
rationale: >
  The existing gate's conservatism is correct for Prophet's job — withholding entry until
  MACD-2D × StochRSI-3D confluence is validated behavior, and weakening it to chase
  earliness would trade a measured property for an unmeasured one inside the conviction
  product. The operator's complaint is a different question (where is an unusually
  favorable early entry forming right now), and the house already killed one attempt to
  bolt washout×turn earliness onto the entry stack (DNR:KILL-WASHOUT-TURN, entry-stack
  Amendment-3 #1747). A separate display/accruing-tier product can accrue live-forward
  evidence freely without touching validated behavior.
alternatives:
  - option: Tune Prophet's existing gate to fire earlier
    why_not: >
      Modifies validated behavior to fix a complaint about a different layer; every false
      start lands inside the conviction product; forbidden by the commissioning handoff.
  - option: Add an earlier "validated entry lane" to Prophet immediately
    why_not: >
      Authority before evidence — promotion is gated on live-forward results per house
      epistemics; starting validated inverts the gauntlet.
  - option: Treat the Terminal grey dot as already-validated and ship it as signal
    why_not: >
      The grey dot is the champion BASELINE for this program's arena, not a globally
      validated take; its identity itself still carries an operator confirmation gate.
evidence:
  - "Operator/CEO execution handoff 2026-08-13, mirrored as research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md §0–§1"
  - "research/DO_NOT_REBUILD.md row DNR:KILL-WASHOUT-TURN (entry-stack Amendment-3, #1747)"
  - "agentos/workstreams/WS-PROPHET-US-ENTRY-TIMING.md — sibling workstream owning engine/prophet_*.py"
affects: ["engine/entry_signal.py", "research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md", "agentos/workstreams/WS-LIVE-ENTRY-RADAR.md"]
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-13
---

## Grounds

Commissioned in the operator/CEO execution handoff received 2026-08-13 ("Do not modify the
existing U.S. Prophet selection/gating logic as part of this program"; "Do not collapse
these layers"; "Do not weaken Prophet to make Radar work"). Recorded at PR-0 so later
sessions inherit the boundary as a decision, not as prose.

## What would reopen this

Radar clearing house promotion gates with live-forward evidence (the planned reopening —
at that point a DEC records how Radar feeds Prophet), or the operator rescinding the
separation. Nothing in Radar's research results short of promotion reopens Prophet's gate.
