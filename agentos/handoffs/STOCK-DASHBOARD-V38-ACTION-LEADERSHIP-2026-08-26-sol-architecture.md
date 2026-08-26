---
workstream: WS:PROPHET-HK-CA-REVAMP
session: sol/stock-dashboard-v38-action-leadership-architecture-20260826
model: sol
ended_because: complete
mission: >
  Recover the high-frequency What to Act On Now customer job without restoring
  the old panel sprawl, separate action timing from trend leadership, freeze the
  V3.8 regional product architecture, and leave one autonomous Fable HK->Canada
  implementation carrier with China and US explicitly outside it.
state_before: >
  Canada V3.7 and HK V3.7 were both PROVEN_LIVE with dated production receipts.
  V3.7 preserved group-action producer truth but placed its normal consumer only
  inside Expand Leadership. HK Leadership joined RS-vs-HSI rank to independent
  Act-Now action stance, producing visually confusing combinations such as rank-1
  Reduce/Avoid. Canada sector numbering was presentation traversal order rather
  than a canonical sector-strength rank. China still had a prominent but
  over-dense What to Act On Now board and no V3.7 follower implementation.
changed:
  - path: research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md
    what: >
      Freezes the V3.8 product law Action != Leadership, restores a compact
      owner-native What to Act On Now surface above Prophet, explicitly labels
      rank basis, forbids presentation-owned numeric rank, defines market-native
      HK/Canada/China bindings, failure states, mobile behavior and production
      proof.
  - path: agentos/decisions/DEC-V38-ACTION-IS-NOT-LEADERSHIP.md
    what: >
      Records the narrow supersession of V3.7 placement semantics without
      invalidating V3.7 production receipts or reopening Prophet/Evidence/quotes.
verified:
  - claim: HK action and leadership are separate current owner axes.
    command: >
      Read templates/hk.html.j2 #sector-rotation and #act-now plus
      site/hk-stock-v36.js collectRotationRanks/collectLaneSectors/collectSectors.
    result: >
      Sector Rotation rank = descriptive RS vs HSI 20/60d; Act-Now stance =
      Buy Now/In Favour/Bottoming Watch/Reduce-Avoid. V3.7 joins, not derives,
      those axes.
  - claim: Canada V3.7 sector numbering lacks a rank owner.
    command: >
      Read site/canada-stock-v36.js collectSectors and
      site/canadabasketdata/sector_pulse_canada.json.
    result: >
      Sector rows are numbered by Act-Now lane traversal (out.length+1), while
      the separate Canada theme artifact publishes real owner ranks. V3.8 must
      remove sector numeric rank unless a fresh census finds a canonical owner.
  - claim: No open PR collision existed on the named presentation surfaces at freeze time.
    command: >
      GitHub open-PR search for hk-stock-v36, canada-stock-v36, china_stocks,
      Sector Leadership, What to Act On Now.
    result: Zero matching open PRs at freeze time.
unverified:
  - claim: The V3.8 presentation implementation exists.
    what_would_verify: >
      Fable completes the HK reference correction, production-proves it, then
      completes the Canada follower correction and production-proves it under the
      exact architecture and current-main collision state.
  - claim: China is safe to implement under current producer/collision truth.
    what_would_verify: >
      A separate post-regional China census repins population, action, rank,
      quote/freshness, Track Record and concurrent China/CN-Limit paths.
unresolved:
  - "The exact current production data may change which HK sectors instantiate the rank/action disagreement; the implementation must preserve the law under any data state."
  - "Canada may have a canonical sector rank outside the current composer; if Fable finds one, return the exact producer/contract to Sol before using it as a visible rank rather than silently widening authority."
  - "Linear projection for WS:PROPHET-HK-CA-REVAMP is known stale relative to current Agent OS; do not use it as source authority for this implementation."
next_actions:
  - "Start one Fable principal-builder carrier for V38-R1 HK. Fable re-bootstraps current protected Skillpack, current Macro main, this architecture/DEC, the V3.7 HK acceptance record and current open collisions before writing."
  - "Fable owns the autonomous loop: HK census -> bounded implementation -> adversarial review -> CI -> merge -> deploy -> entitled production proof. Routine steps do not return to Sol."
  - "On HK V3.8 PROVEN_LIVE, the same carrier continues to V38-R2 Canada: restore at-rest action lanes, preserve real theme rank, remove presentation-owned sector rank, prove production."
  - "Return to Sol only for a real product/authority conflict, required scope widening, failed production proof needing adjudication, or final HK+Canada V3.8 acceptance."
  - "Do not start China or US from this carrier."
