#!/usr/bin/env python3
"""scripts/entry_radar_universe.py — assemble the Live Entry Radar Probe Set.

Reads every producer artifact, runs the Layer A–D funnel, and publishes
``entry_radar_probe_set.json`` into the live-artifact ladder.  This is PR-1's
only entrypoint; there is no detector, no score and no page yet.

WRITE DISCIPLINE — THIS SCRIPT WRITES NO ``data/`` PATH
--------------------------------------------------------
Two sinks, neither durable:

  * the **live dir** (``$MACRO_LIVE_DIR`` → ``/var/lib/macro-live/public/live``
    → ``site/live``), by atomic rename — the same ladder and the same
    ``mkstemp`` + ``os.replace`` shape ``scripts/prophet_live_evaluator.py``
    uses, so a reader never sees a half-written artifact;
  * the **nomination spool** (R2, or ``$ENTRY_RADAR_SPOOL_DIR``).

``DURABLE_WRITES`` below is empty and the ``--nightly`` gate exists to keep it
that way: if a later PR adds a ``data/entry_radar/**`` write it must pass
``engine/ledger_lane.py::nightly_advance_enabled()`` first — the mechanical
form of the single-advancer law (contract §7.3).  The nightly reconciler of
PR-5 is the only writer of durable evidence, and the intraday lane must never
race it on one store.

SESSION STAMPING
----------------
The artifact carries the real NYSE session from ``lib/nyse_calendar``, never
wall-clock arithmetic (contract §7): a holiday is not a session, and an
artifact stamped with a date the market never opened would corrupt every
downstream join.

USAGE
    python3 scripts/entry_radar_universe.py --dry-run
    python3 scripts/entry_radar_universe.py --root . --live-dir /var/lib/macro-live/public/live
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.entry_radar.contracts import ProducerRead, utcnow  # noqa: E402
from engine.entry_radar.nomination_bus import NominationBus  # noqa: E402
from engine.entry_radar.producers import (  # noqa: E402
    memberships_from,
    names_from,
    read_flow_pulse,
    read_group_pulse,
    read_ipo_calendar,
    read_linked_outsiders,
    read_setups,
    read_stock_library,
    read_universe_sources,
    read_us_standouts,
)
from engine.entry_radar.spool import NominationSpool  # noqa: E402
from engine.entry_radar.universe import (  # noqa: E402
    SupabaseWatchlistAdapter,
    assemble_probe_set,
    build_layer_a,
    curated_wrapper_tickers,
    load_config,
)

log = logging.getLogger("entry_radar_universe")

ARTIFACT_NAME = "entry_radar_probe_set.json"
_VPS_LIVE_DIR = Path("/var/lib/macro-live/public/live")

#: Durable ``data/`` paths this script writes.  EMPTY BY DESIGN — see the
#: module docstring.  Anything added here must be gated on
#: ``nightly_advance_enabled()`` before the write, not after.
DURABLE_WRITES: tuple[str, ...] = ()


def live_dir(root: Path, override: str | None = None) -> Path:
    """Resolve the live-artifact directory (contract §7.3 ladder)."""
    if override and override.strip():
        return Path(override.strip())
    env = os.environ.get("MACRO_LIVE_DIR", "").strip()
    if env:
        return Path(env)
    if _VPS_LIVE_DIR.is_dir():
        return _VPS_LIVE_DIR
    return root / "site" / "live"


def market_session(now: datetime | None = None) -> str:
    """The NYSE session date for this pass — calendar, never wall clock."""
    stamp = (now or utcnow()).astimezone(timezone.utc)
    try:
        from lib.nyse_calendar import last_session_on_or_before  # noqa: PLC0415
        from zoneinfo import ZoneInfo  # noqa: PLC0415
        et = stamp.astimezone(ZoneInfo("America/New_York")).date()
        return last_session_on_or_before(et).isoformat()
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=entry-radar::NYSE calendar unavailable ({exc}) — "
              "falling back to the UTC date", flush=True)
        return stamp.date().isoformat()


def write_artifact(path: Path, payload: dict[str, Any]) -> bool:
    """Atomic-rename publish.  False (never a raise) when the sink is absent."""
    parent = path.parent
    if not parent.is_dir():
        print(f"::notice title=entry-radar::{parent} is absent — no live plane on this "
              "host, so no served copy", flush=True)
        return False
    tmp_name: str | None = None
    try:
        # Serialise BEFORE the temp file: a payload that will not encode must not
        # leave a stray dot-file next to a live artifact.
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
            os.fchmod(fh.fileno(), 0o644)
        os.replace(tmp_name, path)
        tmp_name = None
        print(f"entry-radar served {path} ({len(body)} bytes)", flush=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=entry-radar::served copy {path} not written ({exc}) — "
              "the previous copy stands", flush=True)
        return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def collect(root: Path, cfg: dict[str, Any], *, bus: NominationBus,
            now: datetime, supabase_client: Any = None) -> dict[str, Any]:
    """Read every producer, ingest nominations, and return the layer inputs.

    Every read is independent: one absent artifact costs its own lane and
    nothing else, and lands in the artifact's availability block as
    ``unavailable`` rather than as silence.
    """
    site = root / "site"
    data = root / "data"

    sources = read_universe_sources(root, cfg=cfg)
    stock = read_stock_library(stockdata_dir=site / "stockdata", cfg=cfg, now=now)
    flow = read_flow_pulse(site / "live" / "flow_pulse.json", cfg=cfg, now=now)
    ipo = read_ipo_calendar(data / "ipo" / "calendar.parquet", cfg=cfg, now=now)

    # The operator-watchlist block is a real switch: `enabled: false` disables
    # the lane outright rather than leaving a permanently-unavailable producer
    # in the availability report, and `tables` is the adapter's actual read list.
    sb_cfg = dict((cfg.get("layer_b") or {}).get("supabase") or {})
    if sb_cfg.get("enabled", True):
        watchlist = SupabaseWatchlistAdapter(
            supabase_client,
            tables=tuple(sb_cfg.get("tables") or ("watchlists", "watchlist_symbols",
                                                  "portfolio_positions"))).read(now=now)
    else:
        watchlist = ProducerRead(source_id=SupabaseWatchlistAdapter.SOURCE_ID,
                                 status="unavailable", observed_at=now,
                                 detail="disabled via config layer_b.supabase.enabled")

    reads: list[ProducerRead] = [
        read_us_standouts(site / "factordata" / "us_standouts.json", cfg=cfg, now=now),
        read_setups(site / "factordata" / "setups.json", cfg=cfg, now=now),
        read_group_pulse(site / "basketdata" / "pulse.json", cfg=cfg, now=now),
        read_linked_outsiders(site / "basketdata" / "linked_outsiders.json",
                              cfg=cfg, now=now),
        flow.read, ipo.read, stock.read, watchlist,
    ]
    bus.ingest_reads(reads, now=now, pass_id="nightly")

    names = {**names_from(sources), **stock.names}
    layer_a = build_layer_a(sources, names=names, curated=curated_wrapper_tickers())

    hot_features: dict[str, dict[str, Any]] = {
        sym: dict(row) for sym, row in stock.features.items()}
    for sym, row in flow.features.items():
        hot_features.setdefault(sym, {}).update(row)

    return {
        "layer_a": layer_a,
        "memberships": memberships_from(sources),
        "liquidity": stock.features,
        "watchlist": watchlist,
        "hot_features": hot_features,
        "hot_read": stock.read,
        "history_age": {**stock.history_age, **ipo.history_age},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assemble the Live Entry Radar Probe Set.")
    ap.add_argument("--root", default=str(ROOT), help="repo root (default: this checkout)")
    ap.add_argument("--live-dir", default=None,
                    help="override the live-artifact directory (default: the §7.3 ladder)")
    ap.add_argument("--spool-dir", default=None,
                    help="local nomination spool directory (default: $ENTRY_RADAR_SPOOL_DIR)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the assembly summary and write NOTHING")
    ap.add_argument("--nightly", action="store_true",
                    help="assert the nightly lane gate before any durable write")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    root = Path(args.root).resolve()
    now = utcnow()
    cfg = load_config(root)

    if args.nightly:
        # The gate is CALLED unconditionally, not guarded behind a set that is
        # currently empty — a single-advancer law that never executes is
        # documentation, and documentation does not fail closed.  It is a no-op
        # on writes today (DURABLE_WRITES is empty by design) but it is
        # exercised, logged and testable, so PR-5 inherits a live gate rather
        # than a comment.
        from engine.ledger_lane import nightly_advance_enabled  # noqa: PLC0415
        gate = nightly_advance_enabled()
        print(f"entry-radar nightly gate: nightly_advance_enabled()={gate} "
              f"durable_writes={list(DURABLE_WRITES)}", flush=True)
        if DURABLE_WRITES and not gate:
            print("::warning title=entry-radar::--nightly requested outside the nightly "
                  "lane (COLLECT_LANE!=nightly) — durable writes refused", flush=True)
            return 2

    spool = None if args.dry_run else NominationSpool(
        local_dir=Path(args.spool_dir) if args.spool_dir else None,
        prefix=str((cfg.get("spool") or {}).get("prefix")
                   or "live_flow/entry_radar_nominations"))
    bus = NominationBus(spool=spool)

    inputs = collect(root, cfg, bus=bus, now=now)
    out_dir = live_dir(root, args.live_dir)
    previous = None
    prior_path = out_dir / ARTIFACT_NAME
    try:
        previous = json.loads(prior_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None

    probe_set = assemble_probe_set(
        layer_a=inputs["layer_a"], bus=bus, cfg=cfg,
        memberships=inputs["memberships"], liquidity=inputs["liquidity"],
        watchlist=inputs["watchlist"], hot_features=inputs["hot_features"],
        hot_read=inputs["hot_read"], history_age=inputs["history_age"],
        previous=previous, market_session=market_session(now), now=now)

    for line in probe_set.summary_lines():
        print(line, flush=True)

    if args.dry_run:
        print("dry-run — nothing written (no live artifact, no spool object)", flush=True)
        return 0

    payload = probe_set.to_dict()
    payload["lane"] = {"nightly": bool(args.nightly), "durable_writes": list(DURABLE_WRITES)}
    served = write_artifact(out_dir / ARTIFACT_NAME, payload)
    spooled = bool(bus.spool_keys)
    if not served and not spooled:
        # Silence is this estate's default failure mode: a pass that published
        # nothing and exited 0 is indistinguishable from a healthy pass to every
        # instrument we own, and no staleness monitor can see a bake that never
        # landed.  Exit non-zero so the lane's own status carries the fact.
        print("::warning title=entry-radar::pass produced NO output — neither the live "
              f"artifact ({out_dir / ARTIFACT_NAME}) nor a spool object was written; "
              "the probe set on disk is whatever the previous pass left", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
