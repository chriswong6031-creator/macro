# Independent Data and Authority Critic

- Critic identity: `codex-xpv2-data-authority-20260820`
- Frozen artifact commit: `da83976ece01c54d5ab07307e68118693e100a58`
- Overall verdict: **BLOCK**
- Intelligence Hub verdict: **PASS_WITH_CONDITIONS**
- Sector Central verdict: **BLOCK**
- Review mode: read-only, independent, rationale quarantined

Sector Central must not be promoted as canonical from this R2 reference without data-authority repairs. The frozen artifact can remain archived, but the Sector Central candidate currently changes producer truth in action-state, score/performance, confluence-row, bottoming-watch, and movement-context surfaces.

Intelligence Hub is materially aligned with the current producer contract. It is `PASS_WITH_CONDITIONS` because production still contains stale tooltip copy that says policy votes; the R2 candidate fixes that language, but implementation has to prove the old production copy is removed.

## Findings

### DAC-001 — BLOCK — Sector Central Explore assigns wrong action states, scores, and performance

Candidate evidence:

- `MASTERMIND_SECTOR_CENTRAL_V2_R2_FREEZE_CANDIDATE.html:895-902`
- `Memory, HBM & Storage`: score `72`, performance `+21.7%`, cycle `Improving`, action `Almost ready`.
- `Health Care`: score `74`, performance `+9.4%`, cycle `Trending`, action `Buy now`.
- `Semicap Equipment`: score `58`, performance `−10.5%`, action `Stand aside`.
- `Data-Center Power & Cooling`: score `48`, performance `+8.6%`, action `Watch`.

Canonical evidence:

- `engine/sector_central.py:337-430` defines conviction as state → gate → confirm → risk-size cap, not a generic heat/performance score.
- `engine/sector_central.py:367-401` says the validated forward lever is the trend gate/drawdown-risk control; risk-size can only shave bullish conviction and never lift or change direction.
- Current `site/basketdata/action_board.json` says:
  - `Memory, HBM & Storage`: `AVOID`, score `49`, `reco: avoid`, `perf_20d_rel: -0.0959`.
  - `Data-Center Power & Cooling`: `AVOID`, score `38`, `reco: avoid`, `perf_20d_rel: -0.0841`.
  - `Power & Grid Buildout`: `AVOID`, score `35`, `reco: avoid`, `perf_20d_rel: -0.061`.
- Current `site/sectordata/sector_central.json` says:
  - `XLV / Health Care`: conviction score `23`, `Reduce`, direction `down`.
  - `XLC / Communication Services`: conviction score `55`, `Neutral`, `split_view: true`; not a clean Almost ready action call.
- `templates/sector_central.html.j2:2203-2205` says the lanes are the only gated, graded calls; everything below is context.

Required repair:

- Do not hardcode a blended score/20d/cycle/action row unless every field names its producer and preserves authority.
- For themes, use the action-board/theme-intel payload exactly.
- For sectors, use `site/sectordata/sector_central.json` conviction fields exactly.
- If a row is context-only, label it context-only and remove action words unless the canonical action board supplies them.

### DAC-002 — BLOCK — Health Care context leadership is converted into action authority

Candidate evidence:

- Line 419: “Health care is taking the lead as AI and semis cool.”
- Line 472: “Health Care moved into the top three.”
- Line 899: Health Care score `74`, action `Buy now`.

Canonical evidence:

- `engine/sector_central.py:21-26` says US relative momentum is a focus lens, not alpha; it fabricates no directional odds forecast, and baskets are context.
- `engine/sector_central.py:175-178` makes heat display context only.
- Current XLV payload is conviction score `23`, `Reduce`, direction `down`, rotation `extended — watch`.
- Current action-board Health Care row is `on_the_run`, `extended · wait for pullback`, not `Buy now`.
- `site/basketdata/si_handoff.json` has `us_sector_health` as display/context strength with `reco: hold`, not Sector Central Buy now authority.

Required repair:

- “Health Care heat/equal-weight context is strong” may be used as context.
- “Health Care sector is Buy now” may not be used.
- If the hero describes leadership, state that it is tape/heat/context leadership and do not overwrite the action lane.
- The Explore sector row must show the sector producer truth (`Health Care / XLV / 23 / Reduce`) or omit the action field.

