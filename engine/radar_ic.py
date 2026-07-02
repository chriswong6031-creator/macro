"""Radar IC (Information Coefficient) validation harness — Phase 0 accountability.

Proves (or disproves) whether the Divergence Radar's `edge_score` (0-100) has
predictive power over a forward horizon. Mirrors the falsifiable-ledger pattern
of engine/demand_ledger.py + engine/ai_desk_scorer.py, but instead of grading
binary hit/miss theses it computes continuous Spearman rank IC + hit-rate by
edge bucket across all matured snapshots.

How it works
------------
1. snapshot(today) — append TODAY's edge readings to
   data/radar/edge_snapshots.jsonl, one row per basket flag or ticker divergence.
   Idempotent by (date, subject) — never double-appends.

2. compute_ic(today, horizon_d=21) — once a snapshot is ≥ horizon_d old AND price
   data covers [date, date+horizon], it "matures". Compute:
     * Spearman rank IC(edge_score, fwd_rel_return) over ALL matured obs.
     * Rolling IC over the most recent ~90 matured obs.
     * Hit-rate by edge bucket (0-40 / 40-70 / 70-100).
     * Directional accuracy by state.
   Returns a dict with schema "radar_ic.v1". Degrade-safe — if no matured
   snapshots, emits a valid JSON with n_matured:0 and the "accruing" note.

Price helper
------------
Reuses engine.ai_desk._close_series (data/yahoo/<T>.parquet → breadth cache) and
engine.ai_desk_scorer._close_at to compute total returns. SPY = benchmark.

All public functions: Never raise. Return plain data or None on error.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine.ai_desk import _close_series, _level_asof  # price helpers — do NOT reinvent
from engine.ai_desk_scorer import _close_at, _covers   # also reuse; same parquet layer
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "radar_ic.v1"
_SNAPSHOTS_FILE = ("data", "radar", "edge_snapshots.jsonl")
# Default IC grading horizon.  Brief §9: grader now supports multiple horizons;
# the 21d horizon remains the legacy default so that existing consumers of
# radar_ic.json top-level fields (ic_all, n_matured, etc.) are unaffected.
_HORIZON_D = 21        # default ~1 trading month (kept as legacy default)
_ROLLING_N = 90        # rolling window (obs count, not calendar days)
_BENCH = "SPY"

# Edge-score buckets: (label, lo_inclusive, hi_exclusive)
_BUCKETS = [("0-40", 0, 40), ("40-70", 40, 70), ("70-100", 70, 101)]

# States whose implied direction is POSITIVE (we expect positive fwd rel-return)
_BULLISH_STATES = {"POSITIVE_DIVERGENCE", "CONFIRMED_UP"}
# States whose implied direction is NEGATIVE
_BEARISH_STATES = {"NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fwd_rel_return(ticker: str, root: Path, start_date: str, horizon_d: int
                    ) -> float | None:
    """Total return of `ticker` minus SPY over `horizon_d` calendar days from
    `start_date`. Uses close ON or BEFORE start_date as entry, and close ON or
    BEFORE (start_date + horizon_d) as exit. Returns None if price unavailable."""
    try:
        end_ts = (pd.Timestamp(start_date) + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        e0 = _level_asof(ticker, root, start_date)
        e1 = _close_at(ticker, root, end_ts)
        b0 = _level_asof(_BENCH, root, start_date)
        b1 = _close_at(_BENCH, root, end_ts)
        if None in (e0, e1, b0, b1) or e0 == 0 or b0 == 0:
            return None
        return round((e1 / e0 - 1.0) - (b1 / b0 - 1.0), 6)
    except Exception as e:  # noqa: BLE001
        log.debug("_fwd_rel_return(%s, %s): %s", ticker, start_date, e)
        return None


def _is_matured(row: dict, root: Path, horizon_d: int, today: date) -> bool:
    """True when the snapshot is old enough AND price data covers the horizon."""
    try:
        snap_date = pd.Timestamp(row["date"])
        # must be at least horizon_d calendar days old
        if (pd.Timestamp(today) - snap_date).days < horizon_d:
            return False
        end_ts = (snap_date + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        ticker = row["ticker"]
        return bool(
            _covers(ticker, root, end_ts)
            and _covers(_BENCH, root, end_ts)
        )
    except Exception:  # noqa: BLE001
        return False


def _spearman_ic(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation between xs and ys. Returns None if n < 3."""
    n = len(xs)
    if n < 3:
        return None
    try:
        # rank ties broken by average (standard Spearman)
        def ranks(v: list[float]) -> list[float]:
            indexed = sorted(enumerate(v), key=lambda t: t[1])
            r: list[float] = [0.0] * len(v)
            i = 0
            while i < len(indexed):
                j = i
                while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[j][1]:
                    j += 1
                avg_rank = (i + j) / 2 + 1  # 1-based
                for k in range(i, j + 1):
                    r[indexed[k][0]] = avg_rank
                i = j + 1
            return r

        rx, ry = ranks(xs), ranks(ys)
        mx = sum(rx) / n
        my = sum(ry) / n
        num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
        den = math.sqrt(
            sum((rx[i] - mx) ** 2 for i in range(n))
            * sum((ry[i] - my) ** 2 for i in range(n))
        )
        return round(num / den, 4) if den > 0 else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# snapshot accrual
