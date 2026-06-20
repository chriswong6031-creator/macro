"""Per-ticker Divergence Radar (Phase 2) — the #1 gap: the basket radar masks names.

ADDITIVE · LEAF. A parallel, per-NAME divergence read that does NOT touch the
basket radar. It reuses signals already published per ticker:

  • activity (supply-side "smart money is moving"):  the Signal Intelligence Desk
       signal_score (0-100) from site/altdata/mastermind.json — which conveniently
       ALSO carries rs_vs_spy_60d, so we get price for free.
  • price (the already-priced consensus):  rs_vs_spy_60d (60-day relative strength).
  • confirmation: ETF flow direction (fund_flows) + options positioning (GEX).

The divergence is the edge: high activity + flat/down price = POSITIVE (smart money
ahead of the tape); high price + cooling activity = NEGATIVE (price ahead, distribution).
Emits site/basketdata/radar_ticker.json, ranked by edge_score. Context-only, never a
trade trigger; falsifiable per-ticker theses are seeded for later grading vs SPY.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from lib import config
from engine import radar_plus as rp

log = logging.getLogger(__name__)

SCHEMA = "radar_ticker.v1"


def _state(act: float, pr: float) -> tuple[str, str]:
    """Divergence state + lifecycle from normalized activity vs price."""
    if act >= 0.5 and pr <= 0.15:
        return "POSITIVE_DIVERGENCE", "emerging" if pr < -0.3 else "forming"
    if act >= 0.4 and pr >= 0.5:
        return "CONFIRMED_UP", "mature"
    if act <= -0.25 and pr >= 0.5:
        return "NEGATIVE_DIVERGENCE", "fading"
    if act <= -0.25 and pr <= -0.25:
        return "CONFIRMED_DOWN", "fading"
    return "QUIET", "quiet"


def build(today: date | None = None) -> dict:
    """Compute per-ticker divergence over the alt-signal universe. Never raises."""
    today = today or date.today()
    mm = rp._load("site/altdata/mastermind.json") or {}
    alt_bt = rp._load("site/altdata/by_ticker.json") or {}
    ff = rp._load("site/stockdata/fund_flows.json") or {}
    regime = rp._regime()

    rows = []
    for s in (mm.get("signals") or []):
        t = (s.get("ticker") or "").upper()
        if not t:
            continue
        score = s.get("signal_score")
        rs = s.get("rs_vs_spy_60d")
        if score is None:
            continue
        act = (float(score) - 50.0) / 25.0                  # ≈ −2..+2
        pr = (float(rs) / 8.0) if rs is not None else 0.0   # ≈ −2..+2 (8% = ~1σ)
        state, lifecycle = _state(act, pr)

        flows = rp._flow_lean([t], ff)
        options = rp._options_lean([t])
        crowd = rp._crowd_penalty([t], alt_bt)

        act_dir = 1 if state in rp._POS_STATES else -1 if state in rp._NEG_STATES else 0
        legs = [lg for lg in (flows, options) if lg.get("present")]
        agree = sum(1 for lg in legs if rp._sign(lg.get("lean")) == act_dir) if (act_dir and legs) else 0
        breadth = (agree / len(legs)) if legs else 0.5

        # edge: the activity-vs-price gap, scaled by confirmation, regime, crowding
        gap = abs(act - pr)
        base = min(100.0, 26.0 * gap) * (0.55 + 0.45 * breadth) * regime["mult"] - crowd["penalty"]
        edge = int(max(0, min(100, round(base))))

        rows.append({
            "ticker": t, "state": state, "lifecycle": lifecycle, "edge_score": edge,
            "signal_score": score, "rs_vs_spy_60d": rs, "action": s.get("action"),
            "conviction": s.get("conviction"), "extended": bool(s.get("extended")),
            "channels": s.get("channels") or [], "affiliations": s.get("affiliations") or [],
            "activity": round(act, 2), "price": round(pr, 2),
            "flows": flows, "options": options, "crowd": crowd,
            "note": _note(t, state, score, rs, flows, options),
        })

    rows.sort(key=lambda r: (r["state"] != "QUIET", r["edge_score"]), reverse=True)
    out = {
        "schema": SCHEMA, "is_context_only": True, "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "regime": regime, "n": len(rows),
        "n_divergences": sum(1 for r in rows if "DIVERGENCE" in r["state"]),
        "tickers": rows,
        "disclaimer": "Per-name activity (smart-money signal) vs price (60d RS). The divergence "
                      "is the edge — context only, never a trade trigger.",
    }
    return out


def _note(t, state, score, rs, flows, options) -> str:
    rsx = f"{rs:+.1f}% vs SPY" if rs is not None else "RS n/a"
    if state == "POSITIVE_DIVERGENCE":
        head = f"Smart-money signal {score}/100 on {t} while price lags ({rsx}) — activity ahead of the tape."
    elif state == "NEGATIVE_DIVERGENCE":
        head = f"{t} has led ({rsx}) but the alt-data signal is cooling ({score}/100) — price ahead of activity."
    elif state == "CONFIRMED_UP":
        head = f"{t}: signal {score}/100 AND price ({rsx}) both up — confirmed."
    elif state == "CONFIRMED_DOWN":
        head = f"{t}: signal weak ({score}/100) and price down ({rsx})."
    else:
        head = f"{t}: signal {score}/100, {rsx} — no clear divergence."
    tags = []
    if flows.get("present"):
        tags.append("ETF " + ("accumulating" if flows.get("lean", 0) > 0 else "distributing" if flows.get("lean", 0) < 0 else "flat"))
    if options.get("present"):
        tags.append("options " + ("call-leaning" if options.get("lean", 0) > 0 else "put-leaning" if options.get("lean", 0) < 0 else "neutral"))
    return head + (" · " + " · ".join(tags) if tags else "")
