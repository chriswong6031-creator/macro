"""Prospective and authority fences for the frozen terminality shadow lane."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from engine import personality_terminality_shadow as pts
from scripts.build_stock_library import (
    _attach_terminality_shadow,
    _load_terminality_shadow_map,
)


def _tape(n: int = 120) -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-02", periods=n)
    close = 100.0 + np.linspace(0, 8, n) + np.sin(np.arange(n) / 3)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000 + np.arange(n) * 100,
        },
        index=idx,
    )


def _write_tape(root: Path, sym: str, tape: pd.DataFrame) -> None:
    d = root / "baskets" / "ohlcv"
    d.mkdir(parents=True, exist_ok=True)
    tape.to_parquet(d / f"{sym}.parquet")


def _write_context(root: Path, idx: pd.DatetimeIndex) -> None:
    d = root / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": np.linspace(400, 430, len(idx))}, index=idx).to_parquet(
        d / "SPY.parquet"
    )
    b = root / "breadth"
    b.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"ticker": "TEST", "sector": "Unknown", "source": "fixture"}]
    ).to_parquet(b / "ticker_sectors.parquet", index=False)


def _write_source(root: Path, entry_date: str, entry_idx: int, entry_px: float) -> None:
    d = root / "personality_timing"
    d.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "personality_gate_shadow.ledger/v1",
        "as_of": pts.SOURCE_AS_OF_FLOOR,
        "sym": "TEST",
        "codex_asof": "2026-07-25",
        "tailored_rung": "3D",
        "fired_tailored": True,
        "tailored_entry": {
            "entry_date": entry_date,
            "entry_idx": entry_idx,
            "entry_px": entry_px,
        },
    }
    (d / "gate_shadow.jsonl").write_text(json.dumps(row) + "\n")


def _rows(root: Path) -> list[dict]:
    path = root / "personality_timing" / "terminality_shadow.jsonl"
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    ]


def _fake_artifact() -> dict:
    return {
        "manifest": {
            "train_end": "2022-12-31",
            "threshold": 0.6642405954734382,
            "target_coverage": 0.20,
        },
        "models": {},
    }


def _fake_features(ohlcv, market, sector):
    del market, sector
    n = len(ohlcv)
    out = {name: np.zeros(n, dtype=float) for name in pts.FEATURES}
    # First call: rejection exists before the observation timestamp and must not
    # backfill. Once a new session is appended, the last bar is a causal hit.
    out["x_price_rejection"] = np.zeros(n, dtype=bool)
    out["x_price_rejection"][118] = True
    if n > 120:
        out["x_price_rejection"][-1] = True
    return out


def test_prospective_watch_never_backfills_then_advances_once(tmp_path, monkeypatch):
    tape = _tape()
    _write_tape(tmp_path, "TEST", tape)
    _write_context(tmp_path, tape.index)
    event_i = len(tape) - 6
    _write_source(
        tmp_path,
        str(tape.index[event_i].date()),
        event_i,
        float(tape["close"].iloc[event_i]),
    )
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(pts, "load_artifact", lambda root=None: _fake_artifact())
    monkeypatch.setattr(pts, "score_locator", lambda artifact, values: (0.8, 0.8, 0.8))
    monkeypatch.setattr(pts, "feature_arrays", _fake_features)

    first = pts.update(root=tmp_path, as_of="2026-07-26")
    assert first["ledger"]["incumbent_events"] == 1
    assert first["ledger"]["selected"] == 1
    row = _rows(tmp_path)[0]
    assert row["prospective_from"] == str(tape.index[-1].date())
    assert row["watch_status"] == "watching"
    assert row["action"] is None  # the earlier rejection was already visible
    assert row["authority"] == "shadow_only" and row["display_only"] is True

    next_idx = pd.bdate_range(tape.index[-1] + pd.Timedelta(days=1), periods=1)[0]
    extended = pd.concat(
        [
            tape,
            pd.DataFrame(
                {
                    "open": [109.0], "high": [111.0], "low": [108.0],
                    "close": [110.0], "volume": [1_200_000],
                },
                index=[next_idx],
            ),
        ]
    )
    _write_tape(tmp_path, "TEST", extended)
    _write_context(tmp_path, extended.index)
    second = pts.update(root=tmp_path, as_of="2026-07-27")
    assert second["ledger"]["incumbent_events"] == 1
    assert second["ledger"]["appended_today"] == 0
    row = _rows(tmp_path)[0]
    assert row["watch_status"] == "rejection_observed"
    assert row["action"]["entry_date"] == str(next_idx.date())
    assert row["action"]["delay_sessions"] == 6

    # Same-day rerun is idempotent: no duplicate event or action mutation.
    pts.update(root=tmp_path, as_of="2026-07-27")
    rerun = _rows(tmp_path)
    assert len(rerun) == 1
    assert rerun[0]["action"] == row["action"]


def test_below_threshold_incumbent_is_logged_as_control(tmp_path, monkeypatch):
    tape = _tape()
    _write_tape(tmp_path, "TEST", tape)
    _write_context(tmp_path, tape.index)
    event_i = len(tape) - 1
    _write_source(
        tmp_path,
        str(tape.index[event_i].date()),
        event_i,
        float(tape["close"].iloc[event_i]),
    )
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(pts, "load_artifact", lambda root=None: _fake_artifact())
    monkeypatch.setattr(pts, "score_locator", lambda artifact, values: (0.5, 0.5, 0.5))
    monkeypatch.setattr(pts, "feature_arrays", _fake_features)

    state = pts.update(root=tmp_path, as_of="2026-07-26")
    assert state["ledger"]["incumbent_events"] == 1
    assert state["ledger"]["not_selected"] == 1
    assert state["per_ticker"] == {}
    row = _rows(tmp_path)[0]
    assert row["selected"] is False
    assert row["watch_status"] == "not_selected"


def test_non_nightly_lane_cannot_advance_ledger(tmp_path, monkeypatch):
    tape = _tape()
    _write_tape(tmp_path, "TEST", tape)
    _write_context(tmp_path, tape.index)
    _write_source(
        tmp_path,
        str(tape.index[-1].date()),
        len(tape) - 1,
        float(tape["close"].iloc[-1]),
    )
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.setattr(pts, "load_artifact", lambda root=None: _fake_artifact())

    state = pts.update(root=tmp_path, as_of="2026-07-26")
    assert state["gate_open"] is False
    assert not (tmp_path / "personality_timing" / "terminality_shadow.jsonl").exists()


def test_feature_block_is_prefix_invariant():
    tape = _tape(180)
    market = np.linspace(400, 450, len(tape))
    sector = np.linspace(100, 120, len(tape))
    full = pts.feature_arrays(tape, market, sector)
    cut = 143
    prefix = pts.feature_arrays(tape.iloc[:cut], market[:cut], sector[:cut])
    for name in pts.FEATURES:
        a = full[name][cut - 1]
        b = prefix[name][-1]
        if isinstance(a, (bool, np.bool_)):
            assert bool(a) is bool(b), name
        elif np.isnan(a):
            assert np.isnan(b), name
        else:
            assert float(a) == float(b), name


def test_committed_artifact_is_hash_bound_and_excludes_f4():
    artifact = pts.load_artifact()
    assert artifact is not None
    manifest = artifact["manifest"]
    assert manifest["model_id"] == pts.MODEL_ID
    assert manifest["f4_features_included"] is False
    assert tuple(manifest["features"]) == pts.FEATURES
    assert all("f4" not in name and "rvd" not in name for name in pts.FEATURES)


def test_artifact_hash_mismatch_makes_scorer_inert(tmp_path):
    source = pts.artifact_dir(None)
    target = pts.artifact_dir(tmp_path)
    shutil.copytree(source, target)
    near = target / "near_low.json"
    near.write_text(near.read_text() + " ")
    assert pts.load_artifact(tmp_path) is None


def test_ui_copy_keeps_shadow_out_of_decision_authority():
    template = Path("templates/stock.html.j2").read_text(encoding="utf-8")
    assert "Terminality watch · shadow" in template
    assert "Research prioritization only" in template
    assert "never changes entry, ranking, sizing, or alerts" in template


def test_stock_payload_attachment_is_copy_only_and_authority_fenced(tmp_path):
    state_dir = tmp_path / "personality_timing"
    state_dir.mkdir()
    block = {
        "schema": pts.STATE_SCHEMA,
        "model_id": pts.MODEL_ID,
        "authority": "shadow_only",
        "display_only": True,
        "status": "watching",
    }
    state = {
        "schema": pts.STATE_SCHEMA,
        "authority": "shadow_only",
        "display_only": True,
        "artifact_ok": True,
        "may_rank": False,
        "may_size": False,
        "may_gate": False,
        "may_alert": False,
        "per_ticker": {"TEST": block},
    }
    (state_dir / "terminality_shadow_state.json").write_text(json.dumps(state))
    mapping = _load_terminality_shadow_map(tmp_path)
    personality = {"base": {"archetype": {"key": "mixed"}}}
    _attach_terminality_shadow(personality, "TEST", mapping)
    assert personality["terminality_shadow"] == block
    untouched = {"base": {}}
    _attach_terminality_shadow(untouched, "ABSENT", mapping)
    assert "terminality_shadow" not in untouched

    state["may_gate"] = True
    (state_dir / "terminality_shadow_state.json").write_text(json.dumps(state))
    try:
        _load_terminality_shadow_map(tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("authority-widened state must be rejected")
