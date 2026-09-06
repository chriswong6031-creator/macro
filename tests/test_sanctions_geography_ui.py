"""F02-X1 sanctions-geography presentation surface — hostile UI contract tests.

Scope: ONLY the presentation lane owned by internal collaborator A —
``templates/sanctions_geography.{html.j2,css,js}`` and the paired
``site/sanctions_geography.{html,css,js}`` copies. The collector, parser,
projector and build script are a different owner's frozen surface and are never
asserted here beyond the interface they publish.

What these tests defend, in the order the failures would hurt:

1. THE RENDER CONTRACT IS EXACT. ``scripts/build_sanctions_geography.render()``
   builds a bare Jinja ``Environment`` with ``StrictUndefined`` and passes
   exactly four names. A template that reaches for a fifth raises at build time,
   not at review time, so the render is exercised here with that exact env.
2. THE PAGE CANNOT CLAIM A LOCATION. Every count on this surface is "entries
   whose published address field names this country" — a documentary fact about
   paperwork, not about where anyone or anything is. The freeze, the doctrine's
   honesty law and collaborator B's accepted UX falsifier all converge on this,
   so it is asserted as markup, not left to prose review.
3. THE GOVERNED LAYER OWNS THE PIXELS. The design ratchet
   (``check_design_system.py``) treats a template unknown to the page registry as
   NEW and therefore governed; the runtime-style guard
   (``check_runtime_style_injection.py``) hard-fails any JS that injects a
   stylesheet and is absent from the frozen allowlist. Both are re-asserted
   directly against these three files so a violation fails in this suite —
   which a session runs — and not only in the CI pack, which it may not.
4. LIGHT IS A DESIGN, NOT A TOKEN SWAP (theme art-direction law). A stylesheet
   that never names ``[data-theme="light"]`` has not been art-directed; that is
   a mechanical assertion and it is made here.
5. EN/ZH PARITY IS STRUCTURAL. The house mechanism is dual-emit
   ``.l-en``/``.l-zh`` spans switched by ``html[data-lang]`` in theme.css. An
   unpaired span is a string that vanishes in one language.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.check_design_system as DS  # noqa: E402
import scripts.check_runtime_style_injection as RSI  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"

TPL = TEMPLATES / "sanctions_geography.html.j2"
CSS = TEMPLATES / "sanctions_geography.css"
JS = TEMPLATES / "sanctions_geography.js"


# The exact four names scripts/build_sanctions_geography.py::render() passes.
# Widening this dict in a test is how a template silently acquires a fifth
# variable that the real builder will not supply.
RENDER_CONTEXT = {
    "active_section": "research",
    "active_page": "sanctions_geography",
    "source_state": "CURRENT",
    "projection_id": "sha256:7071ac3962103ccea2c12d4451625acbbfc226ffcb85051952a99d92b06c0785",
}


def _render(**overrides) -> str:
    """Render through the builder's exact environment shape."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    ctx = dict(RENDER_CONTEXT)
    ctx.update(overrides)
    return env.get_template("sanctions_geography.html.j2").render(**ctx)


@pytest.fixture(scope="module")
def html() -> str:
    return _render()


@pytest.fixture(scope="module")
def css_text() -> str:
    return CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_text() -> str:
    return JS.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 1 — the frozen render contract
# --------------------------------------------------------------------------

def test_all_three_owned_templates_exist():
    for path in (TPL, CSS, JS):
        assert path.is_file(), f"missing owned surface: {path.relative_to(ROOT)}"


def test_renders_under_the_builders_exact_environment(html):
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_render_uses_no_variable_beyond_the_frozen_four():
    """A fifth name would raise UndefinedError inside the real build, not here.

    Rendering with ONLY the four frozen names already proves it; this test
    states the reason so the next reader does not "helpfully" add a fifth.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    env.get_template("sanctions_geography.html.j2").render(**RENDER_CONTEXT)


@pytest.mark.parametrize(
    "state", ["CURRENT", "SOURCE_STALE", "SOURCE_UNAVAILABLE", "PARSER_SHAPE_CHANGED"]
)
def test_every_frozen_source_state_renders(state):
    """A degraded source must still produce a page, never a build crash."""
    out = _render(source_state=state)
    assert "</html>" in out
    assert 'data-source-state="%s"' % state in out


def test_projection_id_is_carried_into_the_document(html):
    """The receipt is the page's identity device; it must survive the render."""
    assert RENDER_CONTEXT["projection_id"] in html


# --------------------------------------------------------------------------
# 2 — honest sanctions / geography semantics
# --------------------------------------------------------------------------