# ---------------------------------------------------------------------------

def _load_snapshots(root: Path) -> list[dict]:
    p = root.joinpath(*_SNAPSHOTS_FILE)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _snapshot_key(row: dict) -> str:
    return f"{row['date']}|{row['subject']}"


def snapshot(today: date | str | None = None, root: Path | None = None) -> int:
    """Append today's edge readings to data/radar/edge_snapshots.jsonl.
    Idempotent by (date, subject). Returns count of newly-appended rows."""
    try:
        root = Path(root) if root else config.ROOT
        today_str = (today.isoformat() if hasattr(today, "isoformat") else str(today or date.today()))

        # Load current snapshots to find existing keys
        existing = {_snapshot_key(r) for r in _load_snapshots(root)}

        new_rows: list[dict] = []

        # -- per-basket from radar.json --
        radar_p = root / "site" / "basketdata" / "radar.json"
        if radar_p.exists():
            try:
                rd = json.loads(radar_p.read_text())
                mem = _load_membership(root)
                # Build basket→horizon_d map from hypotheses (stamped by radar.py at seed time).
                # Allows compute_ic to grade each snapshot at the correct horizon.
                hyp_horizon: dict[str, int] = {
                    h["subject"]: int(h["horizon_d"])
                    for h in rd.get("hypotheses", [])
                    if h.get("horizon_d") and h.get("subject")
                }
                for flag in rd.get("flags", []):
                    state = flag.get("state", "")
                    if state == "QUIET":
                        continue
                    es = flag.get("edge_score")
                    if es is None:
                        continue
                    basket_id = flag.get("basket", "")
                    proxy = _proxy_for(basket_id, mem)
                    if not proxy:
                        continue
                    row: dict[str, Any] = {
                        "date": today_str,
                        "kind": "basket",
                        "subject": basket_id,
                        "ticker": proxy,
                        "edge_score": int(es),
                        "state": state,
                    }
                    # Stamp horizon_d when available so grader can match the seeded clock.
                    # Legacy snapshots lacking this field are treated as gradeable at all horizons.
                    if basket_id in hyp_horizon:
                        row["horizon_d"] = hyp_horizon[basket_id]
                    key = _snapshot_key(row)
                    if key not in existing:
                        new_rows.append(row)
                        existing.add(key)
            except Exception as e:  # noqa: BLE001
                log.warning("snapshot: radar.json parse error: %s", e)

        # -- per-ticker from radar_ticker.json --
        ticker_p = root / "site" / "basketdata" / "radar_ticker.json"
        if ticker_p.exists():
            try:
                td = json.loads(ticker_p.read_text())
                for t in td.get("tickers", []):
                    state = t.get("state", "")
                    if state == "QUIET":
                        continue
                    es = t.get("edge_score")
                    ticker = t.get("ticker", "")
                    if es is None or not ticker:
                        continue
                    row = {
                        "date": today_str,
                        "kind": "ticker",
                        "subject": ticker,
                        "ticker": ticker,
                        "edge_score": int(es),
                        "state": state,
                    }
                    key = _snapshot_key(row)
                    if key not in existing:
                        new_rows.append(row)
                        existing.add(key)
            except Exception as e:  # noqa: BLE001
                log.warning("snapshot: radar_ticker.json parse error: %s", e)

        if not new_rows:
            log.info("snapshot: nothing new to append (already snapshotted or no data)")
            return 0

        p = root.joinpath(*_SNAPSHOTS_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for r in new_rows:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")

        log.info("snapshot: appended %d rows for %s", len(new_rows), today_str)
        return len(new_rows)

    except Exception as e:  # noqa: BLE001
        log.warning("snapshot failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# membership / proxy helpers (mirrors radar.py, self-contained here)
# ---------------------------------------------------------------------------

def _load_membership(root: Path) -> dict:
    try:
        p = root / "data" / "baskets" / "membership.json"
        return json.loads(p.read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _proxy_for(basket_id: str, mem: dict) -> str | None:
    b = mem.get(basket_id) or {}
    px = b.get("etf_proxy")
    if isinstance(px, list):
        px = px[0] if px else None
    if isinstance(px, str) and px.strip():
        return px.strip().split()[0]
    return None


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------

def _compute_ic_for_horizon(
    rows: list[dict], root: Path, horizon_d: int, today_dt: date,
) -> dict:
    """Inner helper: compute IC stats for a single horizon.

    Snapshots with an explicit `horizon_d` field are only considered for the
    matching horizon.  Legacy snapshots lacking `horizon_d` are eligible at
    every horizon (backward-compatible behaviour — treat as gradeable at all).

    Returns a dict with keys: n_matured, ic_all, ic_rolling, by_bucket, by_state, note.
    Never raises.
    """
    # Filter to rows eligible for this horizon (legacy rows have no horizon_d)
    eligible = [
        r for r in rows
        if r.get("horizon_d") is None or r.get("horizon_d") == horizon_d
    ]
    matured = [r for r in eligible if _is_matured(r, root, horizon_d, today_dt)]

    enriched: list[dict] = []
    for r in matured:
        fwd = _fwd_rel_return(r["ticker"], root, r["date"], horizon_d)
        if fwd is None:
            continue
        enriched.append({**r, "fwd_rel_return": fwd})

    n_matured = len(enriched)

    if n_matured < 3:
        accruing_note = (
            f"Accruing — {n_matured} matured observations so far "
            f"(need ≥3 for IC; grows as the {horizon_d}d horizon elapses)."
        )
        return {
            "n_matured": n_matured,
            "ic_all": None,
            f"ic_rolling_{_ROLLING_N}": None,
            "by_bucket": {label: {"n": 0, "hit_rate": None, "mean_fwd_ret": None}
                          for label, *_ in _BUCKETS},
            "by_state": {},
            "note": accruing_note,
        }

    scores = [r["edge_score"] for r in enriched]
    returns = [r["fwd_rel_return"] for r in enriched]
    ic_all = _spearman_ic(scores, returns)

    # Rolling IC over last _ROLLING_N obs (by append order)
    if n_matured >= _ROLLING_N:
        recent = enriched[-_ROLLING_N:]
        ic_rolling = _spearman_ic(
            [r["edge_score"] for r in recent],
            [r["fwd_rel_return"] for r in recent],
        )
    else:
        ic_rolling = ic_all  # use all when fewer than the window

    # Hit-rate by edge bucket
    by_bucket: dict[str, dict] = {}
    for label, lo, hi in _BUCKETS:
        bucket_rows = [r for r in enriched if lo <= r["edge_score"] < hi]
        n_b = len(bucket_rows)
        if n_b == 0:
            by_bucket[label] = {"n": 0, "hit_rate": None, "mean_fwd_ret": None}
            continue
        hits = 0
        for r in bucket_rows:
            state = r.get("state", "")
            fwd = r["fwd_rel_return"]
            if state in _BULLISH_STATES and fwd > 0:
                hits += 1
            elif state in _BEARISH_STATES and fwd < 0:
                hits += 1
            # CONFIRMED/neutral states — skip from directional hit count
        mean_ret = sum(r["fwd_rel_return"] for r in bucket_rows) / n_b
        by_bucket[label] = {
            "n": n_b,
            "hit_rate": round(hits / n_b, 3),
            "mean_fwd_ret": round(mean_ret, 4),
        }

    # Directional accuracy by state
    by_state: dict[str, dict] = {}
    for state in (*_BULLISH_STATES, *_BEARISH_STATES):
        state_rows = [r for r in enriched if r.get("state") == state]
        n_s = len(state_rows)
        if n_s == 0:
            continue
        if state in _BULLISH_STATES:
            correct = sum(1 for r in state_rows if r["fwd_rel_return"] > 0)
        else:
            correct = sum(1 for r in state_rows if r["fwd_rel_return"] < 0)
        by_state[state] = {
            "n": n_s,
            "dir_accuracy": round(correct / n_s, 3),
            "mean_fwd_ret": round(sum(r["fwd_rel_return"] for r in state_rows) / n_s, 4),
        }

    note = (
        f"{n_matured} matured observations (horizon={horizon_d}d). "
        f"IC_all={ic_all}, IC_rolling_{_ROLLING_N}={ic_rolling}. "
        "CONTEXT-ONLY — never fed into a score/size/allocation."
    ) if n_matured >= 10 else (
        f"ACCRUING — only {n_matured} matured obs (need ~30+ for reliable IC). "
        "Treat these early numbers as provisional. "
        "Context-only, never a trade signal."
    )

    return {
        "n_matured": n_matured,
        "ic_all": ic_all,
        f"ic_rolling_{_ROLLING_N}": ic_rolling,
        "by_bucket": by_bucket,
        "by_state": by_state,
        "note": note,
    }


def compute_ic(today: date | str | None = None, horizon_d: int = _HORIZON_D,
               horizons: list[int] | None = None,
               root: Path | None = None) -> dict:
    """Compute Spearman IC + hit-rate across all matured snapshots.

    Now horizon-parametric: pass `horizons=[21, 63]` (default) to get per-horizon
    blocks under `by_horizon`.  The legacy top-level fields (n_matured, ic_all,
    ic_rolling_90, by_bucket, by_state, note) always reflect the 21d horizon so
    existing consumers of radar_ic.json are unaffected.

    `horizon_d` (single int, legacy) is still accepted; when passed alone it sets
    the primary horizon only — `horizons` takes precedence when given.

    Degrades safely: if no snapshots or none matured yet, returns a valid dict
    with n_matured:0 and an "accruing" note. Never raises.
    """
    if horizons is None:
        horizons = [21, 63]  # default multi-horizon (21d legacy + 63d SEED_HORIZON_D)
    # Ensure the legacy primary horizon is always computed (backward compat)
    if horizon_d not in horizons:
        horizons = [horizon_d] + list(horizons)

    try:
        root = Path(root) if root else config.ROOT
        today_dt = (pd.Timestamp(today).date() if today else date.today())
        today_str = today_dt.isoformat()

        rows = _load_snapshots(root)
        n_total = len(rows)

        # Compute per-horizon blocks
        by_horizon: dict[str, dict] = {}
        for h in horizons:
            by_horizon[str(h)] = _compute_ic_for_horizon(rows, root, h, today_dt)

        # Legacy primary horizon block (horizon_d, default 21d)
        primary = by_horizon[str(horizon_d)]
        n_matured = primary["n_matured"]
        ic_all = primary["ic_all"]
        ic_rolling = primary[f"ic_rolling_{_ROLLING_N}"]

        return {
            "schema": SCHEMA,
            "as_of": today_str,
            "generated_at": _now_iso(),
            "horizon_d": horizon_d,            # legacy primary horizon
            "horizons": horizons,              # all computed horizons
            "n_snapshots": n_total,
            # Legacy top-level fields = primary (21d) horizon — consumers unaffected
            "n_matured": n_matured,
            "ic_all": ic_all,
            f"ic_rolling_{_ROLLING_N}": ic_rolling,
            "by_bucket": primary["by_bucket"],
            "by_state": primary["by_state"],
            "note": primary["note"],
            # Per-horizon detail blocks (W1 scoreboard reads from here)
            "by_horizon": by_horizon,
        }

    except Exception as e:  # noqa: BLE001
        log.warning("compute_ic failed: %s", e)
        as_of_str = (today.isoformat() if hasattr(today, "isoformat")
                     else str(today or date.today()))
        return _empty_result(
            as_of_str, 0, 0, horizon_d,
            f"compute_ic error: {e} — accruing, degrade-safe.",
        )


def _empty_horizon_block(horizon_d: int, note: str) -> dict:
    return {
        "n_matured": 0,
        "ic_all": None,
        f"ic_rolling_{_ROLLING_N}": None,
        "by_bucket": {label: {"n": 0, "hit_rate": None, "mean_fwd_ret": None}
                      for label, *_ in _BUCKETS},
        "by_state": {},
        "note": note,
    }


def _empty_result(as_of: str, n_snapshots: int, n_matured: int,
                  horizon_d: int, note: str) -> dict:
    horizons = [21, 63]
    if horizon_d not in horizons:
        horizons = [horizon_d] + horizons
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "generated_at": _now_iso(),
        "horizon_d": horizon_d,
        "horizons": horizons,
        "n_snapshots": n_snapshots,
        "n_matured": n_matured,
        "ic_all": None,
        f"ic_rolling_{_ROLLING_N}": None,
        "by_bucket": {label: {"n": 0, "hit_rate": None, "mean_fwd_ret": None}
                      for label, *_ in _BUCKETS},
        "by_state": {},
        "note": note,
        "by_horizon": {str(h): _empty_horizon_block(h, note) for h in horizons},
    }
