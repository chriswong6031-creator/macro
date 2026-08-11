from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import engine.options_signal_campaign as campaign_engine
from lib import nyse_calendar

from engine.options_signal_campaign import (
    CAMPAIGNS_PATH,
    CHECKPOINT_PATH,
    FALSE_AUTHORITY,
    OUTCOMES_PATH,
    CampaignContractError,
    canonical_bytes,
    run,
)


ROOT = Path(__file__).resolve().parent.parent
LEGACY_CAMPAIGN_SHA256 = "db326f5c772ab417c43b8579ad50abb0434916922bda3a13c2da5b8303813910"


def _first_jsonl(path: Path, *, complete: bool | None = None) -> dict:
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if complete is None or (row.get("status") == "complete") is complete:
            return row
    raise AssertionError(f"no matching row in {path}")


BASE_EPISODE = _first_jsonl(ROOT / "data/options_signal_episode/episodes.jsonl")
BASE_H60 = _first_jsonl(
    ROOT / "data/options_signal_episode/outcomes_h60.jsonl", complete=True
)
BASE_SESSION = _first_jsonl(
    ROOT / "data/options_signal_episode/outcomes_session.jsonl", complete=True
)


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode()
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:24]}"


def _episode(
    source_event_id: str,
    available_at: str,
    *,
    ticker: str = "NVDA",
    right: str = "C",
    expiration: str = "2026-08-21",
    strike: float = 225.0,
    flow_side: str = "~buy",
    premium_usd: float = 1_000_000.0,
    contracts: int = 100,
) -> dict:
    row = copy.deepcopy(BASE_EPISODE)
    available = datetime.fromisoformat(available_at.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    session = available.astimezone(ZoneInfo("America/New_York")).date()
    expiry = datetime.fromisoformat(expiration).date()
    prior_session = nyse_calendar.session_n_back(session, 1)
    assert prior_session is not None
    row["source_event_id"] = source_event_id
    row["episode_id"] = _stable_id(
        "osep", row["schema"], row["source"], source_event_id
    )
    row["available_at"] = available_at
    row["event_time"] = (available - timedelta(seconds=1)).isoformat().replace(
        "+00:00", "Z"
    )
    row["observed_at"] = available_at
    row["decision_at"] = available_at
    row["published_at"] = None
    row["session_date"] = session.isoformat()
    row["ticker"] = ticker
    row["contract"] = {
        "expiration": expiration,
        "right": right,
        "strike": strike,
    }
    row["feature_snapshot"]["flow_side"] = flow_side
    row["feature_snapshot"]["premium_usd"] = premium_usd
    row["feature_snapshot"]["selection_floor_usd"] = min(25_000, premium_usd)
    row["feature_snapshot"]["contracts"] = contracts
    row["feature_snapshot"]["avg_option_trade_price"] = premium_usd / (
        contracts * 100
    )
    row["feature_snapshot"]["dte"] = (expiry - session).days
    row["provenance"]["feature_cutoff"] = available_at
    row["provenance"]["source_snapshot_asof"] = available_at
    row["provenance"]["source_artifact"] = (
        f"live_flow/events/{session.isoformat()}.jsonl"
    )
    row["provenance"]["oi_vintage"] = prior_session.isoformat()
    return row


def _h60(episode: dict, *, ret: float = 0.01) -> dict:
    row = copy.deepcopy(BASE_H60)
    available = datetime.fromisoformat(episode["available_at"].replace("Z", "+00:00"))
    row["episode_id"] = episode["episode_id"]
    row["outcome_id"] = _stable_id(
        "oout",
        row["schema"],
        "h60-aligned-bars/v1",
        episode["episode_id"],
        60,
    )
    row["horizon_anchor"] = episode["available_at"]
    row["target_time"] = (available + timedelta(minutes=60)).isoformat().replace(
        "+00:00", "Z"
    )
    row["underlying"]["ret"] = ret
    row["underlying"]["mfe"] = max(ret, 0.02)
    row["underlying"]["mae"] = min(ret, -0.01)
    row["provenance"]["price_source"] = f"data/intraday/{episode['ticker']}.parquet"
    return row


def _session(episode: dict, horizon: str = "eod", *, ret: float = 0.03) -> dict:
    row = copy.deepcopy(BASE_SESSION)
    row["episode_id"] = episode["episode_id"]
    row["outcome_id"] = _stable_id(
        "oout", "fixture-session", horizon, episode["episode_id"]
    )
    row["horizon"] = horizon
    row["horizon_sessions"] = {"eod": 0, "1d": 1, "3d": 3, "5d": 5, "10d": 10}[horizon]
    row["horizon_anchor"] = episode["available_at"]
    row["underlying"]["ret"] = ret
    row["underlying"]["mfe"] = max(ret, 0.04)
    row["underlying"]["mae"] = min(ret, -0.02)
    row["provenance"]["price_source"] = f"data/intraday/{episode['ticker']}.parquet"
    return row


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in rows))


