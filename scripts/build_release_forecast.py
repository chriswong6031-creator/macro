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
# MRI-R26: provenance snapshots dir (one JSON per prediction_id)
_INPUT_SNAPSHOTS_RELPATH = "data/release_forecast/input_snapshots"

# Ledger key fields (idempotency guard).
# Round-2b: extended with "model" so champion (model=None) and shadow rows coexist
# without collision. Champion rows have model=None (unchanged); shadows carry model string.
_LEDGER_KEY = ("release", "period", "row_type", "asof_night", "model")

# Shadow model targets: which release_types each shadow model covers
_SHADOW_V3_TARGETS = {"cpi_headline", "cpi_core", "nfp"}
_SHADOW_BRIDGE_TARGETS = {"cpi_headline"}  # cpi_core bridge killed/closed (MRI-R25)

# W11-G: mf_energy shadow (Track T, MRI-R36) — cpi_headline only
_SHADOW_MF_ENERGY_TARGETS = {"cpi_headline"}

# MRI-R40: combined_v1 combination layer — cpi_headline + cpi_core only (prereg §2.1)
_SHADOW_COMBINED_V1_TARGETS = {"cpi_headline", "cpi_core"}

# MRI-R21: NFP v3_factor warning (trails champion; sub-naive on full 2010+ window)
_NFP_V3_WARNING = (
    "trails champion; sub-naive on full-window backtest (2010+ MAE v3=527.9 vs naive=459.8), "
    "catastrophic 2020-recovery error — do not read as an improvement "
    "(MRI-R21 shadow, champion keeps the card)"
)

# Releases tracked by MRI v1+v2 (Round 2a: PCE/PPI/retail added MRI-R23)
_TRACKED_RELEASES = [
    ("cpi_headline",    "cpi",    "inflation"),
    ("cpi_core",        "cpi",    "inflation"),
    ("nfp",             "nfp",    "growth"),
    ("claims",          "claims", "growth"),
    ("pce_headline",    "pce",    "inflation"),
    ("pce_core",        "pce",    "inflation"),
    ("ppi_finaldemand", "ppi",    "inflation"),
    ("retail_sales",    "retail", "growth"),
]

# MRI-R22: expectation-read band threshold (must match engine/release_market_context.py)
_EXPECTATION_BAND_THRESHOLD = 0.35

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

# CPI/PCE family mapping for Cleveland nowcast (series name in nowcast.parquet)
# MRI-R34: also maps pce_headline/pce_core using the pce_mom/core_pce_mom series
# that exist in the live store.
_CLEVELAND_SERIES_MAP = {
    "cpi_headline": "cpi_mom",
    "cpi_core":     "core_cpi_mom",
    "pce_headline": "pce_mom",
    "pce_core":     "core_pce_mom",
}