def test_geography_basis_is_stated_as_published_address(html):
    lowered = html.lower()
    assert "published address" in lowered
    assert "地址" in html, "the published-address basis must also be stated in ZH"


def test_page_denies_the_current_location_reading_in_both_languages(html):
    """The single most dangerous misreading of this surface, refused in markup."""
    lowered = html.lower()
    assert "not a current location" in lowered or "never a current location" in lowered
    assert "并非当前位置" in html or "不是当前位置" in html


def test_thematic_programs_are_not_misread_as_absent_geography(html):
    """Collaborator B's accepted falsifier: non-country-tied programs (cyber,
    narcotics, proliferation) have no address geography by nature. A map that
    stays silent about that reads their blankness as 'nothing here'."""
    lowered = html.lower()
    assert "program" in lowered
    assert "geo_unresolved" in lowered or "unresolved" in lowered


def test_unresolved_geography_is_a_named_state_not_a_zero(html, js_text):
    assert "GEOGRAPHY_UNRESOLVED" in html or "GEOGRAPHY_UNRESOLVED" in js_text


def test_no_compliance_screening_affordance(html):
    """This is a context surface. A screening verb would misrepresent it as a
    sanctions-compliance tool, which the freeze forbids outright."""
    lowered = html.lower()
    for banned in ("screen your", "screening tool", "compliance check",
                   "check a counterparty", "sanctions screening"):
        assert banned not in lowered, f"compliance-screening affordance: {banned!r}"


def test_no_prediction_or_trade_language(html):
    lowered = html.lower()
    for banned in ("buy ", "sell ", "price target", "forecast", "we expect",
                   "will be sanctioned", "trade idea"):
        assert banned not in lowered, f"out-of-scope claim: {banned!r}"


def test_membership_truth_is_the_full_snapshot_not_the_delta(html):
    """Delta omission never implies removal — stated where a reader can see it."""
    lowered = html.lower()
    assert "delta" in lowered
    assert "removal" in lowered or "removed" in lowered


def test_official_source_owner_is_named(html):
    assert "OFAC" in html
    lowered = html.lower()
    assert "treasury" in lowered


def test_boundary_rights_and_schematic_caveat_are_disclosed(html):
    lowered = html.lower()
    assert "natural earth" in lowered
    assert "schematic" in lowered or "disputed" in lowered


def test_no_banned_tier1_vocabulary(html, css_text, js_text):
    """The design ratchet's seed list, asserted on the surface that ships."""
    for name, text in (("template", html), ("css", css_text), ("js", js_text)):
        lowered = text.lower()
        for word in DS.BANNED_VOCABULARY_SEED:
            assert word not in lowered, f"banned Tier-1 vocabulary {word!r} in {name}"


def test_no_validated_claim_word(html):
    """`scripts/check_validated_claims.py` is CI-enforced on user-facing text."""
    assert "validated" not in html.lower()


# --------------------------------------------------------------------------
# 3 — the governed presentation layer owns the pixels
# --------------------------------------------------------------------------

def _blocking(rel: str, text: str):
    return [f for f in DS.scan_text(rel, text) if f.rule in DS.ADDED_BLOCKING_RULES]


def test_owned_templates_trip_no_blocking_design_rule(css_text, js_text):
    """These files are NEW, so `--mode enforce` governs them in full and
    `--mode enforce-added` blocks every added line. A hex, a font stack, a raw
    radius, a literal custom property, a second :root or an emoji fails CI."""
    findings = []
    findings += _blocking("templates/sanctions_geography.css", css_text)
    findings += _blocking("templates/sanctions_geography.js", js_text)
    findings += _blocking("templates/sanctions_geography.html.j2",
                          TPL.read_text(encoding="utf-8"))
    assert not findings, "design-system blocking findings: " + "; ".join(
        f"{f.rule} @ {f.path}:{f.line} — {f.detail}" for f in findings)


def test_stylesheet_declares_no_parallel_token_root(css_text):
    """Named separately from the sweep above because it is the rule most likely
    to be reintroduced by someone 'just adding a couple of page variables'."""
    assert not DS.ROOT_BLOCK_RE.search(css_text), (
        "a :root block outside theme.css is a second palette")


def test_owned_js_injects_no_stylesheet_at_runtime(js_text):
    """`check_runtime_style_injection.py` hard-fails a JS file that injects and
    is absent from the frozen allowlist — and that allowlist is not ours to
    edit. Styling therefore lives in CSS, without exception."""
    assert RSI.file_counts(js_text) == {}, (
        "runtime stylesheet injection in an un-allowlisted file")


def test_template_carries_no_inline_style_block():
    """An inline <style> would move design decisions back out of the governed
    stylesheet and trips the visual-evidence gate's second material shape."""
    assert not re.search(r"<style(?:\s|>)", TPL.read_text(encoding="utf-8"), re.I)


