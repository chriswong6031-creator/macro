"""Precompute the AI stock-research briefs -> site/stockbrief/<TICKER>.json.

Standalone so the ~30 DeepSeek calls (the heaviest single step in the daily
build — ~20 min, which pushed the `engine` CI job past its timeout) run in
their OWN parallel job instead of on build_site's critical path. build_site
writes the bounded target set (action-board standouts + watchlist suggestions)
to data/catalyst/brief_targets.json; this reads it and generates the briefs.

The stock page fetches site/stockbrief/<T>.json client-side, so a <=1-run-old
brief set is fine and the LLM never gates the daily dashboard/deploy. Additive
and default-off: a no-op (exit 0) when catalyst_stock is disabled, the target
file is absent, or anything fails. See engine/catalyst_stock.py.

Usage: python -m scripts.build_stock_briefs
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_stock_briefs")


def _targets() -> list[str]:
    """The ticker set build_site recorded; fall back to the watchlist suggestions
    so the job still does something useful if the target file is missing."""
    p = config.data_dir() / "catalyst" / "brief_targets.json"
    if p.exists():
        try:
            t = json.loads(p.read_text())
            if isinstance(t, list) and t:
                return [str(x) for x in t]
        except Exception as e:  # noqa: BLE001
            log.warning("brief_targets.json unreadable (%s) — falling back to watchlist", e)
    return list(config.load().get("watchlist", {}).get("suggested", []))


def main() -> int:
    try:
        from engine import catalyst_stock
        if not catalyst_stock.enabled():
            log.info("catalyst_stock disabled — skipping (additive)")
            return 0
        targets = _targets()
        if not targets:
            log.info("no brief targets — skipping")
            return 0
        briefs = catalyst_stock.precompute_briefs(targets, root=config.ROOT)
        ok = sum(1 for b in briefs if not b.get("degraded_reason"))
        log.info("precomputed %d AI stock brief(s) (%d usable, %d degraded)",
                 len(briefs), ok, len(briefs) - ok)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("stock-brief precompute failed: %s", e)

    # Accountable AI JUDGMENT layer on the top picks (engine.stock_desk; T9) — one extra
    # DeepSeek call that turns the standout board into FALSIFIABLE, scored leans + a track
    # record. Runs here (the parallel LLM job, after build_site wrote the fresh
    # us_standouts.json) so it never gates the deploy. Gated by stock_desk.enabled() +
    # its own interval; always grades the past-due ledger. Additive, never fatal.
    try:
        from engine import stock_desk
        if stock_desk.enabled():
            out = stock_desk.run(persist=True, root=config.ROOT)
            if out:
                log.info("stock_desk: %d accountable lean(s) on the top picks (%s)",
                         len(out.get("notes") or []), out.get("degraded") or "ok")
        else:
            log.info("stock_desk disabled — skipping (additive)")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("stock_desk run failed: %s", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