def _root(
    tmp_path: Path,
    episodes: list[dict],
    *,
    h60: list[dict] | None = None,
    session: list[dict] | None = None,
) -> Path:
    _write_jsonl(
        tmp_path / "data/options_signal_episode/episodes.jsonl", episodes
    )
    _write_jsonl(
        tmp_path / "data/options_signal_episode/outcomes_h60.jsonl", h60 or []
    )
    _write_jsonl(
        tmp_path / "data/options_signal_episode/outcomes_session.jsonl", session or []
    )
    return tmp_path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_census_keeps_singletons_exact_contracts_stable_and_zero_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = _episode("first", "2026-08-10T14:02:00Z", premium_usd=900_000)
    second = _episode("second", "2026-08-10T14:04:00Z", premium_usd=1_100_000)
    singleton = _episode(
        "singleton", "2026-08-10T14:03:00Z", strike=230.0, flow_side="~sell"
    )
    root = _root(tmp_path, [second, singleton, first])

    summary = run(root_dir=root)
    campaigns_path = root / CAMPAIGNS_PATH
    campaigns = _read_jsonl(campaigns_path)
    assert summary["campaign_revisions_appended"] == 2
    assert len(campaigns) == 2
    assert sorted(row["descriptive"]["member_count"] for row in campaigns) == [1, 2]
    pair = next(row for row in campaigns if row["descriptive"]["member_count"] == 2)
    assert [item["episode_id"] for item in pair["members"]] == [
        first["episode_id"],
        second["episode_id"],
    ]
    assert pair["descriptive"]["premium_usd_total"] == 2_000_000
    assert pair["intent"] == {
        "opening_closing": "unavailable",
        "direction_reliability": "soft",
        "accumulation_distribution": "unavailable",
    }
    assert pair["authority"] == FALSE_AUTHORITY
    assert pair["training_eligible"] is False
    before = {
        path: (root / path).read_bytes()
        for path in (CAMPAIGNS_PATH, OUTCOMES_PATH, CHECKPOINT_PATH)
    }
    replay = run(root_dir=root)
    assert replay["campaign_revisions_appended"] == 0
    assert replay["campaign_outcomes_appended"] == 0
    assert before == {
        path: (root / path).read_bytes()
        for path in (CAMPAIGNS_PATH, OUTCOMES_PATH, CHECKPOINT_PATH)
    }


def test_group_map_iteration_is_byte_identical_for_one_exact_source_prefix(
    tmp_path: Path,
) -> None:
    episodes = [
        _episode("map-nvda", "2026-08-10T14:02:00Z"),
        _episode("map-aapl", "2026-08-10T14:03:00Z", ticker="AAPL"),
        _episode("map-put", "2026-08-10T14:04:00Z", right="P"),
    ]
    root = _root(tmp_path, episodes)
    snapshot = campaign_engine.load_ledger(
        root / campaign_engine.EPISODES_PATH,
        campaign_engine.EPISODES_PATH,
    )
    groups = campaign_engine._validated_episode_groups(snapshot)
    reversed_groups = dict(reversed(tuple(groups.items())))
    forward = campaign_engine._derive_campaign_revisions_from_groups(
        snapshot, groups, {}
    )
    reversed_rows = campaign_engine._derive_campaign_revisions_from_groups(
        snapshot, reversed_groups, {}
    )
    assert b"".join(canonical_bytes(row) + b"\n" for row in forward) == b"".join(
        canonical_bytes(row) + b"\n" for row in reversed_rows
    )


