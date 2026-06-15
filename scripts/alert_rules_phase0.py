"""Phase-0 event study for the condition-based macro ALERT RULES.

The Alert Command Center shows a measured hit-rate only where engine.signal_lab
validated the signal family.  The condition-based macro rules (hy_oas_widening,
net_liquidity_roc_flip, nfci_tightening, sahm_trigger, ebp_widening,
drawdown_risk_high, capitulation_signal, recession-band cross) carried documented
conviction but NO backtest.  This harness earns — or refuses — those numbers.

For each rule we reconstruct its historical firings over the full features frame
(faithful to engine/alerts.py thresholds), then run an event study on forward
SPY returns at 1 / 5 / 20 / 60 trading days:

  • hit-rate in the thesis direction (risk-off rules → P(fwd<0); the contrarian
    capitulation rule → P(fwd>0)), vs the unconditional base rate;
  • mean conditional forward return vs base, and the uplift;
  • a Newey-West (HAC) t-stat of (conditional − base mean) with lags = horizon,
    so the autocorrelation from overlapping windows AND event clustering doesn't
    overstate significance;
  • n_events and n_clusters (firings > horizon apart = independent windows) — the
    honest power, since risk-off events bunch in crises;
  • Benjamini-Hochberg FDR across the whole (rule × horizon) panel.

A rule EARNS a per-horizon hit-rate only if it is thesis-significant, survives
FDR, and has enough independent clusters.  Output: data/alerts/rule_scorecard.json
(read live by engine.alert_triage, mirroring ic_scorecard.json) + a printed table.

Run:  .venv/bin/python -m scripts.alert_rules_phase0
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from engine import inputs
from engine.conditions import conditions_frame
from engine.validation import benjamini_hochberg, newey_west_tstat
from lib import config

HORIZONS = [1, 5, 20, 60]
MIN_CLUSTERS = 8           # below this, power is too low to earn a number
FDR_ALPHA = 0.10


def _norm(s: pd.Series, idx: pd.Index) -> pd.Series:
    return s.reindex(idx).fillna(False).astype(bool)


def build_triggers(f: pd.DataFrame, cf: pd.DataFrame) -> dict[str, dict]:
    """Each rule → {label, thesis ('down'=risk-off, 'up'=contrarian/bullish),
    events (bool Series aligned to f.index)}. Faithful to engine/alerts.py."""
    a = config.load()["alerts"]
    idx = f.index
    out: dict[str, dict] = {}

    # hy_oas_widening: 1d OAS change z > 2.5 (252d window)
    oas = f["hy_oas"].dropna()
    chg = oas.diff()
    z = (chg - chg.rolling(252).mean()) / chg.rolling(252).std()
    out["hy_oas_widening"] = {"label": "HY OAS 1-day widening spike",
        "thesis": "down", "events": _norm(z > a["hy_oas_1d_widening_z"], idx)}

    # nfci_tightening: NFCI upward cross of threshold
    s = f["nfci"]
    out["nfci_tightening"] = {"label": "NFCI tightens above threshold",
        "thesis": "down", "events": _norm((s.shift(1) < a["nfci_tightening_z"]) & (s >= a["nfci_tightening_z"]), idx)}

    # sahm_trigger: Sahm crosses 0.50
    s = f["sahm"]
    out["sahm_trigger"] = {"label": "Sahm rule triggers (0.50)",
        "thesis": "down", "events": _norm((s.shift(1) < a["sahm_trigger"]) & (s >= a["sahm_trigger"]), idx)}

    # ebp_widening: distinct monthly EBP change z > 2.0 (36mo)
    ebp = f["ebp"].dropna()
    dis = ebp[ebp.ne(ebp.shift())]
    dchg = dis.diff()
    ez = (dchg - dchg.rolling(36).mean()) / dchg.rolling(36).std()
    out["ebp_widening"] = {"label": "Excess Bond Premium spike",
        "thesis": "down", "events": _norm(ez > a["ebp_widening_z"], idx)}

    # drawdown_risk_high: macro-stress gauge crosses into high band (>=80)
    s = cf["drawdown_risk"]
    out["drawdown_risk_high"] = {"label": "Macro-stress gauge → HIGH band",
        "thesis": "down", "events": _norm((s.shift(1) < a["drawdown_risk_high"]) & (s >= a["drawdown_risk_high"]), idx)}

    # conditions_recession_state_change (worsening): recession_risk crosses into high (>=55)
    rc = config.load()["engine"]["conditions"]["recession"]
    s = cf["recession_risk"]
    out["recession_high"] = {"label": "Recession-risk band → HIGH",
        "thesis": "down", "events": _norm((s.shift(1) < rc["high_score"]) & (s >= rc["high_score"]), idx)}

    # capitulation_signal: capitulation_score crosses into strong (>=2) — CONTRARIAN
    s = cf["capitulation_score"]
    out["capitulation_signal"] = {"label": "Capitulation gauge fires (contrarian)",
        "thesis": "up", "events": _norm((s.shift(1) < a["capitulation_strong"]) & (s >= a["capitulation_strong"]), idx)}

    # net_liquidity_roc_flip: 20d RoC flips sign, holds 2d, |roc|>=25bn — split by direction
    w = config.load()["engine"]["liquidity"]["roc_window_d"]
    db = a["net_liquidity_roc_deadband_bn"]
    roc = f["net_liquidity_bn"] - f["net_liquidity_bn"].shift(w)
    sg = np.sign(roc)
    flip = (sg != sg.shift(2)) & (sg == sg.shift(1)) & (sg != 0) & (roc.abs() >= db)
    out["net_liq_expand"] = {"label": "Net-liquidity RoC flips POSITIVE (expanding)",
        "thesis": "up", "events": _norm(flip & (roc > 0), idx)}
    out["net_liq_contract"] = {"label": "Net-liquidity RoC flips NEGATIVE (contracting)",
        "thesis": "down", "events": _norm(flip & (roc < 0), idx)}
    return out


def _clusters(dates: pd.DatetimeIndex, spy_idx: pd.DatetimeIndex, h: int) -> int:
    """Count firings separated by more than `h` trading days = independent windows."""
    if len(dates) == 0:
        return 0
    pos = pd.Series(np.arange(len(spy_idx)), index=spy_idx)
    ords = pos.reindex(dates).dropna().sort_values().values
    if len(ords) == 0:
        return 0
    n, last = 1, ords[0]
    for o in ords[1:]:
        if o - last > h:
            n += 1
            last = o
    return n


def event_study(events: pd.Series, spy: pd.Series, thesis: str) -> dict:
    """Forward-SPY event study at each horizon. thesis: 'down' favours fwd<0."""
    ev_dates = events[events].index
    res = {}
    for h in HORIZONS:
        fwd = spy.shift(-h) / spy - 1.0
        base = fwd.dropna()
        cond = fwd.reindex(ev_dates).dropna()
        if len(cond) < 3 or len(base) < 50:
            res[str(h)] = {"n": int(len(cond)), "insufficient": True}
            continue
        fav = (lambda x: x < 0) if thesis == "down" else (lambda x: x > 0)
        hit = float(fav(cond).mean())
        base_hit = float(fav(base).mean())
        mean_c, mean_b = float(cond.mean()), float(base.mean())
        # HAC t-stat of (conditional − base mean); one-sided in the thesis direction
        nw = newey_west_tstat(cond.values - mean_b, lags=h)
        t = nw["t"]
        p2 = nw["p"]
        if t is None or p2 is None:
            p_one = None
        else:
            favourable_sign = (t < 0) if thesis == "down" else (t > 0)
            p_one = (p2 / 2.0) if favourable_sign else (1.0 - p2 / 2.0)
        res[str(h)] = {
            "n": int(len(cond)),
            "n_clusters": _clusters(ev_dates, spy.index, h),
            "hit": round(hit, 3), "base_hit": round(base_hit, 3),
            "hit_uplift": round(hit - base_hit, 3),
            "mean": round(mean_c, 4), "base_mean": round(mean_b, 4),
            "mean_uplift": round(mean_c - mean_b, 4),
            "t_hac": t, "p_one": None if p_one is None else round(p_one, 4),
        }
    return res


def main() -> int:
    f = inputs.build_features()
    cf = conditions_frame(f)
    spy = f["SPY"].dropna()
    trig = build_triggers(f, cf)

    rules: dict[str, dict] = {}
    pvals: dict[str, float] = {}
    for key, spec in trig.items():
        study = event_study(spec["events"], spy, spec["thesis"])
        ev_dates = spec["events"][spec["events"]].index
        ev_in_spy = ev_dates[(ev_dates >= spy.index.min()) & (ev_dates <= spy.index.max())]
        rules[key] = {"label": spec["label"], "thesis": spec["thesis"],
                      "n_events": int(len(ev_in_spy)),
                      "span": (f"{ev_in_spy.min():%Y-%m-%d}..{ev_in_spy.max():%Y-%m-%d}"
                               if len(ev_in_spy) else "—"),
                      "horizons": study}
        for h, r in study.items():
            if not r.get("insufficient") and r.get("p_one") is not None:
                pvals[f"{key}@{h}"] = r["p_one"]

    fdr = benjamini_hochberg(pvals, alpha=FDR_ALPHA)
    for key, rd in rules.items():
        earned_h = []
        for h, r in rd["horizons"].items():
            tag = fdr.get(f"{key}@{h}")
            if tag:
                r["q_fdr"] = tag["q"]
                r["survives"] = bool(tag["reject"] and r.get("n_clusters", 0) >= MIN_CLUSTERS)
                if r["survives"]:
                    earned_h.append(h)
        rd["earned_horizons"] = earned_h
        # 3-way verdict, kept honest: earned (FDR-survivor with power) /
        # no_edge (adequately powered but failed) / underpowered (too few
        # independent events to test at all — NOT the same as "no edge").
        powered = max((r.get("n_clusters", 0) for r in rd["horizons"].values()
                       if not r.get("insufficient")), default=0)
        tested = any(r.get("p_one") is not None for r in rd["horizons"].values())
        if earned_h:
            rd["verdict"] = "earned"
        elif powered >= MIN_CLUSTERS and tested:
            rd["verdict"] = "no_edge"
        else:
            rd["verdict"] = "underpowered"
        # the headline number the page shows: longest earned horizon (most decision-useful)
        rd["headline_horizon"] = (max(earned_h, key=int) if earned_h else None)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "target": "SPY", "horizons_d": HORIZONS,
        "span": f"{spy.index.min():%Y-%m-%d}..{spy.index.max():%Y-%m-%d}",
        "method": "event study; forward SPY return; Newey-West HAC (lags=h); "
                  "BH-FDR across rule×horizon; earned = FDR-survive AND "
                  f">= {MIN_CLUSTERS} independent clusters.",
        "fdr_alpha": FDR_ALPHA, "min_clusters": MIN_CLUSTERS,
        "n_earned": sum(1 for r in rules.values() if r["verdict"] == "earned"),
        "rules": rules,
    }
    outp = config.data_dir() / "alerts" / "rule_scorecard.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(payload, indent=2, default=str))

    # printed summary
    print(f"\nAlert-rule Phase-0 — event study on {payload['target']} ({payload['span']})")
    print(f"{'rule':26s} {'thesis':7s} {'n/clust':>8s}  " + "  ".join(f"{h}d hit/uplift/q" for h in HORIZONS))
    for key, rd in rules.items():
        line = f"{key:26s} {rd['thesis']:7s} {rd['n_events']:>4d}/{rd['horizons'].get('20',{}).get('n_clusters','-'):<3}"
        cells = []
        for h in HORIZONS:
            r = rd["horizons"][str(h)]
            if r.get("insufficient"):
                cells.append(f"{'n<3':>16s}")
            else:
                star = "*" if r.get("survives") else " "
                cells.append(f"{r['hit']:.2f}/{r['hit_uplift']:+.2f}/{r.get('q_fdr','-')}{star:>1s}")
        print(line + "  " + "  ".join(cells) + f"   => {rd['verdict'].upper()}"
              + (f" @{rd['headline_horizon']}d" if rd['headline_horizon'] else ""))
    print(f"\nEARNED: {payload['n_earned']} of {len(rules)} rules. wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
