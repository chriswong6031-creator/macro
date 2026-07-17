"""Export the flagship PROXY REGISTRY to JSON + run the health/fitness gates + smoke-run
the record_series kernel over every MEASURED band (D3-W3.1 §1/§4).

Artifacts written (consumed by the D3-W3 page work — no page changes this wave):
  data/cycle_ontology/proxy_registry.json   the registry (bands:[] schema)
  data/cycle_ontology/registry_health.json  per-band tape health (stale = recorded,
                                            never fatal; a MISSING tape fails the build)
  data/cycle_ontology/proxy_fitness.json     MU/CCJ turn-timing fitness verdicts (A6/A17)
  data/cycle_ontology/samples/*.json         3 representative kernel outputs (the D3-W3
                                             enabler proof: daily ETF, monthly FRED, inverted spread)

Usage: python -m scripts.build_proxy_registry
Exit 0 on success; non-zero (raises) if a measured band's tape is MISSING (structural)
or a kernel smoke-run errors.  A stale tape is recorded in the health report (ok=False
+ report['stale']) and never fails the export — house law: it degrades its own band
on cycle.html, not the artifact chain.  Additive — never mutates the three engine pages' JSON.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import cycle_proxies as cp          # noqa: E402
from engine import sector_cycles as sc          # noqa: E402

log = logging.getLogger("build_proxy_registry")

_SAMPLES = Path("data/cycle_ontology/samples")

# 3 representative bands for the committed sample artifacts (§4): a daily ETF, a monthly
# FRED tape, and an inverted FRED spread — the three kernel modes D3-W3 depends on.
_SAMPLE_BANDS = ["gold", "business", "credit"]


def _kernel_args(band: dict) -> dict:
    """Translate a registry band → record_series kwargs (resolving the vol-scaled default)."""
    s = cp.load_series(band)
    kernel = band.get("kernel") or {}
    zz_pct = kernel.get("zz_pct")
    zz_abs = kernel.get("zz_abs")
    if zz_pct is None and zz_abs is None:
        zz_pct = (sc._zz_pct_for(s) if band["freq"] == "D"
                  else sc._zz_pct_for_monthly(s))
    return {"series": s,
            "kwargs": dict(win_start=s.index.min(), last_ts=s.index[-1],
                           freq=band["freq"], invert=band["invert"],
                           zz_pct=zz_pct, zz_abs=zz_abs,
                           zz_standardize=bool(kernel.get("zz_standardize")),
                           trend_span=kernel.get("trend_span"),
                           stoch_win=kernel.get("stoch_win"),
                           basis_label=band["basis"], family="flagship")}


def smoke_run() -> dict:
    """Run record_series over EVERY measured band; assert each yields a record with turns,
    a position and a phase.  Returns {cycle.band: {ok, n_turns, pos, phase, freq}}."""
    out: dict = {}
    for cid, band in cp.measured_bands():
        key = f"{cid}.{band['band']}"
        args = _kernel_args(band)
        rec = sc.record_series(args["series"], **args["kwargs"])
        if rec is None:
            raise RuntimeError(f"smoke_run: {key} produced NO record (series too short?)")
        now = rec.get("now") or {}
        turns = rec.get("turns") or []
        if now.get("pos") is None or now.get("phase") is None:
            raise RuntimeError(f"smoke_run: {key} missing pos/phase")
        out[key] = {"ok": True, "n_turns": len(turns), "n_turns_all": rec.get("n_turns_all"),
                    "pos": now.get("pos"), "phase": now.get("phase"),
                    "freq": now.get("freq"), "proxy": band["proxy"],
                    "position_gauge": band["position_gauge"],
                    "hazard_features": bool(now.get("hazard_features"))}
    return out


def write_samples(root: Path) -> list[str]:
    """Commit 3 representative kernel outputs under data/cycle_ontology/samples/ (§4)."""
    (root / _SAMPLES).mkdir(parents=True, exist_ok=True)
    written = []
    for cid in _SAMPLE_BANDS:
        band = next(b for b in cp.REGISTRY[cid]["bands"] if b["tier"] == "measured")
        args = _kernel_args(band)
        rec = sc.record_series(args["series"], **args["kwargs"])
        # Trim the fat price/osc point arrays to a small tail so the committed sample is
        # a readable schema witness, not a megabyte of chart points.
        sample = dict(rec)
        for k in ("price", "osc"):
            if isinstance(sample.get(k), list):
                sample[k] = {"len": len(sample[k]), "tail": sample[k][-3:]}
        sample["_meta"] = {"cycle": cid, "band": band["band"], "ref": args["series"].attrs.get("ref"),
                           "freq": band["freq"], "invert": band["invert"], "basis": band["basis"]}
        p = root / _SAMPLES / f"{cid}.json"
        p.write_text(json.dumps(sample, indent=2), encoding="utf-8")
        written.append(str(p))
    return written


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    root = Path(".")
    health = cp.export(root)                 # writes registry + health (raises only if MISSING)
    fitness = cp.run_fitness(root)           # writes proxy_fitness.json
    smoke = smoke_run()                       # the D3-W3 enabler proof
    samples = write_samples(root)

    n_ok = sum(1 for v in smoke.values() if v["ok"])
    log.info("registry exported: %d measured bands, all resolve; %d/%d smoke-passed",
             len(health["bands"]), n_ok, len(smoke))
    log.info("fitness verdicts: %s", {c: ("PASS" if v["pass"] else "DEMOTE")
                                      for c, v in fitness["verdicts"].items()})
    log.info("sample artifacts: %s", ", ".join(Path(s).name for s in samples))
    print(json.dumps({"measured_bands": len(smoke), "smoke_ok": n_ok,
                      "fitness": {c: v["pass"] for c, v in fitness["verdicts"].items()},
                      "samples": [Path(s).name for s in samples]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
