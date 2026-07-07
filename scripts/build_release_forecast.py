"""MRI PR-C — nightly producer for release_forecast.v1.

Emits:
  data/release_forecast/latest.json        — schema release_forecast.v1
  site/macrodata/release_forecast.json     — display copy (byte-identical)
  data/release_forecast/forward_ledger.jsonl  — APPEND-ONLY; projection + scored rows
  data/release_forecast/scoreboard.json    — recomputed nightly from scored rows only

BINDINGS:
  MRI-R4  No LLM calls; no origination of values.
  MRI-R5  benchmark_set only; no fake consensus.
  MRI-R7  display_only=True; all authority booleans False.
  MRI-R8  forward_ledger.jsonl advanced ONLY by this script (nightly lane).

Fail-open: every IO / source failure degrades a field to null, never kills the build.
Idempotent: keyed on (release, period, row_type, asof_night) — re-running same night
adds zero duplicate ledger rows.

Usage:
    python -m scripts.build_release_forecast
    python -m scripts.build_release_forecast --root /path/to/repo --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("build_release_forecast")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Artifact paths
_LEDGER_RELPATH = "data/release_forecast/forward_ledger.jsonl"
_LATEST_RELPATH = "data/release_forecast/latest.json"
_SCOREBOARD_RELPATH = "data/release_forecast/scoreboard.json"
_SITE_RELPATH = "site/macrodata/release_forecast.json"

# Ledger key fields (idempotency guard)
_LEDGER_KEY = ("release", "period", "row_type", "asof_night")

# Releases tracked by MRI v1
_TRACKED_RELEASES = [
    ("cpi_headline", "cpi", "inflation"),
    ("cpi_core",     "cpi", "inflation"),
    ("nfp",          "nfp", "growth"),
]

# CPI family mapping for Cleveland nowcast (series name in nowcast.parquet)
_CLEVELAND_SERIES_MAP = {
    "cpi_headline": "cpi_mom",
    "cpi_core":     "core_cpi_mom",
}

# FRED vintage series for release-day capture
_FRED_VINTAGE_SERIES = {
    "cpi_headline": "CPIAUCSL",
    "cpi_core":     "CPILFESL",
    "nfp":          "PAYEMS",
}

# Wilson CI helper (reused from engine/release_forecast.py pattern)
def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if not n:
        return None
    phat = k / n
    d = 1 + z * z / n
    c = (phat + z * z / (2 * n)) / d
    h = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


# ---------------------------------------------------------------------------
# 1. Upcoming release discovery
# ---------------------------------------------------------------------------

def _find_upcoming_releases(today: date, horizon_days: int = 40) -> list[dict]:
    """Return upcoming CPI and NFP release dates within horizon_days.

    Each element: {release_type, release_date, period, label}
    """
    upcoming: list[dict] = []
    try:
        from engine.event_calendar import us_macro_events
        events = us_macro_events(today=today, horizon_days=horizon_days, use_fred=True)
    except Exception as e:
        log.warning("event_calendar call failed (%s) — using static fallback", e)
        events = []

    for ev in events:
        etype = ev.get("type", "")
        ev_date_raw = ev.get("date")
        if not ev_date_raw:
            continue
        if isinstance(ev_date_raw, str):
            try:
                ev_date = date.fromisoformat(ev_date_raw)
            except ValueError:
                continue
        elif isinstance(ev_date_raw, date):
            ev_date = ev_date_raw
        else:
            continue

        if ev_date <= today:
            continue

        if etype == "CPI":
            # CPI event covers both headline and core for the same period
            # Reference period = the month BEFORE the release month
            ref_month = date(ev_date.year, ev_date.month, 1)
            # The CPI release in month M covers month M-1
            ref_m1 = (pd.Timestamp(ref_month) - pd.offsets.MonthBegin(1)).date()
            period_str = f"{ref_m1.year}-{ref_m1.month:02d}"
            upcoming.append({
                "release_type": "cpi_headline",
                "release": "cpi",
                "release_date": ev_date.isoformat(),
                "period": period_str,
                "regime_axis": "inflation",
            })
            upcoming.append({
                "release_type": "cpi_core",
                "release": "cpi",
                "release_date": ev_date.isoformat(),
                "period": period_str,
                "regime_axis": "inflation",
            })
        elif etype == "NFP":
            ref_month = date(ev_date.year, ev_date.month, 1)
            ref_m1 = (pd.Timestamp(ref_month) - pd.offsets.MonthBegin(1)).date()
            period_str = f"{ref_m1.year}-{ref_m1.month:02d}"
            upcoming.append({
                "release_type": "nfp",
                "release": "nfp",
                "release_date": ev_date.isoformat(),
                "period": period_str,
                "regime_axis": "growth",
            })

    return upcoming


# ---------------------------------------------------------------------------
# 2. Cleveland nowcast benchmark enrichment
# ---------------------------------------------------------------------------

def _read_cleveland_nowcast(root: Path, release_type: str, period_str: str, today: date) -> float | None:
    """Read the Cleveland nowcast for the target period/series, PIT-safe (obs_date <= today).

    Returns the value from the latest obs_date for the matching series and target_period,
    where obs_date <= today. Absent file / rows → None (fail-open).
    """
    series = _CLEVELAND_SERIES_MAP.get(release_type)
    if series is None:
        return None
    path = root / "data" / "cleveland_nowcast" / "nowcast.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        # Normalize types
        df["obs_date"] = pd.to_datetime(df["obs_date"])
        df["target_period"] = pd.to_datetime(df["target_period"])

        # Match target period (period_str = "YYYY-MM")
        target_ts = pd.Timestamp(period_str + "-01")
        today_ts = pd.Timestamp(today)

        mask = (
            (df["series"] == series) &
            (df["target_period"] == target_ts) &
            (df["obs_date"] <= today_ts)
        )
        sub = df[mask]
        if sub.empty:
            return None
        # Latest obs_date
        latest_row = sub.loc[sub["obs_date"].idxmax()]
        val = float(latest_row["value"])
        return val if np.isfinite(val) else None
    except Exception as e:
        log.debug("cleveland_nowcast read failed for %s/%s: %s", release_type, period_str, e)
        return None


# ---------------------------------------------------------------------------
# 3. Policy backdrop join (read-only, display)
# ---------------------------------------------------------------------------

def _read_policy_backdrop(root: Path, today: date) -> dict:
    """Assemble policy_backdrop from persisted artifacts only. Fail-open: any
    missing source degrades its field to null; no LLM calls."""
    backdrop = {
        "fed_stance": None,
        "gap_bp": None,
        "implied_cuts_12m": None,
        "next_fomc": None,
        "guidance_direction": None,
    }

    # --- fed_stance and gap_bp from data/regime/latest.json ---
    regime_path = root / "data" / "regime" / "latest.json"
    if regime_path.exists():
        try:
            with open(regime_path, encoding="utf-8") as fh:
                regime = json.load(fh)

            fed_stance_block = regime.get("fed_stance") or {}
            backdrop["fed_stance"] = fed_stance_block.get("stance") or None
            backdrop["implied_cuts_12m"] = fed_stance_block.get("implied_cuts_12m")

            fed_path_block = regime.get("fed_path") or {}
            gap_block = fed_path_block.get("gap") or {}
            backdrop["gap_bp"] = gap_block.get("gap_bp")

            # guidance_direction from catalyst_tone (persisted in latest.json)
            catalyst = regime.get("catalyst_tone") or {}
            guidance = catalyst.get("guidance_direction")
            backdrop["guidance_direction"] = guidance if guidance else None
        except Exception as e:
            log.debug("regime/latest.json read failed: %s", e)

    # --- next FOMC from event_calendar ---
    try:
        from engine.event_calendar import us_macro_events
        events = us_macro_events(today=today, horizon_days=120, use_fred=False)
        for ev in sorted(events, key=lambda e: e.get("date", "")):
            if ev.get("type") == "FOMC":
                ev_date_raw = ev.get("date")
                if isinstance(ev_date_raw, str):
                    try:
                        ev_date = date.fromisoformat(ev_date_raw)
                    except ValueError:
                        continue
                elif isinstance(ev_date_raw, date):
                    ev_date = ev_date_raw
                else:
                    continue
                if ev_date > today:
                    backdrop["next_fomc"] = ev_date.isoformat()
                    break
    except Exception as e:
        log.debug("next_fomc lookup failed: %s", e)

    return backdrop


# ---------------------------------------------------------------------------
# 4. Projection driver
# ---------------------------------------------------------------------------

def _run_projection(
    release_type: str, asof: date, root: Path, period_str: str | None = None
) -> dict | None:
    """Call engine.release_forecast.project_release and return the result dict.
    period_str ("YYYY-MM", from the event calendar) pins the reference month the
    upcoming print covers — the gasoline_mom leg is anchored on it (PREREG_V1.md §2.3).
    Returns None on any error (fail-open)."""
    try:
        from engine.release_forecast import project_release
        ref_month = date.fromisoformat(period_str + "-01") if period_str else None
        return project_release(release_type, asof, root, ref_month=ref_month)
    except Exception as e:
        log.warning("project_release(%s, %s) failed: %s", release_type, asof, e)
        return None


# ---------------------------------------------------------------------------
# 5. Build upcoming block
# ---------------------------------------------------------------------------

def _build_upcoming_block(
    today: date,
    root: Path,
    upcoming_releases: list[dict],
    policy_backdrop: dict,
) -> list[dict]:
    """Build the 'upcoming' list for the latest.json artifact."""
    out = []
    seen_keys: set[tuple[str, str]] = set()  # (release_type, period) dedup

    for ev in upcoming_releases:
        rt = ev["release_type"]
        period_str = ev["period"]
        key = (rt, period_str)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        release_date = ev["release_date"]
        try:
            days_to = (date.fromisoformat(release_date) - today).days
        except Exception:
            days_to = None

        # Run projection (T-1 of release date, but today is valid when > release date)
        proj_asof = today
        proj = _run_projection(rt, proj_asof, root, period_str=period_str)

        if proj is None:
            # Emit a null projection placeholder
            proj = {
                "release": rt,
                "asof": today.isoformat(),
                "point": None, "p10": None, "p25": None, "p50": None,
                "p75": None, "p90": None,
                "confidence": None,
                "input_completeness": 0.0,
                "benchmark_set": {
                    "naive_prior": None, "trailing_3m": None,
                    "ar_model": None, "cleveland_nowcast": None, "market_implied": None,
                },
                "surprise_skew": {"sigma": None, "tag": None},
                "pit_provenance": {"reason": "projection_failed"},
                "display_only": True, "authority": False,
            }

        # Enrich Cleveland nowcast benchmark
        cleveland_val = _read_cleveland_nowcast(root, rt, period_str, today)
        if "benchmark_set" in proj:
            proj["benchmark_set"]["cleveland_nowcast"] = cleveland_val
        # market_implied stays null (come-back C-2)

        # Determine target (for display)
        if rt in ("cpi_headline", "cpi_core"):
            target = "mom_sa_pct"
        else:
            target = "change_thousands"

        row = {
            "release": ev["release"],
            "release_type": rt,
            "period": period_str,
            "release_date": release_date,
            "days_to": days_to,
            "target": target,
            "projection": {
                "point": proj.get("point"),
                "p10": proj.get("p10"),
                "p25": proj.get("p25"),
                "p50": proj.get("p50"),
                "p75": proj.get("p75"),
                "p90": proj.get("p90"),
            },
            "confidence": proj.get("confidence"),
            "input_completeness": proj.get("input_completeness"),
            "benchmark_set": proj.get("benchmark_set", {}),
            "surprise_skew": proj.get("surprise_skew", {}),
            "pit": proj.get("pit_provenance", {}),
            "regime_axis": ev["regime_axis"],
            "policy_backdrop": policy_backdrop,
        }
        out.append(row)

    return out


# ---------------------------------------------------------------------------
# 6. Forward ledger management
# ---------------------------------------------------------------------------

def _load_ledger(ledger_path: Path) -> list[dict]:
    """Load existing ledger rows from the JSONL file."""
    if not ledger_path.exists():
        return []
    rows = []
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                log.debug("skipping malformed ledger line: %r", line[:80])
    return rows


def _ledger_key(row: dict) -> tuple:
    return tuple(row.get(f) for f in _LEDGER_KEY)


def _append_ledger_rows(ledger_path: Path, new_rows: list[dict]) -> None:
    """Append new rows to the ledger file (idempotent: skip already-keyed rows)."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_ledger(ledger_path)
    existing_keys = {_ledger_key(r) for r in existing}

    to_write = [r for r in new_rows if _ledger_key(r) not in existing_keys]
    if not to_write:
        log.info("ledger: 0 new rows to append (all already present)")
        return

    with open(ledger_path, "a", encoding="utf-8") as fh:
        for row in to_write:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    log.info("ledger: appended %d new rows", len(to_write))


