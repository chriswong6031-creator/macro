"""Regime freshness self-heal -> re-stamp data/regime/latest.json when the price store
has advanced past the regime's as-of.

WHY (the observed bug): the nightly regime engine (engine.run) can run BEFORE the latest
daily close lands in the store. Three real failure modes seen in the git history:
  1. A separate/late "daily collection" commit adds today's SPY bar MINUTES after the last
     regime recompute (e.g. 2026-07-01: engine-render at 23:29 UTC saw only the 06-30 bar;
     the 07-01 bar landed at 23:34 UTC in a later collection commit — the regime never saw it).
  2. The heavy nightly build hits its timeout and is CANCELLED before the engine-outputs
     commit (see daily.yml:153), so the price data lands but the regime never re-stamps.
  3. STORE-BEHIND-MARKET: the nightly US collect commit itself races or fails (daily.yml's
     data push is non-fatal after 5 rebase attempts), so the yahoo/SPY store FREEZES a session
     behind the market — while a different store (massive) already holds the close. Modes 1-2 are
     "engine behind store"; this one is "store behind market", which the store-vs-engine check
     alone can NEVER see (both agree on the stale date). Fix: when the massive reference has
     advanced past yahoo/SPY, re-pull yahoo (keyless) before re-running the engine. (The 2026-07-03
     July-4-holiday incident: US yahoo froze at 07-01, regime stuck at 07-01, massive already 07-02.)

In all three cases data/regime/latest.json — which BOTH the macro.html "Current Macro Regime"
badge AND the Market State board read their as-of date from — is left behind the latest session,
so the dashboard shows a stale date (the "still showing 2026-06-30" report).

This is the FAST, cancellation-proof catch-up. It runs in the intraday fast-path (every
~30 min during RTH, plus a pre-open tick). When the store's last SPY close is newer than
latest.json's date — OR the store itself is behind the massive market reference (mode 3, healed
by a keyless yahoo re-pull) — it re-runs the regime engine (~25s, offline-safe — every leaf is
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


def _market_reference_date() -> str | None:
    """The last session the price store SHOULD reflect — the max of two references:
    (a) the massive US whole-market store's manifest (keyless, already on disk, advanced by
        its own collector), and
    (b) the NYSE-calendar expected last completed session (lib.nyse_calendar — pure rule
        arithmetic, no data dependency).
    (a) alone went blind in the 2026-07-07 incident: the WHOLE nightly collection push died
    (pre-#1823 unstaged-changes rebase bug), so massive froze on the same stale date as
    yahoo/SPY and the store-behind-market check saw agreement — while the calendar knew the
    07-06 session was missing. Best-effort: each leg degrades independently; both absent ->
    None (the store re-pull is simply skipped and behaviour is exactly as before)."""
    refs: list[str] = []
    try:
        m = json.loads((config.data_dir() / "massive_stock_day" / "_manifest.json").read_text())
        d = m.get("latest_date")
        if d:
            refs.append(str(d))
    except Exception:  # noqa: BLE001 — reference is advisory; never let it break the self-heal
        pass
    try:
        from lib import nyse_calendar
        refs.append(str(nyse_calendar.expected_last_session()))
    except Exception:  # noqa: BLE001 — calendar leg is advisory too
        pass
    return max(refs) if refs else None


def _repull_yahoo() -> str | None:
    """Re-collect the yahoo price group so the store catches the latest close before the regime
    re-runs. KEYLESS (period=1mo, ~16s) so the fast-path stays secret-free; run_adapter upserts
    every fetched series back into the store. Returns the refreshed SPY store date. The caller
    wraps this so a network hiccup can never fail the fast-path."""
    from collectors.base import run_adapter
    from collectors.yahoo import YahooAdapter
    res = run_adapter(YahooAdapter())
    log.info("yahoo re-pull -> %s (%s rows, last %s)", res.status, res.rows, res.last_date)
    return _store_close_date()


def refresh(force: bool = False) -> dict:
    store_date = _store_close_date()
    regime_date = _regime_asof()
    # STORE-BEHIND-MARKET self-heal (the 2026-07-03 holiday incident): the regime-vs-store check
    # below only catches the ENGINE lagging the STORE. But when a nightly US collect commit races
    # or fails (daily.yml documents both modes — the non-fatal 5x push-retry AND the timeout cancel
    # before the data commit), the yahoo/SPY store itself freezes a session behind the market while
    # a DIFFERENT store (massive) already holds the close, and every regime recompute faithfully
    # re-stamps the stale date with nothing to catch it. When the massive reference has advanced
    # past yahoo/SPY, re-pull yahoo (keyless, non-fatal) so the regime re-run below sees the latest
    # close. Guarded on regime<market too: a PRIOR fast-path run may have already advanced the
    # regime past a still-frozen COMMITTED store (its re-pull is ephemeral — the fast-path commits
    # regime, not the yahoo store), so skip the re-fetch when there is nothing left to heal.
    # Threaded into the return so the fast-path log surfaces heal / could-not-heal.
    repull = None
    market_date = _market_reference_date()
    if (store_date is not None and market_date is not None and store_date < market_date
            and (force or regime_date is None or regime_date < market_date)):
        log.info("yahoo/SPY store (%s) BEHIND market (%s) — re-pulling yahoo", store_date, market_date)
        try:
            new_date = _repull_yahoo()
            healed = bool(new_date and new_date > store_date)
            repull = {"prev": store_date, "new": new_date, "market": market_date, "healed": healed}
            if healed:
                store_date = new_date
            else:
                log.warning("STORE STILL BEHIND MARKET after yahoo re-pull (store=%s market=%s) — "
                            "upstream feed has not published the close yet", new_date, market_date)
        except Exception as e:  # noqa: BLE001 — the fast-path must never fail on the self-heal
            log.error("yahoo re-pull failed (non-fatal): %s", e)
            repull = {"prev": store_date, "market": market_date, "error": str(e)}

    if store_date is None:
        log.warning("no SPY close in store — nothing to do")
        return {"status": "no_store", "asof": regime_date, "repull": repull}
    # ISO date strings compare lexicographically -> "2026-07-01" > "2026-06-30".
    if not force and regime_date is not None and regime_date >= store_date:
        log.info("regime fresh (asof=%s, store=%s) — no refresh", regime_date, store_date)
        return {"status": "fresh", "asof": regime_date, "store": store_date, "repull": repull}

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
    result = {"status": "refreshed", "asof": new, "prev": regime_date,
              "store": store_date, "quad": latest.get("quad_name"), "repull": repull}

    # W6a MIRROR: record this self-heal firing to the reflex firings ledger.
    # Single-writer law: ONLY the intraday-fastpath lane calls this.
    # The append is additive — existing behavior is unchanged.
    try:
        from datetime import datetime, timezone  # noqa: PLC0415
        from engine.neuralweb.reflexes import record_firing  # noqa: PLC0415
        record_firing("regime_stale_selfheal", {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trigger_type": "staleness_check",
            "trigger_key": f"regime:{regime_date}:store:{store_date}",
            "action_taken": "rerun_engine",
            "scope_type": "macro",
            "scope_key": "regime",
            "direction": 0,      # infrastructure; no directional bet
            "horizon_d": None,   # not gradeable
            "asof": new or store_date,
            "extra": {
                "prev_asof": regime_date,
                "new_asof": new,
                "store_date": store_date,
                "repull_healed": bool(repull and repull.get("healed")),
                "quad": latest.get("quad_name"),
            },
        })
    except Exception as e:  # noqa: BLE001 — firings append must never fail the fast-path
        log.warning("W6a record_firing skipped (non-fatal): %s", e)

    return result


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
