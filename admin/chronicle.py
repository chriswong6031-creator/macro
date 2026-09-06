"""admin/chronicle.py — Chronicle (market context timeline) admin inspector.

Read-only, fail-soft (mirrors admin/marketing.py conventions exactly): every
public function returns {"ok": True, ...} or {"ok": False, "error": ...}. Never
writes. Panels read only the committed data/chronicle/ store.

Single entry point: overview(root=None) -> dict, exposing manifest health
(as_of, coverage, elapsed, per-adapter gaps), per-adapter counts, the last 20
events (date/source/title/weight), and the state_log tail (last 5 rows).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent

_EVENTS_REL = Path("data/chronicle/events.jsonl")
_STATE_LOG_REL = Path("data/chronicle/state_log.jsonl")
_MANIFEST_REL = Path("data/chronicle/manifest.json")

_ACCRUING_NOTE = (
    "data/chronicle/manifest.json not yet written — "
    "accruing after the first nightly Chronicle run."
)

_N_RECENT_EVENTS = 20
_N_STATE_LOG_TAIL = 5
_N_IMPACT_WINDOW = 24


def _default_root() -> Path:
    """Repo root for panel reads when no explicit ``root=`` is passed.

    Mirrors admin/marketing.py._default_root(): resolves through admin.paths.ROOT
    so a seeded dev/demo run (MACRO_ADMIN_ROOT=<tmp>) points every panel at the
    fixture tree. Fail-soft to the package grandparent if paths can't be imported.
    """
    try:
        from .paths import ROOT  # noqa: PLC0415
        return ROOT
    except Exception:  # noqa: BLE001
        return _HERE.parent


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl(path: Path) -> list[dict]:
    try:
        if not path.exists():
            return []
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out
    except Exception:  # noqa: BLE001
        return []


def overview(root=None) -> dict:
    """Manifest health + per-adapter counts + recent events + state_log tail.

    Returns ok:True with an honest accruing note (never ok:False) when the
    manifest has not been written yet — day-0 / bare-fixture-root render.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        manifest = _read_json(repo / _MANIFEST_REL)
        events = _read_jsonl(repo / _EVENTS_REL)
        state_log_rows = _read_jsonl(repo / _STATE_LOG_REL)

        events_sorted = sorted(
            events, key=lambda e: (e.get("date") or "", e.get("id") or ""), reverse=True,
        )
        recent_events = [
            {
                "date": e.get("date"),
                "source": e.get("source"),
                "title": e.get("title"),
                "weight_hint": e.get("weight_hint"),
                "tickers": e.get("tickers") or [],
            }
            for e in events_sorted[:_N_RECENT_EVENTS]
        ]

        state_log_tail = sorted(
            state_log_rows, key=lambda r: str(r.get("date") or ""),
        )[-_N_STATE_LOG_TAIL:]

        # F05/MO-PAID-017: real reader of the consequence projection over a
        # bounded recent window (never a full-corpus nightly dump).
        impact_surface = None
        try:
            from engine.chronicle import impact as impact_mod  # noqa: PLC0415
            impact_surface = impact_mod.glance_consequence_surface(
                events,
                limit=_N_IMPACT_WINDOW,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("chronicle.overview impact surface failed: %s", exc)
            impact_surface = {
                "served_as_market_feed": False,
                "market_feed_disposition": "explicitly_does_not_serve_market_feed",
                "stance_en": "Not available yet",
                "stance_zh": "暂不可用",
                "reason_en": "Consequence projection failed to load.",
                "reason_zh": "后果投影未能加载。",
                "families": {},
                "rows": [],
                "event_count": 0,
                "error": str(exc),
            }

        if manifest is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "manifest": None,
                "as_of": None,
                "coverage": None,
                "elapsed_s": None,
                "adapters": None,
                "gap_notes": [],
                "total_events": len(events),
                "recent_events": recent_events,
                "state_log_tail": state_log_tail,
                "impact_surface": impact_surface,
            }

        return {
            "ok": True,
            "manifest": {
                "produced_at": manifest.get("produced_at"),
                "inputs_hash": manifest.get("inputs_hash"),
                "tier": manifest.get("tier"),
            },
            "as_of": manifest.get("as_of"),
            "coverage": manifest.get("coverage"),
            "elapsed_s": manifest.get("elapsed_s"),
            "adapters": manifest.get("adapters"),
            "ledgers": manifest.get("ledgers"),
            "gap_notes": manifest.get("gap_notes") or [],
            "total_events": len(events),
            "recent_events": recent_events,
            "state_log_tail": state_log_tail,
            "impact_surface": impact_surface,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("chronicle.overview failed: %s", exc)
        return {"ok": False, "error": str(exc)}