def _build_projection_ledger_rows(
    today: date,
    upcoming_block: list[dict],
    policy_backdrop: dict,
) -> list[dict]:
    """Build projection ledger rows for tonight's run."""
    asof_night = today.isoformat()
    rows = []
    for item in upcoming_block:
        row = {
            "row_type": "projection",
            "asof_night": asof_night,
            "release": item.get("release_type"),
            "period": item.get("period"),
            "release_date": item.get("release_date"),
            "days_to": item.get("days_to"),
            "projection_point": item.get("projection", {}).get("point"),
            "projection_p10": item.get("projection", {}).get("p10"),
            "projection_p90": item.get("projection", {}).get("p90"),
            "confidence": item.get("confidence"),
            "input_completeness": item.get("input_completeness"),
            "benchmark_naive_prior": (item.get("benchmark_set") or {}).get("naive_prior"),
            "benchmark_trailing_3m": (item.get("benchmark_set") or {}).get("trailing_3m"),
            "benchmark_ar_model": (item.get("benchmark_set") or {}).get("ar_model"),
            "benchmark_cleveland": (item.get("benchmark_set") or {}).get("cleveland_nowcast"),
            "surprise_skew_sigma": (item.get("surprise_skew") or {}).get("sigma"),
            "surprise_skew_tag": (item.get("surprise_skew") or {}).get("tag"),
            "fed_stance": policy_backdrop.get("fed_stance"),
            "gap_bp": policy_backdrop.get("gap_bp"),
            "implied_cuts_12m": policy_backdrop.get("implied_cuts_12m"),
            "next_fomc": policy_backdrop.get("next_fomc"),
        }
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 7. Release-day capture (score frozen T-1 projections against initial prints)
# ---------------------------------------------------------------------------

