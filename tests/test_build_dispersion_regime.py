"""tests/test_build_dispersion_regime.py — L3 dispersion regime builder tests.

Tests
-----
1. degraded_path_on_none  — when dispersion.assess() returns None (sparse universe),
   build() writes a valid degraded JSON with state=null and gross_mult_live=1.0.
   Never crashes.

2. field_name_parity       — on a healthy assess() return, the emitted JSON contains
   every field name from assess() output verbatim (state, dispersion_pctile, avg_corr,
   shadow_gross_mult, gross_mult, passport) plus the spec-mandated additions
   (as_of, gross_mult_live, history).

3. passport_carry_through  — assess()'s full passport block (basis, verdict, validation,
   note) is carried through verbatim to the emitted JSON.

4. gross_mult_live_always_1 — gross_mult_live is 1.0 regardless of assess()'s
   gross_mult value (hard constraint §5 / §10).

5. history_maintenance      — calling build() twice populates the history list and
   does not grow beyond _HISTORY_LEN entries.

6. degraded_path_no_crash_on_empty_closes — the builder returns a degraded dict and
   does not raise when no close caches exist.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pandas as pd
import numpy as np
import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_dispersion_regime import build, _HISTORY_LEN
from engine import dispersion


# ---------------------------------------------------------------------------
#  Synthetic assess() return fixtures
# ---------------------------------------------------------------------------

def _fake_assess_result(state: str = "lean_in") -> dict:
    """A synthetic return matching the real assess() output schema."""
    shadow = {"lean_in": 1.20, "neutral": 1.0, "lean_out": 0.75}[state]
    en_lbl = {"lean_in": "Selection pays — high dispersion",
               "neutral": "Mixed selection backdrop",
               "lean_out": "Macro tape — selection muted"}[state]
    zh_lbl = {"lean_in": "选股有效 — 高离散度",
               "neutral": "选股环境中性",
               "lean_out": "宏观主导 — 选股弱化"}[state]
    return {
        "dispersion_pct_pts": 1.23,
        "dispersion_pctile": 0.72,
        "avg_corr": 0.18,
        "state": state,
        "gross_mult": 1.0,          # always 1.0 in assess() due to _LIVE_CLAMP
        "shadow_gross_mult": shadow,
        "passport": {
            "basis": "prior",
            "verdict": "display-only per US_BOARD_MEASUREMENT",
            "validation": {
                "artifact": "research/US_BOARD_MEASUREMENT.md#study-3",
                "n": None,
                "survives": False,
            },
            "note": "hand-picked terciles, no measured edge on this universe; "
                    "shadow_gross_mult would gross UP into high-VIX stress — clamped "
                    "to 1.0 until a survivorship-clean selection-IR edge is measured",
        },
        "label": en_lbl,
        "label_zh": zh_lbl,
    }


# ---------------------------------------------------------------------------
#  Test 1: degraded path when assess() returns None
# ---------------------------------------------------------------------------

def test_degraded_path_on_none(tmp_path):
    """assess() returning None must produce a valid degraded JSON, never crash."""
    with (
        mock.patch("scripts.build_dispersion_regime._load_closes",
                   return_value=pd.DataFrame()),
        mock.patch("lib.config.data_dir", return_value=tmp_path),
    ):
        (tmp_path / "dispersion").mkdir(parents=True, exist_ok=True)
        result = build()

    assert result["state"] is None, "degraded state must be null"
    assert result["gross_mult_live"] == 1.0
    assert "passport" in result
    out_path = tmp_path / "dispersion" / "regime.json"
    assert out_path.exists()
    parsed = json.loads(out_path.read_text())
    assert parsed["state"] is None
    assert parsed["gross_mult_live"] == 1.0


# ---------------------------------------------------------------------------
#  Test 2: field-name parity with assess() output
# ---------------------------------------------------------------------------

def test_field_name_parity(tmp_path):
    """Emitted JSON must contain every key from assess() output verbatim."""
    fake = _fake_assess_result("lean_in")
    # Fields that assess() returns (the contract we must mirror)
    assess_keys = {"state", "dispersion_pctile", "avg_corr",
                   "shadow_gross_mult", "gross_mult", "passport"}
    # Spec-mandated additions
    spec_extra_keys = {"as_of", "gross_mult_live", "history"}

    with (
        mock.patch("scripts.build_dispersion_regime._load_closes",
                   return_value=pd.DataFrame({"A": [1.0, 1.01]})),
        mock.patch("engine.dispersion.assess", return_value=fake),
        mock.patch("lib.config.data_dir", return_value=tmp_path),
    ):
        (tmp_path / "dispersion").mkdir(parents=True, exist_ok=True)
        result = build()

    emitted_keys = set(result.keys())
    # All assess() keys present (note: gross_mult is represented as gross_mult_live=1.0)
    for key in (assess_keys - {"gross_mult"}):  # gross_mult -> gross_mult_live in spec
        assert key in emitted_keys, f"missing assess() key: {key}"
    for key in spec_extra_keys:
        assert key in emitted_keys, f"missing spec-mandated key: {key}"
    # gross_mult_live must be present (renamed per spec §5)
    assert "gross_mult_live" in emitted_keys


# ---------------------------------------------------------------------------
#  Test 3: passport carry-through
# ---------------------------------------------------------------------------

def test_passport_carry_through(tmp_path):
    """assess()'s full passport block must be carried through verbatim."""
    fake = _fake_assess_result("neutral")
    with (
        mock.patch("scripts.build_dispersion_regime._load_closes",
                   return_value=pd.DataFrame({"A": [1.0, 1.01]})),
        mock.patch("engine.dispersion.assess", return_value=fake),
        mock.patch("lib.config.data_dir", return_value=tmp_path),
    ):
        (tmp_path / "dispersion").mkdir(parents=True, exist_ok=True)
        result = build()

    pp = result.get("passport", {})
    assert pp.get("basis") == "prior"
    assert pp.get("verdict") == "display-only per US_BOARD_MEASUREMENT"
    assert "validation" in pp
    assert pp["validation"].get("survives") is False


