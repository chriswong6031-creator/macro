"""scripts/build_prophet.py — Prophet Origination Bridge + artifact publisher (W1).

Reads us_standouts.json, originates prophet.trade_plan/v1 envelopes,
runs the management confidence engine for every active plan, and writes:

    site/prophet/index.json          — all active plans + states inline
    site/prophet/plans/<ID>.json     — per-plan artifact
    site/prophet/states/<ID>.json    — per-state artifact
    data/prophet/ledger.jsonl        — forward outcome ledger (INITIALIZED here;
                                       nightly is the SOLE future advancer)

With --publish, also uploads site/prophet/index.json to R2 key
"prophet/index.json" (mirrors build_options_matrix.py upload pattern).

Usage
-----
    python -m scripts.build_prophet [--date YYYY-MM-DD] [--publish]

Environment variables
---------------------
    THETADATA_STORE        Path to ThetaData EOD store root (optional)
    R2_ENDPOINT            Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID       R2 access key
    R2_SECRET_ACCESS_KEY   R2 secret
    R2_BUCKET              R2 bucket name

SCHEDULING NOTE
---------------
NO daily.yml wiring in this PR.  Scheduling follows after operator reviews
the first output.  This script is safe to run manually at any time; it is
idempotent (duplicate plans are suppressed by ID).

AUTHORITY NOTE
--------------
All output artifacts carry authority_tier='display'.  No signal, score, or
escalation originates from an LLM in this pipeline.  The word "validated"
is forbidden in site artifacts (enforced by check_validated_claims.py).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.prophet_bridge import originate_plans
from engine.prophet_management import compute_management_state
from engine.options_structure import validate_trade_plan

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STANDOUTS_PATH = _REPO / "site" / "factordata" / "us_standouts.json"
SITE_PROPHET   = _REPO / "site" / "prophet"
PLANS_DIR      = SITE_PROPHET / "plans"
STATES_DIR     = SITE_PROPHET / "states"
INDEX_PATH     = SITE_PROPHET / "index.json"
LEDGER_DIR     = _REPO / "data" / "prophet"
LEDGER_PATH    = LEDGER_DIR / "ledger.jsonl"

R2_INDEX_KEY   = "prophet/index.json"


# ---------------------------------------------------------------------------
# R2 helpers (mirrors build_options_matrix.py exactly)
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
            max_pool_connections=16,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        try:
            cfg = Config(**kw,
                         request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client(
            "s3",
            endpoint_url=ep,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            config=cfg,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("build_prophet: R2 client build failed: %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    """Upload local file to R2. Returns True on success."""
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("build_prophet: R2 upload ok → %s", r2_key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("build_prophet: R2 upload failed for %s: %s", r2_key, e)
        return False


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, allow_nan=False, default=str, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("build_prophet: failed to read %s: %s", path, e)
    return None


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

LEDGER_SCHEMA_COMMENT = (
    "# prophet ledger row schema — see research/PROPHET_LEDGER_SCHEMA.md\n"
    "# Fields: schema, id, asset, direction, signal_date, close_date,\n"
    "#         outcome (T1_HIT|T2_HIT|INVALIDATED|EXPIRED|CLOSED_EARLY),\n"
    "#         stock_result_pct, option_result_pct (null when no rec),\n"
    "#         days_held, plan_adherence, asof\n"
    "# Nightly is the SOLE advancer of this ledger.\n"
)


def _initialize_ledger() -> None:
    """Create ledger.jsonl + header comment if it doesn't exist."""
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists():
        LEDGER_PATH.write_text(LEDGER_SCHEMA_COMMENT, encoding="utf-8")
        log.info("build_prophet: initialized empty ledger at %s", LEDGER_PATH)
    else:
        log.info("build_prophet: ledger exists at %s; not overwriting", LEDGER_PATH)


# ---------------------------------------------------------------------------
# Existing plan loader
# ---------------------------------------------------------------------------

def _load_existing_plans() -> dict[str, dict]:
    """Load all existing plan JSON files. Returns {id: plan_dict}."""
    plans: dict[str, dict] = {}
    if not PLANS_DIR.exists():
        return plans
    for p in PLANS_DIR.glob("*.json"):
        data = _read_json(p)
        if data and data.get("schema") == "prophet.trade_plan/v1":
            plans[data["id"]] = data
    return plans


def _load_existing_state(plan_id: str) -> dict | None:
    """Load existing management state for a plan (for prev_state EMA chain)."""
    state_path = STATES_DIR / f"{plan_id}.json"
    return _read_json(state_path)


# ---------------------------------------------------------------------------
# Price history loader (for management engine)
# ---------------------------------------------------------------------------

