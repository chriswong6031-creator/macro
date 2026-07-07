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


_STAGE_ZH = {"emerging": "萌芽", "early": "早期", "consensus": "共识",
             "exhausted": "见顶/拥挤", "distribution": "派发", "building": "酝酿"}
_LIFECYCLE_EDGE = {"emerging": 1.0, "forming": 0.82, "mature": 0.34, "fading": 0.12}


def _roro_leg(conditions: dict, sign: str) -> tuple[int, float]:
    """RORO/conditions leg: dir aligned to the radar sign, mag = |roro|. Gated to 0 on a
    divergent (split) tape. Reads data/china_regime/latest.json (the corrected path)."""
    try:
        fe = (conditions or {}).get("fear_euphoria") or {}
        cond = (conditions or {}).get("conditions") or {}
        roro = fe.get("roro")
        if roro is None:
            roro = (cond.get("roro") or {}).get("roro")
        if roro is None:
            return 0, 0.0
        roro = float(roro)
        verdict = str((cond.get("confirmation") or {}).get("verdict") or "")
        mag = 0.0 if verdict.startswith("divergent") else min(1.0, abs(roro))
        rdir = 1 if roro > 0.15 else (-1 if roro < -0.15 else 0)
        # confirms a positive divergence when risk-on; conflicts when opposite
        leg_dir = 0
        if rdir:
            leg_dir = 1 if (rdir > 0) == (sign == "positive") else -1
        return leg_dir, mag
    except Exception:  # noqa: BLE001
        return 0, 0.0


def _news_sign_proven() -> bool:
    """Returns True iff china_validation has proven the news_sentiment sign (sign_ok=True,
    proven=True for the news_sentiment family). Until CCTV backfill grades (W4), this returns
    False — the contrarian sign (sign_expected=-1) has n_obs=0 and is structurally unfalsifiable.
    spec §2.3 / D5: demote sign to weight-0 direction / salience-only until it clears the gate."""
    try:
        from engine import china_signal_lab
        fams = china_signal_lab.load_validation()
        ns = fams.get("news_sentiment") or {}
        return bool(ns.get("proven") and ns.get("sign_ok"))
    except Exception:  # noqa: BLE001
        return False


