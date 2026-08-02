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
3. **THE MAP** — ONE positioning instrument, two lenses, three scopes:
   - Lens **Rotation** (RRG quadrant; engine = existing `subsector_rotation.js`
     mounted via `SR_CFG`, exactly as the China variant proves portable) — scopes:
     Sectors 11 / Themes 47 / Subsectors 269.
   - Lens **Cycle** (0–100 clock; engine = existing `sector_cycles.js` embed) —
     scopes: Sectors / Themes (subsectors have no cycle series; the scope pill
     disables with an honest note).
   - Below-map summary: phase/quadrant counts ("Where they stand") in the unified
     vocabulary; deep links to `sector_cycles.html#<id>` for full history.
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

- `build_sector_central.py` renders the consolidated template; extends its context
  with the baskets story/action payload it already sequences after (`build_baskets`
  runs earlier in the same DAG band and `sector_central` already reads
  `baskets.json`).
- `build_baskets.py`: stops inlining `var BASKETS` into HTML; emits
  `site/baskets_data.js` (stamped by optimize_assets like `sector_central_data.js`);
  renders the redirect stub at `baskets.html`.
- `build_subsector_rotation.py`: unchanged (its JSON feeds the map/movement layers);
  the page template becomes a stub; `subsector_rotation.js` mounts on
  sector_central with `SR_CFG` (China contract untouched).
- Rotation events / Turn Desk / TAPE-ONSET / Time Machine feeds unchanged.
- Self-grader continues to run inside `build_sector_central.py`.

## §4 Build plan

Opus `builder` lanes (design pinned by this doc + main-loop markup direction):
B1 page shell + hero/verdict + do-this-now (template + server-side context),
B2 map/movement mounting (SR_CFG + cycle embed + section JS glue),
B3 money/breadth/explore + stubs + nav + inbound-link sweep + weight budget,
B4 tests: stub redirects, nav-gap, template-site sync, copy-tier lint pass on new
copy, page-weight assertion. Reviewer (opus) adversarial pass before ship.

## §5 Vocabulary bridge (Tier-2 `?` receipt, one place)

"**Leading/Improving/Weakening/Lagging** describe where a group sits vs the market
*right now* (strength × direction). **Bottoming/Prime entry/Trending/Topping/Rolling
over** describe where it sits in its own multi-year cycle. **Lanes** (Buy now / Wait
for a pullback / Take profits / Reduce–avoid) are the only rows that carry a gated,
graded call — everything else on this page is context, measured nightly."
