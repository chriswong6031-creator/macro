"""scripts/chain_snapshot_poller.py — U-CHAIN intraday chain-snapshot lane.

Mac-side RTH loop: every cadence_min minutes (default 15) it sweeps the active
options universe (~150 roots: 22 ETF anchors + top gex names) and pulls a
full-chain greeks snapshot per root via the ThetaData v3 snapshot API —
first_order (delta/theta/vega/rho/IV) + second_order (gamma/vanna/charm/
vomma/veta) — joined on the contract key and appended to per-root per-day
parquet frames.  This is the Interval Map / Volatility Drift data plane
(research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md §5 U-CHAIN, WP-UCHAIN).

Config block 'chain_snapshots:' in config.yml:
  cadence_min:    15    # minutes between sweep starts
  top_names:      128   # single-name roots appended after the 22 ETF anchors
  max_concurrent: 1     # HARD — live_flow poller owns 2 of the terminal's 8 during RTH

Output layout (data/chain_snapshots/, gitignored like the other live lanes):
  {ROOT}/{YYYY-MM-DD}.parquet     — greeks rows, dedup key = (root, expiration,
                                    strike, right, snapshot_bucket)
  {ROOT}/{YYYY-MM-DD}_oi.parquet  — one OI snapshot per root per DAY (first
                                    sweep only; skipped when the sidecar exists,
                                    so restarts never re-pull).  OI TIMING LAW:
                                    snapshot OI is stamped ~06:30 ET and holds
                                    EOD t-1 positions — it does NOT update
                                    intraday, so one pull is complete.
  _meta.json                      — per-cycle run status (sweeps, rows, latency,
                                    errors, quarantined) for tripwires/observability
  {ROOT}/{date}.corrupt-{ts}.parquet — quarantined unreadable day frame (bytes
                                    preserved for recovery, never overwritten;
                                    surfaced in _meta.json "quarantined")

Sweep bucket: sweep-start ET wall time floored to the cadence grid ("HH:MM"),
so re-runs inside the same interval dedup instead of duplicating rows.

Data source tag: rows from this lane carry source="chain_snapshot" — a NEW
source with its own cohort; never pooled with live_flow / EOD-store cohorts.

STORE-RESOLVER NOTE (WP-RESOLVER): this lane performs no thetadata_eod store
READS — it only writes its own data/chain_snapshots/ plane — so the canonical
engine.thetadata_store.resolve_thetadata_store chain is not engaged here.
Any future consumer that joins these frames against the EOD store must go
through the resolver.

Usage:
  # Single sweep (smoke / structural verification; market closed returns
  # last-known close-ish snapshots — timestamps carry the truth)
  python -m scripts.chain_snapshot_poller --once --roots SPY MSFT WDC

  # Continuous loop (RTH only — waits for 09:35 ET when fired early,
  # self-exits after 16:00 ET on weekdays)
  python -m scripts.chain_snapshot_poller --rth-only

INERT semantics: root failures → skip + log, never abort the sweep.
Concurrency: max_concurrent=1 is a HARD cap — the live_flow poller owns 2 of
the terminal's 8 concurrent slots during RTH and T1 backfill uses the rest.
NEVER raise it without explicit Fable adjudication.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
ET = ZoneInfo("America/New_York")

# RTH window (America/New_York) — first sweep 09:35 ET (5 min after the open so
# the chain has real prints), last sweep no later than 16:00 ET.
RTH_START_H, RTH_START_M = 9, 35     # 09:35 ET
RTH_END_H,   RTH_END_M   = 16, 0     # 16:00 ET

# --rth-only fired before the window (launchd fires 06:30 PT = 09:30 ET): wait
# up to this long for the window to open instead of exiting.
PRE_RTH_MAX_WAIT_SEC = 30 * 60

# Output dir under data/ (gitignored, like live_flow_out/)
OUT_DIR = "chain_snapshots"
META_FILE = "_meta.json"

# Contract key + sweep-bucket dedup key for the per-day parquet
CONTRACT_KEY = ["root", "expiration", "strike", "right"]
DEDUP_KEY = CONTRACT_KEY + ["snapshot_bucket"]

# Second-order columns joined onto the first-order base (the second-order
# response also carries bid/ask/IV — those come from the first-order frame).
SECOND_ORDER_JOIN_COLS = ["gamma", "vanna", "charm", "vomma", "veta"]

# Cap on error strings kept in _meta.json per cycle
META_MAX_ERRORS = 20


# ── config access ─────────────────────────────────────────────────────────────

def _cfg() -> dict:
    """Return the chain_snapshots config block (defaults filled by callers)."""
    try:
        return dict(config.load().get("chain_snapshots", {}) or {})
    except Exception:  # noqa: BLE001
        return {}


def _max_concurrent(cfg: dict) -> int:
    """Resolve max_concurrent (default 1).

    HARD LAW: the live_flow poller owns 2 of the ThetaData terminal's 8
    concurrent request slots during RTH and the T1 backfill shares the rest.
    This lane's budget is 1.  NEVER raise without explicit Fable adjudication.
    """
    return max(1, int(cfg.get("max_concurrent", 1)))


def _out_root() -> Path:
    p = config.data_dir() / OUT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── universe resolver (live_flow_poller._resolve_universe pattern) ───────────

def _resolve_universe(cfg: dict) -> list[str]:
    """ETF anchors + top_names from gex_symbols(), deduped, anchors first."""
    from engine.options_universe import gex_symbols

    default_anchors = [
        "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
        "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
        "KRE", "SMH", "XBI", "ARKK", "DIA",
    ]
    anchors = [a.upper() for a in (cfg.get("etf_anchors") or default_anchors)]
    top_n   = int(cfg.get("top_names", 128))

    seen: dict[str, None] = {}
    for t in anchors:
        seen.setdefault(t, None)

    try:
        gex = gex_symbols()
        for t in gex:
            seen.setdefault(t.upper(), None)
    except Exception as e:  # noqa: BLE001
        log.warning("chainsnap: gex_symbols failed: %s", e)

    all_syms = list(seen)
    # Cap at anchors + top_n names after anchors
    return all_syms[: max(len(anchors), len(anchors) + top_n)]


# ── sweep-bucket derivation ───────────────────────────────────────────────────

def derive_bucket(now_et: datetime, cadence_min: int) -> str:
    """Floor an ET wall-clock time to the cadence grid → "HH:MM" bucket label.

    Anchored at midnight ET so buckets are deterministic across restarts
    (09:35 with cadence 15 → "09:30"; 16:00 → "16:00").  Re-running a sweep
    inside the same interval lands in the same bucket and dedups away.
    """
    cadence_min = max(1, int(cadence_min))
    minutes = now_et.hour * 60 + now_et.minute
    floored = (minutes // cadence_min) * cadence_min
    return f"{floored // 60:02d}:{floored % 60:02d}"


# ── first+second order join ───────────────────────────────────────────────────

def join_orders(first_df: pd.DataFrame, second_df: pd.DataFrame | None) -> pd.DataFrame:
    """Left-join second-order greek columns onto the first-order base frame.

    The first-order frame is the base (its snapshot_ts/bid/ask/IV win); only
    SECOND_ORDER_JOIN_COLS are taken from the second-order frame.  Both sides
    are deduped on the contract key first so a duplicated contract row can
    never multiply rows.  A missing/failed second-order frame degrades to
    NaN second-order columns (INERT — the first-order data still lands).
    """
    base = first_df.drop_duplicates(subset=CONTRACT_KEY, keep="first")

    if second_df is None or second_df.empty:
        out = base.copy()
        for col in SECOND_ORDER_JOIN_COLS:
            if col not in out.columns:
                out[col] = float("nan")   # float64 NaN — keeps parquet dtypes stable
        return out.reset_index(drop=True)

    right = second_df.drop_duplicates(subset=CONTRACT_KEY, keep="first")
    join_cols = [c for c in SECOND_ORDER_JOIN_COLS if c in right.columns]
    out = base.merge(right[CONTRACT_KEY + join_cols], on=CONTRACT_KEY, how="left")
    for col in SECOND_ORDER_JOIN_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out.reset_index(drop=True)


# ── parquet append (dedup on contract key + snapshot bucket) ─────────────────

def day_parquet_path(root: str, session_date: str) -> Path:
    d = _out_root() / root.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{session_date}.parquet"


def oi_parquet_path(root: str, session_date: str) -> Path:
    d = _out_root() / root.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{session_date}_oi.parquet"


def _quarantine_corrupt(path: Path, err: Exception) -> str:
    """Rename an unreadable day parquet aside — never delete or overwrite it.

    Intraday chain snapshots are unreproducible, so an existing frame that
    fails to read (memory pressure, pyarrow hiccup, concurrent manual run)
    must keep its bytes: it moves to {stem}.corrupt-{UTC ts}.parquet for
    recovery and the sweep starts a fresh frame.  Raises if even the rename
    fails — the INERT catch in _sweep_root then skips the write, so earlier
    buckets are never replaced by a single sweep's rows.  Returns the
    quarantine file name (surfaced in _meta.json — a WARNING alone is
    effectively silent for a launchd lane).
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine = path.with_name(f"{path.stem}.corrupt-{ts}.parquet")
    path.rename(quarantine)
    log.error("chainsnap: unreadable existing %s (%s) — quarantined to %s, "
              "fresh frame starts from this sweep", path, err, quarantine.name)
    return quarantine.name