# MRI-R32d: tracked release series whose ALFRED vintages must refresh NIGHTLY
# (not weekly). These are the series whose initial prints land within the
# scoring window. The 7-day mtime gate is kept for the rest of DEFAULT_VINTAGE_SERIES.
_NIGHTLY_VINTAGE_SERIES = frozenset([
    "CPIAUCSL", "CPILFESL", "PAYEMS", "ICSA", "IC4WSA", "CCSA",
    "PCEPI", "PCEPILFE", "PPIFIS", "PPIFES",
])

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
        elif etype == "PCE":
            # PCE release covers the prior month (same offset as CPI)
            ref_month = date(ev_date.year, ev_date.month, 1)
            ref_m1 = (pd.Timestamp(ref_month) - pd.offsets.MonthBegin(1)).date()
            period_str = f"{ref_m1.year}-{ref_m1.month:02d}"
            upcoming.append({
                "release_type": "pce_headline",
                "release": "pce",
                "release_date": ev_date.isoformat(),
                "period": period_str,
                "regime_axis": "inflation",
            })
            upcoming.append({
                "release_type": "pce_core",
                "release": "pce",
                "release_date": ev_date.isoformat(),
                "period": period_str,
                "regime_axis": "inflation",
            })
        elif etype == "PPI":
            # PPI release covers the prior month
            ref_month = date(ev_date.year, ev_date.month, 1)
            ref_m1 = (pd.Timestamp(ref_month) - pd.offsets.MonthBegin(1)).date()
            period_str = f"{ref_m1.year}-{ref_m1.month:02d}"
            upcoming.append({
                "release_type": "ppi_finaldemand",
                "release": "ppi",
                "release_date": ev_date.isoformat(),
                "period": period_str,
                "regime_axis": "inflation",
            })

    # Synthesize next-Thursday claims if event_calendar doesn't emit CLAIMS events
    # (CLAIMS events may not be in the static CY2026 fallback)
    has_claims = any(r["release_type"] == "claims" for r in upcoming)
    if not has_claims:
        # Next Thursday within horizon
        upcoming_claims = _next_thursday_claims(today, horizon_days)
        upcoming.extend(upcoming_claims)

    # MRI-R23: retail_sales scaffold — no calendar entry; emit no_data stub always.
    # Attempt clock (#1 of 2) has NOT started; RSAFS parquet absent (2026-07-08).
    # The stub ships the machinery so provenance/coverage flows through without a date.
    upcoming.append({
        "release_type": "retail_sales",
        "release": "retail",
        "release_date": None,  # unknown until RSAFS calendar wired
        "period": None,        # unknown
        "regime_axis": "growth",
        "no_data": True,
        "no_data_reason": "no_data_rsafs_absent",
    })

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
    """Read the Cleveland nowcast for the target period/series, PIT-safe.

    MRI-R34 fix: PIT law uses first_seen_asof <= asof (not obs_date <= asof).
    The store schema is: first_seen_asof / target_period / series / obs_date / value.
    We select rows where first_seen_asof <= today AND target_period matches, then
    pick the latest obs_date among those rows as the best available nowcast.

    Returns the value from the latest obs_date among PIT-eligible rows,
    or None if absent / fail-open.
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
        # Normalize types — first_seen_asof and obs_date stored as strings in practice
        df["obs_date"] = pd.to_datetime(df["obs_date"])
        df["target_period"] = pd.to_datetime(df["target_period"])
        df["first_seen_asof"] = pd.to_datetime(df["first_seen_asof"])

        # Match target period (period_str = "YYYY-MM")
        target_ts = pd.Timestamp(period_str + "-01")
        today_ts = pd.Timestamp(today)

        # MRI-R34 PIT fix: filter on first_seen_asof <= today (not obs_date)
        mask = (
            (df["series"] == series) &
            (df["target_period"] == target_ts) &
            (df["first_seen_asof"] <= today_ts)
        )
        sub = df[mask]
        if sub.empty:
            return None
        # From PIT-eligible rows, take the one with the latest obs_date
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
        elif release_type in ("pce_headline", "pce_core", "ppi_finaldemand"):
            # MRI-R23: new inflation targets — route to release_targets_v11 via project_release
            ref_month = date.fromisoformat(period_str + "-01") if period_str else None
            return project_release(
                release_type, asof, root, ref_month=ref_month,
                period=period_str, release_date=release_date,
            )
        elif release_type == "retail_sales":
            # MRI-R23: retail scaffold — no_data until RSAFS on disk
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
        if rt in ("cpi_headline", "cpi_core", "pce_headline", "pce_core", "ppi_finaldemand"):
            target = "mom_sa_pct"
        elif rt in ("retail_sales",):
            target = "mom_sa_pct"  # once RSAFS accrues; no_data for now
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
            # input_manifest: feature values from projection — passed to _attach_provenance
            # so compute_coverage_flags sees real feature names in its denominator (MRI-R26 rework-2a).
            "input_manifest": proj.get("input_manifest") or {},
            "regime_axis": ev["regime_axis"],
            "policy_backdrop": policy_backdrop,
            # Champion attribution (4 ridge blocks: energy/shelter/core_persistence/pipeline).
            # Null for benchmark_only mode. Used by UI "Component attribution" section distinct
            # from the cpi_bridge waterfall shadow (MRI-R26 rework-ui).
            "components": proj.get("components") if not _is_bmo else None,
            # Confidence v2 — richer breakdown than scalar confidence.
            "confidence_v2": proj.get("confidence_v2"),
            "confidence_components_v2": proj.get("confidence_components_v2"),
            # NFP revision risk (None for all non-NFP release types).
            "revision_risk": proj.get("revision_risk"),
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
    # "model" key defaults to None for champion rows (backward-compatible with pre-2b ledger rows
    # that lack the key). Shadow rows carry an explicit model string.
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
        fh.flush()
        import os as _os
        _os.fsync(fh.fileno())  # MRI-R33 DURABILITY-1: fsync ledger appends
    log.info("ledger: appended %d new rows", len(to_write))


def _attach_provenance(
    upcoming_block: list[dict],
    ledger_path: Path,
    snapshots_dir: Path,
    dry_run: bool = False,
) -> None:
    """MRI-R26: attach input_snapshot and coverage flags to each upcoming item in-place.

    For each item:
      1. Reconstruct a minimal projection dict from the item for snapshot/coverage.
      2. Call engine.release_provenance.build_input_snapshot → write to snapshots_dir/<prediction_id>.json
         (fail-open: IO error → no file, log only).
      3. Set item["input_snapshot_ref"] to the relative path string.
      4. Call engine.release_provenance.compute_coverage_flags → attach four flags as
         item["coverage_flags"].

    AUTHORITY CONTRACT (MRI-R26 / MRI-R2 / MRI-R3):
      - Coverage flags are METADATA ONLY.
      - They NEVER appear in / influence point/interval/skew/confidence.
      - Nothing in this function reads coverage values back into any projection field.

    Fail-open: any error → log, continue (no field attached or null).
    """
    try:
        from engine.release_provenance import build_input_snapshot, compute_coverage_flags
    except Exception as exc:
        log.warning("release_provenance import failed — provenance enrichment skipped: %s", exc)
        return

    for item in upcoming_block:
        rt = item.get("release_type", "")
        pit = item.get("pit") or {}

        # Pre-compute prediction_id in the same way as _build_projection_ledger_rows
        # so the snapshot filename matches the ledger row.
        _period_str = item.get("period") or ""
        _pred_id_for_snap = ""
        _asof_night_str = date.today().isoformat()
        try:
            from engine.release_forecast import make_release_id, make_prediction_id
            if rt and _period_str:
                _release_id = make_release_id(rt, _period_str)
                _pred_id_for_snap = make_prediction_id(_release_id, _asof_night_str)
        except Exception:
            pass

        # Build a minimal projection dict for the provenance module.
        # The provenance module reads pit_provenance, input_manifest, and optionally _features.
        # input_manifest: real feature values stored on the item row (rework-2a MRI-R26 fix);
        # these are used by _declared_legs to count vintaged legs in the denominator.
        proj_for_prov: dict = {
            "release": rt,
            "asof": _asof_night_str,
            "pit_provenance": pit,
            "inputs_hash": pit.get("inputs_hash") or "",
            "input_manifest": item.get("input_manifest") or {},
            "display_only": True,
            "authority": False,
            "prediction_id": _pred_id_for_snap,
        }

        # 1. Input snapshot
        try:
            snapshot = build_input_snapshot(proj_for_prov)
            pred_id = snapshot.get("prediction_id") or ""
            # Write to disk (fail-open)
            ref_path: str | None = None
            if pred_id and not dry_run:
                try:
                    snapshots_dir.mkdir(parents=True, exist_ok=True)
                    # Sanitize prediction_id for use as filename
                    safe_name = pred_id.replace(":", "_").replace("/", "_")
                    snap_file = snapshots_dir / f"{safe_name}.json"
                    with open(snap_file, "w", encoding="utf-8") as fh:
                        json.dump(snapshot, fh, indent=2, default=str)
                    # Store relative path (from repo root)
                    try:
                        ref_path = str(snap_file.relative_to(snapshots_dir.parent.parent.parent))
                    except ValueError:
                        ref_path = str(snap_file)
                except Exception as exc_io:
                    log.debug("provenance snapshot write failed for %s: %s", pred_id, exc_io)
            item["input_snapshot_ref"] = ref_path
        except Exception as exc:
            log.debug("build_input_snapshot failed for %s: %s", rt, exc)
            item["input_snapshot_ref"] = None

        # 2. Coverage flags — DISPLAY-ONLY METADATA; must not feed back into projections
        try:
            flags = compute_coverage_flags(proj_for_prov, ledger_path)
            # AUTHORITY WALL: copy only the four declared flags; never touch point/interval/skew
            item["coverage_flags"] = {
                "weight_coverage":      flags.get("weight_coverage"),
                "fresh_proxy_coverage": flags.get("fresh_proxy_coverage"),
                "non_vintaged_share":   flags.get("non_vintaged_share"),
                "model_maturity":       flags.get("model_maturity"),
            }
        except Exception as exc:
            log.debug("compute_coverage_flags failed for %s: %s", rt, exc)
            item["coverage_flags"] = None


def _run_shadow_v3(
    release_type: str,
    asof: date,
    root: Path,
    period_str: str | None,
    release_date_obj: date | None,
) -> dict | None:
    """Call project_release_v3 for a supported release_type. Fail-open: returns None on error.

    Supports: cpi_headline, cpi_core, nfp. All others return None immediately.
    DISPLAY-ONLY: result carries display_only=True, authority=False.
    """
    if release_type not in _SHADOW_V3_TARGETS:
        return None
    try:
        from engine.release_forecast_v3 import project_release_v3
        ref_month: date | None = None
        if period_str and release_type in ("cpi_headline", "cpi_core"):
            try:
                ref_month = date.fromisoformat(period_str + "-01")
            except Exception:
                pass
        result = project_release_v3(
            release_type, asof, root,
            ref_month=ref_month,
            period=period_str,
            release_date=release_date_obj,
        )
        return result
    except Exception as e:
        log.warning("shadow v3_factor(%s, %s) failed — skipping: %s", release_type, asof, e)
        return None


def _run_shadow_bridge(
    release_type: str,
    asof: date,
    root: Path,
    period_str: str | None,
) -> dict | None:
    """Call compute_cpi_bridge for cpi_headline only. Fail-open: returns None on error.

    cpi_core bridge is killed/closed (MRI-R25). Any other release_type returns None.
    DISPLAY-ONLY: result carries display_only=True, authority=False.
    """
    if release_type not in _SHADOW_BRIDGE_TARGETS:
        return None
    try:
        from engine.release_cpi_bridge import compute_cpi_bridge
        ref_month: date | None = None
        if period_str:
            try:
                ref_month = date.fromisoformat(period_str + "-01")
            except Exception:
                pass
        result = compute_cpi_bridge(
            asof=asof,
            root=root,
            ref_month=ref_month,
            release=release_type,
        )
        return result
    except Exception as e:
        log.warning("shadow cpi_bridge(%s, %s) failed — skipping: %s", release_type, asof, e)
        return None


def _run_shadow_mf_energy(
    release_type: str,
    asof: date,
    root: Path,
    period_str: str | None,
    release_date_obj: date | None,
) -> dict | None:
    """Call project_release_mf for cpi_headline only. Fail-open: returns None on error.

    W11-G task 1: mf_energy shadow (MRI-R36, Track T).
    DISPLAY-ONLY: result carries display_only=True, authority=False, model='mf_energy'.
    """
    if release_type not in _SHADOW_MF_ENERGY_TARGETS:
        return None
    try:
        from engine.release_mf_energy import project_release_mf
        ref_month: date | None = None
        if period_str:
            try:
                ref_month = date.fromisoformat(period_str + "-01")
            except Exception:
                pass
        result = project_release_mf(
            release=release_type,
            asof=asof,
            root=root,
            ref_month=ref_month,
            period=period_str,
            cutoff_label="T-1",
        )
        return result
    except Exception as e:
        log.warning("shadow mf_energy(%s, %s) failed — skipping: %s", release_type, asof, e)
        return None


def _attach_shadows_to_items(upcoming_block: list[dict], root: Path, today: date) -> None:
    """Attach item["shadows"] to each upcoming item that has shadow models. In-place.

    Only cpi_headline, cpi_core, nfp receive v3_factor; only cpi_headline receives
    cpi_bridge and mf_energy. pce/ppi/claims/retail do not receive shadows.
    Each shadow entry is display_only=True.
    Fail-open: a shadow that errors is simply skipped (logged in _run_shadow_*).
    """
    _all_shadow_targets = _SHADOW_V3_TARGETS | _SHADOW_BRIDGE_TARGETS | _SHADOW_MF_ENERGY_TARGETS
    for item in upcoming_block:
        rt = item.get("release_type", "")
        if rt not in _all_shadow_targets:
            continue

        period_str = item.get("period")
        release_date_str = item.get("release_date")
        release_date_obj: date | None = None
        if release_date_str:
            try:
                release_date_obj = date.fromisoformat(release_date_str)
            except Exception:
                pass

        shadows: dict = {}

        # v3_factor shadow
        if rt in _SHADOW_V3_TARGETS:
            try:
                v3_result = _run_shadow_v3(rt, today, root, period_str, release_date_obj)
            except Exception as _e:
                log.warning("_attach_shadows v3_factor(%s) raised — skipping: %s", rt, _e)
                v3_result = None
            if v3_result is not None:
                entry: dict = {
                    "display_only": True,
                    "point": v3_result.get("point"),
                    "p10": v3_result.get("p10"),
                    "p25": v3_result.get("p25"),
                    "p50": v3_result.get("p50"),
                    "p75": v3_result.get("p75"),
                    "p90": v3_result.get("p90"),
                    "confidence": v3_result.get("confidence"),
                    "input_completeness": v3_result.get("input_completeness"),
                }
                if rt == "nfp":
                    entry["warning"] = _NFP_V3_WARNING
                shadows["v3_factor"] = entry

        # cpi_bridge shadow (cpi_headline only)
        if rt in _SHADOW_BRIDGE_TARGETS:
            try:
                bridge_result = _run_shadow_bridge(rt, today, root, period_str)
            except Exception as _e:
                log.warning("_attach_shadows cpi_bridge(%s) raised — skipping: %s", rt, _e)
                bridge_result = None
            if bridge_result is not None:
                shadows["cpi_bridge"] = {
                    "display_only": True,
                    "point": bridge_result.get("point"),
                    "components": bridge_result.get("components"),
                    "prior_driven_share": bridge_result.get("prior_driven_share"),
                    "coverage_residual_pp": bridge_result.get("coverage_residual_pp"),
                    "weight_coverage": bridge_result.get("weight_coverage"),
                    "confidence": bridge_result.get("confidence"),
                }

        # W11-G task 1: mf_energy shadow (cpi_headline only, Track T MRI-R36)
        if rt in _SHADOW_MF_ENERGY_TARGETS:
            try:
                mfe_result = _run_shadow_mf_energy(rt, today, root, period_str, release_date_obj)
            except Exception as _e:
                log.warning("_attach_shadows mf_energy(%s) raised — skipping: %s", rt, _e)
                mfe_result = None
            if mfe_result is not None:
                shadows["mf_energy"] = {
                    "display_only": True,
                    "point": mfe_result.get("point"),
                    "p10": mfe_result.get("p10"),
                    "p25": mfe_result.get("p25"),
                    "p50": mfe_result.get("p50"),
                    "p75": mfe_result.get("p75"),
                    "p90": mfe_result.get("p90"),
                    "confidence": mfe_result.get("confidence"),
                    "input_completeness": mfe_result.get("input_completeness"),
                    "mf_energy_components": mfe_result.get("mf_energy_components"),
                }

        if shadows:
            item["shadows"] = shadows


def _attach_combined_to_items(
    upcoming_block: list[dict],
    existing_ledger: list[dict],
    root: Path,
    today: date,
) -> None:
    """MRI-R40: attach item["combined"] for cpi_headline and cpi_core. In-place.

    Runs AFTER _attach_shadows_to_items so shadow points are available.
    Reads scored errors from existing_ledger to compute shrunk inverse-MAE weights.

    Sets item["combined"] = {
        "combined_point", "p10", "p25", "p50", "p75", "p90",
        "combined_components", "n_scored_basis",
        "display_only": True, "authority": False,
    }
    or item["combined"] = None when <2 non-null inputs are available.
    """
    try:
        from engine.release_combined import (
            compute_combined_point,
            extract_scored_errors,
        )
    except Exception as exc:
        log.warning("release_combined import failed — combined_v1 skipped: %s", exc)
        return

    for item in upcoming_block:
        rt = item.get("release_type", "")
        if rt not in _SHADOW_COMBINED_V1_TARGETS:
            continue

        period_str = item.get("period")

        # --- Gather tonight's input points ---
        proj_block = item.get("projection") or {}
        shadows = item.get("shadows") or {}

        # Champion point
        champ_pt = proj_block.get("point")

        # Shadow points
        v3_pt = (shadows.get("v3_factor") or {}).get("point")
        bridge_pt = (shadows.get("cpi_bridge") or {}).get("point")
        mfe_pt = (shadows.get("mf_energy") or {}).get("point")

        # Cleveland: already fetched into benchmark_set
        bench = item.get("benchmark_set") or {}
        cleveland_pt = bench.get("cleveland_nowcast")

        inputs: dict = {
            "champion":  champ_pt,
            "v3_factor": v3_pt,
        }
        # cpi_bridge and mf_energy: cpi_headline only per prereg §2.2
        if rt == "cpi_headline":
            inputs["cpi_bridge"] = bridge_pt
            inputs["mf_energy"] = mfe_pt
        inputs["cleveland"] = cleveland_pt

        # sigma_champion: from surprise_skew (sigma_scale_pp)
        skew = item.get("surprise_skew") or {}
        sigma_champion = skew.get("sigma_scale_pp")

        # --- Scored errors from existing ledger ---
        try:
            scored_errors = extract_scored_errors(existing_ledger, rt)
        except Exception as exc:
            log.warning("extract_scored_errors failed for %s: %s", rt, exc)
            scored_errors = {}

        # n_scored_basis: number of champion scored rows for this release
        n_scored_basis = sum(
            1 for r in existing_ledger
            if r.get("row_type") == "scored"
            and r.get("release") == rt
            and r.get("model") is None
        )

        # --- Compute combined ---
        try:
            result = compute_combined_point(inputs, scored_errors, sigma_champion)
        except Exception as exc:
            log.warning("compute_combined_point raised for %s/%s: %s", rt, period_str, exc)
            result = None

        if result is not None:
            item["combined"] = {
                "combined_point": result["combined_point"],
                "p10": result["p10"],
                "p25": result["p25"],
                "p50": result["p50"],
                "p75": result["p75"],
                "p90": result["p90"],
                "combined_components": result["combined_components"],
                "n_scored_basis": n_scored_basis,
                "display_only": True,
                "authority": False,
            }
            log.debug(
                "combined_v1 %s/%s: point=%.4f n_active=%d cold_start=%s",
                rt, period_str, result["combined_point"],
                len(result["combined_components"].get("inputs_used", [])),
                result["combined_components"].get("cold_start"),
            )
        else:
            item["combined"] = None
            log.debug("combined_v1 %s/%s: None (<2 inputs)", rt, period_str)


def _build_shadow_ledger_rows(
    today: date,
    upcoming_block: list[dict],
    root: Path,
) -> list[dict]:
    """Build shadow_projection ledger rows for tonight's run.

    One row per (release_type, model) that has a shadow. Champion projection rows
    (row_type="projection") are NOT touched by this function.

    Row shape mirrors champion projection rows with additions:
      - row_type = "shadow_projection"
      - model = "v3_factor" | "cpi_bridge" | "mf_energy"
      - prediction_id includes model slug
      - cpi_bridge carries components, coverage_residual_pp, prior_driven_share
    """
    from engine.release_forecast import make_release_id, make_prediction_id
    asof_night = today.isoformat()
    rows = []

    _all_shadow_targets = (
        _SHADOW_V3_TARGETS | _SHADOW_BRIDGE_TARGETS
        | _SHADOW_MF_ENERGY_TARGETS | _SHADOW_COMBINED_V1_TARGETS
    )
    for item in upcoming_block:
        release_type = item.get("release_type")
        period_str = item.get("period")
        release_date_str = item.get("release_date")

        if release_type not in _all_shadow_targets:
            continue

        release_date_obj: date | None = None
        if release_date_str:
            try:
                release_date_obj = date.fromisoformat(release_date_str)
            except Exception:
                pass

        try:
            _release_id = make_release_id(release_type, period_str)
        except Exception:
            _release_id = None

        _horizon_days: int | None = None
        if release_date_obj:
            try:
                _horizon_days = (release_date_obj - today).days
            except Exception:
                pass

        # v3_factor shadow row
        if release_type in _SHADOW_V3_TARGETS:
            try:
                v3_result = _run_shadow_v3(release_type, today, root, period_str, release_date_obj)
            except Exception as _e:
                log.warning("_build_shadow_ledger v3_factor(%s) raised — skipping: %s", release_type, _e)
                v3_result = None
            if v3_result is not None:
                try:
                    _pred_id = make_prediction_id(
                        _release_id, f"{asof_night}:v3_factor"
                    ) if _release_id else None
                except Exception:
                    _pred_id = None

                row: dict = {
                    "schema": 2,
                    "row_type": "shadow_projection",
                    "model": "v3_factor",
                    "asof_night": asof_night,
                    "release": release_type,
                    "period": period_str,
                    "release_date": release_date_str,
                    "release_id": _release_id,
                    "prediction_id": _pred_id,
                    "horizon_days": _horizon_days,
                    "projection_point": v3_result.get("point"),
                    "projection_p10": v3_result.get("p10"),
                    "projection_p25": v3_result.get("p25"),
                    "projection_p50": v3_result.get("p50"),
                    "projection_p75": v3_result.get("p75"),
                    "projection_p90": v3_result.get("p90"),
                    "confidence": v3_result.get("confidence"),
                    "input_completeness": v3_result.get("input_completeness"),
                    "display_only": True,
                    "authority": False,
                }
                if release_type == "nfp":
                    row["warning"] = _NFP_V3_WARNING
                rows.append(row)
            else:
                log.debug("shadow_projection v3_factor skipped for %s/%s (None result)", release_type, period_str)

        # cpi_bridge shadow row (cpi_headline only)
        if release_type in _SHADOW_BRIDGE_TARGETS:
            try:
                bridge_result = _run_shadow_bridge(release_type, today, root, period_str)
            except Exception as _e:
                log.warning("_build_shadow_ledger cpi_bridge(%s) raised — skipping: %s", release_type, _e)
                bridge_result = None
            if bridge_result is not None:
                try:
                    _pred_id_br = make_prediction_id(
                        _release_id, f"{asof_night}:cpi_bridge"
                    ) if _release_id else None
                except Exception:
                    _pred_id_br = None

                row_br: dict = {
                    "schema": 2,
                    "row_type": "shadow_projection",
                    "model": "cpi_bridge",
                    "asof_night": asof_night,
                    "release": release_type,
                    "period": period_str,
                    "release_date": release_date_str,
                    "release_id": _release_id,
                    "prediction_id": _pred_id_br,
                    "horizon_days": _horizon_days,
                    "projection_point": bridge_result.get("point"),
                    "projection_p10": None,  # bridge is point-only
                    "projection_p25": None,
                    "projection_p50": None,
                    "projection_p75": None,
                    "projection_p90": None,
                    "confidence": bridge_result.get("confidence"),
                    "components": bridge_result.get("components"),
                    "coverage_residual_pp": bridge_result.get("coverage_residual_pp"),
                    "prior_driven_share": bridge_result.get("prior_driven_share"),
                    "weight_coverage": bridge_result.get("weight_coverage"),
                    "display_only": True,
                    "authority": False,
                }
                rows.append(row_br)
            else:
                log.debug("shadow_projection cpi_bridge skipped for %s/%s (None result)", release_type, period_str)

        # W11-G task 1: mf_energy shadow row (cpi_headline only, Track T MRI-R36)
        if release_type in _SHADOW_MF_ENERGY_TARGETS:
            try:
                mfe_result = _run_shadow_mf_energy(release_type, today, root, period_str, release_date_obj)
            except Exception as _e:
                log.warning("_build_shadow_ledger mf_energy(%s) raised — skipping: %s", release_type, _e)
                mfe_result = None
            if mfe_result is not None:
                try:
                    _pred_id_mfe = make_prediction_id(
                        _release_id, f"{asof_night}:mf_energy"
                    ) if _release_id else None
                except Exception:
                    _pred_id_mfe = None

                row_mfe: dict = {
                    "schema": 2,
                    "row_type": "shadow_projection",
                    "model": "mf_energy",
                    "asof_night": asof_night,
                    "release": release_type,
                    "period": period_str,
                    "release_date": release_date_str,
                    "release_id": _release_id,
                    "prediction_id": _pred_id_mfe,
                    "horizon_days": _horizon_days,
                    "projection_point": mfe_result.get("point"),
                    "projection_p10": mfe_result.get("p10"),
                    "projection_p25": mfe_result.get("p25"),
                    "projection_p50": mfe_result.get("p50"),
                    "projection_p75": mfe_result.get("p75"),
                    "projection_p90": mfe_result.get("p90"),
                    "confidence": mfe_result.get("confidence"),
                    "input_completeness": mfe_result.get("input_completeness"),
                    "mf_energy_components": mfe_result.get("mf_energy_components"),
                    "display_only": True,
                    "authority": False,
                }
                rows.append(row_mfe)
            else:
                log.debug("shadow_projection mf_energy skipped for %s/%s (None result)", release_type, period_str)

        # MRI-R40: combined_v1 shadow row (cpi_headline + cpi_core)
        # combined data was attached by _attach_combined_to_items before this call.
        if release_type in _SHADOW_COMBINED_V1_TARGETS:
            combined_data = item.get("combined")
            if combined_data is not None:
                try:
                    _pred_id_cv1 = make_prediction_id(
                        _release_id, f"{asof_night}:combined_v1"
                    ) if _release_id else None
                except Exception:
                    _pred_id_cv1 = None

                row_cv1: dict = {
                    "schema": 2,
                    "row_type": "shadow_projection",
                    "model": "combined_v1",
                    "asof_night": asof_night,
                    "release": release_type,
                    "period": period_str,
                    "release_date": release_date_str,
                    "release_id": _release_id,
                    "prediction_id": _pred_id_cv1,
                    "horizon_days": _horizon_days,
                    "projection_point": combined_data.get("combined_point"),
                    "projection_p10": combined_data.get("p10"),
                    "projection_p25": combined_data.get("p25"),
                    "projection_p50": combined_data.get("p50"),
                    "projection_p75": combined_data.get("p75"),
                    "projection_p90": combined_data.get("p90"),
                    "combined_components": combined_data.get("combined_components"),
                    "n_scored_basis": combined_data.get("n_scored_basis"),
                    "display_only": True,
                    "authority": False,
                }
                rows.append(row_cv1)
                log.debug(
                    "shadow_projection combined_v1 built for %s/%s: point=%.4f",
                    release_type, period_str, combined_data.get("combined_point") or float("nan"),
                )
            else:
                log.debug("shadow_projection combined_v1 skipped for %s/%s (null result)", release_type, period_str)

    return rows


def _assign_cutoff_labels(upcoming_block: list[dict]) -> None:
    """MRI-R35: assign cutoff_label in-place to each upcoming item.

    For each release_type, sort items by release_date. The nearest upcoming
    release gets 'T-1'; all subsequent items for the same release_type get 'early'.
    Items with no release_date get 'early' (treated as far-future).
    Claims: each week is its own period, so each gets 'T-1' for its own slot
    (there is at most 1-2 claims rows — both get 'T-1' by the ordering rule if
    they are distinct periods).
    """
    # Group by release_type, sort by release_date, label nearest as T-1
    from collections import defaultdict
    by_rt: dict[str, list[dict]] = defaultdict(list)
    for item in upcoming_block:
        by_rt[item.get("release_type", "")].append(item)

    for rt, items in by_rt.items():
        # Sort: items without release_date sort last (treated as far future)
        def _sort_key(x: dict) -> str:
            rd = x.get("release_date")
            return rd if rd else "9999-99-99"

        items_sorted = sorted(items, key=_sort_key)
        for i, item in enumerate(items_sorted):
            item["cutoff_label"] = "T-1" if i == 0 else "early"


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
            "model": None,  # Champion rows: model=None; shadows carry explicit model string
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
            # MRI-R20: freeze quirk flag codes (list of code strings) as annotation
            "quirk_flag_codes": [f["code"] for f in (item.get("quirk_flags") or [])],
            # MRI-R22: freeze expectation_read snapshot so forward grading can score it
            "expectation_read": item.get("expectation_read"),
            # freeze sigma_scale_pp for scoring: needed to re-derive bands at score time
            "sigma_scale_pp": (item.get("surprise_skew") or {}).get("sigma_scale_pp"),
            # MRI-R26: provenance coverage flags (display-only metadata; never influence projections)
            "coverage_weight_coverage":      (item.get("coverage_flags") or {}).get("weight_coverage"),
            "coverage_fresh_proxy_coverage": (item.get("coverage_flags") or {}).get("fresh_proxy_coverage"),
            "coverage_non_vintaged_share":   (item.get("coverage_flags") or {}).get("non_vintaged_share"),
            "coverage_model_maturity":       (item.get("coverage_flags") or {}).get("model_maturity"),
            # MRI-R26: reference to on-disk input snapshot (path string or None)
            "input_snapshot_ref":            item.get("input_snapshot_ref"),
            # MRI-R35: cutoff label — 'T-1' for nearest upcoming period, 'early' for later
            "cutoff_label": item.get("cutoff_label"),
            # W11-G task 3: freeze print_integrity regime on ledger row (display-only)
            "print_integrity_regime": item.get("print_integrity_regime"),
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

            # FIX 4: use EARLIEST vintage (initial print) of prior month, matching training.
            # Training uses initial prints via knowable_series/pct_change on first-print rows.
            # Using idxmax (latest revision) here created a training/scoring PIT mismatch.
            prior_mask = (
                (vdf["series"] == series_id) &
                (vdf["period"] == prior_ts)
            )
            prior_sub = vdf[prior_mask]
            if prior_sub.empty:
                return None
            prior_val = float(prior_sub.loc[prior_sub["realtime_start"].idxmin()]["value"])
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
    lookback_days: int = 120,
) -> list[dict]:
    """MRI-R32a/b/c: Catch-up scoring sweep — score ANY unscored past-release
    projection AND shadow_projection row whose initial print is available.

    MRI-R32a: bounded lookback 120d; idempotent on existing scored keys.
    MRI-R32b: T-1 candidate filter = asof_night <= release_date (not strictly <),
      preferring latest strictly-pre-release row. Release-day rows stamped
      frozen_on_release_day=True and annotated; never dropped.
    MRI-R32c: late back-projection only when NO pre-release row exists, flagged
      late=True in the scored row.

    Returns list of new 'scored' rows to append.
    """
    scored_rows = []
    asof_night = today.isoformat()
    lookback_cutoff = (today - timedelta(days=lookback_days)).isoformat()

    # Find scored rows already in ledger — keyed on (release, period, model)
    existing_scored_keys: set[tuple] = {
        (r["release"], r["period"], r.get("model"))
        for r in existing_ledger
        if r.get("row_type") == "scored"
    }

    # Actual-value cache: one lookup per (release, period)
    _actual_cache: dict[tuple[str, str], float | None] = {}

    def _get_actual(release_type: str, period_str: str, release_date_str: str) -> float | None:
        key = (release_type, period_str)
        if key not in _actual_cache:
            raw_print = _get_initial_print(root, release_type, period_str, release_date_str)
            if raw_print is None:
                _actual_cache[key] = None
            else:
                _actual_cache[key] = _compute_actual_from_print(release_type, raw_print, root, period_str)
        return _actual_cache[key]

    def _pick_t1_row(candidates: list[dict], release_date_str: str) -> tuple[dict | None, bool]:
        """MRI-R32b: pick the best frozen T-1 row.

        Preference order:
          1. Latest row with asof_night STRICTLY < release_date (true pre-release).
          2. If none, any row with asof_night == release_date (release-day row),
             stamped frozen_on_release_day=True.
        Returns (row | None, frozen_on_release_day: bool).
        """
        pre_release = [r for r in candidates if r.get("asof_night", "") < release_date_str]
        if pre_release:
            return max(pre_release, key=lambda r: r.get("asof_night", "")), False
        release_day = [r for r in candidates if r.get("asof_night", "") == release_date_str]
        if release_day:
            return max(release_day, key=lambda r: r.get("asof_night", "")), True
        return None, False

    def _score_champion(release_type: str, period_str: str, release_date_str: str,
                        actual: float, t1_proj: dict, frozen_on_release_day: bool,
                        is_late: bool) -> dict:
        """Build a scored row for champion (model=None)."""
        proj_point = t1_proj.get("projection_point")
        proj_p10 = t1_proj.get("projection_p10")
        proj_p25 = t1_proj.get("projection_p25")
        proj_p75 = t1_proj.get("projection_p75")
        proj_p90 = t1_proj.get("projection_p90")
        proj_mode = t1_proj.get("projection_mode")

        our_surprise = (
            round(actual - proj_point, 4)
            if (proj_point is not None and proj_mode != "benchmark_only")
            else None
        )

        bench_naive = t1_proj.get("benchmark_naive_prior")
        if release_type == "claims":
            bench_trailing = t1_proj.get("benchmark_trailing_4w")
        else:
            bench_trailing = t1_proj.get("benchmark_trailing_3m")
        bench_ar = t1_proj.get("benchmark_ar_model")
        bench_cleveland = t1_proj.get("benchmark_cleveland")

        def _sv(bench: float | None) -> float | None:
            return round(actual - bench, 4) if bench is not None else None

        interval_hit: bool | None = None
        if proj_mode != "benchmark_only" and proj_p10 is not None and proj_p90 is not None:
            interval_hit = bool(proj_p10 <= actual <= proj_p90)

        skew_hit: bool | None = None
        bench_vals = [v for v in [bench_naive, bench_trailing, bench_ar, bench_cleveland] if v is not None]
        if proj_mode != "benchmark_only" and bench_vals and proj_point is not None:
            bench_median = float(np.median(bench_vals))
            our_dir = "hotter" if proj_point > bench_median else ("cooler" if proj_point < bench_median else "inline")
            act_dir = "hotter" if actual > bench_median else ("cooler" if actual < bench_median else "inline")
            skew_hit = bool(our_dir == act_dir)

        expectation_hit: bool | None = None
        try:
            frozen_er = t1_proj.get("expectation_read")
            frozen_sigma = t1_proj.get("sigma_scale_pp")
            if (
                frozen_er is not None and isinstance(frozen_er, dict)
                and frozen_er.get("tag") is not None
                and frozen_sigma is not None and frozen_sigma > 0
            ):
                frozen_tag = frozen_er["tag"]
                frozen_median = frozen_er.get("expectation_median")
                if frozen_median is not None:
                    actual_std = (actual - float(frozen_median)) / float(frozen_sigma)
                    if actual_std > _EXPECTATION_BAND_THRESHOLD:
                        actual_tag = "above_expectations"
                    elif actual_std < -_EXPECTATION_BAND_THRESHOLD:
                        actual_tag = "below_expectations"
                    else:
                        actual_tag = "aligned"
                    expectation_hit = bool(frozen_tag == actual_tag)
        except Exception as exc:
            log.debug("expectation_hit failed for %s/%s: %s", release_type, period_str, exc)

        row: dict = {
            "schema": 2,
            "row_type": "scored",
            "model": None,
            "asof_night": asof_night,
            "release": release_type,
            "period": period_str,
            "release_date": release_date_str,
            "actual": actual,
            "actual_first": actual,
            "raw_initial_print": _actual_cache.get((release_type, period_str)),
            "frozen_asof_night": t1_proj.get("asof_night"),
            "frozen_projection_point": proj_point,
            "frozen_projection_p10": proj_p10,
            "frozen_projection_p25": proj_p25,
            "frozen_projection_p75": proj_p75,
            "frozen_projection_p90": proj_p90,
            "our_surprise": our_surprise,
            "surprise_vs_naive": _sv(bench_naive),
            "surprise_vs_trailing": _sv(bench_trailing),
            "surprise_vs_ar": _sv(bench_ar),
            "surprise_vs_cleveland": _sv(bench_cleveland),
            "interval_hit": interval_hit,
            "skew_hit": skew_hit,
            "projection_mode": proj_mode,
            "benchmark_trailing_key": "trailing_4w" if release_type == "claims" else "trailing_3m",
            "expectation_hit": expectation_hit,
            # MRI-R35: freeze cutoff_label from T-1 projection row
            "cutoff_label": t1_proj.get("cutoff_label"),
        }
        if frozen_on_release_day:
            row["frozen_on_release_day"] = True
            row["frozen_on_release_day_note"] = (
                "MRI-R32b: T-1 projection was from release day itself (asof_night == release_date); "
                "no strictly-pre-release projection found. Annotated but not dropped."
            )
        if is_late:
            row["late"] = True
            row["late_note"] = (
                "MRI-R32c: no pre-release projection existed; scored against a late back-projection."
            )
        return row

    # --- Collect all (release, period) pairs in the lookback window that need scoring ---
    # For each row_type (projection / shadow_projection) in the ledger, deduplicate
    # by (release, period) so we attempt scoring once per pair.
    seen_release_period_for_scoring: dict[tuple[str, str, str | None], str] = {}  # -> release_date
    for row in existing_ledger:
        rt_val = row.get("row_type")
        if rt_val not in ("projection", "shadow_projection"):
            continue
        release_type = row.get("release")
        period_str = row.get("period")
        release_date_str = row.get("release_date")
        model = row.get("model")  # None for champion, str for shadow

        if not release_type or not period_str or not release_date_str:
            continue
        # Lookback gate
        if release_date_str < lookback_cutoff:
            continue

        key = (release_type, period_str, model)
        if key not in seen_release_period_for_scoring:
            seen_release_period_for_scoring[key] = release_date_str

    for (release_type, period_str, model_key), release_date_str in seen_release_period_for_scoring.items():
        # Already scored?
        if (release_type, period_str, model_key) in existing_scored_keys:
            continue

        # Release date must have passed
        try:
            release_date = date.fromisoformat(release_date_str)
        except ValueError:
            continue
        if today < release_date:
            continue

        # Get actual value
        actual = _get_actual(release_type, period_str, release_date_str)
        if actual is None:
            log.debug("catch-up: no actual for %s/%s (model=%s) as of %s",
                      release_type, period_str, model_key, asof_night)
            continue

        if model_key is None:
            # --- Champion scoring ---
            all_proj = [
                r for r in existing_ledger
                if r.get("row_type") == "projection"
                and r.get("release") == release_type
                and r.get("period") == period_str
                and r.get("asof_night", "") <= release_date_str  # MRI-R32b: <= not <
            ]
            if not all_proj:
                log.debug("catch-up: no projection candidates for %s/%s", release_type, period_str)
                continue

            t1_proj, frozen_on_rd = _pick_t1_row(all_proj, release_date_str)
            if t1_proj is None:
                log.debug("catch-up: no T-1 row for %s/%s", release_type, period_str)
                continue

            # MRI-R32c: late back-projection only when the selected T-1 row's asof_night
            # is STRICTLY AFTER the release_date (projection was created post-print).
            # Release-day rows (asof_night == release_date) are genuinely pre-print:
            # the nightly runs 02:00 UTC (~10h before the 08:30 ET print), so they
            # are NOT marked late — just annotated frozen_on_release_day by _pick_t1_row.
            is_late = t1_proj.get("asof_night", "") > release_date_str

            sr = _score_champion(release_type, period_str, release_date_str, actual,
                                 t1_proj, frozen_on_rd, is_late)
            scored_rows.append(sr)
            log.info(
                "catch-up scored: %s/%s — actual=%.4f vs proj=%.4f%s%s",
                release_type, period_str, actual,
                t1_proj.get("projection_point") or float("nan"),
                " [frozen_on_release_day]" if frozen_on_rd else "",
                " [late]" if is_late else "",
            )

        else:
            # --- Shadow scoring ---
            shadow_model = model_key
            all_shadow = [
                r for r in existing_ledger
                if r.get("row_type") == "shadow_projection"
                and r.get("model") == shadow_model
                and r.get("release") == release_type
                and r.get("period") == period_str
                and r.get("asof_night", "") <= release_date_str
            ]
            if not all_shadow:
                log.debug("catch-up: no shadow (%s) candidates for %s/%s",
                          shadow_model, release_type, period_str)
                continue

            t1_shadow, frozen_on_rd = _pick_t1_row(all_shadow, release_date_str)
            if t1_shadow is None:
                continue

            shadow_point = t1_shadow.get("projection_point")
            shadow_p10 = t1_shadow.get("projection_p10")
            shadow_p25 = t1_shadow.get("projection_p25")
            shadow_p75 = t1_shadow.get("projection_p75")
            shadow_p90 = t1_shadow.get("projection_p90")

            shadow_surprise = round(actual - shadow_point, 4) if shadow_point is not None else None
            shadow_interval_hit: bool | None = None
            if shadow_p10 is not None and shadow_p90 is not None:
                shadow_interval_hit = bool(shadow_p10 <= actual <= shadow_p90)

            scored_shadow_row: dict = {
                "schema": 2,
                "row_type": "scored",
                "model": shadow_model,
                "asof_night": asof_night,
                "release": release_type,
                "period": period_str,
                "release_date": release_date_str,
                "actual": actual,
                "actual_first": actual,
                "frozen_asof_night": t1_shadow.get("asof_night"),
                "frozen_projection_point": shadow_point,
                "frozen_projection_p10": shadow_p10,
                "frozen_projection_p25": shadow_p25,
                "frozen_projection_p75": shadow_p75,
                "frozen_projection_p90": shadow_p90,
                "our_surprise": shadow_surprise,
                "interval_hit": shadow_interval_hit,
                # MRI-R35: freeze cutoff_label from shadow row
                "cutoff_label": t1_shadow.get("cutoff_label"),
            }
            if frozen_on_rd:
                scored_shadow_row["frozen_on_release_day"] = True

            # Block-level scoring for cpi_bridge rows (display-tier context-accrual).
            # Fail-open: a block-scoring failure must never prevent the scored row.
            if shadow_model == "cpi_bridge" and t1_shadow.get("components"):
                try:
                    from engine.release_block_scoring import score_bridge_blocks
                    block_scores = score_bridge_blocks(
                        root=root,
                        components=t1_shadow["components"],
                        period=period_str,
                        asof=today,
                    )
                    if block_scores:
                        scored_shadow_row["block_scores"] = block_scores
                except Exception as _bse:
                    log.warning(
                        "block_scoring failed for cpi_bridge %s/%s — skipping block_scores: %s",
                        release_type, period_str, _bse,
                    )

            scored_rows.append(scored_shadow_row)
            log.info(
                "catch-up scored shadow (%s): %s/%s — actual=%.4f vs shadow_proj=%.4f",
                shadow_model, release_type, period_str, actual, shadow_point or float("nan"),
            )

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

def _load_defect_notices(root: Path | None) -> list[dict]:
    """Load defect_notices.json if present; fail-open (returns []) on missing/corrupt."""
    if root is None:
        return []
    notices_path = root / "data" / "release_forecast" / "defect_notices.json"
    try:
        if not notices_path.exists():
            return []
        with open(notices_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("notices", [])
    except Exception as e:
        log.debug("defect_notices.json load failed (fail-open): %s", e)
        return []


def _build_scoreboard(
    ledger: list[dict],
    accrual_start: str,
    root: Path | None = None,
) -> dict:
    """Recompute scoreboard from scored ledger rows only. Forward-only.

    accrual_start: ISO date string of when forward accrual began.
    Schema v2 adds: interval_50_coverage (p25-p75 band hits), mae_vs_actual_latest
    (from revision rows where present), reaction summary (mean |dgs10_h0_bp|
    for hot/cold rows when n>=3, else null).

    Round-2b: shadow scored rows (model!=None) are grouped in a separate
    by_shadow section keyed by (release, model). Champion (model=None) rows
    remain in by_release as before.
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

    def _new_agg() -> dict:
        return {
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
            "expectation_hits": [],    # MRI-R22: expectation_read hit/miss
            # MRI-R31: pinball loss accumulators per quantile (p10,p25,p50,p75,p90)
            "pinball_p10": [], "pinball_p25": [], "pinball_p50": [],
            "pinball_p75": [], "pinball_p90": [],
            # MRI-R35: per-cutoff_label accumulators (sub-agg, not output directly)
            "_by_cutoff": {},
        }

    # Per release-type aggregation (champion rows, model=None)
    per_release: dict[str, dict] = {}
    # Per (release, model) aggregation (shadow rows, model!=None)
    per_shadow: dict[tuple[str, str], dict] = {}

    for row in scored:
        rt = row.get("release", "unknown")
        model = row.get("model")  # None for champion, "v3_factor"/"cpi_bridge" for shadows

        if model is None:
            # Champion row
            if rt not in per_release:
                per_release[rt] = _new_agg()
            g = per_release[rt]
        else:
            # Shadow row
            shadow_key = (rt, model)
            if shadow_key not in per_shadow:
                per_shadow[shadow_key] = _new_agg()
            g = per_shadow[shadow_key]

        g["n"] += 1

        actual = row.get("actual")
        proj = row.get("frozen_projection_point")

        if actual is not None and proj is not None:
            g["our_abs_errors"].append(abs(actual - proj))

        # Champion-only fields (bench surprises, skew, expectation) — shadows won't have these
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

        # MRI-R22: expectation_hit accumulation
        eh = row.get("expectation_hit")
        if eh is not None:
            g["expectation_hits"].append(bool(eh))

        # MRI-R31: pinball loss per quantile — L_q(y, q) = (y-q)*(alpha - 1{y<q})
        # where alpha is the quantile level. Sum over 5 quantiles = pinball loss.
        if actual is not None:
            _pb_vals = {
                "pinball_p10": (row.get("frozen_projection_p10"), 0.10),
                "pinball_p25": (row.get("frozen_projection_p25"), 0.25),
                "pinball_p50": (row.get("frozen_projection_point"), 0.50),  # p50 ≈ point
                "pinball_p75": (row.get("frozen_projection_p75"), 0.75),
                "pinball_p90": (row.get("frozen_projection_p90"), 0.90),
            }
            for pb_key, (q_val, alpha) in _pb_vals.items():
                if q_val is not None:
                    err = float(actual) - float(q_val)
                    pb = err * alpha if err >= 0 else err * (alpha - 1.0)
                    g[pb_key].append(pb)

        # mae_vs_actual_latest: use revision data if available
        rev_key = (rt, row.get("period", ""))
        actual_latest = revision_latest.get(rev_key)
        if actual_latest is not None and proj is not None:
            g["revision_errors"].append(abs(actual_latest - proj))

        # Reaction summary (champion only; shadow rows unlikely to have reaction data)
        if model is None:
            react = reaction_by_key.get(rev_key)
            if react is not None:
                bench_naive = row.get("benchmark_naive_prior")
                is_hot_or_cold = (
                    actual is not None and bench_naive is not None
                    and abs(actual - bench_naive) > 0
                )
                if is_hot_or_cold:
                    dgs_h0 = react.get("dgs10_h0_bp")
                    if dgs_h0 is not None:
                        g["reaction_dgs10_h0_abs"].append(abs(dgs_h0))

        # MRI-R35: per-(release, model, cutoff_label) split — accumulate into sub-agg.
        # Only n/MAE/pinball tracked per cutoff (lighter than full replication).
        cutoff_label = row.get("cutoff_label")
        if cutoff_label is not None:
            if cutoff_label not in g["_by_cutoff"]:
                g["_by_cutoff"][cutoff_label] = {
                    "n": 0,
                    "our_abs_errors": [],
                    "pinball_p10": [], "pinball_p25": [], "pinball_p50": [],
                    "pinball_p75": [], "pinball_p90": [],
                }
            cg = g["_by_cutoff"][cutoff_label]
            cg["n"] += 1
            if actual is not None and proj is not None:
                cg["our_abs_errors"].append(abs(actual - proj))
            # Pinball per cutoff
            if actual is not None:
                _pb_cut = {
                    "pinball_p10": (row.get("frozen_projection_p10"), 0.10),
                    "pinball_p25": (row.get("frozen_projection_p25"), 0.25),
                    "pinball_p50": (row.get("frozen_projection_point"), 0.50),
                    "pinball_p75": (row.get("frozen_projection_p75"), 0.75),
                    "pinball_p90": (row.get("frozen_projection_p90"), 0.90),
                }
                for pb_key, (q_val, alpha) in _pb_cut.items():
                    if q_val is not None:
                        err = float(actual) - float(q_val)
                        pb = err * alpha if err >= 0 else err * (alpha - 1.0)
                        cg[pb_key].append(pb)

    def _agg_to_stats(rt: str, g: dict, model_label: str | None = None) -> dict:
        """Convert accumulator to scoreboard stats entry."""
        n = g["n"]
        k_interval = sum(g["interval_hits"])
        n_interval = len(g["interval_hits"])
        k_interval_50 = sum(g["interval_50_hits"])
        n_interval_50 = len(g["interval_50_hits"])
        k_skew = sum(g["skew_hits"])
        n_skew = len(g["skew_hits"])
        k_exp = sum(g["expectation_hits"])
        n_exp = len(g["expectation_hits"])

        def _mae(errs: list[float]) -> float | None:
            return round(float(np.mean(errs)), 4) if errs else None

        reaction_dgs10_mean_abs = None
        if len(g["reaction_dgs10_h0_abs"]) >= 3:
            reaction_dgs10_mean_abs = round(float(np.mean(g["reaction_dgs10_h0_abs"])), 2)

        trailing_label = "mae_trailing_4w" if rt == "claims" else "mae_trailing_3m"
        _entry: dict = {
            "n": n,
            "model": model_label,
            "mae_ours": _mae(g["our_abs_errors"]),
            "mae_naive_prior": _mae(g["naive_abs_errors"]),
            trailing_label: _mae(g["trailing_abs_errors"]),
            "mae_ar_model": _mae(g["ar_abs_errors"]),
            "mae_cleveland": _mae(g["cleveland_abs_errors"]),
            # Schema v2 additions
            "mae_vs_actual_latest": _mae(g["revision_errors"]),
            "p10_p90_coverage": round(k_interval / n_interval, 4) if n_interval > 0 else None,
            "p10_p90_coverage_n": n_interval,
            "interval_50_coverage": round(k_interval_50 / n_interval_50, 4) if n_interval_50 > 0 else None,
            "interval_50_coverage_n": n_interval_50,
            "interval_50_coverage_note": "p25-p75 band; approximates Codex 60% interval (MRI-R13)",
            "skew_hit_rate": round(k_skew / n_skew, 4) if n_skew > 0 else None,
            "skew_hit_rate_n": n_skew,
            "skew_hit_rate_wilson_ci": _wilson(k_skew, n_skew),
            "reaction_mean_abs_dgs10_h0_bp": reaction_dgs10_mean_abs,
            "reaction_n": len(g["reaction_dgs10_h0_abs"]),
            "expectation_read_hit_rate": round(k_exp / n_exp, 4) if n_exp > 0 else None,
            "expectation_read_hit_rate_n": n_exp,
            "expectation_read_hit_rate_note": (
                "Fraction of prints where actual fell in the same band as frozen expectation_read tag "
                "(above_expectations / below_expectations / aligned, ±0.35·σ_scale). "
                "Display-only (MRI-R22). Null until data accrues."
            ),
            # MRI-R31: pinball loss (5-quantile sum), reported-only
            "pinball_loss_5q": (
                round(
                    sum(
                        float(np.mean(g[k])) for k in (
                            "pinball_p10", "pinball_p25", "pinball_p50",
                            "pinball_p75", "pinball_p90"
                        )
                        if g[k]
                    ),
                    4,
                )
                if any(g[k] for k in ("pinball_p10", "pinball_p25", "pinball_p50",
                                      "pinball_p75", "pinball_p90"))
                else None
            ),
            "pinball_loss_5q_n": min(
                (len(g[k]) for k in ("pinball_p10", "pinball_p25", "pinball_p50",
                                     "pinball_p75", "pinball_p90") if g[k]),
                default=0,
            ),
            "pinball_loss_5q_note": (
                "MRI-R31: 5-quantile pinball loss sum (p10+p25+p50+p75+p90 mean losses). "
                "Reported-only; lower is better. Skew display marked descriptive_until_n24."
            ),
        }
        if rt == "claims" and model_label is None:
            _entry["block_note"] = (
                "MRI-R9: weekly claims residuals have strong autocorrelation. "
                "Reported MAE and coverage are computed on individual weekly prints; "
                "effective sample size is smaller than n due to serial correlation. "
                "Era-split results in research/release_forecast/CLAIMS_BACKTEST.md are "
                "the authoritative reference."
            )

        # MRI-R35: by_cutoff sub-map {cutoff_label: {n, mae_ours, pinball_loss_5q}}
        # Backward-compatible: totals above are unchanged; by_cutoff is additive.
        by_cutoff: dict[str, dict] = {}
        for cl, cg in (g.get("_by_cutoff") or {}).items():
            def _pb5(cg: dict) -> float | None:
                _pb_keys = ("pinball_p10", "pinball_p25", "pinball_p50", "pinball_p75", "pinball_p90")
                if not any(cg.get(k) for k in _pb_keys):
                    return None
                return round(
                    sum(
                        float(np.mean(cg[k])) for k in _pb_keys if cg.get(k)
                    ),
                    4,
                )
            by_cutoff[cl] = {
                "n": cg["n"],
                "mae_ours": _mae(cg["our_abs_errors"]),
                "pinball_loss_5q": _pb5(cg),
            }
        _entry["by_cutoff"] = by_cutoff

        return _entry

    release_stats: dict[str, dict] = {}
    for rt, g in per_release.items():
        release_stats[rt] = _agg_to_stats(rt, g, model_label=None)

    # Shadow scoreboard: keyed as "<release>:<model>"
    shadow_stats: dict[str, dict] = {}
    for (rt, mdl), g in per_shadow.items():
        shadow_stats[f"{rt}:{mdl}"] = _agg_to_stats(rt, g, model_label=mdl)

    # MRI-R40 §5: promotion_review entries — annotation only, no metric changes.
    # At n >= 12 scored combined_v1 prints AND any single input's forward MAE < combined's:
    # emit an entry naming the input. Pure adjudication trigger.
    promotion_review: list[dict] = []
    for (rt, mdl), g in per_shadow.items():
        if mdl != "combined_v1":
            continue
        combined_mae = (_agg_to_stats(rt, g, model_label=mdl).get("mae_ours"))
        combined_n = g["n"]
        if combined_n < 12 or combined_mae is None:
            continue
        # Compare against each candidate input's MAE from shadow scoreboard.
        # "cleveland" has no shadow scoreboard entry — compute its standalone forward
        # MAE from champion scored rows' surprise_vs_cleveland field (same source as
        # extract_scored_errors uses), requiring n>=12 cleveland rows per prereg §5.
        candidate_models = ["champion", "v3_factor", "cpi_bridge", "mf_energy", "cleveland"]
        for cand_model in candidate_models:
            if cand_model == "champion":
                # Champion MAE from champion scoreboard
                cand_stats = release_stats.get(rt)
                cand_mae = cand_stats.get("mae_ours") if cand_stats else None
                cand_n = cand_stats.get("n") if cand_stats else 0
            elif cand_model == "cleveland":
                # Cleveland has no shadow projection track — compute directly from
                # champion rows' cleveland_abs_errors (surprise_vs_cleveland field).
                cle_errs = (per_release.get(rt) or {}).get("cleveland_abs_errors", [])
                cand_n = len(cle_errs)
                cand_mae = float(sum(cle_errs) / cand_n) if cand_n >= 12 else None
            else:
                cand_key = (rt, cand_model)
                cand_g = per_shadow.get(cand_key)
                if cand_g is None:
                    continue
                cand_s = _agg_to_stats(rt, cand_g, model_label=cand_model)
                cand_mae = cand_s.get("mae_ours")
                cand_n = cand_g["n"]
            if cand_mae is not None and cand_mae < combined_mae:
                promotion_review.append({
                    "release": rt,
                    "input": cand_model,
                    "mae_input": round(cand_mae, 4),
                    "mae_combined": round(combined_mae, 4),
                    "n_combined": combined_n,
                    "n_input": cand_n,
                    "note": (
                        "MRI-R40 §5: input MAE < combined MAE at n>=12. "
                        "Mandatory adjudication trigger — no automatic change."
                    ),
                })

    # FIX 5: load defect_notices.json and pass through as annotation (no metric change)
    defect_notices = _load_defect_notices(root)

    # Block scoreboard: per-block forward MAE/bias for cpi_bridge rows.
    # Display-tier context-accrual (see engine/release_block_scoring.py).
    # Will be empty until the first cpi_bridge row scores. Fail-open.
    block_scoreboard: dict = {}
    try:
        from engine.release_block_scoring import aggregate_block_scoreboard
        cpi_bridge_scored = [
            r for r in scored
            if r.get("model") == "cpi_bridge" and r.get("block_scores")
        ]
        if cpi_bridge_scored:
            block_scoreboard = aggregate_block_scoreboard(cpi_bridge_scored)
    except Exception as _bsb_e:
        log.warning("block_scoreboard aggregation failed (fail-open): %s", _bsb_e)

    return {
        "schema": "release_forecast_scoreboard.v2",
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "forward_accrual_began": accrual_start,
        "note": "Forward-only: no backtest rows enter this scoreboard (MRI-R8).",
        "by_release": release_stats,
        "by_shadow": shadow_stats,  # Round-2b: per-(release, model) shadow track records
        "promotion_review": promotion_review,  # MRI-R40 §5: annotation, no metric changes
        "defect_notices": defect_notices,  # annotation only; no metric computation changed
        "block_scoreboard": block_scoreboard,  # per-block cpi_bridge MAE/bias (display-tier accrual)
    }


