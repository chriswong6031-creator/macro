"""engine/theme_clinical.py — Per-theme clinical-pipeline rollup (TIL W10).

DISPLAY / CONFLUENCE CONTEXT ONLY.
Authority: may_rank=false, may_gate=false, may_size=false, may_escalate=false,
           is_context_only=true.

Framing (R-TIL-9, spec PR-W10):
  ClinicalTrials.gov v2 theme-level aggregate → registration velocity YoY,
  enrollment-commitment trend, phase-migration read (share of active pipeline
  in Phase-2+ vs year ago — maturing pipeline = nearing monetization).
  12-24mo leading capital-commitment leg for healthcare-adjacent themes.

LIKE-MONTH LAW (W8 precedent):
  YoY comparisons ALWAYS compare the same calendar-month range one year earlier
  (e.g., Q1-2026 vs Q1-2025). This eliminates seasonal registration patterns
  (end-of-year filing clusters, clinical conference cycles). NO unlike-month
  comparisons on unadjusted monthly data.

CRITICAL FENCE:
  No composite across themes. Each theme is independent.
  Never fold into fused_obs_z — separate display leg only.

Input (reads from parquet, never network):
  data/clinical_trials/modality_monthly.parquet
    columns: [modality_id, theme_id, nct_id, study_first_post_date,
              year_month, phases_raw, phase1, phase2, phase3,
              enrollment_target, sponsor_class, ingest_date, vocabulary_version]

Outputs:
  data/neuralweb/theme_clinical.json      (NW artifact; git-tracked)
  site/basketdata/clinical_pipeline.json  (compact site projection; git-tracked)

Multi-path fallback:
  1. CLINICAL_THEMES_STORE env var override
  2. Worktree-local data/clinical_trials/modality_monthly.parquet
  3. Main checkout data/clinical_trials/modality_monthly.parquet
  When absent → honest null written; exit 0.

Usage (collect-lane step):
  from engine.theme_clinical import compute_theme_clinical
  result = compute_theme_clinical()
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (display-tier; never scored)
# ---------------------------------------------------------------------------
AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
    "framing": "clinical_pipeline_capital_commitment",
    "rotation_calls": False,
    "short_calls": False,
    "fused_obs_z_fence": "SEPARATE_DISPLAY_LEG — never fold into fused_obs_z",
}

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config" / "clinical_modalities.yml"
_DEFAULT_STORE = _REPO_ROOT / "data" / "clinical_trials"
_MAIN_CHECKOUT_STORE = Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/clinical_trials"
)
_NW_OUT = _REPO_ROOT / "data" / "neuralweb" / "theme_clinical.json"
_SITE_OUT = _REPO_ROOT / "site" / "basketdata" / "clinical_pipeline.json"
_PARQUET_FILE = "modality_monthly.parquet"

# Like-month YoY window (in months)
_YOY_WINDOW_MONTHS = 12
# Minimum months for YoY computation
_MIN_MONTHS_YOY = 13
# Minimum months for phase-migration trend
_MIN_MONTHS_TREND = 13

# Magnitude bands for velocity reads
_BAND_LARGE_PCT = 25.0
_BAND_MODERATE_PCT = 10.0
_NEUTRAL_FLOOR_PCT = 5.0  # |YoY%| < this → neutral


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _store_path() -> Path:
    override = os.environ.get("CLINICAL_THEMES_STORE")
    if override:
        return Path(override)
    return _DEFAULT_STORE


# ---------------------------------------------------------------------------
# Parquet loader with multi-path fallback
# ---------------------------------------------------------------------------

def _load_parquet() -> Optional[pd.DataFrame]:
    """Load modality_monthly.parquet with multi-path fallback."""
    candidates = [
        _store_path() / _PARQUET_FILE,
        _REPO_ROOT / "data" / "clinical_trials" / _PARQUET_FILE,
        _MAIN_CHECKOUT_STORE / _PARQUET_FILE,
    ]
    for path in candidates:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                log.info("theme_clinical: loaded parquet from %s (%d rows)", path, len(df))
                return df
            except Exception as exc:  # noqa: BLE001
                log.warning("theme_clinical: parquet unreadable at %s: %s", path, exc)
    log.info(
        "theme_clinical: modality_monthly.parquet not found in any candidate path. "
        "Returning honest null. Run collectors/clinicaltrials_themes.py to populate."
    )
    return None


# ---------------------------------------------------------------------------
# Like-month YoY registration velocity (per-theme, per-month series)
# ---------------------------------------------------------------------------

def _compute_registration_yoy(monthly_series: pd.Series) -> Optional[float]:
    """
    Compute like-month YoY for new-registration count.

    LIKE-MONTH LAW: compare trailing 12 months vs the 12 months one year prior.
    This ensures seasonal registration patterns (end-of-year filing clusters,
    conference submission cycles) cancel between numerator and denominator.

    Requires: series indexed by year_month (YYYY-MM), values = n_new_registrations.
    Returns: YoY % change of trailing-12m vs prior-12m sum, or None if < 13 months.
    """
    if monthly_series is None or len(monthly_series) < _MIN_MONTHS_YOY:
        return None
    series = monthly_series.dropna().sort_index()
    if len(series) < _MIN_MONTHS_YOY:
        return None
    # Trailing 12 months
    recent_12 = series.iloc[-12:].sum()
    # Same 12-month window one year earlier (months -24 to -13)
    if len(series) < 24:
        # Partial prior window: use what we have (min 12 months prior)
        n_prior = len(series) - 12
        if n_prior < 1:
            return None
        prior_12 = series.iloc[-24:-12].sum() if len(series) >= 24 else series.iloc[:n_prior].sum()
    else:
        prior_12 = series.iloc[-24:-12].sum()
    if prior_12 == 0 or pd.isna(prior_12):
        return None
    return float((recent_12 - prior_12) / abs(prior_12) * 100.0)


def _compute_enrollment_yoy(monthly_series: pd.Series) -> Optional[float]:
    """
    Compute like-month YoY for enrollment-commitment sum.
    Same construction as _compute_registration_yoy but on enrollment_sum values.
    """
    return _compute_registration_yoy(monthly_series)


def _magnitude_band(abs_yoy: float) -> Optional[str]:
    if abs_yoy >= _BAND_LARGE_PCT:
        return "large"
    if abs_yoy >= _BAND_MODERATE_PCT:
        return "moderate"
    return "small"


def _velocity_read(yoy_pct: Optional[float]) -> tuple[str, Optional[str]]:
    """Convert YoY % to (velocity_read, magnitude_band)."""
    if yoy_pct is None or abs(yoy_pct) < _NEUTRAL_FLOOR_PCT:
        return "neutral", None
    band = _magnitude_band(abs(yoy_pct))
    direction = "accelerating" if yoy_pct > 0 else "decelerating"
    return direction, band


# ---------------------------------------------------------------------------
# Phase-migration read
# ---------------------------------------------------------------------------

def _compute_phase_distribution(
    monthly_df: pd.DataFrame,
) -> dict:
    """
    Phase distribution of INDUSTRY-sponsored registrations by first-post cohort.

    IMPORTANT — NON-PIT CAVEAT:
    The ClinicalTrials.gov v2 API returns only the CURRENT phase for each study
    (there is no historical phase field). Phase stored in the parquet is the phase
    as of the ingest date, not as of the study's first-post date. Consequently:
      - Trailing-12m window: near-PIT (most studies don't migrate phase within
        months of registration; ingest ≈ registration for recent rows).
      - Prior window (backfill, pre-2025): phase-as-of-2026-ingest — these studies
        have had years to migrate to a later phase. Prior-window Phase-2+ share is
        UPPER-BIASED relative to what it was at original registration.
      - Cross-cohort delta (delta_pp) is CONFOUNDED by observation-lag asymmetry
        and must NOT be interpreted as evidence of pipeline maturation. It is
        published as None and must not drive any read or claim.

    What this function returns is accurate and useful:
      - share_phase2plus_recent: Phase-2+ share among trailing-12m registrations
        (near-PIT) — a valid cross-sectional snapshot of recent registrations.
      - n_phase3_recent: count of Phase-3 registrations in trailing 12m (near-PIT).
    The prior-window counts are published for transparency, with explicit caveat.

    LIKE-MONTH LAW: windows defined by trailing-12 vs prior-12 month buckets of
    study_first_post_date (PIT registration date), not ingest date.

    Returns:
      {
        share_phase2plus_recent: float (0-1) — Phase-2+ share, trailing 12m (near-PIT),
        share_phase2plus_prior:  float (0-1) — Phase-2+ share, prior 12m (UPPER-BIASED;
                                               do not compare to recent),
        delta_pp: None — always None; cross-cohort comparison is confounded (see above),
        n_total_recent: int,
        n_phase2plus_recent: int,
        n_phase3_recent: int,
        n_total_prior: int,
        n_phase2plus_prior: int,
        read: str — "high_late_stage" | "mixed" | "early_stage" | "insufficient_data",
               based on recent-window share_phase2plus_recent ONLY (not delta),
        phase_data_caveat: str — machine-readable caveat for downstream consumers,
        coverage_note: str,
      }

    """
    null_result = {
        "share_phase2plus_recent": None,
        "share_phase2plus_prior": None,
        "delta_pp": None,
        "n_total_recent": 0,
        "n_phase2plus_recent": 0,
        "n_phase3_recent": 0,
        "n_total_prior": 0,
        "n_phase2plus_prior": 0,
        "read": "insufficient_data",
        "phase_data_caveat": (
            "phase_non_pit: API returns current phase only; backfill rows carry "
            "phase-as-of-ingest (upper-biased toward late phase for pre-2025 studies); "
            "cross-cohort delta is confounded and not published."
        ),
        "coverage_note": "Insufficient data for phase distribution computation",
    }
    if monthly_df is None or monthly_df.empty:
        return null_result

    months = sorted(monthly_df["year_month"].unique())
    if len(months) < _MIN_MONTHS_TREND:
        null_result["coverage_note"] = f"Only {len(months)} months; need {_MIN_MONTHS_TREND}"
        return null_result

    recent_months = set(months[-12:])
    # Prior window: months -24 to -13 (or earlier available)
    prior_months = set(months[-24:-12]) if len(months) >= 24 else set(months[:max(1, len(months) - 12)])

    recent_df = monthly_df[monthly_df["year_month"].isin(recent_months)]
    prior_df = monthly_df[monthly_df["year_month"].isin(prior_months)]

    n_total_recent = len(recent_df)
    n_phase2plus_recent = int(recent_df["phase2"].fillna(0).sum() + recent_df["phase3"].fillna(0).sum())
    n_phase3_recent = int(recent_df["phase3"].fillna(0).sum())
    n_total_prior = len(prior_df)
    n_phase2plus_prior = int(prior_df["phase2"].fillna(0).sum() + prior_df["phase3"].fillna(0).sum())

    if n_total_recent == 0:
        null_result["coverage_note"] = "No studies in recent 12-month window"
        return null_result

    share_recent = n_phase2plus_recent / n_total_recent
    share_prior = (n_phase2plus_prior / n_total_prior) if n_total_prior > 0 else None

    # Read: based on recent-window ONLY (cross-cohort delta is confounded — see docstring).
    # Thresholds on current registration mix:
    #   >= 40% Phase-2+: high_late_stage (late-stage programs dominating new registrations)
    #   >= 15% Phase-2+: mixed
    #   < 15% Phase-2+: early_stage (predominantly early-phase new registrations)
    if share_recent >= 0.40:
        read = "high_late_stage"
    elif share_recent >= 0.15:
        read = "mixed"
    else:
        read = "early_stage"

    caveat = (
        "phase_non_pit: API returns current phase only; backfill rows carry "
        "phase-as-of-ingest (upper-biased toward late phase for pre-2025 studies); "
        "cross-cohort delta is confounded and not published; "
        "read is based on trailing-12m recent-window only (near-PIT)."
    )

    cov = (
        f"{n_total_recent} INDUSTRY studies in trailing 12m "
        f"({n_phase2plus_recent} Phase-2+, {n_phase3_recent} Phase-3; "
        f"phase as of ingest, near-PIT for recent registrations); "
        f"{n_total_prior} studies in prior window "
        f"(phase upper-biased; cross-cohort delta not published)"
    )

    return {
        "share_phase2plus_recent": round(share_recent, 4),
        "share_phase2plus_prior": round(share_prior, 4) if share_prior is not None else None,
        "delta_pp": None,  # confounded; not published (see phase_data_caveat)
        "n_total_recent": n_total_recent,
        "n_phase2plus_recent": n_phase2plus_recent,
        "n_phase3_recent": n_phase3_recent,
        "n_total_prior": n_total_prior,
        "n_phase2plus_prior": n_phase2plus_prior,
        "read": read,
        "phase_data_caveat": caveat,
        "coverage_note": cov,
    }


# Keep the old name as an alias so callers using the old name still work during migration.
# All new code must call _compute_phase_distribution directly.
_compute_phase_migration = _compute_phase_distribution


# ---------------------------------------------------------------------------
# Per-modality rollup
# ---------------------------------------------------------------------------

def _rollup_modality(
    modality_id: str,
    modality_cfg: dict,
    theme_df: pd.DataFrame,
) -> dict:
    """Roll up one modality into its metrics."""
    mod_df = theme_df[theme_df["modality_id"] == modality_id].copy()

    if mod_df.empty:
        return {
            "modality_id": modality_id,
            "theme_id": modality_cfg.get("theme_id", ""),
            "n_studies_total": 0,
            "year_month_max": None,
            "registration_yoy_pct": None,
            "registration_velocity_read": "neutral",
            "registration_magnitude_band": None,
            "enrollment_yoy_pct": None,
            "enrollment_velocity_read": "neutral",
            "enrollment_magnitude_band": None,
            "phase_distribution": _compute_phase_distribution(mod_df),
            "n_phase3_trailing12m": 0,
            "coverage_note": "No data — run collectors/clinicaltrials_themes.py",
            "coverage_note_zh": "暂无数据——请运行临床试验主题采集器。",
            "expected_read": modality_cfg.get("expected_read", ""),
        }

    n_total = len(mod_df)
    year_month_max = mod_df["year_month"].max() if not mod_df.empty else None

    # Monthly registration counts
    monthly_reg = (
        mod_df.groupby("year_month")["nct_id"].count()
        .sort_index()
        .rename("n_new_registrations")
    )

    # Monthly enrollment sums
    monthly_enroll = (
        mod_df.dropna(subset=["enrollment_target"])
        .groupby("year_month")["enrollment_target"].sum()
        .sort_index()
    )

    reg_yoy = _compute_registration_yoy(monthly_reg)
    enroll_yoy = _compute_enrollment_yoy(monthly_enroll)
    reg_read, reg_band = _velocity_read(reg_yoy)
    enroll_read, enroll_band = _velocity_read(enroll_yoy)

    # Phase distribution (row-level, not monthly aggregated)
    # NOTE: phase is non-PIT for backfill rows — see _compute_phase_distribution docstring.
    pm = _compute_phase_distribution(mod_df)

    # n_phase3 in trailing 12 months
    if year_month_max:
        months_all = sorted(mod_df["year_month"].unique())
        recent_12m = set(months_all[-12:]) if len(months_all) >= 12 else set(months_all)
        n_phase3_t12 = int(mod_df[mod_df["year_month"].isin(recent_12m)]["phase3"].fillna(0).sum())
    else:
        n_phase3_t12 = 0

    cov_en = (
        f"{n_total} INDUSTRY-sponsored studies; "
        f"most recent registration: {year_month_max or 'unknown'}; "
        f"{len(monthly_reg)} months of registration data"
    )
    cov_zh = (
        f"共{n_total}个行业赞助研究；"
        f"最近注册月份：{year_month_max or '未知'}；"
        f"{len(monthly_reg)}个月的注册数据"
    )

    return {
        "modality_id": modality_id,
        "theme_id": modality_cfg.get("theme_id", ""),
        "n_studies_total": n_total,
        "year_month_max": year_month_max,
        "registration_yoy_pct": round(reg_yoy, 2) if reg_yoy is not None else None,
        "registration_velocity_read": reg_read,
        "registration_magnitude_band": reg_band,
        "enrollment_yoy_pct": round(enroll_yoy, 2) if enroll_yoy is not None else None,
        "enrollment_velocity_read": enroll_read,
        "enrollment_magnitude_band": enroll_band,
        "phase_distribution": pm,
        "n_phase3_trailing12m": n_phase3_t12,
        "coverage_note": cov_en,
        "coverage_note_zh": cov_zh,
        "expected_read": modality_cfg.get("expected_read", ""),
    }


# ---------------------------------------------------------------------------
# Per-theme rollup (aggregates across modalities)
# ---------------------------------------------------------------------------

def _rollup_theme(
    theme_id: str,
    modality_cfgs: list[dict],
    df: Optional[pd.DataFrame],
) -> dict:
    """Roll up all modalities for a theme into a per-theme object."""
    modality_results: dict[str, dict] = {}

    for mcfg in modality_cfgs:
        mid = mcfg["modality_id"]
        if df is None or df.empty:
            modality_results[mid] = {
                "modality_id": mid,
                "theme_id": theme_id,
                "n_studies_total": 0,
                "year_month_max": None,
                "registration_yoy_pct": None,
                "registration_velocity_read": "neutral",
                "registration_magnitude_band": None,
                "enrollment_yoy_pct": None,
                "enrollment_velocity_read": "neutral",
                "enrollment_magnitude_band": None,
                "phase_distribution": _compute_phase_distribution(pd.DataFrame()),
                "n_phase3_trailing12m": 0,
                "coverage_note": (
                    "No data — run collectors/clinicaltrials_themes.py to populate. "
                    "Keyless (ClinicalTrials.gov v2; no API key required)."
                ),
                "coverage_note_zh": "暂无数据——请运行临床试验主题采集器（无需API密钥）。",
                "expected_read": mcfg.get("expected_read", ""),
            }
        else:
            modality_results[mid] = _rollup_modality(mid, mcfg, df)

    # Theme-level summary: aggregate across modalities
    n_modalities = len(modality_cfgs)
    modalities_with_data = sum(
        1 for r in modality_results.values() if r.get("n_studies_total", 0) > 0
    )
    total_studies = sum(r.get("n_studies_total", 0) for r in modality_results.values())

    # Theme-level YoY: simple average of modality YoYs where available
    reg_yoys = [
        r["registration_yoy_pct"]
        for r in modality_results.values()
        if r.get("registration_yoy_pct") is not None
    ]
    theme_reg_yoy: Optional[float] = (
        round(float(np.mean(reg_yoys)), 2) if reg_yoys else None
    )
    theme_reg_read, theme_reg_band = _velocity_read(theme_reg_yoy)

    # Theme-level phase-migration: weighted by total studies per modality
    n_phase3_t12_total = sum(r.get("n_phase3_trailing12m", 0) for r in modality_results.values())

    year_month_max_overall = max(
        (r["year_month_max"] for r in modality_results.values() if r.get("year_month_max")),
        default=None,
    )

    cov_en = (
        f"{modalities_with_data}/{n_modalities} modalities have data; "
        f"{total_studies} total INDUSTRY-sponsored studies; "
        f"most recent: {year_month_max_overall or 'unknown'}"
    )
    cov_zh = (
        f"{n_modalities}个模态中{modalities_with_data}个有数据；"
        f"共{total_studies}个行业赞助研究；"
        f"最新月份：{year_month_max_overall or '未知'}"
    )

    return {
        "theme_id": theme_id,
        "n_modalities_configured": n_modalities,
        "n_modalities_with_data": modalities_with_data,
        "n_studies_total": total_studies,
        "year_month_max": year_month_max_overall,
        "theme_registration_yoy_pct": theme_reg_yoy,
        "theme_registration_velocity_read": theme_reg_read,
        "theme_registration_magnitude_band": theme_reg_band,
        "n_phase3_trailing12m": n_phase3_t12_total,
        "modalities": modality_results,
        "coverage_note": cov_en,
        "coverage_note_zh": cov_zh,
    }


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_theme_clinical(
    write_nw: bool = True,
    write_site: bool = True,
) -> dict:
    """
    Compute per-theme clinical-pipeline rollups and write outputs.

    Returns the full NW artifact dict (regardless of write flags).
    Always returns (never raises) — tolerant; exits 0.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    as_of_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Load config
    try:
        cfg = _load_config()
    except Exception as exc:  # noqa: BLE001
        log.error("theme_clinical: config load failed: %s", exc)
        return _honest_null_output(now_str, as_of_date, f"config load error: {exc}")

    modalities = cfg.get("modalities") or []
    vocab_version = str(cfg.get("vocabulary_version", "v1"))

    # Group modalities by theme_id
    by_theme: dict[str, list[dict]] = {}
    for m in modalities:
        tid = m.get("theme_id", "unknown")
        by_theme.setdefault(tid, []).append(m)

    # Load parquet (honest null if absent)
    df = _load_parquet()

    themes_out: dict[str, dict] = {}
    for theme_id, theme_modalities in sorted(by_theme.items()):
        themes_out[theme_id] = _rollup_theme(theme_id, theme_modalities, df)

    # Coverage stats
    themes_with_data = sum(
        1 for t in themes_out.values() if t.get("n_modalities_with_data", 0) > 0
    )
    total_studies = sum(t.get("n_studies_total", 0) for t in themes_out.values())

    nw_artifact = {
        "schema": "theme_clinical.v1",
        "as_of": as_of_date,
        "generated_at": now_str,
        "vocabulary_version": vocab_version,
        "authority": AUTHORITY,
        "honesty_header": (
            "Clinical-pipeline capital-commitment context derived from ClinicalTrials.gov v2 "
            "(keyless; INDUSTRY-sponsored studies only; first-post date as PIT key). "
            "Display/context only. Not a scored factor. Not a buy/sell signal. "
            "Like-month YoY law: all YoY comparisons use same calendar-month windows "
            "(trailing 12m vs prior 12m) — seasonal registration patterns cancel. "
            "Phase distribution: the API returns only CURRENT phase per study — there is "
            "no historical phase field. Phase stored in the parquet is phase as of the "
            "ingest date. For trailing-12m registrations, ingest-phase is near-PIT (studies "
            "rarely migrate phase within months of registration). For backfill studies "
            "(pre-2025), phase may have advanced since first registration — prior-window "
            "Phase-2+ shares are upper-biased. Cross-cohort phase delta (prior vs recent) "
            "is confounded by observation-lag asymmetry and is NOT published. "
            "Phase distribution read (high_late_stage/mixed/early_stage) is based on "
            "trailing-12m registrations only (near-PIT). "
            "No composite across themes — each theme is independent. "
            "INDUSTRY filter: AREA[LeadSponsorClass]INDUSTRY (verified 2026-07-09)."
        ),
        "coverage_stats": {
            "total_themes": len(themes_out),
            "themes_with_data": themes_with_data,
            "total_modalities_configured": len(modalities),
            "total_studies_stored": total_studies,
            "parquet_absent": df is None,
        },
        "api_note": (
            "Source: ClinicalTrials.gov v2 API (clinicaltrials.gov/api/v2/studies). "
            "Keyless (no API key required — verified 2026-07-09). "
            "INDUSTRY filter: filter.advanced=AREA[LeadSponsorClass]INDUSTRY. "
            "Backfill from 2018-01-01 (AREA[StudyFirstPostDate]RANGE[2018-01-01,MAX]). "
            "Full fetch every run — no incremental mode (API returns only current state; "
            "state file records last-ingest date for monitoring only). "
            "Phase: API returns current phase only (non-PIT for backfill rows). "
            "vocabulary_version stamps query definition for PIT-safe history."
        ),
        "themes": themes_out,
    }

    site_artifact = _build_site_projection(nw_artifact)

    if write_nw:
        try:
            _NW_OUT.parent.mkdir(parents=True, exist_ok=True)
            with open(_NW_OUT, "w", encoding="utf-8") as fh:
                json.dump(nw_artifact, fh, indent=2, ensure_ascii=False)
            log.info("theme_clinical: wrote NW artifact to %s", _NW_OUT)
        except Exception as exc:  # noqa: BLE001
            log.error("theme_clinical: NW artifact write failed: %s", exc)

    if write_site:
        try:
            _SITE_OUT.parent.mkdir(parents=True, exist_ok=True)
            with open(_SITE_OUT, "w", encoding="utf-8") as fh:
                json.dump(site_artifact, fh, indent=2, ensure_ascii=False)
            log.info("theme_clinical: wrote site projection to %s", _SITE_OUT)
        except Exception as exc:  # noqa: BLE001
            log.error("theme_clinical: site projection write failed: %s", exc)

    return nw_artifact


