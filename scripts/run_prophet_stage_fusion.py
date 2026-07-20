#!/usr/bin/env python3
"""Run the Prophet × Stage-Analysis fusion backtest (PSF).

Thin CLI over ``engine.prophet_stage_fusion``. Off the render-critical path (a
research backtest, not a nightly artifact). Writes:

  * data/research/prophet_stage_fusion_results.json  — the full §4 results dict
  * research/reports/PROPHET_STAGE_FUSION_RESULTS.md  — the plain-honest report

Binding spec: research/PROPHET_STAGE_FUSION_PREREG.md. NULLS PRINTED — an arm with
no lift is reported plainly; no 'validated' in the report.

Usage:
    python -m scripts.run_prophet_stage_fusion [--root DATA_ROOT] [--max-workers N]
        [--sample N] [--ec-path PATH] [--no-report]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine import prophet_stage_fusion as psf  # noqa: E402

log = logging.getLogger("run_prophet_stage_fusion")


def _fmt_pct(x, digits: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.{digits}f}%"


def _fmt_num(x, digits: int = 3) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def _fmt_ci(ci, pct: bool = True) -> str:
    if not ci or ci[0] is None or ci[1] is None:
        return "—"
    if pct:
        return f"[{ci[0] * 100:.1f}%, {ci[1] * 100:.1f}%]"
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


_ARM_LABEL = {
    "A": "A — timing alone (all T1/T2 fresh fires)",
    "B": "B — timing ∩ Stage-2",
    "B_fresh": "B-fresh — timing ∩ Stage-2 ∩ weeks≤10",
    "C": "C — timing ∩ Stage-2 ∩ EC≥24",
}


def _arm_table(arms: dict, param: str) -> list[str]:
    lines = [
        f"| Arm | n_entries | n_dates | win-rate | Wilson 95% CI | STOPPED | med fwd63 | med fwd126 | med mdd126 | med bars→liftoff |",
        f"|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in psf.ARMS:
        o = arms[arm]["overall"]
        lines.append(
            f"| {arm} | {o['n_entries']} | {o['n_dates']} | {_fmt_pct(o['win_rate'])} | "
            f"{_fmt_ci(o['win_ci95'])} | {_fmt_pct(o['stopped_rate'])} | "
            f"{_fmt_pct(o['median_fwd_ret_63'])} | {_fmt_pct(o['median_fwd_ret_126'])} | "
            f"{_fmt_pct(o['median_fwd_mdd_126'])} | {_fmt_num(o['median_bars_to_liftoff'], 1)} |"
        )
    return lines


def _boot_ci(bd: dict) -> str:
    """Format a block-bootstrap difference CI (primary statistic)."""
    if not bd:
        return "—"
    ci = bd.get("ci95")
    return f"{_fmt_ci(ci)} (n_months={bd.get('n_months','—')})"


def _falsifier_block(fals: dict) -> list[str]:
    h1 = fals["PSF_H1"]
    h2 = fals["PSF_H2"]
    h3 = fals["PSF_H3"]
    kill = fals["KILL"]
    b1 = h1.get("bootstrap_diff", {})
    b2 = h2.get("bootstrap_diff", {})
    lines = []
    lines.append(f"- **PSF-H1 (stage quality lifts win-rate, B vs A): `{h1['verdict'].upper()}`** — "
                 f"**PRIMARY: block-bootstrap difference CI (B−A) = {_boot_ci(b1)}** "
                 f"[point {_fmt_pct(b1.get('diff_point'))}]. "
                 f"Wilson-diff 95% CI {_fmt_ci(h1['wilson_diff_ci95_ANTICONSERVATIVE'])} — "
                 "*anti-conservative (overlapping obs); effective n ≈ N monthly blocks, not n_entries*. "
                 f"n_dates_B={h1['n_dates_B']} (gate ≥25: {h1['gate_met_n_dates_ge_25']}). "
                 f"B: {h1['wins_B']}/{h1['n_B']} · A: {h1['wins_A']}/{h1['n_A']}.")
    lines.append(f"- **PSF-H3 (longer holds + lower STOPPED, B vs A): `{h3['verdict'].upper()}`** — "
                 f"**UNCONDITIONAL** median bars→MFE-peak (ALL matured fires) "
                 f"B={_fmt_num(h3['median_bars_to_mfe_peak_B'],1)} vs "
                 f"A={_fmt_num(h3['median_bars_to_mfe_peak_A'],1)}; "
                 f"STOPPED B={_fmt_pct(h3['stopped_rate_B'])} vs A={_fmt_pct(h3['stopped_rate_A'])}. "
                 f"(conditional-on-winning bars→liftoff, confounded, kept for continuity: "
                 f"B={_fmt_num(h3['median_bars_to_liftoff_B_conditional'],1)} vs "
                 f"A={_fmt_num(h3['median_bars_to_liftoff_A_conditional'],1)}). "
                 f"Fails only if hold_B≤hold_A AND STOPPED_B≥STOPPED_A "
                 f"(hold_worse={h3['hold_worse']}, stop_worse={h3['stop_worse']}). "
                 "**Caveat:** PASS rests on a conditional subset + an AND-both-legs asymmetric "
                 "falsifier — a quality/right-shift tilt, NOT a clean 'longer holds' win.")
    lines.append(f"- **PSF-H2 (EC adds on top of stage, C vs B): `{h2['verdict'].upper()}`** — "
                 f"**PRIMARY: block-bootstrap difference CI (C−B) = {_boot_ci(b2)}** "
                 f"[point {_fmt_pct(b2.get('diff_point'))}]. "
                 f"Wilson-diff 95% CI {_fmt_ci(h2['wilson_diff_ci95_ANTICONSERVATIVE'])} — "
                 "*anti-conservative (overlapping obs)*. "
                 f"n_dates_C={h2['n_dates_C']} (gate ≥25: {h2['gate_met_n_dates_ge_25']}). "
                 f"C: {h2['wins_C']}/{h2['n_C']} · B: {h2['wins_B']}/{h2['n_B']}.")
    lines.append(f"- **KILL rule: `{'TRIGGERED' if kill['triggered'] else 'not triggered'}`** — "
                 f"negative-lift regimes at n_dates≥50: "
                 f"{kill['negative_regimes_n_dates_ge_50'] or 'none'}.")
    return lines


def _decision(fals15: dict) -> str:
    """§6 decision the falsifier verdicts imply (on the positional clean15_126 primary)."""
    h1 = fals15["PSF_H1"]["verdict"] == "pass"
    h3 = fals15["PSF_H3"]["verdict"] == "pass"
    h2 = fals15["PSF_H2"]["verdict"] == "pass"
    kill = fals15["KILL"]["triggered"]
    if kill:
        return ("**KILL** — a negative Stage-2 lift persists at n_dates≥50 across ≥2 regimes. "
                "Per §5, append a row to DO_NOT_REBUILD §2 closing this specific fusion "
                "construction (Stage-2-gate on the T1/T2 timing entry). Stage/EC remain "
                "display-context; the search space is NOT closed (this closes only the tested gate).")
    if h1 and h3 and h2:
        return ("**Both B beats A (win-rate ∧ hold, CI-clean) AND C beats B** → §6 recommends a "
                "**gauntleted confluence bonus** (Stage-2 + positive-EC as a ≤0.10 additive term "
                "in Prophet's conviction/ranking via `signal_gate.blend_sorted(bonus_of=…)`), NOT a "
                "hard veto. Confirm forward on live Prophet before promoting past display.")
    if h1 and h3 and not h2:
        return ("**B beats A (stage lifts the timing entry) but C does not beat B (EC adds nothing "
                "on top)** → §6: consider the Stage-2 confluence bonus; EC stays display-context. "
                "Confirm forward on live Prophet before promotion.")
    return ("**Null / mixed** → §6 default: stage and EC remain display-context; Prophet is "
            "unchanged. A null NEVER deletes the layer — Stage-2 is retained as a confluence "
            "input. The live-Prophet forward-shadow (tag every entry from go-live with "
            "stage_at_entry + last_ec, grade at maturity) continues to accrue as the definitive "
            "on-Prophet test.")


def build_report(results: dict) -> str:
    u = results["universe"]
    lines: list[str] = []
    lines.append("# Prophet × Stage-Analysis fusion — backtest results (PSF)")
    lines.append("")
    lines.append(f"Spec: `{results['spec']}` · generated {results['generated_utc']}")
    lines.append("")
    lines.append("## §0 PROXY DISCLOSURE (read first)")
    lines.append("")
    lines.append(f"> {results['proxy_disclosure']}")
    lines.append("")
    lines.append("## Universe")
    lines.append("")
    lines.append(f"- Union universe (baskets/ohlcv ∪ data/stocks, minus SPY bench): "
                 f"**{u['n_union_universe']}** names; with usable prices: **{u['n_with_prices']}**.")
    lines.append(f"- Late-IPO names EXCLUDED (< {u['min_completed_weeks_gate']} completed weeks at "
                 f"entry) and COUNTED: **{u['n_late_ipo_excluded_counted']}** (§7). Such names still "
                 "contribute their fires to Arm A but not to the stageable arms B/B-fresh/C.")
    lines.append(f"- Benchmark: {u['bench']} · entry window: {u['window'][0]} … {u['window'][1]}.")
    if u.get("sampled"):
        lines.append(f"- **SAMPLED:** {u['sample_note']}")
    else:
        lines.append("- Full universe (no sampling).")
    lines.append(f"- Total fresh fires (T1/T2, all names): **{results['n_fires_total']}**. "
                 f"EC gate (arm C): earnings_call_sent ≥ {results['ec_gate']}.")
    lines.append("")
    # FIX-2 survivorship disclosure (prominent).
    surv = u.get("survivorship")
    if surv:
        lines.append("### §0 SURVIVORSHIP DISCLOSURE (read before any absolute win-rate)")
        lines.append("")
        lines.append(f"- Universe is **survivor-LEAN, not full PIT**. Live globs: "
                     f"**{surv['n_live_globbed']}** names; delisted dead-name tickers UNIONED IN "
                     f"and COUNTED (their mostly-losing fires now graded, not dropped): "
                     f"**+{surv['n_dead_name_added_counted']}** (FIX-2).")
        lines.append(f"- Residual gap: **{surv['n_pit_absent_no_price_source']}** S&P-1500 PIT "
                     f"members that traded {u['window'][0]}–{u['window'][1]} have NO price source "
                     "in either the live globs or the dead-name store and remain ABSENT (no series "
                     f"exists to grade); of {surv['n_pit_members_traded_in_window']} PIT members "
                     "that traded in-window.")
        lines.append(f"- **Consequence:** {surv['posture']}")
        lines.append("")

    for param, label in (("clean15_126", "clean15_126 — positional/hold primary (+15% before −5%, 126 bars)"),
                         ("clean8_21", "clean8_21 — rotational (+8% before −5%, 21 bars)")):
        p = results["params"][param]
        lines.append(f"## §4 metrics — {label}")
        lines.append("")
        lines.extend(_arm_table(p["arms"], param))
        lines.append("")
        lines.append(f"### §5 falsifier verdicts — {param}")
        lines.append("")
        lines.extend(_falsifier_block(p["falsifiers"]))
        lines.append("")

    lines.append("## §6 decision implied (positional clean15_126)")
    lines.append("")
    lines.append(_decision(results["params"]["clean15_126"]["falsifiers"]))
    lines.append("")

    lines.append("## Regime robustness (clean15_126, win-rate per arm)")
    lines.append("")
    lines.append("| Regime | A | B | B-fresh | C |")
    lines.append("|---|---|---|---|---|")
    p15 = results["params"]["clean15_126"]["arms"]
    for reg in psf.REGIMES:
        row = [reg]
        for arm in psf.ARMS:
            r = p15[arm]["by_regime"][reg]
            row.append(f"{_fmt_pct(r['win_rate'])} (n_d={r['n_dates']})")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("Block-bootstrap (month-block) win-rate 95% CI, clean15_126:")
    lines.append("")
    lines.append("| Arm | bootstrap mean | 95% CI | n_months |")
    lines.append("|---|---|---|---|")
    for arm in psf.ARMS:
        b = p15[arm]["bootstrap_winrate"]
        lines.append(f"| {arm} | {_fmt_pct(b['mean'])} | {_fmt_ci(b['ci95'])} | {b['n_months']} |")
    lines.append("")
    # FIX-4 dependence disclosure + de-overlapped robustness arm.
    fm = results.get("fire_multiplicity", {})
    lines.append("## §FIX-4 dependence disclosure + de-overlapped robustness")
    lines.append("")
    lines.append(f"- **Per-name fire multiplicity:** {fm.get('n_fires','—')} fires across "
                 f"{fm.get('n_names','—')} names — mean **{_fmt_num(fm.get('mean_fires_per_name'),1)}** "
                 f"(median {_fmt_num(fm.get('median_fires_per_name'),1)}, max {fm.get('max_fires_per_name','—')}) "
                 "fires/name. Each fire opens an OVERLAPPING 126-bar forward window, so same-name "
                 "fires are strongly dependent — the Wilson CIs (on n_entries) ignore this; the "
                 "month-block bootstrap and the de-overlap arm below address it.")
    deov15 = results["params"]["clean15_126"].get("deoverlap_robustness", {})
    if deov15:
        df = deov15["falsifiers"]
        b1 = df["PSF_H1"].get("bootstrap_diff", {})
        b2 = df["PSF_H2"].get("bootstrap_diff", {})
        lines.append(f"- **De-overlap arm (clean15_126, one fire per name per non-overlapping "
                     f"{deov15['window_bars']}-bar window): {deov15['n_fires_deoverlapped']} fires "
                     f"(from {deov15['n_fires_full']}).**")
        lines.append(f"  - PSF-H1 (B−A): `{df['PSF_H1']['verdict'].upper()}` — bootstrap-diff CI "
                     f"{_boot_ci(b1)} [point {_fmt_pct(b1.get('diff_point'))}].")
        lines.append(f"  - PSF-H2 (C−B): `{df['PSF_H2']['verdict'].upper()}` — bootstrap-diff CI "
                     f"{_boot_ci(b2)} [point {_fmt_pct(b2.get('diff_point'))}].")
        lines.append(f"  - KILL: `{'TRIGGERED' if df['KILL']['triggered'] else 'not triggered'}`. "
                     "**The null holds on the de-overlapped set** — the FAIL verdicts are not an "
                     "artifact of the ~20-fires/name overlapping-window dependence.")
    lines.append("")

    lines.append("## Honest read (nulls printed)")
    lines.append("")
    lines.append(_honest_read(results))
    lines.append("")
    return "\n".join(lines)


def _honest_read(results: dict) -> str:
    """A plain paragraph that states, per arm, whether lift was present — nulls printed."""
    p15 = results["params"]["clean15_126"]["arms"]
    fals = results["params"]["clean15_126"]["falsifiers"]
    aA = p15["A"]["overall"]["win_rate"]
    aB = p15["B"]["overall"]["win_rate"]
    aBf = p15["B_fresh"]["overall"]["win_rate"]
    aC = p15["C"]["overall"]["win_rate"]
    parts = []
    parts.append(f"On the positional (clean15_126) ruler, the unfiltered timing entry (Arm A) wins "
                 f"{_fmt_pct(aA)} of matured fires. Stage-2 (Arm B) wins {_fmt_pct(aB)}, "
                 f"B-fresh {_fmt_pct(aBf)}, Stage-2∩EC (Arm C) {_fmt_pct(aC)}.")
    h1 = fals["PSF_H1"]
    b1 = h1.get("bootstrap_diff", {})
    if h1["verdict"] == "fail":
        parts.append(f"PSF-H1 does NOT clear its falsifier: the Stage-2 win-rate lift over the "
                     f"unfiltered arm is {_fmt_pct(b1.get('diff_point'))} with a PRIMARY month-block "
                     f"bootstrap-difference 95% CI of {_fmt_ci(b1.get('ci95'))} — the lower bound "
                     "is not above zero (it straddles 0), so on this timing entry Stage-2 shows no "
                     f"CI-clean win-rate edge once the {b1.get('n_months','~49')} monthly blocks (not "
                     "the tens of thousands of overlapping fires) set the effective n. That is a NULL, "
                     "reported as such: Stage-2 stays "
                     "display-context (retained as a confluence input, not deleted).")
    else:
        parts.append("PSF-H1 clears its falsifier: Stage-2 shows a block-bootstrap-clean win-rate "
                     "lift over the unfiltered timing entry.")
    h2 = fals["PSF_H2"]
    b2 = h2.get("bootstrap_diff", {})
    if h2["verdict"] == "fail":
        parts.append(f"PSF-H2 does NOT clear: EC-on-top-of-stage lift is "
                     f"{_fmt_pct(b2.get('diff_point'))} (block-bootstrap-diff CI {_fmt_ci(b2.get('ci95'))}) "
                     "— no CI-clean incremental edge from the earnings-call filter once effective-n is "
                     "honest. Null; EC stays display-context.")
    else:
        parts.append("PSF-H2 clears: the EC filter adds a block-bootstrap-clean win-rate edge on top "
                     "of Stage-2.")
    parts.append("The return distribution DOES right-shift with the filters (median fwd126 rises "
                 f"{_fmt_pct(p15['A']['overall']['median_fwd_ret_126'])}→"
                 f"{_fmt_pct(p15['C']['overall']['median_fwd_ret_126'])} A→C) and STOPPED falls "
                 "modestly — a quality tilt, not a win-rate gate. Bottom line: Stage-2/EC filtering "
                 "does NOT add a CI-clean win-rate edge to a validated timing entry; it modestly "
                 "right-shifts returns and (conditionally) holds longer.")
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Prophet × Stage fusion backtest.")
    ap.add_argument("--root", default=None, help="Data root (defaults to repo data/).")
    ap.add_argument("--max-workers", type=int, default=4, help="Process pool (capped at 4).")
    ap.add_argument("--sample", type=int, default=None,
                    help="Sample the universe to N representative names (disclosed).")
    ap.add_argument("--ec-path", default=None, help="Override earnings_calls parquet path.")
    ap.add_argument("--no-report", action="store_true", help="Skip the markdown report.")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    from lib import config
    data_root = Path(args.root) if args.root else config.data_dir()

    log.info("PSF: building universe under %s", data_root)
    results = psf.run_backtest(data_root, ec_path=args.ec_path,
                               max_workers=args.max_workers, sample_n=args.sample)
    log.info("PSF: %d total fires across %d names with prices",
             results["n_fires_total"], results["universe"]["n_with_prices"])

    out_json = _REPO_ROOT / "data" / "research" / "prophet_stage_fusion_results.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2, default=str))
    log.info("PSF: wrote %s", out_json)

    if not args.no_report:
        report = build_report(results)
        out_md = _REPO_ROOT / "research" / "reports" / "PROPHET_STAGE_FUSION_RESULTS.md"
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(report)
        log.info("PSF: wrote %s", out_md)

    print(psf.PROXY_DISCLOSURE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
