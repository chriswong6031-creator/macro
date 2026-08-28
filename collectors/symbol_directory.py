"""Exchange symbol-directory archival collector (LHB-R8 / LHB-W2c).

Prospective accrual infrastructure for the C1 all-listed Detector-D satellite.
Archives WHAT was exchange-listed common equity on each calendar day, plus a
PIT ticker->CIK map.  No display surfaces today; no consumers yet.  The future
Detector-D satellite needs PIT listing status and security-type metadata that
the current price store does not carry.

Artifacts (published under ``data/`` and committed by the daily workflow):
  data/symbol_directory/snapshots/YYYY-MM-DD.parquet
    One row per symbol on that date: date, symbol, security_name, exchange,
    etf (bool), test_issue (bool), is_preferred (bool),
    source ('nasdaqlisted' | 'otherlisted').
    Written at most once per calendar day (idempotent re-runs skip existing
    files).  A snapshot is only written when BOTH sources parse successfully
    and both source-specific row floors plus the combined >= 8 000 floor are
    satisfied.  The per-source guard prevents one materially truncated body
    from hiding behind a full response from the other source.  Writes are
    durable and absent-only (temp file + fsync + atomic link +
    parent-directory fsync).

  data/symbol_directory/cik_map/YYYY-MM-DD.parquet
    ticker, cik (int), title.  Written at most once per ISO week (the file
    changes slowly; one weekly snapshot is sufficient).

  data/symbol_directory/receipts/{snapshots,cik_map}/YYYY-MM-DD.json
    Prospective completion evidence written last in the original artifact
    transaction.  Existing parquets are never retro-minted.  The receipt binds
    the exact parquet and exact response.content hashes/counts; raw response
    bodies are not persisted, so replay verification is explicitly false.

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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config
from lib.symbol_directory_receipts import (
    NASDAQ_LISTED_ARTIFACT_MIN_ROWS,
    NASDAQ_LISTED_SOURCE_ID,
    OTHER_LISTED_ARTIFACT_MIN_ROWS,
    OTHER_LISTED_SOURCE_ID,
    SEC_TICKERS_SOURCE_ID,
    SourceFetch,
    build_symbol_directory_completion_receipt,
    canonical_utc_now,
    completion_receipt_path,
    durable_atomic_write_parquet,
    footer_diagnostic,
    write_symbol_directory_completion_receipt,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# SEC fair-access UA (same pattern as edgar_8k.py).
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"

# nasdaqlisted columns (pipe-separated header row, 8 columns):
#   Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
# otherlisted columns (pipe-separated header row, 8 columns):
#   ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
_FOOTER_MARKER = "File Creation Time"


@dataclass(frozen=True, slots=True)
class _CollectedSnapshot:
    frame: pd.DataFrame
    source_fetches: tuple[tuple[str, SourceFetch[Any]], ...] | None
    pre_dedupe_rows: int
    duplicate_occurrences: int
    duplicate_key_count: int
    source_row_counts: tuple[tuple[str, int], ...]
    spy_occurrences: tuple[dict[str, Any], ...]
    footer_diagnostics: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _CollectedCikMap:
    frame: pd.DataFrame
    source_fetches: tuple[tuple[str, SourceFetch[Any]], ...] | None
    pre_dedupe_rows: int
    duplicate_occurrences: int
    duplicate_key_count: int
    source_row_counts: tuple[tuple[str, int], ...]
    spy_occurrences: tuple[dict[str, Any], ...]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _cell_text(value: object) -> str:
    """Normalize a source cell without turning pandas missing values into ``nan``."""

    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _parse_nasdaqlisted(text: str) -> pd.DataFrame:
    """Parse nasdaqlisted.txt -> DataFrame with canonical columns.

    Drops the footer line ('File Creation Time: ...') before parsing so
    the csv reader never sees a mismatched row-count.  All symbols are kept
    (including preferred shares that contain '$') — filtering is the
    responsibility of consumers.  is_preferred=True is set for any symbol
    containing '$' so consumers can easily exclude them.
    """
    lines = [l for l in text.splitlines() if l and not l.startswith(_FOOTER_MARKER)]
    if len(lines) < 2:
        return pd.DataFrame()
    df = pd.read_csv(
        io.StringIO("\n".join(lines)),
        sep="|",
        dtype=str,
        # Nasdaq tickers collide with pandas' default NA sentinels: the
        # literal symbols NA (Nano Labs), NAN, NULL, NONE are real listings.
        # Without this they parse as NaN, get dropped by the _cell_text
        # guard, and the row-count completeness check below then refuses the
        # whole day's snapshot (LHB-R8 stall 2026-08-11 -> 2026-08-19).
        keep_default_na=False,
        na_filter=False,
    )
    # normalise column names to lowercase / underscored
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        sym = _cell_text(r.get("symbol"))
        if not sym:
            continue
        rows.append(
            {
                "symbol": sym,
                "security_name": _cell_text(r.get("security_name")),
                "exchange": "NASDAQ",
                "etf": _cell_text(r.get("etf")).upper() == "Y",
                "test_issue": _cell_text(r.get("test_issue")).upper() == "Y",
                "is_preferred": "$" in sym,
                "source": "nasdaqlisted",
            }
        )
    return pd.DataFrame(rows)


def _parse_otherlisted(text: str) -> pd.DataFrame:
    """Parse otherlisted.txt -> DataFrame with canonical columns.

    The 'Exchange' column carries single-character codes:
      A=NYSE MKT (AMEX), N=NYSE, P=NYSE Arca, Z=BATS, V=Investors Exchange.
    We store the raw code; consumers translate as needed.

    All symbols are kept (including preferred shares that contain '$');
    is_preferred=True is set for such symbols so consumers can filter them.
    """
    lines = [l for l in text.splitlines() if l and not l.startswith(_FOOTER_MARKER)]
    if len(lines) < 2:
        return pd.DataFrame()
    df = pd.read_csv(
        io.StringIO("\n".join(lines)),
        sep="|",
        dtype=str,
        # Nasdaq tickers collide with pandas' default NA sentinels: the
        # literal symbols NA (Nano Labs), NAN, NULL, NONE are real listings.
        # Without this they parse as NaN, get dropped by the _cell_text
        # guard, and the row-count completeness check below then refuses the
        # whole day's snapshot (LHB-R8 stall 2026-08-11 -> 2026-08-19).
        keep_default_na=False,
        na_filter=False,
    )
    df.columns = [
        c.strip().lower().replace(" ", "_").replace("act_", "") for c in df.columns
    ]
    rows = []
    for _, r in df.iterrows():
        # otherlisted uses "act symbol" as the primary key column
        sym = _cell_text(r.get("symbol")) or _cell_text(r.get("act_symbol"))
        if not sym:
            continue
        rows.append(
            {
                "symbol": sym,
                "security_name": _cell_text(r.get("security_name")),
                "exchange": _cell_text(r.get("exchange")),
                "etf": _cell_text(r.get("etf")).upper() == "Y",
                "test_issue": _cell_text(r.get("test_issue")).upper() == "Y",
                "is_preferred": "$" in sym,
                "source": "otherlisted",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def _fetch_text(
    url: str,
    retries: int = 3,
    timeout: int = 30,
    *,
    with_evidence: bool = False,
) -> str | SourceFetch[str] | None:
    """Keyless HTTP GET, optionally retaining exact in-memory response evidence.

    The default return remains ``str | None`` for existing callers.  The
    evidence form keeps ``response.content`` alongside the decoded text; it
    never attempts to recreate source bytes by encoding ``response.text``.
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            started_at = canonical_utc_now()
            r = requests.get(
                url, timeout=timeout, headers={"User-Agent": "macro-dashboard/1.0"}
            )
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            text = r.text
            if with_evidence:
                return SourceFetch(
                    value=text,
                    content=bytes(r.content),
                    requested_url=url,
                    started_at=started_at,
                    completed_at=canonical_utc_now(),
                    http_status=int(r.status_code),
                )
            return text
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    if last is not None and is_connection_error(last):
        raise last
    return None


