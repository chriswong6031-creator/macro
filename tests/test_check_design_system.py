"""Contracts for scripts/check_design_system.py — the design-system ratchet.

Every rule must catch its own planted violation, a clean fixture must pass, the
two modes must differ in EXIT CODE (report always 0, enforce non-zero), and the
annotations must start the line.

CLOSURE LEGIBILITY (load-bearing, mirrors the script): this module names exactly
ONE scan root, ``templates``, and makes NO subprocess call.  scripts/run_ci_pack.py
widens a job to every scan root named by the modules its commands load, so a
stray literal naming another tree would hand the wired job that whole tree.
Fixtures are built under pytest's ``tmp_path`` and the CLI is driven in-process
through ``main([...])`` for the same reason.

Annotations are asserted through capsys, never caplog: the script prints them
with a bare ``print`` precisely because a logger prefix makes GitHub drop them,
so a caplog assertion would pass while the real output stayed invisible.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.check_design_system as DS  # noqa: E402

TEMPLATES = "templates"


def write_template(root: Path, name: str, body: str) -> Path:
    path = root / TEMPLATES / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# --- rule detection ---------------------------------------------------------

@pytest.mark.parametrize("rule,name,body", [
    ("color-literal", "a.css", ".x{color:#ff0044}"),
    ("color-literal", "a2.css", ".x{color:rgb(1,2,3)}"),
    ("color-literal", "a3.css", ".x{color:hsl(10,20%,30%)}"),
    ("font-family-literal", "b.css", ".x{font-family:Helvetica,sans-serif}"),
    ("radius-literal", "c.css", ".x{border-radius:7px}"),
    ("literal-custom-property", "d.css", ":root{--brand:#123456}"),
    ("literal-custom-property", "d2.css", "body.page-x{--brand:#123456}"),
    ("literal-custom-property", "d3.css", ".scoped .deep{--gap:11px}"),
    ("card-class", "e.css", ".insight-card{padding:0}"),
    ("banned-vocabulary", "f.html.j2", "<p>the falsifier fired</p>"),
    ("banned-vocabulary", "f2.html.j2", "<p>证伪</p>"),
    ("banned-vocabulary", "f3.html.j2", "<p>z-score of 2</p>"),
    ("inline-style-bytes", "g.html.j2", "<style>.x{padding:0}</style>"),
    ("emoji", "h.html.j2", "<p>\U0001F600 hi</p>"),
])
def test_each_rule_catches_its_planted_violation(rule: str, name: str, body: str) -> None:
    hits = {f.rule for f in DS.scan_text(f"{TEMPLATES}/{name}", body)}
    assert rule in hits, f"{rule} missed its own fixture (fired: {sorted(hits)})"


def test_clean_fixture_produces_no_findings() -> None:
    # A SCOPED derived custom property (not `:root`) — a non-theme `:root` block
    # is itself the parallel-token-root violation (TP-0 Task 1), so a fixture
    # meant to prove "this is all legal" must not use one.
    body = (".x{color:var(--ink-1);font-family:var(--font-body);"
            "border-radius:var(--r-2)}\nbody.page-x{--ink-soft:var(--ink-1)}\n")
    assert DS.scan_text(f"{TEMPLATES}/clean.css", body) == []


def test_theme_css_may_declare_literal_tokens() -> None:
    """theme.css IS the palette — rules 1, 2 and 4 must not fire on it."""
    body = ":root{--ink-1:#101418;--font-body:Inter,sans-serif}"
    hits = {f.rule for f in DS.scan_text(DS.THEME_CSS, body)}
    assert "color-literal" not in hits
    assert "literal-custom-property" not in hits
    assert "font-family-literal" not in hits


def test_a_sanctioned_asset_file_is_exempt_from_colour_and_font_rules() -> None:
    sanctioned = sorted(DS.SANCTIONED_LITERAL_FILES - {DS.THEME_CSS})[0]
    hits = {f.rule for f in DS.scan_text(sanctioned, ".x{color:#abcdef}")}
    assert "color-literal" not in hits


def test_a_derived_custom_property_passes_but_a_literal_fallback_does_not() -> None:
    """`--a: var(--b)` is how you extend the palette; a literal fallback is not."""
    derived = DS.scan_text(f"{TEMPLATES}/d.css", ":root{--a:var(--b)}")
    assert [f for f in derived if f.rule == "literal-custom-property"] == []
    fallback = DS.scan_text(f"{TEMPLATES}/d.css", ":root{--a:var(--b,#fff)}")
    assert [f for f in fallback if f.rule == "literal-custom-property"]


def test_radius_token_passes_and_zero_is_inert() -> None:
    assert DS.scan_text(f"{TEMPLATES}/c.css", ".x{border-radius:var(--r-3)}") == []
    assert DS.scan_text(f"{TEMPLATES}/c.css", ".x{border-radius:0}") == []


def test_jinja_expressions_and_fragment_refs_are_not_colour_literals() -> None:
    """Line numbers must survive the blanking, or every report cites the wrong line."""
    body = "\n".join([
        "<a href=\"#abc\">x</a>",
        "{{ '#ff0000' if dark else '#000000' }}",
        "<svg><rect fill=\"url(#fade)\"/></svg>",
        ".real{color:#123456}",
    ])
    findings = DS.scan_text(f"{TEMPLATES}/x.html.j2", body)
    colours = [f for f in findings if f.rule == "color-literal"]
    assert len(colours) == 1
    assert colours[0].line == 4


# --- traversal --------------------------------------------------------------

def test_scan_walks_the_templates_root(tmp_path: Path) -> None:
    write_template(tmp_path, "deep/nested.css", ".x{color:#abcdef}")
    findings = DS.scan(tmp_path)
    assert [f.path for f in findings] == ["templates/deep/nested.css"]


def test_scan_ignores_non_template_suffixes(tmp_path: Path) -> None:
    write_template(tmp_path, "notes.md", "#abcdef")
    assert DS.scan(tmp_path) == []


def test_missing_templates_root_is_not_fatal(tmp_path: Path) -> None:
    assert DS.iter_template_files(tmp_path) == []


# --- governance -------------------------------------------------------------

def _registry(rows: list[dict]) -> dict:
    return {"pages": rows}


def test_governed_templates_reads_only_compliant_rows() -> None:
    registry = _registry([
        {"source_template": "templates/a.html.j2",
         "design_system": {"compliant": True}},
        {"source_template": "templates/b.html.j2",
         "design_system": {"compliant": False}},
    ])
    assert DS.governed_templates(registry) == {"templates/a.html.j2"}


def test_governed_regions_narrow_the_claim_to_their_own_template() -> None:
    registry = _registry([
        {"source_template": "templates/whole.html.j2",
         "design_system": {"compliant": True, "governed_regions": [
             {"template": "templates/shared.html.j2", "region": "body.page-macro"}]}},
    ])
    assert DS.governed_templates(registry) == {"templates/shared.html.j2"}


def test_blocking_covers_governed_and_new_templates_but_not_legacy_ones() -> None:
    findings = [
        DS.Finding("color-literal", "templates/governed.css", 1, "x"),
        DS.Finding("color-literal", "templates/legacy.css", 1, "x"),
        DS.Finding("color-literal", "templates/brand_new.css", 1, "x"),
        DS.Finding("emoji", "templates/governed.css", 1, "x"),
    ]
    governed = {"templates/governed.css"}
    known = {"templates/governed.css", "templates/legacy.css"}
    blocking = DS.blocking_findings(findings, governed, known)
    paths = [f.path for f in blocking]
    assert paths == ["templates/governed.css", "templates/brand_new.css"]
    # rule 8 is warn-tier and must never block
    assert all(f.rule in DS.BLOCKING_RULES for f in blocking)


# --- CLI modes --------------------------------------------------------------

def test_report_mode_exits_zero_even_with_findings(tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}")
    code = DS.main(["--mode", "report", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "color-literal" in out


def test_enforce_mode_exits_nonzero_on_a_blocking_rule(tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}")
    code = DS.main(["--mode", "enforce", "--root", str(tmp_path)])
    capsys.readouterr()
    assert code == 1


def test_enforce_mode_ignores_a_warn_tier_only_violation(tmp_path: Path, capsys) -> None:
    """An emoji is reported but never blocks — rules 5-8 are advisory by design."""
    write_template(tmp_path, "emoji.html.j2", "<p>\U0001F600</p>")
    code = DS.main(["--mode", "enforce", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "emoji" in out


def test_enforce_spares_a_known_but_non_compliant_template(tmp_path: Path, capsys) -> None:
    """The ratchet: legacy surfaces report, they do not block."""
    write_template(tmp_path, "legacy.css", ".x{color:#ff0044}")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(_registry([
        {"source_template": "templates/legacy.css",
         "design_system": {"compliant": False}}])), encoding="utf-8")
    code = DS.main(["--mode", "enforce", "--root", str(tmp_path),
                    "--registry", str(registry)])
    capsys.readouterr()
    assert code == 0


def test_enforce_blocks_a_compliant_template_that_regressed(tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "governed.css", ".x{color:#ff0044}")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(_registry([
        {"source_template": "templates/governed.css",
         "design_system": {"compliant": True}}])), encoding="utf-8")
    code = DS.main(["--mode", "enforce", "--root", str(tmp_path),
                    "--registry", str(registry)])
    capsys.readouterr()
    assert code == 1


def test_report_mode_is_the_default(tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}")
    assert DS.main(["--root", str(tmp_path)]) == 0
    assert "mode=report" in capsys.readouterr().out


# --- output law -------------------------------------------------------------

def test_annotations_start_the_line(tmp_path: Path, capsys) -> None:
    """House law: GitHub drops any annotation that does not START the line."""
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}")
    DS.main(["--mode", "report", "--root", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()
    annotations = [ln for ln in lines if "::notice" in ln or "::error" in ln
                   or "::warning" in ln]
    assert annotations
    for line in annotations:
        assert line.startswith("::"), line


def test_annotations_are_capped_and_summary_comes_first(tmp_path: Path, capsys) -> None:
    body = "\n".join(f".c{i}{{color:#00000{i % 10}}}" for i in range(60))
    write_template(tmp_path, "many.css", body)
    DS.main(["--mode", "report", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    annotations = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert len(annotations) <= DS.ANNOTATION_CAP
    assert "finding(s)" in annotations[0]
    # the detail the cap suppressed must still be readable below the annotations
    assert "many.css:59" in out


def test_enforce_without_a_registry_warns_that_everything_counts_as_new(
        tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}")
    DS.main(["--mode", "enforce", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert any(ln.startswith("::warning") and "counts as NEW" in ln
               for ln in out.splitlines())


# --- self-check -------------------------------------------------------------

def test_self_check_passes(capsys) -> None:
    assert DS.self_check() == 0
    assert "self-check OK" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--self-check", "--selftest"])
def test_both_selftest_spellings_run_the_same_code(flag: str, capsys) -> None:
    """`--selftest` is the house spelling the house-law meta-guard greps for."""
    assert DS.main([flag]) == 0
    assert "self-check OK" in capsys.readouterr().out


def test_self_check_fails_when_a_rule_stops_detecting(monkeypatch, capsys) -> None:
    """A self-check that cannot fail is decoration — mutate a rule and watch it.

    The regex is neutered rather than the fixture, so this pins the DETECTOR and
    not the wording of the fixture text.
    """
    monkeypatch.setattr(DS, "HEX_RE", DS.re.compile(r"(?!x)x"))
    assert DS.self_check() == 1
    out = capsys.readouterr().out
    assert "self-check: rule 'color-literal' did NOT fire" in out
    assert out.splitlines()[0].startswith("::error")


def test_self_check_fixture_set_covers_every_reported_rule() -> None:
    """A rule with no fixture is a rule the self-check silently never proves."""
    reported = set(DS.BLOCKING_RULES) | {
        "card-class", "banned-vocabulary", "inline-style-bytes", "emoji"}
    assert set(DS.DIRTY_FIXTURES) == reported


# --- parallel-token-root (rule 9) --------------------------------------------
#
# A non-theme `:root` block that declares a custom property is a second palette
# definition — illegal even when every value is a pure token derivation, because
# the violation is the SECOND ROOT, not the literal.  A scoped (non-`:root`)
# derived custom property is exactly how a surface is supposed to extend the
# palette, and stays legal.

def test_parallel_token_root_fires_even_when_fully_derived() -> None:
    body = ":root{--brand-2:var(--ink-1)}"
    hits = {f.rule for f in DS.scan_text(f"{TEMPLATES}/x.css", body)}
    assert "parallel-token-root" in hits


def test_parallel_token_root_is_legal_when_scoped() -> None:
    body = "body.page-x{--brand-2:var(--ink-1)}"
    hits = {f.rule for f in DS.scan_text(f"{TEMPLATES}/x.css", body)}
    assert "parallel-token-root" not in hits


def test_parallel_token_root_never_fires_on_theme_css() -> None:
    """theme.css is the sole legitimate token root — the one file this rule must
    never touch, mirroring rules 1/2/4 above."""
    body = ":root{--ink-1:#101418}"
    hits = {f.rule for f in DS.scan_text(DS.THEME_CSS, body)}
    assert "parallel-token-root" not in hits


def test_parallel_token_root_fires_on_a_sanctioned_asset_file() -> None:
    """SANCTIONED_LITERAL_FILES exempts colour/font literals, never a second root
    — theme.css is the ONLY exemption for this rule."""
    sanctioned = sorted(DS.SANCTIONED_LITERAL_FILES - {DS.THEME_CSS})[0]
    hits = {f.rule for f in DS.scan_text(sanctioned, ":root{--brand-2:#fff}")}
    assert "parallel-token-root" in hits


# --- diff parsing: parse_added_line_numbers (pure, no subprocess) ------------

def test_parse_added_line_numbers_basic_hunk() -> None:
    diff = (
        "diff --git a/templates/legacy.css b/templates/legacy.css\n"
        "--- a/templates/legacy.css\n"
        "+++ b/templates/legacy.css\n"
        "@@ -1,0 +2,1 @@\n"
        "+.new{color:#ff0044}\n"
    )
    assert DS.parse_added_line_numbers(diff) == {"templates/legacy.css": {2}}


def test_parse_added_line_numbers_strips_the_trailing_tab_on_a_spaced_path() -> None:
    r"""Git appends a literal TAB after the path when the path contains a space.

    Regression guard (R1). Before the fix the dict key was
    ``templates/panel v2.css\t``, so ``added_lines.get(finding.path)`` missed
    and a brand-new raw colour in that file exited 0 while the identical file
    named without a space exited 1 — a silent false negative in a HARD gate,
    reachable by renaming a stylesheet. The tab is written literally here
    because that is what git emits; this file may not shell out to git (the
    CLOSURE LEGIBILITY contract binds the test as well as the script).
    """
    diff = (
        "diff --git a/templates/panel v2.css b/templates/panel v2.css\n"
        "--- a/templates/panel v2.css\t\n"
        "+++ b/templates/panel v2.css\t\n"
        "@@ -1,0 +2,1 @@\n"
        "+.new{color:#ff0044}\n"
    )
    assert DS.parse_added_line_numbers(diff) == {"templates/panel v2.css": {2}}


def test_parse_added_line_numbers_unquotes_a_c_quoted_non_ascii_path() -> None:
    r"""Git C-quotes any path carrying a non-ASCII byte: ``"templates/pa\303\251nel.css"``.

    Regression guard (R1). The octal escapes are raw BYTES of one UTF-8
    sequence, so they must accumulate and decode once — decoding escape by
    escape yields mojibake and the key never matches a finding's path.
    """
    diff = (
        'diff --git "a/templates/pa\\303\\251nel.css" "b/templates/pa\\303\\251nel.css"\n'
        '--- "a/templates/pa\\303\\251nel.css"\n'
        '+++ "b/templates/pa\\303\\251nel.css"\n'
        "@@ -1,0 +2,1 @@\n"
        "+.new{color:#ff0044}\n"
    )
    assert DS.parse_added_line_numbers(diff) == {"templates/paénel.css": {2}}


def test_enforce_added_blocks_a_new_colour_in_a_spaced_path(tmp_path: Path, capsys) -> None:
    """End-to-end R1: the spaced path must reach the BLOCKING set, not just parse."""
    write_template(tmp_path, "panel v2.css", ".legacy{color:#123456}\n.new{color:#ff0044}\n")
    diff = (
        "diff --git a/templates/panel v2.css b/templates/panel v2.css\n"
        "--- a/templates/panel v2.css\t\n"
        "+++ b/templates/panel v2.css\t\n"
        "@@ -1,0 +2,1 @@\n"
        "+.new{color:#ff0044}\n"
    )
    diff_path = tmp_path / "d.diff"
    diff_path.write_text(diff, encoding="utf-8")
    rc = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                  "--diff-file", str(diff_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "panel v2.css:2" in out
    # line 1 carries an identical legacy literal and must NOT block
    assert "panel v2.css:1" not in out


def test_parse_added_line_numbers_skips_no_newline_marker() -> None:
    r"""`\ No newline at end of file` is not a real line; counting it desyncs
    every subsequent line number in the hunk (C2, binding correction)."""
    diff = (
        "diff --git a/templates/legacy.css b/templates/legacy.css\n"
        "--- a/templates/legacy.css\n"
        "+++ b/templates/legacy.css\n"
        "@@ -1,1 +1,3 @@\n"
        " unchanged\n"
        "+added-a\n"
        "\\ No newline at end of file\n"
        "+added-b\n"
    )
    assert DS.parse_added_line_numbers(diff) == {
        "templates/legacy.css": {2, 3}}


def test_parse_added_line_numbers_unified_zero_style_hunk() -> None:
    """CI invokes `git diff --unified=0` (no context lines); a single-line new
    range also drops its comma."""
    diff = (
        "diff --git a/templates/x.css b/templates/x.css\n"
        "--- a/templates/x.css\n"
        "+++ b/templates/x.css\n"
        "@@ -5,0 +6 @@\n"
        "+.x{color:#abcdef}\n"
    )
    assert DS.parse_added_line_numbers(diff) == {"templates/x.css": {6}}


def test_parse_added_line_numbers_tolerates_trailing_hunk_context() -> None:
    """git appends the enclosing function/selector text after the closing `@@`."""
    diff = (
        "diff --git a/templates/x.css b/templates/x.css\n"
        "--- a/templates/x.css\n"
        "+++ b/templates/x.css\n"
        "@@ -1,2 +1,3 @@ .some-selector {\n"
        " a\n"
        " b\n"
        "+c\n"
    )
    assert DS.parse_added_line_numbers(diff) == {"templates/x.css": {3}}


def test_parse_added_line_numbers_content_starting_with_double_plus_is_counted() -> None:
    """An added line whose CONTENT begins with `++` must not be mistaken for a
    `+++ file` header — a header only ever appears before the hunk starts."""
    diff = (
        "diff --git a/templates/x.css b/templates/x.css\n"
        "--- a/templates/x.css\n"
        "+++ b/templates/x.css\n"
        "@@ -1,0 +2,1 @@\n"
        "++ this looks like a header but is not\n"
    )
    assert DS.parse_added_line_numbers(diff) == {"templates/x.css": {2}}


def test_parse_added_line_numbers_deletions_do_not_advance_the_counter() -> None:
    diff = (
        "diff --git a/templates/x.css b/templates/x.css\n"
        "--- a/templates/x.css\n"
        "+++ b/templates/x.css\n"
        "@@ -1,2 +1,2 @@\n"
        "-old text\n"
        "+new text\n"
    )
    assert DS.parse_added_line_numbers(diff) == {"templates/x.css": {1}}


def test_parse_added_line_numbers_multiple_files_in_one_diff() -> None:
    diff = (
        "diff --git a/templates/a.css b/templates/a.css\n"
        "--- a/templates/a.css\n"
        "+++ b/templates/a.css\n"
        "@@ -0,0 +1,1 @@\n"
        "+.a{color:#111111}\n"
        "diff --git a/templates/b.css b/templates/b.css\n"
        "--- a/templates/b.css\n"
        "+++ b/templates/b.css\n"
        "@@ -0,0 +1,1 @@\n"
        "+.b{color:#222222}\n"
    )
    assert DS.parse_added_line_numbers(diff) == {
        "templates/a.css": {1}, "templates/b.css": {1}}


# --- R1: diff-header path normalization, verified against a REAL `git diff` -
#
# A hand-written diff cannot reproduce git's own escaping (the appended TAB
# for a path with a space; the C-style/octal quoting for a non-ASCII byte),
# so a hand-written fixture would let this bug back in.

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


def test_parse_added_line_numbers_real_git_diff_path_with_a_space(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    target = repo / "templates" / "panel v2.css"
    target.parent.mkdir(parents=True)
    target.write_text(".x{color:#111}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    target.write_text(".x{color:#111}\n.y{color:#222}\n", encoding="utf-8")
    diff = _real_diff(repo, "--unified=0", "--", "templates")
    assert "\t" in diff.splitlines()[3]  # sanity: git really appended the tab
    assert DS.parse_added_line_numbers(diff) == {"templates/panel v2.css": {2}}


def test_parse_added_line_numbers_real_git_diff_non_ascii_quoted_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    target = repo / "templates" / "panél.css"
    target.parent.mkdir(parents=True)
    target.write_text(".x{color:#111}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    target.write_text(".x{color:#111}\n.y{color:#222}\n", encoding="utf-8")
    diff = _real_diff(repo, "--unified=0", "--", "templates")
    assert diff.splitlines()[3].startswith('+++ "b/')  # sanity: git really quoted it
    assert DS.parse_added_line_numbers(diff) == {"templates/panél.css": {2}}


def test_parse_added_line_numbers_real_git_diff_space_and_non_ascii_combined(
        tmp_path: Path) -> None:
    """Both shapes at once: quoted AND carrying the trailing tab — order of
    operations matters (strip the tab first, THEN unquote)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    target = repo / "templates" / "pan él two.css"
    target.parent.mkdir(parents=True)
    target.write_text(".x{color:#111}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    target.write_text(".x{color:#111}\n.y{color:#222}\n", encoding="utf-8")
    diff = _real_diff(repo, "--unified=0", "--", "templates")
    header = diff.splitlines()[3]
    assert header.startswith('+++ "b/') and "\t" in header  # sanity: both shapes present
    assert DS.parse_added_line_numbers(diff) == {"templates/pan él two.css": {2}}


def test_normalize_diff_header_path_dev_null_passes_through() -> None:
    assert DS._normalize_diff_header_path("/dev/null") == "/dev/null"


def test_added_blocking_findings_only_counts_findings_on_added_lines() -> None:
    findings = [
        DS.Finding("color-literal", "templates/legacy.css", 1, "old"),
        DS.Finding("color-literal", "templates/legacy.css", 2, "new"),
        DS.Finding("emoji", "templates/legacy.css", 2, "emoji U+1F319"),  # pictographic: blocks
        DS.Finding("card-class", "templates/legacy.css", 2, "not blocking-tier"),
    ]
    added_lines = {"templates/legacy.css": {2}}
    result = DS.added_blocking_findings(findings, added_lines)
    assert [(f.rule, f.line) for f in result] == [
        ("color-literal", 2), ("emoji", 2)]


def test_added_blocking_rules_is_blocking_rules_plus_emoji_and_parallel_root() -> None:
    assert DS.ADDED_BLOCKING_RULES == frozenset(DS.BLOCKING_RULES) | {
        "emoji", "parallel-token-root"}
    # C3: BLOCKING_RULES stays a tuple — other code reads it as one.
    assert isinstance(DS.BLOCKING_RULES, tuple)


def test_enforce_added_is_a_valid_mode() -> None:
    assert DS.MODES == ("report", "enforce", "enforce-added")


# --- CLI: --mode enforce-added -------------------------------------------------

def test_enforce_added_blocks_only_the_newly_added_line(tmp_path: Path, capsys) -> None:
    """The headline case: an unchanged legacy raw color does NOT block while a
    newly added raw color in the SAME file DOES."""
    write_template(tmp_path, "legacy.css",
                   ".old{color:#ff0044}\n.new{color:#ff0055}\n")
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/legacy.css b/templates/legacy.css\n"
        "--- a/templates/legacy.css\n"
        "+++ b/templates/legacy.css\n"
        "@@ -1,0 +2,1 @@\n"
        "+.new{color:#ff0055}\n",
        encoding="utf-8")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    out = capsys.readouterr().out
    annotations = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert code == 1
    assert any("legacy.css:2" in ln for ln in annotations)
    assert not any("legacy.css:1" in ln for ln in annotations)


def test_enforce_added_passes_when_the_diff_touches_no_blocking_rule(
        tmp_path: Path, capsys) -> None:
    """Unchanged legacy debt in a file untouched by the diff never blocks."""
    write_template(tmp_path, "legacy.css", ".old{color:#ff0044}\n")
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/other.css b/templates/other.css\n"
        "--- a/templates/other.css\n"
        "+++ b/templates/other.css\n"
        "@@ -0,0 +1,1 @@\n"
        "+.clean{color:var(--ink-1)}\n",
        encoding="utf-8")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    capsys.readouterr()
    assert code == 0


