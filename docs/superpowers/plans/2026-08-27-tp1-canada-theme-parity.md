# TP-1 Canada Theme-Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve every production-proven Canada V3.8 product contract while moving its presentation out of runtime JavaScript and delivering deliberately designed premium dark and light art directions.

**Architecture:** Load one governed `stock-dashboard.css` asset before the Canada composer, keep the legacy page visible until both stylesheet and composer are ready, and reduce `site/canada-stock-v36.js` to semantic DOM/state/interaction work. The first extraction uses the existing Canada class grammar under canonical root classes `mx-stockdash mx-stockdash--ca`; light receives explicit research-workspace material treatment while dark is held to a before/after regression budget.

**Tech Stack:** Vanilla JavaScript, CSS custom properties/tokens from `templates/theme.css`, paired plain-copy assets under `templates/` + `site/`, pytest source-contract tests, existing Playwright page-evidence harness, entitled production browser proof.

**Spec:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Approval:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_APPROVAL_2026-08-27.md`

**Prerequisite:** TP-0 governance merged and verified. Do not start TP-1 from the architecture branch; repin fresh `origin/main` after TP-0.

## Global Constraints

- Preserve all invariants recorded by `research/STOCK_DASHBOARD_V38_CANADA_ACCEPTANCE_2026-08-27.md` and `tests/test_canada_v36_composer.py`.
- Do not touch Prophet ranking, scoring, signal availability, lifecycle, population, Canada action authority, theme-rank authority, quote collection, entitlement/auth, Terminal routing, Track Record authority, or the two Canada data fetch contracts.
- Sector rank remains absent; theme rank remains owner-only with a visible basis.
- Missing membership remains unknown, never zero; unknown groups remain research destinations, not no-op filters.
- Top Picks / All Candidates population never changes as a side effect of leadership filtering.
- Canada LIVE quotes remain Western green-up/red-down even when the page language is Chinese.
- No substantive runtime stylesheet may remain in `site/canada-stock-v36.js`.
- New CSS must be token-clean: no raw hex/rgb/hsl, no literal font-family, no off-scale literal radius, no new root token family.
- Dark and light are separately reviewed art directions; light is not accepted because it merely renders.
- Registry compliance is earned only after real production proof; the closeout sequence below keeps that claim truthful.

---

## File Structure

**Create**
- `templates/stock-dashboard.css` — governed presentation owner for the stock-dashboard family.
- `site/stock-dashboard.css` — byte-identical published pair.
- `tests/test_stock_dashboard_css.py` — CSS boundary/token/theme contracts.
- `mockups/evidence/theme-parity/tp1-canada/` — committed harness output + full-page comparison images.

**Modify**
- `templates/dashboard-icons.js` — load `stock-dashboard.css` before entitled Canada composer; preserve bounded script retry.
- `site/dashboard-icons.js` — byte-identical pair.
- `site/canada-stock-v36.js` — remove runtime CSS injection; add canonical root classes; preserve semantic behavior.
- `tests/test_canada_v36_composer.py` — rehome hidden-style assertions to the shared CSS and pin no runtime style injection.
- `config/runtime_style_injection_allowlist.json` — Canada runtime-style budget drops to zero/removes the row.

**Post-production acceptance closeout**
- `config/product_experience/page_registry_overrides.yml` — flip `macro:canada_stocks` compliant only after proof.
- generated `data/product_experience/page_registry.json` if the repository law requires regeneration in the closeout PR.
- `research/THEME_PARITY_TP1_CANADA_ACCEPTANCE_2026-08-<proof-date>.md` — exact receipts and visual acceptance.

---

### Task 1: Freeze the functional and presentation-source regression tests before extraction

**Files:**
- Modify: `tests/test_canada_v36_composer.py`
- Create: `tests/test_stock_dashboard_css.py`

**Interfaces:**
- Consumes: current Canada V3.8 composer and future `templates/stock-dashboard.css`.
- Produces: tests that distinguish semantic JavaScript from presentation CSS and prevent the extraction from deleting load-bearing visibility contracts.

- [ ] **Step 1: Move the hidden-override ownership assertion to the future stylesheet test**

Create `tests/test_stock_dashboard_css.py`:

```python
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "templates" / "stock-dashboard.css"

