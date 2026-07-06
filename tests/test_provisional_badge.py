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
    """A real T3 fire (pinned fixture: seed=50 truncated at 2023-11-20 grades T3) carries the
    flag through the cascade, the gate verdict, and BOTH display subsets.

    Date updated from 2023-11-17 to 2023-11-20: the T3 persistence hardening (default N=2,
    CONFLUENCE_T3_PERSIST) requires 2 consecutive completed 2D-bucket T3 conditions. On
    2023-11-17 only ONE bucket had imm2=True; 2023-11-20 is the first day where both the
    2023-11-17 and 2023-11-20 2D buckets are imm2=True, so T3 fires under the new default."""
    c = _synthetic_close(seed=50)
    trunc = c[c.index <= pd.Timestamp("2023-11-20")]
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


# ------------------------------------------ 3. T3 persistence (CONFLUENCE_T3_PERSIST) --

def test_t3_persist_env_parsing(monkeypatch):
    """_t3_persist() must parse the env knob exactly like _veto_confirm(): floor at 1,
    garbage -> default (2), unset -> default (2)."""
    monkeypatch.delenv("CONFLUENCE_T3_PERSIST", raising=False)
    assert confluence_tiers._t3_persist() == 2      # default
    monkeypatch.setenv("CONFLUENCE_T3_PERSIST", "1")
    assert confluence_tiers._t3_persist() == 1      # legacy
    monkeypatch.setenv("CONFLUENCE_T3_PERSIST", "3")
    assert confluence_tiers._t3_persist() == 3      # custom window
    monkeypatch.setenv("CONFLUENCE_T3_PERSIST", "0")
    assert confluence_tiers._t3_persist() == 1      # floor at 1
    monkeypatch.setenv("CONFLUENCE_T3_PERSIST", "junk")
    assert confluence_tiers._t3_persist() == 2      # garbage -> default


def test_t3_single_session_does_not_fire_under_default(monkeypatch):
    """At the default N=2, a T3 condition that holds on only ONE 2D bucket must NOT fire.

    Fixture: seed=50 truncated at 2023-11-17. Under N=1 (legacy) this graded T3; under N=2
    only ONE 2D bucket (2023-11-17) has imm2=True, so T3 is suppressed."""
    monkeypatch.delenv("CONFLUENCE_T3_PERSIST", raising=False)    # default N=2
    c = _synthetic_close(seed=50)
    trunc = c[c.index <= pd.Timestamp("2023-11-17")]
    casc = confluence_tiers.cascade(trunc)
    assert casc["tier"] != "T3", (
        f"single-session T3 must not fire under N=2 default; got tier={casc['tier']}")


def test_t3_two_consecutive_sessions_fire(monkeypatch):
    """Two consecutive 2D buckets both imm2=True must fire T3 at N=2 default.

    Fixture: seed=50 truncated at 2023-11-20. Both 2023-11-17 and 2023-11-20 buckets
    have imm2=True — this is the first date where 2 consecutive completed buckets qualify."""
    monkeypatch.delenv("CONFLUENCE_T3_PERSIST", raising=False)    # default N=2
    c = _synthetic_close(seed=50)
    trunc = c[c.index <= pd.Timestamp("2023-11-20")]
    casc = confluence_tiers.cascade(trunc)
    assert casc["tier"] == "T3", (
        f"two-consecutive-bucket T3 must fire under N=2; got tier={casc['tier']}")
    assert casc["provisional"] is True


def test_t3_persist_1_restores_legacy(monkeypatch):
    """N=1 must restore the legacy single-session behaviour (byte-identical to the pre-change
    outcome for the seed=50 / 2023-11-17 fixture that originally pinned T3)."""
    monkeypatch.setenv("CONFLUENCE_T3_PERSIST", "1")
    c = _synthetic_close(seed=50)
    trunc = c[c.index <= pd.Timestamp("2023-11-17")]
    casc = confluence_tiers.cascade(trunc)
    assert casc["tier"] == "T3", (
        f"N=1 must restore legacy T3 firing at 2023-11-17; got tier={casc['tier']}")
    assert casc["provisional"] is True


def test_t3_persist_de_escalation(monkeypatch):
    """T3 fire count under N=2 is strictly <= fire count under N=1 (DE-ESCALATION invariant)."""
    c = _synthetic_close(seed=50)
    fires_n1, fires_n2 = 0, 0
    for d in c.index:
        trunc = c[c.index <= d]
        monkeypatch.setenv("CONFLUENCE_T3_PERSIST", "1")
        if confluence_tiers.cascade(trunc)["tier"] == "T3":
            fires_n1 += 1
        monkeypatch.setenv("CONFLUENCE_T3_PERSIST", "2")
        if confluence_tiers.cascade(trunc)["tier"] == "T3":
            fires_n2 += 1
    assert fires_n2 <= fires_n1, (
        f"N=2 must fire T3 no more than N=1; got n1={fires_n1} n2={fires_n2}")
    assert fires_n1 > 0, "fixture must produce at least one T3 fire at N=1 (fixture sanity)"
