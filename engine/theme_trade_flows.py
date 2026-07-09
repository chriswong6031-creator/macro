"""engine/theme_trade_flows.py — Per-theme import-flow rollup (TIL W8).

DISPLAY / CONFLUENCE CONTEXT ONLY.
Authority: may_rank=false, may_gate=false, may_size=false, may_escalate=false,
           is_context_only=true.

Framing (R-TIL-9, spec PR-W8):
  Census HS-code monthly import values → per-theme YoY growth and 3m-vs-12m
  acceleration, signed by expected_direction from trade_flow_codes.yml.
  Physical-flow leg for onshoring/substitution themes — parallel to JODI/EIA.

  Sign convention (expected_direction field in config):
    rising_imports_confirms  → confirmation = positive YoY / positive accel
    falling_imports_confirms → confirmation = NEGATIVE YoY / negative accel
                               (import decline = domestic substitution progress)
  Confirmation reads:
    "confirms"     — direction of signal matches expected_direction
    "contradicts"  — direction opposes expected_direction
    "neutral"      — magnitude below noise floor (|YoY| < 5% or insufficient data)
  Magnitude bands: large (>20% abs YoY), moderate (10-20%), small (5-10%)

CRITICAL FENCE:
  No composite score across themes. Each theme is independent.
  Never fold into fused_obs_z — separate display leg only.

Input (reads from parquet, never network):
  data/trade_flows/imports_monthly.parquet
    columns: [hs_code, stat_month, value_usd, quantity, quantity_unit, ingested_at]

Outputs:
  data/neuralweb/theme_trade_flows.json   (internal NW artifact; git-tracked)
  site/basketdata/trade_flows.json        (site projection; git-tracked; compact)

Data availability:
  Multi-path fallback (mirrors theme_hiring.py pattern):
    1. TRADE_FLOWS_STORE env var override
    2. Worktree-local data/trade_flows/imports_monthly.parquet
    3. Main checkout data/trade_flows/imports_monthly.parquet
  When parquet is absent: returns honest null; exit 0.
  When CENSUS_API_KEY is absent: parquet may be absent; honest null is correct.

Usage (collect-lane step):
  from engine.theme_trade_flows import compute_theme_trade_flows
  result = compute_theme_trade_flows()
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
    "framing": "physical_import_flow_context",
    "rotation_calls": False,
    "short_calls": False,
    "fused_obs_z_fence": "SEPARATE_DISPLAY_LEG — never fold into fused_obs_z",
}

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CODES_PATH = _REPO_ROOT / "config" / "trade_flow_codes.yml"
_DEFAULT_STORE = _REPO_ROOT / "data" / "trade_flows"
_MAIN_CHECKOUT_STORE = Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/data/trade_flows"
)
_NW_OUT = _REPO_ROOT / "data" / "neuralweb" / "theme_trade_flows.json"
_SITE_OUT = _REPO_ROOT / "site" / "basketdata" / "trade_flows.json"

_PARQUET_FILE = "imports_monthly.parquet"

# YoY threshold below which we call "neutral" (avoid noise from tiny swings)
_NEUTRAL_THRESHOLD_PCT = 5.0  # abs(YoY%) < this → neutral

# Magnitude bands (abs YoY%)
_BAND_LARGE = 20.0
_BAND_MODERATE = 10.0


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_codes() -> list[dict]:
    """Load HS-code config from trade_flow_codes.yml."""
    with open(_CODES_PATH, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg.get("codes", [])


def _store_path() -> Path:
    override = os.environ.get("TRADE_FLOWS_STORE")
    if override:
        return Path(override)
    return _DEFAULT_STORE


# ---------------------------------------------------------------------------
# Parquet loader with multi-path fallback
# ---------------------------------------------------------------------------

def _load_parquet() -> Optional[pd.DataFrame]:
    """
    Load imports_monthly.parquet with multi-path fallback.
    Returns None (honest null) if not found anywhere.
    """
    candidates = [
        _store_path() / _PARQUET_FILE,
        _REPO_ROOT / "data" / "trade_flows" / _PARQUET_FILE,
        _MAIN_CHECKOUT_STORE / _PARQUET_FILE,
    ]
    for path in candidates:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                log.info("theme_trade_flows: loaded parquet from %s (%d rows)", path, len(df))
                return df
            except Exception as exc:
                log.warning("theme_trade_flows: parquet unreadable at %s: %s", path, exc)
    log.info(
        "theme_trade_flows: imports_monthly.parquet not found in any candidate path. "
        "Returning honest null. Run collectors/census_trade.py to populate. "
        "Requires CENSUS_API_KEY env var."
    )
    return None


# ---------------------------------------------------------------------------
# YoY and 3m-vs-12m acceleration computations
# ---------------------------------------------------------------------------

def _compute_yoy(series: pd.Series) -> Optional[float]:
    """
    Compute YoY growth (%) for the most recent month in a monthly time series.
    series: indexed by stat_month (YYYY-MM strings), values are float import values.
    Returns None if insufficient data (< 13 months or most recent value is null).
    """
    if series is None or len(series) < 13:
        return None
    series = series.dropna().sort_index()
    if len(series) < 13:
        return None
    most_recent = series.iloc[-1]
    year_ago = series.iloc[-13]
    if year_ago == 0 or pd.isna(year_ago) or pd.isna(most_recent):
        return None
    return float((most_recent - year_ago) / abs(year_ago) * 100.0)


def _compute_accel(series: pd.Series) -> Optional[float]:
    """
    Compute 3m-vs-12m growth-rate acceleration.
    3m annualized rate minus 12m rate, in percentage-point terms.
    Returns None if insufficient data (< 13 months).
    """
    if series is None or len(series) < 13:
        return None
    series = series.dropna().sort_index()
    if len(series) < 13:
        return None

    # 3-month sum (most recent 3 months)
    v3_end = series.iloc[-1]
    v3_start = series.iloc[-4]  # 3 months ago
    if v3_start == 0 or pd.isna(v3_start) or pd.isna(v3_end):
        return None
    rate_3m = float((v3_end - v3_start) / abs(v3_start) * 100.0)

    # 12-month rate
    v12_start = series.iloc[-13]
    if v12_start == 0 or pd.isna(v12_start):
        return None
    rate_12m = float((v3_end - v12_start) / abs(v12_start) * 100.0)

    return float(rate_3m - rate_12m)


def _sign_reading(
    yoy_pct: Optional[float],
    accel: Optional[float],
    expected_direction: str,
) -> tuple[str, Optional[str]]:
    """
    Convert raw metrics to signed confirmation read.

    Returns:
      (confirmation, magnitude_band)
      confirmation ∈ {"confirms", "contradicts", "neutral"}
      magnitude_band ∈ {"large", "moderate", "small", None}
    """
    if yoy_pct is None:
        return "neutral", None

    abs_yoy = abs(yoy_pct)
    if abs_yoy < _NEUTRAL_THRESHOLD_PCT:
        return "neutral", None

    # Determine raw direction of imports
    imports_rising = yoy_pct > 0

    # Confirm or contradict based on expected_direction
    if expected_direction == "rising_imports_confirms":
        confirmation = "confirms" if imports_rising else "contradicts"
    elif expected_direction == "falling_imports_confirms":
        confirmation = "confirms" if not imports_rising else "contradicts"
    else:
        # Unknown direction — neutral
        return "neutral", None

    # Magnitude band
    if abs_yoy >= _BAND_LARGE:
        band = "large"
    elif abs_yoy >= _BAND_MODERATE:
        band = "moderate"
    else:
        band = "small"

    return confirmation, band


# ---------------------------------------------------------------------------
# Per-theme rollup
# ---------------------------------------------------------------------------

def _rollup_theme(
    theme_id: str,
    theme_codes: list[dict],
    df: pd.DataFrame,
) -> dict:
    """
    Roll up all codes for a theme into a per-theme object.

    Returns:
      {
        theme_id, n_codes_configured, n_codes_with_data,
        stat_month_max (most recent month with data),
        import_value_usd_3m (sum of last 3 months, across all codes),
        import_value_usd_12m (sum of last 12 months, across all codes),
        yoy_pct (theme-level, value-weighted average of code YoYs),
        accel_3m_vs_12m (theme-level, value-weighted average),
        confirmation ({"confirms", "contradicts", "neutral"}),
        magnitude_band,
        code_detail ([{hs_code, label_en, yoy_pct, accel, confirmation, n_months}]),
        coverage_note, coverage_note_zh,
      }
    """
    code_details = []
    weighted_yoy_sum = 0.0
    weighted_accel_sum = 0.0
    total_weight = 0.0
    codes_with_data = 0
    max_month: Optional[str] = None

    for code_cfg in theme_codes:
        hs_code = str(code_cfg["hs_code"]).strip()
        expected_dir = code_cfg.get("expected_direction", "rising_imports_confirms")
        label_en = code_cfg.get("label_en", hs_code)

        code_rows = df[df["hs_code"] == hs_code].copy()
        if code_rows.empty:
            code_details.append({
                "hs_code": hs_code,
                "label_en": label_en,
                "expected_direction": expected_dir,
                "yoy_pct": None,
                "accel_3m_vs_12m": None,
                "confirmation": "neutral",
                "magnitude_band": None,
                "n_months": 0,
                "coverage_note": "No data — requires CENSUS_API_KEY and initial backfill",
            })
            continue

        # Build monthly value series
        series = (
            code_rows.dropna(subset=["value_usd"])
            .groupby("stat_month")["value_usd"]
            .sum()
            .sort_index()
        )
        n_months = len(series)
        codes_with_data += 1

        if series.index.max() > (max_month or ""):
            max_month = series.index.max()

        yoy = _compute_yoy(series)
        accel = _compute_accel(series)
        confirmation, band = _sign_reading(yoy, accel, expected_dir)

        # Weight by recent import value (12-month average as proxy)
        weight = float(series.iloc[-12:].mean()) if n_months >= 12 else float(series.mean())
        if weight > 0 and yoy is not None:
            weighted_yoy_sum += yoy * weight
            total_weight += weight
        if weight > 0 and accel is not None:
            weighted_accel_sum += accel * weight

        code_details.append({
            "hs_code": hs_code,
            "label_en": label_en,
            "expected_direction": expected_dir,
            "yoy_pct": round(yoy, 2) if yoy is not None else None,
            "accel_3m_vs_12m": round(accel, 2) if accel is not None else None,
            "confirmation": confirmation,
            "magnitude_band": band,
            "n_months": n_months,
        })

    # Theme-level metrics (value-weighted across codes)
    theme_yoy: Optional[float] = None
    theme_accel: Optional[float] = None
    theme_confirmation = "neutral"
    theme_band: Optional[str] = None

    # Use the theme's dominant expected_direction for the theme-level read
    # (all codes in a theme should share the same direction; if mixed, use plurality)
    direction_counts: dict[str, int] = {}
    for cd in code_details:
        d = cd.get("expected_direction", "rising_imports_confirms")
        direction_counts[d] = direction_counts.get(d, 0) + 1
    theme_direction = max(direction_counts, key=direction_counts.get) if direction_counts else "rising_imports_confirms"

    if total_weight > 0:
        theme_yoy = weighted_yoy_sum / total_weight
        theme_accel = weighted_accel_sum / total_weight if total_weight > 0 else None
        theme_confirmation, theme_band = _sign_reading(theme_yoy, theme_accel, theme_direction)

    # Coverage notes
    n_configured = len(theme_codes)
    cov_note_en = (
        f"{codes_with_data}/{n_configured} HS codes have data"
        + (f"; most recent month: {max_month}" if max_month else "")
        + (". No data — run census_trade collector with CENSUS_API_KEY." if codes_with_data == 0 else "")
    )
    cov_note_zh = (
        f"已配置{n_configured}个HS编码中{codes_with_data}个有数据"
        + (f"；最新数据月份：{max_month}" if max_month else "")
        + ("；无数据——请设置CENSUS_API_KEY并运行普查贸易数据采集器。" if codes_with_data == 0 else "。")
    )

    return {
        "theme_id": theme_id,
        "n_codes_configured": n_configured,
        "n_codes_with_data": codes_with_data,
        "stat_month_max": max_month,
        "expected_direction": theme_direction,
        "yoy_pct": round(theme_yoy, 2) if theme_yoy is not None else None,
        "accel_3m_vs_12m": round(theme_accel, 2) if theme_accel is not None else None,
        "confirmation": theme_confirmation,
        "magnitude_band": theme_band,
        "code_detail": code_details,
        "coverage_note": cov_note_en,
        "coverage_note_zh": cov_note_zh,
    }


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_theme_trade_flows(
    write_nw: bool = True,
    write_site: bool = True,
) -> dict:
    """
    Compute per-theme trade-flow rollups and write outputs.

    Returns the full NW artifact dict (regardless of write flags).
    Always returns (never raises) — tolerant; exits 0.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    as_of_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Load config
    try:
        codes = _load_codes()
    except Exception as exc:
        log.error("theme_trade_flows: failed to load codes config: %s", exc)
        return _honest_null_output(now_str, as_of_date, f"config load error: {exc}")

    # Group codes by theme
    by_theme: dict[str, list[dict]] = {}
    for code_cfg in codes:
        tid = code_cfg.get("theme_id", "unknown")
        by_theme.setdefault(tid, []).append(code_cfg)

    # Load parquet (honest null if absent)
    df = _load_parquet()

    themes_out: dict[str, dict] = {}

    for theme_id, theme_codes in sorted(by_theme.items()):
        if df is None or df.empty:
            # No data at all — emit honest null for every theme
            n = len(theme_codes)
            themes_out[theme_id] = {
                "theme_id": theme_id,
                "n_codes_configured": n,
                "n_codes_with_data": 0,
                "stat_month_max": None,
                "expected_direction": theme_codes[0].get("expected_direction", "rising_imports_confirms") if theme_codes else None,
                "yoy_pct": None,
                "accel_3m_vs_12m": None,
                "confirmation": "neutral",
                "magnitude_band": None,
                "code_detail": [],
                "coverage_note": (
                    f"No data available for {n} configured HS codes. "
                    "Requires CENSUS_API_KEY env var and initial backfill run."
                ),
                "coverage_note_zh": (
                    f"已配置{n}个HS编码，暂无数据。"
                    "需设置CENSUS_API_KEY环境变量并执行首次历史数据回填。"
                ),
            }
        else:
            themes_out[theme_id] = _rollup_theme(theme_id, theme_codes, df)

    # Coverage stats
    themes_with_data = sum(1 for t in themes_out.values() if t.get("n_codes_with_data", 0) > 0)
    total_codes = sum(t.get("n_codes_configured", 0) for t in themes_out.values())
    codes_with_data = sum(t.get("n_codes_with_data", 0) for t in themes_out.values())

    # Build NW artifact
    nw_artifact = {
        "schema": "theme_trade_flows.v1",
        "as_of": as_of_date,
        "generated_at": now_str,
        "authority": AUTHORITY,
        "honesty_header": (
            "Physical import-flow context derived from US Census International Trade API. "
            "Display/context only. Not a scored factor. Not a buy/sell signal. "
            "Sign logic: rising_imports_confirms = more imports = theme-demand evidence; "
            "falling_imports_confirms = import decline = domestic-substitution evidence. "
            "Threshold: |YoY%| < 5% reads as neutral. "
            "No composite across themes — each theme is independent."
        ),
        "coverage_stats": {
            "total_themes": len(themes_out),
            "themes_with_data": themes_with_data,
            "total_codes_configured": total_codes,
            "codes_with_data": codes_with_data,
            "parquet_absent": df is None,
        },
        "api_note": (
            "Source: Census International Trade API (api.census.gov/data/timeseries/intltrade/imports/hs). "
            "Requires CENSUS_API_KEY (NOT keyless — verified 2026-07-09). "
            "Data since 2018-01 (backfill). Census trade data lags ~6 weeks."
        ),
        "themes": themes_out,
    }

    # Site projection (compact — drop code_detail for bandwidth)
    site_artifact = _build_site_projection(nw_artifact)

    # Write outputs
    if write_nw:
        try:
            _NW_OUT.parent.mkdir(parents=True, exist_ok=True)
            with open(_NW_OUT, "w", encoding="utf-8") as fh:
                json.dump(nw_artifact, fh, indent=2, ensure_ascii=False)
            log.info("theme_trade_flows: wrote NW artifact to %s", _NW_OUT)
        except Exception as exc:
            log.error("theme_trade_flows: NW artifact write failed: %s", exc)

    if write_site:
        try:
            _SITE_OUT.parent.mkdir(parents=True, exist_ok=True)
            with open(_SITE_OUT, "w", encoding="utf-8") as fh:
                json.dump(site_artifact, fh, indent=2, ensure_ascii=False)
            log.info("theme_trade_flows: wrote site projection to %s", _SITE_OUT)
        except Exception as exc:
            log.error("theme_trade_flows: site projection write failed: %s", exc)

    return nw_artifact


