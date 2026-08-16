"""scripts/build_cn_live_pack.py — the mainland arming pass (CN-PR-1, spec §4).

Probes the SAME close-only admission gate the China board is built from, with candidate
provisional closes APPENDED as the next MAINLAND session's bar, and publishes the
resulting per-name trigger/fade levels to R2 as ``live_flow/cn_prophet_live_armed.json``.
The next session's 5-minute lane reads that and never re-derives a signal. All compute
lives in :mod:`engine.prophet_live.cn_pack` (which drives
:mod:`engine.prophet_live.armed_pack`); this script owns the universe read, the process
fan-out, the budget deadline and the publish.

    python -m scripts.build_cn_live_pack [--publish] [--out PATH] [--now ISO]
                                         [--workers N] [--limit N]

WHERE IT RUNS. A new step in ``asia-close.yml`` AFTER the library rebuild (so the store
is fresh), ``timeout-minutes: 12``, ``continue-on-error: true``. ADVISORY LANE: its
failure must never red settlement, and its ABSENCE is not silent — the evaluator's
``stale_pack`` honesty catches a missing or N-2 pack the next morning and darks the
whole artifact rather than evaluating today's tape against stale thresholds.

LANE LAW. Writes NOTHING under ``data/`` and commits nothing. One R2 key plus an
optional ``--out`` local copy for the reconciler. ``CN_PROPHET_LIVE_NO_PUBLISH=1``
refuses the publish (and is separate from the US switch).

BUDGET IS LAW. One gate call is ~312 ms on this universe (measured 2026-08-15 on the
real store: 1,711 non-ETF names), so the centre census alone is ~535 CPU-seconds and a
full grid over every name is far past what asia-close can spend. The census is always
paid; the probe phase then runs under BOTH ``max_probe`` (180) and a wall-clock
``max_seconds`` (420), and everything the budget cuts is counted in ``meta.skipped`` —
never silently relabelled dormant.

FAIL-CLOSED ON PARITY (G0.1, inherited). Before anything is published the REAL gate is
re-run at every PUBLISHED price, through the SAME appended-bar construction on the SAME
mainland calendar the edge was measured on. A name the gate contradicts, or one that
could not be checked inside the budget, has its thresholds WITHHELD: it ships its honest
centre state with no levels and the evaluator drops it from coverage. Per NAME — one
boundary case must not dark every other name. Whole-pack refusal is reserved for
structural failures: no ``as_of`` at all, or armed levels with zero re-verified prices
(unproven is not clean).
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
sys.path.insert(0, _CODE_ROOT)

from engine.prophet_live import armed_pack as AP  # noqa: E402
from engine.prophet_live import cn_pack as CP  # noqa: E402
from engine.prophet_live import cn_states as CS  # noqa: E402
from lib import cn_calendar  # noqa: E402

log = logging.getLogger("build_cn_live_pack")

#: Share of the wall-clock budget the probe phase may spend. The remainder is RESERVED
#: for edge verification, because an unverified level is WITHHELD rather than published
#: — so letting the probe consume everything would silently shrink the armed set
#: instead of trading a little coverage for proof.
PROBE_SHARE = 0.75

#: Worker-local state, populated once per process.
_CLOSES: dict[str, Any] = {}
_CFG: dict[str, Any] = {}
_GATE = None


def _winit(cfg: dict[str, Any], keep: list[str] | None) -> None:  # pragma: no cover - subprocess
    """Load the CN universe + the T2 latch into this worker.

    The LATCH IS BUILT PER WORKER and read-only. It cannot be pickled across the pool
    boundary cheaply and it must exist on every gate call (spec §4 — pack-side latch
    discipline is mandatory, because the evaluator never calls ``gate()`` and so has no
    second chance to apply it).
    """
    global _CFG, _GATE
    _CFG = cfg
    keep_set = set(keep or [])
    for tkr, close, _name, _sector in CP.universe_rows():
        if keep_set and tkr not in keep_set:
            continue
        s = AP.clean_closes(close)
        if s is not None and len(s) >= 2:
            _CLOSES[tkr] = s
    _GATE = CP.gate_factory(CP.load_latch())


def _centre(tkr: str) -> dict[str, Any]:  # pragma: no cover - subprocess path
    """Phase 1 task: tonight's verdict + the span a probe would sweep for THIS name."""
    rec = AP.centre_record(tkr, _CLOSES[tkr], cfg=CP.name_cfg(_CFG, tkr), gate_fn=_GATE)
    # The raw analyze() payload is large and can carry NaN; the pack never uses it and
    # pickling it back would dominate the phase's IPC cost.
    v = rec.get("center_verdict") or {}
    rec["center_verdict"] = {k: v.get(k) for k in
                             ("eligible", "tier", "sub", "tier_cascade", "ticks",
                              "bars_to_cross", "hist_d2", "hist_d3", "provisional",
                              "near_miss_reason")}
    return rec


