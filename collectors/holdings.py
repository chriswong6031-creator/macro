"""ETF holdings tracker for the active/thematic watchlist.

Daily snapshot per fund under data/holdings/<TICKER>/<YYYY-MM-DD>.parquet.
The engine diffs consecutive snapshots with flow normalization:

    expected_shares(t) = shares(t-1) * SO(t)/SO(t-1)
    active_decision(t) = actual_shares(t) - expected_shares(t)

which isolates manager decisions from creation/redemption pass-through.
N-PORT (EDGAR, ~60d lag) is a quarterly validation check only, never a live
signal. Per-sponsor fragility is documented in LIMITATIONS.md.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Non-equity holding lines that must NEVER be treated as a stock position: cash,
# FX/currency, money-market, equivalents, derivatives, receivables/payables.
# Their "shares" are a dollar/units BALANCE that swings arbitrarily on a near-zero
# base, so a flow-normalized share-diff explodes into absurd % (the radar's
# "CHATS Cash&Other −15,116,065%" / "BETZ Euro −338,977%" bug). This predicate is
# shared by the diff engine (active_changes_dir) AND the collector
# (collectors.etf_holdings._normalize), because already-stored snapshots are
# never re-cleaned — the diff layer can't trust the snapshot was filtered at write.
# Real foreign-listed EQUITIES (e.g. "000720 KS", "1211 HK", "8001 JP") are kept.
# --------------------------------------------------------------------------- #
_CURRENCY_CODES = {
    "USD", "USDOLLAR", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "HKD", "CNY",
    "CNH", "KRW", "TWD", "SGD", "INR", "BRL", "MXN", "ZAR", "SEK", "NOK", "DKK",
    "NZD", "ILS", "PLN", "THB", "IDR", "MYR", "PHP", "TRY", "CLP", "COP", "PEN",
}
_NON_EQUITY_TICKERS = _CURRENCY_CODES | {
    "", "-", "--", "—", "NAN", "NONE", "NULL", "<NA>", "N/A", "NA", "CASH",
}
# High-precision name patterns — kept tight to avoid flagging real issuers
# (e.g. "FutureFuel", "Cash America" are NOT matched: we anchor on cash-sleeve /
# currency / instrument phrasing, not bare substrings).
_NON_EQUITY_NAME_RE = re.compile(
    r"^\s*cash\b|cash\s*[&/+]|cash\s+and\b|cash\s+equiv|&\s*equivalent|"
    r"money\s*market|u\.?\s*s\.?\s*dollar\b|\bcurrency\b|cash\s*&\s*other|"
    r"\brepo\b|receivable|payable|net\s+other\s+asset|other\s+net\s+asset|"
    r"\bfx\s+forward|forward\s+contract|\bswap\b",
    re.IGNORECASE,
)


def is_non_equity_holding(ticker, name: str = "") -> bool:
    """True if a holdings row is cash / FX / money-market / a derivative /
    receivable — anything whose share count is a balance, not an equity position.
    Used to weed the radar's erroneous near-zero-base blow-ups."""
    tk = str(ticker).strip().upper()
    if tk in _NON_EQUITY_TICKERS:
        return True
    head = tk.split()[0] if tk.split() else ""
    if head in _CURRENCY_CODES:                     # e.g. "USD CASH", "EUR FWD"
        return True
    nm = str(name).strip()
    return bool(nm and _NON_EQUITY_NAME_RE.search(nm))


def _drop_non_equity(df: pd.DataFrame) -> pd.DataFrame:
    """Filter cash/FX/derivative rows from a holdings snapshot. Resolves the name
    column across sponsors (etf_holdings: 'name'; ARK csv: 'company')."""
    if df is None or df.empty or "ticker" not in df.columns:
        return df
    ncol = next((c for c in df.columns if c.lower() in ("name", "company")), None)
    names = df[ncol].astype(str) if ncol else pd.Series("", index=df.index)
    keep = [not is_non_equity_holding(t, n)
            for t, n in zip(df["ticker"].astype(str), names)]
    return df[pd.Series(keep, index=df.index)]


