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

SCHEMA = "intelligence.by_ticker.v1"

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


def build(news_tickers: dict | None, alt_signals: list | None,
          alt_by_ticker: dict | None, today: date | None = None) -> dict:
    """Merge the three already-built artifacts into one per-ticker bundle. PURE.

    news_tickers   — site/news/by_ticker.json   ["tickers"]  (T -> compact news dict)
    alt_signals    — site/altdata/mastermind.json["signals"] (list of scored signals)
    alt_by_ticker  — site/altdata/by_ticker.json["tickers"]  (T -> v2 record)
    """
    news_tickers = news_tickers or {}
    alt_by_ticker = alt_by_ticker or {}
    mm_index = {}
    for s in (alt_signals or []):
        t = (s.get("ticker") or "").upper()
        if t:
            mm_index[t] = s

    universe = set(news_tickers) | set(mm_index) | set(alt_by_ticker)
    out: dict[str, dict] = {}
    for t in sorted(universe):
        t = (t or "").upper()
        if not t:
            continue
        news = news_tickers.get(t)
        alt = _alt_for(t, mm_index, alt_by_ticker)
        if not news and not alt:
            continue
        out[t] = {"ticker": t, "news": news, "alt": alt,
                  "has_news": bool(news), "has_alt": bool(alt),
                  "note": "News flow (demand-side tape) + alt-data signal (supply-side flow), "
                          "side by side — facts only, never pre-blended."}

    today = today or date.today()
    return {"schema": SCHEMA, "is_context_only": True,
            "as_of": today.isoformat(),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "n_tickers": len(out),
            "n_with_both": sum(1 for v in out.values() if v["has_news"] and v["has_alt"]),
            "tickers": out, "disclaimer": DISCLAIMER}


def _read(rel: str) -> dict | None:
    p = config.ROOT / rel
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.warning("intelligence: read %s failed (%s)", rel, e)
        return None


def load_and_build(today: date | None = None) -> dict:
    """Read the three published artifacts from site/ and merge. Never raises;
    empty sub-objects degrade gracefully."""
    news = _read("site/news/by_ticker.json") or {}
    mm = _read("site/altdata/mastermind.json") or {}
    bt = _read("site/altdata/by_ticker.json") or {}
    return build(news.get("tickers"), mm.get("signals"), bt.get("tickers"), today)
