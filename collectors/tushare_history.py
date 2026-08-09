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

  data/tushare/flow_hist.parquet       {ticker, date, flow}    flow = moneyflow_dc 主力 net rate (超大+大单)
  data/tushare/chips_hist.parquet      {ticker, date, winner}  winner = cyq_perf 获利比例 win-rate
  data/tushare/chips_dist_hist.parquet {ticker, date, chip_*}  DERIVED aggregates of the cyq_chips
                                                               筹码分布 histogram (see below)

The chips-DISTRIBUTION leg does not share the other two legs' call shape and cannot. cyq_perf
and moneyflow_dc both answer a whole-market ``trade_date=`` query, so one call fills one whole
cross-section; ``cyq_chips`` REQUIRES ts_code, so it costs one call per NAME and returns a
histogram (~100+ price-level rows) per name per day. Two consequences shaped ``_accrue_chips_
distribution`` and neither is stylistic: calls are RANGED over a window of trading days so one
call covers many dates for a name, and what accrues here is the DERIVED per-ticker-date feature
row, never the raw histogram — 260 dates x N names of raw levels is a store two orders of
magnitude larger than this validation grid, and the raw rows already live (immutably, with
receipts) in the private ``data/china_chips_distribution/`` partitions.

DISPLAY/CONTEXT-ONLY — this is the validation substrate, never itself a signal.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from collectors import tushare_client as tc
from collectors import tushare_chips_distribution as chips_dist

log = logging.getLogger("tushare_history")

FLOW_HIST = config.data_dir() / "tushare" / "flow_hist.parquet"
CHIPS_HIST = config.data_dir() / "tushare" / "chips_hist.parquet"
CHIPS_DIST_HIST = config.data_dir() / "tushare" / "chips_dist_hist.parquet"
_CHIPS_DIST_WINDOW = 20        # trading days per RANGED cyq_chips call (row cap is 6000)
_CHIPS_DIST_MAX_CALLS = 12     # ranged calls per build — the 300/min premium pool is SHARED
_CHIPS_DIST_MAX_NAMES = 40     # names touched per build; accrual is resumable across builds
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


def _existing_pairs(path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    try:
        df = pd.read_parquet(path, columns=["ticker", "date"])
        return set(zip(df["ticker"].astype(str), df["date"].astype(str)))
    except Exception:  # noqa: BLE001
        return set()


def _close_panel():
    """The china_search close panel, re-indexed to YYYYMMDD — the reference price for the
    chip-distribution features. Missing closes yield NULL band features, never a fabricated
    reference: "no chips near the close" and "we don't know the close" are opposite readings."""
    try:
        cp = config.data_dir() / "china_search" / "closes.parquet"
        if not cp.exists():
            return None
        df = pd.read_parquet(cp).sort_index()
        df.index = [pd.Timestamp(d).strftime("%Y%m%d") for d in df.index]
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("tushare_history close panel unavailable (%s)", e)
        return None


def _close_for(closes, ticker: str, d: str):
    if closes is None or ticker not in closes.columns or d not in closes.index:
        return None
    try:
        return _num(closes.at[d, ticker])
    except Exception:  # noqa: BLE001 — duplicate index labels return a Series, not a scalar
        return None


def _accrue_chips_distribution(path, panel: set[str], dates: list[str], *,
                               window: int = _CHIPS_DIST_WINDOW,
                               max_calls: int = _CHIPS_DIST_MAX_CALLS,
                               max_names: int = _CHIPS_DIST_MAX_NAMES) -> int:
    """Backfill DERIVED cyq_chips distribution features into `path`, panel-filtered.

    One RANGED call per (name, window) — cyq_chips requires ts_code, so unlike the other legs
    a date cannot be filled in one call. Bounded three ways (calls, names, window) because the
    300/min premium budget is shared with the running daily collectors; the loop is resumable,
    taking the NEWEST missing dates first so freshness never queues behind old holes.
    """
    if not panel or not dates:
        return 0
    have = _existing_pairs(path)
    closes = _close_panel()
    index = {d: i for i, d in enumerate(dates)}
    rows: list[dict] = []
    calls = 0
    for ticker in sorted(panel)[:max_names]:
        if calls >= max_calls:
            break
        missing = [d for d in dates if (ticker, d) not in have]
        if not missing:
            continue
        end = missing[-1]                                   # newest missing date first
        start_i = max(0, index[end] - window + 1)
        span = dates[start_i:index[end] + 1]
        calls += 1
        df = tc.query(chips_dist.ENDPOINT,
                      ts_code=chips_dist.vendor_ticker(ticker),
                      start_date=span[0], end_date=span[-1])
        if df is None or df.empty or "trade_date" not in df.columns:
            continue
        if len(df) >= chips_dist.VENDOR_MAX_ROWS:
            # At the vendor's row cap the response is TRUNCATED and there is no documented
            # ordering to say which dates survived — a partial histogram would silently
            # deflate every mass feature computed from it. Drop the window, don't guess.
            log.warning("chips distribution window hit the vendor row cap for %s", ticker)
            continue
        for d, group in df.groupby(df["trade_date"].astype(str).str.replace("-", "")):
            if (ticker, d) in have or d not in index:
                continue
            levels = [{"ticker": ticker, "trade_date": d,
                       "price": r.get("price"), "percent": r.get("percent")}
                      for r in group.to_dict(orient="records")]
            mass = sum(_num(x["percent"]) or 0.0 for x in levels)
            if chips_dist.percent_mass_observation(mass) == (
                    "contradicts_documented_percentage_points_fraction_like"):
                # A 100x unit flip would be invisible in every downstream feature. Never rescale.
                log.warning("chips distribution percent unit contradiction for %s %s", ticker, d)
                continue
            f = chips_dist.summarize_distribution(
                levels, ref_price=_close_for(closes, ticker, d))
            rows.append({
                "ticker": ticker, "date": d,
                "chip_entropy_norm": f.get("entropy_normalized"),
                "chip_level_count": f.get("level_count"),
                "chip_peak_price": f.get("peak_price"),
                "chip_avg_cost": f.get("mass_weighted_avg_price"),
                "chip_winner_share": f.get("winner_share"),
                "chip_conc_5pct": f.get("concentration_share_5pct"),
                "chip_conc_10pct": f.get("concentration_share_10pct"),
            })
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    if path.exists():
        try:
            new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        except Exception as e:  # noqa: BLE001 — an unreadable store must not lose this run
            log.warning("chips distribution history unreadable, rewriting from new rows (%s)", e)
    # keep="first": already-stored pairs are filtered out above, so a duplicate here can only
    # be an in-run window overlap. Keeping first matches the raw plane's keep-first store.
    new = new.drop_duplicates(subset=["ticker", "date"], keep="first")
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(path, index=False)
    return len(rows)


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
    try:
        n += _accrue_chips_distribution(CHIPS_DIST_HIST, panel, dates)
    except Exception as e:  # noqa: BLE001
        log.warning("tushare chips distribution history skipped (%s)", e)
    log.info("tushare history: backfilled %d date-slots (flow+chips+chip-distribution)", n)
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
