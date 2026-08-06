"""Quant Lab study builder — the EXPENSIVE half, off the render path.

Walks the point-in-time rebalance grid for each recreated model, scores it as it was
knowable at each date, measures rank-IC / HAC-t / BH-FDR against the realised forward
return, and writes data/quant_lab/study.json. `engine.quant_lab.page` reads that artifact;
build_site.py never recomputes it inline (12 rebalances x a full leg cross-section each is
minutes, and the render budget is law).

Run:
    .venv/bin/python -m scripts.build_quant_lab [--horizon 63] [--quick] [--stdout]

    --quick    only the last 4 rebalances (fast smoke check; NOT a study)
    --stdout   print the summary table instead of only writing the artifact
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.quant_lab import specs, study                       # noqa: E402
from lib import config                                          # noqa: E402

log = logging.getLogger("build_quant_lab")

# QVO is not studied: its fund-sentiment leg is graded `absent` (1.3% coverage), so a QVO
# study would silently be a QV study. Recording the reason beats an unexplained omission.
STUDY_MODELS = ("fintel_qv", "fintel_qvm", "quant_investing_qvm")
SKIPPED = {"fintel_qvo": "fund_sentiment leg is absent (1.3% coverage) — QVO is not "
                         "recreatable on this substrate, so it is not studied."}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=study.DEFAULT_HORIZON)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    out: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "horizon_d": a.horizon,
        "quick": bool(a.quick),
        "limits": study.STANDING_LIMITS,
        "skipped": SKIPPED,
        "models": {},
    }

    for key in STUDY_MODELS:
        if key not in specs.MODELS:
            continue
        # fintel_qvm's first leg is the QV composite itself, which study_model cannot
        # resolve as a raw column — it studies the momentum leg alongside QV's own legs
        # instead, which is the honest decomposition anyway.
        try:
            r = study.study_model(key, horizon=a.horizon,
                                  max_dates=4 if a.quick else None)
        except Exception as e:                     # noqa: BLE001 — one model must not kill the artifact
            log.error("study failed for %s: %s", key, e)
            out["models"][key] = {"model": key, "verdict": "no_data", "error": str(e)}
            continue
        out["models"][key] = r
        c = r.get("composite") or {}
        log.info("%-22s n=%-3s ic=%-9s t=%-8s q=%-8s -> %s",
                 key, c.get("n_dates"), c.get("mean_ic"),
                 c.get("t_hac") or c.get("nw_t"), c.get("q"), r.get("verdict"))

    # The options-dislocation family is DAILY, has no composite, and is scored against its
    # own imported pre-registration — so it takes its own entry point rather than
    # study_model(), whose grid is quarter-end off the close panel and whose composite would
    # be the fused pre-gate score RO-2 forbids.
    if "options_dislocation" in specs.MODELS:
        try:
            r = study.study_options_dislocation()
            out["models"]["options_dislocation"] = r
            # Same mechanism, same key: the family's limits join the artifact's standing
            # limits so the page's existing "what these cannot tell you" panel carries them.
            out["limits"] = {**out["limits"], **study.OPTIONS_LIMITS}
            log.info("%-22s sessions=%s/%s stamps  scored_dates=%s  -> %s",
                     "options_dislocation", r.get("n_sessions"), r.get("n_stamps"),
                     r.get("n_scored_dates"), r.get("verdict"))
            for lk, lv in (r.get("legs") or {}).items():
                log.info("    %-16s ic=%-9s n=%-3s indep=%-3s -> %s (uncorrected: %s)",
                         lk, lv.get("mean_ic"), lv.get("n_dates"),
                         lv.get("n_independent_windows"), lv.get("verdict"),
                         lv.get("verdict_uncorrected"))
        except Exception as e:                     # noqa: BLE001 — must not kill the artifact
            log.error("options dislocation study failed: %s", e)
            out["models"]["options_dislocation"] = {
                "model": "options_dislocation", "verdict": "no_data", "error": str(e)}

    d = config.data_dir() / "quant_lab"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "study.json"
    p.write_text(json.dumps(out, indent=1, default=str))
    log.info("wrote %s (%d models)", p, len(out["models"]))

    if a.stdout:
        for key, r in out["models"].items():
            c = r.get("composite") or {}
            print(f"\n{r.get('name', key)}  [{r.get('verdict')}]")
            if c:
                print(f"  composite  ic={c.get('mean_ic')}  t={c.get('t_hac') or c.get('nw_t')}"
                      f"  q={c.get('q')}  n={c.get('n_dates')}")
            else:
                # No composite is the design here, not a gap — say so rather than printing
                # a row of Nones that reads like a failed study.
                print(f"  no composite by design ({r.get('rule', 'n/a')}); "
                      f"{r.get('n_sessions')} sessions from {r.get('n_stamps')} stamps")
            for lk, lv in sorted((r.get("legs") or {}).items(),
                                 key=lambda kv: -(kv[1].get("mean_ic") or -9)):
                extra = ""
                if lv.get("verdict_uncorrected") and \
                        lv["verdict_uncorrected"] != lv.get("verdict"):
                    extra = f"  [uncorrected: {lv['verdict_uncorrected']}]"
                print(f"    {lk:22} ic={str(lv.get('mean_ic')):>9}"
                      f"  q={str(lv.get('q')):>8}  cov={lv.get('mean_coverage')}"
                      f"  -> {lv.get('verdict')}{extra}")
    return 0


if __name__ == "__main__":
    # Scoped to the CLI entry point on purpose. At module level this mutates the
    # process-global warnings filter for every importer, which is what the
    # import-hygiene ratchet (tests/test_no_module_level_logging_disable.py) exists
    # to stop — the study walk is noisy, but that is this script's problem to mute,
    # not its callers'.
    warnings.filterwarnings("ignore")
    raise SystemExit(main())
