"""Sector washout→turn context for the A-share stock screener board.

The consolidated screener (china_stocks.html "one board, two validated lenses") surfaces
the deepest within-sector dips (the validated reversal edge). This module adds the
OWNER-REQUESTED sector context: a name gets a DISPLAY boost when its sector washed out
along with it and the *sector* is now turning, via either leg:

  leg A (sector turn)   the equal-weight sector composite has washed out AND just fired
                        the validated 2D-MACD x 3D-StochRSI confluence turn — graded by
                        engine.confluence_tiers.cascade on the composite (T2 = the 2D
                        RSI-MACD just crossed with the 3D StochRSI recently crossed;
                        T3 = the same cross projected within ~1-2 days). T4 is excluded
                        (it fires off the 2D stoch, not the 3D — signal_gate.BUYABLE_TIERS).
  leg B (peers basing)  a broad share of the sector's WASHED-OUT peers have finished
                        going down: their smoothed downtrend velocity has collapsed to
                        ~flat (basing) or ticked slightly positive (perking). Velocity =
                        10-session change of the EMA-10 close; "washed" compares the same
                        velocity one month earlier.

Evidence framing (reports/china-reversal-gated.md, #754): conditioning the reversal book
on sector state as a FILTER was falsified (flat beats every gate, net, in every era) —
but washed-out sectors carry a marginally HIGHER per-name reversal IC (0.055-0.066 vs
0.041-0.047), i.e. the information is a small per-name TILT. This module therefore only
RE-ORDERS the default board view and highlights rows; it never adds or removes names,
and it feeds nothing downstream (no conviction, no auto-trade).

Best-effort throughout: bad/short data degrades to {} — a missing leg is absent, never
read as neutral.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.confluence_tiers import cascade

log = logging.getLogger(__name__)

# ── sector-washout thresholds (display context, documented not fitted) ────────
WASHOUT_DD_126 = -0.08     # composite >=8% below its 6-month high …
WASHOUT_RET_63 = -0.05     # … or down >=5% over 3 months (either qualifies)
# ── peer-velocity spec (EMA-10 close, 10-session change) ──────────────────────
V_WASHED = -0.03           # was declining >=3% per 10 sessions a month ago
V_BASED = -0.005           # decline velocity collapsed to ~flat (>= -0.5%)
V_PERK = 0.005             # slight positive uptick (>= +0.5%)
# ── leg-B breadth requirements ("washed out along with them" must be broad) ───
PEER_WASHED_FRAC_MIN = 0.25   # >=25% of the sector was in a washout …
PEER_WASHED_N_MIN = 5         # … and at least 5 names
PEER_BASED_FRAC_MIN = 0.40    # >=40% of those washed peers have stopped going down
MIN_MEMBERS = 8               # thin "sectors" can't produce a meaningful composite
MIN_COVERAGE = 0.5            # drop composite days with <50% member coverage
_TURN_TIERS = ("T2", "T3")    # cascade tiers that count as the sector 2Dx3D turn


def _sector_index(rets: pd.DataFrame) -> pd.Series:
    """Equal-weight (daily-return) sector composite, cumulated to a level. Days with
    thin cross-sectional coverage are dropped, not zero-filled."""
    cov = rets.notna().mean(axis=1)
    ew = rets.mean(axis=1)[cov >= MIN_COVERAGE].dropna()
    return (1.0 + ew).cumprod()


def sector_turn_map(closes: pd.DataFrame, tkr_sector: dict, *, asof=None) -> dict:
    """Per-sector washout/turn/peer-basing map for the screener board.

    Returns ``{"as_of": str, "sectors": {sector: rec}}`` where each rec carries the
    washout state, the composite confluence turn (leg A), the peer-basing breadth
    (leg B) and the derived display ``boost`` (2 = sector turn, 1 = peers basing,
    0 = context only). ``{}`` on missing/short data; never raises."""
    try:
        if closes is None or closes.empty:
            return {}
        c = closes.sort_index()
        c = c.loc[:, ~c.columns.duplicated()]
        if asof is not None:
            c = c.loc[:pd.Timestamp(asof)]
        # velocity spec needs EMA10 warm-up + a month of history on top of the 3m window
        if len(c) < 130:
            log.warning("china sector turn: panel too short (%d)", len(c))
            return {}

        by_sector: dict[str, list[str]] = {}
        for t in c.columns:
            s = tkr_sector.get(t)
            if s and s != "—":
                by_sector.setdefault(s, []).append(t)

        out: dict[str, dict] = {}
        for s, cols in by_sector.items():
            live = c[cols].iloc[-1].notna()
            if int(live.sum()) < MIN_MEMBERS:
                continue
            px = c[cols]
            idx = _sector_index(px.pct_change(fill_method=None))
            if len(idx) < 130:
                continue

            ret63 = float(idx.iloc[-1] / idx.iloc[-64] - 1.0)
            dd126 = float(idx.iloc[-1] / idx.iloc[-126:].max() - 1.0)
            washout = (dd126 <= WASHOUT_DD_126) or (ret63 <= WASHOUT_RET_63)

            # leg A — the sector composite's fresh 2D-MACD x 3D-StochRSI turn
            v = cascade(idx)
            tier = v.get("tier") if v.get("tier") in _TURN_TIERS else None
            turn = ({"tier": tier, "ticks": v.get("ticks"), "sub": v.get("sub"),
                     "provisional": bool(v.get("provisional"))} if tier else None)

            # leg B — washed peers whose decline velocity collapsed / ticked up
            ema10 = px.ewm(span=10, adjust=False, min_periods=10).mean()
            v_now = ema10.iloc[-1] / ema10.iloc[-11] - 1.0
            v_prev = ema10.iloc[-22] / ema10.iloc[-32] - 1.0
            washed = (v_prev <= V_WASHED) & v_now.notna()
            based = washed & (v_now >= V_BASED)
            perk = washed & (v_now >= V_PERK)
            n = int(live.sum())
            wn, bn, pn = int(washed.sum()), int(based.sum()), int(perk.sum())
            washed_frac = wn / n if n else 0.0
            based_frac = bn / wn if wn else 0.0

            leg_turn = bool(washout and turn)
            leg_peers = bool(washout and wn >= PEER_WASHED_N_MIN
                             and washed_frac >= PEER_WASHED_FRAC_MIN
                             and based_frac >= PEER_BASED_FRAC_MIN)
            out[s] = {
                "n": n, "washout": washout,
                "ret_63d": round(ret63 * 100, 1), "dd_126d": round(dd126 * 100, 1),
                "turn": turn,
                "peers": {"washed_n": wn, "washed_frac": round(washed_frac, 2),
                          "based_n": bn, "based_frac": round(based_frac, 2),
                          "perk_n": pn},
                "leg_turn": leg_turn, "leg_peers": leg_peers,
                "boost": 2 if leg_turn else (1 if leg_peers else 0),
            }
        if not out:
            return {}
        return {"as_of": str(c.index.max().date()), "sectors": out}
    except Exception as e:  # noqa: BLE001 — display context, never fatal
        log.warning("china sector turn failed (%s) — skipped", e)
        return {}
