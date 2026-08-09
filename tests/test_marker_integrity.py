"""RC-R2 append-only marker law (engine/marker_integrity.py).

The regression fixture is the exact observed mutation (masterplan §0.4): the b-ai-software
2026-07-06 buy marker, rendered on 07-07, was silently replaced by a 2026-07-09 marker in
the 07-10 render. Under the law the rendered date must win. Network-free.

The second half of this file pins R-SQ7 — the ONE explained mutation the law admits: an
adjudicated bucketing-era change (research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_
FABLE.md). Every test above it is the SAME-ERA law and must keep passing byte-identically;
if one of them breaks, the era gate leaked into the ordinary path.
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


# --------------------------------------------------------------------------- #
# R-SQ7 — the era cutover: the one EXPLAINED mutation the law admits
# --------------------------------------------------------------------------- #

ERA = "sq-abs-session-2026-08-06"


def _redrawn():
    """The same three physical prints as ``_hist()``, re-dated by a grid re-anchor.

    Two of the three move WITHIN ``TOL_DAYS`` (so the same-era law would freeze the old
    dates) and one moves far beyond it (so the same-era law would drop it as invented deep
    history AND ghost-retain the original). Both halves of the swallow are exercised.
    """
    return [
        {"date": "2015-02-04", "type": "buy", "quality": "take",
         "reason": "held confirmation"},                      # -2d: inside tolerance
        {"date": "2015-04-27", "type": "sell"},               # +28d: beyond tolerance
        {"date": "2026-06-10", "type": "sell"},               # -2d: inside tolerance
    ]


def test_era_flip_takes_tonights_marker_history_wholesale():
    """R-SQ7. A re-anchored grid legitimately re-dates every historical marker at once.

    Under the same-era law that re-draw is swallowed: the two in-tolerance prints keep
    their OLD rendered dates forever and the out-of-tolerance one is dropped as
    ``drift_deep_new`` while its original is ghost-retained. The rendered chart would then
    hold the old grid while every live gate() consumer moved to the new one the same
    night. The era gate is what makes the crossing happen exactly once, by law.
    """
    prev = {"asof": "2026-08-05", "markers": _hist()}          # rendered PRE-era: no stamp
    new = {"asof": "2026-08-06", "anchor_era": ERA, "markers": _redrawn()}
    out = mi.merge_payload(prev, new)
    assert out["markers"] == _redrawn(), "tonight's re-drawn history must win wholesale"
    # ...and specifically: no old date survived, and nothing was ghost-retained
    assert "2015-02-06" not in [m["date"] for m in out["markers"]]
    assert len(out["markers"]) == 3
    for k in ("kept_frozen", "drift_lost", "drift_deep_new", "appended"):
        assert k not in out["pit"]["last_night"], (
            f"a cutover is not drift — {k} must not be reported for the crossing night")


def test_era_cutover_is_recorded_on_the_payload_forever():
    prev = {"asof": "2026-08-05", "markers": _hist()}
    new = {"asof": "2026-08-06", "anchor_era": ERA, "markers": _redrawn()}
    out = mi.merge_payload(prev, new)
    assert out["pit"]["era_cutover"] == {
        "from": None, "to": ERA, "at_asof": "2026-08-06", "prev_markers": 3}
    assert out["pit"]["last_night"] == {"era_cutover": out["pit"]["era_cutover"]}
    assert out["asof"] == "2026-08-06"          # live fields still pass through


def test_cumulative_drift_counters_survive_the_cutover():
    """The counters measure the SAME-ERA law's history. A crossing is not drift, so it
    neither resets them nor adds to them — otherwise a one-time re-draw would bury every
    real drift signal that came before it."""
    prev = {"asof": "2026-08-05", "pit": {"relabel_blocked": 2, "drift_lost": 5},
            "markers": _hist()}
    new = {"asof": "2026-08-06", "anchor_era": ERA, "markers": _redrawn()}
    out = mi.merge_payload(prev, new)
    assert out["pit"]["relabel_blocked"] == 2 and out["pit"]["drift_lost"] == 5


def test_the_law_resumes_under_the_new_era_the_very_next_night():
    """The cutover yields ONCE. On night two the same re-dating is unexplained again."""
    night1 = mi.merge_payload({"asof": "2026-08-05", "markers": _hist()},
                              {"asof": "2026-08-06", "anchor_era": ERA,
                               "markers": _redrawn()})
    jittered = [dict(m, date="2026-06-12") if m["date"] == "2026-06-10" else m
                for m in _redrawn()]
    night2 = mi.merge_payload(night1, {"asof": "2026-08-07", "anchor_era": ERA,
                                       "markers": jittered})
    dates = [m["date"] for m in night2["markers"]]
    assert "2026-06-10" in dates and "2026-06-12" not in dates, (
        "same era again — a re-dated marker is kept-frozen exactly as before")
    assert night2["pit"]["last_night"]["kept_frozen"] == 3
    # the crossing stays on the record even though tonight was an ordinary night
    assert night2["pit"]["era_cutover"]["to"] == ERA


def test_matching_eras_are_the_incumbent_law_byte_identical():
    """Adding the stamp to BOTH sides must change nothing at all."""
    prev = {"asof": "2026-07-06", "markers": _hist()}
    new = {"asof": "2026-07-10",
           "markers": _hist() + [{"date": "2026-07-10", "type": "buy",
                                  "quality": "pending"}]}
    plain = mi.merge_payload(prev, new)
    stamped = mi.merge_payload(dict(prev, anchor_era=ERA), dict(new, anchor_era=ERA))
    assert stamped["markers"] == plain["markers"]
    assert stamped["pit"]["last_night"] == plain["pit"]["last_night"]


def test_a_first_render_is_never_a_cutover():
    """No previous file = nothing to cross FROM; the new-file passthrough owns that case."""
    out = mi.merge_payload(None, {"asof": "2026-08-06", "anchor_era": ERA,
                                  "markers": _redrawn()})
    assert out["markers"] == _redrawn()
    assert out["pit"]["last_night"]["new_file"] is True
    assert "era_cutover" not in out["pit"]