def append_day_parquet(path: Path, new_df: pd.DataFrame) -> tuple[int, int, str | None]:
    """Append rows to a per-root per-day parquet with dedup on DEDUP_KEY.

    Existing rows win (keep="first" after existing-then-new concat) so a
    re-run inside the same bucket is a no-op.  Atomic write (tmp + rename).
    An unreadable existing frame is never overwritten: it is quarantined via
    _quarantine_corrupt (bytes preserved) and a rename failure propagates
    instead of destroying earlier buckets.
    Returns (n_new_rows_added, n_total_rows, quarantined_file_name_or_None).
    """
    if new_df is None or new_df.empty:
        n_existing = 0
        if path.exists():
            try:
                n_existing = len(pd.read_parquet(path))
            except Exception:  # noqa: BLE001
                pass
        return 0, n_existing, None

    quarantined: str | None = None
    frames = []
    if path.exists():
        try:
            frames.append(pd.read_parquet(path))
        except Exception as e:  # noqa: BLE001
            quarantined = _quarantine_corrupt(path, e)
    n_before = len(frames[0]) if frames else 0
    frames.append(new_df)

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=[c for c in DEDUP_KEY if c in merged.columns],
                                    keep="first")
    sort_cols = [c for c in ("snapshot_bucket", "expiration", "strike", "right")
                 if c in merged.columns]
    if sort_cols:
        merged = merged.sort_values(sort_cols).reset_index(drop=True)

    tmp = path.with_suffix(".tmp.parquet")
    merged.to_parquet(tmp, index=False)
    tmp.rename(path)
    return len(merged) - n_before, len(merged), quarantined


