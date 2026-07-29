# US Stocks Dashboard UX Simplification Handoff

- **Status:** Implementation-ready product and engineering handoff
- **Prepared:** 2026-07-29
- **Baseline:** `origin/main` at `59d4e924b1936d760993fd79fc456220a70f5ced`
- **Primary surface:** `site/us_stocks.html`
- **Primary template:** `templates/dashboard.html.j2`
- **Prophet card partial:** `templates/_prophet_card.html.j2`

## 1. Executive decision

`us_stocks.html` should become the fastest place in MastermindX to answer four questions:

1. What can I act on now?
2. What is setting up next?
3. What should I avoid, trim, or stop chasing?
4. What changed in Prophet today?

The current page contains the right raw material, but it presents too much of it at the same level. It behaves like several research terminals stacked vertically rather than a stock-picking command center.

The redesign should not remove the underlying evidence. It should change when and where evidence appears:

- Decisions first.
- The reason for each decision second.
- Full diagnostics on demand.
- Research tables on their dedicated pages.

The primary product change is therefore information architecture, not visual decoration.

## 2. Definition of success

The redesigned page succeeds when a user can identify, without scrolling:

- the best three to five entry opportunities;
- the most important wait/avoid instruction;
- any Prophet state change that requires attention;
- the page's data timestamp and freshness;
- the current market posture.

A first-time user should understand the action language without opening a tooltip.

An experienced user should be able to open the full evidence for any decision in one interaction.

## 3. Audit scope and method

The audit used the freshly fetched `origin/main` build, served locally and inspected at:

- desktop: `1280 × 720`;
- mobile: `390 × 844`;
- rendered DOM and accessible structure;
- template, generated HTML, Prophet artifact, and interaction semantics.

Production redirects unauthenticated sessions to sign-in, so the local audit is the exact repository-built surface rather than an unauthenticated production rendering.

## 4. Current-state evidence

### 4.1 Whole-page density

| Metric | Current result |
|---|---:|
| Generated HTML on disk | 949,104 bytes |
| Runtime HTML | approximately 1,147,364 characters |
| Runtime DOM elements | 16,344 |
| Desktop page height | 4,500 px |
| Mobile page height | 10,186 px |
| Links | 348 |
| Buttons | 131 |
| Help controls | 38 |
| Tooltip/help surfaces | 268 |
| Visible data tables | 5 |
| Visible text | approximately 10,501 characters |

This is too much initial interface for a page whose primary purpose is daily decision support.

### 4.2 Above-the-fold hierarchy

Desktop:

1. Global navigation
2. US Stock Dashboard header
3. Market-state strip
4. Five-lane theme/sector action board
5. Prophet Stock Signals begins at approximately 789 px

Mobile:

1. Header panel: 307 px
2. Market-state strip and spacing
3. Action board: 1,415 px
4. Prophet Stock Signals begins at approximately 1,997 px

The flagship stock-selection system therefore begins below the first viewport on desktop and roughly 2.4 screens down on mobile.

### 4.3 Action board

The current action board contains:

- five lanes;
- 37 action items in the DOM;
- theme and sector entities mixed together;
- multiple symbols, scores, timing notes, and state labels;
- a desktop-first five-column comparison.

The lanes are:

- Buy Now
- Almost Ready
- In Favour — Don't Chase
- Take Profits
- Stand Aside

The taxonomy is directionally useful, but the module currently takes priority over the individual stocks users came to see. On mobile the five columns become a long serial sequence, which makes the first lane appear more important simply because it is first.

The floating Ask Mastermind control also overlaps content near the lower-right of this module.

### 4.4 Prophet section

The Prophet panel is now the dominant product surface, but it remains too large and internally contradictory.

| Prophet panel metric | Current result |
|---|---:|
| Desktop height | 1,482 px |
| Mobile height | 3,162 px |
| Panel HTML | approximately 621,978 characters |
| Links in panel | 164 |
| Buttons in panel | 93 |
| Prophet cards in DOM | 81 |
| Cards hidden by initial pager | 76 |
| Per-card caution controls | 76 |

