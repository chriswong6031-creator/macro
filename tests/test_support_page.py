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
    assert "<title>Support — MastermindX</title>" in page
    assert 'href="theme.css"' in page and 'src="theme.js"' in page
    assert 'class="public-nav"' in page
    assert 'class="public-nav-links"' in page
    assert 'class="public-footer"' in page
    assert 'class="site-nav"' not in page
    assert "data-dbase" in page, "write_page must inject the data-base shim"
    assert 'rel="canonical" href="https://www.mastermind-x.com/support.html"' in page


def test_support_shortcuts_prioritize_product_discovery(page):
    assert 'href="products/index.html"' in page
    assert "Explore the platform" in page
    assert 'href="methodology.html"' not in page


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
def _honeypot(page: str) -> str:
    """The honeypot block: the .hp wrapper plus its label and input."""
    m = re.search(r'<div class="hp"[^>]*>(.*?)</div>', page, re.S)
    assert m, "the honeypot block must exist"
    return m.group(0)


def test_honeypot_is_present_offscreen_and_unfocusable(page):
    hp = _honeypot(page)
    field = re.search(r"<input [^>]*>", hp)
    assert field, "the honeypot input must exist"
    assert 'tabindex="-1"' in field.group(0)
    assert 'autocomplete="off"' in field.group(0)
    assert 'aria-hidden="true"' in field.group(0)

    css = re.search(r"\.hp\{([^}]*)\}", page)
    assert css, "the honeypot needs its own off-screen rule"
    rule = " ".join(css.group(1).split())
    assert "left:-9999px" in rule
    # display:none alone is the trap bots learned to skip.
    assert "display:none" not in rule


# The tokens Chrome and every password manager key their autofill heuristics on. The
# honeypot used to be id/name/label = "website" — all three — which is precisely the
# shape they target, and `autocomplete="off"` is advisory in Chrome. A browser-filled
# honeypot is the worst failure this page has: app/support.py answers a tripped one with
# 200 + a throwaway uuid, so the person sees a success slip whose ref matches no row and
# never hears back.
_AUTOFILL_MAGNETS = ("website", "url", "homepage", "organization", "organisation",
                     "company", "address", "email", "phone", "tel", "name", "user")


def test_the_honeypot_is_named_something_autofill_never_targets(page):
    hp = _honeypot(page)
    ident = " ".join(re.findall(r'\b(?:id|name|for)="([^"]*)"', hp)).lower()
    assert ident.strip(), "the honeypot must still carry an id/name"
    label = re.search(r"<label[^>]*>(.*?)</label>", hp, re.S)
    text = (ident + " " + (label.group(1) if label else "")).lower()
    for token in _AUTOFILL_MAGNETS:
        assert token not in text, f"honeypot id/name/label contains the autofill magnet {token!r}"


def test_the_honeypot_still_files_under_the_servers_key(page):
    """Renaming the FIELD must not rename the CONTRACT. app/support.py reads `website`
    from the JSON body; the page reads the element by id and names the key itself."""
    from app import support
    assert "website" in support.TicketRequest.model_fields
    hp_id = re.search(r'<div class="hp".*?<input id="([^"]+)"', page, re.S)
    assert hp_id, "the honeypot input needs an id — the JS reads it by id"
    assert f"var hpEl = $('#{hp_id.group(1)}');" in page
    assert "website: hpEl ? hpEl.value : ''" in page


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


def test_the_ref_derivation_matches_ticket_ref(page):
    """The success slip and the ack email's subject print the SAME number, from two
    independent implementations of it — app/support.py::ticket_ref and this page's JS.
    Nothing else in the estate compares them, so a change to either alone would ship a
    page whose ref finds nothing in the inbox or the admin console.

    Both constants are pinned here, so an edit to one side without the other goes red.
    (tests/test_support_page_js.py runs the two against the same uuids under node.)"""
    from app import support

    js = re.search(r"var hex = String\(([^;]*?)\)"
                   r"\.replace\(/-/g, ''\)\.slice\(0, (\d+)\)\.toUpperCase\(\);", page)
    assert js, "the page's ref derivation is not in its pinned form"
    assert int(js.group(2)) == 8
    assert "'MX-' + hex" in page
    # …and the python side, on the same constants
    assert support.ticket_ref("7f3a2b91-1111-4000-8000-000000000001") == "MX-7F3A2B91"


