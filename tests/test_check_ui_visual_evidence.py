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
@pytest.mark.parametrize(
    "line",
    [
        "/* TODO: extract lane tokens in TP-1 */",
        "",
        "   ",
        " * continuation inside a block comment",
        "/* opening a block comment",
        "*/",
    ],
)
def test_material_paths_ignores_comment_or_blank_css_lines(line):
    assert _css_only(line) == set()


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
