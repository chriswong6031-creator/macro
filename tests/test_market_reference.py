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

from scripts.market_reference_route_evidence import (  # noqa: E402
    REQUIRED_RENDER_INPUTS,
    REQUIRED_SHARED_ASSETS,
    ROUTE_CASES,
    assert_historical_overclaim_is_red,
    expected_query_entry_ids,
    mor1_capture_rows,
    validate_manifest_route_matrix,
)

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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def _live_binding() -> dict:
    source_commit = _git("rev-parse", "HEAD")
    source_tree = _git("rev-parse", f"{source_commit}^{{tree}}")
    site_sha = _sha256_file(REPO / "site" / "reference.html")
    tool_ver = "1.4.0"
    return {
        "source_commit": source_commit,
        "source_tree": source_tree,
        "worktree": str(REPO),
        "site_reference_sha256": site_sha,
        "serve_root": "http://127.0.0.1:9",
        "capture_tool_version": tool_ver,
        "capture_tool_module_sha256": _sha256_file(REPO / "scripts" / "capture_page_evidence.py"),
        "render_invocation": {
            "command": "python -m scripts.build_market_reference",
            "argv": [sys.executable, "-m", "scripts.build_market_reference"],
            "input_digests": {rel: _sha256_file(REPO / rel) for rel in REQUIRED_RENDER_INPUTS},
            "output_digests": {"site/reference.html": site_sha},
        },
        "shared_asset_digests": {rel: _sha256_file(REPO / rel) for rel in REQUIRED_SHARED_ASSETS},
    }


def _ok_journeys(case: dict) -> dict:
    route = case["route"]
    want_q = case["expect"].get("query_q")
    want_hash = (case["expect"].get("hash") or "").lstrip("#")
    final = f"http://127.0.0.1:9/{route}"
    full_ids = expected_query_entry_ids(None, repo_root=REPO)
    probe_ids = expected_query_entry_ids("journeyprobe", repo_root=REPO)
    nav_ids = expected_query_entry_ids("navprobe", repo_root=REPO)
    case_ids = expected_query_entry_ids(want_q, repo_root=REPO) if want_q else full_ids
    back_q = want_q
    back_input = want_q or ""
    return {
        "change": {
            "ok": True,
            "url_q": "journeyprobe",
            "input": "journeyprobe",
            "visible_result_count": len(probe_ids),
            "visible_entry_ids": list(probe_ids),
        },
        "clear": {
            "ok": True,
            "url_q": None,
            "input": "",
            "visible_result_count": len(full_ids),
            "visible_entry_ids": list(full_ids),
        },
        "reload": {
            "ok": True,
            "post_href": final,
            "post_q": want_q,
            "post_hash": want_hash,
            "input_rehydrated": back_input,
            "visible_result_count": len(case_ids),
            "visible_entry_ids": list(case_ids),
        },
        "back": {
            "ok": True,
            "performed": True,
            "after_href": final,
            "href": final,
            "url_q": back_q,
            "input": back_input,
        },
        "forward": {
            "ok": True,
            "performed": True,
            "after_href": "http://127.0.0.1:9/reference.html?q=navprobe",
            "href": "http://127.0.0.1:9/reference.html?q=navprobe",
            "url_q": "navprobe",
            "input": "navprobe",
            "visible_result_count": len(nav_ids),
            "visible_entry_ids": list(nav_ids),
        },
        "share": {
            "ok": True,
            "href": final,
            "final_href": final,
            "matches_final": True,
        },
    }


def _route_state_for(case: dict, *, locale: str = "en") -> dict:
    expect = case["expect"]
    want_q = expect.get("query_q")
    ids = expected_query_entry_ids(want_q, repo_root=REPO) if want_q else expected_query_entry_ids(
        None, repo_root=REPO
    )
    count = len(ids)
    selected = expect.get("selected_id")
    focused = selected if expect.get("require_focus") else None
    total = len(expected_query_entry_ids(None, repo_root=REPO))
    if locale == "zh":
        label = f"显示 {count} 条"
    else:
        label = f"{count} of {total} entries"
    return {
        "requested_url": f"http://127.0.0.1:9/{case['route']}",
        "final_url": f"http://127.0.0.1:9/{case['route']}",
        "hash": expect.get("hash", ""),
        "query_q": want_q,
        "rf_q_value": want_q or "",
        "miss_visible": bool(expect.get("miss_visible")),
        "selected_id": selected,
        "visible_result_count": count,
        "visible_entry_ids": list(ids),
        "count_label_visible": True,
        "count_label_text": label,
        "count_label_values": [str(count)],
        "focused_element_id": focused,
        "focused_visible": bool(expect.get("require_focus")),
        "target_below_fixed_ui": True if expect.get("require_focus") else None,
    }


