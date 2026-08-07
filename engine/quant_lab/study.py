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
  universe      this study ran on a 1,552-name fundamentals panel. Fintel's QV is a
                small-cap "multi-bagger" finder benchmarked to the Russell 2000, so it was
                tested on the wrong end of the size distribution. W2-A (#4688) has since
                widened the panel past 2,800 names; re-running the study on it is open work.
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

# The options-dislocation family samples DAILY, not quarterly, so it gets its own horizon.
# 5 days is the horizon engine/options_dislocation.py ran its own raw-vs-neutralised
# diagnostics at; at h=21 the panel is ~1 window and nothing is measurable at all.
OPTIONS_HORIZON = 5

STANDING_LIMITS = {
    "survivorship": ("Close panel serves currently-listed names only; delisted losers are "
                     "absent. Every number here is an optimistic bound."),
    # Past tense on purpose: this describes the panel THIS STUDY RAN ON, which is frozen.
    # W2-A (#4688) has since widened the panel past 2,800 names — a limit that silently
    # re-read as a present-tense claim would be false the night the panel grew.
    "universe": ("The study ran on a 1,552-name fundamentals panel, concentrated above the "
                 "size band this model targets — 7 of Fintel's 10 published QVM leaders "
                 "were outside it. The panel has since been widened; this is not a re-test."),
    "history": ("In-tree close caches run ~3 years — a handful of independent quarterly "
                "rebalances, not a regime sample."),
    "tier": "Display-tier research. Nothing here promotes a score to rank/size/gate authority.",
}

# Same mechanism, same shape, stamped under the same `limits` key — these are merged into
# the artifact's standing limits by scripts/build_quant_lab.py whenever the options family
# is studied, so the page's existing "What these results cannot tell you" panel carries them
# without a second caveat vocabulary.
OPTIONS_LIMITS = {
    "options_regime": ("The options chain panel is ONE regime — 32 distinct market sessions "
                       "across six weeks. At a 5-day horizon that is ~6 independent windows, "
                       "so every t-statistic here is vacuous by construction and no number on "
                       "this family separates a real effect from zero."),
    "options_stamp": ("Ledger rows are stamped with the collector's RUN date, not the session "
                      "they read: 9 of 41 stamps repeated the prior session and the first 6 "
                      "carried too few names to neutralise. Duplicate sessions are collapsed "
                      "before scoring, but the change primitives still rest on ~13 usable "
                      "dates."),
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


# =======================================================================================
# Options dislocation — a DAILY family, scored against its own pre-registration
# =======================================================================================
def options_sessions(hist) -> list:
    """Collapse the ledger's RUN-date stamps down to distinct market sessions.

    The chain collector stamps each snapshot with the date it RAN, not the session it read.
    Weekend and Monday runs re-read the same Friday chain, so on the first ledger 9 of 41
    stamps repeated their predecessor byte-for-byte (spot equal to 1e-9 across all ~370
    names; Sunday==Saturday and Monday==Sunday, while Saturday differed from Friday because
    the Friday file already held Thursday's chain).

    Scoring those as separate dates would enter one Friday cross-section up to three times,
    shrinking every standard error on a panel whose standard errors are already meaningless.
    Detect by value rather than by weekday: a bank holiday produces the same duplicate and
    carries no weekend marker.
    """
    import numpy as np
    import pandas as pd
    keep, prev = [], None
    for d, g in hist.groupby("date", sort=True):
        v = pd.to_numeric(g.set_index("underlying")["spot"], errors="coerce").dropna()
        if prev is not None and len(v):
            common = v.index.intersection(prev.index)
            if len(common) >= 5 and float(
                    np.isclose(v[common].to_numpy(), prev[common].to_numpy(),
                               rtol=1e-9, atol=1e-9).mean()) > 0.99:
                continue                      # same session, merely re-stamped
        keep.append(str(d))
        if len(v):
            prev = v
    return keep


def study_options_dislocation(*, horizon: int = OPTIONS_HORIZON,
                              min_names: int = MIN_NAMES) -> dict:
    """Score the NEUTRALISED options primitives against their own pre-registered signs.

    `PREREG_SIGNS` is IMPORTED, never restated: the pre-registration lives in
    engine/options_dislocation.py, was fixed before the dormant gate could ever run, and a
    second copy here would be free to drift away from the one the gate tests. Each column is
    ORIENTED by its sign before scoring (`n_col * sign`), which is what lets `_verdict`'s
    existing sign-awareness read correctly: a positive IC means the primitive moved the way
    it was pre-registered to move, and a significant negative one lands as `inverted` — it
    ran against its own pre-registration, which is a finding, not a win.

    There is deliberately NO composite. RO-2 / Signal Commons R3 forbids a fused pre-gate
    score, so this returns per-primitive results only and the caller has nothing to lift.

    Forward returns are SPY-relative over `horizon` SESSIONS (not calendar days), taken from
    the ledger's own spot series after duplicate stamps are collapsed — the same construction
    engine/options_dislocation.py ran its raw-vs-neutralised diagnostics with.
    """
    import numpy as np
    import pandas as pd

    from engine.options_dislocation import PREREG_SIGNS, load_history

    hist = load_history()
    if hist is None or getattr(hist, "empty", True):
        return {"model": "options_dislocation", "verdict": "no_data",
                "limits": {**STANDING_LIMITS, **OPTIONS_LIMITS},
                "note": "No options dislocation ledger on disk."}

    hist = hist.copy()
    hist["date"] = hist["date"].astype(str)
    hist["underlying"] = hist["underlying"].astype(str).str.upper()

    stamps = sorted(hist["date"].unique())
    sessions = options_sessions(hist)
    P = hist[hist["date"].isin(set(sessions))]

    px = (P.pivot_table(index="date", columns="underlying", values="spot", aggfunc="last")
            .sort_index())
    bench = px["SPY"] if "SPY" in px.columns else None

    fwd_by: dict = {}
    for i, d in enumerate(px.index):
        j = i + horizon
        if j >= len(px.index):
            break
        f = px.iloc[j] / px.iloc[i] - 1.0
        if bench is not None and np.isfinite(bench.iloc[i]) and bench.iloc[i]:
            f = f - (bench.iloc[j] / bench.iloc[i] - 1.0)
        fwd_by[d] = f.replace([np.inf, -np.inf], np.nan).dropna()

    per_leg: dict = {}
    coverage: dict = {}
    for col, sign in PREREG_SIGNS.items():
        ncol = f"n_{col}"
        if ncol not in P.columns:
            per_leg[col] = {"n_dates": 0, "verdict": "no_data",
                            "note": f"{ncol} is not in the ledger."}
            continue
        sig_by, cov = {}, []
        for d, g in P.groupby("date", sort=True):
            if d not in fwd_by:
                continue
            s = pd.to_numeric(g.set_index("underlying")[ncol], errors="coerce").dropna()
            if len(s) < min_names:
                continue
            sig_by[d] = s * sign               # orient by the IMPORTED pre-registration
            cov.append(len(s) / max(1, len(g)))
        # periods_per_year: daily sampling. hac_lags: the measured overlap (horizon / step),
        # which ic_summary's own docstring asks callers to pass whenever the grid is sampled
        # finer than the forward window — it is, 5-deep, here.
        res = study_signal(sig_by, fwd_by, periods_per_year=252, hac_lags=horizon)
        res["prereg_sign"] = int(sign)
        res["mean_coverage"] = round(float(np.mean(cov)), 4) if cov else None
        coverage[col] = res["mean_coverage"]
        per_leg[col] = res

    pvals = {k: (v.get("p_hac") or v.get("p")) for k, v in per_leg.items()
             if v.get("n_dates", 0) >= 8 and (v.get("p_hac") or v.get("p")) is not None}
    fdr = benjamini_hochberg(pvals) if pvals else {}

    for k, v in per_leg.items():
        v["q"] = (fdr.get(k) or {}).get("q")
        # `_verdict` reads n_dates as a count of INDEPENDENT observations — true of the
        # quarterly EDGAR grid it was written for, false here: consecutive daily
        # cross-sections share 4 of their 5 forward days. Hand it the independent-window
        # count so the harness's OWN insufficiency floor (n < 8) sees the panel as it really
        # is, rather than inventing a second rule that says the same thing.
        n_ind = int(v.get("n_dates", 0) // horizon)
        v["n_independent_windows"] = n_ind
        # Printed, not hidden: what the SAME harness would have said had the overlap gone
        # uncorrected. On the first ledger every primitive came back `survives_fdr` that way
        # — seven significant-looking factors out of six weeks of a single regime. Keeping
        # the counterfactual in the artifact is what makes the correction auditable instead
        # of merely asserted.
        v["verdict_uncorrected"] = _verdict(v, v["q"])
        v["verdict"] = _verdict({**v, "n_dates": n_ind}, v["q"])

    return {
        "model": "options_dislocation",
        "name": "Options information dislocation",
        "horizon_d": horizon,
        "cadence": "daily",
        "rule": "none_categorical",
        "n_stamps": len(stamps),
        "n_sessions": len(sessions),
        "n_duplicate_stamps": len(stamps) - len(sessions),
        "n_scored_dates": len(fwd_by),
        "spec_legs": list(PREREG_SIGNS),
        "legs": per_leg,
        "coverage": coverage,
        "fdr_alpha": 0.10,
        "limits": {**STANDING_LIMITS, **OPTIONS_LIMITS},
        # No composite, and no top-level verdict that could stand in for one: RO-2 forbids a
        # fused pre-gate score, and a single headline verdict over seven primitives IS one.
        "verdict": "per_primitive",
    }
