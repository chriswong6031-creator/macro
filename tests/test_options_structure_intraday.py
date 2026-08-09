from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pandas as pd
import pytest

from engine.options_structure_intraday import (
    CONVEX_PROFILE,
    MAX_PROJECTED_CONTRACTS,
    PROPHET_PROFILE,
    OptionsStructureIntradayError,
    build_packet,
    canonical_json_bytes,
    construct_occ_symbol,
    strict_json_object,
)
from engine.prophet_bridge import resolve_option


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads(
    (ROOT / "contracts" / "options" / "options.contract_eligibility.v1.schema.json").read_text()
)
SESSION = "2026-08-07"
BUCKET = "16:00"
OBSERVED = "2026-08-07T20:02:00Z"


def _chain() -> pd.DataFrame:
    rows = [
        # Actual Prophet primary target; delta .58 is closest to +.60.
        ("2026-09-18", 105.0, "C", 4.8, 5.2, 0.58, 0.24),
        # Convex OTM call.
        ("2026-09-18", 110.0, "C", 2.8, 3.2, 0.30, 0.27),
        # Convex OTM put.
        ("2026-09-18", 90.0, "P", 2.9, 3.1, -0.30, 0.28),
        # Long-dated convex vehicle; DTE is not confused with intended hold.
        ("2026-11-20", 115.0, "C", 4.9, 5.1, 0.20, 0.31),
    ]
    frame = pd.DataFrame(rows, columns=[
        "expiration", "strike", "right", "bid", "ask", "delta", "implied_vol",
    ])
    frame["root"] = "TST"
    frame["expiration"] = pd.to_datetime(frame["expiration"])
    frame["snapshot_ts"] = pd.to_datetime(["2026-08-07T16:00:00"] * len(frame))
    frame["snapshot_bucket"] = BUCKET
    frame["source"] = "chain_snapshot"
    frame["underlying_price"] = 100.0
    frame["theta"] = -0.04
    frame["vega"] = 0.11
    frame["rho"] = 0.02
    frame["epsilon"] = 0.01
    frame["lambda"] = 4.2
    frame["iv_error"] = 0.0
    frame["gamma"] = [0.03, float("nan"), 0.02, 0.01]
    frame["vanna"] = 0.1
    frame["charm"] = -0.2
    frame["vomma"] = 1.5
    frame["veta"] = 2.5
    return frame


def _oi() -> pd.DataFrame:
    frame = _chain()[["root", "expiration", "strike", "right"]].copy()
    frame["snapshot_ts"] = pd.to_datetime(["2026-08-07T06:30:00"] * len(frame))
    frame["open_interest"] = [500, 1000, 700, 300]
    frame["source"] = "chain_snapshot"
    return frame


def _request() -> dict:
    # 2026-08-07 + 25 + 15 = 2026-09-16; next monthly is 2026-09-18.
    return {"direction": "BULL", "clock_date": SESSION, "horizon_days": 25, "entry": 100.0}


def _packet(**changes):
    kwargs = {
        "root": "TST",
        "session_date": SESSION,
        "snapshot_bucket": BUCKET,
        "observed_at": OBSERVED,
        "available_at": OBSERVED,
        "cadence_minutes": 15,
        "prophet_request": _request(),
    }
    kwargs.update(changes)
    return build_packet(_chain(), _oi(), **kwargs)


def _large_convex_universe(count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    seed = _chain().iloc[[3]].copy()
    chain = seed.loc[seed.index.repeat(count)].reset_index(drop=True)
    chain["strike"] = [105.0 + (index / 2000.0) for index in range(count)]
    oi = chain[["root", "expiration", "strike", "right"]].copy()
    oi["snapshot_ts"] = pd.Timestamp("2026-08-07T06:30:00")
    oi["open_interest"] = 100
    oi["source"] = "chain_snapshot"
    return chain, oi


def _schema_errors(packet: dict) -> list[str]:
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(packet)]


