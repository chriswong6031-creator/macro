"""China central-intelligence analysis — the 2nd/3rd-order synthesis across all four surfaces.

LEAF · CONTEXT-ONLY · join + qualitative confluence (no scored axis, no Phase-0 needed;
`context_conviction` is SALIENCE, never a position size). Never imported by any scoring/
regime/allocation path. This is the layer that makes the hub a synthesis instead of a
4-card index, and the single richest block in the Mastermind briefing. It reads the four
already-emitted surface artifacts off disk (build-order is the only dependency) and joins
them through engine.china_basket_spine. Five outputs (each degrades to [] / {}):

  conviction[]   — per fired radar divergence, fused with news + alt-data + policy → a bounded
                   context_conviction (0-100 salience) + word-band + a rationale that NAMES
                   each contributing surface + inherits the radar hypothesis.
  chains[]       — k-of-n confluence over named multi-hop transmission paths.
  cross_refs[]   — divergence-vs-narrative AGREE/CONFLICT (the priced-for-easing read).
  what_matters[] — ranked top-N salience across surfaces, de-duped.
  what_changed{} — diff vs the prior analysis.json (this engine OWNS the diff).

See research/CHINA_INTEL_POWERHOUSE.md §1.2 / §3.2 / §3.3.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_intel_analysis.v1"

# which news/macro themes confirm each radar signal (the policy/news crosswalk)
SIGNAL_THEME = {
    "pboc_easing": {"monetary", "policy"}, "credit_impulse": {"monetary", "policy"},
    "pmi": {"growth", "industrial_policy"}, "ppi": {"monetary", "industrial_policy"},
    "southbound": {"markets"},
}

DISCLAIMER_EN = ("Context only — a cross-surface join, not a signal/score/size. "
                 "context_conviction is salience (how many independent surfaces line up), "
                 "never a position. Chains are falsifiable hypotheses the radar ledger tracks.")
DISCLAIMER_ZH = ("仅作背景——跨面板的关联，而非信号/评分/仓位。context_conviction 是显著性"
                 "（多少独立面板共振），绝非仓位。链条是可证伪的假设，由雷达台账追踪。")


def _read(rel: str):
    try:
        from engine import china_intel_bus as bus
        return bus._read_json(rel)
    except Exception:  # noqa: BLE001
        return None


def _analysis_path() -> Path:
    p = config.ROOT / "site" / "china_intel_analysis" / "analysis.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------- #
# 1. cross-surface conviction (per fired radar divergence)
# --------------------------------------------------------------------------- #
def _policy_term(signal_key: str, policy: dict) -> float:
    if not policy:
        return 0.0                       # missing policy must add no floor (#11)
    stance = (policy or {}).get("stance")
    if signal_key in ("pboc_easing", "credit_impulse"):
        if stance == "easing":
            return 1.0
        preds = (policy or {}).get("predictions") or []
        if any(("cut" in str(p).lower()) or ("降" in str(p)) for p in preds):
            return 0.7
        if stance == "tightening":
            return 0.0
        return 0.5
    return 0.5


def _conviction(divs: list, news_feed: dict, news_sent: dict, conv_map: dict, policy: dict) -> list:
    from engine import china_basket_spine as sp
    from engine import china_conviction as cv
    band = (news_sent or {}).get("band")
    by_basket = (news_feed or {}).get("by_basket") or {}
    out = []
    for d in divs or []:
        try:
            etf = d.get("sector_etf")
            sign = d.get("sign")
            strength = float(d.get("strength") or 0.0)
            baskets = sp.etf_to_basket().get(etf, [])
            news_hits = sum(int(by_basket.get(b, 0)) for b in baskets)
            members = []
            for b in baskets:
                members += sp.basket_members(b)
            members = list(dict.fromkeys(members))
            aligned = []
            for t in members:
                info = conv_map.get(t)
                if not info:
                    continue
                c = info.get("convergence", 0.0)
                if (sign == "positive" and c > 0.1) or (sign == "negative" and c < -0.1):
                    aligned.append((t, info))
            altdata_term = (sum(abs(i["convergence"]) for _t, i in aligned) / len(aligned)) if aligned else 0.0
            # direction from the signed sentiment z (the band string is too coarse — #12)
            z = (news_sent or {}).get("z")
            news_ok = isinstance(z, (int, float)) and ((z > 0 and sign == "positive") or (z < 0 and sign == "negative"))
            news_term = (min(1.0, news_hits / 3.0) * (1.0 if news_ok else 0.5)) if news_hits else 0.0
            policy_term = _policy_term(d.get("signal_key"), policy)
            raw = 0.40 * strength + 0.25 * news_term + 0.25 * altdata_term + 0.10 * policy_term
            cc = cv.to_100(raw)
            _bk, ben, bzh = cv.band(cc)
            surfaces = ["radar"]
            if news_hits:
                surfaces.append("news")
            if aligned:
                surfaces.append("altdata")
            if policy_term >= 0.7:
                surfaces.append("policy")
            top_members = sorted(aligned, key=lambda x: abs(x[1]["convergence"]), reverse=True)[:3]
            verb_en = "accumulating" if sign == "positive" else "distributing"
            verb_zh = "吸筹" if sign == "positive" else "派发"
            r_en = f"radar {d.get('signal_en')} → {d.get('sector_en')}"
            r_zh = f"雷达 {d.get('signal_zh')} → {d.get('sector_zh')}"
            if news_hits:
                r_en += f" · {news_hits} China headlines on the theme"
                r_zh += f" · 该主题 {news_hits} 条中国头条"
            if aligned:
                r_en += f" · {len(aligned)} alt-data members {verb_en}"
                r_zh += f" · {len(aligned)} 只另类数据成员{verb_zh}"
            if policy_term >= 0.7:
                r_en += " · policy tailwind"
                r_zh += " · 政策顺风"
            out.append({
                "key": d.get("signal_key"), "sector_en": d.get("sector_en"),
                "sector_zh": d.get("sector_zh"), "sector_etf": etf,
                "radar_sign": sign, "radar_strength": round(strength, 3),
                "surfaces_confirming": surfaces, "n_surfaces": len(surfaces),
                "news_hits": news_hits, "news_band": band,
                "members": [{"ticker": t, "name": i.get("name"),
                             "convergence": i.get("convergence"), "side": i.get("side")}
                            for t, i in top_members],
                "policy_term": policy_term,
                "context_conviction": cc, "conviction_band": [ben, bzh],
                "rationale_en": r_en, "rationale_zh": r_zh,
                "hypothesis_en": d.get("hypothesis_en"), "hypothesis_zh": d.get("hypothesis_zh"),
                "reliability": d.get("reliability") or {"basis": "unproven", "n_resolved": 0},
                "note": "CONTEXT salience, never a size or trade",
            })
        except Exception as e:  # noqa: BLE001
            log.debug("conviction row failed (%s)", e)
            continue
    out.sort(key=lambda r: r["context_conviction"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# 2. transmission chains (k-of-n confluence)
# --------------------------------------------------------------------------- #
def _leg(surface, field, aligned, value, en, zh):
    return {"surface": surface, "field": field, "aligned": bool(aligned),
            "value": value, "detail_en": en, "detail_zh": zh}


def _chains(policy: dict, news_feed: dict) -> list:
    try:
        from engine import china_radar as cr
    except Exception:  # noqa: BLE001
        return []
    peas = cr._sig_pboc_easing() or {}
    cred = cr._sig_credit_impulse() or {}
    pmi = cr._sig_pmi() or {}
    sib = cr._sig_southbound() or {}
    stance = (policy or {}).get("stance")
    themes = set((news_feed or {}).get("top_themes") or [])

    def band(k, n):
        # "aligned" not "confirmed" — these legs agree NOW; nothing has been falsification-tested
        f = k / n if n else 0.0
        return "aligned" if f >= 0.6 else ("forming" if f >= 0.3 else "dormant")

    chains = []
    # EASING_REFLATION
    legs = [
        _leg("policy", "stance", stance == "easing", stance, "PBoC stance easing", "央行立场宽松"),
        _leg("radar", "pboc_easing", peas.get("dir") == 1, peas.get("value"),
             "PBoC easing score rising", "宽松分上升"),
        _leg("radar", "credit_impulse", cred.get("dir") == 1, cred.get("value"),
             "Credit impulse improving", "信用脉冲改善"),
        _leg("flow", "southbound", sib.get("dir") == 1, sib.get("value"),
             "Southbound inflow", "南向资金流入"),
        _leg("news", "themes", bool(themes & {"monetary", "policy", "markets"}), None,
             "News skews monetary/policy", "新闻偏货币/政策"),
    ]
    k = sum(1 for l in legs if l["aligned"])
    chains.append({
        "name": "EASING_REFLATION",
        "label_en": "PBoC easing → liquidity → brokers/property → breadth",
        "label_zh": "央行宽松 → 流动性 → 券商/地产 → 市场宽度",
        "k": k, "n": len(legs), "band": band(k, len(legs)), "links": legs,
        "explain_en": f"{k}/{len(legs)} legs of the easing-reflation path align.",
        "explain_zh": f"宽松再通胀路径 {k}/{len(legs)} 段一致。",
        "hypothesis_en": "If the easing path is real, rate-sensitive brokers/property should lead next.",
        "hypothesis_zh": "若宽松路径成立，利率敏感的券商/地产应随后领先。",
    })
    # CYCLICAL_REFLATION
    legs2 = [
        _leg("radar", "pmi", pmi.get("dir") == 1, pmi.get("value"),
             "Mfg PMI expanding", "制造业PMI扩张"),
        _leg("radar", "credit_impulse", cred.get("dir") == 1, cred.get("value"),
             "Credit impulse improving", "信用脉冲改善"),
        _leg("news", "themes", bool(themes & {"industrial_policy", "growth"}), None,
             "News skews industrial/growth", "新闻偏产业/增长"),
    ]
    k2 = sum(1 for l in legs2 if l["aligned"])
    chains.append({
        "name": "CYCLICAL_REFLATION",
        "label_en": "Activity (PMI) + credit → industrial cyclicals",
        "label_zh": "经济活动(PMI)+信用 → 工业周期股",
        "k": k2, "n": len(legs2), "band": band(k2, len(legs2)), "links": legs2,
        "explain_en": f"{k2}/{len(legs2)} legs of the cyclical-reflation path align.",
        "explain_zh": f"周期再通胀路径 {k2}/{len(legs2)} 段一致。",
        "hypothesis_en": "If activity + credit confirm, metals/machinery cyclicals should lead.",
        "hypothesis_zh": "若活动与信用确认，金属/机械周期股应领先。",
    })
    return chains


# --------------------------------------------------------------------------- #
# 3. divergence-vs-narrative cross refs
# --------------------------------------------------------------------------- #
def _cross_refs(policy: dict) -> list:
    try:
        from engine import china_radar as cr
        peas = cr._sig_pboc_easing() or {}
        stance = (policy or {}).get("stance")
        last_moves = (policy or {}).get("last_moves") or []
        has_cuts = any(("cut" in str(m).lower()) or ("降" in str(m)) for m in last_moves)
        if peas.get("dir") == 1 and stance != "easing" and has_cuts:
            return [{
                "signal_key": "pboc_easing", "kind": "conflict",
                "tag_en": "Cuts delivered but the corridor classifier still reads neutral — priced-for-easing, not yet confirmed.",
                "tag_zh": "已有降息/降准，但走廊分类仍为中性——宽松已被预期但尚未确认。",
                "surfaces": ["radar", "policy"],
            }]
    except Exception as e:  # noqa: BLE001
        log.debug("cross_refs failed (%s)", e)
    return []


# --------------------------------------------------------------------------- #
# 4. what matters most (ranked salience, de-duped)
# --------------------------------------------------------------------------- #
def _what_matters(conviction: list, chains: list, news_feed: dict, news_sent: dict,
                  top_n: int = 5) -> list:
    items = []
    # scheduled catalysts
    for ev in (news_feed or {}).get("scheduled_ahead", [])[:3]:
        try:
            d = ev.get("date")
            days = max(0, (date.fromisoformat(d) - date.today()).days) if d else 9
        except (ValueError, TypeError):
            days = 9
        items.append({"kind": "scheduled", "salience": round(1.0 / (1 + days), 3),
                      "label_en": f"{ev.get('name_en')} ({ev.get('md')})",
                      "label_zh": f"{ev.get('name_zh')}（{ev.get('md_zh') or ev.get('md')}）",
                      "detail_en": "Scheduled high-impact China release ahead.",
                      "detail_zh": "即将发布的高影响中国数据。"})
    # news sentiment
    z = (news_sent or {}).get("z")
    if z is not None:
        items.append({"kind": "news", "salience": round(min(1.0, abs(z)), 3),
                      "label_en": f"Media sentiment {(news_sent or {}).get('label_en')}",
                      "label_zh": f"媒体情绪 {(news_sent or {}).get('label_zh')}",
                      "detail_en": f"z {z:+.2f} over {(news_sent or {}).get('n_days')}d.",
                      "detail_zh": f"{(news_sent or {}).get('n_days')}日 z {z:+.2f}。"})
    # radar conviction (dedup on sector+sign keep max)
    seen = {}
    for c in conviction:
        kk = (c.get("sector_en"), c.get("radar_sign"))
        if kk not in seen or c["context_conviction"] > seen[kk]["salience"] * 100:
            seen[kk] = {"kind": "radar", "salience": round(c["context_conviction"] / 100.0, 3),
                        "label_en": f"{c.get('sector_en')} divergence ({c.get('radar_sign')})",
                        "label_zh": f"{c.get('sector_zh')} 背离（{('正向' if c.get('radar_sign')=='positive' else '负向')}）",
                        "detail_en": c.get("rationale_en"), "detail_zh": c.get("rationale_zh")}
    items += list(seen.values())
    # confirmed chains
    for ch in chains:
        if ch["band"] in ("aligned", "forming"):
            items.append({"kind": "chain", "salience": round(ch["k"] / ch["n"], 3),
                          "label_en": f"{ch['label_en']} ({ch['band']})",
                          "label_zh": f"{ch['label_zh']}（{('一致' if ch['band']=='aligned' else '形成中')}）",
                          "detail_en": ch["explain_en"], "detail_zh": ch["explain_zh"]})
    items.sort(key=lambda x: x["salience"], reverse=True)
    for i, it in enumerate(items[:top_n], 1):
        it["rank"] = i
    return items[:top_n]


# --------------------------------------------------------------------------- #
# 5. what changed vs prior run (this engine owns the diff)
# --------------------------------------------------------------------------- #
def _what_changed(prev: dict, conviction: list, policy: dict, news_sent: dict,
                  altdata_mm: dict, news_feed: dict) -> dict:
    out = {"new_accumulation": [], "dropped_accumulation": [], "new_radar_fires": [],
           "resolved_radar": [], "stance_change": None, "sentiment_band_change": None,
           "new_scheduled_within_3d": []}
    if not prev:
        return out          # first run — nothing to diff against
    try:
        # altdata accumulation set (tickers)
        cur_acc = {r.get("ticker") for r in (altdata_mm or {}).get("convergence_top", []) if r.get("ticker")}
        prev_acc = set(prev.get("_acc_tickers") or [])
        out["new_accumulation"] = sorted(cur_acc - prev_acc)[:8]
        out["dropped_accumulation"] = sorted(prev_acc - cur_acc)[:8]
        # radar fires (sector+sign)
        cur_fires = {f"{c.get('key')}->{c.get('sector_en')}" for c in conviction}
        prev_fires = set(prev.get("_radar_fires") or [])
        out["new_radar_fires"] = sorted(cur_fires - prev_fires)[:8]
        out["resolved_radar"] = sorted(prev_fires - cur_fires)[:8]
        # stance
        cur_stance = (policy or {}).get("stance")
        prev_stance = prev.get("_stance")
        if prev_stance and cur_stance and prev_stance != cur_stance:
            out["stance_change"] = {"from": prev_stance, "to": cur_stance}
        # sentiment band
        cur_band = (news_sent or {}).get("band")
        prev_band = prev.get("_sent_band")
        if prev_band and cur_band and prev_band != cur_band:
            out["sentiment_band_change"] = {"from": prev_band, "to": cur_band}
        # scheduled within 3d
        for ev in (news_feed or {}).get("scheduled_ahead", []):
            try:
                if ev.get("date") and (date.fromisoformat(ev["date"]) - date.today()).days <= 3:
                    out["new_scheduled_within_3d"].append(
                        {"name_en": ev.get("name_en"), "name_zh": ev.get("name_zh"), "date": ev.get("date")})
            except (ValueError, TypeError):
                continue
    except Exception as e:  # noqa: BLE001
        log.debug("what_changed failed (%s)", e)
    return out


# --------------------------------------------------------------------------- #
# public
# --------------------------------------------------------------------------- #
def analyze(prev: dict | None = None, asof: date | str | None = None) -> dict:
    """Assemble the central-analysis dict from the on-disk surface emits. Never raises."""
    news_feed = _read("chinanews/feed.json") or {}
    news_sent = _read("chinanews/sentiment.json") or {}
    policy = _read("data/china_policy/latest.json") or {}
    radar = _read("chinaradar/radar.json") or {}
    altdata_mm = _read("chinaaltdata/mastermind.json") or {}
    try:
        from engine import china_altdata
        conv_map = china_altdata.convergence_map()
    except Exception:  # noqa: BLE001
        conv_map = {}

    divs = radar.get("divergences", []) if isinstance(radar, dict) else []
    conviction = _conviction(divs, news_feed, news_sent, conv_map, policy)
    chains = _chains(policy, news_feed)
    cross_refs = _cross_refs(policy)
    what_matters = _what_matters(conviction, chains, news_feed, news_sent)
    what_changed = _what_changed(prev, conviction, policy, news_sent, altdata_mm, news_feed)

    # flagged tickers — names confirmed across surfaces (alt-data + radar lit + news theme)
    flagged = _flagged_tickers(conviction, altdata_mm)

    return {
        "schema": SCHEMA, "is_context_only": True,
        "asof": str(asof) if asof else str(date.today()),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "conviction": conviction, "chains": chains, "cross_refs": cross_refs,
        "what_matters": what_matters, "what_changed": what_changed,
        "flagged_tickers": flagged,
        # carried so the NEXT run can diff (underscored = internal state)
        "_acc_tickers": [r.get("ticker") for r in (altdata_mm or {}).get("convergence_top", []) if r.get("ticker")],
        "_radar_fires": [f"{c.get('key')}->{c.get('sector_en')}" for c in conviction],
        "_stance": (policy or {}).get("stance"),
        "_sent_band": (news_sent or {}).get("band"),
        "llm_synthesis": None,
        "disclaimer_en": DISCLAIMER_EN, "disclaimer_zh": DISCLAIMER_ZH,
    }


def _flagged_tickers(conviction: list, altdata_mm: dict) -> list:
    """Names lit by >=2 surfaces: alt-data accumulation that also sits in a radar-lit basket."""
    from engine import china_conviction as cv
    out, seen = [], set()
    for c in conviction:
        for m in c.get("members", []):
            t = m.get("ticker")
            if not t or t in seen:
                continue
            seen.add(t)
            conv = m.get("convergence")
            out.append({
                "ticker": t, "name": m.get("name"),
                # keep ONE meaning per field: raw signed [-1,1] under its true name, and a
                # 0-100 context_conviction on the SAME scale as conviction[] (was colliding).
                "convergence": conv,
                "context_conviction": cv.to_100(abs(conv or 0)),
                "side": "long-context" if c.get("radar_sign") == "positive" else "short-context",
                "surfaces": ["altdata", "radar"] + (["news"] if c.get("news_hits") else []),
                "reasons": [f"alt-data {m.get('side')} in {c.get('sector_en')}",
                            f"radar {c.get('key')} divergence ({c.get('radar_sign')})"],
                "note_en": "Context watchlist, not a recommendation",
                "note_zh": "背景自选，非推荐",
            })
    out.sort(key=lambda r: abs(r.get("convergence") or 0), reverse=True)
    return out[:12]


def build() -> dict | None:
    """Write site/china_intel_analysis/analysis.json (reads its own prior for what_changed)."""
    try:
        prev = _read("china_intel_analysis/analysis.json")
        a = analyze(prev=prev)
        _analysis_path().write_text(
            json.dumps(a, ensure_ascii=False, separators=(",", ":"), default=str))
        log.info("china_intel_analysis: %d conviction · %d chains · %d flagged",
                 len(a["conviction"]), len(a["chains"]), len(a["flagged_tickers"]))
        return a
    except Exception as e:  # noqa: BLE001
        log.error("china_intel_analysis build failed (%s)", e)
        return None
