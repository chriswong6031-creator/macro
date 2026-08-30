"""Current continuous published-board membership start (`board_since`).

Pure resolver + thin market adapters. This is NOT a new ledger: it reads existing
published board fossils and stamps a display field onto in-memory candidate rows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.prophet_board_since import (
    CN_WATCH_DEFINITIONS,
    collapse_published_observations,
    current_continuous_membership_start,
    is_iso_date,
    observations_from_board_ledger_frame,
    observations_from_cn_frame,
    observations_from_intl_setups_history,
    observations_from_us_snapshots_jsonl,
    stamp_artifact_rows,
    with_current_board,
)


def _obs(*pairs):
    return [(d, frozenset(ids)) for d, ids in pairs]


def test_continuing_candidate_keeps_first_date_of_current_streak():
    obs = _obs(
        ("2026-08-20", {"AAA", "BBB"}),
        ("2026-08-21", {"AAA", "BBB"}),
        ("2026-08-24", {"AAA", "CCC"}),
    )
    assert current_continuous_membership_start(obs, "AAA") == "2026-08-20"


def test_lane_or_shelf_move_does_not_reset():
    """Membership is identity-in-published-observation, not lane identity."""
    obs = _obs(
        ("2026-08-20", {"AAA"}),  # buy
        ("2026-08-21", {"AAA"}),  # watch
        ("2026-08-24", {"AAA"}),  # leaders
    )
    assert current_continuous_membership_start(obs, "AAA") == "2026-08-20"


def test_published_absence_then_readd_resets_to_readd_date():
    obs = _obs(
        ("2026-08-20", {"AAA"}),
        ("2026-08-21", {"BBB"}),  # AAA absent on a published board
        ("2026-08-24", {"AAA"}),
    )
    assert current_continuous_membership_start(obs, "AAA") == "2026-08-24"


def test_missing_whole_board_date_does_not_reset():
    """Weekend / outage / holiday: the date is simply omitted from observations."""
    obs = _obs(
        ("2026-08-20", {"AAA"}),
        # 2026-08-21 missing entirely
        ("2026-08-24", {"AAA"}),
    )
    assert current_continuous_membership_start(obs, "AAA") == "2026-08-20"


def test_same_day_rebuild_last_snapshot_wins_and_does_not_reset():
    raw = [
        ("2026-08-24", frozenset({"AAA", "OLD"})),
        ("2026-08-24", frozenset({"AAA", "NEW"})),
    ]
    obs = collapse_published_observations(raw)
    assert obs == [("2026-08-24", frozenset({"AAA", "NEW"}))]
    assert current_continuous_membership_start(obs, "AAA") == "2026-08-24"
    assert current_continuous_membership_start(obs, "OLD") is None


def test_algorithm_definition_transition_does_not_reset_if_still_present():
    """CN live definition change is not absence. Adapter unions live defs per date."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        [
            {"date": "2026-08-20", "ticker": "600000", "board_definition": "cn_prophet_v3"},
            {"date": "2026-08-21", "ticker": "600000", "board_definition": "cn_prophet_v4"},
            {"date": "2026-08-24", "ticker": "600000", "board_definition": "cn_prophet_v4"},
        ]
    )
    obs = observations_from_cn_frame(df)
    assert current_continuous_membership_start(obs, "600000") == "2026-08-20"


def test_shadow_only_row_does_not_keep_a_visible_streak_alive():
    pd = pytest.importorskip("pandas")
    shadow = next(iter(CN_WATCH_DEFINITIONS))
    df = pd.DataFrame(
        [
            {"date": "2026-08-20", "ticker": "600000", "board_definition": "cn_prophet_v4"},
            {"date": "2026-08-21", "ticker": "600000", "board_definition": shadow},
            {"date": "2026-08-24", "ticker": "600000", "board_definition": "cn_prophet_v4"},
        ]
    )
    obs = observations_from_cn_frame(df)
    # 08-21 is shadow-only → omitted (missing observation), streak continues.
    assert current_continuous_membership_start(obs, "600000") == "2026-08-20"

    only_shadow = pd.DataFrame(
        [
            {"date": "2026-08-20", "ticker": "600001", "board_definition": shadow},
            {"date": "2026-08-24", "ticker": "600001", "board_definition": shadow},
        ]
    )
    assert observations_from_cn_frame(only_shadow) == []
    assert current_continuous_membership_start([], "600001") is None


def test_shadow_only_cannot_create_presence_on_a_live_gap_day_that_published_empty_live():
    """A date that published live rows without this ticker IS an absence, even if
    the ticker sat on a shadow cohort that same date."""
    pd = pytest.importorskip("pandas")
    shadow = next(iter(CN_WATCH_DEFINITIONS))
    df = pd.DataFrame(
        [
            {"date": "2026-08-20", "ticker": "600000", "board_definition": "cn_prophet_v4"},
            {"date": "2026-08-21", "ticker": "600000", "board_definition": shadow},
            {"date": "2026-08-21", "ticker": "600999", "board_definition": "cn_prophet_v4"},
            {"date": "2026-08-24", "ticker": "600000", "board_definition": "cn_prophet_v4"},
        ]
    )
    obs = observations_from_cn_frame(df)
    assert current_continuous_membership_start(obs, "600000") == "2026-08-24"


