"""S&P 500 internal breadth, computed from constituents (not scraped).

- Constituents: Wikipedia table (current members — survivorship caveat:
  fine for the live signal, biased for backtests; see LIMITATIONS.md).
- Closes: yfinance in batches. The raw close matrix is a local cache
  (data/breadth/_closes_cache.parquet, gitignored — in CI restored via
  actions/cache; on miss it is re-downloaded, ~2 min). Only the small
  computed aggregate series is committed to the repo.
- Outputs (data/breadth/breadth.parquet):
    pct_above_50, pct_above_200  — % of members above 50/200DMA
    nh, nl                       — counts of 252d new highs / lows
    adv, dec, ad_line            — daily up/down counts + cumulative A-D line
    n_members                    — denominator that day
"""
from __future__ import annotations

import io
import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class BreadthAdapter(Adapter):
    name = "breadth"
    group = "breadth"

    def __init__(self) -> None:
        self.cfg = config.load()["breadth"]
        self.ycfg = config.load()["yahoo"]
        self.cache_path = config.data_dir() / "breadth" / "_closes_cache.parquet"

    def constituents(self) -> pd.DataFrame:
        r = self.http_get(self.cfg["constituents_url"], retries=3,
                          headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            if "Symbol" in t.columns:
                t = t.rename(columns={"Symbol": "symbol", "Security": "name",
                                      "GICS Sector": "sector"})
                t["symbol"] = t["symbol"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
                return t[["symbol", "name", "sector"]]
        raise ValueError("constituents table not found on Wikipedia page")

    def _download_closes(self, tickers: list[str], period: str) -> pd.DataFrame:
        bs = self.ycfg["batch_size"]
        parts: list[pd.DataFrame] = []
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            for attempt in range(self.ycfg["retries"]):
                try:
                    df = yf.download(batch, period=period, auto_adjust=True,
                                     progress=False, group_by="column", threads=True)
                    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
                    parts.append(closes)
                    break
                except Exception as e:  # noqa: BLE001
                    wait = self.ycfg["backoff_base_s"] * (2 ** attempt)
                    log.warning("breadth batch %d failed (%s); retry in %.0fs", i // bs, e, wait)
                    time.sleep(wait)
            time.sleep(1)
        if not parts:
            raise RuntimeError("no constituent closes downloaded")
        wide = pd.concat(parts, axis=1)
        wide = wide.loc[:, ~wide.columns.duplicated()]
        return wide.sort_index()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        members = self.constituents_checked(self.constituents())
        tickers = members["symbol"].tolist()

        if full_history:
            closes = self._download_closes(tickers, "max")
        else:
            closes = None
            if self.cache_path.exists():
                cached = pd.read_parquet(self.cache_path)
                # refresh tail; full re-pull if cache is stale beyond the overlap
                age = (pd.Timestamp.utcnow().tz_localize(None) - cached.index.max()).days
                if age <= 14:
                    fresh = self._download_closes(tickers, "1mo")
                    closes = fresh.combine_first(cached)
            if closes is None:
                days = self.cfg["lookback_days_live"]
                closes = self._download_closes(tickers, f"{max(1, days // 365 + 1)}y")
            cutoff = closes.index.max() - pd.Timedelta(days=self.cfg["lookback_days_live"] + 30)
            closes = closes[closes.index >= cutoff]

        # coverage sanity: a half-empty matrix silently poisons every ratio
        live_cols = closes.dropna(axis=1, how="all").shape[1]
        if live_cols < len(tickers) * 0.8:
            raise RuntimeError(f"breadth closes too sparse: {live_cols}/{len(tickers)}")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_history:
            closes.to_parquet(self.cache_path)
        # constituents list is reference data, not a time series — written directly
        members.set_index("symbol").to_parquet(self.cache_path.parent / "constituents.parquet")

        return {"breadth": self.compute(closes)}

    def compute(self, closes: pd.DataFrame) -> pd.DataFrame:
        w50, w200 = self.cfg["ma_windows"]
        nhw = self.cfg["nhnl_window"]
        valid = closes.notna()
        ma50 = closes.rolling(w50, min_periods=w50).mean()
        ma200 = closes.rolling(w200, min_periods=w200).mean()
        out = pd.DataFrame(index=closes.index)
        out["n_members"] = valid.sum(axis=1)
        out["pct_above_50"] = 100 * (closes > ma50).sum(axis=1) / ma50.notna().sum(axis=1)
        out["pct_above_200"] = 100 * (closes > ma200).sum(axis=1) / ma200.notna().sum(axis=1)
        roll_hi = closes.rolling(nhw, min_periods=nhw).max()
        roll_lo = closes.rolling(nhw, min_periods=nhw).min()
        out["nh"] = (closes >= roll_hi).sum(axis=1)
        out["nl"] = (closes <= roll_lo).sum(axis=1)
        chg = closes.diff()
        out["adv"] = (chg > 0).sum(axis=1)
        out["dec"] = (chg < 0).sum(axis=1)
        out["ad_line"] = (out["adv"] - out["dec"]).cumsum()
        out = out.dropna(subset=["pct_above_50"])
        # partial rows (e.g. an in-progress trading day where only a handful of
        # tickers have printed) would poison every ratio — drop them
        return out[out["n_members"] >= out["n_members"].rolling(20, min_periods=1).max() * 0.8]

    def constituents_checked(self, members: pd.DataFrame) -> pd.DataFrame:
        if members.empty or len(members) < 400:
            raise ValueError(f"constituents list suspicious: {len(members)} rows")
        return members


def breadth_summary(br: pd.DataFrame | None, full: bool) -> dict | None:
    """Latest-row breadth read for the regional dashboard cards (China / HK / Canada).

    Pure function of a computed breadth frame (the 8-column output of
    ``BreadthAdapter.compute``). Returns the fields the cards already used plus a
    plain-language participation read — ``state`` (broad / thin / mixed), ``tone``,
    and ``net_nh`` — mirroring the US S&P-1500 scorecard's thresholds so the regional
    pages answer the same "how many stocks are actually participating" question.
    DISPLAY-ONLY (never scored). ``full`` flags whether the source was the full
    searchable universe (True) or the curated large-cap gauge (False)."""
    if br is None or br.empty:
        return None
    last = br.iloc[-1]
    pa50 = float(last.get("pct_above_50", float("nan")))
    nh, nl = int(last.get("nh", 0) or 0), int(last.get("nl", 0) or 0)
    net_nh = nh - nl
    # same thresholds as build_site._breadth_read (the US scorecard) — % above the
    # 50-day line is normalized 0-100 so the bands port across markets unchanged
    if pa50 >= 60 and net_nh >= 0:
        state, tone = "broad", "pos"
    elif pa50 <= 40 or net_nh < 0:
        state, tone = "thin", "neg"
    else:
        state, tone = "mixed", "muted"
    try:
        chg20 = round(float(br["pct_above_50"].diff(20).iloc[-1]), 1)
    except Exception:  # noqa: BLE001 — short history → no 20d change
        chg20 = 0.0
    return {
        "pct_above_50": round(pa50, 1),
        "pct_above_200": round(float(last.get("pct_above_200", float("nan"))), 1),
        "nh": nh, "nl": nl, "net_nh": net_nh,
        "adv": int(last.get("adv", 0) or 0), "dec": int(last.get("dec", 0) or 0),
        "ad_trend": "up" if br["ad_line"].diff(20).iloc[-1] > 0 else "down",
        "n_members": int(last.get("n_members", 0) or 0),
        "pct50_chg20": chg20,
        "state": state, "tone": tone, "full": bool(full),
        "asof": pd.Timestamp(last.name).strftime("%Y-%m-%d"),
    }
