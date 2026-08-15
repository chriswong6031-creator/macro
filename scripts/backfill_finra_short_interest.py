"""Backfill the FINRA consolidated short-interest VINTAGE PANEL — 2018 to now.

WHY THIS EXISTS. Every short-interest verdict in this repo rests on one stated
fact: "no PIT short interest — the collector keeps only the latest snapshot, so
the SI leg cannot be back-tested at all" (engine/crowding.py, SM2-R3 preamble,
DO_NOT_REBUILD "Winner-autopsy short-interest / squeeze-fuel legs | DEFERRED —
no PIT short-interest history (single FINRA settlement date)"). That fact is
about OUR COLLECTOR, not about FINRA. collectors/finra.py probes only recent
candidate settlement dates and keeps the newest one that answers; nobody asked
the API for the back-history.

The API has it. Measured 2026-08-05: a single `symbolCode EQUAL` query returns
206 distinct settlement dates spanning 2017-12-29 → 2026-07-15, and every one of
them pages a full ~15k-22k-row cross-section. So the SI panel that was scheduled
to become usable "~2027+" by forward accrual can be rebuilt today, back to
2018-01-12, in about twenty minutes.

WHAT THIS IS AND IS NOT. This is an AS-RESTATED panel pulled today, not a true
vintage matrix of what each settlement looked like on its own publication day.
Two things make it usable anyway, and one caveat keeps it honest:

  * Restatement is rare and FINRA marks it. `revisionFlag == 'R'` appears on
    34/15,627 rows (0.22%) at 2018-01-31 and 1/22,375 (0.004%) at 2026-07-15.
    The flag is preserved so a consumer can exclude or measure them.
  * Publication lag is knowable and bounded. FINRA's schedule reports positions
    on the second business day after settlement and disseminates on the next
    schedule date — settlement Jan 15 → due Jan 20 → published Jan 27, which is
    TWELVE calendar days, not the "~7" this docstring used to claim. We stamp a
    conservative `knowable_date` (8 NYSE sessions, lib/finra_knowable.py) and any
    backtest MUST join on THAT, never on `settlement_date` — joining on settlement
    date buys ~12 days of look-ahead, and the retired 10-calendar-day stamp bought
    2-3 of them back (see lib/finra_knowable.py for the measurements).
  * CAVEAT: for the 0.22% of restated rows we hold the restated value, not the
    originally-published one. That is a real (small) deviation from true PIT and
    is why the panel is labelled as-restated rather than vintage.

TWO DATA-QUALITY LANDMINES, both measured, both guarded here.

  1. `daysToCoverQuantity` is CAPPED at 999.99 as a sentinel when average daily
     volume rounds to ~0. On the 2026-07-15 cross-section that is 3,983/22,375
     rows (17.8%) — the p90 of the raw column IS the sentinel. Any percentile,
     mean, or z-score over the unfiltered column is scoring a sentinel. Confined
     almost entirely to OTC: exchange-listed is 38/12,884 (0.3%). We emit
     `dtc_capped` and leave the raw value alone rather than silently coercing.
  2. The feed is ~42% OTC by row count (9,491/22,375 at 2026-07-15). OTC names
     are not in any tradeable universe here and carry most of the sentinels. We
     emit `market_class` so consumers can filter rather than guessing.

OUTPUT. Panel to data/finra/short_interest_panel.parquet (Mac-local; large and
gitignored by the same convention as data/research/breakdown_events.parquet),
plus a committed vintage-stamped coverage summary at
data/finra/short_interest_panel_coverage.json so CI and reviewers can see what
the panel contains without the panel itself.

Resumable: settlements already present are skipped unless --force.

    python -m scripts.backfill_finra_short_interest              # full 2018->now
    python -m scripts.backfill_finra_short_interest --since 2024-01-01
    python -m scripts.backfill_finra_short_interest --limit 5    # smoke test
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config  # noqa: E402
from lib.finra_knowable import KNOWABLE_LAG_SESSIONS, knowable_date  # noqa: E402

log = logging.getLogger(__name__)

PAGE = 5000
MAX_PAGES = 40
# Calendar-enumeration probe symbol. A mega-cap continuously listed across the
# whole window; one query returns its full settlement-date history, which IS the
# settlement calendar (every settlement publishes a row for a name this liquid).
CALENDAR_SYMBOLS = ("AAPL", "MSFT", "JNJ")

# The publication lag has ONE definition, in lib/finra_knowable.py, imported by
# both this backfill and engine/neuralweb/context_api.py — the two-constant
# mirror they used to keep in sync by drift test is deleted.
#
# The FINRA schedule example is unchanged and now stated honestly: settlement
# Jan 15 -> due Jan 20 6pm ET -> published Jan 27 is TWELVE calendar days, which
# is exactly why the retired KNOWABLE_LAG_DAYS = 10 under-waited. Measured, +10
# calendar days landed 3/2/2 days EARLY on the 2026-06-30 / 07-15 / 07-31
# settlements against 8 NYSE sessions, and on 07-31 it fell three days before our
# own collector's capture date. Erring long can only make a backtest pessimistic;
# erring short manufactures look-ahead at the publication boundary.
#  -> KNOWABLE_LAG_SESSIONS / knowable_date, imported above from lib.finra_knowable.

DTC_SENTINEL = 999.0          # values >= this are FINRA's "ADV ~ 0" cap
LISTED_CLASSES = {"NYSE", "NNM", "ARCA", "SC", "AMEX", "BZX", "BATS", "NMS"}

_RENAME = {
    "symbolCode": "ticker",
    "currentShortPositionQuantity": "short_shares",
    "previousShortPositionQuantity": "prev_short_shares",
    "averageDailyVolumeQuantity": "avg_daily_vol",
    "daysToCoverQuantity": "days_to_cover",
    "changePercent": "si_change_pct",
    "changePreviousNumber": "si_change_shares",
    "settlementDate": "settlement_date",
    "marketClassCode": "market_class",
    "revisionFlag": "revision_flag",
    "stockSplitFlag": "split_flag",
    "issueName": "issue_name",
}
_NUMERIC = ["short_shares", "prev_short_shares", "avg_daily_vol",
            "days_to_cover", "si_change_pct", "si_change_shares"]


def _cfg() -> dict:
    return config.load()["finra"]


def _headers() -> dict:
    c = _cfg()
    return {"User-Agent": c["user_agent"], "Content-Type": "application/json",
            "Accept": "application/json"}


def _post(body: dict, timeout: int = 90) -> list | None:
    try:
        r = requests.post(_cfg()["url"], data=json.dumps(body),
                          headers=_headers(), timeout=timeout)
        if r.status_code != 200:      # 204 = no data for that partition
            return None
        return r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("finra post failed: %s", e)
        return None


def settlement_calendar() -> list[str]:
    """The true settlement calendar, read from FINRA rather than guessed.

    Guessing (last business day on/before the 15th + month-end) is what
    collectors/finra.py does and it misses real dates — 2018-01-15 returns 204
    because that settlement actually landed on 2018-01-12. Asking a continuously
    listed mega-cap for its own history returns the calendar exactly.
    """
    dates: set[str] = set()
    for sym in CALENDAR_SYMBOLS:
        rows = _post({"limit": 1000, "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": sym}]})
        if rows:
            dates.update(str(r["settlementDate"]) for r in rows if r.get("settlementDate"))
        if dates:
            break        # first symbol that answers is enough
    return sorted(dates)


def fetch_settlement(settlement: str) -> pd.DataFrame:
    """Page one settlement's full cross-section."""
    rows: list[dict] = []
    for page in range(MAX_PAGES):
        batch = _post({"limit": PAGE, "offset": page * PAGE,
                       "compareFilters": [{"compareType": "EQUAL",
                                           "fieldName": "settlementDate",
                                           "fieldValue": settlement}]})
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE:
            break
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).rename(columns=_RENAME)
    for c in _NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df = df.drop_duplicates(subset=["settlement_date", "ticker"], keep="last")

    # Landmine 1: preserve the raw value, flag the sentinel. Never coerce to NaN
    # here — a consumer that wants "high DTC" and a consumer that wants "no ADV"
    # need to tell those apart, and silently nulling makes that impossible.
    df["dtc_capped"] = df["days_to_cover"].ge(DTC_SENTINEL).fillna(False)
    # Landmine 2: expose listedness rather than pre-filtering it away.
    df["is_listed"] = df.get("market_class", pd.Series(index=df.index, dtype=object)).isin(LISTED_CLASSES)

    sd = pd.Timestamp(settlement)
    df["settlement_date"] = sd
    # THE PIT COLUMN. Backtests join on this, never on settlement_date.
    df["knowable_date"] = pd.Timestamp(knowable_date(sd.date()))

    keep = ["settlement_date", "knowable_date", "ticker", "short_shares",
            "prev_short_shares", "avg_daily_vol", "days_to_cover", "dtc_capped",
            "si_change_pct", "si_change_shares", "market_class", "is_listed",
            "revision_flag", "split_flag", "issue_name"]
    return df[[c for c in keep if c in df.columns]]


