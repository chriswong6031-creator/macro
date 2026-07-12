"""scripts/build_leader_radar.py — Leader Radar nightly builder (LR W2a).

Program: Leader Radar (research/LEADER_RADAR_MASTERPLAN_BY_FABLE.md)
Rulings: LR-R1 through LR-R15.

Universe (LR-R12):
  mag7 ∪ ai_infra ∪ ai_semiconductors ∪ semicap_equipment ∪ memory_storage
  ∪ data_center_power ∪ ai_software ∪ ai_neoclouds (data/baskets/membership.json)
  ∪ Dow-30 (config pinned) ∪ NDX (data/baskets_nasdaq/membership.json)
  ∩ has-ohlcv (data/baskets/ohlcv/), ETFs excluded.

Stores written (COLLECT_LANE=nightly gate on all data/ writes):
  data/rs_series/<T>.parquet                    — full-history RS ratio on first run; nightly append
  data/leader_radar/state_history.parquet       — (date, ticker, raw_state, confirmed_state)
  data/leader_radar/revisions_history.parquet   — dedup append of revisions/latest.parquet
  data/leader_radar/fire_log.parquet            — (date, ticker, book, fire_type) fire events

Analyst buy-share feed (LR-R2 CROWDED chip e, `analyst_saturated`):
  data/finnhub/recommendation.parquet (collectors/finnhub_altdata.py; monthly
  strongBuy/buy/hold/sell/strongSell counts, ~120-name basket watchlist) read via
  engine/analyst_revisions.revision_map — consensus_pct = (strongBuy+buy)/total×100
  is the buy-share LEVEL the chip compares to CROWDED_ANALYST_BUY_PCT.
  The synapse `analyst-targets` store (yfinance .info) was evaluated 2026-07-12 and
  REJECTED for this chip: it carries only the consensus recommendationKey string +
  num_analysts — no rating-category counts, so no buy-share is derivable from it.
  Null-honest: store absent / ticker uncovered / latest period older than
  _ANALYST_MAX_AGE_DAYS → analyst_buy_pct=None → chip null (never False).
  Store born 2026-06-20 → young-data tag per LR-R14 (coverage.analyst_note + page banner).

Output artifact:
  site/leaderradar/radar.json         — schema leader_radar.v1

Kill-switch: config leader_radar.enabled: false → noindex stub, skip JSON.
Stale SLA: prices lagging NYSE calendar >2 sessions → stale banner, no state advance.
Always exits 0 — fail-soft per-ticker; non-fatal store errors logged and skipped.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config

log = logging.getLogger(__name__)

# ── ETF exclusion set ─────────────────────────────────────────────────────────
_ETF_SET = frozenset({
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLI", "XLU", "XLV", "XLY", "XLP", "XLB", "XLC", "XLRE",
    "SMH", "SOXX", "KRE", "XBI", "ARKK",
    "GLD", "SLV", "TLT", "HYG", "LQD",
})

# ── Dow-30 pinned list (config fallback; checked against data/baskets/ first) ─
# Source: Dow Jones Industrial Average composition as of 2026-07-11
# Pinned per LR-R12: if no dedicated store provides this, use this config block.
_DOW30_PINNED: list[str] = [
    "AAPL", "AMGN", "AMZN", "AXP", "BA",
    "CAT", "CRM", "CSCO", "CVX", "DIS",
    "GS", "HD", "HON", "IBM", "INTC",
    "JNJ", "JPM", "KO", "MCD", "MMM",
    "MRK", "MSFT", "NKE", "NVDA", "PG",
    "SHW", "TRV", "UNH", "V", "VZ",
]


# ── JSON serialiser (mirror of flow_leaders) ──────────────────────────────────

def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if not np.isfinite(float(obj)) else float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is pd.NA or (hasattr(pd, "NaT") and obj is pd.NaT):
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Kill-switch stub ──────────────────────────────────────────────────────────

def _write_noindex_stub(site_root: Path) -> None:
    stub = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>Leader Radar (disabled)</title></head>'
        '<body><p>Leader Radar is currently disabled.</p></body></html>'
    )
    out_dir = site_root / "leaderradar"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "radar.json").write_text(
        json.dumps({"schema": "leader_radar.v1", "enabled": False, "stale": True})
    )
    log.info("build_leader_radar: kill-switch active — wrote noindex stub")


# ── Universe resolution (LR-R12) ─────────────────────────────────────────────

def _tickers_from_basket(basket: dict) -> list[str]:
    """Extract current (not removed) tickers from a basket dict."""
    members = basket.get("members", [])
    tickers: list[str] = []
    for m in members:
        if isinstance(m, dict):
            ticker = m.get("ticker")
            removed = m.get("removed")
            if ticker and not removed:
                tickers.append(ticker)
        elif isinstance(m, str):
            tickers.append(m)
    return tickers


def _resolve_universe(data_root: Path, cfg: dict) -> tuple[list[str], dict[str, list[str]]]:
    """Resolve the LR-R12 universe.

    Returns (sorted_tickers, basket_membership_map).
    basket_membership_map: {basket_name: [ticker, ...]} for handoff watch.
    """
    lr_cfg = cfg.get("leader_radar") or {}
    basket_keys = lr_cfg.get("basket_keys") or [
        "mag7", "ai_infra", "ai_semiconductors", "semicap_equipment",
        "memory_storage", "data_center_power", "ai_software", "ai_neoclouds",
    ]

    # Load data/baskets/membership.json
    membership_path = data_root / "baskets" / "membership.json"
    basket_membership: dict[str, list[str]] = {}
    all_tickers: set[str] = set()

    if membership_path.exists():
        try:
            m = json.loads(membership_path.read_text())
            baskets = m.get("baskets") or {}
            for key in basket_keys:
                bkt = baskets.get(key) or {}
                tickers = _tickers_from_basket(bkt)
                basket_membership[key] = tickers
                all_tickers.update(tickers)
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: baskets/membership.json unreadable: %s", e)

    # Dow-30: check config override, else use pinned list
    dow30_tickers = lr_cfg.get("dow30") or _DOW30_PINNED
    basket_membership["dow30"] = list(dow30_tickers)
    all_tickers.update(dow30_tickers)

    # NDX: from data/baskets_nasdaq/membership.json (amalgamations + subsectors union)
    nasdaq_path = data_root / "baskets_nasdaq" / "membership.json"
    ndx_tickers: list[str] = []
    if nasdaq_path.exists():
        try:
            nm = json.loads(nasdaq_path.read_text())
            ndq_union: set[str] = set()
            for section in ("amalgamations", "subsectors"):
                section_data = nm.get(section) or {}
                for group_val in section_data.values():
                    # Each group is a dict with 'members' list
                    if isinstance(group_val, dict):
                        for member in (group_val.get("members") or []):
                            if isinstance(member, dict):
                                t = member.get("ticker")
                                if t:
                                    ndq_union.add(t)
                            elif isinstance(member, str):
                                ndq_union.add(member)
                    elif isinstance(group_val, list):
                        for m in group_val:
                            if isinstance(m, dict):
                                t = m.get("ticker")
                                if t:
                                    ndq_union.add(t)
                            elif isinstance(m, str):
                                ndq_union.add(m)
            ndx_tickers = sorted(ndq_union)
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: baskets_nasdaq/membership.json unreadable: %s", e)
    basket_membership["ndx"] = ndx_tickers
    all_tickers.update(ndx_tickers)

    # Filter: has ohlcv AND not ETF
    ohlcv_dir = data_root / "baskets" / "ohlcv"
    universe: list[str] = []
    for ticker in sorted(all_tickers):
        if ticker in _ETF_SET:
            continue
        ohlcv_path = ohlcv_dir / f"{ticker}.parquet"
        if ohlcv_path.exists():
            universe.append(ticker)

    log.info(
        "build_leader_radar: universe %d names (from %d candidates; %d baskets)",
        len(universe), len(all_tickers), len(basket_membership),
    )
    return universe, basket_membership


# ── Price store loaders ───────────────────────────────────────────────────────

def _load_ohlcv(ticker: str, data_root: Path) -> pd.DataFrame | None:
    """Load OHLCV parquet for a ticker from data/baskets/ohlcv/."""
    p = data_root / "baskets" / "ohlcv" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p).sort_index()
        if df.empty or "close" not in df.columns:
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("build_leader_radar: ohlcv/%s unreadable: %s", ticker, e)
        return None


def _load_spy(data_root: Path) -> pd.Series | None:
    """Load SPY close from data/yahoo/SPY.parquet."""
    p = data_root / "yahoo" / "SPY.parquet"
    if not p.exists():
        log.warning("build_leader_radar: data/yahoo/SPY.parquet absent")
        return None
    try:
        df = pd.read_parquet(p).sort_index()
        df.index = pd.to_datetime(df.index)
        col = "close" if "close" in df.columns else "close_price"
        if col not in df.columns:
            log.warning("build_leader_radar: SPY parquet has no close column: %s", df.columns.tolist())
            return None
        return df[col].dropna().sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: SPY.parquet unreadable: %s", e)
        return None


def _load_sector_etf_close(etf: str, data_root: Path) -> pd.Series | None:
    """Load sector-ETF close from data/baskets/ohlcv/<ETF>.parquet or data/yahoo/<ETF>.parquet."""
    for path in [
        data_root / "baskets" / "ohlcv" / f"{etf}.parquet",
        data_root / "yahoo" / f"{etf}.parquet",
    ]:
        if path.exists():
            try:
                df = pd.read_parquet(path).sort_index()
                df.index = pd.to_datetime(df.index)
                col = "close" if "close" in df.columns else "close_price"
                if col in df.columns:
                    return df[col].dropna().sort_index()
            except Exception:  # noqa: BLE001
                continue
    return None


# ── Stale SLA ─────────────────────────────────────────────────────────────────

def _check_stale(latest_date: date | None) -> bool:
    """Return True when price store lags NYSE calendar by >2 sessions."""
    if latest_date is None:
        return True
    try:
        from lib.nyse_calendar import trading_dates_between
        today = date.today()
        recent = trading_dates_between(
            date(today.year - 1, today.month, today.day),
            today,
        )
        after = [d for d in recent if d > latest_date and d <= today]
        return len(after) > 2
    except Exception as e:  # noqa: BLE001
        log.debug("build_leader_radar: stale check failed: %s", e)
        return False


# ── RS-series store (LR-R3) ──────────────────────────────────────────────────

def _rs_series_path(ticker: str, data_root: Path) -> Path:
    return data_root / "rs_series" / f"{ticker}.parquet"


def _load_rs_series(ticker: str, data_root: Path) -> pd.Series:
    """Load the stored RS series or return empty."""
    p = _rs_series_path(ticker, data_root)
    if not p.exists():
        return pd.Series(dtype=float)
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        if "rs" in df.columns:
            return df["rs"].sort_index().dropna()
        return pd.Series(dtype=float)
    except Exception as e:  # noqa: BLE001
        log.debug("build_leader_radar: rs_series/%s unreadable: %s", ticker, e)
        return pd.Series(dtype=float)


def _write_rs_series(
    ticker: str,
    rs: pd.Series,
    data_root: Path,
) -> None:
    """Write the RS series to data/rs_series/<T>.parquet."""
    rs_dir = data_root / "rs_series"
    rs_dir.mkdir(parents=True, exist_ok=True)
    p = rs_dir / f"{ticker}.parquet"
    df = pd.DataFrame({"rs": rs})
    df.to_parquet(p, index=True)


def _build_rs_series(
    ticker: str,
    ohlcv: pd.DataFrame,
    spy: pd.Series,
    existing: pd.Series,
    data_root: Path,
) -> pd.Series:
    """Build/append the RS series for a ticker.

    First run: full-history backfill (all available close / SPY).
    Subsequent: append new dates only.
    Returns the current full RS series.
    """
    from engine.leader_lifecycle import rs_series as _rs_series_fn

    close = ohlcv["close"].dropna().sort_index()
    close.index = pd.to_datetime(close.index)

    # Compute full RS series from all available data
    full_rs = _rs_series_fn(close, spy)
    if full_rs.empty:
        return existing

    if existing.empty:
        # First run: full-history backfill
        _write_rs_series(ticker, full_rs, data_root)
        return full_rs
    else:
        # Append-only: find dates not yet in existing
        new_dates = full_rs.index.difference(existing.index)
        if new_dates.empty:
            return existing
        combined = pd.concat([existing, full_rs.reindex(new_dates)]).sort_index().dropna()
        _write_rs_series(ticker, combined, data_root)
        return combined


# ── State history store ───────────────────────────────────────────────────────

_STATE_HISTORY_PATH = "leader_radar/state_history.parquet"


def _load_state_history(data_root: Path) -> pd.DataFrame:
    """Load data/leader_radar/state_history.parquet.

    Columns: date (index), ticker, raw_state, confirmed_state.
    Returns empty DataFrame with correct schema on miss.
    """
    p = data_root / _STATE_HISTORY_PATH
    if not p.exists():
        return pd.DataFrame(columns=["date", "ticker", "raw_state", "confirmed_state"])
    try:
        df = pd.read_parquet(p)
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: state_history.parquet unreadable: %s", e)
        return pd.DataFrame(columns=["date", "ticker", "raw_state", "confirmed_state"])


def _write_state_history(df: pd.DataFrame, data_root: Path) -> None:
    p = data_root / _STATE_HISTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def _ticker_state_history(
    ticker: str,
    state_df: pd.DataFrame,
) -> tuple[list[tuple[date, str]], list[tuple[date, str]]]:
    """Return (raw_history, confirmed_history) for a ticker from state_df.

    Each is a list of (date, state) tuples, newest last.
    """
    if state_df.empty or "ticker" not in state_df.columns:
        return [], []
    sub = state_df[state_df["ticker"] == ticker].copy()
    if sub.empty:
        return [], []
    # Ensure date column is datetime
    if "date" in sub.columns:
        sub["date"] = pd.to_datetime(sub["date"])
        sub = sub.sort_values("date")
        raw = [(row["date"].date(), str(row["raw_state"])) for _, row in sub.iterrows()]
        conf = [(row["date"].date(), str(row["confirmed_state"])) for _, row in sub.iterrows()]
    else:
        raw, conf = [], []
    return raw, conf


# ── Nightly lane gate (HOUSE-U5) ─────────────────────────────────────────────

def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly lane.

    Mirrors build_intraday_flow._ledger_advance_enabled — gate: COLLECT_LANE=nightly
    (or US_LANE=nightly for the US shard variant).
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


# ── Revisions history store ───────────────────────────────────────────────────

_REVISIONS_HISTORY_PATH = "leader_radar/revisions_history.parquet"


def _append_revisions_history(data_root: Path) -> None:
    """Append today's data/revisions/latest.parquet rows to revisions_history.

    Dedup on (asof, ticker). Non-fatal: logs and returns on any error.
    """
    src = data_root / "revisions" / "latest.parquet"
    if not src.exists():
        log.debug("build_leader_radar: revisions/latest.parquet absent — skipping history append")
        return
    try:
        new_df = pd.read_parquet(src).reset_index()
        # Ensure ticker column exists (index may be ticker)
        if "ticker" not in new_df.columns:
            # The index is the ticker
            new_df = pd.read_parquet(src)
            new_df.index.name = "ticker"
            new_df = new_df.reset_index()

        hist_path = data_root / _REVISIONS_HISTORY_PATH
        hist_path.parent.mkdir(parents=True, exist_ok=True)

        if hist_path.exists():
            hist_df = pd.read_parquet(hist_path)
            # Dedup key: (asof, ticker)
            if "asof" in new_df.columns and "ticker" in new_df.columns:
                combined = pd.concat([hist_df, new_df], ignore_index=True)
                combined = combined.drop_duplicates(subset=["asof", "ticker"], keep="last")
                combined.to_parquet(hist_path, index=False)
                log.info(
                    "build_leader_radar: revisions_history: %d rows (+%d new)",
                    len(combined), len(new_df),
                )
        else:
            new_df.to_parquet(hist_path, index=False)
            log.info("build_leader_radar: revisions_history: initialized with %d rows", len(new_df))
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: revisions_history append failed: %s", e)


# ── Fire log store ────────────────────────────────────────────────────────────

_FIRE_LOG_PATH = "leader_radar/fire_log.parquet"
# Columns: date (date), ticker (str), fire_type ('precipice'|'onset')


def _load_fire_log(data_root: Path) -> pd.DataFrame:
    """Load data/leader_radar/fire_log.parquet.

    Returns empty DataFrame with (date, ticker, fire_type) schema on miss.
    """
    p = data_root / _FIRE_LOG_PATH
    if not p.exists():
        return pd.DataFrame(columns=["date", "ticker", "fire_type"])
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: fire_log.parquet unreadable: %s", e)
        return pd.DataFrame(columns=["date", "ticker", "fire_type"])


def _write_fire_log(df: pd.DataFrame, data_root: Path) -> None:
    p = data_root / _FIRE_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def _last_fire_dates(fire_log: pd.DataFrame) -> dict[str, date | None]:
    """Return {ticker: last_fire_date} from the fire log (any fire type)."""
    if fire_log.empty or "ticker" not in fire_log.columns:
        return {}
    result: dict[str, date | None] = {}
    for ticker, grp in fire_log.groupby("ticker"):
        dates = grp["date"].dropna()
        if len(dates) == 0:
            continue
        last = max(dates)
        result[str(ticker)] = last.date() if isinstance(last, pd.Timestamp) else last
    return result


# ── Stockdata context loader ──────────────────────────────────────────────────

def _load_stockdata(ticker: str, site_root: Path) -> dict:
    p = site_root / "stockdata" / f"{ticker}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("build_leader_radar: stockdata/%s unreadable: %s", ticker, e)
        return {}


def _extract_revisions(sd: dict) -> dict:
    """Extract revisions fields from stockdata JSON."""
    rev = sd.get("revisions") or {}
    return {
        "net_up_30d": rev.get("net_up_30d"),
        "est_chg_30d": rev.get("est_chg_30d"),
        "breadth": rev.get("breadth"),
    }


def _extract_valuation(sd: dict) -> dict:
    val = sd.get("valuation") or {}
    tech = sd.get("tech") or {}
    return {
        "cheap_pctile": val.get("cheap_pctile"),
        "fwd_pe": val.get("fwd_pe") or val.get("forward_pe"),
        "sector_median_fwd_pe": val.get("sector_median_fwd_pe"),
        "valuation_pctile_5y": val.get("pctile_5y") or val.get("valuation_pctile_5y"),
    }


def _extract_earnings(sd: dict) -> dict:
    earnings = sd.get("earnings") or {}
    next_date = earnings.get("next_date")
    dte = None
    if next_date:
        try:
            nd = pd.Timestamp(next_date).date()
            dte = (nd - date.today()).days
        except Exception:  # noqa: BLE001
            pass
    return {"days_to_earnings": dte}


def _extract_personality(sd: dict) -> dict:
    """Extract personality labels."""
    base = sd.get("base") or sd
    cp = base.get("chart_personality") or {}
    labels = cp.get("labels") or []
    return {"labels": labels}


def _extract_mktcap(sd: dict) -> float | None:
    profile = sd.get("profile") or {}
    cap = profile.get("mktcap_bn") or profile.get("market_cap_bn")
    if cap is not None:
        try:
            f = float(cap)
            return f if np.isfinite(f) else None
        except (TypeError, ValueError):
            pass
    return None


# ── Analyst buy-share (LR-R2 CROWDED chip e) ──────────────────────────────────

# Latest finnhub recommendation-trends period must be within this window;
# periods are monthly, so 45d = current or previous month. Older → null-honest drop.
_ANALYST_MAX_AGE_DAYS = 45


def _load_analyst_buy_share(data_root: Path, today: date) -> dict[str, dict]:
    """Per-ticker analyst buy-share map from finnhub recommendation-trends.

    Reads data/finnhub/recommendation.parquet through
    engine/analyst_revisions.revision_map (LR-R13: consume, never re-implement);
    consensus_pct = (strongBuy+buy)/total×100 is the LEVEL the analyst_saturated
    chip compares to CROWDED_ANALYST_BUY_PCT. Returns {} when the store is
    absent/unreadable; tickers whose latest period is older than
    _ANALYST_MAX_AGE_DAYS are dropped (stale rating counts must not fire a
    crowding chip). Values: {consensus_pct, n_analysts, n_periods, latest_period}.
    """
    p = data_root / "finnhub" / "recommendation.parquet"
    if not p.exists():
        log.info("build_leader_radar: finnhub/recommendation.parquet absent — analyst chip null")
        return {}
    try:
        recs = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: finnhub/recommendation.parquet unreadable: %s", e)
        return {}
    try:
        from engine.analyst_revisions import revision_map
        full = revision_map(recs)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: revision_map failed: %s", e)
        return {}

    out: dict[str, dict] = {}
    for ticker, row in full.items():
        pct = row.get("consensus_pct")
        if pct is None:
            continue
        try:
            period_age = (today - pd.Timestamp(row.get("latest_period")).date()).days
        except Exception:  # noqa: BLE001
            continue
        if period_age > _ANALYST_MAX_AGE_DAYS:
            log.debug(
                "build_leader_radar: %s analyst period %s stale (%dd) — dropped",
                ticker, row.get("latest_period"), period_age,
            )
            continue
        out[ticker] = {
            "consensus_pct": float(pct),
            "n_analysts": row.get("n_analysts"),
            "n_periods": row.get("n_periods"),
            "latest_period": row.get("latest_period"),
        }
    return out


# ── Regime inputs ─────────────────────────────────────────────────────────────

def _load_regime_inputs(data_root: Path) -> dict:
    """Load dispersion/regime.json fields for leadership_regime."""
    p = data_root / "dispersion" / "regime.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: dispersion/regime.json unreadable: %s", e)
        return {}


# ── Insider cluster loader (LRV-R1b) ──────────────────────────────────────────
# Note (LRV-R1b): LR-R2 spec called for 90d open-market buys; the available
# data is quarterly SEC aggregate (data/sec_insider/insider.parquet, index=ticker,
# columns: n_buys, n_sells, buy_usd, sell_usd, net_usd, quarter).
# Quarterly grain is honest — per-transaction Form-4 PIT panel is in a separate
# research path (sec_insider.py); this store is the available nightly-lane source.

def _load_insider_cluster(
    data_root: Path,
    as_of: date,
    stale_days: int = 120,
) -> dict[str, bool | None]:
    """Build {ticker: bool|None} insider_cluster map from data/sec_insider/insider.parquet.

    True  : latest quarter-end within stale_days of as_of AND n_buys >= 2
    False : quarter present but n_buys < 2
    None  : ticker absent OR quarter-end older than stale_days

    Args:
        data_root: repo data root
        as_of: the date to compute staleness against (typically today)
        stale_days: max calendar days from quarter-end to as_of (default 120)
    """
    p = data_root / "sec_insider" / "insider.parquet"
    if not p.exists():
        log.debug("build_leader_radar: data/sec_insider/insider.parquet absent")
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: insider.parquet unreadable: %s", e)
        return {}

    def _quarter_end(q_str: str) -> date | None:
        """Convert '2026q1' -> 2026-03-31, '2026q2' -> 2026-06-30, etc."""
        try:
            year = int(str(q_str)[:4])
            q = int(str(q_str)[5])
            month_end = q * 3
            day = 31 if month_end in (3, 12) else 30
            return date(year, month_end, day)
        except Exception:  # noqa: BLE001
            return None

    # Grain defense: sort by quarter so latest quarter sorts last, then keep only
    # the last row per ticker.  Prevents silent last-win on duplicate-ticker stores.
    if "quarter" in df.columns:
        df = df.sort_values("quarter", na_position="first")
    df = df.groupby(level=0).tail(1)

    result: dict[str, bool | None] = {}
    for ticker, row in df.iterrows():
        try:
            q_str = row.get("quarter") if hasattr(row, "get") else getattr(row, "quarter", None)
            if q_str is None or (isinstance(q_str, float) and pd.isna(q_str)):
                result[str(ticker)] = None
                continue
            qend = _quarter_end(str(q_str))
            if qend is None:
                result[str(ticker)] = None
                continue
            if (as_of - qend).days > stale_days:
                result[str(ticker)] = None
                continue
            n_buys_raw = row.get("n_buys") if hasattr(row, "get") else getattr(row, "n_buys", None)
            if n_buys_raw is None or (isinstance(n_buys_raw, float) and pd.isna(n_buys_raw)):
                result[str(ticker)] = None
                continue
            result[str(ticker)] = bool(int(n_buys_raw) >= 2)
        except Exception as e:  # noqa: BLE001
            log.debug("build_leader_radar: insider_cluster/%s failed: %s", ticker, e)
            result[str(ticker)] = None
    return result


# ── Options skew loader (LRV-R1c) ─────────────────────────────────────────────
# Sign convention: skew column = otm_put_iv - atm_call_iv (negative = puts cheaper than calls).
# rr proxy = atm_call_iv - otm_put_iv = -skew. Positive rr means calls MORE expensive
# than puts (call-skew-rich). Chip fires when rr_25d >= own 80th percentile of history.
# Require >= 21 observations per name for non-null output; emit skew_n_obs for young-data tag.

def _load_options_skew(
    data_root: Path,
    min_obs: int = 21,
) -> dict[str, dict]:
    """Load call-skew data from data/options_skew/snapshots.parquet.

    Returns {ticker: {'rr_25d': float|None, 'rr_80th_pctile': float|None,
                       'skew_n_obs': int}} for each underlying in the store.

    rr proxy = atm_call_iv - otm_put_iv (= -skew). Chip calls-rich = True when
    rr_25d >= rr_80th_pctile. History < min_obs: both rr values are None.

    Args:
        data_root: repo data root
        min_obs: minimum date observations per ticker for non-null rr percentile (default 21)
    """
    p = data_root / "options_skew" / "snapshots.parquet"
    if not p.exists():
        log.debug("build_leader_radar: data/options_skew/snapshots.parquet absent")
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: options_skew/snapshots.parquet unreadable: %s", e)
        return {}

    if "underlying" not in df.columns or "atm_call_iv" not in df.columns or "otm_put_iv" not in df.columns:
        log.warning("build_leader_radar: options_skew missing required columns")
        return {}

    # Compute rr proxy = atm_call_iv - otm_put_iv = -skew (calls-rich = positive)
    df = df.copy()
    df["rr"] = df["atm_call_iv"] - df["otm_put_iv"]

    # Per-name: use latest observation only; compute 80th pctile over full history
    result: dict[str, dict] = {}
    date_col = "date" if "date" in df.columns else "asof"

    for underlying, grp in df.groupby("underlying"):
        ticker = str(underlying)
        try:
            # Aggregate across tenors: use mean per date
            daily = grp.groupby(date_col)["rr"].mean().sort_index()
            n_obs = len(daily)
            rr_now = float(daily.iloc[-1]) if n_obs > 0 else None
            if n_obs >= min_obs:
                rr_pctile = float(daily.quantile(0.80))
            else:
                rr_pctile = None
                rr_now = None  # also null when < min_obs
            result[ticker] = {
                "rr_25d": rr_now,
                "rr_80th_pctile": rr_pctile,
                "skew_n_obs": n_obs,
            }
        except Exception as e:  # noqa: BLE001
            log.debug("build_leader_radar: options_skew/%s failed: %s", ticker, e)
            result[ticker] = {"rr_25d": None, "rr_80th_pctile": None, "skew_n_obs": 0}
    return result


# ── Basket correlation (LRV-R1d) ──────────────────────────────────────────────

def _compute_basket_correlations(
    basket_membership: dict[str, list[str]],
    ohlcv_map: dict[str, pd.DataFrame],
    window_sessions: int = 60,
    min_members: int = 3,
) -> dict[str, tuple[float | None, float | None]]:
    """Compute mean pairwise 60d return correlation for each basket, now and 60d ago.

    Returns {basket_name: (corr_now, corr_then)}.
    corr_now: mean pairwise correlation of 60d daily returns among basket members today.
    corr_then: same, as of 60 sessions prior.
    None for baskets with < min_members members with data.

    Computed once per basket; members share the result (LRV-R1d).
    """
    results: dict[str, tuple[float | None, float | None]] = {}
    for basket_name, members in basket_membership.items():
        if basket_name in ("dow30", "ndx"):
            results[basket_name] = (None, None)
            continue
        closes: list[pd.Series] = []
        for t in members:
            ohlcv = ohlcv_map.get(t)
            if ohlcv is not None and "close" in ohlcv.columns:
                c = ohlcv["close"].dropna().sort_index()
                if len(c) >= window_sessions + window_sessions + 2:
                    closes.append(c.rename(t))
        if len(closes) < min_members:
            results[basket_name] = (None, None)
            continue
        try:
            # Align on common index
            aligned = pd.concat(closes, axis=1, sort=True).dropna()
            if len(aligned) < window_sessions + window_sessions + 2:
                results[basket_name] = (None, None)
                continue

            def _mean_pairwise_corr(ret_df: pd.DataFrame) -> float | None:
                if ret_df.shape[1] < min_members:
                    return None
                corr_matrix = ret_df.corr()
                # Upper triangle excluding diagonal
                upper = corr_matrix.where(
                    pd.DataFrame(
                        [[i < j for j in range(corr_matrix.shape[1])]
                         for i in range(corr_matrix.shape[0])],
                        index=corr_matrix.index,
                        columns=corr_matrix.columns,
                    )
                )
                vals = upper.stack().dropna()
                if len(vals) == 0:
                    return None
                return float(vals.mean())

            # Now: last window_sessions of returns
            ret_now = aligned.tail(window_sessions).pct_change().dropna()
            corr_now = _mean_pairwise_corr(ret_now) if len(ret_now) >= window_sessions // 2 else None

            # Then: window ending window_sessions bars ago
            end_then = len(aligned) - window_sessions
            start_then = end_then - window_sessions
            if start_then < 0:
                corr_then = None
            else:
                ret_then = aligned.iloc[start_then:end_then].pct_change().dropna()
                corr_then = _mean_pairwise_corr(ret_then) if len(ret_then) >= window_sessions // 2 else None

            results[basket_name] = (corr_now, corr_then)
        except Exception as e:  # noqa: BLE001
            log.debug("build_leader_radar: basket_corr/%s failed: %s", basket_name, e)
            results[basket_name] = (None, None)
    return results


# ── RS rank history builder (LRV-R1a) ─────────────────────────────────────────

def _build_rs_rank_history(
    universe: list[str],
    rs_map: dict[str, pd.Series],
    change_window: int = 63,
) -> dict[str, pd.DataFrame | None]:
    """Build weekly RS rank history for each name in the universe.

    Algorithm (vectorized):
      1. Load all rs_series into a wide DataFrame (date × ticker)
      2. Compute 63-session change of RS series (cross-sectional pct-rank input)
      3. Resample weekly (W-FRI)
      4. Percentile-rank cross-sectionally within universe at each week

    Args:
        universe: list of tickers
        rs_map: {ticker: rs_series (daily)}
        change_window: sessions for RS change computation (default 63)

    Returns:
        {ticker: DataFrame(DatetimeIndex, rs_rank column) | None}
    """
    # Build wide daily RS dataframe
    series_list = []
    valid_tickers = []
    for t in universe:
        rs = rs_map.get(t)
        if rs is not None and not rs.empty and len(rs) >= change_window + 2:
            series_list.append(rs.rename(t))
            valid_tickers.append(t)

    if not series_list:
        return {t: None for t in universe}

    wide = pd.concat(series_list, axis=1, sort=True)

    # Compute 63-session change
    change = wide.diff(change_window)

    # Resample to weekly (W-FRI): take last value per week
    weekly_change = change.resample("W-FRI").last()

    # Cross-sectional percentile rank at each week (pct=True gives 0..1)
    weekly_rank = weekly_change.rank(axis=1, pct=True)

    # Build per-ticker output DataFrames
    result: dict[str, pd.DataFrame | None] = {}
    for t in universe:
        if t in weekly_rank.columns:
            col = weekly_rank[t].dropna()
            if len(col) == 0:
                result[t] = None
            else:
                result[t] = pd.DataFrame({"rs_rank": col})
        else:
            result[t] = None
    return result


# ── Peer median RS slope (LRV-R1a) ────────────────────────────────────────────

def _compute_peer_medians(
    universe: list[str],
    basket_membership: dict[str, list[str]],
    rs_map: dict[str, pd.Series],
    window: int = 63,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Compute peer_median_rs_63d and rs_accel_leader for each ticker.

    peer_median_rs_63d: same-basket peer median of 63d RS slope (name excluded).
    rs_accel_leader: 21-session change of the name's own 63d RS slope.

    For names in multiple baskets, use the basket with the most members.
    Names not in any basket: peer_median = None.

    Returns:
        ({ticker: peer_median_rs_63d}, {ticker: rs_accel_leader})
    """
    from engine.leader_lifecycle import rs_slope as _rs_slope

    # Pre-compute 63d RS slope for each ticker (last value)
    slopes_63d: dict[str, float | None] = {}
    slope_series_63d: dict[str, pd.Series] = {}
    for t in universe:
        rs = rs_map.get(t)
        if rs is None or rs.empty or len(rs) < window // 2:
            slopes_63d[t] = None
            continue
        try:
            s = _rs_slope(rs, window)
            if s.empty or len(s.dropna()) == 0:
                slopes_63d[t] = None
            else:
                val = s.dropna().iloc[-1]
                slopes_63d[t] = float(val) if pd.notna(val) else None
                slope_series_63d[t] = s
        except Exception:  # noqa: BLE001
            slopes_63d[t] = None

    # rs_accel_leader: 21-session change of the 63d slope series
    rs_accel: dict[str, float | None] = {}
    for t in universe:
        try:
            s = slope_series_63d.get(t)
            if s is None or len(s.dropna()) < 22:
                rs_accel[t] = None
                continue
            s_clean = s.dropna()
            if len(s_clean) >= 22:
                accel = float(s_clean.iloc[-1]) - float(s_clean.iloc[-22])
                rs_accel[t] = accel if pd.notna(accel) else None
            else:
                rs_accel[t] = None
        except Exception:  # noqa: BLE001
            rs_accel[t] = None

    # Build ticker -> primary basket map (largest basket the name belongs to)
    ticker_basket: dict[str, str | None] = {t: None for t in universe}
    for basket_name, members in basket_membership.items():
        if basket_name in ("dow30", "ndx"):
            continue
        for t in members:
            if t in universe:
                prev = ticker_basket.get(t)
                if prev is None or len(basket_membership.get(basket_name, [])) > len(basket_membership.get(prev, [])):
                    ticker_basket[t] = basket_name

    # Peer median: median 63d slope of basket peers, excluding the name itself
    peer_median: dict[str, float | None] = {}
    for t in universe:
        basket = ticker_basket.get(t)
        if basket is None:
            peer_median[t] = None
            continue
        peers = [p for p in basket_membership.get(basket, []) if p != t and p in universe]
        peer_slopes = [slopes_63d[p] for p in peers if slopes_63d.get(p) is not None]
        if not peer_slopes:
            peer_median[t] = None
        else:
            import statistics
            peer_median[t] = statistics.median(peer_slopes)

    return peer_median, rs_accel