def _rest_states_for(route_state: dict, *, sha: str) -> list[dict]:
    states = []
    total = len(expected_query_entry_ids(None, repo_root=REPO))
    for viewport in ("desktop", "mobile"):
        for locale in ("en", "zh"):
            for theme in ("dark", "light"):
                rs = dict(route_state)
                count = rs.get("visible_result_count") or 0
                if locale == "zh":
                    rs["count_label_text"] = f"显示 {count} 条"
                else:
                    rs["count_label_text"] = f"{count} of {total} entries"
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
                        "bytes": 10,
                        "width": 10,
                        "height": 10,
                        "applied_theme": theme,
                        "applied_locale": locale,
                        "route_state": rs,
                    }
                )
    return states


def _green_manifest() -> dict:
    pages = []
    for i, case in enumerate(ROUTE_CASES):
        sha = f"{i:064x}"
        pages.append(
            {
                "page_id": case["page_id"],
                "route": case["route"],
                "console_errors": [],
                "failed_responses": [],
                "route_journeys": _ok_journeys(case),
                "states": _rest_states_for(_route_state_for(case), sha=sha),
            }
        )
    return {
        "schema": "mastermind.p0_evidence.v2",
        "tool": {"version": "1.4.0", "module_ref": "scripts/capture_page_evidence.py"},
        "candidate_binding": _live_binding(),
        "target": {
            "resolved_sha_or_none": _git("rev-parse", "HEAD"),
            "resolved_sha_source": "verified worktree HEAD",
        },
        "pages": pages,
        "excluded": [],
    }


def test_historical_committed_manifest_is_red_overclaim():
    assert_historical_overclaim_is_red(HISTORICAL_OVERCLAIM)


def test_missing_route_case_is_red():
    manifest = _green_manifest()
    manifest["pages"] = [p for p in manifest["pages"] if p["route"] != "reference.html#vix"]
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("valid_anchor" in e or "reference.html#vix" in e for e in errors)


def test_relabel_default_digest_as_vix_is_red():
    manifest = _green_manifest()
    default = next(p for p in manifest["pages"] if p["route"] == "reference.html")
    vix = next(p for p in manifest["pages"] if p["route"] == "reference.html#vix")
    stolen = default["states"][0]["sha256"]
    for state in vix["states"]:
        state["sha256"] = stolen
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("reused across distinct routes" in e for e in errors)


def test_query_route_without_query_state_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["query_q"] = None
        state["route_state"]["visible_result_count"] = 0
        state["route_state"]["visible_entry_ids"] = []
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("query_q" in e or "visible_result_count" in e for e in errors)


def test_unknown_anchor_without_miss_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html#not-a-real-entry")
    for state in page["states"]:
        state["route_state"]["miss_visible"] = False
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("miss_visible" in e for e in errors)


def test_vix_without_focus_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html#vix")
    for state in page["states"]:
        state["route_state"]["focused_visible"] = False
        state["route_state"]["target_below_fixed_ui"] = False
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("focused_visible" in e or "target_below_fixed_ui" in e for e in errors)


def test_duplicate_page_id_is_red():
    manifest = _green_manifest()
    clone = copy.deepcopy(manifest["pages"][0])
    clone["route"] = "reference.html#dup"
    manifest["pages"].append(clone)
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("duplicate page_id" in e for e in errors)


def test_missing_journeys_is_red():
    manifest = _green_manifest()
    for page in manifest["pages"]:
        page.pop("route_journeys", None)
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("route_journeys" in e for e in errors)


def test_missing_candidate_binding_is_red():
    manifest = _green_manifest()
    manifest.pop("candidate_binding")
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("candidate_binding" in e for e in errors)


def test_png_byte_mutate_is_red(tmp_path: Path):
    manifest = _green_manifest()
    for page in manifest["pages"]:
        for state in page["states"]:
            path = tmp_path / state["file"]
            path.write_bytes(b"not-a-png-but-bytes")
    errors = validate_manifest_route_matrix(manifest, evidence_dir=tmp_path, repo_root=REPO)
    assert any("PNG" in e or "hash" in e or "bytes" in e or "dimensions" in e for e in errors)


def test_unexpected_extra_png_is_red(tmp_path: Path):
    manifest = _green_manifest()
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"\x00\xff\x00\x00"
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    digest = hashlib.sha256(png).hexdigest()
    for page in manifest["pages"]:
        for state in page["states"]:
            state["sha256"] = digest
            state["bytes"] = len(png)
            state["width"] = 1
            state["height"] = 1
            (tmp_path / state["file"]).write_bytes(png)
    (tmp_path / "orphan_extra.png").write_bytes(png)
    errors = validate_manifest_route_matrix(manifest, evidence_dir=tmp_path, repo_root=REPO)
    assert any("unexpected PNG extras" in e for e in errors)


