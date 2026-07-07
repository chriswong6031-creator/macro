"""engine/cycle_pattern/live.py — state_daily_live adapter.

Nightly union of the three forward-log ledgers into the CPI lake shape.

Output: data/cycle_pattern/state_daily_live.parquet
  - Rows: union of all forward-log rows (full rebuild from source each run).
  - Sort: (entity_id, date) ascending, stable.
  - Identity: (entity_id, date) — forward logs are keep-FIRST by construction
    (engine.cycle_forward_log), so no duplicates exist across dates within one
    log. Across logs an entity can never appear in more than one engine (engines
    are disjoint by entity family), so the union is inherently dedup-free.  The
    test asserts row count == sum of forward-log rows as the cross-check.

Entity-id mapping contract (matches registry.py UPPERCASE join normalization):
  - Non-B- ids (sector ETFs: XLK; country ETFs: EWN; CN numeric: 801010):
      native_id = id.upper() -> matched against entities["native_id"]
      to obtain the entity_id.  Engine scoping (engine_label) narrows the lookup
      to avoid cross-family collisions.
  - B-<SLUG> ids (US baskets: B-AI_AGENTS; CN baskets: B-CN_SOLAR):
      native_id = id[2:].lower()  (strip "B-", lowercase) -> matched against
      entities["native_id"].  B- prefix ids only appear in engines that also
      carry the corresponding basket entities (us_sector_cycles /
      china_sector_cycles), so engine-scoping is applied first.

Added columns (not in forward logs):
  - entity_id     — stable primary key from registry
  - family        — entity family (us_sector, us_basket, cn_sector, cn_basket,
                    country, bloc)
  - engine        — engine label (us_sector_cycles / country_cycles /
                    china_sector_cycles) — homogeneous within each source log
  - source_artifact — provenance path string (data/<engine_dir>/forward_log.parquet)
  - unmapped_id   — bool flag: True when native_id did not resolve to an
                    entity_id; these rows are KEPT with entity_id=None and
                    cause a loud WARNING (never silently dropped).

Hazard columns preserved verbatim from forward logs:
  hazard_1m_p, hazard_1m_src, hazard_3m_p, hazard_3m_src, hazard_6m_p,
  hazard_6m_src.

The artifact is a DERIVED VIEW — fully reconstructed from the forward logs on
each run.  It is NOT a second append ledger.

No sklearn / statsmodels / scipy.stats.  Pure numpy / pandas / pyarrow.
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import NamedTuple

import pandas as pd

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA = _ROOT / "data"

# Three forward-log sources.  Order is display-stable (not load-order sensitive).
class _LogSpec(NamedTuple):
    engine_dir: str          # relative to data/
    engine_label: str        # stamped in 'engine' column
    source_artifact: str     # provenance path

_LOG_SPECS: list[_LogSpec] = [
    _LogSpec("sector_cycles",       "us_sector_cycles",    "data/sector_cycles/forward_log.parquet"),
    _LogSpec("country_cycles",      "country_cycles",      "data/country_cycles/forward_log.parquet"),
    _LogSpec("china_sector_cycles", "china_sector_cycles", "data/china_sector_cycles/forward_log.parquet"),
]

# Six hazard columns guaranteed present in every forward log.
_HAZARD_COLS = [
    "hazard_1m_p", "hazard_1m_src",
    "hazard_3m_p", "hazard_3m_src",
    "hazard_6m_p", "hazard_6m_src",
]

# All forward-log state columns we carry forward (superset; absent cols -> NaN).
_STATE_COLS = [
    "phase", "pos", "osc_slope", "signal", "timing_state", "above200d",
    "rs_63d", "proj_next", "proj_central", "proj_lo", "proj_hi",
    "pos_v2", "phase_v2", "stance", "divergence", "overdue", "basis",
    # China-specific extras (absent in US/country logs -> NaN)
    "signature", "rs_rank",
    "pathway_cond_rate", "pathway_base_rate", "pathway_tercile",
]

# Canonical column order for the output artifact.
_OUTPUT_COLS = (
    ["entity_id", "native_id", "family", "date", "kind", "name"]
    + ["engine", "source_artifact"]
    + _STATE_COLS
    + _HAZARD_COLS
    + ["unmapped_id"]
)


def _build_entity_lookup(entities: pd.DataFrame) -> dict[str, dict[str, tuple[str, str]]]:
    """Build a two-level lookup: engine_label -> {native_id_upper -> (entity_id, family)}.

    For B-prefixed basket ids we also store the stripped-lowercase key so the
    caller can resolve them after stripping the prefix.
    """
    lookup: dict[str, dict[str, tuple[str, str]]] = {}
    for _, row in entities.iterrows():
        eng = str(row["engine"])
        nid = str(row["native_id"]).upper()
        entry = (str(row["entity_id"]), str(row["family"]))
        lookup.setdefault(eng, {})[nid] = entry
    return lookup


def _resolve_native_id(raw_id: str) -> tuple[str, str]:
    """Return (lookup_key, native_id_display) for a raw forward-log 'id' value.

    B-<SLUG>  -> lookup_key = slug.upper() (strip "B-"), native_id = slug.lower()
    all other -> lookup_key = raw_id.upper(),            native_id = raw_id.upper()
    """
    upper = raw_id.upper()
    if upper.startswith("B-"):
        slug = upper[2:]          # SLUG  (e.g. "AI_AGENTS")
        return slug, slug.lower() # lookup against SLUG, display as lowercase slug
    return upper, upper


def _load_one_log(spec: _LogSpec, entity_lookup: dict) -> pd.DataFrame | None:
    """Load one forward-log parquet and attach entity_id/family/engine columns.

    Returns None (and logs a WARNING) when the file does not exist.
    Rows whose native_id cannot be resolved are kept with entity_id=None and
    unmapped_id=True; a WARNING lists every unresolved id.
    """
    fp = _DATA / spec.engine_dir / "forward_log.parquet"
    if not fp.exists():
        log.warning("forward_log absent — skipping: %s", fp)
        return None

    df = pd.read_parquet(fp)
    if df.empty:
        log.warning("forward_log is empty — skipping: %s", fp)
        return None

    df = df.copy()

    # Normalise date to datetime (logs store as string).
    df["date"] = pd.to_datetime(df["date"])

    # Resolve entity_id / family for each row.
    eng_map = entity_lookup.get(spec.engine_label, {})
    entity_ids: list[str | None] = []
    families: list[str | None] = []
    native_ids: list[str] = []
    unmapped: list[bool] = []

    for raw_id in df["id"].astype(str):
        lookup_key, native_display = _resolve_native_id(raw_id)
        entry = eng_map.get(lookup_key)
        if entry is None:
            entity_ids.append(None)
            families.append(None)
            native_ids.append(native_display)
            unmapped.append(True)
        else:
            entity_ids.append(entry[0])
            families.append(entry[1])
            native_ids.append(native_display)
            unmapped.append(False)

    df["entity_id"]  = entity_ids
    df["family"]     = families
    df["native_id"]  = native_ids
    df["unmapped_id"] = unmapped
    df["engine"]          = spec.engine_label
    df["source_artifact"] = spec.source_artifact

    # Report unmapped ids loudly — they are kept, not dropped.
    bad = df.loc[df["unmapped_id"], "id"].unique().tolist()
    if bad:
        log.warning(
            "%s: %d row(s) with unmapped native_id — entity_id=None, kept: %s",
            spec.engine_dir, len(bad), sorted(bad),
        )

    # Ensure all expected state cols are present (absent ones -> NaN).
    for col in _STATE_COLS + _HAZARD_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    return df


def build_state_daily_live(
    entities: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build and return the state_daily_live frame (full deterministic rebuild).

    Parameters
    ----------
    entities:
        Pre-loaded entity registry frame.  When None, loaded from
        data/cycle_pattern/entities.parquet (must already exist on disk).

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, native_id, family, date, kind, name, engine,
        source_artifact, <state_cols>, <hazard_cols>, unmapped_id.
        Sorted (entity_id, date), stable.
    """
    if entities is None:
        ep = _DATA / "cycle_pattern" / "entities.parquet"
        entities = pd.read_parquet(ep)

    entity_lookup = _build_entity_lookup(entities)

    parts: list[pd.DataFrame] = []
    for spec in _LOG_SPECS:
        part = _load_one_log(spec, entity_lookup)
        if part is not None:
            parts.append(part)

    if not parts:
        log.warning("No forward logs found — returning empty state_daily_live frame.")
        return pd.DataFrame(columns=_OUTPUT_COLS)

    combined = pd.concat(parts, ignore_index=True)

    # Select and order output columns (subset to those actually present).
    present = [c for c in _OUTPUT_COLS if c in combined.columns]
    extra   = [c for c in combined.columns if c not in set(_OUTPUT_COLS)
               and c not in {"id"}]  # drop raw 'id'; native_id is the display key
    out = combined[present + extra]

    out = out.sort_values(["entity_id", "date"], kind="stable").reset_index(drop=True)
    return out


def total_forward_log_rows() -> int:
    """Return the sum of row counts across all existing forward logs (no dedup)."""
    total = 0
    for spec in _LOG_SPECS:
        fp = _DATA / spec.engine_dir / "forward_log.parquet"
        if fp.exists():
            total += len(pd.read_parquet(fp))
    return total
