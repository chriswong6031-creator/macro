"""R2 mirror for flow index, leaders, radar, and Options Prophet artifacts.

Uploads site/flow/index.json to R2 key live_flow/flow_idx.json so the live
options-flow heatmap layer can read a fresh flow manifest without waiting for a
full GitHub Pages deploy cycle.

With --leaders flag, uploads site/flowleaders/leaders.json to R2 key
flowleaders/leaders.json (Flow Leaders Desk W2).

With --radar flag, uploads site/leaderradar/radar.json to R2 key
leaderradar/radar.json (Leader Radar LR W2a).

With --options-prophet flag, uploads site/options_prophet/index.json to R2 key
options_prophet/index.json (display-only Options Prophet shadow projection).

Called as a non-fatal step in daily.yml (engine job) AFTER the parallel band
finishes (cl_gex → build_options_flow has written site/flow/index.json).

Graceful degradation by default:
  * If R2 creds are absent → skip silently (exit 0).
  * If source file is absent → warn + exit 0.
  * Any upload failure → warn + exit 0 (never fails the nightly).

`--strict` makes those conditions non-zero, validates the Options Prophet
contract before upload, and verifies the resulting R2 object with HEAD. The
nightly wraps that exit code as an explicit non-fatal workflow warning.

Usage
-----
    python -m scripts.mirror_flow_idx             # uploads flow_idx.json
    python -m scripts.mirror_flow_idx --leaders   # uploads leaders.json
    python -m scripts.mirror_flow_idx --radar     # uploads radar.json
    python -m scripts.mirror_flow_idx --options-prophet
    python -m scripts.mirror_flow_idx --options-prophet --strict

No other arguments; all config comes from environment variables:
    R2_ENDPOINT           Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID      R2 access key
    R2_SECRET_ACCESS_KEY  R2 secret
    R2_BUCKET             R2 bucket name (default: mastermindx)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parent.parent
FLOW_INDEX_PATH = _REPO / "site" / "flow" / "index.json"
R2_KEY = "live_flow/flow_idx.json"

LEADERS_PATH = _REPO / "site" / "flowleaders" / "leaders.json"
LEADERS_R2_KEY = "flowleaders/leaders.json"

RADAR_PATH = _REPO / "site" / "leaderradar" / "radar.json"
RADAR_R2_KEY = "leaderradar/radar.json"

OPTIONS_PROPHET_PATH = _REPO / "site" / "options_prophet" / "index.json"
OPTIONS_PROPHET_R2_KEY = "options_prophet/index.json"


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

        kw = {
            "region_name": "auto",
            "signature_version": "s3v4",
            "max_pool_connections": 8,
            "retries": {"max_attempts": 3, "mode": "standard"},
        }
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
    except Exception as e:  # noqa: BLE001
        log.warning("mirror_flow_idx: R2 client build failed: %s", e)
        return None


def _upload(s3, local_path: Path, r2_key: str, bucket: str) -> bool:
    """Upload one artifact and return whether publication actually succeeded."""
    if not local_path.exists():
        log.warning(
            "mirror_flow_idx: %s absent — skipping R2 upload for %s",
            local_path,
            r2_key,
        )
        return False
    try:
        digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={
                "ContentType": "application/json",
                "Metadata": {"sha256": digest},
            },
        )
        log.info("mirror_flow_idx: uploaded %s → R2:%s", local_path.name, r2_key)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("mirror_flow_idx: upload failed for %s: %s", r2_key, exc)
        return False


def _valid_options_prophet_contract(path: Path) -> bool:
    """Reject permissive-Python JSON and any foreign public contract."""

    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON constant: {token}")

    def exact_utc(value):
        if not isinstance(value, str) or not value.endswith("Z"):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=reject_constant
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log.warning("mirror_flow_idx: invalid Options Prophet JSON: %s", exc)
        return False
    opportunities = payload.get("opportunities") if isinstance(payload, dict) else None
    watchlist = payload.get("watchlist") if isinstance(payload, dict) else None
    readiness = payload.get("readiness") if isinstance(payload, dict) else None
    direction = payload.get("direction") if isinstance(payload, dict) else None
    trajectory = payload.get("trajectory") if isinstance(payload, dict) else None
    ledgers = payload.get("forward_ledgers") if isinstance(payload, dict) else None
    feedback = payload.get("macro_feedback") if isinstance(payload, dict) else None
    selection = payload.get("selection_policy") if isinstance(payload, dict) else None
    portfolio = payload.get("portfolio_boundary") if isinstance(payload, dict) else None
    pit = payload.get("pit_provenance") if isinstance(payload, dict) else None
    accrual = payload.get("accrual") if isinstance(payload, dict) else None
    contexts = payload.get("context_inputs") if isinstance(payload, dict) else None
    provenance = payload.get("provenance") if isinstance(payload, dict) else None
    konseki = (
        contexts.get("konseki_market_memory")
        if isinstance(contexts, dict)
        else None
    )
    allowed_engines = {"plab_flow_leader", "plab_flow_washout"}
    expected_lane = {
        "plab_flow_leader": "flow_leader",
        "plab_flow_washout": "flow_washout",
    }
    root_available = (
        exact_utc(payload.get("available_at")) if isinstance(payload, dict) else None
    )
    root_decision_raw = payload.get("decision_at") if isinstance(payload, dict) else None
    root_decision = (
        exact_utc(root_decision_raw) if root_decision_raw is not None else None
    )

    def nonnegative_count(value) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, int)
            and value >= 0
        )

    def valid_fire_clock(row: dict) -> bool:
        if "decision_at" not in row:
            return False
        available = exact_utc(row.get("available_at"))
        decision_raw = row.get("decision_at")
        decision = exact_utc(decision_raw) if decision_raw is not None else None
        return (
            available is not None
            and root_available is not None
            and (decision_raw is None or (decision is not None and available >= decision))
            and available <= root_available
        )

    def valid_watch_clock(row: dict) -> bool:
        if "decision_at" not in row:
            return False
        available = exact_utc(row.get("available_at"))
        decision_raw = row.get("decision_at")
        decision = exact_utc(decision_raw) if decision_raw is not None else None
        return (
            available is not None
            and root_available is not None
            and (decision_raw is None or (decision is not None and available >= decision))
            and available <= root_available
        )

    def valid_event_accrual(events: object) -> bool:
        if not isinstance(events, dict) or not isinstance(events.get("books"), list):
            return False
        coverage = events.get("timestamp_coverage")
        if not isinstance(coverage, dict) or not isinstance(opportunities, list):
            return False
        exact_decisions = sum(row.get("decision_at") is not None for row in opportunities)
        exact_availability = sum(row.get("available_at") is not None for row in opportunities)
        if (
            events.get("unit") != "immutable_options_originated_fire"
            or events.get("authority") != "display_only"
            or events.get("published_now") != len(opportunities)
            or coverage.get("n_published") != len(opportunities)
            or coverage.get("n_exact_decision_at") != exact_decisions
            or coverage.get("n_exact_available_at") != exact_availability
        ):
            return False
        engine_ids = [
            book.get("engine_id") for book in events["books"] if isinstance(book, dict)
        ]
        return len(engine_ids) == len(events["books"]) == len(set(engine_ids)) and all(
            isinstance(book, dict)
            and book.get("engine_id") in allowed_engines
            and nonnegative_count(book.get("n_fires"))
            and nonnegative_count(book.get("n_open"))
            and nonnegative_count(book.get("n_distinct_fire_dates"))
            for book in events["books"]
        )

    def valid_outcome_accrual(outcomes: object) -> bool:
        if not isinstance(outcomes, dict):
            return False
        if (
            outcomes.get("unit") != "fire_x_horizon"
            or outcomes.get("separate_from_event_accrual") is not True
        ):
            return False
        horizons = outcomes.get("horizons")
        if not isinstance(horizons, dict) or set(horizons) != {
            "1h",
            "eod",
            "1d",
            "3d",
            "5d",
            "10d",
            "expiry",
        }:
            return False
        for cell in horizons.values():
            if not isinstance(cell, dict) or not isinstance(cell.get("books"), list):
                return False
            books = cell["books"]
            if cell.get("instrumented") is True:
                if not books or cell.get("authority") != "descriptive_only":
                    return False
                engine_ids = [
                    book.get("engine_id") for book in books if isinstance(book, dict)
                ]
                if len(engine_ids) != len(books) or len(engine_ids) != len(set(engine_ids)):
                    return False
                if not all(
                    isinstance(book, dict)
                    and book.get("engine_id") in allowed_engines
                    and nonnegative_count(book.get("n"))
                    for book in books
                ):
                    return False
            elif cell.get("instrumented") is False:
                if books:
                    return False
            else:
                return False
        return True

    def valid_forward_ledgers(value: object) -> bool:
        if not isinstance(value, dict) or not isinstance(value.get("books"), list):
            return False
        attribution = value.get("incremental_options_attribution")
        if not isinstance(attribution, dict) or attribution.get("available") is not False:
            return False
        books = value["books"]
        engine_ids = [
            book.get("engine_id") for book in books if isinstance(book, dict)
        ]
        if len(engine_ids) != len(books) or len(engine_ids) != len(set(engine_ids)):
            return False
        for book in books:
            if (
                not isinstance(book, dict)
                or book.get("authority") != "display_only"
                or book.get("engine_id") not in allowed_engines
                or not nonnegative_count(book.get("n_fires"))
                or not nonnegative_count(book.get("n_open"))
                or not nonnegative_count(book.get("n_distinct_fire_dates"))
            ):
                return False
            horizons = book.get("horizons")
            paths = book.get("paths")
            if not isinstance(horizons, dict) or set(horizons) != {
                "h5",
                "h10",
                "h21",
                "h63",
            }:
                return False
            if not isinstance(paths, dict) or set(paths) != {"path25", "path63"}:
                return False
            if not all(
                isinstance(cell, dict) and nonnegative_count(cell.get("n"))
                for cell in [*horizons.values(), *paths.values()]
            ):
                return False
        return True

    source_clocks = pit.get("source_available_at") if isinstance(pit, dict) else None
    source_clocks_ok = (
        isinstance(source_clocks, dict)
        and set(source_clocks) == {"flow_leaders", "pick_lab"}
        and all(
            raw is None
            or (
                exact_utc(raw) is not None
                and root_available is not None
                and exact_utc(raw) <= root_available
            )
            for raw in source_clocks.values()
        )
    )
    konseki_connected = isinstance(konseki, dict) and konseki.get("connected") is True
    konseki_decision = exact_utc(konseki.get("decision_at")) if konseki_connected else None
    konseki_available = exact_utc(konseki.get("available_at")) if konseki_connected else None
    konseki_receipt = konseki.get("receipt") if konseki_connected else None
    konseki_pit_ok = (
        (
            konseki_decision is not None
            and konseki_available is not None
            and konseki_available >= konseki_decision
            and root_available is not None
            and konseki_available <= root_available
            and (root_decision is None or konseki_available <= root_decision)
            and isinstance(konseki_receipt, dict)
            and isinstance(konseki_receipt.get("memory_id"), str)
            and bool(konseki_receipt.get("memory_id", "").strip())
        )
        if konseki_connected
        else (
            isinstance(konseki, dict)
            and konseki.get("decision_at") is None
            and konseki.get("available_at") is None
            and konseki.get("receipt") is None
        )
    )
    valid = (
        isinstance(payload, dict)
        and payload.get("schema") == "options.prophet_shadow/v1"
        and payload.get("authority") == "display_only"
        and payload.get("mode") == "shadow"
        and "decision_at" in payload
        and root_decision_raw is None
        and root_available is not None
        and exact_utc(payload.get("built_at")) == root_available
        and isinstance(pit, dict)
        and pit.get("clock") == "UTC"
        and pit.get("decision_at_required_for_issued_portfolio") is True
        and pit.get("promotion_ready") is False
        and source_clocks_ok
        and isinstance(selection, dict)
        and selection.get("style") == "abstention_first"
        and selection.get("capacity_enforced_by_projection") is False
        and isinstance(selection.get("target_batch_size"), dict)
        and isinstance(portfolio, dict)
        and portfolio.get("operator_reviewed_issue_desk") is False
        and portfolio.get("issued_model_portfolio") is False
        and portfolio.get("managed_positions") is False
        and isinstance(opportunities, list)
        and all(
            isinstance(row, dict)
            and isinstance(row.get("symbol"), str)
            and bool(row.get("symbol", "").strip())
            and row.get("authority") == "display_only"
            and row.get("direction_reliable") is False
            and row.get("engine_id") in allowed_engines
            and row.get("lane") == expected_lane.get(row.get("engine_id"))
            and valid_fire_clock(row)
            and isinstance(row.get("source_signing_reliable"), bool)
            and isinstance(row.get("execution"), dict)
            and row["execution"].get("status") == "withheld"
            and row["execution"].get("executable") is False
            for row in opportunities
        )
        and isinstance(watchlist, list)
        and all(
            isinstance(row, dict)
            and isinstance(row.get("symbol"), str)
            and bool(row.get("symbol", "").strip())
            and row.get("direction_reliable") is False
            and isinstance(row.get("source_signing_reliable"), bool)
            and valid_watch_clock(row)
            for row in watchlist
        )
        and isinstance(readiness, dict)
        and isinstance(readiness.get("components"), dict)
        and isinstance(readiness.get("gates"), dict)
        and isinstance(direction, dict)
        and direction.get("reliable") is False
        and direction.get("value") is None
        and isinstance(trajectory, dict)
        and trajectory.get("status") == "withheld"
        and trajectory.get("take_profit") is None
        and trajectory.get("time_to_target") is None
        and trajectory.get("exit_window") is None
        and valid_forward_ledgers(ledgers)
        and isinstance(accrual, dict)
        and valid_event_accrual(accrual.get("events"))
        and valid_outcome_accrual(accrual.get("outcomes"))
        and isinstance(konseki, dict)
        and konseki.get("expected_schema") == "konseki.market_memory/v1"
        and isinstance(konseki.get("connected"), bool)
        and konseki.get("authority") == "context_only"
        and konseki.get("weight") == 0
        and konseki.get("may_rank") is False
        and konseki.get("may_gate") is False
        and konseki.get("may_size") is False
        and konseki_pit_ok
        and isinstance(provenance, dict)
        and isinstance(feedback, dict)
        and feedback.get("enabled") is False
        and feedback.get("weight") == 0
        and feedback.get("mode") == "shadow_only"
    )
    if not valid:
        log.warning("mirror_flow_idx: refusing foreign Options Prophet contract")
    return valid


def _verify_upload(s3, local_path: Path, r2_key: str, bucket: str) -> bool:
    """Confirm R2 contains the exact local byte length and SHA-256 receipt."""
    try:
        receipt = s3.head_object(Bucket=bucket, Key=r2_key)
        size = receipt.get("ContentLength") if isinstance(receipt, dict) else None
        expected_size = local_path.stat().st_size
        metadata = receipt.get("Metadata") if isinstance(receipt, dict) else None
        remote_digest = metadata.get("sha256") if isinstance(metadata, dict) else None
        expected_digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
        if size != expected_size or remote_digest != expected_digest:
            log.warning(
                "mirror_flow_idx: R2 verification mismatch for %s "
                "(size=%r expected=%r sha256_match=%s)",
                r2_key,
                size,
                expected_size,
                remote_digest == expected_digest,
            )
            return False
        log.info("mirror_flow_idx: verified R2:%s (%d bytes)", r2_key, size)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("mirror_flow_idx: R2 verification failed for %s: %s", r2_key, exc)
        return False


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="R2 mirror for flow index / leaders")
    parser.add_argument(
        "--leaders",
        action="store_true",
        help="Upload site/flowleaders/leaders.json instead of site/flow/index.json",
    )
    parser.add_argument(
        "--radar",
        action="store_true",
        help="Upload site/leaderradar/radar.json (Leader Radar LR W2a)",
    )
    parser.add_argument(
        "--options-prophet",
        action="store_true",
        help="Upload site/options_prophet/index.json (Options Prophet shadow)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Return non-zero when the selected artifact cannot be published. "
            "The calling workflow may still choose to treat that failure as non-fatal."
        ),
    )
    args = parser.parse_args()

    if args.options_prophet:
        local_path = OPTIONS_PROPHET_PATH
        r2_key = OPTIONS_PROPHET_R2_KEY
    elif args.radar:
        local_path = RADAR_PATH
        r2_key = RADAR_R2_KEY
    elif args.leaders:
        local_path = LEADERS_PATH
        r2_key = LEADERS_R2_KEY
    else:
        local_path = FLOW_INDEX_PATH
        r2_key = R2_KEY

    if not local_path.exists():
        log.warning(
            "mirror_flow_idx: %s absent — builder may not have run yet; skipping",
            local_path,
        )
        return 1 if args.strict else 0

    if (
        args.options_prophet
        and args.strict
        and not _valid_options_prophet_contract(local_path)
    ):
        return 1

    s3 = _r2_client()
    if s3 is None:
        log.info("mirror_flow_idx: R2 creds absent — skipping upload (non-fatal)")
        return 1 if args.strict else 0

    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    published = _upload(s3, local_path, r2_key, bucket)
    if args.strict and published:
        published = _verify_upload(s3, local_path, r2_key, bucket)
    return 0 if published or not args.strict else 1


if __name__ == "__main__":
    sys.exit(main())
