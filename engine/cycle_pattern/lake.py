"""engine/cycle_pattern/lake.py — Unified monthly PIT research panel.

UNION of the three monthly cycle backfills (US sector, country, China Shenwan),
mapped onto the shared entity registry (registry.py) and LEFT-JOINed to the
hazard-panel FEATURE columns. Labels (y1/y3/y6/event_date) and hazard
probabilities are deliberately excluded — labels live in outcomes, never in
state (doctrine), and retro hazard scoring is a later preregistered wave.

Row identity is (entity_id, date). China backfill lacks the v2/stance/
divergence/overdue/basis columns; those are filled NaN/None and the affected
rows carry china_schema_v0=True.

Binding contract:
  - Join key against hazard is (native_id UPPERCASE, month-end date). US and
    country ids join 100%; China rows on dates/ids the hazard panel had not yet
    begun tracking join to NaN (a real left-join miss, not a defect).
  - hazard_epoch = 'price_c4414dcb' on joined rows, else None.
  - No sklearn/statsmodels/scipy.stats. Pure pandas joins, no engine recompute.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.cycle_pattern import registry

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA = _ROOT / "data"

HAZARD_EPOCH = "price_c4414dcb"
_HAZARD_PATH = _DATA / "hazard" / f"panel_{HAZARD_EPOCH}.parquet"

# Engine dir -> (family used to build entity_id, engine label, provenance path).
_ENGINE_SOURCES = {
    "sector_cycles": ("us_sector", "us_sector_cycles",
                    "data/sector_cycles/backfill.parquet"),
    "country_cycles": (None, "country_cycles",  # family split: country vs bloc
                    "data/country_cycles/backfill.parquet"),
    "china_sector_cycles": ("cn_sector", "china_sector_cycles",
                            "data/china_sector_cycles/backfill.parquet"),
}

# Backfill state columns carried into the lake (label/outcome columns never here).
_STATE_COLS = [
    "phase", "pos", "osc_slope", "signal", "timing_state", "above200d",
    "rs_63d", "proj_next", "proj_central", "proj_lo", "proj_hi",
    "pos_v2", "phase_v2", "stance", "divergence", "overdue", "basis",
]

# Columns the China backfill lacks (drive the china_schema_v0 gap flag).
_CHINA_GAP_COLS = ["pos_v2", "phase_v2", "stance", "divergence", "overdue", "basis"]

# Hazard FEATURE columns joined onto state. Labels y1/y3/y6/event_date and the
# leg_open_date / censored bookkeeping are intentionally excluded.
_HAZARD_FEATURES = [
    "age_m", "age_bucket", "direction", "trend_pass", "mom_score", "rs_63d",
    "vol_pctile", "amp_proxy", "log_age_ratio", "quad", "liquidity",
]

# Label/outcome columns that MUST NOT appear anywhere in the lake.
_FORBIDDEN_COLS = frozenset({"y1", "y3", "y6", "event_date"})


def _native_to_entity(entities: pd.DataFrame, engine_label: str) -> dict[str, str]:
    """UPPERCASE native_id -> entity_id, scoped to one engine."""
    sub = entities[entities["engine"] == engine_label]
    return {str(n).upper(): eid for n, eid in zip(sub["native_id"], sub["entity_id"])}


def _load_backfill(engine_dir: str, entities: pd.DataFrame) -> pd.DataFrame:
    fam, engine_label, prov = _ENGINE_SOURCES[engine_dir]
    b = pd.read_parquet(_DATA / engine_dir / "backfill.parquet")
    b = b.copy()
    b["native_id"] = b["id"].astype(str).str.upper()

    n2e = _native_to_entity(entities, engine_label)
    b["entity_id"] = b["native_id"].map(n2e)
    if b["entity_id"].isna().any():
        missing = sorted(b.loc[b["entity_id"].isna(), "native_id"].unique())
        raise ValueError(f"{engine_dir}: unmapped native ids {missing}")

    # normalized month-end date (hazard panel is strictly EOM) + raw string kept
    nd = pd.to_datetime(b["date"])
    b["date"] = (nd + pd.offsets.MonthEnd(0)).dt.normalize()

    china = engine_dir == "china_sector_cycles"
    for col in _STATE_COLS:
        if col not in b.columns:
            b[col] = np.nan
    b["china_schema_v0"] = bool(china)

    b["engine"] = engine_label
    b["source_artifact"] = prov
    # per-row basis: China backfill has no basis column -> price (measured px engine)
    if china:
        b["basis"] = "price"

    keep = ["entity_id", "native_id", "date"] + _STATE_COLS + [
        "china_schema_v0", "engine", "source_artifact"]
    return b[keep]


def _load_hazard_features() -> pd.DataFrame:
    h = pd.read_parquet(_HAZARD_PATH)
    h = h.copy()
    h["native_id"] = h["id"].astype(str).str.upper()
    h["date"] = pd.to_datetime(h["date"]).dt.normalize()
    cols = ["native_id", "date"] + _HAZARD_FEATURES
    hf = h[cols].copy()
    # hazard rows are unique per (id, date); guard against silent fan-out.
    if hf.duplicated(["native_id", "date"]).any():
        hf = hf.drop_duplicates(["native_id", "date"], keep="last")
    return hf


def build_state_monthly() -> pd.DataFrame:
    """Return the unified monthly PIT panel, deterministically ordered."""
    entities = registry.build_entities()

    parts = [_load_backfill(d, entities) for d in
            ("sector_cycles", "country_cycles", "china_sector_cycles")]
    state = pd.concat(parts, ignore_index=True)

    hf = _load_hazard_features()
    # hazard rs_63d would collide with the backfill's own rs_63d; suffix the join.
    merged = state.merge(
        hf, on=["native_id", "date"], how="left", suffixes=("", "_hz"),
    )
    merged["hazard_epoch"] = np.where(
        merged["age_m"].notna(), HAZARD_EPOCH, None)

    # doctrine guard: no label/outcome columns may have leaked in.
    leaked = _FORBIDDEN_COLS.intersection(merged.columns)
    if leaked:
        raise ValueError(f"label/outcome columns leaked into state lake: {sorted(leaked)}")

    merged = merged.sort_values(["entity_id", "date"], kind="stable").reset_index(drop=True)
    return merged


def _meta() -> dict:
    """Column-level PIT metadata sidecar contents."""

    def col(pit_class: str, source: str) -> dict:
        return {"pit_class": pit_class, "source": source}

    meta: dict = {"_note": (
        "Rows with date > 2024-01-01 fall inside the permanently embargoed "
        "holdout and MUST NOT be used for any trial/model selection."
    ), "columns": {}}
    c = meta["columns"]

    # keys / provenance
    for k in ("entity_id", "native_id", "date"):
        c[k] = col("pit_pure", "registry+backfill key")
    c["engine"] = col("engine_stamped", "cycle-engine identity")
    c["source_artifact"] = col("pit_pure", "provenance path")
    c["china_schema_v0"] = col("pit_pure", "schema-gap flag")
    c["hazard_epoch"] = col("pit_pure", f"hazard {HAZARD_EPOCH} join marker")

    # engine-stamped cycle state (revision-sensitive engine output, PIT-stamped
    # by the backfill run but not a pure function of price alone)
    for k in ("phase", "pos", "osc_slope", "signal", "timing_state", "above200d",
            "proj_next", "proj_central", "proj_lo", "proj_hi", "pos_v2",
            "phase_v2", "stance", "divergence", "overdue", "basis"):
        c[k] = col("engine_stamped", "cycle backfill (engine stamp)")

    # backfill rs_63d (percent-point scale) is the engine's own relative-strength
    # stamp; the hazard panel carries a distinct fractional rs_63d, joined as
    # rs_63d_hz. Both are price-derived <= t (pit_pure) but not interchangeable.
    c["rs_63d"] = col("pit_pure", "backfill relative strength (pp scale)")
    c["rs_63d_hz"] = col("pit_pure", f"hazard {HAZARD_EPOCH} rs_63d (fractional)")

    # hazard FEATURES
    for k in ("age_m", "age_bucket", "direction", "trend_pass", "mom_score",
            "vol_pctile", "amp_proxy", "log_age_ratio"):
        c[k] = col("pit_pure", f"hazard {HAZARD_EPOCH} price feature")
    # quad/liquidity are revision-optimistic per P-D5-1
    c["quad"] = col("revision_optimistic", "hazard quad (P-D5-1)")
    c["liquidity"] = col("revision_optimistic", "hazard liquidity (P-D5-1)")

    return meta


def write_meta(path: Path) -> None:
    path.write_text(json.dumps(_meta(), ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
