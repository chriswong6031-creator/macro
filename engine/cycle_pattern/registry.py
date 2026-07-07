"""engine/cycle_pattern/registry.py — Cycle-entity registry builder.

Enumerates one row per cycle ENTITY across every engine that emits a cycle
clock (US sector/basket/index-amalgam desks, China Shenwan L1 + baskets,
country/bloc cycles, and the flagship measured proxy bands). The output is the
join spine for the unified PIT state lake (lake.py).

Sources (all committed, no engine recompute):
  - US sectors (11) + US thematic baskets (46): data/baskets/membership.json
    (sectors enumerated from data/sector_cycles/cycle_dna.json["sectors"]).
  - Nasdaq groups (8): data/baskets_nasdaq/membership.json["amalgamations"].
  - Russell groups (11): data/baskets_russell/membership.json["amalgamations"].
  - China Shenwan L1 sectors (31): data/china_sector_cycles/backfill.parquet.
  - China baskets (22): data/baskets_china/membership.json["baskets"].
  - Country cycles (31, incl 7 blocs): data/country_cycles/backfill.parquet.
  - Flagship measured bands (20): engine.cycle_proxies.measured_bands().

Binding contract:
  - entity_id = '<family>:<native_id>' and is the stable primary key.
  - pit_membership is False for ALL baskets/amalgams (basket_index consolidated
    candles are hindsight-curated, pit=False); True only for the measured
    backbone (single-ticker sectors/countries and measured proxy bands).
  - native_id casing matches the hazard-panel / backfill join key exactly:
    US + country ETFs UPPERCASE, China Shenwan numeric, flagship = proxy cid.
  - No sklearn/statsmodels/scipy.stats. Pure stdlib + pandas.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from engine import cycle_proxies

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA = _ROOT / "data"

# Final, sorted column order for entities.parquet.
ENTITY_COLUMNS: list[str] = [
    "entity_id", "native_id", "display_name", "family", "region", "engine",
    "kind", "basis", "tier", "pit_membership", "has_monthly_backfill",
    "has_forward_log", "in_hazard_panel", "source_artifact",
]

# Families whose members are curated amalgams / equal-weight member indices —
# their consolidated candle is pit=False (hindsight membership), so every row
# in these families carries pit_membership=False.
_BASKET_FAMILIES = frozenset(
    {"us_basket", "nasdaq_group", "russell_group", "cn_basket", "bloc"}
)

# The 7 country-cycle ids that are cross-country blocs (kind='basket' in the
# country backfill), not single-country ETFs.
_COUNTRY_BLOC_IDS = frozenset({"AAXJ", "EEM", "EFA", "ILF", "VGK", "VPL", "VXUS"})


def _read_json(rel: str) -> dict:
    return json.loads((_DATA / rel).read_text(encoding="utf-8"))


def _hazard_ids() -> set[str]:
    """Native ids present in the hazard panel (uppercase US/country, numeric CN)."""
    h = pd.read_parquet(_DATA / "hazard" / "panel_price_c4414dcb.parquet",
                        columns=["id"])
    return set(h["id"].astype(str).unique())


def _backfill_ids(engine_dir: str) -> set[str]:
    """Native ids (UPPERCASE) present in an engine's monthly backfill."""
    b = pd.read_parquet(_DATA / engine_dir / "backfill.parquet", columns=["id"])
    return {s.upper() for s in b["id"].astype(str).unique()}


def _forward_log_ids(engine_dir: str) -> set[str]:
    """Native ids (UPPERCASE) carried in an engine's forward_log ledger."""
    fp = _DATA / engine_dir / "forward_log.parquet"
    if not fp.exists():
        return set()
    fl = pd.read_parquet(fp)
    # id column name is 'id' across the cycle ledgers.
    col = "id" if "id" in fl.columns else fl.columns[0]
    return {str(s).upper() for s in fl[col].astype(str).unique()}


