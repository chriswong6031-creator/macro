#!/usr/bin/env python3
"""Deterministic coverage receipt for the A-share limit-move research universe.

This is a descriptive inventory, not a point-in-time alpha study.  It joins the latest healthy
TuShare valuation snapshot to the repaired recent zt pool only to quantify selection bias in the
1,842-name nominal raw cache.  Current market cap is never presented as a historical feature.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "china_stocks_raw"
VALUATION_PATH = ROOT / "data" / "tushare" / "valuation.parquet"
ZT_POOL_PATH = ROOT / "data" / "china_zt_pool" / "pool.parquet"
SESSION_REFERENCE_PATH = RAW_DIR / "600519.SS.parquet"
OFFICIAL_CALENDAR_PATH = ROOT / "data" / "cn_limit_alpha" / "reference" / "cn_exchange_calendar_2026.json"
OUT_PATH = (
    ROOT / "research" / "cn_limit_alpha_sol"
    / "A_SHARE_UNIVERSE_COVERAGE_2026-08-08.json"
)

CAP_THRESHOLDS_YI = (20, 30, 50, 80, 100)
APPEARANCE_BINS_YI = (0, 20, 30, 50, 100, 200, 500, 1000, math.inf)


class IntegrityError(RuntimeError):
    """The frozen inventory or an identity invariant changed."""


def canonical_ticker(value: Any) -> str:
    ticker = str(value).strip().upper()
    return f"{ticker[:-3]}.SS" if ticker.endswith(".SH") else ticker


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def official_sessions(path: Path, start: str, end: str) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "cn_exchange_calendar.v1" or payload.get("year") != 2026:
        raise IntegrityError("official calendar artifact has an unexpected schema/year")
    if date.fromisoformat(start).year != 2026 or date.fromisoformat(end).year != 2026:
        raise IntegrityError("official calendar artifact must fail closed outside 2026")
    closed: set[date] = set()
    for start_text, end_text, _reason in payload.get("closed_ranges", []):
        cursor = date.fromisoformat(start_text)
        stop = date.fromisoformat(end_text)
        while cursor <= stop:
            closed.add(cursor)
            cursor += timedelta(days=1)
    cursor = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    sessions: set[str] = set()
    while cursor <= stop:
        if cursor.weekday() < 5 and cursor not in closed:
            sessions.add(cursor.isoformat())
        cursor += timedelta(days=1)
    return sessions


def build_receipt() -> dict[str, Any]:
    raw = {canonical_ticker(path.stem) for path in RAW_DIR.glob("*.parquet")}
    valuation = pd.read_parquet(VALUATION_PATH).copy()
    pool = pd.read_parquet(ZT_POOL_PATH).copy()
    required_valuation = {"ticker", "total_mv_yi", "trade_date", "asof"}
    required_pool = {"ticker", "date"}
    if not required_valuation.issubset(valuation.columns):
        raise IntegrityError("valuation snapshot lacks required columns")
    if not required_pool.issubset(pool.columns):
        raise IntegrityError("zt pool lacks required columns")

    valuation["ticker_c"] = valuation["ticker"].map(canonical_ticker)
    if valuation["asof"].astype(str).nunique() != 1 or valuation["trade_date"].astype(str).nunique() != 1:
        raise IntegrityError("valuation source is not one frozen asof/trade_date snapshot")
    if valuation["ticker_c"].duplicated().any():
        raise IntegrityError("valuation snapshot has duplicate economic tickers")
    pool["ticker_c"] = pool["ticker"].map(canonical_ticker)
    if pool.duplicated(["ticker_c", "date"]).any():
        raise IntegrityError("zt pool has duplicate canonical ticker/date keys")
    valuation_names = set(valuation["ticker_c"])
    shsz = valuation[valuation["ticker_c"].str.endswith((".SS", ".SZ"))].copy()
    bse = valuation[valuation["ticker_c"].str.endswith(".BJ")].copy()
    zt_names = set(pool["ticker_c"])
    raw_valuation = raw & valuation_names
    raw_shsz = raw & set(shsz["ticker_c"])
    raw_zt = raw & zt_names

    pool_dates = set(pd.to_datetime(pool["date"], errors="raise").dt.strftime("%Y-%m-%d"))
    first_pool_date = min(pool_dates)
    last_pool_date = max(pool_dates)
    expected_sessions = official_sessions(OFFICIAL_CALENDAR_PATH, first_pool_date, last_pool_date)
    session_reference = pd.read_parquet(SESSION_REFERENCE_PATH, columns=["close"])
    reference_dates = {
        stamp.strftime("%Y-%m-%d")
        for stamp in pd.to_datetime(session_reference.index, errors="raise")
        if first_pool_date <= stamp.strftime("%Y-%m-%d") <= last_pool_date
    }
    if reference_dates != expected_sessions:
        raise IntegrityError("600519 reference index disagrees with the tracked official calendar")
    missing_pool_sessions = sorted(expected_sessions - pool_dates)
    off_session_pool_dates = sorted(pool_dates - expected_sessions)
    if off_session_pool_dates:
        raise IntegrityError(f"zt pool contains off-session dates: {off_session_pool_dates}")

    coverage_buckets: dict[str, dict[str, Any]] = {}
    for threshold in CAP_THRESHOLDS_YI:
        bucket = valuation[pd.to_numeric(valuation["total_mv_yi"], errors="coerce") < threshold]
        covered = int(bucket["ticker_c"].isin(raw).sum())
        coverage_buckets[f"lt_{threshold}_yi"] = {
            "names": int(len(bucket)), "raw_names": covered,
            "raw_share": _ratio(covered, len(bucket)),
        }

    top_n = int(math.ceil(len(valuation) * 0.10))
    top = valuation.nlargest(top_n, "total_mv_yi")
    top_covered = int(top["ticker_c"].isin(raw).sum())

    cap_bins: list[dict[str, Any]] = []
    for lower, upper in zip(APPEARANCE_BINS_YI, APPEARANCE_BINS_YI[1:]):
        cap = pd.to_numeric(shsz["total_mv_yi"], errors="coerce")
        bucket = shsz[(cap >= lower) & (cap < upper)]
        hits = int(bucket["ticker_c"].isin(zt_names).sum())
        cap_bins.append({
            "lower_yi_inclusive": lower,
            "upper_yi_exclusive": None if math.isinf(upper) else upper,
            "names": int(len(bucket)),
            "zt_pool_names": hits,
            "appearance_share": _ratio(hits, len(bucket)),
        })

    valuation_by_ticker = valuation.set_index("ticker_c")["total_mv_yi"]
    pool_cap = pd.to_numeric(pool["ticker_c"].map(valuation_by_ticker), errors="coerce")
    valuation_matched = pool_cap.notna()
    below_200 = valuation_matched & (pool_cap < 200)
    below_500 = valuation_matched & (pool_cap < 500)

    raw_shsz_cap = pd.to_numeric(
        shsz.loc[shsz["ticker_c"].isin(raw), "total_mv_yi"], errors="coerce"
    )
    omitted_shsz_cap = pd.to_numeric(
        shsz.loc[~shsz["ticker_c"].isin(raw), "total_mv_yi"], errors="coerce"
    )
    hit_shsz_cap = pd.to_numeric(
        shsz.loc[shsz["ticker_c"].isin(zt_names), "total_mv_yi"], errors="coerce"
    )

    receipt: dict[str, Any] = {
        "schema_version": "cn_limit_universe_coverage.v1",
        "asof": str(valuation["asof"].astype(str).max()),
        "valuation_trade_date": str(valuation["trade_date"].astype(str).max()),
        "authority": "descriptive_research_inventory_only",
        "identity_rule": "uppercase_and_SH_to_SS",
        "sources": {
            "valuation": str(VALUATION_PATH.relative_to(ROOT)),
            "valuation_sha256": file_hash(VALUATION_PATH),
            "zt_pool": str(ZT_POOL_PATH.relative_to(ROOT)),
            "zt_pool_sha256": file_hash(ZT_POOL_PATH),
            "session_reference": str(SESSION_REFERENCE_PATH.relative_to(ROOT)),
            "session_reference_sha256": file_hash(SESSION_REFERENCE_PATH),
            "official_calendar": str(OFFICIAL_CALENDAR_PATH.relative_to(ROOT)),
            "official_calendar_sha256": file_hash(OFFICIAL_CALENDAR_PATH),
            "raw_directory": str(RAW_DIR.relative_to(ROOT)),
            "raw_membership_sha256": canonical_hash(sorted(raw)),
        },
        "universe": {
            "raw_names": len(raw),
            "valuation_names": len(valuation),
            "shsz_names": len(shsz),
            "bse_names": len(bse),
            "raw_valuation_overlap": len(raw_valuation),
            "raw_shsz_overlap": len(raw_shsz),
            "raw_shsz_share": _ratio(len(raw_shsz), len(shsz)),
            "raw_bse_overlap": int(bse["ticker_c"].isin(raw).sum()),
            "raw_median_total_mv_yi": float(raw_shsz_cap.median()),
            "omitted_shsz_median_total_mv_yi": float(omitted_shsz_cap.median()),
            "coverage_buckets": coverage_buckets,
            "top_cap_decile": {
                "names": int(len(top)), "raw_names": top_covered,
                "raw_share": _ratio(top_covered, len(top)),
            },
        },
        "zt_pool": {
            "rows": int(len(pool)),
            "observed_pool_sessions": len(pool_dates),
            "official_calendar_sessions_in_window": len(expected_sessions),
            "reference_ticker_sessions_in_window": len(reference_dates),
            "reference_ticker_set_equal_official_calendar": reference_dates == expected_sessions,
            "missing_official_sessions": missing_pool_sessions,
            "off_session_pool_dates": off_session_pool_dates,
            "session_coverage_scope": "observed_pool_dates_only_missing_sessions_not_zero_imputed",
            "first_session": first_pool_date,
            "last_session": last_pool_date,
            "literal_ticker_values": int(pool["ticker"].astype(str).nunique()),
            "economic_names": len(zt_names),
            "raw_name_overlap": len(raw_zt),
            "raw_name_overlap_share": _ratio(len(raw_zt), len(zt_names)),
            "raw_event_rows": int(pool["ticker_c"].isin(raw).sum()),
            "raw_event_row_share": _ratio(int(pool["ticker_c"].isin(raw).sum()), len(pool)),
            "valuation_matched_rows": int(pool_cap.notna().sum()),
            "valuation_unmatched_rows": int(pool_cap.isna().sum()),
            "below_200_yi_event_rows": int(below_200.sum()),
            "below_200_yi_event_row_share_all_rows": _ratio(int(below_200.sum()), len(pool)),
            "below_200_yi_share_of_valuation_matched_rows": _ratio(
                int(below_200.sum()), int(valuation_matched.sum())
            ),
            "raw_share_among_below_200_yi_rows": round(
                float(pool.loc[below_200, "ticker_c"].isin(raw).mean()), 6
            ),
            "below_500_yi_event_rows": int(below_500.sum()),
            "below_500_yi_event_row_share_all_rows": _ratio(int(below_500.sum()), len(pool)),
            "below_500_yi_share_of_valuation_matched_rows": _ratio(
                int(below_500.sum()), int(valuation_matched.sum())
            ),
            "raw_share_among_below_500_yi_rows": round(
                float(pool.loc[below_500, "ticker_c"].isin(raw).mean()), 6
            ),
            "hit_name_median_total_mv_yi": float(hit_shsz_cap.median()),
            "appearance_by_current_cap": cap_bins,
        },
        "limitations": [
            "current market cap is joined to 36 observed pool dates inside a 39-session official window and is descriptive, not point-in-time alpha evidence",
            "the pool omits three genuine sessions; appearance rates are observed-date descriptive and missing dates are not zero-imputed",
            "historical delisted, ST, listing, suspension, share-count, and float states are not supplied by this receipt",
            "BSE is inventoried but must use a separate 30-percent-band model",
            "pool membership says at least one appearance, not frequency-adjusted or investable return",
        ],
        "untested_variants": [
            "point-in-time cap and float incidence by board, rule era, liquidity, and listing age",
            "full-universe onset and continuation reruns",
            "observability-propensity weighting and matched-overlap sensitivity",
            "delisted-name and historical ST completeness",
        ],
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    return receipt


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    receipt = build_receipt()
    atomic_write(args.output, receipt)
    print(
        f"CN limit universe coverage: raw={receipt['universe']['raw_names']:,} "
        f"market={receipt['universe']['valuation_names']:,} "
        f"zt={receipt['zt_pool']['economic_names']:,} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
