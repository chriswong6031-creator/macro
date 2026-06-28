"""Per-stock share-pledge overhang (股权质押) — an A-share tail-risk plane.

Controlling-shareholder share pledging (股权质押) is the A-share margin-call analog:
when a large fraction of a name's shares are pledged as loan collateral, a price
drop can trigger forced liquidation, so a high pledge ratio is a fragility / tail-risk
overhang — never a bullish read. Eastmoney aggregates this per name at each
quarter-end:

  stock_gpzy_pledge_ratio_em(date=QUARTER_END)
      -> per name: 质押比例 (pledge ratio %), 质押市值 (pledged market value, 万元),
         所属行业 (sector), for one quarter-end snapshot, whole-market.

The source only publishes on the four fiscal quarter-ends ({03-31,06-30,09-30,12-31}),
and the latest quarter is published with a lag (e.g. on 2026-06-21 the 2026-03-31 cut
is not yet out — 2025-12-31 is the freshest). So the LOAD-BEARING piece here is the
quarter-end resolver: take the most recent quarter-end <= today, and walk back one
quarter at a time (up to 4) until a populated snapshot is found. akshare raises a
TypeError (not just an empty frame) on an unpublished quarter, so the walk-back must
swallow exceptions too.

Stored under data/china_pledge/pledge.parquet
({ticker, name, pledge_ratio, pledge_mktcap_yi, sector, quarter, asof}). Idempotent
within a UTC day (a cache already stamped today is left untouched). Best-effort:
degrades to 0 rows / returns 0 on any akshare failure, never raises into a build.

RISK-leg context only (radar / crowding cautions), never a buy signal.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from lib import config
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_pledge")

OUT = config.data_dir() / "china_pledge" / "pledge.parquet"

# Eastmoney publishes pledge ratios only at fiscal quarter-ends.
_QUARTER_ENDS = ("0331", "0630", "0930", "1231")
_MAX_WALKBACK = 4  # quarters to walk back before giving up


def _quarter_ends_desc(today: pd.Timestamp, n: int = _MAX_WALKBACK) -> list[str]:
    """The `n` most recent fiscal quarter-ends <= `today`, newest first (YYYYMMDD)."""
    out: list[str] = []
    year = today.year
    # collect quarter-ends for this year and prior years, descending, keep those <= today
    while len(out) < n and year >= today.year - n:
        for mmdd in reversed(_QUARTER_ENDS):
            d = pd.Timestamp(f"{year}{mmdd}")
            if d <= today:
                out.append(d.strftime("%Y%m%d"))
                if len(out) >= n:
                    break
        year -= 1
    return out


def _fetch_quarter(date: str) -> pd.DataFrame | None:
    """The whole-market pledge-ratio table for one quarter-end. None on failure/empty.

    akshare can raise (TypeError) on an unpublished quarter rather than returning
    an empty frame — both are treated as "not available" so the resolver walks back.
    """
    import akshare as ak
    try:
        df = ak.stock_gpzy_pledge_ratio_em(date=date)
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.debug("china pledge: pledge_ratio_em %s failed (%s)", date, e)
        return None
    return df if df is not None and not df.empty else None


def _resolve_quarter(today: pd.Timestamp) -> tuple[str | None, pd.DataFrame | None]:
    """Walk the recent quarter-ends newest->older, return the first populated one."""
    for date in _quarter_ends_desc(today):
        df = _fetch_quarter(date)
        if df is not None:
            return date, df
    return None, None


def _col(cols: list[str], needle: str) -> str | None:
    """First column whose name contains `needle` (akshare column names drift)."""
    return next((c for c in cols if needle in str(c)), None)


def refresh() -> int:
    """Resolve the freshest published quarter-end pledge snapshot and bake a compact
    per-ticker table. Best-effort: returns names written (0 on failure). Idempotent
    within a UTC day (a cache already stamped today is left untouched, so it runs once
    per CI day even if several builds call it)."""
    asof = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= asof:
                log.info("china pledge: cache already fresh (%s)", asof)
                return 0
        except Exception:  # noqa: BLE001
            pass

    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    quarter, df = _resolve_quarter(today)
    if df is None:
        log.warning("china pledge: no populated quarter-end found")
        return 0

    cols = list(df.columns)
    code_col = _col(cols, "代码")
    name_col = _col(cols, "简称") or _col(cols, "名称")
    ratio_col = _col(cols, "质押比例")
    mktcap_col = _col(cols, "质押市值")
    sector_col = _col(cols, "所属行业")
    if not code_col or ratio_col is None:
        log.warning("china pledge: expected columns missing (%s)", cols)
        return 0

    q_label = pd.to_datetime(quarter).strftime("%Y-%m-%d")
    rows = []
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_col))
        if not t:
            continue
        ratio = _num(r.get(ratio_col))
        if ratio is None:
            continue
        # 质押市值 is reported in 万元 (10k yuan); convert to 亿 (100M yuan).
        mktcap_wan = _num(r.get(mktcap_col)) if mktcap_col else None
        mktcap_yi = round(mktcap_wan / 1e4, 4) if mktcap_wan is not None else None
        rows.append({
            "ticker": t,
            "name": str(r.get(name_col) or "") if name_col else "",
            "pledge_ratio": ratio,
            "pledge_mktcap_yi": mktcap_yi,
            "sector": str(r.get(sector_col) or "") if sector_col else "",
            "quarter": q_label,
            "asof": asof,
        })
    if not rows:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT, index=False)
    log.info("china pledge: wrote %s (%d names, quarter %s, asof %s)",
             OUT, len(rows), q_label, asof)
    return len(rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
