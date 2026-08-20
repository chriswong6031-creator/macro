# Mastermind-X Institutional Product Experience V2
## Turn 3 — Adversarial Review, Reference Repair, Architecture Freeze Candidate, and First Three Operator Handoffs

**Program ID:** `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2`  
**Design thesis:** **Quiet Conviction**  
**Owner:** Sol, AI CEO  
**Final authority:** Chairman Chris Wong  
**Repository:** `mastermindx-market-intelligence/macro`  
**Current-main reconciliation baseline:** `2a228fc494b1accba95c95ca25d37c15b9981ecc`  
**Date:** 2026-08-20  
**State:** `SOL_FREEZE_CANDIDATE`  
**Reference state:** `R2_REPAIRED · NOT YET RIG-APPROVED`  
**Implementation authority:** The three handoffs in §14 may be dispatched only after the independent critic pass in §13 returns no blocker or Sol amends the reference.

**Precedence**

1. Chairman’s direct instructions in the current program.
2. This Turn-3 freeze candidate.
3. `MASTERMIND_INSTITUTIONAL_PRODUCT_EXPERIENCE_V2_TURN_2_ARCHITECTURE.md`.
4. `MASTERMIND_INSTITUTIONAL_PRODUCT_EXPERIENCE_V2_TURN_1_CHARTER.md`.
5. Existing design-system constitution, migration factory, and reference-integrity gate.
6. Older page-specific design plans where they do not conflict with the above.

---

# 0. Executive verdict

The Turn-2 references passed the first and most important test:

> They looked like a modern institutional product rather than a collection of machine outputs.

The Chairman’s positive reaction is meaningful product evidence. The references recovered the intended emotional and functional direction:

- quiet rather than noisy;
- decisive rather than defensive;
- data-dense without looking compressed;
- modern fintech SaaS rather than bespoke analyst HTML;
- attractive enough to become a daily habit;
- responsive without visually becoming a different product.

However, a serious adversarial review found several places where the provisional references improved presentation by drifting from current product truth. Those issues are repaired in the R2 references delivered with this packet.

The main repairs are:

1. **Sector Central now preserves the exact five canonical action lanes.**
2. **The action list preserves the canonical score/priority read instead of replacing it with performance alone.**
3. **The current workspace navigation order is preserved.**
4. **The Map remains a distinct task from What’s Moving.**
5. **Big Pharma is no longer silently promoted into Buy now merely to fill a mockup row.**
6. **Confluence regains its universe tabs and coverage truth.**
7. **The Intelligence Hub explainer now describes the actual ranking method rather than the simplified “room left outranks votes” story.**
8. **Policy is explicitly identified as context that never votes.**
9. **Tooltip, explain-popover, and mobile-dialog semantics are separated.**
10. **Box count is reduced further through compact strips and resource rows.**

The product direction therefore receives:

> **SOL PRODUCT VERDICT: PASS WITH REPAIRS — REPAIRS APPLIED IN R2**

The architecture is now coherent enough to freeze as a candidate. It is **not yet a canonical production reference** until independent Product Regression, Visual/Taste, Mobile/Accessibility, and Authority critics complete the rationale-quarantined review.

---

# 1. Verified current state

## 1.1 Sector Central already has the correct workspace skeleton

The current repository is not a blank slate. `research/SI_WORKSPACE_V2_MASTERPLAN_BY_FABLE.md` and `templates/sector_central.html.j2` already establish:

- one canonical Sector Intelligence route;
- a persistent workspace rail;
- hash-routed same-page views;
- lazy mounting of heavy organs;
- deliberate light mode;
- a mobile segmented switcher;
- legacy-anchor routing;
- display-tier synthesis rather than new signal authority.

That architecture is retained.

The institutional program is not rebuilding the shell. It is replacing the visual, information, content, and responsive composition **inside the existing canonical shell**.

## 1.2 Current rail order is now six views

The current production source orders the workspace:

1. Overview
2. The Map
3. What’s Moving
4. Money & Breadth
5. Explore
6. Confluence

Confluence was appended later so the first five positions and returning-user muscle memory did not move. The R2 reference restores this order.

The Turn-2 mockup’s order—Overview, Moving, Confluence, Map, Breadth, Explore—was visually reasonable but unnecessary product drift.

## 1.3 Current Overview consumes the shared five-lane action board

The canonical action board is shared between US Stocks and Sector Central and currently contains exactly:

1. `Buy now`
2. `Almost ready`
3. `In favour — don’t chase`
4. `Take profits`
5. `Stand aside`

The Turn-2 mockup used:

- Act now;
- Get ready;
- Wait for pullback;
- Protect gains;
- Stand aside.

Those phrases were cleaner in isolation, but they silently changed product semantics. In particular:

- `In favour — don’t chase` is not equivalent to a generic pullback queue;
- `Take profits` is more specific than protect gains;
- `Almost ready` is a timed state, not merely preparation advice.

R2 preserves the canonical language.

## 1.4 Current board exposes more than performance

The live board carries:

- canonical lane;
- full board count;
- composite score/priority;
- relative performance;
- reason;
- kind;
- supporting chips;
- optional trace/decision detail.

The Turn-2 mockup preserved relative performance but removed the score. That risks making the rows look like performance leaders rather than gated action reads.

R2 keeps:

- full name;
- kind/sector;
- canonical score;
- relative performance;
- one human reason;
- destination.

Supporting chips and mechanics are available on detail, not repeated at rest.

## 1.5 Current Intelligence Hub ranking is not “votes versus room left”

`engine/intel_hub.py` ranks on a governed opportunity measure whose core incorporates:

- signal strength;
- estimated edge remaining/runway;
- whether leading evidence appeared before lagging evidence;
- a falsifier/tripwire penalty;
- a de-escalating signal governor.

Dossiers then sort by opportunity score, with composite conviction as the tie-breaker.

Policy is a display facet. It does not vote because its direction is model-originated and may not move a scored rank.

The provisional phrase “Room left outranks votes” was memorable but imprecise. R2 replaces it with:

> **Signal, runway, then timing.**

---

# 2. Adversarial-review method

This was not a preference polish. The references were attacked through four independent lenses.

## 2.1 Product Regression lens

Question:

> What useful capability, truth, action, state, or destination was lost or altered because the new reference looked cleaner?

Tests included:

- current lane vocabulary;
- counts and ordering;
- score and performance;
- route and hash behavior;
- universe selectors;
- coverage/null/stale disclosures;
- self-grader and receipt destinations;
- all current workspace organs.

## 2.2 Visual/Taste lens

Question:

> Does the reference look expensive, intentional, and calm—or merely cleaner than the current page?

Tests included:

