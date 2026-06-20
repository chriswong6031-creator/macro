"""Grade the Divergence Radar + Narrative Brain falsifiable ledgers against the tape.

The accountability close-the-loop. Both desks log falsifiable theses in the ai_desk shape:
  * engine/radar.py        -> data/radar/theses.jsonl           (POSITIVE_DIVERGENCE watches)
  * engine/narrative_brain -> data/narrative_brain/theses.jsonl (durability ENTER/AVOID calls)
Each carries a machine-checkable `falsifier.check` (rel_return: ETF proxy vs SPY over a
horizon) + a `check_by` date. This scorer REUSES engine.ai_desk_scorer's eval + aggregation
verbatim — only the ledger directory differs — so the radar and the brain build the same kind
of honest, calibration-graded track record the AI desk already does.

Idempotent (skips ids already in <desk>/scored.jsonl); a thesis is graded only once its
check_by passes and price data exists, else it stays open. CONTEXT-ONLY — the track record
never feeds a score/size/allocation; it just keeps the desks accountable. Never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from engine import ai_desk_scorer as S
from lib import config

log = logging.getLogger(__name__)

DESKS = ("radar", "narrative_brain")   # data/<desk>/{theses,scored,track_record}


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _state_asof(row: dict) -> str | None:
    """The entry date for price levels — these ledgers log it as `logged_at` (or the id prefix
    YYYY-MM-DD), not the ai_desk `state_asof`."""
    if row.get("state_asof"):
        return row["state_asof"]
    la = row.get("logged_at") or ""
    if la:
        return la[:10]
    rid = str(row.get("id") or "")
    return rid[:10] if rid[:4].isdigit() else None


def _score_desk(desk: str, root: Path, today) -> tuple[Path, list, dict] | None:
    d = root / "data" / desk
    theses = {r["id"]: r for r in _load_jsonl(d / "theses.jsonl") if r.get("id")}
    if not theses:
        return None
    scored = {r["id"]: r for r in _load_jsonl(d / "scored.jsonl") if r.get("id")}
    new = []
    for tid, row in theses.items():
        if tid in scored:
            continue
        res = S._score_one({**row, "state_asof": _state_asof(row)}, root, today)
        if res is not None:
            new.append(res)
    combined = list({**scored, **{r["id"]: r for r in new}}.values())
    return d, new, S._aggregate(combined, theses, today)


def run(persist: bool = True, root=None, today=None) -> dict | None:
    """Score newly-due theses for both desks, append outcomes, rewrite each track record +
    a site copy. Returns {desk: track_record} or None. Never raises into the pipeline."""
    root = Path(root) if root else config.ROOT
    today = today or date.today()
    out: dict[str, dict] = {}
    for desk in DESKS:
        try:
            res = _score_desk(desk, root, today)
            if res is None:
                continue
            d, new, track = res
            if persist:
                if new:
                    with (d / "scored.jsonl").open("a") as fh:
                        for r in new:
                            fh.write(json.dumps(r, default=str) + "\n")
                (d / "track_record.json").write_text(json.dumps(track, indent=2, default=str))
                sp = root / "site" / "basketdata" / f"{desk}_track_record.json"
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(json.dumps(track, separators=(",", ":"), default=str))
            out[desk] = track
            log.info("radar_scorer[%s]: %d newly scored, %d decided total", desk, len(new), track["scored_total"])
        except Exception as e:  # noqa: BLE001 — accountability is best-effort, never fatal
            log.warning("radar_scorer[%s] failed: %s", desk, e)
    return out or None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    r = run()
    print(json.dumps({k: v.get("overall") for k, v in (r or {}).items()}, indent=2) if r
          else "radar_scorer: no ledgers to grade yet")