def _get_initial_print(
    root: Path,
    release_type: str,
    period_str: str,
    release_date_str: str,
) -> float | None:
    """Get the initial print for a (release_type, period) from ALFRED vintages.

    The initial print = the row with the earliest realtime_start for this period,
    where realtime_start falls on or after the release_date (the ALFRED initial
    release, not a pre-release revision).

    Returns None if not available.
    """
    series_id = _FRED_VINTAGE_SERIES.get(release_type)
    if series_id is None:
        return None

    vintage_path = root / "data" / "fred_vintage" / "vintages.parquet"
    if not vintage_path.exists():
        return None

    try:
        vdf = pd.read_parquet(vintage_path)
        if vdf.empty:
            return None

        for col in ("period", "realtime_start"):
            if col in vdf.columns:
                vdf[col] = pd.to_datetime(vdf[col])

        # Target period (first of month)
        target_ts = pd.Timestamp(period_str + "-01")
        release_ts = pd.Timestamp(release_date_str)

        mask = (
            (vdf["series"] == series_id) &
            (vdf["period"] == target_ts) &
            (vdf["realtime_start"] >= release_ts)
        )
        sub = vdf[mask]
        if sub.empty:
            return None

        # Initial print = earliest realtime_start
        init_row = sub.loc[sub["realtime_start"].idxmin()]
        val = float(init_row["value"])
        return val if np.isfinite(val) else None
    except Exception as e:
        log.debug("initial print lookup failed for %s/%s: %s", release_type, period_str, e)
        return None