The heading area reports:

> 81 shown · 132 setups

The pager reports:

> Showing 12 of 84

The DOM contains 81 `.pvcard` nodes.

These counts need one authoritative definition before layout work proceeds.

Each visible Prophet card currently exposes a large set of simultaneous concepts:

- BUY, WAIT, or HOLD;
- Triggered;
- alert/caution count;
- current price;
- ticker and company;
- EDGE score;
- sector;
- Bottoming;
- Turning;
- Ready;
- Trend;
- Zone or Re-add;
- entry range;
- signal date;
- chart and additional popovers.

This is a classic case of detail fatigue. The card is trying to be:

- a scan result;
- a trade instruction;
- a setup diagnostic;
- a price chart;
- a risk report;
- a methodology explainer.

It should be a decision summary that opens those deeper layers.

### 4.5 Duplicate decision surfaces

The page currently gives users overlapping ways to find stock ideas:

- Prophet cards;
- More Fresh Triggers;
- Market Leaders;
- Turn Setups;
- sector buy/sell setups;
- theme/sector action lanes;
- accumulation watch;
- fund moves.

These are analytically distinct, but users experience them as competing recommendation lists.

The UI should make their roles explicit:

- **Prophet:** the single stock decision queue.
- **Themes/sectors:** portfolio context and priority.
- **Breadth:** risk context.
- **Flows:** supporting confirmation.
- **Labs/tables:** exploration and research.

### 4.6 Mobile behavior

At `390 px`:

- Prophet starts at approximately 1,997 px;
- Prophet occupies approximately 3,162 px;
- the page is more than 10,000 px tall;
- the Prophet grid remains two columns of approximately 154 px each;
- the action board becomes a 1,068 px single-column grid;
- 86 of 100 rendered controls are under 44 px in at least one dimension.

Two 154 px stock cards are too narrow for company names, price zones, state chips, warnings, and charts. Mobile should use one prioritized row/card per stock.

### 4.7 Accessibility

Current issues:

- all 38 help controls are non-focusable spans;
- none of the 40 sortable table headers exposes keyboard sorting;
- sortable headers do not maintain `aria-sort`;
- hover-heavy explanations are fragile on touch devices;
- dense small targets are difficult to operate;
- color and symbol combinations carry too much meaning without a single text equivalent.

WCAG 2.2's minimum target guidance is 24 × 24 CSS pixels or sufficient spacing. Important touch controls should target 44 × 44.

References:

- <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>
- <https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html>
- <https://developer.apple.com/design/human-interface-guidelines/accessibility>

### 4.8 Data trust

The latest fetched Prophet artifact is current to 2026-07-28 and contains 55 records in its `plans` array. It also has:

- `plan_count: 67`;
- `active_count: 55`;
- `gate_go: false`;
- invalidated records inside the array.

The UI must define and label:

- candidate count;
- rendered-card count;
- initially visible count;
- active plan count;
- invalidated/closed count;
- total historical plan count.

These must not be collapsed into one ambiguous “shown” number.

Because `gate_go` remains false, Prophet's authority tier must remain visible in plain language. A polished interface must not make experimental/display-tier output appear more validated than it is.

## 5. Product principles

### 5.1 Actionability over coverage

The landing page is not the place to prove that the system has many signals. It is the place to show which few signals deserve attention.

### 5.2 One decision contract

Every stock should resolve to one primary verb:

- **Buy**
- **Wait**
- **Hold**
- **Trim**
- **Exit**
- **Avoid**

Internal state names may support the verb, but they must not compete with it.

### 5.3 Progressive disclosure

Use four information levels:

1. **Global status:** freshness, market state, posture, alert count.
2. **Decision summary:** ticker, verb, price/zone, risk, one reason.
3. **Evidence drawer:** edge, cycle, trend, factors, flows, diagnostics.
4. **Research page:** full tables, history, methodology, calibration.

