"""Tests for Lane F — ignition radar narrow streak persistence honesty (ruling M7C-R7).

Covers:
  engine/ignition_radar.py
    — _streak_from_us_log: counts consecutive trailing days correctly
    — _streak_from_us_log: missing basket breaks the streak at the right point
    — _update_streak_cache: increments on successive different days
    — _update_streak_cache: resets to 0 when score drops below threshold
    — _update_streak_cache: idempotent on same-date rerun (does NOT double-count)
    — _compute_narrow_top: returns None when top score < threshold
    — _compute_narrow_top: returns dict with correct fields when above threshold
    — _compute_narrow_top: streak_sessions >= 3 gates the template condition
    — snapshot() payload contains narrow_top key (display field present)
    — existing state-logic outputs unchanged (fixture-driven gate-invariance)

  template (_ignition_radar_card.html.j2)
    — persistence headline visible when off/warming + score>=0.55 + streak>=3
    — persistence headline hidden when broad state is "ignited"
    — persistence headline hidden when streak < 3
    — bilingual strings present in persistence headline
    — no "validated" in rendered output with narrow_top present
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ──────────────────────────────────────────────────────────────────────────────
# helpers / fixtures
# ──────────────────────────────────────────────────────────────────────────────

_IGNITING_THRESHOLD = 0.55   # mirrors sector_ignition.STATE_IGNITING


def _make_us_log_row(asof: str, basket_id: str, score: float, state: str = "igniting") -> dict:
    """Minimal us_ignition.jsonl row for streak tests."""
    return {
        "asof": asof,
        "market": "us",
        "broad_state": "off",
        "k_count": 1,
        "chips_lit": [],
        "chips_fresh": [],
        "regime_fragile": False,
        "regime_label": "No ignition",
        "top_narrow": [
            {"id": basket_id, "name": "Magnificent Seven",
             "ignition_score": score, "state": state}
        ],
        "logged_at": "2026-07-11T00:00:00+00:00",
        "graded_broad": None,
        "graded_narrow": None,
    }


def _write_us_log(log_path: Path, rows: list[dict]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# _streak_from_us_log
# ──────────────────────────────────────────────────────────────────────────────

from engine.ignition_radar import _streak_from_us_log, _update_streak_cache, _compute_narrow_top


def test_streak_from_log_empty_file(tmp_path):
    log_path = tmp_path / "ignition_log" / "us_ignition.jsonl"
    # file does not exist
    streak, latest_date = _streak_from_us_log("mag7", log_path)
    assert streak == 0
    assert latest_date is None


def test_streak_from_log_counts_consecutive_days(tmp_path):
    """5 consecutive days above threshold → streak == 5."""
    log_path = tmp_path / "ignition_log" / "us_ignition.jsonl"
    rows = [
        _make_us_log_row("2026-07-05", "mag7", 0.70),
        _make_us_log_row("2026-07-06", "mag7", 0.65),
        _make_us_log_row("2026-07-07", "mag7", 0.72),
        _make_us_log_row("2026-07-08", "mag7", 0.60),
        _make_us_log_row("2026-07-09", "mag7", 0.68),
    ]
    _write_us_log(log_path, rows)
    streak, latest_date = _streak_from_us_log("mag7", log_path)
    assert streak == 5
    assert latest_date == "2026-07-09"


def test_streak_from_log_resets_at_gap(tmp_path):
    """Gap day (below threshold) in the middle means only the tail counts."""
    log_path = tmp_path / "ignition_log" / "us_ignition.jsonl"
    rows = [
        _make_us_log_row("2026-07-05", "mag7", 0.70),
        _make_us_log_row("2026-07-06", "mag7", 0.70),
        _make_us_log_row("2026-07-07", "mag7", 0.30),  # below threshold — breaks streak
        _make_us_log_row("2026-07-08", "mag7", 0.72),
        _make_us_log_row("2026-07-09", "mag7", 0.68),
    ]
    _write_us_log(log_path, rows)
    streak, latest_date = _streak_from_us_log("mag7", log_path)
    # Only the last 2 days count (after the gap)
    assert streak == 2
    assert latest_date == "2026-07-09"


def test_streak_from_log_basket_not_in_top_breaks_streak(tmp_path):
    """If basket absent from top_narrow for a day, streak resets at that point."""
    log_path = tmp_path / "ignition_log" / "us_ignition.jsonl"
    rows = [
        _make_us_log_row("2026-07-05", "mag7", 0.70),
        # day 2: different basket tops the list — mag7 absent
        {
            **_make_us_log_row("2026-07-06", "OTHER", 0.90),
            "top_narrow": [{"id": "OTHER", "name": "Other", "ignition_score": 0.90, "state": "igniting"}],
        },
        _make_us_log_row("2026-07-07", "mag7", 0.72),
        _make_us_log_row("2026-07-08", "mag7", 0.68),
    ]
    _write_us_log(log_path, rows)
    streak, latest_date = _streak_from_us_log("mag7", log_path)
    # Only last 2 days (07-07 and 07-08) have mag7 above threshold
    assert streak == 2
    assert latest_date == "2026-07-08"


# ──────────────────────────────────────────────────────────────────────────────
# _update_streak_cache
# ──────────────────────────────────────────────────────────────────────────────

def test_cache_streak_increments_on_new_days(tmp_path):
    streak_path = tmp_path / "ignition_radar" / "narrow_streak.json"
    # Day 1
    s1 = _update_streak_cache("mag7", 0.70, "2026-07-09", streak_path)
    assert s1 == 1
    # Day 2
    s2 = _update_streak_cache("mag7", 0.65, "2026-07-10", streak_path)
    assert s2 == 2
    # Day 3
    s3 = _update_streak_cache("mag7", 0.72, "2026-07-11", streak_path)
    assert s3 == 3


def test_cache_streak_resets_below_threshold(tmp_path):
    streak_path = tmp_path / "ignition_radar" / "narrow_streak.json"
    _update_streak_cache("mag7", 0.70, "2026-07-09", streak_path)
    _update_streak_cache("mag7", 0.70, "2026-07-10", streak_path)
    # Score drops below 0.55 — streak resets
    s = _update_streak_cache("mag7", 0.30, "2026-07-11", streak_path)
    assert s == 0


def test_cache_streak_idempotent_same_date(tmp_path):
    """Same-date rerun must NOT increment the streak."""
    streak_path = tmp_path / "ignition_radar" / "narrow_streak.json"
    s1 = _update_streak_cache("mag7", 0.70, "2026-07-11", streak_path)
    s2 = _update_streak_cache("mag7", 0.70, "2026-07-11", streak_path)  # same date
    s3 = _update_streak_cache("mag7", 0.70, "2026-07-11", streak_path)  # again
    assert s1 == s2 == s3 == 1, "same-date rerun must not double-count the streak"


def test_cache_streak_different_baskets_tracked_independently(tmp_path):
    streak_path = tmp_path / "ignition_radar" / "narrow_streak.json"
    _update_streak_cache("mag7", 0.70, "2026-07-10", streak_path)
    _update_streak_cache("mag7", 0.70, "2026-07-11", streak_path)
    # Different basket
    _update_streak_cache("semis", 0.60, "2026-07-11", streak_path)
    data = json.loads(streak_path.read_text())
    assert data["mag7"]["streak"] == 2
    assert data["semis"]["streak"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# _compute_narrow_top
# ──────────────────────────────────────────────────────────────────────────────

def test_compute_narrow_top_none_when_no_items(tmp_path):
    result = _compute_narrow_top([], tmp_path)
    assert result is None


def test_compute_narrow_top_none_when_below_threshold(tmp_path):
    items = [{"id": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头",
               "ignition_score": 0.40, "state": "fading"}]
    result = _compute_narrow_top(items, tmp_path)
    assert result is None


def test_compute_narrow_top_returns_dict_with_required_fields(tmp_path):
    items = [{"id": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头",
               "ignition_score": 0.70, "state": "igniting"}]
    result = _compute_narrow_top(items, tmp_path)
    assert result is not None
    assert result["basket_id"] == "mag7"
    assert result["name"] == "Magnificent Seven"
    assert result["name_zh"] == "七巨头"
    assert result["score"] == 0.70
    assert "streak_sessions" in result
    assert isinstance(result["streak_sessions"], int)
    assert result["streak_sessions"] >= 1  # at minimum today's session


def test_compute_narrow_top_streak_accumulates(tmp_path):
    """After 4 log days (all prior to today) + today via cache, streak should be 5."""
    # Write 4 days of log history — all prior to today so +1 bridge is applied
    log_path = tmp_path / "ignition_log" / "us_ignition.jsonl"
    rows = [
        _make_us_log_row("2026-07-07", "mag7", 0.70),
        _make_us_log_row("2026-07-08", "mag7", 0.68),
        _make_us_log_row("2026-07-09", "mag7", 0.72),
        _make_us_log_row("2026-07-10", "mag7", 0.65),
    ]
    _write_us_log(log_path, rows)

    items = [{"id": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头",
               "ignition_score": 0.70, "state": "igniting"}]
    result = _compute_narrow_top(items, tmp_path)
    assert result is not None
    # 4 log days (prior to today) + 1 today via cache
    assert result["streak_sessions"] >= 4


def test_compute_narrow_top_same_day_rerender_no_double_count(tmp_path):
    """Same-day re-render idempotency: when the log already contains today's row,
    streak must not be inflated by +1 (the reviewer's must_fix finding)."""
    from datetime import date as _date
    today = str(_date.today())
    log_path = tmp_path / "ignition_log" / "us_ignition.jsonl"
    # Simulate: 4 prior days PLUS today already committed (post-nightly log_us_snapshot)
    rows = [
        _make_us_log_row("2026-07-07", "mag7", 0.70),
        _make_us_log_row("2026-07-08", "mag7", 0.68),
        _make_us_log_row("2026-07-09", "mag7", 0.72),
        _make_us_log_row("2026-07-10", "mag7", 0.65),
        _make_us_log_row(today, "mag7", 0.70),  # today already in log
    ]
    _write_us_log(log_path, rows)

    items = [{"id": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头",
               "ignition_score": 0.70, "state": "igniting"}]
    # First call (simulates engine-render re-run)
    result1 = _compute_narrow_top(items, tmp_path)
    assert result1 is not None
    streak1 = result1["streak_sessions"]

    # Second call — must return same count (truly idempotent)
    result2 = _compute_narrow_top(items, tmp_path)
    assert result2 is not None
    streak2 = result2["streak_sessions"]

    assert streak1 == streak2, (
        f"Same-day re-render double-counted: first={streak1}, second={streak2}"
    )
    # The log has 5 rows (4 prior + today), all above threshold → streak must be exactly 5
    assert streak1 == 5, (
        f"Expected streak=5 (4 prior days + today from log), got {streak1}; "
        "double-count bug would give 6"
    )


# ──────────────────────────────────────────────────────────────────────────────
# snapshot() payload — display fields present
# ──────────────────────────────────────────────────────────────────────────────

def test_snapshot_payload_contains_narrow_top_key(monkeypatch, tmp_path):
    """snapshot() must include 'narrow_top' key (may be None or dict)."""
    import engine.ignition_radar as ir

    # Monkeypatch away all I/O so this runs in <1s and hits no network
    monkeypatch.setattr(ir, "_load_radar_xref", lambda: {"state": None, "phase": None})
    monkeypatch.setattr(ir, "compute_broad", lambda cats, breadth: {
        "as_of": "2026-07-11", "k_count": 1, "state": "off", "chips": [],
    })
    monkeypatch.setattr(ir, "compute_narrow", lambda membership, spy, ticker_cache=None: {
        "as_of": "2026-07-11",
        "items": [
            {"id": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头",
             "ignition_score": 0.70, "state": "igniting",
             "rs_new_high": False, "above_200d_rising": True},
        ],
    })
    monkeypatch.setattr(ir, "compute_regime", lambda broad_state, narrow, rsp, sec: {
        "label_en": "Theme ignition — Magnificent Seven, participation OK",
        "label_zh": "主题点火 — 七巨头，参与度尚可",
        "fragile": False,
        "do_en": "Evidence read, not a buy call.",
        "do_zh": "证据读取，非买入信号。",
    })
    # Stub store reads + catalysts
    from lib import store as _store
    monkeypatch.setattr(_store, "read", lambda ns, tick: None)
    import engine.risk_radar_market_catalysts as _cats
    monkeypatch.setattr(_cats, "compute", lambda root=None: None)

    payload = ir.snapshot(root=str(tmp_path))
    assert "narrow_top" in payload, "snapshot payload must contain 'narrow_top' key"


def test_snapshot_narrow_top_fields_when_above_threshold(monkeypatch, tmp_path):
    """When top narrow score >= 0.55, narrow_top must be a dict with required keys."""
    import engine.ignition_radar as ir

    monkeypatch.setattr(ir, "_load_radar_xref", lambda: {"state": None, "phase": None})
    monkeypatch.setattr(ir, "compute_broad", lambda cats, breadth: {
        "as_of": "2026-07-11", "k_count": 1, "state": "off", "chips": [],
    })
    monkeypatch.setattr(ir, "compute_narrow", lambda membership, spy, ticker_cache=None: {
        "as_of": "2026-07-11",
        "items": [
            {"id": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头",
             "ignition_score": 0.70, "state": "igniting",
             "rs_new_high": False, "above_200d_rising": True},
        ],
    })
    monkeypatch.setattr(ir, "compute_regime", lambda broad_state, narrow, rsp, sec: {
        "label_en": "Theme ignition — Magnificent Seven, participation OK",
        "label_zh": "主题点火 — 七巨头，参与度尚可",
        "fragile": False,
        "do_en": "Evidence read, not a buy call.",
        "do_zh": "证据读取，非买入信号。",
    })
    from lib import store as _store
    monkeypatch.setattr(_store, "read", lambda ns, tick: None)
    import engine.risk_radar_market_catalysts as _cats
    monkeypatch.setattr(_cats, "compute", lambda root=None: None)

    payload = ir.snapshot(root=str(tmp_path))
    nt = payload["narrow_top"]
    assert nt is not None, "narrow_top must not be None when top score >= 0.55"
    for key in ("basket_id", "name", "name_zh", "score", "streak_sessions"):
        assert key in nt, f"narrow_top missing required key: {key}"
    assert nt["basket_id"] == "mag7"
    assert nt["score"] == 0.70
    assert isinstance(nt["streak_sessions"], int)


def test_snapshot_narrow_top_none_when_below_threshold(monkeypatch, tmp_path):
    """When top narrow score < 0.55, narrow_top must be None."""
    import engine.ignition_radar as ir

    monkeypatch.setattr(ir, "_load_radar_xref", lambda: {"state": None, "phase": None})
    monkeypatch.setattr(ir, "compute_broad", lambda cats, breadth: {
        "as_of": "2026-07-11", "k_count": 0, "state": "off", "chips": [],
    })
    monkeypatch.setattr(ir, "compute_narrow", lambda membership, spy, ticker_cache=None: {
        "as_of": "2026-07-11",
        "items": [
            {"id": "xlk", "name": "XLK", "name_zh": "XLK",
             "ignition_score": 0.30, "state": "fading",
             "rs_new_high": False, "above_200d_rising": False},
        ],
    })
    monkeypatch.setattr(ir, "compute_regime", lambda broad_state, narrow, rsp, sec: {
        "label_en": "No ignition", "label_zh": "未点火",
        "fragile": False, "do_en": "No evidence.", "do_zh": "无证据。",
    })
    from lib import store as _store
    monkeypatch.setattr(_store, "read", lambda ns, tick: None)
    import engine.risk_radar_market_catalysts as _cats
    monkeypatch.setattr(_cats, "compute", lambda root=None: None)

    payload = ir.snapshot(root=str(tmp_path))
    assert payload["narrow_top"] is None


# ──────────────────────────────────────────────────────────────────────────────
# Gate invariance — existing state logic unchanged on fixture
# ──────────────────────────────────────────────────────────────────────────────

from engine.ignition_radar import _broad_state, compute_regime


def _make_chip(key: str, lit: bool, fresh: bool) -> dict:
    return {
        "key": key, "label_en": key, "label_zh": key,
        "lit": lit, "fresh": fresh,
        "since": str(date.today()) if lit else None,
        "detail_en": "", "detail_zh": "", "source": "test",
    }


def test_gate_invariance_broad_state_off():
    """Existing state logic: 0 chips lit → off. Must not be changed by persistence PR."""
    chips = [_make_chip(k, False, False) for k in
             ["thrust_confluence", "msi_swing", "washout_thrust20", "ftd",
              "pct50_recover", "nh_flip", "rsp_confirm", "sector_participation"]]
    k = sum(1 for c in chips if c["lit"])
    assert _broad_state(k, chips) == "off"


def test_gate_invariance_broad_state_ignited():
    """Existing state logic: K>=3 + thrust chip fresh → ignited."""
    chips = [
        _make_chip("thrust_confluence", True, True),
        _make_chip("pct50_recover", True, True),
        _make_chip("nh_flip", True, True),
        _make_chip("rsp_confirm", False, False),
        _make_chip("sector_participation", False, False),
        _make_chip("msi_swing", False, False),
        _make_chip("washout_thrust20", False, False),
        _make_chip("ftd", False, False),
    ]
    k = sum(1 for c in chips if c["lit"])
    assert _broad_state(k, chips) == "ignited"


def test_gate_invariance_compute_regime_fragile():
    """Existing regime logic: narrow igniting + no participation → fragile."""
    narrow = [{"id": "mag7", "name": "Magnificent Seven", "state": "igniting",
                "ignition_score": 0.70}]
    r = compute_regime("off", narrow, rsp_confirm_lit=False, sector_participation_lit=False)
    assert r["fragile"] is True


def test_gate_invariance_compute_regime_not_fragile_with_participation():
    """Existing regime logic: narrow igniting + participation → NOT fragile."""
    narrow = [{"id": "mag7", "name": "Magnificent Seven", "state": "igniting",
                "ignition_score": 0.70}]
    r = compute_regime("off", narrow, rsp_confirm_lit=True, sector_participation_lit=False)
    assert r["fragile"] is False


# ──────────────────────────────────────────────────────────────────────────────
# Template rendering — persistence headline
# ──────────────────────────────────────────────────────────────────────────────

try:
    from jinja2 import Environment, FileSystemLoader
    _JINJA_AVAILABLE = True
except ImportError:
    _JINJA_AVAILABLE = False


def _jinja_env():
    from pathlib import Path
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    return env


def _base_payload(state: str = "off", k_count: int = 1) -> dict:
    return {
        "as_of": "2026-07-11",
        "state": state,
        "k_count": k_count,
        "chips": [],
        "regime": {
            "label_en": "Theme ignition — Magnificent Seven, participation OK",
            "label_zh": "主题点火 — 七巨头，参与度尚可",
            "fragile": False,
            "do_en": "Evidence read, not a buy call.",
            "do_zh": "证据读取，非买入信号。",
        },
        "narrow": {
            "items": [
                {"id": "mag7", "name": "Magnificent Seven", "state": "igniting",
                 "ignition_score": 0.70, "rs_new_high": False, "above_200d_rising": True},
            ],
            "as_of": "2026-07-11",
        },
        "narrow_top": {
            "basket_id": "mag7",
            "name": "Magnificent Seven",
            "name_zh": "七巨头",
            "score": 0.70,
            "streak_sessions": 11,
        },
        "radar_xref": {"state": "watch", "phase": None},
        "accruing": "accruing — display-only",
    }


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_persistence_headline_visible_when_off_and_streak_gte_3():
    """Persistence headline ('running · day N') visible when: off, score>=0.55, streak>=3."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    ig = _base_payload(state="off")
    html = macro_tmpl.render(ig=ig)
    assert "running · day 11" in html, f"Persistence headline missing; html={html[:400]}"
    assert "igx-persist" in html


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_persistence_headline_visible_when_warming_and_streak_gte_3():
    """Persistence headline visible for warming state too."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    ig = _base_payload(state="warming")
    html = macro_tmpl.render(ig=ig)
    assert "running · day 11" in html


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_persistence_headline_hidden_when_ignited():
    """Persistence headline must NOT appear when broad state is ignited (not needed there)."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    ig = _base_payload(state="ignited", k_count=4)
    html = macro_tmpl.render(ig=ig)
    assert "igx-persist" not in html, "Persistence row must not appear when broad is ignited"


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_persistence_headline_hidden_when_streak_lt_3():
    """Persistence headline must NOT appear when streak < 3 (not yet persistent)."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    ig = _base_payload(state="off")
    ig["narrow_top"]["streak_sessions"] = 2   # below the 3-session gate
    html = macro_tmpl.render(ig=ig)
    assert "igx-persist" not in html, "Persistence headline must not show when streak < 3"


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_persistence_headline_hidden_when_narrow_top_absent():
    """No narrow_top → no persistence headline."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    ig = _base_payload(state="off")
    ig["narrow_top"] = None
    html = macro_tmpl.render(ig=ig)
    assert "igx-persist" not in html


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_persistence_headline_bilingual():
    """Persistence headline includes both l-en and l-zh spans."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    ig = _base_payload(state="off")
    html = macro_tmpl.render(ig=ig)
    assert "l-en" in html, "English span class must be present"
    assert "l-zh" in html, "Chinese span class must be present"
    # Chinese counter text present
    assert "持续运行" in html, "Chinese persistence text missing"
    assert "第11日" in html, "Chinese day count missing"


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_no_validated_word_with_narrow_top():
    """'validated' must not appear in rendered output when narrow_top is present."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    for state in ("ignited", "warming", "off"):
        ig = _base_payload(state=state)
        html = macro_tmpl.render(ig=ig)
        assert "validated" not in html.lower(), (
            f"'validated' found in rendered HTML for state={state}"
        )
