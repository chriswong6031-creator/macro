"""Falsifiable SIGNAL TRACK-RECORD for the Intelligence Hub — measure, don't assert.

The hub ranks by an opportunity score and labels names by lifecycle stage. Those are
CLAIMS about the future. This harness records them daily and, once a horizon elapses,
grades them against realized forward relative returns — so the page can show whether the
edge is REAL, and so an unproven signal can be flagged rather than trusted.

Generalizes engine/radar_ic.py from a single edge_score to the hub's leading signals:

  1. snapshot(track_rows, today)  — append today's per-name {opportunity, edge_remaining,
     stage, lean} to data/hub/signal_snapshots.jsonl. Idempotent by (date, ticker).

  2. compute(today)               — for EACH horizon (5/10/21/63d), mature the snapshots
     that are old enough AND price-covered, compute forward SPY-relative returns, then:
       • opportunity / edge_remaining IC  — pooled Spearman + per-date cross-sectional ICs
         summarized with a Newey-West HAC t-stat (engine.validation.ic_summary).
       • by-stage mean forward return + hit-rate — the headline test: do 'emerging' names
         actually outperform, and do 'exhausted' ones underperform?
     The horizon whose opportunity-IC peaks is the signal's measured LEAD-TIME.

  3. a signal is "proven" only when matured n is sufficient AND the HAC-t is significant
     with the expected sign — until then it is "measuring" (may flag, must not be trusted).

Reuses engine.validation primitives + the ai_desk price layer. CONTEXT-ONLY ·
DEGRADE-NEVER-RAISE — no matured data ⇒ a valid 'accruing' payload, never an exception.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from engine.ai_desk import _level_asof              # price helpers — do NOT reinvent
from engine.ai_desk_scorer import _close_at, _covers
from engine import validation as V
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "intel_hub.track_record.v1"
_SNAP = ("data", "hub", "signal_snapshots.jsonl")
_HORIZONS = (5, 10, 21, 63)
_BENCH = "SPY"
_BULLISH_STAGES = {"emerging", "early"}
_BEARISH_STAGES = {"exhausted", "distribution"}
_MIN_PROVEN_N = 40           # matured obs before a signal can be called "proven"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(root: Path) -> Path:
    return root.joinpath(*_SNAP)


def _load(root: Path) -> list[dict]:
    p = _path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------- #
# snapshot accrual
# --------------------------------------------------------------------------- #
def snapshot(track_rows: list | None, today: date | str | None = None,
             root: Path | None = None, regime: str | None = None) -> int:
    """Append today's per-name signal readings. Idempotent by (date, ticker). Never raises.
    ``regime`` (the day's macro quadrant, e.g. Q1-Q4) is stamped on each row so a signal that
    only leads in one regime can be measured per-regime and cannot hide behind a blended IC."""
    try:
        root = Path(root) if root else config.ROOT
        today_str = today.isoformat() if hasattr(today, "isoformat") else str(today or date.today())
        existing = {f"{r.get('date')}|{r.get('t')}" for r in _load(root)}
        new = []
        for r in (track_rows or []):
            t = (r.get("t") or "").upper()
            if not t or f"{today_str}|{t}" in existing:
                continue
            row = {"date": today_str, "t": t, "opp": r.get("opp"),
                   "edge": r.get("edge"), "stage": r.get("stage"), "lean": r.get("lean")}
            if r.get("engine_version"):        # additive era-stamp — old rows stay valid without it
                row["engine_version"] = r.get("engine_version")
            if r.get("source"):                # discovery feed (insider_cluster/activist/…) → per-source IC
                row["source"] = r.get("source")
            if regime:                         # macro quadrant of the snapshot day → by_regime IC
                row["regime"] = regime
            new.append(row)
            existing.add(f"{today_str}|{t}")
        if not new:
            return 0
        p = _path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for r in new:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        return len(new)
    except Exception as e:  # noqa: BLE001
        log.warning("hub track snapshot failed: %s", e)
        return 0


# --------------------------------------------------------------------------- #
# maturation + forward returns
# --------------------------------------------------------------------------- #
def _fwd_rel(ticker: str, root: Path, start: str, horizon_d: int) -> float | None:
    try:
        end = (pd.Timestamp(start) + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        e0, e1 = _level_asof(ticker, root, start), _close_at(ticker, root, end)
        b0, b1 = _level_asof(_BENCH, root, start), _close_at(_BENCH, root, end)
        if None in (e0, e1, b0, b1) or not e0 or not b0:
            return None
        return float((e1 / e0 - 1.0) - (b1 / b0 - 1.0))
    except Exception:  # noqa: BLE001
        return None


def _matured(rows: list, root: Path, horizon_d: int, today: date,
             fwd_rel_fn=None) -> list[dict]:
    """Rows old enough AND price-covered, tagged with forward rel-return. ``fwd_rel_fn`` lets a
    non-US region inject its own price/benchmark layer as ``fn(ticker, start_date, horizon_d) ->
    rel_return | None`` (None ⇒ not covered/matured; it folds in coverage). Default = the US
    SPY-relative path, byte-for-byte unchanged."""
    out = []
    for r in rows:
        try:
            if (pd.Timestamp(today) - pd.Timestamp(r["date"])).days < horizon_d:
                continue
            if fwd_rel_fn is not None:
                fwd = fwd_rel_fn(r["t"], r["date"], horizon_d)
            else:
                end = (pd.Timestamp(r["date"]) + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
                if not (_covers(r["t"], root, end) and _covers(_BENCH, root, end)):
                    continue
                fwd = _fwd_rel(r["t"], root, r["date"], horizon_d)
            if fwd is None:
                continue
            out.append({**r, "fwd": fwd})
        except Exception:  # noqa: BLE001
            continue
    return out


def _signed(rows: list, field: str) -> tuple[list, list]:
    """Signal × sign(lean) vs forward return — so a high opportunity on a SHORT lean is
    expected to predict a NEGATIVE forward return. Drops rows missing the field/lean."""
    xs, ys = [], []
    for r in rows:
        v, lean = r.get(field), r.get("lean")
        if v is None or not lean:                 # lean None or 0 ⇒ no directional claim — exclude
            continue
        xs.append(float(v) * (1 if lean > 0 else -1))
        ys.append(r["fwd"])
    return xs, ys


def _pooled_ic(xs: list, ys: list) -> float | None:
    if len(xs) < 10:
        return None
    s = pd.concat([pd.Series(xs).rename("s"), pd.Series(ys).rename("f")], axis=1).dropna()
    if len(s) < 10 or s["s"].nunique() < 2 or s["f"].nunique() < 2:   # need spread for a rank corr
        return None
    return round(float(s["s"].rank().corr(s["f"].rank())), 4)


def _daily_ic(rows: list, field: str, horizon_d: int = 21) -> dict:
    """Per-date cross-sectional ICs → ic_summary (mean IC + HAC t). Needs ≥10 names/date.
    The Newey-West lag is set to the HORIZON: daily snapshots with an h-day forward window
    overlap for ~h days, so the IC series autocorrelates at lag h — a fixed small lag would
    badly under-correct and let noise clear the significance bar at the longer horizons."""
    by_date: dict[str, list] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    ics = []
    for _, day in sorted(by_date.items()):
        xs = [(r.get(field) or 0) * (1 if (r.get("lean") or 0) > 0 else -1) for r in day
              if r.get(field) is not None and r.get("lean")]          # lean truthy ⇒ exclude 0/None
        fwd = [r["fwd"] for r in day if r.get(field) is not None and r.get("lean")]
        if len(xs) < 10 or len(set(xs)) < 2 or len(set(fwd)) < 2:   # need spread, else corr is NaN
            continue
        ic = V.rank_ic(xs, fwd)
        if ic == ic:                                  # not NaN
            ics.append(ic)
    # periods_per_year=2*h ⇒ ic_summary sets the NW lag to h (its lag = periods_per_year//2)
    return V.ic_summary(ics, periods_per_year=2 * horizon_d) if len(ics) >= 6 else {"n_days": len(ics)}


def _by_stage(rows: list) -> dict:
    out: dict[str, dict] = {}
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.get("stage") or "?", []).append(r["fwd"])
    for st, fwds in by.items():
        n = len(fwds)
        mean = sum(fwds) / n if n else 0.0
        # hit = realized return in the EXPECTED direction for the stage
        if st in _BULLISH_STAGES or st == "discovery":
            hit = sum(1 for f in fwds if f > 0) / n if n else None
        elif st in _BEARISH_STAGES:
            hit = sum(1 for f in fwds if f < 0) / n if n else None
        else:
            hit = None
        out[st] = {"n": n, "mean_fwd_rel": round(mean, 4),
                   "hit_rate": round(hit, 3) if hit is not None else None}
    return out


def _by_source(rows: list) -> dict:
    """Forward performance of each DISCOVERY feed (insider_cluster / activist_ownership /
    federal_velocity / radar_quiet). Discovery candidates are bullish-intended (off-desk leading
    accumulation), so a hit is a POSITIVE SPY-relative forward return. This is the evidence a
    display-tier feed needs to EARN a promotion — or to be dropped: 'do this feed's names
    actually outperform?' Only rows carrying a ``source`` participate (on-desk rows are None)."""
    by: dict[str, list] = {}
    for r in rows:
        s = r.get("source")
        if s:
            by.setdefault(s, []).append(r["fwd"])
    out: dict[str, dict] = {}
    for s, fwds in by.items():
        n = len(fwds)
        mean = sum(fwds) / n if n else 0.0
        hit = (sum(1 for f in fwds if f > 0) / n) if n else None
        out[s] = {"n": n, "mean_fwd_rel": round(mean, 4),
                  "hit_rate": round(hit, 3) if hit is not None else None}
    return out


def _by_regime(rows: list) -> dict:
    """Forward performance + opportunity-IC per macro regime (quad Q1-Q4). A signal that only
    leads in one quadrant can't hide behind a blended IC — and, symmetrically, the governor must
    not DEMOTE a signal on evidence drawn from a single regime. This is the per-regime readout the
    regime-aware gate reads once each quadrant has enough matured obs. Only rows carrying a
    ``regime`` stamp participate (older, un-stamped rows are excluded until the stamp accrues)."""
    by: dict[str, list] = {}
    for r in rows:
        rg = r.get("regime")
        if rg:
            by.setdefault(rg, []).append(r)
    out: dict[str, dict] = {}
    for rg, rs in by.items():
        n = len(rs)
        mean = sum(r["fwd"] for r in rs) / n if n else 0.0
        dir_rs = [r for r in rs if r.get("lean")]          # directional rows only (exclude lean 0)
        hit = (sum(1 for r in dir_rs if r["fwd"] * (1 if r["lean"] > 0 else -1) > 0) / len(dir_rs)
               ) if dir_rs else None
        out[rg] = {"n": n, "mean_fwd_rel": round(mean, 4),
                   "hit_rate": round(hit, 3) if hit is not None else None,
                   "opportunity_ic": _pooled_ic(*_signed(rs, "opp"))}
    return out


def compute(today: date | str | None = None, root: Path | None = None,
            horizons=_HORIZONS, *, rows: list | None = None, fwd_rel_fn=None,
            bench: str = _BENCH) -> dict:
    """Grade every matured snapshot across all horizons. Never raises; degrades to 'accruing'.
    Region-parameterized: pass pre-normalized ``rows`` ({date,t,opp,edge,stage,lean}) + a
    ``fwd_rel_fn(ticker, start, horizon_d)`` to grade a non-US hub against its own benchmark
    (e.g. China vs CSI300). Defaults reproduce the US SPY-relative path exactly."""
    try:
        root = Path(root) if root else config.ROOT
        today_dt = pd.Timestamp(today).date() if today else date.today()
        rows = _load(root) if rows is None else rows
        out_h: dict[str, dict] = {}
        peak_ic, lead_time = None, None
        for h in horizons:
            mat = _matured(rows, root, h, today_dt, fwd_rel_fn=fwd_rel_fn)
            opp_daily = _daily_ic(mat, "opp", h)       # rigorous, overlap-robust HAC path
            entry = {
                "n_matured": len(mat),
                # pooled Spearman is provisional/descriptive (pseudo-replicated across dates);
                # the DAILY HAC path is the one the proven gate + lead-time trust.
                "opportunity_ic_pooled": _pooled_ic(*_signed(mat, "opp")),
                "opportunity_ic_daily": opp_daily,
                "opportunity_ic": opp_daily.get("mean_ic"),   # headline = the rigorous mean IC
                "edge_ic_pooled": _pooled_ic(*_signed(mat, "edge")),
                "by_stage": _by_stage(mat),
                "by_source": _by_source(mat),     # per discovery-feed forward performance (promotion evidence)
                "by_regime": _by_regime(mat),     # per-quad IC — the regime-aware gate's readout
            }
            out_h[str(h)] = entry
            # lead-time = the horizon whose per-date HAC IC is significant AND largest (never a
            # single pooled-window artifact)
            t = opp_daily.get("t_hac")
            mic = opp_daily.get("mean_ic")
            if t is not None and t >= 2.0 and mic is not None and mic > 0 and (peak_ic is None or mic > peak_ic):
                peak_ic, lead_time = mic, h

        # a signal is PROVEN only with enough matured obs AND a significant positive HAC-t
        proven = {}
        for h, e in out_h.items():
            d = e.get("opportunity_ic_daily") or {}
            t = d.get("t_hac")
            proven[h] = bool(e["n_matured"] >= _MIN_PROVEN_N and t is not None and t >= 2.0
                             and (e.get("opportunity_ic") or 0) > 0)
        any_matured = any(e["n_matured"] > 0 for e in out_h.values())
        note = ("Measuring — accruing forward observations; the hub's edge is not yet "
                "statistically proven. Early numbers are provisional, context-only."
                if not any(proven.values()) else
                f"Opportunity IC peaks at the {lead_time}d horizon (measured). Context-only.")
        return {
            "schema": SCHEMA, "as_of": today_dt.isoformat(), "generated_at": _now_iso(),
            "is_context_only": True, "n_snapshots": len(rows),
            "horizons": out_h, "lead_time_d": lead_time, "peak_opportunity_ic": peak_ic,
            "proven": proven, "any_matured": any_matured, "note": note, "benchmark": bench,
            "disclaimer": ("An accountable scorecard of the hub's own claims — opportunity rank and "
                           f"lifecycle stage graded against realized {bench}-relative forward returns. "
                           "Until a signal matures and clears a Newey-West significance bar it is "
                           "'measuring', never trusted. Nothing here sizes a position."),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("hub track compute failed: %s", e)
        return {"schema": SCHEMA, "as_of": str(today or date.today()), "generated_at": _now_iso(),
                "is_context_only": True, "n_snapshots": 0, "horizons": {}, "lead_time_d": None,
                "peak_opportunity_ic": None, "proven": {}, "any_matured": False,
                "note": f"compute error ({e}) — accruing, degrade-safe."}
