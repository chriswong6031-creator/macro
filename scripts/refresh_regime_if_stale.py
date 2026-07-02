"""Regime freshness self-heal -> re-stamp data/regime/latest.json when the price store
has advanced past the regime's as-of.

WHY (the observed bug): the nightly regime engine (engine.run) can run BEFORE the latest
daily close lands in the store. Two real failure modes seen in the git history:
  1. A separate/late "daily collection" commit adds today's SPY bar MINUTES after the last
     regime recompute (e.g. 2026-07-01: engine-render at 23:29 UTC saw only the 06-30 bar;
     the 07-01 bar landed at 23:34 UTC in a later collection commit — the regime never saw it).
  2. The heavy nightly build hits its timeout and is CANCELLED before the engine-outputs
     commit (see daily.yml:153), so the price data lands but the regime never re-stamps.

Either way data/regime/latest.json — which BOTH the macro.html "Current Macro Regime" badge
AND the Market State board read their as-of date from — is left one session behind the store,
so the dashboard shows a stale date (the "still showing 2026-06-30" report).

This is the FAST, cancellation-proof catch-up. It runs in the intraday fast-path (every
~30 min during RTH, plus a pre-open tick). When the store's last SPY close is newer than
latest.json's date it re-runs the regime engine (~25s, offline-safe — every leaf is
try/except wrapped) and re-persists the Market State snapshot. The fast-path then commits
ONLY those two small artifacts (data/regime/latest.json + data/market_state/latest.json);
the forward-grading logs engine.run also touches (regime_history.parquet, *_log.jsonl,
regime_one.json, base_effect_fwd.jsonl ...) are the NIGHTLY build's canonical once-per-session
writes and are deliberately NOT committed here, so intraday re-runs never pollute them.

Idempotent + non-fatal: exits 0 whether it refreshed, found the regime already fresh, or
hit an error (the fast-path must never fail because of the self-heal).
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config, store

log = logging.getLogger("refresh_regime")


def _store_close_date() -> str | None:
    """The last SPY daily close date in the price store (the session the regime should reflect)."""
    df = store.read("yahoo", "SPY")
    if df is None or "close" not in df.columns:
        return None
    s = df["close"].dropna()
    if s.empty:
        return None
    return str(pd.to_datetime(s.index).max().date())


def _regime_asof() -> str | None:
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("date")
    except Exception:  # noqa: BLE001
        return None


def refresh(force: bool = False) -> dict:
    store_date = _store_close_date()
    regime_date = _regime_asof()
    if store_date is None:
        log.warning("no SPY close in store — nothing to do")
        return {"status": "no_store", "asof": regime_date}
    # ISO date strings compare lexicographically -> "2026-07-01" > "2026-06-30".
    if not force and regime_date is not None and regime_date >= store_date:
        log.info("regime fresh (asof=%s, store=%s) — no refresh", regime_date, store_date)
        return {"status": "fresh", "asof": regime_date, "store": store_date}

    log.info("regime stale (asof=%s < store=%s) — re-running the regime engine",
             regime_date, store_date)
    from engine.run import run
    latest = run()  # re-stamps data/regime/latest.json to the newest available close
    # market_state persist is downstream of latest.json (normally written by build_site's render
    # lane). Refresh it too so build_risk_state's nightly baseline + the next render read the
    # freshened read. Additive: a failure here does not undo the regime re-stamp.
    try:
        from engine import market_state
        from engine.inputs import build_features
        f = build_features()
        snap = market_state.market_state_snapshot(latest, f, latest.get("alerts") or [])
        market_state.persist(snap)
    except Exception as e:  # noqa: BLE001
        log.error("market_state persist after refresh failed (non-fatal): %s", e)
    new = _regime_asof()
    log.info("regime refreshed -> asof=%s quad=%s", new, latest.get("quad_name"))
    return {"status": "refreshed", "asof": new, "prev": regime_date,
            "store": store_date, "quad": latest.get("quad_name")}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-run the engine even if latest.json is not behind the store")
    args = ap.parse_args()
    try:
        print(refresh(force=args.force))
    except Exception as e:  # noqa: BLE001 — never fail the fast-path on the self-heal
        log.error("refresh_regime_if_stale failed (non-fatal): %s", e)
        print({"status": "error", "error": str(e)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