# ── Display observables from revisions (LRV-R3) ───────────────────────────────

def _extract_display_chips(sd: dict, revisions_df: pd.DataFrame, ticker: str) -> dict:
    """Extract display-only observables (LRV-R3). Must NOT enter any K-of-N gate.

    (a) revision_momentum_90d: est_chg_90d > 0 (tri-state) from revisions/latest.parquet
    (b) eps_dispersion_norm: raw value passed through
    (c) rs_line_gap_pct: computed per-ticker by builder and passed in separately

    Returns dict suitable for row['display_chips'].
    """
    chips: dict = {
        "revision_momentum_90d": None,
        "eps_dispersion_norm": None,
    }
    try:
        # Prefer revisions/latest.parquet
        if not revisions_df.empty and ticker in revisions_df.index:
            row = revisions_df.loc[ticker]
            est_90d = row.get("est_chg_90d") if hasattr(row, "get") else getattr(row, "est_chg_90d", None)
            if est_90d is not None and not (isinstance(est_90d, float) and pd.isna(est_90d)):
                chips["revision_momentum_90d"] = bool(float(est_90d) > 0)
            disp = row.get("eps_dispersion_norm") if hasattr(row, "get") else getattr(row, "eps_dispersion_norm", None)
            if disp is not None and not (isinstance(disp, float) and pd.isna(disp)):
                chips["eps_dispersion_norm"] = float(disp)
    except Exception:  # noqa: BLE001
        pass
    return chips


