# Stock Dashboard V3.8 — Action ≠ Leadership Product Architecture Freeze

Status: **SOL ARCHITECTURE FREEZE — records-only; no product code is authorized by this document alone**

Bootstrap: protected Skillpack `Mastermind@ebff50d65b09a2753b6cb9bea3cb2548522932e4` (`mastermind.sol_skillpack.v1`, skillpack `1.0.0`, bootstrap-major `1`).

Pickup base used for this freeze: Macro `main@919d0e66871fc9a32e51882c6337fbbf32a06e62`.

Chairman product finding, 2026-08-26: the V3.7 presentation is technically correct but compresses two different high-frequency user jobs into one surface. In HK, numeric `01..08` is relative-strength rank while the colored stance is cycle/entry action. A user therefore sees apparently contradictory rows such as `RS #1 + Reduce / Avoid` and a lower-ranked sector marked `Buy Now`. At the same time the fan-favorite `What to Act On Now` workflow survived only inside `Expand Leadership`, so the producer remained live while the immediate decision job became hidden.

This is a **product-completeness correction**, not a rollback of V3.7 production truth. Canada V3.7 and HK V3.7 remain historically `PROVEN_LIVE` for the capabilities they shipped. V3.8 changes the next acceptance target for the presentation layer.

---

## 1. Primary user outcome

Within five seconds, a stock-dashboard user should be able to answer two distinct questions without opening a modal:

1. **What groups can I act on or focus on now?**
2. **What groups are strongest / leading on the market’s trend or rotation measure?**

Those questions may point to different groups. That disagreement is information, not an error.

The page must then let the user move directly from the group view into the canonical Prophet candidate population without creating a new recommendation authority.

### Machine/product outcome

The presentation layer must expose existing owner facts without conflating their axes:

- action / entry timing from the current group-action owner;
- trend / relative-strength / theme rank from the current leadership owner;
- Prophet membership/count from the current candidate owner;
- lifecycle/maturity only from its own producer;
- authority exactly as currently declared.

No browser-side score or ranking may be invented to make the composition look cleaner.

---

## 2. The V3.7 defect being corrected

V3.7 made one good move and one wrong move.

Good: it removed giant duplicate dashboards and preserved owner-native semantics.

Wrong: it decided that the old group-action workflow belonged only inside **Expanded Leadership**.

That buried a high-frequency customer job behind a secondary interaction and made Leadership carry too many meanings at once.

### HK concrete semantics

Current HK owns two orthogonal sector reads:

- `#sector-rotation` publishes **relative-strength rank vs HSI** plus cycle state;
- `#act-now` / `#anv2-*` publishes **Buy Now / In Favour / Bottoming Watch / Reduce-Avoid** from the cycle-entry owner.

The V3.7 composer joins them. Therefore a strong trailing leader may legitimately be late-cycle / Reduce-Avoid, while a lower-RS sector may have a clean entry today.

The problem is not the data. The problem is showing `01` beside a red action badge without naming the rank basis, then hiding the direct action map.

### Canada concrete semantics

Current Canada themes have a real owner-published rank in `sector_pulse_canada.json`.

Current Canada V3.7 sectors do **not** have an equivalent rank in the composer. `collectSectors()` walks the four Act-Now lanes and assigns `rank: out.length + 1`. That traversal position is useful display order, but it is not a canonical sector-strength rank and must not be rendered as though it were one.

### China concrete semantics

The current China estate already has an owner-produced `What to Act On Now` board and separate sector/theme timing / ranking machinery. The old panel is too dense, but its user job remains high value. The earlier V3.7 China follower proposal inherited the same mistaken assumption that group-action semantics should live only in Expanded Leadership; V3.8 supersedes that narrow placement ruling before China implementation begins.

---

## 3. Governing product laws

### 3.1 Axis separation

`Selection ≠ Action ≠ Lifecycle/Maturity ≠ Fillability ≠ Trend Leadership ≠ Authority`

- **Selection**: why a stock is in the focused cohort.
- **Action**: what can be done now according to the canonical action owner.
- **Lifecycle/Maturity**: where the setup is in its own process.
- **Fillability**: whether the opportunity is actually executable where a producer owns that truth.
- **Trend Leadership**: strength / rotation / theme rank on an explicitly named owner metric.
- **Authority**: how strongly the system is entitled to claim the conclusion.

Never visually imply these are interchangeable.

### 3.2 Action owns hue

Action/tactical stance may own the strong green/blue/amber/red treatment.

Selection remains neutral/cool.

Trend rank is primarily ordinal/textual. A high rank is not automatically green.

