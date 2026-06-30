"""Merge cycle-cause-research workflow output → narratives.json + cycle_dna.json (both regions).

Input: one or more JSON files, each {region, bucket, results:[ <finalized series object>, ... ]}
where a series object = {key, now, now_zh, legs:[{date,title,body,drivers,*_zh}], dna:{...}}.

INCREMENTAL + idempotent: loads the existing narratives/dna docs, updates ONLY the series present
in the input (so the US recent-leg narratives and any not-yet-researched bucket survive across the
four per-bucket workflow runs), and writes back. Pure data assembly — no engine calls.

Usage: python -m scripts.assemble_cycle_research <results1.json> [results2.json ...]
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from lib import config

log = logging.getLogger("assemble_cycle_research")

PATHS = {
    "us": {"narr": "data/sector_cycles/narratives.json", "dna": "data/sector_cycles/cycle_dna.json"},
    "china": {"narr": "data/china_sector_cycles/narratives.json", "dna": "data/china_sector_cycles/cycle_dna.json"},
}

_LEG_FIELDS = ("title", "body", "drivers", "title_zh", "body_zh", "drivers_zh")


def _load(p: Path, default: dict) -> dict:
    if not p.exists():
        return dict(default)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else dict(default)
    except Exception as e:  # noqa: BLE001
        log.warning("unreadable %s (%s) — starting fresh", p, e)
        return dict(default)


def _legs_obj(legs: list) -> dict:
    out = {}
    for lg in legs or []:
        date = lg.get("date")
        if not date:
            continue
        out[date] = {k: lg.get(k) for k in _LEG_FIELDS if lg.get(k) is not None}
    return out


def main() -> int:
    if len(sys.argv) < 2:
        log.error("usage: assemble_cycle_research <results.json> ...")
        return 1
    root = Path(config.ROOT)

    # cache docs per region so multiple input files for one region accumulate
    narr_docs: dict[str, dict] = {}
    dna_docs: dict[str, dict] = {}
    touched: dict[str, int] = {}

    for arg in sys.argv[1:]:
        env = json.loads(Path(arg).read_text(encoding="utf-8"))
        region, bucket = env["region"], env["bucket"]      # bucket ∈ {sectors, baskets}
        results = env.get("results") or []
        np_ = root / PATHS[region]["narr"]
        dp_ = root / PATHS[region]["dna"]
        narr = narr_docs.setdefault(region, _load(np_, {
            "version": "2026-06-28-15y", "note": "15y cycle-cause narratives, keyed by the START turn's date "
            "(also accepts YYYY-MM). Front-loaded research against engine turns.", "sectors": {}, "baskets": {}}))
        dna = dna_docs.setdefault(region, _load(dp_, {
            "version": "2026-06-28-15y", "note": "Per-series cycle-DNA (recurring causes, top/bottom signals, "
            "median cycle, current analog) — the predictive 'history rhymes' layer.", "sectors": {}, "baskets": {}}))
        narr.setdefault(bucket, {})
        dna.setdefault(bucket, {})
        for r in results:
            key = r.get("key")
            if not key:
                continue
            narr[bucket][key] = {"now": r.get("now"), "now_zh": r.get("now_zh"), "legs": _legs_obj(r.get("legs"))}
            if r.get("dna"):
                dna[bucket][key] = r["dna"]
            touched[region] = touched.get(region, 0) + 1

    for region, narr in narr_docs.items():
        np_ = root / PATHS[region]["narr"]
        np_.parent.mkdir(parents=True, exist_ok=True)
        np_.write_text(json.dumps(narr, ensure_ascii=False, indent=1), encoding="utf-8")
        dp_ = root / PATHS[region]["dna"]
        dp_.write_text(json.dumps(dna_docs[region], ensure_ascii=False, indent=1), encoding="utf-8")
        ns = sum(len(narr.get(b, {})) for b in ("sectors", "baskets"))
        nl = sum(len(v.get("legs", {})) for b in ("sectors", "baskets") for v in narr.get(b, {}).values())
        log.info("%s: wrote %s (%d series, %d legs) + %s", region, np_, ns, nl, dp_.name)
    log.info("touched: %s", touched)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
