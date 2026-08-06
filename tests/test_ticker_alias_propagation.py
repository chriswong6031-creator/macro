"""Ticker-rename aliases reach EVERY price collector, not just one of them.

THE DEFECT (2026-08-05). Marsh McLennan changed its NYSE symbol MMC -> MRSH on
2026-01-14; Yahoo migrated the history onto MRSH and now 404s MMC as "possibly
delisted". scripts/fetch_basket_extras carried the MMC->MRSH entry in its own local
ALIASES dict and kept collecting Marsh fine (data/baskets/extras.parquet held MMC with
897 rows through 2026-07-31), while its DEEP-store sibling scripts/fetch_basket_ohlcv
carried a local dict with only FI->FISV. So data/baskets/ohlcv/MMC.parquet never
existed from the day that store was created (2026-06-19), the `insurance` basket
rendered on 18/19 members and `us_sector_financials` on 75/76, and the coverage
receipts disclosed it as merely "structural". A shim present in one consumer hid the
missing shim in its sibling.

These pin BEHAVIOUR, not the constant: a test that only compared the two modules'
ALIASES would pass vacuously now that both import the same object (it would still pass
if the shared map were empty). Each test below drives the actual fetch path and asserts
the vendor symbol that goes OUT and the store key that comes BACK.

Run: python -m pytest tests/test_ticker_alias_propagation.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.ticker_aliases import YAHOO_FETCH_ALIASES, fetch_symbol, store_key  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


def _write_membership(tmp_path: Path, tickers: list[str]) -> None:
    p = tmp_path / "baskets" / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"baskets": {"b1": {"members": [{"ticker": t} for t in tickers]}}}))


def _ohlcv_frame(n: int = 40) -> pd.DataFrame:
    idx = pd.bdate_range(end="2026-08-04", periods=n)
    idx.name = "Date"
    return pd.DataFrame({c: 1.0 for c in ("open", "high", "low", "close", "volume")}, index=idx)


# ------------------------------------------------------------------ the map itself
def test_marsh_rename_is_aliased():
    """The rename that caused the incident stays mapped. MMC is dead at the vendor; a
    bare MMC request returns nothing, so the membership ticker must resolve to MRSH."""
    assert fetch_symbol("MMC") == "MRSH"
    assert store_key("MRSH") == "MMC"
    assert fetch_symbol("AAPL") == "AAPL"      # unaliased names pass through untouched
    assert store_key("AAPL") == "AAPL"


def test_alias_map_is_injective():
    """Two membership tickers mapping to one vendor symbol would silently store one
    company's tape under both keys — no downstream check can see that."""
    vendor = list(YAHOO_FETCH_ALIASES.values())
    assert len(vendor) == len(set(vendor)), f"duplicate vendor symbol in the alias map: {vendor}"
    collisions = set(YAHOO_FETCH_ALIASES) & set(vendor)
    assert not collisions, f"a ticker is both a key and a vendor symbol: {collisions}"


# ------------------------------------------------- deep OHLCV store (the missing shim)
def test_deep_store_requests_vendor_symbol_and_stores_membership_ticker(tmp_path, monkeypatch):
    """The regression, driven end to end: fetch under MRSH, write MMC.parquet.

    Fails on the pre-fix code — that local ALIASES held only FI->FISV, so MMC went out
    as "MMC", came back empty, and no file was ever written."""
    from scripts import fetch_basket_ohlcv as mod

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["AAPL", "MMC"])

    asked: list[list[str]] = []

    def fake_download(tickers: list[str]) -> dict[str, pd.DataFrame]:
        asked.append(list(tickers))
        # The vendor answers under ITS symbol only — exactly what Yahoo does today.
        return {t: _ohlcv_frame() for t in tickers if t in ("AAPL", "MRSH")}

    monkeypatch.setattr(mod, "_download_ohlcv", fake_download)
    assert mod.main([]) == 0

    assert asked, "the collector never issued a download"
    assert "MRSH" in asked[0], f"deep store asked the vendor for {asked[0]} — MMC 404s"
    assert "MMC" not in asked[0], "the dead pre-rename symbol must not be requested"

    odir = tmp_path / "baskets" / "ohlcv"
    assert (odir / "MMC.parquet").exists(), "tape stored under the vendor symbol, not the ticker"
    assert not (odir / "MRSH.parquet").exists(), "MRSH must not become a second store key"
    assert len(pd.read_parquet(odir / "MMC.parquet")) == 40


