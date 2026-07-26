"""Font-UI definition guard — unit tests for scripts/check_font_ui_defined.

Fixture pairs (violating + passing) per detection helper, plus end-to-end
run_checks()/main() coverage on a synthetic templates tree and a
current-tree pass assertion (the #2647 fix state must stay green).
"""
from __future__ import annotations

import hashlib
import re
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


def test_theme_link_jinja_prefixed_href_matches():
    # href="{{ rel }}theme.css" (rel = asset-root prefix) is stripped to
    # href=" theme.css" before the link scan; the leading space (the stripped
    # {{ rel }}, which resolves to "../" at render) must still read as a
    # theme.css link. Regression: seo_base.html.j2 linked theme.css this way
    # and the guard false-flagged it as unfonted (the lane rotted red on main).
    assert links_theme_css(strip_jinja('<link rel="stylesheet" href="{{ rel }}theme.css">'))


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


def test_theme_css_link_via_jinja_prefix_passes(tmp_path):
    # seo_base.html.j2 shape: theme.css linked through a {{ rel }} asset-root
    # prefix (resolves to ../ at render). The guard must accept it, not force a
    # redundant local --font-ui definition. This is the exact template that
    # rotted the font-ui lane red on main while ci.yml ran PR-only.
    link = '<link rel="stylesheet" href="{{ rel }}theme.css">'
    _write(tmp_path, "jinja_linked.html.j2", _template(link, _BODY_FONT_FAMILY))
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


# ── the landing's display face must stay self-hosted ─────────────────────────
# Sibling law to the one above, same failure signature: a font that never
# arrives raises no error, it just renders in the fallback. fonts.googleapis.com
# is blocked in mainland China, so a CDN <link> on these surfaces delivers
# NOTHING there. This has already regressed once — the landing carried a CDN
# Archivo <link> and onboard.js re-injected the same URL from ensureAssets() —
# so it is a tripwire, not a one-time fix. Self-hosted files live in
# templates/fonts/ and are declared in onboard.css (the display face) and
# index.html (Inter); see mockups/refs/landing-modern-sans/.

_NO_CDN_FONT_SURFACES = ("index.html", "landing.css", "onboard.css", "onboard.js")


@pytest.mark.skipif(
    not (_REPO_ROOT / "templates" / "index.html").is_file(),
    reason="repo templates/ not present",
)
@pytest.mark.parametrize("name", _NO_CDN_FONT_SURFACES)
def test_landing_surfaces_request_no_google_fonts(name):
    """No live request to the Google Fonts CDN on the landing/onboarding path.

    Matches the URL only where it would be FETCHED — an href/src/url() value or
    a JS string assigned to one — so the prose in the comments explaining why
    the CDN was removed does not trip the guard on itself.
    """
    text = (_REPO_ROOT / "templates" / name).read_text(encoding="utf-8")
    fetches = re.findall(
        r"""(?:href|src)\s*[=:]\s*["']([^"']*fonts\.(?:googleapis|gstatic)\.com[^"']*)"""
        r"""|url\(\s*["']?([^"')]*fonts\.(?:googleapis|gstatic)\.com[^"')]*)""",
        text,
    )
    found = [u or v for u, v in fetches]
    assert found == [], (
        f"templates/{name} fetches a font from the Google Fonts CDN, which is "
        f"blocked in mainland China — self-host it instead: {found}"
    )


@pytest.mark.skipif(
    not (_REPO_ROOT / "templates" / "onboard.css").is_file(),
    reason="repo templates/ not present",
)
def test_display_face_is_self_hosted_and_variable():
    """onboard.css must declare Outfit against a real file, keeping wght variable.

    Five rules ask for the interpolated weight 650 (.stg on the landing plus
    .obm-cmp-cell / .obm-step-lbl / .obm-mini-lbl span / .obm-sum-list li b in
    the sheet). A static instance satisfies none of them and the failure is
    silent — they quietly flatten to the nearest shipped weight.
    """
    css = (_REPO_ROOT / "templates" / "onboard.css").read_text(encoding="utf-8")
    face = re.search(r"@font-face\{[^}]*font-family:\s*'?Outfit'?[^}]*\}", css)
    assert face, "onboard.css no longer declares an @font-face for Outfit"
    block = face.group(0)

    src = re.search(r"""url\(["']?([^"')]+)["']?\)""", block)
    assert src, f"Outfit @font-face has no url(): {block[:160]}"
    assert (_REPO_ROOT / "templates" / src.group(1)).is_file(), (
        f"Outfit @font-face points at templates/{src.group(1)}, which is missing"
    )
    # the weight axis must be declared as a RANGE, not a single value
    assert re.search(r"font-weight:\s*400\s+900", block), (
        "Outfit @font-face lost its variable font-weight range (400 900) — "
        "the interpolated 650 has no instance to select without it"
    )


