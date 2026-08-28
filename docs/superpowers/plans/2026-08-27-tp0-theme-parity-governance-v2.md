# TP-0 Theme-Parity Governance Implementation Plan — V2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new user-facing presentation debt fail closed without reddening inherited estate debt, and require material UI changes to carry existing-harness dark/light evidence that a design reviewer can judge.

**Architecture:** Extend `scripts/check_design_system.py` with a diff-aware forward-only mode while preserving its one-root/no-subprocess closure law. Add a separate ratcheted JavaScript runtime-style guard because widening the design checker would violate that closure contract. Add a small evidence **receipt/index** that maps changed presentation paths to the existing `mastermind.p0_evidence.v2` manifest produced by `scripts/capture_page_evidence.py`; the receipt does not redefine screenshot cells or provenance.

**Tech Stack:** Python 3.12 stdlib + PyYAML, unified-diff parsing, existing `scripts/capture_page_evidence.py`, existing logical CI manifest `.github/ci/legacy-jobs.yml`, repository agent instruction Markdown.

**Spec:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Implementation amendment:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_IMPLEMENTATION_AMENDMENT_1.md`

**Approval:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_APPROVAL_2026-08-27.md`

## Global Constraints

- Execution begins from freshly fetched `origin/main`, never this architecture branch's old base.
- Re-pin the protected Sol Skillpack and re-check path/PR collisions immediately before modification.
- `scripts/check_design_system.py` must continue to name only the `templates` scan root and make no subprocess call.
- Legacy debt reports but does not block unless the changed line is a new forbidden design decision or the registry already marks the governed surface compliant.
- No second design system, token root, page registry, screenshot manifest, evidence lifecycle, or visual score is permitted.
- The canonical capture manifest remains `mastermind.p0_evidence.v2` from `scripts/capture_page_evidence.py`.
- CI checks evidence existence/state identity only. Human/Opus review owns visual taste and acceptance.
- Every new `scripts/check_*.py` file must be registered in `config/house_law_checks.yml` and invoked by a real logical CI job.

---

## File Structure

**Modify**
- `scripts/check_design_system.py`
- `tests/test_check_design_system.py`
- `CLAUDE.md`
- `AGENTS.md`
- `.claude/agents/designer.md`
- `.claude/agents/builder.md`
- `.claude/agents/reviewer.md`
- `.github/PULL_REQUEST_TEMPLATE/design_migration.md`
- `config/house_law_checks.yml`
- `.github/ci/legacy-jobs.yml`
- `docs/HOUSE_LAW_CI_GUARD_SUITE.md` only through the canonical meta-guard emitter

**Create**
- `scripts/check_runtime_style_injection.py`
- `tests/test_check_runtime_style_injection.py`
- `config/runtime_style_injection_allowlist.json`
- `scripts/check_ui_visual_evidence.py`
- `tests/test_check_ui_visual_evidence.py`

---

### Task 1: Add forward-only changed-line enforcement to the existing design checker

**Files:**
- Modify: `scripts/check_design_system.py`
- Modify: `tests/test_check_design_system.py`

**Interfaces:**
- Produces `parse_added_line_numbers(diff_text: str) -> dict[str, set[int]]`.
- Produces `added_blocking_findings(findings, added_lines) -> list[Finding]`.
- Adds CLI mode `enforce-added` and argument `--diff-file PATH`; `PATH=-` reads stdin.

- [ ] **Step 1: Write RED tests for added-line-only blocking**

Add fixtures proving an unchanged legacy raw color does not block while a newly added raw color in the same file does. Add a second fixture proving a new emoji UI glyph and a new non-theme `:root` custom-property family block in `enforce-added`.

Use a real unified hunk:

```python
diff = """diff --git a/templates/legacy.css b/templates/legacy.css
--- a/templates/legacy.css
+++ b/templates/legacy.css
@@ -1,0 +2,1 @@
+.new{color:#ff0044}
"""
```

