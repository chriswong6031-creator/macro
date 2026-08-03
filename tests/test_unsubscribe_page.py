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


def _page_js(text: str) -> str:
    """EVERY inline script block, head bootstrap included.

    Not ``split("<script>")[-1]``. That took only the LAST block, so the theme/lang
    bootstrap in <head> sat outside the slice a mutation check looked at — a fetch added
    there would have passed a test whose entire subject is "nothing mutates on load".
    """
    return "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", text, re.S))


def _spans(text: str, cls: str) -> list[tuple[int, int]]:
    """(start, end) of every ``<span class="{cls}">…</span>``, nesting-aware."""
    out = []
    open_tag = f'<span class="{cls}">'
    for m in re.finditer(re.escape(open_tag), text):
        i = m.end()
        depth = 1
        while depth:
            nxt = re.search(r"<span\b|</span>", text[i:])
            assert nxt, f"unclosed {open_tag}"
            i += nxt.end()
            depth += 1 if nxt.group(0) != "</span>" else -1
        out.append((m.start(), i))
    return out


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
    precedent). It has to be the CURRENT render, or the boundary lists a stale file.

    The comparison is against the page AS THE RENDER LANE SHIPS IT, so this rebuild has to
    replay the lane's whole post-processing chain — ``render.yml`` runs, in this order:

        build_site  ->  inject_data_base  ->  externalize_css  ->  optimize_assets

    Skip a link and the assert stops meaning "the page is stale" and starts meaning "a
    normalizer ran", which is the state main is always in between renders. It shipped that
    way once: the chain here was missing ``externalize_css``, so every inline ``<style>``
    over 1KB — the page's own CSS and the nav mega block, ~280 diff lines — read as
    divergence, and this test was red on main (and therefore ``ci-pack-1`` red on every PR
    in the repo) from the first render after #3743 landed.

    ``inject_wh_banner`` is the one sweep that CANNOT be replayed, and it is a live time
    bomb rather than a hypothetical: ``daily.yml`` runs it over ``site/**/*.html`` with no
    exclusion list, ``render.yml`` does not, so whether this page carries the ticker tag
    depends on which lane touched it last. Replaying it unconditionally would redden the
    test today (223 of 243 root pages, this one and /support.html included, currently ship
    without the tag); NOT handling it reddens the test the first time a daily run lands the
    tag here. So it is stripped from both sides — the treatment #3675 settled on for the
    same sweep, whose regex is imported rather than restated so the two cannot drift. It is
    a marker-guarded additive tag immediately before </body> that changes nothing else.

    Normalising the difference away instead (strip ``?v=`` stamps, ignore ``<style>`` vs
    ``<link>``) would have been the weaker fix: replaying the step keeps the externalized
    CSS compared byte-for-byte, because the href IS the content hash. What must never be
    done is re-rendering the page and committing that — ``site/`` is render-lane territory
    and a hand-render out of a worktree ships a stale-checkout clobber.

    ``make_href`` below mirrors ``scripts.externalize_css`` except that it writes nothing:
    this suite renders into tmp only and must not touch ``site/``. The lane's threshold is
    imported rather than restated so the two cannot drift apart silently.
    """
    import hashlib

    from jinja2 import Environment, FileSystemLoader

    from engine import i18n
    from lib.pages import (css_imports, externalize_css_text, inject_text,
                           optimize_assets_text, preload_css_text)
    from lib.seo import SITE_BASE
    from scripts.build_free_content import _WHB_TAG_RE
    from scripts.externalize_css import MIN_BYTES
    from scripts.optimize_assets import _hash_bytes

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip, SITE_BASE=SITE_BASE)
    fresh = inject_text(env.get_template(TEMPLATE).render(generated_utc="2026-07-26 00:00"))
    site = (ROOT / "site").resolve()

    def asset(url):
        target = (site / url.split("?", 1)[0].split("#", 1)[0]).resolve()
        target.relative_to(site)
        return target

    def hash_for(url):
        target = asset(url)
        return _hash_bytes(target) if target.is_file() else None

    def imports_for(url):
        target = asset(url)
        return css_imports(target.read_text(encoding="utf-8")) if target.is_file() else []

    lifted = {}  # href hash -> the CSS the block held, for the dangling-link check below

    def make_href(css, _index, _media):
        """scripts.externalize_css.externalize's callback, minus the write. The page ships
        at the site ROOT, so its prefix is "" (dbase_prefix); a sub-dir page would need
        "../" per level."""
        data = css.encode("utf-8")
        if len(data) < MIN_BYTES:
            return None  # left inline, exactly as the lane leaves it
        h = hashlib.sha256(data).hexdigest()[:8]
        lifted[h] = css
        return f"assets/css/{h}.css?v={h}"

    fresh = externalize_css_text(fresh, make_href)

    # The href is a content hash, so a MISSING stylesheet still compares equal below while
    # the page ships unstyled — _prune_orphans deletes any hash file no page links, and a
    # page whose site/ copy lags this template links hashes nothing else references. That
    # is the "boundary lists a stale file" failure this suite exists to catch, so name it.
    for h, css in lifted.items():
        f = site / "assets" / "css" / f"{h}.css"
        assert f.is_file(), f"page links assets/css/{h}.css but the render lane shipped no such file"
        assert f.read_text(encoding="utf-8") == css, f"assets/css/{h}.css is not the CSS this page lifted"

    fresh = preload_css_text(optimize_assets_text(fresh, hash_for), imports_for)
    shipped = (ROOT / "site" / "unsubscribe.html").read_text(encoding="utf-8")
    # the lane-dependent ticker tag, off both sides (see the docstring)
    fresh, shipped = _WHB_TAG_RE.sub("", fresh), _WHB_TAG_RE.sub("", shipped)
    assert shipped == fresh, "re-run the builder and commit site/unsubscribe.html"


def test_page_builds_with_the_house_chrome(page):
    assert page.lstrip().startswith("<!DOCTYPE html>")
    assert "<title>Unsubscribe — MastermindX</title>" in page
    assert 'href="theme.css"' in page and 'src="theme.js"' in page
    assert 'class="public-nav"' in page
    assert 'class="public-nav-links"' in page
    assert 'class="public-footer"' in page
    assert 'class="site-nav"' not in page
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
    assert "t: tok" in page and "action: action" in page


def test_nothing_mutates_on_load(page):
    """A GET that unsubscribed would silently opt out everyone whose corporate mail
    scanner follows links in inbound messages. Every request must originate in a click.

    Widened after the W4 audit found the old version proved almost none of that: it read
    only the LAST <script> block (so the head bootstrap was outside the slice), and its
    click check was a per-LINE regex for ``send('`` — defeated by ``var f = send;
    f('unsubscribe')``, by ``sendBeacon``, by ``XMLHttpRequest``, or by an ``<img>``
    beacon, none of which contain that literal at all.
    """
    js = _page_js(page)
    assert js.count("fetch(") == 1, "one request path, and it is the button's"

    # no OTHER way to reach the network, anywhere in any inline block
    for beacon in ("sendBeacon", "XMLHttpRequest", "EventSource", "WebSocket",
                   "navigator.connection", "new Image(", "import("):
        assert beacon not in js, beacon
    # ...nor an <img>/<iframe> that fetches on parse
    for tag in re.findall(r"<(?:img|iframe|object|embed)\b[^>]*>", page):
        assert "/api/" not in tag, tag

    # every CALL of send() is inside a click listener, and send is never aliased
    calls = [m for m in re.finditer(r"(?<!function )\bsend\s*\(", js)]
    assert len(calls) >= 3, "the three buttons"
    for m in calls:
        line = js[js.rfind("\n", 0, m.start()) + 1: js.find("\n", m.start())]
        assert "addEventListener('click'" in line, f"send() outside a click: {line.strip()}"
    assert not re.search(r"=\s*send\s*[;,)]", js), "send() must not be aliased past the check"
    assert js.count("function send(") == 1


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
    assert re.search(r'id="u-back"[^>]*class="btn btn-ghost"|class="btn btn-ghost"[^>]*id="u-back"',
                     page), "the way back must not be a primary button"


def test_the_ghost_button_is_actually_quieter_than_the_primary(page):
    """``".btn-ghost{" in css`` asserted the class EXISTS, not that it does anything — a
    ghost button styled identically to the primary would have passed. What the design
    requires is smaller type, no accent fill, and muted colour."""
    css = _page_css(page)
    body = re.search(r"\n\.btn-ghost\{([^}]*)\}", css).group(1)
    assert "var(--gbtn-bg)" in body, "no accent fill — the primary's gradient must be gone"
    assert "color:var(--muted)" in body
    ghost_size = float(re.search(r"font-size:([\d.]+)px", body).group(1))
    primary = re.search(r"\n\.btn\{([^}]*)\}", css).group(1)
    primary_size = float(re.search(r"font:600 ([\d.]+)px", primary).group(1))
    assert ghost_size < primary_size, (ghost_size, primary_size)


def test_the_ghost_button_stays_secondary_on_a_phone(page):
    """`.act .btn{ width:100%; order:-1; }` matches `.btn.btn-ghost` too, so at 375px the
    "turn them back on" button rendered full width ABOVE its own explanatory note, as the
    only button on screen — the loudest element on the page, on the exact surface where
    email links are opened. Desktop was correct, which is why nothing else caught it."""
    css = _page_css(page)
    mobile = re.search(r"@media \(max-width:480px\)\{(.*?)\n\}", css, re.S).group(1)
    assert ".act .btn{ width:100%; order:-1; }" in mobile
    assert ".act .btn-ghost{ width:auto; order:0; }" in mobile
    assert mobile.index(".act .btn{") < mobile.index(".act .btn-ghost{"), \
        "the override has to come after the rule it overrides"


def test_a_refused_lift_hides_the_way_back_and_explains(page):
    css = _page_css(page)
    assert 'html[data-refused="1"] .refused{ display:block; }' in css
    assert 'html[data-refused="1"] .st-off .btn-ghost{ display:none; }' in css


def test_the_way_back_needs_its_own_token_and_hides_without_one(page):
    """The footer token authorises `unsubscribe` and nothing else, so the undo is a
    capability the SERVER mints — only for the request that actually recorded the opt-out
    — and it lives in a closure, never in the URL, the DOM or an email. No token, no
    button: one that can only 400 is worse than none."""
    css = _page_css(page)
    assert 'html:not([data-undo="1"]) .st-off .btn-ghost{ display:none; }' in css
    assert "resubscribe_token" in page
    assert "action === 'resubscribe' ? UNDO : TOKEN" in page
    # The public header may persist a language preference. The resubscribe
    # capability itself must never be written anywhere that can outlive the tab.
    body = page.split("</head>", 1)[1]
    assert not re.search(
        r"(?:local|session)Storage\.(?:setItem|set)\([^)]*\bUNDO\b", body
    ), "no persistence of the undo"
    assert "textContent = UNDO" not in page and "innerHTML = UNDO" not in page


# ===========================================================================
# Bilingual (the house law)
# ===========================================================================
KEY_STRINGS = [
    ("Email settings", "邮件设置"),
    ("One click. ", "一键退订，"),
    ("No more marketing email.", "不再收到营销邮件。"),
    ("Account emails — receipts, sign-in links, support replies — keep coming either way.",
     "账户邮件——收据、登录链接、客服回复——不受影响，照常送达。"),
    ("Unsubscribe", "退订"),
    ("Nothing changes until you press it.", "在你点击之前，什么都不会改变。"),
    ("Marketing emails are off.", "营销邮件已关闭。"),
    ("Turn them back on", "重新开启"),
    ("We will not email to ask you to reconsider.", "我们不会再发邮件劝你回来。"),
    ("This link does not work.", "这个链接无法使用。"),
    ("Marketing email: off", "营销邮件：已关闭"),
    ("Marketing email: on", "营销邮件：已开启"),
]


@pytest.mark.parametrize("en,zh", KEY_STRINGS)
def test_every_key_string_ships_in_both_languages(page, en, zh):
    assert f'<span class="l-en">{en}</span>' in page, en
    assert f'<span class="l-zh">{zh}</span>' in page, zh


def test_EVERY_english_span_has_a_chinese_twin(page):
    """The generic law, not eleven hand-picked strings.

    KEY_STRINGS covers 12 of the page's ~28 dual spans, so a new EN-only string ships
    green — which is exactly how a bilingual surface goes half-English one commit at a
    time. theme.css hides the wrong half off html[data-lang], so an l-en with no adjacent
    l-zh is not a fallback: it is a line that VANISHES for every Chinese reader.
    """
    en = _spans(page, "l-en")
    zh = _spans(page, "l-zh")
    assert en, "the page is bilingual"
    assert len(en) == len(zh), (len(en), len(zh))
    zh_starts = {s for s, _e in zh}
    for start, end in en:
        assert end in zh_starts, (
            "this English span has no 中文 twin immediately after it: "
            + page[start:end][:120])


def test_the_two_aspects_of_the_state_label_are_symmetric():
    """`营销邮件：开启` against `营销邮件：已关闭` mixed a bare adjective with a perfective
    one for a matched EN pair (on/off). Both take 已."""
    on = dict(KEY_STRINGS)["Marketing email: on"]
    off = dict(KEY_STRINGS)["Marketing email: off"]
    assert on.startswith("营销邮件：已") and off.startswith("营销邮件：已")


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


def test_every_mono_micro_label_recipe_gets_the_same_hanzi_fix(page):
    """The footer column headings (产品 / 资源) use the identical 9px mono + .14em recipe
    and were left out of the fix, so they rendered through the un-pinned chain at the wide
    Latin tracking this file's own comment calls broken spacing. Same recipe, same fix."""
    css = _page_css(page)
    assert 'html[data-lang="zh"] .mx-footer .f-col p{' in css
    fix = re.search(r'html\[data-lang="zh"\] \.mx-footer \.f-col p\{([^}]*)\}', css).group(1)
    assert "PingFang SC" in fix and "letter-spacing:.04em" in fix


def test_the_address_slot_never_renders_an_empty_sentence(page):
    """`mask()` answers '' when the address cannot be resolved (a user id whose auth record
    has no address), and the slot coerced with `masked || ''` — so the page rendered "We
    stopped marketing email to ." with a hole where its object should be. The markup ships
    a dual-language fallback and the painter only overwrites it when there IS a mask."""
    assert '<b class="addr" data-addr>this address</b>' in page
    assert '<b class="addr" data-addr>这个邮箱</b>' in page
    assert "data-addr></b>" not in page, "no empty slot may survive"
    assert "if (!masked) return;" in page


# ===========================================================================
# PIN §1.1 — the state colour law, as an executable assert
# ===========================================================================
def test_success_and_error_never_use_the_direction_tokens(page):
    """--up/--down swap red<->green under html[data-lang="zh"] for the Asia convention, so
    a success panel painted with --up turns RED for every Chinese reader. --ok/--act encode
    health, never direction, and deliberately do not swap.

    Checked over the STYLE ATTRIBUTES too: the old version read only <style> blocks, so an
    inline `style="color:var(--up)"` — which wins over everything in a stylesheet — sailed
    straight through the one guard written to stop it.
    """
    css = _page_css(page)
    assert "var(--up)" not in css and "var(--down)" not in css
    assert "--up" not in css and "--down" not in css
    for value in re.findall(r'\bstyle="([^"]*)"', page):
        assert "--up" not in value and "--down" not in value, value


@pytest.mark.parametrize("selector", [
    r'html\[data-unsub="off"\]\s+\.panel\{ --accent:var\(--ok\); \}',
    r'html\[data-unsub="on"\]\s+\.panel\{ --accent:var\(--ok\); \}',
    r'html\[data-unsub="bad"\]\s+\.panel\{ --accent:var\(--act\); \}',
    r'html\[data-err="1"\]\s+\.panel\{ --accent:var\(--act\); \}',
])
def test_the_rail_carries_the_health_tokens(page, selector):
    assert re.search(selector, _page_css(page)), selector


def test_the_seal_and_the_error_bar_are_correctly_toned(page):
    css = _page_css(page)
    assert "var(--ok)" in re.search(r"\n\.seal\{([^}]*)\}", css).group(1)
    assert "var(--act)" in re.search(r"\n\.seal\.bad\{([^}]*)\}", css).group(1)
    assert "var(--act)" in re.search(r"\n\.err\{([^}]*)\}", css).group(1)


def test_an_error_keeps_the_button_the_reader_was_about_to_press(page):
    """THE PROPERTY, not the line that broke it.

    This test asserted ``html[data-unsub="error"] .st-ready{ display:block; }`` existed —
    and that line IS the bug. `error` was a data-unsub VALUE that displayed the READY step,
    so a failure overwrote whatever step the reader was on: press "Turn them back on" from
    `off`, have the server 500, and the panel flipped to the label MARKETING EMAIL: ON, the
    unsubscribe lede, and an "Unsubscribe" button — the inverse of what was attempted, next
    to a bar saying "try again", on a compliance surface.

    Failure is a separate axis now, so the assertion is structural: `error` is not a state
    at all, `data-err` never selects a step, and the bar rides above whichever step is
    already showing.
    """
    css = _page_css(page)
    assert 'data-unsub="error"' not in css, "`error` must not be a step-selecting state"
    assert "'data-unsub', 'error'" not in page, "...nor may the JS ever set it"
    assert 'html[data-err="1"] .err{ display:flex; }' in css
    # data-err selects the bar and the rail, and NOTHING that shows or hides a step
    for rule in re.findall(r'html\[data-err="1"\][^{]*\{[^}]*\}', css):
        assert ".st-" not in rule, f"the error axis must not select a step: {rule}"


def _drive(page: str, start: str, action: str, outcome: str) -> dict:
    """Run the page's own send() under node against a minimal DOM, and report the
    attributes that decide what the reader sees.

    A text assertion cannot reach this: the defect was a RUNTIME state transition, and the
    audit found it with a browser. This is the same probe, offline.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = _page_js(page).split("/* /unsubscribe.html page JS", 1)[1]
    js = js[js.index("(function"):]
    harness = f"""
    var attrs = {{'data-unsub': {json.dumps(start)}}};
    var H = {{
      setAttribute: function (k, v) {{ attrs[k] = v; }},
      removeAttribute: function (k) {{ delete attrs[k]; }},
      getAttribute: function (k) {{ return attrs[k] === undefined ? null : attrs[k]; }}
    }};
    var handlers = {{}};
    function el(id) {{
      return {{ id: id, setAttribute: function () {{}}, removeAttribute: function () {{}},
                addEventListener: function (_e, fn) {{ handlers[id] = fn; }} }};
    }}
    var nodes = {{'#u-go': el('u-go'), '#u-back': el('u-back'), '#u-off': el('u-off')}};
    global.document = {{
      documentElement: H,
      querySelector: function (s) {{ return nodes[s] || null; }},
      querySelectorAll: function () {{ return []; }},
      addEventListener: function () {{}}
    }};
    global.location = {{ search: '?t=footer-token' }};
    global.window = {{}};
    global.fetch = function () {{
      var outcome = {json.dumps(outcome)};
      if (outcome === 'throw') return Promise.reject(new Error('offline'));
      if (outcome === '500') return Promise.resolve({{ ok: false, status: 500 }});
      if (outcome === '400') return Promise.resolve({{ ok: false, status: 400 }});
      return Promise.resolve({{ ok: true, status: 200,
        json: function () {{ return Promise.resolve({{ state: 'unsubscribed',
          email_masked: 'ad\\u2022\\u2022\\u2022\\u2022\\u2022\\u2022@example.com',
          resubscribe_token: 'undo-token' }}); }} }});
    }};
    {js}
    // put the page into the starting step, then press the button under test
    H.setAttribute('data-unsub', {json.dumps(start)});
    if ({json.dumps(start)} === 'off') H.setAttribute('data-undo', '1');
    handlers[{json.dumps(action)}]();
    setTimeout(function () {{ console.log(JSON.stringify(attrs)); }}, 20);
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(harness)
        path = fh.name
    proc = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("outcome", ["500", "throw"])
def test_a_failed_resubscribe_leaves_the_reader_in_the_off_state(page, outcome):
    """THE REPRODUCTION, executed. Reader is unsubscribed (`off`), presses "Turn them back
    on", the server fails. Before the fix the page moved to `data-unsub="error"`, which
    displayed `.st-ready` — so the label said MARKETING EMAIL: ON (false), the visible
    button became `u-go` "Unsubscribe" (the opposite action), and the lede became the
    unsubscribe lede, all under "That didn't go through. Try again."
    """
    attrs = _drive(page, start="off", action="u-back", outcome=outcome)
    assert attrs["data-unsub"] == "off", "the step the reader was on must survive"
    assert attrs.get("data-err") == "1", "and the bar must say the press failed"
    assert attrs.get("data-undo") == "1", "the undo is still offered — retry means retry"


def test_a_failed_unsubscribe_also_keeps_its_own_step(page):
    """The same rule from the other direction: the ready step keeps its Unsubscribe
    button, which is what the original comment promised and only ever delivered here."""
    attrs = _drive(page, start="ready", action="u-go", outcome="500")
    assert attrs["data-unsub"] == "ready"
    assert attrs.get("data-err") == "1"


def test_a_successful_press_clears_the_error_bar(page):
    attrs = _drive(page, start="ready", action="u-go", outcome="ok")
    assert attrs["data-unsub"] == "off"
    assert "data-err" not in attrs
    assert attrs.get("data-undo") == "1", "a new opt-out may be undone by the one who made it"


def test_a_dead_token_on_the_unsubscribe_press_is_still_the_dead_link_panel(page):
    """400 means the token does not verify, and for the unsubscribe press that IS the
    dead-link story the `bad` panel exists to tell."""
    attrs = _drive(page, start="ready", action="u-go", outcome="400")
    assert attrs["data-unsub"] == "bad"


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


# The public no-account-needed surface, frozen. Widening it is a deliberate act:
# adding a line here is the review checkpoint, which is the whole point of pinning
# the set rather than diffing against a moving branch.
PUBLIC_EXACT = frozenset({
    # /about.html — the entity page (SEO_SUPERCHARGE_MASTERPLAN §0.10). Reviewed
    # public: it is prose about who we are, ships no signals, no customer data and
    # no write surface, and a crawler that has never had a session is exactly the
    # reader it exists for.
    "/about.html",
    "/", "/index.html", "/plans.html", "/macro.html", "/start.html",
    "/us_stocks.html", "/confluence_screener.html", "/research_vault.html",
    "/research_vault_app.js",
    # The two Special Situations tier-preview SHELLS (docs/TIER_PREVIEW_PATTERN.md),
    # promoted from free_registered to anonymous-public by SEO_SUPERCHARGE_MASTERPLAN
    # W1a. Reviewed public: the shell holds only the preview slice, the honest totals
    # and the upgrade wall — every paid row stays in /premiumdata/* (plus the two raw
    # snapshots in premium.enforced_early), which 403 anonymous and Free alike.
    "/special_situations.html", "/china_special_situations.html",
    "/support.html", "/unsubscribe.html",
    "/privacy.html", "/terms.html", "/disclaimer.html",
    "/favicon.svg", "/favicon.ico", "/apple-touch-icon.png",
    "/robots.txt",
    # IndexNow ownership proof (engine/marketing/indexnow.py). Reviewed public: the
    # file holds only the submission key, which the protocol requires to be publicly
    # fetchable — that fetch IS the ownership check. No signals, no user data.
    "/88bb90b05303e3cf469878ebc4dc7543.txt",
    "/sitemap.xml", "/llms.txt", "/brand-facts.json",
    # Stock Seasonality calendar clock (2026-08). Reviewed public deliberately:
    # it is a marketing/SEO surface whose page, stylesheet and script carry only
    # the seasonality sample view — no account state, no gated signal payload
    # (the data itself is served from /seasonalitydata/, gated separately).
    # Ratified here rather than only in config/site_access.yml, which is the
    # whole point of this frozen set: widening the public boundary is an
    # explicit, reviewed act, never a side effect of shipping a page.
    "/stock_seasonality.html", "/stock_seasonality.css", "/stock_seasonality.js",
    "/onboard.css", "/onboard.js", "/tier_preview.css", "/tier_preview.js",
    "/landing.css", "/scene-motion.css", "/scene-motion.js",
    "/chat.css",
    "/theme.css", "/navigation-refresh.css", "/product-nav-icons.css",
    "/logo_config.js", "/stock-logos.js", "/theme.js", "/dashboard-icons.css",
    "/dashboard-icons.js", "/chart_i18n.js", "/timemachine.js", "/tablesort.js",
    "/charts.js", "/risk_state_live.js", "/release_publications_live.js",
    "/heatmap.js", "/stocktable.js", "/globe-deck.js", "/sky.js",
    "/hub-welcome.js", "/vendor/d3-array.min.js", "/vendor/d3-geo.min.js",
    "/vendor/topojson-client.min.js", "/world-110m.json", "/account.js",
    # Ad Central Plane O split-test shim — public for the same reason theme.js is:
    # it runs on anonymous visitors before auth resolves (AD_CENTRAL_MASTERPLAN §2).
    "/adtest.js",
    "/nav_market.js", "/supabase.js", "/data_base.js", "/live.js", "/live_config.js",
    "/live/quotes.json", "/live/breadth.json",
    # Official agency event lifecycle/facts; no signal, portfolio or user data.
    "/live/release_publications.json",
    "/prophet/showcase.json",
    "/seasonalitydata/methodology.json",
    # Stock seasonality calendar clock — public BY DECISION (design-spec §10), not
    # as a side effect. The payload carries no forecast, no score and no
    # cross-symbol ordering: it is computed calendar statistics over public
    # split/dividend-adjusted price history, shipped with the selection accounting
    # that prices them, alongside the methodology manifest above that has described
    # exactly this since the foundation landed.
    #
    # TWO exact entries and no prefix, deliberately: the ~220 per-symbol entity
    # files are gitignored and served from Cloudflare R2, so they never pass
    # through Caddy at all. index.json is the covered-symbol catalog; the SPY
    # entity is the one committed panel, kept so the page has an honest first paint
    # without R2. If a THIRD /seasonalitydata/ path ever shows up in this diff, the
    # gitignore/R2 split has broken — that is the finding, not the frozen set.
    "/seasonalitydata/index.json",
    "/seasonalitydata/entities/SPY.json",
    "/factordata/tech_lab.json",
})

# Paid payload trees. A regression that lists one of these publicly is the failure
# this guard exists to catch, so name them rather than inferring them.
# /factordata/ is NOT blanket-private: /factordata/tech_events/ and the tech_lab.json
# carve-out are deliberate and predate this program, so only the tree root is barred.
NEVER_PUBLIC = ("/labdata/", "/premiumdata/")
PUBLIC_PREFIXES = frozenset({
    # /assets/js/ is the JS twin of /assets/css/: content-hashed page scripts
    # that scripts/externalize_css.py lifts out of `<script data-externalize>`
    # blocks. Derived presentation code with no signal payload — the render-time
    # DATA those scripts read stays inline in the (gated) HTML by construction,
    # which is why the lift is opt-in per block rather than automatic.
    "/assets/css/", "/assets/js/", "/assets/landing/", "/factordata/tech_events/",
    "/stocks/", "/products/", "/tools/", "/learn/", "/blog/", "/research/", "/fonts/",
})


def test_nothing_else_became_public_as_a_side_effect():
    """The public boundary is exactly the frozen set — no more, no less.

    This deliberately does NOT diff against origin/main. A relative assertion is
    self-invalidating: the moment it merges, the diff it measures is empty and the
    test can never fail again (it went red on main that way once already).
    """
    import yaml

    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
    exact = set(policy["public"]["exact"])

    assert PATH in exact, "the unsubscribe page must stay reachable without an account"
    unexpected = exact - PUBLIC_EXACT
    assert not unexpected, f"these paths became public without updating the frozen set: {sorted(unexpected)}"
    missing = PUBLIC_EXACT - exact
    assert not missing, f"these public paths disappeared: {sorted(missing)}"

    prefixes = set(policy["public"].get("prefixes", []))
    assert prefixes == PUBLIC_PREFIXES, (
        "the public prefix list moved; widen the frozen set deliberately. "
        f"added={sorted(prefixes - PUBLIC_PREFIXES)} removed={sorted(PUBLIC_PREFIXES - prefixes)}")

    for tree in NEVER_PUBLIC:
        leaked = [p for p in prefixes if p.startswith(tree)] + [p for p in exact if p.startswith(tree)]
        assert not leaked, f"paid payload tree published publicly: {leaked}"


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