def test_enforce_added_blocks_a_newly_added_emoji(tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "page.html.j2", "<p>\U0001F600 hi</p>\n")
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/page.html.j2 b/templates/page.html.j2\n"
        "--- a/templates/page.html.j2\n"
        "+++ b/templates/page.html.j2\n"
        "@@ -0,0 +1,1 @@\n"
        "+<p>\U0001F600 hi</p>\n",
        encoding="utf-8")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    capsys.readouterr()
    assert code == 1


# --- R3: emoji-as-UI blocking is NARROWER than the rule-8 census regex -------
#
# EMOJI_RE (rule 8, --mode report) intentionally over-matches: measured across
# templates/**, 1,597 hits in 145 files, most of them ordinary typography
# (checkmarks, warning triangles, stars) or country-flag regional indicators
# used as market/locale identifiers in data structures (stock-logos.js,
# intl.html.j2, the nav). Blocking those in enforce-added would red ordinary
# roadmapped work. EMOJI_BLOCKING_RE narrows enforce-added blocking to the
# pictographic planes only (emoji-as-icon), which the design doctrine bans.

def _added_emoji_diff(tmp_path: Path, char: str) -> Path:
    write_template(tmp_path, "page.html.j2", f"<p>{char} hi</p>\n")
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/page.html.j2 b/templates/page.html.j2\n"
        "--- a/templates/page.html.j2\n"
        "+++ b/templates/page.html.j2\n"
        "@@ -0,0 +1,1 @@\n"
        f"+<p>{char} hi</p>\n",
        encoding="utf-8")
    return diff_path