def _conviction(divs: list, news_feed: dict, news_sent: dict, conv_map: dict, policy: dict,
                conditions: dict | None = None) -> list:
    """Independence-WEIGHTED composite per fired divergence (mirrors intel_hub._dossier):
    5 signed legs (radar/altdata/news/policy/conditions) combined geometrically with earned
    weights, rewarded for INDEPENDENT agreement, docked by a falsifier; plus edge-remaining,
    lifecycle stage, leading-gap and an opportunity_score the list is ranked by.

    spec §2.3 / D5 — salience/direction split for the news leg:
      salience   = |z| × coverage (contributes to the magnitude backbone ALWAYS)
      direction  = sign (which way) — ZERO until china_validation news_sentiment family is
                   proven+sign_ok (CCTV backfill, W4). The row carries sign_unproven=True and
                   direction_basis="salience_only" so the UI can label it honestly.
    """
    from engine import china_basket_spine as sp
    from engine import china_conviction as cv
    try:
        from engine import china_signal_lab
        W = china_signal_lab.leg_weights_for("conviction") or {}
    except Exception:  # noqa: BLE001
        W = {}
    wv = [W.get(k, d) for k, d in (("radar", .40), ("altdata", .22), ("news", .20),
                                   ("policy", .10), ("conditions", .08))]
    band = (news_sent or {}).get("band")
    by_basket = (news_feed or {}).get("by_basket") or {}
    news_sign_proven = _news_sign_proven()
    out = []
    for d in divs or []:
        try:
            # Skip venue-family rows — they have no sector ETF and their outcome metric
            # has not matured; injecting them into _conviction would mislabel the gap as
            # a sector RS reading. Re-enable once n_resolved >= 3 venue rows exist.
            if d.get("family") == "venue":
                continue
            etf = d.get("sector_etf")
            sign = d.get("sign")
            strength = float(d.get("strength") or 0.0)
            rel = d.get("reliability") or {"basis": "unproven", "n_resolved": 0}
            rel_factor = 1.0
            hr, nres = rel.get("hit_rate"), rel.get("n_resolved") or 0
            if nres >= 3 and hr is not None:
                rel_factor = max(0.15, min(1.5, 1.5 * float(hr)))
            baskets = sp.etf_to_basket().get(etf, [])
            news_hits = sum(int(by_basket.get(b, 0)) for b in baskets)
            members = []
            for b in baskets:
                members += sp.basket_members(b)
            members = list(dict.fromkeys(members))
            aligned, conv_signed = [], []
            for t in members:
                info = conv_map.get(t)
                if not info:
                    continue
                c = info.get("convergence", 0.0)
                conv_signed.append(c)
                if (sign == "positive" and c > 0.1) or (sign == "negative" and c < -0.1):
                    aligned.append((t, info))
            altdata_mag = (sum(abs(i["convergence"]) for _t, i in aligned) / len(aligned)) if aligned else 0.0
            altdata_dir = 0
            if conv_signed:
                s = sum(conv_signed)
                ad_side = 1 if s > 0 else (-1 if s < 0 else 0)
                altdata_dir = 1 if (ad_side > 0) == (sign == "positive") and ad_side else (-1 if ad_side else 0)
            # spec §2.3 / D5 — salience/direction split for the news leg.
            # SALIENCE: |z| × coverage — always contributes to the magnitude backbone; this is
            # what we know (coverage of the story) without needing to know the direction.
            # DIRECTION: the contrarian sign (sign_expected=-1) has n_obs=0 in china_validation
            # (CCTV backfill not yet run). Until proven+sign_ok clears the gate (W4), news_dir
            # is held at 0 — it does NOT steer direction. The salience path keeps news_mag so
            # the leg still boosts salience (what matters) without injecting a direction.
            z = (news_sent or {}).get("z")
            # salience component: raw |z| presence (always)
            news_salience_mag = (min(1.0, news_hits / 3.0) * min(1.0, abs(z) if isinstance(z, (int, float)) else 0.0)) if news_hits else 0.0
            if news_sign_proven:
                # proven path: contrarian sign is active — z<0 confirms positive divergence, z>0 confirms negative
                news_dir = 0
                if news_hits and isinstance(z, (int, float)) and z != 0:
                    news_dir = 1 if ((z < 0 and sign == "positive") or (z > 0 and sign == "negative")) else -1
                news_mag = (min(1.0, news_hits / 3.0) * (1.0 if news_dir > 0 else 0.5)) if news_hits else 0.0
                news_direction_basis = "proven_contrarian"
            else:
                # unproven path (D5): direction = 0; salience preserved via news_mag = |z|-weighted coverage
                news_dir = 0
                news_mag = news_salience_mag
                news_direction_basis = "salience_only"
            policy_term = _policy_term(d.get("signal_key"), policy)
            policy_dir = 1 if policy_term >= 0.7 else (-1 if policy_term <= 0.0 and (policy or {}).get("stance") == "tightening" else 0)
            cond_dir, cond_mag = _roro_leg(conditions, sign)
            radar_mag = strength * rel_factor
            # geometric-leaning magnitude backbone over PRESENT legs only — absent legs are
            # passed as None (cv.combine skips them); passing 0.0 would crush the composite.
            altdata_c = altdata_mag if aligned else None
            news_c = news_mag if news_hits else None
            policy_c = policy_term if policy else None
            cond_c = cond_mag if cond_dir != 0 else None
            base = cv.combine(radar_mag, altdata_c, news_c, policy_c, cond_c, weights=wv)
            # independence tally — for direction tally, news_dir=0 when sign is unproven so it
            # neither boosts up nor drags dn; it appears in the up count ONLY when sign is proven.
            legs = [("radar", 1, radar_mag), ("altdata", altdata_dir, altdata_mag),
                    ("news", news_dir, news_mag), ("policy", policy_dir, policy_term),
                    ("conditions", cond_dir, cond_mag)]
            up = sum(1 for _n, dr, mg in legs if dr > 0 and mg > 0.05)
            dn = sum(1 for _n, dr, mg in legs if dr < 0 and mg > 0.05)
            n_present = sum(1 for _n, dr, mg in legs if dr != 0 and mg > 0.05)
            net_confirm = up - dn
            agreement = (abs(up - dn) / n_present) if n_present else 0.0
            conf_bonus = min(1.25, 1.0 + 0.08 * max(net_confirm - 1, 0))
            # falsifier: a proven-weak prior call, OR a cross-ref conflict on this signal
            fals = 1.0
            if (rel.get("basis") != "unproven" and hr is not None and float(hr) < 0.45 and nres >= 3):
                fals = 0.85
            composite = round(min(100.0, 100.0 * base * conf_bonus * fals * (0.6 + 0.4 * agreement)), 1)
            _bk, ben, bzh = cv.band(composite)
            lean = 1 if up > dn else (-1 if dn > up else 0)
            surfaces = ["radar"] + [n for n, dr, mg in legs[1:] if dr > 0 and mg > 0.05]
            # edge-remaining + lifecycle + leading-gap + opportunity
            lifecycle = d.get("lifecycle") or ("emerging" if (d.get("price_rs_z") or 0) < -0.3 else "forming")
            edge = _edge_remaining(d, news_hits, news_sent, conditions, aligned)
            gap = _leading_gap(sign, altdata_dir, news_dir, policy, conditions)
            stage = _stage(edge["score"], gap["gap"], lean, edge["n_base"], gap["lag_present"], conditions, sign)
            opp = round(min(100.0, 100.0 * radar_mag * fals * edge["score"] * (1 + 0.15 * max(-2, min(2, gap["gap"])))), 1)
            top_members = sorted(aligned, key=lambda x: abs(x[1]["convergence"]), reverse=True)[:3]
            verb_en = "accumulating" if sign == "positive" else "distributing"
            verb_zh = "吸筹" if sign == "positive" else "派发"
            r_en = f"radar {d.get('signal_en')} → {d.get('sector_en')}"
            r_zh = f"雷达 {d.get('signal_zh')} → {d.get('sector_zh')}"
            if news_hits:
                r_en += f" · {news_hits} China headlines"; r_zh += f" · 该主题 {news_hits} 条头条"
            if aligned:
                r_en += f" · {len(aligned)} alt-data members {verb_en}"; r_zh += f" · {len(aligned)} 只成员{verb_zh}"
            if policy_term >= 0.7:
                r_en += " · policy tailwind"; r_zh += " · 政策顺风"
            if cond_dir > 0:
                r_en += " · risk-on tape"; r_zh += " · 风险偏好"
            # qualitative lifecycle clause — NOT a quantified upside prediction (no % claim)
            r_en += f" · {stage}" + (" (leading the crowd)" if gap["gap"] > 0 else "")
            r_zh += f" · {_STAGE_ZH.get(stage, stage)}" + ("（领先于人群）" if gap["gap"] > 0 else "")
            out.append({
                "key": d.get("signal_key"), "sector_en": d.get("sector_en"),
                "sector_zh": d.get("sector_zh"), "sector_etf": etf,
                "radar_sign": sign, "radar_strength": round(strength, 3),
                "surfaces_confirming": surfaces, "n_surfaces": len(surfaces),
                "news_hits": news_hits, "news_band": band,
                "directions": {"radar": 1, "altdata": altdata_dir, "news": news_dir,
                               "policy": policy_dir, "conditions": cond_dir},
                # spec §2.3 — explicit salience/direction decomposition for the news leg.
                # salience: what deserves attention (always honest). direction: sign (only when proven).
                "salience": round(news_salience_mag, 3),
                "direction": news_dir,
                "direction_basis": news_direction_basis,
                "sign_unproven": not news_sign_proven,
                "net_confirm": net_confirm, "agreement": round(agreement, 2), "lean": lean,
                "conf_bonus": round(conf_bonus, 3), "falsifier_penalty": fals,
                "members": [{"ticker": t, "name": i.get("name"),
                             "convergence": i.get("convergence"), "side": i.get("side")}
                            for t, i in top_members],
                "policy_term": policy_term,
                "context_conviction": composite, "composite_conviction": composite,
                "conviction_band": [ben, bzh],
                "edge_remaining": round(edge["score"], 3), "edge_drivers": edge["drivers"],
                "lifecycle": lifecycle, "leading_gap": gap["gap"], "stage": stage,
                "stage_zh": _STAGE_ZH.get(stage, stage), "opportunity_score": opp,
                "rationale_en": r_en, "rationale_zh": r_zh,
                "hypothesis_en": d.get("hypothesis_en"), "hypothesis_zh": d.get("hypothesis_zh"),
                "reliability": rel,
                "note": "CONTEXT salience, never a size or trade",
            })
        except Exception as e:  # noqa: BLE001
            log.debug("conviction row failed (%s)", e)
            continue
    out.sort(key=lambda r: (r["opportunity_score"], r["composite_conviction"]), reverse=True)
    return out