def _compute_actual_from_print(
    release_type: str,
    raw_initial_print: float,
    root: Path,
    period_str: str,
) -> float | None:
    """Convert initial print level to the target variable (MoM % for CPI, change for NFP).

    For CPI: compute MoM % from current vs prior month level.
    For NFP: compute change from current vs prior month level.
    """
    if release_type in ("cpi_headline", "cpi_core"):
        series_id = _FRED_VINTAGE_SERIES[release_type]
        vintage_path = root / "data" / "fred_vintage" / "vintages.parquet"
        if not vintage_path.exists():
            return None
        try:
            vdf = pd.read_parquet(vintage_path)
            vdf["period"] = pd.to_datetime(vdf["period"])
            vdf["realtime_start"] = pd.to_datetime(vdf["realtime_start"])

            target_ts = pd.Timestamp(period_str + "-01")
            prior_ts = target_ts - pd.offsets.MonthBegin(1)

            # Get latest known prior month level
            prior_mask = (
                (vdf["series"] == series_id) &
                (vdf["period"] == prior_ts)
            )
            prior_sub = vdf[prior_mask]
            if prior_sub.empty:
                return None
            prior_val = float(prior_sub.loc[prior_sub["realtime_start"].idxmax()]["value"])
            if prior_val == 0:
                return None
            return round((raw_initial_print / prior_val - 1) * 100, 4)
        except Exception as e:
            log.debug("CPI MoM computation failed: %s", e)
            return None

    elif release_type == "nfp":
        series_id = "PAYEMS"
        vintage_path = root / "data" / "fred_vintage" / "vintages.parquet"
        if not vintage_path.exists():
            return None
        try:
            vdf = pd.read_parquet(vintage_path)
            vdf["period"] = pd.to_datetime(vdf["period"])
            vdf["realtime_start"] = pd.to_datetime(vdf["realtime_start"])

            target_ts = pd.Timestamp(period_str + "-01")
            prior_ts = target_ts - pd.offsets.MonthBegin(1)

            prior_mask = (
                (vdf["series"] == series_id) &
                (vdf["period"] == prior_ts)
            )
            prior_sub = vdf[prior_mask]
            if prior_sub.empty:
                return None
            # Use initial print of prior month as base (closest to what was known on release day)
            prior_val = float(prior_sub.loc[prior_sub["realtime_start"].idxmin()]["value"])
            return round(raw_initial_print - prior_val, 2)
        except Exception as e:
            log.debug("NFP change computation failed: %s", e)
            return None

    return None