def test_no_history_fail_closed():
    assert current_continuous_membership_start([], "AAA") is None
    assert current_continuous_membership_start(_obs(("2026-08-24", {"BBB"})), "AAA") is None


def test_identity_must_be_on_the_last_observation():
    obs = _obs(("2026-08-20", {"AAA"}), ("2026-08-24", {"BBB"}))
    assert current_continuous_membership_start(obs, "AAA") is None


def test_hk_ca_ledger_watch_group_is_visible_membership():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        [
            {"date": "2026-08-20", "ticker": "700.HK", "group": "entry_open"},
            {"date": "2026-08-21", "ticker": "700.HK", "group": "watch"},
            {"date": "2026-08-24", "ticker": "700.HK", "group": "setting_up"},
        ]
    )
    obs = observations_from_board_ledger_frame(df)
    assert current_continuous_membership_start(obs, "700.HK") == "2026-08-20"


def test_intl_history_omits_versions_without_as_of():
    versions = [
        {"as_of": None, "buy": [{"ticker": "NESN"}]},
        {"as_of": "2026-08-20", "buy": [{"ticker": "NESN"}]},
        {"as_of": "2026-08-24", "buy": [{"ticker": "NESN"}]},
    ]
    obs = observations_from_intl_setups_history(versions)
    assert current_continuous_membership_start(obs, "NESN") == "2026-08-20"


def test_us_snapshots_jsonl_last_line_per_date_wins(tmp_path: Path):
    path = tmp_path / "snapshots.jsonl"
    rows = [
        {"as_of": "2026-08-24", "buy": [{"ticker": "OLD"}], "watch": []},
        {"as_of": "2026-08-24", "buy": [{"ticker": "AAA"}], "watch": [{"ticker": "BBB"}]},
        {"as_of": "2026-08-25", "buy": [{"ticker": "AAA"}], "leaders": [{"ticker": "AAA"}]},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    obs = observations_from_us_snapshots_jsonl(path)
    assert current_continuous_membership_start(obs, "AAA") == "2026-08-24"
    assert current_continuous_membership_start(obs, "BBB") is None
    assert current_continuous_membership_start(obs, "OLD") is None


def test_with_current_board_collapses_same_session():
    hist = _obs(("2026-08-24", {"AAA"}))
    obs = with_current_board(hist, "2026-08-24", {"AAA", "BBB"})
    assert obs[-1][1] == frozenset({"AAA", "BBB"})
    assert current_continuous_membership_start(obs, "BBB") == "2026-08-24"


def test_stamp_seeds_from_history_not_today():
    artifact = {"as_of": "2026-08-29", "buy": [{"ticker": "AAA"}, {"ticker": "NEW"}]}
    obs = _obs(("2026-08-20", {"AAA"}), ("2026-08-29", {"AAA", "NEW"}))
    stamp_artifact_rows(artifact, obs, lanes=("buy",))
    by_tk = {r["ticker"]: r["board_since"] for r in artifact["buy"]}
    assert by_tk["AAA"] == "2026-08-20"
    assert by_tk["NEW"] == "2026-08-29"


def test_stamp_carry_forward_only_when_history_cannot_prove():
    artifact = {"as_of": "2026-08-29", "buy": [{"ticker": "AAA"}]}
    prior = {"buy": [{"ticker": "AAA", "board_since": "2026-07-01"}]}
    stamp_artifact_rows(artifact, observations=[], lanes=("buy",), prior_artifact=prior)
    assert artifact["buy"][0]["board_since"] == "2026-07-01"

    fresh = {"as_of": "2026-08-29", "buy": [{"ticker": "BBB"}]}
    stamp_artifact_rows(fresh, observations=[], lanes=("buy",), prior_artifact=prior)
    assert fresh["buy"][0]["board_since"] is None


def test_stamp_does_not_fallback_to_asof_or_today():
    artifact = {
        "as_of": "2026-08-29",
        "buy": [{"ticker": "AAA", "signal": {"asof": "2026-08-21"}}],
    }
    stamp_artifact_rows(artifact, observations=[], lanes=("buy",))
    assert artifact["buy"][0]["board_since"] is None


def test_stamp_setups_without_history_does_not_mint_as_of(tmp_path, monkeypatch):
    from engine import prophet_board_since as m

    artifact = {"as_of": "2026-08-29", "buy": [{"ticker": "AAA"}]}
    monkeypatch.setattr(m, "observations_from_us_snapshots_jsonl", lambda path: [])
    out = m.stamp_setups("us", artifact, data_dir=tmp_path, repo_root=tmp_path)
    assert out["buy"][0]["board_since"] is None


def test_iso_date_reject_malformed():
    assert is_iso_date("2026-08-24") is True
    assert is_iso_date("2026-8-24") is False
    assert is_iso_date("Aug 24") is False
    assert is_iso_date(None) is False


def test_cn_watch_definitions_match_engine():
    from engine.china_standout_track import WATCH_DEFINITIONS

    assert CN_WATCH_DEFINITIONS == WATCH_DEFINITIONS
