"""tests/test_tech_catalog.py — Smoke tests for engine.tech_catalog.

Asserts:
- Import succeeds and TECH_SIGNALS is a non-empty dict.
- No duplicate signal IDs.
- Every descriptor has the required keys.
- Every descriptor's 'fn' is callable.
- list_signals(), get_signal(), signal_families(), compute() all function correctly.
- Every non-cross-sectional signal's fn returns a pd.Series on a sample OHLCV frame.
- Cross-sectional (fundamental_valuation family) signals are exercised separately
  via the fund_frame=None / empty-frame degradation path.
- new_golden_star is registered and fires correctly (age <= 1 day).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with n rows and a DatetimeIndex."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, size=n))
    high = close * (1.0 + rng.uniform(0.0, 0.02, size=n))
    low = close * (1.0 - rng.uniform(0.0, 0.02, size=n))
    open_ = close * (1.0 + rng.normal(0.0, 0.005, size=n))
    volume = rng.uniform(1_000_000, 50_000_000, size=n)
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def test_import():
    """Catalog imports without error."""
    import engine.tech_catalog as tc  # noqa: F401


def test_tech_signals_populated():
    """TECH_SIGNALS is a non-empty dict."""
    from engine.tech_catalog import TECH_SIGNALS
    assert isinstance(TECH_SIGNALS, dict), "TECH_SIGNALS must be a dict"
    assert len(TECH_SIGNALS) > 0, "TECH_SIGNALS must have at least one entry"


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}


def test_no_duplicate_ids():
    """Signal IDs are unique across the catalog."""
    from engine.tech_catalog import TECH_SIGNALS
    ids = list(TECH_SIGNALS.keys())
    assert len(ids) == len(set(ids)), f"Duplicate signal IDs found: {[x for x in ids if ids.count(x) > 1]}"


def test_required_keys():
    """Every descriptor has the required keys."""
    from engine.tech_catalog import TECH_SIGNALS
    for sid, desc in TECH_SIGNALS.items():
        missing = REQUIRED_KEYS - set(desc.keys())
        assert not missing, f"Signal '{sid}' is missing required keys: {missing}"


def test_fns_callable():
    """Every registered fn is callable."""
    from engine.tech_catalog import TECH_SIGNALS
    for sid, desc in TECH_SIGNALS.items():
        assert callable(desc["fn"]), f"Signal '{sid}' fn is not callable"


def test_direction_values():
    """Direction is one of {-1, 0, +1}."""
    from engine.tech_catalog import TECH_SIGNALS
    valid = {-1, 0, 1}
    for sid, desc in TECH_SIGNALS.items():
        assert desc["direction"] in valid, f"Signal '{sid}' has invalid direction {desc['direction']!r}"


def test_kind_values():
    """Kind is one of 'event', 'state'."""
    from engine.tech_catalog import TECH_SIGNALS
    valid = {"event", "state"}
    for sid, desc in TECH_SIGNALS.items():
        assert desc["kind"] in valid, f"Signal '{sid}' has invalid kind {desc['kind']!r}"


def test_display_bilingual():
    """Every display dict has 'en' and 'zh' keys."""
    from engine.tech_catalog import TECH_SIGNALS
    for sid, desc in TECH_SIGNALS.items():
        disp = desc.get("display", {})
        assert "en" in disp, f"Signal '{sid}' display missing 'en'"
        assert "zh" in disp, f"Signal '{sid}' display missing 'zh'"


# ---------------------------------------------------------------------------
# API: list_signals, get_signal, signal_families
# ---------------------------------------------------------------------------

def test_list_signals_all():
    """list_signals() returns descriptors with a 'signal_id' key."""
    from engine.tech_catalog import list_signals, TECH_SIGNALS
    result = list_signals()
    assert len(result) == len(TECH_SIGNALS)
    for entry in result:
        assert "signal_id" in entry
        assert entry["signal_id"] in TECH_SIGNALS


def test_list_signals_by_family():
    """list_signals(family=...) filters correctly."""
    from engine.tech_catalog import list_signals, signal_families
    families = signal_families()
    assert len(families) > 0
    for fam in families:
        subset = list_signals(family=fam)
        assert all(d["family"] == fam for d in subset), f"Family filter broken for '{fam}'"


def test_get_signal_known():
    """get_signal() returns the descriptor with signal_id key."""
    from engine.tech_catalog import get_signal, TECH_SIGNALS
    sid = next(iter(TECH_SIGNALS))
    desc = get_signal(sid)
    assert desc["signal_id"] == sid


def test_get_signal_unknown():
    """get_signal() raises KeyError for unknown ID."""
    from engine.tech_catalog import get_signal
    with pytest.raises(KeyError):
        get_signal("__nonexistent_signal_xyz__")


def test_signal_families_sorted():
    """signal_families() returns a sorted list of strings."""
    from engine.tech_catalog import signal_families
    fams = signal_families()
    assert fams == sorted(fams)
    assert all(isinstance(f, str) for f in fams)


# ---------------------------------------------------------------------------
# Compute: per-family smoke tests
# ---------------------------------------------------------------------------

_SAMPLE_DF = _make_ohlcv(n=300)

# Families that require only a single-ticker OHLCV DataFrame
_OHLCV_FAMILIES = {
    "ma_crosses",
    "ma_price",
    "pivots",
    "rsi_bands",
    "formations",
    "trend",
    "performance",
    "tech_stars",
}

# fundamental_valuation signals return constant NaN series when no data is present
# (degradation path). We test them separately.
_FUNDAMENTAL_FAMILY = "fundamental_valuation"


def test_compute_ohlcv_families():
    """compute(id, df) returns a pd.Series for every non-fundamental signal."""
    from engine.tech_catalog import list_signals, compute
    df = _SAMPLE_DF.copy()
    errors = []
    for desc in list_signals():
        if desc["family"] == _FUNDAMENTAL_FAMILY:
            continue
        sid = desc["signal_id"]
        try:
            result = compute(sid, df)
            assert isinstance(result, pd.Series), f"Signal '{sid}' did not return pd.Series"
            assert len(result) == len(df), f"Signal '{sid}' returned wrong length series"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sid}: {exc}")
    if errors:
        pytest.fail("compute() failed for {} signal(s):\n{}".format(len(errors), "\n".join(errors)))


def test_compute_fundamental_family_degrades():
    """fundamental_valuation signals degrade gracefully (return Series of NaN) when no fund data."""
    from engine.tech_catalog import list_signals, compute
    df = _SAMPLE_DF.copy()
    # fundamental signals infer ticker from df.attrs or df.index.name;
    # with neither set they return NaN everywhere — acceptable degradation.
    for desc in list_signals(family=_FUNDAMENTAL_FAMILY):
        sid = desc["signal_id"]
        result = compute(sid, df)
        assert isinstance(result, pd.Series), f"Signal '{sid}' did not return pd.Series"
        assert len(result) == len(df), f"Signal '{sid}' returned wrong length series"
        # values should be either NaN (no data) or float
        assert result.dtype in (float, np.float64), f"Signal '{sid}' returned unexpected dtype {result.dtype}"


# ---------------------------------------------------------------------------
# is_screener_firing: raw-score / direction-0 states excluded from firing screen
# ---------------------------------------------------------------------------

def test_is_screener_firing_excludes_raw_score_states():
    """Continuous raw-score / direction-0 states are NOT screener-firing.

    They are non-zero for ~the whole universe, so a "who's firing now" list over
    them would list every ticker.  valuation_pctile is the key case: its
    direction is +1 (would pass kind/direction inference) but it is a 0–1 raw
    score, so it needs the explicit screener_firing=False flag.
    """
    from engine.tech_catalog import TECH_SIGNALS, get_signal, is_screener_firing
    for sid in ("valuation_pctile", "insider_power_state", "return_1d"):
        if sid in TECH_SIGNALS:
            assert is_screener_firing(get_signal(sid)) is False, f"{sid} should be excluded"


def test_is_screener_firing_includes_events_and_directional_states():
    """Events and directional (dir!=0) thresholded states ARE screener-firing."""
    from engine.tech_catalog import TECH_SIGNALS, get_signal, is_screener_firing
    for sid in ("insider_buy", "undervalued_state", "trend_rising_short", "golden_star_st_7_35"):
        if sid in TECH_SIGNALS:
            assert is_screener_firing(get_signal(sid)) is True, f"{sid} should be firing-eligible"


def test_is_screener_firing_inference_and_override():
    """Absent flag → inferred from kind/direction; explicit flag wins."""
    from engine.tech_catalog import is_screener_firing
    # inference: event fires, direction-0 state does not, directional state does
    assert is_screener_firing({"kind": "event", "direction": 0}) is True
    assert is_screener_firing({"kind": "state", "direction": 0}) is False
    assert is_screener_firing({"kind": "state", "direction": -1}) is True
    # explicit flag overrides inference in both directions
    assert is_screener_firing({"kind": "state", "direction": +1, "screener_firing": False}) is False
    assert is_screener_firing({"kind": "state", "direction": 0, "screener_firing": True}) is True


# ---------------------------------------------------------------------------
# tech_stars specific: all six pre-registered star pairs present
# ---------------------------------------------------------------------------

def test_tech_stars_registered():
    """All six pre-registered Golden/Death Star pairs are in the catalog."""
    from engine.tech_catalog import TECH_SIGNALS
    expected_ids = [
        "golden_star_st_7_35",
        "golden_star_st_21_100",
        "golden_star_lt_50_200",
        "death_star_st_7_35",
        "death_star_st_21_100",
        "death_star_lt_50_200",
    ]
    missing = [sid for sid in expected_ids if sid not in TECH_SIGNALS]
    assert not missing, f"Missing tech_stars signal IDs: {missing}"


def test_new_golden_star_registered():
    """new_golden_star is present and fires on the fire bar and bar+1."""
    from engine.tech_catalog import TECH_SIGNALS, compute
    assert "new_golden_star" in TECH_SIGNALS, "new_golden_star not registered"

    df = _SAMPLE_DF.copy()
    result = compute("new_golden_star", df)
    assert isinstance(result, pd.Series)
    assert len(result) == len(df)

    # Verify semantics: wherever the underlying golden_star_st_7_35 fires,
    # new_golden_star should fire on that bar and the next bar.
    from engine.tech_catalog import compute as _compute
    base = _compute("golden_star_st_7_35", df)
    fire_positions = base[base == 1.0].index
    for fd in fire_positions:
        assert result.loc[fd] == 1.0, f"new_golden_star should be 1.0 on fire date {fd}"
        # check next bar if it exists
        loc_int = df.index.get_loc(fd)
        if loc_int + 1 < len(df):
            next_date = df.index[loc_int + 1]
            assert result.loc[next_date] == 1.0, (
                f"new_golden_star should be 1.0 on bar after fire date {fd} (got 0)"
            )


# ---------------------------------------------------------------------------
# compute API: dispatcher respects overrides
# ---------------------------------------------------------------------------

def test_compute_override_params():
    """compute() passes keyword overrides to the signal fn."""
    from engine.tech_catalog import compute
    df = _SAMPLE_DF.copy()
    # rsi14_oversold with fixed bands — override band_mode
    result_dyn = compute("rsi14_oversold", df)
    result_fixed = compute("rsi14_oversold", df, band_mode="fixed")
    assert isinstance(result_dyn, pd.Series)
    assert isinstance(result_fixed, pd.Series)
    # Fixed and dynamic results need not be identical — just both valid Series
    assert len(result_dyn) == len(df)
    assert len(result_fixed) == len(df)