def _edge_remaining(d: dict, news_hits: int, news_sent: dict, conditions: dict, aligned: list) -> dict:
    """How much of the move is still ahead (weighted mean of 0..1 components). Mirrors
    intel_hub._edge_remaining with China-native fields."""
    comps = []   # (weight, score, driver)
    rel = d.get("reliability") or {}
    if rel.get("basis") == "unproven":
        comps.append((1.0, 0.7, "early, untested"))
    elif rel.get("hit_rate") is not None and float(rel.get("hit_rate") or 0) > 0.5:
        comps.append((1.0, 0.45, "pattern already plays out"))
    rs = d.get("price_rs")
    if rs is not None:
        comps.append((0.9, max(0.0, min(1.0, 1.0 - max(float(rs), 0.0) / 15.0)),
                      "sector not yet outperformed" if float(rs) <= 0 else "sector already +RS"))
    if aligned:
        mean_pct = sum((i.get("rank_pctile") or 50) for _t, i in aligned) / len(aligned) if any("rank_pctile" in i for _t, i in aligned) else 50
        comps.append((0.8, max(0.0, min(1.0, 1.0 - mean_pct / 100.0)), "laggard members accumulating"))
    fe = (conditions or {}).get("fear_euphoria") or {}
    if news_hits >= 4 and str(fe.get("band", "")).lower() in ("greed", "euphoria", "贪婪", "亢奋"):
        comps.append((0.7, 0.2, "loud + euphoric (priced)"))
    if not comps:
        return {"score": 0.4, "drivers": ["no components (conservative)"], "n_base": 0}
    wsum = sum(w for w, _s, _drv in comps)
    score = sum(w * s for w, s, _drv in comps) / wsum
    return {"score": round(score, 3), "drivers": [drv for _w, _s, drv in comps],
            "n_base": sum(1 for w, _s, _drv in comps if w >= 0.8)}