def _panel_path():
    return config.data_dir() / "finra" / "short_interest_panel.parquet"


def _coverage_path():
    return config.data_dir() / "finra" / "short_interest_panel_coverage.json"


def write_coverage(panel: pd.DataFrame) -> dict:
    listed = panel[panel["is_listed"]] if "is_listed" in panel.columns else panel
    uncapped = listed[~listed["dtc_capped"]]["days_to_cover"].dropna()
    cov = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": len(panel),
        "settlements": int(panel["settlement_date"].nunique()),
        "first_settlement": str(panel["settlement_date"].min().date()),
        "last_settlement": str(panel["settlement_date"].max().date()),
        "tickers": int(panel["ticker"].nunique()),
        "knowable_lag_sessions": KNOWABLE_LAG_SESSIONS,
        "as_restated": True,
        "revised_rows": int((panel.get("revision_flag") == "R").sum()),
        "dtc_capped_rows": int(panel["dtc_capped"].sum()),
        "dtc_capped_pct": round(100.0 * float(panel["dtc_capped"].mean()), 3),
        "listed_rows": int(panel["is_listed"].sum()) if "is_listed" in panel.columns else None,
        "listed_dtc_capped_pct": round(100.0 * float(listed["dtc_capped"].mean()), 3) if len(listed) else None,
        "listed_dtc_uncapped_median": round(float(uncapped.median()), 3) if len(uncapped) else None,
        "listed_dtc_uncapped_p90": round(float(uncapped.quantile(0.90)), 3) if len(uncapped) else None,
    }
    p = _coverage_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cov, indent=2) + "\n")
    return cov


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default="2018-01-01", help="earliest settlement date to pull")
    ap.add_argument("--limit", type=int, default=0, help="max settlements this run (0 = all)")
    ap.add_argument("--force", action="store_true", help="re-pull settlements already stored")
    ap.add_argument("--sleep", type=float, default=0.2, help="pause between settlements (s)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    since = date.fromisoformat(args.since)

    cal = settlement_calendar()
    if not cal:
        print("::error title=finra-backfill::could not read the settlement calendar", flush=True)
        return 1
    wanted = [d for d in cal if date.fromisoformat(d) >= since]
    log.info("settlement calendar: %d dates (%s -> %s); %d at/after %s",
             len(cal), cal[0], cal[-1], len(wanted), since)

    path = _panel_path()
    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    have = set()
    if not existing.empty and not args.force:
        have = {str(pd.Timestamp(d).date()) for d in existing["settlement_date"].unique()}
    todo = [d for d in wanted if d not in have]
    if args.limit:
        todo = todo[:args.limit]
    log.info("panel has %d settlements; fetching %d", len(have), len(todo))
    if not todo:
        if not existing.empty:
            cov = write_coverage(existing)
            log.info("nothing to fetch; coverage refreshed: %s", cov)
        return 0

    def flush(frames: list[pd.DataFrame], base: pd.DataFrame) -> pd.DataFrame:
        """Merge accumulated settlements into the panel and write it."""
        if not frames:
            return base
        fresh = pd.concat(frames, ignore_index=True)
        merged = pd.concat([base, fresh], ignore_index=True) if not base.empty else fresh
        merged = (merged.drop_duplicates(subset=["settlement_date", "ticker"], keep="last")
                        .sort_values(["settlement_date", "ticker"]).reset_index(drop=True))
        path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(path, index=False)
        return merged

    frames: list[pd.DataFrame] = []
    t0 = time.time()
    got = 0
    # Checkpoint every N settlements. A full run is ~20 minutes across ~205
    # network round-trips; writing only at the end would throw away nineteen
    # minutes of work on a transient failure at minute twenty. Checkpointing also
    # makes --force-free resumption real: a killed run picks up where it stopped
    # because the completed settlements are already in the panel.
    CHECKPOINT = 20
    try:
        for i, d in enumerate(todo, 1):
            df = fetch_settlement(d)
            if df.empty:
                print(f"::warning title=finra-backfill::settlement {d} returned no rows", flush=True)
                continue
            frames.append(df)
            got += 1
            if got % CHECKPOINT == 0:
                existing = flush(frames, existing)
                frames = []
                log.info("  %d/%d settlements (%s), panel=%d rows, %.0fs elapsed [checkpoint]",
                         i, len(todo), d, len(existing), time.time() - t0)
            time.sleep(args.sleep)
    except KeyboardInterrupt:
        log.warning("interrupted — flushing %d pending settlements", len(frames))

    combined = flush(frames, existing)
    if combined.empty:
        print("::error title=finra-backfill::no settlements returned data", flush=True)
        return 1
    cov = write_coverage(combined)
    log.info("panel written: %s", json.dumps(cov))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