def _compute_top5_share(
    universe: list[str],
    ohlcv_map: dict[str, pd.DataFrame],
    mktcap_map: dict[str, float | None],
) -> tuple[float | None, int, str]:
    """Compute top-5 names' share of total 21d universe return (weighted by mktcap).

    Returns (top5_share, n_covered, weighting) where weighting is 'mktcap' when all
    names have valid cap weights, else 'equal_fallback' (mixed or pure equal-weight).
    """
    returns_21d: dict[str, float] = {}
    for ticker in universe:
        ohlcv = ohlcv_map.get(ticker)
        if ohlcv is None or len(ohlcv) < 22:
            continue
        close = ohlcv["close"].dropna().sort_index()
        if len(close) < 22:
            continue
        ret = float(close.iloc[-1] / close.iloc[-22] - 1.0)
        if np.isfinite(ret):
            returns_21d[ticker] = ret

    if not returns_21d:
        return None, 0, "equal_fallback"

    # Cap-weight if possible; track whether any name fell back to equal weight
    cap_weighted: dict[str, float] = {}
    n_covered = 0
    n_fallback = 0
    for t, r in returns_21d.items():
        cap = mktcap_map.get(t)
        if cap is not None and np.isfinite(cap) and cap > 0:
            cap_weighted[t] = r * cap
            n_covered += 1
        else:
            cap_weighted[t] = r  # equal-weight fallback for uncovered names
            n_fallback += 1

    if not cap_weighted:
        return None, 0, "equal_fallback"

    weighting = "mktcap" if n_fallback == 0 else "equal_fallback"

    total_weighted = sum(abs(v) for v in cap_weighted.values())
    if total_weighted == 0:
        return None, n_covered, weighting

    # Sort by abs contribution, take top 5
    sorted_contribs = sorted(cap_weighted.items(), key=lambda x: abs(x[1]), reverse=True)
    top5_contrib = sum(abs(v) for _, v in sorted_contribs[:5])
    return float(top5_contrib / total_weighted), n_covered, weighting


