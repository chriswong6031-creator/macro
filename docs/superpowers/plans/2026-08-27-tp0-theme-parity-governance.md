# TP-0 Theme-Parity Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new user-facing presentation debt fail closed: no new raw design decisions on changed UI lines, no new opaque runtime stylesheet systems, and no material stylesheet change without durable dual-theme visual evidence.

**Architecture:** Extend the existing design-system checker, house-law registry, CI-pack manifest, page-evidence conventions, and agent instructions. Keep the existing `templates/` design-system scan-root contract intact; add a separate runtime-style guard for JavaScript injection rather than widening `check_design_system.py` into another whole-repo walker. Evidence presence is checked mechanically, while visual quality remains a human/Opus review decision.

**Tech Stack:** Python 3.12 stdlib + PyYAML, Git unified diff, GitHub Actions logical jobs in `.github/ci/legacy-jobs.yml`, existing Mastermind page-evidence harness, Markdown agent/PR instructions.

**Spec:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Approval:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_APPROVAL_2026-08-27.md`

## Global Constraints

- Fresh-pickup from current `origin/main`; the planning reconciliation base was `463bb3b4b708a4748fc65a04250366ca94205186`, not an execution authorization.
- Re-pin the protected Sol Skillpack and re-check open PR/path collisions immediately before modifying work.
- Preserve `scripts/check_design_system.py` closure legibility: the checker itself names only the `templates` scan root and makes no subprocess call.
- Do not create a second design system, token root, page registry, evidence plane, or UI lifecycle.
- Legacy debt must not suddenly red the estate; TP-0 is forward-only for changed decisions plus full blocking on already-compliant regions.
- Visual evidence CI proves presence/identity/file integrity only; it does not score beauty or auto-accept screenshots.
- All new `scripts/check_*.py` guards must be registered in `config/house_law_checks.yml` and wired to a real logical CI job before merge.
- Use TDD: each guard is first proven red against a planted hostile fixture and only then implemented.

---

## File Structure

**Modify**
- `scripts/check_design_system.py` — add precise added-line enforcement without changing its scan-root ownership.
- `tests/test_check_design_system.py` — hostile-diff tests for the added-line mode.
- `CLAUDE.md` — repository-wide dual-theme execution law.
- `AGENTS.md` — same durable law for non-Claude agents.
- `.claude/agents/designer.md` — explicit two-art-direction design duty.
- `.claude/agents/builder.md` — block/partial rule when light art direction/evidence is absent.
- `.claude/agents/reviewer.md` — `PASS` requires both themes judged as designs.
- `.github/PULL_REQUEST_TEMPLATE/design_migration.md` — add a required THEME ART DIRECTION section and explicit evidence identity.
- `config/house_law_checks.yml` — register the three design-governance guards.
- `.github/ci/legacy-jobs.yml` — add one bounded logical `design-governance` job.

**Create**
- `scripts/check_runtime_style_injection.py` — ratcheted runtime-style injection fence.
- `tests/test_check_runtime_style_injection.py` — hostile fixture coverage.
- `config/runtime_style_injection_allowlist.json` — exact current legacy budgets; Canada/HK budgets are later ratcheted to zero by TP-1/TP-2.
- `scripts/check_ui_visual_evidence.py` — diff-triggered committed evidence-manifest verifier.
- `tests/test_check_ui_visual_evidence.py` — manifest/diff/PNG-dimension hostile fixtures.
- `config/ui_visual_evidence.yml` — mechanical trigger/evidence contract; no taste scoring.

---

### Task 1: Add diff-aware forward-only enforcement to the existing design-system checker

**Files:**
- Modify: `scripts/check_design_system.py`
- Modify: `tests/test_check_design_system.py`

**Interfaces:**
- Consumes: unified diff text generated externally by Git/CI; current `scan()` / `scan_text()` findings.
- Produces: `parse_added_line_numbers(diff_text: str) -> dict[str, set[int]]`, `added_blocking_findings(findings, added_lines) -> list[Finding]`, CLI mode `enforce-added`.
- `enforce-added` blocks rules `color-literal`, `font-family-literal`, `radius-literal`, `literal-custom-property`, `emoji`, and `parallel-token-root` only when the finding's head-file line is newly added.

- [ ] **Step 1: Write failing tests for added-line parsing and blocking scope**

Add to `tests/test_check_design_system.py`:

```python
def test_enforce_added_blocks_new_literal_but_spares_unchanged_legacy(tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "legacy.css", ".old{color:#abcdef}\n.new{color:#ff0044}\n")
    diff = """diff --git a/templates/legacy.css b/templates/legacy.css
--- a/templates/legacy.css
+++ b/templates/legacy.css
@@ -1,0 +2,1 @@
+.new{color:#ff0044}
"""
    diff_path = tmp_path / "ui.diff"
    diff_path.write_text(diff, encoding="utf-8")
    code = DS.main([
        "--mode", "enforce-added", "--root", str(tmp_path),
        "--diff-file", str(diff_path),
    ])
    out = capsys.readouterr().out
    assert code == 1
    assert "legacy.css:2" in out
    assert "legacy.css:1" not in out