### DAC-003 — BLOCK — Display-only bottoming watch is retitled as an upgrade pipeline

Candidate evidence:

- Lines 460-465 call the section `Early turns` with “Watch until the entry state upgrades.”
- Power & Grid Buildout, Nuclear & SMR Power, and Data-Center Power & Cooling are labeled `Early turn`.

Canonical evidence:

- `scripts/build_sector_central.py:170-188` makes bottoming watch display-tier and binds its words to `bottoming_authority`.
- Current `site/basketdata/baskets.json` says `tier: display`, `may_rank: false`, `may_gate: false`, `may_size: false`, and `may_escalate: false`.
- Its null disclosure is: “A forming low on its own has not been shown to predict what comes next — watch, don't chase.”
- The action board simultaneously places all three names on the avoid side, with scores `35`, `36`, and `38`.

Required repair:

- Restore `Bottoming watch` and explicitly call it display-only.
- Include the null disclosure or a materially equivalent statement.
- Do not describe rows as entry-state upgrades unless the action-board lane actually upgrades.
- Preserve the simultaneous avoid/reduce read; this is a dual-read conflict surface, not an opportunity pipeline.

### DAC-004 — BLOCK — Confluence mixes theme rows into the selected S&P 500 subsector universe

Candidate evidence:

- Lines 700-721 select `S&P 500 65` for `Subsector Confluence · entry timing`.
- Tailwind rows include Medical Devices, Big Pharma, Gold Miners, and Non-AI Software.
- Late/fading rows include Oil & Gas Midstream, Oil & Gas Refining & Marketing, Packaging & Containers, and Medical Instruments & Supplies.

Canonical evidence:

- `templates/subsectors.js:39-43` maps the four datasets to S&P subsectors, baskets, Nasdaq, and Russell.
- `templates/subsectors.js:289-315` filters the current selected universe: buy side is `entry_now`; avoid side is `headwind` or `late`.
- Current `site/marketdata/subsector_confluence.json` S&P tailwinds begin Computer Hardware, Insurance - Brokers, Packaged Foods, Railroads, Insurance - Property & Casualty, Capital Markets, Industrial Distribution, and REIT - Healthcare Facilities.
- Current late/headwind rows begin Biotechnology, Diagnostics & Research, Travel Services, Drug Manufacturers - General, Information Technology Services, Asset Management, Credit Services, and Discount Stores.
- Big Pharma, Gold Miners, and Non-AI Software are thematic/action-board names, not rows in the selected S&P tab.

Required repair:

- Generate the queues from the selected universe payload.
- If themes are shown, activate Thematic Baskets and use `basket_confluence.json`.
- Preserve producer row order unless an explicit lawful disposition defines a new sort.
- Never mix S&P labels and theme labels inside an `S&P 500 65` view.

### DAC-005 — MAJOR — Confluence labels, coverage wording, and tab order drift

Candidate evidence:

- “One group is buy-ready” and `Buy-ready` replace the canonical state label.
- Candidate tab order is S&P 500, Nasdaq-100, Russell-2000, Thematic Baskets.
- Coverage says “65 of 113 subsectors have enough live data to time · 48 remain thin.”

Canonical evidence:

- `templates/subsectors.js:81-88` defines `Entry now`, `Tailwind`, `Neutral`, `Late`, `Headwind`.
- Source dataset order is S&P subsectors, baskets, Nasdaq, Russell.
- Canonical coverage says thin groups are “listed in the table, not timed.”
- Current counts are correctly reproduced: 113 total, 65 gateable, 48 thin; class counts `1 / 16 / 21 / 18 / 9`; other universes 49 baskets, 12 Nasdaq, 93 Russell.

Required repair:

- Use `Entry now` / `现可入场`, unless `Buy-ready` has an explicit approved disposition.
- Restore the thin-but-listed honesty clause.
- Preserve canonical dataset order, or explicitly document a lawful reorder.

### DAC-006 — MAJOR — Action-board counts/order are correct, but exact copy is not

