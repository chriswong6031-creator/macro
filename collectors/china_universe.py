"""China A-share SEARCH universe — the broad name set behind the A-Share Analyzer
search box (site/chinastockdata/).

DECOUPLED from collectors/china_breadth.py on purpose. china_breadth is the curated
~80-name large-cap CSI300-style BREADTH/calibration gauge and must stay stable (the
regime engine is tuned on it). This collector instead imports the top-N mainland
A-shares by market cap so "not all Chinese stocks can be searched" stops being true,
WITHOUT perturbing the calibrated engine — exactly how the US side keeps breadth
(S&P 500) separate from its larger search caches (S&P 400/600).

Data planes (both free, verified 2026-06-13):
  * Universe + Chinese names + market-cap ranking : Sina market-center JSON
      (Market_Center.getHQNodeData, node=hs_a, sort=mktcap). One request/page.
  * Close history (5y, for the cycle/ladder engine)  : yfinance (.SS/.SZ), batched.
  * English name + sector (for English search/labels): yfinance get_info, enriched
      once per ticker and CACHED in members.parquet (bounded lookups/run).

Outputs (committed — small; gives the engine CI job the data via git pull, no
fragile cross-job actions/cache):
  data/china_search/closes.parquet   wide [date x ticker] adjusted closes
  data/china_search/members.parquet  index=ticker; name / name_zh / name_en / sector / mktcap_yi
  data/china_search/coverage.parquet 1-row daily time series (n_stocks) for run_status

build_china_library.universe() reads these FIRST so real names win over the
ticker-as-name fallback from the breadth cache.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


def _to_ticker(sina_symbol: str) -> str | None:
    """sh600519 -> 600519.SS ; sz000001 -> 000001.SZ ; bj/others -> None."""
    s = (sina_symbol or "").strip().lower()
    if len(s) < 8:
        return None
    mkt, code = s[:2], s[2:]
    if not code.isdigit():
        return None
    if mkt == "sh":
        return f"{code}.SS"
    if mkt == "sz":
        return f"{code}.SZ"
    return None  # Beijing (bj) etc. — yfinance has no clean feed


def _code_to_ticker(code: str) -> str | None:
    """Convert a bare 6-digit A-share code to a Yahoo Finance ticker.

    Shanghai (6xxxxx, 9xxxxx, 688xxx STAR) → .SS
    Shenzhen (0xxxxx, 3xxxxx ChiNext)       → .SZ
    Beijing / other                          → None (no yfinance feed)
    """
    code = str(code).strip().zfill(6)
    if not code.isdigit() or len(code) != 6:
        return None
    if code[0] in ("6", "9") or code.startswith("688"):
        return f"{code}.SS"
    if code[0] in ("0", "3"):
        return f"{code}.SZ"
    return None  # 8xxxxx / 4xxxxx = Beijing Stock Exchange — skip


class ChinaUniverseAdapter(Adapter):
    name = "china_universe"
    group = "china_search"
    stale_after_days = 7

    def __init__(self) -> None:
        cn = config.load()["china"]
        self.cfg = cn["search_universe"]
        self.ycfg = cn["yahoo"]                 # batch_size / retries / backoff_base_s
        self.dir = config.data_dir() / "china_search"
        self.closes_path = self.dir / "closes.parquet"
        self.members_path = self.dir / "members.parquet"

    # -- universe (Sina) -------------------------------------------------------
    def _sina_universe(self) -> pd.DataFrame:
        """Top-N A-shares by market cap: DataFrame[ticker, name_zh, mktcap_yi]."""
        scfg = self.cfg["sina"]
        size, page_size = int(self.cfg["size"]), int(scfg["page_size"])
        floor_wan = float(self.cfg.get("min_mktcap_yi", 0)) * 1e4   # 亿 -> 万 (Sina mktcap unit)
        pages = (size + page_size - 1) // page_size + 2             # a little headroom for dropped bj/dupes
        rows: list[dict] = []
        seen: set[str] = set()
        for page in range(1, pages + 1):
            params = {"page": page, "num": page_size, "sort": "mktcap", "asc": 0,
                      "node": scfg["node"], "symbol": "", "_s_r_a": "page"}
            r = self.http_get(scfg["url"], retries=self.ycfg["retries"],
                              backoff_base=self.ycfg["backoff_base_s"], timeout=30,
                              params=params, headers={"Referer": scfg["referer"]})
            try:
                data = r.json()
            except Exception:  # noqa: BLE001 — Sina sometimes returns null/garbage on overrun
                data = None
            if not data:
                break
            for d in data:
                t = _to_ticker(str(d.get("symbol", "")))
                if not t or t in seen:
                    continue
                mktcap_wan = float(d.get("mktcap") or 0)
                if mktcap_wan < floor_wan:
                    continue
                seen.add(t)
                rows.append({"ticker": t, "name_zh": str(d.get("name", "")).strip(),
                             "mktcap_yi": round(mktcap_wan / 1e4, 1)})
            if len(rows) >= size:
                break
            time.sleep(0.4)
        out = pd.DataFrame(rows).head(size)
        if len(out) < min(200, size // 2):
            raise RuntimeError(f"sina universe too small: {len(out)} rows (expected ~{size})")
        log.info("china_universe: Sina returned %d ranked A-shares", len(out))
        return out.set_index("ticker")

    # -- closes (yfinance) -----------------------------------------------------
    def _download_closes(self, tickers: list[str], period: str) -> pd.DataFrame:
        bs = int(self.ycfg["batch_size"])
        parts: list[pd.DataFrame] = []
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            for attempt in range(self.ycfg["retries"]):
                try:
                    df = yf.download(batch, period=period, auto_adjust=True,
                                     progress=False, group_by="column", threads=True)
                    if df is None or df.empty:
                        break
                    closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
                    parts.append(closes)
                    break
                except Exception as e:  # noqa: BLE001
                    wait = self.ycfg["backoff_base_s"] * (2 ** attempt)
                    log.warning("china_universe closes batch %d failed (%s); retry in %.0fs",
                                i // bs, e, wait)
                    time.sleep(wait)
            time.sleep(1)
        if not parts:
            raise RuntimeError("china_universe: no closes downloaded")
        wide = pd.concat(parts, axis=1)
        wide = wide.loc[:, ~wide.columns.duplicated()]
        return wide.sort_index()

    # -- English name + sector (yfinance get_info, cached + bounded) ----------
    def _enrich(self, members: pd.DataFrame, prev: pd.DataFrame | None) -> pd.DataFrame:
        """Fill name_en / sector from a cached prior members table; look up at most
        enrich_per_run NEW tickers via yfinance get_info so nightly stays fast."""
        members = members.copy()
        members["name_en"] = ""
        members["sector"] = ""
        if prev is not None:
            for col in ("name_en", "sector"):
                if col in prev.columns:
                    members[col] = members.index.map(prev[col]).fillna("")
        missing = [t for t in members.index
                   if not str(members.at[t, "name_en"]).strip()
                   or not str(members.at[t, "sector"]).strip()]
        budget = int(self.cfg.get("enrich_per_run", 0))
        looked, ok = 0, 0
        for t in missing:
            if looked >= budget:
                break
            looked += 1
            try:
                info = yf.Ticker(t).get_info() or {}
            except Exception:  # noqa: BLE001 — unofficial; degrade to zh-only name
                continue
            en = (info.get("longName") or info.get("shortName") or "").strip()
            sec = (info.get("sector") or "").strip()
            if en:
                members.at[t, "name_en"] = en
            if sec:
                members.at[t, "sector"] = sec
            if en or sec:
                ok += 1
            time.sleep(0.15)
        if missing:
            log.info("china_universe: enriched %d/%d new names (%d still pending, capped at %d/run)",
                     ok, looked, max(0, len(missing) - looked), budget)
        # combined display name -> "English / 中文" (both searchable); zh-only fallback
        def _disp(row: pd.Series) -> str:
            en, zh = str(row["name_en"]).strip(), str(row["name_zh"]).strip()
            return f"{en} / {zh}" if en and zh else (en or zh or row.name)
        members["name"] = members.apply(_disp, axis=1)
        members["sector"] = members["sector"].replace("", "A-share")
        return members

    # -- CSI index constituents (akshare) -------------------------------------
    def _index_constituents(self, symbols: list[str]) -> list[dict]:
        """Fetch constituent lists for named CSI indices (e.g. '000300', '000852')
        via akshare. Returns a list of {ticker, name_zh} dicts. Best-effort: one
        failed index is logged and skipped, never fatal."""
        try:
            import akshare as ak  # noqa: PLC0415 — optional dep
        except ImportError:
            log.warning("china_universe: akshare not installed — CSI index fetch skipped")
            return []
        rows: list[dict] = []
        for sym in symbols:
            try:
                df = ak.index_stock_cons(symbol=sym)
                # akshare column names vary by version — try common patterns
                code_col = next(
                    (c for c in df.columns if "代码" in c or c.lower() in ("code", "symbol")),
                    df.columns[0] if len(df.columns) else None,
                )
                name_col = next(
                    (c for c in df.columns if "名称" in c or c.lower() == "name"),
                    None,
                )
                if code_col is None:
                    log.warning("china_universe: index %s — no code column found (%s)", sym, list(df.columns))
                    continue
                for _, row in df.iterrows():
                    t = _code_to_ticker(str(row[code_col]))
                    if t:
                        zh = str(row[name_col]).strip() if name_col else ""
                        rows.append({"ticker": t, "name_zh": zh})
                log.info("china_universe: CSI index %s → %d constituents", sym, len(df))
            except Exception as e:  # noqa: BLE001 — one bad index must not kill the run
                log.warning("china_universe: akshare index %s failed (%s) — skipped", sym, e)
        return rows

    # -- main ------------------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("china_universe disabled in config")
        self.dir.mkdir(parents=True, exist_ok=True)

        uni = self._sina_universe()

        # Union with CSI index constituents (CSI 300 + CSI 1000 by default).
        # Stocks already ranked by Sina are kept with their real mktcap; extras
        # get a conservative 30亿 placeholder (all CSI index members exceed the floor).
        idx_symbols = self.cfg.get("index_constituents", [])
        if idx_symbols:
            idx_rows = self._index_constituents(idx_symbols)
            extra = [r for r in idx_rows if r["ticker"] not in uni.index]
            if extra:
                extra_df = pd.DataFrame(
                    [{"ticker": r["ticker"], "name_zh": r["name_zh"], "mktcap_yi": 30.0}
                     for r in extra]
                ).set_index("ticker")
                # deduplicate within the extras list (same ticker from multiple indices)
                extra_df = extra_df[~extra_df.index.duplicated(keep="first")]
                uni = pd.concat([uni, extra_df])
                log.info("china_universe: +%d CSI index extras (total %d)", len(extra_df), len(uni))

        tickers = uni.index.tolist()

        prev_closes = pd.read_parquet(self.closes_path) if self.closes_path.exists() else None
        period = self.cfg.get("history_period", "5y")
        if full_history:
            closes = self._download_closes(tickers, "max")
        elif prev_closes is not None and not prev_closes.empty:
            age = (pd.Timestamp.utcnow().tz_localize(None) - prev_closes.index.max()).days
            new = [t for t in tickers if t not in prev_closes.columns]
            fresh = self._download_closes(tickers, "1mo" if age <= 21 else period)
            closes = fresh.combine_first(prev_closes)
            if new:                                       # backfill deep history for new entrants
                deep = self._download_closes(new, period)
                closes = deep.combine_first(closes)
        else:
            closes = self._download_closes(tickers, period)
        # trim to the current universe (keeps the committed file bounded)
        closes = closes[[t for t in tickers if t in closes.columns]].dropna(axis=1, how="all")

        live = closes.shape[1]
        log.info("china_universe coverage: %d/%d names have closes (%.0f%%)",
                 live, len(tickers), 100 * live / max(1, len(tickers)))
        if live < len(tickers) * 0.6:
            raise RuntimeError(f"china_universe closes too sparse: {live}/{len(tickers)}")

        prev_members = pd.read_parquet(self.members_path) if self.members_path.exists() else None
        members = self._enrich(uni, prev_members)
        members = members.loc[[t for t in members.index if t in closes.columns]]

        if not full_history:
            closes.to_parquet(self.closes_path)
        members[["name", "name_zh", "name_en", "sector", "mktcap_yi"]].to_parquet(self.members_path)

        cov = pd.DataFrame({"n_stocks": [len(members)]},
                           index=pd.DatetimeIndex([closes.index.max()], name="date"))
        return {"coverage": cov}
