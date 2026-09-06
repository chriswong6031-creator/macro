"""View-model unit contract for lib.glossary."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from lib import config
from lib.glossary import (
    BANNED_GLANCE_PATTERNS,
    BANNED_GLANCE_TOKENS,
    GLOSSARY_DOMAINS,
    GLOSSARY_MIN_TERMS,
    GLOSSARY_TERMS,
    glossary_view_model,
    validate_glossary,
)

ROOT = config.ROOT


def test_glossary_defines_at_least_fifty_terms():
    assert len(GLOSSARY_TERMS) >= GLOSSARY_MIN_TERMS


def test_every_term_binds_to_an_existing_source_heading_line():
    for term in GLOSSARY_TERMS:
        path = ROOT / term.source_file
        lines = path.read_text(encoding="utf-8").splitlines()
        actual = lines[term.source_line - 1].strip()
        assert actual in (
            f"### {term.source_heading}",
            f"#### {term.source_heading}",
            f"## {term.source_heading}",
        ), f"{term.id}: {actual!r} does not match {term.source_heading!r}"


def test_term_ids_are_unique_kebab_case():
    ids = [t.id for t in GLOSSARY_TERMS]
    assert len(ids) == len(set(ids))
    for i in ids:
        assert re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", i)


def test_every_term_carries_english_and_chinese_name_and_answer():
    for term in GLOSSARY_TERMS:
        assert term.name_en.strip()
        assert term.name_zh.strip()
        assert term.answer_en.strip()
        assert term.answer_zh.strip()


def test_glance_answers_respect_the_word_and_character_budgets():
    for term in GLOSSARY_TERMS:
        assert len(term.answer_en.split()) <= 30, term.id
        assert len(term.answer_zh) <= 60, term.id
        assert (term.why_en is None) == (term.why_zh is None), term.id
        if term.why_en is not None:
            assert len(term.why_en.split()) <= 20, term.id
            assert len(term.why_zh) <= 40, term.id


def test_glance_text_carries_no_banned_vocabulary():
    for term in GLOSSARY_TERMS:
        for text in (term.answer_en, term.answer_zh, term.why_en or "", term.why_zh or ""):
            for pattern in BANNED_GLANCE_PATTERNS:
                assert not pattern.search(text), f"{term.id}: banned pattern in {text!r}"
            for token in re.findall(r"[A-Za-z0-9_]+", text):
                assert token not in BANNED_GLANCE_TOKENS, f"{term.id}: banned token {token!r}"


def test_validate_glossary_rejects_a_term_whose_source_line_does_not_match():
    bad = replace(GLOSSARY_TERMS[0], source_line=GLOSSARY_TERMS[0].source_line + 1)
    terms = (bad,) + GLOSSARY_TERMS[1:]
    with pytest.raises(ValueError):
        validate_glossary(ROOT, terms)


def test_validate_glossary_rejects_an_over_budget_answer():
    bad = replace(GLOSSARY_TERMS[0], answer_en=" ".join(["word"] * 31))
    terms = (bad,) + GLOSSARY_TERMS[1:]
    with pytest.raises(ValueError):
        validate_glossary(ROOT, terms)


def test_every_frozen_domain_carries_terms_and_no_unknown_domain_appears():
    domain_ids = {d.id for d in GLOSSARY_DOMAINS}
    seen = {t.domain for t in GLOSSARY_TERMS}
    assert seen <= domain_ids
    for domain in GLOSSARY_DOMAINS:
        assert any(t.domain == domain.id for t in GLOSSARY_TERMS), domain.id


def test_view_model_prints_all_twenty_six_letters_including_empty_ones():
    vm = glossary_view_model(ROOT)
    assert len(vm["letters"]) == 26
    assert [l["id"] for l in vm["letters"]] == [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    assert any(l["count"] == 0 for l in vm["letters"])


def test_letter_anchor_is_set_exactly_once_per_occupied_letter():
    vm = glossary_view_model(ROOT)
    for domain in vm["domains"]:
        seen = set()
        for term in domain["terms"]:
            if term["letter_anchor"]:
                assert term["letter"] not in seen
                seen.add(term["letter"])