def _zweig_flag(breadth_df: pd.DataFrame) -> bool | None:
    """Simple Zweig breadth thrust approximation from breadth.parquet."""
    if breadth_df.empty or "adv" not in breadth_df.columns or "dec" not in breadth_df.columns:
        return None
    try:
        recent = breadth_df.tail(10)
        for _, row in recent.iterrows():
            adv = row.get("adv")
            dec = row.get("dec")
            if adv is not None and dec is not None and not pd.isna(adv) and not pd.isna(dec):
                total = float(adv) + float(dec)
                if total > 0 and float(adv) / total >= 0.615:
                    return True
        return False
    except Exception:  # noqa: BLE001
        return None


# ── Winner autopsy watch states ───────────────────────────────────────────────

def _build_watch_states(
    universe: list[str],
    ohlcv_map: dict[str, pd.DataFrame],
    spy: pd.Series,
    ticker_sectors: pd.DataFrame,
) -> dict[str, str | None]:
    """Run compute_watch_states for the universe.

    Assembles the inputs that build_winner_autopsy would use:
    - bars: dict of ticker -> DataFrame with close (+ volume if present)
    - bench_closes: {ETF: Series} from ohlcv or yahoo
    - sector_of: {ticker: sector} from ticker_sectors.parquet
    """
    try:
        from engine.winner_autopsy import compute_watch_states, _GICS_ETF, BENCH
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: winner_autopsy import failed: %s", e)
        return {}

    # sector_of map
    sector_of: dict[str, str] = {}
    if not ticker_sectors.empty and "ticker" in ticker_sectors.columns and "sector" in ticker_sectors.columns:
        for _, row in ticker_sectors.iterrows():
            t = str(row["ticker"])
            s = str(row["sector"])
            sector_of[t] = s

    # bars: only include tickers with ohlcv
    bars: dict[str, pd.DataFrame] = {}
    for ticker in universe:
        ohlcv = ohlcv_map.get(ticker)
        if ohlcv is not None and not ohlcv.empty:
            bars[ticker] = ohlcv

    if not bars:
        return {}

    # bench_closes: SPY + sector ETFs from ohlcv_map / yahoo
    data_root = config.data_dir()
    bench_closes: dict[str, pd.Series] = {BENCH: spy}
    for etf_ticker in set(_GICS_ETF.values()):
        if etf_ticker not in bench_closes:
            s = _load_sector_etf_close(etf_ticker, data_root)
            if s is not None:
                bench_closes[etf_ticker] = s

    try:
        watch_df = compute_watch_states(bars, bench_closes, sector_of)
        if watch_df.empty or "state" not in watch_df.columns or "ticker" not in watch_df.columns:
            return {}
        return dict(zip(watch_df["ticker"].astype(str), watch_df["state"].astype(str)))
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: compute_watch_states failed: %s", e)
        return {}


