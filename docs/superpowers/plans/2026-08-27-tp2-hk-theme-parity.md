# TP-2 Hong Kong Theme-Parity Follower Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Hong Kong's runtime stylesheet bypass and bring HK Stocks onto the same governed dual-theme presentation grammar proven by Canada, without importing any Canada-specific market semantics.

**Architecture:** Extend the already-live `templates/stock-dashboard.css` / `site/stock-dashboard.css` family asset with HK selectors under `mx-stockdash--hk`, factor genuinely identical material rules through shared `:is(...)` selectors, and leave HK-specific data/interaction law in `site/hk-stock-v36.js`. Reuse the TP-1 stylesheet-before-composer loader seam; no second stylesheet or second theme system is created.

**Tech Stack:** Vanilla JavaScript, canonical CSS tokens, paired template/site stylesheet and loader assets, pytest source-contract tests, existing page-evidence harness, entitled production browser proof.

**Spec:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Prerequisites:** TP-0 governance `PROVEN_LIVE` on PR CI; TP-1 Canada theme parity accepted in production and `macro:canada_stocks` compliance closeout merged. Start from fresh `origin/main` only after both are canonical.

## Global Constraints

- Preserve every HK V3.8 invariant from `research/STOCK_DASHBOARD_V38_HK_ACCEPTANCE_2026-08-27.md` and `tests/test_hk_v37_composer.py`.
- Top Picks remain the owner-published `.pv-featured` cohort, never the first N card positions.
- HK has no canonical LIVE quote plane: do not add LIVE clocks, live quote fetches, or Canada table quote enhancement.
- HK Leadership & Rotation rank remains the owner Sector Rotation RS-vs-HSI rank; action stance remains a separate axis.
- Lane traversal is never rank; unranked sectors show no invented number.
- Southbound flow cue remains materiality-gated by the owner's `sig-in` / `sig-out` marker and absent for `sig-neu`/missing.
- Research Tool disclosure remains owner-panel reveal, one at a time.
- Evidence & Record must continue moving both `.trd-wrap` siblings so the Track Record dialog is not stranded under a hidden ancestor.
- Zero network reads remain zero; the HK composer stays fully synchronous.
- No Canada theme-rank semantics, LIVE semantics, fetch set, or first-five Top Picks logic may bleed into HK.
- No substantive runtime stylesheet remains in `site/hk-stock-v36.js`.

---

## File Structure

**Modify**
- `templates/stock-dashboard.css` — extend shared family grammar with HK material selectors.
- `site/stock-dashboard.css` — byte-identical pair.
- `templates/dashboard-icons.js` / `site/dashboard-icons.js` — route HK composer through existing `ensureStockDashCss` seam.
- `site/hk-stock-v36.js` — remove `injectCss()` and add `mx-stockdash mx-stockdash--hk` root classes.
- `tests/test_hk_v37_composer.py` — no-runtime-style, stylesheet-load, semantic regression pins.
- `tests/test_stock_dashboard_css.py` — HK selector/light-art/token-clean coverage.
- `config/runtime_style_injection_allowlist.json` — drop HK runtime-style allowance to zero/remove row.

**Create**
- `mockups/evidence/theme-parity/tp2-hk/` — existing page-evidence harness output + before/after overview shots.

**Post-production closeout**
- `config/product_experience/page_registry_overrides.yml` — flip `macro:hk_stocks` compliant after proof.
- `research/THEME_PARITY_TP2_HK_ACCEPTANCE_2026-08-<proof-date>.md` — exact receipts.

---

### Task 1: Freeze the HK presentation-source and follower-semantic tests

**Files:**
- Modify: `tests/test_hk_v37_composer.py`
- Modify: `tests/test_stock_dashboard_css.py`

**Interfaces:**
- Consumes: current HK V3.8 composer, shared TP-1 stylesheet.
- Produces: tests that forbid runtime CSS while keeping HK-specific semantics pinned.

- [ ] **Step 1: Add the no-runtime-stylesheet test**

```python
def test_hk_composer_contains_no_runtime_stylesheet_system() -> None:
    text = _composer_text()
    assert 'createElement("style")' not in text
    assert "css.textContent" not in text
    assert "style.textContent" not in text
    assert "function injectCss" not in text
```

- [ ] **Step 2: Add the canonical root-class test**

```python
def test_hk_mount_uses_canonical_stock_dashboard_root_classes() -> None:
    text = _composer_text()
    assert "mx-stockdash" in text
    assert "mx-stockdash--hk" in text
```

- [ ] **Step 3: Add the shared stylesheet loader-order test to the existing loader test section**