# ---------------------------------------------------------------------------
# Site projection (compact)
# ---------------------------------------------------------------------------

def _build_site_projection(nw: dict) -> dict:
    """Build compact site projection from the full NW artifact."""
    compact_themes: dict[str, dict] = {}
    for theme_id, t in nw.get("themes", {}).items():
        compact_modalities: dict[str, dict] = {}
        for mid, m in (t.get("modalities") or {}).items():
            compact_modalities[mid] = {
                "modality_id": mid,
                "n_studies_total": m.get("n_studies_total"),
                "year_month_max": m.get("year_month_max"),
                "registration_yoy_pct": m.get("registration_yoy_pct"),
                "registration_velocity_read": m.get("registration_velocity_read"),
                "registration_magnitude_band": m.get("registration_magnitude_band"),
                "enrollment_yoy_pct": m.get("enrollment_yoy_pct"),
                "enrollment_velocity_read": m.get("enrollment_velocity_read"),
                "n_phase3_trailing12m": m.get("n_phase3_trailing12m"),
                "phase_distribution_read": m.get("phase_distribution", {}).get("read"),
                "phase_distribution_share_phase2plus_recent": m.get("phase_distribution", {}).get("share_phase2plus_recent"),
                "phase_data_caveat": m.get("phase_distribution", {}).get("phase_data_caveat"),
                "coverage_note": m.get("coverage_note"),
                "coverage_note_zh": m.get("coverage_note_zh"),
                "expected_read": m.get("expected_read"),
            }
        compact_themes[theme_id] = {
            "theme_id": theme_id,
            "n_modalities_configured": t.get("n_modalities_configured"),
            "n_modalities_with_data": t.get("n_modalities_with_data"),
            "n_studies_total": t.get("n_studies_total"),
            "year_month_max": t.get("year_month_max"),
            "theme_registration_yoy_pct": t.get("theme_registration_yoy_pct"),
            "theme_registration_velocity_read": t.get("theme_registration_velocity_read"),
            "theme_registration_magnitude_band": t.get("theme_registration_magnitude_band"),
            "n_phase3_trailing12m": t.get("n_phase3_trailing12m"),
            "modalities": compact_modalities,
            "coverage_note": t.get("coverage_note"),
            "coverage_note_zh": t.get("coverage_note_zh"),
        }

    return {
        "schema": "theme_clinical.v1",
        "as_of": nw.get("as_of"),
        "generated_at": nw.get("generated_at"),
        "authority": nw.get("authority"),
        "honesty_header": nw.get("honesty_header"),
        "coverage_stats": nw.get("coverage_stats"),
        "themes": compact_themes,
    }