# ---------------------------------------------------------------------------
#  Test 4: gross_mult_live always 1.0 (hard constraint §5 / §10)
# ---------------------------------------------------------------------------

def test_gross_mult_live_always_1(tmp_path):
    """gross_mult_live must be 1.0 regardless of any assess() output."""
    for state in ("lean_in", "neutral", "lean_out"):
        fake = _fake_assess_result(state)
        # Even if assess() hypothetically returned a non-1.0 gross_mult, the
        # builder must clamp gross_mult_live to 1.0.
        fake["gross_mult"] = 99.0  # tamper — must be ignored
        with (
            mock.patch("scripts.build_dispersion_regime._load_closes",
                       return_value=pd.DataFrame({"A": [1.0, 1.01]})),
            mock.patch("engine.dispersion.assess", return_value=fake),
            mock.patch("lib.config.data_dir", return_value=tmp_path),
        ):
            (tmp_path / "dispersion").mkdir(parents=True, exist_ok=True)
            result = build()

        assert result["gross_mult_live"] == 1.0, (
            f"gross_mult_live must always be 1.0 (state={state})"
        )


# ---------------------------------------------------------------------------
#  Test 5: history maintenance
# ---------------------------------------------------------------------------

def test_history_maintenance(tmp_path):
    """Calling build() multiple times populates history without growing beyond limit."""
    (tmp_path / "dispersion").mkdir(parents=True, exist_ok=True)
    fake = _fake_assess_result("lean_in")

    call_count = 0
    def _fake_assess(_returns, **_kw):
        nonlocal call_count
        call_count += 1
        return fake

    n_calls = 5
    with (
        mock.patch("scripts.build_dispersion_regime._load_closes",
                   return_value=pd.DataFrame({"A": [1.0, 1.01]})),
        mock.patch("engine.dispersion.assess", side_effect=_fake_assess),
        mock.patch("lib.config.data_dir", return_value=tmp_path),
    ):
        for _ in range(n_calls):
            result = build()

    # history should have at most 1 entry (all calls have same as_of = today)
    assert isinstance(result["history"], list)
    assert len(result["history"]) >= 1
    assert len(result["history"]) <= _HISTORY_LEN

    # Load from disk and verify history is there
    parsed = json.loads((tmp_path / "dispersion" / "regime.json").read_text())
    assert "history" in parsed
    assert len(parsed["history"]) <= _HISTORY_LEN


