"""FINRA corporate bond market breadth / sentiment collector — CCW W5.

Three datasets from the FINRA Query API (api.finra.org):
  1. corporateMarketBreadth — daily advances/declines/unchanged by productCategory
     (all securities | investment grade | high yield | convertibles)
  2. corporateMarketSentiment — daily volume/trades by (productCategory × tradeType)
     productCategory (6 values) = the buy/sell/dealer dimension:
       {affiliate buy, affiliate sell, all securities, customer buy, customer sell, inter-dealer}
     tradeType (6 values) = the product/grade dimension:
       {all securities, church bonds, convertible bonds, equity linked notes, high yield,
        investment grade}
     → 6 × 6 = 36 rows/day; wire buy/sell exposure off productCategory
  3. corporatesAndAgenciesCappedVolume — monthly trade-size-bucket breakdown by
     gradeCode (IG/HY/AGCY) × 144AFlag (Y/N)

Auth: OAuth 2.0 client-credentials.
  Token URL: POST https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token
  Creds from env: FINRA_API_CLIENT_ID / FINRA_API_CLIENT_SECRET
  If either env var is absent, adapter skips cleanly (returns empty summary, logs INFO).

Incremental fetch strategy:
  - breadth / sentiment: POST body with dateRangeFilters (the only path that reaches
    the full history to 2023-07-17; unfiltered GET returns a ~30-month rolling window
    starting 2023-12-14 which misses the first ~5 months of history). On first run
    (no stored data), fetches full history from 2023-07-17 in 90-day pages. On
    subsequent runs, fetches since (last_stored_date − 5 days) to handle late-arrives.
  - cappedVolume: monthly; same paged strategy but 365-day pages.

Upsert key:
  - breadth: (tradeReportDate, productCategory) → dedup keep-last
  - sentiment: (tradeReportDate, productCategory, tradeType) → dedup keep-last
  - cappedVolume: (tradeReportDate, gradeCode, flag_144a) → dedup keep-last
    where tradeReportDate is constructed as "{tradeYear}-{tradeMonth:02d}-01"

Store: direct parquet write (NOT lib.store.upsert). lib.store.upsert assumes single-row-
per-datetime index and drops duplicates — it collapses multi-row-per-date long-format
data to a single row per date. These three datasets have N rows per date (4/30/18+),
so a custom _write_long_parquet helper reads existing, concatenates, deduplicates on
composite key, and writes back. Parquet paths:
  data/corp_bonds/finra_corporateMarketBreadth.parquet
  data/corp_bonds/finra_corporateMarketSentiment.parquet
  data/corp_bonds/finra_corporatesAndAgenciesCappedVolume.parquet
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

TOKEN_URL = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token"
API_BASE = "https://api.finra.org/data/group/fixedIncomeMarket/name"

# Known earliest dates (discovered 2026-07-14 via POST dateRangeFilter binary search)
BREADTH_HISTORY_START = "2023-07-17"
SENTIMENT_HISTORY_START = "2023-07-17"
CAPPED_VOLUME_HISTORY_START = "2023-01-01"  # monthly; first month available (January 2023)

# Max page size per the FINRA API (documented 5000; confirmed in practice)
PAGE_LIMIT = 5000

# Rate-limiting: sleep between pages (these datasets are ~3 req/night normally)
PAGE_SLEEP_S = 0.5

# Incremental lookback: re-fetch this many days before last stored date
INCREMENTAL_LOOKBACK_DAYS = 5

# Token expiry headroom: re-acquire if fewer than this many seconds remain
TOKEN_EXPIRY_HEADROOM_S = 60


# ------------------------------------------------------------------
# Adapter
# ------------------------------------------------------------------

class FinraCorpBondsAdapter(Adapter):
    """CCW W5: FINRA corporate bond breadth / sentiment / capped-volume collector.

    group='corp_bonds' — same as W1 (CorpBondHoldingsAdapter). The store sub-path
    is data/corp_bonds/finra/ so there is no name collision. Sharing the group means
    both adapters surface in `--only corp_bonds` or `--group corp_bonds` selectors,
    which is correct: they are both CCW data-spine inputs.
    """

    name = "finra_corp_bonds"
    group = "corp_bonds"
    stale_after_days = 3  # daily data; weekend gaps are 2 days

    def __init__(self) -> None:
        self._client_id: str | None = os.environ.get("FINRA_API_CLIENT_ID")
        self._client_secret: str | None = os.environ.get("FINRA_API_CLIENT_SECRET")
        self._token: str | None = None
        self._token_expires_at: float = 0.0  # epoch seconds
        self._dir = config.data_dir() / "corp_bonds"
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Collect all three FINRA datasets; return summary frame keyed 'finra_corp_bonds_runs'."""
        if not self._client_id or not self._client_secret:
            log.info(
                "finra_corp_bonds: FINRA_API_CLIENT_ID / FINRA_API_CLIENT_SECRET not set "
                "— skipping (set env vars to enable CCW-W5 data lane)"
            )
            return {"finra_corp_bonds_runs": _empty_summary()}

        results: dict[str, int] = {}
        errors: list[str] = []

        for ds_name, method in [
            ("corporateMarketBreadth", self._collect_breadth),
            ("corporateMarketSentiment", self._collect_sentiment),
            ("corporatesAndAgenciesCappedVolume", self._collect_capped_volume),
        ]:
            try:
                n = method(full_history=full_history)
                results[ds_name] = n
                log.info("finra_corp_bonds: %s → %d rows upserted", ds_name, n)
            except Exception as e:  # noqa: BLE001 — one dataset must not kill others
                errors.append(f"{ds_name}: {e}")
                log.warning("finra_corp_bonds: %s failed: %s", ds_name, e)

        if errors:
            log.warning("finra_corp_bonds: partial errors: %s", errors)

        summary = pd.DataFrame(
            {ds: [n] for ds, n in results.items()},
            index=[pd.Timestamp(date.today())],
        )
        return {"finra_corp_bonds_runs": summary}

    # ------------------------------------------------------------------
    # Dataset collectors
    # ------------------------------------------------------------------

    def _collect_breadth(self, full_history: bool) -> int:
        """corporateMarketBreadth: (date × productCategory) long rows."""
        parquet_name = "finra_corporateMarketBreadth"
        key_cols = ["tradeReportDate", "productCategory"]
        start_date = self._incremental_start(parquet_name, BREADTH_HISTORY_START, full_history)
        end_date = date.today().isoformat()

        frames = self._fetch_paged_post(
            dataset="corporateMarketBreadth",
            date_field="tradeReportDate",
            start_date=start_date,
            end_date=end_date,
        )
        if not frames:
            log.info("finra_corp_bonds: corporateMarketBreadth — no new rows in [%s, %s]",
                     start_date, end_date)
            return 0

        df = pd.concat(frames, ignore_index=True)
        df["tradeReportDate"] = pd.to_datetime(df["tradeReportDate"]).dt.date.astype(str)
        df = (
            df.sort_values("tradeReportDate")
              .drop_duplicates(subset=key_cols, keep="last")
              .reset_index(drop=True)
        )
        return self._write_long_parquet(parquet_name, df, key_cols=key_cols)

    def _collect_sentiment(self, full_history: bool) -> int:
        """corporateMarketSentiment: (date × productCategory × tradeType) long rows.

        productCategory (6 values) = the buy/sell/dealer dimension:
          affiliate buy | affiliate sell | all securities | customer buy | customer sell | inter-dealer
        tradeType (6 values) = the product/grade dimension:
          all securities | church bonds | convertible bonds | equity linked notes | high yield | investment grade
        Wire buy/sell exposure off productCategory, NOT tradeType.
        """
        parquet_name = "finra_corporateMarketSentiment"
        key_cols = ["tradeReportDate", "productCategory", "tradeType"]
        start_date = self._incremental_start(parquet_name, SENTIMENT_HISTORY_START, full_history)
        end_date = date.today().isoformat()

        frames = self._fetch_paged_post(
            dataset="corporateMarketSentiment",
            date_field="tradeReportDate",
            start_date=start_date,
            end_date=end_date,
        )
        if not frames:
            log.info("finra_corp_bonds: corporateMarketSentiment — no new rows in [%s, %s]",
                     start_date, end_date)
            return 0

        df = pd.concat(frames, ignore_index=True)
        df["tradeReportDate"] = pd.to_datetime(df["tradeReportDate"]).dt.date.astype(str)
        df = (
            df.sort_values("tradeReportDate")
              .drop_duplicates(subset=key_cols, keep="last")
              .reset_index(drop=True)
        )
        return self._write_long_parquet(parquet_name, df, key_cols=key_cols)

    def _collect_capped_volume(self, full_history: bool) -> int:
        """corporatesAndAgenciesCappedVolume: monthly, many numeric columns.

        Key fields: tradeYear, tradeMonth, gradeCode, 144AFlag.
        Date represented as first-of-month via tradeReportDate field (YYYY-MM-01).
        """
        parquet_name = "finra_corporatesAndAgenciesCappedVolume"
        start_date = self._incremental_start_monthly(
            parquet_name, CAPPED_VOLUME_HISTORY_START, full_history
        )

        # cappedVolume: GET endpoint; dataset has ~2232 rows; page through with offset.
        frames = self._fetch_paged_get(dataset="corporatesAndAgenciesCappedVolume")
        if not frames:
            log.info("finra_corp_bonds: corporatesAndAgenciesCappedVolume — no rows returned")
            return 0

        df = pd.concat(frames, ignore_index=True)

        # Normalize date: ALWAYS derive tradeReportDate from tradeYear/tradeMonth.
        # The API's tradeReportDate field for this dataset is corrupted — it returns a
        # +1-year-shifted value (e.g. tradeYear=2023, tradeMonth=1 → "2024-01-01").
        # Using the API field collapses two real years onto overlapping month-01 strings.
        # Unconditionally overwrite whatever the API returns.
        df["tradeReportDate"] = (
            df["tradeYear"].astype(str)
            + "-"
            + df["tradeMonth"].astype(str).str.zfill(2)
            + "-01"
        )

        key_cols = (["tradeReportDate", "gradeCode", "144AFlag"]
                    if "144AFlag" in df.columns else ["tradeReportDate", "gradeCode"])
        df = (
            df.sort_values("tradeReportDate")
              .drop_duplicates(subset=key_cols, keep="last")
              .reset_index(drop=True)
        )

        # Filter to start_date onward for incremental runs
        df = df[df["tradeReportDate"] >= start_date].reset_index(drop=True)
        if df.empty:
            log.info("finra_corp_bonds: corporatesAndAgenciesCappedVolume — no new rows since %s",
                     start_date)
            return 0

        return self._write_long_parquet(parquet_name, df, key_cols=key_cols)

    # ------------------------------------------------------------------
    # Incremental start-date helpers
    # ------------------------------------------------------------------

    def _last_stored_date(self, parquet_name: str, date_col: str = "tradeReportDate") -> date | None:
        """Return the max date in the stored parquet (or None if absent)."""
        p = self._dir / f"{parquet_name}.parquet"
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p, columns=[date_col])
            if df.empty or date_col not in df.columns:
                return None
            max_val = pd.to_datetime(df[date_col], errors="coerce").max()
            if pd.isna(max_val):
                return None
            return max_val.date()
        except Exception as e:  # noqa: BLE001
            log.warning("finra_corp_bonds: could not read last date from %s: %s", parquet_name, e)
            return None

    def _incremental_start(self, parquet_name: str, history_start: str,
                            full_history: bool) -> str:
        if full_history:
            return history_start
        last = self._last_stored_date(parquet_name)
        if last is None:
            log.info("finra_corp_bonds: %s — no prior store, full backfill from %s",
                     parquet_name, history_start)
            return history_start
        # Back up 5 days to catch late-arriving corrections
        start = last - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)
        return start.isoformat()

    def _incremental_start_monthly(self, parquet_name: str, history_start: str,
                                    full_history: bool) -> str:
        if full_history:
            return history_start
        last = self._last_stored_date(parquet_name)
        if last is None:
            return history_start
        # For monthly data, back up ~60 days (2 months) to catch revisions
        start = last - timedelta(days=60)
        return start.isoformat()

    # ------------------------------------------------------------------
    # Parquet write helper (multi-row-per-date; bypasses lib.store.upsert)
    # ------------------------------------------------------------------

    def _write_long_parquet(self, parquet_name: str, new_df: pd.DataFrame,
                             key_cols: list[str]) -> int:
        """Upsert new_df into data/corp_bonds/<parquet_name>.parquet.

        lib.store.upsert drops duplicate index rows (keeps one row per timestamp),
        which destroys multi-row-per-date long-format data. This helper:
          1. Reads the existing parquet (if any).
          2. Concatenates old + new.
          3. Deduplicates on key_cols (keep last = new wins).
          4. Sorts by first key column (tradeReportDate) and writes back.
        Returns the number of rows in the merged store.
        """
        p = self._dir / f"{parquet_name}.parquet"
        if p.exists():
            try:
                old_df = pd.read_parquet(p)
                merged = pd.concat([old_df, new_df], ignore_index=True)
            except Exception as e:  # noqa: BLE001
                log.warning("finra_corp_bonds: could not read %s, replacing: %s", parquet_name, e)
                merged = new_df.copy()
        else:
            merged = new_df.copy()

        # Dedup: new rows win (they came last in the concat)
        merged = (
            merged.sort_values(key_cols[0] if key_cols else merged.columns[0])
                  .drop_duplicates(subset=key_cols, keep="last")
                  .reset_index(drop=True)
        )
        merged.to_parquet(p)
        log.info("finra_corp_bonds: wrote %s (%d rows, %s → %s)",
                 parquet_name, len(merged),
                 merged[key_cols[0]].min() if key_cols else "?",
                 merged[key_cols[0]].max() if key_cols else "?")
        return len(merged)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Acquire or return cached OAuth bearer token.

        Uses 1 retry on failure. Never logs the token or secrets.
        """
        now = time.monotonic()
        if self._token and now < self._token_expires_at - TOKEN_EXPIRY_HEADROOM_S:
            return self._token

        for attempt in range(2):
            try:
                r = requests.post(
                    TOKEN_URL,
                    params={"grant_type": "client_credentials"},
                    auth=(self._client_id, self._client_secret),
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
                self._token = data["access_token"]
                expires_in = int(data.get("expires_in", 3600))
                self._token_expires_at = now + expires_in
                log.info("finra_corp_bonds: token acquired (expires_in=%ds)", expires_in)
                return self._token
            except Exception as e:  # noqa: BLE001
                if attempt == 0:
                    log.warning("finra_corp_bonds: token acquisition failed (attempt 1/2): %s; retrying", e)
                    time.sleep(2)
                else:
                    raise RuntimeError(f"finra_corp_bonds: token acquisition failed after 2 attempts: {e}") from e

        raise RuntimeError("finra_corp_bonds: token acquisition failed (unreachable)")  # pragma: no cover

    def _api_headers(self) -> dict[str, str]:
        tok = self._get_token()
        return {
            "Authorization": f"Bearer {tok}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _fetch_paged_post(
        self,
        dataset: str,
        date_field: str,
        start_date: str,
        end_date: str,
    ) -> list[pd.DataFrame]:
        """POST-paginated fetch with dateRangeFilters.

        The POST body dateRangeFilter is the only path that reaches the full history
        back to 2023-07-17 (unfiltered GET only returns a rolling ~30-month window).
        Pages in 90-day windows to keep page sizes manageable.
        """
        url = f"{API_BASE}/{dataset}"
        frames: list[pd.DataFrame] = []

        window_start = date.fromisoformat(start_date)
        overall_end = date.fromisoformat(end_date)

        while window_start <= overall_end:
            window_end = min(window_start + timedelta(days=90), overall_end)
            offset = 0

            while True:
                body: dict[str, Any] = {
                    "dateRangeFilters": [{
                        "fieldName": date_field,
                        "startDate": window_start.isoformat(),
                        "endDate": window_end.isoformat(),
                    }],
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                }
                try:
                    r = requests.post(url, json=body, headers=self._api_headers(), timeout=60)
                except Exception as e:  # noqa: BLE001
                    log.warning("finra_corp_bonds: %s POST failed at offset=%d: %s", dataset, offset, e)
                    break

                if r.status_code == 204:
                    # No content for this date range window
                    break
                if r.status_code != 200:
                    log.warning("finra_corp_bonds: %s HTTP %d at offset=%d",
                                dataset, r.status_code, offset)
                    break

                try:
                    data = r.json()
                except Exception:
                    log.warning("finra_corp_bonds: %s JSON parse error at offset=%d", dataset, offset)
                    break

                if not isinstance(data, list) or not data:
                    break

                frames.append(pd.DataFrame(data))
                log.info("finra_corp_bonds: %s [%s→%s] offset=%d → %d rows",
                         dataset, window_start, window_end, offset, len(data))

                if len(data) < PAGE_LIMIT:
                    break  # last page
                offset += PAGE_LIMIT
                time.sleep(PAGE_SLEEP_S)

            window_start = window_end + timedelta(days=1)
            time.sleep(PAGE_SLEEP_S)

        return frames

    def _fetch_paged_get(self, dataset: str) -> list[pd.DataFrame]:
        """GET-paginated full fetch (no date filter; used for cappedVolume)."""
        url = f"{API_BASE}/{dataset}"
        frames: list[pd.DataFrame] = []
        offset = 0

        while True:
            try:
                r = requests.get(
                    url,
                    params={"limit": PAGE_LIMIT, "offset": offset},
                    headers=self._api_headers(),
                    timeout=60,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("finra_corp_bonds: %s GET failed at offset=%d: %s", dataset, offset, e)
                break

            if r.status_code == 204:
                break
            if r.status_code == 400:
                # 400 with "Offset of N is larger than..." means we're past the end
                try:
                    msg = r.json().get("message", "")
                    if "larger than the number of records" in msg:
                        break
                except Exception:
                    pass
                log.warning("finra_corp_bonds: %s HTTP 400 at offset=%d: %s",
                            dataset, offset, r.text[:200])
                break
            if r.status_code != 200:
                log.warning("finra_corp_bonds: %s HTTP %d at offset=%d",
                            dataset, r.status_code, offset)
                break

            try:
                data = r.json()
            except Exception:
                log.warning("finra_corp_bonds: %s JSON parse error at offset=%d", dataset, offset)
                break

            if not isinstance(data, list) or not data:
                break

            frames.append(pd.DataFrame(data))
            log.info("finra_corp_bonds: %s GET offset=%d → %d rows", dataset, offset, len(data))

            if len(data) < PAGE_LIMIT:
                break
            offset += PAGE_LIMIT
            time.sleep(PAGE_SLEEP_S)

        return frames


def _empty_summary() -> pd.DataFrame:
    return pd.DataFrame(
        {"skipped": [1]},
        index=[pd.Timestamp(date.today())],
    )
