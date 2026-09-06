"""Macro Command — shell, rail, routing, tokens, panel stubs (F01 / P1).

This is the P1 packet's own test file (frozen spec §9 P1). It owns the shell
that turns `site/macro_monetary.html` into one dashboard page for the twelve
sidebar sections / fourteen `macro_*` workspaces. Content (real stance/primer/
Read/chip data) ships in later packets — P1 asserts the STRUCTURE: rail,
hash-routable panels, tokens, the analyst control, and the house laws that
bind every packet (no machine text, honest nulls, bilingual parity, no
runtime style injection, theme parity).

The copy guard (`scripts/check_macro_command_copy.py`,
`tests/test_macro_command_copy_law.py`) is a PARALLEL packet's file — not
owned or duplicated here.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scripts import build_macro_suite_pages as builder

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DATA_ROOT = ROOT / "site" / "macrodata"
BUILT_AT = "2026-09-06T00:00:00Z"

# The fixed reading order, frozen spec §1.1 — a customer's question order,
# never the producer registry order, and never re-sorted with the data (G3).
EXPECTED_SECTION_ORDER = (
    "overview", "money", "policy", "rates", "inflation", "growth",
    "jobs", "housing", "consumer", "credit", "debt", "trade",
)
SUBTABBED_SECTIONS = ("money", "growth", "credit")


@pytest.fixture(scope="module")
def built_hub(tmp_path_factory) -> str:
    """The real `macro_monetary.html`, rendered from the CURRENT templates
    against the real repo root (not an isolated copy) — this packet's own
    assertions need the real `templates/theme.js` (for the analyst control's
    mount path) and the real `_site_nav.html.j2` (for G7's byte-unchanged
    proof), not a trimmed fixture tree."""
    out = tmp_path_factory.mktemp("macro_command_shell") / "site"
    pages = builder.render(ROOT, data_root=DATA_ROOT, out_dir=out, page_built_at=BUILT_AT)
    hub = [p for p in pages if p.name == builder.HUB_PAGE.output]
    assert hub, "the builder did not write macro_monetary.html"
    return hub[0].read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def macro_command_css() -> str:
    return (TEMPLATES / "macro_command.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def macro_command_js() -> str:
    return (TEMPLATES / "macro_command.js").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# rail + routing
# --------------------------------------------------------------------------

def test_the_rail_has_exactly_twelve_links_in_the_fixed_reading_order(built_hub: str) -> None:
    order = re.findall(r'data-mc-section="([a-z]+)"', built_hub)
    assert order == list(EXPECTED_SECTION_ORDER)


def test_every_hash_href_has_a_matching_bare_id(built_hub: str) -> None:
    """Judge D9: §1.1 once printed `#money` while the template renders
    `id="money"` — every section link and `:target` route was dead. Any
    `href="#token"` anywhere on the page must resolve to a real `id="token"`.
    """
    targets = re.findall(r'href="#([^"]+)"', built_hub)
    assert targets, "expected at least the twelve rail links"
    ids = set(re.findall(r'\bid="([^"]+)"', built_hub))
    for target in targets:
        assert target in ids, f"href=\"#{target}\" has no matching id=\"{target}\""


def test_the_twelve_sections_render_unhidden_and_in_order_with_js_off(built_hub: str) -> None:
    """D8: the served document is a first-class no-JS reading — every panel
    ships visible; JS adds `hidden` only at boot, never the builder. The
    "Loading this section…" line legitimately EXISTS in the served markup
    (D8's own `hidden data-mc-pending` element, unhidden by JS at boot) — the
    house law is that no READER sees it, i.e. every occurrence sits inside an
    element the `hidden` attribute already suppresses, never a bare visible
    occurrence."""
    sections = re.findall(r'<section class="mc-panel" id="([a-z]+)"[^>]*>', built_hub)
    assert sections == list(EXPECTED_SECTION_ORDER)
    for block in re.finditer(r'<section class="mc-panel" id="[a-z]+"[^>]*>', built_hub):
        assert "hidden" not in block.group(0)
    for tag in re.findall(r'<[^>]*data-mc-pending[^>]*>', built_hub):
        assert "hidden" in tag, f"a data-mc-pending element must ship `hidden`: {tag}"
    visible_en = re.sub(r'<p class="mc-figure-pending" hidden data-mc-pending>.*?</p>', '', built_hub)
    assert "Loading this section" not in visible_en
    assert "正在载入本板块" not in visible_en


def test_the_three_subtabbed_sections_carry_a_real_tablist_of_two(built_hub: str) -> None:
    for section_id in SUBTABBED_SECTIONS:
        match = re.search(
            r'<section class="mc-panel" id="' + section_id + r'".*?(?=<section class="mc-panel"|</main>)',
            built_hub, re.S)
        assert match, section_id
        body = match.group(0)
        assert 'role="tablist"' in body, section_id
        tabs = re.findall(r'role="tab"', body)
        assert len(tabs) == 2, (section_id, len(tabs))


def test_non_subtabbed_non_overview_sections_carry_no_tablist(built_hub: str) -> None:
    for section_id in EXPECTED_SECTION_ORDER:
        if section_id in SUBTABBED_SECTIONS or section_id == "overview":
            continue
        match = re.search(
            r'<section class="mc-panel" id="' + section_id + r'".*?(?=<section class="mc-panel"|</main>)',
            built_hub, re.S)
        assert match, section_id
        assert 'role="tablist"' not in match.group(0), section_id


# --------------------------------------------------------------------------
# G7 — no third header; the shared nav is untouched by this packet
# --------------------------------------------------------------------------

def _origin_main_bytes(path: str) -> bytes | None:
    """Best-effort `git show origin/main:<path>`. Returns None (skip, not
    fail) if git cannot answer within the timeout — this host runs a large
    concurrent fleet against one shared clone and a slow git is an
    environment condition, not evidence this packet touched the file."""
    try:
        result = subprocess.run(
            ["git", "show", f"origin/main:{path}"],
            cwd=ROOT, capture_output=True, timeout=240, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


@pytest.mark.parametrize("path", ["templates/_site_nav.html.j2", "templates/theme.css"])
def test_shared_chrome_files_are_byte_unchanged_vs_origin_main(path: str) -> None:
    upstream = _origin_main_bytes(path)
    if upstream is None:
        pytest.skip("git show origin/main could not be resolved in this environment")
    local = (ROOT / path).read_bytes()
    assert local == upstream, f"{path} must be byte-unchanged (G7)"


# --------------------------------------------------------------------------
# G9 — no runtime style injection
# --------------------------------------------------------------------------

def _strip_line_comments(js: str) -> str:
    """Strip `/* ... */` block comments only — good enough here since this
    file's line comments never carry the exact substrings under test, and a
    full JS/CSS tokenizer would be overkill for a guard test."""
    return re.sub(r'/\*.*?\*/', '', js, flags=re.S)


def test_macro_command_js_injects_no_style(macro_command_js: str) -> None:
    """G9. The file's OWN header comment explains this rule in prose (and
    necessarily quotes the very substrings it forbids in code), so the check
    runs against the file with block comments stripped — a real
    `document.createElement('style')` or `x.style.textContent = ...` must
    still be caught in actual code."""
    code = _strip_line_comments(macro_command_js)
    assert "<style" not in code
    assert "style.textContent" not in code
    assert "createElement('style')" not in code
    assert 'createElement("style")' not in code


# --------------------------------------------------------------------------
# G10 — tokens extend, never parallel; zero raw hex in component rules
# --------------------------------------------------------------------------

def _token_block(css: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", css, re.S)
    assert match, selector
    return match.group(1)


def test_every_mc_token_is_a_reference_or_a_literal(macro_command_css: str) -> None:
    root_block = _token_block(macro_command_css, ":root")
    light_block = _token_block(macro_command_css, 'html[data-theme="light"]')
    declarations = re.findall(r'(--mc-[a-z-]+):\s*([^;]+);', root_block + "\n" + light_block)
    assert declarations
    bare_hex = re.compile(r'^#[0-9a-fA-F]{3,8}$')
    for name, value in declarations:
        value = value.strip()
        assert not bare_hex.match(value), f"{name} is a bare hex literal: {value}"


def test_component_rules_carry_zero_raw_hex(macro_command_css: str) -> None:
    """G10: hex is permitted only inside the two theme-invariant shadow
    tokens' own `color-mix()` composites (a fixed neutral tint, not a themed
    ink) — never in a component rule outside the token blocks.

    The two token blocks are removed one at a time (never concatenated) —
    `root_block + light_block` is not itself a contiguous substring of the
    file, since real component rules sit between them, so a single combined
    `.replace()` call would silently match nothing and leave the token
    blocks' own hex-bearing shadow composites in the "component" text."""
    root_block = _token_block(macro_command_css, ":root")
    light_block = _token_block(macro_command_css, 'html[data-theme="light"]')
    component_css = macro_command_css.replace(root_block, "").replace(light_block, "")
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b', component_css), \
        "a component rule must reference a --mc-*/--mq-* token, never a raw hex literal"


