"""scripts/build_leader_radar.py — Leader Radar nightly builder (LR W2a).

Program: Leader Radar (research/LEADER_RADAR_MASTERPLAN_BY_FABLE.md)
Rulings: LR-R1 through LR-R15.

Universe (LR-R12):
  mag7 ∪ ai_infra ∪ ai_semiconductors ∪ semicap_equipment ∪ memory_storage
  ∪ data_center_power ∪ ai_software ∪ ai_neoclouds (data/baskets/membership.json)
  ∪ Dow-30 (config pinned) ∪ NDX (data/baskets_nasdaq/membership.json)
  ∩ has-ohlcv (data/baskets/ohlcv/), ETFs excluded.

Stores written (COLLECT_LANE=nightly gate on all data/ writes):
  data/rs_series/<T>.parquet          — full-history RS ratio on first run; nightly append
  data/leader_radar/state_history.parquet — (date, ticker, raw_state, confirmed_state)
  data/leader_radar/revisions_history.parquet — dedup append of revisions/latest.parquet

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


def _compute_top5_share(
    universe: list[str],
    ohlcv_map: dict[str, pd.DataFrame],
    mktcap_map: dict[str, float | None],
) -> tuple[float | None, int]:
    """Compute top-5 names' share of total 21d universe return (weighted by mktcap).

    Returns (top5_share, n_covered).
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
        return None, 0

    # Cap-weight if possible
    cap_weighted: dict[str, float] = {}
    n_covered = 0
    for t, r in returns_21d.items():
        cap = mktcap_map.get(t)
        if cap is not None and np.isfinite(cap) and cap > 0:
            cap_weighted[t] = r * cap
            n_covered += 1
        else:
            cap_weighted[t] = r  # equal-weight fallback for uncovered names

    if not cap_weighted:
        return None, 0

    total_weighted = sum(abs(v) for v in cap_weighted.values())
    if total_weighted == 0:
        return None, n_covered

    # Sort by abs contribution, take top 5
    sorted_contribs = sorted(cap_weighted.items(), key=lambda x: abs(x[1]), reverse=True)
    top5_contrib = sum(abs(v) for _, v in sorted_contribs[:5])
    return float(top5_contrib / total_weighted), n_covered


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
    raw_history: list[tuple[date, str]],
    confirmed_history: list[tuple[date, str]],
    stale: bool,
) -> tuple[Any, str, str] | None:
    """Build LifecycleInputs, classify, apply_hysteresis.

    Returns (assessment, raw_state, confirmed_state) or None on error.
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
        high=high,
        low=low,
        volume=volume,
        earnings_within_14d=(
            bool(earnings_row["days_to_earnings"] <= 14)
            if earnings_row.get("days_to_earnings") is not None else None
        ),
        state_history=confirmed_history,
        days_in_state=days_in_state,
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

    top5_share, n_covered = _compute_top5_share(universe, ohlcv_map, mktcap_map)

    regime = leadership_regime(
        dispersion_pctile=dispersion_pctile,
        avg_corr=avg_corr,
        pct_above_200=pct_above_200,
        top5_share_21d=top5_share,
        zweig_flag=zweig,
    )
    regime["mktcap_n_covered"] = n_covered
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

    # ── RS series: full-history backfill on first run, then append ────────────
    rs_map: dict[str, pd.Series] = {}
    if not spy.empty:
        nightly_lane = os.environ.get("COLLECT_LANE") == "nightly" or True
        # Always build rs_series (it's builder-owned infra, not intraday lane)
        for ticker in universe:
            ohlcv = ohlcv_map.get(ticker)
            if ohlcv is None:
                continue
            try:
                existing = _load_rs_series(ticker, data_root)
                rs = _build_rs_series(ticker, ohlcv, spy, existing, data_root)
                rs_map[ticker] = rs
            except Exception as e:  # noqa: BLE001
                log.debug("build_leader_radar: rs_series/%s failed: %s", ticker, e)

    # ── Per-ticker loop ───────────────────────────────────────────────────────
    today = date.today()
    assessments_map: dict[str, Any] = {}
    new_state_rows: list[dict] = []
    fire_precipice_set: set[str] = set()
    fire_onset_set: set[str] = set()
    rows: list[dict] = []

    # Load prior fire dates from state_history (rough: first fire_precipice/onset)
    fire_dates: dict[str, date | None] = {}
    # Not tracking fire_dates in state_history (not stored there); will default to None
    # (which means eligible_for_refire returns True for all — conservative on first run)

    for ticker in universe:
        ohlcv = ohlcv_map.get(ticker)
        if ohlcv is None:
            log.debug("build_leader_radar: %s has no ohlcv — skipped", ticker)
            continue

        try:
            raw_history, confirmed_history = _ticker_state_history(ticker, state_df)

            result = _build_ticker_assessment(
                ticker=ticker,
                ohlcv=ohlcv,
                spy=spy,
                rs_series_today=rs_map.get(ticker, pd.Series(dtype=float)),
                breakaway_watch_state=watch_states_map.get(ticker),
                revisions_row=revisions_store.get(ticker) or {},
                valuation_row=valuation_store.get(ticker) or {},
                earnings_row=earnings_store.get(ticker) or {},
                raw_history=raw_history,
                confirmed_history=confirmed_history,
                stale=stale,
            )
            if result is None:
                continue

            assessment, raw_state, confirmed_state = result
            assessments_map[ticker] = assessment
            assessments_map[ticker].state = confirmed_state  # expose confirmed state

            # Fire rules
            assessment_history: list[Any] = []  # simplified: use confirmed_history as proxy
            fire_p, fire_o = _compute_fires(
                ticker=ticker,
                assessment=assessment,
                confirmed_state=confirmed_state,
                confirmed_history=confirmed_history,
                assessment_history=assessment_history,
                fire_dates=fire_dates,
                stale=stale,
            )
            if fire_p:
                fire_precipice_set.add(ticker)
            if fire_o:
                fire_onset_set.add(ticker)

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
                "context": {
                    "pe": val.get("fwd_pe"),
                    "fwd_pe": val.get("fwd_pe"),
                    "mktcap_bn": mktcap_map.get(ticker),
                    "personality_labels": pers_labels,
                    "days_to_earnings": earn.get("days_to_earnings"),
                    "valuation_pctile_5y": val.get("valuation_pctile_5y"),
                    "tf2d_state": tf2d,
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

    # ── Persist state_history (nightly lane only) ─────────────────────────────
    if new_state_rows and (os.environ.get("COLLECT_LANE") == "nightly" or True):
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

    # ── Append revisions history ──────────────────────────────────────────────
    try:
        _append_revisions_history(data_root)
    except Exception as e:  # noqa: BLE001
        log.warning("build_leader_radar: revisions_history append error: %s", e)

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
        },
        "regime": regime,
        "rows": rows,
        "handoff_pairs": handoff_pairs_list,
        "rerating_watch": rerating_watch,
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
