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
import time
from pathlib import Path

import pandas as pd
import numpy as np

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.thetadata_store import _load_parquets, _normalise_date, store_root, clear_parquet_cache
from engine.options_hub import (
    compute_vol,
    compute_gex,
    compute_oi_movers,
    compute_hot_contracts,
    load_gex_history_v2,
    build_context_payload,
    build_tickers_ctx,
    build_oi_confirmed,
)
from engine.levels_publish import levels_payload_from_gex, LEVELS_PREFIX

log = logging.getLogger(__name__)

# ── R2 publish prefix ─────────────────────────────────────────────────────────
R2_PREFIX = "options_hub/"

# ── per-root wall-clock budget ────────────────────────────────────────────────
# Roots with large option chains (e.g. RCL, NVDA) can take 30-60 s legitimately;
# anything beyond ROOT_WALL_BUDGET_S indicates a hang and should be skipped.
ROOT_WALL_BUDGET_S: float = float(os.environ.get("HUB_ROOT_BUDGET_S", "420"))

# ── incremental aggregate publish interval ────────────────────────────────────
# Publish cross-root aggregates (oi_movers / hot_contracts / context) after every
# N roots so a mid-run OOM leaves the feeds only N roots stale, not entirely frozen.
INCREMENTAL_N: int = int(os.environ.get("HUB_INCREMENTAL_N", "50"))

# ── standard data paths (relative to data_root) ───────────────────────────────
_POLYGON_GEX_SUBDIR = "polygon_gex"
_GEX_LATEST_REL     = "gex/latest.json"
_FEAR_GREED_REL     = "basketdata/fear_greed.json"   # relative to site/
_TAPE_FLOW_SUBDIR   = "tape_flow/daily"

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


