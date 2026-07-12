"""engine/sector_fragmentation.py — is the sector aggregate representative? (RC-R6, W1).

The 2026-06-25 failure mode: XLK's cap-weighted close held Topping/SELL veto over every
leg-level read while its legs pointed opposite ways (memory −20%, Mag-7 +11% over the same
sessions). This module computes, per registered sector (config/sector_legs.json):

  • the 20-session return of each leg and of the sector ETF;
  • the leg SPREAD (best minus worst leg, in return points);
  • whether legs DISAGREE IN SIGN materially (best ≥ +3% while worst ≤ −3%);
  • each leg's leg/ETF ratio 20-session change as a z-score vs its own trailing year
    (how abnormal is this leg's divergence from its parent, by its own history).

fragmented=True ⇒ the sector card prints "aggregate not representative — legs disagree"
with the actual legs (RC-R3 chip). DISPLAY/CONTEXT TIER: this flags disagreement; it does
not change any phase, stance, gate, rank, or size (gate surgery is RC-R9 prereg work).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

SCHEMA = "sector_fragmentation.v1"

PARAMS = {
    "ret_len": 20,          # the comparison horizon (sessions)
    "spread_min": 0.12,     # spread alone that flags fragmentation
    "spread_opposite": 0.08,  # spread bar when legs also disagree in sign
    "opposite_min": 0.03,   # |return| each side needs for a sign disagreement to count
    "z_win": 252,           # trailing window for the ratio-change z-score
    "z_min_obs": 120,       # minimum observations to trust the z
    "ratio_z_flag": 2.5,    # any leg this abnormal vs its parent flags fragmentation
}


def _ret_n(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) < n + 1:
        return None
    prev = float(s.iloc[-(n + 1)])
    return (float(s.iloc[-1]) / prev - 1.0) if prev else None


def _ratio_z(leg: pd.Series, etf: pd.Series, p: dict) -> float | None:
    r = (leg / etf).dropna()
    ch = r.pct_change(p["ret_len"]).dropna()
    if len(ch) < p["z_min_obs"]:
        return None
    hist = ch.iloc[-p["z_win"]:]
    sd = float(hist.std())
    if not np.isfinite(sd) or sd < 1e-9:      # degenerate/zero-variance history → no claim
        return None
    return float((ch.iloc[-1] - hist.mean()) / sd)


def sector_row(sec: dict, p: dict = PARAMS) -> dict | None:
    """One sector's fragmentation read from a sector_legs.sector_closes() entry."""
    cfg, etf_close, legs = sec["cfg"], sec["etf_close"], sec["legs"]
    ret_etf = _ret_n(etf_close, p["ret_len"])
    rows = []
    for l in cfg.get("legs", []):
        s = legs.get(l["key"])
        if s is None:
            continue
        r = _ret_n(s, p["ret_len"])
        if r is None:
            continue
        rows.append({"key": l["key"], "name_en": l["name_en"], "name_zh": l["name_zh"],
                     "tier": l.get("tier"), "ret": round(r, 4),
                     "vs_etf": round(r - ret_etf, 4) if ret_etf is not None else None,
                     "ratio_z": (lambda z: round(z, 2) if z is not None else None)(
                         _ratio_z(s, etf_close, p))})
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: r["ret"], reverse=True)
    top, bottom = rows[0], rows[-1]
    spread = top["ret"] - bottom["ret"]
    opposite = top["ret"] >= p["opposite_min"] and bottom["ret"] <= -p["opposite_min"]
    max_abs_z = max((abs(r["ratio_z"]) for r in rows if r["ratio_z"] is not None),
                    default=None)
    fragmented = bool(
        spread >= p["spread_min"]
        or (opposite and spread >= p["spread_opposite"])
        or (max_abs_z is not None and max_abs_z >= p["ratio_z_flag"])
    )
    copy_en = copy_zh = None
    if fragmented:
        copy_en = (f"Aggregate read may not be representative — "
                   f"{top['name_en']} {top['ret']:+.1%} vs {bottom['name_en']} "
                   f"{bottom['ret']:+.1%} over {p['ret_len']} sessions.")
        copy_zh = (f"板块聚合读数或失真 — {top['name_zh']} {top['ret']:+.1%}，"
                   f"{bottom['name_zh']} {bottom['ret']:+.1%}（{p['ret_len']}个交易日）。")
    return {"key": cfg["key"], "etf": cfg["etf"],
            "name_en": cfg["name_en"], "name_zh": cfg["name_zh"],
            "asof": str(etf_close.dropna().index[-1].date()),
            "ret_etf": round(ret_etf, 4) if ret_etf is not None else None,
            "spread": round(spread, 4), "opposite_signs": bool(opposite),
            "max_abs_ratio_z": max_abs_z, "fragmented": fragmented,
            "legs": rows, "copy_en": copy_en, "copy_zh": copy_zh}


def compute(sectors: dict, p: dict = PARAMS, generated_utc: str | None = None) -> dict:
    """The full board: {schema, as_of, sectors: [row...]} for
    site/marketdata/sector_fragmentation.json."""
    rows = []
    for sec in sectors.values():
        try:
            row = sector_row(sec, p)
        except Exception as e:  # noqa: BLE001 — one bad sector never kills the board
            log.warning("sector_fragmentation: %s failed (%s)", sec["cfg"].get("key"), e)
            row = None
        if row:
            rows.append(row)
    rows.sort(key=lambda r: r["spread"], reverse=True)
    return {"schema": SCHEMA, "ok": bool(rows),
            "as_of": max((r["asof"] for r in rows), default=None),
            "generated_utc": generated_utc,
            "authority": {"tier": "display", "may_rank": False, "may_gate": False,
                          "may_size": False, "may_escalate": False},
            "params": p,
            "n_fragmented": sum(1 for r in rows if r["fragmented"]),
            "sectors": rows}
