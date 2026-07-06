"""Nightly sync-gauge appender — keeps data/leadlag/sync_gauge.json current.

The sync gauge (sync = 1 − circ_var(2π·pos/100) = mean resultant length R) was
computed once by leadlag_phase0.py and will go stale without a nightly updater.
This script computes the CURRENT month's sync per family from the latest engine
state and upserts (overwrites same-month entry, idempotent per month) into the
existing JSON, preserving all historical rows.

Data sources (per family):
  us_sector  → data/sector_cycles/forward_log.parquet
  country    → data/country_cycles/forward_log.parquet
  cn_sector  → data/china_sector_cycles/forward_log.parquet

Fall-back: if a forward_log is empty for the current period, use the latest
month's rows from the corresponding backfill.parquet.

Exact formula (from scripts/leadlag_phase0.py compute_sync_gauge):
  ang = 2π * pos / 100
  R   = sqrt(mean(cos(ang))² + mean(sin(ang))²)
  sync = R   (= 1 − circ_var)

Usage: python -m scripts.append_sync_gauge
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("append_sync_gauge")

ROOT = Path(__file__).resolve().parent.parent

SYNC_GAUGE_PATH = ROOT / "data" / "leadlag" / "sync_gauge.json"

# Family → (forward_log path, backfill path, id membership set).
# IDs sourced verbatim from scripts/leadlag_phase0.py (case-insensitive match).
_US_SECTOR_IDS = frozenset(s.lower() for s in [
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
])
_BLOC_IDS = frozenset(s.lower() for s in {"AAXJ", "EEM", "EFA", "ILF", "VGK", "VPL", "VXUS"})
_COUNTRY_IDS = frozenset(s.lower() for s in [
    "AAXJ", "ECH", "EEM", "EFA", "EIDO", "EPOL", "EWA", "EWC", "EWD", "EWG",
    "EWH", "EWI", "EWJ", "EWL", "EWN", "EWP", "EWQ", "EWS", "EWT", "EWU",
    "EWW", "EWY", "EWZ", "EZA", "FXI", "ILF", "INDA", "TUR", "VGK", "VPL", "VXUS",
] if s.lower() not in _BLOC_IDS)
_CN_SECTOR_IDS = frozenset([
    "801010", "801030", "801040", "801050", "801080", "801110", "801120",
    "801130", "801140", "801150", "801160", "801170", "801180", "801200",
    "801210", "801230", "801710", "801720", "801730", "801740", "801750",
    "801760", "801770", "801780", "801790", "801880", "801890", "801950",
    "801960", "801970", "801980",
])

FAMILIES = {
    "us_sector": {
        "forward_log": ROOT / "data" / "sector_cycles" / "forward_log.parquet",
        "backfill":    ROOT / "data" / "sector_cycles" / "backfill.parquet",
        "ids": _US_SECTOR_IDS,
    },
    "country": {
        "forward_log": ROOT / "data" / "country_cycles" / "forward_log.parquet",
        "backfill":    ROOT / "data" / "country_cycles" / "backfill.parquet",
        "ids": _COUNTRY_IDS,
    },
    "cn_sector": {
        "forward_log": ROOT / "data" / "china_sector_cycles" / "forward_log.parquet",
        "backfill":    ROOT / "data" / "china_sector_cycles" / "backfill.parquet",
        "ids": _CN_SECTOR_IDS,
    },
}

MIN_N = 3  # minimum instruments needed to compute a meaningful sync value


def _phase(pos: float) -> str:
    if pos < 25:
        return "trough"
    if pos < 50:
        return "advance"
    if pos < 75:
        return "peak"
    return "decline"


def _compute_sync(vals: np.ndarray) -> float:
    """Circular mean resultant length R = sync = 1 - circ_var.
    Exact formula from scripts/leadlag_phase0.py compute_sync_gauge."""
    ang = 2.0 * np.pi * (vals / 100.0)
    R = np.sqrt(np.mean(np.cos(ang)) ** 2 + np.mean(np.sin(ang)) ** 2)
    return float(R)


def _month_end_date(year: int, month: int) -> str:
    """Return the last day of the given month as YYYY-MM-DD."""
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day = next_month.replace(day=1) - pd.Timedelta(days=1)
    return last_day.strftime("%Y-%m-%d")


def _get_current_pos(fam_key: str, cfg: dict) -> np.ndarray | None:
    """Return pos values for the current month from forward_log or backfill fallback."""
    now = datetime.now(timezone.utc)
    cur_year, cur_month = now.year, now.month

    for src_path in (cfg["forward_log"], cfg["backfill"]):
        if not src_path.exists():
            continue
        try:
            df = pd.read_parquet(src_path)
        except Exception as e:
            log.warning("%s: failed to read %s: %s", fam_key, src_path.name, e)
            continue
        if df.empty or "pos" not in df.columns:
            continue
        df["date"] = pd.to_datetime(df["date"])
        # Filter to current month
        mask = (df["date"].dt.year == cur_year) & (df["date"].dt.month == cur_month)
        sub = df[mask]
        if sub.empty:
            # forward_log empty for current month — try the most recent month present
            if src_path.name == "forward_log.parquet":
                continue  # fall through to backfill
            # backfill fallback: use latest month available
            df["ym"] = df["date"].dt.to_period("M")
            latest_ym = df["ym"].max()
            sub = df[df["ym"] == latest_ym]
        # Filter by family IDs (case-insensitive for sector/country, exact for cn_sector)
        if "id" in sub.columns:
            sub = sub[sub["id"].astype(str).str.lower().isin(cfg["ids"])]
        vals = sub["pos"].dropna().to_numpy(float)
        if len(vals) >= MIN_N:
            return vals
    return None


def _build_gauge_entry(fam_key: str, cfg: dict) -> dict | None:
    """Compute sync for the current month. Returns a gauge row dict or None."""
    now = datetime.now(timezone.utc)
    cur_year, cur_month = now.year, now.month
    month_end = _month_end_date(cur_year, cur_month)

    vals = _get_current_pos(fam_key, cfg)
    if vals is None or len(vals) < MIN_N:
        log.warning("%s: insufficient positions (n=%s) — skipping", fam_key, 0 if vals is None else len(vals))
        return None

    sync = _compute_sync(vals)
    n = len(vals)
    phases: dict[str, int] = {"trough": 0, "advance": 0, "peak": 0, "decline": 0}
    for v in vals:
        phases[_phase(v)] += 1
    frac = {k: round(v / n, 3) for k, v in phases.items()}
    return {
        "date": month_end,
        "sync": round(sync, 4),
        "n": int(n),
        "frac": frac,
    }


def _upsert_family(series: list[dict], entry: dict) -> list[dict]:
    """Overwrite any existing row with the same month prefix (YYYY-MM), else append."""
    month_prefix = entry["date"][:7]  # YYYY-MM
    out = [r for r in series if r.get("date", "")[:7] != month_prefix]
    out.append(entry)
    out.sort(key=lambda r: r.get("date", ""))
    return out


def main() -> int:
    if not SYNC_GAUGE_PATH.exists():
        log.error("sync_gauge.json not found at %s — cannot append", SYNC_GAUGE_PATH)
        return 1

    try:
        gauge = json.loads(SYNC_GAUGE_PATH.read_text())
    except Exception as e:
        log.error("failed to read sync_gauge.json: %s", e)
        return 1

    families: dict = gauge.get("families", {})
    updated = False

    for fam_key, cfg in FAMILIES.items():
        entry = _build_gauge_entry(fam_key, cfg)
        if entry is None:
            continue
        series = families.get(fam_key, [])
        new_series = _upsert_family(series, entry)
        if new_series != series or entry not in series:
            families[fam_key] = new_series
            updated = True
            log.info("%s: upserted sync=%.4f n=%d for %s", fam_key, entry["sync"], entry["n"], entry["date"])

    if updated:
        gauge["families"] = families
        gauge["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        SYNC_GAUGE_PATH.write_text(json.dumps(gauge, indent=2))
        log.info("sync_gauge.json updated")
    else:
        log.info("sync_gauge.json — no changes (all families already current or insufficient data)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
