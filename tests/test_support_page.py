"""tests/test_support_page.py — /support.html (SEE W2 public support desk).

The page is a PINNED design (mockups/support_email/PIN.md + support_page.html), so this
suite guards the properties a later edit could quietly break without anything else going
red — the ones that are invisible in a screenshot:

  * the API contract: the form POSTs the exact seven fields app/support.py validates, to
    the exact route it serves;
  * the abuse hardening: the honeypot exists, is off-screen, unfocusable and un-autofilled
    — and is NOT merely `display:none`, which some bots and some password managers skip;
  * t0 is stamped at render, or the API's time-to-fill gate has nothing to measure;
  * bilingual dual-spans for every user-visible string, and NO translated text in a
    `title=` attribute (l-en/l-zh cannot operate inside an attribute);
  * PIN §1.1, as an executable assert: success/error use --ok/--act and NEVER --up/--down,
    because theme.css swaps those two under html[data-lang="zh"] for the Asia red-up
    convention — a success panel painted with --up turns RED for every Chinese reader.

Renders into tmp_path only; nothing here writes to site/ or data/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEMPLATE = "support.html.j2"


@pytest.fixture(scope="module")
def page(tmp_path_factory) -> str:
    """The page as it ships, rendered into a throwaway dir.

    The Jinja environment is constructed exactly as scripts/build_site.main() does, and
    the output goes through lib.pages.inject_text — the shim half of write_page — so the
    string under test is byte-for-byte what build_support_page writes. Importing
    build_site itself would drag plotly and the whole engine into a suite that is
    otherwise pure-stdlib, and would give this module a way to write into site/; the
    wiring it would have proved is asserted statically in
    test_build_site_wires_the_page_through_write_page instead.
    """
    from engine import i18n
    from lib.pages import inject_text
    from lib.seo import SITE_BASE

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip, SITE_BASE=SITE_BASE)
    html = inject_text(env.get_template(TEMPLATE).render(generated_utc="2026-07-26 00:00"))
    out = tmp_path_factory.mktemp("site") / "support.html"
    out.write_text(html, encoding="utf-8")
    return html


def test_build_site_wires_the_page_through_write_page():
    """One function per page, called from main(), written through write_page.

    write_page and not write_text: a raw write drops the data-base shim whenever the
    builder runs standalone, which silently regresses the R2 rerouting (lib/pages.py).
    """
    src = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    assert "def build_support_page(env: Environment, site: Path, generated: str) -> None:" in src
    assert 'write_page(site / "support.html", html)' in src
    assert "        build_support_page(env, site, generated)\n" in src, "main() must call it"


# ===========================================================================
# It builds, and it is a real page
# ===========================================================================
def test_page_builds_with_the_house_chrome(page):
    assert page.lstrip().startswith("<!DOCTYPE html>")
    assert "<title>Support — Mastermind</title>" in page
    assert 'href="theme.css"' in page and 'src="theme.js"' in page
    assert 'class="site-nav"' in page and 'class="nav-links"' in page   # _site_nav include
    assert "data-dbase" in page, "write_page must inject the data-base shim"
    assert 'rel="canonical" href="https://www.mastermind-x.com/support.html"' in page


def test_no_external_asset_dependencies(page):
    """China blocks the Google CDN — every font and SDK on this estate is vendored."""
    for host in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net",
                 "unpkg.com", "cdnjs.cloudflare.com", "ajax.googleapis.com"):
        assert host not in page, host
    remote = re.findall(r'(?:src|href)="(https?://[^"]+)"', page)
    allowed = ("https://www.mastermind-x.com", "https://app.mastermind-x.com",
               "https://bot.mastermind-x.com")
    for url in remote:
        assert url.startswith(allowed), url


# ===========================================================================
# The API contract (app/support.py)
# ===========================================================================
def test_form_posts_the_pinned_contract_to_the_real_route(page):
    assert "'/api/support/ticket'" in page
    # the seven fields TicketRequest declares, built in one payload literal
    payload = re.search(r"var payload = \{(.*?)\};", page, re.S)
    assert payload, "the submit payload should be one literal, not scattered assignments"
    keys = set(re.findall(r"^\s*(\w+):", payload.group(1), re.M))
    assert keys == {"email", "topic", "subject", "message", "lang", "website", "t0"}


def test_topic_values_match_the_db_check_constraint(page):
    from app import support
    values = set(re.findall(r'<option value="([a-z]+)"', page))
    assert values == set(support.TOPICS)


def test_t0_is_stamped_at_render(page):
    """app/support.py's MIN_FILL_MS gate measures against this; an absent t0 disarms it."""
    assert "var T0 = Date.now();" in page
    assert "t0: T0" in page


