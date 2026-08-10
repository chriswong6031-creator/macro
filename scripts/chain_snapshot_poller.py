"""scripts/chain_snapshot_poller.py — U-CHAIN intraday chain-snapshot lane.

Mac-side RTH loop: every cadence_min minutes (default 15) it sweeps the active
options universe (~150 roots: 22 ETF anchors + top gex names) and pulls a
full-chain greeks snapshot per root via the ThetaData v3 snapshot API —
first_order (delta/theta/vega/rho/IV) + second_order (gamma/vanna/charm/
vomma/veta) — joined only on exact (root, expiration, strike, right,
snapshot_ts); clock-mismatched second-order values remain null/unavailable —
and appended to per-root per-day
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
  _bucket_receipts/{DATE}.jsonl  — strict producer-owned intent/completion/
                                    availability state; authoritative for bucket
                                    completion (unlike _meta.json)
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
  # Single LIVE sweep.  Outside the actual current NYSE bucket this exits
  # without creating a new intent or calling ThetaData; an existing durable
  # decision/elapsed tail may still be truthfully reconciled first.
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
import hashlib
import json
import logging
import math
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import chain_snapshot_completion as completion  # noqa: E402
from engine.session_digest import session_window_et  # noqa: E402
from lib import config  # noqa: E402
from lib import nyse_calendar  # noqa: E402

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
ET = ZoneInfo("America/New_York")

# --rth-only fired before the window (launchd fires 06:30 PT = 09:30 ET): wait
# up to this long for the window to open instead of exiting.
PRE_RTH_MAX_WAIT_SEC = 30 * 60

# Output dir under data/ (gitignored, like live_flow_out/)
OUT_DIR = "chain_snapshots"
META_FILE = "_meta.json"
RECEIPT_DIR = "_bucket_receipts"

# Contract key + sweep-bucket dedup key for the per-day parquet
CONTRACT_KEY = ["root", "expiration", "strike", "right"]
DEDUP_KEY = CONTRACT_KEY + ["snapshot_bucket"]

# Second-order columns joined onto the first-order base (the second-order
# response also carries bid/ask/IV — those come from the first-order frame).
SECOND_ORDER_JOIN_COLS = ["gamma", "vanna", "charm", "vomma", "veta"]
CHAIN_REQUIRED_COLUMNS = {
    "root", "expiration", "strike", "right", "snapshot_ts",
    "snapshot_bucket", "source", "bid", "ask", "delta", "theta", "vega",
    "rho", "epsilon", "lambda", "implied_vol", "iv_error",
    "underlying_price", "gamma", "vanna", "charm", "vomma", "veta",
}
OI_REQUIRED_COLUMNS = {
    "root", "expiration", "strike", "right", "snapshot_ts",
    "open_interest", "source",
}

# Cap on error strings kept in _meta.json per cycle
META_MAX_ERRORS = 20
PENDING_RETRY_SEC = 30.0
GRID_EDGE_GUARD_SEC = 0.25


# ── config access ─────────────────────────────────────────────────────────────

def _cfg() -> dict:
    """Return the chain_snapshots config block (defaults filled by callers)."""
    loaded = config.load()
    if not isinstance(loaded, dict):
        raise ValueError("config root must be a mapping")
    block = loaded.get("chain_snapshots", {})
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise ValueError("chain_snapshots config must be a mapping")
    return dict(block)


def _max_concurrent(cfg: dict) -> int:
    """Resolve max_concurrent (default 1).

    HARD LAW: the live_flow poller owns 2 of the ThetaData terminal's 8
    concurrent request slots during RTH and the T1 backfill shares the rest.
    This lane's budget is 1.  NEVER raise without explicit Fable adjudication.
    """
    value = cfg.get("max_concurrent", 1)
    if type(value) is not int or value != 1:
        raise ValueError("chain_snapshots.max_concurrent must be the exact integer 1")
    return value


def _chain_snapshot_root_path() -> Path:
    """Return the immutable, config-independent producer authority root."""
    return REPO_ROOT / "data" / OUT_DIR


def _out_root() -> Path:
    return completion.ensure_directory_durable(_chain_snapshot_root_path())


def _receipt_root() -> Path:
    return _out_root() / RECEIPT_DIR


def _receipt_root_path() -> Path:
    """Receipt path without creating data/receipt directories."""
    return _chain_snapshot_root_path() / RECEIPT_DIR


# ── universe resolver (live_flow_poller._resolve_universe pattern) ───────────

def _resolve_universe(cfg: dict) -> list[str]:
    """ETF anchors + top_names from gex_symbols(), deduped, anchors first."""
    from engine.options_universe import gex_symbols

    default_anchors = [
        "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
        "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
        "KRE", "SMH", "XBI", "ARKK", "DIA",
    ]
    raw_anchors = cfg.get("etf_anchors", default_anchors)
    if not isinstance(raw_anchors, (list, tuple)):
        raise ValueError("chain_snapshots.etf_anchors must be a root list")
    anchors = list(completion.canonical_roots(raw_anchors))
    top_n = cfg.get("top_names", 128)
    if type(top_n) is not int or top_n < 0:
        raise ValueError("chain_snapshots.top_names must be an exact non-negative integer")

    seen: dict[str, None] = {}
    for t in anchors:
        seen.setdefault(t, None)

    try:
        gex = gex_symbols()
        for root in completion.canonical_roots(gex):
            seen.setdefault(root, None)
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
    return completion.derive_bucket(now_et, cadence_min)


# ── first+second order join ───────────────────────────────────────────────────

def join_orders(first_df: pd.DataFrame, second_df: pd.DataFrame | None) -> pd.DataFrame:
    """Left-join second-order greek columns onto the first-order base frame.

    The first-order frame is the base (its snapshot_ts/bid/ask/IV win); only
    SECOND_ORDER_JOIN_COLS are taken from the second-order frame.  The first-
    order base is deduped on the contract key.  Second-order candidates are
    deduped and joined only on exact (root, expiration, strike, right,
    snapshot_ts), so a duplicated contract row can never multiply rows and a
    clock mismatch stays null/unavailable.  A missing/failed second-order frame
    degrades to NaN second-order columns (INERT — first-order data still lands).
    """
    base = first_df.drop_duplicates(subset=CONTRACT_KEY, keep="first")

    if second_df is None or second_df.empty:
        out = base.copy()
        for col in SECOND_ORDER_JOIN_COLS:
            if col not in out.columns:
                out[col] = float("nan")   # float64 NaN — keeps parquet dtypes stable
        return out.reset_index(drop=True)

    # A second-order value is causally usable only when the vendor clock is
    # exactly the retained first-order contract clock.  Never silently attach
    # gamma/vanna/etc. to a different first-order observation.
    if "snapshot_ts" not in base.columns or "snapshot_ts" not in second_df.columns:
        out = base.copy()
        for col in SECOND_ORDER_JOIN_COLS:
            if col not in out.columns:
                out[col] = float("nan")
        return out.reset_index(drop=True)
    right = second_df.loc[second_df["snapshot_ts"].notna()].drop_duplicates(
        subset=CONTRACT_KEY + ["snapshot_ts"], keep="first",
    )
    join_cols = [c for c in SECOND_ORDER_JOIN_COLS if c in right.columns]
    out = base.merge(
        right[CONTRACT_KEY + ["snapshot_ts"] + join_cols],
        on=CONTRACT_KEY + ["snapshot_ts"],
        how="left",
    )
    for col in SECOND_ORDER_JOIN_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out.reset_index(drop=True)


# ── parquet append (dedup on contract key + snapshot bucket) ─────────────────

def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _confirm_file_durable(path: Path) -> None:
    """Reconfirm a visible file and its pathname before trusting recovery."""
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _read_and_confirm_parquet(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    _confirm_file_durable(path)
    return frame


def _file_sha256(path: Path, *, confirm: bool = True) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if confirm:
            os.fsync(handle.fileno())
    if confirm:
        _fsync_directory(path.parent)
    return digest.hexdigest()


def _target_bucket_frame(frame: pd.DataFrame, root: str, bucket: str) -> pd.DataFrame:
    missing = [col for col in DEDUP_KEY if col not in frame.columns]
    if missing:
        raise RuntimeError(f"target-bucket proof is missing columns: {missing}")
    target = frame.loc[
        frame["root"].map(lambda value: type(value) is str and value == root)
        & frame["snapshot_bucket"].astype(str).eq(bucket)
    ].copy()
    if target.empty:
        raise RuntimeError(f"installed parquet has no {root}/{bucket} target rows")
    if target.duplicated(subset=DEDUP_KEY).any():
        raise RuntimeError(f"installed parquet has duplicate {root}/{bucket} target rows")
    return target


def _canonical_cell(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise RuntimeError("non-finite installed parquet value")
        return value
    if type(value) in {str, int, bool}:
        return value
    raise RuntimeError(f"unsupported installed parquet scalar: {type(value).__name__}")


def _frame_content_sha256(frame: pd.DataFrame) -> str:
    columns = sorted(str(col) for col in frame.columns)
    ordered = frame.sort_values(
        [col for col in DEDUP_KEY if col in frame.columns],
        kind="stable",
    ).reset_index(drop=True)
    payload = {
        "columns": columns,
        "rows": [
            [_canonical_cell(value) for value in row]
            for row in ordered.loc[:, columns].itertuples(index=False, name=None)
        ],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _atomic_install_parquet(
    path: Path,
    frame: pd.DataFrame,
    *,
    required_root: str | None = None,
    required_bucket: str | None = None,
) -> pd.DataFrame:
    """Fsync exact parquet bytes, atomically install, fsync parent, then verify."""
    completion.ensure_directory_durable(path.parent)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".tmp.parquet", dir=path.parent,
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        frame.to_parquet(tmp, index=False)
        with tmp.open("rb") as handle:
            os.fsync(handle.fileno())
        serialized_sha256 = _file_sha256(tmp, confirm=False)
        os.replace(tmp, path)
        _fsync_directory(path.parent)
        installed = pd.read_parquet(path)
        installed_sha256 = _file_sha256(path)
        if installed_sha256 != serialized_sha256:
            raise RuntimeError(f"installed parquet bytes drifted for {path}")
        try:
            pd.testing.assert_frame_equal(
                installed.reset_index(drop=True),
                frame.reset_index(drop=True),
                check_dtype=True,
                check_exact=True,
            )
        except AssertionError as exc:
            raise RuntimeError(f"installed parquet content drift for {path}") from exc
        if required_root is not None and required_bucket is not None:
            _target_bucket_frame(installed, required_root, required_bucket)
        elif required_root is not None:
            if "root" not in installed.columns or installed.empty:
                raise RuntimeError(f"installed parquet cannot prove OI root {required_root}")
            if not installed["root"].astype(str).str.upper().eq(required_root.upper()).all():
                raise RuntimeError(f"installed parquet contains wrong OI root for {required_root}")
        return installed
    finally:
        if tmp.exists():
            tmp.unlink()

def day_parquet_path(root: str, session_date: str) -> Path:
    d = _out_root() / root.upper()
    completion.ensure_directory_durable(d)
    return d / f"{session_date}.parquet"


def oi_parquet_path(root: str, session_date: str) -> Path:
    d = _out_root() / root.upper()
    completion.ensure_directory_durable(d)
    return d / f"{session_date}_oi.parquet"


def _quarantine_glob(path: Path) -> str:
    return f"{path.stem}.corrupt-*.parquet"


def _existing_quarantines(path: Path) -> list[str]:
    names: list[str] = []
    pattern = re.compile(
        rf"^{re.escape(path.stem)}\.corrupt-\d{{8}}T\d{{12}}Z\.parquet$"
    )
    for candidate in sorted(path.parent.glob(_quarantine_glob(path))):
        if not pattern.fullmatch(candidate.name):
            raise RuntimeError(f"malformed quarantine provenance: {candidate}")
        _confirm_file_durable(candidate)
        names.append(candidate.name)
    return names


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
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    quarantine = path.with_name(f"{path.stem}.corrupt-{ts}.parquet")
    if quarantine.exists():
        raise RuntimeError(f"quarantine path collision: {quarantine}")
    path.rename(quarantine)
    _fsync_directory(path.parent)
    _confirm_file_durable(quarantine)
    log.error("chainsnap: unreadable existing %s (%s) — quarantined to %s, "
              "fresh frame starts from this sweep", path, err, quarantine.name)
    return quarantine.name


def append_day_parquet(
    path: Path,
    new_df: pd.DataFrame,
    *,
    replace_target_bucket: bool = False,
) -> tuple[int, int, list[str]]:
    """Append rows to a per-root per-day parquet with dedup on DEDUP_KEY.

    Existing rows win (keep="first" after existing-then-new concat) so a
    re-run inside the same bucket is a no-op.  Atomic write (tmp + rename).
    An unreadable existing frame is never overwritten: it is quarantined via
    _quarantine_corrupt (bytes preserved) and a rename failure propagates
    instead of destroying earlier buckets.
    Returns (n_new_rows_added, n_total_rows, all durable quarantine names).
    """
    if new_df is None or new_df.empty:
        n_existing = 0
        if path.exists():
            try:
                n_existing = len(_read_and_confirm_parquet(path))
            except Exception:  # noqa: BLE001
                pass
        return 0, n_existing, _existing_quarantines(path)

    quarantined = _existing_quarantines(path)
    frames = []
    existing: pd.DataFrame | None = None
    if path.exists():
        try:
            existing = _read_and_confirm_parquet(path)
        except Exception as e:  # noqa: BLE001
            _quarantine_corrupt(path, e)
            quarantined = _existing_quarantines(path)
    n_before = len(existing) if existing is not None else 0
    if existing is not None:
        if replace_target_bucket:
            required = {"root", "snapshot_bucket"}
            if not required.issubset(existing.columns) or not required.issubset(new_df.columns):
                raise RuntimeError("cannot replace recovered target bucket without key columns")
            roots = new_df["root"].astype(str).str.upper().drop_duplicates().tolist()
            buckets = new_df["snapshot_bucket"].astype(str).drop_duplicates().tolist()
            if len(roots) != 1 or len(buckets) != 1:
                raise RuntimeError("recovered target replacement requires one root and bucket")
            keep = ~(
                existing["root"].astype(str).str.upper().eq(roots[0])
                & existing["snapshot_bucket"].astype(str).eq(buckets[0])
            )
            frames.append(existing.loc[keep].copy())
        else:
            frames.append(existing)
    frames.append(new_df)

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=[c for c in DEDUP_KEY if c in merged.columns],
                                    keep="first")
    sort_cols = [c for c in ("snapshot_bucket", "expiration", "strike", "right")
                 if c in merged.columns]
    if sort_cols:
        merged = merged.sort_values(sort_cols).reset_index(drop=True)

    target_roots = new_df["root"].astype(str).str.upper().drop_duplicates().tolist()
    target_buckets = new_df["snapshot_bucket"].astype(str).drop_duplicates().tolist()
    if len(target_roots) != 1 or len(target_buckets) != 1:
        raise RuntimeError("chain append requires exactly one target root and bucket")
    installed = _atomic_install_parquet(
        path,
        merged,
        required_root=target_roots[0],
        required_bucket=target_buckets[0],
    )
    dedup_cols = [c for c in DEDUP_KEY if c in installed.columns]
    if dedup_cols and installed.duplicated(subset=dedup_cols).any():
        raise RuntimeError(f"installed parquet contains duplicate bucket keys: {path}")
    return max(0, len(installed) - n_before), len(installed), quarantined


def _preexisting_target_roots(
    session_date: str,
    bucket: str,
    roots: tuple[str, ...],
) -> list[str]:
    """Read-only fresh-intent guard, called while holding the receipt lock."""
    out = _out_root()
    found: list[str] = []
    for root in roots:
        path = out / root / f"{session_date}.parquet"
        if not path.exists():
            continue
        frame = _read_and_confirm_parquet(path)
        if "root" not in frame.columns or "snapshot_bucket" not in frame.columns:
            raise RuntimeError(f"cannot prove pre-intent target absence in {path}")
        mask = (
            frame["root"].astype(str).str.upper().eq(root)
            & frame["snapshot_bucket"].astype(str).eq(bucket)
        )
        if mask.any():
            found.append(root)
    return found


def _aware_vendor_clocks(frame: pd.DataFrame) -> list[datetime]:
    if "snapshot_ts" not in frame.columns or frame.empty:
        raise RuntimeError("snapshot evidence has no vendor clocks")
    clocks: list[datetime] = []
    for raw in frame["snapshot_ts"]:
        stamp = pd.Timestamp(raw)
        if pd.isna(stamp):
            raise RuntimeError("snapshot evidence contains an invalid vendor clock")
        if stamp.nanosecond != 0:
            raise RuntimeError("vendor clock is not exact to UTC microseconds")
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(ET, ambiguous="raise", nonexistent="raise")
        else:
            stamp = stamp.tz_convert(ET)
        clocks.append(stamp.to_pydatetime().astimezone(timezone.utc))
    return clocks


def _second_order_coverage(first: pd.DataFrame, second: pd.DataFrame) -> tuple[int, int]:
    base = first.drop_duplicates(subset=CONTRACT_KEY, keep="first")
    if "snapshot_ts" not in base.columns or "snapshot_ts" not in second.columns:
        return 0, len(base)
    right = second.loc[second["snapshot_ts"].notna()].drop_duplicates(
        subset=CONTRACT_KEY + ["snapshot_ts"], keep="first",
    )
    right = right[CONTRACT_KEY + ["snapshot_ts"]].copy()
    right["_second_clock_match"] = True
    coverage = base.merge(
        right,
        on=CONTRACT_KEY + ["snapshot_ts"],
        how="left",
    )
    matched = int(coverage["_second_clock_match"].fillna(False).sum())
    return matched, len(base) - matched


def _chain_storage_evidence(path: Path, root: str, bucket: str) -> dict:
    installed = _read_and_confirm_parquet(path)
    missing = sorted(CHAIN_REQUIRED_COLUMNS - set(installed.columns))
    if missing:
        raise RuntimeError(f"installed day chain is missing W0a columns: {missing}")
    if not installed["root"].map(
        lambda value: type(value) is str and value == root
    ).all():
        raise RuntimeError("installed day chain has a non-canonical or wrong root")
    if not installed["source"].map(
        lambda value: type(value) is str and value == "chain_snapshot"
    ).all():
        raise RuntimeError("installed day chain has a wrong source tag")
    target = _target_bucket_frame(installed, root, bucket)
    return {
        "bucket_rows": len(target),
        "bucket_content_sha256": _frame_content_sha256(target),
        "parquet_sha256": _file_sha256(path),
    }


def _validate_oi_frame(frame: pd.DataFrame, root: str) -> None:
    missing = sorted(OI_REQUIRED_COLUMNS - set(frame.columns))
    if frame.empty or missing:
        raise RuntimeError(f"installed OI cannot prove W0a shape; missing={missing}")
    if not frame["root"].map(
        lambda value: type(value) is str and value == root
    ).all():
        raise RuntimeError(f"installed OI contains a non-canonical or wrong root for {root}")
    if not frame["source"].map(
        lambda value: type(value) is str and value == "chain_snapshot"
    ).all():
        raise RuntimeError("installed OI has a wrong source tag")


# ── per-root sweep worker ─────────────────────────────────────────────────────

def _sweep_root(
    root: str,
    session_date: str,
    bucket: str,
    need_oi: bool,
    replace_target_bucket: bool = False,
) -> dict:
    """Pull first+second order snapshots (+ OI on the first sweep of the day)
    for one root, join, append.  INERT: never raises; returns a result dict.
    """
    from collectors import thetadata as td

    res = {
        "root": root,
        "rows": 0,
        "total_rows": 0,
        "oi_rows": 0,
        "oi_total_rows": 0,
        "error": None,
        "completion_errors": [],
        "bucket_rows": 0,
        "bucket_content_sha256": None,
        "parquet_sha256": None,
        "oi_parquet_sha256": None,
        "first_vendor_min_at": None,
        "first_vendor_max_at": None,
        "first_prebucket_rows": 0,
        "first_at_or_after_bucket_rows": 0,
        "second_clock_matched_rows": 0,
        "second_clock_unmatched_rows": 0,
        "quarantined": [],
        "oi_quarantined": [],
    }
    t0 = time.perf_counter()
    try:
        first = td.snapshot_greeks(root, order="first")
        if first is None or first.empty:
            res["error"] = ("first_order snapshot failed" if first is None
                            else "first_order snapshot empty")
            return res
        second = td.snapshot_greeks(root, order="second")
        if second is None or second.empty:
            res["completion_errors"].append(
                "second_order snapshot failed" if second is None
                else "second_order snapshot empty"
            )
            log.warning("chainsnap: %s second_order failed — writing first-order "
                        "rows with NaN second-order columns", root)

        first_base = first.drop_duplicates(subset=CONTRACT_KEY, keep="first")
        first_clocks = _aware_vendor_clocks(first_base)
        res["first_vendor_min_at"] = completion.utc_microseconds(min(first_clocks))
        res["first_vendor_max_at"] = completion.utc_microseconds(max(first_clocks))
        bucket_hour, bucket_minute = (int(part) for part in bucket.split(":"))
        bucket_start = datetime.combine(
            date.fromisoformat(session_date),
            datetime.min.time(),
            tzinfo=ET,
        ).replace(hour=bucket_hour, minute=bucket_minute)
        res["first_prebucket_rows"] = sum(
            stamp < bucket_start.astimezone(timezone.utc) for stamp in first_clocks
        )
        res["first_at_or_after_bucket_rows"] = (
            len(first_clocks) - res["first_prebucket_rows"]
        )
        if second is None or second.empty:
            res["second_clock_unmatched_rows"] = len(first_base)
        else:
            matched, unavailable = _second_order_coverage(first_base, second)
            res["second_clock_matched_rows"] = matched
            res["second_clock_unmatched_rows"] = unavailable

        joined = join_orders(first, second)
        joined["snapshot_bucket"] = bucket
        joined["source"] = "chain_snapshot"

        added, total, quarantined = append_day_parquet(
            day_parquet_path(root, session_date),
            joined,
            replace_target_bucket=replace_target_bucket,
        )
        res["rows"] = added
        res["total_rows"] = total
        res["quarantined"] = quarantined

        # OI: one pull per root per DAY (first sweep only — OI timing law:
        # the 06:30 ET stamp holds EOD t-1 positions and never moves intraday).
        oi_path = oi_parquet_path(root, session_date)
        if not need_oi and oi_path.exists():
            try:
                existing_oi = _read_and_confirm_parquet(oi_path)
                try:
                    _validate_oi_frame(existing_oi, root)
                except RuntimeError as e:
                    _quarantine_corrupt(oi_path, e)
                    res["oi_quarantined"] = _existing_quarantines(oi_path)
                    need_oi = True
                else:
                    res["oi_total_rows"] = len(existing_oi)
                    res["oi_parquet_sha256"] = _file_sha256(oi_path)
            except Exception as e:  # noqa: BLE001
                _quarantine_corrupt(oi_path, e)
                res["oi_quarantined"] = _existing_quarantines(oi_path)
                need_oi = True
        if need_oi:
            oi = td.snapshot_open_interest(root)
            if oi is None or oi.empty:
                res["completion_errors"].append(
                    "open_interest snapshot failed" if oi is None
                    else "open_interest snapshot empty"
                )
                log.warning("chainsnap: %s OI snapshot failed — retried next sweep", root)
            else:
                oi = oi.copy()
                oi["source"] = "chain_snapshot"
                installed_oi = _atomic_install_parquet(
                    oi_path,
                    oi,
                    required_root=root,
                )
                _validate_oi_frame(installed_oi, root)
                res["oi_rows"] = len(installed_oi)
                res["oi_total_rows"] = len(installed_oi)
                res["oi_parquet_sha256"] = _file_sha256(oi_path)
        res["oi_quarantined"] = _existing_quarantines(oi_path)

        evidence = _chain_storage_evidence(
            day_parquet_path(root, session_date), root, bucket,
        )
        res.update(evidence)
        if res["bucket_rows"] != len(first_base):
            res["completion_errors"].append("installed target bucket row count drift")
        if res["oi_total_rows"] <= 0 or res["oi_parquet_sha256"] is None:
            if "open_interest snapshot failed" not in res["completion_errors"] and (
                "open_interest snapshot empty" not in res["completion_errors"]
            ):
                res["completion_errors"].append("open_interest durability proof missing")

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
    replace_target_bucket = cfg.get("_receipt_recovered") is True
    t0 = time.perf_counter()

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_w) as pool:
        futs = {
            pool.submit(
                _sweep_root, root, session_date, bucket,
                not oi_parquet_path(root, session_date).exists(),
                replace_target_bucket,
            ): root
            for root in roots
        }
        for fut in as_completed(futs):
            results.append(fut.result())

    errors = [f"{r['root']}: {r['error']}" for r in results if r["error"]]
    completion_errors = [
        f"{result['root']}: {error}"
        for result in results
        for error in result.get("completion_errors", [])
    ]
    quarantined = [
        f"{result['root']}: {name}"
        for result in results
        for name in result.get("quarantined", [])
    ]
    oi_quarantined = [
        f"{result['root']}: {name}"
        for result in results
        for name in result.get("oi_quarantined", [])
    ]
    by_root = {r.get("root"): r for r in results if isinstance(r, dict)}
    ordered_results = [by_root[root] for root in roots if root in by_root]
    return {
        "bucket":        bucket,
        "universe_n":    len(roots),
        "roots_ok":      sum(1 for r in results if not r["error"]),
        "roots_failed":  len(errors),
        "completion_roots_ok": sum(
            1 for r in results if not r["error"] and not r.get("completion_errors")
        ),
        "completion_roots_failed": sum(
            1 for r in results if r["error"] or r.get("completion_errors")
        ),
        "rows_appended": sum(r["rows"] for r in results),
        "rows_total":    sum(r.get("total_rows", 0) for r in results),
        "oi_rows":       sum(r["oi_rows"] for r in results),
        "oi_total_rows": sum(r.get("oi_total_rows", 0) for r in results),
        "sweep_sec":     round(time.perf_counter() - t0, 1),
        "errors":        errors[:META_MAX_ERRORS],
        "completion_errors": completion_errors[:META_MAX_ERRORS],
        "quarantined":   (quarantined + oi_quarantined)[:META_MAX_ERRORS],
        "_root_results": ordered_results,
    }


def _receipt_skip_summary(lease: completion.BucketLease, state: str) -> dict:
    completed = (
        lease.state.decision.get("completion", {})
        if lease.state.decision is not None else {}
    )
    incomplete = lease.state.incomplete
    is_complete = lease.status == "complete"
    summary = {
        "bucket": lease.bucket,
        "universe_n": len(lease.roots),
        "roots_ok": len(lease.roots) if is_complete else 0,
        "roots_failed": 0 if is_complete else len(lease.roots),
        "completion_roots_ok": len(lease.roots) if is_complete else 0,
        "completion_roots_failed": 0 if is_complete else len(lease.roots),
        "rows_appended": 0,
        "rows_total": int(completed.get("rows_total", 0)),
        "oi_rows": 0,
        "oi_total_rows": int(completed.get("oi_total_rows", 0)),
        "sweep_sec": 0.0,
        "errors": ([] if is_complete else [f"receipt terminal: {state}"]),
        "completion_errors": ([] if is_complete else [f"receipt terminal: {state}"]),
        "quarantined": [],
        "receipt_state": state,
        "receipt_bucket_id": lease.state.intent["bucket_id"],
        "terminalized_receipts": list(lease.terminalized),
        "terminalized_receipt_count": len(lease.terminalized),
    }
    if incomplete is not None:
        summary["receipt_incomplete_reason"] = incomplete["reason"]
    return summary


def _invoke_completion_hook(
    completion_hook: Callable[[dict], object] | None,
    lease: completion.BucketLease,
    summary: dict,
) -> None:
    """Run the disabled-by-default future seam without rewriting source truth."""
    if completion_hook is None:
        return
    try:
        completion_hook(lease.packet())
    except Exception as exc:  # noqa: BLE001 — future repair must not recast source success
        summary["completion_hook_error"] = str(exc)
        log.error(
            "chainsnap: post-availability completion hook failed for %s/%s: %s",
            lease.session_date,
            lease.bucket,
            exc,
            exc_info=True,
        )


def run_managed_sweep(
    roots: list[str],
    session_date: str,
    bucket: str,
    cfg: dict,
    *,
    now: datetime,
    now_fn: Callable[[], datetime] | None = None,
    completion_hook: Callable[[dict], object] | None = None,
    sweep_fn: Callable[[list[str], str, str, dict], dict] | None = None,
) -> dict:
    """Run/recover one receipt-bound bucket under the sole producer lock.

    The future hook is an injection seam only: production passes ``None``.  If
    later supplied it runs synchronously under this same lock, and only after a
    durable availability receipt.  Its failure is returned in observability but
    cannot roll back the already-durable source sweep or completion receipts.
    """
    cadence_min = completion.validate_cadence_min(cfg.get("cadence_min", 15))
    _max_concurrent(cfg)
    requested_roots = list(completion.canonical_roots(roots))
    runner = sweep_fn or run_sweep
    with completion.locked_bucket_lease(
        _receipt_root(),
        session_date=session_date,
        bucket=bucket,
        cadence_min=cadence_min,
        roots=requested_roots,
        now=now,
        now_fn=now_fn,
        pre_intent_target_roots=_preexisting_target_roots,
    ) as lease:
        if lease.status == "complete":
            lease.confirm_complete()
            summary = _receipt_skip_summary(lease, "complete_skip")
            _invoke_completion_hook(completion_hook, lease, summary)
            return summary
        if lease.status == "incomplete":
            return _receipt_skip_summary(lease, "incomplete_skip")
        if lease.status == "decision":
            lease.record_availability(require_live_bucket=True)
            if lease.status != "complete":
                return _receipt_skip_summary(lease, "decision_terminal_incomplete")
            summary = _receipt_skip_summary(lease, "decision_recovered")
            _invoke_completion_hook(completion_hook, lease, summary)
            return summary

        if lease.preexisting_target_roots:
            blocked = list(lease.preexisting_target_roots)
            return {
                "bucket": lease.bucket,
                "universe_n": len(lease.roots),
                "roots_ok": 0,
                "roots_failed": len(lease.roots),
                "completion_roots_ok": 0,
                "completion_roots_failed": len(lease.roots),
                "rows_appended": 0,
                "rows_total": 0,
                "oi_rows": 0,
                "oi_total_rows": 0,
                "sweep_sec": 0.0,
                "errors": [
                    "fresh intent found pre-existing target-bucket rows: "
                    + ",".join(blocked)
                ],
                "completion_errors": [
                    "pre-existing target-bucket rows are not intent-authorized"
                ],
                "quarantined": [],
                "receipt_state": "intent_blocked_preexisting",
                "receipt_bucket_id": lease.state.intent["bucket_id"],
                "preexisting_target_roots": blocked,
                "terminalized_receipts": list(lease.terminalized),
                "terminalized_receipt_count": len(lease.terminalized),
            }

        source_now = lease.refresh_before_source()
        if source_now is None:
            return _receipt_skip_summary(lease, "intent_terminal_incomplete")

        frozen_roots = list(lease.roots)
        source_cfg = dict(cfg)
        source_cfg["_receipt_recovered"] = lease.recovered
        source_cfg["_receipt_source_at"] = completion.utc_microseconds(source_now)
        summary = runner(frozen_roots, lease.session_date, lease.bucket, source_cfg)
        summary["receipt_bucket_id"] = lease.state.intent["bucket_id"]
        summary["terminalized_receipts"] = list(lease.terminalized)
        summary["terminalized_receipt_count"] = len(lease.terminalized)
        complete = (
            summary.get("bucket") == lease.bucket
            and type(summary.get("universe_n")) is int
            and summary["universe_n"] == len(frozen_roots)
            and type(summary.get("completion_roots_ok")) is int
            and summary["completion_roots_ok"] == len(frozen_roots)
            and summary.get("completion_roots_failed") == 0
        )
        if not complete:
            summary["receipt_state"] = "intent_pending"
            return summary

        decision_summary = completion.build_completion_summary(
            lease.roots,
            summary.get("_root_results", []),
        )
        lease.record_decision(decision_summary, require_live_bucket=True)
        if lease.status != "decision":
            summary["receipt_state"] = "decision_terminal_incomplete"
            summary["receipt_incomplete_reason"] = lease.state.incomplete["reason"]
            return summary
        lease.record_availability(require_live_bucket=True)
        if lease.status != "complete":
            summary["receipt_state"] = "availability_terminal_incomplete"
            summary["receipt_incomplete_reason"] = lease.state.incomplete["reason"]
            return summary
        summary["receipt_state"] = "complete"
        summary["availability_at"] = lease.state.availability["availability_at"]
        _invoke_completion_hook(completion_hook, lease, summary)
        return summary


def _write_meta(session_date: str, sweep_n: int, summary: dict, cfg: dict) -> None:
    """Atomic per-cycle run-status write to data/chain_snapshots/_meta.json.

    INERT: never raises — observability must not kill the lane.
    """
    try:
        public_summary = {
            key: value for key, value in summary.items() if not key.startswith("_")
        }
        meta = {
            "schema":         "chain_snapshots.meta/v1",
            "asof":           datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_date":   session_date,
            "sweep_n":        sweep_n,
            "cadence_min":    completion.validate_cadence_min(
                cfg.get("cadence_min", 15),
            ),
            "max_concurrent": _max_concurrent(cfg),
            **public_summary,
        }
        p = _out_root() / META_FILE
        tmp = p.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(meta, default=str))
        tmp.rename(p)
    except Exception as e:  # noqa: BLE001
        log.warning("chainsnap: _meta.json write failed: %s", e)


def _write_recovery_meta(actions: list[dict], cfg: dict, *, sweep_n: int) -> None:
    if not actions:
        return
    incomplete_actions = [
        action for action in actions if action["receipt_state"] == "incomplete"
    ]
    _write_meta(
        actions[-1]["session_date"],
        sweep_n,
        {
            "bucket": actions[-1]["bucket"],
            "universe_n": 0,
            "roots_ok": 0,
            "roots_failed": len(incomplete_actions),
            "completion_roots_ok": 0,
            "completion_roots_failed": len(incomplete_actions),
            "rows_appended": 0,
            "rows_total": 0,
            "oi_rows": 0,
            "oi_total_rows": 0,
            "sweep_sec": 0.0,
            "errors": [
                f"receipt terminal: {action['receipt_incomplete_reason']}"
                for action in incomplete_actions
            ],
            "completion_errors": [],
            "quarantined": [],
            "receipt_state": "receipt_reconciled",
            "receipt_recovery_actions": actions,
            "receipt_recovery_action_count": len(actions),
        },
        cfg,
    )


# ── RTH gating ────────────────────────────────────────────────────────────────

def _within_rth(now: datetime | None = None) -> bool:
    """True only inside a real current NYSE intent window.

    The close bucket has the legacy sub-minute grace (through 16:00:59 on a
    regular day or 13:00:59 on an early close), but no later bucket is admitted.
    """
    try:
        now = now or datetime.now(ET)
        if now.tzinfo is None:
            return False
        local = now.astimezone(ET)
        if not nyse_calendar.is_session(local.date()):
            return False
        open_et, close_et = session_window_et(local.date())
        start = open_et + timedelta(minutes=5)
        return start <= local < close_et + completion.INTENT_CLOSE_GRACE
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
        if now.tzinfo is None:
            return 0
        now = now.astimezone(ET)
        if not nyse_calendar.is_session(now.date()):
            return 0
        open_et, _close_et = session_window_et(now.date())
        start = open_et + timedelta(minutes=5)
        gap = (start - now).total_seconds()
        if 0 < gap <= PRE_RTH_MAX_WAIT_SEC:
            return int(gap) + 1
        return 0
    except Exception:  # noqa: BLE001
        return 0


# ── main loop ─────────────────────────────────────────────────────────────────

def _now_et() -> datetime:
    return datetime.now(ET)


def _seconds_to_next_wall_grid(
    now_et: datetime,
    cadence_min: int,
    *,
    pending: bool = False,
) -> float:
    """Schedule against the next ET wall-grid edge, never sweep duration."""
    cadence = completion.validate_cadence_min(cadence_min)
    if now_et.tzinfo is None:
        raise ValueError("wall-grid scheduling requires an aware clock")
    local = now_et.astimezone(ET)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (local - midnight).total_seconds()
    step = cadence * 60
    next_edge = midnight + timedelta(seconds=(math.floor(elapsed / step) + 1) * step)
    remaining = max(0.0, (next_edge - local).total_seconds())
    if not pending or remaining <= GRID_EDGE_GUARD_SEC:
        return remaining
    return min(PENDING_RETRY_SEC, max(0.0, remaining - GRID_EDGE_GUARD_SEC))


def _session_close_reached(now_et: datetime) -> bool:
    try:
        local = now_et.astimezone(ET)
        if not nyse_calendar.is_session(local.date()):
            return True
        _open_et, close_et = session_window_et(local.date())
        return local >= close_et
    except Exception:  # noqa: BLE001
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="U-CHAIN chain-snapshot poller")
    parser.add_argument(
        "--once", action="store_true",
        help="Run one current live NYSE bucket; outside RTH creates no new intent/source",
    )
    parser.add_argument("--roots", nargs="+", metavar="ROOT",
                        help="Subset of roots (default: full universe)")
    parser.add_argument("--rth-only", action="store_true",
                        help="Exit cleanly outside the actual NYSE session window; "
                             "waits when fired up to 30 min early "
                             "(use with launchd StartCalendarInterval)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Drain already-durable decisions and elapsed tails before parsing mutable
    # chain config or applying the source-admission gate.  This path never
    # resolves a universe or calls ThetaData.
    try:
        recovery_actions = completion.reconcile_existing_receipts(
            _receipt_root_path(),
            now_fn=_now_et,
        )
    except Exception as exc:  # noqa: BLE001 — receipt corruption is fail-visible
        log.error("chainsnap: startup receipt reconciliation failed: %s", exc,
                  exc_info=True)
        return 1
    if recovery_actions:
        log.warning("chainsnap: startup receipt recovery actions=%s", recovery_actions)
        _write_recovery_meta(
            recovery_actions,
            {
                "cadence_min": recovery_actions[-1]["cadence_min"],
                "max_concurrent": 1,
            },
            sweep_n=0,
        )

    try:
        cfg = _cfg()
        cadence_min = completion.validate_cadence_min(cfg.get("cadence_min", 15))
        _max_concurrent(cfg)
    except Exception as exc:  # noqa: BLE001 — malformed config must fail closed
        log.error("chainsnap: invalid chain_snapshots config: %s", exc)
        return 1
    cadence_sec = cadence_min * 60

    # launchd fires at 06:30 PT (09:30 ET).  Only --rth-only waits for 09:35;
    # every other outside-window invocation (including --once) creates no new
    # intent/source and performs no ThetaData probe. Startup receipt-only
    # reconciliation above may already have completed a durable prefix.
    startup_now = _now_et()

    def _drain_before_clean_exit(sweep_n: int) -> bool:
        try:
            actions = completion.reconcile_existing_receipts(
                _receipt_root_path(),
                now_fn=_now_et,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("chainsnap: final receipt reconciliation failed: %s", exc,
                      exc_info=True)
            return False
        if actions:
            log.warning("chainsnap: final receipt recovery actions=%s", actions)
            _write_recovery_meta(actions, cfg, sweep_n=sweep_n)
        return True
    if args.rth_only and not _within_rth(startup_now):
        wait = _pre_rth_wait_sec(startup_now)
        if wait > 0:
            log.info("chainsnap: --rth-only fired %ds before window — waiting", wait)
            time.sleep(wait)
        startup_now = _now_et()
    if not _within_rth(startup_now):
        log.info("chainsnap: no current live NYSE bucket — exiting without collection")
        return 0 if _drain_before_clean_exit(0) else 1

    try:
        if args.roots:
            roots = list(completion.canonical_roots(args.roots))
        else:
            roots = list(completion.canonical_roots(_resolve_universe(cfg)))
    except Exception as exc:  # noqa: BLE001 — invalid universe cannot freeze intent
        log.error("chainsnap: invalid chain snapshot universe: %s", exc)
        return 1

    log.info("chainsnap: universe=%d roots cadence=%ds max_concurrent=%d "
             "(HARD — live_flow owns 2 of the terminal's 8 during RTH)",
             len(roots), cadence_sec, _max_concurrent(cfg))

    terminal_ready = False

    def _source_sweep(
        frozen_roots: list[str], frozen_session: str, frozen_bucket: str, source_cfg: dict,
    ) -> dict:
        """Probe Theta only after the durable bucket intent, once per process."""
        nonlocal terminal_ready
        if not terminal_ready:
            from collectors import thetadata as td
            if not td.reachable(connect_timeout=15):
                raise RuntimeError("Theta Terminal not reachable")
            terminal_ready = True
        return run_sweep(frozen_roots, frozen_session, frozen_bucket, source_cfg)

    sweep_n = 0
    while True:
        sweep_n += 1
        now_et = _now_et()
        if not _within_rth(now_et):
            log.info("chainsnap: no current live NYSE bucket — exiting cleanly")
            return 0 if _drain_before_clean_exit(sweep_n) else 1
        session_date = now_et.strftime("%Y-%m-%d")
        bucket = derive_bucket(now_et, cadence_min)

        log.info("chainsnap: sweep #%d starting (date=%s bucket=%s roots=%d)",
                 sweep_n, session_date, bucket, len(roots))

        try:
            summary = run_managed_sweep(
                roots,
                session_date,
                bucket,
                cfg,
                now=now_et,
                sweep_fn=_source_sweep,
            )
        except Exception as e:  # noqa: BLE001
            log.error("chainsnap: sweep #%d unhandled error: %s", sweep_n, e,
                      exc_info=True)
            if args.once:
                return 1
            retry_delay = _seconds_to_next_wall_grid(
                _now_et(), cadence_min, pending=True,
            )
            if retry_delay > 0:
                time.sleep(retry_delay)
            continue

        _write_meta(session_date, sweep_n, summary, cfg)
        log.info("chainsnap: sweep #%d ok=%d failed=%d rows+%d oi=%d sweep_sec=%.1fs",
                 sweep_n, summary["roots_ok"], summary["roots_failed"],
                 summary["rows_appended"], summary["oi_rows"], summary["sweep_sec"])

        if args.once:
            log.info("chainsnap: --once flag set — exiting after one sweep")
            return 0 if summary.get("receipt_state") in {
                "complete", "complete_skip", "decision_recovered",
            } else 1

        # --rth-only: self-exit at end of each sweep once outside RTH
        after_sweep = _now_et()
        after_within_rth = _within_rth(after_sweep)
        if after_within_rth and derive_bucket(after_sweep, cadence_min) != summary.get(
            "bucket"
        ):
            log.debug("chainsnap: wall bucket advanced during sweep — iterating now")
            continue
        if _session_close_reached(after_sweep) and not (
            after_within_rth and summary.get("receipt_state") == "intent_pending"
        ):
            log.info("chainsnap: close bucket finished — exiting cleanly")
            return 0 if _drain_before_clean_exit(sweep_n) else 1
        if args.rth_only and not after_within_rth:
            log.info("chainsnap: --rth-only outside RTH window — exiting cleanly")
            return 0 if _drain_before_clean_exit(sweep_n) else 1

        sleep_for = _seconds_to_next_wall_grid(
            after_sweep,
            cadence_min,
            pending=summary.get("receipt_state") == "intent_pending",
        )
        if sleep_for > 0:
            log.debug("chainsnap: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)


if __name__ == "__main__":
    sys.exit(main())
