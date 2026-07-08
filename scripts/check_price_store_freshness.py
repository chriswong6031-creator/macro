"""Price-store freshness gate — assert the committed US price store holds the latest
completed NYSE session before the regime engine runs.

WHY (2026-07-07 stale-regime incident, nightly run 28845154707): the collect job fetched
Monday 07-06 bars, but its non-fatal commit step died 5x on the pre-#1823 "cannot pull
with rebase: You have unstaged changes" bug and went GREEN with only a ::warning::. The
engine job (needs: collect, fresh checkout) then read a store frozen at 07-02, computed a
faithful-but-stale RISK_OFF/40 and persisted it as the canonical
data/market_state/latest.json; the live feed carried that backbone (nightly_asof
2026-07-02) while a recompute on real 07-06 data said MIXED/56. The intraday self-heal's
store-behind-market check (scripts/refresh_regime_if_stale.py mode 3) was blind: its
market reference (the massive manifest) froze in the SAME dead push, so every committed
store agreed on the stale date. Only the exchange calendar knows a session is missing —
this gate is that calendar assertion, at the top of the engine lane.

WHAT: compare the store's last SPY daily close (data/yahoo/SPY.parquet) with
lib.nyse_calendar.expected_last_session(). Behind + --heal => re-pull the yahoo price
group (keyless, ~16s; lib.store.upsert folds the bars into the store, and the engine
job's "commit engine outputs" `git add data/` carries them to main — self-healing the
dead-push case without waiting for a human re-dispatch). Behind and unhealed => exit 3
with a ::error:: annotation. The workflow step wraps this in continue-on-error, so the
dashboard still builds from cached data (the engine job's if:always() philosophy) — but
the step shows RED, and engine.market_state.persist() independently stamps the canonical
snapshot `freshness.stale` so the staleness is self-declaring downstream.

A marker JSON (data/quality/price_store_freshness.json) records every evaluation.

Exit codes: 0 fresh/healed, 3 stale (annotated), 2 unexpected error.
`--selftest` runs synthetic assertions (calendar pins + decision logic) and exits 0/1.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from lib import config, nyse_calendar

log = logging.getLogger("price_store_freshness")


def evaluate(store_date: str | None, expected: str) -> str:
    """Pure decision: ISO date strings compare lexicographically."""
    if not store_date:
        return "no_store"
    return "fresh" if store_date >= expected else "stale"


def _write_marker(payload: dict) -> None:
    try:
        p = config.data_dir() / "quality" / "price_store_freshness.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2))
    except Exception as e:  # noqa: BLE001 — the marker is advisory, never the gate
        log.warning("freshness marker write failed: %s", e)


def run(heal: bool, now: datetime | None = None) -> int:
    # Same store readers as the intraday self-heal lane, so the two freshness layers
    # can never disagree about what "the store's last close" means.
    from scripts.refresh_regime_if_stale import _repull_yahoo, _store_close_date

    expected = str(nyse_calendar.expected_last_session(now))
    store_before = _store_close_date()
    status = evaluate(store_before, expected)
    store_after = store_before
    healed = False

    if status in ("stale", "no_store") and heal:
        log.info("store %s behind expected session %s — re-pulling yahoo (keyless)",
                 store_before, expected)
        try:
            store_after = _repull_yahoo()
            healed = evaluate(store_after, expected) == "fresh"
        except Exception as e:  # noqa: BLE001 — a heal failure is just an unhealed stale
            log.error("yahoo re-pull failed: %s", e)
    final = evaluate(store_after, expected)

    _write_marker({
        "checked_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "expected_session": expected,
        "store_before": store_before,
        "store_after": store_after,
        "status": final,
        "healed": healed,
        "heal_attempted": bool(heal and status != "fresh"),
    })

    if final == "fresh":
        print(f"price store fresh: last SPY close {store_after} >= expected session {expected}"
              + (" (healed by keyless yahoo re-pull)" if healed else ""))
        return 0
    print(f"::error title=price store STALE::last SPY close {store_after or 'ABSENT'} < expected "
          f"NYSE session {expected} — the nightly collection likely failed to land on main "
          f"(2026-07-07 incident class); regime/market_state this run are computed from stale "
          f"bars and are stamped freshness.stale by engine.market_state.persist")
    return 3


def selftest() -> int:
    from datetime import date
    cal = nyse_calendar
    checks = [
        # 2026 pins: July-4 observed Fri 07-03; Mon 07-06 is a session (the incident day).
        (not cal.is_session(date(2026, 7, 3)), "2026-07-03 must be the observed July-4 holiday"),
        (cal.is_session(date(2026, 7, 6)), "2026-07-06 (Mon) must be a session"),
        (not cal.is_session(date(2026, 7, 4)), "Saturday is never a session"),
        (not cal.is_session(date(2026, 4, 3)), "2026-04-03 must be Good Friday"),
        (not cal.is_session(date(2026, 6, 19)), "2026-06-19 (Fri) must be Juneteenth"),
        (not cal.is_session(date(2022, 6, 20)), "2022-06-20 must be observed Juneteenth (Sun->Mon)"),
        (cal.is_session(date(2021, 12, 31)), "2021-12-31 trades: Sat New Year is NOT observed early"),
        (not cal.is_session(date(2025, 1, 9)), "2025-01-09 one-off mourning closure"),
        # Incident replay: at 06:01 UTC on Tue 07-07 the expected session is Mon 07-06 …
        (str(cal.expected_last_session(datetime(2026, 7, 7, 6, 1, tzinfo=timezone.utc)))
         == "2026-07-06", "expected session at incident time must be 2026-07-06"),
        # … and mid-afternoon Monday (before close+settle) it is still Thu 07-02.
        (str(cal.expected_last_session(datetime(2026, 7, 6, 19, 0, tzinfo=timezone.utc)))
         == "2026-07-02", "pre-close Monday must expect the pre-holiday-weekend session"),
        (evaluate("2026-07-02", "2026-07-06") == "stale", "stale decision"),
        (evaluate("2026-07-06", "2026-07-06") == "fresh", "fresh decision"),
        (evaluate(None, "2026-07-06") == "no_store", "no_store decision"),
    ]
    failed = [msg for ok, msg in checks if not ok]
    for msg in failed:
        print(f"SELFTEST FAIL: {msg}")
    print(f"selftest: {len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--heal", action="store_true",
                    help="on staleness, re-pull the yahoo price group (keyless) before judging")
    ap.add_argument("--now", default=None,
                    help="ISO timestamp override for the freshness reference (tests)")
    ap.add_argument("--selftest", action="store_true", help="run synthetic assertions and exit")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        now = datetime.fromisoformat(args.now) if args.now else None
        return run(heal=args.heal, now=now)
    except Exception as e:  # noqa: BLE001 — an unexpected crash must still be VISIBLE (exit 2)
        log.error("price-store freshness gate crashed: %s", e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
