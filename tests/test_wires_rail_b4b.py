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

    def fake(texts, cfg=None):
        seen.append(list(texts))
        return ["中文-%d" % i for i, _ in enumerate(texts)]

    monkeypatch.setattr("engine.news_translate.translate_to_zh", fake)
    items = [
        {"id": "a", "en": "Fed holds rates"},
        {"id": "b", "en": "Already done", "zh": "已经有了"},
        {"id": "c", "en": "Claims come in light"},
    ]
    d._attach_zh(items, {"zh_enabled": True})
    # Only the two without a twin were sent to the translator.
    assert seen == [["Fed holds rates", "Claims come in light"]]
    assert items[0]["zh"] == "中文-0"
    assert items[1]["zh"] == "已经有了"          # untouched
    assert items[2]["zh"] == "中文-1"


def test_attach_zh_is_disarmable(monkeypatch):
    d = _daemon()
    monkeypatch.setattr("engine.news_translate.translate_to_zh",
                        lambda texts, cfg=None: pytest.fail("must not be called when disarmed"))
    items = [{"id": "a", "en": "Fed holds rates"}]
    d._attach_zh(items, {"zh_enabled": False})
    assert "zh" not in items[0]


def test_attach_zh_fails_soft_when_the_translator_raises(monkeypatch):
    """A translator fault must cost the item its Chinese twin, never the sink."""
    d = _daemon()

    def boom(texts, cfg=None):
        raise RuntimeError("no key")

    monkeypatch.setattr("engine.news_translate.translate_to_zh", boom)
    items = [{"id": "a", "en": "Fed holds rates"}]
    d._attach_zh(items, {"zh_enabled": True})     # must not raise
    assert "zh" not in items[0]


def test_attach_zh_drops_nulls_and_echoed_english(monkeypatch):
    """translate_to_zh returns None per item when unkeyed/rate-limited, and a
    degenerate model can echo the input back. Neither may ship as a translation —
    the client's honest '英文原文' marker keys off the ABSENCE of `zh`."""
    d = _daemon()
    monkeypatch.setattr("engine.news_translate.translate_to_zh",
                        lambda texts, cfg=None: [None, "Fed holds rates", "  ", "真的中文"])
    items = [{"id": str(i), "en": t} for i, t in enumerate(
        ["a headline", "Fed holds rates", "third", "fourth"])]
    d._attach_zh(items, {"zh_enabled": True})
    assert "zh" not in items[0]                    # None
    assert "zh" not in items[1]                    # echoed the English back
    assert "zh" not in items[2]                    # blank
    assert items[3]["zh"] == "真的中文"


def test_wires_sink_translates_before_the_merge(monkeypatch, tmp_path):
    """Order matters, and the assertion has to prove it.

    Tick 1 publishes an item and pays for its translation. Tick 2 sees the SAME id
    re-arrive untranslated (a recomposed body, a tape stamp attached late). The
    persisted `zh` must survive, and the translator must not be asked again — if
    the merge overwrote field-by-field, we would re-buy a translation every tick
    for as long as an item stays in the window.
    """
    import json
    from datetime import datetime, timezone
    d = _daemon()
    calls: list[list[str]] = []

    def fake(texts, cfg=None):
        calls.append(list(texts))
        return ["译文" for _ in texts]

    monkeypatch.setattr("engine.news_translate.translate_to_zh", fake)
    sink = tmp_path / "live" / "wires.json"
    cfg = {"wire": {"wires_sink_paths": [str(sink)], "rail_max_items": 50,
                    "zh_enabled": True}}
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

    d._write_wires_sink([{"id": "a", "ts": "2026-07-28T11:59:00Z", "en": "one"}], cfg, now)
    first = json.loads(sink.read_text(encoding="utf-8"))
    assert first["schema"] == "wires.v1"
    assert first["items"][0]["zh"] == "译文"
    assert first["zh"] == {"translated": 1, "attempted": 1}

    # same id, re-arriving with a late tape stamp and NO zh
    d._write_wires_sink(
        [{"id": "a", "ts": "2026-07-28T11:59:00Z", "en": "one · SPY +0.4%",
          "tape_stamp": "SPY +0.4%"}], cfg, now)
    second = json.loads(sink.read_text(encoding="utf-8"))
    assert len(second["items"]) == 1
    assert second["items"][0]["zh"] == "译文", "persisted translation was dropped"
    assert second["items"][0]["tape_stamp"] == "SPY +0.4%", "new fields must still win"
    assert len(calls) == 1, "a re-arriving item must not be re-translated"