# ── per-root sweep worker ─────────────────────────────────────────────────────

def _sweep_root(root: str, session_date: str, bucket: str,
                need_oi: bool) -> dict:
    """Pull first+second order snapshots (+ OI on the first sweep of the day)
    for one root, join, append.  INERT: never raises; returns a result dict.
    """
    from collectors import thetadata as td

    res = {"root": root, "rows": 0, "oi_rows": 0, "error": None,
           "quarantined": None}
    t0 = time.perf_counter()
    try:
        first = td.snapshot_greeks(root, order="first")
        if first is None or first.empty:
            res["error"] = ("first_order snapshot failed" if first is None
                            else "first_order snapshot empty")
            return res
        second = td.snapshot_greeks(root, order="second")
        if second is None:
            log.warning("chainsnap: %s second_order failed — writing first-order "
                        "rows with NaN second-order columns", root)

        joined = join_orders(first, second)
        joined["snapshot_bucket"] = bucket
        joined["source"] = "chain_snapshot"

        added, total, quarantined = append_day_parquet(
            day_parquet_path(root, session_date), joined)
        res["rows"] = added
        res["quarantined"] = quarantined

        # OI: one pull per root per DAY (first sweep only — OI timing law:
        # the 06:30 ET stamp holds EOD t-1 positions and never moves intraday).
        if need_oi:
            oi = td.snapshot_open_interest(root)
            if oi is None:
                log.warning("chainsnap: %s OI snapshot failed — retried next sweep", root)
            elif not oi.empty:
                oi = oi.copy()
                oi["source"] = "chain_snapshot"
                oi_path = oi_parquet_path(root, session_date)
                tmp = oi_path.with_suffix(".tmp.parquet")
                oi.to_parquet(tmp, index=False)
                tmp.rename(oi_path)
                res["oi_rows"] = len(oi)

        log.info("chainsnap: %s bucket=%s rows+%d (total %d) oi=%d elapsed=%.1fs",
                 root, bucket, added, total, res["oi_rows"],
                 time.perf_counter() - t0)
        return res
    except Exception as e:  # noqa: BLE001
        log.warning("chainsnap: sweep failed for %s: %s", root, e)
        res["error"] = str(e)
        return res


