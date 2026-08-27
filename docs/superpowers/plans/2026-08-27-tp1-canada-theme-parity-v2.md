# TP-1 Canada Theme-Parity Implementation Plan — V2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every production-proven Canada V3.8 product contract intact while eliminating its runtime CSS system and delivering deliberate premium dark and light treatments from one governed presentation asset.

**Architecture:** `templates/stock-dashboard.css` becomes the presentation owner, paired byte-for-byte to `site/stock-dashboard.css`. `templates/dashboard-icons.js` loads that stylesheet before it attempts the entitled Canada composer. `site/canada-stock-v36.js` continues to own semantic composition/state/interaction only and mounts under `mx-stockdash mx-stockdash--ca`. The light plane is explicitly redesigned as a research workspace; the dark plane is protected by before/after evidence and regression review.

**Tech Stack:** Vanilla JS, canonical CSS tokens from `templates/theme.css`, paired plain-copy assets, pytest, existing `mastermind.p0_evidence.v2` page-evidence harness, real entitled production browser proof.

**Spec:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Implementation amendment:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_IMPLEMENTATION_AMENDMENT_1.md`

**Prerequisite:** TP-0 V2 merged and verified. Start from fresh `origin/main`, not the architecture branch.

## Global Constraints

- Preserve `research/STOCK_DASHBOARD_V38_CANADA_ACCEPTANCE_2026-08-27.md` and every discriminating assertion in `tests/test_canada_v36_composer.py` unless a fresh canonical source explicitly supersedes one.
- Never change Prophet rank/score/population/lifecycle, Action Timing ≠ Leadership law, sector no-rank law, owner-only theme rank, missing≠zero, Top Picks population behavior, Grid/Table XOR, `.sm-hidden` rescue, LIVE quote authority, Track Record, Terminal routing, entitlement, or the two Canada artifact fetches.
- Canada quote colors remain Western green-up/red-down even under ZH.
- No substantive `createElement("style")`/`textContent` stylesheet system may remain in the Canada composer.
- New stylesheet decisions must pass TP-0 design-system enforcement: token-only color/font/radius semantics and no parallel `:root` family.
- Compliance is post-proof truth: the implementation PR leaves `macro:canada_stocks` non-compliant; a separate post-production registry/records closeout flips it only after proof.

---

## File Structure

**Create in implementation PR**
- `templates/stock-dashboard.css`
- `site/stock-dashboard.css`
- `tests/test_stock_dashboard_css.py`
- `mockups/evidence/theme-parity/tp1-canada/EVIDENCE.yml`
- `mockups/evidence/theme-parity/tp1-canada/manifest.json`
- content-addressed PNGs under `mockups/evidence/theme-parity/tp1-canada/cells/`
- before/after overview PNGs under `mockups/evidence/theme-parity/tp1-canada/`

**Modify in implementation PR**
- `templates/dashboard-icons.js`
- `site/dashboard-icons.js`
- `site/canada-stock-v36.js`
- `tests/test_canada_v36_composer.py`
- `config/runtime_style_injection_allowlist.json`

**Post-production closeout**
- `config/product_experience/page_registry_overrides.yml`
- `data/product_experience/page_registry.json` when the canonical builder changes it
- `research/THEME_PARITY_TP1_CANADA_ACCEPTANCE.md`

---

### Task 1: Write RED extraction/fail-soft tests

**Files:** `tests/test_canada_v36_composer.py`, new `tests/test_stock_dashboard_css.py`

- [ ] Add a test that `site/canada-stock-v36.js` contains none of:

```python
('createElement("style")', "style.textContent", "css.textContent", "function injectCss")
```

- [ ] Add a test that the mounted shell contains both canonical classes:

```python
assert "mx-stockdash" in text
assert "mx-stockdash--ca" in text
```

- [ ] Keep `test_composer_still_hides_via_hidden_attribute`; move CSS ownership assertions into the new stylesheet test:

```python
REQUIRED_CANADA_VISIBILITY = (
    ".mx-stockdash--ca .ca-v36-card-grid[hidden]",
    ".mx-stockdash--ca .ca-v36-card-grid .pvcard[hidden]",
    ".mx-stockdash--ca .ca-v36-card-grid .sm-hidden",
)
```

- [ ] Add a loader test that the Canada loader calls one shared `ensureStockDashCss(...)` seam before script injection, and that `link.onload` starts the composer while `link.onerror` does not.

- [ ] Run RED:

```bash
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
```

Expected: existing semantic tests pass; new extraction/loader/CSS-owner tests fail.

- [ ] Commit tests:

```bash
git add tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py
git commit -m "test(canada): freeze theme-parity extraction contracts"
```

---

### Task 2: Add one fail-soft shared stylesheet loader

**Files:** `templates/dashboard-icons.js`, `site/dashboard-icons.js`

- [ ] Implement one idempotent function in the composer-loader region:

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
  link.href = "stock-dashboard.css";
  link.onload = function () {
    link.setAttribute("data-ready", "1");
    onReady();
  };
  link.onerror = function () {
    /* Fail soft: legacy page remains visible; composer is not injected. */
  };
  document.head.appendChild(link);
}
```

