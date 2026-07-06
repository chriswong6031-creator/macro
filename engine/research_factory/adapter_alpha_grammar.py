"""engine.research_factory.adapter_alpha_grammar — Alpha grammar adapter (W3, RF-13).

READS survivors from the BH-FDR output; ROUTES families, not formula noise.

Sources:
  data/research/alpha_candidates.parquet  — BH-FDR survivors (fdr_reject==True)
  data/research/alpha_clusters.json       — cluster membership + net_new_info

RF-13 (Alpha grammar seam):
  - Tracks FAMILIES and survivors (cluster representatives), not individual
    formula formulas.
  - net_new_info is metadata only — NEVER a rank input (FR-1/FR-6 inherited).
  - Both source files are absent-safe: returns [] when either file is missing.

Lazy pandas import: pandas is only imported inside functions that need it,
never at module level.  Falls back to [] on any import/read error.

Pure stdlib at module level; pandas only in-function.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cluster loader (absent-safe)
# ---------------------------------------------------------------------------

def _load_clusters(data_dir: Path) -> list[dict]:
    """Load alpha_clusters.json absent-safely.  Returns [] on any error."""
    path = data_dir / "research" / "alpha_clusters.json"
    if not path.exists():
        log.debug("alpha_clusters.json not found at %s", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        clusters = raw.get("clusters") or []
        if not isinstance(clusters, list):
            log.warning("alpha_clusters.json: 'clusters' is not a list")
            return []
        return clusters
    except Exception as exc:  # noqa: BLE001
        log.warning("_load_clusters: failed to parse %s: %s", path, exc)
        return []


# ---------------------------------------------------------------------------
# Survivors loader (absent-safe, lazy pandas)
# ---------------------------------------------------------------------------

def _load_survivors(data_dir: Path) -> list[dict]:
    """Load alpha_candidates.parquet and return fdr_reject==True rows.

    Uses lazy pandas import.  Returns [] when the file is absent or pandas
    is unavailable.

    Returns list of dicts with keys matching the parquet columns.
    """
    path = data_dir / "research" / "alpha_candidates.parquet"
    if not path.exists():
        log.debug("alpha_candidates.parquet not found at %s", path)
        return []
    try:
        import pandas as pd  # lazy import
    except ImportError:
        log.warning("_load_survivors: pandas not available — returning []")
        return []
    try:
        df = pd.read_parquet(path)
        if "fdr_reject" not in df.columns:
            log.warning("alpha_candidates.parquet: 'fdr_reject' column missing")
            return []
        survivors = df[df["fdr_reject"] == True]  # noqa: E712
        return survivors.to_dict(orient="records")
    except Exception as exc:  # noqa: BLE001
        log.warning("_load_survivors: failed to load %s: %s", path, exc)
        return []


# ---------------------------------------------------------------------------
# Family builder
# ---------------------------------------------------------------------------

def _build_family_map(
    survivors: list[dict],
    clusters: list[dict],
) -> dict[str, dict]:
    """Build a family_id → family-summary map from survivors + clusters.

    Each family is keyed by family name (from alpha_candidates 'family' field).
    Within each family, survivors are collected.  net_new_info is stored as
    cluster metadata only — never used as a rank input.

    Returns dict: family_name → {
        "family": str,
        "survivors": list[dict],  — survivor rows (alpha_id, mechanism_hypothesis, dsr, ...)
        "cluster_representatives": list[str],  — cluster-representative alpha_ids
        "net_new_info": dict,  — alpha_id → net_new_info (METADATA ONLY, not rank)
        "n_survivors": int,
    }
    """
    # Build net_new_info lookup from clusters
    net_new_info_map: dict[str, float] = {}
    cluster_reps: list[str] = []
    for cluster in clusters:
        rep = cluster.get("representative_alpha_id")
        if rep:
            cluster_reps.append(rep)
        for member in cluster.get("members") or []:
            aid = member.get("alpha_id")
            nni = member.get("net_new_info")
            if aid and nni is not None:
                net_new_info_map[aid] = float(nni)

    # Group survivors by family
    family_map: dict[str, dict] = {}
    for row in survivors:
        fam = row.get("family") or "unknown"
        if fam not in family_map:
            family_map[fam] = {
                "family": fam,
                "survivors": [],
                "cluster_representatives": [],
                "net_new_info": {},  # METADATA ONLY — never a rank input (RF-13)
                "n_survivors": 0,
            }
        aid = row.get("alpha_id")
        family_map[fam]["survivors"].append({
            "alpha_id": aid,
            "mechanism_hypothesis": row.get("mechanism_hypothesis"),
            "dsr": row.get("dsr"),
            "mean_ic": row.get("mean_ic"),
            "t_hac": row.get("t_hac"),
            "survivorship_caveat": row.get("survivorship_caveat"),
            "overlap_cluster": row.get("overlap_cluster"),
            "cluster_representative": row.get("cluster_representative"),
            "fdr_reject": row.get("fdr_reject"),
        })
        family_map[fam]["n_survivors"] += 1
        if aid:
            nni = net_new_info_map.get(aid)
            if nni is not None:
                family_map[fam]["net_new_info"][aid] = nni
        if aid and aid in cluster_reps:
            family_map[fam]["cluster_representatives"].append(aid)

    return family_map


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route_all(
    data_dir: Path | None = None,
) -> list[dict]:
    """Load alpha grammar survivors and produce family-level route results.

    Returns a list of family routing dicts.  Empty if either source file is
    absent or on any read error.

    Each returned dict has keys:
      family            : str — alpha grammar family name
      spec_ref          : str — family name (the factory's reference for this group)
      source            : 'alpha_grammar'
      n_survivors       : int — number of BH-FDR survivors in this family
      survivors         : list[dict] — survivor metadata rows
      cluster_reps      : list[str] — cluster-representative alpha_ids
      net_new_info      : dict — alpha_id → net_new_info (METADATA, not rank)
      trial_accounting  : dict — mode='read_only' (alpha grammar has no new trial family)
      note              : str
    """
    _dir = Path(data_dir) if data_dir else Path("data")

    survivors = _load_survivors(_dir)
    clusters = _load_clusters(_dir)

    if not survivors:
        log.debug("route_all: no alpha grammar survivors found — returning []")
        return []

    family_map = _build_family_map(survivors, clusters)

    results: list[dict] = []
    for fam_name, fam_data in family_map.items():
        results.append({
            "family": fam_name,
            "spec_ref": fam_name,
            "source": "alpha_grammar",
            "n_survivors": fam_data["n_survivors"],
            "survivors": fam_data["survivors"],
            "cluster_reps": fam_data["cluster_representatives"],
            # net_new_info: stored as metadata; NEVER used as rank input (RF-13/FR-1/FR-6)
            "net_new_info": fam_data["net_new_info"],
            "trial_accounting": {
                "mode": "read_only",
                "family": None,
                "declared_at": None,
            },
            "note": (
                "net_new_info is cluster metadata only — never a rank input "
                "(RF-13; FR-1/FR-6 inherited). Tracks families and survivors, "
                "not individual formula noise."
            ),
        })

    return results