def test_no_emoji_anywhere_in_the_owned_surface(css_text, js_text):
    """Doctrine §5.8: emoji are not UI icons. The blocking range only."""
    for name, text in (("template", TPL.read_text(encoding="utf-8")),
                       ("css", css_text), ("js", js_text)):
        found = DS.EMOJI_BLOCKING_RE.findall(text)
        assert not found, f"emoji in {name}: {found[:5]}"


def test_colour_semantics_use_language_stable_tokens_only(css_text):
    """`--up`/`--down` FLIP in ZH (红涨绿跌). A sanctions add is not 'up', and a
    degraded source must not turn green in Chinese, so this surface may not key
    any state colour off the directional pair."""
    for token in ("var(--up", "var(--down", "var(--ink-up", "var(--ink-down"):
        assert token not in css_text, (
            f"{token}…) flips meaning in ZH and must not carry sanctions state")


# --------------------------------------------------------------------------
# 4 — theme art direction: dark and light are two designs
# --------------------------------------------------------------------------

def test_light_theme_is_art_directed_not_merely_inherited(css_text):
    assert 'data-theme="light"' in css_text, (
        "no light-specific rule exists — a token swap is not a light design")


def test_light_treatment_covers_the_map_and_the_panels(css_text):
    light_rules = [ln for ln in css_text.splitlines() if 'data-theme="light"' in ln]
    blob = "\n".join(light_rules)
    assert "sg-geo" in blob or "sg-map" in blob, "the map has no light treatment"
    assert re.search(r"sg-(panel|card|rail|tbl|read|src)", blob), (
        "no panel-family surface has a light treatment")


def test_dark_is_the_default_and_is_not_written_as_an_override(css_text):
    """Pages here are dark-first: the base rules ARE dark. A `[data-theme="dark"]`
    override block means the base was authored for light and dark was bolted on."""
    assert css_text.count('data-theme="dark"') <= 2, (
        "dark should be the base art direction, not an override layer")


# --------------------------------------------------------------------------
# 5 — bilingual parity
# --------------------------------------------------------------------------

def test_every_language_span_is_paired(html):
    en = len(re.findall(r'<span class="l-en">', html))
    zh = len(re.findall(r'<span class="l-zh">', html))
    assert en == zh, f"unpaired language spans: {en} EN vs {zh} ZH"
    assert en >= 20, "too few bilingual strings for a full surface"


def test_form_controls_do_not_dual_emit_language_spans(html):
    """An <option> holds text only, so a .l-en/.l-zh pair inside one renders as
    BOTH languages concatenated — the browser pass caught exactly that
    ("Most entries条目最多"). Controls use the data-label-en/zh idiom instead."""
    for opt in re.findall(r"<option\b[^>]*>(.*?)</option>", html, re.S):
        assert "l-en" not in opt and "l-zh" not in opt, (
            f"dual-emit spans inside an <option>: {opt[:80]!r}")
    for opt_tag in re.findall(r"<option\b[^>]*>", html):
        assert "data-label-en=" in opt_tag and "data-label-zh=" in opt_tag, (
            f"<option> carries no bilingual labels: {opt_tag}")
    for tag in re.findall(r"<input\b[^>]*>", html):
        if "placeholder=" in tag:
            assert "data-ph-zh=" in tag, f"placeholder with no ZH twin: {tag}"


def test_page_script_reapplies_language_to_form_controls(js_text):
    """Swapping at boot only would leave the control in the boot language after
    a mid-session flip; theme.js announces the change with `langchange`."""
    assert "langchange" in js_text
    assert "data-label-zh" in js_text and "data-ph-zh" in js_text


def test_no_translated_text_in_title_attributes(html):
    """CI-guarded house rule: `title=` is not a bilingual home; LENS data-tip is."""
    for value in re.findall(r'title="([^"]*)"', html):
        assert not re.search(r"[一-鿿]", value), (
            f"ZH text in a title attribute: {value!r}")


def test_zh_copy_carries_no_raw_english_state_enum(html):
    """`慢速评级: HOLD` is the shape this forbids — an EN machine token dropped
    into ZH copy, which reads as untranslated to the person it addresses."""
    for zh in re.findall(r'<span class="l-zh">(.*?)</span>', html, re.S):
        assert not re.search(r"\b(CURRENT|ADDED_SINCE_PREVIOUS|REMOVED_SINCE_PREVIOUS|SOURCE_CORRECTED|"
                             r"GEOGRAPHY_UNRESOLVED|SOURCE_UNAVAILABLE|SOURCE_STALE|"
                             r"PARSER_SHAPE_CHANGED|NO_RESULTS)\b", zh), (
            f"raw EN state enum inside ZH copy: {zh[:80]!r}")


