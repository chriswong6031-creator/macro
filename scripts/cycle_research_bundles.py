"""Assemble per-series RESEARCH-INPUT bundles for the 15y cycle-cause research pass.

For every US/China sector & basket cycle record it joins: the engine's dated turns/legs
(engine.sector_cycles / engine.china_sector_cycles at the live 15y window), the cross-asset
ROTATION grounding per leg (data/{sector_cycles,china_sector_cycles}/leg_context.json), the
current state, and any EXISTING researched narrative (US, to preserve/improve recent legs).

Writes one compact bundle per series to <out>/bundles/<region>__<bucket>__<key>.json plus a
<out>/manifest.json the research workflow fans out over. Each research agent reads ONE bundle
file (no giant args, no worktree write-contention) and returns the EN+ZH cause narrative for
every leg + a per-series "cycle DNA" profile.

Usage: python -m scripts.cycle_research_bundles [out_dir]   (default /tmp/cycle_research)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from lib import config

log = logging.getLogger("cycle_research_bundles")


def _legs_from_turns(turns: list[dict], ctxmap: dict) -> list[dict]:
    """Ordered leg list start→end with magnitude, major flag, and the leg_context ctx."""
    legs = []
    for i in range(len(turns) - 1):
        a, b = turns[i], turns[i + 1]
        lc = (ctxmap.get("legs") or {}).get(a["date"]) or {}
        legs.append({
            "start": a["date"], "end": b["date"],
            "dir": "rally" if b["k"] == "peak" else "selloff",
            "mag_pct": b.get("mag_pct"), "major": bool(b.get("major")),
            "start_kind": a["k"], "end_kind": b["k"],
            "ctx": lc.get("ctx") or {},
        })
    return legs


def _bundle(rec: dict, region: str, bucket: str, key: str, ctxmap: dict,
            existing: dict | None, benchmark: str, as_of: str) -> dict:
    turns = rec.get("turns") or []
    nw = rec.get("now") or {}
    span = [turns[0]["date"], as_of] if turns else [None, as_of]
    out = {
        "key": key, "region": region, "bucket": bucket, "id": rec.get("id"),
        "name": rec.get("name"), "name_zh": rec.get("name_zh"),
        "group": rec.get("group"), "group_zh": rec.get("group_zh"),
        "kind": rec.get("kind"), "benchmark": benchmark, "as_of": as_of, "span": span,
        "current": {
            "phase": nw.get("phase"), "phaseLabel": nw.get("phaseLabel"),
            "pos": nw.get("pos"), "rs_rank": nw.get("rs_rank"), "signal": nw.get("signal"),
            "above200d": nw.get("above200d"), "ret_win_pct": nw.get("ret_win_pct"),
            "now_ctx": ctxmap.get("now_ctx") or {},
        },
        "n_legs": max(0, len(turns) - 1),
        "legs": _legs_from_turns(turns, ctxmap),
    }
    if rec.get("thesis"):
        out["thesis"] = rec.get("thesis")
    if existing:
        out["existing_now"] = existing.get("now")
        out["existing_legs"] = existing.get("legs") or {}
    return out


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/cycle_research")
    bdir = out_dir / "bundles"
    bdir.mkdir(parents=True, exist_ok=True)

    from engine import sector_cycles as sc
    from engine import china_sector_cycles as ccc

    root = Path(config.ROOT)
    us_ctx = json.loads((root / "data" / "sector_cycles" / "leg_context.json").read_text())
    cn_ctx = json.loads((root / "data" / "china_sector_cycles" / "leg_context.json").read_text())
    us_narr = json.loads((root / "data" / "sector_cycles" / "narratives.json").read_text())

    manifest = []

    def emit(rec, region, bucket, key, ctxmap, existing, bench, as_of):
        b = _bundle(rec, region, bucket, key, ctxmap.get(rec["id"], {}), existing, bench, as_of)
        p = bdir / f"{region}__{bucket}__{key}.json"
        p.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest.append({"key": key, "region": region, "bucket": bucket, "id": rec["id"],
                         "name": rec.get("name"), "n_legs": b["n_legs"], "path": str(p)})

    # ---- US ----
    du = sc.compute()
    as_of_us = du["meta"]["asOf"]
    for s in du["sectors"]:
        key = s["id"]                                   # "xlk"
        emit(s, "us", "sectors", key, us_ctx, (us_narr.get("sectors") or {}).get(key), "SPY", as_of_us)
    for b in du["baskets"]:
        key = b["id"][2:] if b["id"].startswith("b-") else b["id"]   # bare basket id
        emit(b, "us", "baskets", key, us_ctx, (us_narr.get("baskets") or {}).get(key), "SPY", as_of_us)

    # ---- China ----
    dc = ccc.compute()
    as_of_cn = dc["meta"]["asOf"]
    for s in dc["sectors"]:
        emit(s, "china", "sectors", s["id"], cn_ctx, None, "SHCOMP", as_of_cn)   # key = Shenwan code
    for b in dc["baskets"]:
        key = b["id"][2:] if b["id"].startswith("b-") else b["id"]
        emit(b, "china", "baskets", key, cn_ctx, None, "SHCOMP", as_of_cn)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(m["n_legs"] for m in manifest)
    log.info("wrote %d series bundles (%d legs) to %s", len(manifest), tot, bdir)
    by = {}
    for m in manifest:
        by[(m["region"], m["bucket"])] = by.get((m["region"], m["bucket"]), 0) + 1
    for k, v in sorted(by.items()):
        print(f"  {k[0]:6} {k[1]:8} series={v}")
    print(f"  TOTAL series={len(manifest)} legs={tot}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
