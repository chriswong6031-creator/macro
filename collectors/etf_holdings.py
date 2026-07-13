"""Generic multi-sponsor ETF holdings collector — the broad "popular ETFs"
universe (Phase 2). Writes a FULL daily holdings snapshot per fund to
data/etf_holdings/<TICKER>/<YYYY-MM-DD>.parquet with normalized columns
[ticker, name, weight_pct, shares, market_value, as_of]. The engine then diffs
consecutive snapshots with flow normalization
(collectors.holdings.active_changes_dir) to isolate the manager's / index's
actual share decisions — no per-stock prices needed, so it scales to the whole
universe (data/stocks/ only covers ~110 names).

Sponsor reliability (see LIMITATIONS.md):
  ssga    — SPDR daily XLSX, FULL holdings incl. "Shares Held"   (VERIFIED)
  ark     — clean CSV with shares/market_value                   (verified; the
            ARKK/ARKW watchlist is collected by collectors/holdings.py — the
            engine reads those from data/holdings/, so don't duplicate them here)
  ishares — AJAX CSV, product-id keyed; often behind a consent wall (BEST-EFFORT)
  invesco — CSV download endpoint; markup varies                 (BEST-EFFORT)
  vanguard— no reliable free daily holdings feed                 (NOT SUPPORTED)

Each fund is independent: one failing never kills the rest; total failure raises
so the circuit breaker trips. Edit config.yml `etf_holdings.universe` freely —
the list is meant to grow toward the top ~200.
"""
from __future__ import annotations

import io
import logging
import re as _re
import time
import urllib.parse as _urlparse
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

SSGA_XLSX = ("https://www.ssga.com/us/en/intermediary/etfs/library-content/"
             "products/fund-data/etfs/us/holdings-daily-us-en-{fund}.xlsx")
ISHARES_AJAX = ("https://www.ishares.com/us/products/{product_id}/fund/"
                "{cache_id}.ajax?fileType=csv&fileName={fund}_holdings&dataType=fund")
ISHARES_CACHE_ID = "1467271812596"  # State Street/BlackRock CDN cache key (stable-ish)
# Invesco's live cache API (recon 2026-06-13): no headers needed, returns JSON.
# idType=cusip is the RELIABLE id (idType=ticker silently 500s for many funds; only
# the flagship QQQ is pre-warmed by ticker). Parse the `holdings` array.
INVESCO_API = ("https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/"
               "{id}/holdings/fund?idType={idtype}&interval=monthly&productType=ETF")
# Global X: per-fund dated CSV; the on-page download link returns HTML, so hit the
# dated assets.* URL directly and walk back a few business days on 404.
GLOBALX_CSV = "https://assets.globalxetfs.com/funds/holdings/{fund}_full-holdings_{ymd}.csv"
# Roundhill (Filepoint vendor): ONE dated master CSV covers ALL ~51 funds — filter the
# `Account` column. Free, dated, backfillable to 2024 (recon D72). The server SOFT-404s
# (HTTP 200 + an SPA page) for missing dates, so validate the body starts with "Date,Account".
ROUNDHILL_MASTER = ("https://www.roundhillinvestments.com/assets/data/"
                    "FilepointRoundhill.40RU.RU_Holdings_{mdy}.csv")

# Browser UA for the expanded sponsor set (many fund sites 403 / redirect-loop a
# default UA). Chrome-ish string; paired with Accept headers in _ua_get.
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

OUT_COLS = ["ticker", "name", "weight_pct", "shares", "market_value", "as_of"]


