"""Farside Investors — US spot-Bitcoin-ETF daily flow table (free, keyless).

The canonical daily per-fund + total net-flow table (US$m) since the 2024-01-11
launch. Richer than the bgeo aggregate etf-flow-btc: per issuer (IBIT/FBTC/GBTC/…),
fresher, and longer. Scraped HTML → deliberately fail-safe: a fetch/parse failure
raises and the runner records it, leaving the bgeo series as the etf_flow fallback.

Table conventions: parentheses = outflow (negative), "-" = fund not trading yet,
values in US$ millions. The first row is blank and the last row is a cumulative
"Total" — both dropped here.

Output: one frame `etf_flows` with a column per fund ticker (lower-cased) + `total`,
daily-indexed.
"""
from __future__ import annotations

import io
import logging

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


def _num(x) -> float:
    """Parse a Farside cell: '(95.1)' -> -95.1, '1,234' -> 1234, '-'/'' -> NaN."""
    if x is None:
        return np.nan
    s = str(x).strip().replace(",", "").replace("$", "")
    if s in ("", "-", "nan", "NaN", "—"):
        return np.nan
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        v = float(s)
    except ValueError:
        return np.nan
    return -v if neg else v


def parse_table(html: str, funds: list[str]) -> pd.DataFrame:
    """Pure parser: Farside all-data HTML -> daily per-fund + total flow frame (US$m)."""
    tables = pd.read_html(io.StringIO(html))
    if not tables:
        raise ValueError("farside: no tables found")
    # the flow table is by far the widest/tallest (per-fund columns × ~600 days)
    t = max(tables, key=lambda x: x.shape[0] * x.shape[1])
    t.columns = [(" ".join(str(c) for c in col) if isinstance(col, tuple) else str(col)).strip()
                 for col in t.columns]
    date_col = t.columns[0]
    dt = pd.to_datetime(t[date_col], format="%d %b %Y", errors="coerce")
    t = t[dt.notna()].copy()                    # drop the blank header + cumulative "Total" rows
    t.index = dt[dt.notna()]
    t.index.name = "date"

    want = {f.upper(): f for f in funds}
    want["TOTAL"] = "total"
    out = {}
    for col in t.columns:
        key = col.strip().upper()
        if key in want:
            out[want[key]] = t[col].map(_num)
    if "total" not in out:
        raise ValueError("farside: Total column not found (table layout changed?)")
    df = pd.DataFrame(out).sort_index()
    return df[~df.index.duplicated(keep="last")]


class FarsideAdapter(Adapter):
    name = "farside"
    group = "farside"
    stale_after_days = 4

    def __init__(self) -> None:
        self.cfg = config.load()["farside"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["url"], retries=self.cfg["retries"], timeout=40,
                          headers={"User-Agent": self.cfg["user_agent"]})
        df = parse_table(r.text, self.cfg["funds"])
        if df.empty or "total" not in df.columns:
            raise ValueError("farside: parsed an empty/invalid flow table")
        return {"etf_flows": df}
