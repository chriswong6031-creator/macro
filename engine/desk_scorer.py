"""Shared falsifiable-thesis scorer (Phase-C durability engine). DETERMINISTIC · NEVER-RAISES.

Extracted verbatim from engine.ai_desk_scorer so every desk with falsifiable theses
(ai_desk, policy_intent, radar, narrative_brain, stock_desk, thematic_desk, …) can grade
against ONE audited engine instead of a per-desk copy. It is parameterized by ledger
paths + schema + predicate evaluators + aggregation dimensions + calibration-note text;
the defaults reproduce ai_desk's exact behaviour, so engine.ai_desk_scorer is now a thin
binding over this module and the extraction is byte-for-byte behaviour-preserving.

How it scores (no LLM — pure arithmetic over the price cache):
  * A thesis's `falsifier.check` is the ENGINE-derived predicate describing the condition
    under which the thesis is FALSE. We evaluate it once the price window through
    `check_by` has actually elapsed in the data:
      - rel_return: (subject ETF total return − benchmark total return) over the window;
        `miss` iff op(realized, threshold) is True, else `hit`.
      - level (fade-fear): `miss` iff the level makes a new high above entry, else `hit`.
      - soft / unknown kind: not machine-checkable → `unscored` (NEVER fudged).
  * Not ready (data doesn't yet cover check_by) → left open for a later run.
  * check_by long past with no data (e.g. delisted) → `expired`.

Discipline:
  * theses.jsonl is APPEND-ONLY (the desk owns it; we never rewrite it). Outcomes go to a
    SEPARATE append-only scored.jsonl (one row per thesis id), so scoring is idempotent and
    auditable. The rolling summary is written to track_record.json, which the desk's
    briefing reads back to calibrate conviction.
  * CONTEXT-ONLY — track_record never enters a score / size / allocation.
  * Degrade-never-raise; every public function returns plain data or None.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config
from engine import ai_desk as _desk     # shared price-cache accessors (_close_series / _level_asof)

log = logging.getLogger(__name__)

GRACE_BD = 10           # business days past check_by with no data → expired
TERMINAL = ("hit", "miss", "unscored", "expired")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# ledger / scored io (both append-only; dedupe by id, last-wins on read)
# --------------------------------------------------------------------------- #
def load_jsonl(path) -> list:
    try:
        return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        return []


def dedupe_by_id(rows: list) -> dict:
    out = {}
    for r in rows:
        rid = r.get("id")
        if rid:
            out[rid] = r            # last write wins (handles same-day re-runs)
    return out


def load_ledger(root, ledger_path) -> dict:
    return dedupe_by_id(load_jsonl(Path(root).joinpath(*ledger_path)))


def load_scored(root, scored_path) -> dict:
    return dedupe_by_id(load_jsonl(Path(root).joinpath(*scored_path)))


# --------------------------------------------------------------------------- #
# price reads (reuse ai_desk._close_series — lowercase 'close')
# --------------------------------------------------------------------------- #
def covers(ticker, root, check_by) -> bool:
    """True once the cache holds a trading day ON OR AFTER check_by (window elapsed)."""
    s = _desk._close_series(ticker, root)
    try:
        return s is not None and not s.empty and s.index.max() >= pd.Timestamp(check_by)
    except Exception:  # noqa: BLE001
        return False


def close_at(ticker, root, on_date) -> float | None:
    s = _desk._close_series(ticker, root)
    if s is None or s.empty:
        return None
    try:
        s = s[s.index <= pd.Timestamp(on_date)]
        return round(float(s.iloc[-1]), 4) if len(s) else None
    except Exception:  # noqa: BLE001
        return None


def max_close_between(ticker, root, start, end) -> float | None:
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
def start_level(ticker, entry: dict, root, asof) -> float | None:
    """Entry close captured at log time (authoritative), else recover from the cache."""
    if ticker in (entry or {}):
        return entry[ticker]
    return _desk._level_asof(ticker, root, asof)


def eval_rel_return(check, entry, root, asof, check_by) -> dict | None:
    et, vs = check.get("subject_ticker"), check.get("vs")
    e0 = start_level(et, entry, root, asof)
    e1 = close_at(et, root, check_by)
    b0 = start_level(vs, entry, root, asof) if vs else 1.0
    b1 = close_at(vs, root, check_by) if vs else 1.0
    if None in (e0, e1, b0, b1) or e0 == 0 or (vs and b0 == 0):
        return None
    realized = (e1 / e0 - 1.0) - ((b1 / b0 - 1.0) if vs else 0.0)
    op, thr = check.get("op"), float(check.get("threshold", 0.0))
    falsified = (realized < thr) if op == "<" else (realized > thr)
    dir_ok = (realized > 0) if op == "<" else (realized < 0)   # long lean vs short lean
    return {"outcome": "miss" if falsified else "hit",
            "realized": round(realized, 4), "directionally_correct": bool(dir_ok)}


def eval_level(check, entry, root, asof, check_by) -> dict | None:
    t = check.get("subject_ticker")
    e0 = start_level(t, entry, root, asof)
    mx = max_close_between(t, root, asof, check_by)
    final = close_at(t, root, check_by)
    if None in (e0, mx, final) or e0 == 0:
        return None
    falsified = mx > e0                                        # VIX made a new high above entry
    return {"outcome": "miss" if falsified else "hit",
            "realized": round(mx / e0 - 1.0, 4),
            "directionally_correct": bool(final < e0),
            "max_level": mx, "final_level": final}


EVALUATORS = {"rel_return": eval_rel_return, "level": eval_level}


def score_one(row: dict, root, today, *, evaluators=None, grace_bd: int = GRACE_BD) -> dict | None:
    """Score one open thesis. Returns a scored row, or None when not yet ready.
    `evaluators` maps check.kind → evaluator fn (defaults to EVALUATORS)."""
    evaluators = EVALUATORS if evaluators is None else evaluators
    check = (row.get("falsifier") or {}).get("check") or {}
    kind = check.get("kind")
    asof, check_by = row.get("state_asof"), row.get("check_by")
    base = {"id": row.get("id"), "subject": row.get("subject"), "lean": row.get("lean"),
            "conviction": row.get("conviction"), "kind": kind, "check_by": check_by,
            "scored_at": now_iso()}
    if kind == "soft" or kind not in evaluators or not check_by:
        return {**base, "outcome": "unscored", "realized": None,
                "reason": check.get("reason", "not machine-checkable")}
    tickers = [check.get("subject_ticker")] + ([check["vs"]] if check.get("vs") else [])
    if not all(covers(t, root, check_by) for t in tickers if t):
        if today is not None and pd.Timestamp(today) > pd.Timestamp(check_by) + pd.offsets.BusinessDay(grace_bd):
            return {**base, "outcome": "expired", "realized": None,
                    "reason": "no price data through check_by"}
        return None                                           # not ready — try again later
    res = evaluators[kind](check, row.get("entry_levels") or {}, root, asof, check_by)
    if res is None:
        return None
    return {**base, **res}


# --------------------------------------------------------------------------- #
# aggregation — the rolling track record the briefing reads back
# --------------------------------------------------------------------------- #
def bucket(rows: list) -> dict:
    decided = [r for r in rows if r.get("outcome") in ("hit", "miss")]
    hits = sum(1 for r in decided if r["outcome"] == "hit")
    n = len(decided)
    dir_ok = sum(1 for r in decided if r.get("directionally_correct"))
    return {"n": n, "hits": hits, "misses": n - hits,
            "hit_rate": round(hits / n, 3) if n else None,
            "dir_accuracy": round(dir_ok / n, 3) if n else None}


def aggregate(scored: list, ledger: dict, today, *, schema: str,
              by_conviction_keys=("high", "medium", "low"),
              by_kind_keys=("rel_return", "level"),
              calibration_note_fn=None, calibration_note_zh_fn=None) -> dict:
    decided = [r for r in scored if r.get("outcome") in ("hit", "miss")]
    overall = bucket(decided)
    by_conv = {c: bucket([r for r in decided if r.get("conviction") == c])
               for c in by_conviction_keys}
    by_kind = {k: bucket([r for r in decided if r.get("kind") == k])
               for k in by_kind_keys}
    scored_ids = {r.get("id") for r in scored}
    open_n = sum(1 for tid, row in ledger.items()
                 if tid not in scored_ids
                 and ((row.get("falsifier") or {}).get("check") or {}).get("kind") != "soft")
    recent = sorted([r for r in scored if r.get("outcome") in ("hit", "miss")],
                    key=lambda r: r.get("scored_at") or "", reverse=True)[:10]
    out = {
        "schema": schema,
        "as_of": (today.isoformat() if hasattr(today, "isoformat") else str(today)),
        "scored_total": len(decided),
        "open": open_n,
        "unscored_soft": sum(1 for r in scored if r.get("outcome") == "unscored"),
        "expired": sum(1 for r in scored if r.get("outcome") == "expired"),
        "overall": overall,
        "by_conviction": by_conv,
        "by_kind": by_kind,
        "calibration_note": calibration_note_fn(overall, by_conv) if calibration_note_fn else "",
        "recent": [{k: r.get(k) for k in
                    ("id", "subject", "lean", "conviction", "outcome", "realized", "check_by")}
                   for r in recent],
    }
    if calibration_note_zh_fn is not None:
        out["calibration_note_zh"] = calibration_note_zh_fn(overall, by_conv)
    return out


def append_scored(rows: list, root, scored_path) -> None:
    try:
        out = Path(root).joinpath(*scored_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "a") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("desk_scorer: scored append failed: %s", e)


def write_track(track: dict, root, track_path) -> None:
    try:
        out = Path(root).joinpath(*track_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(track, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("desk_scorer: track_record write failed: %s", e)


def run(*, ledger_path, scored_path, track_path, schema,
        evaluators=None, by_kind_keys=("rel_return", "level"),
        calibration_note_fn=None, calibration_note_zh_fn=None, grace_bd: int = GRACE_BD,
        persist: bool = True, root=None, today=None, log_label: str = "desk_scorer") -> dict | None:
    """Score newly-due theses for ONE desk's ledger, append outcomes, rewrite its track
    record. Idempotent (skips ids already in scored.jsonl). Returns the track record, or
    None on error. Every desk-specific knob (paths/schema/evaluators/notes) is injected."""
    try:
        root = Path(root) if root else config.ROOT
        today = today or date.today()
        ledger = load_ledger(root, ledger_path)
        already = load_scored(root, scored_path)
        new_rows = []
        for tid, row in ledger.items():
            if tid in already:
                continue
            res = score_one(row, root, today, evaluators=evaluators, grace_bd=grace_bd)
            if res is not None:
                new_rows.append(res)
        combined = list(dedupe_by_id(list(already.values()) + new_rows).values())
        track = aggregate(combined, ledger, today, schema=schema, by_kind_keys=by_kind_keys,
                          calibration_note_fn=calibration_note_fn,
                          calibration_note_zh_fn=calibration_note_zh_fn)
        if persist:
            if new_rows:
                append_scored(new_rows, root, scored_path)
            write_track(track, root, track_path)
        if new_rows:
            log.info("%s: scored %d new (%s)", log_label, len(new_rows),
                     ", ".join(f"{r['id']}:{r['outcome']}" for r in new_rows))
        return track
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("%s run failed: %s", log_label, e)
        return None
