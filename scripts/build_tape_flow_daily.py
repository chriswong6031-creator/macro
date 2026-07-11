"""scripts/build_tape_flow_daily.py — T2a tape-flow feature builder.

Wildcard-bulk per-root-per-day signed-flow feature aggregation from ThetaData trade+NBBO tape.
Implements the shape ratified by research/T2A_THROUGHPUT_PROBE.md §7 and ruling R6-RESOLVED.

Modes (--mode):
  forward      : prior trading day, full gex_symbols() universe (~360 roots). Nightly.
  episodes     : Tier-S episode windows 2022→, ±15d, from data/oracle/episodes_s.parquet.
                 Only ETF anchors (11 nodes from post-2022 episodes). R6 priority 2.
  etf-history  : 20 ETF anchors, full history 2017→. R6 priority 3.

Storage:
  Daily features : data/tape_flow/daily/<ROOT>.parquet  (1 row/day, tiny, git-committable)
  Raw tape        : data/tape_flow/raw/_manifest.json   (manifest only; bytes on R2-plane)
  State file      : data/tape_flow/_state.json          (resumability + round-robin cursor)

Concurrency:
  2 while backfill_thetadata_eod is alive (pgrep guard, house law)
  6 otherwise (leaves 2 of 8 terminal slots as headroom)

Round-robin resume (forward mode):
  The state file records a cursor (index into the gex_symbols() list) so each nightly run
  starts where the previous budget-limited run left off.  Every root in the universe accrues
  data over time even when the nightly budget is shorter than a full-universe sweep.

Usage:
  python -m scripts.build_tape_flow_daily --mode forward
  python -m scripts.build_tape_flow_daily --mode episodes
  python -m scripts.build_tape_flow_daily --mode etf-history --start 2017-01-01
  python -m scripts.build_tape_flow_daily --mode forward --roots SPY --date 2026-07-02
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Allow running as `python -m scripts.build_tape_flow_daily`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("build_tape_flow_daily")

# ── ETF anchors (mirrors backfill_thetadata_eod.ETF_ANCHORS) ─────────────────
ETF_ANCHORS: list[str] = [
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLI", "XLU", "XLV", "XLY", "XLP", "XLB", "XLC", "XLRE",
    "SMH", "SOXX", "XBI", "KRE", "ARKK",
]
assert len(ETF_ANCHORS) == 20, "ETF_ANCHORS must have exactly 20 elements"

ETF_ANCHOR_SET = set(ETF_ANCHORS)

# Episodes mode: only the ETF anchor nodes that appear in post-2022 Tier-S episodes.
# Measured in T2A_THROUGHPUT_PROBE.md §5: 11 distinct nodes post-2022.
EPISODE_ROOTS = ETF_ANCHOR_SET  # use full ETF set; episode_nodes() filters dynamically

# History start for etf-history mode (R6 priority 3 — aligns with IV availability)
ETF_HISTORY_START = date(2017, 1, 1)

# Raw tape retention: ETF anchors + episode windows only
RAW_RETENTION_ROOTS = ETF_ANCHOR_SET


# ── concurrency guard ─────────────────────────────────────────────────────────
def _backfill_alive() -> bool:
    """True if backfill_thetadata_eod is running (pgrep check, house law).

    When the backfill is alive it owns 6 of 8 terminal slots; we cap at 2.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "backfill_thetadata_eod"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False  # assume not running if check fails


def _max_workers() -> int:
    """2 if backfill is alive, else 6 (leaves 2 of 8 terminal slots free)."""
    return 2 if _backfill_alive() else 6


# ── trading calendar ──────────────────────────────────────────────────────────
def _prior_trading_day(ref: date | None = None) -> date:
    """Return the most recent trading day before or equal to ref (default: today).

    Simple rule: skip weekends. Does not exclude US holidays (acceptable for a
    near-miss; empty-response from API is handled gracefully).
    """
    d = ref or date.today()
    d -= timedelta(days=1)   # at least 1 day back
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def _trading_days_in_range(start: date, end: date) -> list[date]:
    """Return all weekday dates in [start, end] inclusive (simple; no holiday calendar)."""
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


# ── state file ────────────────────────────────────────────────────────────────
def _state_dir() -> Path:
    from lib import config
    p = config.data_dir() / "tape_flow"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path() -> Path:
    return _state_dir() / "_state.json"