- hierarchy;
- container count;
- alignment;
- whitespace;
- card inflation;
- semantic color discipline;
- truncation;
- typography;
- relation between primary and secondary objects;
- whether desktop and mobile both look designed.

## 2.3 Mobile/Accessibility lens

Question:

> Can a phone user complete the same job without hover, hidden capability, tiny controls, or a squeezed desktop layout?

Tests included:

- 320px reflow;
- touch targets;
- tab navigation;
- focus and Escape;
- explain-sheet behavior;
- full names;
- one-handed scanning;
- table/list choices;
- active-tab visibility;
- modal inertness and focus return.

## 2.4 Authority/Truth lens

Question:

> Did display simplification accidentally mint a new score, upgrade a state, merge distinct authorities, hide a null, or allow model copy to change rank meaning?

Tests included:

- producer ownership;
- deterministic versus model-generated fields;
- ranking formula;
- point-in-time clocks;
- policy’s nonvoting boundary;
- action-board population;
- Confluence coverage;
- stale and partial behavior.

The first review was performed without using the design rationale as a defense. Rationale was applied only after the defects were named.

---

# 3. LENS V2 adversarial verdict

## 3.1 What passed

The provisional LENS reference successfully established:

- one short page promise;
- a quiet question-mark trigger;
- a persistent, structured explanation;
- one answer rather than a paragraph wall;
- a separated receipt;
- an obvious mobile sheet;
- deliberate dark and light modes;
- EN/ZH composition;
- a premium visual tone.

Its visual direction is accepted.

## 3.2 What failed

| Finding | Severity | Why it matters | Repair |
|---|---|---|---|
| “Room left outranks votes” is too reductive | Blocker | Misstates the ranking architecture | Replaced with “Signal, runway, then timing” |
| Agreement “never changes rank” is too absolute | Major | Composite conviction tie-breaks; evidence timing changes the leading gap | Removed |
| Five desks were listed without policy’s authority boundary | Major | Could imply policy votes | Receipt now states policy is context and never votes |
| Desktop explain moved focus immediately into the popover | Minor | A toggletip may preserve point of regard on the trigger | Desktop keeps trigger focus; Tab enters interactive content |
| Mobile sheet did not make the background explicitly inert | Major | Visual modal alone is not a semantic modal | Background becomes inert; focus enters and is trapped |
| The dialog initially focused the close button | Minor | Structured explanatory content should be read from the start | Mobile focuses the titled answer block |
| Method link looked like part of the tooltip | Minor | Methodology is a separate depth tier | Retained only in `explain`; never in `tooltip` |
| One visual mode still risked becoming universal | Major | Label, definition, explanation, and method are different jobs | Four governed modes frozen |

## 3.3 Repaired product copy

### Page promise

**Early opportunities, ranked by signal, runway and timing.**

### Explain trigger

**How ranking works**

### Explain content

**Kicker:** How ranking works  
**Title:** Signal, runway, then timing  
**Answer:** Rank rises when evidence is strong, runway remains, and leading signals appear before the crowd.

| Label | Value |
|---|---|
| Signal | Independent evidence must be present. |
| Runway | Estimates how much of the move may remain. |
| Timing | Early evidence ahead of news and momentum lifts rank. |

**Receipt:** Conviction breaks ties. Proven feeder weakness can only reduce rank. Policy is context and never votes. Context only—not a trade trigger.

## 3.4 Final interaction contract

### `tooltip`

- brief, supplemental, and noninteractive;
- hover/focus;
- `role="tooltip"`;
- focus remains on trigger;
- Escape dismisses;
- no link, button, rich receipt, or required instruction;
- 18 English words maximum.

### `define`

- one-sentence term definition;
- hover/focus permitted;
- click may pin it when the user needs more time;
- no interactive content;
- 24 English words maximum.

### `explain`

- question-mark or explicit Explain button;
- click, Enter, or Space only;
- persistent disclosure/nonmodal dialog on desktop;
- may include one detail/method link;
- trigger has `aria-expanded` and `aria-controls`;
- Escape and outside click dismiss;
- focus returns to trigger;
- 45 words above receipt, 75 total maximum.

### `mobile_sheet`

- the phone projection of `explain`;
- modal dialog;
- background inert;
- focus starts on static titled content;
- focus trapped;
- visible close control;
- Escape/back/scrim/swipe dismissal;
- safe-area padding;
- focus returns to trigger.

### `method`

- drawer, tab, or route;
- formulas, weights, sample sizes, examples, history, and complete sources;
- not a tooltip.

---

# 4. Sector Central adversarial verdict

## 4.1 What passed

The Turn-2 Sector Central mockup successfully demonstrated:

- the desired institutional visual grammar;
- a useful page answer;
- a clean action-state distribution;
- resource rows instead of narrow micro-cards;
- full, readable names;
- proportional layout;
- compact leadership handoff;
- a map large enough to matter;
- compact Crosscurrents;
- a single buy-ready focus object in Confluence;
- responsive stacking rather than shrinking;
- modern SaaS cleanliness.

The visual thesis is accepted.

## 4.2 What failed and was repaired

| Finding | Severity | Repair |
|---|---|---|
| Canonical lane names were changed | Blocker | Exact five lane labels restored |
| Big Pharma was moved into Buy now to fill a row | Blocker | Removed from Buy now; only visible verified rows shown |
| Score/priority disappeared | Blocker | Canonical score restored as the primary numeric read |
| Navigation order changed | Major | Current six-view order restored |
| The rotation map was placed in What’s Moving despite an existing Map task | Major | Map returned to The Map; Moving focuses on changes |
| “Since yesterday” used three large cards | Minor | Converted to one compact change strip |
| Early turns used equal cards and reintroduced boxiness | Minor | Converted to one compact contained list |
| Confluence universe tabs were lost | Major | S&P 500, Nasdaq-100, Russell-2000, and Thematic Baskets restored |
| Confluence coverage truth was lost | Major | Timed/thin coverage receipt restored |
| Distribution could be mistaken for a score | Major | It is explicitly a count/filter, never a score |
| Provisional disclaimer remained visible | Minor | Removed from the product reference |
| Mobile tab behavior was underspecified | Major | Manual-activation tab contract frozen |
| Empty/partial states were described but not bound to component placement | Major | State projection contracts added in §10 |

## 4.3 Final rail order

Frozen for the first migration:

1. Overview
2. The Map
3. What’s Moving
4. Money & Breadth
5. Explore
6. Confluence

This preserves current shareable hashes, returning-user position, and current architecture.

A later learning review may reorder views only with observed workflow evidence.

## 4.4 Final Overview order

