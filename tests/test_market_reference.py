"""Tests for scripts/build_market_reference.py (MOR-1 public Reference surface).

Verifies:
1. Registry validation fails closed on every DEC §3.3 / MOR1_CONTRACT.md rule,
   one red-fixture per rule (unknown owner ref, duplicate alias, superseded_by
   cycle, unsafe source URL, missing caveats on kind:indicator, missing either
   language, missing `_zh` sibling for a present unit_or_basis/interpretation_*
   field, schema mismatch, empty entries, invalid kind/family/authority_
   ceiling/status, non-kebab id, aliases presence parity, caveats length
   mismatch, superseded_by resolving to a real id, status:deprecated requiring
   superseded_by, and the B1 anchor-liveness rule) — each fixture violates
   exactly one rule so the failure message is attributable.
2. Happy-path build of the real committed registry: validates clean, the ZH
   supplement's coverage counts (34/26/26/34), and the rendered page carries
   the expected entry/family counts.
3. Anchor stability: every registry entry id appears as a real `id="..."`
   anchor in the rendered HTML (deep-link contract).
4. EN/ZH parity: every rendered entry carries both an `l-en` and an `l-zh`
   span (dual-language contract, build-time guaranteed per DEC §3.2), and the
   `l-zh` span for unit_or_basis/interpretation_* carries the REAL translated
   text from the MOR-1 ZH supplement, not an English-fallback echo.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.build_market_reference import (  # noqa: E402
    RegistryError,
    build_view_model,
    check_anchor_liveness,
    initial_of,
    search_key,
    validate,
)

REGISTRY_PATH = REPO / "config" / "market_reference.yml"
TEMPLATE_DIR = REPO / "templates"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _base_entry(**overrides) -> dict:
    """One minimal, otherwise-fully-valid registry entry. Tests override exactly
    the field(s) needed to trip one rule, so a fixture failure is attributable."""
    entry = {
        "id": "sample-term",
        "kind": "glossary",
        "family": "doctrine",
        "label_en": "Sample Term",
        "label_zh": "示例术语",
        "aliases_en": [],
        "aliases_zh": [],
        "short_definition_en": "A sample definition.",
        "short_definition_zh": "示例定义。",
        "why_it_matters_en": "It matters for the test.",
        "why_it_matters_zh": "对测试很重要。",
        "unit_or_basis": "Categorical",
        "unit_or_basis_zh": "分类",
        "interpretation_up": None,
        "interpretation_down": None,
        "interpretation_neutral": None,
        "caveats_en": [],
        "caveats_zh": [],
        "owner_ref": "aibrief.html",
        "public_source_refs": [],
        "related_ids": [],
        "authority_ceiling": "reference_only",
        "status": "active",
    }
    entry.update(overrides)
    return entry


def _registry(*entries) -> dict:
    return {"schema": "mastermind.market_reference/v1", "entries": list(entries)}


def _indicator_entry(**overrides) -> dict:
    base = _base_entry(
        id="sample-indicator",
        kind="indicator",
        family="regime",
        caveats_en=["One caveat."],
        caveats_zh=["一条注意事项。"],
    )
    base.update(overrides)
    return base


def _errors(exc: RegistryError) -> str:
    return "; ".join(exc.errors)


# ---------------------------------------------------------------------------
# 1 · one red-fixture per validation rule
# ---------------------------------------------------------------------------

def test_unknown_owner_ref_fails_closed():
    reg = _registry(_base_entry(owner_ref="not-a-real-page.html#nope"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "unknown owner page" in _errors(exc.value)


def test_unknown_owner_anchor_fails_closed():
    reg = _registry(_base_entry(owner_ref="macro.html#not-a-real-anchor"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "unknown owner anchor" in _errors(exc.value)


def test_duplicate_alias_fails_closed():
    reg = _registry(
        _base_entry(id="term-one", aliases_en=["shared alias"]),
        _base_entry(id="term-two", aliases_en=["Shared Alias"]),  # casefold+strip collision
    )
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "duplicates an alias already used" in _errors(exc.value)


def test_superseded_by_cycle_fails_closed():
    reg = _registry(
        _base_entry(id="term-a", status="deprecated", superseded_by="term-b"),
        _base_entry(id="term-b", status="deprecated", superseded_by="term-a"),
    )
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "superseded_by cycle" in _errors(exc.value)


def test_unsafe_source_url_fails_closed():
    reg = _registry(_base_entry(public_source_refs=["https://evil.example.com/not-allowlisted"]))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "not on the allowlist" in _errors(exc.value)


def test_unsafe_source_scheme_fails_closed():
    reg = _registry(_base_entry(public_source_refs=["http://fred.stlouisfed.org"]))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "not on the allowlist" in _errors(exc.value)


def test_missing_caveats_on_indicator_fails_closed():
    reg = _registry(_indicator_entry(caveats_en=[], caveats_zh=[]))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "requires a non-empty caveats_en" in _errors(exc.value)


def test_missing_language_fails_closed():
    reg = _registry(_base_entry(label_zh=""))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "label_en and label_zh must both be present" in _errors(exc.value)


def test_duplicate_id_fails_closed():
    reg = _registry(_base_entry(id="dupe-id"), _base_entry(id="dupe-id"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "duplicate id" in _errors(exc.value)


def test_unknown_related_id_fails_closed():
    reg = _registry(_base_entry(related_ids=["ghost-entry"]))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "references unknown id" in _errors(exc.value)


# --- M6: the 9 basic-shape red fixtures the review found missing ----------

def test_schema_mismatch_fails_closed():
    reg = _registry(_base_entry())
    reg["schema"] = "not-the-right-schema/v1"
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "schema must be" in _errors(exc.value)


def test_empty_entries_fails_closed():
    with pytest.raises(RegistryError) as exc:
        validate({"schema": "mastermind.market_reference/v1", "entries": []})
    assert "entries must be a non-empty list" in _errors(exc.value)


def test_invalid_kind_fails_closed():
    reg = _registry(_base_entry(kind="not-a-real-kind"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "kind must be one of" in _errors(exc.value)


def test_invalid_family_fails_closed():
    reg = _registry(_base_entry(family="not-a-real-family"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "family must be one of" in _errors(exc.value)


def test_invalid_authority_ceiling_fails_closed():
    reg = _registry(_base_entry(authority_ceiling="advisory"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "authority_ceiling must be 'reference_only'" in _errors(exc.value)


def test_invalid_status_fails_closed():
    reg = _registry(_base_entry(status="archived"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "status must be one of" in _errors(exc.value)


def test_non_kebab_id_fails_closed():
    reg = _registry(_base_entry(id="Not_Kebab Case!"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "id must be a non-empty kebab-case slug" in _errors(exc.value)


def test_aliases_presence_parity_fails_closed():
    """aliases_en present without aliases_zh (or vice versa) fails closed —
    both must be present when either is, even if one is an empty list."""
    reg = _registry(_base_entry(aliases_en=["only-english-alias"]))
    del reg["entries"][0]["aliases_zh"]
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "aliases_en/aliases_zh must both be present" in _errors(exc.value)


def test_caveats_length_mismatch_fails_closed():
    reg = _registry(_indicator_entry(
        caveats_en=["one caveat", "two caveats"],
        caveats_zh=["一条注意事项"],
    ))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "caveats_en and caveats_zh must have matching length" in _errors(exc.value)


# --- M6: 3 new rules, each with its own red fixture ------------------------

def test_superseded_by_unknown_id_fails_closed():
    reg = _registry(_base_entry(status="deprecated", superseded_by="ghost-entry"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "superseded_by references unknown id" in _errors(exc.value)


def test_deprecated_without_superseded_by_fails_closed():
    reg = _registry(_base_entry(status="deprecated"))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "status:deprecated requires a superseded_by" in _errors(exc.value)


def test_anchor_liveness_fails_closed_on_display_none_id(tmp_path):
    """B1: the durable anchor-liveness rule. A synthetic site/<page>.html with a
    body.<classes> #<id>{display:none} rule matching the page's own rendered
    body class must be rejected — this is the exact selector shape every real
    anchor-hiding bug in this codebase used (mx4-grid / page-stocks toggles)."""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "hiddenpage.html").write_text(
        '<html><body class="page-macro mx4-grid">'
        '<style>body.page-macro.mx4-grid #hidden-thing{display:none!important;}</style>'
        '<div id="hidden-thing">content</div>'
        "</body></html>",
        encoding="utf-8",
    )
    is_live, note = check_anchor_liveness(tmp_path, "hiddenpage.html", "hidden-thing")
    assert is_live is False
    assert "display:none" in note or "visibility:hidden" in note


def test_anchor_liveness_fails_closed_on_host_class_hide_in_linked_css(tmp_path):
    """R1 widening: the id's own element carries a class whose pure-class rule
    (in a LINKED local stylesheet, behind a CSS comment, with a ?v= cache
    buster) hides it — the .mx5-popover/.mx5-dlg shape behind 11 of the 16
    originally-broken entries, in the exact serving shape of site/macro.html
    (zero inline styles, external hashed CSS)."""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "pop.css").write_text(
        "/* Popover panel */\n.pop-panel{display:none;position:absolute}",
        encoding="utf-8",
    )
    (site_dir / "poppage.html").write_text(
        '<html><head><link rel="stylesheet" href="pop.css?v=abc123"></head>'
        '<body class="page-x">'
        '<div class="pop-panel" id="pop-thing">content</div>'
        "</body></html>",
        encoding="utf-8",
    )
    is_live, note = check_anchor_liveness(tmp_path, "poppage.html", "pop-thing")
    assert is_live is False
    assert "own element is hidden" in note


def test_anchor_liveness_fails_closed_on_body_gated_hide_in_linked_css(tmp_path):
    """R1 widening: the body-gated shape must also be found when the rule
    lives in a linked stylesheet rather than an inline <style> block (real
    rendered pages here carry zero inline styles)."""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "page.css").write_text(
        "body.page-y #tray-thing{visibility:hidden}",
        encoding="utf-8",
    )
    (site_dir / "traypage.html").write_text(
        '<html><head><link rel="stylesheet" href="page.css"></head>'
        '<body class="page-y"><div id="tray-thing">content</div></body></html>',
        encoding="utf-8",
    )
    is_live, note = check_anchor_liveness(tmp_path, "traypage.html", "tray-thing")
    assert is_live is False
    assert "visibility:hidden" in note or "display:none" in note


def test_anchor_liveness_accepts_a_visible_id(tmp_path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "visiblepage.html").write_text(
        '<html><body class="page-macro mx4-grid">'
        '<style>body.page-macro.mx4-grid #hidden-thing{display:none!important;}</style>'
        '<div id="visible-thing">content</div>'
        "</body></html>",
        encoding="utf-8",
    )
    is_live, note = check_anchor_liveness(tmp_path, "visiblepage.html", "visible-thing")
    assert is_live is True


def test_anchor_liveness_skips_when_site_page_absent(tmp_path):
    """Fail-open: this builder does not require every OTHER page's site
    output to exist (sparse checkouts, pages this builder does not produce)."""
    is_live, note = check_anchor_liveness(tmp_path, "never-built.html", "whatever")
    assert is_live is True
    assert "not built in this checkout" in note


def test_anchor_liveness_wired_into_validate_fails_closed(tmp_path):
    """End-to-end: validate() itself rejects a KNOWN_OWNER_PAGES anchor that
    resolves to a display:none-gated id in the committed site output."""
    from scripts import build_market_reference as bmr

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "macro.html").write_text(
        '<html><body class="page-macro mx4-grid">'
        '<style>body.page-macro.mx4-grid #regime-radar-decoy{display:none!important;}</style>'
        '<div id="regime-radar-decoy">content</div>'
        "</body></html>",
        encoding="utf-8",
    )
    # temporarily widen the allowlist so this fixture's fragment is "known"
    # without touching the real KNOWN_OWNER_PAGES for every other test
    old = bmr.KNOWN_OWNER_PAGES["macro.html"]
    bmr.KNOWN_OWNER_PAGES["macro.html"] = old | {"regime-radar-decoy"}
    try:
        reg = _registry(_base_entry(owner_ref="macro.html#regime-radar-decoy"))
        with pytest.raises(RegistryError) as exc:
            validate(reg, repo_root=tmp_path)
        assert "not a live/visible anchor" in _errors(exc.value)
    finally:
        bmr.KNOWN_OWNER_PAGES["macro.html"] = old


def test_explicit_null_interpretation_is_accepted_same_as_omitted():
    """Contract note: explicit `null` interpretation values are equivalent to
    omitted — the validator must accept both without complaint (and, since a
    null value has nothing to translate, it needs no `_zh` sibling either)."""
    reg = _registry(_base_entry(interpretation_up=None, interpretation_down=None,
                                 interpretation_neutral=None))
    entries = validate(reg)  # must not raise
    assert len(entries) == 1


def test_missing_zh_for_present_unit_or_basis_fails_closed():
    """MOR-1 ZH supplement rule: once a field is present, its `_zh` sibling is
    required — the old graceful t(en, zh='') render fallback is retired as a
    validation matter (it may still exist as template-level defensive code,
    but a registry that relies on it must no longer validate)."""
    reg = _registry(_base_entry(unit_or_basis="Percent", unit_or_basis_zh=None))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "unit_or_basis is present but unit_or_basis_zh is missing" in _errors(exc.value)


def test_missing_zh_for_present_interpretation_up_fails_closed():
    reg = _registry(_base_entry(interpretation_up="Rising."))
    with pytest.raises(RegistryError) as exc:
        validate(reg)
    assert "interpretation_up is present but interpretation_up_zh is missing" in _errors(exc.value)


def test_present_interpretation_with_zh_sibling_is_accepted():
    reg = _registry(_base_entry(
        interpretation_up="Rising.", interpretation_up_zh="上升。",
        interpretation_down="Falling.", interpretation_down_zh="下降。",
        interpretation_neutral="Flat.", interpretation_neutral_zh="持平。",
    ))
    entries = validate(reg)  # must not raise
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# 2 · happy-path build of the real committed registry
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_entries():
    raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return validate(raw)


def test_real_registry_validates_clean(real_entries):
    assert len(real_entries) == 34


def test_real_registry_zh_supplement_coverage(real_entries):
    """MOR-1 ZH supplement (2026-09-02): unit_or_basis_zh on all 34 entries;
    interpretation_up_zh/down_zh on the 26 entries that carry a directional
    up/down reading; interpretation_neutral_zh on all 34. Counts pinned so a
    future edit that silently drops a translation is caught here, not just by
    the (already fail-closed) validator."""
    has_basis_zh = sum(1 for e in real_entries if e.get("unit_or_basis_zh"))
    has_up_zh = sum(1 for e in real_entries if e.get("interpretation_up_zh"))
    has_down_zh = sum(1 for e in real_entries if e.get("interpretation_down_zh"))
    has_neutral_zh = sum(1 for e in real_entries if e.get("interpretation_neutral_zh"))
    assert has_basis_zh == 34
    assert has_up_zh == 26
    assert has_down_zh == 26
    assert has_neutral_zh == 34
    # and every _zh sibling implies a present _en value (no orphan translations)
    for e in real_entries:
        for base in ("unit_or_basis", "interpretation_up", "interpretation_down", "interpretation_neutral"):
            if e.get(f"{base}_zh"):
                assert e.get(base), f"{e['id']}: {base}_zh present without {base}"


def test_real_registry_builds_expected_families(real_entries):
    vm, families, letters = build_view_model(real_entries)
    assert len(vm) == 34
    assert sum(f["count"] for f in families) == 34
    assert [f["id"] for f in families] == [
        "regime", "liquidity", "volatility-stress", "rates-curve", "credit",
        "breadth-participation", "flows-positioning", "calendar-events",
        "doctrine", "cross-asset-basics",
    ]
    assert letters[0] == "A" and letters[-1] == "Z" and len(letters) == 26


def test_search_key_is_normalized():
    key = search_key({"label_en": "VIX", "label_zh": "", "id": "vix", "aliases_en": ["Fear Gauge!"]})
    assert " " not in key and "!" not in key
    assert key == key.lower()


def test_initial_of_handles_ascii_and_none():
    assert initial_of("VIX") == "V"
    assert initial_of("") == "#"


# ---------------------------------------------------------------------------
# 3 & 4 · rendered page: anchor stability + EN/ZH parity
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rendered_html(real_entries):
    entries_vm, families_vm, letters = build_view_model(real_entries)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    return env.get_template("reference.html.j2").render(
        entries=entries_vm, families=families_vm, letters=letters, generated_at="2026-09-02 00:00 UTC",
    )


def test_every_entry_id_is_a_real_anchor(real_entries, rendered_html):
    for e in real_entries:
        assert re.search(r'id="%s"' % re.escape(e["id"]), rendered_html), (
            f"entry id {e['id']!r} has no id=\"...\" anchor in the rendered page"
        )


def test_every_entry_shows_both_languages(real_entries, rendered_html):
    # One <article id="{id}" ...>...</article> block per entry — check each
    # block individually so a single missing l-zh span is attributable.
    for e in real_entries:
        m = re.search(
            r'<article class="rf-e" id="%s".*?</article>' % re.escape(e["id"]),
            rendered_html, re.DOTALL,
        )
        assert m, f"no <article> block found for entry {e['id']!r}"
        block = m.group(0)
        assert 'class="l-en"' in block, f"{e['id']!r}: no l-en span in rendered block"
        assert 'class="l-zh"' in block, f"{e['id']!r}: no l-zh span in rendered block"


def test_zh_supplement_fields_render_real_translation(real_entries, rendered_html):
    """Turns the old graceful t(en, zh='') fallback into an actual parity
    requirement: wherever the registry carries unit_or_basis / interpretation_*
    in English, the rendered block must show the REAL Chinese translation from
    the ZH supplement (HTML-escaped substring match — the template is
    Environment(autoescape=True), so a straight `"` inside a zh value like
    risk-radar's 'the "scare" scenarios' legitimately renders as `&#34;`) —
    not the English text doing double duty as the l-zh span's content."""
    from markupsafe import escape

    fields = ("unit_or_basis", "interpretation_up", "interpretation_down", "interpretation_neutral")
    checked = 0
    for e in real_entries:
        m = re.search(
            r'<article class="rf-e" id="%s".*?</article>' % re.escape(e["id"]),
            rendered_html, re.DOTALL,
        )
        assert m, f"no <article> block found for entry {e['id']!r}"
        block = m.group(0)
        for base in fields:
            zh_val = e.get(f"{base}_zh")
            if not zh_val:
                continue
            checked += 1
            expected = str(escape(zh_val))
            assert expected in block, (
                f"{e['id']!r}: {base}_zh value {zh_val!r} not found (escaped: {expected!r}) in "
                "rendered block (falling back to English would mean this assertion fails)"
            )
    assert checked == 34 + 26 + 26 + 34  # matches test_real_registry_zh_supplement_coverage


def test_no_unrendered_jinja_braces(rendered_html):
    assert "{{" not in rendered_html and "{%" not in rendered_html


def test_footer_authority_ceiling_present(rendered_html):
    assert "Reference only" in rendered_html
    assert "仅供参考" in rendered_html


def test_unknown_anchor_state_and_search_input_are_server_rendered(rendered_html):
    # Both are hidden-by-default progressive-enhancement affordances (contract
    # §7): they must exist in the server-rendered markup even though JS reveals
    # them, so a JS-disabled reader never sees a blank page or a broken filter.
    assert 'class="rf-miss mx-empty"' in rendered_html
    assert 'id="rf-q"' in rendered_html


# ---------------------------------------------------------------------------
# MOR-1 route-semantic evidence (issue #6782 / PR #6792 review #5099458870)
# Hosted here so contract-delta sees an already-wired suite; do not add a
# new pytest file or expand .github/ci/**.
# ---------------------------------------------------------------------------

from scripts import capture_page_evidence as cpe  # noqa: E402
from scripts.market_reference_route_evidence import (  # noqa: E402
    EVIDENCE_DIR_REL,
    OWNED_SOURCE_PATHS,
    ROUTE_CASES,
    assert_historical_overclaim_is_red,
    derive_local_assets,
    expected_query_entry_ids,
    mor1_capture_rows,
    parse_route,
    resolve_probe_queries,
    validate_manifest_route_matrix,
)

MANIFEST_PATH = REPO / EVIDENCE_DIR_REL / "manifest.json"

HISTORICAL_OVERCLAIM = {
    "schema": "mastermind.p0_evidence.v2",
    "tool": {"version": "1.0.0"},
    "pages": [
        {
            "page_id": "reference.html",
            "route": "reference.html",
            "states": [
                {
                    "viewport": vp,
                    "locale": loc,
                    "theme": th,
                    "access": "anonymous",
                    "force_state": None,
                    "captured": True,
                    "file": "deadbeef.png",
                    "sha256": "aa" * 32,
                    "bytes": 1,
                    "width": 1,
                    "height": 1,
                    "applied_theme": th,
                    "applied_locale": loc,
                }
                for vp in ("desktop", "mobile")
                for loc in ("en", "zh")
                for th in ("dark", "light")
            ],
        }
    ],
    "excluded": [
        {"route": "reference.html#vix", "reason": "historical omission"},
        {"route": "reference.html#not-a-real-entry", "reason": "historical omission"},
        {"route": "reference.html?q=curve", "reason": "historical omission"},
    ],
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


PROBES = resolve_probe_queries(REPO)
FULL_IDS = list(PROBES["full_ids"])
FULL_TOTAL = len(FULL_IDS)
_COMMITTED = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
BASE = _COMMITTED["candidate_binding"]["serve_root"]


def _committed_manifest() -> dict:
    return copy.deepcopy(_COMMITTED)


def _live_binding() -> dict:
    """The REAL binding from the committed packet.

    Synthetic matrix fixtures reuse it verbatim so they exercise route/cell
    semantics against an authentic subject identity, and so no test can pass by
    inventing a binding the verifier would never see in production.
    """

    return copy.deepcopy(_committed_manifest()["candidate_binding"])


def _case_ids(case: dict) -> list:
    want_q = case["expect"].get("query_q")
    return expected_query_entry_ids(want_q, repo_root=REPO) if want_q else list(FULL_IDS)


def _step(
    name: str,
    *,
    path: str,
    q,
    frag: str,
    inp: str,
    ids: list,
    denominator=FULL_TOTAL,
    numerator=None,
) -> dict:
    search = f"?q={q}" if q else ""
    return {
        "step": name,
        "href": f"{BASE}{path}{search}{frag}",
        "pathname": path,
        "search": search,
        "hash": frag,
        "url_q": q,
        "input": inp,
        "visible_result_count": len(ids),
        "visible_entry_ids": list(ids),
        "count_label_numerator": len(ids) if numerator is None else numerator,
        "count_label_denominator": denominator,
        "miss_visible": False,
        "selected_id": None,
    }


def _ok_journey(case: dict) -> dict:
    path, want_q, frag = parse_route(case["route"])
    expect = case["expect"]
    case_ids = _case_ids(case)
    inp = want_q or ""

    initial = _step("initial", path=path, q=want_q, frag=frag, inp=inp, ids=case_ids)
    # After change -> empty_probe -> clear the page has dismissed the open entry
    # and cleared location.hash (close-affordance replaceState in the template),
    # so every post-interaction step carries an empty hash. `back` is held to
    # exactly this state.
    pre_push = _step("pre_push", path=path, q=want_q, frag="", inp=inp, ids=case_ids)
    share_href = f"{BASE}{path}{'?q=' + want_q if want_q else ''}{frag}"
    return {
        "axes": {
            "viewport": "desktop",
            "viewport_width": 1440,
            "viewport_height": 900,
            "locale": "en",
            "theme": "dark",
            "access": "anonymous",
            "force_state": None,
        },
        "applied": {
            "locale": "en",
            "theme": "dark",
            "viewport_width": 1440,
            "viewport_height": 900,
        },
        "probes": {
            "change_query": PROBES["change_query"],
            "forward_query": PROBES["forward_query"],
            "empty_query": PROBES["empty_query"],
        },
        "console_errors": [],
        "failed_responses": [],
        "steps": {
            "initial": initial,
            "change": _step(
                "change",
                path=path,
                q=PROBES["change_query"],
                frag="",
                inp=PROBES["change_query"],
                ids=list(PROBES["change_ids"]),
            ),
            "empty_probe": _step(
                "empty_probe",
                path=path,
                q=PROBES["empty_query"],
                frag="",
                inp=PROBES["empty_query"],
                ids=[],
            ),
            "clear": _step("clear", path=path, q=None, frag="", inp="", ids=list(FULL_IDS)),
            "pre_push": pre_push,
            "pushed": _step(
                "pushed",
                path=path,
                q=PROBES["forward_query"],
                frag="",
                inp=inp,
                ids=case_ids,
            ),
            "back": dict(pre_push, step="back", performed=True),
            "forward": dict(
                _step(
                    "forward",
                    path=path,
                    q=PROBES["forward_query"],
                    frag="",
                    inp=PROBES["forward_query"],
                    ids=list(PROBES["forward_ids"]),
                ),
                performed=True,
            ),
            "reload": _step("reload", path=path, q=want_q, frag=frag, inp=inp, ids=case_ids),
            "share": {
                "step": "share",
                "href": share_href,
                "final_href": share_href,
                "matches_final": True,
                "reopened": dict(
                    _step(
                        "reopened",
                        path=path,
                        q=want_q,
                        frag=frag,
                        inp=inp,
                        ids=case_ids,
                    ),
                    final_href=share_href,
                    selected_id=expect.get("selected_id"),
                    miss_visible=bool(expect.get("miss_visible")),
                    focused_element_id=(
                        expect.get("selected_id") if expect.get("require_focus") else None
                    ),
                    focused_visible=bool(expect.get("require_focus")),
                    target_below_fixed_ui=True if expect.get("require_focus") else None,
                    console_errors=[],
                    failed_responses=[],
                ),
            },
        },
    }


def _route_state_for(case: dict, *, locale: str = "en") -> dict:
    expect = case["expect"]
    path, want_q, frag = parse_route(case["route"])
    ids = _case_ids(case)
    count = len(ids)
    selected = expect.get("selected_id")
    focused = selected if expect.get("require_focus") else None
    label = f"显示 {count} 条" if locale == "zh" else f"{count} of {FULL_TOTAL} entries"
    search = f"?q={want_q}" if want_q else ""
    return {
        "requested_url": f"{BASE}{path}{search}{frag}",
        "final_url": f"{BASE}{path}{search}{frag}",
        "pathname": path,
        "search": search,
        "hash": frag,
        "query_q": want_q,
        "rf_q_value": want_q or "",
        "miss_visible": bool(expect.get("miss_visible")),
        "miss_q_text": (frag.lstrip("#") if expect.get("miss_visible") else None),
        "selected_id": selected,
        "visible_result_count": count,
        "visible_entry_ids": list(ids),
        "count_label_visible": True,
        "count_label_text": label,
        "count_label_values": [count, FULL_TOTAL],
        "count_label_numerator": count,
        "count_label_denominator": FULL_TOTAL,
        "focused_element_id": focused,
        "focused_visible": bool(expect.get("require_focus")),
        "target_below_fixed_ui": True if expect.get("require_focus") else None,
    }


def _rest_states_for(route_state: dict, *, page_index: int) -> list:
    """Eight cells, each owning a UNIQUE screenshot file and digest."""

    states = []
    cell_index = 0
    for viewport in ("desktop", "mobile"):
        for locale in ("en", "zh"):
            for theme in ("dark", "light"):
                rs = copy.deepcopy(route_state)
                count = rs.get("visible_result_count") or 0
                rs["count_label_text"] = (
                    f"显示 {count} 条" if locale == "zh" else f"{count} of {FULL_TOTAL} entries"
                )
                sha = hashlib.sha256(f"mor1:{page_index}:{cell_index}".encode()).hexdigest()
                states.append(
                    {
                        "viewport": viewport,
                        "locale": locale,
                        "theme": theme,
                        "access": "anonymous",
                        "force_state": None,
                        "captured": True,
                        "file": f"{sha[:16]}.png",
                        "sha256": sha,
                        "bytes": 10 + cell_index,
                        "width": 10,
                        "height": 10,
                        "applied_theme": theme,
                        "applied_locale": locale,
                        "console_errors": [],
                        "failed_responses": [],
                        "route_state": rs,
                    }
                )
                cell_index += 1
    return states


def _green_manifest() -> dict:
    pages = []
    for i, case in enumerate(ROUTE_CASES):
        pages.append(
            {
                "page_id": case["page_id"],
                "route": case["route"],
                "console_errors": [],
                "failed_responses": [],
                "route_journey": _ok_journey(case),
                "states": _rest_states_for(_route_state_for(case), page_index=i),
            }
        )
    return {
        "schema": "mastermind.p0_evidence.v2",
        "tool": {"version": cpe.TOOL_VERSION, "module_ref": "scripts/capture_page_evidence.py"},
        "candidate_binding": _live_binding(),
        "target": {
            "resolved_sha_or_none": _git("rev-parse", "HEAD"),
            "resolved_sha_source": "verified worktree HEAD",
        },
        "pages": pages,
        "excluded": [],
    }


def _page(manifest: dict, route: str) -> dict:
    return next(p for p in manifest["pages"] if p["route"] == route)


def _red(manifest: dict, **kw) -> str:
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO, **kw)
    assert errors, "mutation unexpectedly validated"
    return "\n".join(errors)


# --- baseline --------------------------------------------------------------


def test_green_matrix_passes():
    assert validate_manifest_route_matrix(_green_manifest(), repo_root=REPO) == []


def test_historical_committed_manifest_is_red_overclaim():
    assert_historical_overclaim_is_red(HISTORICAL_OVERCLAIM)


def test_committed_mor1_packet_satisfies_route_contract():
    assert MANIFEST_PATH.is_file()
    errors = validate_manifest_route_matrix(
        _committed_manifest(), evidence_dir=MANIFEST_PATH.parent, repo_root=REPO
    )
    assert errors == [], "\n".join(errors)


def test_mor1_capture_rows_cover_four_cases():
    rows = mor1_capture_rows()
    assert [r["capture_route"] for r in rows] == [c["route"] for c in ROUTE_CASES]
    assert len(rows) == 4


def test_template_writes_query_to_url_and_focuses_valid_anchor():
    text = (REPO / "templates" / "reference.html.j2").read_text(encoding="utf-8")
    assert "READ, never written" not in text
    assert "function syncQueryToUrl" in text
    assert "popstate" in text
    assert 'searchParams.set("q"' in text or "searchParams.set('q'" in text
    assert "focusEl.focus" in text or ".focus(" in text
    assert "scrollIntoView" in text


def test_direct_checker_bootstrap_importable():
    src = (REPO / "scripts" / "check_market_reference_route_evidence.py").read_text(
        encoding="utf-8"
    )
    assert "sys.path.insert" in src


# --- probe design ----------------------------------------------------------


def test_journey_probes_are_registry_derived_and_non_empty():
    """A zero-result probe cannot tell a working filter from one that hides all."""

    assert PROBES["change_ids"], "change probe must select real entries"
    assert PROBES["forward_ids"], "forward probe must select real entries"
    assert len(PROBES["change_ids"]) < FULL_TOTAL
    assert len(PROBES["forward_ids"]) < FULL_TOTAL
    assert PROBES["change_ids"] != PROBES["forward_ids"]
    assert PROBES["empty_ids"] == []


def test_every_nonempty_typed_query_hiding_all_rows_is_red():
    """The mutant the retired journeyprobe/navprobe pair could not catch."""

    manifest = _green_manifest()
    for page in manifest["pages"]:
        steps = page["route_journey"]["steps"]
        for name in ("change", "forward"):
            steps[name]["visible_entry_ids"] = []
            steps[name]["visible_result_count"] = 0
            steps[name]["count_label_numerator"] = 0
    joined = _red(manifest)
    assert "journey change" in joined or "journey forward" in joined


# --- subject / evidence identity ------------------------------------------


def test_forged_zero_source_commit_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["source_commit"] = "0" * 40
    joined = _red(manifest)
    assert "forged" in joined or "not a commit" in joined or "not a 40-char" in joined


def test_stale_valid_ancestor_subject_is_red():
    """A real older ancestor with a matching tree is still not the subject.

    All-zero is insufficient: this mutation is internally consistent — real
    commit, real tree — and is caught only because owned non-evidence paths
    moved between it and HEAD.
    """

    manifest = _green_manifest()
    declared = manifest["candidate_binding"]["source_commit"]
    ancestors = _git("rev-list", "--max-count=40", f"{declared}~1").splitlines()
    stale = None
    for candidate in ancestors:
        changed = _git(
            "diff", "--name-only", candidate, "HEAD", "--", *OWNED_SOURCE_PATHS
        )
        if changed.strip():
            stale = candidate
            break
    assert stale, "no ancestor differing in an owned path; cannot exercise this mutant"
    manifest["candidate_binding"]["source_commit"] = stale
    manifest["candidate_binding"]["source_tree"] = _git("rev-parse", f"{stale}^{{tree}}")
    joined = _red(manifest)
    assert "non-evidence path" in joined or "subject-commit blob" in joined


def test_dirty_worktree_capture_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["worktree_clean"] = False
    manifest["candidate_binding"]["worktree_status_tracked"] = [" M scripts/thing.py"]
    joined = _red(manifest)
    assert "dirty worktree" in joined or "worktree_clean" in joined


def test_current_disk_hash_standing_in_for_a_blob_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["site_reference_sha256"] = "cd" * 32
    joined = _red(manifest)
    assert "subject-commit blob" in joined


def test_render_nonzero_returncode_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"]["returncode"] = 1
    joined = _red(manifest)
    assert "returncode" in joined


def test_render_invocation_wrong_cwd_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"]["cwd"] = "/tmp/elsewhere"
    joined = _red(manifest)
    assert "cwd" in joined


def test_non_loopback_serve_root_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["serve_root"] = "https://www.mastermind-x.com"
    joined = _red(manifest)
    assert "serve_root" in joined


def test_site_dir_outside_the_repo_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["site_dir"] = "/tmp/site"
    joined = _red(manifest)
    assert "site_dir" in joined


def test_omitted_local_asset_is_red():
    manifest = _green_manifest()
    assets = manifest["candidate_binding"]["local_asset_digests"]
    dropped = sorted(assets)[0]
    assets.pop(dropped)
    joined = _red(manifest)
    assert "omits assets" in joined


def test_extra_local_asset_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["local_asset_digests"]["site/not-loaded.js"] = "ee" * 32
    joined = _red(manifest)
    assert "does not load" in joined


def test_local_assets_are_derived_from_the_rendered_page():
    html = (REPO / "site" / "reference.html").read_text(encoding="utf-8")
    derived = derive_local_assets(html)
    assert derived, "reference.html must declare local script/link dependencies"
    assert all(rel.startswith("site/") for rel in derived)
    assert not any(rel.startswith(("http", "//")) for rel in derived)


def test_nonempty_excluded_is_red():
    manifest = _green_manifest()
    manifest["excluded"] = [{"route": "reference.html?q=other", "reason": "nope"}]
    joined = _red(manifest)
    assert "excluded" in joined


def test_missing_candidate_binding_is_red():
    manifest = _green_manifest()
    manifest.pop("candidate_binding")
    joined = _red(manifest)
    assert "candidate_binding" in joined


def test_old_tool_version_is_red():
    manifest = _green_manifest()
    manifest["tool"]["version"] = "1.4.0"
    joined = _red(manifest)
    assert "tool version" in joined


# --- closed 32-cell world --------------------------------------------------


def test_missing_route_case_is_red():
    manifest = _green_manifest()
    manifest["pages"] = [p for p in manifest["pages"] if p["route"] != "reference.html#vix"]
    joined = _red(manifest)
    assert "valid_anchor" in joined or "reference.html#vix" in joined


def test_arbitrary_extra_page_is_red():
    manifest = _green_manifest()
    manifest["pages"].append(
        {
            "page_id": "other_page",
            "route": "other.html",
            "console_errors": [],
            "failed_responses": [],
            "route_journey": _ok_journey(ROUTE_CASES[0]),
            "states": [],
        }
    )
    joined = _red(manifest)
    assert "other_page" in joined or "unexpected extra page" in joined


def test_duplicate_page_id_is_red():
    manifest = _green_manifest()
    clone = copy.deepcopy(manifest["pages"][0])
    clone["route"] = "reference.html#dup"
    manifest["pages"].append(clone)
    joined = _red(manifest)
    assert "duplicate page_id" in joined


def test_extra_tablet_rest_cell_is_red():
    manifest = _green_manifest()
    page = manifest["pages"][0]
    extra = copy.deepcopy(page["states"][0])
    extra["viewport"] = "tablet"
    extra["file"] = "tablet-extra.png"
    extra["sha256"] = "ab" * 32
    page["states"].append(extra)
    joined = _red(manifest)
    assert "tablet" in joined or "extra REST" in joined


def test_extra_forced_state_cell_is_red():
    """Previously skipped silently by the REST-key helper, so it rode along."""

    manifest = _green_manifest()
    page = manifest["pages"][0]
    extra = copy.deepcopy(page["states"][0])
    extra["force_state"] = "empty"
    extra["file"] = "forced-extra.png"
    extra["sha256"] = "ac" * 32
    page["states"].append(extra)
    joined = _red(manifest)
    assert "force_state" in joined


def test_substituted_authenticated_access_cell_is_red():
    manifest = _green_manifest()
    page = manifest["pages"][0]
    page["states"][0]["access"] = "authenticated"
    joined = _red(manifest)
    assert "access" in joined


def test_duplicate_logical_cell_is_red():
    manifest = _green_manifest()
    page = manifest["pages"][0]
    dupe = copy.deepcopy(page["states"][0])
    dupe["file"] = "dupe-cell.png"
    dupe["sha256"] = "ad" * 32
    page["states"].append(dupe)
    joined = _red(manifest)
    assert "duplicate logical cell" in joined


# --- screenshot identity ---------------------------------------------------


def test_relabel_default_digest_as_vix_is_red():
    manifest = _green_manifest()
    default = _page(manifest, "reference.html")
    vix = _page(manifest, "reference.html#vix")
    stolen = default["states"][0]["sha256"]
    for state in vix["states"]:
        state["sha256"] = stolen
    joined = _red(manifest)
    assert "distinct logical" in joined


def test_png_reuse_between_themes_inside_one_route_is_red():
    """One image may not stand for dark AND light of the same route."""

    manifest = _green_manifest()
    page = manifest["pages"][0]
    page["states"][1]["sha256"] = page["states"][0]["sha256"]
    page["states"][1]["file"] = page["states"][0]["file"]
    joined = _red(manifest)
    assert "distinct logical" in joined


def test_png_byte_mutate_is_red(tmp_path: Path):
    manifest = _green_manifest()
    for page in manifest["pages"]:
        for state in page["states"]:
            (tmp_path / state["file"]).write_bytes(b"not-a-png-but-bytes")
    joined = _red(manifest, evidence_dir=tmp_path)
    assert "PNG" in joined or "hash" in joined or "bytes" in joined


def test_unexpected_extra_png_is_red(tmp_path: Path):
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )
    manifest = _green_manifest()
    for page in manifest["pages"]:
        for state in page["states"]:
            (tmp_path / state["file"]).write_bytes(png)
    (tmp_path / "orphan_extra.png").write_bytes(png)
    joined = _red(manifest, evidence_dir=tmp_path)
    assert "unexpected PNG extras" in joined


