"""INTELLIGENCE HUB — the US central command that fuses every signal desk into one read.

The dashboard already fuses four per-ticker facets in engine.intelligence (news flow ·
alt-data signal · divergence radar · factor buy-board). This module adds the FIFTH desk —
Policy Watch — and lifts the whole thing from "facts side by side" to a reasoned, ranked
CENTRAL COMMAND with second- and third-order analysis:

  • per-ticker DOSSIER — the five facets + a cross-source CONFIRMATION count, a single
    composite CONVICTION (0-100) that rewards independent agreement and is DOCKED by an
    unanswered falsifier, the policy tailwind/headwind, news VELOCITY (day-over-day), and
    the 2nd/3rd-order FLAGS that name the setup (stealth_accumulation / early_edge /
    crowded_top / confirmed_trend / fading / policy_aligned / policy_conflict).
  • SECTOR heat — per-GICS roll-up: mean/max conviction, the widest demand-vs-supply
    divergence, the policy tilt, and the early-edge / crowded-top counts.
  • DIVERGENCE alerts — the demand-tape-vs-smart-money disagreements, the highest-
    information names, ranked.
  • COMMAND summary — the macro frame, the priority dossiers, and the cross-desk status
    the future US Mastermind pulls.

CONTEXT-ONLY · DEGRADE-NEVER-RAISE · PURE where it can be. Nothing here scores or sizes a
position; it reasons over already-built artifacts and republishes one coherent command view.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "intel_hub.command.v1"

DISCLAIMER = (
    "Context only. A central command that fuses five independent desks — news flow, "
    "alt-data smart-money, the divergence radar, the factor buy-board, and policy intent — "
    "into one reasoned read per name. Composite conviction rewards INDEPENDENT agreement "
    "across desks and is docked by an unanswered falsifier; the second/third-order flags "
    "name the setup. The bot sizes through its own risk framework; nothing here sizes alone."
)

# lean text -> direction
_LEAN_DIR = {"overweight": 1, "add": 1, "buy": 1, "accumulate": 1, "constructive": 1,
             "underweight": -1, "avoid": -1, "sell": -1, "reduce": -1, "trim": -1,
             "neutral": 0, "watch": 0, "hold": 0}

# policy theme / proxy ETF -> GICS sector ETF (so a theme-level policy lean reaches names)
_THEME_TO_SECTOR = {
    "defense": "XLI", "nuclear": "XLU", "uranium": "XLU", "semiconductors": "XLK",
    "ai": "XLK", "energy": "XLE", "financials": "XLF", "banks": "XLF", "housing": "XLY",
    "industrials": "XLI", "materials": "XLB", "health": "XLV", "reshoring": "XLI",
}
_PROXY_TO_SECTOR = {
    "ITA": "XLI", "XAR": "XLI", "PPA": "XLI", "URA": "XLU", "URNM": "XLU", "NLR": "XLU",
    "SMH": "XLK", "SOXX": "XLK", "XLK": "XLK", "XLF": "XLF", "KRE": "XLF", "XLE": "XLE",
    "XLU": "XLU", "XLI": "XLI", "XLB": "XLB", "XLV": "XLV", "XLY": "XLY", "BIL": None,
}

_POS_RADAR = {"POSITIVE_DIVERGENCE", "CONFIRMED_UP"}
_NEG_RADAR = {"NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"}


def _f(x):
    if x is None or isinstance(x, (dict, list, bool)):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Policy facet — per-ticker tailwind from the Policy Watch theses (subject ticker
# direct, else theme/proxy → sector → member). The 5th desk.
# --------------------------------------------------------------------------- #
def build_policy_index(policy: dict | None) -> dict:
    """{by_ticker: {T: facet}, by_sector: {ETF: facet}, regime: str}. Never raises."""
    by_ticker: dict[str, dict] = {}
    by_sector: dict[str, dict] = {}
    if not isinstance(policy, dict):
        return {"by_ticker": by_ticker, "by_sector": by_sector, "regime": None}
    for th in (policy.get("theses") or []):
        subj = (th.get("subject") or "").upper().strip()
        lean = (th.get("lean") or "").lower()
        d = _LEAN_DIR.get(lean, 0)
        if not subj:
            continue
        facet = {"dir": d, "lean": lean, "conviction": th.get("conviction"),
                 "actor": th.get("actor"), "thesis": (th.get("thesis") or "")[:280],
                 "horizon_d": th.get("horizon_d")}
        # strongest-conviction thesis wins for a given subject
        cur = by_ticker.get(subj)
        if cur is None or abs(d) > abs(cur.get("dir", 0)):
            by_ticker[subj] = facet
        sec = _PROXY_TO_SECTOR.get(subj)
        if sec:
            by_sector.setdefault(sec, facet)
    return {"by_ticker": by_ticker, "by_sector": by_sector,
            "regime": policy.get("regime_context")}


def _policy_for(t: str, sectors: list, pidx: dict) -> dict | None:
    """Policy facet for a name: a direct subject thesis, else its sector's policy tilt."""
    direct = pidx["by_ticker"].get(t)
    if direct:
        return {**direct, "via": "direct"}
    for s in (sectors or []):
        sec = pidx["by_sector"].get((s or "").upper())
        if sec:
            return {**sec, "via": "sector"}
    return None


