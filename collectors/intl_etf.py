"""Country-ETF total-return substrate collector (W0-1 of INTL_FIX_MASTERPLAN).

Collects ~23 iShares single-country ETFs as full OHLCV (auto_adjust=True = total
return) and stores them under data/intl_etf/<TICKER>.parquet.  This is the
canonical reproducible substrate for the intl programme — fixing INTL-42.

Design choices:
- SEPARATE from the `yahoo` group (data/yahoo/ is close+volume only; here we need
  full OHLCV to power C3 global-breadth barometer and the tr-trend harness).
- FULL coverage gate: if < COVERAGE_THRESHOLD of the declared universe is returned
  the whole batch is REJECTED and nothing is persisted (fixes the fail-open bug
  INTL-29 / RC-2 — a frozen-tail 200-OK must never silently corrupt the store).
- Cold-start = max history (20y+); incremental thereafter (last 45 days overlap
  window, enough to handle yfinance restatements).
- New tickers added to the TICKERS list deep-seed on first run (same pattern as
  intl_prices).
- overwrite_overlap=True because auto_adjust=True histories are coherent total-
  return series; fresh pulls correctly re-adjust prior bars after ex-dividends.
- store.basis_shifted guard on the incremental window (same contract as
  collectors/yahoo.py): overwrite_overlap only makes the fresh pull own its OWN
  date span — an ex-div/split between fetches re-bases the WHOLE series, which
  strands every pre-window row on the stale basis. A flagged ticker is re-pulled
  period='max'; a failed re-pull drops it for the run (store untouched,
  re-flagged next run).
- stale_after_days=8: weekly cadence, so 8 days is fine.

Run directly for a dry-run check:
    python -m collectors.intl_etf --dry-run
"""
from __future__ import annotations

import argparse
import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

# Canonical 23-ticker universe (all verified on yfinance 2026-07-02).
# Order roughly by region; keep alphabetical within region for determinism.
TICKERS: list[str] = [
    # North America / LatAm
    "EWC",   # Canada
    "EWW",   # Mexico
    "EWZ",   # Brazil
    # Europe developed
    "EWK",   # Belgium
    "EWL",   # Switzerland
    "EWD",   # Sweden
    "EWN",   # Netherlands
    "EWI",   # Italy
    "EWO",   # Austria
    "EWP",   # Spain
    "EWQ",   # France
    "EWU",   # United Kingdom
    "EWG",   # Germany
    # Asia developed
    "EWA",   # Australia
    "EWH",   # Hong Kong (proxy for Greater China tradeable)
    "EWJ",   # Japan
    "EWS",   # Singapore
    "EWT",   # Taiwan
    "EWY",   # South Korea
    # Asia emerging
    "EIDO",  # Indonesia
    "EWM",   # Malaysia
    "INDA",  # India
    # Africa
    "EZA",   # South Africa
]

# Coverage gate: reject the entire batch if fewer than this fraction of tickers
# return usable data.  Fail-closed per INTL-29 mandate.
COVERAGE_THRESHOLD = 0.80

# Incremental overlap window — enough to capture yfinance restatements.
INCREMENTAL_PERIOD = "45d"