# --- route state semantics -------------------------------------------------


def test_query_route_without_query_state_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["query_q"] = None
        state["route_state"]["visible_result_count"] = 0
        state["route_state"]["visible_entry_ids"] = []
    joined = _red(manifest)
    assert "query_q" in joined or "visible_result_count" in joined


def test_unknown_anchor_without_miss_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html#not-a-real-entry")
    for state in page["states"]:
        state["route_state"]["miss_visible"] = False
    joined = _red(manifest)
    assert "miss_visible" in joined


def test_vix_without_focus_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html#vix")
    for state in page["states"]:
        state["route_state"]["focused_visible"] = False
        state["route_state"]["target_below_fixed_ui"] = False
    joined = _red(manifest)
    assert "focused_visible" in joined or "target_below_fixed_ui" in joined


def test_missing_vix_focus_identity_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html#vix")
    for state in page["states"]:
        state["route_state"]["focused_element_id"] = None
    joined = _red(manifest)
    assert "focused_element_id" in joined and "vix" in joined


def test_fabricated_curve_full_library_ids_are_red():
    manifest = _green_manifest()
    fake_ids = [f"fake-{i}" for i in range(FULL_TOTAL)]
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        rs = state["route_state"]
        rs["visible_result_count"] = FULL_TOTAL
        rs["visible_entry_ids"] = list(fake_ids)
        rs["count_label_text"] = f"{FULL_TOTAL} of {FULL_TOTAL} entries"
        rs["count_label_numerator"] = FULL_TOTAL
    joined = _red(manifest)
    assert "visible_entry_ids" in joined or "visible_result_count" in joined


