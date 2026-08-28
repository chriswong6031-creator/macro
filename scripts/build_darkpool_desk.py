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
PANEL_PATH  = config.data_dir() / "finra_short_volume" / "panel.parquet"
# Deep pre-collector history, written ONLY by scripts/backfill_finra_short_volume.py.
#
# WHY THIS IS A SEPARATE FILE (do not merge it back into panel.parquet):
# engine/personality_flow_absorption.py (PSS-AF1, a FROZEN prospective research family —
# see research/DO_NOT_REBUILD.md) seals every panel row dated <= FINRA_PREFIX_END with a
# row count and a SHA256. That seal is tamper-evidence: it is deliberately brittle and
# cannot distinguish "rows legitimately backfilled from the authoritative source" from
# "rows edited to manufacture a result". Backfilling history straight into panel.parquet
# broke it (verified additive-only — 0 pre-existing rows missing, 0 modified, 258,198
# added — and the seal still, correctly, refused). Re-cutting a frozen family's seal is
# an operator decision, not a build-time convenience, so the desk keeps its history here
# and panel.parquet stays byte-identical to what PSS-AF1 attested.
PANEL_DEEP_PATH = config.data_dir() / "finra_short_volume" / "panel_deep.parquet"
ATS_DIR     = config.data_dir() / "finra_ats"
NONATS_DIR  = config.data_dir() / "finra_otc_nonats"
YAHOO_DIR   = config.data_dir() / "yahoo"

# Min dates in panel for the page to be useful (roadmap 30-date floor)
MIN_DATES = 30

# History windows for z-score and trend
RECENT_DAYS   = 5      # "recent" window for short ratio and oe share
BASELINE_DAYS = 40     # longer baseline for z-score
SPARK_DAYS    = 20     # sparkline history

# Minimum observations for oe_z to be meaningful
OE_Z_MIN_OBS  = 20

# Interim Terminal Dark Pool pane artifact (roadmap: Terminal Flow surface).
# EOD tier = daily FINRA-facility off-exchange share + weekly ATS venues. The
# intraday per-print fields (off-exchange %, price levels, biggest prints) stay
# null until an equity-tick feed is wired — display-tier "data pending", never
# faked. Bumps to "intraday" tier when that lands. Debranded: no data-vendor name.
# v2 (2026-08-05): per-name rows changed shape — `oe_share`/`oe_z`/`oe_trend_pp` became
# `participation`/`participation_z`/`participation_norm`, and rows gained `streak`,
# `price_change_pct`, `offex_dollars`, `ats_frac`, block sizes and venue names. A
# consumer reading v1 keys off a v2 payload would silently render blanks, so the schema
# string moves with the shape rather than leaving readers to discover it at runtime.
PANE_SCHEMA    = "darkpool_eod.v2"
PANE_JSON_NAME = "darkpool_eod.json"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_panel() -> pd.DataFrame | None:
    """The desk's view = the collector's panel UNION the deep backfill.

    Two files, one logical panel — see PANEL_DEEP_PATH for why they stay separate.
    The collector's panel wins on any overlapping (date, ticker) because it carries
    FINRA's latest restatement of a session; the deep store is only ever older history.
    A missing deep store is normal (fresh checkout) and simply yields a shorter panel.
    """
    frames: list[pd.DataFrame] = []
    for path, label in ((PANEL_DEEP_PATH, "deep"), (PANEL_PATH, "collector")):
        if not path.exists():
            if label == "collector":
                log.warning("panel not found: %s", path)
            continue
        try:
            df = pd.read_parquet(path)
        except Exception as e:  # noqa: BLE001
            log.warning("%s panel read failed: %s", label, e)
            continue
        if not df.empty:
            frames.append(df)

    if not frames:
        return None
    # keep="last" with the collector appended last ⇒ collector restatements win
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date", "ticker"], keep="last")
    return df.sort_values(["date", "ticker"])


