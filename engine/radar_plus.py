"""Radar PLUS — additive enrichment of the Divergence Radar (Phase 2).

ADDITIVE · POST-EMIT · LEAF. Does NOT touch engine/radar.py or theme_activity.py
(those are actively developed). It reads the already-built site/basketdata/radar.json
and the per-ticker signal artifacts already published by the dashboard, then writes
back NEW per-flag fields — never mutating the existing ones:

  • edge_score (0-100)   — a single conviction/ranking axis: radar salience scaled by
       how many INDEPENDENT confirmation legs agree with the activity direction, then
       adjusted for macro regime and docked for crowding. Lets flags be RANKED.
  • confirm{alt,flows,options,crowd} — wires in signals the radar didn't see, computed
       from each flag's covered tickers:
         alt     — Signal Intelligence Desk score + congress/insider net (smart money)
         flows   — sector-ETF accumulation/distribution (fund_flows)
         options — GEX positioning (skew / put-call OI / dealer gamma regime)
         crowd   — dark-pool/retail crowding → a salience PENALTY, not a signal
  • regime{quad, liquidity, mult} — macro-regime multiplier (cut convictions in a
       tightening / risk-off quad).
  • decay{days_in_state, flip_7d} — from an append-only state history → stale + noisy
       (frequently-flipping) flags lose salience.
  • drivers — the covered tickers actually carrying the confirmation.

Plus a top-level `edge_ranked` (flags sorted by edge_score) and `regime`. Everything
is DISPLAY/CONTEXT — never fused into the radar's own divergence z-score. Degrade-safe.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

_POS_STATES = {"POSITIVE_DIVERGENCE", "CONFIRMED_UP"}
_NEG_STATES = {"NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"}


def _load(rel: str):
    p = config.ROOT / rel
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.debug("radar_plus read %s failed (%s)", rel, e)
        return None


def _num(x):
    """Coerce to float, or None if not a real number (guards dict/str fields)."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _sign(x) -> int:
    v = _num(x)
    return 0 if v is None else (1 if v > 0 else -1 if v < 0 else 0)


# --------------------------------------------------------------------------- #
# per-ticker signal reads (from already-published artifacts)
# --------------------------------------------------------------------------- #
def _alt_index(mm: dict) -> dict:
    return {(s.get("ticker") or "").upper(): s for s in (mm.get("signals") or [])}


def _alt_lean(covered: list, alt_bt: dict, mm_index: dict) -> dict:
    """Smart-money lean across the covered tickers."""
    scores, net, drivers = [], 0, []
    for t in covered:
        t = t.upper()
        sig = mm_index.get(t)
        rec = (alt_bt.get("tickers") or {}).get(t) or {}
        sc = _num((sig or {}).get("signal_score"))
        if sc is not None:
            scores.append(sc)
        cn = _num(rec.get("congress_net")) or 0
        ins = _num(rec.get("insider_net_usd")) or 0
        net += _sign(cn) + _sign(ins)
        if (sc or 0) >= 65 or cn > 0 or ins > 0:
            drivers.append(t)
    if not scores and net == 0:
        return {"present": False}
    avg = round(sum(scores) / len(scores), 1) if scores else None
    lean = 1 if (avg is not None and avg >= 60) or net > 0 else -1 if net < 0 else 0
    return {"present": True, "lean": lean, "avg_signal": avg, "net_smart": net, "drivers": drivers[:5]}


def _flow_lean(covered: list, ff: dict) -> dict:
    """Sector-ETF accumulation vs distribution across covered tickers (fund_flows)."""
    acc = dist = 0
    for t in covered:
        rows = ff.get(t.upper()) or []
        for r in rows:
            d = (r.get("direction") or "").lower()
            if "accumul" in d:
                acc += 1
            elif "distribut" in d:
                dist += 1
    if acc == dist == 0:
        return {"present": False}
    lean = 1 if acc > dist else -1 if dist > acc else 0
    return {"present": True, "lean": lean, "accumulating": acc, "distributing": dist}


def _options_lean(covered: list) -> dict:
    """Options positioning across covered tickers (GEX): call-skew + put/call OI +
    dealer-gamma regime → a soft bullish/bearish positioning lean."""
    leans, n = 0.0, 0
    for t in covered:
        g = _load(f"site/gex/{t.upper()}.json")
        s = (g or {}).get("summary") or {}
        if not s:
            continue
        n += 1
        v = 0.0
        skew = _num(s.get("skew"))
        if skew is not None:
            v += 0.5 if skew > 0 else -0.5 if skew < 0 else 0  # call-skew = bullish lean
        pcr = _num(s.get("put_call_oi_ratio"))
        if pcr is not None:
            v += 0.3 if pcr < 0.9 else -0.3 if pcr > 1.2 else 0  # more calls = bullish
        reg = (s.get("regime") or "").lower()
        if "positive" in reg or "long" in reg:
            v += 0.2          # long-gamma = pinned/stable, mildly supportive
        leans += max(-1.0, min(1.0, v))
    if not n:
        return {"present": False}
    avg = leans / n
    return {"present": True, "lean": _sign(round(avg, 2)), "score": round(avg, 2), "n": n}


