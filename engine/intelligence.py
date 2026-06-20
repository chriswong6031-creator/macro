"""Unified per-ticker INTELLIGENCE bundle — news flow + alt-data signal, side by side.

LEAF · CONTEXT-ONLY · DEGRADE-NEVER-RAISE. The single "News & Intelligence"
surface the Mastermind bot pulls: one file, one tool, two clearly-separated facts
per name —

  • news  — editorial headline flow (demand-side tape): what the market is SAYING
            (from engine.financial_news → site/news/by_ticker.json).
  • alt   — political/insider/contract/affiliation SIGNAL (supply-side flow): what
            smart money is DOING (from the Signal Intelligence Desk →
            site/altdata/mastermind.json + site/altdata/by_ticker.json).

DELIBERATELY NOT BLENDED. The two are kept as separate sub-objects so the bot can
still read the divergence between them — insiders buying into a QUIET tape
(early edge) vs a LOUD tape (crowded/late). Pre-mixing them into one score would
destroy exactly that signal. This module ships FACTS only; the bot's matrix names
which side leads.

Nothing here is a scoring input on the macro side — it republishes already-built
artifacts in one place.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "intelligence.by_ticker.v2"

DISCLAIMER = (
    "Context only. Two independent reads per name — editorial news flow (what the tape is "
    "saying) and the alt-data signal (what political/insider/contract money is doing) — shown "
    "side by side, never pre-blended. The early-edge vs crowded-late divergence between them is "
    "the point. The bot sizes through its own risk framework; nothing here sizes alone."
)

# the alt-data mastermind fields worth carrying into the bundle (scored signal)
_ALT_FIELDS = ("signal_score", "conviction", "action", "direction", "source",
               "weighted_score", "convergence_score", "channels", "trump_linked",
               "rs_vs_spy_60d", "extended", "affiliations", "n_affiliated_actors",
               "thesis", "second_order", "falsifier", "clamped")
# extra context columns from by_ticker.v2 (when no scored mastermind row exists)
_BT_FIELDS = ("channels", "weighted_score", "convergence_score", "trump_linked",
              "affiliated", "congress_net", "gov_contract_usd_30d", "insider_net_usd",
              "dpi_lean", "wsb_mentions", "trump_side")


def _alt_for(t: str, mm_index: dict, bt: dict) -> dict | None:
    """Best alt-data read for a ticker: the scored mastermind signal if present,
    else the unscored by_ticker.v2 record, else None."""
    sig = mm_index.get(t)
    if sig:
        out = {k: sig.get(k) for k in _ALT_FIELDS if sig.get(k) is not None}
        out["scored"] = True
        return out
    rec = bt.get(t)
    # only a REAL signal — at least one active convergence channel. Many by_ticker.v2
    # rows carry a lone context metric (e.g. a congress position) with no channel; those
    # are not an alt-data signal and must not surface as one.
    if rec and (rec.get("channels") or rec.get("convergence_score")):
        out = {k: rec.get(k) for k in _BT_FIELDS if rec.get(k) is not None}
        out["scored"] = False
        out.setdefault("action", "WATCH")
        return out
    return None


_POS_RADAR = {"POSITIVE_DIVERGENCE", "CONFIRMED_UP"}
_NEG_RADAR = {"NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"}


def _radar_for(t: str, ridx: dict) -> dict | None:
    """Per-name radar divergence (Divergence Radar Phase-2)."""
    r = ridx.get(t)
    if not r or r.get("state") == "QUIET":
        return None
    return {k: r.get(k) for k in ("state", "lifecycle", "edge_score", "signal_score",
                                  "rs_vs_spy_60d", "note") if r.get(k) is not None}


def _standout_for(t: str, sidx: dict) -> dict | None:
    """The factor buy-board read (us_standouts) for a name."""
    s = sidx.get(t)
    if not s:
        return None
    return {k: s.get(k) for k in ("state", "label", "alpha", "alpha_entry", "conviction",
                                  "urgency", "dir", "setup", "off_high") if s.get(k) is not None}


def _synthesize(news: dict | None, alt: dict | None, radar: dict | None) -> dict:
    """Cross-facet read: demand-side tape (news) vs supply-side smart-money/activity
    (alt + radar). The divergence between them is the edge. FACTS-derived label only."""
    news_dir = {"pos": 1, "neg": -1}.get((news or {}).get("sentiment_lean")) if news else None
    a_score = (alt or {}).get("signal_score")
    alt_dir = None
    if alt:
        if a_score is not None and a_score >= 65 and (alt.get("action") != "AVOID"):
            alt_dir = 1
        elif (alt.get("action") == "AVOID") or (a_score is not None and a_score < 35):
            alt_dir = -1
        else:
            alt_dir = 0
    rstate = (radar or {}).get("state")
    radar_dir = 1 if rstate in _POS_RADAR else -1 if rstate in _NEG_RADAR else (0 if radar else None)

    supply = [d for d in (alt_dir, radar_dir) if d is not None]
    up = sum(1 for d in supply if d > 0)
    dn = sum(1 for d in supply if d < 0)
    label, read = "quiet", "No strong cross-signal."
    if up and rstate == "POSITIVE_DIVERGENCE" and (news_dir or 0) <= 0:
        label, read = "early_edge", "Smart-money / activity is bullish while the tape is quiet — early edge before the crowd notices."
    elif up and (news_dir or 0) > 0:
        label, read = "confirmed", "Activity and the tape agree (bullish) — confirmed; less edge left."
    elif dn and (news_dir or 0) > 0:
        label, read = "crowded_top", "Tape is loud-bullish but smart money is fading — crowded-top / distribution risk."
    elif dn:
        label, read = "fading", "Smart-money / activity cooling."
    elif up:
        label, read = "accumulation", "Smart-money / activity building, tape not yet bullish."
    return {"label": label, "read": read, "news_dir": news_dir,
            "supply_dir": (1 if up > dn else -1 if dn > up else 0) if supply else None}


def _f(x):
    """Coerce to float, guarding dict/str/bool/None — returns None on failure."""
    if x is None or isinstance(x, (dict, list, bool)):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _dir_news(news):
    return {"pos": 1, "neg": -1}.get((news or {}).get("sentiment_lean")) if news else None


def _dir_alt(alt):
    if not alt:
        return None
    s = _f(alt.get("signal_score"))
    act = alt.get("action")
    if s is not None and s >= 65 and act != "AVOID":
        return 1
    if act == "AVOID" or (s is not None and s < 35):
        return -1
    return 0


def _dir_radar(radar):
    st = (radar or {}).get("state")
    if st in _POS_RADAR:
        return 1
    if st in _NEG_RADAR:
        return -1
    return 0 if radar else None


def _dir_standout(s):
    if not s:
        return None
    lab = (s.get("label") or "").upper()
    state = (s.get("state") or "").upper()
    if "AVOID" in lab or "AVOID" in state or "DON'T CHASE" in lab:
        return -1
    return 1  # on the factor buy-board → bullish candidate


def _brain(news, alt, radar, standout, read: dict) -> dict:
    """Opus-facing per-ticker summary: how MANY independent facets fired, whether they
    AGREE, how STRONG the signal is, and the single ranking key (priority). Deterministic;
    no LLM. This is what the bot's intake reads to triage a name without re-deriving facts."""
    nd, ad, rd, sd = _dir_news(news), _dir_alt(alt), _dir_radar(radar), _dir_standout(standout)
    present = [(name, obj) for name, obj in
               (("news", news), ("alt", alt), ("radar", radar), ("standout", standout)) if obj]
    breadth = len(present) / 4.0

    dirs = [d for d in (nd, ad, rd, sd) if d is not None]
    nz = [d for d in dirs if d != 0]
    agreement = abs(sum(nz)) / len(nz) if nz else 0.0          # 1 unanimous … 0 evenly split
    confidence = round(0.5 * breadth + 0.5 * agreement, 3)
    lean = (1 if sum(nz) > 0 else -1 if sum(nz) < 0 else 0) if nz else 0

    mags = []
    re = _f((radar or {}).get("edge_score"))
    if re is not None:
        mags.append(min(abs(re) / 100.0, 1.0))
    a_s = _f((alt or {}).get("signal_score"))
    if a_s is not None:
        mags.append(min(abs(a_s - 50.0) / 50.0, 1.0))
    so_c = _f((standout or {}).get("conviction"))
    if so_c is not None:
        mags.append(min(abs(so_c), 1.0))
    strength = round(max(mags), 3) if mags else 0.0

    parts = []
    if radar:
        parts.append(f"radar {(radar.get('state') or '')[:4]} edge{radar.get('edge_score')}")
    if alt:
        parts.append(f"alt{alt.get('signal_score') if alt.get('signal_score') is not None else alt.get('weighted_score')} {alt.get('action') or ''}".strip())
    if news:
        parts.append(f"news {news.get('sentiment_lean')} n{news.get('n_recent')}")
    if standout:
        parts.append(f"standout {standout.get('label') or standout.get('state') or ''}".strip())
    falsifier = (alt or {}).get("falsifier") or (radar or {}).get("falsifier")

    return {
        "confidence": confidence,                     # 0..1 — breadth × agreement
        "strength": strength,                         # 0..1 — normalized signal magnitude
        "priority": round(confidence * strength, 3),  # the single ranking key for intake
        "lean": lean,                                 # +1 / 0 / -1 net directional read
        "n_facets": len(present),
        "source_mix": [name for name, _ in present],
        "label": read.get("label"),
        "evidence": " · ".join(parts),
        "falsifier": falsifier,
    }


