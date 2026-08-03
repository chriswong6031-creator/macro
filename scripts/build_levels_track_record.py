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
_INDEX_BARS_DIR = _LEVELS_DIR / "index_bars"
_GRADES_PARQUET = _LEVELS_DIR / "grades.parquet"
_TR_JSON = _LEVELS_DIR / "track_record.json"
R2_TR_KEY = "levels_track_record.json"

# R2.4b index lane: the anchor roots the theta store carries greeks for. data/stocks
# has no ETF/index bars, so these grade against data/levels/index_bars (written by
# scripts/refresh_index_bars.py). SPXW is the weekly book on the SAME underlying index,
# so it grades against the SPX bars.
INDEX_ROOTS: tuple[str, ...] = ("SPY", "QQQ", "IWM", "DIA", "SPX", "SPXW")
_BAR_ALIASES = {"SPXW": "SPX"}


# ── price bars (data/stocks — the only US store with high/low; index roots fall
#    back to data/levels/index_bars, same schema) ─────────────────────────────────

def _load_stock_bars(root: str) -> pd.DataFrame | None:
    p = _STOCKS_DIR / f"{root}.parquet"
    if not p.exists():
        p = _INDEX_BARS_DIR / f"{_BAR_ALIASES.get(root, root)}.parquet"
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


def _prior_bar(bars: pd.DataFrame, session_date: str) -> dict | None:
    """{high, low} of the bar at-or-before session_date — the board session's own
    extremes, feeding the R2.4b prior-day-extreme null. Adjusted basis, same as
    next_bar, so no rebase is needed."""
    d = pd.Timestamp(session_date)
    upto = bars[bars.index <= d]
    if upto.empty:
        return None
    row = upto.iloc[-1]
    try:
        h, l = float(row["high"]), float(row["low"])
    except (TypeError, ValueError, KeyError):
        return None
    if h != h or l != l:  # NaN guard
        return None
    return {"high": h, "low": l}


def _ffloat(x) -> float | None:
    try:
        v = float(x)
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


# A k outside this range is a bad print, not a real corporate action (largest real split
# ~50:1 → k=0.02; a huge reverse split → k~50). Anything wilder is data error → don't scale.
_REBASE_K_MIN, _REBASE_K_MAX = 0.01, 100.0


def _rebase_to_adjusted(levels: dict, prior_close: float | None) -> dict:
    """Rebase a raw-priced reconstructed board onto the ADJUSTED basis of the stock bars.

    BACK-ADJUSTMENT BASIS BUG: the ThetaData greeks store carries RAW prices + strikes
    (split- AND dividend-UNADJUSTED), while data/stocks bars are back-adjusted for BOTH.
    Grading a raw board against an adjusted bar is a basis error that COMPOUNDS backward in
    time, from two sources:
      • splits   — a step change (pre-split NVDA spot ~$1208 vs adjusted bar ~$120, ~10x), and
      • dividends — a slow drift (XOM 2024 raw $114.96 vs adjusted $107.65 = 6.8%; KO ~5.8%).
    Splits crater the big names; the dividend drift is small but DEADLY for low-vol
    high-dividend names (XOM/KO/JNJ/utilities/staples): their expected-move band is so tight
    (±~1-3%) that even a ~6% offset falls entirely outside it EVERY session → ~0% containment
    for a whole year. (The first cut of this fix, #3155, gated on |k-1|>0.10 to catch only
    splits; that left the dividend drift uncorrected and 52 low-vol names graded ~0% in 2024,
    dragging the universe to 51% — hence the UNCONDITIONAL rebase here.)

    Fix: anchor every board's spot to the adjusted prior-close and scale the whole board —
    spot + every node strike/range — by ``k = prior_close_adjusted / spot_raw``. One
    self-calibrating transform for splits, dividends AND intraday basis together, needing no
    corporate-action feed. For a genuinely clean name k≈1 (near-no-op). IV is scale-invariant,
    so the expected-move band rescales automatically and its width-as-percent is unchanged.
    """
    if not isinstance(levels, dict):
        return levels
    spot = _ffloat(levels.get("spot"))
    if spot is None:
        spot = _ffloat(levels.get("spot_ref"))
    pc = _ffloat(prior_close)
    if spot is None or spot <= 0 or pc is None or pc <= 0:
        return levels  # can't establish basis — grade as-is
    k = pc / spot
    if not (_REBASE_K_MIN <= k <= _REBASE_K_MAX):
        return levels  # absurd ratio = a bad print, not a real corporate action — don't scale
    out = dict(levels)
    for f in ("spot", "spot_ref"):
        v = _ffloat(out.get(f))
        if v is not None:
            out[f] = round(v * k, 4)
    new_nodes = []
    for nd in (levels.get("nodes") or []):
        if not isinstance(nd, dict):
            new_nodes.append(nd)
            continue
        nd2 = dict(nd)
        for f in ("strike", "strike_lo", "strike_hi"):
            v = _ffloat(nd2.get(f))
            if v is not None:
                nd2[f] = round(v * k, 4)
        new_nodes.append(nd2)
    out["nodes"] = new_nodes
    out["rebased_k"] = round(k, 6)  # audit trail: back-adjustment rebase factor applied
    return out


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
    pdv = b.get("prevday") or {}
    base = {"board_id": board_id(g.get("root") or "", g.get("session_date") or ""),
            "root": g.get("root"), "session_date": g.get("session_date"),
            "next_date": g.get("next_date"), "reason": g.get("reason"),
            "band_mult": g.get("band_mult"),
            "wall_contained": b.get("wall_contained"), "band_contained": b.get("band_contained"),
            "wall_range_contained": b.get("wall_range_contained"),
            "band_close_contained": b.get("band_close_contained"),
            "pd_high_held": pdv.get("high_held"), "pd_low_held": pdv.get("low_held"),
            "pd_range_contained_close": pdv.get("range_contained_close"),
            "pd_range_contained_range": pdv.get("range_contained_range"),
            "anchor_drew": b.get("anchor_drew"), "flip_pivot": b.get("flip_pivot"),
            "spot": b.get("spot"), "next_close": b.get("next_close"), "regime": b.get("regime")}
    if not g.get("nodes"):
        rows.append({**base, "level_id": base["board_id"], "role": "_board", "strike": None,
                     "sticky": None, "touched": None, "held": None, "broke": None,
                     "post_touch_move_pct": None, "null_touched": None, "null_held": None,
                     "pierce_pct": None})
        return rows
    for nd in g["nodes"]:
        rows.append({**base, "level_id": nd["level_id"], "role": nd["role"], "strike": nd["strike"],
                     "sticky": nd["sticky"], "touched": nd["touched"], "held": nd["held"],
                     "broke": nd["broke"], "post_touch_move_pct": nd["post_touch_move_pct"],
                     "null_touched": nd.get("null_touched"), "null_held": nd.get("null_held"),
                     "pierce_pct": nd.get("pierce_pct")})
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
    if args.universe == "index":
        return list(INDEX_ROOTS)
    return []


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Reconstruct + grade historical levels boards.")
    ap.add_argument("--roots", default="")
    ap.add_argument("--universe", choices=["stocks", "index"], default=None)
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
            pc = _prior_close(bars, sd)
            # rebase the RAW greeks board onto the ADJUSTED bar basis before grading
            # (split-adjustment fix — see _rebase_to_adjusted). No-op for clean names.
            levels_adj = _rebase_to_adjusted(rec["levels"], pc)
            g = grade_board(levels_adj, nb, prior_close=pc,
                            median_iv=rec["median_iv"], band_mult=args.band_mult,
                            prior_bar=_prior_bar(bars, sd))
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
