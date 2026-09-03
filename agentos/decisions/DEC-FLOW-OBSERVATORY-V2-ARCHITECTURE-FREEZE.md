---
key: FLOW-OBSERVATORY-V2-ARCHITECTURE-FREEZE
question: >
  How is the Chairman-approved Flow Observatory V2 program (upgrade of
  flow_velocity.html to a source-separated, correction-safe, coverage-aware flow context
  surface) architected — ownership, data contract home, vocabulary migration, quality
  state machine, history storage, official-sector lens, and wave decomposition?
answer: >
  New workstream WS:FLOW-OBSERVATORY-V2 under program china-system. The product contract
  (flow_observatory.v2) evolves site/flowdata/desk.json ADDITIVELY in place;
  engine/flow_velocity.py keeps velocity math; a focused engine/flow_observatory/
  package (contract/quality/changes/history/groups) composes the new capabilities. The
  misleading state vocabulary is REPLACED with relative-explicit strings plus a five-state
  absolute×relative quadrant enum, with the known desk.json consumer (cn_theme_tape) and
  its pinned tests updated in the same wave. Source quality becomes a deterministic
  six-state per-leg machine with per-market trading-day budgets (lib/cn_calendar /
  lib/hk_calendar) rendered as a first-screen trust strip; product history is an
  append-only ledger (group_pulse episodes pattern, ledger-lane guarded) with revision
  rows and first-known replay, precursored by a minimal W1 state_log.jsonl; the official
  sector lens is Shenwan L1 with constituent membership accruing FORWARD from first
  collection via the existing collectors/china_sectors.py owner (honest-unavailable until
  history exists — curated baskets are never relabeled); the method keeps the #3561
  causal-demean benchmark and calibrates thresholds only through a preregistered
  descriptive evaluation. Eight serial waves (W1..W7 + final acceptance), one PR each,
  per research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md §12.
rationale: >
  Every choice extends a verified existing owner instead of minting a parallel system:
  desk.json is the artifact consumers already read (a sibling artifact splits truth);
  the current state strings are themselves the measured conflation (Autos: vel +2.58σ
  labeled "inflow cooling" while raw 4wk flow is −0.9%; Southbound: "accelerating out"
  beside +¥7.1B absolute) so additive-only fields would leave the live defect shipping
  on china.html's theme tape; desk_guard's staleness detection already exists but is
  advisory-only (::warning) with no page branch — the 12-day #4676 freeze precedent makes
  the binding state machine the wave with the highest truth leverage; group_pulse's
  nightly-guarded episodes.parquet and the sp1500 interval-membership parquet are the
  repo's proven PIT/append patterns; SW L1 index data already lives in
  collectors/china_sectors.py (keyless akshare) making it the lawful official-sector home
  while constituent membership is NOT_BUILT repo-wide; and the #3561 engine repair is
  preserved as benchmark because replacing a repaired measure without preregistered
  evidence is how measure defects recur.
alternatives:
  - option: "Parallel site/flowdata/observatory.json contract artifact"
    why_not: "Duplicate truth store for the same data; splits consumers; violates
      one-canonical-system law."
  - option: "Keep existing state vocabulary, add new fields beside it"
    why_not: "The vocabulary IS the defect (absolute words on a relative measure); the
      conflation would keep rendering via cn_theme_tape on china.html indefinitely."
  - option: "Wait for W3's ledger before any change-comparison (no W1 state_log)"
    why_not: "W1 would ship no what-changed read; a runtime git-history read on runners
      is brittle and unlawful as a data source."
  - option: "Official sectors via Tushare index_classify/index_member"
    why_not: "Entitlement tier never evaluated in-repo, token-gated, and a keyless
      extension of the existing akshare owner likely suffices; re-evaluate inside W4 only
      if akshare lacks constituents."
  - option: "New program/lobe for Flow Observatory"
    why_not: "flow_velocity.html is a product surface of china-system; a new program
      duplicates semantic architecture (packet §6 ruling; mastermind_programs.yml
      china-system purpose covers CN/HK market mechanics)."
  - option: "Hindsight backfill of official-sector membership for historical replay"
    why_not: "Violates point-in-time law; manufactures survivorship-biased history."
evidence:
  - "Census packets 2026-09-02 (three scout lanes): engine/flow_velocity.py:147-156
    (_classify vocabulary), :599-606 (single as_of fallthrough), :31-35 (honesty gate);
    scripts/build_flow_velocity.py:8,48-87,92-138 (additive build, advisory warnings);
    lib/desk_guard.py:92,98 (LEG_LAG_MAX_DAYS=4, DESK_MAX_AGE_DAYS=10);
    templates/flow_velocity.html.j2:425,739,755-757 (date rendering, no stale branch)"
  - "Committed desk.json @2a1c871d0a6d: southbound flow_1m_b=+7.1 vs vel −1.52 state
    'accelerating out'; cn_autos vel +2.58 / rate_4wk −0.9 state 'inflow cooling';
    hk_names as_of 2026-08-31 vs top-level 2026-09-01"
  - "engine/cn_theme_tape.py:247-249,460-467 + tests/test_cn_theme_tape.py:110-111
    (verbatim state-string consumer)"
  - "grep -rn flow_velocity agentos/ → zero hits; gh pr list open searches → zero
    matches; branch overlap checks (claude/trumpflow-promote,
    codex/hk-sector-flow-rotation-research) → zero owned-path overlap"
  - "collectors/china_sectors.py:18-127 (SW L1 index-only); engine/group_flow.py:252-253
    (no non-US PIT membership); data/baskets_china/membership.json (22 baskets, 5
    overlap tickers measured)"
  - "Local canonical rebuild reproduced: python3 -m scripts.build_flow_velocity → 22
    sectors / 1518 names / 341KB"
affects:
  - WS:FLOW-OBSERVATORY-V2
  - china-system
  - engine/flow_observatory/**
  - site/flowdata/**
  - data/flow_observatory/**
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-09-02
---

# Architecture freeze — Flow Observatory V2

Full freeze: `research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md` (source taxonomy §3,
data contract §4, time/correction law §5, vocabulary §6, experience architecture §7,
method plan §8, sector/theme boundary §9, wave graph §12, no-rebuild boundaries §13,
rulings + rejected alternatives §14).
