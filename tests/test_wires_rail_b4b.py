"""tests/test_wires_rail_b4b.py — XG-W7 / D05-B4b+B4c+seeding.

What this pins:

  B4c  daemon ZH pass  — _attach_zh fills a Chinese twin for NEW items only, is
                         disarmable, and FAILS SOFT in every direction (raising
                         translator, None entries, echoed English). The rail must
                         degrade to honest English-plus-marker, never to a blank.
  B4b  news.html rail  — the panel consumes the real wires.v1 contract, renders
                         the engine's plain-word labels instead of the machine
                         `class` slug, and keeps the four HTTP outcomes apart
                         (404 hidden / 401-403 gate / error down / empty quiet).
  seed follow-CTAs     — handles reach marketing mail and the report footer, and
                         are kept OUT of transactional mail and out of the shared
                         public footer (which is IA-locked to the landing and
                         host-locked by the China-access guard in
                         tests/test_support_page.py).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Cannot locate repo root from {p}")


ROOT = _worktree_root()
NEWS_TPL = (ROOT / "templates" / "news.html.j2").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# B4c — the daemon's ZH pass
# --------------------------------------------------------------------------- #
def _daemon():
    return pytest.importorskip("scripts.marketing_fastlane_daemon")


def test_attach_zh_translates_only_items_that_lack_a_twin(monkeypatch):
    d = _daemon()
    seen: list[list[str]] = []

    def fake(texts):
        seen.append(list(texts))
        return ["中文-%d" % i for i, _ in enumerate(texts)]

    monkeypatch.setattr("engine.news_translate.translate_to_zh", fake)
    items = [
        {"id": "a", "en": "Fed holds rates"},
        {"id": "b", "en": "Already done", "zh": "已经有了"},
        {"id": "c", "en": "Claims come in light"},
    ]
    d._attach_zh(items, {})
    # Only the two without a twin were sent to the translator.
    assert seen == [["Fed holds rates", "Claims come in light"]]
    assert items[0]["zh"] == "中文-0"
    assert items[1]["zh"] == "已经有了"          # untouched
    assert items[2]["zh"] == "中文-1"


def test_attach_zh_is_disarmable(monkeypatch):
    d = _daemon()
    monkeypatch.setattr("engine.news_translate.translate_to_zh",
                        lambda texts: pytest.fail("must not be called when disarmed"))
    items = [{"id": "a", "en": "Fed holds rates"}]
    d._attach_zh(items, {"zh_enabled": False})
    assert "zh" not in items[0]


def test_attach_zh_fails_soft_when_the_translator_raises(monkeypatch):
    """A translator fault must cost the item its Chinese twin, never the sink."""
    d = _daemon()

    def boom(texts):
        raise RuntimeError("no key")

    monkeypatch.setattr("engine.news_translate.translate_to_zh", boom)
    items = [{"id": "a", "en": "Fed holds rates"}]
    d._attach_zh(items, {})                       # must not raise
    assert "zh" not in items[0]


def test_attach_zh_drops_nulls_and_echoed_english(monkeypatch):
    """translate_to_zh returns None per item when unkeyed/rate-limited, and a
    degenerate model can echo the input back. Neither may ship as a translation —
    the client's honest '英文原文' marker keys off the ABSENCE of `zh`."""
    d = _daemon()
    monkeypatch.setattr("engine.news_translate.translate_to_zh",
                        lambda texts: [None, "Fed holds rates", "  ", "真的中文"])
    items = [{"id": str(i), "en": t} for i, t in enumerate(
        ["a headline", "Fed holds rates", "third", "fourth"])]
    d._attach_zh(items, {})
    assert "zh" not in items[0]                    # None
    assert "zh" not in items[1]                    # echoed the English back
    assert "zh" not in items[2]                    # blank
    assert items[3]["zh"] == "真的中文"


