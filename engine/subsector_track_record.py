"""Falsifiable forward TRACK-RECORD for the Subsector Rotation read — measure, don't assert.

The rotation engine ranks 268 subsectors by ``emerging_score`` and labels each
emerging / fading / neutral. Those are CLAIMS about the future. This harness
records them daily and, once a horizon elapses, grades them against realized
forward returns — so the page can show whether the read has ANY edge, and so an
unproven signal is flagged rather than trusted.

Structure mirrors engine.hub_track_record (Pattern B) with one real change: a
subsector has no price series, so its forward return is the **equal-weight mean
forward return of its FROZEN member tickers**, SPY-relative. Members are frozen
at snapshot time (no survivorship drift); only members we actually hold prices
for are used, and a subsector with too few priceable members is left unscored.

  1. snapshot(subsectors, member_map, today) — append today's per-subsector
     {date, key, score, stage, lean, members} to data/subsector_rotation/
     snapshots.jsonl. Idempotent by (date, key).
  2. compute(today) — for each horizon (5/10/21/63d) mature the snapshots old
     enough AND price-covered, compute member-EW SPY-relative forward returns,
     then: by-stage hit-rate (do 'emerging' subsectors outperform & 'fading'
     underperform?) + cross-sectional emerging_score IC (Newey-West HAC t) + an
     ERROR LEDGER of recently falsified calls.
  3. "proven" only with enough matured obs AND a significant positive HAC-t.

CONTEXT-ONLY · DEGRADE-NEVER-RAISE — no matured data ⇒ a valid 'accruing'
payload, never an exception. Nothing here sizes a position.
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

SCHEMA = "subsector_rotation.track_record.v1"
_SNAP = ("data", "subsector_rotation", "snapshots.jsonl")
_HORIZONS = (5, 10, 21, 63)
_BENCH = "SPY"
_MIN_PRICED = 3              # a subsector needs ≥ this many priceable members to be scored
_MIN_PROVEN_N = 40          # matured obs before a horizon can be called "proven"


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
def _stage_lean(s: dict, emerging: set, fading: set) -> tuple[str, int]:
    k = s.get("key")
    if k in emerging:
        return "emerging", 1
    if k in fading:
        return "fading", -1
    return "neutral", 0


# Turn states that are directional CLAIMS, mapped onto the incumbent stage vocabulary so
# both reads are graded by exactly the same rule (hit = emerging up / fading down).
_V2_STAGE = {"turn_up": "emerging", "bottoming": "emerging",
             "turn_down": "fading", "topping": "fading"}


def _stage_v2(s: dict) -> str | None:
    """The turn engine's stage for this row, or None when the turn read is absent."""
    st = s.get("turn_state")
    if not st:
        return None
    return _V2_STAGE.get(st, "neutral")


def snapshot(payload: dict, member_map: dict | None = None,
             today: date | str | None = None, root: Path | None = None) -> int:
    """Append today's per-subsector reading. Idempotent by (date, key). Never raises."""
    try:
        root = Path(root) if root else config.ROOT
        member_map = member_map or {}
        today_str = today.isoformat() if hasattr(today, "isoformat") else str(today or date.today())
        existing = {f"{r.get('date')}|{r.get('key')}" for r in _load(root)}
        emerging = set((payload.get("highlights") or {}).get("emerging") or [])
        fading = set((payload.get("highlights") or {}).get("fading") or [])
        new = []
        for s in payload.get("subsectors", []):
            k = s.get("key")
            if not k or f"{today_str}|{k}" in existing:
                continue
            stage, lean = _stage_lean(s, emerging, fading)
            members = [str(t).strip().upper() for t in (member_map.get(k) or []) if str(t).strip()]
            new.append({"date": today_str, "key": k, "name": s.get("name"),
                        "theme": s.get("theme"), "score": s.get("emerging_score"),
                        "rs_mom": s.get("rs_mom"), "accel": s.get("accel"),
                        "quadrant": s.get("quadrant"), "stage": stage, "lean": lean,
                        # HEAD-TO-HEAD (engine/subsector_turn.py): the turn engine's own
                        # rank and stage, logged beside the incumbent so the ledger — not an
                        # argument about which arithmetic is nicer — decides which read is
                        # better. Absent on rows logged before the turn engine shipped;
                        # those rows simply don't accrue to the v2 columns.
                        "score_v2": s.get("rank_score_v2"),
                        "stage_v2": _stage_v2(s),
                        "turn_state": s.get("turn_state"),
                        "members": members})
            existing.add(f"{today_str}|{k}")
        if not new:
            return 0
        p = _path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for r in new:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        return len(new)
    except Exception as e:  # noqa: BLE001
        log.warning("subsector track snapshot failed: %s", e)
        return 0