def test_duplicate_visible_ids_with_matching_count_is_red():
    """``[a, b, a]`` with count=2 satisfied the retired set-equality check."""

    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    ids = _case_ids(ROUTE_CASES[3])
    assert len(ids) >= 2
    for state in page["states"]:
        rs = state["route_state"]
        rs["visible_entry_ids"] = [ids[0], ids[1], ids[0]]
        rs["visible_result_count"] = len(ids)
    joined = _red(manifest)
    assert "duplicates" in joined


def test_out_of_order_visible_ids_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        rs = state["route_state"]
        rs["visible_entry_ids"] = list(reversed(rs["visible_entry_ids"]))
    joined = _red(manifest)
    assert "ordered" in joined


def test_wrong_count_label_denominator_is_red():
    """``3 of 99`` beside three visible rows used to pass."""

    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["count_label_denominator"] = 99
        state["route_state"]["count_label_text"] = "2 of 99 entries"
    joined = _red(manifest)
    assert "denominator" in joined


def test_wrong_count_label_numerator_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["count_label_numerator"] = 7
    joined = _red(manifest)
    assert "numerator" in joined


def test_missing_per_cell_console_receipt_is_red():
    manifest = _green_manifest()
    for state in manifest["pages"][0]["states"]:
        state.pop("console_errors")
    joined = _red(manifest)
    assert "per-cell console_errors" in joined


