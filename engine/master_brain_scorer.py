"""Master Brain scorer — the durability loop for the flagship cross-asset brain (Phase C).

master_brain now stakes its OWN falsifiable cross-asset leans (engine.master_brain producer
→ data/master_brain/theses.jsonl). This grades them against realized closes, exactly like
engine.ai_desk_scorer grades the AI desk — closing the flagship loop end-to-end (it already
READS the desks' track records via gather_state, PR #376; this adds the WRITE/grade side).

A thin ai_desk-specific binding over the shared engine.desk_scorer (the same way
engine.ai_desk_scorer is): its ledger paths + schema + calibration notes, delegating the
predicate evaluation + idempotent scoring + aggregation. CONTEXT-ONLY (track_record never
enters a score/size); deterministic (no LLM); degrade-never-raise.

Nothing imports this module at top level (it runs via `python -m engine.master_brain_scorer`
in the daily build, before the master_brain generator step), so its top-level import of
engine.desk_scorer — which imports engine.ai_desk, which imports engine.master_brain — is
cycle-free.
"""
from __future__ import annotations

import logging
from pathlib import Path

from engine import desk_scorer as _s

log = logging.getLogger(__name__)

SCHEMA = "master_brain_track_record.v1"
_LEDGER = ("data", "master_brain", "theses.jsonl")
_SCORED = ("data", "master_brain", "scored.jsonl")
_TRACK = ("data", "master_brain", "track_record.json")


def _calibration_note(overall: dict, by_conv: dict) -> str:
    if overall["n"] == 0:
        return ("No cross-asset leans scored yet — the brain stakes them rarely and the "
                "track record begins once the first check-by dates pass. Keep conviction modest.")
    hi = by_conv.get("high", {})
    parts = [f"{overall['n']} leans scored, hit-rate {overall['hit_rate']} "
             f"(directional accuracy {overall['dir_accuracy']})."]
    if hi.get("n"):
        parts.append(f"High-conviction calls: {hi['hits']}/{hi['n']} holding.")
    if overall["n"] < 10:
        parts.append("Sample is tiny — the brain's leans are accountability, not yet a validated edge.")
    return " ".join(parts)


def _calibration_note_zh(overall: dict, by_conv: dict) -> str:
    if overall["n"] == 0:
        return "尚无跨资产判断被评分 —— 大脑很少下注，待首批核查日到期后开始累积战绩；在此之前置信保持克制。"
    hi = by_conv.get("high", {})
    parts = [f"已评分 {overall['n']} 条，命中率 {overall['hit_rate']}"
             f"（方向准确率 {overall['dir_accuracy']}）。"]
    if hi.get("n"):
        parts.append(f"高置信判断：{hi['hits']}/{hi['n']} 仍成立。")
    if overall["n"] < 10:
        parts.append("样本极小 —— 大脑的判断是问责，尚非验证过的优势。")
    return "".join(parts)


def run(persist: bool = True, root=None, today=None) -> dict | None:
    """Score newly-due master_brain theses, append outcomes, rewrite the track record.
    Idempotent; NEVER raises. Gets a by_regime breakdown for free (the ledger stamps regime)."""
    return _s.run(ledger_path=_LEDGER, scored_path=_SCORED, track_path=_TRACK, schema=SCHEMA,
                  calibration_note_fn=_calibration_note, calibration_note_zh_fn=_calibration_note_zh,
                  persist=persist, root=root, today=today, log_label="master_brain_scorer")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    t = run(persist=True)
    print(f"master_brain_scorer: {(t or {}).get('scored_total', 0)} scored, "
          f"{(t or {}).get('open', 0)} open")