@pytest.mark.parametrize("char", ["✓", "⚠"])  # checkmark, warning triangle
def test_enforce_added_does_not_block_typography_glyphs(tmp_path: Path, capsys, char: str) -> None:
    diff_path = _added_emoji_diff(tmp_path, char)
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    capsys.readouterr()
    assert code == 0


def test_enforce_added_does_not_block_a_country_flag(tmp_path: Path, capsys) -> None:
    """A regional-indicator flag (e.g. \U0001F1FA\U0001F1F8) is a locale/data
    identifier, not emoji-as-UI decoration — adding a market must not red."""
    diff_path = _added_emoji_diff(tmp_path, "\U0001F1FA\U0001F1F8")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    capsys.readouterr()
    assert code == 0


@pytest.mark.parametrize("char", ["\U0001F319", "\U0001F4CA"])  # crescent moon, bar chart
def test_enforce_added_blocks_a_pictographic_emoji(tmp_path: Path, capsys, char: str) -> None:
    diff_path = _added_emoji_diff(tmp_path, char)
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    capsys.readouterr()
    assert code == 1


def test_report_mode_still_reports_typography_and_flags_via_wide_emoji_re(
        tmp_path: Path, capsys) -> None:
    """--mode report census output is UNCHANGED by R3 — EMOJI_RE (rule 8) still
    matches typography and country flags; only enforce-added narrows."""
    write_template(tmp_path, "page.html.j2",
                   "<p>✓ ⚠ \U0001F1FA\U0001F1F8</p>\n")
    code = DS.main(["--mode", "report", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("emoji") >= 3  # one finding per codepoint, per scan_text


def test_emoji_blocking_re_excludes_typography_and_regional_indicators() -> None:
    assert DS.EMOJI_BLOCKING_RE.search("✓") is None
    assert DS.EMOJI_BLOCKING_RE.search("⚠") is None
    assert DS.EMOJI_BLOCKING_RE.search("\U0001F1FA") is None
    assert DS.EMOJI_BLOCKING_RE.search("\U0001F1F8") is None
    assert DS.EMOJI_BLOCKING_RE.search("\U0001F319") is not None
    assert DS.EMOJI_BLOCKING_RE.search("\U0001F4CA") is not None


def test_emoji_re_report_regex_is_unaffected_by_the_narrow_blocking_pattern() -> None:
    """EMOJI_RE (rule 8 / --mode report) must still match everything it always
    did — R3 adds a SEPARATE narrower pattern, it never edits EMOJI_RE."""
    for char in ("✓", "⚠", "\U0001F1FA", "\U0001F1F8", "\U0001F319"):
        assert DS.EMOJI_RE.search(char) is not None


def test_enforce_added_blocks_a_newly_added_parallel_token_root(
        tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "page.css", ":root{--brand-2:var(--ink-1)}\n")
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/page.css b/templates/page.css\n"
        "--- a/templates/page.css\n"
        "+++ b/templates/page.css\n"
        "@@ -0,0 +1,1 @@\n"
        "+:root{--brand-2:var(--ink-1)}\n",
        encoding="utf-8")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    capsys.readouterr()
    assert code == 1


def test_enforce_added_reads_diff_from_stdin(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello\n"))
    assert DS._read_diff("-") == "hello\n"


def test_enforce_added_reads_diff_from_a_file_path(tmp_path: Path) -> None:
    diff_path = tmp_path / "design.diff"
    diff_path.write_text("some diff text\n", encoding="utf-8")
    assert DS._read_diff(str(diff_path)) == "some diff text\n"


def test_enforce_added_without_diff_file_blocks_nothing_but_warns(
        tmp_path: Path, capsys) -> None:
    """No diff means no line was ever 'added' — fail open, but say so loudly."""
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}\n")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert any(ln.startswith("::warning") and "no --diff-file" in ln
               for ln in out.splitlines())


