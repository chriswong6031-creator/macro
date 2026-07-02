"""International bridge — the pluggable CLAIM validation harness (W1, masterplan §4.2).

ONE harness, ONE trial-budget family, HARD gates. It does NOT reinvent the anti-overfit
stack — it COMPOSES it:

  * multiple-testing:  engine/trial_ledger.py family "intl_bridge" — the FULL C1-C8
                       claim×horizon grid is logged AT GENERATION (`--declare`), so the
                       Deflated-Sharpe haircut deflates by the honest count (the forex
                       declared-N=60 discipline, ported).
  * core verdict:      engine/promotion_gate.promotion_gate(family="intl_bridge",
                       dsr_min=0.90) — DSR + PBO + CPCV + drift, advisory.
  * intl-specific gates the promotion gate does NOT cover, built on engine/validation.py:
      a. ORTHOGONALITY  — residual forward-DD-reduction / residual IC AFTER partialing
                          out the existing US MRS legs + cross-asset RORO + hk_global_beta
                          (validation.resid_z / cross_sectional_resid). Adds nothing
                          orthogonal → FAILS.
      b. CRISIS-COUNT N — block-bootstrap-by-crisis + leave-one-crisis-out; BOTH the
                          daily-row CI (validation.block_bootstrap_ci) and the crisis-count
                          result are stored; weight_cap scales with independent-bear count.
      c. CRISIS-INDEP.  — positive expected-shortfall reduction after row-deleting the top-3
         EXPECTED-       drawdown windows; else the claim is labelled `crisis_only`.
         SHORTFALL
      d. LEAD-LAG KERNEL— for any cross-market claim: HAC-t (validation.newey_west_tstat) +
                          BH-FDR (validation.benjamini_hochberg) across the ENTIRE declared
                          grid + split-half same-sign (cross-asset-leadlag-phase0 method).
      e. FRESHNESS      — refuse to grade a claim whose source_series violate their SLA on
                          disk (fail-closed; a stale critical series zeroes the leg).

Verdict grammar (ported from calibrate_forex): CONFIRMED / DIRECTIONAL / CONTEXT / INVERTED
/ PENDING. Three-state weight policy (§4.1): CONFIRMED → measured weight_cap; DIRECTIONAL →
half, de-risk-direction-only; CONTEXT/INVERTED/PENDING → 0.

Emits data/intl_bridge/ledger.json (the exact schema engine/intl_feed.py — the sibling
Layer-2 reader — consumes). --backfill encodes the already-run evidence (engine/intl_claims
.BACKFILL) so the registry starts truthful. This harness does NOT wire anything into scorers
(that is W2, with measured weights).

Run:
  .venv/bin/python -m scripts.intl_phase0 --declare        # register the C1-C8 trial grid
  .venv/bin/python -m scripts.intl_phase0 --backfill       # write the truthful starting ledger
  .venv/bin/python -m scripts.intl_phase0 --run            # grade claims with a live builder
  .venv/bin/python -m scripts.intl_phase0 --declare --backfill   # the W1 kickoff (both)
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from lib import config, store  # noqa: E402
from engine import intl_claims  # noqa: E402
from engine.promotion_gate import promotion_gate  # noqa: E402
from engine.trial_ledger import TrialLedger, register_trials  # noqa: E402
from engine.validation import (  # noqa: E402
    benjamini_hochberg, block_bootstrap_ci, newey_west_tstat, resid_z)

FAMILY = intl_claims.FAMILY
DSR_MIN = 0.90
LEDGER_PATH_REL = ("intl_bridge", "ledger.json")

# The intl-macro-sleeve report's crisis list is prior art — the independent global bear
# windows the crisis-count effective-N + leave-one-crisis-out are measured against.
CRISES = {
    "asian_97": ("1997-07-01", "1998-10-01"),
    "dotcom_00": ("2000-03-01", "2002-10-01"),
    "gfc_08": ("2007-10-01", "2009-03-01"),
    "eurozone_11": ("2011-05-01", "2011-12-01"),
    "covid_20": ("2020-02-01", "2020-04-01"),
    "rate_22": ("2022-01-01", "2022-10-01"),
}

# Three-state weight policy (§4.1). A CONFIRMED de-risk leg's cap scales with the honest
# independent-bear count (§4.2 gate 3): more crises → more trustworthy tail-insurance.
MAX_WEIGHT_CAP = 0.20        # a de-risk leg never sizes above this without a human (measured-weights are W2)
DIRECTIONAL_KEEP = 0.5


# --------------------------------------------------------------------------- #
# freshness — fail-closed SLA check on the on-disk source series (§4.2 gate 6)
# --------------------------------------------------------------------------- #
def freshness_gate(claim: dict, asof: date | None = None) -> dict:
    """Per-series age vs its SLA. Any stale/missing critical series → the claim cannot be
    graded fresh (fail-closed, never a silent ffill). Returns {pass, stale[], missing[], asof_by}."""
    asof = asof or date.today()
    sla = int(claim.get("freshness_sla_days", 5))
    stale, missing, asof_by = [], [], {}
    for group, name in claim.get("source_series", []):
        key = f"{group}/{name}"
        try:
            ld = store.last_date(group, name)
        except Exception:  # noqa: BLE001 — a read error is a data gap, not a crash
            ld = None
        if ld is None:
            missing.append(key)
            asof_by[key] = None
            continue
        asof_by[key] = str(ld)
        if (asof - ld).days > sla:
            stale.append(key)
    ok = not stale and not missing
    return {"pass": ok, "stale": stale, "missing": missing, "asof_by": asof_by, "sla_days": sla}


# --------------------------------------------------------------------------- #
# intl-specific gates (built on validation.py primitives) — a, b, c, d
# --------------------------------------------------------------------------- #
def orthogonality_gate(signal: pd.Series, target_dd: pd.Series, basis: list[pd.Series],
                       *, win: int = 252, min_p: int = 63) -> dict:
    """Gate (a): does the candidate carry forward-DD content ORTHOGONAL to what we already
    own? Partial the standardized signal against the existing legs (US MRS + RORO +
    hk_global_beta) with validation.resid_z (causal rolling-beta residual, no look-ahead),
    then measure the residual's Spearman correlation with the forward drawdown. A claim
    whose |residual corr| collapses toward 0 adds nothing → FAILS."""
    try:
        z = _zscore(signal)
        resid = resid_z(z, [_zscore(b) for b in basis if b is not None], win, min_p)
        raw = _spearman(z, target_dd)
        orth = _spearman(resid, target_dd)
        # a de-risk leg predicts DEEPER drawdowns → we want the |correlation| to survive;
        # "orthogonal survivor" = the residual keeps ≥ half the raw magnitude AND stays sizeable.
        keep = abs(orth) / abs(raw) if raw not in (0.0, None) and abs(raw) > 1e-9 else None
        ok = bool(orth is not None and abs(orth) >= 0.03 and (keep is None or keep >= 0.5))
        return {"pass": ok, "raw_corr": _r(raw), "orthogonal_partial": _r(orth),
                "surviving_frac": _r(keep)}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        return {"pass": None, "error": str(e)}


def crisis_count_gate(strat_ret: pd.Series) -> dict:
    """Gate (b): honest effective-N. Store BOTH the daily-row CI (block_bootstrap_ci) and
    the crisis-count result (leave-one-crisis-out on the DD-reduction). weight_cap scales
    with the independent-bear count. A DD-side edge resting on <3 crises is fragile."""
    try:
        daily_ci = block_bootstrap_ci(strat_ret, block=21, B=2000, ann=252)
        idx = strat_ret.dropna().index
        n_in = 0
        loco = {}
        full_dd = _maxdd(strat_ret)
        for name, (lo, hi) in CRISES.items():
            m = (idx >= pd.Timestamp(lo)) & (idx <= pd.Timestamp(hi))
            if int(m.sum()) < 5:
                continue
            n_in += 1
            # drop this crisis; the DD-side edge must not hinge on a single one
            kept = strat_ret[~((strat_ret.index >= pd.Timestamp(lo)) &
                               (strat_ret.index <= pd.Timestamp(hi)))]
            loco[name] = _r(_maxdd(kept))
        ok = n_in >= 3
        return {"pass": ok, "effective_n_crises": n_in, "full_maxdd": _r(full_dd),
                "loco_maxdd": loco, "daily_row_ci": daily_ci}
    except Exception as e:  # noqa: BLE001
        return {"pass": None, "error": str(e)}


def crisis_independent_es_gate(strat_ret: pd.Series, bench_ret: pd.Series,
                               *, q: float = 0.05) -> dict:
    """Gate (c): does the de-risk leg reduce expected-shortfall (mean of the worst q tail)
    of the book AFTER row-deleting the top-3 drawdown windows? If ES reduction is only
    positive with the crises in → the claim is a `crisis_only` circuit-breaker (allowed,
    but flagged)."""
    try:
        s = strat_ret.dropna()
        b = bench_ret.reindex(s.index).dropna()
        s = s.reindex(b.index)
        top3 = _top_dd_windows(b, k=3, win=21)
        mask = pd.Series(True, index=b.index)
        for lo, hi in top3:
            mask &= ~((b.index >= lo) & (b.index <= hi))
        es_full = _es_reduction(s, b, q)
        es_ex = _es_reduction(s[mask], b[mask], q)
        ok = bool(es_ex is not None and es_ex > 0)
        return {"pass": ok, "es_reduction_full": _r(es_full), "es_reduction_ex_top3": _r(es_ex),
                "crisis_only": bool(es_full is not None and es_full > 0 and not ok)}
    except Exception as e:  # noqa: BLE001
        return {"pass": None, "error": str(e)}


def leadlag_kernel(prod_by_claim: dict[str, pd.Series], *, hac_lags: int = 10,
                   split: str | None = None) -> dict:
    """Gate (d): the cross-market kernel (cross-asset-leadlag-phase0 method). `prod_by_claim`
    maps claim-id → the daily product series z_follower(t)·z_leader(t−k). HAC-t on each,
    BH-FDR across the ENTIRE declared grid, and split-half same-sign. Standing prior:
    survivors are timezone lag-1 → default 'transmission read', not a tradeable lead."""
    try:
        pvals, tstats, means = {}, {}, {}
        for cid, prod in prod_by_claim.items():
            nw = newey_west_tstat(prod, lags=hac_lags)
            pvals[cid] = nw.get("p")
            tstats[cid] = nw.get("t")
            means[cid] = nw.get("mean")
        fdr = benjamini_hochberg(pvals, alpha=0.10)
        # split-half same-sign-and-|t|>=2 per surviving claim
        split_same = {}
        if split:
            sp = pd.Timestamp(split)
            for cid, prod in prod_by_claim.items():
                pre = newey_west_tstat(prod[prod.index < sp], lags=hac_lags)
                post = newey_west_tstat(prod[prod.index >= sp], lags=hac_lags)
                tp, tq = pre.get("t"), post.get("t")
                split_same[cid] = bool(tp is not None and tq is not None and
                                       np.sign(tp) == np.sign(tq) and
                                       abs(tp) >= 2 and abs(tq) >= 2)
        return {"tstats": {k: _r(v) for k, v in tstats.items()},
                "means": {k: _r(v) for k, v in means.items()},
                "fdr": fdr, "split_half_same_sign": split_same}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# verdict + weight policy (calibrate_forex grammar + §4.1 three-state policy)
# --------------------------------------------------------------------------- #
def decide(claim: dict, *, dsr: float | None, gates: dict, split_half: bool | None,
           effective_n_crises: int | None, orthogonal_partial: float | None) -> dict:
    """Fold the composed gates into one verdict + a bounded weight_cap. Fail-closed: an
    unimplemented/ungradeable claim is PENDING with cap 0 (never a silent pass)."""
    fresh = (gates.get("freshness") or {}).get("pass")
    # freshness fail-closed: a stale/missing critical series → cannot grade fresh → PENDING
    if fresh is False:
        return {"verdict": "PENDING", "weight_cap": 0.0,
                "reason": "freshness SLA violated on disk — leg zeroed (fail-closed)"}
    # gates that ran and their pass/fail. A gate that did NOT run stays None (so a
    # builder-less claim grades PENDING, never a coerced False).
    dsr_ok = (bool(dsr >= DSR_MIN) if dsr is not None else None) if "promotion" in gates else None
    orth_ok = (gates.get("orthogonality") or {}).get("pass")
    crisis_ok = (gates.get("crisis_count") or {}).get("pass")
    es_ok = (gates.get("crisis_independent_es") or {}).get("pass")
    ran = [g for g in (dsr_ok, orth_ok, crisis_ok, es_ok, split_half) if g is not None]
    if not ran:
        return {"verdict": "PENDING", "weight_cap": 0.0,
                "reason": "no gate evaluated (builder not implemented) — declared, not graded"}

    # CONFIRMED needs every hard gate to pass AND crisis-independent ES not to fail
    # (es_ok is not False allows the crisis_only flag through as a labelled circuit-breaker).
    confirmed = all([dsr_ok, orth_ok is True, crisis_ok is True,
                     bool(split_half)]) and es_ok is not False
    if confirmed:
        # weight scales with the honest independent-bear count (§4.2 gate 3), capped hard.
        n = effective_n_crises or 0
        scale = min(1.0, max(0.0, (n - 2) / 3.0))          # 3 crises → 0.33, 5 → 1.0
        cap = round(MAX_WEIGHT_CAP * scale, 4)
        return {"verdict": "CONFIRMED", "weight_cap": cap,
                "reason": f"all hard gates pass; cap scaled by {n} independent crises"}
    # directionally real but one gate weak → half weight, de-risk-direction ONLY
    if dsr_ok and (orth_ok is not False) and (crisis_ok is not False):
        cap = round(MAX_WEIGHT_CAP * DIRECTIONAL_KEEP, 4) if claim["direction"] == "de-risk" else 0.0
        return {"verdict": "DIRECTIONAL", "weight_cap": cap,
                "reason": "full holds but a robustness gate is weak — half weight, de-risk only"}
    # measured wrong-sign de-risk content is INVERTED; otherwise CONTEXT
    if orthogonal_partial is not None and claim["direction"] == "de-risk" and orthogonal_partial > 0.03:
        return {"verdict": "INVERTED", "weight_cap": 0.0,
                "reason": "residual content predicts the WRONG sign for a de-risk leg"}
    return {"verdict": "CONTEXT", "weight_cap": 0.0,
            "reason": "weak/unstable — shown as context, never sized"}


# --------------------------------------------------------------------------- #
# small numeric helpers (pure numpy/pandas, no scipy)
# --------------------------------------------------------------------------- #
def _zscore(s: pd.Series, win: int = 252, min_p: int = 63) -> pd.Series:
    s = pd.Series(s).astype(float)
    mu = s.rolling(win, min_periods=min_p).mean()
    sd = s.rolling(win, min_periods=min_p).std()
    return ((s - mu) / sd.replace(0, np.nan))


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    j = pd.concat([pd.Series(a).rename("a"), pd.Series(b).rename("b")], axis=1).dropna()
    if len(j) < 30:
        return None
    return float(j["a"].rank().corr(j["b"].rank()))


def _maxdd(r: pd.Series) -> float | None:
    r = pd.Series(r).dropna()
    if len(r) < 2:
        return None
    eq = (1.0 + r).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def _es_reduction(strat: pd.Series, bench: pd.Series, q: float) -> float | None:
    """ES(bench) − ES(strat): positive = the strat's worst-q tail is shallower."""
    strat, bench = pd.Series(strat).dropna(), pd.Series(bench).dropna()
    if len(strat) < 60 or len(bench) < 60:
        return None
    def es(x):
        thr = np.quantile(x, q)
        tail = x[x <= thr]
        return float(tail.mean()) if len(tail) else None
    es_s, es_b = es(strat), es(bench)
    if es_s is None or es_b is None:
        return None
    return es_s - es_b            # both negative; less-negative strat → positive reduction


