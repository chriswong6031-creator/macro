"""W6 #22 follow-up — the T3 provisional-basis flag + the config-gated hysteretic veto.

The replay (research/PROVISIONAL_TIER_REPLAY.md) measured T3 fresh fires repainting at
23.8% US / 15.1% CN — above the ~15% flip criterion — while T1/T2 are fine (5.3%/8.8%).
The proportionate response: `provisional: true` is emitted on T3 rows ONLY, flows through
signal_gate's verdict/compact/buy_signal so every board badge can render it; and the
not-topped veto can be debounced (engine/hysteresis, confirm>=2) via the
VETO_HYSTERESIS_CONFIRM env var — default OFF (single-bar, incumbent behaviour).

Pins:
  1. provisional == (tier == "T3") on every cascade output (blank/thin-history included).
  2. A real T3 fire (pinned synthetic fixture) carries provisional=True end-to-end through
     signal_gate.gate -> compact() -> buy_signal().
  3. VETO_HYSTERESIS_CONFIRM unset/1/garbage == the incumbent single-bar veto, exactly.
  4. confirm=2 debounces the cascade's own daily veto stream (wiring == the library), and
     on a pinned wiggle day it HOLDS a name the single-bar veto would blank.

All fixtures in-memory. Run:  python -m pytest tests/test_provisional_badge.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import confluence_tiers, signal_gate  # noqa: E402


def _synthetic_close(n=520, seed=0) -> pd.Series:
    """Same cyclical fixture the replay tests use — crosses actually fire."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    idx = pd.bdate_range("2023-01-02", periods=n)
    base = 100 + 12 * np.sin(t / 24) + 0.03 * t + 4 * np.sin(t / 6)
    noise = np.cumsum(rng.normal(0, 0.3, n))
    return pd.Series(base + noise, index=idx)


# ------------------------------------------------------------- 1. the T3-only invariant
def test_blank_and_thin_history_are_not_provisional():
    assert confluence_tiers._BLANK["provisional"] is False
    thin = _synthetic_close(n=60)
    out = confluence_tiers.cascade(thin, take_active=True)   # thin-history T1 trust path
    assert out["tier"] == "T1" and out["provisional"] is False


def test_provisional_iff_tier_is_t3():
    """provisional must be True exactly when the graded tier is T3 — never on T1/T2/T4/blank."""
    for seed in range(4):
        c = _synthetic_close(seed=seed)
        for cut in range(0, 80, 10):
            out = confluence_tiers.cascade(c.iloc[: len(c) - cut])
            assert out["provisional"] == (out["tier"] == "T3"), (
                f"seed={seed} cut={cut}: tier={out['tier']} provisional={out['provisional']}")


def test_t3_fire_is_provisional_end_to_end():
    """A real T3 fire (pinned fixture: seed=50 truncated at 2023-11-17 grades T3) carries the
    flag through the cascade, the gate verdict, and BOTH display subsets."""
    c = _synthetic_close(seed=50)
    trunc = c[c.index <= pd.Timestamp("2023-11-17")]
    casc = confluence_tiers.cascade(trunc)
    assert casc["tier"] == "T3", "fixture drifted — expected a T3 fire on this truncation"
    assert casc["provisional"] is True
    v = signal_gate.gate("SYN", trunc)
    assert v["tier_cascade"] == "T3" and v["provisional"] is True
    assert signal_gate.compact(v)["provisional"] is True
    assert signal_gate.buy_signal(v)["provisional"] is True
    assert signal_gate.is_buyable(v)   # provisional NEVER changes buyability — display-only


def test_non_t3_verdict_is_not_provisional():
    """A T1/T2/blank gate verdict never carries the flag (and the key is always present)."""
    for seed in range(3):
        c = _synthetic_close(seed=seed)
        v = signal_gate.gate("SYN", c)
        assert "provisional" in v
        if v.get("tier_cascade") != "T3":
            assert v["provisional"] is False


