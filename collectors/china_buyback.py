"""Share-buyback program tracker for A-share names (keyless, via akshare/Eastmoney).

Buybacks (回购) are the cleanest A-share confirmer of issuer conviction: a board
committing real cash to retire shares, and — for SOE / 央企 names — the mechanical
seed of the 中特估 ("China Special Valuation") re-rating thesis (state-backed buyback
of a low-PB name). One WHOLE-MARKET Eastmoney call returns every announced program:

  stock_repurchase_em()  -> per name: 计划回购金额区间 (planned spend), 已回购金额
                            (amount executed so far), 占公告前一日总股本比例 (% of total
                            share capital), and 实施进度 (program status: 实施中/已完成/…).

Stored compactly under data/china_buyback/buyback.parquet
({ticker, name, plan_amt_yi, done_amt_yi, pct_shares, progress, asof}), refreshed
every build (one cheap call, no per-name loop). Amounts are converted to 亿 (/1e8).

EVIDENCE STORE (append-only, keep-first) — separate from the current-program snapshot:
  data/china_buyback/buyback_hist.parquet — one row per (ticker, event_date, plan_key)
  event_date is the strongest vendor PUBLICATION date (公告/披露). Plan start/end is
  NOT a publication date and is never copied into known_at. If publication timing is
  absent or ambiguous, event_date is empty and first_seen is the evidence clock.
  known_at is always the collection first_seen — never an inferred historical date.

CONFIRMER, NOT A STANDALONE SIGNAL. A buyback is corroborating evidence of value /
support, capped as a confirmer leg downstream (engine side), never a buy ranking on
its own — A-share single-factor edges are not validated (research/CHINA_HK_STOCK_SIGNALS.md).
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

import pandas as pd

from lib import config
from collectors.china_analyst import to_ticker, _num
from collectors import _first_seen_store as fss

log = logging.getLogger("china_buyback")

OUT = config.data_dir() / "china_buyback" / "buyback.parquet"
OUT_HIST = config.data_dir() / "china_buyback" / "buyback_hist.parquet"
SOURCE = "akshare.stock_repurchase_em"

HIST_COLUMNS = (
    "ticker",
    "name",
    "event_date",
    "event_date_kind",
    "plan_start",
    "plan_amt_yi",
    "done_amt_yi",
    "pct_shares",
    "progress",
    "plan_key",
    "first_seen",
    "fetched_at",
    "asof",
    "known_at",
    "schema_version",
    "source",
)
HIST_KEY = ["ticker", "event_date", "plan_key"]

# Publication / notice columns only. Plan start/end and "latest update" execution
# dates are NOT publication timing and must not become event_date or known_at.
_PUB_DATE_NEEDLES = (
    ("最新公告日期",),
    ("公告日期",),
    ("披露日期",),
    ("NEWEST_NOTICE_DATE",),
    ("NOTICE_DATE",),
)
_PLAN_START_NEEDLES = (
    ("起始日期",),
    ("开始日期",),
    ("回购起始",),
    ("START_DATE",),
)


def _col(cols: list[str], *needles: str) -> str | None:
    """First column whose name contains ALL the given substrings (akshare names drift
    across versions, so we match by substring, never exact equality)."""
    for c in cols:
        s = str(c)
        if all(n in s for n in needles):
            return c
    return None


def _normalize_date(value) -> str:
    """Vendor date → YYYY-MM-DD, or '' if unparseable. Never invents a date."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    s = str(value).strip()
    if not s or s in ("nan", "None", "NaT", "--", "—"):
        return ""
    try:
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _first_matching_col(cols: list[str], needle_groups: tuple[tuple[str, ...], ...]) -> str | None:
    for needles in needle_groups:
        hit = _col(cols, *needles)
        if hit:
            return hit
    return None


def vendor_publication_date(cols: list[str], row) -> tuple[str, str]:
    """(event_date, kind). kind is 'vendor_publication' or 'absent'.

    Only announcement/disclosure columns qualify. A plan start/end date is
    returned nowhere — using it as known_at would fabricate PIT knowledge.
    """
    pub_col = _first_matching_col(cols, _PUB_DATE_NEEDLES)
    if pub_col is None:
        return "", "absent"
    event_date = _normalize_date(row.get(pub_col))
    if not event_date:
        return "", "absent"
    return event_date, "vendor_publication"


def _plan_key(plan_amt_yi) -> str:
    """Stable-enough program identity when the vendor has no program id.

    Rounded plan amount (or '') — progress updates on the same plan do not mint
    a new key; a later program with a different plan size does.
    """
    if plan_amt_yi is None:
        return ""
    try:
        return f"{float(plan_amt_yi):.4f}"
    except (TypeError, ValueError):
        return ""


