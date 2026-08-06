"""Heal curated per-ticker caches that are shallow only because OUR collection started late.

PROPHET US roadmap §4.5, deliverable 2 — RE-MEASURED before building (2026-08-04).

WHAT THE BRIEF EXPECTED, AND WHAT THE CENSUS ACTUALLY FOUND
-----------------------------------------------------------
The commissioning brief named GOLD (23 bars), SPCX (35) and CDE (51) as names
with decades of real history whose caches were shallow because collection began
recently, and asked for a rate-limited multi-night API backfill.  Measured
against the tree today, that premise does **not** reproduce:

* **GOLD** — 3,113 bars in ``data/baskets/ohlcv`` back to 2014-03-17.  Not shallow.
* **CDE**  — not a member of any of the 47 curated baskets at all; the orphan
  file it does have carries 3,148 bars back to 2014-01-02.  Not shallow.
* **SPCX** — genuinely 34 bars, but it listed 2026-06-12 (``config.yml`` already
  annotates it "IPO 2026-06-12 — LIMITED card until it ages").  No backfill can
  invent history a company did not trade.

And the backfill mechanism the brief asked for **already exists and already runs
unconditionally**: ``scripts/fetch_basket_ohlcv.py`` hard-codes
``START = "2014-01-01"`` and is called every night by ``scripts/collect.py``, so
a newly-added basket member gets twelve years of history on its first night.
There is no rate-limited multi-night backfill to build, and building one would
have been a fix for a defect that is not there.

THE DEFECT THAT IS REAL
-----------------------
The brief's exhibit NUMBERS are exactly right; they point at a store the brief did
not name.  ``data/yahoo/GOLD.parquet`` carries precisely **23 bars** (from
2026-07-01) and ``data/yahoo/SPCX.parquet`` precisely **35** — the operator was
reading ``data/yahoo``, where the whole gold-miner cohort begins 2026-07-01:

    ticker   data/yahoo             data/baskets/ohlcv
    GOLD     23 bars (2026-07-01)   3,113 bars (2014-03-17)
    GFI      23 bars (2026-07-01)   3,163 bars (2014-01-02)
    HMY      23 bars (2026-07-01)   3,163 bars (2014-01-02)
    KGC      23 bars (2026-07-01)   3,163 bars (2014-01-02)
    NEM/EGO/EQX — same shape

All are below ``confluence_tiers.MIN_HISTORY`` (200), so every tier verdict for
them is a structural null — the exact symptom the brief describes.

**The cause is a missing FALLBACK, not missing data.**
``build_stock_library.universe()`` serves ETFs, commodities and the curated
searchable extras from ``data/yahoo`` and never falls back to
``data/baskets/ohlcv``, so a name is gated on last month's history while twelve
years of the same ticker sit one directory over.

(Measured on the REF, not on the shared primary checkout.  An earlier pass read
the occupied checkout's working tree and saw four shallow ``data/stocks`` names
there — CBRE/ISRG/MLM/KMI — which are 5,570-8,166 bars deep on ``origin/main``.
That reading was an artifact of a mid-collection working tree; ``data/stocks`` has
no shallow names on the ref, which is why it heals nothing and is kept in
``TARGET_DIRS`` only as a guard against the defect recurring there.)

WHAT THIS SCRIPT DOES
---------------------
Splices the deeper history that is **already on local disk** into the shallow
cache.  No API call, no key, no rate limit, no multi-night horizon — the donor
bytes are already there, so the whole heal is one pass measured in seconds.

Donor priority: ``data/baskets/ohlcv`` (deepest, 2014+), then
``data/massive_stock_day`` (2021+, only when restored in this lane).

SAFETY — the three rules that make this non-destructive
  1. **PREPEND ONLY.**  Rows are added strictly BEFORE the target's own first
     date.  The existing rows are the fresher, authoritative tail and are never
     touched, so this cannot overwrite good data with donor data (the
     no-overwrite-gate law: a reader fix must not reach behind rows a consumer
     already trusts).
  2. **The target's column set is preserved exactly.**  Donors carry extra
     columns (``open``, ``transactions``); adding them would silently change a
     schema other readers parse.  Donor columns the target lacks are dropped;
     target columns the donor lacks make the donor unusable for that ticker.
  3. **Idempotent by construction.**  A healed file is at or above the depth
     floor, so the next run skips it.  Re-running changes nothing.

Nightly-gated like every other store writer: ``--nightly`` is required to write.
A default invocation measures and prints and writes nothing.

Run (nightly / DAG):   python -m scripts.heal_shallow_caches --nightly
Run (dry, no writes):  python -m scripts.heal_shallow_caches
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.confluence_tiers import MIN_HISTORY  # noqa: E402

log = logging.getLogger("heal_shallow_caches")

#: The caches we heal, in the order ``build_stock_library.universe()`` consults
#: them.  ``data/yahoo`` is where the defect actually lives: ``universe()`` serves
#: ETFs, commodities and the curated searchable extras from it, and it does NOT
#: fall back to ``data/baskets/ohlcv`` — so a name whose yahoo file starts last
#: month is gated on last month's history even though twelve years of the SAME
#: ticker sit one directory over.
TARGET_DIRS = ("data/stocks", "data/yahoo")

#: Donors, deepest first.  Both are local reads — no API, no key, no rate limit.
DONOR_DIRS = ("data/baskets/ohlcv", "data/massive_stock_day")

#: Donor columns that may STAND IN for a target column the donor lacks.
#: ``data/yahoo`` carries ``close_price`` alongside ``close``; the two are
#: byte-identical in every file checked (verified on the ref, not assumed), so a
#: donor's ``close`` fills both without inventing a value.  Any target column with
#: no donor source still disqualifies the donor — rule 2 is intact.
COLUMN_ALIASES = {"close_price": "close"}

#: Files whose stem starts with this are index/macro series (``_GSPC``, ``_VIX``),
#: not tickers — they have no per-ticker donor and are not part of the universe.
SIDECAR_PREFIX = "_"

#: Below this a name cannot produce a tier verdict at all
#: (``confluence_tiers.MIN_HISTORY``) — imported, never redefined here.
DEPTH_FLOOR = MIN_HISTORY


def shallow_targets(root: Path, floor: int = DEPTH_FLOOR) -> list[tuple[str, str, int]]:
    """``(target_dir, ticker, bars)`` for every target cache below the depth floor."""
    out: list[tuple[str, str, int]] = []
    for target_dir in TARGET_DIRS:
        d = root / target_dir
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.parquet")):
            if p.stem.startswith(SIDECAR_PREFIX):
                continue
            try:
                frame = pd.read_parquet(p, columns=["close"])
            except Exception:  # noqa: BLE001 — an unreadable cache is a separate problem
                continue
            bars = int(frame["close"].notna().sum())
            if bars < floor:
                out.append((target_dir, p.stem, bars))
    return out


def _read_donor(root: Path, donor: str, ticker: str) -> pd.DataFrame | None:
    p = root / donor / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        frame = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if frame.empty:
        return None
    if not isinstance(frame.index, pd.DatetimeIndex):
        try:
            frame.index = pd.to_datetime(frame.index)
        except Exception:  # noqa: BLE001
            return None
    return frame.sort_index()


def plan_heal(root: Path, ticker: str, target_dir: str = "data/stocks") -> dict | None:
    """What healing this ticker WOULD do.  Pure read — writes nothing.

    Returns None when no donor can help (no deeper local history, or no donor
    that can source every column the target already has, aliases included).
    """
    target_path = root / target_dir / f"{ticker}.parquet"
    try:
        target = pd.read_parquet(target_path)
    except Exception:  # noqa: BLE001
        return None
    if target.empty:
        return None
    if not isinstance(target.index, pd.DatetimeIndex):
        try:
            target.index = pd.to_datetime(target.index)
        except Exception:  # noqa: BLE001
            return None
    target = target.sort_index()
    first = target.index[0]

    for donor_dir in DONOR_DIRS:
        donor = _read_donor(root, donor_dir, ticker)
        if donor is None:
            continue
        # Rule 2: every target column must have a donor source, directly or
        # through an explicit alias. A donor that cannot fill one would leave NaN
        # holes in a schema downstream readers parse as complete.
        source_for: dict[str, str] = {}
        for column in target.columns:
            if column in donor.columns:
                source_for[column] = column
            elif COLUMN_ALIASES.get(column) in donor.columns:
                source_for[column] = COLUMN_ALIASES[column]
        missing = [c for c in target.columns if c not in source_for]
        if missing:
            log.debug("%s: donor %s cannot source %s — skipped", ticker, donor_dir, missing)
            continue
        earlier = donor.loc[donor.index < first]
        if earlier.empty:
            continue
        head = pd.DataFrame(
            {column: earlier[src] for column, src in source_for.items()},
            index=earlier.index,
        )[list(target.columns)]
        return {
            "ticker": ticker,
            "target_dir": target_dir,
            "donor": donor_dir,
            "target_bars": int(len(target)),
            "prepend_bars": int(len(head)),
            "result_bars": int(len(head) + len(target)),
            "target_first": str(first)[:10],
            "donor_first": str(head.index[0])[:10],
            "_head": head,
            "_target": target,
            "_path": target_path,
        }
    return None


def apply_heal(plan: dict) -> int:
    """Write the spliced frame.  Returns the resulting row count.

    The concat is donor-head THEN target, so every existing row survives byte
    for byte and only genuinely earlier dates are added.  The index name is
    carried over — several readers key on it.
    """
    head, target, path = plan["_head"], plan["_target"], plan["_path"]
    merged = pd.concat([head, target])
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    merged.index.name = target.index.name
    tmp = path.with_suffix(".tmp.parquet")
    merged.to_parquet(tmp)
    tmp.replace(path)
    return int(len(merged))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Heal shallow curated per-ticker caches")
    ap.add_argument("--nightly", action="store_true",
                    help="actually write (the sole advancer; without it this is a dry run)")
    ap.add_argument("--floor", type=int, default=DEPTH_FLOOR,
                    help=f"depth floor in bars (default {DEPTH_FLOOR} = confluence MIN_HISTORY)")
    args = ap.parse_args()

    targets = shallow_targets(ROOT, args.floor)
    print(f"[heal-shallow-caches] {', '.join(TARGET_DIRS)}: "
          f"{len(targets)} cache(s) below {args.floor} bars")
    if not targets:
        print("  nothing to heal")
        return 0

    healed = skipped = 0
    for target_dir, ticker, bars in targets:
        plan = plan_heal(ROOT, ticker, target_dir)
        if plan is None:
            # A name with no deeper local history is NOT a defect — it is a young
            # listing. Say which, so an unhealable row never reads as a failure.
            print(f"  {ticker:<8} {bars:>4} bars in {target_dir:<12} — no deeper local "
                  "donor (young listing, or donor cannot source a column)")
            skipped += 1
            continue
        print(f"  {ticker:<8} {bars:>4} bars in {target_dir:<12} -> {plan['result_bars']:>5} "
              f"(+{plan['prepend_bars']} from {plan['donor']}, back to {plan['donor_first']})")
        if args.nightly:
            rows = apply_heal(plan)
            healed += 1
            log.info("healed %s/%s: %d rows", target_dir, ticker, rows)

    if args.nightly:
        print(f"  WROTE {healed} cache(s); {skipped} unhealable (young listings)")
    else:
        print(f"  DRY RUN — no writes ({len(targets) - skipped} would be healed, "
              f"{skipped} unhealable). Re-run with --nightly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
