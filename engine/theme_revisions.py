"""Theme revision-breadth broadening — T4 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md).

THE IDEA. Analyst EPS-estimate revisions are *lagging* if you wait for them to print,
but they TREND hard once they start (Mill Street: ~83% one-month persistence, IC≈0.23) —
so revision-breadth is the **confirmation / runway gauge** of a theme, never the entry.
The entry thesis is the physical bottleneck (engine/bottleneck.py); this leg answers the
companion question: *has the revision wave started for this theme, and is it broadening?*

The HBM template makes the use explicit:
  TIGHT bottleneck + FLAT revision breadth  = PRECIPICE (early — the June-2024 state)
  TIGHT bottleneck + RISING breadth, narrowing dispersion = runway CONFIRMED.

We roll the per-name revision reads (collectors/equity_revisions.py ->
data/revisions/{latest,history}.parquet; cols net_up_30d, breadth, est_chg_30d/90d,
n_analysts, asof) up to each curated theme in config `themes:` (memory_storage,
ai_semiconductors, semicap_equipment, ...). The `breadth_accel` broadening gauge is a
point-in-time DERIVATIVE off history.parquet — it reports INSUFFICIENT_HISTORY until the
PIT archive (which only began accruing recently) spans the lookback, so there is no
look-ahead. Pure given the two existing stores; DISPLAY-ONLY, never a scored leg.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

MIN_ANALYSTS = 3            # thin-coverage guard — a name needs >=3 estimates to count
FLAT_BAND = 0.10           # |breadth| < this = "not yet firing" (PRECIPICE-compatible)
ACCEL_LOOKBACK_DAYS = 21   # min PIT span before the broadening derivative is trustworthy

WEIGHTS = {"breadth": "mean member net-up share [-1,1]",
           "est_drift_90d": "median member 90d consensus-EPS drift %",
           "breadth_accel": "theme breadth now - breadth ~30d ago (PIT, the broadening gauge)"}


def _latest() -> pd.DataFrame | None:
    p = config.data_dir() / "revisions" / "latest.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("revisions latest unreadable: %s", e)
        return None
    return df if not df.empty else None


def _history() -> pd.DataFrame | None:
    p = config.data_dir() / "revisions" / "history.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return None
    return df if (df is not None and not df.empty and "ticker" in df.columns) else None


def _theme_breadth(rows: pd.DataFrame) -> float | None:
    """Mean net-up share over members with >=MIN_ANALYSTS coverage. None if too thin."""
    ok = rows[rows["n_analysts"] >= MIN_ANALYSTS]
    if ok.empty:
        return None
    return round(float(ok["breadth"].mean()), 3)


def _broadening(theme: str, members: list[str], hist: pd.DataFrame | None,
                breadth_now: float | None) -> tuple[float | None, str]:
    """PIT derivative of theme breadth. Returns (breadth_accel, state).

    INSUFFICIENT_HISTORY until history.parquet spans ACCEL_LOOKBACK_DAYS — no look-ahead."""
    if breadth_now is None or hist is None:
        return None, "INSUFFICIENT_HISTORY"
    h = hist[hist["ticker"].isin(members)].copy()
    if h.empty or "asof" not in h.columns:
        return None, "INSUFFICIENT_HISTORY"
    h["asof"] = pd.to_datetime(h["asof"])
    asofs = sorted(h["asof"].unique())
    if len(asofs) < 2:
        return None, "INSUFFICIENT_HISTORY"
    latest_asof = asofs[-1]
    # the most recent snapshot at least ACCEL_LOOKBACK_DAYS before the latest
    prior_candidates = [a for a in asofs
                        if (latest_asof - a).days >= ACCEL_LOOKBACK_DAYS]
    if not prior_candidates:
        return None, "INSUFFICIENT_HISTORY"
    prior_asof = prior_candidates[-1]
    prev = _theme_breadth(h[h["asof"] == prior_asof].set_index("ticker"))
    if prev is None:
        return None, "INSUFFICIENT_HISTORY"
    accel = round(breadth_now - prev, 3)
    if abs(breadth_now) < FLAT_BAND and accel <= 0:
        state = "FLAT_LOW"          # PRECIPICE-compatible: revisions not yet firing
    elif accel > 0 and breadth_now > 0:
        state = "RISING"            # revision wave underway -> runway
    elif accel < 0 and breadth_now > 0:
        state = "ROLLING"           # wave maturing
    else:
        state = "MIXED"
    return accel, state


def _level_state(breadth: float | None) -> str:
    if breadth is None:
        return "NO_COVERAGE"
    if abs(breadth) < FLAT_BAND:
        return "FLAT_LOW"
    return "POSITIVE" if breadth > 0 else "NEGATIVE"


def theme_revisions_for(theme_key: str, name: str, members: list[str],
                        latest: pd.DataFrame, hist: pd.DataFrame | None) -> dict | None:
    present = [m for m in members if m in latest.index]
    if not present:
        return None
    rows = latest.loc[present]
    if isinstance(rows, pd.Series):       # single member -> normalize to frame
        rows = rows.to_frame().T
    covered = rows[rows["n_analysts"] >= MIN_ANALYSTS]
    breadth = _theme_breadth(rows)
    drift = (round(float(covered["est_chg_90d"].median()), 2)
             if not covered.empty else None)
    net_up_total = (round(float(covered["net_up_30d"].sum()), 1)
                    if not covered.empty else None)
    accel, broadening_state = _broadening(theme_key, members, hist, breadth)
    # top member contributors for transparency (largest |breadth| with coverage)
    contrib = []
    for tk, r in covered.sort_values("breadth").iterrows():
        contrib.append({"ticker": str(tk), "breadth": round(float(r["breadth"]), 2),
                        "est_chg_90d": round(float(r["est_chg_90d"]), 1),
                        "n_analysts": int(r["n_analysts"])})
    return {
        "name": name,
        "breadth": breadth,
        "level_state": _level_state(breadth),
        "est_drift_90d": drift,
        "net_up_total": net_up_total,
        "breadth_accel": accel,
        "broadening_state": broadening_state,
        "coverage": round(len(covered) / len(members), 2),
        "n_covered": int(len(covered)),
        "n_members": len(members),
        "members": contrib[:8],
    }


def compute_theme_revisions(write_ledger: bool = True) -> dict | None:
    """Per-theme revision-breadth read over config `themes:`. DISPLAY-ONLY.

    Returns None when the revisions cache is absent (no run has collected it yet)."""
    latest = _latest()
    if latest is None:
        return None
    hist = _history()
    themes = (config.load() or {}).get("themes") or {}
    if not themes:
        return None
    asof = None
    if "asof" in latest.columns and not latest["asof"].isna().all():
        asof = str(pd.to_datetime(latest["asof"]).max().date())

    out: dict[str, dict] = {}
    for key, spec in themes.items():
        members = spec.get("tickers") or []
        name = spec.get("name", key)
        try:
            r = theme_revisions_for(key, name, members, latest, hist)
        except Exception as e:  # noqa: BLE001 — one theme failing never blocks the rest
            log.warning("theme_revisions[%s] failed: %s", key, e)
            r = None
        if r is not None:
            out[key] = r
    if not out:
        return None

    payload = {
        "asof": asof,
        "n_themes": len(out),
        "themes": out,
        "weights": WEIGHTS,
        "note": ("display-only; revision breadth is the CONFIRMATION / runway gauge, "
                 "NOT the entry — pair with engine/bottleneck.py (TIGHT bottleneck + "
                 "FLAT breadth = PRECIPICE)."),
    }
    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001 — logging is never fatal
            log.warning("theme_revisions ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only forward-grading ledger: one row per (theme, asof). Deduped so a
    rebuild on the same asof does not spam. Graded forward by a later pass (did breadth
    keep broadening? did the basket outperform?)."""
    d = config.data_dir() / "themes"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "revisions_log.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    ts = datetime.now(timezone.utc).isoformat()
    asof = payload.get("asof")
    lines = []
    for key, t in payload["themes"].items():
        if (key, asof) in seen:
            continue
        lines.append(json.dumps({
            "theme": key, "asof": asof, "ts": ts,
            "breadth": t["breadth"], "breadth_accel": t["breadth_accel"],
            "broadening_state": t["broadening_state"], "est_drift_90d": t["est_drift_90d"],
            "n_covered": t["n_covered"],
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