# --------------------------------------------------------------------------- #
# News velocity — day-over-day n_recent (accruing ledger; None until history exists)
# --------------------------------------------------------------------------- #
def _velocity_ledger_path():
    p = config.ROOT / "data" / "intel_hub"
    p.mkdir(parents=True, exist_ok=True)
    return p / "news_counts.jsonl"


def load_velocity(tickers_today: dict, today: date, persist: bool = True) -> dict:
    """Compute per-ticker news velocity vs the trailing average and append today's counts.
    {T: {n_recent, prior_avg, accel, spike}}. Degrade-safe; None-ish before history."""
    path = _velocity_ledger_path()
    hist: dict[str, list] = {}
    try:
        if path.exists():
            for line in path.read_text().splitlines()[-40:]:   # bounded tail
                row = json.loads(line)
                if row.get("date") == today.isoformat():
                    continue                                   # skip same-day re-runs
                for t, n in (row.get("counts") or {}).items():
                    hist.setdefault(t, []).append(n)
    except Exception as e:  # noqa: BLE001
        log.debug("velocity ledger read failed (%s)", e)

    out, counts = {}, {}
    for t, rec in (tickers_today or {}).items():
        n = int((rec.get("news") or {}).get("n_recent") or 0) if isinstance(rec, dict) else 0
        counts[t] = n
        prior = hist.get(t, [])
        prior_avg = round(sum(prior) / len(prior), 2) if prior else None
        if prior_avg is None:                       # no history yet → no velocity read
            accel, spike = None, False
        elif prior_avg == 0:                         # silence → flow: a spike, but no defined rate
            accel, spike = None, (n >= 3)
        else:
            accel = round((n - prior_avg) / prior_avg, 2)   # honest % change vs the trailing avg
            spike = (n >= 3 and accel >= 1.0)
        out[t] = {"n_recent": n, "prior_avg": prior_avg, "accel": accel, "spike": spike}
    if persist:
        try:
            with path.open("a") as fh:
                fh.write(json.dumps({"date": today.isoformat(), "counts": counts}) + "\n")
        except Exception as e:  # noqa: BLE001
            log.debug("velocity ledger write failed (%s)", e)
    return out


# --------------------------------------------------------------------------- #
# Directions per facet
# --------------------------------------------------------------------------- #
def _dirs(v: dict, policy: dict | None) -> dict:
    news = v.get("news") or {}
    alt = v.get("alt") or {}
    radar = v.get("radar") or {}
    standout = v.get("standout") or {}
    nd = {"pos": 1, "neg": -1}.get(news.get("sentiment_lean")) if v.get("news") else None
    a_s = _f(alt.get("signal_score"))
    ad = None
    if v.get("alt"):
        ad = (1 if (a_s is not None and a_s >= 65 and alt.get("action") != "AVOID")
              else -1 if (alt.get("action") == "AVOID" or (a_s is not None and a_s < 35)) else 0)
    rs = radar.get("state")
    rd = (1 if rs in _POS_RADAR else -1 if rs in _NEG_RADAR else 0) if v.get("radar") else None
    sd = None
    if v.get("standout"):
        lab = (standout.get("label") or "").upper()
        sd = -1 if ("AVOID" in lab or "DOWN" in (standout.get("state") or "").upper()) else 1
    pd = policy.get("dir") if policy else None
    return {"news": nd, "alt": ad, "radar": rd, "standout": sd, "policy": pd}


