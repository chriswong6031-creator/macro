---
workstream: WS:STOCK-IDENTITY
session: bottom-up-stock-identity-bcf64e (Claude, PR-0 commissioning session)
model: fable
ended_because: ci_handoff
mission: >
  PR-0 for Bottom-Up Stock Identity & Expert Routing: full prior-work archaeology,
  canonical expert-taxonomy census, frozen research contract with method law and
  PR-1..8 sequence, Agent OS records, adversarial review — docs only, no build wave.
state_before: >
  No program existed (LER DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED had explicitly
  declined to mint it, recording it as a future dependency). Prior related work:
  PTT (audition killed two-ruler, structure arm open), PSS (families killed,
  codex shipped), Stock Personality (display-tier, compat null), SEA (shipped),
  Live Entry Radar PR-0 unmerged (#5578).
changed:
  - path: research/STOCK_IDENTITY_PR0_ARCHAEOLOGY.md
    what: NEW — archaeology map (prior work, kill scopes, expert taxonomy census both repos, interfaces, data substrate, disambiguation)
  - path: research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md
    what: NEW — frozen PR-0 research contract (charter/gates, method law, fingerprint/epoch/ruler/fit/validation/pooling/abstention designs, interfaces, pilot, PR sequence, adversarial review §15, open rulings §16)
  - path: agentos/workstreams/WS-STOCK-IDENTITY.md
    what: NEW — workstream (program market-timing-intelligence, p0 US_PROPHET_ENTRY_TIMING, W0-W7)
  - path: agentos/decisions/DEC-SI-METHOD-LAW-CHANNELS.md
    what: NEW — the method-law decision (3 lawful channels; ratification requested in masterplan §16.1)
  - path: agentos/handoffs/STOCK-IDENTITY-2026-08-13.md
    what: NEW — this handoff
verified:
  - claim: Agent OS records are schema-valid
    command: python3 scripts/agentos.py validate
    result: "0 errors, 5 warnings (phantom-owns-path — paths intentionally not yet built; LER precedent)"
  - claim: PR is docs+records only, no engine/production surface touched
    command: git diff --stat origin/main...HEAD
    result: "research/*.md + agentos/*.md only"
  - claim: KILL-OUTCOME-AUDITION scope (two-ruler, carve-out) read from the registry row itself
    command: rg -n "KILL-OUTCOME-AUDITION" research/DO_NOT_REBUILD.md
    result: row present; scope quoted in archaeology §1.1/§3
  - claim: Adversarial review executed by an independent opus reviewer against the 9 commissioned attack vectors
    command: reviewer agent over both docs (findings recorded in masterplan §15)
    result: findings folded; blockers resolved before freeze
unverified:
  - "Census lane file:line citations were spot-checked by the reviewer pass, not 100% re-read by the main loop; archaeology §4.5 carries the census's own uncertainty list (STARTER stage wiring, Terminal twin parity, harness/e_factors.py location, T2-T4 history, basket-state PIT availability)."
  - "BABA/AEM/PAAS/WPM/AG deep TR-adjusted store presence — flagged as a PR-1 data gate, not resolved here."
unresolved:
  - "Masterplan §16 open rulings (method-law ratification, ruler orientation, GO/NO-GO gate, Radar coupling, tops sibling, registry row, CN scope) — returned to Sol/operator; W1 is gated on them."
next_actions:
  - "Sol/operator: rule on masterplan §16 (esp. §16.1 method law and §16.4 PR-4 GO/NO-GO)."
  - "W1 session (post-ruling): Identity Atlas v0 per masterplan §14 PR-1 row — resolve pilot data gates first."
  - "Revalidate Live Entry Radar state (#5578 merge status, entry_event.v1 schema) at W1 start."
do_not_redo:
  - "Do not re-run the five archaeology censuses — results + uncertainty lists are in research/STOCK_IDENTITY_PR0_ARCHAEOLOGY.md."
  - "Do not re-test per-name outcome audition under any ruler (DNR:KILL-OUTCOME-AUDITION, two-ruler)."
  - "Do not re-derive the expert taxonomy from UI labels — archaeology §4 maps producers; family keys are minted from emitter receipts at W2."
danger_areas:
  - "Prophet/Radar path partition (masterplan G-8) — every future engine PR prints a clean git diff --stat on the guarded paths."
  - "massive_stock_day is raw/unadjusted — prohibited for behavioral math (masterplan §9.7)."
  - "Reused-ticker splices (ECHO/SATS class) — identity hygiene checks before trusting any joined per-ticker history."
prs: [5583]
decisions:
  - DEC:SI-METHOD-LAW-CHANNELS
---

## Note

PR-0 stop condition honored: this session ends at `scripts/ci_handoff.py` with PR #5583
armed for the sweeper; no W1 work was started. The commissioning handoff's 13 deliverables
map to masterplan §0-§16 + archaeology §1-§8 (deliverable index in masterplan §0).
