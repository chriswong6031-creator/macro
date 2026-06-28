"""Alt-data confirmers — the leading rerating legs the desk ALREADY collects, rolled up to
the foresight themes (research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §3.3 / red-team).

WHY A ROLL-UP, NOT A NEW ENGINE. The desk already computes the validated leading rerating
confirmers — open-market insider CLUSTER buys (>=3 buyers) and accelerating federal awards —
in engine/altdata_models.channel_records, persisted per ticker in data/altdata/by_ticker.json.
They were just never fed to the foresight cascade. This is the thin adapter the red-team
asked for: read that substrate, roll the LEADING channels up to each config theme's members,
and expose them so the cascade can use them as CONFIRMERS.

HOUSE DISCIPLINE (why this is not just "more signal = more conviction"):
  - These are SHORT-LEAD CONFIRMERS, never the entry thesis (the physical bottleneck is).
  - They are INVERSE-TO-BREADTH: an insider cluster while revisions are still FLAT is a
    pre-revision tell; the same cluster once revisions are already broad is just crowding,
    which the house treats as NEGATIVE. The cascade applies that inversion (in the score).
  - They are CORRELATION-PENALIZED, never linearly summed (insiders / awards / smart-money
    are partly the same 'informed attention' factor) — the score bonus is bounded.
Pure read of by_ticker.json; DISPLAY-ONLY; returns None when the substrate is absent.
"""
from __future__ import annotations

import json
import logging

from lib import config

log = logging.getLogger(__name__)

# the VALIDATED leading rerating confirmers (blueprint ranking 2-3) — feed the score bonus
LEADING = {"insider_cluster", "gov_contract_accel", "gov_grant_accel"}
# weaker / slower / coincident — surfaced as context only, never scored
CONTEXT = {"congress_cluster", "patent_cluster", "13f_add", "activist_13d"}


def _by_ticker() -> dict | None:
    p = config.data_dir() / "altdata" / "by_ticker.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("altdata by_ticker unreadable: %s", e)
        return None
    tk = (d or {}).get("tickers")
    return d if isinstance(tk, dict) and tk else None


def _channels(rec: dict) -> list[str]:
    ch = rec.get("channels") or []
    return list(ch.keys()) if isinstance(ch, dict) else list(ch)


def _theme_confirmers(name: str, members: list[str], tickers: dict) -> dict | None:
    insider, gov, context = [], [], {}
    for m in members:
        rec = tickers.get(m)
        if not rec:
            continue
        chans = set(_channels(rec))
        if "insider_cluster" in chans:
            insider.append({"ticker": m, "buyers": rec.get("insider_buyers"),
                            "net_usd": rec.get("insider_net_usd")})
        if "gov_contract_accel" in chans or "gov_grant_accel" in chans:
            gov.append({"ticker": m, "accel_x": rec.get("gov_contract_accel"),
                        "usd": rec.get("gov_contract_usd_30d")})
        for c in (chans & CONTEXT):
            context.setdefault(c, []).append(m)
    leading_members = sorted({d["ticker"] for d in insider} | {d["ticker"] for d in gov})
    if not leading_members and not context:
        return None
    # n_leading = distinct LEADING channels firing anywhere in the theme (0-2), correlation-
    # penalized by being a channel COUNT, not a member sum
    n_leading = (1 if insider else 0) + (1 if gov else 0)
    bits = []
    if insider:
        bits.append(f"{len(insider)} insider cluster" + ("s" if len(insider) > 1 else ""))
    if gov:
        bits.append(f"{len(gov)} gov-award accel")
    for c, ms in context.items():
        bits.append(f"{len(ms)} {c.replace('_', ' ')}")
    return {
        "name": name,
        "insider_cluster": insider[:6],
        "gov_accel": gov[:6],
        "context": {c: ms[:6] for c, ms in context.items()},
        "n_leading": n_leading,
        "leading_members": leading_members[:8],
        "summary": " · ".join(bits),
    }


def compute_altdata_confirmers(by_ticker: dict | None = None) -> dict | None:
    """Per-theme roll-up of the leading alt-data confirmers over config `themes:`.
    DISPLAY-ONLY. Returns None when data/altdata/by_ticker.json is absent."""
    d = by_ticker if by_ticker is not None else _by_ticker()
    if not d:
        return None
    tickers = d.get("tickers") or {}
    if not tickers:
        return None
    themes = (config.load() or {}).get("themes") or {}
    if not themes:
        return None
    out = {}
    for key, spec in themes.items():
        members = spec.get("tickers") or []
        try:
            r = _theme_confirmers(spec.get("name", key), members, tickers)
        except Exception as e:  # noqa: BLE001 — one theme failing never blocks the rest
            log.warning("altdata_confirmers[%s] failed: %s", key, e)
            r = None
        if r is not None:
            out[key] = r
    if not out:
        return None
    return {
        "asof": d.get("as_of"),
        "n_themes": len(out),
        "themes": out,
        "note": ("display-only; leading rerating CONFIRMERS (insider clusters, accelerating "
                 "federal awards) rolled up from data/altdata/by_ticker.json. Inverse-to-breadth "
                 "and correlation-penalized in the score — a confirmer pre-revision is a tell, the "
                 "same confirmer once revisions are broad is just crowding."),
    }
