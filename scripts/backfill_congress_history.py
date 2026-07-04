"""One-time deep backfill of the congressional-trades store from Quiver's bulk endpoint.

The nightly collector (``collectors/quiver.py`` :class:`CongressAdapter`) reads
``/beta/live/congresstrading``, which returns only the most-recent ~1,000 rows
(~12 months). That is enough to keep the desk current but far too shallow for
per-member reliability (``engine/congress_members.py``): 12 months gives most
members single-digit trade counts, so every track record reads "insufficient".

Quiver's ``/beta/bulk/congresstrading`` endpoint returns the *full* history
(~114k rows back to 2012). This script fetches it once, normalizes its schema
onto the store's schema, and merges it into ``data/quiver/congress.parquet``
append-only + key-deduped (``keep='first'`` so the live collector's real
``_first_seen`` latency stamps win for overlapping rows; backfilled rows are
stamped with their public ``Filed`` date as the honest earliest-seen proxy).

After this runs, the nightly live collector keeps the tail current; this script
need only be re-run to refresh deep history (e.g. if Quiver restates old rows).

Usage::

    QUIVER_API_KEY=... python -m scripts.backfill_congress_history          # fetch from Quiver
    QUIVER_API_KEY unused: python -m scripts.backfill_congress_history --from-parquet /tmp/raw.parquet

The ``--from-parquet`` mode normalizes/merges a previously-fetched bulk dump
without hitting the API (used for offline verification).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

import pandas as pd
import requests

from lib import config

log = logging.getLogger("backfill_congress_history")

BULK_URL = "https://api.quiverquant.com/beta/bulk/congresstrading"

# STOCK-Act disclosure bands, keyed by the reported lower bound (Quiver's
# Trade_Size_USD == the store's Amount == the band floor, as a string).
_BANDS: list[tuple[int, str]] = [
    (1001, "$1,001 - $15,000"),
    (15001, "$15,001 - $50,000"),
    (50001, "$50,001 - $100,000"),
    (100001, "$100,001 - $250,000"),
    (250001, "$250,001 - $500,000"),
    (500001, "$500,001 - $1,000,000"),
    (1000001, "$1,000,001 - $5,000,000"),
    (5000001, "$5,000,001 - $25,000,000"),
    (25000001, "$25,000,001 - $50,000,000"),
    (50000001, "$50,000,001 - $100,000,000"),
]

# Bulk -> store column rename. Store's canonical columns are the live-endpoint
# schema written by CongressAdapter.
_RENAME = {
    "Name": "Representative",
    "Traded": "TransactionDate",
    "Filed": "ReportDate",
    "Chamber": "House",
    "Trade_Size_USD": "Amount",
    "excess_return": "ExcessReturn",
}

_TICKERTYPE = {"ST": "Stock", "OP": "Stock Option"}

# The store's dedup key (mirror collectors.quiver.CongressAdapter.key_cols).
KEY_COLS = ["BioGuideID", "Ticker", "TransactionDate", "Transaction", "Amount"]

# Canonical store column order (from the live-endpoint schema).
STORE_COLS = [
    "Representative", "BioGuideID", "ReportDate", "TransactionDate", "Ticker",
    "Transaction", "Range", "House", "Amount", "Party", "last_modified",
    "TickerType", "Description", "ExcessReturn", "PriceChange", "SPYChange",
    "_first_seen",
]


def _fetch_bulk() -> pd.DataFrame:
    key = config.secret("QUIVER_API_KEY")
    if not key:
        sys.exit("QUIVER_API_KEY not set — cannot fetch the bulk endpoint.")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    last = None
    for attempt in range(4):
        try:
            r = requests.get(BULK_URL, headers=headers, timeout=120)
            r.raise_for_status()
            return pd.DataFrame(r.json())
        except Exception as e:  # noqa: BLE001 — retry transient network/5xx
            last = e
            log.warning("bulk fetch attempt %d failed: %s", attempt + 1, str(e)[:120])
            time.sleep(3 * (attempt + 1))
    sys.exit(f"bulk fetch failed after retries: {last}")


def _floor_to_range(amount: str) -> str:
    """Reconstruct the STOCK-Act band string from the reported lower bound."""
    try:
        v = int(float(str(amount)))
    except (TypeError, ValueError):
        return ""
    band = ""
    for floor, label in _BANDS:
        if v >= floor:
            band = label
        else:
            break
    return band


def normalize(bulk: pd.DataFrame) -> pd.DataFrame:
    """Map the bulk-endpoint schema onto the store's live-endpoint schema."""
    df = bulk.rename(columns=_RENAME).copy()

    # Everything is stored as strings except the three Quiver return floats.
    df["Amount"] = df["Amount"].map(lambda x: "" if pd.isna(x) else str(x).strip())
    df["Range"] = df["Amount"].map(_floor_to_range)
    df["Transaction"] = df["Transaction"].astype(str).replace({"SALE": "Sale"})
    df["TickerType"] = df.get("TickerType", "").astype(str).map(
        lambda t: _TICKERTYPE.get(t, t))
    if "Description" not in df.columns:
        df["Description"] = df.get("Company", "")

    # Backfilled rows: earliest we *could* have seen them is the public filing
    # date (the store keeps _first_seen as an ISO string, not a timestamp).
    df["_first_seen"] = df["ReportDate"].astype("string")

    # ExcessReturn -> float (store dtype); PriceChange/SPYChange are live-only.
    df["ExcessReturn"] = pd.to_numeric(df["ExcessReturn"], errors="coerce")
    df["PriceChange"] = pd.NA
    df["SPYChange"] = pd.NA

    for col in STORE_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[STORE_COLS]


