"""Independent, deep audit of the China narrative-rotation engine (allocation_china).

Goes beyond scripts/thematic_rotation_phase0.py (which tests a 12-1 momentum PROXY on 16
shallow A-share sector ETFs, ~8.5y) by validating the engine's ACTUAL composite score on a
deeper, survivorship-clean universe and answering the question the owner asked: is this a
predictive engine, or a reactive trend/momentum CONFIRMER?

UNIVERSES
  shenwan   the 31 Shenwan (申万) L1 industry indices (engine.china_sector_index.sw_close),
            continuous indices deep to 1999/2014/2021 — survivorship-clean and far deeper
            than the ETF proxy. The honest testbed to VALIDATE the algorithm on.
  baskets   the 22 live curated A-share theme baskets (engine.baskets_china EW levels), ~5y,
            HINDSIGHT-curated — the live PRODUCT universe, run for CONTEXT only, FLAGGED.

SIGNAL (faithful to engine.narrative_rotation.rank_themes, replicated at the index level)
  score = mean( z(resid_mom_1y) , z(13612W) ) + 0.25·z(accel)
    resid_mom_1y = 1y cumprod (skip last 21d) of the index's MARKET-RESIDUAL return
                   e = r - β·r_bench (causal rolling-252 β, shrunk 0.66 → 1), bench = 000001.SS
    13612W       = engine._mom_13612w(level)         (12·1m + 4·3m + 2·6m + 1·12m)
    accel        = engine._accel(level/bench)        (RS acceleration)
  eligible (abs-trend gate) = engine._abs_gate(level): price>200dma AND 12m return>0

TESTS
  1 rank_ic      cross-sectional Spearman rank-IC of `score` → forward 1m/3m/6m returns,
                 monthly; mean, Newey-West(HAC) t, hit-rate, n; train(<2019)/test(>=2019)
                 sign-stability; label-permutation p-value for mean 1m IC.
  2 leadlag      IC( score_t , 1-month return of month t+k ) for k=-6..+6 — the confirmer
                 test: peak at k<=0 (past/contemporaneous) = lagging confirmer; sustained
                 IC at k>=+1 = genuine lead.
  3 book         the engine's actual book (equal-weight top-4 ELIGIBLE by score, cash for
                 empty slots, 10bps turnover) vs CSI300 buy-hold vs EW-all buy-hold:
                 CAGR/Sharpe/MaxDD/Calmar/DSR/IR; + the trend-gate drawdown effect
                 (gated dual book vs ungated rel book vs EW).

Usage:  python -m scripts.allocation_china_audit
Writes: data/strategies/allocation_china_audit.json  (+ prints a summary)  Additive.
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

from engine import china_sector_index as csi  # noqa: E402
from engine import narrative_rotation as nr    # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("alloc_china_audit")

TY = 12
COST = 0.0010                 # 10 bps / unit turnover (matches the engine Phase-0)
TRAIN_END = "2018-12-31"      # train/test split for sign-stability


# --------------------------------------------------------------- data panels ----
def _shenwan_daily() -> pd.DataFrame:
    from engine.china_sector_cycles import _SW
    cols = {}
    for code in _SW:
        s = csi.sw_close(code)
        if s is not None and len(s) > 300:
            cols[code] = s
    return pd.DataFrame(cols).sort_index()


def _basket_daily() -> pd.DataFrame:
    from engine.baskets_china import compute_china_baskets
    d = compute_china_baskets()
    if not d or not d.get("chart"):
        return pd.DataFrame()
    ch = d["chart"]
    idx = pd.to_datetime(ch["dates"])
    return pd.DataFrame({k: v for k, v in ch["baskets"].items()}, index=idx).sort_index()


# ----------------------------------------------------- engine-faithful signals ----
def _resid_mom_daily(P: pd.DataFrame, bench_ret: pd.Series,
                     win: int = 252, shrink: float = 0.66) -> pd.DataFrame:
    """Daily 1y (skip 21d) cumulative MARKET-RESIDUAL momentum per column — the index-level
    analogue of engine.narrative_rotation resid_mom (causal rolling β shrunk toward 1)."""
    R = P.pct_change(fill_method=None)
    m = bench_ret.reindex(R.index)
    minp = max(win // 2, 60)
    var = m.rolling(win, min_periods=minp).var()
    out = {}
    for c in P.columns:
        beta = R[c].rolling(win, min_periods=minp).cov(m).div(var).shift(1)
        beta = (shrink * beta + (1.0 - shrink)).clip(-2.0, 3.0)
        e = R[c] - beta * m
        log1p = np.log1p(e.clip(-0.95, 10))
        cum = np.expm1(log1p.rolling(252).sum().shift(21))     # 1y resid cumprod, skip last 21d
        out[c] = cum
    return pd.DataFrame(out)


def _mom13612_daily(P: pd.DataFrame) -> pd.DataFrame:
    legs = [(12, 21), (4, 63), (2, 126), (1, 252)]
    acc = sum(w * (P / P.shift(d) - 1.0) for w, d in legs)
    return acc.where(P.shift(252).notna())


def _accel_daily(rs: pd.DataFrame, w: int = 63) -> pd.DataFrame:
    return (rs / rs.shift(w) - 1.0) - (rs.shift(w) / rs.shift(2 * w) - 1.0)


def _gate_daily(P: pd.DataFrame) -> pd.DataFrame:
    sma = P.rolling(nr.SMA_TREND_D, min_periods=nr.SMA_TREND_D // 2).mean()
    r12 = P / P.shift(252) - 1.0
    return (P > sma) & (r12 > 0)


def _xs_z(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional (row-wise) z-score; rows with <3 finite values → NaN (engine rule)."""
    valid = df.notna().sum(axis=1) >= 3
    mu = df.mean(axis=1)
    sd = df.std(axis=1).replace(0, np.nan)
    z = df.sub(mu, axis=0).div(sd, axis=0)
    return z.where(valid, np.nan)