REQUIRED_CANADA_VISIBILITY = (
    ".mx-stockdash--ca .ca-v36-card-grid[hidden]",
    ".mx-stockdash--ca .ca-v36-card-grid .pvcard[hidden]",
    ".mx-stockdash--ca .ca-v36-card-grid .sm-hidden",
)


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def test_canada_hidden_and_legacy_show_more_rescue_live_in_governed_css() -> None:
    text = _css()
    for selector in REQUIRED_CANADA_VISIBILITY:
        assert selector in text
    assert "display:none!important" in text
    assert "display:flex!important" in text
```

Do not delete the existing semantic test `test_composer_still_hides_via_hidden_attribute()`; it proves the CSS contract still corresponds to the JavaScript hide mechanism.

- [ ] **Step 2: Add a failing test that forbids a Canada-owned runtime stylesheet**

Add to `tests/test_canada_v36_composer.py`:

```python
def test_v39_composer_contains_no_runtime_stylesheet_system() -> None:
    text = _composer_text()
    assert 'createElement("style")' not in text
    assert "style.textContent" not in text
    assert "css.textContent" not in text
    assert "function injectCss" not in text
```

- [ ] **Step 3: Add a failing test for canonical root classes**

```python
def test_v39_mount_uses_canonical_stock_dashboard_root_classes() -> None:
    text = _composer_text()
    assert 'mx-stockdash' in text
    assert 'mx-stockdash--ca' in text
```

- [ ] **Step 4: Add a failing loader-order test**

The test reads `templates/dashboard-icons.js`, slices the Canada loader block, and asserts the stylesheet owner is requested before `canada-stock-v36.js` can be injected:

```python
def test_loader_requires_shared_css_before_canada_composer() -> None:
    text = LOADER.read_text(encoding="utf-8")
    start = text.index("__mmCanadaStockV36Loader")
    block = text[start:]
    assert "stock-dashboard.css" in block
    assert block.index("stock-dashboard.css") < block.index("canada-stock-v36.js")
    assert "link.onload" in block
    assert "link.onerror" in block
```

- [ ] **Step 5: Run the focused tests and verify the new assertions fail**

```bash
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
```

Expected: pre-existing Canada semantic tests pass; the new stylesheet/root/no-injection/loader-order tests fail because TP-1 has not been implemented.

- [ ] **Step 6: Commit the red tests**

```bash
git add tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py
git commit -m "test(canada): freeze theme-parity extraction contracts"
```

---

### Task 2: Gate composer loading on the governed stylesheet

**Files:**
- Modify: `templates/dashboard-icons.js`
- Modify: `site/dashboard-icons.js`

**Interfaces:**
- Consumes: public `stock-dashboard.css`; entitled `canada-stock-v36.js`.
- Produces: `ensureStockDashCss(onReady)` that invokes the composer loader only after CSS `load`; CSS error leaves the legacy page untouched.

- [ ] **Step 1: Implement one idempotent stylesheet loader adjacent to the Canada/HK composer loader region**

Use this contract:

```javascript
function ensureStockDashCss(onReady) {
  var id = "mx-stockdash-css";
  var existing = document.getElementById(id);
  if (existing && existing.getAttribute("data-ready") === "1") {
    onReady();
    return;
  }
  if (existing) {
    existing.addEventListener("load", onReady, { once: true });
    return;
  }
  var link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = "stock-dashboard.css?v=tp1";
  link.onload = function () {
    link.setAttribute("data-ready", "1");
    onReady();
  };
  link.onerror = function () {
    // Fail soft: do not inject a composer without its governed presentation.
  };
  document.head.appendChild(link);
}
```

At execution, replace the temporary `v=tp1` stamp with the repository's normal asset-stamp value/hash procedure; the filename and load-order contract are fixed.

- [ ] **Step 2: Wrap the existing Canada script retry in `ensureStockDashCss(inject)`**

Preserve exactly:

- `window.__mmCanadaStockV36Loader` idempotency;
- `attempt < 3` bounded retries;
- `!window.__mmCanadaStockV36` no-reinject guard;
- existing entitled-script error behavior.

Do not make stylesheet retries hide the legacy page; a stylesheet failure simply means the composer never starts.

- [ ] **Step 3: Sync the paired dashboard-icons asset**

```bash
python3 -m scripts.check_template_site_sync --fix
python3 -m scripts.check_template_site_sync
```

Expected: `templates/dashboard-icons.js` and `site/dashboard-icons.js` byte-identical.

- [ ] **Step 4: Run the loader tests**

```bash
python3 -m pytest tests/test_canada_v36_composer.py::test_loader_retries_transient_entitled_fetch_failures tests/test_canada_v36_composer.py::test_loader_requires_shared_css_before_canada_composer -q
```

Expected: pass after the future stylesheet file exists in Task 3; until then only the source-order assertion can pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add templates/dashboard-icons.js site/dashboard-icons.js
git commit -m "feat(stockdash): gate Canada composer on governed CSS"
```