do_not_redo:
  - "Do not rebuild or alter Prophet ranking, Top Picks ownership, Grid/Table XOR, Track Record, Terminal/research routing, quote planes, entitlement or lifecycle semantics."
  - "Do not restore the old giant action boards verbatim. Restore the customer job with capped low-density lanes."
  - "Do not derive Action from Leadership or Leadership from Action."
  - "Do not render a numeric rank without a named canonical rank owner/basis. Lane position is not rank."
  - "Do not add LIVE to HK; do not weaken sig-neu Southbound suppression or .sm-hidden rescue laws."
  - "Do not put China or US writes in the HK/Canada carrier."
danger_areas:
  - "HK rank/action disagreement is expected and valuable; a 'fix' that sorts Buy Now sectors to the top of the RS table would silently create a new ranker."
  - "Canada current sector numbering looks harmless but is presentation-owned. Removing the number is safer than naming traversal order a rank."
  - "Action-group Prophet counts are only valid when canonical group membership exists; unknown membership must not render as 0."
  - "dashboard-icons.js delivery remains edge-immutable per URL; if loader bytes change for any reason, covering render/re-stamp proof is required. Prefer no loader change."
  - "theme.js keeps live references to moved cards; preserve scoped .sm-hidden rescue rules."
prs: []
decisions:
  - DEC:V38-ACTION-IS-NOT-LEADERSHIP
---

# Fable principal-builder packet — V38-R1 HK -> V38-R2 Canada

## Observable mission

After HK R1, an entitled user can see the owner-native group action map immediately above Prophet and can separately understand the explicitly labeled trend/rotation rank below Prophet. After Canada R2, the same interaction grammar exists without inventing a sector rank.

## Authority precedence

1. Current protected Sol Skillpack loaded at Fable pickup.
2. `research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md`.
3. `agentos/decisions/DEC-V38-ACTION-IS-NOT-LEADERSHIP.md`.
4. Existing V3.7 production laws not explicitly superseded here:
   - `research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md`;
   - `research/SOL_V37_REFERENCE_ARTIFACT_PRODUCTION_ADDENDUM.md`;
   - Canada/HK V3.7 acceptance records.
5. Current producer/template/code truth on the exact pickup main SHA.

If current main or a newer accepted source law contradicts this packet, hold only the conflicting point and return it to Sol. Do not silently reinterpret the architecture.

## V38-R1 HK exact scope

Expected code surface:

- `site/hk-stock-v36.js`;
- `tests/test_hk_v37_composer.py` or a bounded successor test file if naming must advance.

Expected behavior:

- compact What to Act On Now at rest above Prophet;
- exact current owner lanes;
- max 3 rows per lane before View all;
- no at-rest performance/score tower;
- group filter preserves Top Picks/All;
- Leadership/Rotation shows explicit RS rank basis;
- Action is a separate field;
- ambiguous BOARD label removed;
- standalone Leading Now removed/absorbed if redundant;
- existing Southbound/Evidence/Research/Featured/no-LIVE/entitlement behavior unchanged.

No engine/template/data write unless Fable proves the current DOM cannot supply a required owner fact. Such a widening is a Sol return boundary.

## V38-R2 Canada exact scope

Expected code surface:

- `site/canada-stock-v36.js`;
- `tests/test_canada_v36_composer.py`.

Expected behavior:

- compact native action lanes above Prophet;
- ranked Themes retain owner `themes[].rank`;
- sector numeric rank removed unless a canonical owner is proven;
- same V3.7 population/XOR/Table/Evidence/quote/Terminal behavior retained.

## Deterministic / statistical / model behavior

The composer is deterministic presentation only. It reads existing owner DOM/artifacts. It creates no statistical signal, threshold, score or LLM-generated market interpretation.

## Required discriminating tests

- Reintroducing `setSource('all')` from an action-group activation must fail.
- Hiding What to Act On Now behind Expand Leadership only must fail.
- Replacing HK owner RS rank with lane traversal/order must fail.
- Rendering Canada sector numeric rank from traversal/order must fail.
- Removing the visible HK rank-basis label must fail.
- Restoring >3 at-rest rows per action lane must fail the product-density pin.
- Reintroducing at-rest China/legacy-style metric towers is a future China rejection trigger, not part of this carrier.
- Existing no-LIVE, .sm-hidden, sig-neu, Track Record and XOR pins remain green.

## Production proof

Run the architecture §14 matrix on the real entitled production path. Green CI alone is insufficient.

## Stop condition

This carrier stops when HK and Canada V3.8 corrections are both truthfully production-proven and durable records are merged, or earlier on a genuine Sol return boundary. It must not absorb China or US.
