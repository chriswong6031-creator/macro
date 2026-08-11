"""scripts/build_prophet_marks.py — Prophet live-premium marks publisher (Item E).

Reads active Prophet plans from the canonical R2 index in publish mode (local checkout
first, then R2, for debug builds), binds each defined option_contract to an exact OCC
identity, and pulls one bounded-age quote per contract from ThetaData v3.  Every open
option plan is accounted for in an immutable prospective evidence observation before
the mutable prophet.live_marks/v1 discovery object advances.  The evidence is mark
change only: it assumes no position or fill and has no execution or product authority.

RTH behaviour
-------------
Outside NYSE RTH (09:30–16:00 ET on trading days) the script exits cleanly with a log
line and does NOT publish.  The launchd plist fires every 5 min 09:25–16:00 ET; the
first cycle before 09:30 open exits immediately.  This avoids publishing stale marks
on a 5-min refresh loop overnight.  The Terminal overlay (Item C) falls back to EOD
when the R2 file is absent or old.

Per-contract error handling
---------------------------
Any single-contract ThetaData failure → skip that contract, log a warning, continue.
Any global error (index load, R2 publish) → log, exit 0 (no crash-loop).

Usage
-----
    python -m scripts.build_prophet_marks [--publish] [--dry-run]

    --publish   Write to R2 (requires R2_* env vars).
    --dry-run   Print the payload to stdout; do not write to R2.
    (no flag)   Build payload + write local JSON to /tmp/prophet_marks_debug.json;
                do not publish to R2.

Environment variables
---------------------
    R2_ENDPOINT          Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID     R2 access key
    R2_SECRET_ACCESS_KEY R2 secret
    R2_BUCKET            R2 bucket name (default: mastermindx)
    PROPHET_INDEX_URL    Override for the R2 fallback URL (optional)

AUTHORITY NOTE
--------------
All output is display-tier.  No signal, score, or escalation originates here.
The word "validated" is forbidden in user-facing text (CI-enforced).
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time as dtime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import logging
import math
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from lib.nyse_calendar import is_session, ET

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "prophet.live_marks/v1"
R2_KEY = "live_flow/prophet_marks.json"
EVIDENCE_SCHEMA = "prophet.option_mark_observation/v1"
EVIDENCE_POINTER_SCHEMA = "prophet.option_mark_pointer/v1"
EVIDENCE_PREFIX = "prophet/option_mark_observations/v1"
MAX_QUOTE_AGE_SECONDS = 30 * 60
R2_FALLBACK_URL = os.environ.get(
    "PROPHET_INDEX_URL",
    "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json",
)

# Regular trading hours: 09:30–16:00 ET (inclusive on open, exclusive on close)
_RTH_OPEN  = dtime(9, 30, 0)
_RTH_CLOSE = dtime(16, 0, 0)

_ROOT_RE = re.compile(r"^[A-Z0-9]{1,6}$")
_OBSERVATION_ID_RE = re.compile(r"^pom_obs_[a-f0-9]{64}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _authority_block() -> dict[str, bool]:
    """The observation chain is evidence only and cannot steer a product."""
    return {
        "rank_authority": False,
        "gate_authority": False,
        "sizing_authority": False,
        "issue_authority": False,
        "trade_authority": False,
        "prophet_authority": False,
        "neural_web_authority": False,
        "training_authority": False,
        "execution_authority": False,
    }


def _canonical_json_bytes(payload: object) -> bytes:
    """Strict bytes used by content identities and immutable R2 objects."""
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")

# ---------------------------------------------------------------------------
# RTH guard
# ---------------------------------------------------------------------------

def _is_rth_now() -> bool:
    """True if current moment is inside NYSE RTH on a trading day."""
    now_et = datetime.now(tz=ET)
    today = now_et.date()
    if not is_session(today):
        return False
    t = now_et.time()
    return _RTH_OPEN <= t < _RTH_CLOSE


# ---------------------------------------------------------------------------
# Prophet index loader
# ---------------------------------------------------------------------------

def _load_index_local() -> dict | None:
    """Load site/prophet/index.json from the repo checkout."""
    idx_path = _REPO / "site" / "prophet" / "index.json"
    if idx_path.exists():
        try:
            with open(idx_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:  # noqa: BLE001
            log.warning("prophet_marks: local index load failed: %s", exc)
    return None


def _load_index_r2() -> dict | None:
    """Fetch the canonical published index.json from R2."""
    try:
        req = urllib.request.Request(
            R2_FALLBACK_URL,
            headers={"User-Agent": "macro-prophet-marks/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_marks: R2 fallback index load failed: %s", exc)
    return None


def _load_index(*, publish: bool = False) -> dict | None:
    """Load the Prophet index appropriate for the requested output mode.

    A deployed publisher may run from an intentionally pinned operations
    checkout, so its local generated index is not canonical.  Publish mode is
    therefore R2-only and fail-closed.  Local-first loading remains useful for
    explicit debug builds in a development checkout.
    """
    if publish:
        return _load_index_r2()

    idx = _load_index_local()
    if idx is not None:
        return idx
    log.info("prophet_marks: local index not found, trying R2 fallback")
    return _load_index_r2()


# ---------------------------------------------------------------------------
# OCC symbol derivation
# ---------------------------------------------------------------------------

def _occ_symbol(asset: str, right: str, expiry: str, strike: float) -> str:
    """Build OCC option symbol.

    Format: {root:6s}{YYMMDD}{C|P}{strike_millis:08d}
    e.g. "BA    260918C00220000"

    Args:
        asset:  underlying ticker (e.g. "BA")
        right:  "C" or "CALL" or "P" or "PUT" (case-insensitive)
        expiry: ISO date string "YYYY-MM-DD"
        strike: dollar float (e.g. 220.0)
    """
    root_padded = asset.upper().ljust(6)
    # YYMMDD from YYYY-MM-DD
    exp_yymmdd = expiry.replace("-", "")[2:]  # "20260918" -> "260918"
    right_char = "C" if right.upper().startswith("C") else "P"
    strike_int = int(round(strike * 1000))
    return f"{root_padded}{exp_yymmdd}{right_char}{strike_int:08d}"


def _plan_contract(
    plan: dict,
    *,
    session_date: date,
) -> tuple[dict[str, object] | None, str | None]:
    """Bind an exact OCC identity without silently rounding a contract."""
    asset = plan.get("asset")
    option = plan.get("option_contract")
    if not isinstance(asset, str) or not _ROOT_RE.fullmatch(asset):
        return None, "INVALID_CONTRACT_IDENTITY"
    if not isinstance(option, dict):
        return None, "INVALID_CONTRACT_IDENTITY"

    right_raw = option.get("right")
    if not isinstance(right_raw, str):
        return None, "INVALID_CONTRACT_IDENTITY"
    right_upper = right_raw.upper()
    if right_upper in {"C", "CALL"}:
        right = "C"
    elif right_upper in {"P", "PUT"}:
        right = "P"
    else:
        return None, "INVALID_CONTRACT_IDENTITY"

    expiry_raw = option.get("expiry")
    if not isinstance(expiry_raw, str):
        return None, "INVALID_CONTRACT_IDENTITY"
    try:
        expiry = date.fromisoformat(expiry_raw)
    except ValueError:
        return None, "INVALID_CONTRACT_IDENTITY"
    if expiry.isoformat() != expiry_raw:
        return None, "INVALID_CONTRACT_IDENTITY"
    if expiry < session_date:
        return None, "CONTRACT_EXPIRED"

    strike_raw = option.get("strike")
    if isinstance(strike_raw, bool):
        return None, "INVALID_CONTRACT_IDENTITY"
    try:
        strike = Decimal(str(strike_raw))
    except (InvalidOperation, ValueError):
        return None, "INVALID_CONTRACT_IDENTITY"
    strike_millis = strike * Decimal(1000)
    if (
        not strike.is_finite()
        or strike <= 0
        or strike_millis != strike_millis.to_integral_value()
        or strike_millis > 99_999_999
    ):
        return None, "INVALID_CONTRACT_IDENTITY"
    strike_millis_int = int(strike_millis)
    occ_symbol = f"{asset:<6}{expiry:%y%m%d}{right}{strike_millis_int:08d}"

    entry_mark = _safe_float(option.get("entry_premium"))
    if entry_mark is not None and entry_mark <= 0:
        entry_mark = None
    if entry_mark is None:
        entry_mark_reason = "ENTRY_MARK_UNAVAILABLE"
    elif option.get("freshness") != "EOD mark":
        entry_mark = None
        entry_mark_reason = "ENTRY_MARK_BASIS_UNVERIFIED"
    else:
        entry_mark_reason = None
    return {
        "root": asset,
        "right": right,
        "expiry": expiry_raw,
        "strike": float(strike),
        "strike_millis": strike_millis_int,
        "occ_symbol": occ_symbol,
        "entry_mark": entry_mark,
        "entry_mark_reason": entry_mark_reason,
    }, None


# ---------------------------------------------------------------------------
# Extract active plans with option contracts
# ---------------------------------------------------------------------------

def _extract_active_plans(index: dict) -> list[dict]:
    """Return every open plan carrying an option contract, including bad rows.

    Malformed contract rows stay in the evidence coverage as abstentions.  Dropping
    them here would make an apparently complete observation silently lossy.
    """
    plans = index.get("plans", [])
    if not isinstance(plans, list):
        raise ValueError("canonical Prophet index plans must be an array")
    active = []
    for p in plans:
        if not isinstance(p, dict):
            raise ValueError("canonical Prophet index contains a non-object plan")
        closed = p.get("closed")
        if closed is not None and not isinstance(closed, bool):
            raise ValueError("canonical Prophet plan closed flag must be boolean")
        phase = p.get("phase", "")
        if closed is True or phase in ("invalidated", "closed", "expired"):
            continue
        if "option_contract" not in p or p.get("option_contract") is None:
            continue
        active.append(p)
    return active


# ---------------------------------------------------------------------------
# ThetaData quote fetch — per-contract
# ---------------------------------------------------------------------------

def _fetch_contract_quote(
    asset: str, right: str, expiry: str, strike: float, session_date: date
) -> dict | None:
    """Pull the latest trade_quote row for ONE specific option contract today.

    Uses collectors.thetadata.trade_quote with start_date=end_date=today.
    Per-contract (specific expiry+strike) is accepted by ThetaData v3 for
    current-day (unlike wildcard-exp bulk which is rejected — see #1774).

    Returns dict with bid, ask, mid, last, ts_utc — or None if no data.
    """
    try:
        from collectors import thetadata as td
    except ImportError as exc:
        log.error("prophet_marks: cannot import collectors.thetadata: %s", exc)
        return None

    try:
        df = td.trade_quote(
            root=asset,
            exp=expiry,
            right=right,
            strike=strike,
            start_date=session_date,
            end_date=session_date,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "prophet_marks: trade_quote(%s, %s, %s, %.3f, %s) failed: %s",
            asset, right, expiry, strike, session_date, exc,
        )
        return None

    if df is None or df.empty:
        log.debug(
            "prophet_marks: no data for %s %s %s %.3f on %s",
            asset, right, expiry, strike, session_date,
        )
        return None

    # Take the latest row by trade_timestamp (df is already time-ordered)
    row = df.iloc[-1]
    bid  = _safe_float(row.get("bid"))
    ask  = _safe_float(row.get("ask"))
    last = _safe_float(row.get("price"))

    # ts_utc: use trade_timestamp if available.
    # trade_timestamp from ThetaData v3 carries fractional seconds, e.g.
    # '2026-07-02T06:30:16.218' (ET-naive) — _to_utc_iso handles this via
    # datetime.fromisoformat (Python 3.11+).
    ts_raw = row.get("trade_timestamp") or row.get("date")
    try:
        ts_utc = _to_utc_iso(ts_raw)
    except Exception as _ts_exc:  # noqa: BLE001
        log.warning(
            "prophet_marks: could not parse trade_timestamp %r — quote refused: %s",
            ts_raw, _ts_exc,
        )
        return None

    return {
        "bid":    bid,
        "ask":    ask,
        "last":   last,
        "ts_utc": ts_utc,
    }


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if not math.isfinite(f) or f < 0:
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _validated_quote(
    raw: object,
    *,
    observed_at: datetime,
    session_date: date,
) -> tuple[dict[str, object] | None, str | None]:
    """Admit a same-session, bounded-age vendor snapshot or abstain."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observation timestamp must be timezone-aware")
    if not isinstance(raw, dict):
        return None, "SOURCE_UNAVAILABLE"
    bid = _safe_float(raw.get("bid"))
    ask = _safe_float(raw.get("ask"))
    last = _safe_float(raw.get("last"))
    if bid is None or ask is None or ask <= 0 or ask < bid:
        return None, "QUOTE_SHAPE_INVALID"

    ts_raw = raw.get("ts_utc")
    if not isinstance(ts_raw, str):
        return None, "QUOTE_SHAPE_INVALID"
    try:
        quote_at = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except ValueError:
        return None, "QUOTE_SHAPE_INVALID"
    if quote_at.tzinfo is None or quote_at.utcoffset() is None:
        return None, "QUOTE_SHAPE_INVALID"
    quote_at = quote_at.astimezone(timezone.utc)
    observed = observed_at.astimezone(timezone.utc)
    if quote_at > observed:
        return None, "QUOTE_AFTER_OBSERVATION"
    if quote_at.astimezone(ET).date() != session_date:
        return None, "QUOTE_WRONG_SESSION"
    exact_age_seconds = (observed - quote_at).total_seconds()
    if exact_age_seconds > MAX_QUOTE_AGE_SECONDS:
        return None, "QUOTE_TOO_OLD"
    age_seconds = int(exact_age_seconds)
    return {
        "label": "vendor_snapshot_bid_ask",
        "bid": bid,
        "ask": ask,
        "mid": round((bid + ask) / 2, 4),
        "last": last,
        "ts_utc": _utc_iso(quote_at),
        "age_seconds": age_seconds,
    }, None


