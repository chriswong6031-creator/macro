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
import time
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

    # --- normalization ----------------------------------------------------------
    @staticmethod
    def _normalize(df: pd.DataFrame, fund: str, asof: str, *, wcol: str | None = None,
                   scol: str | None = None, mcol: str | None = None) -> pd.DataFrame:
        from collectors.holdings import is_non_equity_holding
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
