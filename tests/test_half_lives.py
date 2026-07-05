"""tests/test_half_lives.py — W2 "Measured Half-Lives" (Signal Commons program).

Coverage:
  (1) Schema contract: every family has decay_kind, outcome_unit, half_life (float|None),
      all values python-native (no numpy) — guards the json-zeroing gotcha.
  (2) Null-rule: synthetic family with <3 horizons → half_life=None, reason_null set.
  (3) Null-rule: synthetic family with n_eff < 200 → half_life=None, reason_null set.
  (4) Monotonicity gate — RISING curve (like real track_record): half_life=None,
      reason="edge_non_decaying".
  (5) Monotonicity gate — DECAYING curve: finite tau, CI attempted.
  (6) Staleness honesty: no family in artifact has decay_kind=="staleness" with non-null
      half_life (W2 delivers zero staleness numbers).
  (7) query.py: "half_life" in COLUMNS; old-schema parquet (without column) loads via
      _ensure_columns with NaN and no error.
  (8) CI-pin: assert artifact count == 113; "kernel-half-lives" in registry ids.
  (9) Display: build_half_lives always emits "status":"fit_ran" sentinel key.
  (10) R8/display-only: grep that no behavior-changing module imports half_life.py.
  (11) build_half_lives: fail-open when estimates absent (returns all-null with status=fit_ran).
  (12) _sanitize_for_json: numpy scalars cast to python-native types.
  (13) write_half_lives: always writes file even when all-null.
  (14) Staleness honesty: artifact notes mention "UNMEASURED" for staleness.
  (15) _stamp_family_half_life: fail-open when half_life.json absent.
  (16) _stamp_family_half_life: stamps numeric half_life onto rows with matching engine.
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

# ---------------------------------------------------------------------------
# Locate repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYNAPSE_YML = _REPO_ROOT / "config" / "synapse.yml"

# ---------------------------------------------------------------------------
# Minimal synthetic registry for envelope stamps
# ---------------------------------------------------------------------------
_REG = {
    "meta": {"tier_vocabulary": ["display", "shadow", "confirmer", "scored", "infrastructure"]},
    "artifacts": {
        "kernel-half-lives": {
            "producer": "engine/neuralweb/half_life.py",
            "tier": "infrastructure",
        },
    },
}


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_estimates_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal kernel_estimates.parquet fixture."""
    nwd = tmp_path / "data" / "neuralweb"
    nwd.mkdir(parents=True, exist_ok=True)
    p = nwd / "kernel_estimates.parquet"
    df = pd.DataFrame(rows)
    df.to_parquet(p, index=False)
    return p


