#!/usr/bin/env python3
"""scripts/build_levels_track_record.py — the levels Track Record driver.

Voltick Gamma-Levels program, WP-C1. Reconstructs historical named-level boards from the
deep ThetaData greeks store (2017→) and grades each one against the NEXT session's realized
OHLC, producing a display-tier Track Record: how often the Keystone drew price, the walls
contained the close, sticky levels held / slippery levels broke, and the expected-move band
held — every rate with N, its misses, and a Wilson CI, split by sticky/slippery.

WHY RECONSTRUCTION: forward-published boards only started accruing recently, so a real record
would take months to build. We own greeks back to 2017, so we reconstruct the board for any
past date and grade it — a deep, honest record from day one. Reconstruction uses ONLY data
known at that session's open (greeks + t-1 OI, per the OI timing law), so it is point-in-time.

DISPLAY-TIER: statistics about the map, never a win rate / strategy / buy-sell ranking; misses
shown; dealer-sign assumed not measured.

Usage:
    python -m scripts.build_levels_track_record --roots AAPL,MSFT,NVDA --start 2024-06-01 --end 2024-06-30
    python -m scripts.build_levels_track_record --universe stocks --start 2019-01-01 --publish   # operator backfill
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date as _date, timedelta
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.config import data_dir  # noqa: E402
from engine.thetadata_store import (  # noqa: E402
    _load_parquets, _normalise_date, resolve_thetadata_store, clear_parquet_cache,
)
from engine.options_hub import compute_gex  # noqa: E402
from engine.levels_engine import compute_levels  # noqa: E402
from engine.levels_grade import (  # noqa: E402
    grade_board, aggregate_track_record, board_id, learn_band_mult, TR_SCHEMA,
)

try:
    from engine.grading_stats import wilson_ci as _wilson_ci  # noqa: E402
except Exception:  # noqa: BLE001
    _wilson_ci = None  # aggregation degrades to rates without CIs

log = logging.getLogger("build_levels_track_record")

_LEVELS_DIR = Path(data_dir()) / "levels"
_STOCKS_DIR = Path(data_dir()) / "stocks"
_GRADES_PARQUET = _LEVELS_DIR / "grades.parquet"
_TR_JSON = _LEVELS_DIR / "track_record.json"
R2_TR_KEY = "levels_track_record.json"


# ── price bars (data/stocks — the only US store with high/low) ────────────────────

def _load_stock_bars(root: str) -> pd.DataFrame | None:
    p = _STOCKS_DIR / f"{root}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("bad stock parquet for %s — %s", root, e)
        return None
    df = df.sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def _next_bar(bars: pd.DataFrame, session_date: str) -> dict | None:
    """First bar STRICTLY after session_date. {date, open, high, low, close} or None."""
    d = pd.Timestamp(session_date)
    after = bars[bars.index > d]
    if after.empty:
        return None
    row = after.iloc[0]
    return {
        "date": after.index[0].strftime("%Y-%m-%d"),
        "open": row.get("open"), "high": row.get("high"),
        "low": row.get("low"), "close": row.get("close"),
    }


def _prior_close(bars: pd.DataFrame, session_date: str) -> float | None:
    """Close on/at-or-before session_date (the board session's close — approach side)."""
    d = pd.Timestamp(session_date)
    upto = bars[bars.index <= d]
    if upto.empty:
        return None
    try:
        return float(upto.iloc[-1]["close"])
    except (TypeError, ValueError, KeyError):
        return None


# ── reconstruction ────────────────────────────────────────────────────────────────

def _reconstruct(root: str, session_date: str, store: Path):
    """(levels_payload, median_iv) for a past date, or (None, reason)."""
    yr = int(session_date[:4])
    greeks = _load_parquets("greeks", root, [yr], store)
    if greeks is None or greeks.empty:
        return None, "no_greeks"
    greeks = _normalise_date(greeks)
    g = greeks[greeks["date"] == session_date].copy()
    if g.empty:
        return None, "no_greeks_date"
    oi = _load_parquets("oi", root, [yr], store)
    if oi is None or oi.empty:
        return None, "no_oi"
    oi = _normalise_date(oi)
    oi_prev = oi[oi["date"] == session_date][["expiration", "strike", "right", "open_interest"]].copy()
    if oi_prev.empty:
        return None, "no_oi_date"
    try:
        gex = compute_gex(g, oi_prev, session_date, root)
    except Exception as e:  # noqa: BLE001
        return None, f"gex_error:{type(e).__name__}"
    if not gex or not gex.get("by_strike"):
        return None, "reconstruct_empty"
    levels = compute_levels(gex, spot=gex.get("spot_ref"))
    median_iv = None
    try:
        median_iv = float(g["implied_vol"].median())
    except Exception:  # noqa: BLE001
        median_iv = None
    return {"levels": levels, "median_iv": median_iv, "gex": gex}, "ok"


def _greeks_dates(root: str, years: list[int], store: Path, start: str, end: str) -> list[str]:
    frames = []
    for yr in years:
        gf = _load_parquets("greeks", root, [yr], store)
        if gf is not None and not gf.empty:
            frames.append(_normalise_date(gf)[["date"]])
    if not frames:
        return []
    alld = pd.concat(frames, ignore_index=True)["date"].dropna().unique().tolist()
    return sorted(d for d in alld if start <= d <= end)


# ── grades ledger (single-writer, upsert by board_id) ─────────────────────────────

def _grade_rows_from(g: dict) -> list[dict]:
    """Flatten one graded board into per-node parquet rows (+ a board summary row)."""
    rows = []
    b = g.get("board", {})
    base = {"board_id": board_id(g.get("root") or "", g.get("session_date") or ""),
            "root": g.get("root"), "session_date": g.get("session_date"),
            "next_date": g.get("next_date"), "reason": g.get("reason"),
            "band_mult": g.get("band_mult"),
            "wall_contained": b.get("wall_contained"), "band_contained": b.get("band_contained"),
            "anchor_drew": b.get("anchor_drew"), "flip_pivot": b.get("flip_pivot"),
            "spot": b.get("spot"), "next_close": b.get("next_close"), "regime": b.get("regime")}
    if not g.get("nodes"):
        rows.append({**base, "level_id": base["board_id"], "role": "_board", "strike": None,
                     "sticky": None, "touched": None, "held": None, "broke": None,
                     "post_touch_move_pct": None})
        return rows
    for nd in g["nodes"]:
        rows.append({**base, "level_id": nd["level_id"], "role": nd["role"], "strike": nd["strike"],
                     "sticky": nd["sticky"], "touched": nd["touched"], "held": nd["held"],
                     "broke": nd["broke"], "post_touch_move_pct": nd["post_touch_move_pct"]})
    return rows


def _append_grades(new_rows: list[dict]) -> None:
    _LEVELS_DIR.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(new_rows)
    if _GRADES_PARQUET.exists():
        try:
            old = pd.read_parquet(_GRADES_PARQUET)
            new_ids = set(new_df["board_id"].unique())
            old = old[~old["board_id"].isin(new_ids)]  # upsert: new board wins
            new_df = pd.concat([old, new_df], ignore_index=True)
        except Exception as e:  # noqa: BLE001
            log.warning("grades parquet unreadable, rewriting fresh — %s", e)
    new_df = new_df.drop_duplicates(subset=["level_id"], keep="last")
    tmp = _GRADES_PARQUET.with_suffix(".tmp.parquet")
    new_df.to_parquet(tmp, index=False)
    tmp.replace(_GRADES_PARQUET)


# ── R2 (reuse the hub helpers' env contract) ──────────────────────────────────────

def _publish_r2(local: Path, key: str) -> bool:
    ak = os.environ.get("R2_ACCESS_KEY_ID"); sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    ep = os.environ.get("R2_ENDPOINT"); bucket = os.environ.get("R2_BUCKET", "mastermindx")
    if not (ak and sk and ep):
        log.warning("R2 creds absent — skipping publish")
        return False
    try:
        import boto3  # noqa: PLC0415
        s3 = boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                          aws_secret_access_key=sk, region_name="auto")
        s3.upload_file(str(local), bucket, key, ExtraArgs={"ContentType": "application/json"})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("R2 publish failed for %s — %s", key, e)
        return False