def test_late_source_extension_appends_revision_and_backdated_member_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = _episode("first", "2026-08-10T14:02:00Z")
    root = _root(tmp_path, [first])
    run(root_dir=root)
    second = _episode("second", "2026-08-10T14:05:00Z")
    _write_jsonl(root / "data/options_signal_episode/episodes.jsonl", [first, second])
    summary = run(root_dir=root)
    rows = _read_jsonl(root / CAMPAIGNS_PATH)
    assert summary["campaign_revisions_appended"] == 1
    assert len(rows) == 2
    assert rows[1]["campaign_id"] == rows[0]["campaign_id"]
    assert rows[1]["revision_number"] == 2
    assert rows[1]["supersedes_revision_id"] == rows[0]["campaign_revision_id"]
    assert [item["episode_id"] for item in rows[1]["members"]] == [
        first["episode_id"],
        second["episode_id"],
    ]

    backdated = _episode("backdated", "2026-08-10T14:01:00Z")
    _write_jsonl(
        root / "data/options_signal_episode/episodes.jsonl",
        [first, second, backdated],
    )
    with pytest.raises(CampaignContractError, match="rewrote or backdated"):
        run(root_dir=root)


@pytest.mark.parametrize("mode", ["shrink", "drift"])
def test_checkpoint_rejects_source_shrink_and_prefix_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = _episode("first", "2026-08-10T14:02:00Z")
    second = _episode("second", "2026-08-10T14:05:00Z")
    root = _root(tmp_path, [first, second])
    run(root_dir=root)
    if mode == "shrink":
        _write_jsonl(root / "data/options_signal_episode/episodes.jsonl", [first])
        match = "shrank"
    else:
        changed = copy.deepcopy(first)
        changed["feature_snapshot"]["premium_usd"] += 1
        _write_jsonl(
            root / "data/options_signal_episode/episodes.jsonl", [changed, second]
        )
        match = "prefix changed"
    with pytest.raises(CampaignContractError, match=match):
        run(root_dir=root)


def test_duplicate_nonfinite_and_schema_invalid_sources_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    episode = _episode("duplicate", "2026-08-10T14:02:00Z")
    root = _root(tmp_path / "duplicate", [episode, copy.deepcopy(episode)])
    with pytest.raises(CampaignContractError, match="duplicate source episode"):
        run(root_dir=root)

    invalid = copy.deepcopy(episode)
    del invalid["decision"]
    root = _root(tmp_path / "schema", [invalid])
    with pytest.raises(CampaignContractError, match="schema.json validation failed"):
        run(root_dir=root)

    root = _root(tmp_path / "nonfinite", [])
    raw = canonical_bytes(episode).decode().replace("1000000.0", "NaN", 1)
    (root / "data/options_signal_episode/episodes.jsonl").write_text(raw + "\n")
    with pytest.raises(CampaignContractError, match="malformed JSON"):
        run(root_dir=root)


def test_canonical_writer_has_no_mutable_display_source_dependency() -> None:
    engine = (ROOT / "engine/options_signal_campaign.py").read_text()
    builder = (ROOT / "scripts/build_options_signal_campaign.py").read_text()
    combined = f"{engine}\n{builder}"
    assert "from engine.options_signal_episode import" not in combined
    assert "from engine.options_signal_episode_contract import" in combined
    assert "feed_current" not in combined
    assert "chain_heat" not in combined


