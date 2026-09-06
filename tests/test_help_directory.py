"""Public /help directory integration and truth-boundary guards."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from lib.help_directory import HELP_LINKS, help_directory_view_model
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
    assert "changelog" not in html.lower()
    assert "docs/site_semantics" not in html


def test_help_directory_renders_only_the_frozen_owner_targets(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    html = (tmp_path / "help.html").read_text(encoding="utf-8")

    hrefs = set(re.findall(r'<a\b[^>]*class="help-card"[^>]*href="([^"]+)"', html))
    assert hrefs == {
        "reference.html",
        "methodology.html",
        "measurement.html",
        "glossary.html",
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

    monkeypatch.setattr(build_public_pages, "help_directory_view_model", _broken_help)

    with pytest.raises(ValueError, match="help source drift"):
        build_public_pages.build(tmp_path)

    assert not (tmp_path / "help.html").exists()
    for name in ("plans.html", "support.html", "unsubscribe.html"):
        assert (tmp_path / name).is_file(), name


def test_help_is_discoverable_in_shared_public_nav() -> None:
    nav = (ROOT / "templates" / "_public_nav.html.j2").read_text()
    assert 'href="{{ rel }}help.html"' in nav
    assert "t('Help', '帮助')" in nav