1. Page answer.
2. Market/regime/freshness context.
3. Five-state distribution.
4. Selected-state resource list.
5. Almost-ready rail.
6. Leadership handoff.
7. Early-turn contained list.
8. One compact change strip.
9. Record & Method destination.

No other first-level modules.

## 4.5 Exact action vocabulary

| Producer key | Customer label | R2 presentation |
|---|---|---|
| `buy_now` | Buy now | selected default |
| `buy_soon` | Almost ready | up-next queue |
| `on_the_run` | In favour — don’t chase | pullback/late-trend queue |
| `take_profits` | Take profits | protect/trim queue |
| `hold + avoid` | Stand aside | no-new-buying queue |

The reference does not merge or rename these states.

## 4.6 Resource-row hierarchy

At rest:

1. Full name.
2. Kind or sector.
3. Canonical score.
4. One relevant performance/context metric.
5. One human reason.
6. Destination.

Not at rest:

- duplicate lane chip;
- every supporting factor;
- raw model description;
- methodology;
- repeated caveat;
- internal score anatomy.

## 4.7 Final view jobs

| View | Job |
|---|---|
| Overview | What should I act on now? |
| The Map | Where does the whole market sit? |
| What’s Moving | What leadership changed? |
| Money & Breadth | Is participation supporting the move? |
| Explore | Find and compare a sector or theme. |
| Confluence | Which subsectors have timing support? |

Each view opens with one answer and one primary object.

---

# 5. Architecture freeze candidate

The following decisions are frozen unless an independent critic produces a blocker.

## 5.1 Product topology

- `sector_central.html` remains the canonical US sector/theme/rotation workspace.
- No second Sector Central route.
- Existing redirect/stub and deep-link law remains.
- Existing engine and payload authorities remain.
- Confluence stays in the workspace.
- The action board remains the only gated/graded action layer.
- All other sector views remain context unless their existing owner already grants more authority.

## 5.2 Visual thesis

**Quiet Conviction**

- one dominant answer;
- one dominant object;
- full names;
- restrained semantic color;
- low surface nesting;
- whitespace before decoration;
- data density through alignment;
- charts and lists over card mosaics;
- sci-fi expressed through instrumentation, not neon ornament;
- no decorative machine prose.

## 5.3 Responsive thesis

- mobile-first base;
- same capability and truth, different composition;
- one selected state/view at a time;
- no hover-only fact;
- no page-level horizontal scroll at 320px;
- no primary-name ellipsis;
- touch-safe controls;
- persistent active-view visibility;
- sheets for selected details and explainers;
- true comparison tables may scroll locally or stack.

## 5.4 Content thesis

- answer first;
- support second;
- action third;
- receipt one step away;
- no default-visible model paragraph;
- deterministic display lexicon;
- one caveat per concept per panel;
- exact states, no helpful-sounding synonym drift.

## 5.5 Authority thesis

- presentation never changes rank, population, state, gate, size, or score;
- model text does not originate a rank or default stance;
- policy remains nonvoting context in Intelligence Hub;
- distribution counts are not scores;
- stale legs retain independent clocks;
- missing never becomes zero;
- point-in-time truth is not replaced by latest-known truth.

---

# 6. Canonical component contracts

The names below are semantic contracts. Exact class names may be amended during implementation only if behavior and ownership remain identical.

## 6.1 `mx-page-answer`

**Purpose:** State the page’s answer before the machinery.

Fields:

- eyebrow;
- H1;
- answer sentence;
- optional emphasis span;
- context chips;
- freshness.

Budgets:

- H1: five words preferred, seven maximum;
- answer: fourteen words preferred, twenty maximum;
- context chips: three visible;
- one freshness source.

Mobile:

- answer and first action remain in first viewport;
- context chips wrap;
- no side-by-side meta column.

## 6.2 `mx-workspace-tabs`

**Purpose:** Move among same-route tasks.

Contract:

- `tablist`, `tab`, and `tabpanel` semantics;
- current rail order;
- manual activation because production panels lazy-mount heavy organs;
- arrows move focus;
- Enter/Space activates;
- Home/End supported;
- active tab owns `tabindex=0`;
- hash remains shareable;
- every legacy hash maps to a canonical tab and target;
- desktop orientation vertical;
- phone orientation horizontal;
- active phone tab auto-scrolls into view.

## 6.3 `mx-state-distribution`

**Purpose:** Show the complete action-state population and choose one state.

Fields:

- state key;
- exact label;
- count;
- one short meaning;
- semantic accent.

Rules:

- count reconciles to producer;
- no score;
- selected state controls the resource list;
- zero states remain visible but disabled or honestly selectable;
- no arbitrary equal-height lane bodies.

Mobile:

- horizontal local scroll or compact wrap;
- active state remains visible;
- page itself does not scroll horizontally.

## 6.4 `mx-resource-list`

**Purpose:** Present actionable named objects compactly.

Semantic structure:

- list;
- list item;
- one actionable link/button per row;
- full name;
- secondary identity;
- primary metric;
- optional secondary metric;
- reason;
- destination.

Rules:

- full name never ellipsizes on primary product routes;
- secondary information yields first;
- 48px one-line minimum; 64–76px for two-line rows;
- no nested card;
- dividers rather than separate boxes;
- maximum six at Tier 1 before See all.

## 6.5 `mx-transition-row`

**Purpose:** Show from → to handoffs.

Fields:

- source group;
- destination group;
- age;
- current read;
- destination.

Rules:

- no paragraph card;
- source and destination remain visually distinct;
- age is secondary;
- no action authority implied unless the action board independently confirms.

## 6.6 `mx-change-strip`

**Purpose:** State up to three changes since prior session.

Rules:

- one shared strip;
- no three-card grid;
- maximum three changes;
- date shown only when different;
- absent diff renders nothing;
- no fabricated “steady” message unless useful.

## 6.7 `mx-early-turn-list`

**Purpose:** Preserve Bottoming Watch capability without overpowering Overview.

Fields:

- full group name;
- early-turn state;
- cycle position;
- one gate/caveat;
- destination.

Rules:

- one contained list;
- section-level caveat once;
- no repeated “watch only” chip;
- no claim of buyability;
- maximum three at Overview.

## 6.8 `mx-coverage-receipt`

**Purpose:** State whether the panel covers enough live data to support its read.

Fields:

- total universe;
- timed/current;
- thin;
- stale;
- unavailable;
- as-of.

Rules:

- quiet at rest;
- visible when it changes interpretation;
- never a raw pipeline log;
- links to source/method where available.

## 6.9 `mx-explain`

Modes frozen in §3:

- label;
- define;
- explain;
- mobile sheet;
- method destination.

## 6.10 `mx-state-panel`

Required states:

