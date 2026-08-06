"""Study harness — does a recreated model rank anything on OUR panel?

Deliberately reuses the house gauntlet (`engine.validation`) rather than inventing a
private one, so a Quant Lab result is directly comparable to the factor IC scorecard that
already governs `engine/equity_factors.py`. Same rank-IC, same Newey-West correction for
overlapping forward windows, same Benjamini-Hochberg FDR across the screened panel.

WHAT THIS IS NOT: a promotion gate. Per CLAUDE.md the gauntlet is the PROMOTION gate, and
nothing here promotes anything — a recreation stays display-tier regardless of what comes
back. A positive read here is grounds for writing a pre-registration, not for ranking with
the score. A null is printed, not hidden.

THREE STANDING LIMITS, stamped onto every result so a caller cannot quote the number
without them:

  survivorship  the close panel serves currently-listed names, so delisted losers are
                absent and every read here is an OPTIMISTIC bound.
  universe      the fundamentals panel is ~1,552 names. Fintel's QV is a small-cap
                "multi-bagger" finder benchmarked to the Russell 2000; we are testing it
                on the wrong end of the size distribution.
  history       the in-tree close caches run ~3 years. That is a handful of independent
                quarterly rebalances, not a regime sample.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.quant_lab import legs as legs_mod
from engine.quant_lab import score as score_mod
from engine.validation import benjamini_hochberg, ic_summary, rank_ic

log = logging.getLogger(__name__)

DEFAULT_HORIZON = 63          # ~one quarter, matching the factor IC scorecard
MIN_NAMES = 30                # below this a cross-sectional IC is noise dressed as a number

STANDING_LIMITS = {
    "survivorship": ("Close panel serves currently-listed names only; delisted losers are "
                     "absent. Every number here is an optimistic bound."),
    "universe": ("~1,552 fundamentals-covered names, concentrated above the size band this "
                 "model targets. 6 of Fintel's 10 published QVM leaders are not in it."),
    "history": ("In-tree close caches run ~3 years — a handful of independent quarterly "
                "rebalances, not a regime sample."),
    "tier": "Display-tier research. Nothing here promotes a score to rank/size/gate authority.",
}


def rebalance_grid(px: pd.DataFrame, horizon: int, *, freq: str = "QE",
                   start: str | None = None) -> list:
    """Trading dates on a quarter-end grid that leave room for a realised forward window."""
    if px is None or px.empty:
        return []
    idx = px.index
    lo = pd.Timestamp(start) if start else idx.min()
    out = []
    for q in pd.date_range(lo, idx.max(), freq=freq):
        prior = idx[idx <= q]
        if len(prior) and idx.get_loc(prior[-1]) + horizon < len(idx):
            out.append(prior[-1])
    return out


def forward_returns(px: pd.DataFrame, date, horizon: int) -> pd.Series:
    """Realised `horizon`-day forward return from `date`. NaN where the name has no future
    price — which, on a currently-listed panel, is silently the survivorship hole."""
    idx = px.index
    i = idx.get_loc(date)
    j = i + horizon
    if j >= len(idx):
        return pd.Series(dtype=float)
    return (px.iloc[j] / px.iloc[i] - 1.0).replace([np.inf, -np.inf], np.nan)


def decile_spread(signal: pd.Series, fwd: pd.Series, k: int = 5) -> dict | None:
    """Top-minus-bottom quantile spread — the reading a leaderboard actually implies.

    Reported alongside IC because they answer different questions: IC asks whether the
    whole ranking is monotone, the spread asks whether the names you would actually BUY
    beat the ones you would skip.
    """
    j = pd.concat([signal.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(j) < max(MIN_NAMES, k * 5):
        return None
    try:
        q = pd.qcut(j["s"].rank(method="first"), k, labels=False, duplicates="drop")
    except ValueError:
        return None
    if pd.Series(q).nunique() < k:
        return None
    top, bot = j["f"][q == k - 1], j["f"][q == 0]
    return {"top": float(top.mean()), "bottom": float(bot.mean()),
            "spread": float(top.mean() - bot.mean()),
            "n_top": int(len(top)), "n_bottom": int(len(bot))}


def study_signal(signal_by_date: dict, fwd_by_date: dict, *,
                 periods_per_year: int = 4, hac_lags: int | None = None) -> dict:
    """IC series -> mean IC, IC-IR, HAC t-stat, hit rate, plus the mean decile spread."""
    ics, spreads, dates = [], [], []
    for d, sig in sorted(signal_by_date.items()):
        fwd = fwd_by_date.get(d)
        if fwd is None or len(fwd) == 0:
            continue
        j = pd.concat([pd.Series(sig).rename("s"), pd.Series(fwd).rename("f")], axis=1).dropna()
        if len(j) < MIN_NAMES:
            continue
        ics.append(rank_ic(j["s"], j["f"]))
        ds = decile_spread(j["s"], j["f"])
        if ds:
            spreads.append(ds["spread"])
        dates.append(d)
    if not ics:
        return {"n_dates": 0, "verdict": "no_data",
                "note": "No rebalance had both a scored cross-section and a realised forward window."}
    summ = ic_summary(ics, periods_per_year=periods_per_year, hac_lags=hac_lags)
    summ["n_dates"] = len(ics)
    summ["dates"] = [str(pd.Timestamp(d).date()) for d in dates]
    summ["mean_decile_spread"] = float(np.mean(spreads)) if spreads else None
    summ["n_spreads"] = len(spreads)
    return summ


VERDICTS = ("no_data", "insufficient", "null", "nominal_only", "survives_fdr", "inverted")


def _verdict(summ: dict, q: float | None) -> str:
    """Deliberately blunt, and SIGN-AWARE.

    The sign is the whole point. An |IC| test that ignores direction reports a
    significantly ANTI-predictive signal as `survives_fdr` — which reads as "the model
    works" while the model is ranking winners below losers. The first run of this harness
    did exactly that: the QV composite came back mean_ic = -0.031, t = -2.43, q < 0.10 and
    was labelled a survivor. A signal that significantly ranks backwards gets its own
    verdict, `inverted`.

    `insufficient` is likewise a first-class answer, not a failure mode — with ~3 years of
    prices most reads here cannot separate a real effect from zero, and saying so is more
    useful than a p-value that pretends otherwise.
    """
    n = summ.get("n_dates", 0)
    if n == 0:
        return "no_data"
    if n < 8:
        return "insufficient"
    ic = summ.get("mean_ic")
    t = summ.get("t_hac") or summ.get("nw_t") or summ.get("t")
    if ic is None or not np.isfinite(float(ic)):
        return "no_data"
    signif_fdr = q is not None and q < 0.10
    signif_nom = t is not None and abs(float(t)) >= 2.0
    if float(ic) < 0:
        return "inverted" if (signif_fdr or signif_nom) else "null"
    if signif_fdr:
        return "survives_fdr"
    return "nominal_only" if signif_nom else "null"


def study_model(model_key: str, *, horizon: int = DEFAULT_HORIZON,
                weights: dict | None = None, rule: str = "blend_then_rank",
                start: str | None = None, max_dates: int | None = None) -> dict:
    """Walk the rebalance grid, score the model point-in-time at each date, measure.

    Every cross-section is rebuilt from the PIT panel AS IT WAS KNOWABLE at that date, so
    no rebalance sees a not-yet-filed report. Returns per-leg results alongside the
    composite, because "the composite is null" and "every leg is null" are different
    findings and only the second one closes the construct.
    """
    from engine.quant_lab.specs import MODELS, resolve_leg_keys
    if model_key not in MODELS:
        raise KeyError(f"unknown model: {model_key!r}")
    spec = MODELS[model_key]
    # Expand ref_model legs (QVM's "qv_composite" IS the QV model) so a composite can
    # never quietly reduce to one of its own legs and keep the parent model's name.
    spec_weights = resolve_leg_keys(model_key)
    leg_keys = list(spec_weights)
    weights = weights or spec_weights

    px = legs_mod._closes(None)
    if px is None or px.empty:
        return {"model": model_key, "verdict": "no_data", "limits": STANDING_LIMITS,
                "note": "No close panel available."}
    grid = rebalance_grid(px, horizon, start=start)
    if max_dates:
        grid = grid[-max_dates:]
    if not grid:
        return {"model": model_key, "verdict": "insufficient", "limits": STANDING_LIMITS,
                "n_dates": 0,
                "note": f"No rebalance date leaves a {horizon}-day forward window in a "
                        f"{len(px)}-session panel."}

    comp_sig, fwd_by, leg_sig = {}, {}, {k: {} for k in leg_keys}
    coverage_seen: dict[str, list] = {k: [] for k in leg_keys}
    legs_used_per_date: list[int] = []
    # The 13F leg re-reads every fund shard, so only pay for it when the model uses it.
    want_fs = "fund_sentiment" in leg_keys
    for d in grid:
        try:
            r = legs_mod.compute_legs(d, with_fund_sentiment=want_fs)
        except Exception as e:                          # noqa: BLE001 — one bad date must not kill the study
            log.warning("quant_lab: legs failed at %s (%s)", d, e)
            continue
        L = r["legs"]
        if L.empty:
            continue
        avail = [k for k in leg_keys if k in L.columns and L[k].notna().sum() >= MIN_NAMES]
        if not avail:
            continue
        for k in avail:
            coverage_seen[k].append(r["coverage"].get(k, 0.0))
        legs_used_per_date.append(len(avail))
        c = score_mod.composite(L[avail], {k: weights[k] for k in avail if k in weights},
                                rule=rule)
        fwd = forward_returns(px, d, horizon)
        if len(fwd) == 0:
            continue
        fwd_by[d] = fwd
        comp_sig[d] = c["score"].dropna()
        for k in avail:
            leg_sig[k][d] = L[k].dropna()

    composite_res = study_signal(comp_sig, fwd_by)
    per_leg = {k: study_signal(v, fwd_by) for k, v in leg_sig.items() if v}

    pvals = {k: v.get("p_hac") or v.get("p") for k, v in per_leg.items()
             if v.get("n_dates", 0) >= 8 and (v.get("p_hac") or v.get("p")) is not None}
    cp = composite_res.get("p_hac") or composite_res.get("p")
    if composite_res.get("n_dates", 0) >= 8 and cp is not None:
        pvals["composite"] = cp
    fdr = benjamini_hochberg(pvals) if pvals else {}

    for k, v in per_leg.items():
        v["q"] = (fdr.get(k) or {}).get("q")
        v["verdict"] = _verdict(v, v["q"])
        cov = coverage_seen.get(k) or []
        v["mean_coverage"] = round(float(np.mean(cov)), 4) if cov else None
    composite_res["q"] = (fdr.get("composite") or {}).get("q")
    composite_res["verdict"] = _verdict(composite_res, composite_res["q"])

    # DEGENERATE GUARD. If the composite never actually blended more than one leg, it is
    # not the model — it is whichever leg survived, wearing the model's name. Report that
    # instead of a verdict, and say which legs went missing. (The first study run labelled
    # QVM "survives FDR" on an IC identical to plain 6-month momentum, because five of its
    # six fundamental legs had been silently dropped.)
    min_used = min(legs_used_per_date) if legs_used_per_date else 0
    max_used = max(legs_used_per_date) if legs_used_per_date else 0
    dropped = [k for k in leg_keys if not leg_sig.get(k)]
    degenerate = max_used < 2
    if degenerate:
        composite_res["verdict"] = "degenerate"
        composite_res["degenerate_note"] = (
            f"The composite never blended more than {max_used} leg(s); "
            f"missing legs: {', '.join(dropped) or 'none'}. Whatever this measured, it is "
            f"not {spec['name']}."
        )

    return {
        "model": model_key,
        "name": spec["name"],
        "horizon_d": horizon,
        "rule": rule,
        "n_rebalances": len(grid),
        "grid": [str(pd.Timestamp(d).date()) for d in grid],
        "spec_legs": leg_keys,
        "dropped_legs": dropped,
        "legs_blended": {"min": min_used, "max": max_used, "of": len(leg_keys)},
        "degenerate": degenerate,
        "composite": composite_res,
        "legs": per_leg,
        "fdr_alpha": 0.10,
        "limits": STANDING_LIMITS,
        "verdict": composite_res["verdict"],
    }
