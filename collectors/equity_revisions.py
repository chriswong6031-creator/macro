"""Analyst EPS estimate-REVISION momentum collector (research/STOCK_CONVICTION_V2.md).

Revision momentum — the breadth of analysts RAISING vs lowering, and the drift of the
consensus estimate itself — is the fastest, strongest pre-earnings cross-sectional
predictor in the literature (Mill Street: top-decile 15.6% vs 8.0% bottom; monthly IC
~0.23). It is the locally-unvalidatable-yet (yfinance gives only the CURRENT snapshot,
no history) but literature-validated cousin of the locally-FDR-validated SUE.

This drips a capped batch of US names per build (resumable, never hammers Yahoo) into
  data/revisions/latest.parquet   — newest reading per ticker (the live score reads this)
  data/revisions/history.parquet  — append-only daily snapshots, so the signal accrues a
                                     point-in-time archive we CAN backtest forward.

Fields (forward fiscal year, '+1y'): net_up_30d (up−down analyst count over 30d), breadth
(net/total ∈[−1,1]), est_chg_30d / est_chg_90d (consensus EPS drift %), n_analysts.

W2a (P1-A): add n_covering + breadth_cov
  n_covering  — total number of analysts providing a forward-year EPS estimate (coverage),
                read from the yfinance `earnings_estimate` accessor (Yahoo `earningsEstimate`
                module `numberOfAnalysts`).  This is a SEPARATE accessor from `eps_revisions`
                which carries only the REVISER count — the audited saturation pathology.
                HARD HONESTY RULE: n_covering is set only when the earnings_estimate accessor
                is available AND its numberOfAnalysts field is present and numeric.  If the
                field is absent or non-numeric, n_covering stays None and breadth_cov is not
                computed — it must NEVER silently substitute n_analysts (the reviser count).
  breadth_cov — (up − down) / n_covering, coverage-normalised.  Emitted alongside legacy
                fields (additive — legacy fields are never renamed or removed).  None whenever
                n_covering is absent.

W0.6b (Setup-Species data plane): add estimate DISPERSION + REVENUE revision metrics
  eps_dispersion_norm        — (high_est − low_est) / |mean_est| for the forward-year EPS
                               estimate.  Source: yfinance earnings_estimate accessor columns
                               'high', 'low', 'avg'.  None when avg ≈ 0 or fields missing.
                               High dispersion = wide analyst disagreement.
  rev_growth_fwd             — forward-year implied revenue YoY growth (%): 100 ×
                               (avg_fwd − yearAgoRevenue) / |yearAgoRevenue|.  Source:
                               yfinance revenue_estimate accessor.  None when base ≈ 0.
  rev_est_high_low_spread_norm — (rev_high − rev_low) / |rev_avg| for the forward-year
                               revenue estimate.  Revenue analyst disagreement proxy.
  rev_n_analysts             — numberOfAnalysts from revenue_estimate.  Additive; never
                               substitutes n_analysts or n_covering.

Note: yfinance has no revenue_trend / revenue_revisions endpoint (confirmed 2026-07-03).
The 30d/90d revenue drift columns are structurally unavailable; they are NOT emitted
(omitted rather than fabricated).

All four W0.6b fields are ADDITIVE to the existing schema; no existing field is renamed or
removed.  PIT history behavior is unchanged (append-only history.parquet).

SRC-A1 fiscal period-end anchor (DATA_CLOCK_RIGHTS_MATRIX.md mutation gate 3): each
`earningsTrend` item Yahoo returns carries a top-level `endDate` (the provider's own
fiscal period end for that horizon) alongside `period`; yfinance's public
earnings_estimate/revenue_estimate accessors lift only `period` and discard `endDate`.
`_raw_earnings_trend_items` reads it back from the private `Analysis` attribute the
accessors themselves populate, fully guarded so any failure yields no anchor rather than
raising.  `_period_end_anchors` maps the verbatim provider `endDate` string onto
`period_end` in `_expectation_rows`, keyed on the raw horizon label — never parsed,
never timezone-adjusted, never used to derive `fiscal_period`/`fiscal_year` (those stay
null: deriving them would be a guessed fiscal mapping, which the contract forbids).
`_apply_lineage` then refuses to record a fiscal rollover (same relative horizon label,
different underlying period) as an analyst revision: when the prior and current rows
both carry a real, differing `period_end`, the new row stays a new original instead of a
fabricated `supersedes`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
from typing import Any, Callable

import pandas as pd

from lib import config
from lib.nyse_calendar import session_date

log = logging.getLogger("equity_revisions")
_FRESH_DAYS = 6

# SRC-A1 is a source-owner append-only accrual.  These files deliberately sit
# beside, rather than inside, the legacy revision-breadth artifacts below.
_EXPECTATION_PROVIDER = "yfinance"
_OBSERVATION_COLUMNS = [
    "observation_id", "collection_session_id", "attempt_id", "provider",
    "provider_record_class", "provider_payload_hash", "ticker_compat",
    "issuer_ref", "security_ref", "metric", "horizon_label_raw", "period_end",
    "fiscal_period", "fiscal_year", "observation_type", "value", "unit",
    "currency", "basis", "aggregation_level", "contributor_id",
    "source_effective_at", "source_published_at", "provider_observed_at",
    "system_observed_at", "market_session", "missingness_reason",
    "correction_state", "supersedes_observation_id", "rights_class",
    "provenance_note",
]
_ATTEMPT_COLUMNS = [
    "attempt_id", "collection_session_id", "provider", "ticker_compat",
    "attempted_at", "completed_at", "status", "http_status", "latency_ms",
    "response_payload_hash", "safe_error_class", "safe_error_detail",
    "observation_count",
]
_OBSERVATION_TYPES = (
    "average", "median", "high", "low", "covering_analyst_count", "growth", "year_ago",
)
_FIELD_ALIASES = {
    "average": ("avg", "average", "mean"),
    "median": ("median",),
    "high": ("high",),
    "low": ("low",),
    "covering_analyst_count": ("numberOfAnalysts", "number_of_analysts"),
    "growth": ("growth",),
}


def _canonical_sha256(value: Any) -> str:
    """Hash a JSON-safe value with stable separators and key order."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_timestamp(value: object | None = None) -> pd.Timestamp:
    stamp = pd.Timestamp.now(tz="UTC") if value is None else pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _iso8601(value: object | None = None) -> str:
    return _utc_timestamp(value).isoformat().replace("+00:00", "Z")


