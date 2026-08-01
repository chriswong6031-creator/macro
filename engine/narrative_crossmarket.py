"""Cross-country narrative cross-reference — DISPLAY-ONLY, heavily gated.

The question the user asked: "is a narrative heating up in one market while still emerging in
another — an early-detection / cross-market read?" The honest research verdict was BUILD-LIMITED:
the phenomenon is real (a theme that leads in one market often shows up in another) but it is
NOT tradeable as a lead-lag signal — cross-market thematic momentum is broadly CONTEMPORANEOUS
(~94% same-period), dies past trading costs, and thematic ETFs bleed. So this engine produces a
DISPLAY-ONLY cross-reference chip, never a scored signal and never an axis, with three hard gates
that encode the user's own caveats:

  1. REGION-SPECIFICITY EXCLUSION. Only genuinely cross-applicable, globally-traded themes are in
     the canon crosswalk (semis, software/AI, defense, robotics, gold, base metals, energy,
     autos/EV, pharma, nuclear, luxury). Region-specific themes — banks, insurers, housing/REITs,
     utilities, telecom, gaming, baijiu, SOE value, the regional sleeves — are deliberately absent,
     so they never get a chip. Domestic credit/rates/regulation don't transfer.
  2. MACRO-REGIME ALIGNMENT. Each market's macro Quad is read; a cross-reference between two
     markets in DIFFERENT regimes is flagged (regime_caveat) so the same theme in a different
     regime isn't read as the same trade.
  3. CO-LISTING / FX caveats. China↔Hong Kong links are flagged (co_listed) because A/H names are
     largely the same companies; a standing FX / market-access caveat rides in the disclaimer.

The output is a per-(region, theme) map of "the same narrative elsewhere" — the other markets'
analog theme with its live score/label, so a user can spot a narrative that is already hot
abroad. Pure read; nothing here feeds a score or an allocation.
"""
from __future__ import annotations

import json
import logging

from lib import config

log = logging.getLogger(__name__)

# Canonical cross-market themes → the analog basket ids in each market. ONLY globally-traded,
# cross-applicable narratives belong here (gate 1: region-specificity exclusion). Curated by hand
# against each market's membership.json.
CANON: dict[str, dict] = {
    "semiconductors": {"en": "Semiconductors", "zh": "半导体",
                       "regions": {"us": ["ai_semiconductors", "semicap_equipment"],
                                   "china": ["cn_semis", "cn_ai_compute"],
                                   "intl": ["intl_semis", "intl_tech_hw"]}},
    "software_ai":    {"en": "Software & AI", "zh": "软件与AI",
                       "regions": {"us": ["ai_software", "non_ai_software"],
                                   "china": ["cn_software"], "canada": ["ca_tech"],
                                   "intl": ["intl_software"]}},
    "defense":        {"en": "Defense & Aerospace", "zh": "国防与航空航天",
                       "regions": {"us": ["defense"], "china": ["cn_defense"], "intl": ["intl_defense"]}},
    "robotics":       {"en": "Robotics & Automation", "zh": "机器人与自动化",
                       "regions": {"us": ["robotics_automation"], "china": ["cn_robotics"],
                                   "intl": ["intl_automation"]}},
    "gold":           {"en": "Gold Miners", "zh": "黄金矿业",
                       "regions": {"us": ["gold_miners"], "china": ["cn_gold"],
                                   "canada": ["ca_gold"]}},
    "base_metals":    {"en": "Base Metals & Mining", "zh": "基本金属与矿业",
                       "regions": {"china": ["cn_metals"], "hk": ["hk_materials"],
                                   "canada": ["ca_base_metals"], "intl": ["intl_mining"]}},
    "energy":         {"en": "Energy (Oil & Gas)", "zh": "能源(油气)",
                       "regions": {"us": ["energy_complex"], "hk": ["hk_energy"],
                                   "canada": ["ca_oil_gas"], "intl": ["intl_energy"]}},
    "autos_ev":       {"en": "Autos & EV", "zh": "汽车与电动车",
                       "regions": {"china": ["cn_autos", "cn_battery"], "hk": ["hk_ev"],
                                   "intl": ["intl_autos"]}},
    "pharma":         {"en": "Pharma & Biotech", "zh": "制药与生物科技",
                       "regions": {"china": ["cn_pharma_cxo", "cn_med_devices"], "hk": ["hk_biotech"],
                                   "intl": ["intl_pharma"]}},
    "nuclear":        {"en": "Nuclear & Uranium", "zh": "核能与铀",
                       "regions": {"us": ["nuclear_power"], "canada": ["ca_uranium"]}},
    "luxury":         {"en": "Luxury & Consumer Brands", "zh": "奢侈品与消费品牌",
                       "regions": {"hk": ["hk_consumer"], "intl": ["intl_luxury"]}},
}

REGION_META: dict[str, dict] = {
    "us":     {"flag": "🇺🇸", "en": "US", "zh": "美国", "dir": "basket"},
    "china":  {"flag": "🇨🇳", "en": "China", "zh": "中国", "dir": "basket_china"},
    "hk":     {"flag": "🇭🇰", "en": "Hong Kong", "zh": "香港", "dir": "basket_hk"},
    "canada": {"flag": "🇨🇦", "en": "Canada", "zh": "加拿大", "dir": "basket_canada"},
    "intl":   {"flag": "🌍", "en": "International", "zh": "国际", "dir": "basket_intl"},
}

