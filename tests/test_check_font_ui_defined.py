"""Font-UI definition guard — unit tests for scripts/check_font_ui_defined.

Fixture pairs (violating + passing) per detection helper, plus end-to-end
run_checks()/main() coverage on a synthetic templates tree and a
current-tree pass assertion (the #2647 fix state must stay green).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_font_ui_defined import (
    defines_font_ui,
    includes_interfonts,
    links_theme_css,
    main,
    run_checks,
    strip_comments,
    strip_jinja,
    uses_body_font_ui,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ── fixtures ──────────────────────────────────────────────────────────────────

# The exact single-line body rule shape (vector/ipo/special_situations style)
_BODY_FONT_FAMILY = (
    "<style>\n"
    "body{margin:0;background:var(--bg);color:var(--text);"
    "font-family:var(--font-ui);font-size:15px;line-height:1.5}\n"
    "</style>"
)

# The font: shorthand shape (alerts/commodities style)
_BODY_FONT_SHORTHAND = (
    "<style>\n"
    "body {\n"
    "  margin: 0; padding-top: 24px; background: var(--bg); color: var(--tx);\n"
    "  font: 14px/1.45 var(--font-ui);\n"
    "}\n"
    "</style>"
)

# Multi-line body rule with declaration on its own line (macro_context style)
_BODY_MULTILINE = (
    "<style>\n"
    "body {\n"
    "  font-family: var(--font-ui);\n"
    "  background: var(--bg); color: var(--text); line-height: 1.5;\n"
    "}\n"
    "</style>"
)

_THEME_LINK = '<link rel="stylesheet" href="theme.css">'
_LOCAL_DEF = "<style>:root{--font-ui: Inter, -apple-system, sans-serif;}</style>"
_INTERFONTS_INCLUDE = '{% include "_interfonts.html.j2" %}'


def _template(*parts: str) -> str:
    body = "\n".join(parts)
    return f"<!DOCTYPE html>\n<html lang=\"en\"><head>\n{body}\n</head><body></body></html>\n"


# ── uses_body_font_ui ─────────────────────────────────────────────────────────


def test_body_font_family_var_detected():
    assert uses_body_font_ui(_BODY_FONT_FAMILY)


def test_body_font_shorthand_var_detected():
    assert uses_body_font_ui(_BODY_FONT_SHORTHAND)


def test_body_multiline_rule_detected():
    assert uses_body_font_ui(_BODY_MULTILINE)


def test_body_rule_inside_media_query_detected():
    css = "<style>@media (max-width:700px){ body{font-family:var(--font-ui)} }</style>"
    assert uses_body_font_ui(css)


def test_selector_list_with_body_detected():
    css = "<style>html, body { font: 14px/1.5 var(--font-ui); }</style>"
    assert uses_body_font_ui(css)


def test_selector_list_comma_no_space_detected():
    # Minifier shape: no space after the list comma.
    css = "<style>html,body{font-family:var(--font-ui)}</style>"
    assert uses_body_font_ui(css)


def test_uppercase_selector_and_var_detected():
    # Type selectors and function names are case-insensitive per the CSS spec.
    css = "<style>BODY{FONT-FAMILY:VAR(--font-ui)}</style>"
    assert uses_body_font_ui(css)


def test_uppercase_custom_property_name_is_out_of_scope():
    # Custom property NAMES are case-sensitive: --FONT-UI is a different token
    # (deliberately out of scope — theme.css only defines lowercase).
    css = "<style>body{font-family:var(--FONT-UI)}</style>"
    assert not uses_body_font_ui(css)


def test_jinja_tag_inside_body_block_does_not_void_scan():
    # An interpolation inside body{} unbalances the flat brace scan unless
    # Jinja tags are stripped first.
    css = "<style>body{font-family:var(--font-ui);{{ extra_css }}}</style>"
    assert uses_body_font_ui(strip_jinja(css))


def test_descendant_body_selector_detected():
    css = '<style>html[data-lang="zh"] body { font-family: var(--font-ui); }</style>'
    assert uses_body_font_ui(css)


def test_brand_word_rule_is_not_body_level():
    # The shared _vector_polish brand-word rule must NOT put a host in scope.
    css = (
        "<style>.site-nav .nav-brand .brand-word,.topbar .nav-brand .brand-word"
        "{font-family:var(--font-ui);font-size:13.5px;font-weight:900}</style>"
    )
    assert not uses_body_font_ui(css)


def test_body_rule_without_var_is_not_flagged():
    css = (
        '<style>html[data-lang="zh"] body '
        '{ font-family: "PingFang SC","Microsoft YaHei",Inter,sans-serif; }</style>'
    )
    assert not uses_body_font_ui(css)


def test_tbody_and_class_body_are_not_body():
    css = (
        "<style>tbody{font-family:var(--font-ui)} "
        ".body-copy{font-family:var(--font-ui)}</style>"
    )
    assert not uses_body_font_ui(css)


def test_body_rule_with_only_font_size_is_not_flagged():
    # -webkit-font-smoothing / font-size must not satisfy the font declaration match.
    css = "<style>body{font-size:15px;-webkit-font-smoothing:antialiased;color:var(--font-ui)}</style>"
    assert not uses_body_font_ui(css)


def test_body_rule_in_css_comment_is_ignored():
    css = "<style>/* body{font-family:var(--font-ui)} */ h1{color:red}</style>"
    assert not uses_body_font_ui(strip_comments(css))


# ── links_theme_css ───────────────────────────────────────────────────────────


def test_theme_link_href_matches():
    assert links_theme_css(_THEME_LINK)


def test_theme_link_relative_parent_href_matches():
    assert links_theme_css('<link rel="stylesheet" href="../theme.css">')


def test_theme_link_query_string_matches():
    assert links_theme_css('<link rel="stylesheet" href="theme.css?v=4">')


def test_theme_link_attr_order_reversed_matches():
    assert links_theme_css('<link href="theme.css" rel="stylesheet">')


def test_theme_css_in_css_comment_does_not_match():
    # The naive-grep defeater: comments mention theme.css without linking it.
    assert not links_theme_css(
        "<style>/* tokens mirror theme.css so standalone pages stay in sync */</style>"
    )


def test_theme_css_bare_string_does_not_match():
    assert not links_theme_css("theme.css")


def test_preload_link_does_not_match():
    assert not links_theme_css('<link rel="preload" href="theme.css" as="style">')


def test_other_stylesheet_ending_in_theme_css_does_not_match():
    assert not links_theme_css('<link rel="stylesheet" href="dark_theme.css">')


# ── defines_font_ui ───────────────────────────────────────────────────────────


def test_local_definition_matches():
    assert defines_font_ui(_LOCAL_DEF)


def test_var_usage_is_not_a_definition():
    assert not defines_font_ui("body{font-family:var(--font-ui)}")


def test_var_usage_with_fallback_is_not_a_definition():
    assert not defines_font_ui("body{font-family:var(--font-ui, serif)}")


# ── includes_interfonts ───────────────────────────────────────────────────────


def test_interfonts_include_matches():
    assert includes_interfonts(_INTERFONTS_INCLUDE)


def test_interfonts_include_single_quotes_matches():
    assert includes_interfonts("{% include '_interfonts.html.j2' %}")


def test_missing_interfonts_include():
    assert not includes_interfonts(_THEME_LINK)


# ── run_checks: end-to-end on a synthetic templates tree ─────────────────────


def _write(tmp_path: Path, name: str, content: str) -> None:
    (tmp_path / name).write_text(content, encoding="utf-8")


def test_undefined_token_is_a_violation(tmp_path):
    _write(tmp_path, "broken.html.j2", _template(_BODY_FONT_FAMILY))
    violations, warnings = run_checks(str(tmp_path))
    assert len(violations) == 1
    assert "broken.html.j2" in violations[0][0]
    assert "var(--font-ui)" in violations[0][1]


def test_theme_css_link_passes(tmp_path):
    _write(tmp_path, "linked.html.j2", _template(_THEME_LINK, _BODY_FONT_FAMILY))
    violations, warnings = run_checks(str(tmp_path))
    assert violations == []
    assert warnings == []


def test_theme_css_comment_mention_alone_still_fails(tmp_path):
    _write(
        tmp_path,
        "comment_trap.html.j2",
        _template(
            "<style>/* tokens mirror theme.css */</style>",
            _BODY_FONT_FAMILY,
        ),
    )
    violations, _ = run_checks(str(tmp_path))
    assert len(violations) == 1


def test_local_definition_with_interfonts_passes_clean(tmp_path):
    _write(
        tmp_path,
        "fixed.html.j2",
        _template(_INTERFONTS_INCLUDE, _LOCAL_DEF, _BODY_FONT_FAMILY),
    )
    violations, warnings = run_checks(str(tmp_path))
    assert violations == []
    assert warnings == []


def test_local_definition_without_interfonts_warns(tmp_path):
    _write(tmp_path, "no_fonts.html.j2", _template(_LOCAL_DEF, _BODY_FONT_FAMILY))
    violations, warnings = run_checks(str(tmp_path))
    assert violations == []
    assert len(warnings) == 1
    assert "_interfonts" in warnings[0][1]


def test_commented_out_interfonts_include_still_warns(tmp_path):
    _write(
        tmp_path,
        "dead_include.html.j2",
        _template(f"<!-- {_INTERFONTS_INCLUDE} -->", _LOCAL_DEF, _BODY_FONT_FAMILY),
    )
    violations, warnings = run_checks(str(tmp_path))
    assert violations == []
    assert len(warnings) == 1
    assert "_interfonts" in warnings[0][1]


def test_jinja_inside_body_block_end_to_end_violation(tmp_path):
    _write(
        tmp_path,
        "jinja_body.html.j2",
        _template(
            "<style>body{font-family:var(--font-ui);{{ extra_css }}}</style>"
        ),
    )
    violations, _ = run_checks(str(tmp_path))
    assert len(violations) == 1


def test_out_of_scope_template_ignored(tmp_path):
    # var(--font-ui) only in a non-body rule: no theme.css/def required.
    _write(
        tmp_path,
        "brand_only.html.j2",
        _template("<style>.brand-word{font-family:var(--font-ui)}</style>"),
    )
    violations, warnings = run_checks(str(tmp_path))
    assert violations == []
    assert warnings == []


def test_partial_is_skipped_with_warning(tmp_path):
    _write(
        tmp_path,
        "_polish.html.j2",
        "<style>.brand-word{font-family:var(--font-ui)}</style>",
    )
    violations, warnings = run_checks(str(tmp_path))
    assert violations == []
    assert len(warnings) == 1
    assert "partial" in warnings[0][1]


def test_partial_without_font_ui_is_silent(tmp_path):
    _write(tmp_path, "_nav.html.j2", "<nav>links</nav>")
    violations, warnings = run_checks(str(tmp_path))
    assert violations == []
    assert warnings == []


# ── main(): exit codes ────────────────────────────────────────────────────────


def test_main_exit_1_on_violation(tmp_path, capsys):
    _write(tmp_path, "broken.html.j2", _template(_BODY_FONT_FAMILY))
    assert main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "FAIL" in err
    assert "broken.html.j2" in err


def test_main_exit_0_on_clean_tree(tmp_path, capsys):
    _write(tmp_path, "linked.html.j2", _template(_THEME_LINK, _BODY_FONT_FAMILY))
    assert main([str(tmp_path)]) == 0
    assert "OK" in capsys.readouterr().out


def test_main_exit_0_with_warnings_only(tmp_path, capsys):
    _write(tmp_path, "no_fonts.html.j2", _template(_LOCAL_DEF, _BODY_FONT_FAMILY))
    assert main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "warning:" in out
    assert "OK" in out


def test_main_exit_1_on_missing_dir(tmp_path):
    assert main([str(tmp_path / "nope")]) == 1


# ── current tree must stay green (the #2647 fix state) ───────────────────────


@pytest.mark.skipif(
    not (_REPO_ROOT / "templates").is_dir(), reason="repo templates/ not present"
)
def test_current_templates_tree_passes():
    violations, _warnings = run_checks(str(_REPO_ROOT / "templates"))
    assert violations == [], (
        "templates/ regressed on the #2647 font-ui law: " + repr(violations)
    )
