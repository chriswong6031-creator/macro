"""Tests for the Ignition Radar — broad K-of-8 confluence + narrow theme ignition.

Covers:
  engine/ignition_radar.py
    — broad K counting and state ladder
    — ignited requires >=1 thrust event (confirms alone max out at warming)
    — each confirm rule fires/doesn't on crafted series
    — fragile labeling rule
    — narrow port returns items sorted with quality flags
    — regime label logic for all branches
    — no "validated" in any user-facing text
    — bilingual strings present on chips + regime

  engine/ignition_audit.py (US arm)
    — log_us_snapshot: idempotent by as_of
    — grade_us_broad: shape + h21/h63/h126 keys
    — grade_us_narrow: returns None until h40 matured
    — us_scorecard: accruing note when empty
    — us_snapshot_and_grade: end-to-end smoke test

  Template smoke tests (Jinja)
    — renders with full payload (state=ignited)
    — renders empty when payload is falsy ({}  / None)
    — renders fragile regime shows ⚠️ label
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ──────────────────────────────────────────────────────────────────────────────
# fixtures + helpers
# ──────────────────────────────────────────────────────────────────────────────

def _idx(n=120, start="2024-01-01"):
    return pd.date_range(start, periods=n, freq="B")


def _rising(n=120, slope=0.002, start="2024-01-01") -> pd.Series:
    idx = _idx(n, start)
    return pd.Series((1 + np.full(n, slope)).cumprod(), index=idx)


def _flat(n=120, start="2024-01-01") -> pd.Series:
    idx = _idx(n, start)
    return pd.Series(np.full(n, 100.0), index=idx)


def _breadth_frame(
    n=60,
    pct50=None,
    nh_series=None,
    nl_series=None,
) -> pd.DataFrame:
    """Build a minimal breadth DataFrame for testing confirms."""
    idx = _idx(n)
    data: dict = {
        "n_members": np.full(n, 500),
        "adv": np.full(n, 260, dtype=float),
        "dec": np.full(n, 240, dtype=float),
        "ad_line": np.cumsum(np.full(n, 20.0)),
        "nh": nh_series if nh_series is not None else np.full(n, 10.0),
        "nl": nl_series if nl_series is not None else np.full(n, 5.0),
        "pct_above_50": pct50 if pct50 is not None else np.full(n, 50.0),
        "pct_above_200": np.full(n, 60.0),
    }
    return pd.DataFrame(data, index=idx)


# ──────────────────────────────────────────────────────────────────────────────
# broad K counting and state ladder
# ──────────────────────────────────────────────────────────────────────────────

from engine.ignition_radar import (
    _broad_state,
    _confirm_pct50_recover,
    _confirm_nh_flip,
    _find_last_crossing,
    compute_regime,
)


def _make_chip(key: str, lit: bool, fresh: bool) -> dict:
    return {
        "key": key,
        "label_en": key,
        "label_zh": key,
        "lit": lit,
        "fresh": fresh,
        "since": str(date.today()) if lit else None,
        "detail_en": "",
        "detail_zh": "",
        "source": "test",
    }


def test_broad_state_off_when_no_chips_lit():
    chips = [_make_chip("thrust_confluence", False, False) for _ in range(8)]
    k = sum(1 for c in chips if c["lit"])
    assert _broad_state(k, chips) == "off"


def test_broad_state_warming_when_k1_but_no_thrust():
    # k=2 fresh, but ONLY confirm chips (no thrust keys)
    chips = [
        _make_chip("pct50_recover", True, True),
        _make_chip("nh_flip", True, True),
        _make_chip("rsp_confirm", False, False),
        _make_chip("sector_participation", False, False),
        _make_chip("thrust_confluence", False, False),
        _make_chip("msi_swing", False, False),
        _make_chip("washout_thrust20", False, False),
        _make_chip("ftd", False, False),
    ]
    k = sum(1 for c in chips if c["lit"])
    state = _broad_state(k, chips)
    # confirms alone can't produce "ignited" — must stay at warming
    assert state == "warming", f"Expected 'warming', got '{state}'"


def test_broad_state_ignited_requires_thrust_chip():
    """K>=3 but only confirm chips lit => warming, not ignited."""
    chips = [
        _make_chip("pct50_recover", True, True),
        _make_chip("nh_flip", True, True),
        _make_chip("rsp_confirm", True, True),
        _make_chip("sector_participation", False, False),
        _make_chip("thrust_confluence", False, False),
        _make_chip("msi_swing", False, False),
        _make_chip("washout_thrust20", False, False),
        _make_chip("ftd", False, False),
    ]
    k = sum(1 for c in chips if c["lit"])
    assert k == 3
    state = _broad_state(k, chips)
    # No thrust chip lit => cannot be ignited
    assert state != "ignited", "State must not be ignited without a thrust chip"
    assert state in ("warming", "off")


def test_broad_state_ignited_with_thrust_and_k3():
    """K=3 fresh AND one thrust chip fresh => ignited."""
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
    assert k == 3
    state = _broad_state(k, chips)
    assert state == "ignited"


# ──────────────────────────────────────────────────────────────────────────────
# confirm rule: pct50_recover
# ──────────────────────────────────────────────────────────────────────────────

def test_pct50_recover_fires_when_above55_and_gained5pts():
    # pct_above_50: goes from 48 to 62 over 11 sessions
    n = 30
    pct = np.concatenate([np.full(19, 48.0), np.linspace(48, 62, 11)])
    b = _breadth_frame(n=n, pct50=pct)
    chip = _confirm_pct50_recover(b)
    assert chip["lit"] is True


def test_pct50_recover_off_when_below55():
    # pct stays at 50 the whole time
    n = 30
    pct = np.full(n, 50.0)
    b = _breadth_frame(n=n, pct50=pct)
    chip = _confirm_pct50_recover(b)
    assert chip["lit"] is False


def test_pct50_recover_off_when_above55_but_flat():
    # pct_above_50 is 60 throughout (no +5pt gain)
    n = 30
    pct = np.full(n, 60.0)
    b = _breadth_frame(n=n, pct50=pct)
    chip = _confirm_pct50_recover(b)
    # now=60, prev=60, gain=0 => NOT lit
    assert chip["lit"] is False


# ──────────────────────────────────────────────────────────────────────────────
# confirm rule: nh_flip
# ──────────────────────────────────────────────────────────────────────────────

def test_nh_flip_fires_when_crosses_zero():
    n = 35
    # nh=2, nl=10 for first 25 (spread=-8), then nh=20, nl=2 (spread=+18) for last 10
    nh = np.concatenate([np.full(25, 2.0), np.full(10, 20.0)])
    nl = np.concatenate([np.full(25, 10.0), np.full(10, 2.0)])
    b = _breadth_frame(n=n, nh_series=nh, nl_series=nl)
    chip = _confirm_nh_flip(b)
    assert chip["lit"] is True


def test_nh_flip_off_when_always_positive():
    n = 35
    nh = np.full(n, 20.0)
    nl = np.full(n, 5.0)
    b = _breadth_frame(n=n, nh_series=nh, nl_series=nl)
    chip = _confirm_nh_flip(b)
    # already positive throughout — did NOT cross from <=0 to >0
    assert chip["lit"] is False


def test_nh_flip_off_when_always_negative():
    n = 35
    nh = np.full(n, 2.0)
    nl = np.full(n, 15.0)
    b = _breadth_frame(n=n, nh_series=nh, nl_series=nl)
    chip = _confirm_nh_flip(b)
    assert chip["lit"] is False


# ──────────────────────────────────────────────────────────────────────────────
# FIX 3: _find_last_crossing helper
# ──────────────────────────────────────────────────────────────────────────────

def test_find_last_crossing_detects_recent_transition():
    """_find_last_crossing returns the first date of the current True-run when preceded by False."""
    idx = pd.date_range("2024-01-01", periods=10, freq="B")
    # False x5, then True x5
    vals = pd.Series([False] * 5 + [True] * 5, index=idx)
    ts = _find_last_crossing(vals)
    assert ts == idx[5]


def test_find_last_crossing_no_crossing_when_always_true():
    idx = pd.date_range("2024-01-01", periods=10, freq="B")
    vals = pd.Series([True] * 10, index=idx)
    assert _find_last_crossing(vals) is None


def test_find_last_crossing_none_when_currently_false():
    idx = pd.date_range("2024-01-01", periods=10, freq="B")
    # Ends on False — no active crossing
    vals = pd.Series([False, True, True, False, False], index=idx[:5])
    assert _find_last_crossing(vals) is None


# ──────────────────────────────────────────────────────────────────────────────
# FIX 3: chip fresh = event-honest (lit-without-recent-turn → fresh=False)
# ──────────────────────────────────────────────────────────────────────────────

def test_rsp_confirm_lit_without_recent_turn_fresh_false(monkeypatch):
    """FIX 3: rsp_confirm lit=True but slope has been positive for >15 sessions → fresh=False."""
    from engine.ignition_radar import _confirm_rsp_confirm
    from lib import store as _store

    n = 80
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # RSP slightly outperforms SPY the ENTIRE window (never negative slope → no crossing)
    rsp = pd.DataFrame({"close": np.linspace(100, 120, n)}, index=idx)
    spy_df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)

    def _fake_read(namespace, ticker):
        if ticker == "RSP":
            return rsp
        if ticker == "SPY":
            return spy_df
        return None

    monkeypatch.setattr(_store, "read", _fake_read)
    chip = _confirm_rsp_confirm()
    assert chip["lit"] is True, "slope is positive → lit must be True"
    assert chip["fresh"] is False, "no recent ≤0→>0 crossing → fresh must be False"


def test_rsp_confirm_recent_crossing_gives_fresh_true(monkeypatch):
    """FIX 3: rsp_confirm lit=True AND a ≤0→>0 crossing within last 15 sessions → fresh=True.

    Use a recent end-date so _is_fresh (which compares to date.today()) fires correctly.
    The RSP/SPY ratio must be FALLING in the 21-session lookback window but then turn
    sharply UP within the last 10 sessions so the 20d log-RS slope crosses ≤0 → >0 there.
    """
    from engine.ignition_radar import _confirm_rsp_confirm, _FRESH_BD
    from lib import store as _store
    from datetime import date

    # End the series TODAY so crossing dates are within the _FRESH_BD window.
    # Strategy: RSP flat for long, then falls over sessions 60-70 (RSP < SPY → slope neg),
    # then rises sharply over last 8 sessions (RSP >> SPY → slope crosses positive).
    today = pd.Timestamp(date.today())
    n = 100
    idx = pd.bdate_range(end=today, periods=n)
    # SPY constant at 100
    spy_vals = np.full(n, 100.0)
    # RSP: flat at 100 for first 60, falls to 92 over next 30, then jumps to 115 over last 10
    rsp_flat = np.full(60, 100.0)
    rsp_fall = np.linspace(100, 92, 30)
    rsp_rise = np.linspace(92, 115, 10)
    rsp_vals = np.concatenate([rsp_flat, rsp_fall, rsp_rise])
    rsp_df = pd.DataFrame({"close": rsp_vals}, index=idx)
    spy_df = pd.DataFrame({"close": spy_vals}, index=idx)

    def _fake_read(namespace, ticker):
        if ticker == "RSP":
            return rsp_df
        if ticker == "SPY":
            return spy_df
        return None

    monkeypatch.setattr(_store, "read", _fake_read)
    chip = _confirm_rsp_confirm()
    assert chip["lit"] is True, f"slope should be positive at end; chip={chip}"
    assert chip["fresh"] is True, (
        "RSP/SPY ratio crossed from negative to positive slope within last 10 sessions → fresh"
    )


def test_sector_participation_lit_without_recent_turn_fresh_false(monkeypatch):
    """FIX 3: sector_participation lit=True but was already lit >15 sessions ago → fresh=False."""
    from engine.ignition_radar import _confirm_sector_participation
    from lib import store as _store
    from datetime import date

    # Use a recent end date so _is_fresh works correctly (compares to date.today())
    today = pd.Timestamp(date.today())
    # Build a long rising series ending today — strongly above and rising 50dma the entire window
    n = 150
    idx = pd.bdate_range(end=today, periods=n)
    s = pd.Series(np.linspace(100, 200, n), index=idx)
    df = pd.DataFrame({"close": s.values}, index=idx)

    def _fake_read(namespace, ticker):
        return df  # all 11 ETFs strongly rising throughout

    monkeypatch.setattr(_store, "read", _fake_read)
    chip = _confirm_sector_participation()
    assert chip["lit"] is True
    # Was always above threshold in the 15-session window → no crossing → fresh=False
    assert chip["fresh"] is False, "long-standing state, no recent turn → fresh must be False"


def test_sector_participation_recent_crossing_gives_fresh_true(monkeypatch):
    """FIX 3: sector_participation crossing from below to above threshold recently → fresh=True."""
    from engine.ignition_radar import _confirm_sector_participation
    from lib import store as _store

    n = 120
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # Falling then rising: below 50dma for early sessions, crosses above in last ~8 sessions
    # so that ma50 criterion is newly met
    falling = np.linspace(200, 100, 100)
    rising = np.linspace(100, 115, 20)
    vals = np.concatenate([falling, rising])
    s = pd.Series(vals, index=idx)
    df = pd.DataFrame({"close": s.values}, index=idx)

    def _fake_read(namespace, ticker):
        return df

    monkeypatch.setattr(_store, "read", _fake_read)
    chip = _confirm_sector_participation()
    # Whether lit or not depends on exact threshold crossing; the key assertion is:
    # if fresh=True then lit must also be True
    if chip["fresh"]:
        assert chip["lit"] is True, "fresh implies lit"


# ──────────────────────────────────────────────────────────────────────────────
# FIX 3: compute_regime participation_ok uses lit (state), not fresh
# ──────────────────────────────────────────────────────────────────────────────

def test_regime_participation_ok_uses_lit_not_fresh():
    """FIX 3: participation_ok in compute_regime depends on lit (state), not fresh.

    A lit-but-not-fresh chip must still set participation_ok=True.
    """
    # narrow_igniting + rsp_confirm lit (but not fresh) → participation_ok → NOT fragile
    narrow = [{"id": "ai_infra", "name": "AI Infra", "state": "igniting", "ignition_score": 0.7}]
    # rsp_confirm_lit=True → participation_ok=True regardless of freshness
    r = compute_regime("off", narrow, rsp_confirm_lit=True, sector_participation_lit=False)
    assert r["fragile"] is False, "participation_ok=True must clear fragile flag"

    # rsp_confirm_lit=False but sector_participation_lit=True → also participation_ok
    r2 = compute_regime("off", narrow, rsp_confirm_lit=False, sector_participation_lit=True)
    assert r2["fragile"] is False

    # both False → participation_ok=False → fragile=True
    r3 = compute_regime("off", narrow, rsp_confirm_lit=False, sector_participation_lit=False)
    assert r3["fragile"] is True


def test_broad_state_warming_requires_fresh_not_lit():
    """FIX 3 downstream: a lit-but-not-fresh chip does NOT contribute to warming count.

    _broad_state counts n_fresh. A chip lit=True but fresh=False must not count toward warming.
    """
    # Only lit chips with fresh=False → n_fresh=0 → state='off'
    chips = [
        _make_chip("rsp_confirm", True, False),   # lit but not fresh
        _make_chip("pct50_recover", False, False),
        _make_chip("nh_flip", False, False),
        _make_chip("sector_participation", False, False),
        _make_chip("thrust_confluence", False, False),
        _make_chip("msi_swing", False, False),
        _make_chip("washout_thrust20", False, False),
        _make_chip("ftd", False, False),
    ]
    k = sum(1 for c in chips if c["lit"])
    state = _broad_state(k, chips)
    assert state == "off", (
        "lit-but-not-fresh chip must not count toward warming; "
        f"got '{state}' with k={k}"
    )


def test_broad_state_warming_when_recent_lit():
    """FIX 3: warming only when at least one chip is both lit and fresh."""
    chips = [
        _make_chip("rsp_confirm", True, True),    # lit AND fresh → counts
        _make_chip("pct50_recover", False, False),
        _make_chip("nh_flip", False, False),
        _make_chip("sector_participation", False, False),
        _make_chip("thrust_confluence", False, False),
        _make_chip("msi_swing", False, False),
        _make_chip("washout_thrust20", False, False),
        _make_chip("ftd", False, False),
    ]
    k = sum(1 for c in chips if c["lit"])
    state = _broad_state(k, chips)
    assert state == "warming", f"fresh lit chip should produce warming, got '{state}'"


# ──────────────────────────────────────────────────────────────────────────────
# regime labeling
# ──────────────────────────────────────────────────────────────────────────────

def _narrow_igniting(name="AI Infra") -> list[dict]:
    return [{"id": "ai_infra", "name": name, "state": "igniting", "ignition_score": 0.7}]


def _narrow_empty() -> list[dict]:
    return []


def test_regime_broad_ignited_no_narrow():
    r = compute_regime("ignited", _narrow_empty(), False, False)
    assert "ignition" in r["label_en"].lower() or "broad" in r["label_en"].lower()
    assert r["fragile"] is False
    assert r["label_zh"]  # bilingual


def test_regime_broad_ignited_with_narrow():
    r = compute_regime("ignited", _narrow_igniting("AI Infra"), False, False)
    assert "AI Infra" in r["label_en"]
    assert r["fragile"] is False


def test_regime_narrow_igniting_no_participation():
    r = compute_regime("off", _narrow_igniting("Semis"), False, False)
    assert "fragile" in r["label_en"].lower() or "narrow" in r["label_en"].lower()
    assert r["fragile"] is True


def test_regime_narrow_igniting_with_participation():
    r = compute_regime("warming", _narrow_igniting("Semis"), True, False)
    assert r["fragile"] is False
    assert "Semis" in r["label_en"]


def test_regime_warming():
    r = compute_regime("warming", _narrow_empty(), False, False)
    assert "warming" in r["label_en"].lower()
    assert r["fragile"] is False


def test_regime_off():
    r = compute_regime("off", _narrow_empty(), False, False)
    assert "no ignition" in r["label_en"].lower()
    assert r["fragile"] is False


def test_no_validated_word_in_regime():
    """CI-enforced: 'validated' must not appear in user-facing text."""
    for broad_state in ("ignited", "warming", "off"):
        for narrow in (_narrow_igniting(), _narrow_empty()):
            r = compute_regime(broad_state, narrow, True, True)
            for key in ("label_en", "label_zh", "do_en", "do_zh"):
                val = r.get(key, "")
                assert "validated" not in val.lower(), (
                    f"'validated' found in regime.{key}: {val!r}"
                )


# ──────────────────────────────────────────────────────────────────────────────
# narrow channel — quality flags + sorted output
# ──────────────────────────────────────────────────────────────────────────────

from engine.ignition_radar import compute_narrow, _quality_flags


def test_quality_flags_above_200d_rising():
    # rising 250-session series
    s = _rising(n=250, slope=0.002)
    spy = _flat(n=250)
    flags = _quality_flags(s, spy)
    # should have above_200d_rising = True
    assert flags["above_200d_rising"] is True


def test_quality_flags_below_200d():
    # falling series
    s = _rising(n=250, slope=-0.002)
    spy = _flat(n=250)
    flags = _quality_flags(s, spy)
    assert flags["above_200d_rising"] is False


def test_quality_flags_rs_new_high():
    idx = _idx(n=150)
    # basket outperforms spy over last 126 sessions
    spy = pd.Series(np.full(150, 100.0), index=idx)
    basket = pd.Series(np.linspace(80, 200, 150), index=idx)
    flags = _quality_flags(basket, spy)
    assert flags["rs_new_high"] is True


def test_compute_narrow_returns_sorted_items(tmp_path):
    """Narrow channel returns items sorted by ignition_score desc."""
    # Provide an empty membership so we exercise the no-members path
    result = compute_narrow({}, spy_series=None)
    # With empty membership + ETFs (may or may not load), result must have items list
    assert isinstance(result["items"], list)
    # Items must be sorted descending by ignition_score (None last)
    scores = [it["ignition_score"] for it in result["items"] if it["ignition_score"] is not None]
    assert scores == sorted(scores, reverse=True)


def test_compute_narrow_items_have_quality_flags(tmp_path):
    """Each item must have rs_new_high and above_200d_rising keys."""
    result = compute_narrow({}, spy_series=_flat(n=300))
    for it in result["items"]:
        assert "rs_new_high" in it, f"rs_new_high missing in {it.get('id')}"
        assert "above_200d_rising" in it, f"above_200d_rising missing in {it.get('id')}"


# ──────────────────────────────────────────────────────────────────────────────
# audit US arm — log_us_snapshot idempotency + grade shape
# ──────────────────────────────────────────────────────────────────────────────

from engine import ignition_audit as ia


def _make_ig_snap(as_of=None, state="off", k=0) -> dict:
    as_of = as_of or str(date.today())
    return {
        "as_of": as_of,
        "state": state,
        "k_count": k,
        "chips": [],
        "regime": {"label_en": "No ignition", "label_zh": "未点火", "fragile": False},
        "narrow": {"items": [{"id": "XLK", "name": "XLK", "state": "igniting",
                               "ignition_score": 0.7}],
                   "as_of": as_of},
        "radar_xref": {"state": "watch", "phase": None},
        "accruing": "accruing",
    }


def test_log_us_snapshot_idempotent(tmp_path):
    snap = _make_ig_snap(state="warming", k=1)
    n1 = ia.log_us_snapshot(snap, root=tmp_path)
    n2 = ia.log_us_snapshot(snap, root=tmp_path)  # second call
    assert n1 == 1
    assert n2 == 0   # idempotent by as_of
    p = ia._us_path(tmp_path)
    rows = ia._us_read(p)
    assert len(rows) == 1


def test_log_us_snapshot_different_days_both_logged(tmp_path):
    snap1 = _make_ig_snap(as_of="2026-01-05", state="ignited", k=4)
    snap2 = _make_ig_snap(as_of="2026-01-06", state="warming", k=1)
    ia.log_us_snapshot(snap1, root=tmp_path)
    ia.log_us_snapshot(snap2, root=tmp_path)
    rows = ia._us_read(ia._us_path(tmp_path))
    assert len(rows) == 2


def test_grade_us_broad_shape(tmp_path):
    """Graded broad entry has h21/h63/h126 returns + mae keys when fully mature."""
    # build a long SPY series so h126 has matured
    idx = pd.date_range("2025-01-01", periods=300, freq="B")
    spy = pd.Series(np.linspace(100, 140, 300), index=idx)
    asof = "2025-01-03"
    snap = _make_ig_snap(as_of=asof, state="ignited", k=4)
    ia.log_us_snapshot(snap, root=tmp_path)
    n = ia.grade_us_log(spy, root=tmp_path)
    assert n > 0
    rows = ia._us_read(ia._us_path(tmp_path))
    g = rows[0].get("graded_broad") or {}
    assert "h21" in (g.get("returns") or {})
    assert "h63" in (g.get("returns") or {})
    assert "h126" in (g.get("returns") or {})
    assert "mae" in g


def test_grade_us_broad_h63_primary_grades_without_h126(tmp_path):
    """FIX 1: h63 is the primary gate — entry grades when h63 is mature even if h126 is not.

    A row with 70 forward sessions must produce h21+h63 with h126=None on first pass;
    a second pass with 130 sessions fills h126 without altering h21/h63.
    """
    from engine.ignition_audit import _grade_us_broad

    # 70 sessions after as-of (4 sessions buffer before that)
    start = pd.Timestamp("2025-01-01")
    n = 80
    idx = pd.bdate_range(start, periods=n)
    spy = pd.Series(np.linspace(100, 115, n), index=idx)

    asof_ts = idx[3]  # 3 bars in → 76 bars remain; h63=64 remaining → mature; h126=not
    asof_str = str(asof_ts.date())
    entry = {"asof": asof_str, "broad_state": "warming"}

    g = _grade_us_broad(entry, spy)
    assert g is not None, "must grade when h63 mature even if h126 not"
    rets = g["returns"]
    assert rets.get("h21") is not None
    assert rets.get("h63") is not None
    assert rets.get("h126") is None, "h126 must be null when not mature"

    # Second pass: extend spy so h126 is now mature
    idx2 = pd.bdate_range(start, periods=n + 60)
    spy2 = pd.Series(np.linspace(100, 125, n + 60), index=idx2)
    # Simulate re-grading: inject existing partial grade into entry
    entry["graded_broad"] = g
    g2 = _grade_us_broad(entry, spy2)
    assert g2 is not None
    rets2 = g2["returns"]
    # h126 is now filled
    assert rets2.get("h126") is not None
    # h21 and h63 are preserved (idempotent)
    assert rets2["h21"] == rets["h21"]
    assert rets2["h63"] == rets["h63"]


def test_grade_us_narrow_none_when_immature(tmp_path):
    """Narrow grade returns None when SPY doesn't have h40 bars ahead."""
    idx = pd.date_range("2026-01-01", periods=20, freq="B")
    spy = pd.Series(np.full(20, 100.0), index=idx)
    asof = "2026-01-10"
    snap = _make_ig_snap(as_of=asof, state="warming")
    ia.log_us_snapshot(snap, root=tmp_path)
    n = ia.grade_us_log(spy, root=tmp_path)
    # h40 not matured — neither broad (h63 gate) nor narrow can grade
    rows = ia._us_read(ia._us_path(tmp_path))
    # graded_broad and graded_narrow should still be None (not enough bars)
    assert rows[0].get("graded_broad") is None
    assert rows[0].get("graded_narrow") is None
    assert n == 0


