from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from engine.options_signal_episode import (
    CAMPAIGN_FALSE_AUTHORITY,
    CAMPAIGN_MIN_PREMIUM_USD,
    CAMPAIGN_RULE_FROZEN_AT,
    PRICE_BASIS,
    PRICE_RECEIPT_SCHEMA,
    SESSION_HORIZONS,
    TIMESTAMP_BASIS,
    ContractError,
    append_campaigns,
    append_episodes,
    append_outcomes,
    append_session_outcomes,
    derive_campaigns,
    episode_from_live_event,
    load_jsonl,
    validate_campaign,
    validate_episode,
    validate_outcome,
    validate_outcome_against_episode,
    validate_session_outcome,
    validate_session_outcome_against_episode,
)
from engine.options_signal_episode import (
    derive_h60_outcome as _derive_h60_outcome,
)
from engine.options_signal_episode import (
    derive_session_outcome as _derive_session_outcome,
)
from engine.session_digest import session_window_et
from lib import nyse_calendar
from scripts import audit_options_market_memory_context as options_context_audit
from scripts import workflow_run_source


def _event(**overrides) -> dict:
    row = {
        "id": "source-event-1",
        "ts": "2026-07-02T14:30:00Z",       # 10:30 ET
        "observed_at": "2026-07-02T14:31:00Z",
        "decision_at": "2026-07-02T14:31:00Z",
        "available_at": "2026-07-02T14:31:00Z",
        "published_at": None,
        "anchor_strategy": "durable_available_at",
        "source_snapshot_asof": "2026-07-02T14:31:30Z",
        "root": "TEST",
        "right": "C",
        "exp": "2026-07-17",
        "strike": 105.0,
        "dte": 15,
        "mny_bucket": "atm",
        "side": "~buy",
        "size": 200,
        "avg_price": 2.5,
        "premium": 50_000.0,
        "premium_z": None,
        "baseline_source": "floor",
        "selection_rule": "premium_floor/v1",
        "selection_floor_usd": 25_000,
        "selection_root_class": "single_name",
        "vol_gt_oi": True,
        "oi_vintage": "2026-07-01",
        "repeated": True,
        "swept": False,
        "signing_source": "tape",
    }
    row.update(overrides)
    return row


def _episode(*, source_snapshot_asof: str | None = None, **event_overrides) -> dict:
    event = _event(**event_overrides)
    if "decision_at" not in event_overrides:
        event["decision_at"] = event["observed_at"]
    if "source_snapshot_asof" not in event_overrides:
        event["source_snapshot_asof"] = event["available_at"]
    return episode_from_live_event(
        event,
        source_snapshot_asof=source_snapshot_asof or str(event["source_snapshot_asof"]),
    )


def _bars(*rows: tuple[str, float, float, float, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
        },
        index=pd.to_datetime([r[0] for r in rows], utc=True),
    )


