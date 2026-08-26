"""W2a (P1-A) tests for collectors/equity_revisions._one — n_covering + breadth_cov.

Tests verify:
  (a) breadth_cov is computed from n_covering (earnings_estimate accessor), never n_analysts.
  (b) n_covering unavailable (accessor absent / field missing) → breadth_cov is None; n_analysts
      NOT substituted.
  (c) earnings_estimate.numberOfAnalysts = NaN or 0 → breadth_cov is None (positive-guard).

The _one() function calls yfinance which requires network; we test by monkeypatching yf.Ticker
to return a synthetic object with the accessors pre-populated.
"""
from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Synthetic yfinance Ticker stubs
# ---------------------------------------------------------------------------

class _FakeTicker:
    """Minimal stub of yf.Ticker for testing _one() without network."""

    def __init__(self, eps_revisions, eps_trend, earnings_estimate=None):
        self.eps_revisions = eps_revisions
        self.eps_trend = eps_trend
        self._earnings_estimate = earnings_estimate

    @property
    def earnings_estimate(self):
        return self._earnings_estimate


def _make_rev_df(up=4.0, dn=0.0) -> pd.DataFrame:
    """eps_revisions DataFrame with '+1y' row."""
    return pd.DataFrame(
        {"upLast30days": [up], "downLast30days": [dn]},
        index=["+1y"],
    )


def _make_trend_df(cur=10.0, d30=9.0, d90=8.0) -> pd.DataFrame:
    """eps_trend DataFrame with '+1y' row."""
    return pd.DataFrame(
        {"current": [cur], "30daysAgo": [d30], "90daysAgo": [d90]},
        index=["+1y"],
    )


def _make_ee_df(n_analysts: float | None, horizon: str = "+1y") -> pd.DataFrame | None:
    """earnings_estimate DataFrame (the new accessor)."""
    if n_analysts is None:
        return None
    return pd.DataFrame(
        {"numberOfAnalysts": [n_analysts]},
        index=[horizon],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_breadth_cov_from_earnings_estimate_not_n_analysts(monkeypatch):
    """(a) breadth_cov = (up - dn) / n_covering; n_covering comes from earnings_estimate,
    NOT from n_analysts (the reviser count).

    Setup: up=4, dn=0 → n_analysts (revisers) = 4 → legacy breadth = 1.0 (saturated)
           n_covering (total analysts) = 20 → breadth_cov = 4/20 = 0.2 (de-saturated)
    """
    import yfinance as yf
    import collectors.equity_revisions as er

    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=4.0, dn=0.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=_make_ee_df(n_analysts=20.0),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None

    # Legacy fields unchanged
    assert result["n_analysts"] == 4        # reviser count
    assert result["breadth"] == 1.0         # saturated: 4/4

    # W2a: coverage-normalised
    assert result["n_covering"] == 20
    expected_breadth_cov = round(4.0 / 20, 4)
    assert result["breadth_cov"] == expected_breadth_cov, (
        f"breadth_cov should be {expected_breadth_cov}, not {result['breadth_cov']}; "
        "ensure n_covering not substituted with n_analysts"
    )
    assert result["breadth_cov"] < result["breadth"], (
        "breadth_cov must be less than legacy breadth when n_covering > n_analysts (de-saturation)"
    )


def test_breadth_cov_none_when_earnings_estimate_accessor_unavailable(monkeypatch):
    """(b) earnings_estimate accessor raises → breadth_cov None; n_analysts NOT substituted."""
    import yfinance as yf
    import collectors.equity_revisions as er

    class _TickerNoEE(_FakeTicker):
        @property
        def earnings_estimate(self):
            raise AttributeError("earnings_estimate not available")

    ticker = _TickerNoEE(
        eps_revisions=_make_rev_df(up=4.0, dn=0.0),
        eps_trend=_make_trend_df(),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None

    # HARD HONESTY RULE: breadth_cov and n_covering must be None — never substituted
    assert result["n_covering"] is None, "n_covering must be None when accessor unavailable"
    assert result["breadth_cov"] is None, (
        "breadth_cov must be None — must not substitute n_analysts for n_covering"
    )
    # Legacy breadth is unaffected
    assert result["breadth"] == 1.0
    assert result["n_analysts"] == 4


def test_breadth_cov_none_when_number_of_analysts_field_missing(monkeypatch):
    """(b) earnings_estimate exists but has no numberOfAnalysts column → both None."""
    import yfinance as yf
    import collectors.equity_revisions as er

    # earnings_estimate without the numberOfAnalysts column
    ee = pd.DataFrame({"someOtherField": [5.0]}, index=["+1y"])
    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=3.0, dn=1.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=ee,
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] is None
    assert result["breadth_cov"] is None


def test_breadth_cov_none_when_n_analysts_is_nan(monkeypatch):
    """(c) earnings_estimate.numberOfAnalysts = NaN → both None (NaN-guard)."""
    import yfinance as yf
    import collectors.equity_revisions as er

    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=3.0, dn=0.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=_make_ee_df(n_analysts=float("nan")),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] is None
    assert result["breadth_cov"] is None


