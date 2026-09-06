---
workstream: WS:FLOW-OBSERVATORY-V2
session: worktree-flow-observatory-v2-fable-bced27
model: fable
ended_because: complete
mission: >
  F0 of the Flow Observatory V2 program (operation
  macro-flow-observatory-v2-program-20260902-sol-001): reconcile current state, freeze
  architecture/design/wave plan, and land the durable records so any session can execute
  W1..W7 without the commissioning conversation.
state_before: >
  No workstream owned flow_velocity.html. The live page conflated absolute flow with
  relative pressure (Autos vel +2.58σ labeled "inflow cooling" while raw 4wk flow −0.9%;
  Southbound "accelerating out" beside +¥7.1B 1m absolute), used "big money"/
  "institutions" for order-size and event-selected proxies, rendered one top-level as_of
  while the HK leg trailed a day unrendered, and had advisory-only staleness (::warning)
  with no in-page stale state (12-day #4676 freeze precedent).
changed:
  - path: research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md
    what: "New — full F0 freeze: outcome, archaeology (§2 with fixture measurements and
      pipeline map), source taxonomy (§3), flow_observatory.v2 contract as additive
      desk.json evolution (§4), time/quality/correction law (§5), frozen EN/ZH vocabulary
      incl. five-state quadrant enum (§6), archetype-E experience architecture (§7),
      preregistered method plan (§8), official-vs-curated boundary (§9), wave graph
      F0..W7+final (§12), no-rebuild boundaries (§13), rulings with rejected
      alternatives (§14), collision/path map (§15)."
  - path: agentos/workstreams/WS-FLOW-OBSERVATORY-V2.md
    what: "New workstream record under program china-system with waves, landmines,
      do_not_redo."
  - path: agentos/decisions/DEC-FLOW-OBSERVATORY-V2-ARCHITECTURE-FREEZE.md
    what: "New decision record for the freeze (contract home, vocabulary migration,
      quality machine, ledger, SW L1 lens, wave decomposition) with alternatives."
  - path: agentos/handoffs/FLOW-OBSERVATORY-V2-2026-09-02.md
    what: "This handoff."
verified:
  - claim: "The canonical builder reproduces the live page from real committed data"
    command: "python3 -m scripts.build_flow_velocity (in a site+data materialized
      worktree at 2a1c871d0a6d)"
    result: "wrote site/flow_velocity.html (22 sectors, 1518 names, 341 KB); diff vs
      committed page is the asset-externalization delta only (inline CSS vs
      assets/css/*.css?v=), confirming the canonical artifact includes lib/pages.py
      post-render sweeps"
  - claim: "The conflation fixtures are live in committed data"
    command: "python3 json parse of site/flowdata/desk.json @2a1c871d0a6d"
    result: "southbound flow_1m_b=+7.1, vel 1m=−1.52, state='accelerating out'; cn_autos
      vel=+2.58, rate_4wk=−0.9, rate_norm=−2.8, rate_rel=+1.9, state='inflow cooling';
      hk_names as_of=2026-08-31 vs top-level as_of=2026-09-01; sector states 6/4/11/1"
  - claim: "No collision on owned paths"
    command: "gh pr list --state open (60 PRs, title/body searches for
      flow_velocity/flow observatory/tushare/southbound) + git diff --name-only
      merge-base checks on claude/trumpflow-promote and
      codex/hk-sector-flow-rotation-research"
    result: "zero matching PRs; zero owned-path overlap on both flagged branches"
  - claim: "No existing workstream owns the surface"
    command: "grep -rn flow_velocity agentos/"
    result: "zero hits across workstreams/decisions/discoveries/handoffs"
  - claim: "Official CN sector constituent membership is NOT_BUILT repo-wide"
    command: "grep -rE 'index_member|index_classify|sw_index_cons|stock_board_industry'
      collectors/ engine/ scripts/"
    result: "zero hits; collectors/china_sectors.py holds SW L1 INDEX OHLCV/valuation
      only (31 codes, akshare, keyless)"
unverified:
  - claim: "akshare exposes a keyless SW L1 constituent-membership endpoint usable by
      collectors/china_sectors.py"
    what_would_verify: "W4 implementation spike: call the candidate endpoint(s) and
      inspect returned membership shape; masterplan §9 carries the designed-unavailable
      fallback if this fails"
  - claim: "The ~15 additional grep-hit files reading desk.json (admin/brief.py,
      scripts/build_ai_desk_page.py, scripts/oracle_nightly.py …) do not consume
      state/state_zh verbatim"
    what_would_verify: "W1's mandatory consumer sweep before the vocabulary migration"
unresolved:
  - "Exact quality-band constants (per-leg trading-day budgets, coverage collapse
    thresholds) — calibrated with evidence inside W2 per masterplan §5/§14.7."
  - "Method/threshold selection — preregistered evaluation inside W5 per §8."
next_actions:
  - "Merge this F0 PR (docs+records only; no production behavior change)."
  - "W1 from fresh origin/main: fresh worktree + claude/flow-observatory-v2-w1 branch;
    failing tests first (masterplan §12 W1 row + program packet W1 test list); consumer
    sweep; implement trust strip dates/coverage, quadrant enum + vocabulary migration
    (incl. engine/cn_theme_tape.py + tests), market_read breadth with neutral/unscored
    counts, minimal state_log.jsonl + what-changed; canonical rebuild; browser evidence
    matrix dark/light × EN/ZH × 1440/390; PR → green CI → merge → live verify."
  - "Then W2..W7 + final acceptance serially per masterplan §12."
do_not_redo:
  - "Do not re-derive the archaeology — masterplan §2 carries the verified pipeline map
    with file:line citations (three census packets, 2026-09-02)."
  - "Do not propose a parallel observatory.json, a new program/lobe, hindsight sector
    membership, or a composite flow score — rejected with reasons in DEC record +
    masterplan §14."
  - "Do not treat the current desk_guard budgets as wrong by assumption — the 4-day
    calendar budget has not misfired on record; W2 must measure before replacing
    (masterplan §14.7)."
danger_areas:
  - "engine/cn_theme_tape.py + tests/test_cn_theme_tape.py pin the exact current state
    strings — vocabulary migration without same-PR consumer update reds CI or, worse,
    ships mixed vocabulary."
  - "Sparse worktrees: site/ and data/ are omitted by default; opt in before any build
    (python3 scripts/worktree_sparse.py add site / add data). A write into an omitted
    tree truncates the committed artifact."
  - "site/flow_velocity.html committed bytes include post-render asset sweeps — rebuild
    through the canonical path; never hand-commit raw builder output."
  - "Build lanes are additive-resilient (brun); a red inside build_flow_velocity does
    not fail the workflow — W2's binding states must not accidentally make one optional
    leg fail the whole asia-close job."
prs: []
decisions:
  - DEC:FLOW-OBSERVATORY-V2-ARCHITECTURE-FREEZE
---

# F0 handoff — Flow Observatory V2 freeze

Everything a stranger needs is in `research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md`.
This handoff records what F0 verified, what it deliberately deferred into waves (with
decision rules), and the exact W1 entry point.