def test_non_nightly_lane_never_creates_campaign_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    root = _root(tmp_path, [_episode("one", "2026-08-10T14:02:00Z")])
    summary = run(root_dir=root)
    assert summary["wrote"] is False
    assert summary["write_skipped"] == "COLLECT_LANE is not nightly"
    assert not (root / "data/options_signal_campaign").exists()


def test_crash_before_checkpoint_replays_byte_idempotently_and_checkpoint_is_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    episode = _episode("one", "2026-08-10T14:02:00Z")
    root = _root(tmp_path, [episode], h60=[_h60(episode)])
    observed: list[str] = []

    def crash() -> None:
        assert (root / CAMPAIGNS_PATH).exists()
        assert (root / OUTCOMES_PATH).exists()
        assert not (root / CHECKPOINT_PATH).exists()
        observed.append("outputs-before-checkpoint")
        raise RuntimeError("synthetic crash before checkpoint")

    with pytest.raises(RuntimeError, match="synthetic crash"):
        run(root_dir=root, before_checkpoint=crash)
    assert observed == ["outputs-before-checkpoint"]
    before = {
        path: (root / path).read_bytes() for path in (CAMPAIGNS_PATH, OUTCOMES_PATH)
    }
    run(root_dir=root)
    assert (root / CHECKPOINT_PATH).exists()
    assert before == {
        path: (root / path).read_bytes() for path in (CAMPAIGNS_PATH, OUTCOMES_PATH)
    }
    complete = {
        path: (root / path).read_bytes()
        for path in (CAMPAIGNS_PATH, OUTCOMES_PATH, CHECKPOINT_PATH)
    }
    run(root_dir=root)
    assert complete == {
        path: (root / path).read_bytes()
        for path in (CAMPAIGNS_PATH, OUTCOMES_PATH, CHECKPOINT_PATH)
    }


def test_replay_validation_is_linear_and_byte_preserving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    episodes = [
        _episode(
            f"linear-{index}",
            f"2026-08-10T14:{index:02d}:00Z",
            strike=225.0 + index,
        )
        for index in range(24)
    ]
    root = _root(tmp_path, episodes, h60=[_h60(row) for row in episodes])
    run(root_dir=root)
    frozen = {
        path: (root / path).read_bytes()
        for path in (CAMPAIGNS_PATH, OUTCOMES_PATH, CHECKPOINT_PATH)
    }

    episode_validations = 0
    source_map_builds = 0
    real_validate_episode = campaign_engine.validate_episode
    real_source_maps = campaign_engine._source_outcome_maps

    def counted_episode(row: dict) -> None:
        nonlocal episode_validations
        episode_validations += 1
        real_validate_episode(row)

    def counted_source_maps(*args, **kwargs):
        nonlocal source_map_builds
        source_map_builds += 1
        return real_source_maps(*args, **kwargs)

    monkeypatch.setattr(campaign_engine, "validate_episode", counted_episode)
    monkeypatch.setattr(campaign_engine, "_source_outcome_maps", counted_source_maps)
    replay = campaign_engine.run(root_dir=root)

    assert replay["campaign_revisions_appended"] == 0
    assert replay["campaign_outcomes_appended"] == 0
    assert episode_validations == len(episodes)
    assert source_map_builds == 1
    assert frozen == {
        path: (root / path).read_bytes()
        for path in (CAMPAIGNS_PATH, OUTCOMES_PATH, CHECKPOINT_PATH)
    }


def test_linear_replay_preserves_each_historical_outcome_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = _episode("prefix-first", "2026-08-10T14:02:00Z")
    root = _root(tmp_path, [first], h60=[_h60(first)])
    run(root_dir=root)

    second = _episode("prefix-second", "2026-08-10T14:05:00Z")
    _write_jsonl(
        root / "data/options_signal_episode/episodes.jsonl", [first, second]
    )
    _write_jsonl(
        root / "data/options_signal_episode/outcomes_h60.jsonl",
        [_h60(first), _h60(second)],
    )
    run(root_dir=root)
    outcomes = _read_jsonl(root / OUTCOMES_PATH)
    assert outcomes[0]["source_outcome_prefix"]["records"] == 1
    assert outcomes[-1]["source_outcome_prefix"]["records"] == 2
    frozen = (root / OUTCOMES_PATH).read_bytes()

    replay = run(root_dir=root)
    assert replay["campaign_outcomes_appended"] == 0
    assert (root / OUTCOMES_PATH).read_bytes() == frozen


