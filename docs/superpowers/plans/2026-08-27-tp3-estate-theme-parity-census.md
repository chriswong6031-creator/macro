# TP-3 P0/P1 Estate Theme-Parity Census Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a durable, evidence-backed census of customer-facing P0/P1 surfaces classified `GOOD`, `LIGHT_DEBT`, or `BROKEN`, then group the defects into shared component/template families for TP-4+ convergence waves.

**Architecture:** Use the canonical product page registry as the route/identity source and the existing page-evidence/light-sweep tooling as the screenshot source. The census is a dated research artifact, not a second registry: it may classify and prioritize, but canonical page identity/archetype/compliance continues to live in the product page registry. Human/Opus design judgment assigns the visual class; scripts only capture/organize evidence.

**Tech Stack:** `data/product_experience/page_registry.json`, `scripts/capture_page_evidence.py`, `scripts/light_mode_sweep.py`, Playwright/Chromium, optional Pillow pair composites, Markdown research artifact.

**Spec:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Prerequisites:** TP-1 Canada and TP-2 HK are accepted `PROVEN_LIVE` theme-parity references and their registry compliance closeouts are canonical.

## Global Constraints

- The census must not create a new authoritative page registry, score, design grade, or automated taste model.
- `GOOD`, `LIGHT_DEBT`, and `BROKEN` are temporary census review classes defined by the approved architecture, not product/financial scores.
- Every census row keys to the canonical `page_id`; route/title strings alone are not identity.
- Canada/HK reference implementations are examples of the design law, not mandatory semantic clones.
- No page code is modified in TP-3. A census finding creates a bounded TP-4+ family wave; it does not trigger opportunistic repainting inside the census PR.
- Preserve access honesty: anonymous production capture cannot prove authenticated paid states. Use local committed output or approved fixtures for layout evidence and record access gaps explicitly.
- Do not call a page `GOOD` solely because no automated smell fired. A human/Opus reviewer must inspect light and dark side by side.

---

## File Structure

**Create**
- `research/THEME_PARITY_ESTATE_CENSUS_2026-09.md` — canonical dated census/recommendation artifact for this wave.
- `mockups/evidence/theme-parity/tp3-census/` — bounded evidence/contact sheets for reviewed P0/P1 pages; use page-id-safe slugs.

**Read only**
- `data/product_experience/page_registry.json`
- `config/product_experience/page_registry_overrides.yml`
- `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`
- `docs/DESIGN_DOCTRINE.md`
- `research/DESIGN_MIGRATION_FACTORY_V1.md`
- `scripts/capture_page_evidence.py`
- `scripts/light_mode_sweep.py`

---

### Task 1: Freeze the exact census population from the canonical page registry

**Files:**
- Create draft: `research/THEME_PARITY_ESTATE_CENSUS_2026-09.md`

**Interfaces:**
- Consumes: `mastermind.page_registry.v1` rows.
- Produces: explicit included/excluded page-id list with reasons before visual judgment begins.

- [ ] **Step 1: Rebuild/validate the page registry at fresh main**

Use the repository's current canonical builder command from `config/product_experience/page_registry_overrides.yml`; on the planning base it is:

```bash
python3 scripts/build_product_page_registry.py --as-of "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Do not commit a regenerated registry if fresh main is already canonical and byte-equivalent.

- [ ] **Step 2: Extract the P0/P1 page population deterministically**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('data/product_experience/page_registry.json').read_text())
rows = p.get('pages', [])
for r in sorted(rows, key=lambda x: (str(x.get('priority')), str(x.get('page_id')))):
    if r.get('priority') not in {'P0', 'P1'}:
        continue
    print('\t'.join([
        str(r.get('page_id')),
        str(r.get('priority')),
        str(r.get('route_kind')),
        str(r.get('route')),
        str(r.get('archetype')),
        str((r.get('design_system') or {}).get('compliant', False)),
    ]))
PY
```

- [ ] **Step 3: Record exclusions before capture**

A row is excluded from direct capture only when one of these is true:

- `route_kind: family` and no concrete exemplar route exists;
- route is deliberately non-browser/internal;
- the file/route no longer exists, which is a registry defect to report separately rather than silently omit.

Authenticated pages are **not excluded**: local committed `site/` output may be used for visual composition evidence while production access remains an explicit gap.

- [ ] **Step 4: Create the census header/population tables**

Start `research/THEME_PARITY_ESTATE_CENSUS_2026-09.md` with:

```markdown
# Theme-Parity Estate Census — 2026-09

Status: REVIEW ARTIFACT — keyed to canonical product page registry; not a second registry.
Registry source SHA: `<fresh-main SHA>`
Reference examples: Canada Stocks TP-1 acceptance; HK Stocks TP-2 acceptance.

## Population
| page_id | priority | archetype | route | capture basis | review state |
|---|---|---|---|---|---|
```

At execution, replace the source-SHA scalar with the actual fresh-main SHA and fill the rows from Step 2; do not invent page ids from memory.

- [ ] **Step 5: Commit the population freeze alone**

```bash
git add research/THEME_PARITY_ESTATE_CENSUS_2026-09.md
git commit -m "research(design): freeze P0/P1 theme-parity census population"
```

---

### Task 2: Capture dark/light desktop evidence for every capturable census page

**Files:**
- Create under: `mockups/evidence/theme-parity/tp3-census/`

**Interfaces:**
- Consumes: frozen route list from Task 1.
- Produces: side-by-side dark/light evidence; no classification yet.

- [ ] **Step 1: Build a comma-separated explicit route set from the frozen census**

Use registry routes, not hand-written names. For local pages, route paths must resolve under `site/`.

- [ ] **Step 2: Run the existing evidence harness for dark/light EN desktop**

For batches small enough to remain reviewable:

```bash
python3 scripts/capture_page_evidence.py \
  --site-dir site \
  --routes /route-a.html,/route-b.html \
  --viewports desktop \
  --locales en \
  --themes dark,light \
  --output-dir mockups/evidence/theme-parity/tp3-census/cells \
  --manifest mockups/evidence/theme-parity/tp3-census/manifest.json \
  --smells mockups/evidence/theme-parity/tp3-census/ux-smells.json
```

If the harness's single manifest overwrites rather than appends across batches on fresh main, capture the complete route set in one bounded run instead of stitching manifests by hand.

- [ ] **Step 3: Generate pair composites for human review without changing source screenshots**

Use `scripts/light_mode_sweep.py --pairs` when the page is a simple committed `site/<name>.html` route; otherwise use Pillow to place the two existing harness screenshots side by side. Pair composites live under `mockups/evidence/theme-parity/tp3-census/pairs/`.

The pair is a convenience; the original dark/light screenshots remain the evidence.

- [ ] **Step 4: Record capture failures/gaps in the census**

Do not delete a row because it 404s, times out, requires auth, ignores theme selection, or lacks a concrete family exemplar. Record the exact gap and source.

- [ ] **Step 5: Commit capture evidence before judgment**

```bash
git add mockups/evidence/theme-parity/tp3-census/ research/THEME_PARITY_ESTATE_CENSUS_2026-09.md
git commit -m "evidence(design): capture P0/P1 dark-light census pairs"
```

---

### Task 3: Run an independent design review and assign the census classes

**Files:**
- Modify: `research/THEME_PARITY_ESTATE_CENSUS_2026-09.md`

**Interfaces:**
- Consumes: exact dark/light pair evidence, Master Product Design System, doctrine.
- Produces: per-page `GOOD` / `LIGHT_DEBT` / `BROKEN` plus reason codes and family owner.

- [ ] **Step 1: Use one explicit classification law**

```text
GOOD:
  Light and dark are both deliberate art directions; hierarchy/material/controls remain premium.

LIGHT_DEBT:
  Light is usable and not misleading, but materially weaker than dark or the design constitution;
  repair should occur in the owning shared family.

BROKEN:
  Light materially collapses hierarchy/legibility/interaction meaning, looks like a palette
  translation rather than a designed product, or creates a visual defect that should block a
  flagship acceptance today.
```

- [ ] **Step 2: Use bounded reason codes, not freeform-only taste prose**

Allowed reason codes:

- `flat_material_hierarchy`
- `nested_grey_boxing`
- `dark_glow_translation`
- `accent_smear`
- `border_noise`
- `selected_state_weak`
- `contrast_legibility`
- `white_on_white_loss`
- `modal_scrim_muddy`
- `chart_light_mismatch`
- `mobile_density`
- `zh_layout_parity`
- `theme_ignored`
- `reference_drift`
- `other` (requires a one-sentence explanation)

- [ ] **Step 3: Require the independent reviewer to inspect every pair**

The reviewer returns for every included page:

```text
page_id
class = GOOD | LIGHT_DEBT | BROKEN
reason_codes = [...]
owning_family = <source template/component family>
one-sentence evidence-grounded rationale
```

No automated smell metric may assign the class.