def _load_state() -> dict:
    p = _state_path()
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        pass
    return {"completed": {}}   # {mode: {root: [date_str, ...]}}


def _save_state(state: dict) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    os.replace(tmp, p)


def _is_done(state: dict, mode: str, root: str, trade_date: date) -> bool:
    return str(trade_date) in state.get("completed", {}).get(mode, {}).get(root.upper(), [])


def _mark_done(state: dict, mode: str, root: str, trade_date: date) -> None:
    completed = state.setdefault("completed", {})
    by_mode = completed.setdefault(mode, {})
    root_list = by_mode.setdefault(root.upper(), [])
    ds = str(trade_date)
    if ds not in root_list:
        root_list.append(ds)
        root_list.sort()


# ── round-robin cursor (forward mode) ─────────────────────────────────────────
# The forward-mode universe (~360-400 roots) takes 13 min at 6-concurrent or ~30
# min at 2-concurrent (when backfill is alive).  With a budget cap, the same
# leading roots would complete every night while trailing roots never accrue.
# The cursor remembers the starting offset into gex_symbols() so each nightly
# run begins where the previous one left off, distributing coverage fairly.

def _load_cursor(state: dict, mode: str) -> int:
    """Return the last-saved cursor position (default 0)."""
    return int(state.get("cursors", {}).get(mode, 0))


def _save_cursor(state: dict, mode: str, cursor: int) -> None:
    """Persist the cursor position into the state dict (caller must _save_state)."""
    state.setdefault("cursors", {})[mode] = cursor


def _rotate_work(work: list[tuple], cursor: int) -> list[tuple]:
    """Rotate work list so index `cursor` is the new head.

    The rotated order ensures every root eventually reaches the front of the
    queue across successive budget-limited nightly runs.
    """
    if not work or cursor <= 0:
        return work
    cursor = cursor % len(work)
    return work[cursor:] + work[:cursor]


# ── feature store helpers ─────────────────────────────────────────────────────
def _daily_store_dir() -> Path:
    from lib import config
    p = config.data_dir() / "tape_flow" / "daily"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _raw_manifest_path() -> Path:
    from lib import config
    p = config.data_dir() / "tape_flow" / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p / "_manifest.json"


def _read_daily(root: str) -> pd.DataFrame:
    p = _daily_store_dir() / f"{root.upper()}.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("build_tape_flow_daily: read_daily(%s) failed — %s", root, e)
        return pd.DataFrame()


def _upsert_daily(root: str, row: dict) -> None:
    """Idempotent: replace the row for row['date'] in the per-root daily parquet."""
    from engine.tape_flow import upsert_feature_row, add_zscores
    p = _daily_store_dir() / f"{root.upper()}.parquet"
    existing = _read_daily(root)
    combined = upsert_feature_row(existing, row)
    # Recompute z-scores on every upsert (cheap; derived quantity)
    combined = add_zscores(combined)
    tmp = p.with_suffix(".tmp")
    combined.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, p)


def _update_raw_manifest(root: str, trade_date: date, rows: int, bytes_approx: int) -> None:
    """Record that a raw tape was written to R2 for this root+date."""
    mp = _raw_manifest_path()
    try:
        manifest: dict = json.loads(mp.read_text()) if mp.exists() else {}
    except Exception:  # noqa: BLE001
        manifest = {}
    entries = manifest.get(root.upper(), [])
    ds = str(trade_date)
    entries = [e for e in entries if e.get("date") != ds]
    entries.append({"date": ds, "rows": rows, "bytes_approx": bytes_approx})
    entries.sort(key=lambda e: e["date"])
    manifest[root.upper()] = entries
    tmp = mp.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    os.replace(tmp, mp)


