"""Frozen semantic validators shared by options episode producers and consumers.

This module is deliberately independent of both campaign implementations and of
the episode builder.  It contains no ledger writer and no display dependency.
The source engine retains its deeper price-evidence validation; these functions
pin the decision-time, identity, clock, horizon, and episode-join invariants that
every downstream consumer must enforce again at its own trust boundary.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine.session_digest import ET, session_window_et
from lib import nyse_calendar

EPISODE_SCHEMA = "options.signal_episode/v1"
H60_SCHEMA = "options.signal_episode_outcome/v1"
SESSION_SCHEMA = "options.signal_episode_session_outcome/v1"
H60_MEASUREMENT_VERSION = "h60-aligned-bars/v1"
SESSION_MEASUREMENT_VERSION = "session-close-aligned-bars/v1"
PRICE_RECEIPT_SCHEMA = "polygon.intraday_price_receipt/v1"
SESSION_HORIZONS = {"eod": 0, "1d": 1, "3d": 3, "5d": 5, "10d": 10}

SOURCE_FALSE_AUTHORITY = {
    "may_originate": False,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "may_trade": False,
    "may_publish_pick": False,
    "may_train_prophet": False,
}


class EpisodeSourceContractError(ValueError):
    """A source episode or outcome violates the frozen semantic contract."""


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:24]}"


def _canonical_utc(value: object, field: str) -> datetime:
    if type(value) is not str:
        raise EpisodeSourceContractError(f"{field} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpisodeSourceContractError(f"{field} is not a timestamp") from exc
    if parsed.tzinfo is None:
        raise EpisodeSourceContractError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _canonical_date(value: object, field: str) -> date:
    if type(value) is not str:
        raise EpisodeSourceContractError(f"{field} must be an exact date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise EpisodeSourceContractError(f"{field} is not a date") from exc
    if parsed.isoformat() != value:
        raise EpisodeSourceContractError(f"{field} must be an exact date")
    return parsed


def _finite_number(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EpisodeSourceContractError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        qualifier = " positive" if positive else ""
        raise EpisodeSourceContractError(f"{field} must be a finite{qualifier} number")
    return number


def _price_source_matches_ticker(row: dict[str, Any], ticker: str) -> None:
    price_source = row["provenance"].get("price_source")
    if type(price_source) is not str or Path(price_source).name != f"{ticker}.parquet":
        raise EpisodeSourceContractError(
            "complete outcome price source must match the episode ticker"
        )
    if row["provenance"].get("source_receipt_schema") != PRICE_RECEIPT_SCHEMA:
        raise EpisodeSourceContractError(
            "complete outcome lacks the frozen Polygon price receipt"
        )


def validate_episode_pit(row: dict[str, Any]) -> None:
    """Validate the complete immutable decision-time/PIT episode semantics."""
    if row.get("schema") != EPISODE_SCHEMA:
        raise EpisodeSourceContractError(f"episode schema must be {EPISODE_SCHEMA!r}")
    source = row.get("source")
    source_event_id = row.get("source_event_id")
    if type(source) is not str or not source or source != source.strip():
        raise EpisodeSourceContractError("source must be normalized")
    if (
        type(source_event_id) is not str
        or not source_event_id
        or source_event_id != source_event_id.strip()
    ):
        raise EpisodeSourceContractError("source_event_id must be normalized")
    expected_episode_id = _stable_id("osep", EPISODE_SCHEMA, source, source_event_id)
    if row.get("episode_id") != expected_episode_id:
        raise EpisodeSourceContractError(
            "episode_id must be stable for schema, source, and source_event_id"
        )

    event_time = _canonical_utc(row.get("event_time"), "event_time")
    observed_at = _canonical_utc(row.get("observed_at"), "observed_at")
    decision_at = _canonical_utc(row.get("decision_at"), "decision_at")
    available_at = _canonical_utc(row.get("available_at"), "available_at")
    published_at = (
        _canonical_utc(row.get("published_at"), "published_at")
        if row.get("published_at") is not None
        else None
    )
    if not (event_time <= observed_at <= decision_at <= available_at):
        raise EpisodeSourceContractError(
            "clock order must be event_time <= observed_at <= decision_at <= available_at"
        )
    if published_at is not None and published_at < available_at:
        raise EpisodeSourceContractError("published_at cannot predate durable availability")
    if row.get("anchor_strategy") != "durable_available_at":
        raise EpisodeSourceContractError(
            "episode anchor_strategy must be durable_available_at"
        )

    session = _canonical_date(row.get("session_date"), "session_date")
    if not nyse_calendar.is_session(session):
        raise EpisodeSourceContractError("session_date is not an NYSE session")
    if event_time.astimezone(ET).date() != session:
        raise EpisodeSourceContractError(
            "event_time does not belong to session_date in exchange time"
        )
    open_et, close_et = session_window_et(session)
    open_utc = open_et.astimezone(timezone.utc)
    close_utc = close_et.astimezone(timezone.utc)
    if not (open_utc <= event_time < close_utc):
        raise EpisodeSourceContractError(
            "episode event_time must remain inside the regular session"
        )
    if observed_at < open_utc or any(
        value.astimezone(ET).date() != session
        for value in (observed_at, decision_at, available_at)
    ):
        raise EpisodeSourceContractError(
            "decision-time clocks must remain on the event exchange session"
        )

    ticker = row.get("ticker")
    if type(ticker) is not str or not ticker or ticker != ticker.strip().upper():
        raise EpisodeSourceContractError("ticker must be normalized uppercase")
    contract = row.get("contract")
    if not isinstance(contract, dict) or contract.get("right") not in {"C", "P"}:
        raise EpisodeSourceContractError("contract right must be C or P")
    _finite_number(contract.get("strike"), "contract.strike", positive=True)
    expiration = _canonical_date(contract.get("expiration"), "contract.expiration")
    if expiration < session:
        raise EpisodeSourceContractError("contract expiration precedes the event session")

    decision = row.get("decision")
    if not isinstance(decision, dict) or decision.get("authority") != SOURCE_FALSE_AUTHORITY:
        raise EpisodeSourceContractError("episode decision authority must remain false")
    if (
        decision.get("disposition") != "watch"
        or decision.get("reason") != "notable_flow_event"
        or decision.get("underlying_direction") != "none"
        or decision.get("option_action") != "none"
    ):
        raise EpisodeSourceContractError(
            "episode is outside the frozen descriptive watch census"
        )

    features = row.get("feature_snapshot")
    if not isinstance(features, dict):
        raise EpisodeSourceContractError("feature_snapshot must be an object")
    if features.get("flow_side") not in {"~buy", "~sell", "mixed"}:
        raise EpisodeSourceContractError("feature_snapshot.flow_side is invalid")
    premium = _finite_number(
        features.get("premium_usd"), "feature_snapshot.premium_usd", positive=True
    )
    if features.get("selection_rule") != "premium_floor/v1":
        raise EpisodeSourceContractError("episode selection_rule is outside v1")
    selection_floor = _finite_number(
        features.get("selection_floor_usd"), "feature_snapshot.selection_floor_usd"
    )
    if selection_floor < 0 or premium < selection_floor:
        raise EpisodeSourceContractError("episode premium is below its frozen floor")
    if features.get("selection_root_class") not in {"etf_anchor", "single_name"}:
        raise EpisodeSourceContractError("episode selection_root_class is invalid")
    contracts = features.get("contracts")
    if type(contracts) is not int or contracts < 1:
        raise EpisodeSourceContractError("episode contracts must be a positive integer")
    avg_price = _finite_number(
        features.get("avg_option_trade_price"),
        "feature_snapshot.avg_option_trade_price",
        positive=True,
    )
    expected_avg = premium / (contracts * 100.0)
    if not math.isclose(avg_price, expected_avg, abs_tol=0.0051):
        raise EpisodeSourceContractError(
            "avg_option_trade_price disagrees with premium and contracts"
        )
    dte = features.get("dte")
    if dte is not None and (type(dte) is not int or dte != (expiration - session).days):
        raise EpisodeSourceContractError("episode dte disagrees with expiration and session")

    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        raise EpisodeSourceContractError("episode provenance must be an object")
    if provenance.get("source_artifact") != f"live_flow/events/{session.isoformat()}.jsonl":
        raise EpisodeSourceContractError(
            "source_artifact session must match the episode session"
        )
    snapshot_asof = _canonical_utc(
        provenance.get("source_snapshot_asof"), "provenance.source_snapshot_asof"
    )
    if snapshot_asof != available_at:
        raise EpisodeSourceContractError(
            "source_snapshot_asof must equal durable event availability"
        )
    if provenance.get("feature_cutoff") != row.get("available_at"):
        raise EpisodeSourceContractError("feature_cutoff must equal available_at")
    oi_vintage = provenance.get("oi_vintage")
    if oi_vintage is not None:
        oi_date = _canonical_date(oi_vintage, "provenance.oi_vintage")
        if oi_date >= session or not nyse_calendar.is_session(oi_date):
            raise EpisodeSourceContractError(
                "OI vintage must be a real session before the event"
            )
    if features.get("vol_gt_prior_oi") is not None and oi_vintage is None:
        raise EpisodeSourceContractError(
            "vol_gt_prior_oi requires an exact prior OI vintage"
        )
    quality = row.get("quality")
    if (
        not isinstance(quality, dict)
        or quality.get("availability_exact") is not True
        or quality.get("trade_direction_reliability") != "soft"
        or quality.get("source_baseline") != "floor"
    ):
        raise EpisodeSourceContractError("episode quality differs from the frozen floor seam")


def validate_h60_outcome_join(row: dict[str, Any], episode: dict[str, Any]) -> None:
    """Validate H+60 identity, clocks, horizon, and immutable episode join."""
    validate_episode_pit(episode)
    if row.get("schema") != H60_SCHEMA or row.get("horizon_minutes") != 60:
        raise EpisodeSourceContractError("H+60 outcome schema or horizon is invalid")
    expected_id = _stable_id(
        "oout", H60_SCHEMA, H60_MEASUREMENT_VERSION, episode["episode_id"], 60
    )
    if row.get("outcome_id") != expected_id:
        raise EpisodeSourceContractError(
            "H+60 outcome_id is not stable for its episode and horizon"
        )
    if row.get("episode_id") != episode["episode_id"]:
        raise EpisodeSourceContractError("H+60 outcome references a different episode")
    anchor = _canonical_utc(row.get("horizon_anchor"), "horizon_anchor")
    available = _canonical_utc(episode["available_at"], "episode.available_at")
    if anchor != available:
        raise EpisodeSourceContractError(
            "H+60 horizon_anchor must equal episode.available_at"
        )
    target = _canonical_utc(row.get("target_time"), "target_time")
    computed = _canonical_utc(row.get("computed_at"), "computed_at")
    matured = _canonical_utc(row.get("matured_at"), "matured_at")
    if target - anchor != timedelta(minutes=60):
        raise EpisodeSourceContractError("H+60 target_time must be exactly anchor plus 60m")
    if matured < target or computed < matured:
        raise EpisodeSourceContractError(
            "H+60 maturity must follow target and precede computation"
        )
    if row.get("label_authority") != "research_only":
        raise EpisodeSourceContractError("source outcome must remain research_only")
    if row.get("measurement", {}).get("training_eligible") is not False:
        raise EpisodeSourceContractError("source outcome must remain training-ineligible")

    session = _canonical_date(episode["session_date"], "episode.session_date")
    open_et, close_et = session_window_et(session)
    open_utc = open_et.astimezone(timezone.utc)
    close_utc = close_et.astimezone(timezone.utc)
    status = row.get("status")
    if status == "complete":
        if available >= close_utc or target >= close_utc:
            raise EpisodeSourceContractError(
                "complete H+60 outcome crosses the source session close"
            )
        underlying = row.get("underlying", {})
        entry = _canonical_utc(underlying.get("entry_time"), "underlying.entry_time")
        exit_time = _canonical_utc(underlying.get("exit_time"), "underlying.exit_time")
        if not (open_utc <= entry < exit_time < close_utc) or entry < available:
            raise EpisodeSourceContractError(
                "complete H+60 measurement window is not causal"
            )
        _price_source_matches_ticker(row, episode["ticker"])
    elif status == "incomplete":
        expected_reason = (
            "decision_after_session_close"
            if available >= close_utc
            else "horizon_crosses_session_close"
            if target >= close_utc
            else None
        )
        if expected_reason is None or row.get("reason") != expected_reason:
            raise EpisodeSourceContractError(
                "terminal H+60 outcome is not reproducible from episode clocks"
            )
    else:
        raise EpisodeSourceContractError("H+60 source outcome is not terminal")


def validate_session_outcome_join(
    row: dict[str, Any], episode: dict[str, Any]
) -> None:
    """Validate session-horizon identity, NYSE target, clocks, and episode join."""
    validate_episode_pit(episode)
    horizon = row.get("horizon")
    if row.get("schema") != SESSION_SCHEMA or horizon not in SESSION_HORIZONS:
        raise EpisodeSourceContractError("session outcome schema or horizon is invalid")
    if row.get("horizon_sessions") != SESSION_HORIZONS[horizon]:
        raise EpisodeSourceContractError("session horizon offset is invalid")
    expected_id = _stable_id(
        "oout",
        SESSION_SCHEMA,
        SESSION_MEASUREMENT_VERSION,
        episode["episode_id"],
        horizon,
    )
    if row.get("outcome_id") != expected_id:
        raise EpisodeSourceContractError(
            "session outcome_id is not stable for its episode and horizon"
        )
    if row.get("episode_id") != episode["episode_id"]:
        raise EpisodeSourceContractError("session outcome references a different episode")
    anchor = _canonical_utc(row.get("horizon_anchor"), "horizon_anchor")
    available = _canonical_utc(episode["available_at"], "episode.available_at")
    if anchor != available:
        raise EpisodeSourceContractError(
            "session horizon_anchor must equal episode.available_at"
        )
    source_session = _canonical_date(episode["session_date"], "episode.session_date")
    target_session = nyse_calendar.session_n_forward(
        source_session, SESSION_HORIZONS[horizon]
    )
    if target_session is None or row.get("target_session") != target_session.isoformat():
        raise EpisodeSourceContractError("session outcome target_session is invalid")
    target = _canonical_utc(row.get("target_time"), "target_time")
    expected_target = session_window_et(target_session)[1].astimezone(timezone.utc)
    if target != expected_target:
        raise EpisodeSourceContractError("session target_time is not the declared NYSE close")
    computed = _canonical_utc(row.get("computed_at"), "computed_at")
    matured = _canonical_utc(row.get("matured_at"), "matured_at")
    if matured < max(target, anchor) or computed < matured:
        raise EpisodeSourceContractError(
            "session outcome maturity is not causally ordered"
        )
    if row.get("label_authority") != "research_only":
        raise EpisodeSourceContractError("source outcome must remain research_only")
    if row.get("measurement", {}).get("training_eligible") is not False:
        raise EpisodeSourceContractError("source outcome must remain training-ineligible")
    status = row.get("status")
    if status == "complete":
        _price_source_matches_ticker(row, episode["ticker"])
    elif status == "incomplete":
        if horizon != "eod" or available < target or row.get("reason") != "decision_after_target_close":
            raise EpisodeSourceContractError(
                "terminal session outcome is not reproducible from episode clocks"
            )
    else:
        raise EpisodeSourceContractError("session source outcome is not terminal")


__all__ = [
    "EpisodeSourceContractError",
    "validate_episode_pit",
    "validate_h60_outcome_join",
    "validate_session_outcome_join",
]
