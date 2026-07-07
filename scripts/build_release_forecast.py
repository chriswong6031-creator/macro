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
from datetime import date, datetime, timedelta, timezone
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

# Releases tracked by MRI v1+v2
_TRACKED_RELEASES = [
    ("cpi_headline", "cpi", "inflation"),
    ("cpi_core",     "cpi", "inflation"),
    ("nfp",          "nfp", "growth"),
    ("claims",       "claims", "growth"),
]

# Claims mode — set by §6 backtest verdict (research/release_forecast/CLAIMS_BACKTEST.md).
# Attempt 1 (ridge): MAE 40.839k vs naive 28.673k (full), 24.042k vs 14.790k (2021+) — FAILED.
# Attempt 2 (IC4WSA spec): MAE 43.855k vs naive 27.914k (full), 17.685k vs 14.755k (2021+) — FAILED.
# Kill rule: model MAE >= naive MAE in BOTH full window AND 2021+ slice -> benchmark_only.
# Both attempts failed; no attempt 3 without program-level adjudication (anti-mining law).
_CLAIMS_MODE = "benchmark_only"
_CLAIMS_BENCHMARK_ONLY_REASON = (
    "Walk-forward MAE (IC4WSA spec attempt 2: 43.9 thousand full, 17.7 thousand 2021+) fails to beat "
    "naive_prior (27.9 thousand full, 14.8 thousand 2021+). §6 kill rule triggered on both windows: "
    "benchmark-only mode (research/release_forecast/CLAIMS_BACKTEST.md). "
    "No attempt 3 without program-level adjudication."
)

# CPI family mapping for Cleveland nowcast (series name in nowcast.parquet)
_CLEVELAND_SERIES_MAP = {
    "cpi_headline": "cpi_mom",
    "cpi_core":     "core_cpi_mom",
}

# FRED series for revision sweep (current/latest value for scored releases)
_FRED_REVISION_SERIES = {
    "cpi_headline": "CPIAUCSL",
    "cpi_core":     "CPILFESL",
    "nfp":          "PAYEMS",
    # claims: ICSA level — no revision sweep (weekly, rarely revised)
}

# Revision-sweep idempotency key includes revised_value to allow multiple revisions
_REVISION_KEY = ("release", "period", "row_type", "revised_value")

