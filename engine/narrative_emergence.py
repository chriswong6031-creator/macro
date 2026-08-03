"""Narrative-emergence desk — turn the theme-discovery radar into a ranked, surfaced
"🔥 Forming Narratives" read with HONESTLY-ranked recommended tickers (multi-market).

This is the FUSION + presentation layer on top of two things the build already computes:
  * engine.theme_discovery — coherent, TIGHTENING groups of names NOT already in a basket
    (the substance: co-movement + change-point), region-parameterized.
  * the GDELT macro-narrative backdrop (site/allocationdata/macro_narrative.json) + the AI
    desk's emerging_watch (site/allocationdata/ai_desk_<region>.json) — the ATTENTION/voice
    overlay, read opportunistically and degrades to nothing when absent.

It produces, per forming narrative:
  * a transparent 0–100 EMERGENCE score (tightening-led, never a return forecast),
  * a handful of RECOMMENDED tickers ranked by ENTRY quality — the LEAST-extended names in
    the cluster first (engine.extension), because thematic groups launch near the top and
    chasing the parabolic names is the documented way to lose money on a real theme,
  * an honest caveat block + a "hype = late" caution when an IPO wave / stretched cohort or
    elevated macro attention is present.

HONEST BY CONSTRUCTION. Detection is noisy and early entries have no reliable return edge.
The score ranks cluster formation, not expected payoff. Nothing here is a buy list or feeds
allocation. Pure/additive — returns None on shortfall, never raises.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "narrative_emergence.v1"

_MARKET = {
    "us": ("US", "美股"), "china": ("China A-shares", "A股"), "hk": ("Hong Kong", "港股"),
    "canada": ("Canada", "加股"), "intl": ("International", "国际"),
}

# transparent 0–100 score weights — tightening-led (the "forming" signal), then co-movement
# strength; momentum/novelty/size are light context. Sums to 1.0.
_W = {"tighten": 0.40, "cohesion": 0.30, "momentum": 0.12, "novelty": 0.10, "size": 0.08}

# coarse equity-sector → GDELT macro-narrative bucket bridge (engine.news_vector themes).
# Used ONLY to flag when a cluster sits under a hot macro narrative (attention = late-entry
# CAUTION), never to lift the score. Loose by design; unmapped → no alignment claim.
_SECTOR_NARRATIVE = {
    "Information Technology": "industrial_policy", "Semiconductors": "industrial_policy",
    "Technology": "industrial_policy", "Communication Services": "industrial_policy",
    "Energy": "geopolitics", "Materials": "trade", "Industrials": "industrial_policy",
    "Financials": "monetary", "Real Estate": "monetary", "Utilities": "monetary",
}

# entry-quality rank per extension grade — least-extended first (clean entry > chase).
_ENTRY_RANK = {"intrend": 1.0, "steady": 0.72, "na": 0.5, "stretched": 0.30, "parabolic": 0.0}


def _read_json(p: Path) -> dict | None:
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        pass
    return None


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else float(x))


def _score_label(score: float) -> dict:
    if score >= 65:
        return {"en": "Forming fast", "zh": "快速成形", "css": "ne-hot"}
    if score >= 50:
        return {"en": "Forming", "zh": "成形中", "css": "ne-warm"}
    if score >= 40:
        return {"en": "Early / watch", "zh": "早期观察", "css": "ne-early"}
    return {"en": "Faint", "zh": "微弱", "css": "ne-faint"}


def _attention_backdrop(root: Path) -> dict | None:
    """The market-level GDELT narrative flow + uncertainty regime — coincident CONTEXT the
    build already writes. Region-agnostic (macro/policy/geo); shown as a backdrop, never a
    trigger. None when absent."""
    mn = _read_json(root / "site" / "allocationdata" / "macro_narrative.json")
    if not mn or not mn.get("dominant_themes"):
        return None
    return {
        "dominant": mn.get("dominant_themes")[:4],
        "window_days": mn.get("window_days"),
        "unscheduled_share": mn.get("unscheduled_share"),
        "note_en": "Current macro, policy and geopolitics context. High attention can mean crowded or late.",
        "note_zh": "当前宏观、政策与地缘背景。关注度高可能代表拥挤或偏晚。",
    }


# Display de-registration (operator ruling 2026-07-27, #3821).  emerging_watch is LLM
# prose printed VERBATIM to users by the Forming Narratives panel, so the scout's old
# "Kill criterion: <condition>" framing reached a user-cycle surface.  The prompt no
# longer asks for one (engine.thematic_desk), but briefs are regenerated on the gated
# desk lane — days-old ai_desk_<region>.json files keep the old wording — so the read
# path rewrites the LABEL into the sanctioned watching register.  The CONDITION text is
# never touched, and the background tripwire semantics are unchanged: this is copy only.
_WATCH_LABEL_RE = re.compile(r"\bkill[\s\-_]?criteri(?:on|a)\s*[:：]\s*|\bkill\s*[:：]\s*",
                             re.IGNORECASE)
_WATCH_NOUN_RE = re.compile(r"\bkill[\s\-_]?criteri(?:on|a)\b", re.IGNORECASE)
WATCH_PREFIX_EN = "Watching for: "


def _watch_register(txt: str) -> str:
    """Swap falsifier-register framing in scout prose for the watching register.

    Label form ("Kill criterion: X" / "Kill: X") becomes "Watching for: X"; a bare noun
    phrase ("its kill criterion") becomes "watch condition".  Idempotent, and a no-op on
    text that never carried the register."""
    return _WATCH_NOUN_RE.sub("watch condition", _WATCH_LABEL_RE.sub(WATCH_PREFIX_EN, txt))


def _ai_watch(root: Path, region: str) -> dict | None:
    """The AI thematic desk's ONE emerging_watch hypothesis for this market, if the (gated)
    LLM layer ran. A graded, checkable WATCH — never a buy. None when the desk is off."""
    b = _read_json(root / "site" / "allocationdata" / f"ai_desk_{region}.json")
    if not b:
        return None
    txt = b.get("emerging_watch")
    if not txt or not str(txt).strip():
        return None
    return {"text": _watch_register(str(txt).strip()), "confidence": b.get("confidence"),
            "as_of": b.get("state_asof") or b.get("generated_at")}


def _friendly_name(cand: dict) -> tuple[str, str]:
    """Deterministic display name for a cluster from its sectors. EN + ZH."""
    secs = [c.get("sector") for c in cand.get("constituents", []) if c.get("sector") not in (None, "—", "")]
    n = cand.get("n")
    if cand.get("label") == "Cross-sector" or not secs:
        # name by the two most-common real sectors when we have them
        from collections import Counter
        top = [s for s, _ in Counter(secs).most_common(2)] if secs else []
        if len(top) >= 2:
            return (f"Cross-sector cluster · {top[0]} + {top[1]}",
                    f"跨板块集群 · {top[0]} + {top[1]}")
        return (f"Cross-sector cluster ({n} names)", f"跨板块集群（{n}只）")
    sec = cand.get("top_sector") or "—"
    return (f"Emerging {sec} cluster", f"新兴 {sec} 集群")


def _why(cand: dict) -> tuple[str, str]:
    coh = int(round(cand["cohesion"] * 100))
    chg = cand["cohesion_chg"]
    mom = cand["mom_window"]
    arrow = "tightening" if chg > 0 else "loosening"
    en = (f"{cand['n']} names are moving together: {coh}% average correlation, co-movement "
          f"{arrow} by {chg:.2f}. Basket overlap is {int(cand['basket_overlap']*100)}%; "
          f"the group is {('up' if mom>=0 else 'down')} {abs(mom)*100:.0f}% over the window.")
    zh = (f"{cand['n']} 只个股同步运动：平均相关性 {coh}%，共动"
          f"{'收紧' if chg>0 else '松动'} {chg:.2f}。"
          f"篮子重叠度 {int(cand['basket_overlap']*100)}%；"
          f"区间内组合{'上涨' if mom>=0 else '下跌'} {abs(mom)*100:.0f}%。")
    return en, zh


def _legs(cand: dict) -> dict:
    """Transparent 0..1 legs feeding the emergence score (for the UI breakdown bar)."""
    tighten = _clip01(cand["cohesion_chg"] / 0.30)
    cohesion = _clip01((cand["cohesion"] - 0.45) / (0.85 - 0.45))
    momentum = _clip01(max(0.0, cand["mom_window"]) / 0.30)
    novelty = 1.0 if cand.get("label") in ("Cross-sector", "New cluster") \
        else _clip01((0.80 - cand.get("top_sector_share", 1.0)) / 0.80)
    n = cand.get("n", 0)
    size = 1.0 if 6 <= n <= 20 else (0.6 if n in (5, 21, 22, 23, 24, 25) else 0.35)
    return {k: round(v, 3) for k, v in
            {"tighten": tighten, "cohesion": cohesion, "momentum": momentum,
             "novelty": novelty, "size": size}.items()}


def _emergence_score(legs: dict) -> float:
    return round(100.0 * sum(_W[k] * legs[k] for k in _W), 1)


def _recommended(cand: dict, ext: dict, top_n: int = 5) -> tuple[list[dict], float]:
    """Rank the cluster's constituents by ENTRY quality (least-extended first) using the
    pre-computed extension signals. Returns (rows, stretched_share)."""
    from engine.extension import GRADES
    rows = []
    stretched = 0
    for m in cand.get("constituents", []):
        t = m["ticker"]
        e = ext.get(t) or ext.get(t.upper()) or {}
        g = e.get("grade", "na")
        if g in ("stretched", "parabolic"):
            stretched += 1
        glabel = GRADES.get(g, GRADES["na"])
        rows.append({
            "ticker": t, "name": m.get("name") or t, "name_zh": m.get("name_zh") or "",
            "sector": m.get("sector"),
            "grade": g, "grade_en": glabel[0], "grade_zh": glabel[1], "grade_css": glabel[2],
            "ext": e.get("ext"), "ext_z": e.get("ext_z"), "near_52wh": e.get("near_52wh"),
            "_rank": _ENTRY_RANK.get(g, 0.5),
        })
    # clean entry first, then least-extended; names with no read sink to the middle.
    rows.sort(key=lambda r: (-r["_rank"], (r["ext"] if r["ext"] is not None else 0.0)))
    n_con = max(1, len(cand.get("constituents", [])))
    for r in rows:
        r.pop("_rank", None)
    return rows[:top_n], round(stretched / n_con, 2)


def _caveats(cand: dict, stretched_share: float, attention_aligned: bool) -> tuple[list, list]:
    en = ["Noisy signal; many clusters fade.",
          "Watchlist only, not a buy signal.",
          "Ticker order favors cleaner entries, not higher expected return."]
    zh = ["信号有噪声，许多集群会消退。",
          "仅作观察清单，并非买入信号。",
          "个股排序偏向更干净的入场点，而非更高预期回报。"]
    if cand.get("ipo_wave"):
        en.append("Recent IPO activity adds hype risk.")
        zh.append("近期 IPO 活跃，炒作风险更高。")
    if stretched_share >= 0.4:
        en.append(f"{int(stretched_share*100)}% of the group is already stretched.")
        zh.append(f"{int(stretched_share*100)}% 的组合已经拉伸。")
    if attention_aligned:
        en.append("Macro attention is high; late-entry risk is higher.")
        zh.append("宏观关注度较高，偏晚入场风险更高。")
    return en, zh


def compute_emergence(region: str = "us", root=None, min_score: float = 40.0) -> dict | None:
    """Build the ranked Forming-Narratives read for one market. Pure/additive; returns None
    when the discovery radar has nothing (or caches are absent). Never raises."""
    region = (region or "us").lower()
    root = Path(root) if root else config.ROOT
    try:
        from engine import theme_discovery as td
        rad = td.discover_candidates(region, root=root)
        if not rad or not rad.get("candidates"):
            return None

        # extension signals for the region's universe, computed once (clean-entry ranking).
        ext: dict = {}
        try:
            from engine.extension import extension_signals
            closes, _ns = td._universe(region)
            if closes is not None and not closes.empty:
                ext = extension_signals(closes)
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_emergence[%s]: extension signals unavailable (%s)", region, e)

        backdrop = _attention_backdrop(root)
        dominant_themes = {d.get("theme") for d in (backdrop or {}).get("dominant", [])}

        narratives = []
        for cand in rad["candidates"]:
            legs = _legs(cand)
            score = _emergence_score(legs)
            if score < min_score:
                continue
            name_en, name_zh = _friendly_name(cand)
            why_en, why_zh = _why(cand)
            recs, stretched_share = _recommended(cand, ext)
            theme = _SECTOR_NARRATIVE.get(cand.get("top_sector"))
            aligned = bool(theme and theme in dominant_themes)
            cav_en, cav_zh = _caveats(cand, stretched_share, aligned)
            narratives.append({
                "name_en": name_en, "name_zh": name_zh,
                "why_en": why_en, "why_zh": why_zh,
                "score": score, "score_label": _score_label(score), "legs": legs,
                "n": cand["n"], "cohesion": cand["cohesion"], "cohesion_chg": cand["cohesion_chg"],
                "momentum": cand["mom_window"], "basket_overlap": cand["basket_overlap"],
                "novelty": {"cross_sector": cand.get("label") in ("Cross-sector", "New cluster"),
                            "top_sector": cand.get("top_sector"),
                            "top_sector_share": cand.get("top_sector_share")},
                "recommended": recs,
                "hype": {"ipo_wave": cand.get("ipo_wave", False),
                         "recent_ipos": cand.get("recent_ipos", []),
                         "stretched_share": stretched_share},
                "attention_aligned": aligned, "attention_theme": theme if aligned else None,
                "caveats_en": cav_en, "caveats_zh": cav_zh,
                "signature": _signature(cand),
            })
        narratives.sort(key=lambda x: -x["score"])
        if not narratives:
            return None

        mkt = _MARKET.get(region, (region.upper(), region))
        return {
            "schema": SCHEMA, "is_context_only": True, "region": region,
            "market_en": mkt[0], "market_zh": mkt[1],
            "as_of": rad.get("as_of"), "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_universe": rad.get("n_universe"), "has_sector_map": rad.get("has_sector_map"),
            "attention": backdrop, "ai_watch": _ai_watch(root, region),
            "narratives": narratives,
            "verdict": "display_only_forming_narratives",
            "note_en": "Emerging clusters not yet in a basket. Use as a watchlist, not a buy list.",
            "note_zh": "尚未纳入篮子的成形集群。用于观察清单，并非买入清单。",
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("narrative_emergence[%s] failed: %s", region, e)
        return None


def _signature(cand: dict) -> str:
    """Stable id for a forming narrative = a hash of its sorted constituent set. Lets the
    alert layer tell a genuinely NEW narrative from one it already flagged, across runs."""
    import hashlib
    basis = "|".join(sorted(m["ticker"].upper() for m in cand.get("constituents", [])))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
