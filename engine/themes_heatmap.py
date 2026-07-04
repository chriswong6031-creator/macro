"""Finviz *themes* treemap — pure compute layer.

Builds the JSON contract consumed by ``site/sector_heatmap.html`` (the themes
map-type of the shared ``heatmap.js`` renderer): the Finviz narrative-basket
treemap rendered **Theme → Subsector tile**, each tile coloured by the
subsector's % move over the selected timeframe, with the member tickers (and
their own moves) surfaced on hover — exactly the themes map, in our theme.

Contract mirrors ``engine/sp500_heatmap.py`` so the same renderer draws it; the
only differences are ``map_type="themes"`` (two levels: theme → subsector-leaf,
no third stock level) and that each tile is a *subsector* carrying a ``members``
list rather than a single stock.

Pure: takes already-loaded dicts (the committed Finviz snapshot) and returns a
JSON-serialisable dict. All network/disk I/O lives in
``scripts/fetch_finviz_themes.py`` (the only networked piece) and
``scripts/build_themes_heatmap.py`` (the offline build wrapper).
"""
from __future__ import annotations

from typing import Mapping, Sequence

# Eight daily-group timeframes, same keys/labels as the sp500 heatmap so the
# renderer's tabs/legend/strip are identical. Finviz serves all eight, so every
# one is ``available``.
TIMEFRAMES: list[dict] = [
    {"key": "1D",  "en": "1 day",         "zh": "1天"},
    {"key": "1W",  "en": "1 week",        "zh": "1周"},
    {"key": "MTD", "en": "Month to date", "zh": "本月至今"},
    {"key": "1M",  "en": "1 month",       "zh": "1月"},
    {"key": "3M",  "en": "3 month",       "zh": "3月"},
    {"key": "6M",  "en": "6 month",       "zh": "6月"},
    {"key": "YTD", "en": "Year to date",  "zh": "年初至今"},
    {"key": "1Y",  "en": "1 year",        "zh": "1年"},
]
DEFAULT_TIMEFRAME = "1D"

# Theme (top-level group) → Chinese label. Theme names are the "sector" level of
# the contract, which the renderer shows bilingually; subsector + member labels
# stay English, matching the sp500 map's sub-industry convention.
THEME_ZH: dict[str, str] = {
    "Artificial Intelligence": "人工智能",
    "Cloud Computing": "云计算",
    "Semiconductors": "半导体",
    "Cybersecurity": "网络安全",
    "Software": "软件",
    "Hardware": "硬件",
    "Quantum Computing": "量子计算",
    "Virtual & Augmented Reality": "虚拟与增强现实",
    "Biometrics": "生物识别",
    "Big Data": "大数据",
    "Electric Vehicles": "电动汽车",
    "Industrial Automation": "工业自动化",
    "Defense & Aerospace": "国防与航天",
    "Transportation & Logistics": "运输与物流",
    "Space Tech": "太空科技",
    "Robotics": "机器人",
    "Telecommunications": "电信",
    "Nanotechnology": "纳米技术",
    "Internet of Things": "物联网",
    "Autonomous Systems": "自动驾驶系统",
    "E-commerce": "电子商务",
    "Social Media": "社交媒体",
    "Digital Entertainment": "数字娱乐",
    "Real Estate & REITs": "房地产与REITs",
    "Consumer Goods": "消费品",
    "Smart Home": "智能家居",
    "Wearables": "可穿戴设备",
    "Education Technology": "教育科技",
    "Energy Renewable": "可再生能源",
    "Energy Traditional": "传统能源",
    "Commodities Energy": "能源商品",
    "Commodities Metals": "金属商品",
    "Commodities Agriculture": "农业商品",
    "Agriculture & FoodTech": "农业与食品科技",
    "Environmental Sustainability": "环境可持续",
    "Healthcare & Biotech": "医疗与生物科技",
    "Aging Population & Longevity": "老龄化与长寿",
    "Healthy Food & Nutrition": "健康食品与营养",
    "FinTech": "金融科技",
    "Crypto & Blockchain": "加密与区块链",
}


def build_themes_heatmap(
    tree: Sequence[Mapping],
    subsector_perf: Mapping[str, Mapping[str, float]],
    member_perf: Mapping[str, Mapping[str, float]] | None = None,
    *,
    generated_utc: str | None = None,
    asof: str | None = None,
    source: str = "finviz-themes",
) -> dict:
    """Assemble the themes heatmap payload.

    Parameters
    ----------
    tree           : ``[{theme, key, subsectors:[{key, name, description,
                     members:[ticker,...]}]}]`` — the committed structure.
    subsector_perf : ``{subsector_key: {tf: pct}}`` — colours each tile.
    member_perf    : ``{ticker: {tf: pct}}`` — colours each member row on hover.
    """
    member_perf = member_perf or {}
    tiles: list[dict] = []
    sectors: list[dict] = []
    seen_theme: set[str] = set()

    for theme in tree:
        tname = str(theme.get("theme") or theme.get("key") or "").strip()
        if not tname:
            continue
        if tname not in seen_theme:
            seen_theme.add(tname)
            sectors.append({"key": tname, "en": tname, "zh": THEME_ZH.get(tname, tname)})

        for sub in theme.get("subsectors", []):
            key = str(sub.get("key") or "").strip()
            name = str(sub.get("name") or key).strip()
            if not key:
                continue
            members = [str(m).strip() for m in (sub.get("members") or []) if str(m).strip()]
            sperf = {k: v for k, v in (subsector_perf.get(key) or {}).items() if v is not None}
            mem_rows = []
            for m in members:
                mp = {k: v for k, v in (member_perf.get(m) or {}).items() if v is not None}
                mem_rows.append({"t": m, "perf": mp})
            tiles.append({
                "t": key,
                "name": name,
                "sector": tname,
                "desc": str(sub.get("description") or "").strip(),
                # Size = member count (honest, dependency-free proxy; the map's
                # signal is colour, not area). Floor at 1 so empty baskets draw.
                "size": max(1, len(members)),
                "perf": sperf,
                "members": mem_rows,
            })

    timeframes = [{**tf, "group": "daily", "available": True} for tf in TIMEFRAMES]
    uniq_members = {m["t"] for t in tiles for m in t["members"]}

    return {
        "map_type": "themes",
        "asof": asof or "",
        "generated_utc": generated_utc or "",
        "source": source,
        "delay_min": 15,
        "currency": "USD",
        "default_tf": DEFAULT_TIMEFRAME,
        "timeframes": timeframes,
        "sectors": sectors,
        "tiles": tiles,
        "n_tiles": len(tiles),
        "n_members": len(uniq_members),
        "size_basis": "count",
    }