def build_signals(P_daily: pd.DataFrame, bench_daily: pd.Series) -> dict:
    """Month-end panels of the engine's composite score, its legs, the gate, and forward
    returns — all leak-free (signals from data<=t, forward returns strictly after)."""
    idx = P_daily.index
    bench = bench_daily.reindex(idx).ffill()
    bret = bench.pct_change(fill_method=None)
    rs = P_daily.div(bench, axis=0)

    resid = _resid_mom_daily(P_daily, bret)
    mom = _mom13612_daily(P_daily)
    acc = _accel_daily(rs)
    gate = _gate_daily(P_daily)

    me = P_daily.resample("ME").last().index
    def at_me(df):
        return df.reindex(P_daily.index).ffill().reindex(me)
    rm_m, mom_m, acc_m, gate_m = at_me(resid), at_me(mom), at_me(acc), at_me(gate).fillna(False)

    score = (_xs_z(rm_m) + _xs_z(mom_m)) / 2.0 + 0.25 * _xs_z(acc_m)
    # engine rule: base needs >=1 of the two mom legs; keep where score finite
    M = P_daily.resample("ME").last()
    return {"month_idx": me, "M": M, "score": score, "gate": gate_m,
            "rm_z": _xs_z(rm_m), "mom_z": _xs_z(mom_m), "acc_z": _xs_z(acc_m),
            "bench_m": bench.resample("ME").last()}


# ------------------------------------------------------------------- stats ----
def _nw_t(x, lag: int):
    x = np.asarray([v for v in x if np.isfinite(v)], float)
    n = len(x)
    if n < 8:
        return None, n
    mu = x.mean(); e = x - mu
    s = (e @ e) / n
    for l in range(1, min(lag, n - 1) + 1):
        w = 1.0 - l / (lag + 1.0)
        s += 2.0 * w * (e[l:] @ e[:-l]) / n
    se = np.sqrt(s / n) if s > 0 else None
    return (float(mu / se) if se else None), n


def _spear_row(a: pd.Series, b: pd.Series):
    d = pd.concat([a, b], axis=1).dropna()
    if len(d) < 5:
        return None
    return float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank()))


def rank_ic(sig: dict, horizons=(1, 3, 6)) -> dict:
    M, score, me = sig["M"], sig["score"], sig["month_idx"]
    out = {}
    for h in horizons:
        fwd = M.shift(-h) / M - 1.0
        ics, dates = [], []
        for t in me:
            ic = _spear_row(score.loc[t], fwd.loc[t]) if t in fwd.index else None
            if ic is not None:
                ics.append(ic); dates.append(t)
        ser = pd.Series(ics, index=pd.DatetimeIndex(dates))
        t_hac, n = _nw_t(ser.values, lag=max(h, 2))
        train = ser[ser.index <= TRAIN_END]; test = ser[ser.index > TRAIN_END]
        out[f"{h}m"] = {
            "mean_ic": round(float(ser.mean()), 4), "median_ic": round(float(ser.median()), 4),
            "t_hac": round(t_hac, 2) if t_hac is not None else None,
            "hit": round(float((ser > 0).mean()), 3), "n": int(n),
            "train_ic": round(float(train.mean()), 4) if len(train) else None,
            "test_ic": round(float(test.mean()), 4) if len(test) else None,
            "sign_stable": bool(len(train) and len(test) and np.sign(train.mean()) == np.sign(test.mean())
                                and abs(test.mean()) > 0.005),
        }
        if h == 1:
            out[f"{h}m"]["perm_p"] = _perm_p(score, fwd, me)
    return out