- loading;
- empty + why;
- stale;
- partial;
- unavailable/error.

It preserves useful unaffected content and names exactly what is held, delayed, or missing.

---

# 7. Typography, density, and geometry freeze

## 7.1 Type

- Page H1: responsive 31–46px.
- Section heading: 16–18px.
- Primary name: 14–15px, 650–750 weight.
- Decision/explanation prose: 14px desktop, 15px mobile target.
- Secondary metadata: 12.5–13px.
- Receipts: 11.5–12px.
- No paragraph below 14px.
- No interactive label below 13px.
- Mono/tabular treatment only where numeric alignment benefits.

## 7.2 Space

- Canvas: approximately 1280–1360px by archetype.
- Desktop page gutter: 24–32px.
- Phone gutter: 14–18px.
- First-level vertical rhythm: 24–32px.
- Resource row padding: 12–16px.
- Surface nesting: two levels maximum.

## 7.3 Radius

- Controls: 8–10px.
- Panels: 12–16px.
- Pills: only true compact states/filters.
- No arbitrary continuous radius spectrum.

## 7.4 Color

- Green: positive/actionable state.
- Blue: readiness/information.
- Violet: in-favour/continuation without buy implication.
- Amber: profit protection/late caution.
- Slate: neutral/stand aside.
- Red: negative/failing/invalidated.
- Color does not replace text.
- Policy/context colors never masquerade as score authority.

## 7.5 Motion

- No ambient pulse unless it represents live status.
- Workspace switch is instant.
- First-mount chart reveal only.
- Popover/sheet motion under 220ms.
- Reduced-motion path has no spatial animation.
- No looping sheen, breathing chip, or decorative beacon on operational surfaces.

---

# 8. Mobile freeze

## 8.1 Width contract

Automated checks:

- 320;
- 360;
- 390;
- 430;
- 768;
- 820;
- 1024;
- 1280;
- 1440.

At every width:

- no page-level horizontal overflow;
- no clipped active control;
- no primary-name truncation;
- no off-screen popover;
- no hidden-only capability;
- no overlap at 200% text zoom.

## 8.2 Overview first-screen contract at 390×844

Visible before meaningful scroll:

1. page answer;
2. current context;
3. state distribution;
4. at least two rows from the selected state.

## 8.3 Tabs

- sticky horizontal switcher;
- active tab auto-scrolls;
- no hamburger;
- no equal-width squeeze;
- tab label remains readable;
- swipe is optional, never the only control.

## 8.4 Resource rows

- name and score on first line;
- reason and context on second line;
- destination target at least 40px;
- no horizontal table.

## 8.5 Charts

- chart answer above;
- chart 320–430px tall depending on task;
- selected object opens a sheet;
- accessible list fallback;
- series/annotation density reduced, not font size.

## 8.6 Explain sheet

- modal;
- background inert;
- focus to static heading/answer;
- focus trapped;
- safe areas;
- scrollable content;
- visible close;
- Escape/back/scrim/swipe;
- return focus.

---

# 9. Capability disposition ledger — Sector Central

Nothing disappears without a ruling.

| Current capability | Current home | R2 disposition | V2 home | Authority |
|---|---|---|---|---|
| Rotation verdict | Overview hero | `IMPROVE` | `mx-page-answer` | Existing theme context |
| Regime/context chips | Overview | `RETAIN · COMPRESS` | Page answer context | Existing context |
| Five action lanes | Overview shared board | `IMPROVE` | State distribution + selected resource list | Existing action board |
| Lane counts | Overview | `RETAIN EXACT` | State distribution | Existing action board |
| Composite score/priority | Action rows | `RETAIN` | Resource-row primary metric | Existing producer |
| Relative performance | Action rows | `RETAIN` | Secondary metric | Existing producer |
| Lane reason | Action rows | `REWRITE AS DISPLAY PROJECTION` | One bounded reason | Deterministic mapping/current reviewed field |
| Decision trace | Row hover/detail | `RELOCATE` | Explain/detail | Existing record |
| Tier withholding | Gated hosts | `RETAIN EXACT` | Existing access projection | Existing access gate |
| Leadership handoff | Overview hero/card | `RETAIN · IMPROVE` | Transition row | Existing context |
| What changed | Overview | `RETAIN · IMPROVE` | Change strip | Existing payload-resident diff |
| Self-grader | Overview/below board | `RELOCATE` | Record & Method | Existing grader |
| Bottoming Watch | Overview | `IMPROVE` | Early-turn list | Existing turn read |
| Cycle map | The Map | `RETAIN · IMPROVE` | Primary map/cycle object | Existing cycle engine |
| Sector/theme cards | The Map | `COMPRESS` | Selected detail/list | Existing producer |
| Fast rotation lens | The Map | `RETAIN AS CONTEXT` | Method/selected detail | Existing display order |
| Rotation events | Moving | `IMPROVE` | Transition rows | Existing rotation events |
| Rotating in/out | Moving | `MERGE` | Active handoffs/changes | Existing rotation |
| Fragmented sectors | Moving | `IMPROVE` | Crosscurrents comparison | Existing aggregate facts |
| Desk Watch | Moving | `RETAIN · COMPRESS` | Secondary contained list | Existing context |
| Closed events | Moving | `RELOCATE` | Collapsed history | Existing record |
| ETF flows | Money & Breadth | `RETAIN` | Flow list/table | Existing flow producer |
| Internals/breadth | Money & Breadth | `RETAIN · COMPRESS` | Four primary reads + detail | Existing breadth |
| Heatmap | Money & Breadth | `RETAIN · DEMOTE` | Summary + deep link | Existing heatmap |
| Leadership scorecard | Money & Breadth | `RETAIN` | Compact supporting module | Existing producer |
| Explore table | Explore | `RETAIN · IMPROVE` | Search/filter comparison | Existing payload |
| Performance chart | Explore | `RETAIN` | Selected result detail | Existing series |
| Time Machine | Explore | `RETAIN · COLLAPSE` | Explicit historical tool | Existing artifact |
| Forming Narratives | Explore | `RETAIN WITH PROJECTION` | Analysis-only module | Model output labelled analysis |
| Track record | Explore | `RETAIN` | Record & Method | Existing ledger |
| Confluence universe tabs | Confluence | `RETAIN EXACT` | Confluence toolbar | Existing universe contracts |
| Confluence distribution | Confluence hero | `RETAIN · REFRAME` | Count/filter strip | Existing confluence read |
| Buy-ready group cards | Confluence | `IMPROVE` | One focus object | Existing timing |
| Tailwind groups | Confluence | `IMPROVE` | Resource queue | Existing timing |
| Late/fading groups | Confluence | `IMPROVE` | Compact list/table | Existing timing |
| Per-group member stocks | Confluence | `RETAIN` | Group detail / selected panel | Existing member data |
| Coverage thin/current counts | Confluence | `RETAIN` | Coverage receipt | Existing coverage |
| Long caveat paragraphs | Multiple | `RELOCATE` | LENS/method | Existing receipts |
| Duplicate local card systems | Template CSS | `REMOVE` | Canonical primitives | Display only |
| Legacy hashes | Router | `RETAIN EXACT` | Canonical tab + target map | Navigation contract |

