# Sol V3.7 — Reference Artifact vs Production Addendum

Status: **READ-ONLY SOL REVIEW LAW**  
Purpose: prevent the approved interactive reference from being copied literally where its fixture/prototype behavior is intentionally weaker than production authority requirements.

The V3.7 HTML is a composition reference. It is **not** a semantic/data contract.

## 1. Default ordering is owner-native, never prototype Priority sorting

The reference currently initializes `state.sort = priority` and `filteredCards()` sorts records by the fixture `priority` field even in Grid mode.

Production must NOT inherit that behavior unless the current canonical producer explicitly owns that exact priority order.

Rules:
- Grid default order = canonical producer order/rank.
- Top Picks default order = canonical Top Picks/focus owner order.
- All Candidates default order = canonical broader-population order.
- Table may expose explicit user sorting, including Priority, only if that field already exists and is owner-backed.
- Returning to the default/canonical sort must restore producer order.
- A presentation composer may never become a new cross-market ranker.

Reject any PR where the browser composer performs the primary ranking itself.

## 2. Top Picks membership must be canonical

The prototype uses a fixture boolean (`c.top`) to demonstrate the interaction.

Production must trace membership to the current owner-native selection contract. Do not implement `slice(0, N)`, `rank <= N`, or a new score threshold merely to match the mockup count.

Selection remains separate from Action, Lifecycle and Authority.

## 3. Ticker typography correction

The approved visual/product ruling is:

`San Francisco / Inter / system sans`

The current HTML reference still contains `.ticker { font-family: var(--mono) }` in its internal CSS. This is a prototype inconsistency and must NOT be copied to production.

Ticker, company identity and decision typography should use the product sans stack. Numeric price fields may retain tabular-number treatment.

## 4. LIVE treatment is not universal

The reference currently renders a Prophet `LIVE` chip and card-footer `LIVE` text generically.

Production rules:
- Canada may show LIVE only from the proven canonical live quote plane, with Board vintage kept separate.
- HK must not show LIVE or live % changes until a canonical HK live quote/change owner is proven.
- China/HK direction colors are Asia convention only when true change data exists.
- Error/empty copy must never say another surface is "still live" unless that surface's own freshness contract proves it.
- Generic labels such as `Full live board` must become market/freshness-aware.

## 5. Expanded Leadership buckets in the prototype are visual only

The mockup currently maps fixture tones into generic buckets such as:
- Act now
- Setting up
- Watch / manage
- Reduce / stand aside

This is NOT a cross-market ontology.

Production must summarize exact owner-native states for each market. Examples:
- Canada: preserve current canonical Accumulate / Hold / Trim and Entry Now / In Favour semantics where those are the actual owners.
- HK: preserve current native stances such as Act now / In favour / Mixed / Watch if still current after repin.

Never translate a producer state merely to fit a shared four-cell component.

## 6. Evidence & Record links in the prototype are placeholders

The reference uses `href="#"` for Track Record, Signal History, Methodology and Receipts.

Production acceptance requires:
- real canonical destinations;
- existing record/history owner;
- no placeholder statistics;
- no new outcome ledger;
- explicit unavailable state if a route/owner does not exist.

Track Record restored visually but disconnected from real history = FAIL.

## 7. Filters must use canonical IDs and source-backed fields

The prototype demonstrates filtering using English display labels for theme/sector equality.

Production should use canonical IDs/keys wherever available. Display-label equality must not become identity truth.

Rules:
- theme filter only if canonical membership exists;
- sector filter only owner-backed;
- action/lane filter uses market-native exact states;
- freshness filter uses a real timestamp/newness contract, not the browser clock or a visual `New` badge inferred at runtime;
- missing membership/state never maps to a default bucket.

## 8. Stable filter options vs selected-population results

It is acceptable for the Table workbench to keep a stable option list derived from the broader canonical candidate universe while Top Picks is selected, because controls should not jump around when switching population.

However:
- selecting a group/action with zero matching Top Picks must show an explicit zero state such as `No Top Picks in this group`;
- it must never silently switch to All Candidates;
- counts must describe the actually selected population.

## 9. Grid/Table state law

The HTML reference demonstrates XOR correctly. Production must preserve it:
- Grid DOM visible => candidate table not visible/duplicated.
- Table visible => candidate cards not visible/duplicated.
- both consume the same selected population and active filters.

Do not simply hide one with styling while retaining a second independently initialized data consumer that can drift. Prefer one presentation state over one canonical record projection.

## 10. Table sorting cannot rewrite canonical selection

User-requested Table sorting changes presentation order only.

It may not:
- change Top Picks membership;
- change candidate authority/action;
- persist a newly sorted order back into an owner store;
- redefine the Grid order unless the user explicitly chooses the same presentation sort there and product law authorizes it.

## 11. Card microcharts in the reference are not evidence

The prototype explicitly uses visual-sample microcharts.

Production must preserve the existing real chart/sparkline owner or omit the visual. Never synthesize a decorative trend line that could be interpreted as real price history.

## 12. Leadership filtering is a projection, not authority transfer

Selecting a Theme/Sector may filter Prophet records where membership is canonical.

It must not:
- change Top Pick membership;
- change action;
- change lifecycle;
- create a new recommendation because the group is highly ranked.

If Top Picks filtered to a group is empty but All Candidates contains records, preserve the empty Top Picks state and invite the user to switch population deliberately.

## 13. Error-state locality

One producer failure must degrade locally:
- Prophet failure does not imply Leadership failure;
- Leadership stale does not imply Prophet stale;
- quote failure does not erase board action/rank if those remain valid;
- Track Record unavailable does not erase Prophet;
- theme artifact missing removes/marks theme-dependent controls only.

Avoid global status prose that overstates freshness or outage scope.

## 14. Prototype destinations vs production navigation

Reference `data-toast` links are visual placeholders only.

Production must retain real routes for:
- Terminal stock click today;
- Track Record;
- Signal History if current;
- Methodology;
- Sector Intelligence / thematic explorer;
- specialist research tools.

A visible control with no real destination does not count as restored capability.

## 15. Reference-only counts and fixture labels

Any count, timestamp, rank, action, stance, zone, theme or price embedded in the local HTML is a review fixture. Production must bind to current canonical source outputs.

The mockup must never be used as a source of truth for:
- `5 Top Picks`;
- `10 candidates`;
- theme/sector leaders;
- Track Record statistics;
- freshness;
- action labels.

## 16. Sol acceptance addition

When Fable returns a Canada V3.7 PR, Sol review must separately answer:

1. What exact owner determines Top Picks membership?
2. What exact owner determines default candidate order?
3. Does Grid preserve that order without client-side reranking?
4. What exact source powers Fresh Only?
5. What exact canonical IDs power theme/sector filters?
6. What exact route/owner powers Track Record?
7. What exact producer states appear in Expanded Leadership?
8. Which LIVE claims are quote-backed and which are board-vintage claims?
9. Does every visible restored feature have a real production consumer/destination?
10. Is any mockup fixture being treated as semantic truth?

Any ambiguous answer holds acceptance.

## Final law

> **The reference owns composition and interaction intent. Producers own facts, ranking, membership, state, freshness and history.**
