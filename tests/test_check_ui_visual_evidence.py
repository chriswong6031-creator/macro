"""tests/test_check_ui_visual_evidence.py — TP-0 Task 3.

Exercises `scripts/check_ui_visual_evidence.py`: the guard that requires a
material user-facing UI change (new CSS lines under templates/*.css, a new
inline <style> in a template, or a new runtime-style-injection signature in a
user-facing JS file) to be mapped, by an EVIDENCE.yml receipt, to an existing
`mastermind.p0_evidence.v2` capture manifest carrying complete dark/light x
en/zh x desktop/mobile evidence.

Fixture manifests use the REAL shape emitted by scripts/capture_page_evidence.py
(see its `entry` dict construction, ~lines 988-1069): base keys `viewport`,
`locale`, `theme`, `access`, `viewport_width`, `viewport_height`, `force_state`
are present on every row; success rows additionally carry `captured`, `file`,
`sha256`, `bytes`, `width`, `height`, `applied_theme`, `applied_locale`; a
FAILED row carries only `{"captured": False, "reason": ...}` and nothing else.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.check_ui_visual_evidence as guard

MANIFEST_SCHEMA = "mastermind.p0_evidence.v2"
RECEIPT_SCHEMA = "mastermind.page_evidence_receipt.v1"

REQUIRED_CELLS = [
    (viewport, locale, theme)
    for viewport in ("desktop", "mobile")
    for locale in ("en", "zh")
    for theme in ("dark", "light")
]
VIEWPORT_WIDTH = {"desktop": 1440, "mobile": 390}
VIEWPORT_HEIGHT = {"desktop": 900, "mobile": 844}


# ---------------------------------------------------------------------------
# fixture builders — mirror capture_page_evidence.py's real emitted shape
# ---------------------------------------------------------------------------


def make_state(viewport: str, locale: str, theme: str, *, file: str = "abcITWreal1234.png",
                captured: bool = True, applied_theme: str | None = None,
                applied_locale: str | None = None, viewport_width: int | None = None,
                force_state: str | None = None, width: int | None = 1440, height: int | None = 900) -> dict:
    entry = {
        "viewport": viewport,
        "locale": locale,
        "theme": theme,
        "access": "anonymous",
        "viewport_width": VIEWPORT_WIDTH[viewport] if viewport_width is None else viewport_width,
        "viewport_height": VIEWPORT_HEIGHT.get(viewport, 900),
        "force_state": force_state,
    }
    if not captured:
        entry.update({"captured": False, "reason": "page did not load"})
        return entry
    entry.update({
        "captured": True,
        "file": file,
        "sha256": "f" * 64,
        "bytes": 12345,
        "width": width,
        "height": height,
        "applied_theme": theme if applied_theme is None else applied_theme,
        "applied_locale": locale if applied_locale is None else applied_locale,
    })
    return entry


def make_full_states() -> list[dict]:
    return [make_state(viewport, locale, theme) for viewport, locale, theme in REQUIRED_CELLS]


def make_manifest(*, page_id: str = "macro:canada_stocks", route: str = "/canada_stocks.html",
                   states: list[dict] | None = None, schema: str = MANIFEST_SCHEMA) -> dict:
    return {
        "schema": schema,
        "pages": [{
            "page_id": page_id,
            "route": route,
            "states": states if states is not None else make_full_states(),
            "gaps": [],
        }],
    }


def write_manifest(root: Path, rel_path: str, manifest: dict, *, write_pngs: bool = True) -> Path:
    manifest_path = root / rel_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    if write_pngs:
        for page in manifest.get("pages", []):
            for state in page.get("states", []):
                file_rel = state.get("file")
                if state.get("captured") and file_rel:
                    png_path = manifest_path.parent / file_rel
                    png_path.parent.mkdir(parents=True, exist_ok=True)
                    if not png_path.exists():
                        png_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return manifest_path


def write_receipt(root: Path, rel_path: str, *, changed_paths: list[str], manifest: str,
                   schema: str = RECEIPT_SCHEMA, extra: dict | None = None) -> Path:
    receipt_path = root / rel_path
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema": schema, "changed_paths": changed_paths, "manifest": manifest}
    if extra:
        body.update(extra)
    text = "\n".join(f"{k}: {json.dumps(v)}" for k, v in body.items()) + "\n"
    receipt_path.write_text(text, encoding="utf-8")
    return receipt_path


def css_diff(path: str = "templates/stock-dashboard.css") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,0 +2,1 @@\n"
        "+.new-panel { color: red; }\n"
    )


def non_material_diff(path: str = "scripts/some_engine_module.py") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,0 +2,1 @@\n"
        '+print("hello")\n'
    )


# ---------------------------------------------------------------------------
# material-change detection + diff parsing
# ---------------------------------------------------------------------------


def test_parse_added_lines_skips_no_newline_marker():
    diff = (
        "diff --git a/templates/x.css b/templates/x.css\n"
        "--- a/templates/x.css\n"
        "+++ b/templates/x.css\n"
        "@@ -1,0 +2,1 @@\n"
        "+.a{color:#fff}\n"
        "\\ No newline at end of file\n"
    )
    added = guard.parse_added_lines(diff)
    assert added["templates/x.css"] == [".a{color:#fff}"]


def test_material_paths_detects_new_css_lines():
    added = guard.parse_added_lines(css_diff())
    material = guard.material_paths(added)
    assert "templates/stock-dashboard.css" in material


def test_material_paths_detects_inline_style_tag_in_template():
    diff = (
        "diff --git a/templates/some_page.html.j2 b/templates/some_page.html.j2\n"
        "--- a/templates/some_page.html.j2\n"
        "+++ b/templates/some_page.html.j2\n"
        "@@ -1,0 +2,1 @@\n"
        "+<style>.x{color:red}</style>\n"
    )
    added = guard.parse_added_lines(diff)
    material = guard.material_paths(added)
    assert "templates/some_page.html.j2" in material


def test_material_paths_detects_runtime_style_injection_in_js():
    diff = (
        "diff --git a/site/some_widget.js b/site/some_widget.js\n"
        "--- a/site/some_widget.js\n"
        "+++ b/site/some_widget.js\n"
        "@@ -1,0 +2,1 @@\n"
        "+document.createElement('style');\n"
    )
    added = guard.parse_added_lines(diff)
    material = guard.material_paths(added)
    assert "site/some_widget.js" in material


def test_material_paths_ignores_non_material_python_change():
    added = guard.parse_added_lines(non_material_diff())
    material = guard.material_paths(added)
    assert material == set()


def _css_only(added_line: str) -> set[str]:
    """material_paths() for a diff adding exactly one line to a templates CSS file."""
    diff = (
        "diff --git a/templates/stock-dashboard.css b/templates/stock-dashboard.css\n"
        "--- a/templates/stock-dashboard.css\n"
        "+++ b/templates/stock-dashboard.css\n"
        "@@ -1,0 +2,1 @@\n"
        f"+{added_line}\n"
    )
    return guard.material_paths(guard.parse_added_lines(diff))


# This gate FAILS CLOSED, so an over-broad "material" verdict is a fleet-wide
# block on ordinary PRs — the fastest way to get the whole guard disabled. A
# comment or a blank line cannot change a rendered pixel and must never demand
# an eight-cell dual-theme evidence matrix. Regression guard: an earlier
# implementation accepted the added lines and never inspected them, so adding a
# CSS comment demanded a full evidence packet.
#
# NOTE (R4): " * continuation inside a block comment" and a lone "*/" used to
# live in this list under the OLD line-local `startswith("*")` heuristic. R4
# deletes that heuristic entirely in favor of a per-file state machine that
# tracks an actual `/*`...`*/` open/close across the added lines IN ORDER — a
# single added line with no `/*` opener anywhere in the SAME diff is genuinely
# ambiguous (the real opener may be unchanged context outside this hunk), and
# this gate resolves that ambiguity toward MATERIAL, its documented
# fail-closed direction. See
# test_material_paths_ambiguous_single_line_comment_fragments_fail_closed
# below for the (now correct) outcome on those two lines.
@pytest.mark.parametrize(
    "line",
    [
        "/* TODO: extract lane tokens in TP-1 */",
        "",
        "   ",
        "/* opening a block comment",
    ],
)
def test_material_paths_ignores_comment_or_blank_css_lines(line):
    assert _css_only(line) == set()


def _css_multi(added_lines: list[str], path: str = "templates/stock-dashboard.css") -> set[str]:
    """material_paths() for a diff adding MULTIPLE lines, IN ORDER, to one
    templates CSS file — exercises the R4 state machine across lines."""
    hunk = "\n".join(f"+{ln}" for ln in added_lines)
    diff = (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,0 +2,{len(added_lines)} @@\n"
        f"{hunk}\n"
    )
    return guard.material_paths(guard.parse_added_lines(diff))


@pytest.mark.parametrize(
    "line",
    [
        "* { margin: 0 }",
        "*, *::before { box-sizing: border-box }",
    ],
)
def test_material_paths_universal_selector_is_not_a_comment_continuation(line):
    """R4 false-negative fix: a universal-selector rule is real CSS — a
    global reset is exactly a pixel-changing change — not a comment
    continuation just because it happens to start with `*`."""
    assert _css_multi([line]) == {"templates/stock-dashboard.css"}


def test_material_paths_multiline_block_comment_stays_ignored_across_lines():
    """R4 false-positive fix: a genuine multi-line block comment, with a
    continuation line carrying no leading `*` at all, must stay non-material
    across the WHOLE span — the state machine tracks the open comment across
    added lines instead of judging each line in isolation."""
    lines = [
        "/* TP-1 audit note:",
        "   the canada composer owns its own palette",
        "*/",
    ]
    assert _css_multi(lines) == set()


def test_material_paths_ambiguous_single_line_comment_fragments_fail_closed():
    """A lone `*/` or `*`-prefixed line, with no `/*` opener anywhere in the
    SAME diff (the real opener would be unchanged context outside this hunk),
    is genuinely ambiguous without seeing the whole file. R4 deletes the old
    `startswith("*")` special case, so this now resolves toward MATERIAL —
    the gate's documented fail-closed direction — rather than silently
    skipping the evidence requirement."""
    assert _css_only(" * continuation inside a block comment") == {"templates/stock-dashboard.css"}
    assert _css_only("*/") == {"templates/stock-dashboard.css"}


@pytest.mark.parametrize(
    "line",
    [
        ".mx-stockdash__lane{background:var(--panel-2)}",
        "  color: var(--ink-1);",
        "@media (max-width: 640px) {",
        "}",
        "*/ .x{color:var(--ink-1)}",
        ".y{color:red} /* trailing note */",
    ],
)
def test_material_paths_still_detects_real_css_substance(line):
    assert _css_only(line) == {"templates/stock-dashboard.css"}


# ---------------------------------------------------------------------------
# CLI-level required cases
# ---------------------------------------------------------------------------


def test_non_material_diff_passes_with_no_receipt(tmp_path, capsys):
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=non_material_diff())
    assert rc == 0


def test_material_diff_with_no_receipt_reds(tmp_path, capsys):
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "templates/stock-dashboard.css" in out
    assert out.startswith("::error") or "::error" in out


def test_receipt_with_wrong_manifest_schema_reds(tmp_path, capsys):
    manifest = make_manifest(schema="mastermind.ui_visual_evidence.v1")
    write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/evidence/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "schema" in out


def test_missing_light_cell_reds(tmp_path, capsys):
    states = [make_state(v, l, t) for v, l, t in REQUIRED_CELLS if not (v == "desktop" and l == "en" and t == "light")]
    manifest = make_manifest(states=states)
    write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/evidence/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "desktop/en/light" in out


def test_missing_screenshot_png_reds(tmp_path, capsys):
    manifest = make_manifest()
    manifest_path = write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest, write_pngs=True)
    # Delete exactly one of the referenced PNGs after writing everything else.
    victim_file = manifest["pages"][0]["states"][0]["file"]
    (manifest_path.parent / victim_file).unlink()
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/evidence/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "does not exist" in out or "missing" in out.lower()


def test_applied_theme_mismatch_reds(tmp_path, capsys):
    states = make_full_states()
    # Corrupt exactly one cell's applied_theme so it disagrees with the requested theme.
    for state in states:
        if state["viewport"] == "mobile" and state["locale"] == "zh" and state["theme"] == "dark":
            state["applied_theme"] = "light"
    manifest = make_manifest(states=states)
    write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/evidence/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "applied_theme" in out


def test_complete_eight_cells_passes(tmp_path, capsys):
    manifest = make_manifest()
    write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/evidence/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 0


def test_failed_capture_entry_handled_without_exception(tmp_path, capsys):
    states = make_full_states()
    for state in states:
        if state["viewport"] == "desktop" and state["locale"] == "en" and state["theme"] == "dark":
            failed = {"viewport": "desktop", "locale": "en", "theme": "dark", "access": "anonymous",
                      "viewport_width": 1440, "viewport_height": 900, "force_state": None,
                      "captured": False, "reason": "page load failed"}
            states[states.index(state)] = failed
    manifest = make_manifest(states=states)
    write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/evidence/tp1/manifest.json",
    )
    # Must not raise (e.g. KeyError on a direct index of an absent key).
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "desktop/en/dark" in out


def test_material_path_not_listed_in_any_receipt_reds(tmp_path, capsys):
    # A receipt exists and is otherwise fully valid, but does not own the
    # exact changed path — ownership must be an EXACT match, not "some receipt
    # exists somewhere".
    manifest = make_manifest()
    write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/some_other_file.css"],
        manifest="mockups/evidence/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "templates/stock-dashboard.css" in out


def test_receipt_with_extra_key_is_rejected(tmp_path, capsys):
    manifest = make_manifest()
    write_manifest(tmp_path, "mockups/evidence/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/evidence/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/evidence/tp1/manifest.json",
        extra={"screenshot_cells": []},
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 1
    out = capsys.readouterr().out
    assert "unexpected key" in out.lower() or "only" in out.lower()


def test_missing_mockups_evidence_dir_handled_gracefully(tmp_path, capsys):
    # mockups/evidence/ does not exist on disk at all (real repo state as of
    # TP-0). Only mockups/refs/ exists. The guard must not crash.
    receipts_root = tmp_path / "mockups" / "refs"
    receipts_root.mkdir(parents=True)
    manifest = make_manifest()
    write_manifest(tmp_path, "mockups/refs/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/refs/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/refs/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 0


# ---------------------------------------------------------------------------
# --selftest
# ---------------------------------------------------------------------------


def test_selftest_exits_zero():
    assert guard.run_selftest() == 0


def test_selftest_literal_substring_present_in_source():
    # House-law meta-guard (Pass D) greps the source for the literal substring
    # "selftest" to trust a selftest:true registry entry.
    source = Path(guard.__file__).read_text(encoding="utf-8")
    assert "selftest" in source


# ---------------------------------------------------------------------------
# R1: diff-header path normalization, verified against a REAL `git diff` —
# a hand-written diff cannot reproduce git's own escaping.
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.test",
         "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _real_diff(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "diff", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


def test_parse_added_lines_real_git_diff_path_with_a_space(tmp_path):
    """Git appends a literal TAB after a `+++ b/<path>` header when the path
    contains a space. Verified against a REAL `git diff` — a hand-written
    fixture cannot reproduce the tab, so it would let this bug back in."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    target = repo / "templates" / "panel v2.css"
    target.parent.mkdir(parents=True)
    target.write_text(".x{color:#111}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    target.write_text(".x{color:#111}\n.y{color:#ff0044}\n", encoding="utf-8")
    diff = _real_diff(repo, "--unified=0", "--", "templates")
    assert "\t" in diff.splitlines()[3]  # sanity: git really appended the tab
    added = guard.parse_added_lines(diff)
    assert added == {"templates/panel v2.css": [".y{color:#ff0044}"]}


def test_parse_added_lines_real_git_diff_non_ascii_quoted_path(tmp_path):
    """Git double-quotes (with octal byte escapes) a path containing a
    non-ASCII byte. Verified against a REAL `git diff` — the naive
    `header.startswith("b/")` test this replaces is defeated outright by the
    leading quote character, silently setting path=None on a real path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    target = repo / "templates" / "panél.css"
    target.parent.mkdir(parents=True)
    target.write_text(".x{color:#111}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    target.write_text(".x{color:#111}\n.y{color:#ff0044}\n", encoding="utf-8")
    diff = _real_diff(repo, "--unified=0", "--", "templates")
    assert diff.splitlines()[3].startswith('+++ "b/')  # sanity: git really quoted it
    added = guard.parse_added_lines(diff)
    assert added == {"templates/panél.css": [".y{color:#ff0044}"]}


def test_parse_added_lines_real_git_diff_space_and_non_ascii_combined(tmp_path):
    """A path with BOTH a space and a non-ASCII byte is quoted AND carries the
    trailing tab — order of operations matters (strip the tab first, THEN
    unquote), or the tab rides into the quoted string and defeats unquoting."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    target = repo / "templates" / "pan él two.css"
    target.parent.mkdir(parents=True)
    target.write_text(".x{color:#111}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    target.write_text(".x{color:#111}\n.y{color:#ff0044}\n", encoding="utf-8")
    diff = _real_diff(repo, "--unified=0", "--", "templates")
    header = diff.splitlines()[3]
    assert header.startswith('+++ "b/') and "\t" in header  # sanity: both shapes present
    added = guard.parse_added_lines(diff)
    assert added == {"templates/pan él two.css": [".y{color:#ff0044}"]}


# ---------------------------------------------------------------------------
# R5: a non-UTF-8 byte in --diff-file must produce a finding, never crash.
# ---------------------------------------------------------------------------


def test_diff_file_with_a_non_utf8_byte_does_not_crash(tmp_path, capsys):
    """errors='replace' on the --diff-file read, matching
    check_design_system.py's own diff read."""
    diff_path = tmp_path / "design.diff"
    raw = (
        b"diff --git a/templates/stock-dashboard.css b/templates/stock-dashboard.css\n"
        b"--- a/templates/stock-dashboard.css\n"
        b"+++ b/templates/stock-dashboard.css\n"
        b"@@ -1,0 +2,1 @@\n"
        b"+.new-panel { color: r\xe9d; }\n"
    )
    diff_path.write_bytes(raw)
    rc = guard.main(["--diff-file", str(diff_path), "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "templates/stock-dashboard.css" in out


# ---------------------------------------------------------------------------
# R9: refuse rather than false-red when mockups/ is sparse-omitted.
# ---------------------------------------------------------------------------


def test_material_change_with_mockups_sparse_omitted_refuses(tmp_path, monkeypatch, capsys):
    """Mirrors check_runtime_style_injection.py's own sparse refusal: a
    checkout where `mockups/` is entirely sparse-omitted must REFUSE rather
    than silently report every material change as missing evidence."""
    import scripts.worktree_sparse as ws
    monkeypatch.setattr(ws, "missing_dirs", lambda root: ["mockups"])
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    out = capsys.readouterr().out
    assert rc == 1
    assert "REFUSED" in out
    assert "mockups" in out
    assert "worktree_sparse.py full" in out


def test_non_material_change_is_unaffected_by_mockups_sparse_omission(
        tmp_path, monkeypatch, capsys):
    """The refusal is scoped to the material-change branch — a non-material
    diff never touches mockups/ anyway and must pass on a sparse checkout."""
    import scripts.worktree_sparse as ws
    monkeypatch.setattr(ws, "missing_dirs", lambda root: ["mockups"])
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=non_material_diff())
    assert rc == 0


def test_mockups_evidence_subdir_absence_is_not_a_sparse_refusal(tmp_path, capsys):
    """R9's refusal must never fire on the ordinary, expected absence of
    mockups/evidence/ alone (that subdirectory not existing in git yet — the
    real repo state as of TP-0) — only on the whole `mockups/` top-level
    tracked directory being sparse-omitted. tmp_path is not a git checkout at
    all, so missing_dirs() answers [] here regardless."""
    receipts_root = tmp_path / "mockups" / "refs"
    receipts_root.mkdir(parents=True)
    manifest = make_manifest()
    write_manifest(tmp_path, "mockups/refs/tp1/manifest.json", manifest)
    write_receipt(
        tmp_path, "mockups/refs/tp1/EVIDENCE.yml",
        changed_paths=["templates/stock-dashboard.css"],
        manifest="mockups/refs/tp1/manifest.json",
    )
    rc = guard.main(["--diff-file", "-", "--repo-root", str(tmp_path)],
                     stdin_text=css_diff())
    assert rc == 0


# ---------------------------------------------------------------------------
# Duplicated-constant pin: a silent desync here silently degrades this gate's
# material-change / viewport-identity detection with no failing test to catch
# it. Assert agreement so a future change to either OWNER fails loudly here.
# ---------------------------------------------------------------------------


def test_hardcoded_constants_agree_with_their_owners():
    import scripts.capture_page_evidence as cpe
    import scripts.check_runtime_style_injection as rsi

    # VIEWPORT_WIDTHS duplicates capture_page_evidence.VIEWPORTS's widths for
    # the two viewports this gate requires (desktop, mobile).
    for viewport, width in guard.VIEWPORT_WIDTHS.items():
        assert viewport in cpe.VIEWPORTS, (
            f"{viewport!r} is missing from capture_page_evidence.VIEWPORTS")
        assert cpe.VIEWPORTS[viewport][0] == width, (
            f"{viewport!r}: check_ui_visual_evidence.VIEWPORT_WIDTHS={width} but "
            f"capture_page_evidence.VIEWPORTS width={cpe.VIEWPORTS[viewport][0]}")

    # RUNTIME_STYLE_SIGNATURES duplicates check_runtime_style_injection.PATTERNS
    # (a tuple of compiled patterns here vs a name-keyed dict there — compare
    # by regex source, not container shape).
    guard_patterns = {p.pattern for p in guard.RUNTIME_STYLE_SIGNATURES}
    owner_patterns = {p.pattern for p in rsi.PATTERNS.values()}
    assert guard_patterns == owner_patterns


# ---------------------------------------------------------------------------
# CI wiring pin: an unresolvable comparison base must FAIL, never report green.
#
# Sol REQUEST_CHANGES 2026-08-27 on head 0ded150fe4e3. Both diff-scoped steps
# treated a failed `git merge-base` as `::warning` + `exit 0`, so the two
# forward-only gates could be skipped while design-governance went green. The
# warning text even said so ("this job is green WITHOUT it") — a gate that
# announces it did not run is not a degraded pass, it is an absent gate, which
# is the exact defect class TP-0 exists to prevent (the #1195 shallow-cut
# family). Discriminating: this fails if either path is mutated back to exit 0.
# ---------------------------------------------------------------------------


def _design_governance_steps():
    import yaml

    manifest = guard.REPO_ROOT / ".github" / "ci" / "legacy-jobs.yml"
    jobs = yaml.safe_load(manifest.read_text(encoding="utf-8"))["jobs"]
    assert "design-governance" in jobs, (
        "the design-governance job is gone from .github/ci/legacy-jobs.yml; "
        "TP-0's three guards would then be wired to nothing")
    return jobs["design-governance"]["steps"]


def test_diff_scoped_steps_fail_closed_without_a_comparison_base():
    base_dependent = [
        s for s in _design_governance_steps()
        if "merge-base" in (s.get("run") or "")
    ]
    # Both TP-0 diff-scoped gates depend on the base: the forward-only design
    # ratchet and the visual-evidence gate. Deleting one to satisfy the
    # per-step assertions below fails here instead.
    assert len(base_dependent) == 2, (
        "expected exactly 2 base-dependent design-governance steps "
        f"(forward-only ratchet + visual evidence), found {len(base_dependent)}")

    for step in base_dependent:
        run = step["run"]
        name = step.get("name", "<unnamed>")
        assert "exit 0" not in run, (
            f"design-governance step {name!r} exits 0 when the canonical "
            "comparison base cannot be resolved. That reports GREEN for a gate "
            "that never ran — the fail-open Sol blocked on 2026-08-27. "
            "Use ::error + a nonzero exit.")
        assert "exit 1" in run, (
            f"design-governance step {name!r} has no failing exit path for an "
            "unresolvable comparison base")
        assert "::error" in run, (
            f"design-governance step {name!r} must annotate the missing base "
            "with ::error so an absent gate is visible in the run summary")