### 3.3 A numeric rank requires a rank owner

Every visible numeric group rank must answer:

- Who owns it?
- What does it measure?
- What benchmark / universe / clock does it use?

If those answers are unavailable, do not render a rank number.

**Lane traversal order is never a rank.**

### 3.4 Shared grammar does not create a universal ontology

The shared product can render four lanes in HK/Canada/China and five lanes in the US. It must not rewrite market-native owner states merely to make every country look identical.

---

## 4. Canonical V3.8 page hierarchy

For markets with a current group-action owner:

1. **Market Header**
2. **What to Act On Now** — compact at-rest action map
3. **Prophet** — primary stock candidate workspace
4. **Leadership & Rotation** — analytical trend / rank surface
5. **Evidence & Record**
6. **Research Tools**

The standalone V3.7 **Leading Now** strip is absorbed into the first two layers where it would otherwise repeat action or leadership. A market-specific material cue may remain compactly in the Action or Leadership header only when a canonical producer owns it.

This change is deliberate: the user should not need three separate group summaries (`Leading Now`, hidden Act Now, Leadership) to understand one market.

If a market lacks a canonical group-action owner, omit `What to Act On Now` rather than synthesizing one from rank.

---

## 5. What to Act On Now — the restored customer job

### 5.1 Purpose

Answer:

> **Where should I focus my attention today, and which groups are moving out of favor?**

This is a tactical grouping surface. It is not Prophet, not a new ranker, and not a track record.

### 5.2 Desktop composition

At rest:

- one compact panel;
- owner-native action lanes side by side;
- lane title + total count;
- no more than **3 group rows per lane** before `View all N`;
- panel should target roughly **≤240 px** of vertical depth at 1440×900 when the lane caps are not expanded;
- Prophet must visibly begin in the first decision viewport.

Each at-rest group row may contain only:

1. group name;
2. optional type cue (`Theme` / `Sector`) when mixed kinds share a lane;
3. optional current Prophet-name count **only when canonical membership is known**;
4. a route/filter affordance.

Do **not** place these in the at-rest row:

- 20d/60d performance;
- 5d relative returns;
- arbitrary priority score;
- percentile position;
- multiple diagnostic chips;
- prose rationale;
- a numeric leadership rank.

Those are depth/research fields, not the immediate action map.

### 5.3 Lane language

Use the exact current owner-native labels.

Current HK/Canada owner family:

- `Buy Now`
- `In Favour`
- `Bottoming Watch`
- `Reduce / Avoid`

China must repin current owner labels at implementation time. If they remain the same family, reuse them verbatim. If current China semantics differ, preserve the producer.

The US currently owns a five-lane grammar and remains a separate later architecture/cutover wave.

### 5.4 Interaction law

When canonical group membership exists:

`current Prophet population -> action-group filter -> same Prophet population`

Clicking a group must **not** silently change `Top Picks | All Candidates`.

If Top Picks contains zero names but All Candidates contains matches, preserve the empty Top Picks state and offer the deliberate switch control already proven by V3.7.

If group membership is known and the current Prophet board contains **zero total names** for that group, the row remains useful as a group-research destination. Do not pretend the zero is an error.

If membership is unavailable, omit the count/filter behavior and keep the group-detail route. Missing ≠ zero.

### 5.5 Mobile composition

At ~390px:

- show one horizontal segmented lane selector with all lane titles/counts;
- render one lane body at a time beneath it;
- default to `Buy Now` when non-empty, otherwise the highest-urgency non-empty native lane;
- no horizontal page overflow;
- no four stacked giant lane cards;
- `View all` expands only the active lane.

---

## 6. Leadership & Rotation — the analytical job

### 6.1 Purpose

Answer:

> **Where is market strength / theme leadership / rotation concentrated, and how mature is that leadership?**

It must no longer masquerade as the answer to “what should I buy now?”

### 6.2 Explicit rank basis

Never display a bare `01`, `02`, `03` without the user being able to see what is ranked.

Good examples:

- `RS #1` with header `Relative strength vs HSI`;
- `Theme #1` with header `Theme rank`;
- `Rotation #1` where the owner explicitly calls it rotation rank.

Bad:

- unlabeled `01` beside `Reduce / Avoid`;
- numbering rows because they happen to be rendered first;
- client sorting used as permanent “rank”.

### 6.3 At-rest row contract

At rest, keep this surface compact. Prefer at most the top **5 owner-ranked groups** before expansion.

A row may show:

- explicit rank + basis;
- group name;
- owner cycle/maturity state;
- owner action stance as a **separate** field/chip;
- representative leaders where useful;
- current Prophet-name count where canonical.

