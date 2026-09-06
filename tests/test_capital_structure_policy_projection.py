"""Tests for the Policy watch chip on capital_structure.html (B-F09-6, MO-PAID-067)."""
from __future__ import annotations

import re

import pytest

import scripts.build_capital_structure_page as page_builder

_BANNED_SCORE = re.compile(
    r"\bbuy\b|\bsell\b|bullish|bearish|upgrade|downgrade|\brank\b|\bscore\b|看多|看空|评分",
    re.IGNORECASE,
)


def _render(root):
    return page_builder.render(root).read_text()


def test_1_unavailable_state_renders_both_languages(tmp_path, monkeypatch):
    (tmp_path / "templates").mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copytree(page_builder._REPO_ROOT / "templates", tmp_path / "templates", dirs_exist_ok=True)

    monkeypatch.setattr(page_builder, "_policy_watch", lambda today=None: {
        "state": "unavailable",
        "headline_en": "Policy calendar not in this build",
        "headline_zh": "本次构建未包含政策日历",
        "detail_en": "Nothing is hidden — the source record was not present when this page was built.",
        "detail_zh": "没有隐藏内容——本页构建时未取到来源记录。",
    })
    html = _render(tmp_path)
    assert "Policy calendar not in this build" in html
    assert "本次构建未包含政策日历" in html
    assert 'id="cs-policy"' in html


def test_2_empty_state_differs_from_unavailable(tmp_path, monkeypatch):
    shutil_copy(tmp_path)
    monkeypatch.setattr(page_builder, "_policy_watch", lambda today=None: {
        "state": "empty",
        "headline_en": "No dated policy step ahead",
        "headline_zh": "前方没有已定日期的政策节点",
        "detail_en": "We watch SEC, Treasury, Fed, CFTC and FinCEN rule dates. None is pending.",
        "detail_zh": "我们关注 SEC、财政部、美联储、CFTC 与 FinCEN 的规则日期，目前没有待办节点。",
    })
    html = _render(tmp_path)
    assert "No dated policy step ahead" in html
    assert "Policy calendar not in this build" not in html


def test_3_happy_path_uses_typed_chip_fields(tmp_path, monkeypatch):
    shutil_copy(tmp_path)
    calls = {"n": 0}
    row = {"days_to_next_comment_close": 12, "next_comment_close_date": "2026-09-18",
           "prorule_inflow_60d": 1, "rule_finalization_60d": 0}

    def fake_calendar(df=None, today=None):
        return {"themes": {"capital_markets": row}, "upcoming_events": []}

    def fake_chip(policy_row, theme_key):
        calls["n"] += 1
        return {
            "theme": theme_key,
            "summary": "comment close in 12d (2026-09-18)",
            "days_to_comment_close": 12,
            "days_to_rule_effective": None,
            "prorule_inflow_60d": 1,
            "rule_finalization_60d": 0,
            "next_comment_close_date": "2026-09-18",
            "next_comment_close_title": "x",
            "evidence_class": "dated-structured",
        }

    monkeypatch.setattr("engine.policy_calendar.compute_policy_calendar", fake_calendar)
    monkeypatch.setattr("engine.policy_calendar.format_policy_reg_chip", fake_chip)
    html = _render(tmp_path)
    assert "Comment window closes in 12 days" in html
    assert "征询意见期 12 天后截止" in html
    assert calls["n"] == 1


def test_4_no_score_rank_or_direction(tmp_path, monkeypatch):
    shutil_copy(tmp_path)
    row = {"days_to_next_comment_close": 5}

    def fake_calendar(df=None, today=None):
        return {"themes": {"capital_markets": row}, "upcoming_events": []}

    def fake_chip(policy_row, theme_key):
        return {
            "theme": theme_key, "summary": "comment close in 5d",
            "days_to_comment_close": 5, "days_to_rule_effective": None,
            "prorule_inflow_60d": 0, "rule_finalization_60d": 0,
            "next_comment_close_date": "x", "next_comment_close_title": "x",
            "evidence_class": "dated-structured",
        }

    monkeypatch.setattr("engine.policy_calendar.compute_policy_calendar", fake_calendar)
    monkeypatch.setattr("engine.policy_calendar.format_policy_reg_chip", fake_chip)
    html = _render(tmp_path)
    section = html[html.index('id="cs-policy"'):html.index('id="cs-policy"') + 1200]
    assert not _BANNED_SCORE.search(section)


def test_5_en_zh_span_parity(tmp_path, monkeypatch):
    shutil_copy(tmp_path)
    monkeypatch.setattr(page_builder, "_policy_watch", lambda today=None: {
        "state": "empty", "headline_en": "No dated policy step ahead",
        "headline_zh": "前方没有已定日期的政策节点",
        "detail_en": "We watch SEC, Treasury, Fed, CFTC and FinCEN rule dates. None is pending.",
        "detail_zh": "我们关注 SEC、财政部、美联储、CFTC 与 FinCEN 的规则日期，目前没有待办节点。",
    })
    html = _render(tmp_path)
    start = html.index('id="cs-policy"')
    end = html.index("</section>", start)
    block = html[start:end]
    assert block.count('class="l-en"') == block.count('class="l-zh"')


def test_6_chip_summary_never_rendered(tmp_path, monkeypatch):
    shutil_copy(tmp_path)
    row = {"days_to_next_comment_close": 5}

    def fake_calendar(df=None, today=None):
        return {"themes": {"capital_markets": row}, "upcoming_events": []}

    def fake_chip(policy_row, theme_key):
        return {
            "theme": theme_key, "summary": "MACHINE_ONLY_PHRASE_xyz",
            "days_to_comment_close": 5, "days_to_rule_effective": None,
            "prorule_inflow_60d": 0, "rule_finalization_60d": 0,
            "next_comment_close_date": "x", "next_comment_close_title": "x",
            "evidence_class": "dated-structured",
        }

    monkeypatch.setattr("engine.policy_calendar.compute_policy_calendar", fake_calendar)
    monkeypatch.setattr("engine.policy_calendar.format_policy_reg_chip", fake_chip)
    html = _render(tmp_path)
    assert "MACHINE_ONLY_PHRASE_xyz" not in html


def test_7_paired_asset_guard_unchanged(tmp_path):
    shutil_copy(tmp_path)
    assert page_builder._ASSETS == (
        "capital_structure_boot.js", "capital_structure.css", "capital_structure.js",
    )
    page_builder.render(tmp_path)
    for asset in page_builder._ASSETS:
        src = (tmp_path / "templates" / asset).read_bytes()
        dst = (tmp_path / "site" / asset).read_bytes()
        assert src == dst


def shutil_copy(tmp_path):
    import shutil
    (tmp_path / "templates").mkdir(parents=True, exist_ok=True)
    shutil.copytree(page_builder._REPO_ROOT / "templates", tmp_path / "templates", dirs_exist_ok=True)