def _json_scalar(value: Any) -> Any:
    """Convert provider scalar values without treating absent data as zero."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return _iso8601(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalise_column(column: object) -> str:
    return "".join(character for character in str(column).lower() if character.isalnum())


def _frame_payload(frame: Any) -> list[dict[str, Any]]:
    """Return the stable, complete raw-accessor identity used for replay checks."""
    if frame is None or not hasattr(frame, "index") or not hasattr(frame, "columns"):
        return []
    rows: list[dict[str, Any]] = []
    for horizon in frame.index:
        rows.append({
            "horizon_label_raw": str(horizon),
            "fields": {
                str(column): _json_scalar(frame.loc[horizon, column])
                for column in sorted(frame.columns, key=str)
            },
        })
    return rows


def _safe_http_failure(exc: Exception) -> tuple[str, int | None, str, str]:
    """Classify provider errors without persisting provider bodies or exception text."""
    candidates = [getattr(exc, "status_code", None), getattr(getattr(exc, "response", None), "status_code", None)]
    for candidate in candidates:
        if candidate in (401, 403, 429):
            return f"http_{candidate}", candidate, "provider_http_error", f"http_status_{candidate}"
    match = re.search(r"(?<![0-9])(?:http(?:[ _-]?(?:status|code))?\s*[:=]?\s*)?(401|403|429)(?![0-9])", str(exc).lower())
    if match:
        code = int(match.group(1))
        return f"http_{code}", code, "provider_http_error", f"http_status_{code}"
    return "error", None, "provider_exception", "provider_request_failed"


def _field_value(frame: pd.DataFrame, horizon: object, observation_type: str, metric: str) -> tuple[float | None, str | None]:
    aliases = _FIELD_ALIASES.get(observation_type)
    if observation_type == "year_ago":
        aliases = ("yearAgoEps",) if metric == "EPS" else ("yearAgoRevenue",)
    assert aliases is not None
    columns = {_normalise_column(column): column for column in frame.columns}
    column = next((columns.get(_normalise_column(alias)) for alias in aliases if _normalise_column(alias) in columns), None)
    if column is None:
        return None, "NOT_APPLICABLE"
    value = _finite_number(frame.loc[horizon, column])
    return (value, None) if value is not None else (None, "UNESTIMABLE")


def _market_session(system_observed_at: str) -> str | None:
    """Use the existing NYSE owner; a calendar failure is an explicit null."""
    try:
        return session_date(_utc_timestamp(system_observed_at).to_pydatetime()).isoformat()
    except Exception:  # noqa: BLE001 - a source receipt must not invent a session
        return None


def _raw_earnings_trend_items(client: Any) -> list[dict[str, Any]]:
    """Best-effort read of yfinance's raw earningsTrend items.

    Each item Yahoo returns for `earningsTrend` carries a top-level `endDate` — the
    provider's own fiscal period end for that horizon — alongside `period` (e.g.
    "0q").  yfinance's `Analysis._get_periodic_df` lifts only `period` when it
    builds the public `earnings_estimate`/`revenue_estimate` accessors and discards
    every other item-level key, including `endDate`.  The only known route back to
    the raw items is the private `Analysis` attribute those accessors populate as a
    side effect (`client._analysis._earnings_trend`).

    This function must NEVER raise: a missing attribute, an unexpected shape, an
    absent key, or any other failure yields an empty list rather than failing the
    collection, changing the attempt status, or altering any other field.  This is
    a best-effort anchor read, not a new provider contract.
    """
    try:
        analysis = getattr(client, "_analysis", None)
        raw = getattr(analysis, "_earnings_trend", None) if analysis is not None else None
        if raw is None:
            return []
        if hasattr(raw, "to_dict"):
            records = raw.to_dict(orient="records")
        elif isinstance(raw, list):
            records = raw
        else:
            return []
        return [record for record in records if isinstance(record, dict)]
    except Exception:  # noqa: BLE001 - anchors are best-effort, never fatal
        return []


def _period_end_anchors(items: list[dict[str, Any]]) -> dict[str, str]:
    """Map raw provider horizon label (`period`, e.g. "0q") -> raw `endDate`.

    The provider's value is kept verbatim: no parsing into components, no
    timezone assumptions, no reformatting beyond ensuring it is a plain string.
    A horizon whose item lacks `endDate` simply has no anchor.
    """
    anchors: dict[str, str] = {}
    for item in items:
        try:
            # _json_scalar folds NaN/NaT/None to None uniformly, so a pandas-typed
            # missing endDate (not merely a Python None) is also treated as "no
            # anchor" rather than being stringified into a fake "nan" value.
            period = _json_scalar(item.get("period"))
            end_date = _json_scalar(item.get("endDate"))
            if period is None or end_date is None:
                continue
            anchors[str(period)] = str(end_date)
        except Exception:  # noqa: BLE001 - a single malformed item must not drop the rest
            continue
    return anchors


def _default_collection_session_id(now: object | None = None, environ: dict[str, str] | None = None) -> str:
    """Stable run identity, falling back to the unchanged hourly collection bucket."""
    run_id = (os.environ if environ is None else environ).get("GITHUB_RUN_ID")
    if run_id:
        identity: tuple[str, str] = ("github_run", run_id)
    else:
        identity = ("hourly_bucket", _utc_timestamp(now).floor("h").isoformat())
    return _canonical_sha256(("src-a1", _EXPECTATION_PROVIDER, identity))


def _expectation_rows(
    *,
    ticker: str,
    collection_session_id: str,
    attempt_id: str,
    payload_hash: str,
    frames: dict[str, Any],
    provider_observed_at: str,
    system_observed_at: str,
    period_end_by_horizon: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    anchors = period_end_by_horizon or {}
    for metric, record_class in (("EPS", "earnings_estimate"), ("revenue", "revenue_estimate")):
        frame = frames.get(record_class)
        if frame is None or not hasattr(frame, "index") or not hasattr(frame, "columns"):
            continue
        for horizon in sorted(frame.index, key=str):
            raw_horizon = str(horizon)
            # A group (metric, horizon) is NON-ESTIMABLE when the provider's own
            # covering-analyst count is unavailable or zero — the provider's empty-
            # response shape (see mutation gate 1).  In such a group, every other
            # observation_type that _field_value resolved as PRESENT (missingness
            # None — an interpretable value, the actual mutation-gate violation) is
            # forced to typed missingness, regardless of what number the provider
            # returned.  A field that _field_value already typed as missing (e.g.
            # NOT_APPLICABLE because the provider exposes no such column at all, or
            # an existing UNESTIMABLE) is left exactly as returned — that reason is
            # already lawful and more specific than a blanket UNESTIMABLE would be.
            # covering_analyst_count itself always keeps its literal provider value
            # (including a genuine 0) via _field_value below.
            covering_value, _covering_missingness = _field_value(
                frame, horizon, "covering_analyst_count", metric
            )
            non_estimable_group = covering_value is None or covering_value == 0
            for observation_type in _OBSERVATION_TYPES:
                value, missingness = _field_value(frame, horizon, observation_type, metric)
                if non_estimable_group and observation_type != "covering_analyst_count" and missingness is None:
                    value, missingness = None, "UNESTIMABLE"
                observation_id = _canonical_sha256((
                    collection_session_id, _EXPECTATION_PROVIDER, record_class, payload_hash,
                    ticker, metric, raw_horizon, observation_type,
                ))
                rows.append({
                    "observation_id": observation_id,
                    "collection_session_id": collection_session_id,
                    "attempt_id": attempt_id,
                    "provider": _EXPECTATION_PROVIDER,
                    "provider_record_class": record_class,
                    "provider_payload_hash": payload_hash,
                    "ticker_compat": ticker,
                    "issuer_ref": None,
                    "security_ref": None,
                    "metric": metric,
                    "horizon_label_raw": raw_horizon,
                    # A provider fact, captured verbatim when the anchor is available
                    # (see _period_end_anchors); never guessed, never parsed.  It does
                    # NOT get its own missingness_reason and does not participate in
                    # the non_estimable_group typed-missingness logic above — a row
                    # can carry a real period_end alongside a typed-missing value.
                    "period_end": anchors.get(raw_horizon),
                    # fiscal_period/fiscal_year remain unconditionally null: deriving
                    # them from period_end would be a guessed fiscal mapping, which
                    # the contract forbids (DATA_CLOCK_RIGHTS_MATRIX.md SRC-A1).
                    "fiscal_period": None,
                    "fiscal_year": None,
                    "observation_type": observation_type,
                    "value": value,
                    "unit": None,
                    "currency": None,
                    "basis": None,
                    "aggregation_level": "consensus_snapshot",
                    "contributor_id": None,
                    # yfinance's estimate accessors do not expose source-issued clocks.
                    "source_effective_at": None,
                    "source_published_at": None,
                    "provider_observed_at": provider_observed_at,
                    "system_observed_at": system_observed_at,
                    "market_session": _market_session(system_observed_at),
                    "missingness_reason": missingness,
                    "correction_state": "original",
                    "supersedes_observation_id": None,
                    "rights_class": "UNKNOWN",
                    "provenance_note": f"yfinance_{record_class}_prospective_snapshot",
                })
    return rows


def _read_parquet(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame = pd.read_parquet(path)
    return frame.reindex(columns=columns)


def _write_parquet(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = frame.reindex(columns=columns)
    temporary = path.with_suffix(path.suffix + ".tmp")
    ordered.to_parquet(temporary, index=False)
    temporary.replace(path)


def _apply_lineage(rows: list[dict[str, Any]], existing: pd.DataFrame) -> None:
    """Mark changed values as append-only supersessions; nulls never replace good rows."""
    if existing.empty:
        return
    key_columns = ["provider", "provider_record_class", "ticker_compat", "metric", "horizon_label_raw", "observation_type"]
    for row in rows:
        if row["value"] is None:
            row["correction_state"] = "missing"
            continue
        prior = existing
        for column in key_columns:
            prior = prior[prior[column] == row[column]]
        prior = prior[prior["value"].notna()]
        if prior.empty:
            continue
        newest = prior.sort_values("system_observed_at", kind="stable").iloc[-1]
        # Mutation gate 3: a fiscal rollover is not a revision.  horizon_label_raw
        # is a RELATIVE provider label (e.g. "0q" always means "the current
        # quarter"), so the same key can legitimately refer to a different
        # underlying fiscal period across two observations.  When both the prior
        # and the current row carry a real (non-null) period_end and those differ,
        # this is a rollover: leave the row a new original rather than fabricating
        # a supersession.  A null on either side, or equal non-null period_ends,
        # falls through to the existing value comparison exactly as today.
        prior_period_end = _json_scalar(newest["period_end"])
        current_period_end = _json_scalar(row["period_end"])
        if prior_period_end is not None and current_period_end is not None and prior_period_end != current_period_end:
            continue
        same_value = (
            _json_scalar(newest["value"]) == _json_scalar(row["value"])
            and _json_scalar(newest["unit"]) == _json_scalar(row["unit"])
            and _json_scalar(newest["currency"]) == _json_scalar(row["currency"])
            and _json_scalar(newest["basis"]) == _json_scalar(row["basis"])
        )
        if same_value:
            row["correction_state"] = "unchanged"
        else:
            row["correction_state"] = "supersedes"
            row["supersedes_observation_id"] = newest["observation_id"]


def accrue_expectation_observations(
    tickers: list[str],
    *,
    output_dir: Path | None = None,
    collection_session_id: str | None = None,
    system_observed_at: object | None = None,
    ticker_factory: Callable[[str], Any] | None = None,
) -> dict[str, int]:
    """Accrue one bounded SRC-A1 collection session without changing legacy artifacts.

    Callers may inject both paths and the provider factory for hermetic tests.  The
    default session identifier is deterministic for the collection invocation;
    schedulers that have a stronger run identity can pass it explicitly.
    """
    out_dir = output_dir or (config.data_dir() / "revisions")
    now = _utc_timestamp()
    if system_observed_at is not None:
        requested_clock = _utc_timestamp(system_observed_at)
        if abs((now - requested_clock).total_seconds()) > 60:
            raise ValueError("SRC-A1 refuses a historical system_observed_at; current snapshots cannot be backfilled")
    session_id = collection_session_id or _default_collection_session_id(now)
    observations_path = out_dir / "expectation_observations.parquet"
    attempts_path = out_dir / "expectation_attempts.parquet"
    existing_observations = _read_parquet(observations_path, _OBSERVATION_COLUMNS)
    existing_attempts = _read_parquet(attempts_path, _ATTEMPT_COLUMNS)
    new_observations: list[dict[str, Any]] = []
    new_attempts: list[dict[str, Any]] = []

    if ticker_factory is None:
        import yfinance as yf
        ticker_factory = yf.Ticker

    for ticker in sorted(set(tickers)):
        attempted_at = _iso8601()
        started = pd.Timestamp.now(tz="UTC")
        frames: dict[str, Any] = {}
        accessor_errors: list[Exception] = []
        try:
            client = ticker_factory(ticker)
            for record_class in ("earnings_estimate", "revenue_estimate"):
                try:
                    frames[record_class] = getattr(client, record_class)
                except Exception as exc:  # noqa: BLE001 - classified below without raw text
                    accessor_errors.append(exc)
                    frames[record_class] = None
            provider_observed_at = _iso8601()
            # Fiscal period-end anchor read is fully guarded on top of its own
            # internal guarding: it must never fail this attempt, never change its
            # status, and never touch any other field (mutation gate 3).
            try:
                period_end_by_horizon = _period_end_anchors(_raw_earnings_trend_items(client))
            except Exception:  # noqa: BLE001 - anchors are best-effort, never fatal
                period_end_by_horizon = {}
        except Exception as exc:  # noqa: BLE001 - provider construction/request failure
            completed_at = _iso8601()
            status, http_status, error_class, error_detail = _safe_http_failure(exc)
            payload_hash = None
            attempt_id = _canonical_sha256((session_id, _EXPECTATION_PROVIDER, ticker, payload_hash))
            if attempt_id not in set(existing_attempts["attempt_id"].dropna().astype(str)):
                new_attempts.append({
                    "attempt_id": attempt_id, "collection_session_id": session_id,
                    "provider": _EXPECTATION_PROVIDER, "ticker_compat": ticker,
                    "attempted_at": attempted_at, "completed_at": completed_at,
                    "status": status, "http_status": http_status,
                    "latency_ms": int((pd.Timestamp.now(tz="UTC") - started).total_seconds() * 1000),
                    "response_payload_hash": None, "safe_error_class": error_class,
                    "safe_error_detail": error_detail, "observation_count": 0,
                })
            continue

        payload = {record_class: _frame_payload(frame) for record_class, frame in sorted(frames.items())}
        payload_hash = _canonical_sha256(payload)
        attempt_id = _canonical_sha256((session_id, _EXPECTATION_PROVIDER, ticker, payload_hash))
        if attempt_id in set(existing_attempts["attempt_id"].dropna().astype(str)):
            continue
        system_observed_at = _iso8601()
        response_rows = _expectation_rows(
            ticker=ticker, collection_session_id=session_id, attempt_id=attempt_id,
            payload_hash=payload_hash, frames=frames, provider_observed_at=provider_observed_at,
            system_observed_at=system_observed_at, period_end_by_horizon=period_end_by_horizon,
        )
        _apply_lineage(response_rows, existing_observations)
        deduped_rows = [
            row for row in response_rows
            if row["observation_id"] not in set(existing_observations["observation_id"].dropna().astype(str))
        ]
        valid_metrics = {row["metric"] for row in response_rows if row["value"] is not None}
        malformed_response = any(
            frame is not None and (not hasattr(frame, "index") or not hasattr(frame, "columns"))
            for frame in frames.values()
        )
        if malformed_response:
            status, error_class, error_detail = "malformed", "malformed_response", "unsupported_estimate_shape"
        elif not response_rows and accessor_errors:
            status, http_status, error_class, error_detail = _safe_http_failure(accessor_errors[0])
        elif not response_rows:
            status, error_class, error_detail = "null", "empty_response", "no_estimate_rows"
        elif accessor_errors or len(valid_metrics) < 2:
            status = "partial"
            if accessor_errors:
                _, http_status, error_class, error_detail = _safe_http_failure(accessor_errors[0])
            else:
                http_status, error_class, error_detail = None, "partial_response", "one_or_more_metrics_unavailable"
        else:
            status, error_class, error_detail = "success", None, None
        if not (accessor_errors and not response_rows) and not (accessor_errors and response_rows):
            http_status = None
        new_observations.extend(deduped_rows)
        new_attempts.append({
            "attempt_id": attempt_id, "collection_session_id": session_id,
            "provider": _EXPECTATION_PROVIDER, "ticker_compat": ticker,
            "attempted_at": attempted_at, "completed_at": _iso8601(), "status": status,
            "http_status": http_status,
            "latency_ms": int((pd.Timestamp.now(tz="UTC") - started).total_seconds() * 1000),
            "response_payload_hash": payload_hash, "safe_error_class": error_class,
            "safe_error_detail": error_detail, "observation_count": len(response_rows),
        })

    if new_observations:
        combined_observations = pd.concat([existing_observations, pd.DataFrame(new_observations)], ignore_index=True)
        _write_parquet(observations_path, combined_observations.drop_duplicates(subset=["observation_id"], keep="first"), _OBSERVATION_COLUMNS)
    if new_attempts:
        combined_attempts = pd.concat([existing_attempts, pd.DataFrame(new_attempts)], ignore_index=True)
        _write_parquet(attempts_path, combined_attempts.drop_duplicates(subset=["attempt_id"], keep="first"), _ATTEMPT_COLUMNS)
    return {"attempts": len(new_attempts), "observations": len(new_observations)}


def _one(ticker: str, ticker_client: Any | None = None) -> dict | None:
    if ticker_client is None:
        import yfinance as yf
        ticker_client = yf.Ticker(ticker)
    t = ticker_client
    try:
        rev = t.eps_revisions
        trend = t.eps_trend
    except Exception:  # noqa: BLE001
        return None
    if rev is None or trend is None or not hasattr(rev, "index"):
        return None
    # forward fiscal year ('+1y') is the cleanest, most-covered horizon; fall back to '0y'
    row = None
    for key in ("+1y", "0y"):
        if key in rev.index:
            row = key
            break
    if row is None:
        return None

    def _num(df, r, c):
        try:
            v = float(df.loc[r, c]); return v if v == v else None
        except Exception:  # noqa: BLE001
            return None
    up = _num(rev, row, "upLast30days") or 0.0
    dn = _num(rev, row, "downLast30days") or 0.0
    tot = up + dn
    cur = _num(trend, row, "current")
    d30 = _num(trend, row, "30daysAgo")
    d90 = _num(trend, row, "90daysAgo")

    def _chg(now, then):
        if now is None or then is None or abs(then) < 1e-6:
            return None
        return round((now - then) / abs(then) * 100.0, 2)

    # W2a (P1-A): n_covering from the earnings_estimate accessor.
    # HARD HONESTY RULE: this MUST come from earnings_estimate.numberOfAnalysts, never
    # from `tot` (= up+down from eps_revisions = the REVISER count = the saturation bug).
    # If the accessor is absent, non-numeric, or the field is missing, n_covering stays
    # None and breadth_cov is not computed.
    n_covering: int | None = None
    breadth_cov: float | None = None
    try:
        ee = t.earnings_estimate
        # earnings_estimate is a DataFrame indexed by horizon (e.g. '0q','1q','+1y','0y')
        # with column 'numberOfAnalysts' (Yahoo earningsEstimate.numberOfAnalysts).
        if ee is not None and hasattr(ee, "index") and "numberOfAnalysts" in ee.columns:
            if row in ee.index:
                raw = ee.loc[row, "numberOfAnalysts"]
            else:
                # fall back to any available '+1y' or '0y' row
                raw = None
                for k in ("+1y", "0y"):
                    if k in ee.index:
                        raw = ee.loc[k, "numberOfAnalysts"]
                        break
            if raw is not None:
                v = float(raw)
                if v == v and v >= 1:   # NaN guard + positive guard
                    n_covering = int(v)
                    breadth_cov = round((up - dn) / n_covering, 4)
    except Exception:  # noqa: BLE001
        # accessor unavailable: honour the hard honesty rule — both stay None
        n_covering = None
        breadth_cov = None

    # W0.6b: EPS estimate DISPERSION from earnings_estimate high/low/avg.
    # Normalised by |avg| so it's comparable across stocks.
    # None when avg ≈ 0 or any of the three columns are missing/NaN.
    eps_dispersion_norm: float | None = None
    try:
        ee = t.earnings_estimate  # may already be fetched above (yfinance caches)
        if ee is not None and hasattr(ee, "index"):
            ee_row = None
            for k in ("+1y", "0y"):
                if k in ee.index:
                    ee_row = k
                    break
            if ee_row is not None:
                for col_set in (("high", "low", "avg"), ("High", "Low", "Avg")):
                    c_hi, c_lo, c_av = col_set
                    if all(c in ee.columns for c in col_set):
                        hi = ee.loc[ee_row, c_hi]
                        lo = ee.loc[ee_row, c_lo]
                        av = ee.loc[ee_row, c_av]
                        try:
                            hi, lo, av = float(hi), float(lo), float(av)
                            if hi == hi and lo == lo and av == av and abs(av) >= 1e-6:
                                eps_dispersion_norm = round((hi - lo) / abs(av), 4)
                        except (TypeError, ValueError):
                            pass
                        break
    except Exception:  # noqa: BLE001
        eps_dispersion_norm = None

    # W0.6b: REVENUE revision metrics from revenue_estimate accessor.
    # revenue_estimate is a DataFrame indexed by horizon, with columns:
    #   avg, low, high, numberOfAnalysts, yearAgoRevenue, growth  (Yahoo revenueEstimate)
    # yfinance does NOT expose a revenue_trend / revenue_revisions endpoint — there is no
    # 30daysAgo / 90daysAgo column for revenue estimates (confirmed 2026-07-03).
    # We therefore emit:
    #   rev_growth_fwd  — forward-year implied revenue growth vs yearAgoRevenue (YoY %)
    #   rev_est_high_low_spread_norm — (high − low) / avg revenue estimate (dispersion)
    #   rev_n_analysts  — numberOfAnalysts from revenue_estimate (additive, never
    #                     substitutes n_analysts or n_covering)
    # The 30d/90d drift columns are structurally unavailable from yfinance; they are
    # intentionally omitted rather than fabricated.
    rev_growth_fwd: float | None = None
    rev_est_high_low_spread_norm: float | None = None
    rev_n_analysts: int | None = None
    try:
        re_df = t.revenue_estimate
        if re_df is not None and hasattr(re_df, "index"):
            re_row = None
            for k in ("+1y", "0y"):
                if k in re_df.index:
                    re_row = k
                    break
            if re_row is not None:
                def _rev_num(col: str):
                    try:
                        if col not in re_df.columns:
                            return None
                        v = float(re_df.loc[re_row, col])
                        return v if v == v else None
                    except Exception:  # noqa: BLE001
                        return None

                re_avg = _rev_num("avg")
                re_hi = _rev_num("high")
                re_lo = _rev_num("low")
                re_yago = _rev_num("yearAgoRevenue")
                re_na = _rev_num("numberOfAnalysts")

                # YoY growth: (fwd_avg − year_ago) / |year_ago| * 100
                if re_avg is not None and re_yago is not None and abs(re_yago) >= 1:
                    rev_growth_fwd = round((re_avg - re_yago) / abs(re_yago) * 100.0, 2)
                # Spread dispersion: (high − low) / avg
                if re_hi is not None and re_lo is not None and re_avg is not None and abs(re_avg) >= 1:
                    rev_est_high_low_spread_norm = round((re_hi - re_lo) / abs(re_avg), 4)
                if re_na is not None and re_na >= 1:
                    rev_n_analysts = int(re_na)
    except Exception:  # noqa: BLE001
        rev_growth_fwd = None
        rev_est_high_low_spread_norm = None
        rev_n_analysts = None

    out = {
        "net_up_30d": up - dn,
        "breadth": round((up - dn) / tot, 3) if tot >= 1 else None,
        "est_chg_30d": _chg(cur, d30),
        "est_chg_90d": _chg(cur, d90),
        "n_analysts": int(tot) if tot else None,
        # W2a additions — None when earnings_estimate accessor is unavailable
        "n_covering": n_covering,
        "breadth_cov": breadth_cov,
        # W0.6b additions — None when accessor is unavailable or base ≈ 0
        "eps_dispersion_norm": eps_dispersion_norm,
        "rev_growth_fwd": rev_growth_fwd,
        "rev_est_high_low_spread_norm": rev_est_high_low_spread_norm,
        "rev_n_analysts": rev_n_analysts,
    }
    return out if any(v is not None for v in out.values()) else None


def _universe() -> list[str]:
    tk: list[str] = []
    for grp in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            tk += list(pd.read_parquet(p).index.astype(str))
    return sorted(set(tk))


def fetch_revisions(
    max_new: int = 200,
    *,
    expectation_output_dir: Path | None = None,
    collection_session_id: str | None = None,
    system_observed_at: object | None = None,
) -> int:
    """Drip up to ``max_new`` STALEST names; update latest.parquet + append a dated
    snapshot to history.parquet. Best-effort — any per-name failure is skipped."""
    out_dir = config.data_dir() / "revisions"
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_p = out_dir / "latest.parquet"
    latest = pd.read_parquet(latest_p) if latest_p.exists() else pd.DataFrame()
    today = pd.Timestamp.now("UTC").normalize().tz_localize(None)

    uni = _universe()
    if not uni:
        log.warning("no constituents for revisions universe"); return 0
    asof = latest["asof"] if "asof" in latest.columns else pd.Series(dtype="datetime64[ns]")
    fresh = set(latest.index[(today - pd.to_datetime(asof)).dt.days < _FRESH_DAYS]) if len(latest) else set()
    todo = [t for t in uni if t not in fresh][:max_new]
    if not todo:
        log.info("revisions: all %d names fresh (<%dd)", len(uni), _FRESH_DAYS); return 0

    rows = {}
    # SRC-A1 has the same frozen target set and cadence as this existing drip;
    # it does not add a scheduler, broader universe, or freshness policy.
    try:
        expectation_result = accrue_expectation_observations(
            todo,
            output_dir=expectation_output_dir,
            collection_session_id=collection_session_id,
            system_observed_at=system_observed_at,
        )
    except Exception as exc:  # noqa: BLE001 - preserve legacy revisions availability
        log.warning("SRC-A1 expectation accrual skipped (%s)", type(exc).__name__)
        expectation_result = {"attempts": 0, "observations": 0}
    for t in todo:
        try:
            r = _one(t)
        except Exception as e:  # noqa: BLE001
            log.debug("revisions %s skipped: %s", t, e); continue
        if r:
            r["asof"] = today
            rows[t] = r
    if not rows:
        log.info(
            "revisions: drip fetched 0 of %d (SRC-A1 attempts=%d observations=%d)",
            len(todo), expectation_result["attempts"], expectation_result["observations"],
        )
        return 0
    new = pd.DataFrame.from_dict(rows, orient="index")
    merged = new if latest.empty else pd.concat([latest[~latest.index.isin(new.index)], new])
    merged.to_parquet(latest_p)
    # append a dated snapshot for forward PIT accrual
    hist_p = out_dir / "history.parquet"
    snap = new.copy(); snap["date"] = today
    snap = snap.reset_index(names="ticker")
    if hist_p.exists():
        snap = pd.concat([pd.read_parquet(hist_p), snap], ignore_index=True)
        snap = snap.drop_duplicates(subset=["date", "ticker"], keep="last")
    snap.to_parquet(hist_p)
    log.info(
        "revisions: +%d names (latest now %d, history %d rows; SRC-A1 attempts=%d observations=%d)",
        len(rows), len(merged), len(snap), expectation_result["attempts"], expectation_result["observations"],
    )
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_revisions(int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 50)
