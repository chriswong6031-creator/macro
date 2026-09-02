"""Tests for scripts/build_market_reference.py (MOR-1 public Reference surface).

Verifies:
1. Registry validation fails closed on every DEC §3.3 / MOR1_CONTRACT.md rule,
   one red-fixture per rule (unknown owner ref, duplicate alias, superseded_by
   cycle, unsafe source URL, missing caveats on kind:indicator, missing either
   language) — each fixture violates exactly one rule so the failure message
   is attributable.
2. Happy-path build of the real committed registry: validates clean, and the
   rendered page carries the expected entry/family counts.
3. Anchor stability: every registry entry id appears as a real `id="..."`
   anchor in the rendered HTML (deep-link contract).
4. EN/ZH parity: every rendered entry carries both an `l-en` and an `l-zh`
   span (dual-language contract, build-time guaranteed per DEC §3.2).
"""
from __future__ import annotations

import copy
import re
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


def test_explicit_null_interpretation_is_accepted_same_as_omitted():
    """Contract note: explicit `null` interpretation values are equivalent to
    omitted — the validator must accept both without complaint."""
    reg = _registry(_base_entry(interpretation_up=None, interpretation_down=None,
                                 interpretation_neutral=None))
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