# --------------------------------------------------------------------------
# 5b — repairs pinned by review; each of these shipped broken once
# --------------------------------------------------------------------------

def test_translation_strings_are_never_marked_safe():
    """`|safe` on the bilingual macro turns every future translation string into
    an injection surface to satisfy one bold clause. Emphasis is real markup."""
    body = TPL.read_text(encoding="utf-8")
    macro = re.search(r"\{%\s*macro\s+t\(.*?endmacro\s*%\}", body, re.S)
    assert macro, "the bilingual macro is gone"
    assert "|safe" not in macro.group(0), "t() must escape its arguments"
    assert "<strong>" in body, "emphasis must exist as markup, not inside a string"


def test_caveat_emphasis_survives_escaping(html):
    """The bold clause must reach the browser as emphasis, not as literal tags."""
    assert "&lt;b&gt;" not in html, "escaped markup is being shown to the reader"
    assert re.search(r"<strong>.*?not a current location.*?</strong>", html, re.S)


def test_seo_path_is_the_canonical_hyphenated_route():
    body = TPL.read_text(encoding="utf-8")
    assert 'seo_path = "sanctions-geography.html"' in body
    assert 'seo_path = "sanctions_geography.html"' not in body


def test_page_owns_its_own_canvas_from_tokens(css_text):
    """theme.css does not paint <body>; a page that forgets ships dark panels on
    the browser's white default, which a pixel sample of the first dark capture
    confirmed. The frame is owned here, from tokens, for this page only."""
    block = re.search(r"(?<![\w.\-])body\s*\{[^}]*\}", css_text)
    assert block, "this page never sets a body frame"
    assert "var(--bg)" in block.group(0), "canvas must come from the theme token"
    assert "var(--text)" in block.group(0)


def test_freshness_hook_and_source_hook_are_on_visible_elements(html):
    """The canonical observer probes [data-asof] and [data-source]. Both must sit
    on elements that are actually rendered, not inside a collapsed disclosure."""
    assert re.search(r'<span[^>]*data-sg-asof[^>]*data-asof', html) or \
           re.search(r'<span[^>]*data-asof[^>]*data-sg-asof', html)
    prov = re.search(r'<div[^>]*data-sg-prov[^>]*>', html)
    assert prov and "data-source" in prov.group(0), (
        "the visible provenance rail must carry the source hook")


@pytest.mark.parametrize("hook,label", [
    ("data-sg-view", "register view"),
    ("data-sg-program", "program"),
    ("data-sg-type", "entry type"),
    ("data-sg-change", "official change state"),
    ("data-sg-sort", "sort"),
])
def test_every_required_filter_control_exists_and_is_labelled(html, hook, label):
    tag = re.search(r"<select[^>]*%s[^>]*>" % re.escape(hook), html)
    assert tag, f"missing the {label} control"
    assert "aria-label=" in tag.group(0), f"the {label} control has no accessible name"


def test_the_filter_inventory_is_visibly_complete(html):
    """#6821 names list / program / entry type / change state / geography
    resolution. This vertical reads exactly ONE list, so that control is fixed
    and disabled rather than omitted — an absent control reads as a missing
    capability, a disabled one states the truth."""
    tag = re.search(r"<select[^>]*data-sg-list[^>]*>", html)
    assert tag, "no list control — the filter inventory looks incomplete"
    assert "disabled" in tag.group(0), (
        "one list means the control must be fixed, not a chooser implying a choice")
    assert "OFAC SDN" in html


def test_map_and_table_show_the_same_filtered_register(js_text, css_text):
    """A map left fully lit beside a twelve-row table contradicts the list next
    to it, and a selection the filter excluded is a claim about an invisible row."""
    assert "syncMap" in js_text, "the map is never synchronized with the filters"
    assert "is-off" in js_text and "is-off" in css_text
    assert "model.selected = null" in js_text, (
        "a selection filtered out of view must be cleared")


def test_a_filtered_boundary_is_unreachable_by_keyboard_too(js_text):
    """`pointer-events:none` only takes the mouse away. A dimmed boundary that
    keeps tabindex=0 and its Enter/Space handler is still selectable by keyboard,
    so the filter would apply to one input device and not the other."""
    assert 'setAttribute("tabindex", off ? "-1" : "0")' in js_text, (
        "focusability must move with the filtered state")
    assert 'setAttribute("aria-disabled", off ? "true" : "false")' in js_text
    assert js_text.count('classList.contains("is-off")') >= 2, (
        "both the click and the keydown handler must refuse a filtered boundary")