@pytest.mark.skipif(
    not (_REPO_ROOT / "templates" / "index.html").is_file(),
    reason="repo templates/ not present",
)
@pytest.mark.parametrize("name", ("index.html", "landing.css", "onboard.css"))
def test_no_rule_asks_the_display_face_for_an_axis_it_lacks(name):
    """No live font-stretch / opsz on the landing path.

    The retired Archivo carried a `wdth` axis and Newsreader an `opsz` axis, so
    the CSS drove both. Outfit has NEITHER. A leftover `font-stretch:125%` or
    `font-variation-settings:'opsz' N` does not error — the declaration is just
    ignored — so the only symptom is type that silently renders at the wrong
    width, which is exactly how the CDN-font regression hid for months.

    landing.css is in the list because that is where the display rules actually
    live since #3676 lifted the landing's inline CSS out of index.html — a
    parametrization that only covered index.html would pass over an empty set.
    """
    text = strip_comments((_REPO_ROOT / "templates" / name).read_text(encoding="utf-8"))
    stray = re.findall(r"font-stretch\s*:[^;}]+|font-variation-settings\s*:[^;}]+", text)
    assert stray == [], (
        f"templates/{name} still drives a variation axis Outfit does not have; "
        f"Outfit is weight-only, so these declarations are dead: {stray}"
    )


@pytest.mark.skipif(
    not (_REPO_ROOT / "site" / "fonts" / "Outfit-latin.woff2").is_file(),
    reason="repo site/ not present",
)
def test_display_face_figures_are_tabular_by_default():
    """The shipped subset must be the one whose digits share a single advance.

    Outfit's stock figures are PROPORTIONAL — 13.45px of digit spread at
    48px/800. The face it replaced (Archivo) was tabular by default, so the live
    gauge score (#gz-score, which counts up on load) and every price column on
    the landing depend on fixed advances that NO CSS rule asks for. The property
    is baked into the file instead: build_outfit_subset.py remaps the digit
    codepoints onto Outfit's own `tnum` glyphs.

    Pinning the bytes is the only zero-dependency way to guard that — the CI
    packs install minimal dep sets, so a fontTools-based check here would be a
    permanent silent skip rather than a test. The build script is reproducible
    (it pins SOURCE_DATE_EPOCH and zeroes head.created/modified, without which
    every run produced different bytes), so this digest is stable across
    rebuilds of the same input and only moves when the font really changes. If
    this fails because the font was legitimately rebuilt, re-run the script (it
    asserts the ten advances are equal) and update the digest in the same commit.
    """
    expected = "1cf8df7d11d7fcfb97779d2ea3f2aea3a54ee7e2ca82da50e88ab5ac6745593d"
    shipped = _REPO_ROOT / "site" / "fonts" / "Outfit-latin.woff2"
    mirror = _REPO_ROOT / "templates" / "fonts" / "Outfit-latin.woff2"
    digest = hashlib.sha256(shipped.read_bytes()).hexdigest()
    assert digest == expected, (
        f"site/fonts/Outfit-latin.woff2 hashes to {digest[:16]}…, expected "
        f"{expected[:16]}… — if this was a deliberate rebuild, run "
        f"`python3 mockups/refs/landing-modern-sans/build_outfit_subset.py` "
        f"(it asserts the digits stay tabular) and update this digest"
    )
    assert mirror.read_bytes() == shipped.read_bytes(), (
        "templates/fonts/Outfit-latin.woff2 and site/fonts/Outfit-latin.woff2 "
        "differ — site/fonts is what ships; commit both copies identical"
    )


@pytest.mark.skipif(
    not (_REPO_ROOT / "site" / "onboard.css").is_file(),
    reason="repo site/ not present",
)
@pytest.mark.parametrize("sheet", ("onboard.css", "landing.css"))
def test_landing_stylesheet_cache_stamps_are_current(sheet):
    """index.html's ?v= stamps must match the site stylesheets' actual bytes.

    app/deploy/Caddyfile serves versioned requests immutable/max-age=1y, so a
    stale stamp pins returning visitors to the previous stylesheet — which, for
    a font change, means no @font-face and no display face at all. #3617 shipped
    an onboard.css fix that sat live at the origin while every returning browser
    kept the old sheet; #3624 had to hand-bump that one page.

    landing.css is covered here because #3676 lifted the landing's inline CSS
    into it — that gave the page a SECOND stamped stylesheet, carrying the whole
    display type system and the six Inter @font-face blocks, with no guard on its
    stamp. Both sheets now have to be re-cut together after any edit.
    """
    digest = hashlib.sha256((_REPO_ROOT / "site" / sheet).read_bytes()).hexdigest()[:8]
    for rel in ("templates/index.html", "site/index.html"):
        stamped = re.search(
            rf"{re.escape(sheet)}\?v=([0-9a-f]{{8}})",
            (_REPO_ROOT / rel).read_text(encoding="utf-8"),
        )
        assert stamped, f"{rel} no longer links {sheet} with a ?v= stamp"
        assert stamped.group(1) == digest, (
            f"{rel} links {sheet}?v={stamped.group(1)} but site/{sheet} "
            f"hashes to {digest} — re-cut the stamp in BOTH copies"
        )
