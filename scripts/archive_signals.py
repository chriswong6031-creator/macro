"""Archive the day's MODEL-OUTPUT snapshots into the append-only signal archive.

Reads the latest.json / bond_health.json / regime_snap.json files the engine +
dashboard builders just wrote and appends each (keep-first per as-of date) to
data/signal_archive/<label>.{jsonl,parquet} via engine.signal_archive. It never
recomputes anything — a failure here cannot affect data and the engine succeeds
even if this script dies (every target is wrapped; exit is always 0).

Run this LAST in the daily pipeline, after all the build_* market dashboards, so
every latest.json is fresh. Stale files (a builder that failed today still has
yesterday's file) dedup to a no-op via keep-first, so they can't corrupt the log.

Usage: python -m scripts.archive_signals
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import signal_archive  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("archive_signals")

# (label, path-relative-to-data_dir, preferred as-of key or None to auto-discover).
# These are the daily snapshots the models overwrite in place — the "signal layer".
MANIFEST: list[tuple[str, str, str | None]] = [
    ("us_regime",     "regime/latest.json",        "date"),
    ("regime_snap",   "regime/regime_snap.json",   None),   # has no embedded date
    ("bond_health",   "bonds/bond_health.json",    "as_of"),
    ("china_regime",  "china_regime/latest.json",  "date"),
    ("canada_regime", "canada_regime/latest.json", "date"),
    ("hk_regime",     "hk_regime/latest.json",     "date"),
    ("intl_regime",   "intl/latest.json",          "date"),
    ("forex",         "forex/latest.json",         "date"),
    ("commodity",     "commodity/latest.json",     "date"),
    ("options_gex",   "gex/latest.json",           "asof"),   # index/ETF GEX + skew/put-call (build_gex_board)
    ("baskets",       "baskets/latest.json",       "as_of"),   # per-theme score history (build_baskets)
    ("allocation_us",     "allocation/latest_us.json",     "as_of"),  # rotation playbook risk-over-time
    ("allocation_china",  "allocation/latest_china.json",  "as_of"),
    ("allocation_hk",     "allocation/latest_hk.json",     "as_of"),
    ("allocation_canada", "allocation/latest_canada.json", "as_of"),
    ("baskets_china_ths", "baskets_china_ths/latest.json", "as_of"),  # per-theme THS state accrual
    ("baskets_hk",     "baskets_hk/latest.json",     "as_of"),  # regional theme velocity (sector_pulse)
    ("baskets_china",  "baskets_china/latest.json",  "as_of"),
    ("baskets_canada", "baskets_canada/latest.json", "as_of"),
    ("baskets_intl",   "baskets_intl/latest.json",   "as_of"),
    ("transmission",   "transmission/latest.json",   "asof"),    # PR-E nw-macro-rail R5
    ("market_state",   "market_state/latest.json",   "asof"),    # PR-E nw-macro-rail R5
]


def _fallback_asof(data_dir: Path) -> str | None:
    """The pipeline's market date — used for snapshots that embed no date of their
    own (e.g. regime_snap.json, computed in the US run). Falls back to the UTC run
    date so a snapshot is never dropped purely for lacking a date field."""
    us = data_dir / "regime" / "latest.json"
    if us.exists():
        try:
            iso = signal_archive.find_asof(json.loads(us.read_text()), prefer="date")
            if iso:
                return iso
        except Exception:
            pass
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


def main() -> int:
    data_dir = config.data_dir()
    fallback = _fallback_asof(data_dir)
    wrote = skipped = missing = errored = 0
    for label, rel, key in MANIFEST:
        p = data_dir / rel
        if not p.exists():
            log.info("archive %-13s — skip (no file at %s)", label, rel)
            missing += 1
            continue
        try:
            snap = json.loads(p.read_text())
            asof = signal_archive.find_asof(snap, prefer=key) or fallback
            if signal_archive.archive_snapshot(label, snap, asof):
                log.info("archive %-13s — logged as-of %s", label, asof)
                wrote += 1
            else:
                log.info("archive %-13s — already logged for %s (keep-first)", label, asof)
                skipped += 1
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("archive %-13s — FAILED: %s", label, e)
            errored += 1
    log.info("signal archive: %d new, %d already-logged, %d missing, %d errored",
             wrote, skipped, missing, errored)
    return 0


if __name__ == "__main__":
    sys.exit(main())
