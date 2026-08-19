"""Top-N holdings per sector SPDR + their stock prices + light fundamentals.

- Holdings: SSGA's daily holdings XLSX per fund (public investor documents).
  Top N (=20) by weight, upserted into one history parquet per sector. The
  XLSX already lists every holding, so widening N is free (no extra fetch);
  N=20 roughly doubles name coverage for the single-stock library and the
  heatmap's offline cap proxy vs the legacy top-10.
- Stock prices: yahoo batch for the union of all top-N tickers (~160-200
  names), stored under data/stocks/ — full history on backfill (the cycle
  calibration needs it), incremental daily afterwards.
- Fundamentals: best-effort yfinance info fields, weekly cadence, LOW
  CONFIDENCE by design (unofficial API, sparse fields).
"""
from __future__ import annotations

import io
import logging
import time
from datetime import date, datetime

import pandas as pd

from collectors.base import Adapter
from lib import config, nyse_calendar, store

log = logging.getLogger(__name__)

# How many holdings to keep per sector ETF. The SSGA file carries every holding,
# so this only sets how deep into the tail we store/track. 20 ≈ 75-85% of each
# fund's weight and ~160-200 union names (vs ~110 at top-10). The legacy
# helper names (top10_union/latest_top10) are kept for their callers.
TOP_N = 20

SSGA_XLSX = ("https://www.ssga.com/us/en/intermediary/etfs/library-content/"
             "products/fund-data/etfs/us/holdings-daily-us-en-{fund}.xlsx")


