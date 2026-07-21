#!/usr/bin/env python3
"""Run the Prophet × Stage quality re-grade backtest (PSQ).

Single-pass CLI that fans fire-detection+grading once, then assembles both
the PSF results dict AND the PSQ quality-tilt falsifiers in one pass.
Writes:

  * data/research/psq_results.json          — full results dict (PSF + PSQ)
  * data/research/psf_fires.parquet         — per-fire dump (if <= 20 MB; else gitignored)
  * research/reports/PROPHET_STAGE_QUALITY_RESULTS.md — the honest report

Binding spec: research/PROPHET_STAGE_QUALITY_PREREG.md.
SAME-SAMPLE DISCLOSURE: the PSF run already observed the return right-shift;
PSQ commits the bootstrap CI machinery before re-running.  Proxy disclosure
from PSF §0 applies verbatim.

NULLS PRINTED — every metric printed including nulls; no 'validated' in the
report; all CIs shown; mechanical verdicts only (no adjudication text).

Usage:
    python -m scripts.run_prophet_stage_quality [--root DATA_ROOT]
        [--max-workers N] [--sample N] [--ec-path PATH]
        [--fires-out PATH] [--no-report]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine import prophet_stage_fusion as psf  # noqa: E402

log = logging.getLogger("run_prophet_stage_quality")

_FIRES_PARQUET_SIZE_LIMIT = 20 * 1024 * 1024  # 20 MB


# --------------------------------------------------------------------------- #
# Formatters                                                                    #
# --------------------------------------------------------------------------- #
def _fmt_pct(x, digits: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.{digits}f}%"


def _fmt_num(x, digits: int = 4) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def _fmt_ci(ci, pct: bool = False, digits: int = 4) -> str:
    if not ci or ci[0] is None or ci[1] is None:
        return "[—, —]"
    if pct:
        return f"[{ci[0]*100:.{digits}f}%, {ci[1]*100:.{digits}f}%]"
    return f"[{ci[0]:.{digits}f}, {ci[1]:.{digits}f}]"


def _verdict_line(key: str, verdict: str, reason: str | None = None) -> str:
    r = f" ({reason})" if reason else ""
    return f"- **{key}: `{verdict}`**{r}"


# --------------------------------------------------------------------------- #
# Single-pass fan-out (captures Fire objects without a second run)              #
# --------------------------------------------------------------------------- #
def run_single_pass(data_root: Path, ec_path: str | Path | None = None,
                    max_workers: int = 4, sample_n: int | None = None,
                    sample_seed: int = 20260720) -> tuple[list[psf.Fire], dict]:
    """One parallel fan-out → (all_fires, assembled_results_dict).

    Replicates psf.run_backtest internally, but returns the raw Fire objects
    so the caller can build the per-fire parquet without a second fan-out.
    """
    data_root = Path(data_root)
    dead_prices = psf.grading.load_dead_prices() or {}
    tickers = psf.build_universe(data_root, dead_prices=dead_prices)
    n_universe = len(tickers)
    surv = psf.survivorship_disclosure(data_root, dead_prices=dead_prices)

    sampled = False
    sample_note = None
    if sample_n is not None and sample_n < n_universe:
        rng = np.random.default_rng(sample_seed)
        idx = rng.choice(n_universe, size=sample_n, replace=False)
        tickers = [tickers[i] for i in sorted(idx)]
        sampled = True
        sample_note = (f"Representative random sample of {sample_n}/{n_universe} names "
                       f"(seed={sample_seed}, uniform over the union universe) — DISCLOSED, "
                       "not a silent truncation.")

    workers = max(1, min(int(max_workers), 4))
    all_fires: list[psf.Fire] = []
    n_late_ipo = 0
    n_with_prices = 0
    ec_str = str(ec_path) if ec_path is not None else None

    if workers > 1 and len(tickers) > 20:
        try:
            with ProcessPoolExecutor(max_workers=workers, initializer=psf._run_init,
                                     initargs=(str(data_root), ec_str)) as ex:
                for fires_t, late, had in ex.map(psf._run_one, tickers, chunksize=16):
                    all_fires.extend(fires_t)
                    n_late_ipo += int(late)
                    n_with_prices += int(had)
        except Exception as e:  # noqa: BLE001
            log.warning("PSQ: parallel run failed (%s) — serial fallback", e)
            all_fires, n_late_ipo, n_with_prices = [], 0, 0
            psf._run_init(str(data_root), ec_str)
            for tk in tickers:
                fires_t, late, had = psf._run_one(tk)
                all_fires.extend(fires_t)
                n_late_ipo += int(late)
                n_with_prices += int(had)
    else:
        psf._run_init(str(data_root), ec_str)
        for tk in tickers:
            fires_t, late, had = psf._run_one(tk)
            all_fires.extend(fires_t)
            n_late_ipo += int(late)
            n_with_prices += int(had)

    results = psf.assemble_results(
        all_fires,
        n_universe=n_universe,
        n_with_prices=n_with_prices,
        n_late_ipo=n_late_ipo,
        sampled=sampled,
        sample_note=sample_note,
        sample_n=(len(tickers) if sampled else n_universe),
        survivorship=surv,
    )
    return all_fires, results


# --------------------------------------------------------------------------- #
# Report builder                                                                #
# --------------------------------------------------------------------------- #
def build_report(results: dict, fires_parquet_path: Path | None,
                 fires_parquet_size: int | None) -> str:
    u = results["universe"]
    psq = results.get("psq", {})
    p15 = results["params"]["clean15_126"]
    arms = p15["arms"]
    lines: list[str] = []

    # Header.
    lines += [
        "# Prophet × Stage quality re-grade — backtest results (PSQ)",
        "",
        f"Spec: `research/PROPHET_STAGE_QUALITY_PREREG.md` · generated {results['generated_utc']}",
        "",
    ]

    # §0 Same-sample + proxy disclosure (MUST be first).
    lines += [
        "## §0 SAME-SAMPLE DISCLOSURE (read first)",
        "",
        "> **SAME-SAMPLE CONFIRMATORY RE-ANALYSIS.** The PSF run (predecessor test) already",
        "> observed the return right-shift that PSQ tests (median fwd_ret_126 A→C 1.8%→4.7%).",
        "> PSQ commits the bootstrap CI machinery and pass lines in the pre-registration",
        "> (research/PROPHET_STAGE_QUALITY_PREREG.md) BEFORE re-running, so a CI straddling",
        "> zero is filed as FAIL. The promotion consequence is therefore **provisional** and",
        "> the binding out-of-sample confirmation is the live-Prophet forward shadow (#3157).",
        "> The point estimates below were known before registration; only the CI machinery",
        "> and pass lines were not.",
        "",
        "> **UNIVERSE-DRIFT DISCLOSURE (review round 1):** this re-grade runs on a",
        "> RE-GENERATED universe snapshot, not PSF's literal fire set: nightly store churn",
        "> moves the union universe between runs (PSF run: 2,759 live globs / 56,237 fires;",
        "> the 2026-07-20 PSQ run: 2,520 / 52,078, ~9% live-glob churn). Arm definitions,",
        "> filters, and ruler are frozen by reference (prereg \u00a72); the FIRES are a drifted",
        "> snapshot of the same construction. On the PSQ snapshot the hypothesis-generating",
        "> shift reads A\u2192C 2.29%\u21925.08% (vs 1.8%\u21924.7% on PSF's snapshot \u2014 both quoted",
        "> deliberately; prereg amendment A1). Reviewer robustness: 50\u00d7 jackknife dropping",
        "> 10% of names kept the H1 diff in [+2.14, +3.09]pp, always above the +1.5pp floor.",
        "",
        "> **PROXY DISCLOSURE (PSF §0 applies verbatim):** " + results.get("proxy_disclosure", ""),
        "",
    ]

    # Universe.
    lines += [
        "## Universe",
        "",
        f"- Union universe (baskets/ohlcv ∪ data/stocks, minus SPY bench): **{u['n_union_universe']}** names; "
        f"with usable prices: **{u['n_with_prices']}**.",
        f"- Late-IPO names EXCLUDED (< {u['min_completed_weeks_gate']} completed weeks at entry) "
        f"and COUNTED: **{u['n_late_ipo_excluded_counted']}** (§7).",
        f"- Benchmark: {u['bench']} · entry window: {u['window'][0]} … {u['window'][1]}.",
    ]
    if u.get("sampled"):
        lines.append(f"- **SAMPLED:** {u['sample_note']}")
    else:
        lines.append("- Full universe (no sampling).")
    lines.append(
        f"- Total fresh fires (T1/T2, all names): **{results['n_fires_total']}**. "
        f"EC gate (arm C): earnings_call_sent ≥ {results['ec_gate']}."
    )
    lines.append("")

    # Survivorship.
    surv = u.get("survivorship")
    if surv:
        lines += [
            "### §0 SURVIVORSHIP DISCLOSURE",
            "",
            f"- Universe is **survivor-LEAN, not full PIT**. Live globs: **{surv['n_live_globbed']}** names; "
            f"delisted dead-name tickers UNIONED IN and COUNTED: **+{surv['n_dead_name_added_counted']}** (FIX-2).",
            f"- Residual gap: **{surv['n_pit_absent_no_price_source']}** S&P-1500 PIT members "
            f"that traded {u['window'][0]}–{u['window'][1]} have NO price source anywhere and remain ABSENT; "
            f"of {surv['n_pit_members_traded_in_window']} PIT members that traded in-window.",
            f"- **Consequence:** {surv['posture']}",
            "",
        ]

    # Per-arm summary table (matured fires, clean15_126).
    lines += [
        "## Per-arm summary — matured fires, clean15_126",
        "",
        "| Arm | n_matured | n_months | med fwd_ret_126 | med fwd_mfe_126 | med fwd_mdd_126 | "
        "med EA (mfe+mdd) | STOPPED rate | win-rate |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in psf.ARMS:
        o = arms[arm]["overall"]
        bm = arms[arm]["bootstrap_winrate"]
        n_months = bm.get("n_months", "—")
        mfe = o.get("median_fwd_mfe_126")
        mdd = o.get("median_fwd_mdd_126")
        ea = ((mfe or 0) + (mdd or 0)) if (mfe is not None and mdd is not None) else None
        lines.append(
            f"| {arm} | {o['n_entries']} | {n_months} | "
            f"{_fmt_pct(o['median_fwd_ret_126'])} | {_fmt_pct(o.get('median_fwd_mfe_126'))} | "
            f"{_fmt_pct(o.get('median_fwd_mdd_126'))} | {_fmt_pct(ea)} | "
            f"{_fmt_pct(o['stopped_rate'])} | {_fmt_pct(o['win_rate'])} |"
        )
    lines.append("")

    # PSQ Bootstrap CIs.
    h1 = psq.get("PSQ_H1", {})
    h1_ba = psq.get("PSQ_H1_decompositions", {}).get("B_minus_A", {})
    h1_cb = psq.get("PSQ_H1_decompositions", {}).get("C_minus_B", {})
    h1_deov = psq.get("PSQ_H1_deoverlapped", {})
    h2 = psq.get("PSQ_H2", {})
    h3 = psq.get("PSQ_H3", {})
    kill = psq.get("KILL_PSQ", {})
    regime_leg = psq.get("regime_leg", {}).get("regimes", {})

    lines += [
        "## PSQ bootstrap CIs — paired month-block, n_boot=10,000, seed=20260720",
        "",
        "### PSQ-H1 (PRIMARY) — median fwd_ret_126, C−A",
        "",
    ]
    b1 = h1.get("bootstrap", {})
    lines += [
        f"| Statistic | Value |",
        f"|---|---|",
        f"| n_matured C | {psq.get('n_matured_C', '—')} |",
        f"| n_matured A | {psq.get('n_matured_A', '—')} |",
        f"| n_months (union) | {b1.get('n_months', '—')} |",
        f"| point median A | {_fmt_pct(b1.get('point_lo'))} |",
        f"| point median C | {_fmt_pct(b1.get('point_hi'))} |",
        f"| point diff C−A | {_fmt_pct(b1.get('diff_point'))} |",
        f"| economic floor (preregistered) | +1.5pp (+0.015) |",
        f"| boot mean | {_fmt_pct(b1.get('boot_mean'))} |",
        f"| boot SE | {_fmt_pct(b1.get('boot_se'))} |",
        f"| 2.5% CI | {_fmt_pct(b1.get('ci95', [None, None])[0])} |",
        f"| 97.5% CI | {_fmt_pct(b1.get('ci95', [None, None])[1])} |",
        f"| CI [2.5%, 97.5%] | {_fmt_ci(b1.get('ci95'), pct=True)} |",
        f"| CI lower > 0? | {b1.get('lower_gt_0', '—')} |",
        f"| no-verdict? | {b1.get('no_verdict', '—')} |",
        "",
    ]

    lines += [
        "### PSQ-H1 decompositions (B−A and C−B — PRINTED, NO VERDICTS)",
        "",
        "| Comparison | point diff | 2.5% | 97.5% | n_months |",
        "|---|---|---|---|---|",
    ]
    for label, bd in (("B−A", h1_ba), ("C−B", h1_cb)):
        ci = bd.get("ci95", [None, None])
        lines.append(
            f"| {label} | {_fmt_pct(bd.get('diff_point'))} | "
            f"{_fmt_pct(ci[0])} | {_fmt_pct(ci[1])} | {bd.get('n_months', '—')} |"
        )
    lines.append("")

    lines += [
        "### PSQ-H1 de-overlapped robustness (one fire per name per 126-bar window — SUPPORTING)",
        "",
    ]
    b1d = h1_deov.get("bootstrap", {})
    ci_deov = b1d.get("ci95", [None, None])
    lines += [
        f"- n_fires de-overlapped: {h1_deov.get('n_fires_deoverlapped', '—')} (from {results['n_fires_total']})",
        f"- point diff C−A: {_fmt_pct(b1d.get('diff_point'))}",
        f"- bootstrap CI [2.5%, 97.5%]: {_fmt_ci(ci_deov, pct=True)}",
        f"- n_months: {b1d.get('n_months', '—')}",
        "",
    ]

    lines += [
        "### PSQ-H2 (secondary) — median EA (fwd_mfe_126 + fwd_mdd_126), C−A",
        "",
    ]
    b2 = h2.get("bootstrap", {})
    ci2 = b2.get("ci95", [None, None])
    lines += [
        f"| Statistic | Value |",
        f"|---|---|",
        f"| n_fires C (non-null EA) | {b2.get('n_fires_hi', '—')} |",
        f"| n_fires A (non-null EA) | {b2.get('n_fires_lo', '—')} |",
        f"| n_months | {b2.get('n_months', '—')} |",
        f"| point median EA, A | {_fmt_pct(b2.get('point_lo'))} |",
        f"| point median EA, C | {_fmt_pct(b2.get('point_hi'))} |",
        f"| point diff C−A | {_fmt_pct(b2.get('diff_point'))} |",
        f"| CI [2.5%, 97.5%] | {_fmt_ci(ci2, pct=True)} |",
        f"| no-verdict? | {b2.get('no_verdict', '—')} |",
        "",
    ]

    lines += [
        "### PSQ-H3 (secondary) — stopped fraction, C−A (negative = C better)",
        "",
    ]
    b3 = h3.get("bootstrap", {})
    ci3 = b3.get("ci95", [None, None])
    lines += [
        f"| Statistic | Value |",
        f"|---|---|",
        f"| n_months | {b3.get('n_months', '—')} |",
        f"| point stopped fraction, A | {_fmt_pct(b3.get('point_lo'))} |",
        f"| point stopped fraction, C | {_fmt_pct(b3.get('point_hi'))} |",
        f"| point diff C−A | {_fmt_pct(b3.get('diff_point'))} |",
        f"| CI [2.5%, 97.5%] | {_fmt_ci(ci3, pct=True)} |",
        f"| CI upper < 0? | {b3.get('upper_lt_0', '—')} |",
        f"| no-verdict? | {b3.get('no_verdict', '—')} |",
        "",
    ]

    # Regime leg.
    lines += [
        "## Regime leg — H1 point diff per regime (SUPPORTING, no verdict change alone)",
        "",
        "| Regime | n_dates (A) | n_fires C | n_fires A | med ret C | med ret A | diff (C−A) |",
        "|---|---|---|---|---|---|---|",
    ]
    for reg, rv in regime_leg.items():
        lines.append(
            f"| {reg} | {rv.get('n_dates', '—')} | {rv.get('n_fires_C', '—')} | "
            f"{rv.get('n_fires_A', '—')} | {_fmt_pct(rv.get('median_fwd_ret_C'))} | "
            f"{_fmt_pct(rv.get('median_fwd_ret_A'))} | {_fmt_pct(rv.get('diff_point'))} |"
        )
    lines.append("")

    # Mechanical verdicts.
    lines += [
        "## §5 Mechanical verdicts (pre-registered falsifiers)",
        "",
        "> These lines are MECHANICAL outputs. Adjudication text is in the placeholder section below.",
        "",
    ]
    h1_verdict = h1.get("verdict", "NO-VERDICT")
    h1_reason = h1.get("fail_reason")
    h2_verdict = h2.get("verdict", "NO-VERDICT")
    h3_verdict = h3.get("verdict", "NO-VERDICT")
    kill_triggered = kill.get("triggered", False)

    lines += [
        _verdict_line("PSQ-H1 (PRIMARY — quality tilt; median fwd_ret_126 C−A)",
                      h1_verdict, h1_reason),
        f"  - CI lower bound: {_fmt_pct(b1.get('ci95', [None, None])[0])} "
        f"(must be > 0 to PASS; econ floor: point diff must be >= +1.5pp)",
        f"  - Point diff C−A: {_fmt_pct(b1.get('diff_point'))} "
        f"({'ABOVE' if (b1.get('diff_point') or 0) >= 0.015 else 'BELOW'} +1.5pp floor)",
        "",
        _verdict_line("PSQ-H2 (secondary — EA; no promotion/kill power)", h2_verdict,
                      "CI lower <= 0 → FAIL" if h2_verdict == "FAIL" else None),
        f"  - CI [2.5%, 97.5%]: {_fmt_ci(ci2, pct=True)}",
        "",
        _verdict_line("PSQ-H3 (secondary — stopped fraction; no promotion/kill power)", h3_verdict,
                      "CI upper >= 0 → FAIL" if h3_verdict == "FAIL" else None),
        f"  - CI [2.5%, 97.5%]: {_fmt_ci(ci3, pct=True)}",
        "",
        _verdict_line("KILL predicate (DO_NOT_REBUILD trigger)",
                      "TRIGGERED" if kill_triggered else "not triggered"),
    ]
    if kill.get("kill_reason_overall_nonpositive"):
        lines.append("  - Reason: H1 full-sample point diff <= 0")
    if kill.get("kill_reason_regime_negative"):
        lines.append(f"  - Reason: negative in >= 2 regimes at n_dates >= 50: "
                     f"{kill['kill_reason_regime_negative']}")
    lines.append("")

    # Per-fire parquet note.
    lines += [
        "## Per-fire dump (reproducibility artifact)",
        "",
    ]
    if fires_parquet_path is not None and fires_parquet_path.exists():
        size_mb = (fires_parquet_size or fires_parquet_path.stat().st_size) / (1024 * 1024)
        if size_mb <= 20:
            lines.append(f"- Per-fire parquet committed at `{fires_parquet_path}` ({size_mb:.1f} MB).")
        else:
            lines.append(
                f"- Per-fire parquet is {size_mb:.1f} MB (> 20 MB limit) — **gitignored**. "
                "Regenerate with: "
                "`python -m scripts.run_prophet_stage_quality --fires-out data/research/psf_fires.parquet`"
            )
    else:
        lines.append("- Per-fire parquet not written (run with `--fires-out` to generate).")
    lines.append("")

    # PSF win-rate falsifiers (PSF results carried for context).
    psf_fals = results["params"]["clean15_126"]["falsifiers"]
    psf_h1 = psf_fals.get("PSF_H1", {})
    psf_h2 = psf_fals.get("PSF_H2", {})
    b_psf1 = psf_h1.get("bootstrap_diff", {})
    b_psf2 = psf_h2.get("bootstrap_diff", {})
    lines += [
        "## PSF win-rate falsifiers (carried from predecessor test — context only)",
        "",
        f"- PSF-H1 (B−A win-rate): `{psf_h1.get('verdict', '—').upper()}` — "
        f"bootstrap CI {_fmt_ci(b_psf1.get('ci95'), pct=True)} (n_months={b_psf1.get('n_months', '—')})",
        f"- PSF-H2 (C−B win-rate): `{psf_h2.get('verdict', '—').upper()}` — "
        f"bootstrap CI {_fmt_ci(b_psf2.get('ci95'), pct=True)} (n_months={b_psf2.get('n_months', '—')})",
        f"- PSF KILL: `{'TRIGGERED' if psf_fals.get('KILL', {}).get('triggered') else 'not triggered'}`",
        "",
    ]

    # Adjudication placeholder.
    lines += [
        "## Adjudication (main loop)",
        "",
        "PENDING",
        "",
    ]

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Prophet × Stage quality re-grade (PSQ).")
    ap.add_argument("--root", default=None, help="Data root (defaults to repo data/).")
    ap.add_argument("--max-workers", type=int, default=4, help="Process pool (capped at 4).")
    ap.add_argument("--sample", type=int, default=None,
                    help="Sample the universe to N representative names (disclosed).")
    ap.add_argument("--ec-path", default=None, help="Override earnings_calls parquet path.")
    ap.add_argument("--fires-out", default=None,
                    help="Path for per-fire matured dump parquet (defaults to "
                         "data/research/psf_fires.parquet within the repo).")
    ap.add_argument("--no-report", action="store_true", help="Skip the markdown report.")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    from lib import config  # noqa: PLC0415
    data_root = Path(args.root) if args.root else config.data_dir()

    log.info("PSQ: building universe under %s", data_root)
    all_fires, results = run_single_pass(
        data_root, ec_path=args.ec_path,
        max_workers=args.max_workers, sample_n=args.sample,
    )
    log.info("PSQ: %d total fires across %d names with prices",
             results["n_fires_total"], results["universe"]["n_with_prices"])

    # Write the main JSON (PSF + PSQ combined).
    out_json = _REPO_ROOT / "data" / "research" / "psq_results.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_json = Path(tempfile.mktemp(dir=out_json.parent, suffix=".tmp"))
    tmp_json.write_text(json.dumps(results, indent=2, default=str))
    os.replace(tmp_json, out_json)
    log.info("PSQ: wrote %s", out_json)

    # Per-fire parquet dump.
    fires_path: Path | None = None
    fires_size: int | None = None
    fires_out_path = Path(args.fires_out) if args.fires_out else (
        _REPO_ROOT / "data" / "research" / "psf_fires.parquet")

    if all_fires:
        tbl = psf.build_psq_fires_table(all_fires, psf.EC_SENT_GATE)
        if not tbl.empty:
            fires_out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_pq = Path(tempfile.mktemp(dir=fires_out_path.parent, suffix=".tmp.parquet"))
            tbl.to_parquet(tmp_pq, index=False)
            fires_size = tmp_pq.stat().st_size
            os.replace(tmp_pq, fires_out_path)
            fires_path = fires_out_path
            size_mb = fires_size / 1024 / 1024
            if fires_size <= _FIRES_PARQUET_SIZE_LIMIT:
                log.info("PSQ: wrote %s (%.1f MB) — within 20 MB limit, committed", fires_out_path, size_mb)
            else:
                log.warning("PSQ: fires parquet is %.1f MB (> 20 MB) — must be gitignored", size_mb)
        else:
            log.warning("PSQ: fires table is empty — no parquet written")

    # Report.
    if not args.no_report:
        report = build_report(results, fires_path, fires_size)
        out_md = _REPO_ROOT / "research" / "reports" / "PROPHET_STAGE_QUALITY_RESULTS.md"
        out_md.parent.mkdir(parents=True, exist_ok=True)
        tmp_md = Path(tempfile.mktemp(dir=out_md.parent, suffix=".tmp.md"))
        tmp_md.write_text(report)
        os.replace(tmp_md, out_md)
        log.info("PSQ: wrote %s", out_md)

    # Print mechanical verdicts to stdout.
    psq = results.get("psq", {})
    print("=" * 60)
    print("PSQ MECHANICAL VERDICTS")
    print("=" * 60)
    for key in ("PSQ_H1", "PSQ_H2", "PSQ_H3"):
        v = psq.get(key, {})
        print(f"{key}: {v.get('verdict', 'NO-VERDICT')}  |  "
              f"CI={v.get('bootstrap', {}).get('ci95', [None, None])}  |  "
              f"diff={v.get('bootstrap', {}).get('diff_point')}")
    kill = psq.get("KILL_PSQ", {})
    print(f"KILL_PSQ: {'TRIGGERED' if kill.get('triggered') else 'not triggered'}")
    print("=" * 60)
    print(psf.PROXY_DISCLOSURE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