---

### Task 3: Extract all Canada presentation CSS into the governed paired asset

**Files:**
- Create: `templates/stock-dashboard.css`
- Create: `site/stock-dashboard.css`
- Modify: `site/canada-stock-v36.js`
- Modify: `config/runtime_style_injection_allowlist.json`
- Modify: `tests/test_stock_dashboard_css.py`

**Interfaces:**
- Consumes: the exact declaration inventory currently emitted by `injectCss()` in `site/canada-stock-v36.js`.
- Produces: canonical stylesheet root `.mx-stockdash`, market root `.mx-stockdash--ca`, zero Canada runtime style injection.

- [ ] **Step 1: Create the stylesheet with the full current selector inventory, token-cleaned**

Move every family currently owned by `injectCss()` into `templates/stock-dashboard.css`; do not drop a family during extraction. Required families are:

1. root/page shell, head, Board/LIVE chips;
2. section shell/header and fresh cue;
3. What To Act On Now mobile segmented control, four lanes, lane headers, rows, counts, routes, empty rows, View all;
4. Leadership & Rotation columns/rows/rank/name/leaders/stance/count/basis;
5. Prophet population/view controls, result/filter chips, card grid and card typography overrides;
6. hidden-attribute contracts and `.sm-hidden` rescue;
7. table host/live quote overrides and filtered rows;
8. Research Tools;
9. Evidence & Record moved `.trk` host;
10. modal/scrim/card/table/close control;
11. breakpoints at the current 1200/900/680 boundaries.

Root the component:

```css
.mx-stockdash {
  box-sizing: border-box;
  color: var(--text);
  font-family: var(--font-ui);
}
.mx-stockdash *,
.mx-stockdash *::before,
.mx-stockdash *::after { box-sizing: border-box; }
```

Use radius tokens instead of the current literals:

```css
/* controls */ border-radius: var(--r-ctl);
/* cards/lanes */ border-radius: var(--r-card);
/* top-level modules/modals */ border-radius: var(--r-panel);
/* pills */ border-radius: var(--r-pill);
```

Use `var(--card-shadow)`, `var(--shadow-hover)`, and `var(--popover-shadow)` instead of `rgba(...)` shadow literals. Use `color-mix(...)` only as a property value, never to mint a new literal-valued root token.

- [ ] **Step 2: Preserve Canada action hue semantics with stance tokens rather than raw market-direction paint**

Use the existing Prophet verb family for action lanes/chips:

```css
.mx-stockdash--ca .ca-v36-an-hd.buy,
.mx-stockdash--ca .ca-v36-stance.buy { color: var(--ink-pv-buy, var(--pv-buy)); }
.mx-stockdash--ca .ca-v36-an-hd.near,
.mx-stockdash--ca .ca-v36-stance.near { color: var(--ink-pv-near, var(--pv-near)); }
.mx-stockdash--ca .ca-v36-an-hd.wait,
.mx-stockdash--ca .ca-v36-stance.wait { color: var(--ink-pv-wait, var(--pv-wait)); }
.mx-stockdash--ca .ca-v36-an-hd.avoid,
.mx-stockdash--ca .ca-v36-stance.avoid { color: var(--ink-pv-avoid, var(--pv-avoid)); }
```

Do **not** change `.nb-chg.up/.down` Canada quote convention; the LIVE tape remains Western green-up/red-down under EN and ZH.

- [ ] **Step 3: Remove the runtime stylesheet system from the composer**

Delete:

- `FONT_UI` if it has no non-style consumer;
- `injectCss()`;
- `document.createElement("style")` / `css.textContent` / `document.head.appendChild(css)`;
- the mount-path `injectCss()` call.

When building the composed shell, set the root class to include:

```javascript
main.className = "ca-v36 mx-stockdash mx-stockdash--ca";
```

Do not rename the existing child classes in this wave; they are stable migration-compatible hooks under the canonical root.

- [ ] **Step 4: Publish the CSS pair and ratchet Canada runtime injection budget to zero**

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 scripts/check_runtime_style_injection.py
```

Remove the Canada allowance row/counts that are now zero; do not leave stale budget behind.

- [ ] **Step 5: Make `tests/test_stock_dashboard_css.py` prove token cleanliness on the new asset**

Add:

```python
def test_stock_dashboard_css_uses_no_raw_colour_font_or_radius_literals() -> None:
    findings = DS.scan_text("templates/stock-dashboard.css", _css())
    blocked = {
        "color-literal", "font-family-literal", "radius-literal",
        "literal-custom-property", "parallel-token-root", "emoji",
    }
    assert not [f for f in findings if f.rule in blocked]
```

Import `scripts.check_design_system as DS` using the repository's established test import pattern.

- [ ] **Step 6: Run extraction tests**

```bash
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
python3 scripts/check_runtime_style_injection.py
python3 -m scripts.check_template_site_sync
node --check site/canada-stock-v36.js
```

Expected: all green; Canada no longer appears as runtime-style debt.

- [ ] **Step 7: Commit Task 3**

```bash
git add templates/stock-dashboard.css site/stock-dashboard.css site/canada-stock-v36.js config/runtime_style_injection_allowlist.json tests/test_stock_dashboard_css.py
git commit -m "refactor(canada): move stock-dashboard presentation into governed CSS"
```

---

### Task 4: Implement the Canada light research-workspace art direction without flattening dark

**Files:**
- Modify: `templates/stock-dashboard.css`
- Modify: `site/stock-dashboard.css`
- Modify: `tests/test_stock_dashboard_css.py`

**Interfaces:**
- Consumes: extracted semantic selectors from Task 3.
- Produces: explicit `html[data-theme="light"] .mx-stockdash--ca ...` material rules; dark continues to use the base/dark treatment.

- [ ] **Step 1: Give top-level light modules a white-material hierarchy**

Use token-driven rules:

```css
html[data-theme="light"] .mx-stockdash--ca .ca-v36-sec {
  background: var(--panel);
  border-color: var(--line);
  box-shadow: var(--card-shadow);
}