def test_both_basket_collectors_share_one_alias_map():
    """One map, two readers — the shape that makes a future rename a one-line fix.
    Identity, not equality: two dicts that merely happen to match today would drift."""
    from scripts import fetch_basket_extras, fetch_basket_ohlcv

    assert fetch_basket_ohlcv.ALIASES is YAHOO_FETCH_ALIASES
    assert fetch_basket_extras.ALIASES is YAHOO_FETCH_ALIASES


# ------------------------------------------------------------------ the yahoo adapter
def test_yahoo_adapter_slices_response_by_vendor_symbol():
    """collectors.yahoo._extract is handed the CONFIG ticker but must slice the vendor's
    block. MMC is in stock_search.extra_tickers, so without this the searchable library
    loses Marsh entirely (its Stooq safety net now answers a JS challenge, not CSV)."""
    from collectors.yahoo import YahooAdapter

    idx = pd.bdate_range(end="2026-08-04", periods=5)
    df = pd.DataFrame(
        {("MRSH", c): 1.0 for c in ("Close", "Adj Close", "Volume")}, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)

    out = YahooAdapter._extract(object(), df, "MMC", set(), [])
    assert out is not None, "adapter could not find the renamed name in the response"
    assert list(out.columns) == ["close_price", "close", "volume"]
    assert len(out) == 5


def test_yahoo_adapter_requests_vendor_symbols(monkeypatch):
    """The batch that goes to yfinance carries MRSH; the frame comes back keyed MMC."""
    from collectors.yahoo import YahooAdapter

    cfg = {"tickers": {"grp": ["AAPL", "MMC"]}, "batch_size": 80, "retries": 1,
           "backoff_base_s": 0, "upsert_basis_tol": 1e-3}
    monkeypatch.setattr(config, "load", lambda: {"yahoo": cfg})

    a = YahooAdapter()
    asked: list[list[str]] = []
    idx = pd.bdate_range(end="2026-08-04", periods=5)

    def fake_download(batch, period):
        asked.append(list(batch))
        cols = [(t, c) for t in batch for c in ("Close", "Adj Close", "Volume")]
        out = pd.DataFrame({c: 1.0 for c in cols}, index=idx)
        out.columns = pd.MultiIndex.from_tuples(out.columns)
        return out

    monkeypatch.setattr(a, "_download", fake_download)
    monkeypatch.setattr(a, "_rebase_shifted", lambda frames, ohlc: [])
    frames = a.fetch()

    assert "MRSH" in asked[0] and "MMC" not in asked[0], f"asked vendor for {asked[0]}"
    assert "MMC" in frames and "MRSH" not in frames, f"stored under {sorted(frames)}"


# ------------------------------------------------------------------ the GLD config pin
def test_gld_is_in_a_yahoo_ticker_group():
    """data/yahoo/GLD.parquet froze at 2026-07-14 for three weeks while GDX/GDXJ/GC=F
    stayed current, because GLD sat in NO group here — seeded once by a research pass and
    maintained by nothing (the ^GSPC failure class). Nothing else fetches it: membership
    of a group IS the collection contract."""
    cfg = yaml.safe_load((_ROOT / "config.yml").read_text())
    grouped = {t for grp in cfg["yahoo"]["tickers"].values() for t in grp}
    assert "GLD" in grouped, (
        "GLD fell out of config.yahoo.tickers — it will silently stop accruing while its "
        "gold-complex siblings stay fresh, exactly as it did on 2026-07-14")


@pytest.mark.parametrize("ticker", sorted(YAHOO_FETCH_ALIASES))
def test_aliased_tickers_are_not_also_collected_raw(ticker):
    """A config group listing the aliased ticker is fine (it resolves through the map),
    but listing the VENDOR symbol as well would collect the same company twice under two
    keys and double-count it in any breadth or basket ratio."""
    cfg = yaml.safe_load((_ROOT / "config.yml").read_text())
    grouped = {t for grp in cfg["yahoo"]["tickers"].values() for t in grp}
    extras = set((cfg.get("stock_search") or {}).get("extra_tickers") or [])
    vendor = YAHOO_FETCH_ALIASES[ticker]
    assert vendor not in (grouped | extras), (
        f"{vendor} is the vendor symbol for {ticker}; collecting both mints two stores "
        "for one company")