def test_console_error_confined_to_one_rest_cell_is_red():
    """A page-level aggregate cannot prove an individual cell was clean."""

    manifest = _green_manifest()
    manifest["pages"][0]["states"][3]["console_errors"] = [
        {"text": "TypeError: x is not a function", "source_url": "http://127.0.0.1:9/theme.js"}
    ]
    joined = _red(manifest)
    assert "console_errors not empty" in joined


def test_failed_response_confined_to_one_rest_cell_is_red():
    manifest = _green_manifest()
    manifest["pages"][1]["states"][5]["failed_responses"] = [
        {"url": "http://127.0.0.1:9/live_config.js", "status": 500}
    ]
    joined = _red(manifest)
    assert "failed_responses not empty" in joined


# --- journey ---------------------------------------------------------------


def test_missing_journey_is_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        page.pop("route_journey", None)
    joined = _red(manifest)
    assert "route_journey" in joined


def test_legacy_plural_route_journeys_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journeys"] = {"change": {"ok": True}}
    joined = _red(manifest)
    assert "plural route_journeys is retired" in joined


def test_journey_copied_into_every_cell_is_red():
    """One default-context journey stamped into all eight cells is a false claim."""

    manifest = _green_manifest()
    page = manifest["pages"][0]
    for state in page["states"]:
        state["route_state"]["journeys"] = copy.deepcopy(page["route_journey"]["steps"])
    joined = _red(manifest)
    assert "route_state.journeys is retired" in joined


