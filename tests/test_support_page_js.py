"""tests/test_support_page_js.py — /support.html's page JS, actually executed (SEE W2 review).

tests/test_support_page.py reads the page as text. That is the right tool for a pinned
design and the wrong one for the three defects the W2 review found, every one of which is
a BEHAVIOUR:

  * B1 — one request per submit. The old guard was `aria-busy` plus a CSS
    `pointer-events:none`, which suppresses mouse hit-testing and nothing else. Three
    submits during one in-flight request produced three POSTs → three ticket rows, three
    operator alerts, and three acknowledgment emails carrying three DIFFERENT numbers to
    one person. The mailer's email_log cannot dedupe those: each has its own real
    idem_key. Only running the handler proves the latch holds.
  * B2 — the page must work when auth does not. An anonymous visitor must never touch the
    Supabase SDK, and a session that hangs (a blackholed *.supabase.co SYN does not error,
    it waits) must not strand the submit.
  * B3 — the success copy must follow the API's `mail` flag, in both directions.

Plus the one string that MUST match between two independent implementations: the page's
ref derivation against app/support.py::ticket_ref, run on the same uuids.

The page's own inline <script> is extracted from the rendered page and executed unmodified
against tests/fixtures/support_dom_shim.js. What the shim cannot model — implicit
submission from Enter in a text field, keyboard activation of a focused button, and CSS —
is verified in a real browser and posted in the PR. Node ships on CI and dev Macs; the
suite skips loudly when it is absent (mirrors tests/test_risk_core_js.py).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHIM = ROOT / "tests" / "fixtures" / "support_dom_shim.js"

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

TID = "7f3a2b91-1111-4000-8000-000000000001"
FILLED = ("DOM.nodes['#s-email'].value = 'ada@example.com';"
          "DOM.nodes['#s-subject'].value = 'Card declined';"
          "DOM.nodes['#s-message'].value = 'my card was declined at checkout';")


@pytest.fixture(scope="module")
def page() -> str:
    """The page as it ships — the same render tests/test_support_page.py asserts on."""
    from jinja2 import Environment, FileSystemLoader

    from engine import i18n
    from lib.pages import inject_text
    from lib.seo import SITE_BASE

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip, SITE_BASE=SITE_BASE)
    return inject_text(env.get_template("support.html.j2").render(generated_utc="2026-07-26 00:00"))


@pytest.fixture(scope="module")
def page_js(page: str) -> str:
    """The page's own submit/auth/paint IIFE — the LAST inline <script> on the page."""
    blocks = re.findall(r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", page, re.S)
    assert blocks, "the page must carry an inline script"
    js = blocks[-1]
    assert "/api/support/ticket" in js, "the last inline script should be the page JS"
    return js


@pytest.fixture(scope="module")
def hp_id(page: str) -> str:
    """The honeypot's element id, read off the page so a rename cannot silently no-op."""
    m = re.search(r'<div class="hp".*?<input id="([^"]+)"', page, re.S)
    assert m, "the honeypot input must have an id"
    return "#" + m.group(1)


def _run(page_js: str, body: str, opts: dict, tmp_path: Path, timeout: int = 30) -> dict:
    """Install the shim, run the page's real JS against it, then run `body`; parse stdout."""
    script = textwrap.dedent(
        """
        var SHIM = require(%(shim)s);
        var DOM = SHIM.install(%(opts)s);
        function OUT(o){ process.stdout.write(JSON.stringify(o)); }
        %(page)s
        %(body)s
        """
    ) % {"shim": json.dumps(str(SHIM)), "opts": json.dumps(opts),
         "page": page_js, "body": body}
    f = tmp_path / "run.js"
    f.write_text(script, encoding="utf-8")
    res = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=timeout)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


def _ok_body(**extra) -> str:
    payload = {"ok": True, "ticket_id": TID}
    payload.update(extra)
    return payload


# ===========================================================================
# B1 — one request per submit
# ===========================================================================
@needs_node
@pytest.mark.parametrize("fires", [2, 3, 6])
def test_submitting_repeatedly_while_in_flight_sends_exactly_one_post(page_js, hp_id, tmp_path, fires):
    """The reviewer's reproduction, as a test: N submits during one in-flight request."""
    out = _run(
        page_js,
        FILLED
        + "var f = DOM.nodes['#tk-form'];"
        + f"for (var i = 0; i < {fires}; i++) f.fire('submit');"
        + "setTimeout(function(){ OUT({posts: DOM.fetches.length,"
        "  refs: DOM.fetches.map(function(x){return x.body.subject;}),"
        "  form: DOM.html.getAttribute('data-form')}); }, 300);",
        {"hp": hp_id, "fetchDelay": 120},
        tmp_path,
    )
    assert out["posts"] == 1, f"{fires} submits produced {out['posts']} POSTs"
    assert out["form"] == "success"