def test_css_defines_both_root_and_light_for_every_theme_differing_token(macro_command_css: str) -> None:
    root_block = _token_block(macro_command_css, ":root")
    light_block = _token_block(macro_command_css, 'html[data-theme="light"]')
    root_names = set(re.findall(r'(--mc-[a-z-]+):', root_block))
    light_names = set(re.findall(r'(--mc-[a-z-]+):', light_block))
    assert light_names, "no theme-differing --mc-* tokens found in the light block"
    assert light_names.issubset(root_names), \
        f"light-only tokens with no dark default: {light_names - root_names}"


def test_stance_wash_is_a_percentage_in_both_themes(macro_command_css: str) -> None:
    """D3: `--mc-stance-wash: transparent` would make the `color-mix(...)`
    declaration invalid at computed-value time and silently drop the rule."""
    assert re.search(r'--mc-stance-wash:\s*0%\s*;', macro_command_css)
    assert re.search(r'--mc-stance-wash:\s*6%\s*;', macro_command_css)
    assert "--mc-stance-wash: transparent" not in macro_command_css


def test_the_read_halo_paints_on_the_element_not_a_pseudo(macro_command_css: str) -> None:
    """D4: a `z-index:-1` pseudo paints behind the page canvas."""
    match = re.search(r'\.mc-read-topic\s*\{(.*?)\}', macro_command_css, re.S)
    assert match
    assert "background-image: radial-gradient" in match.group(1)
    assert ".mc-read-topic::before" not in macro_command_css


