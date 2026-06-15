"""Prediction-markets read — market-implied macro odds for the dashboard.

ADDITIVE / leaf module — imports nothing from the scoring core, and nothing in the
scoring path imports it. Reads the dated snapshots collectors/prediction_markets.py
accrues and surfaces, per configured event, the current outcome probabilities + the
day-over-day change. Market-EXPECTATION context (what the crowd is pricing for the
next Fed decision / cuts this year / recession), pairs with the FOMC/jobs catalyst
calendar. Never wired into any score.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from lib import config, store  # noqa: F401  (store kept for parity / future use)

log = logging.getLogger(__name__)


def _cfg() -> dict:
    return config.load().get("prediction_markets", {}) or {}


def _load() -> pd.DataFrame | None:
    p = config.data_dir() / "prediction_markets" / "snapshots.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("prediction snapshots unreadable (%s)", e)
        return None


def build_panel(df: pd.DataFrame, events_cfg: dict, top_n: int = 6) -> dict | None:
    """PURE — from the snapshot frame + the event config, assemble the panel:
    latest probabilities per event + day-over-day change vs the prior snapshot."""
    if df is None or df.empty:
        return None
    dates = sorted(df["snapshot_date"].unique())
    latest = dates[-1]
    prior = dates[-2] if len(dates) >= 2 else None
    cur = df[df["snapshot_date"] == latest]
    prv = df[df["snapshot_date"] == prior] if prior else df.iloc[0:0]
    pmap = {(r.event_key, r.outcome): r.prob for r in prv.itertuples()}

    events = []
    for key, spec in events_cfg.items():
        sub = cur[cur["event_key"] == key]
        if sub.empty:
            continue
        outs = []
        for r in sub.sort_values("prob", ascending=False).itertuples():
            p0 = pmap.get((key, r.outcome))
            outs.append({"outcome": r.outcome, "prob": round(float(r.prob) * 100, 1),
                         "chg_pp": (None if p0 is None else round((float(r.prob) - float(p0)) * 100, 1))})
        if not outs:
            continue
        events.append({
            "key": key, "label_en": spec.get("label_en", key), "label_zh": spec.get("label_zh", key),
            "title": str(sub["event_title"].iloc[0]), "end_date": str(sub["end_date"].iloc[0]),
            "top": outs[0], "outcomes": outs[:top_n],
        })
    if not events:
        return None
    return {
        "asof": str(latest), "prior": (str(prior) if prior else None),
        "built": datetime.now(timezone.utc).isoformat(),
        "source": "Polymarket", "events": events,
        "note": ("Market-IMPLIED probabilities from Polymarket (keyless). What traders are "
                 "pricing for the next Fed decision, cuts this year, and recession — a "
                 "crowd-expectation read that pairs with the catalyst calendar. Δ is vs the "
                 "prior daily snapshot. Context, not a forecast or a signal — never scored."),
    }


def snapshot() -> dict | None:
    return build_panel(_load(), _cfg().get("events", {}) or {})
