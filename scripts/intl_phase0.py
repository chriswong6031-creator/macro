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

        # core verdict via the promotion gate (DSR ≥ 0.90 on the intl_bridge family)
        if strat is not None:
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


def run(builders: dict | None = None) -> Path:
    """Grade every declared claim (with an optional per-claim builder) and write the ledger.
    In W1 no builders are wired, so every claim grades PENDING (freshness-checked) — the
    honest empty-but-declared state. W2+ supplies `builders={claim_id: callable}`."""
    builders = builders or {}
    led = TrialLedger()
    declare(led)                                   # ensure the budget is registered before grading
    features = [grade_claim(c, led, builder=builders.get(c["id"])) for c in intl_claims.CLAIMS]
    return _write_ledger(features, date.today().isoformat())


@register_trials(FAMILY, budget=len(intl_claims.declared_grid()),
                 reason="masterplan §5 C1-C8 claim×horizon grid (pre-registered)")
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="International bridge — claim validation harness")
    ap.add_argument("--declare", action="store_true",
                    help="register the C1-C8 trial family in the ledger (no scan)")
    ap.add_argument("--backfill", action="store_true",
                    help="write the truthful starting ledger from the already-run evidence")
    ap.add_argument("--run", action="store_true",
                    help="grade the declared claims (PENDING until a builder is wired) + write ledger")
    args = ap.parse_args(argv)

    if not (args.declare or args.backfill or args.run):
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

    if args.run and not args.backfill:
        p = run()
        pend = sum(1 for c in intl_claims.CLAIMS)  # all PENDING in W1 (no builders)
        print(f"[run] graded {pend} declared claims (all PENDING — no builder wired in W1) → {p}")
    elif args.run:
        print("[run] skipped — --backfill already wrote the ledger this invocation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