def test_unscoped_journey_without_axes_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journey"].pop("axes")
    joined = _red(manifest)
    assert "unscoped journey" in joined


def test_journey_axes_not_matching_applied_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journey"]["applied"]["theme"] = "light"
    joined = _red(manifest)
    assert "applied theme" in joined


def test_forged_back_is_red():
    """Back must land on the exact pre-push route, not merely off the probe."""

    manifest = _green_manifest()
    for page in manifest["pages"]:
        back = page["route_journey"]["steps"]["back"]
        back["pathname"] = "/somewhere-else.html"
    joined = _red(manifest)
    assert "journey back route" in joined


def test_back_that_never_leaves_the_probe_is_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        steps = page["route_journey"]["steps"]
        steps["back"] = dict(steps["pushed"], step="back", performed=True)
    joined = _red(manifest)
    assert "journey back" in joined


def test_forward_that_does_not_rehydrate_the_input_is_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        page["route_journey"]["steps"]["forward"]["input"] = ""
    joined = _red(manifest)
    assert "did not rehydrate" in joined


def test_journey_console_error_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journey"]["console_errors"] = [
        {"text": "pageerror: boom", "source_url": None}
    ]
    joined = _red(manifest)
    assert "route_journey.console_errors not empty" in joined


def test_journey_failed_response_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journey"]["failed_responses"] = [
        {"url": "http://127.0.0.1:9/theme.css", "status": 404}
    ]
    joined = _red(manifest)
    assert "route_journey.failed_responses not empty" in joined


