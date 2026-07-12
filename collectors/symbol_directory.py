"""Exchange symbol-directory archival collector (LHB-R8 / LHB-W2c).

Prospective accrual infrastructure for the C1 all-listed Detector-D satellite.
Archives WHAT was exchange-listed common equity on each calendar day, plus a
PIT ticker->CIK map.  No display surfaces today; no consumers yet.  The future
Detector-D satellite needs PIT listing status and security-type metadata that
the current price store does not carry.

Artifacts (runner-local, gitignored):
  data/symbol_directory/snapshots/YYYY-MM-DD.parquet
    One row per symbol on that date: date, symbol, security_name, exchange,
    etf (bool), test_issue (bool), is_preferred (bool),
    source ('nasdaqlisted' | 'otherlisted').
    Written at most once per calendar day (idempotent re-runs skip existing
    files).  A snapshot is only written when BOTH sources parse successfully
    and the combined row count is >= 8 000 (a floor that guards against
    truncated bodies).  Writes are atomic (temp file + os.replace).

  data/symbol_directory/cik_map/YYYY-MM-DD.parquet
    ticker, cik (int), title.  Written at most once per ISO week (the file
    changes slowly; one weekly snapshot is sufficient).

  data/symbol_directory/manifest.json  (small; git-tracked-friendly)
    {last_snapshot_date, n_symbols, n_etf, n_common_estimate, n_preferred,
     last_cik_map_date, n_cik_rows, _display_only: true, _version: "v1"}
    last_snapshot_date is the max YYYY-MM-DD stem among files actually present
    in data/symbol_directory/snapshots/*.parquet (None if none exist); it is
    NEVER set to "today" when no file was written, so synapse freshness keys
    never claim a hole is filled.  Same principle for last_cik_map_date.

Sources:
  nasdaqlisted.txt / otherlisted.txt — Nasdaq Trader plain-HTTP text files;
    keyless, pipe-delimited.
  SEC company_tickers.json — fair-access UA required (same _SEC_UA as edgar_8k).

Governance:
  LHB-R8: strata (S&P 1500 / non-S&P US common / FPI-ADR) permanently
  separate.  Pooled cross-strata base rates are FORBIDDEN on every surface
  that consumes this store.  This collector does NOT enforce that — it is the
  responsibility of every downstream consumer.

  Security-type filtering (preferred shares, units, etc.) is the responsibility
  of consumers.  This collector is FAITHFUL: every listed symbol is archived with
  an is_preferred flag (True when the symbol contains "$").  Consumers that want
  only common equity filter on: not etf and not test_issue and not is_preferred.

  This collector is US-lane only.  It runs in every non-asia collect lane
  (not gated behind us_scope).
"""
from __future__ import annotations

import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_TICKERS_URL       = "https://www.sec.gov/files/company_tickers.json"

# SEC fair-access UA (same pattern as edgar_8k.py).
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"

# nasdaqlisted columns (pipe-separated header row, 8 columns):
#   Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
# otherlisted columns (pipe-separated header row, 8 columns):
#   ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
_FOOTER_MARKER = "File Creation Time"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_nasdaqlisted(text: str) -> pd.DataFrame:
    """Parse nasdaqlisted.txt -> DataFrame with canonical columns.

    Drops the footer line ('File Creation Time: ...') before parsing so
    the csv reader never sees a mismatched row-count.  All symbols are kept
    (including preferred shares that contain '$') — filtering is the
    responsibility of consumers.  is_preferred=True is set for any symbol
    containing '$' so consumers can easily exclude them.
    """
    lines = [l for l in text.splitlines()
             if l and not l.startswith(_FOOTER_MARKER)]
    if len(lines) < 2:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO("\n".join(lines)), sep="|", dtype=str)
    # normalise column names to lowercase / underscored
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        sym = str(r.get("symbol", "") or "").strip()
        if not sym:
            continue
        rows.append({
            "symbol":        sym,
            "security_name": str(r.get("security_name", "") or "").strip(),
            "exchange":      "NASDAQ",
            "etf":           str(r.get("etf", "") or "").strip().upper() == "Y",
            "test_issue":    str(r.get("test_issue", "") or "").strip().upper() == "Y",
            "is_preferred":  "$" in sym,
            "source":        "nasdaqlisted",
        })
    return pd.DataFrame(rows)