# FRED vintage series for release-day capture
_FRED_VINTAGE_SERIES = {
    "cpi_headline": "CPIAUCSL",
    "cpi_core":     "CPILFESL",
    "nfp":          "PAYEMS",
    "claims":       "ICSA",
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
        elif etype == "CLAIMS":
            # Claims: weekly Thursday print — period = the Thursday date itself
            period_str = ev_date.isoformat()  # YYYY-MM-DD
            upcoming.append({
                "release_type": "claims",
                "release": "claims",
                "release_date": ev_date.isoformat(),
                "period": period_str,
                "regime_axis": "growth",
            })

    # Synthesize next-Thursday claims if event_calendar doesn't emit CLAIMS events
    # (CLAIMS events may not be in the static CY2026 fallback)
    has_claims = any(r["release_type"] == "claims" for r in upcoming)
    if not has_claims:
        # Next Thursday within horizon
        upcoming_claims = _next_thursday_claims(today, horizon_days)
        upcoming.extend(upcoming_claims)

    return upcoming


def _next_thursday_claims(today: date, horizon_days: int) -> list[dict]:
    """Synthesize the next 1-2 Thursday CLAIMS events within horizon_days."""
    out = []
    # Find next Thursday (weekday=3)
    days_until_thursday = (3 - today.weekday()) % 7
    if days_until_thursday == 0:
        days_until_thursday = 7  # today is Thursday → next Thursday
    next_thu = today + timedelta(days=days_until_thursday)
    for offset in (0, 7):
        ev_date = next_thu + timedelta(days=offset)
        if (ev_date - today).days > horizon_days:
            break
        period_str = ev_date.isoformat()
        out.append({
            "release_type": "claims",
            "release": "claims",
            "release_date": ev_date.isoformat(),
            "period": period_str,
            "regime_axis": "growth",
        })
    return out


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
    release_type: str,
    asof: date,
    root: Path,
    period_str: str | None = None,
    release_date: date | None = None,
) -> dict | None:
    """Call engine.release_forecast.project_release and return the result dict.
    period_str pins the reference month / period the upcoming print covers.
    release_date passed through for schema v2 horizon_days computation.
    Returns None on any error (fail-open)."""
    try:
        from engine.release_forecast import project_release
        if release_type in ("cpi_headline", "cpi_core"):
            ref_month = date.fromisoformat(period_str + "-01") if period_str else None
            return project_release(
                release_type, asof, root, ref_month=ref_month,
                period=period_str, release_date=release_date,
            )
        elif release_type == "nfp":
            return project_release(
                release_type, asof, root,
                period=period_str, release_date=release_date,
            )
        elif release_type == "claims":
            # Claims: pass the period (the Thursday date) through for ID generation
            return project_release(
                release_type, asof, root,
                period=period_str, release_date=release_date,
            )
        else:
            return project_release(release_type, asof, root)
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
            release_date_obj = date.fromisoformat(release_date)
            days_to = (release_date_obj - today).days
        except Exception:
            release_date_obj = None
            days_to = None

        # Run projection (T-1 of release date, but today is valid when > release date)
        proj_asof = today
        proj = _run_projection(rt, proj_asof, root, period_str=period_str, release_date=release_date_obj)

        if proj is None:
            # Emit a null projection placeholder
            # Claims uses trailing_4w key; all others use trailing_3m
            _null_trailing = (
                {"trailing_4w": None} if rt == "claims" else {"trailing_3m": None}
            )
            proj = {
                "release": rt,
                "asof": today.isoformat(),
                "point": None, "p10": None, "p25": None, "p50": None,
                "p75": None, "p90": None,
                "confidence": None,
                "input_completeness": 0.0,
                "benchmark_set": {
                    "naive_prior": None,
                    **_null_trailing,
                    "ar_model": None, "cleveland_nowcast": None, "market_implied": None,
                },
                "surprise_skew": {"sigma": None, "tag": None},
                "pit_provenance": {"reason": "projection_failed"},
                "display_only": True, "authority": False,
            }

        # Claims mode enforcement (§6 verdict from CLAIMS_BACKTEST.md)
        if rt == "claims" and _CLAIMS_MODE == "benchmark_only":
            proj["point"] = None
            proj["p10"] = proj["p25"] = proj["p50"] = proj["p75"] = proj["p90"] = None
            proj["confidence"] = None
            proj["input_completeness"] = None
            proj["surprise_skew"] = {}

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

        # Build projection block (benchmark_only mode carries mode/reason instead of values)
        _is_bmo = rt == "claims" and _CLAIMS_MODE == "benchmark_only"
        proj_block: dict = {}
        if _is_bmo:
            proj_block = {
                "mode": "benchmark_only",
                "reason": _CLAIMS_BENCHMARK_ONLY_REASON,
            }
        else:
            proj_block = {
                "point": proj.get("point"),
                "p10": proj.get("p10"),
                "p25": proj.get("p25"),
                "p50": proj.get("p50"),
                "p75": proj.get("p75"),
                "p90": proj.get("p90"),
            }

        row = {
            "release": ev["release"],
            "release_type": rt,
            "period": period_str,
            "release_date": release_date,
            "days_to": days_to,
            "target": target,
            "projection": proj_block,
            "confidence": proj.get("confidence") if not _is_bmo else None,
            "input_completeness": proj.get("input_completeness") if not _is_bmo else None,
            "benchmark_set": proj.get("benchmark_set", {}),
            "surprise_skew": proj.get("surprise_skew", {}) if not _is_bmo else {},
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
    """Build projection ledger rows for tonight's run (schema v2)."""
    from engine.release_forecast import make_release_id, make_prediction_id
    asof_night = today.isoformat()
    rows = []
    for item in upcoming_block:
        release_type = item.get("release_type")
        period_str = item.get("period")
        release_date_str = item.get("release_date")

        # v2 IDs
        try:
            _release_id = make_release_id(release_type, period_str)
            _pred_id = make_prediction_id(_release_id, asof_night)
        except Exception:
            _release_id = None
            _pred_id = None

        # horizon_days
        try:
            _horizon_days = (date.fromisoformat(release_date_str) - today).days if release_date_str else None
        except Exception:
            _horizon_days = None

        # inputs_hash from projection block (if engine emitted it)
        _inputs_hash = item.get("pit", {}).get("inputs_hash") or item.get("inputs_hash")

        row = {
            "schema": 2,
            "row_type": "projection",
            "asof_night": asof_night,
            "release": release_type,
            "period": period_str,
            "release_date": release_date_str,
            "release_id": _release_id,
            "prediction_id": _pred_id,
            "inputs_hash": _inputs_hash,
            "horizon_days": _horizon_days,
            "days_to": item.get("days_to"),
            "projection_mode": item.get("projection", {}).get("mode"),
            "projection_point": item.get("projection", {}).get("point"),
            "projection_p10": item.get("projection", {}).get("p10"),
            "projection_p25": item.get("projection", {}).get("p25"),
            "projection_p75": item.get("projection", {}).get("p75"),
            "projection_p90": item.get("projection", {}).get("p90"),
            "confidence": item.get("confidence"),
            "input_completeness": item.get("input_completeness"),
            "benchmark_naive_prior": (item.get("benchmark_set") or {}).get("naive_prior"),
            # Claims uses trailing_4w key; all others use trailing_3m
            "benchmark_trailing_3m": (item.get("benchmark_set") or {}).get("trailing_3m") if release_type != "claims" else None,
            "benchmark_trailing_4w": (item.get("benchmark_set") or {}).get("trailing_4w") if release_type == "claims" else None,
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

        # Target period: monthly releases append "-01"; claims require Thursday→Saturday mapping.
        # The producer stores period = Thursday release date (YYYY-MM-DD), but ALFRED stores
        # ICSA with period = week-ending Saturday (release_thursday − 5 days).
        # Verified: ICSA period 2009-05-30 (Sat) has realtime_start 2009-06-04 (Thu).
        if release_type == "claims":
            thursday_ts = pd.Timestamp(period_str)
            target_ts = thursday_ts - pd.Timedelta(days=5)  # map to preceding Saturday
        else:
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

    elif release_type == "claims":
        # ICSA is reported in raw persons; benchmark_set and projection use thousands.
        # Return the initial print divided by 1000.0 to match benchmark units.
        return round(raw_initial_print / 1000.0, 3)

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

        proj_mode = t1_proj.get("projection_mode")

        # Compute surprise vs our projection (null for benchmark_only mode)
        our_surprise = (
            round(actual - proj_point, 4)
            if (proj_point is not None and proj_mode != "benchmark_only")
            else None
        )

        # Benchmarks — claims uses trailing_4w key; all others use trailing_3m
        bench_naive = t1_proj.get("benchmark_naive_prior")
        if release_type == "claims":
            bench_trailing = t1_proj.get("benchmark_trailing_4w")
        else:
            bench_trailing = t1_proj.get("benchmark_trailing_3m")
        bench_ar = t1_proj.get("benchmark_ar_model")
        bench_cleveland = t1_proj.get("benchmark_cleveland")

        def _surprise_vs(bench: float | None) -> float | None:
            if bench is None or actual is None:
                return None
            return round(actual - bench, 4)

        # Interval hit: null in benchmark_only mode; actual within [proj_p10, proj_p90] otherwise
        interval_hit: bool | None = None
        if proj_mode != "benchmark_only" and proj_p10 is not None and proj_p90 is not None:
            interval_hit = bool(proj_p10 <= actual <= proj_p90)

        # Skew direction hit: null in benchmark_only mode
        skew_hit: bool | None = None
        bench_vals = [v for v in [bench_naive, bench_trailing, bench_ar, bench_cleveland] if v is not None]
        if proj_mode != "benchmark_only" and bench_vals and proj_point is not None and actual is not None:
            bench_median = float(np.median(bench_vals))
            our_direction = "hotter" if proj_point > bench_median else ("cooler" if proj_point < bench_median else "inline")
            actual_direction = "hotter" if actual > bench_median else ("cooler" if actual < bench_median else "inline")
            skew_hit = bool(our_direction == actual_direction)

        scored_row = {
            "schema": 2,
            "row_type": "scored",
            "asof_night": asof_night,
            "release": release_type,
            "period": period_str,
            "release_date": release_date_str,
            "actual": actual,
            "actual_first": actual,  # schema v2: capture = initial print, revision rows track drift
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
            "projection_mode": proj_mode,
            "benchmark_trailing_key": "trailing_4w" if release_type == "claims" else "trailing_3m",
        }
        scored_rows.append(scored_row)
        log.info("scored: %s/%s — actual=%.4f vs proj=%.4f", release_type, period_str, actual, proj_point or float("nan"))

    return scored_rows


# ---------------------------------------------------------------------------
# 8a. Revision sweep (schema v2)
# ---------------------------------------------------------------------------

def _get_latest_value(root: Path, release_type: str, period_str: str) -> float | None:
    """Return the LATEST known value for a (release_type, period) from vintages.

    Unlike _get_initial_print which requires realtime_start >= release_date,
    this returns the row with the LATEST realtime_start for any observation.
    Converts level → target variable using the same logic as _compute_actual_from_print.
    """
    series_id = _FRED_REVISION_SERIES.get(release_type)
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

        target_ts = pd.Timestamp(period_str + "-01")
        mask = (vdf["series"] == series_id) & (vdf["period"] == target_ts)
        sub = vdf[mask]
        if sub.empty:
            return None

        # Latest revision = largest realtime_start
        latest_row = sub.loc[sub["realtime_start"].idxmax()]
        raw_val = float(latest_row["value"])

        # Convert to target variable using same logic as _compute_actual_from_print
        return _compute_actual_from_print(release_type, raw_val, root, period_str)
    except Exception as e:
        log.debug("latest value lookup failed for %s/%s: %s", release_type, period_str, e)
        return None


def _check_revision_sweep(
    today: date,
    root: Path,
    existing_ledger: list[dict],
) -> list[dict]:
    """Nightly sweep: for each scored (release, period), check if the latest value
    differs from actual_first by more than 1e-9. If so, and no revision row with
    the same (release, period, revised_value) exists, append one.

    Returns list of new 'revision' rows. Append-only, idempotent.
    """
    revision_rows = []
    asof_night = today.isoformat()

    # Find all scored rows (unique by release, period — use the most recent scored row)
    scored_by_key: dict[tuple[str, str], dict] = {}
    for r in existing_ledger:
        if r.get("row_type") == "scored":
            key = (r.get("release", ""), r.get("period", ""))
            if key not in scored_by_key or r.get("asof_night", "") > scored_by_key[key].get("asof_night", ""):
                scored_by_key[key] = r

    # Build set of existing revision (release, period, revised_value) triples
    existing_revision_keys: set[tuple] = set()
    for r in existing_ledger:
        if r.get("row_type") == "revision":
            rv = r.get("revised_value")
            existing_revision_keys.add((
                r.get("release", ""),
                r.get("period", ""),
                round(rv, 9) if rv is not None else None,
            ))

    for (release_type, period_str), scored_row in scored_by_key.items():
        if not release_type or not period_str:
            continue
        if release_type not in _FRED_REVISION_SERIES:
            continue  # no revision series for claims

        actual_first = scored_row.get("actual_first") or scored_row.get("actual")
        if actual_first is None:
            continue

        latest_val = _get_latest_value(root, release_type, period_str)
        if latest_val is None:
            continue

        revision_pp = round(latest_val - actual_first, 6)
        if abs(revision_pp) <= 1e-9:
            continue  # no meaningful revision

        # Check idempotency: no existing revision row with same (release, period, revised_value)
        rv_key = (release_type, period_str, round(latest_val, 9))
        if rv_key in existing_revision_keys:
            continue

        revision_row = {
            "schema": 2,
            "row_type": "revision",
            "asof_night": asof_night,
            "release": release_type,
            "period": period_str,
            "actual_first": actual_first,
            "actual_latest": round(latest_val, 6),
            "revised_value": round(latest_val, 6),
            "revision_pp": revision_pp,
        }
        revision_rows.append(revision_row)
        log.info(
            "revision: %s/%s — actual_first=%.4f actual_latest=%.4f revision_pp=%.4f",
            release_type, period_str, actual_first, latest_val, revision_pp,
        )

    return revision_rows


# ---------------------------------------------------------------------------
# 8b. Reaction rows (schema v2)
# ---------------------------------------------------------------------------

_TRADING_WEEKDAYS = {0, 1, 2, 3, 4}  # Mon-Fri; simplified (no holiday calendar)


def _next_trading_day(d: date) -> date:
    """Return d if it's a trading day, else advance to the next Mon-Fri."""
    candidate = d
    while candidate.weekday() not in _TRADING_WEEKDAYS:
        candidate += timedelta(days=1)
    return candidate


def _nth_trading_day_after(d: date, n: int) -> date:
    """Return the nth trading session after d (h0 = release day, h1 = next session)."""
    # h0: first trading session ON or AFTER d
    session = _next_trading_day(d)
    for _ in range(n):
        session += timedelta(days=1)
        session = _next_trading_day(session)
    return session


def _read_series_close(path: Path, col: str, d: date) -> float | None:
    """Read daily close for a FRED or yahoo series at date d."""
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        ts = pd.Timestamp(d)
        if ts not in df.index:
            return None
        val = df.loc[ts, col]
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return float(val)
    except Exception as e:
        log.debug("series close read failed %s@%s: %s", path.name, d, e)
        return None


def _check_reaction_rows(
    today: date,
    root: Path,
    existing_ledger: list[dict],
) -> list[dict]:
    """For each scored release whose h1 (next trading session) close is now available,
    compute EOD market reaction fields and emit a 'reaction' row.

    One reaction row per (release, period). Append-only, idempotent.

    Fields emitted:
      dgs10_h0_bp, dgs10_h1_bp   — DGS10 daily change in bp (pct × 100)
      spread_2s10s_h0_bp         — T10Y2Y daily change in bp
      spy_h0_pct, spy_h1_pct     — SPY close-to-close pct change
      dollar_h0_pct              — DTWEXBGS close-to-close pct change

    h0 = release-day session close vs prior-day close
    h1 = next-session close vs h0-session close
    """
    reaction_rows = []
    asof_night = today.isoformat()

    # Existing reaction keys (release, period)
    existing_reaction_keys: set[tuple[str, str]] = {
        (r.get("release", ""), r.get("period", ""))
        for r in existing_ledger
        if r.get("row_type") == "reaction"
    }

    # Scored rows — latest per (release, period)
    scored_by_key: dict[tuple[str, str], dict] = {}
    for r in existing_ledger:
        if r.get("row_type") == "scored":
            key = (r.get("release", ""), r.get("period", ""))
            if key not in scored_by_key or r.get("asof_night", "") > scored_by_key[key].get("asof_night", ""):
                scored_by_key[key] = r

    # Series paths
    dgs10_path = root / "data" / "fred" / "DGS10.parquet"
    t10y2y_path = root / "data" / "fred" / "T10Y2Y.parquet"
    spy_path = root / "data" / "yahoo" / "SPY.parquet"
    dtwex_path = root / "data" / "fred" / "DTWEXBGS.parquet"

    for (release_type, period_str), scored_row in scored_by_key.items():
        if (release_type, period_str) in existing_reaction_keys:
            continue

        release_date_str = scored_row.get("release_date")
        if not release_date_str:
            continue
        try:
            release_date = date.fromisoformat(release_date_str)
        except ValueError:
            continue

        # h0 = release-day trading session (maps forward if weekend/holiday)
        h0_day = _next_trading_day(release_date)
        # h0_prior = the previous trading session before h0
        h0_prior_candidate = h0_day - timedelta(days=1)
        while h0_prior_candidate.weekday() not in _TRADING_WEEKDAYS:
            h0_prior_candidate -= timedelta(days=1)
        h0_prior = h0_prior_candidate
        # h1 = next session after h0
        h1_day = _nth_trading_day_after(h0_day, 1)

        # Need h1 data to be available (h1_day <= today)
        if h1_day > today:
            continue

        def _pct_change(close_cur: float | None, close_prev: float | None) -> float | None:
            if close_cur is None or close_prev is None or close_prev == 0:
                return None
            return round((close_cur / close_prev - 1) * 100, 4)

        def _level_diff_bp(cur: float | None, prev: float | None) -> float | None:
            """DGS10 and T10Y2Y are in pct; bp = diff × 100."""
            if cur is None or prev is None:
                return None
            return round((cur - prev) * 100, 2)

        # DGS10
        dgs10_h0_prior = _read_series_close(dgs10_path, "us10y", h0_prior)
        dgs10_h0 = _read_series_close(dgs10_path, "us10y", h0_day)
        dgs10_h1 = _read_series_close(dgs10_path, "us10y", h1_day)
        dgs10_h0_bp = _level_diff_bp(dgs10_h0, dgs10_h0_prior)
        dgs10_h1_bp = _level_diff_bp(dgs10_h1, dgs10_h0)

        # T10Y2Y (spread_2s10s)
        t10_h0_prior = _read_series_close(t10y2y_path, "spread_2s10s", h0_prior)
        t10_h0 = _read_series_close(t10y2y_path, "spread_2s10s", h0_day)
        spread_h0_bp = _level_diff_bp(t10_h0, t10_h0_prior)

        # SPY (use 'close' column per playbook convention)
        spy_h0_prior = _read_series_close(spy_path, "close", h0_prior)
        spy_h0 = _read_series_close(spy_path, "close", h0_day)
        spy_h1 = _read_series_close(spy_path, "close", h1_day)
        spy_h0_pct = _pct_change(spy_h0, spy_h0_prior)
        spy_h1_pct = _pct_change(spy_h1, spy_h0)

        # DTWEXBGS (broad dollar — index level; use pct change)
        dtwex_h0_prior = _read_series_close(dtwex_path, "broad_dollar", h0_prior)
        dtwex_h0 = _read_series_close(dtwex_path, "broad_dollar", h0_day)
        dollar_h0_pct = _pct_change(dtwex_h0, dtwex_h0_prior)

        # Need at least one data point to emit a row (fail-open: partial data is fine)
        all_none = all(v is None for v in [
            dgs10_h0_bp, dgs10_h1_bp, spread_h0_bp,
            spy_h0_pct, spy_h1_pct, dollar_h0_pct,
        ])
        if all_none:
            log.debug("reaction: all series absent for %s/%s — skipping", release_type, period_str)
            continue

        reaction_row = {
            "schema": 2,
            "row_type": "reaction",
            "asof_night": asof_night,
            "release": release_type,
            "period": period_str,
            "release_date": release_date_str,
            "h0_day": h0_day.isoformat(),
            "h1_day": h1_day.isoformat(),
            "dgs10_h0_bp": dgs10_h0_bp,
            "dgs10_h1_bp": dgs10_h1_bp,
            "spread_2s10s_h0_bp": spread_h0_bp,
            "spy_h0_pct": spy_h0_pct,
            "spy_h1_pct": spy_h1_pct,
            "dollar_h0_pct": dollar_h0_pct,
        }
        reaction_rows.append(reaction_row)
        log.info(
            "reaction: %s/%s — dgs10_h0_bp=%s spy_h0_pct=%s",
            release_type, period_str, dgs10_h0_bp, spy_h0_pct,
        )

    return reaction_rows


# ---------------------------------------------------------------------------
# 8c. Scoreboard
# ---------------------------------------------------------------------------

def _build_scoreboard(
    ledger: list[dict],
    accrual_start: str,
) -> dict:
    """Recompute scoreboard from scored ledger rows only. Forward-only.

    accrual_start: ISO date string of when forward accrual began.
    Schema v2 adds: interval_50_coverage (p25-p75 band hits), mae_vs_actual_latest
    (from revision rows where present), reaction summary (mean |dgs10_h0_bp|
    for hot/cold rows when n>=3, else null).
    """
    scored = [r for r in ledger if r.get("row_type") == "scored"]
    revision_rows = [r for r in ledger if r.get("row_type") == "revision"]
    reaction_rws = [r for r in ledger if r.get("row_type") == "reaction"]

    # Build revision index: (release, period) -> actual_latest
    revision_latest: dict[tuple[str, str], float] = {}
    for r in revision_rows:
        key = (r.get("release", ""), r.get("period", ""))
        rv = r.get("actual_latest") or r.get("revised_value")
        if rv is not None:
            # Keep the most recent revision (max asof_night)
            if key not in revision_latest or r.get("asof_night", "") > revision_latest.get(key + ("_asof",), ""):
                revision_latest[key] = float(rv)

    # Build reaction index: (release, period) -> {dgs10_h0_bp, ...}
    reaction_by_key: dict[tuple[str, str], dict] = {}
    for r in reaction_rws:
        key = (r.get("release", ""), r.get("period", ""))
        reaction_by_key[key] = r

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
                "interval_hits": [],       # p10-p90
                "interval_50_hits": [],    # p25-p75
                "skew_hits": [],
                "revision_errors": [],     # |proj - actual_latest|
                "reaction_dgs10_h0_abs": [],  # |dgs10_h0_bp| for hot/cold rows
            }
        g = per_release[rt]
        g["n"] += 1

        actual = row.get("actual")
        actual_first = row.get("actual_first") or actual
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

        # interval_50_coverage: check if actual falls within [proj_p25, proj_p75]
        p25 = row.get("frozen_projection_p25") or row.get("projection_p25")
        p75 = row.get("frozen_projection_p75") or row.get("projection_p75")
        if actual is not None and p25 is not None and p75 is not None:
            g["interval_50_hits"].append(bool(p25 <= actual <= p75))

        sh = row.get("skew_hit")
        if sh is not None:
            g["skew_hits"].append(bool(sh))

        # mae_vs_actual_latest: use revision data if available
        key = (rt, row.get("period", ""))
        actual_latest = revision_latest.get(key)
        if actual_latest is not None and proj is not None:
            g["revision_errors"].append(abs(actual_latest - proj))

        # Reaction summary: |dgs10_h0_bp| for hot/cold rows
        # hot = actual > benchmark_median, cold = actual < benchmark_median
        react = reaction_by_key.get(key)
        if react is not None:
            skew_tag = row.get("surprise_skew_tag") or row.get("skew_hit")
            # Use the actual vs naive to determine hot/cold
            bench_naive = row.get("benchmark_naive_prior")
            is_hot_or_cold = (
                actual is not None and bench_naive is not None
                and abs(actual - bench_naive) > 0
            )
            if is_hot_or_cold:
                dgs_h0 = react.get("dgs10_h0_bp")
                if dgs_h0 is not None:
                    g["reaction_dgs10_h0_abs"].append(abs(dgs_h0))

    release_stats: dict[str, dict] = {}
    for rt, g in per_release.items():
        n = g["n"]
        k_interval = sum(g["interval_hits"])
        n_interval = len(g["interval_hits"])
        k_interval_50 = sum(g["interval_50_hits"])
        n_interval_50 = len(g["interval_50_hits"])
        k_skew = sum(g["skew_hits"])
        n_skew = len(g["skew_hits"])

        def _mae(errs: list[float]) -> float | None:
            return round(float(np.mean(errs)), 4) if errs else None

        # Reaction summary: only report when n>=3
        reaction_dgs10_mean_abs = None
        if len(g["reaction_dgs10_h0_abs"]) >= 3:
            reaction_dgs10_mean_abs = round(float(np.mean(g["reaction_dgs10_h0_abs"])), 2)

        # Claims uses mae_trailing_4w label; all others use mae_trailing_3m
        trailing_label = "mae_trailing_4w" if rt == "claims" else "mae_trailing_3m"
        _entry: dict = {
            "n": n,
            "mae_ours": _mae(g["our_abs_errors"]),
            "mae_naive_prior": _mae(g["naive_abs_errors"]),
            trailing_label: _mae(g["trailing_abs_errors"]),
            "mae_ar_model": _mae(g["ar_abs_errors"]),
            "mae_cleveland": _mae(g["cleveland_abs_errors"]),
            # Schema v2 additions
            "mae_vs_actual_latest": _mae(g["revision_errors"]),
            "p10_p90_coverage": round(k_interval / n_interval, 4) if n_interval > 0 else None,
            "p10_p90_coverage_n": n_interval,
            # interval_50_coverage: p25-p75 band (approximates Codex [50%,75%] interval_60)
            # Note: this approximates interval_60 coverage; labeled clearly per MRI-R13
            "interval_50_coverage": round(k_interval_50 / n_interval_50, 4) if n_interval_50 > 0 else None,
            "interval_50_coverage_n": n_interval_50,
            "interval_50_coverage_note": "p25-p75 band; approximates Codex 60% interval (MRI-R13)",
            "skew_hit_rate": round(k_skew / n_skew, 4) if n_skew > 0 else None,
            "skew_hit_rate_n": n_skew,
            "skew_hit_rate_wilson_ci": _wilson(k_skew, n_skew),
            # Reaction usefulness descriptor (MRI-R17)
            "reaction_mean_abs_dgs10_h0_bp": reaction_dgs10_mean_abs,
            "reaction_n": len(g["reaction_dgs10_h0_abs"]),
        }
        if rt == "claims":
            _entry["block_note"] = (
                "MRI-R9: weekly claims residuals have strong autocorrelation. "
                "Reported MAE and coverage are computed on individual weekly prints; "
                "effective sample size is smaller than n due to serial correlation. "
                "Era-split results in research/release_forecast/CLAIMS_BACKTEST.md are "
                "the authoritative reference."
            )
        release_stats[rt] = _entry

    return {
        "schema": "release_forecast_scoreboard.v2",
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

    # 6a. Revision sweep (schema v2)
    combined_for_revision = existing_ledger + scored_rows
    revision_rows = _check_revision_sweep(today, root, combined_for_revision)
    log.info("revision sweep: %d new revision rows", len(revision_rows))

    # 6b. Reaction rows (schema v2)
    reaction_rows = _check_reaction_rows(today, root, combined_for_revision)
    log.info("reaction rows: %d new reaction rows", len(reaction_rows))

    # 7. Determine accrual start (earliest projection asof_night in ledger, or today)
    all_proj_nights = [
        r.get("asof_night", "")
        for r in existing_ledger + proj_ledger_rows
        if r.get("row_type") == "projection" and r.get("asof_night")
    ]
    accrual_start = min(all_proj_nights) if all_proj_nights else today.isoformat()

    # 8. Scoreboard from all scored + revision + reaction rows
    all_ledger_for_scoreboard = existing_ledger + scored_rows + revision_rows + reaction_rows
    scoreboard = _build_scoreboard(all_ledger_for_scoreboard, accrual_start)

    # 9. Build last_scored for latest.json (most recent scored row per release_type)
    all_scored = [r for r in existing_ledger if r.get("row_type") == "scored"] + scored_rows
    last_scored_by_rt: dict[str, dict] = {}
    for row in all_scored:
        rt = row.get("release", "")
        if rt not in last_scored_by_rt or row.get("asof_night", "") > last_scored_by_rt[rt].get("asof_night", ""):
            last_scored_by_rt[rt] = row
    last_scored = list(last_scored_by_rt.values())

    # 10. Assemble latest.json artifact (schema release_forecast.v2)
    latest = {
        "schema": "release_forecast.v2",
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

        # Append all new rows to ledger
        all_new_rows = proj_ledger_rows + scored_rows + revision_rows + reaction_rows
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
