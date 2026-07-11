"""Hub a11y regression guard — unit tests for scripts/check_hub_a11y.

One fixture pair (violating + passing) per check class (a–e).
Also exercises the page-discovery logic and the main() exit codes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_hub_a11y import (
    check_a_aria_hidden,
    check_b_lang_boot,
    check_c_pill_contrast,
    check_d_viewport_safe_area,
    check_e_theme_js_lang_sync,
    main,
    run_checks,
)

# ── shared helpers ────────────────────────────────────────────────────────────

_GLOBE_MARKER = '<div class="gd-stage">'  # makes a page "in scope"

_MINIMAL_PASSING = """\
<!DOCTYPE html>
<html lang="en"><head>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<script>document.documentElement.setAttribute('data-lang','en');</script>
<style>
html[data-theme="light"] .pill{{color:color-mix(in srgb,var(--accent) 48%,var(--text))}}
body{{padding:22px max(20px,env(safe-area-inset-right)) 56px max(20px,env(safe-area-inset-left))}}
</style>
</head><body>
{marker}
</body></html>
"""


def _page(extra_body: str = "", extra_head: str = "", use_marker: bool = True) -> str:
    marker = _GLOBE_MARKER if use_marker else ""
    return _MINIMAL_PASSING.format(marker=marker) + extra_body


# ── check a: aria-hidden focusable trap ───────────────────────────────────────


def test_a_button_in_aria_hidden_is_flagged():
    html = '<div aria-hidden="true"><button>Click</button></div>'
    violations = check_a_aria_hidden(html)
    assert violations, "button inside aria-hidden must be flagged"
    assert "button" in violations[0]


def test_a_button_with_tabindex_minus1_passes():
    html = '<div aria-hidden="true"><button tabindex="-1">OK</button></div>'
    assert check_a_aria_hidden(html) == []


def test_a_anchor_in_aria_hidden_is_flagged():
    html = '<div aria-hidden="true"><a href="#">Link</a></div>'
    violations = check_a_aria_hidden(html)
    assert violations
    assert "a" in violations[0]


def test_a_anchor_tabindex_minus1_passes():
    html = '<div aria-hidden="true"><a href="#" tabindex="-1">Hidden link</a></div>'
    assert check_a_aria_hidden(html) == []


def test_a_positive_tabindex_nonfocusable_in_hidden_is_flagged():
    html = '<div aria-hidden="true"><span tabindex="0">Not normally focusable</span></div>'
    violations = check_a_aria_hidden(html)
    assert violations
    assert "span" in violations[0]


def test_a_div_outside_aria_hidden_passes():
    html = '<div><button>Normal button</button></div>'
    assert check_a_aria_hidden(html) == []


def test_a_nested_hidden_button_is_flagged():
    html = '<section aria-hidden="true"><div><p><button>Deep</button></p></div></section>'
    violations = check_a_aria_hidden(html)
    assert violations


def test_a_canvas_with_tabindex_in_hidden_is_flagged():
    html = '<div aria-hidden="true"><canvas tabindex="0"></canvas></div>'
    violations = check_a_aria_hidden(html)
    assert violations


def test_a_real_site_passes(tmp_path):
    """The committed site/index.html must not have any aria-hidden focusable traps."""
    site = Path(__file__).resolve().parent.parent / "site" / "index.html"
    if not site.is_file():
        pytest.skip("site/index.html not present")
    html = site.read_text(encoding="utf-8", errors="replace")
    violations = check_a_aria_hidden(html)
    assert violations == [], f"Unexpected aria-hidden focusable traps: {violations}"


# ── check b: html[lang] + boot-script data-lang ──────────────────────────────


def test_b_missing_lang_attr_is_flagged():
    html = '<html><head><script>document.documentElement.setAttribute("data-lang","en")</script></head><body></body></html>'
    v = check_b_lang_boot(html)
    assert any("lang=" in msg for msg in v)


def test_b_empty_lang_attr_is_flagged():
    html = '<html lang=""><head><script>document.documentElement.setAttribute("data-lang","en")</script></head><body></body></html>'
    v = check_b_lang_boot(html)
    assert any("lang=" in msg for msg in v)


def test_b_lang_present_but_no_data_lang_script_is_flagged():
    html = '<html lang="en"><head><script>var x = 1;</script></head><body></body></html>'
    v = check_b_lang_boot(html)
    assert any("data-lang" in msg for msg in v)


def test_b_lang_with_external_script_not_counted():
    # External scripts (src=) don't count — we need an inline boot script.
    html = '<html lang="en"><head><script src="theme.js"></script></head><body></body></html>'
    v = check_b_lang_boot(html)
    assert any("data-lang" in msg for msg in v)


def test_b_valid_lang_and_data_lang_passes():
    html = (
        '<html lang="en"><head>'
        '<script>document.documentElement.setAttribute(\'data-lang\',\'en\');</script>'
        '</head><body></body></html>'
    )
    assert check_b_lang_boot(html) == []


def test_b_real_site_passes(tmp_path):
    site = Path(__file__).resolve().parent.parent / "site" / "index.html"
    if not site.is_file():
        pytest.skip("site/index.html not present")
    html = site.read_text(encoding="utf-8", errors="replace")
    assert check_b_lang_boot(html) == []


# ── check c: light-theme pill contrast override ───────────────────────────────


def test_c_missing_pill_rule_is_flagged():
    html = '<style>body{color:red}</style>'
    v = check_c_pill_contrast(html)
    assert v
    assert "pill" in v[0]


def test_c_rule_present_with_low_pct_passes():
    html = '<style>html[data-theme="light"] .pill{color:color-mix(in srgb,var(--accent) 48%,var(--text))}</style>'
    assert check_c_pill_contrast(html) == []


def test_c_rule_present_at_boundary_60_passes():
    html = '<style>html[data-theme="light"] .pill{color:color-mix(in srgb,var(--accent) 60%,var(--text))}</style>'
    assert check_c_pill_contrast(html) == []


def test_c_rule_with_high_pct_is_flagged():
    html = '<style>html[data-theme="light"] .pill{color:color-mix(in srgb,var(--accent) 80%,var(--text))}</style>'
    v = check_c_pill_contrast(html)
    assert v
    assert "80%" in v[0]


def test_c_real_site_passes():
    site = Path(__file__).resolve().parent.parent / "site" / "index.html"
    if not site.is_file():
        pytest.skip("site/index.html not present")
    html = site.read_text(encoding="utf-8", errors="replace")
    assert check_c_pill_contrast(html) == []


# ── check d: viewport-fit + safe-area body padding ───────────────────────────


def test_d_missing_viewport_meta_is_flagged():
    html = '<html lang="en"><head></head><body style="padding: env(safe-area-inset-bottom)"></body></html>'
    v = check_d_viewport_safe_area(html)
    assert any("viewport" in msg.lower() for msg in v)


def test_d_viewport_without_viewport_fit_is_flagged():
    html = (
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<style>body{padding:22px max(20px,env(safe-area-inset-right)) 56px}</style>'
    )
    v = check_d_viewport_safe_area(html)
    assert any("viewport-fit=cover" in msg for msg in v)


def test_d_missing_safe_area_in_body_is_flagged():
    html = (
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<style>body{padding:22px}</style>'
    )
    v = check_d_viewport_safe_area(html)
    assert any("safe-area-inset" in msg for msg in v)


def test_d_viewport_fit_and_safe_area_passes():
    html = (
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<style>body{padding:22px max(20px,env(safe-area-inset-right)) 56px}</style>'
    )
    assert check_d_viewport_safe_area(html) == []


def test_d_real_site_passes():
    site = Path(__file__).resolve().parent.parent / "site" / "index.html"
    if not site.is_file():
        pytest.skip("site/index.html not present")
    html = site.read_text(encoding="utf-8", errors="replace")
    assert check_d_viewport_safe_area(html) == []


# ── check e: theme.js documentElement.lang sync ──────────────────────────────


def test_e_missing_theme_js_is_flagged(tmp_path):
    v = check_e_theme_js_lang_sync(str(tmp_path))
    assert v
    assert "not found" in v[0]


def test_e_theme_js_without_docElement_lang_is_flagged(tmp_path):
    (tmp_path / "theme.js").write_text("var x = 1;", encoding="utf-8")
    v = check_e_theme_js_lang_sync(str(tmp_path))
    assert v
    assert "documentElement.lang" in v[0]


def test_e_theme_js_with_docElement_lang_passes(tmp_path):
    (tmp_path / "theme.js").write_text(
        "docEl.lang = lg === 'zh' ? 'zh-CN' : 'en'; // documentElement.lang sync",
        encoding="utf-8",
    )
    assert check_e_theme_js_lang_sync(str(tmp_path)) == []


def test_e_real_theme_js_passes():
    site = Path(__file__).resolve().parent.parent / "site"
    if not (site / "theme.js").is_file():
        pytest.skip("site/theme.js not present")
    assert check_e_theme_js_lang_sync(str(site)) == []


# ── page discovery + full run ─────────────────────────────────────────────────


def test_non_globe_deck_pages_are_skipped(tmp_path):
    """Pages without .gd-stage are ignored (only lang-sync check still fires on theme.js)."""
    (tmp_path / "theme.js").write_text("documentElement.lang = 'en';", encoding="utf-8")
    (tmp_path / "other.html").write_text(
        '<html lang="en"><head></head><body><div class="normal-page">Hi</div></body></html>',
        encoding="utf-8",
    )
    violations = run_checks(str(tmp_path))
    assert violations == []


def test_globe_deck_page_with_violations_is_detected(tmp_path):
    """A globe-deck page with an aria-hidden trap is caught by run_checks."""
    (tmp_path / "theme.js").write_text("documentElement.lang = 'en';", encoding="utf-8")
    html = (
        '<html lang="en"><head>'
        '<meta name="viewport" content="width=device-width, viewport-fit=cover">'
        '<script>document.documentElement.setAttribute("data-lang","en")</script>'
        '<style>html[data-theme="light"] .pill{color:color-mix(in srgb,var(--accent) 48%,var(--text))}'
        'body{padding:env(safe-area-inset-bottom)}</style></head><body>'
        + _GLOBE_MARKER
        + '<div aria-hidden="true"><button>Bad</button></div></body></html>'
    )
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    violations = run_checks(str(tmp_path))
    assert any("(a)" in loc_msg[1] for loc_msg in violations)


def test_main_exits_0_on_clean_tree(tmp_path):
    """main() returns 0 when the site_dir has no globe-deck pages and theme.js is clean."""
    (tmp_path / "theme.js").write_text("documentElement.lang = 'en';", encoding="utf-8")
    assert main([str(tmp_path)]) == 0


def test_main_exits_1_on_violation(tmp_path):
    (tmp_path / "theme.js").write_text("documentElement.lang = 'en';", encoding="utf-8")
    html = (
        '<html lang="en"><head>'
        '<meta name="viewport" content="width=device-width, viewport-fit=cover">'
        '<script>document.documentElement.setAttribute("data-lang","en")</script>'
        '<style>html[data-theme="light"] .pill{color:color-mix(in srgb,var(--accent) 48%,var(--text))}'
        'body{padding:env(safe-area-inset-bottom)}</style></head><body>'
        + _GLOBE_MARKER
        + '<div aria-hidden="true"><input type="text"></div></body></html>'
    )
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    assert main([str(tmp_path)]) == 1


def test_main_real_site_passes():
    """The committed site/ must pass all checks end-to-end."""
    site = Path(__file__).resolve().parent.parent / "site"
    if not site.is_dir():
        pytest.skip("site/ not built")
    assert main([str(site)]) == 0
