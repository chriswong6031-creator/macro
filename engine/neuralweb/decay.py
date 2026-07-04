"""engine.neuralweb.decay — Family-level decay-curve diagnostics (Neural Web W3 PR3).

HONESTY HEADER (mirrors kernel.py verbatim — same provenance law applies)
---------------------------------------------------------------------------
The outputs of this module are ESTIMATES WITH UNCERTAINTY, never findings.

Only shrunken posteriors (shrunken_ic) are consumable by display surfaces; raw
means are diagnostic only and must never drive allocation or alerting.

No behavior-changing consumer may read the artifact produced here
(data/neuralweb/kernel_families.json) until a cell passes the quarterly
pre-registered decision batch.  Display-first law is enforced structurally:
this module registers zero behavior-changing consumers.

PURPOSE
-------
Two diagnostic shapes per engine FAMILY (the 'engine' value in the kernel
estimates — which equals the spine-index engine column):

  A. horizon_curve
     shrunken_ic per horizon for the '__all__' marginal cells from
     kernel_estimates.parquet.  Shows the edge-vs-horizon shape: does the
     family's estimated edge grow, peak, or decay as the holding period extends?

  B. recency_trend
     Per-family, per trailing window {252d, 756d, all}: mean signed excess
     over fires in that window, computed by re-running the same cell math used
     in kernel.py but on a time-slice of the spine index (entity scope, all
     graded rows).  Three windows answer: "is the edge fading in calendar time?"

     NO SHRINKAGE ACROSS WINDOWS.  Windows are temporal views of the same data,
     not independent member observations.  Applying pooling.pooled_edges() across
     three windows would treat the 252d window mean as a "member" that partially
     borrows from the all-time mean — that is circular (252d data is a strict
     subset of the all-time data) and would violate the independence assumption
     of the hierarchical model.  Each window mean is reported as-is so the
     reader can assess drift direction without model contamination.  When future
     disjoint time-blocks are available (pre/post regime epochs), pooling would
     be appropriate; it is not appropriate here.

  C. staleness
     date_last per family (from kernel_estimates) + days_since_last_fire relative
     to the build date.

OUTPUT ARTIFACT: data/neuralweb/kernel_families.json
  {
    "families": {
      "<engine>": {
        "horizon_curve": {5: shrunken_ic, 10: ..., ...},   # __all__ marginal only
        "recency_trend": {
          "252d": {"n_eff": int, "mean": float|null, "wilson_ci_low": float|null},
          "756d": {...},
          "all":  {...}
        },
        "staleness": {"date_last": "YYYY-MM-DD"|null, "days_since_last_fire": int|null},
        "armed": bool
      }
    },
    "generated_from": "sha256:<hex>",   # byte_sha256 of kernel_estimates.parquet
    "produced_at": "YYYY-MM-DDTHH:MM:SSZ",
    # + five sibling envelope keys (schema_version, produced_by, inputs_hash, tier)
  }

USAGE
-----
  from engine.neuralweb.decay import build_families, write_families
  d = build_families(root)           # full in-memory build
  write_families(root)               # idempotent write to disk
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.qledger import wilson_ci_low as _wilson_ci_low
from engine.neuralweb.kernel import (
    HORIZONS,
    MARGINAL_BUCKET,
    WILSON_MIN_N,
    _signed_outcome_series,
)

log = logging.getLogger(__name__)

__all__ = [
    "RECENCY_WINDOWS",
    "build_families",
    "write_families",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Trailing-calendar-day windows for recency_trend.
RECENCY_WINDOWS: dict[str, int] = {
    "252d": 252,
    "756d": 756,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _data_dir(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root) / "data"
    from lib import config  # noqa: PLC0415
    return config.data_dir()


def _load_estimates(root: Path | str | None) -> pd.DataFrame:
    p = _data_dir(root) / "neuralweb" / "kernel_estimates.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("decay._load_estimates: read failed: %s", e)
        return pd.DataFrame()


def _estimates_byte_sha(root: Path | str | None) -> str:
    """sha256 of the kernel_estimates.parquet bytes — provenance anchor."""
    p = _data_dir(root) / "neuralweb" / "kernel_estimates.parquet"
    if not p.exists():
        return "sha256:absent"
    try:
        raw = p.read_bytes()
        return "sha256:" + hashlib.sha256(raw).hexdigest()
    except Exception as e:  # noqa: BLE001
        log.warning("decay._estimates_byte_sha: %s", e)
        return "sha256:error"


def _load_index(root: Path | str | None) -> pd.DataFrame:
    from engine.neuralweb.query import load_index  # noqa: PLC0415
    return load_index(root)


def _window_stats(
    engine: str,
    graded: pd.DataFrame,
    window_days: int | None,
    today_str: str,
) -> dict[str, Any]:
    """Compute mean signed excess + Wilson CI for a trailing calendar-day window.

    Parameters
    ----------
    engine:       engine family name.
    graded:       all graded rows for this engine (entity scope, finite outcomes).
    window_days:  trailing calendar days; None = all-time.
    today_str:    ISO date string for the cutoff (today).

    Returns
    -------
    {"n_eff": int, "mean": float|None, "wilson_ci_low": float|None}

    NOTE — no shrinkage across windows (see module docstring for rationale).
    """
    if graded.empty:
        return {"n_eff": 0, "mean": None, "wilson_ci_low": None}

    if window_days is not None:
        # as_of is str "YYYY-MM-DD"; filter rows within trailing window_days calendar days
        # Rows where as_of >= (today - window_days days) in string comparison
        try:
            cutoff_dt = date.fromisoformat(today_str) - pd.Timedelta(days=window_days)
            cutoff_str = cutoff_dt.isoformat()
            rows = graded[graded["as_of"].astype(str) >= cutoff_str]
        except Exception:  # noqa: BLE001
            rows = graded
    else:
        rows = graded

    if rows.empty:
        return {"n_eff": 0, "mean": None, "wilson_ci_low": None}

    # Dedup to (symbol, as_of) for event-level counting — mirrors kernel._build_cell
    rows_deduped = rows.drop_duplicates(subset=["symbol", "as_of"])
    n_eff = int(len(rows_deduped))
    if n_eff == 0:
        return {"n_eff": 0, "mean": None, "wilson_ci_low": None}

    excess = pd.to_numeric(rows_deduped["outcome_excess"], errors="coerce")
    direction = rows_deduped["direction"]
    signed = _signed_outcome_series(excess, direction)
    finite = signed[np.isfinite(signed)]

    if finite.empty:
        return {"n_eff": n_eff, "mean": None, "wilson_ci_low": None}

    mean_val = float(finite.mean())
    hits = int((finite > 0).sum())
    ci_low: float | None = None
    if n_eff >= WILSON_MIN_N:
        ci_low = _wilson_ci_low(hits, n_eff)

    return {
        "n_eff": n_eff,
        "mean": round(mean_val, 6),
        "wilson_ci_low": round(ci_low, 6) if ci_low is not None else None,
    }


# ---------------------------------------------------------------------------
# Build function
# ---------------------------------------------------------------------------

def build_families(root: Path | str | None = None) -> dict:
    """Build the kernel_families diagnostic payload.

    Returns the JSON-serialisable dict (without envelope keys).
    """
    today_str = date.today().isoformat()
    today_dt = date.today()

    estimates = _load_estimates(root)
    gen_from = _estimates_byte_sha(root)
    index_df = _load_index(root)

    # Filter spine index to entity-scope graded rows with finite outcomes
    entity_graded: pd.DataFrame
    if index_df.empty:
        entity_graded = pd.DataFrame()
        log.warning("decay.build_families: spine index empty — recency_trend will be empty")
    else:
        mask_entity = index_df["scope_type"].astype(str) == "entity"
        mask_graded = index_df["outcome_graded"].fillna(False).map(
            lambda x: bool(x) if x is not None else False
        )
        eidx = index_df[mask_entity & mask_graded].copy()
        eidx["outcome_excess"] = pd.to_numeric(eidx["outcome_excess"], errors="coerce")
        entity_graded = eidx[np.isfinite(eidx["outcome_excess"])].reset_index(drop=True)

    # Determine engine families from estimates (these are the canonical families)
    if estimates.empty:
        families_out: dict[str, Any] = {}
        log.warning("decay.build_families: kernel_estimates empty — returning empty families")
        return {
            "families": families_out,
            "generated_from": gen_from,
            "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    engine_families = estimates["engine"].unique().tolist()

    families_out = {}
    for engine in sorted(engine_families):
        eng_cells = estimates[estimates["engine"] == engine]

        # --- horizon_curve: shrunken_ic per horizon for __all__ marginal cells ---
        marginal_cells = eng_cells[eng_cells["regime"] == MARGINAL_BUCKET]
        horizon_curve: dict[str, Any] = {}
        for _, row in marginal_cells.iterrows():
            h = int(row["horizon"])
            ic = row["shrunken_ic"]
            horizon_curve[str(h)] = round(float(ic), 6) if ic is not None else None

        # --- armed: from estimates (all __all__ cells for this engine share armed) ---
        armed_vals = eng_cells["armed"].dropna().tolist()
        armed = bool(armed_vals[0]) if armed_vals else False

        # --- staleness: date_last across all cells for this engine ---
        date_lasts = eng_cells["date_last"].dropna().astype(str).tolist()
        date_last: str | None = max(date_lasts) if date_lasts else None
        days_since: int | None = None
        if date_last:
            try:
                dl = date.fromisoformat(date_last[:10])
                days_since = (today_dt - dl).days
            except (ValueError, TypeError):
                pass

        # --- recency_trend: mean signed excess over trailing windows ---
        eng_graded: pd.DataFrame
        if entity_graded.empty:
            eng_graded = pd.DataFrame()
        else:
            # Match engine values in the spine index — engine column matches kernel families
            eng_graded = entity_graded[entity_graded["engine"].astype(str) == engine].copy()

        recency_trend: dict[str, Any] = {}
        for window_name, window_days in RECENCY_WINDOWS.items():
            recency_trend[window_name] = _window_stats(engine, eng_graded, window_days, today_str)
        recency_trend["all"] = _window_stats(engine, eng_graded, None, today_str)

        families_out[engine] = {
            "horizon_curve": horizon_curve,
            "recency_trend": recency_trend,
            "staleness": {
                "date_last": date_last,
                "days_since_last_fire": days_since,
            },
            "armed": armed,
        }

    return {
        "families": families_out,
        "generated_from": gen_from,
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Write function (idempotent)
# ---------------------------------------------------------------------------

def write_families(root: Path | str | None = None) -> dict:
    """Build the kernel_families payload and write to data/neuralweb/kernel_families.json.

    Stamps the envelope (artifact_id='kernel-families') as sibling keys per
    the wrapper-prohibition law (engine.neuralweb.envelope module docstring).

    Returns a stats dict.
    """
    payload = build_families(root)

    if root is not None:
        out_dir = Path(root) / "data" / "neuralweb"
    else:
        from lib import config  # noqa: PLC0415
        out_dir = config.data_dir() / "neuralweb"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kernel_families.json"

    # Stamp with envelope (sibling keys)
    try:
        from engine.neuralweb.envelope import stamp  # noqa: PLC0415
        payload = stamp(payload, artifact_id="kernel-families")
    except Exception as e:  # noqa: BLE001
        log.warning("decay.write_families: envelope stamp failed: %s", e)

    import json  # noqa: PLC0415
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    n_families = len(payload.get("families", {}))
    log.info(
        "decay.write_families: wrote %d families to %s",
        n_families, out_path,
    )
    return {
        "output_path": str(out_path),
        "n_families": n_families,
        "generated_from": payload.get("generated_from"),
    }