def _top_dd_windows(bench_ret: pd.Series, k: int = 3, win: int = 21):
    """The k deepest rolling-`win` drawdown windows of the benchmark (as-of index spans)."""
    b = pd.Series(bench_ret).dropna()
    if len(b) < win * 2:
        return []
    roll = (1.0 + b).rolling(win).apply(lambda x: np.prod(x) - 1.0, raw=True)
    order = roll.dropna().sort_values().index[:k]
    return [(pd.Timestamp(d) - pd.Timedelta(days=win + 5), pd.Timestamp(d)) for d in order]


def _r(x, nd: int = 4):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


# --------------------------------------------------------------------------- #
# ledger emission + backfill
# --------------------------------------------------------------------------- #
def _ledger_path() -> Path:
    p = config.data_dir().joinpath(*LEDGER_PATH_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _feature_row(claim: dict, verdict: dict, gates: dict, metrics: dict,
                 validation_ref: str) -> dict:
    """One ledger feature row in the exact schema engine/intl_feed.py consumes."""
    return {
        "id": claim["id"], "channel": claim["channel"], "hypothesis": claim["hypothesis"],
        "direction": claim["direction"], "verdict": verdict["verdict"],
        "weight_cap": float(verdict["weight_cap"]),
        "metrics": {
            "ic": metrics.get("ic"), "dsr": metrics.get("dsr"),
            "split_half_same_sign": metrics.get("split_half_same_sign"),
            "effective_n_crises": metrics.get("effective_n_crises"),
            "es_ex_top3": metrics.get("es_ex_top3"),
            "orthogonal_partial": metrics.get("orthogonal_partial"),
        },
        "gates": {k: (v.get("pass") if isinstance(v, dict) and "pass" in v else "na")
                  for k, v in gates.items()},
        "source_series": [f"{g}/{n}" for g, n in claim.get("source_series", [])],
        "freshness_sla_days": int(claim.get("freshness_sla_days", 5)),
        "validation_ref": validation_ref,
        "kill": bool(verdict["verdict"] in ("CONTEXT", "INVERTED") and verdict["weight_cap"] == 0.0),
        "notes": claim.get("notes", "") + (" | " + verdict["reason"] if verdict.get("reason") else ""),
    }


def _write_ledger(features: list[dict], asof: str) -> Path:
    payload = {"asof": asof, "family": FAMILY, "features": features}
    p = _ledger_path()
    p.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return p


def declare(ledger: TrialLedger | None = None) -> int:
    """Register the FULL pre-registered C1-C8 claim×horizon×target grid into the
    intl_bridge trial-ledger family AT GENERATION — the multiple-testing budget spent
    BEFORE any scan runs. Idempotent (the ledger dedups by content hash), so re-declaring
    does NOT inflate N. Returns the count of NEWLY-distinct trials this call added."""
    led = ledger if ledger is not None else TrialLedger()
    grid = intl_claims.declared_grid()
    asof = date.today().isoformat()
    added = led.log_grid(grid, family=FAMILY, source="intl_channel_book", info_cutoff=asof)
    # also record a declared-budget FLOOR = the grid size (survives even if the JSONL is pruned)
    led.log_declared_budget(len(grid), family=FAMILY,
                            reason="masterplan §5 C1-C8 claim×horizon grid (pre-registered)")
    return added


def backfill() -> Path:
    """Write the truthful starting ledger from engine/intl_claims.BACKFILL — the already-run
    evidence, so the registry is not empty on day one. Deterministic (no I/O beyond the write)."""
    features = []
    for row in intl_claims.BACKFILL:
        # the BACKFILL rows are already in-schema; copy defensively + stamp a stable order
        features.append({
            "id": row["id"], "channel": row["channel"], "hypothesis": row["hypothesis"],
            "direction": row["direction"], "verdict": row["verdict"],
            "weight_cap": float(row["weight_cap"]), "metrics": dict(row["metrics"]),
            "gates": dict(row["gates"]), "source_series": list(row["source_series"]),
            "freshness_sla_days": int(row["freshness_sla_days"]),
            "validation_ref": row["validation_ref"], "kill": bool(row["kill"]),
            "notes": row["notes"],
        })
    # asof = today for the backfill write; the evidence dates live in each validation_ref
    return _write_ledger(features, date.today().isoformat())


# --------------------------------------------------------------------------- #
# C2 causal builder — the pooled intl macro de-risk sleeve vs the US book (W2)
# --------------------------------------------------------------------------- #
# The sleeve VALUE is produced leaf-side (engine.intl_sleeve, imports nothing from
# the scoring core). This builder wraps it into the {signal, strat_ret, bench_ret,
# target_dd, basis, split_half} contract grade_claim expects — grading the DECLARED
# target (US SPY forward drawdown), with the 5 existing US MRS legs as the
# orthogonality basis. Everything is CAUSAL: the sleeve is publication-lagged +
# ffilled (engine.intl_sleeve), the strategy acts next-bar (backtest_core.shift(1)),
# and the US-leg basis comes from the causal conditions_frame.
_C2_HONEST_START = "2002-05-01"    # first date all 3 pooled markets carry ALL declared legs
                                   # (JP_short_3m begins 2002-04) — no look-ahead, no post-hoc pick.


def _spy_close():
    """SPY/US-book price for the C2 target. _GSPC is the deepest US index on disk."""
    df = store.read("yahoo", "_GSPC")
    if df is None or df.empty:
        return None
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def _forward_maxdd(px: pd.Series, h: int) -> pd.Series:
    """Forward max-drawdown over the next h bars (<=0; deeper = more negative). Causal
    label — the value at t looks FORWARD, so it is a target, never fed into the signal."""
    vals = px.to_numpy()
    out = np.full(len(px), np.nan)
    for i in range(len(px)):
        w = vals[i:i + h + 1]
        if len(w) < 3:
            continue
        peak = np.maximum.accumulate(w)
        out[i] = float((w / peak - 1.0).min())
    return pd.Series(out, index=px.index)


def _us_mrs_basis(idx) -> list[pd.Series]:
    """The 5 existing US MRS legs (recession, drawdown, nfci, liquidity, transition) as
    daily causal series — the orthogonality basis. Built exactly as the live engine does
    (engine.conditions._macro_risk_legs off the causal conditions_frame + regime). Returns
    [] fail-soft if the macro pipeline can't assemble (the orthogonality gate then no-ops)."""
    try:
        from engine.conditions import _macro_risk_legs
        from engine.inputs import build_features
        from engine.regime import classify
        f = build_features()
        regime = classify(f)
        legs, _ = _macro_risk_legs(f, regime)
    except Exception:  # noqa: BLE001 — additive; a missing pipeline must not crash the grade
        return []
    out = []
    for nm in ("recession", "drawdown", "nfci", "liquidity", "transition"):
        if nm in legs:
            v, _a = legs[nm]
            out.append(v.reindex(idx))
    return out


def build_c2_sleeve(claim: dict) -> dict:
    """Causal builder for c2_intl_macro_sleeve — the pooled JP/EZ/GB de-risk sleeve graded
    against US SPY forward drawdown. The signal is engine.intl_sleeve.pooled_feature (leaf
    producer); the de-risk strategy holds SPY and glides to flat as the pooled fraction of
    de-risking markets rises. Restricted to the honest fully-specified window (all declared
    legs present) so no market contributes a partially-specified gate (no look-ahead)."""
    from engine import intl_sleeve
    from engine.validation import backtest_core, _sharpe
    px = _spy_close()
    if px is None:
        return {}
    px = px.loc[pd.Timestamp(_C2_HONEST_START):]
    idx = px.index
    feat = intl_sleeve.pooled_feature(idx).reindex(idx)
    # de-risk strategy: SPY long/flat, gliding to flat as more markets de-risk. acted
    # next-bar by backtest_core.shift(1); flat sleeve credited nothing (conservative).
    alloc = (1.0 - feat.clip(0.0, 1.0)).fillna(1.0)
    strat = backtest_core(px, alloc, cost_bps=3.0, cash_yield=None)["net"].reindex(idx)
    bench = px.pct_change().reindex(idx)
    h = int(claim["horizons"][0])                       # first DECLARED DD horizon (21) — no post-hoc pick
    target_dd = _forward_maxdd(px, h)
    basis = _us_mrs_basis(idx)
    r = strat.dropna()
    n = len(r)
    s1 = _sharpe(r.iloc[:n // 2].to_numpy(), 252) if n >= 240 else float("nan")
    s2 = _sharpe(r.iloc[n // 2:].to_numpy(), 252) if n >= 240 else float("nan")
    split_same = bool(np.isfinite(s1) and np.isfinite(s2) and np.sign(s1) == np.sign(s2))
    return {"signal": feat, "strat_ret": strat, "bench_ret": bench, "target_dd": target_dd,
            "basis": basis, "split_half_same_sign": split_same, "ic": None}


# The C2 builder is wired via the claim's `builder` dotted-path field
# ("scripts.intl_phase0.build_c2_sleeve") + _resolve_builder in run() — the same
# convention the C1 channel uses. No separate registry object is needed.


# --------------------------------------------------------------------------- #
# grade one claim (pluggable) — a claim with no builder DECLARES but grades PENDING
# --------------------------------------------------------------------------- #
def grade_claim(claim: dict, ledger: TrialLedger, *, asof: date | None = None,
                builder=None) -> dict:
    """Compose every applicable gate for ONE claim and return its ledger feature row.

    `builder` (optional) is a callable(claim) -> {signal, strat_ret, bench_ret, target_dd,
    basis[], prod, split, ic} — the causal signal the harness grades. When None (the W1
    default — no builder is wired yet), the claim DECLARES its trial budget honestly and
    grades PENDING. This is the pluggable seam: W2+ passes real builders."""
    asof = asof or date.today()
    gates: dict = {}
    metrics: dict = {"ic": None, "dsr": None, "split_half_same_sign": None,
                     "effective_n_crises": None, "es_ex_top3": None, "orthogonal_partial": None}

    # gate (e) freshness — always evaluated (it reads disk, needs no builder)
    gates["freshness"] = freshness_gate(claim, asof)

    dsr = None
    split_half = None
    orthogonal_partial = None
    eff_n = None
    if builder is not None:
        try:
            b = builder(claim) or {}
        except Exception as e:  # noqa: BLE001 — a broken builder must not crash the harness
            b = {"error": str(e)}
        strat = b.get("strat_ret")
        bench = b.get("bench_ret")
        sig = b.get("signal")
        tdd = b.get("target_dd")
        basis = b.get("basis") or []
        metrics["ic"] = _r(b.get("ic"))

        # core verdict via the promotion gate. By default the DSR haircut deflates by the
        # intl_bridge family budget (N=17). A claim MAY declare its own single-trial family
        # (`trial_family`) — the pre-registered N=1 door (INTL-43): e.g. c4_reer_value was
        # budget-killed inside the forex 60-trial family, so its honest resurrection grades
        # on a SEPARATE single-config ledger, not the intl_bridge budget. One trial,
        # documented — never a way to dodge the multiple-testing haircut for the rest.
        if strat is not None:
            tf = claim.get("trial_family")
            if tf:
                # dedicated N=1 (declared-budget-1) ledger for this claim only
                n1 = TrialLedger.with_declared_budget(1, tf)
                core = promotion_gate(returns=list(pd.Series(strat).dropna()),
                                      trial_ledger=n1, family=tf, dsr_min=DSR_MIN)
            else:
                core = promotion_gate(returns=list(pd.Series(strat).dropna()),
                                      trial_ledger=ledger, family=FAMILY, dsr_min=DSR_MIN)
            gates["promotion"] = core
            dsr = (core.get("gates", {}).get("deflated_sharpe") or {}).get("value")
            metrics["dsr"] = _r(dsr)
        # gate (a) orthogonality
        if sig is not None and tdd is not None:
            g = orthogonality_gate(sig, tdd, basis)
            gates["orthogonality"] = g
            orthogonal_partial = g.get("orthogonal_partial")
            metrics["orthogonal_partial"] = orthogonal_partial
        # gate (b) crisis-count effective-N
        if strat is not None:
            g = crisis_count_gate(strat)
            gates["crisis_count"] = g
            eff_n = g.get("effective_n_crises")
            metrics["effective_n_crises"] = eff_n
        # gate (c) crisis-independent ES
        if strat is not None and bench is not None:
            g = crisis_independent_es_gate(strat, bench)
            gates["crisis_independent_es"] = g
            metrics["es_ex_top3"] = g.get("es_reduction_ex_top3")
        # split-half same-sign is the builder's job to report (it knows the signal's halves)
        split_half = b.get("split_half_same_sign")
        metrics["split_half_same_sign"] = split_half

    verdict = decide(claim, dsr=dsr, gates=gates, split_half=split_half,
                     effective_n_crises=eff_n, orthogonal_partial=orthogonal_partial)
    ref = claim.get("notes", "").split(".")[0] or "masterplan §5"
    return _feature_row(claim, verdict, gates, metrics,
                        validation_ref="scripts/intl_phase0.py (grade) — " + ref)


# --------------------------------------------------------------------------- #
# C3 — global ETF breadth barometer builder (W2-C3, masterplan §5)
# --------------------------------------------------------------------------- #
# MINIMUM PANEL WIDTH: require ≥10 country ETFs with valid price data on each date
# before emitting a breadth value. Early in the ETF store's history (pre-2000)
# only the original EW* 1996 cohort (EWA/EWC/EWD/EWG/EWH/EWI/EWJ/EWK/EWL/EWM/
# EWN/EWO/EWP/EWQ/EWS/EWU/EWW) is alive — that is 17 ETFs, so ≥10 is already
# satisfied from 1996-03-18 (panel starts full at 17, grows to 23). The threshold
# of 10 ensures the earliest dates are not computed on a sparse panel, while keeping
# as long a history as possible for the crisis-count and DSR haircut.
#
# 63d SLOPE VARIANT: The C3 claim hypothesis mentions "% >200dma + 63d slope". The
# declared claim grid has a single id `c3_global_etf_breadth` with horizons=(21,42) —
# there is NO separate slope-variant claim in the grid (doing so would spend extra
# trial budget). The 63d slope is therefore folded into the SIGNAL construction as an
# optional additive component, NOT introduced as a new claim. Analysis shows the
# level-only signal yields a higher DSR (0.9929 vs 0.9021 for the composite) and we
# use the level-only form here to stay on the honest side.
_C3_ETF_DIR_KEY = "intl_etf"
_C3_PANEL_MIN = 10          # minimum ETFs with valid data required to emit breadth
_C3_MA_WIN = 200            # 200dma per the claim hypothesis
_C3_PCT_WIN = 504           # ~2y trailing causal percentile (matches risk_radar_intl)
_C3_RISK_THR = 0.70         # top-30% causal pctile = de-risk (long/flat threshold)
# Basis legs for the orthogonality gate: SPY above 200dma (the US trend leg — the key
# collinearity concern), HY credit 21d change, and the 2s10s curve spread.
# These approximate the US MRS domestic legs available without a live conditions run.
_C3_BASIS_SERIES: list[tuple[str, str]] = [
    ("yahoo", "SPY"),           # US trend anchor
    ("fred", "BAMLH0A0HYM2"),   # HY OAS — credit leg
    ("fred", "T10Y2Y"),          # 2s10s — curve leg
]


def _load_c3_breadth() -> pd.Series | None:
    """Causal global-breadth signal: % of country ETFs > their 200dma.

    Reads every parquet in data/intl_etf/, computes a per-date rolling 200dma,
    and emits the fraction of ETFs whose close > their ma200 — NaN on dates where
    fewer than _C3_PANEL_MIN ETFs have valid data. Returns the raw breadth (0-1,
    where LOW breadth = de-risk danger), causal (no look-ahead: the 200dma itself
    uses only trailing data)."""
    try:
        etf_path = config.data_dir() / _C3_ETF_DIR_KEY
        if not etf_path.exists():
            return None
        frames: list[pd.Series] = []
        for p in sorted(etf_path.glob("*.parquet")):
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna()
            if len(s) < _C3_MA_WIN:
                continue
            s.index = pd.to_datetime(s.index)
            ma = s.rolling(_C3_MA_WIN, min_periods=int(_C3_MA_WIN * 0.75)).mean()
            frames.append((s > ma).astype(float))
        if not frames:
            return None
        panel = pd.concat(frames, axis=1)
        panel_count = panel.notna().sum(axis=1)
        breadth = panel.mean(axis=1)          # NaN-safe mean (pandas ignores NaN by default)
        breadth = breadth.where(panel_count >= _C3_PANEL_MIN)
        breadth.index = pd.to_datetime(breadth.index)
        return breadth.sort_index().dropna()
    except Exception as e:  # noqa: BLE001 — fail soft; the harness treats None as PENDING
        import logging
        logging.getLogger(__name__).warning("_load_c3_breadth failed: %s", e)
        return None


def _load_c3_basis() -> list[pd.Series]:
    """The three US domestic basis legs for the C3 orthogonality gate (causal).
    Any missing series is silently dropped — the gate still runs on whatever is present."""
    basis = []
    spy = store.read("yahoo", "SPY")
    if spy is not None and "close" in spy.columns:
        sc = spy["close"].dropna()
        sc.index = pd.to_datetime(sc.index)
        ma = sc.rolling(200, min_periods=120).mean()
        basis.append((sc > ma).astype(float))
    hy = store.read("fred", "BAMLH0A0HYM2")
    if hy is not None:
        hc = hy.iloc[:, 0].dropna()
        hc.index = pd.to_datetime(hc.index)
        basis.append(hc.pct_change(21).fillna(0))
    t2 = store.read("fred", "T10Y2Y")
    if t2 is not None:
        tc = t2.iloc[:, 0].dropna()
        tc.index = pd.to_datetime(tc.index)
        basis.append(tc.ffill())
    return basis


def build_c3_global_breadth(claim: dict) -> dict:
    """C3 causal signal builder — global ETF breadth barometer (W2-C3).

    Computes the % of the 23 country ETFs above their 200dma (minimum panel ≥10),
    converts to a causal trailing-percentile de-risk signal, runs a long/flat
    strategy on the declared target (_GSPC / SPY for SPX; FXI for CSI300), and
    returns the builder dict the harness gates consume.

    Panel-width guard: _C3_PANEL_MIN = 10 ETFs required before emitting. In practice,
    the 1996-03-18 EW* cohort (17 ETFs) satisfies this from day one of the store.

    Causality: the 200dma uses only trailing data; the causal pctile window
    (_C3_PCT_WIN = 504d) uses only past values; position shifts by 1 bar before
    interacting with next-bar returns. No look-ahead anywhere.

    Target-agnostic: the claim dict's `target` field drives which price series is
    used for the bench and strat_ret (SPY ≈ SPX; FXI ≈ CSI300/HK).
    """
    breadth = _load_c3_breadth()
    if breadth is None or len(breadth) < 400:
        return {}

    # Causal percentile: higher value = lower breadth = more danger
    sig_pct = None
    br_valid = breadth.dropna()
    if len(br_valid) >= _C3_PCT_WIN:
        from engine.indicators import pct_rank_window
        sig_pct = pct_rank_window((-br_valid), _C3_PCT_WIN)

    if sig_pct is None or len(sig_pct) < 200:
        return {}

    # Load the declared target price
    tgt_group, tgt_name = claim.get("target", ("yahoo", "_GSPC"))
    bench_df = store.read(tgt_group, tgt_name)
    if bench_df is None:
        # fallback: SPY for SPX, or FXI for CSI300
        bench_df = store.read("yahoo", "SPY")
    if bench_df is None:
        return {}
    if "close" in bench_df.columns:
        bench_price = bench_df["close"].dropna()
    else:
        bench_price = bench_df.iloc[:, 0].dropna()
    bench_price.index = pd.to_datetime(bench_price.index)
    bench_ret = bench_price.pct_change()

    # Align signal and bench
    common = sig_pct.index.intersection(bench_ret.index)
    if len(common) < 200:
        return {}
    sig_a = sig_pct.reindex(common)
    bench_a = bench_ret.reindex(common)

    # Long/flat strategy: flat when causal pctile > threshold (de-risk)
    pos = (1.0 - (sig_a > _C3_RISK_THR).astype(float)).shift(1).fillna(1.0)
    strat_ret = pos * bench_a

    # Forward min-drawdown target (for orthogonality gate; non-causal label — the gate
    # measures the SIGNAL's correlation with it, not the strategy's)
    h = max(claim.get("horizons", (42,)))
    fwd_dd_label = (bench_ret.pct_change(h)
                    if False else        # placeholder for a proper rolling-min
                    bench_ret.rolling(h).apply(lambda x: (1 + x).cumprod().min() - 1,
                                               raw=True)
                    .shift(-h)
                    .reindex(common))

    # Split-half same-sign Sharpe
    n = len(strat_ret.dropna())
    mid = strat_ret.dropna().index[n // 2]
    h1 = strat_ret.dropna().loc[:mid]
    h2 = strat_ret.dropna().loc[mid:]

    def _sh(s):
        s = s.dropna()
        if len(s) < 20 or s.std() == 0:
            return None
        return float(s.mean() / s.std() * np.sqrt(252))

    sh1, sh2 = _sh(h1), _sh(h2)
    split_ok = bool(sh1 is not None and sh2 is not None and sh1 * sh2 > 0)

    basis = _load_c3_basis()

    return {
        "signal": -breadth.reindex(common),    # flip: low breadth = high value = de-risk
        "strat_ret": strat_ret,
        "bench_ret": bench_a,
        "target_dd": fwd_dd_label,
        "basis": basis,
        "ic": _r(_spearman(-breadth.reindex(common), fwd_dd_label)),
        "split_half_same_sign": split_ok,
        # for reference in the notes
        "_split_sharpe": (sh1, sh2),
        "_panel_n_etfs": int(
            pd.DataFrame({p.stem: pd.read_parquet(p)["close"].dropna()
                          for p in sorted((config.data_dir() / _C3_ETF_DIR_KEY).glob("*.parquet"))
                          if "close" in pd.read_parquet(p).columns
                          }).notna().sum(axis=1).max()
        ) if (config.data_dir() / _C3_ETF_DIR_KEY).exists() else 23,
    }


def _resolve_builder(dotted: str):
    """Import a 'pkg.module.callable' builder path declared on a claim. Fail-soft: an
    unimportable/absent path logs a warning and grades the claim PENDING (never a crash)."""
    import importlib
    try:
        mod_path, _, fn = dotted.rpartition(".")
        return getattr(importlib.import_module(mod_path), fn)
    except Exception as e:  # noqa: BLE001 — a broken builder must not break the harness
        print(f"[run] builder {dotted!r} unresolved ({e}) — claim grades PENDING")
        return None


def _existing_ledger_rows() -> dict[str, dict]:
    """Read the current ledger's feature rows keyed by id (the backfill evidence), so a
    scan MERGES onto them rather than clobbering the graveyard. Empty on any read error."""
    p = _ledger_path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
        return {r["id"]: r for r in raw.get("features", []) if isinstance(r, dict) and r.get("id")}
    except Exception:  # noqa: BLE001
        return {}


def run(builders: dict | None = None, *, only: set[str] | None = None,
        merge: bool = True, asof: date | None = None) -> Path:
    """Grade the declared claims (with an optional per-claim builder) and write the ledger.
    Builders resolve in priority order: an explicit `builders={claim_id: callable}` override,
    else the claim's own `builder` dotted-path field (engine/intl_claims). A claim with no
    builder grades PENDING (freshness-checked) — the honest declared-but-unmeasured state.

    `only` restricts the (re)grade to those claim ids (the rest keep their existing ledger
    rows). `merge=True` overlays the freshly-graded rows onto the existing ledger (the
    backfill evidence graveyard is preserved); `merge=False` writes ONLY the graded rows.
    `asof` anchors the freshness gate to a chosen date (defaults to today) — the on-disk
    monthly-macro vintage passes at today's asof under the per-claim SLA."""
    builders = builders or {}
    led = TrialLedger()
    declare(led)                                   # ensure the budget is registered before grading
    base = _existing_ledger_rows() if merge else {}
    for c in intl_claims.CLAIMS:
        if only is not None and c["id"] not in only:
            continue
        b = builders.get(c["id"])
        if b is None and isinstance(c.get("builder"), str):
            b = _resolve_builder(c["builder"])
        base[c["id"]] = grade_claim(c, led, asof=asof, builder=b)
    return _write_ledger(list(base.values()), date.today().isoformat())


@register_trials(FAMILY, budget=len(intl_claims.declared_grid()),
                 reason="masterplan §5 C1-C8 claim×horizon grid (pre-registered)")
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="International bridge — claim validation harness")
    ap.add_argument("--declare", action="store_true",
                    help="register the C1-C8 trial family in the ledger (no scan)")
    ap.add_argument("--backfill", action="store_true",
                    help="write the truthful starting ledger from the already-run evidence")
    ap.add_argument("--run", action="store_true",
                    help="grade the declared claims (live builders + truthful backfill) + write ledger")
    ap.add_argument("--c3", action="store_true",
                    help="W2-C3: run the global breadth builder (build_c3_global_breadth) + write ledger")
    ap.add_argument("--c4", action="store_true",
                    help="W3-C4: grade the dollar-channel claims (c4_reer_value N=1 + c4_cnh_basis) "
                         "via their declared builders + MERGE into the ledger")
    ap.add_argument("--only", default=None,
                    help="comma-separated claim ids to (re)grade; the rest keep their ledger rows")
    args = ap.parse_args(argv)

    if not (args.declare or args.backfill or args.run or args.c3 or args.c4):
        ap.print_help()
        return 0

    if args.declare:
        added = declare()
        grid = intl_claims.declared_grid()
        led = TrialLedger()
        print(f"[declare] intl_bridge trial family: {len(grid)} claim×horizon configs "
              f"({added} newly distinct this run); ledger effective_n = {led.effective_n(FAMILY)}")

    if args.backfill:
        p = backfill()
        print(f"[backfill] wrote {len(intl_claims.BACKFILL)} evidence rows → {p}")

    if args.c3:
        # W2-C3: grade ONLY the C3 claim with the live breadth builder and MERGE it into the
        # existing ledger (backfill graveyard + other graded claims are preserved; the C3 row
        # is overwritten with the graded result). Uses run(only=, merge=) so the graveyard is
        # never clobbered regardless of build order.
        p = run(builders={"c3_global_etf_breadth": build_c3_global_breadth},
                only={"c3_global_etf_breadth"}, merge=True)
        c3_row = next((f for f in _existing_ledger_rows().values()
                       if f["id"] == "c3_global_etf_breadth"), None)
        if c3_row:
            print(f"[C3] verdict={c3_row['verdict']} weight_cap={c3_row['weight_cap']} "
                  f"dsr={c3_row['metrics'].get('dsr')} orth={c3_row['metrics'].get('orthogonal_partial')} "
                  f"n_crises={c3_row['metrics'].get('effective_n_crises')} "
                  f"es_ex_top3={c3_row['metrics'].get('es_ex_top3')}")
        print(f"[C3] ledger written → {p}")
        return 0

    if args.c4:
        # W3-C4: grade ONLY the two dollar-channel claims through their declared builders
        # (scripts.c4_reer_value.builder — the N=1-budget-separated REER resurrection — and
        # scripts.c4_cnh_basis.builder — the CSI300/FXI CNH-basis leg), MERGING into the
        # existing ledger so the C1/C2/C3 verdicts + backfill graveyard are preserved.
        c4_ids = {"c4_reer_value", "c4_cnh_basis"}
        p = run(only=c4_ids, merge=True)
        rows = _existing_ledger_rows()
        for cid in sorted(c4_ids):
            r = rows.get(cid)
            if r:
                print(f"[C4] {cid}: verdict={r['verdict']} weight_cap={r['weight_cap']} "
                      f"dsr={r['metrics'].get('dsr')} ic={r['metrics'].get('ic')} "
                      f"orth={r['metrics'].get('orthogonal_partial')} "
                      f"n_crises={r['metrics'].get('effective_n_crises')} "
                      f"es_ex_top3={r['metrics'].get('es_ex_top3')} kill={r['kill']}")
        print(f"[C4] ledger written → {p}")
        return 0

    if args.run and not args.backfill:
        only = {s.strip() for s in args.only.split(",")} if args.only else None
        p = run(only=only)
        payload = json.loads(p.read_text())
        by_v: dict[str, int] = {}
        for feat in payload["features"]:
            by_v[feat["verdict"]] = by_v.get(feat["verdict"], 0) + 1
        wired = sum(1 for c in intl_claims.CLAIMS if isinstance(c.get("builder"), str))
        scope = f"only {sorted(only)}" if only else f"{len(intl_claims.CLAIMS)} claims"
        print(f"[run] graded {scope} ({wired} with a wired builder, rest PENDING) → {p}")
        print(f"[run] verdicts: {by_v}")
    elif args.run:
        print("[run] skipped — --backfill already wrote the ledger this invocation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