def test_breadth_cov_none_when_n_analysts_is_zero(monkeypatch):
    """(c) earnings_estimate.numberOfAnalysts = 0 → both None (positive-guard prevents /0)."""
    import yfinance as yf
    import collectors.equity_revisions as er

    ticker = _FakeTicker(
        eps_revisions=_make_rev_df(up=3.0, dn=0.0),
        eps_trend=_make_trend_df(),
        earnings_estimate=_make_ee_df(n_analysts=0.0),
    )
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] is None
    assert result["breadth_cov"] is None


def test_earnings_estimate_falls_back_to_0y_horizon(monkeypatch):
    """earnings_estimate has '0y' but not '+1y' → still resolves n_covering from '0y'."""
    import yfinance as yf
    import collectors.equity_revisions as er

    # eps_revisions and trend have '+1y'; earnings_estimate has '0y'
    rev = pd.DataFrame({"upLast30days": [3.0], "downLast30days": [1.0]}, index=["+1y"])
    trend = _make_trend_df()
    ee = pd.DataFrame({"numberOfAnalysts": [15.0]}, index=["0y"])
    ticker = _FakeTicker(eps_revisions=rev, eps_trend=trend, earnings_estimate=ee)
    monkeypatch.setattr(yf, "Ticker", lambda sym: ticker)

    result = er._one("TEST")
    assert result is not None
    assert result["n_covering"] == 15
    assert result["breadth_cov"] == round(2.0 / 15, 4)     # (3-1)/15

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


# ---------------------------------------------------------------------------
# Mutation gate 1 heal — zero-analyst groups must not silently become value=0.0
# (production audit, commit 576959b11804: BRK-B EPS 0q recorded average=high=low=0.0
# with missingness_reason NULL while covering_analyst_count was 0; COKE/CRVL shared
# a byte-identical provider_payload_hash proving the zeros were the provider's empty-
# response shape, not company facts). See collectors/equity_revisions._expectation_rows.
# ---------------------------------------------------------------------------

_NON_COUNT_OBSERVATION_TYPES = ("average", "median", "high", "low", "growth", "year_ago")


def _zero_analyst_eps_frame() -> pd.DataFrame:
    """EPS frame whose '0q' horizon is the provider's empty-response shape: every
    numeric field (including numberOfAnalysts) reads 0.0, mirroring the audited
    BRK-B / COKE / CRVL payloads.  The '+1y' horizon stays normally covered so the
    fix is proven scoped to the (metric, horizon) group, not the whole ticker."""
    return pd.DataFrame(
        {
            "avg": [0.0, 11.0],
            "median": [0.0, 10.9],
            "high": [0.0, 13.0],
            "low": [0.0, 9.0],
            "numberOfAnalysts": [0, 21],
            "growth": [0.0, 0.2],
            "yearAgoEps": [0.0, 9.0],
        },
        index=["0q", "+1y"],
    )


def test_zero_analyst_group_types_every_non_count_field_as_unestimable(tmp_path: Path):
    """(a) A (metric, horizon) group with covering_analyst_count == 0 must emit
    value=None + missingness_reason='UNESTIMABLE' for average/median/high/low/
    growth/year_ago, regardless of the literal (zero) number the provider returned."""
    _run(tmp_path, "scheduled-1", _Ticker(earnings=_zero_analyst_eps_frame(), revenue=_revenue_frame()))
    rows = _observations(tmp_path)
    group = rows[(rows["metric"] == "EPS") & (rows["horizon_label_raw"] == "0q")]
    for observation_type in _NON_COUNT_OBSERVATION_TYPES:
        row = group[group["observation_type"] == observation_type].iloc[0]
        assert pd.isna(row["value"]), f"{observation_type} should be None, got {row['value']!r}"
        assert row["missingness_reason"] == "UNESTIMABLE", (
            f"{observation_type} missingness_reason should be UNESTIMABLE, got {row['missingness_reason']!r}"
        )