class SectorHoldingsAdapter(Adapter):
    """Daily top-N (=20) holdings snapshots for the 11 sector SPDRs."""

    name = "sector_holdings"
    group = "sector_holdings"

    def __init__(self) -> None:
        self.cfg = config.load()["sponsors"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # N rows share one date, so these tables bypass the store's
        # one-row-per-date upsert and are merged here instead
        ok, errors = 0, []
        for fund in self.cfg["sector_funds"]:
            try:
                snap = self._fetch_fund(fund)
                self._merge_write(fund, snap)
                ok += 1
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{fund}: {e}")
        if not ok:
            raise RuntimeError(f"all sector holdings failed: {errors}")
        if errors:
            log.warning("sector_holdings partial: %s", errors)
        s = pd.DataFrame({"funds_ok": [ok]}, index=[pd.Timestamp(date.today())])
        return {"holdings_runs": s}

    def _merge_write(self, fund: str, snap: pd.DataFrame) -> None:
        d = config.data_dir() / self.group
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{fund}.parquet"
        if p.exists():
            old = pd.read_parquet(p)
            old.index = pd.to_datetime(old.index)
            old = old[old.index != snap.index[0]]  # replace same-day snapshot
            snap = pd.concat([old, snap]).sort_index()
        snap.to_parquet(p)
        # PIT history archiver: append-mode dated store for dispersion analysis.
        # Columns: as_of (date), etf (str), ticker, name, weight_pct, rank.
        # Idempotent per (as_of, etf): same-day re-runs drop the old rows first.
        # Pass only today's rows (last date in the now-merged snap).
        today_date = snap.index.max()
        self._append_history(fund, snap.loc[[today_date]])

    def _append_history(self, fund: str, snap: pd.DataFrame) -> None:
        """Append today's snapshot for *fund* to data/sector_holdings/history.parquet.

        Idempotent: if a row for (as_of, etf) already exists it is replaced, not
        duplicated.  ``snap`` carries the per-holding rows indexed by as_of date.
        """
        d = config.data_dir() / self.group
        as_of = snap.index[0].date()
        rows = snap.reset_index(drop=True).copy()
        rows.insert(0, "as_of", as_of)
        rows.insert(1, "etf", fund)
        hist_path = d / "history.parquet"
        if hist_path.exists():
            old = pd.read_parquet(hist_path)
            old["as_of"] = pd.to_datetime(old["as_of"]).dt.date
            # Drop rows for same (as_of, etf) to ensure idempotency
            mask = ~((old["as_of"] == as_of) & (old["etf"] == fund))
            old = old[mask]
            rows = pd.concat([old, rows], ignore_index=True)
        rows["as_of"] = pd.to_datetime(rows["as_of"])
        rows = rows.sort_values(["as_of", "etf", "rank"]).reset_index(drop=True)
        rows.to_parquet(hist_path, index=False)

    def _fetch_fund(self, fund: str) -> pd.DataFrame:
        r = self.http_get(SSGA_XLSX.format(fund=fund.lower()), retries=3, timeout=60,
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        # keep_default_na=False: 'NA' is a live listing (Nano Labs; National Bank of
        # Canada on TSX). na_values=[""] keeps blank -> NaN so dropna/to_numeric are unchanged.
        raw = pd.read_excel(io.BytesIO(r.content), header=None,
                            keep_default_na=False, na_values=[""])
        # find the header row ("Name", "Ticker", ...) and the as-of date above it
        hdr_idx = raw.index[raw.iloc[:, 0].astype(str).str.strip() == "Name"]
        if not len(hdr_idx):
            raise ValueError("holdings header row not found")
        asof = str(date.today())
        for i in range(hdr_idx[0]):
            cell = str(raw.iloc[i, 1])
            if "As of" in cell:
                asof = str(pd.to_datetime(cell.replace("As of", "").strip()).date())
        df = raw.iloc[hdr_idx[0] + 1:].copy()
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.iloc[hdr_idx[0]]]
        df = df.rename(columns={"weight": "weight_pct"})
        wcol = next((c for c in df.columns if "weight" in c), None)
        if wcol is None or "ticker" not in df.columns:
            raise ValueError(f"unexpected columns: {list(df.columns)[:6]}")
        df["weight_pct"] = pd.to_numeric(df[wcol], errors="coerce")
        df = (df.dropna(subset=["weight_pct", "ticker"])
                .query("ticker != '-'")
                .nlargest(TOP_N, "weight_pct"))
        out = pd.DataFrame({
            "ticker": df["ticker"].astype(str).str.strip(),
            "name": df["name"].astype(str).str.strip() if "name" in df.columns else "",
            "weight_pct": df["weight_pct"].round(2),
            "rank": range(1, len(df) + 1),
        })
        out.index = pd.to_datetime([asof] * len(out))
        return out

def top10_union() -> list[str]:
    """Union of current top-N holdings tickers across all sectors (price feed).
    (Name kept for back-compat; returns the top-``TOP_N`` union, not just 10.)"""
    d = config.data_dir() / "sector_holdings"
    if not d.exists():
        return []
    tickers: set[str] = set()
    for p in d.glob("*.parquet"):
        df = pd.read_parquet(p)
        if "ticker" not in df.columns or df.empty:
            continue
        df.index = pd.to_datetime(df.index)
        last_day = df.index.max()
        tickers |= set(df.loc[[last_day], "ticker"].astype(str))
    # yahoo notation: BRK.B -> BRK-B
    return sorted(t.replace(".", "-") for t in tickers if t and t != "nan")


def latest_top10(fund: str) -> pd.DataFrame | None:
    df = store.read("sector_holdings", fund)
    if df is None or df.empty:
        return None
    return df.loc[[df.index.max()]].sort_values("rank")


_DEEP_MIN_ROWS = 250  # below this a "healthy" file is a throttled seed stub, not history

# A period='1mo' refresh reaches ~30 calendar days back; a store frozen longer than
# this has no window overlap left to bridge and would strand an interior hole rather
# than heal it — route to period='max' instead. 21 gives the cheap window margin
# under its own ~30-day reach (SATS class: 46 days frozen at the 2026-08-03
# adjudication — see _fetch_universe below for the incident this pairs with).
_MAX_WINDOW_BRIDGE_DAYS = 21


def _dead_tickers() -> frozenset[str]:
    """Ticker set from the dead-name price store (data/edgar/dead_name_prices.parquet,
    long format — see engine/grading.py::load_dead_prices for the same shape/path).
    Absent/unreadable/column-missing degrades to frozenset(): the dead-name registry is
    a CI-collected side artifact, not always present in every checkout, and a name this
    can't classify simply isn't excluded from anything — the retention union in
    _fetch_universe fails safe toward FETCHING, never toward silently dropping a name."""
    p = config.data_dir() / "edgar" / "dead_name_prices.parquet"
    try:
        # columns=["ticker"] alone (~100x cheaper than a full read — the store carries
        # date/close/source too); a missing 'ticker' column raises here as well and
        # lands in the same except, so the column-missing contract is unchanged.
        df = pd.read_parquet(p, columns=["ticker"])
    except Exception as e:  # noqa: BLE001 — absent/corrupt/column-missing must never block retention
        log.debug("stocks: dead_name_prices unreadable (%s) — no names excluded", e)
        return frozenset()
    return frozenset(df["ticker"].astype(str))


def _fetch_universe(current: list[str], stored: list[str], dead: frozenset[str]) -> list[str]:
    """The retention fetch set: today's top-N union PLUS every ticker still on disk
    under data/stocks, minus names confirmed dead.

    2026-08-03 adjudication: top10_union() ALONE regressed a ticker's fetch the moment
    it fell out of every sector SPDR's top-20 — and scripts/build_stock_library.py's
    universe() keeps preferring the frozen deep store over fresher breadth caches, so
    nothing downstream ever noticed the parquet stopped advancing. Measured receipts:
    QCOM (XLK rank 20, exited 2026-07-09) froze at 2026-07-10; HOOD (XLF r20,
    2026-07-09) froze at 07-10; MRVL (XLK r18, 2026-07-10) froze at 07-13; CVNA (XLY
    r19, 2026-07-16) froze at 07-17; WDC (XLK r20, 2026-07-23) froze at 07-24; HON
    (XLI, exited 06-26) froze at 07-17, that tip itself an artifact of the 07-19
    one-shot basis heal (#3096) — 10 to 46 days frozen apiece, forever, with nothing
    watching. A name must keep being fetched for as long as it is still on disk,
    dead-registry names excepted.

    A dead-registry name that is STILL in the current union is fetched anyway — the
    union side always wins. Ticker symbols get reused across unrelated companies over
    time, and refusing to fetch a live top-N holding because an unrelated past company
    once traded under the same string would be a worse defect than the one this
    function exists to fix."""
    return sorted(set(current) | (set(stored) - dead))


def _report_missing_symbols(requested: list[str], returned, current) -> list[str]:
    """Requested-vs-returned reconciliation for one StockPriceAdapter.fetch() run —
    the collectors/yahoo.py::_report_missing_symbols idiom applied to the data/stocks
    lane (R4 never-silent collectors,
    research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md §3 chip (1)).

    `_pull()` drops a requested-but-unreturned ticker through a log-only
    `except KeyError`, and the ONLY aggregate backstop is fetch()'s 0.7 floor — so up
    to 30% of the fetch set can return nothing on a given night with no per-name trace
    anywhere in the Actions summary (a logger-prefixed line is not an annotation; see
    the annotation law and tests/test_gh_annotation_line_start.py). _fetch_universe's
    retention makes that hole WIDER, not narrower: the fetch set now carries every
    name still on disk, so without this the store-tip audit's stale_live flag is the
    only thing that would ever notice — one whole night later, and without the reason.

    The union/retained SPLIT is the actionable part, and it is the one thing the yahoo
    lane has no need of. A ticker in TODAY's top-N union that returns nothing is a live
    provider failure against a name the desk is actively holding. A RETAINED ticker
    (still on disk, already out of the union) that returns nothing is the
    delisted-or-renamed candidate set — #4616's law is that delisted is not stale, and
    the exit path for those names is the dead-name registry / the #4622 symbol
    resolution protocol (a rename is a KEY MIGRATION), never an in-place refetch.
    Naming the two apart is what lets the next reader route them correctly instead of
    re-diagnosing the whole list from scratch.

    Bare ::warning at line start (annotation law — never through the logger); returns
    the missing list so a caller/test can assert on it without re-parsing the text."""
    have = set(returned)
    missing = [t for t in requested if t not in have]
    if missing:
        union = set(current)
        n_union = sum(1 for t in missing if t in union)
        n_retained = len(missing) - n_union
        shown = missing[:15]
        more = len(missing) - len(shown)
        print(f"::warning title=stocks collector missing symbols::{len(missing)} of "
              f"{len(requested)} requested ticker(s) returned no data ({n_union} in "
              f"today's top-N union, {n_retained} retained off-union — "
              f"delisted/renamed candidates): {', '.join(shown)}"
              f"{f', +{more} more' if more > 0 else ''}", flush=True)
    return missing


class StockPriceAdapter(Adapter):
    """Daily closes for the union of top-N holdings (cycle engine fuel)."""

    name = "stock_prices"
    group = "stocks"
    overwrite_overlap = True  # yfinance auto_adjust=True → seam-free re-adjust of the refresh window

    def __init__(self) -> None:
        self.ycfg = config.load()["yahoo"]

    def stored_series(self) -> list[str]:
        """Every ticker currently on disk under data/stocks — the retention side of
        _fetch_universe (a name the union has dropped must keep appearing here for
        its store to keep advancing; see _fetch_universe's docstring for the
        incident). Do not hoist the leading-underscore filter into the base Adapter:
        data/intl legitimately stores ^-sanitized stems (_N225, _FTSE) that
        IntlPriceAdapter's base stored_series() must keep returning."""
        d = config.data_dir() / self.group
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_"))

    def _needs_full(self, ticker: str, today: pd.Timestamp | None = None) -> bool:
        """A ticker needs a full-history re-fetch when its stored file is missing
        volume for a meaningful share of rows (volume was added to this adapter
        after the price history was first seeded) OR is too shallow to be real
        history — a throttled period='max' seed pull can leave a ~40-row stub that
        a volume-share check alone calls healthy forever (CBRE/ISRG/KMI/MLM,
        2026-05 class) OR has a stored tip older than _MAX_WINDOW_BRIDGE_DAYS calendar
        days — a name _fetch_universe kept in the fetch set after it dropped out of
        top10_union() (or one that simply missed several nights) needs period='max',
        not the cheap period='1mo' window, once the freeze is old enough that the
        window can no longer reach back to the last stored bar (SATS class, 46 days
        frozen at the 2026-08-03 adjudication). Self-heals all three; once deep,
        volume-complete, and current the ticker falls back to the cheap daily window.
        `today` is test-injected; defaults to the current ET calendar date (matches
        scripts/audit_stocks_freshness.py's lag anchor). The tip is parsed
        defensively (NaT / tz-aware index both degrade to True, never a raise) because
        this is called from a bare list comprehension in fetch() with no per-ticker
        try/except — one corrupt stored file must never kill the run for every other
        ticker."""
        old = store.read("stocks", ticker)
        if old is None or old.empty or "volume" not in old.columns:
            return True
        if len(old) < _DEEP_MIN_ROWS:
            return True
        if float(old["volume"].notna().mean()) < 0.95:
            return True
        today = (pd.Timestamp(today).normalize() if today is not None
                 else pd.Timestamp(datetime.now(nyse_calendar.ET).date()))
        tip = pd.Timestamp(old.index.max())
        if pd.isna(tip):
            return True
        if tip.tzinfo is not None:
            tip = tip.tz_localize(None)
        return bool((today - tip.normalize()).days > _MAX_WINDOW_BRIDGE_DAYS)

    def _download(self, batch: list[str], period: str) -> pd.DataFrame:
        import yfinance as yf
        last_exc: Exception | None = None
        for attempt in range(self.ycfg["retries"]):
            try:
                return yf.download(batch, period=period, auto_adjust=True,
                                   progress=False, group_by="ticker", threads=True)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt < self.ycfg["retries"] - 1:
                    time.sleep(self.ycfg["backoff_base_s"] * (2 ** attempt))
        raise last_exc  # type: ignore[misc]

    def _pull(self, period: str, tlist: list[str], frames: dict[str, pd.DataFrame],
              rebase: list[str] | None, tol: float) -> None:
        """Batched download into *frames*. When *rebase* is a list (the cheap 1mo
        window), a ticker whose window disagrees with its stored closes on the
        overlap dates (store.basis_shifted) was re-adjusted by Yahoo since the last
        pull — an ex-div/split/spin-off re-bases the WHOLE series, so splicing the
        window would strand every pre-window row on the stale basis. The window is
        queued for a period='max' re-pull instead (measured 2026-07: 30/231 stored
        names off basis this way; worst a 5.7% spin-off factor = a fabricated
        -7.8% one-day step inside live 126-bar indicator windows)."""
        for i in range(0, len(tlist), self.ycfg["batch_size"]):
            batch = tlist[i:i + self.ycfg["batch_size"]]
            if not batch:
                continue
            df = self._download(batch, period)
            for t in batch:
                try:
                    cols = [c for c in ["Close", "High", "Low", "Volume"] if c in df[t].columns]
                    sub = df[t][cols].rename(columns={"Close": "close", "High": "high",
                                                      "Low": "low", "Volume": "volume"})
                    sub = sub.dropna(subset=["close"])
                except KeyError:
                    log.warning("stocks: no data for %s", t)
                    continue
                if sub.empty:
                    continue
                if rebase is not None and store.basis_shifted(self.group, t, sub, tol=tol):
                    rebase.append(t)  # discard the window; re-pull full history below
                    continue
                frames[t] = sub

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        current = top10_union()
        if not current:
            raise RuntimeError("no holdings stored yet — run sector_holdings first")
        # Retention: keep fetching every name still on disk even after it exits the
        # top-N union (see _fetch_universe's docstring — the 2026-08-03 freeze
        # incident). tickers is therefore always >= current, never fewer.
        tickers = _fetch_universe(current, self.stored_series(), _dead_tickers())
        # daily runs fetch a short window, EXCEPT thin-volume/shallow/stale-tip
        # tickers which get a full-history backfill so a bad seed (or a frozen tip
        # older than the window can bridge) can never silently persist.
        if full_history:
            groups = [("max", tickers)]
        else:
            heal = [t for t in tickers if self._needs_full(t)]
            groups = [("1mo", [t for t in tickers if t not in heal])]
            if heal:
                log.info("stocks: full-history backfill for %d thin/shallow/stale tickers", len(heal))
                groups.append(("max", heal))
        frames: dict[str, pd.DataFrame] = {}
        rebase: list[str] = []
        tol = float(self.ycfg.get("upsert_basis_tol", 1e-3))
        for period, tlist in groups:
            self._pull(period, tlist, frames, rebase if period == "1mo" else None, tol)
        if rebase:
            log.info("stocks: %d name(s) on a re-adjusted basis — refetching "
                     "period='max': %s", len(rebase), rebase[:12])
            try:
                self._pull("max", rebase, frames, None, tol)
            except Exception as e:  # noqa: BLE001 — skip tonight; the guard re-flags next run
                log.warning("stocks: basis refetch failed for %d name(s) (%s) — "
                            "kept out of this run", len(rebase), e)
        # Never-silent: disclose the per-name requested-vs-returned gap BEFORE the
        # aggregate floor decides whether to raise — a run that dies on the floor is
        # exactly the run whose per-name detail is worth having, and a run that
        # survives it can still be hiding up to 30% silent drops.
        _report_missing_symbols(tickers, frames, current)
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"stocks: only {len(frames)}/{len(tickers)} returned")
        return frames


