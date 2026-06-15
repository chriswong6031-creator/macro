"""Train + evaluate the BTC GBT meta-label leaf, and write an HONEST report.

Meta-labeling (López de Prado): the deterministic BTC allocation grid sets the SIDE;
a HistGradientBoostingClassifier learns P(that "be long" call is correct) over the
forward horizon from context features. It FILTERS / SIZES the bet — never direction.

This runner is the only place the leaf is exercised end-to-end. It:
  1. computes the Vector signals (engine.btc_signals.compute_all),
  2. runs engine.meta_label.run_meta_label (purged-OOF GBT, net-of-cost backtest of
     every label × CV-mode × size-scheme vs the primary baseline, Deflated Sharpe with
     n_trials = the configs tried, probability calibration),
  3. writes data/vector/meta_label.json + reports/meta-label-btc.md with the OOF
     metrics and a recommend-live / do-not-wire VERDICT.

The verdict is reported truthfully. The institutional-grade review anticipated that
meta-labeling may add NOTHING here — a valid, valuable outcome. We do not p-hack to a
positive: the same fixed grid + thresholds run every time.

Run: .venv/bin/python -m scripts.meta_label_btc
DEFAULT-OFF: writing this report does NOT enable the leaf or touch the live allocation.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine import btc_signals, meta_label  # noqa: E402
from lib import config  # noqa: E402


def _fmt_bt(d: dict) -> str:
    return (f"CAGR {d['cagr_pct']}% · Sharpe {d['sharpe']} · MaxDD {d['maxdd_pct']}% · "
            f"TiM {d['time_in_market_pct']}% · turn {d['turnover_annual']}/yr (n={d['n_obs']})")


def _markdown(r: dict) -> str:
    L = ["# Bitcoin meta-label (GBT) — honest evaluation\n"]
    if not r.get("available"):
        L.append(f"**Unavailable:** {r.get('reason')}\n")
        L.append("> The leaf degraded gracefully (never raised). Nothing was wired live.")
        return "\n".join(L)

    sel = r["selected"]
    L.append(f"_As of {r['asof']} · span {r['span']} · primary grid `alloc_"
             f"{r['primary_variant']}` · {r['n_events']} long calls over {r['n_bars']} bars_\n")
    L.append(f"## VERDICT: {'✅ ' if r['recommend_live'] else '🚫 '}{r['verdict']}\n")
    for c in r["verdict_checks"]:
        L.append(f"- {c}")
    L.append("\n> " + r["note"] + "\n")

    L.append("## What meta-labeling is\n")
    L.append("The **primary** model (the deterministic momentum × risk_index allocation "
             "grid) sets the **side**. The **secondary** GBT takes that call plus context "
             "and learns **P(the call is correct)** over the forward horizon — used to "
             "**filter / size**, never to pick direction. This is the one high-N layer "
             f"(~{r['n_events']} labeled long calls) where a tree won't just memorize noise.\n")

    L.append("## Selected meta strategy vs the primary baseline (net of cost)\n")
    L.append(f"Selected config: **{sel['label']} · {sel['mode']} · {sel['size']}** "
             f"(coverage {sel['cover']}).\n")
    L.append("| | CAGR | Sharpe | MaxDD | Time-in-mkt |")
    L.append("|---|---:|---:|---:|---:|")
    for lab, d in (("Primary baseline", sel["baseline"]), ("Meta-sized", sel["meta"])):
        L.append(f"| {lab} | {d['cagr_pct']}% | {d['sharpe']} | {d['maxdd_pct']}% | "
                 f"{d['time_in_market_pct']}% |")
    L.append(f"| **Δ (meta − base)** | {sel['d_cagr_pp']:+.1f}pp | {sel['d_sharpe']:+.3f} | "
             f"{sel['d_maxdd_pp']:+.1f}pp | |")
    L.append("\n_The verdict keys off the **walk-forward** (causal) backtest. CPCV "
             "(train on all other purged folds) is reported too — it uses more data but "
             "is non-causal, so it measures information content, not a tradeable curve._\n")

    dm, db = r.get("deflated_sharpe_meta"), r.get("deflated_sharpe_baseline")
    L.append("## Multiple-testing haircut (Deflated Sharpe)\n")
    if dm:
        L.append(f"- **Meta:** DSR **{dm['dsr']}** (SR {dm['sr_annual']} ann vs haircut "
                 f"SR0 {dm['sr0_annual']}); n_trials={dm['n_trials']}, T={dm['T']}d — "
                 f"_{r['dsr_verdict']}_")
    if db:
        L.append(f"- **Baseline:** DSR {db['dsr']} (SR {db['sr_annual']} ann), n_trials=1")
    L.append(f"\n_n_trials = every (label × CV-mode × size-scheme) strategy compared "
             f"= **{r['n_trials']}**. Overestimating is the conservative direction._\n")

    L.append("## Probability calibration (out-of-fold)\n")
    L.append("_Skill > 0 means the OOF probabilities beat the base-rate climatology; "
             "Platt a≈1, b≈0 means they need no recalibration. A heavily shrunk a (≪1) "
             "means the GBT's probabilities barely move with the truth — no information._\n")
    for lname, c in r.get("calibration", {}).items():
        if not c:
            continue
        pl = c.get("platt", {})
        sk = c.get("skill_score")
        read = "CALIBRATED w/ skill" if (sk is not None and sk > 0) else "NO skill (worse than base-rate)"
        L.append(f"- **{lname}** (h={c.get('horizon')}d): Brier {c.get('brier')} vs "
                 f"base {c.get('base_brier')} → skill **{sk}** → _{read}_; base-rate "
                 f"{c.get('base_rate')}; Platt a={pl.get('a')}, b={pl.get('b')}.")
    L.append("")

    L.append("## Full grid (every config tried)\n")
    L.append("| label | mode | size | n_oof | meta Sharpe | base Sharpe | ΔSharpe | ΔCAGR | ΔMaxDD |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for g in sorted(r["grid"], key=lambda x: -x["d_sharpe"]):
        L.append(f"| {g['label']} | {g['mode']} | {g['size']} | {g['n_oof']} | "
                 f"{g['meta']['sharpe']} | {g['baseline']['sharpe']} | {g['d_sharpe']:+.3f} | "
                 f"{g['d_cagr_pp']:+.1f}pp | {g['d_maxdd_pp']:+.1f}pp |")

    coll = r.get("collinearity") or {}
    if coll.get("vif"):
        L.append("\n## Feature collinearity (VIF)\n")
        top = list(coll["vif"].items())[:8]
        L.append(", ".join(f"{k} {v}" for k, v in top))
        if coll.get("redundant"):
            L.append(f"\nRedundant (VIF≥5): {', '.join(coll['redundant'])}")

    boot = r.get("bootstrap") or {}
    if boot:
        L.append("\n## Block-bootstrap CI (selected meta, net)\n")
        L.append(f"Sharpe 95% CI {boot.get('sharpe_ci')} · MaxDD% CI {boot.get('maxdd_ci_pct')} · "
                 f"P(Sharpe>0)={boot.get('sharpe_gt0_prob')}")

    L.append(f"\n## Features ({r['n_features']})\n")
    L.append(", ".join(f"`{f}`" for f in r["features"]))
    L.append(f"\nLabel base rates: " +
             ", ".join(f"{k} {v}" for k, v in r["label_base_rates"].items()))
    return "\n".join(L)


def _summary(r: dict) -> str:
    if not r.get("available"):
        return f"\n=== meta-label UNAVAILABLE: {r.get('reason')} (degraded, no crash) ===\n"
    sel = r["selected"]
    dm = r.get("deflated_sharpe_meta") or {}
    L = [f"\n=== BTC meta-label (GBT) — {r['span']}, {r['n_events']} long calls ==="]
    L.append(f"selected: {sel['label']} / {sel['mode']} / {sel['size']}")
    L.append(f"  baseline : {_fmt_bt(sel['baseline'])}")
    L.append(f"  meta     : {_fmt_bt(sel['meta'])}")
    L.append(f"  delta    : Sharpe {sel['d_sharpe']:+.3f} · CAGR {sel['d_cagr_pp']:+.1f}pp · "
             f"MaxDD {sel['d_maxdd_pp']:+.1f}pp")
    L.append(f"  DSR(meta)={dm.get('dsr')} over n_trials={r['n_trials']}  [{r['dsr_verdict']}]")
    for c in r["verdict_checks"]:
        L.append(f"  {c}")
    L.append(f"\nVERDICT: {'RECOMMEND LIVE' if r['recommend_live'] else 'DO NOT WIRE LIVE'}")
    L.append(r["verdict"])
    return "\n".join(L)


def main() -> int:
    cfg = config.load()["vector"].get("meta_label", {})
    df = btc_signals.compute_all()
    result = meta_label.run_meta_label(df, cfg)

    outdir = config.data_dir() / "vector"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "meta_label.json").write_text(json.dumps(result, indent=2, default=str))
    Path(config.load()["storage"]["reports_dir"], "meta-label-btc.md").write_text(_markdown(result))
    print(_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