def _check_release_day_capture(
    today: date,
    root: Path,
    existing_ledger: list[dict],
) -> list[dict]:
    """Check if any tracked (release, period) has printed today and not yet been scored.

    Returns a list of new 'scored' rows to append.
    """
    scored_rows = []
    asof_night = today.isoformat()

    # Find projection rows in the ledger that don't yet have a corresponding scored row
    # keyed on (release, period)
    existing_scored_keys: set[tuple[str, str]] = {
        (r["release"], r["period"])
        for r in existing_ledger
        if r.get("row_type") == "scored"
    }

    for proj_row in existing_ledger:
        if proj_row.get("row_type") != "projection":
            continue

        release_type = proj_row.get("release")
        period_str = proj_row.get("period")
        release_date_str = proj_row.get("release_date")

        if not release_type or not period_str or not release_date_str:
            continue

        # Already scored?
        if (release_type, period_str) in existing_scored_keys:
            continue

        # Check if the release date has passed
        try:
            release_date = date.fromisoformat(release_date_str)
        except ValueError:
            continue

        if today < release_date:
            continue  # not yet released

        # Try to get initial print
        raw_print = _get_initial_print(root, release_type, period_str, release_date_str)
        if raw_print is None:
            log.debug("no initial print found for %s/%s as of %s", release_type, period_str, asof_night)
            continue

        actual = _compute_actual_from_print(release_type, raw_print, root, period_str)
        if actual is None:
            log.debug("could not convert initial print to target variable for %s/%s", release_type, period_str)
            continue

        # Frozen T-1 projection (latest projection row for this release/period,
        # where asof_night < release_date — find the most recent such row)
        proj_candidates = [
            r for r in existing_ledger
            if r.get("row_type") == "projection"
            and r.get("release") == release_type
            and r.get("period") == period_str
            and r.get("asof_night", "") < release_date_str
        ]
        if not proj_candidates:
            log.debug("no T-1 projection found for %s/%s", release_type, period_str)
            continue

        # Most recent T-1 projection
        t1_proj = max(proj_candidates, key=lambda r: r.get("asof_night", ""))

        proj_point = t1_proj.get("projection_point")
        proj_p10 = t1_proj.get("projection_p10")
        proj_p90 = t1_proj.get("projection_p90")

        # Compute surprise vs our projection
        our_surprise = round(actual - proj_point, 4) if proj_point is not None else None

        # Benchmarks
        bench_naive = t1_proj.get("benchmark_naive_prior")
        bench_trailing = t1_proj.get("benchmark_trailing_3m")
        bench_ar = t1_proj.get("benchmark_ar_model")
        bench_cleveland = t1_proj.get("benchmark_cleveland")

        def _surprise_vs(bench: float | None) -> float | None:
            if bench is None or actual is None:
                return None
            return round(actual - bench, 4)

        # Interval hit: actual within [proj_p10, proj_p90]
        interval_hit: bool | None = None
        if proj_p10 is not None and proj_p90 is not None:
            interval_hit = bool(proj_p10 <= actual <= proj_p90)

        # Skew direction hit: did our skew_tag correctly call the direction vs benchmark median?
        skew_hit: bool | None = None
        bench_vals = [v for v in [bench_naive, bench_trailing, bench_ar, bench_cleveland] if v is not None]
        if bench_vals and proj_point is not None and actual is not None:
            bench_median = float(np.median(bench_vals))
            our_direction = "hotter" if proj_point > bench_median else ("cooler" if proj_point < bench_median else "inline")
            actual_direction = "hotter" if actual > bench_median else ("cooler" if actual < bench_median else "inline")
            skew_hit = bool(our_direction == actual_direction)

        scored_row = {
            "row_type": "scored",
            "asof_night": asof_night,
            "release": release_type,
            "period": period_str,
            "release_date": release_date_str,
            "actual": actual,
            "raw_initial_print": raw_print,
            "frozen_asof_night": t1_proj.get("asof_night"),
            "frozen_projection_point": proj_point,
            "frozen_projection_p10": proj_p10,
            "frozen_projection_p90": proj_p90,
            "our_surprise": our_surprise,
            "surprise_vs_naive": _surprise_vs(bench_naive),
            "surprise_vs_trailing": _surprise_vs(bench_trailing),
            "surprise_vs_ar": _surprise_vs(bench_ar),
            "surprise_vs_cleveland": _surprise_vs(bench_cleveland),
            "interval_hit": interval_hit,
            "skew_hit": skew_hit,
        }
        scored_rows.append(scored_row)
        log.info("scored: %s/%s — actual=%.4f vs proj=%.4f", release_type, period_str, actual, proj_point or float("nan"))

    return scored_rows