def _parse_otherlisted(text: str) -> pd.DataFrame:
    """Parse otherlisted.txt -> DataFrame with canonical columns.

    The 'Exchange' column carries single-character codes:
      A=NYSE MKT (AMEX), N=NYSE, P=NYSE Arca, Z=BATS, V=Investors Exchange.
    We store the raw code; consumers translate as needed.

    All symbols are kept (including preferred shares that contain '$');
    is_preferred=True is set for such symbols so consumers can filter them.
    """
    lines = [l for l in text.splitlines()
             if l and not l.startswith(_FOOTER_MARKER)]
    if len(lines) < 2:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO("\n".join(lines)), sep="|", dtype=str)
    df.columns = [c.strip().lower().replace(" ", "_").replace("act_", "") for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        # otherlisted uses "act symbol" as the primary key column
        sym = str(r.get("symbol", "") or r.get("act_symbol", "") or "").strip()
        if not sym:
            continue
        rows.append({
            "symbol":        sym,
            "security_name": str(r.get("security_name", "") or "").strip(),
            "exchange":      str(r.get("exchange", "") or "").strip(),
            "etf":           str(r.get("etf", "") or "").strip().upper() == "Y",
            "test_issue":    str(r.get("test_issue", "") or "").strip().upper() == "Y",
            "is_preferred":  "$" in sym,
            "source":        "otherlisted",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def _fetch_text(url: str, retries: int = 3, timeout: int = 30) -> str | None:
    """Keyless plain-HTTP GET -> text.  Returns None on any failure."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout,
                             headers={"User-Agent": "macro-dashboard/1.0"})
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    if last is not None and is_connection_error(last):
        raise last
    return None


def _fetch_sec_json(url: str, retries: int = 3, timeout: int = 30) -> dict | None:
    """SEC company_tickers.json — requires descriptive UA."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"},
            )
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    if last is not None and is_connection_error(last):
        raise last
    return None


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _symdir_root() -> Path:
    return config.data_dir() / "symbol_directory"


def _snapshot_path(date_str: str) -> Path:
    return _symdir_root() / "snapshots" / f"{date_str}.parquet"


def _cik_map_dir() -> Path:
    return _symdir_root() / "cik_map"


def _manifest_path() -> Path:
    return _symdir_root() / "manifest.json"


def _this_week_cik_file_exists() -> bool:
    """True if ANY cik_map file was written this ISO week."""
    d = _cik_map_dir()
    if not d.exists():
        return False
    today = datetime.now(timezone.utc).date()
    # ISO week: (year, week) pair
    this_yw = today.isocalendar()[:2]
    for f in d.glob("*.parquet"):
        try:
            fdate = datetime.strptime(f.stem, "%Y-%m-%d").date()
            if fdate.isocalendar()[:2] == this_yw:
                return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Main Adapter
# ---------------------------------------------------------------------------

class SymbolDirectoryAdapter(Adapter):
    """LHB-R8: daily exchange symbol-directory archival + weekly CIK map.

    group='sec': shares the SEC fair-access host budget (<10 req/s across
    data.sec.gov / www.sec.gov / efts.sec.gov).  The CIK map fetch hits
    www.sec.gov/files/company_tickers.json; the symbol-dir files hit
    nasdaqtrader.com (a distinct host, but the adapter is still classified
    sec to keep it in the concurrent pool rather than the serial loop — the
    two nasdaqtrader GETs are small and fast and do not contend with the
    SEC rate limit in practice).
    """

    name = "symbol_directory"
    group = "sec"
    stale_after_days = 3  # weekday collector; flag if missed two trading days

    # ------------------------------------------------------------------
    # fetch() — called by run_adapter; must return {series_name: DataFrame}
    # where each DataFrame has a datetime index (run_adapter validates this).
    # We follow the edgar_8k pattern: write our own parquets and return
    # a small ingest-summary DataFrame so run_adapter has something to
    # timestamp and store.
    # ------------------------------------------------------------------

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:  # noqa: ARG002
        today_str = datetime.now(timezone.utc).date().isoformat()

        snapshot_written = False
        n_symbols = n_etf = n_common_estimate = n_preferred = 0

        # ---- 1. Daily snapshot (skip if already written today) --------
        snap_path = _snapshot_path(today_str)
        if snap_path.exists():
            log.info("symbol_directory: today's snapshot already exists (%s) — skip", snap_path)
            # still read counts for manifest update
            try:
                existing = pd.read_parquet(snap_path)
                n_symbols = len(existing)
                n_etf = int(existing["etf"].sum()) if "etf" in existing.columns else 0
                n_preferred = (
                    int(existing["is_preferred"].sum())
                    if "is_preferred" in existing.columns else 0
                )
                n_common_estimate = int(
                    (~existing["etf"] & ~existing["test_issue"]
                     & ~existing.get("is_preferred", pd.Series([False] * len(existing)))).sum()
                ) if "etf" in existing.columns else 0
            except Exception as e:  # noqa: BLE001
                log.warning("symbol_directory: could not read existing snapshot: %s", e)
        else:
            frames = self._collect_symbol_snapshot()
            if frames is not None:
                snap_path.parent.mkdir(parents=True, exist_ok=True)
                frames["date"] = today_str
                col_order = ["date", "symbol", "security_name", "exchange",
                             "etf", "test_issue", "is_preferred", "source"]
                col_order = [c for c in col_order if c in frames.columns]
                frames = frames[col_order]
                # Atomic write: write to .tmp then os.replace onto final name
                tmp_path = snap_path.with_suffix(".parquet.tmp")
                frames.to_parquet(tmp_path, index=False)
                os.replace(tmp_path, snap_path)
                snapshot_written = True
                n_symbols = len(frames)
                n_etf = int(frames["etf"].sum())
                n_preferred = (
                    int(frames["is_preferred"].sum())
                    if "is_preferred" in frames.columns else 0
                )
                n_common_estimate = int(
                    (~frames["etf"] & ~frames["test_issue"]
                     & ~frames.get("is_preferred", pd.Series([False] * len(frames)))).sum()
                )
                log.info(
                    "symbol_directory: snapshot written %s — %d symbols (%d ETF, "
                    "%d preferred, ~%d non-ETF non-preferred common-estimate)",
                    today_str, n_symbols, n_etf, n_preferred, n_common_estimate,
                )

        # ---- 2. Weekly CIK map (skip if already written this ISO week) ----
        cik_written = False
        n_cik_rows = 0

        cik_map_dir = _cik_map_dir()
        if _this_week_cik_file_exists():
            log.info("symbol_directory: CIK map already written this week — skip")
        else:
            cik_df = self._collect_cik_map()
            if cik_df is not None and not cik_df.empty:
                cik_map_dir.mkdir(parents=True, exist_ok=True)
                cik_path = cik_map_dir / f"{today_str}.parquet"
                cik_df.to_parquet(cik_path, index=False)
                cik_written = True
                n_cik_rows = len(cik_df)
                log.info("symbol_directory: CIK map written %s — %d rows", today_str, n_cik_rows)

        # ---- 3. Manifest (freshness keys from actual files on disk) ----
        # last_snapshot_date = max stem among snapshots/*.parquet (None if none).
        # Never claim freshness over a hole by using today's date unconditionally.
        snap_dir = _symdir_root() / "snapshots"
        last_snapshot_date: str | None = None
        if snap_dir.exists():
            stems = sorted(f.stem for f in snap_dir.glob("*.parquet"))
            last_snapshot_date = stems[-1] if stems else None

        # last_cik_map_date = max stem among cik_map/*.parquet (None if none).
        last_cik_date: str | None = None
        if cik_map_dir.exists():
            existing_cik = sorted(cik_map_dir.glob("*.parquet"))
            if existing_cik:
                last_cik_date = existing_cik[-1].stem
                try:
                    n_cik_rows = n_cik_rows or len(pd.read_parquet(existing_cik[-1]))
                except Exception:  # noqa: BLE001
                    pass

        manifest = {
            "last_snapshot_date": last_snapshot_date,
            "n_symbols": n_symbols,
            "n_etf": n_etf,
            "n_preferred": n_preferred,
            "n_common_estimate": n_common_estimate,
            "last_cik_map_date": last_cik_date,
            "n_cik_rows": n_cik_rows,
            "_display_only": True,
            "_version": "v1",
        }
        mpath = _manifest_path()
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, indent=2))

        # ---- 4. Ingest summary (for run_adapter / status tracking) ----
        ingest = pd.DataFrame(
            {
                "n_symbols":          [n_symbols],
                "n_etf":              [n_etf],
                "n_preferred":        [n_preferred],
                "n_common_estimate":  [n_common_estimate],
                "n_cik_rows":         [n_cik_rows],
                "snapshot_written":   [int(snapshot_written)],
                "cik_written":        [int(cik_written)],
            },
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"symbol_directory__ingest": ingest}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # Minimum combined row count required before writing a snapshot.
    # Live combined roster is ~11-12k; this floor guards against truncated bodies.
    _SNAPSHOT_MIN_ROWS = 8_000

    def _collect_symbol_snapshot(self) -> pd.DataFrame | None:
        """Fetch nasdaqlisted.txt + otherlisted.txt and merge into one frame.

        Returns a DataFrame only when BOTH sources parsed successfully AND the
        combined row count is >= _SNAPSHOT_MIN_ROWS.  If either source fails
        (non-connection error) or the floor check fails, logs a warning and
        returns None so the caller writes nothing for the day (a later same-day
        rerun can then still succeed).  Connection errors are re-raised so the
        outer run_adapter machinery handles host-down correctly.
        """
        sources = [
            (_NASDAQ_LISTED_URL, _parse_nasdaqlisted, "nasdaqlisted"),
            (_OTHER_LISTED_URL,  _parse_otherlisted,  "otherlisted"),
        ]
        frames: list[pd.DataFrame] = []
        for url, parser, label in sources:
            try:
                text = _fetch_text(url)
                if not text:
                    log.warning(
                        "symbol_directory: no text returned from %s (%s) — "
                        "skipping snapshot write for today",
                        url, label,
                    )
                    return None
                df = parser(text)
                if df.empty:
                    log.warning(
                        "symbol_directory: empty parse result from %s (%s) — "
                        "skipping snapshot write for today",
                        url, label,
                    )
                    return None
                frames.append(df)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise  # host down — fail fast
                log.warning(
                    "symbol_directory: fetch/parse error for %s (%s): %s — "
                    "skipping snapshot write for today",
                    url, label, e,
                )
                return None

        combined = pd.concat(frames, ignore_index=True)
        # Deduplicate by symbol (prefer nasdaqlisted for NASDAQ-listed tickers)
        combined = combined.drop_duplicates(subset=["symbol"], keep="first")
        combined = combined.reset_index(drop=True)

        if len(combined) < self._SNAPSHOT_MIN_ROWS:
            log.warning(
                "symbol_directory: combined row count %d < floor %d — "
                "possible truncated body; skipping snapshot write for today",
                len(combined), self._SNAPSHOT_MIN_ROWS,
            )
            return None

        return combined

    def _collect_cik_map(self) -> pd.DataFrame | None:
        """Fetch SEC company_tickers.json -> ticker, cik, title DataFrame."""
        try:
            data = _fetch_sec_json(_TICKERS_URL)
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                raise
            log.warning("symbol_directory: CIK map fetch failed: %s", e)
            return None

        if not data:
            log.warning("symbol_directory: empty CIK map response")
            return None

        rows = []
        for entry in data.values():
            try:
                rows.append({
                    "ticker": str(entry.get("ticker", "") or "").strip().upper(),
                    "cik":    int(entry["cik_str"]),
                    "title":  str(entry.get("title", "") or "").strip(),
                })
            except (KeyError, ValueError, TypeError):
                continue

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df = df[df["ticker"] != ""].drop_duplicates(subset=["ticker"], keep="first")
        return df.reset_index(drop=True)