# ------------------------------------------------------- 2. config-gated hysteretic veto
def test_veto_confirm_env_parsing(monkeypatch):
    monkeypatch.delenv("VETO_HYSTERESIS_CONFIRM", raising=False)
    assert confluence_tiers._veto_confirm() == 1
    monkeypatch.setenv("VETO_HYSTERESIS_CONFIRM", "2")
    assert confluence_tiers._veto_confirm() == 2
    monkeypatch.setenv("VETO_HYSTERESIS_CONFIRM", "0")
    assert confluence_tiers._veto_confirm() == 1        # floor at 1 (single-bar)
    monkeypatch.setenv("VETO_HYSTERESIS_CONFIRM", "junk")
    assert confluence_tiers._veto_confirm() == 1        # garbage -> incumbent behaviour


def test_confirm_1_is_byte_identical_to_default(monkeypatch):
    """confirm=1 must reproduce the incumbent single-bar veto EXACTLY (safe A/B)."""
    c = _synthetic_close(seed=3)
    for cut in (0, 15, 30):
        trunc = c.iloc[: len(c) - cut]
        monkeypatch.delenv("VETO_HYSTERESIS_CONFIRM", raising=False)
        base = confluence_tiers.cascade(trunc)
        monkeypatch.setenv("VETO_HYSTERESIS_CONFIRM", "1")
        one = confluence_tiers.cascade(trunc)
        assert base == one


def test_hysteresis_holds_through_single_bar_veto_wiggle(monkeypatch):
    """Pinned fixture (seed=0, last 20 bars dropped): the single-bar veto blanks the name
    (not_topped False) on a short topped run, the confirm=2 debounce holds it constructive —
    the flicker-suppression direction the replay measured (flicker 1.6% -> 0.0%)."""
    trunc = _synthetic_close(seed=0).iloc[:500]
    monkeypatch.delenv("VETO_HYSTERESIS_CONFIRM", raising=False)
    single = confluence_tiers.cascade(trunc)
    assert single["not_topped"] is False, "fixture drifted — expected a single-bar veto trip"
    monkeypatch.setenv("VETO_HYSTERESIS_CONFIRM", "2")
    hyst = confluence_tiers.cascade(trunc)
    assert hyst["not_topped"] is True, "confirm=2 should debounce the one-bar veto wiggle"


def test_hysteresis_wiring_matches_library(monkeypatch):
    """cascade's confirm=2 veto must equal engine.hysteresis on the SAME per-day stream the
    cascade derives (OB / bear-cross / macd-bear on the daily-mapped 3D legs) — pins the
    wiring, not just one outcome."""
    from engine.hysteresis import hysteretic_not_topped
    from engine.confluence_tiers import (_tf_bars, _stoch_rsi_kd, _rsi_macd, _to_daily, OB,
                                         MIN_HISTORY)
    for seed, cut in ((0, 20), (3, 26), (5, 0)):
        trunc = _synthetic_close(seed=seed)
        trunc = trunc.iloc[: len(trunc) - cut]
        assert len(trunc) >= MIN_HISTORY
        di = trunc.index
        ss3, sk3 = _tf_bars(trunc, 3)
        k3, d3 = _stoch_rsi_kd(ss3)
        m3, s3 = _rsi_macd(ss3)
        k3_d, d3_d = _to_daily(k3, sk3, di), _to_daily(d3, sk3, di)
        m3_d, s3_d = _to_daily(m3, sk3, di), _to_daily(s3, sk3, di)
        nt_raw = ~((k3_d >= OB) | (d3_d >= OB) | (k3_d < d3_d) | (m3_d < s3_d))
        expect = bool(hysteretic_not_topped(nt_raw, confirm=2).iloc[-1])
        monkeypatch.setenv("VETO_HYSTERESIS_CONFIRM", "2")
        got = confluence_tiers.cascade(trunc)["not_topped"]
        monkeypatch.delenv("VETO_HYSTERESIS_CONFIRM", raising=False)
        assert got == expect, f"seed={seed} cut={cut}: wiring diverges from the library"