class IntlEtfAdapter(Adapter):
    """iShares single-country ETF total-return OHLCV substrate.

    group = 'intl_etf' -> data/intl_etf/<TICKER>.parquet
    """

    name = "intl_etf"
    group = "intl_etf"
    stale_after_days = 8          # weekly cadence
    overwrite_overlap = True      # auto_adjust=True histories need overwrite-seam

    def __init__(self) -> None:
        # Inherit batch/retry/backoff settings from the yahoo block; both use
        # yfinance under the hood.  Fall back gracefully if the yahoo block
        # doesn't exist (shouldn't happen in this repo).
        ycfg = config.load().get("yahoo", {})
        self._batch_size: int = int(ycfg.get("batch_size", 40))
        self._retries: int = int(ycfg.get("retries", 3))
        self._backoff_base: float = float(ycfg.get("backoff_base_s", 5.0))
        self._basis_tol: float = float(ycfg.get("upsert_basis_tol", 1e-3))

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Return {TICKER: OHLCV DataFrame} for the full universe.

        Raises RuntimeError if fewer than COVERAGE_THRESHOLD tickers return
        usable data (fail-closed gate — fixes INTL-29).
        """
        stored = set(self.stored_series())
        cold_start = not stored

        if cold_start and not full_history:
            log.info("intl_etf: cold store — seeding full history (period=max)")

        period = "max" if (full_history or cold_start) else INCREMENTAL_PERIOD

        # New tickers added to the universe after the store is already warm.
        new = [] if (cold_start or full_history) else [
            t for t in TICKERS if t not in stored
        ]
        if new:
            log.info("intl_etf: %d new ticker(s) — seeding full history: %s",
                     len(new), ",".join(new))

        frames: dict[str, pd.DataFrame] = {}
        rebase: list[str] = []
        self._collect(TICKERS, period, frames,
                      rebase=rebase if period == INCREMENTAL_PERIOD else None)

        # Deep-seed any new tickers (overwrite the shallow incremental fetch).
        if new:
            self._collect(new, "max", frames)

        # Adjustment-basis guard heal: re-pull flagged tickers period='max' so the
        # whole store rebases in one upsert. A failed batch just leaves the tickers
        # out (store untouched, re-flagged next run) — never spliced; the coverage
        # gate below then decides whether the run still stands.
        if rebase:
            log.info("intl_etf: %d ticker(s) on a re-adjusted basis — refetching "
                     "period='max': %s", len(rebase), rebase)
            self._collect(rebase, "max", frames)

        # ---- Coverage gate (fail-closed) --------------------------------
        got = len(frames)
        need = int(COVERAGE_THRESHOLD * len(TICKERS))
        if got < need:
            raise RuntimeError(
                f"intl_etf: coverage gate FAIL — only {got}/{len(TICKERS)} tickers "
                f"returned data (threshold {COVERAGE_THRESHOLD:.0%}, need ≥{need}). "
                "Refusing to persist a partial batch (fail-closed, INTL-29)."
            )

        log.info("intl_etf: %d/%d tickers fetched (period=%s%s)",
                 got, len(TICKERS), period,
                 f"; {len(new)} new deep-seeded" if new else "")
        return frames

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _collect(self, tickers: list[str], period: str,
                 frames: dict[str, pd.DataFrame],
                 rebase: list[str] | None = None) -> None:
        """Batch-download tickers and extract full OHLCV into frames.

        With a `rebase` list (the incremental pass only), a ticker whose window
        disagrees with stored closes on the overlap dates (store.basis_shifted —
        Yahoo re-adjusted the series after an ex-div/split since the last pull) is
        appended there and kept OUT of frames: even with overwrite_overlap the
        splice would strand every pre-window row on the stale basis. The caller
        re-pulls it period='max'."""
        for i in range(0, len(tickers), self._batch_size):
            batch = tickers[i : i + self._batch_size]
            df = self._download(batch, period)
            if df is None:
                log.warning("intl_etf: download returned None for batch %s", batch)
                continue
            for t in batch:
                try:
                    sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                    ohlcv_cols = {
                        "Open": "open", "High": "high", "Low": "low",
                        "Close": "close", "Volume": "volume",
                    }
                    present = [c for c in ohlcv_cols if c in sub.columns]
                    sub = sub[present].rename(columns=ohlcv_cols)
                    sub = sub.dropna(subset=["close"])
                    if sub.empty:
                        log.warning("intl_etf: no usable rows for %s", t)
                        continue
                    if rebase is not None and store.basis_shifted(
                            self.group, t, sub, tol=self._basis_tol):
                        rebase.append(t)  # discard the window; the caller re-pulls 'max'
                        continue
                    frames[t] = sub
                except KeyError:
                    log.warning("intl_etf: no data column for %s", t)

    def _download(self, batch: list[str], period: str) -> pd.DataFrame | None:
        """yfinance download with retry + exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            try:
                df = yf.download(
                    batch,
                    period=period,
                    auto_adjust=True,    # total-return (dividend-adjusted)
                    progress=False,
                    group_by="ticker",
                    threads=True,
                )
                if df is None or df.empty:
                    raise RuntimeError("empty yfinance response")
                return df
            except Exception as e:  # noqa: BLE001 — degrade; coverage gate enforces quality
                last_exc = e
                wait = self._backoff_base * (2 ** attempt)
                log.warning(
                    "intl_etf download batch failed (%s); retry in %.0fs", e, wait
                )
                time.sleep(wait)
        log.error("intl_etf: all %d retries exhausted for batch %s: %s",
                  self._retries, batch, last_exc)
        return None


# ------------------------------------------------------------------ #
# CLI dry-run helper
# ------------------------------------------------------------------ #
def _main() -> None:
    ap = argparse.ArgumentParser(description="intl_etf dry-run / manual seed")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch and print coverage without writing to the store")
    ap.add_argument("--full-history", action="store_true",
                    help="Force max-history re-seed (same as cold-start)")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    adapter = IntlEtfAdapter()
    try:
        frames = adapter.fetch(full_history=args.full_history)
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return

    print(f"\nCoverage: {len(frames)}/{len(TICKERS)} tickers")
    for tk in TICKERS:
        if tk in frames:
            df = frames[tk]
            cols = list(df.columns)
            print(f"  {tk:6}: {len(df):5d} rows  {df.index[0].date()} .. {df.index[-1].date()}  cols={cols}")
        else:
            print(f"  {tk:6}: MISSING")

    if args.dry_run:
        print("\n[dry-run] Nothing written.")
        return

    from collectors.base import run_adapter
    from lib import store  # noqa: F401 (side-effect: confirms store module loads)
    print("\nPersisting via run_adapter ...")
    result = run_adapter(adapter, full_history=args.full_history)
    print(f"Result: status={result.status} rows={result.rows} last={result.last_date}"
          f"{' err=' + result.error if result.error else ''}")


if __name__ == "__main__":
    _main()