def test_outcome_uses_final_member_clock_exact_anchor_and_reference_only_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = _episode("first", "2026-08-10T14:02:00Z")
    second = _episode("second", "2026-08-10T14:05:00Z")
    first_h60 = _h60(first, ret=0.10)
    second_h60 = _h60(second, ret=0.20)
    root = _root(tmp_path, [first, second], h60=[first_h60, second_h60])
    summary = run(root_dir=root)
    outcomes = _read_jsonl(root / OUTCOMES_PATH)
    h60 = next(row for row in outcomes if row["horizon"] == "h60")
    assert summary["campaign_outcomes_pending"] == 5
    assert h60["campaign_available_at"] == second["available_at"]
    assert h60["anchor_episode_id"] == second["episode_id"]
    assert h60["source_outcome"]["outcome_id"] == second_h60["outcome_id"]
    assert h60["underlying"]["ret"] == 0.20
    assert h60["underlying"]["ret"] != 0.15
    coverage = h60["member_outcome_coverage"]
    assert coverage["observed_member_count"] == 2
    assert [item["episode_id"] for item in coverage["references"]] == [
        first["episode_id"],
        second["episode_id"],
    ]
    assert all(set(item) == {"episode_id", "outcome_id", "status", "row", "row_sha256"} for item in coverage["references"])
    assert h60["option"] == {
        "status": "unavailable",
        "reason": "no_executable_nbbo_quote_path",
        "quote_basis": None,
        "ret": None,
        "mfe": None,
        "mae": None,
    }
    assert h60["authority"] == FALSE_AUTHORITY
    assert h60["training_eligible"] is False


def test_outcome_rejects_noncausal_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = _episode("first", "2026-08-10T14:02:00Z")
    second = _episode("second", "2026-08-10T14:05:00Z")
    bad = _h60(second)
    bad["horizon_anchor"] = first["available_at"]
    root = _root(tmp_path, [first, second], h60=[bad])
    with pytest.raises(CampaignContractError, match="horizon_anchor"):
        run(root_dir=root)


def test_future_feature_cutoff_is_rejected_before_campaign_membership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    episode = _episode("future-feature", "2026-08-11T14:00:00Z")
    episode["provenance"]["feature_cutoff"] = "2026-08-12T14:00:00Z"
    root = _root(tmp_path, [episode])
    with pytest.raises(CampaignContractError, match="feature_cutoff"):
        run(root_dir=root)


@pytest.mark.parametrize("poison", ["ten-minute-target", "forged-id"])
def test_h60_identity_and_exact_sixty_minute_horizon_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, poison: str
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    episode = _episode("horizon-source", "2026-08-10T14:00:00Z")
    outcome = _h60(episode)
    if poison == "ten-minute-target":
        outcome["target_time"] = "2026-08-10T14:10:00Z"
        match = "exactly anchor plus 60m"
    else:
        outcome["outcome_id"] = "oout_" + "0" * 24
        match = "outcome_id"
    root = _root(tmp_path, [episode], h60=[outcome])
    with pytest.raises(CampaignContractError, match=match):
        run(root_dir=root)


def test_member_order_uses_parsed_time_across_exact_and_fractional_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    exact = _episode("exact", "2026-08-11T14:00:00Z")
    fractional = _episode("fractional", "2026-08-11T14:00:00.100000Z")
    root = _root(tmp_path, [fractional, exact])
    run(root_dir=root)
    campaign = _read_jsonl(root / CAMPAIGNS_PATH)[0]
    assert [member["episode_id"] for member in campaign["members"]] == [
        exact["episode_id"],
        fractional["episode_id"],
    ]
    assert campaign["descriptive"]["availability_span_seconds"] == 0.1
    assert campaign["formed_at"] == fractional["available_at"]