def _crowd_penalty(covered: list, alt_bt: dict) -> dict:
    """Crowding from dark-pool distribution + retail (WSB) buzz → a salience penalty
    (chasing a name everyone already sees is lower-edge)."""
    dpi_dist = wsb = 0
    for t in covered:
        rec = (alt_bt.get("tickers") or {}).get(t.upper()) or {}
        if (rec.get("dpi_lean") or "") == "distribution":
            dpi_dist += 1
        if (rec.get("wsb_mentions") or 0) >= 20:
            wsb += 1
    pen = min(15.0, 5.0 * dpi_dist + 4.0 * wsb)
    return {"penalty": round(pen, 1), "dark_pool_distribution": dpi_dist, "retail_buzz": wsb}


# --------------------------------------------------------------------------- #
# macro regime multiplier
# --------------------------------------------------------------------------- #
def _regime() -> dict:
    r = _load("data/regime/latest.json") or _load("site/regimedata/latest.json") or {}
    quad = r.get("quad")
    liq = (r.get("liquidity_overlay") or "")
    # Goldilocks/reflation (q1/q2-ish, growth up) → full conviction; stagflation/deflation
    # or draining liquidity → trim. Coarse but honest.
    mult = 1.0
    gs = r.get("growth_score")
    if gs is not None:
        mult += max(-0.12, min(0.12, float(gs) * 0.12))     # growth tailwind/headwind
    if "drain" in str(liq).lower() or "tight" in str(liq).lower():
        mult -= 0.1
    if (r.get("transition_state") or "").lower() in ("deteriorating", "risk_off"):
        mult -= 0.08
    return {"quad": quad, "quad_name": r.get("quad_name"), "liquidity": liq or None,
            "mult": round(max(0.8, min(1.18, mult)), 3)}


# --------------------------------------------------------------------------- #
# decay — append-only state history
# --------------------------------------------------------------------------- #
def _state_history(today: date) -> dict:
    """Append today's per-basket state, return {basket: {days_in_state, flip_7d}}."""
    from pathlib import Path
    p = config.ROOT / "data" / "radar" / "state_history.jsonl"
    rows = []
    if p.exists():
        for ln in p.read_text().splitlines():
            try:
                rows.append(json.loads(ln))
            except Exception:  # noqa: BLE001
                pass
    return {"_rows": rows, "_path": p, "_today": today}


def _prev_state_and_strip(basket: str, hist: dict) -> tuple:
    """Return (prev_state, state_strip) for a basket.

    prev_state: the state from the most recent history date STRICTLY BEFORE today.
    state_strip: list (oldest→newest, max 14 prior entries) of {"d": "MM-DD", "s": STATE}
                 with today's current state appended as the final entry.
    Both derived from rows with date < today.
    """
    today = hist["_today"]
    today_iso = today.isoformat()
    # All rows for this basket strictly before today, sorted oldest first
    prior = sorted(
        [r for r in hist["_rows"] if r.get("basket") == basket and r.get("date", "") < today_iso],
        key=lambda r: r.get("date", ""),
    )
    prev_state = prior[-1].get("state") if prior else None
    # Build strip from the last 14 prior rows
    strip_rows = prior[-14:]
    strip = [{"d": r["date"][5:], "s": r["state"]} for r in strip_rows]  # "MM-DD"
    return prev_state, strip


def _decay_for(basket: str, state: str, hist: dict) -> dict:
    rows = [r for r in hist["_rows"] if r.get("basket") == basket]
    rows.sort(key=lambda r: r.get("date", ""))
    days_in_state = 1
    for r in reversed(rows):
        if r.get("state") == state:
            days_in_state += 1
        else:
            break
    today = hist["_today"]
    from datetime import timedelta
    wk = (today - timedelta(days=7)).isoformat()
    recent = [r for r in rows if r.get("date", "") >= wk]
    flips = sum(1 for a, b in zip(recent, recent[1:]) if a.get("state") != b.get("state"))
    return {"days_in_state": days_in_state, "flip_7d": flips}


