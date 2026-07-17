"""Build the US Options Screener page → site/options_screener.html.

Display-only. No score/rank path. Coverage is honestly stamped on every surface:
  - n_names: names with polygon_gex summaries present
  - history_depth_days: calendar days from first to last date in the per-ticker parquet
  - young_threshold: IV-rank labelled "young (n=Xd)" when history_depth_days < 252

Data inputs (all read-only):
  - data/polygon_gex/summary_<TICKER>.parquet   (384 names; iv30, put_call_oi_ratio,
      max_pain, magnet_up, magnet_down, gamma_flip, tier — daily since 2026-06-15)
  - data/options_flow/summary_<TICKER>.parquet  (353 names; volume, premium_mn,
      net_premium_mn, pc_ratio, zerodte_share — magnitude reliable, direction SOFT)
  - data/options_skew/snapshots.parquet         (~400 names; skew = otm_put_iv − atm_call_iv,
      tenor ~30d, latest date per underlying)
  - data/options_ivspread/snapshots.parquet     (~370 names; ivspread_rel = spread vs
      cross-sectional peer median; latest date per underlying)
  - data/tape_flow/daily/                       (accruing; read if present)

Columns assembled:
  ticker, sector (basket category or "ETF/Index"), iv30, iv_rank (pct of available
  history — young-labelled while <252d), pc_oi (put/call OI ratio), volume,
  gross_premium_mn, implied_move_30d_pct (IV30 × sqrt(30/365) × 100),
  max_pain, gex_tier, net_prem_tone (~-soft chip: labeled heuristic only),
  gamma_regime, dist_to_flip_pct, net_gex_bn,
  pain_dist_pct, wall_up_dist_pct, wall_down_dist_pct,
  iv30_chg_5d, rel_volume, net_doi,
  skew_pp, skew_tenor_d, ivspread_pp

Feature flag: config.yml key `options_screener.enabled` (default true).  If false,
this script returns 0 immediately, emitting a noindex stub — same darkpool precedent.

Run: python -m scripts.build_options_screener
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_options_screener")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GEX_DIR       = config.data_dir() / "polygon_gex"
FLOW_DIR      = config.data_dir() / "options_flow"
TAPE_FLOW_DIR = config.data_dir() / "tape_flow" / "daily"
SKEW_PATH     = config.data_dir() / "options_skew" / "snapshots.parquet"
IVSPREAD_PATH = config.data_dir() / "options_ivspread" / "snapshots.parquet"

# IV-rank is labelled "young" when fewer than this many calendar days of history
YOUNG_THRESHOLD_DAYS = 252


# ---------------------------------------------------------------------------
# Sector / category lookup from baskets membership
# ---------------------------------------------------------------------------

def _build_sector_map() -> dict[str, str]:
    """Return {ticker: category_label} from baskets membership.json.

    Falls back to 'ETF / Index' for tickers not found in any basket.
    'category' is the basket's broad theme group (e.g. 'AI & Technology').
    First basket wins if a ticker appears in multiple.
    """
    try:
        p = config.data_dir() / "baskets" / "membership.json"
        if not p.exists():
            return {}
        doc = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("sector_map: membership.json unreadable (%s)", e)
        return {}

    baskets = doc.get("baskets") or {}
    items = baskets.values() if isinstance(baskets, dict) else baskets
    out: dict[str, str] = {}
    for b in items:
        if not isinstance(b, dict):
            continue
        cat = b.get("category") or "Other"
        for m in (b.get("members") or []):
            if isinstance(m, dict):
                if m.get("removed"):
                    continue
                t = m.get("ticker")
            else:
                t = m
            if t and isinstance(t, str):
                out.setdefault(t.upper(), cat)
    return out


# ---------------------------------------------------------------------------
# Snapshot lookup tables (loaded once)
# ---------------------------------------------------------------------------

def _load_skew_lookup() -> dict[str, dict]:
    """Return {TICKER: {skew_pp, skew_tenor_d}} from latest date per underlying."""
    if not SKEW_PATH.exists():
        return {}
    try:
        df = pd.read_parquet(SKEW_PATH)
        if df.empty:
            return {}
        # latest date per underlying
        df = df.sort_values("date")
        # whole-row take: groupby.last() is per-column last-VALID and can mix dates
        latest = df.sort_values("date").drop_duplicates("underlying", keep="last")
        out: dict[str, dict] = {}
        for _, row in latest.iterrows():
            underlying = str(row["underlying"]).upper()
            skew_val = row.get("skew")
            tenor_val = row.get("tenor_days")
            skew_pp = None
            if skew_val is not None:
                try:
                    f = float(skew_val)
                    if not (math.isnan(f) or math.isinf(f)):
                        skew_pp = round(f * 100, 1)
                except (TypeError, ValueError):
                    pass
            tenor_d = None
            if tenor_val is not None:
                try:
                    f = float(tenor_val)
                    if not (math.isnan(f) or math.isinf(f)):
                        tenor_d = int(f)
                except (TypeError, ValueError):
                    pass
            out[underlying] = {"skew_pp": skew_pp, "skew_tenor_d": tenor_d}
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("skew lookup failed: %s", e)
        return {}


def _load_ivspread_lookup() -> dict[str, float | None]:
    """Return {TICKER: ivspread_pp} from latest date per underlying.

    ivspread_rel = each name's IV-spread minus the cross-sectional peer median.
    ivspread_pp = ivspread_rel * 100, rounded to 1 decimal.
    """
    if not IVSPREAD_PATH.exists():
        return {}
    try:
        df = pd.read_parquet(IVSPREAD_PATH)
        if df.empty:
            return {}
        df = df.sort_values("date")
        # whole-row take: groupby.last() is per-column last-VALID and can mix dates
        latest = df.sort_values("date").drop_duplicates("underlying", keep="last")
        out: dict[str, float | None] = {}
        for _, row in latest.iterrows():
            underlying = str(row["underlying"]).upper()
            val = row.get("ivspread_rel")
            ivspread_pp = None
            if val is not None:
                try:
                    f = float(val)
                    if not (math.isnan(f) or math.isinf(f)):
                        ivspread_pp = round(f * 100, 1)
                except (TypeError, ValueError):
                    pass
            out[underlying] = ivspread_pp
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("ivspread lookup failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Per-ticker GEX summary loader
# ---------------------------------------------------------------------------

def _load_gex_summary(ticker: str) -> pd.DataFrame | None:
    p = GEX_DIR / f"summary_{ticker}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("gex summary read failed %s: %s", ticker, e)
        return None


def _compute_iv_rank(df: pd.DataFrame) -> tuple[float | None, int, bool]:
    """Return (iv_rank 0-100, n_days, is_young) from a GEX summary DataFrame.

    iv_rank = percentile of current IV30 within available history.
    is_young = True when history_depth_days < YOUNG_THRESHOLD_DAYS.
    """
    if df is None or df.empty or "iv30" not in df.columns:
        return None, 0, True

    iv_series = df["iv30"].dropna()
    n = len(iv_series)
    if n < 2:
        return None, n, True

    current = float(iv_series.iloc[-1])
    rank = float((iv_series < current).sum()) / (n - 1) * 100
    # history depth in calendar days
    try:
        idx = pd.to_datetime(df.index)
        depth_days = (idx[-1] - idx[0]).days
    except Exception:  # noqa: BLE001
        depth_days = n  # fallback: treat as n trading days
    is_young = depth_days < YOUNG_THRESHOLD_DAYS
    return round(rank, 1), n, is_young


def _compute_iv30_chg_5d(df: pd.DataFrame) -> float | None:
    """Return 5-day IV-change in IV points ×100 (latest − 5-rows-earlier), or None.

    Requires ≥6 rows of iv30 data.
    """
    if df is None or df.empty or "iv30" not in df.columns:
        return None
    iv_series = df["iv30"].dropna()
    if len(iv_series) < 6:
        return None
    try:
        latest = float(iv_series.iloc[-1])
        five_back = float(iv_series.iloc[-6])
        chg = (latest - five_back) * 100
        return round(chg, 1)
    except (TypeError, ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Per-ticker flow summary loader
# ---------------------------------------------------------------------------

def _load_flow_summary(ticker: str) -> tuple[dict[str, Any], pd.DataFrame | None]:
    """Return (latest_row_dict, full_df) from options_flow summary, or ({}, None)."""
    p = FLOW_DIR / f"summary_{ticker}.parquet"
    if not p.exists():
        return {}, None
    try:
        df = pd.read_parquet(p)
        if df.empty:
            return {}, None
        row = df.iloc[-1]
        return row.to_dict(), df
    except Exception as e:  # noqa: BLE001
        log.debug("flow summary read failed %s: %s", ticker, e)
        return {}, None


def _compute_rel_volume(flow_df: pd.DataFrame | None) -> float | None:
    """Return rel_volume = latest volume / mean(prior 20 sessions volume).

    Requires ≥5 prior sessions (excluding latest). Returns None otherwise.
    """
    if flow_df is None or flow_df.empty or "volume" not in flow_df.columns:
        return None
    vol_series = flow_df["volume"].dropna()
    if len(vol_series) < 6:  # need latest + ≥5 prior
        return None
    try:
        latest = float(vol_series.iloc[-1])
        prior = vol_series.iloc[-21:-1]  # up to 20 prior sessions
        if len(prior) < 5:
            return None
        mean_prior = float(prior.mean())
        if mean_prior <= 0:
            return None
        return round(latest / mean_prior, 2)
    except (TypeError, ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# tape_flow loader (optional — may not exist yet)
# ---------------------------------------------------------------------------

def _load_tape_tone(ticker: str) -> str | None:
    """Return the net-premium tone label from tape_flow if available, else None.

    Direction is SOFT — labeled 'notable/unusual heuristic', never 'signal'.
    """
    if not TAPE_FLOW_DIR.exists():
        return None
    # Find the most recent file for this ticker
    files = sorted(TAPE_FLOW_DIR.glob(f"*{ticker}*.parquet"))
    if not files:
        # also check daily directory parquet files for embedded ticker column
        return None
    try:
        df = pd.read_parquet(files[-1])
        if "ticker" in df.columns:
            df = df[df["ticker"] == ticker]
        if df.empty:
            return None
        row = df.iloc[-1]
        # net_signed_prem_z column preferred; fall back to net_premium_mn sign
        if "net_signed_prem_z" in row.index:
            z = float(row["net_signed_prem_z"])
            if z > 0.5:
                return "call-leaning"
            elif z < -0.5:
                return "put-leaning"
            return "neutral"
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# Assemble screener rows
# ---------------------------------------------------------------------------

def _safe_float(v: Any, ndigits: int = 2) -> float | None:
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, ndigits)
    except (TypeError, ValueError):
        return None


def _net_prem_tone(net_prem: float | None, tape_tone: str | None) -> str:
    """Return a labeled heuristic tone chip — SOFT, labeled as such.

    Priority: tape_flow z-score > net_premium_mn sign.
    Returns one of: 'call-leaning', 'put-leaning', 'neutral', '' (no data).
    This is a labeled heuristic, never a signal.
    """
    if tape_tone:
        return tape_tone
    if net_prem is None:
        return ""
    if net_prem > 0:
        return "call-leaning"
    if net_prem < 0:
        return "put-leaning"
    return "neutral"


def build_screener_rows(
    sector_map: dict[str, str],
    skew_lookup: dict[str, dict],
    ivspread_lookup: dict[str, float | None],
) -> tuple[list[dict], dict[str, Any]]:
    """Load all available tickers and build the screener row list.

    Returns (rows, coverage_meta).
    """
    # Discover tickers from GEX summaries (primary store)
    gex_files = sorted(GEX_DIR.glob("summary_*.parquet"))
    tickers = [f.stem.replace("summary_", "") for f in gex_files]
    log.info("discovered %d tickers from polygon_gex summaries", len(tickers))

    flow_tickers = {
        f.stem.replace("summary_", "")
        for f in FLOW_DIR.glob("summary_*.parquet")
    }

    rows = []
    n_young = 0
    depth_days_list = []
    n_skew = 0
    n_ivspread = 0
    n_relvol = 0

    for ticker in tickers:
        gex_df = _load_gex_summary(ticker)
        if gex_df is None or gex_df.empty:
            continue

        latest = gex_df.iloc[-1]
        asof_date = str(gex_df.index[-1])[:10]

        iv30 = _safe_float(latest.get("iv30"), 4)
        iv_rank, n_days, is_young = _compute_iv_rank(gex_df)
        if is_young:
            n_young += 1
        if n_days > 0:
            depth_days_list.append(n_days)

        # Implied move proxy: IV30 × sqrt(30/365) — computable from store
        implied_move_30d = None
        if iv30 is not None:
            implied_move_30d = round(iv30 * math.sqrt(30 / 365) * 100, 1)

        spot = _safe_float(latest.get("spot"))
        max_pain = _safe_float(latest.get("max_pain"), 2)
        wall_up = _safe_float(latest.get("magnet_up"), 2)
        wall_down = _safe_float(latest.get("magnet_down"), 2)
        gamma_flip = _safe_float(latest.get("gamma_flip"), 2)
        tier = str(latest.get("tier") or "")

        # New GEX fields
        gamma_regime = str(latest.get("gamma_regime") or "") or None
        dist_to_flip_pct = _safe_float(latest.get("dist_to_flip_pct"), 2)
        net_gex_bn = _safe_float(latest.get("net_gex_bn"), 3)

        # Computed distances (null-safe)
        pain_dist_pct = None
        if spot is not None and max_pain is not None and max_pain != 0:
            pain_dist_pct = round((spot - max_pain) / max_pain * 100, 2)

        wall_up_dist_pct = None
        if wall_up is not None and spot is not None and spot != 0:
            wall_up_dist_pct = round((wall_up - spot) / spot * 100, 2)

        wall_down_dist_pct = None
        if wall_down is not None and spot is not None and spot != 0:
            wall_down_dist_pct = round((spot - wall_down) / spot * 100, 2)

        # IV30 5-day change
        iv30_chg_5d = _compute_iv30_chg_5d(gex_df)

        # GEX store put/call OI ratio
        pc_oi_gex = _safe_float(latest.get("put_call_oi_ratio"), 3)

        # Options flow store
        if ticker in flow_tickers:
            flow, flow_df = _load_flow_summary(ticker)
        else:
            flow, flow_df = {}, None

        volume = int(flow["volume"]) if flow.get("volume") and not math.isnan(float(flow["volume"])) else None
        premium_mn = _safe_float(flow.get("premium_mn"), 2)
        net_prem_mn = _safe_float(flow.get("net_premium_mn"), 2)
        pc_ratio_flow = _safe_float(flow.get("pc_ratio"), 3)
        zerodte = _safe_float(flow.get("zerodte_share"), 3)

        # net_doi (latest, absent-safe int)
        net_doi_raw = flow.get("net_doi")
        net_doi = None
        if net_doi_raw is not None:
            try:
                f = float(net_doi_raw)
                if not (math.isnan(f) or math.isinf(f)):
                    net_doi = int(f)
            except (TypeError, ValueError):
                pass

        # rel_volume
        rel_volume = _compute_rel_volume(flow_df)
        if rel_volume is not None:
            n_relvol += 1

        # Use flow pc_ratio when available; fall back to gex store
        pc_oi = pc_ratio_flow if pc_ratio_flow is not None else pc_oi_gex

        # tape_flow tone (optional)
        tape_tone = _load_tape_tone(ticker)
        tone = _net_prem_tone(net_prem_mn, tape_tone)

        sector = sector_map.get(ticker, "ETF / Index")

        # Skew join
        skew_data = skew_lookup.get(ticker, {})
        skew_pp = skew_data.get("skew_pp")
        skew_tenor_d = skew_data.get("skew_tenor_d")
        if skew_pp is not None:
            n_skew += 1

        # IV-spread join
        ivspread_pp = ivspread_lookup.get(ticker)
        if ivspread_pp is not None:
            n_ivspread += 1

        rows.append({
            "ticker": ticker,
            "sector": sector,
            "asof": asof_date,
            "iv30": round(iv30 * 100, 1) if iv30 is not None else None,  # pct
            "iv_rank": iv_rank,
            "iv_rank_n": n_days,
            "iv_rank_young": is_young,
            "implied_move_30d": implied_move_30d,
            "pc_oi": pc_oi,
            "volume": volume,
            "gross_premium_mn": premium_mn,
            "net_prem_mn": net_prem_mn,
            "zerodte_share": round(zerodte * 100, 1) if zerodte is not None else None,
            "max_pain": max_pain,
            "spot": spot,
            "wall_up": wall_up,
            "wall_down": wall_down,
            "gamma_flip": gamma_flip,
            "gex_tier": tier,
            "net_prem_tone": tone,
            # New fields
            "gamma_regime": gamma_regime,
            "dist_to_flip_pct": dist_to_flip_pct,
            "net_gex_bn": net_gex_bn,
            "pain_dist_pct": pain_dist_pct,
            "wall_up_dist_pct": wall_up_dist_pct,
            "wall_down_dist_pct": wall_down_dist_pct,
            "iv30_chg_5d": iv30_chg_5d,
            "rel_volume": rel_volume,
            "net_doi": net_doi,
            "skew_pp": skew_pp,
            "skew_tenor_d": skew_tenor_d,
            "ivspread_pp": ivspread_pp,
        })

    # Sort: by gross_premium_mn desc (most active first), then ticker
    rows.sort(key=lambda r: (-(r["gross_premium_mn"] or 0), r["ticker"]))

    # Determine overall history depth (median days)
    med_depth = int(sorted(depth_days_list)[len(depth_days_list) // 2]) if depth_days_list else 0

    coverage = {
        "n_names": len(rows),
        "n_young": n_young,
        "n_mature": len(rows) - n_young,
        "median_depth_days": med_depth,
        "young_threshold": YOUNG_THRESHOLD_DAYS,
        "tape_flow_present": TAPE_FLOW_DIR.exists(),
        "n_skew": n_skew,
        "n_ivspread": n_ivspread,
        "n_relvol": n_relvol,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    return rows, coverage


# ---------------------------------------------------------------------------
# Builder main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = config.load()
    os_cfg = cfg.get("options_screener", {}) or {}
    if not os_cfg.get("enabled", True):
        log.info("options_screener.enabled=false — writing disabled stub (noindex + banner)")
        site = config.ROOT / "site"
        site.mkdir(parents=True, exist_ok=True)
        stub_html = (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='robots' content='noindex,nofollow'>"
            "<title>Options Screener — disabled</title>"
            "<link rel='stylesheet' href='theme.css'></head>"
            "<body style='padding:40px'>"
            "<h1>Options Screener</h1>"
            "<p>This page is currently disabled.</p>"
            "</body></html>"
        )
        write_page(site / "options_screener.html", stub_html)
        return 0

    # Check primary store exists
    if not GEX_DIR.exists():
        log.warning("polygon_gex store not found at %s — aborting", GEX_DIR)
        return 0

    gex_count = len(list(GEX_DIR.glob("summary_*.parquet")))
    if gex_count == 0:
        log.warning("no polygon_gex summary files found — aborting")
        return 0

    sector_map = _build_sector_map()
    skew_lookup = _load_skew_lookup()
    ivspread_lookup = _load_ivspread_lookup()
    log.info("loaded skew lookup: %d names, ivspread lookup: %d names", len(skew_lookup), len(ivspread_lookup))

    rows, coverage = build_screener_rows(sector_map, skew_lookup, ivspread_lookup)
    log.info(
        "assembled %d rows (%d young IV-rank, median %dd history, "
        "skew=%d ivspread=%d relvol=%d)",
        len(rows), coverage["n_young"], coverage["median_depth_days"],
        coverage["n_skew"], coverage["n_ivspread"], coverage["n_relvol"],
    )

    # Render
    site = config.ROOT / "site"
    site.mkdir(parents=True, exist_ok=True)

    from engine.i18n import td, tr
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")),
        autoescape=True,
    )
    env.globals.update(
        td=td, tr=tr, zip=zip, len=len,
        options_screener_enabled=os_cfg.get("enabled", True),
    )

    rows_json = json.dumps(rows, ensure_ascii=False, default=str).replace("</", r"<\/")

    html = env.get_template("options_screener.html.j2").render(
        coverage=coverage,
        rows_json=rows_json,
        n_rows=len(rows),
        built=coverage["built"],
    )
    out = site / "options_screener.html"
    write_page(out, html)
    log.info("wrote %s (%d KB, %d rows)", out, len(html) // 1024, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
