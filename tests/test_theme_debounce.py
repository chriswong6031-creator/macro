"""Asymmetric debounce on the theme alert engine (engine.theme_alerts.apply_debounce).

The doctrine asymmetry under test: RISK-direction events (theme_topping /
theme_deteriorating / reco downgrades) are the validated drawdown-control channel and
fire IMMEDIATELY, unchanged. Only CONSTRUCTIVE-direction changes (upgrades into
ACCUMULATE/ENTER, leadership_rotation) are buffered: a flip must hold N_STREAK=2
consecutive builds — counted at most once per session date, since the Asia lane
double-builds intraday — (leadership also needs a >=LEAD_MIN_MARGIN score margin over
rank-2) before it fires, and a flip that reverts on the next build never fires. Old-format
state files without the "_debounce" key must read as "no streak" — never crash. Pure
logic + tmp-dir round-trips through rebuild(); no network.
"""
from __future__ import annotations

import json

from engine import theme_alerts as ta
from lib import config


def _theme(tid, label="neutral", reco="hold", rank=5, score=50):
    return {"id": tid, "label": label, "reco": reco, "rank": rank, "score": score,
            "name": tid.upper(), "name_zh": tid}


def _intel(themes, as_of):
    return {"as_of": as_of, "themes": themes}


def _ld(score=90):
    """A stable rank-1 anchor so reco tests never trip the leadership machine."""
    return _theme("ld", "dominant", "hold", 1, score)


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)


# ------------------------------------------------------- (a) flip that reverts: silent
def test_constructive_flip_that_reverts_next_build_never_fires(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", rank=2)], "2026-06-18")) == []  # seed
    # build 2: hold -> accumulate — buffered, nothing fires
    assert ta.rebuild(_intel([_ld(), _theme("x", reco="accumulate", rank=2)],
                             "2026-06-19")) == []
    # build 3: straight back to hold — the reversion echo is suppressed too (the upgrade
    # never displayed, so the net displayed change is zero)
    assert ta.rebuild(_intel([_ld(), _theme("x", rank=2)], "2026-06-20")) == []
    # build 4: steady state, and the whole whipsaw left no trace in the feed
    assert ta.rebuild(_intel([_ld(), _theme("x", rank=2)], "2026-06-21")) == []
    assert ta.load_events() == []


# ---------------------------------------------------- (b) flip held 2 builds: fires once
def test_constructive_flip_held_two_builds_fires_once_on_second(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", rank=2)], "2026-06-18")) == []  # seed
    assert ta.rebuild(_intel([_ld(), _theme("x", reco="accumulate", rank=2, score=60)],
                             "2026-06-19")) == []                    # build 2: buffered
    fired = ta.rebuild(_intel([_ld(), _theme("x", reco="accumulate", rank=2, score=62)],
                              "2026-06-20"))                         # build 3: confirmed
    assert len(fired) == 1 and fired[0]["type"] == "reco_change"
    assert fired[0]["context"]["from"] == "hold" and fired[0]["context"]["to"] == "accumulate"
    assert fired[0]["context"]["held_sessions"] == 2
    # id schema unchanged: themes:{asset}:{type}:{bucket}:{to_state}
    assert fired[0]["id"] == "themes:x:reco_change:2026-06-20:accumulate"
    # build 4: steady state fires nothing more — exactly once, total
    assert ta.rebuild(_intel([_ld(), _theme("x", reco="accumulate", rank=2, score=62)],
                             "2026-06-21")) == []
    assert len([e for e in ta.load_events() if e["type"] == "reco_change"]) == 1


def test_intraday_double_build_counts_as_one_session(tmp_path, monkeypatch):
    # The Asia lane double-builds intraday (daily + asia-close): two builds on the same
    # session date are ONE observation — a flip cannot confirm within half a day (the
    # measured churn is day-scale; cn_ai_compute's 06-22 ACC would otherwise confirm on
    # the second 06-22 build and revert 06-23). A same-day revert still kills the streak.
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", rank=2)], "2026-06-18")) == []  # seed
    acc = [_ld(), _theme("x", reco="accumulate", rank=2)]
    assert ta.rebuild(_intel(acc, "2026-06-19")) == []          # build 2 (session 1)
    assert ta.rebuild(_intel(acc, "2026-06-19")) == []          # same-session rebuild: no confirm
    fired = ta.rebuild(_intel(acc, "2026-06-20"))               # new session: confirmed
    assert len(fired) == 1 and fired[0]["context"]["held_sessions"] == 2


# ------------------------------------------------------ (c) risk direction: immediate
def test_risk_downgrade_fires_immediately_on_first_build(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    seed = _intel([_ld(), _theme("x", reco="accumulate", rank=2, score=60)], "2026-06-18")
    assert ta.rebuild(seed) == []
    fired = ta.rebuild(_intel([_ld(), _theme("x", reco="trim", rank=2, score=52)],
                              "2026-06-19"))
    assert len(fired) == 1 and fired[0]["type"] == "reco_change"
    assert fired[0]["context"]["to"] == "trim"        # never buffered, never delayed


def test_risk_label_events_pass_through_untouched(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", "dominant", "accumulate", 2, 70)],
                             "2026-06-18")) == []
    fired = ta.rebuild(_intel([_ld(), _theme("x", "fading", "trim", 2, 60)], "2026-06-19"))
    assert [e["type"] for e in fired] == ["theme_topping"]
    assert fired[0]["severity"] == "high"


def test_upgrade_stopping_at_hold_is_not_buffered(tmp_path, monkeypatch):
    # avoid -> hold is constructive-direction but not into ACCUMULATE/ENTER: it clears a
    # risk flag, so it stays immediate (only actionable-buy upgrades are debounced).
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", reco="avoid", rank=2, score=30)],
                             "2026-06-18")) == []
    fired = ta.rebuild(_intel([_ld(), _theme("x", reco="hold", rank=2, score=45)],
                              "2026-06-19"))
    assert len(fired) == 1 and fired[0]["context"]["to"] == "hold"


