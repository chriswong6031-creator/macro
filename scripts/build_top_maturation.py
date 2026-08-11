#!/usr/bin/env python3
"""Build the Winner Health context feed + forward log (TOP ANATOMY W1).

Thin CLI over `engine.top_maturation`. Runs in the daily.yml parallel band next
to Stage Analysis, off the render-critical path.

FAIL-OPEN BY CONTRACT. Any store, metadata or computation problem writes a
`null_state` artifact carrying the reason and exits 0 with a plain warning: the
page then renders its designed "warming up" state, which is an honest reading and
not a broken build. Exit 1 is reserved for being unable to write the artifact at
all.

Display tier, zero authority — see `engine.top_maturation.STANDING_LAW`, which
ships INSIDE the artifact so no downstream reader can pick up the numbers without
the constraint attached.

Usage:
    python -m scripts.build_top_maturation
    python -m scripts.build_top_maturation --root DATA_ROOT [--data-root SOURCE_ROOT]
                                           [--asof YYYY-MM-DD] [--trailing N] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine import top_maturation as tm  # noqa: E402

log = logging.getLogger("build_top_maturation")


def _data_dir(root: str | None) -> Path:
    """Resolve the data dir the way the engines do, else `<repo>/data`."""
    if root:
        return Path(root)
    try:
        from lib import config as _cfg  # noqa: PLC0415
        return Path(_cfg.data_dir())
    except Exception:  # noqa: BLE001
        return _REPO_ROOT / "data"


def _store_vintage(data_root: Path) -> dict:
    """What the source tape says about itself — stamped beside our own read."""
    p = data_root / tm.STORE_REL / "_manifest.json"
    try:
        m = json.loads(p.read_text())
        return {"store": m.get("store"), "n_tickers": m.get("n_tickers"),
                "latest_date": m.get("latest_date"), "updated_at": m.get("updated_at")}
    except Exception:  # noqa: BLE001
        return {}


def _write(out_root: Path, ctx: dict) -> Path:
    p = out_root / tm.LATEST_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ctx, indent=2, ensure_ascii=False, default=str) + "\n")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Winner Health context feed.")
    ap.add_argument("--root", default=None,
                    help="Data root to WRITE into (defaults to the repo data/).")
    ap.add_argument("--data-root", default=None,
                    help="Data root to READ source stores from (defaults to --root).")
    ap.add_argument("--asof", default=None, help="Read date YYYY-MM-DD (default: today UTC).")
    ap.add_argument("--trailing", type=int, default=tm.PANEL_TRAILING_SESSIONS,
                    help=f"Trailing sessions per name (default {tm.PANEL_TRAILING_SESSIONS}).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Read only the first N store files (tests / dry runs).")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    out_root = _data_dir(a.root)
    src_root = Path(a.data_root) if a.data_root else out_root
    t0 = time.time()

    stamp = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "scripts/build_top_maturation.py",
        # `engine.vintage_stamp` is deliberately NOT used here: its 8-field R3
        # stamp asserts a survivorship posture, a forward-path coverage fraction
        # and an era-law cohort, none of which a display-tier nightly read has an
        # honest value for. What CAN be attested is stamped instead — when the
        # source tape was written, and which frozen library the legs were cut
        # from — and nothing beyond that is claimed.
        "store_vintage": _store_vintage(src_root),
    }

    try:
        ctx, diag = tm.build_context(src_root, out_root=out_root, repo_root=_REPO_ROOT,
                                     trailing=a.trailing, asof=a.asof, limit=a.limit,
                                     log=lambda m: print(m, flush=True))
        thr = tm.load_thresholds(src_root)
        stamp["library_vintage"] = thr.get("vintage_utc")
        stamp["library_window"] = [thr.get("window_start"), thr.get("window_end")]
        ctx["_vintage"] = stamp
        ctx["_diagnostics"] = {k: v for k, v in diag.items() if k != "ledger_rows"}
    except Exception as e:  # noqa: BLE001 — fail-open: an honest null beats a dead page
        print(f"::warning title=top-maturation::read did not land ({e}) — writing "
              f"null_state artifact", flush=True)
        ctx = tm.null_context(str(e), asof=a.asof)
        ctx["_vintage"] = stamp
        try:
            _write(out_root, ctx)
        except Exception as e2:  # noqa: BLE001
            print(f"::error title=top-maturation::could not write the artifact ({e2})",
                  flush=True)
            return 1
        return 0

    try:
        p = _write(out_root, ctx)
    except Exception as e:  # noqa: BLE001
        print(f"::error title=top-maturation::could not write the artifact ({e})", flush=True)
        return 1

    n_led = tm.append_forward_log(diag.get("ledger_rows") or [], out_root)
    log.info("wrote %s — %d extended, %s; forward log +%d row(s); %.1fs",
             p, ctx["extended_n"], diag.get("per_state"), n_led, time.time() - t0)
    if diag.get("n_excluded_non_stock_instruments"):
        log.info("instrument filter: %d non-stock instrument(s) excluded from the board "
                 "(%s)", diag["n_excluded_non_stock_instruments"],
                 ", ".join(diag.get("excluded_instruments", [])[:12]))
    if not diag.get("thresholds_present"):
        print("::warning title=top-maturation::no frozen thresholds at "
              "data/top_anatomy/thresholds.json — every leg is dark and the board reads "
              "all-healthy; run scripts.export_top_anatomy_library", flush=True)
    if not diag.get("library_rows"):
        print("::warning title=top-maturation::no analog library at "
              "data/top_anatomy/library.parquet — every row prints 'no match'", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