html[data-theme="light"] .mx-stockdash--ca .ca-v36-sec-hd {
  background: var(--panel);
  border-bottom-color: var(--line);
}
```

The page canvas remains `var(--bg)`; do not paint the entire shell white.

- [ ] **Step 2: Redesign Act-Now as one instrument with four restrained lanes**

Light lanes are neutral materials, not four grey mini-panels:

```css
html[data-theme="light"] .mx-stockdash--ca .ca-v36-an-lane {
  background: var(--panel);
  border-color: var(--line);
  box-shadow: none;
}
html[data-theme="light"] .mx-stockdash--ca .ca-v36-an-row-w + .ca-v36-an-row-w {
  border-top: 1px solid var(--line);
}
html[data-theme="light"] .mx-stockdash--ca .ca-v36-an-row {
  background: transparent;
}
```

Give each header a narrow semantic top rail and quiet tint using the stance tokens; for example:

```css
html[data-theme="light"] .mx-stockdash--ca .ca-v36-an-hd.buy {
  border-top: 2px solid var(--pv-buy);
  background: color-mix(in srgb, var(--pv-buy) 4%, var(--panel));
}
```

Repeat explicitly for `near`, `wait`, and `avoid` with `--pv-near`, `--pv-wait`, `--pv-avoid`; no generic decorative hues.

`View all` remains a flat/quiet footer control with a separator, not a nested raised card.

- [ ] **Step 3: Give light Prophet Top Picks material elevation instead of glow**

```css
html[data-theme="light"] .mx-stockdash--ca .ca-v36-card-grid .ca-v36-top-pick {
  background: var(--panel);
  border-color: color-mix(in srgb, var(--link) 18%, var(--line));
  box-shadow: var(--card-shadow);
}
```

Do not add a luminous halo. Preserve the existing canonical Prophet card state colors.

- [ ] **Step 4: Make light Leadership read as a ranked institutional list**

Use one material surface, row separators, and a quiet hover wash. Do not wrap every row in another card. Keep `Theme #N`, stance, leaders, and count visually separate. A selected row may use a 2–3px wayfinding rail plus a low-alpha `--link` tint; it may not flood the row with saturated color.

- [ ] **Step 5: Make segmented controls legible in light through material contrast**

```css
html[data-theme="light"] .mx-stockdash--ca .ca-v36-seg {
  background: var(--panel2);
  border-color: var(--line);
}
html[data-theme="light"] .mx-stockdash--ca .ca-v36-seg button[aria-selected="true"] {
  background: var(--panel);
  border-color: var(--line);
  box-shadow: var(--card-shadow);
}
```

- [ ] **Step 6: Replace modal literal scrims/shadows with theme-specific token composition**

```css
.mx-stockdash--ca .ca-v36-modal {
  background: color-mix(in srgb, var(--bg) 72%, transparent);
  backdrop-filter: blur(8px);
}
.mx-stockdash--ca .ca-v36-modal-card { box-shadow: var(--popover-shadow); }
html[data-theme="light"] .mx-stockdash--ca .ca-v36-modal {
  background: color-mix(in srgb, var(--text) 16%, transparent);
}
html[data-theme="light"] .mx-stockdash--ca .ca-v36-modal-pane {
  background: var(--panel);
}
```

- [ ] **Step 7: Add structural tests for explicit light treatment**

```python
def test_canada_has_explicit_light_material_rules() -> None:
    text = _css()
    anchor = 'html[data-theme="light"] .mx-stockdash--ca'
    assert text.count(anchor) >= 6
    assert ".ca-v36-an-lane" in text
    assert ".ca-v36-card-grid .ca-v36-top-pick" in text
    assert ".ca-v36-seg button[aria-selected" in text
    assert ".ca-v36-modal" in text
```

This is a presence fence, not aesthetic acceptance; screenshots/review remain binding.

- [ ] **Step 8: Sync and run tests**

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
```

- [ ] **Step 9: Commit Task 4**

```bash
git add templates/stock-dashboard.css site/stock-dashboard.css tests/test_stock_dashboard_css.py
git commit -m "design(canada): give light mode a research-workspace art direction"
```

---

### Task 5: Capture and commit the full dual-theme evidence matrix

**Files:**
- Create/modify under: `mockups/evidence/theme-parity/tp1-canada/`

**Interfaces:**
- Consumes: existing `scripts/capture_page_evidence.py` manifest/screenshot schema; local real `site/` output.
- Produces: committed evidence using the existing page-evidence plane, not a new screenshot truth store.

- [ ] **Step 1: Capture the exact 8-cell matrix with the existing harness**

From a full checkout with Playwright available:

```bash
python3 scripts/capture_page_evidence.py \
  --site-dir site \
  --routes /canada_stocks.html \
  --viewports desktop,mobile \
  --locales en,zh \
  --themes dark,light \
  --max-pages 1 \
  --output-dir mockups/evidence/theme-parity/tp1-canada/cells \
  --manifest mockups/evidence/theme-parity/tp1-canada/manifest.json \
  --smells mockups/evidence/theme-parity/tp1-canada/ux-smells.json \
  --as-of 2026-08-27T00:00:00Z
