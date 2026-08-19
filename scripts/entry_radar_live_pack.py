#!/usr/bin/env python3
"""scripts/entry_radar_live_pack.py — the nightly / pre-open PACK builder (W4/PR-4).

WHAT THIS LANE OWNS (W4 design §2, §3)
---------------------------------------
Everything that happens at a SESSION BOUNDARY, off the RTH path:

  1. assemble the Probe Set — by INVOKING ``scripts/entry_radar_universe.py``'s
     own machinery in-process, never a second funnel — and publish
     ``entry_radar_probe_set.json`` exactly as that script does.  This lane
     becomes the production home for that artifact;
  2. freeze the evaluation substrate and invert C1/C2a into per-name price
     thresholds (``engine/entry_radar/live_pack.py``);
  3. run the §10 episode CLOCK OVERLAY (CANDIDATE → RESOLVED at H, re-arm
     bookkeeping) — calendar arithmetic only, no price;
  4. evaluate the confirmed-bar G0/C5 lanes from the Terminal slice store when
     ``ENTRY_RADAR_SLICE_DIR`` points at one, and publish them honestly
     ``unavailable`` when it does not;
  5. run the nightly threshold-inversion PROOF battery and refuse to publish a
     pack that fails it;
  6. SPOOL the pass, and only then commit the ledger.

WRITE DISCIPLINE — NO ``data/`` PATH IS EVER WRITTEN
-----------------------------------------------------
``data/stocks/<SYM>.parquet`` is READ, through a reader defined here so the
engine package names no store path at all.  The read deliberately does NOT go
through ``lib.store.read``: ``lib.store._path`` calls ``mkdir(parents=True)`` on
the group directory, and a pack builder that CREATES ``data/stocks`` on a host
that has none is a ``data/`` write by accident.

Three sinks, none durable: the live-artifact ladder (probe set), the runtime
state dir (pack + ledger), and the R2/local event spool.  ``DURABLE_WRITES``
below is empty and the ``--nightly`` gate exists to keep it that way.

SPOOL BEFORE CONSUME
--------------------
The pass's transitions are spooled as ONE object under
``live_flow/entry_radar_events/`` (the W1 ``NominationSpool`` mechanism at a
second prefix — same code, not a second queue) BEFORE the ledger commits.  A
spool failure withholds the transitions from the ledger, emits a line-start
``::warning`` and exits 4; the next pass re-derives and retries, which is safe
because every address is deterministic.

EXIT CODES
----------
  0  pack built and published (or already current for this session, or --dry-run)
  2  refusal BEFORE any write — detector spec-hash drift, or no state plane
  3  the pass produced no output at all (neither pack nor probe-set artifact)
  4  spool failure — transitions withheld, ledger NOT committed, pack still saved
  5  the daily store does not reach the expected last session (--allow-stale-store
     overrides; the RTH stale-pack gate is the real protection, this refusal
     keeps the ARTIFACT honest at build time)

USAGE
    python3 scripts/entry_radar_live_pack.py --dry-run
    python3 scripts/entry_radar_live_pack.py --state-dir /var/lib/macro-live/state/entry_radar
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# UNCONDITIONAL, and at position 0 on purpose — the same strong pin
# scripts/entry_radar_universe.py carries.  The `if str(ROOT) not in sys.path`
# form is NOT a pin: when ROOT is already on the path but sits BEHIND a foreign
# package, the guard skips the insert and the foreign package still wins the
# import.  tests/test_check_script_import_pinning.py::_strong_pin rejects the
# conditional shape for exactly that reason.
sys.path.insert(0, str(ROOT))

from engine.entry_radar import live_ledger as ll  # noqa: E402
from engine.entry_radar import live_pack as lp  # noqa: E402
from engine.entry_radar.c5_adapter import run_c5  # noqa: E402
from engine.entry_radar.contracts import iso, utcnow  # noqa: E402
from engine.entry_radar.entry_events import EntryEventStore  # noqa: E402
from engine.entry_radar.g0_adapter import g0_events  # noqa: E402
from engine.entry_radar.indicator_ingest import (  # noqa: E402
    IndicatorSliceError,
    ingest_slice,
    load_slice,
)
from engine.entry_radar.nomination_bus import NominationBus  # noqa: E402
from engine.entry_radar.spool import NominationSpool  # noqa: E402
from engine.entry_radar.universe import assemble_probe_set, load_config  # noqa: E402
from lib.nyse_calendar import expected_last_session  # noqa: E402
from scripts.entry_radar_universe import (  # noqa: E402
    ARTIFACT_NAME,
    collect,
    live_dir,
    market_session,
    write_artifact,
)

log = logging.getLogger("entry_radar_live_pack")

#: Durable ``data/`` paths this script writes.  EMPTY BY DESIGN.
DURABLE_WRITES: tuple[str, ...] = ()

_VPS_STATE_DIR = Path("/var/lib/macro-live/state/entry_radar")
_STATE_DIR_ENV = "ENTRY_RADAR_STATE_DIR"
_SLICE_DIR_ENV = "ENTRY_RADAR_SLICE_DIR"
_SLICE_UNCONFIGURED = "slice_store_unconfigured"


# ---------------------------------------------------------------------------
# sinks
# ---------------------------------------------------------------------------

def state_dir(override: str | None = None) -> Path | None:
    """``--state-dir`` → ``$ENTRY_RADAR_STATE_DIR`` → the VPS path, or None.

    None means "no state plane on this host" — the pack has nowhere lawful to
    live and the lane says so rather than inventing a directory inside the repo.
    """
    if override and override.strip():
        return Path(override.strip())
    env = os.environ.get(_STATE_DIR_ENV, "").strip()
    if env:
        return Path(env)
    if _VPS_STATE_DIR.parent.is_dir():
        return _VPS_STATE_DIR
    return None


def store_reader(root: Path) -> Callable[[str], pd.DataFrame | None]:
    """Read ``data/stocks/<SYM>.parquet``.  Missing or unreadable ⇒ None.

    Deliberately not ``lib.store.read``: that helper's path builder mkdirs the
    group directory (see the module docstring).  The filename sanitisation below
    mirrors ``lib/store.py::_path`` so the two agree on where a name lives.
    """
    group = root / "data" / "stocks"

    def _safe(name: str) -> str:
        return (str(name).replace("^", "_").replace("=", "_")
                .replace("/", "_").replace(" ", "_"))

    def reader(ticker: str) -> pd.DataFrame | None:
        path = group / f"{_safe(ticker)}.parquet"
        if not path.is_file():
            return None
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001 — one bad file is not an outage
            log.warning("entry_radar_live_pack: %s unreadable (%s)", path.name, exc)
            return None
        frame = frame.copy()
        frame.index = pd.to_datetime(frame.index)
        return frame.sort_index()

    return reader


# ---------------------------------------------------------------------------
# the confirmed-bar G0 / C5 lanes
# ---------------------------------------------------------------------------

def slice_lanes(tickers: list[str], *, as_of: date, slice_dir: Path | None,
                ) -> tuple[dict[str, Any], list[Any]]:
    """Run the G0 + C5 confirmed-bar lanes from the Terminal slice store.

    ``ENTRY_RADAR_SLICE_DIR`` unset ⇒ BOTH lanes publish
    ``{available: False, reason: "slice_store_unconfigured"}``.  That is the null
    law, honestly: no ``mastermind.indicator/v1`` slice store exists in
    production anywhere yet (design §3b), and reporting the lanes as "no
    candidates" would be a measured non-fire of a detector that never ran.

    The identity and freshness gates are the ingest module's own; a slice they
    refuse is recorded ``unavailable`` for THAT NAME with the refusal's reason,
    and no event from it reaches any store.
    """
    if slice_dir is None:
        block = {"available": False, "reason": _SLICE_UNCONFIGURED,
                 "slice_dir": None, "names": 0}
        return {"g0": dict(block), "c5": dict(block)}, []

    runs: list[Any] = []
    per_name: dict[str, Any] = {}
    g0_dots = 0
    c5_candidates = 0
    for ticker in tickers:
        path = slice_dir / f"{ticker}.slice.json"
        if not path.is_file():
            per_name[ticker] = {"available": False, "reason": "slice_absent"}
            continue
        try:
            slice_ = load_slice(path)
            store = EntryEventStore()
            ingest_slice(slice_, store, as_of_reference_date=as_of)
            report = g0_events(slice_, store)
            run = run_c5(store)
        except (IndicatorSliceError, ValueError) as exc:
            per_name[ticker] = {"available": False, "reason": "slice_refused",
                                "detail": str(exc)[:400]}
            continue
        g0_dots += len(report.grey_event_ids)
        c5_candidates += len(run.candidates)
        per_name[ticker] = {"available": True,
                            "g0_grey_events": len(report.grey_event_ids),
                            "g0_watch_events": len(report.watch_event_ids),
                            "c5_candidates": len(run.candidates),
                            "c5_episodes": len(run.episodes)}
        runs.append((ticker, run))

    available = [t for t, row in per_name.items() if row.get("available")]
    # "we looked and every slice was unreadable" and "there was nothing to look
    # at" are different facts, and only one of them is a data problem.
    reason = None if available else ("no_probe_names" if not tickers
                                     else "no_readable_slice")
    lanes = {
        "g0": {"available": bool(available), "reason": reason,
               "slice_dir": str(slice_dir), "names": len(available),
               "grey_events": g0_dots},
        "c5": {"available": bool(available), "reason": reason,
               "slice_dir": str(slice_dir), "names": len(available),
               "candidates": c5_candidates},
        "per_name": per_name,
    }
    return lanes, runs


def confirmed_lane_pack_rows(lanes: dict[str, Any],
                             tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Reshape :func:`slice_lanes`'s per-ticker aggregate into the pack's
    ``{ticker: {g0: {...}, c5: {...}}}`` shape (W4.1).

    ``live_pack.confirmed_lanes_snapshot`` is the NORMALIZER — it fills in any
    ticker this function does not name (or a row it does not recognise) with
    the honest ``slice_store_unconfigured`` default; this function only
    translates the slice adapter's own aggregate into rows that normalizer can
    recognise as ``available``.
    """
    per_name = lanes.get("per_name") or {}
    out: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        row = per_name.get(ticker)
        if row is None:
            # slice_dir unset, or this ticker's slice was never looked at at
            # all — the top-level lanes reason (or the module default) applies.
            reason = (lanes.get("g0") or {}).get("reason") or _SLICE_UNCONFIGURED
            unavailable = {"availability": "unavailable", "reason": reason}
            out[ticker] = {"g0": dict(unavailable), "c5": dict(unavailable)}
            continue
        if not row.get("available"):
            unavailable = {"availability": "unavailable", "reason": row.get("reason")}
            if row.get("detail"):
                unavailable["detail"] = row["detail"]
            out[ticker] = {"g0": dict(unavailable), "c5": dict(unavailable)}
            continue
        out[ticker] = {
            "g0": {"availability": "available",
                   "grey_events": row.get("g0_grey_events"),
                   "watch_events": row.get("g0_watch_events")},
            "c5": {"availability": "available",
                   "candidates": row.get("c5_candidates"),
                   "episodes": row.get("c5_episodes")},
        }
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911, PLR0912, PLR0915
    ap = argparse.ArgumentParser(
        description="Build the Live Entry Radar nightly pack (W4/PR-4).")
    ap.add_argument("--root", default=str(ROOT), help="repo root (default: this checkout)")
    ap.add_argument("--state-dir", default=None,
                    help=f"runtime state dir (default: ${_STATE_DIR_ENV}, then "
                         f"{_VPS_STATE_DIR})")
    ap.add_argument("--live-dir", default=None,
                    help="override the live-artifact directory (default: the §7.3 ladder)")
    ap.add_argument("--spool-dir", default=None,
                    help="local event-spool directory (default: $ENTRY_RADAR_SPOOL_DIR)")
    ap.add_argument("--as-of", default=None,
                    help="session to freeze (default: expected_last_session(now))")
    ap.add_argument("--allow-stale-store", action="store_true",
                    help="publish even when the daily store has not reached --as-of")
    ap.add_argument("--force", action="store_true",
                    help="rebuild even when the pack for this session is already current")
    ap.add_argument("--dry-run", action="store_true",
                    help="build, prove and print — write NOTHING")
    ap.add_argument("--nightly", action="store_true",
                    help="assert the nightly lane gate before any durable write")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    root = Path(args.root).resolve()
    now = utcnow()
    as_of = (date.fromisoformat(args.as_of) if args.as_of
             else expected_last_session(now))

    if args.nightly:
        from engine.ledger_lane import nightly_advance_enabled  # noqa: PLC0415
        gate = nightly_advance_enabled()
        print(f"entry-radar-pack nightly gate: nightly_advance_enabled()={gate} "
              f"durable_writes={list(DURABLE_WRITES)}", flush=True)
        if DURABLE_WRITES and not gate:
            print("::warning title=entry-radar-pack::--nightly requested outside the "
                  "nightly lane — durable writes refused", flush=True)
            return 2

    # The spec-hash gate runs FIRST, before a price is read: every level in a
    # pack is attributed to a named detector identity.
    try:
        lp.assert_published_spec_hashes()
    except lp.SpecHashDrift as exc:
        print(f"::error title=entry-radar-pack::{exc}", flush=True)
        return 2

    state = state_dir(args.state_dir)
    if state is None and not args.dry_run:
        print("::warning title=entry-radar-pack::no runtime state plane on this host "
              f"(--state-dir / ${_STATE_DIR_ENV} / {_VPS_STATE_DIR.parent} all absent) "
              "— the pack has nowhere lawful to live; re-run with --dry-run to rehearse",
              flush=True)
        return 2

    # --- idempotency: the pack for this session may already be current -------
    if state is not None and not args.force:
        existing = lp.load_pack(state)
        if existing is not None and existing.as_of == as_of.isoformat():
            print(f"entry-radar-pack already current for {as_of.isoformat()} "
                  f"(pack_hash {existing.pack_hash}) — nothing to do", flush=True)
            return 0

    # --- 1. the probe set, through the W1 machinery --------------------------
    cfg = load_config(root)
    spool_prefix = str((cfg.get("spool") or {}).get("prefix")
                       or "live_flow/entry_radar_nominations")
    nomination_spool = None if args.dry_run else NominationSpool(
        local_dir=Path(args.spool_dir) if args.spool_dir else None,
        prefix=spool_prefix)
    bus = NominationBus(spool=nomination_spool)
    inputs = collect(root, cfg, bus=bus, now=now)

    out_dir = live_dir(root, args.live_dir)
    try:
        previous = json.loads((out_dir / ARTIFACT_NAME).read_text(encoding="utf-8"))
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

    # --- 2. freeze the substrate + invert the thresholds ---------------------
    # The confirmed-bar G0/C5 lanes are read FIRST (from the same tickers
    # `build_pack` will independently derive via `probe_set_snapshot`, a pure
    # function of `probe_set`) so the v2 pack can carry them in `confirmed_lanes`
    # — and therefore inside its own `pack_hash` — from the moment it exists,
    # rather than as a value bolted on after the identity was already computed.
    snapshot_tickers = list(lp.probe_set_snapshot(probe_set).get("tickers") or [])
    slice_dir_raw = os.environ.get(_SLICE_DIR_ENV, "").strip()
    slice_dir = Path(slice_dir_raw) if slice_dir_raw else None
    lanes, c5_runs = slice_lanes(snapshot_tickers, as_of=as_of, slice_dir=slice_dir)
    confirmed_lanes = confirmed_lane_pack_rows(lanes, snapshot_tickers)

    pack = lp.build_pack(probe_set=probe_set, store_reader=store_reader(root),
                         as_of=as_of, built_at=iso(now) or "",
                         vintage=f"store@{as_of.isoformat()}",
                         confirmed_lanes=confirmed_lanes)
    newest = max((row.last_confirmed for row in pack.names
                  if row.last_confirmed), default=None)
    print(f"entry-radar-pack as_of={pack.as_of} next_session={pack.next_session} "
          f"names={len(pack.names)} missing={len(pack.substrate_missing)} "
          f"store_newest={newest} pack_hash={pack.pack_hash}", flush=True)
    if newest != as_of.isoformat() and not args.allow_stale_store:
        print(f"::warning title=entry-radar-pack::the daily store's newest session is "
              f"{newest}, not the expected {as_of.isoformat()} — REFUSING to publish a "
              f"pack stamped at a session the store has not reached "
              f"(--allow-stale-store overrides).  The RTH stale-pack gate is the real "
              f"protection; this refusal keeps the artifact honest at build time",
              flush=True)
        return 5

    # --- 3. the inversion proof ---------------------------------------------
    proof = lp.build_inversion_proof(pack)
    pack = pack.with_proof(proof)
    print(f"entry-radar-pack inversion proof: {proof['cases_total']} case(s), "
          f"pass={proof['pass']} by_family={proof['by_family']}", flush=True)
    if not proof["pass"]:
        for case in proof["failures"][:10]:
            print(f"::warning title=entry-radar-pack-proof::{case['family']}/"
                  f"{case['case']} expected {case['expected']!r} observed "
                  f"{case['observed']!r} at boundary {case['boundary']!r}", flush=True)
        print("::warning title=entry-radar-pack::inversion proof FAILED — the pack is "
              "published with proof_failed=true and the RTH evaluator must refuse the "
              "whole cycle (fail closed)", flush=True)

    # --- 4. clock overlay + the confirmed-bar lanes' ledger events -----------
    # `lanes`/`c5_runs` were already computed above (step 2) so the pack could
    # carry `confirmed_lanes`; this step applies the C5 detector RUNS (episodes/
    # events) those slices produced to the ledger — a different consumption of
    # the same `slice_lanes()` call, not a second read of the slice store.
    ledger = ll.LiveEpisodeLedger.load(state) if state is not None \
        else ll.LiveEpisodeLedger(None)
    confirmed_k = {row.ticker: row.confirmed_k for row in pack.names}

    deltas = [ll.apply_session_clocks(ledger, as_of_session=pack.as_of,
                                      confirmed_k_by_name=confirmed_k)]
    for ticker, run in c5_runs:
        deltas.append(ledger.apply_run(
            ticker=ticker, as_of_session=pack.as_of, runs=[run],
            pass_id=ll.PACK_PASS_ID,
            context={"bar_availability": {"grain": "confirmed_daily_3d",
                                          "lane": "terminal_slice"},
                     "data_quality": "ok",
                     "freshness": {"pack_as_of": pack.as_of,
                                   "source": "terminal_indicator_slice"}}))
    delta = ll.merge_deltas(deltas, as_of_session=pack.as_of, pass_id=ll.PACK_PASS_ID)
    print(f"entry-radar-pack delta: {len(delta.transitions)} transition(s), "
          f"{len(delta.events)} event(s), {len(delta.episodes)} episode(s), "
          f"{len(delta.superseded)} superseded terminal trace(s); "
          f"g0={lanes['g0']} c5={lanes['c5']}", flush=True)

    if args.dry_run:
        print("dry-run — nothing written (no pack, no ledger, no spool object)",
              flush=True)
        return 0

    # --- 5. save the pack ----------------------------------------------------
    assert state is not None  # guarded above for the non-dry-run path
    pack_path = lp.save_pack(pack, state)
    print(f"entry-radar-pack saved {pack_path}", flush=True)

    # --- 6. SPOOL, then commit ----------------------------------------------
    event_spool = ll.EventSpool(
        local_dir=Path(args.spool_dir) if args.spool_dir else None)
    stamp_utc = now.astimezone(timezone.utc)
    health = {
        "pack": {"as_of": pack.as_of, "pack_hash": pack.pack_hash,
                 "proof_failed": pack.proof_failed},
        "probe_set": {"count": int(pack.probe_set.get("count") or 0)},
        "substrate": {"names": len(pack.names),
                      "missing": len(pack.substrate_missing)},
        "lanes": {"g0": lanes["g0"], "c5": lanes["c5"]},
    }
    receipt, committed = ll.spool_then_commit(
        ledger, delta, spool=event_spool, pass_ts=iso(now) or "",
        session=stamp_utc.date().isoformat(), stamp=stamp_utc.strftime("%H%M%S"),
        pack_as_of=pack.as_of, pack_hash=pack.pack_hash, health=health)
    if not committed:
        print("::warning title=entry-radar-pack::event spool FAILED — this pass's "
              f"{len(delta.transitions)} transition(s) are WITHHELD from the ledger and "
              "the payload; the next pass re-derives and retries (every address is "
              "deterministic, so the retry is exactly-once-effective)", flush=True)
        return 4

    ledger.compact(as_of_session=pack.as_of)
    ledger.save()
    if receipt:
        print(f"entry-radar-pack spooled {receipt}", flush=True)

    # --- 7. publish the probe set (this lane's production home) --------------
    payload = probe_set.to_dict()
    payload["lane"] = {"nightly": bool(args.nightly),
                       "durable_writes": list(DURABLE_WRITES),
                       "pack": {"as_of": pack.as_of, "pack_hash": pack.pack_hash}}
    served = write_artifact(out_dir / ARTIFACT_NAME, payload)
    if not served and pack_path is None:
        print("::warning title=entry-radar-pack::pass produced NO output — neither the "
              "pack nor the probe-set artifact was written", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
