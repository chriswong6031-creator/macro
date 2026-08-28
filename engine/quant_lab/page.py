"""Quant Lab page payload — a cheap assembler, deliberately.

RENDER BUDGET: the expensive half (the point-in-time study — 12 rebalances, each rebuilding
the whole leg cross-section) runs OFF the render path in `scripts/build_quant_lab.py` and
lands in `data/quant_lab/study.json`. This module only reads that artifact and computes the
ONE live cross-section, which is a couple of seconds. If the study artifact is missing the
page still renders and says so; it never recomputes it inline.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine.quant_lab import legs as legs_mod
from engine.quant_lab import score as score_mod
from engine.quant_lab import specs as specs_mod
from lib import config

log = logging.getLogger(__name__)

STUDY_PATH = ("quant_lab", "study.json")
BOARD_N = 15                    # names shown on the live board

# Models that get a live board. QVO is excluded on purpose: its fund-sentiment leg is
# graded `absent` at 1.3% coverage, and a board built without it would be a QV board
# wearing a QVO label.
BOARD_MODELS = ("fintel_qv", "quant_investing_qvm")


def _live_coverage() -> dict:
    """Live fundamentals-panel coverage: {tickers, leaders_covered} or {} when the
    panel cannot be read.

    The page's coverage chip and its substrate inventory are CURRENT-STATE claims, so
    they must be read, not stamped. They were hardcoded at 1,552/4 and W2-A (#4688)
    widened the panel past 2,800 — which would have left a shipped page asserting a
    filings coverage it no longer has, and naming CMT/KRT as having "no fundamentals at
    all" when both are now covered. Cheap by construction: one column of one parquet
    the render path already reads elsewhere.
    """
    p = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not p.exists():
        return {}
    try:
        tickers = set(pd.read_parquet(p, columns=["ticker"])["ticker"].astype(str))
    except Exception as e:                     # noqa: BLE001 — never kill the page
        log.warning("quant_lab: fundamentals panel unreadable for coverage (%s)", e)
        return {}
    leaders = specs_mod.UNIVERSE_GAP.get("published_leaders") or []
    return {"tickers": len(tickers),
            "leaders_covered": sum(1 for t in leaders if t in tickers)}


def _universe_gap() -> dict:
    """UNIVERSE_GAP with its two current-state fields refreshed from the live panel.
    Falls back to the stamped values when the panel is unreadable; the `*_at_study`
    fields are frozen history and are never overwritten."""
    gap = dict(specs_mod.UNIVERSE_GAP)
    cov = _live_coverage()
    if cov:
        gap["our_fundamentals_universe"] = cov["tickers"]
        gap["published_leaders_in_our_fundamentals_panel"] = cov["leaders_covered"]
    return gap


def _substrate() -> dict:
    """SUBSTRATE with the fundamentals-panel ticker count refreshed from the live panel
    (same current-state reasoning as _universe_gap)."""
    sub = {k: dict(v) for k, v in specs_mod.SUBSTRATE.items()}
    cov = _live_coverage()
    if cov and "edgar_fundamentals_panel" in sub:
        sub["edgar_fundamentals_panel"]["tickers"] = cov["tickers"]
    return sub


def _read_study() -> dict:
    p = config.data_dir().joinpath(*STUDY_PATH)
    if not p.exists():
        log.info("quant_lab: no study artifact at %s — page renders without measurements", p)
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:                     # noqa: BLE001 — a bad artifact must not kill the page
        log.warning("quant_lab: study artifact unreadable (%s)", e)
        return {}


def _fmt(v, nd=4):
    """Round a numeric to `nd` places; None for missing/non-numeric AND for NaN or
    +-inf. `isinstance(float("nan"), float)` is True, so the previous guard let a
    non-finite float straight through to the template (bare `nan` on the model
    board). A legitimate 0 is preserved, never treated as missing."""
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return round(f, nd)


def _live_board(model_key: str, L: pd.DataFrame, mktcap: pd.Series | None) -> dict | None:
    """Top names under a model's recreated score, with the per-leg decomposition Fintel
    prints AND the leg count, so a thinly-evaluated name cannot pass as a fully-judged one."""
    spec = specs_mod.MODELS[model_key]
    keys = [x["key"] for x in spec["legs"] if x["key"] in L.columns]
    keys = [k for k in keys if L[k].notna().sum() >= 30]
    if len(keys) < 2:
        return None
    c = score_mod.composite(L[keys])
    s = c["score"].dropna()
    if s.empty:
        return None
    top = s.nlargest(BOARD_N)
    rows = []
    for t in top.index:
        rows.append({
            "ticker": t,
            "score": _fmt(top[t], 1),
            "n_legs": int(c["n_legs_used"].get(t, 0)),
            "legs": {k: _fmt(c["leg_pct"][k].get(t), 1) for k in keys},
            "mktcap_bn": _fmt((mktcap.get(t) / 1e9) if mktcap is not None and t in mktcap.index else None, 2),
        })
    return {
        "model": model_key, "rule": c["rule"], "leg_keys": keys,
        "min_legs": c["min_legs"], "n_legs_total": len(keys),
        "n_scored": c["n_scored"], "n_universe": c["n_universe"],
        "rows": rows,
    }


METHODS_DIR = ("quant_lab", "methods")


def _read_method_result(filename: str) -> dict:
    """One method's measured result. A missing/bad artifact yields {} — the card still
    renders and says the measurement is unavailable, rather than the page dying or, worse,
    the spec's prose implying a measurement that is not there."""
    p = config.data_dir().joinpath(*METHODS_DIR, filename)
    if not p.exists():
        log.info("quant_lab: no method result at %s — card renders without measurements", p)
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:                     # noqa: BLE001
        log.warning("quant_lab: method result %s unreadable (%s)", filename, e)
        return {}


def _methods() -> list[dict]:
    """External methods that are not per-name rankers (see specs.METHODS).

    The spec supplies the CLAIM and the reasoning; the artifact supplies every NUMBER. They
    are kept apart on purpose so a stale hand-typed statistic cannot outlive its recompute.
    """
    out = []
    for key, spec in specs_mod.METHODS.items():
        res = _read_method_result(spec["result_artifact"])
        out.append({
            "key": key,
            "name": spec["name"], "name_zh": spec.get("name_zh"),
            "proposer": spec["proposer"], "source_kind": spec["source_kind"],
            "one_line": spec["one_line"], "shape": spec["shape"],
            "proposal_says": spec["proposal_says"],
            "proposal_says_zh": spec.get("proposal_says_zh"),
            "not_a_ranker_because": spec["not_a_ranker_because"],
            "our_test": spec["our_test"],
            "house_rulings": spec["house_rulings"],
            "still_live": spec["still_live"],
            "reopen_when": spec["reopen_when"],
            "harness": spec["harness"], "gate_module": spec["gate_module"],
            "provenance": [specs_mod.SOURCES[s] | {"key": s} for s in spec["provenance"]
                           if s in specs_mod.SOURCES],
            "result": res,
            "has_result": bool(res),
        })
    return out


def build_payload() -> dict:
    """Everything the template needs. Never raises — a missing input degrades a section."""
    study = _read_study()
    live, boards, divergence = {}, {}, None
    try:
        r = legs_mod.compute_legs()
        L, mcap = r["legs"], r.get("mktcap")
        live = {"asof": r["asof"], "n_universe": r["n_universe"],
                "coverage": r["coverage"], "years": r.get("years"),
                "tax_rate": r.get("tax_rate")}
        for mk in BOARD_MODELS:
            b = _live_board(mk, L, mcap)
            if b:
                boards[mk] = b
        qv_keys = [x["key"] for x in specs_mod.MODELS["fintel_qv"]["legs"] if x["key"] in L.columns]
        if len(qv_keys) >= 2:
            divergence = score_mod.rule_divergence(L[qv_keys])
    except Exception as e:                     # noqa: BLE001 — additive; the page still renders
        log.warning("quant_lab: live cross-section failed (%s)", e)

    models = []
    for key, spec in specs_mod.MODELS.items():
        fid = specs_mod.leg_fidelity_summary(key)
        st = (study.get("models") or {}).get(key) or {}
        models.append({
            "key": key,
            "name": spec["name"], "name_zh": spec.get("name_zh"),
            "vendor": spec["vendor"], "family": spec["family"],
            "one_line": spec["one_line"], "vendor_says": spec["vendor_says"],
            "disclosure": spec["disclosure"], "disclosure_note": spec["disclosure_note"],
            "legs": spec["legs"], "combination": spec["combination"],
            "vendor_claims": spec["vendor_claims"],
            "provenance": [specs_mod.SOURCES[s] | {"key": s} for s in spec["provenance"]
                           if s in specs_mod.SOURCES],
            "fidelity": fid,
            # The default heuristic reads "most legs are absent" as "we cannot rebuild this",
            # which is right for a vendor model we are reconstructing and wrong for one of
            # ours that ships every night with a documented list of things it deliberately
            # does not compute. A spec may therefore declare its own answer.
            "buildable": spec.get(
                "buildable", fid["faithful"] + fid["proxy"] >= max(2, fid["n_legs"] - 1)),
            "study": st,
            "board": boards.get(key),
        })

    return {
        "models": models,
        "methods": _methods(),
        "live": live,
        "study_meta": {k: v for k, v in study.items() if k != "models"},
        "has_study": bool(study.get("models")),
        "divergence": divergence,
        "substrate": _substrate(),
        "universe_gap": _universe_gap(),
        "rule_fit": score_mod.fit_observed_weights(),
        "observed": specs_mod.FINTEL_OBSERVED_SCORES,
        "observed_source": specs_mod.SOURCES[specs_mod.FINTEL_OBSERVED_SOURCE],
        "amr": specs_mod.FINTEL_AMR_READOUT,
        "sources": specs_mod.SOURCES,
    }