def merge_into_store(normalized: pd.DataFrame) -> tuple[int, int, int]:
    path = config.data_dir() / "quiver" / "congress.parquet"
    existing = pd.read_parquet(path)
    n_before = len(existing)

    # Align dtypes on the key columns so dedup compares like-for-like (all str).
    combined = pd.concat([existing, normalized], ignore_index=True)
    for c in KEY_COLS:
        combined[c] = combined[c].map(lambda x: "" if pd.isna(x) else str(x).strip())

    # keep='first' -> the existing live rows (with real _first_seen) win over
    # their bulk duplicates; bulk supplies everything older.
    deduped = combined.drop_duplicates(subset=KEY_COLS, keep="first").reset_index(drop=True)
    deduped = deduped.sort_values("TransactionDate").reset_index(drop=True)

    # Coerce back to the store's dtypes so the merged parquet is schema-clean
    # (string columns as nullable StringDtype, the three Quiver returns float64).
    float_cols = {"ExcessReturn", "PriceChange", "SPYChange"}
    for col in STORE_COLS:
        if col in float_cols:
            deduped[col] = pd.to_numeric(deduped[col], errors="coerce")
        else:
            deduped[col] = deduped[col].astype("string")

    n_added = len(deduped) - n_before
    deduped.to_parquet(path, index=False)
    return n_before, n_added, len(deduped)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-parquet", help="normalize/merge a pre-fetched bulk dump instead of calling the API")
    args = ap.parse_args()

    bulk = pd.read_parquet(args.from_parquet) if args.from_parquet else _fetch_bulk()
    log.info("bulk source: %d rows, %d cols", len(bulk), bulk.shape[1])

    normalized = normalize(bulk)
    tx = pd.to_datetime(normalized["TransactionDate"], errors="coerce")
    log.info("normalized: %d rows, %s → %s, %d distinct members",
             len(normalized), tx.min().date(), tx.max().date(),
             normalized["BioGuideID"].nunique())

    n_before, n_added, n_total = merge_into_store(normalized)
    log.info("merged into congress.parquet: %d → %d (+%d rows)", n_before, n_total, n_added)


if __name__ == "__main__":
    main()
