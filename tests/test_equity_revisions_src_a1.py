"""SRC-A1 prospective expectation accrual tests.

These are deliberately hermetic: they prove the source contract without
calling yfinance or writing into the repository's omitted ``data/`` tree.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from collectors import equity_revisions as revisions


def _estimate_frame(*, average: float | None = 10.0, second_average: float | None = 11.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "avg": [average, second_average],
            "median": [9.9, 10.9],
            "high": [12.0, 13.0],
            "low": [8.0, 9.0],
            "numberOfAnalysts": [20, 21],
            "growth": [0.1, 0.2],
            "yearAgoEps": [8.0, 9.0],
        },
        index=["0q", "+1y"],
    )


def _revenue_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "avg": [100.0, 110.0],
            "median": [99.0, 109.0],
            "high": [120.0, 130.0],
            "low": [80.0, 90.0],
            "numberOfAnalysts": [18, 19],
            "growth": [0.05, 0.08],
            "yearAgoRevenue": [95.0, 100.0],
        },
        index=["0q", "+1y"],
    )


class _Ticker:
    def __init__(self, earnings: pd.DataFrame | None = None, revenue: pd.DataFrame | None = None):
        self._earnings = _estimate_frame() if earnings is None else earnings
        self._revenue = _revenue_frame() if revenue is None else revenue

    @property
    def earnings_estimate(self):
        return self._earnings

    @property
    def revenue_estimate(self):
        return self._revenue


def _run(
    tmp_path: Path,
    session: str,
    ticker: _Ticker | None = None,
) -> dict[str, int]:
    client = ticker or _Ticker()
    return revisions.accrue_expectation_observations(
        ["ACME"],
        output_dir=tmp_path,
        collection_session_id=session,
        ticker_factory=lambda _: client,
    )


def _observations(tmp_path: Path) -> pd.DataFrame:
    return pd.read_parquet(tmp_path / "expectation_observations.parquet")


def _attempts(tmp_path: Path) -> pd.DataFrame:
    return pd.read_parquet(tmp_path / "expectation_attempts.parquet")


def test_accrues_all_raw_horizons_eps_and_revenue_with_contract_schema(tmp_path: Path):
    result = _run(tmp_path, "scheduled-1")

    observations = _observations(tmp_path)
    attempts = _attempts(tmp_path)
    assert result == {"attempts": 1, "observations": 28}
    assert list(observations.columns) == revisions._OBSERVATION_COLUMNS
    assert list(attempts.columns) == revisions._ATTEMPT_COLUMNS
    assert set(observations["metric"]) == {"EPS", "revenue"}
    assert set(observations["horizon_label_raw"]) == {"0q", "+1y"}
    assert set(observations["observation_type"]) == set(revisions._OBSERVATION_TYPES)
    covering = observations[
        (observations["metric"] == "EPS")
        & (observations["horizon_label_raw"] == "0q")
        & (observations["observation_type"] == "covering_analyst_count")
    ].iloc[0]
    assert covering["value"] == 20
    assert observations["contributor_id"].isna().all()
    assert (observations["aggregation_level"] == "consensus_snapshot").all()
    assert observations["source_effective_at"].isna().all()
    assert observations["source_published_at"].isna().all()
    assert observations["market_session"].notna().all()
    provider_clock = pd.to_datetime(observations["provider_observed_at"], utc=True)
    system_clock = pd.to_datetime(observations["system_observed_at"], utc=True)
    attempt_clock = pd.to_datetime(attempts.iloc[0]["attempted_at"], utc=True)
    completed_clock = pd.to_datetime(attempts.iloc[0]["completed_at"], utc=True)
    assert (attempt_clock <= provider_clock).all()
    assert (provider_clock <= system_clock).all()
    assert (system_clock <= completed_clock).all()
    assert attempts.iloc[0]["status"] == "success"
    assert attempts.iloc[0]["observation_count"] == 28


def test_same_session_payload_replay_is_idempotent_but_later_session_is_receipted(tmp_path: Path):
    first = _run(tmp_path, "scheduled-1")
    replay = _run(tmp_path, "scheduled-1")
    later = _run(tmp_path, "scheduled-2")

    observations = _observations(tmp_path)
    attempts = _attempts(tmp_path)
    assert first == {"attempts": 1, "observations": 28}
    assert replay == {"attempts": 0, "observations": 0}
    assert later == {"attempts": 1, "observations": 28}
    assert len(attempts) == 2
    assert len(observations) == 56
    assert set(observations.loc[observations["collection_session_id"] == "scheduled-2", "correction_state"]) == {"unchanged"}


def test_changed_payload_appends_supersession_without_mutating_prior_bytes(tmp_path: Path):
    _run(tmp_path, "scheduled-1")
    before = _observations(tmp_path).copy(deep=True)
    changed = _Ticker(earnings=_estimate_frame(average=12.5), revenue=_revenue_frame())
    _run(tmp_path, "scheduled-2", changed)
    after = _observations(tmp_path)

    prior = before[(before["metric"] == "EPS") & (before["horizon_label_raw"] == "0q") & (before["observation_type"] == "average")].iloc[0]
    successor = after[
        (after["collection_session_id"] == "scheduled-2")
        & (after["metric"] == "EPS")
        & (after["horizon_label_raw"] == "0q")
        & (after["observation_type"] == "average")
    ].iloc[0]
    assert successor["value"] == 12.5
    assert successor["correction_state"] == "supersedes"
    assert successor["supersedes_observation_id"] == prior["observation_id"]
    assert len(after) == len(before) * 2
    prior_rows = after.iloc[: len(before)].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        before.fillna("<absent>"), prior_rows.fillna("<absent>"), check_dtype=False,
    )


def test_missing_field_is_typed_unestimable_not_zero(tmp_path: Path):
    _run(tmp_path, "scheduled-1", _Ticker(earnings=_estimate_frame(average=None), revenue=_revenue_frame()))
    rows = _observations(tmp_path)
    average = rows[(rows["metric"] == "EPS") & (rows["horizon_label_raw"] == "0q") & (rows["observation_type"] == "average")].iloc[0]
    assert pd.isna(average["value"])
    assert average["missingness_reason"] == "UNESTIMABLE"


def test_partial_null_and_malformed_attempts_remain_typed_receipts(tmp_path: Path):
    class _Partial:
        earnings_estimate = _estimate_frame()
        revenue_estimate = None

    class _Null:
        earnings_estimate = None
        revenue_estimate = None

    _run(tmp_path, "partial", _Partial())
    _run(tmp_path, "null", _Null())

    class _Malformed:
        earnings_estimate = {"not": "a dataframe"}
        revenue_estimate = {"not": "a dataframe"}

    _run(tmp_path, "malformed", _Malformed())
    statuses = dict(zip(_attempts(tmp_path)["collection_session_id"], _attempts(tmp_path)["status"], strict=True))
    assert statuses == {"partial": "partial", "null": "null", "malformed": "malformed"}


def test_historical_clock_injection_is_refused_to_prevent_snapshot_backfill(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot be backfilled"):
        revisions.accrue_expectation_observations(
            ["ACME"],
            output_dir=tmp_path,
            collection_session_id="old-session",
            system_observed_at="2020-01-01T00:00:00Z",
            ticker_factory=lambda _: _Ticker(),
        )


def test_fiscal_horizon_rollover_is_a_new_raw_horizon_not_a_fabricated_revision(tmp_path: Path):
    _run(tmp_path, "scheduled-1")
    earnings = _estimate_frame()
    earnings.index = ["1q", "+1y"]
    revenue = _revenue_frame()
    revenue.index = ["1q", "+1y"]
    _run(tmp_path, "scheduled-2", _Ticker(earnings=earnings, revenue=revenue))
    rows = _observations(tmp_path)
    rollover = rows[
        (rows["collection_session_id"] == "scheduled-2")
        & (rows["metric"] == "EPS")
        & (rows["horizon_label_raw"] == "1q")
        & (rows["observation_type"] == "average")
    ].iloc[0]
    assert rollover["correction_state"] == "original"
    assert pd.isna(rollover["supersedes_observation_id"])


def test_partial_http_failure_keeps_429_as_operational_evidence(tmp_path: Path):
    class _PartialRateLimited:
        earnings_estimate = _estimate_frame()

        @property
        def revenue_estimate(self):
            raise RuntimeError("HTTP 429 provider response body must never persist")

    _run(tmp_path, "partial-rate-limit", _PartialRateLimited())
    attempt = _attempts(tmp_path).iloc[0]
    assert attempt["status"] == "partial"
    assert attempt["http_status"] == 429
    assert attempt["safe_error_class"] == "provider_http_error"
    assert attempt["safe_error_detail"] == "http_status_429"
    assert "response body" not in " ".join(str(value) for value in attempt.tolist())


def test_year_ago_never_crosses_eps_and_revenue_metric_boundaries(tmp_path: Path):
    eps = _estimate_frame().drop(columns=["yearAgoEps"])
    eps["yearAgoRevenue"] = [999.0, 999.0]
    revenue = _revenue_frame().drop(columns=["yearAgoRevenue"])
    revenue["yearAgoEps"] = [7.0, 8.0]
    _run(tmp_path, "metric-boundary", _Ticker(earnings=eps, revenue=revenue))
    rows = _observations(tmp_path)
    for metric in ("EPS", "revenue"):
        row = rows[(rows["metric"] == metric) & (rows["horizon_label_raw"] == "0q") & (rows["observation_type"] == "year_ago")].iloc[0]
        assert pd.isna(row["value"])
        assert row["missingness_reason"] == "NOT_APPLICABLE"


def test_default_session_identity_is_stable_per_run_or_hourly_bucket():
    env = {"GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "1"}
    assert revisions._default_collection_session_id("2026-08-23T12:00:01Z", env) == revisions._default_collection_session_id("2026-08-23T12:59:59Z", {**env, "GITHUB_RUN_ATTEMPT": "2"})
    assert revisions._default_collection_session_id("2026-08-23T12:00:01Z", {}) == revisions._default_collection_session_id("2026-08-23T12:59:59Z", {})
    assert revisions._default_collection_session_id("2026-08-23T12:00:01Z", {}) != revisions._default_collection_session_id("2026-08-23T13:00:00Z", {})


def test_orphaned_observations_repair_the_attempt_receipt_without_duplicates(tmp_path: Path):
    _run(tmp_path, "crash-session")
    original = _observations(tmp_path).copy(deep=True)
    (tmp_path / "expectation_attempts.parquet").unlink()
    result = _run(tmp_path, "crash-session")
    repaired = _attempts(tmp_path)
    pd.testing.assert_frame_equal(original.fillna("<absent>"), _observations(tmp_path).fillna("<absent>"), check_dtype=False)
    assert result == {"attempts": 1, "observations": 0}
    assert repaired.iloc[0]["observation_count"] == len(original)


def test_market_session_uses_the_existing_nyse_calendar_and_fails_closed(monkeypatch):
    assert revisions._market_session("2026-07-06T14:00:00Z") == "2026-07-06"
    assert revisions._market_session("2026-07-04T14:00:00Z") == "2026-07-02"
    monkeypatch.setattr(revisions, "session_date", lambda _: (_ for _ in ()).throw(RuntimeError("owner unavailable")))
    assert revisions._market_session("2026-07-06T14:00:00Z") is None


def test_http_status_parser_rejects_incidental_digit_substrings():
    status, code, error_class, detail = revisions._safe_http_failure(RuntimeError("provider item 1429 retained"))
    assert (status, code, error_class, detail) == ("error", None, "provider_exception", "provider_request_failed")


@pytest.mark.parametrize("status", [401, 403, 429])
def test_http_failures_are_receipted_and_never_become_neutral_observations(tmp_path: Path, status: int):
    class _Blocked:
        @property
        def earnings_estimate(self):
            raise RuntimeError(f"HTTP {status}")

        @property
        def revenue_estimate(self):
            raise RuntimeError(f"HTTP {status}")

    result = _run(tmp_path, f"blocked-{status}", _Blocked())
    attempts = _attempts(tmp_path)
    assert result == {"attempts": 1, "observations": 0}
    assert attempts.iloc[0]["status"] == f"http_{status}"
    assert attempts.iloc[0]["http_status"] == status
    assert attempts.iloc[0]["safe_error_detail"] == f"http_status_{status}"
    assert not (tmp_path / "expectation_observations.parquet").exists()


def test_failure_after_good_collection_cannot_overwrite_good_observations(tmp_path: Path):
    _run(tmp_path, "scheduled-1")
    before = _observations(tmp_path).copy(deep=True)

    class _Malformed:
        @property
        def earnings_estimate(self):
            raise ValueError("unexpected provider shape")

        @property
        def revenue_estimate(self):
            raise ValueError("unexpected provider shape")

    _run(tmp_path, "scheduled-2", _Malformed())
    after = _observations(tmp_path)
    attempts = _attempts(tmp_path)
    pd.testing.assert_frame_equal(before, after, check_dtype=False)
    assert attempts.iloc[-1]["status"] == "error"
    assert attempts.iloc[-1]["safe_error_detail"] == "provider_request_failed"


def test_legacy_latest_and_history_contract_is_unchanged(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(revisions.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(revisions, "_universe", lambda: ["ACME"])
    monkeypatch.setattr(revisions, "_one", lambda ticker: {"breadth": 0.5, "n_analysts": 4})
    monkeypatch.setattr(revisions, "accrue_expectation_observations", lambda *args, **kwargs: {"attempts": 1, "observations": 0})

    assert revisions.fetch_revisions(max_new=1) == 1
    latest = pd.read_parquet(tmp_path / "revisions" / "latest.parquet")
    history = pd.read_parquet(tmp_path / "revisions" / "history.parquet")
    assert list(latest.columns) == ["breadth", "n_analysts", "asof"]
    assert list(history.columns) == ["ticker", "breadth", "n_analysts", "asof", "date"]
    assert history["ticker"].tolist() == ["ACME"]
