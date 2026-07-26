"""tests/test_unsubscribe_page.py — /unsubscribe.html (SEE W4, gate: boundary green).

The page is a port of the /support.html pinned design (mockups/support_email/PIN.md), so
this suite guards the properties an edit could quietly break without anything else going
red — the ones invisible in a screenshot:

  * **the serving boundary, PER MATCHER.** ``tests/test_site_access_boundary.py`` only
    diffs ONE Caddy matcher (the ``PUBLIC-BOUNDARY`` ``@reg_asset`` block) against
    ``config/site_access.yml``; the other five and ``app/regwall.py``'s mirror have no
    generic guard at all. ``test_support_page.py`` covers its own page with
    ``caddy.count("/support.html") == 6``, which is an occurrence COUNT — it passes if the
    path appears six times in one matcher and zero times in the other five. So this suite
    names each matcher and checks inside it. A page that 302s to sign-in is worthless
    here in a way it is not elsewhere: it is the only exit from marketing mail, and a
    broken one is a compliance failure, not a degraded feature;
  * it is deliberately OUT of the sitemap while being public — the inverse of every other
    public page, so it needs its own assertion;
  * nothing mutates on load (a mail scanner must not be able to unsubscribe anybody);
  * the API contract, both languages, no translated ``title=``;
  * PIN §1.1 — success/error use ``--ok``/``--act`` and NEVER ``--up``/``--down``, which
    theme.css swaps under ``html[data-lang="zh"]``.

Renders into tmp_path only; nothing here writes to site/ or data/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEMPLATE = "unsubscribe.html.j2"
PATH = "/unsubscribe.html"


@pytest.fixture(scope="module")
def page(tmp_path_factory) -> str:
    """The page as it ships, rendered into a throwaway dir.

    The Jinja environment is built exactly as scripts/build_site.main() does and the
    output goes through lib.pages.inject_text — the shim half of write_page — so the
    string under test is byte-for-byte what build_unsubscribe_page writes. Importing
    build_site itself would drag plotly and the whole engine into an otherwise
    pure-stdlib suite, and would give this module a way to write into site/.
    """
    from jinja2 import Environment, FileSystemLoader

    from engine import i18n
    from lib.pages import inject_text
    from lib.seo import SITE_BASE

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip, SITE_BASE=SITE_BASE)
    html = inject_text(env.get_template(TEMPLATE).render(generated_utc="2026-07-26 00:00"))
    out = tmp_path_factory.mktemp("site") / "unsubscribe.html"
    out.write_text(html, encoding="utf-8")
    return html


def _page_css(text: str) -> str:
    """Only the page's own <style> blocks (theme.css/theme.js are linked, not inlined)."""
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S))


# ===========================================================================
# It builds, and it is wired
# ===========================================================================
def test_build_site_wires_the_page_through_write_page():
    """write_page and not write_text: a raw write drops the data-base shim whenever the
    builder runs standalone, which silently regresses the R2 rerouting (lib/pages.py)."""
    src = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    assert "def build_unsubscribe_page(env: Environment, site: Path, generated: str) -> None:" in src
    assert 'write_page(site / "unsubscribe.html", html)' in src
    assert "        build_unsubscribe_page(env, site, generated)\n" in src, "main() must call it"


def test_the_committed_page_matches_the_template():
    """site/unsubscribe.html is committed so the merge cannot ship a 404 (the /support.html
    precedent). It has to be the CURRENT render, or the boundary lists a stale file."""
    from jinja2 import Environment, FileSystemLoader

    from engine import i18n
    from lib.pages import inject_text
    from lib.seo import SITE_BASE

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip, SITE_BASE=SITE_BASE)
    fresh = inject_text(env.get_template(TEMPLATE).render(generated_utc="2026-07-26 00:00"))
    shipped = (ROOT / "site" / "unsubscribe.html").read_text(encoding="utf-8")
    assert shipped == fresh, "re-run the builder and commit site/unsubscribe.html"


def test_page_builds_with_the_house_chrome(page):
    assert page.lstrip().startswith("<!DOCTYPE html>")
    assert "<title>Unsubscribe — Mastermind</title>" in page
    assert 'href="theme.css"' in page and 'src="theme.js"' in page
    assert 'class="site-nav"' in page and 'class="nav-links"' in page   # _site_nav include
    assert "data-dbase" in page, "write_page must inject the data-base shim"
    assert f'rel="canonical" href="https://www.mastermind-x.com{PATH}"' in page


def test_no_external_asset_dependencies(page):
    """China blocks the Google CDN — every font and SDK on this estate is vendored."""
    for host in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net",
                 "unpkg.com", "cdnjs.cloudflare.com", "ajax.googleapis.com"):
        assert host not in page, host
    for url in re.findall(r'(?:src|href)="(https?://[^"]+)"', page):
        assert url.startswith(("https://www.mastermind-x.com", "https://app.mastermind-x.com",
                               "https://bot.mastermind-x.com")), url


