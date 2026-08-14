# Design Migration Factory — V1 (+ ratchet + launch docket)

**Program:** Mastermind Product Design System & Experience Convergence, Wave 0.
**Companions:** `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` (the law this factory applies),
`research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` (the five frozen P0 references and PR-0..6),
`research/PRODUCT_PAGE_CENSUS_2026-08.md` + `data/product_experience/page_registry.json`
(the estate inventory the factory walks), `docs/product_experience/PAGE_EVIDENCE_HARNESS.md`
(how visual evidence is captured and cited).
**Status:** Process law once merged. No production migration rides this PR.

---

## §0 Acceptance gates (binding on every migration packet PR — "not done unless")

1. **Reference conformance:** the migrated page composes only §11 canonical components, obeys
   its archetype's L1 budget and layout, and visually matches its reference's grammar. The
   reviewer compares against the reference mockup/page, not against the old page.
2. **Both themes, both languages, both widths:** committed screenshots (dark+light × EN+ZH ×
   1440w+390w) in the PR body, captured per the evidence harness; the light shot is judged as
   a design (master doc §12), zh judged as native copy (master doc §13).
3. **Density law holds:** one primary question answered above the fold; L1 sections within
   budget; one-integer law (no two visible numbers disagree about one quantity); one as-of per
   panel; no Tier-3 receipts at rest; every demoted/removed module has a named landing.
4. **States shipped:** loading / empty(+why) / stale / error rendered and screenshotted at
   least once (forced-state harness or fixture payloads) — never a bare `—`.
5. **No horizontal page scroll at 390w**; tables scroll in-container.
6. **Engine/data behavior unchanged:** the packet's MUST-NOT-CHANGE list verified (payload
   schemas, counts, access boundaries, ledger writes untouched); display-tier only.
7. **Token cleanliness:** zero new hex/font/radius literals in the diff (ratchet lint §6
   passes); page-local tokens only as derivations.
8. **Registry updated in the same PR:** the page's row gains
   `design_system: {compliant: true, archetype, migrated_pr, evidence}` — the ratchet's
   coverage grows with the migration, or the migration didn't happen.
9. **Fresh end-to-end pass with zero manual workarounds** (spawn-handoff law): a reload-around
   race is a bug the packet owns.
10. **No self-merge on first-pass flagship surfaces:** the commissioning session reviews the
    visual artifact before the normal ship chain proceeds.
11. **Perf budget respected:** the packet's page-weight/perf line (packet §I.5 pattern) holds,
    and generated-family packets carry a render-budget line — render budget is repo law.

---

## §1 Roles — design and migration never share a hat

| Role | Who (model routing law) | Owns | May not |
|---|---|---|---|
| **Design authority** | Fable main loop / `designer` (opus) | archetype assignment, reference mockups, packet authoring, deviation rulings, final visual review | build the migration |
| **Migration builder** | Codex lanes (operator-preferred for bounded mechanical migration) or Opus `builder` | executing a packet exactly: markup/CSS rebind, module demotion per table, states, screenshots | invent design language, add components, change copy tier, touch engine paths |
| **Census / lint / verification** | Codex or sonnet `Explore` lanes | inventories, token-literal sweeps, ratchet tooling runs, evidence capture | any design judgment |
| **Red team** | independent Opus `reviewer` | adversarial pass on references and on first-of-archetype migrations | approve work it authored |

A builder that believes the packet is wrong stops and escalates to the design authority; the
packet is amended (or a dissent recorded) — the builder never improvises. This is the
spawn-handoff law applied to migration: quality travels in the packet, not by pointer.

## §2 The migration packet (template — every field mandatory)