def test_downgrade_below_displayed_while_pending_still_fires(tmp_path, monkeypatch):
    # pending hold->accumulate streak, then raw falls to TRIM (below the displayed HOLD):
    # that is a genuine risk read relative to what the reader saw — immediate, no echo.
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", rank=2)], "2026-06-18")) == []
    assert ta.rebuild(_intel([_ld(), _theme("x", reco="accumulate", rank=2)],
                             "2026-06-19")) == []
    fired = ta.rebuild(_intel([_ld(), _theme("x", reco="trim", rank=2)], "2026-06-20"))
    assert len(fired) == 1 and fired[0]["context"]["to"] == "trim"


# ------------------------------------------- (d) leadership: thin margin never confirms
def test_leadership_flip_below_margin_never_fires(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_theme("a", rank=1, score=60), _theme("b", rank=2, score=58)],
                             "2026-06-18")) == []                    # seed: displayed = a
    for day in ("2026-06-19", "2026-06-20", "2026-06-21"):           # b leads 3 builds...
        fired = ta.rebuild(_intel([_theme("b", rank=1, score=60),
                                   _theme("a", rank=2, score=58)], day))
        assert [e for e in fired if e["type"] == "leadership_rotation"] == []
    # ...but a 2-point margin (< LEAD_MIN_MARGIN=3) is rank noise: never announced,
    # while the streak keeps counting in the persisted state
    state = json.loads((tmp_path / "themes" / "state.json").read_text())
    assert state["_debounce"]["lead"]["displayed"] == "a"
    assert state["_debounce"]["lead"]["pending"] == {"tid": "b", "count": 3,
                                                     "bucket": "2026-06-21"}


def test_leadership_flip_with_margin_held_two_builds_fires_once(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_theme("a", rank=1, score=60), _theme("b", rank=2, score=55)],
                             "2026-06-18")) == []                    # seed: displayed = a
    assert ta.rebuild(_intel([_theme("b", rank=1, score=65), _theme("a", rank=2, score=60)],
                             "2026-06-19")) == []                    # build 2: pending
    fired = ta.rebuild(_intel([_theme("b", rank=1, score=65), _theme("a", rank=2, score=60)],
                              "2026-06-20"))                         # build 3: confirmed
    rot = [e for e in fired if e["type"] == "leadership_rotation"]
    assert len(rot) == 1 and rot[0]["asset"] == "b"
    assert rot[0]["context"]["old_leader"] == "a"
    assert rot[0]["context"]["held_sessions"] == 2 and rot[0]["context"]["margin"] == 5
    assert rot[0]["id"] == "themes:b:leadership_rotation:2026-06-20:lead"
    # steady state: no re-fire
    assert ta.rebuild(_intel([_theme("b", rank=1, score=65), _theme("a", rank=2, score=60)],
                             "2026-06-21")) == []