Do not hand-author a cache stamp. Use the repository's existing asset-stamp/optimizer process after the asset exists.

- [ ] Wrap the existing bounded Canada composer retry with `ensureStockDashCss(inject)`. Preserve `__mmCanadaStockV36Loader`, `attempt < 3`, backoff, and `!window.__mmCanadaStockV36` exactly.

- [ ] Add a browser fixture where `stock-dashboard.css` returns 404; assert the composer never mounts and the legacy `#standouts` and stock table remain visible.

- [ ] Sync and verify:

```bash
python3 -m scripts.check_template_site_sync --fix
python3 -m scripts.check_template_site_sync
node --check templates/dashboard-icons.js
node --check site/dashboard-icons.js
```

- [ ] Commit:

```bash
git add templates/dashboard-icons.js site/dashboard-icons.js tests/test_canada_v36_composer.py
git commit -m "feat(stockdash): gate Canada composer on governed CSS"
```

---

### Task 3: Extract the complete Canada style inventory into the governed pair

**Files:** new `templates/stock-dashboard.css`, new `site/stock-dashboard.css`, modify `site/canada-stock-v36.js`, tests, runtime allowlist.

- [ ] Before deleting `injectCss()`, inventory and port every family exactly once: shell/head/Board+LIVE chips; section shells; Act-Now segmented control/lanes/rows/counts/routes/empty/View-all; Leadership rows/rank/name/leaders/stance/count/basis; Prophet controls/grid/card typography; hidden overrides; `.sm-hidden` rescue; table/live quote presentation; Research Tools; Evidence & Record; modal; 1200/900/680 breakpoints.

- [ ] Root the stylesheet with canonical semantics:

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

- [ ] Replace literal radii/shadows/fonts/colors with existing tokens. Controls use `var(--r-ctl)`, card/lane surfaces `var(--r-card)`, top-level modules/modal `var(--r-panel)`, pills `var(--r-pill)`. Elevation uses `--card-shadow`, `--shadow-hover`, `--popover-shadow`.

- [ ] Action lane/stance identity uses existing Prophet stance tokens, not market-direction literals:

```css
.mx-stockdash--ca .ca-v36-stance.buy { color: var(--ink-pv-buy, var(--pv-buy)); }
.mx-stockdash--ca .ca-v36-stance.near { color: var(--ink-pv-near, var(--pv-near)); }
.mx-stockdash--ca .ca-v36-stance.wait { color: var(--ink-pv-wait, var(--pv-wait)); }
.mx-stockdash--ca .ca-v36-stance.avoid { color: var(--ink-pv-avoid, var(--pv-avoid)); }
```

Apply the same semantic family to lane headers. Do not alter Canada quote `.nb-chg.up/.down` convention.