class HoldingsAdapter(Adapter):
    name = "holdings"
    group = "holdings"

    def __init__(self) -> None:
        self.cfg = config.load()["holdings"]
        self.dir = config.ROOT / config.load()["storage"]["holdings_dir"]

    # holdings snapshots are written directly (one file per fund per day),
    # so fetch() returns {} and reports via raising on total failure.
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        results, errors = {}, []
        for ticker, spec in self.cfg["watchlist"].items():
            try:
                snap = self._fetch_fund(ticker, spec)
                if snap is not None and not snap.empty:
                    self._write_snapshot(ticker, snap)
                    results[ticker] = len(snap)
            except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
                errors.append(f"{ticker}: {e}")
                log.warning("holdings %s failed: %s", ticker, e)
        if not results:
            raise RuntimeError(f"all watchlist funds failed: {errors}")
        # return a tiny summary series so the runner records freshness
        s = pd.DataFrame({"funds_ok": [len(results)]},
                         index=[pd.Timestamp(date.today())])
        return {"holdings_runs": s}

    def _write_snapshot(self, ticker: str, snap: pd.DataFrame) -> None:
        d = self.dir / ticker
        d.mkdir(parents=True, exist_ok=True)
        snap_date = snap["as_of"].iloc[0] if "as_of" in snap.columns else str(date.today())
        snap.to_parquet(d / f"{snap_date}.parquet")

    def _fetch_fund(self, ticker: str, spec: dict) -> pd.DataFrame | None:
        sponsor = spec["sponsor"]
        fn = getattr(self, f"_fetch_{sponsor}", None)
        if fn is None:
            raise ValueError(f"no adapter for sponsor '{sponsor}'")
        return fn(ticker, spec)

    # --- sponsor adapters -------------------------------------------------------
    def _fetch_ark(self, ticker: str, spec: dict) -> pd.DataFrame:
        r = self.http_get(spec["url"], retries=self.cfg["retries"])
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df = df.dropna(subset=["ticker"]) if "ticker" in df.columns else df
        keep = [c for c in ["date", "fund", "company", "ticker", "cusip",
                            "shares", "market_value_($)", "market_value",
                            "weight_(%)", "weight"] if c in df.columns]
        df = df[keep].rename(columns={"market_value_($)": "market_value",
                                      "weight_(%)": "weight"})
        df["shares"] = pd.to_numeric(
            df["shares"].astype(str).str.replace(",", ""), errors="coerce")
        df["as_of"] = str(pd.to_datetime(df["date"].iloc[0]).date()) \
            if "date" in df.columns else str(date.today())
        return df

    def _fetch_coinshares(self, ticker: str, spec: dict) -> pd.DataFrame:
        # URL resolved by recon (see config holdings.watchlist.WGMI.url).
        url = spec.get("url", "")
        if not url:
            raise RuntimeError("WGMI holdings URL not configured yet")
        r = self.http_get(url, retries=self.cfg["retries"])
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        share_col = next((c for c in df.columns if "share" in c or "quantity" in c), None)
        tick_col = next((c for c in df.columns if "ticker" in c or "symbol" in c), None)
        if not share_col or not tick_col:
            raise ValueError(f"unrecognized WGMI csv columns: {list(df.columns)}")
        df = df.rename(columns={share_col: "shares", tick_col: "ticker"})
        df["shares"] = pd.to_numeric(
            df["shares"].astype(str).str.replace(",", ""), errors="coerce")
        df["as_of"] = str(date.today())
        return df.dropna(subset=["shares"])


def active_changes_dir(d, window_d: int, *, min_base_frac: float = 1e-6) -> pd.DataFrame | None:
    """Flow-normalized share decisions from per-day snapshots in directory `d`.

    Isolates the manager's (or index's) actual share decisions from mechanical
    creation/redemption pass-through: expected_shares(t) = shares(t-1)·SO(t)/SO(t-1),
    where the fund SO ratio is proxied by the total share growth of positions
    common to both snapshots. Sponsor-agnostic, so any collector that writes
    snapshots with a `ticker`+`shares` schema (holdings/, etf_holdings/) reuses it.

    Two data-hygiene guards make the %-change trustworthy (every consumer — the
    radar, the dashboard panel, alerts — flows through here):
      1. cash/FX/derivative rows are dropped (is_non_equity_holding);
      2. a position whose expected base is a negligible fraction of the fund
         (< min_base_frac) is dropped, so a near-zero denominator can never
         explode the ratio (also kills placeholder contra-lines).
    """
    from pathlib import Path
    d = Path(d)
    if not d.exists():
        return None
    snaps = sorted(d.glob("*.parquet"))[-(window_d + 1):]
    if len(snaps) < 2:
        return None
    first_df = _drop_non_equity(pd.read_parquet(snaps[0]))
    last_df = _drop_non_equity(pd.read_parquet(snaps[-1]))
    first = first_df.set_index("ticker")["shares"]
    last = last_df.set_index("ticker")["shares"]
    # collapse any duplicate tickers, drop non-numeric residue
    first = pd.to_numeric(first, errors="coerce").groupby(level=0).sum()
    last = pd.to_numeric(last, errors="coerce").groupby(level=0).sum()
    common = first.index.intersection(last.index)
    if common.empty or first[common].sum() == 0:
        return None
    so_ratio = last[common].sum() / first[common].sum()
    expected = first * so_ratio
    diff = (last.reindex(expected.index) - expected).dropna()
    pct = 100 * diff / expected.replace(0, pd.NA)
    out = pd.DataFrame({"active_share_chg": diff, "active_chg_pct": pct})
    # denominator guard: drop positions whose expected base is a negligible
    # share of the fund — their % is meaningless and prone to blow-ups.
    exp_pos = expected[expected > 0]
    if not exp_pos.empty:
        frac = expected.reindex(out.index).fillna(0.0) / exp_pos.sum()
        out = out[frac >= min_base_frac]
    out["is_new"] = False
    # Brand-NEW positions — held now, absent a window ago. A manager INITIATING a
    # stake is the strongest "high interest" signal, but its % change is undefined
    # (no prior base), so we surface it with is_new=True and let downstream rank it
    # on the full CURRENT weight (frac=1) instead of a meaningless ratio.
    new_tk = last.index.difference(first.index)
    new_last = last.reindex(new_tk).dropna()
    new_last = new_last[new_last > 0]
    if len(new_last):
        out = pd.concat([out, pd.DataFrame({
            "active_share_chg": new_last, "active_chg_pct": float("nan"),
            "is_new": True})])
    out["window_start"], out["window_end"] = snaps[0].stem, snaps[-1].stem
    return out.sort_values("active_chg_pct")


def active_changes(ticker: str, window_d: int | None = None) -> pd.DataFrame | None:
    """Flow-normalized manager decisions over the last N snapshots (ARK watchlist)."""
    cfg = config.load()["holdings"]
    window_d = window_d or cfg["active_change_window_d"]
    d = config.ROOT / config.load()["storage"]["holdings_dir"] / ticker
    return active_changes_dir(d, window_d)
