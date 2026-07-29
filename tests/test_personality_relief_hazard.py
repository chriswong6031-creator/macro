"""Prospective, parity, lifecycle, and authority fences for PSS-RH1."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from engine import personality_relief_hazard as prh
from scripts.research import pss_sr3_participation_feasibility as sr3

AUDIT_GRID = Path("data/personality_timing/relief_hazard_audit_grid_v1.parquet")
AUDIT_GRID_SHA256 = (
    "fa2e1c0f6127f9747627075ba534d604b8a042df49ff6c55584c2af885fa8608"
)


def _copy_registration(root: Path) -> None:
    target = root / "personality_timing"
    target.mkdir(parents=True, exist_ok=True)
    source = Path("data/personality_timing")
    for name in (
        "relief_hazard_manifest_v1.json",
        "relief_hazard_membership_v1.json",
    ):
        shutil.copyfile(source / name, target / name)


def _event(
    *,
    action_date: str,
    sym: str = "TEST",
    group: str = "relief_hazard",
) -> dict:
    return {
        "kind": "event",
        "schema": prh.LEDGER_SCHEMA,
        "program_id": prh.PROGRAM_ID,
        "family": prh.FAMILY,
        "construction_id": prh.CONSTRUCTION_ID,
        "construction_sha256": prh.EXPECTED_CONSTRUCTION_SHA256,
        "membership_sha256": prh.EXPECTED_MEMBERSHIP_SHA256,
        "authority": dict(prh.AUTHORITY),
        "sym": sym,
        "sector": "Information Technology",
        "anchor_date": "2026-07-20",
        "formation_confirm": "2026-07-23",
        "action_date": action_date,
        "action_close": 100.0,
        "atr_anchor": 2.0,
        "reference_low": 96.0,
        "anchor_breadth": 0.2,
        "formation_peer_peak": 0.3,
        "level_min": 0.7,
        "active_min": 0.6 if group == "relief_hazard" else 0.3,
        "group": group,
        "delay_sessions": 2,
        "close_depth_atr": 2.0,
        "severity_band": "p2",
        "delay_band": "d1",
        "distance_band": "x2",
        "grade": None,
        "grade_as_of": None,
    }


def _ledger_events(root: Path) -> list[dict]:
    path = root / "personality_timing" / "relief_hazard.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and json.loads(line).get("kind") == "event"
    ]


def test_exact_detector_primitives_match_frozen_sr3_reference():
    idx = pd.bdate_range("2025-01-02", periods=90)
    close = 100 + np.linspace(0, 6, len(idx)) + np.sin(np.arange(len(idx)) / 4)
    frame = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        },
        index=idx,
    )
    pd.testing.assert_series_equal(prh.atr14_prior(frame), sr3.atr14_prior(frame))

    candidates = np.zeros(90, dtype=bool)
    candidates[[1, 5, 23, 24, 50]] = True
    np.testing.assert_array_equal(
        prh.greedy_anchors(candidates),
        sr3.greedy_anchors(candidates),
    )

    names = [f"P{i:02d}" for i in range(17)]
    close_panel = pd.DataFrame(
        {
            name: 100 + np.linspace(0, i + 4, len(idx))
            for i, name in enumerate(names)
        },
        index=idx,
    )
    low_panel = close_panel - 1.0
    atr_panel = pd.DataFrame(2.0, index=idx, columns=names)
    anchor = 30
    action = 40
    exact, reason = sr3.peer_recovery_minima(
        close_panel,
        low_panel,
        atr_panel,
        names[0],
        anchor,
        action,
    )
    live, live_reason = prh.peer_recovery_minima(
        close_panel,
        low_panel,
        atr_panel,
        names[0],
        anchor,
        action,
    )
    assert reason == live_reason == "ok"
    assert live is not None and exact is not None
    assert live[0] == exact["level_0.50"]
    assert live[1] == exact["joint_5"]


def test_full_runtime_detector_matches_every_frozen_sr3_historical_path(
    tmp_path,
    monkeypatch,
):
    registration = prh.load_registration()
    assert registration is not None
    # Audit-only: expose the historical construction to the runtime scanner,
    # then require bit-exact parity with the frozen SR3 events tape.
    # Production keeps the hash-bound 2026-07-24 boundary and cannot execute
    # this monkeypatch.
    #
    # The replay runs on the FROZEN input grid, never the live store. Live
    # panels are total-return adjusted: every dividend retroactively
    # re-scales (and re-rounds) the full close/low/ATR history, and group
    # labels are peer-count ratios thresholded at exactly 0.50, with 525 of
    # the 6294 frozen rows within 0.04 of a floor. A live-store replay
    # therefore flips labels on dividend nights with zero code drift — the
    # 2026-07-28 collection moved 238 values and 13 one-peer count ratios
    # (#3866), and the 2026-07-29 collection re-rounded ASH's 2023-11-08
    # close by ~2e-7 relative across a ~1e-5-dollar threshold margin,
    # pushing IOSP (2023-10-12 -> 2023-11-08) active_min from 20/42 onto
    # the 0.50 floor: level_control -> relief_hazard. No value tolerance
    # separates that from real drift (the ratio steps 1/42 while the input
    # moves 2e-7), so the inputs are pinned instead: the ohlcv vintage at
    # the registration's freeze SOURCE_COMMIT (71ac1df412a9, ohlcv tree
    # identical to the last pre-break daily collection), hash-bound below
    # and rebuilt only by scripts/research/freeze_pss_rh1_audit_grid.py.
    # With the grid frozen, any missing key, any label change, or any value
    # beyond float-reproduction scale is detector-code drift and fails
    # hard — there is no drift budget.
    assert hashlib.sha256(AUDIT_GRID.read_bytes()).hexdigest() == AUDIT_GRID_SHA256
    grid = pd.read_parquet(AUDIT_GRID)
    ohlcv_dir = tmp_path / "baskets" / "ohlcv"
    ohlcv_dir.mkdir(parents=True)
    for sym, frame in grid.groupby("sym", sort=False):
        frame.drop(columns="sym").set_index("date").to_parquet(
            ohlcv_dir / f"{sym}.parquet"
        )
    monkeypatch.setattr(prh, "NOT_BEFORE_SESSION", "2019-01-01")
    detected, _ = prh._scan_paths(
        registration,
        tmp_path,
        pd.Timestamp("2026-07-27"),
    )
    assert len(detected) == 6427
    live = {
        (row["sym"], row["anchor_date"], row["action_date"]): row
        for row in detected
    }
    history = pd.read_parquet(
        "data/research/pss_sr3_participation_recovery_events.parquet"
    )
    assert len(history) == 6294
    for row in history.itertuples(index=False):
        key = (
            str(row.sym),
            str(pd.Timestamp(row.anchor_date).date()),
            str(pd.Timestamp(row.date).date()),
        )
        actual = live.get(key)
        assert actual is not None, ("missing", key)
        expected_group = (
            "relief_hazard" if str(row.group) == "sr3" else str(row.group)
        )
        assert actual["group"] == expected_group, (key, actual["group"])
        for field, frozen_value in (
            ("level_min", row.level_min),
            ("active_min", row.active_min),
            ("close_depth_atr", row.close_depth_atr),
        ):
            assert np.isclose(
                actual[field], float(frozen_value), atol=1e-9
            ), (field, key, float(frozen_value), actual[field])


def test_subject_action_is_first_observable_held_recovery_and_prefix_invariant():
    close = np.full(20, 94.0)
    low = np.full(20, 90.0)
    # Anchor=2 -> confirmation=5 -> earliest possible action=7.
    close[5:9] = [95.0, 96.0, 101.0, 103.0]
    low[5:9] = [89.0, 90.0, 91.0, 92.0]
    full = prh.first_subject_recovery(close, low, 2, 10.0, 90.0)
    prefix = prh.first_subject_recovery(close[:8], low[:8], 2, 10.0, 90.0)
    assert full == prefix == 7


def test_group_boundaries_are_disjoint():
    assert prh.classify_path(0.499999, 1.0) == "weak_level"
    assert prh.classify_path(0.50, 0.499999) == "level_control"
    assert prh.classify_path(0.50, 0.50) == "relief_hazard"


def test_nightly_enrollment_rejects_backfill_and_is_idempotent(
    tmp_path,
    monkeypatch,
):
    _copy_registration(tmp_path)
    old = _event(action_date=prh.NOT_BEFORE_SESSION, sym="OLD")
    future = _event(action_date="2026-07-27", sym="NEW")
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(
        prh,
        "_scan_paths",
        lambda registration, root, through: (
            [old.copy(), future.copy()],
            {"detected_post_cutoff_paths": 2},
        ),
    )

    first = prh.update(root=tmp_path, as_of="2026-07-27")
    assert first is not None
    assert first["ledger"]["events"] == 1
    assert first["ledger"]["appended_today"] == 1
    assert first["ledger"]["rejected_pre_cutoff_today"] == 1
    rows = _ledger_events(tmp_path)
    assert [row["sym"] for row in rows] == ["NEW"]
    assert rows[0]["action_date"] > prh.NOT_BEFORE_SESSION
    assert rows[0]["authority"] == prh.AUTHORITY

    before = (tmp_path / "personality_timing" / "relief_hazard.jsonl").read_bytes()
    second = prh.update(root=tmp_path, as_of="2026-07-27")
    after = (tmp_path / "personality_timing" / "relief_hazard.jsonl").read_bytes()
    assert second is not None and second["ledger"]["appended_today"] == 0
    assert before == after


def test_non_nightly_lane_cannot_scan_append_or_grade(tmp_path, monkeypatch):
    _copy_registration(tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("non-nightly lane attempted a scan")

    monkeypatch.setattr(prh, "_scan_paths", forbidden)
    state = prh.update(root=tmp_path, as_of="2026-07-27")
    assert state is not None
    assert state["gate_open"] is False
    assert state["ledger"]["events"] == 0
    assert not (tmp_path / "personality_timing" / "relief_hazard.jsonl").exists()
    assert (tmp_path / "personality_timing" / "relief_hazard_state.json").exists()


def test_grade_waits_63_later_sessions_and_excludes_action_close():
    idx = pd.bdate_range("2026-07-27", periods=100)
    close = np.full(len(idx), 100.0)
    low = np.full(len(idx), 99.0)
    action = 32
    close[action] = 90.0
    row = _event(action_date=str(idx[action].date()))
    row["action_close"] = 90.0
    row["reference_low"] = 80.0
    row["atr_anchor"] = 2.0
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": low,
            "close": close,
        },
        index=idx,
    )
    assert prh._grade_row(frame.iloc[: action + prh.GRADE_HORIZON], row) is None
    grade = prh._grade_row(frame, row)
    assert grade is not None
    assert grade["matured_on"] == str(idx[action + prh.GRADE_HORIZON].date())
    assert grade["mae63"] > 11.0  # action's 90 close is excluded from MAE63
    assert grade["rebound8_first"] is True


def test_competing_risk_breach_wins_a_same_session_tie_and_unresolved_is_failure():
    close = np.full(70, 100.0)
    low = np.full(70, 99.0)
    close[1] = 108.0
    low[1] = 94.0
    tie = prh._competing_risk(close, low, 0, breach_level=95.0)
    assert tie == {
        "rebound8_first": False,
        "breach_first": True,
        "unresolved": False,
        "resolution_day": 1,
    }

    flat = prh._competing_risk(
        np.full(70, 100.0),
        np.full(70, 99.0),
        0,
        breach_level=95.0,
    )
    assert flat["rebound8_first"] is False
    assert flat["breach_first"] is False
    assert flat["unresolved"] is True


def test_registration_is_fully_hash_bound_and_drift_fails_inert(
    tmp_path,
    monkeypatch,
):
    assert prh.load_registration() is not None
    _copy_registration(tmp_path)
    manifest = tmp_path / "personality_timing" / "relief_hazard_manifest_v1.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert prh.load_registration(tmp_path) is None

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    state = prh.update(root=tmp_path, as_of="2026-07-27")
    assert state is not None
    assert state["registration_ok"] is False
    assert state["ledger"]["events"] == 0
    assert not (tmp_path / "personality_timing" / "relief_hazard.jsonl").exists()


def test_committed_launch_is_zero_event_and_has_absolute_authority_fences():
    rows = [
        json.loads(line)
        for line in Path(
            "data/personality_timing/relief_hazard.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert len(rows) == 1 and rows[0]["kind"] == "registration"
    assert rows[0]["event_rows_at_launch"] == 0
    assert rows[0]["not_before_session"] == prh.NOT_BEFORE_SESSION
    assert rows[0]["authority"] == prh.AUTHORITY

    state = json.loads(
        Path(
            "data/personality_timing/relief_hazard_state.json"
        ).read_text(encoding="utf-8")
    )
    assert state["ledger"]["events"] == 0
    assert state["consumers"] == []
    assert state["authority"] == prh.AUTHORITY
    assert state["decision_read"]["sole_read_executed"] is False

    registry = Path("config/synapse.yml").read_text(encoding="utf-8")
    assert "personality-relief-hazard-state:" in registry
    state_block = registry.split("personality-relief-hazard-state:", 1)[1].split(
        "# IHM-R1", 1
    )[0]
    assert "consumers: []" in state_block
    assert "scored_path_surfaces: []" in state_block

    run_source = Path("engine/run.py").read_text(encoding="utf-8")
    assert "personality_relief_hazard as _prh" in run_source
    assert 'latest["personality_relief_hazard"]' not in run_source


def test_charter_forbids_interim_and_automatic_promotion():
    charter = Path(
        "research/PSS_RH1_RELIEF_HAZARD_PROSPECTIVE_CHARTER.md"
    ).read_text(encoding="utf-8")
    assert "No interim outcome analysis is permitted" in charter
    assert "Failure of any condition kills RH1 at its sole read" in charter
    assert "no automatic promotion" in charter
    assert "strictly later than 2026-07-24" in charter
    dnr = Path("research/DO_NOT_REBUILD.md").read_text(encoding="utf-8")
    assert "PSS-RH1 exact SR3 label as an adverse" in dnr
    assert "Do not backfill, retime, tune, expose per-ticker state" in dnr