# ===========================================================================
# One request per submit (review B1)
# ===========================================================================
def test_a_busy_latch_guards_re_entry_not_just_pointer_events(page):
    """`pointer-events:none` suppresses MOUSE hit-testing and nothing else: it does not
    stop Space/Enter on the focused button, and it does not stop implicit submission from
    Enter in a text field. Three submits during one in-flight request meant three POSTs,
    three ticket rows, three operator alerts and three ack emails carrying three different
    numbers — and each has its own real idem_key, so the email_log ledger cannot dedupe
    them. The guard has to be a latch in the handler plus a disabled button."""
    assert "var busy = false;" in page
    assert "if (busy) return;" in page
    assert "btn.disabled = !!on;" in page
    # cleared on BOTH exits: the tail .then runs after .catch, so failure re-arms too
    assert page.count("setBusy(true)") == 1 and page.count("setBusy(false)") == 1
    assert re.search(r"\}\)\.catch\(function \(\) \{.*?\}\)\.then\(function \(\) \{"
                     r".*?setBusy\(false\);", page, re.S), "the latch must clear after .catch"


# ===========================================================================
# The page must work when auth does not (review B2)
# ===========================================================================
def test_auth_is_skipped_without_a_session_and_time_capped_with_one(page):
    """This is the page app/regwall.py exists to keep reachable for "the people who most
    need it — the ones who cannot sign in". MDXAuth.client() loads the Supabase SDK and
    getSession() can refresh against *.supabase.co, the exact host a visitor behind the
    GFW cannot reach; a blackholed SYN does not error, it hangs. So an anonymous visitor
    must never touch it, and a signed-in one must never wait on it forever."""
    # hasSession() is a cookie probe with no network (templates/theme.js)
    assert "if (window.MDXAuth.hasSession && !window.MDXAuth.hasSession()) return Promise.resolve(h);" in page
    assert "Promise.race([live, capped])" in page
    cap = re.search(r"var AUTH_MS = (\d+);", page)
    assert cap and 500 <= int(cap.group(1)) <= 5000, "the auth cap must exist and be short"


def test_the_submit_fetch_can_be_aborted(page):
    """A hung POST has to end in the error bar, not in a permanently dimmed button."""
    assert "new window.AbortController()" in page
    assert "opt.signal = ctl.signal;" in page
    ms = re.search(r"var POST_MS = (\d+);", page)
    assert ms and 3000 <= int(ms.group(1)) <= 60000
    assert "ctl.abort()" in page


# ===========================================================================
# The page must not promise mail it cannot send (review B3 ruling)
# ===========================================================================
def test_the_slip_prints_the_servers_utc_stamp_never_an_unlabelled_clock(page):
    """The page slip printed local time with no zone while the email slip printed UTC —
    one ticket, two contradicting readings, and the unlabelled one is the page's."""
    assert "sent.textContent = (res && res.sent) || localStamp();" in page
    # the fallback names its zone rather than lying by omission
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in page
    assert "(zone ? ' ' + zone : '')" in page


def test_the_success_copy_has_both_mail_states_and_defaults_to_the_honest_one(page):
    """The estate ships dark (no SMTP credentials yet, docs/ops/email-support-setup.md)
    and the sends are deferred, so the response cannot know a disposition — only whether
    a relay exists. Unknown must render the copy that promises nothing."""
    css = _page_css(page)
    assert ".m-on{ display:none; }" in css                       # default: no promise
    assert 'html[data-mail="on"] .m-on{ display:inline; }' in css
    assert 'html[data-mail="on"] .m-off{ display:none; }' in css
    assert "H.setAttribute('data-mail', (res && res.mail === true) ? 'on' : 'off');" in page

    off = re.findall(r'<span class="m-off">(.*?)</span>\s*</(?:p|span)>', page, re.S)
    assert len(off) == 2, f"expected the slip line and the after-note, got {len(off)}"
    blob = " ".join(off)
    # not a vacuous match: the real copy has to be what we just scanned
    assert "We will reply to" in blob and "Need to add something?" in blob
    assert "我们会回复到" in blob and "需要补充信息？" in blob
    for banned in ("emailed", "Check spam", "垃圾箱", "副本"):
        assert banned not in blob, f"the mail-off copy must not say {banned!r}"


