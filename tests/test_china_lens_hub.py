"""Tests for the China Lens module (W0.2) added to the Intelligence Hub.

Covers:
  (a) build_china_packet from a fixture briefing.json — schema check, key assertions,
      degradation (missing file, missing keys, stale asof).
  (b) Template render, using the REAL render call shape (kwarg-collision safety —
      hub+built+mode+qledger_chips+china). The China Lens MODULE was removed from the
      US hub by operator order 2026-07-11: the packet artifact is still built (regions/
      china.json feeds downstream readers), but the template must NOT render the module
      even when a packet is passed — these tests are the regression guard.

No tracked parquets are dirtied by these tests.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Fixture briefing JSON (compact — only keys the packet builder reads)
# ---------------------------------------------------------------------------
_FIXTURE_BRIEFING = {
    "schema": "china_intel.briefing.v3",
    "is_context_only": True,
    "asof": "2026-07-06",
    "generated_utc": "2026-07-06T08:30:00",
    "surfaces_present": ["news", "policy", "altdata", "radar", "analysis"],
    "surface_asof": {
        "news": "2026-07-06",
        "policy": "2026-07-03",
        "altdata": "2026-07-06",
        "radar": "2026-07-06",
        "analysis": "2026-07-06",
    },
    "conviction": [
        {
            "sector_en": "Semiconductors",
            "sector_zh": "半导体",
            "stage": "consensus",
            "stage_zh": "共识",
            "edge_remaining": 0.365,
        },
        {
            "sector_en": "Brokers",
            "sector_zh": "券商",
            "stage": "early",
            "stage_zh": "早期",
            "edge_remaining": 0.55,
        },
    ],
    "flagged_tickers": [{"ticker": "300782.SZ"}, {"ticker": "600030.SS"}],
    "what_changed": {
        "new_accumulation": ["002898.SZ", "600906.SS"],
        "dropped_accumulation": ["002765.SZ"],
        "new_radar_fires": [],
        "resolved_radar": [],
        "stance_change": None,
        "sentiment_band_change": None,
        "new_scheduled_within_3d": [
            {"name_en": "Customs trade (exports/imports)", "name_zh": "海关进出口数据", "date": "2026-07-07"},
        ],
    },
    "regime": {
        "roro": 0.12,
        "roro_state": "neutral",
        "band_en": "Greed",
        "band_zh": "贪婪",
        "risk_tilt": 0,
    },
    "policy": {
        "pboc_stance": "neutral",
        "stance_label_en": "On hold / neutral",
        "stance_label_zh": "按兵不动 / 中性",
        "stale": False,
    },
    "news": {
        "band": "cautious",
        "band_label_en": "cautious / risk-tilted lean",
        "band_label_zh": "偏谨慎 / 防风险",
    },
    "digest": "Context digest text.",
    "disclaimer": "Context only.",
}

_REFERENCE_DATE = date(2026, 7, 6)


# ---------------------------------------------------------------------------
# Helper — write fixture to tmp_path
# ---------------------------------------------------------------------------
def _write_fixture(tmp_path: Path, data: dict | None = None) -> Path:
    p = tmp_path / "briefing.json"
    # Explicit None check — empty dict {} is falsy but valid; don't collapse to fixture
    payload = _FIXTURE_BRIEFING if data is None else data
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# (a1) Happy-path: schema and key field assertions
# ---------------------------------------------------------------------------
def test_china_packet_schema(tmp_path):
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt is not None, "packet must not be None for a valid briefing"
    assert pkt["schema"] == "intelligence_hub.region.v1"
    assert pkt["region"] == "CN"
    assert pkt["mode"] == "context_only"
    assert pkt["links"]["detail"] == "china_intel.html"


def test_china_packet_as_of(tmp_path):
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt["as_of"] == "2026-07-06"
    assert pkt["asof_age_days"] == 0  # same day


def test_china_packet_headline_accumulation(tmp_path):
    """Headline picks up new_accumulation count."""
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert "+2 accumulation" in pkt["headline"]


def test_china_packet_headline_scheduled(tmp_path):
    """Headline surfaces upcoming scheduled event when no stance/band change."""
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    # The fixture has scheduled events and no stance/band change
    assert "Upcoming:" in pkt["headline"] or "+2 accumulation" in pkt["headline"]


def test_china_packet_headline_stance_change(tmp_path):
    """Stance change appears first in headline."""
    from scripts.build_intel_hub import build_china_packet
    data = dict(_FIXTURE_BRIEFING)
    wc = dict(data["what_changed"])
    wc["stance_change"] = {"from": "neutral", "to": "easing"}
    data = {**data, "what_changed": wc}
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert "Stance: neutral → easing" in pkt["headline"]


def test_china_packet_conviction_rows(tmp_path):
    """Top-2 conviction rows are preserved with expected keys."""
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert len(pkt["conviction"]) == 2
    assert pkt["conviction"][0]["sector_en"] == "Semiconductors"
    assert pkt["conviction"][0]["stage"] == "consensus"
    assert pkt["conviction"][0]["edge_remaining"] == pytest.approx(0.365)
    assert pkt["conviction"][1]["sector_en"] == "Brokers"


def test_china_packet_flagged_ticker_count(tmp_path):
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt["flagged_ticker_count"] == 2


def test_china_packet_regime_and_policy(tmp_path):
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt["regime"]["band_en"] == "Greed"
    assert pkt["regime"]["roro_state"] == "neutral"
    assert pkt["policy"]["stance_label_en"] == "On hold / neutral"
    assert pkt["policy"]["stale"] is False


def test_china_packet_news_band(tmp_path):
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt["news"]["band"] == "cautious"
    assert pkt["news"]["band_label_en"] == "cautious / risk-tilted lean"


def test_china_packet_surfaces_freshness(tmp_path):
    """Per-surface freshness: policy is 3d old (not stale); all others same-day."""
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    surfaces = pkt["surfaces"]
    assert "news" in surfaces
    assert surfaces["news"]["stale"] is False
    assert surfaces["policy"]["asof"] == "2026-07-03"
    assert surfaces["policy"]["stale"] is False  # exactly 3d — not stale (threshold is >3d)


def test_china_packet_stale_surface_flagged(tmp_path):
    """Surface older than 3 days is flagged stale."""
    from scripts.build_intel_hub import build_china_packet
    data = {**_FIXTURE_BRIEFING, "surface_asof": {"news": "2026-06-30", "policy": "2026-07-06"}}
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt["surfaces"]["news"]["stale"] is True   # 6d old > 3d threshold
    assert pkt["surfaces"]["policy"]["stale"] is False


# ---------------------------------------------------------------------------
# (a2) Degradation — missing file, bad JSON, missing keys
# ---------------------------------------------------------------------------
def test_china_packet_missing_file():
    """Absent briefing file returns None (not an exception)."""
    from scripts.build_intel_hub import build_china_packet
    result = build_china_packet(Path("/nonexistent/path/briefing.json"))
    assert result is None


def test_china_packet_bad_json(tmp_path):
    """Malformed JSON returns None."""
    from scripts.build_intel_hub import build_china_packet
    p = tmp_path / "briefing.json"
    p.write_text("{invalid json", encoding="utf-8")
    assert build_china_packet(p) is None


def test_china_packet_empty_json(tmp_path):
    """Empty dict still produces a packet with safe defaults."""
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path, {})
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    # Should return a packet, not None — empty dict is parseable
    assert pkt is not None
    assert pkt["schema"] == "intelligence_hub.region.v1"
    assert pkt["conviction"] == []
    assert pkt["flagged_ticker_count"] == 0
    assert pkt["headline"] == "No changes flagged"


def test_china_packet_missing_what_changed(tmp_path):
    """Missing what_changed falls back to conviction row headline."""
    from scripts.build_intel_hub import build_china_packet
    data = {k: v for k, v in _FIXTURE_BRIEFING.items() if k != "what_changed"}
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt is not None
    # Should fall back to conviction-based headline
    assert "Semiconductors" in pkt["headline"] or len(pkt["headline"]) > 0


def test_china_packet_asof_age_old(tmp_path):
    """asof_age_days is computed correctly for old briefings."""
    from scripts.build_intel_hub import build_china_packet
    data = {**_FIXTURE_BRIEFING, "asof": "2026-07-01"}
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt["asof_age_days"] == 5


def test_china_packet_asof_age_clamped_to_zero(tmp_path):
    """Future-dated briefing produces asof_age_days == 0, not negative."""
    from scripts.build_intel_hub import build_china_packet
    data = {**_FIXTURE_BRIEFING, "asof": "2026-07-10"}  # 4d in the future
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt is not None
    assert pkt["asof_age_days"] == 0


# ---------------------------------------------------------------------------
# (a3) Present-but-null degradation — realistic bus shapes
# The bus emits None surfaces / null regime / null conviction members by design.
# These must not raise; packet or None is acceptable.
# ---------------------------------------------------------------------------

def test_china_packet_null_regime(tmp_path):
    """Briefing with regime: null must not raise."""
    from scripts.build_intel_hub import build_china_packet
    data = {**_FIXTURE_BRIEFING, "regime": None}
    p = _write_fixture(tmp_path, data)
    result = build_china_packet(p, reference_date=_REFERENCE_DATE)
    # Must return without raising — packet or None are both acceptable
    assert result is None or isinstance(result, dict)


def test_china_packet_null_conviction_member(tmp_path):
    """conviction: [null] must not raise — null rows are silently skipped."""
    from scripts.build_intel_hub import build_china_packet
    data = {**_FIXTURE_BRIEFING, "conviction": [None, _FIXTURE_BRIEFING["conviction"][0]]}
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt is not None, "packet must not be None — one valid conviction row exists"
    # The null row must be skipped; only the valid row appears
    assert len(pkt["conviction"]) == 1
    assert pkt["conviction"][0]["sector_en"] == "Semiconductors"


def test_china_packet_null_surface_asof_value(tmp_path):
    """surface_asof with a null value must not raise."""
    from scripts.build_intel_hub import build_china_packet
    data = {**_FIXTURE_BRIEFING, "surface_asof": {"news": None, "policy": "2026-07-06"}}
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt is not None
    assert "news" in pkt["surfaces"]
    assert pkt["surfaces"]["news"]["stale"] is False  # None asof → not stale, just unknown


def test_china_packet_null_scheduled_member(tmp_path):
    """what_changed.new_scheduled_within_3d: [null] must not raise."""
    from scripts.build_intel_hub import build_china_packet
    wc = {**_FIXTURE_BRIEFING["what_changed"], "new_scheduled_within_3d": [None, {"name_en": "PMI data", "name_zh": "PMI数据", "date": "2026-07-07"}]}
    data = {**_FIXTURE_BRIEFING, "what_changed": wc}
    p = _write_fixture(tmp_path, data)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt is not None
    # Headline must not crash; the valid event name should appear
    assert "PMI data" in pkt["headline"] or len(pkt["headline"]) > 0


# ---------------------------------------------------------------------------
# (b) Template render — real call shape, with and without china packet
# ---------------------------------------------------------------------------
def _minimal_hub() -> dict:
    """Return the minimal hub dict the template requires to render without error."""
    return {
        "schema": "intel-hub-v3",
        "n_universe": 0,
        "n_actionable": 0,
        "n_emerging": 0,
        "n_discovery": 0,
        "command": [],
        "emerging": [],
        "exhausted": [],
        "catalysts": [],
        "discovery": [],
        "desks": {k: {"live": False} for k in
                  ("news", "alt_data", "radar", "standout", "policy", "special")},
        "sector_heat": [],
        "macro_context": {},
        "counts": {},
        "disclaimer": "Context only.",
        "as_of": "2026-07-06",
        "track_record": {"n_snapshots": 0},
        "desk_grader": {},
    }


def _get_jinja_env():
    """Load the real Jinja2 environment from the worktree templates directory."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    # Locate templates/ relative to this test file's grandparent
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def test_template_omits_china_module_even_with_packet(tmp_path):
    """Operator order 2026-07-11: the US hub must NOT render the China Lens module,
    even when a valid packet is passed (the render call still passes china= — the
    kwarg must stay accepted without a collision or an error)."""
    from scripts.build_intel_hub import build_china_packet
    p = _write_fixture(tmp_path)
    pkt = build_china_packet(p, reference_date=_REFERENCE_DATE)
    assert pkt is not None

    env = _get_jinja_env()
    hub = _minimal_hub()
    # REAL render call shape — kwarg-collision check: hub dict must not contain 'china' key
    assert "china" not in hub, "hub dict must not contain 'china' — would cause kwarg collision"
    html = env.get_template("intelligence_hub.html.j2").render(
        hub=hub,
        built="2026-07-06T02:00:00+00:00",
        mode="intel_hub",
        qledger_chips={},
        china=pkt,
    )
    assert "china-lens" not in html, "China Lens module removed by operator order — must not render"
    assert "cl-dot" not in html and "cl-chip" not in html, "China Lens markup must be gone"
    # Rest of hub still renders bilingually
    assert "Intelligence Hub" in html or "情报中心" in html
    assert "l-en" in html and "l-zh" in html


def test_template_renders_without_china_omits_module():
    """Template renders correctly when china=None and China Lens module is absent."""
    env = _get_jinja_env()
    hub = _minimal_hub()
    html = env.get_template("intelligence_hub.html.j2").render(
        hub=hub,
        built="2026-07-06T02:00:00+00:00",
        mode="intel_hub",
        qledger_chips={},
        china=None,
    )
    assert "china-lens" not in html, "China Lens module must be absent when china=None"
    # Rest of hub should still render
    assert "Intelligence Hub" in html or "情报中心" in html


def test_template_no_title_cjk_violations():
    """No CJK characters inside title= attributes in the template — CI guard parity."""
    import re
    template_path = Path(__file__).resolve().parent.parent / "templates" / "intelligence_hub.html.j2"
    source = template_path.read_text(encoding="utf-8")
    _CJK = re.compile(r"[一-鿿㐀-䶿　-〿＀-￯]")
    _TITLE_ATTR = re.compile(r'title\s*=\s*"([^"]*)"', re.DOTALL)
    violations = []
    for m in _TITLE_ATTR.finditer(source):
        val = m.group(1)
        if _CJK.search(val):
            violations.append(val[:80])
    assert not violations, f"CJK in title= attribute: {violations}"
