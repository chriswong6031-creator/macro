"""scripts/build_options_hub_nightly.py — nightly Options Hub analytics builder.

Iterates ETF anchor roots (or --roots override), builds per-root vol/GEX payloads
and cross-root OI movers + hot contracts, writes JSONs to
data/live_flow_out/options_hub/ and optionally publishes to R2 options_hub/ prefix.

Usage:
  python -m scripts.build_options_hub_nightly [--roots SPY QQQ IWM] [--out DIR]
      [--publish | --no-publish] [--date YYYY-MM-DD]

Defaults:
  --roots    : all roots with greeks in the T1 store (ETF anchors first)
  --out      : data/live_flow_out/options_hub/
  --publish  : publishes to R2 (requires R2_ENDPOINT / R2_ACCESS_KEY_ID /
               R2_SECRET_ACCESS_KEY / R2_BUCKET env vars)
  --date     : latest available greeks date (auto-detected)

INERT per root: each root failure logs + skips, never aborts the run.
OI TIMING LAW: all GEX and OI-mover logic uses OI[t-1] (never same-day OI).
DISPLAY-TIER ONLY: no ranking, scoring, or money-path interaction.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.thetadata_store import _load_parquets, _normalise_date, store_root
from engine.options_hub import compute_vol, compute_gex, compute_oi_movers, compute_hot_contracts

log = logging.getLogger(__name__)

# ── R2 publish prefix ─────────────────────────────────────────────────────────
R2_PREFIX = "options_hub/"

# ── default roots (ETF anchors) ────────────────────────────────────────────────
DEFAULT_ROOTS = [
    "SPY", "QQQ", "IWM", "DIA", "SMH", "XLF", "XLE", "XLU", "XLK",
    "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE", "XLC",
    "KRE", "XBI", "ARKK", "SOXX", "SPX", "SPXW",
]


# --------------------------------------------------------------------------- #
# R2 helpers (mirrored from scripts/live_flow_poller._r2_client/_upload_r2)   #
# --------------------------------------------------------------------------- #

def _r2_client():
    """Build a boto3 S3 client for R2, or None if creds absent."""
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
        log.warning("options_hub_builder: R2 client build failed: %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    """Upload a local file to R2. Returns True on success."""
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("options_hub_builder: R2 upload ok → %s", r2_key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("options_hub_builder: R2 upload failed for %s: %s", r2_key, e)
        return False


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, allow_nan=False, default=str), encoding="utf-8")


# --------------------------------------------------------------------------- #
# data loading helpers
# --------------------------------------------------------------------------- #

def _latest_greeks_date(root: str, theta_store: str | Path | None) -> str | None:
    """Return the most recent date string in the greeks store for this root."""
    df = _load_parquets("greeks", root, None, theta_store)
    if df.empty or "date" not in df.columns:
        return None
    df = _normalise_date(df)
    dates = sorted(df["date"].unique())
    return dates[-1] if dates else None


def _load_greeks(root: str, theta_store: str | Path | None) -> pd.DataFrame:
    """Load all available greeks parquets for root."""
    df = _load_parquets("greeks", root, None, theta_store)
    if df.empty:
        return pd.DataFrame()
    return _normalise_date(df)


def _load_oi_for_date(root: str, date_str: str, theta_store: str | Path | None) -> pd.DataFrame:
    """Load OI parquet for one specific date."""
    year = pd.Timestamp(date_str).year
    df = _load_parquets("oi", root, [year], theta_store)
    if df.empty:
        return pd.DataFrame()
    df = _normalise_date(df)
    return df[df["date"] == date_str].copy()


def _load_eod_for_date(root: str, date_str: str, theta_store: str | Path | None) -> pd.DataFrame:
    """Load EOD parquet for one specific date."""
    year = pd.Timestamp(date_str).year
    df = _load_parquets("eod", root, [year], theta_store)
    if df.empty:
        return pd.DataFrame()
    df = _normalise_date(df)
    sub = df[df["date"] == date_str].copy()
    # rename bid/ask to avoid collision with greeks
    if "bid" in sub.columns and "bid_eod" not in sub.columns:
        sub = sub.rename(columns={"bid": "bid_eod", "ask": "ask_eod"})
    return sub


def _prev_oi_date(oi_all: pd.DataFrame, asof: str) -> str | None:
    """Return the session before `asof` in the OI store."""
    if oi_all.empty or "date" not in oi_all.columns:
        return None
    dates = sorted(oi_all["date"].unique())
    before = [d for d in dates if d < asof]
    return before[-1] if before else None


def _load_yahoo(root: str) -> pd.Series | None:
    """Load yahoo adjusted-close series for `root`. Returns Series indexed by str date."""
    try:
        from lib import store as lib_store
        safe = root.upper().replace("^", "_").replace("=", "_").replace("/", "_")
        df = lib_store.read("yahoo", safe)
        if df is None or df.empty or "close" not in df.columns:
            return None
        s = df["close"].copy()
        s.index = pd.to_datetime(s.index).date.astype(str)
        return s
    except Exception as e:  # noqa: BLE001
        log.debug("options_hub_builder: yahoo load failed for %s: %s", root, e)
        return None


# --------------------------------------------------------------------------- #
# per-root builder
# --------------------------------------------------------------------------- #

def build_root(
    root: str,
    asof: str,
    theta_store: str | Path | None,
) -> tuple[dict, dict]:
    """Build vol + gex payloads for one root.

    Returns (vol_payload, gex_payload). Both are non-null dicts (may be empty
    analytics when data is absent).

    OI TIMING LAW: we load OI for asof (= OPRA report representing EOD(asof-1)
    positions) as OI[t-1]. The previous session's OI is used for ΔOI comparisons.
    """
    greeks = _load_greeks(root, theta_store)

    # ── vol ────────────────────────────────────────────────────────────────────
    yahoo_closes = _load_yahoo(root)
    yahoo_series: pd.Series
    if yahoo_closes is not None:
        yahoo_series = yahoo_closes
    else:
        yahoo_series = pd.Series(dtype=float)

    vol_payload = compute_vol(greeks, yahoo_series, asof, root)

    # ── gex ────────────────────────────────────────────────────────────────────
    # greeks frame for asof date only
    greeks_asof = greeks[greeks["date"] == asof].copy() if not greeks.empty else pd.DataFrame()

    # OI[t-1]: OPRA reports OI for the session; calling it with asof gives us t-1
    # positions. Per OI timing law: for any day-t GEX signal, the correct OI is
    # the OI parquet for `asof` (which OPRA already reports as end-of-t-1 data).
    oi_t1 = _load_oi_for_date(root, asof, theta_store)

    gex_payload = compute_gex(greeks_asof, oi_t1, asof, root)

    return vol_payload, gex_payload


# --------------------------------------------------------------------------- #
# cross-root OI movers + hot contracts
# --------------------------------------------------------------------------- #

def build_cross_root(
    roots_ok: list[str],
    asof: str,
    theta_store: str | Path | None,
) -> tuple[dict, dict]:
    """Build oi_movers.json and hot_contracts.json across all processed roots."""
    # OI movers: aggregate per-root, merge two latest sessions
    all_mover_rows: list[dict] = []

    eod_frames: dict[str, pd.DataFrame] = {}
    oi_prev_frames: dict[str, pd.DataFrame] = {}

    for root in roots_ok:
        try:
            # EOD for asof
            eod_t = _load_eod_for_date(root, asof, theta_store)
            eod_frames[root] = eod_t

            # OI for asof (= oi[t-1] per timing law)
            oi_t = _load_oi_for_date(root, asof, theta_store)

            # OI for t-2 (the previous session's OI)
            year = pd.Timestamp(asof).year
            oi_all = _load_parquets("oi", root, [year, year - 1], theta_store)
            if not oi_all.empty:
                oi_all = _normalise_date(oi_all)
            t1_date = _prev_oi_date(oi_all, asof) if not oi_all.empty else None

            if t1_date:
                oi_t1 = oi_all[oi_all["date"] == t1_date].copy()
            else:
                oi_t1 = pd.DataFrame()

            oi_prev_frames[root] = oi_t

            # per-root oi_movers
            if not oi_t.empty:
                m = compute_oi_movers(oi_t, oi_t1, eod_t, asof, top_n=100)
                for row in m.get("movers", []):
                    row["root"] = root
                    all_mover_rows.append(row)

        except Exception as e:  # noqa: BLE001
            log.warning("options_hub_builder: cross-root %s failed: %s", root, e)

    # top 100 by |d_oi| across all roots
    all_mover_rows.sort(key=lambda r: abs(r.get("d_oi", 0)), reverse=True)
    oi_movers = {
        "schema": "options_hub.oi_movers/v1",
        "asof": asof,
        "movers": all_mover_rows[:100],
    }

    hot = compute_hot_contracts(eod_frames, oi_prev_frames, asof)

    return oi_movers, hot


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    ap = argparse.ArgumentParser(description="Build Options Hub nightly analytics JSONs")
    ap.add_argument("--roots", nargs="+", metavar="ROOT",
                    help="Override root list (default: all T1 ETF anchors)")
    ap.add_argument("--out", default=None, metavar="DIR",
                    help="Local output directory (default: data/live_flow_out/options_hub/)")
    ap.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="Reference date (default: latest greeks date for SPY)")
    ap.add_argument("--publish", action="store_true", default=True,
                    help="Publish to R2 (default: True)")
    ap.add_argument("--no-publish", dest="publish", action="store_false")
    ap.add_argument("--theta-store", default=None, metavar="PATH",
                    help="Override thetadata store root")
    args = ap.parse_args()

    # ── resolve paths ──────────────────────────────────────────────────────────
    from lib import config as lib_config
    data_root = lib_config.data_dir()

    out_dir = Path(args.out) if args.out else (data_root / "live_flow_out" / "options_hub")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Item 5 — THETADATA_STORE env: explicit override wins over all auto-detect paths.
    # Priority: --theta-store CLI > THETADATA_STORE env > data/thetadata_eod default.
    _theta_store_env = os.environ.get("THETADATA_STORE")
    if args.theta_store:
        theta_store = Path(args.theta_store)
    elif _theta_store_env:
        theta_store = Path(_theta_store_env)
        log.info("options_hub_builder: THETADATA_STORE env → %s", theta_store)
    else:
        theta_store = data_root / "thetadata_eod"

    # If the configured store has no eod/ or greeks/ subdirectories, fall back to the
    # canonical Mac ops-wt path (the brief: "T1 store via symlink data/thetadata_eod ->
    # /Users/chriswong/theta-ops-wt/data/thetadata_eod (create if missing)").
    # This convenience auto-detect ONLY fires when neither --theta-store nor
    # THETADATA_STORE env are set (guarded by the else branch above).
    if not args.theta_store and not _theta_store_env:
        _OPS_WT_STORE = Path("/Users/chriswong/theta-ops-wt/data/thetadata_eod")
        if (not (theta_store / "eod").exists() and
                not (theta_store / "greeks").exists() and
                _OPS_WT_STORE.exists()):
            log.info(
                "options_hub_builder: %s has no eod/greeks subdirs — falling back to %s",
                theta_store, _OPS_WT_STORE,
            )
            theta_store = _OPS_WT_STORE

    # ── resolve roots ─────────────────────────────────────────────────────────
    if args.roots:
        roots = [r.upper() for r in args.roots]
    else:
        # all roots with greeks in the store
        from engine.thetadata_store import universe as td_universe
        store_roots = td_universe(store=theta_store)
        # prioritise DEFAULT_ROOTS, then append any others in the store
        seen: dict[str, None] = {}
        for r in DEFAULT_ROOTS:
            if r in store_roots:
                seen.setdefault(r, None)
        for r in store_roots:
            seen.setdefault(r, None)
        roots = list(seen)
        if not roots:
            roots = DEFAULT_ROOTS

    # ── resolve date ──────────────────────────────────────────────────────────
    asof = args.date
    if not asof:
        asof = _latest_greeks_date("SPY", theta_store)
        if not asof:
            log.error("options_hub_builder: cannot determine latest greeks date for SPY; "
                      "provide --date")
            sys.exit(1)
    log.info("options_hub_builder: asof=%s roots=%s", asof, roots)

    # ── R2 setup ──────────────────────────────────────────────────────────────
    bucket = os.environ.get("R2_BUCKET", "")
    s3 = None
    if args.publish:
        s3 = _r2_client()
        if s3 is None:
            log.warning("options_hub_builder: R2 creds absent — uploads will be skipped")
        elif not bucket:
            log.warning("options_hub_builder: R2_BUCKET not set — uploads will be skipped")
            s3 = None

    # ── per-root loop ─────────────────────────────────────────────────────────
    roots_ok: list[str] = []
    roots_skipped: list[str] = []
    roots_gex_skipped: list[str] = []  # roots where GEX R2 upload was suppressed (guard)

    for root in roots:
        log.info("options_hub_builder: processing %s …", root)
        try:
            vol_payload, gex_payload = build_root(root, asof, theta_store)

            # ── COMPLETENESS GUARD (CONTRACT) ────────────────────────────────────
            # If by_strike is empty, check whether the theta store actually has
            # contracts for this root on asof.  If it does, the empty payload is a
            # mid-backfill artifact — skip the R2 upload to preserve the last-good
            # object.  Only allow publishing an empty by_strike when the store
            # genuinely has no data (no_data_reason must be set in that case).
            gex_publish = True  # default: upload
            if not gex_payload.get("by_strike"):
                oi_check = _load_oi_for_date(root, asof, theta_store)
                if not oi_check.empty:
                    # Store has contracts but compute produced empty by_strike —
                    # suppressing R2 upload to keep last-good object.
                    log.warning(
                        "options_hub_builder: GEX GUARD triggered for %s on %s — "
                        "by_strike is empty but theta store has %d OI rows; "
                        "skipping R2 upload to preserve last-good object",
                        root, asof, len(oi_check),
                    )
                    gex_publish = False
                    roots_gex_skipped.append(root)
                else:
                    # Store genuinely has no data — mark the payload explicitly.
                    gex_payload["no_data_reason"] = (
                        f"no_oi_in_store:{asof}"
                    )
                    log.info(
                        "options_hub_builder: %s has no OI in store for %s — "
                        "publishing with no_data_reason",
                        root, asof,
                    )

            # write locally (always — local file reflects what was computed)
            vol_path = out_dir / "vol" / f"{root}.json"
            gex_path = out_dir / "gex" / f"{root}.json"
            _write_json(vol_path, vol_payload)
            _write_json(gex_path, gex_payload)

            # publish
            if s3 and bucket:
                _upload_r2(s3, bucket, vol_path, f"{R2_PREFIX}vol/{root}.json")
                if gex_publish:
                    _upload_r2(s3, bucket, gex_path, f"{R2_PREFIX}gex/{root}.json")

            roots_ok.append(root)
            log.info("options_hub_builder: %s done", root)

        except Exception as e:  # noqa: BLE001
            log.warning("options_hub_builder: %s FAILED — %s", root, e)
            roots_skipped.append(root)

    # ── cross-root payloads ───────────────────────────────────────────────────
    log.info("options_hub_builder: building cross-root payloads …")
    try:
        oi_movers, hot_contracts = build_cross_root(roots_ok, asof, theta_store)

        oi_path  = out_dir / "oi_movers.json"
        hot_path = out_dir / "hot_contracts.json"
        _write_json(oi_path,  oi_movers)
        _write_json(hot_path, hot_contracts)

        if s3 and bucket:
            _upload_r2(s3, bucket, oi_path,  f"{R2_PREFIX}oi_movers.json")
            _upload_r2(s3, bucket, hot_path, f"{R2_PREFIX}hot_contracts.json")

    except Exception as e:  # noqa: BLE001
        log.warning("options_hub_builder: cross-root build FAILED — %s", e)

    # ── summary ──────────────────────────────────────────────────────────────
    log.info(
        "options_hub_builder: complete. asof=%s roots_ok=%d roots_skipped=%d "
        "roots_gex_guarded=%d",
        asof, len(roots_ok), len(roots_skipped), len(roots_gex_skipped),
    )
    if roots_skipped:
        log.warning("options_hub_builder: skipped roots: %s", roots_skipped)
    if roots_gex_skipped:
        log.warning(
            "options_hub_builder: GEX R2 upload suppressed (guard) for %d roots: %s",
            len(roots_gex_skipped), roots_gex_skipped,
        )

    # Item 6 — register options_hub_nightly in the run_status/circuit-breaker pattern.
    # Mirrors the established pattern in scripts/collect.py + lib/store.write_status.
    try:
        import sys as _sys                      # noqa: PLC0415
        _repo = Path(__file__).resolve().parent.parent
        if str(_repo) not in _sys.path:
            _sys.path.insert(0, str(_repo))
        from lib import store as _store         # noqa: PLC0415
        from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415
        _rs = _store.read_status()
        _rs.setdefault("sources", {})["options_hub_nightly"] = {
            "status":            "ok" if not roots_skipped else "partial",
            "roots_ok":          len(roots_ok),
            "roots_skipped":     len(roots_skipped),
            "roots_gex_guarded": len(roots_gex_skipped),
            "roots_gex_guarded_list": roots_gex_skipped,
            "asof":              asof,
            "checked_at":        _dt.now(_tz.utc).isoformat(),
        }
        _store.write_status(_rs)
        log.info("options_hub_builder: run_status updated")
    except Exception as _rs_err:   # noqa: BLE001
        log.debug("options_hub_builder: run_status write failed (non-fatal): %s", _rs_err)


if __name__ == "__main__":
    main()