# ── sweep driver ──────────────────────────────────────────────────────────────

def run_sweep(roots: list[str], session_date: str, bucket: str,
              cfg: dict) -> dict:
    """One full-universe sweep.  Returns a summary dict for _meta.json."""
    max_w = _max_concurrent(cfg)
    t0 = time.perf_counter()

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_w) as pool:
        futs = {
            pool.submit(
                _sweep_root, root, session_date, bucket,
                not oi_parquet_path(root, session_date).exists(),
            ): root
            for root in roots
        }
        for fut in as_completed(futs):
            results.append(fut.result())

    errors = [f"{r['root']}: {r['error']}" for r in results if r["error"]]
    quarantined = [f"{r['root']}: {r['quarantined']}" for r in results
                   if r.get("quarantined")]
    return {
        "bucket":        bucket,
        "universe_n":    len(roots),
        "roots_ok":      sum(1 for r in results if not r["error"]),
        "roots_failed":  len(errors),
        "rows_appended": sum(r["rows"] for r in results),
        "oi_rows":       sum(r["oi_rows"] for r in results),
        "sweep_sec":     round(time.perf_counter() - t0, 1),
        "errors":        errors[:META_MAX_ERRORS],
        "quarantined":   quarantined[:META_MAX_ERRORS],
    }


def _write_meta(session_date: str, sweep_n: int, summary: dict, cfg: dict) -> None:
    """Atomic per-cycle run-status write to data/chain_snapshots/_meta.json.

    INERT: never raises — observability must not kill the lane.
    """
    try:
        meta = {
            "schema":         "chain_snapshots.meta/v1",
            "asof":           datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_date":   session_date,
            "sweep_n":        sweep_n,
            "cadence_min":    int(cfg.get("cadence_min", 15)),
            "max_concurrent": _max_concurrent(cfg),
            **summary,
        }
        p = _out_root() / META_FILE
        tmp = p.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(meta, default=str))
        tmp.rename(p)
    except Exception as e:  # noqa: BLE001
        log.warning("chainsnap: _meta.json write failed: %s", e)


# ── RTH gating ────────────────────────────────────────────────────────────────

def _within_rth(now: datetime | None = None) -> bool:
    """True if `now` (ET; default wall clock) is inside 09:35–16:00 ET on a
    weekday.  Never raises — returns False on any error.
    """
    try:
        now = now or datetime.now(ET)
        if now.weekday() >= 5:          # Saturday=5, Sunday=6
            return False
        t = now.hour * 60 + now.minute
        start = RTH_START_H * 60 + RTH_START_M   # 575
        end   = RTH_END_H   * 60 + RTH_END_M     # 960
        return start <= t <= end
    except Exception:  # noqa: BLE001
        return False