# ===========================================================================
# The API contract
# ===========================================================================
def test_the_page_posts_to_the_real_route(page):
    assert "'/api/email/unsubscribe'" in page
    assert "method: 'POST'" in page
    assert "t: TOKEN" in page and "action: action" in page


def test_nothing_mutates_on_load(page):
    """A GET that unsubscribed would silently opt out everyone whose corporate mail
    scanner follows links in inbound messages. Every request must originate in a click."""
    js = page.split("<script>")[-1]
    assert js.count("fetch(") == 1, "one request path, and it is the button's"
    for line in js.splitlines():
        if re.search(r"\bsend\('", line):
            assert "addEventListener('click'" in line, f"send() outside a click: {line.strip()}"


def test_a_missing_token_is_decided_client_side_without_a_request(page):
    assert "if (!TOKEN) H.setAttribute('data-unsub', 'bad');" in page


def test_a_400_is_shown_as_a_dead_link_not_an_error(page):
    """The server answers 400 for every token failure; the page already knows how to
    explain a dead link, and "something went wrong" would send the reader to support for
    a problem they can fix by opening a newer email."""
    assert "r.status === 400" in page
    assert "'data-unsub', 'bad'" in page


def test_the_token_is_never_written_back_into_the_dom(page):
    """A forwarded link should leave nothing behind."""
    assert "textContent = TOKEN" not in page
    assert "innerHTML = TOKEN" not in page
    assert "localStorage.setItem('t'" not in page


def test_resubscribe_is_a_separate_explicit_action(page):
    """Never the default. The re-subscribe button is ghost-weight, lives only in the
    already-unsubscribed state, and sends its own action."""
    assert "send('resubscribe', back)" in page
    assert 'id="u-back"' in page
    css = _page_css(page)
    assert ".btn-ghost{" in css
    assert re.search(r'id="u-back"[^>]*class="btn btn-ghost"|class="btn btn-ghost"[^>]*id="u-back"',
                     page), "the way back must not be a primary button"


def test_a_refused_lift_hides_the_way_back_and_explains(page):
    css = _page_css(page)
    assert 'html[data-refused="1"] .refused{ display:block; }' in css
    assert 'html[data-refused="1"] .st-off .btn-ghost{ display:none; }' in css


# ===========================================================================
# Bilingual (the house law)
# ===========================================================================
KEY_STRINGS = [
    ("Email settings", "邮件设置"),
    ("One click. ", "一次点击，"),
    ("No more marketing email.", "不再收到营销邮件。"),
    ("Account emails — receipts, sign-in links, support replies — keep coming either way.",
     "账户邮件——收据、登录链接、客服回复——不受影响，仍会照常发送。"),
    ("Unsubscribe", "退订"),
    ("Nothing changes until you press it.", "在你点击之前，什么都不会改变。"),
    ("Marketing emails are off.", "营销邮件已关闭。"),
    ("Turn them back on", "重新开启"),
    ("We will not email to ask you to reconsider.", "我们不会再发邮件劝你回来。"),
    ("This link does not work.", "这个链接无法使用。"),
    ("Marketing email: off", "营销邮件：已关闭"),
]


@pytest.mark.parametrize("en,zh", KEY_STRINGS)
def test_every_key_string_ships_in_both_languages(page, en, zh):
    assert f'<span class="l-en">{en}</span>' in page, en
    assert f'<span class="l-zh">{zh}</span>' in page, zh


def test_no_translated_text_in_title_attributes(page):
    """CI-guarded house law: l-en/l-zh cannot operate inside an attribute."""
    cjk = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]")
    for value in re.findall(r'\btitle="([^"]*)"', page):
        assert not cjk.search(value), value


def test_the_cjk_micro_label_gets_a_hanzi_face(page):
    """The mono stack carries no Hanzi, so a ZH label otherwise falls through to whatever
    the system picks — on some machines a serif."""
    css = _page_css(page)
    assert 'html[data-lang="zh"] .mlab{' in css
    assert "PingFang SC" in css


# ===========================================================================
# PIN §1.1 — the state colour law, as an executable assert
# ===========================================================================
def test_success_and_error_never_use_the_direction_tokens(page):
    """--up/--down swap red<->green under html[data-lang="zh"] for the Asia convention, so
    a success panel painted with --up turns RED for every Chinese reader. --ok/--act encode
    health, never direction, and deliberately do not swap."""
    css = _page_css(page)
    assert "var(--up)" not in css and "var(--down)" not in css
    assert "--up" not in css and "--down" not in css


@pytest.mark.parametrize("selector", [
    r'html\[data-unsub="off"\]\s+\.panel\{ --accent:var\(--ok\); \}',
    r'html\[data-unsub="on"\]\s+\.panel\{ --accent:var\(--ok\); \}',
    r'html\[data-unsub="bad"\]\s+\.panel\{ --accent:var\(--act\); \}',
    r'html\[data-unsub="error"\]\s+\.panel\{ --accent:var\(--act\); \}',
])
def test_the_rail_carries_the_health_tokens(page, selector):
    assert re.search(selector, _page_css(page)), selector


