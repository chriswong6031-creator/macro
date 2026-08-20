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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class AvailabilityProbe:
    """Result of probing a bounded flat-file window without downloading a file.

    ``reason`` is deliberately operational, not provider-specific prose.  It lets
    callers distinguish configuration, authorization, upstream publication and
    transport failures without ever logging credentials or request signatures.
    """

    available_date: date | None
    reason: str
    detail: str = ""


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
        # keep_default_na=False: 'NA' is a live listing (Nano Labs; National Bank of
        # Canada on TSX). na_values=[""] keeps blank -> NaN so dropna/to_numeric are unchanged.
        df = pd.read_csv(gz, keep_default_na=False, na_values=[""])
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


def _error_code(exc: Exception) -> tuple[str, int | None]:
    """Return the provider error code and HTTP status without importing botocore."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return type(exc).__name__, None
    error = response.get("Error") if isinstance(response.get("Error"), dict) else {}
    meta = response.get("ResponseMetadata") if isinstance(response.get("ResponseMetadata"), dict) else {}
    code = str(error.get("Code") or type(exc).__name__)
    try:
        status = int(meta.get("HTTPStatusCode"))
    except (TypeError, ValueError):
        status = None
    return code, status


def probe_available(product: str = "minute", lookback: int = 6, *,
                    end_date: date | None = None) -> AvailabilityProbe:
    """Probe the newest readable object in a bounded window and preserve why none is.

    A 403 is not the same thing as an unpublished 404, and neither is the same as
    missing configuration.  The former implementation collapsed all three into
    ``None``; the options-flow producer therefore reported success while frozen.
    """
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}")
    if not all(os.environ.get(k) for k in (
            "MASSIVE_S3_ENDPOINT", "MASSIVE_S3_ACCESS_KEY_ID", "MASSIVE_S3_SECRET_ACCESS_KEY")):
        return AvailabilityProbe(None, "configuration_missing")
    cl = client()
    if cl is None:
        return AvailabilityProbe(None, "client_initialization_failed")
    end = end_date or datetime.utcnow().date()
    missing = 0
    for i in range(lookback + 1):
        d = (pd.Timestamp(end) - pd.Timedelta(days=i)).date()
        try:
            cl.get_object(Bucket=_bucket(), Key=_key(product, d), Range="bytes=0-10")
            return AvailabilityProbe(d, "available")
        except Exception as exc:  # noqa: BLE001 — classification is the contract
            code, status = _error_code(exc)
            if status == 403 or code in {"403", "AccessDenied", "Forbidden"}:
                return AvailabilityProbe(None, "authorization_or_entitlement_failure",
                                         f"HTTP {status or 403} {code}")
            if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                missing += 1
                continue
            if status is not None and status >= 500:
                return AvailabilityProbe(None, "provider_service_failure",
                                         f"HTTP {status} {code}")
            return AvailabilityProbe(None, "transport_or_request_failure", code)
    return AvailabilityProbe(None, "upstream_file_absent",
                             f"{missing or lookback + 1} object(s) not published")


def latest_available(product: str = "minute", lookback: int = 6, *,
                     end_date: date | None = None) -> date | None:
    """Most recent date (<= today) whose flat file we can actually GET, scanning back
    `lookback` days. Used by the build to pick the freshest entitled day (T+1 cadence)."""
    return probe_available(product, lookback, end_date=end_date).available_date