def test_missing_journey_listeners_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journey"].pop("console_errors")
    joined = _red(manifest)
    assert "journey failures would be invisible" in joined


def test_share_without_reopen_is_red():
    """``href == page.url`` proves only that a string equals itself."""

    manifest = _green_manifest()
    for page in manifest["pages"]:
        page["route_journey"]["steps"]["share"].pop("reopened")
    joined = _red(manifest)
    assert "share.reopened missing" in joined


def test_share_reopening_the_wrong_route_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    reopened = page["route_journey"]["steps"]["share"]["reopened"]
    reopened["url_q"] = None
    reopened["search"] = ""
    reopened["final_href"] = f"{BASE}/reference.html"
    joined = _red(manifest)
    assert "share.reopened" in joined


def test_share_reopen_with_console_errors_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journey"]["steps"]["share"]["reopened"]["console_errors"] = [
        {"text": "boom", "source_url": None}
    ]
    joined = _red(manifest)
    assert "share.reopened.console_errors not empty" in joined


def test_bogus_back_forward_share_receipts_are_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        steps = page["route_journey"]["steps"]
        steps["back"]["pathname"] = "/reference.html"
        steps["back"]["url_q"] = PROBES["forward_query"]
        steps["forward"]["url_q"] = None
        steps["share"]["href"] = "http://example.test/not-the-share-target"
    joined = _red(manifest)
    assert "journey back" in joined or "journey forward" in joined or "journey share" in joined


