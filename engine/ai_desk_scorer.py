"""AI Desk scorer — the durability ENGINE (Phase C). DETERMINISTIC · NEVER-SCORED.

This is what makes a desk conclusion *durable* rather than merely plausible: the
Phase-0 validation discipline applied to the AI's own output. It grades the
falsifiable theses the desk logged (engine.ai_desk → data/ai_desk/theses.jsonl)
against realized closes, and feeds the measured hit-rate back into conviction:

    Quant DETECTS → AI JUDGES → *track-record GATES* (this module)

The scoring/aggregation engine now lives in the shared, parameterized engine.desk_scorer
(so policy_intent / radar / stock / thematic desks grade against ONE audited engine).
This module is the AI-Desk binding: its ledger paths, schema, and bilingual calibration
notes, plus thin re-exports of the shared internals so existing callers (policy_intent_desk,
radar_scorer) and the test-suite keep importing ai_desk_scorer unchanged.

Discipline:
  * theses.jsonl is APPEND-ONLY; outcomes go to a SEPARATE append-only scored.jsonl, so
    scoring is idempotent + auditable. The rolling summary is written to track_record.json,
    which engine.ai_desk.gather_desk_state() reads back into the next briefing.
  * CONTEXT-ONLY — track_record never enters a score / size / allocation.
  * Degrade-never-raise; every public function returns plain data or None.
"""
from __future__ import annotations

import logging
from pathlib import Path

from engine import desk_scorer as _s

log = logging.getLogger(__name__)

SCHEMA = "ai_desk_track_record.v1"
_LEDGER = ("data", "ai_desk", "theses.jsonl")
_SCORED = ("data", "ai_desk", "scored.jsonl")
_TRACK = ("data", "ai_desk", "track_record.json")
_GRACE_BD = _s.GRACE_BD            # business days past check_by with no data → expired
_TERMINAL = _s.TERMINAL


# --------------------------------------------------------------------------- #
# AI-Desk calibration notes (English canonical + 简体中文 mirror) — desk-specific text
# --------------------------------------------------------------------------- #
def _calibration_note(overall: dict, by_conv: dict) -> str:
    if overall["n"] == 0:
        return ("No theses scored yet — the track record begins once the first "
                "check-by dates pass. Keep conviction modest until it does.")
    hi = by_conv.get("high", {})
    parts = [f"{overall['n']} scored, hit-rate {overall['hit_rate']} "
             f"(directional accuracy {overall['dir_accuracy']})."]
    if hi.get("n"):
        parts.append(f"High-conviction calls: {hi['hits']}/{hi['n']} holding.")
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
        parts.append(f"高置信判断：{hi['hits']}/{hi['n']} 仍成立。")
    if overall["n"] < 10:
        parts.append("样本极小 —— 将置信视为暂定并保持偏低。")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# thin re-exports / bindings over the shared engine, with ai_desk's config baked in.
# Existing callers (engine.policy_intent_desk, engine.radar_scorer) and tests import these
# from ai_desk_scorer; behaviour is byte-identical to the pre-extraction module.
# --------------------------------------------------------------------------- #
_now_iso = _s.now_iso
_load_jsonl = _s.load_jsonl
_dedupe_by_id = _s.dedupe_by_id
_covers = _s.covers
_close_at = _s.close_at
_max_close_between = _s.max_close_between
_start_level = _s.start_level
_eval_rel_return = _s.eval_rel_return
_eval_level = _s.eval_level
_EVAL = _s.EVALUATORS
_bucket = _s.bucket


def _load_ledger(root) -> dict:
    return _s.load_ledger(root, _LEDGER)


def _load_scored(root) -> dict:
    return _s.load_scored(root, _SCORED)


def _score_one(row: dict, root, today) -> dict | None:
    """Score one open thesis (reused by policy_intent_desk / radar_scorer)."""
    return _s.score_one(row, root, today)


def _aggregate(scored: list, ledger: dict, today) -> dict:
    """Aggregate scored rows into the AI-Desk track record (reused by other desks)."""
    return _s.aggregate(scored, ledger, today, schema=SCHEMA,
                        calibration_note_fn=_calibration_note,
                        calibration_note_zh_fn=_calibration_note_zh)


def _append_scored(rows: list, root) -> None:
    _s.append_scored(rows, root, _SCORED)


def _write_track(track: dict, root) -> None:
    _s.write_track(track, root, _TRACK)


def run(persist: bool = True, root=None, today=None) -> dict | None:
    """Score newly-due AI-Desk theses, append outcomes, rewrite the track record.
    Idempotent (skips ids already in scored.jsonl). Returns the track record, or None."""
    return _s.run(ledger_path=_LEDGER, scored_path=_SCORED, track_path=_TRACK, schema=SCHEMA,
                  calibration_note_fn=_calibration_note, calibration_note_zh_fn=_calibration_note_zh,
                  persist=persist, root=root, today=today, log_label="ai_desk_scorer")


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
            L.append(f"  · {c}: {b['hits']}/{b['n']} holding (dir {b['dir_accuracy']})")
    L += ["", "_context only — never scored, sized, or fed into an allocation_"]
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    _t = run(persist=True)
    print(render_markdown(_t) if _t else "ai_desk_scorer: nothing to do (no ledger).")
