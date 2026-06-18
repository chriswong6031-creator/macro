"""Policy-layer scorecard — unify the layer's accountability data into one scannable
read, and surface the SHARPEST DIVERGENCE (a TARGETED theme the rotation map asserts is
policy-favored but that is actually lagging worst vs SPY).

Pure + defensive; never raises. Display-only synthesis of already-computed structures
(prediction counts, rotation realized-check, Fed-stance streak, intel dating)."""
from __future__ import annotations


def summarize(counts: dict | None, rot: dict | None, fed_hist: dict | None,
              dates: dict | None) -> dict:
    counts = counts or {}
    themes = (rot or {}).get("themes") or {}

    verdicts = {"working": 0, "lagging": 0, "mixed": 0, "na": 0}
    sharp = None   # most-negative avg_rel among LAGGING targeted themes
    for theme, v in themes.items():
        verdicts[v.get("verdict", "na")] = verdicts.get(v.get("verdict", "na"), 0) + 1
        if v.get("verdict") == "lagging" and v.get("avg_rel") is not None:
            if sharp is None or v["avg_rel"] < sharp["rel"]:
                sharp = {"theme": theme, "rel": v["avg_rel"]}

    resolved = (counts.get("hit") or 0) + (counts.get("miss") or 0)
    preds = {
        "total": counts.get("total") or 0,
        "open": counts.get("open") or 0,
        "resolved": resolved,
        "hit_rate": counts.get("hit_rate"),
        "overdue": (dates or {}).get("overdue_predictions") or 0,
    }

    stance = None
    if fed_hist and fed_hist.get("current"):
        stance = {"current": fed_hist["current"], "days": fed_hist.get("days_in_stance"),
                  "changed_recently": bool(fed_hist.get("changed_recently"))}

    st = (dates or {}).get("staleness") or {}
    return {
        "predictions": preds,
        "rotation": {**verdicts, "sharpest_divergence": sharp},
        "stance": stance,
        "intel": {"age_days": st.get("age_days"), "stale": bool(st.get("stale"))},
    }