# site/<dir>/baskets.json carrying each market's theme_intel
_BASKETS_DATA = {"us": "basketdata", "china": "chinabasketdata", "hk": "hkbasketdata",
                 "canada": "canadabasketdata", "intl": "intlbasketdata"}


def _load_themes(site, region: str) -> dict:
    """region's {bid: slim theme} from site/<dir>/baskets.json (theme_intel). {} on miss."""
    p = site / _BASKETS_DATA[region] / "baskets.json"
    if not p.exists():
        return {}
    try:
        ti = (json.loads(p.read_text()).get("theme_intel") or {})
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for t in ti.get("themes", []):
        out[t["id"]] = {
            "name": t.get("name"), "name_zh": t.get("name_zh", t.get("name")),
            "score": t.get("score"), "label": t.get("label"), "reco": t.get("reco"),
            "rel20": (t.get("perf") or {}).get("20d", {}).get("rel"),
            "accel": t.get("accel_z"),
        }
    return out


def _quad(region: str) -> str | None:
    """The market's macro Quad (regime) for the alignment gate. US → data/regime; others →
    data/<region>_regime. Intl has no single regime snapshot → None (never claims alignment)."""
    grp = "regime" if region == "us" else f"{region}_regime"
    p = config.data_dir() / grp / "latest.json"
    if not p.exists():
        return None
    try:
        q = json.loads(p.read_text()).get("quad")
        return str(q) if q else None
    except Exception:  # noqa: BLE001
        return None


def compute_crossmarket(site=None) -> dict:
    """Build the per-(region, theme) 'same narrative elsewhere' map. Display-only, gated."""
    site = site if site is not None else (config.ROOT / "site")
    themes = {r: _load_themes(site, r) for r in REGION_META}
    quads = {r: _quad(r) for r in REGION_META}

    links: dict[str, dict] = {r: {} for r in REGION_META}
    for canon, spec in CANON.items():
        present = []
        for region, bids in spec["regions"].items():
            for bid in bids:
                t = themes.get(region, {}).get(bid)
                if t and t.get("score") is not None:
                    present.append({"region": region, "bid": bid, **t})
        if len(present) < 2:                          # need ≥2 markets for a cross-reference
            continue
        for e in present:
            others = []
            for o in present:
                if o["region"] == e["region"]:
                    continue
                qe, qo = quads.get(e["region"]), quads.get(o["region"])
                others.append({
                    "region": o["region"], "bid": o["bid"], "name": o["name"], "name_zh": o["name_zh"],
                    "score": o["score"], "label": o["label"], "reco": o["reco"],
                    "rel20": o["rel20"], "accel": o["accel"],
                    "regime_caveat": bool(qe and qo and qe != qo),   # gate 2
                    "co_listed": ({e["region"], o["region"]} == {"china", "hk"}),  # gate 3
                })
            if not others:
                continue
            others.sort(key=lambda x: -(x["score"] or 0))
            # "heating up elsewhere": a clearly-stronger, confirmed/emerging analog in another market
            hotter = [o for o in others if (o["score"] or 0) >= (e["score"] or 0) + 8
                      and o["label"] in ("dominant", "emerging") and not o["regime_caveat"]]
            links[e["region"]][e["bid"]] = {
                "canon": canon, "canon_en": spec["en"], "canon_zh": spec["zh"],
                "others": others,
                "hotter_elsewhere": list(dict.fromkeys(o["region"] for o in hotter)),  # unique, ordered
            }

    return {
        "as_of": _as_of(site),
        "regions": REGION_META, "quads": quads, "links": links,
        "disclaimer": {
            "en": ("Display-only narrative cross-reference — NOT a validated signal and never scored. "
                   "It flags when the SAME globally-traded theme is also scoring well in another "
                   "market (useful to spot a narrative early), but cross-market thematic momentum is "
                   "broadly contemporaneous — no reliable lead-lag, and it dies past trading costs. "
                   "Region-specific themes (banks, housing, utilities, telecom, gaming) are excluded. "
                   "⚠ = the two markets are in different macro regimes; ⇄ = co-listed A/H names "
                   "(China↔HK). Cross-border investing also carries FX and market-access frictions."),
            "zh": ("仅展示的叙事交叉参考 — 并非经验证的信号，从不计分。当同一全球性主题在另一市场也"
                   "表现强劲时给出提示（有助于尽早发现叙事），但跨市场主题动量大体同期 — 无可靠领先滞后，"
                   "且在交易成本后消失。区域特定主题（银行、住房、公用事业、电信、博彩）已排除。"
                   "⚠＝两市场处于不同宏观周期；⇄＝A/H 同源股票（中国↔香港）。跨境投资还涉及汇率与市场准入摩擦。"),
        },
    }


def _as_of(site) -> str | None:
    for r in ("us", "china", "intl"):
        p = site / _BASKETS_DATA[r] / "baskets.json"
        if p.exists():
            try:
                a = (json.loads(p.read_text()).get("theme_intel") or {}).get("as_of")
                if a:
                    return a
            except Exception:  # noqa: BLE001
                pass
    return None