def test_the_seal_and_the_error_bar_are_correctly_toned(page):
    css = _page_css(page)
    assert "var(--ok)" in re.search(r"\n\.seal\{([^}]*)\}", css).group(1)
    assert "var(--act)" in re.search(r"\n\.seal\.bad\{([^}]*)\}", css).group(1)
    assert "var(--act)" in re.search(r"\n\.err\{([^}]*)\}", css).group(1)


def test_an_error_keeps_the_button_the_reader_was_about_to_press(page):
    """Never discard the action on a failure — the support page's rule, applied here."""
    assert 'html[data-unsub="error"] .st-ready{ display:block; }' in _page_css(page)


# ===========================================================================
# THE SERVING BOUNDARY — per matcher, not by occurrence count
# ===========================================================================
CADDY = (ROOT / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")

#: Every named matcher in the Caddyfile whose path list decides whether a public page is
#: served or bounced to sign-in. The three `_err` twins are the handle_errors mirrors: if
#: the gate upstream blips, THOSE decide, and a page missing from them 302s exactly when
#: the estate is already having a bad day.
MATCHERS = ("@reg_html", "@reg_asset", "@gate_html",
            "@reg_html_err", "@reg_asset_err", "@gate_html_err")


def _matcher_block(name: str) -> str:
    """The body of one named Caddy matcher block."""
    m = re.search(re.escape(name) + r"\s*\{(.*?)\n\s*\}", CADDY, re.S)
    assert m, f"matcher {name} not found in the Caddyfile"
    return m.group(1)


@pytest.mark.parametrize("matcher", MATCHERS)
def test_unsubscribe_is_public_in_every_caddy_matcher(matcher):
    """Named, not counted. `caddy.count(path) == 6` passes if a path appears six times in
    one matcher and zero times in the other five."""
    assert PATH in _matcher_block(matcher), f"{PATH} missing from {matcher}"


@pytest.mark.parametrize("matcher", MATCHERS)
def test_the_matchers_still_agree_with_each_other_about_support(matcher):
    """The page this one was modelled on, so a matcher that silently lost its path list is
    caught here rather than by the next public page's author."""
    assert "/support.html" in _matcher_block(matcher)


def test_unsubscribe_is_public_in_the_policy():
    import yaml

    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
    assert PATH in policy["public"]["exact"]


def test_unsubscribe_is_public_in_the_regwalls_own_mirror():
    """app/regwall.py decides at the API layer. It has NO generic guard — the boundary
    suite never imports it — so this is the only thing standing between a change here and
    a page that 302s every unsubscribe attempt to a sign-in screen."""
    from app import regwall

    assert PATH in regwall.PUBLIC_PATHS
    assert regwall._is_public(PATH) is True
    assert regwall._is_public(PATH + "?t=abc") is True, "the token must not defeat the match"


def test_nothing_else_became_public_as_a_side_effect():
    """Mutation-check the blast radius of this PR's boundary edit: exactly one path was
    added to the policy, and it is this one."""
    import subprocess

    import yaml

    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
    base = subprocess.run(
        ["git", "show", "origin/main:config/site_access.yml"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    if base.returncode != 0:            # shallow clone / detached CI checkout
        pytest.skip("origin/main not available for a diff")
    before = yaml.safe_load(base.stdout)
    added = set(policy["public"]["exact"]) - set(before["public"]["exact"])
    expected = set() if PATH in set(before["public"]["exact"]) else {PATH}
    assert added == expected
    assert set(before["public"]["exact"]) - set(policy["public"]["exact"]) == set()
    assert policy["public"]["prefixes"] == before["public"]["prefixes"]
    assert policy.get("free_registered") == before.get("free_registered")
    assert policy.get("deny") == before.get("deny")
    assert policy.get("premium") == before.get("premium")


# ===========================================================================
# ...but NOT in the sitemap — the inverse of every other public page
# ===========================================================================
def test_unsubscribe_is_reachable_but_not_indexable():
    """Public to reach, not a page to index: it is reached only from a link in an email
    and does nothing without a signed token, so a tokenless search result is a dead end.
    Both halves are needed — a sitemap omission alone does not stop a crawl."""
    from lib import seo

    assert seo.is_public_path(PATH) is True
    assert seo._should_exclude("unsubscribe") is True


def test_the_page_carries_a_noindex_of_its_own(page):
    assert '<meta name="robots" content="noindex, nofollow">' in page


def test_it_does_not_enter_the_core_sitemap(tmp_path):
    from lib import seo

    (tmp_path / "unsubscribe.html").write_text("<html></html>")
    (tmp_path / "support.html").write_text("<html></html>")
    names = [n for n, _u, _f in seo.discover_core_pages(tmp_path)]
    assert "unsubscribe" not in names
    assert "support" in names, "the control: discovery itself still works"


def test_the_nav_was_not_touched():
    """Nav edits are ON HOLD (masterplan R6). The unsubscribe page rides the email, not
    the navigation — nobody goes looking for it."""
    nav = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    assert "unsubscribe" not in nav