def _load_price_history_for_management(ticker: str):
    """Load OHLCV price history for the management engine."""
    import pandas as pd  # noqa: PLC0415
    for sub in ["data/baskets/ohlcv", "data/stocks"]:
        p = _REPO / sub / f"{ticker}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                if not isinstance(df.index, pd.DatetimeIndex):
                    for c in ["date", "Date"]:
                        if c in df.columns:
                            df = df.set_index(c)
                            break
                df.index = pd.to_datetime(df.index)
                return df
            except Exception as e:
                log.warning("build_prophet: price history load failed %s: %s", ticker, e)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Prophet origination bridge + artifact publisher (W1, display-only)."
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="ISO-8601 asof date (sole time anchor; no wall-clock reads beyond this).",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also upload site/prophet/index.json to R2.",
    )
    args = parser.parse_args()

    asof: str = args.date
    log.info("build_prophet: starting — asof=%s publish=%s", asof, args.publish)

    # ── 0. Initialize ledger ──────────────────────────────────────────────────
    _initialize_ledger()

    # ── 1. Load existing plans (duplicate suppression) ────────────────────────
    existing_plans = _load_existing_plans()
    existing_ids: set[str] = set(existing_plans.keys())
    log.info("build_prophet: %d existing plans loaded", len(existing_ids))

    # ── 2. Originate new plans ────────────────────────────────────────────────
    thetadata_store = os.environ.get("THETADATA_STORE")
    new_plans = originate_plans(
        standouts_path=STANDOUTS_PATH,
        asof=asof,
        existing_ids=existing_ids,
        thetadata_store=thetadata_store,
    )
    log.info("build_prophet: %d new plans originated", len(new_plans))

    # Merge all plans
    all_plans = {**existing_plans}
    for p in new_plans:
        all_plans[p["id"]] = p

    # ── 3. Run management engine for every active plan ────────────────────────
    active_entries: list[dict] = []
    import pandas as pd  # noqa: PLC0415

    for plan_id, plan in all_plans.items():
        ticker = plan.get("asset", "")
        ph = _load_price_history_for_management(ticker)

        if ph is None:
            log.warning(
                "build_prophet: no price history for %s; skipping management", ticker
            )
            # Write plan only
            _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            continue

        # PIT: filter price_history to <= asof
        asof_ts = pd.Timestamp(asof)
        ph_pit = ph[ph.index <= asof_ts]

        if ph_pit.empty:
            log.warning(
                "build_prophet: empty price history for %s up to %s", ticker, asof
            )
            _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            continue

        prev_state = _load_existing_state(plan_id)

        try:
            state = compute_management_state(
                plan=plan,
                price_history=ph_pit,
                asof=asof,
                prev_state=prev_state,
            )
        except Exception as e:
            log.warning(
                "build_prophet: management engine failed for %s: %s", plan_id, e
            )
            _write_json(PLANS_DIR / f"{plan_id}.json", plan)
            continue

        # Write artifacts
        _write_json(PLANS_DIR / f"{plan_id}.json", plan)
        _write_json(STATES_DIR / f"{plan_id}.json", state)

        active_entries.append({
            "id": plan_id,
            "asset": plan.get("asset"),
            "direction": plan.get("direction"),
            "entry": plan.get("entry"),
            "invalidation": plan.get("invalidation"),
            "targets": plan.get("targets", []),
            "trigger": plan.get("trigger"),
            "option_contract": plan.get("option_contract"),
            "_r_unit": plan.get("_r_unit"),
            "_conviction_score": plan.get("_conviction_score"),
            "_signal_date": plan.get("_signal_date"),
            "phase": state.get("phase"),
            "management_confidence": state.get("management_confidence"),
            "recommended_action": state.get("recommended_action"),
        })

    # ── 4. Write index.json ───────────────────────────────────────────────────
    index: dict[str, Any] = {
        "schema": "prophet.index/v1",
        "asof": asof,
        "cadence": "nightly-EOD",
        "authority_tier": "display",
        "gate_go": _read_standouts_gate_go(),
        "plan_count": len(all_plans),
        "active_count": len(active_entries),
        "plans": active_entries,
        "note": (
            "DISPLAY-ONLY. All plans are display-tier artifacts. No signal has"
            " passed a forward ledger gate. The word 'validated' is forbidden in"
            " user-facing text. Nightly is the sole advancer of the forward ledger."
        ),
    }
    _write_json(INDEX_PATH, index)
    log.info("build_prophet: wrote index.json (%d active plans)", len(active_entries))

    # ── 5. R2 publish ─────────────────────────────────────────────────────────
    if args.publish:
        s3 = _r2_client()
        if s3:
            bucket = os.environ.get("R2_BUCKET", "mastermindx")
            _upload_r2(s3, bucket, INDEX_PATH, R2_INDEX_KEY)
        else:
            log.warning("build_prophet: --publish set but R2 creds unavailable; skipping")

    # ── 6. Report ─────────────────────────────────────────────────────────────
    log.info("build_prophet: done — %d plans total, %d active", len(all_plans), len(active_entries))
    for e in active_entries:
        log.info(
            "  %s %s | entry=%.2f | inval=%s | T1=%s T2=%s | phase=%s | conf=%s | opt=%s",
            e["asset"],
            e["direction"],
            e.get("entry") or 0,
            e.get("invalidation"),
            e.get("targets", [None])[0] if e.get("targets") else None,
            e.get("targets", [None, None])[1] if len(e.get("targets", [])) > 1 else None,
            e.get("phase"),
            e.get("management_confidence"),
            "Y" if e.get("option_contract") else "N",
        )

    return active_entries


def _read_standouts_gate_go() -> bool:
    """Read gate_go from standouts for the index."""
    try:
        with STANDOUTS_PATH.open(encoding="utf-8") as f:
            return bool(json.load(f).get("gate_go", False))
    except Exception:
        return False


if __name__ == "__main__":
    main()