def build_entities() -> pd.DataFrame:
    """Return the entity registry as a deterministic, entity_id-sorted frame."""
    hazard_ids = _hazard_ids()
    rows: list[dict] = []

    # --- US sectors (11) — measured single-ETF backbone -------------------
    us_sectors = _read_json("sector_cycles/cycle_dna.json")["sectors"]
    us_bf = _backfill_ids("sector_cycles")
    us_fl = _forward_log_ids("sector_cycles")
    # display names live in the country/sector backfill 'name' column.
    us_names = _name_map("sector_cycles")
    for sid in sorted(us_sectors):
        nid = sid.upper()
        rows.append(dict(
            entity_id=f"us_sector:{nid}", native_id=nid,
            display_name=us_names.get(nid, nid), family="us_sector",
            region="us", engine="us_sector_cycles", kind="sector",
            basis="price", tier="measured", pit_membership=True,
            has_monthly_backfill=nid in us_bf, has_forward_log=nid in us_fl,
            in_hazard_panel=nid in hazard_ids,
            source_artifact="data/sector_cycles/cycle_dna.json",
        ))

    # --- US thematic baskets (46) — curated equal-weight indices ----------
    baskets = _read_json("baskets/membership.json")["baskets"]
    for bid in sorted(baskets):
        nid = bid  # basket slug key is its own native id (lowercase, stable)
        rows.append(dict(
            entity_id=f"us_basket:{nid}", native_id=nid,
            display_name=baskets[bid].get("name") or nid, family="us_basket",
            region="us", engine="us_sector_cycles", kind="basket",
            basis="price", tier="frame", pit_membership=False,
            has_monthly_backfill=False, has_forward_log=False,
            in_hazard_panel=False,
            source_artifact="data/baskets/membership.json",
        ))

    # --- Nasdaq groups (8) + Russell groups (11) — index amalgams ---------
    for fam, engine_dir in (("nasdaq_group", "baskets_nasdaq"),
                            ("russell_group", "baskets_russell")):
        amalg = _read_json(f"{engine_dir}/membership.json")["amalgamations"]
        for aid in sorted(amalg):
            rows.append(dict(
                entity_id=f"{fam}:{aid}", native_id=aid,
                display_name=amalg[aid].get("name") or aid, family=fam,
                region="us", engine="us_sector_cycles", kind="amalgam",
                basis="price", tier="frame", pit_membership=False,
                has_monthly_backfill=False, has_forward_log=False,
                in_hazard_panel=False,
                source_artifact=f"data/{engine_dir}/membership.json",
            ))

    # --- China Shenwan L1 sectors (31) — measured backbone ----------------
    cn_names = _name_map("china_sector_cycles")
    cn_bf = _backfill_ids("china_sector_cycles")
    cn_fl = _forward_log_ids("china_sector_cycles")
    for nid in sorted(cn_names):
        rows.append(dict(
            entity_id=f"cn_sector:{nid}", native_id=nid,
            display_name=cn_names[nid], family="cn_sector",
            region="china", engine="china_sector_cycles", kind="sector",
            basis="price", tier="measured", pit_membership=True,
            has_monthly_backfill=nid in cn_bf, has_forward_log=nid in cn_fl,
            in_hazard_panel=nid in hazard_ids,
            source_artifact="data/china_sector_cycles/backfill.parquet",
        ))

    # --- China baskets (22) — curated equal-weight indices ----------------
    cn_baskets = _read_json("baskets_china/membership.json")["baskets"]
    for bid in sorted(cn_baskets):
        rows.append(dict(
            entity_id=f"cn_basket:{bid}", native_id=bid,
            display_name=cn_baskets[bid].get("name") or bid, family="cn_basket",
            region="china", engine="china_sector_cycles", kind="basket",
            basis="price", tier="frame", pit_membership=False,
            has_monthly_backfill=False, has_forward_log=False,
            in_hazard_panel=False,
            source_artifact="data/baskets_china/membership.json",
        ))

    # --- Country cycles (31, incl 7 blocs) --------------------------------
    ctry = _kind_name_map("country_cycles")
    ctry_bf = _backfill_ids("country_cycles")
    ctry_fl = _forward_log_ids("country_cycles")
    for nid in sorted(ctry):
        is_bloc = nid in _COUNTRY_BLOC_IDS
        fam = "bloc" if is_bloc else "country"
        rows.append(dict(
            entity_id=f"{fam}:{nid}", native_id=nid,
            display_name=ctry[nid]["name"], family=fam,
            region="global" if is_bloc else "intl",
            engine="country_cycles",
            kind=ctry[nid]["kind"],
            basis="price",
            tier="frame" if is_bloc else "measured",
            pit_membership=not is_bloc,
            has_monthly_backfill=nid in ctry_bf,
            has_forward_log=nid in ctry_fl,
            # blocs are excluded from the hazard panel (curated amalgams).
            in_hazard_panel=(not is_bloc) and nid in hazard_ids,
            source_artifact="data/country_cycles/backfill.parquet",
        ))

    # --- Flagship measured bands (20) -------------------------------------
    registry = cycle_proxies.REGISTRY
    for cid, band in cycle_proxies.measured_bands():
        rows.append(dict(
            entity_id=f"flagship:{cid}", native_id=cid,
            display_name=registry[cid].get("name") or cid,
            family="flagship_band", region="global", engine="cycle_proxies",
            kind="measured_band", basis=band.get("basis"),
            tier="measured", pit_membership=True,
            has_monthly_backfill=False, has_forward_log=False,
            in_hazard_panel=False,
            source_artifact="engine/cycle_proxies.py::measured_bands",
        ))

    df = pd.DataFrame(rows, columns=ENTITY_COLUMNS)
    df = df.sort_values("entity_id", kind="stable").reset_index(drop=True)
    return df


def _name_map(engine_dir: str) -> dict[str, str]:
    """UPPERCASE native_id -> display_name from an engine's monthly backfill."""
    b = pd.read_parquet(_DATA / engine_dir / "backfill.parquet",
                        columns=["id", "name"])
    b = b.drop_duplicates("id")
    return {str(i).upper(): str(n) for i, n in zip(b["id"], b["name"])}


def _kind_name_map(engine_dir: str) -> dict[str, dict]:
    """UPPERCASE native_id -> {name, kind} from an engine's monthly backfill."""
    b = pd.read_parquet(_DATA / engine_dir / "backfill.parquet",
                        columns=["id", "name", "kind"])
    b = b.drop_duplicates("id")
    return {
        str(i).upper(): {"name": str(n), "kind": str(k)}
        for i, n, k in zip(b["id"], b["name"], b["kind"])
    }
