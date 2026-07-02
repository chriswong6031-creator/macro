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

W1c (P1-B): adaptive broadening lookback + 30v90 drift proxy.
  - ACCEL_LOOKBACK_DAYS (21d) is now the *preference*; if only MIN_ACCEL_DAYS (10d) is
    available the real derivative is computed on that shorter window and `basis_days` is
    set to reflect the actual window used — the read is honest about its basis.
  - When no ≥MIN_ACCEL_DAYS prior snapshot exists, a proxy is computed from per-member
    est_chg_30d vs est_chg_90d: 30d drift > 90d pace ⇒ accelerating.  Output gains
    `proxy: True` and `basis: "drift_30v90"` so consumers can distinguish real from proxy.
  - Falls back to INSUFFICIENT_HISTORY only when neither the archive nor the proxy inputs
    are present.
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
ACCEL_LOOKBACK_DAYS = 21   # preferred PIT span for the broadening derivative
MIN_ACCEL_DAYS = 10        # minimum PIT span — compute real accel on shorter window if needed

WEIGHTS = {"breadth": "mean member net-up share [-1,1]",
           "est_drift_90d": "median member 90d consensus-EPS drift %",
           "breadth_accel": "theme breadth now - breadth ~prior_snapshot ago (PIT, the broadening gauge)"}


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


def _accel_state(breadth_now: float, accel: float) -> str:
    """Map (breadth_now, accel) to the canonical broadening state vocabulary."""
    if abs(breadth_now) < FLAT_BAND and accel <= 0:
        return "FLAT_LOW"   # PRECIPICE-compatible: revisions not yet firing
    elif accel > 0 and breadth_now > 0:
        return "RISING"     # revision wave underway -> runway
    elif accel < 0 and breadth_now > 0:
        return "ROLLING"    # wave maturing
    else:
        return "MIXED"


def _broadening_proxy(members: list[str], latest: pd.DataFrame) -> dict | None:
    """Drift-proxy for broadening when no ≥MIN_ACCEL_DAYS prior snapshot exists.

    Compares est_chg_30d vs est_chg_90d per member: if the 30d drift is stronger than
    the annualised 90d pace, the revision wave is accelerating.  Uses the same state
    vocabulary as _broadening (RISING/FLAT_LOW/ROLLING/MIXED) but adds proxy:True and
    basis:"drift_30v90" so downstream consumers can distinguish real from proxy.

    Returns None when the proxy inputs are absent (no est_chg_30d/est_chg_90d columns
    or no covered members with MIN_ANALYSTS coverage).
    """
    if not {"est_chg_30d", "est_chg_90d", "n_analysts"}.issubset(latest.columns):
        return None
    present = [m for m in members if m in latest.index]
    if not present:
        return None
    rows = latest.loc[present]
    if isinstance(rows, pd.Series):
        rows = rows.to_frame().T
    covered = rows[rows["n_analysts"] >= MIN_ANALYSTS]
    if covered.empty:
        return None

    # annualise the 90d rate to a 30d equivalent: pace_30d = est_chg_90d / 3
    # positive difference = 30d drift is running *ahead* of the 90d pace => accelerating
    pace_30d = covered["est_chg_90d"] / 3.0
    drift_diff = covered["est_chg_30d"] - pace_30d
    median_diff = float(drift_diff.median())

    # proxy breadth-direction signal: sign of median drift-diff
    if median_diff > 0:
        state = "RISING"
    elif median_diff < 0:
        state = "ROLLING"
    else:
        state = "FLAT_LOW"

    return {
        "broadening_state": state,
        "broadening_proxy": True,
        "basis": "drift_30v90",
        "basis_days": None,         # no PIT window
        "breadth_accel": None,      # no derivative yet
        "proxy_drift_diff": round(median_diff, 3),
    }


