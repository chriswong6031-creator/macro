"""scripts/shadow_importance_v0.py — the novelty-first challenger's SHADOW lane
(W3, spec D6 / §3 ladder state SHADOW).

Scores every qbus item with engine.importance_v0, splits each lane (US / CN) into
a HIGH band (top scores) and a LOW band (bottom scores), and registers
salience-only qledger claims (direction=0) for both bands so the nightly grader
prices their forward |excess| the SAME way it prices the hand-formula bands and
the placebo tape. The three tapes are then DIRECTLY comparable on one scoreboard:

    hand china_news HIGH/LOW  (champion)   vs
    us_/cn_importance_v0 HIGH/LOW (challenger, this file)  vs
    placebo entity |excess|   (the null)

CONTRACT (mirrors backfill_qledger_cn.py + sample_qledger_placebo.py exactly so
the slices line up):
  * desk / claim_family = "us_importance_v0" | "cn_importance_v0" per lane.
  * scope = entity, per COVERED ticker on the item (a ticker with local price
    data). Items whose primary subject is a theme, or an entity with no price
    coverage, produce no claim — the challenger only makes claims it can grade,
    exactly like the CN backfill's covered-ticker rule.
  * direction = 0  (salience-only — §2.3 / D5: importance measures MAGNITUDE, it
    does not predict a sign; the placebo tape is the magnitude null it must beat).
  * horizon_d = 5 then 21 (two claims per pair) so slices compare at both clocks.
  * bench = "SPY" (US) | "510300.SS" (CN), the same benches the other tapes use.
  * timestamp_quality = CRAWL_BOUNDED (qbus seendate is the crawl anchor).
  * extra.band = "HIGH" | "LOW"  (mirrors the hand formula's importance_band
    tagging so the scoreboard answers "does the v0 High band move more than Low,
    and more than placebo?" per-slice).
  * is_placebo = False (this IS a real challenger tape, NOT the null).

NEVER RENDERED — shadow lane only. No page reads these claims; they exist purely
to accrue graded |excess| for the duel report (scripts/report_importance_duel.py).

IDEMPOTENT: stable claim_ids salted on item_id+ticker+horizon+band+lane, so this
runs nightly (wired end-of-collect after qbus appends, BEFORE the grader) without
duplicating the ledger. Re-running over the same store is a no-op.

BACKFILL: run over the whole existing qbus store so the first grades land at the
next grader run rather than in weeks (task step 3).

Usage:
    python scripts/shadow_importance_v0.py [--dry-run] [--root PATH]
        [--band-frac 0.25] [--lane us|cn|all] [--json]

Called as an end-of-collect step from scripts/collect.py.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root is importable when run directly.
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine import importance_v0 as iv  # noqa: E402
from engine import qbus  # noqa: E402
from engine.qledger import make_claim, register  # noqa: E402

log = logging.getLogger("shadow_importance_v0")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_HORIZONS = (5, 21)
_LANE_BENCH = {"us": "SPY", "cn": "510300.SS"}
_LANE_FAMILY = {"us": "us_importance_v0", "cn": "cn_importance_v0"}
# Fraction of each lane taken as the HIGH band (top) and the LOW band (bottom).
# A quarter/quarter split (like a High/Low quantile contrast) gives two clean,
# comparably-sized bands; the middle half is left unscored (it is neither a
# confident HIGH nor a confident LOW — registering it would only add noise).
_BAND_FRAC_DEFAULT = 0.25


# --------------------------------------------------------------------------- #
# price coverage — reuse the SAME checks the backfill / placebo samplers use so
# the challenger scopes exactly the tickers the other tapes can grade.
# --------------------------------------------------------------------------- #
def _has_price_us(ticker: str, root: Path) -> bool:
    if (root / "data" / "yahoo" / f"{ticker}.parquet").exists():
        return True
    try:
        from engine.ai_desk import _close_series  # deferred: heavy import
        s = _close_series(ticker, root)
        return s is not None and not s.empty
    except Exception:  # noqa: BLE001
        return False


def _has_price_cn(ticker: str, root: Path) -> bool:
    return (root / "data" / "china_stocks" / f"{ticker}.parquet").exists()


def _covered_tickers(item: dict, lane: str, root: Path) -> list[str]:
    """The item's entities that have local price coverage in the lane. Themes are
    NOT priceable subjects, so only the entities field is consulted (the primary
    subject may be a theme, but a claim can only be scoped to a priceable ticker)."""
    ents = qbus._split(item.get("entities"))
    check = _has_price_us if lane == "us" else _has_price_cn
    seen: list[str] = []
    for t in ents:
        if t and t not in seen and check(t, root):
            seen.append(t)
    return seen


# --------------------------------------------------------------------------- #
# band split — HIGH = top band_frac by score, LOW = bottom band_frac
# --------------------------------------------------------------------------- #
def _assign_bands(scored: list[dict], band_frac: float) -> dict[str, str]:
    """Map item_id -> 'HIGH' | 'LOW' for the top / bottom `band_frac` of scores in
    this (already lane-filtered) list. Ties at the cut are resolved by the stable
    (score, item_id) sort so band assignment is deterministic across re-runs.
    Items in the middle band get no entry (not scored). PURE."""
    if not scored:
        return {}
    ordered = sorted(scored, key=lambda r: (r["importance_v0"], r["item_id"]))
    n = len(ordered)
    k = max(1, int(round(n * band_frac)))
    k = min(k, n // 2 if n >= 2 else n)  # never let HIGH and LOW overlap
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
                    direction=0,               # salience-only (§2.3 / D5)
                    horizon_d=horizon_d,
                    timestamp_quality="CRAWL_BOUNDED",
                    bench=bench,
                    control=None,
                    is_placebo=False,          # a real challenger tape, not the null
                    claim_family=family,
                    extra={
                        "band": band,          # HIGH | LOW — mirrors hand-formula bands
                        "importance_v0": score,
                        "item_id": item_id,
                        "event_key": comp.get("event_key"),
                        "novelty_z": comp.get("novelty_z"),
                        "crowding_penalty": comp.get("crowding_penalty"),
                        "v0_version": iv.VERSION,
                    },
                )
                # stable, idempotent id across nightly re-runs
                claim["salt"] = f"impv0:{lane}:{item_id}:{ticker}:{horizon_d}:{band}"

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
    """Score the qbus store, band-split each lane, register HIGH/LOW salience-only
    claims. Returns a per-lane counter dict. Idempotent; safe to re-run nightly."""
    raw = qbus.read_items()
    df = iv.clean_df(raw)
    if df is None or len(df) == 0:
        log.warning("qbus store empty or unreadable — nothing to score")
        return {"n_items": 0}

    counters: dict = {"n_items": int(len(df)), "band_frac": band_frac}
    lanes = ("us", "cn") if lane == "all" else (lane,)
    for ln in lanes:
        counters.setdefault(f"{ln}_scored", 0)
        counters.setdefault(f"{ln}_pairs", 0)
        counters.setdefault(f"{ln}_no_ticker", 0)
        counters.setdefault(f"{ln}_registered", 0)
        counters.setdefault(f"{ln}_rejected", 0)
        _register_lane(ln, df, root, band_frac, dry_run, counters)

    log.info("shadow_importance_v0 done — %s",
             {k: v for k, v in counters.items() if k != "band_frac"})
    return counters


# --------------------------------------------------------------------------- #
# end-of-collect hook — wired in scripts/collect.py AFTER qbus appends, BEFORE
# the grader, so the same-night grader picks up any freshly-registered claims.
# Non-fatal: a challenger crash must never abort the collection run.
# --------------------------------------------------------------------------- #
def run_as_collect_step(root: Path | str | None = None) -> None:
    try:
        from lib import config
        run(Path(root) if root else config.ROOT)
    except Exception as exc:  # noqa: BLE001
        log.error("[shadow_importance_v0] crashed (non-fatal): %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Score + band-split but do not write claims")
    parser.add_argument("--root", default=None,
                        help="Repo root (default: auto-detected)")
    parser.add_argument("--band-frac", type=float, default=_BAND_FRAC_DEFAULT,
                        help=f"HIGH/LOW band fraction per lane (default {_BAND_FRAC_DEFAULT})")
    parser.add_argument("--lane", default="all", choices=["us", "cn", "all"],
                        help="Which lane(s) to score (default: all)")
    parser.add_argument("--json", action="store_true",
                        help="Emit summary as JSON")
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
