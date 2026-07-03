"""Alt-data falsifiable ledger — what EARNS alt-data a scored vote.

Every cross-signal CONVERGENCE (a ticker lit by >=2 independent alt-data channels)
becomes a DATED, BENCHMARKED, FALSIFIABLE thesis:

    "alt-data convergence on X  =>  X beats SPY over the next ~63 trading days"

We log it on the detection day with entry levels snapshotted, then grade it vs SPY
once the window elapses — reusing the EXACT engine.ai_desk_scorer evaluators (no new
scoring code, no LLM). This is the honest path into the score / model layer: the
signal earns a vote only after the track record shows it predicts forward returns.
Until then it stays display/context-only (conviction starts 'low', never sized).

  data/altdata/theses.jsonl       append-only falsifiable theses (we own this)
  data/altdata/scored.jsonl       one outcome row per matured thesis (idempotent)
  data/altdata/track_record.json  rolling hit-rate the page + brain read back

Only SCORABLE names are logged: the ticker AND SPY must have a price series. Thin /
private vehicles (ABTC, WLFI, …) are recorded in by_ticker but never scored.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from lib import config
from engine import ai_desk as _desk
from engine import ai_desk_scorer as _scorer

log = logging.getLogger(__name__)

HORIZON_D = 63          # ~3 trading months — alt-data flow signals are medium-horizon
_CAL_DAYS = 91          # ≈ 63 trading days in calendar days (for the check_by date)
THRESHOLD = -0.05       # falsified iff the name UNDERperforms SPY by >5% over the window
MIN_SCORE = 2
BENCH = "SPY"
SCHEMA = "altdata_track_record.v1"

_LEDGER = ("data", "altdata", "theses.jsonl")
_SCORED = ("data", "altdata", "scored.jsonl")
_TRACK = ("data", "altdata", "track_record.json")


def _p(root, parts):
    return Path(root).joinpath(*parts)


def _active_subjects(ledger_rows: list, asof: str) -> set:
    """Tickers with a thesis whose window has NOT elapsed yet — vintage dedupe so a
    persistently-convergent name is logged once per window, not every day."""
    return {r.get("ticker") for r in ledger_rows
            if r.get("ticker") and str(r.get("check_by", "")) >= asof}


def build_theses(by_ticker: dict, root=None, today=None) -> list:
    root = Path(root) if root else config.ROOT
    today = today or date.today()
    asof = str(today)
    existing = _scorer._load_jsonl(_p(root, _LEDGER))
    active = _active_subjects(existing, asof)
    existing_ids = {r.get("id") for r in existing}
    check_by = (today + timedelta(days=_CAL_DAYS)).isoformat()

    new = []
    for tk, rec in (by_ticker.get("tickers") or {}).items():
        score = int(rec.get("convergence_score", 0) or 0)
        if score < MIN_SCORE or tk in active:
            continue
        e0 = _desk._level_asof(tk, root, asof)
        b0 = _desk._level_asof(BENCH, root, asof)
        if e0 is None or b0 is None:        # not SCORABLE (thin / private) -> skip, never score
            continue
        rid = f"{asof}-{tk}-altconv"
        if rid in existing_ids:
            continue
        chans = rec.get("channels", [])
        new.append({
            "id": rid, "ticker": tk, "logged_at": datetime.now(timezone.utc).isoformat(),
            "state_asof": asof,
            "subject": f"{tk} alt-data convergence",
            "lean": "overweight", "conviction": "low", "horizon_d": HORIZON_D,
            "convergence_score": score, "channels": chans,
            "trump_linked": bool(rec.get("trump_linked")),
            "falsifier": {
                "text": f"{tk} fails to beat {BENCH} (underperforms by >{abs(THRESHOLD) * 100:.0f}%) "
                        f"over ~{HORIZON_D} trading days despite {score}-channel convergence "
                        f"({', '.join(chans)}).",
                "check": {"kind": "rel_return", "subject_ticker": tk, "vs": BENCH,
                          "op": "<", "threshold": THRESHOLD, "horizon_d": HORIZON_D},
            },
            "check_by": check_by,
            "entry_levels": {tk: e0, BENCH: b0},
            "status": "open", "scored_at": None, "outcome": None, "realized": None,
        })
    if new:
        path = _p(root, _LEDGER)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            for r in new:
                fh.write(json.dumps(r, default=str) + "\n")
        log.info("altdata ledger: logged %d new thesis(es): %s",
                 len(new), ", ".join(r["ticker"] for r in new))
    return new


def score(root=None, today=None) -> dict | None:
    try:
        root = Path(root) if root else config.ROOT
        today = today or date.today()
        ledger = _scorer._dedupe_by_id(_scorer._load_jsonl(_p(root, _LEDGER)))
        already = _scorer._dedupe_by_id(_scorer._load_jsonl(_p(root, _SCORED)))
        new_rows = []
        for tid, row in ledger.items():
            if tid in already:
                continue
            res = _scorer._score_one(row, root, today)   # reuse the exact evaluator
            if res is not None:
                new_rows.append(res)
        combined = list(_scorer._dedupe_by_id(list(already.values()) + new_rows).values())
        track = _scorer._aggregate(combined, ledger, today)
        track["schema"] = SCHEMA
        track["note"] = ("Alt-data convergence theses graded vs SPY. Context-only — the signal "
                         "earns a scored vote only once this track record shows forward edge.")

        sp = _p(root, _SCORED)
        sp.parent.mkdir(parents=True, exist_ok=True)
        if new_rows:
            with open(sp, "a") as fh:
                for r in new_rows:
                    fh.write(json.dumps(r, default=str) + "\n")
        _p(root, _TRACK).write_text(json.dumps(track, indent=2, default=str))
        # derive from root (== config.ROOT in prod) so root=tmp_path tests
        # don't overwrite the tracked site/altdata/track_record.json
        site = root / "site" / "altdata"
        site.mkdir(parents=True, exist_ok=True)
        (site / "track_record.json").write_text(json.dumps(track, indent=2, default=str))
        if new_rows:
            log.info("altdata ledger: scored %d (%s)", len(new_rows),
                     ", ".join(f"{r['id']}:{r['outcome']}" for r in new_rows))
        return track
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("altdata ledger score failed: %s", e)
        return None


def load_track(root=None) -> dict:
    p = _p(root or config.ROOT, _TRACK)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def rebuild(by_ticker: dict, root=None, today=None) -> dict | None:
    build_theses(by_ticker, root=root, today=today)
    return score(root=root, today=today)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    from engine import altdata_signals
    bt = altdata_signals.load()
    t = rebuild(bt) if bt else None
    print(json.dumps(t, indent=2) if t else "altdata_ledger: no by_ticker substrate yet")
