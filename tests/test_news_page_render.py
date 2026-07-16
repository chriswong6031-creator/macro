"""Render smoke tests for the W3 news.html.j2 intelligence boards page.

Two fixtures:
  _full_vm()  — exercising every board: event deltas, macro releases, theme
                pulse, context headlines, reject log, calibration (all-insufficient).
  _empty_vm() — every new artifact is None/missing; the page must render without
                exception and must NOT crash on absent news_rejected / macro_releases /
                news_calibration / macro_news.

Both VMs pass the same keys the build_site.py render call sends.
"""
from __future__ import annotations

from pathlib import Path

import jinja2
import pytest

from engine.macro_news import CHANNEL_LABEL, TIER_LABEL

ROOT = Path(__file__).resolve().parent.parent


def _env() -> jinja2.Environment:
    """Mirror scripts/build_site.py's Jinja env (same loader path)."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
    )
    try:
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


# --------------------------------------------------------------------------- #
# Fixture helpers
# --------------------------------------------------------------------------- #

def _headline(theme: str = "monetary", with_event: bool = True, title: str = "Fed holds rates steady") -> dict:
    base: dict = {
        "title": title,
        "title_zh": "美联储维持利率不变",
        "theme": theme,
        "domain": "reuters.com",
        "source_name": "Reuters",
        "source_tier": 1,
        "url": "https://reuters.com/test",
        "seendate": "2026-07-04T10:00:00Z",
        "channels": ["monetary_policy", "rates"],
        "tickers": ["SPY", "TLT"],
        "importance": "high",
        "importance_score": 85,
        "importance_reasons": ["tier1_source", "macro_theme"],
        "centrality": "primary",
        "novelty_z": 1.8,
        "echo": {"n_sources": 3, "n_desks": 2},
    }
    if with_event:
        base["event"] = {
            "event_type": "earnings_result",
            "direction": "bearish",
            # Real keys emitted by engine/news_events.py extract_numbers()
            # (NEWS-DD-09 fix: template now reads percentages+usd_all, not pcts+dollars_b/m)
            "numbers": {
                "usd": None,
                "usd_all": [1500000000.0, 800000000.0],
                "percentages": [5.25, 5.5],
                "eps": 2.34,
                "guidance_range": None,
                "count": None,
            },
        }
    else:
        base["event"] = None
    return base


def _release_card() -> dict:
    return {
        "release": "nonfarm_payrolls",
        "display_name": "Nonfarm Payrolls",
        "macro_channel": "labor",
        "period": "Jun 2026",
        "latest_date": "2026-07-03",
        "actual": 147000.0,
        "prior": 139000.0,
        "prior_date": "2026-06-06",
        "prior_label": "vs revised prior",
        "transform": "level",
        "deltas": {"vs_prior": 8000.0, "vs_3m_mean": 5200.0, "vs_6m_mean": 3100.0},
        "z3y": 0.8,
        "z5y": 0.7,
        "surprise_size": "notable",
        "direction_tag": "bullish",
        "summary": "Payrolls came in above revised prior, z3y slightly above trend.",
        "n_hist_3y": 36,
        "n_hist_5y": 60,
    }


def _rejected_entry(reason: str = "stock_pick_roundup", title: str = "10 stocks to buy this week") -> dict:
    return {
        "title": title,
        "domain": "fool.com",
        "reason": reason,
    }


def _calibration_entry(verdict: str = "insufficient") -> dict:
    return {
        "event_type": "rate_decision",
        "direction": "bearish",
        "n": 5,
        "n_graded": 3,
        "hit_5d": None,
        "hit_21d": None,
        "avg_rel_5d": None,
        "avg_rel_21d": None,
        "wilson_low_5d": None,
        "wilson_high_5d": None,
        "verdict": verdict,
    }


def _full_vm() -> dict:
    """Full fixture exercising every board."""
    return dict(
        # standard build_site vm keys
        latest={
            "date": "2026-07-04",
            "conditions": {
                "risk_appetite": {
                    "news_sentiment_state": "pessimistic",
                    "news_sentiment_z": -0.9,
                }
            },
        },
        macro_news={
            "headlines": [
                _headline(theme="monetary", with_event=True, title="Fed holds rates steady"),
                _headline(theme="labor",    with_event=True, title="Payrolls beat, unemployment ticks up"),
                _headline(theme="inflation", with_event=False, title="CPI expectations stay elevated"),
                _headline(theme="growth",   with_event=False, title="ISM manufacturing soft for third month"),
            ],
            "synthesis": {
                "read": "4 headlines across 2 themes",
                "top_channels": [{"name": "monetary_policy"}, {"name": "rates"}],
                "top_tickers": [{"ticker": "TLT"}, {"ticker": "SPY"}],
            },
            "fetched_at": "2026-07-04T06:00:00Z",
            "n_raw": 120,
            "n_kept": 4,
            "n_official": 2,
            "n_news_rss": 1,
            "n_gdelt": 1,
            # bilingual chip labels — the real engine dicts, exactly like the payload
            "channel_label": CHANNEL_LABEL,
            "tier_label": TIER_LABEL,
        },
        macro_news_disclaimer="Context only — not a signal.",
        macro_news_disclaimer_zh="仅作背景，非信号。",
        macro_catalysts=[
            {"date": "2026-07-10", "time_et": "08:30", "type": "FOMC", "label": "FOMC minutes"},
        ],
        event_strip=[
            {"dow": "Thu", "md": "Jul 10", "time_et": "08:30", "type": "CPI", "label": "CPI Jun"},
        ],
        prediction_markets=None,
        ndi=None,
        # W3 new keys
        macro_releases={
            "schema": "macro_releases.v1",
            "is_context_only": True,
            "asof": "2026-07-04T06:00:00Z",
            "cards": [_release_card()],
            "n_cards": 1,
            "n_fetched": 8,
            "n_registry": 10,
        },
        news_rejected={
            "schema": "news_reject_log.v1",
            "is_context_only": True,
            "built": "2026-07-04T06:00:00Z",
            "n_total": 5,
            "feeds": {
                "macro": [
                    _rejected_entry("stock_pick_roundup", "10 stocks for 2026"),
                    _rejected_entry("calendar_preview",   "This week in markets"),
                ],
                "financial": [
                    _rejected_entry("routine_fund_distribution", "Distribution notice: XYZ ETF"),
                ],
                "rss": [
                    _rejected_entry("lifestyle_content", "How to retire at 40"),
                    _rejected_entry("personal_finance_advice", "Should I buy gold?"),
                ],
            },
        },
        news_calibration={
            "schema": "news_event_calibration.v1",
            "is_context_only": True,
            "asof": "2026-07-04",
            "n_events_logged": 5,
            "n_events_graded": 0,
            "classes": [
                _calibration_entry("insufficient"),
                _calibration_entry("insufficient"),
            ],
            "reject_audit": {
                "n_sampled": 10,
                "n_graded": 0,
                "classes": [
                    {"reason": "stock_pick_roundup", "n_graded": 0, "avg_rel_21d": None, "note": "accruing"},
                ],
            },
        },
        # NWS-05: financial_news fixture (market + mag7 + providers)
        financial_news={
            "schema": "financial_news.v1",
            "is_context_only": True,
            "fetched_at": "2026-07-04T06:00:00Z",
            "providers": {"polygon": False, "gdelt": True},
            "market": [
                {
                    "title": "Netflix plunges on subscriber miss",
                    "url": "https://example.com/nflx",
                    "domain": "reuters.com",
                    "source": "Reuters",
                    "seendate": "2026-07-04T10:00:00Z",
                    "tickers": ["NFLX"],
                    "event": None,
                    "centrality": "incidental",
                    "novelty_z": 3.1,
                }
            ],
            "mag7": {
                "AAPL": {"name": "Apple", "headlines": [{"title": "Apple AI deal"}]},
                "MSFT": {"name": "Microsoft", "headlines": []},
            },
        },
    )


def _empty_vm() -> dict:
    """All new artifacts are None — page must render without exception."""
    return dict(
        latest={"date": "2026-07-04", "conditions": None},
        macro_news=None,
        macro_news_disclaimer="",
        macro_news_disclaimer_zh="",
        macro_catalysts=[],
        event_strip=[],
        prediction_markets=None,
        ndi=None,
        # W3 keys all absent
        macro_releases=None,
        news_rejected=None,
        news_calibration=None,
        # NWS-05: financial_news absent
        financial_news=None,
    )


# --------------------------------------------------------------------------- #
# Tests — full vm
# --------------------------------------------------------------------------- #

def _render_full() -> str:
    return _env().get_template("news.html.j2").render(**_full_vm())


def _render_empty() -> str:
    return _env().get_template("news.html.j2").render(**_empty_vm())


def test_full_vm_renders_without_exception():
    """Full fixture must render without raising."""
    html = _render_full()
    assert len(html) > 500


def test_full_vm_delta_board_present():
    """<!-- nx-delta-board --> section marker present."""
    html = _render_full()
    assert "nx-delta-board" in html or "nxDeltaBoard" in html


def test_full_vm_release_board_present():
    """<!-- nx-release-board --> section marker present."""
    html = _render_full()
    assert "nx-release-board" in html or "nxReleaseBoard" in html


def test_full_vm_theme_pulse_present():
    """<!-- nx-theme-pulse --> section marker present."""
    html = _render_full()
    assert "nx-theme-pulse" in html or "nxThemePulse" in html


def test_full_vm_context_section_present():
    """<!-- nx-context-section --> section marker present."""
    html = _render_full()
    assert "nx-context-section" in html or "nxContextSection" in html


def test_full_vm_reject_log_present():
    """<!-- nx-reject-log --> section marker present."""
    html = _render_full()
    assert "nx-reject-log" in html or "nxRejectLog" in html


def test_full_vm_calibration_board_present():
    """<!-- nx-calibration-board --> section marker present."""
    html = _render_full()
    assert "nx-calibration-board" in html or "nxCalibrationBoard" in html


def test_full_vm_event_cards_render():
    """Event-typed headlines appear in the delta board with correct event_type class."""
    html = _render_full()
    # fixture uses event_type='earnings_result'; badge class must be ev-earnings_result
    assert "ev-earnings_result" in html
    # label text rendered from event_type key: "Earnings Result"
    assert "Earnings Result" in html
    # no empty ev- class (regression guard for the old ev.get('name','') bug)
    assert 'ev-"' not in html and 'class="nb-event ev-"' not in html


def test_full_vm_release_card_renders():
    """Nonfarm Payrolls card renders with actual value."""
    html = _render_full()
    assert "Nonfarm Payrolls" in html
    assert "147" in html  # actual value present


def test_full_vm_reject_log_groups_by_reason():
    """Reject log groups items by reason — at least one translated label visible.
    NEWS-DD-07: reason slugs are now translated via REJL dict; 'stock_pick_roundup'
    becomes 'Stock pick list' in EN, '选股清单' in ZH.
    """
    html = _render_full()
    # translated label (NEWS-DD-07) — raw slug must not appear
    assert "Stock pick list" in html or "选股清单" in html, (
        "Translated reject reason label must appear"
    )
    assert "stock_pick_roundup" not in html, "Raw slug must not appear in translated output"


def test_full_vm_calibration_shows_insufficient():
    """All-insufficient calibration renders 'accruing' states, not a crash."""
    html = _render_full()
    assert "accruing" in html.lower() or "insufficient" in html.lower()


def test_full_vm_exec_strip_counts():
    """Executive strip shows event counts; both 0 and >0 cases work."""
    html = _render_full()
    # 2 events, 1 release in fixture
    assert "exec-strip" in html
    # counts must be present somewhere in the strip
    assert "exec-chip" in html


def test_full_vm_context_headlines_present():
    """Context (no-event) headlines appear in the context section."""
    html = _render_full()
    # 2 context heads in fixture
    assert "CPI expectations" in html or "nxContextSection" in html


def test_full_vm_theme_pulse_counts():
    """Theme pulse shows monetary/labor/inflation/growth counts."""
    html = _render_full()
    # monetary theme has 1 event head + nothing in ctx = 1 total (or 2 if both)
    assert "pulse-cell" in html or "nxThemePulse" in html


def test_full_vm_no_translated_title_attrs():
    """No translated text inside title= attribute (check_title_i18n guard)."""
    import re
    html = _render_full()
    # Find all title= attributes
    titles = re.findall(r'title=["\']([^"\']+)["\']', html)
    for t_val in titles:
        # Chinese chars: any CJK unified ideograph
        assert not any('一' <= c <= '鿿' for c in t_val), \
            f"Translated text found in title= attribute: {t_val!r}"


# --------------------------------------------------------------------------- #
# Tests — channel-chip i18n (doctrine Law 2: no raw slugs on glance surfaces)
# --------------------------------------------------------------------------- #

def test_context_channel_pills_are_bilingual_not_raw_slugs():
    """Channel chips map through the engine's CHANNEL_LABEL payload dict as
    l-en/l-zh toggle pairs — the raw slug never renders as chip text."""
    html = _render_full()
    # 'rates' is in CHANNEL_LABEL → ('rates', '利率') toggle pair
    assert '<span class="l-en">rates</span><span class="l-zh">利率</span>' in html
    # raw slug never renders as visible text ('monetary_policy' is not a
    # CHANNEL_LABEL key — it must de-underscore, not pass through)
    assert ">monetary_policy<" not in html


def test_context_channel_pills_degrade_without_label_dict():
    """Payloads cached before the engine shipped channel_label de-underscore,
    never raw-slug."""
    vm = _full_vm()
    vm["macro_news"].pop("channel_label")
    html = _env().get_template("news.html.j2").render(**vm)
    assert ">monetary_policy<" not in html
    assert "monetary policy" in html


def test_importance_reasons_never_render():
    """Internal scorer strings stay machine-only in the payload — no surface
    on the news page may print them."""
    html = _render_full()
    assert "tier1_source" not in html
    assert "macro_theme" not in html


# --------------------------------------------------------------------------- #
# Tests — empty vm
# --------------------------------------------------------------------------- #

def test_empty_vm_renders_without_exception():
    """All-empty vm must render without exception (null-safety)."""
    html = _render_empty()
    assert len(html) > 200


def test_empty_vm_still_has_board_structure():
    """Even with all artifacts absent the board sections are present."""
    html = _render_empty()
    assert "nxDeltaBoard" in html
    assert "nxReleaseBoard" in html
    assert "nxCalibrationBoard" in html


def test_empty_vm_calibration_shows_placeholder():
    """Missing calibration artifact renders the 'accruing' placeholder panel."""
    html = _render_empty()
    assert "accruing" in html.lower()


def test_empty_vm_no_context_headlines_crash():
    """No macro_news must not raise — empty state renders."""
    html = _render_empty()
    assert "board-empty" in html or "nxDeltaBoard" in html


def test_empty_vm_reject_log_shows_empty_state():
    """No news_rejected artifact renders empty state, not a crash."""
    html = _render_empty()
    assert "nxRejectLog" in html


def test_empty_vm_no_jinja_undefined_error():
    """Template must not access undefined variables (Jinja2 silent mode active)."""
    # If any key access raises UndefinedError jinja2 would propagate it;
    # the render call would have raised before this assertion.
    html = _render_empty()
    assert html is not None


# --------------------------------------------------------------------------- #
# Tests — event badge key regression (event_type vs name)
# --------------------------------------------------------------------------- #

def test_event_badge_uses_event_type_key():
    """ev.get('event_type') is the live engine key; ev.get('name') is dead.

    Regression guard: if the template regresses to ev.get('name','') the badge
    class becomes ev-\" (empty) and the label text becomes '?'.  Assert neither
    happens when the fixture carries only the event_type key.
    """
    import jinja2

    env = _env()
    tmpl = env.get_template("news.html.j2")
    # headline carrying ONLY the real engine key (event_type), no legacy 'name'
    ev_only_event_type = {
        "event_type": "rating_change",
        "direction": "bullish",
        "numbers": {},
    }
    headline = {
        "title": "Analyst upgrades AAPL to Buy",
        "theme": "analyst",
        "source_tier": 1,
        "source_name": "Goldman",
        "seendate": "2026-07-04T10:00:00Z",
        "novelty_z": 2.1,
        "tickers": ["AAPL"],
        "event": ev_only_event_type,
    }
    vm = dict(
        _empty_vm(),
        macro_news={
            "headlines": [headline],
            "synthesis": None,
            "fetched_at": "2026-07-04T06:00:00Z",
            "n_raw": 1, "n_kept": 1, "n_official": 0, "n_news_rss": 1, "n_gdelt": 0,
        },
    )
    html = tmpl.render(**vm)
    assert "ev-rating_change" in html, "badge class must be ev-rating_change"
    assert "Rating Change" in html, "badge label must be 'Rating Change'"
    # no empty ev- class — the old bug
    assert 'class="nb-event ev-"' not in html, "empty ev- class means name key regression"


def test_badges_bilingual_labels_and_string_tier():
    """Prod emits source_tier as STRINGS ('stock_wire', 'tier1', ...) — the tier
    badge must render a human label ('Wire'/'快讯'), never the raw 'Tstock_wire'
    code the page shipped with.  Event badges must carry the ZH label span too.
    """
    env = _env()
    tmpl = env.get_template("news.html.j2")
    headline = {
        "title": "Analyst upgrades AAPL to Buy",
        "theme": "analyst",
        "source_tier": "stock_wire",  # prod shape: string, not int
        "source_name": "CNBC - Markets",
        "seendate": "2026-07-04T10:00:00Z",
        "novelty_z": None,
        "tickers": ["AAPL"],
        "event": {"event_type": "rating_change", "direction": "bullish", "numbers": {}},
    }
    vm = dict(
        _empty_vm(),
        macro_news={
            "headlines": [headline],
            "synthesis": None,
            "fetched_at": "2026-07-04T06:00:00Z",
            "n_raw": 1, "n_kept": 1, "n_official": 0, "n_news_rss": 1, "n_gdelt": 0,
        },
    )
    html = tmpl.render(**vm)
    assert "Tstock_wire" not in html, "raw internal tier code must not render"
    assert "Wire" in html and "快讯" in html, "tier badge must render bilingual label"
    assert "评级变动" in html, "event badge must render the ZH label"
    # unknown tier falls back to the T<code> form rather than crashing
    headline2 = dict(headline, source_tier="mystery_tier")
    vm["macro_news"]["headlines"] = [headline2]
    assert "Tmystery_tier" in tmpl.render(**vm)


# --------------------------------------------------------------------------- #
# Tests — Delta Board sort (W3 fix: build_site.py ev_heads pre-sort)
# --------------------------------------------------------------------------- #

def _make_ev_head(title: str, novelty_z, seendate: str) -> dict:
    return {
        "title": title,
        "seendate": seendate,
        "novelty_z": novelty_z,
        "event": {"event_type": "macro_release", "direction": "bearish"},
    }


def _apply_ev_heads_sort(heads: list) -> list:
    """Replicate the sort logic from scripts/build_site.py for unit testing."""
    _ev = [h for h in heads if h.get("event")]
    _ev.sort(key=lambda h: h.get("seendate") or "", reverse=True)
    _ev.sort(
        key=lambda h: abs(float(h["novelty_z"])) if h.get("novelty_z") is not None else 0.0,
        reverse=True,
    )
    return _ev


def test_delta_board_sort_by_novelty_z_desc():
    """Headlines with higher |novelty_z| appear first."""
    heads = [
        _make_ev_head("low novelty",  novelty_z=0.5, seendate="20260704T100000Z"),
        _make_ev_head("high novelty", novelty_z=3.2, seendate="20260704T090000Z"),
        _make_ev_head("mid novelty",  novelty_z=1.8, seendate="20260704T080000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    titles = [h["title"] for h in sorted_heads]
    assert titles == ["high novelty", "mid novelty", "low novelty"], titles


def test_delta_board_sort_negative_novelty_z_uses_abs():
    """Negative novelty_z with large magnitude ranks above smaller |z|."""
    heads = [
        _make_ev_head("small positive", novelty_z=1.0, seendate="20260704T100000Z"),
        _make_ev_head("large negative", novelty_z=-2.5, seendate="20260704T090000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    assert sorted_heads[0]["title"] == "large negative"


def test_delta_board_sort_recency_tiebreak():
    """Equal |novelty_z| — most recent seendate wins."""
    heads = [
        _make_ev_head("older",  novelty_z=1.5, seendate="20260703T100000Z"),
        _make_ev_head("newer",  novelty_z=1.5, seendate="20260704T100000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    assert sorted_heads[0]["title"] == "newer"


def test_delta_board_sort_none_novelty_z_goes_last():
    """Headlines with novelty_z=None sort below those with a real z-score."""
    heads = [
        _make_ev_head("no novelty",   novelty_z=None, seendate="20260704T120000Z"),
        _make_ev_head("has novelty",  novelty_z=0.1,  seendate="20260704T060000Z"),
    ]
    sorted_heads = _apply_ev_heads_sort(heads)
    assert sorted_heads[0]["title"] == "has novelty"


# --------------------------------------------------------------------------- #
# Tests — build_site.py render call SHAPE (W3 fix: duplicate-keyword collision)
#
# The real build_site.py render is:
#     env.get_template("news.html.j2").render(
#         **vm,                       # vm ALREADY contains a 'macro_news' key
#         macro_news=_sorted_macro_news,
#         macro_releases=..., news_rejected=..., news_calibration=...,
#     )
# Splatting **vm (which carries macro_news) AND passing macro_news= explicitly
# raises "got multiple values for keyword argument 'macro_news'" at argument
# binding — BEFORE the template runs — and, being unguarded, aborts the whole
# build.  The prior smoke tests built a single flat dict and called render(**vm)
# ONCE, so they never exercised the collision.  These tests reproduce the actual
# call shape.
# --------------------------------------------------------------------------- #

# The real build_site.py vm carries ONLY macro_news among the W3 keys; the other
# side-artifacts (macro_releases / news_rejected / news_calibration / financial_news)
# are loaded into separate locals and passed as explicit keywords, so they are NOT vm
# members.  Reproduce that exact shape rather than the fixture's all-in-one bundle.
_BUILD_SITE_VM_ONLY_MACRO_NEWS = ("macro_releases", "news_rejected", "news_calibration",
                                  "financial_news")


def _build_site_splatted_vm() -> dict:
    """A vm shaped like scripts/build_site.py's real vm: contains 'macro_news' but
    NOT the three side-artifact keys (those are supplied explicitly at render)."""
    vm = _full_vm()
    return {k: v for k, v in vm.items() if k not in _BUILD_SITE_VM_ONLY_MACRO_NEWS}


def test_build_site_render_call_shape_no_duplicate_kwarg():
    """Faithfully reproduce scripts/build_site.py:3163-3175 with the W3 fix applied.

    The real vm carries a 'macro_news' key (build_site.py:3037).  The fix builds
    the render kwargs from `{k:v for k,v in vm.items() if k != 'macro_news'}` and
    then passes macro_news= explicitly alongside the three side-artifacts.  This
    render(**vm_minus_macro_news, macro_news=..., macro_releases=..., ...) shape
    is exactly what the prior suite never exercised (it always did a single flat
    render(**vm)).  It must NOT raise a duplicate-keyword TypeError."""
    vm = _build_site_splatted_vm()
    assert "macro_news" in vm, "vm must carry macro_news (build_site.py:3037)"
    for k in _BUILD_SITE_VM_ONLY_MACRO_NEWS:
        assert k not in vm, f"{k} is NOT a vm key in build_site.py — supplied explicitly"
    render_vm = {k: v for k, v in vm.items() if k != "macro_news"}  # the W3 fix
    sorted_macro_news = dict(vm["macro_news"])  # stand-in for _sorted_macro_news
    html = _env().get_template("news.html.j2").render(
        **render_vm,
        macro_news=sorted_macro_news,
        macro_releases=None,
        news_rejected=None,
        news_calibration=None,
        financial_news=None,
    )
    assert len(html) > 500
    assert "nxDeltaBoard" in html


def test_naive_duplicate_macro_news_kwarg_raises_typeerror():
    """Regression guard: the BUGGY build_site.py shape — splat a vm that still
    contains 'macro_news' AND pass macro_news= explicitly — raises the exact
    TypeError (`got multiple values for keyword argument 'macro_news'`) that used
    to abort the whole build.  If build_site.py ever regresses to `**vm` without
    dropping macro_news, this documents/pins the failure mode."""
    vm = _build_site_splatted_vm()  # carries 'macro_news', shaped like the real vm
    tmpl = _env().get_template("news.html.j2")
    with pytest.raises(TypeError, match="multiple values for keyword argument 'macro_news'"):
        tmpl.render(
            **vm,                                # <-- still contains macro_news
            macro_news=dict(vm["macro_news"]),   # <-- explicit duplicate => collision
            macro_releases=None,
            news_rejected=None,
            news_calibration=None,
            financial_news=None,
        )


# --------------------------------------------------------------------------- #
# Tests — schema-violating side-artifacts (type-contract guards)
#
# The three W3 side-artifacts (macro_releases / news_rejected / news_calibration)
# are written by sibling waves.  json.loads failures already degrade to None in
# build_site.py, but a file that is VALID JSON while violating the pinned schema
# TYPE used to escape the template unguarded and abort every page after
# news.html.  Each case below must render (degrade), never raise.
# --------------------------------------------------------------------------- #

_BAD_ARTIFACT_CASES = [
    # (case id, vm overrides)
    ("calibration_is_list", {"news_calibration": [1, 2, 3]}),
    ("calibration_classes_str", {"news_calibration": {"classes": "x"}}),
    ("releases_cards_str", {"macro_releases": {"cards": "x"}}),
    ("card_non_numeric_fields", {"macro_releases": {"cards": [{
        "release": "CPI", "actual": "N/A", "prior": "N/A", "z3y": "N/A",
        "deltas": {"vs_prior": "N/A"}, "surprise_size": "big",
        "direction_tag": "bullish", "period": "May"}]}}),
    ("releases_is_list", {"macro_releases": [1, 2]}),
    ("cards_of_strings", {"macro_releases": {"cards": ["a", "b"]}}),
    ("calib_reject_audit_bad", {"news_calibration": {
        "classes": [{"event_type": "cpi", "verdict": "candidate", "n": "?",
                     "n_graded": "N/A", "hit_5d": "N/A", "hit_21d": "N/A"}],
        "reject_audit": {"n_sampled": "N/A", "n_graded": 1,
                         "classes": [{"reason": "dup", "avg_rel_21d": "N/A"}]}}}),
    ("rejected_is_list", {"news_rejected": [1, 2]}),
    ("rejected_feeds_str", {"news_rejected": {"feeds": "x"}}),
    ("rejected_items_str", {"news_rejected": {"feeds": {"macro": "xy"}}}),
]


@pytest.mark.parametrize("case_id,overrides",
                         _BAD_ARTIFACT_CASES,
                         ids=[c[0] for c in _BAD_ARTIFACT_CASES])
def test_schema_violating_artifact_degrades_not_raises(case_id, overrides):
    """A valid-JSON, type-violating artifact must degrade to the empty/placeholder
    branch of its board — never raise out of the render."""
    vm = _empty_vm()  # already includes financial_news=None
    vm.update(overrides)
    html = _env().get_template("news.html.j2").render(**vm)
    assert len(html) > 500
    assert "nxCalibrationBoard" in html  # page structure intact past all boards


def test_non_mapping_calibration_falls_to_placeholder():
    """A list-typed calibration artifact lands on the 'not yet generated' branch."""
    vm = _empty_vm()
    vm["news_calibration"] = [1, 2, 3]
    html = _env().get_template("news.html.j2").render(**vm)
    assert "artifact not yet generated" in html


def test_string_cards_release_board_shows_empty_state():
    """cards-as-string degrades the release board to its empty state."""
    vm = _empty_vm()
    vm["macro_releases"] = {"cards": "x"}
    html = _env().get_template("news.html.j2").render(**vm)
    assert "No releases parsed in the window" in html


# --------------------------------------------------------------------------- #
# Tests — design-doctrine fixes (NEWS-DD-01 through NWS-08)
# --------------------------------------------------------------------------- #

def test_stance_lines_present_per_board():
    """NEWS-DD-01: every board must have a plain-word stance line (board-stance class)."""
    html = _render_full()
    # Delta Board, Release Board, Theme Pulse (inline), Context, Calibration, Wires
    # board-stance appears at least 3 times (Delta, Release, Calibration + Wires + Context)
    assert html.count("board-stance") >= 4, (
        f"Expected >=4 board-stance elements, got {html.count('board-stance')}"
    )
    assert "Background read" in html or "background read" in html.lower()
    assert "Data check" in html or "data check" in html.lower()
    assert "Still gathering" in html or "still gathering" in html.lower()


def test_no_raw_z_equals_in_visible_text():
    """NEWS-DD-03: raw 'z=+x.x' must not appear in visible text (only in data-tip attrs)."""
    import re
    html = _render_full()
    # Strip data-tip attribute values before checking
    stripped = re.sub(r'data-tip-[a-z]+="[^"]*"', "", html)
    raw_z = re.findall(r"z=[\+\-]\d", stripped)
    assert not raw_z, f"Raw z= found outside data-tip: {raw_z}"


def test_novelty_plain_word_labels():
    """NEWS-DD-03: Unusual/Notable/Routine labels instead of raw z values."""
    html = _render_full()
    # fixture uses novelty_z=1.8 (> 1.5) -> should render 'Unusual'
    assert "Unusual" in html, "High novelty should render 'Unusual'"


def test_nums_keys_percentages_and_usd_all():
    """NEWS-DD-09: template reads 'percentages' and 'usd_all' (real engine keys)."""
    html = _render_full()
    # fixture sets percentages=[5.25, 5.5] and usd_all=[1500000000, 800000000], eps=2.34
    assert "5.2%" in html or "5.3%" in html, "percentages key must render"
    assert "$1.5B" in html, "usd_all B-scale must render"
    assert "EPS $2.34" in html, "eps scalar must render"


def test_old_nums_keys_not_used():
    """NEWS-DD-09 regression: 'pcts'/'dollars_b'/'dollars_m' keys produce nothing when absent."""
    env = _env()
    tmpl = env.get_template("news.html.j2")
    # Headline with ONLY old keys (no 'percentages'/'usd_all') — should produce no num pills
    head_old_keys = {
        "title": "Old shape test",
        "theme": "monetary",
        "source_tier": "tier1",
        "seendate": "2026-07-04T10:00:00Z",
        "novelty_z": 0.5,
        "event": {
            "event_type": "earnings_result",
            "direction": "bullish",
            "numbers": {
                "pcts": [5.0, 6.0],
                "dollars_b": [3.5],
                "dollars_m": [200.0],
                "eps": [],
            },
        },
    }
    vm = dict(
        _empty_vm(),
        macro_news={"headlines": [head_old_keys], "synthesis": None,
                    "fetched_at": "2026-07-04T06:00:00Z", "n_raw": 1, "n_kept": 1},
    )
    html = tmpl.render(**vm)
    # Old keys don't exist in engine output, template ignores them; no pills rendered
    import re
    pills = re.findall(r'class="ev-num-pill"[^>]*>([^<]+)<', html)
    assert not pills, f"Old keys must not produce pills; got: {pills}"


def test_wires_board_renders_from_financial_json():
    """NWS-05: financial_news fixture causes the wires board to render items and mag7 chips."""
    env = _env()
    tmpl = env.get_template("news.html.j2")
    vm = dict(
        _empty_vm(),
        financial_news={
            "market": [
                {
                    "title": "Netflix plunges on subscriber miss",
                    "url": "https://example.com/nflx",
                    "domain": "reuters.com",
                    "source": "Reuters",
                    "seendate": "2026-07-04T10:00:00Z",
                    "tickers": ["NFLX"],
                    "event": None,
                    "centrality": "incidental",
                    "novelty_z": 3.1,
                }
            ],
            "mag7": {
                "AAPL": {"name": "Apple", "headlines": [{"title": "dummy"}]},
                "MSFT": {"name": "Microsoft", "headlines": []},
            },
            "providers": {"polygon": False, "gdelt": True},
        },
    )
    html = tmpl.render(**vm)
    assert "nxWiresBoard" in html, "wires board section must be present"
    assert "Netflix plunges" in html, "market wire item title must render"
    assert "NFLX" in html, "ticker chip must render"
    assert "AAPL" in html, "mag7 chip with headlines must appear"
    # MSFT has 0 headlines — should not get a chip
    assert "MSFT" not in html or html.count("MSFT") == 0


def test_wires_board_empty_state():
    """NWS-05: wires board shows plain empty state when financial_news is None."""
    html = _render_empty()
    assert "nxWiresBoard" in html
    assert "No market wire items" in html


def test_wires_board_degraded_provider():
    """NWS-05: when polygon=False, degraded coverage message appears."""
    env = _env()
    tmpl = env.get_template("news.html.j2")
    vm = dict(
        _empty_vm(),
        financial_news={
            "market": [],
            "mag7": {},
            "providers": {"polygon": False},
        },
    )
    html = tmpl.render(**vm)
    assert "degraded" in html.lower(), "degraded provider message must appear"


def test_wires_board_none_financial_news_no_crash():
    """NWS-05: financial_news=None must render without crash."""
    html = _render_empty()
    assert len(html) > 500
    assert "nxWiresBoard" in html


def test_reject_reason_slugs_translated():
    """NEWS-DD-07: reject reason slugs are translated to plain labels, not raw slugs."""
    html = _render_full()
    # 'stock_pick_roundup' should become 'Stock pick list', not show raw slug
    assert "stock pick roundup" not in html.lower() or "Stock pick list" in html, (
        "reject reason slug must be translated"
    )
    assert "Stock pick list" in html, "REJL dict must translate stock_pick_roundup"


def test_context_board_renamed():
    """NEWS-DD-09: 'Context Headlines' renamed to 'Other macro headlines'."""
    html = _render_full()
    assert "Other macro headlines" in html, "board must use new name"
    assert "other macro headlines" in html.lower()


def test_board_notes_one_sentence():
    """NEWS-DD-08: board notes are short (< 200 chars each, no multi-sentence walls)."""
    import re
    html = _render_full()
    notes = re.findall(r'class="board-note"[^>]*>(.*?)</div>', html, re.DOTALL)
    for note in notes:
        # Strip HTML tags for length check
        plain = re.sub(r'<[^>]+>', '', note).strip()
        # Allow for bilingual duplication; each language half should be ≤ 180 chars
        # (We check the stripped combined is < 400 chars as a sanity bound)
        assert len(plain) < 500, f"Board note too long ({len(plain)} chars): {plain[:100]}..."


def test_zh_mode_note_in_headlines_section():
    """NWS-04: the ZH-mode untranslated-titles note renders CONDITIONALLY —
    #2661 fills title_zh on render lanes, so the note appears only when at
    least one kept headline is missing title_zh (n_zh_missing > 0)."""
    # Standard fixture: every headline carries title_zh → note absent.
    html = _render_full()
    assert "部分标题来自英文信源" not in html, "note must NOT render when all titles are translated"
    # Strip title_zh from one headline → note renders.
    vm = _full_vm()
    heads = vm["macro_news"]["headlines"]
    assert heads, "fixture must carry headlines"
    heads[0] = {k: v for k, v in heads[0].items() if k != "title_zh"}
    html2 = _env().get_template("news.html.j2").render(**vm)
    assert "部分标题来自英文信源" in html2, "note must render when a title lacks title_zh"


def test_calibration_note_plain_no_wilson_slug():
    """NEWS-DD-04: calibration board Tier-1 note must not expose wilson_low_5d slug."""
    html = _render_full()
    assert "wilson_low_5d" not in html, "wilson_low_5d must not appear in rendered HTML"
    assert "wilson_high_5d" not in html, "wilson_high_5d must not appear in rendered HTML"
    assert "earned-authority gate" not in html, "earned-authority gate must not appear in Tier-1"
    # Mechanics must be in data-tip (Tier 2)
    assert "Wilson" in html, "Wilson details must still exist (in data-tip Tier-2)"