def build(news_tickers: dict | None, alt_signals: list | None,
          alt_by_ticker: dict | None, radar_tickers: list | None = None,
          standouts: list | None = None, today: date | None = None) -> dict:
    """Merge every per-ticker dashboard signal into ONE bundle (4 facets + a read). PURE.

    news_tickers   — site/news/by_ticker.json     ["tickers"]  (T -> compact news dict)
    alt_signals    — site/altdata/mastermind.json ["signals"]  (list of scored alt signals)
    alt_by_ticker  — site/altdata/by_ticker.json  ["tickers"]  (T -> v2 record, fallback)
    radar_tickers  — site/basketdata/radar_ticker.json["tickers"] (per-name divergence)
    standouts      — site/factordata/us_standouts.json["buy"]  (factor buy-board)
    """
    news_tickers = news_tickers or {}
    alt_by_ticker = alt_by_ticker or {}
    mm_index = {(s.get("ticker") or "").upper(): s for s in (alt_signals or []) if s.get("ticker")}
    ridx = {(r.get("ticker") or "").upper(): r for r in (radar_tickers or []) if r.get("ticker")}
    sidx = {(s.get("ticker") or "").upper(): s for s in (standouts or []) if s.get("ticker")}

    universe = set(news_tickers) | set(mm_index) | set(alt_by_ticker) | set(ridx) | set(sidx)
    out: dict[str, dict] = {}
    for t in sorted(universe):
        t = (t or "").upper()
        if not t:
            continue
        news = news_tickers.get(t)
        alt = _alt_for(t, mm_index, alt_by_ticker)
        radar = _radar_for(t, ridx)
        standout = _standout_for(t, sidx)
        if not any((news, alt, radar, standout)):
            continue
        read = _synthesize(news, alt, radar)
        out[t] = {"ticker": t, "news": news, "alt": alt, "radar": radar, "standout": standout,
                  "has_news": bool(news), "has_alt": bool(alt), "has_radar": bool(radar),
                  "has_standout": bool(standout), "read": read,
                  "brain": _brain(news, alt, radar, standout, read),
                  "note": "Demand-side tape (news) + supply-side smart-money/activity (alt + radar) + "
                          "factor buy-board (standout) — facts side by side, never pre-blended."}

    today = today or date.today()
    return {"schema": SCHEMA, "is_context_only": True,
            "as_of": today.isoformat(),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "n_tickers": len(out),
            "n_with_both": sum(1 for v in out.values() if v["has_news"] and v["has_alt"]),
            "n_4facet": sum(1 for v in out.values()
                            if v["has_news"] and v["has_alt"] and (v["has_radar"] or v["has_standout"])),
            "tickers": out, "disclaimer": DISCLAIMER}


def _read(rel: str) -> dict | None:
    p = config.ROOT / rel
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.warning("intelligence: read %s failed (%s)", rel, e)
        return None


def load_and_build(today: date | None = None) -> dict:
    """Read every published per-ticker artifact and merge into the 4-facet bundle.
    Never raises; absent inputs degrade to empty sub-objects."""
    news = _read("site/news/by_ticker.json") or {}
    mm = _read("site/altdata/mastermind.json") or {}
    bt = _read("site/altdata/by_ticker.json") or {}
    rt = _read("site/basketdata/radar_ticker.json") or {}
    so = _read("site/factordata/us_standouts.json") or {}
    return build(news.get("tickers"), mm.get("signals"), bt.get("tickers"),
                 rt.get("tickers"), so.get("buy"), today)