def _perm_p(score: pd.DataFrame, fwd: pd.DataFrame, me, n_perm: int = 1000) -> float:
    """Label-permutation p for mean 1m IC: shuffle forward returns across sectors each month."""
    rng = np.random.default_rng(7)
    actual, perms = [], np.zeros(n_perm)
    rows = []
    for t in me:
        if t not in fwd.index:
            continue
        d = pd.concat([score.loc[t], fwd.loc[t]], axis=1).dropna()
        if len(d) < 5:
            continue
        sr = d.iloc[:, 0].rank().values
        fr = d.iloc[:, 1].rank().values
        rows.append((sr, fr))
        actual.append(np.corrcoef(sr, fr)[0, 1])
    if not rows:
        return None
    am = float(np.mean(actual))
    for j in range(n_perm):
        vals = []
        for sr, fr in rows:
            vals.append(np.corrcoef(sr, rng.permutation(fr))[0, 1])
        perms[j] = np.mean(vals)
    p = float((perms >= am).mean()) if am >= 0 else float((perms <= am).mean())
    return round(p, 4)


def lead_lag(sig: dict, ks=range(-6, 7)) -> dict:
    """IC( score_t , 1-month return of month t+k ). k<0 past, 0 just-ended month (skipped by
    score), k>0 future. Confirmer ⇔ IC peaks at k<=0 and ≈0 for k>=1."""
    M, score, me = sig["M"], sig["score"], sig["month_idx"]
    rm = M.pct_change()
    prof = {}
    for k in ks:
        shifted = rm.shift(-k)        # month t+k return aligned to t
        ics = [ _spear_row(score.loc[t], shifted.loc[t]) for t in me if t in shifted.index ]
        ics = [x for x in ics if x is not None]
        prof[int(k)] = round(float(np.mean(ics)), 4) if ics else None
    return prof


# ------------------------------------------------------------- book backtest ----
def _audit_ledger(name: str):
    """Honest, COUNTED multiple-testing N for the DSR below: an EPHEMERAL Trial Ledger that
    logs, at generation, the 8 return-series this universe sweeps (3 hold horizons × {gated
    dual, rel no-gate} + 2 buy-hold baselines) and lets `deflated_sharpe` count them — never a
    caller-asserted literal that could be lowballed (the keystone ratchet; see
    research/SELF_IMPROVING_AI_SUITE.md + tests/test_no_literal_ntrials.py). Kept in system
    temp, out of the production ledger AND the repo tree, so a manual audit never inflates a
    real family's count nor gets swept into the daily `git add data/`. Returns (ledger, family)."""
    import tempfile
    from engine.trial_ledger import TrialLedger
    fam = f"allocation_china_audit::{name}"
    path = Path(tempfile.gettempdir()) / f"_alloc_china_audit_{name}.jsonl"
    if path.exists():
        path.unlink()
    led = TrialLedger(path=path, family=fam)
    grid = [{"book": "dual" if g else "rel", "gate": g, "hold_m": h}
            for h in (1, 3, 6) for g in (True, False)]
    grid += [{"book": "ew_buyhold"}, {"book": "shanghai_buyhold"}]
    led.log_grid(grid, family=fam)                # 8 distinct configs → effective_n == 8
    return led, fam


