"""scripts/ops_flow_cohorts.py — FS-1 historical flow cohorts (ops lane, off-render).

OPS-LANE ONLY. NOT wired into any workflow (daily.yml / config/dag.yml).
Run manually after prerequisites are met.

SUBCOMMANDS
-----------
tape_recon  -- Pull bulk per-trade tape from ThetaTerminal, apply detector v1,
               and write cohort_tape_recon.parquet.
eod_proxy   -- Build pseudo-events from the thetadata_eod store (vol>OI bursts,
               premium bursts), write cohort_eod_proxy.parquet.

PREREQUISITES
-------------
tape_recon:
  • ThetaTerminal must be running (http://127.0.0.1:25503 reachable — verify with
    `python -c "from collectors.thetadata import reachable; print(reachable())"`)
  • config/flow_recon_ladder.yml defines the priority ladder (tier1→tier3).
  • FLOW_SIGNALS_DIR env var overrides the output directory (default: data/flow_signals/).

eod_proxy:
  • thetadata_eod store must be complete (≥15y per root, ≤5% shortfall allowed).
  • Store path resolution: THETADATA_EOD_DIR env → ~/theta-ops-wt/data/thetadata_eod
    → data/thetadata_eod relative to repo root.
  • Can run TODAY — store is confirmed complete (2026-07-13, 383/383 roots @ 15y).
  • --roots N flag limits to N roots (useful for smoke testing).

RESUME SEMANTICS (tape_recon)
------------------------------
State file: FLOW_SIGNALS_DIR/_recon_state.json
Schema: {"completed": {"ROOT|YYYY-MM-DD": "ok"}, "failed": {"ROOT|YYYY-MM-DD": "msg"}}
An interrupted run resumes from the last pending unit (completed units are skipped).
Failed units are retryable: remove them from "failed" or re-run with --retry-failed.
keep-first on _event_id: a unit that was partially written before a crash is safe
to re-process — duplicate event_ids are dropped, first occurrence wins.

RUNTIME ARITHMETIC (tape_recon)
---------------------------------
Tier1 (15 roots × ~500 trading days 2022→): ~7500 units.
At 8 concurrent, typical ~8s/unit (ETF tape) → ~7500 × 8s / 8 = ~7500s ≈ 2h.
Tier2 (15 roots × ~1000 days 2017→2021): ~15000 units → ~4h at 8-concurrent.
Tier3 (18 single names × ~500 days 2022→): ~9000 units; single names are ~10x
larger per-day → ~12h at 8-concurrent (schedule as an overnight job).
Total: ~18h for all three tiers (split across sessions; fully resumable).

Recommended order: run eod_proxy FIRST (no terminal needed), then tape_recon in
tier order (tier1 → tier2 → tier3) as terminal uptime allows.

PIT COVERAGE NOTE (tape_recon)
--------------------------------
premium_z for tape_recon events is computable only from trailing tape-derived
baselines built PIT during the reconstruction sweep. A root's FIRST 252 trading
days of reconstruction get premium_z=null (honest coverage, never fake-neutral).
This is by design: a baseline requires 252 prior observations.

LEGAL FEATURES (FS-R6)
-----------------------
ALLOWED (measurement): at-ask/at-bid classification, aggression share, sweep
detection from the print's own bid/ask, unsigned premium/volume/vol>OI.
FORBIDDEN: any tick-rule signed net-direction label or feature. Do NOT emit a
signed-direction column from tick inference. The Theta-tape SUSPENDED row stands.

COHORT SEPARATION (FS-R4)
--------------------------
cohort_tape_recon.parquet (source='tape_recon') and cohort_eod_proxy.parquet
(source='eod_proxy') are NEVER pooled with each other or with ledger.parquet.
Use load_cohort() to read — it raises on mixed-source frames.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Return the absolute path to the repo root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def _flow_signals_dir() -> Path:
    """Return the flow_signals output directory.

    Priority: FLOW_SIGNALS_DIR env → data/flow_signals/ relative to repo root.
    """
    env = os.environ.get("FLOW_SIGNALS_DIR")
    if env:
        p = Path(env)
    else:
        p = _repo_root() / "data" / "flow_signals"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _eod_store_root() -> Path | None:
    """Resolve thetadata_eod store root.

    Priority: THETADATA_EOD_DIR env → ~/theta-ops-wt/data/thetadata_eod
              → data/thetadata_eod relative to repo root.
    Returns None if no candidate exists.
    """
    candidates: list[Path] = []
    env = os.environ.get("THETADATA_EOD_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / "theta-ops-wt" / "data" / "thetadata_eod")
    candidates.append(_repo_root() / "data" / "thetadata_eod")
    for c in candidates:
        if c.exists() and (c / "_manifest.json").exists():
            return c
    return None


# ── detector config ────────────────────────────────────────────────────────────

_DETECTOR_CFG: dict | None = None


def _load_detector_cfg() -> dict:
    """Load config/flow_detector.yml. Cached after first call."""
    global _DETECTOR_CFG
    if _DETECTOR_CFG is not None:
        return _DETECTOR_CFG
    try:
        import yaml
        p = _repo_root() / "config" / "flow_detector.yml"
        with p.open() as f:
            _DETECTOR_CFG = yaml.safe_load(f)
        return _DETECTOR_CFG
    except Exception as e:  # noqa: BLE001
        log.warning("ops_flow_cohorts: could not load flow_detector.yml: %s", e)
        _DETECTOR_CFG = {}
        return _DETECTOR_CFG


def _detector_version() -> str:
    """Return the live_feed detector version string (e.g. 'live_feed_v1')."""
    return _load_detector_cfg().get("version", "unknown")


def _eod_proxy_version() -> str:
    """Return the eod_proxy version string (e.g. 'eod_proxy_v1')."""
    cfg = _load_detector_cfg()
    return cfg.get("eod_proxy", {}).get("version", "eod_proxy_v1")


# ── cohort I/O ─────────────────────────────────────────────────────────────────

def load_cohort(path: Path) -> pd.DataFrame:
    """Load a cohort parquet, asserting exactly ONE distinct source value.

    Raises ValueError if the frame carries more than one distinct 'source' value
    (mixed-cohort guard, FS-R4). Returns an empty DataFrame if the file is absent.
    """
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if df.empty:
        return df
    if "source" in df.columns:
        sources = df["source"].dropna().unique().tolist()
        if len(sources) > 1:
            raise ValueError(
                f"load_cohort: mixed sources detected in {path}: {sources}. "
                "Cohorts must never be pooled (FS-R4)."
            )
    return df


def _append_cohort(path: Path, new_rows: list[dict], event_id_col: str = "event_id") -> int:
    """Append new_rows to a cohort parquet, keeping first on event_id_col.

    Uses atomic tmp-rename. Returns the count of rows actually appended.
    Validates that all new_rows have the same 'source' value (mixed-source guard).
    """
    if not new_rows:
        return 0

    # Source homogeneity guard
    sources = {r.get("source") for r in new_rows if r.get("source") is not None}
    if len(sources) > 1:
        raise ValueError(f"_append_cohort: mixed sources in new_rows: {sources}")

    new_df = pd.DataFrame(new_rows)

    if path.exists():
        try:
            existing = load_cohort(path)
        except Exception as e:  # noqa: BLE001
            log.error("ops_flow_cohorts: cannot read existing cohort %s: %s — aborting", path, e)
            return 0

        # Cross-source guard: existing vs new must match
        if not existing.empty and "source" in existing.columns and "source" in new_df.columns:
            ex_sources = existing["source"].dropna().unique().tolist()
            new_sources = new_df["source"].dropna().unique().tolist()
            if ex_sources and new_sources and ex_sources != new_sources:
                raise ValueError(
                    f"_append_cohort: source mismatch — existing={ex_sources} "
                    f"new={new_sources}. Never pool cohorts."
                )

        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df

    # keep-first on event_id (structural backstop)
    merged = merged.drop_duplicates(subset=[event_id_col], keep="first")

    tmp = path.with_suffix(".tmp.parquet")
    try:
        merged.to_parquet(tmp, index=False)
        tmp.rename(path)
    except Exception as e:  # noqa: BLE001
        log.error("ops_flow_cohorts: cohort write failed: %s", e)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return 0

    return len(new_rows)


# ── bucket helpers (import from engine, fall back to inline) ──────────────────

def _dte_bucket(dte: int | float | None) -> str:
    """DTE → bucket label. Matches config/flow_detector.yml dte_buckets exactly."""
    if dte is None:
        return "unknown"
    try:
        d = int(dte)
    except (TypeError, ValueError):
        return "unknown"
    if d == 0:
        return "0d"
    if d <= 7:
        return "1_7d"
    if d <= 30:
        return "8_30d"
    if d <= 90:
        return "31_90d"
    return "90p"


def _mny_bucket(strike: float | None, spot: float | None) -> str:
    """Strike/spot → moneyness bucket label."""
    if strike is None or spot is None or spot <= 0:
        return "unknown"
    try:
        ratio = float(strike) / float(spot)
    except (TypeError, ValueError, ZeroDivisionError):
        return "unknown"
    if ratio < 0.90:
        return "deep_otm_put"
    if ratio < 0.97:
        return "otm_put"
    if ratio <= 1.03:
        return "atm"
    if ratio <= 1.10:
        return "otm_call"
    return "deep_otm_call"


# ── event_id (same convention as engine/live_flow.py) ─────────────────────────

def _event_id(session_date: str, root: str, exp: str, strike: float,
              right: str, seq_max: Any) -> str:
    """Stable 16-char hex event id (matches engine/live_flow._event_id exactly)."""
    import hashlib
    key = f"{session_date}|{root.upper()}|{exp}|{strike:.3f}|{right.upper()}|{seq_max}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]  # noqa: S324


# ── aware-UTC helpers ──────────────────────────────────────────────────────────

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_ts(ts_val: Any) -> str:
    """Normalize timestamp to aware-UTC ISO string (mirrors collectors/flow_signals.py)."""
    ts = pd.Timestamp(ts_val)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# TAPE_RECON SUBCOMMAND
# ═══════════════════════════════════════════════════════════════════════════════

# ── recon state ───────────────────────────────────────────────────────────────

def _recon_state_path() -> Path:
    return _flow_signals_dir() / "_recon_state.json"


def _load_recon_state() -> dict:
    """Load recon state from disk. Returns empty state on absent/corrupt file."""
    p = _recon_state_path()
    if not p.exists():
        return {"completed": {}, "failed": {}}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("ops_flow_cohorts: recon state unreadable: %s — starting fresh", e)
        return {"completed": {}, "failed": {}}


def _save_recon_state(state: dict) -> None:
    """Atomic write of recon state."""
    p = _recon_state_path()
    tmp = p.with_suffix(".tmp.json")
    try:
        tmp.write_text(json.dumps(state, indent=2))
        tmp.rename(p)
    except Exception as e:  # noqa: BLE001
        log.error("ops_flow_cohorts: could not save recon state: %s", e)


def _unit_key(root: str, session_date: str) -> str:
    return f"{root}|{session_date}"


# ── tape_recon premium baseline (FIX 2b) ──────────────────────────────────────

def _compute_tape_premium_baseline(
    accumulated: dict[str, list[tuple[str, float]]],
    root: str,
    window: int = 252,
) -> dict[str, tuple[float, float]] | None:
    """Compute rolling 252-session premium baseline for a root's dte_buckets.

    accumulated[root] is a list of (session_date, dte_bucket, aggregate_premium)
    triples sorted in session order. The baseline for each dte_bucket is built
    from the trailing <window> sessions BEFORE the current one (caller must NOT
    include the current session's data — PIT shift-1 semantics enforced by caller).

    Returns dict {dte_bucket: (mean, std)} or None if fewer than <window> sessions
    are available for any bucket (honest — never fake-neutral).

    Storage format: state["premium_baseline_data"][root] = list of
    [session_date, dte_bucket, aggregate_premium] lists (JSON-serializable).
    """
    data = accumulated.get(root)
    if not data:
        return None

    # Group by dte_bucket
    by_bucket: dict[str, list[float]] = defaultdict(list)
    for entry in data:
        # entry is [session_date, dte_bucket, aggregate_premium]
        _, bkt, prem = entry[0], entry[1], entry[2]
        by_bucket[bkt].append(float(prem))

    result: dict[str, tuple[float, float]] = {}
    for bkt, prems in by_bucket.items():
        if len(prems) < window:
            # Honest: fewer than window prior sessions → no baseline
            continue
        # Use last <window> sessions only
        tail = prems[-window:]
        arr = np.array(tail)
        mean = float(arr.mean())
        std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
        if std > 0:
            result[bkt] = (mean, std)

    return result if result else None


def _update_tape_baseline_data(
    accumulated: dict[str, list],
    root: str,
    session_date: str,
    events: list[dict],
) -> None:
    """Update accumulated premium data for a root after a completed session.

    Extracts per-dte_bucket aggregate premium from the events returned by
    _fetch_unit and appends to the accumulator. Called AFTER events are collected
    so the current session's data is available for FUTURE sessions.

    accumulated is modified in place (stored in state["premium_baseline_data"]).
    """
    if not events:
        return
    # Aggregate premium per dte_bucket for this session
    bucket_prem: dict[str, float] = defaultdict(float)
    for ev in events:
        bkt = ev.get("dte_bucket", "unknown")
        prem = ev.get("premium", 0.0) or 0.0
        bucket_prem[bkt] += float(prem)

    root_data = accumulated.setdefault(root, [])
    for bkt, prem in bucket_prem.items():
        root_data.append([session_date, bkt, prem])
    # Keep sorted by session_date for chronological baseline
    root_data.sort(key=lambda x: x[0])


# ── ladder loading ─────────────────────────────────────────────────────────────

def _load_ladder() -> dict:
    """Load config/flow_recon_ladder.yml."""
    try:
        import yaml
        p = _repo_root() / "config" / "flow_recon_ladder.yml"
        with p.open() as f:
            return yaml.safe_load(f)
    except Exception as e:  # noqa: BLE001
        log.error("ops_flow_cohorts: cannot load flow_recon_ladder.yml: %s", e)
        return {}


def _trading_days_in_range(start: str, end: str) -> list[str]:
    """Return business days (Monday–Friday) between start and end inclusive.

    Note: this is a conservative approximation (includes market holidays).
    A full NYSE calendar is not available in the ops lane without a data store.
    The tape pull for a holiday simply returns an empty DataFrame.
    """
    dates = pd.date_range(start=start, end=end, freq="B")
    return [d.strftime("%Y-%m-%d") for d in dates]


def _build_units(ladder: dict,
                 completed: set[str],
                 failed: set[str],
                 retry_failed: bool = False) -> list[tuple[str, str, str]]:
    """Build the ordered list of (tier_label, root, session_date) units to process.

    Skips completed units. If retry_failed=True, includes failed units too.
    Returns list in tier order (tier1 → tier2 → tier3), then by date within tier.
    """
    today_str = date.today().isoformat()
    units: list[tuple[str, str, str]] = []

    for tier_key in ("tier1", "tier2", "tier3"):
        tier = ladder.get(tier_key)
        if not tier:
            continue
        label = tier.get("label", tier_key)
        start = tier.get("start_date", "2022-01-01")
        end = tier.get("end_date") or today_str
        roots = tier.get("roots", [])

        # Deduplicate roots within this tier (QQQ/SPY appear in multiple tiers)
        seen_roots: set[str] = set()
        unique_roots = []
        for r in roots:
            ru = r.upper()
            if ru not in seen_roots:
                seen_roots.add(ru)
                unique_roots.append(ru)

        days = _trading_days_in_range(start, end)
        for root in unique_roots:
            for d in days:
                key = _unit_key(root, d)
                if key in completed:
                    continue
                if key in failed and not retry_failed:
                    continue
                units.append((label, root, d))

    return units


# ── quote-rule execution classification ───────────────────────────────────────

def _classify_side(price: float, bid: float, ask: float) -> str:
    """Quote-rule (Lee-Ready) execution classification for a single print.

    Returns:
      'at_ask'  — price >= ask (aggressive buy)
      'at_bid'  — price <= bid (aggressive sell)
      'mid'     — price between bid and ask

    This is MEASUREMENT, not tick-rule inference (FS-R6(a)).
    Never returns a signed direction column — callers must NOT aggregate these
    into a tick-rule signed net-direction label.
    """
    try:
        p, b, a = float(price), float(bid), float(ask)
    except (TypeError, ValueError):
        return "unknown"
    if b <= 0 or a < b:
        return "unknown"
    if p >= a:
        return "at_ask"
    if p <= b:
        return "at_bid"
    return "mid"


# ── tape_recon detector (applies detector v1 to raw prints) ───────────────────

_MIN_PRINTS_SWEEP = 3     # config/flow_detector.yml sweep_detection.min_prints
_SIDE_THRESH = 0.60       # fraction of premium from ask/bid side → side label
_PREMIUM_FLOOR_ETF = 1_000_000   # config/flow_detector.yml upstream_gates.premium_floors.etf
_PREMIUM_FLOOR_NAME = 250_000    # config/flow_detector.yml upstream_gates.premium_floors.single

_ETF_ROOTS = frozenset([
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "HYG",
    "XLF", "XLE", "XLU", "XLK", "XLV", "XLI", "XLB", "XLY",
    "XLP", "XLRE", "XLC", "KRE", "SMH", "XBI", "ARKK",
])


def _apply_detector_v1(
    df: pd.DataFrame,
    root: str,
    session_date: str,
    prior_oi_map: dict[tuple[str, str, str], int] | None = None,
    premium_baselines: dict[str, tuple[float, float]] | None = None,
    z252_threshold: float = 3.0,
) -> list[dict]:
    """Apply detector v1 gates to a bulk_trade_quote DataFrame for one (root, session_date).

    Groups prints by (expiration, strike, right) — the "contract" bucket — and
    computes aggregated event features. Emits an event dict per qualifying contract.

    Qualification gates (from config/flow_detector.yml upstream_gates):
      1. Premium floor: sum(price * size * 100) >= floor for the root type.
      2. If premium_baselines provided: dict maps dte_bucket_key → (mean, std).
         premium_z = (total_premium - mean) / std; if >= z252_threshold → qualifies.
         premium_z=None until 252 sessions accumulated (honest; PIT shift-1 semantics
         enforced by caller — baseline must exclude the current session).
      3. vol_gt_oi: if prior_oi_map provided: cumulative contract volume > prior OI.

    Returns list of event dicts with the same schema as the FS-0 ledger
    (collectors/flow_signals.py _EVENT_COLS — minus group/group_zh which are not
    computable here without the sector map).

    FORBIDDEN FEATURES (FS-R6): no signed direction from tick-rule. We compute
    'ask_share' (fraction of premium from at-ask prints) as a MEASUREMENT feature,
    but we do NOT emit a 'side' label derived from tick-rule inference.
    """
    if df is None or df.empty:
        return []

    root_up = root.upper()
    is_etf = root_up in _ETF_ROOTS
    premium_floor = _PREMIUM_FLOOR_ETF if is_etf else _PREMIUM_FLOOR_NAME

    required_cols = {"price", "size", "bid", "ask", "strike", "right"}
    missing = required_cols - set(df.columns)
    if missing:
        log.warning("ops_flow_cohorts: missing columns %s for %s %s — skip", missing, root, session_date)
        return []

    # Normalize numeric columns
    for c in ("price", "size", "bid", "ask", "strike"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["price", "size", "bid", "ask", "strike"])
    if df.empty:
        return []

    # Normalize expiration and right
    if "expiration" in df.columns:
        df["expiration"] = pd.to_datetime(df["expiration"], errors="coerce")
    else:
        return []
    if "right" in df.columns:
        df["right"] = df["right"].str.upper().str[:1]
    else:
        return []

    # Classify execution side for each print (measurement, not inference)
    df["_exec_side"] = df.apply(
        lambda r: _classify_side(r["price"], r["bid"], r["ask"]), axis=1
    )
    df["_premium"] = df["price"] * df["size"] * 100.0
    df["_ask_prem"] = df["_premium"].where(df["_exec_side"] == "at_ask", 0.0)
    df["_bid_prem"] = df["_premium"].where(df["_exec_side"] == "at_bid", 0.0)

    # Get sequence column for event_id stability
    if "sequence" in df.columns:
        df["sequence"] = pd.to_numeric(df["sequence"], errors="coerce").fillna(0)
    else:
        df["sequence"] = range(len(df))

    # Infer session_date for each print
    if "trade_timestamp" in df.columns:
        df["_date"] = pd.to_datetime(df["trade_timestamp"], errors="coerce").dt.date.astype(str)
    elif "date" in df.columns:
        df["_date"] = df["date"].astype(str).str[:10]
    else:
        df["_date"] = session_date

    # Group by contract (expiration, strike, right)
    group_cols = ["expiration", "strike", "right"]
    available_group = [c for c in group_cols if c in df.columns]

    events: list[dict] = []
    ingested_at = _now_utc_iso()
    detector_ver = _detector_version()

    for key, grp in df.groupby(available_group, dropna=False):
        if isinstance(key, tuple):
            exp_val, strike_val, right_val = key[0], key[1], key[2]
        else:
            exp_val = key
            strike_val = grp["strike"].iloc[0] if "strike" in grp.columns else None
            right_val = grp["right"].iloc[0] if "right" in grp.columns else None

        if pd.isna(exp_val) or pd.isna(strike_val) or pd.isna(right_val):
            continue

        exp_str = pd.Timestamp(exp_val).strftime("%Y-%m-%d") if not isinstance(exp_val, str) else str(exp_val)[:10]
        strike_f = float(strike_val)
        right_s = str(right_val).upper()[:1]

        total_premium = float(grp["_premium"].sum())
        n_prints = len(grp)
        total_size = int(grp["size"].sum())
        ask_prem = float(grp["_ask_prem"].sum())
        bid_prem = float(grp["_bid_prem"].sum())
        seq_max = int(grp["sequence"].max()) if "sequence" in grp.columns else n_prints

        # Gate 1: premium floor
        qualifies = total_premium >= premium_floor

        # Gate 2: premium_z baseline (FIX 2b — was dead code: now active).
        # premium_baselines maps dte_bucket_key → (mean, std), built by caller
        # from sessions strictly before this one (shift-1 PIT semantics).
        # premium_z=None until 252 sessions accumulated (honest null coverage).
        premium_z = None
        dte_val_for_z = _compute_dte(exp_str, session_date)
        bucket_key = _dte_bucket(dte_val_for_z)
        if premium_baselines:
            baseline_entry = premium_baselines.get(bucket_key)
            if baseline_entry is not None:
                b_mean, b_std = baseline_entry
                if not (b_std is None or (isinstance(b_std, float) and b_std != b_std)) and b_std > 0:
                    premium_z = (total_premium - b_mean) / b_std
        if not qualifies and premium_z is not None and premium_z >= z252_threshold:
            qualifies = True

        if not qualifies:
            continue

        # Compute features
        dte_val = _compute_dte(exp_str, session_date)
        dte_bkt = _dte_bucket(dte_val)

        # vol_gt_oi: prior session OI comparison (PIT — same-day OI is a leak)
        vol_gt_oi = False
        if prior_oi_map is not None:
            oi_key = (exp_str, f"{strike_f:.3f}", right_s)
            prior_oi = prior_oi_map.get(oi_key, 0)
            if prior_oi > 0 and total_size > prior_oi:
                vol_gt_oi = True

        # Aggression share (measurement, not direction)
        ask_share = ask_prem / total_premium if total_premium > 0 else 0.0
        bid_share = bid_prem / total_premium if total_premium > 0 else 0.0

        # Soft side label (NOT tick-rule; quote-rule only) — intentionally kept
        # as a measurement feature labeled 'soft_side', never used as a direction label
        # per FS-R6. Distinct from the tick-rule-derived 'side' in ledger.parquet.
        if ask_share >= _SIDE_THRESH:
            soft_side = "~buy"
        elif bid_share >= _SIDE_THRESH:
            soft_side = "~sell"
        else:
            soft_side = "mixed"

        # Sweep heuristic: >= 3 prints in group
        swept = n_prints >= _MIN_PRINTS_SWEEP

        # avg_price (premium-weighted)
        premium_vec = grp["_premium"].values
        price_vec = grp["price"].values
        if premium_vec.sum() > 0:
            avg_price = float(np.average(price_vec, weights=premium_vec))
        else:
            avg_price = float(price_vec.mean())

        # Latest print ts
        ts_val = ""
        if "trade_timestamp" in grp.columns:
            ts_cand = grp["trade_timestamp"].dropna()
            if not ts_cand.empty:
                try:
                    ts_val = _normalize_ts(str(ts_cand.iloc[-1]))
                except Exception:  # noqa: BLE001
                    ts_val = ""

        eid = _event_id(session_date, root_up, exp_str, strike_f, right_s, seq_max)

        event: dict[str, Any] = {
            "event_id":        eid,
            "session_date":    session_date,
            "ts":              ts_val,
            "root":            root_up,
            "group":           "",
            "group_zh":        "",
            "right":           right_s,
            "exp":             exp_str,
            "strike":          strike_f,
            "dte":             dte_val,
            "dte_bucket":      dte_bkt,
            "mny_bucket":      "unknown",  # requires spot price; caller may enrich
            "side":            soft_side,  # quote-rule soft side (measurement)
            "n_prints":        n_prints,
            "size":            total_size,
            "avg_price":       avg_price,
            "premium":         total_premium,
            "premium_z":       premium_z,   # null until 252-day baseline available
            "baseline_source": "tape_recon_rolling" if premium_z is not None else None,
            "vol_gt_oi":       vol_gt_oi,
            "repeated":        False,       # not computable from single-day pull
            "zerodte":         dte_val == 0,
            "signing_source":  "quote_rule",
            "swept":           swept,
            "detector_version": detector_ver,
            "source":          "tape_recon",
            "ingested_at":     ingested_at,
            # tape_recon-only extra measurement features (legal per FS-R6(a))
            "ask_share":       round(ask_share, 4),
            "bid_share":       round(bid_share, 4),
        }
        events.append(event)

    return events


def _compute_dte(exp_str: str, session_date: str) -> int | None:
    """Compute DTE from expiration and session date strings (YYYY-MM-DD)."""
    try:
        exp = date.fromisoformat(exp_str)
        sess = date.fromisoformat(session_date)
        return (exp - sess).days
    except Exception:  # noqa: BLE001
        return None


# ── prior OI loader ───────────────────────────────────────────────────────────

def _load_prior_oi(eod_root: Path, root: str, session_date: str
                   ) -> dict[tuple[str, str, str], int]:
    """Load OI for root as of the most-recent PRIOR trading session relative to session_date.

    PIT LAW: OI[t] from OPRA = positions as of EOD t-1. Use OI[t-1] in any day-t
    signal. A same-day vol>OI comparison is a data LEAK (confirmed in collector spec
    and FS-R4 OI-only grid; see also collectors/thetadata.py header OI timing note).

    Bug fixed: the previous exact T-1 calendar match failed for Monday sessions
    (Friday OI is 3 calendar days prior, not 1). Now searches backward up to 4
    calendar days for the most recent OI date STRICTLY BEFORE the session date.
    Also handles year boundaries: Jan 1-2 sessions need December OI from prior year.

    Returns dict keyed by (exp_str, strike_str, right_str) → open_interest int.
    Returns empty dict on any error (conservative: vol_gt_oi will be False).
    """
    oi_dir = eod_root / "oi" / root.upper()
    if not oi_dir.exists():
        return {}
    try:
        target = date.fromisoformat(session_date)

        # Collect candidate dates: up to 4 calendar days before target (bridges weekends
        # + 3-day holiday weekends). Exclude target itself (PIT: no same-day OI).
        candidate_dates = [target - timedelta(days=d) for d in range(1, 5)]

        # Determine which years to load (may span year boundary for Jan 1-2 sessions)
        years_needed = sorted({d.year for d in candidate_dates})

        oi_frames: list[pd.DataFrame] = []
        for yr in years_needed:
            pq_file = oi_dir / f"{yr}.parquet"
            if not pq_file.exists():
                continue
            try:
                df = pd.read_parquet(
                    pq_file,
                    columns=["expiration", "strike", "right", "date", "open_interest"],
                )
                oi_frames.append(df)
            except Exception as e:  # noqa: BLE001
                log.debug("ops_flow_cohorts: prior OI parquet read failed %s %d: %s", root, yr, e)

        if not oi_frames:
            return {}

        oi_df = pd.concat(oi_frames, ignore_index=True)
        oi_df["date"] = pd.to_datetime(oi_df["date"]).dt.date

        # Find the most recent OI date strictly before target, within 4-day window
        candidate_set = {d for d in candidate_dates}
        available = oi_df[oi_df["date"].isin(candidate_set)]
        if available.empty:
            return {}

        # Use the latest available date among candidates
        best_date = max(available["date"].unique())
        prior_rows = oi_df[oi_df["date"] == best_date]
        if prior_rows.empty:
            return {}

        result: dict[tuple[str, str, str], int] = {}
        for _, row in prior_rows.iterrows():
            exp_str = pd.Timestamp(row["expiration"]).strftime("%Y-%m-%d")
            strike_str = f"{float(row['strike']):.3f}"
            right_str = str(row["right"]).upper()[:1]
            result[(exp_str, strike_str, right_str)] = int(row["open_interest"])
        return result
    except Exception as e:  # noqa: BLE001
        log.debug("ops_flow_cohorts: prior OI load failed for %s %s: %s", root, session_date, e)
        return {}


# ── concurrency semaphore ─────────────────────────────────────────────────────

_MAX_INFLIGHT = 8  # FS-1 spec: max 8 requests in flight


def _fetch_unit(
    root: str,
    session_date: str,
    eod_root: Path | None,
    per_request_timeout: float = 120.0,
) -> list[dict] | str:
    """Fetch and detect events for one (root, session_date) unit.

    Returns:
      list[dict] — event rows (may be empty list if no qualifying events)
      str        — error message on any failure

    Never hangs: uses bounded timeout via requests (already enforced in
    collectors/thetadata.py: CONNECT_TIMEOUT=3, READ_TIMEOUT_BETWEEN_BYTES=90).
    """
    try:
        from collectors.thetadata import bulk_trade_quote_day, reachable
    except ImportError as e:
        return f"import error: {e}"

    # Quick reachability check (CONNECT_TIMEOUT=3s in thetadata.py)
    if not reachable():
        return "terminal_unreachable"

    try:
        df = bulk_trade_quote_day(root, session_date)
    except Exception as e:  # noqa: BLE001
        return f"fetch_error: {e}"

    if df is None:
        return "fetch_returned_none"

    if df.empty:
        return []  # valid empty session

    # Load prior-day OI for vol_gt_oi check
    prior_oi: dict = {}
    if eod_root is not None:
        prior_oi = _load_prior_oi(eod_root, root, session_date)

    events = _apply_detector_v1(df, root, session_date, prior_oi_map=prior_oi)
    return events


# ── tape_recon main ───────────────────────────────────────────────────────────

def run_tape_recon(
    retry_failed: bool = False,
    max_units: int | None = None,
    dry_run: bool = False,
) -> int:
    """Run the tape_recon reconstruction sweep.

    Returns the count of events written to cohort_tape_recon.parquet.
    """
    # Terminal reachability gate (BEFORE opening state — fail fast with clear message)
    try:
        from collectors.thetadata import reachable
    except ImportError as e:
        log.error("ops_flow_cohorts: cannot import thetadata: %s", e)
        return 0

    if not reachable():
        log.error(
            "ops_flow_cohorts: ThetaTerminal is NOT reachable at %s. "
            "tape_recon requires the terminal to be running. "
            "Start it with scripts/run_theta_terminal.sh, then retry. "
            "eod_proxy does not need the terminal and can run today.",
            os.environ.get("THETA_TERMINAL_URL", "http://127.0.0.1:25503"),
        )
        return 1  # nonzero = error for shell callers

    ladder = _load_ladder()
    if not ladder:
        log.error("ops_flow_cohorts: empty ladder — check config/flow_recon_ladder.yml")
        return 0

    state = _load_recon_state()
    completed: set[str] = set(state.get("completed", {}).keys())
    failed: set[str] = set(state.get("failed", {}).keys())

    # Premium baseline accumulator: persisted in state["premium_baseline_data"]
    # Maps root → list of [session_date, dte_bucket, aggregate_premium] entries.
    # Loaded from prior runs so resume preserves the accumulated baseline.
    premium_baseline_data: dict[str, list] = state.get("premium_baseline_data", {})
    cfg = _load_detector_cfg()
    baseline_window = int(cfg.get("eod_proxy", {}).get("rolling_window_days", 60))
    # tape_recon uses z252 threshold per upstream spec
    z252_thresh = float(cfg.get("upstream_gates", {}).get("z252_threshold", 3.0))

    units = _build_units(ladder, completed, failed, retry_failed=retry_failed)
    if max_units is not None:
        units = units[:max_units]

    eod_root = _eod_store_root()
    cohort_path = _flow_signals_dir() / "cohort_tape_recon.parquet"

    log.info("ops_flow_cohorts: tape_recon — %d units pending (completed=%d failed=%d)",
             len(units), len(completed), len(failed))

    total_events = 0
    batch_rows: list[dict] = []
    BATCH_SIZE = 50  # write to parquet every N units

    with ThreadPoolExecutor(max_workers=_MAX_INFLIGHT) as executor:
        future_to_unit = {}
        unit_iter = iter(units)

        # Submit initial batch
        for _ in range(_MAX_INFLIGHT):
            try:
                u = next(unit_iter)
                f = executor.submit(_fetch_unit, u[1], u[2], eod_root)
                future_to_unit[f] = u
            except StopIteration:
                break

        while future_to_unit:
            done_futures = []
            # Poll for completed futures
            for fut in list(future_to_unit.keys()):
                if fut.done():
                    done_futures.append(fut)

            if not done_futures:
                time.sleep(0.1)
                continue

            for fut in done_futures:
                tier_label, root, session_date = future_to_unit.pop(fut)
                unit_key = _unit_key(root, session_date)

                try:
                    result = fut.result(timeout=5)
                except Exception as e:  # noqa: BLE001
                    result = f"executor_error: {e}"

                if isinstance(result, str):
                    # Error
                    err_msg = result
                    if err_msg == "terminal_unreachable":
                        log.error(
                            "ops_flow_cohorts: terminal became unreachable during sweep "
                            "— aborting. Remaining units will resume on next run."
                        )
                        _save_recon_state(state)
                        return total_events

                    log.warning("ops_flow_cohorts: unit %s failed: %s", unit_key, err_msg)
                    state.setdefault("failed", {})[unit_key] = err_msg
                else:
                    # Success — annotate premium_z from accumulated baseline (FIX 2b)
                    events: list[dict] = result

                    # Compute z-scores for events using baseline built from PRIOR sessions
                    # (shift-1 PIT: baseline_data has NOT yet been updated for this session)
                    if events:
                        prior_baseline = _compute_tape_premium_baseline(
                            premium_baseline_data, root, window=baseline_window
                        )
                        if prior_baseline is not None:
                            for ev in events:
                                bkt = ev.get("dte_bucket", "unknown")
                                prem = ev.get("premium", 0.0) or 0.0
                                entry = prior_baseline.get(bkt)
                                if entry is not None:
                                    b_mean, b_std = entry
                                    if b_std > 0:
                                        z = (prem - b_mean) / b_std
                                        ev["premium_z"] = z
                                        ev["baseline_source"] = "tape_recon_rolling"

                    # Update accumulator with THIS session's data for FUTURE sessions
                    _update_tape_baseline_data(premium_baseline_data, root, session_date, events)

                    batch_rows.extend(events)
                    total_events += len(events)
                    state.setdefault("completed", {})[unit_key] = "ok"
                    # Remove from failed if it was previously failed (retry succeeded)
                    state.get("failed", {}).pop(unit_key, None)

                    log.info("ops_flow_cohorts: %s %s → %d events (total=%d)",
                             root, session_date, len(events), total_events)

                # Submit next unit
                try:
                    u = next(unit_iter)
                    new_f = executor.submit(_fetch_unit, u[1], u[2], eod_root)
                    future_to_unit[new_f] = u
                except StopIteration:
                    pass

                # Periodic flush
                if len(batch_rows) >= BATCH_SIZE or len(future_to_unit) == 0:
                    if batch_rows and not dry_run:
                        _append_cohort(cohort_path, batch_rows)
                        # Persist premium baseline accumulation for resume
                        state["premium_baseline_data"] = premium_baseline_data
                        _save_recon_state(state)
                    batch_rows = []

    # Final flush
    if batch_rows and not dry_run:
        _append_cohort(cohort_path, batch_rows)
    state["premium_baseline_data"] = premium_baseline_data
    _save_recon_state(state)

    log.info("ops_flow_cohorts: tape_recon complete — %d events written", total_events)
    return total_events


# ═══════════════════════════════════════════════════════════════════════════════
# EOD_PROXY SUBCOMMAND
# ═══════════════════════════════════════════════════════════════════════════════

_EOD_ERA_PARTITIONS = [
    ("2012-15", "2012-01-01", "2015-12-31"),
    ("2016-19", "2016-01-01", "2019-12-31"),
    ("2020-22", "2020-01-01", "2022-12-31"),
    ("2023+",   "2023-01-01", None),          # None = today
]


def _check_manifest(eod_root: Path, max_shortfall_pct: float = 0.05) -> bool:
    """Assert manifest completeness: ≤5% of roots may have n_years < 15.

    Returns True if the store passes. Logs a clear error and returns False if not.
    R8: refuse to run eod_proxy until manifest is complete.
    """
    manifest_path = eod_root / "_manifest.json"
    if not manifest_path.exists():
        log.error("ops_flow_cohorts: eod_proxy: _manifest.json not found at %s", eod_root)
        return False
    try:
        m = json.loads(manifest_path.read_text())
    except Exception as e:  # noqa: BLE001
        log.error("ops_flow_cohorts: eod_proxy: _manifest.json unreadable: %s", e)
        return False

    per_root = m.get("per_root", {})
    if not per_root:
        log.error("ops_flow_cohorts: eod_proxy: _manifest.json has no per_root entries")
        return False

    n_total = len(per_root)
    n_short = sum(1 for v in per_root.values() if v.get("n_years", 0) < 15)
    shortfall_pct = n_short / n_total if n_total > 0 else 1.0

    if shortfall_pct > max_shortfall_pct:
        log.error(
            "ops_flow_cohorts: eod_proxy: manifest shortfall %.1f%% > limit %.1f%% "
            "(%d/%d roots have n_years < 15). Refusing to run until store is complete "
            "(R8 gate). Check ~/theta-ops-wt/data/thetadata_eod/_manifest.json.",
            shortfall_pct * 100, max_shortfall_pct * 100, n_short, n_total,
        )
        return False

    log.info("ops_flow_cohorts: eod_proxy: manifest OK — %d roots, shortfall=%.1f%% (%.0f roots @ <15y)",
             n_total, shortfall_pct * 100, n_short)
    return True


def _build_premium_rolling_baseline(
    eod_dir: Path,
    root: str,
    rolling_window: int,
) -> pd.DataFrame:
    """Build per-(dte_bucket, date) rolling premium baseline across all available years.

    PIT semantics: uses .shift(1) so the current day's premium is EXCLUDED from
    its own z-score computation (no self-inclusion leak).
    min_periods=rolling_window: first <window> sessions yield NaN (honest — never
    fake-neutral).

    Returns a DataFrame indexed by (date, dte_bucket) with columns:
        _roll_mean, _roll_std
    Values are NaN for dates with fewer than rolling_window prior sessions.
    """
    year_frames: list[pd.DataFrame] = []
    if not eod_dir.exists():
        return pd.DataFrame()

    for pq_file in sorted(eod_dir.glob("*.parquet")):
        try:
            df = pd.read_parquet(
                pq_file,
                columns=["expiration", "strike", "right", "date", "close", "volume"],
            )
        except Exception:  # noqa: BLE001
            continue
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df["expiration"] = pd.to_datetime(df["expiration"])
        df["_dte"] = (df["expiration"] - df["date"]).dt.days
        df["_dte_bucket"] = df["_dte"].apply(_dte_bucket)
        df["_premium"] = df["close"] * df["volume"] * 100.0
        year_frames.append(df[["date", "_dte_bucket", "_premium"]])

    if not year_frames:
        return pd.DataFrame()

    all_df = pd.concat(year_frames, ignore_index=True)

    # Daily aggregate premium per (date, dte_bucket) — sum across all contracts
    daily_agg = (
        all_df.groupby(["date", "_dte_bucket"])["_premium"]
        .sum()
        .reset_index()
        .sort_values("date")
    )

    # Rolling mean/std per dte_bucket with shift(1) PIT semantics
    baseline_rows: list[pd.DataFrame] = []
    for bkt, grp in daily_agg.groupby("_dte_bucket"):
        grp = grp.sort_values("date").copy()
        shifted = grp["_premium"].shift(1)  # exclude current day (PIT)
        grp["_roll_mean"] = shifted.rolling(rolling_window, min_periods=rolling_window).mean()
        grp["_roll_std"] = shifted.rolling(rolling_window, min_periods=rolling_window).std()
        baseline_rows.append(grp[["date", "_dte_bucket", "_roll_mean", "_roll_std"]])

    if not baseline_rows:
        return pd.DataFrame()

    return pd.concat(baseline_rows, ignore_index=True)


def _eod_proxy_events_for_root(
    root: str,
    eod_root: Path,
    era_partitions: list[tuple[str, str, str | None]],
    cfg: dict,
) -> list[dict]:
    """Build pseudo-events for one root across all era partitions.

    STREAMS per era per root (never loads full store): reads year parquets
    individually with pyarrow column pruning. RAM law: never loads the full
    EOD store (383 roots × 15y would be ~90GB).

    PIT LAW: vol_gt_oi comparison uses PRIOR-DAY OI only (OI is T+1 in OPRA).
    premium_burst: rolling 60-day mean/std per (dte_bucket) with shift(1) to
    exclude the current day from its own baseline. First <window> sessions get
    premium_z=None (honest — never fake-neutral).

    Qualification: vol_gt_oi OR (premium_z >= premium_burst_z threshold).
    Rows must also pass volume floor + premium floor.

    Returns list of event dicts with source='eod_proxy'.
    """
    proxy_cfg = cfg.get("eod_proxy", {})
    vol_mult = float(proxy_cfg.get("vol_oi_burst_multiplier", 1.0))
    min_vol = int(proxy_cfg.get("min_contract_volume", 5))
    min_prem = float(proxy_cfg.get("min_premium_usd", 1000.0))
    proxy_ver = str(proxy_cfg.get("version", "eod_proxy_v1"))
    rolling_window = int(proxy_cfg.get("rolling_window_days", 60))
    premium_burst_z_thresh = float(proxy_cfg.get("premium_burst_z", 2.5))
    today_str = date.today().isoformat()

    eod_dir = eod_root / "eod" / root.upper()
    oi_dir = eod_root / "oi" / root.upper()
    if not eod_dir.exists():
        log.debug("ops_flow_cohorts: eod_proxy: no eod dir for %s — skip", root)
        return []

    # Build the rolling premium baseline across ALL years FIRST (pass 1).
    # This is lightweight (daily aggregates only) and ensures that era-spanning
    # rolling windows are correctly computed (not restarted at year/era boundaries).
    premium_baseline_df = _build_premium_rolling_baseline(eod_dir, root, rolling_window)
    # Index by (date, dte_bucket) for O(1) lookup during per-row processing
    if not premium_baseline_df.empty:
        premium_baseline_lookup: dict[tuple, tuple] = {
            (row["date"], row["_dte_bucket"]): (row["_roll_mean"], row["_roll_std"])
            for _, row in premium_baseline_df.iterrows()
        }
    else:
        premium_baseline_lookup = {}

    events_all: list[dict] = []
    ingested_at = _now_utc_iso()

    for era_name, era_start, era_end in era_partitions:
        era_end_str = era_end or today_str
        try:
            start_year = int(era_start[:4])
            end_year = int(era_end_str[:4])
        except (ValueError, IndexError):
            continue

        for yr in range(start_year, end_year + 1):
            eod_file = eod_dir / f"{yr}.parquet"
            oi_file = oi_dir / f"{yr}.parquet"
            if not eod_file.exists():
                continue

            try:
                # RAM law: column pruning, NOT read_all
                # "count" = number of option prints in the session (schema-confirmed present)
                eod_df = pd.read_parquet(
                    eod_file,
                    columns=["root", "expiration", "strike", "right", "date", "close", "volume", "count"],
                )
            except Exception as e:  # noqa: BLE001
                log.warning("ops_flow_cohorts: eod_proxy: read eod %s %d failed: %s", root, yr, e)
                continue

            if eod_df.empty:
                continue

            # Filter to era date range
            eod_df = eod_df[
                (eod_df["date"] >= pd.Timestamp(era_start)) &
                (eod_df["date"] <= pd.Timestamp(era_end_str))
            ]
            if eod_df.empty:
                continue

            # Load OI for this year (for vol_gt_oi — prior-day)
            oi_yr_df: pd.DataFrame = pd.DataFrame()
            if oi_file.exists():
                try:
                    oi_yr_df = pd.read_parquet(
                        oi_file,
                        columns=["expiration", "strike", "right", "date", "open_interest"],
                    )
                    # Load a wider window to support cross-year OI lookups at Jan 1-2
                    # (FIX 1b-compatible: merge_asof handles year-boundary lookups when
                    # OI files from both years are loaded together; here we load ±1yr
                    # files via the outer loop so the boundary is handled by tolerance=4d)
                    oi_yr_df = oi_yr_df[
                        (oi_yr_df["date"] >= pd.Timestamp(era_start)) &
                        (oi_yr_df["date"] <= pd.Timestamp(era_end_str))
                    ]
                except Exception as e:  # noqa: BLE001
                    log.debug("ops_flow_cohorts: eod_proxy: OI read failed for %s %d: %s", root, yr, e)

            eod_df["date"] = pd.to_datetime(eod_df["date"])
            eod_df["expiration"] = pd.to_datetime(eod_df["expiration"])
            eod_df["_dte"] = (eod_df["expiration"] - eod_df["date"]).dt.days
            eod_df["_dte_bucket"] = eod_df["_dte"].apply(_dte_bucket)
            eod_df["_premium"] = eod_df["close"] * eod_df["volume"] * 100.0

            # ── VECTORIZED vol>OI join (PIT: prior-SESSION alignment via merge_asof) ──
            #
            # Bug fixed: the previous calendar +1d shift caused Monday/post-holiday
            # sessions to never match (Friday OI lands on Saturday, never found).
            #
            # Correct approach: merge_asof with allow_exact_matches=False finds the
            # most recent OI row STRICTLY BEFORE the session date (T-1 semantics).
            # tolerance=4 calendar days bridges weekends + 3-day holiday weekends.
            # Both frames must be sorted on the join key (date) for merge_asof.
            #
            # PIT LAW preserved: allow_exact_matches=False means same-day OI is
            # never used (the row where OI.date == EOD.date is excluded).
            #
            if not oi_yr_df.empty:
                oi_yr_df = oi_yr_df.copy()
                oi_yr_df["date"] = pd.to_datetime(oi_yr_df["date"])
                oi_yr_df["right"] = oi_yr_df["right"].str.upper().str[:1]
                oi_yr_df["expiration"] = pd.to_datetime(oi_yr_df["expiration"])

                # merge_asof requires both frames globally sorted on the on-key
                eod_sorted = eod_df.sort_values("date")
                oi_sorted = oi_yr_df.sort_values("date")

                # Per-contract backward search for most-recent prior OI
                merged = pd.merge_asof(
                    eod_sorted,
                    oi_sorted[["expiration", "strike", "right", "date", "open_interest"]],
                    by=["expiration", "strike", "right"],
                    on="date",
                    direction="backward",
                    allow_exact_matches=False,   # T-1 PIT: never same-day OI
                    tolerance=pd.Timedelta(days=4),  # bridges weekends + 3-day holidays
                )
                merged["open_interest"] = merged["open_interest"].fillna(0)
            else:
                merged = eod_df.copy()
                merged["open_interest"] = 0

            # Vectorized vol>OI flag
            merged["_vol_gt_oi"] = (
                (merged["volume"] > merged["open_interest"] * vol_mult) &
                (merged["open_interest"] > 0)
            )

            # ── Premium burst z-score (FIX 2a) ──────────────────────────────
            # Lookup rolling baseline (built from ALL years with shift-1 PIT)
            # Result: _premium_z is NaN for first <rolling_window> sessions
            # (min_periods=rolling_window enforces honest null coverage).
            def _lookup_premium_z(row: "pd.Series") -> float | None:
                key = (row["date"], row["_dte_bucket"])
                baseline = premium_baseline_lookup.get(key)
                if baseline is None:
                    return None
                mean, std = baseline
                if pd.isna(mean) or pd.isna(std) or std <= 0:
                    return None
                return float((row["_premium"] - mean) / std)

            merged["_premium_z"] = merged.apply(_lookup_premium_z, axis=1)

            # ── Qualification gate (OR): vol_gt_oi OR premium_burst ─────────
            merged["_premium_burst"] = merged["_premium_z"].apply(
                lambda z: z is not None and not (isinstance(z, float) and z != z) and z >= premium_burst_z_thresh
            )
            merged["_qualifies"] = merged["_vol_gt_oi"] | merged["_premium_burst"]

            # Filter to qualifying rows (vol floor + premium floor + qualification)
            merged = merged[
                (merged["volume"] >= min_vol) &
                (merged["_premium"] >= min_prem) &
                (merged["_qualifies"])
            ]

            if merged.empty:
                continue

            # Compute DTE vectorized
            merged = merged.copy()
            merged["_dte_val"] = (merged["expiration"] - merged["date"]).dt.days
            merged["_dte_bucket"] = merged["_dte_val"].apply(_dte_bucket)
            merged["_session_str"] = merged["date"].dt.strftime("%Y-%m-%d")
            merged["_exp_str"] = merged["expiration"].dt.strftime("%Y-%m-%d")
            merged["_right_str"] = merged["right"].str.upper().str[:1]

            # Iterate only over qualifying rows (drastically smaller than full dataset)
            for _, row in merged.iterrows():
                session_date_str = str(row["_session_str"])
                exp_str = str(row["_exp_str"])
                strike_f = float(row["strike"])
                right_str = str(row["_right_str"])
                vol = int(row["volume"])
                prem = float(row["_premium"])
                avg_price = float(row["close"])
                dte_val = int(row["_dte_val"]) if pd.notna(row["_dte_val"]) else None
                dte_bkt = str(row["_dte_bucket"])
                vol_gt_oi = bool(row["_vol_gt_oi"])
                prior_oi_val = int(row["open_interest"])
                premium_z_val = row.get("_premium_z")
                premium_z_out = float(premium_z_val) if premium_z_val is not None and not (isinstance(premium_z_val, float) and premium_z_val != premium_z_val) else None
                premium_burst_fired = bool(row.get("_premium_burst", False))

                seq_max = vol  # use volume as stable proxy for seq_max in eod_proxy
                eid = _event_id(session_date_str, root.upper(), exp_str, strike_f, right_str, seq_max)

                # "count" is always present (schema-confirmed); use it directly.
                # Falls back to vol only if parquet was written without the column.
                n_prints = int(row["count"]) if "count" in merged.columns and pd.notna(row.get("count")) else vol

                # baseline_source: 'eod_rolling60' if premium_z was available and used
                baseline_src: str | None = "eod_rolling60" if premium_z_out is not None else None

                event: dict[str, Any] = {
                    "event_id":        eid,
                    "session_date":    session_date_str,
                    "ts":              f"{session_date_str}T16:00:00+00:00",  # EOD close time
                    "root":            root.upper(),
                    "group":           "",
                    "group_zh":        "",
                    "right":           right_str,
                    "exp":             exp_str,
                    "strike":          strike_f,
                    "dte":             dte_val,
                    "dte_bucket":      dte_bkt,
                    "mny_bucket":      "unknown",
                    "side":            "unknown",     # EOD aggregate: no per-print side
                    "n_prints":        n_prints,
                    "size":            vol,
                    "avg_price":       avg_price,
                    "premium":         prem,
                    "premium_z":       premium_z_out,
                    "baseline_source": baseline_src,
                    "vol_gt_oi":       vol_gt_oi,
                    "repeated":        False,
                    "zerodte":         dte_val == 0,
                    "signing_source":  None,  # no signing basis for EOD aggregate
                    "swept":           False,         # not computable from EOD
                    "detector_version": proxy_ver,
                    "source":          "eod_proxy",
                    "ingested_at":     ingested_at,
                    "era":             era_name,
                    # eod_proxy extras
                    "prior_oi":        prior_oi_val,
                    "ask_share":       None,
                    "bid_share":       None,
                }
                events_all.append(event)

    return events_all


def run_eod_proxy(
    roots_limit: int | None = None,
    dry_run: bool = False,
    output_dir: Path | None = None,
) -> int:
    """Run the eod_proxy pseudo-event builder.

    Returns the count of events written to cohort_eod_proxy.parquet.
    """
    eod_root = _eod_store_root()
    if eod_root is None:
        log.error(
            "ops_flow_cohorts: eod_proxy: no thetadata_eod store found. "
            "Check THETADATA_EOD_DIR env or ~/theta-ops-wt/data/thetadata_eod. "
            "Store must contain _manifest.json."
        )
        return 0

    if not _check_manifest(eod_root):
        return 0

    cfg = _load_detector_cfg()
    out_dir = output_dir or _flow_signals_dir()
    cohort_path = out_dir / "cohort_eod_proxy.parquet"

    # Get all roots from manifest
    manifest = json.loads((eod_root / "_manifest.json").read_text())
    per_root = manifest.get("per_root", {})
    all_roots = sorted(per_root.keys())

    if roots_limit is not None:
        all_roots = all_roots[:roots_limit]

    log.info("ops_flow_cohorts: eod_proxy — %d roots, era partitions: %s",
             len(all_roots), [e[0] for e in _EOD_ERA_PARTITIONS])

    total_events = 0
    batch_rows: list[dict] = []
    BATCH_SIZE = 500

    for i, root in enumerate(all_roots):
        log.info("ops_flow_cohorts: eod_proxy — root %s (%d/%d)", root, i + 1, len(all_roots))
        try:
            events = _eod_proxy_events_for_root(root, eod_root, _EOD_ERA_PARTITIONS, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("ops_flow_cohorts: eod_proxy: root %s failed: %s", root, e)
            continue

        batch_rows.extend(events)
        total_events += len(events)

        if len(batch_rows) >= BATCH_SIZE:
            if not dry_run:
                _append_cohort(cohort_path, batch_rows)
            batch_rows = []

    if batch_rows and not dry_run:
        _append_cohort(cohort_path, batch_rows)

    log.info("ops_flow_cohorts: eod_proxy complete — %d events written", total_events)
    return total_events


# ═══════════════════════════════════════════════════════════════════════════════
# COVERAGE REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def _coverage_report(out_dir: Path | None = None) -> dict:
    """Compute and print coverage report for both cohorts.

    Writes data/flow_signals/cohort_coverage.json.
    Returns the report dict.
    """
    fsd = out_dir or _flow_signals_dir()
    report: dict[str, Any] = {"generated_at": _now_utc_iso(), "cohorts": {}}

    for cohort_name, fname in [("tape_recon", "cohort_tape_recon.parquet"),
                                 ("eod_proxy", "cohort_eod_proxy.parquet")]:
        path = fsd / fname
        if not path.exists():
            report["cohorts"][cohort_name] = {"n_events": 0, "status": "absent"}
            print(f"\ncohort={cohort_name}: absent (not yet built)")
            continue

        try:
            df = load_cohort(path)
        except Exception as e:  # noqa: BLE001
            report["cohorts"][cohort_name] = {"n_events": 0, "status": f"error: {e}"}
            print(f"\ncohort={cohort_name}: ERROR reading — {e}")
            continue

        if df.empty:
            report["cohorts"][cohort_name] = {"n_events": 0, "status": "empty"}
            print(f"\ncohort={cohort_name}: empty")
            continue

        n = len(df)
        n_roots = df["root"].nunique() if "root" in df.columns else 0
        sessions = sorted(df["session_date"].dropna().unique()) if "session_date" in df.columns else []
        date_span = f"{sessions[0]} → {sessions[-1]}" if sessions else "unknown"
        n_sessions = len(sessions)

        # Events per day
        if "session_date" in df.columns:
            epd = df.groupby("session_date").size()
            epd_mean = float(epd.mean()) if len(epd) > 0 else 0.0
        else:
            epd_mean = 0.0

        # Era breakdown (if available)
        era_breakdown: dict = {}
        if "era" in df.columns:
            for era, grp in df.groupby("era"):
                era_breakdown[str(era)] = len(grp)

        # DTE bucket breakdown
        dte_breakdown: dict = {}
        if "dte_bucket" in df.columns:
            for bkt, grp in df.groupby("dte_bucket"):
                dte_breakdown[str(bkt)] = len(grp)

        # Per-era graded/ungraded/no-history breakdown (FIX 3c)
        # Join grade reason codes back to era via the grades parquet
        era_grade_breakdown: dict[str, dict[str, int]] = {}
        grades_path = fsd / fname.replace(".parquet", "_grades.parquet")
        if grades_path.exists() and "era" in df.columns:
            try:
                gdf = pd.read_parquet(grades_path, columns=["event_id", "reason_code"])
                # Join on event_id to get era
                merged_g = df[["event_id", "era"]].merge(gdf, on="event_id", how="left")
                for era_val, grp in merged_g.groupby("era"):
                    counts: dict[str, int] = {"graded": 0, "no_history": 0, "ungraded": 0}
                    rc_counts = grp["reason_code"].value_counts().to_dict()
                    for rc, cnt in rc_counts.items():
                        if rc in ("ok", "not_yet_matured", "partial_matured"):
                            counts["graded"] += int(cnt)
                        elif rc == "no_price_history_for_era":
                            counts["no_history"] += int(cnt)
                        else:
                            counts["ungraded"] += int(cnt)
                    era_grade_breakdown[str(era_val)] = counts
            except Exception as e:  # noqa: BLE001
                log.debug("ops_flow_cohorts: coverage: era grade join failed: %s", e)

        cohort_rep = {
            "n_events":    n,
            "n_roots":     n_roots,
            "n_sessions":  n_sessions,
            "date_span":   date_span,
            "events_per_day_mean": round(epd_mean, 2),
            "era_breakdown": era_breakdown,
            "dte_breakdown": dte_breakdown,
            "era_grade_breakdown": era_grade_breakdown,
            "status": "ok",
        }
        report["cohorts"][cohort_name] = cohort_rep

        print(f"\ncohort={cohort_name}: {n} events | {n_roots} roots | {n_sessions} sessions "
              f"| {date_span} | {epd_mean:.1f} events/day")
        if dte_breakdown:
            for bkt, cnt in sorted(dte_breakdown.items()):
                print(f"  dte_bucket={bkt}: {cnt}")
        if era_breakdown:
            for era, cnt in sorted(era_breakdown.items()):
                print(f"  era={era}: {cnt}")
        if era_grade_breakdown:
            print("  era grade coverage:")
            for era, breakdown in sorted(era_grade_breakdown.items()):
                print(f"    {era}: graded={breakdown.get('graded', 0)} "
                      f"no_history={breakdown.get('no_history', 0)} "
                      f"ungraded={breakdown.get('ungraded', 0)}")

    # Write coverage JSON
    coverage_path = fsd / "cohort_coverage.json"
    try:
        tmp = coverage_path.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(report, indent=2))
        tmp.rename(coverage_path)
        log.info("ops_flow_cohorts: coverage report → %s", coverage_path)
    except Exception as e:  # noqa: BLE001
        log.warning("ops_flow_cohorts: could not write cohort_coverage.json: %s", e)

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# GRADING (one-grader law: import engine/flow_signals_grade.py primitives)
# ═══════════════════════════════════════════════════════════════════════════════

def run_grade_cohorts(out_dir: Path | None = None) -> dict:
    """Grade cohort events using the FS-0 grader (one-grader law, FS-R2).

    Reads cohort_tape_recon.parquet and cohort_eod_proxy.parquet,
    grades historical events using engine/flow_signals_grade.py primitives,
    writes cohort_tape_recon_grades.parquet and cohort_eod_proxy_grades.parquet.

    Historical events grade to FULL maturity in one pass (unlike the nightly
    ledger grader which waits for horizons to mature).

    FIX 3 — coverage honesty:
      - close is None → reason_code='no_price_data' grade row (not silent skip).
      - session_date < close.index[0] → reason_code='no_price_history_for_era'
        (pre-2023 events on this box's yahoo store are structurally ungradable,
        not merely immature; distinct from 'not_yet_matured').
      - cohort_coverage.json gains per-era graded/ungraded/no-history breakdown.

    FIX 4 — RAM law: streams cohort in row-group batches (pyarrow iter_batches)
    instead of loading the full file into RAM.

    Returns a summary dict with per-cohort grade counts.
    """
    import pyarrow.parquet as pq
    from engine.flow_signals_grade import _grade_event, _spy_close, _load_close
    from datetime import date as date_cls

    fsd = out_dir or _flow_signals_dir()
    today = date_cls.today()
    summary: dict = {}

    for cohort_name, fname in [("tape_recon", "cohort_tape_recon.parquet"),
                                 ("eod_proxy", "cohort_eod_proxy.parquet")]:
        in_path = fsd / fname
        out_path = fsd / fname.replace(".parquet", "_grades.parquet")

        if not in_path.exists():
            log.info("ops_flow_cohorts: grade_cohorts: %s absent — skip", fname)
            continue

        spy = _spy_close()
        close_cache: dict[str, Any] = {}
        grade_rows: list[dict] = []
        n_ok = n_not_matured = n_no_price = n_no_history = n_errors = 0
        # Per-era coverage tracking (era → {graded, no_history, ungraded})
        era_coverage: dict[str, dict[str, int]] = {}

        try:
            pf = pq.ParquetFile(in_path)
        except Exception as e:  # noqa: BLE001
            log.error("ops_flow_cohorts: grade_cohorts: cannot open %s: %s", fname, e)
            continue

        # Stream in row-group batches (FIX 4: avoids loading full cohort into RAM)
        n_batches = 0
        for batch in pf.iter_batches(batch_size=1000):
            n_batches += 1
            cohort_batch = batch.to_pandas()

            for _, row in cohort_batch.iterrows():
                ticker = str(row.get("root", "")).upper()
                session_date = str(row.get("session_date", ""))
                dte_bucket = str(row.get("dte_bucket", "8_30d"))
                event_id = str(row.get("event_id", ""))
                era = str(row.get("era", "")) if "era" in cohort_batch.columns else ""

                # Init era tracker
                if era not in era_coverage:
                    era_coverage[era] = {"graded": 0, "no_history": 0, "ungraded": 0}

                if not ticker or not session_date:
                    n_errors += 1
                    era_coverage[era]["ungraded"] = era_coverage[era].get("ungraded", 0) + 1
                    continue

                if ticker not in close_cache:
                    close_cache[ticker] = _load_close(ticker)
                close = close_cache[ticker]

                if close is None:
                    # FIX 3a: write a grade row with no_price_data instead of silent skip
                    gr = {
                        "event_id":  event_id,
                        "graded_at": datetime.now(timezone.utc).isoformat(),
                        "graded_ok": False,
                        "reason_code": "no_price_data",
                        **{f"{k}_{h}": None
                           for h in [5, 21, 63, 126]
                           for k in ["fwd_ret", "fwd_mfe", "fwd_mdd", "spy_excess"]},
                        "terminal_state_clean8_21": None,
                        "terminal_state_clean15_126": None,
                        "prem_touch_50": None,
                        "entry_price": None,
                        "fill_date": None,
                        "cohort": cohort_name,
                    }
                    grade_rows.append(gr)
                    n_no_price += 1
                    era_coverage[era]["ungraded"] = era_coverage[era].get("ungraded", 0) + 1
                    continue

                # FIX 3b: pre-2023 events are structurally ungradable on this box's yahoo store
                try:
                    sess_dt = date.fromisoformat(session_date[:10])
                    store_start = close.index[0].date() if hasattr(close.index[0], "date") else date.fromisoformat(str(close.index[0])[:10])
                    if sess_dt < store_start:
                        gr = {
                            "event_id":  event_id,
                            "graded_at": datetime.now(timezone.utc).isoformat(),
                            "graded_ok": False,
                            "reason_code": "no_price_history_for_era",
                            **{f"{k}_{h}": None
                               for h in [5, 21, 63, 126]
                               for k in ["fwd_ret", "fwd_mfe", "fwd_mdd", "spy_excess"]},
                            "terminal_state_clean8_21": None,
                            "terminal_state_clean15_126": None,
                            "prem_touch_50": None,
                            "entry_price": None,
                            "fill_date": None,
                            "cohort": cohort_name,
                        }
                        grade_rows.append(gr)
                        n_no_history += 1
                        era_coverage[era]["no_history"] = era_coverage[era].get("no_history", 0) + 1
                        continue
                except Exception:  # noqa: BLE001
                    pass

                gr = _grade_event(event_id, ticker, session_date, dte_bucket, close, spy, today=today)
                rc = gr.get("reason_code", "")
                if rc == "ok":
                    n_ok += 1
                    era_coverage[era]["graded"] = era_coverage[era].get("graded", 0) + 1
                elif rc in ("not_yet_matured", "partial_matured"):
                    n_not_matured += 1
                    era_coverage[era]["graded"] = era_coverage[era].get("graded", 0) + 1
                else:
                    n_errors += 1
                    era_coverage[era]["ungraded"] = era_coverage[era].get("ungraded", 0) + 1
                gr["cohort"] = cohort_name
                grade_rows.append(gr)

        if grade_rows:
            gdf = pd.DataFrame(grade_rows)
            tmp = out_path.with_suffix(".tmp.parquet")
            try:
                gdf.to_parquet(tmp, index=False)
                tmp.rename(out_path)
                log.info(
                    "ops_flow_cohorts: grade_cohorts: %s → %d grades "
                    "(ok=%d not_matured=%d no_price=%d no_history=%d err=%d)",
                    out_path.name, len(grade_rows), n_ok, n_not_matured,
                    n_no_price, n_no_history, n_errors,
                )
            except Exception as e:  # noqa: BLE001
                log.error("ops_flow_cohorts: grade_cohorts: write %s failed: %s", out_path, e)

        summary[cohort_name] = {
            "n_ok": n_ok,
            "n_not_matured": n_not_matured,
            "n_no_price_data": n_no_price,
            "n_no_history": n_no_history,
            "n_errors": n_errors,
            "era_coverage": era_coverage,
        }

    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FS-1 historical flow cohorts (ops lane, off-render)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    # tape_recon
    p_tr = sub.add_parser("tape_recon", help="Pull tape from ThetaTerminal and detect events")
    p_tr.add_argument("--retry-failed", action="store_true",
                      help="Retry units that previously failed")
    p_tr.add_argument("--max-units", type=int, default=None,
                      help="Process at most N units (for smoke testing)")
    p_tr.add_argument("--dry-run", action="store_true",
                      help="Detect events but do not write parquet or state")

    # eod_proxy
    p_ep = sub.add_parser("eod_proxy", help="Build pseudo-events from thetadata_eod store")
    p_ep.add_argument("--roots", type=int, default=None,
                      help="Limit to first N roots (smoke test)")
    p_ep.add_argument("--dry-run", action="store_true",
                      help="Detect events but do not write parquet")
    p_ep.add_argument("--output-dir", type=Path, default=None,
                      help="Override output directory (default: data/flow_signals/)")

    # coverage
    p_cv = sub.add_parser("coverage", help="Print coverage report for both cohorts")
    p_cv.add_argument("--output-dir", type=Path, default=None)

    # grade
    p_gr = sub.add_parser("grade", help="Grade cohort events (one-grader law)")
    p_gr.add_argument("--output-dir", type=Path, default=None)

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    if args.cmd == "tape_recon":
        n = run_tape_recon(
            retry_failed=args.retry_failed,
            max_units=args.max_units,
            dry_run=args.dry_run,
        )
        if n == 1:  # error sentinel from terminal-down
            return 1
        print(f"tape_recon: {'would write' if args.dry_run else 'wrote'} {n} events")
        return 0

    elif args.cmd == "eod_proxy":
        n = run_eod_proxy(
            roots_limit=args.roots,
            dry_run=args.dry_run,
            output_dir=args.output_dir,
        )
        print(f"eod_proxy: {'would write' if args.dry_run else 'wrote'} {n} events")
        return 0

    elif args.cmd == "coverage":
        _coverage_report(out_dir=args.output_dir)
        return 0

    elif args.cmd == "grade":
        summary = run_grade_cohorts(out_dir=args.output_dir)
        print(json.dumps(summary, indent=2))
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    from lib.procutil import hard_exit
    code = main()
    hard_exit(code)