```

If the implementation date changes, use the real capture date consistently in `--as-of` and the acceptance record; do not backdate evidence.

- [ ] **Step 2: Capture explicit before/after overview comparisons**

Use the pre-TP-1 production/baseline commit in a second checkout and the same 1440 viewport. Store:

- `before-dark-en-1440.png`
- `after-dark-en-1440.png`
- `before-light-en-1440.png`
- `after-light-en-1440.png`
- `fullpage-dark-en-1440.png`
- `fullpage-light-en-1440.png`

All belong under `mockups/evidence/theme-parity/tp1-canada/`.

- [ ] **Step 3: Verify evidence honesty**

Check manifest rows report requested `applied_theme`/`applied_locale` correctly and no cell silently fell back. Confirm 390 mobile has no horizontal page overflow through the harness/real browser. The entitled production script is not required for committed local evidence because `site/canada-stock-v36.js` is present in the local static tree; state this provenance in the PR.

- [ ] **Step 4: Run the TP-0 visual-evidence guard against the real PR diff**

```bash
git diff --unified=0 origin/main...HEAD -- templates site > /tmp/tp1-ui.diff
python3 scripts/check_ui_visual_evidence.py --diff-file /tmp/tp1-ui.diff
```

Expected: green with the existing harness manifest/evidence files.

- [ ] **Step 5: Commit evidence**

```bash
git add mockups/evidence/theme-parity/tp1-canada/
git commit -m "evidence(canada): commit dark-light theme parity matrix"
```

---

### Task 6: Run independent functional + design review before merge

**Files:** no new code required unless findings are repaired.

**Interfaces:**
- Consumes: exact PR head, TP-1 spec, V3.8 acceptance, committed evidence.
- Produces: independent reviewer verdict; repairs stay on the same carrier.

- [ ] **Step 1: Run the full Canada regression set and governance gates**

```bash
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
python3 scripts/check_runtime_style_injection.py
python3 -m scripts.check_template_site_sync
node --check site/canada-stock-v36.js
node --check templates/dashboard-icons.js
```

Also run every current CI-owned stock-dashboard/Prophet shared-card test selected by `scripts/run_ci_pack.py --changed-from origin/main --dry-run`; do not substitute a hand-picked subset if the pack owns more.

- [ ] **Step 2: Commission an independent Opus design review**

Review standard must explicitly include:

- light research-workspace hierarchy;
- dark regression comparison;
- Act-Now four-lane composition;
- Prophet Top Pick treatment;
- Leadership material hierarchy;
- controls/modal;
- EN/ZH desktop/mobile evidence;
- no semantic-color misuse;
- no runtime stylesheet bypass.

A reviewer that only reads CSS is insufficient; it must inspect the committed shots.

- [ ] **Step 3: Commission an independent functional/adversarial review**

Attack the exact V3.8 invariants: action ≠ leadership, no sector rank, owner-only theme rank, missing ≠ zero, Top Picks preservation, table/grid, LIVE quote plane, Track Record, routes, fetch set, fail-soft legacy fallback.

- [ ] **Step 4: Repair findings on the same branch and recapture any screenshot whose rendered bytes changed**

Do not keep stale visual evidence after CSS/markup repairs.

- [ ] **Step 5: Wait for binding CI to conclude on the exact repaired head**

Green CI is necessary, not final acceptance.

---

### Task 7: Merge, prove the entitled production path, then earn registry compliance

**Files:**
- Post-proof create: `research/THEME_PARITY_TP1_CANADA_ACCEPTANCE_2026-08-<proof-date>.md`
- Post-proof modify: `config/product_experience/page_registry_overrides.yml`
- Regenerate: `data/product_experience/page_registry.json` when required by the canonical builder.

**Interfaces:**
- Consumes: merged TP-1 implementation SHA and real entitled production page.
- Produces: production proof plus truthful registry compliance in a small records/registry closeout after proof.

**Architecture-law clarification:** A route cannot truthfully be marked compliant *before* the real production proof that the architecture requires. Therefore TP-1 uses two commits/PR carriers for truth: the implementation PR merges with the route still non-compliant; after real proof, a records/registry closeout flips the canonical claim. This preserves the approved intent “compliance is earned, not declared” and must be recorded as the TP implementation amendment rather than silently claiming pre-merge production proof.

- [ ] **Step 1: Merge only after exact-head CI + both independent reviews are clean**

Use the repository's normal merge discipline; no admin merge to outrun pending checks.

- [ ] **Step 2: Verify deployment bytes and asset ordering**

On production, prove:

1. `stock-dashboard.css` returns successfully;
2. Canada composer loads only after stylesheet readiness;
3. stylesheet failure simulation/local harness leaves legacy visible;
4. composer asset is the expected merged bytes/version;
5. no stale old runtime-style code is served.

- [ ] **Step 3: Execute the entitled production journey in both themes**

At desktop and a real 390-capable viewport, verify:

- mount/order: Header → What To Act On Now → Prophet → Leadership & Rotation → Evidence → Research;
- Act-Now caps/View all/empty lane;
- Top Picks and All Candidates;
- sector/theme filters preserve population;
- Grid/Table XOR;
- LIVE quote cells and dates;
- Track Record dialog;
- Terminal routing;
- modal;
- EN/ZH;
- light/dark toggles without composer remount;
- console zero errors;
- no horizontal overflow.

Capture production desktop screenshots in both themes and include them in the acceptance record.

- [ ] **Step 4: If production proof fails, keep `macro:canada_stocks` non-compliant and repair the implementation**

Do not falsify the registry to match the intended result.

- [ ] **Step 5: If production proof passes, create the records/registry closeout**

Update the `macro:canada_stocks` row:

```yaml
  macro:canada_stocks:
    archetype: "discovery_board"
    design_system:
      compliant: true
      governed_regions:
        - {template: templates/canada.html.j2, region: body.page-canada}
        - {template: templates/stock-dashboard.css, region: .mx-stockdash--ca}
      migrated_pr: <the actual merged TP-1 implementation PR number>
      evidence: mockups/evidence/theme-parity/tp1-canada/manifest.json