# --------------------------------------------------------------------------- #
# maturation + member-EW forward returns
# --------------------------------------------------------------------------- #
def _member_ret(ticker: str, root: Path, start: str, end: str) -> float | None:
    p0, p1 = _level_asof(ticker, root, start), _close_at(ticker, root, end)
    if p0 in (None, 0) or p1 is None:
        return None
    return float(p1 / p0 - 1.0)


def _fwd_basket(members: list, root: Path, start: str, horizon_d: int) -> float | None:
    """Equal-weight mean forward return of the frozen members we can price, minus SPY."""
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


def _daily_ic(rows: list, horizon_d: int, field: str = "score") -> dict:
    """Per-date cross-sectional IC of a score field vs forward return → HAC summary.
    The Newey-West lag is the horizon (overlapping windows autocorrelate at lag h)."""
    by_date: dict[str, list] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    ics = []
    for _, day in sorted(by_date.items()):
        xs = [r.get(field) for r in day if r.get(field) is not None]
        fwd = [r["fwd"] for r in day if r.get(field) is not None]
        if len(xs) < 10 or len(set(xs)) < 2 or len(set(fwd)) < 2:
            continue
        ic = V.rank_ic(xs, fwd)
        if ic == ic:
            ics.append(ic)
    return V.ic_summary(ics, periods_per_year=2 * horizon_d) if len(ics) >= 6 else {"n_days": len(ics)}


def _by_stage(rows: list, field: str = "stage") -> dict:
    out: dict[str, dict] = {}
    by: dict[str, list] = {}
    for r in rows:
        if r.get(field) is None:
            continue
        by.setdefault(r.get(field) or "?", []).append(r["fwd"])
    for st, fwds in by.items():
        n = len(fwds)
        mean = sum(fwds) / n if n else 0.0
        if st == "emerging":
            hit = sum(1 for f in fwds if f > 0) / n if n else None
        elif st == "fading":
            hit = sum(1 for f in fwds if f < 0) / n if n else None
        else:
            hit = None
        out[st] = {"n": n, "mean_fwd_rel": round(mean, 4),
                   "hit_rate": round(hit, 3) if hit is not None else None}
    return out


def _recent_misses(rows: list, horizon_d: int, k: int = 8) -> list[dict]:
    """ERROR LEDGER: directional calls that were FALSIFIED — emerging that underperformed,
    fading that outperformed — most recent first. The system's own logged mistakes."""
    miss = []
    for r in rows:
        st, fwd = r.get("stage"), r.get("fwd")
        if st == "emerging" and fwd < 0:
            miss.append(r)
        elif st == "fading" and fwd > 0:
            miss.append(r)
    miss.sort(key=lambda r: (r["date"], abs(r["fwd"])), reverse=True)
    return [{"date": r["date"], "key": r["key"], "name": r.get("name"),
             "theme": r.get("theme"), "stage": r["stage"], "fwd_rel": round(r["fwd"], 4),
             "horizon_d": horizon_d} for r in miss[:k]]


def _head_to_head(out_h: dict) -> dict:
    """Incumbent rank vs turn-engine rank, per horizon — a scoreboard, not a verdict.

    Deliberately prints both ICs and the gap and stops there. Declaring a winner needs the
    same bar any promotion needs (matured n plus a Newey-West t), and until a horizon
    reaches it the honest word is "measuring" — the turn engine ships because its
    arithmetic is defensible, not because this table already favours it.
    """
    rows = {}
    lead = None
    for h, e in out_h.items():
        v2 = e.get("v2") or {}
        a, b = e.get("score_ic"), v2.get("score_ic")
        rows[h] = {"n": e.get("n_matured"), "n_v2": v2.get("n_matured"),
                   "ic": a, "ic_v2": b,
                   "gap": (round(b - a, 4) if (a is not None and b is not None) else None),
                   "t_hac": e.get("score_ic_t_hac"), "t_hac_v2": v2.get("score_ic_t_hac")}
        if (v2.get("n_matured") or 0) >= _MIN_PROVEN_N and b is not None and a is not None:
            lead = "v2" if b > a else "incumbent"
    return {"by_horizon": rows, "leader": lead,
            "note": ("Both ranks graded on the same matured rows and the same rule. No "
                     "horizon has enough matured turn-engine observations to call a "
                     "winner yet." if lead is None else
                     f"At the current matured counts the {lead} rank carries the higher "
                     "information coefficient — still measuring, not promoted."),
            "note_zh": ("两套排序在相同到期样本、相同规则下评分。目前尚无周期积累足够的转向"
                        "引擎观测以判定优劣。" if lead is None else
                        "在当前到期样本量下，" + ("转向引擎" if lead == "v2" else "原排序")
                        + "的信息系数更高——仍在测量中，未获提升。")}


