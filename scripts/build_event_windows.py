"""scripts/build_event_windows.py — W4 EVW producer (RIC program, P3).

Single writer for two artifacts:

  data/event_windows/forward_log.jsonl
      T-1 ex-ante rows (keep-FIRST idempotent per (release_type, release_date)).
      Ledger-lane-gated: COLLECT_LANE=nightly is the sole advancer.
      Off-lane invocations are read-only (snapshot still written, ledger skipped).

  site/event_windows/snapshot.json
      Current event-window phase + collision states + seasonality stats + optional
      ex-ante read for any release landing within the next 2 trading days.
      Written on every run (display artifact, no lane restriction).

Render-budget law: this script is a cheap read-only join over COMMITTED artifacts only.
No ThetaData / T1 store reads on this lane.  If the SPY options_hub vol payload is
absent (theta-ops lane not run yet), the implied-move leg of the ex-ante read is null —
that null is printed honestly per MRI-R20.

LAWS:
  - MRI-R20: ex-ante read annotates uncertainty; NEVER shifts a projection value.
  - RIC-R3: no score dampener; ex-ante read NEVER scales any score.
  - Display context only: is_context_only=True throughout.
  - Calendar/event-window-gated risk legs FORBIDDEN (DO_NOT_REBUILD.md §4).

Run:
    python -m scripts.build_event_windows
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _spy_close() -> pd.Series | None:
    """Load SPY close from committed yahoo store.  Returns None on any failure."""
    try:
        from lib import store
        df = store.read("yahoo", "SPY")
        if df is None or df.empty:
            return None
        col = "close" if "close" in df.columns else df.columns[0]
        s = df[col].dropna().astype(float)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception as exc:  # noqa: BLE001
        log.warning("build_event_windows: SPY close unavailable (%s) — snapshot will degrade", exc)
        return None


def _spy_vol_payload() -> dict | None:
    """Load committed options_hub vol payload for SPY (theta-ops artifact).

    Returns None when not yet written (theta-ops lane not run); null degrades
    the implied-move leg of ex_ante_read() gracefully (MRI-R20 honesty)."""
    try:
        p = _root() / "site" / "options_hub" / "vol" / "SPY.json"
        if not p.exists():
            log.info("build_event_windows: site/options_hub/vol/SPY.json absent — implied-move leg null")
            return None
        return json.loads(p.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("build_event_windows: vol payload read failed (%s)", exc)
        return None


def _vol_regime_snap() -> str | None:
    """Load gamma_regime proxy from committed vol-regime snapshot.

    site/vol/regime.json is written by build_vol_regime.py (cl_gex cluster,
    runs before build_event_windows in the same cluster).  Returns the 'regime'
    field as the gamma_regime proxy (matches what engine/event_window.py expects
    for the ex-ante read: a plain-word regime string).  Returns None on any failure."""
    try:
        p = _root() / "site" / "vol" / "regime.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        return d.get("snapshot", {}).get("regime") or None
    except Exception as exc:  # noqa: BLE001
        log.warning("build_event_windows: vol regime unavailable (%s)", exc)
        return None


def _release_forecast_integrity_chip(release_type: str) -> dict | None:
    """Load print-integrity chip from the committed release_forecast artifact.

    Reads site/macrodata/release_forecast.json (written by build_release_forecast.py).
    Returns the print_integrity sub-dict for the matching release_type, or None."""
    try:
        p = _root() / "site" / "macrodata" / "release_forecast.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        upcoming = (d.get("upcoming") or [])
        rt_lower = release_type.lower()
        for item in upcoming:
            item_rt = (item.get("release_type") or item.get("release") or "").lower()
            if item_rt == rt_lower or item_rt.startswith(rt_lower):
                pi = item.get("print_integrity")
                if pi:
                    return pi
        return None
    except Exception as exc:  # noqa: BLE001
        log.debug("build_event_windows: print_integrity read failed for %s (%s)", release_type, exc)
        return None


def _trading_days_from_today(close: pd.Series, n: int) -> list[str]:
    """Return the next n trading-day dates from tomorrow onward (ISO strings)."""
    today = pd.Timestamp(date.today())
    future = close.index[close.index > today]
    return [ts.date().isoformat() for ts in future[:n]]


# ---------------------------------------------------------------------------
# Forward-ledger stamping
# ---------------------------------------------------------------------------

def _stamp_forward_log(
    snap: dict,
    close: pd.Series,
    vol_payload: dict | None,
    gamma_regime: str | None,
) -> int:
    """Stamp T-1 rows for any release landing within the next 2 trading days.

    Returns the number of new rows written (0 if lane not armed or all already present).

    Ledger-lane-gated: COLLECT_LANE=nightly is the sole advancer (keep-FIRST).
    Off-lane calls are no-ops."""
    from engine.event_window import stamp_ex_ante, ex_ante_read, ledger_lane_armed

    if not ledger_lane_armed():
        log.info("build_event_windows: ledger_lane not armed — forward-log stamp skipped (read-only run)")
        return 0

    # Find releases within next 2 trading days
    today = date.today()
    td_map = {
        "CPI": snap.get("td_to_cpi"),
        "NFP": snap.get("td_to_nfp"),
        "FOMC": snap.get("td_to_fomc"),
        "PPI": snap.get("td_to_ppi"),
    }

    # Build map from release date to release_type for stamping
    trading_dates = _trading_days_from_today(close, 3)

    written = 0
    for rtype, td in td_map.items():
        if td is None or not isinstance(td, int):
            continue
        if td < 0 or td > 2:
            continue
        # Map td to release date
        if td == 0:
            release_date = today.isoformat()
        elif td <= len(trading_dates):
            release_date = trading_dates[td - 1]
        else:
            continue

        pi_chip = _release_forecast_integrity_chip(rtype)
        phase_stats = (snap.get("seasonality") or {}).get("phases", {}).get(snap.get("phase", "quiet"), {})
        ex = ex_ante_read(
            rtype,
            phase_stats=phase_stats,
            gamma_regime=gamma_regime,
            spy_vol_payload=vol_payload,
            print_integrity_chip=pi_chip,
            today=today,
        )
        did_write = stamp_ex_ante(
            release_type=rtype,
            release_date=release_date,
            ex_ante_dict=ex,
            t_minus_1_snap=snap,
        )
        if did_write:
            written += 1
            log.info("build_event_windows: stamped forward-log row %s %s", rtype, release_date)

    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from engine import event_window as ew
    from lib import config

    spy = _spy_close()
    if spy is None:
        log.warning("build_event_windows: SPY close unavailable — writing degraded snapshot")

    vol_payload = _spy_vol_payload()
    gamma_regime = _vol_regime_snap()

    # Load print-integrity chip for whatever release is nearest (CPI most common)
    # snapshot() internally handles the ex-ante read; integrity chip is loaded per-release
    # in _stamp_forward_log().  For snapshot(), pass the closest-release integrity chip.
    # This is additive context — null degrades gracefully.
    pi_chip = None
    for rtype in ("CPI", "FOMC", "NFP", "PPI"):
        chip = _release_forecast_integrity_chip(rtype)
        if chip:
            pi_chip = chip
            break

    snap = ew.snapshot(
        spy,
        spy_vol_payload=vol_payload,
        gamma_regime=gamma_regime,
        print_integrity_chip=pi_chip,
        today=date.today(),
    )

    # ── Write snapshot ────────────────────────────────────────────────────
    root = _root()
    try:
        site_cfg = config.load().get("storage", {})
        site_dir_name = site_cfg.get("site_dir", "site")
    except Exception:  # noqa: BLE001
        site_dir_name = "site"

    site_out = root / site_dir_name / "event_windows"
    site_out.mkdir(parents=True, exist_ok=True)
    snap_path = site_out / "snapshot.json"
    snap_path.write_text(json.dumps(snap, separators=(",", ":"), default=float))
    log.info(
        "build_event_windows: snapshot written — phase=%s collisions=%s asof=%s",
        snap.get("phase"), snap.get("active_collisions"), snap.get("asof"),
    )

    # ── Grade existing forward-log entries ────────────────────────────────
    if spy is not None:
        from engine.event_window import grade_forward_log
        spy_closes = {ts.date().isoformat(): float(v) for ts, v in spy.items()}
        graded = grade_forward_log(spy_closes=spy_closes)
        if graded:
            log.info("build_event_windows: graded %d forward-log row(s)", graded)

    # ── Stamp T-1 forward-log rows (lane-gated) ───────────────────────────
    n_stamped = 0
    if spy is not None and snap.get("available"):
        n_stamped = _stamp_forward_log(snap, spy, vol_payload, gamma_regime)
    else:
        log.info("build_event_windows: forward-log stamp skipped (snap unavailable or no SPY)")

    log.info(
        "build_event_windows: done — snapshot ok=%s phase=%s stamped=%d",
        snap.get("available"), snap.get("phase"), n_stamped,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