def _to_utc_iso(ts: Any) -> str:
    """Convert a timestamp value to UTC ISO string.

    Handles:
      - datetime objects (tz-aware or tz-naive; naive assumed ET)
      - ISO-like strings including fractional seconds (e.g. '2026-07-02T06:30:16.218')
        and TZ offsets (e.g. '...−04:00'), which is the real ThetaData trade_timestamp
        format (confirmed collectors/thetadata.py line 1045).
      - Bare date strings 'YYYY-MM-DD' (treated as midnight ET).

    Naive strings are treated as ET before converting to UTC.
    """
    if ts is None:
        raise ValueError("null timestamp")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            # Assume ET (ThetaData timestamps are ET-naive)
            ts = ts.replace(tzinfo=ET)
        return ts.astimezone(timezone.utc).isoformat(timespec="seconds")
    s = str(ts).strip()
    if not s:
        raise ValueError("empty timestamp string")
    # Primary path: datetime.fromisoformat handles fractional seconds and TZ offsets
    # on Python 3.11+ (this repo runs 3.12).  Naive strings are treated as ET.
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ET)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        pass
    # Fallback: bare date 'YYYY-MM-DD' (fromisoformat handles this, but be explicit)
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        dt = dt.replace(tzinfo=ET)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        pass
    raise ValueError(f"cannot parse timestamp: {ts!r}")