# --------------------------------------------------------------------------- #
# The per-ticker dossier — composite conviction + 2nd/3rd-order flags
# --------------------------------------------------------------------------- #
def _dossier(t: str, v: dict, pidx: dict, vel: dict) -> dict:
    news = v.get("news") or {}
    alt = v.get("alt") or {}
    radar = v.get("radar") or {}
    brain = v.get("brain") or {}
    sectors = news.get("sectors") or []
    policy = _policy_for(t, sectors, pidx)
    dirs = _dirs(v, policy)

    present = [k for k in ("news", "alt", "radar", "standout") if v.get(k)] + (["policy"] if policy else [])
    nz = [d for d in dirs.values() if d not in (None, 0)]
    up = sum(1 for d in nz if d > 0)
    dn = sum(1 for d in nz if d < 0)
    n_confirm = max(up, dn)                                  # desks leaning the dominant way
    n_dissent = min(up, dn)                                  # desks pointing the other way
    net_confirm = n_confirm - n_dissent                      # INDEPENDENT agreement, net of dissent
    agreement = abs(sum(nz)) / len(nz) if nz else 0.0
    lean = 1 if up > dn else -1 if dn > up else 0

    base = _f(brain.get("priority")) or (
        0.5 * (len(present) / 5.0) + 0.5 * agreement) * (_f(brain.get("strength")) or 0.4)
    # confirmation bonus — rewards INDEPENDENT agreement (net of any dissent), capped at +25%
    conf_bonus = min(1.25, 1.0 + 0.08 * max(net_confirm - 1, 0))
    # falsifier penalty — an unanswered disconfirming observation docks conviction
    falsifier = brain.get("falsifier") or (alt.get("falsifier")) or (radar.get("falsifier"))
    fals_pen = 0.85 if falsifier else 1.0
    composite = round(min(100.0, 100.0 * (base * conf_bonus * fals_pen) * (0.6 + 0.4 * agreement)), 1)

    nv = vel.get(t) or {}
    ns = _f(news.get("sentiment_score")) or 0.0           # net polarity in [-1,1] (magnitude)
    quiet_news = (news.get("n_recent") or 0) <= 1 and not nv.get("spike")
    # loud-bull = bullish sentiment of real MAGNITUDE (not a lone 1-pos headline) + loud
    # (a velocity spike, or sustained volume) — tightens the crowded-top / distribution read.
    loud_bull = (dirs["news"] == 1 and ns >= 0.3) and bool(nv.get("spike") or (news.get("n_recent") or 0) >= 4)

    flags = []
    stealth = dirs["alt"] == 1 and radar.get("state") == "POSITIVE_DIVERGENCE" and quiet_news
    policy_early = (bool(policy and policy["dir"] == 1) and dirs["alt"] == 1
                    and (dirs["radar"] or 0) >= 0 and quiet_news)
    if policy_early:
        flags.append("early_edge")              # the policy-confirmed stealth setup (the superset)
    elif stealth:
        flags.append("stealth_accumulation")
    if loud_bull and (dirs["alt"] == -1 or radar.get("state") == "NEGATIVE_DIVERGENCE"):
        flags.append("crowded_top")
    if up >= 3 and dn == 0:
        flags.append("confirmed_trend")
    # fading is mutually exclusive with a confirmed uptrend (alt==-1 ⇒ dn≥1 ⇒ dn≠0 already,
    # but guard explicitly so the two can never co-fire if _dirs ever changes)
    if dirs["alt"] == -1 and (dirs["radar"] or 0) <= 0 and not loud_bull and not (up >= 3 and dn == 0):
        flags.append("fading")
    if policy and lean != 0 and policy["dir"] == lean and policy["dir"] != 0:
        flags.append("policy_aligned")
    if policy and lean != 0 and policy["dir"] == -lean:
        flags.append("policy_conflict")
    if nv.get("spike"):
        flags.append("velocity_spike")

    # a single human-facing read (3rd-order synthesis)
    read = _read_for(flags, lean, n_confirm, policy)

    return {
        "ticker": t, "name": news.get("name") or (v.get("standout") or {}).get("name") or t,
        "sectors": sectors[:3], "baskets": (news.get("baskets") or [])[:3],
        "composite_conviction": composite, "lean": lean,
        "n_confirm": n_confirm, "n_dissent": n_dissent, "n_facets": len(present),
        "agreement": round(agreement, 2),
        "source_mix": present, "directions": dirs,
        "policy": policy, "velocity": nv if nv else None,
        "sentiment_score": ns, "second_order": (alt.get("second_order") or None),
        "falsifier": falsifier, "falsifier_penalty": fals_pen,
        "flags": flags, "read": read,
        "facets": {"news": news or None, "alt": alt or None, "radar": radar or None,
                   "standout": v.get("standout"), "policy": policy},
        "evidence": brain.get("evidence", ""),
    }