def _load_yahoo(tickers: list[str]) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    """Load consolidated daily volume AND close for the display universe.

    Returns ({ticker: volume}, {ticker: close}); missing tickers are omitted gracefully.

    Close was NOT loaded before 2026-08-05 — the desk read only `volume`. Without price
    there is no way to pair hidden-volume intensity with what the quote actually did,
    which is the confluence that makes the read lawful (raw off-exchange share is
    forbidden as a STANDALONE direction signal — DO_NOT_REBUILD, PSS-AF1 row) and is
    also how desks actually read this data. Price coverage is thinner than volume
    coverage, so `n_with_price` is reported and rendered rather than assumed.
    """
    vol: dict[str, pd.Series] = {}
    close: dict[str, pd.Series] = {}
    for tk in tickers:
        p = YAHOO_DIR / f"{tk}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index).normalize()
            if "volume" in df.columns:
                s = df["volume"].dropna()
                if not s.empty:
                    vol[tk] = s
            if "close" in df.columns:
                c = df["close"].dropna()
                if not c.empty:
                    close[tk] = c
        except Exception:  # noqa: BLE001
            continue
    log.info("yahoo loaded: volume %d/%d, close %d/%d tickers",
             len(vol), len(tickers), len(close), len(tickers))
    return vol, close


def _load_nonats_latest(ats_week_start: pd.Timestamp | None) -> pd.DataFrame | None:
    """Load the non-ATS (wholesaler internalization) week matching the ATS week.

    Off-exchange volume is ATS + non-ATS, and non-ATS is the bigger half. Matching the
    WEEK matters: pairing an ATS week against a different non-ATS week would produce a
    meaningless ats_frac. Returns None when the matching week is absent, and every
    downstream ats_frac then stays null rather than being computed from mismatched legs.
    """
    if not NONATS_DIR.exists() or ats_week_start is None:
        return None
    p = NONATS_DIR / f"{ats_week_start.strftime('%Y%m%d')}.parquet"
    if not p.exists():
        log.info("non-ATS week %s not stored yet — venue split stays null",
                 ats_week_start.date())
        return None
    try:
        df = pd.read_parquet(p)
        return df if not df.empty else None
    except Exception as e:  # noqa: BLE001
        log.warning("non-ATS load failed %s: %s", p.name, e)
        return None


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

def _compute_ticker_stats_v2(
    panel: pd.DataFrame,
    yahoo_vol: dict[str, pd.Series],
    yahoo_close: dict[str, pd.Series],
    venue_by_ticker: dict[str, dict],
) -> tuple[list[dict], dict]:
    """Per-name metrics via engine.darkpool_signals + a coverage report.

    SEMANTICS: participation = FINRA-facility off-exchange volume ÷ consolidated volume
    (yahoo). The denominator is labeled explicitly in the page copy.

    Every metric that lacks its input stays None — nulls are printed on the page, never
    imputed. Returns (rows, coverage).
    """
    from engine.darkpool_signals import compute_name_metrics
    from dataclasses import asdict

    rows: list[dict] = []
    cov = {"n_total": 0, "n_with_participation": 0, "n_with_price": 0,
           "n_with_z": 0, "n_with_venue": 0, "n_no_price": 0}

    for ticker, grp in panel.groupby("ticker"):
        tk = str(ticker)
        grp = grp.sort_values("date")
        if len(grp) < 3:
            continue
        cov["n_total"] += 1

        m = compute_name_metrics(
            tk, grp,
            yahoo_vol.get(tk),
            yahoo_close.get(tk),
            venue_by_ticker.get(tk),
        )
        d = asdict(m)
        d["asof"] = str(grp["date"].iloc[-1].date())
        d["finra_total_vol"] = int(grp.iloc[-1]["total_vol"])
        d["n_days"] = int(len(grp))
        # flatten the spark out of extras for the client table
        d["spark20"] = (m.extras or {}).get("spark", [])
        d.pop("extras", None)

        if m.participation is not None:
            cov["n_with_participation"] += 1
        if m.price_change_pct is not None:
            cov["n_with_price"] += 1
        else:
            cov["n_no_price"] += 1
        if m.participation_z is not None:
            cov["n_with_z"] += 1
        if m.ats_frac is not None:
            cov["n_with_venue"] += 1
        rows.append(d)

    return rows, cov


