"""Deterministic source-contract tests for the public /help directory."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from lib.help_directory import HELP_LINKS, help_directory_view_model, validate_help_directory


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_directory_validates_and_exposes_a_serializable_complete_model() -> None:
    """Breaks if a frozen link, category, label, source anchor, or state drifts."""
    validate_help_directory(ROOT)

    model = help_directory_view_model(ROOT)

    assert model["directory_state"] == "complete"
    assert model["categories"] == [
        {"id": "research", "label_en": "Research", "label_zh": "研究"},
        {"id": "platform", "label_en": "Platform", "label_zh": "平台"},
        {"id": "account", "label_en": "Account", "label_zh": "账户"},
    ]
    assert [
        (entry["id"], entry["category"], entry["label_en"], entry["label_zh"], entry["href"], entry["state"])
        for entry in model["entries"]
    ] == [
        ("market-reference", "research", "Market Reference", "市场参考", "reference.html", "complete"),
        ("methodology", "research", "Methodology", "方法论", "methodology.html", "complete"),
        (
            "cycle-intelligence-calibration-lab",
            "research",
            "Cycle Intelligence · Calibration Lab",
            "周期情报 · 校准实验室",
            "measurement.html",
            "complete",
        ),
        ("support", "platform", "Support", "支持", "support.html", "complete"),
        ("plans-pricing", "platform", "Plans & pricing", "方案与定价", "plans.html", "complete"),
        ("billing-payments", "account", "Billing & payments", "账单与付款", "plans.html?billing=portal", "complete"),
        (
            "account-sign-in",
            "account",
            "Account & sign-in",
            "账户与登录",
            "https://app.mastermind-x.com/terminal?signin=1",
            "complete",
        ),
    ]
    for entry in model["entries"]:
        assert {
            "id",
            "category",
            "category_en",
            "category_zh",
            "label_en",
            "label_zh",
            "href",
            "state",
        } <= entry.keys()


def test_empty_filter_is_a_valid_explicit_empty_directory() -> None:
    """Breaks if an empty filtered result is treated as unknown or invalid."""
    model = help_directory_view_model(ROOT, entries=())

    assert model["directory_state"] == "empty"
    assert model["entries"] == []
    assert [category["id"] for category in model["categories"]] == ["research", "platform", "account"]


def test_unknown_entry_is_explicit_and_cannot_inherit_a_link() -> None:
    """Breaks if unknown content silently falls back to a complete target."""
    unknown = replace(
        HELP_LINKS[0],
        id="reference-status-unknown",
        state="unknown",
        href=None,
        status_en="Availability unknown",
        status_zh="可用性未知",
    )

    model = help_directory_view_model(ROOT, entries=(unknown,))

    assert model["directory_state"] == "unknown"
    assert model["entries"] == [{
        "id": "reference-status-unknown",
        "category": "research",
        "category_en": "Research",
        "category_zh": "研究",
        "label_en": "Market Reference",
        "label_zh": "市场参考",
        "href": None,
        "state": "unknown",
        "status_en": "Availability unknown",
        "status_zh": "可用性未知",
    }]


def test_validation_rejects_empty_chinese_label() -> None:
    """Breaks if a missing Chinese label can reach a fallback-capable view."""
    entry = replace(HELP_LINKS[0], label_zh="")

    with pytest.raises(ValueError, match="label_zh must be non-empty"):
        validate_help_directory(ROOT, entries=(entry,))


def test_validation_rejects_duplicate_kebab_id() -> None:
    """Breaks if filters can collide on an unstable directory identity."""
    duplicate = replace(HELP_LINKS[1], id=HELP_LINKS[0].id)

    with pytest.raises(ValueError, match="duplicate help entry id"):
        validate_help_directory(ROOT, entries=(HELP_LINKS[0], duplicate))


def test_validation_rejects_source_missing_one_exact_label(tmp_path: Path) -> None:
    """Breaks if a complete entry can claim a source that lacks its Chinese label."""
    source = tmp_path / "templates" / "source.html.j2"
    source.parent.mkdir()
    source.write_text(HELP_LINKS[0].label_en, encoding="utf-8")
    entry = replace(HELP_LINKS[0], source_template="templates/source.html.j2")

    with pytest.raises(ValueError, match="missing label_zh"):
        validate_help_directory(tmp_path, entries=(entry,))


def test_validation_rejects_unapproved_complete_url() -> None:
    """Breaks if an external host or scheme can be introduced as a help target."""
    entry = replace(HELP_LINKS[0], href="https://example.com/reference.html")

    with pytest.raises(ValueError, match="unapproved href"):
        validate_help_directory(ROOT, entries=(entry,))


def test_validation_rejects_unknown_entry_with_clickable_href() -> None:
    """Breaks if the unknown state can expose an active navigation target."""
    entry = replace(
        HELP_LINKS[0],
        id="reference-status-unknown",
        state="unknown",
        status_en="Availability unknown",
        status_zh="可用性未知",
    )

    with pytest.raises(ValueError, match="unknown entries must not define href"):
        validate_help_directory(ROOT, entries=(entry,))