# ── Per-ticker assessment ─────────────────────────────────────────────────────

def _build_ticker_assessment(
    ticker: str,
    ohlcv: pd.DataFrame,
    spy: pd.Series,
    rs_series_today: pd.Series,
    breakaway_watch_state: str | None,
    revisions_row: dict,
    valuation_row: dict,
    earnings_row: dict,
    analyst_row: dict,
    raw_history: list[tuple[date, str]],
    confirmed_history: list[tuple[date, str]],
    stale: bool,
    # LRV-W1 new wires (all optional; null-safe)
    rs_rank_history: "pd.DataFrame | None" = None,
    peer_median_rs_63d: float | None = None,
    rs_accel_leader: float | None = None,
    insider_cluster: bool | None = None,
    rr_25d: float | None = None,
    rr_80th_pctile: float | None = None,
    basket_corr_now: float | None = None,
    basket_corr_then: float | None = None,
) -> tuple[Any, str, str] | None:
    """Build LifecycleInputs, classify, apply_hysteresis.

    Returns (assessment, raw_state, confirmed_state) or None on error.

    LRV-W1 adds wires for RS rank history, insider_cluster, call_skew, basket_corr.
    All new parameters are null-safe; null never counts as False (Kleene).
    """
    from engine.leader_lifecycle import (
        LifecycleInputs,
        classify,
        apply_hysteresis,
        tf_state_2d,
        STATE_NONE,
    )

    close = ohlcv["close"].dropna().sort_index()
    close.index = pd.to_datetime(close.index)
    high = ohlcv["high"].dropna().sort_index() if "high" in ohlcv.columns else None
    low = ohlcv["low"].dropna().sort_index() if "low" in ohlcv.columns else None
    volume = ohlcv["volume"].dropna().sort_index() if "volume" in ohlcv.columns else None

    # days_in_state from confirmed history
    days_in_state: int | None = None
    if confirmed_history:
        current_state = confirmed_history[-1][1]
        count = 0
        for _, s in reversed(confirmed_history):
            if s == current_state:
                count += 1
            else:
                break
        days_in_state = count

    # analyst_buy_pct (LRV-R1e): buy-share LEVEL from finnhub recommendation-trends
    # (data/finnhub/recommendation.parquet via engine/analyst_revisions.consensus_pct =
    # (strongBuy+buy)/total×100). The synapse `analyst-targets` store (yfinance .info)
    # was evaluated and rejected — consensus recommendationKey only, no rating counts.
    # Null-honest: uncovered/stale-period names arrive here with an empty analyst_row.

    inp = LifecycleInputs(
        close=close,
        bench_close=spy,
        breakaway_watch_state=breakaway_watch_state,
        net_up_30d=revisions_row.get("net_up_30d"),
        est_chg_30d=revisions_row.get("est_chg_30d"),
        revision_breadth=revisions_row.get("breadth"),
        cheap_pctile=valuation_row.get("cheap_pctile"),
        fwd_pe=valuation_row.get("fwd_pe"),
        sector_median_fwd_pe=valuation_row.get("sector_median_fwd_pe"),
        valuation_pctile_5y=valuation_row.get("valuation_pctile_5y"),
        analyst_buy_pct=analyst_row.get("consensus_pct"),
        high=high,
        low=low,
        volume=volume,
        earnings_within_14d=(
            bool(earnings_row["days_to_earnings"] <= 14)
            if earnings_row.get("days_to_earnings") is not None else None
        ),
        state_history=confirmed_history,
        days_in_state=days_in_state,
        # LRV-W1 new wires (rr_25d + rr_80th_pctile → engine computes call_skew_rich)
        rs_rank_history=rs_rank_history,
        peer_median_rs_63d=peer_median_rs_63d,
        rs_accel_leader=rs_accel_leader,
        insider_cluster=insider_cluster,
        rr_25d=rr_25d,
        rr_80th_pctile=rr_80th_pctile,
        basket_corr_now=basket_corr_now,
        basket_corr_then=basket_corr_then,
    )

    assessment = classify(inp)

    # Stale freeze: don't advance confirmed state when prices are stale
    if stale:
        confirmed_state = confirmed_history[-1][1] if confirmed_history else assessment.state
    else:
        confirmed_state = apply_hysteresis(
            assessment.state, raw_history, confirmed_history
        )

    return assessment, assessment.state, confirmed_state


# ── Fire tracking ─────────────────────────────────────────────────────────────

def _compute_fires(
    ticker: str,
    assessment: Any,
    confirmed_state: str,
    confirmed_history: list[tuple[date, str]],
    assessment_history: list[Any],
    fire_dates: dict[str, date | None],
    stale: bool,
) -> tuple[bool, bool]:
    """Return (fire_precipice, fire_onset) for today.

    Applies 21-session lockout + de-escalation check via eligible_for_refire.

    Seed-run rule (B1): if assessment_history is empty (no prior confirmed history
    row), fires are suppressed — entry is unverifiable without a prior state.
    The engine entry guards (precipice_fire / onset_fire) require a prior state to
    detect the transition; an empty history would fire spuriously on every run.
    """
    from engine.leader_lifecycle import (
        precipice_fire as _precipice_fire,
        onset_fire as _onset_fire,
        eligible_for_refire,
        STATE_CATALYST_WINDOW,
        STATE_BREAKAWAY,
    )

    if stale:
        return False, False

    # Seed-run gate: no prior history row → entry unverifiable → no fire
    if not assessment_history:
        return False, False

    # Build a post-hysteresis assessment with the confirmed state
    import copy
    assessment_conf = copy.copy(assessment)
    assessment_conf.state = confirmed_state

    last_fire = fire_dates.get(ticker)
    eligible = eligible_for_refire(confirmed_history, last_fire)

    fire_p = False
    fire_o = False

    if eligible:
        fire_p = _precipice_fire(assessment_conf, assessment_history)
        fire_o = _onset_fire(assessment_conf, assessment_history)

    return fire_p, fire_o


# ── Handoff watch (LR-R4) ────────────────────────────────────────────────────

def _compute_handoff(
    universe: list[str],
    basket_membership: dict[str, list[str]],
    ohlcv_map: dict[str, pd.DataFrame],
    spy: pd.Series,
    assessments_map: dict[str, Any],
) -> tuple[dict[str, bool | None], list[dict]]:
    """Compute basket extended_leg flags and handoff pairs."""
    from engine.leader_lifecycle import (
        extended_leg as _extended_leg,
        handoff_pairs as _handoff_pairs,
        basing_leg as _basing_leg,
        tf_state_2d,
    )

    extended_baskets: dict[str, bool | None] = {}
    # Only check theme baskets (not dow30/ndx which lack a single EW basket)
    theme_baskets = [
        k for k in basket_membership
        if k not in ("dow30", "ndx")
    ]

    for basket_name in theme_baskets:
        members = basket_membership.get(basket_name) or []
        closes = []
        for t in members:
            ohlcv = ohlcv_map.get(t)
            if ohlcv is not None and "close" in ohlcv.columns:
                closes.append(ohlcv["close"].dropna().sort_index())
        if not closes:
            extended_baskets[basket_name] = None
            continue
        try:
            # EW basket close: align on common index
            aligned = pd.concat(closes, axis=1, sort=True).ffill().dropna()
            if aligned.empty:
                extended_baskets[basket_name] = None
                continue
            basket_close = aligned.mean(axis=1)
            extended_baskets[basket_name] = _extended_leg(basket_close, spy)
        except Exception:  # noqa: BLE001
            extended_baskets[basket_name] = None

    pairs = _handoff_pairs(extended_baskets, assessments_map, basket_membership)
    return extended_baskets, pairs


