"""Regime One — the canonical regime artifact with an HONEST decomposition.

Masterplan W2 (`#1 #3 #4 #16 #32`), companion to research/ENGINE_FIX_MASTERPLAN.md §W2
and research/PIT_LEAKAGE_TAX.md.

WHY THIS EXISTS
---------------
The legacy `regime.classify()` fuses coincident market-proxy legs (copper/gold, XLY/XLP,
IWM/SPY, cyclical/defensive, breadth — 73% of the axis weight, all 20d first-derivative
reads) with a minority of monthly econ legs into ONE quad and brands it a forward Hedgeye
regime (`#1`). Three lies compound:
  * the quad is COINCIDENT ("prices already turned") but presented as forward,
  * the econ legs are read latest-revised on their reference stamp (a 34-121d look-ahead,
    measured in PIT_LEAKAGE_TAX.md), and
  * when a feed dies the weighted axis silently renormalizes over survivors (`axes.py:77-79`)
    so an OUTAGE looks like a regime move (`#3`) — and history keeps no freshness column to
    tell full-data days from price-only-proxy days after the fact (`#32`).

Regime One publishes ALONGSIDE the legacy artifacts (SHADOW-FIRST — zero behavioral change
to any current consumer this wave). It splits the single number into four honest reads:

  tape    : the coincident market-proxy read, per-leg, LABELLED coincident.
  macro   : the econ legs on the leak-free `basis='release'` frame (engine/pit.py), each
            carrying per-leg freshness + release-lag provenance.
  forward : causal (FILTERED, non-smoothed) P(Quad) from a supervised HMM + base_effect's
            forward YoY read, each with an explicit `graded: {n, status}` accrual block.
  fused_risk : {label (5-state from engine.risk_state's vocabulary), gross_factor (via the
            single versioned RISK_STATE_GROSS table), confidence}. Confidence DEGRADES at
            inflections: when tape and macro disagree on the INFLATION axis, the leakage
            finding (84.2% PIT-vs-latest agreement, disagreement concentrated on the
            inflation axis at inflections) is encoded as an explicit uncertainty input.

Plus the novel mechanism — FLIP ATTRIBUTION: every label/quad change decomposes into
{data_delta, renorm_delta, revision_delta}. A flip whose majority cause is renormalization
(a leg went NaN/stale and vanished from the weighted sum) is VETOED: the label freezes at
its prior value and a loud `degraded` state is published. An outage can no longer flip the
quad (`#3`).

Every emitted number carries a PASSPORT {basis, frame, freshness, n}.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import pit
from engine.axes import score_axis
from engine.regime import QUAD_NAMES, raw_quad
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "regime_one.v1"

# --------------------------------------------------------------------------- #
# The SINGLE versioned risk-state -> gross-factor mapping table. Defined in ONE
# place (this dict). Mirrors engine.risk_state._DEFAULT_GROSS so the fused_risk
# gross_factor is traceable to a single source; the risk-unification wave (P2-B')
# retires the duplicate and points every consumer here.
# --------------------------------------------------------------------------- #
RISK_STATE_GROSS_VERSION = "2026-07-01.v1"
RISK_STATE_GROSS: dict[str, float] = {
    "risk-on":  1.00,
    "neutral":  1.00,
    "caution":  0.90,
    "elevated": 0.78,
    "risk-off": 0.60,
}
_GROSS_FLOOR = 0.50

# 5-state vocabulary (order = increasing drawdown risk), identical to
# engine.risk_state._STATE_ORDER — the vocabulary we unify ON.
STATE_ORDER = ["risk-on", "neutral", "caution", "elevated", "risk-off"]
STATE_LABEL = {
    "risk-on":  ("Risk-on (regime supportive)", "偏risk-on（体制支持）"),
    "neutral":  ("Neutral", "中性"),
    "caution":  ("Caution", "留意"),
    "elevated": ("Elevated risk", "风险偏高"),
    "risk-off": ("Risk-off", "risk-off"),
}

# Quad -> base risk state prior. Q1/Q2 (growth accelerating) are supportive; Q3
# (stagflation) and Q4 (growth-scare) are risk-elevating. This is the regime's
# CONTRIBUTION to the fused state, NOT the whole state (risk_state.py fuses the
# market-internal legs; here we translate the quad honestly).
_QUAD_RISK_PRIOR = {"Q1": "risk-on", "Q2": "neutral", "Q3": "elevated", "Q4": "risk-off"}

# tape (coincident market-proxy) vs macro (econ) leg partition of each axis.
# These names match the c_{axis}_{leg} columns emitted by engine.axes.
_TAPE_GROWTH = ("copper_gold", "xly_xlp", "us2y_direction", "iwm_spy",
                "cyclical_defensive", "breadth_direction")
_MACRO_GROWTH = ("payrolls_trend", "indpro_trend", "wei_trend", "gdpnow_trend")
_TAPE_INFL = ("breakeven_10y_direction", "breakeven_5y5y_direction", "energy_rs",
              "oil_trend", "inflation_beta_basket", "tips_nominal_momentum")
_MACRO_INFL = ("sticky_cpi_direction",)

# macro leg -> the underlying live-frame column that carries its release/vintage
# provenance (for freshness + release-lag stamping via engine.pit).
_MACRO_LEG_COL = {
    "payrolls_trend": "payrolls", "indpro_trend": "indpro", "wei_trend": "wei",
    "gdpnow_trend": "gdpnow", "sticky_cpi_direction": "sticky_cpi",
}
# expected cadence per macro leg (drives the freshness-state thresholds).
_MACRO_CADENCE = {
    "payrolls_trend": "M", "indpro_trend": "M", "wei_trend": "W",
    "gdpnow_trend": "M", "sticky_cpi_direction": "M",
}
# max age in calendar days before a leg is 'slow' / 'stale' / 'dead', by cadence.
# Tuned so a legitimately-slow monthly print (published ~30-45d after ref end,
# then next print ~30d later) is not falsely flagged, but a genuine multi-cycle
# outage is (#3 vs the false-abort concern in #32).
_CADENCE_FRESH = {
    "W": {"slow": 12, "stale": 21, "dead": 45},
    "M": {"slow": 50, "stale": 75, "dead": 130},
    "Q": {"slow": 140, "stale": 200, "dead": 320},
    "D": {"slow": 5, "stale": 12, "dead": 30},
}


# --------------------------------------------------------------------------- #
# Freshness
# --------------------------------------------------------------------------- #
def _freshness_state(age_days: int | None, cadence: str) -> str:
    if age_days is None:
        return "unknown"
    t = _CADENCE_FRESH.get(cadence, _CADENCE_FRESH["M"])
    if age_days > t["dead"]:
        return "dead"
    if age_days > t["stale"]:
        return "stale"
    if age_days > t["slow"]:
        return "slow"
    return "fresh"


def _last_obs_date(col: str) -> pd.Timestamp | None:
    """Native reference-stamp date of the last real observation of a leg's source
    column (not the ffill'd business-day grid). None if unresolvable."""
    try:
        ref = pit._reference_series(col)
    except Exception:  # noqa: BLE001
        ref = None
    if ref is None or ref.empty:
        return None
    return pd.Timestamp(ref.dropna().index[-1])


def _leg_freshness(col: str, cadence: str, asof: pd.Timestamp) -> dict:
    last = _last_obs_date(col)
    age = None if last is None else max(0, int((pd.Timestamp(asof).normalize() - last.normalize()).days))
    return {
        "asof": None if last is None else str(last.date()),
        "expected_cadence": cadence,
        "age_days": age,
        "state": _freshness_state(age, cadence),
    }


# --------------------------------------------------------------------------- #
# Axis sub-reads (tape vs macro), from an already-scored axis row
# --------------------------------------------------------------------------- #
def _weights(axis: str) -> dict[str, float]:
    comp = config.load()["engine"][f"{axis}_axis"]["components"]
    return {k: float(v["weight"]) for k, v in comp.items()}


def _subread(row: pd.Series, axis: str, legs: tuple[str, ...]) -> dict:
    """Weighted mean of a leg subset of an axis, renormalized over available legs
    (mirrors axes.py), plus per-leg values. Returns score in [-1, 1] or None."""
    w = _weights(axis)
    num, den, per = 0.0, 0.0, {}
    for leg in legs:
        col = f"c_{axis}_{leg}"
        v = row.get(col)
        val = None if (v is None or (isinstance(v, float) and np.isnan(v))) else int(v)
        wi = w.get(leg, 0.0)
        per[leg] = {"value": val, "weight": wi}
        if val is not None and wi > 0:
            num += val * wi
            den += wi
    score = round(num / den, 4) if den > 0 else None
    n_avail = sum(1 for p in per.values() if p["value"] is not None)
    return {"score": score, "n_available": n_avail, "n_total": len(legs),
            "weight_available": round(den, 3), "legs": per}


def _tape_read(row: pd.Series, asof: pd.Timestamp) -> dict:
    g = _subread(row, "growth", _TAPE_GROWTH)
    i = _subread(row, "inflation", _TAPE_INFL)
    return {
        "growth": g["score"], "inflation": i["score"],
        "quad": raw_quad(g["score"] if g["score"] is not None else np.nan,
                         i["score"] if i["score"] is not None else np.nan),
        "growth_legs": g["legs"], "inflation_legs": i["legs"],
        "n_available": g["n_available"] + i["n_available"],
        "coincident": True,
        "note": "coincident market-proxy read (copper/gold, XLY/XLP, IWM/SPY, cyc/def, "
                "breadth, 2y) — prices have already turned; this is not a forecast.",
        "passport": _passport(basis="market", frame="latest",
                              freshness={"asof": str(pd.Timestamp(asof).date()),
                                         "expected_cadence": "D", "state": "fresh"},
                              n=g["n_available"] + i["n_available"]),
    }


def _macro_read(release_row: pd.Series, asof: pd.Timestamp) -> dict:
    """Econ-leg read on the LEAK-FREE release frame, per-leg freshness + release-lag
    provenance attached. `release_row` is the last row of a build_features(pit_basis=
    'release') axis scoring (so the leg c_ values are release-stamped)."""
    g = _subread(release_row, "growth", _MACRO_GROWTH)
    i = _subread(release_row, "inflation", _MACRO_INFL)

    def _enrich(sub: dict) -> dict:
        for leg, cell in sub["legs"].items():
            col = _MACRO_LEG_COL.get(leg)
            cad = _MACRO_CADENCE.get(leg, "M")
            if col is not None:
                cell["freshness"] = _leg_freshness(col, cad, asof)
                cell["release"] = pit.release_provenance(col)
        return sub

    g = _enrich(g)
    i = _enrich(i)
    states = [c["freshness"]["state"] for sub in (g, i) for c in sub["legs"].values()
              if "freshness" in c]
    worst = "fresh"
    for order in ("dead", "stale", "slow", "unknown", "fresh"):
        if order in states:
            worst = order
            break
    return {
        "growth": g["score"], "inflation": i["score"],
        "quad": raw_quad(g["score"] if g["score"] is not None else np.nan,
                         i["score"] if i["score"] is not None else np.nan),
        "growth_legs": g["legs"], "inflation_legs": i["legs"],
        "n_available": g["n_available"] + i["n_available"],
        "worst_freshness": worst,
        "note": "econ legs on the leak-free release frame (engine/pit.py basis='release'): "
                "each row carries only what was published & knowable on that day, initial "
                "release not latest-revised. Per-leg release lag + freshness attached.",
        "passport": _passport(basis="release", frame="pit",
                              freshness={"asof": str(pd.Timestamp(asof).date()),
                                         "expected_cadence": "M", "state": worst},
                              n=g["n_available"] + i["n_available"]),
    }


# --------------------------------------------------------------------------- #
# Forward: causal (filtered) P(Quad) + base_effect
# --------------------------------------------------------------------------- #
_QUADS = ("Q1", "Q2", "Q3", "Q4")


def _causal_filtered_pquad(scores: pd.DataFrame, min_per_quad: int = 60,
                           min_covar: float = 1e-3) -> dict | None:
    """FILTERED (causal) P(Quad) for the latest day — the forward (alpha) recursion
    of a supervised Gaussian HMM using ONLY data up to each t. This is the HONEST
    live probability: unlike engine.regime_hmm.fit_regime_hmm's predict_proba (full-
    sample forward-BACKWARD smoothing, which uses future data at every historical
    point — fine for a hindsight chart, a lie as live history), the filtered posterior
    at t conditions on observations 1..t only. Emissions/transitions are estimated
    supervised from the legacy quad labels (same as regime_hmm — EM collapses on
    market-proxy scores). Returns the current filtered P(Quad) + a filtered history."""
    try:
        from hmmlearn.hmm import GaussianHMM
    except Exception as e:  # noqa: BLE001
        log.warning("regime_one: hmmlearn unavailable: %s", e)
        return None
    feats = ["growth_score", "inflation_score"]
    cols = feats + (["quad"] if "quad" in scores.columns else [])
    df = scores[cols].dropna(subset=feats)
    if "quad" in df.columns:
        df = df[df["quad"].notna()]
    if len(df) < 504:
        return None
    X = df[feats].to_numpy(dtype=float)
    labels = (df["quad"].to_numpy() if "quad" in df.columns
              else np.array([raw_quad(float(g), float(i)) or "Q4" for g, i in X]))
    present = [q for q in _QUADS if int((labels == q).sum()) >= min_per_quad]
    if len(present) < 2:
        return None
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

    # forward (alpha) recursion in log space -> FILTERED posterior at each t.
    logB = m._compute_log_likelihood(X)          # T x k emission log-likelihoods
    log_tm = np.log(np.maximum(tm, 1e-300))
    log_sp = np.log(np.maximum(sp, 1e-300))
    T = len(X)
    log_alpha = np.empty((T, k))
    log_alpha[0] = log_sp + logB[0]
    log_alpha[0] -= _logsumexp(log_alpha[0])     # normalize -> filtered posterior at t=0
    for t in range(1, T):
        prev = log_alpha[t - 1]
        for j in range(k):
            log_alpha[t, j] = _logsumexp(prev + log_tm[:, j]) + logB[t, j]
        log_alpha[t] -= _logsumexp(log_alpha[t])
    filt = np.exp(log_alpha)                      # T x k, rows sum to 1 (filtered)

    def to_quad(post_row):
        out = {q: 0.0 for q in _QUADS}
        for s, q in enumerate(present):
            out[q] = round(float(post_row[s]), 4)
        return out

    today = to_quad(filt[-1])
    modal = max(today, key=today.get)
    hist = [{"date": str(d.date()), **to_quad(filt[j])}
            for j, d in list(enumerate(df.index))[-252:]]
    return {
        "asof": str(df.index[-1].date()),
        "regime_probs_filtered": today,
        "modal_quad": modal,
        "quads_present": present,
        "n_obs": int(T),
        "smoothed_hindsight": False,   # this is the causal live read
        "history_filtered": hist,
        "note": "FILTERED (causal, forward-alpha) P(Quad): each point conditions on data "
                "up to that day only. Not the smoothed hindsight chart.",
    }


def _logsumexp(a: np.ndarray) -> float:
    m = float(np.max(a))
    if not np.isfinite(m):
        return m
    return m + float(np.log(np.sum(np.exp(a - m))))


def _graded_status(jsonl_path, realized_keys: tuple[str, ...]) -> dict:
    """Accrual status for a forward-grading ledger: n rows total, n matured (all
    realized_* keys non-null), earliest un-matured asof. Currently accruing -> the
    honest {n, status} block the masterplan demands on every forward number."""
    n_total, n_matured = 0, 0
    try:
        if jsonl_path.exists():
            import json
            for line in jsonl_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                n_total += 1
                if realized_keys and all(r.get(kk) is not None for kk in realized_keys):
                    n_matured += 1
    except Exception:  # noqa: BLE001
        pass
    status = "accruing" if n_matured < 20 else "gradeable"
    return {"n": n_total, "n_matured": n_matured, "status": status,
            "gate": "scripts/validate_regime_fwd.py"}


def _forward_read(full_regime: pd.DataFrame, base_effect: dict | None,
                  data_dir) -> dict:
    p = data_dir / "regime"
    pquad = _causal_filtered_pquad(full_regime)
    be = base_effect or {}
    return {
        "p_quad": {
            "value": (pquad or {}).get("regime_probs_filtered"),
            "modal_quad": (pquad or {}).get("modal_quad"),
            "smoothed_hindsight": False,
            "graded": _graded_status(p / "regime_fwd_hmm.jsonl",
                                     ("realized_quad_at_21d",)),
            "passport": _passport(basis="measured", frame="latest",
                                  freshness={"asof": (pquad or {}).get("asof"),
                                             "expected_cadence": "D", "state": "fresh"},
                                  n=(pquad or {}).get("n_obs", 0)),
            "history_filtered": (pquad or {}).get("history_filtered"),
        },
        "base_effect": {
            "growth_q1": (be.get("growth") or {}).get("q1"),
            "inflation_q1": (be.get("inflation") or {}).get("q1"),
            "growth_note": be.get("growth_note"),
            "inflation_note": be.get("inflation_note"),
            "revised": be.get("revised"),
            "graded": _graded_status(p / "base_effect_fwd.jsonl",
                                     ("realized_growth_2d_at_63d", "realized_infl_2d_at_63d")),
            "passport": _passport(basis="measured",
                                  frame=("pit" if be.get("revised") is False else "latest"),
                                  freshness={"asof": be.get("as_of"),
                                             "expected_cadence": "M", "state": "fresh"},
                                  n=0),
        },
        "note": "forward reads are ACCRUING — display-only until the graded ledgers "
                "mature and scripts/validate_regime_fwd.py issues a go.",
    }


# --------------------------------------------------------------------------- #
# Fused risk: label (5-state) + gross + confidence (degrades at inflections)
# --------------------------------------------------------------------------- #
def _inflation_axis_disagreement(tape: dict, macro: dict) -> dict:
    """The leakage finding operationalized: PIT-vs-latest quad agreement is 84.2% and
    the disagreement concentrates on the INFLATION axis at inflections (see
    research/PIT_LEAKAGE_TAX.md). Here, tape (coincident, latest) vs macro (release,
    leak-free) inflation-sign disagreement is the LIVE analog of that inflection
    confusion. When they disagree on the inflation sign, we are likely AT such an
    inflection -> confidence must drop. Returns a signed uncertainty input."""
    ti, mi = tape.get("inflation"), macro.get("inflation")
    if ti is None or mi is None:
        return {"disagree": False, "reason": "insufficient legs", "uncertainty": 0.10}
    ts, ms = int(np.sign(ti)), int(np.sign(mi))
    disagree = (ts != 0 and ms != 0 and ts != ms)
    return {
        "disagree": bool(disagree),
        "tape_inflation_sign": ts, "macro_inflation_sign": ms,
        "reason": ("tape (coincident) and macro (release) inflation axes DISAGREE on sign "
                   "— likely an inflation-axis inflection, the 84.2%-agreement/inflection "
                   "confusion; regime label is low-confidence here"
                   if disagree else "tape & macro inflation axes agree on sign"),
        # explicit uncertainty contribution (not a footnote): a sign disagreement on
        # the inflation axis is worth a large confidence haircut.
        "uncertainty": 0.35 if disagree else 0.05,
    }


def _fused_risk(tape: dict, macro: dict, legacy_quad: str, degraded: dict,
                base_conf: float) -> dict:
    """Fuse into the 5-state vocabulary with the single versioned gross table and a
    confidence that degrades at inflections and on degraded (renorm-vetoed) days."""
    # base state from the (frozen-if-vetoed) label quad
    quad = degraded["label_quad"]
    state = _QUAD_RISK_PRIOR.get(quad, "neutral")

    infl = _inflation_axis_disagreement(tape, macro)

    # confidence: start from the axis confidence, subtract the inflection uncertainty
    # and a degraded penalty. Clamp to [0.05, 0.98].
    conf = float(base_conf)
    conf -= infl["uncertainty"]
    if degraded["degraded"]:
        conf -= 0.30
        # a renorm-vetoed flip is itself an elevated-risk tell (feed integrity gone):
        # nudge the state one notch more cautious but never below the frozen label.
        cur = STATE_ORDER.index(state)
        state = STATE_ORDER[min(cur + 1, len(STATE_ORDER) - 1)]
    # tape vs macro growth disagreement is a softer uncertainty input
    tg, mg = tape.get("growth"), macro.get("growth")
    if tg is not None and mg is not None and np.sign(tg) != np.sign(mg) and tg != 0 and mg != 0:
        conf -= 0.10
    conf = round(max(0.05, min(0.98, conf)), 3)

    gross = RISK_STATE_GROSS.get(state, 1.0)
    if degraded["degraded"]:
        # on a degraded read, hold gross no looser than 'caution' regardless of label
        gross = min(gross, RISK_STATE_GROSS["caution"])
    gross = round(max(_GROSS_FLOOR, gross), 3)

    en, zh = STATE_LABEL[state]
    return {
        "label": state,
        "label_en": en,
        "label_zh": zh,
        "gross_factor": gross,
        "gross_mapping_version": RISK_STATE_GROSS_VERSION,
        "confidence": conf,
        "inflation_inflection": infl,
        "degraded": degraded["degraded"],
        "note": "5-state fused risk from the legacy-quad prior + inflection uncertainty; "
                "gross via the single versioned RISK_STATE_GROSS table. SHADOW — no live "
                "consumer flips this wave (risk-vocabulary unification is P2-B').",
        "passport": _passport(basis="measured", frame="latest",
                              freshness={"asof": degraded.get("asof"),
                                         "expected_cadence": "D",
                                         "state": "degraded" if degraded["degraded"] else "fresh"},
                              n=tape.get("n_available", 0) + macro.get("n_available", 0)),
    }


# --------------------------------------------------------------------------- #
# Flip attribution (the novel mechanism) — data vs renorm vs revision delta
# --------------------------------------------------------------------------- #
def attribute_flip(prev: dict | None, tape: dict, macro: dict,
                   legacy_quad: str, prev_release_weight: dict | None = None,
                   release_weight: dict | None = None) -> dict:
    """Decompose a quad/label change since the prior published regime_one into
    {data_delta, renorm_delta, revision_delta} and decide whether to VETO it.

    The move we protect against (#3): a leg goes NaN/stale, drops out of the weighted
    sum, and the axis renormalizes over survivors so the score (and quad) MOVES with no
    real economic change (axes.py:77-79). We separate:
      * renorm_delta  — share of the axis-score move attributable to the AVAILABLE-
                        WEIGHT changing (legs appearing/vanishing) rather than leg
                        VALUES changing. Estimated by re-scoring the prior legs on the
                        CURRENT available-weight and vice-versa.
      * data_delta    — share attributable to leg VALUES flipping (genuine signal).
      * revision_delta— share attributable to release-frame VALUE changes (a leg's
                        release value revised vs the prior published read) — the PIT
                        revision channel.

    Renorm share > 50% of the total axis move on the axis that drives the quad flip
    -> VETO: freeze the label at the prior quad, publish `degraded`.
    """
    cur_quad = legacy_quad
    prev_quad = (prev or {}).get("label", {}).get("quad") if prev else None
    prev_quad = prev_quad or ((prev or {}).get("fused_risk", {}) or {}).get("_quad")
    # fall back to the previously published TAPE+MACRO fused legacy quad if stored
    prev_quad = prev_quad or (prev or {}).get("_legacy_quad")

    result = {
        "asof": tape["passport"]["freshness"]["asof"],
        "prev_quad": prev_quad,
        "cur_quad": cur_quad,
        "flipped": bool(prev_quad is not None and prev_quad != cur_quad),
        "label_quad": cur_quad,      # the quad the label will USE (may be frozen)
        "degraded": False,
        "components": None,
    }
    if not result["flipped"]:
        return result

    # which axis drove the flip? the one whose sign changed between prev and cur quad.
    from engine.regime import _quad_signs
    pg, pi = _quad_signs(prev_quad)
    cg, ci = _quad_signs(cur_quad)
    axis = "growth" if (pg != cg) else "inflation"

    # combine tape+macro legs for the driving axis to reconstruct the full-axis move.
    cur_legs = {**tape.get(f"{axis}_legs", {}), **macro.get(f"{axis}_legs", {})}
    prev_tape = (prev or {}).get("tape", {}) or {}
    prev_macro = (prev or {}).get("macro", {}) or {}
    prev_legs = {**prev_tape.get(f"{axis}_legs", {}), **prev_macro.get(f"{axis}_legs", {})}

    # per-axis component weights (the same weights axes.py renormalizes over).
    axis_w = _weights(axis)

    def _val(legs: dict) -> dict:
        """leg -> value, only for legs with a non-None value (the AVAILABLE set)."""
        return {leg: cell["value"] for leg, cell in legs.items()
                if cell.get("value") is not None}

    def _wmean(avail: set, values: dict) -> float | None:
        """Weighted mean over `avail` legs using `values`, renormalized over the legs
        that are BOTH in avail AND have a value — exactly axes.py's contract."""
        num = den = 0.0
        for leg in avail:
            v = values.get(leg)
            wi = axis_w.get(leg, 0.0)
            if v is None or wi <= 0:
                continue
            num += v * wi
            den += wi
        return (round(num / den, 4) if den > 0 else None)

    prev_vals = _val(prev_legs)
    cur_vals = _val(cur_legs)
    prev_avail = set(prev_vals)
    cur_avail = set(cur_vals)

    prev_score = _wmean(prev_avail, prev_vals)
    cur_score = _wmean(cur_avail, cur_vals)
    # renorm-only: hold VALUES at prev, change AVAILABILITY to cur (legs die/appear).
    # A newly-available leg with no prev value is skipped (it contributes to neither).
    renorm_only_score = _wmean(cur_avail, prev_vals)
    # data-only: hold AVAILABILITY at prev, change VALUES to cur. Legs that died keep
    # their prev value so they don't leave the set — isolates pure value moves.
    data_vals = {leg: cur_vals.get(leg, prev_vals.get(leg)) for leg in prev_avail}
    data_only_score = _wmean(prev_avail, data_vals)

    def _mag(a, b):
        return abs((a if a is not None else 0.0) - (b if b is not None else 0.0))

    total = _mag(cur_score, prev_score)
    data_delta = _mag(data_only_score, prev_score)       # values moved, structure fixed
    renorm_delta = _mag(renorm_only_score, prev_score)   # structure moved, values fixed
    # revision channel: release-frame value change on the macro legs (values in the
    # release frame differ from the prior published release read). Bounded by data_delta.
    revision_delta = 0.0
    for leg in _MACRO_GROWTH + _MACRO_INFL:
        pc = prev_legs.get(leg)
        cc = cur_legs.get(leg)
        if pc and cc and pc.get("value") is not None and cc.get("value") is not None:
            if pc["value"] != cc["value"]:
                revision_delta += abs(cc["value"] - pc["value"]) * cc.get("weight", 0.0)
    denom = (data_delta + renorm_delta) or 1e-9
    renorm_share = round(renorm_delta / denom, 3)
    data_share = round(data_delta / denom, 3)

    # legs that VANISHED (present prev, NaN now) — the renorm cause
    vanished = [leg for leg in prev_legs
                if prev_legs[leg].get("value") is not None
                and cur_legs.get(leg, {}).get("value") is None]

    veto = renorm_share > 0.50
    result["components"] = {
        "driving_axis": axis,
        "total_axis_move": round(total, 4),
        "data_delta": round(data_delta, 4),
        "renorm_delta": round(renorm_delta, 4),
        "revision_delta": round(revision_delta, 4),
        "renorm_share": renorm_share,
        "data_share": data_share,
        "vanished_legs": vanished,
        "prev_axis_score": prev_score, "cur_axis_score": cur_score,
    }
    if veto:
        result["degraded"] = True
        result["label_quad"] = prev_quad     # FREEZE at prior
        result["degraded_reason"] = (
            f"FLIP VETOED: {renorm_share:.0%} of the {axis}-axis move is renormalization "
            f"(legs vanished: {', '.join(vanished) or 'weight shifted'}), not data. "
            f"Label frozen at {prev_quad}; treat as a feed-integrity outage, not a regime "
            f"change (#3). Publishing degraded.")
        log.warning("regime_one: %s", result["degraded_reason"])
    return result


# --------------------------------------------------------------------------- #
# Passports
# --------------------------------------------------------------------------- #
def _passport(*, basis: str, frame: str, freshness: dict, n: int,
              validation: dict | None = None) -> dict:
    """The typed provenance envelope (masterplan 'Signal Passports'):
    {basis: measured|prior|anecdote|market|release, frame: pit|latest|market,
     freshness: {...}, n}. Every regime_one number carries one."""
    return {"basis": basis, "frame": frame, "freshness": freshness, "n": int(n),
            "validation": validation or {"artifact": "calibration/leakage_tax.json",
                                         "status": "shadow"}}


# --------------------------------------------------------------------------- #
# Freshness ledger (compact) for regime history (#32)
# --------------------------------------------------------------------------- #
# Bit positions for the compact per-component freshness bitmask persisted alongside
# regime history so every row is forever auditable as full-data vs degraded. We do
# NOT reconstruct history retroactively (impossible — c_ columns were dropped); this
# starts accruing now. One small int per row (not the fat c_ columns #32 objected to).
_LEDGER_BITS = {
    "payrolls": 0, "indpro": 1, "wei": 2, "gdpnow": 3, "sticky_cpi": 4,
}
_LEDGER_DEGRADED_BIT = 15   # high bit set when the day was renorm-degraded


def freshness_bitmask(macro: dict, degraded: bool) -> int:
    """Pack per-macro-leg freshness into one small int: bit set = that leg was
    fresh/slow (available), unset = stale/dead/missing. Plus the degraded flag."""
    mask = 0
    legs = {**macro.get("growth_legs", {}), **macro.get("inflation_legs", {})}
    for leg, cell in legs.items():
        col = _MACRO_LEG_COL.get(leg)
        if col is None:
            continue
        bit = _LEDGER_BITS.get(col)
        if bit is None:
            continue
        st = (cell.get("freshness") or {}).get("state")
        if st in ("fresh", "slow"):
            mask |= (1 << bit)
    if degraded:
        mask |= (1 << _LEDGER_DEGRADED_BIT)
    return int(mask)


def decode_bitmask(mask: int) -> dict:
    """Inverse of freshness_bitmask — for the auditor. Returns per-leg available bool
    + degraded flag."""
    out = {col: bool(mask & (1 << bit)) for col, bit in _LEDGER_BITS.items()}
    out["degraded"] = bool(mask & (1 << _LEDGER_DEGRADED_BIT))
    return out


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def compute(full_regime: pd.DataFrame, release_axis_row: pd.Series | None,
            base_effect: dict | None, legacy_latest: dict,
            prev: dict | None = None, data_dir=None) -> dict:
    """Build the regime_one artifact.

    Parameters
    ----------
    full_regime : the full classify() frame (WITH c_ leg columns) — for the tape read
        (last row) and the causal HMM (growth_score/inflation_score/quad history).
    release_axis_row : the last row of a scored axis frame built on the LEAK-FREE
        release basis (c_ leg columns). If None, macro falls back to the reference
        legs from full_regime (flagged in the passport).
    base_effect : engine.base_effect.compute(...) output (forward YoY read).
    legacy_latest : the legacy latest.json dict (for asof/quad/confidence).
    prev : the previously published regime_one dict (for flip attribution). None on
        first run.
    """
    if data_dir is None:
        data_dir = config.data_dir()
    asof = full_regime["quad"].last_valid_index()
    row = full_regime.loc[asof]
    legacy_quad = str(row["quad"])
    base_conf = float(row.get("regime_confidence") or 0.0)

    tape = _tape_read(row, asof)
    macro_src = release_axis_row if release_axis_row is not None else row
    macro = _macro_read(macro_src, asof)
    if release_axis_row is None:
        macro["passport"]["basis"] = "reference"
        macro["passport"]["frame"] = "latest"
        macro["note"] += " [FALLBACK: release frame unavailable — reference legs used]"

    flip = attribute_flip(prev, tape, macro, legacy_quad)
    forward = _forward_read(full_regime, base_effect, data_dir)
    fused = _fused_risk(tape, macro, legacy_quad, flip, base_conf)

    out = {
        "schema": SCHEMA,
        "asof": str(asof.date()),
        "legacy_quad": legacy_quad,
        "legacy_quad_name": QUAD_NAMES.get(legacy_quad, legacy_quad),
        "label_quad": flip["label_quad"],       # frozen at prior if renorm-vetoed
        "label_quad_name": QUAD_NAMES.get(flip["label_quad"], flip["label_quad"]),
        "degraded": flip["degraded"],
        "tape": tape,
        "macro": macro,
        "forward": forward,
        "fused_risk": fused,
        "flip_attribution": flip,
        "freshness_bitmask": freshness_bitmask(macro, flip["degraded"]),
        "_legacy_quad": legacy_quad,            # for the next run's flip attribution
        "gross_mapping_version": RISK_STATE_GROSS_VERSION,
        "shadow": True,
        "note": "SHADOW artifact — publishes alongside the legacy regime; zero behavioral "
                "change to any current consumer this wave (P2-A). Risk-vocabulary "
                "unification + MRS retirement is the next wave (P2-B').",
    }
    if flip["degraded"]:
        out["degraded_reason"] = flip.get("degraded_reason")
    return out


def accrue_hmm_row(data_dir=None) -> bool:
    """Append today's causal-filtered modal-quad forward call to
    data/regime/regime_fwd_hmm.jsonl (idempotent per session). The call is graded at
    +21bd by scripts/validate_regime_fwd.py. Lives here (not in the script) so the
    engine never imports the scripts package. Returns True if a row was appended."""
    import json
    if data_dir is None:
        data_dir = config.data_dir()
    hist_p = data_dir / "regime" / "regime_history.parquet"
    if not hist_p.exists():
        return False
    try:
        hist = pd.read_parquet(hist_p)
        hist.index = pd.to_datetime(hist.index)
        pq = _causal_filtered_pquad(hist.sort_index())
    except Exception as e:  # noqa: BLE001
        log.warning("regime_one: HMM accrual fit failed: %s", e)
        return False
    if pq is None:
        return False
    p = data_dir / "regime" / "regime_fwd_hmm.jsonl"
    today = pq["asof"]
    last = None
    if p.exists():
        lines = p.read_text().splitlines()
        if lines:
            try:
                last = json.loads(lines[-1]).get("asof")
            except Exception:  # noqa: BLE001
                last = None
    if last == today:
        return False
    with open(p, "a") as fh:
        fh.write(json.dumps({"asof": today, "pred_modal_quad": pq["modal_quad"],
                             "p_quad_filtered": pq["regime_probs_filtered"],
                             "realized_quad_at_21d": None}, default=str) + "\n")
    return True


def build_release_axis_row(pit_as_of=None) -> pd.Series | None:
    """Helper: score the growth+inflation axes on the LEAK-FREE release frame and return
    the last row (with c_ leg columns). Isolated so run.py can fail-isolate it. Runs the
    SAME axis math via engine.inputs.build_features(pit_basis='release')."""
    try:
        from engine.inputs import build_features
        rf = build_features(pit_basis="release", pit_as_of=pit_as_of)
        gx = score_axis(rf, "growth")
        ix = score_axis(rf, "inflation")
        both = pd.concat([gx, ix], axis=1)
        return both.iloc[-1]
    except Exception as e:  # noqa: BLE001
        log.error("regime_one: release-axis build failed: %s", e)
        return None


def main() -> int:  # pragma: no cover — manual inspection
    import json
    from engine.inputs import build_features
    from engine.regime import classify
    f = build_features()
    reg = classify(f)
    rel = build_release_axis_row()
    try:
        from engine import base_effect as _be
        bex = _be.compute()
    except Exception:
        bex = None
    out = compute(reg, rel, bex, {}, prev=None)
    trimmed = {k: v for k, v in out.items()}
    # drop the long histories for console
    trimmed["forward"]["p_quad"].pop("history_filtered", None)
    print(json.dumps(trimmed, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