The HK loader block must contain `stock-dashboard.css`/`ensureStockDashCss` and the function call must dominate `hk-stock-v36.js` injection. Preserve the existing loader idempotency `__mmHKStockV36Loader` and bounded retry semantics exactly.

- [ ] **Step 4: Add HK visibility/reveal contracts to `tests/test_stock_dashboard_css.py`**

```python
REQUIRED_HK_VISIBILITY = (
    ".mx-stockdash--hk .hk-v37-card-grid[hidden]",
    ".mx-stockdash--hk .hk-v37-card-grid .pvcard[hidden]",
    ".mx-stockdash--hk .hk-v37-card-grid .sm-hidden",
    "body.hk-v37-mounted .panel.hk-v37-revealed",
)


def test_hk_visibility_and_research_tool_reveal_live_in_governed_css() -> None:
    text = _css()
    for selector in REQUIRED_HK_VISIBILITY:
        assert selector in text
```

- [ ] **Step 5: Run focused tests and verify the new assertions fail before extraction**

```bash
python3 -m pytest tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py -q
```

Expected: existing HK semantic tests remain green; the new presentation-source tests fail.

- [ ] **Step 6: Commit red tests**

```bash
git add tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py
git commit -m "test(hk): freeze stock-dashboard theme-parity follower contracts"
```

---

### Task 2: Route HK through the existing stylesheet-before-composer loader seam

**Files:**
- Modify: `templates/dashboard-icons.js`
- Modify: `site/dashboard-icons.js`

**Interfaces:**
- Consumes: TP-1 `ensureStockDashCss(onReady)`.
- Produces: HK composer injection only after shared stylesheet readiness; CSS failure leaves legacy HK page visible.

- [ ] **Step 1: Wrap the existing HK `inject()` call in `ensureStockDashCss(inject)`**

Do not duplicate the function. The loader has exactly one stylesheet node `#mx-stockdash-css` shared by Canada/HK routes.

Preserve:

- HK route gate `/hk_stocks.html`;
- `window.__mmHKStockV36Loader`;
- bounded retry count and backoff already present on current main;
- no composer reinjection after `window.__mmHKStockV36` is set.

- [ ] **Step 2: Verify CSS failure is fail-soft by source contract and browser harness**

A local fixture that makes `stock-dashboard.css` 404 must show:

```javascript
window.__mmHKStockV36 === undefined || window.__mmHKStockV36 === false
```

and the legacy `#standouts`/stock table remain visible. The loader must not hide any legacy element itself.

- [ ] **Step 3: Sync and verify the paired loader**

```bash
python3 -m scripts.check_template_site_sync --fix
python3 -m scripts.check_template_site_sync
node --check templates/dashboard-icons.js
node --check site/dashboard-icons.js
```

- [ ] **Step 4: Commit Task 2**

```bash
git add templates/dashboard-icons.js site/dashboard-icons.js
git commit -m "feat(stockdash): gate HK composer on shared CSS"
```

---

### Task 3: Extract HK CSS and converge truly shared material rules

**Files:**
- Modify: `templates/stock-dashboard.css`
- Modify: `site/stock-dashboard.css`
- Modify: `site/hk-stock-v36.js`
- Modify: `config/runtime_style_injection_allowlist.json`
- Modify: `tests/test_stock_dashboard_css.py`

**Interfaces:**
- Consumes: current HK `injectCss()` declaration inventory and TP-1 Canada stylesheet.
- Produces: no runtime HK CSS; shared material grammar where semantics/geometry are the same; HK-only selectors where behavior differs.

- [ ] **Step 1: Inventory every HK family before deletion**

The extraction must disposition each current `injectCss()` family exactly once:

1. body mount hide/reveal rules for nested HK panels;
2. shell/head/Board chip — **no LIVE chip**;
3. section headers;
4. Act-Now segmented mobile selector, lanes, rows, count/route/View all;
5. Leadership & Rotation basis, RS rank rows, action stance, Southbound cue;
6. Prophet source/view controls, grid, card overrides, empty/filter state;
7. hidden and `.sm-hidden` rescue;
8. table host — **no Canada live-quote enhancement**;
9. Research Tool toggles/revealed panels;
10. Evidence & Record double-wrap host;
11. modal, Sector Rotation table, Southbound subband;
12. 1200/900/680 responsive rules.

- [ ] **Step 2: Factor identical geometry through the shared root, not duplicated market blocks**

Where Canada and HK declarations are genuinely byte-equivalent after token cleanup, use grouped selectors such as:

```css
.mx-stockdash :is(.ca-v36-head, .hk-v37-head) {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 66px;
  margin-bottom: 14px;
}

.mx-stockdash :is(.ca-v36-an-lanes, .hk-v37-an-lanes) {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
```