# ---------------------------------------------------------------------------
# Site projection (compact; drops code_detail)
# ---------------------------------------------------------------------------

def _build_site_projection(nw: dict) -> dict:
    """Build compact site projection from the full NW artifact."""
    compact_themes: dict[str, dict] = {}
    for theme_id, t in nw.get("themes", {}).items():
        compact_themes[theme_id] = {
            "theme_id": theme_id,
            "n_codes_configured": t.get("n_codes_configured"),
            "n_codes_with_data": t.get("n_codes_with_data"),
            "stat_month_max": t.get("stat_month_max"),
            "yoy_pct": t.get("yoy_pct"),
            "accel_3m_vs_12m": t.get("accel_3m_vs_12m"),
            "confirmation": t.get("confirmation"),
            "magnitude_band": t.get("magnitude_band"),
            "coverage_note": t.get("coverage_note"),
            "coverage_note_zh": t.get("coverage_note_zh"),
        }

    return {
        "schema": "theme_trade_flows.v1",
        "as_of": nw.get("as_of"),
        "generated_at": nw.get("generated_at"),
        "authority": nw.get("authority"),
        "honesty_header": nw.get("honesty_header"),
        "coverage_stats": nw.get("coverage_stats"),
        "themes": compact_themes,
    }


# ---------------------------------------------------------------------------
# Honest null output (when config fails or data completely absent)
# ---------------------------------------------------------------------------

def _honest_null_output(now_str: str, as_of_date: str, reason: str) -> dict:
    return {
        "schema": "theme_trade_flows.v1",
        "as_of": as_of_date,
        "generated_at": now_str,
        "authority": AUTHORITY,
        "honesty_header": "No data available — see coverage_stats.error for details.",
        "coverage_stats": {
            "total_themes": 0,
            "themes_with_data": 0,
            "total_codes_configured": 0,
            "codes_with_data": 0,
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
    parser = argparse.ArgumentParser(description="Theme trade-flow rollup engine (TIL W8)")
    parser.add_argument("--no-write-nw", action="store_true",
                        help="Skip writing data/neuralweb/theme_trade_flows.json")
    parser.add_argument("--no-write-site", action="store_true",
                        help="Skip writing site/basketdata/trade_flows.json")
    args = parser.parse_args()

    result = compute_theme_trade_flows(
        write_nw=not args.no_write_nw,
        write_site=not args.no_write_site,
    )
    stats = result.get("coverage_stats", {})
    print(
        f"theme_trade_flows: {stats.get('themes_with_data', 0)}/{stats.get('total_themes', 0)} "
        f"themes with data, {stats.get('codes_with_data', 0)}/{stats.get('total_codes_configured', 0)} codes"
    )
