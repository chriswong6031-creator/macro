"""scripts/build_prophet_live_pack.py — nightly Prophet Live arming pass (P0 D2).

Probes the SAME close-only admission gate the board is built from with candidate
provisional closes and publishes the resulting per-name trigger/fade levels to R2 as
``live_flow/prophet_live_armed.json``. The */5 evaluator reads that and never
re-derives a signal (research/PROPHET_LIVE_INTRADAY_SIGNALS_MASTERPLAN_BY_FABLE.md
§4.1). All compute lives in :mod:`engine.prophet_live.armed_pack`; this script owns
the universe read, the process fan-out, the budget deadline and the publish.

    python -m scripts.build_prophet_live_pack [--publish] [--out PATH] [--now ISO]
                                              [--workers N] [--limit N]

RUNS AFTER build_site inside daily.yml's engine job, non-fatal. It reuses
``scripts.build_stock_library.universe()`` so the close series it probes are the
exact series the board's own ``signal_gate.gate`` call site consumes — a second
loader would be a second definition of the universe, which is how two surfaces start
disagreeing about who is in it.

BUDGET IS LAW. One gate call is ~250 ms on this universe, so a full grid over every
name does not fit the render budget. The centre census (one call per name) is always
paid; the probe phase then runs under both ``max_probe`` and a wall-clock
``max_seconds``, and everything the budget cuts is counted in ``meta.skipped``.
Measured timings are printed on every run so a regression shows up in the log.

FAIL-CLOSED ON PARITY (G0.1). After assembly, every probed name's published
interval is checked against tonight's real verdict. One mismatch and NOTHING is
published: a missing pack makes the evaluator go dark, which is honest, while a
wrong pack tells a user a level that does not exist.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, _CODE_ROOT)

from engine.prophet_live import armed_pack as AP  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402

log = logging.getLogger("build_prophet_live_pack")

#: Worker-local universe: {ticker: close series}. Populated once per process.
_CLOSES: dict[str, Any] = {}
_CFG: dict[str, Any] = {}


def _winit(cfg: dict[str, Any]) -> None:  # pragma: no cover - subprocess path
    """Load the universe into this worker. Mirrors build_stock_library's _winit."""
    from scripts.build_stock_library import universe  # noqa: PLC0415
    global _CFG
    _CFG = cfg
    for tkr, close, _high, _name, _sector in universe():
        s = AP.clean_closes(close)
        if s is not None and len(s) >= 2:
            _CLOSES[tkr] = s


def _centre(tkr: str) -> dict[str, Any]:  # pragma: no cover - subprocess path
    """Phase 1 task: tonight's verdict + the span a probe would sweep."""
    rec = AP.centre_record(tkr, _CLOSES[tkr], cfg=_CFG)
    # The raw analyze() payload is large and can carry NaN; the pack never uses it
    # and pickling it back would dominate the phase's IPC cost.
    v = rec.get("center_verdict") or {}
    rec["center_verdict"] = {k: v.get(k) for k in
                             ("eligible", "tier", "sub", "tier_cascade", "ticks",
                              "bars_to_cross", "hist_d2", "hist_d3", "provisional",
                              "near_miss_reason")}
    return rec