Do not group rules where semantics differ, especially LIVE quote colors, research-panel hiding depth, rank-basis text, Southbound cues, or Track Record DOM shape.

- [ ] **Step 3: Keep HK-specific mount visibility exact**

Because `hk_stocks.html` lacks Canada's `page-canada` direct-child shape, retain the proven descendant rule:

```css
body.hk-v37-mounted .panel { display: none !important; }
body.hk-v37-mounted .panel.hk-v37-revealed { display: block !important; }
```

Do not “normalize” it to the Canada direct-child selector.

- [ ] **Step 4: Use stance tokens for the four action lanes while preserving RS-vs-HSI rank as neutral information**

Action tone uses `--pv-buy/near/wait/avoid` ink/fill family. RS rank/basis uses neutral text/`--link` wayfinding, never green/red to imply a recommendation.

- [ ] **Step 5: Remove HK runtime stylesheet code and add root classes**

Delete `FONT_UI` when no longer used, delete `injectCss()` and its call, and mount:

```javascript
main.className = "hk-v37 mx-stockdash mx-stockdash--hk";
```

No network calls may appear in the file as a side effect of this refactor.

- [ ] **Step 6: Ratchet HK runtime-style allowance to zero**

Update `config/runtime_style_injection_allowlist.json` so HK's obsolete allowance disappears on the same PR.

- [ ] **Step 7: Sync, run token/semantic tests, and prove zero-fetch remains zero**

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 scripts/check_runtime_style_injection.py
python3 -m pytest tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py -q
node --check site/hk-stock-v36.js
```

Also assert the current zero-fetch test in `test_hk_v37_composer.py` still passes.

- [ ] **Step 8: Commit Task 3**

```bash
git add templates/stock-dashboard.css site/stock-dashboard.css site/hk-stock-v36.js config/runtime_style_injection_allowlist.json tests/test_stock_dashboard_css.py
git commit -m "refactor(hk): move stock-dashboard presentation into governed CSS"
```

---

### Task 4: Implement HK-specific light art-direction deltas

**Files:**
- Modify: `templates/stock-dashboard.css`
- Modify: `site/stock-dashboard.css`
- Modify: `tests/test_stock_dashboard_css.py`

**Interfaces:**
- Consumes: shared TP-1 light research-workspace grammar.
- Produces: HK light mode with the same quality contract but HK-native rank/flow/research semantics.

- [ ] **Step 1: Reuse the Canada-proven light material hierarchy for shared shells/lanes/cards/controls**

Top-level panels remain white material on the cool canvas; Act-Now lanes remain neutral with narrow semantic rails; Prophet Top Picks use restrained material elevation rather than glow; selected segmented controls use surface contrast plus shadow.

Do not create a second HK palette or a second `:root` block.

- [ ] **Step 2: Make Leadership & Rotation visibly descriptive, not action-colored**

For light HK:

```css
html[data-theme="light"] .mx-stockdash--hk .hk-v37-lead-basis {
  background: var(--panel2);
  color: var(--muted);
}
html[data-theme="light"] .mx-stockdash--hk .hk-v37-lead-row {
  background: var(--panel);
  border-bottom: 1px solid var(--line);
}
```

RS number/basis stays neutral/wayfinding. The separate action stance chip carries stance hue.

- [ ] **Step 3: Preserve Southbound materiality in layout and color**

The leadership header cue remains absent for neutral/missing materiality. When present, it must use the existing owner-emitted semantic state and quiet informational treatment; do not turn it into a permanently colored banner in light mode.

- [ ] **Step 4: Keep Research Tools as disclosure controls, not a wall of visible legacy panels**

Light revealed specialist panels may use white material + `var(--card-shadow)`, but only the one active `.hk-v37-revealed` panel is visible. Hidden panels stay hidden.

- [ ] **Step 5: Keep the modal clean and ranked**

Use the shared cool light scrim/white modal card. Preserve the HK Sector Rotation rank column and Southbound subband; do not import Canada's themes-only modal shape.

- [ ] **Step 6: Add explicit HK light-rule presence tests**

```python
def test_hk_has_explicit_light_material_rules() -> None:
    text = _css()
    anchor = 'html[data-theme="light"] .mx-stockdash--hk'
    assert text.count(anchor) >= 5
    assert ".hk-v37-lead-row" in text
    assert ".hk-v37-modal" in text
    assert ".hk-v37-card-grid" in text
```

Again, presence is not taste acceptance.

- [ ] **Step 7: Sync/test/commit**

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 -m pytest tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py -q
git add templates/stock-dashboard.css site/stock-dashboard.css tests/test_stock_dashboard_css.py
git commit -m "design(hk): add market-native light research-workspace treatment"
```

---

### Task 5: Capture full HK evidence and run dual independent review

