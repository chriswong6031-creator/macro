"""Analyst EPS estimate-REVISION momentum collector (research/STOCK_CONVICTION_V2.md).

Revision momentum — the breadth of analysts RAISING vs lowering, and the drift of the
consensus estimate itself — is the fastest, strongest pre-earnings cross-sectional
predictor in the literature (Mill Street: top-decile 15.6% vs 8.0% bottom; monthly IC
~0.23). It is the locally-unvalidatable-yet (yfinance gives only the CURRENT snapshot,
no history) but literature-validated cousin of the locally-FDR-validated SUE.

This drips a capped batch of US names per build (resumable, never hammers Yahoo) into
  data/revisions/latest.parquet   — newest reading per ticker (the live score reads this)
  data/revisions/history.parquet  — append-only daily snapshots, so the signal accrues a
                                     point-in-time archive we CAN backtest forward.

Fields (forward fiscal year, '+1y'): net_up_30d (up−down analyst count over 30d), breadth
(net/total ∈[−1,1]), est_chg_30d / est_chg_90d (consensus EPS drift %), n_analysts.

W2a (P1-A): add n_covering + breadth_cov
  n_covering  — total number of analysts providing a forward-year EPS estimate (coverage),
                read from the yfinance `earnings_estimate` accessor (Yahoo `earningsEstimate`
                module `numberOfAnalysts`).  This is a SEPARATE accessor from `eps_revisions`
                which carries only the REVISER count — the audited saturation pathology.
                HARD HONESTY RULE: n_covering is set only when the earnings_estimate accessor
                is available AND its numberOfAnalysts field is present and numeric.  If the
                field is absent or non-numeric, n_covering stays None and breadth_cov is not
                computed — it must NEVER silently substitute n_analysts (the reviser count).
  breadth_cov — (up − down) / n_covering, coverage-normalised.  Emitted alongside legacy
                fields (additive — legacy fields are never renamed or removed).  None whenever
                n_covering is absent.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger("equity_revisions")
_FRESH_DAYS = 6


def _one(ticker: str) -> dict | None:
    import yfinance as yf
    t = yf.Ticker(ticker)
    try:
        rev = t.eps_revisions
        trend = t.eps_trend
    except Exception:  # noqa: BLE001
        return None
    if rev is None or trend is None or not hasattr(rev, "index"):
        return None
    # forward fiscal year ('+1y') is the cleanest, most-covered horizon; fall back to '0y'
    row = None
    for key in ("+1y", "0y"):
        if key in rev.index:
            row = key
            break
    if row is None:
        return None

    def _num(df, r, c):
        try:
            v = float(df.loc[r, c]); return v if v == v else None
        except Exception:  # noqa: BLE001
            return None
    up = _num(rev, row, "upLast30days") or 0.0
    dn = _num(rev, row, "downLast30days") or 0.0
    tot = up + dn
    cur = _num(trend, row, "current")
    d30 = _num(trend, row, "30daysAgo")
    d90 = _num(trend, row, "90daysAgo")

    def _chg(now, then):
        if now is None or then is None or abs(then) < 1e-6:
            return None
        return round((now - then) / abs(then) * 100.0, 2)

    # W2a (P1-A): n_covering from the earnings_estimate accessor.
    # HARD HONESTY RULE: this MUST come from earnings_estimate.numberOfAnalysts, never
    # from `tot` (= up+down from eps_revisions = the REVISER count = the saturation bug).
    # If the accessor is absent, non-numeric, or the field is missing, n_covering stays
    # None and breadth_cov is not computed.
    n_covering: int | None = None
    breadth_cov: float | None = None
    try:
        ee = t.earnings_estimate
        # earnings_estimate is a DataFrame indexed by horizon (e.g. '0q','1q','+1y','0y')
        # with column 'numberOfAnalysts' (Yahoo earningsEstimate.numberOfAnalysts).
        if ee is not None and hasattr(ee, "index") and "numberOfAnalysts" in ee.columns:
            if row in ee.index:
                raw = ee.loc[row, "numberOfAnalysts"]
            else:
                # fall back to any available '+1y' or '0y' row
                raw = None
                for k in ("+1y", "0y"):
                    if k in ee.index:
                        raw = ee.loc[k, "numberOfAnalysts"]
                        break
            if raw is not None:
                v = float(raw)
                if v == v and v >= 1:   # NaN guard + positive guard
                    n_covering = int(v)
                    breadth_cov = round((up - dn) / n_covering, 4)
    except Exception:  # noqa: BLE001
        # accessor unavailable: honour the hard honesty rule — both stay None
        n_covering = None
        breadth_cov = None

    out = {
        "net_up_30d": up - dn,
        "breadth": round((up - dn) / tot, 3) if tot >= 1 else None,
        "est_chg_30d": _chg(cur, d30),
        "est_chg_90d": _chg(cur, d90),
        "n_analysts": int(tot) if tot else None,
        # W2a additions — None when earnings_estimate accessor is unavailable
        "n_covering": n_covering,
        "breadth_cov": breadth_cov,
    }
    return out if any(v is not None for v in out.values()) else None


def _universe() -> list[str]:
    tk: list[str] = []
    for grp in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            tk += list(pd.read_parquet(p).index.astype(str))
    return sorted(set(tk))


def fetch_revisions(max_new: int = 200) -> int:
    """Drip up to ``max_new`` STALEST names; update latest.parquet + append a dated
    snapshot to history.parquet. Best-effort — any per-name failure is skipped."""
    out_dir = config.data_dir() / "revisions"
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_p = out_dir / "latest.parquet"
    latest = pd.read_parquet(latest_p) if latest_p.exists() else pd.DataFrame()
    today = pd.Timestamp.now("UTC").normalize().tz_localize(None)

    uni = _universe()
    if not uni:
        log.warning("no constituents for revisions universe"); return 0
    asof = latest["asof"] if "asof" in latest.columns else pd.Series(dtype="datetime64[ns]")
    fresh = set(latest.index[(today - pd.to_datetime(asof)).dt.days < _FRESH_DAYS]) if len(latest) else set()
    todo = [t for t in uni if t not in fresh][:max_new]
    if not todo:
        log.info("revisions: all %d names fresh (<%dd)", len(uni), _FRESH_DAYS); return 0

    rows = {}
    for t in todo:
        try:
            r = _one(t)
        except Exception as e:  # noqa: BLE001
            log.debug("revisions %s skipped: %s", t, e); continue
        if r:
            r["asof"] = today
            rows[t] = r
    if not rows:
        log.info("revisions: drip fetched 0 of %d", len(todo)); return 0
    new = pd.DataFrame.from_dict(rows, orient="index")
    merged = new if latest.empty else pd.concat([latest[~latest.index.isin(new.index)], new])
    merged.to_parquet(latest_p)
    # append a dated snapshot for forward PIT accrual
    hist_p = out_dir / "history.parquet"
    snap = new.copy(); snap["date"] = today
    snap = snap.reset_index(names="ticker")
    if hist_p.exists():
        snap = pd.concat([pd.read_parquet(hist_p), snap], ignore_index=True)
        snap = snap.drop_duplicates(subset=["date", "ticker"], keep="last")
    snap.to_parquet(hist_p)
    log.info("revisions: +%d names (latest now %d, history %d rows)", len(rows), len(merged), len(snap))
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_revisions(int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 50)