# --- R6: an unreadable --diff-file fails CLOSED, never a silent pass --------

def test_read_diff_reraises_oserror_for_an_unreadable_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.diff"
    with pytest.raises(OSError):
        DS._read_diff(str(missing))


def test_enforce_added_with_an_unreadable_diff_file_fails_closed(
        tmp_path: Path, capsys) -> None:
    """A caller-supplied --diff-file that cannot be read is a CHECKOUT fault,
    not evidence that nothing was added — must NOT silently exit 0."""
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}\n")
    missing = tmp_path / "does-not-exist.diff"
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(missing)])
    out = capsys.readouterr().out
    assert code == 1
    errors = [ln for ln in out.splitlines() if ln.startswith("::error")]
    assert errors, f"expected a bare ::error annotation, got: {out!r}"
    assert any(str(missing) in ln for ln in errors)


# --- enforce-added reporting must stay concise, never dump the estate census --
#
# `report()`/`--mode report` dumping the whole estate is correct on purpose —
# that mode means "show me everything".  `--mode enforce-added` must NOT reuse
# that shape: on the real estate the census runs ~19,000 findings, so an
# unscoped dump makes forward-only enforcement look like it reddened the whole
# estate on every PR (exactly what TP-0 exists to avoid) and floods CI logs.

def test_enforce_added_clean_diff_emits_no_error_and_stays_concise(
        tmp_path: Path, capsys) -> None:
    """Zero blocking findings: exit 0, no ::error at all, estate never dumped."""
    write_template(tmp_path, "estate.css",
                   "\n".join(f".c{i}{{color:#00000{i % 10}}}" for i in range(300)))
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/other.css b/templates/other.css\n"
        "--- a/templates/other.css\n"
        "+++ b/templates/other.css\n"
        "@@ -0,0 +1,1 @@\n"
        "+.clean{color:var(--ink-1)}\n",
        encoding="utf-8")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert code == 0
    assert not any(ln.startswith("::error") for ln in lines)
    assert len(lines) < 20
    assert "estate.css" not in out