def compute(today: date | str | None = None, root: Path | None = None,
            horizons=_HORIZONS) -> dict:
    """Grade every matured snapshot across all horizons. Never raises; degrades to 'accruing'."""
    try:
        root = Path(root) if root else config.ROOT
        today_dt = pd.Timestamp(today).date() if today else date.today()
        rows = _load(root)
        n_days = len({r.get("date") for r in rows})
        out_h: dict[str, dict] = {}
        peak_ic, lead_time = None, None
        misses: list[dict] = []
        for h in horizons:
            mat = _matured(rows, root, h, today_dt)
            ic = _daily_ic(mat, h)
            # HEAD-TO-HEAD: the turn engine's rank graded on the SAME matured rows, same
            # rule, same HAC lag. Only rows carrying score_v2 accrue, so the two columns can
            # legitimately disagree on n — that is disclosed, not averaged away.
            mat_v2 = [r for r in mat if r.get("score_v2") is not None]
            ic_v2 = _daily_ic(mat_v2, h, field="score_v2")
            out_h[str(h)] = {
                "n_matured": len(mat),
                "score_ic": ic.get("mean_ic"),
                "score_ic_t_hac": ic.get("t_hac"),
                "score_ic_detail": ic,
                "by_stage": _by_stage(mat),
                "v2": {
                    "n_matured": len(mat_v2),
                    "score_ic": ic_v2.get("mean_ic"),
                    "score_ic_t_hac": ic_v2.get("t_hac"),
                    "by_stage": _by_stage(mat_v2, field="stage_v2"),
                },
            }
            t, mic = ic.get("t_hac"), ic.get("mean_ic")
            if t is not None and t >= 2.0 and mic is not None and mic > 0 and (peak_ic is None or mic > peak_ic):
                peak_ic, lead_time = mic, h
            if h == 21:                                  # error ledger from the 21d window
                misses = _recent_misses(mat, h)

        proven = {}
        for h, e in out_h.items():
            t = e.get("score_ic_t_hac")
            proven[h] = bool(e["n_matured"] >= _MIN_PROVEN_N and t is not None and t >= 2.0
                             and (e.get("score_ic") or 0) > 0)
        any_matured = any(e["n_matured"] > 0 for e in out_h.values())
        if not any_matured:
            verdict, note = "accruing", (
                "Measuring — logging daily calls; no horizon has matured yet. The forward "
                "edge is unmeasured. Context-only.")
            note_zh = ("测量中——每日记录研判，尚无周期到期，前瞻性优势暂未测得。仅供参考。")
        elif any(proven.values()):
            verdict, note = "validated", (
                f"Emerging-score IC is significant at the {lead_time}d horizon (measured). "
                "Context-only — informs the read, never sizes.")
            note_zh = (f"升温评分的信息系数在 {lead_time} 天周期上显著（已测得）。仅供参考——辅助研判，从不用于仓位。")
        else:
            verdict, note = "measuring", (
                "Accruing forward observations; no horizon clears the Newey-West significance "
                "bar yet. Early numbers are provisional, context-only.")
            note_zh = ("正在累积前瞻观测；尚无周期通过 Newey-West 显著性检验。早期数据为暂定，仅供参考。")
        return {
            "schema": SCHEMA, "as_of": today_dt.isoformat(), "generated_at": _now_iso(),
            "is_context_only": True, "n_snapshots": len(rows), "n_days": n_days,
            "horizons": out_h, "lead_time_d": lead_time, "peak_score_ic": peak_ic,
            "proven": proven, "any_matured": any_matured, "verdict": verdict,
            "note": note, "note_zh": note_zh,
            "recent_misses": misses,
            "head_to_head": _head_to_head(out_h),
            "disclaimer": ("An accountable scorecard of the rotation read's own calls — "
                           "emerging_score rank and emerging/fading labels graded against "
                           "realized member-equal-weight SPY-relative forward returns. Until a "
                           "horizon matures and clears a Newey-West significance bar it is "
                           "'measuring', never trusted. Members are frozen point-in-time; only "
                           "priceable members are used. Nothing here sizes a position."),
            "disclaimer_zh": ("对轮动研判自身研判的可问责记分卡——升温评分排名与升温/退潮标签，"
                              "以成分股等权、相对 SPY 的实际前瞻收益进行评分。在某周期到期并通过 "
                              "Newey-West 显著性检验之前，始终为「测量中」，不予采信。成分股按时间点冻结，"
                              "仅使用可定价成分股。此处任何内容都不用于确定仓位。"),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("subsector track compute failed: %s", e)
        return {"schema": SCHEMA, "as_of": str(today or date.today()), "generated_at": _now_iso(),
                "is_context_only": True, "n_snapshots": 0, "n_days": 0, "horizons": {},
                "lead_time_d": None, "peak_score_ic": None, "proven": {}, "any_matured": False,
                "verdict": "accruing", "note": f"compute error ({e}) — accruing, degrade-safe.",
                "note_zh": f"计算出错（{e}）——累积中，降级安全。",
                "recent_misses": []}
