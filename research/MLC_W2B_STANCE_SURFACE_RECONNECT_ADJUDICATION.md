# MLC-W2b stance-surface adjudication — feed KEPT, surface RECONNECTED (2026-08-01)

**Question referred:** (a) is `site/mlcdata/stance_matrix.json` still built and current?
(b) reconnect the dead conflicted-view surface to the live "Do this now" rvx lanes, or
retire the feed via DO_NOT_REBUILD?

## Ruling

**(a) The artifact is built, current, and consumed.** Nightly dag node
`build_stance_matrix` (`config/dag.yml`, fail-soft, display-only, CONST-ART2
`authority: false`); output committed by tonight's run (`engine: regime update
2026-08-02`, `as_of: 2026-08-01`, inputs 07-31/08-02). The edge serves `/mlcdata/*`
through `@reg_asset` (registration-gated, same gate as the pages that fetch it).
It has a **live consumer today**: `allocation.html(.j2)` invokes
`renderAllocStanceChips()` on boot and chips position rows whose four reads disagree.

**(b) KEEP the feed — no DO_NOT_REBUILD row. RECONNECT the surface, in the rvx idiom,
on baskets.html (the page that owns the act_now lanes).** Retirement fails on every
prong: the feed is current, cheap (aggregation-only), display-tier under the
epistemics law (de-escalation/honesty infrastructure, never a signal origin), has a
live consumer, and its engine-side sibling (`_apply_sector_conflict_demotion` /
`_apply_momentum_cooling_demotion` in `engine/theme_scoring.py`) actively shapes
`act_now` every night. No standing kill covers it (the only MLC-adjacent DNR row is
MLC-W1's forced-call class — unrelated to this de-escalation layer).

## What was actually dead (evidence, and premise corrections)

- The referred brief said the rvx lanes live on `sector_central.html.j2` — on main at
  ruling time **they live on `baskets.html.j2`** (`#actnow.rvx-lanes`, filled by
  `renderActBoard()`); `sector_central` is an *input* to the stance matrix. (The brief
  spoke from the in-flight consolidation's vantage — see Consolidation interplay below.)
- The referred test name `test_merged_page_keeps_live_mlc_split_view` **does not exist
  on main**; it reads as the consolidation masterplan's pin-to-write for the merged
  page. The documentation on main is `tests/test_theme_scoring_conflicted.py` (engine
  demotion tests + template smoke tests, re-pinned by this PR).
- Nothing landed on main had deleted the fork. The kill was **PR #3282 (baskets rvx
  revamp)**:
  it replaced `renderActNow`/`renderThemeDesk` with `renderActBoard`/rotation map and
  dropped the call sites. What remained on main until this PR: `renderStanceChips`
  defined-never-called (US inline copy), `#actnow-footnote` referenced-but-nonexistent,
  and `renderActNow` defined-never-called. The `baskets_desk.js` copy is a *non-US*
  boot (`deskBoot`) where `renderStanceChips` early-returns by design (US-only artifact)
  — alive, correctly inert, untouched.
- The engine-side conflicted mechanism **never stopped**: demoted items were folded
  into the live board's WAIT lane (with their engine reason as the row subline), but
  under the lane's generic "stretched — no clean entry" narrative and with the
  stance-matrix chips entirely dark. Tonight's `conflicted` is `[]`, so no user-visible
  mislabeling exists at ruling time; the first demotion night would have shipped one.
- Old smoke tests asserted bare substrings ("actnow-footnote", "renderStanceChips")
  which the dead definitions satisfied — vacuous pins; replaced.

## Shipped in this PR (templates/baskets.html.j2 + tests)

1. `renderActBoard` tags folded conflicted items (`_conflicted`) → `actRow` renders a
   warn `conflicted / 观点冲突` chip; the row subline already carries the engine's
   bilingual reason (Tier-2 receipt inline).
2. `#actnow-footnote` element restored under the lanes; shows the V1-approved sentence
   ("Conflicted = in favour on its own read, but its sector view says Reduce." /
   「观点冲突 = 自身信号看好，但所属板块评级为减配。」) only when a sector-demoted item
   is present (active-only; cooling-demoted rows self-explain inline).
3. `renderStanceChips` rebuilt for the live markup: fetches `mlcdata/stance_matrix.json`
   once (cached across langchange re-renders), chips act-board rows (`data-mlc-bid`)
   whose matrix `agreement` is mixed/split with the shipped vocabulary
   (`mixed reads/观点分歧`, `split view/严重分歧`) and `tip_en/tip_zh` hover receipts;
   invoked from `renderActBoard`. Conflicted-tagged rows keep their engine marker
   (one chip per row). `data-mlc-bid` (not `data-bid`) respects the FTR-W3 guard.
4. Dead fork deleted: `renderActNow`, old `renderStanceChips`, `actNowPulseBar`
   (`renderRegimeSizing` stays live via the hero path). Tests re-pinned to the live
   contract: footnote *element*, chips *invocation*, fork *absence* + `_conflicted` tag.

## Consolidation interplay (in-flight at ruling time)

The Sector Intelligence consolidation (operator-chartered 2026-08-01; masterplan
`research/SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md` on the program's
in-flight branch, **not yet on main**) merges baskets.html INTO sector_central.html
(URL kept). This ruling therefore changes one of that program's dispositions: the MLC
client surface is no longer part of the deletable dead fork — it is a **live surface
the merged page must carry**: `renderActBoard`'s conflicted fold+tag, the `actRow`
`mlcchip`, the `#actnow-footnote` element, and the cache-based `renderStanceChips`
(`data-mlc-bid`), pinned on the merged page by the masterplan's
`test_merged_page_keeps_live_mlc_split_view`. The consolidation session has been
notified; whichever branch rebases second takes this PR's `renderActBoard` shape
verbatim.

## Follow-ups (not this PR)

- Remaining dark V1 desk code on the US page (`renderThemeDesk`, FTR chip strips
  targeting `.tcard`s that no longer render, orphan `anrow/anwrap/pulse-bar` CSS) —
  spun off to its own verify-then-sweep task.
- `us_stocks.html#action-board` (the "+N more" overflow target): verify how it
  presents conflicted items; extend the marker there if it flattens them.
- Stance chips on `sector_central` rows would be a *new* design decision (the matrix
  reads sector_central as an input); anyone proposing it starts from this ruling, not
  from the dead V1 code.