def _publish_aggregates(
    roots_ok: list[str],
    asof: str,
    theta_store,
    out_dir: Path,
    s3,
    bucket: str,
    fear_greed_path: Path,
    gex_latest_path: Path,
    live_flow_out_dir: Path,
    label: str = "incremental",
) -> dict | None:
    """Compute and publish cross-root aggregate artifacts from roots processed so far.

    Called both incrementally (every INCREMENTAL_N roots) and at end-of-run.
    Returns the oi_movers payload (for oi_confirmed chaining) or None on failure.
    """
    if not roots_ok:
        return None
    log.info(
        "options_hub_builder: [%s] publishing aggregates over %d roots …",
        label, len(roots_ok),
    )
    oi_movers_payload: dict | None = None
    try:
        oi_movers, hot_contracts = build_cross_root(roots_ok, asof, theta_store)
        oi_movers_payload = oi_movers
        oi_path  = out_dir / "oi_movers.json"
        hot_path = out_dir / "hot_contracts.json"
        _write_json(oi_path,  oi_movers)
        _write_json(hot_path, hot_contracts)
        if s3 and bucket:
            _upload_r2(s3, bucket, oi_path,  f"{R2_PREFIX}oi_movers.json")
            _upload_r2(s3, bucket, hot_path, f"{R2_PREFIX}hot_contracts.json")
        log.info("options_hub_builder: [%s] oi_movers + hot_contracts done", label)
    except Exception as e:  # noqa: BLE001
        log.warning("options_hub_builder: [%s] cross-root build FAILED — %s", label, e)

    try:
        ctx_payload = build_context_payload(
            asof=asof,
            gex_latest_path=gex_latest_path,
            fear_greed_path=fear_greed_path,
        )
        ctx_path = out_dir / "context.json"
        _write_json(ctx_path, ctx_payload)
        if s3 and bucket:
            _upload_r2(s3, bucket, ctx_path, f"{R2_PREFIX}context.json")
        log.info("options_hub_builder: [%s] context.json done", label)
    except Exception as e:  # noqa: BLE001
        log.warning("options_hub_builder: [%s] context.json build FAILED — %s", label, e)

    try:
        oi_confirmed_list = build_oi_confirmed(
            asof=asof,
            live_flow_out_dir=live_flow_out_dir,
            oi_movers_today=oi_movers_payload,
        )
        oi_conf_payload = {
            "schema": "options_hub.oi_confirmed/v1",
            "asof": asof,
            "confirmed": oi_confirmed_list,
        }
        oi_conf_path = out_dir / "oi_confirmed.json"
        _write_json(oi_conf_path, oi_conf_payload)
        if s3 and bucket:
            _upload_r2(s3, bucket, oi_conf_path, f"{R2_PREFIX}oi_confirmed.json")
        log.info(
            "options_hub_builder: [%s] oi_confirmed.json done (%d confirmed)",
            label, len(oi_confirmed_list),
        )
    except Exception as e:  # noqa: BLE001
        log.warning(
            "options_hub_builder: [%s] oi_confirmed.json build FAILED — %s", label, e,
        )

    return oi_movers_payload


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
    polygon_gex_dir: Path | None = None,
) -> tuple[dict, dict]:
    """Build vol + gex payloads for one root.

    Returns (vol_payload, gex_payload). Both are non-null dicts (may be empty
    analytics when data is absent).

    OI TIMING LAW: we load OI for asof (= OPRA report representing EOD(asof-1)
    positions) as OI[t-1]. The previous session's OI is used for ΔOI comparisons.

    CONTRACT v2: gex_payload.history is attached when polygon_gex_dir is provided
    and the summary_{ROOT}.parquet exists.  When absent, the 'history' key is
    omitted entirely (not set to null) — frontend checks key presence.
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

    # ── CONTRACT v2: attach gex history from polygon_gex summary parquet ──────
    if polygon_gex_dir is not None:
        try:
            hist = load_gex_history_v2(root, polygon_gex_dir)
            if hist is not None:
                gex_payload = dict(gex_payload)
                gex_payload["history"] = hist
        except Exception as _he:  # noqa: BLE001
            log.warning("build_root: gex_history attach failed for %s — %s", root, _he)

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
# Completeness guard helper (pure — testable without main())
# --------------------------------------------------------------------------- #

def _gex_publish_decision(
    gex_payload: dict,
    root: str,
    asof: str,
    theta_store,
) -> tuple[bool, dict, bool]:
    """Decide whether to publish gex_payload to R2.

    Returns (gex_publish, gex_payload, is_guarded):
      - gex_publish:  True  → upload to R2; False → skip upload (preserve last-good)
      - gex_payload:  possibly mutated (no_data_reason added for genuine empty store)
      - is_guarded:   True when upload was suppressed by the mid-backfill guard
    """
    if gex_payload.get("by_strike"):
        return True, gex_payload, False

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
        return False, gex_payload, True
    else:
        # Store genuinely has no data — mark the payload explicitly.
        gex_payload = dict(gex_payload)
        gex_payload["no_data_reason"] = f"no_oi_in_store:{asof}"
        log.info(
            "options_hub_builder: %s has no OI in store for %s — "
            "publishing with no_data_reason",
            root, asof,
        )
        return True, gex_payload, False


def _gex_history_relpath(root: str, gex_payload: dict) -> str | None:
    """Relative path for the dated per-strike GEX snapshot, or None to skip.

    WP-GEX-SNAPSHOTS (research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md §7):
    gex/{ROOT}.json is overwritten in place every night, so per-strike
    topology is lost as point-in-time data. Retaining the same payload under
    a dated key gives the Exposure-by-Strike scrubber and S-TOPO-SIGMA a
    point-in-time per-strike topology history to read from.

    Key date = the payload's own as-of/session date (NEVER wall clock — a
    delayed or manual re-run must land on the session it describes, not the
    day it happened to run).

    Returns None (skip the dated write) when:
      - the payload has no by_strike rows (never write empty history), or
      - the payload carries no asof date to key by.
    """
    if not gex_payload.get("by_strike"):
        return None
    asof = gex_payload.get("asof")
    if not asof:
        return None
    return f"gex_history/{root}/{asof}.json"


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

    # CONTRACT v2 data paths (resolved once; graceful-absent throughout)
    polygon_gex_dir = data_root / _POLYGON_GEX_SUBDIR
    gex_latest_path = data_root / _GEX_LATEST_REL
    # fear_greed.json lives under site/ (git-tracked, not data/)
    _repo_root = Path(__file__).resolve().parent.parent
    fear_greed_path = _repo_root / "site" / _FEAR_GREED_REL
    tape_flow_dir = data_root / _TAPE_FLOW_SUBDIR
    live_flow_out_dir = data_root / "live_flow_out"  # poller archive root

    # WP-RESOLVER — store resolution is canonical: --theta-store CLI wins, then
    # engine.thetadata_store.resolve_thetadata_store (THETADATA_STORE env →
    # data_dir()/thetadata_eod → ops-wt), every candidate content-checked.
    # Fail-loud contract: this builder PUBLISHES artifacts, so when no store
    # resolves it exits nonzero instead of building/publishing empty payloads
    # (the options_witness 0/18 empty-store incident shape).
    from engine.thetadata_store import _has_store_content, resolve_thetadata_store
    if args.theta_store:
        theta_store = Path(args.theta_store)
        if not _has_store_content(theta_store):
            log.error(
                "options_hub_builder: --theta-store %s is missing or contains none "
                "of eod/oi/greeks — refusing to build/publish from an empty store",
                theta_store,
            )
            sys.exit(1)
    else:
        theta_store = resolve_thetadata_store(
            required=False, purpose="build_options_hub_nightly")
        if theta_store is None:
            log.error(
                "options_hub_builder: no ThetaData store resolves — exiting "
                "nonzero WITHOUT writing/publishing empty artifacts "
                "(set THETADATA_STORE or pass --theta-store)")
            sys.exit(1)

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
    roots_timeout: list[str] = []      # roots skipped due to wall-clock budget

    _last_incremental: int = 0         # index of last incremental aggregate publish

    for _root_idx, root in enumerate(roots):
        log.info("options_hub_builder: processing %s …", root)
        _root_start = time.monotonic()
        try:
            vol_payload, gex_payload = build_root(root, asof, theta_store, polygon_gex_dir)

            _elapsed = time.monotonic() - _root_start
            if _elapsed > ROOT_WALL_BUDGET_S:
                log.warning(
                    "options_hub_builder: %s budget exceeded (%.1fs > %.0fs) — "
                    "skipping upload, continuing",
                    root, _elapsed, ROOT_WALL_BUDGET_S,
                )
                roots_timeout.append(root)
                clear_parquet_cache()
                continue

            # ── COMPLETENESS GUARD (CONTRACT) ────────────────────────────────────
            gex_publish, gex_payload, is_guarded = _gex_publish_decision(
                gex_payload, root, asof, theta_store
            )
            if is_guarded:
                roots_gex_skipped.append(root)

            # write locally (always — local file reflects what was computed)
            vol_path = out_dir / "vol" / f"{root}.json"
            gex_path = out_dir / "gex" / f"{root}.json"
            _write_json(vol_path, vol_payload)
            _write_json(gex_path, gex_payload)

            # CONTRACT v2 — per-root tickers_ctx
            try:
                tctx = build_tickers_ctx(root, asof, tape_flow_dir)
                tctx_path = out_dir / "tickers_ctx" / f"{root}.json"
                _write_json(tctx_path, tctx)
                if s3 and bucket:
                    _upload_r2(s3, bucket, tctx_path,
                               f"{R2_PREFIX}tickers_ctx/{root}.json")
            except Exception as _te:  # noqa: BLE001
                log.warning("options_hub_builder: tickers_ctx failed for %s — %s", root, _te)

            # publish vol + gex
            if s3 and bucket:
                _upload_r2(s3, bucket, vol_path, f"{R2_PREFIX}vol/{root}.json")
                if gex_publish:
                    _upload_r2(s3, bucket, gex_path, f"{R2_PREFIX}gex/{root}.json")

            # ── WP-GEX-SNAPSHOTS: dated per-strike GEX snapshot ────────────────
            # gex/{root}.json above stays overwrite-in-place (consumers depend
            # on that key — UNCHANGED). Additionally retain the same payload
            # under a DATED key so per-strike topology survives as
            # point-in-time history for the Exposure-by-Strike scrubber +
            # S-TOPO-SIGMA (research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md §7
            # WP-GEX-SNAPSHOTS). Date = payload asof (session date), never
            # wall clock. Empty payloads (no by_strike rows) are never
            # written. INERT per root, like everything else in this loop.
            try:
                _hist_rel = _gex_history_relpath(root, gex_payload)
                if _hist_rel:
                    hist_path = out_dir / _hist_rel
                    _write_json(hist_path, gex_payload)
                    if s3 and bucket and gex_publish:
                        _upload_r2(s3, bucket, hist_path, f"{R2_PREFIX}{_hist_rel}")
            except Exception as _hist_err:  # noqa: BLE001
                log.warning(
                    "options_hub_builder: gex_history dated snapshot failed for %s — %s",
                    root, _hist_err,
                )

            # ── WP-A2.5: levels.v1 (named gamma-level board) ───────────────────
            # Translate the SAME gex payload into the named-level board — Anchor,
            # Call/Put walls, Flip, Cluster, Counter, Void, Trapdoor, Launchpad,
            # Stack — with the sticky/slippery color law and a plain-English note
            # per node, and publish levels/{root}.json for the Terminal Levels
            # board (Voltick Gamma-Levels program, WP-A2.5). This is a pure
            # downstream transform of gex_payload: the gex key above is unchanged
            # and this is INERT per root like everything else in this loop. Empty
            # boards (no by_strike rows) are never written.
            try:
                levels_payload = levels_payload_from_gex(gex_payload)
                if levels_payload is not None:
                    levels_path = out_dir / "levels" / f"{root}.json"
                    _write_json(levels_path, levels_payload)
                    if s3 and bucket and gex_publish:
                        _upload_r2(s3, bucket, levels_path,
                                   f"{LEVELS_PREFIX}{root}.json")
            except Exception as _lv_err:  # noqa: BLE001
                log.warning(
                    "options_hub_builder: levels publish failed for %s — %s",
                    root, _lv_err,
                )

            roots_ok.append(root)
            log.info(
                "options_hub_builder: %s done (%.1fs)", root,
                time.monotonic() - _root_start,
            )

        except Exception as e:  # noqa: BLE001
            log.warning("options_hub_builder: %s FAILED — %s", root, e)
            roots_skipped.append(root)

        finally:
            # Release per-root parquet cache after every root to bound peak memory.
            # Without this, the cache accumulates ALL year-files for ALL roots
            # (49 GB+ of greeks) which OOM-kills the process mid-universe.
            clear_parquet_cache()

        # ── incremental aggregate publish ──────────────────────────────────────
        # Publish cross-root aggregates from roots processed so far every
        # INCREMENTAL_N roots.  A mid-run death then degrades to N-root-stale feeds
        # rather than freezing all aggregates for the entire day.
        if len(roots_ok) >= _last_incremental + INCREMENTAL_N:
            _publish_aggregates(
                roots_ok=list(roots_ok),   # snapshot
                asof=asof,
                theta_store=theta_store,
                out_dir=out_dir,
                s3=s3,
                bucket=bucket,
                fear_greed_path=fear_greed_path,
                gex_latest_path=gex_latest_path,
                live_flow_out_dir=live_flow_out_dir,
                label=f"incremental@{len(roots_ok)}",
            )
            _last_incremental = len(roots_ok)

    # ── final cross-root payloads (full universe) ─────────────────────────────
    # This overwrites any incremental checkpoint with the complete universe.
    oi_movers_payload = _publish_aggregates(
        roots_ok=roots_ok,
        asof=asof,
        theta_store=theta_store,
        out_dir=out_dir,
        s3=s3,
        bucket=bucket,
        fear_greed_path=fear_greed_path,
        gex_latest_path=gex_latest_path,
        live_flow_out_dir=live_flow_out_dir,
        label="final",
    )

    # ── summary / completion sentinel ────────────────────────────────────────
    _total_roots = len(roots)
    _processed   = len(roots_ok) + len(roots_skipped) + len(roots_timeout)
    _is_partial  = (roots_skipped or roots_timeout or _processed < _total_roots)

    log.info(
        "options_hub_builder: COMPLETE asof=%s roots_ok=%d roots_skipped=%d "
        "roots_timeout=%d roots_gex_guarded=%d total=%d partial=%s",
        asof, len(roots_ok), len(roots_skipped), len(roots_timeout),
        len(roots_gex_skipped), _total_roots, _is_partial,
    )
    if roots_skipped:
        log.warning("options_hub_builder: error-skipped roots: %s", roots_skipped)
    if roots_timeout:
        log.warning("options_hub_builder: timeout-skipped roots: %s", roots_timeout)
    if roots_gex_skipped:
        log.warning(
            "options_hub_builder: GEX R2 upload suppressed (guard) for %d roots: %s",
            len(roots_gex_skipped), roots_gex_skipped,
        )

    # ── run_status ───────────────────────────────────────────────────────────
    # Register options_hub_nightly in the run_status/circuit-breaker pattern.
    # Mirrors the established pattern in scripts/collect.py + lib/store.write_status.
    try:
        from lib import store as _store         # noqa: PLC0415
        from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415
        _rs = _store.read_status()
        _rs.setdefault("sources", {})["options_hub_nightly"] = {
            "status":                "ok" if not _is_partial else "partial",
            "roots_ok":              len(roots_ok),
            "roots_skipped":         len(roots_skipped),
            "roots_timeout":         len(roots_timeout),
            "roots_gex_guarded":     len(roots_gex_skipped),
            "roots_gex_guarded_list": roots_gex_skipped,
            # CONTRACT v2 object counts
            "context_json":          "ok" if (out_dir / "context.json").exists() else "missing",
            "asof":                  asof,
            "checked_at":            _dt.now(_tz.utc).isoformat(),
        }
        _store.write_status(_rs)
        log.info("options_hub_builder: run_status updated")
    except Exception as _rs_err:   # noqa: BLE001
        log.debug("options_hub_builder: run_status write failed (non-fatal): %s", _rs_err)

    # ── exit code ────────────────────────────────────────────────────────────
    # Non-zero exit on partial run so launchd/monitoring surfaces the failure
    # rather than swallowing it silently.
    if _is_partial:
        sys.exit(2)


if __name__ == "__main__":
    main()