class EtfHoldingsAdapter(Adapter):
    name = "etf_holdings"
    group = "etf_holdings"

    def __init__(self) -> None:
        self.cfg = config.load()["etf_holdings"]
        self.universe = self.cfg.get("universe", {})
        self.dir = config.data_dir() / self.group
        self.retries = self.cfg.get("retries", 3)

    # snapshots are written directly (one file per fund per day); fetch() returns
    # a tiny summary series so the runner records freshness, and raises only when
    # EVERY fund failed (so the breaker can trip).
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        ok, errors = 0, []
        for ticker, spec in self.universe.items():
            try:
                snap = self._fetch_one(ticker, spec)
                if snap is not None and not snap.empty:
                    self._write_snapshot(ticker, snap)
                    ok += 1
                time.sleep(0.4)
            except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
                errors.append(f"{ticker}: {e}")
                log.warning("etf_holdings %s failed: %s", ticker, e)
        if not ok:
            raise RuntimeError(f"all ETF holdings failed: {errors}")
        if errors:
            log.warning("etf_holdings partial (%d ok): %s", ok, errors[:8])
        s = pd.DataFrame({"funds_ok": [ok]}, index=[pd.Timestamp(date.today())])
        return {"holdings_runs": s}

    def _write_snapshot(self, ticker: str, snap: pd.DataFrame) -> None:
        d = self.dir / ticker
        d.mkdir(parents=True, exist_ok=True)
        asof = str(snap["as_of"].iloc[0]) if "as_of" in snap.columns else str(date.today())
        target = d / f"{asof}.parquet"
        if target.exists():
            try:
                existing = pd.read_parquet(target)
                # Align dtypes/index before comparison so trivial cast differences
                # don't trigger a false-positive overwrite.
                existing_cmp = existing.reset_index(drop=True).astype(str)
                new_cmp = snap.reset_index(drop=True).astype(str)
                if existing_cmp.equals(new_cmp):
                    log.warning(
                        "etf_holdings: %s as_of %s unchanged upstream — "
                        "skipping rewrite (stale sponsor data)",
                        ticker, asof,
                    )
                    return
            except Exception:  # noqa: BLE001 — on any error fall through to overwrite
                pass
        snap.to_parquet(target)

    def _fetch_one(self, ticker: str, spec: dict) -> pd.DataFrame | None:
        sponsor = spec["sponsor"]
        fn = getattr(self, f"_fetch_{sponsor}", None)
        if fn is None:
            raise ValueError(f"no adapter for sponsor '{sponsor}'")
        return fn(ticker, spec)

    # --- sponsor adapters -------------------------------------------------------
    def _fetch_ssga(self, ticker: str, spec: dict) -> pd.DataFrame:
        url = spec.get("url") or SSGA_XLSX.format(fund=ticker.lower())
        r = self.http_get(url, retries=self.retries, timeout=60,
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        raw = pd.read_excel(io.BytesIO(r.content), header=None)
        hdr = raw.index[raw.iloc[:, 0].astype(str).str.strip() == "Name"]
        if not len(hdr):
            raise ValueError("holdings header row not found")
        i = hdr[0]
        asof = str(date.today())
        for j in range(i):
            cell = str(raw.iloc[j, 1])
            if "As of" in cell:
                asof = str(pd.to_datetime(cell.replace("As of", "").strip()).date())
        df = raw.iloc[i + 1:].copy()
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.iloc[i]]
        wcol = next((c for c in df.columns if "weight" in c), None)
        scol = next((c for c in df.columns if "share" in c), None)
        if "ticker" not in df.columns or wcol is None:
            raise ValueError(f"unexpected SSGA columns: {list(df.columns)[:8]}")
        return self._normalize(df, ticker, asof, wcol=wcol, scol=scol)

    def _fetch_ark(self, ticker: str, spec: dict) -> pd.DataFrame:
        url = spec["url"]
        r = self.http_get(url, retries=self.retries)
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df = df.dropna(subset=["ticker"]) if "ticker" in df.columns else df
        df = df.rename(columns={"market_value_($)": "market_value",
                                "weight_(%)": "weight", "company": "name"})
        asof = (str(pd.to_datetime(df["date"].iloc[0]).date())
                if "date" in df.columns and len(df) else str(date.today()))
        self._assert_recent(asof, ticker)   # renamed ARK funds freeze the old-name URL
        return self._normalize(df, ticker, asof, wcol="weight", scol="shares",
                               mcol="market_value")

    def _fetch_ishares(self, ticker: str, spec: dict) -> pd.DataFrame:
        url = ISHARES_AJAX.format(product_id=spec["product_id"],
                                  cache_id=spec.get("cache_id", ISHARES_CACHE_ID),
                                  fund=ticker)
        r = self.http_get(url, retries=self.retries,
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        # iShares prepends a metadata preamble; the table starts at the "Ticker" row.
        lines = r.text.splitlines()
        start = next((k for k, ln in enumerate(lines)
                      if ln.lower().startswith('"ticker"') or ln.lower().startswith("ticker,")), None)
        if start is None:
            raise ValueError("iShares holdings table not found (consent wall?)")
        df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df = df.rename(columns={"weight_(%)": "weight", "shares": "shares",
                                "market_value": "market_value"})
        wcol = next((c for c in df.columns if "weight" in c), None)
        return self._normalize(df, ticker, str(date.today()), wcol=wcol,
                               scol="shares", mcol="market_value")

    def _fetch_invesco(self, ticker: str, spec: dict) -> pd.DataFrame:
        # idType=cusip is reliable; idType=ticker only works for pre-warmed funds
        # (QQQ). Prefer the configured cusip, else fall back to ticker.
        cusip = spec.get("cusip")
        idval, idtype = (cusip, "cusip") if cusip else (ticker, "ticker")
        url = INVESCO_API.format(id=idval, idtype=idtype)
        r = self.http_get(url, retries=self.retries)
        d = r.json()
        rows = d.get("holdings") or []
        if not rows:
            raise ValueError("invesco: empty holdings array")
        df = pd.DataFrame(rows).rename(columns={
            "issuerName": "name", "units": "shares",
            "percentageOfTotalNetAssets": "weight", "marketValueBase": "market_value"})
        asof = (str(pd.to_datetime(d["effectiveDate"]).date())
                if d.get("effectiveDate") else str(date.today()))
        return self._normalize(df, ticker, asof, wcol="weight", scol="shares",
                               mcol="market_value")

    def _fetch_globalx(self, ticker: str, spec: dict) -> pd.DataFrame:
        last_err = None
        for back in range(0, 6):
            ymd = (date.today() - pd.Timedelta(days=back)).strftime("%Y%m%d")
            url = GLOBALX_CSV.format(fund=ticker.lower(), ymd=ymd)
            try:
                r = self.http_get(url, retries=1, timeout=30,
                                  headers={"User-Agent": "Mozilla/5.0 (research)"})
            except Exception as e:  # noqa: BLE001 — 404 on non-trading days; walk back
                last_err = e
                continue
            lines = r.text.splitlines()
            hdr = next((k for k, ln in enumerate(lines)
                        if ln.lower().startswith("% of net assets") or ln.lower().startswith('"% of net assets')), None)
            if hdr is None:
                last_err = ValueError("Global X: header row not found")
                continue
            asof = ymd
            for ln in lines[:hdr]:
                if "as of" in ln.lower():
                    asof = str(pd.to_datetime(ln.lower().split("as of")[1].strip()).date())
            df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])))
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
            wcol = next((c for c in df.columns if "net_assets" in c or "weight" in c), None)
            scol = next((c for c in df.columns if "shares" in c), None)
            return self._normalize(df, ticker, asof, wcol=wcol, scol=scol,
                                   mcol=next((c for c in df.columns if "market_value" in c), None))
        raise RuntimeError(f"Global X: no holdings file in the last 6 days ({last_err})")

    def _roundhill_master(self, mdy: str):
        """Fetch + cache the dated Roundhill master holdings CSV (all funds). Returns
        a DataFrame, or None when the date has no real file (the server soft-404s with
        HTTP 200 + an SPA page, so we validate the body, not the status code)."""
        cache = getattr(self, "_rh_cache", None)
        if cache is None:
            cache = self._rh_cache = {}
        if mdy in cache:
            return cache[mdy]
        try:
            r = self.http_get(ROUNDHILL_MASTER.format(mdy=mdy), retries=1, timeout=30,
                              headers={"User-Agent": "Mozilla/5.0 (research)"})
        except Exception:  # noqa: BLE001 — missing date; caller walks back
            cache[mdy] = None
            return None
        if not r.text.lstrip().lower().startswith("date,account"):  # soft-404 guard
            cache[mdy] = None
            return None
        cache[mdy] = pd.read_csv(io.StringIO(r.text))
        return cache[mdy]

    def _fetch_roundhill(self, ticker: str, spec: dict) -> pd.DataFrame:
        last_err = None
        for back in range(0, 6):
            mdy = (date.today() - pd.Timedelta(days=back)).strftime("%m%d%Y")
            master = self._roundhill_master(mdy)
            if master is None:
                continue
            sub = master[master["Account"].astype(str).str.strip() == ticker]
            if sub.empty:
                last_err = ValueError(f"{ticker} not in Roundhill master {mdy}")
                continue
            asof = str(date.today())
            try:
                asof = str(pd.to_datetime(sub["Date"].iloc[0]).date())
            except (ValueError, TypeError):
                pass
            df = sub.rename(columns={"StockTicker": "ticker", "SecurityName": "name",
                                     "Weightings": "weight", "Shares": "shares",
                                     "MarketValue": "market_value"})
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
            return self._normalize(df, ticker, asof, wcol="weight", scol="shares",
                                   mcol="market_value")
        raise RuntimeError(f"Roundhill: no holdings for {ticker} in the last 6 days ({last_err})")

    # --- shared helpers for the expanded sponsor set ---------------------------
    def _ua_get(self, url, retries=None, timeout=45, **kw):
        """GET with a browser User-Agent (many fund sites 403 or redirect-loop a
        non-browser UA). Delegates to Adapter.http_get for retry/backoff."""
        headers = {"User-Agent": _BROWSER_UA, "Accept": "*/*",
                   "Accept-Language": "en-US,en;q=0.9"}
        headers.update(kw.pop("headers", {}))
        return self.http_get(url,
                             retries=retries if retries is not None else self.retries,
                             timeout=timeout, headers=headers, **kw)

    @staticmethod
    def _assert_recent(asof: str, fund: str, max_lag_days: int = 45) -> None:
        """Guard the stale-ghost failure mode: renamed funds (e.g. ARKF/ARKX) leave
        the OLD-name URL serving data FROZEN months back. Raise if as_of is older
        than max_lag_days. Deliberately lenient — it only catches truly frozen
        feeds, never the normal 1-2 week publication lag some sponsors run."""
        try:
            ts = pd.to_datetime(asof)
        except Exception:  # noqa: BLE001 — unparseable: let it through (backstop, not a gate)
            return
        if (pd.Timestamp(date.today()) - ts).days > max_lag_days:
            raise ValueError(
                f"{fund}: holdings as_of {asof} is stale (> {max_lag_days}d) — "
                "frozen / renamed feed? refusing to snapshot")

    @staticmethod
    def _xlsx_header_row(raw: pd.DataFrame, need=("ticker",), any_of=("share",)) -> int | None:
        """Row index whose lowercased cells contain every token in `need` and at
        least one token matching `any_of`. For sponsor XLSX with a title preamble."""
        for j in range(min(20, len(raw))):
            cells = [str(c).strip().lower() for c in raw.iloc[j].tolist()]
            if all(any(t == c or t in c for c in cells) for t in need) \
                    and any(any(a in c for c in cells) for a in any_of):
                return j
        return None

    # --- VanEck (XLSX; slug per fund; soft-404 guard on PK zip magic) ----------
    def _fetch_vaneck(self, ticker: str, spec: dict) -> pd.DataFrame:
        slug = spec.get("slug")
        if not slug:
            raise ValueError(f"vaneck {ticker}: missing 'slug' in spec")
        url = f"https://www.vaneck.com/us/en/investments/{slug}/downloads/holdings/"
        r = self._ua_get(url, timeout=45)
        if r.content[:2] != b"PK":  # wrong slug soft-404s to a ~277KB HTML page
            raise ValueError(f"vaneck {ticker}: not an XLSX (soft-404? {len(r.content)}B)")
        raw = pd.read_excel(io.BytesIO(r.content), header=None)
        hdr = self._xlsx_header_row(raw, need=("ticker",), any_of=("share",))
        if hdr is None:
            raise ValueError(f"vaneck {ticker}: header row not found")
        asof = str(date.today())
        for j in range(hdr):
            for c in raw.iloc[j].tolist():
                m = _re.search(r"(\d{2}/\d{2}/\d{4})", str(c))
                if m:
                    try:
                        asof = str(pd.to_datetime(m.group(1)).date())
                    except Exception:  # noqa: BLE001
                        pass
        df = raw.iloc[hdr + 1:].copy()
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.iloc[hdr]]
        wcol = next((c for c in df.columns if "net_assets" in c or "weight" in c), None)
        scol = next((c for c in df.columns if "share" in c), None)
        mcol = next((c for c in df.columns if "market_value" in c), None)
        ncol = next((c for c in df.columns if "holding_name" in c or c == "name"), None)
        if ncol and ncol != "name":
            df = df.rename(columns={ncol: "name"})
        return self._normalize(df, ticker, asof, wcol=wcol, scol=scol, mcol=mcol)

    # --- First Trust (server-rendered HTML table; pandas.read_html) -----------
    def _fetch_firsttrust(self, ticker: str, spec: dict) -> pd.DataFrame:
        url = f"https://www.ftportfolios.com/retail/etf/ETFholdings.aspx?Ticker={ticker}"
        r = self._ua_get(url, timeout=45)
        df = self._pick_html_table(r.text, need_weight=True, need_shares=True,
                                   who=f"firsttrust {ticker}")
        # First Trust: Security Name | Identifier(=ticker) | CUSIP | ... | Shares | MV | Weighting
        ncol = next((c for c in df.columns if "security" in c or "holding" in c or c == "name"), None)
        tcol = next((c for c in df.columns if c in ("ticker", "symbol", "identifier")), None)
        ren = {}
        if ncol and ncol != "name":
            ren[ncol] = "name"
        if tcol and tcol != "ticker":
            ren[tcol] = "ticker"
        df = df.rename(columns=ren)
        wcol = next((c for c in df.columns if "weight" in c), None)
        scol = next((c for c in df.columns if "share" in c or "quantit" in c), None)
        mcol = next((c for c in df.columns if "market_value" in c or c == "value"), None)
        asof = str(date.today())
        m = _re.search(r"[Aa]s of\s+(\d{1,2}/\d{1,2}/\d{4})", r.text)
        if m:
            try:
                asof = str(pd.to_datetime(m.group(1)).date())
            except Exception:  # noqa: BLE001
                pass
        return self._normalize(df, ticker, asof, wcol=wcol, scol=scol, mcol=mcol)

    # --- Bitwise (server-rendered HTML table) ---------------------------------
    def _fetch_bitwise(self, ticker: str, spec: dict) -> pd.DataFrame:
        url = spec.get("url") or f"https://{ticker.lower()}etf.com/holdings"
        r = self._ua_get(url, timeout=45)
        df = self._pick_html_table(r.text, need_weight=True, need_shares=True,
                                   who=f"bitwise {ticker}")
        ncol = next((c for c in df.columns if c == "name" or "holding" in c or "company" in c), None)
        tcol = next((c for c in df.columns if c in ("ticker", "symbol")), None)
        ren = {}
        if ncol and ncol != "name":
            ren[ncol] = "name"
        if tcol and tcol != "ticker":
            ren[tcol] = "ticker"
        df = df.rename(columns=ren)
        wcol = next((c for c in df.columns if "weight" in c), None)
        scol = next((c for c in df.columns if "share" in c), None)
        mcol = next((c for c in df.columns if "market_value" in c or c == "value"), None)
        asof = str(date.today())
        m = _re.search(r"[Aa]s of\s+(\d{1,2}/\d{1,2}/\d{4})", r.text)
        if m:
            try:
                asof = str(pd.to_datetime(m.group(1)).date())
            except Exception:  # noqa: BLE001
                pass
        return self._normalize(df, ticker, asof, wcol=wcol, scol=scol, mcol=mcol)

    # --- stockanalysis.com — NON-OFFICIAL third-party (Finnhub-sourced) --------
    #     Used ONLY for funds whose issuer feed is JS/anti-bot walled (e.g. WGMI;
    #     CoinShares' own site is a JS-rendered app). Labelled unofficial in the
    #     universe + on the page. See LIMITATIONS.md (non-official layer).
    def _fetch_stockanalysis(self, ticker: str, spec: dict) -> pd.DataFrame:
        url = f"https://stockanalysis.com/etf/{ticker.lower()}/holdings/"
        r = self._ua_get(url, timeout=45)
        df = self._pick_html_table(r.text, need_weight=True, need_shares=True,
                                   who=f"stockanalysis {ticker}", weight_token="pct")
        sym = next((c for c in df.columns if c == "symbol"), None)
        if sym:
            df = df.rename(columns={sym: "ticker"})
        if "ticker" in df.columns:  # some symbols carry a leading '$'
            df["ticker"] = df["ticker"].astype(str).str.lstrip("$").str.strip()
        wcol = next((c for c in df.columns if "weight" in c or "pct" in c), None)
        scol = next((c for c in df.columns if "share" in c), None)
        asof = str(date.today())
        m = _re.search(r"[Aa]s of\s+([A-Za-z]{3,9}\.?\s+\d{1,2},\s+\d{4})", r.text)
        if m:
            try:
                asof = str(pd.to_datetime(m.group(1).replace(".", "")).date())
            except Exception:  # noqa: BLE001
                pass
        return self._normalize(df, ticker, asof, wcol=wcol, scol=scol, mcol=None)

    @staticmethod
    def _pick_html_table(html: str, *, need_weight: bool, need_shares: bool,
                         who: str, weight_token: str = "weight") -> pd.DataFrame:
        """First HTML <table> that has a weight column and (if required) a
        shares/quantity column. Raises ValueError if none match."""
        try:
            tables = pd.read_html(io.StringIO(html))
        except Exception as e:  # noqa: BLE001 — needs lxml/bs4; degrade per-fund
            raise ValueError(f"{who}: read_html failed ({e})")
        for t in tables:
            cols = [str(c).strip().lower() for c in t.columns]
            has_w = (not need_weight) or any(weight_token in c or "%" in c for c in cols)
            has_s = (not need_shares) or any("share" in c or "quantit" in c for c in cols)
            if has_w and has_s:
                t = t.copy()
                t.columns = [str(c).strip().lower().replace(" ", "_").replace("%", "pct")
                             for c in t.columns]
                return t
        raise ValueError(f"{who}: no holdings table found")

    # --- Sprott (full holdings embedded as a data: URI in static fund-page HTML) -
    def _fetch_sprott(self, ticker: str, spec: dict) -> pd.DataFrame:
        slug = spec.get("slug")
        if not slug:
            raise ValueError(f"sprott {ticker}: missing 'slug' in spec")
        r = self._ua_get(f"https://sprottetfs.com/{slug}/", timeout=45)
        m = _re.search(r'href="data:application/(?:csv|octet-stream)[^"]*?,([^"]+)"', r.text)
        if not m:
            raise ValueError(f"sprott {ticker}: holdings data-URI not found")
        csv_text = _urlparse.unquote(m.group(1))
        df = pd.read_csv(io.StringIO(csv_text))
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        df = df.rename(columns={k: v for k, v in
                                {"symbol": "ticker", "quantity": "shares", "security": "name"}.items()
                                if k in df.columns})
        asof = str(date.today())
        m2 = _re.search(r"as of\s+([A-Z][a-z]+ \d{1,2}, \d{4})", r.text)
        if m2:
            try:
                asof = str(pd.to_datetime(m2.group(1)).date())
            except Exception:  # noqa: BLE001
                pass
        wcol = next((c for c in df.columns if "weight" in c), None)
        mcol = next((c for c in df.columns if "market_value" in c), None)
        return self._normalize(df, ticker, asof, wcol=wcol, scol="shares", mcol=mcol)

    # --- Amplify (public Firebase Firestore REST; dated docs, backfillable) ----
    def _fetch_amplify(self, ticker: str, spec: dict) -> pd.DataFrame:
        base = ("https://firestore.googleapis.com/v1/projects/amplify-etfs-data-feed/"
                f"databases/(default)/documents/funds/{ticker}/holdings")
        key = spec.get("api_key", "AIzaSyCibhGo4lu8ZALtBvf_ZT351BDMUPqOYjc")
        listing = self._ua_get(f"{base}?mask.fieldPaths=asOfDate&pageSize=400&key={key}",
                               timeout=45).json()
        dates = [d.get("name", "").rsplit("/", 1)[-1]
                 for d in (listing.get("documents") or [])]
        dates = [d for d in dates if d]
        if not dates:
            raise ValueError(f"amplify {ticker}: empty holdings collection")
        latest = max(dates)
        doc = self._ua_get(f"{base}/{latest}?key={key}", timeout=45).json()
        return self._parse_amplify_doc(doc, ticker, latest)

    @staticmethod
    def _parse_amplify_doc(doc: dict, ticker: str, fallback_date: str) -> pd.DataFrame:
        fields = doc.get("fields", {})

        def _gv(mv: dict, k: str):
            v = mv.get(k, {})
            return (v.get("stringValue") or v.get("integerValue")
                    or v.get("doubleValue") or v.get("nullValue"))
        holdings = (fields.get("holdings", {}).get("arrayValue", {}).get("values", []))
        rows = []
        for h in holdings:
            mv = h.get("mapValue", {}).get("fields", {})
            rows.append({"ticker": _gv(mv, "StockTicker"), "name": _gv(mv, "SecurityName"),
                         "weight": _gv(mv, "Weightings"), "shares": _gv(mv, "Shares"),
                         "market_value": _gv(mv, "MarketValue")})
        df = pd.DataFrame(rows)
        if df.empty or "ticker" not in df.columns:
            raise ValueError(f"amplify {ticker}: empty / parse-less holdings doc")
        asof = fields.get("asOfDate", {}).get("stringValue") or fallback_date
        try:
            asof = str(pd.to_datetime(asof).date())
        except Exception:  # noqa: BLE001
            asof = fallback_date
        return EtfHoldingsAdapter._normalize(df, ticker, asof, wcol="weight",
                                             scol="shares", mcol="market_value")

    # --- Defiance (dated XLSX; forward-dated T+1; probe a small date window) ---
    def _fetch_defiance(self, ticker: str, spec: dict) -> pd.DataFrame:
        slug = spec.get("slug", ticker.lower())
        last_err = None
        for back in range(-1, 4):  # tomorrow (forward-dated), today, back 3 days
            d = (pd.Timestamp(date.today()) - pd.Timedelta(days=back))
            mdy = d.strftime("%m-%d-%Y")
            url = f"https://www.defianceetfs.com/wp-content/uploads/xls/{slug}-{mdy}.xlsx"
            try:
                r = self._ua_get(url, retries=1, timeout=30)
            except Exception as e:  # noqa: BLE001 — 404 on non-trading days; walk on
                last_err = e
                continue
            if r.content[:2] != b"PK":
                last_err = ValueError("not xlsx")
                continue
            raw = pd.read_excel(io.BytesIO(r.content), header=None)
            hdr = self._xlsx_header_row(raw, need=("ticker",), any_of=("share", "weight"))
            if hdr is None:
                last_err = ValueError("header not found")
                continue
            df = raw.iloc[hdr + 1:].copy()
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.iloc[hdr]]
            asof = str(d.date())
            wcol = next((c for c in df.columns if "weight" in c), None)
            scol = next((c for c in df.columns if "share" in c), None)
            ncol = next((c for c in df.columns if c == "name" or "holding" in c), None)
            if ncol and ncol != "name":
                df = df.rename(columns={ncol: "name"})
            return self._normalize(df, ticker, asof, wcol=wcol, scol=scol, mcol=None)
        raise RuntimeError(f"defiance {ticker}: no xlsx in probe window ({last_err})")

    # --- Procure (Filepoint CSV; scrape the current .csv href off the fund page) -
    def _fetch_procure(self, ticker: str, spec: dict) -> pd.DataFrame:
        page = spec.get("page", f"https://procureetfs.com/{ticker.lower()}/")
        r = self._ua_get(page, timeout=45)
        m = _re.search(r'href="([^"]+\.csv)"', r.text)
        if not m:
            raise ValueError(f"procure {ticker}: holdings csv link not found")
        csv_url = m.group(1)
        if csv_url.startswith("/"):
            csv_url = "https://procureetfs.com" + csv_url
        rc = self._ua_get(csv_url, timeout=45)
        if not rc.text.lstrip().lower().startswith("date,account"):
            raise ValueError(f"procure {ticker}: unexpected csv header")
        df = pd.read_csv(io.StringIO(rc.text))
        df = df.rename(columns={"StockTicker": "ticker", "SecurityName": "name",
                                "Weightings": "weight", "Shares": "shares",
                                "MarketValue": "market_value"})
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        asof = str(date.today())
        try:
            asof = str(pd.to_datetime(df["date"].iloc[0]).date())
        except Exception:  # noqa: BLE001
            pass
        return self._normalize(df, ticker, asof, wcol="weight", scol="shares",
                               mcol="market_value")

    # --- Exchange Traded Concepts white-label CMS (JSON; e.g. Range NUKZ) ------
    def _fetch_etc(self, ticker: str, spec: dict) -> pd.DataFrame:
        url = f"https://cms.etc-webmaker.com/holdings?ticker={ticker.lower()}"
        data = self._ua_get(url, timeout=45).json()
        rec = data[0] if isinstance(data, list) and data else data
        fin = (rec or {}).get("finData") or []
        if not fin:
            raise ValueError(f"etc {ticker}: empty finData")
        df = pd.DataFrame([{"ticker": h.get("ticker"), "name": h.get("description"),
                            "shares": h.get("quantity"), "market_value": h.get("market_value"),
                            "weight": h.get("percent_of_nav")} for h in fin])
        asof = str(date.today())
        try:
            asof = str(pd.to_datetime(rec.get("date")).date())
        except Exception:  # noqa: BLE001
            pass
        return self._normalize(df, ticker, asof, wcol="weight", scol="shares",
                               mcol="market_value")

    # --- normalization ----------------------------------------------------------
    @staticmethod
    def _normalize(df: pd.DataFrame, fund: str, asof: str, *, wcol: str | None = None,
                   scol: str | None = None, mcol: str | None = None) -> pd.DataFrame:
        from collectors.holdings import is_non_equity_holding
        if "ticker" not in df.columns:
            _tk = next((c for c in df.columns
                        if c in ("symbol", "identifier", "holding_ticker", "stock_ticker")
                        or c.endswith("_ticker") or "ticker" in c or "symbol" in c), None)
            if _tk is None:
                raise ValueError(f"{fund}: no ticker/symbol column in {list(df.columns)}")
            df = df.rename(columns={_tk: "ticker"})
        def num(s):
            return pd.to_numeric(
                s.astype(str).str.replace(r"[,$%()]", "", regex=True).str.strip(),
                errors="coerce")
        out = pd.DataFrame({
            "ticker": df["ticker"].astype(str).str.strip(),
            "name": (df["name"].astype(str).str.strip() if "name" in df.columns else ""),
            "weight_pct": num(df[wcol]) if wcol and wcol in df.columns else pd.NA,
            "shares": num(df[scol]) if scol and scol in df.columns else pd.NA,
            "market_value": num(df[mcol]) if mcol and mcol in df.columns else pd.NA,
        })
        # share-based engine needs a real equity ticker + shares; drop cash, FX,
        # money-market, derivatives and untickered residue (shared predicate, so
        # the collector and the diff engine agree on what counts as equity).
        keep = [not is_non_equity_holding(t, n)
                for t, n in zip(out["ticker"], out["name"])]
        out = out[pd.Series(keep, index=out.index)].dropna(subset=["shares"])
        if out.empty:
            raise ValueError(f"{fund}: no equity/shared rows after normalization")
        out["as_of"] = asof
        return out.reset_index(drop=True)