```

When implementing, replace the PR-number scalar with the actual merged PR number; do not invent it during planning.

Regenerate the registry with its canonical builder and validate the design-system checker in full `--mode enforce` against the newly governed CSS region/template ownership.

- [ ] **Step 6: Write the acceptance record with exact receipts**

Record implementation PR/head/merge, CI run, stylesheet/composer hashes, production URL/time, production screenshots, dark/light review, mobile proof, and any residual. State Canada theme parity `PROVEN_LIVE` only if all are clean.

- [ ] **Step 7: Merge the closeout and stop TP-1**

TP-2 may start only after the Canada compliance/acceptance closeout is canonical.

---

## TP-1 Acceptance

TP-1 is complete only when:

- Canada composer owns no substantive CSS at runtime;
- `stock-dashboard.css` is governed/token-clean and paired to `site/`;
- CSS failure preserves the legacy page;
- the full existing V3.8 semantic suite remains green;
- committed dark/light × EN/ZH × desktop/mobile evidence exists;
- an independent design reviewer explicitly accepts light and dark;
- entitled production proof passes;
- `macro:canada_stocks` flips compliant only after that proof;
- the runtime-style allowlist has no stale Canada exemption.

**Stop condition:** Do not absorb HK into the Canada implementation PR. Return exact acceptance/registry receipts, then start TP-2 fresh from main.