def _broadening(theme: str, members: list[str], hist: pd.DataFrame | None,
                breadth_now: float | None,
                latest: pd.DataFrame | None = None) -> dict:
    """PIT derivative of theme breadth.  Returns a dict with broadening_state, breadth_accel,
    basis_days, and optionally proxy/basis fields.

    Adaptive lookback (W1c / P1-B):
      1. Prefer a prior snapshot ≥ ACCEL_LOOKBACK_DAYS (21d) back — legacy behaviour.
      2. Accept any prior snapshot ≥ MIN_ACCEL_DAYS (10d) back and set basis_days to the
         actual window used so the read is honest about its shorter basis.
      3. When no ≥MIN_ACCEL_DAYS snapshot exists, fall back to the drift proxy if latest
         carries est_chg_30d/est_chg_90d; proxy:True is emitted alongside the state.
      4. INSUFFICIENT_HISTORY only when even the proxy inputs are absent.

    Never raises; always returns a dict.
    """
    no_history_result = {
        "broadening_state": "INSUFFICIENT_HISTORY",
        "breadth_accel": None,
        "basis_days": None,
    }

    # --- attempt real PIT derivative ------------------------------------------
    if breadth_now is not None and hist is not None:
        h = hist[hist["ticker"].isin(members)].copy()
        if not h.empty and "asof" in h.columns:
            h["asof"] = pd.to_datetime(h["asof"])
            asofs = sorted(h["asof"].unique())
            if len(asofs) >= 2:
                latest_asof = asofs[-1]
                # prefer ≥21d; accept ≥10d
                prior_candidates_full = [a for a in asofs
                                         if (latest_asof - a).days >= ACCEL_LOOKBACK_DAYS]
                prior_candidates_min = [a for a in asofs
                                        if (latest_asof - a).days >= MIN_ACCEL_DAYS]

                prior_asof = None
                if prior_candidates_full:
                    prior_asof = prior_candidates_full[-1]
                elif prior_candidates_min:
                    prior_asof = prior_candidates_min[-1]

                if prior_asof is not None:
                    prev = _theme_breadth(h[h["asof"] == prior_asof].set_index("ticker"))
                    if prev is not None:
                        basis_days = int((latest_asof - prior_asof).days)
                        accel = round(breadth_now - prev, 3)
                        state = _accel_state(breadth_now, accel)
                        return {
                            "broadening_state": state,
                            "breadth_accel": accel,
                            "basis_days": basis_days,
                        }

    # --- fall back to drift proxy when no PIT window ---------------------------
    if latest is not None:
        proxy = _broadening_proxy(members, latest)
        if proxy is not None:
            return proxy

    return no_history_result


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
             if (not covered.empty and "est_chg_90d" in covered.columns) else None)
    net_up_total = (round(float(covered["net_up_30d"].sum()), 1)
                    if (not covered.empty and "net_up_30d" in covered.columns) else None)
    bn = _broadening(theme_key, members, hist, breadth, latest)
    # top member contributors for transparency (largest |breadth| with coverage)
    contrib = []
    for tk, r in covered.sort_values("breadth").iterrows():
        entry: dict = {"ticker": str(tk), "breadth": round(float(r["breadth"]), 2),
                       "n_analysts": int(r["n_analysts"])}
        if "est_chg_90d" in r.index:
            entry["est_chg_90d"] = round(float(r["est_chg_90d"]), 1)
        contrib.append(entry)
    out = {
        "name": name,
        "breadth": breadth,
        "level_state": _level_state(breadth),
        "est_drift_90d": drift,
        "net_up_total": net_up_total,
        "breadth_accel": bn.get("breadth_accel"),
        "broadening_state": bn.get("broadening_state", "INSUFFICIENT_HISTORY"),
        "coverage": round(len(covered) / len(members), 2),
        "n_covered": int(len(covered)),
        "n_members": len(members),
        "members": contrib[:8],
    }
    # surface the adaptive-lookback / proxy fields when present
    if bn.get("basis_days") is not None:
        out["basis_days"] = bn["basis_days"]
    if bn.get("broadening_proxy"):
        out["broadening_proxy"] = True
        out["basis"] = bn.get("basis", "drift_30v90")
        if bn.get("proxy_drift_diff") is not None:
            out["proxy_drift_diff"] = bn["proxy_drift_diff"]
    return out


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
        row = {
            "theme": key, "asof": asof, "ts": ts,
            "breadth": t["breadth"], "breadth_accel": t["breadth_accel"],
            "broadening_state": t["broadening_state"], "est_drift_90d": t["est_drift_90d"],
            "n_covered": t["n_covered"],
        }
        if t.get("basis_days") is not None:
            row["basis_days"] = t["basis_days"]
        if t.get("broadening_proxy"):
            row["broadening_proxy"] = True
            row["basis"] = t.get("basis", "drift_30v90")
        lines.append(json.dumps(row, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
