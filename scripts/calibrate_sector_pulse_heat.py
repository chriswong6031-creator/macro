"""Phase-0 kill-test of the Sector Pulse HEAT TIERS (heating/hot/cooling/broken/idle).

engine.sector_pulse assigns each of the 46 US theme baskets a descriptive heat tier from
rank/score velocity over the signal-archive streams. The tiers ship DISPLAY-ONLY per the
house validate-before-weight rule. This script asks the only question that could ever
change that: do the tiers carry a MEASURABLE forward edge, or are they texture?

PRE-REGISTERED CLAIMS (all vs the same-day "idle" baseline, 21d horizon, primary):
  heating  -> higher forward 21d RELATIVE return than idle, OR SHALLOWER forward 21d
              max drawdown than idle (either leg clears -> measurable).
  hot      -> same two legs as heating (context tier — top-quartile persistence).
  cooling  -> DEEPER forward 21d max drawdown than idle.
  broken   -> DEEPER forward 21d max drawdown than idle.
  idle     -> the baseline; carries no claim by construction.

MEASUREMENT (house conventions, mirrors scripts.calibrate_baskets):
  * The tier classifier is IMPORTED from engine.sector_pulse (_heat_tier) — the shipped
    code path, never a re-implementation. Labels come from engine.theme_scoring._label.
  * Primary inference = HAC (Newey-West) t on the SAME-DAY paired difference
    mean(metric | tier) - mean(metric | idle), one obs per sampled bar (the sector panel
    co-moves within a day, so pooled t-stats overstate |t|). |t| >= HAC_FLOOR_T (2.0)
    with the claimed sign, AND Benjamini-Hochberg reject at q<=0.10 across the 6-cell
    panel (heating/hot x rel21+dd21, cooling/broken x dd21) -> "measurable_edge".
  * Per-tier absolute event studies (calibrate_baskets._event_study) are reported as
    context; split-half (2013 boundary) reported for every primary cell.
  * Sampling every STEP=5 bars de-overlaps; HAC lags = ceil(21/STEP) mop up the rest.

UNIVERSES:
  proxy    9-11 SPDR sector ETFs, ~27y daily — the GO/NO-GO substrate. Rank series are
           reconstructed point-in-time from the RS-derived proxy score (the same
           cross-sectional rank-by-score that defines the live board), heat from the
           shipped _heat_tier at daily resolution (exact 5-session deltas).
           BOARD-WIDTH CAVEAT: +/-3 rank positions is ~27% of an 11-wide proxy board vs
           ~6.5% of the 46-wide live board, so the proxy UNDER-fires the rank-delta legs;
           the score-delta (>=6pts) and label legs are board-width-free. A sensitivity
           pass re-runs with +/-1 (the same board SHARE as live +/-3) — reported, never
           the verdict cell.
  live     the US theme baskets, ~3y, HINDSIGHT-curated membership — descriptive
           context only, never a gate (same caveat as calibrate_baskets.run_live).
  archive  the accruing engine.signal_archive 'baskets' stream — the REAL shipped
           rank/score/label snapshots. Graded whenever a snapshot has >=21 subsequent
           sessions of basket tape; until the stream is deep enough this lane only
           reports accrual status (rerun bar recorded in the artifact).

VERDICT: written to data/strategies/sector_pulse_heat.json (baskets_calibration.json
pattern). engine.sector_pulse._heat_strength reads ONLY the per-tier verdict to set the
displayed grade (backtested vs descriptive/unconfirmed) — heat NEVER binds a score or a
weight regardless of outcome. A refutation is recorded, not deleted.

Usage:  python -m scripts.calibrate_sector_pulse_heat [--no-live]
Additive / never fatal.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V                      # noqa: E402
from engine import sector_pulse as SP                   # noqa: E402
from engine.sector_pulse import _heat_tier              # noqa: E402
from engine.theme_scoring import _label, WEIGHTS        # noqa: E402
from engine.trial_ledger import TrialLedger             # noqa: E402
from lib import config                                  # noqa: E402
from scripts.calibrate_baskets import (                 # noqa: E402
    BH_Q, DD_RISK, FWD_H, HAC_FLOOR_T, LF_SPLIT, STEP, Z_LB,
    _adj, _breadth_leg, _crowd_pen, _event_study, _f, _fwd_dd, _fwd_rel,
    _panel_breadth, _proxy_score, _rel, _rs_features, _trend_leg,
    REGION_SECTORS, sector_prices,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("calibrate_sector_pulse_heat")

TIERS = ("heating", "hot", "cooling", "broken", "idle")
CLAIM = {"heating": "continuation", "hot": "continuation",
         "cooling": "risk", "broken": "risk", "idle": "continuation"}
# the pre-registered 6-cell primary panel: (tier, metric, wanted sign of tier-minus-idle)
PANEL = (("heating", "rel21", +1), ("heating", "dd21", +1),
         ("hot", "rel21", +1), ("hot", "dd21", +1),
         ("cooling", "dd21", -1), ("broken", "dd21", -1))


# --------------------------------------------------------------------------- #
# shared: paired same-day tier-vs-idle difference (the primary claim)
# --------------------------------------------------------------------------- #
def _paired_vs_idle(vals: np.ndarray, tiers: np.ndarray, ev: np.ndarray,
                    tier: str, pre: np.ndarray) -> dict:
    """HAC t of the per-bar difference mean(vals|tier) - mean(vals|idle). One obs per
    sampled bar that has BOTH a tier row and an idle row (paired by construction —
    fwd drawdown is <=0 everywhere, so only the same-day diff is a claim)."""
    ok = np.isfinite(vals)
    diffs, dpre = [], []
    for b in np.unique(ev[ok & (tiers == tier)]):
        day = ok & (ev == b)
        f, u = day & (tiers == tier), day & (tiers == "idle")
        if f.any() and u.any():
            diffs.append(float(vals[f].mean() - vals[u].mean()))
            dpre.append(bool(pre[day & (tiers == tier)][0]))
    if len(diffs) < 8:
        return {"t_hac": None, "p_hac": None, "mean_pct": None, "n_days": len(diffs)}
    nw = V.newey_west_tstat(np.array(diffs), lags=int(np.ceil(21 / STEP)))
    d, m = np.array(diffs), np.array(dpre)
    half = {}
    for name, msk in (("pre2013", m), ("post2013", ~m)):
        half[name] = {"mean_pct": round(100 * float(d[msk].mean()), 2) if msk.any() else None,
                      "n_days": int(msk.sum())}
    return {"t_hac": nw["t"], "p_hac": nw["p"],
            "mean_pct": round(100 * (nw["mean"] or 0), 2), "n_days": len(diffs),
            "split_half": half}


def _paired_panel(rows: np.ndarray, tiers: np.ndarray) -> dict:
    """Run the 6-cell primary panel + BH-FDR across it. rows columns:
    rel21, dd21, bar, pre2013."""
    rel21, dd21, ev, pre = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3].astype(bool)
    out, pvals = {}, {}
    for tier, metric, want in PANEL:
        cell = f"{tier}_{metric}"
        rec = _paired_vs_idle(rel21 if metric == "rel21" else dd21, tiers, ev, tier, pre)
        rec["claim_sign"] = want
        if rec.get("p_hac") is not None:
            pvals[cell] = rec["p_hac"]
        out[cell] = rec
    for cell, q in (V.benjamini_hochberg(pvals, alpha=BH_Q) if pvals else {}).items():
        out[cell]["bh_q"] = q["q"]
        out[cell]["bh_reject"] = q["reject"]
    return out


def _cell_measurable(rec: dict) -> bool:
    t = rec.get("t_hac")
    return (t is not None and rec.get("mean_pct") is not None
            and np.sign(rec["mean_pct"] or 0) == rec["claim_sign"]
            and abs(t) >= HAC_FLOOR_T and bool(rec.get("bh_reject")))


def _cell_inverted(rec: dict) -> bool:
    t = rec.get("t_hac")
    return (t is not None and rec.get("mean_pct") is not None
            and np.sign(rec["mean_pct"] or 0) == -rec["claim_sign"] and abs(t) >= HAC_FLOOR_T)


# --------------------------------------------------------------------------- #
# PROXY universe — 27y SPDR sectors, the GO/NO-GO substrate
# --------------------------------------------------------------------------- #
def _proxy_daily_states(P: pd.DataFrame, spy: pd.Series,
                        breadth: pd.DataFrame, feats: dict) -> tuple[np.ndarray, np.ndarray]:
    """Daily (score, label) per (day, sector) — daily resolution because the live
    rank_delta_5d is 'exactly 5 sessions back', not 'previous sampled bar'."""
    idx, cols = P.index, list(P.columns)
    start = max(Z_LB, 200)
    score = np.full((len(idx), len(cols)), np.nan)
    labels = np.full((len(idx), len(cols)), None, dtype=object)
    bnp = {k: breadth[k].to_numpy() for k in ("pct50", "pct200", "nh", "nl", "net_nh")}
    arrs = {c: {k: feats[c][k].to_numpy()
                for k in ("accel_z", "rs_pctile", "r5", "r20", "r60", "delta_5d")}
            for c in cols}
    Pv = {c: P[c].to_numpy() for c in cols}
    for i in range(start, len(idx)):
        for j, c in enumerate(cols):
            if not np.isfinite(Pv[c][i]):
                continue
            a = arrs[c]
            az, rp = a["accel_z"][i], a["rs_pctile"][i]
            if not (np.isfinite(az) and np.isfinite(rp)):
                continue
            r5, r20, r60, d5 = a["r5"][i], a["r20"][i], a["r60"][i], a["delta_5d"][i]
            trend = _trend_leg(r5, r20, r60, float(az))
            bl = _breadth_leg(bnp["pct50"][i], bnp["pct200"][i], bnp["net_nh"][i])
            sc = _proxy_score(trend, bl, _crowd_pen(float(rp)))
            fp = {"accel_z": float(az), "rs_pctile": float(rp)}
            perf = {"5d": {"rel": _f(r5)}, "20d": {"rel": _f(r20)}, "60d": {"rel": _f(r60)}}
            bdict = {"pct50": _f(bnp["pct50"][i]), "nh": int(bnp["nh"][i]),
                     "nl": int(bnp["nl"][i])}
            score[i, j] = sc
            labels[i, j] = _label(sc, fp, perf, bdict, _f(d5))
    return score, labels


def _heat_events(P: pd.DataFrame, spy_v: np.ndarray, score: np.ndarray,
                 labels: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    """Sample every STEP bars; classify heat with the SHIPPED _heat_tier from the
    reconstructed rank/score state; collect forward outcomes. A row requires a valid
    state at BOTH i and i-5 (the live tier with missing history degrades to idle-ish;
    the backtest keeps the event definition clean instead)."""
    idx = P.index
    S = pd.DataFrame(score, index=idx, columns=P.columns)
    R = S.rank(axis=1, ascending=False, method="first")   # rank 1 = best, like the board
    nvalid = S.notna().sum(axis=1).to_numpy()
    Rv, Sv = R.to_numpy(), S.to_numpy()
    Pv = {c: P[c].to_numpy() for c in P.columns}
    events: dict = {k: [] for k in TIERS}
    rows, tier_seq = [], []
    for i in range(max(Z_LB, 200) + 5, len(idx) - max(FWD_H) - 1, STEP):
        for j, c in enumerate(P.columns):
            if not (np.isfinite(Sv[i, j]) and np.isfinite(Sv[i - 5, j])):
                continue
            rd5 = int(Rv[i - 5, j] - Rv[i, j])            # + = rank improved (number fell)
            sd5 = float(Sv[i, j] - Sv[i - 5, j])
            heat = _heat_tier(int(Rv[i, j]), int(nvalid[i]), labels[i, j], rd5, sd5)
            px = Pv[c]
            fr21, fr63 = _fwd_rel(px, spy_v, i, 21), _fwd_rel(px, spy_v, i, 63)
            dd21, dd63 = _fwd_dd(px, i, 21), _fwd_dd(px, i, 63)
            if not np.isfinite(fr21):
                continue
            events[heat].append((fr21, fr63, dd21, dd63, i))
            rows.append((fr21, dd21, float(i), 1.0 if idx[i] < LF_SPLIT else 0.0))
            tier_seq.append(heat)
    return events, np.array(rows, float), np.array(tier_seq, dtype=object)


def run_heat_proxy(region: str = "us") -> dict:
    spec = REGION_SECTORS[region]
    P = sector_prices(region, monthly=False)
    spy = _adj(spec["bench"], spec["group"])
    if P.empty or spy is None or P.shape[1] < 4:
        return {"error": "insufficient proxy data"}
    spy = spy.reindex(P.index).ffill()
    breadth = _panel_breadth(P)
    feats = {c: _rs_features(P[c].dropna().reindex(P.index), spy) for c in P.columns}
    spy_v = spy.to_numpy()

    log.info("proxy: reconstructing daily score/label states…")
    score, labels = _proxy_daily_states(P, spy, breadth, feats)

    log.info("proxy: heat events at the shipped ±3/6pt thresholds…")
    events, rows, tiers = _heat_events(P, spy_v, score, labels)
    if len(rows) < 500:
        return {"error": "thin", "n": len(rows)}
    tier_days = {t: int(np.unique(rows[tiers == t][:, 2]).size) for t in TIERS}
    out = {"universe": "proxy_spdr_sectors", "n_assets": int(P.shape[1]),
           "span": [str(P.index.min().date()), str(P.index.max().date())],
           "n_rows": int(len(rows)), "tier_days": tier_days,
           "tier_n": {t: int((tiers == t).sum()) for t in TIERS},
           "board_width_note": ("±3 rank positions ≈27% of the 11-wide proxy board vs "
                                "≈6.5% of the 46-wide live board — the proxy UNDER-fires "
                                "the rank-delta legs; score-delta/label legs are width-free. "
                                "sensitivity_rank1 re-runs at ±1 (live board share)."),
           "tiers": _event_study(events, CLAIM),
           "paired_vs_idle": _paired_panel(rows, tiers)}

    # sensitivity: rank-delta thresholds at the live board SHARE (±1 of 11 ≈ ±3 of 46).
    # Monkeypatch the module constants so the classifier code path stays the shipped one.
    log.info("proxy: sensitivity pass at ±1 rank threshold…")
    heat0, cool0 = SP._HEAT_RANK_DELTA, SP._COOL_RANK_DELTA
    try:
        SP._HEAT_RANK_DELTA, SP._COOL_RANK_DELTA = 1, -1
        _, rows1, tiers1 = _heat_events(P, spy_v, score, labels)
        out["sensitivity_rank1"] = {
            "tier_n": {t: int((tiers1 == t).sum()) for t in TIERS},
            "paired_vs_idle": _paired_panel(rows1, tiers1)}
    finally:
        SP._HEAT_RANK_DELTA, SP._COOL_RANK_DELTA = heat0, cool0
    return out


# --------------------------------------------------------------------------- #
# LIVE universe — ~3y theme baskets, descriptive context only
# --------------------------------------------------------------------------- #
def run_heat_live(region: str = "us") -> dict:
    """Full-fidelity heat reconstruction on the hindsight-curated basket tape. Scores
    on a 5-session grid (grid spacing == the live 5-session look-back, so rank/score
    deltas are exact); ranks are the cross-section of baskets scored that bar."""
    try:
        from engine import group_flow, theme_scoring as TS
        from engine.baskets import _ew_level
        s = group_flow._setup()
        if s is None:
            return {"error": "no live setup"}
        closes, rets, idx, bench = s["closes"], s["rets"], s["idx"], s["bench"]
        cfg = group_flow._cfg()
        bdict = s["mem"]["baskets"]
        items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
        bench_v = bench.to_numpy()
        grid = list(range(max(cfg["min_history_d"], 200), len(idx) - max(FWD_H) - 1, STEP))
        if len(grid) < 10:
            return {"error": "tape too short"}

        # per-basket state at every grid bar: (score, label, lvl_v)
        state: dict[str, dict] = {}
        lvls: dict[str, np.ndarray] = {}
        for bid, b in items:
            members = b.get("members", [])
            present = [m["ticker"] for m in members if m["ticker"] in rets.columns]
            if len(present) < 3:
                continue
            lvl = _ew_level(rets, members, idx)
            if lvl.dropna().empty:
                continue
            mask = pd.DataFrame(False, index=idx, columns=present)
            for m in members:
                t = m["ticker"]
                if t not in present:
                    continue
                act = np.asarray(idx >= pd.Timestamp(m["added"]))
                if m.get("removed"):
                    act = act & np.asarray(idx < pd.Timestamp(m["removed"]))
                mask[t] = act
            mc_closes = closes[present].where(mask)
            prep = group_flow.prep_group(mc_closes, lvl, bench, cfg)
            if prep is None:
                continue
            lvl_v = lvl.to_numpy()
            st = {}
            for i in grid:
                fp = group_flow.fingerprint_at(prep, i, cfg)
                if fp is None:
                    continue
                trend = _trend_leg(_rel(lvl_v, bench_v, i, 5), _rel(lvl_v, bench_v, i, 20),
                                   _rel(lvl_v, bench_v, i, 60), fp.get("accel_z"))
                bl, bd = TS._breadth_leg(mc_closes, i, fp)
                il, _ = TS._impulse_leg(rets[present].where(mask), mc_closes, i)
                cp, _ = TS._crowding_pen(fp, {"breadth": None}, None)
                raw = (WEIGHTS["trend"] * trend + WEIGHTS["breadth"] * bl
                       + WEIGHTS["impulse"] * il - WEIGHTS["crowding"] * cp)
                sc = int(round(50 + 50 * float(np.clip(raw, -1, 1))))
                perf = {"5d": {"rel": _rel(lvl_v, bench_v, i, 5)},
                        "20d": {"rel": _rel(lvl_v, bench_v, i, 20)},
                        "60d": {"rel": _rel(lvl_v, bench_v, i, 60)}}
                st[i] = (sc, _label(sc, fp, perf, bd, _rel(lvl_v, bench_v, i, 5)))
            if st:
                state[bid] = st
                lvls[bid] = lvl_v
        if len(state) < 5:
            return {"error": "too few scoreable baskets", "n": len(state)}

        # cross-sectional ranks per grid bar, then heat + forward outcomes
        events: dict = {k: [] for k in TIERS}
        rows, tier_seq = [], []
        for k in range(1, len(grid)):
            i, ip = grid[k], grid[k - 1]
            day = {bid: st[i] for bid, st in state.items() if i in st}
            prev = {bid: st[ip] for bid, st in state.items() if ip in st}
            if len(day) < 5:
                continue
            order = sorted(day, key=lambda b: -day[b][0])
            rank = {b: r + 1 for r, b in enumerate(order)}
            prev_order = sorted(prev, key=lambda b: -prev[b][0])
            prev_rank = {b: r + 1 for r, b in enumerate(prev_order)}
            for bid, (sc, lab) in day.items():
                if bid not in prev_rank:
                    continue
                rd5 = prev_rank[bid] - rank[bid]
                sd5 = float(sc - prev[bid][0])
                heat = _heat_tier(rank[bid], len(day), lab, rd5, sd5)
                lvl_v = lvls[bid]
                fr21, fr63 = _fwd_rel(lvl_v, bench_v, i, 21), _fwd_rel(lvl_v, bench_v, i, 63)
                dd21, dd63 = _fwd_dd(lvl_v, i, 21), _fwd_dd(lvl_v, i, 63)
                if not np.isfinite(fr21):
                    continue
                events[heat].append((fr21, fr63, dd21, dd63, i))
                rows.append((fr21, dd21, float(i), 1.0 if idx[i] < LF_SPLIT else 0.0))
                tier_seq.append(heat)
        if len(rows) < 100:
            return {"error": "thin", "n": len(rows)}
        rows, tiers = np.array(rows, float), np.array(tier_seq, dtype=object)
        return {"universe": "live_baskets", "n_baskets": len(state),
                "span": [str(idx.min().date()), str(idx.max().date())],
                "n_rows": int(len(rows)),
                "tier_n": {t: int((tiers == t).sum()) for t in TIERS},
                "tiers": _event_study(events, CLAIM),
                "paired_vs_idle": _paired_panel(rows, tiers),
                "warning": ("HINDSIGHT-curated membership, ~3y, survivorship-biased — "
                            "descriptive context only, NEVER a gate.")}
    except Exception as e:  # noqa: BLE001 — live leg is best-effort context
        log.warning("live universe skipped: %s", e)
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# ARCHIVE lane — the real shipped snapshots; grades accrue as the stream deepens
# --------------------------------------------------------------------------- #
def run_heat_archive() -> dict:
    """Reconstruct heat from the REAL archived rank/score/label snapshots (the exact
    inputs the live pulse reads) and grade any snapshot with >=21 subsequent sessions
    of tape. Today the stream is days deep — this lane records accrual status and the
    re-run bar; each re-run grades whatever has matured since."""
    try:
        snaps = SP._load_archive_snapshots("us")
        if not snaps:
            return {"error": "no archive"}
        n_heat, gradeable = 0, 0
        tier_counts = {t: 0 for t in TIERS}
        for k in range(5, len(snaps)):
            cur = {t["id"]: t for t in snaps[k]["themes"]
                   if t.get("id") and t.get("rank") and t.get("score") is not None}
            old = {t["id"]: t for t in snaps[k - 5]["themes"]
                   if t.get("id") and t.get("rank") and t.get("score") is not None}
            n = len(cur)
            for tid, th in cur.items():
                if tid not in old:
                    continue
                rd5 = old[tid]["rank"] - th["rank"]
                sd5 = float(th["score"] - old[tid]["score"])
                heat = _heat_tier(th["rank"], n, th.get("label", "neutral"), rd5, sd5)
                tier_counts[heat] += 1
                n_heat += 1
        # 21d-forward maturity: sessions counted on the archive's own daily cadence
        gradeable = max(0, len(snaps) - 5 - 21)
        return {"stream": "baskets", "n_snapshots": len(snaps),
                "span": [snaps[0]["asof"], snaps[-1]["asof"]],
                "n_heat_rows": n_heat, "tier_counts": tier_counts,
                "n_gradeable_21d": gradeable,
                "rerun_bar": (">=90 archived sessions (~4.5 months) before the archive "
                              "lane can confirm/deny the proxy verdict; re-run this "
                              "script then (grades accrue automatically)."),
                "note": ("Heat reconstructed from the REAL shipped snapshots — validates "
                         "the reconstruction machinery on live data even before forward "
                         "windows mature.")}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# verdict — the only block engine.sector_pulse._heat_strength reads
# --------------------------------------------------------------------------- #
def _heat_verdict(proxy: dict) -> dict:
    """Distil the proxy paired-vs-idle panel into per-tier verdicts. Continuation tiers
    (heating/hot) pass on EITHER leg (rel21 higher OR dd21 shallower); risk tiers on the
    dd21-deeper leg. 'inverted' flags a significant OPPOSITE-sign read — an honesty
    tripwire (a 'heating' chip that measurably precedes UNDERperformance must never be
    upgraded, and the note calls it out)."""
    cells = proxy.get("paired_vs_idle", {}) or {}
    out = {}
    for tier in ("heating", "hot", "cooling", "broken"):
        legs = [c for (t, m, _s) in PANEL if t == tier for c in [f"{t}_{m}"]]
        recs = {c: cells.get(c, {}) for c in legs}
        via = next((c for c, r in recs.items() if _cell_measurable(r)), None)
        inverted = [c for c, r in recs.items() if _cell_inverted(r)]
        best = recs.get(via) if via else (recs.get(legs[0]) or {})
        out[tier] = {"claim": ("fwd 21d rel-return / drawdown vs same-day idle"
                               if CLAIM[tier] == "continuation"
                               else "fwd 21d drawdown deeper than same-day idle"),
                     "verdict": ("measurable_edge" if via else
                                 ("thin" if best.get("t_hac") is None else "not_measurable")),
                     "via": via, "inverted": inverted or None,
                     "t_hac": best.get("t_hac"), "mean_pct": best.get("mean_pct"),
                     "n_days": best.get("n_days"), "bh_q": best.get("bh_q")}
    out["idle"] = {"verdict": "baseline", "claim": None}
    out["GO"] = any(out[t]["verdict"] == "measurable_edge"
                    for t in ("heating", "hot", "cooling", "broken"))
    out["decision"] = "grades_upgraded" if out["GO"] else "display_only_refuted"
    out["note"] = ("Verdict controls ONLY the displayed grade (backtested vs descriptive/"
                   "unconfirmed) via sector_pulse._heat_strength — heat tiers never bind "
                   "a score, a reco or a weight regardless of outcome "
                   "(validate-before-weight). Measured on the 27y US proxy; cited "
                   "cross-market the way baskets_calibration is.")
    return out


def _print_lane(name: str, lane: dict) -> None:
    if lane.get("error"):
        print(f"\n=== {name}: {lane['error']} ===")
        return
    print(f"\n=== {name} ({lane.get('universe', lane.get('stream'))}, "
          f"span {lane.get('span')}) ===")
    tn = lane.get("tier_n") or lane.get("tier_counts") or {}
    print("  tier n:", {k: v for k, v in tn.items()})
    for cell, r in (lane.get("paired_vs_idle") or {}).items():
        print(f"  {cell:16s} diff {str(r.get('mean_pct')):>7}%  t {str(r.get('t_hac')):>7}  "
              f"n_days {str(r.get('n_days')):>4}  BHq {str(r.get('bh_q', '—')):>7}  "
              f"{'MEASURABLE' if _cell_measurable(r) else ('INVERTED' if _cell_inverted(r) else '')}")


def main(do_live: bool = True) -> int:
    led = TrialLedger()
    led.log_grid([{"tier": t, "metric": m} for (t, m, _s) in PANEL]
                 + [{"tier": t, "metric": m, "rank_thresh": 1} for (t, m, _s) in PANEL],
                 family="sector_pulse_heat", info_cutoff="2026-07-03",
                 source="calibrate_sector_pulse_heat")
    led.log_declared_budget(16, family="sector_pulse_heat",
                            reason="6-cell primary panel + 6-cell board-width sensitivity "
                                   "+ design variants considered (baseline choice, "
                                   "horizon, live/archive lanes)")

    out = {"schema": "sector_pulse_heat.v1", "region": "us",
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "fwd_horizons_d": list(FWD_H), "step_d": STEP, "dd_risk": DD_RISK,
           "hac_floor_t": HAC_FLOOR_T, "bh_q": BH_Q,
           "classifier": {"source": "engine.sector_pulse._heat_tier (imported, shipped)",
                          "rank_delta_5d_thresh": SP._HEAT_RANK_DELTA,
                          "cool_rank_delta_5d_thresh": SP._COOL_RANK_DELTA,
                          "score_delta_5d_thresh": SP._HEAT_SCORE_DELTA},
           "n_trials": led.effective_n("sector_pulse_heat")}

    log.info("running PROXY heat kill-test (27y SPDR sectors)…")
    out["proxy"] = run_heat_proxy("us")
    _print_lane("PROXY (GO/NO-GO)", out["proxy"])
    if out["proxy"].get("sensitivity_rank1"):
        _print_lane("PROXY sensitivity ±1 rank",
                    {"universe": "proxy ±1", "span": out["proxy"].get("span"),
                     **out["proxy"]["sensitivity_rank1"]})

    if do_live:
        log.info("running LIVE basket lane (descriptive)…")
        out["live"] = run_heat_live("us")
        _print_lane("LIVE (descriptive)", out["live"])

    log.info("running ARCHIVE lane (accruing)…")
    out["archive"] = run_heat_archive()
    a = out["archive"]
    if not a.get("error"):
        print(f"\n=== ARCHIVE ({a['stream']}, {a['n_snapshots']} snaps "
              f"{a['span'][0]}→{a['span'][1]}) ===")
        print(f"  heat rows {a['n_heat_rows']}  tiers {a['tier_counts']}  "
              f"gradeable-21d {a['n_gradeable_21d']}")

    out["verdict"] = _heat_verdict(out["proxy"]) if not out["proxy"].get("error") \
        else {"GO": False, "decision": "display_only_refuted",
              "error": out["proxy"].get("error")}
    v = out["verdict"]
    summary = {t: v[t]["verdict"] for t in ("heating", "hot", "cooling", "broken") if t in v}
    print(f"\n  VERDICT: {summary}")
    print(f"  GO {v.get('GO')} → {v.get('decision')}")

    p = config.data_dir() / "strategies" / "sector_pulse_heat.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", p)
    return 0


if __name__ == "__main__":
    sys.exit(main("--no-live" not in sys.argv))