def test_enforce_added_blocks_new_emoji_and_parallel_root(tmp_path: Path, capsys) -> None:
    write_template(
        tmp_path,
        "new.css",
        ':root{--page-tone:var(--panel)}\n.x::before{content:"😀"}\n',
    )
    diff = """diff --git a/templates/new.css b/templates/new.css
new file mode 100644
--- /dev/null
+++ b/templates/new.css
@@ -0,0 +1,2 @@
+:root{--page-tone:var(--panel)}
+.x::before{content:"😀"}
"""
    diff_path = tmp_path / "ui.diff"
    diff_path.write_text(diff, encoding="utf-8")
    assert DS.main([
        "--mode", "enforce-added", "--root", str(tmp_path),
        "--diff-file", str(diff_path),
    ]) == 1
    out = capsys.readouterr().out
    assert "parallel-token-root" in out
    assert "emoji" in out
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing mode/functions**

Run:

```bash
python3 -m pytest tests/test_check_design_system.py -q
```

Expected: the newly added tests fail because `enforce-added`, `--diff-file`, and/or `parallel-token-root` do not exist yet; all pre-existing tests remain unchanged.

- [ ] **Step 3: Implement precise head-line extraction from unified diff**

Add a pure parser; do not shell out from the checker:

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
        m = HUNK_RE.match(raw)
        if m:
            new_line = int(m.group(1))
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

- [ ] **Step 4: Add a structural `parallel-token-root` finding to full-file scanning**

Define a block regex and emit the finding at the `:root` selector line whenever a non-theme source creates a root custom-property family, even when the values are derivations:

```python
ROOT_TOKEN_BLOCK_RE = re.compile(r":root\s*\{(?P<body>.*?)\}", re.DOTALL)


def root_token_findings(rel_path: str, cleaned: str) -> list[Finding]:
    if rel_path == THEME_CSS:
        return []
    out: list[Finding] = []
    for match in ROOT_TOKEN_BLOCK_RE.finditer(cleaned):
        if not CUSTOM_PROP_RE.search(match.group("body")):
            continue
        line = cleaned.count("\n", 0, match.start()) + 1
        out.append(Finding(
            "parallel-token-root", rel_path, line,
            "custom-property family declared under :root outside theme.css",
        ))
    return out
```

Call it from `scan_text()` after line-level findings.

- [ ] **Step 5: Add `enforce-added` without weakening existing `report` / `enforce` semantics**

Add:

```python
MODES = ("report", "enforce", "enforce-added")
ADDED_BLOCKING_RULES = frozenset(BLOCKING_RULES) | {"emoji", "parallel-token-root"}


def added_blocking_findings(
    findings: Iterable[Finding], added_lines: dict[str, set[int]]
) -> list[Finding]:
    return [
        f for f in findings
        if f.rule in ADDED_BLOCKING_RULES and f.line in added_lines.get(f.path, set())
    ]
```

