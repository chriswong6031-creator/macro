"""scripts/live_flow_poller.py — intraday options-flow polling driver.

Mac-side loop: fetches bulk_trade_quote per root per cycle, runs the live_flow
event engine, writes JSON artifacts locally and uploads to R2.

Config block 'live_flow:' in config.yml:
  cadence_sec:    120     # target poll interval
  max_concurrent: 2       # HARD LAW — T1 backfill shares the 8-request cap
  etf_anchors:    [...]   # defaults to build_tape_flow's 21 + DIA
  top_names:      100     # resolved from gex_symbols() after anchors
  etf_floor:      1000000 # $ gross premium floor for ETF anchors
  name_floor:     250000  # $ gross premium floor for single names
  retention_hours: 24     # trailing window for feed events

Usage:
  # Single cycle (smoke / testing)
  python -m scripts.live_flow_poller --once --date 2026-07-02 --roots SPY QQQ KRE

  # Single cycle with short retention (state-wipe smoke)
  python -m scripts.live_flow_poller --once --date 2026-07-02 --roots SPY QQQ --retention-hours 96

  # Continuous loop (RTH only — exits outside 09:25–16:05 ET on weekdays)
  python -m scripts.live_flow_poller --rth-only

  # Override session date (market closed)
  python -m scripts.live_flow_poller --date 2026-07-02 --once

INERT semantics: root failures → skip + log, never abort the cycle.
NEVER raise max_concurrent above 2 without explicit Fable adjudication.

New R2 objects emitted each cycle (live_flow/ prefix):
  tide_current.json       — market tide (NCP/NPP/gross/vol cumulative minutes + sectors)
  dte_tide_current.json   — DTE-bucket tide (5 buckets)
  tickers/{ROOT}.json     — per-root drill (top ~40 by day gross premium)
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import resource
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from lib import config

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
# Stdlib zoneinfo (repo convention, e.g. engine/options_flow.py) — no pytz dependency.
ET = ZoneInfo("America/New_York")
PROBE_ROOT   = "SPY"        # root used for delta_mode probe
PROBE_WINDOW = 90           # seconds to subtract from "now" for time-windowed probe
ARCHIVE_HOUR_CADENCE = 3600  # write hourly archive every ~3600s

# R2 live_flow prefix
R2_PREFIX = "live_flow/"

# Out/state dirs (gitignored)
OUT_DIR   = "live_flow_out"
STATE_DIR = "live_flow_state"

# Top tickers to publish per cycle (by day gross premium)
TOP_TICKERS_N = 40

# Day-state size guard: warn if exceeds this byte threshold
DAY_STATE_SIZE_WARN_BYTES = 50 * 1024 * 1024  # 50 MB

# RTH window (America/New_York) — poller active within this range
RTH_START_H, RTH_START_M = 9, 25     # 09:25 ET
RTH_END_H,   RTH_END_M   = 16, 5     # 16:05 ET

# Item 1b: per-root retry on None return — widen connect timeout and pause before skip.
# "terminal offline" may only be claimed after a direct probe with PROBE_CONNECT_TIMEOUT.
RETRY_CONNECT_TIMEOUT = 15   # seconds — wider connect for per-root retry
RETRY_PAUSE_SEC       = 5    # seconds — pause before retry

# Item 8: RSS logging threshold
RSS_WARN_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


# ── config access ─────────────────────────────────────────────────────────────

def _cfg() -> dict:
    """Return the live_flow config block (with defaults filled)."""
    try:
        return dict(config.load().get("live_flow", {}) or {})
    except Exception:  # noqa: BLE001
        return {}


def _r2_public_base() -> str:
    try:
        return config.load().get("r2_data_plane", {}).get("public_base", "")
    except Exception:  # noqa: BLE001
        return ""


# ── output paths ─────────────────────────────────────────────────────────────

def _out_dir() -> Path:
    p = config.data_dir() / OUT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_dir() -> Path:
    p = config.data_dir() / STATE_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── universe resolver ─────────────────────────────────────────────────────────

def _resolve_universe(cfg: dict) -> list[str]:
    """ETF anchors + top_names from gex_symbols(), deduped."""
    from engine.options_universe import gex_symbols

    default_anchors = [
        "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
        "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
        "KRE", "SMH", "XBI", "ARKK", "DIA",
    ]
    anchors = [a.upper() for a in (cfg.get("etf_anchors") or default_anchors)]
    top_n   = int(cfg.get("top_names", 100))

    seen: dict[str, None] = {}
    for t in anchors:
        seen.setdefault(t, None)

    try:
        gex = gex_symbols()
        for t in gex:
            seen.setdefault(t.upper(), None)
    except Exception as e:  # noqa: BLE001
        log.warning("poller: gex_symbols failed: %s", e)

    all_syms = list(seen)
    # Cap at anchors + top_n names after anchors
    return all_syms[: max(len(anchors), len(anchors) + top_n)]


# ── delta_mode probe ─────────────────────────────────────────────────────────

def _probe_delta_mode(session_date: str) -> str:
    """Determine whether time-filtered incremental pulls work on this terminal.

    Issues one SPY call bulk_trade_quote for the full day and one with a 15-min
    window near the end of the day.  If the time-filtered pull returns fewer rows
    (and > 0), delta_mode="time_window".  If it returns the same or more rows (or
    terminal doesn't support start_time), delta_mode="full_day".
    """
    from collectors import thetadata as td

    log.info("poller: probing delta_mode via SPY %s …", session_date)
    try:
        full = td.bulk_trade_quote(PROBE_ROOT, "call", session_date, session_date)
        if full is None or full.empty:
            log.info("poller: probe — no data for %s, defaulting to full_day", session_date)
            return "full_day"

        n_full = len(full)
        # Try a 15-minute window ending 15 minutes before close of trading (14:45 ET)
        win = td.bulk_trade_quote(
            PROBE_ROOT, "call", session_date, session_date,
            start_time="14:30:00", end_time="14:45:00",
        )
        if win is None:
            log.info("poller: probe — windowed pull failed, using full_day")
            return "full_day"

        n_win = len(win)
        log.info("poller: probe — full=%d window(14:30-14:45)=%d", n_full, n_win)
        if 0 < n_win < n_full:
            log.info("poller: delta_mode=time_window (time filter confirmed)")
            return "time_window"
        log.info("poller: delta_mode=full_day (window filter inconclusive)")
        return "full_day"
    except Exception as e:  # noqa: BLE001
        log.warning("poller: delta_mode probe failed: %s — defaulting full_day", e)
        return "full_day"


# ── per-root fetch ────────────────────────────────────────────────────────────

def _fetch_root(root: str, session_date: str,
                start_time: str | None, end_time: str | None
                ) -> tuple[str, object | None, object | None]:
    """Fetch call + put for one root.  Returns (root, calls_df, puts_df).

    Either may be None (terminal failure) or empty DataFrame (no trades).

    Item 1b — retry logic:
      If the first fetch returns None (terminal contention under ~360-root backfill
      saturates the 8-request ceiling), pause RETRY_PAUSE_SEC seconds then retry ONCE
      with RETRY_CONNECT_TIMEOUT (15s).  "terminal offline/unreachable" log may only be
      emitted after a direct probe with the wider timeout confirms the terminal is down.
      Otherwise log "terminal contended — root skipped after retry".

    INERT: never raises.
    """
    from collectors import thetadata as td

    try:
        cfg = _cfg()
        kw: dict = {}
        if start_time:
            kw["start_time"] = start_time
        if end_time:
            kw["end_time"] = end_time
        near_dte_cap = cfg.get("near_dte_cap_days", 90)
        if near_dte_cap is not None:
            kw["near_dte_cap_days"] = int(near_dte_cap)

        calls = td.bulk_trade_quote(root, "call", session_date, session_date, **kw)
        puts  = td.bulk_trade_quote(root, "put",  session_date, session_date, **kw)

        # Item 1b: if BOTH legs are None (not just empty) retry once with wider timeout
        if calls is None and puts is None:
            log.debug("poller: fetch returned None for %s — pausing %ds before retry",
                      root, RETRY_PAUSE_SEC)
            time.sleep(RETRY_PAUSE_SEC)
            calls = td.bulk_trade_quote(root, "call", session_date, session_date, **kw)
            puts  = td.bulk_trade_quote(root, "put",  session_date, session_date, **kw)

            if calls is None and puts is None:
                # Determine whether the terminal is genuinely offline
                terminal_up = td.reachable(connect_timeout=RETRY_CONNECT_TIMEOUT)
                if terminal_up:
                    log.warning("poller: terminal contended — root %s skipped after retry", root)
                else:
                    log.warning("poller: terminal offline/unreachable (probe with %ds timeout failed)"
                                " — root %s skipped after retry",
                                RETRY_CONNECT_TIMEOUT, root)
                return root, None, None

        return root, calls, puts
    except Exception as e:  # noqa: BLE001
        log.warning("poller: fetch failed for %s: %s", root, e)
        return root, None, None


# ── OI loader ────────────────────────────────────────────────────────────────

def _load_oi_prev(root: str, session_date: str) -> object | None:
    """Load t-1 OI from thetadata_eod; returns None gracefully."""
    try:
        from engine import thetadata_store as ts
        d_prev = datetime.strptime(session_date, "%Y-%m-%d").date() - timedelta(days=1)
        for _ in range(5):
            chain = ts.chain(str(d_prev), root.upper())
            if not chain.empty and "open_interest" in chain.columns:
                cols = [c for c in ("expiration", "strike", "right", "open_interest")
                        if c in chain.columns]
                return chain[cols].dropna(subset=["open_interest"])
            d_prev -= timedelta(days=1)
        return None
    except Exception as e:  # noqa: BLE001
        log.debug("poller: oi_prev failed for %s: %s", root, e)
        return None


# ── prior-session close loader (FIX 3 — moneyness) ───────────────────────────

def _load_prev_close(root: str, session_date: str) -> float | None:
    """Return the prior-session close for `root` from the yahoo store.

    Looks up data/yahoo/{ROOT}.parquet, takes the LAST row with date STRICTLY
    before session_date (never session_date itself — lookahead law).
    Returns None if the store is absent or no qualifying row exists.
    INERT: never raises — missing store must not crash a cycle.
    """
    try:
        from lib import store
        import pandas as pd

        safe_root = root.upper().replace("^", "_").replace("=", "_").replace("/", "_")
        df = store.read("yahoo", safe_root)
        if df is None or df.empty or "close" not in df.columns:
            return None
        sess_dt = pd.Timestamp(session_date)
        # Strictly before session_date — no lookahead
        prior = df[df.index < sess_dt]
        if prior.empty:
            return None
        last_close = prior["close"].iloc[-1]
        if pd.isna(last_close) or float(last_close) <= 0:
            return None
        return float(last_close)
    except Exception as e:  # noqa: BLE001
        log.debug("poller: prev_close failed for %s: %s", root, e)
        return None


# ── state I/O ─────────────────────────────────────────────────────────────────

def _load_day_state(session_date: str) -> dict:
    p = _state_dir() / f"day_state_{session_date}.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
        # Item 2: version check — discard day_state written by an older schema version.
        # full_day mode re-accumulates from zero so nothing is lost.
        # time_window mode also resets here; one full-day cycle follows before windowed
        # increments resume (watermarks start empty and full-day pull is safe).
        from engine.live_flow import DAY_STATE_VERSION  # noqa: PLC0415
        stored_ver = raw.get("schema_version", 1)
        if stored_ver < DAY_STATE_VERSION:
            log.info(
                "poller: day_state schema_version=%d < current=%d — discarding stale state "
                "(full_day mode will re-accumulate from zero this cycle)",
                stored_ver, DAY_STATE_VERSION,
            )
            return {}
        # emitted_ids is serialised as a list
        raw["emitted_ids"] = set(raw.get("emitted_ids", []))
        # contract_vol and notability_history stored with string keys (JSON constraint);
        # restore to tuple keys for engine compatibility
        def _restore_key(k: str):
            # 3-tuple contract keys: (exp:str, strike:float, right:str)
            try:
                parts = json.loads(k)
                if isinstance(parts, list) and len(parts) == 3:
                    return (str(parts[0]), float(parts[1]), str(parts[2]))
            except Exception:  # noqa: BLE001
                pass
            return k

        def _restore_seq_key(k: str):
            # seen_sequences keys are now 4-tuples: (root:str, exp:str, strike:float, right:str)
            # (schema_version>=2).  A 3-tuple key would be pre-v2 residue and is discarded
            # by the version gate above, so only the 4-tuple form is expected here.
            try:
                parts = json.loads(k)
                if isinstance(parts, list) and len(parts) == 4:
                    return (str(parts[0]), str(parts[1]), float(parts[2]), str(parts[3]))
            except Exception:  # noqa: BLE001
                pass
            return k
        raw["contract_vol"] = {
            _restore_key(k): v for k, v in raw.get("contract_vol", {}).items()
        }
        raw["notability_history"] = {
            _restore_key(k): v for k, v in raw.get("notability_history", {}).items()
        }
        raw["seen_sequences"] = {
            _restore_seq_key(k): v for k, v in raw.get("seen_sequences", {}).items()
        }
        # Tide accumulators — all string-keyed, load as-is
        for tide_key in ("market_tide_minutes", "sector_tide", "dte_tide",
                         "root_minutes", "root_strikes", "root_expiries",
                         "root_top_contracts", "sweep_clusters"):
            if tide_key not in raw:
                raw[tide_key] = {}
        return raw
    except Exception as e:  # noqa: BLE001
        log.warning("poller: could not load day state: %s", e)
        return {}


def _state_key(k) -> str:
    """Convert a tuple or other key to a JSON-safe string key."""
    if isinstance(k, (list, tuple)):
        return json.dumps([str(x) for x in k])
    return str(k)


def _save_day_state(session_date: str, state: dict) -> None:
    p = _state_dir() / f"day_state_{session_date}.json"
    try:
        from engine.live_flow import DAY_STATE_VERSION as _DSV  # noqa: PLC0415
        raw: dict = {}
        raw["schema_version"] = _DSV   # Item 2: stamp version for forward-compat checks
        raw["emitted_ids"] = list(state.get("emitted_ids", set()))
        raw["all_events"]  = state.get("all_events", [])
        raw["root_gross_today"] = state.get("root_gross_today", {})
        # Tuple-keyed dicts → string-keyed for JSON serialisation
        raw["contract_vol"]      = {_state_key(k): v
                                    for k, v in state.get("contract_vol", {}).items()}
        raw["notability_history"] = {_state_key(k): v
                                     for k, v in state.get("notability_history", {}).items()}
        raw["seen_sequences"]     = {_state_key(k): v
                                     for k, v in state.get("seen_sequences", {}).items()}
        # Tide accumulators — all string-keyed, serialise directly
        for tide_key in ("market_tide_minutes", "sector_tide", "dte_tide",
                         "root_minutes", "root_strikes", "root_expiries",
                         "root_top_contracts", "sweep_clusters"):
            raw[tide_key] = state.get(tide_key, {})

        serialised = json.dumps(raw, default=str)

        # Size guard: warn if day-state exceeds threshold
        byte_count = len(serialised.encode())
        if byte_count > DAY_STATE_SIZE_WARN_BYTES:
            log.warning(
                "poller: day_state size %d MB exceeds %d MB threshold — "
                "consider reducing top_names or retention_hours",
                byte_count // (1024 * 1024),
                DAY_STATE_SIZE_WARN_BYTES // (1024 * 1024),
            )

        tmp = p.with_suffix(".tmp.json")
        tmp.write_text(serialised)
        tmp.rename(p)
    except Exception as e:  # noqa: BLE001
        log.warning("poller: could not save day state: %s", e)


# ── JSON file writers ─────────────────────────────────────────────────────────

def _write_json(filename: str, obj: dict) -> Path:
    """Atomic write to data/live_flow_out/<filename>."""
    out = _out_dir() / filename
    tmp = out.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(obj, default=str))
    tmp.rename(out)
    return out


# ── R2 upload ─────────────────────────────────────────────────────────────────

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
        kw = dict(region_name="auto", signature_version="s3v4",
                  max_pool_connections=16,
                  retries={"max_attempts": 3, "mode": "standard"})
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep,
                            aws_access_key_id=ak,
                            aws_secret_access_key=sk,
                            config=cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("poller: R2 client build failed: %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    """Upload a local file to R2.  Returns True on success."""
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("poller: R2 upload ok → %s", r2_key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("poller: R2 upload failed for %s: %s", r2_key, e)
        return False


def _list_archive_keys(s3, bucket: str) -> list[str]:
    """List all keys under live_flow/archive/."""
    try:
        out, tok = [], None
        while True:
            kw: dict = {"Bucket": bucket, "Prefix": R2_PREFIX + "archive/"}
            if tok:
                kw["ContinuationToken"] = tok
            r = s3.list_objects_v2(**kw)
            for o in r.get("Contents", []):
                out.append(o["Key"])
            if not r.get("IsTruncated"):
                return out
            tok = r.get("NextContinuationToken")
    except Exception as e:  # noqa: BLE001
        log.warning("poller: list archive keys failed: %s", e)
        return []


def _prune_archive(s3, bucket: str, older_than_hours: int = 48) -> None:
    """Delete archive objects older than older_than_hours."""
    keys = _list_archive_keys(s3, bucket)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    to_delete = []
    for k in keys:
        # key format: live_flow/archive/YYYYMMDDTHH.json
        stem = Path(k).stem  # e.g. "2026070214"
        try:
            ts = datetime.strptime(stem, "%Y%m%dT%H").replace(tzinfo=timezone.utc)
            if ts < cutoff:
                to_delete.append(k)
        except Exception:  # noqa: BLE001
            pass
    if to_delete:
        try:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in to_delete]})
            log.info("poller: pruned %d archive objects older than %dh", len(to_delete), older_than_hours)
        except Exception as e:  # noqa: BLE001
            log.warning("poller: archive prune failed: %s", e)


# ── baseline loader ───────────────────────────────────────────────────────────

def _load_baselines() -> dict:
    p = config.data_dir() / "live_flow_baselines" / "baselines.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("poller: could not load baselines: %s", e)
        return {}


# ── session date ─────────────────────────────────────────────────────────────

def _session_date(override: str | None = None) -> str:
    """Return session date as YYYY-MM-DD.

    Uses America/New_York to determine the current date during market hours.
    --date override for closed-market smokes.
    """
    if override:
        return override
    return datetime.now(ET).strftime("%Y-%m-%d")


# ── single-cycle logic ────────────────────────────────────────────────────────

def run_cycle(
    roots: list[str],
    session_date: str,
    delta_mode: str,
    day_state: dict,
    baselines: dict,
    cfg: dict,
    cycle_watermarks: dict,   # FIX 2: {root: {"ts": str, "seq": float}} — mutated in place
    forced_full_day: bool = False,  # True when --date override forces full_day regardless of probe
) -> tuple[dict, dict, dict, dict, dict]:
    """Run one poll cycle.  Returns (feed_data, heat_data, meta_data, updated_day_state, tide_day_state).

    Fetches all roots in parallel (max_concurrent=2), runs the engine, aggregates.

    FIX 2 — per-root watermarks + overlap dedup:
      cycle_watermarks[root] = {"ts": last_trade_ts_str, "seq": max_sequence_seen}
      time_window mode: start_time = watermark_ts - 30s overlap (RTH open on first cycle).
      Row-level dedup inside the engine (seen_sequences state) makes overlap safe.
      full_day mode: always pulls full day; engine dedup ensures idempotency.

    FIX 3 — prev_close loaded per-root from yahoo store for honest moneyness.
    """
    from engine import live_flow as lf
    import pandas as pd

    max_w = int(cfg.get("max_concurrent", 2))
    etf_floor  = int(cfg.get("etf_floor",  1_000_000))
    name_floor = int(cfg.get("name_floor",  250_000))

    etf_anchors = [a.upper() for a in (cfg.get("etf_anchors") or [])]
    if not etf_anchors:
        from scripts.live_flow_poller import _resolve_universe
        etf_anchors_set = set(_resolve_universe(cfg)[:23])  # rough default
    else:
        etf_anchors_set = set(etf_anchors)

    batch_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cycle_t0 = time.perf_counter()

    # FIX 2 — compute per-root start_time for time_window mode
    # For full_day mode start_time is always None (pull full day; dedup handles idempotency)
    RTH_OPEN = "09:30:00"
    _OVERLAP_SEC = 30   # 30s overlap safety window

    def _root_start_time(root: str) -> str | None:
        """Return start_time for this root's fetch, or None (full day)."""
        if delta_mode != "time_window":
            return None
        wm = cycle_watermarks.get(root)
        if not wm or not wm.get("ts"):
            # First cycle for this root → start from RTH open
            return RTH_OPEN
        # Advance watermark by subtracting overlap
        try:
            wm_dt = datetime.fromisoformat(wm["ts"].replace("Z", "+00:00"))
            wm_et = wm_dt.astimezone(ET)
            overlap_dt = wm_et - timedelta(seconds=_OVERLAP_SEC)
            return overlap_dt.strftime("%H:%M:%S")
        except Exception:  # noqa: BLE001
            return RTH_OPEN

    all_events: list[dict]  = list(day_state.get("all_events", []))
    root_gross: dict        = dict(day_state.get("root_gross_today", {}))
    emitted_ids: set[str]   = set(day_state.get("emitted_ids", set()))
    contract_vol: dict      = dict(day_state.get("contract_vol", {}))
    notab_hist: dict        = dict(day_state.get("notability_history", {}))
    seen_sequences: dict    = dict(day_state.get("seen_sequences", {}))

    # Tide accumulator state — carry forward across cycles
    market_tide_minutes: dict = dict(day_state.get("market_tide_minutes", {}))
    sector_tide: dict         = {k: dict(v) for k, v in day_state.get("sector_tide", {}).items()}
    dte_tide: dict            = {k: dict(v) for k, v in day_state.get("dte_tide", {}).items()}
    root_minutes_acc: dict    = {k: dict(v) for k, v in day_state.get("root_minutes", {}).items()}
    root_strikes_acc: dict    = {k: dict(v) for k, v in day_state.get("root_strikes", {}).items()}
    root_expiries_acc: dict   = {k: dict(v) for k, v in day_state.get("root_expiries", {}).items()}
    root_top_contr: dict      = {k: list(v) for k, v in day_state.get("root_top_contracts", {}).items()}
    sweep_clusters_acc: dict  = dict(day_state.get("sweep_clusters", {}))

    heat_rows: list[dict]   = []
    unusual_by_root: dict   = {}
    meta_notes: list[str]   = []
    requests_count          = 0

    # Fetch in parallel (max_concurrent=2); per-root start_time in time_window mode
    fetch_results: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=max_w) as pool:
        futs = {
            pool.submit(
                _fetch_root, root, session_date,
                _root_start_time(root),   # per-root watermark start
                None,                     # end_time always None ("now")
            ): root
            for root in roots
        }
        for fut in as_completed(futs):
            r, calls_df, puts_df = fut.result()
            fetch_results[r] = (calls_df, puts_df)
            requests_count += 2  # two calls per root (call + put)

    # Process each root
    for root in roots:
        calls_df, puts_df = fetch_results.get(root, (None, None))
        if calls_df is None and puts_df is None:
            log.debug("poller: skip %s (both legs failed)", root)
            continue

        # FIX 2 — advance per-root watermark from trade_timestamp in returned rows
        # (done before the engine call so a crash mid-root doesn't lose the watermark)
        for df_part in (calls_df, puts_df):
            if df_part is not None and not df_part.empty and "trade_timestamp" in df_part.columns:
                try:
                    import pandas as pd
                    max_ts = df_part["trade_timestamp"].dropna().max()
                    max_seq_val = None
                    if "sequence" in df_part.columns:
                        max_seq_val = float(pd.to_numeric(
                            df_part["sequence"], errors="coerce").dropna().max())
                    if max_ts and str(max_ts) not in ("NaT", "nan", ""):
                        wm_cur = cycle_watermarks.get(root, {})
                        cur_ts  = wm_cur.get("ts")
                        if cur_ts is None or str(max_ts) > cur_ts:
                            wm_new = {"ts": str(max_ts)}
                            if max_seq_val is not None and not (max_seq_val != max_seq_val):
                                wm_new["seq"] = max_seq_val
                            cycle_watermarks[root] = wm_new
                except Exception as e:  # noqa: BLE001
                    log.debug("poller: watermark advance failed for %s: %s", root, e)

        # FIX 3 — load prev_close for honest moneyness
        prev_close = _load_prev_close(root, session_date)

        # Per-root prior state — pass ALL accumulators so the engine starts from the
        # running cross-root total rather than empty dicts.  The engine deep-copies each
        # dict on entry (lines 399-416 of live_flow.py), so passing the live references
        # here is safe — no aliasing hazard between concurrent workers because fetch is
        # already done (parallel phase is over) and processing is sequential.
        prior = {
            "emitted_ids":      emitted_ids,
            "contract_vol":     contract_vol,
            "notability_history": notab_hist,
            "root_gross_today": root_gross,
            "seen_sequences":   seen_sequences,
            # FIX: tide accumulators were missing — each root was starting fresh and the
            # last root's result was overwriting all prior roots' data (drop-all bug).
            "market_tide_minutes": market_tide_minutes,
            "sector_tide":         sector_tide,
            "dte_tide":            dte_tide,
            "root_minutes":        root_minutes_acc,
            "root_strikes":        root_strikes_acc,
            "root_expiries":       root_expiries_acc,
            "root_top_contracts":  root_top_contr,
            "sweep_clusters":      sweep_clusters_acc,
        }

        try:
            oi_prev = _load_oi_prev(root, session_date)
            result  = lf.process_batch(
                calls_df=calls_df,
                puts_df=puts_df,
                session_date=session_date,
                batch_ts=batch_ts,
                prior_state=prior,
                oi_prev=oi_prev,
                baselines=baselines,
                etf_floor=etf_floor,
                name_floor=name_floor,
                etf_anchors=list(etf_anchors_set),
                prev_close=prev_close,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("poller: engine failed for %s: %s", root, e)
            continue

        # Merge state
        state_out = result.get("state", {})
        emitted_ids     = state_out.get("emitted_ids", emitted_ids)
        contract_vol    = state_out.get("contract_vol", contract_vol)
        notab_hist      = state_out.get("notability_history", notab_hist)
        root_gross      = state_out.get("root_gross_today", root_gross)
        seen_sequences  = state_out.get("seen_sequences", seen_sequences)

        # Merge tide accumulators (engine returns updated dicts mutated in-place)
        market_tide_minutes = state_out.get("market_tide_minutes", market_tide_minutes)
        sector_tide         = state_out.get("sector_tide", sector_tide)
        dte_tide            = state_out.get("dte_tide", dte_tide)
        root_minutes_acc    = state_out.get("root_minutes", root_minutes_acc)
        root_strikes_acc    = state_out.get("root_strikes", root_strikes_acc)
        root_expiries_acc   = state_out.get("root_expiries", root_expiries_acc)
        root_top_contr      = state_out.get("root_top_contracts", root_top_contr)
        sweep_clusters_acc  = state_out.get("sweep_clusters", sweep_clusters_acc)

        # Accumulate new events
        for ev in result.get("events", []):
            all_events.append(ev)

        # Heat rows
        heat_rows.extend(result.get("heat", []))

        # Unusual names (latest per root)
        for un in result.get("unusual_names", []):
            r2 = un.get("root", root)
            if r2:
                unusual_by_root[r2] = un

        meta_notes.extend(result.get("meta_notes", []))

        # Item 8 — free per-root frames after processing to cap intraday memory growth.
        del calls_df, puts_df, result
        fetch_results[root] = (None, None)  # release DataFrame references

    # Periodic GC after processing all roots (Item 8)
    gc.collect()

    # 24h retention trim
    retention_h = int(cfg.get("retention_hours", 24))
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=retention_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_events = lf.trim_events(all_events, cutoff_ts)

    # Aggregate heat across roots
    agg_heat = lf.aggregate_heat(heat_rows)

    # Enrich unusual_names with group labels
    unusual_list: list[dict] = []
    for root, un in unusual_by_root.items():
        from engine.live_flow import _root_to_group, _load_names_sectors
        ns = _load_names_sectors()
        grp_en, grp_zh = _root_to_group(root, ns)
        un["group"]    = grp_en
        un["group_zh"] = grp_zh
        # Fill call_prem_share from heat rows
        for hr in heat_rows:
            if hr.get("_root") == root:
                un["call_prem_share"] = round(float(hr.get("call_prem_share", 0.0)), 4)
                break
        unusual_list.append(un)

    # Sort unusual by |prem_z| desc, then by gross_premium_today desc
    def _un_sort_key(u: dict):
        pz = u.get("prem_z")
        return (abs(pz) if pz is not None else 0.0, u.get("gross_premium_today", 0.0))
    unusual_list.sort(key=_un_sort_key, reverse=True)

    cycle_sec = time.perf_counter() - cycle_t0

    # Build feed payload
    n_events = len(all_events)
    truncated = n_events >= lf.MAX_EVENTS

    baseline_note_ready = sum(1 for b in baselines.values()
                               if b.get("std") and float(b["std"]) > 0)
    notes: list[str] = []
    if baseline_note_ready == 0:
        notes.append("No EOD-252 baselines ready; floor gate only. "
                     "Run build_live_flow_baselines to enable z-scores.")
    else:
        notes.append(f"{baseline_note_ready} roots have EOD-252 baselines.")
    if delta_mode == "full_day":
        if forced_full_day:
            notes.append("Historical session — full-day mode forced (--date override).")
        else:
            notes.append("Incremental time-window pulls not supported on this terminal; "
                         "using full-day re-pull each cycle.")
    if truncated:
        notes.append(f"Events capped at {lf.MAX_EVENTS}; oldest dropped.")
    # Deduplicate meta_notes: same note from N roots appears only once
    seen_notes: set[str] = set()
    for note in meta_notes:
        if note not in seen_notes:
            seen_notes.add(note)
            notes.append(note)

    feed_payload = {
        "schema":       "live_flow.feed/v1",
        "asof":         batch_ts,
        "session_date": session_date,
        "session_pct":  _session_pct(),
        "baseline_note": {
            "en": notes[0] if notes else "",
            "zh": notes[0] if notes else "",  # same text; no translation
        },
        "events":         all_events,
        "unusual_names":  unusual_list,
    }

    heat_payload = {
        "schema":       "live_flow.heat/v1",
        "asof":         batch_ts,
        "session_date": session_date,
        "groups":       agg_heat,
    }

    meta_payload = {
        "schema":                "live_flow.meta/v1",
        "asof":                  batch_ts,
        "cadence_sec_target":    int(cfg.get("cadence_sec", 120)),
        "cadence_sec_measured":  round(cycle_sec, 1),
        "universe_n":            len(roots),
        "roots_polled":          len(fetch_results),
        "requests_last_cycle":   requests_count,
        "cycle_sec":             round(cycle_sec, 1),
        "delta_mode":            delta_mode,
        "notes":                 notes,
    }

    # Build compound day_state for tide JSON builders
    tide_day_state = {
        "market_tide_minutes": market_tide_minutes,
        "sector_tide":         sector_tide,
        "dte_tide":            dte_tide,
        "root_minutes":        root_minutes_acc,
        "root_strikes":        root_strikes_acc,
        "root_expiries":       root_expiries_acc,
        "root_top_contracts":  root_top_contr,
        "root_gross_today":    root_gross,
    }

    updated_state = {
        "all_events":         all_events,
        "emitted_ids":        emitted_ids,
        "contract_vol":       contract_vol,
        "notability_history": notab_hist,
        "root_gross_today":   root_gross,
        "seen_sequences":     seen_sequences,
        # Tide accumulators
        "market_tide_minutes": market_tide_minutes,
        "sector_tide":         sector_tide,
        "dte_tide":            dte_tide,
        "root_minutes":        root_minutes_acc,
        "root_strikes":        root_strikes_acc,
        "root_expiries":       root_expiries_acc,
        "root_top_contracts":  root_top_contr,
        "sweep_clusters":      sweep_clusters_acc,
    }

    return feed_payload, heat_payload, meta_payload, updated_state, tide_day_state


def _session_pct() -> float:
    """Fraction of the 6.5h trading session elapsed (0–1).  Clamped [0,1]."""
    try:
        now = datetime.now(ET)
        open_et  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_et = now.replace(hour=16, minute=0,  second=0, microsecond=0)
        total    = (close_et - open_et).total_seconds()
        elapsed  = (now - open_et).total_seconds()
        return round(max(0.0, min(1.0, elapsed / total)), 4)
    except Exception:  # noqa: BLE001
        return 0.0


# ── main loop ─────────────────────────────────────────────────────────────────

def _within_rth() -> bool:
    """True if the current America/New_York time is within RTH window (09:25–16:05)
    on a weekday.  Never raises — returns False on any error.
    """
    try:
        now = datetime.now(ET)
        if now.weekday() >= 5:          # Saturday=5, Sunday=6
            return False
        t = now.hour * 60 + now.minute  # minutes since midnight ET
        start = RTH_START_H * 60 + RTH_START_M   # 565
        end   = RTH_END_H   * 60 + RTH_END_M     # 965
        return start <= t <= end
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    parser = argparse.ArgumentParser(description="Live options-flow poller")
    parser.add_argument("--once",  action="store_true", help="Single cycle then exit")
    parser.add_argument("--date",  metavar="YYYY-MM-DD",
                        help="Session date override (market-closed smokes)")
    parser.add_argument("--roots", nargs="+", metavar="ROOT",
                        help="Subset of roots (default: full universe)")
    parser.add_argument("--retention-hours", type=int, default=None,
                        metavar="N",
                        help="Override retention_hours from config (smoke aid, e.g. 96)")
    parser.add_argument("--rth-only", action="store_true",
                        help="Exit cleanly outside 09:25-16:05 ET on weekdays "
                             "(use with launchd StartCalendarInterval)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # --rth-only: exit immediately if outside RTH (launchd fires at 09:25, daemon must
    # self-exit at 16:05; StartCalendarInterval fires again next day at 09:25).
    if args.rth_only and not _within_rth():
        log.info("poller: --rth-only outside RTH window — exiting cleanly")
        return 0

    # Check terminal reachable — startup probe uses a tolerant 15s default so a
    # slow-starting ThetaTerminal doesn't abort the poller unnecessarily.
    # Override via THETA_CONNECT_TIMEOUT env (same variable that controls the
    # per-root retry timeout in thetadata.py).
    from collectors import thetadata as td
    startup_timeout = int(os.environ.get("THETA_CONNECT_TIMEOUT", "15"))
    if not td.reachable(connect_timeout=startup_timeout):
        log.error("poller: Theta Terminal not reachable — abort")
        return 1

    cfg = _cfg()

    # --retention-hours CLI override
    if args.retention_hours is not None:
        cfg["retention_hours"] = args.retention_hours
        log.info("poller: retention_hours overridden to %d (CLI)", args.retention_hours)

    session_date = _session_date(args.date)
    log.info("poller: session_date=%s once=%s", session_date, args.once)

    # Resolve universe
    if args.roots:
        roots = [r.upper() for r in args.roots]
    else:
        roots = _resolve_universe(cfg)
    log.info("poller: universe=%d roots", len(roots))

    # FIX 2 — historical smokes (--date override) must use full_day:
    # time-windowed pulls anchored to a live clock make no sense on a past session.
    if args.date:
        delta_mode = "full_day"
        log.info("poller: delta_mode=full_day (forced — historical --date override)")
    else:
        delta_mode = _probe_delta_mode(session_date)
        log.info("poller: delta_mode=%s", delta_mode)

    # Load baselines (static for the session)
    baselines = _load_baselines()
    n_baselines = len(baselines)
    log.info("poller: loaded %d baseline entries", n_baselines)

    # R2 setup
    bucket = os.environ.get("R2_BUCKET", "")
    s3 = _r2_client()
    if not s3:
        log.warning("poller: R2 creds absent — uploads will be skipped")
    elif not bucket:
        log.warning("poller: R2_BUCKET not set — uploads will be skipped")
        s3 = None

    # Day state (persist emitted_ids, contract_vol, etc.)
    day_state  = _load_day_state(session_date)
    watermarks: dict = {}
    last_archive_write = 0.0
    cadence   = int(cfg.get("cadence_sec", 120))

    cycle_n = 0
    while True:
        loop_t0 = time.perf_counter()
        cycle_n += 1
        log.info("poller: cycle #%d starting (date=%s delta_mode=%s)",
                 cycle_n, session_date, delta_mode)

        try:
            feed, heat, meta, updated_state, tide_day_state = run_cycle(
                roots=roots,
                session_date=session_date,
                delta_mode=delta_mode,
                day_state=day_state,
                baselines=baselines,
                cfg=cfg,
                cycle_watermarks=watermarks,
                forced_full_day=bool(args.date),
            )
        except Exception as e:  # noqa: BLE001
            log.error("poller: cycle #%d unhandled error: %s", cycle_n, e, exc_info=True)
            if args.once:
                return 1
            time.sleep(cadence)
            continue

        day_state = updated_state
        _save_day_state(session_date, {
            k: (list(v) if isinstance(v, set) else v)
            for k, v in day_state.items()
        })

        # Write legacy JSON
        feed_path = _write_json("feed_current.json", feed)
        heat_path = _write_json("heat_current.json", heat)
        meta_path = _write_json("meta.json", meta)

        # ── Build and write tide JSON objects ─────────────────────────────────
        from engine import live_flow as lf_mod
        from engine.live_flow import _load_names_sectors

        tide_payload = lf_mod.build_tide_current(
            session_date=session_date,
            asof=meta.get("asof", feed.get("asof", "")),
            day_state=tide_day_state,
            spy_minute_prices=[],   # spy series: omit (no clean intraday spot source)
        )
        dte_tide_payload = lf_mod.build_dte_tide_current(
            session_date=session_date,
            asof=meta.get("asof", feed.get("asof", "")),
            day_state=tide_day_state,
        )
        tide_path     = _write_json("tide_current.json", tide_payload)
        dte_tide_path = _write_json("dte_tide_current.json", dte_tide_payload)

        # Build ticker JSONs for top ~40 roots by gross premium
        ns_map  = _load_names_sectors()
        rg_dict = tide_day_state.get("root_gross_today", {})
        top_roots_by_gross = sorted(rg_dict.items(), key=lambda kv: kv[1], reverse=True)
        ticker_count = 0
        ticker_paths: list[tuple[Path, str]] = []  # (local_path, r2_key)
        _tickers_out_dir = _out_dir() / "tickers"
        _tickers_out_dir.mkdir(parents=True, exist_ok=True)

        for tick_root, _ in top_roots_by_gross[:TOP_TICKERS_N]:
            try:
                tk_payload = lf_mod.build_ticker_json(
                    root=tick_root,
                    session_date=session_date,
                    asof=meta.get("asof", feed.get("asof", "")),
                    day_state=tide_day_state,
                    root_gross_today=rg_dict,
                    baselines=baselines,
                    names_sectors=ns_map,
                )
                # Skip empty payloads — minutes=0 AND strikes=0 means no data landed for
                # this root (e.g. fetch failed under contention); publishing an empty file
                # would overwrite a valid prior-cycle file with stale zeros.
                n_min = len(tk_payload.get("minutes", []))
                n_str = len(tk_payload.get("strikes", []))
                if n_min == 0 and n_str == 0:
                    log.info("poller: skip empty ticker JSON for %s (minutes=0, strikes=0)",
                             tick_root)
                    continue
                tk_file = tick_root.upper().replace(".", "_") + ".json"
                tk_local = _tickers_out_dir / tk_file
                tmp_tk = tk_local.with_suffix(".tmp.json")
                tmp_tk.write_text(json.dumps(tk_payload, default=str))
                tmp_tk.rename(tk_local)
                ticker_paths.append((tk_local, R2_PREFIX + f"tickers/{tick_root.upper()}.json"))
                ticker_count += 1
            except Exception as tk_err:  # noqa: BLE001
                log.warning("poller: ticker JSON failed for %s: %s", tick_root, tk_err)

        roots_ok_n    = meta.get("roots_polled", 0)
        roots_total_n = meta.get("universe_n", len(roots))
        roots_skip_n  = roots_total_n - roots_ok_n

        log.info("poller: cycle #%d events=%d unusual=%d heat_groups=%d "
                 "minutes=%d sectors=%d tickers=%d cycle_sec=%.1fs",
                 cycle_n,
                 len(feed.get("events", [])),
                 len(feed.get("unusual_names", [])),
                 len(heat.get("groups", [])),
                 len(tide_payload.get("minutes", [])),
                 len(tide_payload.get("sectors", [])),
                 ticker_count,
                 meta.get("cycle_sec", 0))

        # Item 6 — register live_flow_poller in the run_status/circuit-breaker pattern.
        # Mirrors the established pattern in scripts/collect.py + lib/store.write_status.
        # Writes a 'live_flow_poller' entry under sources with ok/roots_ok/roots_skipped/asof.
        try:
            from lib import store as _store   # noqa: PLC0415
            _rs = _store.read_status()
            _rs.setdefault("sources", {})["live_flow_poller"] = {
                "status":        "ok",
                "roots_ok":      roots_ok_n,
                "roots_skipped": roots_skip_n,
                "asof":          meta.get("asof", ""),
                "cycle_n":       cycle_n,
                "checked_at":    datetime.now(timezone.utc).isoformat(),
            }
            _store.write_status(_rs)
        except Exception as _rs_err:  # noqa: BLE001
            log.debug("poller: run_status write failed (non-fatal): %s", _rs_err)

        # Item 8 — peak-RSS logging (>2 GB triggers a meta note).
        try:
            rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS: ru_maxrss is in bytes; Linux: kilobytes.
            import platform as _plat  # noqa: PLC0415
            if _plat.system() == "Linux":
                rss_bytes *= 1024
            if rss_bytes > RSS_WARN_BYTES:
                log.warning(
                    "poller: cycle #%d peak RSS %.1f GB exceeds 2 GB threshold",
                    cycle_n, rss_bytes / (1024 ** 3),
                )
                meta.setdefault("notes", []).append(
                    f"peak RSS {rss_bytes / (1024**3):.1f} GB > 2 GB threshold — "
                    "consider reducing universe or retention_hours"
                )
        except Exception as _rss_err:  # noqa: BLE001
            log.debug("poller: RSS check failed (non-fatal): %s", _rss_err)

        # Upload to R2
        if s3:
            _upload_r2(s3, bucket, feed_path, R2_PREFIX + "feed_current.json")
            _upload_r2(s3, bucket, heat_path, R2_PREFIX + "heat_current.json")
            _upload_r2(s3, bucket, meta_path, R2_PREFIX + "meta.json")
            _upload_r2(s3, bucket, tide_path,     R2_PREFIX + "tide_current.json")
            _upload_r2(s3, bucket, dte_tide_path, R2_PREFIX + "dte_tide_current.json")
            for tk_local, tk_r2_key in ticker_paths:
                _upload_r2(s3, bucket, tk_local, tk_r2_key)

            # Hourly archive
            now_ts  = time.time()
            if now_ts - last_archive_write >= ARCHIVE_HOUR_CADENCE:
                hour_key = datetime.now(timezone.utc).strftime("%Y%m%dT%H")
                archive_local = _write_json(f"archive_{hour_key}.json", feed)
                _upload_r2(s3, bucket, archive_local,
                           R2_PREFIX + f"archive/{hour_key}.json")
                last_archive_write = now_ts
                _prune_archive(s3, bucket, older_than_hours=48)

        if args.once:
            log.info("poller: --once flag set — exiting after one cycle")
            return 0

        # --rth-only: exit at end of each cycle once outside RTH
        if args.rth_only and not _within_rth():
            log.info("poller: --rth-only outside RTH window — exiting cleanly")
            return 0

        # Sleep for remainder of cadence
        elapsed = time.perf_counter() - loop_t0
        sleep_for = max(0.0, cadence - elapsed)
        if sleep_for > 0:
            log.debug("poller: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)


if __name__ == "__main__":
    sys.exit(main())
