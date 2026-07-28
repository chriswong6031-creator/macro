"""Nightly private Trade Memory runner.

Reads only the explicitly configured operator's closed episodes from Supabase,
builds point-in-time evidence, writes private LLM autopsies back to the same rows,
then rebuilds the private pattern-candidate view.  No personal trade content or
derived personal pattern is written to git or stdout.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from engine.neuralweb import trade_memory
from engine.neuralweb.trade_memory_store import SupabaseTradeMemoryStore, build_store

log = logging.getLogger("run_trade_memory")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_prophet_pick_autopsies(root: str | Path | None = None) -> list[dict[str, Any]]:
    """Project canonical Prophet pick autopsies into the private pattern rebuild."""
    repo = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    base = repo / "data" / "standout_audit" / "pick_autopsies"
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for path in sorted(base.glob("*/*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            llm = doc.get("llm") if isinstance(doc.get("llm"), dict) else {}
            hypotheses = llm.get("signal_hypotheses")
            if not isinstance(hypotheses, list) or not hypotheses:
                continue
            attribution = (
                doc.get("attribution") if isinstance(doc.get("attribution"), dict) else {}
            )
            excess = attribution.get("excess_spy")
            if excess is None:
                excess = attribution.get("excess_21d")
            if excess is None:
                excess = attribution.get("excess_sector")
            try:
                numeric_excess = float(excess)
            except (TypeError, ValueError):
                continue
            outcome = (
                "win" if numeric_excess > 0
                else "loss" if numeric_excess < 0
                else "flat"
            )
            pick_id = str(doc.get("pick_id") or path.stem)
            out.append({
                "episode_ref": f"prophet:{pick_id}",
                "entry_date": doc.get("entry_date"),
                "outcome": outcome,
                "signal_hypotheses": hypotheses,
                "authority": "research_only",
                "direct_authority": False,
            })
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "trade_memory: one Prophet autopsy could not join pattern rebuild (%s)",
                type(exc).__name__,
            )
    return out


def run(
    store: SupabaseTradeMemoryStore | None,
    *,
    root: str | Path | None = None,
    cap: int = 8,
    model_caller: Callable[[str, str], Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Process a bounded batch; return counts only (privacy-safe)."""
    if store is None or not store.available:
        return {
            "ok": True,
            "configured": False,
            "processed": 0,
            "completed": 0,
            "failed": 0,
            "patterns": 0,
        }

    pending = store.fetch_pending(limit=cap)
    processed = completed = failed = 0
    for row in pending:
        processed += 1
        episode_id = str(row.get("id") or "")
        try:
            packet = trade_memory.build_evidence_packet(row, root=root)
            # Keep the database identity in the private packet; normalize_episode()
            # intentionally accepts only trade facts and therefore omits it.
            packet["episode"]["id"] = episode_id
            autopsy, provider = trade_memory.invoke_autopsy(
                packet, model_caller=model_caller
            )
            if autopsy is None:
                failed += 1
                if not dry_run:
                    store.update_episode(episode_id, {
                        "evidence_packet": packet,
                        "autopsy_state": "retry",
                        "autopsy_model": provider,
                        "autopsy_error": "no_structured_reply",
                        "updated_at": _now(),
                    })
                continue
            completed += 1
            if not dry_run:
                store.update_episode(episode_id, {
                    "evidence_packet": packet,
                    "autopsy": autopsy,
                    "autopsy_state": "complete",
                    "autopsy_model": provider,
                    "autopsied_at": _now(),
                    "autopsy_error": None,
                    "updated_at": _now(),
                })
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.warning("trade_memory: one private episode failed (%s)", type(exc).__name__)
            if not dry_run:
                store.update_episode(episode_id, {
                    "autopsy_state": "retry",
                    "autopsy_error": type(exc).__name__[:80],
                    "updated_at": _now(),
                })

    pattern_n = 0
    if not dry_run:
        rows = store.fetch_autopsied()
        autopsies: list[dict[str, Any]] = []
        for row in rows:
            item = row.get("autopsy")
            if not isinstance(item, dict):
                continue
            # Re-attach immutable episode facts needed by the deterministic
            # repetition/time-cluster gate.
            item = dict(item)
            item["episode_ref"] = str(row.get("id") or item.get("episode_ref") or "")
            item["entry_date"] = row.get("entry_date") or item.get("entry_date")
            item["outcome"] = row.get("outcome") or item.get("outcome")
            autopsies.append(item)
        # One private derived view, two canonical sources: owner rows above plus
        # Prophet's existing git-backed pick autopsies. Personal rows never move in
        # the other direction and no second episode store is created.
        autopsies.extend(_load_prophet_pick_autopsies(root))
        patterns = trade_memory.build_pattern_candidates(autopsies)
        if store.replace_patterns(patterns):
            pattern_n = len(patterns)

    return {
        "ok": True,
        "configured": True,
        "processed": processed,
        "completed": completed,
        "failed": failed,
        "patterns": pattern_n,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the private Prophet Trade Memory lane")
    parser.add_argument("--cap", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run(build_store(), cap=max(1, min(25, args.cap)), dry_run=args.dry_run)
    # Count-only output. Never print a ticker, date, note, price, packet, or autopsy.
    if not result["configured"]:
        print("trade_memory: private store not configured — clean no-op")
    else:
        print(
            "trade_memory: processed={processed} completed={completed} "
            "failed={failed} patterns={patterns}".format(**result)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
