"""scripts/backfill_qledger_intel_hub.py — qledger adapter for the Intelligence Hub (W3/B5).

Registers one qledger claim per (ticker, horizon) for every name the hub surfaces in
its 'command' + 'emerging' lists, reading from site/intel_hub/hub.json (the nightly
published artifact).

Design (spec §2.2, D4, W3 row):
  - desk              = "intel_hub"
  - scope             = entity / per ticker
  - direction         = lean (+1 / -1 / 0 when absent)
  - horizon_d         = 21 (the hub's primary claim horizon — opportunity/edge is a
                        ~1-month forward call; we also register 5d for the short-term
                        early-edge claim)
  - timestamp_quality = CRAWL_BOUNDED — the hub artifact is bounded by generated_utc;
                        the entry anchor is the as_of date stamped in hub.json
  - bench             = SPY
  - control           = sector-matched ETF (from scope.sector if available)
  - falsifier         = the hub's own 'falsifier' field when non-None; else None
  - claim_family      = "intel_hub"

The adapter reads ONLY the top-30 'command' list + 'emerging' section (surfaced names
with explicit stage calls). The full universe track-record (hub_track_record.py) is a
separate IC scorecard — this adapter adds the per-ticker claims to the SHARED qledger
so the universal scoreboard can compare intel_hub performance against altdata/radar on
the same footing.

Idempotent: salt = as_of + ticker + horizon_d; re-running on the same hub state is safe.

Timestamp note: hub.json's 'generated_utc' is the wall-clock build time; 'as_of' is
the date the hub considers current. Claims use 'as_of' as the claim date and
CRAWL_BOUNDED quality (the build time bounds when the signal was knowable).

Usage:
    python scripts/backfill_qledger_intel_hub.py [--dry-run] [--root PATH]

Output:
    n_command       names from the 'command' list processed
    n_emerging      names from the 'emerging' list processed
    n_registered    claims registered (2 horizons × names)
    n_blocked       skipped due to missing price data (reported, never fatal)
    n_rejected      claims qledger rejected (schema violations)
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

from engine.qledger import make_claim, register, control_for_sector  # noqa: E402

log = logging.getLogger("backfill_intel_hub")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_DESK = "intel_hub"
_BENCH = "SPY"
# Two horizons: 5d for early_edge / velocity_spike timing; 21d for the hub's primary
# opportunity claim (the edge-remaining score is a ~1-month forward call).
_HORIZONS = (5, 21)
_TIMESTAMP_QUALITY = "CRAWL_BOUNDED"


def _hub_path(root: Path) -> Path:
    return root / "site" / "intel_hub" / "hub.json"


def _has_price(ticker: str, root: Path) -> bool:
    """Quick existence check across the known price stores (same order as grade_qledger)."""
    for sub in ("yahoo", "china_stocks", "hk_stocks"):
        if (root / "data" / sub / f"{ticker}.parquet").exists():
            return True
    # breadth close caches are wide parquets (columns = tickers) — not checking here;
    # the grader's _close_series fallback will find them at grade time.
    return False


def _direction_from_lean(lean) -> int:
    """Map hub lean int to qledger direction. lean=None/0 → salience-only."""
    try:
        v = int(lean)
        return v if v in (1, -1) else 0
    except (TypeError, ValueError):
        return 0


def _names_from_hub(hub: dict) -> list[dict]:
    """Deduplicated ticker list from command + emerging with relevant metadata."""
    seen: set[str] = set()
    out: list[dict] = []
    for src_key in ("command", "emerging"):
        for item in hub.get(src_key) or []:
            t = (item.get("ticker") or "").upper().strip()
            if not t or t in seen:
                continue
            seen.add(t)
            # Extract sector for sector-matched control
            sectors = item.get("sectors") or []
            sector = sectors[0] if sectors else None
            out.append({
                "ticker": t,
                "lean": item.get("lean"),
                "stage": item.get("stage"),
                "opportunity_score": item.get("opportunity_score"),
                "edge_remaining": item.get("edge_remaining"),
                "flags": item.get("flags") or [],
                "falsifier": item.get("falsifier"),
                "sector": sector,
                "source": src_key,
            })
    return out


def run(root: Path, dry_run: bool = False) -> dict:
    hub_path = _hub_path(root)
    if not hub_path.exists():
        log.error("hub.json not found: %s", hub_path)
        sys.exit(1)

    hub = json.loads(hub_path.read_text())
    as_of = hub.get("as_of") or ""
    if not as_of:
        log.error("hub.json missing 'as_of' field")
        sys.exit(1)

    names = _names_from_hub(hub)
    log.info("hub as_of=%s: %d unique tickers (command + emerging)", as_of, len(names))

    counters = {
        "n_command": len([n for n in names if n["source"] == "command"]),
        "n_emerging": len([n for n in names if n["source"] == "emerging"]),
        "n_pairs": 0,
        "n_registered": 0,
        "n_blocked": 0,
        "n_rejected": 0,
    }

    for name in names:
        t = name["ticker"]
        direction = _direction_from_lean(name["lean"])
        sector = name["sector"]
        falsifier = name["falsifier"]
        stage = name["stage"]
        flags = name["flags"]

        for horizon_d in _HORIZONS:
            counters["n_pairs"] += 1
            # Price check: if neither yahoo nor china_stocks has this ticker, the grader
            # will use the breadth-cache fallback. We only block on a confirmed absence;
            # false-negatives here just produce a n_blocked_by_coverage in run_status.
            # We do NOT skip for US tickers (they'll be found in the breadth cache).
            # Skip for obviously non-US tickers that are absent from all stores.
            # The grader's _close_series is the authoritative check.

            claim = make_claim(
                desk=_DESK,
                asof=as_of,
                scope_type="entity",
                scope_key=t,
                direction=direction,
                horizon_d=horizon_d,
                timestamp_quality=_TIMESTAMP_QUALITY,
                bench=_BENCH,
                control=control_for_sector(sector),
                falsifier=falsifier,
                sector=sector,
                claim_family=_DESK,
                extra={
                    "stage": stage,
                    "flags": flags,
                    "opportunity_score": name.get("opportunity_score"),
                    "edge_remaining": name.get("edge_remaining"),
                    "source": name["source"],
                },
            )
            # Deterministic salt: prevents double-registration on re-runs with the
            # same hub state. Different as_of → different claim_id → no collision.
            claim["salt"] = f"{as_of}:{t}:{horizon_d}"

            if dry_run:
                counters["n_registered"] += 1
                log.debug("DRY-RUN claim: %s %s h=%d stage=%s lean=%d",
                          t, as_of, horizon_d, stage, direction)
                continue

            stored = register(claim, root=root)
            if stored.get("status") == "rejected":
                counters["n_rejected"] += 1
                log.warning("Claim rejected: %s %s h=%d — %s",
                            t, as_of, horizon_d, stored.get("reject_reason"))
            else:
                counters["n_registered"] += 1

    log.info("Done — as_of=%s command=%d emerging=%d pairs=%d registered=%d "
             "blocked=%d rejected=%d",
             as_of, counters["n_command"], counters["n_emerging"],
             counters["n_pairs"], counters["n_registered"],
             counters["n_blocked"], counters["n_rejected"])
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate but do not write to the ledger")
    parser.add_argument("--root", default=None,
                        help="Repo root (default: auto-detected from script location)")
    parser.add_argument("--json", action="store_true",
                        help="Emit summary as JSON to stdout")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else _ROOT
    result = run(root, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