**Files:**
- Create under: `mockups/evidence/theme-parity/tp2-hk/`

- [ ] **Step 1: Capture the existing harness matrix**

```bash
python3 scripts/capture_page_evidence.py \
  --site-dir site \
  --routes /hk_stocks.html \
  --viewports desktop,mobile \
  --locales en,zh \
  --themes dark,light \
  --max-pages 1 \
  --output-dir mockups/evidence/theme-parity/tp2-hk/cells \
  --manifest mockups/evidence/theme-parity/tp2-hk/manifest.json \
  --smells mockups/evidence/theme-parity/tp2-hk/ux-smells.json
```

Use the real capture timestamp/as-of; do not backdate.

- [ ] **Step 2: Capture before/after dark and light 1440 overview images**

Store under the same evidence directory, plus `fullpage-dark-en-1440.png` and `fullpage-light-en-1440.png`.

- [ ] **Step 3: Run the TP-0 evidence guard against the actual diff**

```bash
git diff --unified=0 origin/main...HEAD -- templates site > /tmp/tp2-ui.diff
python3 scripts/check_ui_visual_evidence.py --diff-file /tmp/tp2-ui.diff
```

- [ ] **Step 4: Independent design review**

The reviewer must inspect: light/dark Act-Now, RS-vs-HSI Leadership, action-vs-rank separation, Southbound cue, Top Picks, modal, Research Tool disclosure, EN/ZH, 390, and dark regression.

- [ ] **Step 5: Independent functional/adversarial review**

Attack: pv-featured cohort law, zero fetch, no LIVE, rank owner, null rank, membership missing ≠ zero, Southbound materiality gate, `.sm-hidden` rescue, population preservation, double `.trd-wrap`, research tools, abort-to-legacy.

- [ ] **Step 6: Repair and recapture changed visuals; wait for exact-head CI**

No stale screenshot may remain after a rendering repair.

---

### Task 6: Prove production, then earn HK registry compliance

**Files:**
- Post-proof create: `research/THEME_PARITY_TP2_HK_ACCEPTANCE_2026-08-<proof-date>.md`
- Post-proof modify: `config/product_experience/page_registry_overrides.yml`

- [ ] **Step 1: Merge only after exact-head checks and reviews are clean**

- [ ] **Step 2: On entitled production prove shared CSS loads before HK composer and the served composer contains no runtime stylesheet**

- [ ] **Step 3: Execute the real HK journey in dark/light, EN/ZH, desktop/390**

Verify:

- Act-Now 4 lanes + caps/View all;
- Top Picks = `.pv-featured`, All Candidates unchanged;
- group filter preserves population;
- Grid/Table XOR;
- Leadership `RS #N` basis and separate action stance;
- no LIVE anywhere;
- Southbound cue only when owner materiality is directional;
- modal retains ranked sectors + Southbound subband;
- Track Record dialog opens after both wraps moved;
- each Research Tool reveals one owner panel;
- theme switch needs no composer remount;
- console clean and 390 no overflow.

- [ ] **Step 4: Keep HK non-compliant if any production proof fails**

- [ ] **Step 5: After clean proof, flip `macro:hk_stocks` compliant in the records/registry closeout**

Use:

```yaml
  macro:hk_stocks:
    archetype: "discovery_board"
    design_system:
      compliant: true
      governed_regions:
        - {template: templates/hk.html.j2, region: "hk stocks mode"}
        - {template: templates/stock-dashboard.css, region: .mx-stockdash--hk}
      migrated_pr: <actual merged TP-2 PR number>
      evidence: mockups/evidence/theme-parity/tp2-hk/manifest.json
```

Use the exact region vocabulary accepted by the current registry builder on fresh main; do not invent a selector if the HK stocks body has no dedicated body class. The important ownership is the HK stocks template mode plus `.mx-stockdash--hk` shared-CSS region.

- [ ] **Step 6: Regenerate/validate the page registry and write acceptance receipts**

Record merge/CI hashes, served CSS/JS hashes, entitled production matrix, screenshots, and any residual. Only then state HK theme parity `PROVEN_LIVE`.

- [ ] **Step 7: Merge closeout and stop**

TP-3 census starts only after both Canada and HK are canonical compliant examples.

---

## TP-2 Acceptance

TP-2 is complete only when HK has zero runtime stylesheet debt, consumes the one governed stock-dashboard stylesheet, retains all HK-specific semantic contracts, passes the full evidence matrix and independent dual-theme review, proves the entitled production journey, and earns registry compliance after proof.

**Stop condition:** Do not begin China convergence or estate-wide repainting in this wave. Return exact production/registry receipts to Sol, then TP-3 performs the site-wide census from a stable pair of reference implementations.
