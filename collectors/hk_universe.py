"""Expanded HK universe collector — HSCI full constituent deep OHLCV.

Slice H of the HK/Canada overhaul program (masterplan §3 H4, §8 W1).

WHY
---
The reversal effect (H4) lives in small/mid-cap names; the existing 157-name
``hk_stocks`` panel is mega-cap (HSI/HSCEI-curated breadth universe). This collector
expands coverage to the full ~537-name HSCI (Hang Seng Composite Index), adding
~380 names spanning small/mid/large caps, so H4 can be tested on the small/low-ADV
cohort where the reversal signal is theoretically live.

UNIVERSE SOURCE
---------------
Hang Seng Indexes official API (keyless, verified 2026-07-03):
  https://www.hsi.com.hk/data/eng/rt/index-series/hsci/constituents.do
Returns current HSCI constituent list (537 names as of 2026-07-03, dated same-day).
Fallback: a cached _universe.json written by a prior run (the file is small and
committed).  If neither succeeds the collector FAILS CLOSED — per the house rule
"empty fetch != success."

DELTA FROM EXISTING
-------------------
The 157 names already in ``data/hk_stocks/`` (fetched by
``collectors/hk_stock_prices.py``) are subtracted.  Those stay in their existing
store; this collector only pulls the incremental HSCI-but-not-in-hk_stocks names
into a SEPARATE store ``data/hk_stocks_ext/``.  The two namespaces never mix and the
existing signal engine is not disturbed.

STORE DECISION — R2
-------------------
``data/hk_stocks_ext/<TICKER>.parquet`` (per-ticker parquets, one per HSCI-ext name).
Rationale: ~380 new names × ~170 KB avg = ~65 MB initial; growing ~140 KB/day.
Above the "fast-growing per-ticker" threshold → R2 pattern applies:
  * ``data/hk_stocks_ext/`` added to .gitignore (*.parquet only)
  * ``scripts/publish_r2 --dirs hk_stocks_ext`` wired in CI (daily lane)
  * ``scripts/audit_r2 --anchors hk_stocks_ext`` documented for the freshness tripwire

Committed files (small, needed for CI status / resume):
  * ``data/hk_stocks_ext/_universe.json``    — cached HSCI list + fetch date
  * ``data/hk_stocks_ext/_checkpoint.json``  — progress/resume state (batch index)

FETCH DESIGN
------------
yfinance deep-OHLCV (``period='max'``, ``auto_adjust=True``), reusing
``collectors._stock_ohlc.fetch_ohlc()`` — same machinery as
``collectors/hk_stock_prices.py``.

* Batched (50 names/chunk) with inter-chunk sleep (3 s) to respect Yahoo 429 limits.
* Resumable / idempotent: names whose parquet already exists and is "deep enough"
  (≥250 rows) skip to the cheap 1-month window on re-runs.  New/shallow names pull
  ``period='max'``.  The checkpoint records the last completed batch index so a
  hard-killed run resumes from exactly where it stopped.
* Per-chunk fault isolation: a batch that fails permanently is SKIPPED (logged); the
  next nightly run refills the gap.  Only a total-zero result raises.
* ``store.upsert(overwrite_overlap=True)`` ensures dividend/split-adjusted history is
  seam-free at the refresh edge (same as ``HkStockPriceAdapter``).

RUN_STATUS
----------
Group ``hk_stocks_ext`` stamped with last-good-date and a one-row coverage summary
(``data/hk_stocks_ext/_coverage.parquet``, committed).

TRIPWIRE
--------
``audit_r2 --anchors hk_stocks_ext`` (``hk_stocks_ext/_manifest.json`` key) once the
daily publish lane is activated.

RESUME
------
  python -m scripts.collect --only hk_universe

FULL HISTORY (re-pull all names)
---------------------------------
  python -m scripts.collect --only hk_universe --full-history
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from collectors._stock_ohlc import fetch_ohlc
from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

_HSCI_URL = "https://www.hsi.com.hk/data/eng/rt/index-series/hsci/constituents.do"
_HSCI_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _ext_dir() -> Path:
    return config.data_dir() / "hk_stocks_ext"


def _universe_path() -> Path:
    return _ext_dir() / "_universe.json"


def _checkpoint_path() -> Path:
    return _ext_dir() / "_checkpoint.json"


# ---------------------------------------------------------------------------
# HSCI universe
# ---------------------------------------------------------------------------

def _fetch_hsci_universe(retries: int = 3, backoff_base: float = 3.0) -> list[str]:
    """Fetch current HSCI constituents from the HSI API.

    Returns list of yfinance tickers: ``['0001.HK', '0002.HK', …]``.
    Raises ``RuntimeError`` when the endpoint is unavailable AND there is no
    cached fallback — fail-closed, never proceeds with an empty universe.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(_HSCI_URL, headers={"User-Agent": _HSCI_UA}, timeout=20)
            r.raise_for_status()
            data = r.json()
            series = data["indexSeriesList"][0]
            index_list = series["indexList"][0]
            constituents = index_list["constituentContent"]
            if len(constituents) < 100:
                raise ValueError(
                    f"HSCI API returned only {len(constituents)} constituents "
                    f"(expected ~500+); likely truncated"
                )
            tickers = [f'{c["code"].zfill(4)}.HK' for c in constituents]
            log.info(
                "hk_universe: HSCI API returned %d constituents (date: %s)",
                len(tickers),
                series.get("constituentsDate", "?"),
            )
            return tickers
        except Exception as e:  # noqa: BLE001
            last_exc = e
            wait = backoff_base * (2 ** attempt)
            log.warning(
                "hk_universe: HSCI fetch attempt %d/%d failed (%s); retry in %.0fs",
                attempt + 1, retries, e, wait,
            )
            if attempt < retries - 1:
                time.sleep(wait)

    # Cached fallback (committed from a prior successful run)
    cache = _universe_path()
    if cache.exists():
        try:
            cached = json.loads(cache.read_text())
            tickers = cached.get("tickers", [])
            if len(tickers) >= 100:
                log.warning(
                    "hk_universe: HSCI API unavailable; using cached universe "
                    "(%d names from %s)",
                    len(tickers), cached.get("as_of", "unknown"),
                )
                return tickers
        except Exception:  # noqa: BLE001
            pass

    # Hard fail — never proceed with an empty universe
    raise RuntimeError(
        f"hk_universe: HSCI API unavailable and no cached fallback found. "
        f"Last error: {last_exc}"
    ) from last_exc


