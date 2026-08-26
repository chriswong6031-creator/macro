# Sol Adversarial Review Gate — Canada Stock Dashboard V3.7

Status: **SOL REVIEW FREEZE — implementation owned by the existing Fable HK+Canada regional carrier**

Purpose: prevent Canada V3.7 from becoming visually correct while semantically wrong, incomplete, or duplicative.

## 1. Primary outcome

Within five seconds, a Canada user should be able to answer:

1. What are the highest-priority names?
2. What can I do now?
3. Where is leadership concentrated?
4. Can I switch from glance mode to a real research table without changing the underlying population?
5. Where do I verify historical performance and methodology?

The V3.7 implementation passes only when the entire journey works in production.

## 2. Non-negotiable authority laws

- **Selection != Action != Lifecycle != Authority**.
- Canada remains a **screen / evidence-accruing** surface unless the canonical producer grants stronger authority.
- `Top Picks` may be a deterministic presentation subset of the existing canonical ordered Canada screen, but it must not create a new score, ranker, or official-pick claim.
- Action owns hue. Top-Pick selection styling stays neutral/cool and subtle.
- Board intelligence freshness and live quote freshness are separate clocks.
- Missing != zero. Missing action != WAIT. Missing theme membership != inferred membership.

## 3. Top Picks review gate

Fable must identify the exact canonical source of membership before merge.

Acceptable:
- an existing owner emits a focused/featured/top subset; or
- the existing canonical screen has an accepted deterministic ordered projection and V3.7 merely reveals the already-established first-N focus set without changing order.

Reject:
- client-side re-ranking;
- a new composite score;
- arbitrary `slice(0, 5)` with no accepted owner rule;
- visual treatment implying official-pick authority.

Tests:
- Top Picks selected -> only the canonical focus subset is in the visible/accessibility surface.
- All Candidates selected -> full owner-native population.
- Leadership filters can reduce either population without silently switching modes.
- Result count distinguishes global population size from filtered visible count.

## 4. Grid / Table XOR gate

Grid and Table are two presentations of one stateful Prophet workspace.

Required:
- Grid active -> candidate cards only.
- Table active -> table only.
- Do not append table below cards.
- Prefer rendering only the active representation; do not leave a second accessible duplicate population hidden in a way that can double-count analytics, quote bindings, keyboard navigation, or screen-reader content.
- Population mode and filters persist across presentation changes.
- Same ticker opens the same canonical Terminal destination in either view.

Reject if:
- the table uses a separately built candidate population;
- view change re-fetches/re-ranks differently;
- live quote updater sees duplicate active records;
- hidden duplicated rows remain keyboard/screen-reader reachable.

## 5. Table workbench gate

Restore power without prose.

Required where source-backed:
- ticker/name search;
- action/lane filter;
- sector filter;
- theme filter;
- freshness filter only if canonical freshness exists;
- sort;
- column chooser.

No `Why here` or `Key caveat` prose columns.

Filter law:
`selected population -> leadership filter -> table filters -> user sort -> presentation`

Sorting never changes underlying owner rank; it changes only the user's table ordering for that view.

## 6. Track Record / Evidence & Record gate

Track Record was removed accidentally and must return through the existing canonical outcome owner.

At rest:
- `Track Record ->`
- `Signal History ->` if canonical route exists
- `Methodology ->`
- receipts/data provenance only where an existing route exists.

Do not ship placeholder performance statistics.
Do not create another historical ledger.
If an entry is unavailable, omit it or label it unavailable rather than inventing a target URL/stat.

Evidence & Record remains below Leadership and cannot displace Prophet from the first decision viewport.

## 7. Leadership gate — IMPORTANT HARDENING

The V3.7 mockup's generic tone-bucket summary is **reference-only and must not become production semantic authority**.

Expanded Leadership must preserve **owner-native stance labels**.

For Canada, expected native examples already observed include:
- theme stances such as `Accumulate`, `Hold`, `Trim`;
- sector stances such as `Entry Now`, `In Favour`.

Do not translate these into a fake universal lifecycle such as `Act Now / Setting Up / Watch / Reduce` unless an existing canonical owner already emits that partition.

Recommended expanded summary pattern:

- `Themes · 3 Accumulate · 1 Hold · 1 Trim`
- `Sectors · 2 Entry Now · 3 In Favour`

Then show the ranked Theme and Sector tables with their exact native stance, breadth/count, and representative leaders.

This recovers the useful old actionability without inventing cross-market semantics.

## 8. Leading Now gate

At rest:
- leading Theme;
- leading Sector;
- optional deterministic What Changed cue only if a real prior-vs-current comparison exists.

Do not show a permanent no-op message such as `No fresh Prophet signals`.
Do not manufacture a change sentence from current-state counts alone.

## 9. Card gate

Preserve the approved compact Prophet/V4-derived card family.

- system/San Francisco/Inter sans ticker;
- price + live % change high emphasis;
- Canada direction colors: green up / red down;
- action badge dominant;
- one-hop Terminal click;
- no drawer interception;
- no explanatory paragraphs;
- lifecycle may remain compact structural metadata but must not overpower action/price.

No new stock-card family.

## 10. Failure-state gate

Must behave correctly for:
- Top Picks empty;
- leadership filter yields zero Top Picks but All Candidates has matches;
- quote missing;
- board stale while quote live;
- theme artifact missing;
- Track Record unavailable;
- partial candidate coverage;
- composer JS error / data fetch failure.

Progressive enhancement must leave an existing usable surface rather than blanking the page.

## 11. Production visual matrix

Required before `PROVEN_LIVE`:

- light desktop;
- dark desktop;
- 390px mobile;
- EN;
- ZH if current Canada product contract promises it;
- Top Picks;
- All Candidates;
- Grid;
- Table;
- search/filter/sort/column chooser;
- Leadership expansion;
- Track Record route;
- Terminal route;
- live quote refresh.

## 12. Sol rejection triggers

Reject the PR even if CI is green if any of these are true:

- Top Picks is decorative rather than population-controlling.
- Top Picks membership has no canonical rule.
- Table appends below Grid.
- Grid and Table use different data populations.
- Track Record is represented by placeholder links/stats.
- generic Leadership action labels replace owner-native stances.
- presentation migration changes screen rank/action logic.
- Canada starts claiming official-pick authority.
- a new quote, history, entitlement, lifecycle, or ranking plane appears.
- mobile remains two-up.
- production proof is only screenshots of static/mock data.

## 13. Acceptance statement

Canada V3.7 is accepted only if it is simultaneously:

- simpler than the legacy board at first glance;
- more functionally complete than V3.6;
- at least as powerful as the useful legacy workflows when the user deliberately enters deeper modes;
- authority-honest.
