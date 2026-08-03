# Sector Intelligence Consolidation — Masterplan (by Fable)

Status: ACTIVE build program, 2026-08-01. Operator charter: "investigate all 3 pages …
combine the three pages into one sector intelligence platform that does holistic sector
and theme analysis as well as their rotational analysis … you are authorized to
consolidate, merge, group, create, remove, upgrade any features."

Program scope: **US surfaces only.** China mirrors (`sector_central_china`,
`baskets_china`, `subsector_rotation_china`) are a follow-up program that ports this
pattern; this build must not break their shared JS (`subsector_rotation.js` via
`window.SR_CFG`).

---

## §0 ACCEPTANCE GATES (not done unless)

1. **One page.** `sector_central.html` is the single US sector/theme/rotation hub,
   titled **Sector Intelligence**. `baskets.html` and `subsector_rotation.html` render
   as redirect stubs (meta-refresh + canonical + one-line pointer with anchor links);
   every feature on the kill list below is either absorbed or dead — no orphaned
   full-page duplicates.
2. **Five-second test at the top.** A cold reader landing on the page sees, without
   scrolling: the rotation state in plain words, this week's handoff, and the action
   shortlist. No wall-of-text hero paragraphs (the old sector_central hero prose and the
   old subsector_rotation 60-word subtitle both fail this and die).
3. **One vocabulary.** Quadrants: Leading / Improving / Weakening / Lagging (map, now).
   Cycle phases: Bottoming / Prime entry / Trending / Topping / Rolling over (clock,
   history). Action lanes: 🟢 Buy now / 🔵 Wait for a pullback / 🟠 Take profits /
   ⚪ Reduce–avoid. No second synonym set anywhere on the page; EN/ZH parity.
4. **Epistemic line intact.** Gated conviction (graded, logged) appears ONLY in the
   verdict/action layer, from the existing sector_central conviction engine + baskets
   action lanes. Every subsector/velocity/turn instrument stays display-only with its
   "ranks nothing, gates nothing, sizes nothing" posture — caveat walls compressed to
   `?` receipts per DESIGN_DOCTRINE, not deleted. **No new combined score, no
   rotation×cycle gate (DO_NOT_REBUILD: rotation×cycle confluence is DON'T-TEST; no
   `sector_rotation_schedule`-shaped parallel surface).** The self-grader chip
   ("N calls logged … measured, not asserted") survives.
5. **Page weight.** Rendered `sector_central.html` ≤ ~400KB. The 1.43MB inline
   `var BASKETS` payload is externalized to a stamped data file; below-fold JS sections
   mount lazily. No inline per-basket member tables (they live on `basket/*` detail
   pages, which 909 ticker-page links depend on — keep alive).
6. **Nav simplification.** US "Sector Central" submenu: 4 entries → 2
   (**Sector Intelligence**, **Subsector Confluence**). `_navlinks.html.j2` only; no
   third header family; China/HK/Canada nav untouched.
7. **Nothing silently lost.** Every retired section is accounted for in the PR body's
   disposition table (absorbed → where / killed → why). Detail-page families
   (`basket/*`, `rotation/*`, `subsector/*`), `sector_cycles.html`,
   `subsectors.html`, `state_of_themes.html`, `sector_heatmap.html` keep working, with
   inbound links updated to the new anchors.
8. **Proof.** Local render + browser verification light/dark/EN/ZH with per-section
   crops in the PR body; `python -m scripts.check_template_site_sync --fix` clean;
   nav-gap check, public-chrome tests, and the full relevant pack green; commit → push
   → PR → `merge-on-green` per ship loop.

---

## §1 The problem (measured, 2026-08-01)

