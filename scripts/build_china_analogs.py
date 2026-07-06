"""Build the China historical regime analog finder.

Finds the k=12 nearest historical dates (by feature-space distance) to today's
regime reading.  DISPLAY-ONLY — no signals, no scores, no predictions.
Emits site/china_intel/analogs.json with schema china_intel.analogs.v1.

Feature vector (see METHOD_NOTE below):
  - z-scored growth_score + inflation_score (full-history z, population stats)
  - one-hot categorical mismatch: quad / liquidity / cycle (each mismatch = 1.0)

Distance: Euclidean over the combined feature vector.
Constraints:
  - Time-exclusion: candidates must be >=120 calendar days before query date.
  - Greedy diversity: skip candidates within 60 calendar days of an already-
    selected analog.
  - Rows with NaN quad, NaN growth_score, or NaN inflation_score are excluded
    from both candidacy and querying.

Forward paths:
  - SHCOMP (000001.SS): +20/+60/+120 trading sessions forward log return,
    anchored to the first close strictly after the analog date (PIT).
  - CSI300 ETF (510300.SS): same, or null when the analog predates its listing.
  - Off-history windows return null (never truncated numbers).

Callable standalone: python -m scripts.build_china_analogs
Callable from build_china.py sub-builder loop.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
K = 12
TIME_EXCLUSION_DAYS = 120   # calendar days before query to exclude candidates
DIVERSITY_DAYS = 60         # calendar days — skip if within an already-selected analog
SCHEMA = "china_intel.analogs.v1"

METHOD_NOTE = (
    "Feature vector: z-scored growth_score and inflation_score (population z "
    "over all valid candidate rows) plus one-hot categorical distance for quad, "
    "liquidity, and cycle (each mismatched category contributes 1.0 to the "
    "Euclidean distance). Weighting is fixed and undifferentiated across the "
    "five dimensions. Neighbors selected by greedy Euclidean nearest-neighbor "
    "with time-exclusion >=120 calendar days and intra-result diversity >=60 "
    "calendar days. Forward paths use PIT-anchored first close strictly after "
    "the analog date; off-history windows return null."
)

DISCLAIMER_EN = (
    "DISPLAY ONLY. Historical analogs are descriptive summaries of past regime "
    "similarity. They are not signals, forecasts, or recommendations. Past market "
    "paths under similar regimes do not predict future returns."
)
DISCLAIMER_ZH = (
    "仅供展示。历史相似情景是对过去制度相似性的描述性总结，不构成任何信号、预测或投资建议。"
    "过去在类似制度下的市场走势不代表未来收益。"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _root() -> Path:
    """Repo root: parent of this scripts/ directory."""
    return Path(__file__).resolve().parent.parent


def _site_china_intel() -> Path:
    try:
        from lib import config
        cfg = config.load()
        sd = cfg["storage"]["site_dir"]
        base = Path(sd) if Path(sd).is_absolute() else (_root() / sd)
    except Exception:  # noqa: BLE001
        base = _root() / "site"
    d = base / "china_intel"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_regime(root: Path) -> pd.DataFrame | None:
    p = root / "data" / "china_regime" / "regime_history.parquet"
    if not p.exists():
        log.warning("regime_history.parquet not found at %s", p)
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    return df


def _load_price(root: Path, ticker: str) -> pd.Series | None:
    p = root / "data" / "china" / f"{ticker}.parquet"
    if not p.exists():
        log.warning("%s.parquet not found at %s", ticker, p)
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    col = "close"
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten if MultiIndex (some Yahoo stores have Price level)
        df.columns = [c[-1] if isinstance(c, tuple) else c for c in df.columns]
    if col not in df.columns:
        log.warning("%s.parquet has no 'close' column: %s", ticker, df.columns.tolist())
        return None
    return df[col].sort_index()


def _is_valid_row(row: pd.Series) -> bool:
    """True if the row can participate as a candidate or query."""
    quad = row.get("quad")
    g = row.get("growth_score")
    inf = row.get("inflation_score")
    if pd.isna(quad) or quad in ("", "unknown", "None"):
        return False
    if pd.isna(g) or pd.isna(inf):
        return False
    return True


def _build_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Return the subset of df that are valid candidates (no NaN quad or scores)."""
    mask = df.apply(_is_valid_row, axis=1)
    return df.loc[mask].copy()


def _z_stats(candidates: pd.DataFrame) -> tuple[float, float, float, float]:
    """Population mean+std for growth and inflation over the candidate set."""
    g_mean = float(candidates["growth_score"].mean())
    g_std = float(candidates["growth_score"].std(ddof=0))
    i_mean = float(candidates["inflation_score"].mean())
    i_std = float(candidates["inflation_score"].std(ddof=0))
    # Guard against zero-std (degenerate history)
    if g_std == 0 or math.isnan(g_std):
        g_std = 1.0
    if i_std == 0 or math.isnan(i_std):
        i_std = 1.0
    return g_mean, g_std, i_mean, i_std