@pytest.mark.parametrize("en,zh", [
    ("We will reply to ", "我们会回复到 "),
    ("Need to add something? Write to ", "需要补充信息？请发邮件至 "),
])
def test_the_mail_off_copy_ships_in_both_languages(page, en, zh):
    assert en in page and zh in page


def test_what_happens_next_is_true_in_both_mail_states(page):
    """That list renders BEFORE any submit, so the page cannot yet know whether mail is
    switched on — which means every line in it has to hold either way. It used to promise
    an email with a ticket number and a reply to that email; the number is stamped on the
    slip regardless, and the address is how we answer regardless."""
    block = re.search(r'<div class="next">(.*?)</div>', page, re.S)
    assert block, "the 'what happens next' rail must exist"
    items = block.group(1)
    for promise in ("email", "邮件"):
        assert promise not in items, f"the pre-submit rail must not promise {promise!r}"
    assert "ticket number" in items and "工单号" in items


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
def _matcher_body(caddy: str, name: str) -> str:
    """The body of the `@name { … }` matcher DEFINITION (not the `handle @name {` block).

    Anchored at line start so `handle @reg_html {` cannot be mistaken for the definition;
    matcher blocks contain no nested braces, so the first dedented `}` closes them.
    """
    m = re.search(rf"^[ \t]*@{name}\s*\{{(.*?)\n[ \t]*\}}", caddy, re.S | re.M)
    assert m, f"@{name} is not defined in the Caddyfile"
    return m.group(1)


def _directive(body: str, name: str) -> list[str]:
    """The tokens of a `<name> …` line inside a matcher body ('path' / 'not path')."""
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if line.startswith(name + " "):
            return line[len(name):].split()
    return []


# Which list of which matcher /support.html has to appear in, and why. A bare
# `count(...) == 6` was green for all of these AND for the mutation that moves an
# occurrence out of @gate_html and into @never_site — which would 404 the page while the
# arithmetic still balanced.
CADDY_BOUNDARY = [
    # matcher,        directive,  what it means
    ("reg_html",      "not path", "exempt from the registration wall"),
    ("reg_asset",     "not path", "exempt from the asset wall"),
    ("gate_html",     "path",     "inside the public funnel"),
    ("reg_html_err",  "not path", "still exempt when the gate upstream is down"),
    ("reg_asset_err", "not path", "still exempt when the gate upstream is down"),
    ("gate_html_err", "path",     "still served when the gate upstream is down"),
]


@pytest.mark.parametrize("matcher,directive,why", CADDY_BOUNDARY)
def test_support_is_public_in_every_caddy_matcher_by_name(matcher, directive, why):
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    tokens = _directive(_matcher_body(caddy, matcher), directive)
    assert tokens, f"@{matcher} has no `{directive}` line"
    assert "/support.html" in tokens, f"@{matcher} must list /support.html — {why}"


def test_support_is_never_404ed_as_an_internal_preview():
    """@never_site respond 404s outright. An occurrence relocated here reads as 'still
    six mentions' to a counting test and as 'page does not exist' to a visitor."""
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    assert "/support.html" not in _directive(_matcher_body(caddy, "never_site"), "path")


def test_support_is_public_in_all_three_places():
    import yaml
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    assert "/support.html" in policy["public"]["exact"]

    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    # The six named above and NOWHERE else — the per-matcher tests prove each one is
    # present; this proves a seventh has not appeared somewhere nobody reviewed.
    #
    # `redir` lines are counted SEPARATELY, not waived: a redirect TARGET is not a
    # boundary matcher (it decides where /support goes, not who may read it), but an
    # unreviewed redirect is still a way to move the page, so the alias set is pinned
    # by name below. Bumping the matcher count to absorb a redirect would blind the
    # arithmetic to the relocation this guard exists to catch.
    redir_lines = [l.strip() for l in caddy.splitlines()
                   if l.strip().startswith("redir ") and "/support.html" in l]
    assert redir_lines == ["redir /support /support.html 301"], redir_lines
    matcher_mentions = sum(
        l.count("/support.html") for l in caddy.splitlines()
        if not l.strip().startswith("redir ")
    )
    assert matcher_mentions == len(CADDY_BOUNDARY)

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
