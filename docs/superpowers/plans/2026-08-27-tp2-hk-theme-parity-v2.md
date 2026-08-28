# TP-2 Hong Kong Theme-Parity Follower Implementation Plan — V2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring HK Stocks onto the same governed dual-theme presentation layer proven by Canada while preserving HK-native product/data semantics exactly.

**Architecture:** Extend the existing paired `templates/stock-dashboard.css` / `site/stock-dashboard.css` with `mx-stockdash--hk`. Reuse the one `ensureStockDashCss` loader from TP-1. Remove HK's `injectCss()` runtime presentation system while keeping `site/hk-stock-v36.js` as the semantic/state/interaction composer. Factor genuinely identical Canada/HK geometry at the shared root; keep rank, flow, panel-depth, and no-LIVE differences market-specific.

**Tech Stack:** Vanilla JS, canonical CSS tokens, paired template/site assets, pytest, existing `mastermind.p0_evidence.v2` harness, real entitled production browser proof.

**Spec:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Implementation amendment:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_IMPLEMENTATION_AMENDMENT_1.md`

**Prerequisites:** TP-0 merged; TP-1 Canada production acceptance and registry closeout merged. Start from fresh `origin/main`.

## Global Constraints

- Preserve current HK V3.8 acceptance and `tests/test_hk_v37_composer.py` unless fresh canonical source supersedes a specific assertion.
- Top Picks remain owner `.pv-featured`, never first-N card position.
- HK remains zero-fetch and has no LIVE quote plane, LIVE chip, live date, or Canada quote-table enhancement.
- Leadership rank is owner Sector Rotation relative-strength-vs-HSI; action stance remains independent. Lane traversal never becomes rank.
- Null rank stays null; missing membership never becomes zero.
- Southbound cue remains present only for owner `sig-in`/`sig-out`, absent for `sig-neu` or missing.
- Research Tools reveal only owner panels, one at a time.
- Evidence & Record continues moving both `.trd-wrap` siblings so the dialog is never stranded under a hidden ancestor.
- No substantive runtime stylesheet remains in `site/hk-stock-v36.js`.
- Registry compliance flips only after post-merge production proof.

---

## File Structure

**Implementation PR modifies**
- `templates/stock-dashboard.css`
- `site/stock-dashboard.css`
- `templates/dashboard-icons.js`
- `site/dashboard-icons.js`
- `site/hk-stock-v36.js`
- `tests/test_hk_v37_composer.py`
- `tests/test_stock_dashboard_css.py`
- `config/runtime_style_injection_allowlist.json`

**Implementation PR creates evidence**
- `mockups/evidence/theme-parity/tp2-hk/EVIDENCE.yml`
- `mockups/evidence/theme-parity/tp2-hk/manifest.json`
- `mockups/evidence/theme-parity/tp2-hk/cells/*.png`
- before/after overview PNGs in the same evidence directory

**Post-proof closeout**
- `config/product_experience/page_registry_overrides.yml`
- `data/product_experience/page_registry.json` when regenerated
- `research/THEME_PARITY_TP2_HK_ACCEPTANCE.md`

---

### Task 1: Write RED HK extraction and shared-loader tests

**Files:** `tests/test_hk_v37_composer.py`, `tests/test_stock_dashboard_css.py`

- [ ] Add a test forbidding `createElement("style")`, `css.textContent`, `style.textContent`, and `function injectCss` in `site/hk-stock-v36.js`.
- [ ] Add a test requiring `mx-stockdash` and `mx-stockdash--hk` in the mounted shell.
- [ ] Add a loader test requiring the existing `ensureStockDashCss` seam to dominate `hk-stock-v36.js` injection. Do not allow a second stylesheet loader function.
- [ ] Move presentation assertions into `tests/test_stock_dashboard_css.py` and require:

```python
REQUIRED_HK_VISIBILITY = (
    ".mx-stockdash--hk .hk-v37-card-grid[hidden]",
    ".mx-stockdash--hk .hk-v37-card-grid .pvcard[hidden]",
    ".mx-stockdash--hk .hk-v37-card-grid .sm-hidden",
    "body.hk-v37-mounted .panel.hk-v37-revealed",
)
```

- [ ] Run RED:

```bash
python3 -m pytest tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py -q
```

Existing HK semantic assertions must remain green; new presentation-source assertions fail.

- [ ] Commit:

```bash
git add tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py
git commit -m "test(hk): freeze theme-parity follower contracts"
```

---

### Task 2: Route HK through the already-proven stylesheet readiness seam

**Files:** `templates/dashboard-icons.js`, `site/dashboard-icons.js`

- [ ] Do not duplicate `ensureStockDashCss`. Wrap the current HK bounded composer retry in the existing seam.
- [ ] Preserve `/hk_stocks.html` route gating, `__mmHKStockV36Loader`, existing retry count/backoff, and no reinjection after `__mmHKStockV36`.
- [ ] Add a CSS-404 browser fixture proving HK composer never mounts and legacy `#standouts`/table remain visible.
- [ ] Sync/parse:

```bash
python3 -m scripts.check_template_site_sync --fix
python3 -m scripts.check_template_site_sync
node --check templates/dashboard-icons.js
node --check site/dashboard-icons.js
```

- [ ] Commit:

```bash
git add templates/dashboard-icons.js site/dashboard-icons.js tests/test_hk_v37_composer.py
git commit -m "feat(stockdash): gate HK composer on shared CSS"
```

---

### Task 3: Extract HK presentation and converge only truly shared geometry

**Files:** shared stylesheet pair, HK composer, runtime allowlist, CSS tests.

- [ ] Before deleting HK `injectCss()`, disposition every current family: body nested-panel hide/reveal; shell/head/Board chip; section headers; Act-Now lanes/rows/mobile selector; Leadership RS basis/rank/action stance/Southbound cue; Prophet controls/grid/card rules; hidden/`.sm-hidden`; table host; Research Tools/revealed panels; Evidence double-wrap host; modal/Sector Rotation/Southbound subband; 1200/900/680 breakpoints.

- [ ] Where declarations are genuinely identical after token cleanup, factor them at `.mx-stockdash` with grouped selectors, e.g.:

```css
.mx-stockdash :is(.ca-v36-head, .hk-v37-head) {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 66px;
  margin-bottom: 14px;
}
```

Do not group LIVE semantics, rank/basis rules, Southbound, Track Record DOM shape, or body panel-depth behavior.

- [ ] Preserve the proven HK descendant visibility law exactly:

```css
body.hk-v37-mounted .panel { display: none !important; }
body.hk-v37-mounted .panel.hk-v37-revealed { display: block !important; }
```

Do not normalize it to Canada's direct-child shape.

- [ ] Action lanes use Prophet stance tokens. RS rank/basis stays neutral/wayfinding and never uses up/down hues to imply recommendation.

- [ ] Remove `FONT_UI` if style-only, delete HK `injectCss()` and call, and mount:

```javascript
main.className = "hk-v37 mx-stockdash mx-stockdash--hk";
```

- [ ] Confirm the composer still contains zero network reads.

- [ ] Remove HK's now-zero runtime-style allowance, sync the stylesheet pair, and verify:

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 scripts/check_runtime_style_injection.py
python3 -m pytest tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py -q
node --check site/hk-stock-v36.js
```

- [ ] Commit:

```bash
git add templates/stock-dashboard.css site/stock-dashboard.css site/hk-stock-v36.js config/runtime_style_injection_allowlist.json tests/test_stock_dashboard_css.py
git commit -m "refactor(hk): move stock-dashboard presentation into governed CSS"
```

---

### Task 4: Implement HK light art-direction deltas

**Files:** shared stylesheet pair and CSS tests.

- [ ] Reuse Canada-proven research-workspace materials for shared shell, Act-Now lanes, Prophet card grid, controls and modal: cool canvas, white material, disciplined hairline/shadow, no translated glow.

- [ ] Keep Leadership descriptive: light RS rows are neutral white/list material with row separators. `RS #N`/basis stays neutral or `--link` wayfinding; the separate action stance chip carries stance hue.

- [ ] Southbound cue remains absent when neutral/missing. When directional, use restrained informational material; never make a permanent saturated banner.

- [ ] Research Tool controls stay compact; only the active `.hk-v37-revealed` owner panel becomes visible. Revealed light panels use white material and standard elevation.

- [ ] Modal light uses the shared cool scrim/white raised card while preserving HK's ranked sectors and Southbound subband. Do not copy Canada's themes-only modal semantics.

- [ ] Add a source fence requiring explicit rules rooted by:

```text
html[data-theme="light"] .mx-stockdash--hk
```

covering Leadership, Prophet grid/Top Picks, modal, and controls. Presence is not visual acceptance.

- [ ] Sync/test/commit:

```bash
cp templates/stock-dashboard.css site/stock-dashboard.css
python3 -m scripts.check_template_site_sync
python3 -m pytest tests/test_hk_v37_composer.py tests/test_stock_dashboard_css.py -q
git add templates/stock-dashboard.css site/stock-dashboard.css tests/test_stock_dashboard_css.py
git commit -m "design(hk): add market-native light research-workspace treatment"
```

---

### Task 5: Capture canonical evidence and run independent dual review

- [ ] Capture directly with the existing harness:

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

- [ ] Save `mockups/evidence/theme-parity/tp2-hk/EVIDENCE.yml`:

```yaml
schema: mastermind.page_evidence_receipt.v1
changed_paths:
  - templates/stock-dashboard.css
manifest: mockups/evidence/theme-parity/tp2-hk/manifest.json
```

- [ ] Capture same-baseline before/after 1440 dark/light overview shots and current full-page dark/light shots. Verify manifest schema/cells/applied state and 390 no-overflow.

- [ ] Run:

```bash
git diff --unified=0 origin/main...HEAD -- templates site > /tmp/tp2-ui.diff
python3 scripts/check_ui_visual_evidence.py --diff-file /tmp/tp2-ui.diff
```

- [ ] Independent design review inspects both themes for Act-Now, RS-vs-HSI Leadership, action/rank separation, Southbound cue, Prophet Top Picks, modal, Research Tool disclosure, EN/ZH and 390.

- [ ] Independent functional review attacks `.pv-featured` Top Picks, zero-fetch/no-LIVE, owner rank/null rank, missing≠zero, Southbound gate, population preservation, `.sm-hidden`, double `.trd-wrap`, research disclosure and legacy fallback.

- [ ] Repair on same carrier; recapture any changed rendering; wait for exact-head CI.

---

### Task 6: Merge, prove production, then close registry truth

- [ ] Merge only after exact-head checks and both independent reviews pass.
- [ ] Prove production loads the shared CSS before HK composer and serves no runtime stylesheet system in the composer.
- [ ] Execute dark/light EN/ZH desktop/real-390: Act-Now lanes/View-all; `.pv-featured` Top Picks/All; group filtering preserving population; Grid/Table XOR; `RS #N` basis + separate action stance; no LIVE anywhere; Southbound only when directional; modal rank/Southbound subband; Track Record after both wraps moved; Research Tools one-at-a-time; theme toggle no remount; clean console/no overflow.
- [ ] If proof fails, keep `macro:hk_stocks` non-compliant and repair.
- [ ] If proof passes, obtain the actual implementation PR number with `gh pr view --json number --jq .number`, write that integer into the post-proof registry closeout, set `evidence: mockups/evidence/theme-parity/tp2-hk/manifest.json`, and govern the HK stocks template mode plus `.mx-stockdash--hk` shared-CSS region using the current registry's accepted region vocabulary.
- [ ] Regenerate/validate the registry and write stable acceptance file `research/THEME_PARITY_TP2_HK_ACCEPTANCE.md` with exact merge/CI/hash/browser/evidence receipts.
- [ ] Merge closeout and stop. Do not absorb China or estate repair.

---

## TP-2 Acceptance

HK completes only when runtime style debt is zero, it consumes the one governed stock-dashboard stylesheet, all HK-native semantics remain green, the eight canonical harness states and before/after evidence are committed, independent design + functional reviews pass, entitled production proof passes, and compliance flips only after proof.