def test_the_filter_group_landmark_is_also_bilingual(html):
    tag = re.search(r"<div[^>]*data-sg-filters[^>]*>", html, re.S)
    assert tag, "the filter group is gone"
    assert 'role="group"' in tag.group(0)
    assert "data-aria-en=" in tag.group(0) and "data-aria-zh=" in tag.group(0)


def test_a_dimmed_boundary_is_not_styled_as_an_honest_zero(css_text):
    """Filtered-out and no-data must stay visually distinct, or the map starts
    reporting zeros it does not have."""
    off = re.search(r"\.sg-geo\.is-off\s*\{[^}]*\}", css_text)
    assert off and "opacity" in off.group(0)
    assert 'html[data-theme="light"] .sg-geo.is-off' in css_text, (
        "a dim tuned for a dark field is nearly invisible on paper")


@pytest.mark.parametrize("hook", [
    "data-sg-search", "data-sg-list", "data-sg-view",
    "data-sg-program", "data-sg-type", "data-sg-change", "data-sg-sort",
])
def test_every_control_carries_a_bilingual_accessible_name(html, hook):
    """An accessible name left in English is still an untranslated string — it is
    just one only a screen-reader user hears."""
    tag = re.search(r"<(?:select|input)[^>]*%s[^>]*>" % re.escape(hook), html)
    assert tag, f"missing control {hook}"
    assert "data-aria-en=" in tag.group(0) and "data-aria-zh=" in tag.group(0), (
        f"{hook} has no bilingual accessible name")


def test_locale_switch_applies_accessible_names_not_only_visible_text(js_text):
    assert "data-aria-zh" in js_text
    assert 'setAttribute("aria-label"' in js_text


def test_filters_are_disabled_rather_than_silently_ignored(js_text):
    """A control the current view cannot apply must say so, or the UI is
    claiming a filter it is not honouring."""
    assert "syncControls" in js_text
    assert "disabled" in js_text and "aria-disabled" in js_text


def test_entry_type_filter_is_derived_from_entries_not_from_names(js_text):
    assert "typesByGeo" in js_text
    assert "entity_type" in js_text


def test_staleness_is_derived_from_the_deadline_not_only_from_a_label(js_text):
    """The deterministic artifact carries source_state=CURRENT plus a
    freshness.stale_after deadline; staleness is a fact about the clock."""
    assert "stale_after" in js_text
    assert "deadlinePassed" in js_text, (
        "staleness must be derived from the deadline, not only from an explicit label")


def test_a_nameless_correction_row_still_shows_its_uid(js_text):
    """Delta corrections may legally omit the entity-level name; a blank heading
    would drop the one identifier that is always published."""
    assert "displayName" in js_text
    assert "OFAC UID " in js_text


# --------------------------------------------------------------------------
# 6 — shell, structure, accessibility
# --------------------------------------------------------------------------

def test_uses_the_canonical_product_nav_and_invents_no_third_header(html):
    assert '<nav class="site-nav">' in html, "must include _site_nav.html.j2"
    assert html.count('<nav class="site-nav">') == 1
    assert '<div class="topbar"' not in html, "third header family"


def test_exactly_one_h1(html):
    assert len(re.findall(r"<h1\b", html)) == 1


def test_sections_head_with_h2_and_stay_within_the_archetype_budget(html):
    h2s = re.findall(r"<h2\b", html)
    assert len(h2s) >= 3, "sections must be headed so the outline is navigable"
    l1 = re.findall(r'<section\b[^>]*class="[^"]*\bsg-sec\b', html)
    assert 1 <= len(l1) <= 6, (
        f"archetype E allows at most 6 first-level sections, found {len(l1)}")


def test_map_is_an_accessible_group_with_interactive_children(html):
    m = re.search(r"<svg\b[^>]*class=\"[^\"]*sg-map[^\"]*\"[^>]*>", html)
    assert m, "no .sg-map svg"
    tag = m.group(0)
    assert 'role="group"' in tag
    assert "aria-labelledby=" in tag or "aria-label=" in tag


def test_map_is_not_the_only_path_to_the_data(html):
    """Hover/click on a map is not reachable for every user; the table is the
    keyboard and screen-reader path to the same counts."""
    assert re.search(r'<table\b[^>]*class="[^"]*sg-tbl', html), "no country table"


def test_table_scrolls_inside_its_own_container(css_text, html):
    assert re.search(r'class="[^"]*sg-tblwrap', html), "table lacks a scroll box"
    block = re.search(r"\.sg-tblwrap\s*\{[^}]*\}", css_text)
    assert block and "overflow" in block.group(0), (
        "the box must scroll, so the page never scrolls horizontally")