Label the count `Prophet`, `Candidates`, or equivalent. Do not use an ambiguous header such as `BOARD`.

Deeper fields such as 20d/60d RS, rank deltas, Southbound context, breadth internals and extended diagnostics belong in `Expand Leadership` / the underlying group page.

### 6.4 Contradiction fixture is required

The implementation must prove a case where trend rank and action disagree.

Example class:

`RS #1 · late cycle · Reduce / Avoid`

versus

`RS #8 · buy zone · Buy Now`

The UI passes only if a reasonable user can understand that one axis is **trend strength** and the other is **entry timing**.

A tiny help tooltip may say:

> Trend rank measures relative strength; Action measures entry timing. A strong leader can be late-cycle.

Do not add a paragraph to every row.

---

## 7. Experience reference composition

Desktop, conceptual only:

```text
[ Market Header / board clock / truthful freshness ]

WHAT TO ACT ON NOW
┌ Buy Now (3) ─────┬ In Favour (2) ────┬ Bottoming (0) ────┬ Reduce/Avoid (3) ┐
│ Financials  2 P  │ Exchange       0 P │ —                  │ Healthcare   0 P │
│ Insurance   4 P  │ Energy         0 P │                    │ Industrials  1 P │
│ Telecom     0 P  │                    │                    │ Consumer     1 P │
└──────────────────┴────────────────────┴────────────────────┴───────────────────┘

PROPHET
[ Top Picks | All Candidates ] [ Grid | Table ] ...

LEADERSHIP & ROTATION                         Relative strength vs HSI (?)
RS #1  Healthcare       Nearing a high       REDUCE / AVOID     0 Prophet
RS #2  Exchange         Nearing a high       IN FAVOUR          0 Prophet
RS #3  Financials       Buy zone             BUY NOW            2 Prophet
RS #4  Insurance        Buy zone             BUY NOW            4 Prophet
[ Expand leadership ]

EVIDENCE & RECORD
RESEARCH TOOLS
```

The exact names/counts above are illustrative of the current HK state; production always binds to current owners.

---

## 8. Market-specific bindings

## 8.1 Hong Kong — reference implementation market

Current source laws:

- Action lanes: existing `#act-now` / `#anv2-buy`, `#anv2-pull`, `#anv2-bot`, `#anv2-red` owner DOM.
- Leadership rank: existing `#sector-rotation` **RS vs HSI** rank.
- Cycle state: existing sector-rotation / cycle owner.
- Prophet membership: current HK Prophet table/card owner.
- Top Picks: current `pv-featured` cohort, never positional.
- Quotes: no canonical per-ticker HK live quote plane today; V3.8 must retain the V3.7 no-LIVE law.
- Southbound: remains materiality-gated and compressed into Leadership/Research; never becomes another action authority.

Required HK V3.8 correction:

1. Restore the native action lanes at rest above Prophet in compressed form.
2. Remove the action band from being the only home inside `Expand Leadership`.
3. Rename/reframe `Sector Leadership` as `Leadership & Rotation` or equivalent.
4. Render explicit `RS #N` / `Relative strength vs HSI` labels.
5. Rename ambiguous `BOARD` count to `Prophet` / `Candidates`.
6. Keep action stance visible as a separate axis.
7. Preserve every V3.7 Prophet/Evidence/Research/no-LIVE/entitlement law.

## 8.2 Canada — follower correction

Current source laws:

- Action lanes: existing Canada `#act-now` / `#anv2-*` owner DOM.
- Theme leadership: `canadabasketdata/sector_pulse_canada.json` publishes real `themes[].rank` and owner stance.
- Sector action state: current Act-Now owner.
- Current V3.7 sector numeric `rank` is generated by lane traversal inside `collectSectors()` and is **not** an accepted sector-strength rank.

Required Canada V3.8 correction:

1. Restore native action lanes at rest above Prophet.
2. Preserve ranked **Themes** where the owner publishes rank.
3. Do **not** render numeric Sector rank unless a current canonical sector-rank owner is independently found and named.
4. If no sector-rank owner exists, sectors remain fully useful through What to Act On Now and group detail without invented numbers.
5. Preserve Canada live quote treatment, Top Picks first-five accepted projection, Table, Track Record and Terminal routes exactly unless a separate defect is found.

## 8.3 China — next separate follower, not this regional carrier

The earlier China V3.7 follower freeze remains useful for population, fillability, quote, Track Record, screener and research-tool boundaries, but its action placement is superseded here.

Before any China modification:

