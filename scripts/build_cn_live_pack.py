"""scripts/build_cn_live_pack.py — CN armed-pack driver (CN-PR-1, spec §4).

Runs AFTER the china library rebuild in asia-close (wired in CN-PR-2). Advisory:
``continue-on-error: true`` — a miss is ``stale_pack`` on the next session, never
a red settlement.

    python -m scripts.build_cn_live_pack [--publish] [--out PATH] [--now ISO]
                                         [--limit N]

Universe = ``build_china_library.universe()`` minus Sector ETF / Index, through
``stock_tradability_ok`` when maps are supplied. Probe uses the CN calendar and
the per-class daily-limit band. T2 latch is loaded read-only.

FAIL-CLOSED ON PARITY (G0.1 inherited): unpublished / mismatched edges are
withheld per name, never silently shipped.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _CODE_ROOT)

from engine.prophet_live import cn_pack as CP  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402
from engine.prophet_live import armed_pack as AP  # noqa: E402

log = logging.getLogger("build_cn_live_pack")


def _now(raw: str | None) -> datetime | None:
    if not raw:
        return None
    t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def load_frozen(root: Path) -> dict[str, dict[str, Any]]:
    """Nightly board rows keyed by ticker. Missing file → empty (fail-open)."""
    for rel in ("site/china_standouts.json", "data/china_standouts.json"):
        p = root / rel
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=cn-live-pack::frozen board {p} unreadable ({exc})",
                  flush=True)
            continue
        out: dict[str, dict[str, Any]] = {}
        lanes = doc.get("lanes") if isinstance(doc, dict) else None
        if isinstance(lanes, dict):
            for lane, rows in lanes.items():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    tkr = str(row.get("ticker") or row.get("symbol") or "")
                    if not tkr:
                        continue
                    blob = dict(row)
                    blob.setdefault("lane", lane)
                    out[tkr] = blob
        elif isinstance(doc, dict):
            for tkr, row in (doc.get("names") or doc.get("rows") or {}).items():
                if isinstance(row, dict):
                    out[str(tkr)] = row
        if out:
            return out
    return {}


def build(*, root: Path | None = None, cfg: dict[str, Any] | None = None,
          now: datetime | None = None, limit: int | None = None,
          series: dict[str, Any] | None = None,
          gate_fn=None, frozen: dict[str, dict[str, Any]] | None = None,
          tradable: dict[str, bool] | None = None) -> dict[str, Any]:
    """Assemble the CN armed pack. ``series`` injects a test universe."""
    from lib import cn_calendar  # noqa: PLC0415

    t0 = time.time()
    c = CP.pack_cfg(cfg)
    root = root or Path(_CODE_ROOT)
    skipped: dict[str, int] = {}

    if series is None:
        from scripts.build_china_library import universe  # noqa: PLC0415
        rows = CP.filter_universe(universe())
        if tradable:
            rows = [r for r in rows if tradable.get(r[0], True)]
        series = {}
        for row in rows:
            tkr, close = row[0], row[1]
            s = AP.clean_closes(close)
            if s is None or len(s) < 2:
                skipped["no_series"] = skipped.get("no_series", 0) + 1
                continue
            series[tkr] = s
    else:
        series = {t: AP.clean_closes(s) for t, s in series.items()}
        series = {t: s for t, s in series.items() if s is not None and len(s) >= 2}

    if limit:
        series = dict(list(series.items())[: int(limit)])

    tip = AP.as_of_date(series.values())
    g = gate_fn or CP.make_cn_gate()
    if frozen is None:
        frozen = load_frozen(root)

    recs: dict[str, dict[str, Any]] = {}
    probes: dict[str, dict[str, Any]] = {}
    gate_calls = 0
    max_lag = int(c.get("max_lag_sessions") or 2)
    import pandas as pd  # noqa: PLC0415
    for tkr, s in series.items():
        lag = AP.session_lag(str(pd.Timestamp(s.index[-1]).date()), tip,
                             calendar=cn_calendar)
        if lag > max_lag:
            recs[tkr] = AP.stale_record(tkr, s, lag)
            skipped["stale_series"] = skipped.get("stale_series", 0) + 1
            continue
        rec = CP.centre_record(tkr, s, cfg=c, gate_fn=g)
        recs[tkr] = rec
        gate_calls += int(rec.get("gate_calls") or 0)
        if rec.get("skip"):
            skipped[rec["skip"]] = skipped.get(rec["skip"], 0) + 1

    wanted = [t for t, r in recs.items() if r.get("wants_probe")]
    wanted.sort(key=lambda t: AP.probe_priority(recs[t]))
    cap = int(c.get("max_probe") or 180)
    to_probe = wanted[:cap]
    if len(wanted) > cap:
        skipped["probe_cap"] = len(wanted) - cap
        for t in wanted[cap:]:
            recs[t]["skip"] = "probe_cap"
            recs[t]["wants_probe"] = False

    for tkr in to_probe:
        r = CP.probe_name(tkr, series[tkr], recs[tkr], cfg=c, gate_fn=g)
        probes[tkr] = r
        gate_calls += int(r.get("gate_calls") or 0)
        if r.get("irregular"):
            skipped["irregular"] = skipped.get("irregular", 0) + 1

    names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}
    checks = {t: AP.edge_checks(e, probes.get(t)) for t, e in names.items()}
    checks = {t: v for t, v in checks.items() if v}
    edges = 0
    mismatched: set[str] = set()
    verified: set[str] = set()
    bad: list[str] = []
    for tkr, chk in checks.items():
        lines, n = CP.verify_edges(tkr, series[tkr], chk, gate_fn=g)
        edges += n
        gate_calls += n
        verified.add(tkr)
        if lines:
            bad.extend(lines)
            mismatched.add(tkr)

    def _withhold(tickers: set[str], reason: str) -> None:
        tickers = {t for t in tickers if t in recs}
        if not tickers:
            return
        for t in tickers:
            probes.pop(t, None)
            recs[t]["skip"] = reason
            recs[t]["wants_probe"] = False
        skipped[reason] = skipped.get(reason, 0) + len(tickers)

    _withhold(set(checks) - verified, "unverified")
    _withhold(mismatched, "edge_mismatch")
    names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}
    mem_bad = AP.membership_mismatches(names)
    if mem_bad:
        bad.extend(mem_bad.values())
        _withhold(set(mem_bad), "membership_mismatch")
        names = {t: AP.name_entry(r, probes.get(t)) for t, r in recs.items()}

    payload = CP.assemble(
        names, as_of=tip or "", cfg=c, universe_n=len(series),
        wanted_n=len(wanted), gate_calls=gate_calls,
        build_seconds=time.time() - t0, skipped=skipped,
        edges_checked=edges, frozen=frozen, now=now,
    )
    payload["meta"]["edge_mismatches"] = bad
    print(f"cn-live pack: universe={len(series)} probed={payload['meta']['probed_n']} "
          f"armed={payload['meta']['armed_n']} tip={tip} "
          f"{payload['meta']['build_seconds']}s", flush=True)
    return payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--now", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--root", default=_CODE_ROOT)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    try:
        cfg = None
        try:
            from lib import config  # noqa: PLC0415
            cfg = config.load()
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=cn-live-pack::config.yml unreadable ({exc})",
                  flush=True)
        payload = build(root=Path(args.root), cfg=cfg, now=_now(args.now),
                        limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"::error title=cn-live-pack::{exc}", flush=True)
        return 1
    if args.out:
        Path(args.out).write_text(json.dumps(payload, allow_nan=False, indent=2),
                                  encoding="utf-8")
    if args.publish:
        if not r2io.put_json(r2io.CN_PACK_KEY, payload):
            print("::warning title=cn-live-pack::R2 publish failed — pack stays local",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