def test_bearer_token_is_attached_when_a_session_exists(page):
    """Signed-in submissions must carry the token — the API replaces the client-sent
    address with the verified one and attaches the real user_id and tier snapshot."""
    assert "MDXAuth.client()" in page and "auth.getSession()" in page
    assert "'Bearer ' + tok" in page


def test_rate_limit_gets_its_own_honest_message(page):
    """A 429 is not a connection problem, so it must not say 'check your connection'."""
    assert "r.status === 429" in page
    assert "fail('rate')" in page
    assert 'class="e-rate"' in page and 'class="e-generic"' in page


# ===========================================================================
# Abuse hardening (masterplan R2)
# ===========================================================================
def test_honeypot_is_present_offscreen_and_unfocusable(page):
    field = re.search(r'<input id="s-website"[^>]*>', page)
    assert field, "the honeypot input must exist"
    assert 'name="website"' in field.group(0)
    assert 'tabindex="-1"' in field.group(0)
    assert 'autocomplete="off"' in field.group(0)

    css = re.search(r"\.hp\{([^}]*)\}", page)
    assert css, "the honeypot needs its own off-screen rule"
    rule = " ".join(css.group(1).split())
    assert "left:-9999px" in rule
    # display:none alone is the trap bots learned to skip.
    assert "display:none" not in rule


# ===========================================================================
# Bilingual (G5)
# ===========================================================================
KEY_STRINGS = [
    ("Support", "支持"),
    ("Write once. ", "一次写清，"),
    ("Get a real answer.", "真人回复。"),
    ("Support replies by email — usually within one business day.",
     "我们通过邮件回复——通常在一个工作日内。"),
    ("New request", "新建请求"),
    ("Received", "已收到"),
    ("Your email", "你的邮箱"),
    ("Signed in as", "当前登录"),
    ("Topic", "问题类型"),
    ("Subject", "主题"),
    ("Message", "内容"),
    ("Send request", "发送请求"),
    ("Request received.", "已收到你的请求。"),
    ("Write another request", "再写一条请求"),
    ("What happens next", "接下来会发生什么"),
    ("Faster than writing", "比写信更快"),
]


@pytest.mark.parametrize("en,zh", KEY_STRINGS)
def test_every_key_string_ships_in_both_languages(page, en, zh):
    assert f'<span class="l-en">{en}</span>' in page, en
    assert f'<span class="l-zh">{zh}</span>' in page, zh


def test_placeholders_use_the_attribute_contract_not_spans(page):
    """A dual-language <span> inside an attribute prints as literal markup."""
    for en, zh in (("One line — what is this about?", "一句话说明这是什么问题"),
                   ("Write it however you like.", "怎么写都可以。")):
        assert f'data-ph-en="{en}"' in page
        assert f'data-ph-zh="{zh}"' in page
    assert 'placeholder="<span' not in page


def test_option_labels_are_painted_from_data_attributes(page):
    """<option> text cannot hold l-en/l-zh spans, so the pin paints it from data-en/zh."""
    assert 'data-zh="账单与付款"' in page and 'data-en="Billing &amp; payments"' in page
    assert "o.getAttribute(zh() ? 'data-zh' : 'data-en')" in page


def test_no_translated_text_in_title_attributes(page):
    """CI-guarded house law: l-en/l-zh cannot operate inside an attribute."""
    cjk = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]")
    for value in re.findall(r'\btitle="([^"]*)"', page):
        assert not cjk.search(value), value


def test_langchange_is_listened_for_on_document(page):
    """theme.js dispatches langchange on DOCUMENT and it does not bubble, so a window
    listener would silently never fire and the page would keep the boot language."""
    assert "document.addEventListener('langchange'" in page
    assert "window.addEventListener('langchange'" not in page


# ===========================================================================
# PIN §1.1 — the state colour law, as an executable assert
# ===========================================================================
def _page_css(text: str) -> str:
    """Only the page's own <style> blocks (theme.js/theme.css are linked, not inlined)."""
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S))


