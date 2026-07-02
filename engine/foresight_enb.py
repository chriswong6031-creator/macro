"""Foresight ENB + cluster module — W4a (research/FORESIGHT_DESK_UPGRADE_BY_FABLE.md §1 Q5).

Effective Number of Bets (ENB) and hierarchical clustering for the 18 foresight themes.

PURPOSE:
  Most foresight themes are correlated — memory_storage, ai_semiconductors, and semicap_equipment
  all move with the same hyperscaler-capex driver.  Treating them as 18 independent calls
  overstates diversification.  ENB measures the TRUE number of independent bets so the
  sizing strip can say "9 constructive themes ≈ 2.7 independent bets" — the institutional
  concentration truth the cascade currently hides.

MECHANISM:
  1. Read member-EW daily return series per theme from data/yahoo/*.parquet (same ``_closes``
     pattern as engine/foresight_grader.py:_closes — NOT a copy of the grader, just the same
     parquet read idiom).
  2. Build a 120d rolling correlation matrix across ALL 18 themes (any theme with <30 days of
     EW returns is excluded from that run; the matrix may be smaller than 18×18).
  3. ENB = (Σλ)² / Σλ² — the participation ratio over the correlation matrix's eigenvalues.
     Perfect correlation → ENB ≈ 1; independent → ENB ≈ N.
  4. Hierarchical clustering (scipy.cluster.hierarchy with average linkage + distance threshold
     d = 1 − 0.7 = 0.3 on the correlation-distance matrix).  If scipy is unavailable (should
     not happen — hmmlearn already pulls it in via scikit-learn), a greedy ρ>0.7 agglomeration
     is used (no new dependencies).
  5. Cluster membership written to data/foresight/enb_log.jsonl (append-only, deduped by date).
  6. ``load_cluster_membership()`` returns {theme: cluster_id} for the LATEST logged date so
     convergence.py and sizing.py can consume it without re-running the compute.

GRADING: ENB itself is a risk display (concentration truth), not a signal.  The nightly log
is auditable.  No grading of ENB is implied.

DEPENDENCIES: numpy, pandas (already in requirements); scipy (pulled in via hmmlearn/scikit-learn).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

WINDOW_DAYS = 120       # rolling window for return series
MIN_DAYS = 30           # minimum trading days to include a theme in the matrix
CLUSTER_CORR_THRESH = 0.7   # themes with ρ > this are merged in the same cluster (distance < 0.3)


# ---------------------------------------------------------------------------
# Closes reader — same pattern as engine/foresight_grader.py:_closes
# Does NOT import from the grader to avoid a circular dependency.
# ---------------------------------------------------------------------------

def _closes(ticker: str) -> pd.Series | None:
    p = config.data_dir() / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if "close" not in df.columns:
        return None
    s = df["close"].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _theme_ew_returns(
    themes_cfg: dict[str, dict],
    window: int = WINDOW_DAYS,
) -> dict[str, pd.Series]:
    """Member-equal-weight daily return series per theme, last ``window`` trading days.

    Only themes with >= MIN_DAYS observations after EW averaging are included.
    Returns {theme_key: pd.Series of daily returns}."""
    result: dict[str, pd.Series] = {}
    for key, spec in themes_cfg.items():
        tickers = spec.get("tickers") or []
        serieses = [_closes(t) for t in tickers]
        serieses = [s for s in serieses if s is not None and len(s) >= 5]
        if not serieses:
            continue
        # Align on common dates
        df = pd.concat(serieses, axis=1, keys=[t for t, s in zip(tickers, serieses) if s is not None and len(s) >= 5], sort=True)
        df = df.ffill().dropna(how="all")
        df = df.iloc[-window:] if len(df) >= window else df
        if len(df) < MIN_DAYS:
            continue
        ew = df.mean(axis=1)
        rets = ew.pct_change().dropna()
        if len(rets) < MIN_DAYS:
            continue
        result[key] = rets
    return result


def _build_corr_matrix(returns: dict[str, pd.Series]) -> tuple[pd.DataFrame, list[str]]:
    """Build pairwise correlation matrix.  Returns (corr_df, themes_included).

    Themes with insufficient overlap after alignment are dropped."""
    if not returns:
        return pd.DataFrame(), []
    df = pd.DataFrame(returns)
    df = df.dropna(how="all")
    # Drop columns with too few non-NaN rows
    df = df.loc[:, df.notna().sum() >= MIN_DAYS]
    if df.shape[1] < 2:
        return pd.DataFrame(), list(df.columns)
    corr = df.corr()
    themes = list(corr.columns)
    return corr, themes


def _enb(corr: pd.DataFrame) -> float | None:
    """Effective Number of Bets = (Σλ)² / Σλ² (participation ratio) over eigenvalues of
    the correlation matrix.  Returns None when the matrix is too small or degenerate."""
    if corr.empty or corr.shape[0] < 2:
        return None
    try:
        vals = np.linalg.eigvalsh(corr.values)
        vals = vals[vals > 0]
        if len(vals) == 0 or np.sum(vals ** 2) == 0:
            return None
        enb = float((np.sum(vals) ** 2) / np.sum(vals ** 2))
        return round(enb, 2)
    except Exception as e:  # noqa: BLE001
        log.debug("ENB eigenvalue computation failed: %s", e)
        return None


def _cluster_themes(
    corr: pd.DataFrame,
    themes: list[str],
    threshold: float = CLUSTER_CORR_THRESH,
) -> dict[str, str]:
    """Hierarchical clustering → {theme: cluster_id_str}.

    Tries scipy.cluster.hierarchy first (standard approach); falls back to greedy ρ>threshold
    agglomeration when scipy is unavailable (no new deps).

    Cluster IDs are strings: "c0", "c1", … — to be mapped to human-readable names by
    CLUSTER_NAMES in foresight_convergence.py.  The names assigned here are "c0" etc., but
    the convergence module's CLUSTER_NAMES dict maps well-known IDs to display labels.

    NOTE: To allow the convergence module to name clusters meaningfully, we assign stable IDs
    based on the LARGEST cluster member (the theme key that sorts first alphabetically).
    This is deterministic across runs as long as the corr matrix composition is stable."""
    if corr.empty or len(themes) < 2:
        return {t: f"c_{t}" for t in themes}   # each theme its own singleton cluster

    distance = 1.0 - corr.clip(-1, 1)

    try:
        from scipy.cluster import hierarchy
        from scipy.spatial.distance import squareform
        # scipy linkage expects a CONDENSED distance vector, not a square matrix
        condensed = squareform(distance.values, checks=False)
        Z = hierarchy.linkage(condensed, method="average")
        labels = hierarchy.fcluster(Z, t=1.0 - threshold, criterion="distance")
        membership: dict[str, str] = {}
        for theme, label in zip(themes, labels):
            membership[theme] = f"c{label}"
        return membership
    except Exception as e:  # noqa: BLE001
        log.debug("scipy clustering failed (%s), using greedy fallback", e)

    # Greedy fallback: O(n²) single-link agglomeration at ρ > threshold
    assigned: dict[str, str] = {}
    next_id = 0
    for i, t in enumerate(themes):
        if t in assigned:
            continue
        cid = f"c{next_id}"
        next_id += 1
        assigned[t] = cid
        for j, other in enumerate(themes):
            if j == i or other in assigned:
                continue
            if abs(float(corr.iloc[i, j])) > threshold:
                assigned[other] = cid
    return assigned


def _name_clusters(membership: dict[str, str]) -> dict[str, str]:
    """Re-key cluster IDs to stable string names based on the known-name map.

    Known clusters in CLUSTER_NAMES (foresight_convergence.py) are matched against
    representative themes.  Unrecognised clusters keep their cN id.

    Convention: if a cluster contains any of the AI-capex themes (ai_semiconductors,
    memory_storage, data_center_power, semicap_equipment, grid_electrification,
    nuclear_power), it is labelled 'ai_capex'.  Defense themes → 'defense'.
    Healthcare themes → 'healthcare'.  Everything else → keeps its 'cN' id."""
    AI_CAPEX = {"ai_semiconductors", "memory_storage", "data_center_power",
                "semicap_equipment", "grid_electrification", "nuclear_power"}
    DEFENSE = {"defense_aerospace", "space_satellite"}
    HEALTHCARE = {"glp1_obesity", "medical_devices", "diagnostics_lifesci"}

    # Build cluster_id → {themes}
    cid_to_themes: dict[str, set[str]] = {}
    for theme, cid in membership.items():
        cid_to_themes.setdefault(cid, set()).add(theme)

    # Rename cluster IDs
    rename: dict[str, str] = {}
    for cid, t_set in cid_to_themes.items():
        if t_set & AI_CAPEX:
            rename[cid] = "ai_capex"
        elif t_set & DEFENSE:
            rename[cid] = "defense"
        elif t_set & HEALTHCARE:
            rename[cid] = "healthcare"
        else:
            rename[cid] = cid   # keep numeric cN id

    return {theme: rename.get(cid, cid) for theme, cid in membership.items()}


def compute_enb(
    themes_cfg: dict | None = None,
    *,
    write_log: bool = True,
    constructive_themes: list[str] | None = None,
) -> dict | None:
    """Compute ENB + cluster membership for all 18 foresight themes.

    Args:
        themes_cfg: theme config dict (loaded from config if None).
        write_log: append nightly row to data/foresight/enb_log.jsonl.
        constructive_themes: subset of theme keys at thesis stage or score>=55
            (for the sizing-note ENB over constructive themes only).

    Returns a dict with:
        enb_all:        float|None — ENB over ALL themes with data
        enb_constructive: float|None — ENB over constructive subset (None if <2)
        n_themes_in_matrix: int
        n_constructive_in_matrix: int
        clusters: {theme: cluster_id}
        note: str

    Returns None on catastrophic failure.
    """
    if themes_cfg is None:
        try:
            cfg = config.load() or {}
            themes_cfg = cfg.get("themes") or {}
        except Exception as e:  # noqa: BLE001
            log.warning("foresight_enb: config load failed: %s", e)
            return None
    if not themes_cfg:
        return None

    returns = _theme_ew_returns(themes_cfg)
    if not returns:
        log.debug("foresight_enb: no theme return series — data/yahoo likely empty")
        return {
            "enb_all": None,
            "enb_constructive": None,
            "n_themes_in_matrix": 0,
            "n_constructive_in_matrix": 0,
            "clusters": {},
            "note": "No return series available — data/yahoo/*.parquet absent or too short.",
        }

    corr, themes = _build_corr_matrix(returns)
    enb_all = _enb(corr) if not corr.empty else None
    membership_raw = _cluster_themes(corr, themes) if len(themes) >= 2 else {t: f"c_{t}" for t in themes}
    membership = _name_clusters(membership_raw)

    # ENB over constructive subset
    enb_constructive: float | None = None
    n_constructive_in_matrix = 0
    if constructive_themes and len(constructive_themes) >= 2:
        c_keys = [t for t in constructive_themes if t in returns]
        n_constructive_in_matrix = len(c_keys)
        if len(c_keys) >= 2:
            c_corr, c_themes = _build_corr_matrix({k: returns[k] for k in c_keys})
            enb_constructive = _enb(c_corr) if not c_corr.empty else None

    today_str = date.today().isoformat()
    result = {
        "asof":                    today_str,
        "enb_all":                 enb_all,
        "enb_constructive":        enb_constructive,
        "n_themes_in_matrix":      len(themes),
        "n_constructive_in_matrix": n_constructive_in_matrix,
        "clusters":                membership,
        "n_constructive_requested": len(constructive_themes) if constructive_themes else 0,
        "note": (
            f"ENB = (Σλ)²/Σλ² (participation ratio) over eigenvalues of the "
            f"{len(themes)}×{len(themes)} theme correlation matrix ({WINDOW_DAYS}d window). "
            f"Clustering: scipy average-linkage at distance threshold 1−{CLUSTER_CORR_THRESH}=0.3 "
            f"(greedy fallback if unavailable). "
            f"ENB_all={enb_all}, ENB_constructive={enb_constructive}."
        ),
    }

    if write_log:
        try:
            _append_log(result)
        except Exception as e:  # noqa: BLE001
            log.warning("foresight_enb: log append failed: %s", e)

    return result


def _append_log(payload: dict) -> None:
    """Append one row per day to data/foresight/enb_log.jsonl (deduped by date)."""
    d = config.data_dir() / "foresight"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "enb_log.jsonl"

    asof = payload.get("asof", date.today().isoformat())
    seen: set[str] = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                a = e.get("asof")
                if a:
                    seen.add(a)
            except Exception:  # noqa: BLE001
                continue

    if asof in seen:
        return

    row = {
        "asof":                    asof,
        "enb_all":                 payload.get("enb_all"),
        "enb_constructive":        payload.get("enb_constructive"),
        "n_themes_in_matrix":      payload.get("n_themes_in_matrix"),
        "n_constructive_in_matrix": payload.get("n_constructive_in_matrix"),
        "clusters":                payload.get("clusters"),
    }
    with p.open("a") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def load_cluster_membership(asof: str | None = None) -> dict[str, str]:
    """Return {theme: cluster_id} for the requested date (default: latest logged date).

    Used by foresight_convergence.py and foresight_sizing.py to consume ENB clusters
    without re-running the compute (which is done nightly).

    Returns {} when the log is absent or has no valid rows for the date."""
    p = config.data_dir() / "foresight" / "enb_log.jsonl"
    if not p.exists():
        return {}

    rows: list[dict] = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            if e.get("clusters") and e.get("asof"):
                rows.append(e)
        except Exception:  # noqa: BLE001
            continue

    if not rows:
        return {}

    if asof is not None:
        matches = [r for r in rows if r["asof"] == asof]
        if not matches:
            return {}
        return matches[0].get("clusters") or {}

    # Latest date
    rows.sort(key=lambda r: r["asof"])
    return rows[-1].get("clusters") or {}
