"""engine.theme_revisions — T4 revision-breadth roll-up. Verifies the per-theme breadth
math, the thin-coverage guard, level-state banding, the PIT broadening derivative,
and the W1c adaptive-lookback + drift-proxy (P1-B). DISPLAY-ONLY contract.
"""
from __future__ import annotations

import pandas as pd

from engine import theme_revisions as tr


def _latest_frame():
    # memory_storage members: 3 strongly-positive, 1 thin (ignored), 1 absent
    return pd.DataFrame(
        {"net_up_30d": [10.0, 8.0, 6.0, 1.0],
         "breadth": [0.9, 0.8, 0.7, 0.5],
         "est_chg_30d": [5.0, 4.0, 3.0, 1.0],
         "est_chg_90d": [20.0, 18.0, 15.0, 2.0],
         "n_analysts": [12.0, 10.0, 8.0, 2.0],          # last one < MIN_ANALYSTS -> dropped
         "asof": pd.Timestamp("2026-06-16")},
        index=["MU", "WDC", "STX", "SNDK"],
    )


def _themes():
    return {"themes": {"memory_storage": {"name": "Memory", "tickers": ["MU", "WDC", "STX", "SNDK", "NTAP"]}}}


def _patch(monkeypatch, latest, hist=None, themes=None):
    monkeypatch.setattr(tr, "_latest", lambda: latest)
    monkeypatch.setattr(tr, "_history", lambda: hist)
    monkeypatch.setattr(tr.config, "load", lambda: themes or _themes())


def test_breadth_drops_thin_coverage(monkeypatch):
    _patch(monkeypatch, _latest_frame())
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    # mean breadth over the 3 covered names (0.9,0.8,0.7) = 0.8; the n=2 name is excluded
    assert t["breadth"] == 0.8
    assert t["n_covered"] == 3 and t["n_members"] == 5
    assert t["coverage"] == round(3 / 5, 2)
    assert t["level_state"] == "POSITIVE"
    assert t["est_drift_90d"] == 18.0          # median of 20,18,15


def test_flat_low_level(monkeypatch):
    df = _latest_frame()
    df["breadth"] = [0.05, -0.05, 0.02, 0.5]   # near zero -> FLAT_LOW
    _patch(monkeypatch, df)
    out = tr.compute_theme_revisions(write_ledger=False)
    assert out["themes"]["memory_storage"]["level_state"] == "FLAT_LOW"


def test_insufficient_history_when_no_archive_and_proxy_absent(monkeypatch):
    """No archive AND no est_chg_30d/est_chg_90d columns → INSUFFICIENT_HISTORY."""
    latest = pd.DataFrame(
        {"net_up_30d": [10.0, 8.0, 6.0],
         "breadth": [0.9, 0.8, 0.7],
         "n_analysts": [12.0, 10.0, 8.0],
         "asof": pd.Timestamp("2026-06-16")},
        index=["MU", "WDC", "STX"],
    )
    _patch(monkeypatch, latest, hist=None)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["broadening_state"] == "INSUFFICIENT_HISTORY"
    assert t["breadth_accel"] is None
    assert not t.get("broadening_proxy")


def test_broadening_rising_with_spanning_history(monkeypatch):
    """Legacy behaviour: ≥21d prior snapshot → real accel, no proxy flag."""
    latest = _latest_frame()
    # history: a snapshot ~40d earlier with LOWER breadth -> breadth rising -> RISING
    hist = pd.DataFrame({
        "ticker": ["MU", "WDC", "STX", "MU", "WDC", "STX"],
        "breadth": [0.2, 0.1, 0.1, 0.9, 0.8, 0.7],
        "n_analysts": [12.0, 10.0, 8.0, 12.0, 10.0, 8.0],
        "asof": [pd.Timestamp("2026-05-05")] * 3 + [pd.Timestamp("2026-06-16")] * 3,
    })
    _patch(monkeypatch, latest, hist=hist)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["broadening_state"] == "RISING"
    assert t["breadth_accel"] is not None and t["breadth_accel"] > 0
    assert t.get("basis_days") is not None and t["basis_days"] >= tr.ACCEL_LOOKBACK_DAYS
    assert not t.get("broadening_proxy")  # real read, no proxy


def test_returns_none_without_data(monkeypatch):
    monkeypatch.setattr(tr, "_latest", lambda: None)
    assert tr.compute_theme_revisions(write_ledger=False) is None


# --- W1c (P1-B) new tests ---------------------------------------------------

def test_adaptive_lookback_10_to_20d_real_accel(monkeypatch):
    """(a) 10-20d-old snapshot → real accel computed with basis_days set, no proxy flag."""
    latest = _latest_frame()
    # prior snapshot exactly 14 days back — between MIN_ACCEL_DAYS(10) and ACCEL_LOOKBACK_DAYS(21)
    prior_date = pd.Timestamp("2026-06-16") - pd.Timedelta(days=14)
    hist = pd.DataFrame({
        "ticker": ["MU", "WDC", "STX", "MU", "WDC", "STX"],
        "breadth": [0.3, 0.2, 0.2, 0.9, 0.8, 0.7],       # prior lower → accel positive
        "n_analysts": [12.0, 10.0, 8.0, 12.0, 10.0, 8.0],
        "asof": [prior_date] * 3 + [pd.Timestamp("2026-06-16")] * 3,
    })
    _patch(monkeypatch, latest, hist=hist)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["broadening_state"] == "RISING"
    assert t["breadth_accel"] is not None and t["breadth_accel"] > 0
    # basis_days reflects the actual 14-day window (< 21d preference)
    assert t.get("basis_days") == 14
    assert not t.get("broadening_proxy")   # real read, no proxy


