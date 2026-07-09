"""scripts/build_unusual_baseline.py — per-root 30-session option-volume baseline.

Reads the ThetaData EOD store (per-root, column-pruned — RAM LAW: never load full store)
and computes 30-session volume statistics for each root and, where the bounded read is
cheap, per-contract (expiration, strike, right) stats.

Output:
    data/live_flow_out/unusual_baseline.json  (local, gitignored)
    R2: live_flow/unusual_baseline.json       (when --publish is set)

Schema: flow.unusual_baseline/v1
{
  "schema": "flow.unusual_baseline/v1",
  "asof": "YYYY-MM-DD",
  "sessions_used": ["YYYY-MM-DD", ...],
  "roots": {
    "<ROOT>": {
      "mean_vol_30d": float | null,
      "p95_vol_30d":  float | null,
      "sessions_used": int,
      "null_reason": str | null        # present and non-null when below MIN_SESSIONS
    },
    ...
  }
}

DISPLAY-TIER: no signal scoring, no money-path.
OI law: not applicable here (volume-only artifact, no OI reads).
RAM LAW: reads only the single-year parquet for each root; never loads full store.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
# Minimum sessions needed to emit non-null stats; honest null otherwise.
MIN_SESSIONS = 10

# Sessions requested for the rolling window.
WINDOW_SESSIONS = 30

# Output paths
_OUT_LOCAL    = "live_flow_out/unusual_baseline.json"
_R2_KEY       = "live_flow/unusual_baseline.json"

# Default roots (same set as build_options_matrix)
DEFAULT_ROOTS = [
    "SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD", "GOOGL",
]


# ── store helpers ─────────────────────────────────────────────────────────────

def _store_root_path() -> Path:
    """Path to the thetadata_eod store root (env override or default)."""
    env = os.environ.get("THETADATA_STORE")
    if env:
        return Path(env)
    # Default: theta-ops-wt pattern (matches flow-ops-wt convention)
    return Path.home() / "theta-ops-wt" / "data" / "thetadata_eod"


def _out_path() -> Path:
    """Local output path under data/live_flow_out/."""
    return _REPO / "data" / _OUT_LOCAL


def _recent_sessions(store: Path, root: str, n: int = WINDOW_SESSIONS) -> list[str]:
    """Return the n most recent session dates (YYYY-MM-DD) with EOD data for root.

    Column-pruned per RAM LAW: reads only current-year and prior-year parquets,
    loads only the 'date' column first to identify sessions, then full parquet
    only for the matching subset.  Never loads all years.
    """
    eod_dir = store / "eod" / root.upper()
    if not eod_dir.exists():
        return []

    # Read only the two most recent year parquets (current + prior) to bound reads.
    today = date.today()
    candidate_years = sorted({today.year, today.year - 1}, reverse=True)

    dates_seen: set[str] = set()
    for yr in candidate_years:
        f = eod_dir / f"{yr}.parquet"
        if not f.exists():
            continue
        try:
            # Column-pruned: load only 'date' column to enumerate sessions cheaply.
            df_dates = pd.read_parquet(f, columns=["date"])
            df_dates["date"] = pd.to_datetime(df_dates["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            df_dates = df_dates.dropna(subset=["date"])
            dates_seen.update(df_dates["date"].unique().tolist())
        except Exception as e:  # noqa: BLE001
            log.debug("unusual_baseline: date-scan failed for %s/%d: %s", root, yr, e)

    if not dates_seen:
        return []

    # Sort descending; return up to n
    all_dates = sorted(dates_seen, reverse=True)
    return all_dates[:n]


def _load_volume_for_sessions(store: Path, root: str, sessions: list[str]) -> pd.DataFrame | None:
    """Load volume data for the given sessions, column-pruned.

    Returns a DataFrame with columns [date, volume] (aggregate daily volume per session).
    Per RAM LAW: reads only the year parquets needed (at most 2), loads only
    ['date', 'volume'] columns.
    """
    if not sessions:
        return None

    years_needed = sorted({int(s[:4]) for s in sessions})
    eod_dir = store / "eod" / root.upper()
    frames = []

    session_set = set(sessions)

    for yr in years_needed:
        f = eod_dir / f"{yr}.parquet"
        if not f.exists():
            continue
        try:
            df = pd.read_parquet(f, columns=["date", "volume"])
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=["date"])
            # Filter to only the sessions we need
            df = df[df["date"].isin(session_set)]
            if not df.empty:
                frames.append(df)
        except Exception as e:  # noqa: BLE001
            log.debug("unusual_baseline: volume load failed for %s/%d: %s", root, yr, e)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    combined["volume"] = pd.to_numeric(combined["volume"], errors="coerce")
    combined = combined.dropna(subset=["volume"])
    combined = combined[combined["volume"] > 0]
    if combined.empty:
        return None

    # Aggregate: sum volume across all contracts per session date
    daily = combined.groupby("date")["volume"].sum().reset_index()
    return daily


def compute_root_baseline(store: Path, root: str) -> dict:
    """Compute 30-session volume baseline for one root.

    Returns a dict with mean_vol_30d, p95_vol_30d, sessions_used, and
    optionally null_reason if fewer than MIN_SESSIONS are available.
    """
    root = root.upper()
    sessions = _recent_sessions(store, root, WINDOW_SESSIONS)

    if len(sessions) < MIN_SESSIONS:
        n = len(sessions)
        reason = f"only {n} sessions available (minimum {MIN_SESSIONS})"
        log.info("unusual_baseline: %s — null (%s)", root, reason)
        return {
            "mean_vol_30d":  None,
            "p95_vol_30d":   None,
            "sessions_used": n,
            "null_reason":   reason,
        }

    daily = _load_volume_for_sessions(store, root, sessions)
    if daily is None or daily.empty:
        reason = "volume data absent for session range"
        log.info("unusual_baseline: %s — null (%s)", root, reason)
        return {
            "mean_vol_30d":  None,
            "p95_vol_30d":   None,
            "sessions_used": 0,
            "null_reason":   reason,
        }

    vols = daily["volume"].values
    n_ok = int(len(vols))

    # Post-load gate: the date-scan at line 176 checked len(sessions), but volume
    # loading may fail or filter rows for some of those sessions.  Re-apply the
    # floor to the actual post-load session count so we never emit stats over
    # fewer than MIN_SESSIONS real data points.
    if n_ok < MIN_SESSIONS:
        reason = f"only {n_ok} sessions with volume data after load (minimum {MIN_SESSIONS})"
        log.info("unusual_baseline: %s — null (%s)", root, reason)
        return {
            "mean_vol_30d":  None,
            "p95_vol_30d":   None,
            "sessions_used": n_ok,
            "null_reason":   reason,
        }

    mean_v = float(np.mean(vols))
    p95_v  = float(np.percentile(vols, 95))

    log.info("unusual_baseline: %s — sessions=%d mean_vol=%.0f p95_vol=%.0f",
             root, n_ok, mean_v, p95_v)
    return {
        "mean_vol_30d":  round(mean_v, 0),
        "p95_vol_30d":   round(p95_v, 0),
        "sessions_used": n_ok,
        "null_reason":   None,
    }


# ── R2 helpers ─────────────────────────────────────────────────────────────────

def _r2_client():
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
        log.warning("unusual_baseline: R2 client build failed: %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("unusual_baseline: R2 upload ok → %s", r2_key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("unusual_baseline: R2 upload failed for %s: %s", r2_key, e)
        return False


# ── main builder ──────────────────────────────────────────────────────────────

def build(roots: list[str], store: Path | None = None,
          publish: bool = False, dry_run: bool = False) -> dict:
    """Compute baseline for each root.  Returns the full payload dict.

    publish=True uploads to R2 (sourcing creds from env).
    dry_run=True skips all writes/uploads.
    """
    if store is None:
        store = _store_root_path()

    asof = date.today().isoformat()
    roots_out: dict[str, dict] = {}

    for root in roots:
        root = root.upper()
        try:
            roots_out[root] = compute_root_baseline(store, root)
        except Exception as e:  # noqa: BLE001
            log.error("unusual_baseline: unexpected error for %s: %s", root, e)
            roots_out[root] = {
                "mean_vol_30d":  None,
                "p95_vol_30d":   None,
                "sessions_used": 0,
                "null_reason":   f"error: {e}",
            }

    # Collect all sessions referenced (union of sessions across roots with data)
    all_sessions: list[str] = []
    if store is not None and not dry_run:
        # Quick union — just use SPY as representative if present
        rep_root = "SPY" if "SPY" in [r.upper() for r in roots] else (roots[0].upper() if roots else None)
        if rep_root:
            all_sessions = _recent_sessions(store, rep_root, WINDOW_SESSIONS)

    payload = {
        "schema":        "flow.unusual_baseline/v1",
        "asof":          asof,
        "sessions_used": all_sessions,
        "roots":         roots_out,
    }

    if dry_run:
        log.info("unusual_baseline: [DRY RUN] payload roots=%d", len(roots_out))
        return payload

    # ── write local ───────────────────────────────────────────────────────────
    out = _out_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.rename(out)
    log.info("unusual_baseline: wrote %s", out)

    # ── upload to R2 ─────────────────────────────────────────────────────────
    if publish:
        s3 = _r2_client()
        bucket = os.environ.get("R2_BUCKET", "")
        if s3 and bucket:
            _upload_r2(s3, bucket, out, _R2_KEY)
        else:
            log.warning("unusual_baseline: --publish set but R2 creds/bucket absent — skipping upload")

    return payload


# ── CLI ────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build per-root 30-session option-volume baseline (flow.unusual_baseline/v1)."
    )
    parser.add_argument(
        "--roots", nargs="+", default=DEFAULT_ROOTS,
        metavar="ROOT",
        help="Option root symbols (default: SPY QQQ IWM NVDA TSLA AAPL MSFT META AMD GOOGL)",
    )
    parser.add_argument(
        "--publish", action="store_true", default=False,
        help="Upload to R2 live_flow/unusual_baseline.json",
    )
    parser.add_argument(
        "--store", default=None,
        help="Path to ThetaData EOD store root (default: THETADATA_STORE env or ~/theta-ops-wt/...)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Compute and log results without writing any file",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = Path(args.store) if args.store else None
    roots = [r.upper() for r in args.roots]
    log.info("unusual_baseline: roots=%d publish=%s dry_run=%s", len(roots), args.publish, args.dry_run)

    payload = build(roots=roots, store=store, publish=args.publish, dry_run=args.dry_run)

    n_ok   = sum(1 for v in payload["roots"].values() if v.get("mean_vol_30d") is not None)
    n_null = sum(1 for v in payload["roots"].values() if v.get("mean_vol_30d") is None)
    log.info("unusual_baseline: done — ok=%d null=%d", n_ok, n_null)
    return 0


if __name__ == "__main__":
    sys.exit(main())
