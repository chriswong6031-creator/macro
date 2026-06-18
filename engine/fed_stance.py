"""Fed reaction-function read — make monetary-policy STANCE an explicit dimension.

Today the regime model treats policy only IMPLICITLY (via yields / breakevens). This
leaf turns the already-computed, display-only pieces — fed_path (market-implied path +
the market-vs-Fed gap) and catalyst_tone (the FOMC-statement guidance direction) — into
one explicit, named reaction-function descriptor: hawkish / neutral / dovish, with the
market-vs-Fed divergence and what's driving it.

DISCIPLINE: PHASE-0 GATED = DISPLAY-ONLY, NEVER SCORED. It is a descriptor read off
existing leaves; nothing in axes / regime / conditions imports it or sizes from it. It
exists so the dashboard can state the Fed's stance explicitly instead of leaving the
reader to infer it from the curve. A market PRICE (fed_path) is reactive, not an edge.
"""
from __future__ import annotations


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def snapshot(latest: dict | None) -> dict:
    """Return an explicit monetary-stance descriptor from latest.json. Defensive:
    {stance: 'unknown', ...} when the inputs are missing."""
    latest = latest or {}
    fp = latest.get("fed_path") or {}
    gap = fp.get("gap") or {}
    cat = latest.get("catalyst_tone") or {}

    cuts12 = _num(fp.get("implied_cuts_12m"))      # negative = HIKES priced by the market
    guidance = str(cat.get("guidance_direction") or "").strip().lower()  # tightening/easing/on_hold/mixed/unknown
    gap_bp = _num(gap.get("gap_bp"))

    drivers_en, drivers_zh = [], []
    if cuts12 is not None:
        if cuts12 <= -0.25:
            drivers_en.append(f"market prices ~{abs(round(cuts12,1))} hike(s) over 12m")
            drivers_zh.append(f"市场计入未来12个月约{abs(round(cuts12,1))}次加息")
        elif cuts12 >= 0.25:
            drivers_en.append(f"market prices ~{round(cuts12,1)} cut(s) over 12m")
            drivers_zh.append(f"市场计入未来12个月约{round(cuts12,1)}次降息")
        else:
            drivers_en.append("market prices roughly no change over 12m")
            drivers_zh.append("市场计入未来12个月基本不变")
    if guidance in ("tightening", "easing", "on_hold", "mixed"):
        _g = {"tightening": ("statement guidance tightening", "声明指引偏紧"),
              "easing": ("statement guidance easing", "声明指引偏松"),
              "on_hold": ("statement guidance on-hold", "声明指引按兵不动"),
              "mixed": ("statement guidance mixed", "声明指引中性混合")}[guidance]
        drivers_en.append(_g[0]); drivers_zh.append(_g[1])
    if gap_bp is not None and abs(gap_bp) >= 10 and gap.get("lean_en"):
        drivers_en.append(f"{gap.get('lean_en')} ({gap_bp:+.0f}bp)")
        drivers_zh.append(f"{gap.get('lean_zh') or gap.get('lean_en')}（{gap_bp:+.0f}bp）")

    # stance: combine market-implied path + statement guidance
    hawkish = (cuts12 is not None and cuts12 <= -0.5) or guidance == "tightening"
    dovish = (cuts12 is not None and cuts12 >= 1.5) or guidance == "easing"
    if hawkish and not dovish:
        stance, lab_en, lab_zh, color = "hawkish", "Hawkish", "鹰派", "down"
    elif dovish and not hawkish:
        stance, lab_en, lab_zh, color = "dovish", "Dovish", "鸽派", "up"
    elif cuts12 is None and guidance in ("", "unknown"):
        stance, lab_en, lab_zh, color = "unknown", "Unknown", "未知", "muted"
    else:
        stance, lab_en, lab_zh, color = "neutral", "Neutral / on-hold", "中性 / 按兵", "muted"

    return {
        "stance": stance, "label_en": lab_en, "label_zh": lab_zh, "color": color,
        "implied_cuts_12m": cuts12, "guidance": guidance or "unknown",
        "market_vs_fed_bp": gap_bp, "market_vs_fed_en": gap.get("lean_en"),
        "market_vs_fed_zh": gap.get("lean_zh"),
        "drivers_en": drivers_en, "drivers_zh": drivers_zh,
        "is_context_only": True, "phase0": "display-only — never scored",
        "note_en": "Explicit reaction-function read off fed_path + the FOMC-statement guidance. A market price is reactive, not a forecast; display only.",
        "note_zh": "基于 fed_path 与 FOMC 声明指引的显式“反应函数”读数。市场价格是被动反应而非预测；仅供展示。",
    }
