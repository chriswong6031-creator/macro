"""Append-only archiver of context-regime state into data/signal_archive/context_daily.parquet.

Reads regime/latest.json, market_state/latest.json, and the fear-greed parquet, then
appends one row per calendar date (keep-FIRST — same-day re-runs are a no-op) following
the pattern in engine/signal_archive.py.  Every source is absent-safe: a missing file
yields NaN columns, never a crash.  Running this nightly fixes the P-D5-3 class of
'no PIT context history' problems going forward.

Columns written:
  date, quad, liquidity, cycle_tag, transition_state, regime_confidence,
  market_verdict, market_score, vol_regime_verdict, fear_greed_composite

Usage: python -m scripts.archive_context_snapshots
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("archive_context_snapshots")

ARCHIVE_FILE = "context_daily.parquet"


def _load_json_safe(path: Path) -> dict:
    """Return parsed JSON dict or {} if file missing / unreadable."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _read_regime(data_dir: Path) -> dict:
    return _load_json_safe(data_dir / "regime" / "latest.json")


def _read_market_state(data_dir: Path) -> dict:
    return _load_json_safe(data_dir / "market_state" / "latest.json")


def _read_fear_greed(data_dir: Path) -> float | None:
    """Return the latest fear-greed composite value or None if absent."""
    p = data_dir / "sentiment_crypto" / "fear_greed.parquet"
    try:
        df = pd.read_parquet(p)
        if df.empty or "fear_greed" not in df.columns:
            return None
        return float(df["fear_greed"].iloc[-1])
    except Exception:
        return None


def _build_row(regime: dict, ms: dict, fear_greed: float | None) -> dict:
    """Flatten the sources into the flat schema row."""
    vol = regime.get("vol_regime") or {}
    date_val = regime.get("date") or regime.get("asof") or datetime.now(timezone.utc).date().isoformat()
    return {
        "date": str(date_val)[:10],
        "quad": regime.get("quad"),
        "liquidity": regime.get("liquidity_overlay"),
        "cycle_tag": regime.get("cycle_tag"),
        "transition_state": regime.get("transition_state"),
        "regime_confidence": regime.get("confidence"),
        "market_verdict": ms.get("verdict") if ms else None,
        "market_score": ms.get("score") if ms else None,
        "vol_regime_verdict": vol.get("regime") if isinstance(vol, dict) else None,
        "fear_greed_composite": fear_greed,
    }


def _append(archive_path: Path, row: dict) -> bool:
    """Append row to archive, keep-FIRST per date. Returns True if written."""
    date = row["date"]
    if not date:
        log.warning("no date resolved — skipping")
        return False
    old = pd.read_parquet(archive_path) if archive_path.exists() else None
    if old is not None and "date" in old.columns and date in set(old["date"].astype(str)):
        log.info("context_daily — already logged for %s (keep-first)", date)
        return False
    logged_at = datetime.now(timezone.utc).isoformat()
    new_row = {"logged_at": logged_at, **row}
    merged = pd.concat([old, pd.DataFrame([new_row])], ignore_index=True) \
        if old is not None else pd.DataFrame([new_row])
    merged.to_parquet(archive_path, index=False)
    log.info("context_daily — logged %s", date)
    return True


def main() -> int:
    data_dir = config.data_dir()
    archive_dir = data_dir / "signal_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / ARCHIVE_FILE

    regime = _read_regime(data_dir)
    ms = _read_market_state(data_dir)
    fear_greed = _read_fear_greed(data_dir)

    row = _build_row(regime, ms, fear_greed)
    _append(archive_path, row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