def _partition_session_rows(
    rows: list[dict], *, panel_latest: str, tracked_universe: int
) -> tuple[list[dict], list[dict], dict]:
    """Split comparable current observations from last-known historical rows.

    A ticker's own newest row remains useful in Browse All, but only a row whose
    clock equals the authoritative desk session may enter the current gauge,
    standout board, ranking or machine context.  No forward fill is performed.
    """
    current: list[dict] = []
    stale: list[dict] = []
    for raw in rows:
        row = dict(raw)
        if str(row.get("asof") or "") == panel_latest:
            row["session_status"] = "current"
            current.append(row)
        else:
            row["session_status"] = "stale"
            stale.append(row)

    tracked = max(int(tracked_universe), len(current) + len(stale))
    missing = max(0, tracked - len(current) - len(stale))
    census = {
        "tracked_universe": tracked,
        "current_session_rows": len(current),
        "stale_rows": len(stale),
        "missing_rows": missing,
        "current_session_pct": round(100.0 * len(current) / tracked, 1) if tracked else 0.0,
    }
    return current, stale, census


def _compute_ticker_stats(
    panel: pd.DataFrame,
    yahoo_vol: dict[str, pd.Series],
    ats_latest: pd.DataFrame | None,
    ats_week_start: pd.Timestamp | None,
) -> tuple[list[dict], int, int]:
    """LEGACY v1 per-name computation — retained only for the ATS per-ticker join path
    exercised by tests/test_darkpool_desk.py. The live build uses
    _compute_ticker_stats_v2 + engine.darkpool_signals.

    SEMANTICS: off_ex_share = FINRA-facility total_vol / yahoo consolidated volume.

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
    """Rank by UNUSUALNESS vs each name's own norm — not by the raw level.

    Sorting by raw off-exchange share (what this did before 2026-08-05) put the same
    structurally-dark names at the top every session: a variance decomposition over the
    panel attributed 42.7% of participation variance to a fixed per-name effect, with
    45% day-over-day overlap in the top 20 and rank autocorrelation of 0.58 at lag 1.
    Retail-heavy and thin names simply always print more off-exchange. Ranking on the
    deviation from each name's OWN norm puts what changed at the front instead.

    Names without enough history for a z (honest null) sort last on participation, so
    they are still browsable but never occupy the board.
    """
    from engine.darkpool_signals import unusualness  # local: keeps import cost off the stub path

    rated   = [r for r in ticker_stats if r.get("participation_z") is not None]
    unrated = [r for r in ticker_stats if r.get("participation_z") is None]
    return (
        sorted(rated, key=lambda r: -unusualness(_as_metrics(r)))
        + sorted(unrated, key=lambda r: (r.get("participation") is None, -(r.get("participation") or 0)))
    )


def _as_metrics(row: dict):
    """Adapt a plain desk row back to the NameMetrics shape `unusualness` expects."""
    from engine.darkpool_signals import NameMetrics
    return NameMetrics(
        ticker=row.get("ticker", ""),
        participation=row.get("participation"),
        participation_z=row.get("participation_z"),
        streak=row.get("streak") or 0,
        offex_dollars=row.get("offex_dollars"),
        short_rate_z=row.get("short_rate_z"),
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


def _emit_pane_json(
    rows_clean: list[dict],
    ats_table: dict,
    *,
    panel_latest: str,
    panel_dates: int,
    below_floor: bool,
    n_with_oe: int,
    n_with_ats: int,
    ats_lag_note: str | None,
    built: str,
    gauge: dict | None = None,
    coverage: dict | None = None,
    historical_rows: list[dict] | None = None,
    out_path: Path | None = None,
) -> Path:
    """Write the interim Terminal Dark Pool pane artifact → site/darkpool_eod.json.

    Reuses the already-numpy-cleaned per-ticker rows (same payload the HTML desk
    embeds), so any Terminal Flow pane can consume it via a plain fetch instead
    of scraping the page. Additive + guarded: the caller wraps this in try/except
    so a failure here can NEVER break the HTML desk.

    Tier is EOD — daily FINRA-facility off-exchange share + weekly per-ATS venues.
    The intraday tick-feed fields (per-print off-exchange %, price levels, biggest
    prints) are emitted as explicit nulls under `pending`; they are never faked.
    `source` is debranded (no data-vendor name — house law).
    """
    payload = {
        "schema": PANE_SCHEMA,
        "tier": "eod",                         # -> "intraday" once an equity-tick feed lands
        "source": "finra_facilities",          # debranded — no data-vendor name
        "asof": panel_latest,                  # daily off-exchange data date
        "panel_dates": panel_dates,
        "below_floor": below_floor,
        "n_with_oe": n_with_oe,
        "n_with_ats": n_with_ats,
        "gauge": gauge or {},                  # dollar-weighted market-wide participation
        "coverage": coverage or {},            # which inputs were actually available
        # Machine-facing current cross-section: every row has the same clock as
        # top-level ``asof``.  Last-known older observations are kept separately
        # for explicit historical browsing and never enter current authority.
        "universe": rows_clean,
        "historical_rows": historical_rows or [],
        "venues": {                            # weekly ATS venue rollup + WoW
            "week_start": ats_table.get("week_start"),
            "lag_note": ats_lag_note,
            "lag_days": ats_table.get("lag_days"),
            "n_symbols_total": ats_table.get("n_symbols_total"),
            "rows": ats_table.get("venues", []),
        },
        "pending": {                           # intraday tick-feed fields — explicit null, never faked
            "intraday_oe_share": None,
            "price_levels": None,
            "biggest_prints": None,            # INDIVIDUAL prints still need ticks; the
                                               # per-venue AVERAGE print size now ships in
                                               # universe[].ats_block_shares (weekly, EOD).
            "note": "intraday per-print off-exchange data pending equity-tick feed",
        },
        "built": built,
    }
    out = out_path or (config.ROOT / "site" / PANE_JSON_NAME)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info("wrote %s (%d names, tier=eod, %d with_oe)", out, len(rows_clean), n_with_oe)
    return out


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
        log.error("panel missing — no current Dark Pool publication authority; prior artifacts retained")
        print("::error title=Dark Pool source unavailable::canonical FINRA panel is missing or unreadable; prior artifacts retained", flush=True)
        return 1

    n_dates = panel["date"].nunique()
    panel_latest = str(panel["date"].max().date())
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

    # Load yahoo volume + close (close drives the price confluence — see _load_yahoo)
    yahoo_vol, yahoo_close = _load_yahoo(tickers)

    # Load ATS (latest two weeks for wow_pp) + the MATCHING non-ATS week
    ats_latest, ats_prior = _load_ats_two()
    ats_week_start: pd.Timestamp | None = None
    if ats_latest is not None and not ats_latest.empty:
        ats_week_start = ats_latest["week_start"].iloc[0]
        log.info("ATS latest week: %s, prior: %s",
                 str(ats_week_start.date()) if ats_week_start is not None else "none",
                 str(ats_prior["week_start"].iloc[0].date()) if ats_prior is not None else "none")
    nonats_latest = _load_nonats_latest(ats_week_start)

    # Venue split: institutional dark pools vs wholesaler internalization
    from engine.darkpool_signals import venue_split, market_gauge, NameMetrics
    venue_by_ticker = venue_split(ats_latest, nonats_latest)
    log.info("venue split: %d tickers (non-ATS week %s)",
             len(venue_by_ticker), "present" if nonats_latest is not None else "MISSING")

    # Compute per-name stats (all qualifying names, no cap)
    ticker_stats, coverage = _compute_ticker_stats_v2(
        panel_universe, yahoo_vol, yahoo_close, venue_by_ticker
    )
    ticker_stats = _sort_ticker_stats(ticker_stats)

    current_stats, stale_stats, session_census = _partition_session_rows(
        ticker_stats,
        panel_latest=panel_latest,
        tracked_universe=len(display_universe) or len(tickers),
    )
    coverage.update(session_census)

    gauge = market_gauge([
        NameMetrics(ticker=r["ticker"], participation=r.get("participation"),
                    participation_z=r.get("participation_z"),
                    offex_dollars=r.get("offex_dollars"))
        for r in current_stats
    ])

    n_with_oe = sum(r.get("participation") is not None for r in current_stats)
    n_with_ats = sum(r.get("ats_frac") is not None for r in current_stats)

    # ATS venue table (with wow_pp)
    ats_table = _compute_ats_venue_table(ats_latest, ats_prior)

    # Data freshness
    panel_dates    = n_dates
    below_floor    = n_dates < MIN_DATES
    ats_week_label = ats_table.get("week_start")

    # Publication lag is COMPUTED, never asserted. The hardcoded "2–4 wk" chip
    # understated reality: on 2026-08-05 the newest stored week was 2026-06-22, i.e.
    # 44 days (6.3 weeks) old. A lag chip that is itself stale is worse than none.
    ats_lag_days = None
    ats_lag_note = None
    if ats_week_label:
        ats_lag_days = int((pd.Timestamp(panel_latest) - pd.Timestamp(ats_week_label)).days)
        ats_lag_note = f"{ats_lag_days // 7} wk publication lag" if ats_lag_days >= 7 \
            else f"{ats_lag_days} d publication lag"
    ats_table["lag_days"] = ats_lag_days
    ats_table["lag_note"] = ats_lag_note

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

    current_clean = [_clean_row(r) for r in current_stats]
    stale_clean = [_clean_row(r) for r in stale_stats]
    rows_clean = current_clean + stale_clean
    # <\/ guard: venue names are external FINRA strings — prevent </script> breakout
    table_json = json.dumps(rows_clean, separators=(",", ":")).replace("</", r"<\/")

    # Render
    site = config.ROOT / "site"
    site.mkdir(parents=True, exist_ok=True)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Actionable positioning context + same-day change-feed (darkpool_context.v1).
    # Turns the raw desk into plain-word accumulation/distribution/unusual leans, a
    # laid-out standout board, and a hero verdict — and persists the artifact the
    # Neural Web dark-pool lobe reads. Additive + guarded: NEVER breaks the HTML desk.
    dp_ctx: dict | None = None
    try:
        from engine import darkpool_context as _dpc
        dp_ctx = _dpc.build_context_feed(
            current_clean,
            {"week_start": ats_table.get("week_start"),
             "venues": ats_table.get("venues", []),
             "lag_note": ats_lag_note,
             "lag_days": ats_lag_days},
            asof=panel_latest, built=built, root=config.ROOT,
            gauge=gauge, coverage=coverage,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("darkpool_context build failed (non-fatal): %s", e)

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
        ats_lag_days=ats_lag_days,
        n_tickers_total=len(ticker_stats),
        display_universe_size=len(display_universe) or len(tickers),
        n_with_oe=n_with_oe,
        n_with_ats=n_with_ats,
        coverage=coverage,
        gauge=gauge,
        table_json=table_json,
        dp=dp_ctx,
    )
    out = site / "darkpool.html"
    write_page(out, html)
    log.info("wrote %s (%d KB, %d rows, %d dates, %d with_oe, %d with_ats)",
             out, len(html) // 1024, len(ticker_stats), panel_dates, n_with_oe, n_with_ats)

    # Interim Terminal Dark Pool pane artifact (EOD tier). Additive + guarded:
    # never blocks the desk. Upgrades to intraday per-print once a tick feed lands.
    try:
        _emit_pane_json(
            current_clean, ats_table,
            panel_latest=panel_latest, panel_dates=panel_dates, below_floor=below_floor,
            n_with_oe=n_with_oe, n_with_ats=n_with_ats, ats_lag_note=ats_lag_note, built=built,
            gauge=gauge, coverage=coverage, historical_rows=stale_clean,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("pane json emit failed (non-fatal): %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
