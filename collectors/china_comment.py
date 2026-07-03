"""千股千评 per-name market read (keyless, via akshare/Eastmoney).

Eastmoney's "千股千评" desk is the single highest-value free per-name A-share feed:
one WHOLE-MARKET call returns, for every name, a compact retail-vs-institution read
that has no clean US analog —

  stock_comment_em()  -> per name:
      关注指数  (attention index, retail eyeball heat 0-100)
      机构参与度 (institutional participation, fraction 0-1 of float held by 机构)
      主力成本  (main-force / smart-money average cost basis, vs the live price)
      综合得分  (Eastmoney composite score 0-100)
      目前排名  (current popularity rank, lower = hotter)
      上升     (rank delta vs prior day, +ve = climbing the board)

Stored two ways under data/china_comment/:
  detail.parquet         -> the latest snapshot (one row per name + asof), re-fetchable
  attention_hist.parquet -> an APPENDED {ticker,date,attention} log, deduped on
                            ticker+date, so the engine can read an attention VELOCITY
                            (today's heat vs its trailing average) — the only piece that
                            needs history accrued across builds.

Derived reads (computed downstream in engine/china_extras.comment):
  inst_vs_retail       = clip((机构参与度·100 − 50)/50, -1, 1)
  main_force_cost_gap  = (最新价/主力成本 − 1)·100      (price above smart-money cost = room used up)
  comment_score        = .4·clip((综合得分−50)/30,-1,1) + .4·inst_vs_retail
                         + .2·sign(上升)·clip(|上升|/200, 0, 1)

DISPLAY-ONLY context. Eastmoney's composite/attention are crowd-sentiment reads, not a
validated A-share timing edge — surfaced as a retail-vs-institution backdrop, never a
buy/sell ranking. Column names DRIFT across akshare versions, so every field is matched
by Chinese SUBSTRING (关注指数 / 机构参与度 / 主力成本 / 综合得分 / 目前排名 / 上升),
never by exact column equality.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from lib import config
from collectors import _drip
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_comment")

OUT = config.data_dir() / "china_comment" / "detail.parquet"
HIST = config.data_dir() / "china_comment" / "attention_hist.parquet"
# Append-only PIT history for the full per-name snapshot (detail, not just attention).
# Keyed by (asof, ticker); lets the engine back-test how inst_participation /
# main_cost_gap / score moved across days. detail.parquet remains the unchanged
# snapshot read by every existing consumer.
DETAIL_HIST = config.data_dir() / "china_comment" / "detail_hist.parquet"


def _col(cols: list, *needles: str):
    """First column whose name CONTAINS any needle (substring match, version-proof)."""
    for c in cols:
        s = str(c)
        if any(n in s for n in needles):
            return c
    return None


def fetch_table() -> pd.DataFrame | None:
    """The whole-market 千股千评 table. Returns None on failure (never raises)."""
    import akshare as ak
    try:
        df = ak.stock_comment_em()
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.warning("china comment: stock_comment_em failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def _parse(df: pd.DataFrame) -> list[dict]:
    """Flatten the table into per-ticker rows via SUBSTRING column matching."""
    cols = list(df.columns)
    code_c = _col(cols, "代码")
    name_c = _col(cols, "名称")
    price_c = _col(cols, "最新价")
    att_c = _col(cols, "关注指数")
    inst_c = _col(cols, "机构参与度")
    cost_c = _col(cols, "主力成本")
    score_c = _col(cols, "综合得分")
    rank_c = _col(cols, "目前排名", "排名")
    delta_c = _col(cols, "上升")
    if not code_c:
        return []
    rows: list[dict] = []
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_c))
        if not t:
            continue
        inst = _num(r.get(inst_c)) if inst_c else None
        # 机构参与度 is a fraction (0-1) in current akshare; normalise to a 0-100 percent.
        if inst is not None and inst <= 1.5:
            inst = inst * 100.0
        rows.append({
            "ticker": t,
            "name": str(r.get(name_c) or "").strip() if name_c else "",
            "attention": _num(r.get(att_c)) if att_c else None,
            "inst_participation": inst,
            "main_cost": _num(r.get(cost_c)) if cost_c else None,
            "score": _num(r.get(score_c)) if score_c else None,
            "rank": _num(r.get(rank_c)) if rank_c else None,
            "rank_delta": _num(r.get(delta_c)) if delta_c else None,
            "price": _num(r.get(price_c)) if price_c else None,
        })
    return rows


def _accrue_hist(rows: list[dict], date: str) -> None:
    """Append today's {ticker,date,attention} to the history log, deduped on ticker+date."""
    new = pd.DataFrame(
        [{"ticker": r["ticker"], "date": date, "attention": r["attention"]}
         for r in rows if r.get("attention") is not None]
    )
    if new.empty:
        return
    if HIST.exists():
        try:
            old = pd.read_parquet(HIST)
            new = pd.concat([old, new], ignore_index=True)
        except Exception:  # noqa: BLE001 — corrupt cache: start over from today
            pass
    new = new.drop_duplicates(subset=["ticker", "date"], keep="last")
    HIST.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(HIST, index=False)


def refresh() -> int:
    """Bake the latest 千股千评 snapshot + accrue the attention-velocity history.
    Best-effort: returns the number of names written (0 on failure). Idempotent within a
    UTC day — a cache already stamped with today's date is left untouched."""
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today:
                log.info("china comment: cache already fresh (%s)", today)
                return 0
        except Exception:  # noqa: BLE001
            pass
    df = fetch_table()
    if df is None:
        return 0
    rows = _parse(df)
    if not rows:
        return 0
    # The trading day the read pertains to (for the velocity log); fall back to UTC date.
    trade_date = today
    dcol = _col(list(df.columns), "交易日", "日期")
    if dcol is not None:
        try:
            v = pd.to_datetime(df[dcol].dropna().iloc[0])
            trade_date = v.strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            pass
    _accrue_hist(rows, trade_date)
    out = pd.DataFrame(rows)
    out["asof"] = today
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("china comment: wrote %s (%d names, asof %s)", OUT, len(out), today)
    # Append to the PIT detail history (additive; never overwrites the snapshot consumers read).
    try:
        hist_rows = out.to_dict("records")
        _drip.append_snapshot(DETAIL_HIST, hist_rows, date_col="asof")
        log.info("china comment: appended detail history %s (asof %s)", DETAIL_HIST, today)
    except Exception as e:  # noqa: BLE001 — history is telemetry, never fatal
        log.warning("china comment: detail history append failed (%s)", e)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