def test_success_and_error_never_use_the_direction_tokens(page):
    """--up/--down swap red<->green under html[data-lang="zh"] for the Asia convention, so
    a success panel painted with --up turns RED for every Chinese reader. --ok/--act encode
    health, never direction, and deliberately do not swap."""
    css = _page_css(page)
    assert "var(--up)" not in css and "var(--down)" not in css
    assert "--up" not in css and "--down" not in css


@pytest.mark.parametrize("selector,token", [
    (r'html\[data-form="success"\] \.ticket\{ --accent:var\(--ok\); \}', "--ok"),
    (r'html\[data-form="error"\]   \.ticket\{ --accent:var\(--act\); \}', "--act"),
])
def test_the_rail_carries_the_health_tokens(page, selector, token):
    assert re.search(selector, _page_css(page)), selector


def test_success_seal_and_ticket_ref_are_ok_toned(page):
    css = _page_css(page)
    seal = re.search(r"\.tk-done \.seal\{([^}]*)\}", css).group(1)
    assert "var(--ok)" in seal
    ref = re.search(r"\.slip \.v\.big\{([^}]*)\}", css).group(1)
    assert "var(--ok)" in ref


def test_error_bar_is_act_toned(page):
    css = _page_css(page)
    err = re.search(r"\n\.err\{([^}]*)\}", css).group(1)
    assert "var(--act)" in err


# ===========================================================================
# The pinned behaviour that is content, not decoration (PIN §4.3)
# ===========================================================================
def test_every_topic_carries_its_what_to_include_line(page):
    from app import support
    hint = re.search(r"var HINT = \{(.*?)\n  \};", page, re.S).group(1)
    for topic in support.TOPICS:
        assert re.search(rf"\b{topic}:\s*\[", hint), topic


def test_the_ref_is_stamped_once_never_printed_twice(page):
    """Design doctrine Law 4: on success the header ref HIDES and the real number lands in
    the slip below at full size."""
    css = _page_css(page)
    assert 'html[data-form="success"] .tk-ref{ display:none; }' in css
    assert "'MX-' + hex" in page


def test_signed_in_state_prefills_and_locks_the_address(page):
    assert "emailEl.readOnly = true" in page
    assert 'H.setAttribute(\'data-auth\', \'in\')' in page
    assert 'html[data-auth="in"]  .auth-out{ display:none; }' in _page_css(page)


def test_the_identity_pill_claims_only_what_is_true(page):
    """The pin's word for this pill was "Verified". Supabase email confirmation is not
    switched on yet (masterplan §6 step 5 schedules it), so the pill says what the product
    actually knows — this is the address on the signed-in account — and the CI grep gate on
    earned claims stays green for the right reason rather than via an allowlist entry that
    could cite no artifact."""
    assert '<span class="l-en">Account</span>' in page
    assert '<span class="l-zh">账户</span>' in page
    assert "已验证" not in page


# ===========================================================================
# Entry points (masterplan R6 — funnel, not nav)
# ===========================================================================
def test_landing_footer_and_plans_page_link_to_support():
    landing = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert '<a href="support.html" data-zh="支持">Support</a>' in landing
    # plain-copy pair: the site copy must move with the template (CI-guarded)
    assert '<a href="support.html" data-zh="支持">Support</a>' in (
        ROOT / "site" / "index.html").read_text(encoding="utf-8")

    plans = (ROOT / "templates" / "plans.html.j2").read_text(encoding="utf-8")
    assert 'href="support.html"' in plans


def test_the_nav_was_not_touched():
    """Main-nav edits are ON HOLD (masterplan R6): support rides the funnel."""
    nav = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    assert "support.html" not in nav


# ===========================================================================
# The serving boundary (G6) — the page is worthless if it 302s to sign-in
# ===========================================================================
def test_support_is_public_in_all_three_places():
    import yaml
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    assert "/support.html" in policy["public"]["exact"]

    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    # both live matchers AND both handle_errors mirrors, or a gate-upstream blip
    # redirects the one page a stuck visitor needs.
    assert caddy.count("/support.html") == 6

    from app import regwall
    assert "/support.html" in regwall.PUBLIC_PATHS
    assert regwall._is_public("/support.html") is True


def test_support_enters_the_sitemap(tmp_path):
    from lib import seo
    assert seo.is_public_path("/support.html") is True
    assert not seo._should_exclude("support")
    (tmp_path / "support.html").write_text("<html></html>")
    names = [n for n, _u, _f in seo.discover_core_pages(tmp_path)]
    assert "support" in names
