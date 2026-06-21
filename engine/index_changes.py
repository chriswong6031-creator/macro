"""S&P index-change CONTEXT — fresh constituent ADDITIONS as a dated catalyst the five
desks don't track, with the honest decomposition that keeps it from being a folklore trap.

The announcement→effective [-5,0] run-up for S&P additions is REAL and recent (validated in
scripts/validate_index_reconstitution.py: pure-add +1.6% gross, t=4.6; recent +2.0%, t=5.8),
BUT (Vijh-Wang 2022) it lives ENTIRELY in PURE / net-new additions — a name entering from
OUTSIDE the S&P universe, with no offsetting forced index seller. MIGRATIONS (400→500) and
M&A-replacement adds have a forced seller and ~no edge. AND net of small-cap transaction cost
the TYPICAL pure add LOSES (sp600 net median < 0, hit < 50%) — a net-of-cost mirage whose
residual net edge sits only in the announcement-overnight gap (needs intraday opens to trade).

So this is DISPLAY-ONLY CONTEXT: surface freshly-announced PURE additions (effective date still
ahead or just past) as a fresh, dated, leading catalyst — never a scored sizer. The scoring gate
(announce_net_scored) stays closed; the leg flips on only if intraday validation ever earns it.
PURE compute; disk IO isolated.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "index_changes.v1"
_RECENT_DAYS = 10              # an addition effective within the last ~2 trading weeks is still fresh
_UPCOMING_DAYS = 21           # …or scheduled within the next few weeks (quarterly batch lead ~10d)


def pit_history() -> dict:
    """{ticker: PIT membership rows} for cohort classification (empty dict if unavailable)."""
    try:
        p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
        if not p.exists():
            return {}
        pit = pd.read_parquet(p)
        pit["sd"] = pd.to_datetime(pit["start_date"], errors="coerce")
        pit["ed"] = pd.to_datetime(pit["end_date"], errors="coerce")
        pit["ticker"] = pit["ticker"].astype(str).str.upper()
        return {t: g for t, g in pit.groupby("ticker")}
    except Exception as e:  # noqa: BLE001
        log.debug("pit_history read failed (%s)", e)
        return {}


def classify_cohort(ticker: str, eff_date, index: str, pit_by_t: dict) -> str:
    """An S&P ADD is 'pure'/net-new (entering from OUTSIDE the S&P universe — no offsetting
    forced index seller → the real run-up), 'migration' (active in a DIFFERENT S&P index just
    before, e.g. 400→500 — has a forced seller, ~no edge), or 'readd' (was previously in THIS
    index). PURE is the only cohort that carries the announcement run-up. PURE."""
    g = pit_by_t.get(str(ticker).upper())
    if g is None or getattr(g, "empty", True):
        return "pure"
    try:
        d = pd.to_datetime(eff_date)
    except Exception:  # noqa: BLE001
        return "pure"
    prior = g[g["sd"] < (d - pd.Timedelta(days=5))]
    if prior.empty:
        return "pure"
    near = prior[(prior["src"] != index)
                 & ((prior["ed"].isna()) | (prior["ed"] >= d - pd.Timedelta(days=10)))]
    if not near.empty:
        return "migration"
    return "readd" if not prior[prior["src"] == index].empty else "pure"


def load_gate() -> dict:
    """The index-reconstitution validation gate (announce_gross_scored / announce_net_scored)."""
    try:
        import json
        p = config.data_dir() / "index_reconstitution" / "validation_gate.json"
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


_INDEX_LABEL = {"sp500": "S&P 500", "sp400": "S&P MidCap 400", "sp600": "S&P SmallCap 600"}


def build_snapshot(today: date | None = None, changes=None) -> dict:
    """Context payload: freshly-announced S&P ADDITIONS (pure cohort highlighted), upcoming +
    recent, with the gross/net honesty from the gate. CONTEXT-ONLY, never scored. PURE-ish."""
    today = today or date.today()
    if changes is None:
        from collectors.sp_index_changes import load_changes
        changes = load_changes()
    gate = load_gate()
    net_scored = bool(gate.get("announce_net_scored"))
    gross_scored = bool(gate.get("announce_gross_scored"))
    tiers = gate.get("announce_tiers") or {}

    out_pure, out_other = [], []
    if changes is not None and not getattr(changes, "empty", True):
        adds = changes[changes["action"] == "addition"].copy()
        pit = pit_history()
        td = pd.Timestamp(today)
        for r in adds.itertuples(index=False):
            eff = pd.to_datetime(getattr(r, "effective_date", None), errors="coerce")
            if pd.isna(eff):
                continue
            dte = int((eff - td).days)                      # >0 ahead, <0 already effective
            if dte < -_RECENT_DAYS or dte > _UPCOMING_DAYS:  # not fresh
                continue
            cohort = classify_cohort(r.ticker, eff, r.index, pit)
            rec = {
                "ticker": str(r.ticker).upper(), "index": r.index,
                "index_label": _INDEX_LABEL.get(r.index, r.index),
                "effective_date": str(eff.date()), "days_to_effective": dte,
                "announce_date": getattr(r, "announce_date", None),
                "company": getattr(r, "company", None), "cohort": cohort,
                "run_up_window_open": bool(-_RECENT_DAYS <= dte <= 5),  # within [-5,0]-ish of effective
                "edge_tier": bool(tiers.get(r.index)),       # does this index carry the gross run-up
            }
            (out_pure if cohort == "pure" else out_other).append(rec)
    out_pure.sort(key=lambda d: d["days_to_effective"])
    out_other.sort(key=lambda d: d["days_to_effective"])

    return {
        "schema": SCHEMA, "is_context_only": True, "scored": False,
        "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pure_additions": out_pure, "other_additions": out_other,
        "n_pure": len(out_pure), "n_other": len(out_other),
        "gate": {"gross_scored": gross_scored, "net_scored": net_scored,
                 "note": gate.get("note")},
        "disclaimer": (
            "Freshly-announced S&P index ADDITIONS. The pre-effective run-up is real GROSS for "
            "PURE/net-new adds, but net of small-cap costs the typical name is flat-to-negative "
            "(a net-of-cost mirage) — so this is CONTEXT, never a scored buy. Migrations/M&A-"
            "replacements (other_additions) have a forced seller and no edge."),
    }
