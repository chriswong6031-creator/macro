"""tests/test_email_templates.py — the W-D pinned email base (SEE W2).

`app/mailer.py::render_email` is the ONLY shell any send in the estate may use, so the
properties pinned in mockups/support_email/PIN.md §6 are asserted here rather than left to
review. Every one of them exists because breaking it breaks a real mail client:

  * no images, no external CSS, no remote anything — a blocked logo makes a billing email
    look like phishing, and a stripped stylesheet must never take the layout with it;
  * tables for layout, `role="presentation"`, 600px;
  * background-color AND color set together on the same element (Gmail/Outlook.com
    force-invert regardless of `color-scheme`; flipping only the background is what
    produces black-on-black);
  * both languages in EVERY message, EN first, then the labelled 中文 rule;
  * CLASS DISCIPLINE — the unsubscribe slot renders for marketing and is ABSENT from a
    transactional send, because a receipt or a ticket acknowledgment goes out regardless
    of marketing opt-out and the link would lie about what it does.

Fully offline: render_email is a pure function and nothing here touches SMTP or Supabase.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import mailer  # noqa: E402

BLOCKS = [
    {"en": "Your Insider trial has started.", "zh": "你的 Insider 试用已开始。"},
    {"kind": "kv",
     "en": [("Plan", "Insider — monthly"), ("Price", "US$69.00 per month")],
     "zh": [("方案", "Insider — 按月"), ("价格", "每月 69.00 美元")]},
    {"kind": "quote", "en": "my card failed", "zh": "银行卡扣款失败"},
    {"kind": "button", "en": "Manage billing", "zh": "管理账单",
     "url": "https://www.mastermind-x.com/plans.html?billing=portal"},
    {"kind": "fine", "en": "Cancel any time before 1 Aug 2026.", "zh": "8 月 1 日前可随时取消。"},
]


@pytest.fixture(scope="module")
def rendered() -> tuple[str, str]:
    return mailer.render_email(
        "Your trial has started", "试用已开始", BLOCKS,
        eyebrow="TRIAL",
        preheader="Free until 1 Aug 2026. Cancel before then and you are not charged.",
        why_en="You received this because you started an Insider trial on 25 July 2026.",
        why_zh="你收到这封邮件，是因为你在 2026 年 7 月 25 日开始了 Insider 试用。",
    )


# ===========================================================================
# Rule 3 + the China constraint: nothing is fetched from anywhere
# ===========================================================================
def test_no_images_no_external_css_no_remote_assets(rendered):
    html, _text = rendered
    low = html.lower()
    assert "<img" not in low, "the brand is TEXT — a blocked logo reads as phishing"
    assert "background-image" not in low
    assert "url(" not in low, "no remote or data asset may be referenced"
    assert "@import" not in low
    assert "<link" not in low, "an external stylesheet is stripped by half the clients"
    assert "<script" not in low
    # The only absolute URLs allowed are things the READER clicks.
    for url in re.findall(r'href="([^"]+)"', html):
        assert url.startswith(("https://www.mastermind-x.com", "mailto:")), url


def test_style_block_is_enhancement_only_never_load_bearing(rendered):
    """PIN §6.2 rule 2: Gmail strips <style> in several contexts, so the <style> block may
    only hold the dark + mobile overlays. Everything structural is inline on the element."""
    html, _text = rendered
    block = re.search(r"<style[^>]*>(.*?)</style>", html, re.S)
    assert block, "the progressive-enhancement block should exist"
    body = block.group(1)
    # every rule in it is inside a media query
    stripped = re.sub(r"@media[^{]+\{.*?\n  \}", "", body, flags=re.S).strip()
    assert "{" not in stripped, f"non-media rules leaked into <style>: {stripped[:200]}"
    assert "prefers-color-scheme: dark" in body and "max-width:620px" in body


# ===========================================================================
# Rules 1, 4, 5: tables, 600px, paired background+color
# ===========================================================================
def test_every_layout_table_is_presentational(rendered):
    html, _text = rendered
    tables = re.findall(r"<table[^>]*>", html)
    assert tables
    for tag in tables:
        assert 'role="presentation"' in tag, tag
        assert 'border="0"' in tag and 'cellpadding="0"' in tag and 'cellspacing="0"' in tag, tag
    assert "display:flex" not in html and "display:grid" not in html


def test_shell_is_600px_fixed_and_fluid_under_620(rendered):
    html, _text = rendered
    assert 'width="600"' in html and "max-width:600px" in html
    assert ".mx-shell   { width:100% !important" in html


def test_no_text_ever_inherits_its_colour(rendered):
    """PIN §6.2 rule 5, as the pinned markup actually expresses it: background and text
    live on paired PARENT/CHILD elements, so the checkable half is that every element
    which sets a face also states its colour. Text that inherits is text an inverter can
    move out from under its background — that is the black-on-black failure."""
    html, _text = rendered
    checked = 0
    for style in re.findall(r'style="([^"]*font-family:[^"]*)"', html):
        flat = " ".join(style.split())
        checked += 1
        assert re.search(r"(?<![-a-z])color:", flat), flat
    assert checked >= 8, f"expected the whole card to be explicitly coloured, saw {checked}"


# Backgrounds the pin paints, and the subset that is deliberately IDENTICAL in both
# schemes: the brand band (the product's identity, and an already-dark surface is the
# safest thing to hand an inverter), the CTA, and the gradient stops.
_PALETTE_BG = {"#eef1f5", "#ffffff", "#0f1115", "#f6f8fb", "#285fff",
               "#3b82f6", "#6366f1", "#7c5cff"}
_SCHEME_STABLE_BG = {"#0f1115", "#285fff", "#3b82f6", "#6366f1", "#7c5cff"}


def test_every_painted_surface_is_a_pinned_colour_the_overlay_can_reach(rendered):
    html, _text = rendered
    tags = re.findall(r"<[a-z0-9]+\b[^>]*background-color:[^>]*>", html)
    assert tags
    for tag in tags:
        bg = re.search(r"background-color:\s*(#[0-9a-fA-F]{6})", tag).group(1).lower()
        assert bg in _PALETTE_BG, f"unpinned surface colour {bg}: {tag[:120]}"
        if bg in _SCHEME_STABLE_BG:
            continue
        assert re.search(r'class="[^"]*\bmx-(canvas|card|slip)\b', tag), (
            f"scheme-varying surface with no mx-* hook, so the dark overlay cannot "
            f"reach it: {tag[:160]}")


def test_canvas_colour_is_on_the_body_as_well_as_the_wrapper(rendered):
    """Clients that drop the wrapper table's background still paint the right shade."""
    html, _text = rendered
    body_tag = re.search(r"<body[^>]*>", html).group(0)
    assert 'bgcolor="#eef1f5"' in body_tag and "background-color:#eef1f5" in body_tag
    assert html.count('class="mx-canvas"') == 2      # <body> + the wrapper table


