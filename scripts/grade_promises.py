"""scripts/grade_promises.py — run the three promise-graders, ship the artifacts.

Cycle Intelligence W2.4.  Produces the platform's FIRST real scorecards from the
12,519 backfilled monthly PIT stamps + the small live cohort:

  - data/<engine>/scorecards/promises_<epoch>.json   (per engine, SEPARATE — never pooled)
  - data/cycle_ontology/cone_recalibration.json       (versioned recal multipliers →
                                                        kills the lerp(1.5,13) constants)
  - research/cycle_masterplan/W24_FIRST_SCORECARDS.md  (honest headline table)

Usage:
    python -m scripts.grade_promises            # grade all three engines, write artifacts
    python -m scripts.grade_promises --check     # grade in-memory, print, write nothing
    python -m scripts.grade_promises --engine sector_cycles

 Engines: sector_cycles (US, 11 SPDR), country_cycles (24+ country ETFs),
china_sector_cycles (31 Shenwan L1).  Sectors and countries are SEPARATE scorecards.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from engine import promise_graders as pg

log = logging.getLogger("grade_promises")

ENGINES = ["sector_cycles", "country_cycles", "china_sector_cycles"]


# ── price loaders (SAME basis the stamps were computed on) ────────────────────────────

def _yahoo_prices(ids: list[str]) -> dict[str, pd.Series]:
    """close_price (price_v1) panel for US sector / country ETFs — the stamp basis."""
    from engine.inputs import yahoo_closes
    px = yahoo_closes(basis="price")
    upper = {c.upper(): c for c in px.columns}
    out: dict[str, pd.Series] = {}
    for sid in ids:
        col = upper.get(sid.upper())
        if col is not None:
            s = px[col].dropna()
            if not s.empty:
                out[sid] = s
    return out


def _china_prices(ids: list[str]) -> dict[str, pd.Series]:
    """Shenwan L1 index close (price basis — A-share indices are not TR)."""
    from engine import china_sector_index as csi
    out: dict[str, pd.Series] = {}
    for sid in ids:
        try:
            s = csi.sw_close(str(sid))
        except Exception:  # noqa: BLE001
            s = None
        if s is not None and not s.dropna().empty:
            out[sid] = s.dropna()
    return out


def _load_prices(engine: str, ids: list[str]) -> dict[str, pd.Series]:
    if engine == "china_sector_cycles":
        return _china_prices(ids)
    return _yahoo_prices(ids)


def _epoch_tag(scorecard: dict) -> str:
    """Filename epoch = basis_version + zz_version from the graded rows (badge discipline)."""
    ep = scorecard.get("epoch", {}) or {}
    basis = ep.get("basis_version") or "unknown_basis"
    zz = ep.get("zz_version") or "unknown_zz"
    return f"{basis}_{zz}"


# ── artifacts ─────────────────────────────────────────────────────────────────────────

def grade_all(engines: list[str], data_root: Path) -> dict[str, dict]:
    scorecards: dict[str, dict] = {}
    for engine in engines:
        try:
            from engine import grading_stats as gs
            df = gs.load_graded_log(engine, include_backfill=True)
        except Exception as e:  # noqa: BLE001
            log.warning("grade_promises: cannot load log for %s: %s", engine, e)
            continue
        if df is None or len(df) == 0:
            log.warning("grade_promises: no data for %s — skipping", engine)
            scorecards[engine] = {"engine": engine, "status": "no_data"}
            continue
        ids = sorted({str(i) for i in df["id"].dropna().unique()})
        prices = _load_prices(engine, ids)
        if not prices:
            log.warning("grade_promises: no prices resolved for %s — skipping", engine)
            scorecards[engine] = {"engine": engine, "status": "no_prices"}
            continue
        log.info("grade_promises: grading %s (%d instruments, %d priced, %d stamps)",
                 engine, len(ids), len(prices), len(df))
        scorecards[engine] = pg.grade_engine(engine, prices, include_backfill=True)
    return scorecards


def write_scorecards(scorecards: dict[str, dict], data_root: Path) -> list[Path]:
    written: list[Path] = []
    for engine, sc in scorecards.items():
        if sc.get("status") in ("no_data", "no_prices"):
            continue
        out_dir = data_root / engine / "scorecards"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"promises_{_epoch_tag(sc)}.json"
        path.write_text(json.dumps(sc, indent=2, default=str))
        written.append(path)
        log.info("grade_promises: wrote %s", path)
    return written


def write_cone_recalibration(scorecards: dict[str, dict], data_root: Path) -> Path:
    """Ship the versioned cone-recalibration artifact (D2 §3.2 / CC-1).

    This is what KILLS the lerp(1.5,13) class of constants downstream: the projection
    code reads recal_multiplier per engine at build time instead of a hand constant.
    Multipliers are taken from the BACKTEST cohort (the matured one) headline slice AND
    the forward-only slice (the honest "is the cone itself calibrated" number).
    """
    recal: dict = {
        "schema": "cone_recalibration.v1",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "nominal": pg.NOMINAL_CONE,
        "source": "engine.promise_graders.cone_grade (W2.4)",
        "note": ("recal_halfwidth = quantile(|timing_err|, nominal) from the realized "
                 "turn-timing distribution; replaces lerp(1.5,13) / tilt(1.35,0.7). "
                 "Use the forward_only multiplier when the projection points forward; the "
                 "headline multiplier is dominated by chronically-overdue projections "
                 "(W2.4 finding: re-anchoring repaint, cycles-core-4)."),
        "engines": {},
    }
    for engine, sc in scorecards.items():
        bt = (sc.get("cohorts", {}) or {}).get("BACKTEST", {})
        cc = bt.get("cone_coverage") if isinstance(bt, dict) else None
        if not cc:
            continue
        fwd = cc.get("forward_only") or {}
        recal["engines"][engine] = {
            "epoch": sc.get("epoch"),
            "cohort": "BACKTEST",
            "headline": {"empirical": cc.get("empirical"), "n": cc.get("n"),
                         "recal_halfwidth_days": cc.get("recal_halfwidth"),
                         "recal_multiplier": cc.get("recal_multiplier"),
                         "verdict": cc.get("verdict")},
            "forward_only": {"empirical": fwd.get("empirical"), "n": fwd.get("n"),
                             "recal_halfwidth_days": fwd.get("recal_halfwidth"),
                             "recal_multiplier": fwd.get("recal_multiplier"),
                             "verdict": fwd.get("verdict")},
            "overdue_fraction": cc.get("overdue_fraction"),
        }
    path = data_root / "cycle_ontology"
    path.mkdir(parents=True, exist_ok=True)
    out = path / "cone_recalibration.json"
    out.write_text(json.dumps(recal, indent=2, default=str))
    log.info("grade_promises: wrote %s", out)
    return out


# ── human-readable scorecard ──────────────────────────────────────────────────────────

def _fmt(v, nd=3):
    return "—" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def _fmt_ci(ci):
    return "—" if not ci else f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def write_markdown(scorecards: dict[str, dict], repo_root: Path) -> Path:
    L: list[str] = []
    L.append("# W2.4 — The Three Promise-Graders: FIRST REAL SCORECARDS")
    L.append("")
    L.append("**Wave:** Cycle Intelligence W2.4 · **Generated:** "
             f"{pd.Timestamp.now("UTC").isoformat()}")
    L.append("")
    L.append("This is the program's **first real self-measurement** — the first leak-free "
             "walk-forward track record for the numbers the platform already plots. Per "
             "the doctrine, **a bad number honestly measured is the product.** Turn truth "
             "is the INDEPENDENT realized-extrema oracle "
             "(`cycle_ontology.realized_extrema_turns`, ruling A6) — the ZigZag detector "
             "never grades itself. Sectors and countries are SEPARATE scorecards. BACKTEST "
             "(backfilled) and LIVE (prospective) cohorts never blend in one number.")
    L.append("")
    L.append("## Headline — turn P/R · cone coverage · reliability (BACKTEST cohort)")
    L.append("")
    L.append("| Engine | n stamps | Turn precision | Turn recall | Timing err (mo, median/IQR) "
             "| Cone cov vs 0.80 | Cone (fwd-only) | Overdue frac | Signal skill | Stance skill |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for engine, sc in scorecards.items():
        bt = (sc.get("cohorts", {}) or {}).get("BACKTEST", {})
        if not isinstance(bt, dict) or bt.get("status") == "empty" or "turn_pr" not in bt:
            L.append(f"| {engine} | — | (no matured cohort) | | | | | | | |")
            continue
        tp = bt["turn_pr"]["pooled"]
        cc = bt["cone_coverage"]
        fwd = cc.get("forward_only") or {}
        rl = bt["reliability"]
        te = tp.get("timing_err", {})
        te_s = (f"{_fmt(te.get('median'),1)} / {_fmt(te.get('iqr'),1)}" if te else "—")
        sig = rl.get("signal", {}).get("skill_score")
        stc = rl.get("stance", {}).get("skill_score")
        L.append(
            f"| **{engine}** | {bt.get('n_stamps')} "
            f"| {_fmt(tp.get('precision'))} {_fmt_ci(tp.get('precision_ci'))} "
            f"| {_fmt(tp.get('recall'))} {_fmt_ci(tp.get('recall_ci'))} "
            f"| {te_s} "
            f"| {_fmt(cc.get('empirical'))} (n={cc.get('n')}) "
            f"| {_fmt(fwd.get('empirical'))} (n={fwd.get('n')}) "
            f"| {_fmt(cc.get('overdue_fraction'))} "
            f"| {_fmt(sig)} | {_fmt(stc)} |")
    L.append("")
    L.append("## Pre-registration gate verdicts (PREREGISTRATION.md §3)")
    L.append("")
    L.append("Gates are FROZEN — this reports pass/fail/inconclusive, it does not move any "
             "criterion. FDR-BH applied within the `turn_pr` family at q=0.10.")
    L.append("")
    L.append("| Gate | Claim | Bar | Result | Verdict |")
    L.append("|---|---|---|---|---|")
    for engine, sc in scorecards.items():
        bt = (sc.get("cohorts", {}) or {}).get("BACKTEST", {})
        if not isinstance(bt, dict) or "turn_pr" not in bt:
            continue
        tp = bt["turn_pr"]["pooled"]
        cc = bt["cone_coverage"]
        rl = bt["reliability"]
        # CC-3 turn P/R
        pci = tp.get("precision_ci")
        rci = tp.get("recall_ci")
        cc3_pass = bool(pci and rci and pci[0] > 0.5 and rci[0] > 0.5
                        and tp.get("n_eff", 0) >= 40)
        L.append(f"| **CC-3** ({engine}) | turn P/R Wilson-lo > 0.5 on n_eff≥40, "
                 f"independent truth | prec-lo {_fmt(pci[0],2) if pci else '—'}, "
                 f"rec-lo {_fmt(rci[0],2) if rci else '—'}, n_eff {tp.get('n_eff')} "
                 f"| {'PASS' if cc3_pass else 'FAIL'} | {tp.get('verdict')} |")
        # CC-1 cone coverage (calibration, report-only)
        ci = cc.get("ci")
        cc1_cal = bool(ci and ci[0] <= cc.get("nominal", 0.8) <= ci[1])
        L.append(f"| **CC-1** ({engine}) | cone coverage ≈ 0.80 (calibration, report-only) "
                 f"| empirical {_fmt(cc.get('empirical'))} vs 0.80, CI {_fmt_ci(ci)} "
                 f"| {'CALIBRATED' if cc1_cal else 'MISCALIBRATED'} | {cc.get('verdict')} |")
        # CC-2 reliability skill > 0
        for fld in ("signal", "stance"):
            r = rl.get(fld, {})
            skill = r.get("skill_score")
            n = r.get("n", 0)
            cc2_pass = bool(skill is not None and skill > 0 and n >= 30)
            L.append(f"| **CC-2** ({engine}/{fld}) | Brier skill vs base rate > 0, n≥30 "
                     f"| skill {_fmt(skill)}, hit {_fmt(r.get('hit_rate'))} vs base "
                     f"{_fmt(r.get('base_hit_rate'))}, n {n} "
                     f"| {'PASS' if cc2_pass else 'FAIL'} | {r.get('verdict')} |")
    L.append("")
    L.append("## Cone recalibration multipliers (ships to cone_recalibration.json)")
    L.append("")
    L.append("The recalibration half-width = `quantile(|timing_err|, 0.80)` from the "
             "realized turn-timing distribution. This **replaces** the `lerp(1.5,13)` / "
             "`tilt(1.35,0.7)` hand constants (audit cycle-flagship-4).")
    L.append("")
    L.append("| Engine | Headline mult (×) | Forward-only mult (×) | Interpretation |")
    L.append("|---|---|---|---|")
    for engine, sc in scorecards.items():
        bt = (sc.get("cohorts", {}) or {}).get("BACKTEST", {})
        cc = bt.get("cone_coverage") if isinstance(bt, dict) else None
        if not cc:
            continue
        fwd = cc.get("forward_only") or {}
        hm = cc.get("recal_multiplier")
        fm = fwd.get("recal_multiplier")
        interp = ("cones far too tight" if hm and hm > 1.5
                  else "cones too wide" if hm and hm < 0.7 else "near-calibrated")
        L.append(f"| {engine} | {_fmt(hm)} | {_fmt(fm)} | {interp} |")
    L.append("")
    L.append("## Honest reading of the numbers")
    L.append("")
    L.append("- **Turn precision is low and cone coverage is far below 0.80.** This is not "
             "a grader bug — it is the measurement doing its job. The dominant cause "
             "(surfaced by the `overdue_fraction` column) is that a large majority of "
             "stamped projections are **chronically overdue**: their `proj_central` points "
             "at a turn date in the PAST relative to the stamp. This is exactly the "
             "re-anchoring / `find_troughs` repaint the audit flagged (cycles-core-4).")
    L.append("- **The forward-only cone slice** isolates the cone's own calibration from "
             "the overdue-projection pathology; it is the number to watch once the "
             "projection engine is fixed downstream (D5).")
    L.append("- **Reliability skill is negative** for the directional labels vs the "
             "instrument base rate over 63d — the labels do not, on this backfill, beat "
             "an always-predict-the-majority-direction coin. Reported honestly, not hidden.")
    L.append("- **LIVE cohort** is small and prospective; its cells stay `ACCRUING` until "
             "n_eff≥40. Badge discipline (A6/A1): a BACKTEST number never promotes a "
             "user-facing MEASURED badge — only a matured LIVE cohort can.")
    L.append("")
    L.append("_Artifacts: `data/<engine>/scorecards/promises_<epoch>.json`, "
             "`data/cycle_ontology/cone_recalibration.json`._")
    L.append("")
    out = repo_root / "research" / "cycle_masterplan" / "W24_FIRST_SCORECARDS.md"
    out.write_text("\n".join(L))
    log.info("grade_promises: wrote %s", out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="W2.4 promise-graders")
    ap.add_argument("--check", action="store_true",
                    help="grade in-memory and print; write no artifacts")
    ap.add_argument("--engine", choices=ENGINES, help="grade a single engine")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose or args.check else logging.WARNING,
                        format="%(levelname)s %(message)s")

    try:
        from lib import config
        data_root = config.data_dir()
    except Exception:  # noqa: BLE001
        data_root = Path("data")
    repo_root = Path(__file__).resolve().parents[1]

    engines = [args.engine] if args.engine else ENGINES
    scorecards = grade_all(engines, Path(data_root))

    if args.check:
        print(json.dumps(scorecards, indent=2, default=str))
        return 0

    write_scorecards(scorecards, Path(data_root))
    write_cone_recalibration(scorecards, Path(data_root))
    write_markdown(scorecards, repo_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