def _plan_evidence_row(
    plan: dict,
    *,
    contract: dict[str, object] | None,
    contract_reason: str | None,
    quote: dict[str, object] | None,
    quote_reason: str | None,
) -> dict[str, object]:
    plan_id = plan.get("id")
    asset = plan.get("asset")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError("canonical Prophet option plan is missing id")
    if not isinstance(asset, str) or not asset.strip():
        raise ValueError(f"canonical Prophet option plan {plan_id} is missing asset")
    phase = plan.get("phase")
    if not isinstance(phase, str) or not phase:
        phase = "unknown"

    plan_times: dict[str, str | None] = {}
    for field in ("plan_asof", "recorded_at", "entry_date"):
        value = plan.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"canonical Prophet option plan {plan_id} has malformed {field}"
            )
        plan_times[field] = value

    if contract is None:
        current_quote = None
        quote_status = "abstain"
        final_quote_reason = contract_reason or "INVALID_CONTRACT_IDENTITY"
        entry_mark = None
    else:
        current_quote = quote
        quote_status = "available" if quote is not None else "abstain"
        final_quote_reason = None if quote is not None else (quote_reason or "SOURCE_UNAVAILABLE")
        entry_value = contract.get("entry_mark")
        entry_mark = (
            {
                "value": entry_value,
                "basis": "plan_eod_mid",
                "asof": (
                    plan_times["plan_asof"]
                    or plan_times["recorded_at"]
                    or plan_times["entry_date"]
                ),
                "nbbo": False,
                "executable": False,
            }
            if isinstance(entry_value, (int, float)) and entry_value > 0
            else None
        )

    mark_change_pct: float | None = None
    mark_change_reason: str | None
    if current_quote is None:
        mark_change_status = "unavailable"
        mark_change_reason = final_quote_reason
    elif entry_mark is None:
        mark_change_status = "unavailable"
        reason = contract.get("entry_mark_reason") if contract is not None else None
        mark_change_reason = (
            reason if isinstance(reason, str) else "ENTRY_MARK_UNAVAILABLE"
        )
    else:
        current_mid = float(current_quote["mid"])
        entry_value = float(entry_mark["value"])
        mark_change_pct = round((current_mid / entry_value - 1.0) * 100.0, 4)
        mark_change_status = "available"
        mark_change_reason = None

    public_contract = None
    if contract is not None:
        public_contract = {
            key: contract[key]
            for key in (
                "root",
                "right",
                "expiry",
                "strike",
                "strike_millis",
                "occ_symbol",
            )
        }

    lifecycle_state = (
        "watch_only_pre_trigger" if phase == "pre_trigger" else "display_plan_active"
    )
    return {
        "plan": {
            "id": plan_id,
            "asset": asset,
            "phase": phase,
            **plan_times,
        },
        "contract": public_contract,
        "quote_status": quote_status,
        "quote_reason": final_quote_reason,
        "quote": current_quote,
        "plan_entry_mark": entry_mark,
        "mark_change_status": mark_change_status,
        "mark_change_reason": mark_change_reason,
        "mark_change_from_plan_pct": mark_change_pct,
        "mark_change_basis": "plan_eod_mid_to_vendor_snapshot_mid",
        "lifecycle": {
            "state": lifecycle_state,
            "position_assumed": False,
            "trade_pnl_claim": False,
        },
    }


