# Sol HK Stock Dashboard V3.7 — Follower Architecture Freeze

Status: **READ-ONLY SOL ARCHITECTURE — HK modification remains gated on Canada V3.7 PROVEN_LIVE**

This packet hardens the HK follower so Fable can move immediately after Canada passes without cloning Canada-specific semantics.

## 1. Product thesis

The HK stock dashboard has one primary authority surface: **Prophet**.

The page should answer, in order:

1. Which HK names deserve attention?
2. Which of those are actually selected as the focused cohort?
3. What is actionable versus still developing?
4. Which themes/sectors are leading?
5. Is mainland/HK flow or structure materially changing the interpretation?
6. How has the system performed historically?
7. Where do I go for specialist research?

Shared UX grammar does not imply shared market semantics.

## 2. Frozen hierarchy

1. **Market Header**
2. **Leading Now**
3. **Prophet** — `Top Picks | All Candidates`, `Grid | Table`
4. **Theme & Sector Leadership**
5. **Evidence & Record**
6. **Research Tools**

No generic permanent Market Context panel.
No second Prophet-like shelf.

## 3. Critical HK authority law: LIVE is conditional

The Canada reference cannot be copied literally here.

If current HK production has **no canonical live quote/change plane**, HK must NOT show:
- a green `LIVE` status implying live stock prices;
- fabricated intraday percentage changes;
- `LIVE` text inside Prophet cards;
- a quote clock newer than the actual source.

In that case show only the truthful owner-native board/data vintage, e.g. a Board/Market Data timestamp if the producer provides one.

If a canonical HK live quote plane is separately proven before implementation, then:
- use Asia convention: **up red / down green**;
- keep Board intelligence clock separate from quote clock.

Fable must prove the quote owner before enabling the live treatment.

## 4. Prophet population law

Previously verified HK structure showed:
- one broader Prophet population;
- a smaller `Featured`/focus cohort;
- actionable and setting-up records that are not identical to the Featured cohort.

For V3.7:

### Top Picks
Use the existing canonical Featured/focus selection owner if it remains current.

`Top Pick / Featured` explains **selection**, not action.
A Featured record may be Buy, Near, Hold, Wait, etc. if the owner emits that state.
Never infer Buy from Featured.

### All Candidates
Use the full current owner-native HK Prophet population.

No synthetic `Now/Early/All` ontology is required if `Top Picks | All Candidates` now expresses the Chairman-approved primary population axis.
Early/developing state should remain a filter/action/lifecycle property of records, not a second Prophet.

## 5. Prophet card/table law

Same shared presentation grammar as Canada:
- compact V4-derived card;
- action owns hue;
- selection halo neutral/cool;
- system/SF/Inter ticker;
- direct one-hop Terminal route for now;
- no decision drawer;
- Grid/Table XOR;
- same filters/population in both modes.

HK table should expose only owner-backed useful columns. Candidate HK-native optional columns may include Southbound/A-H information **only if current producers exist and the values materially aid scan work**.

Do not force Canada columns onto HK.

## 6. Leading Now

At rest show:
- #1 Theme;
- #1 Sector;
- optional deterministic material change cue.

HK may additionally earn one **conditional flow cue** when mainland/HK flow materially changes interpretation, for example:
`Southbound supportive · Banks`

But this cue must be absent when stale, unavailable, or non-material.
It must not become a permanent third dashboard statistic.

## 7. Theme & Sector Leadership

Default:
- ranked Themes + Sectors;
- exact native stance;
- breadth/count;
- representative leaders;
- one shared Expand control.

Expected previously observed themes included examples such as:
- Deep-reset Healthcare;
- Southbound Banks;
- Property Recovery;
- Insurance Reset;
- China Internet.

Expected native stances included examples such as:
- Act now;
- In favour;
- Mixed;
- Watch.

These are examples from the previously verified estate, not permission to hard-code them. Fable must repin current owner data.

## 8. Expanded Leadership — market-native recovery

Do not use the generic V3.7 mockup tone buckets as semantic authority.

Summarize exact current HK native stance counts, e.g. conceptually:
`Themes · 1 Act now · 1 In favour · 1 Mixed · 2 Watch`

Then show full Theme/Sector ranking.

### Southbound / Mainland Money
Decision: **INTEGRATE / COMPRESS**.

Preferred homes, in priority order:
1. conditional Leading Now flow cue if material;
2. Expanded Leadership flow/timing column or subband;
3. full Southbound explorer as Research Tool.

Do not restore a giant permanent Southbound panel above Prophet.

### A/H structure
Decision: **CONDITIONAL**.

Preferred homes:
- optional Table column;
- Expanded Leadership contextual field;
- dossier/deep research.

Only surface on L1 when it changes the interpretation of a name/group.

### Sector Rotation
Feed ranking/timing semantics into Leadership. Do not create another full rotation board on the stock page.

## 9. Evidence & Record

Restore/preserve:
- canonical Track Record;
- Signal History if owner route exists;
- Methodology;
- receipts/provenance where existing.

Compact trust layer only.
No new HK performance ledger.

## 10. Research Tools

Preserve valuable specialist jobs without competing with Prophet:

- Fast Movers;
- Washout / reversion;
- Southbound flow explorer;
- deep Global Risk analysis;
- screener/specialist desks where current producers are live.

These are destinations, not recommendation shelves.

## 11. What remains removed

- giant Global Risk prose at L1;
- separate exposure/funding panel for every diagnostic;
- multiple pick-like shelves;
- generic Market Context shell;
- explanatory card essays;
- decision sidebar.

If old intelligence remains useful, relocate it rather than delete it.

## 12. HK failure/null behavior

- no HK live plane -> no LIVE implication;
- stale Southbound -> omit/degrade flow cue locally, do not mark Prophet stale;
- missing A/H -> omit field, never zero;
- Featured present but action missing -> selection remains; action unavailable;
- leadership producer stale -> warn Leadership only;
- Track Record unavailable -> Evidence entry shows unavailable/omits, no fake stats;
- filtered Top Picks empty -> explicit zero state; do not silently switch to All Candidates.

## 13. HK acceptance fixtures

Required adversarial fixtures:

1. Featured + actionable.
2. Featured + non-actionable/wait state if current producer supplies one.
3. Non-Featured + actionable.
4. Setting-up/developing record.
5. Missing live quote plane.
6. Southbound stale/missing.
7. A/H missing.
8. Track Record route.
9. Grid/Table XOR.
10. leadership filter affecting Prophet without changing underlying selection/action semantics.
11. Asia direction colors only when a true quote/change plane exists.

## 14. Sol review rejection triggers

Reject HK even if CI is green if:

- `Featured` is rendered as equivalent to BUY;
- non-Featured actionable names disappear from All Candidates;
- LIVE is shown without a canonical HK live plane;
- Southbound becomes a second recommendation authority;
- universal Canada group states replace HK native stances;
- Fast Movers/Washout reappear as competing primary shelves;
- Track Record is dropped;
- Grid/Table duplicates population;
- a new HK ranker/quote/history/authority store is introduced.

## 15. Production acceptance target

A five-second HK read should be:

**focused names -> action state -> leadership -> material mainland/HK context -> trust/history**

without asking the user to parse multiple competing intelligence dashboards.