def test_attach_zh_strips_the_tape_stamp_before_translating():
    """The stamp is language-neutral and the rail re-renders it from the structured
    field, so sending it to the model buys a mangled duplicate at token cost."""
    d = _daemon()
    sent: list[str] = []
    import engine.news_translate as nt
    orig = nt.translate_to_zh
    nt.translate_to_zh = lambda texts, cfg=None: (sent.extend(texts), [None] * len(texts))[1]
    try:
        d._attach_zh([{"id": "a", "en": "Trump speaks · WTI -1.8%",
                       "tape_stamp": "WTI -1.8%"}], {"zh_enabled": True})
    finally:
        nt.translate_to_zh = orig
    assert sent == ["Trump speaks"]


def test_attach_zh_caps_the_work_per_tick():
    """The tick budget is ~75s and the heartbeat only touches after it returns."""
    d = _daemon()
    seen: list[int] = []
    import engine.news_translate as nt
    orig = nt.translate_to_zh
    nt.translate_to_zh = lambda texts, cfg=None: (seen.append(len(texts)), [None] * len(texts))[1]
    try:
        items = [{"id": str(i), "en": "headline %d" % i} for i in range(40)]
        filled, tried = d._attach_zh(items, {"zh_enabled": True, "zh_per_tick": 16})
    finally:
        nt.translate_to_zh = orig
    assert seen == [16] and tried == 16