def _feature_vector(
    row: pd.Series,
    g_mean: float, g_std: float,
    i_mean: float, i_std: float,
    query_quad: str, query_liq: str, query_cycle: str,
) -> np.ndarray:
    """5-dim feature: [gz, iz, quad_mismatch, liq_mismatch, cycle_mismatch]."""
    gz = (float(row["growth_score"]) - g_mean) / g_std
    iz = (float(row["inflation_score"]) - i_mean) / i_std
    quad_mm = 0.0 if row["quad"] == query_quad else 1.0
    liq_mm = 0.0 if row["liquidity"] == query_liq else 1.0
    cyc_mm = 0.0 if row["cycle"] == query_cycle else 1.0
    return np.array([gz, iz, quad_mm, liq_mm, cyc_mm], dtype=float)


def _fwd_log_return(
    price: pd.Series | None,
    anchor_date: pd.Timestamp,
    sessions: int,
) -> float | None:
    """
    Log return from the first close strictly after anchor_date to the close
    sessions trading days later.  Returns None if price series is missing,
    anchor predates the series start (pre-listing PIT guard), anchor falls at or
    past the series end, or the forward window extends past history.

    Pre-listing PIT guard: if anchor_date < price.index.min(), the series has
    not started yet — returning a forward return would silently anchor to the
    listing date, fabricating lookahead returns.  Return None instead.
    """
    if price is None:
        return None
    # PIT guard: anchor predates the price series start
    if anchor_date < price.index.min():
        return None
    after = price.loc[price.index > anchor_date]
    if len(after) == 0:
        return None                          # anchor at or past end of price history
    start_close = float(after.iloc[0])
    if sessions >= len(after):
        return None                          # forward window extends past history
    end_close = float(after.iloc[sessions])
    if start_close <= 0 or end_close <= 0:
        return None
    return round(math.log(end_close / start_close), 6)


def _fwd_paths(
    anchor_date: pd.Timestamp,
    shcomp: pd.Series | None,
    csi300: pd.Series | None,
) -> tuple[dict, dict | None]:
    """Return (fwd_shcomp, fwd_csi300) dicts.  csi300 is None if not available."""
    h20 = _fwd_log_return(shcomp, anchor_date, 20)
    h60 = _fwd_log_return(shcomp, anchor_date, 60)
    h120 = _fwd_log_return(shcomp, anchor_date, 120)
    fwd_sh = {"h20": h20, "h60": h60, "h120": h120}

    # CSI300 only if any window is available (i.e. price series covers the date).
    # PIT guard: anchor must be >= series start AND have subsequent closes.
    # Without the pre-listing guard, an analog predating 2012-05-04 (510300.SS
    # inception) would silently anchor to the listing-day close — fabricating
    # forward returns from a date 185-1433 days after the analog.
    if csi300 is not None:
        if anchor_date < csi300.index.min():
            fwd_csi = None   # analog predates CSI300 listing (PIT violation)
        else:
            after = csi300.loc[csi300.index > anchor_date]
            if len(after) == 0:
                fwd_csi = None   # anchor at/past end of CSI300 price history
            else:
                c20 = _fwd_log_return(csi300, anchor_date, 20)
                c60 = _fwd_log_return(csi300, anchor_date, 60)
                c120 = _fwd_log_return(csi300, anchor_date, 120)
                fwd_csi: dict | None = {"h20": c20, "h60": c60, "h120": c120}
    else:
        fwd_csi = None

    return fwd_sh, fwd_csi