def _read_for(flags: list, lean: int, n_confirm: int, policy: dict | None) -> str:
    if "early_edge" in flags or "stealth_accumulation" in flags:
        return ("Smart money + radar are positioning into a quiet tape"
                + (" with a policy tailwind" if policy and policy.get("dir") == 1 else "")
                + " — stealth accumulation before the crowd notices.")
    if "crowded_top" in flags:
        return ("The tape is loud-bullish while smart money fades and the radar diverges "
                "negative — crowded-top / distribution risk; a late entry.")
    if "confirmed_trend" in flags:
        return f"{n_confirm} independent desks agree — a confirmed trend; consensus, less edge left."
    if "fading" in flags:
        return "Smart-money and the radar are cooling — momentum fading; an early de-risk."
    if "policy_conflict" in flags:
        return "Desks lean one way but policy intent cuts the other — unresolved; size small."
    if "policy_aligned" in flags:
        return ("Desks lean " + ("up" if lean > 0 else "down")
                + " with policy intent on the same side — aligned momentum.")
    if lean > 0:
        return "Modestly constructive across the desks that fired."
    if lean < 0:
        return "Modestly cautious across the desks that fired."
    return "No strong cross-desk signal."


# --------------------------------------------------------------------------- #
# Sector heat — GICS roll-up
# --------------------------------------------------------------------------- #
_SECTOR_NAME = {
    "XLB": "Materials", "XLC": "Communication", "XLE": "Energy", "XLF": "Financials",
    "XLI": "Industrials", "XLK": "Technology", "XLP": "Staples", "XLRE": "Real Estate",
    "XLU": "Utilities", "XLV": "Health Care", "XLY": "Discretionary",
}


def _peer_confirm(dossiers: list, min_conv: float = 45.0) -> None:
    """THIRD-ORDER — is a name's signal echoed by its basket/supply-chain peers (a durable
    theme-wide move) or ISOLATED (idiosyncratic / possibly early)? Annotates each dossier
    in place with peer_confirm + peers + a theme_wide / isolated flag."""
    by_basket: dict[str, list] = {}
    for d in dossiers:
        for b in (d.get("baskets") or []):
            by_basket.setdefault(b, []).append(d)
    for d in dossiers:
        peers = set()
        for b in (d.get("baskets") or []):
            for p in by_basket.get(b, []):
                if (p["ticker"] != d["ticker"] and d["lean"] != 0 and p["lean"] == d["lean"]
                        and p["composite_conviction"] >= min_conv):
                    peers.add(p["ticker"])
        d["peer_confirm"] = len(peers)
        d["peers"] = sorted(peers)[:5]
        if d["lean"] != 0 and d["composite_conviction"] >= min_conv:
            if len(peers) >= 2:
                d["flags"].append("theme_wide")     # the whole basket is moving — durable
            elif not peers and d.get("baskets"):
                d["flags"].append("isolated")        # a name-specific signal — early or idiosyncratic