def test_leadership_flip_that_reverts_never_fires(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_theme("a", rank=1, score=65), _theme("b", rank=2, score=55)],
                             "2026-06-18")) == []
    assert ta.rebuild(_intel([_theme("b", rank=1, score=66), _theme("a", rank=2, score=60)],
                             "2026-06-19")) == []                    # b takes #1 (pending)
    # a retakes #1: the whole round-trip is silent, and the pending streak is wiped
    fired = ta.rebuild(_intel([_theme("a", rank=1, score=66), _theme("b", rank=2, score=60)],
                              "2026-06-20"))
    assert [e for e in fired if e["type"] == "leadership_rotation"] == []
    state = json.loads((tmp_path / "themes" / "state.json").read_text())
    assert state["_debounce"]["lead"] == {"displayed": "a", "pending": None}
    assert ta.load_events() == []


# ------------------------------------------------- (e) old-format state: no streak keys
def test_old_format_state_file_without_streaks_is_streak_start(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    p = tmp_path / "themes" / "state.json"
    p.parent.mkdir(parents=True)
    # pre-debounce state.json: just the per-theme snapshot, no "_debounce" key
    p.write_text(json.dumps({
        "ld": {"label": "dominant", "reco": "hold", "rank": 1, "score": 90,
               "name": "LD", "name_zh": "ld"},
        "x": {"label": "neutral", "reco": "hold", "rank": 2, "score": 50,
              "name": "X", "name_zh": "x"},
    }))
    # no crash; the constructive flip is treated as a fresh streak start (buffered)
    assert ta.rebuild(_intel([_ld(), _theme("x", reco="accumulate", rank=2, score=58)],
                             "2026-06-19")) == []
    state = json.loads(p.read_text())
    assert state["_debounce"]["reco"]["x"] == {"from": "hold", "to": "accumulate",
                                               "count": 1, "bucket": "2026-06-19"}
    # and it confirms normally on the next build
    fired = ta.rebuild(_intel([_ld(), _theme("x", reco="accumulate", rank=2, score=58)],
                              "2026-06-20"))
    assert len(fired) == 1 and fired[0]["context"]["to"] == "accumulate"


def test_risk_downgrade_immediate_even_from_old_format_state(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    p = tmp_path / "themes" / "state.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        "x": {"label": "neutral", "reco": "accumulate", "rank": 1, "score": 60,
              "name": "X", "name_zh": "x"}}))
    fired = ta.rebuild(_intel([_theme("x", reco="avoid", rank=1, score=30)], "2026-06-19"))
    assert len(fired) == 1 and fired[0]["context"]["to"] == "avoid"


# ============================= theme_emerging debounce (new) =============================

# ---------------------------------------- (a) suppressed on first sighting, fires on 2nd
def test_theme_emerging_suppressed_first_build_fires_on_second(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    # seed: x is neutral
    assert ta.rebuild(_intel([_ld(), _theme("x", label="neutral", rank=2)],
                             "2026-06-18")) == []
    # build 2: x transitions neutral -> emerging — constructive, should be BUFFERED
    assert ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=60)],
                             "2026-06-19")) == []
    # build 3: x still emerging — streak now 2, should FIRE
    fired = ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=62)],
                              "2026-06-20"))
    assert len(fired) == 1
    assert fired[0]["type"] == "theme_emerging"
    assert fired[0]["asset"] == "x"
    assert fired[0]["context"]["from"] == "neutral"
    assert fired[0]["context"]["to"] == "emerging"
    assert fired[0]["context"]["held_sessions"] == 2
    assert fired[0]["id"] == "themes:x:theme_emerging:2026-06-20:emerging"
    # build 4: steady state — no re-fire
    assert ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=62)],
                             "2026-06-21")) == []
    assert len([e for e in ta.load_events() if e["type"] == "theme_emerging"]) == 1