---

# 10. Failure-state freeze

## 10.1 Overview

### Loading

- page identity and context paint;
- distribution skeleton;
- resource-row skeletons;
- no explanatory paragraph.

### Empty Buy now

**No groups cleared the Buy now bar tonight.**  
*Almost ready contains the strongest current setups.*

The state selector remains complete.

### Stale

**Action states are from Aug 19.**  
*Prices are current; lane membership is held at the last good read.*

### Partial

**Actions are current; leadership handoff is delayed.**

The action list remains usable.

### Error

**The action board did not load.**  
*Map, breadth, and group detail remain available.*

## 10.2 The Map

- missing map does not erase selected group/list;
- stale cycle and current rotation keep separate clocks;
- source failure names the missing leg;
- no blended “current” stamp.

## 10.3 Moving

- no active events is a valid quiet state;
- closed history remains;
- stale event feed does not fabricate a handoff;
- Crosscurrents can remain if its source is healthy.

## 10.4 Money & Breadth

- each leg keeps its own clock;
- disagreement stays visible;
- no average score is minted;
- one failed leg is partial, not total error.

## 10.5 Explore

- no result is distinct from no data;
- search/filter empty preserves filters;
- detail failure does not erase result list.

## 10.6 Confluence

### Coverage thin

**65 of 113 subsectors can be timed.**  
*The remaining 48 stay visible but do not receive a timing state.*

### No buy-ready

**No group is buy-ready.**  
*Tailwind contains the strongest groups still approaching entry.*

### Stale

**Timing is from the last settled session.**

---

# 11. Human Display Projection freeze

Working contract: `mastermind.display_projection.v1`.

This remains a read-only projection over canonical facts.

## 11.1 Action-row projection

```json
{
  "entity_id": "basket:gold_miners",
  "display_name": "Gold Miners",
  "kind_key": "theme",
  "lane_key": "buy_now",
  "score": 76,
  "relative_performance": 27.2,
  "relative_period": "20d",
  "reason_key": "fresh_entry_confirmed",
  "freshness": {
    "source_asof": "2026-08-19",
    "quality": "current"
  },
  "href": "basket/gold_miners.html",
  "receipt_refs": []
}
```

The display projection does not recalculate the score or lane.

## 11.2 Explainer projection

```json
{
  "mode": "explain",
  "kind": "read",
  "title_key": "intel_hub_ranking_title",
  "answer_key": "intel_hub_ranking_answer",
  "rows": [
    {"label_key": "signal", "value_key": "intel_hub_signal_rule"},
    {"label_key": "runway", "value_key": "intel_hub_runway_rule"},
    {"label_key": "timing", "value_key": "intel_hub_timing_rule"}
  ],
  "receipt_key": "intel_hub_ranking_receipt",
  "method_href": "/method/intelligence-hub-ranking"
}
```

## 11.3 Model-output boundary

A model-generated field may appear only as:

```json
{
  "analysis_only": true,
  "provider": "...",
  "model": "...",
  "generated_at": "...",
  "source_refs": [],
  "text": "..."
}
```

It may not become:

- default page answer;
- lane;
- rank;
- score;
- stance;
- gate;
- size;
- primary reason without deterministic review/mapping.

---

# 12. Reference acceptance matrix

The R2 references must survive:

## 12.1 Product

- all capabilities in §9 accounted for;
- exact lane vocabulary;
- exact counts;
- no fabricated row;
- score retained;
- no new authority;
- complete destinations.

## 12.2 Visual

- no first-level paragraph wall;
- no primary-name ellipsis;
- no arbitrary equal columns;
- no giant empty half-layout;
- no repeated warning per row;
- no more than two nested surfaces;
- page looks intentional in light and dark.

## 12.3 Mobile

- 320px no page overflow;
- 390px first-screen contract;
- touch-safe;
- tabs keyboard/touch safe;
- no hover-only fact;
- explain sheet works;
- EN/ZH names remain complete.

## 12.4 State

At least one captured proof of:

- loading;
- empty;
- stale;
- partial;
- error;
- zero/one/few/many cardinality.

## 12.5 Production

- real nightly payload;
- real builder;
- no manual DOM patch;
- deployed route;
- running build SHA;
- desktop and mobile browser proof;
- light/dark and EN/ZH;
- exact count reconciliation;
- rollback proof.

---

# 13. Independent critic packet

The references are not canonical until these reviews are performed by independent sessions that did not author the references.

## 13.1 Product Regression Critic — exact prompt

```text
You are the independent Product Regression Critic for Mastermind-X.

Do not redesign the page. Do not grade visual beauty first. Your only mission is to determine whether the candidate reference preserves or improves every useful current customer capability without changing data authority.

Authority order:
1. Chairman instructions.
2. XPV2 Turn-3 freeze candidate.
3. Current production source and payload contracts.
4. Candidate R2 reference.
5. Designer rationale only AFTER your first verdict.

Inputs:
- current production screenshots for Sector Central Overview, Moving, Confluence;
- current templates/sector_central.html.j2;
- current templates/_us_act_now_board.html.j2;
- current relevant JS/payload contracts;
- §9 capability-disposition ledger;
- R2 reference HTML.

First pass — rationale quarantined:
A. Enumerate every useful current capability.
B. Mark each RETAINED, IMPROVED, RELOCATED, LOST, ALTERED, or UNPROVEN.
C. Attack lane labels, counts, order, scores, access, hashes, universes, nulls, clocks, coverage, and detail destinations.
D. Identify any visually clean element that makes the product less useful.
E. Return BLOCK / PASS_WITH_CONDITIONS / PASS.

Only after the first verdict, read the design rationale and determine whether any finding is lawfully resolved by an explicit disposition.

A blocker is:
- changed rank/state/gate/population;
- silent capability loss;
- broken user journey;
- missing access/freshness/correction behavior;
- a spec called implementation;
- an unowned duplicate system.

Output:
1. Verdict.
2. Blockers.
3. Majors.
4. Capability ledger delta.
5. Exact required repairs.
6. What must be production-proven.
```

## 13.2 Visual/Taste Critic — exact prompt

