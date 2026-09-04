# Theme-Parity Ratchet + Presentation-Layer Convergence Architecture

**Status:** DRAFT FROZEN CANDIDATE — Chairman approved the architecture direction on 2026-08-27; this written specification still requires Chairman review before implementation planning or builder dispatch.

**Sol Skillpack pin:** `mastermindx-market-intelligence/Mastermind@af43f356f4f7f34cb3514d1d1099b50444af8487` (`mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap-major 1 compatible).

**Macro pickup base:** `mastermindx-market-intelligence/macro@ca671bf404feb7d5212da9da3f6ad458efd331dd`.

**Authority precedence for this program:**

1. `docs/DESIGN_DOCTRINE.md` — user/content law.
2. `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` — visual/composition constitution.
3. `research/DESIGN_MIGRATION_FACTORY_V1.md` — migration/evidence/ratchet process law.
4. This architecture — theme-parity enforcement, presentation-source boundary, and rollout sequencing.
5. Per-surface migration packets and approved references.
6. Individual live pages — evidence only, never precedent.

This architecture extends the existing design system. It does **not** create a second design system, token root, page registry, evidence system, or UI lifecycle.

---

## 0. Chairman outcome

Mastermind must stop treating light mode as a mechanical translation of dark mode.

The customer-facing product must have two deliberately designed art directions of one semantic system:

- **Dark:** command center — luminance depth, instrument calm, restrained glow.
- **Light:** research workspace — paper, structure, air, white material on a cool canvas, hairline discipline, shadow instead of glow.

A builder must not be able to ship a premium dark surface and obtain a passing light surface merely because the same CSS still renders after token substitution.

The immediate proving vertical is the Canada Stocks V3.8 page, where the product/semantic correction is already `PROVEN_LIVE` but the Chairman has identified the light treatment as materially degraded relative to the intended Mastermind quality bar. The permanent outcome is site-wide prevention, not a Canada-only repaint.

### Primary user job

A Mastermind subscriber should be able to use any primary surface in the selected theme without feeling that one theme is the designed product and the other is a fallback skin.

### Machine / organizational job

The design system, agent instructions, page registry, CI guards, evidence harness, and review workflow must make dual-theme design parity a **forward-only enforced property**, while allowing legacy debt to be retired incrementally rather than reddening the entire repository at once.

### 10/10 end state

A future builder starting from a fresh session cannot accidentally recreate this failure because:

1. the design packet specifies separate dark and light treatments;
2. substantive presentation CSS lives in governed source, not runtime JS escape hatches;
3. new UI code is token-clean by construction;
4. changed visual surfaces owe committed evidence in both themes, both languages, desktop and mobile;
5. light-mode evidence is explicitly reviewed for taste/hierarchy rather than only renderability;
6. compliant surfaces are registry-ratcheted and cannot regress silently;
7. missing visual proof yields `PARTIAL/BLOCKED`, never `PASS`;
8. production acceptance preserves functional/product truth and visual-quality truth as separate claims.

---

## 1. Current canonical state

### 1.1 Capability ledger

| Capability | State | Canonical evidence / ruling |
|---|---|---|
| User-first design doctrine | `PROVEN_LIVE` as house law | `docs/DESIGN_DOCTRINE.md` |
| Light is a design target, not a translation | `PROVEN_LIVE` as written law | Doctrine §5 builder checklist / 2026-08-03 light-mode parity ruling |
| Master product design system | `PROVEN_LIVE` as visual/composition law | `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` |
| Dark/light as two art directions | `PROVEN_LIVE` as written law | Master Product Design System §1/§12 |
| Dual-theme migration evidence matrix | `PROVEN_LIVE` as process law | `research/DESIGN_MIGRATION_FACTORY_V1.md` + `.github/PULL_REQUEST_TEMPLATE/design_migration.md` |
| Light-mode capture tooling | `BUILT_NOT_PROVEN` as a universal gate | `scripts/light_mode_sweep.py`; useful but optional/off-render-path |
| Design-system static checker | `PARTIAL` | `scripts/check_design_system.py`; R0 report-only default |
| Compliant-surface registry ratchet | `DARK_OR_DISCONNECTED` | `config/product_experience/page_registry_overrides.yml`; compliance coverage has not been graduated sufficiently to prevent this class |
| Runtime presentation governance | `BROKEN` | Stock-dashboard composer owns substantial CSS inside `site/*-stock-v36.js`, outside the current design checker scan root |
| Canada Stocks V3.8 product/semantic behavior | `PROVEN_LIVE` | PR #6545 / merge `1276333b37b9131ed77c97bc6ffaa63a1ca9be72`; acceptance `research/STOCK_DASHBOARD_V38_CANADA_ACCEPTANCE_2026-08-27.md` |
| Canada V3.8 dark visual composition | `PROVEN_LIVE` for current production usability; preserve unless this program explicitly improves it | same production acceptance + Chairman review |
| Canada V3.8 light visual quality | `BROKEN` | Chairman production review 2026-08-27: flat/nested-grey/degraded composition; dark becomes visually coherent when theme is switched |
| Site-wide prevention of dark-first / light-translation regressions | `NOT_BUILT` | no hard end-to-end gate currently makes the written law unavoidable |

### 1.2 Material disagreement ledger

**Claim:** “The repository already requires light-mode parity.”

- Source A: doctrine/design-system/migration-factory say yes.
- Source B: Canada V3.8 shipped with a dark-first runtime stylesheet whose light treatment is mostly token translation.
- Canonical owner: design law owns the requirement; GitHub/live product owns what actually shipped.
- Ruling: the law is not stale. **Enforcement and presentation-source boundaries are incomplete.**

**Claim:** “Canada V3.8 is complete.”

- Source A: V3.8 acceptance correctly records the product/semantic correction as `PROVEN_LIVE`.
- Source B: Chairman visual review identifies a material light-plane design defect.
- Canonical owner: both facts survive. Functional/product proof does not automatically prove visual quality.
- Ruling: V3.8 semantic capability remains `PROVEN_LIVE`; light-theme visual parity is a separate `BROKEN` capability to repair without reopening ranking, signal, membership, quote, entitlement, or action-vs-leadership law.

### 1.3 Collision census at freeze

At `ca671bf404feb7d5212da9da3f6ad458efd331dd`, no open PR was found by current GitHub search for:

- `site/canada-stock-v36.js`;
- `site/hk-stock-v36.js`;
- `scripts/check_design_system.py`.

The architecture must be re-collision-checked immediately before each implementation wave; this statement is not future authorization.

---

## 2. Root cause

The failure is not “builders ignored a missing design guide.” The repository already contains the right principle. Four structural gaps let the failure pass anyway.

### 2.1 Law exists, but the static ratchet is not yet authoritative enough

`scripts/check_design_system.py` still describes itself as R0/report-only by default. It can detect substantial design debt, but the estate has not graduated enough surfaces to make that detection a hard forward-only contract.

### 2.2 The compliant registry has insufficient coverage

The migration factory correctly designed a growing compliant-surface registry so legacy debt would not red main. In practice, too few high-value surfaces are ratcheted as compliant, so the strongest enforcement path does not cover the pages being redesigned most aggressively.

### 2.3 Runtime CSS is an enforcement escape hatch

Canada and HK stock-dashboard composers carry large runtime-generated CSS strings inside `site/*-stock-v36.js`. The current design-system checker deliberately scans `templates/` only. Therefore a builder can obey the design system in templates while creating a parallel, largely ungoverned presentation layer in runtime JS.

This is the key architecture defect to close.

### 2.4 Visual proof has been treated as functional proof on some fast-moving product waves

The stock-dashboard reviews were strong on product truth: rank authority, missing-vs-zero, action-vs-leadership, population preservation, filters, routes, live quotes, entitlement, and degradation behavior. That rigor must remain.

But “light page opens and functions” is not equivalent to “light mode is deliberately designed.” The migration-factory evidence contract already knows this; non-migration product waves have not been consistently forced through an equivalent visual-quality gate.

---

## 3. Binding design thesis

### 3.1 Two themes, one semantics, two compositions

Dark and light share:

- information architecture;
- component semantics;
- spacing/type scales;
- state meanings;
- user actions;
- data contracts;
- ordering and density law;
- interaction behavior.

They do **not** have to share identical material treatment.

A theme-specific treatment is expected when the visual mechanism itself changes across luminance environments.

Examples:

| Semantic job | Dark mechanism | Light mechanism |
|---|---|---|
| Page depth | luminance steps + restrained glow | cool canvas + white material + disciplined shadow/hairline |
| Selected/featured card | quiet ring + low-alpha glow | white/raised card + restrained border/shadow; no luminous halo |
| Action lane identity | dark tinted rail/header + subtle fill | mostly white/neutral lane + narrow semantic rail/header treatment |
| Hover elevation | luminance + shadow | shadow + border definition |
| Ambient brand atmosphere | low-alpha aurora | pastel stain with much lower visual weight |
| Modal backdrop | dark scrim | cool low-opacity scrim; avoid dirty grey overlay |
| Colored rows | dark tint may carry depth | quiet tint + 2–3px semantic rail; avoid highlighter smear |

A CSS rule is not inherently superior because it is shared across themes. Shared semantic variables are desirable; shared material recipes are only desirable when they remain visually correct.

### 3.2 Light is not “less dark”

The light art direction must read as an institutional research workspace, not a dark terminal whose colors were inverted.

For primary discovery boards, the default target is:

- perceptibly cool page canvas;
- white or near-white top-level material;
- minimal nested grey containers;
- one clear elevation step between canvas, panel, and raised interactive element;
- hairlines used for structure, not box spam;
- shadows used to establish material hierarchy, not glow;
- hue reserved for meaning, never decoration;
- strong text hierarchy and numeric discipline;
- empty space used as a structural tool.

### 3.3 Dark remains a first-class target

This program is not a “make everything light” redesign. Canada dark currently demonstrates much of the intended premium character. Dark regressions are blocking unless explicitly approved as an improvement.

---

## 4. Presentation-source boundary

### 4.1 Governing rule

**Substantive product styling may not be authored as an opaque runtime CSS system inside page/composer JavaScript.**

JavaScript may:

- mount/move/recompose canonical DOM;
- set state classes/attributes;
- select existing variants;
- control disclosure, filters, modals and interaction;
- apply truly data-dependent inline geometry only where CSS cannot express the value (for example a measured width or chart coordinate), using governed semantic custom properties when practical.

JavaScript may not:

- define a page's material system through a multi-kilobyte `style.textContent` string;
- mint a parallel palette/token family;
- carry duplicated light/dark stylesheet branches invisible to the design-system checker;
- create reusable component styling that belongs in governed presentation source.

### 4.2 Stock-dashboard family target

The Canada/HK stock-dashboard family converges on one governed presentation asset:

- source: `templates/stock-dashboard.css`;
- published pair: `site/stock-dashboard.css`;
- semantic tokens: inherited from `templates/theme.css` only;
- page-local custom properties: derivations only;
- base namespace: `.mx-stockdash`;
- market modifiers only when semantics genuinely differ: `.mx-stockdash--ca`, `.mx-stockdash--hk`, later `.mx-stockdash--cn` if/when authorized.

This stylesheet is a **consumer** of the master design system, not a new token authority. No new `:root` palette family is permitted.

The existing composer class names may be temporarily supported during the extraction wave if that materially reduces risk, but the canonical family stylesheet owns the visual decisions. Any aliasing is migration compatibility, not a second design language.

### 4.3 Loader / fail-soft rule

A composer may not hide the legacy page until its governed stylesheet is available.

Conceptual sequence:

```text
legacy page visible
→ shared stock-dashboard stylesheet loaded and verified
→ composer prerequisites/data available
→ composer mounts
→ mounted class activates composed presentation
```

If CSS fails, JS fails, data fails, or required DOM is absent, the legacy page remains visible and functional. No flash of an unstyled composed shell may replace the legacy surface.

### 4.4 Theme switch rule

Theme switching must not require re-running the composer. The DOM is semantic; the governed stylesheet resolves the correct art direction through theme selectors/tokens.

---

## 5. Canada V3.8 as the proving vertical

Canada is the first repaired vertical because:

1. the Chairman identified the defect there directly;
2. V3.8 product semantics are already production-proven, giving a stable functional baseline;
3. the runtime CSS escape hatch is easy to identify;
4. the same pattern can then be reused for HK without copying Canada semantics.

### 5.1 Must preserve exactly

The Canada theme-parity wave MUST NOT change:

- `What to Act On Now` owner-native lane semantics;
- Action Timing ≠ Leadership law;
- sector no-rank law;
- owner-only theme rank + visible basis;
- per-group membership known/unknown behavior;
- missing ≠ zero;
- Top Picks population law;
- Grid/Table XOR;
- `.sm-hidden` rescue behavior;
- LIVE quote plane/table enhancement;
- Board date vs LIVE date distinction;
- Track Record ownership and moved `.trk` behavior;
- Terminal routes;
- the two Canada artifact fetches and their degrade behavior;
- entitlement/auth;
- Prophet ranking, lifecycle, population, signals or scoring;
- engine/data contracts.

The accepted V3.8 production record remains the functional baseline.

### 5.2 Canada light art direction

The Canada first vertical freezes these visual goals:

#### Page and panel hierarchy

- Cool canvas is visibly distinct from primary panels.
- Primary modules are white/near-white material with one disciplined E1 shadow/hairline treatment.
- Nested `panel2` grey is used sparingly; do not stack grey panel inside grey lane inside grey row unless each boundary conveys real interaction/state.

#### What To Act On Now

The four lane containers must read as **one action instrument with four semantic lanes**, not four mini dashboards.

At 1440-class light mode:

- outer module owns the main material/shadow;
- lane bodies are primarily white/neutral;
- stance identity comes from a narrow semantic top/left rail and restrained heading treatment;
- rows rely on typography + separators rather than individual raised boxes;
- “View all” is a quiet control, not another boxed panel;
- empty Buy Now remains intentionally calm and honest, not visually broken;
- no performance/rank information is added.

Dark may continue using stronger tint/luminance differentiation where it is visually successful.

#### Prophet cards

- Preserve existing Prophet card semantics and canonical stance colors.
- Top Picks in light mode use material elevation and a restrained ring; no luminous glow.
- Price/change hierarchy remains strong.
- Avoid white-card-on-white disappearance: card edge/elevation must remain legible against the containing material.

#### Leadership & Rotation

- Theme rank basis remains explicit.
- Light rows should feel like an institutional ranking table/list, not a stack of grey buttons.
- Action stance and rank stay visually separate axes.

#### Controls

- Segmented controls require a real selected state in light mode: white raised selection inside a slightly deeper neutral track, or equivalent token-driven treatment.
- Borders alone are insufficient if selected and unselected surfaces collapse perceptually.

#### Modal

- Light overlay uses a cool low-opacity scrim.
- Modal card is white material with disciplined shadow; no muddy grey sheet.
- Internal tables/panes avoid unnecessary nested boxes.

### 5.3 Dark regression budget

The Canada wave owes before/after dark screenshots and computed checks. Any dark visual change outside the explicitly named extraction/convergence surface is a review finding. The preferred outcome is dark visual parity or a separately justified improvement, not incidental repaint.

---

## 6. Enforcement architecture

The permanent fix has four independent gates. No single gate is trusted to carry the whole quality bar.

### 6.1 Gate A — forward-only design-system static ratchet

Do **not** turn the whole legacy estate red.

Graduate `scripts/check_design_system.py` in two layers:

#### A1. Added-line / new-decision enforcement

On any user-facing diff, newly introduced design decisions may not add:

- raw color literals outside canonical theme/sanctioned owners;
- literal font families;
- literal radii outside the radius scale;
- literal-valued local custom-property palettes;
- new emoji-as-UI;
- new parallel token roots.

Pre-existing debt remains reportable and cannot grow.

#### A2. Full-region enforcement

When a page/region earns `design_system.compliant: true`, the existing registry ratchet becomes full blocking law for that governed region. Compliance never silently flips back to false. Regression requires an explicit, expiring exception with review-visible rationale.

### 6.2 Gate B — runtime-style injection fence

Add a dedicated registered house-law guard for user-facing JavaScript presentation injection.

Required behavior:

- detect new runtime `<style>` creation / large CSS-string injection / `insertRule`-style parallel presentation systems;
- allow canonical shared theme owners only through an explicit, narrow allowlist;
- pin legacy exemptions by file/count or equivalent ratchet so debt cannot grow;
- Canada/HK composer exemptions disappear as their CSS is extracted;
- a new composer cannot introduce another opaque stylesheet and still pass CI.

This is a separate guard rather than widening `check_design_system.py`'s intentionally narrow scan-root/CI-closure contract.

### 6.3 Gate C — visual evidence contract for material UI changes

Any material visual/composition change owes a committed evidence manifest using the existing page-evidence harness conventions.

Minimum matrix for flagship/customer-facing changes:

- dark EN 1440;
- dark EN 390;
- dark ZH 1440;
- dark ZH 390;
- light EN 1440;
- light EN 390;
- light ZH 1440;
- light ZH 390;
- one full-page overview shot;
- forced loading / empty(+why) / stale / error where the surface owns those states.

CI may check **presence, declared page/theme/lang/width identity, and file existence**. CI does not decide whether the design is beautiful.

A human/Opus design reviewer judges:

- hierarchy;
- material depth;
- density;
- theme-specific treatment;
- typography;
- responsive composition;
- semantic color use;
- native ZH parity;
- visual regressions against the approved reference/baseline.

A verbal statement “checked light/dark” is no longer sufficient evidence for a material design wave.

### 6.4 Gate D — agent instruction / handoff law

Update the durable instructions consumed by both Claude and non-Claude builders.

Every user-facing design/implementation packet must contain a **THEME ART DIRECTION** section with:

- dark treatment;
- light treatment;
- which mechanisms intentionally differ;
- reference screenshots/mockups;
- theme-specific failure states;
- required evidence matrix.

Designer rule:

- must make explicit dark and light composition decisions;
- may not approve “same CSS but tokens swap” without arguing why the mechanism genuinely works in both themes.

Builder rule:

- if a frozen visual spec lacks light art direction or required evidence, stop `BLOCKED/PARTIAL`; do not invent or silently translate;
- must not create a parallel runtime stylesheet to avoid design-system constraints.

Reviewer rule:

- `PASS` requires both themes to be judged as designs;
- functional browser success is necessary but not sufficient.

Durable homes to amend in the implementation program include at minimum:

- `CLAUDE.md`;
- `AGENTS.md`;
- `.claude/agents/designer.md`;
- `.claude/agents/builder.md`;
- design-migration/relevant PR checklists;
- `config/house_law_checks.yml` for the new runtime-style guard.

---

## 7. Registry law

### 7.1 Compliance is earned, not declared

A route flips to `design_system.compliant: true` only after:

- canonical reference or approved baseline exists;
- both themes pass design review;
- EN/ZH + desktop/mobile evidence exists;
- new static ratchet passes;
- runtime-style bypass is absent;
- failure states are proven;
- production/browser proof confirms the intended surface.

### 7.2 Canada first

`macro:canada_stocks` is the first stock-dashboard route to earn compliant status under this program.

The registry update belongs in the **same implementation PR that actually earns the claim**, never in this architecture PR and never before visual proof.

### 7.3 HK follower

HK follows only after Canada is accepted, using the same shared presentation grammar but its own market-native semantics:

- no LIVE quote plane unless a canonical owner later exists;
- HK sector RS-vs-HSI rank remains HK-specific;
- Southbound cues remain owner/materiality-gated;
- Canada theme-rank semantics do not bleed into HK.

Shared stylesheet does not mean shared market facts.

---

## 8. Site-wide rollout architecture

This is a sequence of independently useful verticals, not a big-bang redesign.

### TP-0 — Governance + guard foundation

**Observable capability:** future UI work can no longer introduce new dark-first runtime presentation debt invisibly.

Scope:

- runtime-style injection guard + house-law registration/CI;
- forward-only added-line design ratchet;
- durable agent instruction amendments;
- generalized visual-evidence requirement for material UI changes;
- no page repaint required.

This foundation is complete only when deliberate hostile fixtures prove each guard catches the defect class it claims to prevent.

### TP-1 — Canada first vertical

**Observable capability:** Canada Stocks V3.8 keeps its proven product semantics while becoming a deliberately designed premium light + dark surface.

Scope:

- extract substantive composer styling to `templates/stock-dashboard.css` / paired published asset;
- remove Canada runtime stylesheet injection;
- implement the approved Canada light art direction;
- preserve dark behavior and all V3.8 product contracts;
- commit full evidence matrix;
- independent design review;
- production proof;
- flip `macro:canada_stocks` compliant only on acceptance.

### TP-2 — HK follower

**Observable capability:** HK gets the same theme-quality contract and presentation-source governance without inheriting Canada-specific data semantics.

Scope:

- remove HK runtime stylesheet injection;
- consume shared stock-dashboard presentation grammar;
- explicit HK light art direction deltas;
- full evidence/proof;
- flip HK compliant only on acceptance.

### TP-3 — P0/P1 estate theme-parity census

**Observable capability:** there is a durable, current list of customer surfaces whose light plane is `GOOD`, `LIGHT_DEBT`, or `BROKEN`, with repair grouped by shared component/template family.

The census is not a second page registry. It is a dated research/evidence artifact keyed to the canonical product page registry and is disposable once the registry/repairs absorb its findings.

Priority order:

1. paid discovery/decision surfaces;
2. command center and market regime surfaces;
3. instrument analyzers/dossiers;
4. acquisition/public product surfaces;
5. long-tail research/lab pages.

Repairs occur by shared template/component family, not hand-polish × thousands.

### TP-4+ — Family convergence waves

Each wave:

- selects one shared family;
- fixes its light/dark art direction at the correct owner layer;
- removes local parallel styling where possible;
- captures evidence;
- ratchets affected registry regions compliant.

The compliant set only grows.

---

## 9. Failure states and fail-closed behavior

### Missing stylesheet

Composer does not mount; legacy page stays visible. Never hide legacy first and hope CSS arrives.

### Theme token missing

Use an existing documented fallback only where the canonical component already specifies one. Do not mint a raw literal in the consumer to make the screenshot look right.

### Evidence capture unavailable

Material UI wave is `PARTIAL/BLOCKED`, not visually accepted. Unit tests/CI may continue, but no final design acceptance is claimed.

### Light mode functionally correct but visually poor

Functional proof remains valid; visual acceptance fails. Repair the presentation layer without falsifying the functional ledger.

### Dark improvement conflicts with light improvement

Do not average both into a mediocre shared declaration. Use one semantic component with explicit theme-specific material treatments.

### New required component absent from the master design system

Stop and route a design-system primitive decision/DS-PR. Builder does not invent a page-local substitute merely to unblock itself.

### Legacy debt detected while touching an unrelated area

Report it; do not absorb unrelated estate cleanup unless the changed decision would worsen it. Forward-only ratchet blocks new debt, not every inherited defect.

---

## 10. Verification and acceptance law

A theme-parity vertical is complete only when all four proof classes pass.

### 10.1 Static/source proof

- token cleanliness;
- no substantive runtime stylesheet injection;
- no new parallel root/token family;
- stylesheet/template-site pairing correct;
- agent/house-law checks registered and wired where applicable.

### 10.2 Functional regression proof

For Canada/HK stock dashboards, preserve the full existing discriminating test suites and add tests that prove CSS extraction cannot mutate semantic behavior.

The required functional invariants include population, filtering, missing-vs-zero, owner ranks, action-vs-leadership, routes, quotes, Track Record and fail-soft legacy behavior.

### 10.3 Visual evidence proof

- required theme/lang/width screenshot matrix;
- before/after comparison for the repaired surface;
- forced state evidence where applicable;
- no horizontal page scroll at 390;
- explicit dark regression comparison;
- explicit light design review against this architecture + master design system.

### 10.4 Production proof

On the real entitled production path where required:

- correct assets loaded;
- composer mount/fallback behavior proven;
- light/dark toggle verified without remount dependency;
- critical interactions exercised;
- console clean;
- no stale asset/version mismatch;
- screenshots captured from production at relevant desktop breakpoints;
- mobile proof from a real browser/harness capable of honoring the requested viewport.

**Green CI is not this proof.**

---

## 11. Non-goals / no-rebuild boundaries

This program does **not**:

- redesign Prophet ranking, scoring, lifecycle or population;
- change Canada/HK action or leadership authority;
- create a new theme engine;
- create a new token root;
- create a second page registry;
- create a pixel-diff bot that pretends to judge taste;
- auto-normalize every historical CSS literal in one PR;
- force every dark and light pixel to have the same geometry if the material mechanism needs to differ;
- replace the existing page evidence harness;
- clone US visual semantics blindly into Canada/HK;
- reopen already-proven V3.8 product semantics merely because the presentation layer is being repaired.

The central no-rebuild rule is:

> **Extend the existing design system and evidence/registry planes; remove the bypass. Do not solve a governance gap by creating another governance plane.**

---

## 12. Review questions for this written freeze

Before implementation planning begins, the Chairman should be able to answer yes to these questions:

1. Does the architecture preserve the dark experience rather than flattening both themes into one compromise?
2. Does the light direction match the desired premium “research workspace” character rather than simple inversion?
3. Is Canada correctly the first proving vertical without turning it into the only fix?
4. Does moving substantive composer CSS into governed source close the actual escape hatch?
5. Does the ratchet avoid the opposite failure — suddenly reddening thousands of legacy pages?
6. Are future Claude/Codex/Fable sessions mechanically forced to provide theme-specific visual evidence?
7. Does the solution remain one canonical design system, not a second UI control plane?

Implementation planning and dispatch begin only after this written freeze is approved.