def _all_authority_blocks(value):
    if isinstance(value, dict):
        if set(value) == {
            "rank_authority", "gate_authority", "sizing_authority",
            "issue_authority", "trade_authority", "prophet_authority",
        }:
            yield value
        for child in value.values():
            yield from _all_authority_blocks(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_authority_blocks(child)


def test_packet_is_schema_valid_strict_deterministic_and_authority_false() -> None:
    first = _packet()
    second = _packet()
    assert _schema_errors(first) == []
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["packet_id"] == second["packet_id"]
    assert b"NaN" not in canonical_json_bytes(first)
    assert all(not any(block.values()) for block in _all_authority_blocks(first))
    assert first["limitations"] == {
        "bid_ask_depth": "unavailable",
        "capacity_assessed": False,
        "underlying_selection": "not_in_scope",
        "execution_quote_polling": "not_in_scope",
        "issuance": "not_authorized",
    }
    # Source row order is intentionally bound because legacy Prophet's primary
    # idxmin tie law is first-row-sensitive. Same source/retry, not arbitrary
    # source shuffling, is the deterministic-byte contract.
    shuffled = build_packet(
        _chain().sample(frac=1, random_state=7).reset_index(drop=True),
        _oi().sample(frac=1, random_state=9).reset_index(drop=True),
        root="TST",
        session_date=SESSION,
        snapshot_bucket=BUCKET,
        observed_at=OBSERVED,
        available_at=OBSERVED,
        cadence_minutes=15,
        prophet_request=_request(),
    )
    assert first["source_receipt"]["chain"]["bucket_sha256"] != shuffled["source_receipt"]["chain"]["bucket_sha256"]


def test_profiles_are_separate_and_convex_filter_keeps_long_dated_contract() -> None:
    packet = _packet()
    prophet = packet["profiles"][PROPHET_PROFILE]
    convex = packet["profiles"][CONVEX_PROFILE]
    assert prophet["selection"]["mode"] == "primary_delta60"
    prophet_contract = next(
        row for row in packet["contracts"] if row["contract_id"] == prophet["selection"]["contract_id"]
    )
    assert prophet_contract["contract"]["strike"] == 105.0
    convex_contracts = {
        row["contract_id"]: row
        for row in packet["contracts"]
        if CONVEX_PROFILE in row["profile_matches"]
    }
    assert {row["contract"]["strike"] for row in convex_contracts.values()} == {90.0, 110.0, 115.0}
    long_dated = next(row for row in convex_contracts.values() if row["contract"]["strike"] == 115.0)
    assert long_dated["dte_calendar_days"] == 105
    assert long_dated["implied_vol"] == pytest.approx(0.31)
    assert long_dated["volume"] == {
        "value": None,
        "available": False,
        "source_note": "volume_not_captured_by_chain_snapshot",
    }
    assert long_dated["profile_evaluations"][CONVEX_PROFILE] == {
        "matched": True,
        "passed_filters": [
            "browser_quote_fresh_valid",
            "dte_30_180",
            "otm_5_20_pct",
            "absolute_delta_0_10_0_45",
            "spread_pct_lte_15",
            "prior_session_oi_gte_100",
        ],
        "failed_filters": [],
    }
    assert convex["definition"]["research_only_not_reconstructed_competitor_rule"] is True
    assert convex["definition"]["ranking_inputs"] == []
    ordered_spreads = [
        convex_contracts[contract_id]["quote"]["spread_pct"]
        for contract_id in convex["eligible_contract_ids"]
    ]
    assert ordered_spreads == sorted(ordered_spreads)
    # The packet's identity order is not a blended/cross-profile recommendation.
    assert [row["contract_id"] for row in packet["contracts"]] == sorted(
        row["contract_id"] for row in packet["contracts"]
    )


def test_projected_contract_cap_matches_schema_at_exact_boundary() -> None:
    assert SCHEMA["properties"]["contracts"]["maxItems"] == MAX_PROJECTED_CONTRACTS
    chain, oi = _large_convex_universe(MAX_PROJECTED_CONTRACTS)
    packet = build_packet(
        chain, oi, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED,
    )
    assert len(packet["contracts"]) == MAX_PROJECTED_CONTRACTS

    chain, oi = _large_convex_universe(MAX_PROJECTED_CONTRACTS + 1)
    with pytest.raises(OptionsStructureIntradayError, match="projected contract count exceeds 20000"):
        build_packet(
            chain, oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


def test_prophet_primary_selection_matches_actual_resolver(monkeypatch, tmp_path) -> None:
    greeks_dir = tmp_path / "greeks" / "TST"
    greeks_dir.mkdir(parents=True)
    greeks = _chain().rename(columns={"snapshot_ts": "date"})
    greeks["date"] = pd.Timestamp(SESSION)
    greeks[[
        "date", "expiration", "right", "delta", "strike", "bid", "ask", "implied_vol",
    ]].to_parquet(greeks_dir / "2026.parquet", index=False)
    monkeypatch.setattr("engine.prophet_bridge._structure_receipt", lambda *args, **kwargs: None)
    actual = resolve_option(
        ticker="TST",
        direction="BULL",
        entry=100.0,
        horizon_days=25,
        signal_date=SESSION,
        thetadata_store=str(tmp_path),
        asof=SESSION,
        clock_date=SESSION,
    )
    packet = _packet()
    selected_id = packet["profiles"][PROPHET_PROFILE]["selection"]["contract_id"]
    selected = next(row for row in packet["contracts"] if row["contract_id"] == selected_id)
    assert actual is not None
    assert actual["note"] == "delta-targeted (0.60)"
    assert (actual["expiry"], actual["right"], actual["strike"]) == (
        selected["contract"]["expiration"],
        selected["contract"]["right"],
        selected["contract"]["strike"],
    )


def test_prophet_primary_tie_preserves_actual_first_source_row_idxmin(monkeypatch, tmp_path) -> None:
    chain = _chain()
    target = chain[
        chain["expiration"].eq(pd.Timestamp("2026-09-18"))
        & chain["right"].eq("C")
    ].copy()
    target["delta"] = 0.55
    target = target.sort_values("strike", ascending=False)
    remainder = chain.drop(index=target.index)
    chain = pd.concat([target, remainder], ignore_index=True)

    greeks_dir = tmp_path / "greeks" / "TST"
    greeks_dir.mkdir(parents=True)
    greeks = chain.rename(columns={"snapshot_ts": "date"})
    greeks["date"] = pd.Timestamp(SESSION)
    greeks[[
        "date", "expiration", "right", "delta", "strike", "bid", "ask", "implied_vol",
    ]].to_parquet(greeks_dir / "2026.parquet", index=False)
    monkeypatch.setattr("engine.prophet_bridge._structure_receipt", lambda *args, **kwargs: None)
    actual = resolve_option(
        ticker="TST",
        direction="BULL",
        entry=100.0,
        horizon_days=25,
        signal_date=SESSION,
        thetadata_store=str(tmp_path),
        asof=SESSION,
        clock_date=SESSION,
    )
    packet = build_packet(
        chain, _oi(), root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    profile = packet["profiles"][PROPHET_PROFILE]
    selected = next(
        row for row in packet["contracts"]
        if row["contract_id"] == profile["selection"]["contract_id"]
    )
    assert actual is not None
    assert actual["strike"] == 110.0
    assert selected["contract"]["strike"] == actual["strike"]
    assert profile["definition"]["primary_tie_semantics"] == (
        "first source row, matching pandas Series.idxmin"
    )


def test_prophet_resolves_then_abstains_instead_of_substituting_quote() -> None:
    chain = _chain()
    target_calls = (
        chain["expiration"].eq(pd.Timestamp("2026-09-18"))
        & chain["right"].eq("C")
    )
    chain.loc[target_calls, "delta"] = [0.60, 0.59]
    chain.loc[chain["strike"].eq(105.0), "bid"] = 0.0
    packet = build_packet(
        chain, _oi(), root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    profile = packet["profiles"][PROPHET_PROFILE]
    assert profile["status"] == "abstain"
    assert profile["abstention_reason"] == "LEGACY_CANDIDATE_NOT_BROWSER_ELIGIBLE"
    assert profile["eligible_contract_ids"] == []
    assert profile["selection"] is None


def test_prophet_fallback_is_labelled_and_deterministic_not_row_ordered() -> None:
    chain = _chain()
    chain.loc[chain["expiration"].eq(pd.Timestamp("2026-09-18")), "delta"] = float("nan")
    # Put the farther call first; deterministic fallback must still pick 105.
    chain = chain.sort_values("strike", ascending=False).reset_index(drop=True)
    packet = build_packet(
        chain,
        _oi(),
        root="TST",
        session_date=SESSION,
        snapshot_bucket=BUCKET,
        observed_at=OBSERVED,
        prophet_request=_request(),
    )
    profile = packet["profiles"][PROPHET_PROFILE]
    selected = next(row for row in packet["contracts"] if row["contract_id"] == profile["selection"]["contract_id"])
    assert profile["selection"]["mode"] == "fallback_closest_otm_deterministic"
    assert selected["contract"]["strike"] == 105.0
    assert "row order" in profile["definition"]["legacy_fallback_disclosure"]


def test_missing_prophet_context_does_not_invent_a_legacy_horizon() -> None:
    packet = _packet(prophet_request=None)
    profile = packet["profiles"][PROPHET_PROFILE]
    assert profile["status"] == "context_required"
    assert profile["eligible_contract_ids"] == []
    assert profile["selection"] is None


def test_prophet_plan_clock_is_point_in_time_bound_to_packet_session() -> None:
    same = _packet(prophet_request={**_request(), "clock_date": SESSION})
    assert same["profiles"][PROPHET_PROFILE]["request"]["clock_date"] == SESSION

    prior = _packet(prophet_request={**_request(), "clock_date": "2026-08-06"})
    assert prior["profiles"][PROPHET_PROFILE]["request"]["clock_date"] == "2026-08-06"

    with pytest.raises(OptionsStructureIntradayError, match="later than the packet session"):
        _packet(prophet_request={**_request(), "clock_date": "2026-08-10"})
    with pytest.raises(OptionsStructureIntradayError, match="real NYSE session"):
        _packet(prophet_request={**_request(), "clock_date": "2026-07-03"})


def test_optional_source_volume_is_exposed_but_never_used_for_ranking() -> None:
    chain = _chain()
    chain["volume"] = [40, 165, 210, 75]
    packet = build_packet(
        chain,
        _oi(),
        root="TST",
        session_date=SESSION,
        snapshot_bucket=BUCKET,
        observed_at=OBSERVED,
        prophet_request=_request(),
    )
    assert _schema_errors(packet) == []
    contract = next(row for row in packet["contracts"] if row["contract"]["strike"] == 110.0)
    assert contract["volume"] == {"value": 165, "available": True, "source_note": "chain_snapshot"}
    assert packet["profiles"][CONVEX_PROFILE]["definition"]["ranking_inputs"] == []


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("bid", 0.0, "ZERO_OR_MISSING_QUOTE"),
        ("ask", 2.0, "CROSSED_QUOTE"),
        ("snapshot_ts", pd.Timestamp("2026-08-07T15:30:00"), "QUOTE_STALE"),
    ],
)
def test_zero_crossed_and_stale_quotes_never_enter_a_profile(field, value, reason) -> None:
    chain = _chain()
    chain[field] = value
    if field == "ask":
        chain["bid"] = 3.0
    packet = build_packet(
        chain,
        _oi(),
        root="TST",
        session_date=SESSION,
        snapshot_bucket=BUCKET,
        observed_at=OBSERVED,
        prophet_request=_request(),
    )
    assert packet["contracts"] == []
    assert packet["coverage"]["browser_eligible_contract_count"] == 0
    assert packet["coverage"]["quote_rejection_counts"][reason] == len(chain)


def test_early_close_window_is_real_and_regular_close_is_rejected() -> None:
    chain = _chain()
    chain["expiration"] = pd.Timestamp("2027-01-15")
    chain["snapshot_bucket"] = "13:00"
    chain["snapshot_ts"] = pd.Timestamp("2026-11-27T13:00:00")
    oi = _oi()
    oi["expiration"] = pd.Timestamp("2027-01-15")
    oi["snapshot_ts"] = pd.Timestamp("2026-11-27T06:30:00")
    packet = build_packet(
        chain,
        oi,
        root="TST",
        session_date="2026-11-27",
        snapshot_bucket="13:00",
        observed_at="2026-11-27T18:02:00Z",
        prophet_request=None,
    )
    assert packet["session"]["early_close"] is True
    assert packet["session"]["close_at"] == "2026-11-27T18:00:00.000000Z"
    with pytest.raises(OptionsStructureIntradayError, match="outside NYSE window"):
        build_packet(
            chain.assign(snapshot_bucket="13:15"),
            oi,
            root="TST",
            session_date="2026-11-27",
            snapshot_bucket="13:15",
            observed_at="2026-11-27T18:02:00Z",
        )


def test_holiday_bucket_and_malformed_or_duplicate_sources_fail_closed() -> None:
    with pytest.raises(OptionsStructureIntradayError, match="not an NYSE session"):
        build_packet(
            _chain(), _oi(), root="TST", session_date="2026-12-25",
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )
    with pytest.raises(OptionsStructureIntradayError, match="missing columns"):
        build_packet(
            _chain().drop(columns=["bid"]), _oi(), root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )
    duplicated = pd.concat([_chain(), _chain().iloc[[0]]], ignore_index=True)
    with pytest.raises(OptionsStructureIntradayError, match="duplicate chain contract"):
        build_packet(
            duplicated, _oi(), root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


@pytest.mark.parametrize(
    ("source", "field", "value"),
    [
        ("chain", "root", None),
        ("chain", "root", True),
        ("chain", "root", "tst"),
        ("chain", "right", None),
        ("chain", "right", True),
        ("chain", "right", "c"),
        ("chain", "expiration", "2026-09-18JUNK"),
        ("chain", "strike", None),
        ("chain", "strike", True),
        ("oi", "root", None),
        ("oi", "root", True),
        ("oi", "right", "c"),
        ("oi", "expiration", "2026-09-18JUNK"),
        ("oi", "strike", False),
    ],
)
def test_source_contract_identity_is_exact_and_never_relabelled(source, field, value) -> None:
    chain = _chain()
    oi = _oi()
    frame = chain if source == "chain" else oi
    frame[field] = frame[field].astype(object)
    frame.at[0, field] = value
    with pytest.raises(OptionsStructureIntradayError):
        build_packet(
            chain, oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


def test_dates_and_builder_clocks_are_exact_not_prefix_parsed() -> None:
    with pytest.raises(OptionsStructureIntradayError, match="invalid session_date"):
        build_packet(
            _chain(), _oi(), root="TST", session_date=f"{SESSION}JUNK",
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )
    with pytest.raises(OptionsStructureIntradayError, match="timezone-aware"):
        _packet(observed_at="2026-08-07T20:02:00", available_at="2026-08-07T20:02:00")


def test_microsecond_timestamp_identity_is_preserved_end_to_end() -> None:
    packets = []
    for fraction in ("000100", "000900"):
        chain = _chain()
        chain["snapshot_ts"] = pd.Timestamp(f"2026-08-07T16:00:00.{fraction}")
        oi = _oi()
        oi["snapshot_ts"] = pd.Timestamp(f"2026-08-07T06:30:00.{fraction}")
        packet = build_packet(
            chain,
            oi,
            root="TST",
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            observed_at=f"2026-08-07T20:02:00.{fraction}Z",
            available_at=f"2026-08-07T20:02:00.{fraction}Z",
            prophet_request=_request(),
        )
        assert _schema_errors(packet) == []
        assert packet["clocks"]["vendor_snapshot_ts_min"] == (
            f"2026-08-07T20:00:00.{fraction}Z"
        )
        assert packet["clocks"]["builder_observed_at"] == (
            f"2026-08-07T20:02:00.{fraction}Z"
        )
        assert packet["clocks"]["available_at"] == (
            f"2026-08-07T20:02:00.{fraction}Z"
        )
        assert all(
            row["quote"]["snapshot_ts"] == f"2026-08-07T20:00:00.{fraction}Z"
            for row in packet["contracts"]
        )
        assert all(
            row["open_interest"]["snapshot_ts"]
            == f"2026-08-07T10:30:00.{fraction}Z"
            for row in packet["contracts"]
        )
        packets.append(packet)

    first, second = packets
    assert first["source_receipt"]["chain"]["bucket_sha256"] != second[
        "source_receipt"
    ]["chain"]["bucket_sha256"]
    assert first["source_receipt"]["prior_session_open_interest"][
        "projection_sha256"
    ] != second["source_receipt"]["prior_session_open_interest"]["projection_sha256"]
    assert first["packet_id"] != second["packet_id"]
    assert canonical_json_bytes(first) != canonical_json_bytes(second)


def test_second_precision_normalizes_to_exact_six_digit_utc() -> None:
    packet = _packet()
    assert packet["session"]["open_at"].endswith(".000000Z")
    assert packet["session"]["close_at"].endswith(".000000Z")
    assert packet["session"]["bucket_at"].endswith(".000000Z")
    assert packet["clocks"]["builder_observed_at"].endswith(".000000Z")
    assert packet["clocks"]["available_at"].endswith(".000000Z")
    assert all(
        row["quote"]["snapshot_ts"].endswith(".000000Z")
        for row in packet["contracts"]
    )
    assert all(
        row["open_interest"]["snapshot_ts"].endswith(".000000Z")
        for row in packet["contracts"]
    )


@pytest.mark.parametrize("clock_source", ["chain", "oi", "observed", "available"])
def test_sub_microsecond_timestamps_fail_closed_without_truncation(clock_source) -> None:
    chain = _chain()
    oi = _oi()
    observed = OBSERVED
    available = OBSERVED
    if clock_source == "chain":
        chain["snapshot_ts"] = pd.Timestamp("2026-08-07T16:00:00.000000100")
    elif clock_source == "oi":
        oi["snapshot_ts"] = pd.Timestamp("2026-08-07T06:30:00.000000100")
    elif clock_source == "observed":
        observed = "2026-08-07T20:02:00.000000100Z"
    else:
        available = "2026-08-07T20:02:00.000000100Z"
    with pytest.raises(OptionsStructureIntradayError, match="sub-microsecond"):
        build_packet(
            chain,
            oi,
            root="TST",
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            observed_at=observed,
            available_at=available,
            prophet_request=_request(),
        )


def test_exact_strike_identity_has_no_three_decimal_collision() -> None:
    chain = _chain().iloc[:2].copy()
    chain["expiration"] = pd.Timestamp("2026-09-18")
    chain["strike"] = [110.0004, 110.0005]
    chain["delta"] = [0.30, 0.31]
    oi = chain[["root", "expiration", "strike", "right"]].copy()
    oi["snapshot_ts"] = pd.Timestamp("2026-08-07T06:30:00")
    oi["open_interest"] = [1000, 1001]
    oi["source"] = "chain_snapshot"
    packet = build_packet(
        chain, oi, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    assert _schema_errors(packet) == []
    contracts = packet["contracts"]
    assert {row["contract"]["strike_canonical"] for row in contracts} == {
        "110.0004", "110.0005",
    }
    assert len({row["contract_id"] for row in contracts}) == 2
    assert all(row["contract"]["occ_symbol"] is None for row in contracts)

    duplicate = chain.copy()
    duplicate["strike"] = duplicate["strike"].astype(object)
    duplicate.at[1, "strike"] = Decimal("110.000400")
    with pytest.raises(OptionsStructureIntradayError, match="duplicate chain contract"):
        build_packet(
            duplicate, oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


def test_oi_and_volume_preserve_exact_integers_above_two_to_the_53() -> None:
    exact = 2**53 + 1
    chain = _chain()
    chain["volume"] = [exact] * len(chain)
    oi = _oi()
    oi["open_interest"] = [exact] * len(oi)
    packet = build_packet(
        chain, oi, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    assert packet["contracts"]
    assert all(row["volume"]["value"] == exact for row in packet["contracts"])
    assert all(row["open_interest"]["value"] == exact for row in packet["contracts"])
    assert str(exact).encode() in canonical_json_bytes(packet)

    chain["volume"] = float(2**53 + 2)
    with pytest.raises(OptionsStructureIntradayError, match=r"ambiguous 2\^53 boundary"):
        build_packet(
            chain, oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


def test_nullable_integer_float_parquet_roundtrip_is_accepted_when_unambiguous(tmp_path) -> None:
    chain = _chain()
    chain["volume"] = [None, 100, 300, None]
    oi = _oi()
    oi["open_interest"] = [None, 100, 300, None]
    chain_path = tmp_path / "chain.parquet"
    oi_path = tmp_path / "oi.parquet"
    chain.to_parquet(chain_path, index=False)
    oi.to_parquet(oi_path, index=False)
    roundtrip_chain = pd.read_parquet(chain_path)
    roundtrip_oi = pd.read_parquet(oi_path)
    assert str(roundtrip_chain["volume"].dtype) == "float64"
    assert str(roundtrip_oi["open_interest"].dtype) == "float64"

    packet = build_packet(
        roundtrip_chain, roundtrip_oi, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    by_strike = {row["contract"]["strike"]: row for row in packet["contracts"]}
    assert by_strike[105.0]["volume"]["value"] is None
    assert by_strike[105.0]["open_interest"]["value"] is None
    assert by_strike[110.0]["volume"]["value"] == 100
    assert by_strike[110.0]["open_interest"]["value"] == 100


def test_nullable_float_rounding_of_two_to_the_53_plus_one_fails_closed(tmp_path) -> None:
    chain = _chain()
    chain["volume"] = [2**53 + 1, None, None, None]
    oi = _oi()
    oi["open_interest"] = [2**53 + 1, None, None, None]
    chain_path = tmp_path / "chain.parquet"
    oi_path = tmp_path / "oi.parquet"
    chain.to_parquet(chain_path, index=False)
    oi.to_parquet(oi_path, index=False)
    roundtrip_chain = pd.read_parquet(chain_path)
    roundtrip_oi = pd.read_parquet(oi_path)
    # The +1 lexical identity has already collapsed to the 2^53 float. The
    # publisher cannot distinguish that from a literal 2^53 float, so the
    # boundary itself is intentionally rejected for floating source values.
    assert roundtrip_chain.loc[0, "volume"] == float(2**53)
    assert roundtrip_oi.loc[0, "open_interest"] == float(2**53)
    with pytest.raises(OptionsStructureIntradayError, match=r"ambiguous 2\^53 boundary"):
        build_packet(
            roundtrip_chain, roundtrip_oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


def test_float_integer_boundary_and_exact_nonfloat_boundary_are_explicit() -> None:
    chain = _chain()
    chain["volume"] = [float(2**53 - 1)] * len(chain)
    oi = _oi()
    oi["open_interest"] = [float(2**53 - 1)] * len(oi)
    packet = build_packet(
        chain, oi, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    assert all(
        row["volume"]["value"] == 2**53 - 1
        and row["open_interest"]["value"] == 2**53 - 1
        for row in packet["contracts"]
    )

    chain["volume"] = [str(2**53), str(2**53 + 1), str(2**53), str(2**53 + 1)]
    oi["open_interest"] = [2**53, 2**53 + 1, 2**53, 2**53 + 1]
    packet = build_packet(
        chain, oi, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    assert {row["volume"]["value"] for row in packet["contracts"]} == {
        2**53, 2**53 + 1,
    }
    assert {row["open_interest"]["value"] for row in packet["contracts"]} == {
        2**53, 2**53 + 1,
    }

    chain["volume"] = float(2**53)
    with pytest.raises(OptionsStructureIntradayError, match=r"ambiguous 2\^53 boundary"):
        build_packet(
            chain, oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (-1.0, "non-negative"),
        (1.5, "exact integer"),
        (float("inf"), "non-finite"),
        (True, "invalid option volume"),
    ],
)
def test_volume_rejects_noninteger_nonfinite_negative_and_boolean_values(value, reason) -> None:
    chain = _chain()
    chain["volume"] = value
    with pytest.raises(OptionsStructureIntradayError, match=reason):
        build_packet(
            chain, _oi(), root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


@pytest.mark.parametrize(
    "stamp",
    [
        pd.Timestamp("2026-08-06T16:00:00"),
        pd.Timestamp("2026-08-07T09:31:00"),
        pd.Timestamp("2026-08-10T06:30:00"),
    ],
)
def test_oi_availability_clock_never_crosses_session_or_open(stamp) -> None:
    oi = _oi()
    oi["snapshot_ts"] = stamp
    with pytest.raises(OptionsStructureIntradayError, match="OI snapshot"):
        build_packet(
            _chain(), oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


def test_prior_day_stamp_is_retained_for_raw_expired_oi_but_rejected_for_live_oi() -> None:
    expired = _oi().iloc[[0]].copy()
    expired["expiration"] = pd.Timestamp("2026-08-06")
    expired["snapshot_ts"] = pd.Timestamp("2026-08-06T06:30:00")
    oi_with_expired = pd.concat([_oi(), expired], ignore_index=True)
    packet = build_packet(
        _chain(), oi_with_expired, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    receipt = packet["source_receipt"]["prior_session_open_interest"]
    assert receipt["row_count"] == 5
    assert receipt["usable_row_count"] == 4
    assert receipt["expired_excluded_row_count"] == 1
    assert receipt["projection_sha256"] != _packet()["source_receipt"][
        "prior_session_open_interest"
    ]["projection_sha256"]

    live_wrong_day = _oi()
    live_wrong_day.loc[0, "snapshot_ts"] = pd.Timestamp("2026-08-06T06:30:00")
    with pytest.raises(OptionsStructureIntradayError, match="OI snapshot date"):
        build_packet(
            _chain(), live_wrong_day, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )

    expired_future = expired.copy()
    expired_future["snapshot_ts"] = pd.Timestamp("2030-01-02T06:30:00")
    with pytest.raises(OptionsStructureIntradayError, match="after builder observation"):
        build_packet(
            _chain(), pd.concat([_oi(), expired_future], ignore_index=True),
            root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )

    expired_after_open = expired.copy()
    expired_after_open["snapshot_ts"] = pd.Timestamp("2026-08-07T15:00:00")
    with pytest.raises(OptionsStructureIntradayError, match="after the NYSE session open"):
        build_packet(
            _chain(), pd.concat([_oi(), expired_after_open], ignore_index=True),
            root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


@pytest.mark.parametrize("vintage", ["2026-08-07", "2026-07-03", "2026-08-10"])
def test_asserted_oi_vintage_must_be_the_immediate_prior_real_session(vintage) -> None:
    oi = _oi()
    oi["vintage_session"] = vintage
    with pytest.raises(OptionsStructureIntradayError, match="prior NYSE session"):
        build_packet(
            _chain(), oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )


def test_oi_vintage_derivation_skips_exchange_holiday() -> None:
    chain = _chain()
    chain["snapshot_ts"] = pd.Timestamp("2026-07-06T16:00:00")
    oi = _oi()
    oi["snapshot_ts"] = pd.Timestamp("2026-07-06T06:30:00")
    oi["vintage_session"] = "2026-07-02"
    packet = build_packet(
        chain, oi, root="TST", session_date="2026-07-06",
        snapshot_bucket=BUCKET, observed_at="2026-07-06T20:02:00Z",
    )
    oi_receipt = packet["source_receipt"]["prior_session_open_interest"]
    assert oi_receipt["vintage_session"] == "2026-07-02"
    assert oi_receipt["vintage_derivation"] == "previous_real_nyse_session"
    assert all(
        row["open_interest"]["vintage_session"] == "2026-07-02"
        for row in packet["contracts"]
    )


def test_oi_vintage_occ_and_strict_duplicate_json_contract() -> None:
    packet = _packet()
    assert all(row["open_interest"]["vintage_session"] == "2026-08-06" for row in packet["contracts"])
    assert construct_occ_symbol("TST", date(2026, 9, 18), "C", 105.0) == "TST   260918C00105000"
    assert construct_occ_symbol("BRK.B", date(2026, 9, 18), "C", 105.0) is None
    with pytest.raises(OptionsStructureIntradayError, match="duplicate JSON key"):
        strict_json_object(b'{"root":"TST","root":"BAD"}')
    with pytest.raises(OptionsStructureIntradayError, match="non-finite"):
        strict_json_object(b'{"value":NaN}')
    fractional_oi = _oi()
    fractional_oi["open_interest"] = fractional_oi["open_interest"].astype(float)
    fractional_oi.loc[0, "open_interest"] = 100.5
    with pytest.raises(OptionsStructureIntradayError, match="exact integer"):
        build_packet(
            _chain(), fractional_oi, root="TST", session_date=SESSION,
            snapshot_bucket=BUCKET, observed_at=OBSERVED,
        )
    float_oi = _oi()
    float_oi["open_interest"] = float_oi["open_interest"].astype(float)
    packet = build_packet(
        _chain(), float_oi, root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED,
    )
    assert all(isinstance(row["open_interest"]["value"], int) for row in packet["contracts"])


def test_available_at_cannot_precede_observation() -> None:
    with pytest.raises(OptionsStructureIntradayError, match="precedes"):
        _packet(available_at="2026-08-07T20:01:59Z")


def test_quote_freshness_is_measured_at_first_usable_availability_boundary() -> None:
    chain = _chain()
    chain["snapshot_bucket"] = "15:45"
    chain["snapshot_ts"] = pd.Timestamp("2026-08-07T15:45:00")
    common = {
        "root": "TST",
        "session_date": SESSION,
        "snapshot_bucket": "15:45",
        "observed_at": "2026-08-07T19:45:00Z",
        "prophet_request": _request(),
    }

    at_boundary = build_packet(
        chain,
        _oi(),
        available_at="2026-08-07T20:05:00Z",
        **common,
    )
    assert at_boundary["clocks"]["builder_observed_at"] == "2026-08-07T19:45:00.000000Z"
    assert at_boundary["clocks"]["available_at"] == "2026-08-07T20:05:00.000000Z"
    assert at_boundary["contracts"]
    assert all(row["quote"]["age_minutes"] == 20.0 for row in at_boundary["contracts"])
    assert at_boundary["profiles"][PROPHET_PROFILE]["status"] == "selected"
    assert at_boundary["profiles"][CONVEX_PROFILE]["status"] == "eligible"

    after_boundary = build_packet(
        chain,
        _oi(),
        available_at="2026-08-07T20:05:00.000001Z",
        **common,
    )
    assert after_boundary["coverage"]["browser_eligible_contract_count"] == 0
    assert after_boundary["coverage"]["quote_rejection_counts"] == {
        "QUOTE_STALE": len(chain)
    }
    assert after_boundary["contracts"] == []
    assert after_boundary["profiles"][PROPHET_PROFILE]["status"] == "abstain"
    assert after_boundary["profiles"][CONVEX_PROFILE]["status"] == "abstain"


def test_cadence_cannot_silently_drift_from_the_15_minute_contract() -> None:
    with pytest.raises(OptionsStructureIntradayError, match="must be 15"):
        _packet(cadence_minutes=5)


@pytest.mark.parametrize("cadence", [15.0, "15", True])
def test_cadence_control_is_integral_not_coerced(cadence) -> None:
    with pytest.raises(OptionsStructureIntradayError, match="must be an integer"):
        _packet(cadence_minutes=cadence)


@pytest.mark.parametrize("horizon", [25.9, "25", True, None])
def test_prophet_horizon_control_is_integral_not_coerced(horizon) -> None:
    request = {**_request(), "horizon_days": horizon}
    with pytest.raises(OptionsStructureIntradayError, match="must be an integer"):
        _packet(prophet_request=request)


@pytest.mark.parametrize(
    "plan_context",
    [
        {**_request(), "direction": "bull"},
        {**_request(), "entry": "100"},
        {**_request(), "entry": True},
    ],
)
def test_prophet_control_identity_is_not_coerced(plan_context) -> None:
    with pytest.raises(OptionsStructureIntradayError):
        _packet(prophet_request=plan_context)


def test_bucket_and_builder_clock_causality_fail_closed() -> None:
    with pytest.raises(OptionsStructureIntradayError, match="invalid snapshot bucket"):
        _packet(snapshot_bucket="16:07")
    with pytest.raises(OptionsStructureIntradayError, match="precedes the requested bucket"):
        _packet(observed_at="2026-08-07T19:59:00Z")
    with pytest.raises(OptionsStructureIntradayError, match="outside the causal session window"):
        _packet(
            observed_at="2026-08-10T20:02:00Z",
            available_at="2026-08-10T20:02:00Z",
        )


def test_nonpositive_spot_can_never_survive_profile_projection() -> None:
    chain = _chain()
    chain["underlying_price"] = 0.0
    packet = build_packet(
        chain, _oi(), root="TST", session_date=SESSION,
        snapshot_bucket=BUCKET, observed_at=OBSERVED, prophet_request=_request(),
    )
    assert packet["profiles"][PROPHET_PROFILE]["status"] == "abstain"
    assert packet["contracts"] == []
    assert _schema_errors(packet) == []


def test_schema_rejects_any_authority_promotion() -> None:
    packet = deepcopy(_packet())
    packet["authority"]["trade_authority"] = True
    assert any("False was expected" in message for message in _schema_errors(packet))


def test_schema_requires_the_same_canonical_utc_clock_shape_as_runtime() -> None:
    packet = deepcopy(_packet())
    packet["clocks"]["available_at"] = "2026-08-07T16:02:00-04:00"
    assert any("does not match" in message for message in _schema_errors(packet))
    packet["clocks"]["available_at"] = "2026-08-07T20:02:00.000Z"
    assert any("does not match" in message for message in _schema_errors(packet))