```text
You are the independent Visual and Taste Critic for Mastermind-X.

Judge the candidate as if it were shipping from a billion-dollar institutional fintech company. Do not reward it merely for being cleaner than the current page.

Inputs:
- baseline screenshots;
- R2 desktop dark/light EN/ZH;
- R2 390px and 320px;
- no designer rationale until first verdict.

Attack:
- hierarchy;
- visual dominance;
- alignment;
- density;
- whitespace;
- card inflation;
- semantic color;
- typography;
- truncation;
- chart prominence;
- accidental emptiness;
- whether the page feels expensive, calm, and coherent;
- whether mobile looks independently designed.

Return:
- BLOCK / PASS_WITH_CONDITIONS / PASS;
- ten strongest defects in priority order;
- the most embarrassing viewport/state;
- any component that still looks vibe-coded;
- any place where sci-fi styling becomes childish;
- exact repair, without inventing new product logic.
```

## 13.3 Mobile and Accessibility Critic — exact prompt

```text
You are the independent Mobile and Accessibility Critic.

Test:
- 320, 360, 390, 430, 768, 820 widths;
- 200% text zoom;
- keyboard only;
- touch/coarse pointer;
- reduced motion;
- EN and ZH;
- explain popover desktop;
- explain sheet mobile;
- tab routing and legacy hashes;
- loading/empty/stale/partial/error.

Attack:
- page overflow;
- target size;
- clipped focus;
- hidden capability;
- hover-only facts;
- wrong tooltip/dialog roles;
- broken focus return;
- missing inert background;
- inaccessible charts/tables;
- off-screen active tabs;
- primary-name truncation.

Return exact DOM/viewport evidence and blocker status.
```

## 13.4 Data and Authority Critic — exact prompt

```text
You are the independent Data and Authority Critic.

Compare candidate display text and ordering against canonical producer code.

For Intelligence Hub:
- verify opportunity-score ingredients;
- verify tie-break;
- verify signal governor direction;
- verify policy is nonvoting;
- verify the explainer does not overstate probability or trade authority.

For Sector Central:
- verify exact action-board keys and labels;
- verify counts and order;
- verify score/performance fields;
- verify Confluence universes and coverage;
- verify no context view becomes gated authority.

Return every incorrect sentence, field, state, or implied authority.
```

---

# 14. First three bounded operator handoffs

These handoffs are complete enough that builders do not need to rediscover the product. They remain gated on §13.

---

## HANDOFF 1 — `XPV2-LENS-IH1`
### LENS V2 semantic foundation + Intelligence Hub first real consumer

**Recommended builder:** Terra or a bounded Codex session  
**Independent reviewers:** Opus Product Regression + Opus Mobile/Accessibility  
**Fable:** not required unless a site-wide runtime collision is discovered

### Observable mission

On the production Intelligence Hub, a user can activate **How ranking works** and receive the accurate R2 explanation in a governed desktop explain-popover or mobile modal sheet. Legacy `data-tip-*` help across the rest of the site continues to function unchanged.

### Why it matters

This closes the systemic defect the Chairman keeps finding manually:

- question-mark paragraph walls;
- machine text;
- tiny reading type;
- wrong interaction semantics;
- inaccessible rich content;
- repeated explanations.

It also proves the V2 display-projection pattern through one real producer and one real product consumer.

### Authority and precedence

1. Turn-3 §3 and §6.9.
2. R2 LENS reference.
3. `docs/DESIGN_DOCTRINE.md`.
4. Existing `theme.js` LENS runtime.
5. Existing `_lens.html.j2`.
6. Intelligence Hub producer code remains canonical for ranking.

### Verified current state

- Current LENS singleton supports legacy strings and rich hidden blocks.
- Current legacy string tier displays text unchanged.
- Current rich macro is optional.
- Current runtime uses tooltip semantics even when mobile behaves as a dialog.
- Intelligence Hub’s visible ranking explanation is long and imprecise.
- `engine/intel_hub.py` owns the actual ranking and may not be edited in this PR.
- No open PR was found that owns the Intelligence Hub UI.
- Recheck current open PRs for `templates/theme.js`, `templates/_lens.html.j2`, and `templates/intelligence_hub.html.j2` immediately before branching.

### Exact scope

Repository: `mastermindx-market-intelligence/macro`

Owned paths:

- `templates/theme.js`
- paired `site/theme.js` only through the canonical sync path
- `templates/_lens.html.j2`
- `templates/intelligence_hub.html.j2`
- relevant tests
- R2 reference/evidence paths
- migration packet and registry region for Intelligence Hub

Theme CSS is out of scope unless the design authority explicitly amends this handoff after a measured runtime limitation.

### Explicit non-goals

- no engine change;
- no ranking change;
- no opportunity formula change;
- no policy authority change;
- no bulk tooltip-copy migration;
- no removal of legacy string support;
- no site-wide visual reskin;
- no new tooltip controller;
- no raw formula on Tier 1;
- no change to access or payloads.

### Complete user journey

Desktop:

1. User lands on Intelligence Hub.
2. Page promise reads: “Early opportunities, ranked by signal, runway and timing.”
3. User focuses or clicks **How ranking works**.
4. Click/Enter/Space opens persistent explain-popover.
5. Trigger reports expanded state.
6. User reads answer, three rows, receipt.
7. Tab enters Method link when present.
8. Escape/outside click/trigger closes.
9. Focus returns to or remains logically anchored at trigger.

Mobile:

1. User taps the 40–44px explain target.
2. Background becomes inert.
3. Modal sheet opens.
4. Focus moves to static titled content.
5. Focus remains inside.
6. User closes by visible control, Escape/back, scrim, or swipe.
7. Focus returns to trigger.

Legacy:

- a current brief `data-tip-en/zh` still opens as a brief tooltip;
- no rich interaction is added to legacy text automatically.

### Data, time, null, and correction behavior

- Copy is static governed display language.
- Numbers are not repeated in the explainer unless canonical producer fields supply them.
- No current rank is recomputed.
- Missing method route hides the link rather than rendering a dead control.
- EN and ZH are explicit twins.
- A correction to ranking logic must update the governed copy contract in a separate reviewed change.

### Deterministic versus statistical versus model-generated

- interaction: deterministic;
- ranking explanation: reviewed deterministic copy;
- source ranking: existing statistical/deterministic producer, untouched;
- model text: prohibited.

### Failure states

- missing explainer content: trigger does not render;
- JS unavailable: optional static Method link remains; no hidden critical instruction;
- popover cannot place: falls back to centered bounded disclosure;
- mobile unsupported `inert`: tested fallback focus shield;
- missing ZH: build fails on governed consumer.

### Ordered implementation