# ---------------------------------------------------------------------------
# 8d. PR-I enrichments (MRI-R15 / MRI-R16 / MRI-R17)
# ---------------------------------------------------------------------------

def _benchmark_median(benchmark_set: dict) -> float | None:
    """Compute median across available benchmark values for the surprise-distribution band."""
    vals = [
        v for v in [
            benchmark_set.get("naive_prior"),
            benchmark_set.get("trailing_3m"),
            benchmark_set.get("ar_model"),
            benchmark_set.get("cleveland_nowcast"),
        ]
        if v is not None and math.isfinite(float(v))
    ]
    if not vals:
        return None
    return float(np.median(vals))


def _enrich_upcoming_block(upcoming_block: list[dict], root: Path) -> None:
    """Attach PR-I enrichment fields to each upcoming entry in-place. Fail-open."""
    try:
        from engine.release_market_context import (
            compute_surprise_distribution,
            compute_expectation_read,
            get_kalshi_implied,
            get_market_implied_benchmark,
            get_reaction_sensitivity,
        )
    except Exception as exc:
        log.warning("release_market_context import failed — enrichments skipped: %s", exc)
        return

    try:
        from engine.release_quirks import compute_quirk_flags as _cqf_raw
        # W11-G: wrap so root is always passed (CRITICAL SIGNATURE FIX — MRI-R38c).
        # The new Track S flags (active_strike, nfp_preliminary_benchmark, etc.)
        # read data/ calendars + work-stoppages parquet.  Without root they SILENTLY
        # use _repo_root() which may differ from our runtime root; with root they
        # always read from the correct tree.
        import functools as _ft
        _compute_quirk_flags = _ft.partial(_cqf_raw, root=root)
    except Exception as exc:  # pragma: no cover
        log.warning("release_quirks import failed — quirk_flags enrichment skipped: %s", exc)
        _compute_quirk_flags = None

    snapshots_path = root / "data" / "prediction_markets" / "snapshots.parquet"
    kalshi_path = snapshots_path.parent / "kalshi_releases.parquet"
    playbook_path = root / "research" / "release_playbook" / "results" / "playbook_v1.json"

    # Read current regime label (for reaction sensitivity regime preference)
    current_regime: str | None = None
    try:
        regime_path = root / "data" / "regime" / "latest.json"
        if regime_path.exists():
            with open(regime_path, encoding="utf-8") as fh:
                regime_data = json.load(fh)
            current_regime = regime_data.get("quad") or regime_data.get("label") or None
    except Exception as exc:
        log.debug("regime read for enrichment failed: %s", exc)

    for item in upcoming_block:
        rt = item.get("release_type", "")
        proj = item.get("projection", {})
        skew = item.get("surprise_skew", {})
        bench = item.get("benchmark_set", {})

        # MRI-R15: surprise_distribution
        try:
            # sigma_scale_pp is the pp-scale std the CDF integrates over;
            # skew["sigma"] is the standardized POSITION, not the scale.
            sigma = skew.get("sigma_scale_pp") if skew else None
            bench_med = _benchmark_median(bench) if bench else None
            if sigma and bench_med is not None:
                item["surprise_distribution"] = compute_surprise_distribution(
                    proj, bench_med, sigma
                )
            else:
                item["surprise_distribution"] = None
        except Exception as exc:
            log.debug("surprise_distribution enrichment failed for %s: %s", rt, exc)
            item["surprise_distribution"] = None

        # MRI-R16: market_implied — Kalshi release ladder preferred (implied_median,
        # per masterplan §9.1), Polymarket event match as fallback.
        try:
            release_date_str = item.get("release_date")
            mi = get_kalshi_implied(rt, item.get("period"), kalshi_path)
            if mi is None:
                mi = get_market_implied_benchmark(rt, release_date_str, snapshots_path)
            # Attach to benchmark_set.market_implied (context only, never model math)
            if bench is not None:
                bench["market_implied"] = mi
            item["market_implied"] = mi  # also at top level for UI discovery
        except Exception as exc:
            log.debug("market_implied enrichment failed for %s: %s", rt, exc)
            if bench is not None:
                bench["market_implied"] = None
            item["market_implied"] = None

        # MRI-R22: expectation_read — our point vs EXPECTATION SET median
        # Expectation set: cleveland_nowcast + kalshi implied_median (preferred)
        # or polymarket numeric implied (fallback). Trend benchmarks are EXCLUDED.
        # Reuse already-fetched market_implied (mi) and Cleveland value from bench.
        try:
            proj_point = (item.get("projection") or {}).get("point")
            sigma_scale = (item.get("surprise_skew") or {}).get("sigma_scale_pp")

            # Build expectation_values from sources already attached this pass
            _exp_vals: dict[str, float | None] = {}

            # Cleveland (from benchmark_set — already enriched above)
            _cleveland = (bench or {}).get("cleveland_nowcast")
            if _cleveland is not None:
                _exp_vals["cleveland_nowcast"] = _cleveland

            # Market-implied: prefer Kalshi implied_median, fallback Polymarket numeric
            # mi was set in the MRI-R16 block above (either Kalshi or Polymarket result)
            _mi = item.get("market_implied")
            if _mi is not None:
                # Kalshi result carries 'implied_median' (numeric); Polymarket carries
                # 'implied' as an outcome string (not necessarily numeric — skip if str).
                _kalshi_med = _mi.get("implied_median") if _mi.get("source") == "kalshi" else None
                _poly_implied = _mi.get("implied") if _mi.get("source") != "kalshi" else None
                if _kalshi_med is not None:
                    try:
                        _exp_vals["kalshi"] = float(_kalshi_med)
                    except (TypeError, ValueError):
                        pass
                elif _poly_implied is not None:
                    try:
                        _exp_vals["polymarket"] = float(_poly_implied)
                    except (TypeError, ValueError):
                        pass  # Polymarket outcome strings are non-numeric; skip

            item["expectation_read"] = compute_expectation_read(
                proj_point, _exp_vals, sigma_scale
            )
        except Exception as exc:
            log.debug("expectation_read enrichment failed for %s: %s", rt, exc)
            item["expectation_read"] = None

        # MRI-R17: reaction_sensitivity
        try:
            item["reaction_sensitivity"] = get_reaction_sensitivity(
                rt, playbook_path, current_regime
            )
        except Exception as exc:
            log.debug("reaction_sensitivity enrichment failed for %s: %s", rt, exc)
            item["reaction_sensitivity"] = None

        # MRI-R20: quirk_flags — deterministic calendar annotations (pure display)
        try:
            if _compute_quirk_flags is not None:
                period_str = item.get("period") or ""
                item["quirk_flags"] = _compute_quirk_flags(rt, period_str)
            else:
                item["quirk_flags"] = []
        except Exception as exc:
            log.debug("quirk_flags enrichment failed for %s: %s", rt, exc)
            item["quirk_flags"] = []


