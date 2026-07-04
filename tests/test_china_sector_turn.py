"""Sector washout→turn map tests (engine/china_sector_turn.py).

Synthetic checks (no disk): the two display-boost legs fire exactly per spec —
leg A = sector washed out AND the composite fires a fresh 2D-MACD x 3D-StochRSI
turn (cascade T2/T3; T4 excluded); leg B = a broad share of washed-out peers have
stopped falling (decline velocity collapsed / slight uptick). A rising sector never
boosts even with basing peers; thin sectors and short panels degrade to absent.
The cascade verdict itself is validated in its own tests — here it is monkeypatched
so the map logic is tested deterministically."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_sector_turn as cst  # noqa: E402

N_SESSIONS = 160
_DATES = pd.bdate_range("2024-01-01", periods=N_SESSIONS)


def _name(shape: str, i: int) -> pd.Series:
    """One synthetic close series (~160 sessions), per shape:
      based    flat 100 → decline to 80 (sessions 96..139) → flat 80 (last 21)
      perking  same decline → gentle rise 80→82 over the last 21
      falling  same decline slope, continuing through the last session
      rising   flat 100 → ramp to 120 over the last 63
    A tiny per-name offset keeps columns distinct without changing the shape."""
    off = 1.0 + i * 0.001
    flat = np.full(96, 100.0)
    if shape == "rising":
        v = np.concatenate([np.full(97, 100.0), np.linspace(100.0, 120.0, 63)])
    elif shape == "falling":
        v = np.concatenate([flat, np.linspace(100.0, 70.0, 64)])
    else:
        decline = np.linspace(100.0, 80.0, 44)
        tail = (np.linspace(80.0, 82.0, 21) if shape == "perking" else np.full(21, 80.0))
        v = np.concatenate([flat, decline[1:], tail])
    return pd.Series(v[:N_SESSIONS] * off, index=_DATES)


def _panel(shapes: dict[str, str]):
    """Panel of 10 names per sector; `shapes` maps sector → member shape."""
    closes, sec = {}, {}
    for s, shape in shapes.items():
        for i in range(10):
            t = f"{s}{i}"
            closes[t] = _name(shape, i)
            sec[t] = s
    return pd.DataFrame(closes), sec


_BLANK = {"tier": None, "ticks": None, "sub": None, "provisional": False}


def _patch_cascade(monkeypatch, by_len: dict | None = None, verdict: dict | None = None):
    """Replace the (separately validated) cascade with a controlled verdict."""
    v = dict(_BLANK, **(verdict or {}))
    monkeypatch.setattr(cst, "cascade", lambda idx, **k: dict(v))


def test_leg_turn_boost2(monkeypatch):
    _patch_cascade(monkeypatch, verdict={"tier": "T2", "ticks": 1, "sub": "deep"})
    closes, sec = _panel({"Health": "falling"})          # washed out, index "turns" (patched)
    out = cst.sector_turn_map(closes, sec)
    rec = out["sectors"]["Health"]
    assert rec["washout"] and rec["leg_turn"] and rec["boost"] == 2
    assert rec["turn"]["tier"] == "T2" and rec["turn"]["ticks"] == 1


def test_t3_projected_counts_t4_does_not(monkeypatch):
    closes, sec = _panel({"Health": "falling"})
    _patch_cascade(monkeypatch, verdict={"tier": "T3", "ticks": 0})
    assert cst.sector_turn_map(closes, sec)["sectors"]["Health"]["boost"] == 2
    _patch_cascade(monkeypatch, verdict={"tier": "T4", "ticks": 0})
    rec = cst.sector_turn_map(closes, sec)["sectors"]["Health"]
    assert rec["turn"] is None and rec["leg_turn"] is False   # 2D-stoch tier ≠ the 3D turn


def test_peers_basing_boost1(monkeypatch):
    _patch_cascade(monkeypatch)                          # no composite turn
    closes, sec = _panel({"Tech": "based"})
    rec = cst.sector_turn_map(closes, sec)["sectors"]["Tech"]
    assert rec["washout"] and not rec["leg_turn"]
    assert rec["peers"]["washed_n"] >= cst.PEER_WASHED_N_MIN
    assert rec["peers"]["based_frac"] >= cst.PEER_BASED_FRAC_MIN
    assert rec["leg_peers"] and rec["boost"] == 1


def test_perking_peers_counted(monkeypatch):
    _patch_cascade(monkeypatch)
    closes, sec = _panel({"Tech": "perking"})
    rec = cst.sector_turn_map(closes, sec)["sectors"]["Tech"]
    assert rec["leg_peers"] and rec["peers"]["perk_n"] > 0


def test_still_falling_no_boost(monkeypatch):
    _patch_cascade(monkeypatch)
    closes, sec = _panel({"Energy": "falling"})          # washed out but nothing basing
    rec = cst.sector_turn_map(closes, sec)["sectors"]["Energy"]
    assert rec["washout"] and rec["peers"]["based_n"] == 0 and rec["boost"] == 0


def test_rising_sector_never_boosts(monkeypatch):
    # even a fresh composite cross must not boost when the sector never washed out
    _patch_cascade(monkeypatch, verdict={"tier": "T2", "ticks": 0})
    closes, sec = _panel({"Momo": "rising"})
    rec = cst.sector_turn_map(closes, sec)["sectors"]["Momo"]
    assert not rec["washout"] and rec["boost"] == 0


def test_thin_and_junk_sectors_skipped(monkeypatch):
    _patch_cascade(monkeypatch)
    closes, sec = _panel({"Big": "based"})
    for i in range(3):                                    # 3 members < MIN_MEMBERS
        t = f"Thin{i}"
        closes[t] = _name("based", i)
        sec[t] = "Thin"
    junk = _name("based", 5)
    closes["JUNK0"] = junk
    sec["JUNK0"] = "—"
    out = cst.sector_turn_map(closes, sec)
    assert "Big" in out["sectors"]
    assert "Thin" not in out["sectors"] and "—" not in out["sectors"]


def test_short_panel_degrades():
    closes, sec = _panel({"Health": "based"})
    assert cst.sector_turn_map(closes.iloc[-60:], sec) == {}
    assert cst.sector_turn_map(pd.DataFrame(), sec) == {}
    assert cst.sector_turn_map(None, sec) == {}
