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

import json
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
    body = (".x{color:var(--ink-1);font-family:var(--font-body);"
            "border-radius:var(--r-2)}\n:root{--ink-soft:var(--ink-1)}\n")
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
