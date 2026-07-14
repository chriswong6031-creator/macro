"""Track-record card tests for the Risk Radar scorecard surface.

Covers:
  1. _rr_scorecard_track() is fail-soft: returns None on missing file.
  2. _radar_to_rd() includes a 'track' key (always present, None when scorecard absent).
  3. _calm_radar() includes 'track' key (for old pages that skip the banner).
  4. Jinja templates parse without syntax errors (_risk_radar_card.html.j2 +
     _risk_radar_card.css.j2).
  5. No "validated" string in the new template additions (CI-guarded law).
  6. track block renders NOTHING when rd.track is absent/None (fail-soft guard).
  7. track block renders the glance line when scorecard is present with sufficient data.
  8. track block renders the "too few" line when hit_rate is null (n < 5 honesty floor).
  9. _build_risk_radar in build_macro_context includes 'track' key.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from jinja2 import Environment, FileSystemLoader

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
_REPO = Path(__file__).resolve().parent.parent
_TEMPLATES = _REPO / "templates"


def _jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)))
    # minimal globals the card needs
    env.globals["zip"] = zip
    return env


def _minimal_rd(track=None) -> dict:
    """Minimal radar dict that satisfies the card template."""
    return {
        "state": "caution",
        "top_score": 72,
        "label_en": "credit",
        "label_zh": "信用",
        "state_zh": "谨慎",
        "do_en": "Trim risk.",
        "do_zh": "降低风险。",
        "gross": None,
        "dd5": 0.08,
        "dd10": 0.14,
        "dd21": 0.28,
        "dd_lift": 1.6,
        "dd_base": {"h5": 0.036, "h10": 0.086, "h21": 0.178},
        "is_loud": True,
        "scares": [],
        "forward_log": None,
        "cycle": None,
        "counterread": None,
        "amp": 0,
        "amp_keys": [],
        "amp_flags_en": [],
        "amp_flags_zh": [],
        "severe_gated": False,
        "ceiling": None,
        "recovery": None,
        "track": track,
    }


def _scorecard_market(
    graded_n: int = 10,
    tp: int = 7,
    hit_rate: float | None = 0.7,
    log_fresh: bool = True,
) -> dict:
    """Minimal MARKET block matching the schema in the build brief."""
    return {
        "asof_last_row": "2026-07-13",
        "monitoring": {
            "log_fresh": log_fresh,
            "last_logged_days_ago": 0 if log_fresh else 3,
            "ungraded_backlog": 2,
            "graded_n": graded_n,
        },
        "windows": {
            "full": {
                "alerts": {"n": graded_n + 3, "tp": tp + 2, "fp": 4, "hit_rate": hit_rate},
                "watch_caution": {"n": 12, "tp": 8, "tn": 4, "precursor_rate": 0.67},
                "calm": {"n": 20, "dd_missed": 1, "quiet": 19, "quiet_rate": 0.95},
                "by_scare": {},
                "recovery": {"n": 6, "ok": 5, "rate": 0.83},
            },
            "y1": {
                "alerts": {"n": graded_n, "tp": tp, "fp": graded_n - tp, "hit_rate": hit_rate},
                "watch_caution": {"n": 8, "tp": 6, "tn": 2, "precursor_rate": 0.75},
                "calm": {"n": 14, "dd_missed": 0, "quiet": 14, "quiet_rate": 1.0},
                "by_scare": {
                    "credit": {"n": 4, "tp": 3, "fp": 1, "hit_rate": None},
                },
                "recovery": None,
            },
        },
    }


# --------------------------------------------------------------------------- #
# 1. _rr_scorecard_track fail-soft on missing file
# --------------------------------------------------------------------------- #
def test_scorecard_track_returns_none_on_missing_file():
    from engine.market_state import _rr_scorecard_track

    with tempfile.TemporaryDirectory() as td:
        with mock.patch("lib.config.data_dir", return_value=Path(td)):
            result = _rr_scorecard_track("us")
    assert result is None


def test_scorecard_track_returns_market_block_when_present():
    from engine.market_state import _rr_scorecard_track

    market_data = _scorecard_market()
    blob = {
        "schema": "risk_radar_scorecard.v1",
        "generated_at": "2026-07-13T00:00:00Z",
        "markets": {"us": market_data},
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "risk_radar"
        p.mkdir()
        (p / "scorecard.json").write_text(json.dumps(blob))
        with mock.patch("lib.config.data_dir", return_value=Path(td)):
            result = _rr_scorecard_track("us")
    assert result is not None
    assert result["monitoring"]["log_fresh"] is True


def test_scorecard_track_returns_none_for_missing_market_key():
    from engine.market_state import _rr_scorecard_track

    blob = {"schema": "risk_radar_scorecard.v1", "markets": {"cn": _scorecard_market()}}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "risk_radar"
        p.mkdir()
        (p / "scorecard.json").write_text(json.dumps(blob))
        with mock.patch("lib.config.data_dir", return_value=Path(td)):
            result = _rr_scorecard_track("us")
    assert result is None


# --------------------------------------------------------------------------- #
# 2. _radar_to_rd includes 'track' key
# --------------------------------------------------------------------------- #
def test_radar_to_rd_includes_track_key():
    from engine.market_state import _radar_to_rd

    minimal_rr = {
        "state": "caution",
        "top_score": 65,
        "dominant_label_en": "credit",
        "dominant_label_zh": "信用",
        "drawdown_prob": {},
    }
    with mock.patch("engine.market_state._rr_scorecard_track", return_value=None):
        rd = _radar_to_rd(minimal_rr)
    assert "track" in rd
    assert rd["track"] is None


def test_radar_to_rd_track_maps_market_key_intl():
    """CN market key passed to _rr_scorecard_track, not 'us'."""
    from engine.market_state import _radar_to_rd

    minimal_rr = {"state": "watch", "top_score": 40, "market": "cn", "drawdown_prob": {}}
    calls = []

    def _capture(mkt):
        calls.append(mkt)
        return None

    with mock.patch("engine.market_state._rr_scorecard_track", side_effect=_capture):
        _radar_to_rd(minimal_rr)
    assert calls == ["cn"]


def test_radar_to_rd_defaults_to_us_when_market_absent():
    from engine.market_state import _radar_to_rd

    minimal_rr = {"state": "calm", "drawdown_prob": {}}
    calls = []

    def _capture(mkt):
        calls.append(mkt)
        return None

    with mock.patch("engine.market_state._rr_scorecard_track", side_effect=_capture):
        _radar_to_rd(minimal_rr)
    assert calls == ["us"]


# --------------------------------------------------------------------------- #
# 3. _calm_radar includes 'track' key
# --------------------------------------------------------------------------- #
def test_calm_radar_includes_track_key():
    from engine.market_state import _calm_radar

    rd = _calm_radar()
    assert "track" in rd
    assert rd["track"] is None


# --------------------------------------------------------------------------- #
# 4. Jinja templates parse without syntax errors
# --------------------------------------------------------------------------- #
def test_risk_radar_card_template_parses():
    env = _jinja_env()
    env.parse((_TEMPLATES / "_risk_radar_card.html.j2").read_text())


def test_risk_radar_card_css_parses():
    env = _jinja_env()
    env.parse((_TEMPLATES / "_risk_radar_card.css.j2").read_text())


# --------------------------------------------------------------------------- #
# 5. No "validated" in new template additions (CI-guarded law)
# --------------------------------------------------------------------------- #
def test_no_validated_in_rr_card_template():
    src = (_TEMPLATES / "_risk_radar_card.html.j2").read_text()
    # Filter to only the track block we added
    start = src.find("rrx-trk")
    block = src[start:] if start >= 0 else src
    assert "validated" not in block.lower(), (
        "Word 'validated' found in the track-record block — use 'graded', 'track record', or 'hit rate' instead"
    )


# --------------------------------------------------------------------------- #
# 6. track block renders NOTHING when rd.track is None
# --------------------------------------------------------------------------- #
def test_card_renders_no_track_chrome_when_track_is_none():
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(track=None)
    html = tmpl.module.risk_radar_card(rd, [])
    assert "rrx-trk" not in html


def test_card_renders_no_track_chrome_when_track_key_absent():
    """Older rd dicts without the 'track' key at all must not crash or output chrome."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(track=None)
    del rd["track"]  # simulate a pre-change rd dict
    html = tmpl.module.risk_radar_card(rd, [])
    assert "rrx-trk" not in html


