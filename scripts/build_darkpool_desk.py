"""Build the Dark Pool Desk page → site/darkpool.html.

SEMANTICS (binding — roadmap R5):
  T1e: FINRA CNMSshvol daily off-exchange (FINRA-facility) volume — NOT "dark pool prints",
       NOT "live". The total_vol column is off-exchange volume reported to FINRA's consolidated
       market-surveillance facilities. "Dark pool share" = FINRA-facility vol ÷ consolidated
       day volume (joined from data/yahoo volume for the display universe).
  T2e: FINRA OTC Transparency weekly per-ATS venue breakdown — labeled with a 2–4 wk lag chip.

Display universe: options_universe.gex_symbols() (~360 tickers) — same universe restricted
in the backfill (SIZE LAW: full-universe 8y ~67MB > 30MB git ceiling).

Feature flag: config.yml key `darkpool.enabled` (default true). If false, this script
returns 0 immediately without writing the page, so the nav entry is never added.

Run: python -m scripts.build_darkpool_desk
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_darkpool_desk")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PANEL_PATH = config.data_dir() / "finra_short_volume" / "panel.parquet"
ATS_DIR    = config.data_dir() / "finra_ats"
YAHOO_DIR  = config.data_dir() / "yahoo"

# Min dates in panel for the page to be useful (roadmap 30-date floor)
MIN_DATES = 30

# History windows for z-score and trend
RECENT_DAYS  = 5      # "recent" window for short ratio
BASELINE_DAYS = 40    # longer baseline for z-score

# Per-name table cap (performance)
TABLE_CAP = 100


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_panel() -> pd.DataFrame | None:
    if not PANEL_PATH.exists():
        log.warning("panel not found: %s", PANEL_PATH)
        return None
    try:
        df = pd.read_parquet(PANEL_PATH)
    except Exception as e:  # noqa: BLE001
        log.warning("panel read failed: %s", e)
        return None
    if df.empty:
        return None
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "ticker"])


def _load_yahoo_volume(tickers: list[str]) -> dict[str, pd.Series]:
    """Load consolidated daily volume for the display universe from data/yahoo/.
    Returns {ticker: pd.Series(date->volume)}. Missing tickers are omitted gracefully."""
    out: dict[str, pd.Series] = {}
    for tk in tickers:
        p = YAHOO_DIR / f"{tk}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p, columns=["volume"])
            df.index = pd.to_datetime(df.index).normalize()
            s = df["volume"].dropna()
            if not s.empty:
                out[tk] = s
        except Exception:  # noqa: BLE001
            continue
    log.info("yahoo volume loaded for %d/%d tickers", len(out), len(tickers))
    return out


def _load_ats() -> pd.DataFrame | None:
    """Load latest available ATS weekly transparency data."""
    if not ATS_DIR.exists():
        return None
    # Week files are <YYYYMMDD>.parquet — the group dir ALSO holds the runner's
    # heartbeat series (finra_ats__ingest.parquet), which sorts lexicographically
    # AFTER every digit-named week file and used to shadow the real latest week
    # (schema mismatch → silent None → venue table never rendered).
    files = sorted(p for p in ATS_DIR.glob("*.parquet") if p.stem.isdigit())
    if not files:
        return None
    # Load latest week
    latest_file = files[-1]
    try:
        df = pd.read_parquet(latest_file)
        if df.empty:
            return None
        df["week_start"] = pd.to_datetime(df["week_start"])
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("ATS load failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def _compute_ticker_stats(panel: pd.DataFrame, yahoo_vol: dict[str, pd.Series]) -> list[dict]:
    """Per-name off-exchange share, short ratio, z-scores, trends.

    SEMANTICS: off_ex_share = FINRA-facility total_vol / yahoo consolidated volume.
    The denominator is labeled explicitly in the page copy.
    """
    rows: list[dict] = []
    for ticker, grp in panel.groupby("ticker"):
        grp = grp.sort_values("date")
        if len(grp) < 3:
            continue

        # Short ratio stats
        ratios = grp["short_ratio"].values
        latest_ratio = float(ratios[-1])
        recent_ratio = float(grp.tail(RECENT_DAYS)["short_vol"].sum() /
                             max(grp.tail(RECENT_DAYS)["total_vol"].sum(), 1))
        baseline_ratio = float(grp.tail(BASELINE_DAYS)["short_vol"].sum() /
                                max(grp.tail(BASELINE_DAYS)["total_vol"].sum(), 1))
        trend_pp = round((recent_ratio - baseline_ratio) * 100, 2)

        # Z-score vs own history
        if len(ratios) >= 5:
            mu = float(np.nanmean(ratios))
            sigma = float(np.nanstd(ratios))
            z = round((latest_ratio - mu) / sigma, 2) if sigma > 0 else 0.0
        else:
            z = 0.0

        # Off-exchange share: FINRA-facility vol ÷ consolidated (yahoo) vol
        asof_date = grp["date"].iloc[-1]
        oe_share: float | None = None
        oe_note = "denominator: yahoo consolidated vol"
        if ticker in yahoo_vol:
            ys = yahoo_vol[ticker]
            # Use the closest date within ±3 trading days
            nearby = ys.loc[(ys.index <= asof_date) & (ys.index >= asof_date - pd.Timedelta(days=5))]
            if not nearby.empty:
                cons_vol = float(nearby.iloc[-1])
                finra_vol = float(grp.iloc[-1]["total_vol"])
                if cons_vol > 0:
                    oe_share = round(finra_vol / cons_vol, 4)
        if oe_share is None:
            oe_note = "denominator unavailable"

        rows.append({
            "ticker": str(ticker),
            "asof": str(asof_date.date()),
            "short_ratio": round(latest_ratio, 4),
            "short_ratio_recent": round(recent_ratio, 4),
            "short_ratio_baseline": round(baseline_ratio, 4),
            "trend_pp": trend_pp,
            "ratio_z": z,
            "n_days": int(len(grp)),
            "oe_share": oe_share,          # None if denominator unavailable
            "oe_note": oe_note,
            "finra_total_vol": int(grp.iloc[-1]["total_vol"]),
        })
    return rows


def _sort_ticker_stats(ticker_stats: list[dict]) -> list[dict]:
    """Sort ticker rows by off-exchange share (desc), then by short_ratio (desc) for rows without share data."""
    # Sort by oe_share desc (those with data), then by short_ratio
    with_share = [r for r in ticker_stats if r["oe_share"] is not None]
    without_share = [r for r in ticker_stats if r["oe_share"] is None]
    sorted_rows = (
        sorted(with_share, key=lambda r: r["oe_share"], reverse=True)
        + sorted(without_share, key=lambda r: r["short_ratio"], reverse=True)
    )
    return sorted_rows


def _compute_ats_venue_table(ats_df: pd.DataFrame) -> dict:
    """Aggregate ATS data into a venue table (total shares and trades per venue)."""
    if ats_df is None or ats_df.empty:
        return {}
    week_start = str(ats_df["week_start"].iloc[0].date()) if not ats_df.empty else "unknown"
    venue_agg = (
        ats_df[ats_df["mpid"].str.len() > 0]
        .groupby(["mpid", "venue_name"])
        .agg(total_shares=("shares", "sum"), total_trades=("trades", "sum"), n_symbols=("ticker", "nunique"))
        .reset_index()
        .sort_values("total_shares", ascending=False)
    )
    venues = venue_agg.head(20).to_dict("records")
    for v in venues:
        v["total_shares"] = int(v["total_shares"])
        v["total_trades"] = int(v["total_trades"])
        v["n_symbols"] = int(v["n_symbols"])
    return {
        "week_start": week_start,
        "venues": venues,
        "n_symbols_total": int(ats_df["ticker"].nunique()),
    }


# ---------------------------------------------------------------------------
# Builder main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = config.load()
    dp_cfg = cfg.get("darkpool", {}) or {}
    if not dp_cfg.get("enabled", True):
        log.info("darkpool.enabled=false in config — writing disabled stub (noindex + banner)")
        site = config.ROOT / "site"
        site.mkdir(parents=True, exist_ok=True)
        stub_html = (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='robots' content='noindex,nofollow'>"
            "<title>Dark Pool Desk — disabled</title>"
            "<link rel='stylesheet' href='theme.css'></head>"
            "<body style='padding:40px;font-family:system-ui,sans-serif'>"
            "<h1>Dark Pool Desk</h1>"
            "<p style='color:var(--muted,#888)'>This feature is currently disabled.</p>"
            "</body></html>"
        )
        write_page(site / "darkpool.html", stub_html)
        return 0

    # Load panel
    panel = _load_panel()
    if panel is None:
        log.error("panel missing — run: python -m scripts.backfill_finra_short_volume")
        return 0

    n_dates = panel["date"].nunique()
    log.info("panel: %d rows, %d dates, %d tickers", len(panel), n_dates, panel["ticker"].nunique())

    if n_dates < MIN_DATES:
        log.warning("panel has only %d dates (floor=%d) — page will show thin-data warning",
                    n_dates, MIN_DATES)

    # Display universe
    try:
        from engine.options_universe import gex_symbols
        display_universe = set(gex_symbols())
    except Exception as e:  # noqa: BLE001
        log.warning("options_universe load failed (%s) — using panel tickers", e)
        display_universe = set(panel["ticker"].unique())

    panel_universe = panel[panel["ticker"].isin(display_universe)] if display_universe else panel
    tickers = list(panel_universe["ticker"].unique())

    # Load yahoo volumes for off-exchange share computation
    yahoo_vol = _load_yahoo_volume(tickers)

    # Compute per-name stats
    ticker_stats = _compute_ticker_stats(panel_universe, yahoo_vol)
    ticker_stats = _sort_ticker_stats(ticker_stats)

    # Cap table for rendering
    table_rows = ticker_stats[:TABLE_CAP]

    # ATS venue table
    ats_df = _load_ats()
    ats_table = _compute_ats_venue_table(ats_df)

    # Data freshness
    panel_latest = str(panel["date"].max().date())
    panel_dates  = n_dates
    below_floor  = n_dates < MIN_DATES
    ats_week_start = ats_table.get("week_start")
    ats_lag_note  = "2–4 wk publication lag" if ats_week_start else None

    # Render
    site = config.ROOT / "site"
    site.mkdir(parents=True, exist_ok=True)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    from engine.i18n import td, tr
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")),
        autoescape=True,
    )
    env.globals.update(td=td, tr=tr, zip=zip, len=len)

    html = env.get_template("darkpool.html.j2").render(
        built=built,
        panel_latest=panel_latest,
        panel_dates=panel_dates,
        below_floor=below_floor,
        table_rows=table_rows,
        ats_table=ats_table,
        ats_lag_note=ats_lag_note,
        n_tickers_total=len(ticker_stats),
        display_universe_size=len(display_universe) or len(tickers),
        has_oe_share=any(r["oe_share"] is not None for r in table_rows),
    )
    out = site / "darkpool.html"
    write_page(out, html)
    log.info("wrote %s (%d KB, %d rows, %d dates)",
             out, len(html) // 1024, len(table_rows), panel_dates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
