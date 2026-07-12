"""RC-R2 append-only marker law (engine/marker_integrity.py).

The regression fixture is the exact observed mutation (masterplan §0.4): the b-ai-software
2026-07-06 buy marker, rendered on 07-07, was silently replaced by a 2026-07-09 marker in
the 07-10 render. Under the law the rendered date must win. Network-free.
"""
from __future__ import annotations

from engine import marker_integrity as mi


def _hist():
    return [
        {"date": "2015-02-06", "type": "buy", "quality": "take", "reason": "held confirmation"},
        {"date": "2015-03-30", "type": "sell"},
        {"date": "2026-06-12", "type": "sell"},
    ]


def test_regression_b_ai_software_redating_blocked():
    prev = {"asof": "2026-07-06",
            "markers": _hist() + [{"date": "2026-07-06", "type": "buy", "quality": "pending",
                                   "reason": "confirmation window open"}]}
    new = {"asof": "2026-07-10", "state": "long-bias",
           "markers": _hist() + [{"date": "2026-07-09", "type": "buy", "quality": "pending",
                                  "reason": "confirmation window open"}]}
    out = mi.merge_payload(prev, new)
    dates = [m["date"] for m in out["markers"] if m["type"] == "buy" and m["date"] > "2026"]
    assert dates == ["2026-07-06"], "rendered marker must keep its date; 07-09 is the same print"
    assert out["asof"] == "2026-07-10"          # live fields pass through
    assert out["pit"]["last_night"]["appended"] == 0


def test_fresh_quality_refinement_allowed():
    prev = {"asof": "2026-07-06",
            "markers": [{"date": "2026-07-01", "type": "buy", "quality": "pending"}]}
    new = {"asof": "2026-07-10",
           "markers": [{"date": "2026-07-01", "type": "buy", "quality": "take",
                        "reason": "held confirmation"}]}
    out = mi.merge_payload(prev, new)
    (m,) = out["markers"]
    assert m["date"] == "2026-07-01" and m["quality"] == "take"
    assert out["pit"]["refined"] == 1


def test_frozen_relabel_blocked():
    prev = {"asof": "2026-07-06",
            "markers": [{"date": "2015-02-06", "type": "buy", "quality": "take"}]}
    new = {"asof": "2026-07-10",
           "markers": [{"date": "2015-02-06", "type": "buy", "quality": "block"}]}
    out = mi.merge_payload(prev, new)
    (m,) = out["markers"]
    assert m["quality"] == "take", "history is frozen — a recompute may not re-grade it"
    assert out["pit"]["relabel_blocked"] == 1


def test_genuinely_new_recent_marker_appended():
    prev = {"asof": "2026-07-06", "markers": _hist()}
    new = {"asof": "2026-07-10",
           "markers": _hist() + [{"date": "2026-07-10", "type": "buy", "quality": "pending"}]}
    out = mi.merge_payload(prev, new)
    assert out["markers"][-1]["date"] == "2026-07-10"
    assert out["pit"]["last_night"]["appended"] == 1


def test_deep_history_drift_dropped_and_lost_retained():
    prev = {"asof": "2026-07-06", "markers": _hist()}
    new = {"asof": "2026-07-10",
           "markers": [m for m in _hist() if m["date"] != "2015-03-30"]  # recompute lost one
           + [{"date": "2019-05-01", "type": "buy", "quality": "take"}]}  # ...and invented one
    out = mi.merge_payload(prev, new)
    dates = [m["date"] for m in out["markers"]]
    assert "2015-03-30" in dates, "a rendered marker the recompute lost must be retained"
    assert "2019-05-01" not in dates, "a recompute may not invent deep history"
    assert out["pit"]["last_night"]["drift_lost"] == 1
    assert out["pit"]["last_night"]["drift_deep_new"] == 1


def test_no_prev_file_passthrough():
    new = {"asof": "2026-07-10", "markers": _hist()}
    out = mi.merge_payload(None, new)
    assert out["markers"] == _hist()
    assert out["pit"]["last_night"]["new_file"] is True


def test_pit_counts_accumulate_across_nights():
    prev = {"asof": "2026-07-06", "pit": {"relabel_blocked": 2},
            "markers": [{"date": "2015-02-06", "type": "buy", "quality": "take"}]}
    new = {"asof": "2026-07-10",
           "markers": [{"date": "2015-02-06", "type": "buy", "quality": "block"}]}
    out = mi.merge_payload(prev, new)
    assert out["pit"]["relabel_blocked"] == 3


def test_date_jitter_within_tolerance_keeps_rendered_date():
    prev = {"asof": "2026-07-06",
            "markers": [{"date": "2024-03-11", "type": "sell"}]}
    new = {"asof": "2026-07-10",
           "markers": [{"date": "2024-03-12", "type": "sell"}]}
    out = mi.merge_payload(prev, new)
    (m,) = out["markers"]
    assert m["date"] == "2024-03-11"
    assert out["pit"]["last_night"]["drift_lost"] == 0