def test_focus_is_visible_on_interactive_elements(css_text):
    assert ":focus-visible" in css_text


def test_reduced_motion_is_respected(css_text):
    assert "prefers-reduced-motion" in css_text


def test_mobile_floor_is_designed_at_390(css_text):
    widths = [int(w) for w in re.findall(r"max-width:\s*(\d+)px", css_text)]
    assert widths, "no responsive breakpoint at all"
    assert min(widths) <= 640, "no small-viewport recomposition"


def test_designed_loading_empty_and_error_states_exist(html, css_text, js_text):
    """Loading is a skeleton at true geometry; empty is a sentence with a why;
    error names what failed AND what still works. A bare '—' is not a state."""
    assert "sg-skel" in css_text and "sg-skel" in html, "no loading skeleton"
    assert "sg-empty" in css_text, "no designed empty state"
    assert "sg-empty-why" in css_text or "sg-empty-why" in js_text, (
        "an empty state without a stated cause is a dead end")
    assert "NO_RESULTS" in js_text, "the frozen empty-query state is unhandled"


# --------------------------------------------------------------------------
# 7 — the data contract, bound to the frozen projection
# --------------------------------------------------------------------------

def test_js_reads_the_frozen_artifact_name(js_text):
    assert "sanctions-geography-data.json" in js_text


def test_js_binds_only_frozen_schema_keys(js_text):
    for key in ("summary", "countries", "changes",
                "unresolved_geography", "source", "freshness", "method"):
        assert key in js_text, f"frozen projection key never consumed: {key}"


def test_js_reuses_the_existing_boundary_asset(js_text):
    assert "world-110m.json" in js_text
    assert "countries" in js_text


def test_page_declares_no_second_country_authority(js_text):
    """Geometry ids come from the projection's own `geo_id`; a page-local
    country table would be exactly the second ISO authority the freeze bans."""
    assert "geo_id" in js_text
    iso_like = re.findall(r"[\"'](?:AF|AL|DZ|AR|AU|AT|BR|CA|CN|CU|FR|DE|IN|IR|"
                          r"IQ|JP|KP|RU|SY|GB|US|VE)[\"']\s*:", js_text)
    assert not iso_like, f"page-local country map detected: {iso_like[:5]}"


def test_js_never_infers_a_removal(js_text):
    """`delta omission never implies removal` is a correctness rule, so the
    REMOVED_SINCE_PREVIOUS state may only come from an explicit official action field."""
    assert "REMOVED_SINCE_PREVIOUS" in js_text
    assert "action" in js_text or "state" in js_text


def test_degraded_provenance_prefers_projection_state_over_last_good_receipt(js_text):
    assert "p.source_state || src.source_health" in js_text
    assert 'health === "SOURCE_STALE"' in js_text


def test_idless_topology_shapes_are_not_painted_as_honest_zero(js_text, css_text):
    assert "is-identityless" in js_text
    assert ".sg-geo.is-identityless" in css_text
    assert "data-step" in js_text


def test_map_accessible_names_are_bilingual_and_reapplied_on_language_change(js_text):
    assert "updateMapAccessibleNames" in js_text
    assert "data-name-en" in js_text and "data-name-zh" in js_text
    apply_lang = re.search(r"function applyLang\(\)\s*\{.*?\n  \}", js_text, re.S)
    assert apply_lang and "updateMapAccessibleNames" in apply_lang.group(0)


