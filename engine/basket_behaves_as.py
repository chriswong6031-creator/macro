"""engine/basket_behaves_as.py — dual-membership "behaves-as" reads (Rotation Command RC-R7).

A name can sit in more than one curated basket and receive OPPOSITE reads with nothing
reconciling them. The 2026-06-25 postmortem's case: NVDA is in both `mag7` (which read
avoid/EXTENDED all window) and `ai_semiconductors` (which read buy/BUY_PARTIAL), and the
tape said NVDA belonged with the mega-cap generals — but no surface said so. This module
computes, for each dual-member, the trailing-20d (and 60d) return correlation of the name
against EACH home basket's EX-NAME equal-weight composite, and names the home it actually
tracks. Display-only: it reads current membership and never re-curates it (Ratio Lens
purity law); it computes NAME-vs-HOME correlation, which is orthogonal to Ratio Lens's
pairwise basket RATIOS — no overlap in mechanism or surface.

Pure w.r.t. files (reads the OHLCV store via engine.basket_index). No LLM, no authority.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import basket_index, sector_legs

log = logging.getLogger(__name__)

CORR_MIN_BARS = 20          # need at least a full 20d window to state a corr
CORR_WINDOWS = (20, 60)     # trailing windows; 20d is the headline, 60d the confirm/tiebreak

# coarse read families for the conflict flag — a dual-member is a CONFLICT when its homes
# span more than one family and at least one is constructive (the NVDA case: mag7 'late'
# = neutral vs ai_semiconductors 'tailwind' = constructive).
_FAMILY = {
    "entry_now": "constructive", "forming": "constructive", "tailwind": "constructive",
    "late": "neutral", "neutral": "neutral",
    "headwind": "avoid",
}


def _family(cls: str | None) -> str:
    return _FAMILY.get(cls or "", "neutral")


def _corr(name_close: pd.Series, comp_level: pd.Series, window: int) -> float | None:
    """Pearson correlation of daily returns over the last `window` aligned bars."""
    idx = name_close.dropna().index.intersection(comp_level.dropna().index)
    if len(idx) < window + 1:
        return None
    a = name_close.reindex(idx).pct_change().iloc[-window:]
    b = comp_level.reindex(idx).pct_change().iloc[-window:]
    both = pd.concat([a, b], axis=1).dropna()
    if len(both) < window - 2:              # allow a couple of stale bars, no more
        return None
    sa, sb = both.iloc[:, 0], both.iloc[:, 1]
    if sa.std() == 0 or sb.std() == 0:
        return None
    c = float(sa.corr(sb))
    return None if not np.isfinite(c) else round(c, 3)


def rank_homes(home_rows: list[dict]) -> list[dict]:
    """Order a name's homes best-first: highest 20d corr, with 60d breaking a round(corr20,2)
    tie. The None-aware fallback is deliberate — `corr60 or -1` would collapse a LEGITIMATE
    corr60 of 0.0 (a near-orthogonal home, this module's core case) to the missing-sentinel
    and pick the wrong home in a tie."""
    return sorted(home_rows, key=lambda h: (round(h["corr20"], 2),
                  h["corr60"] if h.get("corr60") is not None else -1.0), reverse=True)


def _items(memberships) -> list[tuple]:
    return list(memberships.items()) if isinstance(memberships, dict) \
        else [(b.get("id"), b) for b in memberships]


def annotate(baskets: list[dict], memberships) -> dict:
    """Stamp `member["behaves_as"]` on every dual-member in every home it appears in, and
    return a small summary. Mutates the `baskets` member dicts in place (they flow to the
    JSON payload + every consumer). `baskets` = scored groups (each has basket_id, class,
    regime.side, members[].ticker); `memberships` = the raw {basket_id: {members:[...]}}.
    """
    # active members per basket (removed==None), for the ex-name composite
    active = {bid: [m.get("ticker") for m in (spec.get("members") or [])
                    if m.get("ticker") and not m.get("removed")]
              for bid, spec in _items(memberships)}
    # each scored basket's coarse read, for conflict detection + display
    read = {g["basket_id"]: {"class": g.get("class"), "side": g.get("regime", {}).get("side"),
                             "label": g.get("label"), "label_zh": g.get("label_zh")}
            for g in baskets if g.get("basket_id")}
    # ticker -> home basket_ids among the SCORED baskets (only homes that actually rendered)
    homes: dict[str, set] = {}
    for g in baskets:
        bid = g.get("basket_id")
        for m in g.get("members", []):
            homes.setdefault(m["ticker"], set()).add(bid)
    dual = {t: sorted(bs) for t, bs in homes.items() if len(bs) > 1}

    n_conflict = 0
    annotated: list[str] = []
    for t, bids in dual.items():
        name_close = None
        mdf = basket_index._load_member_ohlcv(t)
        if mdf is not None and "close" in mdf:
            name_close = mdf["close"].dropna()
        if name_close is None or len(name_close) < CORR_MIN_BARS + 1:
            continue
        home_rows = []
        for bid in bids:
            others = [x for x in active.get(bid, []) if x != t]
            comp, meta = sector_legs._ew_close(others)
            if comp is None:
                continue
            corr = {f"corr{w}": _corr(name_close, comp, w) for w in CORR_WINDOWS}
            if corr["corr20"] is None:
                continue
            r = read.get(bid, {})
            home_rows.append({"id": bid, "label": r.get("label") or bid,
                              "label_zh": r.get("label_zh"), "class": r.get("class"),
                              "side": r.get("side"), **corr})
        if len(home_rows) < 2:
            continue
        home_rows = rank_homes(home_rows)
        best = home_rows[0]
        fams = {_family(h["class"]) for h in home_rows}
        conflict = len(fams) > 1 and "constructive" in fams
        n_conflict += conflict
        payload = {"home_id": best["id"], "home_label": best["label"],
                   "home_label_zh": best["label_zh"], "conflict": conflict,
                   "homes": home_rows}
        # stamp on the member dict in EACH home so both cards show it
        for g in baskets:
            if g.get("basket_id") in bids:
                for m in g.get("members", []):
                    if m["ticker"] == t:
                        m["behaves_as"] = payload
        annotated.append(t)

    log.info("behaves_as: %d dual-members annotated (%d in conflict) — e.g. %s",
             len(annotated), n_conflict, ", ".join(annotated[:6]) or "none")
    return {"n_dual": len(dual), "n_annotated": len(annotated), "n_conflict": n_conflict,
            "annotated": annotated}