def test_zh_pass_writes_nothing_inside_the_repo():
    """D05 W0: the poller makes zero repo writes, and the nightly is the sole
    advancer of any forward ledger. The shared translation cache is git-TRACKED and
    data/ai_costs/usage.jsonl is a forward ledger, so this lane must use neither."""
    d = _daemon()
    cfg = d._zh_cfg({})
    cache = Path(cfg["cache_dir"])
    assert cache.is_absolute()
    assert "news_translation" not in str(cache), "must not share the git-tracked cache"
    assert str(cache).startswith(str(ROOT / "data" / "marketing" / "press"))
    import subprocess
    out = subprocess.run(["git", "check-ignore", str(cache / "probe.json")],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, "the lane cache directory is NOT gitignored"
    assert cfg["usage_sink"] == "none", "must not append to the nightly-owned ledger"
    # The real constraint is the ~75s tick whose heartbeat only touches after it
    # returns: one hung endpoint must not read to the monitor as a dead daemon.
    # The bound was 20 while this lane spoke HTTP to DeepSeek; it moved to 45 with
    # the 2026-07-31 switch to codex, where a turn is a CLI spawn PLUS a model call.
    assert cfg["max_retries"] == 0 and cfg["timeout_s"] <= 60


def test_zh_defaults_off_when_the_config_key_is_removed():
    """Deleting the key must disarm the spend, never silently arm it."""
    d = _daemon()
    assert d._attach_zh([{"id": "a", "en": "x"}], {}) == (0, 0)


def test_merge_window_prunes_by_age_as_well_as_count():
    """A count cap alone lets a quiet feed serve days-old items as the live wire."""
    from datetime import datetime, timedelta, timezone
    d = _daemon()
    now = datetime.now(timezone.utc)
    fresh = {"id": "new", "ts": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    old = {"id": "old", "ts": (now - timedelta(hours=100)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    merged = d._merge_wires_window([old], [fresh], 50, {"rail_max_age_h": 48})
    assert [it["id"] for it in merged] == ["new"]
    # and the bound is configurable rather than baked in
    both = d._merge_wires_window([old], [fresh], 50, {"rail_max_age_h": 200})
    assert len(both) == 2


def test_merge_window_ages_against_the_caller_clock_not_the_wall_clock():
    """MAJOR 4: `now` is the tick's clock, and it must decide the age cutoff.

    `_write_wires_sink` already holds the tick's `now` and stamps it into the
    payload, but the merge re-read `datetime.now`, so the sink aged items
    against a different instant than the one it published. Anything pinned to a
    past date — a fixture, a replay, a backfill — then lost its whole window the
    moment wall-clock drifted past `rail_max_age_h`. That is what turned this
    suite red on 2026-07-29 against 2026-07-27 fixtures at a 48h horizon, on a
    head that had changed nothing about the wire.
    """
    from datetime import datetime, timedelta, timezone
    d = _daemon()
    # A window that is ancient by the wall clock and current by the caller's.
    pinned = datetime(2020, 5, 17, 12, 0, tzinfo=timezone.utc)
    items = [{"id": f"i{n}",
              "ts": (pinned - timedelta(hours=n)).strftime("%Y-%m-%dT%H:%M:%SZ")}
             for n in (1, 2, 3)]

    kept = d._merge_wires_window([], items, 50, {"rail_max_age_h": 48}, now=pinned)
    assert [it["id"] for it in kept] == ["i1", "i2", "i3"], (
        "an explicit `now` was ignored and the wall clock aged the window out")

    # The same call WITHOUT `now` keeps the wall-clock behaviour for the ad-hoc
    # callers that have no tick — these items really are years old.
    assert d._merge_wires_window([], items, 50, {"rail_max_age_h": 48}) == []


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
def test_news_rail_carries_the_flagship_handle_only():
    """Flagship-only is a live-account rule, not a taste call — see
    test_no_cta_points_at_a_dark_account."""
    block = NEWS_TPL.split('class="nxw-social"')[-1].split("</div>")[0]
    assert "x.com/mastermindx001" in block
    assert "mastermindnews1" not in block


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
    assert "mastermindx001" in mk_html and "mastermindx001" in mk_text
    assert "mastermindnews1" not in mk_html and "mastermindnews1" not in mk_text
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


# --------------------------------------------------------------------------- #
# The rail against REAL engine output (not hand-written JSON)
# --------------------------------------------------------------------------- #
def _engine_rail_item(**over):
    """One wires.v1 item built by the ENGINE, so the client contract is checked
    against what press_lane actually emits rather than against a fixture someone
    wrote from the docs."""
    press_lane = pytest.importorskip("engine.marketing.press_lane")
    from datetime import datetime, timezone
    now = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
    scored = {"id": "w1", "headline": "Trump says the call with Xi was friendly",
              "published_at": "2026-07-28T14:58:00Z", "event_class": "policy",
              "corroboration_class": "corroborated", "salience": 90.0,
              "source_name": "Reuters"}
    scored.update(over)
    return press_lane._build_rail_item(
        scored, now, {}, corr={}, now_iso="2026-07-28T15:00:00Z",
        window_s=1800, quotes_store=None, tape_cfg={}, wire_voice_enabled=False)


def test_engine_emits_every_field_the_rail_reads():
    item = _engine_rail_item()
    for field in ("id", "ts", "class", "label_en", "label_zh", "en", "corroboration"):
        assert field in item, field
    assert item["label_en"] == "Washington" and item["label_zh"] == "政策"
    assert item["class"] == "policy"


def test_engine_always_embeds_the_tape_stamp_in_en():
    """The gloss the rail renders depends on this being true on BOTH paths — the
    first version of the client guarded with `if the text does not contain it`,
    which never fired, so the shipped rail printed a bare number with no window."""
    press_lane = pytest.importorskip("engine.marketing.press_lane")
    from datetime import datetime, timezone
    now = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
    scored = {"id": "w2", "headline": "Nvidia lifts its outlook",
              "published_at": "2026-07-28T14:00:00Z", "event_class": "company_news",
              "corroboration_class": "direct-quote"}
    emitted = press_lane._build_rail_item(
        scored, now, {"w2": {"text": "Nvidia lifts its outlook · NVDA +2.4%",
                             "register": "companies", "tape_stamp": "NVDA +2.4%",
                             "attribution": "Nvidia"}},
        corr={}, now_iso="2026-07-28T15:00:00Z", window_s=1800,
        quotes_store=None, tape_cfg={}, wire_voice_enabled=False)
    assert emitted["tape_stamp"] == "NVDA +2.4%"
    assert emitted["en"].endswith(" · NVDA +2.4%"), (
        "both rail paths compose '<body> · <stamp>'; the client strips this tail")


def test_client_strips_the_embedded_stamp_and_re_renders_the_gloss():
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "var tail = ' · ' + tape;" in body
    assert "text.slice(-tail.length) === tail" in body
    assert "'since this crossed'" in body and "'自该消息出现以来'" in body
    assert "indexOf(tape) < 0" not in body, "the dead guard must be gone"


def test_corroboration_protocol_matches_the_engine_wording():
    """Pin the engine↔client string protocol from the ENGINE side: if the wording
    set changes, this fails here rather than silently degrading the rail."""
    press_lane = pytest.importorskip("engine.marketing.press_lane")
    assert press_lane._corroboration_chip(0, "direct-quote") == "verified"
    assert press_lane._corroboration_chip(3, "corroborated") == "3 sources"
    assert press_lane._corroboration_chip(1, "hearsay") == "reports"
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "/^verified$/i" in body
    assert "/^(\\d+)\\s+sources?$/i" in body
    assert "/^reports$/i" in body


def test_unknown_corroboration_wording_degrades_to_the_neutral_form():
    """An unrecognised label is not evidence of weak sourcing, so it must not be
    drawn as the single-report form — and it must never leak raw English into ZH."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    tail = body.split("function corrOf")[1].split("function renderList")[0]
    assert "form:'neutral'" in tail
    assert "zh:'来源信息'" in tail
    css = NEWS_TPL.split("LIVE WIRE (B4b)")[1]
    assert '.nxw-node[data-corr="neutral"]::after{ border-style:solid; }' in css


def test_source_count_is_not_dressed_up_as_verified_independence():
    """The engine counts distinct feeds/handles. Calling that 'independent wires'
    invents a check nobody ran."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "independent wires" not in body
    assert "独立通讯社" not in body
    assert "not a check on independence" in body


# --------------------------------------------------------------------------- #
# Degradation, freshness and polling
# --------------------------------------------------------------------------- #
def test_the_masked_503_is_read_as_absent_not_as_a_fault():
    """Caddy's @reg_asset_err rewrites a MISSING protected asset into a 503 JSON.
    Until the exclusion is deployed that is the not-published case in a costume;
    reading it as a fault parks a permanent 'not reachable' on a dark feature."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "site_access_temporarily_unavailable" in body
    assert "r.status === 503" in body
    assert "throw new Error('http 503')" in body, "any OTHER 503 stays a real fault"


def test_caddy_lets_a_missing_wires_json_reach_the_client_as_404():
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    err = caddy.split("@reg_asset_err {")[1].split("}")[0]
    assert "/live/wires.json" in err
    # ...and the asset is still registration-gated: the PUBLIC boundary block,
    # which tests/test_site_access_boundary.py diffs against site_access.yml,
    # must NOT list it.
    public = caddy.split("# PUBLIC-BOUNDARY-START")[1].split("# PUBLIC-BOUNDARY-END")[0]
    assert "/live/wires.json" not in public


def test_settled_negative_states_stop_the_poll_timer():
    """Otherwise every open tab runs a no-store fetch every 60s forever for an
    answer that cannot change without a deploy."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "function stop(){" in body and "clearInterval(pollTimer)" in body
    assert "mode = 'down'; showState('down'); stop();" in body
    assert "function absent(){ mode = 'absent'; box.hidden = true; stop(); }" in body
    assert "if(mode === 'absent'){ box.hidden = true; return; }" in body, \
        "repaint must handle absent"


def test_freshness_comes_from_the_newest_item_not_the_daemon_stamp():
    """updated_at is re-stamped every tick whether or not anything crossed, so a
    quiet feed would pulse LIVE over a three-day-old window."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "function isStale(){" in body
    assert "Date.parse(items[i].ts" in body
    assert "Date.parse(updatedAt)" not in body, "freshness must not key off updated_at"


def test_the_stale_state_is_actually_visible():
    css = NEWS_TPL.split("LIVE WIRE (B4b)")[1].split("/* ---- responsive ---- */")[0]
    assert '.nxw[data-state="stale"] .nxw-lamp' in css
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "Nothing new for a while" in body and "暂无新消息" in body


def test_seen_tracks_every_arrival_not_just_the_filtered_view():
    """Scoped to the visible slice, a filter switch animated old items as fresh."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "items.forEach(function(it){ if(!seen[it.id]) fresh[it.id] = 1; });" in body
    assert "if(painted && fresh[it.id]) row.classList.add('is-new');" in body


# --------------------------------------------------------------------------- #
# Information architecture + accessibility
# --------------------------------------------------------------------------- #
def test_the_wire_uses_the_pages_own_lane_filter_not_a_second_pill_row():
    assert "nxWireFilters" not in NEWS_TPL and "renderFilters" not in NEWS_TPL
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "getElementById('nxSeg')" in body
    for lane in ("'macro'", "'fed'", "'companies'", "'markets'"):
        assert lane in body, lane
    # a lane with no wire items explains itself instead of showing a blank box
    assert "nxw-lanenone" in body


def test_the_wire_panel_sits_below_the_filter_row_that_drives_it():
    assert NEWS_TPL.index('id="nxSeg"') < NEWS_TPL.index('id="nxWire"'), \
        "a control must come before what it controls"
    # ...and the panel sits OUTSIDE the ranked feed's {% if FEED %} guard, which
    # is what keeps it on the page when the ranked board is empty (asserted for
    # real by test_the_rail_renders_even_when_the_ranked_feed_is_empty).
    between = NEWS_TPL[NEWS_TPL.index('id="nxSeg"'):NEWS_TPL.index('id="nxWire"')]
    assert "{% endif %}" in between, "the wire must not be inside the FEED guard"


def test_the_corroboration_tip_is_discoverable_and_focusable():
    """This span carries the panel's whole epistemic payload; a tip with no
    affordance and no keyboard route is a tip nobody reads."""
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "'nxw-corr lens-term'" in body
    assert "cs.setAttribute('tabindex', '0')" in body


def test_the_signin_cta_still_goes_somewhere_without_the_auth_modal():
    body = NEWS_TPL.split("LIVE WIRE (B4b)")[-1]
    assert "index.html?signin=1" in body


def test_zh_copy_is_idiomatic_not_a_calque():
    assert "刚刚跨过的消息" not in NEWS_TPL, "calque of 'crossed the tape'"
    assert "最新快讯" in NEWS_TPL


# --------------------------------------------------------------------------- #
# The template actually RENDERS the rail
# --------------------------------------------------------------------------- #
def test_the_rail_reaches_rendered_html():
    """Every other test here reads the template as TEXT, so wrapping the whole
    section in `{% if false %}` would keep them all green while the page shipped
    without a rail. This one renders it."""
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
                             undefined=jinja2.ChainableUndefined, autoescape=False)
    html = env.get_template("news.html.j2").render(
        news_feed=[{"title": "A headline", "url": "#", "theme": "macro",
                    "lane": "macro", "rank_score": 50, "seendate": "2026-07-28T12:00:00Z",
                    "source_name": "Reuters", "tickers": []}],
        macro_news={"fetched_at": "2026-07-28T12:00:00Z", "headlines": []},
        rel="",
    )
    assert 'id="nxWire"' in html
    assert 'id="nxWireList"' in html and 'id="nxWireState"' in html
    assert "live/wires.json" in html
    assert "x.com/mastermindx001" in html
    assert "mastermindnews1" not in html
    # the shared lane row is present and precedes the panel
    assert html.index('id="nxSeg"') < html.index('id="nxWire"')


def test_the_rail_renders_even_when_the_ranked_feed_is_empty():
    """The wire is a live surface; a quiet news day for the RANKED board must not
    take it off the page. This is exactly what the split {% if FEED %} guards."""
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
                             undefined=jinja2.ChainableUndefined, autoescape=False)
    html = env.get_template("news.html.j2").render(news_feed=[], macro_news={}, rel="")
    assert 'id="nxWire"' in html


def test_china_desks_drop_the_follow_line():
    """x.com is unreachable behind the GFW; these pages' readers are presumptively
    there, so the CTA would be a dead link for the audience that page is for."""
    jinja2 = pytest.importorskip("jinja2")
    base = (ROOT / "templates" / "report_base.html.j2").read_text(encoding="utf-8")
    assert "{% block foot_social %}" in base
    for name in ("china_intel", "china_radar", "china_altdata",
                 "china_policy_watch", "china_news", "china_special_situations"):
        src = (ROOT / "templates" / (name + ".html.j2")).read_text(encoding="utf-8")
        assert "{% block foot_social %}{% endblock %}" in src, name


def test_marketing_mail_keeps_the_handle_out_of_the_chinese_half():
    mailer = pytest.importorskip("app.mailer")
    html, text = mailer.render_email("T", "标题", [{"en": "Body.", "zh": "正文。"}],
                                     follow=True)
    assert "Follow the desk on X" in html
    assert "在 X 上关注我们" not in html
    assert "X 账号" not in text


def test_no_cta_points_at_a_dark_account():
    """@mastermindnews1 is wired but DISABLED in config/marketing.yml, so it
    receives nothing; a CTA to it advertises an empty feed."""
    mailer = pytest.importorskip("app.mailer")
    assert mailer._X_HANDLES == ("mastermindx001",)
    for rel in ("templates/news.html.j2", "templates/report_base.html.j2",
                "templates/press/news_front.html.j2",
                "templates/press/research_front.html.j2"):
        assert "mastermindnews1" not in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_the_suite_is_wired_into_a_ci_job():
    """This repo has no broad pytest sweep: a suite named by NO job runs nowhere."""
    jobs = (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text(encoding="utf-8")
    assert "tests/test_wires_rail_b4b.py" in jobs