def _probe(args: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:  # pragma: no cover
    """Phase 2 task: grid + bisection over the name's daily-limit span."""
    tkr, rec = args
    return tkr, AP.probe_name(tkr, _CLOSES[tkr], rec, cfg=CP.name_cfg(_CFG, tkr),
                              gate_fn=_GATE, calendar=cn_calendar)


def _verify(args: tuple[str, list]) -> tuple[str, list[str], int]:  # pragma: no cover
    """Phase 3 task: re-run the real gate at this name's published edges."""
    tkr, checks = args
    lines, n = AP.verify_edges(tkr, _CLOSES[tkr], checks, gate_fn=_GATE,
                               calendar=cn_calendar)
    return tkr, lines, n


def _drain(futs: dict, timeout: float, label: str):
    """Yield ``(result, False)`` per completed future, then ``(None, True)`` on timeout.

    One drain for all three phases so the budget is enforced identically. A phase that
    runs out of time is DISCLOSED (the caller records a skipped reason) — never allowed
    to overrun, because asia-close's own cap is what silently drops the whole step.
    """
    if not futs:
        return
    try:
        for fut in as_completed(futs, timeout=max(1.0, timeout)):
            yield fut.result(), False
    except TimeoutError:
        print(f"::warning title=cn-prophet-pack::{label} hit the {timeout:.0f}s "
              "remaining budget — unfinished names are disclosed in meta.skipped",
              flush=True)
        yield None, True
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=cn-prophet-pack::{label} error: {exc}", flush=True)


def _workers(explicit: int | None) -> int:
    """Pool size. Reuses the stock library's own policy so the passes agree."""
    if explicit:
        return max(1, int(explicit))
    try:
        from scripts.build_stock_library import _library_workers  # noqa: PLC0415
        return _library_workers()
    except Exception:  # noqa: BLE001
        return max(1, min(os.cpu_count() or 1, 8))


def build(*, cfg: dict[str, Any] | None = None, now: datetime | None = None,
          workers: int | None = None, limit: int | None = None,
          root: Path | None = None) -> dict[str, Any]:
    """Run all three phases across a process pool and return the assembled payload."""
    c = CP.cn_pack_cfg(cfg)
    t0 = time.time()
    rows = CP.universe_rows(limit=limit)
    tickers = [t for (t, *_r) in rows]
    frozen = CP.frozen_context(CP.load_standouts(root or Path(_CODE_ROOT)))
    adjustment = CP.price_adjustment(tickers)

    series: dict[str, Any] = {}
    skipped: dict[str, int] = {}
    for tkr, close, _name, _sector in rows:
        s = AP.clean_closes(close)
        if s is None or len(s) < 2:
            skipped["no_series"] = skipped.get("no_series", 0) + 1
            continue
        series[tkr] = s
    tip = AP.as_of_date(series.values())
    print(f"cn-prophet pack: universe={len(rows)} usable={len(series)} tip={tip} "
          f"frozen_ctx={len(frozen)} load={time.time() - t0:.1f}s", flush=True)

    import pandas as pd  # noqa: PLC0415
    max_lag = int(c["max_lag_sessions"])
    fresh: list[str] = []
    recs: dict[str, dict[str, Any]] = {}
    for tkr, s in series.items():
        lag = AP.session_lag(str(pd.Timestamp(s.index[-1]).date()), tip, cn_calendar)
        if lag > max_lag:
            # A suspended A-share is an ORDINARY event here, not a dead series — it
            # ships its centre state marked stale and unprobed, and comes back on its
            # own when the tape does.
            recs[tkr] = AP.stale_record(tkr, s, lag)
            skipped["stale_series"] = skipped.get("stale_series", 0) + 1
        else:
            fresh.append(tkr)

    nw = _workers(workers)
    gate_calls = 0
    t_centre = t_probe = t_verify = time.time()
    centre_s = probe_s = verify_s = 0.0
    wanted = 0
    probes: dict[str, dict[str, Any]] = {}
    edges = 0
    bad: list[str] = []
    checks: dict[str, list] = {}
    verified: set[str] = set()
    mismatched: set[str] = set()
    probe_seconds: dict[str, float] = {}
    deadline = float(c["max_seconds"])
    ex = ProcessPoolExecutor(max_workers=nw, initializer=_winit,
                             initargs=(c, tickers if limit else None))
    try:
        cfuts = {ex.submit(_centre, t): t for t in fresh}
        for rec, timed_out in _drain(cfuts, deadline, "centre census"):
            if timed_out:
                missed = [t for t in fresh if t not in recs]
                for t in missed:
                    recs[t] = AP.stale_record(t, series[t], 0)
                    recs[t]["skip"] = "census_deadline"
                skipped["census_deadline"] = len(missed)
                break
            recs[rec["ticker"]] = rec
            gate_calls += rec["gate_calls"]
            if rec.get("skip"):
                skipped[rec["skip"]] = skipped.get(rec["skip"], 0) + 1
        centre_s = time.time() - t_centre
        wanted = sum(1 for r in recs.values() if r.get("wants_probe"))
        split = AP.split_probes(recs, c, skipped)
        print(f"cn-prophet pack: centre census {len(fresh)} names in {centre_s:.1f}s "
              f"({gate_calls} gate calls, {nw} workers) — wants_probe={wanted} "
              f"queued board={len(split['board'])} cross={len(split['cross'])}",
              flush=True)

        t_probe = time.time()
        probe_budget = deadline * PROBE_SHARE - (time.time() - t_centre)
        board_win, cross_floor = AP.class_windows(probe_budget, c["board_probe_share"])
        print(f"cn-prophet pack: probe budget {probe_budget:.0f}s -> board "
              f"{board_win:.0f}s, cross floor {cross_floor:.0f}s "
              f"(board_probe_share={c['board_probe_share']})", flush=True)

        for cls, window in (("board", board_win), ("cross", None)):
            names_for = split[cls]
            if not names_for:
                probe_seconds[cls] = 0.0
                continue
            t_cls = time.time()
            win = window if window is not None else AP.cross_window(
                probe_budget, c["board_probe_share"], time.time() - t_probe)
            payloads = [(t, {"span": recs[t]["span"],
                             "as_of_close": recs[t]["as_of_close"]})
                        for t in names_for]
            futs = {ex.submit(_probe, p): p[0] for p in payloads}
            done_before = len(probes)
            for res, timed_out in _drain(futs, win, f"{cls} probe slice"):
                if timed_out:
                    unfinished = len(futs) - (len(probes) - done_before)
                    key = f"deadline_{cls}"
                    skipped[key] = skipped.get(key, 0) + unfinished
                    break
                tkr, r = res
                probes[tkr] = r
                gate_calls += r["gate_calls"]
                if r.get("irregular"):
                    skipped["irregular"] = skipped.get("irregular", 0) + 1
            probe_seconds[cls] = time.time() - t_cls
            print(f"cn-prophet pack: {cls} slice {len(probes) - done_before}/"
                  f"{len(futs)} probed in {probe_seconds[cls]:.1f}s (window {win:.0f}s)",
                  flush=True)
        probe_s = time.time() - t_probe

        # PHASE 3 — the independent parity gate. Re-runs the REAL gate at every
        # PUBLISHED edge and at the false-side bound the bisection measured, on the
        # SAME mainland calendar. This is the check that can actually fail.
        t_verify = time.time()
        names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}
        checks = {t: AP.edge_checks(e, probes.get(t)) for t, e in names.items()}
        checks = {t: v for t, v in checks.items() if v}
        vfuts = {ex.submit(_verify, (t, v)): t for t, v in checks.items()}
        left = deadline - (time.time() - t_centre)
        for res, timed_out in _drain(vfuts, left, "edge verification"):
            if timed_out:
                break
            tkr, lines, n = res
            if lines:
                bad.extend(lines)
                mismatched.add(tkr)
            verified.add(tkr)
            edges += n
            gate_calls += n
        verify_s = time.time() - t_verify
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    def _withhold(tickers_: set[str], reason: str) -> None:
        """Drop one name's thresholds, keep its honest centre state."""
        tickers_ = {t for t in tickers_ if t in recs}
        if not tickers_:
            return
        for t in tickers_:
            probes.pop(t, None)
            recs[t]["skip"] = reason
            recs[t]["wants_probe"] = False
        skipped[reason] = skipped.get(reason, 0) + len(tickers_)
        print(f"::warning title=cn-prophet-pack::{len(tickers_)} names withheld "
              f"({reason}) — their thresholds are not published "
              f"(meta.skipped.{reason})", flush=True)

    _withhold(set(checks) - verified, "unverified")
    _withhold(mismatched, "edge_mismatch")
    names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}
    mem_bad = AP.membership_mismatches(names)
    if mem_bad:
        bad.extend(mem_bad.values())
        _withhold(set(mem_bad), "membership_mismatch")
        names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}

    payload = CP.assemble(names, as_of=tip or "", cfg=c, universe_n=len(rows),
                          wanted_n=wanted, gate_calls=gate_calls, edges_checked=edges,
                          probe_seconds=probe_seconds, frozen=frozen,
                          adjustment=adjustment,
                          build_seconds=time.time() - t0, skipped=skipped, now=now)
    payload["meta"]["phase_seconds"] = {"load": round(t_centre - t0, 1),
                                        "centre": round(centre_s, 1),
                                        "probe": round(probe_s, 1),
                                        "verify": round(verify_s, 1)}
    payload["meta"]["workers"] = nw
    payload["meta"]["edge_mismatches"] = bad
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build (and optionally publish) the CN Prophet Live armed pack.")
    parser.add_argument("--publish", action="store_true",
                        help=f"upload to R2 key {CS.CN_PACK_KEY}")
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
            print(f"::error title=cn-prophet-pack::unparseable --now {args.now!r}",
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
            print(f"::warning title=cn-prophet-pack::config.yml unreadable ({exc}) "
                  "— in-code defaults", flush=True)
        payload = build(cfg=cfg, now=now, workers=args.workers, limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"::error title=cn-prophet-pack::build failed: {exc}", flush=True)
        log.warning("build_cn_live_pack: unexpected failure", exc_info=True)
        return 1

    m = payload["meta"]
    print(f"cn-prophet pack: as_of={payload['as_of']} universe_n={m['universe_n']} "
          f"probed_n={m['probed_n']} armed_n={m['armed_n']} "
          f"center_flips={m.get('probe_center_flips')} frozen_n={m.get('frozen_n')} "
          f"gate_calls={m['gate_calls']} build_seconds={m['build_seconds']} "
          f"phases={m.get('phase_seconds')} limit_classes={payload['limit_classes']} "
          f"states={m['states']} skipped={m['skipped']}", flush=True)
    for cls, cc in (m.get("by_class") or {}).items():
        print(f"cn-prophet pack: class {cls}: candidates={cc['candidates_n']} "
              f"probed={cc['probed_n']} armed={cc['armed_n']} "
              f"probe_seconds={cc['probe_seconds']}", flush=True)

    if not payload["as_of"]:
        print("::error title=cn-prophet-pack::no as_of — the close stores produced no "
              "dated bar; refusing to publish an undatable pack", flush=True)
        return 1

    for line in (CP.sanity(payload) or [])[:20]:
        print(f"::warning title=cn-prophet-pack::structural: {line}", flush=True)

    bad = list(m.get("edge_mismatches") or [])
    for line in bad[:20]:
        print(f"cn-prophet parity mismatch (levels withheld): {line}", flush=True)
    if bad:
        print(f"::warning title=cn-prophet-pack-parity::{len(bad)} names disagreed with "
              "the live gate at a published price — those names ship with NO thresholds "
              "(meta.skipped.edge_mismatch / .membership_mismatch)", flush=True)
    residual = AP.self_check(payload["names"])
    if residual:
        for line in residual[:20]:
            print(f"cn-prophet residual mismatch: {line}", flush=True)
        print(f"::error title=cn-prophet-pack-parity::{len(residual)} mismatches "
              "survived the per-name withholding — pack NOT published", flush=True)
        return 1

    armed = int(m["armed_n"])
    if armed and not m.get("edges_checked"):
        # Unproven is not clean.
        print(f"::error title=cn-prophet-pack-parity::{armed} armed names but 0 "
              "published prices were re-verified against the gate — pack NOT published",
              flush=True)
        return 1
    print(f"cn-prophet pack: {m['edges_checked']} published prices re-verified against "
          f"the live gate across {armed} armed names, 0 mismatches; membership check "
          f"clean over {m['probed_n']} probed names", flush=True)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")),
                     encoding="utf-8")
        print(f"cn-prophet pack: wrote {p} ({p.stat().st_size} bytes)", flush=True)

    if args.publish:
        if not CS.publish_json(CS.CN_PACK_KEY, payload):
            print("::warning title=cn-prophet-pack::R2 publish failed, refused or "
                  "credentials absent — the evaluator will dark on no_pack", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
