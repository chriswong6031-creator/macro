---
key: FLOW-OBSERVATORY-V2
title: Flow Observatory V2 — production-proven CN/HK flow context surface
objective: >
  Upgrade flow_velocity.html from a semantically overstated normalized-flow dashboard
  into a source-separated, correction-safe, point-in-time, coverage-aware Flow
  Observatory. Done means the W1..W7 waves of
  research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md are merged and live-verified:
  trust strip, absolute-vs-relative truth (quadrants), binding source-quality states,
  PIT observation history with corrections, official-vs-curated lenses with
  contribution/concentration, calibrated descriptive method, research workflow, and
  product-learning events — all context_only.
status: active
program: china-system
repos: [macro]
owner: fable
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md
  - research/flow_observatory/
  - engine/flow_observatory/
  - data/flow_observatory/
decisions:
  - DEC:FLOW-OBSERVATORY-V2-ARCHITECTURE-FREEZE
landmines:
  - "engine/flow_velocity.py's in-code honesty gate (per-name CN fund-flow rank-IC ≈
    −0.008, never scored into allocation) survives every wave; validation_meta group-flow
    forecast weights stay zero."
  - "engine/cn_theme_tape.py consumes desk.json ashare_sectors state/state_zh verbatim and
    tests/test_cn_theme_tape.py pins the exact strings — any vocabulary change updates the
    consumer + tests in the same PR, after a consumer sweep (~15 unverified grep-hit
    readers listed in masterplan §2.2)."
  - "The committed site page carries post-render externalized CSS (assets/css/*.css?v=);
    the canonical artifact = builder output + lib/pages.py sweeps — never hand-commit raw
    builder output as site truth."
  - "Northbound aggregate is HISTORICAL_ONLY (frozen 2024-08-16); no per-stock Northbound
    accumulation product (china-alpha do_not_redo)."
do_not_redo:
  - "No composite flow/conviction score or cross-source rank (DNR:KILL-FUSED-COMPOSITE,
    DNR:KILL-REGIME-SCORECARD; GROUP_READS_MASTERPLAN G0-2)."
  - "No second membership truth store — curated themes stay baskets_china/baskets_hk;
    official SW L1 membership extends collectors/china_sectors.py with forward accrual,
    never hindsight backfill, never relabeled curated baskets."
  - "No second alert engine, analytics plane, market calendar, or flow collector for an
    existing source."
waves:
  - {id: F0, title: "Architecture freeze + durable records", status: done, pr: 6776}
  - {id: W1, title: "Trust strip, changed-today, absolute-vs-relative truth", status: done, pr: 6780, depends_on: [F0]}
  - {id: W2, title: "Binding source quality + fail-visible publication", status: done, pr: 6791, depends_on: [W1]}
  - {id: W3, title: "PIT observation history, transitions, corrections", status: in_progress, depends_on: [W2]}
  - {id: W4, title: "Official/curated lenses, coverage, contribution, concentration", status: todo, depends_on: [W3]}
  - {id: W5, title: "Preregistered method evaluation + threshold calibration", status: todo, depends_on: [W4]}
  - {id: W6, title: "History, compare, drilldown, research workflow", status: todo, depends_on: [W5]}
  - {id: W7, title: "Product-learning instrumentation via /api/collect", status: todo, depends_on: [W6]}
  - {id: FINAL, title: "Adversarial integrated acceptance vs the 12 program fixtures", status: todo, depends_on: [W7]}
next_action: "Execute W3 (PIT observation ledger + corrections) per research/flow_observatory/W3_SPEC.md, then W4..W7 + final acceptance per masterplan §12."
---

# Flow Observatory V2

Canonical plan: `research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md` (outcome, archaeology,
frozen contracts, wave graph, no-rebuild boundaries). Program parent: `china-system`
(flow_velocity.html is CN/HK cross-border + A-share market mechanics; no prior workstream
owned this surface — verified `grep -rn flow_velocity agentos/` empty at freeze;
WS-CHINA-ALPHA-INTELLIGENCE is the disjoint Prophet-ordering sibling under the same
program; WS-INTRADAY-FLOW-P0-RECOVERY owns a different page).