# ---------------------------------------------------------------------------
# 8. Scoreboard
# ---------------------------------------------------------------------------

def _build_scoreboard(
    ledger: list[dict],
    accrual_start: str,
) -> dict:
    """Recompute scoreboard from scored ledger rows only. Forward-only.

    accrual_start: ISO date string of when forward accrual began.
    """
    scored = [r for r in ledger if r.get("row_type") == "scored"]

    # Per release-type aggregation
    per_release: dict[str, dict] = {}
    for row in scored:
        rt = row.get("release", "unknown")
        if rt not in per_release:
            per_release[rt] = {
                "n": 0,
                "our_abs_errors": [],
                "naive_abs_errors": [],
                "trailing_abs_errors": [],
                "ar_abs_errors": [],
                "cleveland_abs_errors": [],
                "interval_hits": [],
                "skew_hits": [],
            }
        g = per_release[rt]
        g["n"] += 1

        actual = row.get("actual")
        proj = row.get("frozen_projection_point")
        if actual is not None and proj is not None:
            g["our_abs_errors"].append(abs(actual - proj))

        for bench_key, err_key in [
            ("surprise_vs_naive", "naive_abs_errors"),
            ("surprise_vs_trailing", "trailing_abs_errors"),
            ("surprise_vs_ar", "ar_abs_errors"),
            ("surprise_vs_cleveland", "cleveland_abs_errors"),
        ]:
            v = row.get(bench_key)
            if v is not None:
                g[err_key].append(abs(v))

        ih = row.get("interval_hit")
        if ih is not None:
            g["interval_hits"].append(bool(ih))

        sh = row.get("skew_hit")
        if sh is not None:
            g["skew_hits"].append(bool(sh))

    release_stats: dict[str, dict] = {}
    for rt, g in per_release.items():
        n = g["n"]
        k_interval = sum(g["interval_hits"])
        n_interval = len(g["interval_hits"])
        k_skew = sum(g["skew_hits"])
        n_skew = len(g["skew_hits"])

        def _mae(errs: list[float]) -> float | None:
            return round(float(np.mean(errs)), 4) if errs else None

        release_stats[rt] = {
            "n": n,
            "mae_ours": _mae(g["our_abs_errors"]),
            "mae_naive_prior": _mae(g["naive_abs_errors"]),
            "mae_trailing_3m": _mae(g["trailing_abs_errors"]),
            "mae_ar_model": _mae(g["ar_abs_errors"]),
            "mae_cleveland": _mae(g["cleveland_abs_errors"]),
            "p10_p90_coverage": round(k_interval / n_interval, 4) if n_interval > 0 else None,
            "p10_p90_coverage_n": n_interval,
            "skew_hit_rate": round(k_skew / n_skew, 4) if n_skew > 0 else None,
            "skew_hit_rate_n": n_skew,
            "skew_hit_rate_wilson_ci": _wilson(k_skew, n_skew),
        }

    return {
        "schema": "release_forecast_scoreboard.v1",
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "forward_accrual_began": accrual_start,
        "note": "Forward-only: no backtest rows enter this scoreboard (MRI-R8).",
        "by_release": release_stats,
    }


