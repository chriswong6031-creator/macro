"""Rotation Command W1 — RC-R1 detector + lifecycle (engine/rotation_events.py).

Synthetic legs replicate the 2026-06 shape: leg A (memory-like) melts up then crashes,
leg B (mag7-like) declines to a fresh low then reclaims. The three-way AND must fire on
the handoff, must NOT fire mid-blowoff (the naive misfire), and the lifecycle must close
on lapse/TTL and honor the re-fire lockout. Network-free.
"""
from __future__ import annotations

import pandas as pd

from engine import rotation_events as re_


def _series(vals) -> pd.Series:
    idx = pd.bdate_range("2024-01-02", periods=len(vals))
    return pd.Series(list(vals), index=idx, dtype=float)


def _blowoff_leg(n_flat=280, runup=20, crash=6) -> pd.Series:
    """Flat → +2%/session for `runup` sessions (≈ +49% over 20) → −4%/session for `crash`."""
    vals = [100.0] * n_flat
    for _ in range(runup):
        vals.append(vals[-1] * 1.02)
    for _ in range(crash):
        vals.append(vals[-1] * 0.96)
    return _series(vals)


def _turn_leg(n_flat=280, decline=20, rise=6) -> pd.Series:
    """Flat → −0.8%/session for `decline` (fresh 40d low) → +1.2%/session for `rise`."""
    vals = [100.0] * n_flat
    for _ in range(decline):
        vals.append(vals[-1] * 0.992)
    for _ in range(rise):
        vals.append(vals[-1] * 1.012)
    return _series(vals)


# ------------------------------------------------------------------ signatures ----

def test_blowoff_crash_fires_on_meltup_then_crash():
    r = re_.blowoff_crash(_blowoff_leg())
    assert r is not None
    assert r["runup_pct"] > 0.15
    assert r["runup_z"] >= 2.0
    assert r["drawdown_pct"] > 0.10


def test_blowoff_crash_none_on_flat_and_none_mid_blowoff():
    assert re_.blowoff_crash(_series([100.0] * 320)) is None
    # truncate before the crash: still making highs → no signature
    mid = _blowoff_leg(crash=0)
    assert re_.blowoff_crash(mid) is None


def test_blowoff_crash_abs_runup_path_when_z_fails():
    """A year-long melt-up inflates its own trailing ret20 distribution (memory June
    2026 scored z=1.6 on a +47%/20s runup) — the absolute-runup path must still fire."""
    p = dict(re_.PARAMS)
    p["runup_z_min"] = 99.0                 # force the z path off
    r = re_.blowoff_crash(_blowoff_leg(), p)
    assert r is not None
    assert r["qualified_by"] == "abs_runup"
    assert r["runup_pct"] >= p["runup_strong"]


def test_blowoff_crash_none_on_ordinary_decline():
    # a drawdown without a preceding z-scored runup is a downtrend, not a blowoff-crash
    vals = [100.0] * 280 + [100.0 * (0.99 ** k) for k in range(1, 27)]
    assert re_.blowoff_crash(_series(vals)) is None


def test_turn_up_fires_after_low_and_reclaim():
    r = re_.turn_up(_turn_leg())
    assert r is not None
    assert r["off_low_pct"] >= 0.03
    assert r["reclaimed"] is True


def test_turn_up_none_while_still_falling():
    assert re_.turn_up(_turn_leg(rise=0)) is None


def test_turn_up_phase_family_substitutes_reclaim():
    # a +3.1% pop off yesterday's low that stays BELOW the prior-5-session max (the
    # declining tape above it): no reclaim yet — but a Trough-family phase substitutes
    s = _turn_leg(rise=0)
    pop = pd.Series([float(s.iloc[-1]) * 1.031],
                    index=pd.bdate_range(s.index[-1] + pd.Timedelta(days=1), periods=1))
    s = pd.concat([s, pop])
    base = re_.turn_up(s)
    withphase = re_.turn_up(s, phase="Trough")
    assert withphase is not None
    assert base is None
    assert withphase.get("phase") == "Trough"


def test_pair_confirm_inflection():
    a, b = _blowoff_leg(), _turn_leg()
    n = min(len(a), len(b))
    r = re_.pair_confirm(b.iloc[-n:], a.iloc[-n:])
    assert r is not None
    assert r["ratio_chg_10s"] > 0


# ------------------------------------------------------------- pair evaluation ----

def _aligned_pair():
    a, b = _blowoff_leg(), _turn_leg()
    n = min(len(a), len(b))
    a, b = a.iloc[-n:], b.iloc[-n:]
    b.index = a.index
    return a, b


def test_evaluate_pair_fires_on_handoff():
    a, b = _aligned_pair()
    r = re_.evaluate_pair(a, b)
    assert r is not None
    assert set(r) >= {"blowoff", "turn", "ratio", "asof"}


def test_evaluate_pair_suppresses_naive_midblowoff_fire():
    """Mid-June analogue: A still blowing off, B still declining → nothing fires,
    in either direction."""
    a = _blowoff_leg(crash=0)
    b = _turn_leg(rise=0)
    n = min(len(a), len(b))
    a, b = a.iloc[-n:], b.iloc[-n:]
    b.index = a.index
    assert re_.evaluate_pair(a, b) is None
    assert re_.evaluate_pair(b, a) is None       # reverse pair equally quiet


def test_find_start_is_on_or_after_the_low():
    a, b = _aligned_pair()
    started = re_.find_start(a, b)
    low_date = re_.turn_up(b)["low_date"]
    assert started >= low_date


