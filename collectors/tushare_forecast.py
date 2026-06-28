"""Earnings guidance + sell-side forecast revisions — Tushare forecast / report_rc (GATED).

Two analyst/earnings feeds the free akshare stack can't reliably reach:

  forecast   业绩预告   PRIMARY (2000积分, reliable): company self-guidance — direction
             (预增/预减/扭亏/续盈/略增…) + the guided net-profit % change range. The earnings
             SURPRISE backdrop per name.
  report_rc  卖方盈利预测明细  BEST-EFFORT (8000积分, throttled to 1 call/hour on this tier):
             per-analyst EPS / target-price / rating detail. Stored raw for the future
             forecast-REVISION-momentum leg; degrades silently when the hourly budget is spent.

GATED: no-ops unless ``TUSHARE_TOKEN`` is set.
  data/tushare/forecast.parquet   ticker, type, p_change_min, p_change_max, end_date, ann_date, asof
  data/tushare/report_rc.parquet  raw recent-window sell-side rows (best-effort), for revision calc

DISPLAY/CONTEXT-ONLY (registered ``pending`` in china_signal_lab) — collected + accruing (report_rc
history is the point); not yet surfaced or scored, awaiting a Phase-0 validation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from lib import config
from collectors import tushare_client as tc

log = logging.getLogger("tushare_forecast")

OUT = config.data_dir() / "tushare" / "forecast.parquet"
OUT_HIST = config.data_dir() / "tushare" / "forecast_hist.parquet"
OUT_RC = config.data_dir() / "tushare" / "report_rc.parquet"
_FIELDS = "ts_code,ann_date,end_date,type,p_change_min,p_change_max"

# 业绩预告 type → guidance direction. Positive = improving earnings, negative = deteriorating.
_POS_TYPES = {"预增", "略增", "扭亏", "续盈", "预盈", "减亏"}
_NEG_TYPES = {"预减", "略减", "首亏", "续亏", "预亏", "增亏"}


def _guidance_score(typ, p_min, p_max) -> float | None:
    """Signed [-1,1] earnings-guidance surprise: type direction × magnitude from the guided net-profit
    %-change midpoint (base 0.5 so a directional type still scores; +0.5 scaled by |Δ%|/50). None for
    an unmapped/neutral type."""
    sign = 1 if str(typ or "") in _POS_TYPES else (-1 if str(typ or "") in _NEG_TYPES else 0)
    if sign == 0:
        return None
    mids = [float(x) for x in (p_min, p_max) if isinstance(x, (int, float)) and x == x]
    mag = min(1.0, abs(sum(mids) / len(mids)) / 50.0) if mids else 0.0
    return round(max(-1.0, min(1.0, sign * (0.5 + 0.5 * mag))), 3)


def _accrue_hist(df) -> None:
    """Append {ticker, ann_date, guidance_score} to the announcement history, deduped on ticker+ann_date."""
    new = df[["ticker", "ann_date", "guidance_score"]].dropna(subset=["guidance_score"]).copy()
    new["ann_date"] = new["ann_date"].astype(str)
    if new.empty:
        return
    if OUT_HIST.exists():
        try:
            new = pd.concat([pd.read_parquet(OUT_HIST), new], ignore_index=True)
        except Exception:  # noqa: BLE001
            pass
    new = new.drop_duplicates(subset=["ticker", "ann_date"], keep="last")
    OUT_HIST.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(OUT_HIST, index=False)


def _window(days: int) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=days)).strftime("%Y%m%d"), now.strftime("%Y%m%d")


def _recent_periods(n: int = 5) -> list[str]:
    """The most recent ~n quarter-end reporting periods (YYYYMMDD), newest first, including up to
    one quarter ahead (companies PRE-announce guidance before the period actually ends)."""
    now = datetime.now(timezone.utc)
    q_ends = ((3, 31), (6, 30), (9, 30), (12, 31))
    fut = (now + timedelta(days=100)).strftime("%Y%m%d")
    cand = [f"{y}{m:02d}{d:02d}" for y in range(now.year - 2, now.year + 2) for (m, d) in q_ends]
    return sorted([c for c in cand if c <= fut], reverse=True)[:n]


def refresh() -> int:
    if not tc.enabled():
        return 0
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    fresh = OUT.exists()
    if fresh:
        try:
            fresh = str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today
        except Exception:  # noqa: BLE001
            fresh = False
    if fresh:
        return 0
    # forecast needs ann_date / ts_code / period — pull the recent quarter-end periods whole-market
    # (forecast_vip @ 5000积分) and combine; keep the latest guidance per name.
    frames = []
    for p in _recent_periods():
        d = tc.query("forecast_vip", period=p, fields=_FIELDS)
        if d is not None and len(d):
            frames.append(d)
    df = pd.concat(frames, ignore_index=True) if frames else None
    n = 0
    if df is not None and len(df):
        df = df.rename(columns={"ts_code": "ticker"}).dropna(subset=["ticker", "ann_date"])
        for c in ("p_change_min", "p_change_max"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["guidance_score"] = [_guidance_score(t, lo, hi) for t, lo, hi in
                                zip(df.get("type"), df.get("p_change_min"), df.get("p_change_max"))]
        # ACCRUE the full announcement history (all rows, deduped on ticker+ann_date) → the substrate
        # for the china_validation `guidance` family. Append-only across builds (events are PIT-stamped).
        _accrue_hist(df)
        # snapshot = the LATEST guidance per name (drop undated already done; NaN can't win keep='last')
        snap = df.sort_values("ann_date").drop_duplicates(subset=["ticker"], keep="last")
        snap["asof"] = today
        keep = ["ticker", "type", "p_change_min", "p_change_max", "guidance_score",
                "end_date", "ann_date", "asof"]
        out = snap[[c for c in keep if c in snap.columns]]
        OUT.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(OUT, index=False)
        n = len(out)
        log.info("tushare forecast: wrote %s (%d names)", OUT, n)
    else:
        log.warning("tushare forecast: no forecast rows")

    # report_rc — best-effort (1 call/hour); store raw for the future revision leg
    try:
        rstart, rend = _window(30)
        rc = tc.query("report_rc", _retries=0, start_date=rstart, end_date=rend)
        if rc is not None and len(rc):
            rc = rc.rename(columns={"ts_code": "ticker"})
            rc["asof"] = today
            OUT_RC.parent.mkdir(parents=True, exist_ok=True)
            rc.to_parquet(OUT_RC, index=False)
            log.info("tushare report_rc: wrote %s (%d rows, raw)", OUT_RC, len(rc))
    except Exception as e:  # noqa: BLE001 — premium/throttled, never fatal
        log.info("tushare report_rc skipped (%s)", e)
    return n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