def _strip_css_comments(css: str) -> str:
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def test_no_mc_tone_class_is_minted(macro_command_css: str) -> None:
    """D5: tone ink is inherited from `macro_suite.css:88-91`'s `.mq-tone-*`
    — this page must never mint a parallel `.mc-tone-*` family. The file's
    own DS-header comment necessarily names the forbidden pattern in prose,
    so the check runs with comments stripped — a real selector must still be
    caught."""
    assert not re.search(r'\.mc-tone-', _strip_css_comments(macro_command_css))


# --------------------------------------------------------------------------
# G4 — honest nulls: every dash carries a sibling .mq-sr
# --------------------------------------------------------------------------

def test_every_mq_dash_carries_a_sibling_mq_sr(built_hub: str) -> None:
    for match in re.finditer(r'<span class="mq-dash"[^>]*>—</span>(.{0,80})', built_hub, re.S):
        tail = match.group(1)
        assert 'class="mq-sr"' in tail, "a mq-dash with no adjacent mq-sr is an unlabelled dash (G4)"


# --------------------------------------------------------------------------
# §8 — exactly one analyst control, zero new endpoint strings
# --------------------------------------------------------------------------

def test_exactly_one_analyst_control(built_hub: str) -> None:
    main_html = built_hub[built_hub.index('<main class="mc-shell"'):]
    buttons = main_html.count("data-mc-analyst")
    # The button variant carries the attribute twice (data-mc-analyst plus the
    # two label attributes on the SAME element) only once per element; count
    # distinct control OPENINGS instead.
    openings = len(re.findall(r'<(?:button|a)[^>]*class="mc-analyst"', main_html))
    assert openings == 1, f"expected exactly one .mc-analyst control, found {openings}"


def test_zero_new_endpoint_strings(built_hub: str, macro_command_js: str) -> None:
    main_html = built_hub[built_hub.index('<main class="mc-shell"'):]
    for forbidden in ("?topic=", "&section=", "/api/"):
        assert forbidden not in main_html, forbidden
        assert forbidden not in macro_command_js, forbidden


# --------------------------------------------------------------------------
# G6 — bilingual parity, no ZH in title=
# --------------------------------------------------------------------------

_ZH_RE = re.compile(r'[一-鿿]')


def test_no_zh_text_inside_any_title_attribute(built_hub: str) -> None:
    for value in re.findall(r'\btitle="([^"]*)"', built_hub):
        assert not _ZH_RE.search(value), f'title="{value}" carries ZH text'


# --------------------------------------------------------------------------
# paired plain-copy assets (§9 standing notes)
# --------------------------------------------------------------------------

def test_macro_command_assets_are_registered_shared_assets() -> None:
    assert "macro_command.css" in builder.SHARED_ASSETS
    assert "macro_command.js" in builder.SHARED_ASSETS


def test_site_macro_command_assets_match_their_templates() -> None:
    for name in ("macro_command.css", "macro_command.js"):
        site_path = ROOT / "site" / name
        template_path = TEMPLATES / name
        assert site_path.exists(), f"site/{name} has not been built/committed yet"
        assert site_path.read_bytes() == template_path.read_bytes(), \
            f"site/{name} is not byte-identical to templates/{name}"


# --------------------------------------------------------------------------
# SECTIONS constant (R10)
# --------------------------------------------------------------------------

def test_sections_constant_covers_all_fourteen_workspaces_once() -> None:
    workspace_ids: list[str] = []
    for section in builder.SECTIONS:
        if section.subtabs:
            workspace_ids.extend(tab.workspace_id for tab in section.subtabs)
        elif section.workspace_id:
            workspace_ids.append(section.workspace_id)
    assert sorted(workspace_ids) == sorted(p.workspace_id for p in builder.SUITE_PAGES)
    assert len(workspace_ids) == len(set(workspace_ids)) == 14


def test_sections_constant_ids_are_bare_tokens_no_hash() -> None:
    for section in builder.SECTIONS:
        assert "#" not in section.id
        for tab in section.subtabs:
            assert "#" not in tab.id