def _sector_heat(dossiers: list, pidx: dict) -> list:
    by: dict[str, list] = {}
    for d in dossiers:
        for s in (d.get("sectors") or []):
            if s in _SECTOR_NAME:
                by.setdefault(s, []).append(d)
    out = []
    for etf, ds in by.items():
        convs = [d["composite_conviction"] for d in ds]
        ee = sum(1 for d in ds if "early_edge" in d["flags"] or "stealth_accumulation" in d["flags"])
        ct = sum(1 for d in ds if "crowded_top" in d["flags"])
        pol = pidx["by_sector"].get(etf)
        out.append({
            "etf": etf, "name": _SECTOR_NAME[etf], "n": len(ds),
            "mean_conviction": round(sum(convs) / len(convs), 1) if convs else 0,
            "max_conviction": round(max(convs), 1) if convs else 0,
            "net_lean": (1 if sum(d["lean"] for d in ds) > 0 else
                         -1 if sum(d["lean"] for d in ds) < 0 else 0),
            "early_edge": ee, "crowded_top": ct,
            "policy_tilt": pol["dir"] if pol else None,
            "top": sorted(ds, key=lambda x: x["composite_conviction"], reverse=True)[0]["ticker"],
        })
    out.sort(key=lambda x: x["mean_conviction"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build(bundle: dict | None, policy: dict | None, macro_context: dict | None = None,
          today: date | None = None, top: int = 30) -> dict:
    """Fuse the intelligence bundle + policy into the central command view. PURE-ish
    (load_velocity touches a ledger). Never raises."""
    today = today or date.today()
    tickers = (bundle or {}).get("tickers") or {}
    pidx = build_policy_index(policy)
    vel = load_velocity(tickers, today)

    dossiers = [_dossier(t, v, pidx, vel) for t, v in tickers.items()]
    _peer_confirm(dossiers)                              # 3rd-order: theme-wide vs isolated
    # rank by composite conviction, tie-break on confirmation breadth
    dossiers.sort(key=lambda d: (d["composite_conviction"], d["n_confirm"]), reverse=True)

    early = [d for d in dossiers if {"early_edge", "stealth_accumulation"} & set(d["flags"])]
    crowded = [d for d in dossiers if "crowded_top" in d["flags"]]
    confirmed = [d for d in dossiers if "confirmed_trend" in d["flags"]]
    policy_conflict = [d for d in dossiers if "policy_conflict" in d["flags"]]
    spikes = [d for d in dossiers if "velocity_spike" in d["flags"]]

    mc = dict(macro_context or {})
    if pidx.get("regime") and "policy_regime" not in mc:
        mc["policy_regime"] = (pidx["regime"] or "")[:400]

    n_actionable = sum(1 for d in dossiers[:top] if d["composite_conviction"] >= 55 and d["n_confirm"] >= 2)
    return {
        "schema": SCHEMA, "is_context_only": True, "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "macro_context": mc,
        "desks": {                                          # cross-desk status board
            "news": {"live": any(d["facets"].get("news") for d in dossiers)},
            "alt_data": {"live": any(d["facets"].get("alt") for d in dossiers)},
            "radar": {"live": any(d["facets"].get("radar") for d in dossiers)},
            "standout": {"live": any(d["facets"].get("standout") for d in dossiers)},
            "policy": {"live": bool(pidx["by_ticker"] or pidx["by_sector"])},
        },
        "n_universe": len(dossiers), "n_actionable": n_actionable,
        "counts": {"early_edge": len(early), "crowded_top": len(crowded),
                   "confirmed": len(confirmed), "policy_conflict": len(policy_conflict),
                   "velocity_spike": len(spikes),
                   "theme_wide": sum(1 for d in dossiers if "theme_wide" in d["flags"]),
                   "isolated": sum(1 for d in dossiers if "isolated" in d["flags"])},
        "command": dossiers[:top],
        "divergence_alerts": {"early_edge": [_compact(d) for d in early[:12]],
                              "crowded_top": [_compact(d) for d in crowded[:12]]},
        "policy_conflicts": [_compact(d) for d in policy_conflict[:8]],
        "velocity_spikes": [_compact(d) for d in spikes[:8]],
        "sector_heat": _sector_heat(dossiers, pidx),
        "how_to_use": (
            "Read macro_context for the frame. The command list is ranked by composite "
            "conviction (independent-desk agreement × strength, docked by an unanswered "
            "falsifier). Spend depth on divergence_alerts — early_edge = smart money before "
            "the crowd; crowded_top = distribution risk. sector_heat shows where the desks "
            "cluster. Every dossier names its falsifier; track it."),
        "disclaimer": DISCLAIMER,
    }


def _compact(d: dict) -> dict:
    return {k: d[k] for k in ("ticker", "name", "composite_conviction", "lean", "n_confirm",
                              "flags", "read", "sectors", "falsifier") if k in d}


# --------------------------------------------------------------------------- #
# load_and_build — read published artifacts and emit the command
# --------------------------------------------------------------------------- #
def _read(rel: str):
    p = config.ROOT / rel
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.warning("intel_hub: read %s failed (%s)", rel, e)
        return None


def load_and_build(today: date | None = None, top: int = 30) -> dict:
    """Read the intelligence bundle + policy + macro frame and emit the command. Never raises."""
    from engine import intelligence, briefing
    bundle = intelligence.load_and_build(today)
    policy = _read("site/policy_intent.json")
    macro = briefing.macro_context(today)
    return build(bundle, policy, macro, today, top)