def test_enforce_added_dirty_diff_reports_only_the_blocking_finding(
        tmp_path: Path, capsys) -> None:
    """One blocking finding on a heavily-dirty estate: output stays small and
    names only the blocking finding — never the estate census."""
    write_template(tmp_path, "estate.css",
                   "\n".join(f".c{i}{{color:#00000{i % 10}}}" for i in range(300)))
    write_template(tmp_path, "legacy.css",
                   ".old{color:#ff0044}\n.new{color:#ff0055}\n")
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/legacy.css b/templates/legacy.css\n"
        "--- a/templates/legacy.css\n"
        "+++ b/templates/legacy.css\n"
        "@@ -1,0 +2,1 @@\n"
        "+.new{color:#ff0055}\n",
        encoding="utf-8")
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
                    "--diff-file", str(diff_path)])
    out = capsys.readouterr().out
    lines = out.splitlines()
    errors = [ln for ln in lines if ln.startswith("::error")]
    assert code == 1
    # summary + the one blocking exemplar — never one per estate finding.
    assert len(errors) == 2
    assert any("legacy.css:2" in ln for ln in errors)
    assert not any("legacy.css:1" in ln for ln in errors)
    assert len(lines) < 20
    assert "estate.css" not in out
    assert "legacy.css:1" not in out


