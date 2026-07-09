"""scripts/build_prophet_marks.py — Prophet live-premium marks publisher (Item E).

Reads active prophet plans from site/prophet/index.json (repo checkout, fallback to R2),
extracts plans with a defined option_contract, derives the OCC symbol, pulls a current
quote per contract from ThetaData v3 (PER-CONTRACT — v3 rejects wildcard-exp current-day,
see #1774), assembles the prophet.live_marks/v1 payload, and publishes to R2 key
live_flow/prophet_marks.json.

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
import json
import logging
import os
import sys
import urllib.request
from datetime import datetime, time as dtime, timezone, date
from pathlib import Path
from typing import Any

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.nyse_calendar import is_session, ET

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "prophet.live_marks/v1"
R2_KEY = "live_flow/prophet_marks.json"
R2_FALLBACK_URL = os.environ.get(
    "PROPHET_INDEX_URL",
    "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json",
)

# Regular trading hours: 09:30–16:00 ET (inclusive on open, exclusive on close)
_RTH_OPEN  = dtime(9, 30, 0)
_RTH_CLOSE = dtime(16, 0, 0)

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
    """Fallback: fetch index.json from R2 public URL."""
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


def _load_index() -> dict | None:
    """Load the prophet index, local first then R2 fallback."""
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


# ---------------------------------------------------------------------------
# Extract active plans with option contracts
# ---------------------------------------------------------------------------

def _extract_active_plans(index: dict) -> list[dict]:
    """Return plans that have a defined option_contract and are not invalidated."""
    plans = index.get("plans", [])
    active = []
    for p in plans:
        phase = p.get("phase", "")
        if phase in ("invalidated", "closed", "expired"):
            continue
        oc = p.get("option_contract")
        if not oc:
            continue
        # option_contract must have right, strike, expiry
        if not all(oc.get(k) for k in ("right", "strike", "expiry")):
            log.debug(
                "prophet_marks: plan %s has incomplete option_contract, skipping",
                p.get("id"),
            )
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
    mid  = round((bid + ask) / 2, 4) if bid is not None and ask is not None else None

    # ts_utc: use trade_timestamp if available
    ts_raw = row.get("trade_timestamp") or row.get("date")
    try:
        ts_utc = _to_utc_iso(ts_raw)
    except Exception:  # noqa: BLE001
        ts_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return {
        "bid":    bid,
        "ask":    ask,
        "mid":    mid,
        "last":   last,
        "ts_utc": ts_utc,
    }


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else round(f, 4)  # NaN guard
    except (TypeError, ValueError):
        return None


def _to_utc_iso(ts: Any) -> str:
    """Convert a timestamp value to UTC ISO string."""
    if ts is None:
        raise ValueError("null timestamp")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            # Assume ET
            ts = ts.replace(tzinfo=ET)
        return ts.astimezone(timezone.utc).isoformat(timespec="seconds")
    s = str(ts)
    # Try ISO parse
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:len(fmt) + 5].strip(), fmt.replace("%S", "%S"))
            dt = dt.replace(tzinfo=ET)
            return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            pass
    raise ValueError(f"cannot parse timestamp: {ts!r}")


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


def _publish_r2(payload_json: str) -> bool:
    """Write JSON string to R2 key live_flow/prophet_marks.json."""
    s3 = _r2_client()
    if s3 is None:
        log.warning("prophet_marks: R2 client unavailable — skipping publish")
        return False
    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    try:
        s3.put_object(
            Bucket=bucket,
            Key=R2_KEY,
            Body=payload_json.encode("utf-8"),
            ContentType="application/json",
        )
        log.info("prophet_marks: published → R2 %s/%s", bucket, R2_KEY)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("prophet_marks: R2 publish failed: %s", exc)
        return False


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
        index = _load_index()
    except Exception as exc:  # noqa: BLE001
        log.error("prophet_marks: index load failed: %s", exc)
        return None
    if index is None:
        log.error("prophet_marks: index unavailable — aborting cycle")
        return None

    # 3. Extract plans with option contracts
    active = _extract_active_plans(index)
    log.info("prophet_marks: %d active plans with option contracts", len(active))
    if not active:
        log.info("prophet_marks: no active plans with option contracts — nothing to publish")
        # Publish an empty marks object so the consumer gets a fresh timestamp
        pass  # fall through to publish empty marks

    # 4. Determine session date (today in ET)
    now_et = datetime.now(tz=ET)
    session_date = now_et.date()

    # 5. Fetch quote per contract
    marks: dict[str, dict] = {}
    for plan in active:
        plan_id = plan.get("id", "<unknown>")
        asset   = plan.get("asset", "")
        oc      = plan.get("option_contract", {})
        right   = oc.get("right", "")
        expiry  = oc.get("expiry", "")
        strike  = oc.get("strike")

        if not (asset and right and expiry and strike is not None):
            log.debug("prophet_marks: plan %s missing contract fields, skipping", plan_id)
            continue

        occ = _occ_symbol(asset, right, expiry, float(strike))
        log.debug(
            "prophet_marks: fetching quote for plan=%s occ=%s (asset=%s %s %s %.2f)",
            plan_id, occ, asset, right, expiry, float(strike),
        )

        quote = _fetch_contract_quote(asset, right, expiry, float(strike), session_date)
        if quote is None:
            log.warning(
                "prophet_marks: no quote for plan=%s occ=%s — skipped",
                plan_id, occ,
            )
            continue

        marks[occ] = quote
        log.info(
            "prophet_marks: plan=%s occ=%s bid=%.2f ask=%.2f last=%s",
            plan_id, occ,
            quote["bid"] or 0.0,
            quote["ask"] or 0.0,
            quote["last"],
        )

    # 6. Assemble payload
    asof_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload: dict = {
        "schema":       SCHEMA,
        "asof_utc":     asof_utc,
        "session_date": session_date.isoformat(),
        "marks":        marks,
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
        _publish_r2(payload_json)
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