def _pre_rth_wait_sec(now: datetime | None = None) -> int:
    """Seconds to wait for the RTH window to open, or 0.

    The launchd plist fires at 06:30 PT (= 09:30 ET); the first sweep belongs
    at 09:35 ET.  Returns the wait only when `now` is a weekday within
    PRE_RTH_MAX_WAIT_SEC before the window start; 0 otherwise (caller exits).
    """
    try:
        now = now or datetime.now(ET)
        if now.weekday() >= 5:
            return 0
        start = now.replace(hour=RTH_START_H, minute=RTH_START_M,
                            second=0, microsecond=0)
        gap = (start - now).total_seconds()
        if 0 < gap <= PRE_RTH_MAX_WAIT_SEC:
            return int(gap) + 1
        return 0
    except Exception:  # noqa: BLE001
        return 0


# ── main loop ─────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="U-CHAIN chain-snapshot poller")
    parser.add_argument("--once",  action="store_true", help="Single sweep then exit")
    parser.add_argument("--roots", nargs="+", metavar="ROOT",
                        help="Subset of roots (default: full universe)")
    parser.add_argument("--rth-only", action="store_true",
                        help="Exit cleanly outside 09:35-16:00 ET on weekdays; "
                             "waits when fired up to 30 min early "
                             "(use with launchd StartCalendarInterval)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # --rth-only: launchd fires at 06:30 PT (09:30 ET) — wait for the 09:35
    # window start rather than exiting; genuinely outside RTH → exit cleanly.
    if args.rth_only and not _within_rth():
        wait = _pre_rth_wait_sec()
        if wait > 0:
            log.info("chainsnap: --rth-only fired %ds before window — waiting", wait)
            time.sleep(wait)
        if not _within_rth():
            log.info("chainsnap: --rth-only outside RTH window — exiting cleanly")
            return 0

    # Startup probe: tolerant 15s connect (a slow-starting ThetaTerminal must
    # not abort the lane).  Per-request calls skip reachable() by design — see
    # collectors.thetadata._snapshot_get.
    from collectors import thetadata as td
    if not td.reachable(connect_timeout=15):
        log.error("chainsnap: Theta Terminal not reachable — abort")
        return 1

    cfg = _cfg()
    cadence_sec = max(60, int(cfg.get("cadence_min", 15)) * 60)

    if args.roots:
        roots = [r.upper() for r in args.roots]
    else:
        roots = _resolve_universe(cfg)

    log.info("chainsnap: universe=%d roots cadence=%ds max_concurrent=%d "
             "(HARD — live_flow owns 2 of the terminal's 8 during RTH)",
             len(roots), cadence_sec, _max_concurrent(cfg))

    sweep_n = 0
    while True:
        loop_t0 = time.perf_counter()
        sweep_n += 1
        now_et = datetime.now(ET)
        session_date = now_et.strftime("%Y-%m-%d")
        bucket = derive_bucket(now_et, int(cfg.get("cadence_min", 15)))

        log.info("chainsnap: sweep #%d starting (date=%s bucket=%s roots=%d)",
                 sweep_n, session_date, bucket, len(roots))

        try:
            summary = run_sweep(roots, session_date, bucket, cfg)
        except Exception as e:  # noqa: BLE001
            log.error("chainsnap: sweep #%d unhandled error: %s", sweep_n, e,
                      exc_info=True)
            if args.once:
                return 1
            time.sleep(cadence_sec)
            continue

        _write_meta(session_date, sweep_n, summary, cfg)
        log.info("chainsnap: sweep #%d ok=%d failed=%d rows+%d oi=%d sweep_sec=%.1fs",
                 sweep_n, summary["roots_ok"], summary["roots_failed"],
                 summary["rows_appended"], summary["oi_rows"], summary["sweep_sec"])

        if args.once:
            log.info("chainsnap: --once flag set — exiting after one sweep")
            return 0

        # --rth-only: self-exit at end of each sweep once outside RTH
        if args.rth_only and not _within_rth():
            log.info("chainsnap: --rth-only outside RTH window — exiting cleanly")
            return 0

        elapsed = time.perf_counter() - loop_t0
        sleep_for = max(0.0, cadence_sec - elapsed)
        if sleep_for > 0:
            log.debug("chainsnap: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)


if __name__ == "__main__":
    sys.exit(main())