- repin the current China action owner;
- repin current theme/sector rank owners;
- repin current selective/Featured population owner;
- re-check current quote/change ownership;
- re-check concurrent China intelligence/CN-Limit paths.

China V3.8 at-rest action panel must be **dramatically simpler** than the current giant China board:

- preserve native lane titles/counts;
- cap rows;
- group name first;
- no 20d/5d performance stack at rest;
- no position percentile at rest;
- no score tower;
- no duplicate lifecycle diagnostics already visible in Prophet;
- detailed theme/sector evidence moves to Leadership expansion or the group page.

The China implementation is a **new carrier after the HK/Canada correction is production-proven**. Do not add China writes to the HK/Canada carrier.

## 8.4 United States — held

US retains its separate V4/convergence/cutover prerequisites.

Future US adoption should preserve the current owner-native five-lane action grammar rather than forcing the regional four-lane family.

No US product code is authorized by this freeze.

---

## 9. Capability ledger at freeze time

| Capability | State | Ruling |
|---|---|---|
| HK V3.7 Prophet / Evidence / Research | `PROVEN_LIVE` | Keep; no redo |
| HK action producer | `PROVEN_LIVE` | Restore prominent compressed consumer |
| HK at-rest What to Act On Now job | `PARTIAL` | Data exists but primary workflow is buried in expansion |
| HK leadership rank | `PROVEN_LIVE` data, confusing presentation | Keep rank; label basis and separate from action |
| Canada V3.7 Prophet / Evidence / quotes | `PROVEN_LIVE` | Keep; no redo |
| Canada action producer | `PROVEN_LIVE` | Restore prominent compressed consumer |
| Canada at-rest action job | `PARTIAL` | Same product-completeness issue |
| Canada theme ranking | `PROVEN_LIVE` source | Keep owner rank |
| Canada sector numeric V3.7 rank | `REJECTED_BY_DESIGN` for V3.8 | Traversal position is not rank |
| China existing What to Act On Now | `PROVEN_LIVE` but over-dense | Compress, do not delete |
| China V3.8 follower | `NOT_BUILT` | Fresh producer census first |
| US V3.8 adoption | `NOT_BUILT` / held | Separate US architecture |

---

## 10. Failure / null behavior

### Action owner missing

Omit/degrade `What to Act On Now` locally. Never synthesize action from leadership rank.

### Rank owner missing

Keep the action map. Hide numeric rank and rank language. Do not infer rank from lane/order.

### Membership missing

Omit Prophet count/filter for that group. Missing membership is not zero membership.

### Known zero Prophet names

Show a truthful zero or quiet `No current Prophet names`; keep the group-research route usable.

### Top Picks zero under selected group

Preserve Top Picks, show explicit zero state, and offer deliberate switch to All Candidates only when that broader population has matches.

### Stale group-action data

Degrade the Action panel only. Do not mark Prophet or quotes stale.

### Stale rank/rotation data

Degrade Leadership only. Do not erase current action state.

### Composer failure

Progressive enhancement must leave the existing legacy page usable, as V3.7 already requires.

---

## 11. No-rebuild / no-authority boundaries

For HK/Canada V3.8 correction:

- no new action mapping;
- no new ranker;
- no new sector/theme score;
- no new Prophet membership rule;
- no new lifecycle/fillability rule;
- no new quote plane;
- no new Track Record ledger;
- no auth/entitlement change;
- no candidate reordering;
- no template/engine/data change merely to make the UI easier if the current owner DOM already exposes the truth;
- no US or China write in the same carrier;
- no resurrection of giant legacy action boards;
- no permanent diagnostic prose above Prophet.

Expected HK implementation scope should remain presentation/test code unless a fresh census proves an unavoidable missing consumer seam.

---

## 12. Ordered implementation sequence

### V38-R1 — HK reference correction

Operator: **Fable** as principal carrier owner; bounded workers allowed.

Mission:

> Make the current HK V3.7 page let a user see owner-native group action immediately while clearly separating RS leadership from entry/action timing, without changing any underlying owner semantics.

Expected primary paths:

- `site/hk-stock-v36.js`
- `tests/test_hk_v37_composer.py` (or a correctly named V3.8 successor if the repository convention warrants it)

Only widen scope if current-main archaeology proves the existing composer cannot lawfully consume the current owner DOM.

R1 stops at **HK PROVEN_LIVE V3.8 correction**. It does not start China or US.

### V38-R2 — Canada follower correction

Released only after R1 production proof.

Mission:

> Port the interaction grammar, not HK rank semantics: restore the Canada action map at rest, keep real theme rank, and remove any presentation-owned sector rank.

Expected primary paths:

- `site/canada-stock-v36.js`
- `tests/test_canada_v36_composer.py`

R2 stops at Canada production proof.

### V38-R3 — China follower

Separate carrier, separate fresh census after R1/R2 acceptance.

No automatic start from this architecture PR.

---

## 13. Adversarial acceptance tests

### 13.1 Action prominence

- Without opening any modal, a desktop user can identify every native action lane and at least the first three groups in populated lanes.
- Group action is not recoverable only through `Expand Leadership`.
- China reference composition contains no old giant metric stack at rest.

### 13.2 Rank/action separation

- A fixture with `rank #1 + Reduce/Avoid` renders honestly and understandably.
- A lower-ranked `Buy Now` fixture remains Buy Now.
- Rank label names its basis.
- Removing the rank-basis label must fail a discriminating test where applicable.
- Replacing owner rank with lane index must fail.

### 13.3 No presentation-owned rank

- Canada sector rows cannot display numeric rank sourced from `out.length + 1` / traversal position.
- If no owner sector rank exists, the UI omits the number rather than creating one.

### 13.4 Prophet interaction

- Action-group filtering preserves Top Picks/All Candidates.
- Grid/Table remain XOR and preserve the same selected group.
- Zero Top Picks never silently widens to All.
- Known zero vs unknown membership remain distinct.

### 13.5 Product density

At 1440×900:

- Header + compact What to Act On Now + start of Prophet are visible in the first decision viewport.
- Action panel target ≤240 px when collapsed.
- No lane shows more than three rows before explicit expansion.
- At-rest action rows do not carry 20d/60d/5d performance stacks, score towers or percentile fields.

### 13.6 Mobile

At 390px:

- one active action lane body at a time;
- all lane titles/counts accessible through the segmented selector;
- no horizontal overflow;
- Prophet cards remain one full-width decision card;
- Action lane change does not mutate Prophet selection until a group is actually chosen.

### 13.7 Existing V3.7 invariants

Regression tests continue to prove:

- correct Top Picks owner;
- no silent population switch;
- Grid/Table XOR;
- Track Record owner;
- no fake LIVE in HK;
- Canada quote/board clocks remain distinct;
- `.sm-hidden` rescue stays intact;
- sig-neu Southbound suppression stays intact;
- direct research/Terminal routes remain real;
- progressive enhancement keeps the legacy surface usable.

---

## 14. Production proof

Green CI is not acceptance.

For each implementation market, proof must use the real entitled production path and current owner data.

Minimum matrix:

- desktop light + dark;
- EN + ZH;
- 390px;
- action panel collapsed + expanded lane;
- each non-empty native lane;
- at least one action-group → Prophet filter;
- zero Top Picks / broader matches path;
- Grid + Table after group filter;
- Leadership rank basis visible;
- contradictory rank/action fixture when present in current data or a faithful local exact-byte fixture plus production rank/action states;
- Evidence & Record route;
- current entitlement/quote/no-LIVE invariants;
- no console error / no overflow.

---

## 15. Supersession map

This freeze **does not** invalidate the whole V3.7 architecture.

It supersedes only these narrow product-placement assumptions:

### V3.7 Functional Completeness Freeze

Superseded:

- `Old group action lanes -> RECOVER SEMANTICS -> Expanded Leadership` as the sole normal home.
- `Leading Now` as a mandatory separate layer when it duplicates group action or trend leadership.

Still controlling:

- Prophet population and XOR laws;
- card law;
- Evidence & Record;
- research-tool demotion;
- authority boundaries;
- production proof law.

### HK V3.7 follower architecture

Superseded only where it put action summary solely inside Expanded Leadership or used a bare #1 sector as the primary “leading now” read.

Still controlling:

- Featured = selection, not action;
- no fabricated LIVE;
- Southbound materiality gate;
- sector-rotation owner rank;
- Track Record;
- specialist-tool depth hierarchy;
- failure/null law.

### China V3.7 follower architecture

Superseded only for the old hierarchy/Leading-Now/Leadership placement that hides the high-frequency action map.

Still controlling for future China work:

- population/fillability separation;
- screeners remain separate;
- theme-cycle / reversion / turn depth hierarchy;
- risk backdrop demotion;
- Evidence & Record integrity;
- no fake quote/live/rank authority.

---

## Final law

> **The strongest group is not necessarily the best entry, and the best entry is not necessarily the strongest group. Mastermind must show both truths clearly instead of forcing the user to infer the difference.**

And the migration law remains:

> **Simplicity through compression, not simplicity through deletion. High-frequency customer jobs stay prominent; low-frequency evidence moves into depth.**
