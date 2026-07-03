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

W0.6b (Setup-Species data plane): add estimate DISPERSION + REVENUE revision metrics
  eps_dispersion_norm        — (high_est − low_est) / |mean_est| for the forward-year EPS
                               estimate.  Source: yfinance earnings_estimate accessor columns
                               'high', 'low', 'avg'.  None when avg ≈ 0 or fields missing.
                               High dispersion = wide analyst disagreement.
  rev_growth_fwd             — forward-year implied revenue YoY growth (%): 100 ×
                               (avg_fwd − yearAgoRevenue) / |yearAgoRevenue|.  Source:
                               yfinance revenue_estimate accessor.  None when base ≈ 0.
  rev_est_high_low_spread_norm — (rev_high − rev_low) / |rev_avg| for the forward-year
                               revenue estimate.  Revenue analyst disagreement proxy.
  rev_n_analysts             — numberOfAnalysts from revenue_estimate.  Additive; never
                               substitutes n_analysts or n_covering.

Note: yfinance has no revenue_trend / revenue_revisions endpoint (confirmed 2026-07-03).
The 30d/90d revenue drift columns are structurally unavailable; they are NOT emitted
(omitted rather than fabricated).

All four W0.6b fields are ADDITIVE to the existing schema; no existing field is renamed or
removed.  PIT history behavior is unchanged (append-only history.parquet).
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

    # W0.6b: EPS estimate DISPERSION from earnings_estimate high/low/avg.
    # Normalised by |avg| so it's comparable across stocks.
    # None when avg ≈ 0 or any of the three columns are missing/NaN.
    eps_dispersion_norm: float | None = None
    try:
        ee = t.earnings_estimate  # may already be fetched above (yfinance caches)
        if ee is not None and hasattr(ee, "index"):
            ee_row = None
            for k in ("+1y", "0y"):
                if k in ee.index:
                    ee_row = k
                    break
            if ee_row is not None:
                for col_set in (("high", "low", "avg"), ("High", "Low", "Avg")):
                    c_hi, c_lo, c_av = col_set
                    if all(c in ee.columns for c in col_set):
                        hi = ee.loc[ee_row, c_hi]
                        lo = ee.loc[ee_row, c_lo]
                        av = ee.loc[ee_row, c_av]
                        try:
                            hi, lo, av = float(hi), float(lo), float(av)
                            if hi == hi and lo == lo and av == av and abs(av) >= 1e-6:
                                eps_dispersion_norm = round((hi - lo) / abs(av), 4)
                        except (TypeError, ValueError):
                            pass
                        break
    except Exception:  # noqa: BLE001
        eps_dispersion_norm = None

    # W0.6b: REVENUE revision metrics from revenue_estimate accessor.
    # revenue_estimate is a DataFrame indexed by horizon, with columns:
    #   avg, low, high, numberOfAnalysts, yearAgoRevenue, growth  (Yahoo revenueEstimate)
    # yfinance does NOT expose a revenue_trend / revenue_revisions endpoint — there is no
    # 30daysAgo / 90daysAgo column for revenue estimates (confirmed 2026-07-03).
    # We therefore emit:
    #   rev_growth_fwd  — forward-year implied revenue growth vs yearAgoRevenue (YoY %)
    #   rev_est_high_low_spread_norm — (high − low) / avg revenue estimate (dispersion)
    #   rev_n_analysts  — numberOfAnalysts from revenue_estimate (additive, never
    #                     substitutes n_analysts or n_covering)
    # The 30d/90d drift columns are structurally unavailable from yfinance; they are
    # intentionally omitted rather than fabricated.
    rev_growth_fwd: float | None = None
    rev_est_high_low_spread_norm: float | None = None
    rev_n_analysts: int | None = None
    try:
        re_df = t.revenue_estimate
        if re_df is not None and hasattr(re_df, "index"):
            re_row = None
            for k in ("+1y", "0y"):
                if k in re_df.index:
                    re_row = k
                    break
            if re_row is not None:
                def _rev_num(col: str):
                    try:
                        if col not in re_df.columns:
                            return None
                        v = float(re_df.loc[re_row, col])
                        return v if v == v else None
                    except Exception:  # noqa: BLE001
                        return None

                re_avg = _rev_num("avg")
                re_hi = _rev_num("high")
                re_lo = _rev_num("low")
                re_yago = _rev_num("yearAgoRevenue")
                re_na = _rev_num("numberOfAnalysts")

                # YoY growth: (fwd_avg − year_ago) / |year_ago| * 100
                if re_avg is not None and re_yago is not None and abs(re_yago) >= 1:
                    rev_growth_fwd = round((re_avg - re_yago) / abs(re_yago) * 100.0, 2)
                # Spread dispersion: (high − low) / avg
                if re_hi is not None and re_lo is not None and re_avg is not None and abs(re_avg) >= 1:
                    rev_est_high_low_spread_norm = round((re_hi - re_lo) / abs(re_avg), 4)
                if re_na is not None and re_na >= 1:
                    rev_n_analysts = int(re_na)
    except Exception:  # noqa: BLE001
        rev_growth_fwd = None
        rev_est_high_low_spread_norm = None
        rev_n_analysts = None

    out = {
        "net_up_30d": up - dn,
        "breadth": round((up - dn) / tot, 3) if tot >= 1 else None,
        "est_chg_30d": _chg(cur, d30),
        "est_chg_90d": _chg(cur, d90),
        "n_analysts": int(tot) if tot else None,
        # W2a additions — None when earnings_estimate accessor is unavailable
        "n_covering": n_covering,
        "breadth_cov": breadth_cov,
        # W0.6b additions — None when accessor is unavailable or base ≈ 0
        "eps_dispersion_norm": eps_dispersion_norm,
        "rev_growth_fwd": rev_growth_fwd,
        "rev_est_high_low_spread_norm": rev_est_high_low_spread_norm,
        "rev_n_analysts": rev_n_analysts,
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
