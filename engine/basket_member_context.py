"""Within-basket member context — the leader-vs-chase read the per-name brake omits.

THE PROBLEM THIS SOLVES. The Top-Picks board's extension brakes are honest and validated,
but both are INTRA-NAME: the absolute one (`pct_vs_200dma >= 30%` → "don't chase", engine/
stock_score) and the own-history one (`ext_z >= 2` parabolic, engine/extension). Neither
knows the COHORT. So when a theme runs hot and the WHOLE basket is ~+30% above its 200d MA,
the theme's *leader* trips the same absolute "chase" brake as a junk name that idiosyncratically
spiked — even though the leader is barely extended RELATIVE TO ITS THEME. Leaders rally more
than laggards by construction, so an absolute brake systematically punishes exactly the names
a thematic book wants.

This module adds the missing axis: for each LIVE member of each basket, where its extension
and its 20-day relative strength sit WITHIN the basket's own cross-section. That lets the page
separate two things the absolute brake conflates:

  * "Leader · in-line stretch"   — extended, but ~with its theme (low ext_rel) and leading it
                                    (high within-basket RS). The leader you want; the trade is
                                    to TIME the entry (wait for a pullback), not to veto it.
  * "Extended beyond theme"      — stretched idiosyncratically FAR past its cohort (high ext
                                    rank / ext_rel) or own-history parabolic. The genuine chase.

HONEST BY CONSTRUCTION (this is why it lives apart from any score):
  * It RE-READS the same validated per-name extension; it does NOT manufacture a new edge.
    Phase-0 (scripts/thematic_rotation_phase0) found basket-AGGREGATE extension has no
    forward-drawdown edge — the parabolic→crash link is a per-name effect. So this is COHORT
    CONTEXT for the per-name flag, never a basket-timing or return claim, never scored.
  * The own-history parabolic flag (ext_z>=2, validated −94% DD) still reads as a chase here
    regardless of cohort — a radioactive name is radioactive whatever its peers do.

Region-aware via engine.group_flow._setup (US + CN/HK/CA once regionalised), same as
engine.theme_extension. All from the daily close matrix the page already loads — no new data.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import extension, group_flow

log = logging.getLogger(__name__)

# need a real cross-section before "within-basket" means anything
MIN_MEMBERS = 4
# a member is "extended" (the gray zone where leader-vs-chase matters) at/above this % over its
# own 200d MA — set just under the board's _STRETCH_WARN=25 so we catch names approaching the brake.
EXT_FLOOR = 20.0
# WITHIN-BASKET "beyond" cut: stretched FAR past the cohort = a chase, not theme-leadership.
# Gated on ext_rel (pp above the basket MEDIAN), NOT on the within-basket extension RANK: in a
# small/tight basket the genuine leader can sit in the top rank quintile while being only a point
# or two above the median, so rank would false-flag exactly the leader we want to keep.
BEYOND_REL = 10.0         # >10pp above the basket's MEDIAN % over 200d MA = extended beyond theme
# leads its theme on 20d relative strength
LEAD_RANK = 0.55
# a laggard with room (catch-up candidate territory — RS-slope detection is a later move)
LAG_RANK = 0.35
LAG_EXT = 10.0
# a theme has "run hot" only when its TYPICAL member is meaningfully extended. Gating on the
# median (not just "≥2 names extended") keeps the panel on its premise — re-reading extension
# inside a theme that actually rallied — and drops flat, high-dispersion themes where a couple of
# names ran ahead of a theme that mostly didn't (there the within-theme lens isn't the right one;
# that is an emerging-leader question for a later move). ~half the board's _STRETCH_WARN=25.
HOT_MEDIAN = 12.0

# band -> (en, zh, tone) ; tone vocabulary matches site/theme_addons.js toneVar()
# "leader" = extended + leads its theme + NOT parabolic vs its own history => the name to TIME an
# entry on (wait for a pullback), not to blanket-veto for tripping the absolute brake.
BANDS = {
    "leader":   ("Leader · time the entry", "领涨 · 等回调",  "pos"),
    "extended": ("Extended",                "延展偏高",       "warn"),
    "beyond":   ("Extended beyond theme",   "延展超出主题",   "neg"),
    "laggard":  ("Laggard · room",          "落后 · 有空间",  "neu"),
    "in_range": ("In range",                "区间内",         "neu"),
    "na":       ("—",                       "—",             "neu"),
}
_PARABOLIC_LABEL = ("Parabolic — chase", "抛物 — 追高")


def classify_member(ext_abs: float | None, ext_rel: float | None,
                    rs_rank: float | None, grade: str | None) -> tuple[str, bool]:
    """Pure within-basket band from a member's absolute extension, its extension EXCESS over the
    basket median (ext_rel), its within-basket 20d-RS rank, and its own-history grade. Returns
    (band, is_parabolic). The own-history parabolic flag is a chase regardless of cohort."""
    parabolic = grade == "parabolic"
    if parabolic:                                   # radioactive vs ITSELF — cohort can't excuse it
        return "beyond", True
    if ext_abs is None or rs_rank is None:
        return "na", False
    extended = ext_abs >= EXT_FLOOR
    if extended and ext_rel is not None and ext_rel >= BEYOND_REL:
        return "beyond", False                      # stretched far past its cohort = a chase
    if extended and rs_rank >= LEAD_RANK:
        return "leader", False                      # extended WITH its theme + leads it
    if extended:
        return "extended", False                    # extended, mid-pack — mild caution
    if rs_rank <= LAG_RANK and ext_abs <= LAG_EXT:
        return "laggard", False                     # lagging with room (catch-up territory)
    return "in_range", False


def _band_labels(band: str, parabolic: bool) -> tuple[str, str, str]:
    en, zh, tone = BANDS.get(band, BANDS["na"])
    if parabolic:                                   # keep the validated radioactive name visible
        return _PARABOLIC_LABEL[0], _PARABOLIC_LABEL[1], "neg"
    return en, zh, tone


def _r(x, n: int = 2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def _ret20(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 21:
        return None
    a, b = s.iloc[-21], s.iloc[-1]
    if not np.isfinite(a) or a == 0 or not np.isfinite(b):
        return None
    return (b / a - 1.0) * 100.0


def _mt(m: dict):
    return m.get("ticker") or m.get("symbol")


def _live_members(members: list[dict], present: set[str], last: pd.Timestamp) -> list[dict]:
    """Members present in the close matrix whose dated [added, removed) window is open today
    (mirrors engine.group_flow / engine.theme_extension)."""
    live = []
    for m in members:
        t = _mt(m)
        if t not in present:
            continue
        if pd.Timestamp(m.get("added")) <= last and (
                not m.get("removed") or pd.Timestamp(m["removed"]) > last):
            live.append(m)
    return live


def _theme_rows(closes: pd.DataFrame, ext_sig: dict[str, dict], bid: str, b: dict,
                last: pd.Timestamp) -> dict | None:
    """Per-member within-basket context for ONE basket, or None if too thin."""
    members = b.get("members", [])
    present = {_mt(m) for m in members if _mt(m) in closes.columns}
    live = _live_members(members, present, last)
    # collect raw per-member reads
    recs = []
    for m in live:
        t = _mt(m)
        sig = ext_sig.get(t) or {}
        recs.append({
            "ticker": t,
            "name": m.get("name") or t,
            "ext": _r(sig.get("ext"), 1),            # % above own 200d MA (== board's pct_vs_200dma)
            "ext_z": _r(sig.get("ext_z")),           # own-history extension z
            "grade": sig.get("grade"),
            "ret20": _r(_ret20(closes[t]), 1),
        })
    # the cross-section needs members with an extension read
    ext_vals = [r["ext"] for r in recs if r["ext"] is not None]
    if len(ext_vals) < MIN_MEMBERS:
        return None
    med = float(np.median(ext_vals))
    ext_rank = pd.Series({r["ticker"]: r["ext"] for r in recs if r["ext"] is not None}).rank(pct=True)
    rs_rank = pd.Series({r["ticker"]: r["ret20"] for r in recs if r["ret20"] is not None}).rank(pct=True)

    out = []
    for r in recs:
        er = ext_rank.get(r["ticker"])
        rr = rs_rank.get(r["ticker"])
        rel = None if r["ext"] is None else r["ext"] - med
        band, parab = classify_member(r["ext"], rel,
                                      None if rr is None else float(rr), r["grade"])
        en, zh, tone = _band_labels(band, parab)
        out.append({**r, "ext_rel": _r(rel, 1), "ext_rank": _r(er), "rs_rank": _r(rr),
                    "band": band, "band_en": en, "band_zh": zh, "tone": tone,
                    "parabolic": parab})
    # leaders + the chase read at the top; then by extension desc
    _order = {"beyond": 0, "leader": 1, "extended": 2, "in_range": 3, "laggard": 4, "na": 5}
    out.sort(key=lambda x: (_order.get(x["band"], 9), -(x["ext"] if x["ext"] is not None else -1e9)))

    n_leaders = sum(1 for x in out if x["band"] == "leader")
    n_beyond = sum(1 for x in out if x["band"] == "beyond")
    n_ext = sum(1 for x in out if x["band"] in ("leader", "extended", "beyond"))
    return {
        "id": bid, "name": b.get("name", bid),
        "name_zh": b.get("name_zh", b.get("name", bid)),
        "category": b.get("category", "Other"),
        "n": len([r for r in recs if r["ext"] is not None]),
        "median_ext": _r(med, 1),
        "n_leaders": n_leaders, "n_beyond": n_beyond, "n_extended": n_ext,
        "hot": med >= HOT_MEDIAN and n_ext >= 2,      # typical member extended = the "theme ran hot" case
        "members": out,
    }


def compute_member_context(region: str = "us") -> dict | None:
    """Per-basket within-member leader-vs-chase context for a region. None on shortfall
    (additive caller). Display-only — cohort context for the validated per-name brake."""
    s = group_flow._setup(region)
    if s is None:
        return None
    closes, idx = s["closes"], s["idx"]
    if closes is None or closes.empty or len(idx) < 220:
        return None
    ext_sig = extension.extension_signals(closes)    # the SAME per-name read the board uses
    if not ext_sig:
        return None
    last = idx.max()

    bdict = s["mem"]["baskets"]
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
    themes, by_ticker = [], {}
    for bid, b in items:
        row = _theme_rows(closes, ext_sig, bid, b, last)
        if row is None:
            continue
        themes.append(row)
        for m in row["members"]:
            by_ticker.setdefault(m["ticker"], []).append({
                "basket_id": bid, "basket": row["name"], "basket_zh": row["name_zh"],
                "band": m["band"], "band_en": m["band_en"], "band_zh": m["band_zh"],
                "tone": m["tone"], "parabolic": m["parabolic"],
                "ext": m["ext"], "ext_rel": m["ext_rel"], "ext_rank": m["ext_rank"],
                "rs_rank": m["rs_rank"], "median_ext": row["median_ext"],
            })
    if not themes:
        return None
    # hot / most-extended themes first (the page leads with the "theme ran hot" cases)
    themes.sort(key=lambda x: (not x["hot"], -(x["n_beyond"] + x["n_leaders"]),
                               -(x["median_ext"] or -1e9)))
    return {
        "as_of": last.strftime("%Y-%m-%d"),
        "region": s.get("region", region),
        "method": ("Per live member: % above its own 200d MA (ext), own-history extension grade, "
                   "and 20d return — each ranked WITHIN its basket. ext_rel = member ext − basket "
                   "median ext."),
        "thresholds": {"ext_floor": EXT_FLOOR, "beyond_rel": BEYOND_REL,
                       "lead_rank": LEAD_RANK, "hot_median": HOT_MEDIAN},
        "disclaimer_en": ("Display-only cohort context for the validated per-name extension brake: "
                          "is a name extended because it LEADS a moving theme (so the trade is to "
                          "wait for a pullback, not to veto it) or because it spiked BEYOND its "
                          "theme (a chase)? It re-reads the same per-name flag against its peers — "
                          "it is not a new return or drawdown edge."),
        "disclaimer_zh": ("仅供展示：为已验证的个股延展刹车提供同侪背景 —— 某只个股延展，是因为它在"
                          "领涨一个正在运行的主题（那么应等回调再进，而非否决），还是因为它已"
                          "延展到超出主题（追高）？它只是把同一个股信号放到同侪中重读，并非新的收益或回撤优势。"),
        "themes": themes,
        "by_ticker": by_ticker,
    }