def _fetch_sec_json(
    url: str,
    retries: int = 3,
    timeout: int = 30,
    *,
    with_evidence: bool = False,
) -> dict | SourceFetch[dict] | None:
    """SEC company_tickers JSON, optionally with exact response evidence."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            started_at = canonical_utc_now()
            r = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"},
            )
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            value = r.json()
            if with_evidence:
                return SourceFetch(
                    value=value,
                    content=bytes(r.content),
                    requested_url=url,
                    started_at=started_at,
                    completed_at=canonical_utc_now(),
                    http_status=int(r.status_code),
                )
            return value
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


# A snapshot is written every calendar day the collector runs; more than this
# many days behind means the lane is stalled, not merely idle over a weekend.
_SNAPSHOT_STALE_AFTER_DAYS = 3


def _snapshot_lag_days(last_snapshot_date: str | None, today_str: str) -> int | None:
    """Whole days between the newest snapshot on disk and today (None if unknown)."""

    if not last_snapshot_date:
        return None
    try:
        last = datetime.strptime(last_snapshot_date, "%Y-%m-%d").date()
        today = datetime.strptime(today_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (today - last).days


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
            fdate = datetime.strptime(f"{f.stem} +0000", "%Y-%m-%d %z").date()
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

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        collector_started_at = canonical_utc_now()
        today_str = collector_started_at[:10]

        snapshot_written = False
        n_symbols = n_etf = n_common_estimate = n_preferred = 0

        # ---- 1. Daily snapshot (skip if already written today) --------
        snap_path = _snapshot_path(today_str)
        if snap_path.exists():
            log.info(
                "symbol_directory: today's snapshot already exists (%s) — skip",
                snap_path,
            )
            # still read counts for manifest update
            try:
                existing = pd.read_parquet(snap_path)
                n_symbols = len(existing)
                n_etf = int(existing["etf"].sum()) if "etf" in existing.columns else 0
                n_preferred = (
                    int(existing["is_preferred"].sum())
                    if "is_preferred" in existing.columns
                    else 0
                )
                n_common_estimate = (
                    int(
                        (
                            ~existing["etf"]
                            & ~existing["test_issue"]
                            & ~existing.get(
                                "is_preferred", pd.Series([False] * len(existing))
                            )
                        ).sum()
                    )
                    if "etf" in existing.columns
                    else 0
                )
            except Exception as e:  # noqa: BLE001
                log.warning("symbol_directory: could not read existing snapshot: %s", e)
        else:
            collected_snapshot = self._collect_symbol_snapshot(with_evidence=True)
            if collected_snapshot is None:
                # A refused write is silent in run_status (the adapter still
                # reports 'ok'), which is how the 2026-08-11 stall ran for 8
                # nights unnoticed.  Annotate the Actions summary instead.
                print(
                    "::warning title=symbol_directory-snapshot-skipped::"
                    f"symbol_directory wrote no snapshot for {today_str} "
                    "(a source guard refused the write; see the warnings above)",
                    flush=True,
                )
            if collected_snapshot is not None:
                if isinstance(collected_snapshot, _CollectedSnapshot):
                    snapshot_details = collected_snapshot
                    frames = snapshot_details.frame
                else:  # compatibility guard for subclasses overriding the old helper
                    snapshot_details = None
                    frames = collected_snapshot
                frames["date"] = today_str
                col_order = [
                    "date",
                    "symbol",
                    "security_name",
                    "exchange",
                    "etf",
                    "test_issue",
                    "is_preferred",
                    "source",
                ]
                col_order = [c for c in col_order if c in frames.columns]
                frames = frames[col_order]
                durable_atomic_write_parquet(frames, snap_path)
                snapshot_written = True
                n_symbols = len(frames)
                n_etf = int(frames["etf"].sum())
                n_preferred = (
                    int(frames["is_preferred"].sum())
                    if "is_preferred" in frames.columns
                    else 0
                )
                n_common_estimate = int(
                    (
                        ~frames["etf"]
                        & ~frames["test_issue"]
                        & ~frames.get("is_preferred", pd.Series([False] * len(frames)))
                    ).sum()
                )
                log.info(
                    "symbol_directory: snapshot written %s — %d symbols (%d ETF, "
                    "%d preferred, ~%d non-ETF non-preferred common-estimate)",
                    today_str,
                    n_symbols,
                    n_etf,
                    n_preferred,
                    n_common_estimate,
                )
                if (
                    snapshot_details is not None
                    and snapshot_details.source_fetches is not None
                ):
                    if len(snapshot_details.spy_occurrences) != 1:
                        log.warning(
                            "symbol_directory: SPY occurrence count is %d; snapshot "
                            "remains reconstruction-only and gets no completion receipt",
                            len(snapshot_details.spy_occurrences),
                        )
                    else:
                        receipt = build_symbol_directory_completion_receipt(
                            kind="listing_snapshot",
                            observation_date=today_str,
                            artifact_path=snap_path,
                            source_fetches=snapshot_details.source_fetches,
                            collector_started_at=collector_started_at,
                            collector_completed_at=canonical_utc_now(),
                            pre_dedupe_rows=snapshot_details.pre_dedupe_rows,
                            duplicate_occurrences=snapshot_details.duplicate_occurrences,
                            duplicate_key_count=snapshot_details.duplicate_key_count,
                            source_row_counts=snapshot_details.source_row_counts,
                            pre_dedupe_spy_occurrences=snapshot_details.spy_occurrences,
                            non_authoritative_footers=(
                                snapshot_details.footer_diagnostics
                            ),
                        )
                        receipt_path = completion_receipt_path(
                            _symdir_root(),
                            kind="listing_snapshot",
                            observation_date=today_str,
                        )
                        write_symbol_directory_completion_receipt(
                            receipt_path,
                            receipt,
                            snap_path,
                            expected_kind="listing_snapshot",
                        )
                        log.info(
                            "symbol_directory: prospective snapshot receipt written %s",
                            receipt_path,
                        )

        # ---- 2. Weekly CIK map (skip if already written this ISO week) ----
        cik_written = False
        n_cik_rows = 0

        cik_map_dir = _cik_map_dir()
        if _this_week_cik_file_exists():
            log.info("symbol_directory: CIK map already written this week — skip")
        else:
            collected_cik = self._collect_cik_map(with_evidence=True)
            if collected_cik is not None:
                if isinstance(collected_cik, _CollectedCikMap):
                    cik_details = collected_cik
                    cik_df = cik_details.frame
                else:  # compatibility guard for subclasses overriding the old helper
                    cik_details = None
                    cik_df = collected_cik
            else:
                cik_details = None
                cik_df = None
            if cik_df is not None and not cik_df.empty:
                cik_path = cik_map_dir / f"{today_str}.parquet"
                durable_atomic_write_parquet(cik_df, cik_path)
                cik_written = True
                n_cik_rows = len(cik_df)
                log.info(
                    "symbol_directory: CIK map written %s — %d rows",
                    today_str,
                    n_cik_rows,
                )
                if cik_details is not None and cik_details.source_fetches is not None:
                    receipt = build_symbol_directory_completion_receipt(
                        kind="sec_registrant_map",
                        observation_date=today_str,
                        artifact_path=cik_path,
                        source_fetches=cik_details.source_fetches,
                        collector_started_at=collector_started_at,
                        collector_completed_at=canonical_utc_now(),
                        pre_dedupe_rows=cik_details.pre_dedupe_rows,
                        duplicate_occurrences=cik_details.duplicate_occurrences,
                        duplicate_key_count=cik_details.duplicate_key_count,
                        source_row_counts=cik_details.source_row_counts,
                        pre_dedupe_spy_occurrences=cik_details.spy_occurrences,
                    )
                    receipt_path = completion_receipt_path(
                        _symdir_root(),
                        kind="sec_registrant_map",
                        observation_date=today_str,
                    )
                    write_symbol_directory_completion_receipt(
                        receipt_path,
                        receipt,
                        cik_path,
                        expected_kind="sec_registrant_map",
                    )
                    log.info(
                        "symbol_directory: prospective CIK receipt written %s",
                        receipt_path,
                    )

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
                except Exception as exc:  # noqa: BLE001
                    log.debug(
                        "symbol_directory: could not read latest CIK row count: %s", exc
                    )

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

        # Freshness alarm: consumers (scripts/check_symbol_rename_drift.py) read
        # the NEWEST snapshot, so a frozen directory reds the whole fleet while
        # this adapter keeps reporting 'ok'.  Make the lag visible in CI.
        stale_days = _snapshot_lag_days(last_snapshot_date, today_str)
        if stale_days is not None and stale_days > _SNAPSHOT_STALE_AFTER_DAYS:
            print(
                "::warning title=symbol_directory-stale::"
                f"newest symbol_directory snapshot is {last_snapshot_date} "
                f"({stale_days}d behind {today_str}); downstream identity guards "
                "compare live universes against a frozen roster",
                flush=True,
            )

        # ---- 4. Ingest summary (for run_adapter / status tracking) ----
        ingest = pd.DataFrame(
            {
                "n_symbols": [n_symbols],
                "n_etf": [n_etf],
                "n_preferred": [n_preferred],
                "n_common_estimate": [n_common_estimate],
                "n_cik_rows": [n_cik_rows],
                "snapshot_written": [int(snapshot_written)],
                "cik_written": [int(cik_written)],
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
    # Independently guard both feeds.  The versioned receipt contract carries
    # the same floors and validates exact post-dedupe counts from the parquet.
    _SOURCE_ARTIFACT_MIN_ROWS: ClassVar[dict[str, int]] = {
        "nasdaqlisted": NASDAQ_LISTED_ARTIFACT_MIN_ROWS,
        "otherlisted": OTHER_LISTED_ARTIFACT_MIN_ROWS,
    }

    def _collect_symbol_snapshot(
        self,
        *,
        with_evidence: bool = False,
    ) -> pd.DataFrame | _CollectedSnapshot | None:
        """Fetch nasdaqlisted.txt + otherlisted.txt and merge into one frame.

        Returns a DataFrame only when BOTH sources parsed successfully AND the
        combined row count is >= _SNAPSHOT_MIN_ROWS and each source retains its
        versioned post-dedupe minimum.  If either source fails (non-connection
        error) or a floor check fails, logs a warning and returns None so the
        caller writes nothing for the day (a later same-day rerun can then still
        succeed).  Connection errors are re-raised so the outer run_adapter
        machinery handles host-down correctly.
        """
        sources = [
            (
                _NASDAQ_LISTED_URL,
                _parse_nasdaqlisted,
                "nasdaqlisted",
                NASDAQ_LISTED_SOURCE_ID,
            ),
            (
                _OTHER_LISTED_URL,
                _parse_otherlisted,
                "otherlisted",
                OTHER_LISTED_SOURCE_ID,
            ),
        ]
        frames: list[pd.DataFrame] = []
        source_fetches: list[tuple[str, SourceFetch[Any]]] = []
        source_row_counts: list[tuple[str, int]] = []
        footer_diagnostics: list[dict[str, Any]] = []
        for url, parser, label, source_id in sources:
            try:
                fetched = _fetch_text(url, with_evidence=with_evidence)
                if isinstance(fetched, SourceFetch):
                    text = fetched.value
                    source_fetches.append((source_id, fetched))
                else:
                    text = fetched
                if not text:
                    log.warning(
                        "symbol_directory: no text returned from %s (%s) — "
                        "skipping snapshot write for today",
                        url,
                        label,
                    )
                    return None
                if not isinstance(text, str):
                    raise TypeError(f"{label} response did not decode to text")
                df = parser(text)
                if df.empty:
                    log.warning(
                        "symbol_directory: empty parse result from %s (%s) — "
                        "skipping snapshot write for today",
                        url,
                        label,
                    )
                    return None
                source_data_rows = len(
                    [
                        line
                        for line in text.splitlines()[1:]
                        if line and not line.startswith(_FOOTER_MARKER)
                    ]
                )
                if len(df) != source_data_rows:
                    log.warning(
                        "symbol_directory: %s parsed %d of %d non-footer rows — "
                        "skipping incomplete snapshot write for today",
                        label,
                        len(df),
                        source_data_rows,
                    )
                    return None
                footer = footer_diagnostic(source_id=source_id, text=text)
                if footer["matching_line_count"] != 1:
                    log.warning(
                        "symbol_directory: %s returned %d creation footers — "
                        "skipping incomplete snapshot write for today",
                        label,
                        footer["matching_line_count"],
                    )
                    return None
                frames.append(df)
                source_row_counts.append((source_id, len(df)))
                footer_diagnostics.append(footer)
            except Exception as e:
                if is_connection_error(e):
                    raise  # host down — fail fast
                log.warning(
                    "symbol_directory: fetch/parse error for %s (%s): %s — "
                    "skipping snapshot write for today",
                    url,
                    label,
                    e,
                )
                return None

        combined = pd.concat(frames, ignore_index=True)
        pre_dedupe_rows = len(combined)
        counts = combined["symbol"].value_counts(dropna=False)
        duplicate_counts = counts[counts > 1]
        duplicate_occurrences = int((duplicate_counts - 1).sum())
        duplicate_key_count = len(duplicate_counts)
        spy_occurrences = tuple(
            {
                "source_id": (
                    NASDAQ_LISTED_SOURCE_ID
                    if row["source"] == "nasdaqlisted"
                    else OTHER_LISTED_SOURCE_ID
                ),
                "symbol": str(row["symbol"]),
                "security_name": str(row["security_name"]),
                "exchange": str(row["exchange"]),
                "etf": bool(row["etf"]),
                "test_issue": bool(row["test_issue"]),
                "is_preferred": bool(row["is_preferred"]),
            }
            for _, row in combined[combined["symbol"] == "SPY"].iterrows()
        )
        # Deduplicate by symbol (prefer nasdaqlisted for NASDAQ-listed tickers)
        combined = combined.drop_duplicates(subset=["symbol"], keep="first")
        combined = combined.reset_index(drop=True)

        artifact_source_counts = combined["source"].value_counts().to_dict()
        for source_label, minimum_rows in self._SOURCE_ARTIFACT_MIN_ROWS.items():
            artifact_rows = int(artifact_source_counts.get(source_label, 0))
            if artifact_rows < minimum_rows:
                log.warning(
                    "symbol_directory: %s artifact row count %d < source floor %d — "
                    "possible truncated body; skipping snapshot write for today",
                    source_label,
                    artifact_rows,
                    minimum_rows,
                )
                return None

        if len(combined) < self._SNAPSHOT_MIN_ROWS:
            log.warning(
                "symbol_directory: combined row count %d < floor %d — "
                "possible truncated body; skipping snapshot write for today",
                len(combined),
                self._SNAPSHOT_MIN_ROWS,
            )
            return None

        if not with_evidence:
            return combined
        return _CollectedSnapshot(
            frame=combined,
            source_fetches=(
                tuple(source_fetches) if len(source_fetches) == len(sources) else None
            ),
            pre_dedupe_rows=pre_dedupe_rows,
            duplicate_occurrences=duplicate_occurrences,
            duplicate_key_count=duplicate_key_count,
            source_row_counts=tuple(source_row_counts),
            spy_occurrences=spy_occurrences,
            footer_diagnostics=tuple(footer_diagnostics),
        )

    def _collect_cik_map(
        self,
        *,
        with_evidence: bool = False,
    ) -> pd.DataFrame | _CollectedCikMap | None:
        """Fetch SEC company_tickers.json -> ticker, cik, title DataFrame."""
        try:
            fetched = _fetch_sec_json(_TICKERS_URL, with_evidence=with_evidence)
        except Exception as e:
            if is_connection_error(e):
                raise
            log.warning("symbol_directory: CIK map fetch failed: %s", e)
            return None

        if isinstance(fetched, SourceFetch):
            data = fetched.value
            source_fetches: tuple[tuple[str, SourceFetch[Any]], ...] | None = (
                (SEC_TICKERS_SOURCE_ID, fetched),
            )
        else:
            data = fetched
            source_fetches = None

        if not data:
            log.warning("symbol_directory: empty CIK map response")
            return None
        if not isinstance(data, dict):
            log.warning("symbol_directory: CIK map response root is not an object")
            return None

        rows = []
        rejected_rows = 0
        for entry in data.values():
            if not isinstance(entry, dict):
                rejected_rows += 1
                continue
            try:
                ticker = str(entry.get("ticker", "") or "").strip().upper()
                cik = int(entry["cik_str"])
                title = str(entry.get("title", "") or "").strip()
            except (KeyError, ValueError, TypeError):
                rejected_rows += 1
                continue
            if not ticker or cik <= 0 or not title:
                rejected_rows += 1
                continue
            rows.append({"ticker": ticker, "cik": cik, "title": title})

        if rejected_rows:
            log.warning(
                "symbol_directory: CIK map rejected %d malformed rows — "
                "skipping incomplete map write",
                rejected_rows,
            )
            return None

        if not rows:
            return None

        pre_dedupe = pd.DataFrame(rows).reset_index(drop=True)
        counts = pre_dedupe["ticker"].value_counts(dropna=False)
        duplicate_counts = counts[counts > 1]
        duplicate_occurrences = int((duplicate_counts - 1).sum())
        duplicate_key_count = len(duplicate_counts)
        spy_occurrences = tuple(
            {
                "source_id": SEC_TICKERS_SOURCE_ID,
                "ticker": str(row["ticker"]),
                "cik": int(row["cik"]),
                "title": str(row["title"]),
            }
            for _, row in pre_dedupe[pre_dedupe["ticker"] == "SPY"].iterrows()
        )
        df = pre_dedupe.drop_duplicates(subset=["ticker"], keep="first")
        df = df.reset_index(drop=True)
        if not with_evidence:
            return df
        return _CollectedCikMap(
            frame=df,
            source_fetches=source_fetches,
            pre_dedupe_rows=len(pre_dedupe),
            duplicate_occurrences=duplicate_occurrences,
            duplicate_key_count=duplicate_key_count,
            source_row_counts=((SEC_TICKERS_SOURCE_ID, len(pre_dedupe)),),
            spy_occurrences=spy_occurrences,
        )