def _stats(R: pd.Series, bench_m_ret: pd.Series | None = None, *,
           ledger=None, family: str | None = None) -> dict:
    R = R.dropna()
    if len(R) < 12:
        return {}
    eq = (1 + R).cumprod()
    yrs = len(R) / TY
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1)
    sharpe = float(R.mean() / R.std() * np.sqrt(TY)) if R.std() > 0 else None
    mdd = float((eq / eq.cummax() - 1).min())
    out = {"cagr": round(cagr, 4), "sharpe": round(sharpe, 2) if sharpe else None,
           "max_dd": round(mdd, 4), "calmar": round(float(cagr / abs(mdd)), 2) if mdd < 0 else None,
           "n_months": int(len(R))}
    try:
        from engine.validation import deflated_sharpe
        sr_m = R.mean() / R.std() if R.std() > 0 else 0.0
        # N is COUNTED from the Trial Ledger at generation, not a caller-asserted literal.
        dsr = deflated_sharpe(sr_m, float(R.skew()), float(R.kurtosis() + 3.0), len(R),
                              ledger=ledger, family=family, trading_year=TY)
        if dsr is not None:
            out["dsr"] = round(float(dsr.get("dsr", dsr) if isinstance(dsr, dict) else dsr), 3)
    except Exception:  # noqa: BLE001
        pass
    if bench_m_ret is not None:
        b = bench_m_ret.reindex(R.index)
        act = (R - b).dropna()
        if len(act) > 12 and act.std() > 0:
            out["ir_vs_bench"] = round(float(act.mean() / act.std() * np.sqrt(TY)), 2)
        worst = b < b.quantile(0.10)
        if worst.sum() >= 5:
            out["worst_decile_ret"] = round(float(R[worst].mean()), 4)
    return out


def book(sig: dict, top_n: int, gate: bool, hold: int = 1, cost: float = COST) -> tuple[pd.Series, dict]:
    """Rebalance every `hold` months (the live engine is low-turnover — monthly churn is the
    worst case in a mean-reverting tape). Hold the selected EW top-N for `hold` months; cost
    is charged only on rebalance turnover; idle/ungated slots sit in cash @ 0%."""
    M, score, gate_m, me = sig["M"], sig["score"], sig["gate"], sig["month_idx"]
    rm_next = M.pct_change().shift(-1)            # rm_next.loc[t] = return of month t+1
    held = pd.Series(0.0, index=M.columns)
    wp = pd.Series(0.0, index=M.columns)
    rows, cash_hist = [], []
    for i, t in enumerate(me[:-1]):
        turn = 0.0
        if i % hold == 0:                        # refresh the signal only every `hold` months
            sc = score.loc[t].dropna()
            if gate:
                elig = gate_m.loc[t].reindex(sc.index).fillna(False)
                sc = sc[elig]
            top = sc.sort_values(ascending=False).head(top_n).index
            w = pd.Series(0.0, index=M.columns)
            if len(top):
                w[top] = 1.0 / top_n
            turn = float((w - wp).abs().sum())
            held, wp = w, w
        cash_hist.append(1.0 - float(held.sum()))
        r = float((held * rm_next.loc[t]).sum()) - turn * cost
        rows.append((me[i + 1], r))
    return pd.Series(dict(rows)), {"top_n": top_n, "gated": gate, "hold_m": hold,
                                   "avg_cash": round(float(np.mean(cash_hist)), 3) if cash_hist else None}


def rank_ic_nonoverlap(sig: dict, h: int) -> dict:
    """De-overlapped rank-IC: sample every h-th month so the forward windows don't overlap
    (overlapping monthly sampling of an h-month forward return inflates the HAC t)."""
    M, score, me = sig["M"], sig["score"], sig["month_idx"]
    fwd = M.shift(-h) / M - 1.0
    ics, dates = [], []
    for j in range(0, len(me), h):
        t = me[j]
        ic = _spear_row(score.loc[t], fwd.loc[t]) if t in fwd.index else None
        if ic is not None:
            ics.append(ic); dates.append(t)
    ser = pd.Series(ics, index=pd.DatetimeIndex(dates))
    t_hac, n = _nw_t(ser.values, lag=1)
    return {"mean_ic": round(float(ser.mean()), 4) if len(ser) else None,
            "t_hac": round(t_hac, 2) if t_hac is not None else None, "n": int(n)}


