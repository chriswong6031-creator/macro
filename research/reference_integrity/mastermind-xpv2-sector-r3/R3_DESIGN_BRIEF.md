# XPV2-SC-R3A — R3 Design Brief (Deliverable 6)

This is a BOUNDED BRIEF — it constrains what R3 may build, it does not draw
anything. It exists because four critics BLOCKED the R2 Sector Central
mockup for inventing/mixing authority and losing capabilities; every
constraint below closes one of those failure modes with a specific
production citation, not a general design preference.

Frozen sources: `ADJUDICATIONS.md`, `capability_disposition_ledger.md`,
`producer_binding_matrix.md`, `routing_contract.md`,
`access_hydration_contract.md`, `fixture/`.

## 1. Page answer job

Sector Central answers one question per view, never more than one:

| View | The one question it answers |
|---|---|
| Overview | "What should I do right now?" — the only view carrying a graded action call (the Act-Now board) plus the Bottoming Watch strip and the self-grader |
| Map | "Where does each group sit right now, and is anything context-worth-watching?" — explicitly NOT a call view (`sector_central.html.j2:2267`: "Only the lanes above carry a gated, graded call") |
| Moving | "What changed recently?" — rotation/flow context, explicitly "ranks nothing, gates nothing, sizes nothing" |
| Money | "Where is money actually flowing, and how broad is the market?" — breadth/flow context |
| Explore | "Let me look under the hood" — self-serve table/chart/history/emergence, no new call |
| Confluence | "Give me a timed subsector/basket call, sortable and filterable, across four universes" — the ONE other view besides Overview that carries Action-authority per Deliverable 2 |

A candidate that lets a context view (Map, Moving, Money, Explore) answer
"what do I do" in its own visual weight — bigger type, brighter color, a
button — has repeated the R2 defect class regardless of whether the
underlying data changed.

## 2. Context/action dual-read law (binding, per ADJUDICATIONS §A3)

- **Bottoming Watch stays watch-only.** Its payload fields `signal` and
  `timing_state` are DELIBERATELY never rendered by production (`_us_bottoming_watch.html.j2:23-28`,
  "COPY LAW: Watch vocabulary only, never a buy verb"). R3 may not surface
  those fields, may not retitle the strip as an "early entry" or "upgrade
  pipeline" concept (this is exactly DAC-003's finding against the R2
  candidate), and must keep the strip visually and semantically separate
  from the five action lanes — a full-width strip UNDER them, never a sixth
  lane.
