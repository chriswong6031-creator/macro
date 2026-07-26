#!/usr/bin/env python3
"""scripts/marketing_requeue_stale_copy.py — rewrite queued outbox copy in place.

WHY THIS EXISTS
A copy fix that lands AFTER the nightly has already generated a day's outbox
does not reach the queue. The nightly writes items once; the publisher posts
whatever is sitting there. So on 2026-07-26 the flagship queue held eight
weekend_levels items that carried the FIXED chart cards (generated after #3551)
but the PRE-FIX headline (generated before #3585) — every one of them still
opened "$TICKER into the week". They were scheduled for later the same day and
would have gone out the moment the publisher was re-armed.

WHAT IT DOES
Regenerates the copy for a lane's still-queued items using the CURRENT code,
carries their existing media across, quarantines the stale rows and enqueues the
rewritten ones. Media is preserved rather than re-rendered on purpose: the cards
were rendered on the nightly runner and uploaded to R2, and a local re-render
without R2 credentials would produce a card with no public URL, which Buffer
cannot attach — the post would silently go out text-only.

Only items that are still decidable are touched. Anything posted, posting or
quarantined is terminal and left exactly as it is.

    # show what would change, touch nothing
    python3 -m scripts.marketing_requeue_stale_copy --as-of 2026-07-26

    # write the ledger
    python3 -m scripts.marketing_requeue_stale_copy --as-of 2026-07-26 --apply

The ledger rows this writes must be COMMITTED for the publisher to see them.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("requeue_stale_copy")

# Statuses a rewrite may not touch: the post is gone or deliberately killed.
_TERMINAL = frozenset({"posted", "posting", "quarantined", "failed"})


def _load_cfg(root: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load((root / "config" / "marketing.yml").read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.yml unreadable (%s) — LLM voice lane stays off", exc)
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True, help="content date to rewrite, YYYY-MM-DD")
    ap.add_argument("--lane", default="weekend_levels", help="provenance to rewrite")
    ap.add_argument("--account", default="flagship")
    ap.add_argument("--apply", action="store_true",
                    help="write the ledger (default is a dry run)")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(args.root)

    from engine.marketing import weekend_levels as wl  # noqa: PLC0415
    from engine.marketing.outbox import (  # noqa: PLC0415
        enqueue, fold_state, transition, effective_cap,
    )

    if args.lane != "weekend_levels":
        log.error("only the weekend_levels lane is supported (got %r)", args.lane)
        return 2

    state = fold_state(root)
    items, statuses = state["items"], state["status"]

    stale = [
        it for it in items.values()
        if it.get("as_of") == args.as_of
        and it.get("provenance") == args.lane
        and it.get("account") == args.account
        and str(statuses.get(it["id"], "queued")) not in _TERMINAL
    ]
    if not stale:
        log.info("nothing to rewrite for %s / %s", args.as_of, args.lane)
        return 0

    # Preserve ladder order so the rewritten items keep their slots.
    stale.sort(key=lambda it: str(it.get("scheduled_at") or ""))
    tickers = [str(it["source"].get("ticker") or "") for it in stale]
    schedule = [(it.get("slot"), it.get("scheduled_at") or "immediate") for it in stale]
    media_by_ticker = {
        str(it["source"].get("ticker") or ""): (it.get("media") or []) for it in stale
    }

    # Regenerate copy ONLY. with_media=False: the existing cards are already
    # rendered and hosted; re-rendering here would drop their public URL.
    fresh = wl.build_items(
        root, tickers=tickers, as_of=args.as_of, account=args.account,
        schedule=schedule, max_items=len(tickers), cfg=_load_cfg(root),
        with_media=False,
    )
    fresh_by_ticker = {str(i["source"].get("ticker") or ""): i for i in fresh}

    planned: list[tuple[dict, dict]] = []
    for old in stale:
        tk = str(old["source"].get("ticker") or "")
        new = fresh_by_ticker.get(tk)
        if new is None:
            log.warning("  %-6s no regenerated item (data gone?) — LEFT AS IS", tk)
            continue
        if new["text"] == old["text"]:
            log.info("  %-6s copy unchanged — leaving in place", tk)
            continue
        new["media"] = media_by_ticker.get(tk) or []
        if new["media"] and new["media"][0].get("media_url"):
            new.setdefault("source", {})["media_url"] = new["media"][0]["media_url"]
        planned.append((old, new))

    if not planned:
        log.info("every queued item already carries current copy — nothing to do")
        return 0

    log.info("%s %d item(s) for %s:",
             "REWRITING" if args.apply else "WOULD REWRITE", len(planned), args.as_of)
    for old, new in planned:
        log.info("  %-6s  %r", old["source"].get("ticker"), old["text"].splitlines()[0])
        log.info("       ->  %r  (media kept: %d)",
                 new["text"].splitlines()[0], len(new.get("media") or []))

    if not args.apply:
        log.info("\ndry run — pass --apply to write the ledger")
        return 0

    cap = effective_cap(_load_cfg(root))
    done = 0
    for old, new in planned:
        # Enqueue the replacement FIRST: if that fails, the original is still
        # queued and the day still has content, rather than an empty slot.
        res = enqueue(new, root=root, max_per_account_day=cap)
        if res != "queued":
            log.warning("  %-6s enqueue returned %r — original left queued",
                        old["source"].get("ticker"), res)
            continue
        ok = transition(old["id"], "quarantined", actor="requeue_stale_copy",
                        root=root,
                        note=f"superseded by {new['id']} (stale copy: pre-fix headline)")
        if not ok:
            log.warning("  %-6s could not quarantine %s — BOTH are now queued, "
                        "fix by hand", old["source"].get("ticker"), old["id"])
            continue
        done += 1

    log.info("rewrote %d/%d item(s). COMMIT data/marketing/outbox/ for the "
             "publisher to see this.", done, len(planned))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