def test_wires_sink_translates_before_the_merge(monkeypatch, tmp_path):
    """Order matters: a persisted item must keep the twin it got on arrival, so
    the ZH pass runs over THIS tick's items and never over the whole window."""
    d = _daemon()
    monkeypatch.setattr("engine.news_translate.translate_to_zh",
                        lambda texts: ["译文" for _ in texts])
    cfg = {"wire": {"wires_sink_paths": [str(tmp_path / "live" / "wires.json")],
                    "rail_max_items": 50}}
    import json
    from datetime import datetime, timezone
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    d._write_wires_sink([{"id": "a", "ts": "2026-07-28T11:59:00Z", "en": "one"}], cfg, now)
    payload = json.loads((tmp_path / "live" / "wires.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "wires.v1"
    assert payload["items"][0]["zh"] == "译文"


# --------------------------------------------------------------------------- #
# B4b — the news.html live-wire rail
# --------------------------------------------------------------------------- #
def test_rail_consumes_the_live_wires_contract():
    """The panel must read the real published asset, by the relative path the rest
    of the live plane uses (live.js: 'live/quotes.json'), and must verify the
    schema tag rather than trusting any JSON that answers."""
    assert "'live/wires.json'" in NEWS_TPL
    assert "wires.v1" in NEWS_TPL
    # every field name the engine actually emits (press_lane._build_rail_item)
    for field in ("label_en", "label_zh", "corroboration", "tape_stamp", "attribution", "updated_at"):
        assert field in NEWS_TPL, field


def test_rail_never_renders_the_machine_class_slug():
    """`class` is the machine slug and stays machine-side: it may be used to FILTER,
    but the visible label is always label_en/label_zh (doctrine Law 2, raw slugs)."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    # the slug is read for filtering/keying only
    assert "it['class']" in body
    # ...and the label is what reaches the DOM
    assert "el('span','nxw-cls', String(label))" in body
    assert "zh ? (it.label_zh || it.label_en) : it.label_en" in body


def test_rail_keeps_the_four_http_outcomes_apart():
    """404 (not published here) must hide the panel; a refusal must ask the reader
    to sign in; a fault must say so; an empty window must say the desk is quiet.
    Collapsing any pair of these into 'empty list' is the dishonest degradation
    this panel exists to avoid."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "r.status === 404" in body and "box.hidden = true" in body
    assert "r.status === 401 || r.status === 403" in body and "showState('gate')" in body
    assert "showState('down')" in body
    assert "if(!items.length){ showState('quiet'); return; }" in body


def test_rail_states_all_carry_a_stance_and_both_languages():
    """Doctrine Law 1: every panel says what to do, even when the answer is
    'nothing'. Law: bilingual parity on everything a user reads."""
    body = NEWS_TPL.split("var STATE_COPY")[-1].split("function showState")[0]
    for kind in ("gate:", "down:", "quiet:"):
        assert kind in body, kind
    # the two 'nothing is wrong' states say so in plain words, in both languages
    assert "Nothing to act on" in body and "无需操作" in body
    assert "Nothing to do" in body


def test_rail_writes_wire_copy_with_textcontent_only():
    """Item text is third-party wire copy republished on our page. The renderer
    must never build it through innerHTML."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert not re.search(r"\.innerHTML\s*=", body), "wire copy must never be assigned as HTML"
    assert "n.textContent = text" in body


def test_rail_uses_no_directional_colour():
    """红涨绿跌 hazard avoided by construction: the wire carries no direction, so
    it borrows neither --up nor --down. If a future revision adds a direction, it
    must use the theme tokens (which swap under zh), not literal green/red."""
    css = NEWS_TPL.split("LIVE WIRE (B4b)")[1].split("/* ---- responsive ---- */")[0]
    assert "var(--up)" not in css and "var(--down)" not in css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css.replace("#000", "")), \
        "the wire panel is theme-token only — no literal hex outside the mask stop"


def test_rail_tier_two_copy_uses_data_tips_not_title_attributes():
    """CI-guarded house law: no translated text in title=. The wire's Tier-2 copy
    (what 'reports' vs '2 sources' means, what each account posts) rides the LENS
    data-tip pair instead."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "data-tip-en" in body and "data-tip-zh" in body
    assert 'title="' not in NEWS_TPL.split("nxw-social")[-1].split("</section>")[0]


# --------------------------------------------------------------------------- #
# Follow-CTA seeding sweep
# --------------------------------------------------------------------------- #
def test_news_rail_carries_both_the_wire_and_the_flagship_handle():
    block = NEWS_TPL.split('class="nxw-social"')[-1].split("</div>")[0]
    assert "x.com/mastermindnews1" in block
    assert "x.com/mastermindx001" in block


def test_report_footer_carries_the_flagship_handle_as_its_own_row():
    """A legal disclaimer and a marketing CTA must not read as one sentence."""
    base = (ROOT / "templates" / "report_base.html.j2").read_text(encoding="utf-8")
    foot = base.split('<footer class="rfoot">')[-1].split("</footer>")[0]
    assert "x.com/mastermindx001" in foot
    assert "not investment advice" in foot
    # the handle sits in its own element, after the disclaimer text
    assert foot.index("not investment advice") < foot.index("rf-x")
    assert "<div><a class=\"rf-x\"" in foot


def test_marketing_mail_carries_the_handles_and_transactional_mail_does_not():
    mailer = pytest.importorskip("app.mailer")
    blocks = [{"en": "Body.", "zh": "正文。"}]
    mk_html, mk_text = mailer.render_email("T", "标题", blocks, follow=True)
    tx_html, tx_text = mailer.render_email("T", "标题", blocks, eyebrow="RECEIPT")
    for handle in ("mastermindx001", "mastermindnews1"):
        assert handle in mk_html and handle in mk_text, handle
    assert "x.com/" not in tx_html and "x.com/" not in tx_text


def test_only_marketing_senders_pass_follow():
    """Receipts, dunning and support replies are service messages. Any new
    follow=True outside app/marketing_emails.py is a regression."""
    for name in ("app/billing_emails.py", "app/support.py"):
        assert "follow=True" not in (ROOT / name).read_text(encoding="utf-8"), name
    assert (ROOT / "app" / "marketing_emails.py").read_text(
        encoding="utf-8").count("follow=True") == 2


def test_the_shared_public_footer_stays_handle_free():
    """Deliberate, not an oversight (see this module's docstring): the shared
    public footer is IA-locked to the hand-authored landing by
    test_public_chrome.py and host-locked by the China-access guard in
    test_support_page.py — and x.com is itself unreachable in China, so an X link
    there would ship a dead link into the footer of the whole public estate.
    Placing it needs an operator decision, not a design wave."""
    footer = (ROOT / "templates" / "_public_footer.html.j2").read_text(encoding="utf-8")
    assert "//x.com" not in footer      # not "mastermind-x.com", which contains "x.com"
