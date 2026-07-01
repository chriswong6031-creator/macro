"""Continuous regime probabilities via a Gaussian Hidden Markov Model (v1, L2).

The legacy engine argmaxes the two axis scores into one of four boxes with a 7-day hysteresis
debounce, and reports a `|score|*agreement` "confidence" that is a heuristic, not a probability
(today it reads 0.125 — a coin flip — with no notion of how likely the regime is to flip). This
module replaces the argmax with a 4-state Gaussian HMM over the [growth_score, inflation_score]
history, yielding what the box cannot: SOFT membership P(Quad_k), a QUAD-level transition matrix
P(next quad | current quad), a per-regime HAZARD (flip probability), and expected dwell time.

State -> Quad mapping. hmmlearn's state indices are arbitrary and can permute between fits
(label switching — the plan's critique §2.4). We never rely on the index: each fitted state is
mapped to a quad by the ECONOMIC MEANING of its mean vector via engine.regime.raw_quad(g, i),
and P(Quad_k) is the sum of the posteriors of every state whose mean sits in quad k. That mapping
is deterministic from the fitted means, so it is stable across refits by construction — no
Hungarian assignment needed. If the four states do not cover all four quads (they need not), the
uncovered quad simply gets P=0 — an honest statement that the model sees no such regime in-sample.

DISPLAY-ONLY (v1): this is a parallel artifact behind `engine.regime_fwd` gating. The legacy
`raw_quad` + hysteresis path in engine/regime.py stays canonical and untouched; nothing here
drives a weight, size, or gross dial until scripts/validate_regime_fwd.py clears it. The fit is
cheap (~1s on 14k rows) but still belongs in the nightly calibration (scripts/calibrate_regime_hmm.py
writes data/regime/hmm_latest.json), NOT the render path — the renderer only reads the JSON.

NOTE on the historical P(Quad) series emitted for the chart: it is the FULL-SAMPLE smoothed
posterior (predict_proba over all history from a single fit), so historical points use future
data — fine for DESCRIPTION/display, but a *scored* claim (does P(transition) predict?) requires a
causal expanding-window refit, which is deferred to the validation harness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.regime import raw_quad

_QUADS = ("Q1", "Q2", "Q3", "Q4")
_FEATURES = ("growth_score", "inflation_score")


def _informed_hmm(X: np.ndarray, labels: np.ndarray, present: list[str], min_covar: float):
    """Build a Gaussian HMM whose states ARE the four quads, with emissions and transitions
    estimated from the legacy quad labels (supervised init — the regimes are KNOWN, not latent).
    Unsupervised EM is deliberately NOT used: on market-proxy axis scores it collapses all states
    into the dense growth>=0 half and never allocates a Q3/Q4 state. Returns a fitted-params model
    ready for predict_proba (forward-backward smoothing over the empirical transition dynamics)."""
    from hmmlearn.hmm import GaussianHMM
    k = len(present)
    means = np.array([X[labels == q].mean(axis=0) for q in present])
    covs = np.array([np.cov(X[labels == q].T) + np.eye(2) * min_covar for q in present])
    idx = {q: j for j, q in enumerate(present)}
    tm = np.full((k, k), 1e-6)
    for a, b in zip(labels[:-1], labels[1:]):
        if a in idx and b in idx:
            tm[idx[a], idx[b]] += 1.0
    tm /= tm.sum(axis=1, keepdims=True)
    sp = np.array([(labels == q).mean() for q in present], dtype=float)
    sp /= sp.sum()
    m = GaussianHMM(n_components=k, covariance_type="full", init_params="", params="")
    m.startprob_, m.transmat_, m.means_, m.covars_ = sp, tm, means, covs
    return m


def _empirical_transmat(labels: np.ndarray) -> dict[str, dict[str, float]]:
    """Quad-level transition matrix P(next quad | current quad) counted from the quad path over
    the FULL history — the interpretable object the plan wants, covering all four quads."""
    out = {i: {j: 0.0 for j in _QUADS} for i in _QUADS}
    counts = {i: 0 for i in _QUADS}
    for a, b in zip(labels[:-1], labels[1:]):
        if a in out:
            out[a][b] += 1.0
            counts[a] += 1
    for i in _QUADS:
        if counts[i]:
            for j in _QUADS:
                out[i][j] = round(out[i][j] / counts[i], 4)
    return out


def fit_regime_hmm(scores: pd.DataFrame, min_per_quad: int = 60, min_covar: float = 1e-3,
                   history_days: int = 756) -> dict | None:
    """Fit the informed HMM and return the current soft regime read + transition/hazard structure.

    `scores` needs a DatetimeIndex and the columns growth_score, inflation_score (as written to
    data/regime/regime_history.parquet). Returns None if there is too little data or the fit fails."""
    cols = list(_FEATURES) + (["quad"] if "quad" in scores.columns else [])
    df = scores[cols].dropna(subset=list(_FEATURES))
    # Label source = the committed hysteresis-DEBOUNCED quad (the regime the system actually
    # tracks; realistic ~2-month persistence). Recomputing raw_quad off the axis scores flickers.
    # Fall back to raw_quad only if the column is absent.
    if "quad" in df.columns:
        df = df[df["quad"].notna()]
    if len(df) < 504:  # ~2y of business days minimum
        return None
    X = df[list(_FEATURES)].to_numpy(dtype=float)
    labels = (df["quad"].to_numpy() if "quad" in df.columns
              else np.array([raw_quad(float(g), float(i)) or "Q4" for g, i in X]))
    present = [q for q in _QUADS if int((labels == q).sum()) >= min_per_quad]
    if len(present) < 2:
        return None
    model = _informed_hmm(X, labels, present, min_covar)

    post = model.predict_proba(X)                              # T x k smoothed quad posterior
    qpost = np.zeros((len(X), 4))
    for s, q in enumerate(present):                            # state s IS quad `present[s]`
        qpost[:, _QUADS.index(q)] = post[:, s]
    modal = np.array([_QUADS[i] for i in qpost.argmax(axis=1)])

    # Regime-transition dynamics at MONTHLY frequency: quads persist for months, so a DAILY
    # transition matrix is dominated by argmax jitter and understates dwell (P(stay) looks low
    # only because the raw path flickers to adjacent quads and back). Month-end labels give the
    # honest "how likely is the regime to change this month / how long do regimes last."
    monthly = pd.Series(labels, index=df.index).resample("ME").last().dropna().to_numpy()
    transmat = _empirical_transmat(monthly)                    # empirical P(next|cur) over all 4 quads
    cur_quad = modal[-1]
    p_stay = transmat[cur_quad][cur_quad]
    hazard = round(1.0 - p_stay, 4)                            # P(leave current quad next MONTH)
    dwell = round(1.0 / (1.0 - p_stay), 1) if p_stay < 1.0 else None   # expected regime length, months
    tir_m = 0                                                  # trailing months in the current quad
    for q in monthly[::-1]:
        if q == monthly[-1]:
            tir_m += 1
        else:
            break

    today = qpost[-1]
    idx = df.index
    hist = [{"date": str(d.date()), **{q: round(float(qpost[k, m]), 4) for m, q in enumerate(_QUADS)}}
            for k, d in list(enumerate(idx))[-history_days:]]

    # agreement with the legacy argmax quad (a sanity read, not a target)
    agree = round(float(np.mean(modal == labels)), 3)

    return {
        "asof": str(idx[-1].date()),
        "n_obs": int(len(X)),
        "n_states": int(len(present)),
        "quads_present": present,
        "regime_probs": {q: round(float(today[m]), 4) for m, q in enumerate(_QUADS)},
        "modal_quad": cur_quad,
        "transition_matrix": transmat,
        "next_quad_probs": transmat[cur_quad],
        "hazard": hazard,                       # P(leave current quad next MONTH)
        "expected_dwell_months": dwell,         # 1/hazard, months
        "time_in_regime_months": tir_m,
        "state_means": [{"quad": present[s], "growth": round(float(mu[0]), 3),
                         "inflation": round(float(mu[1]), 3)} for s, mu in enumerate(model.means_)],
        "legacy_agreement": agree,              # fraction of days modal HMM quad == raw_quad
        "history": hist,
        "note": ("display-only smoothed posterior; scored use requires causal expanding-window "
                 "refit + validate_regime_fwd.py"),
    }


def main() -> int:  # pragma: no cover - manual inspection
    import json
    from lib import config
    df = pd.read_parquet(config.data_dir() / "regime" / "regime_history.parquet")
    out = fit_regime_hmm(df)
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
