"""International SEARCH universe — the pooled top-N names per market behind the
International Stock dashboard (site/intlstockdata/) and the per-market residual-
alpha cross-section.

Universe source = the UK-domiciled iShares **UCITS** ETF holdings CSV for each
market (keyless; the SAME ajax pattern as the canada XIC collector). One request
per fund yields ticker + proper company name + GICS sector + index weight + the
listing Location/Exchange — so we derive the Yahoo suffix AND the country flag
straight from the CSV (no get_info enrichment loop). Verified 2026-06-15/19:

  JP IJPN 251866 -> .T    KR IKOR 251871 -> .KS   TW ITWN 251878 -> .TW
  IN NDIA 297617 -> .NS   AU SAUS 251851 -> .AX   GB ISF  251795 -> .L
  EZ IMEU 251860 -> per-row Exchange/Location

A market may list MULTIPLE funds — its primary `ucits` plus an optional
`ucits_extra` list (e.g. UK = FTSE 100 ISF + FTSE 250 mid-caps MIDD) — pooled to
widen the cross-section. Funds degrade independently; first-write-wins dedup
handles a name carried by two funds.

The holdings CSV link is exposed in the product page's static HTML (UK site) at a
stable loader id (config intl.search_universe.ajax_holdings_id); if it rots we
self-heal by scraping the product page for `[0-9]+\.ajax?fileType=csv`.

Close history (5y, for the cycle/ladder + residual-alpha engine) is yfinance,
batched. Each fund degrades independently — one broken fund skips that market,
the others still build. Outputs (committed — small, like canada_search):
  data/intl_search/closes.parquet   wide [date x ticker] adjusted closes
  data/intl_search/members.parquet  index=ticker; name/sector/country/flag/market/weight
  data/intl_search/coverage.parquet 1-row daily series (n_stocks) for run_status
"""
from __future__ import annotations

import io
import logging
import re
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from collectors.breadth import repair_seams
from lib import config

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_BASE = "https://www.blackrock.com/uk/individual/products"

# Europe (IMEU is multi-country): listing Location/country -> Yahoo suffix + flag.
# Keyed by the CSV `Location` column (country name), which is more stable than the
# free-text `Exchange` string.
_EU_SUFFIX = {
    "Germany": ".DE", "France": ".PA", "Netherlands": ".AS", "United Kingdom": ".L",
    "Switzerland": ".SW", "Italy": ".MI", "Spain": ".MC", "Sweden": ".ST",
    "Denmark": ".CO", "Finland": ".HE", "Norway": ".OL", "Belgium": ".BR",
    "Ireland": ".IR", "Austria": ".VI", "Portugal": ".LS", "Luxembourg": ".LU",
    "Poland": ".WA",
}
_EU_FLAG = {
    "Germany": "🇩🇪", "France": "🇫🇷", "Netherlands": "🇳🇱", "United Kingdom": "🇬🇧",
    "Switzerland": "🇨🇭", "Italy": "🇮🇹", "Spain": "🇪🇸", "Sweden": "🇸🇪",
    "Denmark": "🇩🇰", "Finland": "🇫🇮", "Norway": "🇳🇴", "Belgium": "🇧🇪",
    "Ireland": "🇮🇪", "Austria": "🇦🇹", "Portugal": "🇵🇹", "Luxembourg": "🇱🇺",
    "Poland": "🇵🇱",
}

_SKIP = {"", "CASH", "CASH_USD", "USD", "EUR", "GBP", "JPY", "KRW", "TWD", "CHF",
         "--", "-", "NAN", "NONE", "MARGIN", "FUTURES"}


def _clean_local(raw: str) -> str | None:
    """Normalise a raw exchange ticker for the Yahoo `<code><suffix>` convention.
    Strips a trailing dot (LSE 'BP.' -> 'BP'); maps an internal class dot to a dash
    ('BT.A' -> 'BT-A'). Numeric Asian codes ('8306', '005930') pass through."""
    t = (raw or "").strip().upper()
    if t in _SKIP:
        return None
    t = t.rstrip(".")
    t = t.replace(".", "-")
    t = t.replace(" ", "")
    if not re.match(r"^[A-Z0-9-]{1,12}$", t):
        return None
    return t