# ---------------------------------------------------------------------------
#  Test 6: degraded path with no crash on empty closes
# ---------------------------------------------------------------------------

def test_no_crash_empty_closes(tmp_path):
    """Build must not raise even with empty closes panel (graceful degradation)."""
    (tmp_path / "dispersion").mkdir(parents=True, exist_ok=True)
    with mock.patch("lib.config.data_dir", return_value=tmp_path):
        # _load_closes will find no parquet files in tmp_path — returns empty
        result = build()

    assert result is not None
    assert result["gross_mult_live"] == 1.0
    out = json.loads((tmp_path / "dispersion" / "regime.json").read_text())
    assert out["gross_mult_live"] == 1.0


# ---------------------------------------------------------------------------
#  Eigen-concentration tests (DISP-EIGEN-1 fields)
# ---------------------------------------------------------------------------

def _make_returns(n_days: int, n_names: int, seed: int = 42,
                  factor_loading: float | None = None) -> pd.DataFrame:
    """Synthetic return panel. factor_loading=None => iid; else one-factor."""
    rng = np.random.default_rng(seed)
    if factor_loading is None:
        data = rng.normal(0, 0.01, size=(n_days, n_names))
    else:
        common = rng.normal(0, 0.01, size=(n_days, 1))
        idio = rng.normal(0, 0.001, size=(n_days, n_names))
        data = factor_loading * common + idio
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    return pd.DataFrame(data, index=dates, columns=[f"N{i}" for i in range(n_names)])


def test_eigen_iid_panel():
    """300d x 30n iid noise: effective_universe_bets_pr well above 5, dominant share low."""
    returns = _make_returns(300, 30)
    result = dispersion.assess(returns)
    assert result is not None
    eigen = result.get("eigen")
    assert eigen is not None, "eigen block should not be None for adequate panel"
    assert eigen["effective_universe_bets_pr"] > 5, (
        f"iid panel should have ENB > 5, got {eigen['effective_universe_bets_pr']}"
    )
    # For iid data dominant share should be low (well under 0.5)
    assert eigen["dominant_equity_pc_share"] < 0.5, (
        f"iid dominant share should be low, got {eigen['dominant_equity_pc_share']}"
    )


def test_eigen_one_factor_panel():
    """One-factor panel: dominant_equity_pc_share > 0.8, ENB < 2."""
    returns = _make_returns(300, 30, factor_loading=1.0)
    result = dispersion.assess(returns)
    assert result is not None
    eigen = result.get("eigen")
    assert eigen is not None
    assert eigen["dominant_equity_pc_share"] > 0.8, (
        f"one-factor panel should have dominant share > 0.8, got {eigen['dominant_equity_pc_share']}"
    )
    assert eigen["effective_universe_bets_pr"] < 2.0, (
        f"one-factor panel should have ENB < 2, got {eigen['effective_universe_bets_pr']}"
    )


def test_eigen_none_on_tiny_panel():
    """Eigen block is None when panel has fewer than 20 names."""
    returns = _make_returns(300, 10)  # 10 names < _EIGEN_MIN_NAMES=20
    result = dispersion.assess(returns)
    # assess() itself may return None due to r.shape[1] < 20 guard
    if result is None:
        return  # assess() gated out — acceptable, eigen=None by construction
    eigen = result.get("eigen")
    assert eigen is None, (
        f"eigen should be None for panel with only 10 names, got {eigen}"
    )


def test_eigen_excluded_from_history_rows(tmp_path):
    """eigen block must NOT appear in history list entries."""
    (tmp_path / "dispersion").mkdir(parents=True, exist_ok=True)
    fake = _fake_assess_result("lean_in")
    # Inject a non-None eigen block into the fake assess result
    fake["eigen"] = {
        "basis": "trailing_252d_fixed",
        "n_names_used": 30,
        "n_days_used": 252,
        "dominant_equity_pc_share": 0.2345,
        "effective_universe_bets_pr": 12.34,
        "idio_dispersion_share": 0.6789,
        "sector_pc_loadings": None,
        "note": "test",
        "display_only": True,
    }

    with (
        mock.patch("scripts.build_dispersion_regime._load_closes",
                   return_value=pd.DataFrame({"A": [1.0, 1.01]})),
        mock.patch("engine.dispersion.assess", return_value=fake),
        mock.patch("lib.config.data_dir", return_value=tmp_path),
    ):
        result = build()

    # eigen present at top level
    assert "eigen" in result, "eigen key should be present at top level of output"
    # eigen absent from every history entry
    for entry in result.get("history", []):
        assert "eigen" not in entry, (
            f"eigen key should NOT appear in history entries; found in: {entry}"
        )

    # Verify on disk too
    parsed = json.loads((tmp_path / "dispersion" / "regime.json").read_text())
    assert "eigen" in parsed
    for entry in parsed.get("history", []):
        assert "eigen" not in entry, "eigen key must not be in on-disk history entries"