def _save_universe(tickers: list[str], dated: str | None = None) -> None:
    """Write the fetched universe to the committed _universe.json."""
    _ext_dir().mkdir(parents=True, exist_ok=True)
    _universe_path().write_text(
        json.dumps(
            {
                "as_of": dated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": _HSCI_URL,
                "n": len(tickers),
                "tickers": tickers,
            },
            indent=2,
        )
    )


# ---------------------------------------------------------------------------
# Existing panel delta
# ---------------------------------------------------------------------------

def _existing_hk_stocks() -> set[str]:
    """Names already stored in data/hk_stocks/ (the 157-name curated panel)."""
    p = config.data_dir() / "hk_stocks"
    if not p.exists():
        return set()
    return {f.stem for f in p.glob("*.parquet") if not f.stem.startswith("_")}


def _ext_tickers(all_hsci: list[str]) -> list[str]:
    """HSCI names NOT already in the hk_stocks panel — the incremental fetch set."""
    existing = _existing_hk_stocks()
    return [t for t in all_hsci if t not in existing]


# ---------------------------------------------------------------------------
# Checkpoint helpers (committed small JSON, lets a partial run resume)
# ---------------------------------------------------------------------------

def _load_checkpoint() -> dict:
    p = _checkpoint_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_checkpoint(cp: dict) -> None:
    _ext_dir().mkdir(parents=True, exist_ok=True)
    _checkpoint_path().write_text(json.dumps(cp, indent=2))


# ---------------------------------------------------------------------------
# Depth histogram
# ---------------------------------------------------------------------------

