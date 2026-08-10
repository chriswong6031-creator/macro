"""engine.price_pressure.panel — the single import seam onto LSR-P0.

THE WHOLE POINT OF THIS MODULE IS THAT IT CONTAINS NO MATH.  The frozen base
rates this lobe publishes (masterplan §6) were measured on the LSR-P0
construction, so the display must quote distributions computed on *the same*
residual it shows.  A re-typed copy of the panel build or the peer
residualisation would drift silently and invalidate every published table on the
day it drifted.  Therefore: every construction below is IMPORTED from
``scripts/research_liquidity_shock_reversal.py`` and re-exported by name.

Deliberately NOT swapped for ``engine/residual_alpha.py``'s Vasicek beta
regression — that is a masterplan §8 research leg, never a silent substitution.

The one underscore-private import is none: LSR exposes everything this lobe
needs publicly.  If that ever changes, re-export it HERE with a comment saying
why, so the seam stays one file wide.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:  # a bare `python -m scripts.…` run has it already
    sys.path.insert(0, str(_REPO))

# ── the seam ────────────────────────────────────────────────────────────────
# Imported, never copied (masterplan §0 acceptance gate).
from scripts.research_liquidity_shock_reversal import (  # noqa: E402
    BASE_WIN,
    FWD_HORIZONS,
    MIN_ADV_EVENT,
    MIN_ADV_PANEL,
    MIN_PRICE,
    NEWS_WINDOW_DAYS,
    VOL_TRIGGER,
    Z_TRIGGER,
    build_panel,
    corwin_schultz,
    date_block_ci,
    derive,
    harvest_events,
    news_flags,
    sector_ex_self_peer,
)

__all__ = [
    "BASE_WIN", "FWD_HORIZONS", "MIN_ADV_EVENT", "MIN_ADV_PANEL", "MIN_PRICE",
    "NEWS_WINDOW_DAYS", "VOL_TRIGGER", "Z_TRIGGER",
    "build_panel", "corwin_schultz", "date_block_ci", "derive", "harvest_events",
    "news_flags", "sector_ex_self_peer",
    "PANEL_COLUMNS", "load_panel", "panel_sessions", "store_status",
]

#: The wide frames ``build_panel`` caches, in its own order.
PANEL_COLUMNS: tuple[str, ...] = (
    "open", "high", "low", "close", "volume", "transactions", "split_day",
)


def load_panel(cache: Path, store: Path) -> dict[str, pd.DataFrame]:
    """Split-repaired, liquidity-filtered wide panel (LSR ``build_panel``).

    THE NIGHTLY REBUILDS THIS IN MEMORY EVERY RUN (measured 45-60s, §4.0).  No
    wide-frame cache is committed or published anywhere — a stale ~170MB panel
    silently answering "what happened last night" is worse than 45 seconds of
    scanning (masterplan §4, review finding 13).  ``cache`` therefore points at
    a LOCAL scratch dir and exists only as a convenience for the manual backfill;
    the nightly passes a temp dir it throws away.
    """
    return build_panel(Path(cache), Path(store))


def panel_sessions(panel: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """The panel's trading-session index — the lobe's only notion of "a session"."""
    return pd.DatetimeIndex(panel["close"].index)


def _sessions_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    """Calendar days a->b as an approximate session count (~5/7 duty cycle).

    Deliberately generous: a long weekend or a holiday week must never read as a
    stale store, because the consequence of a false stale is a night that
    silently skips the ledger advance.
    """
    days = int((pd.Timestamp(b).normalize() - pd.Timestamp(a).normalize()).days)
    return int(days * 5 / 7)


def store_status(store: Path, sessions: pd.DatetimeIndex | None = None, *,
                 today: pd.Timestamp | None = None,
                 stale_sessions: int = 10) -> dict:
    """Health read on the bar store, for the nightly's refuse-to-run gate.

    Two independent staleness measures, because they catch different failures:

    * manifest ``latest_date`` vs ``today`` — the COLLECTOR stopped (cheap; runs
      before the 45-60s panel build, so a dead store costs seconds not minutes).
    * panel newest session vs manifest ``latest_date`` — this checkout's copy of
      the store lags its canonical R2 home (§4.0), so the panel is older than the
      manifest claims.

    Either one over ``stale_sessions`` sets ``stale``; the caller then warns and
    exits WITHOUT touching artifacts, so a stale run can never overwrite a good
    ledger with a short one.
    """
    store = Path(store)
    out: dict = {"present": False, "n_files": 0, "last_session": None,
                 "manifest_latest": None, "stale": False,
                 "sessions_behind_manifest": None, "sessions_behind_today": None,
                 "reason": None}
    if not store.exists():
        out["reason"] = "store directory absent"
        return out
    files = list(store.glob("*.parquet"))
    out["n_files"] = len(files)
    out["present"] = bool(files)
    if not files:
        out["reason"] = "store directory holds no parquet files"
        return out
    if sessions is not None and len(sessions):
        out["last_session"] = str(pd.Timestamp(sessions[-1]).date())
    manifest = store / "_manifest.json"
    latest = None
    if manifest.exists():
        try:
            import json

            raw = json.loads(manifest.read_text(encoding="utf-8")) or {}
            # The collector writes `latest_date`; `coverage.last_day` is its twin.
            # Read both — a manifest whose key we cannot find must not read as
            # "fresh", which is what silently missing the key would do.
            latest = (raw.get("latest_date")
                      or (raw.get("coverage") or {}).get("last_day"))
        except Exception:  # noqa: BLE001 — a torn manifest is not a reason to fail
            latest = None
    if latest:
        out["manifest_latest"] = str(latest)
        if today is not None:
            n = _sessions_between(pd.Timestamp(latest), pd.Timestamp(today))
            out["sessions_behind_today"] = n
            if n > stale_sessions:
                out["stale"] = True
                out["reason"] = (f"store manifest latest_date={latest} is ~{n} sessions "
                                 f"behind {pd.Timestamp(today).date()}")
        if sessions is not None and len(sessions):
            n = _sessions_between(pd.Timestamp(sessions[-1]), pd.Timestamp(latest))
            out["sessions_behind_manifest"] = n
            if n > stale_sessions:
                out["stale"] = True
                out["reason"] = (f"panel newest session {out['last_session']} is ~{n} "
                                 f"sessions behind the store manifest ({latest})")
    return out
