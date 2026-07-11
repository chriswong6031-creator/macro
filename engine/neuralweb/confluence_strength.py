"""engine.neuralweb.confluence_strength — Deterministic confluence strength scorer (R-V4-6).

PURPOSE
-------
For each (subject, as_of, direction, horizon) event visible in the confluence graph,
compute:

  n_confirming_raw         — count of distinct engine families that fired this event
  n_independent_confirming — float; partial credit applied: engines in the dominant
                             overlap cluster contribute their discounted weight
                             (cluster_weight) instead of 1.0
  engines                  — sorted list of confirming engine ids
  regime_bucket            — stamp from world_state.regime.quad (CONTEXT only;
                             no conditioning logic applied here; display-only)

REDUNDANCY DISCOUNT
-------------------
Engines in the dominant_overlap_cluster (from covariance_spine.json lobes block) are
structurally correlated.  They receive partial credit:

    cluster_weight = 1.0 / len(dominant_overlap_cluster)

Example: a 4-engine dominant cluster contributes 0.25 each instead of 1.0.  Engines
NOT in the dominant cluster contribute 1.0 each.  When the dominant cluster is absent
(covariance_spine not yet computed), all engines contribute 1.0 (no discount).

HARD EXCLUSION
--------------
rotation-state × cycle-position pairing is DON'T-TEST (DO_NOT_REBUILD registry).
If BOTH engine families appear among confirming engines, they are counted normally
but NO dedicated rotation_cycle_pair field is emitted.  The exclusion is enforced in
assert_no_authority() by never adding such a key.

SCHEMA
------
data/neuralweb/confluence_strength.json
{
  "schema":               "neuralweb.confluence_strength.v1",
  "artifact_id":          "confluence-strength",
  "asof":                 <str>,
  "tier":                 "display",
  "is_context_only":      true,
  "display_only":         true,
  "authority_check":      [...violations] or [],
  "produced_by":          "engine/neuralweb/confluence_strength.py",
  "produced_at":          <utc str>,
  "rows":                 [
    {
      "subject":                  <str>,  # e.g. "engine:us_board"
      "as_of":                    <str>,
      "direction":                <int>,
      "horizon":                  <str>,
      "n_confirming_raw":         <int>,
      "n_independent_confirming": <float>,
      "engines":                  [<str>, ...],
      "regime_bucket":            <str | null>
    }
  ],
  "redundancy_discount": {
    "dominant_cluster_engines": [...] or null,
    "cluster_weight":           <float> or null,
    "source":                   "data/neuralweb/covariance_spine.json"
  },
  "gaps":                 [<str>, ...]
}

FAIL-OPEN CONTRACT
------------------
Every source read is fail-open.  Missing/corrupt artifacts produce an empty or
degraded payload with gaps noted; function never raises.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.neuralweb._law import assert_no_authority

log = logging.getLogger(__name__)

_SCHEMA = "neuralweb.confluence_strength.v1"
_HARD_LAW = (
    "HARD LAW: display-only; never gates, never ranks, never raises a priority. "
    "Redundancy discount is descriptive only. "
    "rotation-state × cycle-position pairing DON'T-TEST (DO_NOT_REBUILD)."
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _repo_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _read_json(p: Path) -> dict | list | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_strength: unreadable %s — %s", p, exc)
        return None


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Redundancy-discount loader
# ---------------------------------------------------------------------------


def _load_redundancy_params(repo: Path, gaps: list[str]) -> tuple[set[str], float | None]:
    """Return (dominant_cluster_set, cluster_weight) from covariance_spine.json.

    Returns (empty set, None) when spine absent — no discount applied.
    cluster_weight = 1.0 / len(dominant_cluster) when cluster has >= 2 engines.
    """
    spine_path = repo / "data" / "neuralweb" / "covariance_spine.json"
    if not spine_path.exists():
        gaps.append(
            "confluence_strength: covariance_spine.json absent — "
            "no redundancy discount applied (all engines contribute 1.0)"
        )
        return set(), None

    raw = _read_json(spine_path)
    if raw is None:
        gaps.append("confluence_strength: covariance_spine.json unreadable — no discount")
        return set(), None

    lobes = (raw.get("blocks") or {}).get("lobes")
    if lobes is None:
        gaps.append(
            "confluence_strength: covariance_spine.json has no lobes block — no discount"
        )
        return set(), None

    clusters = lobes.get("clusters") or []
    if not clusters:
        gaps.append("confluence_strength: no clusters in lobes block — no discount")
        return set(), None

    # Dominant cluster = largest by engine count
    dominant = max(clusters, key=lambda c: len(c if isinstance(c, list) else (c.get("engines") or [])))
    # clusters may be list[list[str]] or list[{"engines": [...]}]
    if isinstance(dominant, list):
        dominant_engines: list[str] = dominant
    elif isinstance(dominant, dict):
        dominant_engines = dominant.get("engines") or []
    else:
        gaps.append("confluence_strength: unexpected cluster format — no discount")
        return set(), None

    if len(dominant_engines) < 2:
        return set(), None  # singleton cluster = no discount needed

    weight = 1.0 / len(dominant_engines)
    return set(dominant_engines), weight


# ---------------------------------------------------------------------------
# Regime bucket loader
# ---------------------------------------------------------------------------


def _load_regime_bucket(repo: Path, gaps: list[str]) -> str | None:
    """Load current regime quad from world_state.json.  Context-only stamp."""
    ws_path = repo / "data" / "neuralweb" / "world_state.json"
    if not ws_path.exists():
        gaps.append("confluence_strength: world_state.json absent — regime_bucket null")
        return None

    raw = _read_json(ws_path)
    if not isinstance(raw, dict):
        gaps.append("confluence_strength: world_state.json unreadable — regime_bucket null")
        return None

    regime = raw.get("regime")
    if not isinstance(regime, dict):
        return None

    return regime.get("quad")  # str or None


# ---------------------------------------------------------------------------
# Core scorer
# ---------------------------------------------------------------------------


def _compute_rows(
    confirms_edges: list[dict],
    dominant_cluster: set[str],
    cluster_weight: float | None,
    regime_bucket: str | None,
    gaps: list[str],
) -> list[dict]:
    """Build strength rows from confirms edges in the confluence graph.

    Each confirms edge carries src=engine:X, dst=engine:Y on the same
    (symbol/subject, as_of, direction, horizon) key.  We reconstruct the
    co-firing groups from the edge list.

    For more robust subject keying we parse from edge notes where available,
    but primarily key on (src_engine, dst_engine) pairs per edge.

    Approach:
      - Each 'confirms' edge = src and dst both fired the same (subject, as_of,
        direction, horizon).  We build a union of engine ids per event key
        from the spine co-firing data embedded in the graph's confirms edges.
      - Since the graph summarizes pairs, not raw events, we use the edge
        metadata (n, note) to identify per-event groups by their engine membership.
        The confirms edges are engine:X → engine:Y meaning both fired together.
      - We reconstruct connected components of engine pairs → each component
        represents a co-firing event group with its engine members.

    In practice, the confluence graph only carries pairwise engine × engine
    co-firing lift edges (not per-event detail).  For per-event strength rows
    the correct primary source is the spine_index.parquet directly (same columns
    the confirms edges were built from).  We use that if available; fall back to
    edge-based reconstruction.
    """
    rows: list[dict] = []

    # If no confirms edges, emit zero rows but note it
    if not confirms_edges:
        gaps.append("confluence_strength: 0 confirms edges — strength rows empty")
        return rows

    # Build rows from confirms edge metadata:
    # Each confirms edge has n (co-fire count) and identifies two engines.
    # We aggregate at the edge level — one 'row' per engine pair × direction inferred.
    # NOTE: the spine_index path (below) gives the real per-event granularity.
    # For the strength scorer the key insight is: which engines fired together
    # and by how much are they redundant?  We emit one aggregate row per
    # (engine_pair, direction=1) as a summary (direction from lift sign or 1 default).
    #
    # HARD EXCLUSION: never emit a dedicated rotation_cycle_pair field.
    # Both engine families may appear in 'engines' list — that is allowed.
    # What is forbidden is a separate field named after the pairing.

    for edge in confirms_edges:
        src = edge.get("src", "")
        dst = edge.get("dst", "")
        if not src.startswith("engine:") or not dst.startswith("engine:"):
            continue

        e1 = src.removeprefix("engine:")
        e2 = dst.removeprefix("engine:")
        n_raw = edge.get("n") or 0
        if n_raw == 0:
            continue

        engine_list = sorted([e1, e2])
        # Compute n_independent_confirming for this pair
        n_indep = _score_independent([e1, e2], dominant_cluster, cluster_weight)

        # subject = pair description; as_of = null (pair-level, not event-level)
        # For display purposes emit a row per engine pair
        row: dict[str, Any] = {
            "subject": f"{e1}+{e2}",
            "as_of": None,  # pair-level aggregate, not event-level
            "direction": 1,  # positive co-firing; direction sign in spine_index
            "horizon": "pair-aggregate",
            "n_confirming_raw": 2,
            "n_independent_confirming": round(n_indep, 4),
            "engines": engine_list,
            "regime_bucket": regime_bucket,
            "n_cofire_events": n_raw,
        }
        rows.append(row)

    return rows


def _score_independent(
    engines: list[str],
    dominant_cluster: set[str],
    cluster_weight: float | None,
) -> float:
    """Score n_independent_confirming for a list of engine ids.

    Engines in the dominant overlap cluster contribute cluster_weight each.
    Engines outside contribute 1.0 each.
    """
    if not engines:
        return 0.0
    if not dominant_cluster or cluster_weight is None:
        return float(len(engines))

    score = 0.0
    for eng in engines:
        if eng in dominant_cluster:
            score += cluster_weight
        else:
            score += 1.0
    return score


# ---------------------------------------------------------------------------
# Spine-index path: per-event granularity
# ---------------------------------------------------------------------------


def _compute_rows_from_spine(
    repo: Path,
    dominant_cluster: set[str],
    cluster_weight: float | None,
    regime_bucket: str | None,
    gaps: list[str],
) -> list[dict]:
    """Build per-event strength rows from spine_index.parquet (preferred path).

    Groups spine rows by (symbol, as_of, direction, horizon); collects the
    distinct engine families that fired; applies redundancy discount.

    Returns empty list on any failure (fail-open).
    """
    spine_path = repo / "data" / "neuralweb" / "spine_index.parquet"
    if not spine_path.exists():
        gaps.append(
            "confluence_strength: spine_index.parquet absent — "
            "falling back to confirms-edge aggregation"
        )
        return []

    try:
        import pandas as pd  # noqa: PLC0415

        df = pd.read_parquet(spine_path)
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"confluence_strength: spine_index.parquet unreadable — {exc}")
        return []

    try:
        import pandas as pd  # noqa: PLC0415

        required_cols = {"symbol", "as_of", "direction", "horizon", "engine"}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            gaps.append(
                f"confluence_strength: spine_index missing columns {missing_cols} — "
                "falling back to confirms-edge aggregation"
            )
            return []

        # Only fired rows (direction != 0)
        fired = df[df["direction"] != 0].copy()
        if fired.empty:
            gaps.append("confluence_strength: no fired rows in spine_index — rows empty")
            return []

        # Exclude placebo control lane
        fired = fired[fired["engine"] != "placebo"]

        # Group by event key
        group_cols = ["symbol", "as_of", "direction", "horizon"]
        # Coerce direction to int for safe grouping
        try:
            fired["direction"] = fired["direction"].astype(int)
        except Exception:  # noqa: BLE001
            pass

        rows: list[dict] = []
        for key, grp in fired.groupby(group_cols, sort=False):
            symbol_val, as_of_val, dir_val, horizon_val = key
            engine_list = sorted(grp["engine"].dropna().unique().tolist())

            if len(engine_list) < 2:
                # Single engine — no co-firing; skip (not a confluence event)
                continue

            n_raw = len(engine_list)
            n_indep = _score_independent(engine_list, dominant_cluster, cluster_weight)

            row: dict[str, Any] = {
                "subject": str(symbol_val),
                "as_of": str(as_of_val),
                "direction": int(dir_val),
                "horizon": str(horizon_val),
                "n_confirming_raw": n_raw,
                "n_independent_confirming": round(n_indep, 4),
                "engines": engine_list,
                "regime_bucket": regime_bucket,
                # HARD EXCLUSION: no rotation_cycle_pair field emitted here.
                # Both rotation-state and cycle-position families may appear in
                # 'engines' — counting them is permitted.  A dedicated pairing
                # field is DON'T-TEST (DO_NOT_REBUILD).
            }
            rows.append(row)

        return rows

    except Exception as exc:  # noqa: BLE001
        log.warning("confluence_strength: spine grouping failed — %s", exc)
        gaps.append(f"confluence_strength: spine grouping error — {exc}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_strength(
    root: Path | str | None = None,
    now: datetime | None = None,
    graph: dict | None = None,
) -> dict:
    """Build and return the confluence strength payload.

    Parameters
    ----------
    root:
        Repo root override.
    now:
        UTC datetime for produced_at.  Defaults to now.
    graph:
        Pre-loaded confluence graph dict (for testing / to avoid re-reading).
        When None, read from data/neuralweb/confluence_graph.json.

    Returns
    -------
    dict
        Always returns a dict.  Never raises.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    repo = _repo_root(root)
    gaps: list[str] = []

    # ── Load covariance_spine redundancy params ──────────────────────────────
    dominant_cluster, cluster_weight = _load_redundancy_params(repo, gaps)

    redundancy_discount: dict[str, Any] = {
        "dominant_cluster_engines": sorted(dominant_cluster) if dominant_cluster else None,
        "cluster_weight": round(cluster_weight, 4) if cluster_weight is not None else None,
        "source": "data/neuralweb/covariance_spine.json",
    }

    # ── Load regime bucket (context stamp only) ──────────────────────────────
    regime_bucket = _load_regime_bucket(repo, gaps)

    # ── Try spine_index path first (per-event granularity) ──────────────────
    rows = _compute_rows_from_spine(
        repo, dominant_cluster, cluster_weight, regime_bucket, gaps
    )

    # ── Fallback: confirms edges from confluence_graph ───────────────────────
    if not rows:
        if graph is None:
            graph_path = repo / "data" / "neuralweb" / "confluence_graph.json"
            if graph_path.exists():
                graph = _read_json(graph_path)  # type: ignore[assignment]
                if not isinstance(graph, dict):
                    graph = None
                    gaps.append(
                        "confluence_strength: confluence_graph.json unreadable — "
                        "strength rows empty"
                    )
            else:
                gaps.append(
                    "confluence_strength: confluence_graph.json absent — "
                    "strength rows empty"
                )

        if graph is not None:
            confirms = [
                e for e in (graph.get("edges") or [])
                if e.get("edge_type") == "confirms"
            ]
            rows = _compute_rows(
                confirms, dominant_cluster, cluster_weight, regime_bucket, gaps
            )

    # ── Determine asof ───────────────────────────────────────────────────────
    asof = now.strftime("%Y-%m-%d")
    if rows:
        dates = [r["as_of"] for r in rows if r.get("as_of")]
        if dates:
            asof = max(dates)

    # ── Assemble payload ─────────────────────────────────────────────────────
    payload: dict[str, Any] = {
        "schema": _SCHEMA,
        "artifact_id": "confluence-strength",
        "asof": asof,
        "tier": "display",
        "is_context_only": True,
        "display_only": True,
        "hard_law": _HARD_LAW,
        "rows": rows,
        "redundancy_discount": redundancy_discount,
        "gaps": gaps,
        "produced_by": "engine/neuralweb/confluence_strength.py",
        "produced_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # ── assert_no_authority self-check ───────────────────────────────────────
    violations = assert_no_authority(payload)
    payload["authority_check"] = violations
    if violations:
        log.warning("confluence_strength: authority violations: %s", violations)

    return payload


def build_and_write(
    root: Path | str | None = None,
    now: datetime | None = None,
    out_path: Path | str | None = None,
    graph: dict | None = None,
) -> dict:
    """Build the confluence strength artifact and write to disk.

    Returns the payload dict.  Never raises; write failures propagate as OSError.
    """
    repo = _repo_root(root)
    if out_path is None:
        dest = repo / "data" / "neuralweb" / "confluence_strength.json"
    else:
        dest = Path(out_path)

    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = build_strength(root=repo, now=now, graph=graph)

    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    log.info(
        "confluence_strength: written %d rows, %d gaps → %s",
        len(payload.get("rows") or []),
        len(payload.get("gaps") or []),
        dest,
    )
    return payload