# --- review 5108611410: closed URL identity --------------------------------


def test_forged_requested_url_is_red():
    """`requested_url` was recorded and never checked."""

    manifest = _green_manifest()
    for state in manifest["pages"][0]["states"]:
        state["route_state"]["requested_url"] = f"{BASE}/reference.html?q=whatever#forged"
    joined = _red(manifest)
    assert "requested_url" in joined


def test_cross_origin_final_url_is_red():
    manifest = _green_manifest()
    for state in manifest["pages"][0]["states"]:
        state["route_state"]["final_url"] = "https://www.mastermind-x.com/reference.html"
    joined = _red(manifest)
    assert "cross-origin" in joined


def test_cross_origin_share_href_is_red():
    manifest = _green_manifest()
    share = manifest["pages"][0]["route_journey"]["steps"]["share"]
    share["href"] = "https://www.mastermind-x.com/reference.html"
    share["final_href"] = "https://www.mastermind-x.com/reference.html"
    joined = _red(manifest)
    assert "cross-origin" in joined


def test_extra_query_key_on_final_url_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["final_url"] = f"{BASE}/reference.html?q=curve&utm_source=x"
    joined = _red(manifest)
    assert "query" in joined


def test_duplicate_q_parameter_is_red():
    """`parse_qs(...)['q'][0]` silently ignored the second value."""

    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["final_url"] = f"{BASE}/reference.html?q=curve&q=regime"
    joined = _red(manifest)
    assert "query" in joined


