"""Weekly sentiment: NAAIM exposure index and AAII bull/bear survey.

Both are scrapers with graceful failure — they feed the weekly report's
positioning-extremes section, never the regime engine. AAII's full history is
member-only; the free page exposes recent weeks, which is enough for the
percentile-rank logic once a year of weekly rows has accumulated.
"""
from __future__ import annotations

import io
import logging
import re

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class NaaimAdapter(Adapter):
    name = "sentiment_naaim"
    group = "sentiment"
    stale_after_days = 12  # weekly (Thursday)

    def __init__(self) -> None:
        self.cfg = config.load()["sentiment"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["naaim_url"], retries=self.cfg["retries"],
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        # NAAIM links a dated since-inception XLSX from the page (filename
        # changes weekly) — discover it, then parse the full history
        m = re.search(r'https?://naaim\.org/wp-content/uploads/[^"\']+\.xlsx?', r.text)
        if not m:
            raise ValueError("NAAIM since-inception workbook link not found on page")
        rx = self.http_get(m.group(0), retries=self.cfg["retries"],
                           headers={"User-Agent": "Mozilla/5.0 (research)"})
        raw = pd.read_excel(io.BytesIO(rx.content))
        cols = [str(c).strip().lower() for c in raw.columns]
        raw.columns = cols
        date_col = next(c for c in cols if "date" in c)
        num_col = next((c for c in cols if "mean" in c or "average" in c or "exposure" in c),
                       cols[1])
        df = pd.DataFrame(
            {"naaim_exposure": pd.to_numeric(raw[num_col], errors="coerce").to_numpy()},
            index=pd.to_datetime(raw[date_col], errors="coerce").to_numpy())
        df = df[df.index.notna()].dropna()
        if len(df) < 10:
            raise ValueError(f"NAAIM workbook parsed to only {len(df)} rows")
        return {"naaim": df.sort_index()}


class AaiiAdapter(Adapter):
    name = "sentiment_aaii"
    group = "sentiment"
    stale_after_days = 12  # weekly (Thursday)
    expected_failure = ("AAII blocks non-browser clients (403) — known limitation, "
                        "not used by the regime engine")

    def __init__(self) -> None:
        self.cfg = config.load()["sentiment"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["aaii_url"], retries=self.cfg["retries"],
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            cols = [str(c).strip().lower() for c in t.columns]
            if "bullish" in " ".join(cols) and len(t) >= 1:
                t.columns = cols
                date_col = next((c for c in cols if "date" in c or "week" in c), cols[0])
                out = pd.DataFrame(index=pd.to_datetime(t[date_col], errors="coerce").to_numpy())
                for fld in ("bullish", "neutral", "bearish"):
                    col = next((c for c in cols if fld in c), None)
                    if col:
                        out[f"aaii_{fld}"] = (t[col].astype(str).str.rstrip("%")
                                              .pipe(pd.to_numeric, errors="coerce").to_numpy())
                out = out.dropna(how="all").dropna(axis=0, subset=["aaii_bullish"])
                if len(out):
                    return {"aaii": out.sort_index()}
        raise ValueError("AAII results table not found — page structure changed or paywalled")