- [ ] Remove `FONT_UI` if it becomes style-only, delete `injectCss()` and its call, and mount:

```javascript
main.className = "ca-v36 mx-stockdash mx-stockdash--ca";
```

Keep existing child class names this wave.

- [ ] Copy the stylesheet pair and remove Canada's now-zero runtime-style allowance:

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 scripts/check_runtime_style_injection.py
```

- [ ] Add a token-clean test using `scripts.check_design_system.scan_text()` and reject `color-literal`, `font-family-literal`, `radius-literal`, `literal-custom-property`, `parallel-token-root`, `emoji`.

- [ ] Run:

```bash
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
python3 scripts/check_runtime_style_injection.py
node --check site/canada-stock-v36.js
```

- [ ] Commit:

```bash
git add templates/stock-dashboard.css site/stock-dashboard.css site/canada-stock-v36.js config/runtime_style_injection_allowlist.json tests/test_stock_dashboard_css.py
git commit -m "refactor(canada): move stock-dashboard presentation into governed CSS"
```

---

### Task 4: Implement Canada light as a research-workspace art direction

**Files:** `templates/stock-dashboard.css`, `site/stock-dashboard.css`, `tests/test_stock_dashboard_css.py`

- [ ] Top-level light modules: white `var(--panel)` material on `var(--bg)`, `var(--line)` hairlines, `var(--card-shadow)`; do not turn the entire page white.

- [ ] Act-Now light: one outer material; lane bodies mostly neutral/white; no grey-card-inside-grey-card stack. Rows use separators. Each lane header gets only a narrow 2px semantic rail and ~4% stance-token tint. `View all` is a quiet footer control, not a raised nested box.

- [ ] Prophet Top Picks light: `var(--panel)` plus restrained `--link` border mix and `var(--card-shadow)`; no glow halo.

- [ ] Leadership light: one ranked institutional list surface with row separators; rank and action stance remain separate visual axes. Selected/filter state may use a 2–3px `--link` rail plus low-alpha tint.

- [ ] Segmented controls light: `var(--panel2)` track, selected `var(--panel)` button + line + card shadow.

- [ ] Modal light: cool low-alpha scrim from `var(--text)` + white modal material + `var(--popover-shadow)`; inner panes avoid nested grey boxes.

- [ ] Add a structural presence fence requiring explicit selectors rooted by:

```text
html[data-theme="light"] .mx-stockdash--ca
```

and covering Act-Now, Top Picks, segmented controls, Leadership, and modal. This only proves explicit treatment exists; screenshots/reviewer own taste.

- [ ] Sync, test, commit:

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
git add templates/stock-dashboard.css site/stock-dashboard.css tests/test_stock_dashboard_css.py
git commit -m "design(canada): give light mode a research-workspace art direction"
```

---

### Task 5: Capture the canonical eight-cell evidence matrix and before/after views

**Files:** `mockups/evidence/theme-parity/tp1-canada/`

- [ ] Run the existing harness directly into a commit-eligible output directory:

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
  --smells mockups/evidence/theme-parity/tp1-canada/ux-smells.json
```

The manifest must report `schema: mastermind.p0_evidence.v2` and every requested rest cell `captured:true`, with matching `applied_theme`/`applied_locale`.

- [ ] Create the receipt/index:

```yaml
schema: mastermind.page_evidence_receipt.v1
changed_paths:
  - templates/stock-dashboard.css
