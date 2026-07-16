"""Falsifiable forward TRACK-RECORD for the index-leadership RUNNING / COILING calls —
measure, don't assert.

The leadership layer surfaces two kinds of CLAIM about the future, per subsector:
  • RUNNING — an already-leading subsector keeps outperforming (momentum continuation).
  • COILING — a lagging subsector turns up and outperforms (a confirmed bottom).
Both are bets that the subsector's members beat SPY over the next few weeks. This harness
logs them daily and, once a horizon elapses, grades them against the realized member-EW
SPY-relative forward return of their FROZEN members — so the page can show whether the
read has ANY edge instead of asserting one.

Mirrors engine.subsector_track_record (Pattern B) with a namespaced store
(data/index_leadership/snapshots.jsonl) and a per-claim-type split (RUNNING vs COILING are
different bets, graded apart). Reuses the SAME price + stats helpers the rest of the desk
uses — engine.ai_desk._level_asof, engine.ai_desk_scorer._close_at/_covers,
engine.validation.rank_ic/ic_summary — so nothing here reinvents a return or a t-stat.

CONTEXT-ONLY · DEGRADE-NEVER-RAISE. No matured data ⇒ a valid 'accruing' payload, never an
exception. Bottom-timing is a drawdown / ordering lever, not return-alpha — nothing here
sizes a position. Members are frozen point-in-time (no survivorship drift); only priceable
members count; a call with too few priceable members is left unscored.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from engine.ai_desk import _level_asof              # price helpers — do NOT reinvent
from engine.ai_desk_scorer import _close_at, _covers
from engine import validation as V
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "index_leadership.track_record.v1"
_SNAP = ("data", "index_leadership", "snapshots.jsonl")
_HORIZONS = (5, 10, 21, 63)
_BENCH = "SPY"
_MIN_PRICED = 3              # a call needs ≥ this many priceable frozen members to be scored
_MIN_PROVEN_N = 40          # matured obs before a claim/horizon can be called "proven"
_STAGES = ("running", "coiling", "coiling_primed")


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
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _calls(payload: dict) -> list[dict]:
    """Flatten the payload's per-tab RUNNING + COILING lists into gradeable call rows
    (id = 'tab:key' — a subsector key can appear in more than one tab)."""
    rows = []
    for tab, t in (payload.get("tabs") or {}).items():
        for e in t.get("rising") or []:
            rows.append({"tab": tab, "key": e.get("key"), "name": e.get("label"),
                         "stage": "running", "score": e.get("emerging_score")})
        for e in t.get("coiling") or []:
            co = e.get("coil") or {}
            st = "coiling_primed" if co.get("stage") == "primed" else "coiling"
            rows.append({"tab": tab, "key": e.get("key"), "name": e.get("label"),
                         "stage": st, "score": (co.get("coil_score") if co else e.get("emerging_score"))})
    return rows


def _nightly_lane() -> bool:
    """COLLECT_LANE gate — house law: nightly is the sole advancer of data/ forward
    ledgers. Same sentinel as engine.basket_turn_watch (daily.yml sets it on the
    engine-lane step); US_LANE accepted as the legacy alias so tests keep working.
    Added when build_index_leadership was wired into the nightly (dead-wire fix
    2026-07-16) so provisional lanes (earlyclose / closing-bell) can never append."""
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


def snapshot(payload: dict, member_map: dict | None = None,
             today: date | str | None = None, root: Path | None = None) -> int:
    """Append today's RUNNING + COILING calls with their FROZEN member baskets. Idempotent
    by (date, id). Never raises. `member_map` = {'tab:key': [tickers]}."""
    try:
        if not _nightly_lane():
            log.info("index_leadership track: COLLECT_LANE != nightly — snapshot append skipped")
            return 0
        root = Path(root) if root else config.ROOT
        member_map = member_map or {}
        today_str = today.isoformat() if hasattr(today, "isoformat") else str(today or date.today())
        existing = {f"{r.get('date')}|{r.get('id')}" for r in _load(root)}
        new = []
        for c in _calls(payload):
            cid = f"{c['tab']}:{c['key']}"
            if not c["key"] or f"{today_str}|{cid}" in existing:
                continue
            members = [str(t).strip().upper() for t in (member_map.get(cid) or []) if str(t).strip()]
            new.append({"date": today_str, "id": cid, "tab": c["tab"], "key": c["key"],
                        "name": c["name"], "stage": c["stage"], "score": c["score"],
                        "lean": 1, "members": members})
            existing.add(f"{today_str}|{cid}")
        if not new:
            return 0
        p = _path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for r in new:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        return len(new)
    except Exception as e:  # noqa: BLE001
        log.warning("index_leadership track snapshot failed: %s", e)
        return 0


# --------------------------------------------------- maturation + forward returns ----

def _member_ret(ticker: str, root: Path, start: str, end: str) -> float | None:
    p0, p1 = _level_asof(ticker, root, start), _close_at(ticker, root, end)
    if p0 in (None, 0) or p1 is None:
        return None
    return float(p1 / p0 - 1.0)


def _fwd_basket(members: list, root: Path, start: str, horizon_d: int) -> float | None:
    """Equal-weight mean forward return of the frozen priceable members, minus SPY."""
    try:
        end = (pd.Timestamp(start) + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        rets = [r for t in (members or []) if (r := _member_ret(t, root, start, end)) is not None]
        if len(rets) < _MIN_PRICED:
            return None
        b0, b1 = _level_asof(_BENCH, root, start), _close_at(_BENCH, root, end)
        if b0 in (None, 0) or b1 is None:
            return None
        return float(sum(rets) / len(rets) - (b1 / b0 - 1.0))
    except Exception:  # noqa: BLE001
        return None


def _matured(rows: list, root: Path, horizon_d: int, today: date) -> list[dict]:
    out = []
    for r in rows:
        try:
            if (pd.Timestamp(today) - pd.Timestamp(r["date"])).days < horizon_d:
                continue
            end = (pd.Timestamp(r["date"]) + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
            if not _covers(_BENCH, root, end):
                continue
            fwd = _fwd_basket(r.get("members"), root, r["date"], horizon_d)
            if fwd is None:
                continue
            out.append({**r, "fwd": fwd})
        except Exception:  # noqa: BLE001
            continue
    return out


def _ic(rows: list, horizon_d: int) -> dict:
    """Per-date cross-sectional IC of the call score vs forward return → HAC summary.
    Newey-West lag = the horizon (overlapping windows autocorrelate at lag h)."""
    by_date: dict[str, list] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    ics = []
    for _, day in sorted(by_date.items()):
        xs = [r.get("score") for r in day if r.get("score") is not None]
        fwd = [r["fwd"] for r in day if r.get("score") is not None]
        if len(xs) < 8 or len(set(xs)) < 2 or len(set(fwd)) < 2:
            continue
        ic = V.rank_ic(xs, fwd)
        if ic == ic:  # not NaN
            ics.append(ic)
    return V.ic_summary(ics, periods_per_year=2 * horizon_d) if len(ics) >= 6 else {"n_days": len(ics)}


def _by_stage(rows: list) -> dict:
    """Per-claim hit-rate + mean forward return. RUNNING and COILING are both BULLISH
    claims (members beat SPY), so a 'hit' is fwd_rel > 0 for every stage."""
    out: dict[str, dict] = {}
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.get("stage") or "?", []).append(r["fwd"])
    for st, fwds in by.items():
        n = len(fwds)
        mean = sum(fwds) / n if n else 0.0
        hit = sum(1 for f in fwds if f > 0) / n if n else None
        out[st] = {"n": n, "mean_fwd_rel": round(mean, 4),
                   "hit_rate": round(hit, 3) if hit is not None else None}
    return out


def _recent_misses(rows: list, horizon_d: int, k: int = 8) -> list[dict]:
    """ERROR LEDGER: bullish calls FALSIFIED (member basket UNDERperformed SPY), newest first."""
    miss = [r for r in rows if r.get("fwd") is not None and r["fwd"] < 0]
    miss.sort(key=lambda r: (r["date"], abs(r["fwd"])), reverse=True)
    return [{"date": r["date"], "id": r["id"], "name": r.get("name"), "stage": r.get("stage"),
             "fwd_rel": round(r["fwd"], 4), "horizon_d": horizon_d} for r in miss[:k]]


def compute(today: date | str | None = None, root: Path | None = None,
            horizons=_HORIZONS) -> dict:
    """Grade every matured snapshot across all horizons. Never raises; degrades to 'accruing'."""
    try:
        root = Path(root) if root else config.ROOT
        today_dt = pd.Timestamp(today).date() if today else date.today()
        rows = _load(root)
        n_days = len({r.get("date") for r in rows})
        out_h: dict[str, dict] = {}
        peak_ic, lead_time, misses = None, None, []
        for h in horizons:
            mat = _matured(rows, root, h, today_dt)
            run = [r for r in mat if r.get("stage") == "running"]
            coil = [r for r in mat if r.get("stage") in ("coiling", "coiling_primed")]
            run_ic, coil_ic = _ic(run, h), _ic(coil, h)
            out_h[str(h)] = {
                "n_matured": len(mat),
                "by_stage": _by_stage(mat),
                "running_ic": run_ic.get("mean_ic"), "running_ic_t_hac": run_ic.get("t_hac"),
                "coiling_ic": coil_ic.get("mean_ic"), "coiling_ic_t_hac": coil_ic.get("t_hac"),
            }
            for grp, icd in (("run", run_ic), ("coil", coil_ic)):
                t, mic = icd.get("t_hac"), icd.get("mean_ic")
                if t is not None and t >= 2.0 and mic and mic > 0 and (peak_ic is None or mic > peak_ic):
                    peak_ic, lead_time = mic, h
            if h == 21:
                misses = _recent_misses(mat, h)

        proven = {}
        for h, e in out_h.items():
            n_ok = e["n_matured"] >= _MIN_PROVEN_N
            rt, ct = e.get("running_ic_t_hac"), e.get("coiling_ic_t_hac")
            proven[h] = bool(n_ok and (((rt or 0) >= 2.0 and (e.get("running_ic") or 0) > 0)
                                       or ((ct or 0) >= 2.0 and (e.get("coiling_ic") or 0) > 0)))
        any_matured = any(e["n_matured"] > 0 for e in out_h.values())
        if not any_matured:
            verdict, note = "accruing", ("Measuring — logging RUNNING / COILING calls daily; no "
                                         "horizon has matured yet. The forward edge is unmeasured. Context-only.")
        elif any(proven.values()):
            verdict, note = "validated", (f"Call-score IC is significant at the {lead_time}d horizon "
                                          "(measured). Context-only — informs the read, never sizes.")
        else:
            verdict, note = "measuring", ("Accruing forward observations; no horizon clears the "
                                          "Newey-West significance bar yet. Early numbers are provisional, context-only.")
        return {
            "schema": SCHEMA, "as_of": today_dt.isoformat(), "generated_at": _now_iso(),
            "is_context_only": True, "n_snapshots": len(rows), "n_days": n_days,
            "horizons": out_h, "lead_time_d": lead_time, "peak_ic": peak_ic,
            "proven": proven, "any_matured": any_matured, "verdict": verdict, "note": note,
            "recent_misses": misses,
            "disclaimer": ("A falsifiable scorecard of the leadership read's OWN calls — RUNNING "
                           "(momentum continuation) and COILING (confirmed bottom) — graded against "
                           "realized member-equal-weight SPY-relative forward returns. Until a horizon "
                           "matures and clears a Newey-West significance bar it is 'measuring', never "
                           "trusted. Members frozen point-in-time; only priceable members used. Nothing "
                           "here sizes a position."),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("index_leadership track compute failed: %s", e)
        return {"schema": SCHEMA, "as_of": str(today or date.today()), "generated_at": _now_iso(),
                "is_context_only": True, "n_snapshots": 0, "n_days": 0, "horizons": {},
                "lead_time_d": None, "peak_ic": None, "proven": {}, "any_matured": False,
                "verdict": "accruing", "note": f"compute error ({e}) — accruing, degrade-safe.",
                "recent_misses": []}