def hist_rows_from_table(df: pd.DataFrame, *, fetched_at: str, asof: str) -> list[dict]:
    """Evidence rows from the vendor table. known_at is always first_seen."""
    cols = list(df.columns)
    code_col = _col(cols, "代码")
    name_col = _col(cols, "简称") or _col(cols, "名称")
    prog_col = _col(cols, "进度")
    plan_col = _col(cols, "计划回购金额", "上限") or _col(cols, "计划回购金额")
    done_col = _col(cols, "已回购金额")
    pct_col = _col(cols, "总股本比例", "上限") or _col(cols, "总股本比例")
    start_col = _first_matching_col(cols, _PLAN_START_NEEDLES)
    if not code_col:
        return []
    rows: list[dict] = []
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_col))
        if not t:
            continue
        plan = _num(r.get(plan_col)) if plan_col else None
        done = _num(r.get(done_col)) if done_col else None
        pct = _num(r.get(pct_col)) if pct_col else None
        plan_amt_yi = (plan / 1e8) if plan is not None else None
        event_date, kind = vendor_publication_date(cols, r)
        rows.append({
            "ticker": t,
            "name": str(r.get(name_col) or "") if name_col else "",
            "event_date": event_date,
            "event_date_kind": kind,
            "plan_start": _normalize_date(r.get(start_col)) if start_col else "",
            "plan_amt_yi": plan_amt_yi,
            "done_amt_yi": (done / 1e8) if done is not None else None,
            "pct_shares": pct,
            "progress": str(r.get(prog_col) or "") if prog_col else "",
            "plan_key": _plan_key(plan_amt_yi),
            "first_seen": fetched_at,
            "fetched_at": fetched_at,
            "asof": asof,
            "known_at": fetched_at,  # collection clock; NEVER the vendor event_date
            "schema_version": fss.SCHEMA_VERSION,
            "source": SOURCE,
        })
    return rows


def accrue_buyback_hist(rows: list[dict]) -> int:
    """Append-only keep-first on (ticker, event_date, plan_key). Returns net-new keys."""
    return fss.accrue_keep_first(
        OUT_HIST, rows, columns=HIST_COLUMNS, key=HIST_KEY,
        sort_by=["event_date", "ticker", "plan_key"],
    )


def fetch_table() -> pd.DataFrame | None:
    """The whole-market Eastmoney buyback table. Returns None on failure."""
    import akshare as ak
    try:
        df = ak.stock_repurchase_em()
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.warning("china buyback: stock_repurchase_em failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def refresh() -> int:
    """Fetch the whole-market buyback table once and bake a compact per-ticker row.
    Best-effort: returns the number of names written (0 on failure). Overwrites the
    cache each run (the source is a same-day snapshot, fully re-fetchable). Idempotent
    within a UTC day: a cache already stamped with today's date is left untouched."""
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today:
                log.info("china buyback: cache already fresh (%s)", today)
                return 0
        except Exception:  # noqa: BLE001
            pass
    df = fetch_table()
    if df is None:
        return 0
    cols = list(df.columns)
    code_col = _col(cols, "代码")
    name_col = _col(cols, "简称") or _col(cols, "名称")
    prog_col = _col(cols, "进度")
    # plan amount: prefer the upper bound of 计划回购金额区间, else any plan-amount col
    plan_col = _col(cols, "计划回购金额", "上限") or _col(cols, "计划回购金额")
    done_col = _col(cols, "已回购金额")
    # % of total share capital: prefer the upper bound of 占…总股本比例
    pct_col = _col(cols, "总股本比例", "上限") or _col(cols, "总股本比例")
    if not code_col:
        log.warning("china buyback: no code column in %s", cols)
        return 0
    rows = []
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_col))
        if not t:
            continue
        plan = _num(r.get(plan_col)) if plan_col else None
        done = _num(r.get(done_col)) if done_col else None
        pct = _num(r.get(pct_col)) if pct_col else None
        rows.append({
            "ticker": t,
            "name": str(r.get(name_col) or "") if name_col else "",
            "plan_amt_yi": (plan / 1e8) if plan is not None else None,
            "done_amt_yi": (done / 1e8) if done is not None else None,
            "pct_shares": pct,
            "progress": str(r.get(prog_col) or "") if prog_col else "",
        })
    if not rows:
        return 0
    fetched_at = datetime.now(timezone.utc).isoformat()
    n_hist = accrue_buyback_hist(hist_rows_from_table(df, fetched_at=fetched_at, asof=today))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out["asof"] = today
    out.to_parquet(OUT, index=False)
    log.info("china buyback: wrote %s (%d names, asof %s); hist +%d -> %s",
             OUT, len(out), today, n_hist, OUT_HIST)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