@needs_node
def test_the_latch_re_arms_after_a_success(page_js, hp_id, tmp_path):
    """One ticket per submit, not one ticket per page load: 'Write another request' has to
    leave the form usable."""
    out = _run(
        page_js,
        FILLED
        + "var f = DOM.nodes['#tk-form'];"
        "f.fire('submit');"
        "setTimeout(function(){"
        "  DOM.nodes['#s-again'].fire('click');"
        + FILLED +
        "  f.fire('submit');"
        "  setTimeout(function(){ OUT({posts: DOM.fetches.length,"
        "    form: DOM.html.getAttribute('data-form')}); }, 200);"
        "}, 200);",
        {"hp": hp_id, "fetchDelay": 40},
        tmp_path,
    )
    assert out["posts"] == 2
    assert out["form"] == "success"


@needs_node
def test_the_latch_re_arms_after_a_failure(page_js, hp_id, tmp_path):
    """Cleared on BOTH exits. A failed submit that leaves the button dead is a lost
    customer on the page they came to when everything else was already broken."""
    out = _run(
        page_js,
        FILLED
        + "var f = DOM.nodes['#tk-form'];"
        "f.fire('submit');"
        "setTimeout(function(){"
        "  f.fire('submit');"
        "  setTimeout(function(){ OUT({posts: DOM.fetches.length,"
        "    form: DOM.html.getAttribute('data-form'),"
        "    disabled: DOM.nodes['#s-send'].disabled}); }, 200);"
        "}, 200);",
        {"hp": hp_id, "fetchDelay": 40, "fail_all": True},
        tmp_path,
    )
    assert out["posts"] == 2, "a failed submit must leave the form usable"
    assert out["form"] == "error"
    assert out["disabled"] is False


@needs_node
def test_the_button_is_disabled_while_in_flight_not_merely_dimmed(page_js, hp_id, tmp_path):
    """`disabled` is what the HTML spec makes a hard stop for implicit submission — a form
    whose default button is disabled is not submitted at all."""
    out = _run(
        page_js,
        FILLED
        + "var b = DOM.nodes['#s-send'];"
        "DOM.nodes['#tk-form'].fire('submit');"
        "var during = {disabled: b.disabled, busy: b.getAttribute('aria-busy')};"
        "setTimeout(function(){ OUT({during: during,"
        "  after: {disabled: b.disabled, busy: b.getAttribute('aria-busy')}}); }, 250);",
        {"hp": hp_id, "fetchDelay": 60},
        tmp_path,
    )
    assert out["during"] == {"disabled": True, "busy": "true"}
    assert out["after"] == {"disabled": False, "busy": None}


@needs_node
def test_a_submit_that_fails_validation_never_latches(page_js, hp_id, tmp_path):
    """The latch is set AFTER validate(), or a typo in the email would freeze the form."""
    out = _run(
        page_js,
        "DOM.nodes['#s-email'].value = 'not-an-email';"
        "DOM.nodes['#s-subject'].value = 's';"
        "DOM.nodes['#s-message'].value = 'm';"
        "var f = DOM.nodes['#tk-form'];"
        "f.fire('submit');"
        + FILLED +
        "f.fire('submit');"
        "setTimeout(function(){ OUT({posts: DOM.fetches.length}); }, 200);",
        {"hp": hp_id, "fetchDelay": 20},
        tmp_path,
    )
    assert out["posts"] == 1, "a rejected submit must not consume the latch"