# ---------------------------------------------------------------------------
# 8e-W11G. Print-integrity chip + NFP revision context (W11-G tasks 3 & 4)
# ---------------------------------------------------------------------------

def _attach_integrity_and_revision_context(
    upcoming_block: list[dict],
    root: Path,
    today: date,
) -> None:
    """W11-G tasks 3 & 4: attach print_integrity and (for nfp) revision_context.

    Task 3 — print-integrity chip (MRI-R38c):
      Call engine.release_integrity.compute_print_integrity per release family.
      Attach item["print_integrity"] = {regime, collection_rate_vs_5y,
      cpi_median_se_trend, revision_streak}.  Also freeze regime on the
      projection ledger (via item["print_integrity_regime"]).
      Fail-open when the integrity parquet is absent.

    Task 4 — NFP revision context (MRI-R37 descriptive remainder):
      For nfp release_type only: attach item["revision_context"] = the
      DESCRIPTIVE level-bias annotation from compute_revision_context()
      PLUS a model_status line {track_r: 'killed_attempt_1', lean_display: false}
      for honesty.  No lean direction is attached.
      Fail-open.

    AUTHORITY CONTRACT:
      - print_integrity values are DISPLAY-ONLY METADATA.
      - revision_context is DESCRIPTIVE only; no lean, no scoring.
      - Nothing in this function reads these values back into projections.
    """
    try:
        from engine.release_integrity import compute_print_integrity
    except Exception as exc:
        log.warning("release_integrity import failed — print_integrity enrichment skipped: %s", exc)
        compute_print_integrity = None  # type: ignore[assignment]

    try:
        from engine.release_revision_model import compute_revision_context
    except Exception as exc:
        log.warning("release_revision_model import failed — revision_context enrichment skipped: %s", exc)
        compute_revision_context = None  # type: ignore[assignment]

    for item in upcoming_block:
        rt = item.get("release_type", "")

        # --- Task 3: print-integrity chip ---
        if compute_print_integrity is not None:
            try:
                integrity = compute_print_integrity(
                    release_type=rt,
                    as_of=today,
                    root=root,
                )
                item["print_integrity"] = {
                    "regime": integrity.get("regime"),
                    "collection_rate_vs_5y": integrity.get("collection_rate_vs_5y"),
                    "cpi_median_se_trend": integrity.get("cpi_median_se_trend"),
                    "revision_streak": integrity.get("revision_streak"),
                    "source_years": integrity.get("source_years"),
                    "as_of": integrity.get("as_of"),
                    "display_only": True,
                    "authority": False,
                }
                # Freeze regime for ledger (read back from integrity dict)
                item["print_integrity_regime"] = integrity.get("regime")
            except Exception as exc:
                log.debug("print_integrity enrichment failed for %s: %s", rt, exc)
                item["print_integrity"] = None
                item["print_integrity_regime"] = None
        else:
            item["print_integrity"] = None
            item["print_integrity_regime"] = None

        # --- Task 4: NFP revision context (descriptive, no lean) ---
        if rt == "nfp":
            if compute_revision_context is not None:
                try:
                    ctx = compute_revision_context()
                    # Attach descriptive level-bias annotation
                    item["revision_context"] = {
                        **ctx,
                        # model_status block (honesty: Track R KILLED attempt 1 per §12.3)
                        "model_status": {
                            "track_r": "killed_attempt_1",
                            "lean_display": False,
                            "note": (
                                "Track R revision-direction model (MRI-R37): kill rule triggered "
                                "(Wilson LB <= majority-class base rate in walk-forward). "
                                "No lean direction is displayed. "
                                "Descriptive level-bias annotation is display-only (MRI-R37)."
                            ),
                        },
                        "display_only": True,
                        "authority": False,
                    }
                except Exception as exc:
                    log.debug("revision_context enrichment failed for nfp: %s", exc)
                    item["revision_context"] = None
            else:
                item["revision_context"] = None


