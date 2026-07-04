"""Oracle B1 — Sector-personality classification layer.

Classifies each panel node on trailing history into one of:
  {mean_reverter, trender, rate_proxy, idiosyncratic, mixed}

These are STATISTICAL CLASSIFICATIONS derived from observed price-relative
history.  They are DESCRIPTIVE/DISPLAY tier — they describe historical
response-type, not what the node will do next.  All classifications must be
labeled accordingly wherever they are displayed.

Metrics computed per node (requires ≥ MIN_HISTORY_DAYS trading days):
  trend_persistence   — lag-20 autocorrelation of the rs series
  reversion_strength  — AR(1) coefficient of 20-day changes in rs (negative = mean-reverting)
  rate_beta           — Pearson correlation of rs-change (20d) with tlt_ret_10d
  idiosyncrasy        — 1 − R² of node rs-change vs its complex-mean rs-change;
                        unmapped nodes get 1.0 (fully idiosyncratic by definition)

Classification thresholds (all provenance-commented):
  mean_reverter   — reversion_strength < THRESH_REVERSION (AR(1) < −0.10)
  trender         — trend_persistence > THRESH_TREND (acf20 > 0.15)
  rate_proxy      — |rate_beta| > THRESH_RATE (|corr| > 0.40)
  idiosyncratic   — idiosyncrasy > THRESH_IDIOSYNCRASY (1−R² > 0.70)
  mixed           — none of the above

Rules are evaluated in priority order: mean_reverter > trender > rate_proxy >
idiosyncratic > mixed.  A node can only hold one class.

Output: data/oracle/personality.json — a dict mapping node → personality class.
  This file is GITIGNORED (mirrors panel_*.parquet pattern — heavy local artifact).
  It is refreshed nightly as part of the oracle pipeline.

R4 binding (ORACLE_GAUNTLET_P3_ADJUDICATION.md):
  - Personality classes are statistical labels, not forecasts.
  - They must be labeled "descriptive/display" wherever displayed.
  - No personality class may feed any score, size, or gate.

Usage (CLI):
  python -m scripts.build_oracle_personality --data-dir PATH
  (wired as Step 3b in oracle_nightly.py, after episodes, before state)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — all thresholds are provenance-commented
# ---------------------------------------------------------------------------

# Minimum trading-day history required for classification (≥2y ≈ 504 days;
# using 500 for robustness against holiday gaps).
# Source: spec B1 "per node with ≥2y history".
MIN_HISTORY_DAYS: int = 500

# AR(1) coefficient of 20d rs-changes below this → mean_reverter.
# Source: spec B1 "reversion_strength < −0.1 → mean_reverter".
THRESH_REVERSION: float = -0.10

# Lag-20 autocorrelation of rs above this → trender.
# Source: spec B1 "trend_persistence > 0.15 → trender".
THRESH_TREND: float = 0.15

# |Pearson correlation of rs-change (20d) with tlt_ret_10d| above this → rate_proxy.
# Source: spec B1 "|rate_beta| > 0.4 → rate_proxy".
THRESH_RATE: float = 0.40

# 1 − R² of node rs-change vs complex-mean rs-change above this → idiosyncratic.
# Source: spec B1 "idiosyncrasy > 0.7 → idiosyncratic".
THRESH_IDIOSYNCRASY: float = 0.70

# Rolling window for the 20d rs-change used in reversion_strength + rate_beta.
RS_CHANGE_WINDOW: int = 20  # trading days; matches spec wording "20d rs-changes"

# Number of lag steps for trend_persistence autocorrelation.
# Source: spec B1 "lag-20 autocorrelation".
TREND_ACF_LAG: int = 20

# Classification priority order (first match wins).
# Source: spec B1 "mean_reverter / trender / rate_proxy / idiosyncratic / mixed".
_PRIORITY = ["mean_reverter", "trender", "rate_proxy", "idiosyncratic", "mixed"]

# Bilingual label map — display only.
LABEL_ZH: dict[str, str] = {
    "mean_reverter": "均值回归型",
    "trender": "趋势跟踪型",
    "rate_proxy": "利率代理型",
    "idiosyncratic": "特异型",
    "mixed": "混合型",
}
LABEL_DESCRIPTION_EN: dict[str, str] = {
    "mean_reverter": (
        "Historically shows negative AR(1) on RS-changes — "
        "relative-strength moves tend to reverse. Statistical classification only."
    ),
    "trender": (
        "Historically shows positive lag-20 RS autocorrelation — "
        "relative-strength moves tend to persist. Statistical classification only."
    ),
    "rate_proxy": (
        "Historically shows high correlation between RS-changes and TLT returns — "
        "relative strength co-moves with interest-rate direction. Statistical classification only."
    ),
    "idiosyncratic": (
        "Historically moves independently of its complex mean — "
        "systematic rotation patterns are weak for this node. Statistical classification only."
    ),
    "mixed": (
        "No dominant personality pattern detected on trailing history. "
        "Statistical classification only."
    ),
}


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _acf_lag_k(series: pd.Series, k: int) -> float | None:
    """Lag-k autocorrelation of a series.  Returns None if insufficient data."""
    clean = series.dropna()
    if len(clean) < k + 30:  # need some headroom
        return None
    # Manual lag-k Pearson (no scipy needed)
    x = clean.iloc[:-k].values
    y = clean.iloc[k:].values
    if len(x) < 10:
        return None
    mx, my = x.mean(), y.mean()
    sx, sy = x.std(), y.std()
    if sx < 1e-10 or sy < 1e-10:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _ar1_coef(series: pd.Series) -> float | None:
    """AR(1) coefficient of a series via OLS (numpy only, no scipy)."""
    clean = series.dropna()
    if len(clean) < 30:
        return None
    x = clean.iloc[:-1].values
    y = clean.iloc[1:].values
    mx, my = x.mean(), y.mean()
    denom = np.sum((x - mx) ** 2)
    if denom < 1e-12:
        return None
    return float(np.sum((x - mx) * (y - my)) / denom)


def _pearson_corr(x: pd.Series, y: pd.Series) -> float | None:
    """Pearson correlation with alignment, NaN-safe."""
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 30:
        return None
    sx, sy = df["x"].std(), df["y"].std()
    if sx < 1e-10 or sy < 1e-10:
        return None
    return float(df["x"].corr(df["y"]))


def _r2_vs_complex_mean(node_rs_chg: pd.Series, complex_rs_chg: pd.Series) -> float | None:
    """R² of node rs_change regressed on complex mean rs_change.

    Uses numpy OLS.  Returns None if insufficient data.
    idiosyncrasy = 1 − R².
    """
    df = pd.DataFrame({"node": node_rs_chg, "cmplx": complex_rs_chg}).dropna()
    if len(df) < 30:
        return None
    sx = df["cmplx"].std()
    if sx < 1e-10:
        return None
    r = float(df["node"].corr(df["cmplx"]))
    return r * r  # R² = r²  (single regressor, no intercept needed for R² definition)


def _compute_node_stats(
    node_rs: pd.Series,
    node_rs_chg: pd.Series,
    tlt_ret: pd.Series,
    complex_rs_chg: pd.Series | None,
) -> dict[str, float | None]:
    """Compute the four B1 stats for a single node."""
    trend_persistence = _acf_lag_k(node_rs, TREND_ACF_LAG)
    reversion_strength = _ar1_coef(node_rs_chg)
    rate_beta = _pearson_corr(node_rs_chg, tlt_ret)
    if complex_rs_chg is not None:
        r2 = _r2_vs_complex_mean(node_rs_chg, complex_rs_chg)
        idiosyncrasy = (1.0 - r2) if r2 is not None else 1.0
    else:
        idiosyncrasy = 1.0  # unmapped nodes → fully idiosyncratic per spec
    return {
        "trend_persistence": trend_persistence,
        "reversion_strength": reversion_strength,
        "rate_beta": rate_beta,
        "idiosyncrasy": idiosyncrasy,
    }


def _classify(stats: dict[str, float | None]) -> str:
    """Classify a node based on computed stats.  Priority: mean_reverter first."""
    rev = stats.get("reversion_strength")
    trend = stats.get("trend_persistence")
    rate = stats.get("rate_beta")
    idio = stats.get("idiosyncrasy")

    if rev is not None and rev < THRESH_REVERSION:
        return "mean_reverter"
    if trend is not None and trend > THRESH_TREND:
        return "trender"
    if rate is not None and abs(rate) > THRESH_RATE:
        return "rate_proxy"
    if idio is not None and idio > THRESH_IDIOSYNCRASY:
        return "idiosyncratic"
    return "mixed"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_personality(
    data_dir: Path | str,
    rotation_groups_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build the personality classification for all panel nodes.

    Parameters
    ----------
    data_dir : Path | str
        Root data directory (contains oracle/ subdirectory).
    rotation_groups_path : Path | str | None
        Override path to rotation_groups.json.  Defaults to
        data_dir/oracle/rotation_groups.json.

    Returns
    -------
    dict — personality payload:
      {
        "schema": "oracle_personality.v1",
        "asof": "YYYY-MM-DD",
        "note": "DESCRIPTIVE/DISPLAY tier — statistical labels, not forecasts.",
        "thresholds": {...},
        "nodes": {
          "<node_id>": {
            "personality": str,
            "personality_zh": str,
            "description_en": str,
            "stats": {
              "trend_persistence": float | null,
              "reversion_strength": float | null,
              "rate_beta": float | null,
              "idiosyncrasy": float | null,
            },
            "n_obs": int,
            "insufficient_history": bool
          }, ...
        }
      }
    """
    data_dir = Path(data_dir)
    oracle_dir = data_dir / "oracle"

    # --- Load both panels (S = long ETF history; M = subsector coverage) ---
    # Merge: S-nodes take precedence for any node present in both.
    # Rationale: Tier S has 25+ year history, Tier M has ~5 years.
    frames: list[pd.DataFrame] = []
    for tier in ("s", "m"):
        p = oracle_dir / f"panel_{tier}.parquet"
        if p.exists():
            try:
                df_tier = pd.read_parquet(p)
                frames.append(df_tier)
                log.info("personality: loaded panel_%s (%d rows)", tier, len(df_tier))
            except Exception:  # noqa: BLE001
                log.warning("personality: could not load panel_%s", tier, exc_info=True)
    if not frames:
        log.warning("personality: no panel found — returning empty personality")
        return {
            "schema": "oracle_personality.v1",
            "asof": None,
            "note": "DESCRIPTIVE/DISPLAY tier — statistical labels, not forecasts.",
            "thresholds": _threshold_dict(),
            "nodes": {},
        }

    # Merge: for duplicate nodes, keep the one with more history (longer history wins).
    # Build a combined panel: concat all, then drop duplicates keeping the longer series.
    if len(frames) == 1:
        panel = frames[0]
    else:
        # Get the set of nodes in Tier S (long history); for those nodes, drop M rows.
        tier_s_nodes = set(frames[0].index.get_level_values("node").unique()) if frames else set()
        # Keep all Tier S rows + Tier M rows for nodes NOT in Tier S
        tier_m_filtered = frames[1][
            ~frames[1].index.get_level_values("node").isin(tier_s_nodes)
        ] if len(frames) > 1 else pd.DataFrame()
        panel = pd.concat([frames[0], tier_m_filtered]) if len(tier_m_filtered) > 0 else frames[0]
        log.info(
            "personality: merged panel — S_nodes=%d, M_only_nodes=%d",
            len(tier_s_nodes),
            len(tier_m_filtered.index.get_level_values("node").unique()) if len(tier_m_filtered) else 0,
        )

    # Establish asof from panel
    dates = panel.index.get_level_values("date")
    asof_str = str(pd.Timestamp(dates.max()).strftime("%Y-%m-%d"))

    # --- Load rotation_groups for complex mapping ---
    rg_path = rotation_groups_path or (oracle_dir / "rotation_groups.json")
    complex_map: dict[str, str] = {}  # node → complex_id
    complexes_def: list[dict] = []
    try:
        rg = json.loads(Path(rg_path).read_text()) if Path(rg_path).exists() else {}
        complexes_def = rg.get("complexes") or []
        for c in complexes_def:
            cid = c.get("id", "")
            for m in (c.get("members") or []):
                complex_map[str(m)] = cid
    except Exception:  # noqa: BLE001
        log.warning("personality: could not load rotation_groups", exc_info=True)

    # --- Precompute per-complex mean rs_change ---
    # rs_change = 20d change in rs; complex mean = average across members
    node_rs: dict[str, pd.Series] = {}
    node_rs_chg: dict[str, pd.Series] = {}
    node_tlt: dict[str, pd.Series] = {}

    nodes = panel.index.get_level_values("node").unique()
    for node in nodes:
        try:
            nd = panel.xs(node, level="node")
            nd = nd.sort_index()
            rs = nd["rs"].dropna()
            if len(rs) == 0:
                continue
            rs_chg = rs.diff(RS_CHANGE_WINDOW).dropna()
            # tlt_ret_10d is a shared macro series — use per-node column if available
            tlt = nd["tlt_ret_10d"].dropna() if "tlt_ret_10d" in nd.columns else pd.Series(dtype=float)
            node_rs[node] = rs
            node_rs_chg[node] = rs_chg
            node_tlt[node] = tlt
        except Exception:  # noqa: BLE001
            log.warning("personality: could not extract series for node %s", node, exc_info=True)

    # Build complex mean rs_chg per complex_id
    complex_mean_rs_chg: dict[str, pd.Series] = {}
    for c in complexes_def:
        cid = c.get("id", "")
        members = [m for m in (c.get("members") or []) if m in node_rs_chg]
        if not members:
            continue
        chg_df = pd.concat([node_rs_chg[m].rename(m) for m in members], axis=1)
        complex_mean_rs_chg[cid] = chg_df.mean(axis=1)

    # --- Classify each node ---
    result_nodes: dict[str, Any] = {}
    for node in nodes:
        rs = node_rs.get(node)
        rs_chg = node_rs_chg.get(node)
        tlt = node_tlt.get(node, pd.Series(dtype=float))
        n_obs = len(rs) if rs is not None else 0

        if n_obs < MIN_HISTORY_DAYS:
            result_nodes[str(node)] = {
                "personality": "mixed",
                "personality_zh": LABEL_ZH["mixed"],
                "description_en": LABEL_DESCRIPTION_EN["mixed"],
                "stats": {
                    "trend_persistence": None,
                    "reversion_strength": None,
                    "rate_beta": None,
                    "idiosyncrasy": None,
                },
                "n_obs": n_obs,
                "insufficient_history": True,
            }
            continue

        # Complex mean rs_chg for idiosyncrasy
        cid = complex_map.get(str(node))
        cmplx_rs_chg = complex_mean_rs_chg.get(cid) if cid else None

        stats = _compute_node_stats(rs, rs_chg, tlt, cmplx_rs_chg)
        personality = _classify(stats)

        result_nodes[str(node)] = {
            "personality": personality,
            "personality_zh": LABEL_ZH.get(personality, personality),
            "description_en": LABEL_DESCRIPTION_EN.get(personality, ""),
            "stats": {
                k: (round(float(v), 4) if v is not None else None)
                for k, v in stats.items()
            },
            "n_obs": n_obs,
            "insufficient_history": False,
        }

    log.info(
        "personality: classified %d nodes (sufficient history: %d, skipped: %d)",
        len(result_nodes),
        sum(1 for v in result_nodes.values() if not v.get("insufficient_history")),
        sum(1 for v in result_nodes.values() if v.get("insufficient_history")),
    )

    return {
        "schema": "oracle_personality.v1",
        "asof": asof_str,
        "note": (
            "DESCRIPTIVE/DISPLAY tier — statistical classifications from "
            "trailing history only.  Not forecasts.  Classifications refresh "
            "nightly but describe the node's historical RS response type."
        ),
        "thresholds": _threshold_dict(),
        "nodes": result_nodes,
    }


def _threshold_dict() -> dict:
    return {
        "min_history_days": MIN_HISTORY_DAYS,
        "thresh_reversion": THRESH_REVERSION,
        "thresh_trend": THRESH_TREND,
        "thresh_rate": THRESH_RATE,
        "thresh_idiosyncrasy": THRESH_IDIOSYNCRASY,
        "rs_change_window": RS_CHANGE_WINDOW,
        "trend_acf_lag": TREND_ACF_LAG,
        "priority": _PRIORITY,
    }


def write_personality(payload: dict, data_dir: Path | str) -> Path:
    """Write personality.json to data/oracle/.

    Returns the written path.  Degrade-never-raise.
    """
    data_dir = Path(data_dir)
    out_path = data_dir / "oracle" / "personality.json"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, separators=(",", ":"), default=str))
        log.info("personality: wrote %s (%d nodes)", out_path, len(payload.get("nodes", {})))
    except Exception:  # noqa: BLE001
        log.warning("personality: write failed", exc_info=True)
    return out_path


def flat_map(payload: dict) -> dict[str, str]:
    """Return a flat node→personality_class dict for use in live.py."""
    nodes = payload.get("nodes") or {}
    return {node: v["personality"] for node, v in nodes.items()}