def _fixture_price_receipt(
    episode: dict,
    bars: pd.DataFrame,
    *,
    price_source: str,
    bar_seconds: int,
    price_delay_minutes: int,
) -> dict:
    frame = bars.copy().sort_index()
    index = pd.to_datetime(frame.index, utc=True)
    available = datetime.fromisoformat(
        episode["available_at"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    entry_candidates = index[index >= pd.Timestamp(available)]
    entry = entry_candidates[0].to_pydatetime().astimezone(timezone.utc)
    target = available + timedelta(minutes=60)
    steps = max(1, math.ceil(max(0.0, (target - entry).total_seconds()) / bar_seconds))
    exit_time = entry + timedelta(seconds=steps * bar_seconds)
    source_available = exit_time + timedelta(minutes=price_delay_minutes)
    return {
        "schema": PRICE_RECEIPT_SCHEMA,
        "ticker": episode["ticker"],
        "source_file": Path(price_source).name,
        "source_file_sha256": hashlib.sha256(b"fixture-price-source").hexdigest(),
        "source_available_at": source_available.isoformat().replace("+00:00", "Z"),
        "bar_seconds": bar_seconds,
        "vendor_delay_minutes": price_delay_minutes,
        "adjusted": True,
        "price_basis": PRICE_BASIS,
        "timestamp_basis": TIMESTAMP_BASIS,
        "row_count": len(frame),
        "first_time": index.min().to_pydatetime().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "last_time": index.max().to_pydatetime().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
    }


def derive_h60_outcome(episode, bars, **kwargs):
    """Test helper: bind direct engine fixtures to an exact synthetic receipt."""
    if (
        "price_receipt" not in kwargs
        and isinstance(bars, pd.DataFrame)
        and not bars.empty
        and type(kwargs.get("bar_seconds")) is int
        and type(kwargs.get("price_delay_minutes")) is int
    ):
        kwargs["price_receipt"] = _fixture_price_receipt(
            episode,
            bars,
            price_source=kwargs["price_source"],
            bar_seconds=kwargs["bar_seconds"],
            price_delay_minutes=kwargs["price_delay_minutes"],
        )
    return _derive_h60_outcome(episode, bars, **kwargs)


def _fixture_session_price_receipt(
    episode: dict,
    horizon: str,
    bars: pd.DataFrame,
    *,
    price_source: str,
    bar_seconds: int,
    price_delay_minutes: int,
    source_available_at: datetime | None = None,
) -> dict:
    frame = bars.copy().sort_index()
    index = pd.to_datetime(frame.index, utc=True)
    target_session = nyse_calendar.session_n_forward(
        datetime.fromisoformat(episode["session_date"]).date(), SESSION_HORIZONS[horizon],
    )
    assert target_session is not None
    target_time = session_window_et(target_session)[1].astimezone(timezone.utc)
    available = source_available_at or target_time + timedelta(minutes=price_delay_minutes)
    return {
        "schema": PRICE_RECEIPT_SCHEMA,
        "ticker": episode["ticker"],
        "source_file": Path(price_source).name,
        "source_file_sha256": hashlib.sha256(b"fixture-session-price-source").hexdigest(),
        "source_available_at": available.isoformat().replace("+00:00", "Z"),
        "bar_seconds": bar_seconds,
        "vendor_delay_minutes": price_delay_minutes,
        "adjusted": True,
        "price_basis": PRICE_BASIS,
        "timestamp_basis": TIMESTAMP_BASIS,
        "row_count": len(frame),
        "first_time": index.min().to_pydatetime().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "last_time": index.max().to_pydatetime().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
    }


def derive_session_outcome(episode, horizon, bars, **kwargs):
    if (
        "price_receipt" not in kwargs
        and isinstance(bars, pd.DataFrame)
        and not bars.empty
        and type(kwargs.get("bar_seconds")) is int
        and type(kwargs.get("price_delay_minutes")) is int
    ):
        kwargs["price_receipt"] = _fixture_session_price_receipt(
            episode,
            horizon,
            bars,
            price_source=kwargs["price_source"],
            bar_seconds=kwargs["bar_seconds"],
            price_delay_minutes=kwargs["price_delay_minutes"],
        )
    return _derive_session_outcome(episode, horizon, bars, **kwargs)


def _session_bars(
    episode: dict,
    horizon: str,
    *,
    bar_seconds: int = 1800,
    tail_sessions: int = 0,
) -> pd.DataFrame:
    start = datetime.fromisoformat(episode["session_date"]).date()
    target = nyse_calendar.session_n_forward(start, SESSION_HORIZONS[horizon] + tail_sessions)
    assert target is not None
    sessions = nyse_calendar.sessions_between(start, target)
    stamps: list[pd.Timestamp] = []
    for session in sessions:
        open_et, close_et = session_window_et(session)
        stamps.extend(pd.date_range(
            open_et.astimezone(timezone.utc),
            close_et.astimezone(timezone.utc) - timedelta(seconds=bar_seconds),
            freq=pd.Timedelta(seconds=bar_seconds),
        ))
    values = [100.0 + index * 0.05 for index in range(len(stamps))]
    return pd.DataFrame(
        {
            "open": values,
            "high": [value + 1.0 for value in values],
            "low": [value - 1.0 for value in values],
            "close": [value + 0.25 for value in values],
        },
        index=pd.DatetimeIndex(stamps),
    )


def _polygon_hourly_session_bars(
    episode: dict,
    horizon: str,
) -> pd.DataFrame:
    """Production Polygon shape: UTC-hour buckets, not NYSE-open-aligned."""
    start = datetime.fromisoformat(episode["session_date"]).date()
    target = nyse_calendar.session_n_forward(start, SESSION_HORIZONS[horizon])
    assert target is not None
    stamps: list[pd.Timestamp] = []
    for session in nyse_calendar.sessions_between(start, target):
        open_et, close_et = session_window_et(session)
        first = pd.Timestamp(open_et.astimezone(timezone.utc)).ceil("h")
        final = pd.Timestamp(close_et.astimezone(timezone.utc)) - timedelta(hours=1)
        stamps.extend(pd.date_range(first, final, freq="h"))
    values = [100.0 + index * 0.25 for index in range(len(stamps))]
    return pd.DataFrame(
        {
            "open": values,
            "high": [value + 1.0 for value in values],
            "low": [value - 1.0 for value in values],
            "close": [value + 0.5 for value in values],
        },
        index=pd.DatetimeIndex(stamps),
    )


def _write_receipted_price_source(
    directory: Path,
    frame: pd.DataFrame,
    *,
    ticker: str = "TEST",
    source_available_at: str = "2026-07-02T16:15:00Z",
    bar_seconds: int = 3600,
    delay_minutes: int = 15,
) -> None:
    source = directory / f"{ticker}.parquet"
    frame.to_parquet(source)
    index = pd.to_datetime(frame.index, utc=True)
    receipt = {
        "schema": PRICE_RECEIPT_SCHEMA,
        "ticker": ticker,
        "source_file": source.name,
        "source_file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_available_at": source_available_at,
        "bar_seconds": bar_seconds,
        "vendor_delay_minutes": delay_minutes,
        "adjusted": True,
        "price_basis": PRICE_BASIS,
        "timestamp_basis": TIMESTAMP_BASIS,
        "row_count": len(frame),
        "first_time": index.min().to_pydatetime().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "last_time": index.max().to_pydatetime().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
    }
    (directory / f"{ticker}.parquet.receipt.json").write_text(
        json.dumps(receipt, sort_keys=True) + "\n"
    )


def _stage_records(event: dict | None = None) -> list[dict]:
    row = dict(event or _event())
    available_at = row.pop("available_at")
    row.pop("published_at", None)
    row.pop("source_snapshot_asof", None)
    row.pop("anchor_strategy", None)
    return [
        {
            "schema": "live_flow.event_stage/v1",
            "kind": "decision",
            "event_id": row["id"],
            "event": row,
        },
        {
            "schema": "live_flow.event_stage/v1",
            "kind": "availability",
            "event_id": row["id"],
            "available_at": available_at,
        },
    ]


def _campaign_episode(
    source_event_id: str,
    premium_usd: float,
    *,
    session_date: str = "2026-07-02",
    available_at: str | None = None,
    ticker: str = "TEST",
    expiration: str = "2026-07-17",
    strike: float = 105.0,
    right: str = "C",
) -> dict:
    session = datetime.fromisoformat(session_date).date()
    available = datetime.fromisoformat(
        (available_at or f"{session_date}T14:31:00Z").replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    event_time = available - timedelta(minutes=1)
    prior_session = nyse_calendar.session_n_back(session, 1)
    assert prior_session is not None
    expiration_date = datetime.fromisoformat(expiration).date()
    contracts = 10_000
    return _episode(
        id=source_event_id,
        ts=event_time.isoformat().replace("+00:00", "Z"),
        observed_at=available.isoformat().replace("+00:00", "Z"),
        decision_at=available.isoformat().replace("+00:00", "Z"),
        available_at=available.isoformat().replace("+00:00", "Z"),
        root=ticker,
        right=right,
        exp=expiration,
        strike=strike,
        dte=(expiration_date - session).days,
        size=contracts,
        avg_price=float(premium_usd) / (contracts * 100),
        premium=premium_usd,
        vol_gt_oi=True,
        oi_vintage=prior_session.isoformat(),
    )


def _campaign_h60_outcome(episode: dict) -> dict:
    available = datetime.fromisoformat(
        episode["available_at"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    session = datetime.fromisoformat(episode["session_date"]).date()
    close = session_window_et(session)[1].astimezone(timezone.utc)
    target = available + timedelta(minutes=60)
    if target >= close:
        outcome = derive_h60_outcome(
            episode,
            None,
            computed_at=target + timedelta(minutes=1),
            price_source=f"data/intraday/{episode['ticker']}.parquet",
            bar_seconds=None,
            price_delay_minutes=None,
            price_receipt=None,
        )
        assert outcome["status"] == "incomplete"
        return outcome
    entry = pd.Timestamp(available).ceil("h").to_pydatetime().astimezone(timezone.utc)
    exit_time = entry + timedelta(hours=1)
    outcome = derive_h60_outcome(
        episode,
        _bars(
            (entry.isoformat(), 100.0, 101.0, 99.0, 100.5),
            (exit_time.isoformat(), 100.5, 102.0, 100.0, 101.0),
        ),
        computed_at=exit_time,
        price_source=f"data/intraday/{episode['ticker']}.parquet",
        bar_seconds=3600,
        price_delay_minutes=0,
    )
    assert outcome["status"] == "complete"
    return outcome


def _canonical_test_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def test_episode_freezes_exact_availability_and_zero_authority() -> None:
    row = _episode()
    validate_episode(row)
    assert row["schema"] == "options.signal_episode/v1"
    assert row["decision"]["disposition"] == "watch"
    assert set(row["decision"]["authority"].values()) == {False}
    assert row["provenance"]["feature_cutoff"] == row["available_at"]
    assert row["provenance"]["oi_vintage"] == "2026-07-01"


def test_episode_identity_is_recomputed_from_source_event_semantics() -> None:
    row = _episode()
    forged = copy.deepcopy(row)
    forged["episode_id"] = "osep_" + "0" * 24
    with pytest.raises(ContractError, match="episode_id must be stable"):
        validate_episode(forged)


def test_episode_rejects_retroactive_availability_backfill() -> None:
    with pytest.raises(ContractError, match="observed_at"):
        _episode(observed_at=None, available_at=None)


def test_episode_rejects_event_clock_after_availability() -> None:
    with pytest.raises(ContractError, match="clock order"):
        _episode(ts="2026-07-02T14:32:00Z")


def test_episode_rejects_source_snapshot_before_first_availability() -> None:
    with pytest.raises(ContractError, match="source snapshot"):
        episode_from_live_event(
            _event(), source_snapshot_asof="2026-07-02T14:30:30Z",
        )

    with pytest.raises(ContractError, match="snapshot envelope must equal"):
        episode_from_live_event(
            _event(), source_snapshot_asof="2026-07-02T14:31:30.000001Z",
        )

    leaked = _episode()
    leaked["provenance"]["source_snapshot_asof"] = "2026-07-02T14:31:00.000001Z"
    with pytest.raises(ContractError, match="must equal durable event availability"):
        validate_episode(leaked)


def test_episode_requires_exact_oi_vintage_when_oi_feature_present() -> None:
    with pytest.raises(ContractError, match="exact OI vintage"):
        _episode(oi_vintage=None)
    # The feature itself may be absent; then no OI date is invented.
    row = _episode(vol_gt_oi=None, oi_vintage=None)
    assert row["provenance"]["oi_vintage"] is None


@pytest.mark.parametrize("oi_vintage", ["2026-07-02", "2026-07-06", "2026-07-04"])
def test_episode_rejects_non_prior_oi_vintage_even_without_oi_feature(
    oi_vintage: str,
) -> None:
    with pytest.raises(ContractError, match="strictly before"):
        _episode(vol_gt_oi=None, oi_vintage=oi_vintage)


def test_episode_rejects_non_session_source_date() -> None:
    with pytest.raises(ContractError, match="not an NYSE session"):
        _episode(
            ts="2026-07-04T14:30:00Z",
            observed_at="2026-07-04T14:31:00Z",
            available_at="2026-07-04T14:31:00Z",
            exp="2026-07-17",
            vol_gt_oi=None,
            oi_vintage=None,
        )


def test_episode_rejects_premarket_and_collapsed_clock_order() -> None:
    with pytest.raises(ContractError, match="premarket"):
        _episode(
            ts="2026-07-02T13:29:00Z",
            observed_at="2026-07-02T13:29:10Z",
            decision_at="2026-07-02T13:29:20Z",
            available_at="2026-07-02T13:29:30Z",
        )
    with pytest.raises(ContractError, match="clock order"):
        _episode(decision_at="2026-07-02T14:30:59Z")


def test_h60_complete_is_explicit_post_target_aligned_bar_proxy() -> None:
    row = derive_h60_outcome(
        _episode(),
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="data/intraday/TEST.parquet",
        bar_seconds=3600,
        price_delay_minutes=15,
    )
    validate_outcome(row)
    assert row["status"] == "complete"
    assert row["underlying"]["entry_time"] == "2026-07-02T15:00:00Z"
    assert row["underlying"]["exit_time"] == "2026-07-02T16:00:00Z"
    assert row["underlying"]["ret"] == pytest.approx(0.03)
    assert row["underlying"]["mfe"] == pytest.approx(0.04)
    assert row["underlying"]["mae"] == pytest.approx(-0.02)
    assert row["underlying"]["entry_delay_minutes"] == pytest.approx(29.0)
    assert row["underlying"]["exit_delay_minutes"] == pytest.approx(29.0)
    assert row["horizon_anchor"] == "2026-07-02T14:31:00Z"
    assert row["target_time"] == "2026-07-02T15:31:00Z"
    assert row["matured_at"] == "2026-07-02T16:15:00Z"
    assert row["measurement"] == {
        "version": "h60-aligned-bars/v1",
        "kind": "aligned_bar_proxy",
        "target_aligned": False,
        "training_eligible": False,
        "training_ineligibility_reasons": [
            "measurement_window_not_target_aligned",
            "bar_resolution_exceeds_60s",
            "price_delay_exceeds_1m",
        ],
        "window": {
            "start": "2026-07-02T15:00:00Z",
            "end": "2026-07-02T16:00:00Z",
        },
    }
    assert row["option"]["status"] == "unavailable"
    assert row["option"]["reason"] == "no_executable_nbbo_quote_path"


def test_h60_requires_a_complete_declared_cadence_grid() -> None:
    episode = _episode()
    stamps = pd.date_range(
        "2026-07-02T14:31:00Z", "2026-07-02T15:31:00Z", freq="1min",
    )
    complete = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=stamps,
    )
    row = derive_h60_outcome(
        episode,
        complete,
        computed_at=datetime(2026, 7, 2, 15, 32, tzinfo=timezone.utc),
        price_source="data/intraday/TEST.parquet",
        bar_seconds=60,
        price_delay_minutes=0,
    )
    validate_outcome(row)
    validate_outcome_against_episode(row, episode)
    assert row["status"] == "complete"
    assert row["measurement"]["target_aligned"] is True
    assert row["measurement"]["training_eligible"] is True

    endpoints_only = complete.iloc[[0, -1]]
    assert derive_h60_outcome(
        episode,
        endpoints_only,
        computed_at=datetime(2026, 7, 2, 15, 32, tzinfo=timezone.utc),
        price_source="fixture",
        bar_seconds=60,
        price_delay_minutes=0,
    )["reason"] == "measurement_path_gap"

    missing_interior = complete.drop(complete.index[23])
    assert derive_h60_outcome(
        episode,
        missing_interior,
        computed_at=datetime(2026, 7, 2, 15, 32, tzinfo=timezone.utc),
        price_source="fixture",
        bar_seconds=60,
        price_delay_minutes=0,
    )["reason"] == "measurement_path_gap"


def test_h60_ignores_post_exit_tail_but_rejects_used_bar_corruption() -> None:
    episode = _episode()
    base = _bars(
        ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
        ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
    )
    baseline = derive_h60_outcome(
        episode, base,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    future_corrupt = pd.concat([
        base,
        _bars(("2026-07-02T17:00:00Z", 110.0, 100.0, 111.0, 109.0)),
    ])
    replay = derive_h60_outcome(
        episode, future_corrupt,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert replay["measurement"] == baseline["measurement"]
    assert replay["underlying"] == baseline["underlying"]
    assert replay["matured_at"] == baseline["matured_at"]
    assert replay["provenance"]["price_vintage"] == baseline["provenance"]["price_vintage"]

    evolving_exit_tail = base.copy()
    evolving_exit_tail.loc[pd.Timestamp("2026-07-02T16:00:00Z"), ["high", "low", "close"]] = [
        1.0, 999.0, -10.0,
    ]
    exit_tail_replay = derive_h60_outcome(
        episode, evolving_exit_tail,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert exit_tail_replay == baseline

    invalid_exit_open = base.copy()
    invalid_exit_open.loc[pd.Timestamp("2026-07-02T16:00:00Z"), "open"] = float("nan")
    rejected = derive_h60_outcome(
        episode, invalid_exit_open,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert rejected["reason"] == "missing_price_fields"


def test_missing_exit_bar_remains_pending_for_later_nightly() -> None:
    row = derive_h60_outcome(
        _episode(),
        _bars(("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0)),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="data/intraday/TEST.parquet",
        bar_seconds=3600,
    )
    assert row == {
        "status": "pending",
        "reason": "missing_exit_bar",
        "episode_id": _episode()["episode_id"],
    }


def test_coarse_aligned_exit_at_close_stays_pending_without_causal_contract() -> None:
    episode = _episode(
        id="coarse-close",
        ts="2026-07-02T18:29:00Z",       # 14:29 ET
        observed_at="2026-07-02T18:30:00Z",
        available_at="2026-07-02T18:30:00Z",
    )
    bars = _bars(("2026-07-02T19:00:00Z", 100.0, 101.0, 99.0, 100.5))
    early = derive_h60_outcome(
        episode, bars,
        computed_at=datetime(2026, 7, 2, 19, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert early["reason"] == "horizon_not_matured"

    matured = derive_h60_outcome(
        episode, bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert matured["status"] == "pending"
    assert matured["reason"] == "aligned_exit_crosses_session_close"


def test_post_close_processing_is_retained_but_never_becomes_a_label() -> None:
    episode = _episode(
        id="post-close-decision",
        ts="2026-07-02T19:59:00Z",
        observed_at="2026-07-02T20:00:01Z",
        decision_at="2026-07-02T20:00:02Z",
        available_at="2026-07-02T20:00:03Z",
    )
    validate_episode(episode)
    early = derive_h60_outcome(
        episode, None,
        computed_at=datetime(2026, 7, 2, 20, 30, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=60, price_delay_minutes=1,
    )
    assert early["reason"] == "horizon_not_matured"

    matured = derive_h60_outcome(
        episode, None,
        computed_at=datetime(2026, 7, 2, 22, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=60, price_delay_minutes=1,
    )
    assert matured["status"] == "incomplete"
    assert matured["reason"] == "decision_after_session_close"
    validate_outcome(matured)

    with pytest.raises(ContractError, match="event exchange date"):
        _episode(
            id="next-date-decision",
            ts="2026-07-02T19:59:00Z",
            observed_at="2026-07-03T13:30:00Z",
            decision_at="2026-07-03T13:30:01Z",
            available_at="2026-07-03T13:30:02Z",
        )


def test_late_event_gets_terminal_session_boundary_label() -> None:
    episode = _episode(
        id="late",
        ts="2026-07-02T19:10:00Z",       # 15:10 ET
        observed_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
    )
    row = derive_h60_outcome(
        episode,
        _bars(("2026-07-02T19:30:00Z", 100.0, 101.0, 99.0, 100.5)),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="data/intraday/TEST.parquet",
        bar_seconds=3600,
    )
    assert row["status"] == "incomplete"
    assert row["reason"] == "horizon_crosses_session_close"
    validate_outcome(row)


def test_early_cross_close_run_remains_pending_until_target() -> None:
    episode = _episode(
        id="late-early-run",
        ts="2026-07-02T19:10:00Z",
        observed_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
    )
    row = derive_h60_outcome(
        episode,
        None,
        computed_at=datetime(2026, 7, 2, 19, 30, tzinfo=timezone.utc),
        price_source="fixture",
        bar_seconds=3600,
    )
    assert row == {
        "status": "pending",
        "reason": "horizon_not_matured",
        "episode_id": episode["episode_id"],
    }


def test_target_exactly_at_close_is_terminal_not_a_label() -> None:
    episode = _episode(
        id="at-close",
        ts="2026-07-02T18:59:30Z",
        observed_at="2026-07-02T19:00:00Z",
        decision_at="2026-07-02T19:00:00Z",
        available_at="2026-07-02T19:00:00Z",
    )
    row = derive_h60_outcome(
        episode, None,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600,
    )
    assert row["status"] == "incomplete"
    assert row["reason"] == "horizon_crosses_session_close"


@pytest.mark.parametrize("offset_microseconds", [-999_000, -1_000, 1_000, 500_000, 999_000])
def test_outcome_horizon_rejects_every_fractional_second_drift(
    offset_microseconds: int,
) -> None:
    episode = _episode(
        id="fractional-horizon",
        ts="2026-07-02T19:10:00Z",
        observed_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
    )
    row = derive_h60_outcome(
        episode, None,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=60, price_delay_minutes=1,
    )
    drifted = copy.deepcopy(row)
    target = datetime.fromisoformat(drifted["target_time"].replace("Z", "+00:00"))
    shifted = target + pd.Timedelta(microseconds=offset_microseconds)
    drifted["target_time"] = shifted.isoformat().replace("+00:00", "Z")
    drifted["matured_at"] = drifted["target_time"]
    with pytest.raises(ContractError, match=r"exactly H\+60"):
        validate_outcome(drifted)


def test_outcome_horizon_requires_exact_integer_type() -> None:
    episode = _episode(
        id="typed-horizon",
        ts="2026-07-02T19:10:00Z",
        observed_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
    )
    row = derive_h60_outcome(
        episode, None,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=60, price_delay_minutes=1,
    )
    row["horizon_minutes"] = 60.0
    with pytest.raises(ContractError, match="horizon_minutes|horizon must be"):
        validate_outcome(row)


def test_unknown_bar_cadence_fails_closed() -> None:
    row = derive_h60_outcome(
        _episode(),
        _bars(("2026-07-02T15:00:00Z", 100.0, 101.0, 99.0, 100.5)),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=None,
    )
    assert row["status"] == "pending"
    assert row["reason"] == "unknown_bar_cadence"


def test_schema_format_arithmetic_and_ohlc_fail_closed() -> None:
    malformed_clock = _episode()
    malformed_clock["event_time"] = "not-a-timestamp"
    with pytest.raises(ContractError, match="ISO-8601 timestamp"):
        validate_episode(malformed_clock)

    episode = _episode()
    outcome = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    outcome["underlying"]["ret"] += 0.01
    with pytest.raises(ContractError, match="arithmetically inconsistent"):
        validate_outcome(outcome)

    invalid_bar = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 99.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert invalid_bar["reason"] == "invalid_ohlc_bar"


def test_outcome_contract_rejects_impossible_cross_field_states() -> None:
    valid = derive_h60_outcome(
        _episode(),
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )

    mutations = []
    wrong_underlying_status = copy.deepcopy(valid)
    wrong_underlying_status["underlying"]["status"] = "unavailable"
    mutations.append(wrong_underlying_status)
    positive_mae = copy.deepcopy(valid)
    positive_mae["underlying"]["mae"] = 0.01
    mutations.append(positive_mae)
    impossible_mae = copy.deepcopy(valid)
    impossible_mae["underlying"]["mae"] = -2.0
    mutations.append(impossible_mae)
    early_maturity = copy.deepcopy(valid)
    early_maturity["matured_at"] = early_maturity["underlying"]["exit_time"]
    mutations.append(early_maturity)
    null_provenance = copy.deepcopy(valid)
    null_provenance["provenance"]["price_source"] = None
    null_provenance["provenance"]["price_vintage"] = None
    mutations.append(null_provenance)
    unavailable_option_return = copy.deepcopy(valid)
    unavailable_option_return["option"]["ret"] = 0.25
    mutations.append(unavailable_option_return)
    arbitrary_reason = copy.deepcopy(valid)
    arbitrary_reason["measurement"]["training_ineligibility_reasons"] = ["arbitrary"]
    mutations.append(arbitrary_reason)
    complete_with_reason = copy.deepcopy(valid)
    complete_with_reason["reason"] = "should_be_null"
    mutations.append(complete_with_reason)
    nonfinite = copy.deepcopy(valid)
    nonfinite["underlying"]["mfe"] = float("inf")
    mutations.append(nonfinite)
    incomplete_option = copy.deepcopy(valid)
    incomplete_option["option"] = {
        "status": "complete", "reason": None,
        "quote_basis": "executable_bid_ask", "ret": 0.1,
        "mfe": 0.2, "mae": -0.1,
    }
    mutations.append(incomplete_option)

    for mutation in mutations:
        with pytest.raises(ContractError):
            validate_outcome(mutation)


def test_h60_unknown_or_invalid_price_delay_never_matures() -> None:
    episode = _episode()
    bars = _bars(
        ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
        ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
    )
    pending = derive_h60_outcome(
        episode, bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=None,
    )
    assert pending["reason"] == "unknown_price_delay"
    for invalid in (-1, 1.5, "15", True):
        with pytest.raises(ContractError, match="exact non-negative integer"):
            derive_h60_outcome(
                episode, bars,
                computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
                price_source="fixture", bar_seconds=3600,
                price_delay_minutes=invalid,
            )

    before_delay = derive_h60_outcome(
        episode, bars,
        computed_at=datetime(2026, 7, 2, 16, 14, 59, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert before_delay["reason"] == "measurement_not_available"
    matured = derive_h60_outcome(
        episode, bars,
        computed_at=datetime(2026, 7, 2, 16, 15, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert matured["status"] == "complete"


def test_h60_rejects_naive_computation_clock() -> None:
    with pytest.raises(ContractError, match="timezone-aware"):
        derive_h60_outcome(
            _episode(), None,
            computed_at=datetime(2026, 7, 2, 21, 0),
            price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
        )


def test_early_close_calendar_is_respected() -> None:
    # 2026-11-27 is the Friday after Thanksgiving; close is 13:00 ET / 18:00Z.
    episode = _episode(
        id="half-day",
        ts="2026-11-27T17:01:00Z",
        observed_at="2026-11-27T17:02:00Z",
        available_at="2026-11-27T17:02:00Z",
        exp="2026-12-18",
        dte=21,
        oi_vintage="2026-11-25",
    )
    row = derive_h60_outcome(
        episode,
        _bars(("2026-11-27T17:30:00Z", 100.0, 101.0, 99.0, 100.5)),
        computed_at=datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc),
        price_source="data/intraday/TEST.parquet",
        bar_seconds=3600,
    )
    assert row["status"] == "incomplete"
    assert row["reason"] == "horizon_crosses_session_close"


def test_early_close_post_close_decision_and_coarse_alignment_are_terminal() -> None:
    post_close = _episode(
        id="half-day-post-close",
        ts="2026-11-27T17:59:00Z",
        observed_at="2026-11-27T18:00:01Z",
        decision_at="2026-11-27T18:00:02Z",
        available_at="2026-11-27T18:00:03Z",
        exp="2026-12-18",
        dte=21,
        oi_vintage="2026-11-25",
    )
    validate_episode(post_close)
    post_close_outcome = derive_h60_outcome(
        post_close, None,
        computed_at=datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=60, price_delay_minutes=1,
    )
    assert post_close_outcome["reason"] == "decision_after_session_close"

    coarse = _episode(
        id="half-day-coarse-close",
        ts="2026-11-27T16:29:00Z",       # 11:29 ET
        observed_at="2026-11-27T16:30:00Z",
        available_at="2026-11-27T16:30:00Z",
        exp="2026-12-18",
        dte=21,
        oi_vintage="2026-11-25",
    )
    coarse_outcome = derive_h60_outcome(
        coarse,
        _bars(("2026-11-27T17:00:00Z", 100.0, 101.0, 99.0, 100.5)),
        computed_at=datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    assert coarse_outcome == {
        "status": "pending",
        "reason": "aligned_exit_crosses_session_close",
        "episode_id": coarse["episode_id"],
    }


@pytest.mark.parametrize(
    ("episode", "computed_at", "reason"),
    [
        (
            _episode(
                id="no-meta-cross-close", ts="2026-07-02T19:10:00Z",
                observed_at="2026-07-02T19:11:00Z",
                available_at="2026-07-02T19:11:00Z",
            ),
            datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
            "horizon_crosses_session_close",
        ),
        (
            _episode(
                id="no-meta-post-close", ts="2026-07-02T19:59:00Z",
                observed_at="2026-07-02T20:00:01Z",
                decision_at="2026-07-02T20:00:02Z",
                available_at="2026-07-02T20:00:03Z",
            ),
            datetime(2026, 7, 2, 22, 0, tzinfo=timezone.utc),
            "decision_after_session_close",
        ),
        (
            _episode(
                id="no-meta-early-close", ts="2026-11-27T17:01:00Z",
                observed_at="2026-11-27T17:02:00Z",
                available_at="2026-11-27T17:02:00Z",
                exp="2026-12-18", dte=21, oi_vintage="2026-11-25",
            ),
            datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc),
            "horizon_crosses_session_close",
        ),
    ],
)
def test_session_terminal_outcomes_do_not_require_price_metadata(
    episode: dict, computed_at: datetime, reason: str,
) -> None:
    row = derive_h60_outcome(
        episode, None, computed_at=computed_at,
        price_source="", bar_seconds=None, price_delay_minutes=None,
    )
    assert row["status"] == "incomplete"
    assert row["reason"] == reason
    validate_outcome_against_episode(row, episode)


@pytest.mark.parametrize("bar_seconds", [60.0, True])
def test_derive_rejects_noninteger_declared_bar_cadence(bar_seconds: object) -> None:
    with pytest.raises(ContractError, match="exact integer"):
        derive_h60_outcome(
            _episode(),
            _bars(
                ("2026-07-02T14:31:00Z", 100.0, 101.0, 99.0, 100.5),
                ("2026-07-02T15:31:00Z", 101.0, 102.0, 100.0, 101.5),
            ),
            computed_at=datetime(2026, 7, 2, 16, 0, tzinfo=timezone.utc),
            price_source="fixture", bar_seconds=bar_seconds, price_delay_minutes=0,
        )


def _retime_complete_outcome(
    outcome: dict, *, entry: str, exit_: str,
) -> dict:
    """Keep a complete row internally valid while adversarially moving its window."""
    row = copy.deepcopy(outcome)
    anchor = datetime.fromisoformat(row["horizon_anchor"].replace("Z", "+00:00"))
    target = datetime.fromisoformat(row["target_time"].replace("Z", "+00:00"))
    entry_dt = datetime.fromisoformat(entry.replace("Z", "+00:00"))
    exit_dt = datetime.fromisoformat(exit_.replace("Z", "+00:00"))
    row["underlying"]["entry_time"] = entry
    row["underlying"]["exit_time"] = exit_
    row["underlying"]["entry_delay_minutes"] = round(
        (entry_dt - anchor).total_seconds() / 60.0, 3,
    )
    row["underlying"]["exit_delay_minutes"] = round(
        (exit_dt - target).total_seconds() / 60.0, 3,
    )
    row["measurement"]["window"] = {"start": entry, "end": exit_}
    row["measurement"]["target_aligned"] = entry_dt == anchor and exit_dt == target
    evidence = row["underlying"]["evidence"]
    evidence["path"][0]["time"] = entry
    evidence["exit"]["time"] = exit_
    evidence["sha256"] = hashlib.sha256(json.dumps(
        {"path": evidence["path"], "exit": evidence["exit"]},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")).hexdigest()
    matured = exit_dt + timedelta(minutes=row["provenance"]["price_delay_minutes"])
    row["matured_at"] = matured.isoformat().replace("+00:00", "Z")
    computed = datetime.fromisoformat(row["computed_at"].replace("Z", "+00:00"))
    if computed < matured:
        row["computed_at"] = matured.isoformat().replace("+00:00", "Z")
    row["provenance"]["price_vintage"] = exit_
    row["provenance"]["source_available_at"] = row["matured_at"]
    row["provenance"]["source_file_first_time"] = entry
    row["provenance"]["source_file_last_time"] = exit_
    return row


@pytest.mark.parametrize(
    ("entry", "exit_"),
    [
        ("2026-07-02T19:00:00Z", "2026-07-02T20:00:00Z"),
        ("2026-07-02T20:01:00Z", "2026-07-02T21:01:00Z"),
        ("2026-07-06T15:00:00Z", "2026-07-06T16:00:00Z"),
    ],
)
def test_episode_outcome_join_rejects_complete_window_outside_session(
    entry: str, exit_: str,
) -> None:
    episode = _episode()
    outcome = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    poisoned = _retime_complete_outcome(outcome, entry=entry, exit_=exit_)
    validate_outcome(poisoned)
    with pytest.raises(ContractError, match="inside the episode session"):
        validate_outcome_against_episode(poisoned, episode)


@pytest.mark.parametrize(
    ("entry", "exit_", "error"),
    [
        (
            "2026-07-02T15:00:00Z", "2026-07-02T16:01:00Z",
            "first aligned bar boundary",
        ),
        (
            "2026-07-02T15:38:00Z", "2026-07-02T16:38:00Z",
            "entry exceeds the admitted bar gap",
        ),
    ],
)
def test_episode_outcome_join_reproduces_entry_and_exit_grid(
    entry: str, exit_: str, error: str,
) -> None:
    episode = _episode()
    outcome = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=3600, price_delay_minutes=15,
    )
    poisoned = _retime_complete_outcome(outcome, entry=entry, exit_=exit_)
    if error == "first aligned bar boundary":
        with pytest.raises(ContractError, match="span the measurement grid"):
            validate_outcome(poisoned)
        return
    validate_outcome(poisoned)
    with pytest.raises(ContractError, match=error):
        validate_outcome_against_episode(poisoned, episode)


def test_complete_outcome_price_source_is_bound_to_episode_ticker() -> None:
    episode = _episode()
    outcome = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="data/intraday/TEST.parquet",
        bar_seconds=3600,
        price_delay_minutes=15,
    )
    validate_outcome_against_episode(outcome, episode)

    absolute = copy.deepcopy(outcome)
    absolute["provenance"]["price_source"] = "/private/cache/TEST.parquet"
    validate_outcome_against_episode(absolute, episode)

    for wrong in (
        "data/intraday/MSFT.parquet",
        "data/intraday/TEST.parquet.bak",
        "data/intraday/test.parquet",
    ):
        poisoned = copy.deepcopy(outcome)
        poisoned["provenance"]["price_source"] = wrong
        with pytest.raises(ContractError, match="match the episode ticker"):
            validate_outcome_against_episode(poisoned, episode)


def test_jsonl_append_is_nightly_only_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    episode = _episode()
    outcome = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture",
        bar_seconds=3600,
        price_delay_minutes=15,
    )
    ep_path = tmp_path / "episodes.jsonl"
    out_path = tmp_path / "outcomes.jsonl"

    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    assert append_episodes(ep_path, [episode]) == -1
    assert not ep_path.exists()

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert append_episodes(ep_path, [episode, copy.deepcopy(episode)]) == 1
    assert append_episodes(ep_path, [episode]) == 0
    assert append_outcomes(out_path, [outcome, copy.deepcopy(outcome)]) == 1
    assert append_outcomes(out_path, [outcome]) == 0
    assert len(load_jsonl(ep_path)) == 1
    assert len(load_jsonl(out_path)) == 1


def test_first_jsonl_append_durably_links_directory_and_ledger(
    tmp_path: Path, monkeypatch,
) -> None:
    import engine.options_signal_episode as ledger

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    order: list[str] = []
    real_fsync = ledger.os.fsync

    def fsync_spy(fd: int) -> None:
        mode = ledger.os.fstat(fd).st_mode
        order.append("directory_fsync" if stat.S_ISDIR(mode) else "file_fsync")
        real_fsync(fd)

    monkeypatch.setattr(ledger.os, "fsync", fsync_spy)
    path = tmp_path / "ledger" / "episodes.jsonl"
    assert append_episodes(path, [_episode()]) == 1
    assert path.read_bytes().endswith(b"\n")
    assert order == [
        "directory_fsync", "directory_fsync",  # ledger dir + parent link
        "file_fsync", "directory_fsync",      # first-created ledger link
        "file_fsync",                           # appended row bytes
    ]


def test_duplicate_episode_payload_drift_fails_closed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "episodes.jsonl"
    episode = _episode()
    drifted = copy.deepcopy(episode)
    drifted["feature_snapshot"]["premium_usd"] += 1
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert append_episodes(path, [episode]) == 1
    assert append_episodes(path, [copy.deepcopy(episode)]) == 0
    with pytest.raises(ContractError, match="conflicting append payload"):
        append_episodes(path, [drifted])


def test_outcome_id_and_semantic_key_reject_label_drift(tmp_path: Path, monkeypatch) -> None:
    episode = _episode()
    bars = _bars(
        ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
        ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
    )
    first = derive_h60_outcome(
        episode, bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture-a", bar_seconds=3600, price_delay_minutes=15,
    )
    drifted = derive_h60_outcome(
        episode, bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture-b", bar_seconds=3600, price_delay_minutes=15,
    )
    assert first["outcome_id"] == drifted["outcome_id"]
    path = tmp_path / "outcomes.jsonl"
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert append_outcomes(path, [first]) == 1
    assert append_outcomes(path, [copy.deepcopy(first)]) == 0
    with pytest.raises(ContractError, match="conflicting append payload"):
        append_outcomes(path, [drifted])

    invalid_id = copy.deepcopy(first)
    invalid_id["outcome_id"] = "oout_" + "0" * 24
    with pytest.raises(ContractError, match="outcome_id must be stable"):
        append_outcomes(path, [invalid_id])


def test_jsonl_malformed_interior_and_torn_final_fail_closed(
    tmp_path: Path, monkeypatch,
) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"ok":true}\nnot-json\n{"ok":true}\n')
    with pytest.raises(ContractError, match="malformed line 2"):
        load_jsonl(malformed)

    duplicate = tmp_path / "duplicate-key.jsonl"
    duplicate.write_text('{"schema":"first","schema":"second"}\n')
    with pytest.raises(ContractError, match="malformed line 1"):
        load_jsonl(duplicate)

    torn = tmp_path / "torn.jsonl"
    episode = _episode()
    torn.write_bytes(json.dumps(episode, sort_keys=True).encode("utf-8"))
    with pytest.raises(ContractError, match="torn/non-terminated"):
        load_jsonl(torn)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(ContractError, match="torn/non-terminated"):
        append_episodes(torn, [episode])


def test_raw_stage_splits_observation_decision_and_durable_availability(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    event["observed_at"] = "2026-07-02T14:31:00Z"
    event["decision_at"] = "2026-07-02T14:33:00Z"
    clock = lambda: datetime(2026, 7, 2, 14, 34, tzinfo=timezone.utc)
    staged = poller._stage_raw_events("2026-07-02", [event], now_fn=clock)
    assert staged[0]["observed_at"] == "2026-07-02T14:31:00Z"
    assert staged[0]["decision_at"] == "2026-07-02T14:33:00Z"
    assert staged[0]["available_at"] == "2026-07-02T14:34:00Z"
    assert staged[0]["published_at"] is None
    assert staged[0]["anchor_strategy"] == "durable_available_at"
    receipts = (tmp_path / "2026-07-02.jsonl").read_text().splitlines()
    assert [json.loads(line)["kind"] for line in receipts] == ["decision", "availability"]
    replay_event = dict(event)
    replay_event["observed_at"] = "2026-07-02T14:35:00Z"
    replay_event["decision_at"] = "2026-07-02T14:36:00Z"
    replay = poller._stage_raw_events("2026-07-02", [replay_event], now_fn=clock)
    assert replay[0]["available_at"] == staged[0]["available_at"]
    assert replay[0]["observed_at"] == staged[0]["observed_at"]
    assert replay[0]["decision_at"] == staged[0]["decision_at"]
    assert len((tmp_path / "2026-07-02.jsonl").read_text().splitlines()) == 2


def test_new_stage_fsyncs_directory_before_observing_availability(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)

    order: list[str] = []
    real_fsync = poller.os.fsync

    def fsync_spy(fd: int) -> None:
        mode = poller.os.fstat(fd).st_mode
        order.append("directory_fsync" if stat.S_ISDIR(mode) else "file_fsync")
        real_fsync(fd)

    clock_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        order.append(f"clock_{clock_calls}")
        return datetime(2026, 7, 2, 14, 31 + clock_calls, tzinfo=timezone.utc)

    monkeypatch.setattr(poller.os, "fsync", fsync_spy)
    poller._stage_raw_events("2026-07-02", [event], now_fn=clock)
    assert order == [
        "clock_1", "file_fsync", "directory_fsync", "clock_2", "file_fsync",
        "file_fsync", "directory_fsync",
    ]


def test_new_nested_stage_root_is_directory_durable_before_first_clock(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    stage_root = tmp_path / "fresh" / "nested" / "events"
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(stage_root))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)

    order: list[str] = []
    real_fsync = poller.os.fsync

    def fsync_spy(fd: int) -> None:
        mode = poller.os.fstat(fd).st_mode
        order.append("directory_fsync" if stat.S_ISDIR(mode) else "file_fsync")
        real_fsync(fd)

    clock_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        order.append(f"clock_{clock_calls}")
        return datetime(2026, 7, 2, 14, 31 + clock_calls, tzinfo=timezone.utc)

    monkeypatch.setattr(poller.os, "fsync", fsync_spy)
    poller._stage_raw_events("2026-07-02", [event], now_fn=clock)

    first_clock = order.index("clock_1")
    assert first_clock == 6  # new dir + durable parent link per component
    assert order[:first_clock] == ["directory_fsync"] * first_clock
    assert order[first_clock:] == [
        "clock_1", "file_fsync", "directory_fsync", "clock_2", "file_fsync",
        "file_fsync", "directory_fsync",
    ]
    assert stage_root.is_dir()


def test_raw_stage_replay_reconfirms_visible_receipts_after_fsync_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)

    real_fsync = poller.os.fsync
    regular_file_calls = 0
    fail_availability_once = True

    def fsync_spy(fd: int) -> None:
        nonlocal regular_file_calls, fail_availability_once
        mode = poller.os.fstat(fd).st_mode
        if not stat.S_ISDIR(mode):
            regular_file_calls += 1
            if fail_availability_once and regular_file_calls == 2:
                fail_availability_once = False
                raise OSError("simulated availability-receipt fsync failure")
        real_fsync(fd)

    clock = lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc)
    monkeypatch.setattr(poller.os, "fsync", fsync_spy)
    with pytest.raises(OSError, match="availability-receipt fsync failure"):
        poller._stage_raw_events("2026-07-02", [event], now_fn=clock)

    stage_path = tmp_path / "2026-07-02.jsonl"
    assert [
        json.loads(line)["kind"] for line in stage_path.read_text().splitlines()
    ] == ["decision", "availability"]

    before_replay = regular_file_calls
    replayed = poller._stage_raw_events("2026-07-02", [event], now_fn=clock)
    assert regular_file_calls > before_replay
    assert replayed[0]["available_at"] == "2026-07-02T14:32:00Z"
    assert len(stage_path.read_text().splitlines()) == 2


def test_raw_stage_replay_reconfirms_first_path_link_after_directory_fsync_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)

    real_fsync = poller.os.fsync
    fail_directory_once = True
    replay_directory_fsyncs = 0

    def fsync_spy(fd: int) -> None:
        nonlocal fail_directory_once, replay_directory_fsyncs
        mode = poller.os.fstat(fd).st_mode
        if stat.S_ISDIR(mode):
            if fail_directory_once:
                fail_directory_once = False
                raise OSError("simulated stage-directory fsync failure")
            replay_directory_fsyncs += 1
        real_fsync(fd)

    clock = lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc)
    monkeypatch.setattr(poller.os, "fsync", fsync_spy)
    with pytest.raises(OSError, match="stage-directory fsync failure"):
        poller._stage_raw_events("2026-07-02", [event], now_fn=clock)

    stage_path = tmp_path / "2026-07-02.jsonl"
    assert [
        json.loads(line)["kind"] for line in stage_path.read_text().splitlines()
    ] == ["decision"]
    replayed = poller._stage_raw_events("2026-07-02", [event], now_fn=clock)
    assert replay_directory_fsyncs >= 1
    assert replayed[0]["available_at"] == "2026-07-02T14:32:00Z"
    assert [
        json.loads(line)["kind"] for line in stage_path.read_text().splitlines()
    ] == ["decision", "availability"]


def test_atomic_publication_receipt_replace_is_directory_durable(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    order: list[str] = []
    real_fsync = poller.os.fsync

    def fsync_spy(fd: int) -> None:
        mode = poller.os.fstat(fd).st_mode
        order.append("directory_fsync" if stat.S_ISDIR(mode) else "file_fsync")
        real_fsync(fd)

    monkeypatch.setattr(poller.os, "fsync", fsync_spy)
    path = poller._atomic_write_json(
        tmp_path / "published.json",
        {"schema": "live_flow.event_publications/v1", "objects": {}},
    )
    assert path.exists()
    assert order == ["file_fsync", "directory_fsync"]


def test_raw_stage_recovers_decision_only_crash_with_first_clocks(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    first = _event(
        observed_at="2026-07-02T14:31:00.123456Z",
        decision_at="2026-07-02T14:32:00.234567Z",
    )
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        first.pop(key, None)
    decision_only = {
        "schema": "live_flow.event_stage/v1",
        "kind": "decision",
        "event_id": first["id"],
        "event": first,
    }
    stage_path = tmp_path / "2026-07-02.jsonl"
    stage_path.write_text(json.dumps(decision_only, sort_keys=True) + "\n")

    replay = dict(first)
    replay["observed_at"] = "2026-07-02T14:35:00Z"
    replay["decision_at"] = "2026-07-02T14:36:00Z"
    recovered = poller._stage_raw_events(
        "2026-07-02", [replay],
        now_fn=lambda: datetime(2026, 7, 2, 14, 37, 0, 345678, tzinfo=timezone.utc),
    )
    assert recovered[0]["observed_at"] == first["observed_at"]
    assert recovered[0]["decision_at"] == first["decision_at"]
    assert recovered[0]["available_at"] == "2026-07-02T14:37:00.345678Z"
    receipts = [json.loads(line) for line in stage_path.read_text().splitlines()]
    assert [row["kind"] for row in receipts] == ["decision", "availability"]

    drifted = dict(replay)
    drifted["premium"] += 1
    with pytest.raises(RuntimeError, match="staged event drift"):
        poller._stage_raw_events("2026-07-02", [drifted])


def test_raw_stage_and_publisher_reject_physical_receipt_reordering(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    available_at = event.pop("available_at")
    for key in ("published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    receipts = [
        {
            "schema": "live_flow.event_stage/v1", "kind": "availability",
            "event_id": event["id"], "available_at": available_at,
        },
        {
            "schema": "live_flow.event_stage/v1", "kind": "decision",
            "event_id": event["id"], "event": event,
        },
    ]
    path = tmp_path / "2026-07-02.jsonl"
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in receipts))
    with pytest.raises(RuntimeError, match="precedes decision"):
        poller._stage_raw_events("2026-07-02", [event])

    calls = []
    monkeypatch.setattr(
        poller, "_upload_r2",
        lambda _s3, _bucket, _path, key: calls.append(key) or True,
    )
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == []


def test_poller_clock_preserves_microseconds_and_rejects_naive_time() -> None:
    from scripts import live_flow_poller as poller

    fixed = datetime(2026, 7, 2, 14, 31, 0, 999999, tzinfo=timezone.utc)
    assert poller._utc_now_iso(lambda: fixed) == "2026-07-02T14:31:00.999999Z"
    with pytest.raises(RuntimeError, match="timezone-aware"):
        poller._utc_now_iso(lambda: datetime(2026, 7, 2, 14, 31))


def test_raw_stage_rejects_availability_before_decision(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event(decision_at="2026-07-02T14:34:00Z")
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    with pytest.raises(RuntimeError, match="availability predates decision"):
        poller._stage_raw_events(
            "2026-07-02", [event],
            now_fn=lambda: datetime(2026, 7, 2, 14, 33, tzinfo=timezone.utc),
        )
    receipts = [json.loads(line) for line in (tmp_path / "2026-07-02.jsonl").read_text().splitlines()]
    assert [row["kind"] for row in receipts] == ["decision"]


def test_raw_stage_admits_same_date_post_close_clocks_but_rejects_stale_date(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    stage_root = tmp_path / "post-close"
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(stage_root))
    event = _event(
        id="post-close-stage",
        ts="2026-07-02T19:59:00Z",
        observed_at="2026-07-02T20:00:01Z",
        decision_at="2026-07-02T20:00:02Z",
    )
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    staged = poller._stage_raw_events(
        "2026-07-02", [event],
        now_fn=lambda: datetime(2026, 7, 2, 20, 0, 3, tzinfo=timezone.utc),
    )
    assert staged[0]["available_at"] == "2026-07-02T20:00:03Z"

    wrong_clock_root = tmp_path / "wrong-clock"
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(wrong_clock_root))
    wrong_clock = dict(event)
    wrong_clock["id"] = "next-date-clock"
    wrong_clock["observed_at"] = "2026-07-03T13:30:00Z"
    wrong_clock["decision_at"] = "2026-07-03T13:30:01Z"
    with pytest.raises(RuntimeError, match="decision clocks leave stage date"):
        poller._stage_raw_events(
            "2026-07-02", [wrong_clock],
            now_fn=lambda: datetime(2026, 7, 3, 13, 30, 2, tzinfo=timezone.utc),
        )
    assert not (wrong_clock_root / "2026-07-02.jsonl").exists()

    stale_root = tmp_path / "stale-invocation"
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(stale_root))
    same_date_decision = dict(event)
    same_date_decision["id"] = "stale-invocation"
    with pytest.raises(RuntimeError, match="staging clock is outside session date"):
        poller._stage_raw_events(
            "2026-07-02", [same_date_decision],
            now_fn=lambda: datetime(2026, 7, 3, 13, 30, tzinfo=timezone.utc),
        )
    assert not (stale_root / "2026-07-02.jsonl").exists()


def test_learning_stage_partitions_regular_and_early_close_boundaries(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    regular = [
        _event(id="before-close", ts="2026-07-02T19:59:59.999999Z"),
        _event(id="at-close", ts="2026-07-02T20:00:00Z"),
        _event(id="after-close", ts="2026-07-02T20:00:00.000001Z"),
    ]
    eligible, display_only = poller._partition_learning_stage_events(
        "2026-07-02", regular,
    )
    assert [row["id"] for row in eligible] == ["before-close"]
    assert [row["id"] for row in display_only] == ["at-close", "after-close"]

    early_close = [
        _event(id="early-before", ts="2026-11-27T17:59:59.999999Z"),
        _event(id="early-at", ts="2026-11-27T18:00:00Z"),
    ]
    eligible, display_only = poller._partition_learning_stage_events(
        "2026-11-27", early_close,
    )
    assert [row["id"] for row in eligible] == ["early-before"]
    assert [row["id"] for row in display_only] == ["early-at"]

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    at_close = dict(regular[1])
    at_close["observed_at"] = "2026-07-02T20:00:01Z"
    at_close["decision_at"] = "2026-07-02T20:00:02Z"
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        at_close.pop(key, None)
    with pytest.raises(RuntimeError, match="outside the regular-session learning window"):
        poller._stage_raw_events(
            "2026-07-02", [at_close],
            now_fn=lambda: datetime(2026, 7, 2, 20, 0, 3, tzinfo=timezone.utc),
        )
    assert not (tmp_path / "2026-07-02.jsonl").exists()

    weekend_root = tmp_path / "weekend"
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(weekend_root))
    weekend = _event(
        id="weekend", ts="2026-07-04T14:30:00Z",
        observed_at="2026-07-04T14:31:00Z",
        decision_at="2026-07-04T14:31:30Z",
    )
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        weekend.pop(key, None)
    with pytest.raises(RuntimeError, match="not an NYSE session"):
        poller._stage_raw_events(
            "2026-07-04", [weekend],
            now_fn=lambda: datetime(2026, 7, 4, 14, 32, tzinfo=timezone.utc),
        )
    assert not (weekend_root / "2026-07-04.jsonl").exists()


def test_run_cycle_keeps_close_boundary_print_display_only(
    monkeypatch,
) -> None:
    from engine import live_flow as live_engine
    from scripts import live_flow_poller as poller

    frame = pd.DataFrame([{"trade_timestamp": "2026-07-02T20:00:00Z"}])
    monkeypatch.setattr(
        "collectors.thetadata.bulk_trade_quote",
        lambda _root, right, *_args, **_kwargs: frame.copy() if right == "call" else pd.DataFrame(),
    )
    monkeypatch.setattr(poller, "_load_oi_prev", lambda *_args: None)
    monkeypatch.setattr(poller, "_load_prev_close", lambda *_args: None)

    boundary_event = {
        "id": "display-close-boundary",
        "ts": "2026-07-02T20:00:00Z",
        "observed_at": "2026-07-02T20:00:01Z",
    }

    def fake_process_batch(**kwargs):
        return {
            "state": kwargs["prior_state"],
            "events": [copy.deepcopy(boundary_event)],
            "heat": [], "unusual_names": [], "meta_notes": [],
        }

    monkeypatch.setattr(live_engine, "process_batch", fake_process_batch)
    real_datetime = datetime
    fixed_now = real_datetime(2026, 7, 2, 20, 0, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(
        poller, "datetime",
        type("FakeDT", (), {
            "now": staticmethod(lambda tz=None: fixed_now),
            "strptime": real_datetime.strptime,
            "fromisoformat": real_datetime.fromisoformat,
            "fromtimestamp": real_datetime.fromtimestamp,
        }),
    )

    def must_not_stage(*_args, **_kwargs):
        raise AssertionError("close-boundary display event must not reach PIT stage")

    feed, _heat, meta, _state, _tide = poller.run_cycle(
        roots=["TEST"], session_date="2026-07-02", delta_mode="full_day",
        day_state={}, baselines={},
        cfg={
            "max_concurrent": 2, "etf_floor": 0, "name_floor": 0,
            "etf_anchors": ["TEST"], "retention_hours": 24,
        },
        cycle_watermarks={}, event_stager=must_not_stage,
    )
    assert [row["id"] for row in feed["events"]] == ["display-close-boundary"]
    assert "pit_learning_stage_excluded_outside_rth=1" in meta["notes"]


@pytest.mark.parametrize("bad_id", [123, " source-event-1", "source-event-1 ", ""])
def test_raw_stage_rejects_noncanonical_event_id_before_file_creation(
    tmp_path: Path, monkeypatch, bad_id: object,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event(id=bad_id)
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    with pytest.raises(RuntimeError, match="normalized string id"):
        poller._stage_raw_events(
            "2026-07-02", [event],
            now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
        )
    assert not (tmp_path / "2026-07-02.jsonl").exists()


def test_poller_stage_strips_split_clock_fields_and_builder_consumes_bytes(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    # The display-shaped event includes every downstream-only clock field. The
    # durable decision receipt must own none of them; availability is a separate
    # post-fsync receipt and the builder reconstructs the envelope explicitly.
    staged = poller._stage_raw_events(
        "2026-07-02", [_event()],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )
    assert staged[0]["anchor_strategy"] == "durable_available_at"
    records = [json.loads(line) for line in (tmp_path / "2026-07-02.jsonl").read_text().splitlines()]
    assert not {
        "available_at", "published_at", "source_snapshot_asof", "anchor_strategy",
    }.intersection(records[0]["event"])
    events = builder._events_from_stage(records, expected_session_date="2026-07-02")
    assert events[0]["anchor_strategy"] == "durable_available_at"
    assert events[0]["available_at"] == staged[0]["available_at"]


@pytest.mark.parametrize("bad_event_id", [1, True])
def test_event_publisher_rejects_nonstring_receipt_id_without_r2(
    tmp_path: Path, monkeypatch, bad_event_id: object,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event(id=str(bad_event_id))
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    records = [
        {
            "schema": "live_flow.event_stage/v1", "kind": "decision",
            "event_id": bad_event_id, "event": event,
        },
        {
            "schema": "live_flow.event_stage/v1", "kind": "availability",
            "event_id": bad_event_id, "available_at": "2026-07-02T14:32:00Z",
        },
    ]
    (tmp_path / "2026-07-02.jsonl").write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records)
    )
    calls: list[str] = []
    monkeypatch.setattr(
        poller, "_upload_r2",
        lambda _s3, _bucket, _path, key: calls.append(key) or True,
    )
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == []


def test_event_publisher_rejects_duplicate_json_keys_without_r2(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    event_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
    decision = (
        '{"schema":"live_flow.event_stage/v1","kind":"decision",'
        '"event_id":"source-event-1","event_id":"source-event-1","event":'
        + event_json + "}\n"
    )
    availability = json.dumps({
        "schema": "live_flow.event_stage/v1", "kind": "availability",
        "event_id": "source-event-1", "available_at": "2026-07-02T14:32:00Z",
    }, separators=(",", ":")) + "\n"
    (tmp_path / "2026-07-02.jsonl").write_text(decision + availability)
    calls: list[str] = []
    monkeypatch.setattr(
        poller, "_upload_r2",
        lambda _s3, _bucket, _path, key: calls.append(key) or True,
    )
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == []

    # The same strict decoder guards local publication proof state.
    (tmp_path / "2026-07-02.jsonl").unlink()
    poller._stage_raw_events(
        "2026-07-02", [event],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )
    (tmp_path / "published.json").write_text(
        '{"schema":"wrong","schema":"live_flow.event_publications/v1","objects":{}}\n'
    )
    calls.clear()
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == []


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_raw_stage_and_builder_reject_nonstandard_json_constants_atomically(
    tmp_path: Path, monkeypatch, nonfinite: float,
) -> None:
    from scripts import build_options_signal_episode as builder
    from scripts import live_flow_poller as poller

    event = _event(unused_fact=nonfinite)
    stage_event = dict(event)
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        stage_event.pop(key, None)
    stage_root = tmp_path / "stage"
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(stage_root))
    with pytest.raises(RuntimeError, match="strict finite JSON"):
        poller._stage_raw_events(
            "2026-07-02", [stage_event],
            now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
        )
    assert not (stage_root / "2026-07-02.jsonl").exists()

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    repo = tmp_path / "repo"
    with pytest.raises(ContractError, match="non-finite JSON"):
        builder.run(
            root_dir=repo,
            stages_by_session={"2026-07-02": _stage_records(event)},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    ledger_root = repo / "data/options_signal_episode"
    assert not (ledger_root / "episodes.jsonl").exists()
    assert not (ledger_root / "outcomes_h60.jsonl").exists()
    assert not (ledger_root / "checkpoint.json").exists()


def test_raw_stage_upload_failure_does_not_invent_publication(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    staged = poller._stage_raw_events(
        "2026-07-02", [event],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )

    class BrokenS3:
        def upload_file(self, *args, **kwargs):
            raise OSError("offline")

    assert poller._upload_r2(
        BrokenS3(), "bucket", tmp_path / "2026-07-02.jsonl",
        "live_flow/events/2026-07-02.jsonl",
    ) is False
    assert staged[0]["published_at"] is None


def test_event_stage_publish_orders_stage_before_index_and_stops_on_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    poller._stage_raw_events(
        "2026-07-02", [event],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )

    calls = []

    def success(_s3, _bucket, _path, key):
        calls.append(key)
        return True

    monkeypatch.setattr(poller, "_upload_r2", success)
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is True
    assert calls == [
        "live_flow/events/2026-07-02.jsonl",
        "live_flow/events/dates.json",
    ]

    failed_root = tmp_path / "failed"
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(failed_root))
    poller._stage_raw_events(
        "2026-07-02", [event],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )
    calls.clear()

    def fail_stage(_s3, _bucket, _path, key):
        calls.append(key)
        return False

    monkeypatch.setattr(poller, "_upload_r2", fail_stage)
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == ["live_flow/events/2026-07-02.jsonl"]


def test_event_index_never_advertises_an_unpublished_prior_session(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    day_one = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        day_one.pop(key, None)
    poller._stage_raw_events(
        "2026-07-02", [day_one],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )

    calls = []

    def day_one_fails(_s3, _bucket, _path, key):
        calls.append(key)
        return key != "live_flow/events/2026-07-02.jsonl"

    monkeypatch.setattr(poller, "_upload_r2", day_one_fails)
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == ["live_flow/events/2026-07-02.jsonl"]
    assert not (tmp_path / "dates.json").exists()

    day_two = _event(
        id="source-event-day-two",
        ts="2026-07-06T14:30:00Z",
        observed_at="2026-07-06T14:31:00Z",
        decision_at="2026-07-06T14:32:00Z",
    )
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        day_two.pop(key, None)
    poller._stage_raw_events(
        "2026-07-06", [day_two],
        now_fn=lambda: datetime(2026, 7, 6, 14, 33, tzinfo=timezone.utc),
    )
    calls.clear()
    assert poller._publish_event_stage(object(), "bucket", "2026-07-06") is True
    assert calls == [
        "live_flow/events/2026-07-02.jsonl",
        "live_flow/events/2026-07-06.jsonl",
        "live_flow/events/dates.json",
    ]
    index = json.loads((tmp_path / "dates.json").read_text())
    assert index["sessions"] == ["2026-07-06"]
    receipts = json.loads((tmp_path / "published.json").read_text())
    assert sorted(receipts["objects"]) == ["2026-07-06"]


def test_quiet_current_session_retries_and_advertises_prior_stage(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    prior = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        prior.pop(key, None)
    poller._stage_raw_events(
        "2026-07-02", [prior],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )

    calls: list[str] = []

    def fail_prior(_s3, _bucket, _path, key):
        calls.append(key)
        return False

    monkeypatch.setattr(poller, "_upload_r2", fail_prior)
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == ["live_flow/events/2026-07-02.jsonl"]

    calls.clear()
    monkeypatch.setattr(
        poller, "_upload_r2",
        lambda _s3, _bucket, _path, key: calls.append(key) or True,
    )
    # 2026-07-06 is a valid NYSE session with no notable event/stage file.
    assert not (tmp_path / "2026-07-06.jsonl").exists()
    assert poller._publish_event_stage(object(), "bucket", "2026-07-06") is True
    assert calls == [
        "live_flow/events/2026-07-02.jsonl",
        "live_flow/events/dates.json",
    ]
    assert json.loads((tmp_path / "dates.json").read_text())["sessions"] == [
        "2026-07-02",
    ]


def test_quiet_session_reports_unproven_torn_history_as_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    prior = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        prior.pop(key, None)
    poller._stage_raw_events(
        "2026-07-02", [prior],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(poller, "_upload_r2", lambda *_args: True)
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is True

    (tmp_path / "2026-07-06.jsonl").write_bytes(b'{"torn":true}')
    calls: list[str] = []
    monkeypatch.setattr(
        poller, "_upload_r2",
        lambda _s3, _bucket, _path, key: calls.append(key) or True,
    )
    assert poller._publish_event_stage(object(), "bucket", "2026-07-07") is False
    assert calls == ["live_flow/events/dates.json"]
    assert (tmp_path / "2026-07-06.jsonl").exists()


@pytest.mark.parametrize(
    "receipt_payload",
    [
        {
            "schema": "live_flow.event_publications/v1",
            "objects": {
                "9999-99-99": {"bytes": 1, "sha256": "a" * 64},
            },
        },
        {
            "schema": "live_flow.event_publications/v1",
            "objects": {
                "2026-07-04": {"bytes": 1, "sha256": "a" * 64},
            },
        },
        {
            "schema": "live_flow.event_publications/v1",
            "objects": {},
            "unexpected": True,
        },
    ],
)
def test_event_publisher_fails_closed_on_impossible_receipt_state(
    tmp_path: Path, monkeypatch, receipt_payload: dict,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    event = _event()
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        event.pop(key, None)
    poller._stage_raw_events(
        "2026-07-02", [event],
        now_fn=lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc),
    )
    (tmp_path / "published.json").write_text(json.dumps(receipt_payload) + "\n")
    calls: list[str] = []
    monkeypatch.setattr(
        poller, "_upload_r2",
        lambda _s3, _bucket, _path, key: calls.append(key) or True,
    )

    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert calls == []


def test_event_stage_publish_fast_paths_proven_history_and_prunes_to_64(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))
    sessions = [
        stamp.date().isoformat()
        for stamp in pd.date_range("2026-01-05", periods=110)
        if poller.nyse_calendar.is_session(stamp.date())
    ][:66]
    for session_date in sessions:
        event = _event(
            id=f"retention-{session_date}",
            ts=f"{session_date}T14:30:00Z",
            observed_at=f"{session_date}T14:31:00Z",
            decision_at=f"{session_date}T14:31:30Z",
        )
        for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
            event.pop(key, None)
        poller._stage_raw_events(
            session_date, [event],
            now_fn=lambda value=session_date: datetime.fromisoformat(
                f"{value}T14:32:00+00:00"
            ),
        )

    monkeypatch.setattr(poller, "_upload_r2", lambda *_args: True)
    current = sessions[-1]
    assert poller._publish_event_stage(object(), "bucket", current) is True

    retained_files = sorted(path.stem for path in tmp_path.glob("????-??-??.jsonl"))
    assert retained_files == sessions[-64:]
    receipts = json.loads((tmp_path / "published.json").read_text())
    assert sorted(receipts["objects"]) == sessions[-64:]
    index = json.loads((tmp_path / "dates.json").read_text())
    assert index["sessions"] == sessions[-64:]

    original_parser = poller._parse_event_stage_bytes
    parsed_sessions: list[str] = []

    def counting_parser(session_date, *args, **kwargs):
        parsed_sessions.append(session_date)
        return original_parser(session_date, *args, **kwargs)

    monkeypatch.setattr(poller, "_parse_event_stage_bytes", counting_parser)
    assert poller._publish_event_stage(object(), "bucket", current) is True
    assert parsed_sessions == [current]

    # A failed extension outside the newest-64 window must retain both its
    # local suffix and the older remote-prefix fence.
    pending_old = sessions[-64]
    pending_event = _event(
        id=f"pending-extension-{pending_old}",
        ts=f"{pending_old}T14:35:00Z",
        observed_at=f"{pending_old}T14:36:00Z",
        decision_at=f"{pending_old}T14:36:30Z",
    )
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        pending_event.pop(key, None)
    poller._stage_raw_events(
        pending_old, [pending_event],
        now_fn=lambda: datetime.fromisoformat(f"{pending_old}T14:37:00+00:00"),
    )
    next_sessions = [
        stamp.date().isoformat()
        for stamp in pd.date_range(pd.Timestamp(current) + pd.Timedelta(days=1), periods=10)
        if poller.nyse_calendar.is_session(stamp.date())
    ][:2]
    for session_date in next_sessions:
        event = _event(
            id=f"new-retention-{session_date}",
            ts=f"{session_date}T14:30:00Z",
            observed_at=f"{session_date}T14:31:00Z",
            decision_at=f"{session_date}T14:31:30Z",
        )
        for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
            event.pop(key, None)
        poller._stage_raw_events(
            session_date, [event],
            now_fn=lambda value=session_date: datetime.fromisoformat(
                f"{value}T14:32:00+00:00"
            ),
        )

    def fail_old_extension(_s3, _bucket, _path, key):
        return key != f"live_flow/events/{pending_old}.jsonl"

    monkeypatch.setattr(poller, "_upload_r2", fail_old_extension)
    assert poller._publish_event_stage(object(), "bucket", next_sessions[-1]) is True
    assert (tmp_path / f"{pending_old}.jsonl").exists()
    retained_proofs = json.loads((tmp_path / "published.json").read_text())["objects"]
    assert pending_old in retained_proofs
    assert retained_proofs[pending_old]["bytes"] < (
        tmp_path / f"{pending_old}.jsonl"
    ).stat().st_size


def test_event_stage_publication_enforces_monotonic_prefix(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))

    def stage(event: dict, minute: int) -> None:
        row = dict(event)
        for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
            row.pop(key, None)
        poller._stage_raw_events(
            "2026-07-02", [row],
            now_fn=lambda: datetime(2026, 7, 2, 14, minute, tzinfo=timezone.utc),
        )

    stage(_event(id="prefix-one"), 32)
    uploaded: list[tuple[str, bytes]] = []

    def capture(_s3, _bucket, path, key):
        uploaded.append((key, Path(path).read_bytes()))
        return True

    monkeypatch.setattr(poller, "_upload_r2", capture)
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is True
    stage_path = tmp_path / "2026-07-02.jsonl"
    initial = stage_path.read_bytes()
    initial_receipt = json.loads((tmp_path / "published.json").read_text())["objects"]["2026-07-02"]

    same_size_rewrite = initial.replace(b'"strike":105.0', b'"strike":106.0', 1)
    assert len(same_size_rewrite) == len(initial) and same_size_rewrite != initial
    stage_path.write_bytes(same_size_rewrite)
    uploaded.clear()
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert not any(key.endswith("/2026-07-02.jsonl") for key, _raw in uploaded)
    assert json.loads((tmp_path / "published.json").read_text())["objects"]["2026-07-02"] == initial_receipt

    stage_path.write_bytes(initial)
    stage(_event(id="prefix-two", strike=110.0), 33)
    extended = stage_path.read_bytes()
    uploaded.clear()
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is True
    extended_receipt = json.loads((tmp_path / "published.json").read_text())["objects"]["2026-07-02"]
    assert extended_receipt == {
        "bytes": len(extended), "sha256": hashlib.sha256(extended).hexdigest(),
    }

    stage_path.write_bytes(initial)
    uploaded.clear()
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert not any(key.endswith("/2026-07-02.jsonl") for key, _raw in uploaded)
    assert json.loads((tmp_path / "published.json").read_text())["objects"]["2026-07-02"] == extended_receipt

    changed_prefix_growth = same_size_rewrite + extended[len(initial):]
    stage_path.write_bytes(changed_prefix_growth)
    uploaded.clear()
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is False
    assert not any(key.endswith("/2026-07-02.jsonl") for key, _raw in uploaded)
    assert json.loads((tmp_path / "published.json").read_text())["objects"]["2026-07-02"] == extended_receipt


def test_event_stage_upload_uses_immutable_validated_snapshot(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import live_flow_poller as poller

    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path))

    def raw_event(event: dict) -> dict:
        row = dict(event)
        for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
            row.pop(key, None)
        return row

    first = raw_event(_event(id="race-one"))
    second = raw_event(_event(id="race-two", strike=110.0))
    clock = lambda: datetime(2026, 7, 2, 14, 32, tzinfo=timezone.utc)
    poller._stage_raw_events("2026-07-02", [first], now_fn=clock)
    uploaded_stage: list[bytes] = []
    injected = False

    def upload_with_concurrent_append(_s3, _bucket, path, key):
        nonlocal injected
        payload = Path(path).read_bytes()
        if key.endswith("/2026-07-02.jsonl"):
            uploaded_stage.append(payload)
            if not injected:
                injected = True
                poller._stage_raw_events("2026-07-02", [second], now_fn=clock)
        return True

    monkeypatch.setattr(poller, "_upload_r2", upload_with_concurrent_append)
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is True
    receipt = json.loads((tmp_path / "published.json").read_text())["objects"]["2026-07-02"]
    assert receipt == {
        "bytes": len(uploaded_stage[0]),
        "sha256": hashlib.sha256(uploaded_stage[0]).hexdigest(),
    }
    local_after_race = (tmp_path / "2026-07-02.jsonl").read_bytes()
    assert len(local_after_race) > receipt["bytes"]

    injected = True
    assert poller._publish_event_stage(object(), "bucket", "2026-07-02") is True
    updated_receipt = json.loads((tmp_path / "published.json").read_text())["objects"]["2026-07-02"]
    assert updated_receipt["bytes"] == len(local_after_race)
    assert updated_receipt["sha256"] == hashlib.sha256(local_after_race).hexdigest()
    assert not list(tmp_path.glob(".publish-*.jsonl"))


def test_json_schema_documents_accept_runtime_rows(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    repo = Path(__file__).resolve().parent.parent
    episode_schema = json.loads(
        (repo / "contracts/options/options.signal_episode.v1.schema.json").read_text()
    )
    outcome_schema = json.loads(
        (repo / "contracts/options/options.signal_episode_outcome.v1.schema.json").read_text()
    )
    receipt_schema = json.loads(
        (repo / "contracts/options/polygon.intraday_price_receipt.v1.schema.json").read_text()
    )
    for schema in (episode_schema, outcome_schema, receipt_schema):
        jsonschema.Draft202012Validator.check_schema(schema)
    episode = _episode()
    outcome = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture",
        bar_seconds=3600,
        price_delay_minutes=15,
    )
    jsonschema.Draft202012Validator(episode_schema).validate(episode)
    jsonschema.Draft202012Validator(outcome_schema).validate(outcome)
    intraday = tmp_path / "intraday"
    intraday.mkdir()
    _write_receipted_price_source(
        intraday,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
    )
    receipt = json.loads((intraday / "TEST.parquet.receipt.json").read_text())
    receipt_validator = jsonschema.Draft202012Validator(
        receipt_schema, format_checker=jsonschema.FormatChecker(),
    )
    receipt_validator.validate(receipt)
    poisoned_receipt = {**receipt, "source_file_sha256": "NOT-A-DIGEST"}
    assert list(receipt_validator.iter_errors(poisoned_receipt))
    null_complete = copy.deepcopy(outcome)
    null_complete["measurement"]["window"] = {"start": None, "end": None}
    for key in (
        "entry_time", "exit_time", "entry_price", "exit_price", "ret", "mfe", "mae",
        "entry_delay_minutes", "exit_delay_minutes", "bar_seconds", "path_basis",
    ):
        null_complete["underlying"][key] = None
    assert list(jsonschema.Draft202012Validator(outcome_schema).iter_errors(null_complete))


def test_builder_writes_split_ledgers_and_replays_cleanly(tmp_path: Path, monkeypatch) -> None:
    from scripts import build_options_signal_episode as builder

    data = tmp_path / "data"
    intraday = data / "intraday"
    intraday.mkdir(parents=True)
    price_frame = _bars(
        ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
        ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
    )
    _write_receipted_price_source(intraday, price_frame)
    feed = {
        "schema": "live_flow.feed/v1",
        "asof": "2026-07-02T20:01:00Z",
        "session_date": "2026-07-02",
        "events": [_event()],
    }
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = builder.run(
        root_dir=tmp_path,
        feed=feed,
        stage_records=_stage_records(),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    second = builder.run(
        root_dir=tmp_path,
        feed=feed,
        stage_records=_stage_records(),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    assert first["episodes_appended"] == 1
    assert first["outcomes_appended"] == 1
    assert second["episodes_appended"] == 0
    assert second["outcomes_appended"] == 0
    assert len(load_jsonl(data / "options_signal_episode/episodes.jsonl")) == 1
    assert len(load_jsonl(data / "options_signal_episode/outcomes_h60.jsonl")) == 1
    stored_outcome = load_jsonl(data / "options_signal_episode/outcomes_h60.jsonl")[0]
    assert stored_outcome["provenance"]["price_delay_minutes"] == 15
    assert stored_outcome["provenance"]["price_source"] == "data/intraday/TEST.parquet"
    checkpoint = json.loads(
        (data / "options_signal_episode/checkpoint.json").read_text()
    )
    assert checkpoint["sessions"]["2026-07-02"]["records"] == 2

    drifted_stage = _stage_records()
    drifted_stage[0]["event"]["premium"] += 1
    with pytest.raises(ContractError, match="prefix changed"):
        builder.run(
            root_dir=tmp_path,
            feed=feed,
            stage_records=drifted_stage,
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )


def test_builder_allows_legacy_price_without_receipt_while_other_ticker_accrues(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    data = tmp_path / "data"
    intraday = data / "intraday"
    intraday.mkdir(parents=True)
    price_frame = _bars(
        ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
        ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
    )
    _write_receipted_price_source(intraday, price_frame, ticker="TEST")
    price_frame.to_parquet(intraday / "LEGACY.parquet")
    test_event = _event(id="receipted-test")
    legacy_event = _event(id="legacy-without-receipt", root="LEGACY")
    stages = _stage_records(test_event) + _stage_records(legacy_event)

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    summary = builder.run(
        root_dir=tmp_path,
        stages_by_session={"2026-07-02": stages},
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    assert summary["episodes_appended"] == 2
    assert summary["outcomes_appended"] == 1
    assert summary["outcomes_pending"] == 1
    assert summary["pending_reasons"] == {"missing_price_receipt": 1}
    outcomes = load_jsonl(data / "options_signal_episode/outcomes_h60.jsonl")
    assert [row["episode_id"] for row in outcomes] == [
        _episode(id="receipted-test")["episode_id"]
    ]
    checkpoint = json.loads(
        (data / "options_signal_episode/checkpoint.json").read_text()
    )
    assert checkpoint["sessions"]["2026-07-02"]["records"] == 4


@pytest.mark.parametrize("cache_state", [
    "absent", "receipt_without_source", "torn_receipt_with_source",
])
def test_builder_persists_clock_terminal_outcome_without_reading_price_cache(
    tmp_path: Path, monkeypatch, cache_state: str,
) -> None:
    from scripts import build_options_signal_episode as builder

    intraday = tmp_path / "data/intraday"
    intraday.mkdir(parents=True)
    if cache_state == "receipt_without_source":
        (intraday / "TEST.parquet.receipt.json").write_text("{}\n")
    elif cache_state == "torn_receipt_with_source":
        (intraday / "TEST.parquet").write_bytes(b"not-a-parquet")
        (intraday / "TEST.parquet.receipt.json").write_text("{torn")
    late_event = _event(
        id="late-clock-terminal",
        ts="2026-07-02T19:10:00Z",
        observed_at="2026-07-02T19:11:00Z",
        decision_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
        source_snapshot_asof="2026-07-02T19:11:00Z",
    )
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    summary = builder.run(
        root_dir=tmp_path,
        stages_by_session={"2026-07-02": _stage_records(late_event)},
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    assert summary["outcomes_terminal_incomplete"] == 1
    assert summary["outcomes_pending"] == 0
    outcomes = load_jsonl(
        tmp_path / "data/options_signal_episode/outcomes_h60.jsonl"
    )
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "incomplete"
    assert outcomes[0]["reason"] == "horizon_crosses_session_close"


def test_builder_caches_one_session_snapshot_error_across_all_horizons(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    late_event = _event(
        id="late-h60-terminal-session-retry",
        ts="2026-07-02T19:10:00Z",
        observed_at="2026-07-02T19:11:00Z",
        decision_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
        source_snapshot_asof="2026-07-02T19:11:00Z",
    )
    reads = 0

    def corrupt_snapshot(*_args, **_kwargs):
        nonlocal reads
        reads += 1
        raise ContractError("invalid price snapshot for TEST: injected")

    monkeypatch.setattr(builder, "_price_snapshot", corrupt_snapshot)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    summary = builder.run(
        root_dir=tmp_path,
        stages_by_session={"2026-07-02": _stage_records(late_event)},
        computed_at=datetime(2026, 7, 20, 22, 0, tzinfo=timezone.utc),
    )
    assert reads == 1
    assert summary["outcomes_terminal_incomplete"] == 1
    assert summary["session_outcomes_pending"] == 5
    assert summary["session_pending_reasons"] == {"invalid_price_receipt": 5}
    assert (tmp_path / "data/options_signal_episode/checkpoint.json").exists()


def test_builder_still_rejects_present_malformed_price_receipt(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    intraday = tmp_path / "data/intraday"
    intraday.mkdir(parents=True)
    price_frame = _bars(
        ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
        ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
    )
    _write_receipted_price_source(intraday, price_frame)
    (intraday / "TEST.parquet.receipt.json").write_text("{torn")
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(ContractError, match="invalid price snapshot for TEST"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": _stage_records()},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    assert not (
        tmp_path / "data/options_signal_episode/checkpoint.json"
    ).exists()


def test_builder_records_exact_external_intraday_source_path(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "external_vendor_cache"
    external.mkdir()
    price_frame = _bars(
        ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
        ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
    )
    _write_receipted_price_source(external, price_frame)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setenv("MACRO_INTRADAY_DIR", str(external))
    summary = builder.run(
        root_dir=repo,
        feed={"session_date": "2026-07-02"},
        stage_records=_stage_records(),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    assert summary["outcomes_appended"] == 1
    outcome = load_jsonl(
        repo / "data/options_signal_episode/outcomes_h60.jsonl"
    )[0]
    assert outcome["provenance"]["price_source"] == (
        external / "TEST.parquet"
    ).resolve().as_posix()


def test_builder_rejects_misanchored_existing_outcome_before_any_advance(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    event = _event(
        id="misanchored-outcome",
        ts="2026-07-02T19:10:00Z",
        observed_at="2026-07-02T19:11:00Z",
        decision_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
    )
    episode = _episode(
        id="misanchored-outcome",
        ts="2026-07-02T19:10:00Z",
        observed_at="2026-07-02T19:11:00Z",
        decision_at="2026-07-02T19:11:00Z",
        available_at="2026-07-02T19:11:00Z",
    )
    true_outcome = derive_h60_outcome(
        episode, None,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture", bar_seconds=60, price_delay_minutes=1,
    )
    reason_drift = copy.deepcopy(true_outcome)
    reason_drift["reason"] = "decision_after_session_close"
    validate_outcome(reason_drift)
    with pytest.raises(ContractError, match="terminal outcome reason disagrees"):
        validate_outcome_against_episode(reason_drift, episode)

    outcome = copy.deepcopy(true_outcome)
    outcome["horizon_anchor"] = "2026-07-02T14:00:00Z"
    outcome["target_time"] = "2026-07-02T15:00:00Z"
    outcome["matured_at"] = "2026-07-02T15:00:00Z"
    validate_outcome(outcome)
    with pytest.raises(ContractError, match="horizon_anchor must equal"):
        validate_outcome_against_episode(outcome, episode)

    ledger_root = tmp_path / "data/options_signal_episode"
    ledger_root.mkdir(parents=True)
    episode_path = ledger_root / "episodes.jsonl"
    outcome_path = ledger_root / "outcomes_h60.jsonl"
    episode_bytes = json.dumps(episode, sort_keys=True, separators=(",", ":")) + "\n"
    outcome_bytes = json.dumps(outcome, sort_keys=True, separators=(",", ":")) + "\n"
    episode_path.write_text(episode_bytes)
    outcome_path.write_text(outcome_bytes)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(ContractError, match="horizon_anchor must equal"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": _stage_records(event)},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    assert episode_path.read_text() == episode_bytes
    assert outcome_path.read_text() == outcome_bytes
    assert not (ledger_root / "checkpoint.json").exists()


def test_builder_catches_up_missed_session_in_order(tmp_path: Path, monkeypatch) -> None:
    from scripts import build_options_signal_episode as builder

    day_one = _event(id="day-one")
    day_two = _event(
        id="day-two",
        ts="2026-07-06T14:30:00Z",
        observed_at="2026-07-06T14:31:00Z",
        decision_at="2026-07-06T14:31:00Z",
        available_at="2026-07-06T14:31:00Z",
        source_snapshot_asof="2026-07-06T14:31:30Z",
        oi_vintage="2026-07-02",
        dte=11,
    )
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    summary = builder.run(
        root_dir=tmp_path,
        stages_by_session={
            "2026-07-06": _stage_records(day_two),
            "2026-07-02": _stage_records(day_one),
        },
        computed_at=datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc),
    )
    assert summary["sessions_processed"] == ["2026-07-02", "2026-07-06"]
    assert summary["episodes_appended"] == 2
    checkpoint = json.loads(
        (tmp_path / "data/options_signal_episode/checkpoint.json").read_text()
    )
    assert sorted(checkpoint["sessions"]) == ["2026-07-02", "2026-07-06"]


def test_checkpoint_merges_concurrent_session_writers_without_loss(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    checkpoint = tmp_path / "data/options_signal_episode/checkpoint.json"
    sessions = [
        "2026-07-02", "2026-07-06", "2026-07-07", "2026-07-08",
        "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14",
        "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20",
    ]

    def advance(session_date: str) -> None:
        records = _stage_records(_event(id=f"checkpoint-{session_date}"))
        builder._advance_checkpoint(
            checkpoint, session_date, records, dry_run=False,
        )

    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        list(pool.map(advance, sessions))

    stored = json.loads(checkpoint.read_text())
    assert sorted(stored["sessions"]) == sessions
    assert not list(checkpoint.parent.glob(".checkpoint.json.*.tmp"))


def test_checkpoint_crash_temp_is_gitignored() -> None:
    repo = Path(__file__).resolve().parents[1]
    target = "data/options_signal_episode/.checkpoint.json.crash-window.tmp"
    checked = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", target],
        cwd=repo,
        check=False,
    )
    assert checked.returncode == 0, (
        "a killed checkpoint replace must not be swept into the nightly git add data/"
    )


def test_options_pit_engine_and_adversarial_suites_are_ci_wired() -> None:
    repo = Path(__file__).resolve().parents[1]
    workflow = (repo / ".github/workflows/ci.yml").read_text()
    manifest = (repo / ".github/ci/legacy-jobs.yml").read_text()
    for required in (
        '"engine/options_signal_episode.py"',
        '"engine/options_signal_campaign.py"',
        '"contracts/options/options.signal_episode_session_outcome.v1.schema.json"',
        '"contracts/options/options.signal_campaign.v1.schema.json"',
        '"contracts/options/options.signal_campaign.v2.schema.json"',
        '"contracts/options/options.signal_campaign_outcome.v1.schema.json"',
        '"contracts/options/options.signal_campaign_checkpoint.v1.schema.json"',
        '"data/options_signal_episode/campaigns.jsonl"',
        '"data/options_signal_campaign/**"',
        '"research/options_estate/OPTIONS_SIGNAL_CAMPAIGNS_PREREG.md"',
        '"research/options_estate/OPTIONS_SIGNAL_CAMPAIGN_V2_PREREG.md"',
        '"ops/LIVE_FLOW_RUNBOOK.md"',
        '"engine/live_flow.py"',
        '"tests/test_options_signal_episode.py"',
        '"tests/test_live_flow.py"',
    ):
        assert required in workflow
    assert "python -m pytest tests/test_options_signal_episode.py -q" in manifest
    assert "python -m pytest tests/test_options_signal_campaign.py -q" in manifest
    assert "python -m pytest tests/test_live_flow.py -q" in manifest


def test_committed_options_pit_ledgers_are_strict_valid_joined_shadow_data() -> None:
    from scripts import build_options_signal_episode as builder

    repo = Path(__file__).resolve().parents[1]
    ledger_root = repo / "data/options_signal_episode"
    episodes = load_jsonl(ledger_root / "episodes.jsonl")
    h60_outcomes = load_jsonl(ledger_root / "outcomes_h60.jsonl")
    session_outcomes = load_jsonl(ledger_root / "outcomes_session.jsonl")
    checkpoint = json.loads((ledger_root / "checkpoint.json").read_text())

    assert episodes
    assert len({row["episode_id"] for row in episodes}) == len(episodes)
    episode_by_id = {row["episode_id"]: row for row in episodes}
    builder._validate_checkpoint_document(checkpoint)
    assert {row["session_date"] for row in episodes} <= set(checkpoint["sessions"])

    for episode in episodes:
        validate_episode(episode)
        assert set(episode["decision"]["authority"].values()) == {False}

    assert len({row["outcome_id"] for row in h60_outcomes}) == len(h60_outcomes)
    for outcome in h60_outcomes:
        episode = episode_by_id[outcome["episode_id"]]
        validate_outcome_against_episode(outcome, episode)
        assert outcome["label_authority"] == "research_only"
        assert outcome["option"]["status"] == "unavailable"

    assert len({row["outcome_id"] for row in session_outcomes}) == len(
        session_outcomes
    )
    for outcome in session_outcomes:
        episode = episode_by_id[outcome["episode_id"]]
        validate_session_outcome_against_episode(outcome, episode)
        assert outcome["label_authority"] == "research_only"
        assert outcome["measurement"]["training_eligible"] is False
        assert outcome["option"]["status"] == "unavailable"


def test_daily_options_pit_checkpoint_is_immediate_success_only_metadata_replay() -> None:
    repo = Path(__file__).resolve().parents[1]
    # 512KB-cap diet: engine bodies live in scripts/ci/ — splice them back IN
    # PLACE so the positional index() slicing below keeps its meaning.
    workflow = workflow_run_source.resolved_workflow_text(
        repo / ".github/workflows/daily.yml", repo
    )
    helper = (repo / "scripts/ci/options_signal_nightly.sh").read_text()
    builder_name = (
        "      - name: OIP PIT — durable episodes + H+60 and "
        "declared-session-close proxy accrual"
    )
    campaign_builder_name = (
        "      - name: OIP campaign v2 — exact-contract revision and "
        "anchored-outcome accrual"
    )
    checkpoint_name = (
        "      - name: OIP PIT — checkpoint the five durable episode ledgers"
    )
    campaign_checkpoint_name = (
        "      - name: OIP campaign v2 — checkpoint the exact three canonical ledgers"
    )
    following_name = (
        "      - name: XSR W1 — US fast-sector rotation lens "
        "(build_us_sector_rotation)"
    )
    builder_start = workflow.index(builder_name)
    campaign_builder_start = workflow.index(campaign_builder_name)
    checkpoint_start = workflow.index(checkpoint_name)
    campaign_checkpoint_start = workflow.index(campaign_checkpoint_name)
    following_start = workflow.index(following_name)
    builder_block = workflow[builder_start:campaign_builder_start]
    campaign_builder_block = workflow[campaign_builder_start:checkpoint_start]
    checkpoint_block = workflow[checkpoint_start:campaign_checkpoint_start]
    campaign_checkpoint_block = workflow[campaign_checkpoint_start:following_start]

    assert (
        builder_start
        < campaign_builder_start
        < checkpoint_start
        < campaign_checkpoint_start
        < following_start
    )
    assert "id: options_signal_episode" in builder_block
    assert "continue-on-error: true" in builder_block
    assert "run: python -m scripts.build_options_signal_episode" in builder_block
    assert "id: options_signal_campaign" in campaign_builder_block
    assert "run: python -m scripts.build_options_signal_campaign" in campaign_builder_block
    assert (
        "if: always() && steps.options_signal_episode.outcome == 'success'"
        in campaign_builder_block
    )
    assert (
        "if: always() && steps.options_signal_episode.outcome == 'success'"
        in checkpoint_block
    )
    assert "id: options_signal_episode_publish" in checkpoint_block
    assert (
        "run: bash scripts/ci/options_signal_nightly.sh publish-episode"
        in checkpoint_block
    )

    expected_paths = {
        "data/options_signal_episode/checkpoint.json",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
        "data/options_signal_episode/outcomes_session.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
    }
    declared = helper.split("readonly -a OIP_EPISODE_PATHS=(", 1)[1].split(")", 1)[0]
    assert {line.strip() for line in declared.splitlines() if line.strip()} == expected_paths
    episode_helper = helper.split("publish_episode() {", 1)[1].split(
        "\npublish_campaign() {", 1
    )[0]
    assert 'git add -- "${OIP_EPISODE_PATHS[@]}"' in episode_helper
    assert 'push_staged_clean "${OIP_EPISODE_PATHS[@]}"' in episode_helper
    assert "oip_exact_candidate_commit" in episode_helper
    assert 'git reset -q -- "${OIP_EPISODE_PATHS[@]}"' in episode_helper
    assert "git commit -m" not in episode_helper
    assert "git pull" not in episode_helper
    assert "git rebase" not in episode_helper
    assert "git checkout" not in episode_helper
    assert "git stash" not in episode_helper
    assert "git clean" not in episode_helper

    assert "id: options_signal_campaign_publish" in campaign_checkpoint_block
    assert "steps.options_signal_episode_publish.outcome == 'success'" in (
        campaign_checkpoint_block
    )
    assert "steps.options_signal_campaign.outcome == 'success'" in (
        campaign_checkpoint_block
    )
    assert (
        "run: bash scripts/ci/options_signal_nightly.sh publish-campaign"
        in campaign_checkpoint_block
    )
    expected_campaign_paths = {
        "data/options_signal_campaign/campaigns.jsonl",
        "data/options_signal_campaign/outcomes.jsonl",
        "data/options_signal_campaign/checkpoint.json",
    }
    declared_campaign = helper.split(
        "readonly -a OIP_CAMPAIGN_PATHS=(", 1
    )[1].split(")", 1)[0]
    assert {
        line.strip() for line in declared_campaign.splitlines() if line.strip()
    } == expected_campaign_paths
    campaign_helper = helper.split("publish_campaign() {", 1)[1].split(
        "\nexclude_broad() {", 1
    )[0]
    assert 'git add -- "${OIP_CAMPAIGN_PATHS[@]}"' in campaign_helper
    assert 'push_staged_clean "${OIP_CAMPAIGN_PATHS[@]}"' in campaign_helper
    assert "oip_exact_candidate_commit" in campaign_helper
    assert 'git reset -q -- "${OIP_CAMPAIGN_PATHS[@]}"' in campaign_helper
    assert "git commit -m" not in campaign_helper

    broad_start = workflow.index("      - name: commit engine outputs")
    broad_end = workflow.index(
        "      - name: assemble machine-consumable feeds", broad_start
    )
    broad_block = workflow[broad_start:broad_end]
    assert "git add data/ site/ reports/" in broad_block
    assert "bash scripts/ci/options_signal_nightly.sh exclude-broad" in broad_block
    broad_add = broad_block.index("git add data/ site/ reports/")
    exclusions = [
        match.start()
        for match in re.finditer(
            "bash scripts/ci/options_signal_nightly.sh exclude-broad", broad_block
        )
    ]
    assert len(exclusions) == 2
    assert exclusions[0] < broad_add < exclusions[1]
    assert "require-clean-broad-start" in broad_block
    assert "commit-broad-candidate" in broad_block
    assert "commit-render-sync" in broad_block
    assert 'git commit -m "engine: regime update' not in broad_block
    assert 'git commit -m "render-sync: post-rebase guards' not in broad_block
    assert broad_block.index("data/prophet/origination_receipts") < (
        broad_block.rindex("bash scripts/ci/options_signal_nightly.sh exclude-broad")
    )
    cleanup_helper = helper.split("exclude_broad() {", 1)[1].split(
        "\nassert_integrity() {", 1
    )[0]
    assert 'git checkout HEAD -- "$root"' in cleanup_helper
    assert 'git reset -q -- "${OIP_NARROW_ROOTS[@]}"' in cleanup_helper
    assert 'git clean -fd -- "${OIP_NARROW_ROOTS[@]}"' in cleanup_helper

    final_gate = workflow.index(
        "      - name: OIP PIT — fail closed after unrelated rendering completes"
    )
    assert final_gate > following_start
    final_gate_block = workflow[final_gate:]
    assert "        if: always()" in final_gate_block
    assert "OIP_EPISODE_BUILD_OUTCOME" in final_gate_block
    assert "OIP_EPISODE_PUBLISH_OUTCOME" in final_gate_block
    assert "OIP_CAMPAIGN_BUILD_OUTCOME" in final_gate_block
    assert "OIP_CAMPAIGN_PUBLISH_OUTCOME" in final_gate_block
    assert "run: bash scripts/ci/options_signal_nightly.sh assert-integrity" in (
        final_gate_block
    )
    integrity_helper = helper.split("assert_integrity() {", 1)[1]
    for outcome in (
        "OIP_EPISODE_BUILD_OUTCOME",
        "OIP_EPISODE_PUBLISH_OUTCOME",
        "OIP_CAMPAIGN_BUILD_OUTCOME",
        "OIP_CAMPAIGN_PUBLISH_OUTCOME",
    ):
        assert f'${{{outcome}:-}}' in integrity_helper
    assert "OIP PIT integrity passed" in integrity_helper
    assert "return 1" in integrity_helper


def test_narrow_commit_tree_candidate_cannot_advance_head_on_interruption(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    origin = tmp_path / "origin.git"
    lane = tmp_path / "lane"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
    )
    lane.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=lane,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(origin))
    campaign_paths = (
        "data/options_signal_campaign/campaigns.jsonl",
        "data/options_signal_campaign/outcomes.jsonl",
        "data/options_signal_campaign/checkpoint.json",
    )
    for path in campaign_paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"version":1}\n')
    git("add", *campaign_paths)
    git("commit", "-m", "baseline")
    git("push", "-u", "origin", "main")
    parent = git("rev-parse", "HEAD")

    for path in campaign_paths:
        (lane / path).write_text('{"version":2}\n')
    result = subprocess.run(
        ["bash", str(helper), "publish-campaign"],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "GITHUB_RUN_ID": "campaign-test",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pushed options campaign v2 ledgers on attempt 1" in result.stdout
    remote_tip = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "main"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert git("rev-parse", "HEAD") == parent
    assert remote_tip != parent
    assert subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", f"{remote_tip}^"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip() == parent
    for path in campaign_paths:
        remote_bytes = subprocess.run(
            ["git", "--git-dir", str(origin), "show", f"main:{path}"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        assert remote_bytes == '{"version":2}\n'
        assert git("show", f"HEAD:{path}") == '{"version":1}'
        assert (lane / path).read_text() == '{"version":2}\n'
    assert subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=lane, check=False
    ).returncode == 0
    assert subprocess.run(
        ["git", "diff", "--quiet"], cwd=lane, check=False
    ).returncode == 1


def test_five_ledger_episode_helper_keeps_head_and_publishes_exact_scope(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    origin = tmp_path / "origin.git"
    lane = tmp_path / "lane"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(origin))
    episode_paths = (
        "data/options_signal_episode/checkpoint.json",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
        "data/options_signal_episode/outcomes_session.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
    )
    for path in episode_paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"version":1}\n')
    foreign = lane / "data/foreign.json"
    foreign.write_text("keep me unstaged\n")
    git("add", *episode_paths)
    git("commit", "-m", "baseline")
    git("push", "-u", "origin", "main")
    parent = git("rev-parse", "HEAD")

    for path in episode_paths:
        (lane / path).write_text('{"version":2}\n')
    result = subprocess.run(
        ["bash", str(helper), "publish-episode"],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "GITHUB_RUN_ID": "episode-test",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pushed options PIT episode ledgers on attempt 1" in result.stdout
    assert git("rev-parse", "HEAD") == parent
    remote_tip = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "main"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert remote_tip != parent
    assert subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", f"{remote_tip}^"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip() == parent
    remote_tree = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "main^{tree}"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert remote_tree != git("rev-parse", "HEAD^{tree}")
    for path in episode_paths:
        remote_bytes = subprocess.run(
            ["git", "--git-dir", str(origin), "show", f"main:{path}"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        assert remote_bytes == '{"version":2}\n'
        assert git("show", f"HEAD:{path}") == '{"version":1}'
        assert (lane / path).read_text() == '{"version":2}\n'
    assert foreign.read_text() == "keep me unstaged\n"
    assert "data/foreign.json" in git("status", "--porcelain")


@pytest.mark.parametrize(
    "refusal", ["foreign-staged", "owned-symlink", "owned-executable"]
)
def test_narrow_episode_helper_refuses_unsafe_publication(
    tmp_path: Path, refusal: str
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    origin = tmp_path / "origin.git"
    lane = tmp_path / "lane"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(origin))
    episode_paths = (
        "data/options_signal_episode/checkpoint.json",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
        "data/options_signal_episode/outcomes_session.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
    )
    for path in episode_paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"version":1}\n')
    git("add", *episode_paths)
    git("commit", "-m", "baseline")
    git("push", "-u", "origin", "main")
    parent = git("rev-parse", "HEAD")
    for path in episode_paths:
        (lane / path).write_text('{"version":2}\n')

    if refusal == "foreign-staged":
        foreign = lane / "data/foreign.json"
        foreign.write_text('{"must_not_ride":true}\n')
        git("add", "data/foreign.json")
    elif refusal == "owned-symlink":
        target = lane / episode_paths[-1]
        target.unlink()
        target.symlink_to("episodes.jsonl")
    else:
        target = lane / episode_paths[-1]
        target.chmod(0o755)
        git("add", episode_paths[-1])

    result = subprocess.run(
        ["bash", str(helper), "publish-episode"],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "GITHUB_RUN_ID": "refusal-test",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    diagnostics = result.stdout + result.stderr
    assert "::error title=options PIT checkpoint" in diagnostics or (
        "::error title=options candidate index rejected" in diagnostics
    )
    assert git("rev-parse", "HEAD") == parent
    remote_tip = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "main"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert remote_tip == parent


@pytest.mark.parametrize("publisher", ["episode", "campaign"])
def test_narrow_publishers_isolate_foreign_index_toctou_race(
    tmp_path: Path, publisher: str
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    origin = tmp_path / "origin.git"
    lane = tmp_path / "lane"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(origin))
    episode_paths = (
        "data/options_signal_episode/checkpoint.json",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
        "data/options_signal_episode/outcomes_session.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
    )
    campaign_paths = (
        "data/options_signal_campaign/campaigns.jsonl",
        "data/options_signal_campaign/outcomes.jsonl",
        "data/options_signal_campaign/checkpoint.json",
    )
    paths = episode_paths if publisher == "episode" else campaign_paths
    for path in paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"version":1}\n')
    git("add", *paths)
    git("commit", "-m", "baseline")
    git("push", "-u", "origin", "main")
    parent = git("rev-parse", "HEAD")
    for path in paths:
        (lane / path).write_text('{"version":2}\n')
    foreign = lane / "data/foreign.json"
    foreign.write_text('{"must_not_ride":true}\n')

    wrapper = tmp_path / f"run-{publisher}-race.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "oip_after_scope_check() { git add -- data/foreign.json; }\n"
        "export OIP_NIGHTLY_SOURCE_ONLY=1\n"
        f'. "{helper}"\n'
        f"publish_{publisher}\n"
    )
    wrapper.chmod(0o755)
    result = subprocess.run(
        ["bash", str(wrapper)],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "GITHUB_RUN_ID": f"{publisher}-race",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("rev-parse", "HEAD") == parent
    remote_tip = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "main"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert remote_tip != parent
    remote_paths = set(
        subprocess.run(
            ["git", "--git-dir", str(origin), "diff-tree", "--no-commit-id", "-r", "--name-only", remote_tip],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
    )
    assert remote_paths == set(paths)
    assert "data/foreign.json" not in remote_paths
    assert subprocess.run(
        ["git", "--git-dir", str(origin), "cat-file", "-e", "main:data/foreign.json"],
        text=True,
        capture_output=True,
        check=False,
    ).returncode != 0
    assert git("diff", "--cached", "--name-only") == "data/foreign.json"


@pytest.mark.parametrize("publisher", ["episode", "campaign"])
def test_narrow_publishers_use_one_generation_when_allowed_paths_restage(
    tmp_path: Path, publisher: str
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    origin = tmp_path / "origin.git"
    lane = tmp_path / "lane"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(origin))
    episode_paths = (
        "data/options_signal_episode/checkpoint.json",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
        "data/options_signal_episode/outcomes_session.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
    )
    campaign_paths = (
        "data/options_signal_campaign/campaigns.jsonl",
        "data/options_signal_campaign/outcomes.jsonl",
        "data/options_signal_campaign/checkpoint.json",
    )
    paths = episode_paths if publisher == "episode" else campaign_paths
    for path in paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"generation":0}\n')
    git("add", *paths)
    git("commit", "-m", "baseline")
    git("push", "-u", "origin", "main")
    parent = git("rev-parse", "HEAD")
    for path in paths:
        (lane / path).write_text('{"generation":1}\n')

    quoted_paths = " ".join(f"'{path}'" for path in paths)
    wrapper = tmp_path / f"run-{publisher}-allowed-race.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "oip_after_stage_snapshot() {\n"
        f"  for path in {quoted_paths}; do printf '%s\\n' '{{\"generation\":2}}' > \"$path\"; done\n"
        f"  git add -- {quoted_paths}\n"
        "}\n"
        "export OIP_NIGHTLY_SOURCE_ONLY=1\n"
        f'. "{helper}"\n'
        f"publish_{publisher}\n"
    )
    wrapper.chmod(0o755)
    result = subprocess.run(
        ["bash", str(wrapper)],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "GITHUB_RUN_ID": f"{publisher}-allowed-race",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("rev-parse", "HEAD") == parent
    for path in paths:
        remote_bytes = subprocess.run(
            ["git", "--git-dir", str(origin), "show", f"main:{path}"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        assert remote_bytes == '{"generation":1}\n'
        assert (lane / path).read_text() == '{"generation":2}\n'


def test_broad_cleanup_removes_first_publication_campaign_additions(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    lane = tmp_path / "lane"
    lane.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=lane,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    episode_paths = (
        "data/options_signal_episode/checkpoint.json",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
        "data/options_signal_episode/outcomes_session.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
    )
    for path in episode_paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"safe":true}\n')
    git("add", *episode_paths)
    git("commit", "-m", "baseline")

    for path in episode_paths:
        (lane / path).write_text('{"unsafe":true}\n')

    campaign_root = lane / "data/options_signal_campaign"
    campaign_root.mkdir(parents=True)
    paths = [
        "data/options_signal_campaign/campaigns.jsonl",
        "data/options_signal_campaign/outcomes.jsonl",
        "data/options_signal_campaign/checkpoint.json",
    ]
    for path in paths:
        (lane / path).write_text("{}\n")
    extra_episode = lane / "data/options_signal_episode/unexpected.json"
    extra_episode.write_text('{"must_not_ride":true}\n')
    extra_campaign = lane / "data/options_signal_campaign/unexpected.json"
    extra_campaign.write_text('{"must_not_ride":true}\n')
    foreign = lane / "data/foreign.json"
    foreign.write_text('{"keep":true}\n')
    git("add", "data")
    result = subprocess.run(
        ["bash", str(helper), "exclude-broad"],
        cwd=lane,
        env={**os.environ, "GITHUB_WORKSPACE": str(repo)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    assert not campaign_root.exists()
    assert not extra_episode.exists()
    assert not extra_campaign.exists()
    for path in episode_paths:
        assert (lane / path).read_text() == '{"safe":true}\n'
    assert git("diff", "--cached", "--name-only") == "data/foreign.json"
    assert foreign.read_text() == '{"keep":true}\n'


@pytest.mark.parametrize(
    "failed_name",
    [
        None,
        "OIP_EPISODE_BUILD_OUTCOME",
        "OIP_EPISODE_PUBLISH_OUTCOME",
        "OIP_CAMPAIGN_BUILD_OUTCOME",
        "OIP_CAMPAIGN_PUBLISH_OUTCOME",
    ],
)
def test_terminal_integrity_helper_requires_all_four_successes(
    tmp_path: Path, failed_name: str | None
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    names = (
        "OIP_EPISODE_BUILD_OUTCOME",
        "OIP_EPISODE_PUBLISH_OUTCOME",
        "OIP_CAMPAIGN_BUILD_OUTCOME",
        "OIP_CAMPAIGN_PUBLISH_OUTCOME",
    )
    # This formerly suppressed command dispatch entirely.  It is deliberately
    # hostile here: execution must depend only on Bash's sourced-vs-executed
    # identity, never on a caller-controlled environment variable.
    env = {
        **os.environ,
        "GITHUB_WORKSPACE": str(repo),
        "OIP_NIGHTLY_SOURCE_ONLY": "1",
    }
    env.update({name: "success" for name in names})
    if failed_name is not None:
        env[failed_name] = "failure"
    result = subprocess.run(
        ["bash", str(helper), "assert-integrity"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if failed_name is None:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OIP PIT integrity passed" in result.stdout
    else:
        assert result.returncode != 0
        assert result.stdout.startswith("::error title=OIP PIT integrity::")


def test_narrow_publisher_hard_pins_symbolic_main_and_ignores_allowlist_env(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    origin = tmp_path / "origin.git"
    lane = tmp_path / "lane"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(origin))
    paths = (
        "data/options_signal_episode/checkpoint.json",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
        "data/options_signal_episode/outcomes_session.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
    )
    for path in paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"version":1}\n')
    git("add", *paths)
    git("commit", "-m", "base")
    git("push", "-u", "origin", "main")
    main = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "evil")
    for path in paths:
        (lane / path).write_text('{"version":2}\n')

    result = subprocess.run(
        ["bash", str(helper), "publish-episode"],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "RUNNER_TEMP": str(tmp_path),
            "PUSH_MAIN_BRANCHES": "evil",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "requires exact symbolic refs/heads/main" in result.stderr
    remote = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "main"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert remote == main


def test_narrow_candidate_refuses_reset_to_parent_at_snapshot_boundary(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    origin = tmp_path / "origin.git"
    lane = tmp_path / "lane"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(origin))
    paths = (
        "data/options_signal_campaign/campaigns.jsonl",
        "data/options_signal_campaign/outcomes.jsonl",
        "data/options_signal_campaign/checkpoint.json",
    )
    for path in paths:
        target = lane / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"version":1}\n')
    git("add", *paths)
    git("commit", "-m", "base")
    git("push", "-u", "origin", "main")
    parent = git("rev-parse", "HEAD")
    for path in paths:
        (lane / path).write_text('{"version":2}\n')
    wrapper = tmp_path / "empty-candidate.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "oip_before_stage_snapshot() { git reset --hard -q HEAD; }\n"
        f'. "{helper}"\n'
        "publish_campaign\n"
    )
    wrapper.chmod(0o755)
    result = subprocess.run(
        ["bash", str(wrapper)],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "options candidate empty" in result.stderr
    assert git("rev-parse", "HEAD") == parent
    remote = subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "main"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert remote == parent


@pytest.mark.parametrize("command,allowed_root", [("commit-broad-candidate", "data"), ("commit-render-sync", "site")])
def test_locked_commit_uses_frozen_allowed_tree_and_clears_index(
    tmp_path: Path, command: str, allowed_root: str
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    lane = tmp_path / "lane"
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    target = lane / allowed_root / "owned.txt"
    target.parent.mkdir(parents=True)
    target.write_text("v1\n")
    git("add", ".")
    git("commit", "-m", "base")
    parent = git("rev-parse", "HEAD")
    target.write_text("v2\n")
    git("add", str(target.relative_to(lane)))
    result = subprocess.run(
        ["bash", str(helper), command, "locked candidate"],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("rev-parse", "HEAD^") == parent
    assert git("show", f"HEAD:{allowed_root}/owned.txt") == "v2"
    assert git("status", "--porcelain") == ""
    assert not (lane / ".git/index.lock").exists()


def test_locked_broad_refusal_preserves_foreign_lock_and_sanitizes_owned_failure(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    lane = tmp_path / "lane"
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    owned = lane / "data/owned.txt"
    foreign = lane / "config/foreign.txt"
    owned.parent.mkdir(parents=True)
    foreign.parent.mkdir(parents=True)
    owned.write_text("v1\n")
    foreign.write_text("v1\n")
    git("add", ".")
    git("commit", "-m", "base")
    parent = git("rev-parse", "HEAD")
    owned.write_text("v2\n")
    foreign.write_text("v2\n")
    git("add", ".")
    result = subprocess.run(
        ["bash", str(helper), "commit-broad-candidate", "must fail"],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert git("rev-parse", "HEAD") == parent
    assert git("diff", "--cached", "--name-only") == ""
    assert not (lane / ".git/index.lock").exists()

    (lane / ".git/index.lock").write_text("other-writer")
    result = subprocess.run(
        ["bash", str(helper), "commit-broad-candidate", "busy"],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert (lane / ".git/index.lock").read_text() == "other-writer"
    assert git("rev-parse", "HEAD") == parent


def test_locked_broad_snapshot_blocks_late_index_writer(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    lane = tmp_path / "lane"
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=lane, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    owned = lane / "data/owned.txt"
    foreign = lane / "config/foreign.txt"
    owned.parent.mkdir(parents=True)
    foreign.parent.mkdir(parents=True)
    owned.write_text("v1\n")
    foreign.write_text("v1\n")
    git("add", ".")
    git("commit", "-m", "base")
    owned.write_text("v2\n")
    git("add", "data/owned.txt")
    wrapper = tmp_path / "locked-race.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "oip_after_locked_tree_snapshot() {\n"
        "  printf 'v2\\n' > config/foreign.txt\n"
        "  if git add config/foreign.txt >/dev/null 2>&1; then return 91; fi\n"
        "  return 0\n"
        "}\n"
        f'. "{helper}"\n'
        "oip_commit_locked_roots 'locked race' true data site reports templates\n"
    )
    wrapper.chmod(0o755)
    result = subprocess.run(
        ["bash", str(wrapper)],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "RUNNER_TEMP": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD") == (
        "data/owned.txt"
    )
    assert git("show", "HEAD:config/foreign.txt") == "v1"
    assert git("diff", "--cached", "--name-only") == ""
    assert git("diff", "--name-only") == "config/foreign.txt"


def test_locked_broad_ref_cas_does_not_overwrite_newer_local_main(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / "scripts/ci/options_signal_nightly.sh"
    lane = tmp_path / "lane"
    subprocess.run(["git", "init", "-q", "-b", "main", str(lane)], check=True)

    def git(*args: str, input_text: str | None = None) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=lane,
            text=True,
            input=input_text,
            capture_output=True,
            check=True,
        ).stdout.strip()

    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    target = lane / "data/owned.txt"
    target.parent.mkdir(parents=True)
    target.write_text("v1\n")
    git("add", ".")
    git("commit", "-m", "base")
    parent = git("rev-parse", "HEAD")
    other = git("commit-tree", f"{parent}^{{tree}}", "-p", parent, input_text="other\n")
    target.write_text("v2\n")
    git("add", "data/owned.txt")
    wrapper = tmp_path / "ref-race.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "oip_after_locked_tree_snapshot() {\n"
        "  git update-ref refs/heads/main \"$OTHER\" \"$PARENT\"\n"
        "}\n"
        f'. "{helper}"\n'
        "oip_commit_locked_roots 'must lose ref race' true data site reports templates\n"
    )
    wrapper.chmod(0o755)
    result = subprocess.run(
        ["bash", str(wrapper)],
        cwd=lane,
        env={
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "RUNNER_TEMP": str(tmp_path),
            "PARENT": parent,
            "OTHER": other,
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert git("rev-parse", "refs/heads/main") == other
    assert git("diff", "--cached", "--name-only") == ""
    assert not (lane / ".git/index.lock").exists()


def test_session_outcome_registry_has_one_writer_no_authority_consumers() -> None:
    yaml = pytest.importorskip("yaml")
    repo = Path(__file__).resolve().parents[1]
    registry = yaml.safe_load((repo / "config/synapse.yml").read_text())
    artifact = registry["artifacts"]["options-signal-episode-session-outcomes"]
    assert artifact["producer"] == "scripts/build_options_signal_episode.py"
    assert artifact["known_extra_writers"] == []
    assert artifact["consumers"] == [
        "scripts/build_options_signal_episode.py",
        "engine/options_signal_campaign.py",
    ]
    assert artifact["external_consumers"] == []
    assert artifact["tier"] == "shadow"
    notes = artifact["notes"].lower()
    for fence in (
        "training_eligible is always false",
        "no rank",
        "prophet consumer is registered",
    ):
        assert fence in notes


def test_builder_stage_date_mismatch_is_atomic_and_does_not_checkpoint(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(ContractError, match="key/session mismatch"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={
                "2026-07-02": _stage_records(_event(id="valid-first")),
                "2026-07-06": _stage_records(_event(id="wrong-date")),
            },
            computed_at=datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc),
        )
    ledger_root = tmp_path / "data/options_signal_episode"
    assert not (ledger_root / "episodes.jsonl").exists()
    assert not (ledger_root / "outcomes_h60.jsonl").exists()
    assert not (ledger_root / "checkpoint.json").exists()

    from scripts import live_flow_poller as poller
    monkeypatch.setenv("LIVE_FLOW_EVENT_STAGE_DIR", str(tmp_path / "stage"))
    wrong = _event(id="poller-wrong-date")
    for key in ("available_at", "published_at", "source_snapshot_asof", "anchor_strategy"):
        wrong.pop(key, None)
    with pytest.raises(RuntimeError, match="belongs to 2026-07-02"):
        poller._stage_raw_events("2026-07-06", [wrong])
    assert not (tmp_path / "stage/2026-07-06.jsonl").exists()


def test_builder_rejects_receipt_reordering_and_conversion_drop_without_checkpoint(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    reversed_stage = list(reversed(_stage_records()))
    with pytest.raises(ContractError, match="precedes its decision"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": reversed_stage},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )

    inadmissible = _event(oi_vintage=None, vol_gt_oi=True)
    with pytest.raises(ContractError, match="inadmissible decision"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": _stage_records(inadmissible)},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    ledger_root = tmp_path / "data/options_signal_episode"
    assert not (ledger_root / "episodes.jsonl").exists()
    assert not (ledger_root / "outcomes_h60.jsonl").exists()
    assert not (ledger_root / "checkpoint.json").exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"size": 200.9},
        {"dte": 15.9},
        {"dte": 14},
        {"dte": 16},
        {"dte": 999},
        {"repeated": "false"},
        {"swept": 1},
        {"avg_price": -2.5},
        {"avg_price": 5.5},
        {"exp": "2026-07-17junk"},
        {"exp": "20260717"},
        {"exp": "2026-W29-5"},
        {"oi_vintage": "2026-07-01junk"},
        {"oi_vintage": "20260701"},
        {"oi_vintage": "2026-W27-3"},
        {"root": " test "},
        {"right": "CALL"},
        {"mny_bucket": "banana"},
        {"signing_source": None},
        {"signing_source": "nbbo"},
        {"baseline_source": None},
        {"baseline_source": "banana"},
        {"baseline_source": "z252", "premium_z": 3.5},
        {"premium_z": 3.5},
        {"selection_rule": "banana"},
        {"selection_floor_usd": 50_001},
        {"selection_floor_usd": -1},
        {"selection_root_class": "banana"},
        {"vol_gt_oi": 1},
        {"vol_gt_oi": 0},
        {"vol_gt_oi": "false"},
    ],
)
def test_builder_rejects_coerced_learning_facts_without_checkpoint(
    tmp_path: Path, monkeypatch, overrides: dict,
) -> None:
    from scripts import build_options_signal_episode as builder

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(ContractError, match="inadmissible decision"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": _stage_records(_event(**overrides))},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    ledger_root = tmp_path / "data/options_signal_episode"
    assert not (ledger_root / "episodes.jsonl").exists()
    assert not (ledger_root / "outcomes_h60.jsonl").exists()
    assert not (ledger_root / "checkpoint.json").exists()


@pytest.mark.parametrize(
    "malformation", [
        "duplicate_pair", "decision_after_pair", "extra_field",
        "embedded_reserved", "empty",
    ],
)
def test_builder_rejects_malformed_receipt_state_machine_atomically(
    tmp_path: Path, monkeypatch, malformation: str,
) -> None:
    from scripts import build_options_signal_episode as builder

    stage = _stage_records()
    if malformation == "duplicate_pair":
        stage = stage + copy.deepcopy(stage)
    elif malformation == "decision_after_pair":
        stage = stage + [copy.deepcopy(stage[0])]
    elif malformation == "extra_field":
        stage[0]["unexpected"] = True
    elif malformation == "embedded_reserved":
        stage[0]["event"]["available_at"] = "2026-07-02T14:40:00Z"
    else:
        stage = []

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(
        ContractError,
        match="duplicate staged decision|receipt shape|non-durable fields|empty dated event stage",
    ):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": stage},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    ledger_root = tmp_path / "data/options_signal_episode"
    assert not (ledger_root / "episodes.jsonl").exists()
    assert not (ledger_root / "outcomes_h60.jsonl").exists()
    assert not (ledger_root / "checkpoint.json").exists()


@pytest.mark.parametrize(
    "index",
    [
        {"schema": "wrong", "sessions": []},
        {"schema": "live_flow.event_dates/v1", "sessions": ["9999-99-99"]},
        {
            "schema": "live_flow.event_dates/v1",
            "sessions": ["2026-07-02", "2026-07-02"],
        },
        {
            "schema": "live_flow.event_dates/v1",
            "sessions": ["2026-07-06", "2026-07-02"],
        },
    ],
)
def test_public_event_dates_fallback_rejects_untrusted_index(
    monkeypatch, index: dict,
) -> None:
    from scripts import build_options_signal_episode as builder

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(index).encode()

    monkeypatch.setattr(builder, "_r2_client", lambda: None)
    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(ContractError, match="event-stage dates index"):
        builder.discover_event_sessions()


def test_public_event_dates_fallback_accepts_exact_bounded_index(monkeypatch) -> None:
    from scripts import build_options_signal_episode as builder

    payload = {
        "schema": "live_flow.event_dates/v1",
        "sessions": ["2026-07-02", "2026-07-06"],
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(builder, "_r2_client", lambda: None)
    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    assert builder.discover_event_sessions() == ["2026-07-02", "2026-07-06"]


def test_public_event_dates_fallback_rejects_duplicate_json_keys(monkeypatch) -> None:
    from scripts import build_options_signal_episode as builder

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return (
                b'{"schema":"wrong","schema":"live_flow.event_dates/v1",'
                b'"sessions":[]}'
            )

    monkeypatch.setattr(builder, "_r2_client", lambda: None)
    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(ContractError, match="dates index is malformed"):
        builder.discover_event_sessions()


def test_builder_integrity_failure_is_nonzero_and_does_not_advance(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    data = tmp_path / "data/options_signal_episode"
    data.mkdir(parents=True)
    checkpoint = data / "checkpoint.json"
    checkpoint.write_text("{not-json\n")
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(ContractError, match="checkpoint is corrupt"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": _stage_records()},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    assert checkpoint.read_text() == "{not-json\n"
    assert not (data / "episodes.jsonl").exists()

    duplicate_checkpoint = (
        '{"schema":"options.signal_episode_checkpoint/v1",'
        '"sessions":{},"sessions":{}}\n'
    )
    checkpoint.write_text(duplicate_checkpoint)
    with pytest.raises(ContractError, match="checkpoint is corrupt"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": _stage_records()},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )
    assert checkpoint.read_text() == duplicate_checkpoint
    assert not (data / "episodes.jsonl").exists()

    def fail_run(**_kwargs):
        raise ContractError("integrity probe")

    monkeypatch.setattr(builder, "run", fail_run)
    assert builder.main(["--root-dir", str(tmp_path)]) == 1


@pytest.mark.parametrize(
    "bad_sessions",
    [
        {"1999-01-01": "bad"},
        {"2026-07-02": {"records": -1, "prefix_sha256": "x"}},
        {"2026-07-02": {"records": "2", "prefix_sha256": "0" * 64}},
        {"20260702": {"records": 0, "prefix_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}},
        {"2026-07-04": {"records": 0, "prefix_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}},
    ],
)
def test_checkpoint_rejects_every_malformed_existing_session(
    tmp_path: Path, monkeypatch, bad_sessions: dict,
) -> None:
    from scripts import build_options_signal_episode as builder

    checkpoint = tmp_path / "data/options_signal_episode/checkpoint.json"
    checkpoint.parent.mkdir(parents=True)
    original = json.dumps({
        "schema": "options.signal_episode_checkpoint/v1",
        "sessions": bad_sessions,
    }) + "\n"
    checkpoint.write_text(original)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(ContractError, match="checkpoint"):
        builder._advance_checkpoint(
            checkpoint, "2026-07-02", _stage_records(), dry_run=False,
        )
    assert checkpoint.read_text() == original


def test_session_outcome_schema_and_runtime_validator_are_strict() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    episode = _episode()
    bars = _session_bars(episode, "eod")
    row = derive_session_outcome(
        episode,
        "eod",
        bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    validate_session_outcome(row)
    validate_session_outcome_against_episode(row, episode)
    schema = json.loads((
        Path(__file__).resolve().parents[1]
        / "contracts/options/options.signal_episode_session_outcome.v1.schema.json"
    ).read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker(),
    ).validate(row)

    extra = copy.deepcopy(row)
    extra["unexpected"] = True
    with pytest.raises(ContractError, match="schema validation"):
        validate_session_outcome(extra)
    wrong_mapping = copy.deepcopy(row)
    wrong_mapping["horizon_sessions"] = 1
    with pytest.raises(ContractError, match="schema validation|disagrees"):
        validate_session_outcome(wrong_mapping)
    for coerced in (True, 0.0):
        wrong_type = copy.deepcopy(row)
        wrong_type["horizon_sessions"] = coerced
        with pytest.raises(ContractError, match="horizon_sessions"):
            validate_session_outcome(wrong_type)
    noncanonical = copy.deepcopy(row)
    noncanonical["target_time"] = "2026-07-02T20:00:00+00:00"
    with pytest.raises(ContractError, match="canonical UTC"):
        validate_session_outcome(noncanonical)
    forged_id = copy.deepcopy(row)
    forged_id["outcome_id"] = "oout_" + "0" * 24
    with pytest.raises(ContractError, match="not stable"):
        validate_session_outcome(forged_id)
    wrong_calendar = copy.deepcopy(row)
    wrong_calendar["measurement"]["calendar_basis"] = "authoritative_exchange_calendar/v1"
    with pytest.raises(ContractError, match="schema validation|calendar_basis"):
        validate_session_outcome(wrong_calendar)
    for coerced in (True, 10.0):
        wrong_manifest_count = copy.deepcopy(row)
        evidence = wrong_manifest_count["underlying"]["evidence"]
        evidence["sessions"][0]["expected_count"] = coerced
        evidence["manifest_root_sha256"] = hashlib.sha256(json.dumps(
            evidence["sessions"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode()).hexdigest()
        with pytest.raises(ContractError, match="schema validation|count arithmetic"):
            validate_session_outcome(wrong_manifest_count)


def test_session_horizons_use_real_sessions_holidays_and_early_close() -> None:
    episode = _episode()
    one_day = derive_session_outcome(
        episode,
        "1d",
        _session_bars(episode, "1d"),
        computed_at=datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    assert one_day["target_session"] == "2026-07-06"
    assert one_day["target_time"] == "2026-07-06T20:00:00Z"
    assert one_day["horizon_sessions"] == 1

    early_episode = _episode(
        id="early-close-horizon",
        ts="2026-11-25T15:30:00Z",
        observed_at="2026-11-25T15:31:00Z",
        decision_at="2026-11-25T15:31:00Z",
        available_at="2026-11-25T15:31:00Z",
        source_snapshot_asof="2026-11-25T15:31:00Z",
        exp="2026-12-18",
        dte=23,
        oi_vintage="2026-11-24",
    )
    early = derive_session_outcome(
        early_episode,
        "1d",
        _session_bars(early_episode, "1d"),
        computed_at=datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    assert early["target_session"] == "2026-11-27"
    assert early["target_time"] == "2026-11-27T18:00:00Z"
    assert early["underlying"]["evidence"]["exit"]["bar_time"] == (
        "2026-11-27T17:30:00Z"
    )


def test_session_hourly_production_shape_discloses_open_stub_and_close_proxy() -> None:
    regular_episode = _episode(
        id="hourly-regular",
        ts="2026-07-02T13:31:00Z",
        observed_at="2026-07-02T13:32:00Z",
        decision_at="2026-07-02T13:32:00Z",
        available_at="2026-07-02T13:32:00Z",
        source_snapshot_asof="2026-07-02T13:32:00Z",
    )
    regular_bars = _polygon_hourly_session_bars(regular_episode, "eod")
    regular = derive_session_outcome(
        regular_episode,
        "eod",
        regular_bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=3600,
        price_delay_minutes=15,
    )
    manifest = regular["underlying"]["evidence"]["sessions"][0]
    assert regular_bars.index.strftime("%H:%M").tolist() == [
        "14:00", "15:00", "16:00", "17:00", "18:00", "19:00",
    ]
    assert regular["underlying"]["entry_time"] == "2026-07-02T14:00:00Z"
    assert regular["underlying"]["evidence"]["exit"]["bar_time"] == (
        "2026-07-02T19:00:00Z"
    )
    assert manifest["uncovered_open_seconds"] == 1800
    assert manifest["observation_count"] == manifest["expected_count"] == 6

    early_episode = _episode(
        id="hourly-modeled-early-close",
        ts="2026-11-27T14:31:00Z",
        observed_at="2026-11-27T14:32:00Z",
        decision_at="2026-11-27T14:32:00Z",
        available_at="2026-11-27T14:32:00Z",
        source_snapshot_asof="2026-11-27T14:32:00Z",
        exp="2026-12-18",
        dte=21,
        oi_vintage="2026-11-25",
    )
    early_bars = _polygon_hourly_session_bars(early_episode, "eod")
    early = derive_session_outcome(
        early_episode,
        "eod",
        early_bars,
        computed_at=datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=3600,
        price_delay_minutes=15,
    )
    assert early_bars.index.strftime("%H:%M").tolist() == ["15:00", "16:00", "17:00"]
    assert early["target_time"] == "2026-11-27T18:00:00Z"
    assert early["underlying"]["evidence"]["exit"]["bar_time"] == (
        "2026-11-27T17:00:00Z"
    )
    assert early["underlying"]["evidence"]["sessions"][0][
        "uncovered_open_seconds"
    ] == 1800
    assert derive_session_outcome(
        early_episode,
        "eod",
        early_bars.drop(early_bars.index[-1]),
        computed_at=datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=3600,
        price_delay_minutes=15,
    )["reason"] == "missing_session_close_bar"


def test_session_opening_gaps_and_missing_declared_close_bar_remain_pending() -> None:
    episode = _episode()
    one_minute = _session_bars(episode, "1d", bar_seconds=60)
    first_admitted = pd.Timestamp(episode["available_at"])
    missing_entry_span = one_minute.drop(pd.date_range(
        first_admitted, first_admitted + timedelta(minutes=3), freq="min",
    ))
    assert derive_session_outcome(
        episode,
        "1d",
        missing_entry_span,
        computed_at=datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=60,
        price_delay_minutes=15,
    )["reason"] == "entry_bar_gap"

    target_session = nyse_calendar.session_n_forward(
        datetime.fromisoformat(episode["session_date"]).date(), 1,
    )
    assert target_session is not None
    target_open = session_window_et(target_session)[0].astimezone(timezone.utc)
    missing_next_open = one_minute.drop(pd.date_range(
        target_open, target_open + timedelta(minutes=3), freq="min",
    ))
    assert derive_session_outcome(
        episode,
        "1d",
        missing_next_open,
        computed_at=datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=60,
        price_delay_minutes=15,
    )["reason"] == "entry_bar_gap"

    regular_hourly = _polygon_hourly_session_bars(episode, "eod")
    assert derive_session_outcome(
        episode,
        "eod",
        regular_hourly.drop(regular_hourly.index[-1]),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=3600,
        price_delay_minutes=15,
    )["reason"] == "missing_session_close_bar"


def test_session_outcome_waits_for_target_close_and_receipt_availability() -> None:
    episode = _episode()
    bars = _session_bars(episode, "eod")
    early = derive_session_outcome(
        episode,
        "eod",
        bars,
        computed_at=datetime(2026, 7, 2, 19, 59, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    assert early == {
        "status": "pending", "reason": "horizon_not_matured",
        "episode_id": episode["episode_id"], "horizon": "eod",
    }
    receipt = _fixture_session_price_receipt(
        episode,
        "eod",
        bars,
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
        source_available_at=datetime(2026, 7, 2, 20, 45, tzinfo=timezone.utc),
    )
    not_known = _derive_session_outcome(
        episode,
        "eod",
        bars,
        computed_at=datetime(2026, 7, 2, 20, 30, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
        price_receipt=receipt,
    )
    assert not_known["reason"] == "measurement_not_available"
    matured = _derive_session_outcome(
        episode,
        "eod",
        bars,
        computed_at=datetime(2026, 7, 2, 20, 45, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
        price_receipt=receipt,
    )
    assert matured["matured_at"] == "2026-07-02T20:45:00Z"


def test_session_clock_terminal_is_only_late_eod_and_needs_no_price_source() -> None:
    episode = _episode(
        id="late-durable-eod",
        ts="2026-07-02T19:50:00Z",
        observed_at="2026-07-02T19:51:00Z",
        decision_at="2026-07-02T19:51:00Z",
        available_at="2026-07-02T20:01:00Z",
        source_snapshot_asof="2026-07-02T20:01:00Z",
    )
    before_decision_available = _derive_session_outcome(
        episode,
        "eod",
        None,
        computed_at=datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
    )
    assert before_decision_available["status"] == "pending"
    assert before_decision_available["reason"] == "horizon_not_matured"

    outcome = _derive_session_outcome(
        episode,
        "eod",
        None,
        computed_at=datetime(2026, 7, 2, 20, 5, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
    )
    assert outcome["status"] == "incomplete"
    assert outcome["reason"] == "decision_after_target_close"
    assert outcome["matured_at"] == episode["available_at"]
    assert set(outcome["provenance"].values()) == {None}
    validate_session_outcome_against_episode(outcome, episode)

    inverted = copy.deepcopy(outcome)
    inverted["computed_at"] = "2026-07-02T20:00:00Z"
    inverted["matured_at"] = "2026-07-02T20:00:00Z"
    with pytest.raises(ContractError, match="decision availability"):
        validate_session_outcome(inverted)

    next_session = derive_session_outcome(
        episode,
        "1d",
        _session_bars(episode, "1d"),
        computed_at=datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    assert next_session["status"] == "complete"
    assert next_session["underlying"]["entry_time"] == "2026-07-06T13:30:00Z"
    assert next_session["underlying"]["exit_time"] == "2026-07-06T20:00:00Z"
    validate_session_outcome_against_episode(next_session, episode)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticker", "OTHER"),
        ("source_file", "OTHER.parquet"),
        ("source_file_sha256", "not-a-digest"),
        ("price_basis", "unadjusted"),
        ("timestamp_basis", "aggregate_window_end_utc"),
        ("adjusted", False),
        ("bar_seconds", 3600),
        ("vendor_delay_minutes", 16),
        ("row_count", 0),
        ("first_time", "2026-07-02T16:00:00Z"),
        ("last_time", "2026-07-02T19:00:00Z"),
        ("source_available_at", "2026-07-02T20:14:00Z"),
    ],
)
def test_session_outcome_refuses_mismatched_receipt_fields(field: str, value) -> None:
    episode = _episode()
    bars = _session_bars(episode, "eod")
    receipt = _fixture_session_price_receipt(
        episode,
        "eod",
        bars,
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    receipt[field] = value
    pending = _derive_session_outcome(
        episode,
        "eod",
        bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
        price_receipt=receipt,
    )
    assert pending["status"] == "pending"
    assert pending["reason"] == "invalid_price_receipt"


def test_session_outcome_compact_evidence_replays_metrics_and_rejects_path_gaps() -> None:
    episode = _episode()
    bars = _session_bars(episode, "eod")
    row = derive_session_outcome(
        episode,
        "eod",
        bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    evidence = row["underlying"]["evidence"]
    assert row["underlying"]["entry_time"] == "2026-07-02T15:00:00Z"
    assert row["underlying"]["exit_time"] == "2026-07-02T20:00:00Z"
    assert evidence["exit"] == {
        "bar_time": "2026-07-02T19:30:00Z",
        "time": "2026-07-02T20:00:00Z",
        "close": bars.iloc[-1]["close"],
    }
    assert evidence["entry"] == {"bar_time": "2026-07-02T15:00:00Z", "open": 100.15}
    assert evidence["observation_count"] == 10
    assert evidence["sessions"] == [{
        "session": "2026-07-02",
        "first_bar_time": "2026-07-02T15:00:00Z",
        "last_bar_time": "2026-07-02T19:30:00Z",
        "uncovered_open_seconds": 5400,
        "observation_count": 10,
        "expected_count": 10,
        "session_path_sha256": evidence["sessions"][0]["session_path_sha256"],
    }]
    selected = bars[
        (bars.index >= pd.Timestamp("2026-07-02T15:00:00Z"))
        & (bars.index <= pd.Timestamp("2026-07-02T19:30:00Z"))
    ]
    canonical_observations = [{
        "time": timestamp.isoformat().replace("+00:00", "Z"),
        "open": round(float(bar["open"]), 8),
        "high": round(float(bar["high"]), 8),
        "low": round(float(bar["low"]), 8),
        "close": round(float(bar["close"]), 8),
    } for timestamp, bar in selected.iterrows()]
    assert evidence["sessions"][0]["session_path_sha256"] == hashlib.sha256(json.dumps(
        canonical_observations,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode()).hexdigest()
    assert evidence["manifest_root_sha256"] == hashlib.sha256(json.dumps(
        evidence["sessions"], ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        allow_nan=False,
    ).encode()).hexdigest()
    assert row["underlying"]["ret"] == pytest.approx(
        bars.iloc[-1]["close"] / bars[bars.index >= pd.Timestamp("2026-07-02T14:31:00Z")].iloc[0]["open"] - 1
    )
    for mutate, error, refresh_root in (
        (
            lambda value: value["underlying"]["evidence"]["entry"].__setitem__(
                "open", round(value["underlying"]["evidence"]["entry"]["open"] + 0.01, 8),
            ),
            "arithmetic disagrees",
            False,
        ),
        (
            lambda value: value["underlying"]["evidence"]["extrema"]["high"].__setitem__(
                "value",
                round(
                    value["underlying"]["evidence"]["extrema"]["high"]["value"] + 0.01,
                    8,
                ),
            ),
            "arithmetic disagrees",
            False,
        ),
        (
            lambda value: value["underlying"]["evidence"]["sessions"][0].__setitem__(
                "observation_count", 9,
            ),
            "count arithmetic",
            True,
        ),
        (
            lambda value: value["underlying"]["evidence"]["sessions"][0].__setitem__(
                "uncovered_open_seconds", 0,
            ),
            "uncovered-open",
            True,
        ),
        (
            lambda value: value["underlying"]["evidence"].__setitem__(
                "manifest_root_sha256", "0" * 64,
            ),
            "manifest-root digest is inconsistent",
            False,
        ),
    ):
        tampered = copy.deepcopy(row)
        mutate(tampered)
        if refresh_root:
            compact = tampered["underlying"]["evidence"]
            compact["manifest_root_sha256"] = hashlib.sha256(json.dumps(
                compact["sessions"], ensure_ascii=False, separators=(",", ":"), sort_keys=True,
                allow_nan=False,
            ).encode()).hexdigest()
        with pytest.raises(ContractError, match=error):
            validate_session_outcome(tampered)

    high_bars = bars + 9_900.0
    high_price_drift = derive_session_outcome(
        episode,
        "eod",
        high_bars,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    high_price_drift["underlying"]["entry_price"] += 0.000001
    with pytest.raises(ContractError, match="arithmetic disagrees"):
        validate_session_outcome(high_price_drift)
    for field in ("entry_price", "exit_price", "ret", "mfe", "mae"):
        one_unit_drift = copy.deepcopy(row)
        one_unit_drift["underlying"][field] += 0.00000001
        with pytest.raises(ContractError, match="arithmetic disagrees"):
            validate_session_outcome(one_unit_drift)
    ninth_decimal = copy.deepcopy(row)
    ninth_decimal["underlying"]["evidence"]["entry"]["open"] += 0.000000001
    with pytest.raises(ContractError, match="canonical eight-decimal"):
        validate_session_outcome(ninth_decimal)

    missing = bars.drop(bars.index[4])
    assert derive_session_outcome(
        episode,
        "eod",
        missing,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )["reason"] == "measurement_path_gap"
    corrupt = bars.copy()
    corrupt.loc[corrupt.index[3], "high"] = 1.0
    assert derive_session_outcome(
        episode,
        "eod",
        corrupt,
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )["reason"] == "invalid_ohlc_bar"


def test_session_outcome_ignores_post_target_tail_with_same_receipt() -> None:
    episode = _episode()
    baseline_bars = _session_bars(episode, "eod")
    with_tail = _session_bars(episode, "eod", tail_sessions=1)
    receipt = _fixture_session_price_receipt(
        episode,
        "eod",
        with_tail,
        price_source="fixture/TEST.parquet",
        bar_seconds=1800,
        price_delay_minutes=15,
    )
    kwargs = {
        "computed_at": datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        "price_source": "fixture/TEST.parquet",
        "bar_seconds": 1800,
        "price_delay_minutes": 15,
        "price_receipt": receipt,
    }
    baseline = _derive_session_outcome(episode, "eod", baseline_bars, **kwargs)
    replay = _derive_session_outcome(episode, "eod", with_tail, **kwargs)
    assert replay == baseline


def test_session_compact_evidence_size_is_bounded_at_one_minute_ten_days() -> None:
    episode = _episode()
    bars = _session_bars(episode, "10d", bar_seconds=60)
    computed_at = datetime(2026, 7, 20, 22, 0, tzinfo=timezone.utc)
    rows = [
        derive_session_outcome(
            episode,
            horizon,
            bars,
            computed_at=computed_at,
            price_source="fixture/TEST.parquet",
            bar_seconds=60,
            price_delay_minutes=15,
        )
        for horizon in SESSION_HORIZONS
    ]
    encoded = [json.dumps(
        row, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False,
    ).encode() for row in rows]
    ten_day = rows[-1]["underlying"]["evidence"]
    assert ten_day["observation_count"] > 4_000
    assert len(ten_day["sessions"]) == 11
    assert "path" not in ten_day
    assert len(encoded[-1]) < 8_000
    assert sum(map(len, encoded)) < 30_000


def test_all_session_horizons_have_independent_idempotent_semantic_keys(
    tmp_path: Path, monkeypatch,
) -> None:
    episode = _episode()
    bars = _session_bars(episode, "10d")
    computed_at = datetime(2026, 7, 20, 22, 0, tzinfo=timezone.utc)
    rows = [
        derive_session_outcome(
            episode,
            horizon,
            bars,
            computed_at=computed_at,
            price_source="fixture/TEST.parquet",
            bar_seconds=1800,
            price_delay_minutes=15,
        )
        for horizon in SESSION_HORIZONS
    ]
    assert [row["horizon"] for row in rows] == list(SESSION_HORIZONS)
    assert [row["outcome_id"] for row in rows] == [
        "oout_b77f802b7e9f049fe70f4a00",
        "oout_caf0a51b8f1a3a1dd757729f",
        "oout_fe043c1096f9d7836cccb268",
        "oout_aee63492487e3c6b4bee2f31",
        "oout_658e05daceb6ea0d5ba53baa",
    ]
    assert all(row["measurement"]["training_eligible"] is False for row in rows)
    assert all(row["option"]["status"] == "unavailable" for row in rows)
    path = tmp_path / "outcomes_session.jsonl"
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert append_session_outcomes(path, rows + copy.deepcopy(rows)) == 5
    assert append_session_outcomes(path, rows) == 0
    for original in rows:
        drift = copy.deepcopy(original)
        drift["provenance"]["price_source"] = "other/TEST.parquet"
        validate_session_outcome(drift)
        with pytest.raises(ContractError, match="conflicting append payload"):
            append_session_outcomes(path, [drift])


def test_session_append_failure_keeps_checkpoint_last_and_h60_bytes_stable(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    data = tmp_path / "data"
    intraday = data / "intraday"
    intraday.mkdir(parents=True)
    episode = _episode()
    frame = _session_bars(episode, "10d")
    target_session = nyse_calendar.session_n_forward(
        datetime.fromisoformat(episode["session_date"]).date(), 10,
    )
    assert target_session is not None
    target_close = session_window_et(target_session)[1].astimezone(timezone.utc)
    computed_at = target_close + timedelta(hours=1)
    _write_receipted_price_source(
        intraday,
        frame,
        source_available_at=(target_close + timedelta(minutes=15)).isoformat().replace(
            "+00:00", "Z"
        ),
        bar_seconds=1800,
        delay_minutes=15,
    )
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    real_append = builder.append_session_outcomes

    def fail_session_append(*_args, **_kwargs):
        raise ContractError("injected session ledger failure")

    monkeypatch.setattr(builder, "append_session_outcomes", fail_session_append)
    with pytest.raises(ContractError, match="injected session ledger failure"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": _stage_records()},
            computed_at=computed_at,
        )
    ledger = data / "options_signal_episode"
    assert not (ledger / "checkpoint.json").exists()
    assert not (ledger / "outcomes_session.jsonl").exists()
    episode_bytes = (ledger / "episodes.jsonl").read_bytes()
    h60_bytes = (ledger / "outcomes_h60.jsonl").read_bytes()
    h60_id = load_jsonl(ledger / "outcomes_h60.jsonl")[0]["outcome_id"]

    monkeypatch.setattr(builder, "append_session_outcomes", real_append)
    replay = builder.run(
        root_dir=tmp_path,
        stages_by_session={"2026-07-02": _stage_records()},
        computed_at=computed_at,
    )
    assert replay["episodes_appended"] == 0
    assert replay["outcomes_appended"] == 0
    assert replay["session_outcomes_appended"] == 5
    assert (ledger / "episodes.jsonl").read_bytes() == episode_bytes
    assert (ledger / "outcomes_h60.jsonl").read_bytes() == h60_bytes
    assert load_jsonl(ledger / "outcomes_h60.jsonl")[0]["outcome_id"] == h60_id
    assert len(load_jsonl(ledger / "outcomes_session.jsonl")) == 5
    assert (ledger / "checkpoint.json").exists()


def test_h60_v1_id_and_canonical_bytes_are_frozen() -> None:
    episode = _episode()
    outcome = derive_h60_outcome(
        episode,
        _bars(
            ("2026-07-02T15:00:00Z", 100.0, 104.0, 98.0, 102.0),
            ("2026-07-02T16:00:00Z", 103.0, 105.0, 101.0, 104.0),
        ),
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        price_source="fixture",
        bar_seconds=3600,
        price_delay_minutes=15,
    )
    encoded = json.dumps(
        outcome, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        allow_nan=False,
    ).encode()
    assert outcome["schema"] == "options.signal_episode_outcome/v1"
    assert outcome["outcome_id"] == "oout_2a558932c692c26734be3917"
    assert len(encoded) == 1989
    assert hashlib.sha256(encoded).hexdigest() == (
        "1167252ede715d0b1909007cdf7466da0c8bf1cfd3eceb21e8870035633837ff"
    )


def test_builder_consumes_partial_session_extension_and_rejects_shrink(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    first_event = _event(id="partial-one")
    second_event = _event(id="partial-two", strike=110.0)
    first_stage = _stage_records(first_event)
    extended_stage = first_stage + _stage_records(second_event)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = builder.run(
        root_dir=tmp_path,
        stages_by_session={"2026-07-02": first_stage},
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    extended = builder.run(
        root_dir=tmp_path,
        stages_by_session={"2026-07-02": extended_stage},
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    assert first["episodes_appended"] == 1
    assert extended["episodes_appended"] == 1
    with pytest.raises(ContractError, match="shrank"):
        builder.run(
            root_dir=tmp_path,
            stages_by_session={"2026-07-02": first_stage},
            computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    ("premiums", "expected_count"),
    [
        ([3_000_000], 0),
        ([1_500_000, 1_499_999], 0),
        ([1_500_000, 1_500_000], 1),
    ],
)
def test_campaign_first_prefix_requires_two_events_and_exact_three_million(
    premiums: list[int], expected_count: int,
) -> None:
    episodes = [
        _campaign_episode(
            f"threshold-{index}",
            premium,
            available_at=f"2026-07-02T14:{31 + index:02d}:00Z",
        )
        for index, premium in enumerate(premiums)
    ]
    campaigns, pending = derive_campaigns(
        episodes,
        [_campaign_h60_outcome(episode) for episode in episodes],
    )
    assert len(campaigns) == expected_count
    assert pending == []
    if campaigns:
        assert campaigns[0]["crossing"]["cumulative_premium_usd"] == (
            CAMPAIGN_MIN_PREMIUM_USD
        )


def test_campaign_tie_shuffle_and_later_events_are_byte_stable() -> None:
    tied = [
        _campaign_episode(
            f"tie-{index}", 1_000_000, available_at="2026-07-02T14:31:00Z",
        )
        for index in range(3)
    ]
    outcomes = [_campaign_h60_outcome(episode) for episode in tied]
    baseline, pending = derive_campaigns(tied, outcomes)
    shuffled, shuffled_pending = derive_campaigns(
        [tied[2], tied[0], tied[1]], [outcomes[1], outcomes[2], outcomes[0]],
    )
    assert pending == shuffled_pending == []
    assert _canonical_test_bytes(baseline) == _canonical_test_bytes(shuffled)
    assert len(baseline) == 1
    ordered = sorted(tied, key=lambda row: row["episode_id"])
    assert baseline[0]["crossing"]["episode_ids"] == [
        episode["episode_id"] for episode in ordered
    ]
    assert baseline[0]["crossing"]["episode_prefix_sha256"] == hashlib.sha256(
        _canonical_test_bytes(ordered)
    ).hexdigest()

    campaign = baseline[0]
    group = campaign["group"]
    normalized_group = [
        group["session_date"],
        group["ticker"],
        group["expiration"],
        format(Decimal(str(group["strike"])).normalize(), "f"),
        group["right"],
    ]
    full_rule_identity = {
        "schema": campaign["schema"],
        "rule": campaign["rule"],
        "group": normalized_group,
    }
    expected_id = "ocam_" + hashlib.sha256(
        _canonical_test_bytes(full_rule_identity)
    ).hexdigest()[:24]
    id_only_identity = {
        **full_rule_identity,
        "rule": campaign["rule"]["id"],
    }
    id_only_digest = "ocam_" + hashlib.sha256(
        _canonical_test_bytes(id_only_identity)
    ).hexdigest()[:24]
    assert campaign["campaign_id"] == expected_id
    assert campaign["campaign_id"] != id_only_digest

    later = _campaign_episode(
        "tie-later", 9_000_000, available_at="2026-07-02T14:40:00Z",
    )
    with_later, later_pending = derive_campaigns(
        [later, *tied], [*outcomes, _campaign_h60_outcome(later)],
    )
    assert later_pending == []
    assert _canonical_test_bytes(with_later) == _canonical_test_bytes(baseline)


def test_campaign_normalizes_equivalent_anchor_clock_to_canonical_utc() -> None:
    episodes = [
        _campaign_episode("offset-one", 1_500_000),
        _campaign_episode(
            "offset-two", 1_500_000, available_at="2026-07-02T14:32:00Z",
        ),
    ]
    anchor = episodes[-1]
    for field in ("observed_at", "decision_at", "available_at"):
        anchor[field] = "2026-07-02T10:32:00-04:00"
    anchor["provenance"]["source_snapshot_asof"] = "2026-07-02T10:32:00-04:00"
    anchor["provenance"]["feature_cutoff"] = "2026-07-02T10:32:00-04:00"
    validate_episode(anchor)
    outcome = _campaign_h60_outcome(anchor)
    campaigns, pending = derive_campaigns(
        episodes, [_campaign_h60_outcome(episodes[0]), outcome],
    )
    assert pending == []
    assert campaigns[0]["formed_at"] == "2026-07-02T14:32:00Z"


def test_campaign_evidence_phase_is_recomputed_at_the_frozen_boundary() -> None:
    retrospective_episodes = [
        _campaign_episode("phase-retro-one", 1_500_000),
        _campaign_episode(
            "phase-retro-two", 1_500_000,
            available_at="2026-07-02T14:32:00Z",
        ),
    ]
    retrospective, _ = derive_campaigns(
        retrospective_episodes,
        [_campaign_h60_outcome(episode) for episode in retrospective_episodes],
    )
    assert retrospective[0]["evidence_phase"] == "retrospective_discovery"

    prospective_episodes = [
        _campaign_episode(
            "phase-prospective-one", 1_500_000,
            session_date="2026-08-11", available_at="2026-08-11T14:31:00Z",
            expiration="2026-08-21",
        ),
        _campaign_episode(
            "phase-prospective-two", 1_500_000,
            session_date="2026-08-11", available_at="2026-08-11T14:32:00Z",
            expiration="2026-08-21",
        ),
    ]
    prospective, _ = derive_campaigns(
        prospective_episodes,
        [_campaign_h60_outcome(episode) for episode in prospective_episodes],
    )
    assert prospective[0]["evidence_phase"] == "prospective_after_rule_freeze"

    exact_boundary = copy.deepcopy(prospective[0])
    exact_boundary["formed_at"] = CAMPAIGN_RULE_FROZEN_AT
    validate_campaign(exact_boundary)
    mislabeled = copy.deepcopy(retrospective[0])
    mislabeled["evidence_phase"] = "prospective_after_rule_freeze"
    with pytest.raises(ContractError, match="evidence_phase"):
        validate_campaign(mislabeled)


def test_campaign_retroactive_earlier_insertion_conflicts_in_append_store(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    baseline_episodes = [
        _campaign_episode("retro-one", 1_500_000),
        _campaign_episode(
            "retro-two", 1_500_000, available_at="2026-07-02T14:32:00Z",
        ),
    ]
    baseline, _ = derive_campaigns(
        baseline_episodes,
        [_campaign_h60_outcome(episode) for episode in baseline_episodes],
    )
    path = tmp_path / "campaigns.jsonl"
    assert append_campaigns(path, baseline) == 1
    frozen = path.read_bytes()

    earlier = _campaign_episode(
        "retro-earlier", 1_500_000, available_at="2026-07-02T14:30:00Z",
    )
    revised_episodes = [*baseline_episodes, earlier]
    revised, _ = derive_campaigns(
        revised_episodes,
        [_campaign_h60_outcome(episode) for episode in revised_episodes],
    )
    assert revised[0]["campaign_id"] == baseline[0]["campaign_id"]
    assert revised[0] != baseline[0]
    with pytest.raises(ContractError, match="conflicting append payload"):
        append_campaigns(path, revised)
    assert path.read_bytes() == frozen


@pytest.mark.parametrize(
    ("dimension", "variant"),
    [
        ("session_date", {"session_date": "2026-07-06"}),
        ("ticker", {"ticker": "OTHER"}),
        ("expiration", {"expiration": "2026-07-24"}),
        ("strike", {"strike": 110.0}),
        ("right", {"right": "P"}),
    ],
)
def test_campaign_exact_group_dimensions_never_coalesce(
    dimension: str, variant: dict[str, object],
) -> None:
    base = [
        _campaign_episode("dimension-base-one", 1_500_000),
        _campaign_episode(
            "dimension-base-two", 1_500_000,
            available_at="2026-07-02T14:32:00Z",
        ),
    ]
    variant_session = str(variant.get("session_date", "2026-07-02"))
    variant_kwargs = {key: value for key, value in variant.items() if key != "session_date"}
    other = [
        _campaign_episode(
            f"dimension-{dimension}-one", 1_500_000,
            session_date=variant_session,
            **variant_kwargs,
        ),
        _campaign_episode(
            f"dimension-{dimension}-two", 1_500_000,
            session_date=variant_session,
            available_at=f"{variant_session}T14:32:00Z",
            **variant_kwargs,
        ),
    ]
    episodes = [*base, *other]
    campaigns, pending = derive_campaigns(
        episodes, [_campaign_h60_outcome(episode) for episode in episodes],
    )
    assert pending == []
    assert len(campaigns) == 2
    assert campaigns[0]["group"][dimension] != campaigns[1]["group"][dimension]


def test_campaign_strike_identity_remains_exact_above_float_safe_integer() -> None:
    episodes: list[dict] = []
    for strike_index, strike in enumerate((9_007_199_254_740_992, 9_007_199_254_740_993)):
        for event_index in range(2):
            episode = _campaign_episode(
                f"wide-strike-{strike_index}-{event_index}",
                1_500_000,
                available_at=f"2026-07-02T14:{31 + event_index:02d}:00Z",
            )
            episode["contract"]["strike"] = strike
            validate_episode(episode)
            episodes.append(episode)
    campaigns, pending = derive_campaigns(
        episodes, [_campaign_h60_outcome(episode) for episode in episodes],
    )
    assert pending == []
    assert len(campaigns) == 2
    assert {campaign["group"]["strike"] for campaign in campaigns} == {
        9_007_199_254_740_992,
        9_007_199_254_740_993,
    }


def test_campaign_missing_h60_is_pending_not_an_orphan() -> None:
    episodes = [
        _campaign_episode("pending-one", 1_500_000),
        _campaign_episode(
            "pending-two", 1_500_000, available_at="2026-07-02T14:32:00Z",
        ),
    ]
    campaigns, pending = derive_campaigns(
        episodes, [_campaign_h60_outcome(episodes[0])],
    )
    assert campaigns == []
    assert pending == [episodes[-1]["episode_id"]]


def test_campaign_membership_ignores_complete_vs_incomplete_h60_values() -> None:
    complete_group = [
        _campaign_episode("complete-one", 1_500_000, ticker="EARLY"),
        _campaign_episode(
            "complete-two", 1_500_000, ticker="EARLY",
            available_at="2026-07-02T14:32:00Z",
        ),
    ]
    incomplete_group = [
        _campaign_episode(
            "incomplete-one", 1_500_000, ticker="LATE",
            available_at="2026-07-02T19:20:00Z",
        ),
        _campaign_episode(
            "incomplete-two", 1_500_000, ticker="LATE",
            available_at="2026-07-02T19:30:00Z",
        ),
    ]
    episodes = [*complete_group, *incomplete_group]
    outcomes = [_campaign_h60_outcome(episode) for episode in episodes]
    assert {outcomes[1]["status"], outcomes[3]["status"]} == {
        "complete", "incomplete",
    }
    campaigns, pending = derive_campaigns(episodes, outcomes)
    assert pending == []
    assert len(campaigns) == 2
    shifted_outcomes = copy.deepcopy(outcomes)
    for outcome in shifted_outcomes:
        computed = datetime.fromisoformat(
            outcome["computed_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        outcome["computed_at"] = (
            computed + timedelta(days=1)
        ).isoformat().replace("+00:00", "Z")
    replay, replay_pending = derive_campaigns(episodes, shifted_outcomes)
    assert replay_pending == []
    assert _canonical_test_bytes(replay) == _canonical_test_bytes(campaigns)
    for campaign in campaigns:
        assert set(campaign["anchor"]) == {
            "schema", "outcome_id", "episode_id", "horizon_minutes",
        }
        serialized = _canonical_test_bytes(campaign)
        for forbidden in (
            b'"status"', b'"underlying"', b'"option"', b'"entry_price"',
            b'"exit_price"', b'"ret"', b'"mfe"', b'"mae"',
        ):
            assert forbidden not in serialized


def test_campaign_rejects_wrong_h60_references_horizons_and_ids() -> None:
    episodes = [
        _campaign_episode("reference-one", 1_500_000),
        _campaign_episode(
            "reference-two", 1_500_000, available_at="2026-07-02T14:32:00Z",
        ),
    ]
    outcomes = [_campaign_h60_outcome(episode) for episode in episodes]
    valid, _ = derive_campaigns(episodes, outcomes)

    with pytest.raises(ContractError, match="duplicate campaign H\\+60 outcome"):
        derive_campaigns(episodes, [*outcomes, copy.deepcopy(outcomes[-1])])

    wrong_horizon = copy.deepcopy(outcomes[-1])
    wrong_horizon["horizon_minutes"] = 30
    with pytest.raises(ContractError, match="schema validation"):
        derive_campaigns(episodes, [outcomes[0], wrong_horizon])

    wrong_id = copy.deepcopy(outcomes[-1])
    wrong_id["outcome_id"] = "oout_" + "0" * 24
    with pytest.raises(ContractError, match="outcome_id"):
        derive_campaigns(episodes, [outcomes[0], wrong_id])

    orphan_episode = _campaign_episode("reference-orphan", 50_000)
    with pytest.raises(ContractError, match="references missing episode"):
        derive_campaigns(episodes, [*outcomes, _campaign_h60_outcome(orphan_episode)])

    wrong_anchor = copy.deepcopy(valid[0])
    wrong_anchor["anchor"]["episode_id"] = episodes[0]["episode_id"]
    with pytest.raises(ContractError, match="first crossing episode"):
        validate_campaign(wrong_anchor)


def test_campaign_rejects_authority_training_and_non_dollar_premiums() -> None:
    episodes = [
        _campaign_episode("authority-one", 1_500_000),
        _campaign_episode(
            "authority-two", 1_500_000, available_at="2026-07-02T14:32:00Z",
        ),
    ]
    campaigns, _ = derive_campaigns(
        episodes, [_campaign_h60_outcome(episode) for episode in episodes],
    )
    assert campaigns[0]["authority"] == CAMPAIGN_FALSE_AUTHORITY
    escalated = copy.deepcopy(campaigns[0])
    escalated["authority"]["may_select"] = True
    with pytest.raises(ContractError, match="schema validation"):
        validate_campaign(escalated)
    trainable = copy.deepcopy(campaigns[0])
    trainable["training_eligible"] = True
    with pytest.raises(ContractError, match="schema validation"):
        validate_campaign(trainable)

    fractional = [
        _campaign_episode("fractional-one", 1_500_000.5),
        _campaign_episode(
            "fractional-two", 1_500_000,
            available_at="2026-07-02T14:32:00Z",
        ),
    ]
    with pytest.raises(ContractError, match="rounded-dollar"):
        derive_campaigns(
            fractional, [_campaign_h60_outcome(episode) for episode in fractional],
        )
    with pytest.raises(ContractError, match="finite"):
        _campaign_episode("nonfinite", math.inf)
    unsafe = _campaign_episode("unsafe-rounded-dollar", 9_007_199_254_740_992)
    with pytest.raises(ContractError, match="rounded-dollar"):
        derive_campaigns([unsafe], [])


def test_campaign_locked_append_is_concurrently_idempotent_and_conflict_strict(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    episodes = [
        _campaign_episode("concurrent-one", 1_500_000),
        _campaign_episode(
            "concurrent-two", 1_500_000, available_at="2026-07-02T14:32:00Z",
        ),
    ]
    campaigns, _ = derive_campaigns(
        episodes, [_campaign_h60_outcome(episode) for episode in episodes],
    )
    path = tmp_path / "campaigns.jsonl"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _value: append_campaigns(path, campaigns), range(2)))
    assert sorted(results) == [0, 1]
    assert load_jsonl(path) == campaigns

    conflict = copy.deepcopy(campaigns[0])
    conflict["crossing"]["episode_prefix_sha256"] = "f" * 64
    validate_campaign(conflict)
    with pytest.raises(ContractError, match="conflicting append payload"):
        append_campaigns(path, [conflict])
    assert load_jsonl(path) == campaigns


def test_committed_campaign_ledger_is_exact_frozen_corpus_not_future_recomputation() -> None:
    repo = Path(__file__).resolve().parent.parent
    ledger_root = repo / "data/options_signal_episode"
    campaign_body = (ledger_root / "campaigns.jsonl").read_bytes()
    episodes = load_jsonl(ledger_root / "episodes.jsonl")
    outcomes = load_jsonl(ledger_root / "outcomes_h60.jsonl")
    committed = load_jsonl(ledger_root / "campaigns.jsonl")
    assert len(committed) == 8
    assert len(campaign_body) == 10_492
    assert hashlib.sha256(campaign_body).hexdigest() == (
        "db326f5c772ab417c43b8579ad50abb0434916922bda3a13c2da5b8303813910"
    )
    assert {row["evidence_phase"] for row in committed} == {"retrospective_discovery"}
    options_context_audit._validate_frozen_legacy_campaign_ledger(
        body=campaign_body,
        campaigns=committed,
        episodes=episodes,
        h60_outcomes=outcomes,
    )

    future_episodes = [
        _campaign_episode(
            "retired-v1-future-one",
            1_500_000,
            session_date="2026-08-12",
            available_at="2026-08-12T14:31:00Z",
            ticker="RETIRED",
            expiration="2026-09-18",
        ),
        _campaign_episode(
            "retired-v1-future-two",
            1_500_000,
            session_date="2026-08-12",
            available_at="2026-08-12T14:32:00Z",
            ticker="RETIRED",
            expiration="2026-09-18",
        ),
    ]
    future_outcomes = [_campaign_h60_outcome(row) for row in future_episodes]
    # The baseline this synthetic pair is measured against has to come from the same
    # documents it is added to. `derive_campaigns` re-derives EVERY qualifying group
    # from an episode ledger the nightly lane extends, so a hand-typed cardinality
    # here was a scheduled red: the 2026-08-13 durable checkpoint (e9738279704,
    # +822 episodes) took the derivation from the frozen eight groups to twenty while
    # campaigns.jsonl stayed byte-frozen at its retired v1 rows -- which is precisely
    # the divergence this test's name says the committed corpus must NOT track.
    baseline, baseline_pending = derive_campaigns(episodes, outcomes)
    expanded, pending = derive_campaigns(
        [*episodes, *future_episodes], [*outcomes, *future_outcomes]
    )
    assert len(baseline) >= len(committed)
    assert len(expanded) == len(baseline) + 1
    # A qualifying anchor whose H+60 row has not landed yet is a live transient of
    # the source lane -- the session's last episodes are minted after the close and
    # their outcome arrives later -- not a hole in the frozen corpus. The claims that
    # survive a growing ledger: the synthetic pair creates no new pending anchor, and
    # no pending anchor belongs to a campaign the corpus already froze.
    assert pending == baseline_pending
    assert not set(pending) & {
        episode_id
        for row in committed
        for episode_id in row["crossing"]["episode_ids"]
    }
    assert {row["campaign_id"] for row in committed} < {
        row["campaign_id"] for row in expanded
    }
    options_context_audit._validate_frozen_legacy_campaign_ledger(
        body=campaign_body,
        campaigns=committed,
        episodes=[*episodes, *future_episodes],
        h60_outcomes=[*outcomes, *future_outcomes],
    )
    with pytest.raises(
        options_context_audit.AuditInputError,
        match="frozen eight-row corpus",
    ):
        options_context_audit._validate_frozen_legacy_campaign_ledger(
            body=campaign_body + b"\n",
            campaigns=committed,
            episodes=episodes,
            h60_outcomes=outcomes,
        )


def test_campaign_registry_has_one_writer_and_no_authority_consumers() -> None:
    import yaml

    repo = Path(__file__).resolve().parent.parent
    registry = yaml.safe_load((repo / "config/synapse.yml").read_text())
    legacy = registry["artifacts"]["options-signal-campaigns"]
    assert legacy["producer"] == ""
    assert legacy["known_extra_writers"] == []
    assert legacy["consumers"] == [
        "scripts/audit_options_market_memory_context.py"
    ]
    assert legacy["external_consumers"] == []
    assert legacy["weights"] == "none"
    assert legacy["scored_path_surfaces"] == []

    assert registry["artifacts"]["options-signal-episodes"]["consumers"] == [
        "scripts/build_options_signal_episode.py",
        "scripts/capture_market_memory_options_episodes.py",
        "scripts/audit_options_market_memory_context.py",
        "engine/options_signal_campaign.py",
        "scripts/run_options_sparse_selector.py",
    ]
    assert registry["artifacts"]["options-signal-episode-h60-outcomes"][
        "consumers"
    ] == [
        "scripts/build_options_signal_episode.py",
        "scripts/audit_options_market_memory_context.py",
        "scripts/audit_options_episode_outcome_coverage.py",
        "engine/options_signal_campaign.py",
        "engine/options_episode_coverage.py",
    ]

    expected_campaign_consumers = {
        "options-signal-campaign-revisions": [
            "engine/options_signal_campaign.py",
            "scripts/run_options_sparse_selector.py",
        ],
        "options-signal-campaign-outcomes": [
            "engine/options_signal_campaign.py",
        ],
        "options-signal-campaign-checkpoint": [
            "engine/options_signal_campaign.py",
            "scripts/run_options_sparse_selector.py",
        ],
    }
    for artifact_id, consumers in expected_campaign_consumers.items():
        artifact = registry["artifacts"][artifact_id]
        assert artifact["producer"] == "engine/options_signal_campaign.py"
        assert artifact["known_extra_writers"] == []
        assert artifact["consumers"] == consumers
        assert artifact["external_consumers"] == []
        assert artifact["weights"] == "none"
        assert artifact["scored_path_surfaces"] == []


def test_campaign_contract_carries_no_chain_heat_or_directional_projection_fields() -> None:
    repo = Path(__file__).resolve().parent.parent
    contract = (
        repo / "contracts/options/options.signal_campaign.v1.schema.json"
    ).read_text()
    ledger = (repo / "data/options_signal_episode/campaigns.jsonl").read_text()
    for forbidden in (
        "ask_share", '"lean"', "total_premium_mn", "direction_label",
        "bullish", "bearish",
    ):
        assert forbidden not in contract
        assert forbidden not in ledger


def test_episode_builder_preserves_legacy_campaign_bytes_and_has_no_campaign_summary(
    tmp_path: Path, monkeypatch,
) -> None:
    from scripts import build_options_signal_episode as builder

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    first = _event(
        id="campaign-builder-one",
        ts="2026-07-02T19:19:00Z",
        observed_at="2026-07-02T19:20:00Z",
        decision_at="2026-07-02T19:20:00Z",
        available_at="2026-07-02T19:20:00Z",
        source_snapshot_asof="2026-07-02T19:20:00Z",
        size=10_000,
        avg_price=1.5,
        premium=1_500_000,
    )
    ledger_root = tmp_path / "data/options_signal_episode"
    ledger_root.mkdir(parents=True)
    legacy_bytes = (
        Path(__file__).resolve().parent.parent
        / "data/options_signal_episode/campaigns.jsonl"
    ).read_bytes()
    (ledger_root / "campaigns.jsonl").write_bytes(legacy_bytes)
    summary = builder.run(
        root_dir=tmp_path,
        stages_by_session={"2026-07-02": _stage_records(first)},
        computed_at=datetime(2026, 7, 2, 21, 0, tzinfo=timezone.utc),
    )
    assert len(load_jsonl(ledger_root / "episodes.jsonl")) == 1
    assert (ledger_root / "campaigns.jsonl").read_bytes() == legacy_bytes
    assert not any(key.startswith("campaign") for key in summary)
    assert (ledger_root / "checkpoint.json").exists()
