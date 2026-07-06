"""scripts/build_options_flow_attention.py — W-D options_flow_attention reflex trigger.

Neural Web W-D (RO-8, OPTIONS_NW_ENTRY_INTELLIGENCE_MASTERPLAN §4).

WHAT THIS SCRIPT DOES
---------------------
Runs nightly (after the collect job).  For each name on the current US board/watch
lanes it evaluates two direction-free trigger conditions against EOD options data:

  (a) vol>OI magnitude burst:
      fresh_contracts > 0  AND  fresh_premium z-score >= 2.0 vs per-name rolling
      history.  Null-safe: fewer than MIN_HISTORY_ROWS (5) history rows → no fire.

  (b) wall/flip proximity:
      abs(dist_to_flip_pct) <= PROXIMITY_PCT_THRESHOLD (1.0 %)  OR
      min wall distance = min(abs(spot-magnet_up), abs(spot-magnet_down)) / spot
      * 100 <= PROXIMITY_PCT_THRESHOLD (1.0 %).

ALL firings carry direction=0 (direction-free per RO-8).

LIVE R2 FEED STUB
-----------------
The intraday live_flow/ R2 feed is UNDEPLOYED (feat/flow-desk branch).  A hard
stale-guard is implemented: if the feed metadata file (live_flow/meta.json) is
absent or its 'generated_at' timestamp is > LIVE_FEED_STALE_MINUTES (15) minutes
old, the live-feed reader returns an empty dict and logs the gap.  Live firings
are expected to be ZERO until feat/flow-desk deploys — that is honest and correct.

BOARD MEMBERSHIP (PIT SOURCE)
------------------------------
Board names come from two PIT artifacts (both committed to site/factordata/):
  - site/factordata/us_standouts.json  → buy + watch lanes
  - site/factordata/us_standouts_v2.json → entry_open + setting_up lanes
No intraday state is read.  The nightly EOD options summaries are the sole data
source.

SINGLE-WRITER LAW
-----------------
ONLY this script calls record_firing() for the options_flow_attention reflex.
No other writer may append to data/reflexes/options_flow_attention/firings.jsonl.

OUTPUT
------
Appends to data/reflexes/options_flow_attention/firings.jsonl.
Never raises: all errors are caught and logged.  Missing data → no fire.

NIGHTLY FOLD
------------
adapt_reflexes() in engine.neuralweb.query discovers and maps the firings.jsonl
to spine rows with ledger='reflexes', outcome_graded=False (ungraded-honest).
The staging gap is covered: daily.yml commit steps use 'git add data/' which
covers data/reflexes/options_flow_attention/.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Direction-free per RO-8 — every firing must carry direction=0.
DIRECTION_FREE: int = 0

# z-score threshold for vol>OI magnitude burst trigger (a).
PREMIUM_Z_THRESHOLD: float = 2.0

# Minimum rolling-history rows required to compute a z-score (null-safe floor).
MIN_HISTORY_ROWS: int = 5

# Proximity threshold for wall/flip trigger (b): 1 % of spot.
PROXIMITY_PCT_THRESHOLD: float = 1.0

# Live R2 feed stale-guard: >15 min → no-fire from live feed.
LIVE_FEED_STALE_MINUTES: int = 15

# Column names in options_flow summary parquets.
_COL_FRESH_CONTRACTS = "fresh_contracts"
_COL_PREMIUM_MN = "premium_mn"

# Column names in polygon_gex summary parquets.
_COL_DIST_TO_FLIP = "dist_to_flip_pct"
_COL_MAGNET_UP = "magnet_up"
_COL_MAGNET_DOWN = "magnet_down"
_COL_SPOT = "spot"


# ---------------------------------------------------------------------------
# Board membership helpers
# ---------------------------------------------------------------------------

def _load_board_names(site_root: Path) -> list[str]:
    """Return unique tickers from current US board/watch lanes.

    Reads two PIT artifacts from site/factordata/:
      - us_standouts.json  (buy + watch lanes)
      - us_standouts_v2.json (entry_open + setting_up lanes)

    Returns an empty list (no fire) if both are absent.  Missing keys are
    guarded safely (Jinja missing-key law: check existence before access).
    """
    tickers: set[str] = set()

    # us_standouts.json: buy + watch
    p1 = site_root / "factordata" / "us_standouts.json"
    if p1.exists():
        try:
            d = json.loads(p1.read_text(encoding="utf-8"))
            for lane_key in ("buy", "watch"):
                if lane_key in d and isinstance(d[lane_key], list):
                    for item in d[lane_key]:
                        if isinstance(item, dict) and item.get("ticker"):
                            tickers.add(str(item["ticker"]))
        except Exception as e:  # noqa: BLE001
            log.warning("options_flow_attention: failed to load us_standouts.json: %s", e)

    # us_standouts_v2.json: all lanes
    p2 = site_root / "factordata" / "us_standouts_v2.json"
    if p2.exists():
        try:
            d = json.loads(p2.read_text(encoding="utf-8"))
            if isinstance(d.get("lanes"), dict):
                for lane_rows in d["lanes"].values():
                    if isinstance(lane_rows, list):
                        for item in lane_rows:
                            if isinstance(item, dict) and item.get("ticker"):
                                tickers.add(str(item["ticker"]))
        except Exception as e:  # noqa: BLE001
            log.warning("options_flow_attention: failed to load us_standouts_v2.json: %s", e)

    return sorted(tickers)


# ---------------------------------------------------------------------------
# Options data readers
# ---------------------------------------------------------------------------

def _load_flow_summary(data_root: Path, ticker: str) -> pd.DataFrame | None:
    """Load data/options_flow/summary_<TICKER>.parquet.  Returns None on miss."""
    p = data_root / "options_flow" / f"summary_{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        # Defensive sort: PIT correctness must not depend on writer sort discipline.
        # lib/store.py:upsert() sorts before writing, but guard here so iloc[-1]
        # always picks the chronologically latest row even if a future writer appends
        # unsorted rows.
        df = df.sort_index()
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("options_flow_attention: flow summary load failed %s: %s", ticker, e)
        return None


def _load_gex_summary(data_root: Path, ticker: str) -> pd.DataFrame | None:
    """Load data/polygon_gex/summary_<TICKER>.parquet.  Returns None on miss."""
    p = data_root / "polygon_gex" / f"summary_{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        # Defensive sort: same PIT invariant as _load_flow_summary — see above.
        df = df.sort_index()
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("options_flow_attention: gex summary load failed %s: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# Live R2 feed stub — hard stale-guard
# ---------------------------------------------------------------------------

def _check_live_feed(data_root: Path) -> dict[str, Any]:
    """Hard stale-guard for the R2 live_flow feed.

    The feat/flow-desk branch is UNDEPLOYED.  This stub checks for a local
    live_flow/meta.json file (which the poller would write if running).  If
    absent or stale (generated_at > LIVE_FEED_STALE_MINUTES old), it returns
    an empty dict and logs a gap — no firings are generated from the live feed.

    Returns:
        dict with 'available': bool, 'reason': str, and optionally 'meta' dict.
    """
    meta_path = data_root / "live_flow" / "meta.json"
    if not meta_path.exists():
        log.debug(
            "options_flow_attention: live_flow/meta.json absent "
            "(feat/flow-desk UNDEPLOYED) — live feed NO-FIRE"
        )
        return {"available": False, "reason": "live_flow/meta.json absent (feed undeployed)"}

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("options_flow_attention: live_flow/meta.json parse error: %s — NO-FIRE", e)
        return {"available": False, "reason": f"meta parse error: {e}"}

    # Check staleness
    generated_at_str = meta.get("generated_at") or meta.get("ts") or meta.get("as_of")
    if not generated_at_str:
        log.warning(
            "options_flow_attention: live_flow/meta.json has no timestamp — NO-FIRE"
        )
        return {"available": False, "reason": "no timestamp in meta.json"}

    try:
        # Parse ISO-8601 UTC timestamp
        generated_at = pd.to_datetime(generated_at_str, utc=True)
        now_utc = datetime.now(timezone.utc)
        age_minutes = (now_utc - generated_at.to_pydatetime()).total_seconds() / 60.0
        if age_minutes > LIVE_FEED_STALE_MINUTES:
            log.info(
                "options_flow_attention: live feed stale (%.1f min > %d min threshold) — NO-FIRE",
                age_minutes, LIVE_FEED_STALE_MINUTES,
            )
            return {
                "available": False,
                "reason": f"stale: {age_minutes:.1f}m > {LIVE_FEED_STALE_MINUTES}m",
                "age_minutes": age_minutes,
            }
        log.debug("options_flow_attention: live feed fresh (%.1f min old)", age_minutes)
        return {"available": True, "meta": meta, "age_minutes": age_minutes}
    except Exception as e:  # noqa: BLE001
        log.warning("options_flow_attention: live feed age check failed: %s — NO-FIRE", e)
        return {"available": False, "reason": f"age check failed: {e}"}


# ---------------------------------------------------------------------------
# Trigger (a): vol>OI magnitude burst
# ---------------------------------------------------------------------------

def _compute_premium_z(flow_df: pd.DataFrame) -> float | None:
    """Compute z-score of the latest premium_mn vs per-name history.

    Returns None if:
      - _COL_PREMIUM_MN column absent
      - fewer than MIN_HISTORY_ROWS rows in history
      - std is zero (degenerate history)
    """
    if _COL_PREMIUM_MN not in flow_df.columns:
        return None
    series = flow_df[_COL_PREMIUM_MN].dropna()
    if len(series) < MIN_HISTORY_ROWS:
        return None
    history = series.iloc[:-1]  # exclude latest row for z-score baseline
    if len(history) < MIN_HISTORY_ROWS - 1:
        return None
    mean = float(history.mean())
    std = float(history.std(ddof=1))
    if std == 0 or pd.isna(std):
        return None
    latest = float(series.iloc[-1])
    return (latest - mean) / std


def _trigger_vol_oi_burst(
    ticker: str,
    flow_df: pd.DataFrame | None,
    asof: str,
) -> dict[str, Any] | None:
    """Return a firing dict if trigger (a) fires, else None.

    Null-safe: returns None when flow data is absent or history insufficient.
    Never raises.
    """
    if flow_df is None or flow_df.empty:
        return None

    try:
        latest = flow_df.iloc[-1]

        # Check fresh_contracts > 0
        if _COL_FRESH_CONTRACTS not in flow_df.columns:
            return None
        fresh = latest.get(_COL_FRESH_CONTRACTS)
        if fresh is None or pd.isna(fresh) or float(fresh) <= 0:
            return None

        # Check premium z-score >= threshold
        premium_z = _compute_premium_z(flow_df)
        if premium_z is None:
            log.debug(
                "options_flow_attention: %s vol>OI z-score null (history insufficient — n=%d)",
                ticker, len(flow_df),
            )
            return None
        if premium_z < PREMIUM_Z_THRESHOLD:
            return None

        log.info(
            "options_flow_attention: %s vol>OI burst: fresh_contracts=%s premium_z=%.2f",
            ticker, fresh, premium_z,
        )
        return {
            "trigger_type": "vol_oi_burst",
            "trigger_key": f"vol_oi_burst:{ticker}:{asof}",
            "action_taken": "attention_flag",
            "scope_type": "entity",
            "scope_key": ticker,
            "direction": DIRECTION_FREE,
            "horizon_d": None,
            "asof": asof,
            "extra": {
                "trigger_label": "vol>OI magnitude burst",
                "fresh_contracts": float(fresh),
                "premium_z": round(premium_z, 3),
                "premium_z_threshold": PREMIUM_Z_THRESHOLD,
                "history_n": len(flow_df),
            },
        }
    except Exception as e:  # noqa: BLE001
        log.debug("options_flow_attention: vol>OI burst eval failed %s: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# Trigger (b): wall/flip proximity
# ---------------------------------------------------------------------------

def _trigger_wall_flip_proximity(
    ticker: str,
    gex_df: pd.DataFrame | None,
    asof: str,
) -> dict[str, Any] | None:
    """Return a firing dict if trigger (b) fires, else None.

    Null-safe: returns None when gex data is absent.
    Never raises.
    """
    if gex_df is None or gex_df.empty:
        return None

    try:
        latest = gex_df.iloc[-1]

        flip_proximity = None
        wall_proximity = None
        near_flip = False
        near_wall = False

        # (b1) flip proximity: abs(dist_to_flip_pct) <= threshold
        if _COL_DIST_TO_FLIP in gex_df.columns:
            dist = latest.get(_COL_DIST_TO_FLIP)
            if dist is not None and not pd.isna(dist):
                flip_proximity = abs(float(dist))
                near_flip = flip_proximity <= PROXIMITY_PCT_THRESHOLD

        # (b2) wall proximity: min distance to magnets / spot * 100
        if (
            _COL_SPOT in gex_df.columns
            and _COL_MAGNET_UP in gex_df.columns
            and _COL_MAGNET_DOWN in gex_df.columns
        ):
            spot_val = latest.get(_COL_SPOT)
            magnet_up_val = latest.get(_COL_MAGNET_UP)
            magnet_down_val = latest.get(_COL_MAGNET_DOWN)

            if (
                spot_val is not None and not pd.isna(spot_val)
                and float(spot_val) > 0
            ):
                spot = float(spot_val)
                dist_up = None
                dist_down = None

                if magnet_up_val is not None and not pd.isna(magnet_up_val):
                    dist_up = abs(spot - float(magnet_up_val)) / spot * 100.0
                if magnet_down_val is not None and not pd.isna(magnet_down_val):
                    dist_down = abs(spot - float(magnet_down_val)) / spot * 100.0

                if dist_up is not None or dist_down is not None:
                    wall_proximity = min(
                        d for d in [dist_up, dist_down] if d is not None
                    )
                    near_wall = wall_proximity <= PROXIMITY_PCT_THRESHOLD

        if not (near_flip or near_wall):
            return None

        reason_parts: list[str] = []
        if near_flip and flip_proximity is not None:
            reason_parts.append(f"dist_to_flip={flip_proximity:.2f}%")
        if near_wall and wall_proximity is not None:
            reason_parts.append(f"min_wall_dist={wall_proximity:.2f}%")
        reason = " AND ".join(reason_parts)

        log.info(
            "options_flow_attention: %s wall/flip proximity: %s",
            ticker, reason,
        )
        return {
            "trigger_type": "wall_flip_proximity",
            "trigger_key": f"wall_flip_proximity:{ticker}:{asof}",
            "action_taken": "attention_flag",
            "scope_type": "entity",
            "scope_key": ticker,
            "direction": DIRECTION_FREE,
            "horizon_d": None,
            "asof": asof,
            "extra": {
                "trigger_label": "wall/flip proximity",
                "near_flip": near_flip,
                "near_wall": near_wall,
                "dist_to_flip_pct": flip_proximity,
                "min_wall_dist_pct": wall_proximity,
                "proximity_threshold_pct": PROXIMITY_PCT_THRESHOLD,
            },
        }
    except Exception as e:  # noqa: BLE001
        log.debug("options_flow_attention: wall/flip proximity eval failed %s: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    root: Path | str | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the options_flow_attention nightly trigger.

    Args:
        root: repo root (default: inferred from lib.config).
        dry_run: if True, evaluate triggers but do not call record_firing.

    Returns:
        Summary dict: {
            'board_names': [...],
            'fires': [...],       # list of firing records
            'gaps': [...],        # log of skips/missing-data notes
            'live_feed': {...},   # live feed stale-guard result
        }
    """
    # Resolve root paths
    if root is not None:
        root_p = Path(root)
    else:
        try:
            from lib import config as _cfg  # noqa: PLC0415
            root_p = _cfg.ROOT
        except Exception:  # noqa: BLE001
            root_p = Path(__file__).resolve().parent.parent

    data_root = root_p / "data"
    site_root = root_p / "site"

    gaps: list[str] = []
    fires: list[dict] = []

    # Live feed stale-guard (PLACEHOLDER — feat/flow-desk UNDEPLOYED).
    # All EOD firings come from parquet paths below regardless of live_status.
    # The stale-guard gates a FUTURE intraday live-fire path that does not exist
    # yet; when feat/flow-desk deploys, the live leg must be wired here.
    # Until then live_status is always available=False and the guard is a no-op.
    live_status = _check_live_feed(data_root)
    if not live_status.get("available"):
        gaps.append(
            f"options_flow_attention: live feed unavailable "
            f"({live_status.get('reason', 'unknown')}) — live leg NO-FIRE"
        )

    # Determine asof from today's date
    asof_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Load board membership
    board_names = _load_board_names(site_root)
    if not board_names:
        gaps.append(
            "options_flow_attention: no board names found "
            "(us_standouts.json + us_standouts_v2.json absent or empty) — no fires"
        )
        log.info("options_flow_attention: no board names — exiting")
        return {"board_names": [], "fires": [], "gaps": gaps, "live_feed": live_status}

    log.info("options_flow_attention: evaluating %d board names", len(board_names))

    from engine.neuralweb.reflexes import record_firing  # noqa: PLC0415

    fired_tickers: set[str] = set()

    for ticker in board_names:
        flow_df = _load_flow_summary(data_root, ticker)
        gex_df = _load_gex_summary(data_root, ticker)

        if flow_df is None and gex_df is None:
            log.debug("options_flow_attention: %s no EOD data — skip", ticker)
            gaps.append(f"options_flow_attention: {ticker}: no flow or gex summary — skip")
            continue

        # Determine asof from latest available data row
        asof = asof_today
        if flow_df is not None and not flow_df.empty:
            try:
                asof = str(flow_df.index[-1])[:10]
            except Exception:  # noqa: BLE001
                pass
        elif gex_df is not None and not gex_df.empty:
            try:
                asof = str(gex_df.index[-1])[:10]
            except Exception:  # noqa: BLE001
                pass

        # Evaluate trigger (a): vol>OI magnitude burst
        fire_a = _trigger_vol_oi_burst(ticker, flow_df, asof)
        if fire_a is not None:
            fire_a["ts"] = now_iso
            if not dry_run:
                try:
                    rec = record_firing("options_flow_attention", fire_a, root=root_p)
                    fires.append(rec)
                    fired_tickers.add(ticker)
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "options_flow_attention: record_firing failed %s trigger_a: %s",
                        ticker, e,
                    )
            else:
                fires.append({"dry_run": True, **fire_a})
                fired_tickers.add(ticker)

        # Evaluate trigger (b): wall/flip proximity
        fire_b = _trigger_wall_flip_proximity(ticker, gex_df, asof)
        if fire_b is not None:
            fire_b["ts"] = now_iso
            if not dry_run:
                try:
                    rec = record_firing("options_flow_attention", fire_b, root=root_p)
                    fires.append(rec)
                    fired_tickers.add(ticker)
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "options_flow_attention: record_firing failed %s trigger_b: %s",
                        ticker, e,
                    )
            else:
                fires.append({"dry_run": True, **fire_b})
                fired_tickers.add(ticker)

    log.info(
        "options_flow_attention: %d fires on %d unique tickers (board=%d, %s)",
        len(fires), len(fired_tickers), len(board_names),
        "dry_run" if dry_run else "live",
    )
    return {
        "board_names": board_names,
        "fires": fires,
        "gaps": gaps,
        "live_feed": live_status,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [options_flow_attention] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="W-D options_flow_attention reflex trigger (nightly)."
    )
    parser.add_argument("--root", default=None, help="Repo root (default: auto)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Evaluate triggers without writing firings.jsonl")
    args = parser.parse_args()

    result = run(root=args.root, dry_run=args.dry_run)
    print(json.dumps({
        "board_n": len(result["board_names"]),
        "fires_n": len(result["fires"]),
        "gaps_n": len(result["gaps"]),
        "live_feed_available": result["live_feed"].get("available", False),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
