"""Tests for engine.uk_policy_brain — the UK (HM Treasury / GOV.UK) policy desk.

Mirrors the test shape of tests/test_policy_intent_desk.py: gate-off writes
nothing, network/model failures degrade rather than raise, the model's stance
is clamped to a closed set, and invented numbers/tickers are rejected in code.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from engine import uk_policy_brain as brain

FIXTURE = Path(__file__).parent / "fixtures" / "uk_policy_govuk_sample.json"

def _load_real_intel() -> dict:
    root = Path(__file__).parent.parent
    p = root / "data" / "policy" / "intel.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"fed": {"task_forces": []}, "administration": {"verified_levers": []},
                "rotation": {}, "predictions": [], "monitor": [], "sources": [], "caveats": []}


_REAL_INTEL = _load_real_intel()


def _clear_env(monkeypatch):
    for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", brain.GATE_ENV):
        monkeypatch.delenv(k, raising=False)


def test_gate_off_without_key_returns_none_and_writes_nothing(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    assert brain.enabled() is False
    result = brain.run(root=tmp_path)
    assert result is None
    assert not (tmp_path / "site" / "uk_policy.json").exists()


def test_unreachable_source_degrades_never_raises(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(brain.GATE_ENV, "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _boom(url, timeout=15):
        raise RuntimeError("network down")

    monkeypatch.setattr(brain, "_fetch", _boom)
    assert brain.collect() == []

    def stub_call(prompt):
        return {"summary_en": "x", "stance": "routine"}

    result = brain.run(root=tmp_path, force=True, call=stub_call)
    # No prior record and no items -> None (degrade, no exception)
    assert result is None


def test_positive_parse():
    raw = FIXTURE.read_bytes()
    items = brain._parse_search_results(raw)
    assert len(items) == 2
    it = items[0]
    assert it["headline"] if "headline" in it else it["title"]
    assert it["source_url"] if "source_url" in it else it["url"].startswith("https://www.gov.uk/")
    from datetime import datetime
    datetime.fromisoformat(it["published"])
    assert it["doc_type"]
    id1 = it["id"]
    items2 = brain._parse_search_results(raw)
    assert items2[0]["id"] == id1


def test_stance_is_clamped_to_closed_set():
    assert brain._norm_stance("bullish") == "routine"
    assert brain._norm_stance("restrictive") == "restrictive"
    assert brain._norm_stance(None) == "routine"
    assert brain._norm_stance("SUPPORTIVE") == "supportive"


def test_model_cannot_invent_numbers_or_tickers():
    excerpt = "The Treasury confirmed the plan will proceed as announced."
    bad_number = "This will cost about £4.2bn according to the plan."
    bad_ticker = "Analysts expect HSBA to benefit from this."
    assert brain._sanitize_field(bad_number, excerpt) is None
    assert brain._sanitize_field(bad_ticker, excerpt) is None
    good = "The plan will proceed as announced."
    assert brain._sanitize_field(good, excerpt) == good


def test_no_scoring_path_imports_this_desk():
    root = Path(__file__).parent.parent
    hits = []
    for base in ("engine", "scripts"):
        for p in (root / base).rglob("*.py"):
            if p.name == "uk_policy_brain.py":
                continue
            try:
                text = p.read_text()
            except Exception:
                continue
            if re.search(r"^\s*(from engine import uk_policy_brain|import engine\.uk_policy_brain)", text, re.M):
                hits.append(str(p.relative_to(root)))
    assert hits == ["scripts/build_whitehouse.py"], hits


def test_panel_renders_every_state(tmp_path):
    jinja2 = pytest.importorskip("jinja2")
    from jinja2 import Environment, FileSystemLoader
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.build_policy_watch import _uk_desk_view, brief as _brief_fn  # noqa: E402

    root = Path(__file__).parent.parent
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    tmpl = env.get_template("policy_watch.html.j2")

    base_ctx = dict(
        intel=_REAL_INTEL, counts={"total": 0, "hit": 0, "miss": 0, "hit_rate": None},
        desk=None, fed_stance=None, fed_hist={}, rot=None, rot_hist={}, dates={},
        catalysts=[], scorecard=None, generated_utc="2026-09-06 00:00 UTC",
        verified_en="", verified_zh="", source_links=[], featured_predictions=[],
        brief=_brief_fn, active_section="research", active_page="policy_watch",
    )
    for state in ("ok", "no_new", "source_outage", "stale", "gate_off"):
        raw = None if state == "gate_off" else {
            "state": state, "stance": "restrictive",
            "jurisdiction_en": "United Kingdom", "jurisdiction_zh": "英国",
            "body_en": "HM Treasury", "body_zh": "英国财政部",
            "source_label": "GOV.UK", "headline": "Test headline",
            "source_url": "https://www.gov.uk/government/news/test",
            "doc_type_en": "News story", "doc_type_zh": "新闻稿",
            "published_iso": "2026-09-04T09:30:00+00:00",
            "known_at_iso": "2026-09-04T10:00:00+00:00",
            "summary_en": "A plain summary.", "summary_zh": "简单摘要。",
            "watch_en": "Watch the next update.", "watch_zh": "关注下一次更新。",
            "excerpt": "Source excerpt text.", "provider_label": "Claude API · test",
        }
        html = tmpl.render(uk_desk=_uk_desk_view(raw), **base_ctx)
        assert f'data-uk-state="{state}"' in html
        assert 'id="uk"' in html
        assert "United Kingdom" in html and "英国" in html


def test_panel_register_and_parity(tmp_path):
    pytest.importorskip("jinja2")
    from jinja2 import Environment, FileSystemLoader
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.build_policy_watch import _uk_desk_view, brief as _brief_fn  # noqa: E402

    root = Path(__file__).parent.parent
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    tmpl = env.get_template("policy_watch.html.j2")
    base_ctx = dict(
        intel=_REAL_INTEL, counts={"total": 0, "hit": 0, "miss": 0, "hit_rate": None},
        desk=None, fed_stance=None, fed_hist={}, rot=None, rot_hist={}, dates={},
        catalysts=[], scorecard=None, generated_utc="2026-09-06 00:00 UTC",
        verified_en="", verified_zh="", source_links=[], featured_predictions=[],
        brief=_brief_fn, active_section="research", active_page="policy_watch",
    )
    raw = {
        "state": "ok", "stance": "restrictive",
        "jurisdiction_en": "United Kingdom", "jurisdiction_zh": "英国",
        "body_en": "HM Treasury", "body_zh": "英国财政部",
        "source_label": "GOV.UK", "headline": "Test headline",
        "source_url": "https://www.gov.uk/government/news/test",
        "doc_type_en": "News story", "doc_type_zh": "新闻稿",
        "published_iso": "2026-09-04T09:30:00+00:00",
        "known_at_iso": "2026-09-04T10:00:00+00:00",
        "summary_en": "A plain summary.", "summary_zh": "简单摘要。",
        "watch_en": "Watch the next update.", "watch_zh": "关注下一次更新。",
        "excerpt": "Source excerpt text.", "provider_label": "Claude API · test",
    }
    html = tmpl.render(uk_desk=_uk_desk_view(raw), **base_ctx)
    uk_section = html[html.index('id="uk"'):]
    end = uk_section.find('<section class="pw-section"', 1)
    uk_section = uk_section if end == -1 else uk_section[:end]
    for banned in ("falsifier", "refuted", "invalidated", "证伪"):
        assert banned not in uk_section
    for m in re.finditer(r'title="([^"]*)"', uk_section):
        assert not re.search(r"[一-鿿]", m.group(1))
    en_spans = re.findall(r'<span class="l-en">', uk_section)
    zh_spans = re.findall(r'<span class="l-zh">', uk_section)
    assert len(en_spans) == len(zh_spans)


def test_view_builder_never_returns_none():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.build_policy_watch import _uk_desk_view, brief as _brief_fn  # noqa: E402

    v = _uk_desk_view(None)
    assert v["state"] == "gate_off"
    v2 = _uk_desk_view({"state": "garbage", "stance": "garbage"})
    assert v2["state"] == "gate_off"
    assert v2["stance"] == "routine"