def _leading_gap(sign: str, altdata_dir: int, news_dir: int, policy: dict, conditions: dict) -> dict:
    """Leading flow (radar divergence + altdata) minus lagging confirmers (loud news, already-
    eased policy, risk-on tape). gap>0 = leading the crowd."""
    lead = 1 + (1 if altdata_dir > 0 else 0)   # a fired radar divergence is LEADING either sign
    stance = (policy or {}).get("stance")
    fe = (conditions or {}).get("fear_euphoria") or {}
    roro = fe.get("roro")
    risk_on = isinstance(roro, (int, float)) and float(roro) > 0.15
    lag = (1 if news_dir > 0 else 0) + (1 if stance == "easing" else 0) + (1 if risk_on else 0)
    lag_present = (1 if news_dir != 0 else 0) + (1 if stance else 0) + (1 if roro is not None else 0)
    return {"gap": lead - lag, "lead": lead, "lag": lag, "lag_present": lag_present}


def _stage(edge: float, gap: int, lean: int, n_base: int, lag_present: int,
           conditions: dict, sign: str) -> str:
    fe = (conditions or {}).get("fear_euphoria") or {}
    euphoric = str(fe.get("band", "")).lower() in ("greed", "euphoria", "贪婪", "亢奋")
    if euphoric and gap < 0:
        return "exhausted"
    if lean < 0:
        return "distribution" if sign == "positive" else "exhausted"
    if edge >= 0.66 and gap >= 1 and n_base >= 2 and lag_present >= 1:
        return "emerging"
    if edge >= 0.50 and gap >= 0:
        return "early"
    return "consensus"


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
    # scheduled catalysts — skip items whose date has already passed; expired catalysts
    # would otherwise score salience=1.0 (days clamped to 0) and top the board spuriously.
    for ev in (news_feed or {}).get("scheduled_ahead", [])[:3]:
        try:
            d = ev.get("date")
            days = (date.fromisoformat(d) - date.today()).days if d else 9
        except (ValueError, TypeError):
            days = 9
        if days < 0:
            continue  # audit fix: past-dated catalysts must not appear on today's board
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
    conditions = _read("data/china_regime/latest.json") or {}   # RORO / fear-euphoria leg (corrected path)
    try:
        from engine import china_altdata
        conv_map = china_altdata.convergence_map()
    except Exception:  # noqa: BLE001
        conv_map = {}

    # Audit fix: detect a stale news feed so the caller knows the news leg is fabricating
    # freshness.  If the feed's own asof lags the analysis asof by >3 days, mark it stale
    # and pass an empty sent dict into what_matters so the stale z-score is excluded.
    analysis_asof = date.fromisoformat(str(asof)) if asof else date.today()
    news_stale = False
    try:
        feed_asof_raw = news_feed.get("asof")
        if feed_asof_raw:
            lag = (analysis_asof - date.fromisoformat(str(feed_asof_raw)[:10])).days
            news_stale = lag > 3
    except (ValueError, TypeError):
        pass
    news_sent_for_matters = {} if news_stale else news_sent

    divs = radar.get("divergences", []) if isinstance(radar, dict) else []
    conviction = _conviction(divs, news_feed, news_sent, conv_map, policy, conditions)
    chains = _chains(policy, news_feed)
    cross_refs = _cross_refs(policy)
    what_matters = _what_matters(conviction, chains, news_feed, news_sent_for_matters)
    what_changed = _what_changed(prev, conviction, policy, news_sent, altdata_mm, news_feed)

    # flagged tickers — names confirmed across surfaces (alt-data + radar lit + news theme)
    flagged = _flagged_tickers(conviction, altdata_mm)

    return {
        "schema": SCHEMA, "is_context_only": True,
        "asof": str(asof) if asof else str(date.today()),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "news_stale": news_stale,          # audit flag: news leg excluded from salience when True
        "conviction": conviction, "chains": chains, "cross_refs": cross_refs,
        "what_matters": what_matters, "what_changed": what_changed,
        "flagged_tickers": flagged,
        # carried so the NEXT run can diff (underscored = internal state)
        "_acc_tickers": [r.get("ticker") for r in (altdata_mm or {}).get("convergence_top", []) if r.get("ticker")],
        "_radar_fires": [f"{c.get('key')}->{c.get('sector_en')}" for c in conviction],
        "_stance": (policy or {}).get("stance"),
        "_sent_band": (news_sent or {}).get("band"),
        # llm_synthesis: cross-surface AI synthesis is not wired yet (W5).
        # Per spec §2.4: degraded output must be ABSENT, not neutral — emit the
        # explicit degraded_reason so the template can render the state rather
        # than silently showing nothing (brain_usable = present AND not degraded).
        "llm_synthesis": None,
        "llm_synthesis_degraded_reason": "not_wired",
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