Add `--diff-file`, where `-` means `sys.stdin.read()`. `enforce-added` must require diff input and return 1 only for `added_blocking_findings`; it still prints all findings as context, but unchanged debt does not block.

- [ ] **Step 6: Re-run the checker test suite**

Run:

```bash
python3 -m pytest tests/test_check_design_system.py -q
python3 scripts/check_design_system.py --self-check
```

Expected: all tests pass and the existing report/enforce contracts remain intact.

- [ ] **Step 7: Mutation-check the new mode**

Temporarily remove `emoji` from `ADDED_BLOCKING_RULES` and verify `test_enforce_added_blocks_new_emoji_and_parallel_root` fails; restore. Then change the parser so deleted lines increment `new_line` and verify the literal-line test fails; restore.

- [ ] **Step 8: Commit Task 1**

```bash
git add scripts/check_design_system.py tests/test_check_design_system.py
git commit -m "fix(design): enforce new UI decisions forward-only"
```

---

### Task 2: Build the runtime-style injection ratchet

**Files:**
- Create: `scripts/check_runtime_style_injection.py`
- Create: `tests/test_check_runtime_style_injection.py`
- Create: `config/runtime_style_injection_allowlist.json`

**Interfaces:**
- Consumes: user-facing `.js` files under `templates/` and `site/` plus the committed allowlist.
- Produces: deterministic per-file counts for `create_style`, `style_text`, `insert_rule`, and `style_markup`; exit 1 when a file/pattern exceeds its frozen allowance or a new injecting file appears.
- The guard never judges CSS quality; it prevents presentation systems from escaping the governed stylesheet layer.

- [ ] **Step 1: Write hostile-fixture tests**

Create `tests/test_check_runtime_style_injection.py` with fixtures like:

```python
def test_new_runtime_stylesheet_file_fails(tmp_path: Path) -> None:
    root = tmp_path
    (root / "site").mkdir()
    (root / "templates").mkdir()
    (root / "config").mkdir()
    (root / "site" / "new-ui.js").write_text(
        'const s=document.createElement("style");s.textContent=".x{color:red}";',
        encoding="utf-8",
    )
    allow = root / "config" / "runtime_style_injection_allowlist.json"
    allow.write_text('{"schema":"mastermind.runtime_style_allowlist.v1","files":{}}')
    assert RSI.run(root, allow) == 1


def test_budget_can_only_stay_equal_or_shrink(tmp_path: Path) -> None:
    # allowance says one style creation; fixture contains two
    ...
    assert RSI.run(root, allow) == 1
```

The second test's concrete fixture must write exactly two `document.createElement("style")` calls and an allowance of `{"create_style": 1}`.

- [ ] **Step 2: Verify tests fail before the guard exists**

Run:

```bash
python3 -m pytest tests/test_check_runtime_style_injection.py -q
```

Expected: import/module failure.

- [ ] **Step 3: Implement the scanner and exact budget contract**

Use these signatures:

```python
PATTERNS = {
    "create_style": re.compile(r"createElement\(\s*['\"]style['\"]\s*\)"),
    "style_text": re.compile(r"(?:style|css)\.textContent\s*="),
    "insert_rule": re.compile(r"\.sheet\.insertRule\s*\("),
    "style_markup": re.compile(r"<style(?:\s|>)", re.IGNORECASE),
}


def scan_file(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {name: len(rx.findall(text)) for name, rx in PATTERNS.items()}
```

The allowlist schema is:

```json
{
  "schema": "mastermind.runtime_style_allowlist.v1",
  "generated_from": "<git sha recorded by the implementation worker>",
  "files": {
    "site/example.js": {"create_style": 1, "style_text": 1, "insert_rule": 0, "style_markup": 0}
  }
}
```

Rules:

1. a non-zero actual count in an unlisted file is hard red;
2. `actual > allowed` is hard red;
3. `actual < allowed` prints a `::notice` instructing the same PR to lower/remove the stale budget;
4. zero-count files do not need allowlist rows;
5. paired template/site copies may each have rows because the guard scans both actual delivery sources.