```markdown
# MIGRATION PACKET — <route>            packet-id: MP-<seq>  date  author
1  ROUTE + TEMPLATE      site route(s); owning template(s)/builder(s) with paths
2  ARCHETYPE             letter + one line on why; registry row id
3  CANONICAL REFERENCE   the mockup/page this must match (path or route) + specimen
4  PRIMARY QUESTION      one sentence (registry `primary_user_question`)
5  PRIMITIVES TO REUSE   the §11 components this page composes (explicit list)
6  MODULE DISPOSITIONS   table: current module → RETAIN / COMPRESS / MERGE-INTO <x> /
                         DEMOTE-TO <tier/tab/page> / REMOVE (landing named) — every current
                         first-level module appears exactly once
7  MUST NOT CHANGE       engine outputs, payload schemas, canonical counts, access
                         boundaries, URLs, ledger/data writes — verified in review
8  FILES IN SCOPE        exhaustive
9  FORBIDDEN SCOPE       theme.css (unless the packet IS a DS-PR — token/primitive edits
                         happen only through DS-PRs; DS-PR-0 pre-lands the html-body var()
                         rebinds packets consume), nav partials, engine scripts, sibling
                         pages (on a multi-page template like dashboard.html.j2 the sibling
                         page is the SAME FILE — the packet names its owned region/selector
                         scope and its sequencing against any sibling packet) — plus
                         packet-specific bans
10 STATES                the four states' copy (EN+ZH) written IN the packet
11 EVIDENCE REQUIRED     the §0.2 screenshot matrix + forced-state shots + harness capture
12 ACCEPTANCE            §0 gates + packet-specific checks (each testable by a stranger)
13 COLLISIONS            open PRs/lanes on these files (gh pr list + ACTIVE_BUILD_MAP)
14 ROLLBACK              revert story (template-scoped by default)
```

Packets are committed under `research/migration_packets/MP-<seq>-<slug>.md` BEFORE the builder
is spawned; the spawn prompt inlines §0 gates and the packet path plus committed reference
image paths (never prose descriptions of a look).

## §3 The factory pipeline

1. **Assign** — design authority assigns archetype + priority in the registry overrides
   (DS-PR-1 seeds all rows; §7 docket orders the queue).
2. **Design** — for a first-of-archetype page: reference mockup (mockup gate, packet law).
   For a follower page: the archetype reference + a delta note suffice; no new mockup unless
   the page carries a novel module.
3. **Packet** — authored per §2, committed, collisions checked.
4. **Build** — one packet = one PR = one page/family (families migrate at the template level).
5. **Verify** — ratchet lint + evidence capture + reviewer pass against §0.
6. **Ratchet** — registry row flips compliant in the same PR; the lint's coverage grows.
7. **Record** — packet marked DONE with PR number; deviations/dissents appended to the packet.

## §4 Standard line items (ride every packet unless the packet says why not)

- Rebind page-local hexes/fonts/radii → tokens (the census's 4,800-hex debt retires
  page-by-page; never a big-bang). Radius/duration values snap to the §2.2 stops — a stated
  repaint line in the packet.
- As-of variants → `.dtp-asof` / `.dtp` family; one per panel.
- Empty states → `.mx-empty`+`.mx-empty-why` (5 sanctioned causes).
- Display charts → illus idiom (the 9/247 compliance gap closes through packets).
- Emoji-as-icons → `_icons.html.j2` monoline set.
- Exactly one h1; `.mx-sec` header anatomy on every panel (band labels are eyebrow-styled
  real h2s — the outline never loses a section).
- 390w no-horizontal-scroll check; mobile reduction per archetype (§15: the archetype's
  declared reduction governs).
- Banned Tier-1 vocabulary sweep (doctrine §2) on all touched copy, EN and ZH.
- Inline `<style>` byte-size governed by ratchet rule 7 (§6): warn on any growth, fail >5%.

## §5 PR sequencing — how the factory's foundations land

The packet's PR-0 (type ramp, `.ladder`, `.chg-row`, `.empty`, lock slots) is already law and
**owns the first theme.css edit**. The factory adds, in order:

| PR | Scope | Blocks |
|---|---|---|
| **DS-PR-0** (after packet PR-0, same owner discipline: small, reviewed alone) | remaining §2.2 scales (`--sp-*`, `--r-*`, `--t-*/--ease-*`, `--ser-*`, `--shadow-hover`, `--ink-tier`, `--ink-prov` alias) + new primitives under the **`.mx-*` namespace** (`.mx-vh`, `.mx-sec`, `.mx-tbl`, `.mx-callout`, `.mx-disc`, `.mx-rail`; packet PR-0's land renamed `.mx-ladder`/`.mx-chg-row`/`.mx-empty`+`.mx-empty-why`) + **the `html body` var() rebind** of the vector-polish block and component radii at current values (without it the tokens are dead — theme.css:378-379 out-specifies any consumer) + reconciliation of `dashboard.html.j2:1653`'s local `--sp-*` (its `--sp-8:32`→`--sp-7`; recorded amendment to packet PR-0's `--fs-*`-only extraction boundary) + zh tracking/uppercase resets beyond h2 + `_icons` base-CSS reconciliation (stroke 1.8) + `.eyebrow`→`--fs-label` snap + specimen updated to consume real tokens (its local proposed-block deleted). **Collision gate before landing: re-run the §8 class-collision scan; any new `.mx-*` hit blocks.** | all migration packets |
| **DS-PR-1** | (a) `design_system` added to `OVERRIDABLE` in `scripts/build_product_page_registry.py:97-103` — today the builder hard-errors on unknown override keys (`:1050-1053`), so the field must be schema'd before any packet writes it; (b) the existing `archetype` values re-keyed to the §10 registry ids (crosswalk in the master doc §10) + the field completed for all rows; (c) **governance unit defined**: a registry row governs `(source_template, selector/region scope)` pairs, not bare files — `dashboard.html.j2` (renders macro + us_stocks) gets explicit `governed_regions`; (d) ratchet script `scripts/check_design_system.py` lands **report-only** (guard-registry registered; annotation law: bare `print("::notice …", flush=True)` at line start) | ratchet waves R1+, all packet gates §0.3/§0.7/§0.8 |
| **DS-PR-2** | PR template / review checklist wiring for evidence matrix; harness gains forced-state capture flag if absent | — |

**AMENDED 2026-08-12 (foundations lane):** DS-PR-1 (PR #5486) landed ahead of packet PR-0/DS-PR-0 —
grounds: Sol §J.9 (count-ladder ratification) is still pending, which blocks the theme.css chain;
DS-PR-1 consumes nothing from DS-PR-0, and its ratchet lands R0 report-only. DS-PR-2 (PR #5475)
shipped alongside it. Executed order of docket items 1–3 is therefore **3 → 1 → 2**; gates and
scopes are unchanged.

theme.css collision discipline: DS-PR-0 lands only after packet PR-0 merges (one file, two
sequenced PRs, never parallel); the known four-way blast radius (sync → hash → stamps →
line-sliced mockup) applies to both.

## §6 The anti-regression ratchet

**Mechanism: a growing compliant-surface registry, diff-scoped lint, three waves.** Legacy debt
never reds main: the lint only judges (a) files whose registry row says `compliant: true`, and
(b) newly created templates.

**Static rules** (`scripts/check_design_system.py`, on the PR diff; the governed unit is the
registry row's `(template, region)` pair from DS-PR-1(c), never a bare file):

1. New color literals (`#hex`, `rgb(`, `hsl(`) outside `theme.css`/sanctioned asset files.
2. New `font-family:` literals (tokens only).
3. New `border-radius` values not `var(--r-*)`.
4. New **literal-valued custom properties in ANY selector** outside `theme.css` (`:root`,
   `body.page-*`, or class scope alike — `dashboard.html.j2:1616` declares its family on
   `body.page-macro`, which a `:root`-only rule misses). Derivations
   (`--local: var(--theme-token)`) are the §2 compliant pattern and pass.
5. New `*-card` class *definitions* outside the canonical inventory (heuristic; warn-tier).
6. Banned Tier-1 vocabulary outside `data-tip-*`/`<details>`/Tier-3 pages (doctrine §6's
   planned vocabulary lint — same registry, same waves).
7. Inline `<style>` byte growth on a governed region (warn at >0, fail at >5%).
8. Emoji codepoints in markup on governed regions.

**Evidence rules** (process gates, not static lint): the §0.2 screenshot matrix, forced-state
shots, and harness capture are review-blocking for packet PRs; DS-PR-2 wires the checklist. A
follow-up may add a CI presence check (registry row's `evidence` path exists) — presence only,
never pixel judgment in CI.

**Waves:** **R0** (with DS-PR-1): report-only `::notice` annotations on every PR, estate-wide —
builds the baseline and finds false positives. **R1**: blocking for compliant-registry regions;
NEW templates get the **graduated born-compliant rule** — rules 1–4 block, rules 5–8 warn
(a new surface must be token-clean from birth, but is not required to be a completed
migration; the §8 delta audit's `--ff-*`/winner-health window shows what ungraduated R1 would
have blocked mid-flight). A new template may carry
`design_system: {exempt: true, reason, expires}` in its registry row — operator-visible,
time-boxed, never silent. **R2** (post-launch): warn-tier estate-wide, blocking threshold
reviewed quarterly. The registry only grows; a compliant region that must regress requires
the same exception entry (never silent removal).

**Known-trap notes for the implementer:** annotations start the line, printed not logged,
`flush=True` (CI-guarded house law); the checker must be registered in the guard registry;
warn-tier output is not a red (a wall of `::warning` with exit 0 gates nothing — the blocking
arm is the exit code on rule violations for governed files).

## §7 P0 launch convergence docket

**Principle:** the customer journey and high-reach families converge before launch; the long
tail converges by template, post-launch. Nothing is hand-polished ×4,000.

**P0 — pre-launch (blocking commercial launch):**

| # | Item | Dependency |
|---|---|---|
| 1 | packet PR-0 foundations | **Sol §J.9** (count-ladder ratification; clause 3 — the cell set + field — is ANSWERED 2026-08-13 by the Prophet ruling, PR #5504: PR-0(c) builds the derived `lifecycle_state` projection per ruling §9, not a minted stage enum) |
| 2 | DS-PR-0 (scales + `.mx-*` primitives + rebinds) | packet PR-0 merged |
| 3 | **DS-PR-1** (registry field schema + archetype re-key + governance unit + ratchet R0) | DS-PR-0 — **sequenced before every migration below because gates §0.3/§0.7/§0.8 consume it** |
| 4 | PR-1 funnel chrome (nav auth/plans presence, 404 — the 404 mockup in PR-1's own mockup gate is archetype I's reference, satisfying first-of-archetype) | PR-0 |
| 5 | Today reference build (`start.html`, A) | DS-PR-0 + mockup gate |
| 6 | Prophet board reference (`us_stocks.html`, B) — packet AUTHORED 2026-08-13: `research/migration_packets/MP-1-prophet-board.md` | DS-PR-0; PR-0(c) field live in a published payload; §J.10 concurrence **GRANTED 2026-08-13** (PR #5504, ruling §10 conditions bind); mockup gate |
| 7 | Prophet detail (new surface, C-signal) | Sol §J decisions, Handoff D |
| 8 | Plans (H-plans) | Chairman Founding-Pro variant decision |
| 9 | Dossier reference + `stock.html` resolver (C-company) | Sol route ruling |
| 10 | **macro.html migration to the dense-dashboard reference** (D) — the Wave-0 reference (`mockups/design_system/macro_reference.html`) is its frozen contract. **Recorded supersession:** IA §8 row 3 said "conformance pass later; not a reference page" — this docket amends that ruling (grounds: the D archetype needs a production consumer pre-launch, and macro is P0 route #3 and the estate's main anonymous SEO entry). **Same-file collision:** items 6 and 10 both edit `dashboard.html.j2` — item 6 lands first; item 10's packet names its macro-mode region scope and rebases on 6 (site-heavy law: rebuild, not rebase, on conflict) | DS-PR-0 + item 6 merged |
| 11 | Landing proof-belt hero (live dated board replaces mock-ups) | taste-gate (packet §H) |
| 12 | Nav N0 six-job regroup | **Sol approval (IA §10.1)** |
| 13 | Access-truth fixes (Handoff A's lane: proof-page payload, silent 401s, signup seam) | its own lane — listed because the journey breaks without it |

*Status 2026-08-12: item 3 (DS-PR-1) executed first per the §5 amendment. Items 1–2 remain blocked
on Sol §J.9. Items 4 and 5 have their mockup gate satisfied by
`mockups/design_system/{today_reference,utility_reference}.html` (this lane); the BUILDS still wait
on DS-PR-0.*

**P1 — immediately post-launch:** `china.html` + `hk.html` (D-archetype followers of the macro
reference — the reference generalizing IS the test of Wave 0), `news`/`alerts` (G — the G
reference ships with the first of these, satisfying first-of-archetype), `watchlist`
(**pending the IA §10.4 Sol ruling** — its archetype home follows the ruling),
`confluence_screener` + heatmaps (B), `research_vault` (F — its migration is the F reference),
`products/*` polish (H-product), sector_central pair (C/E — the E reference ships with the
first desk migrated).

**P2 — the neglected middle (~30 desks):** intelligence desks (E) in reach order
(`china_intel`, `policy_watch` twins, `alt_data`, `smart_money`, `capital_structure`,
`fundamental_forensics`, `market_memory`, `foresight`, `neural_web` post-naming), remaining
market dashboards (`canada`, `intl`, country pages, `bonds`, `forex`, `commodities`, cycles
family), remaining boards (`baskets_*`, `allocation_*`, `stage_analysis`, `winner_health`,
`leader_radar`, `stock_seasonality`, radars).

**P3 — generated long tail, template-level only:** `stocks/` dossier family (with P0 #7's
template), `basket*/`, `subsector*/`, `sectors/`, `rotation*/` (archetype C templates), then
the self-contained vector/hub legacy family last.

**Sequence rule:** within any wave, first-of-archetype pages go first (they buy the reference
that makes followers cheap); a follower never migrates before its archetype's reference page
has shipped and survived review.

## §8 Current-main delta audit record (bounded sonnet lane, 2026-08-12)

Scope: customer-facing templates/CSS/JS changed since census provenance (2026-08-11T00:00Z,
SHA `6560d5a8`); 15 commits to origin/main HEAD `5a40d6a`. Findings that matter to this
program (full lane report in the session transcript; facts, file:line cited by the lane):

1. **Foundation files untouched:** `theme.css`, `tier_preview.css`, `navigation-refresh.css`,
   `landing.css`, `_icons.html.j2`, `_prophet_card.html.j2` — zero commits since census. The
   token architecture this program extends is current.
2. **A new page-local token root was born after the census:** `--ff-indigo/--ff-cyan/
   --ff-coral/--ff-amber/--ff-ink-soft/--ff-card` in `fundamental_forensics.css:6-13`
   (+331 lines, Filing Forensics UX revamp `ef5c186`). Added to the §11.3 migration table in
   the master doc. This is live proof the fragmentation engine keeps running until the ratchet
   lands — DS-PR-1's R0 wave would have flagged it at birth.
3. **`.ladder` name collision:** Winner Health's three-tier board (`411b7d0`, +473 lines,
   ~40 new page-local classes) already uses `.shelf/.rung/.ladder` inside
   `winner_health.html.j2`'s inline style. Packet PR-0's planned `.ladder` count-ladder
   primitive in theme.css MUST verify against this page (rename the primitive, e.g.
   `.mx-ladder`, or prove the page-local rules can't leak) before landing — an inline
   page-local class out-specifies a theme rule on that page.
4. **Type-ramp drift confirmed and enumerated** (sharpens packet PR-0's shadowing-cleanup
   list): `seo_base.html.j2:118-120` duplicates macro's 11-value ramp identically;
   `leader_radar.html.j2:108-117` drifted (display 44, h1 27, h2 16, no h3);
   `intraday_flow.html.j2:29-30` drifted (display 44, h1 27, h2 17, no h3);
   `bonds.html.j2:65` carries a one-off `--fs-hero:56px`. All are `--fs-*` reconciliation
   targets in the foundations wave.
5. **china.html index-tile bug from the census is fixed on main** (`4fb2324` — CSI 300/ChiNext
   tiles were rendering ETF NAV as index level). The census §6 defect list is one row shorter;
   the regime-contradiction findings stand.
6. `government-revenue-parity.css` (+109) is a restoration of a file deleted 2026-08-02, not
   new design language. Other deltas (prophet receipts plain-word pass, dashboard release-radar
   modal refinement, basket_detail stamp fix, biocatalyst change-tape) are content/correctness
   work inside existing idioms — no new card systems, no new routes.
7. **Rival token scales beyond `--fs-*`** (red-team supplement — the lane's item 4 enumerated
   the ramp only): `options.html.j2:90-91` ships `--s1..--s8` (`--s8:44px`) **and** its own
   `--r-pill/--r-ctl/--r-panel/--r-shell`; `dashboard.html.j2:1653` ships a `body.page-macro`
   `--sp-*` block (no `--sp-7`, `--sp-8:32px` — the §2.2 collision DS-PR-0 reconciles);
   `dashboard.html.j2:1655` + `seo_base.html.j2:118-123` ship `--r-sm/--r-md/--r-lg`. All are
   named reconciliation targets (DS-PR-0 for the dashboard `--sp-*`; each page's migration
   for the rest).
8. **Module-count anchors** for the master doc §10 selection ruling: macro = 13 first-level
   sections (hero `dashboard.html.j2:2257` through where-next `:11292`, visual order per the
   `order:` scheme documented at `:5329-5342`, plus the DOM-order Release Radar `:8609`);
   china = 14 (`china.html.j2:1659-2279`). Counts are the delta lane's, template-anchored.
9. **Baseline naming:** "census provenance" in this section = the page census's registry
   snapshot (`data/product_experience/page_registry.json`, `generated_at
   2026-08-11T00:00:00Z`, macro source SHA `6560d5a8` — `research/PRODUCT_PAGE_CENSUS_2026-08.md`
   §1); the experience census (same PR #5401) shares it.
10. **Mockup-path convention:** program-level design-system references live under
   `mockups/refs/design-system/`; per-page migration mockups keep the packet convention
   `mockups/refs/institutionalize/<page>/` (packet §I mockup gate). Two namespaces, one rule:
   committed files, never prose.

## §9 Red-team record

Two independent Opus red-team passes ran 2026-08-12 (full record + dispositions: master doc
§18). Verdict REWORK — scoped; integrated in this PR. Findings that changed THIS document:

- **Docket ordering:** DS-PR-1 moved from P0 item 11 to item 3 — it was sequenced *after*
  the seven migrations whose §0.3/§0.7/§0.8 gates consume its field, script, and archetype
  assignments. Sol §J.9 restored as item 1's dependency (packet PR-0(c) mints the stage
  field §J.9 reserves).
- **Ratchet mechanics:** `design_system` is NOT an overridable registry key today (the
  builder hard-errors, `build_product_page_registry.py:1050-1053`) — DS-PR-1(a) schemas it;
  governance unit redefined as `(template, region)` pairs (DS-PR-1(c)) because
  `dashboard.html.j2` renders two pages and file-granularity would red the macro region's
  legacy debt the moment `us_stocks` flips compliant — exactly the "never reds legacy"
  violation; rule 4 re-specified to literal-valued custom properties in ANY selector
  (`body.page-*` roots were invisible to a `:root`-only rule, and the derivation pattern it
  DID flag is the compliant one); R1 born-compliant graduated (rules 1–4 block, 5–8 warn)
  with a time-boxed, operator-visible exemption field.
- **Packet form:** same-file sibling-page rule added to field 9 (the dashboard.html.j2
  case); §0 gained the perf/render-budget gate; §4's inline-style line now cites the §6.7
  thresholds instead of stating a rival "never grows" law.
- **DS-PR-0 scope:** `.mx-*` namespace law (11 collision families enumerated in the master
  doc §11.1); the `html body` var() rebind; the `dashboard.html.j2` `--sp-*` reconciliation
  (recorded packet-boundary amendment); the collision-scan landing gate.
- **Docket content:** IA §8-row-3 supersession for macro.html now recorded instead of
  silent; items 6/10 same-file sequencing named; first-of-archetype coverage stated for I
  (404 in PR-1's mockup gate), G and E (P1); watchlist hedged to the IA §10.4 Sol ruling.
- §8 gained items 7–10 (rival scales the lane's ramp-only enumeration missed;
  module-count template anchors; baseline naming; mockup-path convention).

Standing dissents: none — the two partially-rejected findings and their grounds are in the
master doc §18.12.