# ---------------------------------------------------------------------------
# 9. Main build
# ---------------------------------------------------------------------------

def build(root: Path, dry_run: bool = False) -> dict:
    """Main nightly build entry point. Returns the latest.json payload."""
    today = date.today()
    asof_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    log.info("build_release_forecast: asof=%s, today=%s", asof_utc, today)

    # 1. Find upcoming releases
    upcoming_releases = _find_upcoming_releases(today, horizon_days=40)
    log.info("found %d upcoming release events in 40-day window", len(upcoming_releases))

    # 2. Policy backdrop
    policy_backdrop = _read_policy_backdrop(root, today)
    log.info("policy_backdrop: stance=%s gap_bp=%s next_fomc=%s",
             policy_backdrop.get("fed_stance"),
             policy_backdrop.get("gap_bp"),
             policy_backdrop.get("next_fomc"))

    # 3. Build upcoming projection block
    upcoming_block = _build_upcoming_block(today, root, upcoming_releases, policy_backdrop)
    log.info("built %d upcoming projection entries", len(upcoming_block))

    # 4. Load existing ledger
    ledger_path = root / _LEDGER_RELPATH
    existing_ledger = _load_ledger(ledger_path)
    log.info("loaded %d existing ledger rows", len(existing_ledger))

    # 5. Build today's projection ledger rows
    proj_ledger_rows = _build_projection_ledger_rows(today, upcoming_block, policy_backdrop)

    # 6. Release-day capture (check if any tracked release printed)
    scored_rows = _check_release_day_capture(today, root, existing_ledger)
    log.info("release-day capture: %d new scored rows", len(scored_rows))

    # 7. Determine accrual start (earliest projection asof_night in ledger, or today)
    all_proj_nights = [
        r.get("asof_night", "")
        for r in existing_ledger + proj_ledger_rows
        if r.get("row_type") == "projection" and r.get("asof_night")
    ]
    accrual_start = min(all_proj_nights) if all_proj_nights else today.isoformat()

    # 8. Scoreboard from all scored rows (existing + new)
    all_scored = [r for r in existing_ledger if r.get("row_type") == "scored"] + scored_rows
    scoreboard = _build_scoreboard(all_scored, accrual_start)

    # 9. Build last_scored for latest.json (most recent scored row per release_type)
    last_scored_by_rt: dict[str, dict] = {}
    for row in all_scored:
        rt = row.get("release", "")
        if rt not in last_scored_by_rt or row.get("asof_night", "") > last_scored_by_rt[rt].get("asof_night", ""):
            last_scored_by_rt[rt] = row
    last_scored = list(last_scored_by_rt.values())

    # 10. Assemble latest.json artifact (schema release_forecast.v1)
    latest = {
        "schema": "release_forecast.v1",
        "asof": asof_utc,
        "display_only": True,
        "authority": {
            "can_score": False,
            "can_size": False,
            "can_trade": False,
        },
        "upcoming": upcoming_block,
        "last_scored": last_scored,
        "scoreboard_ref": "data/release_forecast/scoreboard.json",
    }

    if not dry_run:
        # Write latest.json
        latest_path = root / _LATEST_RELPATH
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(latest_path, "w", encoding="utf-8") as fh:
            json.dump(latest, fh, indent=2, default=str)
        log.info("wrote %s", latest_path)

        # Write site copy (display copy — byte-identical)
        site_path = root / _SITE_RELPATH
        site_path.parent.mkdir(parents=True, exist_ok=True)
        with open(site_path, "w", encoding="utf-8") as fh:
            json.dump(latest, fh, indent=2, default=str)
        log.info("wrote %s", site_path)

        # Append projection + scored rows to ledger
        all_new_rows = proj_ledger_rows + scored_rows
        _append_ledger_rows(ledger_path, all_new_rows)

        # Write scoreboard
        scoreboard_path = root / _SCOREBOARD_RELPATH
        scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
        with open(scoreboard_path, "w", encoding="utf-8") as fh:
            json.dump(scoreboard, fh, indent=2, default=str)
        log.info("wrote %s", scoreboard_path)

    return latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MRI PR-C nightly producer")
    parser.add_argument("--root", default=str(_REPO_ROOT), help="Repo root")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no writes")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    root = Path(args.root)
    try:
        result = build(root, dry_run=args.dry_run)
        if args.dry_run:
            print(json.dumps(result, indent=2, default=str))
        log.info("build_release_forecast: complete")
        return 0
    except Exception as e:
        log.exception("build_release_forecast: FATAL — %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