# ── Rerating watch ────────────────────────────────────────────────────────────

def _compute_rerating_watch(
    universe: list[str],
    assessments_map: dict[str, Any],
    revisions_map: dict[str, dict],
    valuation_map: dict[str, dict],
    earnings_map: dict[str, dict],
) -> list[dict]:
    """Build rerating watch rows for names in advanced states."""
    from engine.leader_lifecycle import (
        rerating_conditions,
        STATE_BREAKAWAY,
        STATE_LEADERSHIP,
        STATE_CATALYST_WINDOW,
    )

    watch_states = {STATE_BREAKAWAY, STATE_LEADERSHIP, STATE_CATALYST_WINDOW}
    rows: list[dict] = []
    for ticker in universe:
        a = assessments_map.get(ticker)
        if a is None or a.state not in watch_states:
            continue
        chips = rerating_conditions(
            revisions_map.get(ticker) or {},
            valuation_map.get(ticker) or {},
            earnings_map.get(ticker) or {},
        )
        rows.append({"ticker": ticker, "state": a.state, "chips": chips})
    return rows


# ── Regime ───────────────────────────────────────────────────────────────────

def _build_regime(
    regime_raw: dict,
    breadth_df: pd.DataFrame,
    universe: list[str],
    ohlcv_map: dict[str, pd.DataFrame],
    mktcap_map: dict[str, float | None],
) -> dict:
    """Build leadership regime dict."""
    from engine.leader_lifecycle import leadership_regime

    dispersion_pctile_raw = regime_raw.get("dispersion_pctile")
    dispersion_pctile = (
        float(dispersion_pctile_raw) * 100.0
        if dispersion_pctile_raw is not None and float(dispersion_pctile_raw) <= 1.0
        else (float(dispersion_pctile_raw) if dispersion_pctile_raw is not None else None)
    )
    avg_corr: float | None = regime_raw.get("avg_corr")

    pct_above_200: float | None = None
    zweig: bool | None = None
    if not breadth_df.empty:
        if "pct_above_200" in breadth_df.columns:
            last = breadth_df["pct_above_200"].dropna()
            if not last.empty:
                pct_above_200 = float(last.iloc[-1])
        zweig = _zweig_flag(breadth_df)

    top5_share, n_covered, top5_weighting = _compute_top5_share(universe, ohlcv_map, mktcap_map)

    regime = leadership_regime(
        dispersion_pctile=dispersion_pctile,
        avg_corr=avg_corr,
        pct_above_200=pct_above_200,
        top5_share_21d=top5_share,
        zweig_flag=zweig,
    )
    regime["mktcap_n_covered"] = n_covered
    # m4: expose weighting method so equal-weight fallback is visible in the artifact
    regime["top5_weighting"] = top5_weighting
    return regime


# ── Main build ────────────────────────────────────────────────────────────────