def _probe(args: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:  # pragma: no cover
    """Phase 2 task: grid + bisection over the name's span."""
    tkr, rec = args
    return tkr, AP.probe_name(tkr, _CLOSES[tkr], rec, cfg=_CFG)


def _workers(explicit: int | None) -> int:
    """Pool size. Reuses the stock library's own policy so the two passes agree."""
    if explicit:
        return max(1, int(explicit))
    try:
        from scripts.build_stock_library import _library_workers  # noqa: PLC0415
        return _library_workers()
    except Exception:  # noqa: BLE001
        return max(1, min(os.cpu_count() or 1, 8))


def build(*, cfg: dict[str, Any] | None = None, now: datetime | None = None,
          workers: int | None = None, limit: int | None = None) -> dict[str, Any]:
    """Run both phases across a process pool and return the assembled payload."""
    from scripts.build_stock_library import universe  # noqa: PLC0415

    c = AP.pack_cfg(cfg)
    t0 = time.time()
    uni = universe()
    if limit:
        uni = uni[: int(limit)]
    series: dict[str, Any] = {}
    skipped: dict[str, int] = {}
    for tkr, close, _high, _name, _sector in uni:
        s = AP.clean_closes(close)
        if s is None or len(s) < 2:
            skipped["no_series"] = skipped.get("no_series", 0) + 1
            continue
        series[tkr] = s
    tip = AP.as_of_date(series.values())
    print(f"prophet-live pack: universe={len(uni)} usable={len(series)} tip={tip} "
          f"load={time.time() - t0:.1f}s", flush=True)

    max_lag = int(c["max_lag_sessions"])
    fresh: list[str] = []
    recs: dict[str, dict[str, Any]] = {}
    import pandas as pd  # noqa: PLC0415
    for tkr, s in series.items():
        lag = AP.session_lag(str(pd.Timestamp(s.index[-1]).date()), tip)
        if lag > max_lag:
            recs[tkr] = AP.stale_record(tkr, s, lag)
            skipped["stale_series"] = skipped.get("stale_series", 0) + 1
        else:
            fresh.append(tkr)

    nw = _workers(workers)
    gate_calls = 0
    t_centre = t_probe = time.time()
    centre_s = probe_s = 0.0
    wanted = 0
    probes: dict[str, dict[str, Any]] = {}
    ex = ProcessPoolExecutor(max_workers=nw, initializer=_winit, initargs=(c,))
    try:
        for rec in ex.map(_centre, fresh, chunksize=16):
            recs[rec["ticker"]] = rec
            gate_calls += rec["gate_calls"]
            if rec.get("skip"):
                skipped[rec["skip"]] = skipped.get(rec["skip"], 0) + 1
        centre_s = time.time() - t_centre
        wanted = sum(1 for r in recs.values() if r.get("wants_probe"))
        order = AP.order_probes(recs, c, skipped)
        print(f"prophet-live pack: centre census {len(fresh)} names in {centre_s:.1f}s "
              f"({gate_calls} gate calls, {nw} workers) — wants_probe={wanted} "
              f"queued={len(order)}", flush=True)

        # DEADLINE, not just a count. Gate cost swings ~10x with history depth, so a
        # name cap alone cannot bound the step; whatever does not finish in time is
        # cancelled and disclosed rather than allowed to eat the render budget.
        deadline = float(c["max_seconds"])
        t_probe = time.time()
        payloads = [(t, {"span": recs[t]["span"], "known": recs[t].get("known") or {}})
                    for t in order]
        futs = {ex.submit(_probe, p): p[0] for p in payloads}
        timed_out = False
        try:
            for fut in as_completed(futs, timeout=max(1.0, deadline)):
                tkr, res = fut.result()
                probes[tkr] = res
                gate_calls += res["gate_calls"]
                if res.get("irregular"):
                    skipped["irregular"] = skipped.get("irregular", 0) + 1
        except TimeoutError:
            timed_out = True
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=prophet-live-pack::probe phase error: {exc}", flush=True)
        if timed_out:
            unfinished = len(futs) - len(probes)
            skipped["deadline"] = skipped.get("deadline", 0) + unfinished
            print(f"::warning title=prophet-live-pack::probe phase hit the "
                  f"{deadline:.0f}s budget with {unfinished} names unprobed "
                  "(disclosed as meta.skipped.deadline)", flush=True)
    finally:
        # cancel_futures so a deadline does not then wait out the whole queue.
        ex.shutdown(wait=False, cancel_futures=True)
    probe_s = time.time() - t_probe

    names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}
    payload = AP.assemble(names, as_of=tip or "", cfg=c, universe_n=len(uni),
                          wanted_n=wanted, gate_calls=gate_calls,
                          build_seconds=time.time() - t0, skipped=skipped, now=now)
    payload["meta"]["phase_seconds"] = {"load": round(t_centre - t0, 1),
                                        "centre": round(centre_s, 1),
                                        "probe": round(probe_s, 1)}
    payload["meta"]["workers"] = nw
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build (and optionally publish) the Prophet Live armed pack.")
    parser.add_argument("--publish", action="store_true",
                        help=f"upload to R2 key {r2io.PACK_KEY}")
    parser.add_argument("--out", default=None, help="also write the payload to this path")
    parser.add_argument("--now", default=None,
                        help="ISO timestamp override for built_at (tests / replays)")
    parser.add_argument("--workers", type=int, default=None,
                        help="process-pool size (default: the stock library's own policy)")
    parser.add_argument("--limit", type=int, default=None,
                        help="probe only the first N universe names (smoke runs)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    now: datetime | None = None
    if args.now:
        try:
            now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            print(f"::error title=prophet-live-pack::unparseable --now {args.now!r}",
                  flush=True)
            return 2
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

    try:
        cfg = None
        try:
            from lib import config  # noqa: PLC0415
            cfg = config.load()
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=prophet-live-pack::config.yml unreadable ({exc}) "
                  "— in-code defaults", flush=True)
        payload = build(cfg=cfg, now=now, workers=args.workers, limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"::error title=prophet-live-pack::build failed: {exc}", flush=True)
        log.warning("build_prophet_live_pack: unexpected failure", exc_info=True)
        return 1

    m = payload["meta"]
    print(f"prophet-live pack: as_of={payload['as_of']} universe_n={m['universe_n']} "
          f"probed_n={m['probed_n']} armed_n={m['armed_n']} "
          f"gate_calls={m['gate_calls']} build_seconds={m['build_seconds']} "
          f"phases={m.get('phase_seconds')} states={m['states']} skipped={m['skipped']}",
          flush=True)

    if not payload["as_of"]:
        print("::error title=prophet-live-pack::no as_of — the close stores produced "
              "no dated bar; refusing to publish an undatable pack", flush=True)
        return 1

    bad = AP.self_check(payload["names"])
    if bad:
        for line in bad[:20]:
            print(f"prophet-live parity mismatch: {line}", flush=True)
        print(f"::error title=prophet-live-pack-parity::{len(bad)} mismatches between "
              "the published interval and tonight's gate verdict — pack NOT published",
              flush=True)
        return 1
    print(f"prophet-live pack: parity clean over {m['probed_n']} probed names",
          flush=True)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")),
                     encoding="utf-8")
        print(f"prophet-live pack: wrote {p} ({p.stat().st_size} bytes)", flush=True)

    if args.publish:
        if not r2io.put_json(r2io.PACK_KEY, payload):
            print("::warning title=prophet-live-pack::R2 publish failed or "
                  "credentials absent — the evaluator will dark on no_pack", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
