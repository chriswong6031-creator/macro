"""PBoC corridor & liquidity series — the missing central-bank legs for the Policy Watch.

KEYLESS · DISPLAY/CONTEXT-ONLY. The China Policy Watch (engine/china_policy_watch.py)
reads LPR 1Y/5Y and RRR from the existing china_macro store; this collector adds the
remaining reliable, globally-reachable PBoC legs:

  fx_reserves  — SAFE FX reserves + PBoC gold reserves (monthly)  [macro_china_fx_gold]
  repo_rates   — interbank repo fixings FR001/FR007/FR014 (daily) [repo_rate_query]
  cny_fix      — BOC/SAFE USD reference rate -> USD/CNY (daily)    [currency_boc_safe]

Each series is isolated in its own try/except so one drifting endpoint never sinks the
others; akshare is imported LAZILY inside fetch() so a missing dep surfaces as a tracked
adapter failure rather than silently removing the adapter. The current MLF / 7-day OMO
administered RATE is not exposed cleanly by any keyless source (PBoC HTML only), so the
corridor uses LPR + RRR + the FR007 money-market rate (a clean DR007 analog) instead.
See research/CHINA_INTEL_POWERHOUSE.md §3.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


def _col(df: pd.DataFrame, *needles: str):
    """First column whose name contains any needle (akshare Chinese column drift)."""
    for n in needles:
        for c in df.columns:
            if n in str(c):
                return c
    return None


def _parse_month(v) -> pd.Timestamp | None:
    s = str(v)
    m = re.search(r"(\d{4})\D+(\d{1,2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        try:
            return pd.Timestamp(year=y, month=mo, day=1)
        except ValueError:
            return None
    try:
        return pd.Timestamp(pd.to_datetime(s))
    except Exception:  # noqa: BLE001
        return None


class ChinaPbocAdapter(Adapter):
    name = "china_pboc"
    group = "china_pboc"
    stale_after_days = 40   # FX reserves are monthly; repo/cny are daily but tolerate gaps

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001 — tracked adapter failure
            raise RuntimeError(f"china_pboc: akshare unavailable ({e})") from e

        out: dict[str, pd.DataFrame] = {}
        errors: list[str] = []

        # --- FX reserves + gold (monthly) ----------------------------------- #
        try:
            df = ak.macro_china_fx_gold()
            mcol = _col(df, "月份", "月", "日期")
            fx = _col(df, "国家外汇储备-数值", "外汇储备-数值", "外汇储备")
            gold = _col(df, "黄金储备-数值", "黄金储备")
            rows = {}
            for _, r in df.iterrows():
                d = _parse_month(r[mcol])
                if d is None:
                    continue
                rows[d] = {"fx_reserves": pd.to_numeric(r.get(fx), errors="coerce"),
                           "gold_reserves": pd.to_numeric(r.get(gold), errors="coerce")}
            if rows:
                out["fx_reserves"] = pd.DataFrame.from_dict(rows, orient="index").sort_index()
        except Exception as e:  # noqa: BLE001 — per-series isolation
            errors.append(f"fx_reserves({e})")

        # --- interbank repo fixings FR001/FR007/FR014 (daily) --------------- #
        try:
            df = ak.repo_rate_query(symbol="回购定盘利率")
            dcol = _col(df, "date", "日期")
            df = df.copy()
            df.index = pd.to_datetime(df[dcol], errors="coerce")
            keep = {c: c for c in ("FR001", "FR007", "FR014") if c in df.columns}
            sub = df[list(keep)].apply(pd.to_numeric, errors="coerce").dropna(how="all")
            sub = sub[~sub.index.isna()]
            if not sub.empty:
                out["repo_rates"] = sub.sort_index()
        except Exception as e:  # noqa: BLE001
            errors.append(f"repo_rates({e})")

        # --- BOC/SAFE USD reference -> USD/CNY (daily) ---------------------- #
        try:
            df = ak.currency_boc_safe()
            dcol = _col(df, "日期", "date")
            usd = _col(df, "美元")
            s = pd.to_numeric(df[usd], errors="coerce")
            # BOC reference is RMB per 100 USD (~710); normalize to USD/CNY (~7.1)
            s = s.where(s < 50, s / 100.0)
            ser = pd.DataFrame({"usd_cny": s.values},
                               index=pd.to_datetime(df[dcol], errors="coerce"))
            ser = ser[~ser.index.isna()].dropna().sort_index()
            if not ser.empty:
                out["cny_fix"] = ser
        except Exception as e:  # noqa: BLE001
            errors.append(f"cny_fix({e})")

        if not out:
            raise RuntimeError(f"china_pboc: no series fetched ({'; '.join(errors)})")
        if errors:
            log.warning("china_pboc partial: %s", "; ".join(errors))
        log.info("china_pboc: fetched %s", list(out))
        return out
