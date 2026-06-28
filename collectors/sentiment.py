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
from datetime import datetime, timezone

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

    # AAII's bot filter 403s short/"research" agents — a full browser UA passes.
    _UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["aaii_url"], retries=self.cfg["retries"],
                          headers={"User-Agent": self._UA})
        if "Pardon Our Interruption" in r.text or "px-captcha" in r.text:
            # PerimeterX bot wall (common from datacenter IPs) — 200 but no data.
            # Surface it cleanly; expected_failure routes this to a graceful "blocked".
            raise ValueError("AAII served a bot-challenge interstitial (no data)")
        for t in pd.read_html(io.StringIO(r.text)):
            t = self._promote_header(t)
            cols = [str(c).strip().lower() for c in t.columns]
            if "bullish" not in " ".join(cols) or len(t) < 1:
                continue
            t.columns = cols
            date_col = next((c for c in cols if "date" in c or "week" in c), cols[0])
            out = pd.DataFrame(index=self._parse_dates(t[date_col]))
            for fld in ("bullish", "neutral", "bearish"):
                col = next((c for c in cols if fld in c), None)
                if col:
                    out[f"aaii_{fld}"] = (t[col].astype(str).str.rstrip("%")
                                          .pipe(pd.to_numeric, errors="coerce").to_numpy())
            out = out[out.index.notna()].dropna(how="all")
            if "aaii_bullish" in out:
                out = out.dropna(axis=0, subset=["aaii_bullish"])
            if len(out):
                return {"aaii": out.sort_index()}
        raise ValueError("AAII results table not found — page structure changed or paywalled")

    @staticmethod
    def _promote_header(t: pd.DataFrame) -> pd.DataFrame:
        """AAII's free table ships its header as the first DATA row (read_html then
        sees numeric 0..n column names). Promote it when the labels live in row 0."""
        if "bullish" in " ".join(str(c).lower() for c in t.columns) or t.empty:
            return t
        first = [str(v).strip().lower() for v in t.iloc[0].tolist()]
        if "bullish" in " ".join(first):
            t = t.iloc[1:].copy()
            t.columns = first
        return t

    @staticmethod
    def _parse_dates(s: pd.Series) -> pd.DatetimeIndex:
        """Parse AAII's year-less reported dates ('Jun 24'). pandas/dateutil default a
        missing year to 0001, so stamp the current year onto year-less rows, then roll
        any date that lands in the future back one year (a December row read in
        January)."""
        raw = s.astype(str).str.strip()
        yr = datetime.now(timezone.utc).year
        stamped = raw.where(raw.str.contains(r"\b\d{4}\b"), raw + f" {yr}")
        d = pd.to_datetime(stamped, errors="coerce", format="mixed")
        cutoff = pd.Timestamp(datetime.now(timezone.utc).date()) + pd.Timedelta(days=3)
        d = d.mask(d.notna() & (d > cutoff), d - pd.offsets.DateOffset(years=1))
        return pd.DatetimeIndex(d)