def test_evidence_phase_is_exact_before_at_and_after_rule_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    root = _root(
        tmp_path,
        [_episode("phase-template", "2026-08-11T14:00:00Z")],
    )
    run(root_dir=root)
    template = _read_jsonl(root / CAMPAIGNS_PATH)[0]
    cases = (
        ("2026-08-11T13:23:59.999999Z", "retrospective_context"),
        ("2026-08-11T13:24:00Z", "prospective_after_rule_freeze"),
        ("2026-08-11T13:24:00.000001Z", "prospective_after_rule_freeze"),
    )
    rows = []
    for clock, phase in cases:
        row = copy.deepcopy(template)
        row["formed_at"] = clock
        row["members"][-1]["available_at"] = clock
        row["descriptive"]["first_available_at"] = clock
        row["descriptive"]["last_available_at"] = clock
        row["evidence_phase"] = phase
        campaign_engine.validate_campaign(row)
        rows.append(row)

    mislabeled = copy.deepcopy(rows[0])
    mislabeled["evidence_phase"] = "prospective_after_rule_freeze"
    with pytest.raises(CampaignContractError, match="evidence phase"):
        campaign_engine.validate_campaign(mislabeled)


def test_grouping_never_merges_across_any_exact_contract_dimension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    episodes = [
        _episode("base", "2026-08-10T14:00:00Z"),
        _episode("session", "2026-08-11T14:00:00Z"),
        _episode("ticker", "2026-08-10T14:01:00Z", ticker="AAPL"),
        _episode("right", "2026-08-10T14:02:00Z", right="P"),
        _episode(
            "expiration",
            "2026-08-10T14:03:00Z",
            expiration="2026-08-28",
        ),
        _episode("strike", "2026-08-10T14:04:00Z", strike=230.0),
    ]
    root = _root(tmp_path, episodes)
    run(root_dir=root)
    campaigns = _read_jsonl(root / CAMPAIGNS_PATH)
    assert len(campaigns) == 6
    assert {row["descriptive"]["member_count"] for row in campaigns} == {1}
    assert len(
        {
            (
                row["group"]["session_date"],
                row["group"]["ticker"],
                row["group"]["right"],
                row["group"]["expiration"],
                row["group"]["strike_key"],
            )
            for row in campaigns
        }
    ) == 6


def test_grouping_preserves_adjacent_integer_strikes_above_float_safe_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    strikes = (9_007_199_254_740_992, 9_007_199_254_740_993)
    episodes = [
        _episode(
            f"high-strike-{index}",
            f"2026-08-10T14:0{index}:00Z",
            strike=strike,
        )
        for index, strike in enumerate(strikes)
    ]
    root = _root(tmp_path, episodes)
    run(root_dir=root)
    campaigns = _read_jsonl(root / CAMPAIGNS_PATH)
    assert len(campaigns) == 2
    assert {row["group"]["strike"] for row in campaigns} == set(strikes)
    assert {row["group"]["strike_key"] for row in campaigns} == {
        str(strike) for strike in strikes
    }
    assert len({row["campaign_id"] for row in campaigns}) == 2


def test_legacy_threshold_rows_are_byte_frozen_and_episode_builder_is_decoupled() -> None:
    legacy = ROOT / "data/options_signal_episode/campaigns.jsonl"
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == LEGACY_CAMPAIGN_SHA256
    assert len(legacy.read_text().splitlines()) == 8
    builder = (ROOT / "scripts/build_options_signal_episode.py").read_text()
    for forbidden in ("derive_campaigns", "append_campaigns", "CAMPAIGN_REL"):
        assert forbidden not in builder


def test_source_episode_authority_must_remain_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    unsafe = _episode("unsafe", "2026-08-10T14:02:00Z")
    unsafe["decision"]["authority"]["may_rank"] = True
    root = _root(tmp_path, [unsafe])
    with pytest.raises(CampaignContractError, match="may_rank"):
        run(root_dir=root)
