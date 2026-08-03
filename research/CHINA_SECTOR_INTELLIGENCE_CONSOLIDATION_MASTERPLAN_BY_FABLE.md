# China Sector Intelligence — consolidation masterplan (by Fable)

Status: ACTIVE build program, 2026-08-02. Port of the US Sector Intelligence
consolidation (`research/SECTOR_INTELLIGENCE_CONSOLIDATION_MASTERPLAN_BY_FABLE.md`,
PR #4237, merged 33da894ce7dd) to the China mirrors, under the same operator charter
("consolidate, merge, group, create, remove, upgrade any features" — 2026-08-01).

Scope: `sector_central_china.html` + `baskets_china.html` +
`subsector_rotation_china.html` → ONE **China Sector Intelligence / 中国行业智慧**
page at `sector_central_china.html` (URL kept). The THS universe browser
(`baskets_china_ths.html`, 3.5MB) is OUT OF SCOPE — stays live, linked from Explore.
US surfaces untouched. HK/Canada/Intl mirrors are a later program.

---

## §0 ACCEPTANCE GATES (not done unless)

1. **One page.** `sector_central_china.html` is the single China sector/theme/rotation
   hub, titled **China Sector Intelligence 🇨🇳 / 中国行业智慧**. `baskets_china.html`
   and `subsector_rotation_china.html` render as redirect stubs (US stub pattern
   verbatim: noindex,follow + meta refresh 0 + canonical-to-target via `seo_path` +
   one-line pointer + `location.replace` with anchor deep-link).
2. **Five-second test.** Cold reader sees without scrolling: the rotation state in
   plain words (theme-context hero: "Money is rotating / 资金正在轮动" family —
   already computed, `baskets_china.html.j2:263-269`), the gated conviction
   shortlist, and where to go next. The `scc-rail` link-farm row
   (`sector_central_china.html.j2:196-201`) dies — a hub that is a row of four
   outbound links fails the five-second test by definition.
3. **One vocabulary, EN/ZH parity.** Same lexicon as US (§5 of the US masterplan).
   NEW, China-specific: one ZH term for "subsector" — the nav says 子行业
   (子行业轮动/子行业汇聚) while the hub page says 细分行业
   (`sector_central_china.html.j2:198-199`). Align every touched surface to the
   nav's 子行业; no second synonym set survives on the merged page.
4. **Epistemic line intact.** China's gated layer = the `#sc-board` conviction board
   + `#grader` (engine `china_sector_central` — the ORIGINAL gated engine; the US is
   its port, `engine/sector_central.py:5`). Rotation/velocity instruments stay
   display-only with caveats compressed to `?` receipts. NO new scores, no
   rotation×cycle gate (DO_NOT_REBUILD), and NO inventing organs China lacks data
   for (§3). LLM never originates signals (A7).
5. **Page weight.** The 774KB inline `BASKETS`+`CHART` blobs
   (`baskets_china.html.j2:494-495`) are EXTERNALIZED — the page fetches
   `chinabasketdata/baskets.json` (already written every run by
   `build_baskets_china.py`). Mind the **#2886 double-render contract**
   (`build_baskets_china.py:381-392`): the second render exists so the INLINE
   payload picks up post-organ `turn_state` (lifecycle chips / Entry Radar), and the
   first render exists so an organ failure still ships a page. Externalization
   replaces both: render the shell ONCE (no payload), and write the JSON with the
   same fail-safety the double render gave the page — a pre-organ fail-soft write
   plus the post-organ authoritative write (or one write in a `finally`-guaranteed
   path carrying whatever state exists). A stale pre-organ-only JSON is the
   us_stocks one-build-lag class (#2829) — regression-test the turn_state presence.
6. **Nav 5→3.** China "Sector Central" flyout (5 entries,
   `_navlinks.html.j2:110-116`) collapses to flat rows: **China Sector Intelligence
   (中国行业智慧)** · **Subsector Confluence (子行业汇聚)** · **Market Heatmap
   (市场热力图)** (kept — unlike the US, china_heatmap has no other nav home).
   `_navlinks.html.j2` only; China/HK/Canada other menus untouched; no third header
   family. (As built: the in-menu row label is the short **Sector Intelligence /
   行业智慧** — the row already sits inside the China menu, so the "China" prefix is
   redundant there; the page's own kicker/title carry the full China Sector
   Intelligence / 中国行业智慧.)
7. **Nothing silently lost.** PR body carries the full disposition table (§6).
   Detail families stay live: `site/basket_china/` (22), `site/rotation_china/`
   (233), Confluence's `site/subsector_china/` (untouched).
   `scripts/build_theme_detail.py` gains a china arm in the region back-link
   conditional (~line 273-277): back → `../sector_central_china.html#actnow-section`,
   label "China Sector Intelligence / 中国行业智慧".
   `scripts/build_subsector_rotation_china_pages.py` back_href re-points to
   `sector_central_china.html#si-movement`. Inbound links updated in the SAME PR:
   census found `baskets_china.html` referenced from 8 template files
   (allocation.html.j2:619, china_intel.html.j2:814, china.html.j2:1538,
   cn_reversal_sleeve.html.j2, chat.html:116, nav_market.js:244, _navlinks,
   sector_central_china itself) and `subsector_rotation_china.html` from 8
   (incl. sector_cycles_china.html.j2, chat.html) — every non-stub referrer
   re-targets to the merged anchors. Grep scripts/ + engine/ for URL-string
   deep-links to both absorbed pages (census covered templates only).
8. **Cross-lane integrity.** The China chain builds in `asia-close.yml`
   (brun steps: baskets_cn, baskets_ths, subsector_rot, subsector_rot_pages,
   sector_central — lines ~403-522); step semantics unchanged.
   `build_site.py`'s asof idempotency guard (~5593: asia lane already ran → US
   nightly only re-renders the HTML shell from committed JSON) must keep working
   for the merged page — the shell render must not require asia-lane-only inputs.
   `render.yml` path lists gain any new/renamed files. `subsector_rotation.js` is
   shared with the US — any change stays SR_CFG/data-driven backward-compatible
   (China mount: `subsector_rotation_china.html.j2:188` today, moves into the
   merged page).
9. **Proof.** Local render + browser verification light/dark/EN/ZH with per-section
   crops in the PR body (tall-viewport/card-harness for below-fold sections —
   known pane quirk); `python -m scripts.check_template_site_sync --fix` clean;
   validated-claims + nav-gap + public-chrome checks green; full relevant packs
   green; commit → push → PR → `merge-on-green` per ship loop. Reference = the
   SHIPPED US page (`templates/sector_central.html.j2` on main) — committed code
   satisfies the reference law; no prose-only look handoffs.

---

## §1 Census facts (Sonnet census 2026-08-02, main-loop spot-verified)

| Surface | Size | Shape |
|---|---|---|
| `sector_central_china.html.j2` (685 lines → 83KB rendered) | hero + `#regime` + `scc-rail` link farm + `sc-tabs` Shenwan⇄Baskets toggle (drives cycle map AND board via `linkTabs()`) + `#sc-cyclemap` (full US-parity embed: sector_cycles.js + mm_charts.js + 4 data JS files) + optional `#sc-desk-table` + `#sc-board` conviction board + `#grader` | data: `sector_central_china_data.js` (157KB, external — already the right pattern) via `build_china_sector_central.py` (103 lines) |
| `baskets_china.html.j2` (72KB → **905KB** rendered) | theme-context hero (state line + stance + days chip + strength/watch chips) → `#entry-radar` (378) → `_forming_narratives` include (382) → `#table-section` (393) → `#chart-section` (404) → `#categories` (419) → `#reversal-sleeve-card` (432) | **774KB INLINE payload** (`BASKETS`+`CHART`, lines 494-495); `build_baskets_china.py` (547 lines, #2886 double render); also writes `chinabasketdata/baskets.json` + `narrative_emergence.json` + `member_signals.json`, `factordata/cn_reversal_sleeve.json`; copies baskets_desk.js, forming_narratives.js, lightweight-charts.js |
| `subsector_rotation_china.html.j2` (214 lines → 61KB) | h1 → `#rotation-app` (shared `subsector_rotation.js` via SR_CFG json `marketdata/subsector_rotation_china.json`, detailDir `rotation_china/`) → `#rc-events-cn` China Rotation Events rail (self-contained style+script, RC-R14) | data: 233 THS subsectors + 22 curated themes; NO sectors/turn/track_record keys; `themes_unit` never emitted (JS guard no-op for China — verified); shell rendered contextless by `build_site.py:5602-5616` |

NOT consolidated (linked, not absorbed): `china_sector_desk.html` (live Shenwan
board + Pathway Desk — SOURCE of the Wilson-CI odds the conviction engine consumes;
keep standalone), `narrative_radar.html` (independent THS radar),
`subsectors_china.html` (Confluence funnel — stays per US precedent),
`sector_cycles_china.html` (embed source), `china_heatmap.html`,
`baskets_china_ths.html` (THS browser, 3.5MB, largest generated page).

Key asymmetries vs US:
- **No rvx action lanes** — baskets_china is the pre-rvx FactorWatch shape. China's
  action surface = the conviction board. Do not invent lanes.
- **No turn ledger / track record / sector-ETF cross-section** in the China rotation
  feed (US-only organs in `build_subsector_rotation.py:280-338`).
- **No si_handoff.json** — the theme-context hero is rendered server-side from
  `engine.theme_context.compute_theme_context(region="china")` inside
  build_baskets_china; the merged page keeps server-side hero rendering (no new
  artifact).
- **Cycle embed already US-parity**; conviction engine is the original.
- ZH synonym split 子行业 vs 细分行业 (gate 3).

## §2 Target IA (US funnel, adapted to what China HAS)

Order on the merged `sector_central_china.html`:

1. `#regime` band (existing).
2. **VERDICT hero** — theme-context hero transplanted from baskets_china
   (state line / stance / days-in-state / strength+watch chips with
   basket_china links); kicker `CHINA SECTOR INTELLIGENCE 🇨🇳 / 中国行业智慧`;
   one as-of stamp. Old sector_central_china hero prose → `?` receipts.
3. **Section rail** (`#si-rail`, US idiom): Do this now / The map / What's moving /
   Explore / Stock entry funnel → `subsectors_china.html` (external, labeled).
4. **DO THIS NOW** (`#actnow-section`) — the `#sc-board` conviction board + `#grader`
   PROMOTED here (China's only gated layer; the board IS the call surface; exact
   gated semantics + self-grader chip preserved; sectors⇄baskets follows the
   universe toggle as today via linkTabs).
5. **THE MAP** (`#si-map`) — `sc-tabs` universe toggle + `#sc-cyclemap` embed +
   optional `#sc-desk-table` (unchanged engines).
6. **WHAT'S MOVING** (`#si-movement`) — `#rc-events-cn` rail + `#rotation-app`
   (233 THS / 22 themes, unchanged mechanics; caveat walls → `?` receipts).
7. **EXPLORE** (`#si-explore`) — `#entry-radar`, `_forming_narratives` include
   (ne_base `chinabasketdata/`), `#table-section`, `#chart-section`, `#categories`,
   `#reversal-sleeve-card` (heavy pieces collapsed/lazy per US idiom), and a links
   row: THS universe browser (`baskets_china_ths.html`) · Live Sector Board
   (`china_sector_desk.html`) · Narrative Basket Radar (`narrative_radar.html`) ·
   Market Heatmap (`china_heatmap.html`).
8. Footer `?` receipts (methodology, vocabulary bridge — reuse US §5 bridge,
   translated).

Reuse the US section ids (`#si-rail`/`#actnow-section`/`#si-map`/`#si-movement`)
where the structure matches so tests and idioms stay greppable. Transplant, don't
rewrite (US render-mode law): existing renderers keep their mount ids; new code is
glue, wayfinding, and copy.

## §3 Explicitly NOT built (data honesty — consolidations transplant, never birth engines)

- No desk_watch / time_machine / turns-this-week / rotating-in-out modules (no
  China turn ledger, no track record, no sector-ETF cross-section). If wanted:
  separate program with its own adjudication.
- No China si_handoff.json (server-side hero needs none).
- No THS⇄curated taxonomy merge; the THS browser page stays as-is.
- No new scores; no rotation×cycle confluence (DO_NOT_REBUILD).
- No SRR themes-widening (US §4b addendum kill applies in spirit: the merged page
  already serves the curated-basket view via the toggle; the rotation app's themes
  unit (22) already exists for China and STAYS — it predates this program).

## §4 Build waves (Opus builders, bounded; Fable pins design + reviews + merges)

- **W1 plumbing** (builder): externalize the China payload — `build_baskets_china.py`
  single render + fail-safe JSON write ordering (gate 5), page boot fetch
  (`__siFetch` idiom from the US page), stub templates for the two absorbed pages,
  nav 5→3, `build_theme_detail.py` china arm, `build_subsector_rotation_china_pages.py`
  back_href, `build_site.py` stub/merged render wiring, inbound-link retargets (§0.7).
- **W2 template merge** (main loop assembles mechanically with marker asserts if the
  builder stalls — US Wave-A lesson): transplant organs into
  `sector_central_china.html.j2` per §2; ZH synonym sweep (gate 3).
  **W2 TRAP — THS template survival (caught 2026-08-02, absent from the census
  dispositions):** `baskets_china.html.j2` is rendered by TWO builders — 
  `build_baskets_china.py` (the curated page this program stubs) AND
  `build_baskets_china_ths.py` (`lite=True`, the out-of-scope 3.5MB THS browser).
  Stubbing the template in place would silently destroy the THS page. Order of
  operations: (1) extract the full FactorWatch template byte-identically to
  `baskets_china_factorwatch.html.j2`; (2) re-point `build_baskets_china_ths.py`
  at it; (3) only then replace `baskets_china.html.j2` with the redirect stub.
  Tests pin: THS page still renders from the extracted template with `lite=True`;
  the stub template contains no `BASKETS`/`CHART` references; the extracted
  template is reachable from exactly one builder (no dual-render ambiguity left).
- **W3 tests** (builder): port the `test_sector_intelligence_page.py` pattern to a
  China sibling (stub assertions, section skeleton, payload-externalized, nav
  collapsed, US-untouched inverse guards); retarget moved-markup pins; #2886
  regression pin (turn_state present in the fetched JSON after a full build).
- **W4 verification + ship** (main loop): local render, browser proofs
  light/dark/EN/ZH, ship loop to merge-on-green, live verification.

## §5 Vocabulary bridge

US §5 bridge reused verbatim, ZH-translated, ONE place (footer `?` receipt), with
the China addition: 子行业 is the site's word for subsector (细分行业 retired from
these surfaces).

## §6 Disposition table (target state; PR body carries the as-built version)

| Today | Disposition |
|---|---|
| sector_central_china hero prose | → `?` receipts; theme-context hero replaces it |
| `scc-rail` 4-link farm | **killed** (rail + in-page sections replace it) |
| `sc-tabs` + `#sc-cyclemap` + `#sc-desk-table` | → THE MAP (unchanged engines) |
| `#sc-board` + `#grader` | → DO THIS NOW (promoted, unchanged semantics) |
| baskets_china theme-context hero | → VERDICT hero (transplant, retitled) |
| baskets_china `#entry-radar`, table, chart, categories, reversal sleeve | → EXPLORE (heavy pieces lazy) |
| baskets_china `_forming_narratives` include | → EXPLORE (same include, ne_base kept) |
| baskets_china inline BASKETS+CHART (774KB) | **externalized** → fetch `chinabasketdata/baskets.json` |
| subsector_rotation_china `#rotation-app` | → WHAT'S MOVING (unchanged SR_CFG mount, pageHref → merged page) |
| `#rc-events-cn` rail | → WHAT'S MOVING (unchanged) |
| baskets_china.html / subsector_rotation_china.html | → redirect stubs (`#actnow-section` / `#si-movement`) |
| nav flyout 5 entries | → 3 flat rows (gate 6) |