- [ ] **Step 4: Generate the initial baseline from the current fresh main tree**

Add a `--emit-baseline` mode that writes JSON to stdout, then run from a full checkout:

```bash
python3 scripts/check_runtime_style_injection.py --emit-baseline \
  > config/runtime_style_injection_allowlist.json
```

Immediately run:

```bash
python3 scripts/check_runtime_style_injection.py
```

Expected: exit 0 with no over-budget findings. Keep the generated exact counts; do not manually widen them.

- [ ] **Step 5: Add an explicit test that Canada/HK are represented while legacy injection exists**

The repository-level test reads the committed config and, only while the files still contain an injection, asserts that `site/canada-stock-v36.js` and `site/hk-stock-v36.js` have finite exact budgets. This test is intentionally removed/rekeyed in TP-1/TP-2 when the actual counts reach zero.

- [ ] **Step 6: Run tests and self-check**

Run:

```bash
python3 -m pytest tests/test_check_runtime_style_injection.py -q
python3 scripts/check_runtime_style_injection.py --selftest
python3 scripts/check_runtime_style_injection.py
```

Expected: all green.

- [ ] **Step 7: Mutation-check the guard**

Plant one extra `createElement("style")` in a temporary copied JS file with the committed allowance and verify exit 1. Increase the allowance without changing the file and verify the stale-budget test/notice catches the attempted permanent widening in review.

- [ ] **Step 8: Commit Task 2**

```bash
git add scripts/check_runtime_style_injection.py tests/test_check_runtime_style_injection.py config/runtime_style_injection_allowlist.json
git commit -m "feat(design): fence runtime stylesheet injection"
```

---

### Task 3: Require durable dual-theme evidence for material stylesheet decisions

**Files:**
- Create: `scripts/check_ui_visual_evidence.py`
- Create: `tests/test_check_ui_visual_evidence.py`
- Create: `config/ui_visual_evidence.yml`

**Interfaces:**
- Consumes: the PR's unified diff via `--diff-file`, repository files, committed manifest JSON under `mockups/evidence/manifests/`.
- Produces: exit 1 when a material stylesheet decision is present but no valid manifest covering the changed path exists.
- Mechanical trigger scope: changed `.css` under `templates/`; added inline `<style` under `templates/*.j2`; added runtime-style injection signatures under `templates/*.js` or `site/*.js`.

- [ ] **Step 1: Write failing manifest-contract tests**

Create tests for: no manifest → red; missing one light cell → red; missing PNG → red; wrong width → red; complete eight-cell + full-page manifest → green.

Use a minimal valid manifest fixture:

```python
manifest = {
    "schema": "mastermind.ui_visual_evidence.v1",
    "routes": ["/canada_stocks.html"],
    "changed_paths": ["templates/stock-dashboard.css"],
    "cells": [
        {"theme": theme, "locale": locale, "viewport": viewport, "path": path}
        for theme in ("dark", "light")
        for locale in ("en", "zh")
        for viewport, path in (("1440x900", "shot-1440.png"), ("390x844", "shot-390.png"))
    ],
    "full_page": "fullpage-dark-en-1440.png",
    "state_ownership": {
        "loading": {"owned": False, "reason": "legacy fallback owns pre-mount loading"},
        "empty": {"owned": False, "reason": "surface renders owner-provided empty state"},
        "stale": {"owned": False, "reason": "no composer-owned stale state"},
        "error": {"owned": False, "reason": "mount failure falls back to legacy page"}
    },
}
```

For the PNG fixture, write a real PNG header/IHDR using stdlib `struct`/`zlib` so dimension checks are non-vacuous.

- [ ] **Step 2: Verify tests fail before implementation**

Run:

```bash
python3 -m pytest tests/test_check_ui_visual_evidence.py -q
```

Expected: module import failure.

- [ ] **Step 3: Implement material-diff detection**

Reuse a local pure unified-diff parser in this guard; do not import Git or call subprocess. A path is material when:

```python
def is_material_change(path: str, added_lines: list[str]) -> bool:
    if path.startswith("templates/") and path.endswith(".css"):
        return bool(added_lines)
    joined = "\n".join(added_lines)
    if path.startswith("templates/") and path.endswith((".j2", ".html")):
        return "<style" in joined.lower()
    if path.endswith(".js") and path.startswith(("templates/", "site/")):
        return bool(re.search(
            r"createElement\(\s*['\"]style|\.textContent\s*=|\.sheet\.insertRule|<style(?:\s|>)",
            joined,
            re.IGNORECASE,
        ))
    return False
```

This gate deliberately does **not** claim that every copy/DOM-only edit is visually material; the durable agent/review law in Task 4 remains broader than this mechanical minimum.

- [ ] **Step 4: Validate exact evidence identity and PNG dimensions**

Required cell identities are the Cartesian product:

```python
REQUIRED = {
    (theme, locale, viewport)
    for theme in ("dark", "light")
    for locale in ("en", "zh")
    for viewport in ("1440x900", "390x844")
}
```

Read PNG width/height from IHDR. Desktop cells must have width 1440; mobile cells width 390. Height may exceed the nominal viewport for full-page captures, but may not be zero or smaller than the nominal viewport height when the manifest declares a viewport shot.

Every material changed path must appear in at least one manifest's `changed_paths`. The referenced files must exist. `full_page` is mandatory. Each of the four state keys must either name a shot path with `owned: true` or an explicit non-empty reason with `owned: false`.

- [ ] **Step 5: Create the committed mechanical config**

`config/ui_visual_evidence.yml`:

```yaml
schema: mastermind.ui_visual_evidence_gate.v1
manifest_root: mockups/evidence/manifests
required_themes: [dark, light]
required_locales: [en, zh]
required_viewports: ["1440x900", "390x844"]
state_keys: [loading, empty, stale, error]
```

No aesthetic thresholds or pixel scores belong in this file.

- [ ] **Step 6: Run focused tests and self-check**

```bash
python3 -m pytest tests/test_check_ui_visual_evidence.py -q
python3 scripts/check_ui_visual_evidence.py --selftest
```

Expected: green.

- [ ] **Step 7: Commit Task 3**

```bash
git add scripts/check_ui_visual_evidence.py tests/test_check_ui_visual_evidence.py config/ui_visual_evidence.yml
git commit -m "feat(design): require dual-theme UI evidence manifests"
```

---

### Task 4: Make theme art direction a durable designer/builder/reviewer contract

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `.claude/agents/designer.md`
- Modify: `.claude/agents/builder.md`
- Modify: `.claude/agents/reviewer.md`
- Modify: `.github/PULL_REQUEST_TEMPLATE/design_migration.md`

**Interfaces:**
- Consumes: existing design-system/doctrine precedence.
- Produces: one consistent operator contract visible to Claude, Codex/other agents, designers, builders, reviewers, and design-migration PR authors.

- [ ] **Step 1: Add a single canonical rule block to `CLAUDE.md` and mirror it in `AGENTS.md`**

Add under the existing Design System section, preserving current precedence text:

```markdown
### Theme art direction — hard gate

Dark and light are two art directions of one semantic system, never palette inversion.
Every material user-facing design/implementation packet MUST name:
- DARK TREATMENT;
- LIGHT TREATMENT;
- MECHANISMS THAT INTENTIONALLY DIFFER;
- reference/baseline evidence;
- theme-specific failure/degraded states;
- the required dark/light × EN/ZH × desktop/mobile evidence matrix.

A builder may not satisfy light mode by token substitution alone unless the frozen design explicitly
argues why the same material mechanism is correct in both luminance environments. Missing light art
direction or missing required visual evidence is PARTIAL/BLOCKED, never PASS. Substantive runtime
stylesheet systems in JavaScript are prohibited; presentation belongs in governed design-system
source. Functional browser success is necessary but not visual acceptance.
```

The two repository files must carry semantically identical law; do not let account-specific memory own this rule.

- [ ] **Step 2: Tighten the designer contract**

Add to `.claude/agents/designer.md` rules:

```markdown
- For every material surface, state the dark and light art directions separately. "Same CSS, tokens swap" is not a design decision unless you explicitly justify why the material mechanism works in both themes.
- Your returned evidence must include both themes at the required widths/locales; a missing light proof makes STATUS PARTIAL/BLOCKED.
```

- [ ] **Step 3: Tighten the builder contract**

Add to `.claude/agents/builder.md`:

```markdown
- A frozen user-facing spec that lacks LIGHT TREATMENT or its required evidence matrix is incomplete: stop PARTIAL/BLOCKED and return the gap; do not invent a light translation.
- Do not create a page/composer-owned runtime stylesheet to bypass theme.css/design-system governance. Use the frozen governed presentation owner.
```

- [ ] **Step 4: Tighten the reviewer contract**

Add to `.claude/agents/reviewer.md`:

```markdown
- For material UI work, PASS requires separate dark and light design adjudication. Verify hierarchy, material depth, semantic color, responsive composition, EN/ZH parity, and required committed evidence. "It renders in light" is not visual acceptance.
- Treat missing light evidence, palette-inversion styling, or an opaque runtime stylesheet bypass as a material finding.
```

- [ ] **Step 5: Add a required THEME ART DIRECTION section to the design-migration PR template**

Insert before the evidence matrix:

```markdown
## Theme art direction — required

### Dark treatment
<!-- Name depth, material, hue, shadow/glow and interaction treatment. -->

### Light treatment
<!-- Name paper/canvas/material hierarchy, shadow/hairline treatment and any mechanisms that differ from dark. -->

### Intentional theme differences
<!-- List the mechanisms that are not shared verbatim and why. -->

- [ ] Light has been judged as a design, not merely rendered after token substitution.
- [ ] No substantive runtime stylesheet was introduced to bypass the governed presentation layer.
```

- [ ] **Step 6: Add source-level tests only if the repository already has instruction-contract tests; otherwise use exact grep assertions in the TP-0 verification command**

Run:

```bash
grep -n "Theme art direction — hard gate" CLAUDE.md AGENTS.md
grep -n "Same CSS, tokens swap" .claude/agents/designer.md
grep -n "runtime stylesheet" .claude/agents/builder.md .claude/agents/reviewer.md
grep -n "Theme art direction — required" .github/PULL_REQUEST_TEMPLATE/design_migration.md
```

Expected: each exact marker appears in the intended owner file.

- [ ] **Step 7: Commit Task 4**

```bash
git add CLAUDE.md AGENTS.md .claude/agents/designer.md .claude/agents/builder.md .claude/agents/reviewer.md .github/PULL_REQUEST_TEMPLATE/design_migration.md
git commit -m "docs(design): make dual-theme art direction a hard agent gate"
```

---

### Task 5: Register and wire all design-governance guards in one bounded CI job

**Files:**
- Modify: `config/house_law_checks.yml`
- Modify: `.github/ci/legacy-jobs.yml`

**Interfaces:**
- Consumes: Task 1 `check_design_system.py`, Task 2 runtime guard, Task 3 evidence guard.
- Produces: logical CI job `design-governance`; house-law registry entries whose wiring checker can prove real invocation.

- [ ] **Step 1: Add the logical CI job**

Append a bounded `design-governance` job to `.github/ci/legacy-jobs.yml` with exact changed-path scope:

```yaml
  design-governance:
    if: ${{ false }}
    gate: code
    scope: exclusive
    paths:
      - "templates/**"
      - "site/**/*.js"
      - "scripts/check_design_system.py"
      - "scripts/check_runtime_style_injection.py"
      - "scripts/check_ui_visual_evidence.py"
      - "tests/test_check_design_system.py"
      - "tests/test_check_runtime_style_injection.py"
      - "tests/test_check_ui_visual_evidence.py"
      - "config/runtime_style_injection_allowlist.json"
      - "config/ui_visual_evidence.yml"
      - "config/product_experience/**"
      - "config/house_law_checks.yml"
      - "CLAUDE.md"
      - "AGENTS.md"
      - ".claude/agents/**"
      - ".github/PULL_REQUEST_TEMPLATE/design_migration.md"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: design guard unit tests
        run: python -m pytest tests/test_check_design_system.py tests/test_check_runtime_style_injection.py tests/test_check_ui_visual_evidence.py -q
      - name: runtime stylesheet injection ratchet
        run: python scripts/check_runtime_style_injection.py
      - name: forward-only design decisions
        shell: bash
        run: |
          git diff --unified=0 "${{ github.event.pull_request.base.sha }}" HEAD -- templates \
            > /tmp/design.diff
          python scripts/check_design_system.py --mode enforce-added --diff-file /tmp/design.diff
      - name: material UI evidence
        shell: bash
        run: |
          git diff --unified=0 "${{ github.event.pull_request.base.sha }}" HEAD -- templates site \
            > /tmp/ui.diff
          python scripts/check_ui_visual_evidence.py --diff-file /tmp/ui.diff
```

The implementation worker must preserve the repository's current run-pack syntax if the manifest schema has advanced on fresh main; the logical job name and command semantics above are binding.

- [ ] **Step 2: Register/update house-law entries**

In `config/house_law_checks.yml`, ensure there is exactly one entry for the existing design-system checker and add the two new guards. Use these law ids:

- `ui.design_system_forward_ratchet`
- `ui.runtime_style_injection`
- `ui.visual_evidence_manifest`

All three use `severity: hard`, `workflow: .github/workflows/ci.yml`, `job: design-governance`, `lane: pr_ci`, and name their test files in `source_ref`. The runtime/evidence guards advertise `--selftest`, so set `selftest: true`.

- [ ] **Step 3: Run the meta-guard and pack validator**

```bash
python3 scripts/check_house_law_registry.py
python3 scripts/check_house_law_registry.py --emit-docs
python3 scripts/run_ci_pack.py --validate-only
```

Expected: zero HARD findings; regenerated `docs/HOUSE_LAW_CI_GUARD_SUITE.md` is included if the meta-guard changes it.

- [ ] **Step 4: Run the full TP-0 local verification set**

```bash
python3 -m pytest \
  tests/test_check_design_system.py \
  tests/test_check_runtime_style_injection.py \
  tests/test_check_ui_visual_evidence.py -q
python3 scripts/check_runtime_style_injection.py
python3 scripts/check_house_law_registry.py
python3 scripts/run_ci_pack.py --validate-only
```

Expected: green.

- [ ] **Step 5: Perform three hostile end-to-end controls**

On a throwaway local mutation, verify each produces non-zero and then restore:

1. add `color:#ff00ff` to a changed line in a legacy template CSS → `enforce-added` red;
2. add `document.createElement("style")` to a previously clean user-facing JS → runtime-style guard red;
3. change `templates/stock-dashboard.css` or a temporary fixture CSS without adding a manifest → visual-evidence guard red.

- [ ] **Step 6: Commit Task 5**

```bash
git add config/house_law_checks.yml .github/ci/legacy-jobs.yml docs/HOUSE_LAW_CI_GUARD_SUITE.md
git commit -m "ci(design): wire theme-parity governance gates"
```

---

## TP-0 Acceptance / Production Proof

TP-0 is complete when:

1. all three hostile defect classes fail locally and in the PR's real CI job;
2. unchanged legacy design debt does not cause the job to red;
3. the runtime allowlist is exact and cannot grow silently;
4. no new `check_*.py` remains unregistered;
5. `CLAUDE.md`, `AGENTS.md`, designer/builder/reviewer contracts all carry the dual-theme hard gate;
6. the design-migration template requires explicit dark/light art direction;
7. fresh PR CI concludes green on the exact head;
8. merge alone is reported as governance built, not as Canada/HK visual repair.

**Stop condition:** TP-0 stops after the governance gates are merged and verified on the real PR CI path. It does not repaint Canada or alter stock-dashboard product semantics.

**Continuation handoff required:** exact merge SHA, CI run IDs, committed runtime baseline, hostile-control receipts, any false positives discovered, and confirmation that TP-1 may start from fresh main.
