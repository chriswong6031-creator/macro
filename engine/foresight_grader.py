"""Foresight forward-grading — the learning loop of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md, Phase 5). Makes the desk's own hit-rate measured,
public, and immutable.

The cascade logs every actionable flag at fire time (data/foresight/log.jsonl for
PRECIPICE/BROADENING theses; data/glut_watch/log.jsonl for GLUT exit calls). This grader
re-opens each flag once it has MATURED (asof + horizon in the past), computes the theme's
realized equal-weight return vs SPY over the horizon, and records hit/miss — a thesis hits
if the theme OUTPERFORMED SPY; a glut call hits if it UNDERPERFORMED. Writes
data/foresight/track_record.json (per-stage hit-rate + average excess), which the desk page
publishes verbatim.

HONEST BY CONSTRUCTION: the ledgers only began accruing recently, so until flags mature this
reports n_graded=0 / n_pending=N — never a fabricated hit-rate. Forward-only (no look-ahead);
this is the only trustworthy way to learn the desk's true precision. Pure given the stores.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

HORIZON_DAYS = 90          # ~63 trading days — the revision-momentum / PEAD horizon
MIN_MEMBERS = 2           # need >=2 priced members to grade a theme


def _closes(ticker: str) -> pd.Series | None:
    p = config.data_dir() / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if "close" not in df.columns:
        return None
    s = df["close"].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _ret(s: pd.Series | None, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    """Total return between the first close on/after `start` and the first on/after `end`.
    None if either side is missing (end beyond the data = not yet matured)."""
    if s is None:
        return None
    a = s[s.index >= start]
    b = s[s.index >= end]
    if a.empty or b.empty:
        return None
    p0, p1 = float(a.iloc[0]), float(b.iloc[0])
    if p0 <= 0:
        return None
    return p1 / p0 - 1.0


def _theme_excess(members: list[str], start: pd.Timestamp, end: pd.Timestamp,
                  spy: pd.Series | None) -> float | None:
    spy_ret = _ret(spy, start, end)
    if spy_ret is None:
        return None
    rets = [r for r in (_ret(_closes(m), start, end) for m in members) if r is not None]
    if len(rets) < MIN_MEMBERS:
        return None
    return (sum(rets) / len(rets)) - spy_ret           # equal-weight theme excess vs SPY


def _read_ledger(rel: str) -> list[dict]:
    p = config.data_dir() / rel
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def grade(today: pd.Timestamp | None = None, write: bool = True) -> dict:
    """Grade every matured flag; return + persist the track record."""
    if today is None:
        today = pd.Timestamp.now().normalize()
    themes = (config.load() or {}).get("themes") or {}
    spy = _closes("SPY")

    # (ledger, stage-key, hit-direction): thesis hits on OUTperformance, glut on UNDERperformance
    sources = [("foresight/log.jsonl", None, +1), ("glut_watch/log.jsonl", "GLUT-EXIT", -1)]
    by_stage: dict[str, dict] = {}
    n_total = n_graded = n_pending = 0

    for rel, force_stage, direction in sources:
        for e in _read_ledger(rel):
            theme = e.get("theme")
            asof = e.get("asof")
            stage = force_stage or e.get("stage") or "UNKNOWN"
            if not theme or not asof or theme not in themes:
                continue
            n_total += 1
            start = pd.Timestamp(asof)
            end = start + pd.Timedelta(days=HORIZON_DAYS)
            if today < end:
                n_pending += 1
                continue
            excess = _theme_excess(themes[theme].get("tickers") or [], start, end, spy)
            if excess is None:
                n_pending += 1                          # data not yet available to grade
                continue
            hit = (excess * direction) > 0
            b = by_stage.setdefault(stage, {"n": 0, "hits": 0, "sum_excess": 0.0})
            b["n"] += 1
            b["hits"] += 1 if hit else 0
            b["sum_excess"] += excess
            n_graded += 1

    for stage, b in by_stage.items():
        b["hit_rate"] = round(b["hits"] / b["n"], 3) if b["n"] else None
        b["avg_excess_pct"] = round(100.0 * b["sum_excess"] / b["n"], 2) if b["n"] else None
        b.pop("sum_excess", None)

    summary = {
        "updated": str(today.date()),
        "horizon_days": HORIZON_DAYS,
        "n_total": n_total, "n_graded": n_graded, "n_pending": n_pending,
        "by_stage": by_stage,
        "note": ("forward-only hit-rate of the desk's PRECIPICE/BROADENING theses (hit = "
                 "theme outperformed SPY over ~3mo) and GLUT exit calls (hit = underperformed). "
                 "Immutable; accrues as flags mature — n_graded=0 until the first flags age in."),
    }
    if write:
        try:
            d = config.data_dir() / "foresight"
            d.mkdir(parents=True, exist_ok=True)
            (d / "track_record.json").write_text(json.dumps(summary, separators=(",", ":")))
        except Exception as e:  # noqa: BLE001
            log.warning("track_record write failed: %s", e)
    return summary