def test_eigen_json_serializable():
    """The full assess() output including eigen block must be JSON-serializable."""
    returns = _make_returns(300, 30)
    result = dispersion.assess(returns)
    assert result is not None
    # Must not raise
    serialized = json.dumps(result, default=str)
    parsed = json.loads(serialized)
    assert "eigen" in parsed


def test_eigen_block_shape():
    """Eigen block, when present, must have all required keys with correct basis."""
    returns = _make_returns(300, 30)
    result = dispersion.assess(returns)
    assert result is not None
    eigen = result.get("eigen")
    assert eigen is not None
    required_keys = {
        "basis", "n_names_used", "n_days_used",
        "dominant_equity_pc_share", "effective_universe_bets_pr",
        "idio_dispersion_share", "sector_pc_loadings", "note", "display_only",
    }
    for k in required_keys:
        assert k in eigen, f"eigen block missing key: {k}"
    assert eigen["basis"] == "trailing_252d_fixed"
    assert eigen["display_only"] is True
    assert eigen["sector_pc_loadings"] is None


def test_compute_eigen_block_direct_15_name_guard():
    """_compute_eigen_block directly with a 15-name panel exercises its own <20 guard.

    test_eigen_none_on_tiny_panel is partly vacuous: assess() early-returns None at
    r.shape[1] < 20, so _compute_eigen_block never sees the panel.  This test calls
    _compute_eigen_block directly to cover its own minimum-names path.
    """
    returns = _make_returns(300, 15)
    result = dispersion._compute_eigen_block(returns)
    assert result is None, (
        f"_compute_eigen_block should return None for 15-name panel, got {result}"
    )


def test_idio_dispersion_share_discriminates_factor_structure():
    """idio_dispersion_share must be lower for a one-factor panel than for iid.

    This guards against the near-degeneracy bug (whitened returns making the ratio
    near-constant ~0.92-0.97 regardless of factor structure).  After the fix
    (variance-share on demeaned returns), a strongly factor-driven panel has much
    lower idio_dispersion_share than iid noise.
    """
    iid_returns = _make_returns(300, 30, seed=42, factor_loading=None)
    one_factor_returns = _make_returns(300, 30, seed=42, factor_loading=1.0)

    iid_result = dispersion.assess(iid_returns)
    one_factor_result = dispersion.assess(one_factor_returns)

    assert iid_result is not None
    assert one_factor_result is not None

    iid_eigen = iid_result.get("eigen")
    one_factor_eigen = one_factor_result.get("eigen")

    assert iid_eigen is not None, "eigen block should not be None for 300d x 30n iid panel"
    assert one_factor_eigen is not None, "eigen block should not be None for 300d x 30n one-factor panel"

    iid_idio = iid_eigen["idio_dispersion_share"]
    one_factor_idio = one_factor_eigen["idio_dispersion_share"]

    assert iid_idio is not None, "idio_dispersion_share should not be None for valid iid panel"
    assert one_factor_idio is not None, "idio_dispersion_share should not be None for valid one-factor panel"

    # One-factor panel should have substantially lower idio share than iid panel.
    # With the corrected variance-share definition: one-factor concentrates variance
    # in the common component, leaving little residual variance → low idio share.
    # iid panel: no common factor → all variance is residual → high idio share.
    assert one_factor_idio < iid_idio, (
        f"idio_dispersion_share should be lower for one-factor panel ({one_factor_idio}) "
        f"than for iid panel ({iid_idio}); near-equal values indicate near-degeneracy bug"
    )