1. Create migration packet with exact R2 copy.
2. Add explicit LENS mode contract while preserving legacy path.
3. Implement desktop explain disclosure.
4. Implement mobile modal projection.
5. Implement focus/keyboard/inert behavior.
6. Convert Intelligence Hub ranking explainer to rich governed mode.
7. Remove old long ranking paragraph from its default trigger.
8. Add content-budget and authority tests.
9. Capture required matrix.
10. Independent review.
11. Merge, deploy, production proof.
12. Flip only the governed Intelligence Hub/LENS consumer region compliant.

### Acceptance tests

Behavioral:

- label/tooltip remains brief and noninteractive;
- explain opens only on activation, not hover;
- desktop role and focus behavior;
- mobile modal/inert/focus trap;
- Escape, outside click, return focus;
- only one open LENS surface;
- no nested popovers;
- 320px placement;
- reduced motion.

Content:

- exact EN/ZH copy;
- title/answer/rows/receipt budgets;
- “Policy is context and never votes” present;
- no “agreement never changes rank” claim;
- no model text;
- no raw internal slug.

Regression:

- legacy `data-tip-*` fixtures;
- help-icon upgrade fixtures;
- current tooltip users;
- no AI-Brief `data-lens` collision;
- no title-attribute i18n regression;
- template/site sync.

### Real production proof

- deployed Intelligence Hub;
- running SHA;
- desktop dark EN open;
- desktop light ZH open;
- mobile 390 dark EN sheet;
- mobile 390 light ZH sheet;
- keyboard recording/assertion;
- touch/coarse-pointer proof;
- no console error;
- current ranking data unchanged byte-for-byte.

### Stop condition

Stop after this single consumer is proven live. Do not begin the bulk tooltip census or Sector Central migration in the same session.

### Required continuation handoff

Return:

- merge SHA;
- production SHA;
- evidence paths;
- legacy regression result;
- exact remaining LENS mechanisms;
- any semantic/runtime caveat;
- recommended `LENS-2` census scope.

---

## HANDOFF 2 — `XPV2-SC-OV1`
### Sector Central Overview institutional migration

**Recommended builder:** Terra or Codex  
**Independent reviewers:** Opus Product Regression + Opus Visual/Taste  
**Fable:** reserved for an unexpected shared-action-board authority collision

### Observable mission

A production user opening `sector_central.html#overview` can answer in five seconds:

1. where leadership is shifting;
2. which exact action lane is active;
3. the top current names with full names, score, performance, and reason;
4. what is almost ready;
5. what changed.

### Why it matters

This is the first full flagship vertical proving that the design system can turn a legacy multi-engine page into an institutional daily workflow without changing product truth.

### Authority and precedence

1. Turn-3 §§4–10.
2. R2 Sector Central reference.
3. Existing Sector Intelligence workspace/router law.
4. Existing action-board producer and access law.
5. Existing legacy hashes.

### Verified current state

- Sector Central shell and router already exist.
- Current Overview consumes `_us_act_now_board.html.j2`.
- That include is shared with US Stocks and contains a separate visual system.
- Current action board is five exact lanes.
- Current names can abbreviate or ellipsize.
- Current page has long header and footnote copy.
- Current grader exists independently.
- Current PR #6076 owns US Stocks/Prophet regions; it must not be affected.
- No open PR was found for Sector Central.
- Recheck `templates/sector_central.html.j2`, `_us_act_now_board.html.j2`, and `scripts/build_sector_central.py` immediately before branching.

### Exact scope

Owned:

- `templates/sector_central.html.j2` Overview governed region
- one new canonical display partial/macro if needed for:
  - state distribution;
  - resource list;
  - transition row;
  - early-turn list;
  - change strip
- `scripts/build_sector_central.py` only for read-only display projection assembly when required
- tests
- reference/evidence
- migration packet
- registry governed region

Avoid editing `_us_act_now_board.html.j2` unless absolutely necessary; the preferred architecture is a Sector-specific consumer projection over the same canonical `action_board` data so US Stocks does not change.

### Explicit non-goals

- no action-board producer edit;
- no lane rename;
- no count/order change;
- no score change;
- no access change;
- no US Stocks change;
- no map/moving/money/explore/confluence redesign;
- no nav partial change;
- no engine change;
- no grader methodology change;
- no new combined score.

### Complete user journey

1. User opens Overview.
2. Page answer identifies leadership handoff.
3. Context shows regime and as-of once.
4. Five-state distribution shows exact counts.
5. Buy now is selected by default when nonempty.
6. List shows up to three verified current Buy now rows; View all reports the true full count.
7. User selects any other state and list updates without reload.
8. Full names remain visible.
9. Row opens existing group/theme destination.
10. Almost ready rail shows three nearest groups.
11. Leadership handoff shows source → destination.
12. Early turns preserve watch capability without claiming buyability.
13. Change strip shows up to three real payload-resident changes.
14. Record & Method reaches grader/receipts.

### Data, time, null, and correction behavior

- same `action_board` object;
- same lane arrays;
- same order;
- same full counts;
- same score;
- same performance;
- reasons use deterministic mapping or reviewed existing text;
- one page as-of;
- different source clocks shown only when needed;
- zero lane remains visible;
- no lane data triggers explicit partial/error state;
- corrected payload replaces display on next canonical build; no local cache of rank truth.

### Deterministic/statistical/model-generated

- lane/count/order/score: canonical producer;
- display reason: deterministic bounded projection;
- handoff/change strip: payload-resident deterministic composition;
- grader: existing statistical record;
- model copy: prohibited at Tier 1.

### Failure states

Force and prove:

- loading;
- no Buy now;
- no action board;
- stale action board/current prices;
- current actions/delayed handoff;
- one-row lane;
- 27-row Stand aside;
- missing score;
- long EN name;
- long ZH name.

### Ordered implementation

1. Current capability census and exact row-field mapping.
2. Commit migration packet and R2 reference.
3. Assemble read-only display projection.
4. Implement page answer.
5. Implement exact state distribution.
6. Implement selected-state resource list.
7. Implement Almost ready rail.
8. Implement leadership handoff.
9. Implement early-turn list.
10. Implement change strip.
11. Rehome grader/receipts.
12. Preserve all anchors/router behavior.
13. Remove superseded Overview chrome/CSS only inside governed region.
14. Tests and state fixtures.
15. Full evidence matrix.
16. Independent critics.
17. Merge/deploy/prove.
18. Flip Overview region compliant.

### Acceptance tests