### 5.4 Honest emptiness

Do not fill a lane to make the page look busy. An empty Buy list is valuable information.

### 5.5 Change is more important than state

The daily landing experience should emphasize what changed since the previous build:

- new entry;
- entry closed;
- trigger fired;
- action changed;
- target or invalidation reached;
- evidence strengthened or weakened;
- data became stale.

### 5.6 Mobile is not compressed desktop

Mobile should be a one-column decision queue with secondary data omitted or moved into drawers.

## 6. Proposed page architecture

### 6.1 Desktop wireframe

```text
┌──────────────────────────────────────────────────────────────────────┐
│ STOCKS                                      As of Jul 28 EOD • Fresh │
│ Market: Mixed • Posture: Careful • Breadth: Constructive            │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ WHAT CHANGED                                                        │
│ 3 entry windows opened • 2 actions changed • 1 invalidated          │
└──────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────┬──────────────────────────────────────┐
│ PROPHET — ACT NOW             │ PROPHET — WATCH NEXT                │
│ 3–5 concise stock rows        │ 3–5 concise stock rows              │
│ Buy / Trim / Exit             │ Wait / Almost ready                 │
└───────────────────────────────┴──────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ PORTFOLIO CONTEXT                                                    │
│ Buy themes • Don't chase • Take profits • Stand aside               │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ EXPLORE                                                             │
│ All Prophet signals | Sectors | Breadth | Flows | Pick Lab          │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.2 Mobile wireframe

```text
STOCKS
As of Jul 28 EOD • Fresh
Mixed market • Careful posture

WHAT CHANGED
3 new • 2 changed • 1 invalidated

ACT NOW
[single full-width stock row]
[single full-width stock row]
[single full-width stock row]

WATCH NEXT
[single full-width stock row]
[single full-width stock row]

