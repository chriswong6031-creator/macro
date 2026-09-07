"""Public /help directory integration and truth-boundary guards."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from lib.help_directory import (
    HELP_LINKS,
    HELP_ANSWERS,
    _CATEGORIES_BY_ID,
    _check_banned_vocabulary,
    _is_approved_href,
    help_directory_view_model,
    help_answers_view_model,
    product_changelog,
)
from scripts import build_public_pages


ROOT = Path(__file__).resolve().parents[1]


def test_public_builder_renders_help_directory(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)

    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    assert 'data-directory-state="complete"' in html
    assert '<nav class="public-nav"' in html
    assert '<footer class="public-footer">' in html
    assert 'id="help-search"' in html
    assert 'role="status"' in html
    assert 'data-empty-state="empty"' in html
    assert 'data-unknown-state="unknown"' not in html
    assert '>complete<' not in html
    assert '>empty · 0<' not in html
    assert '>unknown<' not in html
    assert "Available" in html
    assert "可用" in html
    assert 'data-changelog-state="published"' in html
    assert "docs/site_semantics" not in html


def test_build_site_renders_help_page_with_the_full_view_model(tmp_path: Path) -> None:
    """The nightly full-site render must render help.html too, not just the
    fast-path public builder (review finding B-F13-3 BLOCKER-1).

    scripts.build_site.build_help_page used to call only
    ``help_directory_view_model`` and splat entries/categories/directory_state
    at the template — but templates/help.html.j2 also dereferences
    ``answers``, ``answers_state``, ``changelog.state`` and iterates
    ``support_plans``, so this exact call shape raised
    ``UndefinedError: 'changelog' is undefined``, silently swallowed by
    build_site's own except-and-log wrapper (no site/help.html written, no
    test failure — ``git diff --stat origin/main -- scripts/build_site.py``
    was empty because nothing there had ever been touched or exercised).
    This test drives scripts.build_site.build_help_page directly — the real
    nightly call shape, not build_public_pages' fast path — and would have
    failed red before lib.help_directory.help_page_view_model became the one
    builder both call sites share.
    """
    import scripts.build_site as bs
    from datetime import datetime, timezone
    from lib import config

    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"), autoescape=True)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    bs.build_help_page(env, tmp_path, generated)

    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    assert 'data-directory-state="complete"' in html
    assert 'data-changelog-state="published"' in html
    assert HELP_ANSWERS[0].question_en in html


def test_help_directory_renders_only_the_frozen_owner_targets(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")

    hrefs = set(re.findall(r'<a\b[^>]*class="help-card"[^>]*href="([^"]+)"', html))
    assert hrefs == {
        "reference.html",
        "methodology.html",
        "measurement.html",
        "support.html",
        "plans.html",
        "plans.html?billing=portal",
        "https://app.mastermind-x.com/terminal?signin=1",
    }
    for label_en, label_zh in (
        ("Market Reference", "市场参考"),
        ("Methodology", "方法论"),
        ("Cycle Intelligence · Calibration Lab", "周期情报 · 校准实验室"),
        ("Support", "支持"),
        ("Plans &amp; pricing", "方案与定价"),
        ("Billing &amp; payments", "账单与付款"),
        ("Account &amp; sign-in", "账户与登录"),
    ):
        assert label_en in html
        assert label_zh in html


def test_help_route_is_registered_as_public_and_extensionless() -> None:
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()

    assert "/help.html" in policy["public"]["exact"]
    assert "redir /help /help.html 301" in caddy
    assert caddy.count("/help.html") >= 5


def test_help_uses_strict_bilingual_markup_and_accessible_filters() -> None:
    template = (ROOT / "templates" / "help.html.j2").read_text()

    assert "macro t(en, zh)" in template
    assert "zh if zh else en" not in template
    assert 'aria-label="{{ t_text(\'Search\', \'搜索\') }}"' in template
    assert 'aria-pressed="true"' in template
    assert 'aria-live="polite"' in template
    assert '@media (max-width:600px)' in template
    assert 'html[data-theme="light"]' in template
    assert "style.textContent" not in template
    assert 'class="sr-only"' not in template


def test_mixed_unknown_entry_renders_beside_complete_owner_without_a_link() -> None:
    unknown = replace(
        HELP_LINKS[1],
        id="methodology-status-unknown",
        state="unknown",
        href=None,
        status_en="Availability unknown",
        status_zh="可用性未知",
    )
    vm = help_directory_view_model(ROOT, entries=(HELP_LINKS[0], unknown))
    vm.update(help_answers_view_model(ROOT))
    vm["changelog"] = product_changelog(ROOT)
    from lib.help_directory import support_routing_view_model

    vm.update(support_routing_view_model())
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)

    html = env.get_template("help.html.j2").render(generated_utc="test", **vm)

    assert 'id="help-market-reference" href="reference.html"' in html
    unknown_card = re.search(
        r'<article class="help-card" id="help-methodology-status-unknown"(?P<body>.*?)</article>',
        html,
        re.DOTALL,
    )
    assert unknown_card is not None
    assert "href=" not in unknown_card.group(0)
    assert 'aria-disabled="true"' in unknown_card.group(0)
    assert "Availability unknown" in unknown_card.group(0)
    assert "可用性未知" in unknown_card.group(0)
    assert len(re.findall(r'<(?:a|article)\b[^>]*\sdata-help-card(?:\s|>)', html)) == 2


def test_public_builder_defers_help_failure_until_other_public_pages_land(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _broken_help(_root: Path) -> dict:
        raise ValueError("help source drift")

    monkeypatch.setattr(build_public_pages, "help_page_view_model", _broken_help)

    with pytest.raises(ValueError, match="help source drift"):
        build_public_pages.build(tmp_path)

    assert not (tmp_path / "help.html").exists()
    for name in ("plans.html", "support.html", "unsubscribe.html"):
        assert (tmp_path / name).is_file(), name


def test_help_is_discoverable_in_shared_public_nav() -> None:
    nav = (ROOT / "templates" / "_public_nav.html.j2").read_text()
    assert 'href="{{ rel }}help.html"' in nav
    assert "t('Help', '帮助')" in nav


# ===========================================================================
# Packet B-F13-3 — answers, changelog
# ===========================================================================
_FILE_RE = re.compile(r"[A-Za-z_]+\.(py|j2|yml|css|js)")
_CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")


def _check_no_banned(en: str, zh: str) -> None:
    # Delegates to the production checker (lib.help_directory._check_banned_vocabulary)
    # instead of maintaining a second, drift-prone word list here (review finding M2:
    # the old local copy re-implemented the same defective substring match, so it could
    # never catch a bug in the real checker). Raises AssertionError with the same
    # message shape the rest of this module already expects.
    try:
        _check_banned_vocabulary("test fixture", en, zh)
    except ValueError as exc:
        raise AssertionError(str(exc)) from exc


def test_answers_are_question_shaped_and_bilingual() -> None:
    assert len(HELP_ANSWERS) >= 12
    starters = ("How", "What", "Where", "Why", "When", "Can", "Will", "Do")
    for a in HELP_ANSWERS:
        assert a.question_en.startswith(starters), a.question_en
        assert a.question_en.rstrip().endswith("?")
        assert a.question_zh.rstrip().endswith("？")
        assert a.question_en and a.question_zh and a.answer_en and a.answer_zh
        assert a.answer_zh != a.answer_en
        assert a.question_zh != a.question_en


def test_answer_word_budgets() -> None:
    for a in HELP_ANSWERS:
        # Spec §1.6 budgets questions at <=10 words; the frozen §4.1 entry text for
        # "why-a-dash" itself runs to 11 words — a spec self-inconsistency (see PR
        # DEVIATIONS) rather than an authoring error, so the gate allows one word
        # of slack instead of silently rewriting the frozen copy.
        assert len(a.question_en.split()) <= 11, a.question_en
        assert len(a.answer_en.split()) <= 22, a.answer_en
        assert a.answer_en.rstrip().endswith(".")
        assert len(a.question_zh) <= 20, a.question_zh
        assert len(a.answer_zh) <= 46, a.answer_zh


def test_answers_carry_no_machine_vocabulary() -> None:
    for a in HELP_ANSWERS:
        _check_no_banned(a.question_en, a.question_zh)
        _check_no_banned(a.answer_en, a.answer_zh)


def test_answer_categories_reuse_the_frozen_vocabulary() -> None:
    for a in HELP_ANSWERS:
        assert a.category in _CATEGORIES_BY_ID
    assert set(a.category for a in HELP_ANSWERS) <= set(_CATEGORIES_BY_ID)


def test_answer_hrefs_are_approved_and_land_on_a_real_owner() -> None:
    for a in HELP_ANSWERS:
        if a.href is None:
            continue
        assert _is_approved_href(a.href)


def test_changelog_is_dated_newest_first_and_cites_a_pr() -> None:
    vm = product_changelog(ROOT)
    assert vm["state"] == "published"
    entries = vm["entries"]
    assert len(entries) >= 1
    for e in entries:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"])
        assert e["date"] >= "2026-09-04"
        assert isinstance(e["pr"], int) and e["pr"] > 0
        assert e["en"] and e["zh"] and e["zh"] != e["en"]
    keys = [(e["date"], e["pr"]) for e in entries]
    assert keys == sorted(keys, reverse=True)


def test_changelog_renders_on_the_help_page(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    assert 'data-changelog-state="published"' in html
    assert '<time datetime="2026-09-04"' in html
    assert "#6849" in html
    vm = product_changelog(ROOT)
    newest = vm["entries"][0]
    assert newest["zh"] in html


def test_missing_changelog_file_degrades_to_a_disclosed_empty_state(tmp_path: Path) -> None:
    vm = product_changelog(tmp_path)
    assert vm["state"] == "empty"
    assert vm["entries"] == []
    assert vm["note_en"] and vm["note_zh"]


def test_malformed_changelog_is_refused(tmp_path: Path) -> None:
    from lib import help_directory as hd
    bad_root = tmp_path
    (bad_root / "data" / "product").mkdir(parents=True)
    (bad_root / "data" / "product" / "changelog.yml").write_text(
        "schema: mastermind.product_changelog.v1\n"
        "note_en: n\nnote_zh: n\n"
        "entries:\n  - {id: bad, date: not-a-date, pr: 1, en: x, zh: y}\n"
    )
    with pytest.raises(ValueError):
        hd.product_changelog(bad_root)


def test_help_page_prints_the_plan_promises(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    for plan_id in ("free", "essential", "pro"):
        assert f'data-plan="{plan_id}"' in html
    assert html.count('class="help-support-cta"') == 1


def test_answers_render_above_the_resource_grid(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    assert html.index("help-answers-h") < html.index('class="help-grid"')


def test_search_covers_answers_and_links(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    assert "[data-help-card],[data-answer]" in html


def test_still_one_nav_family(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    assert 'class="public-nav"' in html
    assert "_site_nav" not in html


def test_no_raw_pr_or_slug_leaks_into_user_copy(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")
    # Scope to OUR new sections only — the shared nav/footer chrome carries its own
    # legitimate all-caps microcopy (e.g. "CONNECTED RESEARCH DESK") unrelated to this
    # packet's authored answers/changelog copy.
    answers_html = re.search(r'<dl class="help-answers">(.*?)</dl>', html, re.S)
    log_html = re.search(r'<ul class="help-log">(.*?)</ul>', html, re.S)
    for match in (answers_html, log_html):
        if match is None:
            continue
        dd_and_p = re.findall(r"<(?:dd|p)[^>]*>(.*?)</(?:dd|p)>", match.group(1), re.S)
        for chunk in dd_and_p:
            text = re.sub(r"<[^>]+>", "", chunk)
            assert not _FILE_RE.search(text), text
            assert not _CAPS_RE.search(text), text
