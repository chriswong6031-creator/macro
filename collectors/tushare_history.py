"""Accruing per-name HISTORY for the Tushare cross-sectional legs (fund-flow, chips) — GATED.

The snapshot collectors overwrite a single day; the predictive-validation harness
(engine/china_validation) needs a GRID of historical cross-sections to compute forward-return
rank-IC. This maintains a compact weekly-grid history — for only the names in the china_search
panel (the names that have forward returns to validate against) — backfilling any missing grid
dates from Tushare on first run and adding the newest each build, deduped on ticker+date. So the
``fundflow`` / ``chips`` validation families compute a REAL verdict immediately (using the history
the ¥-tier already paid for) instead of waiting months to accrue forward.

GATED: no-ops unless ``TUSHARE_TOKEN`` is set. Both queries are leakage-irrelevant (raw signal
snapshots; the harness does the leak-guarded forward alignment).

  data/tushare/flow_hist.parquet   {ticker, date, flow}    flow = moneyflow_dc 主力 net rate (超大+大单)
  data/tushare/chips_hist.parquet  {ticker, date, winner}  winner = cyq_perf 获利比例 win-rate

DISPLAY/CONTEXT-ONLY — this is the validation substrate, never itself a signal.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from collectors import tushare_client as tc

log = logging.getLogger("tushare_history")

FLOW_HIST = config.data_dir() / "tushare" / "flow_hist.parquet"
CHIPS_HIST = config.data_dir() / "tushare" / "chips_hist.parquet"
_GRID_WEEKS = 52          # ~1y of weekly cross-sections (≥ _MIN_PROVEN_N=40 → can reach "proven")
_MAX_BACKFILL = 60        # safety cap on fetches per build (first run backfills the grid, then ~1/build)


def _panel_tickers() -> set[str]:
    """Tickers in the china_search panel — the only names with forward returns to validate."""
    try:
        mp = config.data_dir() / "china_search" / "members.parquet"
        if not mp.exists():
            return set()
        m = pd.read_parquet(mp)
        if m.index.name == "ticker" and "ticker" not in m.columns:
            return set(m.index.astype(str))
        col = "ticker" if "ticker" in m.columns else m.columns[0]
        return set(m[col].astype(str))
    except Exception:  # noqa: BLE001
        return set()


def _grid_dates(n_weeks: int = _GRID_WEEKS) -> list[str]:
    """Weekly trading-day grid (YYYYMMDD) from the china_search close-panel index, newest last."""
    try:
        cp = config.data_dir() / "china_search" / "closes.parquet"
        if not cp.exists():
            return []
        idx = pd.read_parquet(cp).sort_index().index
        grid = list(idx[-(n_weeks * 5):][::5])          # every ~5th trading day = weekly
        return [pd.Timestamp(d).strftime("%Y%m%d") for d in grid]
    except Exception as e:  # noqa: BLE001
        log.debug("tushare_history grid dates failed (%s)", e)
        return []


def _existing_dates(path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(pd.read_parquet(path, columns=["date"])["date"].astype(str))
    except Exception:  # noqa: BLE001
        return set()


def _flow_value(r) -> float | None:
    e = _num(getattr(r, "buy_elg_amount_rate", None))
    l = _num(getattr(r, "buy_lg_amount_rate", None))
    parts = [x for x in (e, l) if x is not None]
    if parts:
        return sum(parts)                                # 主力 (超大+大单) net rate — matches the live leg
    return _num(getattr(r, "net_amount_rate", None))     # fallback: total net rate


def _accrue(path, api: str, fields: str, value_attr, col: str, panel: set[str],
            dates: list[str]) -> int:
    """Backfill any missing grid dates for `api` into `path` ({ticker,date,<col>}), panel-filtered."""
    have = _existing_dates(path)
    missing = [d for d in dates if d not in have][-_MAX_BACKFILL:]
    if not missing:
        return 0
    rows: list[dict] = []
    for d in missing:
        df = tc.query(api, trade_date=d, fields=fields)
        if df is None or df.empty or "ts_code" not in df.columns:
            continue
        for r in df.itertuples():
            t = str(getattr(r, "ts_code", "") or "")
            if not t or (panel and t not in panel):
                continue
            v = value_attr(r)
            if v is not None:
                rows.append({"ticker": t, "date": d, col: v})
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    if path.exists():
        try:
            new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        except Exception:  # noqa: BLE001
            pass
    new = new.drop_duplicates(subset=["ticker", "date"], keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(path, index=False)
    return len(missing)


def refresh() -> int:
    """Maintain the fund-flow + chips weekly-grid history. Gated; returns #dates backfilled."""
    if not tc.enabled():
        return 0
    panel = _panel_tickers()
    dates = _grid_dates()
    if not dates:
        log.warning("tushare history: no panel date grid")
        return 0
    n = 0
    try:
        n += _accrue(FLOW_HIST, "moneyflow_dc",
                     "trade_date,ts_code,buy_elg_amount_rate,buy_lg_amount_rate,net_amount_rate",
                     _flow_value, "flow", panel, dates)
    except Exception as e:  # noqa: BLE001
        log.warning("tushare flow history skipped (%s)", e)
    try:
        n += _accrue(CHIPS_HIST, "cyq_perf", "trade_date,ts_code,winner_rate",
                     lambda r: _num(getattr(r, "winner_rate", None)), "winner", panel, dates)
    except Exception as e:  # noqa: BLE001
        log.warning("tushare chips history skipped (%s)", e)
    log.info("tushare history: backfilled %d date-slots (flow+chips)", n)
    return n


def _num(v):
    try:
        return float(v) if v is not None and float(v) == float(v) else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
