"""Commodity Coverage Ledger — B-F09-6 (MO-DELTA-029).

Names, per commodity family, the exact file that reads prices and the exact
file that reads physical supply for this build — printing "Not covered yet"
in plain words wherever no producer is wired, rather than omitting the row.

Pure filesystem read over a frozen 5-family registry. Never imports `lib.store`
or any scoring path, never writes, never raises. This module is an inventory
of existing producers/artifacts, not a new store (F09 do_not_redo).
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The ONLY source labels a coverage cell may cite — licence-safety guard.
PUBLIC_SOURCES = frozenset({
    "EIA Weekly Petroleum Status Report",
    "EIA 每周石油状况报告",
    "Daily price history (Yahoo)",
    "每日价格历史（Yahoo）",
})

_NOT_COVERED = {"en": "Not covered yet", "zh": "尚未覆盖"}
_WAITING = {"en": "Built, waiting on data", "zh": "已建成，等待数据"}

# Frozen registry — exactly 5 families, frozen id order.
FAMILIES: tuple[dict, ...] = (
    {
        "id": "energy",
        "family_en": "Energy — crude & fuels",
        "family_zh": "能源——原油与成品油",
        "price": {
            "producer": "engine/commodity_inputs.py",
            "artifacts": ("data/yahoo/CL_F.parquet",),
            "source_en": "Daily price history (Yahoo)",
            "source_zh": "每日价格历史（Yahoo）",
            "cell_en": "Daily prices for oil, gas and fuels",
            "cell_zh": "原油、天然气与成品油的日线价格",
        },
        "supply": {
            "producer": "engine/commodity_supply_context.py",
            "artifacts": (
                "data/eia/crude_stocks.parquet",
                "data/eia/crude_production.parquet",
                "data/eia/crude_imports.parquet",
            ),
            "source_en": "EIA Weekly Petroleum Status Report",
            "source_zh": "EIA 每周石油状况报告",
            "cell_en": "US weekly petroleum stocks, against the 5-year seasonal norm",
            "cell_zh": "美国每周石油库存，对比五年季节常态",
        },
    },
    {
        "id": "precious",
        "family_en": "Precious metals",
        "family_zh": "贵金属",
        "price": {
            "producer": "engine/commodity_inputs.py",
            "artifacts": ("data/yahoo/GC_F.parquet",),
            "source_en": "Daily price history (Yahoo)",
            "source_zh": "每日价格历史（Yahoo）",
            "cell_en": "Daily prices for gold, silver, platinum and palladium",
            "cell_zh": "黄金、白银、铂金与钯金的日线价格",
        },
        "supply": None,
    },
    {
        "id": "base",
        "family_en": "Industrial metals",
        "family_zh": "工业金属",
        "price": {
            "producer": "engine/commodity_inputs.py",
            "artifacts": ("data/yahoo/HG_F.parquet",),
            "source_en": "Daily price history (Yahoo)",
            "source_zh": "每日价格历史（Yahoo）",
            "cell_en": "Daily prices for copper",
            "cell_zh": "铜的日线价格",
        },
        "supply": None,
    },
    {
        "id": "agri",
        "family_en": "Grains & softs",
        "family_zh": "谷物与软商品",
        "price": {
            "producer": "engine/commodity_inputs.py",
            "artifacts": ("data/yahoo/ZC_F.parquet",),
            "source_en": "Daily price history (Yahoo)",
            "source_zh": "每日价格历史（Yahoo）",
            "cell_en": "Daily prices for corn, wheat, soybeans, cattle, coffee, sugar, cocoa and cotton",
            "cell_zh": "玉米、小麦、大豆、活牛、咖啡、食糖、可可与棉花的日线价格",
        },
        "supply": None,
    },
    {
        "id": "techmat",
        "family_en": "Semiconductors & critical tech materials",
        "family_zh": "半导体与关键科技材料",
        "price": None,
        "supply": None,
    },
)


def _axis_cell(axis: dict | None, root: Path) -> dict:
    """Resolve one read axis (price|supply) against the filesystem.

    Returns {"read": bool, "en": str, "zh": str, "source": {...} | None}.
    Never raises: a stat error on any artifact is treated as "missing".
    """
    if axis is None:
        return {"read": False, "en": _NOT_COVERED["en"], "zh": _NOT_COVERED["zh"], "source": None}

    producer = axis.get("producer")
    if not producer:
        return {"read": False, "en": _NOT_COVERED["en"], "zh": _NOT_COVERED["zh"], "source": None}

    producer_exists = False
    try:
        producer_exists = (root / producer).exists()
    except Exception:  # noqa: BLE001 — a stat error must never crash the build
        producer_exists = False

    artifacts = axis.get("artifacts") or ()
    artifact_exists = False
    for a in artifacts:
        try:
            if (root / a).exists():
                artifact_exists = True
                break
        except Exception:  # noqa: BLE001
            continue

    if producer_exists and artifact_exists:
        return {
            "read": True,
            "en": axis.get("cell_en", _NOT_COVERED["en"]),
            "zh": axis.get("cell_zh", _NOT_COVERED["zh"]),
            "source": {
                "producer": producer,
                "source_en": axis.get("source_en", ""),
                "source_zh": axis.get("source_zh", ""),
            },
        }
    if producer_exists and not artifact_exists:
        return {"read": False, "en": _WAITING["en"], "zh": _WAITING["zh"], "source": None}
    return {"read": False, "en": _NOT_COVERED["en"], "zh": _NOT_COVERED["zh"], "source": None}


def compute_coverage_matrix(root: Path | None = None) -> dict:
    """Resolve the frozen registry against THIS build's filesystem.

    Returns {"rows": [row, ...]}. Never raises; never writes; never scores.
    """
    root = Path(root) if root is not None else _REPO_ROOT
    rows: list[dict] = []
    try:
        for fam in FAMILIES:
            price = _axis_cell(fam.get("price"), root)
            supply = _axis_cell(fam.get("supply"), root)

            if supply["read"]:
                state = "covered"
                state_en, state_zh = "Prices + supply", "价格＋供需"
            elif price["read"]:
                state = "partial"
                state_en, state_zh = "Prices only", "仅价格"
            else:
                state = "none"
                state_en, state_zh = _NOT_COVERED["en"], _NOT_COVERED["zh"]

            sources = [s["source"] for s in (price, supply) if s["source"] is not None]

            rows.append({
                "id": fam["id"],
                "family_en": fam["family_en"],
                "family_zh": fam["family_zh"],
                "state": state,
                "state_en": state_en,
                "state_zh": state_zh,
                "price_en": price["en"],
                "price_zh": price["zh"],
                "supply_en": supply["en"],
                "supply_zh": supply["zh"],
                "sources": sources,
            })
    except Exception:  # noqa: BLE001 — this panel must never crash the build
        return {"rows": []}
    return {"rows": rows}