manifest: mockups/evidence/theme-parity/tp1-canada/manifest.json
```

Save it as `mockups/evidence/theme-parity/tp1-canada/EVIDENCE.yml`.

- [ ] Capture four 1440 comparison images from the same baseline/current source pairing: `before-dark-en-1440.png`, `after-dark-en-1440.png`, `before-light-en-1440.png`, `after-light-en-1440.png`, plus current full-page dark/light EN shots. Do not recapture baseline from a different historical page version.

- [ ] Verify mobile `390` has no page horizontal overflow and that all manifest screenshot files exist at their referenced relative paths.

- [ ] Run the TP-0 gate:

```bash
git diff --unified=0 origin/main...HEAD -- templates site > /tmp/tp1-ui.diff
python3 scripts/check_ui_visual_evidence.py --diff-file /tmp/tp1-ui.diff
```

- [ ] Commit evidence:

```bash
git add mockups/evidence/theme-parity/tp1-canada/
git commit -m "evidence(canada): commit dark-light theme parity matrix"
```

---

### Task 6: Independent reviews + exact-head regression proof

- [ ] Run all tests selected by the current CI pack for the actual diff, plus:

```bash
python3 -m pytest tests/test_canada_v36_composer.py tests/test_stock_dashboard_css.py -q
python3 scripts/check_runtime_style_injection.py
python3 -m scripts.check_template_site_sync
node --check site/canada-stock-v36.js
node --check templates/dashboard-icons.js
```

- [ ] Independent Opus design review must inspect committed images and explicitly adjudicate: light hierarchy/material depth, dark regression, Act-Now, Prophet Top Picks, Leadership, controls/modal, EN/ZH, desktop/390, semantic hue use, and no runtime CSS bypass.

- [ ] Independent functional reviewer attacks: action≠leadership, no sector rank, owner-only theme rank, missing≠zero, Top Picks, Grid/Table, LIVE quotes/dates, Track Record, Terminal routes, two-fetch contract, fail-soft legacy fallback.

- [ ] Repair findings on the same carrier and recapture every visual cell whose rendered bytes changed.

- [ ] Wait for all binding CI to conclude on the exact repaired head. Do not merge while pending.

---

### Task 7: Merge, prove entitled production, then close registry truth

**Files after production proof:** stable acceptance path `research/THEME_PARITY_TP1_CANADA_ACCEPTANCE.md`; registry files.

- [ ] Merge the implementation PR only after exact-head CI + both reviews pass.

- [ ] Prove production serves `stock-dashboard.css` and the merged composer bytes, the stylesheet is ready before composer mount, theme changes do not remount the composer, and a stylesheet-load failure fixture leaves legacy visible.

- [ ] Execute the entitled journey in dark/light, EN/ZH, desktop and a real 390-capable viewport: section order, Act-Now caps/View-all/empty lane, Top Picks/All, sector/theme filters preserving population, Grid/Table XOR, LIVE cells and Board/LIVE dates, Track Record, Terminal, modal, console, overflow.

- [ ] If any proof fails, leave `macro:canada_stocks` non-compliant and repair the implementation.

- [ ] If proof passes, open the records/registry closeout. Obtain the merged implementation PR number as an actual integer with:

```bash
IMPLEMENTATION_PR=$(gh pr view --json number --jq .number)
printf '%s\n' "$IMPLEMENTATION_PR"
```

Write that integer into `design_system.migrated_pr`; never copy a planned number.

- [ ] Set `macro:canada_stocks.design_system.compliant: true`, preserve its `archetype: discovery_board`, add governed ownership for the Canada stocks template mode and `.mx-stockdash--ca`, and set `evidence` to `mockups/evidence/theme-parity/tp1-canada/manifest.json`.

- [ ] Regenerate the canonical page registry, run full design-system enforcement on the now-governed surface, and write `research/THEME_PARITY_TP1_CANADA_ACCEPTANCE.md` with implementation PR/head/merge, CI run ids, CSS/JS hashes, production timestamps, screenshots, 390 proof, review verdicts, and residuals.

- [ ] Merge the closeout. Stop TP-1; do not absorb HK.

---

## TP-1 Acceptance

Canada is complete only when runtime style debt is zero, the shared stylesheet is token-clean and fail-soft-loaded, every V3.8 semantic invariant remains green, all eight existing-harness visual cells plus before/after evidence are committed, independent design and functional reviews pass, entitled production proof passes, and registry compliance is flipped only in the post-proof closeout.