# --------------------------------------------------------------------------- #
# 7. Glance line appears when scorecard is present with sufficient data
# --------------------------------------------------------------------------- #
def test_card_renders_track_line_with_hit_rate():
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(track=_scorecard_market(graded_n=10, tp=7, hit_rate=0.7))
    html = tmpl.module.risk_radar_card(rd, [])
    assert "rrx-trk" in html
    assert "Track record" in html
    assert "7" in html
    assert "10" in html


# --------------------------------------------------------------------------- #
# 8. "Too few" line when hit_rate is null (n < 5 honesty floor)
# --------------------------------------------------------------------------- #
def test_card_renders_too_few_when_hit_rate_null():
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(track=_scorecard_market(graded_n=3, tp=2, hit_rate=None))
    html = tmpl.module.risk_radar_card(rd, [])
    assert "rrx-trk" in html
    assert "Too few" in html or "too few" in html.lower()


# --------------------------------------------------------------------------- #
# 8b. Stale-ledger message when monitoring.log_fresh is false
# --------------------------------------------------------------------------- #
def test_card_renders_stale_message_when_not_fresh():
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(track=_scorecard_market(log_fresh=False))
    html = tmpl.module.risk_radar_card(rd, [])
    assert "rrx-trk" in html
    assert "stale" in html.lower() or "Monitoring paused" in html


# --------------------------------------------------------------------------- #
# 9. _build_risk_radar in build_macro_context includes 'track' key
# --------------------------------------------------------------------------- #
def test_build_risk_radar_includes_track_key():
    from scripts.build_macro_context import _build_risk_radar

    with mock.patch("engine.market_state._rr_scorecard_track", return_value=None):
        result = _build_risk_radar(None, None)
    assert "track" in result