- exact lane labels and order;
- exact counts;
- exact selected rows/order;
- score retained;
- no Big Pharma fabricated in Buy now;
- full names no ellipsis at 320–1440;
- state selection URL behavior defined and tested;
- `#actnow-section`, `#regime`, `#grader`, `#read-*` still resolve;
- US Stocks rendered bytes/components unaffected where required;
- no raw model paragraph;
- one page freshness;
- one caveat per concept;
- 390 first-screen contract;
- EN/ZH;
- light/dark;
- no horizontal page scroll.

### Real production proof

- real settled nightly payload;
- counts reconcile;
- top three rows reconcile;
- all five selectors work;
- one destination opens correctly;
- legacy hash opens correct panel/target;
- 1440 dark/light EN/ZH;
- 390 dark/light EN/ZH;
- 320 stress;
- loading/empty/stale/partial/error fixtures;
- running SHA;
- rollback.

### Stop condition

Stop after Overview is live and accepted. Do not begin Moving or shared action-board redesign.

### Required continuation handoff

Return:

- current-to-new capability ledger;
- merge/deploy SHAs;
- screenshots and DOM assertions;
- exact remaining Overview debt;
- any shared-component candidate;
- handoff readiness for `XPV2-SC-MV1`.

---

## HANDOFF 3 — `XPV2-SC-MV1`
### Sector Central What’s Moving institutional migration

**Recommended builder:** Terra or Codex  
**Independent reviewers:** Opus Product Regression + Opus Visual/Taste

### Observable mission

A production user opening `sector_central.html#moving` can immediately identify:

- active leadership handoffs;
- what changed;
- crosscurrents inside fragmented sectors;
- closed event history;

without reading a wall of explanatory text or confusing the view with The Map.

### Why it matters

The current Moving view places events, disclaimers, fragmented-sector prose, and other machine text ahead of the useful task. This PR turns it into a concise leadership-change workflow while preserving the existing rotation-event authority.

### Authority and precedence

1. Turn-3 §4.7 and R2 Moving reference.
2. Existing Sector workspace/router and legacy-anchor map.
3. Existing rotation events and group-flow producers.
4. The Map remains the owner of the whole-market quadrant map.

### Verified current state

- `#moving` exists.
- Rotation events, rotation app, and desk watch are current organs.
- Time Machine and Forming Narratives already live under Explore.
- `rotation_events.js` is a canonical current consumer.
- Fragmented-sector facts exist but are presented as long labelled prose.
- No open PR was found for Sector Central/rotation-events UI; recheck immediately before branch.

### Exact scope

Owned:

- `templates/sector_central.html.j2` Moving governed region
- `templates/rotation_events.js` and paired asset only if required
- display-only helper/partial
- tests
- migration packet
- reference/evidence
- registry region

### Explicit non-goals

- no rotation-event producer change;
- no map redesign;
- no cycle score;
- no new action gate;
- no event reorder unless producer already supplies order;
- no Time Machine work;
- no Explore work;
- no Confluence work;
- no engine change;
- no new alert publication.

### Complete user journey

1. User opens What’s Moving.
2. One answer states number and direction of active handoffs.
3. Active handoffs show source → destination, age, and one read.
4. User opens destination group.
5. Change strip shows recent starts/stops.
6. Crosscurrents compare leading versus lagging pockets.
7. Desk Watch appears only when it has useful content; otherwise a compact quiet state.
8. Closed history is collapsed.
9. Method/receipt explains event meaning once.

### Data/time/null/correction

- active/closed state from existing event data;
- event age from existing dates;
- source/destination unchanged;
- crosscurrent figures unchanged;
- no active events is valid;
- stale events are labelled;
- corrections update same event record/consumer;
- one failed source creates partial state rather than wiping healthy modules.

### Deterministic/statistical/model-generated

- event list/state: existing deterministic producer;
- one-line read: deterministic state projection;
- crosscurrents: existing measured facts;
- model prose: excluded at Tier 1.

### Failure states

- no active handoffs;
- stale event feed;
- events current/crosscurrents unavailable;
- one handoff;
- many handoffs;
- long group names;
- missing age;
- source equals destination invalid fixture must fail closed.

### Ordered implementation

1. Census current organs and fields.
2. Commit packet/reference.
3. Create answer composer.
4. Create transition rows.
5. Add compact change strip.
6. Convert Fragmented Sectors to Crosscurrents comparison.
7. Compress Desk Watch.
8. Collapse closed history.
9. Rehome one explanation into LENS.
10. Preserve hashes.
11. State fixtures/tests.
12. Evidence/critics.
13. Merge/deploy/prove.
14. Flip Moving region compliant.

### Acceptance tests

- active count and rows reconcile;
- no map duplicated;
- source/destination exact;
- event age exact;
- full names;
- no paragraph wall;
- no repeated “not a buy signal” per row;
- Crosscurrents figures exact;
- no event means quiet, not error;
- legacy `#si-movement`, `#rc-events-mount`, `#rotation-app` resolve;
- mobile and keyboard;
- EN/ZH;
- light/dark;
- no page overflow.

### Real production proof

- current event payload;
- active and quiet fixture;
- 1440/390;
- legacy deep link;
- destination drill;
- current build SHA;
- no console errors;
- rollback.

### Stop condition

Stop after What’s Moving is accepted live. Do not begin The Map, Money & Breadth, Explore, or Confluence.

### Required continuation handoff

Return exact readiness for:

- `XPV2-SC-CF1` Confluence;
- `XPV2-SC-MAP1`;
- `XPV2-SC-MB1`;
- `XPV2-SC-EX1`.

---

# 15. Program sequence after the first three PRs

1. `XPV2-LENS-IH1`
2. `XPV2-SC-OV1`
3. `XPV2-SC-MV1`
4. `XPV2-SC-CF1` — Confluence focus + queues + universe/coverage
5. `XPV2-SC-MAP1` — map and selected-detail architecture
6. `XPV2-SC-MB1` — Money & Breadth
7. `XPV2-SC-EX1` — Explore
8. Sector Central whole-route production acceptance
9. China Sector Central delta reference and family port
10. Intelligence-desk family extraction
11. US Stocks whole-page reference after Prophet structural work settles
12. Macro regime-dashboard reference
13. Options/market-structure family after truth repairs
14. Instrument-analyzer family after dossier authority settles
15. Long-tail family migration and ratchet expansion

---

# 16. Exact next action

1. Put the two R2 references and this packet through the four independent critics in §13.
2. Sol adjudicates every blocker and major.
3. Earn Reference Integrity approval receipts.
4. Commit the freeze packet, references, receipts, and three migration packets into the repository.
5. Dispatch `XPV2-LENS-IH1` to a bounded Terra/Codex execution session.
6. Sol reviews the first PR against the reference before merge.
7. Production proof.
8. Only then dispatch `XPV2-SC-OV1`.

No broad “redesign the site” operator prompt is authorized.
