"""Alt-data picks — filter the NOISE, examine the signal.

A wealthy political figure's disclosed trades are mostly portfolio plumbing: broad ETFs,
index funds, money-market and Treasury funds, broker-managed/'unsolicited' lots — and a
single periodic disclosure can dump hundreds of tickers at once. Examining each is
pointless. The SIGNAL is the specific, idiosyncratic, single-name conviction bets,
especially those that converge with other channels or tie to the latent-stake graph.

This module classifies the passive/broad holdings out, then triages the specific names
worth examining with a first-pass relative-strength read (name vs SPY). The deep
"is this a good pick" verdict already lives on the stock page (the conviction profile +
the alt-data chip); this is the curated shortlist that decides WHICH names deserve that
look. Display/context-only — heuristic classifier, never a scored axis.
"""
from __future__ import annotations

import logging

from lib import config

log = logging.getLogger(__name__)

# High-precision fund/passive markers (rarely appear in an operating company's name).
_PASSIVE_KW = (
    "etf", "index fund", " index", "money market", "money mkt", "mutual fund",
    "unsolicited", "treasury", "municipal", "muni bond", "bond fund", "bond index",
    "income fund", "total stock", "total bond", "aggregate bond", "russell",
    "s&p 500", "s&p500", "s & p 500", "nasdaq-100", "nasdaq 100", "ishares", "spdr",
    "vanguard", "invesco qqq", "target date", "target retirement", "select sector",
)
# Common broad-market ETF tickers (passive, regardless of name).
_BROAD_ETFS = {
    "SPY", "VOO", "IVV", "QQQ", "VTI", "IWM", "DIA", "AGG", "BND", "VEA", "VWO",
    "IEFA", "IEMG", "VUG", "VTV", "SCHB", "SCHX", "VIG", "VYM", "VXUS", "BNDX",
}


def is_passive(company: str | None, ticker: str | None) -> bool:
    """True for broad / passive / cash-management holdings — the noise to filter out."""
    t = (ticker or "").upper().strip()
    if t in _BROAD_ETFS:
        return True
    c = (company or "").lower()
    return any(k in c for k in _PASSIVE_KW)


def _rs_vs_spy(ticker: str, root, win: int = 60) -> float | None:
    """Relative strength: name return minus SPY return over `win` trading days, in pp."""
    try:
        from engine import ai_desk as _desk
        root = root or config.ROOT
        s = _desk._close_series(ticker, root)
        spy = _desk._close_series("SPY", root)
        if s is None or spy is None or len(s) < 6 or len(spy) < 6:
            return None

        def _ret(x):
            n = min(win, len(x) - 1)
            return float(x.iloc[-1] / x.iloc[-1 - n] - 1) if n > 0 else 0.0
        return round((_ret(s) - _ret(spy)) * 100, 1)
    except Exception:  # noqa: BLE001
        return None


def _verdict(score: int, rs: float | None, trump_linked: bool) -> dict:
    base_en = "strong signal" if score >= 3 else "examine" if score >= 2 else "single-channel"
    base_zh = "强信号" if score >= 3 else "值得审视" if score >= 2 else "单渠道"
    if trump_linked:
        base_en += " · Trump-linked"; base_zh += " · 特朗普关联"
    if rs is None:
        return {"en": f"{base_en} — price n/a", "zh": f"{base_zh} — 无价格"}
    tone_en = "leading" if rs > 2 else "lagging" if rs < -2 else "in-line"
    tone_zh = "领先" if rs > 2 else "落后" if rs < -2 else "持平"
    return {"en": f"{base_en} · {tone_en} vs SPY ({rs:+.1f}pp 60d)",
            "zh": f"{base_zh} · 相对标普{tone_zh}（60日{rs:+.1f}个百分点）"}


def build_picks(feed: dict | None, by_ticker: dict | None, root=None, top: int = 15) -> dict:
    """The curated, noise-filtered shortlist of specific names worth examining."""
    bt = (by_ticker or {}).get("tickers", {}) if by_ticker else {}
    sig = (feed or {}).get("signals", {})
    trump = sig.get("trump", []) or []
    passive_n = sum(1 for t in trump if is_passive(t.get("company"), t.get("ticker")))

    # federal contract-spend acceleration per ticker (recent vs year-ago) — the
    # "money moving ahead of the tape" signal. The Divergence Radar owns the BASKET-level
    # version off the authoritative USAspending source; here it's a NAME-level flag on the
    # specific picks, off the gov-contract leaders the engine already computes.
    gov_accel = {g["ticker"]: g["accel_x"] for g in (sig.get("gov_contracts", []) or [])
                 if g.get("ticker") and g.get("accel_x") is not None}

    cand: dict[str, set] = {}
    # specific (non-passive) Trump single-name trades
    for t in trump:
        tk = t.get("ticker")
        if not tk or is_passive(t.get("company"), tk):
            continue
        cand.setdefault(tk, set()).add(f"Trump {t.get('side') or 'trade'}")
    # cross-signal convergent names (already noise-light by construction)
    for tk, rec in bt.items():
        if int(rec.get("convergence_score", 0) or 0) >= 2:
            cand.setdefault(tk, set()).add(f"{rec['convergence_score']}-channel convergence")
    # strongly-accelerating federal contract recipients (spend running ahead of price)
    for tk, ax in gov_accel.items():
        if ax >= 2.0:
            cand.setdefault(tk, set()).add(f"fed-spend accel {ax:.1f}x")

    picks = []
    for tk, reasons in cand.items():
        rec = bt.get(tk, {})
        score = int(rec.get("convergence_score", 0) or 0)
        ax = gov_accel.get(tk)
        if ax is not None and ax >= 1.25:
            reasons.add(f"fed-spend accel {ax:.1f}x")
        rs = _rs_vs_spy(tk, root)
        picks.append({
            "ticker": tk, "reasons": sorted(reasons), "convergence": score,
            "trump_linked": bool(rec.get("trump_linked")),
            "gov_contract_accel": round(ax, 2) if ax is not None else None,
            "rs_vs_spy_60d": rs, "verdict": _verdict(score, rs, bool(rec.get("trump_linked"))),
        })
    picks.sort(key=lambda p: (p["convergence"], p["rs_vs_spy_60d"] if p["rs_vs_spy_60d"] is not None else -999),
               reverse=True)

    return {
        "schema": "altdata.picks.v1",
        "picks": picks[:top],
        "filtered_passive": passive_n,
        "note": ("Passive / broad holdings (ETFs, index, money-market, Treasury, "
                 "broker-managed) filtered out — only specific conviction names are examined. "
                 "'fed-spend accel' = federal contract $ running ahead of the tape."),
    }