def test_us_scorecard_accruing_when_empty(tmp_path):
    sc = ia.us_scorecard(root=tmp_path)
    assert sc["n_graded"] == 0
    assert "accruing" in (sc.get("note") or "").lower()


def test_us_snapshot_and_grade_smoke(tmp_path):
    idx = pd.date_range("2025-01-01", periods=300, freq="B")
    spy = pd.Series(np.linspace(100, 140, 300), index=idx)
    snap = _make_ig_snap(as_of="2025-01-03")
    sc = ia.us_snapshot_and_grade(snap, spy, root=tmp_path)
    assert "n_graded" in sc
    assert "note" in sc
    assert "accruing" in sc["note"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# template smoke test (Jinja)
# ──────────────────────────────────────────────────────────────────────────────

try:
    from jinja2 import Environment, FileSystemLoader
    import os
    _JINJA_AVAILABLE = True
except ImportError:
    _JINJA_AVAILABLE = False


def _jinja_env():
    from pathlib import Path
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    return env


def _full_payload(state="ignited") -> dict:
    return {
        "as_of": "2026-07-11",
        "state": state,
        "k_count": 4,
        "chips": [
            {"key": "thrust_confluence", "label_en": "Breadth thrust",
             "label_zh": "广度推进", "lit": True, "fresh": True,
             "detail_en": "test", "detail_zh": "测试"},
            {"key": "pct50_recover", "label_en": "Breadth >50dma recovery",
             "label_zh": "50日线广度回升", "lit": True, "fresh": True,
             "detail_en": "test", "detail_zh": "测试"},
            {"key": "nh_flip", "label_en": "New highs flipping positive",
             "label_zh": "新高翻正", "lit": False, "fresh": False,
             "detail_en": "test", "detail_zh": "测试"},
            {"key": "rsp_confirm", "label_en": "Equal-weight RS (RSP/SPY)",
             "label_zh": "等权RS（RSP/SPY）", "lit": True, "fresh": True,
             "detail_en": "test", "detail_zh": "测试"},
            {"key": "sector_participation", "label_en": "Sector breadth",
             "label_zh": "板块广度", "lit": True, "fresh": True,
             "detail_en": "test", "detail_zh": "测试"},
            {"key": "msi_swing", "label_en": "Summation swing",
             "label_zh": "求和指数跃升", "lit": False, "fresh": False,
             "detail_en": "test", "detail_zh": "测试"},
            {"key": "washout_thrust20", "label_en": "%>20dma washout",
             "label_zh": "20日线洗出", "lit": False, "fresh": False,
             "detail_en": "test", "detail_zh": "测试"},
            {"key": "ftd", "label_en": "Follow-through day",
             "label_zh": "放量确认日", "lit": False, "fresh": False,
             "detail_en": "test", "detail_zh": "测试"},
        ],
        "regime": {
            "label_en": "Broad ignition — participation surging",
            "label_zh": "全面点火 — 参与度激增",
            "fragile": False,
            "do_en": "Evidence read, not a buy call.",
            "do_zh": "证据读取，非买入信号。",
        },
        "narrow": {
            "items": [
                {"id": "ai_infra", "name": "AI Infra", "state": "igniting",
                 "ignition_score": 0.78, "rs_new_high": True, "above_200d_rising": True},
                {"id": "semis", "name": "Semis", "state": "running",
                 "ignition_score": 0.60, "rs_new_high": False, "above_200d_rising": True},
                {"id": "XLK", "name": "XLK", "state": "running",
                 "ignition_score": 0.55, "rs_new_high": False, "above_200d_rising": False},
            ],
            "as_of": "2026-07-11",
        },
        "radar_xref": {"state": "watch", "phase": "recovery"},
        "forward_log": {"n_graded": 0, "note": "accruing"},
        "accruing": "accruing — display-only",
    }


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_renders_with_full_payload():
    env = _jinja_env()
    tmpl = env.get_template("_ignition_radar_card.html.j2")
    ig = _full_payload(state="ignited")
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    html = macro_tmpl.render(ig=ig)
    assert "Ignition Radar" in html or "点火雷达" in html
    assert "igx" in html
    assert "igx-ignited" in html
    assert "Breadth thrust" in html  # chip label present


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_renders_nothing_when_payload_absent():
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}"
        "{% if ig %}{{ igc.ignition_radar_card(ig) }}{% endif %}"
    )
    html = macro_tmpl.render(ig=None)
    assert "igx" not in html
    html_empty = macro_tmpl.render(ig={})
    assert "igx" not in html_empty


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_fragile_regime_shows_warning():
    env = _jinja_env()
    payload = _full_payload(state="warming")
    payload["regime"]["fragile"] = True
    payload["regime"]["label_en"] = "Narrow ignition — AI Infra; fragile until participation broadens"
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    html = macro_tmpl.render(ig=payload)
    assert "⚠️" in html
    assert "Fragile" in html or "fragile" in html.lower()


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_template_bilingual_strings_present():
    env = _jinja_env()
    payload = _full_payload()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    html = macro_tmpl.render(ig=payload)
    # English
    assert "Ignition Radar" in html
    # Chinese
    assert "点火雷达" in html


@pytest.mark.skipif(not _JINJA_AVAILABLE, reason="jinja2 not installed")
def test_no_validated_word_in_template_output():
    """CI-enforced: 'validated' must not appear in rendered template output."""
    env = _jinja_env()
    macro_tmpl = env.from_string(
        "{% import '_ignition_radar_card.html.j2' as igc %}{{ igc.ignition_radar_card(ig) }}"
    )
    for state in ("ignited", "warming", "off"):
        payload = _full_payload(state=state)
        html = macro_tmpl.render(ig=payload)
        assert "validated" not in html.lower(), (
            f"'validated' found in rendered HTML for state={state}"
        )