def test_dark_overlay_never_flips_a_background_without_its_text(rendered):
    """The overlay is the half Gmail ignores, but where it IS honoured a background that
    moves without its text colour is the same black-on-black failure."""
    html, _text = rendered
    dark = re.search(r"prefers-color-scheme: dark\)\s*\{(.*?)\n  \}", html, re.S).group(1)
    assert "background-color:#0b0d11" in dark and "color:#d7dce3" in dark
    assert "background-color:#181b21" in dark and "color:#96a0b0" in dark


def test_colour_scheme_meta_is_declared(rendered):
    html, _text = rendered
    assert '<meta name="color-scheme" content="light dark" />' in html
    assert '<meta name="supported-color-schemes" content="light dark" />' in html


def test_gradient_bar_is_three_solid_cells_not_a_gradient(rendered):
    """PIN §6.4 — a CSS gradient silently disappears in Outlook and a gradient image would
    be blocked; three solid cells paint identically in every client."""
    html, _text = rendered
    assert "linear-gradient" not in html
    for stop in ("#3b82f6", "#6366f1", "#7c5cff"):
        assert f'bgcolor="{stop}"' in html and f"background-color:{stop}" in html
    assert html.count('height="4"') == 3


def test_brand_band_is_dark_in_both_schemes(rendered):
    """It is the product's identity, and an already-dark band is the safest thing to hand
    a colour inverter — so it is NOT in the dark-mode overlay."""
    html, _text = rendered
    assert 'bgcolor="#0f1115"' in html
    dark = re.search(r"prefers-color-scheme: dark\)\s*\{(.*?)\n  \}", html, re.S).group(1)
    assert "mx-band" not in dark


# ===========================================================================
# R4: both languages, always, EN first
# ===========================================================================
def test_both_languages_ship_in_every_message(rendered):
    html, text = rendered
    assert "Your trial has started" in html and "试用已开始" in html
    for block in BLOCKS:
        for value in (block["en"], block["zh"]):
            if isinstance(value, list):
                for k, v in value:
                    assert k in html, k
                    assert v in html, v
            else:
                assert value in html, value
    assert "Your trial has started" in text and "试用已开始" in text