def _evidence_coverage(
    *,
    index: dict,
    rows: list[dict[str, object]],
    source_call_count: int,
) -> dict[str, object]:
    available_quotes = sum(row["quote_status"] == "available" for row in rows)
    available_changes = sum(
        row["mark_change_status"] == "available" for row in rows
    )
    contracts = {
        row["contract"]["occ_symbol"]
        for row in rows
        if isinstance(row.get("contract"), dict)
    }
    plans = index.get("plans")
    return {
        "index_plan_count": len(plans) if isinstance(plans, list) else None,
        "active_option_plan_count": len(rows),
        "unique_contract_count": len(contracts),
        "source_call_count": source_call_count,
        "available_quote_plan_count": available_quotes,
        "abstained_quote_plan_count": len(rows) - available_quotes,
        "available_mark_change_plan_count": available_changes,
        "all_active_option_plans_accounted": True,
    }


def _build_observation(
    *,
    index: dict,
    observed_at_utc: str,
    session_date: str,
    rows: list[dict[str, object]],
    coverage: dict[str, object],
    previous: dict[str, object] | None,
) -> dict[str, object]:
    """Build one content-addressed, backwards-linked evidence observation."""
    index_asof = index.get("asof")
    if not isinstance(index_asof, str):
        raise ValueError("canonical Prophet index asof is missing")
    try:
        parsed_index_asof = date.fromisoformat(index_asof)
    except ValueError as exc:
        raise ValueError("canonical Prophet index asof is malformed") from exc
    if parsed_index_asof.isoformat() != index_asof:
        raise ValueError("canonical Prophet index asof is malformed")
    index_recorded_at = index.get("recorded_at")
    if index_recorded_at is not None and not isinstance(index_recorded_at, str):
        raise ValueError("canonical Prophet index recorded_at is malformed")

    try:
        observed = datetime.fromisoformat(observed_at_utc.replace("Z", "+00:00"))
        session = date.fromisoformat(session_date)
    except ValueError as exc:
        raise ValueError("option mark observation clock is malformed") from exc
    if (
        observed.tzinfo is None
        or observed.utcoffset() is None
        or session.isoformat() != session_date
        or observed.astimezone(ET).date() != session
    ):
        raise ValueError("option mark observation clock is inconsistent")

    payload: dict[str, object] = {
        "schema": EVIDENCE_SCHEMA,
        "observation_id": None,
        "observed_at_utc": observed_at_utc,
        "session_date": session_date,
        "prophet_index": {
            "schema": index.get("schema"),
            "asof": index_asof,
            "recorded_at": index_recorded_at,
            "semantic_sha256": sha256(_canonical_json_bytes(index)).hexdigest(),
            "source_url": R2_FALLBACK_URL,
        },
        "source": {
            "provider": "thetadata_v3",
            "endpoint": "trade_quote",
            "quote_label": "vendor_snapshot_bid_ask",
            "maximum_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
            "nbbo": False,
            "live": False,
            "executable": False,
            "fill": False,
        },
        "previous": previous,
        "coverage": coverage,
        "rows": rows,
        "limitations": {
            "mark_change_only": True,
            "not_trade_pnl": True,
            "no_position_assumed": True,
            "no_size_venue_or_condition_receipt": True,
            "prospective_from_first_observation_only": True,
        },
        "authority": _authority_block(),
    }
    identity = dict(payload)
    identity.pop("observation_id")
    payload["observation_id"] = (
        "pom_obs_" + sha256(_canonical_json_bytes(identity)).hexdigest()
    )
    return payload