def test_old_tool_version_is_red():
    manifest = _green_manifest()
    manifest["tool"]["version"] = "1.2.0"
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert any("tool version" in e for e in errors)


def test_green_matrix_passes():
    assert validate_manifest_route_matrix(_green_manifest(), repo_root=REPO) == []


def test_mor1_capture_rows_cover_four_cases():
    rows = mor1_capture_rows()
    assert [r["capture_route"] for r in rows] == [c["route"] for c in ROUTE_CASES]
    assert len(rows) == 4


def test_template_writes_query_to_url_and_focuses_valid_anchor():
    text = (REPO / "templates" / "reference.html.j2").read_text(encoding="utf-8")
    assert "READ, never written" not in text
    assert "function syncQueryToUrl" in text
    assert "popstate" in text
    assert "searchParams.set(\"q\"" in text or "searchParams.set('q'" in text
    assert "focusEl.focus" in text or ".focus(" in text
    assert "scrollIntoView" in text


def test_direct_checker_bootstrap_importable():
    src = (REPO / "scripts" / "check_market_reference_route_evidence.py").read_text(
        encoding="utf-8"
    )
    assert "sys.path.insert" in src


def test_forged_zero_source_commit_is_red():
    manifest = _green_manifest()
    manifest["candidate_binding"]["source_commit"] = "0" * 40
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert errors, "forged all-zero source_commit must not validate"
    joined = "\n".join(errors)
    assert "forged" in joined or "not a commit" in joined or "not a 40-char" in joined


def test_fabricated_curve_full_library_ids_are_red():
    manifest = _green_manifest()
    fake_ids = [f"fake-{i}" for i in range(34)]
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html?q=curve")
    for state in page["states"]:
        state["route_state"]["visible_result_count"] = 34
        state["route_state"]["visible_entry_ids"] = list(fake_ids)
        state["route_state"]["count_label_text"] = "34 of 34 entries"
        state["route_state"]["count_label_values"] = ["34"]
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert errors, "34 fabricated curve IDs must not validate"
    joined = "\n".join(errors)
    assert "visible_entry_ids" in joined or "visible_result_count" in joined or "34/34" in joined


def test_extra_tablet_rest_cell_is_red():
    manifest = _green_manifest()
    page = manifest["pages"][0]
    extra = copy.deepcopy(page["states"][0])
    extra["viewport"] = "tablet"
    extra["file"] = "tablet-extra.png"
    extra["sha256"] = "ab" * 32
    page["states"].append(extra)
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert errors, "extra tablet REST cell must not validate"
    joined = "\n".join(errors)
    assert "tablet" in joined or "extra REST" in joined


def test_arbitrary_extra_page_is_red():
    manifest = _green_manifest()
    manifest["pages"].append(
        {
            "page_id": "other_page",
            "route": "other.html",
            "console_errors": [],
            "failed_responses": [],
            "route_journeys": _ok_journeys(ROUTE_CASES[0]),
            "states": [],
        }
    )
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert errors, "arbitrary extra page must not validate"
    joined = "\n".join(errors)
    assert "other_page" in joined or "unexpected extra page" in joined


def test_bogus_back_forward_share_receipts_are_red():
    manifest = _green_manifest()
    bogus = {
        "back": {
            "ok": True,
            "performed": True,
            "after_href": "http://127.0.0.1:9/reference.html?q=navprobe",
            "url_q": "navprobe",
            "input": "wrong",
        },
        "forward": {
            "ok": True,
            "performed": True,
            "after_href": "http://127.0.0.1:9/reference.html",
            "url_q": None,
            "input": "",
        },
        "share": {
            "ok": True,
            "href": "http://example.test/not-the-share-target",
            "final_href": "http://127.0.0.1:9/reference.html",
            "matches_final": True,
        },
    }
    for page in manifest["pages"]:
        page["route_journeys"].update(bogus)
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert errors, "bogus back/forward/share receipts must not validate"
    joined = "\n".join(errors)
    assert "journey back" in joined or "journey forward" in joined or "journey share" in joined


def test_missing_vix_focus_identity_is_red():
    manifest = _green_manifest()
    page = next(p for p in manifest["pages"] if p["route"] == "reference.html#vix")
    for state in page["states"]:
        state["route_state"]["focused_element_id"] = None
    errors = validate_manifest_route_matrix(manifest, repo_root=REPO)
    assert errors, "missing VIX focused_element_id must not validate"
    joined = "\n".join(errors)
    assert "focused_element_id" in joined and "vix" in joined


def test_committed_mor1_packet_satisfies_route_contract():
    manifest_path = REPO / "mockups" / "evidence" / "market_reference_mor1" / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = validate_manifest_route_matrix(
        manifest, evidence_dir=manifest_path.parent, repo_root=REPO
    )
    assert errors == [], "\n".join(errors)