def test_english_leads_and_the_chinese_half_is_labelled(rendered):
    html, _text = rendered
    en_at = html.index("Your trial has started")
    rule_at = html.index("中文")
    zh_at = html.index("试用已开始")
    assert en_at < rule_at < zh_at, "EN primary, then the labelled 中文 rule, then ZH"


def test_zh_slip_keys_use_a_cjk_face_not_the_mono_stack():
    """PIN §2.1/§6.3: the mono stack carries no Hanzi, so a ZH key otherwise falls through
    to whatever the system picks — on some machines a serif."""
    html, _text = mailer.render_email(
        "T", "T", [{"kind": "kv", "en": [("PLAN", "x")], "zh": [("方案", "x")]}])
    zh_cell = re.search(r'<td class="mx-slip-k"[^>]*>\s*方案', html)
    assert zh_cell, "the ZH slip key cell should exist"
    assert "PingFang SC" in zh_cell.group(0)
    en_cell = re.search(r'<td class="mx-slip-k"[^>]*>\s*PLAN', html)
    assert "SFMono-Regular" in en_cell.group(0)


def test_preheader_and_eyebrow_render(rendered):
    html, text = rendered
    assert "Free until 1 Aug 2026" in html
    assert "display:none" in html.split("Free until")[0][-260:], "preheader must be hidden"
    assert ">TRIAL<" in html.replace("\n", "").replace(" ", "") or "TRIAL" in html
    assert "MASTERMIND · TRIAL" in text


def test_why_line_states_the_actual_trigger(rendered):
    html, text = rendered
    assert "You received this because you started an Insider trial on 25 July 2026." in html
    assert "你收到这封邮件，是因为你在 2026 年 7 月 25 日开始了 Insider 试用。" in html
    assert "You received this because" in text


# ===========================================================================
# PIN §6.7 / masterplan R5 — class discipline
# ===========================================================================
def test_transactional_send_carries_no_unsubscribe_slot(rendered):
    """A receipt or a ticket ack goes out regardless of marketing opt-out, so an
    unsubscribe link on one would lie about what it does."""
    html, text = rendered
    assert "unsubscribe" not in html.lower()
    assert "退订" not in html
    assert "unsubscribe" not in text.lower()


def test_marketing_send_renders_the_unsubscribe_slot():
    url = "https://www.mastermind-x.com/unsubscribe.html?t=abc.def"
    html, text = mailer.render_email("Campaign", "推广", [{"en": "hi", "zh": "你好"}],
                                     unsubscribe_url=url)
    assert html.count(url) == 2, "EN + ZH unsubscribe links"
    assert ">Unsubscribe</a>" in html and ">退订</a>" in html
    assert url in text


def test_ticket_ack_is_transactional_and_unsubscribe_free(monkeypatch):
    """End-to-end on the real caller: app/support.py's acknowledgment must come out of the
    pinned base with the slot deleted (PIN §7.7 is a transactional template)."""
    from app import support
    captured: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (captured.append(kw), "sent")[1])
    status = support._ack_submitter(
        ticket_id="7f3a2b91-1111-4000-8000-000000000001", topic="billing",
        subject="Card declined", message="my card failed", email="ada@example.com",
        user_id=None)
    assert status == "sent" and len(captured) == 1
    assert captured[0]["cls"] == "transactional"
    assert "unsubscribe" not in captured[0]["html"].lower()
    assert "MX-7F3A2B91" in captured[0]["html"]


# ===========================================================================
# Untrusted input
# ===========================================================================
@pytest.mark.parametrize("kind", ["p", "fine", "quote", "button"])
def test_stranger_written_text_is_escaped_everywhere(kind):
    html, _text = mailer.render_email(
        "T", "T", [{"kind": kind, "en": '<script>alert(1)</script>', "zh": "x",
                    "url": 'https://www.mastermind-x.com/"onmouseover="x'}])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'onmouseover="x' not in html


def test_quote_keeps_the_line_breaks_the_person_typed():
    html, _text = mailer.render_email(
        "T", "T", [{"kind": "quote", "en": "line one\nline two", "zh": "x"}])
    assert "line one<br />line two" in html


def test_empty_blocks_are_skipped_not_rendered_blank():
    html, text = mailer.render_email("T", "T", [{"en": "only english", "zh": ""}])
    assert "only english" in html and "only english" in text


# ===========================================================================
# Regression guard: the W1 placeholder base is really gone
# ===========================================================================
def test_the_w1_functional_placeholder_base_has_been_replaced():
    html, _text = mailer.render_email("T", "T", [{"en": "x", "zh": "y"}])
    assert "W1 functional base" not in html
    assert html.lstrip().startswith("<!DOCTYPE html PUBLIC")