def test_enforce_added_summary_leads_with_the_blocking_count(
        tmp_path: Path, capsys) -> None:
    """The estate total, if mentioned at all, must be clearly labelled
    non-blocking — never presented as this mode's error count."""
    write_template(tmp_path, "estate.css",
                   "\n".join(f".c{i}{{color:#00000{i % 10}}}" for i in range(50)))
    write_template(tmp_path, "legacy.css",
                   ".old{color:#ff0044}\n.new{color:#ff0055}\n")
    diff_path = tmp_path / "design.diff"
    diff_path.write_text(
        "diff --git a/templates/legacy.css b/templates/legacy.css\n"
        "--- a/templates/legacy.css\n"
        "+++ b/templates/legacy.css\n"
        "@@ -1,0 +2,1 @@\n"
        "+.new{color:#ff0055}\n",
        encoding="utf-8")
    DS.main(["--mode", "enforce-added", "--root", str(tmp_path),
             "--diff-file", str(diff_path)])
    out = capsys.readouterr().out
    summary = next(ln for ln in out.splitlines() if ln.startswith("::error"))
    assert "1 blocking finding" in summary
    assert "non-blocking" in summary


def test_enforce_added_never_reuses_reports_full_dump_shape(
        tmp_path: Path, capsys) -> None:
    """`report_added` is a distinct function from `report` — enforce-added must
    not fall back to the estate-dumping code path under any finding count."""
    write_template(tmp_path, "estate.css",
                   "\n".join(f".c{i}{{color:#00000{i % 10}}}" for i in range(120)))
    code = DS.main(["--mode", "enforce-added", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("estate.css") == 0


def test_report_mode_still_dumps_the_full_census(tmp_path: Path, capsys) -> None:
    """`--mode report` behavior must stay EXACTLY as it is today — the concise
    reporter above only applies to `enforce-added`."""
    write_template(tmp_path, "estate.css",
                   "\n".join(f".c{i}{{color:#00000{i % 10}}}" for i in range(60)))
    code = DS.main(["--mode", "report", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("estate.css") >= 60


# --- regression guard: report/enforce keep their exact prior semantics -------

def test_report_and_enforce_are_unaffected_by_the_new_mode(
        tmp_path: Path, capsys) -> None:
    write_template(tmp_path, "dirty.css", ".x{color:#ff0044}\n")
    report_code = DS.main(["--mode", "report", "--root", str(tmp_path)])
    report_out = capsys.readouterr().out
    enforce_code = DS.main(["--mode", "enforce", "--root", str(tmp_path)])
    enforce_out = capsys.readouterr().out
    assert report_code == 0
    assert enforce_code == 1
    assert "mode=report" in report_out
    assert "mode=enforce" in enforce_out
