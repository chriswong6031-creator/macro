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

  # Continuous loop
  python -m scripts.live_flow_poller

  # Override session date (market closed)
  python -m scripts.live_flow_poller --date 2026-07-02 --once

INERT semantics: root failures → skip + log, never abort the cycle.
NEVER raise max_concurrent above 2 without explicit Fable adjudication.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytz  # type: ignore[import-untyped]

from lib import config

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
ET = pytz.timezone("America/New_York")
PROBE_ROOT   = "SPY"        # root used for delta_mode probe
PROBE_WINDOW = 90           # seconds to subtract from "now" for time-windowed probe
ARCHIVE_HOUR_CADENCE = 3600  # write hourly archive every ~3600s

# R2 live_flow prefix
R2_PREFIX = "live_flow/"

# Out/state dirs (gitignored)
OUT_DIR   = "live_flow_out"
STATE_DIR = "live_flow_state"


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
    Errors are logged and (root, None, None) is returned — caller skips root.
    INERT: never raises.
    """
    from collectors import thetadata as td
    import pandas as pd

    try:
        kw: dict = {}
        if start_time:
            kw["start_time"] = start_time
        if end_time:
            kw["end_time"] = end_time

        calls = td.bulk_trade_quote(root, "call", session_date, session_date, **kw)
        puts  = td.bulk_trade_quote(root, "put",  session_date, session_date, **kw)
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


# ── state I/O ─────────────────────────────────────────────────────────────────

def _load_day_state(session_date: str) -> dict:
    p = _state_dir() / f"day_state_{session_date}.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
        # emitted_ids is serialised as a list
        raw["emitted_ids"] = set(raw.get("emitted_ids", []))
        # contract_vol and notability_history stored with string keys (JSON constraint);
        # restore to tuple keys for engine compatibility
        def _restore_key(k: str):
            try:
                parts = json.loads(k)
                if isinstance(parts, list) and len(parts) == 3:
                    return (str(parts[0]), float(parts[1]), str(parts[2]))
            except Exception:  # noqa: BLE001
                pass
            return k
        raw["contract_vol"] = {
            _restore_key(k): v for k, v in raw.get("contract_vol", {}).items()
        }
        raw["notability_history"] = {
            _restore_key(k): v for k, v in raw.get("notability_history", {}).items()
        }
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
        raw: dict = {}
        raw["emitted_ids"] = list(state.get("emitted_ids", set()))
        raw["all_events"]  = state.get("all_events", [])
        raw["root_gross_today"] = state.get("root_gross_today", {})
        # Tuple-keyed dicts → string-keyed for JSON serialisation
        raw["contract_vol"]      = {_state_key(k): v
                                    for k, v in state.get("contract_vol", {}).items()}
        raw["notability_history"] = {_state_key(k): v
                                     for k, v in state.get("notability_history", {}).items()}
        tmp = p.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(raw, default=str))
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
    cycle_watermarks: dict,   # {root: last_trade_ts_str} — mutated in place
) -> tuple[dict, dict, dict, list[str]]:
    """Run one poll cycle.  Returns (feed_data, heat_data, updated_day_state, meta_notes).

    Fetches all roots in parallel (max_concurrent=2), runs the engine, aggregates.
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

    # Determine time-window params
    start_time_param: str | None = None
    end_time_param: str | None   = None
    if delta_mode == "time_window":
        # Watermark minus 90s safety buffer
        now_et = datetime.now(ET)
        # go back PROBE_WINDOW=90s from now to get the watermark
        wm = now_et - timedelta(seconds=PROBE_WINDOW)
        start_time_param = wm.strftime("%H:%M:%S")
        end_time_param   = None  # up to "now"

    all_events: list[dict]  = list(day_state.get("all_events", []))
    root_gross: dict        = dict(day_state.get("root_gross_today", {}))
    emitted_ids: set[str]   = set(day_state.get("emitted_ids", set()))
    contract_vol: dict      = dict(day_state.get("contract_vol", {}))
    notab_hist: dict        = dict(day_state.get("notability_history", {}))

    heat_rows: list[dict]   = []
    unusual_by_root: dict   = {}
    meta_notes: list[str]   = []
    requests_count          = 0

    # Fetch in parallel (max_concurrent=2)
    fetch_results: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=max_w) as pool:
        futs = {
            pool.submit(_fetch_root, root, session_date, start_time_param, end_time_param): root
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

        # Per-root prior state
        prior = {
            "emitted_ids":      emitted_ids,
            "contract_vol":     contract_vol,
            "notability_history": notab_hist,
            "root_gross_today": root_gross,
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
            )
        except Exception as e:  # noqa: BLE001
            log.warning("poller: engine failed for %s: %s", root, e)
            continue

        # Merge state
        state_out = result.get("state", {})
        emitted_ids   = state_out.get("emitted_ids", emitted_ids)
        contract_vol  = state_out.get("contract_vol", contract_vol)
        notab_hist    = state_out.get("notability_history", notab_hist)
        root_gross    = state_out.get("root_gross_today", root_gross)

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
        notes.append("Incremental time-window pulls not supported on this terminal; "
                     "using full-day re-pull each cycle.")
    if truncated:
        notes.append(f"Events capped at {lf.MAX_EVENTS}; oldest dropped.")
    notes.extend(meta_notes)

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

    updated_state = {
        "all_events":         all_events,
        "emitted_ids":        emitted_ids,
        "contract_vol":       contract_vol,
        "notability_history": notab_hist,
        "root_gross_today":   root_gross,
    }

    return feed_payload, heat_payload, meta_payload, updated_state


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

def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    parser = argparse.ArgumentParser(description="Live options-flow poller")
    parser.add_argument("--once",  action="store_true", help="Single cycle then exit")
    parser.add_argument("--date",  metavar="YYYY-MM-DD",
                        help="Session date override (market-closed smokes)")
    parser.add_argument("--roots", nargs="+", metavar="ROOT",
                        help="Subset of roots (default: full universe)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Check terminal reachable
    from collectors import thetadata as td
    if not td.reachable():
        log.error("poller: Theta Terminal not reachable — abort")
        return 1

    cfg = _cfg()
    session_date = _session_date(args.date)
    log.info("poller: session_date=%s once=%s", session_date, args.once)

    # Resolve universe
    if args.roots:
        roots = [r.upper() for r in args.roots]
    else:
        roots = _resolve_universe(cfg)
    log.info("poller: universe=%d roots", len(roots))

    # delta_mode probe
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
            feed, heat, meta, updated_state = run_cycle(
                roots=roots,
                session_date=session_date,
                delta_mode=delta_mode,
                day_state=day_state,
                baselines=baselines,
                cfg=cfg,
                cycle_watermarks=watermarks,
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

        # Write local JSON
        feed_path = _write_json("feed_current.json", feed)
        heat_path = _write_json("heat_current.json", heat)
        meta_path = _write_json("meta.json", meta)

        log.info("poller: cycle #%d events=%d unusual=%d heat_groups=%d cycle_sec=%.1fs",
                 cycle_n,
                 len(feed.get("events", [])),
                 len(feed.get("unusual_names", [])),
                 len(heat.get("groups", [])),
                 meta.get("cycle_sec", 0))

        # Upload to R2
        if s3:
            _upload_r2(s3, bucket, feed_path, R2_PREFIX + "feed_current.json")
            _upload_r2(s3, bucket, heat_path, R2_PREFIX + "heat_current.json")
            _upload_r2(s3, bucket, meta_path, R2_PREFIX + "meta.json")

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

        # Sleep for remainder of cadence
        elapsed = time.perf_counter() - loop_t0
        sleep_for = max(0.0, cadence - elapsed)
        if sleep_for > 0:
            log.debug("poller: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)


if __name__ == "__main__":
    sys.exit(main())