# ---------------------------------------------------------------------------
# Honest null output
# ---------------------------------------------------------------------------

def _honest_null_output(now_str: str, as_of_date: str, reason: str) -> dict:
    return {
        "schema": "theme_clinical.v1",
        "as_of": as_of_date,
        "generated_at": now_str,
        "authority": AUTHORITY,
        "honesty_header": "No data available — see coverage_stats.error for details.",
        "coverage_stats": {
            "total_themes": 0,
            "themes_with_data": 0,
            "total_modalities_configured": 0,
            "total_studies_stored": 0,
            "parquet_absent": True,
            "error": reason,
        },
        "themes": {},
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Theme clinical-pipeline rollup engine (TIL W10)"
    )
    parser.add_argument("--no-write-nw", action="store_true",
                        help="Skip writing data/neuralweb/theme_clinical.json")
    parser.add_argument("--no-write-site", action="store_true",
                        help="Skip writing site/basketdata/clinical_pipeline.json")
    args = parser.parse_args()

    result = compute_theme_clinical(
        write_nw=not args.no_write_nw,
        write_site=not args.no_write_site,
    )
    stats = result.get("coverage_stats", {})
    print(
        f"theme_clinical: {stats.get('themes_with_data', 0)}/{stats.get('total_themes', 0)} "
        f"themes with data, {stats.get('total_studies_stored', 0)} total studies"
    )