- **Map's `reco` tags are a recorded CONFLICT, not a template to extend.**
  Production itself renders `theme_intel.themes[].reco` as Buy/Add/Hold/Trim/Avoid
  tags on the Map's linked board, beneath a context-only disclaimer — the
  SAME defect class the critics blocked in R2 (DAC-001/002), shipping in
  production today. Ruling: R3 preserves this AS-IS (it is a RETAIN
  capability, `capability_disposition_ledger.md` #38) but must NOT amplify
  it — no larger type, no color-coding beyond what production already does,
  no relocating it out from under its own disclaimer, no treating it as
  equivalent in authority to the Overview action lanes. Production's repair
  of this defect is filed separately and is out of scope here.
- **The hero/leadership context (Overview) and the action-board lane
  assignment are structurally independent** — no code path connects them
  (`capability_disposition_ledger.md` #26). R3 must not visually imply a
  connection (e.g. drawing an arrow from the hero's "Health Care is leading"
  sentence into the Buy-now lane) that production's own code does not have.
- Every Context-authority field in `producer_binding_matrix.md` must render
  with LESS visual weight than every Action-authority field on the same
  view. A CONFLICT-labeled field (Map's reco tags) may not visually outrank
  an Action field either.

## 3. View-by-view capability law

Every capability marked **RETAIN** in `capability_disposition_ledger.md`
(90 of 92 rows) is a journey R3 must preserve end-to-end: the reader must be
able to reach the same information, take the same click, and see the same
null/error/empty state as production does today. This includes:

- All six views' hash-routable journeys and all 21 `LEGACY_ANCHORS` (deep
  links must keep working — `routing_contract.md`).
- The `#read-*` Act-Now trace-open mechanism.
- Premium preview/hydrate exactly as specced in `access_hydration_contract.md`
  (full counts always free; row bodies gated; one silent collapse state for
  401/403/5xx/offline; no separate "access denied" banner invented).
- Thin-but-listed wording wherever the producer emits the fields for it
  (S&P, Nasdaq, Russell) — and its ABSENCE on the Baskets tab must render as
  absence, not as a fabricated zero-state message (ledger #66, BLOCKED_DATA).
- The Bottoming Watch display-tier contract (§2 above).
- Track Record / self-grader, nightly-sole-advancer, "log never read back
  into a live score."
- Time Machine's full journey, including that it fetches nothing until
  first `<details>` open.
- Forming Narratives, with the A8 labeling requirement (§4 below).

The two **BLOCKED_DATA** capabilities (Baskets-tab thin/gateable disclosure;
correction/revision representation) must NOT be invented. R3 may not draw a
"data is thin" note on the Baskets confluence tab (no producer field backs
it) and may not draw a "this value was corrected" affordance anywhere on the
page (no producer contract exists for it anywhere in the codebase, per lane
F's exhaustive grep). If R3 believes either is now needed, that is a new
producer requirement to route back through `ADJUDICATIONS.md`, not something
to sketch around in the frontend.

## 4. Forming Narratives labeling (A8)

The narrative rank/score is 100% deterministic (fixed-weight formula, no
LLM). The single LLM-originated field, `ai_watch`, must be labeled **"model
analysis"** wherever R3 renders it — this is the binding matrix's exact
authority string (`producer_binding_matrix.md`, Explore section). The
deterministic rank/score must NOT carry that label; conflating the two
mislabels the majority of the panel as LLM output when it is not. R3 should
make the LLM provenance visually explicit (an icon + label, an inline tag) —
production's current "🧭 AI scout watch" line is a good-faith attempt at this
but does not use an explicit "model analysis"/AI-generated string; R3
closing that gap is encouraged, not required, since it is a labeling
addition to a RETAIN capability, not a repair of one.

## 5. Mobile reduction per view

- **Overview**: fold/show-more threshold (3 rows) must survive; the
  gated-shell hydrate flow's `restoreFold()` DOM-side fold rebuild must
  survive on mobile too (it already guards `n<=3`).
- **Map/Moving/Money**: these lazy-mounted panels (`#sc-chart`,
  `#rotation-app`, `#heatmap-scorecard`, etc.) have NO documented
  mobile-specific behavior in the archaeology beyond shared CSS
  ellipsis/overflow rules — R3 owns the mobile layout decision for these,
  bounded only by "the underlying fetched data and its null/error states
  must not change" (Deliverable 2).
- **Explore**: the table's default top-8/bottom-8 + "Show all" behavior and
  the chart's deferred-mount-on-`display:none` fix (`:2731-2740`) are both
  RETAIN capabilities that must survive a mobile reflow.
- **Confluence**: the four-universe tab strip, its hard-coded DOM order
  (S&P → Nasdaq → Russell → Baskets, per A4), and the per-surface caps
  (buy column 4, avoid column 8, picks 12) must survive.
- **Known mobile gap, recorded not repaired (A7 seam b)**: the ≤767px
  sticky top bar has no `scroll-margin-top` compensation on legacy anchor
  targets. R3 may repair this as a genuine UX improvement (it is a CSS-only
  fix, not a data/authority change) — but doing so is optional, not a gate
  requirement, since ADJUDICATIONS files it as "not repaired this wave."

## 6. Accessible equivalents REQUIRED (new requirement, not optional)

Lane C's census found two chart-only surfaces with **no accessible
text/table equivalent anywhere on the page**:

1. **The sector-cycle clock chart** (`#sc-chart`, Map view) — no off-chart
   per-sector cycle-state text list was found (`producer_binding_matrix.md`
   Map row 3).
2. **The market-heat treemap** (`#heatmap-scorecard`, Money view) — no
   separate text/table alternative was found within Money-view scope
   (`producer_binding_matrix.md` Money row 5).

**R3 MUST ship a table/text alternative for both**, in the same spirit as
production's own pattern for the rotation map (`#rvx-board` is a full
ranked-list alternative to `#rvx-rmap`) and the whole-market rotation map
(`drawStrip()`'s emerging/fading chip lists alongside the chart). This is a
genuine new UI surface, not a recomputation — it must read the SAME producer
fields the chart already reads (`window.SECTOR_CYCLES` /
`marketdata/sp500_heatmap.json`), just render them as rows instead of pixels.

## 7. The exact producer-bound fixture

R3's build and its acceptance evidence are bound to
`research/reference_integrity/mastermind-xpv2-sector-r3/fixture/` — the
frozen, byte-verified (`fixture/receipts.json`) copy of every producer
artifact this page reads, captured at commit
`4c55fe433490adfd75fd901ef25f5793db2202db` on 2026-08-20. R3 renders against
these fixture files, not against live `site/`/`data/` (which the nightly
rewrites and would make any R3 acceptance evidence non-reproducible — the
exact trap `ADJUDICATIONS.md` §A10 names). See `fixture/PROVENANCE.md` for
the full source→producer map.

## 8. Forbidden local recomputation

R3 (and any client-side code it ships) may NOT recompute, in the browser or
in a new build step, any of the following — they are server/engine
authority and re-deriving them client-side is exactly how a candidate
invents a second, driftable source of truth:

- **Rank** — theme rank, sector conviction rank, subsector/basket rank
  within any Confluence universe, Explore table default sort weighting.
- **Action lane assignment** — which of the six `_ACTNOW_LANES` keys a row
  belongs to, or which Confluence `class` bucket (`entry_now/forming/
  tailwind/neutral/late/headwind`) a group belongs to.
- **Counts** — lane header counts, `n_gateable`/`n_subsectors`/`n_thin`,
  action-board `total`. These are baked at build time off the FULL board;
  a client recompute risks silently diverging from the gated preview.
- **State classification** — regime state (BUY/SETUP/NEUTRAL/etc.), entry
  tier (T1-T4), `reliability` (thin/low-confidence flag), Bottoming Watch's
  `bottoming_authority` chip text.
- **Ordering** — the producer-fixed sort order for action-board lanes
  (theme-then-sector, `buy_soon` days-ascending), Confluence group order
  (`_CLASS_ORDER`/weight/rs60 tuple), member-row order (weight/`vs_basket`).
  Client-side RE-SORT of an already-fetched list (e.g. Explore's
  column-header sort, Confluence's full-table default-tier sort) is fine —
  that is production's own documented behavior, not a new recomputation.

Any UI element implying a number, action, or ordering not already present in
the fixture payload is a fabrication, not a design.

## 9. Required evidence matrix

R3's acceptance packet must ship, per the spawn-handoff law
(`CLAUDE.md` §Spawn-handoff law):

1. **Per-view screenshots**, light + dark + zh, for all six views
   (Overview, Map, Moving, Money, Explore, Confluence) — 18 crops minimum.
2. **Hash-routing proof**: at minimum, one canonical hash per view (6), a
   sample of legacy anchors covering at least one per view (6+), the
   `#theme-<id>` boot-time redirect, the `#read-<id>` trace-open, and the
   unknown/empty-hash fallback — landing on Overview.
3. **Access-state proof against the fixture states** (not live data):
   (a) ungated/full board, (b) gated shell at `preview_rows=3` with the
   sign-in disclosure line, (c) hydrated full board after a simulated
   successful `tier_payload.v1` fetch. All three driven from
   `fixture/premiumdata/sector_central.json` and `fixture/basketdata/action_board.json`,
   never from a live fetch.
4. **200% zoom** pass on at least the Overview and Confluence views (the two
   densest, per row-count and per-universe tab count).
5. **Accessible-equivalent proof** for the two new table/text surfaces
   required by §6 above.
6. **A written capability cross-check against `capability_disposition_ledger.md`**
   — every RETAIN row's journey demonstrated present, not merely claimed.

Falsifier/refutation language stays off every user-facing surface per the
house design doctrine — none of the above evidence items may print words
like "thesis refuted" or a raw kill-criterion sentence; the display-tier
copy (Bottoming Watch's watch-only vocabulary, Forming Narratives' rewritten
"Watching for: X" labels) is itself the compliant form and must not be
reverted to its internal (falsifier-register) wording.