Candidate evidence:

- Counts are `4 / 5 / 5 / 3 / 27` in the correct lane order.
- Subcopy is abbreviated to `Entry confirmed`, `Near trigger`, `Trend intact`, `Late cycle`, and `No new buying`.
- ZH Stand aside is `暂时回避`.

Canonical evidence:

- `scripts/build_sector_central.py:67-73` defines the exact lane key order.
- `_us_act_now_board.html.j2:523-528` derives Stand aside from `hold + avoid`.
- Current counts are buy now 4, buy soon 5, on the run 5, take profits 3, hold 13, avoid 14, so Stand aside is 27.
- Exact canonical copy is:
  - `Entry confirmed today`.
  - `Setting up — wait for the trigger, not a buy yet`.
  - `Uptrend intact but extended · wait for a pullback`.
  - `Late in the cycle / topping — protect gains`.
  - `Stand aside` / `观望` / `Hold what you own · no new buying`.

Required repair:

- Keep the lane order and counts.
- Restore canonical subcopy or record an explicit approved disposition.
- Restore `观望` unless the bilingual language owner approves the alternate.
- Preserve that Stand aside is hold plus avoid, not a pure avoid lane.

### DAC-007 — MAJOR — Moving/handoff copy contradicts the current producer payload

Candidate evidence:

- Lines 568-570 say money is leaving semicap equipment and moving toward memory and non-AI hardware.
- Lines 578-579 show Semicap equipment → Memory & storage and → Non-AI tech & hardware.

Canonical evidence:

- Current `site/basketdata/si_handoff.json` makes theme context display-only.
- The trailing leader is Memory, HBM & Storage, health `broken`, recommendation `avoid`, score `49`.
- The challenger is Silver Miners.
- The canonical migration note says money is moving into Software and out of Semiconductors.
- Absorbing groups are Software, Materials & Mining, and Consumer Defensive; bleeding groups are Semiconductors, Semiconductors & Hardware, and Energy & Power.
- Non-AI tech is `deteriorating`, `avoid`, score `42`.
- `templates/sector_central.html.j2:2371-2378` says the movement view is display-only and ranks, gates, and sizes nothing.

Required repair:

- Bind movement copy to `si_handoff.json`: out of semiconductors, into software and secondarily materials/mining or defensives.
- Treat Memory/HBM/Storage as the broken trailing leader, not the destination.
- Keep the display-only disclaimer visible and never convert movement into action state.

### DAC-008 — CONDITION — Intelligence Hub copy is correct, but production retains stale policy-vote text

Candidate evidence:

- Lines 248-267 correctly say rank rises with evidence, runway, and leading signals; conviction breaks ties; proven feeder weakness can only reduce rank; policy is context and never votes; and this is not a trade trigger.

Canonical evidence:

- `engine/intel_hub.py:75-89` defines voting desks as news, alt, radar, and standout; policy is absent and display-only.
- `engine/intel_hub.py:617-626` computes opportunity from signal core × falsifier penalty × edge remaining × leading-gap multiplier.
- `engine/intel_hub.py:627-639` makes the signal governor de-escalation-only.
- `engine/intel_hub.py:955-958` sorts by opportunity score then composite conviction, descending.
- Policy and signal-governor tests confirm those invariants.
- Current `templates/intelligence_hub.html.j2:405-407` still says “Five desks vote on each name” and includes policy intent.

Required repair:

- Replace the stale production tooltip with the candidate/canonical wording.
- Add a regression assertion that visible ranking copy cannot describe policy intent as a voting desk.
- Preserve policy as a live display facet only.

## Correct statements confirmed

### Intelligence Hub

- The candidate BG sample aligns with current `site/intel_hub/hub.json` after rounding: opportunity score 14.7, edge remaining 0.775, early stage, T2 eligible entry gate, RS versus SPY of −13.48, with room/laggard drivers.
- “Signal, runway, then timing” is directionally correct against the producer formula.
- “Conviction breaks ties” is correct.
- “Proven feeder weakness can only reduce rank” is correct.
- “Policy is context and never votes” is correct.
- “Context only—not a trade trigger” is correct.

### Sector Central