Expected assertion: exit `1`; output contains `legacy.css:2` but not `legacy.css:1`.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest tests/test_check_design_system.py -q
```

Expected: only the new tests fail because the new mode/parser/rule do not exist.

- [ ] **Step 3: Implement the pure unified-diff parser**

```python
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_added_line_numbers(diff_text: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    path: str | None = None
    new_line = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
            out.setdefault(path, set())
            continue
        match = HUNK_RE.match(raw)
        if match:
            new_line = int(match.group(1))
            continue
        if path is None or raw.startswith(("diff --git ", "--- ")):
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            out[path].add(new_line)
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            continue
        else:
            new_line += 1
    return out
```

- [ ] **Step 4: Add `parallel-token-root` detection without changing theme ownership**

For any scanned file except `templates/theme.css`, emit a finding at a `:root` block that declares one or more custom properties, even if the property values are token derivations. This catches a parallel root, while scoped derived custom properties remain legal.

- [ ] **Step 5: Add the new blocking set and mode**

```python
MODES = ("report", "enforce", "enforce-added")
ADDED_BLOCKING_RULES = frozenset(BLOCKING_RULES) | {"emoji", "parallel-token-root"}


def added_blocking_findings(findings, added_lines):
    return [
        finding for finding in findings
        if finding.rule in ADDED_BLOCKING_RULES
        and finding.line in added_lines.get(finding.path, set())
    ]
```

`report` and full `enforce` keep their existing semantics exactly.

- [ ] **Step 6: Verify and mutation-test**

```bash
python3 -m pytest tests/test_check_design_system.py -q
python3 scripts/check_design_system.py --self-check
```

Mutation controls: remove `emoji` from the added blocking set and verify the hostile test fails; make deletion lines increment the new-file line counter and verify the line-number test fails; restore both.

- [ ] **Step 7: Commit**

```bash
git add scripts/check_design_system.py tests/test_check_design_system.py
git commit -m "fix(design): enforce new UI decisions forward-only"
```

---

### Task 2: Add the ratcheted runtime stylesheet-injection guard

**Files:**
- Create: `scripts/check_runtime_style_injection.py`
- Create: `tests/test_check_runtime_style_injection.py`
- Create: `config/runtime_style_injection_allowlist.json`

**Interfaces:**
- Scans user-facing `.js` under `templates/` and `site/`.
- Counts `create_style`, `style_text`, `insert_rule`, `style_markup` per file.
- Exit `1` if an injecting file is absent from the frozen baseline or any actual count exceeds its exact allowance.
- If actual count is lower than allowance, emit a GitHub `::notice` requiring the same PR to shrink/remove the stale allowance.

- [ ] **Step 1: Write RED hostile fixtures**

Tests must cover: new injecting file → red; allowance 1 with actual 2 → red; allowance 2 with actual 1 → stale-budget notice; clean file → pass.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest tests/test_check_runtime_style_injection.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement exact pattern counts**

```python
PATTERNS = {
    "create_style": re.compile(r"createElement\(\s*['\"]style['\"]\s*\)"),
    "style_text": re.compile(r"(?:style|css)\.textContent\s*="),
    "insert_rule": re.compile(r"\.sheet\.insertRule\s*\("),
    "style_markup": re.compile(r"<style(?:\s|>)", re.IGNORECASE),
}
```

The baseline shape is:

```json
{
  "schema": "mastermind.runtime_style_allowlist.v1",
  "generated_from": "git commit sha",
  "files": {}
}
```

`generated_from` is populated by `git rev-parse HEAD` in the baseline-emission command; the implementation never substitutes a guessed value.

- [ ] **Step 4: Add `--emit-baseline` and generate from the fresh execution base**

```bash
BASE_SHA=$(git rev-parse HEAD)
python3 scripts/check_runtime_style_injection.py --emit-baseline --generated-from "$BASE_SHA" \
  > config/runtime_style_injection_allowlist.json
python3 scripts/check_runtime_style_injection.py
```

Expected: exact current debt passes; no count is manually increased.

- [ ] **Step 5: Add `--selftest`, verify, mutation-test, commit**

```bash
python3 -m pytest tests/test_check_runtime_style_injection.py -q
python3 scripts/check_runtime_style_injection.py --selftest
python3 scripts/check_runtime_style_injection.py
git add scripts/check_runtime_style_injection.py tests/test_check_runtime_style_injection.py config/runtime_style_injection_allowlist.json
git commit -m "feat(design): fence runtime stylesheet injection"
```

---

### Task 3: Gate material UI changes on the existing page-evidence manifest

**Files:**
- Create: `scripts/check_ui_visual_evidence.py`
- Create: `tests/test_check_ui_visual_evidence.py`

**Interfaces:**
- Consumes a unified PR diff and receipt files named `EVIDENCE.yml` under `mockups/refs/` or `mockups/evidence/`.
- Receipt format contains only: `schema: mastermind.page_evidence_receipt.v1`, `changed_paths`, `manifest`.
- The referenced manifest must be the existing `mastermind.p0_evidence.v2` shape from `scripts/capture_page_evidence.py`.
- Required rest cells for a flagship material change: dark/light × en/zh × desktop/mobile, each `captured:true`, requested/applied theme+locale aligned, and referenced PNG file present.
- Forced-state truth remains whatever the existing manifest says; the receipt never re-describes state cells.

- [ ] **Step 1: Write RED tests using the real existing manifest shape**

Create fixtures with:

```python
manifest = {
    "schema": "mastermind.p0_evidence.v2",
    "pages": [{
        "page_id": "macro:canada_stocks",
        "route": "/canada_stocks.html",
        "states": [],
        "gaps": [],
    }],
}
```

Populate `states` with dictionaries matching `capture_page_evidence.py`: `viewport`, `locale`, `theme`, `captured`, `file`, `width`, `height`, `applied_theme`, `applied_locale`, and `force_state`.

Tests: material diff with no receipt → red; receipt with wrong manifest schema → red; one missing light cell → red; missing screenshot file → red; complete eight rest cells → pass.

- [ ] **Step 2: Run RED**

```bash
python3 -m pytest tests/test_check_ui_visual_evidence.py -q
```

- [ ] **Step 3: Implement material-diff detection**

A change is mechanically material when it adds lines to `templates/*.css`, adds an inline `<style` to a template, or adds a runtime-style injection signature to a user-facing JS file. Do not broaden this checker into a taste detector.

- [ ] **Step 4: Implement the receipt/index lookup and canonical manifest validation**

Required receipt example:

```yaml
schema: mastermind.page_evidence_receipt.v1
changed_paths:
  - templates/stock-dashboard.css
manifest: mockups/evidence/theme-parity/tp1-canada/manifest.json
```

For every material changed path, at least one receipt must own that exact path. The referenced manifest must exist and have `schema == "mastermind.p0_evidence.v2"`.

For the target manifest page, require these six-field identities on `force_state is None` rows:

```text
desktop / en / dark
desktop / zh / dark
desktop / en / light
desktop / zh / light
mobile  / en / dark
mobile  / zh / dark
mobile  / en / light
mobile  / zh / light
```

Require desktop `width == 1440`, mobile `width == 390`, `captured is True`, `applied_theme == theme`, `applied_locale == locale`, and `(manifest.parent / state["file"]).exists()`.

- [ ] **Step 5: Add `--selftest`, verify, and mutation-test**

```bash
python3 -m pytest tests/test_check_ui_visual_evidence.py -q
python3 scripts/check_ui_visual_evidence.py --selftest
```

Mutation controls: remove one light state; change one applied theme; delete one PNG. Each must red.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_ui_visual_evidence.py tests/test_check_ui_visual_evidence.py
git commit -m "feat(design): require canonical dual-theme evidence"
```

---

### Task 4: Make dual-theme art direction a durable agent and PR contract

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `.claude/agents/designer.md`
- Modify: `.claude/agents/builder.md`
- Modify: `.claude/agents/reviewer.md`
- Modify: `.github/PULL_REQUEST_TEMPLATE/design_migration.md`

- [ ] **Step 1: Add the same hard law to `CLAUDE.md` and `AGENTS.md`**

The block must say dark/light are two art directions; every material UI packet names DARK TREATMENT, LIGHT TREATMENT, intentional mechanism differences, reference/baseline, theme-specific degraded states, and the evidence matrix. Token substitution alone is not proof. Missing light art direction/evidence is `PARTIAL/BLOCKED`. Substantive runtime stylesheet systems are prohibited.

- [ ] **Step 2: Update designer/builder/reviewer role files**

Designer: separately state both art directions and provide both evidence sets.

Builder: if LIGHT TREATMENT/evidence is missing, stop rather than inventing a translation; never add an opaque runtime stylesheet bypass.

Reviewer: material UI `PASS` requires separate dark/light adjudication of hierarchy, material depth, semantic color, responsive composition, and EN/ZH parity.

- [ ] **Step 3: Add `## Theme art direction — required` to the design-migration PR template**

Sections: Dark treatment, Light treatment, Intentional theme differences, plus checkboxes that light was judged as a design and no runtime stylesheet bypass was introduced.

- [ ] **Step 4: Verify exact markers and commit**

```bash
grep -n "Theme art direction" CLAUDE.md AGENTS.md .github/PULL_REQUEST_TEMPLATE/design_migration.md
grep -n "runtime stylesheet" .claude/agents/builder.md .claude/agents/reviewer.md
git add CLAUDE.md AGENTS.md .claude/agents/designer.md .claude/agents/builder.md .claude/agents/reviewer.md .github/PULL_REQUEST_TEMPLATE/design_migration.md
git commit -m "docs(design): make dual-theme art direction a hard gate"
```

---

### Task 5: Register and wire the three governance checks

**Files:**
- Modify: `config/house_law_checks.yml`
- Modify: `.github/ci/legacy-jobs.yml`
- Regenerate: `docs/HOUSE_LAW_CI_GUARD_SUITE.md`

- [ ] **Step 1: Add one logical `design-governance` CI job**

It runs:

```bash
python -m pytest tests/test_check_design_system.py tests/test_check_runtime_style_injection.py tests/test_check_ui_visual_evidence.py -q
python scripts/check_runtime_style_injection.py
git diff --unified=0 "$PR_BASE_SHA" HEAD -- templates > /tmp/design.diff
python scripts/check_design_system.py --mode enforce-added --diff-file /tmp/design.diff
git diff --unified=0 "$PR_BASE_SHA" HEAD -- templates site > /tmp/ui.diff
python scripts/check_ui_visual_evidence.py --diff-file /tmp/ui.diff
```

In GitHub Actions, set `PR_BASE_SHA` from `github.event.pull_request.base.sha`; use the repository's current manifest syntax on fresh main.

- [ ] **Step 2: Register exactly these law ids**

```text
ui.design_system_forward_ratchet
ui.runtime_style_injection
ui.visual_evidence_manifest
```

Each has real `.github/workflows/ci.yml` → `design-governance` wiring. The two new scripts advertise `--selftest`; register them as `selftest:true`.

- [ ] **Step 3: Run meta-validation and hostile controls**

```bash
python3 scripts/check_house_law_registry.py
python3 scripts/check_house_law_registry.py --emit-docs
python3 scripts/run_ci_pack.py --validate-only
```

Then prove three deliberate mutations red: new raw color on a changed template line; new `createElement("style")` beyond baseline; material CSS change without an `EVIDENCE.yml` receipt.

- [ ] **Step 4: Commit and run the full TP-0 verification set**

```bash
git add config/house_law_checks.yml .github/ci/legacy-jobs.yml docs/HOUSE_LAW_CI_GUARD_SUITE.md
git commit -m "ci(design): wire theme-parity governance gates"
python3 -m pytest tests/test_check_design_system.py tests/test_check_runtime_style_injection.py tests/test_check_ui_visual_evidence.py -q
python3 scripts/check_runtime_style_injection.py
python3 scripts/check_house_law_registry.py
python3 scripts/run_ci_pack.py --validate-only
```

---

## TP-0 Acceptance

TP-0 completes when all three hostile defect classes red under the real PR CI job, unchanged legacy debt stays green, the runtime budget cannot grow silently, both agent families carry the dual-theme hard gate, and the PR merges on exact-head concluded CI. TP-0 does not repaint Canada/HK and must not be described as visual production proof.

**Stop condition:** Return merge SHA, CI run IDs, runtime baseline receipt, hostile-control receipts, and any false positives. TP-1 starts only from fresh main after this foundation is canonical.