def run_universe(name: str, P: pd.DataFrame, bench_daily: pd.Series, contaminated: bool) -> dict:
    sig = build_signals(P, bench_daily)
    bench_m_ret = sig["bench_m"].pct_change()
    ew = P.resample("ME").last().pct_change().mean(axis=1)
    led, fam = _audit_ledger(name)        # counted multiple-testing N shared by every DSR below
    ric = rank_ic(sig)
    ric["6m_nonoverlap"] = rank_ic_nonoverlap(sig, 6)        # de-overlapped significance check
    # book at the engine's realistic low-turnover hold horizons (monthly churn = worst case)
    book_by_hold = {}
    for h in (1, 3, 6):
        dual_R, dmeta = book(sig, nr.N_HOLD, gate=True, hold=h)
        rel_R, _ = book(sig, nr.N_HOLD, gate=False, hold=h)
        bd = _stats(dual_R, bench_m_ret, ledger=led, family=fam); bd["avg_cash"] = dmeta["avg_cash"]
        book_by_hold[f"hold_{h}m"] = {"engine_top4_dual": bd,
                                      "top4_rel_nogate": _stats(rel_R, bench_m_ret, ledger=led, family=fam)}
    return {
        "n_assets": int(P.shape[1]),
        "span": [str(P.index.min().date()), str(P.index.max().date())],
        "contaminated": contaminated,
        "rank_ic": ric,
        "lead_lag": lead_lag(sig),
        "book_by_hold": book_by_hold,
        "baselines": {
            "ew_buyhold": _stats(ew, bench_m_ret, ledger=led, family=fam),
            "shanghai_composite_buyhold": _stats(bench_m_ret.reindex(ew.index), ledger=led, family=fam),  # 000001.SS (not CSI300)
        },
    }


def main() -> int:
    out = {"schema": "allocation_china_audit.v1",
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "cost_bps": COST * 1e4, "train_test_split": TRAIN_END, "universes": {}}
    bench = csi.benchmark_close()
    if bench is None:
        log.error("no benchmark (000001.SS) — abort"); return 0

    Psw = _shenwan_daily()
    if Psw.shape[1] >= 10:
        out["universes"]["shenwan"] = run_universe("shenwan", Psw, bench, contaminated=False)
        log.info("shenwan: %d sectors %s", Psw.shape[1], out["universes"]["shenwan"]["span"])

    try:
        Pb = _basket_daily()
        if not Pb.empty and Pb.shape[1] >= 5:
            out["universes"]["baskets"] = run_universe("baskets", Pb, bench, contaminated=True)
            out["universes"]["baskets"]["warning"] = (
                "HINDSIGHT-curated membership + ~5y + 22 names — underpowered & survivorship-"
                "biased. Context only, never a validation.")
            log.info("baskets: %d themes %s", Pb.shape[1], out["universes"]["baskets"]["span"])
    except Exception as e:  # noqa: BLE001
        log.warning("basket universe skipped: %s", e)

    p = config.data_dir() / "strategies" / "allocation_china_audit.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", p)

    # human summary
    for uname, u in out["universes"].items():
        print(f"\n########## {uname.upper()} ({u['n_assets']} assets {u['span'][0]}→{u['span'][1]}"
              f"{', CONTAMINATED' if u['contaminated'] else ''}) ##########")
        ic = u["rank_ic"]
        for h in ("1m", "3m", "6m"):
            r = ic[h]
            extra = f" perm_p={r.get('perm_p')}" if "perm_p" in r else ""
            print(f"  rank-IC {h}: mean {r['mean_ic']:+.4f} (t_hac {r['t_hac']}) hit {r['hit']} "
                  f"n={r['n']} | train {r['train_ic']} test {r['test_ic']} sign_stable={r['sign_stable']}{extra}")
        no = ic.get("6m_nonoverlap", {})
        print(f"  rank-IC 6m NON-OVERLAP: mean {no.get('mean_ic')} (t_hac {no.get('t_hac')}) n={no.get('n')}")
        ll = u["lead_lag"]
        print("  LEAD/LAG IC( score_t , ret_{t+k} ):")
        print("   k:   " + "  ".join(f"{k:+d}" for k in sorted(ll, key=int)))
        print("   IC:  " + "  ".join(f"{(ll[k] if ll[k] is not None else 0):+.2f}" for k in sorted(ll, key=int)))
        print("  BOOK by hold horizon (engine top-4 dual / top-4 rel no-gate):")
        for hk, hv in u["book_by_hold"].items():
            d, rl = hv["engine_top4_dual"], hv["top4_rel_nogate"]
            print(f"   {hk:9} dual: CAGR {d['cagr']*100:5.2f}% Sharpe {d.get('sharpe')} MaxDD {d['max_dd']*100:6.1f}% "
                  f"cash~{d.get('avg_cash')} | rel: CAGR {rl['cagr']*100:5.2f}% MaxDD {rl['max_dd']*100:6.1f}%")
        for k, s in u["baselines"].items():
            if s:
                print(f"   {k:28} CAGR {s['cagr']*100:5.2f}%  Sharpe {s.get('sharpe')}  MaxDD {s['max_dd']*100:6.1f}%  IR {s.get('ir_vs_bench')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
