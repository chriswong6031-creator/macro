"""scripts/shadow_importance_v0_pit.py — PIT-correct re-backfill for the
novelty-v0 challenger (W4, spec §4 W4 row, integrator debt items 1+2).

WHY THIS SCRIPT EXISTS
----------------------
The W3 `shadow_importance_v0.py` backfill contained two bugs that biased the
seeded importance_v0 scores:

  1. echo_stats look-ahead (integrator debt item 1): `qbus.echo_stats` had no
     `asof` filter, so any item that later accumulated corroborators AFTER its
     own seendate got credit for future cross-desk breadth (W_CORROBORATION=0.28
     weight).  A story from 2026-06-10 that attracted five desks by 2026-06-20
     would score as if all five desks were present on 2026-06-10.  This inflated
     the importance_v0 of old stories that eventually became big, biasing the HIGH
     band toward retrospectively-obvious picks rather than truly-novel ones.

  2. tz-mixed seendate NaT (integrator debt item 2): `qbus._subject_daily_counts`
     used tz-naive `pd.to_datetime(errors="coerce")` on the seendate column, which
     coerced tz-AWARE ISO 8601 strings (`2026-06-21T12:00:00+00:00`) to NaT.  The
     ~938-row CN lane is entirely tz-aware, so its novelty_z always returned None
     (neutral contribution 0.5), making every CN item effectively equivalent on the
     novelty axis and the HIGH/LOW bands meaningless for CN.

BOTH BUGS ARE NOW FIXED IN ENGINE CODE (W4):
  - `qbus._subject_daily_counts` now uses `utc=True` + `.map(ts.date())`.
  - `qbus.echo_stats` now accepts an `asof` parameter and filters to items seen
    on or before it.
  - `engine.importance_v0.score_components` passes its `asof` to `echo_stats`.

This script re-runs the backfill using the FIXED engine, registering claims under
the `_pit` families (`us_importance_v0_pit` / `cn_importance_v0_pit`) so the W3
and W4 tapes are independently comparable on the duel scoreboard.  The old
`us/cn_importance_v0` families are retained in the ledger as an audit artefact
(they show what look-ahead bias looked like).

CONTRACT (identical to shadow_importance_v0.py except family/salt):
  * desk / claim_family = "us_importance_v0_pit" | "cn_importance_v0_pit".
  * scope = entity, per covered ticker.
  * direction = 0  (salience-only, §2.3/D5).
  * horizon_d = 5 then 21.
  * bench = "SPY" (US) | "510300.SS" (CN).
  * timestamp_quality = CRAWL_BOUNDED.
  * extra.band = "HIGH" | "LOW".
  * extra.pit_corrected = True  (audit field — distinguishes these from W3 claims).
  * is_placebo = False.
  * salt prefix = "impv0pit:" (distinct from W3 "impv0:") so both tapes coexist
    in the ledger without collision.

IDEMPOTENT: re-running over the same qbus store is a no-op (same stable salt).

Usage:
    python scripts/shadow_importance_v0_pit.py [--dry-run] [--root PATH]
        [--band-frac 0.25] [--lane us|cn|all] [--json]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine import importance_v0 as iv  # noqa: E402
from engine import qbus  # noqa: E402
from engine.qledger import make_claim, register  # noqa: E402

log = logging.getLogger("shadow_importance_v0_pit")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_HORIZONS = (5, 21)
_LANE_BENCH = {"us": "SPY", "cn": "510300.SS"}
# _pit suffix distinguishes these from the W3 biased families.
_LANE_FAMILY = {"us": "us_importance_v0_pit", "cn": "cn_importance_v0_pit"}
_BAND_FRAC_DEFAULT = 0.25

# Salt prefix that DIFFERS from shadow_importance_v0.py ("impv0:") so both
# tapes can coexist in the same ledger without claim_id collision.
_SALT_PREFIX = "impv0pit"


# --------------------------------------------------------------------------- #
# price coverage — identical to shadow_importance_v0.py
# --------------------------------------------------------------------------- #
def _has_price_us(ticker: str, root: Path) -> bool:
    if (root / "data" / "yahoo" / f"{ticker}.parquet").exists():
        return True
    try:
        from engine.ai_desk import _close_series
        s = _close_series(ticker, root)
        return s is not None and not s.empty
    except Exception:  # noqa: BLE001
        return False


def _has_price_cn(ticker: str, root: Path) -> bool:
    return (root / "data" / "china_stocks" / f"{ticker}.parquet").exists()


def _covered_tickers(item: dict, lane: str, root: Path) -> list[str]:
    ents = qbus._split(item.get("entities"))
    check = _has_price_us if lane == "us" else _has_price_cn
    seen: list[str] = []
    for t in ents:
        if t and t not in seen and check(t, root):
            seen.append(t)
    return seen


# --------------------------------------------------------------------------- #
# band split — identical algorithm, public so tests can import it directly
# --------------------------------------------------------------------------- #
def _assign_bands(scored: list[dict], band_frac: float) -> dict[str, str]:
    """Map item_id -> 'HIGH' | 'LOW'.  Identical to shadow_importance_v0._assign_bands;
    duplicated here so this script has no import dependency on the W3 script."""
    if not scored:
        return {}
    ordered = sorted(scored, key=lambda r: (r["importance_v0"], r["item_id"]))
    n = len(ordered)
    k = max(1, int(round(n * band_frac)))
    k = min(k, n // 2 if n >= 2 else n)
    bands: dict[str, str] = {}
    for r in ordered[:k]:
        bands[r["item_id"]] = "LOW"
    for r in ordered[n - k:]:
        bands[r["item_id"]] = "HIGH"
    return bands


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def _register_lane(lane: str, df, root: Path, band_frac: float,
                   dry_run: bool, counters: dict) -> None:
    scored = iv.score_store(df=df, lane=lane)
    counters[f"{lane}_scored"] = len(scored)
    if not scored:
        return

    bands = _assign_bands(scored, band_frac)
    by_id = {r["item_id"]: r for r in scored}
    id_to_item = {str(r.get("item_id") or ""): r for r in df.to_dict("records")}

    bench = _LANE_BENCH[lane]
    family = _LANE_FAMILY[lane]

    for item_id, band in bands.items():
        comp = by_id.get(item_id)
        item = id_to_item.get(item_id)
        if comp is None or item is None:
            continue
        asof = comp["asof"]
        score = comp["importance_v0"]
        covered = _covered_tickers(item, lane, root)
        if not covered:
            counters[f"{lane}_no_ticker"] += 1
            continue

        for ticker in covered:
            counters[f"{lane}_pairs"] += 1
            for horizon_d in _HORIZONS:
                claim = make_claim(
                    desk=family,
                    asof=asof,
                    scope_type="entity",
                    scope_key=ticker,
                    direction=0,
                    horizon_d=horizon_d,
                    timestamp_quality="CRAWL_BOUNDED",
                    bench=bench,
                    control=None,
                    is_placebo=False,
                    claim_family=family,
                    extra={
                        "band": band,
                        "importance_v0": score,
                        "item_id": item_id,
                        "event_key": comp.get("event_key"),
                        "novelty_z": comp.get("novelty_z"),
                        "crowding_penalty": comp.get("crowding_penalty"),
                        "v0_version": iv.VERSION,
                        # audit field: confirms this claim was scored with the
                        # PIT-correct asof-filtered echo_stats path (W4 fix).
                        "pit_corrected": True,
                    },
                )
                # DISTINCT salt from W3 script so both tapes coexist.
                claim["salt"] = (
                    f"{_SALT_PREFIX}:{lane}:{item_id}:{ticker}:{horizon_d}:{band}"
                )

                if dry_run:
                    counters[f"{lane}_registered"] += 1
                    continue
                stored = register(claim, root=root)
                if stored.get("status") == "rejected":
                    counters[f"{lane}_rejected"] += 1
                    log.warning("claim rejected: %s %s h=%d — %s", ticker, asof,
                                horizon_d, stored.get("reject_reason"))
                else:
                    counters[f"{lane}_registered"] += 1


def run(root: Path, dry_run: bool = False, band_frac: float = _BAND_FRAC_DEFAULT,
        lane: str = "all") -> dict:
    """Score the qbus store with PIT-correct engine (W4 fixes applied), band-split
    each lane, register HIGH/LOW salience-only claims under the _pit families.
    Returns a per-lane counter dict.  Idempotent; safe to re-run nightly."""
    raw = qbus.read_items()
    df = iv.clean_df(raw)
    if df is None or len(df) == 0:
        log.warning("qbus store empty or unreadable — nothing to score")
        return {"n_items": 0}

    counters: dict = {"n_items": int(len(df)), "band_frac": band_frac,
                      "pit_corrected": True}
    lanes = ("us", "cn") if lane == "all" else (lane,)
    for ln in lanes:
        counters.setdefault(f"{ln}_scored", 0)
        counters.setdefault(f"{ln}_pairs", 0)
        counters.setdefault(f"{ln}_no_ticker", 0)
        counters.setdefault(f"{ln}_registered", 0)
        counters.setdefault(f"{ln}_rejected", 0)
        _register_lane(ln, df, root, band_frac, dry_run, counters)

    log.info("shadow_importance_v0_pit done — %s",
             {k: v for k, v in counters.items() if k != "band_frac"})
    return counters


# --------------------------------------------------------------------------- #
# end-of-collect hook — runs nightly ALONGSIDE shadow_importance_v0.py so both
# tapes accrue in parallel.  Non-fatal.
# --------------------------------------------------------------------------- #
def run_as_collect_step(root: Path | str | None = None) -> None:
    try:
        from lib import config
        run(Path(root) if root else config.ROOT)
    except Exception as exc:  # noqa: BLE001
        log.error("[shadow_importance_v0_pit] crashed (non-fatal): %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Score + band-split but do not write claims")
    parser.add_argument("--root", default=None,
                        help="Repo root (default: auto-detected)")
    parser.add_argument("--band-frac", type=float, default=_BAND_FRAC_DEFAULT,
                        help=f"HIGH/LOW band fraction (default {_BAND_FRAC_DEFAULT})")
    parser.add_argument("--lane", default="all", choices=["us", "cn", "all"],
                        help="Lane(s) to score (default: all)")
    parser.add_argument("--json", action="store_true", help="Emit summary as JSON")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else _ROOT
    result = run(root, dry_run=args.dry_run, band_frac=args.band_frac, lane=args.lane)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    # hard_exit: this one-shot reads parquet (qbus store) — a plain exit can
    # deadlock forever in pyarrow's C++ shutdown on macOS (#2196). Required now
    # that the collect_tail job runs this standalone via `python -m`.
    from lib.procutil import hard_exit
    try:
        main()
    except Exception:  # noqa: BLE001 — traceback then hard-exit; never hang the lane
        import traceback
        traceback.print_exc()
        hard_exit(1)
    hard_exit(0)
