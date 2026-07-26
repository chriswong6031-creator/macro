"""Accruing per-name HISTORY for the Tushare cross-sectional legs (fund-flow, chips) — GATED.

The snapshot collectors overwrite a single day; the predictive-validation harness
(engine/china_validation) needs a GRID of historical cross-sections to compute forward-return
rank-IC. This maintains a compact ~1y DAILY grid history — for only the names in the china_search
panel (the names that have forward returns to validate against) — backfilling any missing grid
dates from Tushare on first run and adding the newest each build, deduped on ticker+date. So the
``fundflow`` / ``chips`` validation families compute a REAL verdict immediately (using the history
the ¥-tier already paid for) instead of waiting months to accrue forward.

CADENCE — the store is DAILY, and now says so. It was written as a strided "weekly" grid
(``idx[-260:][::5]``), but a tail-anchored stride has no fixed origin: the freshest bar sat
PERMANENTLY 4 trading days behind the newest close (the flow page printed an as-of 4 days older
than the southbound card beside it, every day), and the phase walked one trading day per build,
so the append-only store accreted every phase and went daily regardless — measured 2026-07-25,
273 distinct dates over ~14 months, median gap 1 trading day. ``_grid_dates`` is now a CONTIGUOUS
daily tail anchored on the newest close (#3596): that fixes the staleness and removes the phase
while KEEPING the dense history — anchoring drops nothing already stored, it only fills the holes
the drifting phase left.

The dense cadence INVALIDATED the overlap assumptions downstream — engine/china_validation had
sized its HAC lags and its N gate for a weekly step. That harness now measures the cadence
instead of assuming it (#3597); see its module docstring. It reads this contiguous grid correctly
with no further change, and gates on distinct weeks + non-overlapping windows, never on the raw
cross-section count.

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
_GRID_DAYS = 260          # ~1y of DAILY cross-sections. NOTE: china_validation gates on distinct
                          # weeks + non-overlapping forward windows, never on this row count.
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


def _grid_dates(n_days: int = _GRID_DAYS) -> list[str]:
    """The last `n_days` trading days (YYYYMMDD) from the china_search close-panel index, newest last.

    CONTIGUOUS and anchored on the NEWEST close — deliberately not a strided sample. The grid was
    ``idx[-(52*5):][::5]``, commented "every ~5th trading day = weekly", which a tail-anchored
    slice cannot deliver because the stride has no fixed origin:

      * the newest element a stride-5 walk over the last 260 rows keeps is always position -5, so
        the freshest bar was PERMANENTLY 4 trading days behind the newest close. The flow page
        printed an as-of 4 days older than the southbound card beside it, every single day, and it
        read as a collector outage when it was arithmetic;
      * the whole phase shifted one trading day per build, so the append-only store accreted all
        five phases and became a ~daily panel anyway (verified: 210 dates, median gap 1 trading
        day) — the shape engine/flow_velocity's 20/65-BAR windows were resized for in #3561.

    Contiguous kills both at once: no stride ⇒ no phase to drift, and the last element IS the last
    close. `_MAX_BACKFILL` still bounds fetches per build and takes the NEWEST missing dates first,
    so freshness never queues behind a backlog of old holes.
    """
    try:
        cp = config.data_dir() / "china_search" / "closes.parquet"
        if not cp.exists():
            return []
        idx = pd.read_parquet(cp).sort_index().index
        return [pd.Timestamp(d).strftime("%Y%m%d") for d in idx[-n_days:]]
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
    """Maintain the fund-flow + chips daily-grid history. Gated; returns #dates backfilled."""
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
