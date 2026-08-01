"""engine.chronicle.governor — build + write the Chronicle W0 derived store.

Entry point: build_and_write(root=None, rebuild=False) -> dict summary.
Run via: python -m scripts.build_chronicle [--rebuild]  (scripts/build_chronicle.py
is the thin CLI wrapper — mirrors scripts/build_marketing.py's thinness over
engine/neuralweb/marketing_governor.py).

No LLM calls anywhere in this module or its imports (W0 is 100% deterministic).
Never-raise: every exception is absorbed into result["error"]; per-source
failures are already absorbed as per-adapter gap notes one level down
(engine.chronicle.spine.build_events), so result["error"] should in practice
only ever fire on a truly unexpected top-level bug.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import manifest as manifest_mod
from . import earnings_calls, rollups, spine, state_log

log = logging.getLogger(__name__)

_ARTIFACT_MANIFEST = "chronicle-manifest"

MANIFEST_REL = Path("data") / "chronicle" / "manifest.json"


def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def build_and_write(
    root: Path | str | None = None,
    rebuild: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the Chronicle store and write events.jsonl + rollups + manifest.json.

    Incremental (default): syncs healthy evidence-addressed earnings scores into
    the committed call-event ledger, appends tonight's state_log capture row
    (idempotent by date), THEN fully recomputes events.jsonl from all sources +
    the now-current Chronicle-owned ledgers.
    --rebuild: skips the state_log append and recomputes events.jsonl from all
    sources + the EXISTING state_log rows only — state_log.jsonl is never
    deleted or rewritten by rebuild (masterplan §0 gate 1 exemption).

    Never raises. result["error"] set only on a fatal top-level failure.
    """
    t0 = time.time()
    result: dict[str, Any] = {"events_path": None, "manifest_path": None}
    try:
        repo = _repo_root(root)
        now = now or datetime.now(timezone.utc)
        as_of = now.strftime("%Y-%m-%d")

        earnings_call_sync = earnings_calls.sync_from_scores(
            repo, rebuild=rebuild, as_of=now,
        )

        state_appended = False
        state_gap: str | None = None
        # M13: "rebuild" is itself a distinct reason — --rebuild deliberately
        # never touches the forward ledger, so its state_appended=False is
        # expected, not a symptom.
        state_reason = "rebuild_skipped"
        if not rebuild:
            state_appended, state_gap, state_reason = state_log.append_row_if_new(repo, now=now)

        events_path = repo / spine.EVENTS_REL
        prev_events = spine.load_events_jsonl(events_path)
        prev_ids = {e.get("id") for e in prev_events}

        raw_events, adapter_report = spine.build_events(repo, as_of=now)
        sync_reason = str(earnings_call_sync.get("reason") or "")
        if sync_reason not in {"", "current", "updated", "rebuild_skipped"}:
            info = adapter_report.setdefault("earnings_call", {"count": 0, "gap": None})
            sync_note = f"score projection sync: {sync_reason}"
            if earnings_call_sync.get("gap"):
                sync_note += f" ({earnings_call_sync['gap']})"
            info["gap"] = f"{info['gap']}; {sync_note}" if info.get("gap") else sync_note
        if state_gap:
            adapter_report["state_log_capture"] = {"count": 0, "gap": state_gap}

        # B1: union-merge with whatever was previously committed so a source
        # row leaving the current snapshot RETAINS its event instead of
        # silently vanishing. dropped_events is the (possibly empty) list of
        # previously-committed events the recompute no longer produces.
        events_sorted, dropped_events = spine.union_events(prev_events, raw_events)
        new_ids = {e.get("id") for e in events_sorted}
        added = len(new_ids - prev_ids)

        for name in adapter_report:
            adapter_report[name].setdefault("dropped_from_source", 0)
        if dropped_events:
            dropped_by_source: dict[str, int] = {}
            for e in dropped_events:
                src = e.get("source") or "unknown"
                dropped_by_source[src] = dropped_by_source.get(src, 0) + 1
            for src, cnt in dropped_by_source.items():
                info = adapter_report.setdefault(src, {"count": 0, "gap": None, "dropped_from_source": 0})
                info["dropped_from_source"] = cnt
                note = (f"{cnt} event(s) retained after their source row left the "
                        f"current snapshot (union-merge, never deleted)")
                info["gap"] = f"{info['gap']}; {note}" if info.get("gap") else note

        spine.write_events_jsonl(events_path, events_sorted)
        result["events_path"] = str(events_path)

        dates = sorted({e.get("date") for e in events_sorted if e.get("date")})
        coverage = {
            "start": dates[0] if dates else None,
            "end": dates[-1] if dates else None,
            "note": (f"{len(events_sorted)} events across {len(dates)} distinct date(s)"
                     if dates else "no events yet"),
        }

        daily_doc = rollups.build_daily(events_sorted, as_of)
        weekly_doc = rollups.build_weekly(events_sorted, as_of)
        daily_path = rollups.write_daily(repo, daily_doc)
        weekly_path = rollups.write_weekly(repo, weekly_doc)
        result["daily_path"] = str(daily_path)
        result["weekly_path"] = str(weekly_path)

        elapsed = time.time() - t0
        state_log_path = repo / state_log.STATE_LOG_REL
        payload = manifest_mod.build_manifest(
            repo=repo,
            as_of=as_of,
            coverage=coverage,
            adapter_report=adapter_report,
            events_path=events_path,
            state_log_path=state_log_path,
            earnings_call_path=repo / earnings_calls.CALL_EVENTS_REL,
            elapsed_s=elapsed,
        )
        try:
            from engine.neuralweb.envelope import stamp  # noqa: PLC0415
            payload = stamp(payload, artifact_id=_ARTIFACT_MANIFEST)
        except Exception as exc:  # noqa: BLE001
            log.warning("chronicle.governor: envelope stamp failed: %s", exc)
            now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            payload.setdefault("schema_version", 1)
            payload.setdefault("produced_by", "scripts/build_chronicle.py")
            payload.setdefault("produced_at", now_str)
            payload.setdefault("inputs_hash", "sha256:unstamped")
            payload.setdefault("tier", "display")

        manifest_path = repo / MANIFEST_REL
        _write_json_atomic(manifest_path, payload)
        result["manifest_path"] = str(manifest_path)

        result["adapter_report"] = adapter_report
        result["total_events"] = len(events_sorted)
        result["added"] = added
        result["state_appended"] = state_appended
        result["state_reason"] = state_reason
        result["earnings_call_sync"] = earnings_call_sync
        result["elapsed_s"] = round(elapsed, 3)
        result["rebuild"] = rebuild
    except Exception as exc:  # noqa: BLE001
        log.warning("chronicle.governor: build_and_write failed: %s", exc, exc_info=True)
        result["error"] = str(exc)
    return result


# m9: no __main__ block here — running this module directly would write the
# LIVE committed store from whatever local checkout state happens to be on
# disk, an off-nightly write path into a forward ledger. The one sanctioned
# entry point is scripts/build_chronicle.py (python -m scripts.build_chronicle
# [--rebuild]), which is explicit about root/rebuild and mirrors every other
# governor's CLI-wrapper convention in this repo.