def test_zero_analyst_group_keeps_the_literal_zero_count_with_null_missingness(tmp_path: Path):
    """(b) covering_analyst_count itself keeps the literal provider 0, with NULL
    missingness — it is the genuine, interpretable field a consumer reads to detect
    the non-estimable condition, and must never itself be swept into missingness."""
    _run(tmp_path, "scheduled-1", _Ticker(earnings=_zero_analyst_eps_frame(), revenue=_revenue_frame()))
    rows = _observations(tmp_path)
    covering = rows[
        (rows["metric"] == "EPS")
        & (rows["horizon_label_raw"] == "0q")
        & (rows["observation_type"] == "covering_analyst_count")
    ].iloc[0]
    assert covering["value"] == 0
    assert pd.isna(covering["missingness_reason"])


def test_covered_group_with_a_genuine_zero_value_keeps_it_as_a_real_observation(tmp_path: Path):
    """(c) Regression guard for the 7 legitimate zeros the audit found across ALK,
    AOSL, ARE, CBRL, CNC: a covered group (analyst count >= 1) that happens to carry
    a real 0.0 estimate — e.g. a low estimate of 0.0 alongside 19 analysts — must
    still record that 0.0 with NULL missingness, never swept into UNESTIMABLE."""
    revenue = _revenue_frame()
    revenue.loc["0q", "low"] = 0.0
    revenue.loc["0q", "numberOfAnalysts"] = 19
    _run(tmp_path, "scheduled-1", _Ticker(earnings=_estimate_frame(), revenue=revenue))
    rows = _observations(tmp_path)
    low = rows[
        (rows["metric"] == "revenue")
        & (rows["horizon_label_raw"] == "0q")
        & (rows["observation_type"] == "low")
    ].iloc[0]
    assert low["value"] == 0.0
    assert pd.isna(low["missingness_reason"])
    covering = rows[
        (rows["metric"] == "revenue")
        & (rows["horizon_label_raw"] == "0q")
        & (rows["observation_type"] == "covering_analyst_count")
    ].iloc[0]
    assert covering["value"] == 19
    assert pd.isna(covering["missingness_reason"])


def test_group_with_analyst_count_column_entirely_absent_is_non_estimable(tmp_path: Path):
    """(d) A group whose covering-analyst-count field is entirely absent (not merely
    zero) must also be treated as NON-ESTIMABLE — 'unavailable OR equal to 0' per the
    frozen spec — and forces the same typed-missingness fields."""
    earnings = _estimate_frame().drop(columns=["numberOfAnalysts"])
    _run(tmp_path, "scheduled-1", _Ticker(earnings=earnings, revenue=_revenue_frame()))
    rows = _observations(tmp_path)
    group = rows[(rows["metric"] == "EPS") & (rows["horizon_label_raw"] == "0q")]
    for observation_type in _NON_COUNT_OBSERVATION_TYPES:
        row = group[group["observation_type"] == observation_type].iloc[0]
        assert pd.isna(row["value"])
        assert row["missingness_reason"] == "UNESTIMABLE"
    covering = group[group["observation_type"] == "covering_analyst_count"].iloc[0]
    assert pd.isna(covering["value"])
    assert covering["missingness_reason"] == "NOT_APPLICABLE"


def test_observation_id_formula_is_undisturbed_by_the_missingness_repair(tmp_path: Path):
    """(e) observation_id is a deterministic hash of (session, provider, record_class,
    payload_hash, ticker, metric, raw_horizon, observation_type) — it must never
    depend on value/missingness, for both the newly-repaired non-estimable rows and
    the unaffected covered rows, proving the tuple/hashing was not disturbed."""
    _run(tmp_path, "scheduled-1", _Ticker(earnings=_zero_analyst_eps_frame(), revenue=_revenue_frame()))
    rows = _observations(tmp_path)
    attempt = _attempts(tmp_path).iloc[0]
    session_id = attempt["collection_session_id"]
    payload_hash = attempt["response_payload_hash"]

    def _expected_id(record_class: str, ticker: str, metric: str, raw_horizon: str, observation_type: str) -> str:
        return revisions._canonical_sha256((
            session_id, "yfinance", record_class, payload_hash, ticker, metric, raw_horizon, observation_type,
        ))

    # A row forced into UNESTIMABLE by this repair still carries the untouched id.
    non_estimable_row = rows[
        (rows["metric"] == "EPS") & (rows["horizon_label_raw"] == "0q") & (rows["observation_type"] == "average")
    ].iloc[0]
    assert non_estimable_row["observation_id"] == _expected_id(
        "earnings_estimate", "ACME", "EPS", "0q", "average"
    )
    # An unaffected covered row keeps the same formula too.
    covered_row = rows[
        (rows["metric"] == "EPS") & (rows["horizon_label_raw"] == "+1y") & (rows["observation_type"] == "average")
    ].iloc[0]
    assert covered_row["observation_id"] == _expected_id(
        "earnings_estimate", "ACME", "EPS", "+1y", "average"
    )


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