class IntlUniverseAdapter(Adapter):
    name = "intl_universe"
    group = "intl_search"
    stale_after_days = 7

    def __init__(self) -> None:
        icfg = config.load()["intl"]
        self.cfg = icfg["search_universe"]
        self.ycfg = icfg["yahoo"]
        self.countries = icfg["countries"]
        self.dir = config.data_dir() / "intl_search"
        self.closes_path = self.dir / "closes.parquet"
        self.members_path = self.dir / "members.parquet"

    # -- holdings CSV per fund -------------------------------------------------
    def _holdings_url(self, u: dict) -> str:
        return (f"{_BASE}/{u['product_id']}/{u['slug']}/{self.cfg['ajax_holdings_id']}.ajax"
                f"?fileType=csv&fileName={u['file_name']}_holdings&dataType=fund")

    def _self_heal_url(self, u: dict) -> str | None:
        """If the stable loader id rots, scrape the product page for the live
        holdings ajax link."""
        try:
            page = self.http_get(f"{_BASE}/{u['product_id']}/{u['slug']}", timeout=30,
                                  headers={"User-Agent": _UA}).text
        except Exception:  # noqa: BLE001
            return None
        m = re.search(rf"/uk/individual/products/{u['product_id']}/[A-Za-z0-9/_-]*"
                      rf"[0-9]+\.ajax\?fileType=csv&fileName={u['file_name']}_holdings&dataType=fund",
                      page)
        return ("https://www.blackrock.com" + m.group(0)) if m else None

    def _fetch_holdings(self, cc: str, c: dict, u: dict) -> pd.DataFrame:
        """DataFrame[ticker, name, sector, country, flag, market, weight] for one fund."""
        url = self._holdings_url(u)
        try:
            r = self.http_get(url, retries=self.ycfg["retries"],
                              backoff_base=self.ycfg["backoff_base_s"], timeout=40,
                              headers={"User-Agent": _UA})
            text = r.text
            if "Ticker" not in text[:5000] and "Holdings" not in text[:200]:
                raise ValueError("no holdings header")
        except Exception:  # noqa: BLE001 — try the self-heal scrape
            healed = self._self_heal_url(u)
            if not healed:
                raise
            text = self.http_get(healed, timeout=40, headers={"User-Agent": _UA}).text

        lines = text.splitlines()
        hdr = next((i for i, ln in enumerate(lines)
                    if ln.split(",")[0].strip().strip('"') == "Ticker"), None)
        if hdr is None:
            raise ValueError(f"{u['file_name']} holdings: no 'Ticker' header row")
        df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])), thousands=",")

        def col(sub: str) -> str | None:
            return next((cn for cn in df.columns if sub in cn.lower()), None)
        tcol, ncol, scol = col("ticker"), col("name"), col("sector")
        acol, wcol, lcol = col("asset class"), col("weight"), col("location")
        if not all((tcol, ncol, wcol)):
            raise ValueError(f"{u['file_name']} holdings: unexpected columns {list(df.columns)}")
        if acol is not None:
            df = df[df[acol].astype(str).str.strip().str.lower() == "equity"]
        df["_w"] = pd.to_numeric(df[wcol], errors="coerce")

        suffix = u.get("suffix") or ""
        rows = []
        for _, x in df.iterrows():
            loc = (str(x[lcol]).strip() if lcol else "")
            if suffix:                       # single-country fund: fixed suffix + country flag
                code = _clean_local(str(x[tcol]))
                sfx, flag, market = suffix, c["flag"], c["name"]
            else:                            # EZ multi-country: suffix + flag from Location
                sfx = _EU_SUFFIX.get(loc)
                code = _clean_local(str(x[tcol]))
                flag, market = _EU_FLAG.get(loc, c["flag"]), loc or c["name"]
                if sfx is None:
                    continue
            w = x["_w"]
            if code is None or pd.isna(w) or w <= 0:
                continue
            rows.append({"ticker": code + sfx, "name": str(x[ncol]).strip().title(),
                         "sector": (str(x[scol]).strip() if scol else "—") or "—",
                         "country": cc, "flag": flag, "market": market,
                         "weight": round(float(w), 4)})
        out = (pd.DataFrame(rows).drop_duplicates(subset="ticker")
               .sort_values("weight", ascending=False).head(int(self.cfg.get("size", 220))))
        if out.empty:
            raise RuntimeError(f"{u['file_name']}: 0 usable rows")
        log.info("intl_universe %s/%s: %d names", cc, u["file_name"], len(out))
        return out

    def _all_members(self) -> pd.DataFrame:
        # Each market contributes its primary UCITS fund plus any `ucits_extra`
        # funds (e.g. UK FTSE 100 + FTSE 250 mid-caps) — pooled to widen the
        # cross-section. Each fund degrades independently; one down can't kill the
        # universe. First-write-wins dedup handles names listed in two funds.
        parts = []
        for cc, c in self.countries.items():
            funds = ([c["ucits"]] if c.get("ucits") else []) + list(c.get("ucits_extra") or [])
            for u in funds:
                try:
                    parts.append(self._fetch_holdings(cc, c, u))
                except Exception as e:  # noqa: BLE001 — one fund down can't kill the universe
                    log.warning("intl_universe: %s/%s fund failed: %s", cc, u.get("file_name"), e)
        if not parts:
            raise RuntimeError("intl_universe: every UCITS fund failed")
        m = pd.concat(parts, ignore_index=True).drop_duplicates(subset="ticker")
        return m.set_index("ticker")

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
                    log.warning("intl_universe closes batch %d failed (%s); retry in %.0fs",
                                i // bs, e, wait)
                    time.sleep(wait)
            time.sleep(1)
        if not parts:
            raise RuntimeError("intl_universe: no closes downloaded")
        wide = pd.concat(parts, axis=1)
        return wide.loc[:, ~wide.columns.duplicated()].sort_index()

    def _merge_refreshed(self, fresh: pd.DataFrame, prev: pd.DataFrame) -> pd.DataFrame:
        """``fresh.combine_first(prev)`` + split-seam repair (2026-07-10 KLAC class).

        yfinance auto_adjust back-adjusts only the freshly downloaded window, so
        after a split (e.g. the big JP re-denominations like NTT 25:1) the
        combine_first tail refresh leaves prev rows BEFORE the fresh window on
        the pre-split basis — a permanent fake ±N00% day at the seam. Flagged
        tickers are re-pulled over the full window and replaced wholesale; never
        fatal (see collectors.breadth.repair_seams)."""
        merged = fresh.combine_first(prev)
        merged, _ = repair_seams(merged, fresh, prev, self._download_closes,
                                 name=self.name)
        return merged

    # -- main ------------------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("intl_universe disabled in config")
        self.dir.mkdir(parents=True, exist_ok=True)

        uni = self._all_members()
        tickers = uni.index.tolist()
        period = self.cfg.get("history_period", "5y")

        prev = pd.read_parquet(self.closes_path) if self.closes_path.exists() else None
        if full_history:
            closes = self._download_closes(tickers, "max")
        elif prev is not None and not prev.empty:
            age = (pd.Timestamp.utcnow().tz_localize(None) - prev.index.max()).days
            new = [t for t in tickers if t not in prev.columns]
            fresh = self._download_closes(tickers, "1mo" if age <= 21 else period)
            closes = self._merge_refreshed(fresh, prev)
            if new:
                closes = self._download_closes(new, period).combine_first(closes)
        else:
            closes = self._download_closes(tickers, period)
        closes = closes[[t for t in tickers if t in closes.columns]].dropna(axis=1, how="all")

        live = closes.shape[1]
        log.info("intl_universe coverage: %d/%d names have closes (%.0f%%)",
                 live, len(tickers), 100 * live / max(1, len(tickers)))
        if live < len(tickers) * float(self.cfg.get("min_coverage", 0.5)):
            raise RuntimeError(f"intl_universe closes too sparse: {live}/{len(tickers)}")

        members = uni.loc[[t for t in uni.index if t in closes.columns]]
        if not full_history:
            closes.to_parquet(self.closes_path)
        members[["name", "sector", "country", "flag", "market", "weight"]].to_parquet(self.members_path)

        cov = pd.DataFrame({"n_stocks": [len(members)]},
                           index=pd.DatetimeIndex([closes.index.max()], name="date"))
        return {"coverage": cov}