# ===========================================================================
# B2 — the page must work when auth does not
# ===========================================================================
@needs_node
def test_an_anonymous_visitor_never_touches_the_supabase_sdk(page_js, hp_id, tmp_path):
    """hasSession() is a cookie probe with no network. MDXAuth.client() loads the SDK and
    getSession() can refresh against *.supabase.co — the exact host this page exists to
    route around (app/regwall.py)."""
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({posts: DOM.fetches.length,"
        "  sdk: DOM.authCalls, probes: DOM.hasSessionCalls,"
        "  auth: !!(DOM.fetches[0] && DOM.fetches[0].headers['Authorization'])}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "auth": {"hasSession": False}},
        tmp_path,
    )
    assert out["sdk"] == 0, "the SDK must not be loaded for an anonymous submit"
    assert out["probes"] >= 1, "…and the cookie probe is what decided that"
    assert out["posts"] == 1 and out["auth"] is False


@needs_node
def test_a_real_session_still_attaches_its_bearer(page_js, hp_id, tmp_path):
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({sdk: DOM.authCalls,"
        "  auth: DOM.fetches[0].headers['Authorization'] || null}); }, 300);",
        {"hp": hp_id, "fetchDelay": 10,
         "auth": {"hasSession": True, "token": "tok-123", "clientDelayMs": 20}},
        tmp_path,
    )
    assert out["sdk"] == 1
    assert out["auth"] == "Bearer tok-123"


@needs_node
def test_a_hanging_auth_client_does_not_strand_the_submit(page_js, hp_id, tmp_path):
    """The GFW failure mode: the SYN is blackholed, so the promise never settles and never
    errors. Unbounded, the button dims and NOTHING happens — no ticket, no error bar, no
    explanation, on the page whose entire purpose is being reachable when auth is not."""
    out = _run(
        page_js,
        FILLED
        + "var t0 = Date.now();"
        "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({posts: DOM.fetches.length,"
        "  ms: DOM.fetches.length ? DOM.fetches[0].t - t0 : -1,"
        "  auth: !!(DOM.fetches[0] && DOM.fetches[0].headers['Authorization']),"
        "  form: DOM.html.getAttribute('data-form')}); }, 6000);",
        {"hp": hp_id, "fetchDelay": 10,
         "auth": {"hasSession": True, "clientHangs": True}},
        tmp_path,
    )
    assert out["posts"] == 1, "the ticket must still go out, unauthenticated"
    assert out["auth"] is False              # filed as signed-out, which the API accepts
    assert out["form"] == "success"
    # the cap is 2500ms; anything near the 6s wait means it never fired
    assert 1000 < out["ms"] < 4000, f"the auth cap did not fire as expected ({out['ms']}ms)"


@needs_node
def test_the_post_carries_an_abort_signal(page_js, hp_id, tmp_path):
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({signal: !!(DOM.fetches[0].init &&"
        "  DOM.fetches[0].init.signal)}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10},
        tmp_path,
    )
    assert out["signal"] is True


@needs_node
def test_a_rejected_request_lands_the_error_bar(page_js, hp_id, tmp_path):
    """The path an abort takes. Nothing typed is discarded on the way."""
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({form: DOM.html.getAttribute('data-form'),"
        "  err: DOM.html.getAttribute('data-err'),"
        "  kept: DOM.nodes['#s-message'].value}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "fail_all": True},
        tmp_path,
    )
    assert out["form"] == "error" and out["err"] == "generic"
    assert out["kept"] == "my card was declined at checkout"


@needs_node
def test_a_429_gets_the_rate_limit_message_not_the_connection_one(page_js, hp_id, tmp_path):
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({err: DOM.html.getAttribute('data-err')}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "status": 429},
        tmp_path,
    )
    assert out["err"] == "rate"


# ===========================================================================
# B3 — the success copy follows the API's mail flag
# ===========================================================================
@needs_node
@pytest.mark.parametrize("mail,expect", [(True, "on"), (False, "off"), (None, "off")])
def test_the_success_state_follows_the_mail_flag(page_js, hp_id, tmp_path, mail, expect):
    """None is an API that did not answer, and the honest render for "we do not know" is
    the copy that promises nothing."""
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({mail: DOM.html.getAttribute('data-mail'),"
        "  form: DOM.html.getAttribute('data-form')}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "mail": mail, "ticket_id": TID},
        tmp_path,
    )
    assert out["form"] == "success"
    assert out["mail"] == expect


@needs_node
def test_the_slip_prints_the_servers_stamp_when_it_is_given_one(page_js, hp_id, tmp_path):
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({sent: DOM.nodes['#slip-sent'].textContent}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "sent": "26 Jul 2026, 14:04 UTC", "ticket_id": TID},
        tmp_path,
    )
    assert out["sent"] == "26 Jul 2026, 14:04 UTC"


@needs_node
def test_the_local_fallback_stamp_names_its_zone(page_js, hp_id, tmp_path):
    """An API that sends no stamp must still not print an unlabelled clock beside an
    email slip that says UTC."""
    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({sent: DOM.nodes['#slip-sent'].textContent}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "ticket_id": TID},
        tmp_path,
    )
    # a zone name or offset, never a bare "26 Jul 2026, 14:04"
    assert re.search(r"\d{2}:\d{2} \S+$", out["sent"]), out["sent"]


# ===========================================================================
# The ref: two implementations of one string
# ===========================================================================
@needs_node
@pytest.mark.parametrize("ticket_id", [
    "7f3a2b91-1111-4000-8000-000000000001",
    "f80cb92c-159b-4961-951c-2354df62d813",
    "00000000-0000-4000-8000-000000000000",
    "abcdef01-2345-6789-abcd-ef0123456789",
])
def test_the_page_and_ticket_ref_derive_the_same_number(page_js, hp_id, tmp_path, ticket_id):
    """The success slip and the ack email's subject print the SAME number from two
    independent implementations. Nothing else in the estate compares them."""
    from app import support

    out = _run(
        page_js,
        FILLED
        + "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({ref: DOM.nodes['#slip-ref'].textContent}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "ticket_id": ticket_id},
        tmp_path,
    )
    assert out["ref"] == support.ticket_ref(ticket_id)


# ===========================================================================
# The honeypot's server contract survived its rename
# ===========================================================================
@needs_node
def test_the_renamed_honeypot_still_files_under_the_website_key(page_js, hp_id, tmp_path):
    out = _run(
        page_js,
        FILLED
        + f"DOM.nodes['{hp_id}'].value = 'http://spam.test';"
        "DOM.nodes['#tk-form'].fire('submit');"
        "setTimeout(function(){ OUT({body: DOM.fetches[0].body}); }, 200);",
        {"hp": hp_id, "fetchDelay": 10, "ticket_id": TID},
        tmp_path,
    )
    assert out["body"]["website"] == "http://spam.test"
    assert set(out["body"]) == {"email", "topic", "subject", "message", "lang", "website", "t0"}
