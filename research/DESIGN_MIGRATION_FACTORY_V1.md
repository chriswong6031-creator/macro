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
9  FORBIDDEN SCOPE       theme.css (unless the packet IS a DS-PR), nav partials, engine
                         scripts, sibling pages — plus packet-specific bans
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
  page-by-page; never a big-bang).
- As-of variants → `.dtp-asof` / `.dtp` family; one per panel.
- Empty states → `.empty`+`.empty-why` (5 sanctioned causes).
- Display charts → illus idiom (the 9/247 compliance gap closes through packets).
- Emoji-as-icons → `_icons.html.j2` monoline set.
- Exactly one h1; `.sec` header anatomy on every panel.
- 390w no-horizontal-scroll check; mobile reduction per archetype.
- Banned Tier-1 vocabulary sweep (doctrine §2) on all touched copy, EN and ZH.
- Inline `<style>` shrinks or holds — never grows (measured in the lint report).

## §5 PR sequencing — how the factory's foundations land

The packet's PR-0 (type ramp, `.ladder`, `.chg-row`, `.empty`, lock slots) is already law and
**owns the first theme.css edit**. The factory adds, in order:

| PR | Scope | Blocks |
|---|---|---|
| **DS-PR-0** (after packet PR-0, same owner discipline: small, reviewed alone) | remaining §2.2 scales (`--sp-*`, `--r-*`, `--t-*/--ease-*`, `--ser-*`, `--shadow-hover`) + new primitives (`.vh`, `.sec`, `.tbl`, `.callout`, `.disc`) + `_icons` base-CSS promotion + specimen updated to consume real tokens (its local proposed-block deleted) | all migration packets |
| **DS-PR-1** | registry overrides gain `archetype` for all rows + `design_system` field schema; ratchet script `scripts/check_design_system.py` lands **report-only** (guard-registry registered, annotation law obeyed: bare `print("::notice …", flush=True)` at line start) | ratchet waves R1+ |
| **DS-PR-2** | PR template / review checklist wiring for evidence matrix; harness gains forced-state capture flag if absent | — |

theme.css collision discipline: DS-PR-0 lands only after packet PR-0 merges (one file, two
sequenced PRs, never parallel); the known four-way blast radius (sync → hash → stamps →
line-sliced mockup) applies to both.

## §6 The anti-regression ratchet

**Mechanism: a growing compliant-surface registry, diff-scoped lint, three waves.** Legacy debt
never reds main: the lint only judges (a) files whose registry row says `compliant: true`, and
(b) newly created templates.

**Static rules** (`scripts/check_design_system.py`, on the PR diff):

1. New color literals (`#hex`, `rgb(`, `hsl(`) outside `theme.css`/sanctioned asset files.
2. New `font-family:` literals (tokens only).
3. New `border-radius` values not `var(--r-*)`.
4. New `:root { --` token-family blocks outside `theme.css`.
5. New `*-card` class *definitions* outside the canonical inventory (heuristic; warn-tier).
6. Banned Tier-1 vocabulary outside `data-tip-*`/`<details>`/Tier-3 pages (doctrine §6's
   planned vocabulary lint — same registry, same waves).
7. Inline `<style>` byte growth on a compliant file (warn at >0, fail at >5%).
8. Emoji codepoints in markup on compliant files.

**Evidence rules** (process gates, not static lint): the §0.2 screenshot matrix, forced-state
shots, and harness capture are review-blocking for packet PRs; DS-PR-2 wires the checklist. A
follow-up may add a CI presence check (registry row's `evidence` path exists) — presence only,
never pixel judgment in CI.

**Waves:** **R0** (with DS-PR-1): report-only `::notice` annotations on every PR, estate-wide —
builds the baseline and finds false positives. **R1**: blocking for compliant-registry files +
all NEW templates (born-compliant rule). **R2** (post-launch): warn-tier estate-wide, blocking
threshold reviewed quarterly. The registry only grows; a compliant page that must regress
requires an operator-visible exception entry in the registry row (never silent removal).

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
| 1 | packet PR-0 + DS-PR-0 foundations | — |
| 2 | PR-1 funnel chrome (nav auth/plans presence, 404) | PR-0 |
| 3 | Today reference build (`start.html`, A) | PR-0 + mockup gate |
| 4 | Prophet board reference (`us_stocks.html`, B) | PR-0, §J.10 concurrence, Prophet-lane coordination |
| 5 | Prophet detail (new surface, C) | Sol §J decisions, Handoff D |
| 6 | Plans (H) | Chairman Founding-Pro variant decision |
| 7 | Dossier reference + `stock.html` resolver (C) | Sol route ruling |
| 8 | **macro.html migration to the dense-dashboard reference** (D) — the Wave-0 reference (`mockups/design_system/macro_reference.html`) is its frozen contract | DS-PR-0 + reference ratified |
| 9 | Landing proof-belt hero (live dated board replaces mock-ups) | taste-gate (packet §H) |
| 10 | Nav N0 six-job regroup | **Sol approval (IA §10.1)** |
| 11 | DS-PR-1 ratchet R0 | DS-PR-0 |
| 12 | Access-truth fixes (Handoff A's lane: proof-page payload, silent 401s, signup seam) | its own lane — listed because the journey breaks without it |

**P1 — immediately post-launch:** `china.html` + `hk.html` (D-archetype followers of the macro
reference — the reference generalizing IS the test of Wave 0), `news`/`alerts`/`watchlist` (G,
pending IA §10.4 identity ruling), `confluence_screener` + heatmaps (B), `research_vault` (F),
`products/*` polish (H), sector_central pair (C/E).

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

## §9 Red-team record

**PENDING** — same rule as the master doc §18: this factory is not frozen until the
independent Opus red-team pass has run and its real findings are recorded here.