# --------------------------------------------------------------------------- #
# public: enrich radar.json in place-ish
# --------------------------------------------------------------------------- #
def enrich(radar: dict, today: date | None = None) -> dict:
    """Add edge_score + confirm legs + regime + decay + drivers to each flag, plus a
    top-level edge_ranked + regime + changes. Mutates and returns `radar`. Never raises."""
    today = today or date.today()
    today_mmdd = today.isoformat()[5:]  # "MM-DD"
    flags = radar.get("flags") or []
    alt_bt = _load("site/altdata/by_ticker.json") or {}
    mm = _load("site/altdata/mastermind.json") or {}
    mm_index = _alt_index(mm)
    ff = _load("site/stockdata/fund_flows.json") or {}
    regime = _regime()
    hist = _state_history(today)
    new_history = []

    for f in flags:
        try:
            covered = (f.get("observable") or {}).get("covered") or []
            state = f.get("state") or "QUIET"
            obs_dir = (f.get("observable") or {}).get("dir") or 0
            act_dir = 1 if state in _POS_STATES else -1 if state in _NEG_STATES else obs_dir

            alt = _alt_lean(covered, alt_bt, mm_index)
            flows = _flow_lean(covered, ff)
            options = _options_lean(covered)
            crowd = _crowd_penalty(covered, alt_bt)

            legs = [lg for lg in (alt, flows, options) if lg.get("present")]
            if act_dir != 0 and legs:
                agree = sum(1 for lg in legs if _sign(lg.get("lean")) == act_dir)
                breadth = agree / len(legs)
            else:
                breadth = 0.5

            sal = float(f.get("salience") or f.get("divergence") or 0)
            base = min(100.0, 30.0 * sal)               # salience → 0-100
            base *= (0.55 + 0.45 * breadth)             # confirmation scales 0.55x–1.0x
            base *= regime["mult"]
            base -= crowd["penalty"]
            edge = int(max(0, min(100, round(base))))

            drivers = alt.get("drivers") or []
            decay = _decay_for(f.get("basket"), state, hist)

            # --- new additive fields ---
            try:
                prev_state, strip = _prev_state_and_strip(f.get("basket"), hist)
                # append today's current state as the final strip entry
                strip = strip + [{"d": today_mmdd, "s": state}]
                f["prev_state"] = prev_state
                f["state_strip"] = strip
            except Exception as e:  # noqa: BLE001
                log.debug("radar_plus prev_state/state_strip %s failed (%s)", f.get("basket"), e)
                f.setdefault("prev_state", None)
                f.setdefault("state_strip", [{"d": today_mmdd, "s": state}])

            f["edge_score"] = edge
            f["confirm"] = {"alt": alt, "flows": flows, "options": options, "crowd": crowd,
                            "breadth": round(breadth, 2), "n_legs": len(legs)}
            f["regime"] = regime
            f["decay"] = decay
            f["drivers"] = drivers
            new_history.append({"date": today.isoformat(), "basket": f.get("basket"), "state": state})
        except Exception as e:  # noqa: BLE001
            log.warning("radar_plus enrich flag %s failed (%s)", f.get("basket"), e)
            f.setdefault("edge_score", 0)

    # append today's snapshot (idempotent per date+basket)
    try:
        seen = {(r.get("date"), r.get("basket")) for r in hist["_rows"]}
        add = [r for r in new_history if (r["date"], r["basket"]) not in seen]
        if add:
            hist["_path"].parent.mkdir(parents=True, exist_ok=True)
            with hist["_path"].open("a") as fh:
                for r in add:
                    fh.write(json.dumps(r) + "\n")
    except Exception as e:  # noqa: BLE001
        log.debug("state history append failed (%s)", e)

    # --- top-level changes block ---
    try:
        # find the most recent date strictly before today across all history rows
        today_iso = today.isoformat()
        prior_dates = sorted({r.get("date", "") for r in hist["_rows"] if r.get("date", "") < today_iso})
        prev_date = prior_dates[-1] if prior_dates else None

        new_divergences, resolved, flips = [], [], []
        for f in flags:
            basket = f.get("basket")
            name = f.get("name") or basket
            name_zh = f.get("name_zh") or ""
            cur = f.get("state") or "QUIET"
            prev = f.get("prev_state")  # None if no history
            if prev is None or prev == cur:
                continue
            cur_div = cur.endswith("_DIVERGENCE")
            prev_div = prev.endswith("_DIVERGENCE")
            entry = {"basket": basket, "name": name, "name_zh": name_zh, "from": prev, "to": cur}
            if cur_div and not prev_div:
                new_divergences.append(entry)
            elif prev_div and not cur_div:
                resolved.append(entry)
            else:
                flips.append(entry)

        radar["changes"] = {
            "prev_date": prev_date,
            "new_divergences": new_divergences,
            "resolved": resolved,
            "flips": flips,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("radar_plus changes block failed (%s)", e)
        radar.setdefault("changes", {"prev_date": None, "new_divergences": [], "resolved": [], "flips": []})

    radar["regime"] = regime
    radar["edge_ranked"] = sorted(
        [{"basket": f.get("basket"), "name": f.get("name"), "state": f.get("state"),
          "edge_score": f.get("edge_score", 0), "breadth": (f.get("confirm") or {}).get("breadth")}
         for f in flags if f.get("state") != "QUIET"],
        key=lambda x: x["edge_score"], reverse=True)
    radar["enriched_utc"] = datetime.now(timezone.utc).isoformat()
    radar["enriched"] = True
    return radar