# ── main ──────────────────────────────────────────────────────────────────────────

def _resolve_roots(args) -> list[str]:
    if args.roots:
        return [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    if args.universe == "stocks" and _STOCKS_DIR.exists():
        return sorted(p.stem.upper() for p in _STOCKS_DIR.glob("*.parquet"))
    return []


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Reconstruct + grade historical levels boards.")
    ap.add_argument("--roots", default="")
    ap.add_argument("--universe", choices=["stocks"], default=None)
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--band-mult", type=float, default=1.96)
    args = ap.parse_args(argv)

    end = args.end or (_date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    roots = _resolve_roots(args)
    if not roots:
        log.error("no roots (pass --roots or --universe stocks)")
        return 2
    try:
        store = resolve_thetadata_store(required=True, purpose="levels track record")
    except Exception as e:  # noqa: BLE001
        log.error("no thetadata store: %s", e)
        return 3
    store = Path(store)
    years = list(range(int(args.start[:4]), int(end[:4]) + 1))
    today = _date.today().strftime("%Y-%m-%d")

    all_graded: list[dict] = []
    band_rows: list[dict] = []
    reasons: dict[str, int] = {}
    for root in roots:
        bars = _load_stock_bars(root)
        if bars is None:
            reasons["no_price_data"] = reasons.get("no_price_data", 0) + 1
            log.info("%s: not in data/stocks — skipped (coverage-honest)", root)
            continue
        dates = _greeks_dates(root, years, store, args.start, end)
        n_root = 0
        for sd in dates:
            nb = _next_bar(bars, sd)
            if nb is None:
                # board's next session hasn't happened yet (or after end): unmatured, not a miss
                reasons["not_yet_matured"] = reasons.get("not_yet_matured", 0) + 1
                continue
            if nb["date"] > today:
                reasons["not_yet_matured"] = reasons.get("not_yet_matured", 0) + 1
                continue
            rec, why = _reconstruct(root, sd, store)
            if rec is None:
                reasons[why] = reasons.get(why, 0) + 1
                continue
            g = grade_board(rec["levels"], nb, prior_close=_prior_close(bars, sd),
                            median_iv=rec["median_iv"], band_mult=args.band_mult)
            reasons[g["reason"]] = reasons.get(g["reason"], 0) + 1
            all_graded.append(g)
            if g["reason"] == "ok":
                band_rows.append({"spot": g["board"].get("spot"), "median_iv": rec["median_iv"],
                                  "next_high": nb["high"], "next_low": nb["low"],
                                  "regime": g["board"].get("regime")})
            n_root += 1
        clear_parquet_cache()
        if n_root:
            log.info("%s: graded %d boards", root, n_root)

    # persist per-node grades ledger
    rows = [r for g in all_graded for r in _grade_rows_from(g)]
    if rows:
        _append_grades(rows)

    # aggregate + learn the band multiplier (sticky vs slippery cohorts)
    tr = aggregate_track_record(all_graded, ci_fn=_wilson_ci)
    tr["reasons_all"] = reasons
    tr["window"] = {"start": args.start, "end": end}
    tr["roots"] = roots if len(roots) <= 50 else f"{len(roots)} roots"
    tr["learned_band_mult"] = {
        "all": learn_band_mult(band_rows),
        "sticky": learn_band_mult([b for b in band_rows if b.get("regime") == "sticky"]),
        "slippery": learn_band_mult([b for b in band_rows if b.get("regime") == "slippery"]),
        "target_containment": 0.667,
        "note": "smallest expected-move multiplier that would have contained the next-session range in ~2/3 of boards; learned separately for sticky and slippery days.",
    }
    tr["disclaimer"] = ("Statistics about the map — how often dealer-positioning levels described "
                        "what price did next. Positioning, not prophecy. Not a win rate, not a "
                        "strategy, never a buy or sell ranking. Misses are shown. The dealer-sign "
                        "convention behind sticky/slippery is assumed, not measured.")

    _LEVELS_DIR.mkdir(parents=True, exist_ok=True)
    _TR_JSON.write_text(json.dumps(tr, separators=(",", ":")))
    if args.publish:
        _publish_r2(_TR_JSON, R2_TR_KEY)

    graded_ok = tr["n_boards_graded"]
    log.info("levels track record: %d boards graded (of %d attempts) → %s",
             graded_ok, tr["n_boards"], _TR_JSON)
    for role in ("anchor", "cluster", "counter", "flip", "trapdoor", "launchpad", "walls"):
        pr = tr["per_role"].get(role)
        if pr and pr.get("n"):
            log.info("  %-9s %-28s %s  (n=%d, misses=%d)", role, pr["label"],
                     f"{pr['rate']:.0%}" if pr["rate"] is not None else "—", pr["n"], pr["misses"])
    bc = tr["board"]["band_contained"]
    if bc.get("n"):
        log.info("  band contained the range: %s (n=%d, misses=%d); learned mult all=%s sticky=%s slippery=%s",
                 f"{bc['rate']:.0%}", bc["n"], bc["misses"],
                 tr["learned_band_mult"]["all"], tr["learned_band_mult"]["sticky"],
                 tr["learned_band_mult"]["slippery"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