class StockFundamentalsAdapter(Adapter):
    """Best-effort valuation/quality snapshot per holding. Weekly cadence,
    LOW CONFIDENCE (unofficial yfinance fields, often missing)."""

    name = "stock_fundamentals"
    group = "stock_fundamentals"
    stale_after_days = 12

    FIELDS = {"forwardPE": "fwd_pe", "trailingPE": "pe",
              "profitMargins": "profit_margin", "revenueGrowth": "rev_growth",
              "returnOnEquity": "roe", "dividendYield": "div_yield",
              "marketCap": "mkt_cap"}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        import yfinance as yf
        tickers = top10_union()
        if not tickers:
            raise RuntimeError("no holdings stored yet")
        rows = []
        today = pd.Timestamp(date.today())
        for t in tickers:
            rec: dict = {"ticker": t}
            try:
                info = yf.Ticker(t).info or {}
                for src, dst in self.FIELDS.items():
                    rec[dst] = info.get(src)
                time.sleep(0.2)
            except Exception as e:  # noqa: BLE001
                log.debug("fundamentals %s: %s", t, e)
            rows.append(rec)
        df = pd.DataFrame(rows).set_index("ticker")
        if df.drop(columns=["mkt_cap"], errors="ignore").notna().sum().sum() < len(tickers):
            log.warning("fundamentals very sparse this run")
        wide = df.unstack().to_frame().T
        wide.index = [today]
        wide.columns = [f"{t}__{f}" for f, t in wide.columns]
        return {"snapshots": wide}


def latest_fundamentals(ticker: str) -> dict:
    df = store.read("stock_fundamentals", "snapshots")
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    out = {}
    for col, v in row.items():
        t, _, f = str(col).partition("__")
        if t == ticker and pd.notna(v):
            out[f] = v
    return out
