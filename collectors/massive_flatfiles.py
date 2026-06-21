"""collectors/massive_flatfiles.py — massive.com S3 flat-file reader: the OPTIONS-FLOW data foundation.

massive.com (a Polygon.io-compatible vendor) exposes daily OPRA flat files on an
S3-compatible store (files.massive.com, bucket 'flatfiles'). Our account is ENTITLED to
download the AGGREGATE products (verified by probe 2026-06-21):

  • us_options_opra/minute_aggs_v1/  — per-contract per-MINUTE OHLCV + volume + txns (~18 MB/day)
  • us_options_opra/day_aggs_v1/     — per-contract DAILY OHLCV + volume + txns (~3 MB/day)
  • us_stocks_sip/day_aggs_v1/       — stock daily bars (for option/stock volume ratios)

…over a ROLLING RECENT WINDOW (~2025→present). It is NOT entitled to the per-trade tape
(trades_v1) or the NBBO quotes (quotes_v1) — both return 403 via flat-file AND REST. So the
flow engine signs volume with a MINUTE TICK-RULE (the option's own minute-close tick),
which is the honest fallback when the trade-level tape and NBBO are unavailable; true
quote-rule signing is an optional Databento calibration (collectors/databento_tbbo.py).

This reader downloads one day's gzip, filters to the requested underlyings, parses the OCC
option symbol, and caches the filtered frame to data/massive_flat/ so re-runs never
re-download. Graceful by construction: no S3 creds / 403 / missing file -> empty frame, never
raises into the build (matches the FRED-vintages / polygon-gex accrual discipline).

Schema (aggregates): ticker, volume, open, close, high, low, window_start (ns), transactions.
OCC option symbol: O:<UNDERLYING><YYMMDD><C|P><strike*1000, 8 digits>.
"""
from __future__ import annotations

import gzip
import io
import logging
import os
import re
from datetime import date, datetime

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

BUCKET_DEFAULT = "flatfiles"
OPT_RE = re.compile(r"^O:([A-Z]+)(\d{6})([CP])(\d{8})$")
PRODUCTS = {
    "minute": "us_options_opra/minute_aggs_v1",
    "day": "us_options_opra/day_aggs_v1",
    "stock_day": "us_stocks_sip/day_aggs_v1",
}


# --------------------------------------------------------------------------- #
# S3 client (env-driven; None when not configured)
# --------------------------------------------------------------------------- #
def client():
    ep = os.environ.get("MASSIVE_S3_ENDPOINT")
    ak = os.environ.get("MASSIVE_S3_ACCESS_KEY_ID")
    sk = os.environ.get("MASSIVE_S3_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk,
                            config=Config(signature_version="s3v4",
                                          retries={"max_attempts": 3, "mode": "standard"}))
    except Exception as e:  # noqa: BLE001
        log.warning("massive_flat: boto3 client init failed: %s", e)
        return None


def enabled() -> bool:
    return client() is not None


def _bucket() -> str:
    return os.environ.get("MASSIVE_S3_BUCKET", BUCKET_DEFAULT)


def _key(product: str, d: date) -> str:
    base = PRODUCTS[product]
    return f"{base}/{d.year:04d}/{d.month:02d}/{d.isoformat()}.csv.gz"


# --------------------------------------------------------------------------- #
# OCC symbol parsing
# --------------------------------------------------------------------------- #
def parse_occ(ticker: str):
    """O:SPY260620C00600000 -> (underlying, expiry_date, is_call, strike). None on miss."""
    m = OPT_RE.match(str(ticker))
    if not m:
        return None
    u, ymd, cp, strike = m.groups()
    try:
        exp = datetime.strptime(ymd, "%y%m%d").date()
    except ValueError:
        return None
    return u, exp, (cp == "C"), int(strike) / 1000.0


def _add_occ_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorised OCC parse -> underlying / expiry / is_call / strike columns."""
    ex = df["ticker"].str.extract(OPT_RE)
    df = df.assign(
        underlying=ex[0],
        expiry=pd.to_datetime(ex[1], format="%y%m%d", errors="coerce"),
        is_call=ex[2].eq("C"),
        strike=pd.to_numeric(ex[3], errors="coerce") / 1000.0,
    )
    return df


def _uni_tag(underlyings) -> str:
    """Stable cache tag for a universe filter — so a 2-name fetch can't be served to a
    10-name caller (the cache key MUST include the filter)."""
    if not underlyings:
        return "all"
    import hashlib
    u = sorted(set(underlyings))
    return f"u{len(u)}_{hashlib.md5(','.join(u).encode()).hexdigest()[:8]}"


def _cache_path(product: str, d: date, underlyings=None) -> "os.PathLike":
    p = config.data_dir() / "massive_flat" / product
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{d.isoformat()}_{_uni_tag(underlyings)}.parquet"


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def fetch_aggs(d: date, product: str = "minute", underlyings: list[str] | None = None,
               *, use_cache: bool = True) -> pd.DataFrame:
    """One day's option aggregates filtered to `underlyings` (None = all), with OCC columns
    parsed. Cached to data/massive_flat/. Empty frame on no-creds / 403 / missing file."""
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}")
    uni = set(underlyings) if underlyings else None
    cache = _cache_path(product, d, underlyings)         # universe is part of the key
    if use_cache and cache.exists():
        try:
            return pd.read_parquet(cache)                # already the exact requested universe
        except Exception:  # noqa: BLE001 — corrupt cache -> refetch
            pass
    cl = client()
    if cl is None:
        log.info("massive_flat: no S3 creds — skip (%s %s)", product, d)
        return pd.DataFrame()
    key = _key(product, d)
    try:
        obj = cl.get_object(Bucket=_bucket(), Key=key)
        raw = obj["Body"].read()
    except Exception as e:  # noqa: BLE001 — 403/404/weekend -> empty
        log.info("massive_flat: get %s failed (%s) — empty", key, str(e)[:80])
        return pd.DataFrame()
    try:
        gz = gzip.GzipFile(fileobj=io.BytesIO(raw))
        df = pd.read_csv(gz)
    except Exception as e:  # noqa: BLE001
        log.warning("massive_flat: parse %s failed: %s", key, e)
        return pd.DataFrame()
    if product == "stock_day":
        # stock bars: ticker is the plain symbol; filter directly
        if uni is not None:
            df = df[df["ticker"].isin(uni)]
        return df.reset_index(drop=True)
    # options: parse OCC, filter to underlyings
    if uni is not None:
        pref = df["ticker"].str.extract(r"^O:([A-Z]+)\d")[0]
        df = df[pref.isin(uni)]
    if df.empty:
        return df
    df = _add_occ_cols(df).dropna(subset=["underlying", "strike"])
    df = df.reset_index(drop=True)
    if use_cache:
        try:
            df.to_parquet(cache)
        except Exception:  # noqa: BLE001 — cache is a nicety
            pass
    return df


def latest_available(product: str = "minute", lookback: int = 6) -> date | None:
    """Most recent date (<= today) whose flat file we can actually GET, scanning back
    `lookback` days. Used by the build to pick the freshest entitled day (T+1 cadence)."""
    cl = client()
    if cl is None:
        return None
    today = pd.Timestamp(datetime.utcnow().date())
    for i in range(lookback + 1):
        d = (today - pd.Timedelta(days=i)).date()
        try:
            cl.get_object(Bucket=_bucket(), Key=_key(product, d), Range="bytes=0-10")
            return d
        except Exception:  # noqa: BLE001
            continue
    return None