Six US surfaces answer one user question ("where should my money be, at what
granularity, and when?") in four costumes and three taxonomies:

| Page | Costume | Universe | Overlap |
|---|---|---|---|
| `sector_central.html` (98KB) | 0–100 cycle clock + gated conviction | 11 sectors + 47 baskets | cycle map, conviction board, flow, heat, LAS leadership |
| `baskets.html` (1.5MB!) | action lanes + RRG quadrant | 47 baskets (incl. 11 sector-EW) | "Do this now", rotation map, breadth, explorer |
| `subsector_rotation.html` (124KB) | velocity/RRG + turns, "not a buy list" | 269 Finviz subsectors / 41 themes / 11 ETFs | rotation map, turns, rotating in/out, events, Time Machine |
| `subsectors.html` | entry funnel (T1–T4) | curated S&P/NDX/R2K/baskets | rotation read + universe toggles again |
| `sector_cycles.html` | full cycle study | 11 sectors | the clock again, full-page |
| `state_of_themes.html` | narrative lifecycle | 18 stories | "which theme is working" again |

Three RRG-style position visuals, three ranked tables, two breadth blocks, two flow
reads, two action layers, two meanings of "theme" (47 curated baskets vs 41 Finviz
groupings), and four frameworks the user must reconcile unaided (does Leading =
Trending = In favour = Tailwind? no surface says). The nav offers four parallel
siblings under one flyout. This is the decision fatigue the operator named.

Found along the way (fix in-scope): the "Momentum & flow board" on
subsector_rotation reads `_data.velocity_board` from `subsector_rotation.json`, but
that key is only ever written to `rotation_events.json` — the section is dead in
production (hidden by its `!vb` guard). Kill it (redundant with Rotating in/out).

## §2 The design: one funnel, three granularities

**Page = Sector Intelligence** (`sector_central.html`, kicker "US SECTOR
INTELLIGENCE", ZH 行业智慧 — matches the Cycle Intelligence 周期智慧 naming family).
Structure mirrors how a trader thinks — verdict → map → evidence → depth — so "where
to go next" is always "keep scrolling," and every deeper layer is one click, never a
different page:

**Sticky section rail:** Verdict · Map · Movement · Money · Explore.

1. **VERDICT (hero)** — absorbed from baskets' hero (the best pattern in the estate):
   state headline ("Money is rotating"), one plain sentence, THIS WEEK'S HANDOFF card
   (losing → taking the lead), state chips (days-in-state, seasonality, policy risk,
   sizing posture). Server-rendered from the existing `BASKETS.story` payload.
2. **DO THIS NOW** — baskets' action lanes fused with the conviction board: one row
   per name across sectors+themes (chip-labeled SECTOR/THEME), lane = stance, line =
   20d-vs-S&P + reason phrase; the conviction board's gated read (reasoning trace,
   grade history) becomes the row's expand/popover instead of a second board. Footer
   links "Drill to stocks → Subsector Confluence". Scope-independent (curated,
   gated universes only — subsectors never enter this layer).
3. **THE MAP** — one section, ONE scope control (Sectors 11 · Themes 47 ·
   Subsectors 269), two stacked instruments sharing it:
   - **Rotation card** (now): the `SRR` renderer from `subsector_rotation.js`
     mounted via `SR_CFG` (portability proven by the China variant). Scope units:
     Sectors = the existing real-price ETF unit; **Themes = OUR 47 baskets fed into
     the SRR node schema via a small adapter over the `BASKETS` payload** (the rvx
     map's RS×momentum data, same RRG concept); Subsectors = the existing Finviz
     269 unit. **The Finviz "Themes 41" unit dies** — "Themes" on this page means
     our 47 curated baskets, always; the Finviz taxonomy survives only at subsector
     granularity where it is the only source (scope caption carries the source
     honesty: "broad Finviz universe — display only"). This kill resolves the
     two-meanings-of-"theme" defect at the root.
   - **Cycle card** (history): the existing `sector_cycles.js` embed
     (`window.SECTOR_CYCLES`), families sectors/baskets as today. At Subsectors
     scope the card quiets with an honest note (no cycle series exists there).
   - Below each card: its phase/quadrant counts in the unified vocabulary; deep
     links to `sector_cycles.html#<id>` for full history. The §5 vocabulary bridge
     `?` lives on this section's heading.
4. **MOVEMENT** — the subsector_rotation evidence suite, compressed: Turns this week
   (turned up/down, still forming, handoffs) · Rotating in / Rotating out · Rotation
   events (donor→receiver flow lanes + fragmented-sector chips) · one compact
   **Desk watch** module folding Turn Desk + Earliest-flow-signs into quiet
   display-only rows (they are usually empty; a quiet tape is a valid read).
5. **MONEY & BREADTH** — ETF creation/redemption flow table (unique data, unchanged)
   · Under-the-hood breadth (from baskets) · Market-heat scorecard (compact embed +
   "Expand → sector_heatmap.html") · index leadership (LAS) as one compact card.
6. **EXPLORE** — scope-aware ranked table (the subsector 12-col table / theme
   performance table / sector table unify here) with search + sort; rebased
   performance chart (vs S&P / absolute); **Time Machine** (lazy, collapsed);
   **Track record** (conviction self-grader + subsector turn track record, one honest
   module); one merged methodology footer (single as-of, single disclaimer — the
   current stacked-disclaimer walls compress to `?` receipts).

**Kill list** (features, not data): baskets' standalone rotation map section ·
sector_central's standalone conviction-board section (content lives in DO THIS NOW
expands) · subsector_rotation's dead velocity board · duplicate breadth block ·
duplicate hero prose · vetoed/duplicated rank tables outside EXPLORE · three of the
four "theme rotation" reads (one survives, scope-switched) · stacked disclaimers.

**Survivors elsewhere:** `subsectors.html` (Subsector Confluence) stays — the
stock-entry funnel is a different deliverable (the "then what do I buy" step), linked
from DO THIS NOW. `sector_cycles.html` stays as the cycle study (Research menu).
`state_of_themes.html` stays (narrative artifact; naming cleanup is follow-up).
Detail families stay. `sector_heatmap.html` stays (its mini rotation strip repoints
to the new anchor).

## §3 Data plumbing (no new signals; presentation-tier only)

Census-verified facts this rests on: `site/baskets.html`'s 1.5MB = three inline
blobs (BASKETS 841,707 + CHART 305,139 + THEME_ALERTS 209,759 chars = 86.2% of the
file), and `site/basketdata/baskets.json` (1.14MB) ALREADY carries the same
baskets+chart+theme_intel payload on disk nightly. The V1 "Theme Rotation Desk"
fork inside `baskets.html.j2` (~1651–2179 + CSS ~88–309: renderThemeDesk /
renderConcentration / renderRotation / renderScorecards / renderMacroCtx /
decorateRealActivity / renderStanceChips) is dead — `boot()` never calls it and its
container ids don't exist. The intl pages' live twin (`_baskets_desk.html.j2` +
`baskets_desk.js`) is untouched by this program.

- The consolidated page **fetches `basketdata/baskets.json`** (the artifact that
  already exists) instead of embedding; `THEME_ALERTS` moves to a new
  `basketdata/theme_alerts.json` fetched lazily by the bell. Verdict hero stays
  server-rendered from `theme_context` (paints before any fetch).
- `build_baskets.py` keeps computing everything it computes today; its render step
  emits the redirect stub at `baskets.html` + the alerts JSON; all other outputs
  (basketdata/*, detail-page inputs, radar.html, addons) unchanged.
- `build_sector_central.py` renders the consolidated template with the merged
  context (theme_context + factor_season + flows + its own payload emission,
  unchanged); self-grader unchanged. DAG order already correct
  (`build_baskets` → … → `build_sector_central`).
- `build_subsector_rotation.py` unchanged (JSON feeds the map/movement layers);
  its page template becomes a stub; `subsector_rotation.js` mounts on the merged
  page via `SR_CFG` (China contract untouched).
- Conviction-trace expands join lanes rows to `SECTOR_CENTRAL` records by id
  (`b-<basket_id>` / sector id). Kind separation is law (engine already prevents
  proxy-basket ↔ sector rank borrowing): a row's expand shows ITS record only, with
  a link to the sibling read (cap-weighted ETF ↔ EW basket), never a merged rank.
- Rotation events / Turn Desk / TAPE-ONSET / Time Machine feeds unchanged.

## §3b Found defects fixed in-scope

1. Dead V1 desk fork in `baskets.html.j2` (~27% of the template) — deleted with the
   template's retirement.
2. Dead "Momentum & flow board" on subsector_rotation (reads `velocity_board` from
   the wrong artifact; hidden in production) — killed, not rewired (redundant with
   Rotating in/out).
3. `basket_detail.html.j2` back-link label "← Theme Rotation Desk" (names a design
   that no longer exists) → "← Sector Intelligence", href unchanged
   (`../sector_central.html`... adjust to actual filename with anchor).
4. Bell deep-link `openTheme()` no-ops (targets nonexistent `#theme-<id>`) →
   repoint items at `basket/<id>.html`.
5. "(Equal-Weight)" de-labeling at boot (FIX 1a/1b) — replaced by explicit kind
   chips (`SECTOR` / `SECTOR EW` / `THEME`) on lane rows and card surfaces.
6. `risk_state_live.js` loaded by sector_central but targeting other pages'
   elements — script tag dropped from the merged page.
7. `engine/subsector_rotation.py` docstring "34 hand-curated baskets" is stale
   (47) — corrected in passing.

## §4 Build plan

**Base-shell decision:** the consolidated template STARTS FROM `baskets.html.j2`'s
rvx layer (the estate's most modern, doctrine-compliant shell: tape band, alerts
bell, hero, lanes, under-the-hood, explorer) — renamed, re-titled Sector
Intelligence, emitted at `sector_central.html`. The old `sector_central.html.j2`
contributes organs (cycle-map embed block + data preloads, conviction/trace data,
flow table, heat scorecard, LAS strip, grader); `subsector_rotation.html.j2`
contributes organs (SRR map mount, turns rail, rotating in/out, rotation events,
Desk watch, lazy Time Machine). Rework-in-place of the older shells is explicitly
rejected.

Opus `builder` lanes, sequential on this branch (one template file — no parallel
edits): **Wave A** = merged template (baskets shell → sector_central.html) + hero/
lanes with conviction-trace expands + payload externalization (`baskets_data.js`) +
build script rewiring + redirect stubs (clone `vector_allocation.html.j2` pattern).
**Wave B** = map section (SRR mount + 47-basket adapter unit + cycle embed + scope
control) + movement section (turns/in-out/events/Desk watch) + explore (scope-aware
table + chart + lazy Time Machine + merged track record) + nav rewiring + primary
inbound-link sweep (`dashboard.html.j2`, `sector_heatmap` strip PAGE_HREF,
`subsectors.html.j2`; long-tail links ride the stubs) + tests (stubs, nav-gap,
template-site sync, markup-pin updates: ftr_w1/ftr_w3/group_flow/validated-claims,
weight assertion). **Reviewer (opus)** adversarial pass before ship; main loop
verifies visually and ships.

## §4b Build notes — deviations from §2/§4 (recorded during the build, 2026-08-01)

1. **Map scopes shipped as Sectors/Themes over the rvx instrument** (11 EW proxies vs
   36 themes, one scope filter) with the cycle clock beside it; the SRR-with-47-unit
   upgrade (§2's adapter/server-unit idea) is DEFERRED — instead the whole-market SRR
   app ships intact in MOVEMENT pinned to its broadest universe (269 subsectors + 11
   ETFs). Rationale: zero-risk transplant of two proven instruments beats a new
   cross-payload adapter in the consolidation PR; the IA story stays clean ("the map
   = our curated universes; movement = the whole market").
2. **Finviz-41 themes unit killed by FLAG, not by data removal**
   (`themes_unit:false` + renderer guard): `engine/neuralweb/thematic_state.py`
   consumes the themes array for quadrant rollups — data product survives, UI dies,
   China (no flag) unaffected.
3. **Handoff artifact is `basketdata/si_handoff.json`**, NOT theme_context.json —
   that path already had a single owner (`engine.theme_context.write_context`) and a
   Neural Web lobe reader (`world_state.py`); one-writer law respected.
4. **The 11 cap-weighted sector conviction cards keep a compact board** inside the
   map section (sectors-only render of the donor board); basket-kind conviction
   surfaces exclusively via the lane trace-expands. Prevents the sector reads from
   becoming unreachable (lanes are basket-native).
5. **deepStrip stays** (display cleanliness); the ambiguity defect is solved by kind
   chips (`SECTOR EW`) on lane rows, not by un-stripping names everywhere.
6. **Wave A builder was killed** after 33 minutes of zero-output analysis; the
   template merge was executed in the main loop via marker-asserted assembly
   scripts; narrow extraction (rotation_events/desk_watch/time_machine JS) went to a
   bounded builder instead.

### Follow-ups (PR-A1, 2026-08-02)

7. **Forming Narratives panel mounted at the end of MOVEMENT.**
   `engine.narrative_emergence` has emitted `site/basketdata/narrative_emergence.json`
   for US nightly all along, and `templates/_forming_narratives.html.j2` was already
   mounted on baskets_china/hk/canada/intl — never on any US page. The US read was
   computed and never shown. It ends MOVEMENT deliberately: the funnel descends gated
   lanes → map → whole-market motion → what is forming next. No new rail entry; the
   panel is display-only and self-hides when the JSON is absent.

8. **`state_of_themes` naming aligned to the nav promise "Theme Tracker / 主题追踪".**
   One artifact carried three names — slug `state_of_themes.html`, page title "State
   of Themes"/主题态势, nav label "Theme Tracker"/主题追踪. The nav promise wins: a
   user who clicks "Theme Tracker" must land on a page that says Theme Tracker. The
   **slug is kept** — URL churn is not worth it on a page linked only from the nav,
   and the SEO canonical stays stable. Display copy moved (title, seo_title, brand,
   plus the hand-authored nav copy in `templates/chat.html`, which had drifted to the
   old name); the slug, module name, artifact keys and ledger ids did not.

   8b. **Story-id ↔ basket-id crosswalk closed additively.** Only 7 of the 18 story
   ids are spelled like their basket, so `build_portfolio_ctx._themes_block`'s
   same-id join into `theme_lanes.json` silently read null for the other 11
   (power_grid, obesity_glp1, payments_fintech, defense, space_economy,
   critical_minerals, uranium_miners, ai_infra, ai_neoclouds, reshoring,
   managed_care). Story ids key ledgers and were NOT renamed. Instead
   `config/theme_crosswalk.yml` (v2) gained `primary_basket_id` — the one basket that
   IS the theme, transcribed from each row's own note, null where the note itself
   disclaims a dedicated basket. It is deliberately narrower than `basket_ids`: that
   list answers "which baskets give this theme a price surface" and includes
   supply-chain proxies, which do not survive being read backwards (managed_care is
   the medical_devices theme's closest healthcare proxy; a managed_care holder does
   not own that theme). 13 stories resolve a basket, 5 stay honestly null.
   `theme_lanes.json` now ships `basket_lanes` + `theme_baskets` beside the unchanged
   `lanes`; the consumer prefers the explicit map and falls back to the same-id
   lookup, so the join is a strict superset.

8c. **`baskets.html#theme-<id>` deep-link contract restored in the stub.** The merge
   turned `baskets.html` into a redirect stub that discarded the hash, so alerts rows
   (`engine/alert_triage.py` assembles page + `#theme-<id>` anchor), bookmarks and
   outbound links all dumped the visitor at the lanes anchor. The stub is the correct
   RECEIVER: it now runs a head-script resolver — validate the id against the nightly
   basket id list (passed as `theme_ids` by `build_baskets.py`, the same list
   `build_detail_pages` writes `basket/<id>.html` from), then `location.replace()` to
   that detail page; an unknown/stale id falls through to the merged page rather than a
   404, and the meta refresh stays as the no-JS fallback. Live in-page emitters
   (dashboard sector-heat/cool chips) were already re-pointed at `basket/<id>.html`
   during the merge — only their comments still described the retired hop.

8d. **macro-desk family membership changed** (roster recorded in
   `tests/test_macro_desk_surface.py`): `baskets` and `subsector_rotation` LEFT — both
   are stubs with their own inline style block, linking no `macro-desk.css`.
   `sector_central` STAYED but changed VARIANT to `page-baskets` (the merged page is
   descended from the baskets rvx layer). **Known gap, not yet reconciled:** the merged
   page still carries `scc-wrap` / `scc-cycle` / `cyc-stage` / `scc-section-h` /
   `scc-boardhead` markup, and `macro-desk.css` scopes ~15 rules for exactly those
   classes under `body.macro-desk.page-sector-central` — dead on the merged page since
   the merge (its China sibling keeps the class, so they stay live there). Reconciling
   is a styling call with cascade-collision risk against the rvx layer, so it is left
   for a design pass; the roster pin records the shipped truth meanwhile.

9. **ADJUDICATED KILL — the SRR "Themes-47" unit (the §4b-1 deferral) is closed
   WON'T-BUILD.** Reasons: (a) the merged page already serves 47-basket rotation in
   THE MAP (rvx instrument, sectors/baskets scopes) — a second 47-row rotation table
   in MOVEMENT recreates the same-universe duplication this program cured; (b)
   MOVEMENT's IA promise is "the whole market" (§4b-1), deliberately excluding
   curated universes; (c) the `themes` array in `subsector_rotation.json` is
   contract-bound to `engine/neuralweb/thematic_state.py` (keys by finviz `theme`
   name) and cannot be repurposed — an additive dark unit would ship an unreviewed
   dark lane serving no surface. If a future program wants SRR as the SOLE rotation
   instrument (11/47/269 in one), that is a design program with its own adjudication,
   not a follow-up chore.

## §5 Vocabulary bridge (Tier-2 `?` receipt, one place)

"**Leading/Improving/Weakening/Lagging** describe where a group sits vs the market
*right now* (strength × direction). **Bottoming/Prime entry/Trending/Topping/Rolling
over** describe where it sits in its own multi-year cycle. **Lanes** (Buy now / Wait
for a pullback / Take profits / Reduce–avoid) are the only rows that carry a gated,
graded call — everything else on this page is context, measured nightly."

## §6 Pinned design spec — VERDICT + DO THIS NOW (main-loop design, builders implement)

Census facts this leans on: `BASKETS.story` (leader/handoff/state chips) already
exists in the baskets payload; `SECTOR_CENTRAL.market` carries ~28 regime fields of
which the current page renders ONE sentence; conviction cards already compute
score+tier+phase+trace; the "(Equal-Weight)" disambiguating suffix is currently
STRIPPED at boot (both FIX 1a/1b blocks) — that de-labeling dies.

Render-mode law for the whole merge: **transplant, don't rewrite.** The baskets
hero/lanes/map are client-rendered by the `rvx-*` layer from the `BASKETS` payload —
they stay client-rendered from the externalized payload, mounted in the new shell
with the copy/IA changes below. Same for the rotation-app (`SR_CFG` mount) and the
cycle embed (`SECTOR_CYCLES`). New code is glue, wayfinding, and copy — not engine
rewrites.

### 6.1 VERDICT hero (`.si-hero`, rvx hero transplanted)

Layout: two-column ≥880px (left = state, right = handoff card), stacked below.

- Kicker: `US SECTOR INTELLIGENCE 🇺🇸` (ZH 美国行业智慧). H1 = the state headline,
  dynamic from the rotation state, e.g. **"Money is rotating"** / "Leadership is
  narrow" / "A quiet tape" — the existing baskets hero-state vocabulary, verbatim
  reuse of its state → headline map.
- One plain sentence under it (≤14 words wins the glance): "Money is moving into
  Software and out of Semiconductors. Favour the fresh leaders."
- Right card `THIS WEEK'S HANDOFF`: losing → taking the lead (name + 20d line each),
  arrow between; whole card links to the two names' detail pages.
- Chip row (max 5, one line): rotation-state chip (▸ stance phrasing, e.g. "Rotation
  under way — favour the fresh leaders, not the old one"), days-in-state,
  seasonality chip, policy-risk chip, sizing chip. Every chip carries its existing
  `data-tip-en/zh` receipt. Regime enrichment: the seasonality/policy chips may draw
  from `SECTOR_CENTRAL.market` fields already computed (quad_name, liquidity) —
  display-tier phrasing only, no new scores.
- One as-of stamp, top right of hero. The old sector_central methodology paragraph
  moves to the footer `?` receipt; the "New here?" clock explainer moves to a `?`
  next to the Map lens toggle (Tier 2), not a hero strip.

### 6.2 DO THIS NOW (`.si-actnow`, server-rendered rows + JS expand)

- Four lanes in fixed order, each a titled group with count + one-line meaning:
  🟢 **Buy now** — "In favour and a clean entry is set up right now."
  🔵 **Wait for a pullback** — "In favour, but stretched — no clean entry yet."
  🟠 **Take profits** — "Was leading — momentum now rolling over."
  ⚪ **Reduce / avoid** — "Weak and getting weaker — stand aside." (collapsed past 5,
  "+ N more ▾")
- Row anatomy (one line, grid-aligned): name · kind chip (`SECTOR` / `SECTOR EW` /
  `THEME` — the de-label bug fix) · 20d-vs-S&P mono figure · reason phrase
  ("accelerating · 2 report soon" / "entry quality 85%") · disclosure caret.
- Row expand (click; `.si-trace`) = the conviction board's gated read, relocated:
  conviction tier + score, cycle phase chip, the reasoning-trace line (cycle leads →
  gate → confirm), mini cycle sparkline, grade history when present, links
  "open cycle →" (`sector_cycles.html#<id>`) and "members →" (`basket/<id>.html`).
  One row open at a time; deep-linkable via `#read-<id>`.
- Lane footer (once, not per-row): "Lanes are the only gated, graded calls on this
  page" + self-grader chip ("N calls logged · grades mature at 5/10/21/63d —
  measured, not asserted") + "Drill to stocks → Subsector Confluence".
- Universe: sectors (11, cap-weighted ETF read) + themes (36) + sector-EW proxies
  (11) — the current conviction universe, unchanged. No subsectors here, ever.

### 6.2b Disposition table (every current section, accounted)

| Today | Where | Disposition |
|---|---|---|
| baskets hero (verdict + handoff + chips) | baskets | **→ VERDICT hero** (transplant, retitled) |
| baskets tape strip/band + shock banner | baskets | → top of merged page, one instance |
| baskets alerts bell + THEME_ALERTS | baskets | → merged nav row; alerts JSON externalized; deep-link fixed |
| baskets "Do this now" lanes | baskets | **→ DO THIS NOW** + conviction-trace expands |
| sector_central "Conviction board" cards | sector_central | → absorbed into lane-row expands (trace, tier, sparkline, grade) |
| sector_central self-grader | sector_central | → lane footer chip + EXPLORE track-record module |
| baskets "The rotation map" (rvx SVG, 47) | baskets | → **killed as a separate instrument**; its RS×velocity data feeds the SRR Themes-47 unit |
| subsector_rotation "Rotation map" (SRR) | subsector_rotation | **→ THE MAP rotation card** (scopes 11/47/269; Finviz-41-themes unit dies) |
| sector_central "Cycle map" embed | sector_central | **→ THE MAP cycle card** (unchanged engine, shared scope control) |
| sector_central "New here?" strip + methodology hero prose | sector_central | → `?` receipts (map heading / footer) |
| subsector_rotation "Turns this week" | subsector_rotation | **→ MOVEMENT** (unchanged) |
| subsector_rotation "Rotating in/out" | subsector_rotation | → MOVEMENT (unchanged) |
| subsector_rotation "Rotation Events" + fragmented sectors | subsector_rotation | → MOVEMENT (unchanged mechanics, compressed caveats) |
| subsector_rotation "Turn Desk" + "Earliest flow signs" | subsector_rotation | → MOVEMENT "Desk watch" compact module (quiet-state honest) |
| subsector_rotation "Momentum & flow board" | subsector_rotation | **KILLED** (dead in production; redundant) |
| subsector_rotation "Time Machine" | subsector_rotation | → EXPLORE, collapsed + lazy |
| subsector_rotation track record | subsector_rotation | → EXPLORE track-record module (beside conviction grader; separate readouts, never merged stats) |
| subsector_rotation full ranked table | subsector_rotation | → EXPLORE table, Subsectors scope |
| baskets "Performance table" + category chips | baskets | → EXPLORE table, Themes scope |
| baskets "Performance" chart | baskets | → EXPLORE chart (unchanged) |
| baskets "Under the hood" breadth+money flow | baskets | **→ MONEY & BREADTH** (unchanged) |
| sector_central "Sector flow" SPDR table | sector_central | → MONEY & BREADTH (unchanged) |
| sector_central "Market heat" scorecard + expand | sector_central | → MONEY & BREADTH (unchanged) |
| sector_central "Index leadership rotation" (LAS) | sector_central | → MONEY & BREADTH compact card |
| baskets dead V1 desk fork | baskets | **DELETED** |
| baskets hidden member-symbol registry | baskets | → merged page (live-quote scraper contract preserved) |
| both pages' stacked disclaimers | all | → one merged footer + `?` receipts |

### 6.3 Visual system

No new palette or type: the page keeps `macro-desk.css` + `theme.css` tokens (this
is a consolidation, not a rebrand — restraint IS the risk here). The one signature
element: the **handoff card** in the hero (losing → taking, with the accent arrow) —
everything else stays quiet. Section h2s follow the existing house pattern
("Do this now — the shortlist, by action"). Mono numerals for figures only, never
words. Dark/light parity via existing tokens; zh copy written at parity, not
translated literally. Reduced-motion: no new animations beyond existing ilx
draw-on-reveal.