- [ ] **Step 4: Add the adjudication columns to the census**

Final per-page table shape:

```markdown
| page_id | priority | archetype | route | class | reason codes | owning family | evidence | rationale |
```

- [ ] **Step 5: Adversarially re-review every `GOOD` P0 page**

A second reviewer or Sol spot-checks all `GOOD` P0 rows to reduce false-green classification. Any disagreement is recorded and resolved; do not average to a score.

- [ ] **Step 6: Commit the classification**

```bash
git add research/THEME_PARITY_ESTATE_CENSUS_2026-09.md
git commit -m "research(design): adjudicate P0/P1 theme parity"
```

---

### Task 4: Group defects into TP-4+ shared-family repair waves

**Files:**
- Modify: `research/THEME_PARITY_ESTATE_CENSUS_2026-09.md`

**Interfaces:**
- Consumes: page classifications and canonical source-template/component ownership.
- Produces: ordered family backlog where one repair can improve multiple routes.

- [ ] **Step 1: Group by actual owner, not visual resemblance**

Use `source_template`, shared partial/asset, or canonical component owner. Examples of valid family keys are `templates/dashboard.html.j2`, `templates/theme.css` component family, a specific shared stock-dashboard stylesheet, or a shared dossier template. “Grey cards” is not an owner.

- [ ] **Step 2: Rank families by customer reach and severity**

Order lexically by this decision rule, not a fake numeric score:

1. any family containing a `BROKEN` P0 paid decision/discovery surface;
2. other `BROKEN` P0;
3. `LIGHT_DEBT` P0 paid decision/discovery;
4. remaining `LIGHT_DEBT` P0;
5. P1 in the same order;
6. `GOOD` families need no repair wave.

- [ ] **Step 3: Write one bounded candidate mission per family**

Each candidate mission names:

- observable capability;
- owning source paths;
- affected page ids;
- top reason codes;
- whether the repair is component-level or page-family-level;
- exact non-goals;
- evidence owed before the family can ratchet compliant.

Do not write implementation code in TP-3.

- [ ] **Step 4: Identify the exact next TP-4 wave**

The census ends with:

```markdown
## Exact next action
Family: <actual highest-priority owner from the completed census>
Affected page_ids: [...]
Mission: <one observable theme-parity repair>
Held: every other family
Return to Sol if: owner collision, missing canonical reference, or repair would require a new design-system primitive.
```

The values are filled from the completed census, not guessed in this plan.

- [ ] **Step 5: Commit the family backlog**

```bash
git add research/THEME_PARITY_ESTATE_CENSUS_2026-09.md
git commit -m "research(design): freeze theme-parity family repair backlog"
```

---

### Task 5: Verify the census remains research evidence rather than a duplicate registry

**Files:** no new files unless findings require documentation repair.

- [ ] **Step 1: Confirm every census row maps to an existing page-registry id**

Run a small Python assertion that the set of census `page_id` values is a subset of the canonical registry set. Do not add missing ids to the census as invented records; repair the registry through its owner if a real page is missing.

- [ ] **Step 2: Confirm no code consumes the census as runtime authority**

```bash
git grep -n "THEME_PARITY_ESTATE_CENSUS_2026-09" -- ':!research/THEME_PARITY_ESTATE_CENSUS_2026-09.md'
```

Expected: no runtime/config/engine consumer.

- [ ] **Step 3: Run applicable evidence/house-law validation**

```bash
python3 scripts/check_house_law_registry.py
python3 scripts/check_reference_integrity.py --help >/dev/null
```

Use Reference Integrity only if the census wave creates or promotes a canonical reference; the census itself is evidence/review, not automatically a reference approval.

- [ ] **Step 4: Final independent review of the next-wave recommendation**

Reviewer attacks whether the chosen family actually owns the defect, whether the census class is supported by the screenshots, and whether a shared repair would accidentally widen scope across unrelated pages.

---

## TP-3 Acceptance

TP-3 is complete when:

- the exact P0/P1 population/exclusions are frozen from the canonical page registry;
- every capturable included page has dark/light evidence or an explicit capture gap;
- every row has independent human/Opus classification and reason codes;
- all P0 `GOOD` rows receive a second false-green check;
- defects are grouped by actual shared owner;
- one exact TP-4 family wave is selected;
- no code/runtime/config layer treats the census as a second registry.

**Stop condition:** TP-3 makes no page presentation changes. It stops after the evidence-backed family backlog and exact TP-4 mission are reviewed and committed.