def build(
    data_root: Path | None = None,
    site_root: Path | None = None,
) -> dict:
    """Build radar.json. Returns payload dict."""
    t0 = time.monotonic()
    cfg = config.load()
    lr_cfg = cfg.get("leader_radar") or {}

    if data_root is None:
        data_root = config.data_dir()
    if site_root is None:
        site_root = config.ROOT / cfg["storage"]["site_dir"]

    out_dir = site_root / "leaderradar"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not lr_cfg.get("enabled", True):
        _write_noindex_stub(site_root)
        return {}

    as_of = datetime.now(timezone.utc).isoformat()

    # ── Universe ──────────────────────────────────────────────────────────────
    universe, basket_membership = _resolve_universe(data_root, cfg)
    if not universe:
        log.warning("build_leader_radar: empty universe — writing cold-start artifact")

    # ── SPY close ─────────────────────────────────────────────────────────────
    spy = _load_spy(data_root)
    if spy is None:
        log.warning("build_leader_radar: SPY absent — RS series and regime degraded")
        spy = pd.Series(dtype=float)

    # ── Stale SLA ─────────────────────────────────────────────────────────────
    latest_date: date | None = None
    if not spy.empty:
        last_ts = spy.index[-1]
        latest_date = last_ts.date() if hasattr(last_ts, "date") else pd.Timestamp(last_ts).date()
    stale = _check_stale(latest_date)
    if stale:
        log.warning("build_leader_radar: stale (latest=%s) — state frozen", latest_date)

    # ── Load breadth and ticker_sectors ───────────────────────────────────────
    breadth_df = pd.DataFrame()
    try:
        bp = data_root / "breadth" / "breadth.parquet"
        if bp.exists():
            breadth_df = pd.read_parquet(bp).sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: breadth.parquet unreadable: %s", e)

    ticker_sectors = pd.DataFrame()
    try:
        tsp = data_root / "breadth" / "ticker_sectors.parquet"
        if tsp.exists():
            ticker_sectors = pd.read_parquet(tsp)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: ticker_sectors.parquet unreadable: %s", e)

    # ── Load OHLCV for all universe names ─────────────────────────────────────
    ohlcv_map: dict[str, pd.DataFrame] = {}
    for ticker in universe:
        df = _load_ohlcv(ticker, data_root)
        if df is not None:
            ohlcv_map[ticker] = df

    # ── Revisions (latest.parquet) ────────────────────────────────────────────
    revisions_df = pd.DataFrame()
    try:
        rp = data_root / "revisions" / "latest.parquet"
        if rp.exists():
            revisions_df = pd.read_parquet(rp)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: revisions/latest.parquet unreadable: %s", e)

    def _revisions_row(ticker: str) -> dict:
        if revisions_df.empty:
            return {}
        if ticker in revisions_df.index:
            row = revisions_df.loc[ticker]
            return {
                "net_up_30d": row.get("net_up_30d") if hasattr(row, "get") else getattr(row, "net_up_30d", None),
                "est_chg_30d": row.get("est_chg_30d") if hasattr(row, "get") else getattr(row, "est_chg_30d", None),
                "breadth": row.get("breadth") if hasattr(row, "get") else getattr(row, "breadth", None),
            }
        return {}

    revisions_uncovered: list[str] = [t for t in universe if t not in (revisions_df.index.tolist() if not revisions_df.empty else [])]

    # ── State history ─────────────────────────────────────────────────────────
    state_df = _load_state_history(data_root)

    # ── Winner autopsy watch states ───────────────────────────────────────────
    watch_states_map: dict[str, str | None] = {}
    if not spy.empty:
        try:
            watch_states_map = _build_watch_states(universe, ohlcv_map, spy, ticker_sectors)
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: watch_states failed: %s", e)

    # ── Stockdata context (revisions, valuation, earnings, personality) ───────
    revisions_store: dict[str, dict] = {}
    valuation_store: dict[str, dict] = {}
    earnings_store: dict[str, dict] = {}
    personality_store: dict[str, dict] = {}
    mktcap_map: dict[str, float | None] = {}

    for ticker in universe:
        sd = _load_stockdata(ticker, site_root)
        # Prefer revisions from revisions/latest.parquet over stockdata
        rev_pq = _revisions_row(ticker)
        if rev_pq:
            revisions_store[ticker] = rev_pq
        else:
            revisions_store[ticker] = _extract_revisions(sd)
        valuation_store[ticker] = _extract_valuation(sd)
        earnings_store[ticker] = _extract_earnings(sd)
        personality_store[ticker] = _extract_personality(sd)
        mktcap_map[ticker] = _extract_mktcap(sd)

    # ── Regime ────────────────────────────────────────────────────────────────
    regime_raw = _load_regime_inputs(data_root)
    regime = _build_regime(regime_raw, breadth_df, universe, ohlcv_map, mktcap_map)

    # ── RS series: full-history backfill on first run (nightly), read-only otherwise ──
    nightly_lane = _ledger_advance_enabled()
    rs_map: dict[str, pd.Series] = {}
    if not spy.empty:
        for ticker in universe:
            ohlcv = ohlcv_map.get(ticker)
            if ohlcv is None:
                continue
            try:
                if nightly_lane:
                    # Nightly: build + write (backfill on first run, append thereafter)
                    existing = _load_rs_series(ticker, data_root)
                    rs = _build_rs_series(ticker, ohlcv, spy, existing, data_root)
                else:
                    # Non-nightly: read-only; skip data/ write (HOUSE-U5)
                    rs = _load_rs_series(ticker, data_root)
                rs_map[ticker] = rs
            except Exception as e:  # noqa: BLE001
                log.debug("build_leader_radar: rs_series/%s failed: %s", ticker, e)

    # ── LRV-W1: New loaders (insider, skew, RS-rank, basket-corr, peer-medians) ──
    t_lrv_w1 = time.monotonic()

    # Insider cluster: {ticker: True/False/None}
    insider_map: dict[str, bool | None] = {}
    try:
        insider_map = _load_insider_cluster(data_root, date.today())
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: insider_cluster load failed: %s", e)

    # Options skew: {ticker: {rr_25d, rr_80th_pctile, skew_n_obs}}
    skew_map: dict[str, dict] = {}
    try:
        skew_map = _load_options_skew(data_root)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: options_skew load failed: %s", e)

    # LRV-R1e — analyst buy-share: {ticker: {consensus_pct, n_analysts, ...}}
    analyst_store: dict[str, dict] = {}
    try:
        analyst_store = _load_analyst_buy_share(data_root, date.today())
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: analyst buy-share load failed: %s", e)
    analyst_covered = [t for t in universe if t in analyst_store]
    analyst_uncovered = [t for t in universe if t not in analyst_store]

    # RS rank history: {ticker: DataFrame(rs_rank) | None}  (vectorized)
    rs_rank_history_map: dict[str, Any] = {}
    if rs_map:
        try:
            rs_rank_history_map = _build_rs_rank_history(universe, rs_map)
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: rs_rank_history build failed: %s", e)

    # Peer medians: {ticker: peer_median_rs_63d}, {ticker: rs_accel_leader}
    peer_median_map: dict[str, float | None] = {}
    rs_accel_map: dict[str, float | None] = {}
    if rs_map:
        try:
            peer_median_map, rs_accel_map = _compute_peer_medians(
                universe, basket_membership, rs_map
            )
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: peer_medians failed: %s", e)

    # Basket correlations: {basket: (corr_now, corr_then)}
    basket_corr_map: dict[str, tuple] = {}
    if ohlcv_map:
        try:
            basket_corr_map = _compute_basket_correlations(
                basket_membership, ohlcv_map
            )
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: basket_corr failed: %s", e)

    # Build ticker → basket mapping (primary basket = largest non-dow30/ndx basket)
    ticker_primary_basket: dict[str, str | None] = {}
    for t in universe:
        best: str | None = None
        best_size = 0
        for bname, members in basket_membership.items():
            if bname in ("dow30", "ndx"):
                continue
            if t in members and len(members) > best_size:
                best = bname
                best_size = len(members)
        ticker_primary_basket[t] = best

    log.info(
        "[timing] LRV-W1 loaders: insider=%d, skew=%d, rs_rank=%d, peer_median=%d, basket_corr=%d (%.2fs)",
        len(insider_map), len(skew_map), len(rs_rank_history_map),
        len(peer_median_map), len(basket_corr_map),
        time.monotonic() - t_lrv_w1,
    )

    # ── Per-ticker loop ───────────────────────────────────────────────────────
    today = date.today()
    assessments_map: dict[str, Any] = {}
    new_state_rows: list[dict] = []
    new_fire_rows: list[dict] = []
    fire_precipice_set: set[str] = set()
    fire_onset_set: set[str] = set()
    rows: list[dict] = []

    # Load prior fire dates from fire_log (real per-ticker last fire date)
    fire_log_df = _load_fire_log(data_root)
    fire_dates: dict[str, date | None] = _last_fire_dates(fire_log_df)

    for ticker in universe:
        ohlcv = ohlcv_map.get(ticker)
        if ohlcv is None:
            log.debug("build_leader_radar: %s has no ohlcv — skipped", ticker)
            continue

        try:
            raw_history, confirmed_history = _ticker_state_history(ticker, state_df)

            # LRV-W1: resolve per-ticker basket-level inputs
            _primary_basket = ticker_primary_basket.get(ticker)
            _basket_corr = basket_corr_map.get(_primary_basket) if _primary_basket else None
            _skew = skew_map.get(ticker) or {}

            result = _build_ticker_assessment(
                ticker=ticker,
                ohlcv=ohlcv,
                spy=spy,
                rs_series_today=rs_map.get(ticker, pd.Series(dtype=float)),
                breakaway_watch_state=watch_states_map.get(ticker),
                revisions_row=revisions_store.get(ticker) or {},
                valuation_row=valuation_store.get(ticker) or {},
                earnings_row=earnings_store.get(ticker) or {},
                analyst_row=analyst_store.get(ticker) or {},
                raw_history=raw_history,
                confirmed_history=confirmed_history,
                stale=stale,
                # LRV-W1 new wires
                rs_rank_history=rs_rank_history_map.get(ticker),
                peer_median_rs_63d=peer_median_map.get(ticker),
                rs_accel_leader=rs_accel_map.get(ticker),
                insider_cluster=insider_map.get(ticker),
                rr_25d=_skew.get("rr_25d"),
                rr_80th_pctile=_skew.get("rr_80th_pctile"),
                basket_corr_now=_basket_corr[0] if _basket_corr else None,
                basket_corr_then=_basket_corr[1] if _basket_corr else None,
            )
            if result is None:
                continue

            assessment, raw_state, confirmed_state = result
            assessments_map[ticker] = assessment
            assessments_map[ticker].state = confirmed_state  # expose confirmed state

            # Fire rules — B1 fix: build real prior-assessment proxy from confirmed_history.
            # confirmed_history is a list of (date, state) tuples, newest last.
            # precipice_fire / onset_fire check assessment_history[-1].state to detect entry.
            # Seed run (no prior history): no fire — entry is unverifiable without history.
            from engine.leader_lifecycle import LifecycleAssessment as _LA
            if confirmed_history:
                # Construct a minimal prior LifecycleAssessment from the last persisted state.
                # Duck-type: precipice_fire/onset_fire only read .state on history[-1].
                prior_state = confirmed_history[-1][1]
                _prior = _LA(state=prior_state, evidence={}, n_avail=0)
                assessment_history_proxy: list[Any] = [_prior]
            else:
                # Seed run: no prior history row — suppress all fires (entry unverifiable).
                assessment_history_proxy = []

            fire_p, fire_o = _compute_fires(
                ticker=ticker,
                assessment=assessment,
                confirmed_state=confirmed_state,
                confirmed_history=confirmed_history,
                assessment_history=assessment_history_proxy,
                fire_dates=fire_dates,
                stale=stale,
            )
            if fire_p:
                fire_precipice_set.add(ticker)
                new_fire_rows.append({
                    "date": today,
                    "ticker": ticker,
                    "fire_type": "precipice",
                })
            if fire_o:
                fire_onset_set.add(ticker)
                new_fire_rows.append({
                    "date": today,
                    "ticker": ticker,
                    "fire_type": "onset",
                })

            # 2D oscillator
            close_series = ohlcv["close"].dropna().sort_index()
            from engine.leader_lifecycle import tf_state_2d
            tf2d = tf_state_2d(close_series)

            # days_in_state from confirmed
            days_in_state: int | None = None
            if confirmed_history:
                cur = confirmed_history[-1][1]
                count = 0
                for _, s in reversed(confirmed_history):
                    if s == cur:
                        count += 1
                    else:
                        break
                days_in_state = count

            # Context fields
            pers = personality_store.get(ticker) or {}
            pers_labels = pers.get("labels") or []
            val = valuation_store.get(ticker) or {}
            earn = earnings_store.get(ticker) or {}

            # LRV-W1: k_true / n_avail per state (count_k_true_n_avail)
            from engine.leader_lifecycle import count_k_true_n_avail as _count_k
            k_true, n_avail = _count_k(confirmed_state, assessment.evidence)

            # LRV-W1: rs_line_gap_pct (display-only, must NOT enter K-of-N or state gate)
            _rs_gap: float | None = None
            try:
                from engine.leader_lifecycle import rs_line_gap_pct as _rs_gap_fn
                _rs_ticker = rs_map.get(ticker)
                if _rs_ticker is not None and not _rs_ticker.empty:
                    _rs_gap = _rs_gap_fn(_rs_ticker)
            except Exception:  # noqa: BLE001
                _rs_gap = None

            # LRV-W1: display_chips sub-dict (LRV-R3; NEVER enter K-of-N or state gates)
            _display_chips = _extract_display_chips({}, revisions_df, ticker)
            _display_chips["rs_line_gap_pct"] = _rs_gap

            rows.append({
                "ticker": ticker,
                "raw_state": raw_state,
                "state": confirmed_state,
                "days_in_state": days_in_state,
                "chips": {
                    k: v for k, v in assessment.evidence.items()
                },
                "de_escalations": assessment.de_escalation_chips,
                "fire_precipice": fire_p,
                "fire_onset": fire_o,
                "k_true": k_true,
                "n_avail": n_avail,
                "display_chips": _display_chips,
                "context": {
                    "pe": val.get("fwd_pe"),
                    "fwd_pe": val.get("fwd_pe"),
                    "mktcap_bn": mktcap_map.get(ticker),
                    "personality_labels": pers_labels,
                    "days_to_earnings": earn.get("days_to_earnings"),
                    "valuation_pctile_5y": val.get("valuation_pctile_5y"),
                    "tf2d_state": tf2d,
                    # LRV-W1 context additions
                    "skew_n_obs": (skew_map.get(ticker) or {}).get("skew_n_obs"),
                    "peer_median_rs_63d": peer_median_map.get(ticker),
                    "rs_accel_leader": rs_accel_map.get(ticker),
                    "insider_cluster": insider_map.get(ticker),
                    # LRV-R1e context: buy-share level + analyst count behind analyst_saturated
                    "analyst_buy_pct": (analyst_store.get(ticker) or {}).get("consensus_pct"),
                    "analyst_n": (analyst_store.get(ticker) or {}).get("n_analysts"),
                },
                "breakaway_watch_state": watch_states_map.get(ticker),
            })

            # Accumulate new state row for state_history
            new_state_rows.append({
                "date": today,
                "ticker": ticker,
                "raw_state": raw_state,
                "confirmed_state": confirmed_state,
            })

        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: ticker %s failed (skipped): %s", ticker, e)
            continue

    # ── Persist data/ stores (nightly lane only — HOUSE-U5) ───────────────────
    if nightly_lane:
        # state_history
        if new_state_rows:
            try:
                new_df = pd.DataFrame(new_state_rows)
                # Dedup: remove today's existing rows for these tickers, then append
                if not state_df.empty and "date" in state_df.columns:
                    state_df["date"] = pd.to_datetime(state_df["date"])
                    today_ts = pd.Timestamp(today)
                    existing_not_today = state_df[state_df["date"] != today_ts]
                    updated = pd.concat([existing_not_today, new_df], ignore_index=True)
                else:
                    updated = new_df
                _write_state_history(updated, data_root)
                log.info("build_leader_radar: state_history: %d total rows", len(updated))
            except Exception as e:  # noqa: BLE001
                log.warning("build_leader_radar: state_history write failed: %s", e)

        # fire_log
        if new_fire_rows:
            try:
                new_fire_df = pd.DataFrame(new_fire_rows)
                # Dedup: remove today's existing fire rows, then append
                if not fire_log_df.empty and "date" in fire_log_df.columns:
                    fire_log_df["date"] = pd.to_datetime(fire_log_df["date"])
                    today_ts = pd.Timestamp(today)
                    existing_fire_not_today = fire_log_df[fire_log_df["date"] != today_ts]
                    updated_fire = pd.concat([existing_fire_not_today, new_fire_df], ignore_index=True)
                else:
                    updated_fire = new_fire_df
                _write_fire_log(updated_fire, data_root)
                log.info("build_leader_radar: fire_log: %d total rows", len(updated_fire))
            except Exception as e:  # noqa: BLE001
                log.warning("build_leader_radar: fire_log write failed: %s", e)

        # revisions_history
        try:
            _append_revisions_history(data_root)
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: revisions_history append error: %s", e)
    else:
        log.debug(
            "build_leader_radar: COLLECT_LANE!=nightly — skipping data/ writes (HOUSE-U5)",
        )

    # ── Handoff watch ─────────────────────────────────────────────────────────
    extended_baskets: dict[str, bool | None] = {}
    handoff_pairs_list: list[dict] = []
    if not spy.empty:
        try:
            extended_baskets, handoff_pairs_list = _compute_handoff(
                universe, basket_membership, ohlcv_map, spy, assessments_map,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: handoff computation failed: %s", e)

    # ── Rerating watch ────────────────────────────────────────────────────────
    rerating_watch: list[dict] = []
    try:
        rerating_watch = _compute_rerating_watch(
            universe, assessments_map, revisions_store, valuation_store, earnings_store,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: rerating_watch failed: %s", e)

    # ── LRV-W1: early_entry artifact (LRV-R2) ────────────────────────────────
    # CW/QA/SUPPRESSED rows with ≥1 True lead chip; sorted deterministically;
    # NO fused score — order is by (state_bucket, -k_true, days_in_state asc, ticker).
    # State buckets: CW=0, QA=1, SUP=2.
    from engine.leader_lifecycle import (
        STATE_CATALYST_WINDOW, STATE_QUIET_ACCUMULATION, STATE_SUPPRESSED,
    )

    _early_state_bucket = {
        STATE_CATALYST_WINDOW: 0,
        STATE_QUIET_ACCUMULATION: 1,
        STATE_SUPPRESSED: 2,
    }
    early_entry_rows: list[dict] = []
    for row in rows:
        _state = row["state"]
        if _state not in _early_state_bucket:
            continue
        _chips = row.get("chips") or {}
        # For SUPPRESSED: include only rows with ≥1 True LEAD chip.
        # Lead chips are the five positive-momentum signals; non-lead suppression chips
        # (e.g. drawdown_25pct, rs_slope_negative_3m, below_200dma_12m) must NOT
        # count — they merely confirm suppression, not early-entry candidacy.
        _LEAD_CHIPS = frozenset((
            "revision_positive",
            "rs_turn",
            "accum_evidence",
            "obv_divergence",
            "insider_cluster",
        ))
        _has_lead = any(_chips.get(k) is True for k in _LEAD_CHIPS)
        if _state == STATE_SUPPRESSED and not _has_lead:
            continue
        _k = row.get("k_true", 0) or 0
        _days = row.get("days_in_state")
        _days_sort = _days if _days is not None else 9999  # nulls last
        early_entry_rows.append({
            "ticker": row["ticker"],
            "state": _state,
            "k_true": _k,
            "n_avail": row.get("n_avail", 0),
            "days_in_state": row.get("days_in_state"),
            "fire_precipice": row.get("fire_precipice", False),
            "fire_onset": row.get("fire_onset", False),
            "rs_line_gap_pct": (row.get("display_chips") or {}).get("rs_line_gap_pct"),
            "display_chips": row.get("display_chips") or {},
            "_sort_key": (
                _early_state_bucket[_state],
                -_k,
                _days_sort,
                row["ticker"],
            ),
        })

    early_entry_rows.sort(key=lambda r: r["_sort_key"])
    for r in early_entry_rows:
        del r["_sort_key"]

    # ── LRV-W1: handoff_context artifact (LRV-R4) ────────────────────────────
    # Per-basket: extension_pctile_vs_200d, rs_21d_slope_sign, is_extended.
    from engine.leader_lifecycle import (
        rs_slope as _rs_slope_fn,
        basket_extension_pctile as _basket_ext_pctile,
    )
    import statistics as _statistics
    handoff_context: list[dict] = []
    for bname, members in basket_membership.items():
        if bname in ("dow30", "ndx"):
            continue
        _is_ext = extended_baskets.get(bname)
        # rs_21d_slope_sign: sign of 21d RS slope for EW basket RS series
        # Use median of member 21d RS slopes as basket-level proxy
        _member_slopes_21d: list[float] = []
        for t in members:
            _rs = rs_map.get(t)
            if _rs is None or _rs.empty or len(_rs) < 22:
                continue
            try:
                _sl = _rs_slope_fn(_rs, 21)
                if not _sl.empty:
                    _v = _sl.dropna()
                    if len(_v) > 0:
                        _member_slopes_21d.append(float(_v.iloc[-1]))
            except Exception:  # noqa: BLE001
                pass
        _rs21_sign: int | None = None
        if _member_slopes_21d:
            _med = _statistics.median(_member_slopes_21d)
            _rs21_sign = 1 if _med > 0 else (-1 if _med < 0 else 0)
        # extension_pctile_vs_200d: percentile of current basket EW extension vs own 200d
        # history, using the same basket_extension_pctile() helper as extended_leg() so
        # the two callers cannot drift.
        _ext_pctile: float | None = None
        _bkt_closes = []
        for t in members:
            _ohlcv = ohlcv_map.get(t)
            if _ohlcv is not None and "close" in _ohlcv.columns:
                _bkt_closes.append(_ohlcv["close"].dropna().sort_index())
        if _bkt_closes:
            try:
                _aligned_bkt = pd.concat(_bkt_closes, axis=1, sort=True).ffill().dropna()
                if not _aligned_bkt.empty:
                    _basket_close = _aligned_bkt.mean(axis=1)
                    _ext_pctile = _basket_ext_pctile(_basket_close)
            except Exception:  # noqa: BLE001
                _ext_pctile = None
        handoff_context.append({
            "basket": bname,
            "n_members": len(members),
            "is_extended": _is_ext,
            "rs_21d_slope_sign": _rs21_sign,
            "extension_pctile_vs_200d": _ext_pctile,
        })

    # ── Payload ───────────────────────────────────────────────────────────────
    elapsed = time.monotonic() - t0
    payload: dict[str, Any] = {
        "schema": "leader_radar.v1",
        "as_of": as_of,
        "stale": stale,
        "elapsed_s": round(elapsed, 2),
        "coverage": {
            "n_universe": len(universe),
            "revisions_uncovered": revisions_uncovered[:50],  # cap list
            "mktcap_n_covered": sum(1 for v in mktcap_map.values() if v is not None),
            "tape_note": "4H data available for select core names only; null-honest elsewhere",
            "rs_depth_note": "rs_series full-history backfill on first run (rs_series depth == ohlcv depth)",
            # LRV-R1e: analyst buy-share coverage (finnhub recommendation-trends,
            # ~120-name basket watchlist ⊂ universe; store born 2026-06-20 → young data)
            "analyst_covered": len(analyst_covered),
            "analyst_uncovered": analyst_uncovered[:50],  # cap list
            "analyst_note": (
                "analyst buy-share from finnhub recommendation-trends "
                "(monthly rating counts, ~120-name watchlist; young data — store live since 2026-06-20); "
                "uncovered or stale-period names carry a null chip"
            ),
        },
        "regime": regime,
        "rows": rows,
        "handoff_pairs": handoff_pairs_list,
        "rerating_watch": rerating_watch,
        # LRV-W1 artifacts
        "early_entry": early_entry_rows,
        "handoff_context": handoff_context,
    }

    # ── Write artifact ────────────────────────────────────────────────────────
    out_path = out_dir / "radar.json"
    out_path.write_text(
        json.dumps(payload, separators=(",", ":"), default=_json_default)
    )
    log.info(
        "build_leader_radar: wrote %s (%d rows, %d fire_p, %d fire_o, %.1fs, stale=%s)",
        out_path, len(rows), len(fire_precipice_set), len(fire_onset_set),
        elapsed, stale,
    )

    # ── Render HTML ───────────────────────────────────────────────────────────
    tpl_root = config.ROOT / "templates"
    tpl_path = tpl_root / "leader_radar.html.j2"
    if tpl_path.exists():
        try:
            from jinja2 import Environment, FileSystemLoader
            env = Environment(loader=FileSystemLoader(str(tpl_root)), autoescape=False)
            tpl = env.get_template("leader_radar.html.j2")
            rendered = tpl.render(leader_radar=payload)
            html_out = site_root / "leader_radar.html"
            html_out.write_text(rendered)
            log.info("build_leader_radar: rendered %s", html_out)
        except Exception as e:  # noqa: BLE001
            log.warning("build_leader_radar: HTML render failed: %s", e)
    else:
        log.info("build_leader_radar: template %s absent — skipping HTML", tpl_path)

    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        result = build()
        if result:
            cov = result.get("coverage") or {}
            log.info(
                "build_leader_radar: done. universe=%d, stale=%s, elapsed=%.1fs",
                cov.get("n_universe", 0),
                result.get("stale"),
                result.get("elapsed_s", 0),
            )
    except Exception as e:  # noqa: BLE001
        log.error("build_leader_radar: unexpected error: %s", e, exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