# ---------------------------------------------------------------------------
# 8e. Capture health (MRI-R32e)
# ---------------------------------------------------------------------------

def _compute_capture_health(
    today: date,
    root: Path,
    existing_ledger: list[dict],
    lookback_days: int = 120,
) -> dict:
    """MRI-R32e: compute capture_health block for latest.json.

    Reports:
      - last_nightly_asof: most recent asof_night in ledger
      - nightly_gap_days: how many calendar days since the last nightly run
      - past_due_unscored: list of {release, period, release_date, reason}
          where reason in: missing_vintage / no_t1_projection / api_key_absent
      - enricher_staleness: per-enricher last-known asof (from existing rows)

    Fail-open: any error → partial dict with available fields.
    """
    import os as _os
    health: dict = {
        "asof": today.isoformat(),
        "last_nightly_asof": None,
        "nightly_gap_days": None,
        "past_due_unscored": [],
        "enricher_staleness": {},
    }

    # Last nightly asof from any row in ledger
    all_asofs = [r.get("asof_night", "") for r in existing_ledger if r.get("asof_night")]
    if all_asofs:
        last_asof = max(all_asofs)
        health["last_nightly_asof"] = last_asof
        try:
            gap = (today - date.fromisoformat(last_asof)).days
            health["nightly_gap_days"] = gap
        except Exception:
            pass

    # FRED API key presence
    has_fred_key = bool(_os.environ.get("FRED_API_KEY", "").strip())

    # Already scored keys
    scored_keys: set[tuple] = {
        (r["release"], r["period"], r.get("model"))
        for r in existing_ledger
        if r.get("row_type") == "scored"
    }

    # Past-due unscored: projection/shadow_projection rows where release_date has passed
    lookback_cutoff = (today - timedelta(days=lookback_days)).isoformat()
    seen: set[tuple] = set()  # (release, period, model)

    for row in existing_ledger:
        if row.get("row_type") not in ("projection", "shadow_projection"):
            continue
        release_type = row.get("release") or ""
        period_str = row.get("period") or ""
        release_date_str = row.get("release_date") or ""
        model = row.get("model")  # None or str

        if not release_type or not period_str or not release_date_str:
            continue
        if release_date_str < lookback_cutoff:
            continue

        try:
            release_date = date.fromisoformat(release_date_str)
        except ValueError:
            continue
        if today < release_date:
            continue  # not yet released

        key = (release_type, period_str, model)
        if key in scored_keys or key in seen:
            continue
        seen.add(key)

        # Diagnose why it is unscored
        if not has_fred_key:
            reason = "api_key_absent"
        elif _get_initial_print(root, release_type, period_str, release_date_str) is None:
            reason = "missing_vintage"
        else:
            # Check if there is any T-1 candidate
            pre_rows = [
                r for r in existing_ledger
                if r.get("row_type") in ("projection", "shadow_projection")
                and r.get("model") == model
                and r.get("release") == release_type
                and r.get("period") == period_str
                and r.get("asof_night", "") <= release_date_str
            ]
            reason = "no_t1_projection" if not pre_rows else "unknown"

        health["past_due_unscored"].append({
            "release": release_type,
            "period": period_str,
            "release_date": release_date_str,
            "model": model,
            "reason": reason,
        })

    health["past_due_unscored_count"] = len(health["past_due_unscored"])

    # Enricher staleness: check Kalshi snapshot and Cleveland nowcast asof
    try:
        kalshi_path = root / "data" / "prediction_markets" / "kalshi_releases.parquet"
        if kalshi_path.exists():
            import stat as _stat
            mtime = kalshi_path.stat().st_mtime
            health["enricher_staleness"]["kalshi_releases_mtime"] = datetime.fromtimestamp(
                mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    try:
        cleveland_path = root / "data" / "cleveland_nowcast" / "nowcast.parquet"
        if cleveland_path.exists():
            import stat as _stat
            mtime = cleveland_path.stat().st_mtime
            health["enricher_staleness"]["cleveland_nowcast_mtime"] = datetime.fromtimestamp(
                mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    # W11-G task 5: extend enricher staleness with new W11-E sources
    try:
        ws_path = root / "data" / "bls_work_stoppages" / "stoppages.parquet"
        if ws_path.exists():
            mtime = ws_path.stat().st_mtime
            health["enricher_staleness"]["work_stoppages_mtime"] = datetime.fromtimestamp(
                mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            health["enricher_staleness"]["work_stoppages_mtime"] = None
    except Exception:
        pass

    try:
        integrity_path = root / "data" / "bls_print_integrity" / "integrity.parquet"
        if integrity_path.exists():
            mtime = integrity_path.stat().st_mtime
            health["enricher_staleness"]["print_integrity_mtime"] = datetime.fromtimestamp(
                mtime, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            health["enricher_staleness"]["print_integrity_mtime"] = None
    except Exception:
        pass

    return health


# ---------------------------------------------------------------------------
# 8f. Input-snapshot GC (MRI-R33 SNAPSHOT-GC-1)
# ---------------------------------------------------------------------------

def _run_snapshot_gc(snapshots_dir: Path, existing_ledger: list[dict], today: date) -> int:
    """MRI-R33 SNAPSHOT-GC-1: GC input_snapshots older than 30 days.

    Keep permanently: frozen T-1 receipts per (release, period).
      These are snapshots referenced by the latest strictly-pre-release projection
      row per (release, period) — they are permanent witnesses.
    Delete: all other snapshots older than 30d.

    Returns number of files deleted.
    """
    if not snapshots_dir.exists():
        return 0

    cutoff_date = today - timedelta(days=30)

    # Build set of permanently-kept snapshot refs:
    # For each (release, period), the latest asof_night < release_date projection row's
    # input_snapshot_ref is permanent.
    permanent_refs: set[str] = set()
    by_release_period: dict[tuple[str, str], list[dict]] = {}
    for row in existing_ledger:
        if row.get("row_type") != "projection":
            continue
        release_type = row.get("release") or ""
        period_str = row.get("period") or ""
        release_date_str = row.get("release_date") or ""
        asof_night = row.get("asof_night") or ""

        if not release_type or not period_str or not release_date_str:
            continue
        if asof_night >= release_date_str:
            continue  # not a pre-release row

        key = (release_type, period_str)
        by_release_period.setdefault(key, []).append(row)

    for key, rows in by_release_period.items():
        latest_pre = max(rows, key=lambda r: r.get("asof_night", ""))
        ref = latest_pre.get("input_snapshot_ref")
        if ref:
            # ref is a relative path string; extract basename for matching
            import os.path as _osp
            permanent_refs.add(_osp.basename(ref))

    deleted = 0
    try:
        for snap_file in snapshots_dir.glob("*.json"):
            # Keep permanently-protected files
            if snap_file.name in permanent_refs:
                continue
            # GC files older than 30 days
            try:
                mtime_date = date.fromtimestamp(snap_file.stat().st_mtime)
                if mtime_date < cutoff_date:
                    snap_file.unlink()
                    deleted += 1
            except Exception as exc_inner:
                log.debug("snapshot GC: failed to delete %s: %s", snap_file.name, exc_inner)
    except Exception as exc:
        log.debug("snapshot GC scan failed: %s", exc)

    if deleted:
        log.info("snapshot GC: deleted %d snapshots older than 30d", deleted)
    return deleted


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

    # 3a. PR-I enrichments — fail-open per field; any exception → null + log
    _enrich_upcoming_block(upcoming_block, root)

    # 3a-W11G. Print-integrity chip (MRI-R38c) + NFP revision context (MRI-R37).
    # Runs after PR-I so the full enrichment order is stable.
    _attach_integrity_and_revision_context(upcoming_block, root, today)
    log.info("integrity chip + revision context attached to %d items", len(upcoming_block))

    # 4. Load existing ledger
    ledger_path = root / _LEDGER_RELPATH
    existing_ledger = _load_ledger(ledger_path)
    log.info("loaded %d existing ledger rows", len(existing_ledger))

    # 3b. MRI-R26: attach provenance (input_snapshot + coverage_flags) to each upcoming item.
    # Must run AFTER enrichments so prediction_id is present; BEFORE ledger rows so flags freeze.
    snapshots_dir = root / _INPUT_SNAPSHOTS_RELPATH
    _attach_provenance(upcoming_block, ledger_path, snapshots_dir, dry_run=dry_run)
    log.info("provenance: coverage flags and snapshot refs attached to %d items", len(upcoming_block))

    # 3c. Round-2b + W11-G: attach shadow projections to upcoming items (display-only, additive).
    # Now includes mf_energy for cpi_headline (W11-G task 1).
    # Fail-open per model: errors logged in _run_shadow_*/helpers, never break the build.
    _attach_shadows_to_items(upcoming_block, root, today)
    shadow_counts = {item.get("release_type", "?"): len(item.get("shadows", {}))
                     for item in upcoming_block if item.get("shadows")}
    log.info("shadow projections attached (incl. mf_energy): %s", shadow_counts)

    # 3c-R40: MRI-R40 combined_v1 combination layer (cpi_headline + cpi_core).
    # Must run AFTER _attach_shadows_to_items (needs tonight's shadow points) and
    # AFTER ledger load (needs scored errors for weight computation).
    _attach_combined_to_items(upcoming_block, existing_ledger, root, today)
    combined_counts = {item.get("release_type", "?"): (item.get("combined") is not None)
                       for item in upcoming_block if item.get("release_type") in _SHADOW_COMBINED_V1_TARGETS}
    log.info("combined_v1 attached: %s", combined_counts)

    # 3d. MRI-R35: assign cutoff_label to each upcoming item before ledger rows freeze them.
    _assign_cutoff_labels(upcoming_block)
    log.info("cutoff labels assigned to %d items", len(upcoming_block))

    # 5. Build today's projection ledger rows (champion, model=None)
    proj_ledger_rows = _build_projection_ledger_rows(today, upcoming_block, policy_backdrop)

    # 5b. Round-2b + W11-G: Build shadow_projection ledger rows
    # (model="v3_factor"|"cpi_bridge"|"mf_energy")
    shadow_ledger_rows = _build_shadow_ledger_rows(today, upcoming_block, root)
    log.info("shadow ledger rows built: %d (incl. mf_energy)", len(shadow_ledger_rows))

    # 6. MRI-R32a: catch-up scoring sweep — score ANY unscored past-release projection
    # (champion + shadow) whose initial print is in vintages; 120d lookback, idempotent.
    scored_rows = _check_release_day_capture(today, root, existing_ledger)
    log.info("catch-up scoring sweep: %d new scored rows (champion + shadow)", len(scored_rows))

    # 6a. Revision sweep (schema v2)
    combined_for_revision = existing_ledger + scored_rows
    revision_rows = _check_revision_sweep(today, root, combined_for_revision)
    log.info("revision sweep: %d new revision rows", len(revision_rows))

    # 6b. Reaction rows (schema v2)
    reaction_rows = _check_reaction_rows(today, root, combined_for_revision)
    log.info("reaction rows: %d new reaction rows", len(reaction_rows))

    # 6c. MRI-R32e: capture_health block
    capture_health = _compute_capture_health(today, root, existing_ledger + scored_rows)
    log.info(
        "capture_health: last_asof=%s gap_days=%s past_due=%d",
        capture_health.get("last_nightly_asof"),
        capture_health.get("nightly_gap_days"),
        capture_health.get("past_due_unscored_count", 0),
    )
    if capture_health.get("past_due_unscored"):
        for item in capture_health["past_due_unscored"]:
            log.warning(
                "CAPTURE_HEALTH: unscored %s/%s (release_date=%s reason=%s)",
                item.get("release"), item.get("period"),
                item.get("release_date"), item.get("reason"),
            )

    # 6d. MRI-R33 SNAPSHOT-GC-1: GC input_snapshots older than 30d (keep frozen T-1 receipts)
    if not dry_run:
        try:
            _run_snapshot_gc(snapshots_dir, existing_ledger + proj_ledger_rows, today)
        except Exception as exc_gc:
            log.debug("snapshot GC step failed (non-fatal): %s", exc_gc)

    # 7. Determine accrual start (earliest projection asof_night in ledger, or today)
    all_proj_nights = [
        r.get("asof_night", "")
        for r in existing_ledger + proj_ledger_rows
        if r.get("row_type") == "projection" and r.get("asof_night")
    ]
    accrual_start = min(all_proj_nights) if all_proj_nights else today.isoformat()

    # 8. Scoreboard from all scored + revision + reaction rows (champion + shadow)
    all_ledger_for_scoreboard = existing_ledger + scored_rows + revision_rows + reaction_rows
    scoreboard = _build_scoreboard(all_ledger_for_scoreboard, accrual_start, root=root)

    # 9. Build last_scored for latest.json (most recent scored row per release_type, champion only)
    all_scored = [r for r in existing_ledger if r.get("row_type") == "scored" and r.get("model") is None] + \
                 [r for r in scored_rows if r.get("model") is None]
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
        "enrichments": [
            "surprise_distribution", "market_implied", "reaction_sensitivity",
            "quirk_flags", "expectation_read", "coverage_flags", "input_snapshot_ref",
            "shadows", "cutoff_label",
            # W11-G additions
            "print_integrity", "revision_context",
            # MRI-R40: combined_v1 combination layer
            "combined",
        ],
        "upcoming": upcoming_block,
        "last_scored": last_scored,
        "scoreboard_ref": "data/release_forecast/scoreboard.json",
        # MRI-R32e: capture health strip
        "capture_health": capture_health,
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

        # Append all new rows to ledger (champion + shadow projection rows + scored + revision + reaction)
        all_new_rows = proj_ledger_rows + shadow_ledger_rows + scored_rows + revision_rows + reaction_rows
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
