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
RECENT_DAYS   = 5      # "recent" window for short ratio and oe share
BASELINE_DAYS = 40     # longer baseline for z-score
SPARK_DAYS    = 20     # sparkline history

# Minimum observations for oe_z to be meaningful
OE_Z_MIN_OBS  = 20


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


def _load_ats_two() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Load the latest TWO ATS weekly parquet files (digit-named only).
    Returns (latest_df, prior_df). Either may be None."""
    if not ATS_DIR.exists():
        return None, None
    files = sorted(p for p in ATS_DIR.glob("*.parquet") if p.stem.isdigit())
    if not files:
        return None, None
    latest_df = _safe_load_ats(files[-1])
    prior_df  = _safe_load_ats(files[-2]) if len(files) >= 2 else None
    return latest_df, prior_df


def _safe_load_ats(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        df["week_start"] = pd.to_datetime(df["week_start"])
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("ATS load failed %s: %s", path.name, e)
        return None


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def _compute_ticker_stats(
    panel: pd.DataFrame,
    yahoo_vol: dict[str, pd.Series],
    ats_latest: pd.DataFrame | None,
    ats_week_start: pd.Timestamp | None,
) -> tuple[list[dict], int, int]:
    """Per-name off-exchange share series, short ratio, z-scores, trends, ATS join.

    SEMANTICS: off_ex_share = FINRA-facility total_vol / yahoo consolidated volume.
    The denominator is labeled explicitly in the page copy.

    Returns: (rows, n_with_oe, n_with_ats)
    """
    # Build per-ticker ATS lookup {ticker -> {ats_shares, ats_top_venue, ats_venues_n, ats_share_pct}}
    ats_lookup: dict[str, dict] = {}
    if ats_latest is not None:
        for ticker, grp in ats_latest.groupby("ticker"):
            ats_shares = float(grp["shares"].sum())
            top_idx = grp["shares"].idxmax() if not grp.empty else None
            ats_top_venue = str(grp.loc[top_idx, "venue_name"]) if top_idx is not None else None
            ats_venues_n = int(grp["mpid"].nunique())

            # ats_share_pct = ats_shares / sum(yahoo vol in that ATS week Mon–Fri)
            ats_share_pct: float | None = None
            if ats_week_start is not None and str(ticker) in yahoo_vol:
                week_end = ats_week_start + pd.Timedelta(days=4)
                ys = yahoo_vol[str(ticker)]
                week_vol = float(ys.loc[(ys.index >= ats_week_start) & (ys.index <= week_end)].sum())
                if week_vol > 0:
                    ats_share_pct = round(ats_shares / week_vol * 100, 2)

            ats_lookup[str(ticker)] = {
                "ats_shares": int(ats_shares),
                "ats_top_venue": ats_top_venue,
                "ats_venues_n": ats_venues_n,
                "ats_share_pct": ats_share_pct,
            }

    rows: list[dict] = []
    n_with_oe = 0
    n_with_ats = 0

    for ticker, grp in panel.groupby("ticker"):
        grp = grp.sort_values("date")
        if len(grp) < 3:
            continue

        # --- Short ratio stats ---
        ratios = grp["short_ratio"].values
        latest_ratio = float(ratios[-1])
        recent_ratio = float(grp.tail(RECENT_DAYS)["short_vol"].sum() /
                             max(grp.tail(RECENT_DAYS)["total_vol"].sum(), 1))
        baseline_ratio = float(grp.tail(BASELINE_DAYS)["short_vol"].sum() /
                                max(grp.tail(BASELINE_DAYS)["total_vol"].sum(), 1))
        trend_pp = round((recent_ratio - baseline_ratio) * 100, 2)

        # Z-score of short ratio vs own history
        if len(ratios) >= 5:
            mu = float(np.nanmean(ratios))
            sigma = float(np.nanstd(ratios))
            z = round((latest_ratio - mu) / sigma, 2) if sigma > 0 else 0.0
        else:
            z = 0.0

        # --- Off-exchange share series (exact-date inner join with yahoo) ---
        oe_share: float | None = None
        oe_share_5d: float | None = None
        oe_share_40d: float | None = None
        oe_trend_pp: float | None = None
        oe_z: float | None = None
        spark20: list[float] = []

        if str(ticker) in yahoo_vol:
            ys = yahoo_vol[str(ticker)]
            finra_ser = grp.drop_duplicates("date", keep="last").set_index("date")["total_vol"]
            # Exact-date inner join
            joined = finra_ser.to_frame().join(ys.rename("yahoo_vol"), how="inner")
            joined = joined[joined["yahoo_vol"] > 0]
            if not joined.empty:
                oe_ser = joined["total_vol"] / joined["yahoo_vol"]
                oe_ser = oe_ser.dropna()
                if not oe_ser.empty:
                    oe_share = round(float(oe_ser.iloc[-1]), 4)
                    n_with_oe += 1
                    tail5 = oe_ser.tail(RECENT_DAYS)
                    tail40 = oe_ser.tail(BASELINE_DAYS)
                    oe_share_5d  = round(float(tail5.mean()), 4) if len(tail5) >= 1 else None
                    oe_share_40d = round(float(tail40.mean()), 4) if len(tail40) >= 5 else None
                    if oe_share_5d is not None and oe_share_40d is not None:
                        oe_trend_pp = round((oe_share_5d - oe_share_40d) * 100, 2)
                    if len(oe_ser) >= OE_Z_MIN_OBS:
                        mu_oe = float(oe_ser.mean())
                        sd_oe = float(oe_ser.std(ddof=0))  # match ratio_z's population σ
                        oe_z = round((float(oe_ser.iloc[-1]) - mu_oe) / sd_oe, 2) if sd_oe > 0 else 0.0
                    spark20 = [round(float(v), 3) for v in oe_ser.tail(SPARK_DAYS).tolist()]

        # --- ATS per-ticker join ---
        ats_info = ats_lookup.get(str(ticker), {})
        if ats_info:
            n_with_ats += 1

        rows.append({
            "ticker": str(ticker),
            "asof": str(grp["date"].iloc[-1].date()),
            # Short ratio
            "short_ratio": round(latest_ratio, 4),
            "short_ratio_recent": round(recent_ratio, 4),
            "short_ratio_baseline": round(baseline_ratio, 4),
            "trend_pp": trend_pp,
            "ratio_z": z,
            "n_days": int(len(grp)),
            "finra_total_vol": int(grp.iloc[-1]["total_vol"]),
            # Off-exchange share (series-derived)
            "oe_share": oe_share,
            "oe_share_5d": oe_share_5d,
            "oe_share_40d": oe_share_40d,
            "oe_trend_pp": oe_trend_pp,
            "oe_z": oe_z,
            "spark20": spark20,
            # ATS
            "ats_shares": ats_info.get("ats_shares"),
            "ats_top_venue": ats_info.get("ats_top_venue"),
            "ats_venues_n": ats_info.get("ats_venues_n"),
            "ats_share_pct": ats_info.get("ats_share_pct"),
        })

    return rows, n_with_oe, n_with_ats


def _sort_ticker_stats(ticker_stats: list[dict]) -> list[dict]:
    """Sort ticker rows by off-exchange share (desc), then by short_ratio (desc)."""
    with_share    = [r for r in ticker_stats if r["oe_share"] is not None]
    without_share = [r for r in ticker_stats if r["oe_share"] is None]
    return (
        sorted(with_share, key=lambda r: r["oe_share"], reverse=True)
        + sorted(without_share, key=lambda r: r["short_ratio"], reverse=True)
    )


def _compute_ats_venue_table(
    ats_latest: pd.DataFrame | None,
    ats_prior: pd.DataFrame | None,
) -> dict:
    """Aggregate ATS data into a venue table (top 20) with wow_pp."""
    if ats_latest is None or ats_latest.empty:
        return {}

    week_start = str(ats_latest["week_start"].iloc[0].date())

    # Filter valid mpid rows
    valid = ats_latest[ats_latest["mpid"].str.len() > 0]

    latest_agg = (
        valid
        .groupby(["mpid", "venue_name"])
        .agg(
            total_shares=("shares", "sum"),
            total_trades=("trades", "sum"),
            n_symbols=("ticker", "nunique"),
        )
        .reset_index()
    )
    all_shares_latest = float(latest_agg["total_shares"].sum())
    if all_shares_latest > 0:
        latest_agg["share_of_total_pct"] = (
            latest_agg["total_shares"] / all_shares_latest * 100
        ).round(2)
    else:
        latest_agg["share_of_total_pct"] = None

    # WoW: compute prior week share_of_total_pct per mpid
    if ats_prior is not None and not ats_prior.empty:
        prior_valid = ats_prior[ats_prior["mpid"].str.len() > 0]
        prior_agg = (
            prior_valid
            .groupby("mpid")
            .agg(prior_shares=("shares", "sum"))
            .reset_index()
        )
        all_shares_prior = float(prior_agg["prior_shares"].sum())
        if all_shares_prior > 0:
            prior_agg["prior_pct"] = (
                prior_agg["prior_shares"] / all_shares_prior * 100
            ).round(2)
        else:
            prior_agg["prior_pct"] = None

        merged = latest_agg.merge(prior_agg[["mpid", "prior_pct"]], on="mpid", how="left")
        merged["wow_pp"] = (merged["share_of_total_pct"] - merged["prior_pct"]).round(2)
        # New venue this week (absent prior)
        merged["wow_is_new"] = merged["prior_pct"].isna()
    else:
        merged = latest_agg.copy()
        merged["wow_pp"] = None
        merged["wow_is_new"] = False

    merged = merged.sort_values("total_shares", ascending=False)
    venues = merged.head(20).to_dict("records")

    for v in venues:
        v["total_shares"] = int(v["total_shares"])
        v["total_trades"] = int(v["total_trades"])
        v["n_symbols"]    = int(v["n_symbols"])
        # Convert numpy scalars / NaN to Python native for JSON serialisation
        sot = v.get("share_of_total_pct")
        v["share_of_total_pct"] = round(float(sot), 2) if sot is not None and not (isinstance(sot, float) and np.isnan(sot)) else None
        wow = v.get("wow_pp")
        v["wow_pp"] = round(float(wow), 2) if wow is not None and not (isinstance(wow, float) and np.isnan(wow)) else None
        v["wow_is_new"] = bool(v.get("wow_is_new", False))

    return {
        "week_start": week_start,
        "venues": venues,
        "n_symbols_total": int(ats_latest["ticker"].nunique()),
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

    # Load ATS (latest two weeks for wow_pp)
    ats_latest, ats_prior = _load_ats_two()
    ats_week_start: pd.Timestamp | None = None
    if ats_latest is not None and not ats_latest.empty:
        ats_week_start = ats_latest["week_start"].iloc[0]
        log.info("ATS latest week: %s, prior: %s",
                 str(ats_week_start.date()) if ats_week_start is not None else "none",
                 str(ats_prior["week_start"].iloc[0].date()) if ats_prior is not None else "none")

    # Compute per-name stats (all qualifying names, no cap)
    ticker_stats, n_with_oe, n_with_ats = _compute_ticker_stats(
        panel_universe, yahoo_vol, ats_latest, ats_week_start
    )
    ticker_stats = _sort_ticker_stats(ticker_stats)

    # ATS venue table (with wow_pp)
    ats_table = _compute_ats_venue_table(ats_latest, ats_prior)

    # Data freshness
    panel_latest   = str(panel["date"].max().date())
    panel_dates    = n_dates
    below_floor    = n_dates < MIN_DATES
    ats_week_label = ats_table.get("week_start")
    ats_lag_note   = "2–4 wk publication lag" if ats_week_label else None

    # JSON payload for client-side rendering — all qualifying rows, no cap
    # Use a custom encoder that safely handles numpy types and None
    def _clean(v):
        if v is None:
            return None
        if isinstance(v, float) and np.isnan(v):
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        return v

    def _clean_row(r: dict) -> dict:
        return {k: _clean(v) if not isinstance(v, list) else [_clean(x) for x in v]
                for k, v in r.items()}

    rows_clean = [_clean_row(r) for r in ticker_stats]
    # <\/ guard: venue names are external FINRA strings — prevent </script> breakout
    table_json = json.dumps(rows_clean, separators=(",", ":")).replace("</", r"<\/")

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
        ats_table=ats_table,
        ats_lag_note=ats_lag_note,
        n_tickers_total=len(ticker_stats),
        display_universe_size=len(display_universe) or len(tickers),
        n_with_oe=n_with_oe,
        n_with_ats=n_with_ats,
        table_json=table_json,
    )
    out = site / "darkpool.html"
    write_page(out, html)
    log.info("wrote %s (%d KB, %d rows, %d dates, %d with_oe, %d with_ats)",
             out, len(html) // 1024, len(ticker_stats), panel_dates, n_with_oe, n_with_ats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