def _fan_stats(analogs: list[dict]) -> dict:
    """Compute p25/median/p75/n of fwd_shcomp paths across analogs."""
    result: dict = {}
    for horizon in ("h20", "h60", "h120"):
        vals = [a["fwd_shcomp"][horizon] for a in analogs if a["fwd_shcomp"][horizon] is not None]
        n = len(vals)
        if n == 0:
            result[horizon] = {"p25": None, "median": None, "p75": None, "n": 0}
        else:
            arr = np.array(vals, dtype=float)
            result[horizon] = {
                "p25": round(float(np.percentile(arr, 25)), 6),
                "median": round(float(np.percentile(arr, 50)), 6),
                "p75": round(float(np.percentile(arr, 75)), 6),
                "n": n,
            }
    return result


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _find_analogs(
    regime: pd.DataFrame,
    shcomp: pd.Series | None,
    csi300: pd.Series | None,
    k: int = K,
) -> dict[str, Any]:
    """Return the full analogs payload dict (or raise on logic errors)."""

    candidates = _build_candidates(regime)
    n_candidate_days = len(candidates)
    coverage_start = str(candidates.index.min().date()) if n_candidate_days else None
    coverage_end = str(candidates.index.max().date()) if n_candidate_days else None

    if n_candidate_days == 0:
        raise ValueError("No valid candidate rows after filtering NaN quad/scores")

    # Query = latest valid day (latest regime row that passes validity)
    valid_regime = _build_candidates(regime)
    if len(valid_regime) == 0:
        raise ValueError("No valid query row: all rows have NaN quad or scores")
    query_row = valid_regime.iloc[-1]
    query_date = query_row.name  # Timestamp

    g_mean, g_std, i_mean, i_std = _z_stats(candidates)

    query_gz = (float(query_row["growth_score"]) - g_mean) / g_std
    query_iz = (float(query_row["inflation_score"]) - i_mean) / i_std

    query_info: dict = {
        "date": str(query_date.date()),
        "quad": str(query_row["quad"]),
        "quad_name": str(query_row["quad_name"]),
        "liquidity": str(query_row["liquidity"]),
        "cycle": str(query_row["cycle"]),
        "growth_z": round(query_gz, 4),
        "inflation_z": round(query_iz, 4),
    }

    # Exclude candidates within TIME_EXCLUSION_DAYS of query
    cutoff = query_date - pd.Timedelta(days=TIME_EXCLUSION_DAYS)
    pool = candidates.loc[candidates.index <= cutoff].copy()

    if len(pool) == 0:
        return {
            "query": query_info,
            "analogs": [],
            "fan": {h: {"p25": None, "median": None, "p75": None, "n": 0}
                    for h in ("h20", "h60", "h120")},
            "coverage": {
                "start": coverage_start,
                "end": coverage_end,
                "n_candidate_days": n_candidate_days,
            },
        }

    # Build feature vectors for entire pool
    query_vec = np.array([
        query_gz, query_iz,
        0.0,   # same as self for categoricals (irrelevant — just for shape)
        0.0,
        0.0,
    ], dtype=float)

    pool_vecs = np.array([
        _feature_vector(
            row,
            g_mean, g_std, i_mean, i_std,
            query_row["quad"], query_row["liquidity"], query_row["cycle"],
        )
        for _, row in pool.iterrows()
    ], dtype=float)

    # Euclidean distances
    diffs = pool_vecs - query_vec
    distances = np.sqrt((diffs ** 2).sum(axis=1))

    # Sort by distance ascending
    order = np.argsort(distances)
    sorted_dates = pool.index[order]
    sorted_dists = distances[order]
    sorted_rows = pool.iloc[order]

    # Greedy diversity selection
    selected: list[pd.Timestamp] = []
    analog_records: list[dict] = []

    for idx, (date, dist, (_, row)) in enumerate(
        zip(sorted_dates, sorted_dists, sorted_rows.iterrows())
    ):
        if len(selected) >= k:
            break
        # Diversity check: skip if within DIVERSITY_DAYS of any already-selected
        too_close = any(
            abs((date - sel).days) < DIVERSITY_DAYS
            for sel in selected
        )
        if too_close:
            continue

        selected.append(date)
        fwd_sh, fwd_csi = _fwd_paths(date, shcomp, csi300)
        analog_records.append({
            "date": str(date.date()),
            "distance": round(float(dist), 4),
            "quad": str(row["quad"]),
            "quad_name": str(row["quad_name"]) if not pd.isna(row.get("quad_name", None)) else None,
            "liquidity": str(row["liquidity"]),
            "cycle": str(row["cycle"]),
            "fwd_shcomp": fwd_sh,
            "fwd_csi300": fwd_csi,
        })

    fan = _fan_stats(analog_records)

    return {
        "coverage": {
            "start": coverage_start,
            "end": coverage_end,
            "n_candidate_days": n_candidate_days,
        },
        "query": query_info,
        "analogs": analog_records,
        "fan": fan,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build() -> int:
    """
    Main entry point.  Writes site/china_intel/analogs.json.
    Never raises into the orchestrator; logs errors and returns 0.
    """
    root = _root()
    try:
        regime = _load_regime(root)
        if regime is None:
            log.error("build_china_analogs: regime_history.parquet missing; skipping")
            return 0

        shcomp = _load_price(root, "000001.SS")
        csi300 = _load_price(root, "510300.SS")

        payload = _find_analogs(regime, shcomp, csi300)

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        as_of = payload["query"]["date"]

        out: dict = {
            "schema": SCHEMA,
            "is_context_only": True,
            "generated_utc": now_utc,
            "as_of": as_of,
            "coverage": payload["coverage"],
            "query": payload["query"],
            "analogs": payload["analogs"],
            "fan": payload["fan"],
            "method_note": METHOD_NOTE,
            "disclaimer_en": DISCLAIMER_EN,
            "disclaimer_zh": DISCLAIMER_ZH,
        }

        out_path = _site_china_intel() / "analogs.json"
        out_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2, default=str)
        )
        log.info(
            "build_china_analogs: wrote %s (%d analogs, as_of %s)",
            out_path, len(payload["analogs"]), as_of,
        )
    except Exception as e:  # noqa: BLE001 — never fatal
        log.error("build_china_analogs: failed (%s); skipping", e, exc_info=True)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return build()


if __name__ == "__main__":
    import sys
    sys.exit(main())