# ── OI prior-day lookup ───────────────────────────────────────────────────────
def _get_prior_oi(root: str, trade_date: date) -> pd.DataFrame | None:
    """Load OI[t-1] for the given root and trade_date.

    OI timing law (thetadata.py doc + OPRA spec): OI[t] published ~06:30 ET =
    positions as of EOD t-1. So for a trade on day t, prior OI = OI[t-1]
    which is stored in the t-1 date's EOD row. We look up in the thetadata_eod
    OI store for the calendar day before trade_date.
    """
    from lib import config
    prior_date = trade_date - timedelta(days=1)
    # Skip weekends
    while prior_date.weekday() >= 5:
        prior_date -= timedelta(days=1)

    oi_root_dir = config.data_dir() / "thetadata_eod" / "oi" / root.upper()
    if not oi_root_dir.exists():
        return None

    year_file = oi_root_dir / f"{prior_date.year}.parquet"
    if not year_file.exists():
        return None

    try:
        df = pd.read_parquet(year_file)
        # Normalize date column
        if "timestamp" in df.columns:
            df["_date"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.normalize()
        elif "date" in df.columns:
            df["_date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
        else:
            return None
        row = df[df["_date"] == pd.Timestamp(prior_date)]
        if row.empty:
            return None
        return row[["expiration", "strike", "right", "open_interest"]].copy()
    except Exception as e:  # noqa: BLE001
        log.debug("build_tape_flow_daily: OI lookup (%s, %s) failed — %s", root, trade_date, e)
        return None


# ── greeks chain lookup ───────────────────────────────────────────────────────
def _get_greeks_chain(root: str, trade_date: date) -> pd.DataFrame | None:
    """Load per-contract greeks (including underlying_price) for the given root+date.

    Used for delta-notional flow and underlying_price (moneyness). Returns None
    if the store is absent or the date is not covered.
    """
    from lib import config
    greeks_root_dir = config.data_dir() / "thetadata_eod" / "greeks" / root.upper()
    if not greeks_root_dir.exists():
        return None

    year_file = greeks_root_dir / f"{trade_date.year}.parquet"
    if not year_file.exists():
        return None

    try:
        df = pd.read_parquet(year_file)
        if "timestamp" in df.columns:
            df["_date"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.normalize()
        elif "date" in df.columns:
            df["_date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
        else:
            return None
        row = df[df["_date"] == pd.Timestamp(trade_date)]
        if row.empty:
            return None
        keep = [c for c in ("expiration", "strike", "right", "delta", "underlying_price")
                if c in row.columns]
        return row[keep].copy()
    except Exception as e:  # noqa: BLE001
        log.debug("build_tape_flow_daily: greeks lookup (%s, %s) failed — %s", root, trade_date, e)
        return None


# ── single root-day worker ────────────────────────────────────────────────────
def _process_root_day(root: str, trade_date: date, mode: str,
                      retain_raw: bool = False) -> dict:
    """Pull, aggregate, and store features for one root+date.

    Returns a status dict for the run_status registration.
    No-partial contract: if either leg (call/put) fails, returns error status.
    """
    from collectors.thetadata import bulk_trade_quote
    from engine.tape_flow import aggregate_day

    t0 = time.perf_counter()
    log.info("tape_flow: %s %s pulling tape …", root, trade_date)

    # Pull both legs (2 requests per root-day; right=* → HTTP 400, so call+put separately)
    calls_df = bulk_trade_quote(root, "call", trade_date, trade_date)
    if calls_df is None:
        log.warning("tape_flow: %s %s call leg failed — skipping", root, trade_date)
        return {"root": root, "date": str(trade_date), "status": "error", "reason": "call_leg_failed"}

    puts_df = bulk_trade_quote(root, "put", trade_date, trade_date)
    if puts_df is None:
        log.warning("tape_flow: %s %s put leg failed — skipping", root, trade_date)
        return {"root": root, "date": str(trade_date), "status": "error", "reason": "put_leg_failed"}

    # OI[t-1] and greeks chain for joined features
    oi_prev = _get_prior_oi(root, trade_date)
    greeks = _get_greeks_chain(root, trade_date)

    # Aggregate features
    row = aggregate_day(
        calls=calls_df,
        puts=puts_df,
        trade_date=trade_date,
        root=root,
        oi_prev=oi_prev,
        greeks_chain=greeks,
    )

    # Upsert into daily store
    _upsert_daily(root, row)

    elapsed = time.perf_counter() - t0
    total_rows = (len(calls_df) if not calls_df.empty else 0) + \
                 (len(puts_df) if not puts_df.empty else 0)

    # Raw tape retention: manifest only (bytes on R2-plane)
    if retain_raw and total_rows > 0:
        raw_calls = calls_df.memory_usage(deep=True).sum() if not calls_df.empty else 0
        raw_puts = puts_df.memory_usage(deep=True).sum() if not puts_df.empty else 0
        _update_raw_manifest(root, trade_date, rows=total_rows,
                             bytes_approx=int(raw_calls + raw_puts))

    log.info("tape_flow: %s %s done — rows=%d elapsed=%.1fs", root, trade_date, total_rows, elapsed)
    return {
        "root": root,
        "date": str(trade_date),
        "status": "ok",
        "rows": total_rows,
        "elapsed_sec": round(elapsed, 1),
        "net_signed_premium": row.get("net_signed_premium"),
        "gross_premium": row.get("gross_premium"),
        "volume": row.get("volume"),
        "trade_count": row.get("trade_count"),
    }


# ── episode window loader ─────────────────────────────────────────────────────
def _episode_root_days(episode_root_filter: set[str] | None = None) -> list[tuple[str, date]]:
    """Load Tier-S episodes (post-2022) and expand to ±15d windows.

    Source: data/oracle/episodes_s.parquet, paired/onset columns.
    Only ETF anchor roots are used (per R6 priority 2 scope).
    Returns list of (root, date) tuples, deduplicated.
    """
    from lib import config
    ep_path = config.data_dir() / "oracle" / "episodes_s.parquet"
    if not ep_path.exists():
        log.warning("tape_flow: episodes_s.parquet not found — skipping episode mode")
        return []

    try:
        ep = pd.read_parquet(ep_path)
    except Exception as e:  # noqa: BLE001
        log.warning("tape_flow: could not read episodes_s.parquet — %s", e)
        return []

    EPISODE_ONSET_FLOOR = date(2022, 1, 1)  # Tier-M options-era onset floor per O-OPT prereg R3

    # Collect all episode date columns (onset, paired, etc.)
    date_cols = [c for c in ep.columns if c in ("onset", "paired", "start_date", "end_date", "date")]
    if not date_cols:
        log.warning("tape_flow: episodes_s.parquet has no recognised date columns: %s", list(ep.columns))
        return []

    # Resolve roots: episodes may have a 'node' or 'root' column; use ETF anchors as the
    # options target (sector episodes → sector ETF equivalent).
    # For now use all ETF anchors for every episode window (safe over-coverage; dedup handles it).
    root_set = episode_root_filter or ETF_ANCHOR_SET

    seen: set[tuple[str, date]] = set()
    results: list[tuple[str, date]] = []
    WINDOW = 15  # ±15 calendar days

    for _, ep_row in ep.iterrows():
        # Get episode reference date (onset or paired)
        for col in date_cols:
            val = ep_row.get(col)
            if pd.isna(val):
                continue
            try:
                ep_date = pd.Timestamp(val).date()
            except Exception:  # noqa: BLE001
                continue
            if ep_date < EPISODE_ONSET_FLOOR:
                continue
            # Expand ±15d
            for day_offset in range(-WINDOW, WINDOW + 1):
                window_date = ep_date + timedelta(days=day_offset)
                if window_date.weekday() >= 5:  # skip weekends
                    continue
                if window_date < EPISODE_ONSET_FLOOR:
                    continue
                if window_date > date.today():
                    continue
                for root in root_set:
                    key = (root, window_date)
                    if key not in seen:
                        seen.add(key)
                        results.append(key)

    log.info("tape_flow: episode mode expanded to %d root-day combinations", len(results))
    return results


# ── run_status registration ───────────────────────────────────────────────────
def _register_run_status(mode: str, n_ok: int, n_err: int, elapsed_sec: float,
                         last_date: str) -> None:
    """Register this run in data/run_status.json per P0.7 pattern."""
    from lib import config
    rs_path = config.data_dir() / "run_status.json"
    try:
        rs: dict = json.loads(rs_path.read_text()) if rs_path.exists() else {}
    except Exception:  # noqa: BLE001
        rs = {}
    sources = rs.setdefault("sources", {})
    sources[f"tape_flow_{mode}"] = {
        "status": "ok" if n_ok > 0 else ("error" if n_err > 0 else "empty"),
        "n_ok": n_ok,
        "n_err": n_err,
        "elapsed_sec": round(elapsed_sec, 1),
        "last_date": last_date,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
    }
    tmp = rs_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rs, indent=2))
    os.replace(tmp, rs_path)
    log.info("tape_flow: registered run_status[tape_flow_%s] n_ok=%d n_err=%d", mode, n_ok, n_err)


# ── audit tripwire ────────────────────────────────────────────────────────────
def _audit_store(root: str, trade_date: date) -> dict:
    """Verify the just-written row is readable and has the expected date.

    Returns dict with 'ok' bool and 'reason' string. P0.7 pattern.
    """
    df = _read_daily(root)
    if df.empty:
        return {"ok": False, "reason": "store empty after write"}
    if "date" not in df.columns:
        return {"ok": False, "reason": "no date column"}
    dates = df["date"].astype(str)
    if str(trade_date) not in dates.values:
        return {"ok": False, "reason": f"{trade_date} not found in store (rows={len(df)})"}
    return {"ok": True, "reason": "ok"}


# ── main ──────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="T2a tape-flow feature builder")
    parser.add_argument(
        "--mode", choices=["forward", "episodes", "etf-history"],
        default="forward",
        help="forward=prior trading day; episodes=Tier-S ±15d; etf-history=ETF anchors 2017→",
    )
    parser.add_argument(
        "--roots", default=None,
        help="Comma-separated root override (e.g. SPY,QQQ). Overrides mode universe.",
    )
    parser.add_argument(
        "--date", default=None,
        help="Target date override YYYY-MM-DD (forward mode only).",
    )
    parser.add_argument(
        "--start", default=None,
        help="Start date YYYY-MM-DD for etf-history mode (default: 2017-01-01).",
    )
    parser.add_argument(
        "--end", default=None,
        help="End date YYYY-MM-DD for etf-history mode (default: today).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-run even if state marks the root-day as completed.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the root-day work plan without pulling or writing.",
    )
    parser.add_argument(
        "--no-audit", action="store_true",
        help="Skip store audit tripwire (for smoke-test performance).",
    )
    parser.add_argument(
        "--budget-minutes", type=float, default=None, metavar="N",
        help=(
            "Hard-stop after N minutes (wall-clock from process start). "
            "Saves state after every completed root-day so the next run resumes. "
            "Budget-exceeded exit is clean (exit 0); intended for CI nightly steps. "
            "For forward mode the default is 15 minutes if not specified."
        ),
    )
    args = parser.parse_args(argv)

    # [timing] t0 — process entry
    t_global = time.perf_counter()
    _tick_prev = [t_global]

    def _tick(label: str) -> None:
        """Emit a [timing] log line for profiling nightly lane performance."""
        _now = time.perf_counter()
        log.info("[timing] %-36s +%6.1fs (cum %7.1fs)",
                 label, _now - _tick_prev[0], _now - t_global)
        _tick_prev[0] = _now

    from collectors.thetadata import reachable
    if not reachable():
        log.warning("tape_flow: ThetaData terminal not reachable — exiting gracefully")
        _tick("reachable-check (MISS)")
        sys.exit(0)
    _tick("reachable-check (OK)")

    state = _load_state()

    # ── forward-mode default budget ───────────────────────────────────────────
    # Without a budget the forward step can run 9-31 min (6 vs 2 workers), leaving
    # insufficient room for episodes(30)+etf-history(20) in the 100-min job ceiling.
    # Default: 15 min for forward mode.
    #
    # Runtime math (at 2-concurrent, backfill alive):
    #   375-root universe serial ≈ 1,851s → at 2-concurrent ≈ 20 min total.
    #   15 min covers ~2/3 of the universe on night one (~150 roots).
    #   The round-robin cursor (now load-bearing) ensures the remaining ~1/3
    #   reaches the head of the queue on night two — full universe ≈ every 2 nights.
    #
    # At 6-concurrent (backfill absent): ~7 min → all 375 roots fit in one night.
    #
    # Residual job-ceiling tightness: episodes (30 min) and etf-history (20 min)
    # are pre-existing budgets this PR does not change. Forward(15) + episodes(30) +
    # etf-history(20) + collectors/finviz(~35) = ~100 min — exactly at the
    # timeout-minutes:100 ceiling. Any overrun in episodes or etf-history may still
    # cause the job to be cancelled by CI.
    _forward_default_budget: float | None = 15.0
    if args.mode == "forward" and args.budget_minutes is None:
        args.budget_minutes = _forward_default_budget
        log.info(
            "tape_flow: forward mode — applying default budget %.0f min "
            "(pass --budget-minutes N to override)",
            args.budget_minutes,
        )

    # ── build work list ───────────────────────────────────────────────────────
    if args.roots:
        root_override = [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    else:
        root_override = None

    work: list[tuple[str, date]] = []  # (root, trade_date)
    retain_raw_set: set[str] = set()
    _cursor_key: str = args.mode   # state cursor key

    if args.mode == "forward":
        if args.date:
            trade_date = date.fromisoformat(args.date)
        else:
            trade_date = _prior_trading_day()
        from engine.options_universe import gex_symbols
        roots = root_override or gex_symbols()
        work_all = [(r, trade_date) for r in roots]
        # Round-robin: rotate by the saved cursor so each nightly run starts at a
        # different root, ensuring the full universe accrues data over multiple nights.
        if not root_override:
            saved_cursor = _load_cursor(state, _cursor_key)
            work_all = _rotate_work(work_all, saved_cursor)
        work = work_all
        # Raw retention: ETF anchors only in forward mode
        retain_raw_set = ETF_ANCHOR_SET

    elif args.mode == "episodes":
        pairs = _episode_root_days(
            episode_root_filter=set(root_override) if root_override else None)
        work = pairs
        retain_raw_set = set()  # episode backfill: features only (no raw retention here)

    elif args.mode == "etf-history":
        start = date.fromisoformat(args.start) if args.start else ETF_HISTORY_START
        end = date.fromisoformat(args.end) if args.end else date.today()
        roots = root_override or ETF_ANCHORS
        trading_days = _trading_days_in_range(start, end)
        work = [(r, d) for r in roots for d in trading_days]
        retain_raw_set = ETF_ANCHOR_SET  # full raw retention for ETF history

    n_total = len(work)

    # Filter already-completed root-days (unless --force)
    if not args.force:
        work = [(r, d) for r, d in work
                if not _is_done(state, args.mode, r, d)]

    n_skipped = n_total - len(work)
    workers = _max_workers()
    log.info(
        "tape_flow: mode=%s universe=%d skipped=%d pending=%d "
        "max_workers=%d (backfill_alive=%s) budget=%.0fmin",
        args.mode, n_total, n_skipped, len(work),
        workers, _backfill_alive(),
        args.budget_minutes if args.budget_minutes is not None else -1,
    )
    _tick("work-list build")

    if args.dry_run:
        for root, d in work[:20]:
            print(f"  DRY-RUN: {root} {d}")
        if len(work) > 20:
            print(f"  … and {len(work) - 20} more")
        return

    if not work:
        log.info("tape_flow: nothing to do (all completed or empty universe)")
        _register_run_status(args.mode, 0, 0, 0.0, str(date.today()))
        return

    # ── budget deadline ───────────────────────────────────────────────────────
    # --budget-minutes: hard-stop after N wall-clock minutes so the CI step
    # never overruns its slot.  State is persisted after every completed
    # root-day, so the next nightly run resumes where we left off.
    budget_deadline: float | None = (
        t_global + args.budget_minutes * 60.0
        if args.budget_minutes is not None
        else None
    )

    # ── concurrent execution ──────────────────────────────────────────────────
    n_ok = 0
    n_err = 0
    budget_exceeded = False
    last_date = str(date.today())
    # Track how many work items were actually submitted before budget-stop
    n_attempted = 0

    # BUDGET-ENFORCEMENT NOTE (fix for submit-all flaw):
    # Submitting all work upfront then breaking as_completed loop does NOT hard-stop
    # the executor — ThreadPoolExecutor.__exit__ calls shutdown(wait=True) which
    # drains ALL submitted futures regardless of the break.  Fix: submit work in
    # batches of size=workers and check the budget before submitting the next batch.
    # This bounds the overshoot to at most (workers) in-flight tasks past the deadline.
    BATCH_SIZE = workers  # one batch = one "wave" of concurrent requests

    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        work_iter = iter(work)
        pending: dict = {}   # future → (root, trade_date)

        def _fill_pending() -> None:
            """Submit up to BATCH_SIZE new tasks to keep the executor busy."""
            while len(pending) < BATCH_SIZE:
                try:
                    root, td = next(work_iter)
                except StopIteration:
                    break
                nonlocal n_attempted
                n_attempted += 1
                fut = executor.submit(_process_root_day, root, td, args.mode,
                                      root in retain_raw_set)
                pending[fut] = (root, td)

        _fill_pending()  # seed the first batch

        while pending:
            # Wait for any one future in the current batch to complete
            done_futures, _ = wait(
                pending.keys(),
                return_when=FIRST_COMPLETED,
            )
            for future in done_futures:
                root, td = pending.pop(future)
                try:
                    result = future.result()
                except Exception as e:  # noqa: BLE001
                    log.warning("tape_flow: %s %s raised unexpected error — %s", root, td, e)
                    result = {"root": root, "date": str(td),
                              "status": "error", "reason": str(e)}

                if result.get("status") == "ok":
                    n_ok += 1
                    last_date = result.get("date", last_date)
                    _mark_done(state, args.mode, root, td)
                    _save_state(state)

                    # Audit tripwire (P0.7)
                    if not args.no_audit:
                        audit = _audit_store(root, td)
                        if not audit["ok"]:
                            log.warning("tape_flow: audit FAILED %s %s — %s",
                                        root, td, audit["reason"])
                else:
                    n_err += 1
                    log.warning("tape_flow: %s %s %s — %s",
                                result.get("status", "error"), root, td,
                                result.get("reason", "unknown"))

            # Hard-stop: check budget BEFORE submitting the next batch.
            # This ensures we never start new work past the deadline.
            if budget_deadline is not None and time.perf_counter() >= budget_deadline:
                log.info(
                    "tape_flow: budget %.1f min exceeded after n_ok=%d — "
                    "draining already-done futures, cancelling queued ones, saving state; "
                    "next run resumes from remaining work",
                    args.budget_minutes, n_ok,
                )
                budget_exceeded = True
                # Drain any futures that already finished (their parquet rows were
                # already written by the worker thread; record them before cancelling
                # so their _mark_done calls are not lost).
                for f in list(pending.keys()):
                    if f.done():
                        root_d, td_d = pending.pop(f)
                        try:
                            res_d = f.result()
                        except Exception as e_d:  # noqa: BLE001
                            res_d = {"root": root_d, "date": str(td_d),
                                     "status": "error", "reason": str(e_d)}
                        if res_d.get("status") == "ok":
                            n_ok += 1
                            last_date = res_d.get("date", last_date)
                            _mark_done(state, args.mode, root_d, td_d)
                            _save_state(state)
                        else:
                            n_err += 1
                # Cancel remaining queued-but-not-started futures (Python 3.9+)
                for f in list(pending.keys()):
                    f.cancel()
                break

            # Refill: submit more work to keep workers busy
            _fill_pending()

    finally:
        # Shut down the executor; wait=True so in-flight (non-cancelled) tasks finish
        # cleanly before we write final state.  cancel_futures=True tells the executor
        # to drop anything still in its queue that was not explicitly cancelled above.
        executor.shutdown(wait=True, cancel_futures=True)

    # ── round-robin cursor advance (forward mode) ────────────────────────────
    # Advance the cursor by the number of PROCESSED (actually completed-and-recorded)
    # items this run, not by n_attempted/submitted.  Orphaned or cancelled submissions
    # that were never recorded must not advance the cursor past unrecorded roots —
    # otherwise those roots would be silently skipped on the next run.
    n_processed = n_ok + n_err   # roots whose result was received and _mark_done called
    if args.mode == "forward" and not args.roots and n_processed > 0:
        old_cursor = _load_cursor(state, _cursor_key)
        new_cursor = (old_cursor + n_processed) % max(n_total, 1)
        _save_cursor(state, _cursor_key, new_cursor)
        _save_state(state)
        log.info("tape_flow: forward cursor advanced %d → %d (universe=%d, processed=%d)",
                 old_cursor, new_cursor, n_total, n_processed)

    elapsed = time.perf_counter() - t_global
    _tick("execution complete")

    # ── outcome summary (one parseable line for log grep / monitoring) ────────
    outcome = "BUDGET-STOP" if budget_exceeded else "COMPLETE"
    log.info(
        "tape_flow OUTCOME mode=%s status=%s "
        "attempted=%d succeeded=%d skipped=%d failed=%d elapsed=%.1fs",
        args.mode, outcome, n_attempted, n_ok, n_skipped, n_err, elapsed,
    )

    _register_run_status(args.mode, n_ok, n_err, elapsed, last_date)


if __name__ == "__main__":
    main()
