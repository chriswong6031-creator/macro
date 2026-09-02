---
key: UI-VISUAL-EVIDENCE-GATE-MISSES-PURE-STRUCTURAL-MARKUP
claim: >
  The canonical UI visual-evidence gate currently requires the eight-state browser
  evidence matrix for added template CSS, added inline <style>, or runtime style
  injection, but a pure structural HTML/Jinja addition that reuses existing CSS can
  materially change page hierarchy or consume viewport without making the changed
  template a material path.
falsifier: >
  Read scripts/check_ui_visual_evidence.py material_paths() and its three
  _is_material_* predicates, or pass a diff that only adds a visible
  <section>/<div class="panel"> to templates/*.html.j2 through material_paths();
  this discovery is false if that template is classified material without also
  adding CSS/style-injection lines.
so_what: >
  Do not create another screenshot/evidence system. A follow-up hardening wave should
  extend the existing check_ui_visual_evidence.py classification narrowly enough to
  catch newly added first-level structural modules while avoiding a fleet-wide evidence
  tax on harmless nested markup. Until that classifier is safely widened, reviewers of
  action-dashboard PRs must apply DEC:ACTION-DASHBOARD-TIER1-TELEMETRY-DEMOTION and
  explicitly check whether new at-rest acreage was introduced using existing styles.
kind: constraint
verified_at: 2026-09-01
verified_by: "scripts/check_ui_visual_evidence.py material_paths/_is_material_css/_is_material_inline_style/_is_material_runtime_js and tests/test_check_ui_visual_evidence.py material-change cases on macro@a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4"
scope:
  - macro
  - "scripts/check_ui_visual_evidence.py"
  - "tests/test_check_ui_visual_evidence.py"
  - "templates/*.html.j2"
confidence: verified
---

## Why this matters here

The exact 2026-08-16 CN strip insertion added its own inline `<style>`, so the **current**
TP-0 gate would classify that historical diff as material and require real browser
evidence. That is an important improvement over the process that existed when PR #5786
merged.

It is not complete prevention, though. The gate deliberately does not judge taste, and its
material-path detector is intentionally narrow. A future worker could add a large new
first-level block using existing `.panel`, `.card`, grid, or other governed classes and
change the page composition without touching CSS. That is exactly the remaining mechanical
coverage gap this discovery records.

The correct repair is to strengthen the existing evidence-classification seam without
turning it into a taste engine or a duplicate evidence plane. Any proposed matcher must be
adversarially tested for false positives before becoming a fleet-wide hard gate.