def test_committed_dom_probe_executes_selection_clear_and_language_refresh():
    probe = ROOT / "scripts" / "sanctions_geography_dom_probe.js"
    assert probe.is_file(), "the behavioral DOM probe must be committed and reproducible"
    completed = subprocess.run(
        ["node", str(probe), str(JS)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["selection_cleared"] == 1
    assert result["dimmed_keyboard_reachable"] == 0
    assert result["zh_map_name_applied"] is True
    assert result["initial_shard_requests"] == 0
    assert result["selection_shard_requests"] == 1
    assert result["selected_entries_loaded"] == 1
    assert result["tampered_shard_refused"] is True
    assert result["tampered_shard_state_error"] is True


# --------------------------------------------------------------------------
# 8 — the paired site artifacts, bound to the BUILDER's own constants
# --------------------------------------------------------------------------
#
# The site-side filenames are the source lane's decision, not ours: the builder
# renamed them mid-build (underscored -> hyphenated) while this suite was being
# written. Hard-coding either spelling here would have turned that ordinary
# upstream choice into a red test in a lane that does not own the constant. So
# the mapping is READ from scripts/build_sanctions_geography.py by parsing it —
# never by importing it, because importing would execute the source lane's
# collector/engine modules and make this suite fail for their reasons.


def _builder_constants() -> tuple[str, dict[str, str]]:
    """`PAGE_NAME` and `ASSET_MAP` as literals, without executing the module."""
    import ast

    tree = ast.parse((ROOT / "scripts" / "build_sanctions_geography.py").read_text("utf-8"))
    found: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ("PAGE_NAME", "ASSET_MAP", "ASSETS"):
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    page = found.get("PAGE_NAME")
    assert isinstance(page, str), "builder no longer declares a literal PAGE_NAME"

    mapping = found.get("ASSET_MAP")
    if isinstance(mapping, dict):
        return page, {str(k): str(v) for k, v in mapping.items()}
    # Older builder shape: a flat tuple copied name-for-name.
    assets = found.get("ASSETS")
    assert isinstance(assets, (list, tuple)), "builder declares neither ASSET_MAP nor ASSETS"
    return page, {str(a): str(a) for a in assets}


def test_builder_still_renders_this_lanes_template():
    """If the builder stops rendering our template, this suite is guarding a
    file nobody ships — a silent failure worth failing loudly."""
    body = (ROOT / "scripts" / "build_sanctions_geography.py").read_text("utf-8")
    assert "sanctions_geography.html.j2" in body


def test_every_owned_template_asset_has_a_byte_identical_site_copy():
    _, mapping = _builder_constants()
    owned = {k: v for k, v in mapping.items() if k.startswith("sanctions_geography.")}
    assert set(owned) == {"sanctions_geography.css", "sanctions_geography.js"}, (
        f"the builder's owned-asset set moved: {sorted(owned)}")
    for source_name, site_name in sorted(owned.items()):
        src = TEMPLATES / source_name
        dst = SITE / site_name
        assert dst.is_file(), f"missing paired site copy: site/{site_name}"
        assert src.read_bytes() == dst.read_bytes(), (
            f"site/{site_name} diverges from templates/{source_name} — "
            "re-render the page instead of hand-editing the site copy")


def test_rendered_site_page_exists_and_links_the_owned_assets():
    page_name, mapping = _builder_constants()
    page = SITE / page_name
    assert page.is_file(), f"site/{page_name} was never built"
    out = page.read_text(encoding="utf-8")
    for site_name in mapping.values():
        assert site_name in out, f"the rendered page never references {site_name}"


def test_rendered_site_page_carries_the_same_honest_semantics():
    """The template is what we author; the site page is what a reader loads.
    Asserting only the template would let a render step silently drop a caveat."""
    page_name, _ = _builder_constants()
    out = (SITE / page_name).read_text(encoding="utf-8")
    lowered = out.lower()
    assert "not a current location" in lowered
    assert "并非当前位置" in out
    assert "published address" in lowered
    assert out.count('<nav class="site-nav">') == 1
    assert len(re.findall(r"<h1\b", out)) == 1


# --------------------------------------------------------------------------
# 9 — the canonical theme-parity receipt (added to this lane's writer boundary
#     by the operation's path ruling; verify_shots stays as working evidence)
# --------------------------------------------------------------------------

EVIDENCE_DIR = ROOT / "mockups" / "evidence" / "sanctions-geography"


def _guard():
    import scripts.check_ui_visual_evidence as guard
    return guard


def test_canonical_receipt_exists_and_carries_only_the_allowed_keys():
    import yaml

    receipt = EVIDENCE_DIR / "EVIDENCE.yml"
    assert receipt.is_file(), "the canonical TP-0 receipt is missing"
    data = yaml.safe_load(receipt.read_text(encoding="utf-8"))
    guard = _guard()
    assert set(data) == guard.RECEIPT_ALLOWED_KEYS, (
        "an extra key on a receipt is a second evidence plane starting to grow")
    assert data["schema"] == guard.RECEIPT_SCHEMA


def test_receipt_owns_the_only_material_path_this_lane_adds():
    """Only the stylesheet is a material UI change under the guard's three
    shapes — the template carries no inline <style and the script injects no
    rules — but the receipt must literally list whatever is material."""
    import yaml

    guard = _guard()
    data = yaml.safe_load((EVIDENCE_DIR / "EVIDENCE.yml").read_text(encoding="utf-8"))
    added = {
        p: (TEMPLATES / pathlib_name).read_text(encoding="utf-8").splitlines()
        for p, pathlib_name in (
            ("templates/sanctions_geography.css", "sanctions_geography.css"),
            ("templates/sanctions_geography.js", "sanctions_geography.js"),
            ("templates/sanctions_geography.html.j2", "sanctions_geography.html.j2"),
        )
    }
    material = guard.material_paths(added)
    assert material, "expected the stylesheet to register as a material UI change"
    for path in material:
        assert path in data["changed_paths"], f"receipt does not own {path}"


def test_referenced_manifest_carries_all_eight_rest_cells():
    guard = _guard()
    import yaml

    data = yaml.safe_load((EVIDENCE_DIR / "EVIDENCE.yml").read_text(encoding="utf-8"))
    record = guard.ReceiptRecord(
        path="mockups/evidence/sanctions-geography/EVIDENCE.yml", data=data, error=None)
    errors = guard.validate_manifest_evidence(record, ROOT)
    assert not errors, "; ".join(errors)


def test_state_evidence_covers_the_paths_a_rest_capture_cannot_reach():
    """Interaction and degraded-source states, each with recorded DOM
    assertions — a picture nobody can check is not evidence."""
    log = EVIDENCE_DIR / "states" / "observations.json"
    assert log.is_file(), "no state-evidence log"
    payload = json.loads(log.read_text(encoding="utf-8"))
    assert payload["driver"] == "scripts/capture_sanctions_geography_states.py"
    assert (ROOT / payload["driver"]).is_file(), "state evidence has no committed driver"
    artifact_paths = {
        "data_sha256": SITE / "sanctions-geography-data.json",
        "page_sha256": SITE / "sanctions-geography.html",
        "css_sha256": SITE / "sanctions-geography.css",
        "js_sha256": SITE / "sanctions-geography.js",
        "driver_sha256": ROOT / payload["driver"],
    }
    for field, artifact in artifact_paths.items():
        assert payload["artifacts"][field] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    projection = json.loads((SITE / "sanctions-geography-data.json").read_text(encoding="utf-8"))
    assert payload["artifacts"]["projection_id"] == projection["projection_id"]
    assert payload["artifacts"]["source_identity"] == projection["source_identity"]
    captured = {c["state"] for c in payload["captures"]}
    for required in ("selected-boundary", "no-results", "filtered-map-sync",
                     "unresolved-register", "stale-derived", "unavailable",
                     "parser-shape-changed"):
        assert required in captured, f"no browser evidence for {required}"
    axis = {(c["state"], c["theme"], c["locale"]) for c in payload["captures"]}
    for state in ("selected-boundary", "no-results", "filtered-map-sync",
                  "unresolved-register", "stale-derived", "unavailable",
                  "parser-shape-changed"):
        for theme in ("dark", "light"):
            for locale in ("en", "zh"):
                assert (state, theme, locale) in axis, (
                    f"missing evidence cell {state}/{theme}/{locale}")
    for cap in payload["captures"]:
        assert (EVIDENCE_DIR / "states" / cap["file"]).is_file(), cap["file"]
    # Prefer an EN cell for mechanical DOM assertions so locale-specific copy
    # cannot vacate a structural check; every state still has a full axis above.
    by_state = {}
    for cap in payload["captures"]:
        if cap["theme"] == "dark" and cap["locale"] == "en":
            by_state[cap["state"]] = cap["observations"]
    assert by_state["no-results"]["empty_shown"] >= 1
    assert by_state["no-results"]["cause_stated"] >= 1
    assert by_state["no-results"]["primary_surface_state_slug_count"] == 0
    assert by_state["selected-boundary"]["row_focusable"] is True
    assert by_state["selected-boundary"]["map_path_selected"] == 1
    assert by_state["selected-boundary"]["initial_shard_requests"] == 0
    assert by_state["selected-boundary"]["selection_shard_requests"] == 1
    assert by_state["selected-boundary"]["zh_map_name_applied"] is True
    assert by_state["selected-boundary"]["identityless_paths"] > 0
    assert by_state["selected-boundary"]["identityless_paths_with_zero_count"] == 0
    assert by_state["unresolved-register"]["program_filter_disabled"] is True
    sync = by_state["filtered-map-sync"]
    assert sync["boundaries_dimmed"] > 0, "a filter left every boundary lit"
    assert sync["selection_cleared"] > 0, (
        "the capture did not exercise clearing a selection excluded by the filter")
    assert sync["dimmed_still_keyboard_reachable"] == 0, (
        "a filtered boundary was still reachable by keyboard — the filter would "
        "apply to the mouse and not to the tab key")
    assert sync["dimmed_missing_aria_disabled"] == 0
    assert sync["eligible_still_focusable"] == sync["rows"], (
        "the boundaries the filter kept must stay focusable")
    for degraded in ("stale-derived", "unavailable", "parser-shape-changed"):
        assert by_state[degraded]["state_code_visible"] is True
        assert by_state[degraded]["banner_shown"] == 1
        assert "SYNTHETIC" in by_state[degraded]["fixture"], (
            "a degraded-state capture must declare its fixture, never imply a real outage")