# --------------------------------------- (b) streak reset when emerging label breaks
def test_theme_emerging_streak_reset_on_label_change(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", label="neutral", rank=2)],
                             "2026-06-18")) == []  # seed
    # build 2: x goes emerging (buffered)
    assert ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2)],
                             "2026-06-19")) == []
    # build 3: x drops back to neutral — streak dies, nothing fires
    assert ta.rebuild(_intel([_ld(), _theme("x", label="neutral", rank=2)],
                             "2026-06-20")) == []
    # build 4: x goes emerging again — fresh streak start, still buffered
    assert ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2)],
                             "2026-06-21")) == []
    # build 5: confirmed on the second consecutive emerging build
    fired = ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=65)],
                              "2026-06-22"))
    assert len(fired) == 1 and fired[0]["type"] == "theme_emerging"
    assert fired[0]["context"]["held_sessions"] == 2
    assert ta.load_events() != []


# ---------------------------------------- (c) theme_topping is still immediate
def test_theme_topping_still_fires_immediately(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert ta.rebuild(_intel([_ld(), _theme("x", label="dominant", reco="accumulate",
                                            rank=2, score=70)], "2026-06-18")) == []
    fired = ta.rebuild(_intel([_ld(), _theme("x", label="fading", reco="trim",
                                             rank=2, score=60)], "2026-06-19"))
    # must fire on the FIRST build with no buffering
    types = [e["type"] for e in fired]
    assert "theme_topping" in types
    topping = [e for e in fired if e["type"] == "theme_topping"][0]
    assert topping["severity"] == "high"
    # and only one build later the event already exists in the feed
    assert len([e for e in ta.load_events() if e["type"] == "theme_topping"]) == 1


# ------- (d) old-format state file without the "label" key must not crash ---------------
def test_old_format_state_without_label_key_does_not_crash(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    p = tmp_path / "themes" / "state.json"
    p.parent.mkdir(parents=True)
    # pre-label-debounce state.json: has _debounce but only "reco" and "lead" — no "label"
    p.write_text(json.dumps({
        "ld": {"label": "dominant", "reco": "hold", "rank": 1, "score": 90,
               "name": "LD", "name_zh": "ld"},
        "x": {"label": "neutral", "reco": "hold", "rank": 2, "score": 50,
              "name": "X", "name_zh": "x"},
        "_debounce": {
            "reco": {},
            "lead": {"displayed": "ld", "pending": None}
            # no "label" key — this is the old format
        },
    }))
    # must not raise; theme_emerging is buffered (fresh streak start)
    result = ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=55)],
                                "2026-06-19"))
    assert result == []
    # state now has the label key
    state = json.loads(p.read_text())
    assert "label" in state["_debounce"]
    assert state["_debounce"]["label"]["x"]["count"] == 1
    # and confirms on the next build normally
    fired = ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=55)],
                               "2026-06-20"))
    assert len(fired) == 1 and fired[0]["type"] == "theme_emerging"


# ---------- (e) dominant->emerging churn: 4 builds of oscillation produce one alert -----
def test_dominant_to_emerging_churn_fires_only_after_two_consecutive(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    # seed with dominant
    assert ta.rebuild(_intel([_ld(), _theme("x", label="dominant", rank=2, score=70)],
                             "2026-06-18")) == []
    # build 2: dominant -> emerging (buffered)
    assert ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=65)],
                             "2026-06-19")) == []
    # build 3: reverts to dominant — streak dies silently
    assert ta.rebuild(_intel([_ld(), _theme("x", label="dominant", rank=2, score=72)],
                             "2026-06-20")) == []
    # build 4: emerging again (new streak, count=1, buffered)
    assert ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=64)],
                             "2026-06-21")) == []
    # build 5: emerging again — count=2, CONFIRM fires
    fired = ta.rebuild(_intel([_ld(), _theme("x", label="emerging", rank=2, score=66)],
                              "2026-06-22"))
    assert len(fired) == 1 and fired[0]["type"] == "theme_emerging"
    assert len(ta.load_events()) == 1   # exactly one alert despite 4 oscillation builds
