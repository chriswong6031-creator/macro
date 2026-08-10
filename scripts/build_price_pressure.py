"""scripts/build_price_pressure.py — Price Pressure lobe builder (DRL W1).

DISPLAY tier, context_only authority, zero scored surfaces.  Program home:
``research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md``.

Two modes:

    python -m scripts.build_price_pressure
        NIGHTLY INCREMENT (the daily.yml step).  Rebuilds the panel in memory
        (~45-60s, measured; no wide-frame cache is committed anywhere), harvests
        the self-healing catch-up window, appends idempotently, re-grades every
        open row, and writes ``data/price_pressure/latest.json``.  The LEDGER
        write is gated on ``engine.ledger_lane.nightly_advance_enabled()``: any
        lane may rebuild the display, only the nightly may advance the ledger.

    python -m scripts.build_price_pressure --backfill --store DIR --panel-cache DIR
        The one-shot historical seed + frozen base rates.  Operator-run, local,
        OFF CI and off the render path.  Never invoked by a workflow.

Refuse-to-run gate: a missing or stale bar store prints a workflow annotation and
exits 0 WITHOUT touching any artifact — a short run must never overwrite a good
ledger.  The annotation goes out through a bare ``print`` at the start of the
line: every builder here logs with a prefixing format, so an annotation emitted
through ``log.warning`` reads as an alarm in review and produces nothing in the
Actions summary (house law, ``tests/test_gh_annotation_line_start.py``).

No network calls.  No LLM (constitution A7).  Always exits 0 on the nightly path.
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stderr)
log = logging.getLogger("build_price_pressure")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STALE_SESSIONS = 10


def _resolve(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """(root, data_dir, store) — argument overrides first, then lib.config."""
    root = Path(args.root).resolve() if args.root else _REPO_ROOT
    if args.data_root:
        data_dir = Path(args.data_root).resolve()
    else:
        try:
            from lib import config

            data_dir = Path(config.data_dir())
        except Exception:  # noqa: BLE001 — a bare checkout still has data/
            data_dir = root / "data"
    store = Path(args.store).resolve() if args.store else data_dir / "massive_stock_day"
    return root, data_dir, store


def _nightly(args: argparse.Namespace) -> int:
    t0 = time.time()
    root, data_dir, store = _resolve(args)

    # Refuse an absent store before importing the parquet stack. The nightly
    # contract is fail-soft even in a bare checkout, where pandas/pyarrow may not
    # be installed; importing them first turned the intended warning into an
    # unrelated ModuleNotFoundError and a non-zero exit.
    if not store.exists() or not any(store.glob("*.parquet")):
        reason = "store absent or contains no parquet bars"
        print(f"::warning title=price-pressure-store-stale::bar store unusable at {store} "
              f"({reason}) — artifacts left untouched", flush=True)
        log.warning("price_pressure: refusing to run (%s)", reason)
        return 0

    import pandas as pd

    from engine.price_pressure import artifact as pp_artifact
    from engine.price_pressure import base_rates as pp_base
    from engine.price_pressure import detect as pp_detect
    from engine.price_pressure import panel as pp_panel
    from engine.price_pressure import pipeline as pp_pipeline

    pre = pp_panel.store_status(store, today=pd.Timestamp.now(tz="UTC").tz_localize(None).normalize(),
                                stale_sessions=args.stale_sessions)
    if not pre["present"] or pre["stale"]:
        print(f"::warning title=price-pressure-store-stale::bar store unusable at {store} "
              f"({pre['reason'] or 'unknown'}) — artifacts left untouched", flush=True)
        log.warning("price_pressure: refusing to run (%s)", pre["reason"])
        return 0

    cache_ctx = None
    if args.panel_cache:
        cache = Path(args.panel_cache)
    else:
        # No committed panel cache, ever: a stale ~170MB wide frame silently
        # answering "what happened last night" is worse than 45s of scanning.
        cache_ctx = tempfile.TemporaryDirectory(prefix="price_pressure_panel_")
        cache = Path(cache_ctx.name)
    try:
        prep = pp_pipeline.prepare(store, cache, data_dir)
        post = pp_panel.store_status(store, prep["sessions"],
                                     stale_sessions=args.stale_sessions)
        if post["stale"]:
            print(f"::warning title=price-pressure-store-stale::{post['reason']} — "
                  "artifacts left untouched", flush=True)
            log.warning("price_pressure: refusing to advance (%s)", post["reason"])
            return 0

        res = pp_pipeline.advance(prep, data_dir, mode="nightly", write=True,
                                  require_nightly_lane=not args.force_write,
                                  min_sessions=args.min_sessions, cap=args.cap)
        frozen = pp_base.read_base_rates(data_dir)
        payload = pp_artifact.build(
            res["ledger"], root=root, panel_names=prep["panel_names"],
            panel_span=prep["panel_span"], design=pp_detect.constants(),
            base_rates=frozen, sector_covered_share=prep["sector_covered_share"],
            basket_labels=prep.get("basket_labels"),
        )
        out = pp_artifact.write(payload, data_dir)
    finally:
        if cache_ctx is not None:
            cache_ctx.cleanup()

    st = res["stats"]
    log.info("price_pressure: wrote %s (rows=%d, gaps=%d)", out,
             len(res["ledger"]), len(payload.get("gaps") or []))
    # The masterplan requires the step's wall cost in the workflow log (§4).
    print(f"price_pressure: nightly increment {time.time() - t0:.1f}s "
          f"(panel {prep['timing_s']['panel']}s, derive {prep['timing_s']['derive']}s) "
          f"window={st['window']} appended={st['merge'].get('appended')} "
          f"forward={st['merge'].get('era_forward')} gap={st['merge'].get('era_gap')} "
          f"advanced={st['grade'].get('advanced')} closed={st['grade'].get('closed')} "
          f"ledger_write={st['write'].get('written')}", flush=True)
    if not st["write"].get("written"):
        log.info("price_pressure: ledger not advanced (%s)", st["write"].get("reason"))
    return 0


def _backfill(args: argparse.Namespace) -> int:
    from engine.price_pressure import backfill as pp_backfill

    t0 = time.time()
    root, data_dir, store = _resolve(args)
    if not args.panel_cache:
        print("::warning title=price-pressure-backfill::--panel-cache is required for "
              "--backfill (a 20k-file scan should not be repeated by accident)", flush=True)
        return 1
    if not store.exists() or not any(store.glob("*.parquet")):
        print(f"::warning title=price-pressure-backfill::bar store absent at {store}",
              flush=True)
        return 1

    res = pp_backfill.run(store=store, cache=Path(args.panel_cache), data_root=data_dir,
                          data_dir=data_dir, write_ledger=True)
    st = res["stats"]
    cov = (res["payload"].get("coverage") or {})
    print(f"price_pressure: BACKFILL {time.time() - t0:.1f}s "
          f"span={cov.get('panel_span')} panel={cov.get('panel_names')} "
          f"events={cov.get('events_total')} "
          f"(down={cov.get('events_down')} up={cov.get('events_up')}) "
          f"protected={st['merge'].get('protected')} "
          f"base_rates={res['base_rates_path']} artifact={res['artifact_path']}",
          flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Price Pressure lobe (DRL W1).")
    ap.add_argument("--backfill", action="store_true",
                    help="one-shot historical seed + frozen base rates (local only)")
    ap.add_argument("--store", default=None,
                    help="bar store directory (default: <data>/massive_stock_day)")
    ap.add_argument("--panel-cache", default=None,
                    help="local scratch dir for the wide panel (required with --backfill)")
    ap.add_argument("--root", default=None, help="repo root override")
    ap.add_argument("--data-root", default=None, help="data directory override")
    ap.add_argument("--min-sessions", type=int, default=15,
                    help="catch-up window floor, in sessions")
    ap.add_argument("--cap", type=int, default=90,
                    help="catch-up window cap, in sessions")
    ap.add_argument("--stale-sessions", type=int, default=_STALE_SESSIONS,
                    help="refuse to run when the store is more sessions behind than this")
    ap.add_argument("--force-write", action="store_true",
                    help="bypass the nightly-lane ledger gate (tests/local only)")
    args = ap.parse_args(argv)

    try:
        return _backfill(args) if args.backfill else _nightly(args)
    except Exception as exc:  # noqa: BLE001 — non-fatal step: annotate, do not traceback out
        print(f"::warning title=price-pressure-failed::{type(exc).__name__}: {exc}",
              flush=True)
        log.exception("price_pressure: build failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