def test_proxy_state_when_no_history(monkeypatch):
    """(b) No archive → drift proxy fires with proxy:True and basis:'drift_30v90'.

    est_chg_30d (5,4,3) > est_chg_90d/3 (20/3,18/3,15/3) ≈ (6.7,6.0,5.0) → diff negative
    so state = ROLLING (30d drift below the 90d pace → decelerating).
    We use data where 30d > 90d/3 to get RISING.
    """
    # override latest so est_chg_30d is well above est_chg_90d/3 → RISING proxy
    latest = pd.DataFrame(
        {"net_up_30d": [10.0, 8.0, 6.0, 1.0],
         "breadth": [0.9, 0.8, 0.7, 0.5],
         "est_chg_30d": [12.0, 10.0, 9.0, 1.0],   # 30d >> 90d/3 (≈6.7/6/5) → accelerating
         "est_chg_90d": [20.0, 18.0, 15.0, 2.0],
         "n_analysts": [12.0, 10.0, 8.0, 2.0],
         "asof": pd.Timestamp("2026-06-16")},
        index=["MU", "WDC", "STX", "SNDK"],
    )
    _patch(monkeypatch, latest, hist=None)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    # the SCORED/staged field stays INSUFFICIENT_HISTORY (the cascade drops the proxy
    # flag at its boundary and foresight_score's acceleration axis would score a
    # level-derived proxy identically to a real PIT accel) — the directional read
    # lives in its own broadening_proxy_state field
    assert t["broadening_state"] == "INSUFFICIENT_HISTORY"
    assert t.get("broadening_proxy_state") == "RISING"
    assert t.get("broadening_proxy") is True
    assert t.get("basis") == "drift_30v90"
    assert t["breadth_accel"] is None       # no PIT derivative available


def test_proxy_all_nan_est_chg_degrades_to_insufficient_history(monkeypatch):
    """All-NaN est_chg inputs must NOT produce a confident FLAT_LOW from no data, and
    must not leak a NaN proxy_drift_diff into the (strict-JSON) payload."""
    latest = pd.DataFrame(
        {"net_up_30d": [10.0, 8.0, 6.0],
         "breadth": [0.9, 0.8, 0.7],
         "est_chg_30d": [float("nan")] * 3,
         "est_chg_90d": [float("nan")] * 3,
         "n_analysts": [12.0, 10.0, 8.0],
         "asof": pd.Timestamp("2026-06-16")},
        index=["MU", "WDC", "STX"],
    )
    _patch(monkeypatch, latest, hist=None)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["broadening_state"] == "INSUFFICIENT_HISTORY"
    assert not t.get("broadening_proxy")
    v = t.get("proxy_drift_diff")
    assert v is None or v == v              # never a NaN in the payload


def test_proxy_deadband_maps_small_diff_to_flat_low(monkeypatch):
    """|median 30v90 diff| below PROXY_DEADBAND → FLAT_LOW proxy read, not RISING —
    the sign-only proxy must not be more trigger-happy than the real accel path."""
    latest = pd.DataFrame(
        {"net_up_30d": [10.0, 8.0, 6.0],
         "breadth": [0.9, 0.8, 0.7],
         "est_chg_30d": [5.1, 5.05, 5.2],    # barely above 90d/3 = 5.0
         "est_chg_90d": [15.0, 15.0, 15.0],
         "n_analysts": [12.0, 10.0, 8.0],
         "asof": pd.Timestamp("2026-06-16")},
        index=["MU", "WDC", "STX"],
    )
    _patch(monkeypatch, latest, hist=None)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t.get("broadening_proxy_state") == "FLAT_LOW"


def test_proxy_inputs_absent_gives_insufficient_history(monkeypatch):
    """(c) No archive and no est_chg_30d/est_chg_90d → INSUFFICIENT_HISTORY, no proxy."""
    latest = pd.DataFrame(
        {"net_up_30d": [10.0, 8.0, 6.0],
         "breadth": [0.9, 0.8, 0.7],
         # deliberately omit est_chg_30d and est_chg_90d
         "n_analysts": [12.0, 10.0, 8.0],
         "asof": pd.Timestamp("2026-06-16")},
        index=["MU", "WDC", "STX"],
    )
    _patch(monkeypatch, latest, hist=None)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["broadening_state"] == "INSUFFICIENT_HISTORY"
    assert t["breadth_accel"] is None
    assert not t.get("broadening_proxy")


def test_legacy_21d_history_no_proxy_flag(monkeypatch):
    """(d) ≥21d history → unchanged legacy behaviour: basis_days≥21, no proxy flag."""
    latest = _latest_frame()
    prior_date = pd.Timestamp("2026-06-16") - pd.Timedelta(days=25)
    hist = pd.DataFrame({
        "ticker": ["MU", "WDC", "STX", "MU", "WDC", "STX"],
        "breadth": [0.5, 0.4, 0.4, 0.9, 0.8, 0.7],
        "n_analysts": [12.0, 10.0, 8.0, 12.0, 10.0, 8.0],
        "asof": [prior_date] * 3 + [pd.Timestamp("2026-06-16")] * 3,
    })
    _patch(monkeypatch, latest, hist=hist)
    out = tr.compute_theme_revisions(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["broadening_state"] == "RISING"
    assert t.get("basis_days") is not None and t["basis_days"] >= tr.ACCEL_LOOKBACK_DAYS
    assert not t.get("broadening_proxy")    # no proxy when real window is available
