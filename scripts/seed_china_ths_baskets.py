"""Seed data/baskets_china_ths/membership.json — A-share baskets mirroring 同花顺 (THS) themes.

The machine-maintained sibling of scripts/seed_china_baskets.py. Instead of hand-picking members,
this adopts 同花顺's own thematic taxonomy: a CURATED subset of THS concept boards (概念板块) and
THS's live member lists for each, fetched by collectors.china_ths_concepts. We curate only WHICH
themes to carry (id / English label / category / thesis); the *members* are THS's, verbatim.

POINT-IN-TIME, accumulated forward: each run reads every dated snapshot in
data/baskets_china_ths/snapshots/ and diffs them, so a member's `added` is the first snapshot it
appeared in and `removed` is when THS dropped it. On the FIRST run there is only one snapshot, so
every current member is seeded at SEED (the china_search cache start) — the same HINDSIGHT-curated,
descriptive treatment the curated baskets carry (membership-as-of-today applied over the window,
honestly labelled, not an out-of-sample backtest). As snapshots accumulate the history becomes
genuinely point-in-time.

Universe = the FREE china_search top-market-cap A-share close cache (~1,500 names, ~5y). THS themes
include a small-cap tail outside that cache; those names are dropped (recorded under `missing`) and
a theme with <3 covered members is skipped. Benchmark = CSI 300 (沪深300, the 510300.SS ETF).

Re-runnable: `python -m scripts.seed_china_ths_baskets [--refresh]`  (--refresh re-fetches a
today snapshot before building; otherwise the latest existing snapshot is used, or one is fetched
if none exists).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("seed_china_ths_baskets")

SEED = "2021-06-15"  # china_search cache start; first-run members seeded here (hindsight-curated)

# Auto-add taxonomy curation (P3 — automated rule; curated baskets bypass ALL of this).
AUTO_MIN_MEMBERS = 8   # a non-curated THS board needs >=8 priced members to auto-import (was 3);
#                        thinner concepts add correlated noise more than diversified signal, and the
#                        board's reliability tiering already flags/collapses anything <6.
JACCARD_DEDUPE = 0.85  # two concepts sharing >=85% of members are near-redundant slices of one
#                        theme; keep the broader/curated one, drop the auto duplicate.

# Substring patterns marking NON-investable event / news / mechanical THS boards (not themes):
# earnings-forecast & corporate-action events, "owns-a-stake-in-X" participation baskets, index /
# connect / margin mechanics, sub-new-stock buckets, and one-off political/news labels. Verified
# against the live taxonomy to catch only junk (预增/举牌/参股X/次新股/沪深股通/芬太尼/…), no real theme.
_DROP_SUBSTRINGS = (
    # daily-tape / price-action event boards (future-proof; usually not exposed as boards)
    "涨停", "连板", "触板", "昨日", "首板", "炸板",
    # earnings-forecast & corporate-action events
    "预增", "预减", "扭亏", "摘帽", "摘星", "举牌", "高送转", "送转", "填权",
    "定增", "股权转让", "债转股", "员工持股", "股权激励", "回购", "增持", "减持", "解禁", "破发",
    # ownership / participation derivative boards ("参股银行/券商/保险" …)
    "参股",
    # index-membership / connect / financing mechanics
    "MSCI", "富时", "标普道琼斯", "深股通", "沪股通", "陆股通", "融资融券", "转债", "可转债", "国债",
    # mechanical "new stock" buckets & one-off news / political / hype labels
    "次新", "海峡两岸", "芬太尼", "租售同权", "独角兽",
)


def _is_event_board(name: str) -> bool:
    return any(k in (name or "") for k in _DROP_SUBSTRINGS)


def _jaccard(a: set, b: set) -> float:
    return (len(a & b) / len(a | b)) if (a and b) else 0.0

# Bilingual category labels (mirror the curated page's "EN · 中文" grouping style).
CATS = {
    "ai":      ("Technology & AI", "科技与AI"),
    "robot":   ("Robotics & Automation", "机器人与自动化"),
    "energy":  ("Energy Transition", "新能源"),
    "auto":    ("Autos & Mobility", "汽车与出行"),
    "health":  ("Healthcare & Biotech", "医药与生物科技"),
    "consumer":("Consumer", "消费"),
    "materials":("Materials & Resources", "资源与材料"),
    "fin":     ("Financials", "金融"),
    "mfg":     ("Advanced Manufacturing", "高端制造"),
    "frontier":("Frontier Tech", "前沿科技"),
}

# Each entry: (basket_id, THS concept name [MUST match the THS map exactly], English label,
#              category key, English thesis, 中文 thesis). name_zh = the THS concept name.
CURATED: list[tuple] = [
    # ── Technology & AI ───────────────────────────────────────────────────────
    ("ths_ai",            "人工智能",       "Artificial Intelligence", "ai",
     "Broad A-share AI complex — models, compute and applications.", "A股人工智能总线 — 模型、算力与应用。"),
    ("ths_cpo",           "共封装光学(CPO)", "Co-Packaged Optics (CPO)", "ai",
     "Optical-interconnect supply chain for AI datacentre switching.", "AI数据中心交换的光互连产业链。"),
    ("ths_storage_chip",  "存储芯片",       "Memory Chips", "ai",
     "DRAM/NAND memory design, manufacture and modules.", "DRAM/NAND存储设计、制造与模组。"),
    ("ths_litho",         "光刻机",         "Lithography Equipment", "ai",
     "Domestic lithography tools and their supply chain.", "国产光刻机及配套产业链。"),
    ("ths_sic",           "第三代半导体",    "3rd-Gen Semiconductors", "ai",
     "SiC/GaN wide-bandgap power & RF semiconductors.", "碳化硅/氮化镓宽禁带功率与射频半导体。"),
    ("ths_adv_pkg",       "先进封装",       "Advanced Packaging", "ai",
     "Chiplet / 2.5D-3D advanced semiconductor packaging.", "Chiplet/2.5D-3D先进封装。"),
    ("ths_liquid_cool",   "液冷服务器",      "Liquid-Cooled Servers", "ai",
     "Liquid cooling for AI server racks.", "面向AI服务器机柜的液冷方案。"),
    ("ths_aidc",          "数据中心(AIDC)",  "Data Centers (AIDC)", "ai",
     "AI datacentre build-out — IDC operators and gear.", "AI数据中心建设 — IDC运营商与设备。"),
    ("ths_xinchuang",     "信创",          "Domestic IT (Xinchuang)", "ai",
     "Domestic-substitution IT stack — OS, chips, software.", "信息技术应用创新 — 国产操作系统、芯片、软件。"),
    ("ths_pcb",           "PCB概念",       "PCB", "ai",
     "Printed-circuit-board makers riding AI-server demand.", "受益AI服务器需求的PCB厂商。"),
    ("ths_consumer_elec", "消费电子概念",    "Consumer Electronics", "ai",
     "Phones, wearables and their A-share supply chain.", "手机、可穿戴及A股供应链。"),

    # ── Robotics & Automation ─────────────────────────────────────────────────
    ("ths_humanoid",      "人形机器人",      "Humanoid Robots", "robot",
     "Humanoid-robot makers and component suppliers.", "人形机器人整机与零部件。"),
    ("ths_robotics",      "机器人概念",      "Robotics", "robot",
     "Industrial robots, automation and motion control.", "工业机器人、自动化与运动控制。"),

    # ── Energy Transition ─────────────────────────────────────────────────────
    ("ths_solar",         "光伏概念",       "Solar PV", "energy",
     "Solar value chain — silicon, cells, modules, inverters.", "光伏产业链 — 硅料、电池、组件、逆变器。"),
    ("ths_battery",       "锂电池概念",      "Lithium Battery", "energy",
     "Li-ion cells, materials and the battery supply chain.", "锂电池电芯、材料与产业链。"),
    ("ths_solid_state",   "固态电池",       "Solid-State Battery", "energy",
     "Next-gen solid-state battery developers.", "下一代固态电池研发企业。"),
    ("ths_storage_ess",   "储能",          "Energy Storage", "energy",
     "Grid/behind-the-meter energy-storage systems.", "电网侧/用户侧储能系统。"),
    ("ths_wind",          "风电",          "Wind Power", "energy",
     "Wind turbines, components and offshore wind.", "风电整机、零部件与海上风电。"),
    ("ths_hydrogen",      "氢能源",         "Hydrogen", "energy",
     "Hydrogen production, storage and fuel cells.", "氢气制取、储运与燃料电池。"),
    ("ths_nuclear",       "核电",          "Nuclear Power", "energy",
     "Nuclear power operators and equipment.", "核电运营商与设备。"),
    ("ths_charging",      "充电桩",         "EV Charging", "energy",
     "EV charging-pile makers and operators.", "充电桩制造与运营。"),
    ("ths_uhv",           "特高压",         "Ultra-High Voltage", "energy",
     "UHV transmission equipment and the grid build-out.", "特高压输电设备与电网建设。"),
    ("ths_vpp",           "虚拟电厂",       "Virtual Power Plant", "energy",
     "Virtual-power-plant / demand-response platforms.", "虚拟电厂/需求响应平台。"),

    # ── Autos & Mobility ──────────────────────────────────────────────────────
    ("ths_nev",           "新能源汽车",      "New-Energy Vehicles", "auto",
     "EV/PHEV makers and the new-energy auto chain.", "新能源整车与产业链。"),
    ("ths_autonomous",    "无人驾驶",       "Autonomous Driving", "auto",
     "Self-driving software, sensors and ADAS.", "自动驾驶软件、传感器与ADAS。"),
    ("ths_auto_elec",     "汽车电子",       "Automotive Electronics", "auto",
     "Automotive chips, electronics and domain controllers.", "汽车芯片、电子与域控制器。"),
    ("ths_die_cast",      "一体化压铸",      "Integrated Die-Casting", "auto",
     "Giga-casting / integrated die-cast body suppliers.", "一体化压铸车身供应商。"),
    ("ths_low_altitude",  "低空经济",       "Low-Altitude Economy", "auto",
     "eVTOL / drones / low-altitude airspace economy.", "eVTOL/无人机/低空空域经济。"),

    # ── Healthcare & Biotech ──────────────────────────────────────────────────
    ("ths_innovative_rx", "创新药",         "Innovative Drugs", "health",
     "Innovative-drug developers and their CXO partners.", "创新药研发企业及CXO伙伴。"),
    ("ths_aesthetics",    "医美概念",       "Medical Aesthetics", "health",
     "Medical-aesthetics products and services.", "医疗美容产品与服务。"),
    ("ths_bci",           "脑机接口",       "Brain-Computer Interface", "health",
     "Brain-computer-interface research and hardware.", "脑机接口研发与硬件。"),
    ("ths_synbio",        "合成生物",       "Synthetic Biology", "health",
     "Synthetic-biology and bio-manufacturing.", "合成生物与生物制造。"),
    ("ths_med_devices",   "医疗器械概念",    "Medical Devices", "health",
     "Medical-device makers across imaging, IVD, implants.", "影像、IVD、植介入等医疗器械。"),

    # ── Consumer ──────────────────────────────────────────────────────────────
    ("ths_baijiu",        "白酒概念",       "Baijiu (Liquor)", "consumer",
     "China's premium liquor — the bellwether consumer basket.", "白酒 — 消费风向标篮子。"),
    ("ths_prepared_food", "预制菜",         "Prepared Dishes", "consumer",
     "Pre-made / ready-meal food producers.", "预制菜/速食生产商。"),
    ("ths_appliances",    "家用电器",       "Home Appliances", "consumer",
     "White goods and small home appliances.", "大家电与小家电。"),
    ("ths_cross_border",  "跨境电商",       "Cross-Border E-Commerce", "consumer",
     "Cross-border e-commerce sellers and enablers.", "跨境电商卖家与服务商。"),

    # ── Materials & Resources ─────────────────────────────────────────────────
    ("ths_rare_earth",    "稀土永磁",       "Rare-Earth & Magnets", "materials",
     "Rare-earth miners and permanent-magnet makers.", "稀土开采与永磁制造。"),
    ("ths_gold",          "黄金概念",       "Gold", "materials",
     "Gold miners and producers.", "黄金开采与生产。"),
    ("ths_coal",          "煤炭概念",       "Coal", "materials",
     "Thermal/coking coal producers — the high-dividend value bloc.", "动力/焦煤生产 — 高股息价值板块。"),

    # ── Financials ────────────────────────────────────────────────────────────
    ("ths_fintech",       "互联网金融",      "Internet Finance", "fin",
     "Internet-finance platforms and fintech.", "互联网金融平台与金融科技。"),
    ("ths_digital_curr",  "数字货币",       "Digital Currency", "fin",
     "Digital-RMB / e-CNY infrastructure plays.", "数字人民币/e-CNY基础设施。"),

    # ── Advanced Manufacturing ────────────────────────────────────────────────
    ("ths_defense",       "军工",          "Defense", "mfg",
     "Defense primes and the military-industrial chain.", "军工总装与军民产业链。"),
    ("ths_big_plane",     "大飞机",         "Large Aircraft", "mfg",
     "C919 large-aircraft and commercial-aviation chain.", "C919大飞机及商用航空产业链。"),
    ("ths_space",         "商业航天",       "Commercial Aerospace", "mfg",
     "Commercial space — launch, satellites, ground.", "商业航天 — 火箭、卫星、地面。"),
    ("ths_satnav",        "卫星导航",       "Satellite Navigation", "mfg",
     "BeiDou satellite-navigation applications.", "北斗卫星导航应用。"),
    ("ths_machine_tool",  "工业母机",       "Machine Tools", "mfg",
     "High-end CNC machine tools ('mother machines').", "高端数控机床（工业母机）。"),
    ("ths_specialized",   "专精特新",       "Specialized SMEs", "mfg",
     "'Little-giant' specialized & sophisticated SMEs.", "专精特新“小巨人”企业。"),

    # ── Frontier Tech ─────────────────────────────────────────────────────────
    ("ths_quantum",       "量子科技",       "Quantum Tech", "frontier",
     "Quantum computing / communication research.", "量子计算/通信研究。"),
    ("ths_fusion",        "可控核聚变",      "Nuclear Fusion", "frontier",
     "Controlled-fusion research and supply chain.", "可控核聚变研究与产业链。"),
]

CONSTRUCTION = ("Equal-weighted, point-in-time dated membership, buy-and-hold between changes. "
                "Members are 同花顺 (Tonghuashun) concept-board constituents, filtered to the free "
                "china_search price cache. Benchmark = CSI 300 (沪深300).")
HISTORY_NOTE = ("Membership is THS's, snapshotted over time; `added`/`removed` reflect when a name "
                "entered/left the THS board (first-run members seed at the cache start). Series "
                "before a name's add date is a backtest of the membership at that point.")
NOTE = ("A-share baskets mirroring 同花顺 concept-board themes & members — descriptive structure, "
        "not an out-of-sample backtest and not a buy list.")


def _latest_snapshot(refresh: bool) -> dict[str, list[dict]]:
    """Return the THS member snapshot to build from (optionally re-fetching a today snapshot)."""
    from collectors import china_ths_concepts as ths
    snap_dir = config.data_dir() / "baskets_china_ths" / "snapshots"
    names = [row[1] for row in CURATED]
    if refresh or not snap_dir.exists() or not list(snap_dir.glob("*.json")):
        log.info("fetching fresh THS snapshot (%d themes)…", len(names))
        return ths.snapshot(names)
    latest = max(snap_dir.glob("*.json"), key=lambda p: p.stem)
    log.info("building from existing snapshot %s", latest.name)
    return json.loads(latest.read_text())


def _all_snapshots() -> list[tuple[str, dict]]:
    """All dated snapshots, oldest→newest, as [(date, {theme:[{ticker,name}]})]."""
    snap_dir = config.data_dir() / "baskets_china_ths" / "snapshots"
    out = []
    for p in sorted(snap_dir.glob("*.json"), key=lambda x: x.stem):
        try:
            out.append((p.stem, json.loads(p.read_text())))
        except Exception as e:  # noqa: BLE001
            log.warning("snapshot %s unreadable: %s", p.name, e)
    return out


def _pit_members(theme: str, snaps: list[tuple[str, dict]], universe: set[str],
                 zh_name) -> tuple[list[dict], list[str]]:
    """Diff snapshots → point-in-time member records for one theme, filtered to the universe.

    Returns (members, missing) where members carry added/removed/name_zh/rationale and `missing`
    lists THS members dropped because they're outside the price cache.
    """
    dates = [d for d, _ in snaps]
    first_date = dates[0]
    latest_theme = snaps[-1][1].get(theme, [])
    latest_tickers = {m["ticker"] for m in latest_theme}
    latest_name = {m["ticker"]: m["name"] for m in latest_theme}

    # first date each ticker appears, last date it appears, and a display name
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}
    any_name: dict[str, str] = {}
    for d, snap in snaps:
        for m in snap.get(theme, []):
            t = m["ticker"]
            first_seen.setdefault(t, d)
            last_seen[t] = d
            any_name[t] = m["name"]

    members, missing = [], []
    for t in sorted(first_seen):
        if t not in universe:
            missing.append(t)
            continue
        added = SEED if first_seen[t] == first_date else first_seen[t]
        if t in latest_tickers:
            removed = None
        else:  # gone from the latest board → removed at the first snapshot after it last appeared
            after = [d for d in dates if d > last_seen[t]]
            removed = after[0] if after else None
        ths_nm = latest_name.get(t, any_name.get(t, t))
        members.append({"ticker": t, "added": added, "removed": removed,
                        "name_zh": zh_name(t, ths_nm),
                        "rationale": "同花顺概念成分 · THS concept member"})
    return members, missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch a today snapshot before building")
    ap.add_argument("--curated-only", action="store_true",
                    help="build ONLY the 50 hand-curated baskets (skip auto-adding the rest of the THS taxonomy)")
    args = ap.parse_args()

    members_p = config.data_dir() / "china_search" / "members.parquet"
    closes_p = config.data_dir() / "china_search" / "closes.parquet"
    if not closes_p.exists():
        log.error("china_search cache missing (%s) — cannot seed", closes_p)
        return 1
    meta = pd.read_parquet(members_p) if members_p.exists() else pd.DataFrame()
    universe = set(pd.read_parquet(closes_p, columns=None).columns)
    # widen to the deep per-name OHLC store the confluence ENGINE actually prices from
    # (engine.basket_index._load_member_ohlcv → data/china_stocks), so more THS concepts qualify.
    cs_dir = config.data_dir() / "china_stocks"
    if cs_dir.exists():
        universe |= {p.stem for p in cs_dir.glob("*.parquet")}

    def zh_name(t: str, fallback: str) -> str:
        if not meta.empty and t in meta.index and pd.notna(meta.loc[t, "name_zh"]):
            return str(meta.loc[t, "name_zh"]).replace(" ", "")
        return fallback

    _latest_snapshot(args.refresh)        # ensure ≥1 snapshot exists (fetches on first run)
    snaps = _all_snapshots()
    if not snaps:
        log.error("no THS snapshots available — run with --refresh")
        return 1

    out_baskets: dict[str, dict] = {}
    skipped = []
    for bid, ths_name, en, catkey, th_en, th_zh in CURATED:
        members, missing = _pit_members(ths_name, snaps, universe, zh_name)
        if len(members) < 3:
            skipped.append(f"{bid}({ths_name}):{len(members)}")
            continue
        cat_en, cat_zh = CATS[catkey]
        out_baskets[bid] = {
            "name": en, "name_zh": ths_name,
            "category": cat_en, "category_zh": cat_zh,
            "etf_proxy": None, "etf_proxy_note": "",
            "created": SEED, "weighting": "equal",
            "thesis": th_en, "thesis_zh": th_zh,
            "members": members,
            "ths_concept": ths_name,
            "changelog": [{"date": SEED, "action": "import",
                           "note": f"Imported 同花顺 concept '{ths_name}' — "
                                   f"{len(members)} members in cache"
                                   f"{f', {len(missing)} outside' if missing else ''}."}],
        }

    # ── auto-add EVERY OTHER THS concept (beyond the curated set) with >=3 priced members ──
    # The curated entries carry hand-written English labels / categories / theses; every other THS
    # concept board adopts its 同花顺 name verbatim (name_zh) with an optional English label +
    # category from the translation map (data/baskets_china_ths/concept_en_map.json, produced by the
    # haiku translate pass) and a generic thesis. This widens the desk from the curated handful to
    # the FULL priced THS taxonomy. Skipped (and curated) silently if --curated-only.
    if not args.curated_only:
        from collectors.china_ths_concepts import concept_code_map
        codes = concept_code_map()
        en_map_p = config.data_dir() / "baskets_china_ths" / "concept_en_map.json"
        en_map = json.loads(en_map_p.read_text()) if en_map_p.exists() else {}
        curated_names = {row[1] for row in CURATED}
        n_auto = 0
        n_event, n_thin = 0, 0
        dropped_event = []
        for ths_name in snaps[-1][1].keys():
            if ths_name in curated_names:
                continue
            if _is_event_board(ths_name):          # skip event / news / mechanical boards
                n_event += 1
                dropped_event.append(ths_name)
                continue
            code = codes.get(ths_name)
            if not code:
                continue
            members, missing = _pit_members(ths_name, snaps, universe, zh_name)
            if len(members) < AUTO_MIN_MEMBERS:    # too thin to auto-import (curated set is exempt)
                n_thin += 1
                continue
            bid = "thsc" + str(code)
            if bid in out_baskets:
                continue
            tr = en_map.get(ths_name) or {}
            out_baskets[bid] = {
                "name": tr.get("en") or ths_name, "name_zh": ths_name,
                "category": tr.get("category_en") or "THS Concept",
                "category_zh": tr.get("category_zh") or "同花顺概念",
                "etf_proxy": None, "etf_proxy_note": "",
                "created": SEED, "weighting": "equal",
                "thesis": f"同花顺 concept board '{ths_name}' — {len(members)} priced A-share members.",
                "thesis_zh": f"同花顺概念板块「{ths_name}」——{len(members)} 只有价A股成分。",
                "members": members, "ths_concept": ths_name,
                "changelog": [{"date": snaps[-1][0], "action": "auto-import",
                               "note": f"Auto-imported 同花顺 concept '{ths_name}' ({len(members)} priced members)."}],
            }
            n_auto += 1
        log.info("auto-added %d non-curated THS concepts (>=%d priced members); "
                 "dropped %d event/news/mechanical boards, %d too thin (<%d)",
                 n_auto, AUTO_MIN_MEMBERS, n_event, n_thin, AUTO_MIN_MEMBERS)
        if dropped_event:
            log.info("  event/news boards dropped: %s", ", ".join(sorted(dropped_event)))

    # ── dedupe near-identical concepts (Jaccard >= threshold) — keep the broader / curated one ──
    # The flat THS taxonomy has heavy overlap (a stock sits in ~4 concepts), so many auto boards are
    # near-redundant slices of one theme; they inflate correlated entry-now / double-buy signals.
    # Curated baskets are protected (never dropped); only an AUTO board is dropped as a duplicate.
    _order = ([b for b in out_baskets if not b.startswith("thsc")] +
              sorted([b for b in out_baskets if b.startswith("thsc")],
                     key=lambda b: -len(out_baskets[b]["members"])))
    kept_sets: list[tuple[str, set]] = []
    dropped_dup = []
    for bid in _order:
        ms = {m["ticker"] for m in out_baskets[bid]["members"] if not m.get("removed")}
        dup_of = next((kb for kb, ks in kept_sets if _jaccard(ms, ks) >= JACCARD_DEDUPE), None)
        if dup_of and bid.startswith("thsc"):
            dropped_dup.append(f"{out_baskets[bid]['name_zh']}≈{out_baskets[dup_of]['name_zh']}")
            del out_baskets[bid]
        else:
            kept_sets.append((bid, ms))
    if dropped_dup:
        log.info("deduped %d near-identical auto concepts (Jaccard>=%.2f): %s",
                 len(dropped_dup), JACCARD_DEDUPE, ", ".join(dropped_dup))

    if not out_baskets:
        log.error("no THS baskets built — check the snapshot / universe overlap")
        return 1
    if skipped:
        log.warning("skipped %d themes with <3 covered members: %s", len(skipped), ", ".join(skipped))

    payload = {
        "version": snaps[-1][0], "seed_date": SEED, "curated": snaps[-1][0],
        "source": "tonghuashun_concept_boards", "snapshots": [d for d, _ in snaps],
        "benchmark": "510300.SS", "benchmark_label": "CSI 300", "benchmark_label_zh": "沪深300",
        "construction": CONSTRUCTION, "history_note": HISTORY_NOTE, "note": NOTE,
        "baskets": out_baskets,
    }
    out_dir = config.data_dir() / "baskets_china_ths"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_p = out_dir / "membership.json"
    out_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    n_members = sum(len(v["members"]) for v in out_baskets.values())
    log.info("wrote %s — %d THS baskets, %d members (from %d snapshot(s))",
             out_p, len(out_baskets), n_members, len(snaps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