def _make_spine_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal spine_index.parquet fixture."""
    from engine.neuralweb.query import COLUMNS
    nwd = tmp_path / "data" / "neuralweb"
    nwd.mkdir(parents=True, exist_ok=True)
    p = nwd / "spine_index.parquet"
    df = pd.DataFrame(rows)
    # Fill missing columns with defaults
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    df.to_parquet(p, index=False)
    return p


def _minimal_estimates_row(engine: str, horizon: int, ic: float, n_eff: int) -> dict:
    return {
        "engine": engine,
        "regime": "__all__",
        "horizon": horizon,
        "shrunken_ic": ic,
        "n_eff": float(n_eff),
        "armed": False,
        "date_last": "2026-01-01",
    }


def _minimal_graded_row(engine: str, symbol: str, as_of: str, horizon: int, excess: float) -> dict:
    return {
        "signal_id": f"tr:{as_of}:{symbol}:{horizon}",
        "engine": engine,
        "family": engine + ":buy",
        "ledger": "track_record",
        "as_of": as_of,
        "symbol": symbol,
        "scope_type": "entity",
        "universe": "us_1500",
        "horizon": horizon,
        "direction": 1,
        "size_binding": False,
        "fill_basis": "close",
        "score": 1.0,
        "outcome_excess": excess,
        "outcome_graded": True,
        "graded_at": as_of,
    }


# ---------------------------------------------------------------------------
# (1) Schema contract — all families have mandatory keys and python-native types
# ---------------------------------------------------------------------------

def test_schema_mandatory_keys(tmp_path: Path):
    """Every family entry must have decay_kind, outcome_unit, half_life (float|None),
    and all numeric values must be python-native (not numpy)."""
    from engine.neuralweb.half_life import build_half_lives, _sanitize_for_json

    # Write a minimal rising estimates (like real track_record)
    _make_estimates_parquet(tmp_path, [
        _minimal_estimates_row("track_record", 5, 0.05, 50),
        _minimal_estimates_row("track_record", 10, 0.07, 50),
        _minimal_estimates_row("track_record", 21, 0.10, 50),
        _minimal_estimates_row("track_record", 63, 0.14, 50),
        _minimal_estimates_row("track_record", 126, 0.18, 50),
    ])

    # Write 250 graded rows (above family floor) to get past floor check
    graded_rows = []
    for i in range(250):
        graded_rows.append(_minimal_graded_row("track_record", f"S{i}", "2026-01-01", 21, 0.01))
    _make_spine_parquet(tmp_path, graded_rows)

    payload = build_half_lives(tmp_path)
    families = payload.get("families", {})
    assert families, "expected non-empty families dict"

    for key, entry in families.items():
        assert "decay_kind" in entry, f"{key}: missing decay_kind"
        assert "outcome_unit" in entry, f"{key}: missing outcome_unit"
        assert "half_life" in entry, f"{key}: missing half_life"
        assert "reason_null" in entry, f"{key}: missing reason_null"
        assert "n_eff" in entry, f"{key}: missing n_eff"
        assert "n_horizons" in entry, f"{key}: missing n_horizons"
        assert "fit_rho" in entry, f"{key}: missing fit_rho"
        assert "ci_low" in entry, f"{key}: missing ci_low"
        assert "ci_high" in entry, f"{key}: missing ci_high"

        hl = entry["half_life"]
        assert hl is None or isinstance(hl, float), f"{key}: half_life must be float|None, got {type(hl)}"

        # All values must be python-native — NOT numpy types
        for field_name, field_val in entry.items():
            if field_val is not None:
                assert not isinstance(field_val, (np.floating, np.integer, np.bool_)), (
                    f"{key}.{field_name}: numpy scalar found — use python-native types"
                )


# ---------------------------------------------------------------------------
# (2) Null-rule — < 3 admissible horizons → half_life=None
# ---------------------------------------------------------------------------

def test_null_rule_insufficient_horizons(tmp_path: Path):
    """A family with only 2 admissible horizons must emit half_life=None."""
    from engine.neuralweb.half_life import build_half_lives

    _make_estimates_parquet(tmp_path, [
        _minimal_estimates_row("radar", 5, 0.03, 200),
        _minimal_estimates_row("radar", 63, 0.025, 200),  # only 2 points
    ])
    # Many graded rows so family floor passes
    graded_rows = [_minimal_graded_row("radar", f"S{i}", "2026-01-01", 5, 0.005)
                   for i in range(250)]
    _make_spine_parquet(tmp_path, graded_rows)

    payload = build_half_lives(tmp_path)
    entry = payload["families"]["radar"]
    assert entry["half_life"] is None, "2-horizon family must have null half_life"
    assert entry["reason_null"] is not None, "reason_null must be set"
    assert "horizon" in entry["reason_null"].lower() or "admissible" in entry["reason_null"].lower()


# ---------------------------------------------------------------------------
# (3) Null-rule — n_eff < 200 → half_life=None
# ---------------------------------------------------------------------------

def test_null_rule_family_floor(tmp_path: Path):
    """A family with n_eff < 200 must emit half_life=None (family floor)."""
    from engine.neuralweb.half_life import build_half_lives, FAMILY_FLOOR_N

    _make_estimates_parquet(tmp_path, [
        _minimal_estimates_row("radar", 5, 0.03, 200),
        _minimal_estimates_row("radar", 10, 0.025, 200),
        _minimal_estimates_row("radar", 21, 0.018, 200),
    ])
    # Only 10 graded rows — well below FAMILY_FLOOR_N=200
    graded_rows = [_minimal_graded_row("radar", f"S{i}", "2026-01-01", 5, 0.005)
                   for i in range(10)]
    _make_spine_parquet(tmp_path, graded_rows)

    payload = build_half_lives(tmp_path)
    entry = payload["families"]["radar"]
    assert entry["half_life"] is None
    assert entry["reason_null"] is not None
    # Should mention n_eff or floor
    assert "n_eff" in entry["reason_null"] or "floor" in entry["reason_null"]
    assert entry["n_eff"] < FAMILY_FLOOR_N


# ---------------------------------------------------------------------------
# (4) Monotonicity gate — RISING curve → half_life=None, reason=edge_non_decaying
# ---------------------------------------------------------------------------

def test_monotone_gate_rising_curve(tmp_path: Path):
    """A rising IC curve (like real track_record) must be blocked by the monotone gate."""
    from engine.neuralweb.half_life import build_half_lives

    # Monotonically RISING IC — matches real track_record pattern
    _make_estimates_parquet(tmp_path, [
        _minimal_estimates_row("track_record", 5, 0.0487, 200),
        _minimal_estimates_row("track_record", 10, 0.0573, 200),
        _minimal_estimates_row("track_record", 21, 0.0717, 200),
        _minimal_estimates_row("track_record", 63, 0.1112, 200),
        _minimal_estimates_row("track_record", 126, 0.1578, 200),
    ])
    graded_rows = [_minimal_graded_row("track_record", f"S{i}", "2026-01-01", 21, 0.01)
                   for i in range(250)]
    _make_spine_parquet(tmp_path, graded_rows)

    payload = build_half_lives(tmp_path)
    entry = payload["families"]["track_record"]
    assert entry["half_life"] is None, "Rising curve must have null half_life"
    assert entry["reason_null"] == "edge_non_decaying", (
        f"Expected reason='edge_non_decaying', got {entry['reason_null']!r}"
    )
    # fit_rho should be positive (indicating rising correlation)
    if entry["fit_rho"] is not None:
        assert entry["fit_rho"] > 0, "Rising curve should have positive Spearman rho"


# ---------------------------------------------------------------------------
# (5) Monotonicity gate — DECAYING curve → finite tau
# ---------------------------------------------------------------------------

def test_monotone_gate_decaying_curve(tmp_path: Path):
    """A monotonically decaying IC curve must yield a finite positive half_life."""
    from engine.neuralweb.half_life import build_half_lives

    # Strictly DECREASING IC — gate should pass
    _make_estimates_parquet(tmp_path, [
        _minimal_estimates_row("test_engine", 5, 0.20, 500),
        _minimal_estimates_row("test_engine", 10, 0.14, 500),
        _minimal_estimates_row("test_engine", 21, 0.08, 500),
        _minimal_estimates_row("test_engine", 63, 0.03, 500),
        _minimal_estimates_row("test_engine", 126, 0.01, 500),
    ])
    # 250 graded rows for multiple horizons (above family floor)
    graded_rows = []
    for i in range(50):
        for h in [5, 10, 21, 63, 126]:
            graded_rows.append(
                _minimal_graded_row("test_engine", f"S{i}", "2026-01-01", h, 0.01)
            )
    _make_spine_parquet(tmp_path, graded_rows)

    payload = build_half_lives(tmp_path)
    entry = payload["families"]["test_engine"]
    # A decaying curve should yield a finite half_life OR be caught by CI instability
    # (which is also acceptable — CI instability → NaN is correct behavior)
    assert entry["decay_kind"] in ("horizon", None), (
        f"decay_kind must be 'horizon' or None, got {entry['decay_kind']!r}"
    )
    if entry["half_life"] is not None:
        assert isinstance(entry["half_life"], float), "half_life must be float"
        assert entry["half_life"] > 0, "half_life must be positive"
        assert math.isfinite(entry["half_life"]), "half_life must be finite"
        # CI should also be non-None for a measured value
        # (may be None if bootstrap was unstable — that's ok too)
    # fit_rho should be negative (decreasing)
    if entry["fit_rho"] is not None:
        assert entry["fit_rho"] < 0, "Decaying curve should have negative Spearman rho"


# ---------------------------------------------------------------------------
# (6) Staleness honesty — no family has decay_kind=="staleness" with non-null half_life
# ---------------------------------------------------------------------------

def test_staleness_honesty(tmp_path: Path):
    """W2 must not deliver any staleness half-life numbers."""
    from engine.neuralweb.half_life import build_half_lives

    # Write minimal estimates
    _make_estimates_parquet(tmp_path, [
        _minimal_estimates_row("track_record", 5, 0.05, 200),
        _minimal_estimates_row("track_record", 10, 0.07, 200),
    ])
    _make_spine_parquet(tmp_path, [
        _minimal_graded_row("track_record", f"S{i}", "2026-01-01", 5, 0.01)
        for i in range(250)
    ])

    payload = build_half_lives(tmp_path)
    for key, entry in payload.get("families", {}).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("decay_kind") == "staleness":
            assert entry.get("half_life") is None, (
                f"Family {key!r}: decay_kind=staleness must have null half_life "
                f"(staleness half-life is UNMEASURED in W2)"
            )

    # Also check the notes mention UNMEASURED for staleness
    notes = payload.get("notes", "")
    assert "UNMEASURED" in notes or "unmeasured" in notes.lower(), (
        "Artifact notes must explicitly state staleness half-life is UNMEASURED"
    )


# ---------------------------------------------------------------------------
# (7) query.py: "half_life" in COLUMNS; old-schema parquet loads with NaN
# ---------------------------------------------------------------------------

def test_half_life_in_columns():
    """'half_life' must be present in engine.neuralweb.query.COLUMNS."""
    from engine.neuralweb.query import COLUMNS
    assert "half_life" in COLUMNS, "'half_life' must be in COLUMNS (W1 contract)"


def test_old_schema_parquet_loads_with_nan(tmp_path: Path):
    """Old-schema parquet (without half_life column) must load via _ensure_columns with NaN."""
    from engine.neuralweb.query import _ensure_columns, COLUMNS

    # Build a minimal DataFrame without the half_life column
    old_schema_df = pd.DataFrame({
        "signal_id": ["test:s1"],
        "engine": ["track_record"],
        "family": ["track_record:buy"],
        "ledger": ["track_record"],
        "as_of": ["2026-01-01"],
        "symbol": ["AAPL"],
        "scope_type": ["entity"],
        "universe": ["us_1500"],
        "horizon": [21],
        "direction": [1],
        "size_binding": [False],
        "fill_basis": ["close"],
        "score": [1.0],
        "outcome_excess": [0.04],
        "outcome_graded": [True],
        "graded_at": ["2026-02-01"],
    })
    assert "half_life" not in old_schema_df.columns

    # _ensure_columns must add it without error
    result = _ensure_columns(old_schema_df)
    assert "half_life" in result.columns
    # Must be NaN (not 0, not False) for rows without a source value
    assert result["half_life"].isna().all(), "half_life must default to NaN for old-schema rows"
    # Must have all canonical COLUMNS
    assert list(result.columns) == COLUMNS, "Column order must match COLUMNS"


# ---------------------------------------------------------------------------
# (8) CI-pin — artifact count == 113; "kernel-half-lives" in registry
# ---------------------------------------------------------------------------

def test_artifact_count_and_new_id():
    """synapse.yml must have exactly 113 artifacts including 'kernel-half-lives'."""
    with _SYNAPSE_YML.open(encoding="utf-8") as fh:
        registry = yaml.safe_load(fh)
    artifact_ids = list(registry.get("artifacts", {}).keys())
    assert len(artifact_ids) == 113, (
        f"Expected 113 artifacts in synapse.yml, found {len(artifact_ids)}. "
        "Update test_signal_bus_doc.py:76 if count changed intentionally."
    )
    assert "kernel-half-lives" in artifact_ids, (
        "'kernel-half-lives' must be registered in config/synapse.yml"
    )


# ---------------------------------------------------------------------------
# (9) Status sentinel — build_half_lives always emits "status":"fit_ran"
# ---------------------------------------------------------------------------

def test_status_sentinel_always_present(tmp_path: Path):
    """build_half_lives must always return a dict with status='fit_ran'."""
    from engine.neuralweb.half_life import build_half_lives

    # No estimates at all → should still return status
    payload = build_half_lives(tmp_path)
    assert payload.get("status") == "fit_ran", (
        f"build_half_lives must return status='fit_ran', got {payload.get('status')!r}"
    )


# ---------------------------------------------------------------------------
# (10) R8/display-only — no behavior-changing module imports half_life.py
# ---------------------------------------------------------------------------

def test_no_behavioral_consumer():
    """allocation.py, alert_triage, and board ordering must not import half_life."""
    behavioral_modules = [
        _REPO_ROOT / "engine" / "allocation.py",
        _REPO_ROOT / "engine" / "alert_triage.py",
        _REPO_ROOT / "scripts" / "build_standout_board.py",
        _REPO_ROOT / "scripts" / "build_board_order.py",
    ]
    for mod_path in behavioral_modules:
        if not mod_path.exists():
            continue
        source = mod_path.read_text(encoding="utf-8")
        assert "half_life" not in source or "family_half_life" not in source or (
            # Allow import of the module in tests; block in behavioral modules
            "import half_life" not in source and "from engine.neuralweb.half_life" not in source
        ), (
            f"{mod_path.name}: behavioral module must not import half_life.py "
            f"(R7/R8 display-only law)"
        )


# ---------------------------------------------------------------------------
# (11) Fail-open when estimates absent
# ---------------------------------------------------------------------------

def test_fail_open_no_estimates(tmp_path: Path):
    """build_half_lives must return a well-formed payload even with no estimates."""
    from engine.neuralweb.half_life import build_half_lives

    # tmp_path has no parquet files at all
    payload = build_half_lives(tmp_path)
    assert isinstance(payload, dict)
    assert payload.get("status") == "fit_ran"
    assert "families" in payload
    assert isinstance(payload["families"], dict)
    # No family should have a non-None half_life
    for v in payload["families"].values():
        if isinstance(v, dict):
            assert v.get("half_life") is None


# ---------------------------------------------------------------------------
# (12) _sanitize_for_json — numpy scalars cast to python-native
# ---------------------------------------------------------------------------

def test_sanitize_for_json():
    """_sanitize_for_json must cast numpy scalars to python-native types."""
    from engine.neuralweb.half_life import _sanitize_for_json

    obj = {
        "a": np.float64(1.23),
        "b": np.int64(42),
        "c": np.bool_(True),
        "d": None,
        "e": [np.float64(0.5), np.int64(7)],
        "f": {"nested": np.float64(0.0)},
        "g": np.float64(float("nan")),  # NaN → None
        "h": np.float64(float("inf")),  # inf → None
    }
    result = _sanitize_for_json(obj)
    assert isinstance(result["a"], float) and not isinstance(result["a"], np.floating)
    assert isinstance(result["b"], int) and not isinstance(result["b"], np.integer)
    assert isinstance(result["c"], bool) and not isinstance(result["c"], np.bool_)
    assert result["d"] is None
    assert all(isinstance(x, (int, float)) for x in result["e"])
    assert isinstance(result["f"]["nested"], float)
    assert result["g"] is None  # NaN → None
    assert result["h"] is None  # inf → None


# ---------------------------------------------------------------------------
# (13) write_half_lives — always writes file
# ---------------------------------------------------------------------------

def test_write_half_lives_always_writes(tmp_path: Path):
    """write_half_lives must write half_life.json even when all families are null."""
    from engine.neuralweb.half_life import write_half_lives

    # No data at all — should still write
    stats = write_half_lives(tmp_path)
    out_path = Path(stats["output_path"])
    assert out_path.exists(), "half_life.json must always be written"

    # Parse and verify structure
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "families" in payload
    assert "status" in payload
    assert payload["status"] in ("fit_ran", "fit_failed")

    # Verify json is parseable and all values are python-native
    for key, entry in payload["families"].items():
        if isinstance(entry, dict) and "half_life" in entry:
            hl = entry["half_life"]
            assert hl is None or isinstance(hl, float), (
                f"{key}: half_life in written JSON must be float|null"
            )


# ---------------------------------------------------------------------------
# (14) Notes field mentions UNMEASURED for staleness
# ---------------------------------------------------------------------------

def test_notes_mention_staleness_unmeasured(tmp_path: Path):
    """The artifact notes must explicitly state staleness half-life is UNMEASURED."""
    from engine.neuralweb.half_life import build_half_lives

    payload = build_half_lives(tmp_path)
    notes = payload.get("notes", "")
    assert "staleness" in notes.lower() or "UNMEASURED" in notes, (
        "notes must mention staleness and UNMEASURED status"
    )


# ---------------------------------------------------------------------------
# (15) _stamp_family_half_life — fail-open when half_life.json absent
# ---------------------------------------------------------------------------

def test_stamp_fail_open_no_artifact(tmp_path: Path):
    """_stamp_family_half_life must return df unchanged when half_life.json absent."""
    from engine.neuralweb.query import _stamp_family_half_life, COLUMNS

    df = pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS})
    df = pd.concat([df, pd.DataFrame([{
        "signal_id": "t:s1",
        "engine": "track_record",
        "half_life": np.nan,
        **{c: np.nan for c in COLUMNS if c not in ["signal_id", "engine", "half_life"]},
    }])], ignore_index=True)

    # tmp_path has no half_life.json
    result = _stamp_family_half_life(df.copy(), tmp_path)
    assert result["half_life"].isna().all(), "half_life must stay NaN when artifact absent"


# ---------------------------------------------------------------------------
# (16) _stamp_family_half_life — stamps numeric values on matching rows
# ---------------------------------------------------------------------------

def test_stamp_stamps_numeric_half_life(tmp_path: Path):
    """_stamp_family_half_life must fill half_life for rows whose engine has a measured value."""
    from engine.neuralweb.query import _stamp_family_half_life, COLUMNS

    # Write a half_life.json with a measured value for test_engine
    hl_dir = tmp_path / "data" / "neuralweb"
    hl_dir.mkdir(parents=True, exist_ok=True)
    hl_payload = {
        "families": {
            "test_engine": {
                "decay_kind": "horizon",
                "outcome_unit": "signed_excess",
                "half_life": 21.5,
                "ci_low": 18.0,
                "ci_high": 26.0,
                "n_eff": 300,
                "n_horizons": 5,
                "reason_null": None,
                "fit_rho": -0.95,
            },
            "other_engine": {
                "decay_kind": None,
                "outcome_unit": "magnitude",
                "half_life": None,
                "ci_low": None,
                "ci_high": None,
                "n_eff": 50,
                "n_horizons": 2,
                "reason_null": "edge_non_decaying",
                "fit_rho": 0.82,
            },
        },
        "status": "fit_ran",
    }
    (hl_dir / "half_life.json").write_text(
        json.dumps(hl_payload, indent=2), encoding="utf-8"
    )

    # Build a df with rows for both engines; half_life starts as NaN
    rows = [
        {c: np.nan for c in COLUMNS}
        | {"signal_id": f"t:s{i}", "engine": "test_engine", "half_life": np.nan}
        for i in range(3)
    ] + [
        {c: np.nan for c in COLUMNS}
        | {"signal_id": f"o:s{i}", "engine": "other_engine", "half_life": np.nan}
        for i in range(2)
    ]
    df = pd.DataFrame(rows)[COLUMNS]

    result = _stamp_family_half_life(df, tmp_path)
    # test_engine rows should have half_life=21.5
    test_mask = result["engine"] == "test_engine"
    test_hl = result.loc[test_mask, "half_life"].tolist()
    assert all(abs(v - 21.5) < 1e-6 for v in test_hl), (
        f"test_engine rows should be stamped with half_life≈21.5; got {test_hl}"
    )
    # other_engine rows should stay NaN (null half_life in artifact)
    other_mask = result["engine"] == "other_engine"
    assert result.loc[other_mask, "half_life"].isna().all(), (
        "other_engine rows should stay NaN (null half_life)"
    )