def test_blank_query_on_default_route_is_red():
    """`?q=` on a route whose query must be ABSENT."""

    manifest = _green_manifest()
    page = _page(manifest, "reference.html")
    for state in page["states"]:
        state["route_state"]["final_url"] = f"{BASE}/reference.html?q="
        state["route_state"]["search"] = "?q="
    joined = _red(manifest)
    assert "query" in joined or "search field" in joined


def test_search_field_disagreeing_with_href_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["search"] = "?q=regime"
    joined = _red(manifest)
    assert "search field" in joined


# --- review 5108611410: unknown-anchor recovery slug -----------------------


def test_missing_recovery_slug_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html#not-a-real-entry")
    for state in page["states"]:
        state["route_state"]["miss_q_text"] = ""
    joined = _red(manifest)
    assert "miss_q_text" in joined


def test_wrong_recovery_slug_is_red():
    """A panel that appears while naming the wrong entry."""

    manifest = _green_manifest()
    page = _page(manifest, "reference.html#not-a-real-entry")
    for state in page["states"]:
        state["route_state"]["miss_q_text"] = "vix"
    joined = _red(manifest)
    assert "miss_q_text" in joined


def test_recovery_slug_on_a_non_miss_route_is_red():
    manifest = _green_manifest()
    for state in manifest["pages"][0]["states"]:
        state["route_state"]["miss_q_text"] = "not-a-real-entry"
    joined = _red(manifest)
    assert "miss_q_text" in joined


# --- review 5108611410: journey transition binding -------------------------


def test_stale_hash_on_change_step_is_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        step = page["route_journey"]["steps"]["change"]
        step["hash"] = "#stale"
        step["href"] = f"{BASE}/reference.html?q={PROBES['change_query']}#stale"
    joined = _red(manifest)
    assert "journey change" in joined


def test_empty_probe_carrying_a_real_query_is_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        step = page["route_journey"]["steps"]["empty_probe"]
        step["url_q"] = PROBES["change_query"]
        step["search"] = f"?q={PROBES['change_query']}"
        step["href"] = f"{BASE}/reference.html?q={PROBES['change_query']}"
    joined = _red(manifest)
    assert "journey empty_probe" in joined


def test_journey_step_fields_disagreeing_with_href_is_red():
    manifest = _green_manifest()
    manifest["pages"][0]["route_journey"]["steps"]["clear"]["pathname"] = "/elsewhere.html"
    joined = _red(manifest)
    assert "journey clear" in joined


# --- review 5108611410: frozen render invocation ---------------------------


def test_render_command_substitution_is_red():
    """`echo build_market_reference but do nothing` used to satisfy a substring test."""

    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"]["command"] = (
        "echo build_market_reference but do nothing"
    )
    joined = _red(manifest)
    assert "frozen" in joined


def test_render_argv_substitution_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"]["argv"] = ["/bin/false"]
    joined = _red(manifest)
    assert "argv" in joined


def test_render_argv_non_python_interpreter_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"]["argv"] = [
        "/bin/sh",
        "-m",
        "scripts.build_market_reference",
    ]
    joined = _red(manifest)
    assert "not a python interpreter" in joined


def test_render_argv_wrong_module_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"]["argv"] = [
        sys.executable,
        "-m",
        "scripts.build_something_else",
    ]
    joined = _red(manifest)
    assert "argv[1:]" in joined


# --- SOL build-identity addendum: deterministic clean-checkout replay -------


def test_builder_clock_is_an_explicit_input():
    """An implicit wall clock makes the artifact unreplayable by construction."""

    from scripts.build_market_reference import GENERATED_AT_ENV, resolve_generated_at

    import os as _os

    prev = _os.environ.get(GENERATED_AT_ENV)
    try:
        _os.environ[GENERATED_AT_ENV] = "2026-09-04 05:30 UTC"
        assert resolve_generated_at() == "2026-09-04 05:30 UTC"
        _os.environ[GENERATED_AT_ENV] = "2026-09-04T05:30:00Z"
        assert resolve_generated_at() == "2026-09-04 05:30 UTC"
        _os.environ.pop(GENERATED_AT_ENV)
        assert resolve_generated_at().endswith("UTC")
    finally:
        if prev is None:
            _os.environ.pop(GENERATED_AT_ENV, None)
        else:
            _os.environ[GENERATED_AT_ENV] = prev


def test_committed_artifact_replays_byte_identically():
    """The committed page must be rebuildable from the subject commit."""

    binding = _live_binding()
    errors = validate_manifest_route_matrix(_green_manifest(), repo_root=REPO)
    replay_errors = [e for e in errors if "replay" in e]
    assert replay_errors == [], "\n".join(replay_errors)
    assert binding["render_invocation"]["generated_at"]


def test_different_generated_at_fails_the_replay_is_red():
    """The named mutant: every declared digest is internally consistent, but the
    committed page was produced with a different clock."""

    manifest = _green_manifest()
    invocation = manifest["candidate_binding"]["render_invocation"]
    invocation["generated_at"] = "2001-01-01 00:00 UTC"
    invocation["env"] = {"MOR1_GENERATED_AT": "2001-01-01 00:00 UTC"}
    joined = _red(manifest)
    assert "replay does not reproduce" in joined


def test_missing_generated_at_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"].pop("generated_at")
    joined = _red(manifest)
    assert "generated_at missing" in joined


def test_env_not_recording_the_clock_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["render_invocation"]["env"] = {"MOR1_GENERATED_AT": "elsewhen"}
    joined = _red(manifest)
    assert "MOR1_GENERATED_AT" in joined


# --- SOL build-identity addendum: origin + complete query shape -------------


def test_foreign_origin_with_correct_path_query_hash_is_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["final_url"] = "https://evil.example/reference.html?q=curve"
    joined = _red(manifest)
    assert "cross-origin" in joined


def test_conflicting_repeated_q_values_are_red():
    manifest = _green_manifest()
    page = _page(manifest, "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["final_url"] = f"{BASE}/reference.html?q=curve&q=curve"
    joined = _red(manifest)
    assert "query" in joined


def test_share_round_trip_on_the_wrong_origin_is_red():
    """Correct path state, wrong host — that is not a round trip."""

    manifest = _green_manifest()
    share = manifest["pages"][0]["route_journey"]["steps"]["share"]
    share["final_href"] = "https://evil.example/reference.html"
    share["reopened"]["final_href"] = "https://evil.example/reference.html"
    joined = _red(manifest)
    assert "round-trip" in joined or "cross-origin" in joined
