"""Forward-outcome ledger for the BTC impulse radar (P3).

Accountability: every build STAMPS the day's radar state + which act legs fired +
BTC close into data/vector/impulse_ledger.jsonl (idempotent — one row per asof).
On later builds, GRADE() fills the forward outcome for matured rows (>= 3 trading
days later): did a fired DOWN leg actually precede a -5%/3d down-move, did a fired
UP leg precede a +5%/3d up-move. That live hit-rate is what the falsifier
(btc_impulse_radar_backtest) and a human use to see a leg decay in real time,
rather than trusting the historical backtest forever.

Schema (one JSON object per line):
  {asof, down_score, down_ladder, down_act, up_score, up_ladder, up_act,
   fires:{d2,d3,u1}, btc_close, outcome:{matured, fwd_min_pct, fwd_max_pct,
   down_hit, up_hit} | null}
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

LABEL_H = 3        # trading-day forward horizon (matches the backtest label)
LABEL_THR = 0.05   # +-5%


def _path():
    return config.data_dir() / "vector" / "impulse_ledger.jsonl"


def load() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write(rows: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""))


def _fired(legs: list[dict], key: str) -> bool:
    for l in legs or []:
        if l.get("key") == key:
            return bool(l.get("fired_today"))
    return False


def stamp(radar: dict | None, sig_df: pd.DataFrame | None = None) -> None:
    """Append today's radar row (idempotent on asof). Never raises."""
    try:
        if not radar or not radar.get("ok"):
            return
        asof = radar.get("asof")
        if not asof:
            return
        rows = load()
        if rows and rows[-1].get("asof") == asof:
            return  # already stamped this build-day
        down, up = radar.get("down", {}), radar.get("up", {})
        close = None
        if sig_df is not None and "close" in sig_df.columns and len(sig_df):
            close = float(sig_df["close"].iloc[-1])
        rows.append({
            "asof": asof,
            "down_score": down.get("score"), "down_ladder": down.get("ladder"),
            "down_act": bool(down.get("act_live")),
            "up_score": up.get("score"), "up_ladder": up.get("ladder"),
            "up_act": bool(up.get("act_live")),
            "fires": {"d2": _fired(down.get("legs"), "d2_dvol"),
                      "d3": _fired(down.get("legs"), "d3_sopr"),
                      "u1": _fired(up.get("legs"), "u1_sopr")},
            "btc_close": close,
            "outcome": None,
        })
        _write(rows)
    except Exception as e:  # noqa: BLE001 — ledger is additive, never fatal
        log.debug("impulse ledger stamp skipped: %s", e)


def grade(sig_df: pd.DataFrame | None = None) -> dict:
    """Fill forward outcomes for matured rows. Returns a small summary. Never raises."""
    try:
        if sig_df is None or "close" not in sig_df.columns:
            return {"ok": False, "reason": "no close series"}
        close = sig_df["close"].copy()
        close.index = pd.to_datetime(close.index)
        close = close.sort_index()
        rows = load()
        graded = 0
        for r in rows:
            try:                              # one corrupt/hand-edited row must NOT abort
                if r.get("outcome") is not None:  # grading of every other matured row
                    continue
                ts = pd.Timestamp(r["asof"])
                if ts not in close.index:
                    continue
                pos = close.index.get_loc(ts)
                if pos + LABEL_H >= len(close):
                    continue  # not matured yet
                base = float(close.iloc[pos])
                fwd = close.iloc[pos + 1: pos + 1 + LABEL_H]
                if fwd.empty or base <= 0:
                    continue
                fwd_min = float(fwd.min()) / base - 1.0
                fwd_max = float(fwd.max()) / base - 1.0
                down_fired = any(r.get("fires", {}).get(k) for k in ("d2", "d3"))
                up_fired = bool(r.get("fires", {}).get("u1"))
                r["outcome"] = {
                    "matured": True,
                    "fwd_min_pct": round(fwd_min * 100, 2),
                    "fwd_max_pct": round(fwd_max * 100, 2),
                    "down_hit": bool(down_fired and fwd_min <= -LABEL_THR),
                    "up_hit": bool(up_fired and fwd_max >= LABEL_THR),
                }
                graded += 1
            except Exception as e:  # noqa: BLE001 — skip the bad row, keep grading the rest
                log.debug("impulse ledger: skipped a bad row (%s): %s", r.get("asof"), e)
                continue
        if graded:
            _write(rows)
        return render_summary(rows)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def render_summary(rows: list[dict] | None = None) -> dict:
    """Rolling forward hit-rate per direction over matured fires (for display)."""
    rows = rows if rows is not None else load()
    matured = [r for r in rows if (r.get("outcome") or {}).get("matured")]
    down_fires = [r for r in matured if any(r["fires"].get(k) for k in ("d2", "d3"))]
    up_fires = [r for r in matured if r["fires"].get("u1")]
    def _rate(fires, key):
        return round(sum(1 for r in fires if r["outcome"].get(key)) / len(fires), 3) if fires else None
    return {
        "ok": True, "n_rows": len(rows), "n_matured": len(matured),
        "down": {"n_fires": len(down_fires), "hit_rate": _rate(down_fires, "down_hit")},
        "up": {"n_fires": len(up_fires), "hit_rate": _rate(up_fires, "up_hit")},
        "note": ("Live forward hit-rate of the radar's act-tier fires (matured "
                 ">=3d). Thin until fires accrue; complements the historical "
                 "backtest — a decaying hit-rate is the early decay signal."),
    }