PORTFOLIO CONTEXT
[Buy] [Don't chase] [Trim] [Avoid]

EXPLORE
Prophet • Sectors • Breadth • Flows
```

## 7. Proposed top-level components

### 7.1 Command header

Display:

- `Stocks`;
- global as-of timestamp;
- freshness state;
- market state;
- posture;
- compact breadth label;
- one link to the full macro/risk surface.

Remove from the primary line:

- descriptive paragraph;
- multiple inline help bubbles;
- seasonal context chip;
- Pick Lab as a hero action.

Seasonality and Pick Lab can remain in secondary navigation.

### 7.2 Change digest

This becomes the first alert surface.

Show only state transitions since the prior build:

- `3 new entry windows`;
- `2 action changes`;
- `1 plan invalidated`;
- `5 names removed`;
- `data stale` when applicable.

Each item opens a single shared changes drawer. Do not render separate modal systems for track record, changes, cautions, and card detail when one drawer shell can serve them all.

### 7.3 Prophet spotlight

Default groups:

- **Act now:** Buy, Trim, Exit.
- **Watch next:** Wait, Almost Ready.

Optional third group:

- **Hold/manage:** only for plans a signed-in user follows or owns.

Do not put 81 cards in the initial DOM. Render:

- five Act Now rows;
- five Watch Next rows;
- a count and link to All Signals.

The full signal universe belongs in an in-page tab or dedicated Prophet surface loaded on demand.

### 7.4 Portfolio context

Compress the five-lane action board into a contextual strip below Prophet.

Recommended groups:

- **Favour**
- **Don't chase**
- **Trim**
- **Avoid**

“Buy Now” for themes should be renamed or visually separated from stock “Buy” actions so users do not confuse a sector allocation view with an individual security instruction.

Limit each group to three items. The full theme rationale belongs on the Baskets page.

### 7.5 Explore navigation

Replace the remaining stacked panels with a compact set of destinations:

- All Prophet Signals
- Sector Central
- Market Breadth
- Turn Setups
- Fund Flows
- Pick Lab

The page may show one-line summaries from those systems, but not full tables.

## 8. Prophet row/card contract

### 8.1 Required default content

Each default row should contain:

- ticker;
- company;
- one primary action;
- current price;
- entry or re-add zone;
- invalidation/risk level;
- one plain-English “why now” sentence;
- signal date or age;
- freshness;
- alert/follow control.

Example:

```text
TPR  Tapestry                         BUY
$150.90 • Entry $146.60–$150.90 • Risk below $141.20
Fresh turn with positive edge; entry window remains open.
Triggered Jul 27                                      Alert ○
```

### 8.2 Content moved to the evidence drawer

- EDGE score and percentile;
- alpha rank;
- Bottoming/Continuation lane;
- Turning/Ready/Trend diagnostics;
- chart;
- factor confirmation;
- insider evidence;
- GEX/options context;
- flow confirmation;
- earnings surprise;
- caution list;
- methodology;
- base-rate details;
- longer thesis.

### 8.3 Content to remove or translate

Do not show these as unexplained primary labels:

- `EDGE 96`;
- `T1`, `T2`, or internal tier notation;
- simultaneous `Bottoming`, `Turning`, `Ready`, and `Trend`;
- multiple caution symbols;
- icons such as `≈`, `◑`, or similar internal glyphs.

If an internal state changes the user action, translate it into the one-sentence reason. Otherwise keep it in diagnostics.

### 8.4 Priority and sorting

Default ordering:

1. Action severity: Exit/Trim, then Buy, then Wait.
2. Freshness: state changes today first.
3. Decision quality: underlying engine priority.
4. Concentration control: avoid displaying multiple correlated names without a same-bet warning.

The user should never need to interpret EDGE score and signal date to infer urgency.

## 9. Alert system

### 9.1 Alert-worthy events

Create an alert only when:

- a stock enters the actionable queue;
- an entry zone opens or closes;
- a Prophet trigger fires;
- the primary action changes;
- a target is hit;
- an invalidation is hit;
- a plan becomes stale;
- a critical data source fails;
- the thesis changes materially.

### 9.2 Severity

- **Critical/red:** invalidated, exit, critical data failure.
- **Warning/amber:** trim, deteriorating, do not chase, stale.
- **Action/green:** newly opened entry.
- **Watch/blue:** almost ready, trigger approaching.
- **Neutral/grey:** informational change.

### 9.3 Alert copy

Every alert must answer:

- what changed;
- when it changed;
- what the current action is;
- why the action changed.

Bad:

> Caution 3

Good:

> **DAN changed from Buy to Wait** — price moved above the preferred entry zone at the Jul 28 close.

### 9.4 Alert behavior

- Deduplicate by ticker and state transition.
- Timestamp each alert.
- Allow acknowledge/dismiss.
- Keep acknowledged history in the changes drawer.
- Keep alert preferences in one consistent control.
- Avoid per-card popovers competing with a global alert center.

## 10. Disposition of current modules

| Current module | Decision | Destination |
|---|---|---|
| Stock header | Rewrite | Compact command header |
| Market-state strip | Keep and compress | Command header |
| Seasonal context | Demote | Context drawer |
| Five-lane action board | Compress | Portfolio Context |
| Prophet grid | Replace initial view | Act Now / Watch Next rows |
| Prophet table toggle | Keep for expert view | All Prophet Signals |
| Track record | Keep | Prophet drawer/tab |
| What changed today | Promote | Change Digest |
| More Fresh Triggers | Merge | All Prophet Signals |
| Market Leaders | Move | All Prophet Signals / Discovery |
| Market Breadth | Summarize | Header; full board on Breadth page |
| Sector buy/sell table | Summarize | Sector Central |
| Turn Setups | Move | Discovery/Pick Lab |
| Accumulation Watch | Use as confirmation | Flow detail page |
| Real Fund Moves | Use as confirmation | ETF/Fund Moves page |
| Ask Mastermind floating control | Keep without occlusion | Docked responsive assistant button |

## 11. Terminology contract

### 11.1 Primary verbs

Use only:

- Buy
- Wait
- Hold
- Trim
- Exit
- Avoid

### 11.2 Supporting state

Allowed in secondary copy:

- Entry open
- Almost ready
- Extended
- Triggered
- Invalidated
- Target reached
- Stale

### 11.3 Research terms

Keep inside the evidence drawer:

- alpha;
- residual momentum;
- MACD/StochRSI;
- edge percentile;
- cycle tier;
- factor score;
- reflexivity;
- base rate.

### 11.4 Count labels

Use explicit labels:

- `12 visible`;
- `81 qualifying signals`;
- `132 scanned setups`;
- `55 active plans`;
- `3 invalidated today`.

Never use an ambiguous `shown` count for different populations.

## 12. Freshness and data contract

### 12.1 Global metadata

Add one page-level object:

```json
{
  "asof": "2026-07-28",
  "generated_utc": "2026-07-29T...",
  "cadence": "nightly-EOD",
  "freshness": "fresh",
  "authority_tier": "display",
  "gate_go": false
}
```

### 12.2 Normalized Prophet summary

The template should consume a normalized view model rather than infer counts from multiple arrays:

```json
{
  "qualifying_count": 81,
  "initial_visible_count": 10,
  "scanned_setup_count": 132,
  "active_plan_count": 52,
  "invalidated_count": 3,
  "changed_today_count": 30,
  "act_now": [],
  "watch_next": [],
  "manage": []
}
```

### 12.3 Freshness policy

Recommended:

- fresh: current or latest expected trading-day close;
- delayed: one expected build late;
- stale: more than one expected build late;
- unavailable: source missing or invalid.

When stale:

- show the stale state prominently;
- remove “today” language;
- disable new-entry alerts;
- retain historical information with an explicit timestamp.

## 13. Visual system

### 13.1 Hierarchy

- Page title: 24–28 px.
- Section title: 16–18 px.
- Stock ticker/action: 15–16 px and semibold.
- Body: 14–16 px.
- Supporting metadata: 12–13 px minimum.
- Avoid 8–10 px operational labels in the primary view.

### 13.2 Color

Reserve color for decisions:

- green: entry open/buy;
- blue: watch/wait;
- amber: extended/trim/caution;
- red: exit/invalidated;
- grey: neutral/hold.

Do not color EDGE, sector leadership, action, trend, and caution independently on the same row.

### 13.3 Icons

Use one icon family. Remove mixed emoji, mathematical symbols, and unrelated glyphs from the primary layer.

Every icon-only control must have an accessible name.

### 13.4 Density

Desktop:

- one or two decision columns;
- no more than ten stock rows initially;
- 12–16 px internal spacing;
- 20–28 px between major sections.

Mobile:

- one decision column;
- full-width rows;
- no persistent two-column stock grid;
- no horizontally scrolling primary table.

## 14. Interaction model

Use one shared right-side drawer on desktop and bottom sheet/full-screen sheet on mobile.

The drawer supports:

- stock evidence;
- caution details;
- change history;
- track record;
- methodology.

Benefits:

- fewer modal implementations;
- consistent escape/focus behavior;
- fewer buttons in each card;
- less DOM;
- better mobile behavior.

Opening a stock row should open the drawer. A clear secondary link opens the full stock page.

## 15. Accessibility requirements

- Replace `.help` spans with real buttons.
- Give every help button an accessible name, such as `Explain edge score`.
- Support click/tap, keyboard, Escape, and focus return.
- Put sortable behavior on buttons inside `<th>`.
- Maintain `aria-sort`.
- Ensure visible focus styling.
- Use text in addition to color.
- Target 44 × 44 for important touch controls.
- Ensure controls below 44 have at least WCAG-compliant minimum size/spacing.
- Announce dynamic filter and result-count changes with a polite live region.
- Trap focus only in true modal dialogs.
- Respect reduced-motion preferences.
- Test English and Chinese layouts independently.

## 16. Performance budgets

These are product budgets, not external standards:

| Budget | Target |
|---|---:|
| Initial generated HTML | under 300 KB |
| Initial DOM elements | under 3,000 |
| Initial Prophet rows/cards | 10 maximum |
| Initial page height desktop | under 2,500 px |
| Initial page height mobile | under 5,000 px |
| Tooltip/help instances in initial DOM | under 25 |
| Full research tables | lazy/on-demand |

Implementation techniques:

- do not render 76 hidden Prophet cards;
- render the next page only after user request;
- load expert tables when their tab opens;
- use one drawer shell;
- move repeated bilingual tooltip prose to keyed data or shared templates;
- avoid duplicating grid and table markup for the same records.

## 17. Responsive requirements

### Desktop

- Prophet appears in the first viewport.
- Act Now and Watch Next can sit side by side.
- Portfolio context uses a compact four-group row.
- Research destinations appear as links/cards, not full tables.

### Tablet

- Prophet groups stack.
- Portfolio context becomes two columns.
- Drawer remains side-mounted if space permits.

### Mobile

- Header, change digest, and first actionable stock fit within the first screen.
- Prophet uses one full-width row per stock.
- Portfolio context uses tabs or an accordion.
- Evidence opens in a full-height sheet.
- No horizontal scrolling for primary decisions.
- Ask Mastermind must not cover actionable content or navigation.

## 18. Instrumentation and evaluation

Track:

- time to first stock-detail open;
- percentage of sessions opening a top-five Prophet signal;
- usage of Act Now versus Watch Next;
- changes-drawer open rate;
- alert acknowledgement rate;
- All Signals open rate;
- research-table usage after removal from the landing page;
- mobile scroll depth to first Prophet interaction;
- zero-result/empty-lane frequency;
- stale-data exposure count.

Run a five-user task test:

1. Find the best stock to enter now.
2. Explain why it is actionable.
3. Find the nearest invalidation.
4. Identify what changed today.
5. Find a stock that is strong but should not be chased.

Pass condition: each task completes without help in under 30 seconds; task 1 should complete in under 10 seconds.

## 19. Implementation sequence

### Phase 0 — Data and count contract

- Reconcile the 81/84/132 counts.
- Define active versus invalidated Prophet plans.
- Add global freshness metadata.
- Normalize primary action verbs.
- Add tests for summary counts and stale-state behavior.

### Phase 1 — New first viewport

- Build compact command header.
- Promote What Changed.
- Add Act Now and Watch Next Prophet summaries.
- Move the existing action board below Prophet.
- Preserve current modules below as a temporary fallback.

### Phase 2 — Progressive disclosure

- Introduce the shared evidence drawer.
- Simplify Prophet cards/rows.
- Remove per-card caution popovers.
- Move Track Record and changes into the shared drawer/tab model.
- Stop rendering hidden Prophet cards.

### Phase 3 — Remove duplication

- Merge More Fresh Triggers into All Prophet Signals.
- Move Market Leaders to Discovery/All Signals.
- Replace full breadth/sector/flow tables with summaries and links.
- Convert the action board into compact Portfolio Context.

### Phase 4 — Mobile, accessibility, and performance

- Replace two-column mobile cards with one-column rows.
- Implement accessible help and sorting.
- Enforce target-size and focus requirements.
- Lazy-load research views.
- Validate performance budgets.

### Phase 5 — Visual polish and experimentation

- Normalize iconography.
- Tune typography and spacing.
- Test Act Now/Watch Next labels.
- Test whether Hold/manage deserves a separate visible group.
- Review bilingual line wrapping and label length.

## 20. Acceptance criteria

### Product

- [ ] Prophet appears in the first desktop and mobile viewport.
- [ ] A user can identify the top three actions without opening a tooltip.
- [ ] Every stock has exactly one primary action verb.
- [ ] What Changed is visible near the top.
- [ ] Freshness and as-of are always visible.
- [ ] Theme/sector calls are visually distinct from individual stock calls.
- [ ] Full research tables no longer dominate the landing page.

### Data

- [ ] Candidate, active, visible, setup, invalidated, and historical counts reconcile.
- [ ] Invalidated plans are not counted as active.
- [ ] Stale data suppresses fresh-entry language and alerts.
- [ ] `gate_go`/authority tier is accurately disclosed.

### Mobile

- [ ] Prophet uses one column at 390 px.
- [ ] No primary decision table scrolls horizontally.
- [ ] Ask Mastermind does not cover content.
- [ ] Important controls have 44 × 44 targets.
- [ ] First actionable stock appears in the first screen or immediately below the compact status header.

### Accessibility

- [ ] Help controls are focusable buttons.
- [ ] Tooltips/popovers work by keyboard and touch.
- [ ] Sortable headers are keyboard-operable and expose `aria-sort`.
- [ ] Dynamic counts are announced.
- [ ] Visible focus is present.
- [ ] Color is never the only state indicator.

### Performance

- [ ] Initial HTML is below 300 KB.
- [ ] Initial DOM is below 3,000 elements.
- [ ] No more than ten Prophet rows render initially.
- [ ] Expert tables load only on request.
- [ ] The page meets the desktop and mobile height budgets.

## 21. QA matrix

Test:

- English dark mode;
- English light mode;
- Chinese dark mode;
- Chinese light mode;
- 390 × 844 mobile;
- 768 px tablet;
- 1280 × 720 desktop;
- 1440 px desktop;
- fresh data;
- delayed data;
- stale data;
- no actionable buys;
- one actionable buy;
- more than ten actionable buys;
- invalidation today;
- count mismatch rejected by build/test;
- keyboard-only navigation;
- VoiceOver/Safari smoke test;
- reduced-motion mode.

## 22. Files likely involved

- `templates/dashboard.html.j2`
- `templates/_prophet_card.html.j2`
- `templates/theme.css`
- `templates/theme.js`
- `scripts/build_site.py`
- Prophet/action-board view-model builders used by `build_site.py`
- `site/prophet/index.json` producer and its tests
- table sorting/filtering utilities
- relevant render and page-contract tests

Generated `site/us_stocks.html` should be treated as an output, not the primary implementation surface.

## 23. Risks and open decisions

### Must resolve before implementation

1. What is the authoritative difference between the displayed 81, pager 84, and 132 setups?
2. Which Prophet phases count as active?
3. Should Hold/manage rows appear for every user or only followed/owned positions?
4. Does `gate_go: false` require an “Experimental” label in the command header or only the Prophet section?
5. Should the full Prophet universe remain on `us_stocks.html` behind a tab or move to a dedicated page?

### Recommended decisions

- Treat Prophet as the only individual-stock decision queue.
- Keep sectors/themes as portfolio context, not a parallel stock picker.
- Keep the full Prophet universe behind an in-page All Signals tab initially.
- Show Hold/manage only for followed or active plans when user state exists.
- Display the authority tier beside Prophet until the gate changes.
- Use the shared drawer rather than adding more independent modals.

## 24. Non-goals

This handoff does not authorize:

- changing signal math or ranking logic;
- changing backtest claims;
- changing Prophet's gate;
- changing portfolio sizing rules;
- removing required disclosures;
- redesigning the full Terminal application;
- merging unrelated global-navigation work into this project.

Required disclosures should become shorter and contextual, not disappear.

## 25. Final product statement

The current page proves how much the system knows. The redesigned page should prove that the system knows what matters now.

The landing experience should show a small number of explicit decisions, reveal changes immediately, and let the evidence remain one click away.
