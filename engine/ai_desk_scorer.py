"""AI Desk scorer — the durability ENGINE (Phase C). DETERMINISTIC · NEVER-SCORED.

This is what makes a desk conclusion *durable* rather than merely plausible: the
Phase-0 validation discipline applied to the AI's own output. It grades the
falsifiable theses the desk logged (engine.ai_desk → data/ai_desk/theses.jsonl)
against realized closes, and feeds the measured hit-rate back into conviction:

    Quant DETECTS → AI JUDGES → *track-record GATES* (this module)

How it scores (no LLM — pure arithmetic over the price cache):
  * A thesis's `falsifier.check` is the ENGINE-derived predicate describing the
    condition under which the thesis is FALSE. We evaluate it once the price window
    through `check_by` has actually elapsed in the data:
      - rel_return: (subject ETF total return − SPY total return) over [state_asof,
        check_by]; `miss` iff op(realized, threshold) is True, else `hit`.
      - level (fade-fear): `miss` iff VIX makes a new high above the entry level
        anywhere in the window, else `hit`.
      - soft: not machine-checkable → `unscored` (NEVER fudged into a hit/miss).
  * Not ready (data doesn't yet cover check_by) → left open for a later run.
  * check_by long past with no data (e.g. delisted) → `expired`.

Discipline:
  * theses.jsonl is APPEND-ONLY (the analyst owns it; we never rewrite it). Outcomes
    go to a SEPARATE append-only data/ai_desk/scored.jsonl (one row per thesis id),
    so scoring is idempotent and auditable. The rolling summary is written to
    data/ai_desk/track_record.json, which engine.ai_desk.gather_desk_state() already
    reads back into the next briefing.
  * CONTEXT-ONLY — track_record never enters a score / size / allocation; nothing in
    axes / regime / conditions imports this. Honest about sample size in the note.
  * Degrade-never-raise; every public function returns plain data or None.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config
from engine import ai_desk as _desk     # reuse paths + _close_series + _level_asof

log = logging.getLogger(__name__)

SCHEMA = "ai_desk_track_record.v1"
_LEDGER = ("data", "ai_desk", "theses.jsonl")
_SCORED = ("data", "ai_desk", "scored.jsonl")
_TRACK = ("data", "ai_desk", "track_record.json")
_GRACE_BD = 10           # business days past check_by with no data → expired
_TERMINAL = ("hit", "miss", "unscored", "expired")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# ledger / scored io (both append-only; dedupe by id, last-wins on read)
# --------------------------------------------------------------------------- #
def _load_jsonl(path) -> list:
    try:
        return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        return []


def _dedupe_by_id(rows: list) -> dict:
    out = {}
    for r in rows:
        rid = r.get("id")
        if rid:
            out[rid] = r            # last write wins (handles same-day re-runs)
    return out


def _load_ledger(root) -> dict:
    return _dedupe_by_id(_load_jsonl(Path(root).joinpath(*_LEDGER)))


def _load_scored(root) -> dict:
    return _dedupe_by_id(_load_jsonl(Path(root).joinpath(*_SCORED)))


# --------------------------------------------------------------------------- #
# price reads (reuse ai_desk._close_series — lowercase 'close')
# --------------------------------------------------------------------------- #
def _covers(ticker, root, check_by) -> bool:
    """True once the cache holds a trading day ON OR AFTER check_by (window elapsed)."""
    s = _desk._close_series(ticker, root)
    try:
        return s is not None and not s.empty and s.index.max() >= pd.Timestamp(check_by)
    except Exception:  # noqa: BLE001
        return False


def _close_at(ticker, root, on_date) -> float | None:
    s = _desk._close_series(ticker, root)
    if s is None or s.empty:
        return None
    try:
        s = s[s.index <= pd.Timestamp(on_date)]
        return round(float(s.iloc[-1]), 4) if len(s) else None
    except Exception:  # noqa: BLE001
        return None


def _max_close_between(ticker, root, start, end) -> float | None:
    s = _desk._close_series(ticker, root)
    if s is None or s.empty:
        return None
    try:
        s = s[(s.index > pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
        return round(float(s.max()), 4) if len(s) else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# the predicate evaluators — a `check` is the FALSIFICATION condition
# --------------------------------------------------------------------------- #
def _start_level(ticker, entry: dict, root, asof) -> float | None:
    """Entry close captured at log time (authoritative), else recover from the cache."""
    if ticker in (entry or {}):
        return entry[ticker]
    return _desk._level_asof(ticker, root, asof)


def _eval_rel_return(check, entry, root, asof, check_by) -> dict | None:
    et, vs = check.get("subject_ticker"), check.get("vs")
    e0 = _start_level(et, entry, root, asof)
    e1 = _close_at(et, root, check_by)
    b0 = _start_level(vs, entry, root, asof) if vs else 1.0
    b1 = _close_at(vs, root, check_by) if vs else 1.0
    if None in (e0, e1, b0, b1) or e0 == 0 or (vs and b0 == 0):
        return None
    realized = (e1 / e0 - 1.0) - ((b1 / b0 - 1.0) if vs else 0.0)
    op, thr = check.get("op"), float(check.get("threshold", 0.0))
    falsified = (realized < thr) if op == "<" else (realized > thr)
    dir_ok = (realized > 0) if op == "<" else (realized < 0)   # long lean vs short lean
    return {"outcome": "miss" if falsified else "hit",
            "realized": round(realized, 4), "directionally_correct": bool(dir_ok)}


def _eval_level(check, entry, root, asof, check_by) -> dict | None:
    t = check.get("subject_ticker")
    e0 = _start_level(t, entry, root, asof)
    mx = _max_close_between(t, root, asof, check_by)
    final = _close_at(t, root, check_by)
    if None in (e0, mx, final) or e0 == 0:
        return None
    falsified = mx > e0                                        # VIX made a new high above entry
    return {"outcome": "miss" if falsified else "hit",
            "realized": round(mx / e0 - 1.0, 4),
            "directionally_correct": bool(final < e0),
            "max_level": mx, "final_level": final}


_EVAL = {"rel_return": _eval_rel_return, "level": _eval_level}


def _score_one(row: dict, root, today) -> dict | None:
    """Score one open thesis. Returns a scored row, or None when not yet ready."""
    check = (row.get("falsifier") or {}).get("check") or {}
    kind = check.get("kind")
    asof, check_by = row.get("state_asof"), row.get("check_by")
    base = {"id": row.get("id"), "subject": row.get("subject"), "lean": row.get("lean"),
            "conviction": row.get("conviction"), "kind": kind, "check_by": check_by,
            "scored_at": _now_iso()}
    if kind == "soft" or kind not in _EVAL or not check_by:
        return {**base, "outcome": "unscored", "realized": None,
                "reason": check.get("reason", "not machine-checkable")}
    tickers = [check.get("subject_ticker")] + ([check["vs"]] if check.get("vs") else [])
    if not all(_covers(t, root, check_by) for t in tickers if t):
        if today is not None and pd.Timestamp(today) > pd.Timestamp(check_by) + pd.offsets.BusinessDay(_GRACE_BD):
            return {**base, "outcome": "expired", "realized": None,
                    "reason": "no price data through check_by"}
        return None                                           # not ready — try again later
    res = _EVAL[kind](check, row.get("entry_levels") or {}, root, asof, check_by)
    if res is None:
        return None
    return {**base, **res}


# --------------------------------------------------------------------------- #
# aggregation — the rolling track record the briefing reads back
# --------------------------------------------------------------------------- #
def _bucket(rows: list) -> dict:
    decided = [r for r in rows if r.get("outcome") in ("hit", "miss")]
    hits = sum(1 for r in decided if r["outcome"] == "hit")
    n = len(decided)
    dir_ok = sum(1 for r in decided if r.get("directionally_correct"))
    return {"n": n, "hits": hits, "misses": n - hits,
            "hit_rate": round(hits / n, 3) if n else None,
            "dir_accuracy": round(dir_ok / n, 3) if n else None}


def _calibration_note(overall: dict, by_conv: dict) -> str:
    if overall["n"] == 0:
        return ("No theses scored yet — the track record begins once the first "
                "check-by dates pass. Keep conviction modest until it does.")
    hi = by_conv.get("high", {})
    parts = [f"{overall['n']} scored, hit-rate {overall['hit_rate']} "
             f"(directional accuracy {overall['dir_accuracy']})."]
    if hi.get("n"):
        parts.append(f"High-conviction calls: {hi['hits']}/{hi['n']} not falsified.")
    if overall["n"] < 10:
        parts.append("Sample is tiny — treat conviction as provisional and lean low.")
    return " ".join(parts)


def _calibration_note_zh(overall: dict, by_conv: dict) -> str:
    """简体中文 mirror of _calibration_note (display-only; the English note is canonical)."""
    if overall["n"] == 0:
        return "尚无判断被评分 —— 待首批核查日到期后开始累积战绩；在此之前置信保持克制。"
    hi = by_conv.get("high", {})
    parts = [f"已评分 {overall['n']} 条，命中率 {overall['hit_rate']}"
             f"（方向准确率 {overall['dir_accuracy']}）。"]
    if hi.get("n"):
        parts.append(f"高置信判断：{hi['hits']}/{hi['n']} 未被证伪。")
    if overall["n"] < 10:
        parts.append("样本极小 —— 将置信视为暂定并保持偏低。")
    return "".join(parts)


def _aggregate(scored: list, ledger: dict, today) -> dict:
    decided = [r for r in scored if r.get("outcome") in ("hit", "miss")]
    overall = _bucket(decided)
    by_conv = {c: _bucket([r for r in decided if r.get("conviction") == c])
               for c in ("high", "medium", "low")}
    by_kind = {k: _bucket([r for r in decided if r.get("kind") == k])
               for k in ("rel_return", "level")}
    scored_ids = {r.get("id") for r in scored}
    open_n = sum(1 for tid, row in ledger.items()
                 if tid not in scored_ids
                 and ((row.get("falsifier") or {}).get("check") or {}).get("kind") != "soft")
    recent = sorted([r for r in scored if r.get("outcome") in ("hit", "miss")],
                    key=lambda r: r.get("scored_at") or "", reverse=True)[:10]
    return {
        "schema": SCHEMA,
        "as_of": (today.isoformat() if hasattr(today, "isoformat") else str(today)),
        "scored_total": len(decided),
        "open": open_n,
        "unscored_soft": sum(1 for r in scored if r.get("outcome") == "unscored"),
        "expired": sum(1 for r in scored if r.get("outcome") == "expired"),
        "overall": overall,
        "by_conviction": by_conv,
        "by_kind": by_kind,
        "calibration_note": _calibration_note(overall, by_conv),
        "calibration_note_zh": _calibration_note_zh(overall, by_conv),
        "recent": [{k: r.get(k) for k in
                    ("id", "subject", "lean", "conviction", "outcome", "realized", "check_by")}
                   for r in recent],
    }


def _append_scored(rows: list, root) -> None:
    try:
        d = Path(root) / "data" / "ai_desk"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "scored.jsonl", "a") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("ai_desk_scorer: scored append failed: %s", e)


def _write_track(track: dict, root) -> None:
    try:
        out = Path(root) / "data" / "ai_desk" / "track_record.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(track, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("ai_desk_scorer: track_record write failed: %s", e)


def run(persist: bool = True, root=None, today=None) -> dict | None:
    """Score newly-due theses, append outcomes, rewrite the track record. Idempotent
    (skips ids already in scored.jsonl). Returns the track record, or None on error."""
    try:
        root = Path(root) if root else config.ROOT
        today = today or date.today()
        ledger = _load_ledger(root)
        already = _load_scored(root)
        new_rows = []
        for tid, row in ledger.items():
            if tid in already:
                continue
            res = _score_one(row, root, today)
            if res is not None:
                new_rows.append(res)
        combined = list(_dedupe_by_id(list(already.values()) + new_rows).values())
        track = _aggregate(combined, ledger, today)
        if persist:
            if new_rows:
                _append_scored(new_rows, root)
            _write_track(track, root)
        if new_rows:
            log.info("ai_desk_scorer: scored %d new (%s)", len(new_rows),
                     ", ".join(f"{r['id']}:{r['outcome']}" for r in new_rows))
        return track
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("ai_desk_scorer run failed: %s", e)
        return None


def render_markdown(track: dict) -> str:
    if not track:
        return "_no track record_"
    L = [f"# AI Desk track record — {track.get('as_of', '?')}", "",
         track.get("calibration_note", ""), "",
         f"- scored: {track['scored_total']} · open: {track['open']} · "
         f"unscored(soft): {track['unscored_soft']} · expired: {track['expired']}"]
    ov = track.get("overall", {})
    L.append(f"- overall: hit-rate {ov.get('hit_rate')} ({ov.get('hits')}/{ov.get('n')}), "
             f"directional {ov.get('dir_accuracy')}")
    for c in ("high", "medium", "low"):
        b = track.get("by_conviction", {}).get(c, {})
        if b.get("n"):
            L.append(f"  · {c}: {b['hits']}/{b['n']} not falsified (dir {b['dir_accuracy']})")
    L += ["", "_context only — never scored, sized, or fed into an allocation_"]
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    _t = run(persist=True)
    print(render_markdown(_t) if _t else "ai_desk_scorer: nothing to do (no ledger).")