def _observation_pointer(observation: dict[str, object]) -> dict[str, object]:
    observation_id = observation.get("observation_id")
    session_date = observation.get("session_date")
    if not isinstance(observation_id, str) or not _OBSERVATION_ID_RE.fullmatch(
        observation_id
    ):
        raise ValueError("option mark observation id is malformed")
    if not isinstance(session_date, str):
        raise ValueError("option mark observation session is malformed")
    try:
        parsed_session = date.fromisoformat(session_date)
    except ValueError as exc:
        raise ValueError("option mark observation session is malformed") from exc
    if parsed_session.isoformat() != session_date:
        raise ValueError("option mark observation session is malformed")

    identity = dict(observation)
    identity.pop("observation_id", None)
    expected_id = "pom_obs_" + sha256(_canonical_json_bytes(identity)).hexdigest()
    if observation_id != expected_id:
        raise ValueError("option mark observation content identity mismatch")
    body = _canonical_json_bytes(observation)
    return {
        "schema": EVIDENCE_POINTER_SCHEMA,
        "observation_id": observation_id,
        "key": f"{EVIDENCE_PREFIX}/{session_date}/{observation_id}.json",
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
    }


# ---------------------------------------------------------------------------
# R2 helpers
# ---------------------------------------------------------------------------

def _r2_client():
    """Build a boto3 S3 client for R2, or None if creds are absent."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config
        kw = dict(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=4,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        try:
            cfg = Config(
                **kw,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
        except TypeError:
            cfg = Config(**kw)
        return boto3.client(
            "s3",
            endpoint_url=ep,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            config=cfg,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_marks: R2 client build failed: %s", exc)
        return None


def _r2_error(exc: Exception) -> tuple[str, int]:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return "", 0
    error = response.get("Error")
    metadata = response.get("ResponseMetadata")
    code = str(error.get("Code") or "") if isinstance(error, dict) else ""
    try:
        status = int(metadata.get("HTTPStatusCode") or 0) if isinstance(metadata, dict) else 0
    except (TypeError, ValueError):
        status = 0
    return code, status


def _r2_not_found(exc: Exception) -> bool:
    code, status = _r2_error(exc)
    return status == 404 or code in {"404", "NoSuchKey", "NotFound"}


def _r2_precondition(exc: Exception) -> bool:
    code, status = _r2_error(exc)
    return status in {409, 412} or code in {
        "409",
        "412",
        "ConditionalRequestConflict",
        "PreconditionFailed",
    }


def _read_r2_object(
    client: Any,
    bucket: str,
    key: str,
) -> tuple[bytes, str | None]:
    response = client.get_object(Bucket=bucket, Key=key)
    stream = response.get("Body")
    if stream is None or not hasattr(stream, "read"):
        raise ValueError(f"R2 {key} returned no readable body")
    body = stream.read()
    if not isinstance(body, bytes):
        raise ValueError(f"R2 {key} returned non-bytes")
    size = response.get("ContentLength")
    if isinstance(size, int) and size != len(body):
        raise ValueError(f"R2 {key} content length mismatch")
    etag = response.get("ETag")
    if etag is not None and (not isinstance(etag, str) or not etag.strip()):
        raise ValueError(f"R2 {key} returned malformed ETag")
    return body, etag


def _read_r2_bytes(client: Any, bucket: str, key: str) -> bytes:
    return _read_r2_object(client, bucket, key)[0]


def _validate_pointer(pointer: object) -> dict[str, object]:
    required = {"schema", "observation_id", "key", "sha256", "bytes"}
    if not isinstance(pointer, dict) or set(pointer) != required:
        raise ValueError("option mark evidence pointer shape is malformed")
    observation_id = pointer.get("observation_id")
    key = pointer.get("key")
    digest = pointer.get("sha256")
    size = pointer.get("bytes")
    if pointer.get("schema") != EVIDENCE_POINTER_SCHEMA:
        raise ValueError("option mark evidence pointer schema mismatch")
    if not isinstance(observation_id, str) or not _OBSERVATION_ID_RE.fullmatch(
        observation_id
    ):
        raise ValueError("option mark evidence pointer id is malformed")
    if (
        not isinstance(key, str)
        or not key.startswith(f"{EVIDENCE_PREFIX}/")
        or not key.endswith(f"/{observation_id}.json")
        or ".." in key
    ):
        raise ValueError("option mark evidence pointer key is malformed")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ValueError("option mark evidence pointer digest is malformed")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("option mark evidence pointer size is malformed")
    return dict(pointer)


def _load_previous_pointer(
    client: Any,
    bucket: str,
) -> tuple[dict[str, object] | None, str | None]:
    """Return the verified chain head and current-object ETag for a CAS update."""
    try:
        current_body, current_etag = _read_r2_object(client, bucket, R2_KEY)
    except Exception as exc:  # noqa: BLE001
        if _r2_not_found(exc):
            return None, None
        raise
    if current_etag is None:
        raise ValueError("current Prophet marks object has no ETag")
    try:
        current = json.loads(current_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("current Prophet marks object is not valid JSON") from exc
    if not isinstance(current, dict) or current.get("schema") != SCHEMA:
        raise ValueError("current Prophet marks schema mismatch")
    if "evidence" not in current:
        return None, current_etag
    pointer = _validate_pointer(current.get("evidence"))
    previous_body = _read_r2_bytes(client, bucket, str(pointer["key"]))
    if len(previous_body) != pointer["bytes"]:
        raise ValueError("previous option mark evidence byte count mismatch")
    if sha256(previous_body).hexdigest() != pointer["sha256"]:
        raise ValueError("previous option mark evidence digest mismatch")
    try:
        previous = json.loads(previous_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("previous option mark evidence is not valid JSON") from exc
    if not isinstance(previous, dict) or previous.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("previous option mark evidence identity mismatch")
    if _canonical_json_bytes(previous) != previous_body:
        raise ValueError("previous option mark evidence identity mismatch")
    if _observation_pointer(previous) != pointer:
        raise ValueError("previous option mark evidence pointer mismatch")
    return pointer, current_etag


def _publish_immutable_observation(
    client: Any,
    bucket: str,
    pointer: dict[str, object],
    body: bytes,
) -> None:
    try:
        client.put_object(
            Bucket=bucket,
            Key=pointer["key"],
            Body=body,
            ContentType="application/json",
            CacheControl="public, max-age=31536000, immutable",
            Metadata={
                "sha256": str(pointer["sha256"]),
                "schema": EVIDENCE_SCHEMA,
                "observation-id": str(pointer["observation_id"]),
                "immutable": "true",
            },
            IfNoneMatch="*",
        )
    except Exception as exc:  # noqa: BLE001
        if not _r2_precondition(exc):
            raise
        existing = _read_r2_bytes(client, bucket, str(pointer["key"]))
        if existing != body:
            raise ValueError("immutable option mark evidence collision") from exc
    verified = _read_r2_bytes(client, bucket, str(pointer["key"]))
    if verified != body:
        raise ValueError("immutable option mark evidence readback mismatch")


def _publish_r2(
    payload: dict,
    *,
    index: dict,
    evidence_rows: list[dict[str, object]],
) -> dict | None:
    """Publish immutable evidence first, then the current discoverability pointer."""
    client = _r2_client()
    if client is None:
        log.warning("prophet_marks: R2 client unavailable — skipping publish")
        return None
    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    try:
        previous, current_etag = _load_previous_pointer(client, bucket)
        observation = _build_observation(
            index=index,
            observed_at_utc=str(payload["asof_utc"]),
            session_date=str(payload["session_date"]),
            rows=evidence_rows,
            coverage=dict(payload["coverage"]),
            previous=previous,
        )
        pointer = _observation_pointer(observation)
        observation_body = _canonical_json_bytes(observation)
        _publish_immutable_observation(client, bucket, pointer, observation_body)

        published = dict(payload)
        published["evidence"] = pointer
        current_body = _canonical_json_bytes(published)
        current_put = {
            "Bucket": bucket,
            "Key": R2_KEY,
            "Body": current_body,
            "ContentType": "application/json",
            "CacheControl": "public, max-age=15, must-revalidate",
            "Metadata": {
                "sha256": sha256(current_body).hexdigest(),
                "schema": SCHEMA,
                "evidence-observation-id": str(pointer["observation_id"]),
            },
        }
        if current_etag is None:
            current_put["IfNoneMatch"] = "*"
        else:
            current_put["IfMatch"] = current_etag
        client.put_object(
            **current_put,
        )
        if _read_r2_bytes(client, bucket, R2_KEY) != current_body:
            raise ValueError("current Prophet marks readback mismatch")
        log.info(
            "prophet_marks: published evidence %s then current → R2 %s/%s",
            pointer["observation_id"],
            bucket,
            R2_KEY,
        )
        return published
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_marks: R2 evidence publication failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_marks(publish: bool = False, dry_run: bool = False) -> dict | None:
    """Build and (optionally) publish the prophet.live_marks/v1 payload.

    Returns the payload dict on success, None on global failure.
    Never raises — all errors are logged.
    """
    # 1. RTH guard
    if not _is_rth_now():
        now_et = datetime.now(tz=ET)
        log.info(
            "prophet_marks: outside RTH (%s ET, is_session=%s) — skipping cycle",
            now_et.strftime("%H:%M:%S"),
            is_session(now_et.date()),
        )
        return None

    # 2. Load index
    try:
        index = _load_index(publish=publish)
    except Exception as exc:  # noqa: BLE001
        log.error("prophet_marks: index load failed: %s", exc)
        return None
    if index is None:
        log.error("prophet_marks: index unavailable — aborting cycle")
        return None
    if index.get("schema") != "prophet.index/v1":
        log.error("prophet_marks: canonical index schema mismatch")
        return None

    # 3. Extract plans with option contracts
    try:
        active = _extract_active_plans(index)
    except ValueError as exc:
        log.error("prophet_marks: canonical index plan shape failed: %s", exc)
        return None
    log.info("prophet_marks: %d active plans with option contracts", len(active))
    if not active:
        log.info("prophet_marks: no active plans with option contracts — nothing to publish")
        # Publish an empty marks object so the consumer gets a fresh timestamp
        pass  # fall through to publish empty marks

    # 4. Determine session date (today in ET)
    cycle_started_at = datetime.now(timezone.utc).replace(microsecond=0)
    session_date = cycle_started_at.astimezone(ET).date()

    # 5. Fetch once per exact contract, while accounting for every active option plan.
    marks: dict[str, dict] = {}
    evidence_rows: list[dict[str, object]] = []
    plan_contracts: list[
        tuple[dict, dict[str, object] | None, str | None]
    ] = []
    raw_quote_cache: dict[str, object] = {}
    quote_cache: dict[
        str, tuple[dict[str, object] | None, str | None]
    ] = {}
    try:
        for plan in active:
            plan_id = plan.get("id")
            contract, contract_reason = _plan_contract(
                plan, session_date=session_date
            )
            if contract is not None:
                occ = str(contract["occ_symbol"])
                if occ not in raw_quote_cache:
                    log.debug(
                        "prophet_marks: fetching plan=%s occ=%s",
                        plan_id,
                        occ,
                    )
                    raw_quote_cache[occ] = _fetch_contract_quote(
                        str(contract["root"]),
                        str(contract["right"]),
                        str(contract["expiry"]),
                        float(contract["strike"]),
                        session_date,
                    )
            plan_contracts.append((plan, contract, contract_reason))

        # Availability is observed only after every vendor call returned. Capturing
        # this before polling would make a legitimately newer returned row look like
        # a future quote and would understate source age on slow calls.
        observed_at = datetime.now(timezone.utc).replace(microsecond=0)
        quote_cache = {
            occ: _validated_quote(
                raw,
                observed_at=observed_at,
                session_date=session_date,
            )
            for occ, raw in raw_quote_cache.items()
        }

        for plan, contract, contract_reason in plan_contracts:
            plan_id = plan.get("id")
            quote = None
            quote_reason = contract_reason
            if contract is not None:
                occ = str(contract["occ_symbol"])
                quote, quote_reason = quote_cache[occ]
                if quote is not None:
                    marks[occ] = {
                        key: quote[key]
                        for key in ("bid", "ask", "mid", "last", "ts_utc")
                    }
                    log.info(
                        "prophet_marks: plan=%s occ=%s bid=%.2f ask=%.2f age=%ss",
                        plan_id,
                        occ,
                        float(quote["bid"]),
                        float(quote["ask"]),
                        quote["age_seconds"],
                    )
                else:
                    log.warning(
                        "prophet_marks: plan=%s occ=%s abstained reason=%s",
                        plan_id,
                        occ,
                        quote_reason,
                    )
            evidence_rows.append(
                _plan_evidence_row(
                    plan,
                    contract=contract,
                    contract_reason=contract_reason,
                    quote=quote,
                    quote_reason=quote_reason,
                )
            )
    except (TypeError, ValueError) as exc:
        log.error("prophet_marks: evidence construction failed: %s", exc)
        return None

    # 6. Assemble payload
    asof_utc = _utc_iso(observed_at)
    coverage = _evidence_coverage(
        index=index,
        rows=evidence_rows,
        source_call_count=len(raw_quote_cache),
    )
    payload: dict = {
        "schema":       SCHEMA,
        "asof_utc":     asof_utc,
        "session_date": session_date.isoformat(),
        "marks":        marks,
        "coverage":     coverage,
    }

    payload_json = json.dumps(payload, allow_nan=False, default=str, indent=2)
    log.info(
        "prophet_marks: payload ready — %d marks, asof_utc=%s",
        len(marks), asof_utc,
    )

    # 7. Output
    if dry_run:
        print(payload_json)
    elif publish:
        published = _publish_r2(
            payload,
            index=index,
            evidence_rows=evidence_rows,
        )
        if published is None:
            log.error("prophet_marks: evidence/current R2 publication failed")
            return None
        payload = published
    else:
        # Default: write to /tmp for smoke inspection
        tmp_path = Path("/tmp/prophet_marks_debug.json")
        tmp_path.write_text(payload_json, encoding="utf-8")
        log.info("prophet_marks: debug output written to %s", tmp_path)

    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prophet live-marks publisher (prophet.live_marks/v1).",
    )
    p.add_argument(
        "--publish",
        action="store_true",
        help="Publish to R2 key live_flow/prophet_marks.json.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload JSON to stdout; do not write anywhere.",
    )
    return p.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    args = _parse_args()
    try:
        result = build_marks(publish=args.publish, dry_run=args.dry_run)
        if result is None and _is_rth_now():
            # Only non-zero if we TRIED and failed (RTH but no payload)
            sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        log.error("prophet_marks: unhandled error — exit 0 (no crash-loop): %s", exc)
        sys.exit(0)


if __name__ == "__main__":
    main()
