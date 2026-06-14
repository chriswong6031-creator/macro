"""SEC EDGAR quarterly diluted-EPS panel for the SUE earnings-momentum factor.

The annual fundamentals panel (collectors/edgar.py) carries only annual NetIncome,
which cannot express the QUARTERLY earnings surprise (SUE / post-earnings-announcement
drift) the literature documents. This module fetches the quarterly
EarningsPerShareDiluted frames (CY{year}Q{1..4}, uom USD-per-shares) — one keyless
call per calendar quarter, ~5k filers each — and builds a long point-in-time panel
keyed (ticker, period_end). The frames API does not carry the filing date, so we
stamp a synthetic as-of date = period_end + a reporting lag (mirroring the annual
panel's PIT convention in collectors/edgar.py). See scripts/validate_sue.py and
research/DATA_SIGNAL_EXPANSION_2026.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from collectors.edgar import _cfg, _frame, _ticker_cik_map, _universe_tickers
from lib import config

log = logging.getLogger(__name__)

EPS_CONCEPT = "EarningsPerShareDiluted"
EPS_UNIT = "USD-per-shares"


def eps_panel_path():
    return config.data_dir() / "edgar" / "eps_quarterly.parquet"


def build_eps_panel(start_year: int = 2008, end_year: int | None = None,
                    reporting_lag_days: int | None = None,
                    max_age_days: int = 7, force: bool = False) -> pd.DataFrame:
    """Fetch the quarterly diluted-EPS frames and write data/edgar/eps_quarterly.parquet.
    Columns: ticker, period_end, eps_q, asof_date. Universe = S&P 1500 breadth caches.
    Weekly-cached (like the annual panel): a fresh parquet is returned without refetching
    the ~72 frames, so the daily build only recomputes the factor ranks."""
    p = eps_panel_path()
    if not force and p.exists():
        age_d = (datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) / 86400.0
        if age_d < max_age_days:
            log.info("eps_quarterly cache fresh (%.1fd) — skip fetch", age_d)
            return pd.read_parquet(p)
    if end_year is None:
        end_year = datetime.now(timezone.utc).year
    lag = reporting_lag_days if reporting_lag_days is not None \
        else int(_cfg().get("quarterly_lag_days", 60))
    universe = _universe_tickers()
    if not universe:
        raise RuntimeError("no breadth close caches — run breadth collectors first")
    tic_cik = _ticker_cik_map(universe, end_year - 1)
    cik2tic: dict[int, str] = {}
    for t, c in tic_cik.items():
        cik2tic.setdefault(int(c), t)        # dedup dual-class: first ticker per CIK
    base = _cfg()["base_url"]
    rows: list[tuple[str, str, float]] = []
    for year in range(start_year, end_year + 1):
        for q in ("Q1", "Q2", "Q3", "Q4"):
            fr = _frame(base, EPS_CONCEPT, f"CY{year}{q}", EPS_UNIT)
            for cik, (eps, end) in fr.items():
                t = cik2tic.get(cik)
                if t and end:
                    rows.append((t, end, float(eps)))
    if not rows:
        raise RuntimeError("no quarterly EPS frames returned (SEC unreachable?)")
    df = pd.DataFrame(rows, columns=["ticker", "period_end", "eps_q"])
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    df = df.dropna(subset=["period_end"]).sort_values("period_end")
    # one EPS per (ticker, period_end): a duration frame may carry near-dup rows
    df = df.drop_duplicates(["ticker", "period_end"], keep="last").reset_index(drop=True)
    df["asof_date"] = df["period_end"] + pd.Timedelta(days=lag)
    p = eps_panel_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    log.info("eps_quarterly: %d rows, %d tickers, %s..%s", len(df), df["ticker"].nunique(),
             df["period_end"].min().date(), df["period_end"].max().date())
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_eps_panel()
