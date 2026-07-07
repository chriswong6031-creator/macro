"""Age-pooled per-entity KM baseline for the INDEX-level hazard panel (IX-1 substrate).

Computes P(y_h = 1 | entity, direction) — the age-POOLED analogue of the
family-stratified, age-bucketed KM prior in scripts/fit_cycle_hazard._km_horizon_table.
At index level most entities have too few distinct turns for per-(entity, age-bucket)
cells, so v0 pools over age and falls back to the FAMILY-pooled rate whenever an entity
has fewer than ``min_rows`` person-period rows for a direction (and to the global
per-direction rate if the family is empty).

Pure functions over a panel frame — no I/O, no state. Deliberately NOT wired into any
live surface: the preregistered IX-1 trial wave decides whether/where this baseline is
consumed (it is the natural null for that trial).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.grading_stats import wilson_ci

HORIZONS = (1, 3, 6)
KM_MIN_ROWS_DEFAULT = 30
_REQUIRED_COLS = ("id", "family", "direction", "y1", "y3", "y6")


def _cell(sub: pd.DataFrame, h: int, z: float) -> dict:
    """Event rate + Wilson CI for one (rows, horizon) cell."""
    n = len(sub)
    events = int(sub[f"y{h}"].sum()) if n else 0
    p = events / n if n else float("nan")
    ci = wilson_ci(events, n, z=z) if n else None
    return {
        "n": n,
        "events": events,
        "p": float(p) if n else np.nan,
        "ci90": [round(ci[0], 5), round(ci[1], 5)] if ci else None,
    }


def index_km_table(
    panel: pd.DataFrame,
    min_rows: int = KM_MIN_ROWS_DEFAULT,
    horizons: tuple[int, ...] = HORIZONS,
    z: float = 1.645,
) -> dict:
    """Age-pooled KM horizon table P(y_h=1 | entity, direction) with family fallback.

    Parameters
    ----------
    panel : person-period frame with columns id, family, direction, y1/y3/y6.
    min_rows : entity-level estimate requires >= min_rows rows per (entity, direction);
        below that the entity cell carries the family-pooled rate (source
        'family_pooled'), or the global per-direction rate (source 'global') if the
        family itself has no rows.
    z : Wilson CI z (default 1.645 = 90% CI, matching the member KM baselines).

    Returns a plain-dict table (deterministic iteration order — sorted keys):
      {"params": {...},
       "global": {direction: {h: cell}},
       "families": {family: {direction: {h: cell}}},
       "entities": {id: {direction: {"n": int, "family": str,
                                     "horizons": {h: cell + "source"}}}}}
    """
    missing = [c for c in _REQUIRED_COLS if c not in panel.columns]
    if missing:
        raise ValueError(f"index_km_table: panel missing columns {missing}")

    out: dict = {
        "params": {"min_rows": int(min_rows), "horizons": list(horizons), "z": float(z)},
        "global": {},
        "families": {},
        "entities": {},
    }

    directions = ["up", "down"]

    for direction in directions:
        gsub = panel[panel["direction"] == direction]
        out["global"][direction] = {h: _cell(gsub, h, z) for h in horizons}

    for fam in sorted(panel["family"].unique()):
        out["families"][fam] = {}
        for direction in directions:
            fsub = panel[(panel["family"] == fam) & (panel["direction"] == direction)]
            out["families"][fam][direction] = {h: _cell(fsub, h, z) for h in horizons}

    for iid in sorted(panel["id"].unique()):
        isub_all = panel[panel["id"] == iid]
        fam = isub_all["family"].iloc[0]
        out["entities"][iid] = {}
        for direction in directions:
            isub = isub_all[isub_all["direction"] == direction]
            n = len(isub)
            horizons_out: dict = {}
            for h in horizons:
                own = _cell(isub, h, z)
                if n >= min_rows:
                    chosen = dict(own)
                    chosen["source"] = "entity"
                else:
                    fam_cell = out["families"][fam][direction][h]
                    if fam_cell["n"] > 0:
                        chosen = dict(fam_cell)
                        chosen["source"] = "family_pooled"
                    else:
                        chosen = dict(out["global"][direction][h])
                        chosen["source"] = "global"
                    # keep the entity's own (insufficient) counts visible for audits
                    chosen["own_n"] = own["n"]
                    chosen["own_events"] = own["events"]
                horizons_out[h] = chosen
            out["entities"][iid][direction] = {
                "n": n,
                "family": fam,
                "horizons": horizons_out,
            }
    return out


def km_predict_index(table: dict, rows: pd.DataFrame) -> dict[int, np.ndarray]:
    """Predict P(y_h=1) for each row of ``rows`` from a fitted index_km_table.

    Mirrors scripts/fit_cycle_hazard.km_predict's shape ({h: np.array}) so the trial
    wave can drop it in as the null model. Unknown (id, direction) pairs fall back to
    family, then global rates.
    """
    horizons = table["params"]["horizons"]
    ids = rows["id"].to_numpy()
    fams = rows["family"].to_numpy()
    dirs = rows["direction"].to_numpy()
    out: dict[int, np.ndarray] = {}
    for h in horizons:
        vals = np.empty(len(rows))
        for i in range(len(rows)):
            ent = table["entities"].get(ids[i], {}).get(dirs[i])
            if ent is not None:
                vals[i] = ent["horizons"][h]["p"]
                continue
            fam_cell = table["families"].get(fams[i], {}).get(dirs[i], {}).get(h)
            if fam_cell is not None and fam_cell["n"] > 0:
                vals[i] = fam_cell["p"]
            else:
                vals[i] = table["global"][dirs[i]][h]["p"]
        out[h] = vals
    return out