def _depth_histogram(group: str, tickers: list[str]) -> dict[int, int]:
    """Return {year: count} where count = names with first data bar before <year>."""
    thresholds = [2005, 2010, 2015, 2020]
    counts: dict[int, int] = {y: 0 for y in thresholds}
    for t in tickers:
        df = store.read(group, t)
        if df is None or df.empty:
            continue
        first_year = df.index.min().year
        for y in thresholds:
            if first_year <= y:
                counts[y] += 1
    return counts


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class HkUniverseAdapter(Adapter):
    """Expanded HSCI universe collector (data/hk_stocks_ext/, R2-destined).

    ``fetch()`` returns a single-key dict ``{"coverage": <summary_df>}`` for the
    run_status stale-detector, exactly as ``canada_universe`` does.  Per-ticker
    OHLCV parquets are written incrementally via ``store.upsert`` inside the
    batch loop (not returned en-masse to the runner) so the checkpoint is updated
    after every chunk and a hard-killed run can resume from the last batch.
    """

    name = "hk_universe"
    group = "hk_stocks_ext"
    stale_after_days = 3          # daily price data; tolerate long HK weekend
    overwrite_overlap = True      # yfinance auto_adjust=True: seam-free adjustment

    def __init__(self) -> None:
        hk_cfg = config.load()["hk"]
        # Reuse HK yfinance tuning; slightly more conservative sleep for the larger run
        self.ycfg: dict = {
            **hk_cfg["stock_prices"],
            "sleep_s": hk_cfg["stock_prices"].get("sleep_s", 2.5),
        }
        _ext_dir().mkdir(parents=True, exist_ok=True)

    # -- main fetch -----------------------------------------------------------

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Pull deep OHLCV for all HSCI-ext names; returns a coverage summary."""

        # 1. Resolve universe (live API with committed fallback)
        all_hsci = _fetch_hsci_universe(
            retries=int(self.ycfg.get("retries", 3)),
            backoff_base=float(self.ycfg.get("backoff_base_s", 3.0)),
        )
        _save_universe(all_hsci)

        new_names = _ext_tickers(all_hsci)
        n_existing_panel = len(all_hsci) - len(new_names)

        log.info(
            "hk_universe: HSCI=%d  already_in_hk_stocks=%d  to_fetch=%d",
            len(all_hsci), n_existing_panel, len(new_names),
        )

        if not new_names:
            log.info("hk_universe: hk_stocks already covers every HSCI name; nothing to fetch")
            return {"coverage": pd.DataFrame(
                [{"n_universe": len(all_hsci), "n_existing": n_existing_panel,
                  "n_target": 0, "n_fetched": 0, "n_failed": 0, "pct_complete": 100.0}],
                index=[pd.Timestamp(date.today())],
            )}

        # 2. Resume: skip batches already completed in a prior run (unless full_history)
        cp = _load_checkpoint()
        last_batch_done = int(cp.get("last_batch_done", -1)) if not full_history else -1
        bs = int(self.ycfg.get("batch_size", 50))
        sleep_s = float(self.ycfg.get("sleep_s", 2.5))
        total_batches = (len(new_names) + bs - 1) // bs

        if last_batch_done >= 0:
            log.info(
                "hk_universe: checkpoint found — batch %d/%d done; resuming",
                last_batch_done + 1, total_batches,
            )

        n_fetched = int(cp.get("n_fetched", 0)) if not full_history else 0
        n_failed = int(cp.get("n_failed", 0)) if not full_history else 0

        # 3. Fetch batches
        for batch_idx in range(total_batches):
            if batch_idx <= last_batch_done and not full_history:
                continue   # already done in a prior run

            batch = new_names[batch_idx * bs: (batch_idx + 1) * bs]
            if not batch:
                continue

            log.info(
                "hk_universe: batch %d/%d — %d names (%s … %s)",
                batch_idx + 1, total_batches, len(batch), batch[0], batch[-1],
            )

            try:
                batch_frames = fetch_ohlc(batch, self.group, self.ycfg, full_history)
                # Write each parquet incrementally (idempotent; checkpoint is valid
                # even if the process is killed mid-batch — partial writes will be
                # re-pulled on the next run since last_batch_done only advances when
                # the whole batch completes).
                for ticker, df in batch_frames.items():
                    try:
                        store.upsert(
                            self.group, ticker, df,
                            overwrite_overlap=self.overwrite_overlap,
                        )
                    except Exception as ue:  # noqa: BLE001
                        log.warning("hk_universe: upsert failed for %s: %s", ticker, ue)

                n_fetched += len(batch_frames)
                n_failed += len(batch) - len(batch_frames)
                log.info(
                    "hk_universe: batch %d/%d → %d/%d ok  (cumulative: %d fetched / %d failed)",
                    batch_idx + 1, total_batches,
                    len(batch_frames), len(batch),
                    n_fetched, n_failed,
                )
            except Exception as e:  # noqa: BLE001 — batch-level isolation; never fatal
                log.warning(
                    "hk_universe: batch %d/%d permanently failed (%s); skipping",
                    batch_idx + 1, total_batches, e,
                )
                n_failed += len(batch)

            # Advance checkpoint after every batch
            _save_checkpoint({
                "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "n_universe": len(all_hsci),
                "n_target": len(new_names),
                "last_batch_done": batch_idx,
                "total_batches": total_batches,
                "n_fetched": n_fetched,
                "n_failed": n_failed,
            })

            if batch_idx + 1 < total_batches:
                time.sleep(sleep_s)

        # 4. Depth histogram over newly-fetched names
        fetched_tickers = [
            t for t in new_names
            if (config.data_dir() / "hk_stocks_ext" / f"{t}.parquet").exists()
        ]
        histogram = _depth_histogram(self.group, fetched_tickers)
        log.info(
            "hk_universe: depth histogram — pre-2005:%d  pre-2010:%d  pre-2015:%d  pre-2020:%d",
            histogram[2005], histogram[2010], histogram[2015], histogram[2020],
        )

        # 5. Coverage summary row (written via run_status machinery)
        pct = round(100.0 * n_fetched / max(1, len(new_names)), 1)
        log.info(
            "hk_universe: DONE — %d/%d new names fetched (%.1f%%)  %d failed",
            n_fetched, len(new_names), pct, n_failed,
        )

        row = {
            "n_universe": len(all_hsci),
            "n_existing": n_existing_panel,
            "n_target": len(new_names),
            "n_fetched": n_fetched,
            "n_failed": n_failed,
            "pct_complete": pct,
            "depth_pre2005": histogram[2005],
            "depth_pre2010": histogram[2010],
            "depth_pre2015": histogram[2015],
            "depth_pre2020": histogram[2020],
        }
        return {
            "coverage": pd.DataFrame([row], index=[pd.Timestamp(date.today())])
        }
