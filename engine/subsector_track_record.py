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
  3. "proven" only with enough matured obs AND a significant positive HAC-t AND a graded
     span covering >= 6 non-overlapping horizon-length windows (_MIN_INDEP_WINDOWS). The
     window floor is the one that bites: matured rows count a 268-name cross-section, so a
     single date clears the row bar while buying no independent evidence at all.

CONTEXT-ONLY · DEGRADE-NEVER-RAISE — no matured data ⇒ a valid 'accruing'
payload, never an exception. Nothing here sizes a position.
"""
from __future__ import annotations

import json
import logging
import math
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
_MIN_PROVEN_N = 40          # matured cross-sectional ROWS before a horizon can be called "proven"
# INDEPENDENT-WINDOW FLOOR (2026-08-03 experiments audit). _MIN_PROVEN_N counts matured
# cross-sectional rows — one date of 268 subsectors satisfies it outright — while the gate it
# guards is a TIME-SERIES statistic on the per-date IC. On 2026-08-03 the 21d horizon shipped
# verdict="validated" off 10 IC-days spanning 12 CALENDAR days: ~0.4 non-overlapping 21-day
# windows, i.e. one market episode graded ten times. Rows are not evidence; independent
# windows are. A horizon may only be called proven once its matured IC-day span covers at
# least this many NON-OVERLAPPING horizon-length windows:
#
#     indep_windows = (last_ic_date - first_ic_date).days / (horizon_d * 7 / 5)
#
# The 7/5 converts the horizon from trading days (how _HORIZONS is expressed) to the calendar
# days the span is measured in — 21 trading days ≈ 29.4 calendar days. Six windows is the
# floor, not a target: it is the smallest span at which the episodes being averaged can differ.
_MIN_INDEP_WINDOWS = 6.0
_TD_TO_CALENDAR = 7.0 / 5.0  # trading days → calendar days


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


def _window_span(ic_dates: list, horizon_d: int) -> dict:
    """Calendar span of the IC-days and how many NON-OVERLAPPING horizon-length windows it
    covers. This — not the matured row count — is the honest sample size of a time-series
    statistic built from daily cross-sections of one universe (see _MIN_INDEP_WINDOWS)."""
    if not ic_dates:
        return {"ic_first_date": None, "ic_last_date": None,
                "ic_span_days": 0, "indep_windows": 0.0}
    first, last = min(ic_dates), max(ic_dates)
    try:
        span = int((pd.Timestamp(last) - pd.Timestamp(first)).days)
    except Exception:  # noqa: BLE001
        span = 0
    win = max(1.0, float(horizon_d) * _TD_TO_CALENDAR)
    return {"ic_first_date": first, "ic_last_date": last,
            "ic_span_days": span, "indep_windows": round(span / win, 2)}


def _iid_t(ic: dict) -> float | None:
    """Plain iid t of the per-date IC series — mean / (sd / sqrt(n)). The NO-correction
    baseline a HAC t is supposed to sit below on an overlapping-window series."""
    mean, sd, n = ic.get("mean_ic"), ic.get("ic_vol"), ic.get("n")
    try:
        if mean is None or sd is None or not n or int(n) < 2 or float(sd) <= 0:
            return None
        return float(mean) / (float(sd) / math.sqrt(float(n)))
    except (TypeError, ValueError):  # noqa: BLE001
        return None


def _gate_t(ic: dict, horizon_d: int) -> tuple[float | None, bool]:
    """(t the promotion gate is allowed to read, hac_was_anticonservative).

    Newey-West is a CORRECTION: on a positively-overlapping series it widens the standard
    error and pushes |t| DOWN from the iid baseline. When it does the opposite — t_hac
    exceeds |t_iid|, which happens when the Bartlett long-run variance lands below gamma0/n
    on a short series — the "corrected" t is anticonservative BY CONSTRUCTION and is not
    evidence of anything. Measured 2026-08-03 on this very ledger: 1.392>1.208 @5d,
    4.638>3.600 @10d, 4.850>3.179 @21d, all three horizons inverted.

    The gate then reads the iid t (the weaker of the two). This can only ever WITHDRAW a
    promotion, never grant one, and the substitution is announced on the Actions log
    whenever it touches a t that would otherwise have cleared the bar.
    """
    t_hac = ic.get("t_hac")
    t_iid = _iid_t(ic)
    if t_hac is None:
        return (t_iid, False)
    if t_iid is None:
        return (float(t_hac), False)
    if float(t_hac) > abs(t_iid):
        if float(t_hac) >= 2.0:
            # Bare print at line start + flush — a logger prefix makes GitHub drop the
            # annotation silently (CLAUDE.md, tests/test_gh_annotation_line_start.py).
            print(f"::warning title=subsector_track_record::hac anticonservative at {horizon_d}d "
                  f"— t_hac={float(t_hac):.3f} exceeds |t_iid|={abs(t_iid):.3f} on n="
                  f"{ic.get('n')} overlapping IC-days (effective lag "
                  f"{ic.get('hac_lags')} of {ic.get('hac_lags_requested')} requested); "
                  f"promotion gate reads the iid t instead", flush=True)
        return (abs(t_iid) if float(t_hac) > 0 else -abs(t_iid), True)
    return (float(t_hac), False)


def _daily_ic(rows: list, horizon_d: int, field: str = "score") -> dict:
    """Per-date cross-sectional IC of a score field vs forward return → HAC summary.
    The Newey-West lag is the horizon (overlapping windows autocorrelate at lag h).

    Also discloses the CALENDAR SPAN those IC-days cover and the non-overlapping
    horizon-windows it buys (`ic_span_days` / `indep_windows`) — the promotion gate reads
    the windows, because a row count cannot tell one episode from six."""
    by_date: dict[str, list] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    ics, ic_dates = [], []
    for d, day in sorted(by_date.items()):
        xs = [r.get(field) for r in day if r.get(field) is not None]
        fwd = [r["fwd"] for r in day if r.get(field) is not None]
        if len(xs) < 10 or len(set(xs)) < 2 or len(set(fwd)) < 2:
            continue
        ic = V.rank_ic(xs, fwd)
        if ic == ic:
            ics.append(ic)
            ic_dates.append(d)
    out = (V.ic_summary(ics, periods_per_year=2 * horizon_d) if len(ics) >= 6
           else {"n_days": len(ics)})
    out.update(_window_span(ic_dates, horizon_d))
    return out


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


# --------------------------------------------------------------------------- #
# FRONT-FACING NOTE — one table, one guard
#
# The note is the only sentence from this ledger a reader actually sees (it renders through
# scripts/build_subsector_rotation.py -> site/marketdata/subsector_rotation.json ->
# templates/subsector_rotation.js -> sector_central.html). Exactly ONE of these strings
# claims significance, and it is reachable from exactly one verdict.
#
# The strings live in a table rather than inline in compute() so `note_violation` can audit a
# STORED payload against them — the claim gate (scripts/check_validated_claims.py) cannot see
# this sentence at all: it never uses the word "validated", and it reaches the page through a
# runtime fetch of a 758 KB single-line JSON that no SCAN_GLOB covers (and whose
# `"verdict": "validated"` field is a _STRUCTURAL skip by design). The 2026-08-03 audit found
# the significance claim shipped for weeks with nothing able to fail because of it.
# --------------------------------------------------------------------------- #
_NOTES: dict[str, tuple[str, str]] = {
    "accruing": (
        "Measuring — logging daily calls; no horizon has matured yet. The forward "
        "edge is unmeasured. Context-only.",
        "测量中——每日记录研判，尚无周期到期，前瞻性优势暂未测得。仅供参考。"),
    "measuring": (
        "Accruing forward observations; no horizon clears the Newey-West significance "
        "bar yet. Early numbers are provisional, context-only.",
        "正在累积前瞻观测；尚无周期通过 Newey-West 显著性检验。早期数据为暂定，仅供参考。"),
    # THE ONLY significance claim in this module. Reachable only when honest_verdict()
    # returns "validated" off the payload's own disclosed numbers.
    "validated": (
        "Emerging-score IC is significant at the {h}d horizon (measured). "
        "Context-only — informs the read, never sizes.",
        "升温评分的信息系数在 {h} 天周期上显著（已测得）。仅供参考——辅助研判，从不用于仓位。"),
}


def _note_for(verdict: str, lead_time: int | None) -> tuple[str, str]:
    en, zh = _NOTES.get(verdict) or _NOTES["accruing"]
    return en.format(h=lead_time), zh.format(h=lead_time)


def honest_verdict(payload: dict) -> str:
    """Re-derive the verdict from a payload's OWN disclosed per-horizon numbers.

    Pure function of the artifact — it reads no prices and no snapshots — so a STORED
    track-record payload can be audited long after the run that produced it, by a test or by
    the builder that is about to publish it.
    """
    hz = payload.get("horizons") or {}
    if not any((e.get("n_matured") or 0) > 0 for e in hz.values()):
        return "accruing"
    for e in hz.values():
        t = e.get("score_ic_t_gate")
        if ((e.get("n_matured") or 0) >= _MIN_PROVEN_N
                and float(e.get("indep_windows") or 0.0) >= _MIN_INDEP_WINDOWS
                and t is not None and float(t) >= 2.0
                and (e.get("score_ic") or 0) > 0):
            return "validated"
    return "measuring"


def note_violation(payload: dict) -> str | None:
    """None when a track-record payload's front-facing note is backed by its own numbers;
    a one-line description of the violation otherwise.

    Two independent things must hold, and BOTH are checked against the payload alone:
      1. the stated verdict is the one honest_verdict() derives from the disclosed numbers;
      2. the note pair is verbatim the _NOTES entry for that verdict.

    (2) is what actually pins the significance sentence: it exists in exactly one table row,
    so a note carrying it can only pass while the verdict is "validated" — and (1) will not
    let the verdict be "validated" unless a horizon really cleared both floors. Wording drift
    is caught too, which matters because the honest 'measuring' copy legitimately contains
    "significance"/"显著" inside a NEGATION ("no horizon clears the ... bar yet"); a token
    grep would either miss the claim or flag the disclaimer.
    """
    stated = payload.get("verdict")
    honest = honest_verdict(payload)
    if stated != honest:
        hz = payload.get("horizons") or {}
        detail = "; ".join(
            f"{h}d: n={e.get('n_matured')}, ic={e.get('score_ic')}, "
            f"t_gate={e.get('score_ic_t_gate')}, indep_windows={e.get('indep_windows')}"
            for h, e in sorted(hz.items(), key=lambda kv: int(kv[0])))
        return (f"verdict={stated!r} but the payload's own numbers support {honest!r} "
                f"(floors: n>={_MIN_PROVEN_N}, indep_windows>={_MIN_INDEP_WINDOWS}, "
                f"t>=2.0, ic>0) — {detail}")
    if payload.get("compute_error"):
        return None                    # degrade-safe payload: claims nothing, copy is the error
    want_en, want_zh = _note_for(honest, payload.get("lead_time_d"))
    if (payload.get("note") or "") != want_en or (payload.get("note_zh") or "") != want_zh:
        return (f"note copy does not match the canonical {honest!r} note "
                f"(lead_time_d={payload.get('lead_time_d')!r}) — got "
                f"{(payload.get('note') or '')[:90]!r}")
    return None


def withdraw_unbacked_note(payload: dict) -> str | None:
    """De-escalate a payload IN PLACE to the note its own numbers support.

    Returns the violation string when anything was withdrawn (the caller announces it), None
    when the note was already backed. DE-ESCALATION ONLY: honest_verdict never returns
    "validated" unless both floors cleared, so this can strip a claim and never mint one.
    """
    viol = note_violation(payload)
    if viol is None:
        return None
    payload["verdict"] = honest_verdict(payload)
    if payload["verdict"] != "validated":
        payload["lead_time_d"] = None
        payload["peak_score_ic"] = None
    payload["note"], payload["note_zh"] = _note_for(payload["verdict"],
                                                    payload.get("lead_time_d"))
    payload["note_withdrawn"] = viol
    return viol


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
            t_gate, anticon = _gate_t(ic, h)
            out_h[str(h)] = {
                "n_matured": len(mat),
                "score_ic": ic.get("mean_ic"),
                "score_ic_t_hac": ic.get("t_hac"),
                # what the promotion gate actually reads, and why it may differ from t_hac
                "score_ic_t_gate": (round(t_gate, 3) if t_gate is not None else None),
                "score_ic_t_iid": (round(_iid_t(ic), 3) if _iid_t(ic) is not None else None),
                "hac_anticonservative": anticon,
                # independent-window disclosure — the honest n of a time-series gate
                "ic_span_days": ic.get("ic_span_days"),
                "indep_windows": ic.get("indep_windows"),
                "indep_windows_required": _MIN_INDEP_WINDOWS,
                "score_ic_detail": ic,
                "by_stage": _by_stage(mat),
                "v2": {
                    "n_matured": len(mat_v2),
                    "score_ic": ic_v2.get("mean_ic"),
                    "score_ic_t_hac": ic_v2.get("t_hac"),
                    "by_stage": _by_stage(mat_v2, field="stage_v2"),
                },
            }
            if h == 21:                                  # error ledger from the 21d window
                misses = _recent_misses(mat, h)

        proven = {}
        for h, e in out_h.items():
            t = e.get("score_ic_t_gate")
            proven[h] = bool(e["n_matured"] >= _MIN_PROVEN_N
                             # the honest n: independent windows, not cross-sectional rows
                             and (e.get("indep_windows") or 0.0) >= _MIN_INDEP_WINDOWS
                             and t is not None and t >= 2.0
                             and (e.get("score_ic") or 0) > 0)
        # lead_time is picked FROM the proven set, so the headline horizon can never name one
        # the gate refused (it used to be selected on a bare t>=2.0, ignoring both floors).
        for h, e in out_h.items():
            mic = e.get("score_ic")
            if proven.get(h) and mic is not None and (peak_ic is None or mic > peak_ic):
                peak_ic, lead_time = mic, int(h)
        any_matured = any(e["n_matured"] > 0 for e in out_h.values())
        verdict = ("accruing" if not any_matured
                   else "validated" if any(proven.values())
                   else "measuring")
        note, note_zh = _note_for(verdict, lead_time)
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
                           "realized member-equal-weight SPY-relative forward returns. A horizon "
                           "stays 'measuring' until it clears a Newey-West significance bar AND "
                           "its graded days span at least six non-overlapping windows of that "
                           "length — many readings of one stretch of market are one reading, not "
                           "many. Members are frozen point-in-time; only priceable members are "
                           "used. Nothing here sizes a position."),
            "disclaimer_zh": ("对轮动研判自身研判的可问责记分卡——升温评分排名与升温/退潮标签，"
                              "以成分股等权、相对 SPY 的实际前瞻收益进行评分。某周期须同时通过 "
                              "Newey-West 显著性检验，且其评分日跨度覆盖至少六段互不重叠的同长度窗口，"
                              "才会脱离「测量中」——同一段行情读十遍仍只是一遍。成分股按时间点冻结，"
                              "仅使用可定价成分股。此处任何内容都不用于确定仓位。"),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("subsector track compute failed: %s", e)
        return {"schema": SCHEMA, "as_of": str(today or date.today()), "generated_at": _now_iso(),
                "is_context_only": True, "n_snapshots": 0, "n_days": 0, "horizons": {},
                "lead_time_d": None, "peak_score_ic": None, "proven": {}, "any_matured": False,
                "verdict": "accruing", "note": f"compute error ({e}) — accruing, degrade-safe.",
                "note_zh": f"计算出错（{e}）——累积中，降级安全。",
                # names the degradation so note_violation exempts the copy check rather than
                # alarming on it — a payload that claims nothing cannot overclaim
                "compute_error": str(e),
                "recent_misses": []}
