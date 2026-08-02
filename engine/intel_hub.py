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

SCHEMA = "intel_hub.command.v2"   # v2: ranked by edge-remaining/opportunity (not desk agreement)
# v3: price-trajectory spine + T1-T4 entry gate. Stamped into hub.json AND each track-record
# snapshot row so the forward grader can segment the pre/post-inversion-fix era.
ENGINE_VERSION = "hub-v3-trajectory"

# Footer copy: one sentence (DESIGN_DOCTRINE Law 4 — one footnote per panel, no stack).
# The tripwire that docks conviction still runs; its LANGUAGE is not front-facing
# (operator order 2026-07-27, #3821 — falsifier/refutation wording never ships to a
# glance surface). The ranking method itself lives in the hero's `?` popover (Tier 2).
DISCLAIMER = (
    "Context only — five research desks fused into one read per name, never a trade "
    "instruction and never a position size."
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

# ── EDGE-REMAINING reframe (V2) ──────────────────────────────────────────── #
# Leading desks see smart-money/activity FLOW before price; lagging desks only
# confirm AFTER the move is already visible. The pre-consensus edge is a LEADING
# desk firing while the lagging desks are still quiet — the opposite of the
# agreement the v1 composite rewarded.
_LEADING = ("alt", "radar")
_LAGGING = ("news", "standout", "policy")

# radar lifecycle → how much of the move is still ahead (1 = all ahead, 0 = late)
_LIFECYCLE_EDGE = {"emerging": 1.0, "forming": 0.82, "mature": 0.34, "fading": 0.12}
# factor buy-board label → how early in the move (keyword match, first hit wins)
_LABEL_EDGE = (
    ("BOTTOMING", 0.95), ("NEARING A LOW", 0.95), ("EMERGING", 0.92),
    ("BUY ZONE", 0.74), ("UNCONFIRMED TURN", 0.70), ("TURN", 0.70),
    ("ACCUMULAT", 0.80), ("UPTREND", 0.40), ("CONFIRMED", 0.40), ("EXTENDED", 0.12),
)
# special-situation categories that carry genuine forward optionality (a fresh,
# dated, under-reacted catalyst) vs administrative/terminal events
_CATALYST_LIVE = {"Acquisitions", "Activist Campaigns", "Strategic Reviews", "Spin-Offs",
                  "Going-Private", "Tender Offers", "Issuer Tenders", "Capital Returns",
                  "Restructuring", "Rights Offerings", "M&A / Divestitures", "Divestitures"}
_CATALYST_FRESH_D = 45        # a catalyst older than this has been digested
_OFF_DESK_INJECT = 12         # cap off-desk discovery names injected into the ranked command list


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


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


def _policy_usable(facet: dict | None) -> bool:
    """A policy facet is usable for direction/flags/gap only when its conviction is not
    low or absent.  Low-conviction leans contribute NOTHING — the flags go dark while all
    shipped leans are ungraded.  A future n_graded>0 condition can be added here in one
    place once the scoreboard (W1) ships grades."""
    if not facet:
        return False
    conv = facet.get("conviction")
    return conv not in (None, "low")


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
    pd = policy.get("dir") if _policy_usable(policy) else None
    return {"news": nd, "alt": ad, "radar": rd, "standout": sd, "policy": pd}


# --------------------------------------------------------------------------- #
# EDGE REMAINING — how much of the move is still AHEAD (V2 pricing-in axis).
# Built entirely from fields the feeders already compute and the v1 hub threw
# away. 1.0 = early / lots of room; 0.0 = late / fully priced-in. Degrades to a
# neutral 0.5 when a name has no priced-in inputs (e.g. news-only).
# --------------------------------------------------------------------------- #
def _edge_remaining(v: dict, dirs: dict, vel_rec: dict, catalyst: dict | None,
                    discovery: dict | None = None, traj: dict | None = None) -> dict:
    radar = v.get("radar") or {}
    standout = v.get("standout") or {}
    alt = v.get("alt") or {}
    news = v.get("news") or {}
    traj = traj or {}
    rolling_over = bool(traj.get("rolling_over"))
    comps: list[tuple[float, float, str]] = []   # (weight, score, driver)

    lc = (radar.get("lifecycle") or "").lower()
    if lc in _LIFECYCLE_EDGE:
        comps.append((1.4, _LIFECYCLE_EDGE[lc], f"radar {lc}"))

    wbp = _f(radar.get("within_basket_pct"))
    if wbp is not None and radar.get("state") in _POS_RADAR:
        # a basket laggard reads as "room to run" ONLY if the name isn't itself broken.
        # A rolling-over laggard has no room — the drawdown is the tape pricing it down,
        # not an opportunity — so the room credit is killed (0) and flagged as a drag.
        room = 0.0 if rolling_over else _clamp01(1.0 - wbp)
        comps.append((0.8, room,
                      "broken laggard (no room)" if rolling_over else
                      "basket laggard (room)" if wbp < 0.4 else "basket leader (priced-in)"))

    lab = (standout.get("label") or "").upper()
    if lab:
        le = next((s for k, s in _LABEL_EDGE if k in lab), 0.5)
        comps.append((0.9, le, f"buy-board {lab.lower()}"))

    # off-high drawdown discount: prefer the buy-board's value, fall back to the shared
    # trajectory spine (yahoo-adjusted) so the discount is ALWAYS live for a name with
    # price history — not silently absent because the name isn't on the buy-board.
    oh = _f(standout.get("off_high"))
    if oh is None:
        oh_frac = _f(traj.get("off_high_252"))
        oh = oh_frac * 100.0 if oh_frac is not None else None   # spine is a fraction; buy-board is pct
    if oh is not None:                                 # 0 = at highs (priced), −22%+ = room
        # a rolling-over name's drawdown is NOT room — it is a falling knife, so the
        # off-high "room" credit is capped low rather than rewarding the crash.
        oh_score = 0.1 if rolling_over else _clamp01(0.15 + (-oh) / 22.0)
        comps.append((0.6, oh_score,
                      f"{oh:.0f}% off high (falling)" if rolling_over else
                      f"{oh:.0f}% off high" if oh < -2 else "at the highs"))

    # crowding discount — a loud, high-magnitude, accelerating tape is already paid for
    if news:
        ns = abs(_f(news.get("sentiment_score")) or 0.0)
        nrec = int(news.get("n_recent") or 0)
        accel = vel_rec.get("accel")
        crowd = 0.45 * _clamp01(nrec / 6.0) + 0.35 * ns + (0.20 if (accel is not None and accel >= 1.0) else 0.0)
        comps.append((0.9, _clamp01(1.0 - crowd),
                      "loud, crowded tape" if crowd > 0.55 else "quiet tape (room)"))

    if alt.get("extended") is True:
        comps.append((0.7, 0.05, "extended (anti-chase)"))

    rs = _f(alt.get("rs_vs_spy_60d"))
    if rs is None:
        rs = _f(radar.get("rs_vs_spy_60d"))
    if rs is None:
        rs = _f(traj.get("rs_vs_spy_60d"))              # shared spine fallback — always live w/ price
    if rs is not None:
        comps.append((0.7, _clamp01(1.0 - max(rs, 0.0) / 40.0) if rs > 0 else 1.0,
                      f"RS {rs:+.0f}% vs SPY"))

    if catalyst and catalyst.get("live"):
        ds = catalyst.get("days_since")
        if ds is not None:
            comps.append((0.7, _clamp01(1.0 - ds / float(_CATALYST_FRESH_D)),
                          f"fresh {(catalyst.get('category') or 'catalyst').lower()}"))

    n_base = len(comps)                                    # genuine (non-discovery) priced-in evidence
    if discovery:                                          # off-desk leading accumulation = some room
        dsc = _f(discovery.get("disc_score"))
        if dsc is not None:
            # anti-chase: a discovery leg cannot claim 'room' on an already-extended / run-up name,
            # and is a MODEST leg (low base, lower weight) so one off-tape feed can't drive edge.
            ext = alt.get("extended") is True
            hc = 0.25 if ext else (0.5 if (rs is not None and rs > 40) else 1.0)
            comps.append((0.5, _clamp01((0.18 + 0.5 * dsc) * hc),
                          f"discovery: {(discovery.get('source') or '').replace('_', ' ')}"))

    if not comps:
        return {"score": 0.4, "n_components": 0, "n_base": 0, "drivers": []}   # conservative, not a free 0.5
    wsum = sum(w for w, _, _ in comps)
    score = sum(w * s for w, s, _ in comps) / wsum
    ranked = sorted(comps, key=lambda c: c[1], reverse=True)
    drivers = [c[2] for c in ranked[:2]]               # the most edge-positive reasons
    if len(comps) > 2 and ranked[-1][1] < 0.35:        # surface the biggest drag — only if not already shown
        drivers.append("⚠ " + ranked[-1][2])
    return {"score": round(_clamp01(score), 3), "n_components": len(comps),
            "n_base": n_base, "drivers": drivers}


# --------------------------------------------------------------------------- #
# LEADING-vs-LAGGING gap — the inverted agreement reward. Pays a leading desk
# (smart-money flow / a positive divergence) firing while the lagging desks
# (news, momentum buy-board, policy) are still quiet. gap > 0 ⇒ flow is AHEAD of
# the crowd (pre-consensus); gap ≤ 0 ⇒ price/news already lead (late).
# --------------------------------------------------------------------------- #
def _leading_gap(v: dict, dirs: dict) -> dict:
    radar = v.get("radar") or {}
    rstate = radar.get("state")
    radar_lead = 1 if rstate == "POSITIVE_DIVERGENCE" else 0   # CONFIRMED_UP is coincident, not leading
    alt_lead = 1 if dirs.get("alt") == 1 else 0
    lead_up = radar_lead + alt_lead
    lag_up = ((1 if dirs.get("news") == 1 else 0)
              + (1 if dirs.get("standout") == 1 else 0)
              + (1 if rstate == "CONFIRMED_UP" else 0)
              + (1 if dirs.get("policy") == 1 else 0))
    # lagging desks that are PRESENT — a "quiet crowd" only counts when the crowd's desks
    # exist and are silent, not when their data is merely absent.
    lag_present = ((1 if v.get("news") else 0)
                   + (1 if v.get("standout") else 0)
                   + (1 if dirs.get("policy") is not None else 0)
                   + (1 if rstate == "CONFIRMED_UP" else 0))
    return {"lead_up": lead_up, "lag_up": lag_up, "gap": lead_up - lag_up, "lag_present": lag_present}


def _stage(edge: float, gap: int, lean: int, flags: list, n_components: int, lag_present: int,
           rolling_over: bool = False) -> str:
    """Place the name on the idea lifecycle. The hub ranks edge-remaining, so this label is
    the headline read: emerging/early = where the edge is; consensus/exhausted = already
    priced; distribution = desks lean down and price is rolling over; FALTERING = the price
    is rolling over (deep off-high, falling, below the 50d) regardless of what the desks lean."""
    # PRICE VETO — a name whose own price is rolling over can NEVER be an emerging/early edge,
    # no matter how bullish the desks read. It is faltering (bullish-but-broken) or, if the
    # desks also lean down, distribution/exhausted. This is the anti-inversion floor.
    if rolling_over:
        if lean < 0:
            return "exhausted" if edge < 0.30 else "distribution"
        return "faltering"
    if "crowded_top" in flags:                            # loud top — fade regardless of net lean
        return "exhausted"
    if lean < 0:                                          # desks lean DOWN
        return "exhausted" if edge < 0.30 else "distribution"
    if lean == 0:
        return "building"
    # bullish (lean > 0) ----------------------------------------------------------------
    if edge < 0.30:
        return "exhausted"
    # EMERGING (top tier): leading flow ahead of a quiet-but-PRESENT crowd, with room AND
    # ≥2 pieces of priced-in evidence — never a thin, data-sparse single hit.
    if edge >= 0.66 and gap >= 1 and n_components >= 2 and lag_present >= 1:
        return "emerging"
    if edge >= 0.50 and gap >= 0:                         # leading not behind the crowd
        return "early"
    return "consensus"                                    # bullish but priced-in / price-led (gap < 0)


# --------------------------------------------------------------------------- #
# The per-ticker dossier — composite conviction + 2nd/3rd-order flags
# --------------------------------------------------------------------------- #
def _dossier(t: str, v: dict, pidx: dict, vel: dict, catalyst: dict | None = None,
             discovery: dict | None = None, traj: dict | None = None,
             entry_gate: dict | None = None, gov: dict | None = None) -> dict:
    news = v.get("news") or {}
    alt = v.get("alt") or {}
    radar = v.get("radar") or {}
    brain = v.get("brain") or {}
    sectors = news.get("sectors") or []
    policy = _policy_for(t, sectors, pidx)
    dirs = _dirs(v, policy)
    traj = traj or {}
    rolling_over = bool(traj.get("rolling_over"))

    # a low-conviction policy facet must contribute NOTHING — it must not inflate
    # composite (via len(present)) nor appear in source_mix / n_facets.
    present = [k for k in ("news", "alt", "radar", "standout") if v.get(k)] + (["policy"] if _policy_usable(policy) else [])
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
    # early_edge requires a USABLE policy lean (conviction not low/absent); a low-conviction
    # thesis cannot trigger the flag — the UI must go dark while leans are ungraded.
    policy_early = (_policy_usable(policy) and policy["dir"] == 1 and dirs["alt"] == 1
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
    # policy_aligned / policy_conflict only fire when the facet is USABLE
    if _policy_usable(policy) and lean != 0 and policy["dir"] == lean and policy["dir"] != 0:
        flags.append("policy_aligned")
    if _policy_usable(policy) and lean != 0 and policy["dir"] == -lean:
        flags.append("policy_conflict")
    if nv.get("spike"):
        flags.append("velocity_spike")

    # ── V2: edge-remaining + leading-gap → opportunity (the new ranking key) ──
    gap = _leading_gap(v, dirs)
    edge = _edge_remaining(v, dirs, nv, catalyst, discovery, traj)
    signal_core = _f(brain.get("strength")) or 0.0            # genuine magnitude, NOT agreement
    if discovery:                                             # BOUNDED boost — discovery never SUBSTITUTES for signal
        dlift = (_f(discovery.get("disc_score")) or 0.0) * 0.7
        signal_core = signal_core + 0.35 * max(0.0, dlift - signal_core)
    # continuous leading-gap multiplier — no binary cliff: ±15% per net leading desk, capped ±2
    gap_mult = 1.0 + 0.15 * max(-2, min(2, gap["gap"]))
    opportunity = round(min(100.0, 100.0 * signal_core * fals_pen * edge["score"] * gap_mult), 1)
    # ── SIGNAL GOVERNOR (de-escalation only) — close the measure→act loop ──────────────────
    # If a feeder has been PROVEN mis-firing by its matured, overlap-robust track record
    # (engine.signal_governor), scale DOWN the opportunity of the names it is bullishly driving.
    # trust ∈ [floor,1] ⇒ opportunity can only fall, never rise. No governor / healthy ⇒ no-op.
    # The STAGE label is left ungoverned (it describes the feeders' read); only the RANK moves.
    gov_mult, governed_by = 1.0, []
    if gov and lean > 0:
        rt = gov.get("radar", 1.0)
        if rt < 1.0 and radar.get("state") in _POS_RADAR:
            gov_mult *= rt
            governed_by.append("radar")
    if gov_mult < 1.0:
        opportunity = round(opportunity * gov_mult, 1)
    # the lifecycle gate uses NON-discovery evidence (n_base) so a single off-tape discovery
    # feed cannot, by itself, label a name 'emerging' or push it into the actionable cohort.
    # rolling_over is the price VETO — a broken name can never read emerging/early.
    stage = _stage(edge["score"], gap["gap"], lean, flags, edge["n_base"], gap["lag_present"],
                   rolling_over=rolling_over)
    if rolling_over and "faltering" not in flags:
        flags.append("faltering")
    if stage in ("emerging", "early") and "confirmed_trend" in flags:
        flags.remove("confirmed_trend")                       # pre-consensus ⇒ not a confirmed consensus
    if stage == "emerging":
        flags.append("emerging")
    if catalyst and catalyst.get("live"):
        flags.append("catalyst")
    if discovery:
        flags.append("discovery")

    # a single human-facing read (3rd-order synthesis)
    read = _read_for(flags, lean, n_confirm, policy, stage, edge, gap)

    return {
        "ticker": t, "name": news.get("name") or (v.get("standout") or {}).get("name") or t,
        "sectors": sectors[:3], "baskets": (news.get("baskets") or [])[:3],
        "composite_conviction": composite, "lean": lean,
        "opportunity_score": opportunity, "edge_remaining": edge["score"],
        "governor_mult": round(gov_mult, 3), "governed_by": governed_by or None,
        "edge_drivers": edge["drivers"], "edge_components": edge["n_components"], "stage": stage,
        "entry_gate": entry_gate, "trajectory": traj or None,
        "leading_gap": gap["gap"], "lead_up": gap["lead_up"], "lag_up": gap["lag_up"],
        "lag_present": gap["lag_present"], "catalyst": catalyst, "discovery": discovery,
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


def _read_for(flags: list, lean: int, n_confirm: int, policy: dict | None,
              stage: str = "", edge: dict | None = None, gap: dict | None = None) -> str:
    pct = int(round((edge or {}).get("score", 0.5) * 100))
    g = (gap or {}).get("gap", 0)
    if stage == "emerging":
        return (f"A leading desk is firing {('ahead of ' + str(g) + ' still-quiet ') if g else 'into a quiet '}"
                f"lagging desk{'s' if g != 1 else ''}, with ~{pct}% of the move still ahead"
                + (" and a policy tailwind" if _policy_usable(policy) and policy.get("dir") == 1 else "")
                + (" plus a fresh catalyst" if "catalyst" in flags else "")
                + " — pre-consensus, where the edge is.")
    if "early_edge" in flags or "stealth_accumulation" in flags:
        return ("Smart money + radar are positioning into a quiet tape"
                + (" with a policy tailwind" if _policy_usable(policy) and policy.get("dir") == 1 else "")
                + f" — stealth accumulation, ~{pct}% of the move still ahead.")
    if stage == "early":
        return f"A leading desk leads, the tape is still catching up — early, ~{pct}% edge remaining."
    if "crowded_top" in flags or stage == "exhausted":
        return ("Loud-bullish tape while smart money fades / radar diverges negative — "
                f"crowded / distribution risk, only ~{pct}% edge left; a late entry to fade.")
    if stage == "distribution":
        return ("Desks lean bearish and price is rolling over — distribution; "
                "de-risk / avoid, not a long.")
    if "confirmed_trend" in flags or stage == "consensus":
        return (f"{n_confirm} desks agree and price has confirmed — consensus, "
                f"~{pct}% edge remaining; own it, don't chase it.")
    if "fading" in flags:
        return "Smart-money and the radar are cooling — momentum fading; an early de-risk."
    if "policy_conflict" in flags:
        return "Desks lean one way but policy intent cuts the other — unresolved; size small."
    if "policy_aligned" in flags:
        return ("Desks lean " + ("up" if lean > 0 else "down")
                + " with policy intent on the same side — aligned momentum.")
    if lean > 0:
        return f"Modestly constructive across the desks that fired (~{pct}% edge remaining)."
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
# catalyst index — fuse the already-built Special Situations desk as a dated,
# under-reacted event leg (6th desk). Strictly context.
# --------------------------------------------------------------------------- #
def _catalyst_index(special: dict | None, today: date) -> dict:
    """ticker → fresh special-situation catalyst with days_since + a live-optionality flag."""
    out: dict[str, dict] = {}
    bt = (special or {}).get("by_ticker")
    for t, rec in (bt.items() if isinstance(bt, dict) else []):
        k = (t or "").upper().strip()
        if not k or not isinstance(rec, dict):
            continue
        ds, d = None, rec.get("date")
        if d:
            try:
                ds = (today - date.fromisoformat(str(d)[:10])).days
            except (ValueError, TypeError):
                ds = None
        cat = rec.get("category")
        out[k] = {"category": cat, "stage": rec.get("stage") or "", "date": d,
                  "days_since": ds, "brief": (rec.get("brief") or "")[:240],
                  "source": rec.get("source"), "confidence": rec.get("confidence"),
                  "live": (cat in _CATALYST_LIVE) and (ds is None or ds <= 120)}
    return out


def _discovery_dossier(cand: dict, catalyst: dict | None,
                       traj: dict | None = None,
                       entry_gate: dict | None = None) -> dict:
    """A dossier for an OFF-desk discovery candidate — a name not in any feeder's universe,
    surfaced purely by a leading scan (radar QUIET-accumulating / federal velocity)."""
    t = (cand.get("ticker") or "").upper()
    dsc = _f(cand.get("disc_score")) or 0.0
    # UNCAPPED strength (insider clusters carry it; others fall back to disc_score). Orders same-
    # cap discovery names via the ranked tie-break (composite_conviction) WITHOUT lifting the
    # opportunity ceiling above the source's display cap — so a strong insider cluster surfaces
    # above a marginal one, and neither out-ranks a validated lead.
    strength = _f(cand.get("cluster_strength"))
    strength = strength if strength is not None else dsc
    edge = round(_clamp01(0.55 + 0.4 * dsc), 3)            # off-desk leading signal ⇒ room
    opp = round(min(100.0, 100.0 * (dsc * 0.7) * edge * 1.15), 1)
    flags = ["discovery"] + (["catalyst"] if (catalyst and catalyst.get("live")) else [])
    nulls = {"news": None, "alt": None, "radar": None, "standout": None, "policy": None}
    return {
        "ticker": t, "name": t, "sectors": [], "baskets": [],
        "composite_conviction": round(strength * 60, 1), "lean": 1,
        "opportunity_score": opp, "edge_remaining": edge,
        "edge_drivers": [cand.get("reason") or "off-desk leading signal"],
        "edge_components": 1, "stage": "discovery",
        "entry_gate": entry_gate, "trajectory": traj or None,
        "leading_gap": 1, "lead_up": 1, "lag_up": 0, "lag_present": 0,
        "catalyst": catalyst, "discovery": cand,
        "n_confirm": 1, "n_dissent": 0, "n_facets": 0, "agreement": 1.0,
        "source_mix": ["discovery"], "directions": dict(nulls),
        "policy": None, "velocity": None, "sentiment_score": 0.0, "second_order": None,
        "falsifier": None, "falsifier_penalty": 1.0, "peer_confirm": 0, "peers": [],
        "flags": flags, "read": cand.get("reason") or "Off-desk leading accumulation — not on any desk yet.",
        "facets": dict(nulls), "evidence": cand.get("reason", ""),
    }


# --------------------------------------------------------------------------- #
# ENTRY GATE — the owner's validated T1-T4 confluence buy verdict per name.
# A ⚡ prime-entry badge (is_buyable) + a flat-sell flag the hero list gates on.
# Reads the pre-built site/factordata/signal_gate.json (slim buy_signal verdicts);
# computes on demand from the yahoo close for a surfaced name absent from it.
# --------------------------------------------------------------------------- #
def _load_gate_index() -> dict:
    """The pre-built T1-T4 confluence verdicts: {TICKER: buy_signal}. Degrade-safe."""
    d = _read("site/factordata/signal_gate.json") or {}
    return d.get("verdicts") or {}


def _entry_gate(t: str, gate_index: dict, traj_closes=None) -> dict | None:
    """The validated-confluence entry verdict for a name. Uses the pre-built verdict when
    present; else computes on demand from the yahoo close series. Returns a compact badge
    dict {eligible, tier, buyable, flat_sell} or None when neither path has price.

    flat_sell = the gate says NOT a buy (ineligible / no fresh confluence) — the exact
    condition the hero list must EXCLUDE (SMCI/AVGO/MPWR/NVDA all read flat_sell)."""
    from engine import signal_gate as SG
    v = gate_index.get(t)
    if v is None and traj_closes is not None and len(traj_closes) >= 60:
        try:
            full = SG.gate(t, traj_closes)
            v = SG.buy_signal(full)
        except Exception:  # noqa: BLE001
            v = None
    if v is None:
        return None
    buyable = SG.is_buyable(v)
    eligible = bool(v.get("eligible"))
    return {"eligible": eligible, "tier": v.get("tier_cascade"),
            "buyable": buyable, "flat_sell": not eligible}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _diversify_by_source(items: list, n: int, per_source: int, src) -> list:
    """Top `n` from a score-ordered list while capping any single source to `per_source`,
    so one prolific feed (e.g. 100+ insider clusters pinned at the score cap) can't
    monopolize a surface. Under-fill tops up from the leftovers in score order. PURE."""
    picked, counts, seen = [], {}, set()
    for i, it in enumerate(items):
        s = src(it)
        if counts.get(s, 0) < per_source:
            picked.append(it)
            counts[s] = counts.get(s, 0) + 1
            seen.add(i)
            if len(picked) >= n:
                return picked
    for i, it in enumerate(items):                       # under-filled → ignore the cap
        if i not in seen:
            picked.append(it)
            if len(picked) >= n:
                break
    return picked


def build(bundle: dict | None, policy: dict | None, macro_context: dict | None = None,
          today: date | None = None, top: int = 30, special: dict | None = None,
          discovery: dict | None = None) -> dict:
    """Fuse the intelligence bundle + policy + catalysts into the central command view,
    ranked by EDGE REMAINING (opportunity), not desk agreement. PURE-ish (load_velocity
    touches a ledger). Never raises."""
    today = today or date.today()
    tickers = (bundle or {}).get("tickers") or {}
    pidx = build_policy_index(policy)
    vel = load_velocity(tickers, today)
    cidx = _catalyst_index(special, today)
    didx = (discovery or {}).get("by_ticker") or {}
    # SIGNAL GOVERNOR — the per-feeder trust map (de-escalation only). Absent/corrupt ⇒ {}
    # (identity), so a hub with no governor file ranks byte-identically to before. Never raises.
    try:
        from engine import signal_governor
        gov = signal_governor.load_trust(config.ROOT)
    except Exception:  # noqa: BLE001 — governor is additive, never fatal to the build
        gov = {}
    # PRICE-TRAJECTORY spine + validated entry gate — the anti-inversion pair. Load the
    # yahoo close ONCE per name (reused for both the trajectory read and any on-demand gate),
    # so a rolling-over / broken name can be vetoed out of the hero list and stage.
    from engine.trajectory import _yahoo_closes, snapshot as _traj_snap
    gate_index = _load_gate_index()

    def _price_read(t: str):
        closes = _yahoo_closes(t, config.ROOT)
        traj = _traj_snap(t, config.ROOT, closes=closes) if closes is not None else None
        egate = _entry_gate(t, gate_index, closes)
        return traj, egate

    _pr = {t: _price_read(t) for t in tickers}
    dossiers = [_dossier(t, v, pidx, vel, cidx.get(t), didx.get(t),
                         traj=_pr[t][0], entry_gate=_pr[t][1], gov=gov) for t, v in tickers.items()]
    # DISCOVERY: inject OFF-desk candidates (not in any feeder's universe) as their own dossiers.
    # Bound the injection to the strongest few (off_desk is disc-sorted) so a large lagging-
    # confirmer feed (e.g. insider clusters) can't flood the ranked command list; the rest still
    # live in the Discovery section via the candidate feed.
    off = [c for c in ((discovery or {}).get("off_desk") or [])
           if (c.get("ticker") or "").upper() not in tickers][:_OFF_DESK_INJECT]
    # Extend _pr with off-desk tickers so the discovery dossier gets trajectory + entry_gate.
    for c in off:
        ot = (c.get("ticker") or "").upper()
        if ot and ot not in _pr:
            _pr[ot] = _price_read(ot)
    dossiers += [_discovery_dossier(c, cidx.get((c.get("ticker") or "").upper()),
                                    traj=_pr.get((c.get("ticker") or "").upper(), (None, None))[0],
                                    entry_gate=_pr.get((c.get("ticker") or "").upper(), (None, None))[1])
                 for c in off]
    _peer_confirm(dossiers)                              # 3rd-order: theme-wide vs isolated
    # V2 RANKING: opportunity = signal × edge-remaining × leading-gap. Tie-break on
    # composite conviction. This DEMOTES the confirmed/consensus cohort the v1 sort floated
    # to the top and PROMOTES the early, leading-desk-ahead, not-yet-priced names.
    dossiers.sort(key=lambda d: (d["opportunity_score"], d["composite_conviction"]), reverse=True)

    # HERO GATE — a name can headline the "Emerging edge" hero ONLY if BOTH hold:
    #   (a) its price is NOT rolling over (the trajectory veto — enforced in _stage too), AND
    #   (b) the owner's validated T1-T4 confluence gate AFFIRMATIVELY reads eligible.
    # Absence of evidence is NOT admission: a name with no gate verdict and no price
    # history (e.g. a crashed small-cap outside every price store) must not headline on
    # the strength of what we can't see — it stays in the ranked command list with its
    # honest stage, but the flagship hero strip demands positive confirmation.
    def _hero_ok(d: dict) -> bool:
        if (d.get("trajectory") or {}).get("rolling_over"):
            return False
        eg = d.get("entry_gate")
        if not eg or eg.get("flat_sell") or not eg.get("eligible"):
            return False
        return True

    emerging_hero = [d for d in dossiers if d["stage"] in ("emerging", "early") and _hero_ok(d)]
    exhausted = [d for d in dossiers if d["stage"] in ("exhausted", "distribution", "faltering")]
    catalysts = sorted((d for d in dossiers if "catalyst" in d["flags"]),
                       key=lambda d: ((d.get("catalyst") or {}).get("days_since")
                                      if (d.get("catalyst") or {}).get("days_since") is not None else 9999))
    # DISCOVERY SECTION — the home for off-desk needles. Built DIRECTLY from the candidate feed
    # (sorted by disc_score) so it surfaces the strongest discovery signals regardless of the
    # command-injection cap; only the command LIST is bounded (above), never this section.
    _dossier_by_t = {d["ticker"]: d for d in dossiers}
    discovery_cands = (discovery or {}).get("candidates") or []
    discovery_list = [{"ticker": c.get("ticker"), "discovery": c,
                       "stage": (_dossier_by_t.get(c.get("ticker"), {}).get("stage") or "discovery")}
                      for c in discovery_cands if c.get("ticker")]
    n_discovery_total = (discovery or {}).get("n", len(discovery_list))
    early = [d for d in dossiers if {"early_edge", "stealth_accumulation"} & set(d["flags"])]
    crowded = [d for d in dossiers if "crowded_top" in d["flags"]]
    confirmed = [d for d in dossiers if "confirmed_trend" in d["flags"]]
    policy_conflict = [d for d in dossiers if "policy_conflict" in d["flags"]]
    spikes = [d for d in dossiers if "velocity_spike" in d["flags"]]

    mc = dict(macro_context or {})
    if pidx.get("regime") and "policy_regime" not in mc:
        mc["policy_regime"] = (pidx["regime"] or "")[:400]

    n_emerging = sum(1 for d in dossiers if d["stage"] == "emerging")
    n_early = sum(1 for d in dossiers if d["stage"] == "early")
    n_actionable = sum(1 for d in dossiers[:top]
                       if d["stage"] in ("emerging", "early") and d["leading_gap"] >= 0
                       and d["opportunity_score"] >= 35)
    # T5 COVERAGE TRIPWIRE — count command-list names lacking price data so silent
    # veto-escapes are visible in hub.json (not just a silent None trajectory).
    command_dossiers = dossiers[:top]
    n_command = len(command_dossiers)
    n_with_trajectory = sum(1 for d in command_dossiers if d.get("trajectory") is not None)
    n_without_trajectory = n_command - n_with_trajectory
    if n_without_trajectory > 0:
        tickers_no_price = [d["ticker"] for d in command_dossiers
                            if d.get("trajectory") is None]
        log.warning("hub coverage: %d/%d command names lack price data (veto-escapes): %s",
                    n_without_trajectory, n_command, tickers_no_price)
    _coverage = {
        "command_names": n_command,
        "with_trajectory": n_with_trajectory,
        "without_trajectory": n_without_trajectory,
    }
    return {
        "schema": SCHEMA, "engine_version": ENGINE_VERSION,
        "is_context_only": True, "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "macro_context": mc,
        "desks": {                                          # cross-desk status board
            "news": {"live": any(d["facets"].get("news") for d in dossiers)},
            "alt_data": {"live": any(d["facets"].get("alt") for d in dossiers)},
            "radar": {"live": any(d["facets"].get("radar") for d in dossiers)},
            "standout": {"live": any(d["facets"].get("standout") for d in dossiers)},
            "policy": {"live": bool(pidx["by_ticker"] or pidx["by_sector"])},
            "special": {"live": bool(cidx)},
        },
        "n_universe": len(dossiers), "n_actionable": n_actionable, "n_emerging": n_emerging,
        "n_discovery": n_discovery_total,
        "coverage": _coverage,
        "counts": {"emerging": n_emerging, "early": n_early, "exhausted": len(exhausted),
                   "catalyst": len(catalysts), "discovery": n_discovery_total,
                   "discovery_off_desk": (discovery or {}).get("n_off_desk", 0),
                   "early_edge": len(early), "crowded_top": len(crowded),
                   "confirmed": len(confirmed), "policy_conflict": len(policy_conflict),
                   "velocity_spike": len(spikes),
                   "theme_wide": sum(1 for d in dossiers if "theme_wide" in d["flags"]),
                   "isolated": sum(1 for d in dossiers if "isolated" in d["flags"])},
        "command": dossiers[:top],
        # lightweight per-name rows for the falsifiable track-record (ALL names, not just the
        # top — the cross-sectional IC must see the whole ranking). Stripped before site write.
        "track_rows": [{"t": d["ticker"], "opp": d["opportunity_score"],
                        "edge": d["edge_remaining"], "stage": d["stage"], "lean": d["lean"],
                        "source": (d.get("discovery") or {}).get("source"),   # feed for per-source IC (None = on-desk)
                        "engine_version": ENGINE_VERSION}
                       for d in dossiers],
        "discovery": _diversify_by_source(
            discovery_list, 14, 5, src=lambda d: (d.get("discovery") or {}).get("source")),
        "emerging": [_compact(d) for d in emerging_hero[:14]],
        "exhausted": [_compact(d) for d in exhausted[:12]],
        "catalysts": [_compact(d) for d in catalysts[:12]],
        "divergence_alerts": {"early_edge": [_compact(d) for d in early[:12]],
                              "crowded_top": [_compact(d) for d in crowded[:12]]},
        "policy_conflicts": [_compact(d) for d in policy_conflict[:8]],
        "velocity_spikes": [_compact(d) for d in spikes[:8]],
        "sector_heat": _sector_heat(dossiers, pidx),
        "how_to_use": (
            "The command list is ranked by OPPORTUNITY = genuine signal magnitude × edge "
            "remaining × leading-vs-lagging gap — NOT by how many desks agree (agreement is a "
            "lagging, consensus condition). 'emerging' = a leading desk firing ahead of a quiet "
            "crowd with most of the move still ahead (where the edge is); 'exhausted' = already "
            "run, fade-risk. catalysts = fresh dated special-situation events. Every dossier "
            "names what would change its read and its edge_remaining; track both."),
        "disclaimer": DISCLAIMER,
    }


def _compact(d: dict) -> dict:
    return {k: d[k] for k in ("ticker", "name", "composite_conviction", "opportunity_score",
                              "edge_remaining", "edge_drivers", "stage", "leading_gap", "lean",
                              "n_confirm", "flags", "read", "sectors", "falsifier", "catalyst",
                              "discovery", "entry_gate", "trajectory")
            if k in d}


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
    from engine import intelligence, briefing, intel_discovery
    bundle = intelligence.load_and_build(today)
    policy = _read("site/policy_intent.json")
    macro = briefing.macro_context(today)
    special = _read("site/allocationdata/special_situations.json")
    discovery = intel_discovery.load_and_build(bundle_universe=set(bundle.get("tickers") or {}), today=today)
    return build(bundle, policy, macro, today, top, special=special, discovery=discovery)