- Action-board lane order and counts `4 / 5 / 5 / 3 / 27` are correct.
- The first three Buy now rows—Gold Miners 76, AI Agents & Applications 71, Non-AI Software 70—match the current payload.
- The first three On the run rows—Big Pharma 77, Silver Miners 76, AI Software & Platforms 65—are directionally correct.
- Confluence numeric coverage is correct: S&P 65, Nasdaq 12, Russell 93, baskets 49; S&P 65 of 113 gateable, 48 thin; spread `1 / 16 / 21 / 18 / 9`.
- Auto Manufacturers as the single current S&P `entry_now` group is correct, with the producer's extended/overbought caution retained.

## Exact required repairs

1. Replace hardcoded Explore rows with producer-bound rows, or remove action fields until each field is bound to the correct producer.
2. Correct the known wrong Explore rows: Memory/HBM/Storage is current AVOID 49 with negative 20d relative performance; Data-Center Power & Cooling is AVOID 38; Health Care sector is 23/Reduce; Communication Services is 55/Neutral/split-view.
3. Rewrite the Health Care hero so context/heat leadership cannot be read as action authority.
4. Restore Bottoming watch and its display-only, nonpredictive null disclosure; preserve avoid/reduce conflicts.
5. Regenerate Confluence rows from the active universe only.
6. Restore canonical Confluence labels, tab order or disposition, and thin-but-listed coverage language.
7. Restore exact action-lane subcopy and ZH parity, especially `观望`.
8. Bind Moving to the current handoff payload and retain its display-only disclaimer.
9. Replace Intelligence Hub's stale production policy-vote tooltip.
10. Add regression tests for policy nonvoting, bottoming-watch authority, action-board copy/counts, selected-universe Confluence rows, display-only movement, and explicit Explore producer sources.

## What must be production-proven

- Rendered Sector Central is built from current producer payloads, not hand-entered rows.
- Action-board counts match the action-board payload; lane copy and ZH match the canonical include; Stand aside is hold plus avoid.
- Bottoming-watch rows carry display-only authority and the null disclosure.
- Context views do not claim rank, gate, size, or action authority.
- Explore preserves source-specific scores and never confuses heat/RS/movement with buy authority.
- Confluence selected universe controls row identity and order; thin-but-listed honesty remains visible.
- Premium/gated rows are not leaked while full counts remain visible.
- Intelligence Hub contains no policy-voting language, ranks opportunity first with conviction only as tie-break, keeps the governor downward-only, and retains the no-trade-trigger disclaimer.
- Display rows either bind to current payloads or are explicitly marked as frozen examples.
- Proof includes frozen reference SHA, builder-output SHA, payload timestamps, rendered DOM/HTML evidence, and at least one payload-to-DOM comparison for every affected area.

## Evidence and limits

Canonical source/payload set reviewed:

- `engine/intel_hub.py`
- `templates/intelligence_hub.html.j2`
- `tests/test_intel_hub_policy_gate.py`
- `tests/test_intel_hub_w0_heals.py`
- `tests/test_signal_governor.py`
- `tests/test_intel_hub.py`
- `site/intel_hub/hub.json`
- `engine/sector_central.py`
- `scripts/build_sector_central.py`
- `templates/sector_central.html.j2`
- `templates/_us_act_now_board.html.j2`
- `templates/subsectors.js`
- `tests/test_sector_intelligence_page.py`
- `tests/test_sector_central_gate.py`
- `site/basketdata/action_board.json`
- `site/basketdata/baskets.json`
- `site/basketdata/si_handoff.json`
- `site/sectordata/sector_central.json`
- `site/marketdata/subsector_confluence.json`
- `site/marketdata/basket_confluence.json`
- `site/marketdata/subsector_confluence_nasdaq.json`
- `site/marketdata/subsector_confluence_russell.json`

Not evaluated in this lane: browser rendering, visual quality, mobile, accessibility, screenshots, or live production. Historical change-strip claims requiring prior-day provenance were not judged unless the current payload directly contradicted them. Static reference data was not treated as a defect by itself.

No files were edited by the critic, no subagents were spawned from the critic, and no implementation or repair was performed.