# ------------------------------------------------------------------- lifecycle ----

def _sectors(a, b):
    cfg = {"key": "xlk", "etf": "XLK", "name_en": "Technology", "name_zh": "科技",
           "legs": [
               {"key": "memory", "tier": "secondary", "name_en": "Memory", "name_zh": "存储"},
               {"key": "mag7", "tier": "primary", "name_en": "Mag 7", "name_zh": "七巨头"},
           ]}
    return {"xlk": {"cfg": cfg, "etf_close": a,
                    "legs": {"memory": a, "mag7": b}, "leg_meta": {}}}


def test_step_pairs_creates_event_with_receipts_and_copy():
    a, b = _aligned_pair()
    state, active, created, closed = re_.step_pairs(_sectors(a, b), {})
    assert "xlk:memory->mag7" in created
    ev = next(e for e in active if e["id"] == "xlk:memory->mag7")
    assert ev["severity"] in ("notable", "major")     # mag7 leg is primary
    assert ev["day_n"] >= 1
    assert "Rotation" in ev["copy_en"] and "轮动" in ev["copy_zh"]
    assert not closed
    assert "xlk:memory->mag7" in state["active"]


def test_step_pairs_lapse_closes_event():
    a, b = _aligned_pair()
    state, _, created, _ = re_.step_pairs(_sectors(a, b), {})
    assert created
    # conditions gone: both legs flat-extended so nothing fires, ratio slope ~0
    idx = pd.bdate_range(a.index[-1] + pd.Timedelta(days=1), periods=40)
    flat_a = pd.concat([a, pd.Series(float(a.iloc[-1]), index=idx)])
    flat_b = pd.concat([b, pd.Series(float(b.iloc[-1]), index=idx)])
    p = dict(re_.PARAMS)
    closed_seen = []
    for k in range(p["lapse_run"] + p["ttl_sessions"] + 2):
        state, active, _, closed = re_.step_pairs(
            _sectors(flat_a.iloc[:len(a) + k + 1], flat_b.iloc[:len(b) + k + 1]), state, p)
        closed_seen += closed
        if closed:
            break
    assert closed_seen, "event never closed on lapse/TTL"
    assert closed_seen[0]["reason"] in ("conditions_lapsed", "ttl", "ratio_slope_flipped")
    assert "xlk:memory->mag7" not in state["active"]


def test_step_pairs_lockout_blocks_immediate_refire():
    a, b = _aligned_pair()
    asof = str(a.index[-1].date())
    state = {"active": {}, "closed": {"xlk:memory->mag7": asof}}
    state2, active, created, _ = re_.step_pairs(_sectors(a, b), state)
    assert "xlk:memory->mag7" not in created
    assert all(e["id"] != "xlk:memory->mag7" for e in active)


def test_severity_tiers_and_bump():
    rc = {"blowoff": {"drawdown_pct": 0.20, "peak_date": "x", "runup_pct": .3, "runup_z": 3},
          "turn": {"low_date": "x", "off_low_pct": 0.09, "reclaimed": True},
          "ratio": {}}
    small = {"blowoff": {**rc["blowoff"], "drawdown_pct": 0.11},
             "turn": {**rc["turn"], "off_low_pct": 0.03}, "ratio": {}}
    assert re_.severity({"tier": "primary"}, {"tier": "primary"}, small) == "major"
    assert re_.severity({"tier": "secondary"}, {"tier": "primary"}, small) == "notable"
    assert re_.severity({"tier": "secondary"}, {"tier": "secondary"}, small) == "standard"
    # move-size bump lifts one level
    assert re_.severity({"tier": "secondary"}, {"tier": "secondary"}, rc) == "notable"


def test_coldstart_replay_equals_incremental_stepping():
    """Deploy-mid-episode invariant: replaying the trailing window from scratch must
    land on the same active state as having stepped nightly all along."""
    a, b = _aligned_pair()
    p = dict(re_.PARAMS)
    replay_state, _, _ = re_.coldstart_replay(_sectors(a, b), p)
    inc_state: dict = {}
    idx = a.dropna().index
    for cut in idx[-p["coldstart_backscan"]:-1]:
        inc_state, *_ = re_.step_pairs(
            _sectors(a.loc[:cut], b.loc[:cut]), inc_state, p)
    ra = replay_state.get("active", {}).get("xlk:memory->mag7")
    ia = inc_state.get("active", {}).get("xlk:memory->mag7")
    assert (ra is None) == (ia is None)
    if ra:
        assert ra["started"] == ia["started"]


def test_run_nightly_persists_state_ledger_and_payload(tmp_path):
    a, b = _aligned_pair()
    payload = re_.run_nightly(_sectors(a, b), tmp_path, generated_utc="test")
    assert payload["schema"] == "rotation_events.v1"
    assert payload["authority"]["may_gate"] is False
    # first run cold-starts: the event is created during the replay (flagged in the
    # ledger) or, if it only fires on the final bar, in created_tonight
    assert payload["active"]
    assert payload["created_tonight"] or payload["coldstart"]
    assert (tmp_path / "rotation_events" / "state.json").exists()
    lines = (tmp_path / "rotation_events" / "events.jsonl").read_text().strip().splitlines()
    assert any('"event": "created"' in ln or '"event":"created"' in ln for ln in lines)
    # second run: same event still active, nothing re-created
    payload2 = re_.run_nightly(_sectors(a, b), tmp_path, generated_utc="test")
    assert not payload2["created_tonight"]
    assert any(e["id"] == "xlk:memory->mag7" for e in payload2["active"])
